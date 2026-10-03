"""§8 항목30(2026-10-03) — 여러 페이지(용지틀)를 PDF 1개의 여러 쪽으로.

사용자 결정: PDF 1개 여러 쪽 · 캔버스 배치 순서(왼쪽 위부터) · 체크로 고르기(기본 전부) · PDF만.
PDF를 열어 쪽 수·용지 크기를 재는 테스트는 PyMuPDF(fitz)가 있는 PC에서만 돈다(requirements 밖)."""
import os
import uuid
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QDialog, QFileDialog, QGraphicsScene, QMessageBox

from _shared import *  # noqa: F401,F403

from easycad.canvas.host_dialogs import _PdfExportDialog
from easycad.fileio.pdf_export import _list_title_frames, _reading_order, export_pdf_pages


def _tmp(name):
    d = os.path.join(_TMP, f"mpdf_{uuid.uuid4().hex}")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _three_frames(scene):
    """1번 A3 가로(왼쪽 위) · 2번 A4 세로(오른쪽 위) · 3번 A4 가로(아랫줄). 추가 순서는 일부러 뒤섞음."""
    out = {}
    for size, orient, pos, label in (("A4", "portrait", (1400, 0), "2번"),
                                     ("A3", "landscape", (0, 0), "1번"),
                                     ("A4", "landscape", (0, 900), "3번")):
        fr = _TitleBlockItem(size, orient, {"title": label})
        fr.setPos(QPointF(*pos))
        scene.addItem(fr)
        out[label] = fr
    return out


def _page_sizes_mm(path):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open(path)
    return [(round(p.rect.width / 72 * 25.4), round(p.rect.height / 72 * 25.4)) for p in doc]


def test_reading_order_is_left_to_right_then_next_row():
    sc = QGraphicsScene()
    fr = _three_frames(sc)
    assert _reading_order(_list_title_frames(sc)) == [fr["1번"], fr["2번"], fr["3번"]]


def test_export_pdf_pages_one_page_per_frame_with_own_paper():
    sc = QGraphicsScene()
    fr = _three_frames(sc)
    path = _tmp("a.pdf")
    assert export_pdf_pages(sc, path, [fr["1번"], fr["2번"], fr["3번"]])
    assert _page_sizes_mm(path) == [(420, 297), (210, 297), (297, 210)]


def test_dialog_multi_mode_defaults_all_checked_in_layout_order():
    w = CanvasWindow()
    fr = _three_frames(w._scene)
    dlg = _PdfExportDialog(w, w._scene, False)
    assert dlg._multi_active()
    opts = dlg.result_options()
    assert opts["pages"] == [fr["1번"], fr["2번"], fr["3번"]]
    assert "(3쪽)" in dlg._ok_btn.text()

    dlg._page_list.item(1).setCheckState(Qt.CheckState.Unchecked)   # 2번 빼기
    assert dlg.result_options()["pages"] == [fr["1번"], fr["3번"]]
    assert "(2쪽)" in dlg._ok_btn.text()

    for i in range(dlg._page_list.count()):
        dlg._page_list.item(i).setCheckState(Qt.CheckState.Unchecked)
    assert not dlg._ok_btn.isEnabled()                              # 하나도 없으면 저장 불가

    dlg._multi_cb.setChecked(False)                                  # 끄면 예전 단일 방식
    assert dlg.result_options()["pages"] is None and dlg._ok_btn.isEnabled()


def test_dialog_multi_mode_only_for_pdf_and_two_plus_frames():
    w = CanvasWindow()
    _three_frames(w._scene)
    dlg = _PdfExportDialog(w, w._scene, False, default_format="png")
    assert not dlg._multi_active() and dlg.result_options()["pages"] is None

    w2 = CanvasWindow()
    w2._scene.addItem(_TitleBlockItem("A4", "landscape", {}))
    dlg2 = _PdfExportDialog(w2, w2._scene, False)
    assert not dlg2._multi_active() and dlg2.result_options()["pages"] is None


def test_host_export_document_writes_multipage_pdf():
    w = CanvasWindow()
    _three_frames(w._scene)
    path = _tmp("b.pdf")
    with patch.object(_PdfExportDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
         patch.object(QFileDialog, "getSaveFileName", return_value=(path, "")), \
         patch.object(QMessageBox, "information"), patch.object(QMessageBox, "warning"):
        w._export_document("pdf")
    assert _page_sizes_mm(path) == [(420, 297), (210, 297), (297, 210)]
