---
name: ids-model-evaluation
description: "학습된 분류 모델을 Accuracy/Precision/Recall/F1/ROC-AUC로 평가하고 Confusion Matrix, ROC Curve를 시각화한다. 'IDS 모델 평가', '분류 성능 평가', 'ROC curve', 'confusion matrix' 관련 작업 시 사용."
---

# IDS Model Evaluation

분류 모델의 test set 예측 결과로 다중 지표 평가와 시각화를 생성하는 절차.

## 지표 계산

```python
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    confusion_matrix, roc_curve
)

metrics = {
    "accuracy": accuracy_score(y_true, y_pred),
    "precision": precision_score(y_true, y_pred),
    "recall": recall_score(y_true, y_pred),
    "f1": f1_score(y_true, y_pred),
    "roc_auc": roc_auc_score(y_true, y_proba),  # y_proba는 확률, y_pred가 아님
}
```

`roc_auc_score`는 반드시 확률(`y_proba`)을 넣는다 — 예측 클래스(`y_pred`)를 넣으면 잘못된 값이 나온다.

## 시각화

```python
import matplotlib.pyplot as plt
from sklearn.metrics import ConfusionMatrixDisplay, RocCurveDisplay

ConfusionMatrixDisplay.from_predictions(y_true, y_pred)
plt.savefig(f"report/figures/confusion_matrix_{model_name}.png", bbox_inches="tight")
plt.close()

RocCurveDisplay.from_predictions(y_true, y_proba)
plt.savefig(f"report/figures/roc_curve_{model_name}.png", bbox_inches="tight")
plt.close()
```

## IDS 맥락에서의 지표 해석 관점

리포트의 "discussion and analysis"에 쓸 해석 관점:

- **Recall이 낮다** → False Negative가 많다 → 실제 공격 트래픽을 정상으로 오분류 → IDS의 핵심 실패 모드(공격을 놓침). 보안 맥락에서는 Precision보다 Recall을 우선하는 경우가 많다는 점을 논의할 가치가 있다.
- **Precision이 낮다** → False Positive가 많다 → 정상 트래픽을 공격으로 오분류 → 운영 부담(alert fatigue) 증가.
- **Accuracy만 높고 F1/Recall이 낮다** → 클래스 불균형 신호. benign 데이터(CAIDA)와 malicious 데이터(CIC+UNSW)의 크기 차이가 크면 accuracy가 과대평가될 수 있다는 점을 반드시 짚는다.
- **ROC-AUC**는 임계값에 무관한 전반적 분리력을 보여준다. Precision/Recall이 특정 임계값(기본 0.5)에서의 성능이라는 점과 대비해 설명하면 분석 깊이가 생긴다.
- 여러 모델을 비교했다면, 단순히 "이 모델이 더 높다"가 아니라 어떤 특징(모델 구조, 데이터 가정)이 그 차이를 만들었는지 한 단계 더 설명한다.

## 흔한 실수

- confusion matrix 라벨 순서(0=benign, 1=malicious)를 명시하지 않아 해석 시 혼동
- ROC-AUC에 확률 대신 이진 예측값 사용
- 다중 모델 비교 시 그림 파일명이 겹쳐 덮어써짐 — 파일명에 반드시 모델명 포함
