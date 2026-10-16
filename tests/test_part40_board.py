"""§8 항목53 1단계 보드 틀(2026-10-16) — 16:9 틀, 끌면 안의 것도 같이, 잉크 맞추기, 보드 색, 출력은 흰 종이.

- `core_shapes._BoardItem` / `_board_members` — 소속은 위치(가운데가 안에 있으면), 끌 때만 같이 움직임.
- `host_board._BoardMixin` — 「삽입 › 보드」, 보드 위 잉크 맞추기(`_push_entry` 길목, 같은 기록 칸), 「보드 색」.
- `pdf_export._swap_white_to_black_for_print` — 보드 바탕은 출력 동안 흰색, 밝은 잉크는 검정.
"""
from _shared import *  # noqa: F401,F403

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest

from easycad.canvas.annotator_core import _BoardItem, _RectItem, _PolyArrowItem, BOARD_ASPECT
from easycad.canvas.host_board import INK_ON_DARK, INK_ON_LIGHT
from easycad.fileio.pdf_export import _restore_swapped_colors, _swap_white_to_black_for_print


def _window(dark=True):
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    _app.processEvents()
    if w._dark != dark:
        w._toggle_theme()
    return w


def _close(w):
    for d in w._docs:
        d.dirty = False
    w.close()


def _rect(w, board, dx, dy, text="상자"):
    r = _RectItem(QRectF(0, 0, 160, 80))
    r.setPen(w.make_pen())
    r.setPos(board.pos() + QPointF(dx, dy))
    r.setFlags(r.GraphicsItemFlag.ItemIsMovable | r.GraphicsItemFlag.ItemIsSelectable)
    w._scene.addItem(r)
    r.ensure_label().setPlainText(text)
    w.push_undo_add(r)
    return r


def test_insert_board_is_16_9_white_behind_content():
    w = _window()
    other = _RectItem(QRectF(0, 0, 10, 10))
    w._scene.addItem(other)
    b = w._insert_board()
    r = b.rect()
    assert abs(r.width() / r.height() - BOARD_ASPECT) < 1e-6 and b.bg().name() == "#ffffff"
    assert b.zValue() < other.zValue() and b.isSelected() and w._undo[-1].ops[0][1] is b
    _close(w)


def test_drawing_on_board_fixes_ink_in_same_undo_step():
    w = _window(dark=True)                       # 다크 화면 기본 잉크 = 흰색 → 흰 보드 위에선 안 보임
    b = w._insert_board()
    n = len(w._undo)
    r = _rect(w, b, 100, 100)
    assert r.pen().color().name() == INK_ON_LIGHT and r._label.defaultTextColor().name() == INK_ON_LIGHT
    assert len(w._undo) == n + 1                 # 넣기와 잉크 맞추기가 한 칸
    outside = _rect(w, b, -400, 0)
    assert outside.pen().color().name() == "#ffffff"   # 보드 밖은 그대로
    w.undo()
    assert outside.scene() is None and r.pen().color().name() == INK_ON_LIGHT
    w.undo()
    assert r.scene() is None
    _close(w)


def test_meaningful_colors_are_left_alone():
    w = _window()
    b = w._insert_board()
    r = _RectItem(QRectF(0, 0, 100, 50))
    r.setPen(QColor("#4a8fd9"))
    r.setPos(b.pos() + QPointF(50, 50))
    w._scene.addItem(r)
    w.push_undo_add(r)
    assert r.pen().color().name() == "#4a8fd9"
    _close(w)


def test_board_color_change_recolors_ink_and_undoes_together():
    w = _window()
    b = w._insert_board()
    r = _rect(w, b, 100, 100)
    w._set_board_color(b, "#24382f")
    assert b.bg().name() == "#24382f" and b.is_dark()
    assert r.pen().color().name() == INK_ON_DARK and r._label.defaultTextColor().name() == INK_ON_DARK
    w.undo()
    assert b.bg().name() == "#ffffff" and r.pen().color().name() == INK_ON_LIGHT
    menu = w._build_board_color_menu(b)
    names = [a.text() for a in menu.actions()]
    assert names[:2] == ["화이트", "블랙"] and "다른 색" in names
    sub = [a for a in menu.actions() if a.menu() is not None][0].menu()
    assert len([a for a in sub.actions() if not a.isSeparator()]) == 9   # 견본 8 + 직접 고르기
    _close(w)


