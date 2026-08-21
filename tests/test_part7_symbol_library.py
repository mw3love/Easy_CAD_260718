"""커스텀 심볼 팔레트(§8 항목8) — 선택 등록 → 팔레트 반영 → 배치(그룹 복원) → 삭제.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part7_symbol_library.py. 라이브러리 파일은 _isolated_symbol_library로 격리된
임시 경로를 써 실제 리포의 symbol_library/symbol_library.json(2026-08-20 이관, 이전엔
OS AppData)을 건드리지 않는다.
"""
from unittest.mock import patch

from PyQt6.QtWidgets import QInputDialog, QMessageBox, QMenu, QFileDialog
from PyQt6.QtGui import QPen

from _shared import *  # noqa: F401,F403
from easycad.fileio import symbol_library
from easycad.canvas.host_selection import _group_scene_rect
from easycad.canvas.host_ui import _PALETTE_SYM_ICON_PX
from easycad.fileio.document import _b64_to_pixmap


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


def test_register_selection_thumbnail_uses_min_stroke_render():
    # [실사용 피드백 2026-08-18] 배선 확인 — 등록 시 썸네일 렌더가 최소 두께 헬퍼를 거치는지
    # (값 검증은 test_part6의 test_min_stroke_render_* 가 이미 함, 여기선 배선만).
    from easycad.canvas import host_selection
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w, width=1.0); r.setSelected(True)
        with patch("easycad.canvas.host_selection._min_stroke_render",
                   wraps=host_selection._min_stroke_render) as spy, \
             patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        assert spy.called


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


# ---- [실사용 피드백 2026-08-18] 심볼 이름변경(우클릭 메뉴) -----------------------------

def test_rename_symbol_updates_name():
    with _isolated_symbol_library():
        entry = symbol_library.add_symbol("증폭기", [], "")
        symbol_library.rename_symbol(entry["id"], "저잡음 증폭기")
        assert symbol_library.load_library()[0]["name"] == "저잡음 증폭기"


def test_rename_symbol_blank_name_is_noop():
    with _isolated_symbol_library():
        entry = symbol_library.add_symbol("증폭기", [], "")
        symbol_library.rename_symbol(entry["id"], "   ")
        assert symbol_library.load_library()[0]["name"] == "증폭기"


def test_rename_symbol_unknown_id_is_noop():
    with _isolated_symbol_library():
        symbol_library.add_symbol("증폭기", [], "")
        symbol_library.rename_symbol("doesnotexist", "새이름")
        assert symbol_library.load_library()[0]["name"] == "증폭기"


def test_rename_custom_symbol_prompt_updates_entry_and_button_refresh():
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]

        with patch.object(QInputDialog, "getText", return_value=("저잡음 증폭기", True)):
            w._rename_custom_symbol_prompt(sym_id)
        assert symbol_library.load_library()[0]["name"] == "저잡음 증폭기"
        assert sym_id in w._custom_sym_buttons   # refresh가 다시 그려도 버튼 매핑 유지
        # [실사용 피드백 2026-08-19] 정적 toolTip()이 아니라 호버 시 지연 계산되는 확대
        # 미리보기(tooltip_html_fn)로 바뀌었다 — 그 계산 결과에 새 이름이 반영되는지 확인.
        btn = w._custom_sym_buttons[sym_id][0]
        assert btn.toolTip() == ""
        assert "저잡음 증폭기" in btn._tooltip_html_fn()


def test_rename_custom_symbol_prompt_cancelled_keeps_name():
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]

        with patch.object(QInputDialog, "getText", return_value=("무시될 이름", False)):
            w._rename_custom_symbol_prompt(sym_id)
        assert symbol_library.load_library()[0]["name"] == "증폭기"


def test_custom_symbol_context_menu_has_rename_and_delete_actions():
    """우클릭이 곧바로 삭제 확인창을 띄우던 옛 동작 대신 메뉴(즐겨찾기 토글/이름변경/삭제)를
    띄우는지 — 실제 모달은 `exec`를 no-op으로 바꿔 안 띄우고, 만들어진 메뉴의 액션 텍스트만
    확인. [2026-08-20] 즐겨찾기 토글 항목이 맨 앞에 추가됨(deep-interview).
    [실사용 요청 2026-08-21] "SVG로 내보내기…"가 구분선과 함께 이름변경/삭제 사이에 추가됨."""
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]
        btn = w._custom_sym_buttons[sym_id][0]

        created_menus = []

        class _CapturingMenu(QMenu):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                created_menus.append(self)

            def exec(self, *a, **kw):
                return None   # 실제 모달을 안 띄움

        with patch("easycad.canvas.host_ui.QMenu", _CapturingMenu):
            w._show_custom_symbol_context_menu(btn, QPointF(1, 1).toPoint(), sym_id)
        assert len(created_menus) == 1
        texts = [a.text() for a in created_menus[0].actions() if not a.isSeparator()]
        assert texts == ["즐겨찾기 추가", "이름변경…", "SVG로 내보내기…", "삭제…"]


# ---- [실사용 요청 2026-08-21] 심볼 우클릭 → SVG로 내보내기 --------------------------------

