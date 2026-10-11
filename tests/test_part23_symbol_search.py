"""§8 항목34(2026-10-03) — '내 심볼' 검색창. 사용자 결정: 항상 보이는 검색칸(제목 바로 아래) ·
폴더 유지·빈 폴더 숨김(접힌 폴더도 검색 중엔 펼쳐 보임) · 이름 일부 + 초성.
⚠ QTest.keyClicks로 한글 자모를 치면 테스트 프로세스가 exit 127로 죽는다(검색 기능과 무관 — 신호를 끊어도
같음, 2026-10-03 실측) → 한글은 setText로 넣는다."""
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QTest

from _shared import *  # noqa: F401,F403
from easycad.app_settings import app_settings
from easycad.canvas.host_ui import _symbol_name_matches
from easycad.fileio import symbol_library
from easycad.fileio.document import _pixmap_to_b64


def test_name_match_substring_case_and_choseong():
    assert _symbol_name_matches("Zigbee", "zig")
    assert _symbol_name_matches("Zigbee", "  ZIG ")
    assert _symbol_name_matches("안테나", "ㅇㅌ")
    assert _symbol_name_matches("안테나", "ㅌㄴ")
    assert _symbol_name_matches("안테나", "안ㅌ")          # 글자와 초성 섞기
    assert _symbol_name_matches("UHD 안테나", "ㅇㅌㄴ")
    assert _symbol_name_matches("아무거나", "")
    assert not _symbol_name_matches("안테나", "ㅇㄴ")       # 이어진 글자만
    assert not _symbol_name_matches("앰프", "ㅇㅌ")
    assert not _symbol_name_matches("abc", "ㅇ")


def _thumb():
    pm = QPixmap(8, 8)
    pm.fill(Qt.GlobalColor.white)
    return _pixmap_to_b64(pm)


def _lib(folder_a, folder_b):
    rect = [{"type": "rect", "rect": [0, 0, 40, 30], "pen": "#ff000000", "width": 1.0, "fill": None,
             "pos": [0, 0], "scale": 1.0, "rotation": 0.0, "z": 0, "origin": [0, 0]}]
    symbol_library.create_folder(folder_a)
    symbol_library.create_folder(folder_b)
    ant = symbol_library.add_symbol("안테나", rect, _thumb(), folder_a)
    amp = symbol_library.add_symbol("앰프", rect, _thumb(), folder_b)
    zig = symbol_library.add_symbol("Zigbee", rect, _thumb(), None)
    return ant, amp, zig


def test_search_filters_and_hides_empty_folders():
    with _isolated_symbol_library():
        ant, amp, zig = _lib("폴더A", "폴더B")
        w = CanvasWindow()
        body = w._custom_sym_body.layout()
        assert body.count() == 3                               # 폴더 2개 + 「새 폴더」(미분류 없음 — Zigbee는 폴더B로)
        w._custom_sym_search.setText("ㅇㅌ")
        assert set(w._custom_sym_buttons) == {ant["id"]}
        assert body.count() == 1                               # 폴더A만 남음
        w._custom_sym_search.setText("zig")
        assert set(w._custom_sym_buttons) == {zig["id"]}
        w._custom_sym_search.setText("없는이름")
        assert not w._custom_sym_buttons and body.count() == 1
        assert body.itemAt(0).widget().text() == "일치하는 도형·심볼 없음"
        w._custom_sym_search.clear()
        assert set(w._custom_sym_buttons) == {ant["id"], amp["id"], zig["id"]} and body.count() == 3
        assert zig["folder"] == "폴더B"                        # 폴더 없이 등록 → 마지막에 쓴 폴더


def test_search_shows_collapsed_folder_without_changing_saved_state():
    with _isolated_symbol_library():
        folder = f"접힘시험_{uuid.uuid4().hex[:6]}"
        ant, _amp, _zig = _lib(folder, f"다른_{uuid.uuid4().hex[:6]}")
        key = f"symfolder_collapsed_{folder}"
        st = app_settings()
        st.setValue(key, True)
        try:
            w = CanvasWindow()
            body = w._custom_sym_body
            assert not w._custom_sym_buttons[ant["id"]][0].isVisibleTo(body)   # 평소엔 접힘
            w._custom_sym_search.setText("안테")
            assert w._custom_sym_buttons[ant["id"]][0].isVisibleTo(body)       # 검색 중엔 보임
            assert st.value(key, False, type=bool) is True                     # 저장값 그대로
            w._custom_sym_search.clear()
            assert not w._custom_sym_buttons[ant["id"]][0].isVisibleTo(body)
        finally:
            st.remove(key)


