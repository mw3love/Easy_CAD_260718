"""§8 항목33(2026-10-03) — 벡터 PDF 가져오기. 사용자 결정: 열기(Ctrl+O)로 새 탭 · 쪽마다 빈 용지틀 나란히 ·
글자는 고칠 수 있는 글자 · 많으면 개수 알려 주고 계속/취소. 시험 PDF는 PyMuPDF로 그 자리에서 만든다."""
import os
import uuid
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsScene, QMessageBox

from _shared import *  # noqa: F401,F403
from easycad.canvas.annotator_core import (
    _TitleBlockItem, _PathItem, _PolygonItem, _RectItem, _TextItem, _ImageItem,
)
from easycad.fileio import pdf_import
from easycad.fileio.document import item_to_dict, dict_to_item
from easycad.fileio.pdf_export import export_pdf_pages, _reading_order, _list_title_frames

fitz = pytest.importorskip("fitz")

S = pdf_import.SCALE


def _tmp(name):
    d = os.path.join(_TMP, f"pdfimp_{uuid.uuid4().hex}")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _sample_pdf(**save_kw):
    """1쪽 A4 세로(선·채움 사각·채운 원·점선·가로/세로 글자·삼각형 2개 채움·구멍 채움·그림),
    2쪽 A3(세로로 만들어 90° 회전 → 가로로 보임), 3쪽 Letter(규격 밖)."""
    doc = fitz.open()
    p = doc.new_page(width=595.28, height=841.89)
    p.draw_line((50, 50), (300, 50), color=(1, 0, 0), width=2)
    p.draw_rect(fitz.Rect(60, 100, 200, 180), color=(0, 0, 1), fill=(0.8, 0.9, 1), width=1)
    p.draw_circle((400, 150), 40, color=None, fill=(0, 0.6, 0))
    p.draw_line((50, 300), (400, 300), color=(0, 0, 0), width=1, dashes="[6 3] 0")
    p.insert_text((100, 400), "HELLO", fontsize=14)
    p.insert_text((300, 600), "VERT", fontsize=14, rotate=90)
    sh = p.new_shape()   # AutoCAD식 굵은 선: 떨어진 삼각형 2개를 한 경로로 채움
    sh.draw_polyline([(50, 700), (90, 700), (70, 740), (50, 700)])
    sh.draw_polyline([(150, 700), (190, 700), (170, 740), (150, 700)])
    sh.finish(color=None, fill=(0, 0, 0))
    sh.commit()
    sh = p.new_shape()   # 구멍 있는 채움(홀짝)
    sh.draw_rect(fitz.Rect(300, 700, 400, 800))
    sh.draw_rect(fitz.Rect(330, 730, 370, 770))
    sh.finish(color=None, fill=(1, 0.5, 0), even_odd=True)
    sh.commit()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4), 0)
    pix.clear_with(200)
    p.insert_image(fitz.Rect(450, 700, 550, 800), pixmap=pix)
    p2 = doc.new_page(width=841.89, height=1190.55)
    p2.draw_rect(fitz.Rect(100, 100, 300, 200), color=(0, 0, 0), width=3)
    p2.insert_text((120, 150), "ROT", fontsize=20)
    p2.set_rotation(90)
    p3 = doc.new_page(width=612, height=792)
    p3.draw_line((10, 10), (600, 780), color=(0, 0, 0), width=1)
    path = _tmp("sample.pdf")
    doc.save(path, **save_kw)
    return path


def _top(scene, cls):
    return [it for it in scene.items() if it.parentItem() is None and isinstance(it, cls)]


def test_paper_of_matches_a_sizes_both_orientations():
    assert pdf_import.paper_of(595.28, 841.89) == ("A4", "portrait")
    assert pdf_import.paper_of(1191, 842) == ("A3", "landscape")   # AutoCAD 1.pdf 크기(반올림)
    assert pdf_import.paper_of(612, 792) is None                    # Letter
    assert pdf_import.paper_of(2384, 3370) is None                  # A0 — 용지틀 미지원


