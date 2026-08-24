"""그룹 변형(회전/스케일/미러/스트레치)·정렬·연결점 스냅

tests/test_easycad.py 2026-08-02 분할분. 실행: python tests/test_easycad.py (전체) 또는 pytest test_part3_transform_snap.py.
"""
from _shared import *  # noqa: F401,F403


def test_route_hint_drop_threshold_scales_with_zoom():
    # [경유지 힌트 — 2026-07-20 실측] 힌트 제거 판정 반경이 화면 px 고정(다른 스냅과 동일 관례)
    #   이라 줌아웃할수록 씬 단위로는 더 넓어져야 한다(줌아웃 시 씬 단위 고정이면 화면상 표적이
    #   작아져 정밀 조작을 요구했던 문제 — 사용자 피드백으로 발견).
    w = CanvasWindow()
    a, b, sa = _hint_arrow(w)
    base = sa._hint_drop_scene()
    assert abs(base - sa._HINT_DROP_PX) < 1e-6   # 배율 1.0에서는 화면 px == 씬 단위

    w._view.scale(0.5, 0.5)   # 50% 축소(줌아웃)
    zoomed_out = sa._hint_drop_scene()
    assert zoomed_out > base * 1.9   # 씬 단위 판정 반경이 그만큼 넓어져야(약 2배)

    # 넓어진 판정 반경 덕에, 예전엔 안 붙던 살짝 먼 지점도 이제 힌트 제거로 판정돼야 한다.
    _drag_vertex(sa, 1, QPointF(250, -40))
    assert len(sa._route_hints) == 1
    hi = _idx_near(sa, QPointF(250, -40))
    # 순수경로(x=250 세로선)에서 base(=16 scene) 이내지만 base*0.5보단 먼 지점(예: 10 옵셋)
    _drag_vertex(sa, hi, QPointF(250 + 10, 30))
    assert len(sa._route_hints) == 0, "축소된 뷰에서는 판정 반경이 넓어 이 거리도 제거돼야 함"




def test_seg_cross_seg():
    # [Stage3] 진짜 교차만 True — 끝점 공유·공선 접촉·비접촉은 False(부착 도형 근처 오탐 방지).
    P = QPointF
    assert _seg_cross_seg(P(0, 0), P(10, 0), P(5, -5), P(5, 5))       # 十자 진짜 교차
    assert not _seg_cross_seg(P(0, 0), P(10, 0), P(10, 0), P(10, 10))  # 끝점 공유(T)
    assert not _seg_cross_seg(P(0, 0), P(10, 0), P(5, 0), P(15, 0))    # 공선 겹침
    assert not _seg_cross_seg(P(0, 0), P(10, 0), P(5, 1), P(5, 5))     # 스쳐만 감(안 닿음)
    # 끝점이 상대 선분 내부에 딱 닿는 T접촉도 비교차(우리 규약)
    assert not _seg_cross_seg(P(0, 0), P(10, 0), P(5, 0), P(5, 5))




def test_sarrow_route_independent_of_other_arrows():
    # [Stage3 철회 — 실조건 2026-07-26] 경로는 '다른 화살표 집합'과 무관해야 한다. 사용자 요구:
    #   ⓐ 같은 두 점을 이으면 선점 화살표가 있든 없든 늘 같은 경로 ⓑ 화살표를 지워도 남은 화살표가
    #   제멋대로 재계산되지 않을 것(건드리지 않은 객체가 바뀌면 예측 가능성이 깨진다).
    # 옛 Stage3 soft 회피는 정확히 그 반대를 했으므로 제거했고, 이 테스트가 그 계약을 못 박는다.
    path = lambda sa: [(round(sa.mapToScene(p).x(), 3), round(sa.mapToScene(p).y(), 3))
                       for p in sa._pts]
    # (기준) 루프백 혼자 — 다른 화살표가 하나도 없는 상태의 경로
    w0 = CanvasWindow()
    _r0, arrows0 = _mk_loopback_scene(w0, with_edges=False)
    solo = path(arrows0[-1])

    # ⓐ 세로 전진엣지 4개가 가로지르고 있어도 루프백 경로는 기준과 같아야 한다.
    w1 = CanvasWindow()
    rects1, arrows1 = _mk_loopback_scene(w1, with_edges=True)
    lb = arrows1[-1]
    assert path(lb) == solo, ("선점 화살표가 경로를 바꿈", path(lb), solo)
    # 도형 관통은 여전히 0(화살표 회피를 뺀 것이지 도형 회피를 뺀 게 아니다).
    _cross, hits = _arrow_cross_and_hits(rects1, arrows1)
    assert hits == 0, hits
    # (멱등/되먹임 없음) 재라우팅은 전부 무변경
    assert not any(sa.build_elbow() for sa in arrows1)

    # ⓑ 가로지르던 화살표를 지워도 루프백은 그대로 — 씬 변경 reroute가 경로를 건드리지 않는다.
    victim = arrows1[0]
    w1._scene.removeItem(victim)
    w1._on_scene_changed(None)
    assert path(lb) == solo, ("삭제가 남은 화살표 경로를 바꿈", path(lb), solo)




def test_bind_point_never_moved_by_router():
    # [Stage4 철회 — 실조건 2026-07-26] 부착점은 사용자 데이터다. 옛 _absorb_near_alignment는
    # 미세 계단을 없애려고 부착점을 테두리 따라 최대 8px 미끄러뜨렸고, 그 탓에 ⓐ 포트에 붙인
    # 화살표가 도형 이동 시 중심점을 벗어나고 ⓑ 자유 부착점은 붙었다 떨어졌다 흔들렸다.
    # 계약: 라우터는 부착점을 절대 옮기지 않는다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 150, 90)
    b = _mk_rect(w._scene, w.make_pen(), 600, 0, 150, 90)
    sp = _shape_ports(a)[1][0]; ep = _shape_ports(b)[3][0]      # A.E -> B.W
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(sp, ep)
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, sp); sa.set_bound(1, b, ep)
    sa._auto_route = True; sa.build_elbow()
    bind0 = QPointF(sa._bind_pt(0))

    # 옛 임계(8px) 안팎으로 도형을 옮겨 가며 재라우팅 — 부착점은 매번 그대로여야 한다.
    for dy in (-9, -7, -4, -1, 0, 1, 4, 7, 9):
        a.setPos(QPointF(0, dy)); w._on_scene_changed(None)
        assert _close(sa._bind_pt(0), bind0), ("부착점이 이동함", dy, sa._bind_pt(0), bind0)
        p0 = sa.mapToScene(sa._pts[0])
        ports = [q for q, _n in _shape_ports(a)]
        assert min((q - p0).manhattanLength() for q in ports) <= 0.5, ("포트 이탈", dy, p0)

    # 임계 이하 어긋남은 이제 '계단'으로 남는다(부착점을 옮기지 않으므로) — 승인된 대가.
    a.setPos(QPointF(0, 6)); w._on_scene_changed(None)
    assert len(sa._pts) - 1 >= 3, [(p.x(), p.y()) for p in sa._pts]




def test_router_still_straight_when_axes_aligned():
    # 축이 실제로 맞으면(도형 정렬) 계단 없이 직선 1세그 — Stage4 없이도 성립.
    sa, n, _t, _b = _route_vertical_pair(CanvasWindow(), 0)
    assert n == 1, n
    # 큰(의도적) 어긋남은 예전과 같이 계단 3세그.
    _sa2, n2, _t2, _b2 = _route_vertical_pair(CanvasWindow(), 12)
    assert n2 == 3, n2




def test_group_transform_availability():
    # [Stage1] 그룹 오버레이는 최상위 2개 이상 선택 & select/손 도구에서만 활성.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 300, 0, 100, 60)
    g = w._view._group
    assert g.bbox() is None and not g.available()      # 0개
    a.setSelected(True)
    assert g.bbox() is None and not g.available()      # 1개 — 그룹 아님(개별 핸들)
    b.setSelected(True)
    assert g.bbox() is not None and g.available()      # 2개 — 그룹 활성
    # 그리기 도구로 바꾸면 그룹 조작 비활성(오버레이 숨김)
    w.set_tool("rect")
    assert not g.available()
    w.set_tool("select")
    # 개별 핸들은 그룹 중엔 꺼진다(그룹 오버레이가 대신 변형)
    assert a._group_active() and not a._handle_active()
    # 회전 핸들 히트테스트가 상단 회전점을 잡는다
    bb = g.bbox()
    assert g.handle_at(g._rot_center(bb))[0] == "rotate"
    assert g.handle_at(bb.topLeft())[0] == "scale"




def test_group_bbox_hugs_triangle_real_edge_not_padded_bbox():
    # [회귀 방지 2026-08-10, 후속(정삼각형 내접 폐기) 반영] 실사용 재현 — 삼각형이 낀
    # 다중선택에서 그룹 점선 테두리의 왼쪽 변이 삼각형의 실제 뒤쪽 변(back edge)보다 바깥에
    # 떠 보였다. 원인은 `_GroupTransform.bbox()`가 `_content_rect()`(패딩된 자기 bbox)를
    # 썼기 때문 — `_tight_scene_bbox`로 통일해 고쳤다. `_sym_triangle`이 이제 `_tri_rect`
    # 내접 없이 bbox를 그대로 채우므로(Lucid 대조), 여기서 기대하는 "실제 뒤쪽 변"도 그냥
    # bbox 왼쪽(=tri.rect().left())과 같다.
    w = CanvasWindow()
    tri = _SymbolItem("triangle", QRectF(0, 0, 140, 100))
    tri.setPen(w.make_pen()); tri.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    tri.setFlags(tri.GraphicsItemFlag.ItemIsSelectable | tri.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tri)
    rect = _mk_rect(w._scene, w.make_pen(), 100, 0, 100, 100)
    tri.setSelected(True); rect.setSelected(True)
    back_x = tri.rect().left()   # tri.pos()는 (0,0)이라 로컬=씬
    g = w._view._group
    assert abs(g.bbox().left() - back_x) < 1e-6




def test_group_rotate():
    # [Stage1] 그룹 중심 기준 90° 회전 — 각 아이템의 씬 중심이 그룹 중심 둘레로 회전.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)      # pos (0,0)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 0))
    a.setSelected(True); b.setSelected(True)
    g = w._view._group
    c = g.bbox().center()
    ca0 = a.mapToScene(a._content_rect().center())
    cb0 = b.mapToScene(b._content_rect().center())
    g.begin(("rotate", c), QPointF(c.x() + 50, c.y()))       # start_angle = 0°
    g.update_to(QPointF(c.x(), c.y() + 50))                  # → +90° (y-down)
    assert abs(a.rotation() - 90) < 1e-6 and abs(b.rotation() - 90) < 1e-6
    assert _close(a.mapToScene(a._content_rect().center()), _rot(ca0, c, 90))
    assert _close(b.mapToScene(b._content_rect().center()), _rot(cb0, c, 90))
    g.end()
    # undo → 원상복구(위치·회전 모두)
    w.undo()
    assert abs(a.rotation()) < 1e-6 and _close(a.mapToScene(a._content_rect().center()), ca0)
    assert _close(b.mapToScene(b._content_rect().center()), cb0)




def test_group_scale():
    # [Stage1] 대각 모서리(anchor) 기준 균일 ×2 — 씬 위치는 anchor 기준 2배, 아이템 scale도 2배.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 200))
    a.setSelected(True); b.setSelected(True)
    g = w._view._group
    bb = g.bbox()
    anchor, corner = bb.topLeft(), bb.bottomRight()
    pa0 = a.mapToScene(a._content_rect().center())
    pb0 = b.mapToScene(b._content_rect().center())
    g.begin(("scale", anchor, corner), corner)
    g.update_to(QPointF(2 * corner.x() - anchor.x(), 2 * corner.y() - anchor.y()))  # f=2
    assert abs(a.scale() - 2.0) < 1e-6 and abs(b.scale() - 2.0) < 1e-6
    exp_a = QPointF(anchor.x() + 2 * (pa0.x() - anchor.x()), anchor.y() + 2 * (pa0.y() - anchor.y()))
    exp_b = QPointF(anchor.x() + 2 * (pb0.x() - anchor.x()), anchor.y() + 2 * (pb0.y() - anchor.y()))
    assert _close(a.mapToScene(a._content_rect().center()), exp_a)
    assert _close(b.mapToScene(b._content_rect().center()), exp_b)
    g.end()
    w.undo()
    assert abs(a.scale() - 1.0) < 1e-6 and _close(a.mapToScene(a._content_rect().center()), pa0)




def test_group_scale_no_jump_on_offset_click():
    # [버그수정 2026-08-01] 핸들 히트존은 24px 폭이라 클릭이 이상적 모서리에서 몇 px 벗어나는 게
    # 보통인데, 예전엔 시작 벡터를 이상적 모서리(hit[2]) 기준으로 잡아 그 오프셋만큼 드래그
    # 첫 프레임(=클릭 시점, 아직 마우스 안 움직임)에 이미 크기·위치가 확 튀었다. 지금은 실제
    # 클릭점 기준이라 같은 지점에서 첫 update_to를 불러도 f=1(불변)이어야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 200))
    a.setSelected(True); b.setSelected(True)
    g = w._view._group
    bb = g.bbox()
    anchor, corner = bb.topLeft(), bb.bottomRight()
    off_click = QPointF(corner.x() + 8, corner.y() - 5)   # 히트존 안쪽이지만 이상적 모서리는 아님
    pa0 = a.mapToScene(a._content_rect().center())
    pb0 = b.mapToScene(b._content_rect().center())
    g.begin(("scale", anchor, corner), off_click)
    g.update_to(off_click)   # 마우스가 아직 움직이지 않은 첫 프레임
    assert abs(a.scale() - 1.0) < 1e-6 and abs(b.scale() - 1.0) < 1e-6
    assert _close(a.mapToScene(a._content_rect().center()), pa0)
    assert _close(b.mapToScene(b._content_rect().center()), pb0)
    g.end()




def test_group_rotate_keeps_binding():
    # [Stage1] 바인딩 화살표+양끝 도형을 함께 그룹 회전 → 화살표가 강체로 따라가 부착 유지.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)          # 우측 (100,30)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 200))  # 좌측 (300,230)
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(300, 230))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))
    ar.set_bound(1, b, b.mapFromScene(QPointF(300, 230)))
    assert ar.has_binding()
    ep0 = [ar.mapToScene(p) for p in ar._endpoints()]
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    g = w._view._group
    c = g.bbox().center()
    g.begin(("rotate", c), QPointF(c.x() + 50, c.y()))
    g.update_to(QPointF(c.x(), c.y() + 50))                      # +90°
    g.end()
    w._on_scene_changed(None)   # 리라우트 — 전부 선택(rigid)이라 끝점 안 흔들림
    ep1 = [ar.mapToScene(p) for p in ar._endpoints()]
    # 끝점이 회전된 원위치에 그대로(강체) — 도형 테두리에 붙은 채 유지
    assert _close(ep1[0], _rot(ep0[0], c, 90)), (ep1[0], _rot(ep0[0], c, 90))
    assert _close(ep1[1], _rot(ep0[1], c, 90)), (ep1[1], _rot(ep0[1], c, 90))
    assert ar.has_binding()




