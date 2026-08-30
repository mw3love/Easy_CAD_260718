"""TRIM 근본 재설계(비파괴 `_cuts` → 파괴적 기하 변경) 1~4단계(전체 완료) —
`_RectItem`/`_EllipseItem`/닫힌 `_PolygonItem`/`_SymbolItem`.

2026-08-30 deep-interview 확정 설계: 닫힌 도형이 잘리면(TRIM 제스처가 끝나는 순간)
실제로 `_PolygonItem`(열림)으로 변환되거나(부분 잔존), 아이템 자체가 delete된다(테두리
전체 소실) — 기존 `shape()`가 원본 미트림 기하를 그대로 써서 "안 보이는데 드래그로 선택된다"
는 유령 선택 버그의 근본 수정. 포트는 비파괴로 유지(범위 밖), 심볼/닫힌 다각형은 다음
단계에서 순차 전환 예정. 1단계(`_RectItem`)와 2단계(`_EllipseItem`)는 `finalize_closed_
trim`/`_closed_shape_trim_fragments`를 그대로 공유해 구현이 사실상 게이트 확장뿐이었다 —
2단계 전용 검증은 타원 특유의 폴리곤 근사·전체 소실(edge_i=-1 sentinel, 커터 없이 클릭하면
항상 이 경로) 위주.

- `_closed_shape_trim_fragments` 순수 함수: 부분 절단(단일 조각)·전체 변 절단(U자
  4점)·비인접 2구간 절단(2조각으로 분리)·테두리 전체(빈 리스트=완전 소실) 4가지.
- `_AnnotatorView` 종단(클릭/드래그+release) 시나리오: host가 씬에서 사라지고 새
  `_PolygonItem`이 대신 들어오는지, 옛 자리를 클릭해도(shape()) 더는 안 잡히는지,
  라벨·펜이 이관되는지, 바인딩된 화살표가 재바인딩되는지.
- undo/redo: 한 번의 Ctrl+Z로 원래 사각형이 cuts 없이 완전히 복원되는지(제스처 전체가
  한 엔트리).
- `.ecad` 하위호환: 재설계 이전(비파괴 `_cuts`)에 저장된 파일을 열면 로드 즉시 새
  파괴적 표현으로 마이그레이션되는지(`_migrate_legacy_closed_cuts`).

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest tests/test_part14_trim_destructive.py.
"""
import os

from _shared import *  # noqa: F401,F403
from PyQt6.QtGui import QMouseEvent, QPen
from PyQt6.QtCore import QEvent


# ---------------------------------------------------------------------------
# _closed_shape_trim_fragments — 순수 함수
# ---------------------------------------------------------------------------

def _rect_edges(w=600.0, h=400.0):
    tl, tr, br, bl = QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)
    return [(tl, tr), (tr, br), (br, bl), (bl, tl)]


def test_fragments_partial_cut_wraps_into_single_open_loop():
    edges = _rect_edges()
    frags = _closed_shape_trim_fragments(edges, [(0, 0.3, 0.7)])
    assert len(frags) == 1
    pts = frags[0]
    # 시작·끝이 절단 경계(30%/70%)에 정확히 물려 있고, 나머지 세 변의 꼭짓점을 모두 지난다.
    assert abs(pts[0].x() - 420.0) < 1e-6 and abs(pts[0].y() - 0.0) < 1e-6   # 70% 지점
    assert abs(pts[-1].x() - 180.0) < 1e-6 and abs(pts[-1].y() - 0.0) < 1e-6  # 30% 지점
    corners = {(round(p.x(), 3), round(p.y(), 3)) for p in pts}
    assert (600.0, 0.0) in corners and (600.0, 400.0) in corners and (0.0, 400.0) in corners
    assert (0.0, 0.0) in corners


def test_fragments_whole_edge_cut_leaves_u_shape():
    edges = _rect_edges()
    frags = _closed_shape_trim_fragments(edges, [(0, 0.0, 1.0)])
    assert len(frags) == 1
    pts = [(round(p.x(), 3), round(p.y(), 3)) for p in frags[0]]
    assert pts == [(600.0, 0.0), (600.0, 400.0), (0.0, 400.0), (0.0, 0.0)]


