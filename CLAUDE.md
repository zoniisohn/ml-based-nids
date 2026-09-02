## 하네스: ML 기반 네트워크 침입 탐지 시스템 (NIDS HW)

**목표:** 패킷 트래픽 데이터에서 flow 특징을 추출하고, 분류 모델을 학습·평가하여 README.md/report/results.md를 갱신하고, 트러블슈팅 이력을 docs/harness-postmortem.md에 기록한다.

**트리거 (Harness Engineering 전용):** 이 과제(특징 추출/모델 학습/평가/리포트) 관련 작업 요청 시 `nids-hw-orchestrator` 스킬을 사용하라. 단, 이 트리거는 `.claude/agents`·`.claude/skills`의 고정 파이프라인(Harness Engineering) 쪽에만 해당한다. **Loop Engineering** 작업 요청(예: "loop 실행해줘", "ralph loop 돌려줘")은 이 스킬을 쓰지 말고 `loop-engineering/RALPH_PROMPT.md` + `ralph-loop` 플러그인(`/ralph-loop`)으로 진행한다 — 별도의 격리된 작업 공간(`loop-engineering/`)에서, Harness 쪽 코드(`src/`, `.claude/agents`, `.claude/skills`, `docs/harness-postmortem.md`)를 참고하지 않고 독립적으로 수행하는 것이 이 비교 실험의 핵심 전제다. 단순 질문은 직접 응답 가능.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-08-29 | 초기 구성 (4개 에이전트 파이프라인 + 오케스트레이터) | 전체 | 과제 지시사항(HW ML-Based NIDS) 기반 하네스 구축 |
| 2026-08-29 | hw-report-writer 역할 변경: PDF 리포트 작성 → README.md/report/results.md 갱신 (PDF 제거) | hw-report-writer 에이전트, hw-report-writing 스킬, nids-hw-orchestrator 스킬 | Harness Engineering vs Loop Engineering 비교 실험을 위해 산출물을 git으로 버전 관리되는 살아있는 문서로 유지하기로 결정 |
| 2026-08-29 | hw-report-writer에 docs/harness-postmortem.md 갱신 역할 추가 (오케스트레이터가 Phase 2 트러블슈팅 이력을 전달하면 append) | hw-report-writer 에이전트, hw-report-writing 스킬, nids-hw-orchestrator 스킬 | 첫 실행에서 겪은 문제(중복 프로세스, OOM, 코드 버그, 데이터 누수 발견 등)를 수동으로 문서화했는데, 이후 실행에서도 같은 문서에 누적 기록되도록 파이프라인 규칙으로 정례화 |
| 2026-09-02 | Loop Engineering 뼈대 추가: `loop-engineering/` 격리 작업공간, `loop-engineering/RALPH_PROMPT.md`, `ralph-loop` 플러그인 채택 | 신규 `loop-engineering/` 디렉터리, `.gitignore`, CLAUDE.md, README.md | Harness Engineering 완주(데이터 누수 발견 및 완화 시도 실패까지 포함) 후 비교 실험의 반대 축을 구현. 새 세션이 Harness의 트러블슈팅 지식으로 오염되지 않도록 별도 작업공간 분리, 단 "label-source confound가 존재한다"는 사실 자체는 informed 조건으로 프롬프트에 명시 |
