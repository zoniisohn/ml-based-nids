---
name: nids-hw-orchestrator
description: "ML 기반 네트워크 침입 탐지 시스템(NIDS) 과제 전체 파이프라인(특징 추출 → 모델 학습 → 평가 → 리포트 작성)을 조율한다. '인트루전 탐지 과제 시작', 'IDS 과제 실행', '데이터 넣었으니 파이프라인 돌려줘', '네트워크 보안 과제 진행' 시 사용. 후속 작업(다시 실행, 특징/모델/평가/리포트만 재실행, 결과 개선, 데이터 업데이트 후 재실행 등)에도 반드시 이 스킬을 사용."
---

# NIDS HW Orchestrator

ML 기반 네트워크 침입 탐지 시스템 과제([Network Security] HW ML-Based Network Intrusion Detection System)의 4단계 파이프라인을 조율하는 오케스트레이터.

## 실행 모드: 서브 에이전트 (파이프라인)

이 과제는 각 단계가 이전 단계의 산출물에 강하게 의존하는 순차 파이프라인이다 (`references/agent-design-patterns.md`의 "파이프라인 패턴" 기준: 순차 의존이 강해 팀 모드의 이점이 제한적). 따라서 `Agent` 도구로 각 단계를 순서대로 호출하고, 파일 기반으로 산출물을 전달한다. 팀원 간 실시간 토론이 필요한 상충 데이터나 병렬 탐색이 없으므로 서브 에이전트 모드가 적합하다.

## 에이전트 구성

| 순서 | 에이전트 | subagent_type | 역할 | 스킬 | 주요 출력 |
|------|---------|---------------|------|------|----------|
| 1 | flow-feature-engineer | flow-feature-engineer | 패킷→flow 변환, 특징 추출 | flow-feature-extraction | `data/processed/features.csv` |
| 2 | ids-model-trainer | ids-model-trainer | 분류 모델 학습 | ids-model-training | `models/*.joblib`, 예측 결과 |
| 3 | ids-model-evaluator | ids-model-evaluator | 다중 지표 평가·시각화 | ids-model-evaluation | `report/figures/*`, 평가 결과 |
| 4 | hw-report-writer | hw-report-writer | README/결과 문서 갱신 + 트러블슈팅 이력 기록 (git 관리, PDF 없음) | hw-report-writing | `report/results.md`, 갱신된 `README.md`, 갱신된 `docs/harness-postmortem.md` |

모든 `Agent` 호출에 `model: "sonnet"`를 명시한다.

## 워크플로우

### Phase 0: 컨텍스트 확인 (후속 작업 지원)

1. `_workspace/` 디렉토리와 그 안의 `0N_*` 파일들의 존재 여부를 확인한다.
2. 판단:
   - **`_workspace/` 미존재** → 초기 실행. Phase 1로 진행.
   - **사용자가 특정 단계만 지목** ("모델만 다시 학습해줘", "리포트만 다시 써줘" 등) → 부분 재실행. 해당 단계의 에이전트만 호출하되, 그 단계가 의존하는 이전 산출물(`_workspace/0(N-1)_*`)이 존재하는지 먼저 확인한다. 없으면 사용자에게 알리고 선행 단계부터 실행할지 확인한다.
   - **`_workspace/`가 있고 사용자가 새 데이터/처음부터 재실행을 요청** → 기존 `_workspace/`를 `_workspace_{YYYYMMDD_HHMMSS}/`로 이동한 뒤 Phase 1부터 전체 재실행.
3. 부분 재실행 시, 해당 에이전트 프롬프트에 이전 산출물 경로와 "무엇을 개선/수정해야 하는지"(사용자 피드백)를 포함한다.

### Phase 1: 준비

1. `data/raw/`에 `caida_60_sec_new.csv`, `cic_60_sec_new.csv`, `unsw_60_sec_new.csv`가 있는지 확인한다. 하나라도 없으면 사용자에게 파일 배치를 요청하고 중단한다 (임의 데이터로 진행하지 않는다).
2. `_workspace/`가 없으면 생성한다.

### Phase 2: 순차 파이프라인 실행

각 단계는 이전 단계 완료 후 호출한다 (병렬 호출 금지 — 강한 순차 의존).

Phase 2 진행 중 오케스트레이터가 직접 개입해야 했던 사건(중복 프로세스 종료, OOM/재시도, 코드 버그 수정, 예상 밖 결과 발견 등)이 있으면, 각 사건을 증상/진단/해결 한두 문장으로 메모해둔다 — 4번 단계에서 hw-report-writer에게 그대로 전달하기 위함이다 (`docs/harness-postmortem.md` 참고).

1. `Agent(subagent_type: "flow-feature-engineer", model: "sonnet", prompt: "data/raw/의 3개 CSV로 flow 특징을 추출하라. 산출물: data/processed/features.csv, _workspace/01_feature_engineer_summary.md")`
2. 1번 완료 확인(`_workspace/01_feature_engineer_summary.md` 존재) 후:
   `Agent(subagent_type: "ids-model-trainer", model: "sonnet", prompt: "data/processed/features.csv로 분류 모델을 학습하라. 산출물: models/*.joblib, _workspace/02_trainer_test_predictions.csv, _workspace/02_trainer_summary.md")`