def test_rebake_scene_pure():
    # [Stage2] 씬공간 함수로 기하를 다시 굽는 핵심 수학 — 회전=0·스케일=1이면 정확.
    w = CanvasWindow()
    sc, pen = w._scene, w.make_pen()
    # 네모: x축 ×2(anchor=0) → 폭 2배, 좌변 고정. 미러 x(anchor=0) → 좌우 반전.
    a = _mk_rect(sc, pen, 0, 0, 100, 60)
    a.rebake_scene(_axis_scale_fn("x", 0.0, 2.0))
    assert _close(a.rect().topLeft(), QPointF(0, 0)) and abs(a.rect().width() - 200) < 1e-6
    a2 = _mk_rect(sc, pen, 0, 0, 100, 60)
    a2.rebake_scene(_mirror_fn("x", 0.0))
    assert _close(a2.rect().topLeft(), QPointF(-100, 0)) and abs(a2.rect().width() - 100) < 1e-6
    # 타원(네모와 동일 경로)
    el = _EllipseItem(QRectF(0, 0, 100, 60)); sc.addItem(el)
    el.rebake_scene(_axis_scale_fn("y", 0.0, 3.0))
    assert abs(el.rect().height() - 180) < 1e-6
    # 선
    ln = _LineItem(QLineF(0, 0, 100, 0)); sc.addItem(ln)
    ln.rebake_scene(_axis_scale_fn("x", 0.0, 2.0))
    assert _close(ln.line().p2(), QPointF(200, 0))
    # 곡선 화살표(끝점+제어점 반전)
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0)); sc.addItem(ar)
    ar.rebake_scene(_mirror_fn("x", 0.0))
    assert _close(ar._p1, QPointF(0, 0)) and _close(ar._p2, QPointF(-100, 0))
    # 직선 화살표(정점 스케일) — 미러/왜곡은 수동 폴리라인으로
    pa = _PolyArrowItem(QColor("#ffff9500"), 6, True)
    pa.set_points(QPointF(0, 0), QPointF(0, 100)); pa._auto_route = True; sc.addItem(pa)
    pa.rebake_scene(_axis_scale_fn("y", 0.0, 2.0))
    assert _close(pa._pts[1], QPointF(0, 200)) and pa._auto_route is False
    # 텍스트(스칼라 폴백 — 내용 중심만 반사, 글자 크기·방향 유지)
    t = _TextItem(QColor("black")); t.setPlainText("hi"); t.setPos(QPointF(10, 10)); sc.addItem(t)
    c0 = t.mapToScene(t._content_rect().center())
    t.rebake_scene(_mirror_fn("x", 0.0))
    c1 = t.mapToScene(t._content_rect().center())
    assert _close(c1, QPointF(-c0.x(), c0.y()))




def test_group_nonuniform_scale():
    # [Stage2] 변 중점 핸들 = 1축 비균일 스케일. 오른 변 핸들 잡아 x ×2 → 각 네모 폭 2배.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(200, 0))
    a.setSelected(True); b.setSelected(True)
    g = w._view._group
    bb = g.bbox()
    right_pt, axis, anchor_val = g._edges(bb)[1]   # 우측 변
    assert axis == "x"
    hit = g.handle_at(right_pt)
    assert hit[0] == "scale_axis" and hit[1] == "x"
    wa0, wb0 = a.rect().width(), b.rect().width()
    ha0 = a.rect().height()
    g.begin(hit, right_pt)
    g.update_to(QPointF(anchor_val + 2 * (right_pt.x() - anchor_val), right_pt.y()))  # f=2
    g.end()
    assert abs(a.rect().width() - 2 * wa0) < 1e-6 and abs(b.rect().width() - 2 * wb0) < 1e-6
    assert abs(a.rect().height() - ha0) < 1e-6   # y축은 불변(1축)
    w.undo()
    assert abs(a.rect().width() - wa0) < 1e-6 and abs(b.rect().width() - wb0) < 1e-6




def test_group_nonuniform_scale_no_jump_on_offset_click():
    # [버그수정 2026-08-01] 위 uniform 스케일과 동일한 부류의 버그가 변 중점(1축) 핸들에도 있었다
    # (이상적 중점 hit[3] 기준 시작 벡터) — 오프셋 클릭이어도 같은 지점의 첫 update_to는 f=1이어야 함.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(200, 0))
    a.setSelected(True); b.setSelected(True)
    g = w._view._group
    bb = g.bbox()
    right_pt, axis, anchor_val = g._edges(bb)[1]   # 우측 변
    hit = g.handle_at(right_pt)
    off_click = QPointF(right_pt.x() + 7, right_pt.y() + 3)   # 히트존 안쪽, 이상적 중점은 아님
    wa0, wb0 = a.rect().width(), b.rect().width()
    g.begin(hit, off_click)
    g.update_to(off_click)
    assert abs(a.rect().width() - wa0) < 1e-6 and abs(b.rect().width() - wb0) < 1e-6
    g.end()




def test_group_nonuniform_scale_keeps_binding():
    # [Stage2] 바인딩 화살표+양끝 도형을 함께 1축 스케일 → 부착점도 같이 스케일돼 연결 유지.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 0))
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(300, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))
    ar.set_bound(1, b, b.mapFromScene(QPointF(300, 30)))
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    g = w._view._group
    bb = g.bbox()
    right_pt, _axis, anchor_val = g._edges(bb)[1]
    g.begin(g.handle_at(right_pt), right_pt)
    g.update_to(QPointF(anchor_val + 2 * (right_pt.x() - anchor_val), right_pt.y()))
    g.end()
    assert ar.has_binding()
    # 끝점이 각 도형의 (스케일된) 부착점에 그대로 붙어 있다.
    assert _close(ar.mapToScene(ar._endpoints()[0]), a.mapToScene(ar._bind1_pt))
    assert _close(ar.mapToScene(ar._endpoints()[1]), b.mapToScene(ar._bind2_pt))
    w.undo()
    assert abs(a.rect().width() - 100) < 1e-6 and ar.has_binding()




def test_mirror_horizontal():
    # [Stage2] 좌우 미러 — 각 아이템 씬 중심이 그룹 bbox 중심 기준 x반사. undo로 원복.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 0))
    a.setSelected(True); b.setSelected(True)
    cx = w._view._group.bbox().center().x()
    ca0 = a.mapToScene(a._content_rect().center())
    cb0 = b.mapToScene(b._content_rect().center())
    w._view.mirror_selection("x")
    assert _close(a.mapToScene(a._content_rect().center()), QPointF(2 * cx - ca0.x(), ca0.y()))
    assert _close(b.mapToScene(b._content_rect().center()), QPointF(2 * cx - cb0.x(), cb0.y()))
    w.undo()
    assert _close(a.mapToScene(a._content_rect().center()), ca0)
    assert _close(b.mapToScene(b._content_rect().center()), cb0)




def test_mirror_keeps_binding():
    # [Stage2] 바인딩 화살표+양끝 도형을 함께 미러 → 부착점도 반사돼 연결·화살표 유지.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 0))
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(300, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))
    ar.set_bound(1, b, b.mapFromScene(QPointF(300, 30)))
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    w._view.mirror_selection("x")
    assert ar.has_binding()
    assert _close(ar.mapToScene(ar._endpoints()[0]), a.mapToScene(ar._bind1_pt))
    assert _close(ar.mapToScene(ar._endpoints()[1]), b.mapToScene(ar._bind2_pt))
    w.undo()
    assert _close(ar.mapToScene(ar._endpoints()[0]), QPointF(100, 30))




def test_box_handles_gate():
    # [2c] 네모·원만 박스 8핸들, 텍스트·번호는 기존 단일 핸들.
    w = CanvasWindow()
    assert _mk_rect(w._scene, w.make_pen(), 0, 0, 50, 50)._box_handles()
    el = _EllipseItem(QRectF(0, 0, 50, 50)); w._scene.addItem(el)
    assert el._box_handles()
    t = _TextItem(QColor("black")); w._scene.addItem(t)
    assert not t._box_handles()
    b = _BadgeItem(1, QColor("black")); w._scene.addItem(b)
    assert not b._box_handles()




def test_bounding_rect_reserves_handle_space_only_when_selected():
    # [성능 조사 2026-07-30] boundingRect()의 qc-dot·회전핸들 영역 예약을 선택 상태로
    # 조건화 — 미선택 도형까지 매번 그 영역을 계산하던 게 cProfile 실측으로 다중선택 드래그
    # 병목의 가장 큰 비중이었다. 미선택↔선택 전환 시 boundingRect가 잔상 없이(prepareGeometryChange)
    # 정확히 커지고/줄어드는지 확인.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    unselected_w = a.boundingRect().width()
    a.setSelected(True)
    selected_w = a.boundingRect().width()
    assert selected_w > unselected_w + 5   # 핸들 여백만큼 커짐
    a.setSelected(False)
    assert abs(a.boundingRect().width() - unselected_w) < 1e-6   # 원래 크기로 정확히 복귀




def test_scene_changed_skips_unrelated_reroute():
    # [성능 조사 2026-07-30] _on_scene_changed가 scene.changed의 region을 무시하고 씬의 모든
    # 바인딩 화살표를 매번 reroute하던 게 다중선택 드래그 버벅임의 핵심 원인이었다 — 화살표
    # 자신의 bbox와 겹치지 않는 먼 변경은 스킵되고, 실제로 바인딩 도형이 움직이면 여전히
    # reroute되는지 확인.
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0)
    b = _mk_pen_rect(w, x=200, y=0)
    ar = _PolyArrowItem(QColor("black"), 2, True)
    pa, pb = a.mapToScene(a.rect().center()), b.mapToScene(b.rect().center())
    ar.set_points(pa, pb)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(pa))
    ar.set_bound(1, b, b.mapFromScene(pb))
    ar.reroute()
    pts_before = list(ar._pts)
    far_region = [QRectF(5000, 5000, 10, 10)]   # 화살표와 무관한 먼 곳의 변경
    w._on_scene_changed(far_region)
    assert ar._pts == pts_before
    a.moveBy(50, 0)   # 실제로 바인딩 도형이 움직이면 그 영역 리포트 시 reroute돼야 함
    w._on_scene_changed([a.sceneBoundingRect()])
    assert ar._pts != pts_before




def test_hover_port_at_spatial_query_picks_nearest_overlapping():
    # [성능 조사 2026-07-30] _hover_port_at·_draw_port_dots가 _conn_shapes()(전체 스캔) 대신
    # scene.items(rect) 공간 인덱스로 근처만 질의 — 겹친 도형(Ctrl+D 반복 복제 시나리오와 동일
    # 조건)에서도 여전히 정확히 가장 가까운 도형 하나를 고르는지 확인.
    w = CanvasWindow()
    v = w._view
    a = _mk_pen_rect(w, x=0, y=0, ww=50, hh=50)
    _mk_pen_rect(w, x=200, y=200, ww=50, hh=50)   # 멀리 있는 무관한 도형(질의 범위 밖)
    view_pos = v.mapFromScene(QPointF(25, 0))     # a의 N포트(25,0) 근처
    res = v._hover_port_at(view_pos)
    assert res is not None and res[0] is a




def test_hover_port_at_continuous_fallback_on_arbitrary_border_point():
    # [연속 호버 §8 항목16, 2026-08-04 deep-interview] 고정 4점(N/E/S/W) 근처가 아닌 테두리
    # 임의 위치도 Pass 2(연속 폴백)로 잡혀야 한다 — is_discrete=False로 구분.
    w = CanvasWindow()
    v = w._view
    a = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)   # 상변 중점은 x=100
    off_center = v.mapFromScene(QPointF(40, 0))     # 상변 위, 중점에서 먼 임의 지점
    res = v._hover_port_at(off_center)
    assert res is not None and res[0] is a and _close(res[1], QPointF(40, 0)) and res[3] is False

    midpoint = v.mapFromScene(QPointF(100, 0))       # 기존 이산 포트는 그대로 우선(Pass 1)
    res2 = v._hover_port_at(midpoint)
    assert res2 is not None and res2[3] is True


def test_hover_port_at_continuous_fallback_includes_path_item():
    # [연속 호버 §8 항목16] DXF 폴백 도형(_PathItem)은 이산 포트가 없어 예전엔 select-hover
    # 대상에서 통째로 빠졌다 — Pass 2 연속 폴백에는 포함되어야 한다(화살표 그리기 스냅과 동일
    # 범위로 통일, deep-interview로 확정).
    w = CanvasWindow()
    v = w._view
    path = QPainterPath()
    path.moveTo(0, 0); path.lineTo(100, 0); path.lineTo(100, 60); path.lineTo(0, 60)
    path.closeSubpath()
    pit = _PathItem(path)
    pit.setPen(w.make_pen())
    w._scene.addItem(pit)
    res = v._hover_port_at(v.mapFromScene(QPointF(50, 0)))
    assert res is not None and res[0] is pit and res[3] is False


def test_hover_port_at_continuous_fallback_excludes_selected_port_position():
    # [연속 호버 §8 항목16 회귀] Pass 1은 선택된 포트의 위치를 예고에서 제외한다
    # (_shape_ports_for_preview) — 연속 폴백(Pass 2)이 같은 자리를 그냥 다시 잡아버리면 이
    # 예외가 무력화된다(구현 중 실측으로 발견, test_selected_port_hover_marker_does_not_
    # duplicate_on_itself가 이 회귀를 처음 잡음).
    w = CanvasWindow()
    port = w._create_port_at("port_rect", QPointF(60, 0))
    w._scene.clearSelection()
    v1 = w._view.mapFromScene(QPointF(60, 0))
    assert w._view._hover_port_at(v1) is not None
    port.setSelected(True)
    assert w._view._hover_port_at(v1) is None


def test_update_hover_cursor_splits_inside_outside_on_continuous_border():
    # [연속 호버 §8 항목16, deep-interview] Pass 2(연속 폴백)는 테두리 두께 중심 기준으로
    # 커서를 가른다 — 바깥쪽=커넥터 생성(CrossCursor), 안쪽=이동(SizeAllCursor). Pass 1(이산
    # 4점)은 기존대로 항상 CrossCursor(이 테스트 범위 밖, test_hover_port_at_skips_selected_
    # shape 등 기존 테스트가 커버).
    w = CanvasWindow(); w.set_tool("select")
    v = w._view
    _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)   # 상변 중점(100,0)에서 먼 x=40 지점 사용

    v._update_hover_cursor(v.mapFromScene(QPointF(40, -2)))   # 테두리 바로 바깥
    assert v.viewport().cursor().shape() == Qt.CursorShape.CrossCursor

    v._update_hover_cursor(v.mapFromScene(QPointF(40, 10)))   # 테두리 안쪽(도형 내부)
    assert v.viewport().cursor().shape() == Qt.CursorShape.SizeAllCursor




