"""§8 항목 — 그룹 프레임(2026-08-25 deep-interview: "svg 등 그룹을 이미지처럼 하나의 틀로
포트닷/큐닷 적용"). 대상은 `_group_id`를 가진 모든 그룹(Ctrl+G 임의 조합 포함). 화살표는
그룹 자체(group_id 문자열)를 직접 참조하는 `_GroupBindProxy`에 지속 연결되고, 포트 위치는
그때그때 그룹 멤버들의 tight bbox에서 라이브로 계산된다(실체 있는 새 아이템 없음). 범위는
포트닷·큐닷·화살표 부착까지만 — TRIM/EXTEND는 그룹 프레임을 대상/커터로 삼지 않는다.

`tests/test_easycad.py` 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part8_group_frame.py.
"""
from _shared import *  # noqa: F401,F403
from easycad.canvas.annotator_core import (
    _GroupBindProxy, _group_members, _group_bbox_scene,
    regroup_duplicated_items, remap_grouped_bindings,
)


def _mk_group(w, group_id="g1"):
    """서로 떨어진 사각형 2개를 같은 group_id로 묶어 반환(합집합 bbox: (0,0)-(220,60))."""
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 120, 0, 100, 60)
    a._group_id = b._group_id = group_id
    return a, b


def test_group_bbox_scene_is_union_of_members():
    # `_content_rect()` 기본 폴백은 펜 폭의 절반만큼 살짝 부풀린 값이라(기존 `_group_scene_
    # rect`와 동일 관례) 정확히 0이 아니라 그 근방이면 된다.
    w = CanvasWindow()
    a, b = _mk_group(w)
    box = _group_bbox_scene(_group_members(w._scene, "g1"))
    assert _close(box.topLeft(), QPointF(0, 0), eps=1.0)
    assert _close(box.bottomRight(), QPointF(220, 60), eps=1.0)


def test_group_members_excludes_other_groups_and_ungrouped():
    w = CanvasWindow()
    a, b = _mk_group(w, "g1")
    c = _mk_rect(w._scene, w.make_pen(), 500, 500, 40, 40)   # 그룹 없음
    d = _mk_rect(w._scene, w.make_pen(), 600, 600, 40, 40)
    d._group_id = "g2"
    members = _group_members(w._scene, "g1")
    assert set(members) == {a, b}


def _has_close(pts, target, eps=1.0):
    return any(_close(p, target, eps=eps) for p in pts)


def test_group_bind_proxy_ports_match_live_bbox_and_track_moves():
    w = CanvasWindow()
    a, b = _mk_group(w)
    proxy = _GroupBindProxy(w._scene, "g1")
    ports = _shape_ports(proxy)
    assert len(ports) == 4
    pts = [sp for sp, _n in ports]
    assert _has_close(pts, QPointF(110, 0))    # N: 합집합 bbox 위쪽 변 중점
    assert _has_close(pts, QPointF(220, 30))   # E
    assert _has_close(pts, QPointF(110, 60))   # S
    assert _has_close(pts, QPointF(0, 30))     # W
    # 멤버 하나를 옮기면(=그룹 전체 이동을 흉내) bbox·포트가 즉시 새 값을 반영한다(라이브 계산).
    a.moveBy(50, 0); b.moveBy(50, 0)
    pts2 = [sp for sp, _n in _shape_ports(proxy)]
    assert _has_close(pts2, QPointF(160, 0))


def test_group_bind_proxy_scene_none_when_group_empty():
    w = CanvasWindow()
    proxy = _GroupBindProxy(w._scene, "no-such-group")
    assert proxy.scene() is None
    assert proxy.mapToScene(QPointF(0.5, 0.5)) == QPointF(0.5, 0.5)   # 안전 폴백(그대로 반환)


