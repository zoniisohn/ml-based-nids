# ML-Based NIDS — Harness Engineering vs Loop Engineering

This repository serves two purposes at once:

1. **Goal**: extract flow-level features from packet traffic data, then train and evaluate a classification model to build a network intrusion detection system.
2. **Meta-experiment**: carry out the same assignment using two different AI collaboration styles — **Harness Engineering** and **Loop Engineering** — and compare their process and results.

This README itself is kept as a living document, continuously updated with the progress and results of both approaches.

## Key finding: the headline metrics are misleading (data leakage confirmed)

The Harness Engineering run of the pipeline produced RF/XGBoost models with ~99.99% accuracy/F1 and ROC-AUC ≈ 1.0. **These numbers do not reflect real intrusion-detection ability.** In this dataset, `label` is perfectly confounded with `source_dataset` — benign is CAIDA and 100% of malicious is CIC+UNSW — so a classifier can hit near-perfect scores by learning to recognize which capture environment a flow came from, without learning anything about attack behavior.

We confirmed this with a cross-source generalization test: train only on CAIDA(benign)+CIC(malicious), then evaluate on UNSW (malicious) traffic the model never saw during training.

| Model | Recall on unseen malicious source (UNSW, n=122,295) | Accuracy on held-out benign (CAIDA, n=50,000) |
|---|---:|---:|
| Random Forest | **0.0000** (0 of 122,295 attacks detected) | 0.9999 |
| XGBoost | **0.0000** (0 of 122,295 attacks detected) | 0.9998 |

Zero recall on a completely unseen attack source, while still near-perfect on held-out benign traffic, is the signature of a model that learned "is this CIC" rather than "is this an attack."

**Mitigation attempt (failed, but confirms the limit is structural, not fixable by feature selection).** We tested whether dropping the most source-identifying features would fix it. A diagnostic classifier trained only on malicious flows (CIC vs. UNSW — same label, different capture source) achieved **100% accuracy** telling the two sources apart, meaning the confound isn't confined to a few features. Dropping the top 5 flagged features (`protocol`, `byte_count`, `pkt_size_max`, `packet_count`, `pkt_size_mean`) and retraining on the remaining 9 left UNSW recall at **0.0000 — unchanged**. This rules out "bad feature selection" as the cause: the leakage is baked into the dataset's flow-level statistics across capture environments, and only new data (with label and source decoupled) can fix it, not further feature engineering.