def test_export_custom_symbol_svg_writes_file():
    # 심볼 저장 형식이 이미 도형 dict 목록이라(insert_items로 재구성) + export_svg_symbol
    # (콘텐츠 크기에 꽉 맞춘 SVG)만으로 새 의존성 없이 구현 — 실제 파일이 생기는지 확인.
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w, x=0, y=0, ww=80, hh=50); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]

        out = os.path.join(_TMP, f"amp_{uuid.uuid4().hex}.svg")
        with patch.object(QFileDialog, "getSaveFileName", return_value=(out, "")):
            w._export_custom_symbol_svg(sym_id)
        assert os.path.exists(out)
        with open(out, encoding="utf-8") as f:
            content = f.read()
        assert "<svg" in content and "<rect" in content


def test_export_custom_symbol_svg_missing_id_is_noop():
    with _isolated_symbol_library():
        w = CanvasWindow()
        with patch.object(QFileDialog, "getSaveFileName") as mock_save:
            w._export_custom_symbol_svg("no-such-id")
        mock_save.assert_not_called()


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


def test_delete_folder_deletes_member_symbols_too():
    # [정책 전환 2026-08-19] 도입 당시엔 소속 심볼을 미분류로 옮겨 보존했으나, 실사용
    # 피드백으로 "폴더 삭제 = 안의 것도 함께 삭제" 정책으로 뒤집혔다(남기고 싶으면 삭제
    # 전에 직접 다른 폴더로 옮겨두는 루틴 전제). 무관한 다른 폴더·미분류 심볼은 그대로
    # 남는지도 함께 확인.
    with _isolated_symbol_library():
        symbol_library.create_folder("무선")
        symbol_library.create_folder("전원")
        deleted = symbol_library.add_symbol("증폭기", [], "", folder="무선")
        kept_other_folder = symbol_library.add_symbol("변압기", [], "", folder="전원")
        kept_unfiled = symbol_library.add_symbol("커넥터", [], "", folder=None)
        symbol_library.delete_folder("무선")
        assert symbol_library.load_folders() == ["전원"]
        remaining_ids = {e["id"] for e in symbol_library.load_library()}
        assert deleted["id"] not in remaining_ids
        assert remaining_ids == {kept_other_folder["id"], kept_unfiled["id"]}


# ---- [실사용 피드백 2026-08-19] 폴더 이름변경 ("새 폴더 만들고 이름수정이 안 되네") -----

def test_rename_folder_updates_name_and_member_references():
    with _isolated_symbol_library():
        symbol_library.create_folder("무선")
        entry = symbol_library.add_symbol("증폭기", [], "", folder="무선")
        symbol_library.rename_folder("무선", "안테나")
        assert symbol_library.load_folders() == ["안테나"]
        assert symbol_library.load_library()[0]["id"] == entry["id"]
        assert symbol_library.load_library()[0]["folder"] == "안테나"   # 참조도 함께 갱신


def test_rename_folder_blank_or_unchanged_or_unknown_is_noop():
    with _isolated_symbol_library():
        symbol_library.create_folder("무선")
        symbol_library.rename_folder("무선", "   ")
        symbol_library.rename_folder("무선", "무선")
        symbol_library.rename_folder("없음", "새이름")
        assert symbol_library.load_folders() == ["무선"]


def test_rename_folder_to_existing_name_is_noop():
    with _isolated_symbol_library():
        symbol_library.create_folder("무선")
        symbol_library.create_folder("안테나")
        symbol_library.rename_folder("무선", "안테나")   # 중복 이름은 무시(호출부가 확인)
        assert symbol_library.load_folders() == ["무선", "안테나"]


def test_rename_symbol_folder_prompt_updates_library_and_refreshes_panel():
    with _isolated_symbol_library():
        w = CanvasWindow()
        with patch.object(QInputDialog, "getText", return_value=("무선", True)):
            w._prompt_create_symbol_folder()

        with patch.object(QInputDialog, "getText", return_value=("안테나", True)):
            w._rename_symbol_folder_prompt("무선")
        assert symbol_library.load_folders() == ["안테나"]


def test_rename_symbol_folder_prompt_duplicate_name_warns_and_keeps_original():
    with _isolated_symbol_library():
        w = CanvasWindow()
        with patch.object(QInputDialog, "getText", return_value=("무선", True)):
            w._prompt_create_symbol_folder()
        with patch.object(QInputDialog, "getText", return_value=("전원", True)):
            w._prompt_create_symbol_folder()

        with patch.object(QInputDialog, "getText", return_value=("전원", True)), \
                patch.object(QMessageBox, "warning") as mock_warn:
            w._rename_symbol_folder_prompt("무선")
        assert mock_warn.called
        assert symbol_library.load_folders() == ["무선", "전원"]   # 변경 없음


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
        assert symbol_library.load_library() == []   # [정책 전환 2026-08-19] 소속 심볼도 함께 삭제


def test_delete_symbol_folder_prompt_warns_with_member_count():
    # [정책 전환 2026-08-19] "미분류로 이동" 문구 대신 실제로 사라질 개수를 경고에 담는다 —
    # 되돌릴 수 없는 조작이라 "몇 개가 없어지는지"가 문구에 있어야 한다.
    with _isolated_symbol_library():
        w = CanvasWindow()
        with patch.object(QInputDialog, "getText", return_value=("무선", True)):
            w._prompt_create_symbol_folder()
        symbol_library.add_symbol("증폭기", [], "", folder="무선")
        symbol_library.add_symbol("안테나", [], "", folder="무선")

        with patch.object(QMessageBox, "question",
                           return_value=QMessageBox.StandardButton.No) as mock_q:
            w._delete_symbol_folder_prompt("무선")
        msg = mock_q.call_args[0][2]
        assert "2개" in msg
        assert "완전히 삭제" in msg
        assert symbol_library.load_folders() == ["무선"]   # No 선택 — 변경 없음


