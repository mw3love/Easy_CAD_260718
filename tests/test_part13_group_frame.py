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