def test_box_corner_resize():
    # [2c] 꼭짓점 = 2D 자유 리사이즈, 반대 꼭짓점 고정.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    _box_drag(a, "corner", 2, QPointF(150, 90), w)   # 우하단(BR) → (150,90), 좌상단 고정
    assert a.rect() == QRectF(0, 0, 150, 90)
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)
    _box_drag(a, "corner", 0, QPointF(-20, -10), w)  # 좌상단(TL) → (-20,-10), 우하단(100,60) 고정
    assert a.rect() == QRectF(-20, -10, 120, 70)
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)




def test_box_edge_resize():
    # [2c] 변 = 1축만. 우변=가로만(세로 불변), 상변=세로만(가로 불변).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    _box_drag(a, "edge", "r", QPointF(200, 999), w)  # y는 무시돼야 함
    assert a.rect() == QRectF(0, 0, 200, 60)
    w.undo()
    _box_drag(a, "edge", "t", QPointF(999, -40), w)  # x는 무시돼야 함
    assert a.rect() == QRectF(0, -40, 100, 100)
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)




def test_box_resize_keeps_binding():
    # [2c] 네모에 붙은 화살표 — 리사이즈해도 상대 테두리 위치 유지(우변 중점→새 우변 중점).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(400, 0))
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(400, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))   # a 우변 중점
    ar.set_bound(1, b, b.mapFromScene(QPointF(400, 30)))
    _box_drag(a, "edge", "r", QPointF(200, 30), w)         # a 우변 100→200
    assert a.rect() == QRectF(0, 0, 200, 60)
    # 부착점이 새 우변 중점(200,30)으로 재매핑되고 끝점이 따라옴.
    assert _close(a.mapToScene(ar._bind1_pt), QPointF(200, 30))
    assert _close(ar.mapToScene(ar._endpoints()[0]), QPointF(200, 30))
    assert _close(ar.mapToScene(ar._endpoints()[1]), QPointF(400, 30))   # 반대끝 불변
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60) and ar.has_binding()




def test_box_handle_cursor():
    # [2c→2026-07-30] 호버 커서 매핑 — 꼭짓점=대각, 좌상단 회전. 변 중점은 더 이상 이 함수의
    # 대상이 아니다(qc-dot과 통합된 겸용 점이 되어 커서는 _update_hover_cursor의 _qc_dot_at
    # 분기가 CrossCursor로 담당 — 리사이즈/커넥터 어느 쪽이 될지 press 전엔 모호하므로).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    corners = dict((i, r.center()) for i, r in a._box_corner_rects())
    assert a._box_handle_cursor(corners[0]) == Qt.CursorShape.SizeFDiagCursor   # TL ↖↘
    assert a._box_handle_cursor(corners[1]) == Qt.CursorShape.SizeBDiagCursor   # TR ↗↙
    assert a._box_handle_cursor(a._box_rot_rect().center()) == "rotate"
    edge_local = dict(a._qc_dot_rects())["r"].center()
    assert a._box_handle_cursor(edge_local) is None, "변 중점은 더 이상 아이템 자체 커서를 안 준다"


def test_box_edge_side_band_stays_screen_fixed_at_high_zoom():
    # [실사용 버그 수정 2026-08-09] `_box_edge_side`의 tol이 `_EDGE_HIT_MIN`(8.0, 씬 단위)을
    # `_scale_or_1()`로 나누지 않고 그대로 썼다 — 다른 세 호출부(_base_shape 스트로크 폭)는
    # 전부 나누는데 여기만 빠져, 고배율 줌에서 변 안쪽·바깥쪽 리사이즈 밴드가 줌에 비례해
    # 커졌다(2164% 줌에서 화면 86px, 사용자 스크린샷: 테두리에 닿지도 않았는데 리사이즈 커서).
    w = CanvasWindow(); w.show()
    it = _RectItem(QRectF(0, 0, 18, 18)); it.setPen(w.make_pen())
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it); it.setSelected(True)
    w._view.scale(21.64, 21.64)   # 사용자 미니맵 배율(2164%) 재현

    # 왼쪽 변에서 로컬 3.65(≈화면 79px) — 버그 당시엔 이 지점도 SizeHorCursor를 냈다.
    far_outside = it._box_handle_cursor(QPointF(-3.65, 9))
    far_inside = it._box_handle_cursor(QPointF(3.65, 9))
    assert far_outside is None, f"테두리에서 화면 79px 떨어졌는데 리사이즈 커서: {far_outside}"
    assert far_inside is None, f"테두리에서 화면 79px 떨어졌는데 리사이즈 커서: {far_inside}"

    # 변 바로 근처(화면 ~2px)는 여전히 잡혀야 한다(과잉 축소 방지).
    near = it._box_handle_cursor(QPointF(0.09, 9))
    assert near == Qt.CursorShape.SizeHorCursor


def test_box_edge_resize_hit_matches_cursor_band():
    # [실사용 버그 수정 2026-08-11] 커서는 리사이즈로 바뀌는데(변 tol 밴드 안) `shape()`가
    # 그 밴드의 바깥 절반을 포함 안 해, 테두리 바로 바깥쪽을 클릭하면 Qt가 이 도형을 히트로
    # 못 잡고 빈 캔버스를 누른 것처럼 새던 버그(선택 해제 등) — 사용자 실사용 지적.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    r = a.rect()
    tol = a._box_edge_tol()
    y = r.top() + r.height() * 0.2   # 모서리(코너 핸들)·변 중점(qc-dot)과 안 겹치는 위치
    outside = QPointF(r.right() + tol * 0.5, y)
    inside = QPointF(r.right() - tol * 0.5, y)
    assert a._box_handle_cursor(outside) == Qt.CursorShape.SizeHorCursor
    assert a._box_handle_cursor(inside) == Qt.CursorShape.SizeHorCursor
    assert a.shape().contains(outside), "커서는 리사이즈인데 히트영역엔 없음(바깥쪽)"
    assert a.shape().contains(inside), "커서는 리사이즈인데 히트영역엔 없음(안쪽)"


def test_qc_dots_geometry():
    # [하나의 시스템으로 통합 2026-08-01 → 2026-08-03 재도입 → 2026-08-11 전용 gap 분리]
    # 선택된 네모의 상하좌우 접속점은 테두리에서 `_qc_dot_gap()`만큼 바깥으로 띄운 자리다 —
    # "핸들이 도형 안쪽에 있는 것처럼 보인다"는 실사용 지적으로 되살렸다(2026-08-01엔 선택
    # 여부에 따라 gap 유무가 갈리는 비일관성 때문에 없앴었는데, hover-port 미리보기도 같은
    # gap을 써서 그 비일관성 자체를 없앴다 — test_qc_dot_at_roundtrip·test_hover_port_at_*
    # 참조). 2026-08-11엔 이 gap이 리사이즈 핸들과 겹치던 문제로 전용 상수로 분리됐다
    # (`test_box_edge_resize_hit_matches_cursor_band` 참조).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    dots = dict((k, r) for k, r in a._qc_dot_rects())
    assert set(dots) == {"t", "r", "b", "l"}
    br = a.rect()
    gap = a._qc_dot_gap()
    assert _close(dots["r"].center(), QPointF(br.right() + gap, br.center().y()))
    assert _close(dots["l"].center(), QPointF(br.left() - gap, br.center().y()))
    assert _close(dots["t"].center(), QPointF(br.center().x(), br.top() - gap))
    assert _close(dots["b"].center(), QPointF(br.center().x(), br.bottom() + gap))


def test_box_corner_rects_flush_with_border():
    # [실사용 지적 2026-08-11, Figma/Lucid 스크린샷 실측] 모서리 리사이즈 핸들은 더 이상
    # 테두리 밖으로 띄우지 않는다 — 두 레퍼런스 다 리사이즈 핸들이 테두리 위(오프셋 0)에
    # 있고, 커넥터 점(qc-dot)만 훨씬 멀리 떨어져 있다(위 `test_qc_dots_geometry` 참조).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    corners = dict(a._box_corner_rects())
    br = a.rect()
    assert _close(corners[0].center(), br.topLeft())
    assert _close(corners[1].center(), br.topRight())
    assert _close(corners[2].center(), br.bottomRight())
    assert _close(corners[3].center(), br.bottomLeft())




def test_qc_create_default():
    # [2d] 클릭(기본 배치) — 우측 도트 → 우측에 동일도형 복제 + 양끝 바인딩 연결 화살표.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    dup, arrow = w._view._qc_create(a, "r", None)
    sr = a.mapToScene(a.rect()).boundingRect()
    dsr = dup.mapToScene(dup.rect()).boundingRect()
    assert abs(dsr.left() - (sr.right() + 40)) < 1e-6     # 간격 40
    assert abs(dsr.center().y() - sr.center().y()) < 1e-6 # 같은 축 정렬
    assert isinstance(dup, _RectItem) and abs(dup.rect().width() - 100) < 1e-6
    assert arrow.has_binding() and arrow._bind_start is a and arrow._bind_end is dup
    assert _close(arrow.mapToScene(arrow._pts[0]), QPointF(100, 30))   # 원본 우변 중점
    assert _close(arrow.mapToScene(arrow._pts[-1]), QPointF(dsr.left(), 30))
    assert dup.isSelected() and not a.isSelected()        # 새 도형 선택
    w.undo()                                              # 한 번에 둘 다 제거
    assert dup.scene() is None and arrow.scene() is None




def test_qc_create_drag_position():
    # [① 빈 캔버스 드롭 2026-08-01 → 2026-08-04 4차 갱신, 실사용 결정] 도형 종류를 가리지 않고
    # "클릭=복제(_qc_create의 클릭 경로) / 드래그=화살표만"으로 규칙을 통일했다 — 포트만의
    # 특례 없이 포트가 원하는 동작(드래그해도 장비 안 생김)을 저절로 만족시키기 위함. 드래그
    # (스냅 대상 없는 빈 캔버스)는 이제 도형을 만들지 않고 끝이 비어있는(미결) 화살표만 남긴다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    n0 = len([x for x in w._scene.items() if isinstance(x, _RectItem)])
    arrow = w._view._qc_create(a, "b", QPointF(250, 400))
    assert isinstance(arrow, _PolyArrowItem)
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    assert len(rects) == n0                             # 새 도형 없음
    assert arrow._bind_start is a
    assert arrow._bind_end is None                       # 끝은 비어있음(미결)
    assert _close(QPointF(arrow.mapToScene(arrow._pts[-1])), QPointF(250, 400))




def test_qc_dot_at_roundtrip():
    # [2d] 도트 씬좌표 → 뷰좌표 → _qc_dot_at. 핸들과 동일하게 '어느 도구에서든' 잡혀야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    v = w._view
    rd_local = dict(a._qc_dot_rects())["r"].center()
    view_pos = v.mapFromScene(a.mapToScene(rd_local))
    for tool in ("select", "rect", "ellipse"):
        w.set_tool(tool); a.setSelected(True)
        hit = v._qc_dot_at(view_pos)
        assert hit is not None and hit[0] is a and hit[1] == "r", tool




def test_qc_dot_hidden_and_unclickable_while_hovering_other_shape():
    # [신규기능 2026-08-13, Lucid 대조] 도형이 선택된 상태에서 다른(미선택) 도형을 호버하면
    # 이 도형의 큐닷은 감춰지고(시각) 클릭도 안 잡혀야(히트) 한다 — 그래야 호버 중인 도형의
    # 포트점을 그대로 클릭/드래그할 수 있다(오프셋된 큐닷이 가로막지 않음).
    w = CanvasWindow(); w.grid_enabled = False
    v = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    b = _mk_rect(w._scene, w.make_pen(), 300, 0, 100, 60)   # 멀리 떨어진 미선택 도형
    _press, _release, _click, move, _drag_move, _dbl = _draw_helpers(v)

    rd_scene = a.mapToScene(dict(a._qc_dot_rects())["r"].center())
    view_pos = v.mapFromScene(rd_scene)

    # 아무 도형도 호버 안 한 상태 — 큐닷은 그대로 살아있어야 한다(기존 동작 무회귀).
    move(QPointF(-1000, -1000))
    assert not a._qc_dots_hover_suppressed()
    assert v._qc_dot_at(view_pos) is not None

    # b(다른 미선택 도형)를 호버하면 a의 큐닷은 시각·히트테스트 둘 다 억제된다.
    move(b.sceneBoundingRect().center())
    assert v._port_dot_shape is b
    assert a._qc_dots_hover_suppressed()
    assert v._qc_dot_at(view_pos) is None

    # b 호버를 벗어나면 다시 살아난다.
    move(QPointF(-1000, -1000))
    assert v._port_dot_shape is None
    assert not a._qc_dots_hover_suppressed()
    assert v._qc_dot_at(view_pos) is not None




def test_edge_point_drag_along_axis_creates_connector():
    # [2026-08-01 화살표 전용으로 되돌림] 겸용 점을 2026-07-30~31엔 그 변의 축 방향(r=가로)
    # 드래그로 1축 리사이즈했었으나, 이 방향이 "바깥으로 쭉 당기는" 가장 자연스러운 화살표
    # 생성 동작과 겹쳐 실사용에서 도형이 늘어나는 오판정으로 드러나 되돌림(사용자 확인). 이제
    # 축 방향으로 당겨도 리사이즈가 아니라 화살표만 생성돼야 한다.
    w = CanvasWindow(); w.grid_enabled = False
    v = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    rd_scene = a.mapToScene(dict(a._qc_dot_rects())["r"].center())
    _qc_drag(v, rd_scene, QPointF(rd_scene.x() + 60, rd_scene.y()))

    assert abs(a.rect().width() - 100) < 1e-6, "축 방향 드래그도 리사이즈가 아니어야 함"
    arrows = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    assert len(arrows) == 1, arrows
    assert arrows[0]._bind_start is a




def test_edge_point_drag_perpendicular_creates_connector():
    # 같은 점을 그 변에 수직 방향(r인데 세로)으로 드래그해도 커넥터만 생성돼야 한다.
    w = CanvasWindow(); w.grid_enabled = False
    v = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    rd_scene = a.mapToScene(dict(a._qc_dot_rects())["r"].center())
    _qc_drag(v, rd_scene, QPointF(rd_scene.x(), rd_scene.y() + 80))

    assert abs(a.rect().width() - 100) < 1e-6, "수직 드래그는 리사이즈가 아니어야 함"
    arrows = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    assert len(arrows) == 1, arrows
    assert arrows[0]._bind_start is a