def test_border_snap_at_targets_group_frame_not_individual_member():
    w = CanvasWindow(); w.grid_enabled = False
    a, b = _mk_group(w)
    w._scene.clearSelection()
    w.set_tool("arrow")
    # 오른쪽 조각(b)의 우측 변 중점 근처 — 낱개라면 b에 붙어야 하지만, 그룹이므로 그룹 전체
    # bbox의 우측 변(220,30)에 붙어야 한다(=이미지처럼 "하나의 틀" 취급).
    snap = w._view._border_snap_at(w._view.mapFromScene(QPointF(220, 30)))
    assert snap is not None
    sp, _n, host = snap
    assert isinstance(host, _GroupBindProxy)
    assert host.group_id == "g1"
    assert _close(sp, QPointF(220, 30), eps=1.0)


def test_port_dot_target_returns_group_proxy_for_unselected_member():
    w = CanvasWindow(); w.grid_enabled = False
    a, b = _mk_group(w)
    w._scene.clearSelection()
    target = w._view._port_dot_target(QPointF(220, 30))
    assert isinstance(target, _GroupBindProxy)
    assert target.group_id == "g1"


def test_port_dot_target_none_when_group_selected():
    w = CanvasWindow(); w.grid_enabled = False
    a, b = _mk_group(w)
    a.setSelected(True)   # 그룹 동기화가 b도 함께 선택시킴(host_selection._sync_group_selection)
    assert b.isSelected()
    assert w._view._port_dot_target(QPointF(220, 30)) is None