def test_rebuild_during_search_keeps_query_and_esc_clears():
    with _isolated_symbol_library():
        ant, _amp, _zig = _lib("폴더A", "폴더B")
        w = CanvasWindow()
        w._custom_sym_search.setText("안")
        new = symbol_library.add_symbol("안내판", [], _thumb(), None)
        w._refresh_custom_symbol_section()                      # 등록 직후와 같은 다시 그리기
        assert w._custom_sym_search.text() == "안"
        assert set(w._custom_sym_buttons) == {ant["id"], new["id"]}
        QTest.keyClick(w._custom_sym_search, Qt.Key.Key_Escape)
        assert w._custom_sym_search.text() == ""
        assert len(w._custom_sym_buttons) == 4


def test_search_box_sits_at_top_of_shape_symbol_card():
    """[첫 화면 재디자인 2026-10-07, 시안 3라운드 S3] 검색칸은 카드 맨 위(「즐겨찾기」 위)."""
    w = CanvasWindow()
    outer = w._left_container.layout()
    assert outer.itemAt(0).widget().isAncestorOf(w._custom_sym_search)
    assert outer.itemAt(1).widget() is w._fav_section
    assert outer.itemAt(2).widget() is w._basic_section
    assert w._custom_sym_search.isClearButtonEnabled()
    assert w._left_panel._title_lbl.text() == "도형 · 심볼"


def test_search_shows_flat_list_with_basic_shapes_and_folder_names():
    """[패널 통일 2라운드 2026-10-11, 시안 2-3] 검색 결과는 폴더로 나누지 않은 한 줄 목록 — 기본 도형도 함께,
    줄 오른쪽에 어느 폴더인지. 그동안 「즐겨찾기」·「기본 도형」 칸은 숨긴다."""
    from PyQt6.QtWidgets import QLabel
    with _isolated_symbol_library():
        ant, _amp, _zig = _lib("폴더A", "폴더B")
        w = CanvasWindow()
        w.show()
        w._custom_sym_search.setText("ㅅ")          # 사각형·삼각형·시작/끝·저장소 (심볼은 없음)
        body = w._custom_sym_body.layout()
        assert body.count() == 1
        sec = body.itemAt(0).widget()
        assert sec._title_lbl.text() == "검색 결과" and sec.count_lbl.text() == "4"
        assert list(w._search_result_buttons) == ["rect", "sym:triangle", "sym:terminal", "sym:database"]
        assert all(b.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                   for b in w._search_result_buttons.values())
        assert not w._fav_section.isVisibleTo(w._left_container)
        assert not w._basic_section.isVisibleTo(w._left_container)
        w._custom_sym_search.setText("안테")
        assert set(w._custom_sym_buttons) == {ant["id"]}
        tags = [l.text() for l in body.itemAt(0).widget().findChildren(QLabel)]
        assert "폴더A" in tags                                          # 어느 폴더인지 줄 오른쪽에
        w._custom_sym_search.clear()
        assert w._fav_section.isVisibleTo(w._left_container)
        assert w._basic_section.isVisibleTo(w._left_container)


def test_favorites_start_with_four_basics_and_toggle_from_any_palette_item():
    """[실사용 피드백 2026-10-11] 옛 「자주 쓰는 것」(최근 8개 자동) → 사용자가 넣고 빼는 「즐겨찾기」(제목 ★).
    기본 도형도 내 심볼도 우클릭 메뉴로 넣고 빼며, 쓰기만 해서는 안 바뀐다. 라이브러리 파일에 저장(PC 간 동기화)."""
    from PyQt6.QtWidgets import QMenu
    from unittest.mock import patch
    with _isolated_symbol_library():
        ant, _amp, _zig = _lib("폴더A", "폴더B")
        w = CanvasWindow()
        assert "★" in w._fav_section._title_lbl.text() and "즐겨찾기" in w._fav_section._title_lbl.text()
        assert [b.text() for b in w._fav_palette_buttons.values()] == ["사각형", "원", "판단", "시작/끝"]
        w._shape_tool_buttons["triangle"].click()               # 쓰기만 해서는 안 들어간다
        assert "sym:triangle" not in w._fav_palette_buttons
        assert w._fav_palette_buttons["rect"].isChecked() is False

        def run_menu(btn, key, label):
            seen = []

            def fake_exec(menu, *_a):
                acts = [a for a in menu.actions() if a.text()]
                seen.extend(a.text() for a in acts)
                assert all(not a.icon().isNull() for a in acts)      # 메뉴는 늘 아이콘+글자
                next(a for a in acts if a.text() == label).trigger()
            with patch.object(QMenu, "exec", fake_exec):
                w._show_palette_item_menu(btn, btn.rect().center(), key)
            return seen
        assert run_menu(w._shape_tool_buttons["triangle"], "sym:triangle", "즐겨찾기에 넣기") == ["즐겨찾기에 넣기"]
        assert list(w._fav_palette_buttons)[-1] == "sym:triangle"        # 맨 뒤에
        seen = run_menu(w._custom_sym_buttons[ant["id"]][0], f"customsym:{ant['id']}", "즐겨찾기에 넣기")
        assert seen[0] == "즐겨찾기에 넣기" and "이름변경…" in seen and "삭제…" in seen
        assert f"customsym:{ant['id']}" in w._fav_palette_buttons
        assert w._fav_section.count_lbl.text() == "6"
        # 즐겨찾기 칸 안에서 빼기
        run_menu(w._fav_palette_buttons["rect"], "rect", "즐겨찾기에서 빼기")
        assert "rect" not in w._fav_palette_buttons
        assert symbol_library.load_favorites() == ["ellipse", "sym:decision", "sym:terminal", "sym:triangle",
                                                   f"customsym:{ant['id']}"]
        assert list(CanvasWindow()._fav_palette_buttons) == symbol_library.load_favorites()   # 다음 창에도
        symbol_library.delete_symbol(ant["id"])                  # 지운 심볼은 즐겨찾기에서도 빠진다
        assert f"customsym:{ant['id']}" not in symbol_library.load_favorites()