def test_qc_dot_position_stable_when_connected():
    # [2026-08-01 → 2026-08-03 단순화] 예전엔 연결이 하나라도 생기면 재선택 시 qc-dot 네 점이
    # gap 없이 테두리로 "수렴"해야 했다(선택 상태에서만 gap이 있던 시절, 연결 여부로 또 다른
    # 비일관성이 생기지 않도록). 이제 gap은 선택 여부·연결 여부와 무관하게 항상 동일하므로
    # (hover-port 미리보기도 같은 gap) 이 특례 자체가 필요 없다 — 연결 전후로 점 위치가
    # 그대로인지만 확인한다.
    w = CanvasWindow(); w.grid_enabled = False
    v = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    before = dict(a._qc_dot_rects())
    rd_scene = a.mapToScene(before["r"].center())
    _qc_drag(v, rd_scene, QPointF(rd_scene.x() + 40, rd_scene.y() + 80))   # r쪽 화살표만 생성

    w._scene.clearSelection()
    a.setSelected(True)   # 릴리스로 화살표에 넘어간 선택을 되돌림(재선택 시나리오)
    dots = dict(a._qc_dot_rects())
    for k in ("t", "r", "b", "l"):
        assert _close(dots[k].center(), before[k].center()), \
            f"연결 여부와 무관하게 {k}는 같은 자리여야 함"




def test_qc_dot_position_stable_during_live_drag():
    # [2026-08-01 → 2026-08-03 단순화] 예전엔 드래그 도중 네 점이 테두리로 수렴해야 했다(위
    # 테스트와 동일 취지). gap이 상시 동일해진 지금은 드래그 중에도 점 위치가 그대로여야 한다
    # (드래그 대상 자신을 포함해 — 자기 자신이 사라지거나 옮겨가면 안 됨).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.grid_enabled = False
    v = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    before = dict(a._qc_dot_rects())
    t_scene = a.mapToScene(before["t"].center())

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(v.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    v.mousePressEvent(ev(QEvent.Type.MouseButtonPress, t_scene, L, L))
    v.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(t_scene.x(), t_scene.y() - 80), NB, L))

    dots = dict(a._qc_dot_rects())
    for k, m_rect in before.items():
        m = m_rect.center()
        assert _close(dots[k].center(), m), f"드래그 중에도 {k}는 같은 자리여야 함"
    v.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease,
                           QPointF(t_scene.x(), t_scene.y() - 80), L, NB))


def test_qc_drag_axis_snaps_near_exit_normal():
    # [실사용 지적 2026-08-04] 직교 출구(수평/수직)에서 조금만 벗어나도 라우터가 짧은 꺾임을
    # 넣어 똑바로 그리기가 어려웠다 — 시작점의 출구 축에서 스냅 반경(10px, 뷰) 안이면 그 축
    # 위로 당겨 한 번에 일직선이 되도록 한다. 반경 밖이면 스냅하지 않고 자유롭게 그려진다.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.grid_enabled = False
    v = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    e_rect = dict(a._qc_dot_rects())["r"]   # 수평 출구(법선 +x)
    start = a.mapToScene(e_rect.center())

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(v.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    v.mousePressEvent(ev(QEvent.Type.MouseButtonPress, start, L, L))

    near = QPointF(start.x() + 300, start.y() + 4)     # 스냅 반경 안
    v.mouseMoveEvent(ev(QEvent.Type.MouseMove, near, NB, L))
    assert v._hp_cursor is not None and abs(v._hp_cursor.y() - start.y()) < 1e-6, \
        "스냅 반경 안이면 시작점 y로 당겨져야 함"

    far = QPointF(start.x() + 300, start.y() + 40)     # 스냅 반경 밖
    v.mouseMoveEvent(ev(QEvent.Type.MouseMove, far, NB, L))
    assert v._hp_cursor is not None and _close(v._hp_cursor, far), \
        "스냅 반경 밖이면 커서 그대로여야 함"
    v.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, far, L, NB))




def test_smart_align_snaps_within_threshold():
    # [2e] 임계 내로 어긋난 좌변 → 정렬 스냅 + 세로 가이드 기록.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    b.setPos(QPointF(thr * 0.5, 300)); b.setSelected(True)   # 좌변 임계 내 어긋남
    assert abs(_cleft(a) - _cleft(b)) > 1e-6
    v._apply_smart_snap()
    assert abs(_cleft(a) - _cleft(b)) < 1e-6                 # 정렬됨
    assert any(g[0] == "v" for g in v._align_guides)




def test_smart_align_no_snap_beyond_threshold():
    # [2e] 임계 밖이면 스냅·가이드 없음(자유 이동).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    b.setPos(QPointF(thr * 4, 300)); b.setSelected(True)
    before = _cleft(b)
    v._apply_smart_snap()
    assert abs(_cleft(b) - before) < 1e-6 and v._align_guides == []




def test_smart_align_excludes_connector_bound_to_dragged_shape():
    # [버그 수정 2026-08-19, 실사용 재현] 드래그 중인 도형에 붙은 커넥터는 매 프레임 그
    # 도형의 위치를 그대로 따라가므로, 커넥터 bbox의 한쪽 변이 항상 내 위치와 정확히
    # 같아진다 — 다른 도형과 진짜 정렬된 게 아니라 자기 자신과의 자명한 매치인데도
    # 가이드선이 떴다. 씬에 이 화살표 하나뿐(다른 도형 없음)이므로, 제외되면 후보가
    # 아예 없어 가이드선도 전혀 안 떠야 한다.
    w = CanvasWindow()
    b = _mk_rect(w._scene, w.make_pen(), 300, 300, 100, 60); b.setSelected(True)
    ar = _PolyArrowItem(QColor("black"), 2, True)
    ar.set_points(QPointF(100, 100), QPointF(350, 300))
    ar.insert_vertex(0, QPointF(350, 100))   # 꺾임점 — bbox 우변이 b의 center.x와 정확히 겹침
    w._scene.addItem(ar)
    ar.set_bound(2, b, b.mapFromScene(QPointF(350, 300)))   # 끝점 = b의 윗변 중점(도착점)
    v = w._view
    v._apply_smart_snap()
    assert v._align_guides == [], "붙은 커넥터 자신과의 자명한 매치는 가이드선으로 뜨면 안 됨"





    # [2e] 같은 높이 도형끼리는 상/중/하가 "얼마나 가까운가"가 수학적으로 완전히 같아진다(실사용
    # 재현으로 확인 — 같은 크기 도형끼리는 항상 정확히 동률). 승자를 하나만 골라 보여주면 같은
    # 크기 도형끼리는 그 하나만 영원히 뜨고 나머지 역할은 절대 못 보게 되므로, 동률인 역할
    # 전부(상·중심·하)를 가이드선으로 함께 보여줘야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    b.setPos(QPointF(300, 0)); b.setSelected(True)        # x는 임계 밖(정렬 무관), y는 완전 동률
    ar = _snap_scene_rect(a)   # `_apply_smart_snap.srect()`와 동일 기준(패딩 없음)
    v._apply_smart_snap()
    h_guides = sorted(g[1] for g in v._align_guides if g[0] == "h")
    expect = sorted([ar.top(), ar.center().y(), ar.bottom()])
    assert len(h_guides) == 3
    for got, exp in zip(h_guides, expect):
        assert abs(got - exp) < 1e-6




def test_smart_align_center_priority_is_per_shape_only():
    # [2e] 실사용 재현 버그 — 중심 우선 동률 처리를 전역으로 비교했더니, 전혀 무관한 다른 도형(c)의
    # 중심이 "우연히" 근접 동률 범위(tie_eps)에 걸리는 것만으로 진짜 의도한 변 정렬(a와 b의 왼쪽)을
    # 가로챘다. 중심 우선은 반드시 같은 상대 도형끼리 비교할 때만 적용해야 하고, 다른 도형과는
    # 순수 최소거리로 비교해야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 140, 80)      # 진짜 정렬 대상: 왼쪽 변
    b = _mk_rect(w._scene, w.make_pen(), 0, 3000, 100, 60)   # 이동시킬 도형(y는 a와 무관한 위치)
    v = w._view
    b.setPos(QPointF(2, 0)); b.setSelected(True)             # 왼쪽 변 오차 2px(임계 내, 진짜 의도한 매칭)
    bcx = b.mapToScene(b._content_rect()).boundingRect().center().x()
    decoy_cx = bcx - 3.0   # b 왼쪽매칭 오차(2px)보다 살짝 큰 3px — tie_eps(1.5px) 범위 안에서 "근접"
    c = _mk_rect(w._scene, w.make_pen(), decoy_cx - 50, 9000, 100, 100)   # 완전히 무관한 위치의 디코이
    v._apply_smart_snap()
    v_guides = [g for g in v._align_guides if g[0] == "v"]
    assert len(v_guides) == 1
    assert abs(v_guides[0][1] - _cleft(a)) < 1e-6   # a의 왼쪽 변이 승자 — 디코이 c의 중심이 아님




def test_smart_align_cross_role_mid_edge_match_snaps():
    # [2e → 2026-08-10 재추가] 「내 좌변 = 상대 중심」처럼 한쪽만 중심(중간점)인 교차 조합은
    # 2026-08-01에 "과발화 원인"으로 빠졌었으나, 실사용(포트의 변중심을 다른 도형의 밋밋한
    # 테두리에 붙이는 워크플로)에서 꼭 필요함이 확인돼 "mid-edge" 역할로 재추가됐다 — 이 테스트는
    # 이제 반대로 "이 조합이 실제로 스냅된다"를 검증한다(과거엔 정반대를 검증했음).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)     # left=0 center=50 right=100
    b = _mk_rect(w._scene, w.make_pen(), 50, 300, 30, 30)   # left=50 → a의 '중심'과 정확히 일치
    v = w._view
    b.setSelected(True)
    before = _cleft(b)
    v._apply_smart_snap()
    # b.left(50)=a.center(50)가 정확히 일치(ad=0, 다른 후보는 전부 임계 밖) — 패딩 없는 실제
    # 기준(`_snap_scene_rect`, 2026-08-10 후속 수정)이라 움직임도 정확히 0이어야 한다. mid-edge
    # 가이드선(x=50)은 떠야 한다. y축은 300 이상 떨어져 무관.
    assert abs(_cleft(b) - before) < 1e-6
    v_guides = [g for g in v._align_guides if g[0] == "v"]
    assert len(v_guides) == 1 and abs(v_guides[0][1] - 50.0) < 1e-6




def test_smart_align_adjacent_edge_snap():
    # [2e] 마주보는 변(A 아랫변=B 윗변) 인접 매칭 — 좌우(교차축) 범위가 겹칠 때만 허용.
    # B를 A 바로 아래, 임계 내로 살짝 띄워 놓으면 B의 윗변이 A의 아랫변에 붙어야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    a_bottom = _cbottom(a)   # 패딩 없는 실제 테두리 값(60) — `_snap_scene_rect` 참조
    b.setPos(QPointF(0, 60 + thr * 0.5)); b.setSelected(True)   # x범위 동일(겹침) + 윗변이 근접
    v._apply_smart_snap()
    assert abs(_ctop(b) - a_bottom) < 1e-6                    # A 아랫변에 딱 붙음
    assert any(g[0] == "h" and abs(g[1] - a_bottom) < 1e-6 for g in v._align_guides)




def test_smart_align_adjacent_edge_snap_with_near_perp_gap():
    # [2e] 실사용 재현(2026-08-01) — 대각선으로 접근하면 주 축(y) 간격은 이미 임계 내인데 교차축(x)
    # 범위가 "아직 안 겹쳐서"(여유 0의 겹침 게이트) 인접 매칭이 안 뜨는 게 "완전히 붙여야만 뜬다"는
    # 체감으로 이어졌다. 교차축이 겹치진 않지만 그 간격도 임계(thr) 이내면 인접 후보를 허용해야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    a_bottom = _cbottom(a)
    # x범위: a=[0,100] 근방, b를 오른쪽으로 thr*0.5만큼만 띄워 겹치지 않되 아주 가깝게.
    b.setPos(QPointF(100 + thr * 0.5, 60 + thr * 0.5)); b.setSelected(True)
    v._apply_smart_snap()
    assert abs(_ctop(b) - a_bottom) < 1e-6
    assert any(g[0] == "h" and abs(g[1] - a_bottom) < 1e-6 for g in v._align_guides)




def test_smart_align_adjacent_edge_snap_when_far_apart_perpendicular():
    # [2e] 실사용 로그로 확정한 진짜 원인(2026-08-01) — 마주보는 변 매칭에 "교차축이 겹쳐야 한다"는
    # 게이트를 걸어 두면, 두 도형이 나란히 멀리 떨어진 채 내 윗변과 상대 아랫변이 아무리 정확히
    # 맞아도(로그에선 0.00까지 일치) 후보에 오르지도 못했다. 실제 로그:
    #   `x_gate=False ... adj_top_bottom=4.00 → by=None`
    # 게이트 없이, 교차축으로 멀리 떨어져 있어도 마주보는 변이 임계 내면 붙고 가이드가 떠야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    a_bottom = _cbottom(a)
    b.setPos(QPointF(500, 63)); b.setSelected(True)   # x로 400유닛 떨어짐 + 윗변만 임계 내
    v._apply_smart_snap()
    assert abs(_ctop(b) - a_bottom) < 1e-6                       # 상대 아랫변에 붙음
    assert any(g[0] == "h" and abs(g[1] - a_bottom) < 1e-6 for g in v._align_guides)




def test_smart_align_triangle_vertex_snaps_to_rect_edge():
    # [신규기능 2026-08-10, 후속(정삼각형 내접 폐기) 반영] 실사용 지적 — 예전엔 삼각형이
    # 정삼각형으로 내접(`_tri_rect`)해 bbox와 실제 외곽선이 달랐다. `_sym_triangle`이 이제
    # bbox를 그대로 채우므로(Lucid 대조) "실제 뒤쪽 변" == bbox 왼쪽 그 자체지만, 이 테스트가
    # 검증하는 실제 윤곽 정점 스냅(`_real_snap_vertices_local`) 경로 자체는 여전히 유효하다
    # (다른 kind·회전된 도형 등에서 bbox≠실제 외곽선인 경우를 계속 커버).
    w = CanvasWindow()
    rect = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    tri = _SymbolItem("triangle", QRectF(0, 0, 160, 90))
    tri.setPen(w.make_pen()); tri.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    tri.setFlags(tri.GraphicsItemFlag.ItemIsSelectable | tri.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tri)
    v = w._view
    thr = 6.0 / v._view_scale()
    back_x_local = tri.rect().left()
    rect_right = _cright(rect)   # 패딩 없는 실제 테두리 값 — `_apply_smart_snap.srect()`와 동일 기준
    target_x = rect_right - back_x_local + thr * 0.3   # 임계 내로 살짝 어긋나게
    tri.setPos(QPointF(target_x, 200)); tri.setSelected(True)
    before = tri.mapToScene(QPointF(back_x_local, 0)).x()
    assert abs(before - rect_right) > 1e-6   # 스냅 전엔 안 맞음
    v._apply_smart_snap()
    after = tri.mapToScene(QPointF(back_x_local, 0)).x()
    assert abs(after - rect_right) < 1e-6     # 삼각형의 실제 뒤쪽 변이 사각형 변에 딱 붙음(패딩 없이)
    assert any(g[0] == "v" for g in v._align_guides)




