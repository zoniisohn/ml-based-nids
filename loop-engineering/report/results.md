# Loop Engineering — NIDS 결과 보고서

## 1. 특징 추출

원본 패킷 CSV 3종(`data/raw/{caida,cic,unsw}_60_sec_new.csv`, 헤더 없음, 컬럼:
`src_ip,dst_ip,src_port,dst_port,protocol,pkt_size,timestamp`)을 5-tuple
(`src_ip,dst_ip,src_port,dst_port,protocol`, 방향성 유지) 기준으로 그룹핑해
flow-level 특징을 만들었다 (`loop-engineering/src/extract_features.py`).

- 라벨: caida = benign(0), cic/unsw = malicious(1)
- flow당 계산한 특징: `flow_pkt_count`, `flow_byte_count`, `flow_duration`,
  packet size 통계(`pkt_size_mean/std/min/max`), IAT(inter-arrival time)
  통계(`iat_mean/std/min/max`, flow 내부 timestamp diff 기반),
  `pkt_size_entropy`(고정 bin Shannon entropy)
- 메모리 절약을 위해 dtype을 작게 고정(int64/int32/int16/float32/float64)하고
  pandas groupby 벡터화 연산으로 처리 (8GB RAM 환경 제약, RALPH_PROMPT.md 참고)

처리 결과 (`data/processed/_extract_log.txt`):

| source | 원본 패킷 행 수 | flow 수 | 처리 시간 |
|---|---:|---:|---:|
| unsw | 171,183 | 122,295 | 0.7s |
| cic | 11,392,183 | 161,947 | 27.4s |
| caida | 31,562,458 | 1,942,256 | 351.5s |
| **합계** | — | **2,226,498** | — |

라벨 분포: benign(caida) 1,942,256 / malicious(cic+unsw) 284,242. NaN 없음.

## 2. 특징 선택 근거

`loop-engineering/src/train_model.py`에서 학습에 사용한 특징:
`protocol`, `flow_pkt_count`, `flow_byte_count`, `pkt_size_mean/std/min/max`,
`iat_mean/std/min/max`, `flow_duration`, `pkt_size_entropy` — 총 13개.

**`src_ip`/`dst_ip`/`src_port`/`dst_port`는 의도적으로 제외했다.** 이 데이터셋은
캡처 환경(source_dataset)마다 네트워크 대역이 달라서, raw IP/포트를 그대로 넣으면
모델이 "공격 여부"가 아니라 "어느 캡처 환경에서 왔는가"를 거의 완벽하게 맞히는
지름길(label과 source_dataset의 100% confound, RALPH_PROMPT.md 4번 항목)을 학습해
버린다. 이는 실제 트래픽 행동 특징이 아니라 데이터 수집 방식의 artifact이므로
제거했다. `protocol`은 카디널리티가 작고 행동적 의미가 있어 유지했다.

**benign(caida) 클래스 언더샘플링.** caida(benign) 1,942,256행은 malicious 전체
284,242행의 약 6.8배로 불균형이 크고, 이 머신(8GB RAM, 다른 앱과 공유)에서
전체 데이터를 그대로 RandomForest에 넣는 최초 시도가 시스템 메모리 압박으로
반복 실패했다(자세한 원인/조치는 `_loop_log.md` iter 8~9 참고). 이에 caida를
malicious 대비 3배로 캡핑해 언더샘플링했다:
- standard용: caida 1,942,256 → 852,818행 (p≈0.439, 기준 malicious_total=284,242)
- cross_source용: caida 1,942,256 → 486,243행 (p≈0.250, 기준 cic=161,947)

`random_state=42`로 재현 가능하며, 잔여 불균형은 `class_weight="balanced"`로
보정한다. 이 언더샘플링은 절대적인 flow 수를 줄일 뿐 클래스 간 상대적 구성은
유지하므로 아래 결과 해석에 실질적 영향을 주지 않는다(특히 cross_source recall=0
결과는 표본 크기가 아니라 분포 자체의 문제임 — 4번 논의 참고).

## 3. 학습·평가 요약

모델: RandomForestClassifier(n_estimators=100, max_depth=15,
class_weight="balanced", n_jobs=1 — 8GB RAM 환경에서 반복 실패 후 `n_jobs=2→1`,
`n_estimators=200→100`, `max_depth=20→15`로 축소, random_state=42)

두 가지 split으로 학습/평가:

1. **standard**: 언더샘플링된 caida + cic + unsw (총 1,137,060 flow)를 80/20
   stratified random split
