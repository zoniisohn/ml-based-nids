---
name: ids-model-training
description: "flow-level 특징 테이블로 Random Forest/SVM/XGBoost 등 분류 모델을 학습한다. 'IDS 모델 학습', '분류기 학습', 'train/test 분할', '클래스 불균형' 관련 작업 시 사용."
---

# IDS Model Training

flow-level 특징(`features.csv`)으로 정상/악성 이진 분류 모델을 학습하는 절차.

## 표준 파이프라인

```python
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
import joblib

df = pd.read_csv("data/processed/features.csv")
X = df.drop(columns=["label"])
y = df["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42
)

model = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=42)
model.fit(X_train, y_train)

joblib.dump(model, "models/random_forest.joblib")
```

`stratify=y`는 필수다 — flow 라벨 비율이 CAIDA(benign) vs CIC+UNSW(malicious) 데이터셋 크기 차이로 불균형할 수 있고, 무작위 분할 시 test set의 클래스 비율이 왜곡될 수 있다.

## 여러 모델 비교 시

RF/SVM/XGBoost를 각각 학습하고 동일한 test set에 대해 예측 확률까지 저장한다. SVM은 `probability=True`를 명시하지 않으면 `predict_proba`가 동작하지 않으므로 ROC-AUC 계산을 위해 반드시 설정한다.

```python
from sklearn.svm import SVC
svm = SVC(probability=True, class_weight="balanced", random_state=42)
```

XGBoost 사용 시:
```python
from xgboost import XGBClassifier
xgb = XGBClassifier(eval_metric="logloss", random_state=42)
```

## 예측 결과 저장 형식

평가 단계가 바로 쓸 수 있도록 다음 컬럼을 가진 CSV로 저장한다:

```
y_true, y_pred_{model1}, y_proba_{model1}, y_pred_{model2}, y_proba_{model2}, ...
```

`y_proba`는 양성 클래스(malicious=1)에 대한 확률이어야 한다 (`predict_proba(X_test)[:, 1]`).

## 흔한 실수

- SVM에서 `probability=True` 누락 → 평가 단계에서 ROC-AUC 계산 불가
- feature 스케일이 서로 크게 다른데(예: byte 수 vs entropy) SVM 학습 시 스케일링 없이 사용 — SVM은 스케일에 민감하므로 `StandardScaler`를 train에 fit, test에 transform으로 적용 (RF/XGBoost는 스케일링 불필요)
- test set에도 fit을 적용하는 데이터 누수
- 클래스 불균형을 무시하고 `class_weight` 미설정 — accuracy는 높아 보여도 소수 클래스 recall이 낮아질 수 있다
