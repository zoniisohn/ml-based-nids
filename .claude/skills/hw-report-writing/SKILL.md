---
name: hw-report-writing
description: "Feature extraction/모델 학습/평가 산출물을 종합해 과제 제출용 리포트를 작성하고 PDF로 변환한다. '리포트 작성', '최종 보고서', 'PDF로 변환', '제출물 정리' 관련 작업 시 사용."
---

# HW Report Writing

파이프라인 산출물을 과제 제출 형식의 리포트로 종합하고 PDF로 변환하는 절차.

## 리포트 구조 (과제 요구사항 기준)

```markdown
# ML-Based Network Intrusion Detection System

## 1. Feature Extraction
(raw packet → 5-tuple flow 구성 → feature 계산 과정 설명)

## 2. Feature Selection Rationale
(왜 이 feature들을 선택했는지 — 각 feature가 침입 탐지에 유의미한 이유)

## 3. Model Training and Evaluation Summary
(모델 종류, 학습 설정, train/test 크기, 지표 표)

## 4. Discussion and Analysis
(성능 해석, 한계, 개선 방향)
```

## PDF 변환 방법 (우선순위)

**1순위 — pandoc:**
```bash
pandoc report/final_report.md -o report/final_report.pdf
```
이미지 경로는 `.md` 파일 기준 상대경로로 두면 pandoc이 자동으로 임베드한다.

**2순위 — Python (pandoc 미설치 시):**
```python
import markdown
from weasyprint import HTML

with open("report/final_report.md", encoding="utf-8") as f:
    html_body = markdown.markdown(f.read(), extensions=["tables"])
HTML(string=html_body, base_url="report/").write_pdf("report/final_report.pdf")
```

**3순위 — 둘 다 실패:**
`.md` 파일만 산출하고, 사용자에게 도구 미설치 사실과 수동 변환 방법(VS Code "Markdown PDF" 확장, 또는 `.md`를 Word/Google Docs로 붙여넣어 내보내기)을 안내한다. 조용히 실패로 끝내지 않는다.

## 원칙

- 이전 단계 요약(`_workspace/0*_*.md`)은 작업 로그 톤이므로, 리포트는 제출 문서 톤(서술형, 3인칭 또는 격식체)으로 다시 쓴다.
- 수치는 상위 결과 파일 값을 그대로 인용한다 — 재계산하거나 임의 추정하지 않는다.
- 표절 방지 조항이 있는 과제이므로 문장은 새로 작성한다(요약 파일을 그대로 복사하지 않는다).
- 시각화(figures)는 반드시 리포트 본문에 삽입하고, 각 그림에 대해 최소 1문장 이상 해석을 붙인다 — 그림만 던지지 않는다.