def test_import_pages_side_by_side_with_plain_frames():
    sc = QGraphicsScene()
    st = {}
    n = pdf_import.import_pdf(sc, _sample_pdf(), stats=st)
    assert n == len([it for it in sc.items() if it.parentItem() is None])
    assert st["pages"] == 3 and st["no_frame"] == 1 and st["skipped_images"] == 0 and st["vector"]
    frames = sorted(_top(sc, _TitleBlockItem), key=lambda f: f.pos().x())
    assert [(f._size, f._orient, f._plain) for f in frames] == [("A4", "portrait", True),
                                                               ("A3", "landscape", True)]
    a4 = frames[0].sceneBoundingRect()
    assert abs(frames[0].mapRectToScene(frames[0].rect()).width() - 595.28 * S) < 2
    # 2쪽은 1쪽 오른쪽에 간격을 두고, 3쪽(용지틀 없음)은 그 오른쪽
    assert frames[1].pos().x() > a4.right()
    letter_line = max(_top(sc, _PathItem), key=lambda it: it.sceneBoundingRect().left())
    assert letter_line.sceneBoundingRect().left() > frames[1].sceneBoundingRect().right()


def test_geometry_colors_and_styles_follow_pdf():
    sc = QGraphicsScene()
    pdf_import.import_pdf(sc, _sample_pdf())
    paths = _top(sc, _PathItem)
    red = [p for p in paths if p.pen().color().name() == "#ff0000"]
    assert len(red) == 1
    r = red[0].mapRectToScene(red[0].path().boundingRect())
    assert abs(r.left() - 50 * S) < 1 and abs(r.right() - 300 * S) < 1 and abs(r.center().y() - 50 * S) < 1
    assert abs(red[0].pen().widthF() - 2 * S) < 1e-6
    dashed = [p for p in paths if p.pen().style().value == 2]
    assert len(dashed) == 1                                            # 점선 유지
    circle = [p for p in paths if p.brush().color().name() == "#009900"]
    assert len(circle) == 1 and circle[0].path().elementCount() > 8   # 곡선 채움은 곡선 그대로
    box = [p for p in _top(sc, _PolygonItem) if p.brush().color().name() in ("#cce5ff", "#cce6ff")]
    assert len(box) == 1 and box[0].pen().color().name() == "#0000ff"  # 채움+테두리 둘 다


def test_disjoint_fill_subpaths_become_separate_polygons_and_holes_stay_holes():
    """pitfalls: AutoCAD 굵은 선(떨어진 삼각형 여러 개를 한 경로로) → 끊긴 지점마다 별도 다각형."""
    sc = QGraphicsScene()
    pdf_import.import_pdf(sc, _sample_pdf())
    black = [p for p in _top(sc, _PolygonItem) if p.brush().color().name() == "#000000"]
    assert len(black) == 2 and all(len(p.local_pts()) == 3 for p in black)
    holed = [p for p in _top(sc, _PathItem) if p.brush().color().name() == "#ff8000"]
    assert len(holed) == 1
    c = holed[0].sceneBoundingRect().center()
    assert not holed[0].path().contains(holed[0].mapFromScene(c))   # 가운데는 구멍


def test_text_is_editable_text_on_baseline_with_rotation():
    sc = QGraphicsScene()
    pdf_import.import_pdf(sc, _sample_pdf())
    texts = {t.toPlainText(): t for t in _top(sc, _TextItem)}
    assert set(texts) == {"HELLO", "VERT", "ROT"}
    hello = texts["HELLO"]
    base = hello.mapToScene(hello.transformOriginPoint())
    assert abs(base.x() - 100 * S) < 1 and abs(base.y() - 400 * S) < 1   # 기준선 왼쪽 점 그대로
    assert hello.font().pointSize() == round(14 * S * 0.75)
    assert abs(texts["VERT"].rotation() + 90) < 1e-6                     # 아래→위로 읽는 세로 글자
    assert abs(texts["ROT"].rotation() - 90) < 1e-6                      # 90° 돌린 쪽의 글자도 돈다


def test_rotated_page_geometry_is_shown_rotated():
    sc = QGraphicsScene()
    pdf_import.import_pdf(sc, _sample_pdf())
    a3 = [f for f in _top(sc, _TitleBlockItem) if f._size == "A3"][0]
    fr = a3.mapRectToScene(a3.rect())
    box = [p for p in _top(sc, _PathItem) if abs(p.pen().widthF() - 3 * S) < 1e-6]
    assert len(box) == 1
    r = box[0].sceneBoundingRect()
    assert fr.contains(r)
    assert r.height() > r.width()          # 원래 가로로 긴 사각형(200×100)이 세로로 섰다


def test_pdf_images_become_image_items():
    sc = QGraphicsScene()
    pdf_import.import_pdf(sc, _sample_pdf())
    imgs = _top(sc, _ImageItem)
    assert len(imgs) == 1
    r = imgs[0].mapRectToScene(imgs[0].rect())
    assert abs(r.width() - 100 * S) < 2 and abs(r.left() - 450 * S) < 2


