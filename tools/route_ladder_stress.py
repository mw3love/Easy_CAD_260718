"""§8 항목19 F3 — 클리어런스 사다리(A*)가 실제로 도는 스트레스 픽스처 생성.

route_stress.ecad(격자 메시, 인접 도형끼리만 연결)는 간격이 넉넉해 `_route_ortho`의
preferred(단순 엘보)가 항상 안전 — A* 사다리가 3단계 실측에서 단 한 번도 안 돌았다
(docs/route_review_2026-08.md 7단계 진단 정정). 사다리를 실제로 태우려면 preferred가
장애물을 관통해야 한다 — 이 픽스처는 격자 메시에 더해 **한 칸 건너뛰는(skip-one) 연결**을
추가한다: (r,c)→(r,c+2)를 중심-대-중심(같은 y)으로 이으면, 직선 preferred가 그 사이
(r,c+1) 도형의 **한복판**을 정확히 관통한다(구석만 스치는 대각선과 달리 확실한 충돌) —
세로도 동일(r,c)→(r+2,c). [1차 시도: 대각선 코너-대-코너 연결은 인접 4칸 사이 빈 공간만
지나가 실제로는 단 한 건도 관통하지 않았다(ratio 전원 1.00으로 확인 후 폐기) — 관통을
강제하려면 "사이 도형의 중심을 직선으로 관통"해야 한다는 게 이 재시도의 근거.]

사용법: python tools/route_ladder_stress.py [출력경로]
"""
import gc
import os
import sys

gc.disable()  # [PyQt 함정, profile_obstacle_scan.py와 동일 근거] 순환GC가 C++ 객체를 조기파괴.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QColor

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import _RectItem, _PolyArrowItem, _EllipseItem, _SymbolItem
from easycad.fileio.document import save_document

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from route_quality_check import _rect, _bind_arrow  # noqa: E402

_APP = QApplication.instance() or QApplication([])   # [PyQt 함정] 지역변수면 build() 반환 시 refcount 0으로 앱 자체가 죽는다


def build(cols=8, rows=6, cell_w=220, cell_h=160, box_w=100, box_h=60):
    w = CanvasWindow()
    grid = {}
    for r in range(rows):
        for c in range(cols):
            grid[(r, c)] = _rect(w._scene, c * cell_w, r * cell_h, box_w, box_h)
    n = 0
    for r in range(rows):
        for c in range(cols):
            it = grid[(r, c)]
            if c + 1 < cols:
                _bind_arrow(w._scene, it, grid[(r, c + 1)])
                n += 1
            if r + 1 < rows:
                a, b = it, grid[(r + 1, c)]
                ra, rb = a.rect(), b.rect()
                _bind_arrow(w._scene, a, b,
                            QPointF(ra.center().x(), ra.bottom()),
                            QPointF(rb.center().x(), rb.top()))
                n += 1
            # [F3] 한 칸 건너뛰기 — 중심-대-중심 직선이 사이 도형 한복판을 관통하도록 강제.
            if c + 2 < cols:
                b = grid[(r, c + 2)]
                ib, bb = it.rect(), b.rect()
                _bind_arrow(w._scene, it, b,
                            QPointF(ib.right(), ib.center().y()),
                            QPointF(bb.left(), bb.center().y()))
                n += 1
            if r + 2 < rows:
                b = grid[(r + 2, c)]
                ib, bb = it.rect(), b.rect()
                _bind_arrow(w._scene, it, b,
                            QPointF(ib.center().x(), ib.bottom()),
                            QPointF(bb.center().x(), bb.top()))
                n += 1
    _APP.processEvents(); _APP.processEvents()
    return w, n


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "route_ladder_stress.ecad"
    w, n = build()
    save_document(w._scene, path)
    shapes = sum(1 for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem)))
    arrows = sum(1 for it in w._scene.items() if isinstance(it, _PolyArrowItem))
    print(f"저장: {path} (도형 {shapes}개, 화살표 {arrows}개, 생성시도 {n}건)")


if __name__ == "__main__":
    main()
