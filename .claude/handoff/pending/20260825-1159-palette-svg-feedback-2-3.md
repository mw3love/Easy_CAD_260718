# 팔레트 등록 메뉴 — "미분류" 제거 → 즐겨찾기 슬롯으로 교체

생성: 2026-08-25 11:59
갱신: 2026-08-26 — 항목 B(SVG 그룹 큐닷)는 완전히 해결돼(그룹 프레임 3차, `_GroupBindProxy`/
`whole_group_id()`/`qc_dot_rects()` 코드로 재확인 완료) 서술을 걷어냄, 항목 A만 남김.

## 배경

2026-08-25 세션에서 사용자가 우클릭 "팔레트에 등록" 서브메뉴에 대해 추가 요청을 냈다:
"미분류 제거하고 그 자리는 즐겨찾기 자리로. 진짜 미분류가 필요하면 1개짜리 임시폴더를
만드는 게 오히려 직관적." 아직 미착수.

## 현재 상태

`host_selection.py::_build_register_symbol_menu`(348번 줄 부근)가 `[(미분류), 폴더1,
폴더2, ..., 새 폴더...]` 순으로 서브메뉴를 만든다(359번 줄: `m.addAction("(미분류)", ...)`).

## 구현 방향(확인 필요한 지점)

- `symbol_library.py`에 이미 `toggle_favorite(symbol_id)`(144번 줄)가 있다 —
  `add_symbol(name, item_dicts, thumb_b64, folder=None)`는 `favorite` 인자가 없고 항상
  `False`로 생성한 뒤(121번 줄) 별도 토글이 필요하다.
- "즐겨찾기로 등록" 메뉴 항목을 클릭하면: (a) `add_symbol(..., folder=None)`로 등록 후
  반환된 entry의 id로 `toggle_favorite(id)` 호출, 또는 (b) `add_symbol`에 `favorite=True`
  인자를 새로 추가하는 두 방법이 있다. (b)가 더 깔끔해 보이지만 `add_symbol` 시그니처
  변경이라 다른 호출부(SVG "내 심볼로 저장" 등, `host_fileio.py`) 영향 범위를 먼저 확인.
- 즐겨찾기로 등록된 심볼도 내부적으로 `folder=None`(미분류)일 수 있다는 점은 문제 없음 —
  기존 "이중표시"(원본 폴더 위치 + 즐겨찾기 섹션 둘 다 노출, 2026-08-20 구현) 관례가
  이미 `folder=None`이면서 `favorite=True`인 상태를 지원하는지만 확인하면 됨(아마 지원함,
  `_refresh_custom_symbol_section` 로직 확인).
- 서브메뉴 순서는 `[즐겨찾기로 등록, 폴더1, 폴더2, ..., 새 폴더...]`로 재구성.

## 판단 기준

`_build_register_symbol_menu`/`register_selection_as_symbol`는 국소 수정으로 충분할 것.
새 pytest는 기존 `tests/test_part7_symbol_library.py`의 서브메뉴 테스트들
(`test_build_register_symbol_menu_*`) 옆에 추가.

## 참고

관련 코드: `easycad/canvas/host_selection.py`(등록 메뉴), `easycad/fileio/symbol_library.py`
(`add_symbol`/`toggle_favorite`).
