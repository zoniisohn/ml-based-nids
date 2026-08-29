## 하네스: ML 기반 네트워크 침입 탐지 시스템 (NIDS HW)

**목표:** 패킷 트래픽 데이터에서 flow 특징을 추출하고, 분류 모델을 학습·평가하여 과제 제출용 리포트(PDF)까지 생성한다.

**트리거:** 이 과제(특징 추출/모델 학습/평가/리포트) 관련 작업 요청 시 `nids-hw-orchestrator` 스킬을 사용하라. 단순 질문은 직접 응답 가능.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-08-29 | 초기 구성 (4개 에이전트 파이프라인 + 오케스트레이터) | 전체 | 과제 지시사항(HW ML-Based NIDS) 기반 하네스 구축 |
| 2026-08-29 | hw-report-writer 역할 변경: PDF 리포트 작성 → README.md/report/results.md 갱신 (PDF 제거) | hw-report-writer 에이전트, hw-report-writing 스킬, nids-hw-orchestrator 스킬 | Harness Engineering vs Loop Engineering 비교 실험을 위해 산출물을 git으로 버전 관리되는 살아있는 문서로 유지하기로 결정 |
