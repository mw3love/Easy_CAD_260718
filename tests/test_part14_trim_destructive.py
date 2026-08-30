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
    """[TRIM 자연 경계 곡선 확장, 2026-08-30 실사용 재현 이후 강화] 곡선 런 확장
    (`_curve_run_edges`) 도입 전엔 이 펜스 드래그가 심볼 자체는 지워도 근사 세그먼트
    단위로만 잘려 완전 소실은 Not-tested로 남겨뒀다 — 이제는 자연 경계 클릭 각각이
    그 곡선(타원 전체·호 전체) 전부를 한 번에 지우므로, 같은 4점 펜스 드래그로 아무
    잔여물 없이 완전히 사라짐까지 보장된다."""
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
    assert [it for it in w._scene.items() if isinstance(it, (_SymbolItem, _PolygonItem))] == []


# ---------------------------------------------------------------------------
# 실사용 재현 버그 3(2026-08-30, 같은 날 후속) — 저장소(원기둥) 심볼의 곡선(윗면 타원·
# 아랫면 호)이 커터 없이 클릭해도 근사 세그먼트 하나만 지워져 "군데군데 끊긴" 점선처럼만
# 트림됨. 원인: `_trim_candidate_segment`의 자연 경계가 변 하나 단위라 곡선 근사(수십
# 개 세그먼트)엔 사실상 무의미. 1차 시도(각도 기반 판정)는 벽→호 전환이 접선 방향이라
# 벽까지 삼켜버리는 더 나쁜 결과를 냈다(되돌림) — 최종 해법은 원본 QPainterPath 요소
# (`elementAt`)를 서브패스별로 직접 훑어 "진짜 lineTo/moveTo 모서리"만 hard로 잡는 것.
# ---------------------------------------------------------------------------

def test_curve_run_edges_grows_whole_ellipse_subpath():
    db = _SymbolItem("database", QRectF(0, 0, 200, 300))
    spans = _host_outline_edge_spans(db)
    ellipse_start, ellipse_end, closed = spans[0]
    assert closed is True
    run = _curve_run_edges(db, (ellipse_start + ellipse_end) // 2)
    assert len(run) == ellipse_end - ellipse_start   # 서브패스 전체(타원 전부)


def test_curve_run_edges_stops_at_wall_arc_boundary_not_the_walls():
    db = _SymbolItem("database", QRectF(0, 0, 200, 300))
    spans = _host_outline_edge_spans(db)
    body_start, body_end, closed = spans[1]
    assert closed is False
    mid = (body_start + body_end) // 2
    run = _curve_run_edges(db, mid)
    assert body_start not in run and (body_end - 1) not in run   # 양쪽 벽은 안 딸려옴
    assert len(run) > 1   # 호 근사 세그먼트 여럿은 하나로 묶임

    # 벽 자체를 클릭하면(그 변 자신) 확장이 안 일어나 그 변 하나만.
    assert _curve_run_edges(db, body_start) == [body_start]
    assert _curve_run_edges(db, body_end - 1) == [body_end - 1]


def test_natural_boundary_click_on_bottom_arc_removes_only_the_arc_via_view():
    """실사용 재현 정확한 시나리오 — 아랫면 호를 커터 없이 클릭하면 호만 사라지고
    양쪽 벽·윗면 타원은 그대로 남아야 한다(전엔 근사 조각 하나만 지워져 점선처럼
    보였다)."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    db = _SymbolItem("database", QRectF(0, 0, 200, 300))
    w._scene.addItem(db)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    bottom_arc_pt = QPointF(100, 298)   # 아랫면 호 한가운데
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, bottom_arc_pt, NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, bottom_arc_pt, L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, bottom_arc_pt, L, NB))

    assert db.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 3   # 왼쪽 벽(열림 2점) + 오른쪽 벽(열림 2점) + 윗면 타원(닫힘)
    closed_flags = sorted(f._closed for f in frags)
    assert closed_flags == [False, False, True]
    gids = {f._group_id for f in frags}
    assert len(gids) == 1 and None not in gids
    ellipse_frag = next(f for f in frags if f._closed)
    assert len(ellipse_frag.local_pts()) == 64   # 타원은 완전히 그대로


def test_natural_boundary_click_on_top_ellipse_removes_whole_ellipse_keeps_body_intact():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    db = _SymbolItem("database", QRectF(0, 0, 200, 300))
    w._scene.addItem(db)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    top_pt = QPointF(100, 0)   # 윗면 타원 꼭대기
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, top_pt, NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, top_pt, L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, top_pt, L, NB))

    assert db.scene() is None
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1   # 몸통(벽+호)이 하나도 안 잘려 그대로 한 조각
    assert frags[0]._closed is False
    assert len(frags[0].local_pts()) == 35   # 몸통 서브패스 34변 그대로(+1)


def test_curve_run_intelligence_propagates_to_fragment_after_first_cut():
    """[실사용 재현 4, 2026-08-30 같은 날 후속] 사용자가 정확히 이 순서로 재현: 몸통(호)을
    먼저 잘라 심볼이 조각난 뒤, 남은 윗면 타원을 또 자르면 — 더 이상 `_SymbolItem`이
    아니므로 예전처럼 근사 세그먼트 단위(점선)로 되돌아갔다. `_curve_hard_norm`을 조각에
    물려줘 두 번째 절단도 타원 전체를 한 번에 지워야 한다."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    db = _SymbolItem("database", QRectF(0, 0, 200, 300))
    w._scene.addItem(db)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    bottom_arc_pt = QPointF(100, 298)
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, bottom_arc_pt, NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, bottom_arc_pt, L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, bottom_arc_pt, L, NB))
    w._scene.clearSelection()

    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    ellipse_frag = next(f for f in frags if f._closed)
    assert getattr(ellipse_frag, "_curve_hard_norm", None)   # 조각에 물려받음

    top_pt = QPointF(100, 0)
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, top_pt, NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, top_pt, L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, top_pt, L, NB))

    assert ellipse_frag.scene() is None   # 근사 조각 하나가 아니라 타원 전체가 사라짐
    remaining = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(remaining) == 2   # 양쪽 벽(2점씩)만 남음
    assert all(not f._closed and len(f.local_pts()) == 2 for f in remaining)


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