def _folder_zone_and_label(w, folder_name):
    """폴더 이름으로 `_SymbolFolderDropZone`과 그 안 제목 QLabel을 찾는다(폴더 목록 순서 —
    미분류가 항상 0번, 이후 `symbol_library.load_folders()` 순서)."""
    body = w._custom_sym_body
    zones = [body.layout().itemAt(i).widget() for i in range(body.layout().count())]
    idx = 0 if folder_name is None else 1 + symbol_library.load_folders().index(folder_name)
    zone = zones[idx]
    title_lbl = zone.layout().itemAt(0).layout().itemAt(0).widget()
    return zone, title_lbl


def test_symbol_folder_right_click_opens_rename_delete_menu():
    """[실사용 피드백 2026-08-19 재개편] 폴더 이름변경(✎)·삭제(×) 버튼 2개를 없애고 이름
    우클릭 메뉴로 통합 — 실제 배선(`customContextMenuRequested` → `_show_symbol_folder_
    context_menu`)이 걸려 있는지, 액션이 올바른 폴더를 대상으로 하는지 확인."""
    with _isolated_symbol_library():
        w = CanvasWindow()
        with patch.object(QInputDialog, "getText", return_value=("무선", True)):
            w._prompt_create_symbol_folder()
        _, title_lbl = _folder_zone_and_label(w, "무선")
        assert title_lbl.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

        created_menus = []

        class _CapturingMenu(QMenu):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                created_menus.append(self)

            def exec(self, *a, **kw):
                return None

        with patch("easycad.canvas.host_ui.QMenu", _CapturingMenu):
            title_lbl.customContextMenuRequested.emit(QPointF(1, 1).toPoint())
        assert len(created_menus) == 1
        assert [a.text() for a in created_menus[0].actions()] == ["이름변경…", "삭제…"]

        with patch.object(QInputDialog, "getText", return_value=("안테나", True)):
            created_menus[0].actions()[0].trigger()
        assert symbol_library.load_folders() == ["안테나"]


def test_unfiled_group_has_no_right_click_menu():
    """미분류는 이름변경·삭제 대상이 아니므로 우클릭 메뉴 자체가 안 걸려야 한다
    (`add_group`의 `deletable=False` 분기)."""
    with _isolated_symbol_library():
        w = CanvasWindow()
        _, title_lbl = _folder_zone_and_label(w, None)
        assert title_lbl.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu


# ---- [실사용 버그 수정 2026-08-19] 팔레트 버튼 스타일 + 썸네일 선명도 --------------------

def test_custom_symbol_button_gets_palette_accent_qss():
    # 커스텀 심볼 버튼이 `_accent_btns`(host_ui._apply_theme)에서 빠져 있어 Qt 기본 스타일의
    # raised 배경 박스로 남던 버그 — 일반 도형/심볼 버튼과 같은 스타일시트를 받는지 확인.
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        sym_id = symbol_library.load_library()[0]["id"]
        btn = w._custom_sym_buttons[sym_id][0]
        assert btn.styleSheet() == w._palette_accent_qss(w._dark)
        # 형제(기본 도형) 버튼과 완전히 같은 문자열이어야 시각적으로도 동일하게 렌더된다.
        assert btn.styleSheet() == w._shape_tool_buttons["rect"].styleSheet()


def test_custom_symbol_thumbnail_matches_palette_icon_resolution():
    # 예전엔 64px로 렌더한 뒤 팔레트가 그 PNG를 18px로 다시 스무스 축소해(이중축소) 선이
    # 서브픽셀로 사라졌다 — 이제 최종 아이콘 해상도에서 바로 렌더해 이중축소 자체가 없다.
    with _isolated_symbol_library():
        w = CanvasWindow()
        r = _mk_pen_rect(w, ww=100, hh=60); r.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        entry = symbol_library.load_library()[0]
        pm = _b64_to_pixmap(entry["thumb"])
        assert pm.width() == _PALETTE_SYM_ICON_PX and pm.height() == _PALETTE_SYM_ICON_PX


