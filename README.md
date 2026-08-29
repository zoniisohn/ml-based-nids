# ML-Based NIDS

ML 기반 네트워크 침입 탐지 시스템(Network Intrusion Detection System) 과제용 Claude Code 하네스입니다. 패킷 트래픽 데이터에서 flow 특징을 추출하고, 분류 모델을 학습·평가한 뒤 제출용 리포트(PDF)까지 생성하는 4단계 파이프라인을 자동화합니다.

## 파이프라인

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

| 단계 | 에이전트 | 역할 | 주요 산출물 |
|------|---------|------|------------|
| 1 | `flow-feature-engineer` | 패킷 → 5-tuple flow 변환, flow-level 특징 추출 (Size/Duration/IAT/Entropy 등) | `data/processed/features.csv` |
| 2 | `ids-model-trainer` | 분류 모델 학습 (Random Forest/SVM/XGBoost), 클래스 불균형 처리 | `models/*.joblib` |
| 3 | `ids-model-evaluator` | Accuracy/Precision/Recall/F1/ROC-AUC 평가, Confusion Matrix·ROC Curve 시각화 | `report/figures/*.png` |
| 4 | `hw-report-writer` | 산출물 종합, 최종 리포트 작성 및 PDF 변환 | `report/final_report.pdf` |

## 사용법

1. `data/raw/`에 원본 패킷 CSV(`caida_60_sec_new.csv`, `cic_60_sec_new.csv`, `unsw_60_sec_new.csv`)를 배치합니다.
2. Claude Code에서 `nids-hw-orchestrator` 스킬이 요청 의도에 따라 자동으로 트리거되며, 4단계 파이프라인을 순차 실행합니다.
3. 특정 단계만 다시 실행하거나 결과 개선을 요청하는 후속 작업도 동일한 오케스트레이터가 처리합니다.

## 디렉토리 구조

```
.claude/            # 에이전트·스킬 정의
data/raw/           # 원본 패킷 CSV (git 미포함)
data/processed/     # 추출된 flow 특징 (git 미포함)
models/             # 학습된 모델 (git 미포함)
report/             # 평가 결과 및 최종 리포트 (git 미포함)
src/                # 파이프라인 스크립트
```
