---
name: flow-feature-extraction
description: "패킷 단위 네트워크 트래픽 CSV를 5-tuple 기준 flow로 재구성하고 Flow Size/Duration/Packet Size 통계/IAT 통계/Entropy 등 flow-level 특징을 추출한다. 'flow 구성', '패킷을 플로우로 묶기', 'IAT', 'entropy 특징', '네트워크 특징 추출' 관련 작업 시 사용."
---

# Flow Feature Extraction

패킷 단위 raw 데이터를 침입 탐지 모델이 학습 가능한 flow-level 표(table)로 변환하는 절차.

## 왜 flow 단위인가

패킷 하나만으로는 정상/악성을 판단하기 어렵다. 침입 탐지에서 의미 있는 신호(스캔의 빠른 반복, DoS의 짧은 flow duration과 큰 flow size, 정상 통신의 규칙적인 IAT 등)는 "연결(flow)" 단위에서 드러난다. 그래서 5-tuple로 패킷을 flow로 묶은 뒤 통계 특징을 계산한다.

## 5-tuple 그룹핑

5-tuple = (Source IP, Destination IP, Source Port, Destination Port, Protocol).

**핵심 판단 포인트 — 단방향 vs 양방향 flow:**
- 단방향(uni-directional): (src, dst, sport, dport, proto)를 그대로 키로 사용. A→B와 B→A가 별개 flow가 된다.
- 양방향(bi-directional): (src, dst, sport, dport, proto)와 그 역방향 (dst, src, dport, sport, proto)을 같은 flow로 합친다. 정규화 키를 만들려면 IP:Port 쌍을 정렬(예: 사전순으로 작은 쪽을 항상 앞에 두는 방식)해서 같은 flow가 방향에 관계없이 동일한 키로 묶이게 한다.
- 과제 지시사항은 5-tuple만 명시하고 방향을 특정하지 않았으므로, 데이터의 특성(단방향 캡처인지 양방향인지)을 먼저 확인하고 선택한 방식과 이유를 `_workspace` 요약에 남긴다. 세 데이터셋 모두 동일한 방식을 일관되게 적용하는 것이 중요하다 — 방식이 다르면 벤치마크 자체가 왜곡된다.

## 계산할 통계량

- **Flow Size**: flow 내 패킷 수, 총 바이트 수(둘 다 유용)
- **Flow Duration**: `max(timestamp) - min(timestamp)` (초 단위 등 데이터 timestamp 단위 확인 필수)
- **Packet Size 통계**: mean/min/max/std — `numpy`로 계산
- **IAT(Inter-Arrival Time) 통계**: 정렬된 timestamp의 연속 차분(`diff()`) → mean/min/max/std. 패킷이 1개뿐인 flow는 IAT가 정의되지 않으므로 0 또는 NaN으로 명시적으로 처리(임의로 큰 값을 채우지 않는다).
- **Packet Size Entropy**: 패킷 크기 값들의 분포에 대한 Shannon entropy. 연속값이므로 히스토그램 bin으로 이산화한 뒤 확률분포를 구해 계산한다.
- **IAT Entropy**: 동일한 방식으로 IAT 값 분포에 대해 계산.

Shannon entropy 계산 패턴:
```python
import numpy as np

def shannon_entropy(values, bins=10):
    values = np.asarray(values)
    if len(values) < 2:
        return 0.0
    counts, _ = np.histogram(values, bins=bins)
    probs = counts[counts > 0] / counts.sum()
    return float(-(probs * np.log2(probs)).sum())
```

## 데이터셋 간 스키마 정규화

CAIDA/CIC/UNSW는 컬럼명과 형식이 다를 가능성이 높다. 각 데이터셋을 로드할 때 다음 공통 스키마로 매핑하는 어댑터 함수를 각각 만든다:

```python
COMMON_COLUMNS = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol", "timestamp", "packet_size"]
```

실제 컬럼명은 반드시 `df.columns`로 먼저 확인 후 매핑한다 — 가정으로 하드코딩하지 않는다.

## 라벨링

- CAIDA → `label = 0` (benign)
- CIC, UNSW → `label = 1` (malicious)

세 데이터셋을 정규화 후 concat하여 하나의 `features.csv`로 만든다.

## 흔한 실수

- timestamp 단위 불일치(초 vs 마이크로초)를 확인하지 않고 Duration/IAT를 계산 — 데이터셋마다 실제 값을 확인한다.
- flow당 패킷이 1개인 경우 std/IAT 계산에서 NaN 발생 — 반드시 처리 로직을 넣는다.
- 세 데이터셋을 다른 flow 구성 방식(단방향/양방향)으로 처리 — 일관성 깨짐.