def test_dragging_board_moves_members_and_one_undo_restores():
    w = _window()
    b = w._insert_board()
    inside = _rect(w, b, 300, 300)
    outside = _rect(w, b, -500, 0)
    b2_from = QPointF(b.pos())
    in_from, out_from = QPointF(inside.pos()), QPointF(outside.pos())
    view = w._view
    view.fitInView(b.sceneBoundingRect().adjusted(-600, -100, 100, 100), Qt.AspectRatioMode.KeepAspectRatio)
    _app.processEvents()
    w._scene.clearSelection()
    start = view.mapFromScene(b.mapToScene(b.rect().topLeft()) + QPointF(1200, 700))   # 보드 빈 곳
    vp = view.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for i in range(1, 6):
        QTest.mouseMove(vp, start + QPoint(20 * i, 10 * i))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start + QPoint(100, 50))
    _app.processEvents()
    d = b.pos() - b2_from
    assert d.manhattanLength() > 10
    assert (inside.pos() - in_from - d).manhattanLength() < 0.5      # 안의 것은 같이
    assert (outside.pos() - out_from).manhattanLength() < 0.5        # 밖의 것은 그대로
    w.undo()
    assert (b.pos() - b2_from).manhattanLength() < 0.5 and (inside.pos() - in_from).manhattanLength() < 0.5
    _close(w)


def test_members_skip_bound_arrows_and_other_boards():
    from easycad.canvas.annotator_core import _board_members
    w = _window()
    b = w._insert_board()
    a1, a2 = _rect(w, b, 100, 100), _rect(w, b, 500, 100)
    arr = _PolyArrowItem(QColor("white"), 2.0)
    arr.set_points(a1.mapToScene(QPointF(160, 40)), a2.mapToScene(QPointF(0, 40)))
    arr.set_bound(0, a1, QPointF(160, 40))
    w._scene.addItem(arr)
    small = w._insert_board()
    small.setPos(b.pos() + QPointF(200, 200))
    w._scene.clearSelection()
    m = _board_members(b)
    assert a1 in m and a2 in m and arr not in m and small not in m
    _close(w)


def test_export_prints_board_on_white_paper():
    w = _window()
    b = w._insert_board()
    r = _rect(w, b, 100, 100)
    w._set_board_color(b, "#1e2b45")
    swapped = _swap_white_to_black_for_print(w._scene)
    try:
        assert b.bg().name() == "#ffffff"
        assert r.pen().color().name() == "#000000"                    # 밝은 잉크 → 검정
    finally:
        _restore_swapped_colors(swapped)
    assert b.bg().name() == "#1e2b45" and r.pen().color().name() == INK_ON_DARK
    _close(w)


def test_board_save_load_roundtrip(tmp_path):
    from easycad.fileio.document import load_document, save_document
    w = _window()
    b = w._insert_board()
    w._set_board_color(b, "#dde9f3")
    path = str(tmp_path / "b.ecad")
    save_document(w._scene, path)
    w2 = _window()
    load_document(w2._scene, path)
    boards = [it for it in w2._scene.items() if isinstance(it, _BoardItem)]
    assert len(boards) == 1 and boards[0].bg().name() == "#dde9f3"
    assert boards[0].rect() == b.rect() and boards[0].zValue() == b.zValue()
    _close(w)
    _close(w2)


def test_board_resize_keeps_16_9():
    b = _BoardItem(QRectF(0, 0, 1600, 900))
    b._box_orig_rect = QRectF(b.rect())
    r = b._constrain_box_rect(QRectF(0, 0, 2000, 950), "corner", 2)
    assert abs(r.width() / r.height() - BOARD_ASPECT) < 1e-6
    r = b._constrain_box_rect(QRectF(0, 0, 1600, 1200), "edge", "b")
    assert abs(r.width() / r.height() - BOARD_ASPECT) < 1e-6


def test_insert_menu_and_toolbar_have_board():
    w = _window()
    assert w._act_board.iconText() == "보드"
    assert any(a is w._act_board for a in w.findChildren(type(w._act_board)))
    _close(w)
