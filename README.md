# Easy CAD

빠르고 쉬운 순서도/간단도면 작성기. 최종 목표는 **PDF 인쇄**, 기존 CAD 자산과의 **DXF 상호운용**.

pasteflow 주석 편집기(`QGraphicsScene` 기반 스냅·베지어 화살표)를 독립 무한캔버스 앱으로
승격한 프로젝트. 계획 전문은 `260718 Easy CAD/EasyCAD_계획.md`(Google Drive) 참조.

## 실행

```
pip install -r requirements.txt
python run.py
```

## 현재 상태 — Phase 0 (코어 이식 + 무한 캔버스)

- `easycad/canvas/annotator_core.py` — pasteflow 편집기 코어 verbatim 이식(theme import만 수정)
- `easycad/canvas/host.py` — 무한 캔버스 호스트(얇은 owner + 최소 툴바)
- 도구: 선택 · 네모 · 화살표(2점 베지어, 테두리 스냅) · 텍스트 · 원 · 선 · 펜 · 번호
- 조작: 스크롤=줌(커서 기준) · 가운데버튼/손모드 드래그=패닝 · Del=삭제 · Ctrl+Z=되돌리기 · Ctrl+C/V=연속 복사붙여넣기

## 로드맵

Phase 1 v1: 저장/열기 + PDF 출력(A4~A1, 전체/선택영역) · Phase 2 속도 UX ·
Phase 3 DXF 왜복 · Phase 4 표·이미지·표제란·Mermaid · Phase 5 AI 이미지→도면.
