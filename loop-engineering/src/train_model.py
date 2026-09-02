"""Train NIDS classifiers on the flow-level features.

Trains two Random Forest models to compare a standard (random, stratified)
split against a cross-source split that isolates the label/source_dataset
confound documented in RALPH_PROMPT.md (benign==caida, malicious==cic+unsw):

  1. "standard": random 80/20 stratified split over the full feature table.
  2. "cross_source": train on caida+cic, test on unsw only (a source the
     model never saw during training) -- this is the honest generalization
     check for "attack detection" vs. "capture-environment fingerprinting".

Raw identity columns (src_ip, dst_ip, src_port, dst_port) are dropped before
training: since each source dataset was captured on a different network,
those columns are near-perfect proxies for source_dataset (and therefore for
label), so keeping them would let the model cheat via the confound instead
of learning traffic behavior. protocol is kept as a small-cardinality
behavioral feature.

n_jobs is capped (not -1) because this machine only has 8GB RAM and an
unbounded thread pool has previously caused OOM kills during parallel
training on this box.
"""
import gc
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

FEATURES = [
    "protocol",
    "flow_pkt_count",
    "flow_byte_count",
    "pkt_size_mean",
    "pkt_size_std",
    "pkt_size_min",
    "pkt_size_max",
    "iat_mean",
    "iat_std",
    "iat_min",
    "iat_max",
    "flow_duration",
    "pkt_size_entropy",
]

# n_estimators/max_depth kept modest and n_jobs=1 (not -1/2): this machine has 8GB RAM
# total and is shared with other apps (observed as low as ~0.3GB free system-wide during
# a prior attempt), so a lighter model that finishes reliably beats a bigger one that
# gets killed mid-fit by system-wide memory pressure / swap thrash.
RF_PARAMS = dict(
    n_estimators=100,
    max_depth=15,
    class_weight="balanced",
    n_jobs=1,
    random_state=42,
)

# The benign class (caida) is ~6.8x the combined malicious class (cic+unsw). A prior
# full-data training attempt (2.2M rows, n_estimators=200, n_jobs=2) ran >25 minutes
# without finishing and was killed under system memory pressure. Undersample the
# majority (caida) class to keep training data volume bounded; class_weight="balanced"
# still corrects the residual imbalance within the sampled set.
UNDERSAMPLE_RATIO = 3  # cap caida rows at this multiple of the minority count
RANDOM_STATE = 42

# Exact flow counts per source, from the feature-extraction run log
# (loop-engineering/data/processed/_extract_log.txt). Used only to size the
# undersampling probability below -- not relied on for correctness, since the
# chunked reader below counts/filters the real rows as it streams them.
CAIDA_N = 1_942_256
CIC_N = 161_947
UNSW_N = 122_295

CHUNKSIZE = 200_000
READ_DTYPES = {
    "protocol": "int16",
    "flow_pkt_count": "int32",
    "flow_byte_count": "float32",
    "pkt_size_mean": "float32",
    "pkt_size_std": "float32",
    "pkt_size_min": "float32",
    "pkt_size_max": "float32",
    "iat_mean": "float32",
    "iat_std": "float32",
    "iat_min": "float32",
    "iat_max": "float32",
    "flow_duration": "float32",
    "pkt_size_entropy": "float32",
    "label": "int8",
}


def log(msg, t0):
    print(f"[{time.time()-t0:7.1f}s] {msg}", file=sys.stderr, flush=True)