# ---------------------------------------------------------------------------
# 실사용 재현 버그(2026-08-30, 같은 날 후속) — "사각형 한 변은 잘 지워지는데, 그렇게
# 생긴 다각형 상태에서 나머지 세 변은 트림이 안 먹는다." 원인: 열린 도형 TRIM의 기존
# "자유단 보호"(독립된 선을 한 번에 통째로 지우는 사고 방지, `_trim_candidate_open_
# segment`)가 방금 막 잘려나온 조각(`_trim_derived`)에도 그대로 적용돼, 남은 3변 중
# 자유단에 닿은 2변(가운데 변 제외)은 자연 경계로 영원히 못 지웠다.
# ---------------------------------------------------------------------------

def test_side_adjacent_to_free_end_is_trimmable_in_a_separate_gesture():
    """1단계 테스트(`test_erasing_all_four_edges_in_one_drag_deletes_the_item_entirely`)는
    한 번의 연속 드래그로 4변을 다 지웠다 — 이 테스트는 실사용처럼 **별도의 제스처**로
    한 변씩 지운다. 첫 절단 직후 생긴 자유단에 닿은 변(오른쪽)이 지워지는지가 핵심."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    # 1번째 제스처 — 위쪽 변 삭제(release로 확정, RectItem → 열린 PolygonItem 변환).
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    poly = frags[0]
    assert poly._trim_derived is True

    # 2번째 제스처(별도) — 오른쪽 변(자유단에 바로 닿은 변). 옛 버그에선 여기서 preview가
    # None이라 아무 일도 안 일어났다.
    right_mid = QPointF(600, 200)
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, right_mid, NB, NB))
    assert view._trim_preview is not None and view._trim_preview[0] == "open"
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, right_mid, L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, right_mid, L, NB))
    assert poly.scene() is w._scene   # 아직 다 안 지워졌으니 살아있어야 함
    assert len(poly.local_pts()) == 3   # 남은 두 변(아래+왼쪽)


def test_erasing_last_remaining_segment_across_separate_gestures_deletes_item():
    """오른쪽·왼쪽 변을 별도 제스처로 지운 뒤, 마지막 남은 한 변(가운데)까지 지우면
    완전 소실(아이템 delete)이어야 한다 — 옛 버그에선 이 마지막 변도 자유단 보호에
    걸려 조용히 무시됐다."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    for pt in (QPointF(300, 0), QPointF(600, 200), QPointF(0, 200), QPointF(300, 400)):
        view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, pt, NB, NB))
        view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, pt, L, L))
        view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, pt, L, NB))

    assert host.scene() is None
    assert [it for it in w._scene.items() if isinstance(it, (_RectItem, _PolygonItem))] == []


