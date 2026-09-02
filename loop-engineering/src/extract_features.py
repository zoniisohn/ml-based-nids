"""Flow-level feature extraction for the NIDS homework (Loop Engineering track).

Reads packet-level CSVs (columns: src_ip,dst_ip,src_port,dst_port,protocol,
pkt_size,timestamp; no header) and aggregates them into directional 5-tuple
flows (src_ip,dst_ip,src_port,dst_port,protocol). Designed to run on an 8GB
RAM machine against files up to ~1.8GB / ~32M rows, so dtypes are kept small
and one source file is processed (and released) at a time.
"""
import gc
import sys
import time

import numpy as np
import pandas as pd

COLS = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol", "pkt_size", "timestamp"]
FLOW_COLS = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol"]

DTYPES = {
    "src_ip": "int64",
    "dst_ip": "int64",
    "src_port": "int32",
    "dst_port": "int32",
    "protocol": "int16",
    "pkt_size": "float32",
    "timestamp": "float64",
}

SIZE_BINS = [-np.inf, 64, 128, 256, 512, 768, 1024, 1280, 1518, 4096, 9001, np.inf]


def extract(path: str, source: str, label: int) -> pd.DataFrame:
    t0 = time.time()
    df = pd.read_csv(path, header=None, names=COLS, dtype=DTYPES)
    n_rows = len(df)

    df.sort_values(FLOW_COLS + ["timestamp"], inplace=True, kind="mergesort")
    df["iat"] = df.groupby(FLOW_COLS, sort=False)["timestamp"].diff()
    df["size_bin"] = pd.cut(df["pkt_size"], bins=SIZE_BINS)

    g = df.groupby(FLOW_COLS, sort=False)
    agg = g.agg(
        flow_pkt_count=("pkt_size", "count"),
        flow_byte_count=("pkt_size", "sum"),
        pkt_size_mean=("pkt_size", "mean"),
        pkt_size_std=("pkt_size", "std"),
        pkt_size_min=("pkt_size", "min"),
        pkt_size_max=("pkt_size", "max"),
        ts_min=("timestamp", "min"),
        ts_max=("timestamp", "max"),
        iat_mean=("iat", "mean"),
        iat_std=("iat", "std"),
        iat_min=("iat", "min"),
        iat_max=("iat", "max"),
    ).reset_index()

    agg["flow_duration"] = agg["ts_max"] - agg["ts_min"]
    agg.drop(columns=["ts_min", "ts_max"], inplace=True)
    for c in ["pkt_size_std", "iat_mean", "iat_std", "iat_min", "iat_max"]:
        agg[c] = agg[c].fillna(0.0)

    bin_counts = df.groupby(FLOW_COLS + ["size_bin"], sort=False, observed=True).size()
    bin_counts = bin_counts.reset_index(name="cnt")
    totals = bin_counts.groupby(FLOW_COLS, sort=False)["cnt"].transform("sum")
    p = bin_counts["cnt"] / totals
    bin_counts["ent_term"] = -p * np.log2(p)
    entropy = bin_counts.groupby(FLOW_COLS, sort=False)["ent_term"].sum().reset_index(
        name="pkt_size_entropy"
    )

    agg = agg.merge(entropy, on=FLOW_COLS, how="left")
    agg["pkt_size_entropy"] = agg["pkt_size_entropy"].fillna(0.0)

    agg["source_dataset"] = source
    agg["label"] = label

    n_flows = len(agg)
    elapsed = time.time() - t0
    print(f"[{source}] rows={n_rows:,} flows={n_flows:,} elapsed={elapsed:.1f}s", file=sys.stderr)

    del df, g, bin_counts, totals, p
    gc.collect()
    return agg


def main():
    jobs = [
        ("data/raw/unsw_60_sec_new.csv", "unsw", 1),
        ("data/raw/cic_60_sec_new.csv", "cic", 1),
        ("data/raw/caida_60_sec_new.csv", "caida", 0),
    ]
    out_path = "loop-engineering/data/processed/features.csv"
    frames = []
    for path, source, label in jobs:
        frames.append(extract(path, source, label))
        gc.collect()

    result = pd.concat(frames, ignore_index=True)
    result.to_csv(out_path, index=False)
    print(f"wrote {out_path} with {len(result):,} flows total", file=sys.stderr)


if __name__ == "__main__":
    main()