def test_custom_symbol_thumbnail_stroke_visible_for_thin_wide_symbol():
    # [실사용 버그 수정 2026-08-19] 가로로 길고 펜이 얇은(1px) 그룹은 옛 고정 최소두께
    # (씬 단위 3.0)로도 18px 아이콘에서 서브픽셀(<1px)로 사라졌다 — 목표 두께를 최종
    # 픽셀 기준으로 역산하는 새 로직이 이런 극단 비율에서도 눈에 보이는 픽셀을 남기는지
    # 직접 렌더해 확인(육안 확인은 이미 스크린샷으로 완료 — 여기선 회귀 방지용 픽셀 카운트).
    with _isolated_symbol_library():
        w = CanvasWindow()
        pen = QPen(QColor("#cdd8e3")); pen.setWidthF(1.0)
        r = _RectItem(QRectF(0, 0, 60, 40)); r.setPen(pen); r.setPos(0, 0)
        r.setFlags(r.GraphicsItemFlag.ItemIsSelectable | r.GraphicsItemFlag.ItemIsMovable)
        e = _EllipseItem(QRectF(0, 0, 30, 30)); e.setPen(pen); e.setPos(80, 10)
        e.setFlags(e.GraphicsItemFlag.ItemIsSelectable | e.GraphicsItemFlag.ItemIsMovable)
        w._scene.addItem(r); w._scene.addItem(e)
        r.setSelected(True); e.setSelected(True)
        with patch.object(QInputDialog, "getText", return_value=("증폭기", True)):
            w.register_selection_as_symbol()
        entry = symbol_library.load_library()[0]
        img = _b64_to_pixmap(entry["thumb"]).toImage()
        opaque = sum(
            1 for x in range(img.width()) for y in range(img.height())
            if img.pixelColor(x, y).alpha() > 40
        )
        total = img.width() * img.height()
        # [실측] 이 심볼(60x40+30x30, 18px 렌더)에서 새 로직은 34/324(~10.5%). 같은 box를
        # 옛 고정 최소두께(scene 3.0)로 렌더하면 21/324(~6.5%)뿐 — 0.08은 둘을 확실히
        # 가르면서 심볼마다 갈리는 실측치에는 여유를 둔 문턱값.
        assert opaque / total > 0.08, f"expected a clearly visible icon, got {opaque}/{total} opaque px"


# ---- [실사용 피드백 2026-08-19] 커스텀 심볼 클릭-드래그 비율고정 크기조절 --------------------