def test_progressive_multi_gesture_erasure_undo_chain_restores_original_rect():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    pts = (QPointF(300, 0), QPointF(600, 200), QPointF(0, 200), QPointF(300, 400))
    for pt in pts:
        view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, pt, NB, NB))
        view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, pt, L, L))
        view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, pt, L, NB))
    assert host.scene() is None

    for _ in range(len(pts)):
        w.undo()
    assert host.scene() is w._scene
    assert getattr(host, "_cuts", None) in (None, [])
    assert [it for it in w._scene.items() if isinstance(it, _PolygonItem)] == []


# ---------------------------------------------------------------------------
# 실사용 재현 버그 2(2026-08-30, 같은 날 후속) — 겹친 다른 도형이 근처에 있으면(커터
# 역할), TRIM 파괴적 조각의 자연 경계 판정이 꼭짓점을 넘어 여러 변을 한 번에 잡아버림
# ("첫 변 자르니 나머지 세 변이 한꺼번에 잘린다"). 원인: 열린 다각형 TRIM의 "cutter
# 사이 꼭짓점째로 지운다"는 규칙(진짜 자유형 폴리라인엔 맞는 설계)이 `_trim_derived`
# 조각에도 그대로 적용됐던 것 — 이제 트림 파생 조각은 클릭한 변 하나 안에서만 판정한다.
# ---------------------------------------------------------------------------

def test_natural_boundary_never_spans_past_a_corner_even_with_nearby_cutter():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    rect1 = _mk_pen_rect(w, x=0, y=0, ww=300, hh=300)
    _mk_pen_rect(w, x=150, y=150, ww=300, hh=300)   # 겹치는 도형 = 잠재적 cutter
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    # 오른쪽 변 위쪽 절반만 자연 경계로 잘림(커터가 y=150에서 걸침) — 5점짜리 열린 조각.
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(300, 100), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(300, 100), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(300, 100), L, NB))
    frags = [it for it in w._scene.items() if isinstance(it, _PolygonItem)]
    assert len(frags) == 1
    poly = frags[0]
    assert poly._trim_derived is True

    # 위쪽 변을 호버 — 옛 버그는 근처 cutter 탓에 왼쪽 변까지 한 번에 잡혔다. 이제는
    # 딱 그 변 하나(단일 세그먼트)만 후보로 잡혀야 한다.
    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(100, 0), NB, NB))
    kind, tp_host, (seg_lo, t_lo), (seg_hi, t_hi) = view._trim_preview
    assert kind == "open" and tp_host is poly
    assert seg_lo == seg_hi   # 단일 세그먼트 — 꼭짓점을 넘어가지 않음
    assert abs(t_lo - 0.0) < 1e-6 and abs(t_hi - 1.0) < 1e-6

    before_pts = len(poly.local_pts())
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(100, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(100, 0), L, NB))
    assert poly.scene() is w._scene   # 통째로 사라지지 않고 살아있어야 함
    assert len(poly.local_pts()) == before_pts - 1   # 변 하나(꼭짓점 1개)만 줄어듦


# ---------------------------------------------------------------------------
# 실사용 재현 버그 5(2026-08-30, 같은 날 후속) — SVG로 들여온 다중 조각 그림(고양이)의
# 낱개 선 조각들이 커터 없이는 하나도 안 지워짐. 원인: 자유단 보호(2026-08-28)가 그룹에
# 속한 조각에도 그대로 적용됨 — "독립된 선 하나"가 아니라 "더 큰 그림의 부품"이라는
# 사용자 판단으로 그룹 소속 항목은 이 보호를 우회하도록 확장(`_trim_allows_full_erase`).
# 그룹 밖의 진짜 독립된 낱개 선은 여전히 보호 대상 그대로 유지.
# ---------------------------------------------------------------------------

def test_grouped_standalone_line_erases_without_cutter():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    line = _LineItem(QLineF(0, 0, 100, 0))
    line._group_id = "cat_group"
    w._scene.addItem(line)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(50, 0), NB, NB))
    assert view._trim_preview is not None and view._trim_preview[0] == "open"
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(50, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(50, 0), L, NB))

    assert line.scene() is None
    w.undo()
    assert line.scene() is w._scene   # undo로 완전 복원