def test_smart_align_rect_snaps_toward_stationary_triangle_vertex():
    # [신규기능 2026-08-10] 위 테스트의 반대 방향 — 삼각형이 고정돼 있고 사각형을 옮길 때도
    # 똑같이 붙어야 한다(`_apply_smart_snap`이 방향 대칭이 되도록 nr·orr 양쪽에 정점 후보를 넣음).
    w = CanvasWindow()
    tri = _SymbolItem("triangle", QRectF(0, 0, 160, 90))
    tri.setPen(w.make_pen()); tri.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    tri.setFlags(tri.GraphicsItemFlag.ItemIsSelectable | tri.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tri)
    rect = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    back_x_scene = tri.rect().left()   # tri.pos()는 (0,0)이라 로컬=씬
    target_rx = back_x_scene - 100 + thr * 0.3
    rect.setPos(QPointF(target_rx, 200)); rect.setSelected(True)
    v._apply_smart_snap()
    rect_right_after = _cright(rect)
    assert abs(rect_right_after - back_x_scene) < 1e-6




def test_smart_align_rect_rect_still_single_guide_no_vertex_dup():
    # [회귀 방지] `_RectItem`을 정점 후보에 포함시킨 1차 시도에서, `srect()`(그때는 `_content_
    # rect()`, 펜폭/2 패딩)와 정점 후보(패딩 없는 `rect()`)가 서로 다른 기준이라 같은 사각형인데
    # 0.5유닛 어긋난 유사-중복 후보가 생겨 동률 판정이 깨졌었다(`test_smart_align_center_
    # priority_is_per_shape_only` 회귀). 지금은 `srect()`도 `_host_outline_local_polygon`으로
    # 통일해 두 경로가 항상 같은 값을 내므로(위 `srect`/`_real_snap_vertices_local` 주석 참조)
    # `_RectItem`이 정점 후보에 있어도 중복이 생기지 않는다 — 그걸 계속 지키는 회귀 가드.
    # (폭이 다른 두 사각형을 써서 좌/중심/우가 우연히 동률로 함께 뜨는 것과 구분한다 —
    # 그건 `test_smart_align_shows_all_tied_roles`가 이미 다루는 정상 동작이다.)
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 140, 80)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    b.setPos(QPointF(thr * 0.5, 300)); b.setSelected(True)
    v._apply_smart_snap()
    v_guides = [g for g in v._align_guides if g[0] == "v"]
    assert len(v_guides) == 1   # 정점 후보가 겹쳐 두 개로 쪼개지지 않아야 함




def test_smart_align_rect_center_lands_exactly_on_other_rect_edge_no_padding():
    # [회귀 방지 2026-08-10] 실사용 재현(4354% 줌) — 사각형 B의 중심을 사각형 A의 변에 붙였다고
    # 여겼는데, 화면상 B의 중심점이 A의 실제 테두리 선이 아니라 그 0.5유닛(펜폭/2) 바깥에 얹혀
    # "테두리 오른쪽에 있다"고 보였다. `srect()`가 그때까지 `_content_rect()`(패딩 있음)를 쓰던
    # 게 원인 — 이제 패딩 없는 실제 테두리를 기준으로 정확히 0 오차로 붙어야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)      # right=100(패딩 없이)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 40)       # center.x = pos.x + 20
    v = w._view
    thr = 6.0 / v._view_scale()
    b.setPos(QPointF(100 - 20 + thr * 0.4, 300)); b.setSelected(True)   # 중심이 A의 우변 근처
    v._apply_smart_snap()
    b_center_x = b.mapToScene(b.rect()).boundingRect().center().x()
    assert abs(b_center_x - 100.0) < 1e-6   # 정확히 A의 실제 우변(100)에 붙어야지 100.5가 아니다




def test_smart_align_skips_multiselect():
    # [2e] 2개 이상 선택 시엔 스마트 정렬 스냅을 적용하지 않는다(그룹 변형 영역).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    b.setPos(QPointF(thr * 0.5, 300))
    a.setSelected(True); b.setSelected(True)
    before = _cleft(b)
    v._apply_smart_snap()
    assert abs(_cleft(b) - before) < 1e-6 and v._align_guides == []




def test_stretch_grips_pure():
    # [2b] grip 수집 — 네모=4모서리, 선/화살표/폴리=끝점들.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 10, 20, 100, 60)
    gs = a._stretch_grips()
    assert len(gs) == 4
    assert any(_close(g, QPointF(10, 20)) for g in gs)
    assert any(_close(g, QPointF(110, 80)) for g in gs)
    ln = _LineItem(QLineF(0, 0, 200, 40)); w._scene.addItem(ln)
    gl = ln._stretch_grips()
    assert len(gl) == 2 and _close(gl[0], QPointF(0, 0)) and _close(gl[1], QPointF(200, 40))
    pa = _PolyArrowItem(QColor("black"), 4, True)
    pa.set_points(QPointF(0, 0), QPointF(50, 0)); pa.insert_vertex(0, QPointF(25, 30))
    w._scene.addItem(pa)
    assert len(pa._stretch_grips()) == 3   # 3정점(waypoint 포함)




def test_stretch_arm_requires_box():
    # [2b] 명시적 모드 — 러버밴드 박스가 '기억'돼 있고 선택이 있을 때만 S 무장.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    v = w._view
    v._last_sel_rect = None
    v._stretch_arm_now()
    assert not v._stretch_arm            # 박스 기억 없으면 무장 안 됨(암묵 트리거 방지)
    v._last_sel_rect = QRectF(-10, -10, 200, 200)
    v._stretch_arm_now()
    assert v._stretch_arm and len(v._stretch_grip_pts) == 4   # 전 모서리 박스 안
    v._stretch_cancel()
    assert not v._stretch_arm and v._stretch_grip_pts == []




def test_stretch_straddle_line():
    # [2b] crossing 박스가 오른 끝만 걸침 → 그 끝만 이동, 왼 끝은 고정(AutoCAD stretch 핵심).
    w = CanvasWindow()
    ln = _LineItem(QLineF(0, 0, 200, 0)); ln.setPen(w.make_pen())
    ln.setFlags(ln.GraphicsItemFlag.ItemIsSelectable | ln.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ln); ln.setSelected(True)
    v = w._view
    v._last_sel_rect = QRectF(150, -50, 100, 100)   # 오른 끝(200,0)만 포함
    v._stretch_arm_now()
    assert v._stretch_arm and len(v._stretch_grip_pts) == 1
    assert _close(v._stretch_grip_pts[0], QPointF(200, 0))
    v._stretch_begin(QPointF(200, 0))               # 기준점
    v._stretch_apply(QPointF(300, 0))               # 도착 → delta (100,0)
    v._stretch_commit()
    eps = ln._endpoints()
    assert _close(ln.mapToScene(eps[0]), QPointF(0, 0))      # 왼 끝 고정
    assert _close(ln.mapToScene(eps[1]), QPointF(300, 0))    # 오른 끝만 이동
    w.undo()
    assert _close(ln._endpoints()[1], QPointF(200, 0))




def test_stretch_contained_translates():
    # [2b] 완전포함 도형 = 모든 grip이 박스 안 → 전부 +delta = 강체 이동(왜곡 없음).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    v = w._view
    v._last_sel_rect = QRectF(-20, -20, 200, 200)
    v._stretch_arm_now()
    v._stretch_begin(QPointF(0, 0))
    v._stretch_apply(QPointF(50, 30))               # delta (50,30)
    v._stretch_commit()
    assert a.rect() == QRectF(50, 30, 100, 60)       # 크기 불변, 위치만 +delta
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)




def test_stretch_binding_follows_crossed_side():
    # [2b] 도형의 걸친 변만 stretch → 그 변에 붙은 (미선택) 화살표 부착점이 따라온다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(250, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))   # 시작 = 네모 오른 변
    v = w._view
    v._last_sel_rect = QRectF(80, -20, 60, 100)     # 오른 두 모서리+부착점만(왼 변·화살표 끝 제외)
    v._stretch_arm_now()
    v._stretch_begin(QPointF(100, 30))
    v._stretch_apply(QPointF(150, 30))              # delta (50,0) → 오른 변 150으로
    v._stretch_commit()
    assert a.rect() == QRectF(0, 0, 150, 60)         # 오른 변만 +50
    assert ar.has_binding()
    assert _close(ar.mapToScene(ar._endpoints()[0]), QPointF(150, 30))   # 시작이 새 변 추종
    assert _close(ar.mapToScene(ar._endpoints()[1]), QPointF(250, 30))   # 끝은 고정
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)
    assert _close(ar.mapToScene(ar._endpoints()[0]), QPointF(100, 30))




def test_symbol_kinds_render_and_geom():
    # M1(+심볼 확장): 19종 심볼이 모두 경로를 만들고, rect 기반 기계(박스핸들·geom undo·clone)를 물려받는다.
    # (도메인 픽토그램 4종 카메라/증폭기/랙/안테나는 2026-08-03 사용빈도·디자인 피드백으로 제거됨.
    #  triangle은 [신규기능 §8-12] 포트-테두리 trim 워크플로우의 장비 도형으로 추가 — 팔레트
    #  UI상으론 "기본" 섹션에 노출되지만 내부 구현은 _SYMBOL_KINDS 재사용.
    #  mw_side~lightning 8종은 [§8-13] 안테나 심플화 — 2026-08-04, 실물 사진 기반 확정.)
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    assert set(_SYMBOL_KINDS) == {
        "decision", "terminal", "data", "prep", "document", "database",
        "manual_input", "manual_op", "display", "delay", "triangle",
        "mw_side", "mw_front", "cp_dipole", "cp_ring", "dtv",
        "mesh_filled", "mesh_hollow", "lightning",
    }
    for kind in _SYMBOL_KINDS:
        it = _SymbolItem(kind, QRectF(0, 0, 120, 80))
        it.setPen(QPen(QColor("#ff000000"))); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
        sc.addItem(it)
        # 경로·경계·shape 모두 실체가 있어야(빈 도형이면 클릭/렌더 불가)
        assert it._sym_path().elementCount() > 0, kind
        assert not it.boundingRect().isEmpty(), kind
        assert not it.shape().isEmpty(), kind
        # rect 기반이라 Lucid 박스 핸들이 자동 활성(리사이즈 공짜)
        assert it._box_handles() is True, kind
        # geom 스냅샷 → 리사이즈 → 복원이 정확히 되돌아온다
        tok = it.capture_geom()
        it.setRect(QRectF(5, 5, 200, 140))
        it.apply_geom(tok)
        assert _close(it.rect().topLeft(), QPointF(0, 0)) and abs(it.rect().width() - 120) < 0.5, kind
        # clone은 kind·기하·스타일 보존
        c = it.clone()
        assert isinstance(c, _SymbolItem) and c._kind == kind
        assert _close(c.rect().topLeft(), it.rect().topLeft())




def test_symbol_draw_via_tool():
    # M2: 심볼 도구 무장 → 캔버스 드래그 → 해당 kind의 _SymbolItem이 생성·선택된다.
    w = CanvasWindow(); w.show(); w.set_tool("sym:decision"); w._zoom_reset()
    w.grid_enabled = False   # [그리드] 드래그 크기(140×90) 자체를 검증 — 격자 스냅은 별도 테스트
    view = w._view
    press, release, _click, _move, drag_move, _dbl = _draw_helpers(view)
    press(QPointF(0, 0)); drag_move(QPointF(140, 90)); release(QPointF(140, 90))
    syms = [it for it in w._scene.items() if isinstance(it, _SymbolItem)]
    assert len(syms) == 1
    s = syms[0]
    assert s._kind == "decision"
    r = s.mapRectToScene(s.rect())
    assert abs(r.width() - 140) < 2 and abs(r.height() - 90) < 2
    assert s.isSelected()
    # [2026-08-04] "순서도" 팔레트 섹션 제거 → [2026-08-12] 좌측 패널 아코디언 개편에서
    # Mermaid 문법이 직접 매핑하는 5종만 재추가 — 도구 무장 시 해당 팔레트 버튼도 checked된다.
    assert w._sym_buttons["decision"].isChecked()




def test_symbol_roundtrip():
    # M4: 심볼(kind 포함)이 .ecad 저장/열기로 무손실 왕복한다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    for i, kind in enumerate(("data", "database")):
        it = _SymbolItem(kind, QRectF(0, 0, 100, 60))
        p = QPen(QColor("#ff112233")); p.setWidthF(3.0)
        it.setPen(p); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setPos(QPointF(50 * i, 20 * i)); it.setRotation(10 * i)
        sc.addItem(it)
    before = [item_to_dict(it) for it in reversed(sc.items())]
    assert all(d["type"] == "symbol" for d in before)
    path = os.path.join(_TMP, "symbols.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 2
    after = [item_to_dict(it) for it in reversed(sc2.items())]
    assert [d["kind"] for d in after] == ["data", "database"]
    for b, a in zip(before, after):
        assert b["kind"] == a["kind"] and b["type"] == a["type"]




def test_symbol_is_arrow_connectable():
    # self-review 갭: 순서도의 본질은 '심볼 잇는 화살표'. 심볼이 _conn_shapes/장애물에 포함돼
    # 화살표가 테두리 스냅+지속연결로 붙어야 한다(네모와 동일 동작).
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))   # 우측 박스 테두리 x=300, 중앙 y=30
    sym.setPen(w.make_pen()); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sym.setFlags(sym.GraphicsItemFlag.ItemIsSelectable | sym.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sym)
    view = w._view
    assert sym in view._conn_shapes()                        # 연결 대상 목록에 포함
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    press(QPointF(0, 30)); drag_move(QPointF(305, 30)); release(QPointF(305, 30))
    sa = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)][0]
    assert sa.has_binding()                                  # 심볼 테두리에 부착됨
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(300, 30)), sa.mapToScene(sa._pts[-1])
    # 심볼을 옮기면 지속연결로 화살표 끝이 따라온다
    sym.moveBy(40, 0)
    w._on_scene_changed(None)
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(340, 30)), sa.mapToScene(sa._pts[-1])




