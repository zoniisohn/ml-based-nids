"""
Flow-level feature extraction for the NIDS homework pipeline.

Reads packet-level CSVs from data/raw/ (CAIDA / CIC / UNSW captures, all
60-second windows), groups packets into unidirectional flows keyed by the
5-tuple (src_ip, dst_ip, src_port, dst_port, protocol), and computes a
flow-level feature table suitable for a binary classifier
(benign vs. malicious).

Input schema (no header row, 7 comma-separated columns, confirmed by
inspecting data/raw/*.csv directly since no documentation ships with them):

    src_ip, dst_ip, src_port, dst_port, protocol, pkt_size, timestamp

  - src_ip / dst_ip : IPv4 address encoded as an unsigned 32-bit integer
  - src_port / dst_port : transport port (0 for protocols without ports)
  - protocol : IP protocol number (6=TCP, 17=UDP, 1=ICMP, etc.)
  - pkt_size : packet size in bytes
  - timestamp : capture time as a Unix epoch float (seconds)

All three raw files share this exact schema, so a single normalized
loading path is used for all of them (no per-dataset column remapping is
needed) -- this was verified against real header-less rows from each file
before writing this script.

Labeling (per assignment instructions, this is not derivable from the CSVs
themselves so it is set from *which file* a flow's packets came from):
  - CAIDA  -> label 0 (benign backbone traffic)
  - CIC    -> label 1 (malicious / attack traffic)
  - UNSW   -> label 1 (malicious / attack traffic)

Memory strategy (caida_60_sec_new.csv is ~1.8GB, cic_60_sec_new.csv is
~660MB -- too large to comfortably load whole into a DataFrame at once):
  - Each file is streamed with pandas.read_csv(chunksize=...).
  - Per chunk, per-flow *sufficient statistics* are computed with a single
    vectorized groupby (count, sum, sum-of-squares, min, max for packet
    size and for inter-arrival time). These small per-chunk-per-flow
    partial-aggregate tables are collected in a list and combined with one
    final groupby-reduce at the end (a standard chunked map-reduce), so the
    full raw packet list is never held in memory at once.
  - Shannon entropy needs the *exact value distribution* per flow, which
    sufficient statistics alone can't give. This is accumulated with
    per-flow collections.Counter objects (packet-size Counter keyed by the
    exact byte value; IAT Counter keyed by the IAT rounded to microsecond
    precision, since raw floating point timestamps are close to unique and
    would make a full-precision histogram meaningless). Real traffic has
    heavy repetition in both packet size and inter-arrival spacing, so
    these Counters stay far smaller than the raw packet count.
  - Inter-arrival time crosses chunk boundaries (a flow's packets can be
    split across two chunks). Since every source file is already sorted by
    timestamp ascending (verified below), a dict of "last seen timestamp
    per flow" is carried across chunk boundaries to correctly compute the
    IAT of the first packet of a flow within a new chunk.

Output: data/processed/features.csv, one row per flow, label as the last
column. Re-run this script any time data/raw/ changes; it always rebuilds
the full features.csv from scratch (no incremental append).
"""

import math
import os
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

RAW_DIR = "data/raw"
OUT_DIR = "data/processed"
OUT_PATH = os.path.join(OUT_DIR, "features.csv")

COLS = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol", "pkt_size", "timestamp"]
FLOW_KEY = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol"]

DTYPES = {
    "src_ip": "int64",
    "dst_ip": "int64",
    "src_port": "int32",
    "dst_port": "int32",
    "protocol": "int16",
    "pkt_size": "int64",   # int64 to keep byte-sum / sum-of-squares safe for very large flows
    "timestamp": "float64",
}

CHUNKSIZE = 2_000_000
IAT_ROUND_DECIMALS = 6  # microsecond-level bucketing for a meaningful IAT histogram

# (filename, label, source name) -- label per assignment: CAIDA=benign(0), CIC/UNSW=malicious(1)
SOURCES = [
    ("caida_60_sec_new.csv", 0, "caida"),
    ("cic_60_sec_new.csv", 1, "cic"),
    ("unsw_60_sec_new.csv", 1, "unsw"),
]


def shannon_entropy_from_counter(counter: Counter) -> float:
    """Shannon entropy (base 2) of the discrete distribution described by counter's counts."""
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    ent = 0.0
    for c in counter.values():
        if c <= 0:
            continue
        p = c / total
        ent -= p * math.log2(p)
    return ent


