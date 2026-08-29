"""
Cross-source (leave-one-malicious-source-out) validation.

Purpose: 01_feature_engineer_summary.md 라벨링 방식상 benign=CAIDA, malicious=CIC+UNSW로
라벨이 데이터 소스와 100% 겹친다. 그래서 02/03단계에서 나온 RF/XGBoost의 99.99% 성능이
"공격 시그니처를 학습한 것"인지 "캡처 환경/소스를 구분한 것"인지 구별이 안 된다.

이를 검증하기 위해: CAIDA(benign) + CIC(malicious)로만 학습하고, 학습 때 전혀 보지 못한
malicious 소스인 UNSW 전체를 테스트에 포함시킨다. 만약 모델이 CIC의 소스 특유 아티팩트가
아니라 진짜 "공격 트래픽의 일반적 패턴"을 학습했다면 UNSW에 대해서도 높은 recall이 나와야
하고, 그렇지 않다면(재현율이 뚝 떨어지면) source-based leakage라는 강한 증거가 된다.

메모리 제약(8GB) 대응: 02_trainer 단계에서 검증된 것과 같은 규모(학습 ~35만 행)로 제한하고
n_jobs를 제한한다. SVM은 이번 검증의 핵심 질문(RF/XGBoost의 leakage 의심)과 무관하고
이미 저성능이 확인됐으므로 생략한다.
"""

import gc
import sys
import time
import json
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

import xgboost as xgb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_CSV = PROJECT_ROOT / "data" / "processed" / "features.csv"
WORKSPACE_DIR = PROJECT_ROOT / "_workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42

TRAIN_CAIDA_N = 200_000   # benign, 학습용
TEST_CAIDA_N = 50_000     # benign, held-out 테스트용 (학습에 안 쓴 별도 샘플)
TRAIN_CIC_N = 150_000     # malicious, 학습용 (전체 161,947 중 대부분)
# UNSW(122,295, malicious)는 전량 테스트 전용 -- 학습 때 전혀 보지 않는 malicious 소스

FEATURE_COLS = [
    "protocol", "packet_count", "byte_count", "flow_duration",
    "pkt_size_mean", "pkt_size_min", "pkt_size_max", "pkt_size_std",
    "iat_mean", "iat_min", "iat_max", "iat_std",
    "pkt_size_entropy", "iat_entropy",
]
CATEGORICAL_COLS = ["protocol"]
NUMERIC_COLS = [c for c in FEATURE_COLS if c not in CATEGORICAL_COLS]
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

    # non-overlapping CAIDA train/test samples
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

    log(f"Train: {len(train_df):,} rows (caida benign={TRAIN_CAIDA_N:,}, cic malicious={len(train_df) - TRAIN_CAIDA_N:,})")
    log(f"Test:  {len(test_df):,} rows (caida benign holdout={TEST_CAIDA_N:,}, UNSW malicious [UNSEEN SOURCE]={len(unsw):,})")

    for c in NUMERIC_COLS:
        train_df[c] = train_df[c].astype("float32")
        test_df[c] = test_df[c].astype("float32")

    X_train = train_df[FEATURE_COLS]
    y_train = train_df[LABEL_COL].astype(int)
    X_test = test_df[FEATURE_COLS]
    y_test = test_df[LABEL_COL].astype(int)
    test_source = test_df[SOURCE_COL].to_numpy()

    preprocessor = ColumnTransformer(
        transformers=[
            ("protocol_ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_COLS),
            ("scale", StandardScaler(), NUMERIC_COLS),
        ],
        sparse_threshold=0.0,
    )
    log("Fitting preprocessor on train set...")
    X_train_t = preprocessor.fit_transform(X_train)
    X_test_t = preprocessor.transform(X_test)

    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    scale_pos_weight = n_neg / n_pos
    log(f"scale_pos_weight = {scale_pos_weight:.4f}")

    results = {}

    log("Training RandomForestClassifier (cross-source) ...")
    rf = RandomForestClassifier(
        n_estimators=100, max_depth=15, class_weight="balanced", n_jobs=1, random_state=RANDOM_STATE,
    )
    rf.fit(X_train_t, y_train)
    rf_proba = rf.predict_proba(X_test_t)[:, 1]
    rf_pred = (rf_proba >= 0.5).astype(int)
    results["rf"] = {"pred": rf_pred, "proba": rf_proba}
    joblib.dump(rf, PROJECT_ROOT / "models" / "cross_source_random_forest.joblib")
    log("RF done.")
    del rf
    gc.collect()

    log("Training XGBClassifier (cross-source) ...")
    xgb_clf = xgb.XGBClassifier(
        n_estimators=100, max_depth=6, learning_rate=0.1, tree_method="hist",
        scale_pos_weight=scale_pos_weight, eval_metric="logloss", n_jobs=2, random_state=RANDOM_STATE,
    )
    xgb_clf.fit(X_train_t, y_train)
    xgb_proba = xgb_clf.predict_proba(X_test_t)[:, 1]
    xgb_pred = (xgb_proba >= 0.5).astype(int)
    results["xgb"] = {"pred": xgb_pred, "proba": xgb_proba}
    joblib.dump(xgb_clf, PROJECT_ROOT / "models" / "cross_source_xgboost.joblib")
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

        # recall broken down by source -- the key diagnostic
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
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "train_caida_benign": TRAIN_CAIDA_N,
        "train_cic_malicious": TRAIN_CIC_N,
        "test_caida_benign_holdout": TEST_CAIDA_N,
        "test_unsw_malicious_fully_unseen_source": int(len(unsw)),
        "elapsed_sec": time.time() - t0,
    }

    out_path = WORKSPACE_DIR / "03b_cross_source_validation.json"
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
