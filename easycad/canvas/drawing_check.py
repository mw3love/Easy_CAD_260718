"""「도면 검사」(§8 항목48, 2026-10-16) — 고쳐야 할 곳 네 가지를 찾는다. 결과 카드·표시는 `host_check`가 맡는다.

1. 연결 안 된 화살표 끝 — 화살표 끝이 아무 상자에도 붙지 않음(`_bind1/_bind2`, 직각은 `_bind_start/_bind_end`).
2. 넘친 글자 — 상자 가운데 글자가 상자 밖으로 나감.
3. 겹친 상자 — 두 상자가 일부만 겹침(한 상자가 다른 상자 안에 쏙 들어간 건 묶음 표시로 보고 뺀다).
4. 상자를 지나가는 선 — 화살표가 자기 양 끝 상자가 아닌 상자를 뚫고 지나감.

anatomy 스킬(wheresryan22/anatomy)의 "비평가처럼, 0개가 될 때까지 검사"에서 가져온 생각 — 그쪽은 선 끝·관통·겹침을 그림에서
찾고, 우리는 고칠 수 있는 도면에서 찾아 그 자리로 데려간다. 판단은 보수적으로(헷갈리면 안 잡음): 잘못 잡으면 검사를 안 믿게 된다.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QLineF, QPointF, QRectF
from PyQt6.QtGui import QPainterPath

from easycad.canvas.annotator_core import (
    _ArrowItem, _EllipseItem, _PolyArrowItem, _PolygonItem, _RectItem, _SymbolItem,
)

BOX_TYPES = (_RectItem, _EllipseItem, _SymbolItem, _PolygonItem)
ARROW_TYPES = (_ArrowItem, _PolyArrowItem)

KIND_TEXT = {
    "loose_end": "연결 안 된 화살표 끝",
    "text_overflow": "상자 밖으로 넘친 글자",
    "box_overlap": "겹친 상자",
    "line_through": "상자를 지나가는 선",
}
KIND_ORDER = ("loose_end", "text_overflow", "box_overlap", "line_through")

_OVERLAP_MIN = 0.08     # 작은 상자 넓이의 8% 넘게 겹쳐야 "겹침"(살짝 닿은 건 뺌)
_TEXT_SLACK = 2.0       # 글자가 이만큼(px)까지 삐져나온 건 봐줌(글꼴 여백)
_THROUGH_INSET = 6.0    # 상자를 이만큼 안쪽으로 줄인 뒤 선이 지나가야 "관통"(테두리 스침은 뺌)


@dataclass
class Issue:
    kind: str
    item: object          # 문제의 주인(화살표·상자) — 결과 카드가 선택해 보여 준다
    where: QRectF         # 표시할 자리(씬 좌표)
    note: str = ""        # 한 줄 설명(상자 글자 등)

    @property
    def title(self) -> str:
        return KIND_TEXT[self.kind]


def _label_text(it) -> str:
    return " ".join(c.toPlainText().strip() for c in it.childItems()
                    if hasattr(c, "toPlainText") and c.toPlainText().strip())


def _shape_rect(it) -> QRectF:
    """상자의 몸통(테두리 굵기·핸들 여유를 뺀) 씬 사각형."""
    return it.mapRectToScene(it.rect()) if hasattr(it, "rect") else it.sceneBoundingRect()


def _arrow_ends(it):
    """(시작 씬 좌표, 끝 씬 좌표, 시작에 붙은 상자, 끝에 붙은 상자)."""
    if isinstance(it, _PolyArrowItem):
        pts = it._pts
        return it.mapToScene(pts[0]), it.mapToScene(pts[-1]), it._bind_start, it._bind_end
    return it.mapToScene(it._p1), it.mapToScene(it._p2), it._bind1, it._bind2


def _arrow_polyline(it) -> list[QPointF]:
    """화살표 몸통을 꺾은선으로(곡선은 잘게 나눔) — 씬 좌표."""
    if isinstance(it, _PolyArrowItem):
        return [it.mapToScene(p) for p in it._pts]
    p1, p2 = it._p1, it._p2
    if it._ctrl1 is None or it._ctrl2 is None:
        return [it.mapToScene(p1), it.mapToScene(p2)]
    path = QPainterPath(p1)
    path.cubicTo(it._ctrl1, it._ctrl2, p2)
    return [it.mapToScene(path.pointAtPercent(i / 24)) for i in range(25)]


def _segment_hits_rect(a: QPointF, b: QPointF, r: QRectF) -> bool:
    if r.contains(a) or r.contains(b):
        return True
    edges = (QLineF(r.topLeft(), r.topRight()), QLineF(r.topRight(), r.bottomRight()),
             QLineF(r.bottomRight(), r.bottomLeft()), QLineF(r.bottomLeft(), r.topLeft()))
    seg = QLineF(a, b)
    for e in edges:
        kind, _pt = seg.intersects(e)
        if kind == QLineF.IntersectionType.BoundedIntersection:
            return True
    return False


def _mark(p: QPointF, size: float = 18.0) -> QRectF:
    return QRectF(p.x() - size / 2, p.y() - size / 2, size, size)


def check_drawing(scene, items=None) -> list[Issue]:
    """씬(또는 `items`만 — AI 임시 결과 검사용)에서 문제 목록. 보이지 않는 아이템은 뺀다. 순서는 `KIND_ORDER`, 같은 종류는 위→아래·왼→오."""
    pool = items if items is not None else [it for it in scene.items() if it.parentItem() is None]
    pool = [it for it in pool if it.isVisible()]
    boxes = [it for it in pool if isinstance(it, BOX_TYPES)]
    arrows = [it for it in pool if isinstance(it, ARROW_TYPES)]
    issues: list[Issue] = []

    # 1. 연결 안 된 화살표 끝 — 단, 끝이 상자 테두리 위에 그냥 놓인 건(붙지 않았어도) 사람 눈엔 이어져 보이므로 뺀다.
    for it in arrows:
        p0, p1, b0, b1 = _arrow_ends(it)
        for p, bound in ((p0, b0), (p1, b1)):
            if bound is not None:
                continue
            if any(_shape_rect(bx).adjusted(-3, -3, 3, 3).contains(p) for bx in boxes):
                continue
            issues.append(Issue("loose_end", it, _mark(p), _label_text(it)))

    # 2. 넘친 글자
    for bx in boxes:
        body = _shape_rect(bx).adjusted(-_TEXT_SLACK, -_TEXT_SLACK, _TEXT_SLACK, _TEXT_SLACK)
        for c in bx.childItems():
            if hasattr(c, "toPlainText") and c.toPlainText().strip() and c.isVisible():
                tr = c.sceneBoundingRect()
                if not body.contains(tr):
                    issues.append(Issue("text_overflow", bx, tr.united(_shape_rect(bx)), c.toPlainText().strip()))
                break

    # 3. 겹친 상자(일부만 — 쏙 들어간 건 묶음으로 봄)
    rects = [(bx, _shape_rect(bx)) for bx in boxes]
    for i, (a, ra) in enumerate(rects):
        for b, rb in rects[i + 1:]:
            inter = ra.intersected(rb)
            if inter.isEmpty() or ra.contains(rb) or rb.contains(ra):
                continue
            small = min(ra.width() * ra.height(), rb.width() * rb.height())
            if small > 0 and inter.width() * inter.height() / small > _OVERLAP_MIN:
                issues.append(Issue("box_overlap", a, inter, f"{_label_text(a)} · {_label_text(b)}".strip(" ·")))

    # 4. 상자를 지나가는 선(자기 양 끝 상자는 빼고)
    for it in arrows:
        _p0, _p1, b0, b1 = _arrow_ends(it)
        line = _arrow_polyline(it)
        for bx, r in rects:
            if bx is b0 or bx is b1:
                continue
            inner = r.adjusted(_THROUGH_INSET, _THROUGH_INSET, -_THROUGH_INSET, -_THROUGH_INSET)
            if inner.isEmpty():
                continue
            if any(_segment_hits_rect(a, b, inner) for a, b in zip(line, line[1:])):
                issues.append(Issue("line_through", it, inner, _label_text(bx)))
                break

    rank = {k: i for i, k in enumerate(KIND_ORDER)}
    issues.sort(key=lambda s: (rank[s.kind], round(s.where.center().y() / 20), s.where.center().x()))
    return issues


def summary(issues) -> str:
    """「연결 안 된 화살표 끝 2 · 겹친 상자 1」 — 없으면 빈 문자열."""
    counts = {k: 0 for k in KIND_ORDER}
    for s in issues:
        counts[s.kind] += 1
    return " · ".join(f"{KIND_TEXT[k]} {n}" for k, n in counts.items() if n)
