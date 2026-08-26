# Easy CAD

빠르고 쉬운 순서도/간단도면 작성기. 최종 목표는 **PDF 인쇄**, 기존 CAD 자산과의 **DXF 상호운용**.

pasteflow 주석 편집기(`QGraphicsScene` 기반 스냅·베지어 화살표)를 독립 무한캔버스 앱으로
승격한 프로젝트. 계획 전문은 `docs/EasyCAD_계획.md`(리포 내) 참조.

## 실행

```
pip install -r requirements.txt
python run.py
```

테스트: `python tests/test_easycad.py`(요약 러너) 또는 `pytest tests/`(전체, 1000종+) —
offscreen 회귀 스모크. 정확한 현재 종수는 실행 시 출력을 참조(계속 늘어나는 중이라 이
문서엔 고정 숫자를 적지 않는다).

## 구조

- `easycad/canvas/` — 캔버스 코어(`core_constants.py`/`core_shapes.py`/`core_view.py`,
  `annotator_core.py`는 하위호환 재수출 shim) + 창(`host.py`, 역할별 `host_*.py` 믹스인).
- `easycad/fileio/` — PDF·DXF/DWG·`.ecad`·SVG·Mermaid·이미지→도면 빌더 왕복.
- `easycad/ai/` — AI 게이트웨이 클라이언트(Mermaid/SVG 생성, 텍스트→도면).
- 상세 구조·현재 진행 상태·작업 규칙은 `CLAUDE.md`, 월별 이력은 `docs/history/`,
  자주 겪는 함정은 `docs/pitfalls.md` 참조.

## 도구 · 조작

- 상단 도구(단축키 1~7, T): 선택 · 화살표 · 텍스트 · 선 · 다각형 · 펜 · 번호 · 자르기(TRIM).
  사각형·원과 심볼 라이브러리(기본 도형·순서도·"내 심볼")는 좌측 팔레트에서 클릭/드래그로 배치.
- 조작: 스크롤=줌(커서 기준) · 가운데버튼/손모드 드래그=패닝 · Del=삭제 · Ctrl+Z=되돌리기 ·
  Ctrl+C/V=복사붙여넣기 · Ctrl+D=복제 · Shift+G=격자 · Shift+A=정렬가이드
- 단축키는 편집(&E) → "단축키 설정…"에서 카테고리별로 재할당 가능(`shortcuts.py`가 기본값 소유).

## 로드맵

핵심 기능(무한캔버스·PDF/`.ecad`·DXF·DWG 왕복·심볼 라이브러리·TRIM/EXTEND·AI 이미지→도면·
Mermaid/SVG AI 생성·마인드맵 뻗기 등)은 전부 완료됐고, 현재는 최종 검수(코드리뷰·함정
재발감사·릴리스 준비) 단계다. 상세 진행 상태·다음 순서는 `CLAUDE.md`와
`docs/EasyCAD_계획.md` §8 참조.
