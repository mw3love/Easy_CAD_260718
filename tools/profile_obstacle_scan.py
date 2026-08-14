"""§8 항목19 4단계 — `_obstacle_rects()`(2단계 finding 1)가 정말 총 씬 아이템 수에 비례하는지
직접 격리해서 측정한다. 도형 수(=실제 A* 장애물 후보)는 고정하고, **화살표 개수만** 늘려가며
같은 화살표 하나의 `_obstacle_rects()`/`build_elbow()` 호출 시간을 잰다 — 라우팅 난이도는
그대로 두고 "총 아이템 수"라는 변수 하나만 격리하기 위해 추가 화살표는 전부 바인딩 없는
장식용(라우팅에 관여 안 함)으로 둔다.

사용법: python tools/profile_obstacle_scan.py
"""
import gc
import os
import sys
import time

gc.disable()  # PyQt 래퍼가 순환GC 중간에 C++ 객체를 조기 파괴하는 사고를 피한다(진단용 스크립트라 무해).
_KEEPALIVE = []  # 창을 여러 개 순차 생성하는 동안 아무것도 회수되지 않도록 전부 붙잡아 둔다.

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QColor, QPen

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import _RectItem, _PolyArrowItem

_APP = QApplication.instance() or QApplication([])

REPS = 300
SHAPE_COUNT = 50


def _pen():
    p = QPen(QColor("#333333")); p.setWidthF(1.0)
    return p


def build_scene(extra_arrows: int):
    app = _APP
    w = CanvasWindow()
    w.resize(800, 600)
    w.show()
    sc = w._scene
    shapes = []
    cols = 10
    for i in range(SHAPE_COUNT):
        r, c = divmod(i, cols)
        it = _RectItem(QRectF(0, 0, 80, 50))
        it.setPos(QPointF(c * 160, r * 120))
        it.setPen(_pen())
        it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
        sc.addItem(it)
        shapes.append(it)

    a, b = shapes[0], shapes[1]
    probe = _PolyArrowItem(QColor("#1f6feb"), 2, True)
    probe.set_points(QPointF(a.rect().right(), a.rect().center().y()),
                      QPointF(b.rect().left(), b.rect().center().y()))
    probe.setFlags(probe.GraphicsItemFlag.ItemIsSelectable | probe.GraphicsItemFlag.ItemIsMovable)
    sc.addItem(probe)
    probe.set_bound(0, a, QPointF(a.rect().right(), a.rect().center().y()))
    probe.set_bound(1, b, QPointF(b.rect().left(), b.rect().center().y()))
    probe._auto_route = True

    # 장식용 화살표(바인딩 없음) — 라우팅에 관여 안 하고 scene.items() 크기만 늘린다.
    decos = []
    for i in range(extra_arrows):
        j, k = i % SHAPE_COUNT, (i + 1) % SHAPE_COUNT
        deco = _PolyArrowItem(QColor("#888888"), 1, True)
        deco.set_points(QPointF(shapes[j].pos()), QPointF(shapes[k].pos()))
        sc.addItem(deco)
        decos.append(deco)

    app.processEvents(); app.processEvents()
    # [PyQt 함정] QGraphicsScene에 addItem()해도 C++ 쪽이 파이썬 래퍼 수명을 보장 안 한다 —
    # 함수 지역변수(shapes/decos)가 리턴 후 GC되면 그 아이템들의 파이썬 래퍼가 죽어 이후
    # scene.items() 호출이 "QGraphicsScene has been deleted"로 죽는다(실측 재현, 오탐 메시지).
    # 창뿐 아니라 만든 아이템도 전부 붙잡아 둔다.
    _KEEPALIVE.append((w, shapes, probe, decos))
    return w, probe


def time_call(fn, reps=REPS):
    t0 = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t0) * 1000.0 / reps


def main():
    print(f"도형 {SHAPE_COUNT}개 고정, 장식용(비바인딩) 화살표 개수만 증가시키며 측정 "
          f"(각 {REPS}회 평균, ms/call)\n")
    print(f"{'화살표+':>8} {'총 아이템':>9} {'_obstacle_rects':>16} {'build_elbow(fast=False)':>24}")
    for extra in (0, 100, 300, 600, 1000, 2000):
        w, probe = build_scene(extra)
        total_items = len(w._scene.items())
        t_obst = time_call(probe._obstacle_rects)
        t_elbow = time_call(lambda: probe.build_elbow())
        print(f"{extra:>8} {total_items:>9} {t_obst:>14.4f}ms {t_elbow:>22.4f}ms")


if __name__ == "__main__":
    main()