def test_palette_items_always_show_icon_and_name():
    """[실사용 피드백 2026-10-11] 큰 아이콘 보기 없앰("글자가 같이 있는 게 가독성이 좋음") — 늘 아이콘 옆 이름 한 줄,
    긴 이름은 …로, 보기 전환 버튼도 없다."""
    from PyQt6.QtCore import Qt as _Qt
    with _isolated_symbol_library():
        ant, _amp, _zig = _lib("폴더A", "폴더B")
        symbol_library.rename_symbol(ant["id"], "야기 안테나 3소자 긴 이름")
        w = CanvasWindow()
        assert not hasattr(w, "_palette_view_btns") and not hasattr(w, "_palette_view")
        b = w._custom_sym_buttons[ant["id"]][0]
        assert b._full_name == "야기 안테나 3소자 긴 이름" and b.accessibleName() == b._full_name
        assert b.toolButtonStyle() == _Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        assert b.text() == b.fontMetrics().elidedText(b._full_name, _Qt.TextElideMode.ElideRight, 118)
        for btn in list(w._shape_tool_buttons.values()) + list(w._fav_palette_buttons.values()):
            assert btn.toolButtonStyle() == _Qt.ToolButtonStyle.ToolButtonTextBesideIcon and btn.text()


def test_favorites_and_basic_sections_collapse_and_persist():
    """[실사용 피드백 2026-10-11] 「즐겨찾기」·「기본 도형」도 제목 줄에서 접는다 — 접힘 저장, 접었다 펴면
    패널 높이가 원래대로, 접어 둔 기본 도형도 검색 중엔 펼쳐 보이고 결과로 센다."""
    st = app_settings()
    keys = ("palette_section_collapsed_fav", "palette_section_collapsed_basic")
    st.setValue("left_panel_height", 5000)   # 카드 높이 상한(창 절반)에 안 걸리게
    iso = _isolated_symbol_library()   # 실제 라이브러리의 폴더들까지 들어가면 레이어 카드 위 상한에 닿는다
    iso.__enter__()
    try:
        w = CanvasWindow()
        w.show()
        h0 = w._left_panel.height()
        w._basic_section.collapse_btn.click()
        assert w._basic_section.body.isHidden() and w._basic_section.collapse_btn.text() == "▸"
        assert w._left_panel.height() < h0                       # 패널이 줄어든다
        assert st.value(keys[1], False, type=bool) is True
        w._custom_sym_search.setText("판단")
        assert "sym:decision" in w._search_result_buttons        # 접혀 있어도 결과 목록엔 나온다(2026-10-11 한 줄 목록)
        assert st.value(keys[1], False, type=bool) is True       # 저장값 그대로
        w._custom_sym_search.clear()
        QTest.qWait(50)                                          # 내 심볼 다시 그리기는 한 틱 뒤에 크기가 맞는다
        assert w._basic_section.body.isHidden()
        w._fav_section.collapse_btn.click()
        assert w._fav_section.body.isHidden() and st.value(keys[0], False, type=bool) is True
        w2 = CanvasWindow()                                      # 다음 창에도 접힌 채
        assert w2._fav_section.body.isHidden() and w2._basic_section.body.isHidden()
        w._basic_section.collapse_btn.click(); w._fav_section.collapse_btn.click()
        assert w._left_panel.height() == h0, (w._left_panel.height(), h0)   # 다 펴면 원래 높이
    finally:
        iso.__exit__(None, None, None)
        for k in keys + ("left_panel_height",):
            st.remove(k)
