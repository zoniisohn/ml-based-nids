"""
feature_leakage_diagnosis.py에서 "환경(소스) 식별에 강하게 기여"한다고 판정된 feature
(protocol, byte_count, pkt_size_max, packet_count, pkt_size_mean)를 제거한 뒤,
cross_source_validation.py와 동일한 train/test 분할로 다시 학습해 UNSW recall이
개선되는지 확인한다. 나머지 로직(분할, 모델 하이퍼파라미터, 메모리 제약 대응)은
cross_source_validation.py와 동일하게 유지해 두 결과가 "feature 세트 차이"만으로
비교되도록 한다.
"""

import gc
import sys
import time
import json
import traceback
from pathlib import Path

import pandas as pd
import joblib

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

import xgboost as xgb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_CSV = PROJECT_ROOT / "data" / "processed" / "features.csv"
WORKSPACE_DIR = PROJECT_ROOT / "_workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42

TRAIN_CAIDA_N = 200_000
TEST_CAIDA_N = 50_000
TRAIN_CIC_N = 150_000

# feature_leakage_diagnosis.py 결과에서 threshold>=0.05로 flag된 feature 제거
# (protocol, byte_count, pkt_size_max, packet_count, pkt_size_mean)
FEATURE_COLS = [
    "flow_duration", "pkt_size_min", "pkt_size_std",
    "iat_mean", "iat_min", "iat_max", "iat_std",
    "pkt_size_entropy", "iat_entropy",
]
LABEL_COL = "label"
SOURCE_COL = "source_dataset"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if n >= len(df):
        return df
    return df.sample(n=n, random_state=seed)


def main() -> None:
    t0 = time.time()
    log(f"Loading {FEATURES_CSV} ...")
    df = pd.read_csv(FEATURES_CSV)
    log(f"Loaded shape={df.shape}")

    caida = df[df[SOURCE_COL] == "caida"]
    cic = df[df[SOURCE_COL] == "cic"]
    unsw = df[df[SOURCE_COL] == "unsw"]
    log(f"caida={len(caida):,} cic={len(cic):,} unsw={len(unsw):,}")
    del df
    gc.collect()

    caida_train = sample(caida, TRAIN_CAIDA_N, RANDOM_STATE)
    caida_remaining = caida.drop(caida_train.index)
    caida_test = sample(caida_remaining, TEST_CAIDA_N, RANDOM_STATE + 1)
    del caida, caida_remaining
    gc.collect()

    cic_train = sample(cic, TRAIN_CIC_N, RANDOM_STATE)
    del cic
    gc.collect()

    train_df = pd.concat([caida_train, cic_train], ignore_index=True)
    test_df = pd.concat([caida_test, unsw], ignore_index=True)
    del caida_train, cic_train, caida_test
    gc.collect()

    log(f"Train: {len(train_df):,} rows | Test: {len(test_df):,} rows "
        f"(mitigated feature set, {len(FEATURE_COLS)} numeric features, protocol dropped)")

    for c in FEATURE_COLS:
        train_df[c] = train_df[c].astype("float32")
        test_df[c] = test_df[c].astype("float32")

    X_train = train_df[FEATURE_COLS]
    y_train = train_df[LABEL_COL].astype(int)
    X_test = test_df[FEATURE_COLS]
    y_test = test_df[LABEL_COL].astype(int)
    test_source = test_df[SOURCE_COL].to_numpy()

    scaler = StandardScaler()
    X_train_t = scaler.fit_transform(X_train)
    X_test_t = scaler.transform(X_test)

    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    scale_pos_weight = n_neg / n_pos
    log(f"scale_pos_weight = {scale_pos_weight:.4f}")

    results = {}

    log("Training RandomForestClassifier (mitigated features) ...")
    rf = RandomForestClassifier(
        n_estimators=100, max_depth=15, class_weight="balanced", n_jobs=1, random_state=RANDOM_STATE,
    )
    rf.fit(X_train_t, y_train)
    rf_proba = rf.predict_proba(X_test_t)[:, 1]
    rf_pred = (rf_proba >= 0.5).astype(int)
    results["rf"] = {"pred": rf_pred, "proba": rf_proba}
    joblib.dump(rf, PROJECT_ROOT / "models" / "cross_source_mitigated_random_forest.joblib")
    log("RF done.")
    del rf
    gc.collect()

    log("Training XGBClassifier (mitigated features) ...")
    xgb_clf = xgb.XGBClassifier(
        n_estimators=100, max_depth=6, learning_rate=0.1, tree_method="hist",
        scale_pos_weight=scale_pos_weight, eval_metric="logloss", n_jobs=2, random_state=RANDOM_STATE,
    )
    xgb_clf.fit(X_train_t, y_train)
    xgb_proba = xgb_clf.predict_proba(X_test_t)[:, 1]
    xgb_pred = (xgb_proba >= 0.5).astype(int)
    results["xgb"] = {"pred": xgb_pred, "proba": xgb_proba}
    joblib.dump(xgb_clf, PROJECT_ROOT / "models" / "cross_source_mitigated_xgboost.joblib")
    log("XGB done.")
    del xgb_clf
    gc.collect()

    report = {}
    for name, r in results.items():
        pred, proba = r["pred"], r["proba"]
        overall = {
            "accuracy": accuracy_score(y_test, pred),
            "precision": precision_score(y_test, pred),
            "recall": recall_score(y_test, pred),
            "f1": f1_score(y_test, pred),
            "roc_auc": roc_auc_score(y_test, proba),
        }
        tn, fp, fn, tp = confusion_matrix(y_test, pred).ravel()
        overall["confusion_matrix"] = {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}

        unsw_mask = test_source == "unsw"
        caida_mask = test_source == "caida"
        unsw_recall = recall_score(y_test[unsw_mask], pred[unsw_mask]) if unsw_mask.sum() else None
        caida_specificity = accuracy_score(y_test[caida_mask], pred[caida_mask]) if caida_mask.sum() else None

        report[name] = {
            "overall": overall,
            "recall_on_unseen_malicious_source_UNSW": unsw_recall,
            "n_unsw_test": int(unsw_mask.sum()),
            "accuracy_on_holdout_benign_CAIDA": caida_specificity,
            "n_caida_test": int(caida_mask.sum()),
        }
        log(f"{name}: overall acc={overall['accuracy']:.4f} f1={overall['f1']:.4f} auc={overall['roc_auc']:.4f} | "
            f"recall on UNSEEN malicious source (UNSW, n={int(unsw_mask.sum())})={unsw_recall:.4f} | "
            f"accuracy on held-out benign (CAIDA, n={int(caida_mask.sum())})={caida_specificity:.4f}")

    report["_meta"] = {
        "feature_cols": FEATURE_COLS,
        "dropped_leaky_features": ["protocol", "byte_count", "pkt_size_max", "packet_count", "pkt_size_mean"],
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "elapsed_sec": time.time() - t0,
    }

    out_path = WORKSPACE_DIR / "03d_cross_source_validation_mitigated.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"Saved -> {out_path}")
    log(f"Done. Total elapsed = {time.time() - t0:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL ERROR:")
        traceback.print_exc()
        sys.exit(1)