Full writeup, diagnosis steps, and general troubleshooting principles this surfaced: **[docs/harness-postmortem.md](docs/harness-postmortem.md)**.

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
report/results.md, README.md (Progress log / Results comparison updated)
```

| Step | Agent | Role |
|------|-------|------|
| 1 | `flow-feature-engineer` | Convert packets into 5-tuple flows, extract flow-level features (size/duration/IAT/entropy, etc.) |
| 2 | `ids-model-trainer` | Train classification models (Random Forest/SVM/XGBoost), handle class imbalance |
| 3 | `ids-model-evaluator` | Evaluate Accuracy/Precision/Recall/F1/ROC-AUC, visualize confusion matrix and ROC curve |
| 4 | `hw-report-writer` | Update `report/results.md` and this README (no PDF — git-tracked Markdown is the deliverable) |

- Pros: clear separation of responsibilities, per-step outputs can be verified, easy to re-run a single step in isolation.
- Cons: upfront design cost, less flexible — if the shape of the task changes, the harness itself needs to be redesigned.

### Loop Engineering

No fixed division of labor between agents. Implemented with the `ralph-loop` Claude Code plugin's Stop-hook mechanism: a single task prompt ([`loop-engineering/RALPH_PROMPT.md`](loop-engineering/RALPH_PROMPT.md)) is re-injected verbatim every time the session tries to end, with **no summary of prior iterations carried over** — the model must reconstruct progress purely from what it finds on disk (`loop-engineering/_loop_log.md` and whatever files already exist) and decide the next step itself, until it emits an exact completion string or a max-iteration cap is hit.

To keep the comparison fair, this runs in its own isolated workspace (`loop-engineering/`), sharing only the read-only raw CSVs in `data/raw/` with the Harness run — it does not read or copy the Harness implementation (`src/`, `.claude/agents/`, `.claude/skills/`, `docs/harness-postmortem.md`). One deliberate asymmetry: the Loop prompt is *informed* that `label` is confounded with `source_dataset` and requires a cross-source check from the start, rather than re-discovering that blind — so this run tests process/engineering style under a known constraint, not independent bug-discovery.

- Pros: low upfront design cost, flexible when direction needs to change mid-task.
- Cons: harder to keep consistency across iterations, progress tracking is looser than with a harness, no persistent memory between iterations means every iteration re-pays the cost of re-orienting from files alone.

## Directory structure

```
.claude/            # Harness Engineering: agent and skill definitions
data/raw/           # Raw packet CSVs (not tracked in git; shared read-only input for both approaches)
data/processed/     # Harness Engineering: extracted flow features (not tracked in git)
models/             # Harness Engineering: trained models (not tracked in git)
report/             # Harness Engineering: evaluation outputs (not tracked in git)
src/                # Harness Engineering: pipeline scripts
loop-engineering/   # Loop Engineering: isolated workspace (src/, data/processed/, models/, report/) + RALPH_PROMPT.md
```

## Progress log

| Date | Approach | Notes |
|------|----------|-------|
| 2026-08-29 | Harness | Repository initialized; 4 subagents + orchestrator skill set up. Not yet run (raw data not placed in `data/raw/`). |
| 2026-08-29 | Harness | Full pipeline run on raw CAIDA/CIC/UNSW CSVs (2,226,498 flows extracted). Hit and resolved: duplicate background processes in feature extraction, repeated OOM kills in model training (8GB RAM machine), two `UnboundLocalError` bugs introduced by a memory-safety patch, and several false "crashed" signals from the orchestrator's own monitoring. RF/XGBoost/SVM trained on a 400k-row stratified subsample. Initial evaluation showed ~99.99% accuracy/F1, which a follow-up cross-source validation showed to be data leakage (see Key Finding above) rather than real detection ability. Full incident writeup: [docs/harness-postmortem.md](docs/harness-postmortem.md). |
| 2026-09-02 | Harness | Attempted to mitigate the data leakage by identifying and dropping the features most predictive of capture source (via an auxiliary classifier on the label-constant malicious subset) and retraining. UNSW recall stayed at 0.0000 — confirmed the leakage is structural to the dataset, not fixable by feature selection. See Key Finding above and [docs/harness-postmortem.md](docs/harness-postmortem.md) (사건 6). |

## Results comparison

| Metric | Harness Engineering | Loop Engineering |
|--------|---------------------|-------------------|
| Time to complete | ~1.5 hours end-to-end, of which roughly half was troubleshooting (duplicate processes, OOM retries, two code bugs) rather than productive pipeline time | TBD |
| Accuracy / F1 / ROC-AUC | RF/XGBoost: 0.9999 / 0.9995 / 1.0000 on the original test split — **but invalidated**: recall on an unseen malicious source (UNSW) is 0.0000 (see Key Finding). SVM: 0.9797 / 0.9196 / 0.9889, same caveat applies. | TBD |
| Ease of re-running / partial fixes | Easy to target precisely — file-based checkpoints (`_workspace/0N_*`) let the orchestrator re-run exactly the failing stage (e.g. only `ids-model-trainer`) without repeating earlier stages | TBD |
| Points requiring human intervention | Killing duplicate background processes (x2); deciding how to fix OOM (reduce parallelism vs. move to Colab vs. subsample — user chose subsample); diagnosing and fixing 2 `UnboundLocalError` bugs in a subagent-written script; requesting the cross-source validation that surfaced the leakage (the pipeline's own evaluator step would not have caught this on its own) | TBD |
