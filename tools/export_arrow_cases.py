"""웹 칠판 화살표 손질(web/src/next/arrowedit.js·arrows.js)이 데스크톱과 같은 답을 내는지 맞춰 볼 시험 사례(§8 항목61 3-2, 2026-10-17).

- 경유지 길: 상자 둘에 붙은 「자동 길」 화살표 + route_hints 하나 → `build_elbow` 꼭짓점
- 알약 끌기: 꼭짓점·구간·끌 자리 → `_begin_segment_drag`·`_drag_segment_to`·`_end_segment_drag`
- 나눠 끌기: 알약 아닌 자리 → `_begin_subdivide_drag` 뒤 같은 끌기
- 곡선 휨·S자: `_solve_ctrl`·`_recompute_snap_curve`
`web/test/fixtures/arrow_cases.json`에 쓴다. 웹 시험 = `web/test/arrowedit.test.mjs`.

실행: python tools/export_arrow_cases.py [--seed 7]
"""
import argparse
import json
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtGui import QColor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from easycad.canvas.core_shapes import _ArrowItem, _PolyArrowItem  # noqa: E402
from easycad.canvas.host import CanvasWindow  # noqa: E402
from easycad.fileio.document import dict_to_item  # noqa: E402

R = lambda v: round(v, 4)  # noqa: E731
PTS = lambda pts: [[R(p.x()), R(p.y())] for p in pts]  # noqa: E731


def rect(x, y, w, h):
    return {"type": "rect", "rect": [0, 0, w, h], "pos": [x, y], "pen": "#ff000000", "width": 2, "fill": None}


def hint_cases(rnd, sc):
    out = []
    for _ in range(12):
        a = rect(rnd.randrange(-300, -100, 10), rnd.randrange(-100, 100, 10), 120, 60)
        b = rect(rnd.randrange(100, 300, 10), rnd.randrange(-100, 100, 10), 120, 60)
        ia, ib = dict_to_item(a), dict_to_item(b)
        sc.addItem(ia); sc.addItem(ib)
        s = QPointF(a["pos"][0] + 120, a["pos"][1] + 30)
        e = QPointF(b["pos"][0], b["pos"][1] + 30)
        ar = _PolyArrowItem(QColor("#111"), 2, True, False, 1.0)
        ar._curve_r = 10.0
        ar.set_points(s, e)
        ar.set_bound(0, ia, ia.mapFromScene(s)); ar.set_bound(1, ib, ib.mapFromScene(e))
        ar._auto_route = True
        hint = [rnd.randrange(-60, 60, 10), rnd.choice([-150, -120, 120, 150])]
        ar._route_hints = [QPointF(*hint)]
        sc.addItem(ar)
        ar.build_elbow()
        out.append({"a": a, "b": b, "s": [s.x(), s.y()], "e": [e.x(), e.y()], "hint": hint, "expect": PTS(ar._pts)})
        sc.removeItem(ar); sc.removeItem(ia); sc.removeItem(ib)
    return out


def seg_cases(rnd, sc):
    out = []
    shapes = [[[0, 0], [100, 0], [100, 80], [220, 80]], [[0, 0], [60, 0], [60, -90], [240, -90], [240, 0], [300, 0]], [[0, 0], [0, 120], [160, 120]]]
    for pts in shapes:
        for _ in range(4):
            ar = _PolyArrowItem(QColor("#111"), 2, True, False, 1.0)
            ar._pts = [QPointF(*p) for p in pts]
            sc.addItem(ar)
            handles = ar._segment_handles()
            i, mid, horiz = rnd.choice(handles)
            sub = rnd.random() < 0.5
            a, b = ar._pts[i], ar._pts[i + 1]
            if sub:   # 알약 밖, 한쪽 끝 가까이
                t = rnd.choice([0.15, 0.85])
                near = QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
                ar._begin_subdivide_drag(i, near)
            else:
                near = mid
                ar._begin_segment_drag(i)
            to = QPointF(mid.x() + rnd.randrange(-50, 50, 5), mid.y() + rnd.randrange(-50, 50, 5))
            ar._drag_segment_to(to)
            ar._end_segment_drag()
            out.append({"pts": pts, "i": i, "sub": sub, "near": [R(near.x()), R(near.y())], "to": [to.x(), to.y()], "expect": PTS(ar._pts)})
            sc.removeItem(ar)
    return out