2. **cross_source**: 언더샘플링된 caida + cic로 학습 (648,190 flow), **학습 중
   전혀 보지 않은 unsw 전체**(122,295 flow)를 테스트셋으로 사용

평가 결과 (`loop-engineering/src/evaluate_model.py`,
`data/processed/eval_results.json`):

| split | n_test | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|---:|
| standard (random 80/20) | 227,412 | 0.99987 | 0.99965 | 0.99982 | 0.99974 | 0.99999677 |
| cross_source (unsw 전체 held-out) | 122,295 | 0.0 | — | **0.0** | — | — |

cross_source 테스트셋(unsw)은 전부 malicious(label=1)이므로 negative가 없어
accuracy는 recall과 사실상 동치이고 precision/F1/ROC-AUC는 정의되지 않는다
(코드에서 `None`으로 표시) — **recall이 유일한 유효 지표**다.
Confusion matrix/ROC curve: `report/figures/standard_confusion_matrix.png`,
`report/figures/standard_roc_curve.png`, `report/figures/cross_source_confusion_matrix.png`
(cross_source는 단일 클래스라 ROC curve 없음).

## 4. 논의

이 데이터셋의 가장 중요한 함정은 **label과 source_dataset이 100% confound**되어
있다는 점이다 (benign = 전부 caida, malicious = 전부 cic+unsw). standard split
결과(accuracy/recall/F1/ROC-AUC 모두 0.9997~0.99999)는 이 우려를 실측으로 확인한다:
IP/포트를 제외했음에도 flow 통계량만으로 사실상 완벽한 분류가 나왔는데, 이는
"공격을 탐지하는 능력"이라기보다 세 캡처 환경(캡처 장비, 시점, 네트워크 조건)이
통계적으로 워낙 이질적이어서 어느 소스에서 왔는지를 거의 완벽히 구분해낸 결과일
가능성이 크다.

**cross-source 검증이 바로 그 가설을 확증한다: recall = 0.0.** caida+cic로 학습한
모델은 학습 때 전혀 보지 못한 unsw의 malicious flow를 **단 하나도** 탐지하지
못했다(122,295개 중 0개 True Positive). standard split에서 99.98% recall을
보이던 것과 같은 모델 구조·특징·하이퍼파라미터인데도 결과가 이렇게 극단적으로
갈린다는 것은, standard split의 높은 점수가 "공격 행동의 일반화된 패턴"이 아니라
"cic 소스의 (그리고 간접적으로 caida 소스의) 특이한 flow 통계 분포"를 암기한
결과이고, unsw는 그 분포 밖에 있어 전혀 다른 영역으로 취급됐음을 시사한다.
즉 IP/포트를 제거하는 것만으로는 confound를 완전히 막지 못했다 — flow 레벨 통계
자체(패킷 크기 분포, IAT 패턴 등)도 캡처 환경마다 충분히 달라서 지름길로
악용될 수 있음을 보여주는 사례다.

**진단: 퇴화(degenerate) 실패임을 직접 확인.** recall=0이 단순 임계값 문제가
아니라 모델이 완전히 무너진 결과인지 확인하기 위해 cross_source 모델로 unsw
전체(122,295건)를 다시 예측해봤다. 결과: **122,295건 전원 class 0(benign)으로
예측**, malicious 확률(`predict_proba`)의 최댓값조차 0.33(평균 0.006, 중앙값
0.0)으로 어느 flow에도 0.5 임계값 근처까지 간 경우가 없었다. 즉 이 모델은
"애매하게 놓친" 것이 아니라 unsw의 malicious flow를 caida/cic에서 학습한
"benign 영역"과 거의 확신을 갖고 동일시하고 있다 — 세 데이터셋의 flow 통계
분포 자체가 서로 다른 캡처 환경의 표식으로 학습됐다는 가설과 정확히 들어맞는다.

**결론 및 시사점.** 이 데이터셋 구성(소스=라벨)에서는 random split 기반의
성능 지표를 "침입 탐지 성능"으로 보고하면 안 된다 — 실질적으로는 도메인
일반화가 전혀 되지 않는 모델을 만들어 놓고 우수하다고 착각하게 만든다. 진짜
공격 탐지 일반화 성능을 평가하려면 (1) 공격/정상 트래픽이 같은 캡처
환경/네트워크에서 함께 수집된 데이터셋을 쓰거나, (2) 최소한 이 실험처럼
소스를 기준으로 한 held-out 검증을 표준 지표와 나란히 반드시 보고해야 한다.