def test_ungrouped_standalone_line_still_protected_from_full_erase():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    line = _LineItem(QLineF(0, 0, 100, 0))   # group_id 없음 — 진짜 독립된 선
    w._scene.addItem(line)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(50, 0), NB, NB))
    assert view._trim_preview is None   # 커터 없이는 후보 자체가 안 잡힘(기존 보호 유지)
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(50, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(50, 0), L, NB))
    assert line.scene() is w._scene   # 그대로 유지


# ---------------------------------------------------------------------------
# 실사용 재현 버그 5 후속(2026-08-30, 같은 날 후속) — `_PathItem`(펜 궤적·DXF 베지어
# 폴백·SVG 곡선 공용)은 §8 항목17 원안에서 TRIM 범위 밖으로 확정됐었으나, 고양이 SVG의
# "펜" 조각이 이 클래스로 매핑돼 위 그룹 완화와 짝을 맞추지 못하면 여전히 안 지워진다는
# 사용자 확인 후 추가. 커터 역할은 여전히 제외 — TRIM 대상(host)으로만 확장.
# ---------------------------------------------------------------------------

def _mk_path_item(w, pts, group_id=None):
    path = QPainterPath()
    path.moveTo(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    it = _PathItem(path)
    if group_id is not None:
        it._group_id = group_id
    w._scene.addItem(it)
    return it


def test_grouped_single_segment_path_item_erases_without_cutter():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    p = _mk_path_item(w, [QPointF(0, 0), QPointF(100, 0)], group_id="cat_group")
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(50, 0), NB, NB))
    assert view._trim_preview is not None and view._trim_preview[0] == "open"
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(50, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(50, 0), L, NB))

    assert p.scene() is None
    w.undo()
    assert p.scene() is w._scene


def test_ungrouped_path_item_still_protected_from_full_erase():
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    p = _mk_path_item(w, [QPointF(0, 0), QPointF(100, 0)])   # group_id 없음
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(50, 0), NB, NB))
    assert view._trim_preview is None
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(50, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(50, 0), L, NB))
    assert p.scene() is w._scene


def test_multi_segment_path_item_natural_boundary_shortens_not_fully_erases():
    """세그먼트가 여럿인 펜 궤적은 그룹 완화가 있어도 클릭한 세그먼트 하나만 지워지고
    나머지는 남는다(전체 소실은 아니다) — 자유단 보호 완화는 "완전 소실 허용" 게이트일
    뿐, 다중 세그먼트를 한꺼번에 지우는 것과는 별개."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    p = _mk_path_item(w, [QPointF(0, 0), QPointF(50, 20), QPointF(100, 0)], group_id="cat_group")
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(25, 10), NB, NB))
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(25, 10), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(25, 10), L, NB))

    assert p.scene() is w._scene   # 완전 소실 아님 — 일부만 잘림
    remaining = p.path().toSubpathPolygons()[0]
    assert remaining.count() == 2   # 첫 세그먼트만 잘려나가고 나머지 한 변만 남음


def test_multi_subpath_path_item_is_not_a_trim_target():
    """[실사용 재현, 2026-08-30 같은 날 후속] 서브패스 2개짜리 펜(예: 코 삼각형 서브패스
    + 입 곡선 서브패스가 한 `_PathItem`에 같이 들어있는 경우) — 첫 서브패스만 골라
    자르면 나머지 서브패스가 `setPath()`에 통째로 사라진다("펜이 끊김" 보고). 부분
    지원으로 데이터를 조용히 파괴하느니 아예 트림 대상에서 뺀다."""
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    w = CanvasWindow(); w.grid_enabled = False
    path = QPainterPath()
    path.moveTo(0, 0)
    path.lineTo(100, 0)
    path.moveTo(0, 50)   # 두 번째 서브패스 — 별개의 선
    path.lineTo(100, 50)
    p = _PathItem(path)
    p._group_id = "cat_group"
    w._scene.addItem(p)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    view.mouseMoveEvent(_ev(view, QEvent.Type.MouseMove, QPointF(50, 0), NB, NB))
    assert view._trim_preview is None   # 후보 자체가 안 잡힘
    view.mousePressEvent(_ev(view, QEvent.Type.MouseButtonPress, QPointF(50, 0), L, L))
    view.mouseReleaseEvent(_ev(view, QEvent.Type.MouseButtonRelease, QPointF(50, 0), L, NB))

    assert p.scene() is w._scene
    assert len(p.path().toSubpathPolygons()) == 2   # 두 서브패스 모두 그대로 보존