def load_undersampled(t0):
    """Stream features.csv in chunks instead of loading it whole.

    A previous attempt (plain pd.read_csv of the full 2.2M-row / 19-column
    file, i.e. before dropping the id columns and before undersampling) was
    killed before it even finished the read under system-wide memory
    pressure (observed free RAM as low as ~0.3GB, shared with other apps on
    this 8GB machine). Reading in chunks with usecols/dtype restricted to
    only what training needs, and subsampling the majority (caida) class
    chunk-by-chunk, keeps peak memory bounded by CHUNKSIZE instead of by the
    full file.
    """
    prob_std = min(1.0, UNDERSAMPLE_RATIO * (CIC_N + UNSW_N) / CAIDA_N)
    prob_cs = min(1.0, UNDERSAMPLE_RATIO * CIC_N / CAIDA_N)
    rng = np.random.default_rng(RANDOM_STATE)

    usecols = FEATURES + ["source_dataset", "label"]
    caida_std_parts, caida_cs_parts, cic_parts, unsw_parts = [], [], [], []

    reader = pd.read_csv(
        "loop-engineering/data/processed/features.csv",
        usecols=usecols,
        dtype=READ_DTYPES,
        chunksize=CHUNKSIZE,
    )
    n_seen = 0
    for chunk in reader:
        n_seen += len(chunk)
        is_caida = chunk["source_dataset"].values == "caida"
        if is_caida.any():
            caida_chunk = chunk.loc[is_caida]
            keep_std = rng.random(len(caida_chunk)) < prob_std
            caida_std_parts.append(caida_chunk.loc[keep_std])
            keep_cs = rng.random(len(caida_chunk)) < prob_cs
            caida_cs_parts.append(caida_chunk.loc[keep_cs])
        is_cic = chunk["source_dataset"].values == "cic"
        if is_cic.any():
            cic_parts.append(chunk.loc[is_cic])
        is_unsw = chunk["source_dataset"].values == "unsw"
        if is_unsw.any():
            unsw_parts.append(chunk.loc[is_unsw])
    log(f"streamed {n_seen:,} rows from features.csv (chunksize={CHUNKSIZE:,})", t0)

    caida_std = pd.concat(caida_std_parts, ignore_index=True)
    caida_cs = pd.concat(caida_cs_parts, ignore_index=True)
    cic_df = pd.concat(cic_parts, ignore_index=True)
    unsw_df = pd.concat(unsw_parts, ignore_index=True)
    del caida_std_parts, caida_cs_parts, cic_parts, unsw_parts
    gc.collect()
    log(
        f"caida undersampled {CAIDA_N:,} -> std:{len(caida_std):,} (p={prob_std:.3f}) "
        f"/ cross_source:{len(caida_cs):,} (p={prob_cs:.3f}); cic={len(cic_df):,} unsw={len(unsw_df):,}",
        t0,
    )
    return caida_std, caida_cs, cic_df, unsw_df


def main():
    t0 = time.time()
    caida_std, caida_cs, cic, unsw = load_undersampled(t0)

    # --- 1. standard random stratified split (caida already undersampled above) ---
    df_std = pd.concat([caida_std, cic, unsw], ignore_index=True)
    del caida_std
    log(f"[standard] training pool = {len(df_std):,} rows", t0)

    X_train, X_test, y_train, y_test, src_train, src_test = train_test_split(
        df_std[FEATURES],
        df_std["label"],
        df_std["source_dataset"],
        test_size=0.2,
        stratify=df_std["label"],
        random_state=RANDOM_STATE,
    )
    rf_standard = RandomForestClassifier(**RF_PARAMS)
    rf_standard.fit(X_train, y_train)
    log(f"[standard] trained on {len(X_train):,} rows", t0)

    joblib.dump(rf_standard, "loop-engineering/models/rf_standard_split.joblib")
    X_test.assign(label=y_test, source_dataset=src_test).to_csv(
        "loop-engineering/data/processed/test_standard.csv", index=False
    )
    log("[standard] model + test set saved", t0)
    del rf_standard, X_train, X_test, y_train, y_test, src_train, src_test, df_std
    gc.collect()

    # --- 2. cross-source split: train on caida(undersampled)+cic, test on unseen unsw ---
    df_train_cs = pd.concat([caida_cs, cic], ignore_index=True)
    del caida_cs
    log(
        f"[cross_source] training pool = {len(df_train_cs):,} rows (caida+cic), "
        f"test pool (unsw, unseen) = {len(unsw):,} rows",
        t0,
    )

    rf_cross = RandomForestClassifier(**RF_PARAMS)
    rf_cross.fit(df_train_cs[FEATURES], df_train_cs["label"])
    log(f"[cross_source] trained on {len(df_train_cs):,} rows (caida+cic)", t0)

    joblib.dump(rf_cross, "loop-engineering/models/rf_cross_source.joblib")
    unsw[FEATURES + ["label"]].to_csv(
        "loop-engineering/data/processed/test_cross_source.csv", index=False
    )
    log("[cross_source] model + test set saved", t0)
    log("done", t0)


if __name__ == "__main__":
    main()
