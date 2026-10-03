"""§8 항목31(2026-10-03) — DXF 채우기(HATCH) 내보내기·가져오기.

사용자 결정: 별도 EC_FILL 레이어 · 투명도 유지 · 도형 4종(사각·원·심볼·닫힌 다각형)+글자 배경 ·
다시 열 때 Easy CAD 채우기는 그 도형으로 되살리고, 다른 CAD의 단색 해치는 채운 패스로(구멍 유지),
무늬 해치는 건너뛰고 개수만 센다."""
import os
import uuid

import ezdxf
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsScene

from _shared import *  # noqa: F401,F403

from easycad.fileio.dxf_import import import_dxf


def _tmp(name):
    d = os.path.join(_TMP, f"hatch_{uuid.uuid4().hex}")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _filled_scene():
    sc = QGraphicsScene()
    pen = QPen(QColor("black"), 2)

    def add(it, pos, fill):
        it.setPen(pen); it.setPos(QPointF(*pos))
        if fill:
            it.apply_fill(QColor(*fill))
        sc.addItem(it)
        return it
    add(_RectItem(QRectF(0, 0, 120, 80)), (0, 0), (255, 0, 0, 128))
    add(_EllipseItem(QRectF(0, 0, 100, 100)), (200, 0), (0, 160, 0))
    add(_SymbolItem("decision", QRectF(0, 0, 120, 80)), (400, 0), (0, 0, 255))
    add(_PolygonItem([QPointF(0, 0), QPointF(100, 0), QPointF(50, 80)], True,
                     rect=QRectF(0, 0, 100, 80)), (600, 0), (255, 200, 0))
    add(_RectItem(QRectF(0, 0, 120, 80)), (0, 200), None)
    add(_PolygonItem([QPointF(0, 0), QPointF(100, 0), QPointF(50, 80)], False,
                     rect=QRectF(0, 0, 100, 80)), (600, 200), None)   # 열린 폴리라인
    t = _TextItem(QColor("black")); t.setPlainText("배경"); t.set_bg(QColor(255, 255, 0, 200))
    t.setPos(QPointF(200, 200)); sc.addItem(t)
    return sc


def _fills(scene):
    out = []
    for it in scene.items():
        if it.parentItem() is not None:
            continue
        if isinstance(it, _TextItem):
            out.append(None if it._bg is None else it._bg.getRgb())
        elif hasattr(it, "brush"):
            b = it.brush()
            out.append(None if b.style() == Qt.BrushStyle.NoBrush else b.color().getRgb())
    return sorted(out, key=str)


def test_export_writes_solid_hatches_on_fill_layer_before_outline():
    sc = _filled_scene()
    path = _tmp("a.dxf")
    export_dxf(sc, path)
    ents = list(ezdxf.readfile(path).modelspace())
    hatches = [e for e in ents if e.dxftype() == "HATCH"]
    assert len(hatches) == 5                                   # 채운 4종 + 글자 배경
    assert all(h.dxf.layer == "EC_FILL" and h.dxf.solid_fill == 1 for h in hatches)
    rgbs = {tuple(h.rgb): round(h.transparency, 2) for h in hatches}
    assert rgbs[(255, 0, 0)] == 0.5 and rgbs[(0, 160, 0)] == 0.0   # 반투명 유지
    # 각 채우기는 자기 테두리보다 앞(=아래)
    first_hatch = next(i for i, e in enumerate(ents) if e.dxftype() == "HATCH")
    assert first_hatch < next(i for i, e in enumerate(ents) if e.dxftype() == "LWPOLYLINE")


def test_round_trip_restores_fills_on_matching_shapes():
    sc = _filled_scene()
    path = _tmp("b.dxf")
    export_dxf(sc, path)
    sc2 = QGraphicsScene(); stats = {}
    import_dxf(sc2, path, stats=stats)
    assert stats["failed"] == 0
    # 같은 색들이 되살아나고, 따로 떨어진 채운 패스가 생기지 않음(개수 동일)
    assert _fills(sc2) == _fills(sc)
    assert len([i for i in sc2.items() if i.parentItem() is None]) == \
        len([i for i in sc.items() if i.parentItem() is None])


def test_external_solid_hatch_keeps_hole_and_pattern_hatch_is_counted():
    path = _tmp("c.dxf")
    doc = ezdxf.new(); m = doc.modelspace()
    h = m.add_hatch(); h.set_solid_fill(rgb=(200, 50, 50))
    h.paths.add_polyline_path([(0, 0), (100, 0), (100, 100), (0, 100)], is_closed=True)
    h.paths.add_polyline_path([(30, 30), (70, 30), (70, 70), (30, 70)], is_closed=True)
    p = m.add_hatch(color=3); p.set_pattern_fill("ANSI31", scale=1)
    p.paths.add_polyline_path([(200, 0), (300, 0), (300, 100), (200, 100)], is_closed=True)
    doc.saveas(path)
    sc = QGraphicsScene(); stats = {}
    import_dxf(sc, path, stats=stats)
    assert stats["failed"] == 1                                # 무늬 해치
    paths = [i for i in sc.items() if isinstance(i, _PathItem)]
    assert len(paths) == 1
    pi = paths[0]
    assert pi.brush().color().getRgb()[:3] == (200, 50, 50)
    br = pi.path().boundingRect()
    assert not pi.path().contains(br.center())                 # 구멍
    assert pi.path().contains(QPointF(br.left() + br.width() * 0.1, br.top() + br.height() * 0.1))


def test_filled_path_survives_ecad_round_trip():
    from PyQt6.QtGui import QBrush, QPainterPath
    sc = QGraphicsScene()
    qp = QPainterPath(); qp.addRect(QRectF(0, 0, 50, 50))
    it = _PathItem(qp); it.setPen(QPen(QColor("red"), 0)); it.setBrush(QBrush(QColor(10, 20, 30, 100)))
    sc.addItem(it)
    plain = _PathItem(qp); plain.setPen(QPen(QColor("blue"), 1)); sc.addItem(plain)
    path = _tmp("d.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene(); load_document(sc2, path)
    got = [None if i.brush().style() == Qt.BrushStyle.NoBrush else i.brush().color().getRgb()
           for i in sc2.items() if isinstance(i, _PathItem)]
    assert sorted(got, key=str) == sorted([(10, 20, 30, 100), None], key=str)
