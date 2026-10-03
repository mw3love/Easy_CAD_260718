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
        assert body.count() == 3                               # 미분류 + 폴더 2개(즐겨찾기 없음)
        w._custom_sym_search.setText("ㅇㅌ")
        assert set(w._custom_sym_buttons) == {ant["id"]}
        assert body.count() == 1                               # 폴더A만 남음
        w._custom_sym_search.setText("zig")
        assert set(w._custom_sym_buttons) == {zig["id"]}
        w._custom_sym_search.setText("없는이름")
        assert not w._custom_sym_buttons and body.count() == 1
        assert body.itemAt(0).widget().text() == "일치하는 심볼 없음"
        w._custom_sym_search.clear()
        assert set(w._custom_sym_buttons) == {ant["id"], amp["id"], zig["id"]} and body.count() == 3


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


def test_search_box_sits_under_my_symbols_title():
    w = CanvasWindow()
    sec = w._custom_sym_section.layout()
    assert sec.itemAt(1).widget().isAncestorOf(w._custom_sym_search)   # 제목(0) 바로 다음
    assert w._custom_sym_search.isClearButtonEnabled()