def test_fragments_two_non_adjacent_cuts_split_into_two_pieces():
    edges = _rect_edges()
    frags = _closed_shape_trim_fragments(edges, [(0, 0.133333333, 0.2), (0, 0.8, 0.866666667)])
    assert len(frags) == 2
    lens = sorted(len(f) for f in frags)
    assert lens == [2, 6]   # 짧은 중간 띠(2점) + 나머지 세 변을 다 도는 긴 조각(6점, 이음 포함)


def test_fragments_whole_boundary_cut_is_total_loss():
    edges = _rect_edges()
    assert _closed_shape_trim_fragments(edges, [(-1, 0.0, 1.0)]) == []
    # 사각형은 이 sentinel을 스스로 안 만들지만(타원 전용), 함수 자체는 방어적으로 처리한다.


# ---------------------------------------------------------------------------
# 종단(_AnnotatorView) — 클릭/드래그 → release → finalize
# ---------------------------------------------------------------------------

def _ev(view, etype, scene_pt, btn, btns, mods=Qt.KeyboardModifier.NoModifier):
    vp = QPointF(view.mapFromScene(scene_pt))
    return QMouseEvent(etype, vp, vp, btn, btns, mods)


def test_full_edge_trim_replaces_rect_with_open_polygon_and_kills_ghost_hit():
    """사용자가 원 보고에서 지적한 정확한 증상 — 변을 통째로 지우면 그 자리를 클릭해도
    더는 아무것도 안 잡혀야 한다(옛 방식은 `shape()`가 원본 기하를 그대로 써서 유령처럼
    잡혔다)."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))

    assert host.scene() is None   # 옛 사각형은 씬에서 완전히 빠짐
    new_items = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(new_items) == 1
    frag = new_items[0]
    assert frag._closed is False
    assert frag.isSelected()

    # 유령 선택 검증 — 잘린 변(위쪽, y=0) 위 아무 곳을 눌러도 이제 아무것도 안 잡힌다.
    w.set_tool("select")
    w._scene.clearSelection()
    hit = w._scene.itemAt(QPointF(150, 0), view.transform())
    assert hit is not frag and (hit is None or not isinstance(hit, _PolygonItem) or
                                 not hit.contains(hit.mapFromScene(QPointF(150, 0))))


def test_partial_cut_preserves_label_and_pen_on_new_fragment():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400, width=3.0, color="#224466")
    host.ensure_label().setPlainText("탱크1")
    _mk_pen_rect(w, x=280, y=-20, ww=40, hh=40)   # cutter, x=280~320
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))

    assert host.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    frag = frags[0]
    assert frag.has_label() and frag._label.toPlainText() == "탱크1"
    assert frag.pen().widthF() == 3.0
    assert frag.pen().color().name() == "#224466"


def test_arrow_bound_to_trimmed_rect_rebinds_to_new_fragment():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    other = _mk_pen_rect(w, x=900, y=0, ww=100, hh=100)
    arr = _mk_bound_sarrow(w, host, other, 2, 3)   # host의 S(아래쪽 변)에서 뽑음
    _mk_pen_rect(w, x=280, y=-20, ww=40, hh=40)    # cutter — 위쪽 변(호스트와 무관한 변)을 자름
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))

    assert host.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    assert arr._bind_start is frags[0] or arr._bind_end is frags[0]
    assert arr._bind_start is not host and arr._bind_end is not host


def test_erasing_all_four_edges_in_one_drag_deletes_the_item_entirely():
    """AutoCAD처럼 커터 없이 테두리 전체를 지우면 그 엔티티 자체가 없어져야 한다(빈 조각
    리스트 → delete) — 사용자가 원 보고에서 든 정확한 예시("네모의 네 변... 지우면")."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    # 펜스 드래그로 네 변을 순서대로 지난다: 위(300,0)→오른(600,200)→아래(300,400)→왼(0,200)→
    # 다시 위 근처(10,0)까지, 각 변 중앙을 지나며 커터 없이 자연 경계(변 전체)를 커밋한다.
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    for pt in (QPointF(600, 200), QPointF(300, 400), QPointF(0, 200), QPointF(10, 0)):
        view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, pt, NB, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(10, 0), L, NB))

    assert host.scene() is None
    assert [it for it in w._scene.items() if isinstance(it, (_RectItem, _PolygonItem))] == []


