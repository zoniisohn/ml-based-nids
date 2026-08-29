# ML-Based NIDS — Harness Engineering vs Loop Engineering

This repository serves two purposes at once:

1. **Assignment goal**: extract flow-level features from packet traffic data, then train and evaluate a classification model to build a network intrusion detection system.
2. **Meta-experiment**: carry out the same assignment using two different AI collaboration styles — **Harness Engineering** and **Loop Engineering** — and compare their process and results.

Instead of producing a separate PDF report for submission, this README itself is kept as a living document, continuously updated with the progress and results of both approaches.

## What's being compared

### Harness Engineering

A fixed pipeline with roles defined up front. Built from `.claude/agents` and `.claude/skills`, where `nids-hw-orchestrator` calls four specialized subagents in a set order.

```
data/raw/*.csv
    │  [flow-feature-engineer]
    ▼
data/processed/features.csv
    │  [ids-model-trainer]
    ▼
models/*.joblib
    │  [ids-model-evaluator]
    ▼
report/figures/*.png
    │  [hw-report-writer]
    ▼
report/final_report.pdf
```

| Step | Agent | Role |
|------|-------|------|
| 1 | `flow-feature-engineer` | Convert packets into 5-tuple flows, extract flow-level features (size/duration/IAT/entropy, etc.) |
| 2 | `ids-model-trainer` | Train classification models (Random Forest/SVM/XGBoost), handle class imbalance |
| 3 | `ids-model-evaluator` | Evaluate Accuracy/Precision/Recall/F1/ROC-AUC, visualize confusion matrix and ROC curve |
| 4 | `hw-report-writer` | Synthesize outputs into a final report |

- Pros: clear separation of responsibilities, per-step outputs can be verified, easy to re-run a single step in isolation.
- Cons: upfront design cost, less flexible — if the shape of the task changes, the harness itself needs to be redesigned.

### Loop Engineering

No fixed division of labor between agents. Instead, `/loop` repeats the same task, and on each iteration the model decides for itself what to do next, incrementally improving the result.

- Pros: low upfront design cost, flexible when direction needs to change mid-task.
- Cons: harder to keep consistency across iterations, progress tracking is looser than with a harness.

## Directory structure

```
.claude/            # Harness Engineering: agent and skill definitions
data/raw/           # Raw packet CSVs (not tracked in git)
data/processed/     # Extracted flow features (not tracked in git)
models/             # Trained models (not tracked in git)
report/             # Evaluation outputs (not tracked in git)
src/                # Pipeline scripts
```

## Progress log

| Date | Approach | Notes |
|------|----------|-------|
| 2026-08-29 | Harness | Repository initialized; 4 subagents + orchestrator skill set up. Not yet run (raw data not placed in `data/raw/`). |

## Results comparison

Neither approach has been run yet, so there's no data to compare. The table below will be filled in once each pipeline has been executed.

| Metric | Harness Engineering | Loop Engineering |
|--------|---------------------|-------------------|
| Time to complete | TBD | TBD |
| Accuracy / F1 / ROC-AUC | TBD | TBD |
| Ease of re-running / partial fixes | TBD | TBD |
| Points requiring human intervention | TBD | TBD |
