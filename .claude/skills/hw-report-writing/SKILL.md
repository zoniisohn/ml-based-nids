---
name: hw-report-writing
description: "Feature extraction/모델 학습/평가 산출물을 종합해 report/results.md와 저장소 README.md를 업데이트하고, 트러블슈팅 이력을 docs/harness-postmortem.md에 기록한다. PDF 대신 git으로 버전 관리되는 문서를 유지한다. '리포트 작성', '결과 문서 갱신', 'README 업데이트', '제출물 정리', '포스트모템' 관련 작업 시 사용."
---

# HW Report Writing

파이프라인 산출물을 `report/results.md`와 저장소 `README.md`에 반영하고, 실행 중 겪은 문제를 `docs/harness-postmortem.md`에 기록하는 절차. PDF 변환은 하지 않는다 — git으로 버전 관리되는 Markdown 문서가 최종 산출물이다.

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
5. 이번 실행에서 중요한 트러블슈팅/발견(아래 harness-postmortem 절 참고)이 있었다면, README 상단 "Key finding" 또는 그에 준하는 위치에 한두 문단으로 요약하고 `docs/harness-postmortem.md`로 링크한다.

## docs/harness-postmortem.md 갱신 절차

1. 오케스트레이터가 프롬프트로 "이번 실행에서 발생한 특이사항/트러블슈팅 이력"을 전달했을 때만 이 파일을 갱신한다. 전달된 게 없으면(무사히 통과한 실행) 손대지 않는다 — 사건을 지어내지 않는다.
2. 파일이 없으면 새로 만들고, 있으면 append한다: 기존 "사건 기록"/"일반 원칙"/"하네스 엔지니어링의 특징적 문제" 절의 내용을 지우거나 재작성하지 않는다.
3. 새 사건은 증상(symptom) → 진단(diagnosis) → 해결(resolution) 순서로 기존 사건들과 같은 형식의 절로 추가한다.
4. 그 사건에서 일반화되는 원칙이 있으면 "일반 원칙" 절에, 파이프라인 구조 자체에 내재한 문제라면 "하네스 엔지니어링의 특징적 문제" 절에 추가한다 — 기존 항목과 취지가 겹치면 새로 추가하지 않는다.

## 원칙

- 이전 단계 요약(`_workspace/0*_*.md`)은 작업 로그 톤이므로, `results.md`는 문서 톤(서술형, 3인칭 또는 격식체)으로 다시 쓴다.
- 수치는 상위 결과 파일 값을 그대로 인용한다 — 재계산하거나 임의 추정하지 않는다.
- 표절 방지 조항이 있는 과제이므로 문장은 새로 작성한다(요약 파일을 그대로 복사하지 않는다).
- 시각화(figures)는 반드시 `results.md` 본문에 삽입하고, 각 그림에 대해 최소 1문장 이상 해석을 붙인다 — 그림만 던지지 않는다.
- `docs/harness-postmortem.md`는 append-only로 다룬다 — 기존 내용을 재작성하거나 삭제하지 않는다.
- `git add`/`commit`/`push`는 이 스킬의 범위가 아니다 — 파일 갱신까지만 담당한다.