def _place_customsym_via_mouse(view, tool_key, start, end=None, shift=False):
    """press(→move→release)로 커스텀 심볼 배치를 시뮬레이트. end가 None이면 순수 클릭(드래그 없음)."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    mods = Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier

    def _ev(etype, sp, buttons):
        vp = QPointF(view.mapFromScene(sp))
        return QMouseEvent(etype, vp, vp, Qt.MouseButton.LeftButton, buttons, mods)

    NB = Qt.MouseButton.NoButton
    L = Qt.MouseButton.LeftButton
    view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, start, L))
    release_pt = start if end is None else end
    if end is not None:
        view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, end, L))
    view.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, release_pt, NB))


def _register_two_shape_symbol(w, name="드래그심볼"):
    r = _mk_pen_rect(w, x=0, y=0, ww=60, hh=40)
    e = _EllipseItem(QRectF(0, 0, 30, 30)); e.setPos(80, 10)
    e.setFlags(e.GraphicsItemFlag.ItemIsSelectable | e.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(e)
    r.setSelected(True); e.setSelected(True)
    with patch.object(QInputDialog, "getText", return_value=(name, True)):
        w.register_selection_as_symbol()
    sym_id = symbol_library.load_library()[0]["id"]
    w._scene.clear()
    return sym_id


def test_customsym_click_without_drag_arms_two_click_mode():
    # [실사용 피드백 2026-08-19, "1번 방식" 추가] rect/ellipse/sym:와 동일하게, 드래그 없는
    # 클릭은 즉시 배치가 아니라 클릭-클릭 배치 모드로 전환한다 — 옛 "단발 클릭=즉시
    # 기본크기 배치" 관례는 일관성을 위해 폐지됐다(사용자 선택).
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        w.set_tool(f"customsym:{sym_id}")
        view = w._view
        u0 = len(w._undo)

        _place_customsym_via_mouse(view, sym_id, QPointF(0, 0))

        assert view._csym_drag is not None and view._csym_drag["armed"]
        assert len(w._undo) == u0   # 아직 확정 전 — undo에 안 남음

        # 움직임 없이 같은 자리에서 다시 클릭 = rect/ellipse의 '점 하나' 퇴화와 동일하게 폐기.
        from PyQt6.QtCore import QEvent
        L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
        view.mousePressEvent(_csym_ev(view, QEvent.Type.MouseButtonPress, QPointF(0, 0), L, L))
        view.mouseReleaseEvent(_csym_ev(view, QEvent.Type.MouseButtonRelease, QPointF(0, 0), NB, NB))

        assert view._csym_drag is None
        assert not [it for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem))]
        assert len(w._undo) == u0


def test_customsym_drag_scales_uniformly_and_undoes_as_one_group():
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        _, box0 = w._build_custom_symbol_items(sym_id)
        import math
        diag0 = math.hypot(box0.width(), box0.height())

        w.set_tool(f"customsym:{sym_id}")
        u0 = len(w._undo)
        start = QPointF(200, 200)
        end = QPointF(start.x() + diag0 * 2.0, start.y())   # 대각선 2배 거리만큼 드래그
        _place_customsym_via_mouse(w._view, sym_id, start, end)

        assert w._view._csym_drag is None
        placed = [it for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem))]
        assert len(placed) == 2
        new_r = next(it for it in placed if isinstance(it, _RectItem))
        new_e = next(it for it in placed if isinstance(it, _EllipseItem))
        assert abs(new_r.scale() - 2.0) < 0.05
        assert abs(new_e.scale() - 2.0) < 0.05   # 비율 고정 — 그룹 전체가 같은 배율
        # 앵커(box0 좌상단)는 press 지점 그대로 — 패딩(eps=3.0)이 스케일(2배)만큼도 커지므로 여유를 둔다.
        assert _close(new_r.pos(), start, eps=6.0)
        assert len(w._undo) == u0 + 1   # 드래그 전체가 undo 1스텝

        gids = {getattr(it, "_group_id", None) for it in placed}
        assert len(gids) == 1 and None not in gids

        w.undo()
        assert not [it for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem))]


def test_customsym_tiny_jitter_click_arms_instead_of_finalizing():
    # [실사용 버그 방지 2026-08-19] moved<4 판정은 press~release 거리만 본다 — 그 사이에
    # 손떨림 같은 미세한 mouseMoveEvent(예: 2px)가 껴도 "그냥 클릭"과 동일하게 클릭-클릭
    # 배치 모드로 전환돼야 한다(즉시 확정되면 안 됨).
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        w.set_tool(f"customsym:{sym_id}")
        view = w._view

        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent
        NO = Qt.KeyboardModifier.NoModifier
        L = Qt.MouseButton.LeftButton
        NB = Qt.MouseButton.NoButton

        def _ev(etype, sp, btn, btns):
            vp = QPointF(view.mapFromScene(sp))
            return QMouseEvent(etype, vp, vp, btn, btns, NO)

        start = QPointF(0, 0)
        jitter = QPointF(2, 1)   # 4px 미만 — moved<4 임계 안쪽
        u0 = len(w._undo)
        view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, start, L, L))
        view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, jitter, NB, L))
        view.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, jitter, NB, NB))

        assert view._csym_drag is not None and view._csym_drag["armed"]
        assert len(w._undo) == u0


def test_customsym_drag_scale_grows_smoothly_without_flicker():
    # [실사용 버그 수정 2026-08-19] 예전엔 press에서 바로 기본크기(scale=1)로 놓은 뒤 첫
    # move에서 공식(dist≈0 → 최소치)이 적용돼 "기본크기로 반짝했다가 줄어드는" 깜빡임이
    # 있었다 — press 시점부터 최소크기에서 시작해 드래그 내내 단조증가해야 한다.
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        w.set_tool(f"customsym:{sym_id}")
        view = w._view

        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent
        NO = Qt.KeyboardModifier.NoModifier
        L = Qt.MouseButton.LeftButton
        NB = Qt.MouseButton.NoButton

        def _ev(etype, sp, btn, btns):
            vp = QPointF(view.mapFromScene(sp))
            return QMouseEvent(etype, vp, vp, btn, btns, NO)

        start = QPointF(0, 0)
        view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, start, L, L))
        r_item = next(it for it in view._csym_drag["items"] if isinstance(it, _RectItem))
        scales = [r_item.scale()]
        assert scales[0] < 0.2, f"press should start near-minimum scale, not default(1.0), got {scales[0]}"

        for step in range(1, 11):
            pt = QPointF(start.x() + step * 12, start.y())
            view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, pt, NB, L))
            scales.append(r_item.scale())
        assert all(b >= a - 1e-9 for a, b in zip(scales, scales[1:])), \
            f"scale must grow monotonically (no flicker/dip): {scales}"
        view.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, pt, NB, NB))


def test_customsym_button_thumbnail_self_heals_from_old_64px_format():
    # [실사용 버그 수정 2026-08-19] 2026-08-19 이전(구 포맷, 64px 이중축소)에 등록된 심볼도
    # 재등록 없이 팔레트를 다시 그릴 때 자동으로 최신 포맷(18px, 직접렌더)으로 화면엔 치유돼
    # 보인다. 실제 사용자 파일(37898900 "46")에서 재현됐던 버그의 회귀 테스트.
    # [실사용 회귀 수정 2026-08-19] 디스크 영구저장(symbol_library.update_symbol_thumb)은
    # 전체 스모크에서 무관한 다른 테스트를 간헐 실패시켜(동기 파일쓰기가 Qt 이벤트 타이밍을
    # 건드림, host_selection._ensure_symbol_thumb_current 참조) 포기했다 — 그래서 이 테스트는
    # 디스크가 아니라 인메모리 결과(팔레트 버튼에 실제로 걸리는 아이콘)를 확인한다.
    with _isolated_symbol_library():
        w0 = CanvasWindow()
        r = _mk_pen_rect(w0, ww=100, hh=60)
        item_dicts = [item_to_dict(r)]
        entry = symbol_library.add_symbol("옛심볼", item_dicts, "")
        assert entry["thumb"] == ""   # 구 데이터를 흉내(빈 문자열 = _b64_to_pixmap이 0x0 취급)

        healed = w0._ensure_symbol_thumb_current(entry)
        pm = _b64_to_pixmap(healed["thumb"])
        assert pm.width() == _PALETTE_SYM_ICON_PX and pm.height() == _PALETTE_SYM_ICON_PX
        assert symbol_library.load_library()[0]["thumb"] == ""   # 디스크는 의도적으로 그대로

        # 팔레트 버튼 자체도 (디스크가 아니라) 이 인메모리 치유 결과로 아이콘을 그린다.
        w0._refresh_custom_symbol_section()
        btn = w0._custom_sym_buttons[entry["id"]][0]
        assert not btn.icon().isNull()


def test_customsym_right_click_cancel_removes_preview_items():
    # 드래그 도중 우클릭 취소 — 씬에 미리 넣어둔 프리뷰 아이템이 고아로 남지 않아야 한다.
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        w.set_tool(f"customsym:{sym_id}")
        view = w._view
        u0 = len(w._undo)

        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent
        NO = Qt.KeyboardModifier.NoModifier
        L = Qt.MouseButton.LeftButton

        def _ev(etype, sp, btn, btns):
            vp = QPointF(view.mapFromScene(sp))
            return QMouseEvent(etype, vp, vp, btn, btns, NO)

        view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, QPointF(0, 0), L, L))
        assert view._csym_drag is not None
        assert view._rmb_is_busy()
        view._right_click_cancel()

        assert view._csym_drag is None
        assert not [it for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem))]
        assert len(w._undo) == u0   # 폐기된 배치는 undo에 안 남는다
        assert w.current_tool == "select"


# ---- [실사용 피드백 2026-08-19] 커스텀 심볼 클릭-클릭(드래그 없는 두 번 클릭) 배치 ------------

def _csym_ev(view, etype, sp, btn, btns, mods=Qt.KeyboardModifier.NoModifier):
    from PyQt6.QtGui import QMouseEvent
    vp = QPointF(view.mapFromScene(sp))
    return QMouseEvent(etype, vp, vp, btn, btns, mods)


def test_customsym_two_click_placement_scales_via_idle_move():
    # rect/ellipse/sym:와 동일한 "클릭 → 버튼 안 눌러도 이동 → 다시 클릭" 워크플로가
    # 커스텀 심볼(그룹)에도 동작하는지 — 특히 버튼을 안 누른 상태의 mouseMoveEvent가
    # 라이브 스케일을 갱신하는지가 핵심(기존 드래그 경로와 다른 코드 분기).
    with _isolated_symbol_library():
        from PyQt6.QtCore import QEvent
        import math
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        _, box0 = w._build_custom_symbol_items(sym_id)
        diag0 = math.hypot(box0.width(), box0.height())
        w.set_tool(f"customsym:{sym_id}")
        view = w._view
        u0 = len(w._undo)
        L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

        start = QPointF(0, 0)
        view.mousePressEvent(_csym_ev(view, QEvent.Type.MouseButtonPress, start, L, L))
        view.mouseReleaseEvent(_csym_ev(view, QEvent.Type.MouseButtonRelease, start, NB, NB))
        assert view._csym_drag is not None and view._csym_drag["armed"]

        far = QPointF(diag0 * 1.5, 0)
        view.mouseMoveEvent(_csym_ev(view, QEvent.Type.MouseMove, far, NB, NB))   # 버튼 안 누름
        r_item = next(it for it in view._csym_drag["items"] if isinstance(it, _RectItem))
        assert 1.3 < r_item.scale() < 1.7

        view.mousePressEvent(_csym_ev(view, QEvent.Type.MouseButtonPress, far, L, L))
        assert view._csym_drag is None
        view.mouseReleaseEvent(_csym_ev(view, QEvent.Type.MouseButtonRelease, far, NB, NB))

        placed = [it for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem))]
        assert len(placed) == 2
        assert len(w._undo) == u0 + 1


def test_customsym_two_click_escape_cancels_without_undo():
    with _isolated_symbol_library():
        from PyQt6.QtCore import QEvent
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        w.set_tool(f"customsym:{sym_id}")
        view = w._view
        u0 = len(w._undo)
        L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

        start = QPointF(0, 0)
        view.mousePressEvent(_csym_ev(view, QEvent.Type.MouseButtonPress, start, L, L))
        view.mouseReleaseEvent(_csym_ev(view, QEvent.Type.MouseButtonRelease, start, NB, NB))
        assert view._csym_drag is not None and view._csym_drag["armed"]

        view.keyPressEvent(_EscapeKeyEvent())

        assert view._csym_drag is None
        assert not [it for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem))]
        assert len(w._undo) == u0


def test_customsym_two_click_enter_confirms_current_scale():
    with _isolated_symbol_library():
        from PyQt6.QtCore import QEvent
        import math
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        _, box0 = w._build_custom_symbol_items(sym_id)
        diag0 = math.hypot(box0.width(), box0.height())
        w.set_tool(f"customsym:{sym_id}")
        view = w._view
        u0 = len(w._undo)
        L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

        start = QPointF(0, 0)
        view.mousePressEvent(_csym_ev(view, QEvent.Type.MouseButtonPress, start, L, L))
        view.mouseReleaseEvent(_csym_ev(view, QEvent.Type.MouseButtonRelease, start, NB, NB))
        far = QPointF(diag0, 0)
        view.mouseMoveEvent(_csym_ev(view, QEvent.Type.MouseMove, far, NB, NB))

        view.keyPressEvent(_EnterKeyEvent())

        assert view._csym_drag is None
        placed = [it for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem))]
        assert len(placed) == 2
        new_r = next(it for it in placed if isinstance(it, _RectItem))
        assert abs(new_r.scale() - 1.0) < 0.05
        assert len(w._undo) == u0 + 1


def test_customsym_two_click_tool_switch_cancels_pending_placement():
    with _isolated_symbol_library():
        from PyQt6.QtCore import QEvent
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        w.set_tool(f"customsym:{sym_id}")
        view = w._view
        u0 = len(w._undo)
        L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

        start = QPointF(0, 0)
        view.mousePressEvent(_csym_ev(view, QEvent.Type.MouseButtonPress, start, L, L))
        view.mouseReleaseEvent(_csym_ev(view, QEvent.Type.MouseButtonRelease, start, NB, NB))
        assert view._csym_drag is not None and view._csym_drag["armed"]

        w.set_tool("select")   # [실사용 피드백 2026-08-19] 단축키 등으로 도구 전환

        assert view._csym_drag is None
        assert not [it for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem))]
        assert len(w._undo) == u0


def _EscapeKeyEvent():
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)


def _EnterKeyEvent():
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)


# ---- [실사용 피드백 2026-08-19] 호버 확대 미리보기 — "46번 아이콘이 뭔 그림인지 안 보임" ---

def test_symbol_preview_html_embeds_larger_render_than_palette_icon():
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        entry = symbol_library.load_library()[0]
        html_out = w._symbol_preview_html(entry)
        assert "드래그심볼" in html_out
        assert '<img src="data:image/png;base64,' in html_out
        b64 = html_out.split("base64,", 1)[1].split('"', 1)[0]
        pm = _b64_to_pixmap(b64)
        # 팔레트 아이콘(_PALETTE_SYM_ICON_PX)보다 훨씬 큰 해상도로 다시 렌더해야 한다 —
        # 그래야 다중 도형(2개+) 조합의 형태가 확대해서 구분된다.
        assert pm.width() > _PALETTE_SYM_ICON_PX * 2


def test_symbol_preview_html_escapes_name():
    with _isolated_symbol_library():
        entry = symbol_library.add_symbol("<b>위험</b>", [], "")
        w = CanvasWindow()
        html_out = w._symbol_preview_html(entry)
        assert "<b>위험</b>" not in html_out
        assert "&lt;b&gt;" in html_out


def test_custom_symbol_button_uses_lazy_tooltip_not_precomputed_at_refresh():
    """[실사용 피드백 2026-08-19] "심볼이 많아지면?" 확장성 우려에 대한 답 — 새로고침 시점엔
    아무 것도 안 그리고, 실제 호버(QEvent.ToolTip)가 일어날 때만 큰 미리보기를 계산한다.
    버튼의 정적 QToolTip은 비워두고, 지연 콜백만 들고 있는지로 이를 검증한다."""
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        btn = w._custom_sym_buttons[sym_id][0]
        assert btn.toolTip() == ""
        assert btn._tooltip_html_fn is not None
        assert "드래그심볼" in btn._tooltip_html_fn()


def test_custom_symbol_icon_size_at_least_matches_base_shape_icon():
    # [실사용 피드백 2026-08-19] "심볼 아이콘이 최소한 기본도형만큼은 나오게" — 커스텀 심볼
    # 버튼의 아이콘 픽셀 크기가 기본도형 버튼과 같거나 커야 한다.
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        custom_icon_size = w._custom_sym_buttons[sym_id][0].iconSize()
        base_icon_size = w._shape_tool_buttons["rect"].iconSize()
        assert custom_icon_size.width() >= base_icon_size.width()
        assert custom_icon_size.height() >= base_icon_size.height()


def test_custom_symbol_button_dispatches_real_qevent_tooltip_to_qtooltip_showtext():
    """단위 테스트는 지금까지 `btn._tooltip_html_fn()`을 직접 호출해 콜백 내용만 검증했다 —
    여기서는 실제 `QEvent.ToolTip`을 `event()`에 흘려 Qt 배선 자체(`QToolTip.showText` 호출)
    까지 확인한다. 기본도형 버튼은 정적 tooltip 경로 그대로라 이 배선을 안 타는지도 함께."""
    from PyQt6.QtCore import QEvent, QPoint
    from PyQt6.QtGui import QHelpEvent

    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        btn = w._custom_sym_buttons[sym_id][0]
        ev = QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), QPoint(10, 10))
        with patch("easycad.canvas.host_widgets.QToolTip.showText") as mock_show:
            handled = btn.event(ev)
        assert handled is True
        assert mock_show.called
        assert "드래그심볼" in mock_show.call_args.args[1]

        base_btn = w._shape_tool_buttons["rect"]
        ev2 = QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), QPoint(10, 10))
        with patch("easycad.canvas.host_widgets.QToolTip.showText") as mock_show2:
            base_btn.event(ev2)
        assert not mock_show2.called   # 기본도형은 정적 setToolTip 경로 그대로


# ---- [신규기능, 2026-08-20, deep-interview] '내 심볼' 즐겨찾기 -------------------------
# 확정 스코프: favorite 불리언 필드(folder와 같은 패턴, 별도 id목록 아님) · UI 위치는 '내
# 심볼' 최상단(미분류보다 위) · 표시방식은 이중표시(원래 폴더+즐겨찾기 둘 다) · 폴더
# 완전삭제 시 자동 정리(별도 코드 불필요, entry 자체가 지워지므로) · 우클릭 메뉴는 토글
# 액션 1개 · 드래그 대상 아님(우클릭 전용).

def test_add_symbol_defaults_favorite_false():
    with _isolated_symbol_library():
        entry = symbol_library.add_symbol("증폭기", [], "")
        assert entry["favorite"] is False
        assert symbol_library.load_library()[0]["favorite"] is False


def test_toggle_favorite_sets_and_unsets_flag():
    with _isolated_symbol_library():
        entry = symbol_library.add_symbol("증폭기", [], "")
        symbol_library.toggle_favorite(entry["id"])
        assert symbol_library.load_library()[0]["favorite"] is True
        symbol_library.toggle_favorite(entry["id"])
        assert symbol_library.load_library()[0]["favorite"] is False


def test_toggle_favorite_unknown_id_is_noop():
    with _isolated_symbol_library():
        symbol_library.add_symbol("증폭기", [], "")
        symbol_library.toggle_favorite("doesnotexist")
        assert symbol_library.load_library()[0]["favorite"] is False


def test_delete_folder_drops_favorited_member_from_favorites_too():
    # favorite는 심볼 엔트리 자체의 필드라 폴더 완전삭제(2026-08-19 정책) 시 별도 정리
    # 코드 없이 엔트리와 함께 자동으로 사라진다 — deep-interview에서 확정한 전제 검증.
    with _isolated_symbol_library():
        symbol_library.create_folder("무선")
        entry = symbol_library.add_symbol("증폭기", [], "", folder="무선")
        symbol_library.toggle_favorite(entry["id"])
        symbol_library.delete_folder("무선")
        assert symbol_library.load_library() == []


def test_favorites_dual_display_button_count_tracks_toggle():
    # 즐겨찾기 안 된 상태 = 원래 폴더(미분류) 버튼 1개. 즐겨찾기하면 이중표시로 2개
    # (미분류+즐겨찾기 섹션)가 되고, 해제하면 다시 1개로 돌아온다.
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        assert len(w._custom_sym_buttons[sym_id]) == 1

        w._toggle_custom_symbol_favorite(sym_id)
        assert len(w._custom_sym_buttons[sym_id]) == 2

        w._toggle_custom_symbol_favorite(sym_id)
        assert len(w._custom_sym_buttons[sym_id]) == 1


def test_favorites_group_absent_from_panel_when_empty():
    # 즐겨찾기 섹션은 항목이 하나도 없으면 아예 그려지지 않는다(add_group의 early return).
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        body_count_before = w._custom_sym_body.layout().count()   # 미분류 1개 그룹뿐

        w._toggle_custom_symbol_favorite(sym_id)
        body_count_after = w._custom_sym_body.layout().count()   # 즐겨찾기+미분류 2개 그룹
        assert body_count_after == body_count_before + 1

        w._toggle_custom_symbol_favorite(sym_id)
        assert w._custom_sym_body.layout().count() == body_count_before


def test_set_tool_syncs_checked_state_across_dual_display_buttons():
    # host_canvas.set_tool이 sid당 버튼 전부(이중표시 2개)의 체크상태를 함께 동기화하는지.
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        w._toggle_custom_symbol_favorite(sym_id)
        assert len(w._custom_sym_buttons[sym_id]) == 2

        w.set_tool(f"customsym:{sym_id}")
        assert all(b.isChecked() for b in w._custom_sym_buttons[sym_id])

        w.set_tool("select")
        assert not any(b.isChecked() for b in w._custom_sym_buttons[sym_id])


def test_context_menu_favorite_action_label_toggles_with_state():
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)

        created_menus = []

        class _CapturingMenu(QMenu):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                created_menus.append(self)

            def exec(self, *a, **kw):
                return None

        btn = w._custom_sym_buttons[sym_id][0]
        with patch("easycad.canvas.host_ui.QMenu", _CapturingMenu):
            w._show_custom_symbol_context_menu(btn, QPointF(1, 1).toPoint(), sym_id)
        assert [a.text() for a in created_menus[0].actions()][0] == "즐겨찾기 추가"

        w._toggle_custom_symbol_favorite(sym_id)
        created_menus.clear()
        btn = w._custom_sym_buttons[sym_id][0]
        with patch("easycad.canvas.host_ui.QMenu", _CapturingMenu):
            w._show_custom_symbol_context_menu(btn, QPointF(1, 1).toPoint(), sym_id)
        assert [a.text() for a in created_menus[0].actions()][0] == "즐겨찾기 해제"


def test_context_menu_toggle_action_invokes_toggle_favorite():
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        btn = w._custom_sym_buttons[sym_id][0]

        with patch("easycad.canvas.host_ui.QMenu.exec", return_value=None):
            w._show_custom_symbol_context_menu(btn, QPointF(1, 1).toPoint(), sym_id)
            # exec()는 no-op이라 메뉴가 실제로 안 뜨므로, 핸들러를 직접 호출해 배선 확인.
            w._toggle_custom_symbol_favorite(sym_id)
        assert symbol_library.load_library()[0]["favorite"] is True


def test_favorites_zone_is_not_a_symbol_folder_drop_target():
    # deep-interview 확정: 즐겨찾기 섹션은 드롭 대상이 아니라 우클릭 전용 — 다른 폴더처럼
    # _SymbolFolderDropZone(acceptDrops=True)로 감싸지 않는다.
    with _isolated_symbol_library():
        w = CanvasWindow()
        sym_id = _register_two_shape_symbol(w)
        w._toggle_custom_symbol_favorite(sym_id)
        zones = [w._custom_sym_body.layout().itemAt(i).widget()
                 for i in range(w._custom_sym_body.layout().count())]
        drop_zones = [z for z in zones if z.acceptDrops()]
        # 즐겨찾기(비-드롭) + 미분류(드롭) 2그룹 중 드롭 가능한 건 미분류 하나뿐.
        assert len(zones) == 2
        assert len(drop_zones) == 1