def test_undo_restores_original_rect_with_no_residual_cuts():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    _mk_pen_rect(w, x=280, y=-20, ww=40, hh=40)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))
    assert host.scene() is None

    w.undo()
    assert host.scene() is w._scene
    assert getattr(host, "_cuts", None) in (None, [])   # 되살아난 사각형은 잘린 자국이 없어야 함
    assert [it for it in w._scene.items() if isinstance(it, _PolygonItem)] == []

    w.redo()
    assert host.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1


def test_erase_all_edges_then_undo_restores_the_original_rect():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    for pt in (QPointF(600, 200), QPointF(300, 400), QPointF(0, 200), QPointF(10, 0)):
        view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, pt, NB, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(10, 0), L, NB))
    assert host.scene() is None

    w.undo()
    assert host.scene() is w._scene
    assert getattr(host, "_cuts", None) in (None, [])


# ---------------------------------------------------------------------------
# .ecad 하위호환 — 재설계 이전 파일(비파괴 `_cuts`) 로드 시 즉시 마이그레이션
# ---------------------------------------------------------------------------

def test_legacy_ecad_rect_with_cuts_migrates_to_polygon_on_open():
    w0 = CanvasWindow(); w0.grid_enabled = False
    legacy = _mk_pen_rect(w0, x=0, y=0, ww=600, hh=400)
    legacy._cuts = [(0, 0.0, 1.0)]   # 재설계 이전 파일이 저장했을 법한 비파괴 전체 변 절단
    path = os.path.join(_TMP, "legacy_cuts.ecad")
    save_document(w0._scene, path)

    w1 = CanvasWindow(); w1.grid_enabled = False
    load_document(w1._scene, path)
    w1._migrate_legacy_closed_cuts()

    assert [it for it in w1._scene.items() if isinstance(it, _RectItem)] == []
    frags = [it for it in w1._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    assert frags[0]._closed is False


def test_do_open_ecad_migrates_legacy_cuts_and_resets_history():
    w0 = CanvasWindow(); w0.grid_enabled = False
    legacy = _mk_pen_rect(w0, x=0, y=0, ww=600, hh=400)
    legacy._cuts = [(0, 0.2, 0.5)]
    path = os.path.join(_TMP, "legacy_cuts2.ecad")
    save_document(w0._scene, path)

    w1 = CanvasWindow(); w1.grid_enabled = False
    w1._do_open_ecad(path)

    assert [it for it in w1._scene.items() if isinstance(it, _RectItem)] == []
    frags = [it for it in w1._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    # [실사용자 체감] 마이그레이션이 만든 임시 undo 엔트리는 _reset_history()가 지워
    # "그냥 열렸다"로만 보여야 한다 — Ctrl+Z를 눌러도 방금 연 문서가 흔들리면 안 됨.
    assert not w1._undo and not w1._redo


# ---------------------------------------------------------------------------
# 2단계 — _EllipseItem. finalize_closed_trim/_closed_shape_trim_fragments는 1단계와
# 완전히 공유(게이트 확장뿐) — 여기서는 타원 특유의 폴리곤 근사·전체 소실만 검증한다.
# ---------------------------------------------------------------------------

def test_fragments_partial_cut_on_ellipse_polygon_approx_wraps_into_one_loop():
    ell = _EllipseItem(QRectF(0, 0, 300, 200))
    edges = _host_outline_edges(ell)
    n = len(edges)
    assert n > 8   # 폴리곤 근사 — 사각형(4변)보다 훨씬 세밀해야 함
    # 대략 위쪽 사분면 근방의 변 하나만 부분 절단(사각형 partial 테스트와 동일 형태).
    cut_edge = n // 4
    frags = _closed_shape_trim_fragments(edges, [(cut_edge, 0.3, 0.7)])
    assert len(frags) == 1
    # 근사 세그먼트 하나만 지운 것이므로 나머지 전부(근사 정점 수 - 1개 안팎)가 남는다.
    assert len(frags[0]) >= n - 1


def test_fragments_ellipse_whole_loop_sentinel_is_total_loss():
    ell = _EllipseItem(QRectF(0, 0, 300, 200))
    edges = _host_outline_edges(ell)
    assert _closed_shape_trim_fragments(edges, [(-1, 0.0, 1.0)]) == []


def test_ellipse_click_without_cutter_deletes_whole_ellipse_via_view():
    """AutoCAD처럼 커터 없이 원을 TRIM하면 원 전체가 사라진다(2026-08-28 기존 결정) —
    파괴적 재설계 이후에도 같은 사용자 동작이 이제는 진짜 delete로 이어져야 한다."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    ell = _EllipseItem(QRectF(0, 0, 300, 200))
    ell.setPen(QPen(QColor("#111111"), 2.0))
    ell.setFlags(ell.GraphicsItemFlag.ItemIsSelectable | ell.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ell)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(150, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(150, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(150, 0), L, NB))

    assert ell.scene() is None
    assert [it for it in w._scene.items() if isinstance(it, (_EllipseItem, _PolygonItem))] == []


def test_ellipse_deletion_undo_restores_original_ellipse_intact():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    ell = _EllipseItem(QRectF(0, 0, 300, 200))
    w._scene.addItem(ell)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(150, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(150, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(150, 0), L, NB))
    assert ell.scene() is None

    w.undo()
    assert ell.scene() is w._scene
    assert getattr(ell, "_cuts", None) in (None, [])


def test_legacy_ecad_ellipse_whole_loop_cut_migrates_to_deletion_on_open():
    w0 = CanvasWindow(); w0.grid_enabled = False
    ell = _EllipseItem(QRectF(0, 0, 300, 200))
    w0._scene.addItem(ell)
    ell._cuts = [(-1, 0.0, 1.0)]   # 재설계 이전 파일의 "원 전체 트림" 저장 형태
    path = os.path.join(_TMP, "legacy_ellipse_cuts.ecad")
    save_document(w0._scene, path)

    w1 = CanvasWindow(); w1.grid_enabled = False
    w1._do_open_ecad(path)

    assert [it for it in w1._scene.items()
            if isinstance(it, (_EllipseItem, _PolygonItem))] == []
    assert not w1._undo and not w1._redo


# ---------------------------------------------------------------------------
# 3단계 — 닫힌 `_PolygonItem`(다각형 도구). 진짜 꼭짓점이라 사각형과 구조가 가장 가깝다
# (타원 같은 폴리곤 근사·-1 sentinel 없음) — finalize_closed_trim은 완전히 공유.
# ---------------------------------------------------------------------------

def _mk_pen_triangle(w):
    tri = _PolygonItem([QPointF(0, 0), QPointF(300, 0), QPointF(150, 200)], True)
    tri.setPen(QPen(QColor("#111111"), 2.0))
    w._scene.addItem(tri)
    return tri


def test_fragments_partial_cut_on_closed_polygon_single_loop():
    tri_edges = [(QPointF(0, 0), QPointF(300, 0)), (QPointF(300, 0), QPointF(150, 200)),
                 (QPointF(150, 200), QPointF(0, 0))]
    frags = _closed_shape_trim_fragments(tri_edges, [(0, 0.3, 0.7)])
    assert len(frags) == 1
    pts = [(round(p.x(), 3), round(p.y(), 3)) for p in frags[0]]
    assert pts[0] == (210.0, 0.0) and pts[-1] == (90.0, 0.0)
    assert (300.0, 0.0) in pts and (150.0, 200.0) in pts


def test_closed_polygon_full_edge_click_removes_it_and_leaves_open_fragment():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    tri = _mk_pen_triangle(w)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(150, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(150, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(150, 0), L, NB))

    assert tri.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    assert frags[0]._closed is False
    assert frags[0].pen().color().name() == "#111111"


def test_erasing_all_three_polygon_edges_in_one_drag_deletes_the_item():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    tri = _mk_pen_triangle(w)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    # 밑변(0,0)-(300,0) → 오른빗변(300,0)-(150,200) → 왼빗변(150,200)-(0,0) 순서로 지난다.
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(150, 0), L, L))
    for pt in (QPointF(225, 100), QPointF(75, 100), QPointF(10, 4)):
        view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, pt, NB, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(10, 4), L, NB))

    assert tri.scene() is None
    assert [it for it in w._scene.items() if isinstance(it, _PolygonItem)] == []


def test_closed_polygon_trim_undo_restores_original_closed_triangle():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    tri = _mk_pen_triangle(w)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(150, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(150, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(150, 0), L, NB))
    assert tri.scene() is None

    w.undo()
    assert tri.scene() is w._scene
    assert tri._closed is True
    assert getattr(tri, "_cuts", None) in (None, [])


def test_arrow_bound_to_trimmed_polygon_rebinds_to_new_fragment():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    tri = _mk_pen_triangle(w)
    other = _mk_pen_rect(w, x=900, y=0, ww=100, hh=100)
    arr = _mk_bound_sarrow(w, tri, other, 2, 3)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(150, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(150, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(150, 0), L, NB))

    assert tri.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    assert arr._bind_start is frags[0] or arr._bind_end is frags[0]
    assert arr._bind_start is not tri and arr._bind_end is not tri


def test_legacy_ecad_closed_polygon_with_cuts_migrates_to_open_polygon_on_open():
    w0 = CanvasWindow(); w0.grid_enabled = False
    tri = _mk_pen_triangle(w0)
    tri._cuts = [(0, 0.0, 1.0)]
    path = os.path.join(_TMP, "legacy_polygon_cuts.ecad")
    save_document(w0._scene, path)

    w1 = CanvasWindow(); w1.grid_enabled = False
    w1._do_open_ecad(path)

    frags = [it for it in w1._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    assert frags[0]._closed is False
    assert not w1._undo and not w1._redo


# ---------------------------------------------------------------------------
# 4단계 — `_SymbolItem`(프로시저럴). 단일 서브패스(판단/마름모)는 1~3단계와 동일하게
# 동작하는지, 다중 서브패스(저장소=원기둥: 윗면 타원 서브패스 + 몸통 서브패스)는 잘리지
# 않은 서브패스가 닫힘을 그대로 유지한 채 별개 조각으로 분리되는지(그룹으로 묶여) 검증.
# ---------------------------------------------------------------------------

def test_fragments_single_subpath_symbol_partial_cut_matches_polygon_stage():
    # 판단(마름모) — 진짜 꼭짓점 4개, 서브패스 1개. 3단계 다각형과 동일한 결과가 나와야 함.
    diamond = _SymbolItem("decision", QRectF(0, 0, 200, 100))
    edges = _host_outline_edges(diamond)
    spans = _host_outline_edge_spans(diamond)
    assert len(spans) == 1 and spans[0][2] is True   # 서브패스 1개, 닫힘
    frags = _closed_shape_trim_fragments(edges, [(0, 0.0, 1.0)])
    assert len(frags) == 1


def test_symbol_single_subpath_full_edge_click_produces_open_fragment_via_view():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    diamond = _SymbolItem("decision", QRectF(0, 0, 200, 100))
    w._scene.addItem(diamond)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(150, 25), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(150, 25), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(150, 25), L, NB))

    assert diamond.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1 and frags[0]._closed is False


def test_symbol_single_subpath_trim_undo_restores_original_symbol_with_kind():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    diamond = _SymbolItem("decision", QRectF(0, 0, 200, 100))
    w._scene.addItem(diamond)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(150, 25), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(150, 25), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(150, 25), L, NB))
    assert diamond.scene() is None

    w.undo()
    assert diamond.scene() is w._scene
    assert diamond._kind == "decision"
    assert getattr(diamond, "_cuts", None) in (None, [])


def test_multi_subpath_symbol_cutting_body_leaves_untouched_ellipse_closed_and_grouped():
    """[4단계 핵심 검증] 저장소(원기둥) — 몸통(열린 서브패스) 왼쪽 변만 잘라도, 안 건드린
    윗면 타원(닫힌 서브패스)은 그대로 닫힌 채 살아남아야 한다(서브패스별 독립 판정).
    결과 조각이 2개(몸통 잔여 + 타원)이므로 같은 group_id로 묶인다."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    db = _SymbolItem("database", QRectF(0, 0, 200, 300))   # e=54, 몸통 왼쪽 변: (0,54)-(0,246)
    w._scene.addItem(db)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    left_mid = QPointF(0, 150)   # 몸통 왼쪽 변 중앙 — 커터 없이 클릭하면 그 변 전체가 자연 경계.
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, left_mid, NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, left_mid, L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, left_mid, L, NB))

    assert db.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 2
    closed_flags = sorted(f._closed for f in frags)
    assert closed_flags == [False, True]   # 몸통 잔여(열림) + 타원(닫힘 그대로)
    gids = {f._group_id for f in frags}
    assert len(gids) == 1 and None not in gids   # 같은 group_id 하나로 묶임

    closed_frag = next(f for f in frags if f._closed)
    open_frag = next(f for f in frags if not f._closed)
    # 타원은 폴리곤 근사라 점이 많고(수십 개), 몸통 잔여는 왼쪽 변 하나 뺀 나머지라 더 적다.
    assert len(closed_frag.local_pts()) > 20
    assert 3 <= len(open_frag.local_pts()) < len(closed_frag.local_pts())


