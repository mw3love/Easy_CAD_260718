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
    # [회귀 방지 2026-08-10] 실사용 재현 — 삼각형이 낀 다중선택에서 그룹 점선 테두리의 왼쪽
    # 변이 삼각형의 실제 뒤쪽 변(back edge)보다 바깥에 떠 보였다. 원인은 `_GroupTransform.
    # bbox()`가 `_content_rect()`(패딩된 자기 bbox)를 썼기 때문 — `_apply_smart_snap.srect()`
    # 와 같은 병(`_tight_scene_bbox` 주석 참조)이라 같은 헬퍼로 통일해 고쳤다.
    w = CanvasWindow()
    tri = _SymbolItem("triangle", QRectF(0, 0, 140, 100))   # 폭>높이 → 뒤쪽 변에 x-패딩 생김
    tri.setPen(w.make_pen()); tri.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    tri.setFlags(tri.GraphicsItemFlag.ItemIsSelectable | tri.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tri)
    rect = _mk_rect(w._scene, w.make_pen(), 100, 0, 100, 100)
    tri.setSelected(True); rect.setSelected(True)
    back_x = _tri_rect(tri.rect()).left()   # tri.pos()는 (0,0)이라 로컬=씬
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


def test_qc_dots_geometry():
    # [하나의 시스템으로 통합 2026-08-01 → 2026-08-03 재도입] 선택된 네모의 상하좌우 접속점은
    # 테두리에서 `_HANDLE_GAP_FACTOR`만큼 바깥으로 띄운 자리다 — "핸들이 도형 안쪽에 있는
    # 것처럼 보인다"는 실사용 지적으로 되살렸다(2026-08-01엔 선택 여부에 따라 gap 유무가
    # 갈리는 비일관성 때문에 없앴었는데, 이번엔 hover-port 미리보기도 같은 gap을 써서 그
    # 비일관성 자체를 없앴다 — test_qc_dot_at_roundtrip·test_hover_port_at_* 참조).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    dots = dict((k, r) for k, r in a._qc_dot_rects())
    assert set(dots) == {"t", "r", "b", "l"}
    br = a.rect()
    gap = a._handle_px() * a._HANDLE_GAP_FACTOR
    assert _close(dots["r"].center(), QPointF(br.right() + gap, br.center().y()))
    assert _close(dots["l"].center(), QPointF(br.left() - gap, br.center().y()))
    assert _close(dots["t"].center(), QPointF(br.center().x(), br.top() - gap))
    assert _close(dots["b"].center(), QPointF(br.center().x(), br.bottom() + gap))




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




def test_smart_align_shows_all_tied_roles():
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
    # [신규기능 2026-08-10] 실사용 지적 — 삼각형 bbox가 정사각이 아니면(폭≠높이) 정삼각형이
    # bbox 안쪽에 내접해(`_tri_rect`) 뒤쪽 변(꼭짓점 2개)이 bbox 왼쪽 변보다 안쪽에 있다. 예전
    # bbox 전용 스마트 스냅은 이 "실제 뒤쪽 변" 위치를 몰라 삼각형이 사각형에 딱 붙지 않았다 —
    # 실제 윤곽 정점(`_real_snap_vertices_local`)을 후보에 추가해 해결.
    w = CanvasWindow()
    rect = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    tri = _SymbolItem("triangle", QRectF(0, 0, 160, 90))   # 폭>높이 → 뒤쪽 변에 x-패딩 생김
    tri.setPen(w.make_pen()); tri.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    tri.setFlags(tri.GraphicsItemFlag.ItemIsSelectable | tri.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tri)
    v = w._view
    thr = 6.0 / v._view_scale()
    back_x_local = _tri_rect(tri.rect()).left()
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
    back_x_scene = _tri_rect(tri.rect()).left()   # tri.pos()는 (0,0)이라 로컬=씬
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
    # [2026-08-04] "순서도" 팔레트 섹션 제거 — sym:* 도구는 백엔드에 남아 여전히 무장·생성되지만
    # 동기화할 팔레트 버튼이 없다.
    assert not hasattr(w, "_sym_buttons")




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
    # [회귀 방지 2026-08-10] 실사용 지적 — 일반 로직(bbox N/E/S/W 투영)은 삼각형의 사선 변에서
    # "그 변의 진짜 중점"이 아니라 "박스 중심에서 내린 최근접점"을 줘 어긋났다(뒤쪽 축정렬
    # 변만 우연히 맞음). 폭≠높이인 비정사각 박스로 확실히 검증(정사각이면 어긋남이 작아
    # 착시로 우연히 맞아 보일 수 있음).
    tri = _SymbolItem("triangle", QRectF(0, 0, 200, 140))
    tr = _tri_rect(tri.rect())
    tl, bl = QPointF(tr.left(), tr.top()), QPointF(tr.left(), tr.bottom())
    apex = QPointF(tr.right(), tr.center().y())
    expect = {
        "t": QPointF((apex.x() + tl.x()) / 2.0, (apex.y() + tl.y()) / 2.0),
        "r": apex,
        "b": QPointF((bl.x() + apex.x()) / 2.0, (bl.y() + apex.y()) / 2.0),
        "l": QPointF(tl.x(), tr.center().y()),
    }
    got = dict(zip("trbl", _shape_ports(tri)))
    for k, exp in expect.items():
        sp, _n = got[k]
        assert abs(sp.x() - exp.x()) < 1e-6 and abs(sp.y() - exp.y()) < 1e-6, (k, sp, exp)


def test_box_corner_rects_triangle_at_real_vertices():
    # [회귀 방지 2026-08-10, 후속 수정 포함] 실사용 지적 — 꼭짓점 사각 핸들이 바운딩박스
    # 모서리라 삼각형의 실제 꼭짓점과 떨어져 보였다. 뒤쪽 두 꼭짓점(TL·BL)은 핸들 위치를
    # 실제 꼭짓점(+기존 핸들 간격)으로 옮겼는지 검증. 앞쪽 꼭짓점(TR·BR)은 처음엔 둘 다
    # 거기 두었다가, 이미 그 자리에 있는 qc-dot과 마커 두 개가 겹쳐 보인다는 후속 지적으로
    # 아예 뺐다 — qc-dot이 전담(리사이즈는 TL·BL 두 핸들 어느 쪽을 끌어도 가능해 능력 손실 없음).
    tri = _SymbolItem("triangle", QRectF(0, 0, 200, 140))
    tr = _tri_rect(tri.rect())
    rects = dict(tri._box_corner_rects())
    gap = tri._handle_px() * tri._HANDLE_GAP_FACTOR
    assert set(rects.keys()) == {0, 3}   # 앞쪽 꼭짓점(1·2)은 더 이상 핸들로 안 뜬다
    assert abs(rects[0].center().x() - (tr.left() - gap)) < 1e-6   # TL: 뒤쪽 위 꼭짓점, 바깥(-x)으로 gap
    assert abs(rects[0].center().y() - (tr.top() - gap)) < 1e-6
    assert abs(rects[3].center().x() - (tr.left() - gap)) < 1e-6   # BL: 뒤쪽 아래 꼭짓점
    assert abs(rects[3].center().y() - (tr.bottom() + gap)) < 1e-6




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
    tr = _tri_rect(tri.rect())
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


