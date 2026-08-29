---
name: hw-report-writing
description: "Feature extraction/모델 학습/평가 산출물을 종합해 report/results.md와 저장소 README.md를 업데이트한다. PDF 대신 git으로 버전 관리되는 문서를 유지한다. '리포트 작성', '결과 문서 갱신', 'README 업데이트', '제출물 정리' 관련 작업 시 사용."
---

# HW Report Writing

파이프라인 산출물을 `report/results.md`와 저장소 `README.md`에 반영하는 절차. PDF 변환은 하지 않는다 — git으로 버전 관리되는 Markdown 문서가 최종 산출물이다.

## 결과 문서 구조 (`report/results.md`)

```markdown
# ML-Based Network Intrusion Detection System — Results

## 1. Feature Extraction
(raw packet → 5-tuple flow 구성 → feature 계산 과정 설명)

## 2. Feature Selection Rationale
(왜 이 feature들을 선택했는지 — 각 feature가 침입 탐지에 유의미한 이유)

## 3. Model Training and Evaluation Summary
(모델 종류, 학습 설정, train/test 크기, 지표 표)

## 4. Discussion and Analysis
(성능 해석, 한계, 개선 방향)
```

## README.md 갱신 절차

1. "Progress log" 표에 새 행을 append한다: `| 날짜 | Harness 또는 Loop | 이번 실행 요약 |`. 기존 행은 지우지 않는다.
2. "Results comparison" 표에서 이번에 실행한 방식 열의 TBD를 실제 수치(소요 시간, Accuracy/F1/ROC-AUC, 재실행 용이성, 사람 개입 지점)로 교체한다.
3. 반대쪽 방식 열에 아직 값이 없으면 TBD로 남겨둔다 — 임의로 채우지 않는다.
4. 그 외 섹션(방식 비교 설명, 디렉토리 구조 등)은 수정하지 않는다.

## 원칙

- 이전 단계 요약(`_workspace/0*_*.md`)은 작업 로그 톤이므로, `results.md`는 문서 톤(서술형, 3인칭 또는 격식체)으로 다시 쓴다.
- 수치는 상위 결과 파일 값을 그대로 인용한다 — 재계산하거나 임의 추정하지 않는다.
- 표절 방지 조항이 있는 과제이므로 문장은 새로 작성한다(요약 파일을 그대로 복사하지 않는다).
- 시각화(figures)는 반드시 `results.md` 본문에 삽입하고, 각 그림에 대해 최소 1문장 이상 해석을 붙인다 — 그림만 던지지 않는다.
- `git add`/`commit`/`push`는 이 스킬의 범위가 아니다 — 파일 갱신까지만 담당한다.