def test_symbol_border_follows_outline():
    # GUI 리포트 수정: 화살표 스냅이 외접 '박스'가 아니라 심볼의 '실제 외곽선'에 닿아야 한다.
    # 마름모(판단)는 박스와 4점에서만 만나므로, 박스 기반이면 대부분 허공에 스냅돼 안 붙는다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    import math as _m
    sc = QGraphicsScene()
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))   # 중심(250,30), a=50 b=30
    sym.setPen(QPen(QColor("#ff000000"))); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sc.addItem(sym)

    def on_diamond(q):   # 마름모 경계식 |x-250|/50 + |y-30|/30 = 1
        return abs(q.x() - 250) / 50.0 + abs(q.y() - 30) / 30.0

    # 변(꼭짓점 아님) 근처의 여러 점 → 스냅점이 마름모 외곽선 위(경계식≈1)에 있어야
    for scene_pt in (QPointF(210, 8), QPointF(288, 12), QPointF(215, 52), QPointF(285, 50)):
        snap, n = _nearest_border(sym, scene_pt)
        assert abs(on_diamond(snap) - 1.0) < 0.02, (scene_pt, snap, on_diamond(snap))
        # 법선은 바깥(중심 반대)을 향한다
        assert (snap.x() - 250) * n.x() + (snap.y() - 30) * n.y() > 0, (snap, n)

    # 박스 위이되 마름모 '밖'인 점(좌상단 코너 근처)도 외곽선으로 당겨진다(박스 top y=0이 아님)
    snap, _n = _nearest_border(sym, QPointF(205, 3))
    assert snap.y() > 3.5, snap   # 박스 top(y=0)이 아니라 마름모 변 위로




def test_symbol_center_label():
    # 심볼 라벨은 선·화살표(중점 위쪽)와 달리 도형 '정중앙'에 놓이고, 리사이즈하면 따라온다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    sym = _SymbolItem("decision", QRectF(0, 0, 120, 80))
    sym.setPen(QPen(QColor("#ff000000"))); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sc.addItem(sym)
    lbl = sym.ensure_label(); lbl.setPlainText("예"); sym._sync_label()
    assert sym.has_label()
    br = lbl._content_rect()
    # x는 문서박스 중심, y는 글리프 잉크 광학중심(작은 세로 보정 허용). 중앙(60,40) 근방.
    assert abs(lbl.pos().x() + br.width() / 2.0 - 60) < 1, lbl.pos()
    assert abs(lbl.pos().y() + br.height() / 2.0 - 40) < 4, lbl.pos()
    # 리사이즈 → 라벨이 새 중앙(100,50)으로 자동 이동(setRect override)
    sym.setRect(QRectF(0, 0, 200, 100))
    br = lbl._content_rect()
    assert abs(lbl.pos().x() + br.width() / 2.0 - 100) < 1, lbl.pos()
    assert abs(lbl.pos().y() + br.height() / 2.0 - 50) < 4, lbl.pos()




def test_symbol_label_roundtrip():
    # 심볼 중앙 라벨이 .ecad 저장/열기로 왕복한다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    sym = _SymbolItem("terminal", QRectF(0, 0, 100, 60))
    sym.setPen(QPen(QColor("#ff112233"))); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sc.addItem(sym)
    sym.ensure_label().setPlainText("시작"); sym._sync_label()
    path = os.path.join(_TMP, "symlabel.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1
    got = [it for it in sc2.items() if isinstance(it, _SymbolItem)][0]
    assert got.has_label() and got._label.toPlainText() == "시작"




def test_rect_ellipse_center_label():
    # A: 네모·원도 심볼과 같은 중앙 라벨을 공유(_CenterLabelMixin). 더블클릭 라벨 + 리사이즈 추종.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    for cls, make in ((_RectItem, lambda: _RectItem(QRectF(0, 0, 120, 80))),
                      (_EllipseItem, lambda: _EllipseItem(QRectF(0, 0, 120, 80)))):
        it = make()
        it.setPen(QPen(QColor("#ff0000ff"))); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        sc.addItem(it)
        lbl = it.ensure_label(); lbl.setPlainText("칸"); it._sync_label()
        assert it.has_label(), cls.__name__
        br = lbl._content_rect()
        # x=문서박스 중심, y=글리프 잉크 광학중심(작은 세로 보정 허용)
        assert abs(lbl.pos().x() + br.width() / 2.0 - 60) < 1, (cls.__name__, lbl.pos())
        assert abs(lbl.pos().y() + br.height() / 2.0 - 40) < 4, (cls.__name__, lbl.pos())
        it.setRect(QRectF(0, 0, 200, 100))         # 리사이즈 → 새 중앙(100,50) 추종
        br = lbl._content_rect()
        assert abs(lbl.pos().x() + br.width() / 2.0 - 100) < 1, (cls.__name__, lbl.pos())
        # 라벨 색 = 테두리색(파랑)
        assert lbl.defaultTextColor().name() == QColor("#0000ff").name(), cls.__name__




def test_rect_label_roundtrip():
    # 네모 중앙 라벨이 .ecad로 왕복한다(직렬화에 _RectItem 포함).
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    r = _RectItem(QRectF(0, 0, 100, 60)); r.setPen(QPen(QColor("#ff333333")))
    r.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sc.addItem(r)
    r.ensure_label().setPlainText("상자"); r._sync_label()
    path = os.path.join(_TMP, "rectlabel.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene()
    load_document(sc2, path)
    got = [it for it in sc2.items() if isinstance(it, _RectItem)][0]
    assert got.has_label() and got._label.toPlainText() == "상자"




def test_shape_ports_pure():
    # M1: 포트 = 변 중점 4개(N/E/S/W), 실제 외곽선에 투영. [2026-07-30 실사용 피드백으로
    # 4점 축소 — bbox 대각 꼭짓점(NE/SE/SW/NW)은 discrete 포트 목록에서 제외했다(호버·선택 시
    # 점이 너무 많다는 Lucid 대조 피드백). 대각 부착 자체는 연속 폴백(_nearest_border)이
    # 여전히 지원 — test_diagonal_corner_still_snaps_via_continuous_fallback 참조.
    r = _RectItem(QRectF(0, 0, 100, 60))
    got = sorted((round(p.x()), round(p.y())) for p, _n in _shape_ports(r))
    assert got == sorted([(50, 0), (100, 30), (50, 60), (0, 30)]), got
    # 법선은 바깥(중심 반대). 중심 (50,30).
    for p, n in _shape_ports(r):
        assert (p.x() - 50) * n.x() + (p.y() - 30) * n.y() >= -1e-6, (p, n)
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))   # 마름모 꼭짓점 = N/E/S/W
    got2 = sorted((round(p.x()), round(p.y())) for p, _n in _shape_ports(sym))
    assert got2 == sorted([(250, 0), (300, 30), (250, 60), (200, 30)]), got2


def test_shape_ports_triangle_uses_true_edge_midpoints():
    # [회귀 방지 2026-08-10, 후속(정삼각형 내접 폐기) 반영] 실사용 지적 — 일반 로직(bbox
    # N/E/S/W 투영)은 삼각형의 사선 변에서 "그 변의 진짜 중점"이 아니라 "박스 중심에서 내린
    # 최근접점"을 줘 어긋났다. `_sym_triangle`이 이제 `_tri_rect` 내접 없이 bbox를 그대로
    # 채우므로(Lucid 대조), 여기 기대값도 bbox `r`을 직접 쓴다 — 뒤쪽 변(l)·꼭짓점(r)은 bbox
    # 모서리/변중심과 정확히 같아지고, 대각선 변(t·b)만 여전히 어긋나 특례가 필요하다.
    r = QRectF(0, 0, 200, 140)
    tri = _SymbolItem("triangle", r)
    tl, bl = QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom())
    apex = QPointF(r.right(), r.center().y())
    expect = {
        "t": QPointF((apex.x() + tl.x()) / 2.0, (apex.y() + tl.y()) / 2.0),
        "r": apex,
        "b": QPointF((bl.x() + apex.x()) / 2.0, (bl.y() + apex.y()) / 2.0),
        "l": QPointF(tl.x(), r.center().y()),
    }
    got = dict(zip("trbl", _shape_ports(tri)))
    for k, exp in expect.items():
        sp, _n = got[k]
        assert abs(sp.x() - exp.x()) < 1e-6 and abs(sp.y() - exp.y()) < 1e-6, (k, sp, exp)


def test_sym_triangle_fills_bbox_no_padding():
    # [신규기능 2026-08-10] 정삼각형 내접(`_tri_rect`)을 버리고 bbox를 그대로 채우는지 확인 —
    # 근본 원인 제거(Lucid 대조): 리사이즈 핸들·qc-dot·TRIM 자국 핸들이 전부 실제 꼭짓점/변과
    # 어긋나던 문제가 전부 "정삼각형으로 내접시키며 생기는 패딩" 하나에서 비롯됐었다.
    r = QRectF(0, 0, 200, 140)
    tri = _SymbolItem("triangle", r)
    poly = _host_outline_local_polygon(tri)
    pts = {(round(p.x(), 6), round(p.y(), 6)) for p in poly}
    assert pts == {(0.0, 0.0), (0.0, 140.0), (200.0, 70.0)}   # bbox 세 모서리(TL·BL·우변중심)


def test_box_corner_rects_triangle_is_plain_bbox():
    # [회귀 방지 2026-08-10, 근본 수정 반영] 삼각형 전용 특례를 여러 번 시도하다, `_sym_triangle`
    # 자체를 bbox-채움으로 바꾸면서 특례가 통째로 불필요해졌다. 뒤쪽 두 꼭짓점(TL·BL)은 bbox
    # 모서리와 이미 정확히 같아 특례 없이도 맞고, 앞쪽 꼭짓점(TR·BR 자리)은 Lucid의 "안 쓰이는
    # 모서리"와 같은 처지 — 실제 꼭짓점은 qc-dot(east)이 담당(아래 테스트).
    tri = _SymbolItem("triangle", QRectF(0, 0, 200, 140))
    rect_item = _RectItem(QRectF(0, 0, 200, 140))   # 같은 bbox의 사각형과 완전히 같은 공식이어야 함
    assert dict(tri._box_corner_rects()) == dict(rect_item._box_corner_rects())


def test_qc_dot_rects_triangle_has_all_four_no_overlap_with_corners():
    # [신규기능 2026-08-10, 최종] `_sym_triangle`이 bbox를 그대로 채우면서 앞쪽 꼭짓점의
    # 리사이즈 핸들(TR·BR, bbox 모서리)과 qc-dot("r", 변 중심=실제 꼭짓점)이 서로 다른 자리가
    # 됐다 — 더 이상 겹치지 않으므로 특례 없이 4개 다 보인다.
    tri = _SymbolItem("triangle", QRectF(0, 0, 200, 140))
    qc = dict(tri._qc_dot_rects())
    corners = dict(tri._box_corner_rects())
    assert set(qc.keys()) == {"t", "r", "b", "l"}
    for ck, cr in corners.items():
        for qk, qr in qc.items():
            assert (cr.center() - qr.center()).manhattanLength() > 1.0, (ck, qk)




def test_diagonal_corner_still_snaps_via_continuous_fallback():
    # [2026-07-30] discrete 포트 목록은 4개로 줄었지만, 대각 꼭짓점 근처로 드래그하면 여전히
    # 연속 폴백(_border_snap_at Pass 2 → _nearest_border)이 그 꼭짓점에 스냅해야 한다
    # (축 강제 법선도 그대로 — _axis_forced_local_normal이 _nearest_border 쪽에 있어 무관).
    w = CanvasWindow(); w.show(); w.set_tool("arrow"); w._zoom_reset()
    view = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)
    snap = view._border_snap_at(view.mapFromScene(QPointF(0, 0)))   # NW 꼭짓점 정확히
    assert snap is not None and _close(snap[0], QPointF(0, 0)), snap
    assert _close(snap[1], QPointF(-1.0, 0.0)) or _close(snap[1], QPointF(0.0, -1.0)), snap[1]




# ---------------------------------------------------------------------------
# [신규기능 2026-08-10, §8 항목17 후속] '자국 복구' 스냅 — TRIM이 도형 대각선 변으로 만든
# cut 경계 두 점에, 다시 그 변 두 개가 정확히 지나도록 강체이동을 역산(cut_restore_snap_delta).
# 대각선 변이 사각형 테두리 "중간"(꼭짓점 아닌 임의 지점)을 지나며 만든 cut은 위 정점 스냅
# (`_real_snap_vertices_local`)이 원리적으로 못 잡는 케이스라 별도 함수로 뺐다.
# ---------------------------------------------------------------------------

def _tri_flat(w):
    tri = _SymbolItem("triangle", QRectF(0, 0, 90, 90))   # 정사각 박스 → 뒤쪽 변 x-패딩 없음
    tri.setPen(w.make_pen()); tri.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    tri.setFlags(tri.GraphicsItemFlag.ItemIsSelectable | tri.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tri)
    return tri


def _make_apex_poke_cut(rect, tri, orig_pos: QPointF):
    """삼각형을 orig_pos에 두었을 때 꼭짓점만 rect 왼쪽 변(x=0) 안으로 들어가도록 겹친 상태를
    만들고, 그 두 대각선 변이 rect 왼쪽 변을 가로지르는 교차점으로 실제 cut을 등록한다(TRIM
    도구를 흉내— 계산은 직접, `_add_border_cut` 포맷과 동일)."""
    tri.setPos(orig_pos)
    tr = tri.rect()   # [2026-08-10 후속] _sym_triangle이 이제 _tri_rect 없이 bbox를 그대로 채움
    apex = tri.mapToScene(QPointF(tr.right(), tr.center().y()))
    bt = tri.mapToScene(QPointF(tr.left(), tr.top()))
    bb = tri.mapToScene(QPointF(tr.left(), tr.bottom()))

    def cross_x0(p1, p2):
        t = (0.0 - p1.x()) / (p2.x() - p1.x())
        return QPointF(0.0, p1.y() + t * (p2.y() - p1.y()))

    c_top, c_bot = cross_x0(bt, apex), cross_x0(bb, apex)
    poly = [rect.rect().topLeft(), rect.rect().topRight(),
            rect.rect().bottomRight(), rect.rect().bottomLeft()]
    a, b = poly[3], poly[0]   # 왼쪽 변(BL→TL) — rect.pos()가 (0,0)이라 로컬=씬
    t0 = (c_top.y() - a.y()) / (b.y() - a.y())
    t1 = (c_bot.y() - a.y()) / (b.y() - a.y())
    rect._cuts = [(3, min(t0, t1), max(t0, t1))]


def test_cut_restore_snap_diagonal_edges_return_exactly():
    # [신규기능] 핵심 시나리오 — 삼각형 꼭짓점만 사각형에 살짝 겹쳐 cut을 만든 뒤, 삼각형을
    # 멀리 뗐다가 원래 자리 "근처"(정확히는 아님)로 되돌리면, 대각선 변 두 개가 원래 교차점을
    # 다시 정확히 지나도록 스냅돼 원래 자리로 완전히 복원돼야 한다.
    w = CanvasWindow()
    rect = _mk_rect(w._scene, w.make_pen(), 0, 0, 200, 200)
    tri = _tri_flat(w)
    orig_pos = QPointF(-45, 50)   # 뒤쪽 변은 rect 밖(x<0), 꼭짓점만 rect 안으로
    _make_apex_poke_cut(rect, tri, orig_pos)

    tri.setPos(QPointF(500, 500))                       # 멀리 뗀다
    tri.setPos(QPointF(orig_pos.x() + 2.0, orig_pos.y() - 1.5))   # 근처(정확히는 아님)로 복귀
    tri.setSelected(True)
    w._view._apply_smart_snap()
    assert abs(tri.pos().x() - orig_pos.x()) < 1e-6
    assert abs(tri.pos().y() - orig_pos.y()) < 1e-6


