"""화살표 라우팅 전수 점검(§8 항목19) 3단계 — 경로 품질 실측 도구.

두 가지 일을 한다:
  ⓐ `--gen [path]`  화살표-집중 스트레스 픽스처를 새로 만들어 저장(기존 `200.ecad`는 화살표
     0개라 이 용도로 못 씀 — `docs/route_review_2026-08.md` 1단계 표 참조). 그리드 메시(다수
     도형을 격자로 배치 + 인접 도형끼리 전부 연결)와, 2단계에서 찾은 "코리도 사전필터가 이론상
     완전성을 깰 수 있는" 케이스를 좁혀서 검증할 인접 장애물 미로(maze) 둘을 함께 넣는다.
  ⓑ `--analyze <path>`  임의 .ecad를 읽어 모든 직교 바인딩 화살표의 경로 품질을 정량화한다:
     - ratio = 실제 경로 길이 / 맨해튼 거리(1.0에 가까울수록 곧음, 크면 우회)
     - vertex 수(정점 많을수록 지그재그)
     - 도형 관통 여부(있으면 안전 위반 — 있어선 안 됨)
     상위 우회 후보를 출력해 "이질적 경로"(불필요하게 먼 우회)를 사람이 스크린샷과 대조하게 한다.

사용법:
    python tools/route_quality_check.py --gen route_stress.ecad
    python tools/route_quality_check.py --analyze route_stress.ecad
    python tools/route_quality_check.py --analyze kbs_1tv_test.ecad
"""
import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QColor

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _SymbolItem, _PolyArrowItem, _ArrowItem, _path_hits_rects,
)
from easycad.fileio.document import save_document, load_document


def _rect(scene, x, y, w, h):
    it = _RectItem(QRectF(0, 0, w, h))
    it.setPos(QPointF(x, y))
    it.setPen(_default_pen())
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    scene.addItem(it)
    return it


def _default_pen():
    from PyQt6.QtGui import QPen
    from PyQt6.QtCore import Qt
    p = QPen(QColor("#333333"))
    p.setWidthF(1.0)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _bind_arrow(scene, a, b, local_a=None, local_b=None):
    """a·b 테두리 중심 근처를 잇는 자동라우팅 직교 화살표 하나 생성."""
    ra, rb = a.rect(), b.rect()
    la = local_a if local_a is not None else QPointF(ra.right(), ra.center().y())
    lb = local_b if local_b is not None else QPointF(rb.left(), rb.center().y())
    sp, ep = a.mapToScene(la), b.mapToScene(lb)
    ar = _PolyArrowItem(QColor("#1f6feb"), 2, True)
    ar.set_points(sp, ep)
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    scene.addItem(ar)
    ar.set_bound(0, a, la)
    ar.set_bound(1, b, lb)
    ar._auto_route = True
    ar.build_elbow()
    return ar


def _gen_mesh(scene, cols=8, rows=6, cell_w=220, cell_h=160, box_w=100, box_h=60):
    """격자 메시 — 각 도형을 오른쪽·아래 이웃과 연결(다수 도형·다수 화살표, 조밀한 장애물)."""
    grid = {}
    for r in range(rows):
        for c in range(cols):
            x, y = c * cell_w, r * cell_h
            grid[(r, c)] = _rect(scene, x, y, box_w, box_h)
    n = 0
    for r in range(rows):
        for c in range(cols):
            it = grid[(r, c)]
            if c + 1 < cols:
                _bind_arrow(scene, it, grid[(r, c + 1)])
                n += 1
    # 세로 연결은 위/아래가 사각형 좌우가 아니라 상/하변이어야 자연스러움 — 별도로 상/하 로컬점 지정.
    for r in range(rows):
        for c in range(cols):
            if r + 1 < rows:
                a, b = grid[(r, c)], grid[(r + 1, c)]
                ra, rb = a.rect(), b.rect()
                _bind_arrow(scene, a, b,
                            QPointF(ra.center().x(), ra.bottom()),
                            QPointF(rb.center().x(), rb.top()))
                n += 1
    return n


