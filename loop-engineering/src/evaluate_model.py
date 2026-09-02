"""Evaluate the two NIDS Random Forest models trained by train_model.py.

Loads each model plus its held-out test split (saved by train_model.py),
computes Accuracy/Precision/Recall/F1/ROC-AUC, and saves a confusion matrix
and ROC curve figure per model under loop-engineering/report/figures/.

The "cross_source" model's test set is 100% unsw (label==1, malicious) since
RALPH_PROMPT.md's cross-source check trains on caida+cic and tests on unsw
never seen during training -- so for that model, recall is the number that
matters (there are no negatives to compute a meaningful ROC curve against),
while the "standard" model's random stratified split has both classes and
supports the full metric set.
"""
import json
import sys

import joblib
import matplotlib

matplotlib.use("Agg")
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
)

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

FIG_DIR = "loop-engineering/report/figures"


def evaluate(name, model_path, test_csv_path):
    model = joblib.load(model_path)
    df = pd.read_csv(test_csv_path)
    X = df[FEATURES]
    y = df["label"]

    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)[:, 1]

    metrics = {
        "n_test": int(len(df)),
        "n_positive": int(y.sum()),
        "n_negative": int((y == 0).sum()),
        "accuracy": accuracy_score(y, y_pred),
        "recall": recall_score(y, y_pred, zero_division=0),
    }

    has_both_classes = y.nunique() > 1
    if has_both_classes:
        metrics["precision"] = precision_score(y, y_pred, zero_division=0)
        metrics["f1"] = f1_score(y, y_pred, zero_division=0)
        metrics["roc_auc"] = roc_auc_score(y, y_proba)
    else:
        metrics["precision"] = None
        metrics["f1"] = None
        metrics["roc_auc"] = None
        print(
            f"[{name}] test set has a single class (all label={y.iloc[0]}); "
            "precision/F1/ROC-AUC are undefined, reporting recall only.",
            file=sys.stderr,
        )

    cm = confusion_matrix(y, y_pred, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(4, 4))
    ConfusionMatrixDisplay(cm, display_labels=["benign", "malicious"]).plot(
        ax=ax, cmap="Blues", colorbar=False
    )
    ax.set_title(f"{name}: confusion matrix")
    fig.tight_layout()
    fig.savefig(f"{FIG_DIR}/{name}_confusion_matrix.png", dpi=150)
    plt.close(fig)

    if has_both_classes:
        fig, ax = plt.subplots(figsize=(4, 4))
        RocCurveDisplay.from_predictions(y, y_proba, ax=ax)
        ax.set_title(f"{name}: ROC curve")
        fig.tight_layout()
        fig.savefig(f"{FIG_DIR}/{name}_roc_curve.png", dpi=150)
        plt.close(fig)

    print(f"[{name}] {metrics}", file=sys.stderr)
    return metrics


def main():
    results = {
        "standard": evaluate(
            "standard",
            "loop-engineering/models/rf_standard_split.joblib",
            "loop-engineering/data/processed/test_standard.csv",
        ),
        "cross_source": evaluate(
            "cross_source",
            "loop-engineering/models/rf_cross_source.joblib",
            "loop-engineering/data/processed/test_cross_source.csv",
        ),
    }
    with open("loop-engineering/data/processed/eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("wrote loop-engineering/data/processed/eval_results.json", file=sys.stderr)


if __name__ == "__main__":
    main()