def process_file(path: str, label: int, source_name: str):
    """Stream one packet-level CSV and return a flow-level feature DataFrame for it."""
    partial_aggs = []
    size_counters = defaultdict(Counter)   # flow key -> Counter(pkt_size -> count)
    iat_counters = defaultdict(Counter)    # flow key -> Counter(rounded_iat -> count)
    last_ts_map = {}                       # flow key -> last seen timestamp (cross-chunk IAT)

    n_rows = 0
    reader = pd.read_csv(path, header=None, names=COLS, dtype=DTYPES, chunksize=CHUNKSIZE)
    for chunk_id, chunk in enumerate(reader):
        n_rows += len(chunk)
        chunk = chunk.copy()
        chunk["pkt_size_sq"] = chunk["pkt_size"].astype("float64") ** 2

        # ---- vectorized per-flow numeric sufficient statistics for this chunk ----
        agg = chunk.groupby(FLOW_KEY, sort=False).agg(
            count=("pkt_size", "size"),
            size_sum=("pkt_size", "sum"),
            size_sumsq=("pkt_size_sq", "sum"),
            size_min=("pkt_size", "min"),
            size_max=("pkt_size", "max"),
            ts_min=("timestamp", "min"),
            ts_max=("timestamp", "max"),
        ).reset_index()

        # ---- exact packet-size value distribution, merged into the global per-flow Counter ----
        size_vc = chunk.groupby(FLOW_KEY, sort=False)["pkt_size"].value_counts()
        for key, cnt in size_vc.items():
            flow_key = key[:-1]
            val = key[-1]
            size_counters[flow_key][val] += int(cnt)

        # ---- inter-arrival time within this chunk ----
        # Stable sort by flow key preserves each flow's original (already time-ascending)
        # row order, so a plain diff() per group gives the correct within-chunk IAT.
        chunk_sorted = chunk.sort_values(FLOW_KEY, kind="mergesort")
        iat = chunk_sorted.groupby(FLOW_KEY, sort=False)["timestamp"].diff()
        nan_mask = iat.isna()

        if nan_mask.any():
            first_rows = chunk_sorted.loc[nan_mask, FLOW_KEY + ["timestamp"]]
            keys = list(first_rows[FLOW_KEY].itertuples(index=False, name=None))
            prev_vals = np.array([last_ts_map.get(k, np.nan) for k in keys], dtype="float64")
            filled = first_rows["timestamp"].to_numpy() - prev_vals
            iat.loc[nan_mask] = filled

        # guard against any floating-point noise producing a tiny negative IAT
        iat = iat.clip(lower=0)
        chunk_sorted = chunk_sorted.assign(iat=iat.to_numpy())

        # update the cross-chunk "last timestamp per flow" map
        for row in agg.itertuples(index=False):
            fk = tuple(getattr(row, c) for c in FLOW_KEY)
            last_ts_map[fk] = row.ts_max

        # ---- IAT sufficient statistics (rows with iat==NaN => truly the very first packet
        #      of that flow ever seen -> correctly excluded from IAT stats) ----
        valid_iat = chunk_sorted.dropna(subset=["iat"])
        if len(valid_iat):
            valid_iat = valid_iat.copy()
            valid_iat["iat_sq"] = valid_iat["iat"] ** 2
            iat_agg = valid_iat.groupby(FLOW_KEY, sort=False).agg(
                iat_count=("iat", "size"),
                iat_sum=("iat", "sum"),
                iat_sumsq=("iat_sq", "sum"),
                iat_min=("iat", "min"),
                iat_max=("iat", "max"),
            ).reset_index()
            agg = agg.merge(iat_agg, on=FLOW_KEY, how="left")
            agg["iat_count"] = agg["iat_count"].fillna(0.0)
            agg["iat_sum"] = agg["iat_sum"].fillna(0.0)
            agg["iat_sumsq"] = agg["iat_sumsq"].fillna(0.0)
            agg["iat_min"] = agg["iat_min"].fillna(np.inf)
            agg["iat_max"] = agg["iat_max"].fillna(-np.inf)

            # rounded-IAT value distribution, merged into the global per-flow Counter
            iat_tmp = valid_iat[FLOW_KEY].copy()
            iat_tmp["iat_r"] = valid_iat["iat"].round(IAT_ROUND_DECIMALS)
            iat_vc = iat_tmp.groupby(FLOW_KEY + ["iat_r"], sort=False).size()
            for key, cnt in iat_vc.items():
                flow_key = key[:-1]
                val = key[-1]
                iat_counters[flow_key][val] += int(cnt)
        else:
            agg["iat_count"] = 0.0
            agg["iat_sum"] = 0.0
            agg["iat_sumsq"] = 0.0
            agg["iat_min"] = np.inf
            agg["iat_max"] = -np.inf

        partial_aggs.append(agg)
        print(f"  [{source_name}] chunk {chunk_id}: {len(chunk):,} rows "
              f"(cumulative {n_rows:,}), {len(agg):,} flows in this chunk")

    if not partial_aggs:
        return pd.DataFrame(), 0, 0

    all_partial = pd.concat(partial_aggs, ignore_index=True)
    final = all_partial.groupby(FLOW_KEY, sort=False).agg(
        packet_count=("count", "sum"),
        byte_count=("size_sum", "sum"),
        size_sumsq=("size_sumsq", "sum"),
        pkt_size_min=("size_min", "min"),
        pkt_size_max=("size_max", "max"),
        first_ts=("ts_min", "min"),
        last_ts=("ts_max", "max"),
        iat_count=("iat_count", "sum"),
        iat_sum=("iat_sum", "sum"),
        iat_sumsq=("iat_sumsq", "sum"),
        iat_min=("iat_min", "min"),
        iat_max=("iat_max", "max"),
    ).reset_index()

    # ---- derived features ----
    final["flow_duration"] = (final["last_ts"] - final["first_ts"]).clip(lower=0)

    final["pkt_size_mean"] = final["byte_count"] / final["packet_count"]
    pkt_var = final["size_sumsq"] / final["packet_count"] - final["pkt_size_mean"] ** 2
    final["pkt_size_std"] = np.sqrt(pkt_var.clip(lower=0))

    has_iat = final["iat_count"] > 0
    final["iat_mean"] = np.where(has_iat, final["iat_sum"] / final["iat_count"].replace(0, np.nan), 0.0)
    iat_var = final["iat_sumsq"] / final["iat_count"].replace(0, np.nan) - final["iat_mean"] ** 2
    final["iat_std"] = np.where(has_iat, np.sqrt(iat_var.clip(lower=0)), 0.0)
    final["iat_min"] = np.where(has_iat, final["iat_min"], 0.0)
    final["iat_max"] = np.where(has_iat, final["iat_max"], 0.0)
    final["iat_mean"] = final["iat_mean"].fillna(0.0)

    # ---- entropy features from the accumulated per-flow Counters ----
    flow_tuples = list(final[FLOW_KEY].itertuples(index=False, name=None))
    final["pkt_size_entropy"] = [
        shannon_entropy_from_counter(size_counters.get(fk, Counter())) for fk in flow_tuples
    ]
    final["iat_entropy"] = [
        shannon_entropy_from_counter(iat_counters.get(fk, Counter())) for fk in flow_tuples
    ]

    final["source_dataset"] = source_name
    final["label"] = label

    out_cols = FLOW_KEY + [
        "packet_count", "byte_count", "flow_duration",
        "pkt_size_mean", "pkt_size_min", "pkt_size_max", "pkt_size_std",
        "iat_mean", "iat_min", "iat_max", "iat_std",
        "pkt_size_entropy", "iat_entropy",
        "source_dataset", "label",
    ]
    return final[out_cols], n_rows, len(final)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    stats = {}
    for filename, label, source_name in SOURCES:
        path = os.path.join(RAW_DIR, filename)
        if not os.path.exists(path):
            print(f"WARNING: {path} not found, skipping {source_name}")
            stats[source_name] = {"status": "missing", "rows": 0, "flows": 0}
            continue
        print(f"Processing {source_name} ({path}) ...")
        df, n_rows, n_flows = process_file(path, label, source_name)
        print(f"  -> {n_rows:,} packets, {n_flows:,} flows")
        stats[source_name] = {"status": "ok", "rows": n_rows, "flows": n_flows}
        if len(df):
            results.append(df)

    if not results:
        raise SystemExit("No datasets could be processed -- check data/raw/*.csv")

    combined = pd.concat(results, ignore_index=True)
    combined.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(combined):,} total flows to {OUT_PATH}")
    print(combined["label"].value_counts())
    return stats, combined


if __name__ == "__main__":
    main()
