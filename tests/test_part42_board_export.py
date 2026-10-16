"""§8 항목53 3단계 보드 막대·「내보내기」(2026-10-16) — 보드 하나를 고르면 위에 막대(색·내보내기),
내보내기 = 그림 복사·PNG·PDF 한 쪽(A3 가로)·HTML을 보드 범위로, 출력은 늘 흰 종이.
"""
import os
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

import fitz
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication, QToolButton

from easycad.canvas.annotator_core import _RectItem, BOARD_ASPECT


def _setup():
    w = CanvasWindow()
    w.resize(1600, 950)
    w.show()
    _app.processEvents()
    board = w._insert_board()
    inside = _RectItem(QRectF(0, 0, 200, 100))
    inside.setPen(w.make_pen())
    inside.setPos(board.pos() + QPointF(200, 200))
    inside.setFlags(inside.GraphicsItemFlag.ItemIsMovable | inside.GraphicsItemFlag.ItemIsSelectable)
    w._scene.addItem(inside)
    inside.ensure_label().setPlainText("안")
    w.push_undo_add(inside)
    outside = _RectItem(QRectF(0, 0, 200, 100))
    outside.setPen(w.make_pen())
    outside.setPos(board.mapRectToScene(board.rect()).topRight() + QPointF(300, 0))
    w._scene.addItem(outside)
    outside.ensure_label().setPlainText("밖")
    w.push_undo_add(outside)
    return w, board, inside, outside


def _close(w):
    for d in w._docs:
        d.dirty = False
    w.close()


def test_bar_shows_only_for_one_selected_board():
    w, board, inside, _out = _setup()
    w._scene.clearSelection()
    board.setSelected(True)
    w._board_bar_sync(w._view)
    bar = w._board_bar
    assert bar.isVisible() and bar.board is board
    texts = [b.text() for b in bar.findChildren(QToolButton)]
    assert "내보내기 ▾" in texts and "화이트" in texts and "블랙" in texts
    assert [a.text().split("  —  ")[0] for a in bar.export_menu.actions()] == ["그림으로 복사", "PNG 그림 파일", "PDF 한 쪽", "HTML 공유"]
    inside.setSelected(True)                       # 둘을 고르면 숨김
    w._board_bar_sync(w._view)
    assert not bar.isVisible()
    w._scene.clearSelection()
    w._board_bar_sync(w._view)
    assert not bar.isVisible()
    _close(w)


def test_bar_color_button_changes_board():
    w, board, inside, _out = _setup()
    w._scene.clearSelection()
    board.setSelected(True)
    w._board_bar_sync(w._view)
    black = [b for b in w._board_bar.findChildren(QToolButton) if b.text() == "블랙"][0]
    black.click()
    assert board.is_dark() and inside.pen().color().name() == "#fafafa"
    _close(w)


def test_export_copy_and_png_cover_board_only(tmp_path):
    w, board, _in, _out = _setup()
    w._set_board_color(board, "#24382f")
    w._scene.clearSelection()
    assert w._board_export(board, "copy") is True
    img = QApplication.clipboard().image()
    assert abs(img.width() / img.height() - BOARD_ASPECT) < 0.02    # 보드 밖 상자는 안 들어감(넣었으면 옆으로 길어짐)
    assert img.pixelColor(img.width() // 2, 4).name() == "#ffffff"   # 칠판색 보드도 흰 종이
    path = w._board_export(board, "png", path=str(tmp_path / "b.png"))
    assert path and os.path.getsize(path) > 0
    assert board.bg().name() == "#24382f" and w._scene.selectedItems() == []   # 색·선택 되돌림
    _close(w)


def test_export_pdf_is_one_a3_landscape_page(tmp_path):
    w, board, _in, _out = _setup()
    path = w._board_export(board, "pdf", path=str(tmp_path / "b.pdf"))
    with fitz.open(path) as doc:
        assert doc.page_count == 1
        r = doc[0].rect
        assert abs(r.width - 1191) < 2 and abs(r.height - 842) < 2      # A3 가로(pt)
    _close(w)


def test_export_html_only_board(tmp_path):
    w, board, _in, _out = _setup()
    path = w._board_export(board, "html", path=str(tmp_path / "b.html"), open_after=False)
    html = open(path, encoding="utf-8").read()
    assert '"안"' in html and '"밖"' not in html
    _close(w)


def test_export_cancel_and_context_menu():
    w, board, _in, _out = _setup()
    with _patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")):
        assert w._board_export(board, "png") is None
    w._scene.clearSelection()
    board.setSelected(True)
    menu = w._build_context_menu()
    sub = [a.menu() for a in menu.actions() if a.menu() is not None and a.text() == "보드 내보내기"]
    assert sub and [a.text() for a in sub[0].actions()] == ["그림으로 복사", "PNG 그림 파일", "PDF 한 쪽", "HTML 공유"]
    _close(w)
