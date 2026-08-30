"""TRIM 근본 재설계(비파괴 `_cuts` → 파괴적 기하 변경) 1단계 — `_RectItem`.

2026-08-30 deep-interview 확정 설계: 닫힌 사각형이 잘리면(TRIM 제스처가 끝나는 순간)
실제로 `_PolygonItem`(열림)으로 변환되거나(부분 잔존), 아이템 자체가 delete된다(테두리
전체 소실) — 기존 `shape()`가 원본 미트림 기하를 그대로 써서 "안 보이는데 드래그로 선택된다"
는 유령 선택 버그의 근본 수정. 포트는 비파괴로 유지(범위 밖), 원/심볼/닫힌 다각형은 다음
단계에서 순차 전환 예정 — 이 파일은 `_RectItem`만 다룬다.

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
from PyQt6.QtGui import QMouseEvent
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
