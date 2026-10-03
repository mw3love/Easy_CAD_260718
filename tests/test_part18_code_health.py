"""점검 3단계(2026-10-03) — DXF 내보내기·가져오기에서 변환 실패로 빠진 객체를 조용히 넘기지 않고
개수를 알리는지."""
import os
import uuid
from unittest.mock import patch

import ezdxf
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsScene, QMessageBox

from _shared import *  # noqa: F401,F403

from easycad.fileio import dxf_export
from easycad.fileio.dxf_import import import_dxf


def _tmp(name):
    d = os.path.join(_TMP, f"health_{uuid.uuid4().hex}")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def test_export_dxf_counts_failed_objects():
    sc = QGraphicsScene()
    _mk_rect(sc, QPen(QColor("red")), 0, 0, 100, 60)
    _mk_rect(sc, QPen(QColor("red")), 200, 0, 100, 60)
    stats = {}
    real = dxf_export._export_rect
    calls = []

    def _flaky(msp, it):
        calls.append(it)
        if len(calls) == 1:
            raise RuntimeError("변환 실패 흉내")
        return real(msp, it)

    with patch.object(dxf_export, "_export_rect", side_effect=_flaky):
        assert dxf_export.export_dxf(sc, _tmp("a.dxf"), stats=stats) is True
    assert stats == {"failed": 1}


def test_host_warns_when_dxf_export_drops_objects():
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    titles = []
    with patch.object(dxf_export, "_export_rect", side_effect=RuntimeError("x")), \
         patch("easycad.canvas.host_fileio.export_dxf",
               side_effect=lambda sc, p, stats=None: dxf_export.export_dxf(sc, p, stats=stats)), \
         patch.object(QMessageBox, "warning", side_effect=lambda *a, **k: titles.append(a[2])):
        w._do_export_dxf(_tmp("b.dxf"))
    assert len(titles) == 1 and "1개" in titles[0]

    titles.clear()
    with patch.object(QMessageBox, "warning", side_effect=lambda *a, **k: titles.append(a[2])):
        w._do_export_dxf(_tmp("c.dxf"))   # 실패 없으면 조용히
    assert titles == []


def test_import_dxf_counts_skipped_entities():
    path = _tmp("d.dxf")
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_spline([(0, 0), (50, 40), (100, 0), (150, 40)])
    msp.add_line((0, 0), (100, 100))
    doc.saveas(path)
    stats = {}
    with patch("ezdxf.entities.Spline.flattening", side_effect=RuntimeError("flatten 실패 흉내")):
        n = import_dxf(QGraphicsScene(), path, stats=stats)
    assert stats["failed"] == 1 and n >= 1   # 선은 들어오고 스플라인 1개만 빠짐
    stats2 = {}
    import_dxf(QGraphicsScene(), path, stats=stats2)
    assert stats2["failed"] == 0                  # 다음 호출에 새지 않음
