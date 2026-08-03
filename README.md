# Easy CAD

빠르고 쉬운 순서도/간단도면 작성기. 최종 목표는 **PDF 인쇄**, 기존 CAD 자산과의 **DXF 상호운용**.

pasteflow 주석 편집기(`QGraphicsScene` 기반 스냅·베지어 화살표)를 독립 무한캔버스 앱으로
승격한 프로젝트. 계획 전문은 `docs/EasyCAD_계획.md`(리포 내) 참조.

## 실행

```
pip install -r requirements.txt
python run.py
```

테스트: `python tests/test_easycad.py` (또는 `pytest tests/`) — 373종 offscreen 회귀 스모크.

## 구조

- `easycad/canvas/` — 캔버스 코어(`core_constants.py`/`core_shapes.py`/`core_view.py`,
  `annotator_core.py`는 하위호환 재수출 shim) + 창(`host.py`, 역할별 `host_*.py` 믹스인).
- `easycad/fileio/` — PDF·DXF·`.ecad`·Mermaid·이미지→도면 빌더.
- 상세 구조·현재 진행 상태·작업 규칙은 `CLAUDE.md`, 월별 이력은 `docs/history/`,
  자주 겪는 함정은 `docs/pitfalls.md` 참조.

## 도구 · 조작

- 도구: 선택 · 네모 · 화살표(직선/곡선/직각) · 텍스트 · 원 · 선 · 펜 · 번호 · 심볼 14종
- 조작: 스크롤=줌(커서 기준) · 가운데버튼/손모드 드래그=패닝 · Del=삭제 · Ctrl+Z=되돌리기 ·
  Ctrl+C/V=복사붙여넣기 · Ctrl+D=복제 · Shift+G=격자 · Shift+A=정렬가이드

## 로드맵

Phase 0~5 완료(무한캔버스 코어·PDF/`.ecad`·DXF 왕복·Mermaid import·이미지→도면 빌더).
Phase 6(편집 경험 현대화 UI/UX) 진행 중 — 다음 순서는 `docs/EasyCAD_계획.md` §8 참조.