3. 2번 완료 확인 후:
   `Agent(subagent_type: "ids-model-evaluator", model: "sonnet", prompt: "_workspace/02_trainer_test_predictions.csv로 모델을 평가하라. 산출물: report/figures/*.png, _workspace/03_evaluator_results.md")`
4. 3번 완료 확인 후:
   `Agent(subagent_type: "hw-report-writer", model: "sonnet", prompt: "_workspace/01~03 산출물을 종합해 report/results.md를 작성하고, 저장소 README.md의 Progress log/Results comparison 표를 이번 실행(Harness) 결과로 갱신하라. PDF는 만들지 않는다. 이번 실행에서 다음과 같은 특이사항/트러블슈팅이 있었다: {Phase 2에서 메모해둔 사건 목록, 없으면 이 문장 자체를 생략} — 이를 바탕으로 docs/harness-postmortem.md에 사건 기록을 append하라.")`

### Phase 3: 결과 취합 및 보고

1. `_workspace/04_report_writer_summary.md`를 읽어 README.md/`report/results.md`/`docs/harness-postmortem.md`가 어떻게 갱신되었는지 확인한다.
2. 사용자에게 요약 보고: 추출된 flow 수, 학습된 모델, 주요 지표(Accuracy/F1/ROC-AUC), 갱신된 문서 위치(`README.md`, `report/results.md`, 트러블슈팅이 있었다면 `docs/harness-postmortem.md`).
3. 변경 사항을 git에 커밋/푸시할지 사용자에게 확인한다 (자동으로 커밋·푸시하지 않는다 — 항상 사용자 확인 후 진행).
4. 결과에서 개선할 부분이 있는지 사용자에게 물어본다 (강요하지 않되 기회를 제공).

### Phase 4: 정리

- `_workspace/`는 삭제하지 않는다 (감사 추적 및 부분 재실행용).
- 새 실행으로 보관 이동한 `_workspace_{timestamp}/`가 여러 개 쌓이면, 사용자에게 정리 여부를 물어본다 (자동 삭제 금지).

## 데이터 흐름

```
data/raw/*.csv
    │  [flow-feature-engineer]
    ▼
data/processed/features.csv ── _workspace/01_feature_engineer_summary.md
    │  [ids-model-trainer]
    ▼
models/*.joblib, _workspace/02_trainer_test_predictions.csv ── _workspace/02_trainer_summary.md
    │  [ids-model-evaluator]
    ▼
report/figures/*.png ── _workspace/03_evaluator_results.md
    │  [hw-report-writer]
    ▼
report/results.md, README.md (Progress log / Results comparison 갱신), docs/harness-postmortem.md (트러블슈팅이 있었던 경우)
```

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| `data/raw/` 원본 데이터 누락 | Phase 1에서 중단, 사용자에게 파일 배치 요청 |
| 특정 단계 에이전트 실패 | 1회 재시도. 재실패 시 사용자에게 에러 내용 보고, 다음 단계로 강제 진행하지 않음(파이프라인이므로 뒷 단계가 입력을 못 받음) |
| 모델 라이브러리(xgboost 등) 미설치 | 해당 모델만 건너뛰고 나머지 모델로 진행, 요약에 명시 |

## 테스트 시나리오

### 정상 흐름
1. 사용자가 `data/raw/`에 3개 CSV를 배치하고 "IDS 과제 파이프라인 실행해줘" 요청
2. Phase 0에서 초기 실행 판정 (`_workspace/` 없음)
3. Phase 1에서 원본 데이터 확인
4. Phase 2에서 4개 에이전트를 순서대로 호출, 각 단계 산출물 확인 후 다음 단계 진행
5. Phase 3에서 최종 지표와 갱신된 `README.md`/`report/results.md` 경로를 사용자에게 보고, git 커밋 여부 확인
6. 예상 결과: `data/processed/features.csv`, `models/*.joblib`, `report/figures/*.png`, `report/results.md`, 갱신된 `README.md` 생성

### 에러 흐름
1. 사용자가 "모델 평가 결과가 이상해, ROC-AUC만 다시 확인해줘" 요청 (후속 작업)
2. Phase 0에서 `_workspace/02_trainer_test_predictions.csv` 존재 확인 → 부분 재실행 판정
3. `ids-model-evaluator`만 재호출, 사용자 피드백("ROC-AUC 확인")을 프롬프트에 포함
4. 재실행 결과를 `_workspace/03_evaluator_results.md`에 갱신
5. `hw-report-writer`는 이번 요청 범위에 없으므로 호출하지 않되, `README.md`/`report/results.md`가 이미 존재하면 최신 평가 결과와 불일치할 수 있음을 사용자에게 알림
