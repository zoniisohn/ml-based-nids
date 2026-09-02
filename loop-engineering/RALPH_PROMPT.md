# Loop Engineering — NIDS 과제 (반복 실행 프롬프트)

너는 지금 "Loop Engineering" 방식으로 이 과제를 수행하고 있다. 고정된 서브 에이전트
역할 분담(Harness Engineering) 없이, 매 iteration마다 스스로 현재 상태를 파악하고
다음에 할 일을 판단해서 진행한다. 이 프롬프트는 매 iteration 동일하게 재주입되며,
너는 이전 iteration에서 무엇을 했는지 기억하지 못한다 — 오직 파일과 git 상태만으로
진행 상황을 파악해야 한다. 매 iteration 시작 시 `loop-engineering/` 안에 이미 뭐가
있는지, `loop-engineering/_loop_log.md`에 지금까지 뭘 했다고 적혀있는지부터 확인하라.

## 작업 범위 (반드시 지킬 것)
- 모든 산출물은 `loop-engineering/` 아래에만 생성한다.
- 원본 데이터는 `data/raw/{caida_60_sec_new.csv, cic_60_sec_new.csv, unsw_60_sec_new.csv}`를
  읽기 전용으로 사용한다 (컬럼: src_ip,dst_ip,src_port,dst_port,protocol,pkt_size,timestamp).
- **`src/`, `.claude/agents/`, `.claude/skills/`, `docs/harness-postmortem.md`, README.md의
  "Key finding" 섹션은 읽지도 참고하지도 복사하지도 않는다.** 같은 과제를 다른 방식
  (Harness Engineering)으로 이미 풀어본 결과물이라 그대로 베끼면 비교 실험 의미가 없다.
- README.md의 "Progress log"/"Results comparison" 중 기존 Harness 행/셀은 수정하지 않는다
  — Loop 쪽 행/열만 채운다.

## 과제 (Harness Engineering과 동일한 목표)
1. 3개 CSV에서 5-tuple 기준 flow를 구성하고 flow-level 특징(패킷 수, 바이트 수, duration,
   packet size 통계, IAT 통계, entropy 등)을 추출해 `loop-engineering/data/processed/features.csv`로
   저장한다. 라벨: caida=benign(0), cic/unsw=malicious(1).
2. 이 특징으로 분류 모델(최소 1개 이상, 예: Random Forest/XGBoost)을 학습한다.
   클래스 불균형을 처리한다.
3. Accuracy/Precision/Recall/F1/ROC-AUC로 평가하고 confusion matrix/ROC curve를 시각화한다.
4. **알려진 함정(처음부터 반영할 것)**: 이 데이터셋은 label과 source_dataset이 100%
   confound되어 있다(benign=전부 caida, malicious=전부 cic+unsw). 단순 random
   train/test split 지표는 "공격 탐지 능력"이 아니라 "캡처 환경 구분 능력"을 측정하는
   것일 수 있다. 표준 평가와 별개로 **cross-source 검증**(예: caida+cic로 학습, 학습 때
   전혀 안 본 unsw 전체로 테스트, recall 확인)을 반드시 포함해 진짜 일반화 성능을 보고하라.
5. 결과를 `loop-engineering/report/results.md`(특징 추출 / 특징 선택 근거 / 학습·평가 요약 /
   논의, 4개 섹션)로 문서화한다.
6. 매 iteration 끝에 `loop-engineering/_loop_log.md`에 이번에 한 일을 한 줄 append한다
   (이전 기억이 없으므로 이게 유일한 감사 추적이다).
7. 전체가 끝나면 README.md의 "Progress log"에 Loop 행을 추가하고 "Results comparison"
   표의 Loop Engineering 열을 채운다(TBD를 실제 수치로).

## 환경 참고
이 머신은 RAM이 넉넉하지 않다(8GB). 병렬 학습(`n_jobs=-1`)이 메모리 부족으로 예외 없이
프로세스를 죽일 수 있다. 같은 지점에서 반복 실패하면 병렬도를 낮추거나 데이터를
subsample하는 등 스스로 판단해서 대응하라.

## 종료 조건
1~7이 모두 끝나고 검증됐다고 판단될 때만 마지막 줄에 정확히 다음을 출력하라:
`<promise>LOOP_NIDS_DONE</promise>`
아직 안 끝났다면 이 문자열을 출력하지 말고 이번 iteration에서 할 수 있는 다음 작업을 하라.
