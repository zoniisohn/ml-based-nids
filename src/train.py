"""
IDS 모델 학습 스크립트

data/processed/features.csv (flow-level 특징, 마지막 컬럼 label)를 읽어
Random Forest / XGBoost / SVM(선형 RBF, 서브샘플) 세 모델을 학습하고,
테스트셋 예측 결과와 학습된 모델을 저장한다.

재현성: random_state=42로 고정. 스크립트를 처음부터 끝까지 실행하면
동일한 결과가 재현되도록 노트북 순서 의존 없이 top-to-bottom으로 작성됨.

실행: python src/train.py
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

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC

import xgboost as xgb

# ----------------------------------------------------------------------------
# 경로 설정
# ----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_CSV = PROJECT_ROOT / "data" / "processed" / "features.csv"
MODELS_DIR = PROJECT_ROOT / "models"
WORKSPACE_DIR = PROJECT_ROOT / "_workspace"

MODELS_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42
TEST_SIZE = 0.2
# 저메모리(8GB, 여유 <1GB) 환경에서 전체 178만 행으로 RF/XGB를 학습하면 반복적으로 OOM kill이
# 발생함 (n_jobs=1, float32, gc.collect()까지 적용해도 재현됨) -> 학습에 쓰는 전체 데이터 자체를
# stratified subsample로 줄인다. 과제 수준 분류기 성능 검증에는 이 정도 규모로 충분하다.
SUBSAMPLE_SIZE = 400_000
SVM_SUBSAMPLE_SIZE = 20_000  # SVM(RBF)은 O(n^2)~O(n^3)이라 전체(178만 행) 학습이 비현실적 -> 학습셋에서 stratified subsample만 사용. 평가는 전체 test set에 대해 수행하여 모델 간 공정 비교.

# 식별자/누수 위험 컬럼은 학습 특징에서 제외:
#  - src_ip, dst_ip, src_port, dst_port: 특정 호스트에 과적합될 위험 (01_feature_engineer_summary.md 권고)
#  - source_dataset: CAIDA=0, CIC/UNSW=1 로 label과 1:1 대응되는 컬럼이라 그대로 쓰면 완전한 데이터 누수
FEATURE_COLS = [
    "protocol",
    "packet_count",
    "byte_count",
    "flow_duration",
    "pkt_size_mean",
    "pkt_size_min",
    "pkt_size_max",
    "pkt_size_std",
    "iat_mean",
    "iat_min",
    "iat_max",
    "iat_std",
    "pkt_size_entropy",
    "iat_entropy",
]
CATEGORICAL_COLS = ["protocol"]  # IP 프로토콜 번호는 순서 의미가 없는 범주형 -> one-hot
NUMERIC_COLS = [c for c in FEATURE_COLS if c not in CATEGORICAL_COLS]
LABEL_COL = "label"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> None:
    t0 = time.time()

    if not FEATURES_CSV.exists():
        raise FileNotFoundError(
            f"{FEATURES_CSV} 가 없습니다. flow-feature-engineer 단계를 먼저 실행해야 합니다."
        )

    log(f"Loading {FEATURES_CSV} ...")
    df = pd.read_csv(FEATURES_CSV)
    log(f"Loaded shape={df.shape}")

    class_counts = df[LABEL_COL].value_counts().sort_index()
    log(f"Class distribution (전체):\n{class_counts.to_string()}")

    # 저메모리 환경 대응: 전체 데이터를 stratified subsample로 축소 (아래 SUBSAMPLE_SIZE 주석 참고)
    if SUBSAMPLE_SIZE < len(df):
        df, _dropped = train_test_split(
            df, train_size=SUBSAMPLE_SIZE, stratify=df[LABEL_COL], random_state=RANDOM_STATE
        )
        del _dropped
        gc.collect()
        subsample_class_counts = df[LABEL_COL].value_counts().sort_index()
        log(f"Subsampled to {len(df):,} rows for memory safety. Class distribution (subsample):\n{subsample_class_counts.to_string()}")
    else:
        subsample_class_counts = class_counts

    # float32로 다운캐스트 -> 특징 행렬 메모리 절반, 저메모리 환경(8GB) 대응
    n_subsampled = len(df)
    X = df[FEATURE_COLS].copy()
    for c in NUMERIC_COLS:
        X[c] = X[c].astype("float32")
    y = df[LABEL_COL].astype(int).copy()
    del df
    gc.collect()

    # ------------------------------------------------------------------
    # Stratified train/test split
    # ------------------------------------------------------------------
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    log(f"Train shape={X_train.shape}, Test shape={X_test.shape}")
    log(f"Train class dist:\n{y_train.value_counts().sort_index().to_string()}")
    log(f"Test class dist:\n{y_test.value_counts().sort_index().to_string()}")

    # ------------------------------------------------------------------
    # 전처리: protocol -> one-hot, 나머지 수치형 -> StandardScaler
    # train에만 fit, test/subsample에는 transform만 적용 (데이터 누수 방지)
    # ------------------------------------------------------------------
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "protocol_ohe",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_COLS,
            ),
            ("scale", StandardScaler(), NUMERIC_COLS),
        ],
        sparse_threshold=0.0,
    )

    log("Fitting preprocessor on train set...")
    X_train_t = preprocessor.fit_transform(X_train)
    X_test_t = preprocessor.transform(X_test)
    log(f"Transformed train shape={X_train_t.shape}, test shape={X_test_t.shape}")

    joblib.dump(preprocessor, MODELS_DIR / "preprocessor.joblib")
    log(f"Saved preprocessor -> {MODELS_DIR / 'preprocessor.joblib'}")

    # class imbalance 비율 (benign:malicious ~ 6.8:1)
    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    scale_pos_weight = n_neg / n_pos
    log(f"scale_pos_weight (neg/pos) for XGBoost = {scale_pos_weight:.4f}")

    results = {}  # model_name -> dict(pred_label, pred_proba)

    # ------------------------------------------------------------------
    # 1) Random Forest (전체 train set, class_weight='balanced')
    # ------------------------------------------------------------------
    log("Training RandomForestClassifier ...")
    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=15,
        class_weight="balanced",
        n_jobs=1,  # 저메모리(8GB) 환경: 병렬 워커가 데이터를 복제해 OOM을 유발하므로 단일 프로세스로 제한
        random_state=RANDOM_STATE,
    )
    t_rf = time.time()
    rf.fit(X_train_t, y_train)
    log(f"RF trained in {time.time() - t_rf:.1f}s")
    rf_proba = rf.predict_proba(X_test_t)[:, 1]
    rf_pred = (rf_proba >= 0.5).astype(int)
    results["rf"] = {"pred": rf_pred, "proba": rf_proba}
    joblib.dump(rf, MODELS_DIR / "random_forest.joblib")
    log(f"Saved -> {MODELS_DIR / 'random_forest.joblib'}")
    del rf
    gc.collect()

    # ------------------------------------------------------------------
    # 2) XGBoost (전체 train set, scale_pos_weight로 불균형 보정)
    # ------------------------------------------------------------------
    log("Training XGBClassifier ...")
    xgb_clf = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        tree_method="hist",
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        n_jobs=2,  # 저메모리(8GB) 환경 대응: 전체 코어 병렬(n_jobs=-1) 대신 제한
        random_state=RANDOM_STATE,
    )
    t_xgb = time.time()
    xgb_clf.fit(X_train_t, y_train)
    log(f"XGBoost trained in {time.time() - t_xgb:.1f}s")
    xgb_proba = xgb_clf.predict_proba(X_test_t)[:, 1]
    xgb_pred = (xgb_proba >= 0.5).astype(int)
    results["xgb"] = {"pred": xgb_pred, "proba": xgb_proba}
    joblib.dump(xgb_clf, MODELS_DIR / "xgboost.joblib")
    log(f"Saved -> {MODELS_DIR / 'xgboost.joblib'}")
    del xgb_clf
    gc.collect()

    # ------------------------------------------------------------------
    # 3) SVM (RBF kernel, class_weight='balanced')
    #    전체 178만 행 학습은 SVC의 O(n^2)~O(n^3) 복잡도상 비현실적이므로
    #    train set에서 stratified subsample(SVM_SUBSAMPLE_SIZE)만 사용.
    #    평가는 다른 모델과 동일한 전체 test set에 대해 수행 -> 비교 유효.
    # ------------------------------------------------------------------
    log(f"Sampling {SVM_SUBSAMPLE_SIZE} rows (stratified) from train set for SVM ...")
    if SVM_SUBSAMPLE_SIZE < len(X_train_t):
        X_svm_train, _, y_svm_train, _ = train_test_split(
            X_train_t,
            y_train,
            train_size=SVM_SUBSAMPLE_SIZE,
            stratify=y_train,
            random_state=RANDOM_STATE,
        )
    else:
        X_svm_train, y_svm_train = X_train_t, y_train
    log(
        f"SVM train subsample shape={X_svm_train.shape}, "
        f"class dist={pd.Series(y_svm_train).value_counts().sort_index().to_dict()}"
    )

    log("Training SVC (RBF kernel) ...")
    svm_clf = SVC(
        kernel="rbf",
        C=1.0,
        class_weight="balanced",
        probability=True,
        random_state=RANDOM_STATE,
    )
    t_svm = time.time()
    svm_clf.fit(X_svm_train, y_svm_train)
    log(f"SVM trained in {time.time() - t_svm:.1f}s")
    svm_proba = svm_clf.predict_proba(X_test_t)[:, 1]
    svm_pred = (svm_proba >= 0.5).astype(int)
    results["svm"] = {"pred": svm_pred, "proba": svm_proba}
    joblib.dump(svm_clf, MODELS_DIR / "svm.joblib")
    log(f"Saved -> {MODELS_DIR / 'svm.joblib'}")
    n_svm_train = len(X_svm_train)
    del svm_clf, X_svm_train, y_svm_train
    gc.collect()

    # ------------------------------------------------------------------
    # 테스트셋 예측 결과 저장 (평가 단계 입력)
    # ------------------------------------------------------------------
    pred_df = pd.DataFrame(
        {
            "true_label": y_test.values,
            "rf_pred_label": results["rf"]["pred"],
            "rf_pred_proba": results["rf"]["proba"],
            "xgb_pred_label": results["xgb"]["pred"],
            "xgb_pred_proba": results["xgb"]["proba"],
            "svm_pred_label": results["svm"]["pred"],
            "svm_pred_proba": results["svm"]["proba"],
        },
        index=X_test.index,
    )
    out_csv = WORKSPACE_DIR / "02_trainer_test_predictions.csv"
    pred_df.to_csv(out_csv, index=False)
    log(f"Saved predictions -> {out_csv} (shape={pred_df.shape})")

    # ------------------------------------------------------------------
    # 요약 메타데이터 저장 (summary.md 작성에 활용)
    # ------------------------------------------------------------------
    meta = {
        "original_total_rows": int(class_counts.sum()),
        "subsampled_total_rows": int(n_subsampled),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "class_counts_original_full_dataset": class_counts.to_dict(),
        "class_counts_subsample": subsample_class_counts.to_dict(),
        "class_counts_train": y_train.value_counts().sort_index().to_dict(),
        "class_counts_test": y_test.value_counts().sort_index().to_dict(),
        "svm_subsample_size": int(n_svm_train),
        "scale_pos_weight_xgb": scale_pos_weight,
        "elapsed_sec": time.time() - t0,
    }
    with open(WORKSPACE_DIR / "02_trainer_run_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    log(f"Done. Total elapsed = {time.time() - t0:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL ERROR:")
        traceback.print_exc()
        sys.exit(1)
