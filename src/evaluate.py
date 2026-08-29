"""
IDS 모델 평가 스크립트

입력: _workspace/02_trainer_test_predictions.csv
      (true_label, {model}_pred_label, {model}_pred_proba 컬럼 반복)
출력: report/figures/confusion_matrix_{model}.png
      report/figures/roc_curve_{model}.png
      report/figures/roc_curve_comparison.png
      _workspace/03_evaluator_results.md (본 스크립트가 아니라 별도로 작성됨)

메모리 제약(8GB) 대응: pandas로 CSV 1회만 로드, 모델별 파생 컬럼만 슬라이싱해서 사용.
matplotlib Agg 백엔드로 가벼운 PNG만 생성 (GUI 렌더링 없음).
"""

import matplotlib
matplotlib.use("Agg")

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    RocCurveDisplay,
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

ROOT = Path(__file__).resolve().parents[1]
PRED_CSV = ROOT / "_workspace" / "02_trainer_test_predictions.csv"
FIG_DIR = ROOT / "report" / "figures"
RESULT_JSON = ROOT / "_workspace" / "03_evaluator_metrics.json"

MODELS = [
    ("rf", "Random Forest"),
    ("xgb", "XGBoost"),
    ("svm", "SVM (RBF)"),
]


def main():
    if not PRED_CSV.exists():
        print(
            f"ERROR: 입력 파일이 없습니다: {PRED_CSV}\n"
            "ids-model-trainer가 먼저 실행되어 예측 결과를 생성해야 합니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.read_csv(PRED_CSV)
    y_true = df["true_label"].values

    FIG_DIR.mkdir(parents=True, exist_ok=True)

    all_metrics = {}
    roc_fig, roc_ax = plt.subplots(figsize=(6, 5))

    for key, display_name in MODELS:
        pred_col = f"{key}_pred_label"
        proba_col = f"{key}_pred_proba"

        if pred_col not in df.columns:
            print(f"WARNING: {pred_col} 컬럼이 없어 {display_name}을(를) 건너뜁니다.", file=sys.stderr)
            continue

        y_pred = df[pred_col].values

        metrics = {
            "accuracy": accuracy_score(y_true, y_pred),
            "precision": precision_score(y_true, y_pred, zero_division=0),
            "recall": recall_score(y_true, y_pred, zero_division=0),
            "f1": f1_score(y_true, y_pred, zero_division=0),
        }

        has_proba = proba_col in df.columns
        if has_proba:
            y_proba = df[proba_col].values
            metrics["roc_auc"] = roc_auc_score(y_true, y_proba)
        else:
            metrics["roc_auc"] = None
            print(f"WARNING: {proba_col} 컬럼이 없어 {display_name}의 ROC-AUC는 N/A 처리합니다.", file=sys.stderr)

        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()
        metrics["confusion_matrix"] = {
            "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "labels": "0=benign, 1=malicious",
        }

        all_metrics[key] = {"display_name": display_name, **metrics}

        # --- Confusion Matrix 시각화 ---
        fig_cm, ax_cm = plt.subplots(figsize=(5, 5))
        ConfusionMatrixDisplay(cm, display_labels=["benign(0)", "malicious(1)"]).plot(
            ax=ax_cm, cmap="Blues", colorbar=False, values_format="d"
        )
        ax_cm.set_title(f"Confusion Matrix — {display_name}")
        fig_cm.tight_layout()
        fig_cm.savefig(FIG_DIR / f"confusion_matrix_{key}.png", bbox_inches="tight", dpi=120)
        plt.close(fig_cm)

        # --- 개별 ROC Curve 시각화 ---
        if has_proba:
            fig_roc, ax_roc = plt.subplots(figsize=(5, 5))
            RocCurveDisplay.from_predictions(y_true, y_proba, ax=ax_roc, name=display_name)
            ax_roc.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1, label="Chance")
            ax_roc.set_title(f"ROC Curve — {display_name}")
            ax_roc.legend(loc="lower right")
            fig_roc.tight_layout()
            fig_roc.savefig(FIG_DIR / f"roc_curve_{key}.png", bbox_inches="tight", dpi=120)
            plt.close(fig_roc)

            # 비교용 ROC curve에도 추가
            fpr, tpr, _ = roc_curve(y_true, y_proba)
            roc_ax.plot(fpr, tpr, label=f"{display_name} (AUC={metrics['roc_auc']:.4f})")

        print(f"[{display_name}] " + ", ".join(f"{k}={v:.4f}" for k, v in metrics.items() if isinstance(v, float)))

    # --- 3개 모델 비교 ROC curve ---
    roc_ax.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1, label="Chance")
    roc_ax.set_xlabel("False Positive Rate")
    roc_ax.set_ylabel("True Positive Rate")
    roc_ax.set_title("ROC Curve Comparison — RF vs XGBoost vs SVM")
    roc_ax.legend(loc="lower right")
    roc_fig.tight_layout()
    roc_fig.savefig(FIG_DIR / "roc_curve_comparison.png", bbox_inches="tight", dpi=120)
    plt.close(roc_fig)

    with open(RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Metrics saved to {RESULT_JSON}")
    print(f"Figures saved to {FIG_DIR}")


if __name__ == "__main__":
    main()