def test_plain_frame_roundtrips_and_clones():
    fr = _TitleBlockItem("A3", "landscape", plain=True)
    d = item_to_dict(fr)
    assert d["plain"] is True
    assert dict_to_item(d)._plain is True
    assert fr.clone()._plain is True
    assert "plain" not in item_to_dict(_TitleBlockItem("A3", "landscape"))   # 하위호환: 기본은 키 없음
    assert dict_to_item({**item_to_dict(_TitleBlockItem("A4")), "type": "titleblock"})._plain is False


def test_plain_frame_hit_area_has_no_title_table():
    plain, normal = _TitleBlockItem("A3", "landscape", plain=True), _TitleBlockItem("A3", "landscape")
    tb = normal._tb_rect().center()
    assert normal.shape().contains(tb) and not plain.shape().contains(tb)


def test_reexport_gives_same_pages_and_paper():
    """항목30과 짝 — 가져온 쪽들을 다시 「모든 페이지를 한 PDF로」 내면 같은 쪽 수·용지."""
    sc = QGraphicsScene()
    pdf_import.import_pdf(sc, _sample_pdf())
    out = _tmp("again.pdf")
    assert export_pdf_pages(sc, out, _reading_order(_list_title_frames(sc)))
    doc = fitz.open(out)
    assert [(round(p.rect.width / 72 * 25.4), round(p.rect.height / 72 * 25.4)) for p in doc] == \
        [(210, 297), (420, 297)]


def test_host_open_pdf_new_tab_external_path_and_no_undo():
    w = CanvasWindow()
    w._set_recent_files([])
    path = _sample_pdf()
    before = w._tabs.count()
    w._open_path(path)
    assert w._tabs.count() == before + 1
    assert w._external_path == path and not w._doc_path            # Ctrl+S가 PDF를 덮어쓰지 않게
    assert w._tabs.tabText(w._tabs.currentIndex()).startswith("sample.pdf")
    assert "PDF 가져오기 완료" in w.statusBar().currentMessage()
    assert "용지틀 없이" in w.statusBar().currentMessage()          # Letter 쪽 안내
    assert len(_top(w._scene, _TitleBlockItem)) == 2
    assert not w._undo                                               # 열기는 되돌리기 기록을 비운다
    assert w._recent_files()[0] == os.path.abspath(path)
    w._set_recent_files([])


def test_large_pdf_asks_and_cancel_leaves_scene_empty():
    w = CanvasWindow()
    w._set_recent_files([])
    asked = []
    w._confirm_large_pdf = lambda n: (asked.append(n), False)[1]
    with patch.object(pdf_import, "LARGE_COUNT", 3):
        w._open_path(_sample_pdf())
    assert asked and asked[0] > 3
    assert not [it for it in w._scene.items() if it.parentItem() is None]
    assert "취소" in w.statusBar().currentMessage()
    assert w._recent_files() == []                                   # 취소한 파일은 최근 목록에 안 넣음
    w._confirm_large_pdf = lambda n: True
    with patch.object(pdf_import, "LARGE_COUNT", 3):
        w._open_path(_sample_pdf())
    assert _top(w._scene, _TextItem)
    w._set_recent_files([])


def test_progress_cancel_returns_none_and_keeps_scene():
    sc = QGraphicsScene()
    keep = _mk_rect(sc, QPen(QColor("#123456")), 0, 0, 10, 10)
    assert pdf_import.import_pdf(sc, _sample_pdf(), progress=lambda d, t: False) is None
    assert sc.items() == [keep]


def test_encrypted_pdf_shows_message():
    path = _sample_pdf(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    with pytest.raises(pdf_import.PdfImportError, match="암호"):
        pdf_import.read_pdf(path)
    w = CanvasWindow()
    msgs = []
    with patch.object(QMessageBox, "warning", side_effect=lambda *a, **k: msgs.append(a[2])):
        w._open_path(path)
    assert msgs and "암호" in msgs[0]


def test_dropping_pdf_opens_new_tab():
    w = CanvasWindow()
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(_sample_pdf())])
    before = w._tabs.count()
    assert w._handle_url_drop(md, QPointF(0, 0)) == 1
    assert w._tabs.count() == before + 1 and _top(w._scene, _TextItem)


def test_open_filter_lists_pdf():
    assert "*.pdf" in CanvasWindow._OPEN_FILTER
