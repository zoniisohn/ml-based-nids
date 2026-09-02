"""
환경(캡처 소스) 아티팩트를 학습하는 feature를 진단한다.

핵심 아이디어: CIC와 UNSW는 label이 둘 다 malicious(=1)로 동일하다. 그런데도 이 두
소스를 구분하는 신호가 feature에 강하게 남아있다면, 그 feature는 "공격 행위"가 아니라
"어느 캡처 환경에서 왔는가"를 반영하는 아티팩트일 가능성이 높다 (label이 상수이므로
소스 구분 신호에 라벨 정보가 전혀 섞여 있지 않은 깨끗한 진단이 된다).

방법: malicious 서브셋(CIC+UNSW)만 사용해 "이 flow가 UNSW인가?"를 예측하는 RF를 학습하고
feature importance를 본다. importance가 높은 feature일수록 환경 아티팩트를 담고 있다고
간주해 완화(제거) 대상으로 표시한다.
"""

import gc
import json
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_CSV = PROJECT_ROOT / "data" / "processed" / "features.csv"
WORKSPACE_DIR = PROJECT_ROOT / "_workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_STATE = 42

FEATURE_COLS = [
    "protocol", "packet_count", "byte_count", "flow_duration",
    "pkt_size_mean", "pkt_size_min", "pkt_size_max", "pkt_size_std",
    "iat_mean", "iat_min", "iat_max", "iat_std",
    "pkt_size_entropy", "iat_entropy",
]
CATEGORICAL_COLS = ["protocol"]
NUMERIC_COLS = [c for c in FEATURE_COLS if c not in CATEGORICAL_COLS]
SOURCE_COL = "source_dataset"
LABEL_COL = "label"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> None:
    t0 = time.time()
    log(f"Loading {FEATURES_CSV} ...")
    df = pd.read_csv(FEATURES_CSV)
    malicious = df[df[SOURCE_COL].isin(["cic", "unsw"])].copy()
    log(f"malicious subset (cic+unsw) = {len(malicious):,} rows "
        f"(cic={int((malicious[SOURCE_COL]=='cic').sum()):,}, unsw={int((malicious[SOURCE_COL]=='unsw').sum()):,})")
    assert malicious[LABEL_COL].nunique() == 1, "label must be constant within malicious subset by construction"
    del df
    gc.collect()

    for c in NUMERIC_COLS:
        malicious[c] = malicious[c].astype("float32")

    X = malicious[FEATURE_COLS]
    y_is_unsw = (malicious[SOURCE_COL] == "unsw").astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_is_unsw, test_size=0.25, stratify=y_is_unsw, random_state=RANDOM_STATE
    )
    del malicious
    gc.collect()

    preprocessor = ColumnTransformer(
        transformers=[
            ("protocol_ohe", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_COLS),
            ("scale", StandardScaler(), NUMERIC_COLS),
        ],
        sparse_threshold=0.0,
    )
    X_train_t = preprocessor.fit_transform(X_train)
    X_test_t = preprocessor.transform(X_test)

    log("Training RF to distinguish CIC vs UNSW within the malicious-only subset ...")
    clf = RandomForestClassifier(
        n_estimators=100, max_depth=12, class_weight="balanced", n_jobs=1, random_state=RANDOM_STATE,
    )
    clf.fit(X_train_t, y_train)
    proba = clf.predict_proba(X_test_t)[:, 1]
    pred = (proba >= 0.5).astype(int)
    acc = accuracy_score(y_test, pred)
    auc = roc_auc_score(y_test, proba)
    log(f"CIC-vs-UNSW discriminability: accuracy={acc:.4f} roc_auc={auc:.4f} "
        f"(this should be near chance/~0.5 if features carry no source-identity signal within malicious flows)")

    # feature importances aligned back to original (pre-one-hot) numeric feature names;
    # protocol is one-hot'd so we report its total importance as a single bucket.
    ohe = preprocessor.named_transformers_["protocol_ohe"]
    ohe_names = list(ohe.get_feature_names_out(CATEGORICAL_COLS))
    all_names = ohe_names + NUMERIC_COLS
    importances = dict(zip(all_names, clf.feature_importances_.tolist()))

    protocol_importance = sum(v for k, v in importances.items() if k in ohe_names)
    numeric_importance = {k: v for k, v in importances.items() if k not in ohe_names}
    ranked = sorted(numeric_importance.items(), key=lambda kv: kv[1], reverse=True)
    ranked_full = [("protocol", protocol_importance)] + ranked
    ranked_full.sort(key=lambda kv: kv[1], reverse=True)

    log("Feature importance for source-identity (CIC vs UNSW), descending:")
    for name, imp in ranked_full:
        log(f"  {name:20s} {imp:.4f}")

    # mitigation rule: drop any feature whose importance for predicting SOURCE
    # (within the label-constant malicious subset) is >= 0.05 -- i.e. features
    # that are informative about capture environment rather than attack behavior.
    LEAKY_THRESHOLD = 0.05
    leaky_features = [name for name, imp in ranked_full if imp >= LEAKY_THRESHOLD]
    mitigated_feature_cols = [c for c in FEATURE_COLS if c not in leaky_features]

    log(f"Flagged as environment-leaky (importance >= {LEAKY_THRESHOLD}): {leaky_features}")
    log(f"Mitigated feature set ({len(mitigated_feature_cols)}/{len(FEATURE_COLS)} kept): {mitigated_feature_cols}")

    report = {
        "cic_vs_unsw_discriminability": {"accuracy": acc, "roc_auc": auc},
        "feature_importance_for_source_identity": dict(ranked_full),
        "leaky_threshold": LEAKY_THRESHOLD,
        "leaky_features": leaky_features,
        "mitigated_feature_cols": mitigated_feature_cols,
        "elapsed_sec": time.time() - t0,
    }
    out_path = WORKSPACE_DIR / "03c_feature_leakage_diagnosis.json"
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