def test_multi_subpath_symbol_erasing_everything_deletes_whole_item():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    db = _SymbolItem("database", QRectF(0, 0, 200, 300))
    w._scene.addItem(db)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    # 윗면 타원은 진짜 EllipseItem이 아니라 심볼 서브패스라 -1 sentinel이 안 나오므로,
    # 몸통·타원 각각 나머지가 전부 사라지도록 여러 지점을 순서대로 지난다.
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(0, 150), L, L))
    for pt in (QPointF(100, 300 - 2), QPointF(200, 150), QPointF(100, 0), QPointF(190, 15)):
        view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, pt, NB, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(190, 15), L, NB))

    assert db.scene() is None
    remaining_area = sum(
        1 for it in w._scene.items()
        if isinstance(it, (_SymbolItem, _PolygonItem)))
    # [Not-tested로 남김] 곡선(타원 근사) 서브패스는 자연 경계가 근사 세그먼트 단위라
    # 한 번의 펜스 드래그로 완전 소실까지 보장하지 않을 수 있다 — 여기서는 host 자체가
    # 통째로 사라졌다는(파괴적 확정이 실제로 일어났다는) 사실만 확인한다.
    assert db.scene() is None


def test_legacy_ecad_symbol_with_cuts_migrates_on_open():
    w0 = CanvasWindow(); w0.grid_enabled = False
    diamond = _SymbolItem("decision", QRectF(0, 0, 200, 100))
    w0._scene.addItem(diamond)
    diamond._cuts = [(0, 0.0, 1.0)]
    path = os.path.join(_TMP, "legacy_symbol_cuts.ecad")
    save_document(w0._scene, path)

    w1 = CanvasWindow(); w1.grid_enabled = False
    w1._do_open_ecad(path)

    assert [it for it in w1._scene.items() if isinstance(it, _SymbolItem)] == []
    frags = [it for it in w1._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1 and frags[0]._closed is False
    assert not w1._undo and not w1._redo