def curve_cases(rnd):
    out = []
    for _ in range(10):
        p1 = QPointF(rnd.randrange(-100, 0, 5), rnd.randrange(-50, 50, 5))
        p2 = QPointF(rnd.randrange(100, 250, 5), rnd.randrange(-80, 80, 5))
        ar = _ArrowItem(QColor("#111"), 2, True, False, 1.0)
        ar.set_points(p1, p2)
        which = rnd.choice([1, 2])
        tgt = QPointF(rnd.randrange(-20, 200, 5), rnd.randrange(-100, 100, 5))
        if ar._ctrl1 is None:
            ar._ctrl1 = ar._point_straight(ar._BEND_TS[0]); ar._ctrl2 = ar._point_straight(ar._BEND_TS[1])
        ar._solve_ctrl(which, tgt)
        bend = [[R(ar._ctrl1.x()), R(ar._ctrl1.y())], [R(ar._ctrl2.x()), R(ar._ctrl2.y())]]
        n0 = rnd.choice([None, [1, 0], [0, -1]])
        n1 = rnd.choice([None, [-1, 0], [0, 1]])
        ar2 = _ArrowItem(QColor("#111"), 2, True, False, 1.0)
        ar2.set_points(p1, p2)
        ar2._endpoint_border_normal = lambda idx, n1=n1: None if n1 is None else QPointF(*n1)
        ar2._recompute_snap_curve(0, None if n0 is None else QPointF(*n0))
        snap = None if ar2._ctrl1 is None else [[R(ar2._ctrl1.x()), R(ar2._ctrl1.y())], [R(ar2._ctrl2.x()), R(ar2._ctrl2.y())]]
        out.append({"p1": [p1.x(), p1.y()], "p2": [p2.x(), p2.y()], "which": which, "target": [tgt.x(), tgt.y()], "bend": bend, "n0": n0, "n1": n1, "snap": snap})
    return out


def label_cases(rnd):
    from PyQt6.QtCore import QRectF
    from easycad.canvas.core_shapes import _snap_label_off
    out = []
    poly = [[0, 0], [120, 0], [120, 90], [260, 90]]
    pa = _PolyArrowItem(QColor("#111"), 2, True, False, 1.0)
    pa._pts = [QPointF(*q) for q in poly]
    ca = _ArrowItem(QColor("#111"), 2, True, False, 1.0)
    ca.set_points(QPointF(0, 0), QPointF(240, 60)); ca._ctrl1 = QPointF(60, -80); ca._ctrl2 = QPointF(200, 140)
    for _ in range(16):
        q = QPointF(rnd.uniform(-20, 280), rnd.uniform(-60, 140))
        t, off = pa._project_to_path(q)
        ct, coff = ca._project_to_curve(q)
        w, h = rnd.choice([40, 80]), rnd.choice([20, 30])
        n = rnd.choice([[0, -1], [1, 0], [0.6, 0.8]])
        snap = _snap_label_off(QPointF(*n), off, QRectF(0, 0, w, h))
        out.append({"q": [q.x(), q.y()], "poly": [R(t), R(off)], "curve": [R(ct), R(coff)], "n": n, "w": w, "h": h, "snap": R(snap)})
    return {"poly": poly, "curve": {"p1": [0, 0], "p2": [240, 60], "ctrl1": [60, -80], "ctrl2": [200, 140]}, "cases": out}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    rnd = random.Random(a.seed)
    _app = QApplication.instance() or QApplication(sys.argv)
    w = CanvasWindow()
    sc = w._scene
    data = {"hints": hint_cases(rnd, sc), "segments": seg_cases(rnd, sc), "curves": curve_cases(rnd), "labels": label_cases(rnd)}
    out = os.path.join(ROOT, "web", "test", "fixtures", "arrow_cases.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print({k: len(v) for k, v in data.items()}, "→", out)


if __name__ == "__main__":
    main()
