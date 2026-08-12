"""커스텀 심볼 팔레트(§8 항목8) — 선택 등록 → 팔레트 반영 → 배치(그룹 복원) → 삭제.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part7_symbol_library.py. 라이브러리 파일은 _isolated_symbol_library로 격리된
임시 경로를 써 실제 사용자 AppData(symbol_library.json)를 건드리지 않는다.
"""
from unittest.mock import patch

from PyQt6.QtWidgets import QInputDialog, QMessageBox

from _shared import *  # noqa: F401,F403
from easycad.fileio import symbol_library
from easycad.canvas.host_selection import _group_scene_rect


def test_register_selection_creates_entry_and_palette_button():
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w, x=200, y=200, ww=100, hh=60)
        e = _EllipseItem(QRectF(0, 0, 40, 40)); e.setPos(260, 230)
        e.setFlags(e.GraphicsItemFlag.ItemIsSelectable | e.GraphicsItemFlag.ItemIsMovable)
        w._scene.addItem(e)
        r.setSelected(True); e.setSelected(True)

        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()

        entries = symbol_library.load_library()
        assert len(entries) == 1
        assert entries[0]["name"] == "증폭기"
        assert {d["type"] for d in entries[0]["items"]} == {"rect", "ellipse"}
        assert entries[0]["id"] in w._custom_sym_buttons


def test_register_empty_selection_is_noop():
    with _isolated_symbol_library():
        w = CanvasWindow()
        w.register_selection_as_symbol()   # 선택 없음
        assert symbol_library.load_library() == []


def test_register_cancelled_name_dialog_does_not_save():
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w)
        r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("", False)):
            w.register_selection_as_symbol()
        assert symbol_library.load_library() == []


def test_place_custom_symbol_preserves_relative_layout_and_groups():
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)      # 원본 좌상단 (0,0)
        e = _EllipseItem(QRectF(0, 0, 40, 40)); e.setPos(120, 10)   # 원본 좌상단 (120,10)
        e.setFlags(e.GraphicsItemFlag.ItemIsSelectable | e.GraphicsItemFlag.ItemIsMovable)
        w._scene.addItem(e)
        r.setSelected(True); e.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]

        w._scene.clearSelection()
        placed = w._create_shape_at(f"customsym:{sym_id}", QPointF(1000.0, 1000.0))
        assert placed is not None
        sel = w._scene.selectedItems()
        assert len(sel) == 2   # 새로 놓인 2개가 선택된 상태

        gids = {getattr(it, "_group_id", None) for it in sel}
        assert len(gids) == 1 and None not in gids   # 그룹으로 묶여 함께 선택/이동됨

        box = _group_scene_rect(sel)
        assert abs(box.left() - 1000.0) < 1e-6 and abs(box.top() - 1000.0) < 1e-6
        # 원본에서 e가 r보다 (120,10)만큼 떨어져 있던 상대 배치가 배치 후에도 유지되는지.
        new_r = next(it for it in sel if isinstance(it, _RectItem))
        new_e = next(it for it in sel if isinstance(it, _EllipseItem))
        assert abs((new_e.pos().x() - new_r.pos().x()) - 120.0) < 1e-6
        assert abs((new_e.pos().y() - new_r.pos().y()) - 10.0) < 1e-6


def test_place_custom_symbol_unknown_id_returns_none():
    with _isolated_symbol_library():
        w = CanvasWindow()
        before = len(w._scene.items())
        assert w._create_shape_at("customsym:doesnotexist", QPointF(0, 0)) is None
        assert len(w._scene.items()) == before


def test_delete_custom_symbol_removes_entry_and_button():
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            w._delete_custom_symbol_prompt(sym_id)
        assert symbol_library.load_library() == []
        assert sym_id not in w._custom_sym_buttons


def test_delete_custom_symbol_declined_keeps_entry():
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            w._delete_custom_symbol_prompt(sym_id)
        assert len(symbol_library.load_library()) == 1
        assert sym_id in w._custom_sym_buttons


# ---- [신규기능, 2026-08-12 좌측 패널 아코디언 개편] 내 심볼 폴더 -----------------------

def test_new_symbol_defaults_to_unclassified():
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        assert symbol_library.load_library()[0]["folder"] is None


def test_create_folder_persists_even_when_empty():
    with _isolated_symbol_library():
        symbol_library.create_folder("무선")
        assert symbol_library.load_folders() == ["무선"]
        symbol_library.create_folder("무선")   # 중복 생성은 무시
        assert symbol_library.load_folders() == ["무선"]


def test_create_folder_blank_name_is_noop():
    with _isolated_symbol_library():
        symbol_library.create_folder("   ")
        assert symbol_library.load_folders() == []


def test_move_symbol_between_folders():
    with _isolated_symbol_library():
        symbol_library.create_folder("무선")
        entry = symbol_library.add_symbol("증폭기", [], "")
        symbol_library.move_symbol(entry["id"], "무선")
        assert symbol_library.load_library()[0]["folder"] == "무선"
        symbol_library.move_symbol(entry["id"], None)   # 미분류로 되돌리기
        assert symbol_library.load_library()[0]["folder"] is None


def test_delete_folder_moves_members_to_unclassified_not_deletes_them():
    with _isolated_symbol_library():
        symbol_library.create_folder("무선")
        entry = symbol_library.add_symbol("증폭기", [], "", folder="무선")
        symbol_library.delete_folder("무선")
        assert symbol_library.load_folders() == []
        entries = symbol_library.load_library()
        assert len(entries) == 1
        assert entries[0]["id"] == entry["id"]
        assert entries[0]["folder"] is None


def test_left_panel_new_folder_and_drag_move_wiring():
    """UI 배선 — "+" 버튼(`_prompt_create_symbol_folder`)과 드롭존 콜백(`_move_custom_symbol`)이
    실제로 라이브러리를 갱신하고 팔레트를 다시 그리는지. 실제 QDrag 합성은 이 하네스가
    라이브 드래그를 재현 못 한다는 기존 제약(docs/history 참조)과 같은 이유로 피하고, 드롭존이
    호출하는 콜백을 직접 호출해 같은 경로를 검증한다."""
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]

        with patch.object(QInputDialog, "getText", return_value=("무선", True)):
            w._prompt_create_symbol_folder()
        assert symbol_library.load_folders() == ["무선"]

        w._move_custom_symbol(sym_id, "무선")
        assert symbol_library.load_library()[0]["folder"] == "무선"
        assert sym_id in w._custom_sym_buttons   # refresh가 다시 그려도 버튼 매핑 유지

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            w._delete_symbol_folder_prompt("무선")
        assert symbol_library.load_folders() == []
        assert symbol_library.load_library()[0]["folder"] is None