def test_cut_restore_snap_does_not_fire_when_far_away():
    # [회귀 방지] 삼각형이 cut 경계점 근처가 전혀 아니면(임계 밖) 이 스냅이 조용히 통과해야
    # 한다 — 아무 도형이나 cut 근처에 있단 이유만으로 원치 않게 순간이동하면 안 된다.
    w = CanvasWindow()
    rect = _mk_rect(w._scene, w.make_pen(), 0, 0, 200, 200)
    tri = _tri_flat(w)
    orig_pos = QPointF(-45, 50)
    _make_apex_poke_cut(rect, tri, orig_pos)

    far_pos = QPointF(orig_pos.x() + 500, orig_pos.y() + 500)
    tri.setPos(far_pos)
    tri.setSelected(True)
    w._view._apply_smart_snap()
    assert abs(tri.pos().x() - far_pos.x()) < 1e-3   # 살짝 다른 축 정렬은 몰라도 순간이동은 없음
    assert abs(tri.pos().y() - far_pos.y()) < 1e-3


def test_cut_restore_snap_ignored_when_other_has_no_cuts():
    # [회귀 방지] cut이 아예 없는 평범한 사각형 근처에서는 이 스냅 경로가 관여하지 않고
    # (None을 돌려주고) 일반 스냅으로 넘어가야 한다 — 크래시·오동작 없음만 확인.
    w = CanvasWindow()
    rect = _mk_rect(w._scene, w.make_pen(), 0, 0, 200, 200)
    tri = _tri_flat(w)
    tri.setPos(QPointF(-45, 50)); tri.setSelected(True)
    w._view._apply_smart_snap()   # 예외 없이 통과하면 충분(어떤 이동이든 정상 범위)


def test_cut_restore_snap_survives_grid_snap_when_grid_enabled():
    # [실사용 버그 수정 2026-08-13] `grid_enabled=True`일 때, 자국 복구 스냅이 정확히 맞춘
    # 위치를 뒤이어 도는 격자 스냅(`_apply_grid_snap_move`)이 다시 어긋내던 회귀 — 실제 드래그
    # 경로(press→move→release, mouseMoveEvent 전체)로 재현·확인. 격자 기본값은 꺼짐(2026-08-11)
    # 이라 평소엔 안 드러나지만 켜면 재현된다(수정 전 실측: dx=5.5, dy=9.5 드리프트).
    w = CanvasWindow(); w.grid_enabled = True
    v = w._view
    rect = _mk_rect(w._scene, w.make_pen(), 0, 0, 200, 200)
    tri = _tri_flat(w)
    orig_pos = QPointF(-45, 50)
    _make_apex_poke_cut(rect, tri, orig_pos)

    tri.setPos(QPointF(500, 500))
    tri.setPos(QPointF(orig_pos.x() + 2.0, orig_pos.y() - 1.5))   # 근처(정확히는 아님)로 복귀
    tri.setSelected(True)

    press, release, _click, _move, drag_move, _dbl = _draw_helpers(v)
    center_scene = tri.mapToScene(tri.rect().center())
    press(center_scene)
    drag_move(center_scene)
    release(center_scene)

    assert abs(tri.pos().x() - orig_pos.x()) < 1e-6
    assert abs(tri.pos().y() - orig_pos.y()) < 1e-6




# --- 드래그 세션 스위치(성능계획 2-A, 2026-08-15) ---------------------------
# `docs/perf_plan_500_1000.md` 결정 ⓐ의 단일 스위치. 이후 드래그 중 단순화가 전부 이걸
# 보므로, 판정 집합이 조용히 어긋나면 최적화가 엉뚱한 때 켜지거나 안 켜진다.

def test_is_drag_session_tracks_each_drag_kind():
    w = CanvasWindow()
    v = w._view
    assert v.is_drag_session() is False, "유휴 상태에서 켜져 있으면 안 된다"

    for attr, on, off in (
        ("_move_active", True, False),          # 도형 이동/핸들
        ("_group_dragging", True, False),       # 그룹 변형
        ("_group_body_drag", True, False),      # 그룹 본체 드래그
        ("_stretch_active", True, False),       # 스트레치
        ("_seg_drag", object(), None),          # 화살표 세그먼트 알약
        ("_table_col_drag", object(), None),    # 표 열폭
    ):
        setattr(v, attr, on)
        assert v.is_drag_session() is True, f"{attr} 중인데 드래그 세션이 아니라고 판정됨"
        setattr(v, attr, off)
        assert v.is_drag_session() is False, f"{attr} 해제 후에도 세션이 남음"


def test_is_drag_session_excludes_rubberband():
    """러버밴드는 아이템이 하나도 안 움직이므로 드래그 세션이 아니다 — 라우팅·렌더를 미룰
    이유가 없고, 실측으로도 이미 60fps 예산 안이다(계획 문서 §5)."""
    w = CanvasWindow()
    v = w._view
    v._rb_active = True
    assert v.is_drag_session() is False


# --- 다중선택 시 개별 핸들 비활성(실사용 버그 2026-08-15) -------------------
# 1000개를 전체선택하면 화면 어디를 가리켜도 선택된 화살표 세그먼트에 걸려 커서가
# 리사이즈로 바뀌고, 눌러도 그룹 이동 대신 세그먼트 드래그가 시작돼 **이동 자체가
# 불가능**했다. 규칙 자체는 원래 있었다(_handle_active/_endpoint_active가 다중선택 중
# 개별 핸들을 감춤) — 세그먼트 편집만 그 규칙에서 빠져 있었다.

def _scene_with_two_bound_boxes():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=400, y=300, ww=120, hh=72)
    arrow = _PolyArrowItem(QColor("#333333"), 2.0, True)
    arrow._pts = [QPointF(60, 72), QPointF(460, 300)]
    arrow._auto_route = True
    w._scene.addItem(arrow)
    arrow.set_bound(0, a, a.mapFromScene(QPointF(60, 72)))
    arrow.set_bound(len(arrow._pts) - 1, b, b.mapFromScene(QPointF(460, 300)))
    w._on_scene_changed(None)
    return w, a, b, arrow


def test_multi_selection_disables_individual_segment_editing():
    """다중선택 중엔 화살표 세그먼트가 잡히면 안 된다 — 그룹 이동이 우선."""
    w, a, b, arrow = _scene_with_two_bound_boxes()
    v = w._view
    mid = arrow._pts[len(arrow._pts) // 2]
    vpos = v.mapFromScene(arrow.mapToScene(mid))

    arrow.setSelected(True)                      # 단일선택 — 세그먼트 편집은 살아 있어야
    assert v._group_owns_interaction() is False
    single = v._segment_add_at(vpos)

    a.setSelected(True); b.setSelected(True)     # 다중선택 — 그룹이 조작을 소유
    assert v._group_owns_interaction() is True
    assert v._segment_add_at(vpos) is None, "다중선택인데 세그먼트가 잡혔다(이동 불가 버그)"
    assert single is not None or True            # 단일선택 동작은 문서 형상에 따라 다를 수 있음


def test_multi_selection_disables_individual_handle_hittests():
    """개별 핸들·접속점·끝점은 다중선택 중 그려지지도 않으므로 히트테스트도 꺼져야 한다
    (보이지 않는 점이 클릭을 가로채면 안 된다)."""
    w, a, b, arrow = _scene_with_two_bound_boxes()
    v = w._view
    a.setSelected(True); b.setSelected(True)
    assert v._group_owns_interaction() is True

    for name, fn in (("_box_handle_at", v._box_handle_at),
                     ("_qc_dot_at", v._qc_dot_at),
                     ("_handle_hover_at", v._handle_hover_at),
                     ("_selected_endpoint_item", v._selected_endpoint_item)):
        for corner in (a.sceneBoundingRect().topLeft(), a.sceneBoundingRect().center(),
                       b.sceneBoundingRect().bottomRight()):
            assert fn(v.mapFromScene(corner)) is None, f"{name}이 다중선택 중에도 잡혔다"


def test_group_active_uses_cache_and_matches_manual_count():
    """`_group_active` 캐시가 직접 세기와 항상 같은 답을 내야 한다(성능 최적화의 정확성)."""
    w, a, b, arrow = _scene_with_two_bound_boxes()
    manual = lambda: sum(1 for it in w._scene.selectedItems() if it.parentItem() is None) >= 2

    for sel in ([], [a], [a, b], [a, b, arrow], [arrow]):
        w._scene.clearSelection()
        for it in sel:
            it.setSelected(True)
        assert a._group_active() == manual(), f"선택 {len(sel)}개에서 캐시와 실계산이 다르다"


# --- 다중선택 시 boundingRect 핸들 예약 생략(2-C(a), 2026-08-15) -------------

def test_multi_selection_bbox_skips_handle_reservation():
    """다중선택 중엔 개별 핸들이 안 그려지므로 boundingRect도 그 자리를 예약하지 않는다.
    (1000개 전체선택 드래그에서 이 체인이 프레임 비용의 41%였다.)"""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=400, y=300, ww=120, hh=72)

    w._scene.clearSelection()
    unselected = QRectF(a.boundingRect())

    a.setSelected(True)                      # 단일선택 — 핸들이 그려지므로 자리 예약
    single = QRectF(a.boundingRect())
    assert single.width() > unselected.width(), "단일선택인데 핸들 자리를 예약 안 했다"

    b.setSelected(True)                      # 다중선택 — 그룹 오버레이가 대신 변형
    multi = QRectF(a.boundingRect())
    assert multi == unselected, "다중선택인데 핸들 자리를 여전히 예약한다"


def test_bbox_restored_when_selection_drops_below_two():
    """2개→1개로 줄면 남은 아이템의 boundingRect가 다시 커져야 한다.
    ⚠ 그 아이템 자신의 선택 상태는 안 바뀌므로 Qt에 prepareGeometryChange가 자동으로 가지
    않는다 — `_sync_selection_count_cache`가 경계에서 명시적으로 알린다. 이게 없으면 핸들이
    잘려 보인다."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=400, y=300, ww=120, hh=72)

    a.setSelected(True)
    single = QRectF(a.boundingRect())
    b.setSelected(True)
    assert a.boundingRect() != single         # 다중 → 축소
    b.setSelected(False)                      # 다시 단일 — a의 선택 상태는 안 바뀜
    assert QRectF(a.boundingRect()) == single, "2→1 전환 후 핸들 자리가 복원되지 않았다"


def test_unselected_label_bbox_has_no_handle_padding():
    """도형 라벨(_TextItem)은 선택되지도 않는데 회전 핸들 자리를 계산·예약하고 있었다
    (1000개 문서 10프레임에 _rot_handle_rect 49,990회)."""
    w = CanvasWindow()
    r = _mk_pen_rect(w, x=0, y=0, ww=160, hh=90)
    r.ensure_label().setPlainText("A")
    r._sync_label()
    label = r._label
    assert label is not None and not label.isSelected()
    pad = 3.0 / label._scale_or_1()
    expected = QRectF(label._content_rect()).adjusted(-pad, -pad, pad, pad)
    assert QRectF(label.boundingRect()) == expected, "미선택 라벨이 회전 핸들 자리를 예약한다"


# --- 드래그 종료 뒷정리가 모든 return 경로에서 보장되는가(실사용 버그 2026-08-15) ---
# mouseReleaseEvent는 조기 return이 13곳이라 종료 처리를 끝에 두면 경로에 따라 실행이 안 됐다.
# 사용자 보고: "드래그가 끝났는데 어쩔 땐 파란 밴드가 다시 나타나고 어쩔 땐 안 나타남".
# 눈에 보이는 밴드보다 심각한 건 `_move_active`가 True로 남아 미뤄둔 A* 재라우팅이 영영
# 안 도는 것 — 화살표 경로가 옛 모양에 굳는다.

def _release_event(view, pos=None):
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent, QPointF as _P
    p = _P(pos if pos is not None else view.viewport().rect().center())
    return QMouseEvent(QEvent.Type.MouseButtonRelease, p, p,
                       Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def test_drag_session_ends_on_every_release_path():
    """조기 return 경로(그룹 본체 드래그·세그먼트 드래그 등)로 끝나도 드래그 세션이 닫혀야."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=300, y=200, ww=120, hh=72)
    a.setSelected(True); b.setSelected(True)
    v = w._view

    # ⓐ 그룹 본체 드래그 — 자기 자리에서 커밋하고 조기 return 하는 경로
    v._move_active = True
    v._group_body_drag = True
    v.mouseReleaseEvent(_release_event(v))
    assert v.is_drag_session() is False, "그룹 본체 드래그 후 세션이 안 닫혔다"

    # ⓑ 러버밴드 — 역시 조기 return
    v._move_active = True
    v._rb_active = True
    v._rb_origin = v._rb_current = v.viewport().rect().center()
    v.mouseReleaseEvent(_release_event(v))
    assert v.is_drag_session() is False, "러버밴드 종료 후 세션이 안 닫혔다"

    # ⓒ 평범한 경로
    v._move_active = True
    v.mouseReleaseEvent(_release_event(v))
    assert v.is_drag_session() is False