def test_arrow_bound_to_group_proxy_follows_whole_group_move():
    w = CanvasWindow()
    a, b = _mk_group(w)
    proxy = _GroupBindProxy(w._scene, "g1")
    arrow = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    start = QPointF(-100, 30)
    arrow.set_points(start, QPointF(0, 30))
    arrow.setFlags(arrow.GraphicsItemFlag.ItemIsSelectable | arrow.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(arrow)
    arrow.set_bound(1, proxy, proxy.mapFromScene(QPointF(0, 30)))   # 그룹 W변 중점에 부착
    assert arrow.reroute() is False   # 이미 그 자리라 무변화

    a.moveBy(200, 40); b.moveBy(200, 40)   # 그룹 전체를 함께 옮김(현재 구조상 항상 같이 움직임)
    assert arrow.reroute() is True
    assert _close(arrow.mapToScene(arrow._endpoints()[1]), QPointF(200, 70))


def test_group_bound_arrow_survives_ecad_roundtrip():
    w = CanvasWindow()
    a, b = _mk_group(w)
    proxy = _GroupBindProxy(w._scene, "g1")
    arrow = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    arrow.set_points(QPointF(-100, 30), QPointF(0, 30))
    arrow.setFlags(arrow.GraphicsItemFlag.ItemIsSelectable | arrow.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(arrow)
    arrow.set_bound(1, proxy, proxy.mapFromScene(QPointF(0, 30)))

    path = os.path.join(_TMP, f"group_bind_{uuid.uuid4().hex}.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    n = load_document(w2._scene, path)
    assert n == 3   # 사각형 2 + 화살표 1

    arrows = [it for it in w2._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(arrows) == 1
    a2 = arrows[0]
    host2 = a2._bound(len(a2._pts) - 1)
    assert isinstance(host2, _GroupBindProxy)
    assert host2.group_id == "g1"
    # 복원된 그룹 멤버를 옮기면(=그룹 전체 이동) 새 문서에서도 계속 라이브로 따라간다.
    members2 = _group_members(w2._scene, "g1")
    assert len(members2) == 2
    for m in members2:
        m.moveBy(10, 5)
    assert a2.reroute() is True


def test_duplicate_group_with_bound_arrow_rebinds_to_new_group():
    w = CanvasWindow()
    a, b = _mk_group(w)
    proxy = _GroupBindProxy(w._scene, "g1")
    arrow = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    arrow.set_points(QPointF(-100, 30), QPointF(0, 30))
    arrow.setFlags(arrow.GraphicsItemFlag.ItemIsSelectable | arrow.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(arrow)
    arrow.set_bound(1, proxy, proxy.mapFromScene(QPointF(0, 30)))

    a2, b2, arrow2 = a.clone(), b.clone(), arrow.clone()
    pairs = [(a, a2), (b, b2), (arrow, arrow2)]
    gid_map = regroup_duplicated_items(pairs)
    remap_grouped_bindings(pairs, gid_map)

    assert a2._group_id == b2._group_id
    assert a2._group_id != "g1"
    host2 = arrow2._bound(len(arrow2._pts) - 1)
    assert isinstance(host2, _GroupBindProxy)
    assert host2.group_id == a2._group_id   # 사본 그룹으로 재연결, 원본 그룹이 아님


def test_group_bind_proxy_is_selected_reflects_all_members():
    # [실사용 크래시 수정 2026-08-25] `.isSelected()`가 없어 AttributeError로 앱이 죽던
    # 버그(host_canvas._make_pin_pred, _PolyArrowItem.reroute 양쪽에서 무조건 호출)의
    # 재발 방지 — 존재 자체와 의미(그룹 전체가 선택돼야 True)를 함께 검증. `CanvasWindow`의
    # `_sync_group_selection`은 멤버 하나만 선택해도 즉시 전체를 함께 선택시켜(host_selection.py)
    # "일부만 선택된" 중간 상태를 실제로는 못 만드므로, 그 동기화가 안 걸린 맨 `QGraphicsScene`
    # 으로 all() 정의 자체를 직접 검증한다.
    from PyQt6.QtWidgets import QGraphicsScene
    scene = QGraphicsScene()
    a = _RectItem(QRectF(0, 0, 100, 60)); b = _RectItem(QRectF(120, 0, 100, 60))
    a.setFlags(a.GraphicsItemFlag.ItemIsSelectable); b.setFlags(b.GraphicsItemFlag.ItemIsSelectable)
    a._group_id = b._group_id = "g1"
    scene.addItem(a); scene.addItem(b)
    proxy = _GroupBindProxy(scene, "g1")
    assert proxy.isSelected() is False
    a.setSelected(True)
    assert proxy.isSelected() is False   # 일부만 선택 — 아직 그룹 전체는 아님
    b.setSelected(True)
    assert proxy.isSelected() is True


def test_group_to_normal_shape_arrow_survives_scene_changed_without_crash():
    # [실사용 크래시 수정 2026-08-25, 실조건 재현] 미선택 그룹 포트에서 일반 도형으로
    # 화살표를 긋고 아무 도형이나 움직이면(→ scene.changed → _on_scene_changed →
    # reroute(pin_pred=...)) AttributeError로 프로그램이 통째로 죽던 버그. 화살표를
    # 선택한 채로(사용자가 그린 직후 상태) 재현해야 `_make_pin_pred`의
    # `arrow.isSelected() and sh.isSelected()` 분기를 실제로 태운다.
    w = CanvasWindow()
    a, b = _mk_group(w)
    normal = _mk_rect(w._scene, w.make_pen(), 400, 0, 100, 60)
    proxy = _GroupBindProxy(w._scene, "g1")
    arrow = _ArrowItem(QColor("#ff0000ff"), 2, True)
    arrow.set_points(QPointF(220, 30), QPointF(400, 30))
    arrow.setFlags(arrow.GraphicsItemFlag.ItemIsSelectable | arrow.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(arrow)
    arrow.set_bound(0, proxy, proxy.mapFromScene(QPointF(220, 30)))
    arrow.set_bound(1, normal, normal.mapFromScene(QPointF(400, 30)))
    w._scene.clearSelection()
    arrow.setSelected(True)   # 방금 그린 화살표는 선택된 채로 남는다(실사용 관례)

    normal.moveBy(50, 20)
    w._on_scene_changed(None)   # 크래시 없이 통과해야 함(수정 전엔 여기서 AttributeError)
    assert _close(arrow.mapToScene(arrow._endpoints()[1]), QPointF(450, 50))


def test_port_dot_target_not_occluded_by_overlapping_sibling_group_member():
    # [실사용 버그 수정 2026-08-25, 그룹 프레임 후속] SVG 다중조각 심볼처럼 그룹 멤버끼리
    # 겹치는 경우(예: WiFi 아이콘의 겹친 호), 커서가 겹치는 영역(=형제 멤버의 몸통) 위에
    # 있으면 예전엔 "남이 가린다"고 오판해 그룹 예고점이 사라졌다.
    w = CanvasWindow(); w.show(); w.set_tool("select")
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 200, 60)
    b = _mk_rect(w._scene, w.make_pen(), 100, 0, 100, 60)   # a와 100~200 구간 겹침
    a._group_id = b._group_id = "gtest"
    w._scene.clearSelection()
    target = w._view._port_dot_target(QPointF(150, 30))   # 겹치는 영역, b의 몸통 한가운데
    assert isinstance(target, _GroupBindProxy) and target.group_id == "gtest"


def test_hover_port_at_not_occluded_by_overlapping_sibling_group_member():
    w = CanvasWindow(); w.show(); w.set_tool("select")
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 200, 60)
    b = _mk_rect(w._scene, w.make_pen(), 100, 0, 100, 60)
    a._group_id = b._group_id = "gtest"
    w._scene.clearSelection()
    hit = w._view._hover_port_at(w._view.mapFromScene(QPointF(199, 30)))   # 오른쪽 변, b 쪽
    assert hit is not None and isinstance(hit[0], _GroupBindProxy) and hit[0].group_id == "gtest"


# ---- [실사용 요청 2026-08-25, 그룹 프레임 후속] 선택된 그룹 자신의 큐닷 -------------------
# deep-interview로 범위 확정: `_group_id` 그룹이 선택 전체와 정확히 일치할 때만(임의
# 다중선택 전체는 대상 아님). 다중선택 변형 오버레이(_GroupTransform)의 변 중점 리사이즈
# 핸들(gap=0)과 안 겹치게 큐닷은 바깥으로 띄운다.

def test_whole_group_id_requires_exact_selection_match():
    w = CanvasWindow()
    a, b = _mk_group(w, "g1")
    c = _mk_rect(w._scene, w.make_pen(), 500, 0, 40, 40)   # 무관 도형
    view = w._view
    a.setSelected(True)   # b도 동기화로 함께 선택됨
    assert view._group.whole_group_id() == "g1"
    c.setSelected(True)   # 그룹 밖 도형이 섞이면 더 이상 "정확히 이 그룹"이 아님
    assert view._group.whole_group_id() is None


def test_whole_group_id_none_for_arbitrary_multi_select():
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 40)
    b = _mk_rect(w._scene, w.make_pen(), 100, 0, 40, 40)   # _group_id 없음
    view = w._view
    a.setSelected(True); b.setSelected(True)
    assert view._group.whole_group_id() is None
    assert view._group.qc_dot_rects() == []


def test_selected_group_qc_dot_rects_offset_outside_resize_edge_handles():
    w = CanvasWindow()
    a, b = _mk_group(w)   # 합집합 bbox 대략 (0,0)-(220,60)
    view = w._view
    a.setSelected(True)
    rects = dict(view._group.qc_dot_rects())
    box = view._group.bbox()
    # 큐닷은 리사이즈 변 중점 핸들(gap=0, 정확히 bbox 테두리 위)보다 항상 바깥에 있어야
    # 겹치지 않는다.
    assert rects["t"].y() < box.top()
    assert rects["r"].x() > box.right()
    assert rects["b"].y() > box.bottom()
    assert rects["l"].x() < box.left()


def test_qc_dot_at_hits_selected_group_qc_dot_and_creates_bound_arrow():
    w = CanvasWindow(); w.show(); w.set_tool("select")
    a, b = _mk_group(w)
    normal = _mk_rect(w._scene, w.make_pen(), 400, 0, 100, 60)
    view = w._view
    a.setSelected(True)
    right_pt = dict(view._group.qc_dot_rects())["r"]
    hit = view._qc_dot_at(view.mapFromScene(right_pt))
    assert hit is not None
    item, side = hit
    assert isinstance(item, _GroupBindProxy) and item.group_id == "g1" and side == "r"

    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    press(right_pt)
    drag_move(QPointF(350, 30))
    drag_move(QPointF(400, 30))
    release(QPointF(400, 30))

    arrows = [it for it in w._scene.items() if isinstance(it, (_ArrowItem, _PolyArrowItem))]
    assert len(arrows) == 1
    assert isinstance(arrows[0]._bound(0), _GroupBindProxy)
    assert arrows[0]._bound(0).group_id == "g1"