def _gen_corridor_maze(scene, origin_x, origin_y):
    """[2단계 finding 재검토] 코리도 사전필터(_CORRIDOR_PAD_MIN=400) 완전성 한계를 좁혀서
    검증 — 시작·끝을 가까이 두고 그 사이를 곧바로 막는 '벽' 하나(코리도와 반드시 겹침 —
    이 벽 자체는 완전성을 못 깬다, 2단계 분석 참조)와, 코리도 바깥에 멀리 떨어진 별개 장애물
    (겹치지 않음 — 안전하게 무시돼도 되는지 확인용)을 함께 둔다."""
    ax, ay = origin_x, origin_y
    bx, by = origin_x + 120, origin_y
    a = _rect(scene, ax, ay, 60, 60)
    b = _rect(scene, bx, by, 60, 60)
    # 직접 경로를 막는 벽(코리도와 겹침 — 정상적으로 완전탐색 대상)
    _rect(scene, ax + 60, ay - 300, 20, 660)
    # 코리도 밖(>400px)에 있는 무관 장애물 — 결과에 영향 없어야 정상(간섭 시 버그)
    _rect(scene, ax - 900, ay - 900, 100, 100)
    ar = _bind_arrow(scene, a, b,
                      QPointF(a.rect().right(), a.rect().center().y()),
                      QPointF(b.rect().left(), b.rect().center().y()))
    return ar


def cmd_gen(path):
    app = QApplication.instance() or QApplication([])
    w = CanvasWindow()
    n_arrows = _gen_mesh(w._scene)
    _gen_corridor_maze(w._scene, origin_x=-2000, origin_y=-2000)
    app.processEvents(); app.processEvents()
    save_document(w._scene, path)
    shapes = sum(1 for it in w._scene.items() if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem)))
    arrows = sum(1 for it in w._scene.items() if isinstance(it, (_PolyArrowItem, _ArrowItem)))
    print(f"저장: {path} (도형 {shapes}개, 화살표 {arrows}개 — 메시 {n_arrows} + 미로 1)")


def _path_len(pts):
    return sum(math.hypot(b.x() - a.x(), b.y() - a.y()) for a, b in zip(pts, pts[1:]))


def cmd_analyze(path):
    app = QApplication.instance() or QApplication([])
    w = CanvasWindow()
    load_document(w._scene, path)
    app.processEvents(); app.processEvents()

    shapes = [it for it in w._scene.items()
              if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]

    rows = []
    for it in w._scene.items():
        if not isinstance(it, _PolyArrowItem):
            continue
        if it._routing != "ortho" or not it.has_binding():
            continue
        pts = [it.mapToScene(p) for p in it._pts]
        if len(pts) < 2:
            continue
        s, e = pts[0], pts[-1]
        manhattan = abs(e.x() - s.x()) + abs(e.y() - s.y())
        length = _path_len(pts)
        ratio = length / manhattan if manhattan > 1e-6 else 1.0
        # 관통 판정 — 양끝 바인딩 도형은 third_party에서 빼고 판정(자기 부착 도형은 원래 접촉).
        own = {id(it._bind_start), id(it._bind_end)}
        third_party = [sh.mapRectToScene(sh.rect()) for sh in shapes if id(sh) not in own]
        hits = _path_hits_rects(pts, third_party)
        rows.append((ratio, len(pts), length, manhattan, hits, s, e))

    rows.sort(key=lambda r: -r[0])
    n_hit = sum(1 for r in rows if r[4])
    print(f"직교 바인딩 화살표 {len(rows)}개 분석 ({path})")
    print(f"도형 관통(안전 위반): {n_hit}건" + ("  ⚠" if n_hit else "  (없음, 정상)"))
    if n_hit:
        for r in rows:
            if r[4]:
                print(f"  관통! ratio={r[0]:.2f} verts={r[1]} "
                      f"({r[5].x():.0f},{r[5].y():.0f})→({r[6].x():.0f},{r[6].y():.0f})")
    print("\n우회 비율 상위 10건 (ratio = 실제경로/맨해튼거리, 1.0=곧음):")
    for ratio, nv, length, manhattan, hits, s, e in rows[:10]:
        print(f"  ratio={ratio:5.2f}  verts={nv:2d}  길이={length:7.1f}  맨해튼={manhattan:7.1f}  "
              f"({s.x():.0f},{s.y():.0f})→({e.x():.0f},{e.y():.0f})")
    if rows:
        import statistics
        ratios = [r[0] for r in rows]
        print(f"\nratio 평균={statistics.mean(ratios):.2f} 중앙값={statistics.median(ratios):.2f} "
              f"최대={max(ratios):.2f}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--gen" in args:
        i = args.index("--gen")
        path = args[i + 1] if i + 1 < len(args) else "route_stress.ecad"
        cmd_gen(path)
    elif "--analyze" in args:
        i = args.index("--analyze")
        path = args[i + 1]
        cmd_analyze(path)
    else:
        print(__doc__)