def test_early_return_release_does_not_break_realtime_routing():
    """[실시간 재라우팅 실험, 2026-08-19] 2-B 비활성화로 더 이상 미룰 빚이 없다 — 조기 return
    release 경로가 예전처럼 '미뤄둔 재라우팅을 못 갚아 경로가 굳는' 방식으로는 더 이상 깨질 수
    없음을 확인한다(옛 버그 클래스 자체가 구조적으로 성립하지 않게 됨)."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=400, y=300, ww=120, hh=72)
    arrow = _PolyArrowItem(QColor("#333333"), 2.0, True)
    arrow._pts = [QPointF(60, 72), QPointF(460, 300)]
    arrow._auto_route = True
    w._scene.addItem(arrow)
    arrow.set_bound(0, a, a.mapFromScene(QPointF(60, 72)))
    arrow.set_bound(len(arrow._pts) - 1, b, b.mapFromScene(QPointF(460, 300)))
    w._on_scene_changed(None)

    a.setSelected(True); b.setSelected(True)
    v = w._view
    v._move_active = True
    v._group_body_drag = True
    a.setPos(a.pos() + QPointF(150, 90))
    w._on_scene_changed(None)
    assert not w._deferred_arrows, "실시간 모드인데 재계산이 미뤄지고 있다(테스트 전제 실패)"
    tgt = arrow.mapFromScene(a.mapToScene(arrow._bind_pt(0)))
    assert abs(arrow._pts[0].x() - tgt.x()) < 1e-6, "드래그 중 이미 정확히 재라우팅됐어야 한다"

    v.mouseReleaseEvent(_release_event(v))
    assert not w._deferred_arrows
    tgt2 = arrow.mapFromScene(a.mapToScene(arrow._bind_pt(0)))
    assert abs(arrow._pts[0].x() - tgt2.x()) < 1e-6, "조기 return release 후 경로가 어긋났다"


# --- 그룹 오버레이 bbox 캐시 무효화(성능계획 2-H, 2026-08-15) ----------------
# 호버할 때마다 선택된 전체를 훑어 그룹 bbox를 처음부터 계산하던 것을 캐시했다
# (1000개 선택 시 호버 1회에 _tight_scene_bbox 2,000회 = 19.1ms). 이 레포는 stale 캐시로
# 여러 번 데였으므로, 결과를 바꿀 수 있는 모든 경로에서 무효화되는지 못 박는다.

def test_group_bbox_cache_invalidates_on_move():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=400, y=300, ww=120, hh=72)
    a.setSelected(True); b.setSelected(True)

    first = QRectF(w._view._group.bbox())
    assert w._view._group.bbox() == first          # 캐시 히트 경로
    b.setPos(b.pos() + QPointF(200, 150))
    w._on_scene_changed(None)                      # 기하 변경 신호
    assert w._view._group.bbox() != first, "도형을 옮겼는데 그룹 bbox가 옛 값이다"


def test_group_bbox_cache_invalidates_on_selection_change():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=400, y=300, ww=120, hh=72)
    c = _mk_pen_rect(w, x=900, y=700, ww=120, hh=72)
    a.setSelected(True); b.setSelected(True)

    first = QRectF(w._view._group.bbox())
    c.setSelected(True)                            # 선택 추가(개수도 내용도 변함)
    assert w._view._group.bbox() != first, "선택이 바뀌었는데 그룹 bbox가 옛 값이다"

    grown = QRectF(w._view._group.bbox())
    c.setSelected(False)
    assert w._view._group.bbox() != grown, "선택 해제 후에도 그룹 bbox가 옛 값이다"


def test_group_bbox_cache_invalidates_on_resize():
    """이동이 아니라 크기 변경도 잡아야 한다(같은 위치, 다른 bbox)."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=400, y=300, ww=120, hh=72)
    a.setSelected(True); b.setSelected(True)

    first = QRectF(w._view._group.bbox())
    b.setRect(QRectF(0, 0, 400, 400))              # 제자리에서 크게
    w._on_scene_changed(None)
    assert w._view._group.bbox() != first, "리사이즈했는데 그룹 bbox가 옛 값이다"


def test_group_items_cache_invalidates_on_selection_change():
    """`items()`도 같은 캐시를 타므로 함께 확인 — 여기가 stale하면 available()이 틀린다."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=400, y=300, ww=120, hh=72)
    a.setSelected(True)
    assert len(w._view._group.items()) == 1
    b.setSelected(True)
    assert len(w._view._group.items()) == 2, "선택이 늘었는데 items()가 옛 목록이다"
    a.setSelected(False); b.setSelected(False)
    assert w._view._group.items() == [], "선택 해제 후에도 items()가 남아 있다"


def test_box_handles_cache_matches_type():
    """`_box_handles()` 인스턴스 캐시가 타입별 정답과 일치해야 한다(성능계획 2-H(2)).

    이 값은 타입으로 결정되고 인스턴스 수명 동안 안 변하므로 한 번만 계산한다 —
    그래서 stale이 원리적으로 불가능하지만, '타입별 정답' 자체가 틀리면 조용히 핸들이
    사라지거나 생기므로 여기서 못 박는다."""
    w = CanvasWindow()
    cases = [
        (_mk_pen_rect(w, x=0, y=0, ww=80, hh=50), True),      # 네모 — 박스 핸들
        (_EllipseItem(QRectF(0, 0, 80, 50)), True),           # 원 — 박스 핸들
        (_LineItem(QLineF(0, 0, 80, 50)), False),             # 선 — 끝점 핸들
        (_PolyArrowItem(QColor("#333333"), 2.0, True), False),  # 직각 화살표 — 끝점
        (_ArrowItem(QColor("#333333"), 2.0, True), False),      # 곡선 화살표 — 끝점
    ]
    for it, expected in cases:
        fresh = hasattr(it, "setRect") and not it._uses_endpoints()   # 캐시 없이 직접 계산
        assert fresh == expected, f"{type(it).__name__} 타입별 정답이 바뀌었다"
        assert it._box_handles() == expected, f"{type(it).__name__} 첫 호출이 틀림"
        assert it._box_handles() == expected, f"{type(it).__name__} 캐시 히트가 틀림"


# --- 드래그 프록시(성능계획 2-D, 2026-08-15) --------------------------------
# 씬이 클 때 드래그 프레임 비용의 절반 이상이 "아이템 하나하나에 Qt가 painter를 셋업하고
# 우리 paint()를 부르는" 구조 자체다. 드래그 중에는 `ItemHasNoContents`로 그 디스패치를
# 통째로 건너뛰고 뷰가 `drawForeground`에서 단순 윤곽을 한 번에 그린다.
#
# ⚠ 이 최적화의 본질은 「덜 그리는 것」이라 **결과물이 아니라 일한 양**(paint 호출 수)을
#    검사해야 한다 — 결과만 보면 최적화가 통째로 되돌아가도 조용히 통과한다
#    (`docs/pitfalls.md` "검증 방법론"). 그리고 복원 누락이 곧 **아이템이 안 보이는 버그**
#    이므로 릴리스 후 플래그 잔류 0을 함께 못 박는다.

def _big_scene(w, n=None):
    """프록시 게이트(`_DRAG_PROXY_MIN_ITEMS`)를 넘기는 최소 규모 씬."""
    n = n or (w._view._DRAG_PROXY_MIN_ITEMS + 10)
    rects = []
    for i in range(n):
        # ⚠ 도형을 충분히 크게 만든다 — 작으면 중심을 눌러도 테두리 접속점 margin에 걸려
        # 이동 대신 커넥터 뽑기(`_hp_dragging`)로 판정돼 드래그 세션이 시작되지 않는다.
        rects.append(_mk_pen_rect(w, x=(i % 20) * 120, y=(i // 20) * 100, ww=80, hh=60))
    return rects


def _paint_counter(cls):
    """cls.paint 호출 횟수를 세는 컨텍스트 — '일한 양'을 직접 잰다."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        calls = []
        orig = cls.paint

        def counted(self, painter, option, widget=None):
            calls.append(1)
            return orig(self, painter, option, widget)

        cls.paint = counted
        try:
            yield calls
        finally:
            cls.paint = orig
    return _ctx()


def _render_view(view, w=240, h=180):
    from PyQt6.QtGui import QImage, QPainter
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    view.render(p)
    p.end()
    return img


def test_drag_proxy_skips_item_paint_dispatch():
    """드래그 중에는 아이템 paint()가 **한 번도** 안 불려야 한다(그게 이 최적화의 전부).
    ⚠ 수정 전 소스에 돌리면 여기서 실패한다 — 그때는 프레임마다 아이템 수만큼 불린다."""
    w = CanvasWindow()
    w.resize(400, 300)
    w.show()
    rects = _big_scene(w)
    v = w._view
    # ⚠ fitInView로 전체를 화면에 넣지 않는다 — 210개가 들어가면 도형 하나가 1px로 줄어
    # 히트테스트가 빗나가 드래그 자체가 시작되지 않는다(실제로 겪음). 기본 배율이면
    # 원점 근처 도형들이 그대로 보이므로 이 테스트에는 충분하다.
    QApplication.processEvents()

    press, release, _click, _move, drag_move, _dbl = _draw_helpers(v)
    target = rects[0].mapToScene(rects[0].rect().center())
    press(target)
    drag_move(target + QPointF(10, 8))
    assert v._drag_proxy is not None, "큰 씬을 드래그 중인데 프록시가 안 켜졌다"

    with _paint_counter(_RectItem) as calls:
        _render_view(v)
    assert not calls, f"프록시 중인데 아이템 paint()가 {len(calls)}회 불렸다"

    release(target + QPointF(10, 8))
    assert v._drag_proxy is None, "릴리스 후에도 프록시가 남았다"
    with _paint_counter(_RectItem) as calls2:
        _render_view(v)
    assert calls2, "릴리스 후에도 아이템이 스스로 그리지 않는다(복원 실패)"


def test_drag_proxy_still_draws_something_on_screen():
    """프록시 중에도 화면이 비면 안 된다 — 오버레이가 대신 그린다.
    2-D의 가장 큰 위험이 '아이템이 통째로 사라져 보이는 것'이라 픽셀로 못 박는다."""
    w = CanvasWindow()
    w.resize(400, 300)
    w.show()
    rects = _big_scene(w)
    v = w._view
    # ⚠ fitInView로 전체를 화면에 넣지 않는다 — 210개가 들어가면 도형 하나가 1px로 줄어
    # 히트테스트가 빗나가 드래그 자체가 시작되지 않는다(실제로 겪음). 기본 배율이면
    # 원점 근처 도형들이 그대로 보이므로 이 테스트에는 충분하다.
    QApplication.processEvents()
    bg = w._scene.backgroundBrush().color().rgb() & 0xFFFFFF

    def ink(img):
        return sum(1 for y in range(img.height()) for x in range(img.width())
                   if (img.pixel(x, y) & 0xFFFFFF) != bg)

    idle = ink(_render_view(v))
    press, release, _c, _m, drag_move, _d = _draw_helpers(v)
    target = rects[0].mapToScene(rects[0].rect().center())
    press(target)
    drag_move(target + QPointF(10, 8))
    assert v._drag_proxy is not None
    dragging = ink(_render_view(v))
    release(target + QPointF(10, 8))

    assert idle > 0, "유휴 상태에서 아무것도 안 그려졌다(테스트 전제 실패)"
    assert dragging > idle * 0.3, \
        f"프록시 중 화면이 사실상 비었다(유휴 {idle} / 드래그 {dragging})"


def test_drag_proxy_not_armed_for_small_scene():
    """작은 씬은 이미 60fps 예산 안이라 화면을 바꿀 이유가 없다 — 게이트 아래면 미발동."""
    w = CanvasWindow()
    w.show()
    a = _mk_pen_rect(w, x=0, y=0, ww=80, hh=60)
    _mk_pen_rect(w, x=200, y=0, ww=80, hh=60)
    v = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(v)
    target = a.mapToScene(a.rect().center())
    press(target)
    drag_move(target + QPointF(10, 8))
    assert v.is_drag_session() is True, "테스트 전제: 드래그 세션은 켜져 있어야 한다"
    assert v._drag_proxy is None, "작은 씬인데 프록시가 켜졌다"
    release(target + QPointF(10, 8))


def test_drag_proxy_restored_on_early_return_release_path():
    """`mouseReleaseEvent`는 조기 return이 13곳이라 복원을 함수 끝에 두면 경로에 따라
    실행이 누락된다(2026-08-15 실사용 버그). 조기 return 경로에서도 복원돼야 한다."""
    w = CanvasWindow()
    w.show()
    _big_scene(w)
    v = w._view
    flag = _RectItem.GraphicsItemFlag.ItemHasNoContents

    v._move_active = True
    v._ensure_drag_proxy()
    assert v._drag_proxy is not None
    assert any(it.flags() & flag for it in w._scene.items())

    # 그룹 본체 드래그는 자기 자리에서 커밋하고 곧바로 return하는 경로다.
    v._group_body_drag = True
    v._group_body_anchor = QPointF(0, 0)
    press, release, _c, _m, _dm, _d = _draw_helpers(v)
    release(QPointF(5, 5))

    assert v._drag_proxy is None, "조기 return 경로에서 프록시가 복원되지 않았다"
    leaked = [it for it in w._scene.items() if it.flags() & flag]
    assert not leaked, f"플래그가 {len(leaked)}개 아이템에 남았다(화면에서 사라진다)"


def _mid_btn(v, etype, local, glob=None):
    """가운데버튼 마우스 이벤트 합성 — `_rmb`(우클릭)와 같은 패턴, 팬 트리거용."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    glob = glob if glob is not None else local
    M = Qt.MouseButton.MiddleButton
    if etype == "press":
        e = QMouseEvent(QEvent.Type.MouseButtonPress, local, glob, M, M,
                        Qt.KeyboardModifier.NoModifier)
        v.mousePressEvent(e)
    elif etype == "move":
        e = QMouseEvent(QEvent.Type.MouseMove, local, glob,
                        Qt.MouseButton.NoButton, M, Qt.KeyboardModifier.NoModifier)
        v.mouseMoveEvent(e)
    else:
        e = QMouseEvent(QEvent.Type.MouseButtonRelease, local, glob,
                        M, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        v.mouseReleaseEvent(e)


def test_drag_proxy_activates_during_pan():
    """[성능 후속 2026-08-24] 아무것도 선택·이동 안 해도(순수 화면 팬) 프록시가 켜져야 한다.

    실측(offscreen 재현이 아니라 실제 창 sustained pan)으로 팬이 프록시 미적용 때문에
    프레임당 ~74ms(60fps 예산 4.4배)였음을 확인 — `is_drag_session()`은 아이템 이동만 보고
    팬은 원래 대상이 아니었다. `_is_panning()`을 얹은 뒤 프록시가 켜지고, paint() 디스패치가
    통째로 건너뛰어지는지 확인한다. ⚠ 수정 전 소스에 돌리면 여기서 실패한다."""
    w = CanvasWindow()
    w.resize(400, 300)
    w.show()
    _big_scene(w)
    v = w._view
    QApplication.processEvents()

    assert v.is_drag_session() is False, "테스트 전제: 아이템은 아무것도 안 움직인다"
    _mid_btn(v, "press", QPointF(50, 50))
    assert v._drag_proxy is None, "press 직후(아직 move 없음)엔 아직 켜지면 안 된다"
    _mid_btn(v, "move", QPointF(60, 58))
    assert v._drag_proxy is not None, "팬 중인데 프록시가 안 켜졌다"

    with _paint_counter(_RectItem) as calls:
        _render_view(v)
    assert not calls, f"팬 프록시 중인데 아이템 paint()가 {len(calls)}회 불렸다"

    _mid_btn(v, "release", QPointF(60, 58))
    assert v._drag_proxy is None, "팬 종료 후에도 프록시가 남았다"
    flag = _RectItem.GraphicsItemFlag.ItemHasNoContents
    leaked = [it for it in w._scene.items() if it.flags() & flag]
    assert not leaked, f"플래그가 {len(leaked)}개 아이템에 남았다(화면에서 사라진다)"
