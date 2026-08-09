"""8포트·DXF 가져오기/내보내기·표·Mermaid·Sketch 빌더

tests/test_easycad.py 2026-08-02 분할분. 실행: python tests/test_easycad.py (전체) 또는 pytest test_part4_ports_fileio.py.
"""
from _shared import *  # noqa: F401,F403


def test_diamond_cardinal_normals_are_axis_aligned():
    # [실사용 버그 2026-07-29] 마름모 좌우 꼭짓점(E/W)이 폭≠높이(홀쭉하지 않은 비율)일 때
    # _nearest_border의 변-기준 법선이 기울어져 라우터가 '수직'으로 오판, 좌우 꼭짓점인데
    # 화살표가 위아래로 드나들었다. N/E/S/W 포트 법선은 위치는 그대로 두고 방향만 축정렬로
    # 강제해야 한다(실제 신고된 185x106 비율로 재현).
    sym = _SymbolItem("decision", QRectF(0, 0, 185, 106))
    ports = _shape_ports(sym)
    n_dirs = [(round(n.x(), 3), round(n.y(), 3)) for _p, n in ports[:4]]
    assert n_dirs == [(0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)], n_dirs
    for _p, n in ports[:4]:
        horiz = abs(n.x()) >= abs(n.y())
        assert horiz == (abs(n.x()) == 1.0), "N/E/S/W는 정확히 축정렬이어야 한다"
    # 네모·원은 이미 축정렬이라 이 보정이 no-op이어야 한다(회귀 방지).
    r = _RectItem(QRectF(0, 0, 185, 60))
    r_dirs = [(round(n.x(), 3), round(n.y(), 3)) for _p, n in _shape_ports(r)[:4]]
    assert r_dirs == [(0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0)], r_dirs




def test_port_priority_then_continuous_fallback():
    # M2: 포트 근처 커서 → 포트에 딱. 포트에서 먼 변 중간 → 기존 연속 외곽선 폴백.
    w = CanvasWindow(); w.show(); w.set_tool("arrow"); w._zoom_reset()
    view = w._view
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))
    sym.setPen(w.make_pen()); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sym.setFlags(sym.GraphicsItemFlag.ItemIsSelectable | sym.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sym)
    # N 포트(250,0) 근처(253,3) → 포트로 스냅
    snap = view._border_snap_at(view.mapFromScene(QPointF(253, 3)))
    assert snap is not None and _close(snap[0], QPointF(250, 0)), snap
    # N-E 변 위, N 포트와 대각 꼭짓점 포트(286.76,22.06, 8포트 확장분) 사이 중간점(~21px씩) →
    # 포트 밖(18px 반경 초과) → 연속 외곽선(그 점 그대로)
    snap2 = view._border_snap_at(view.mapFromScene(QPointF(268.38, 11.03)))
    assert snap2 is not None and _close(snap2[0], QPointF(268.38, 11.03), eps=2), snap2




def test_hover_port_at_skips_selected_shape():
    # [8포트 select-hover 2026-07-29] 선택 도구에서 포트 hover는 '미선택' 도형에만 반응한다
    # (선택된 도형은 리사이즈·회전 핸들과 자리가 겹쳐 qc-dot이 담당).
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    view = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)
    hit = view._hover_port_at(view.mapFromScene(QPointF(100, 30)))   # E 포트 근처
    assert hit is not None and hit[0] is r and _close(hit[1], QPointF(100, 30))
    r.setSelected(True)
    assert view._hover_port_at(view.mapFromScene(QPointF(100, 30))) is None




def test_select_tool_port_drag_creates_connector():
    # [8포트 select-hover] 선택 도구에서 미선택 도형 포트를 드래그해 다른 도형에 이으면 도형
    # 복제 없이 커넥터만 생성된다(qc-dot과 달리 선택 여부 무관 hover 기반, 클릭/드래그는
    # release에서 가른다). [① 빈 캔버스 드롭 2026-08-01] 스냅 대상 없는 빈 캔버스 드래그는
    # test_select_tool_port_drag_into_empty_space_creates_shape가 따로 검증(새 도형 생성).
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    view = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)
    tgt = _mk_pen_rect(w, x=260, y=0, ww=100, hh=60)
    tgt_center = tgt.mapToScene(tgt.rect().center())
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    n_rect0 = len([x for x in w._scene.items() if isinstance(x, _RectItem)])
    press(QPointF(100, 30))                 # E 포트
    drag_move(tgt_center)                   # 임계 초과 — 커넥터 프리뷰로 전환(기존 도형 내부)
    release(tgt_center)
    arrows = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    assert len(arrows) == 1, "포트 드래그로 커넥터가 생성돼야 한다"
    assert len([x for x in w._scene.items() if isinstance(x, _RectItem)]) == n_rect0  # 복제 없음
    assert arrows[0]._bind_start is r                                # 시작이 그 도형에 바인딩
    assert arrows[0]._bind_end is tgt                                # 끝도 기존 도형에 바인딩
    assert not r.isSelected()                                        # 드래그였으므로 도형 선택 폴백 없음




def test_select_tool_port_drag_into_empty_space_creates_shape():
    # [① 빈 캔버스 드롭 2026-08-01 → 2026-08-04 4차 갱신, 실사용 결정] 스냅 대상 없는 빈
    # 캔버스로 접속점을 드래그하면(도형 종류 무관) 이제 도형을 만들지 않고 끝이 비어있는
    # (미결) 화살표만 남긴다 — "드래그=화살표만"으로 규칙 통일(포트 예외 없이).
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    view = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    n_rect0 = len([x for x in w._scene.items() if isinstance(x, _RectItem)])
    press(QPointF(100, 30))                 # E 포트
    drag_move(QPointF(400, 200))            # 빈 캔버스
    release(QPointF(400, 200))
    arrows = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    assert len(arrows) == 1
    assert len(rects) == n_rect0                                     # 새 도형 없음
    assert arrows[0]._bind_start is r and arrows[0]._bind_end is None
    assert _close(QPointF(arrows[0].mapToScene(arrows[0]._pts[-1])), QPointF(400, 200))




def test_select_tool_port_click_without_drag_just_selects():
    # [실사용 요청 2026-08-09, 5차 — 클릭=복제 폐지] 포트(접속점) 위에서 드래그 없이 누르고
    # 떼면(제자리 클릭) 예전엔 즉시 도형 복제+화살표가 생겼으나, 의도치 않은 복제가 다른
    # 작업을 방해한다는 피드백으로 폐지 — 이제는 그 도형을 선택만 한다(드래그하면 여전히
    # 화살표만 생성, 아래 test_select_tool_port_drag_creates_connector가 검증).
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    view = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)
    press, release, _c, _m, _dm, _d = _draw_helpers(view)
    n0 = len([x for x in w._scene.items() if isinstance(x, _RectItem)])
    press(QPointF(100, 30)); release(QPointF(100, 30))               # 제자리 클릭(E 포트)
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    arrows = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    assert len(rects) == n0, "제자리 클릭이 도형을 복제하면 안 됨"
    assert len(arrows) == 0, "제자리 클릭이 화살표를 만들면 안 됨"
    assert r.isSelected()




def test_port_drag_self_loop_binds_and_avoids_corner_hug():
    # [자기자신 연결 버그 수정 2026-07-30] 같은 도형의 서로 다른 두 포트를 커넥터로 이으면(자기
    # 연결) 전에는 'snap 도형이 src면 무바인딩' 가드 때문에 도착 쪽이 안 붙어(ne=None) 법선
    # 스텁이 안 생기고, 모서리를 그대로 파고드는 경로가 나왔다(사용자 실사용 스크린샷 제보).
    # 라우터(_route_ortho) 자체는 자기연결(conn_rects 양끝이 같은 rect)을 이미 올바르게
    # 바깥으로 우회시킨다는 걸 확인했으므로, 수정은 '충분히 먼' 자기연결이면 바인딩을 허용하는 것.
    from easycad.canvas.annotator_core import _path_hits_rects
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    view = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    press(QPointF(100, 30))                 # E 포트(시작)
    drag_move(QPointF(50, 60))              # S 포트 쪽으로 — 같은 도형, 충분히 먼 다른 포트
    release(QPointF(50, 60))
    arrows = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    assert len(arrows) == 1
    arr = arrows[0]
    assert arr._bind_start is r and arr._bind_end is r, "자기연결도 양끝 다 바인딩돼야 한다"
    pts = [arr.mapToScene(p) for p in arr._pts]
    r_rect = r.mapRectToScene(r.rect())
    assert not _path_hits_rects(pts, [r_rect]), ("경로가 자기 도형을 관통/재진입", pts)
    # 시작 이탈 스텁은 수평(E 법선), 도착 진입 스텁은 수직(S 법선) — 모서리를 파고들지 않고
    # 법선 방향으로 먼저 빠져나간 뒤 꺾여야 한다(둘 다 인접점과 좌표가 그대로 같으면 스텁 없음=버그).
    assert abs(pts[0].y() - pts[1].y()) < 1e-6 and abs(pts[0].x() - pts[1].x()) > 1e-6
    assert abs(pts[-1].x() - pts[-2].x()) < 1e-6 and abs(pts[-1].y() - pts[-2].y()) > 1e-6




def test_port_drag_self_loop_near_start_stays_unbound():
    # 회귀 방지 — 드래그 시작 직후 같은 포트로 도로 스냅되는 퇴화 케이스(0-길이 자기연결)는
    # 여전히 무바인딩으로 남아야 한다(옛 가드가 원래 막으려던 경우, _far_enough_for_self_loop eps).
    from easycad.canvas.annotator_core import _far_enough_for_self_loop
    assert not _far_enough_for_self_loop(QPointF(100, 30), QPointF(100, 30.3))
    assert _far_enough_for_self_loop(QPointF(100, 30), QPointF(50, 60))




def test_arrow_binds_to_port_and_follows():
    # M4: 화살표를 포트 근처로 그리면 포트에 부착, 도형을 옮기면 포트 따라 이동.
    w = CanvasWindow(); w.show(); w.set_tool("arrow"); w._zoom_reset()
    view = w._view
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))
    sym.setPen(w.make_pen()); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sym.setFlags(sym.GraphicsItemFlag.ItemIsSelectable | sym.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sym)
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    press(QPointF(50, 200)); drag_move(QPointF(253, 3)); release(QPointF(253, 3))
    ar = [it for it in w._scene.items() if isinstance(it, _ArrowItem)][-1]
    assert ar.has_binding()
    assert _close(ar.mapToScene(ar._p2), QPointF(250, 0)), ar.mapToScene(ar._p2)
    sym.moveBy(40, 0); w._on_scene_changed(None)              # N 포트 (250,0)→(290,0)
    assert _close(ar.mapToScene(ar._p2), QPointF(290, 0)), ar.mapToScene(ar._p2)




def test_dxf_export():
    # Phase 3: 각 도형 타입이 개별 DXF 엔티티로 매핑되는지 + Y축 뒤집기 확인.
    import ezdxf
    from PyQt6.QtGui import QPen
    w = CanvasWindow(); w.show()
    sc = w._scene

    rect = _RectItem(QRectF(0, 0, 100, 60)); rect.setPen(QPen(QColor("red")))
    rect.setBrush(QBrush(Qt.BrushStyle.NoBrush)); rect.setPos(QPointF(10, 20)); sc.addItem(rect)
    circ = _EllipseItem(QRectF(0, 0, 80, 80)); circ.setPen(QPen(QColor("blue")))
    circ.setBrush(QBrush(Qt.BrushStyle.NoBrush)); circ.setPos(QPointF(200, 0)); sc.addItem(circ)
    ell = _EllipseItem(QRectF(0, 0, 120, 60)); ell.setPen(QPen(QColor("blue")))
    ell.setBrush(QBrush(Qt.BrushStyle.NoBrush)); ell.setPos(QPointF(400, 0)); sc.addItem(ell)
    line = _LineItem(QLineF(0, 0, 100, 50)); line.setPen(QPen(QColor("black"))); sc.addItem(line)
    ar = _ArrowItem(QColor("green"), 2.0, True)      # 베지어 화살 → SPLINE
    ar.set_points(QPointF(0, 0), QPointF(100, 40)); ar._ctrl1 = QPointF(30, -20)
    ar._ctrl2 = QPointF(70, 60); sc.addItem(ar)
    sar = _PolyArrowItem(QColor("purple"), 2.0, True)
    sar._pts = [QPointF(0, 0), QPointF(50, 0), QPointF(50, 40)]; sc.addItem(sar)
    txt = _TextItem(QColor("black")); txt.setPlainText("hello"); txt.setPos(QPointF(0, 300))
    sc.addItem(txt)
    badge = _BadgeItem(7, QColor("orange")); badge.setPos(QPointF(300, 300)); sc.addItem(badge)
    sym = _SymbolItem("decision", QRectF(0, 0, 100, 60)); sym.setPen(QPen(QColor("teal")))
    sym.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sym.setPos(QPointF(0, 400)); sc.addItem(sym)

    path = os.path.join(_TMP, "export.dxf")
    assert export_dxf(sc, path)
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    kinds = {}
    for e in msp:
        kinds[e.dxftype()] = kinds.get(e.dxftype(), 0) + 1
    # 베지어 화살 = SPLINE, 정원 = CIRCLE, 타원 = ELLIPSE, 직교화살+심볼+네모 = LWPOLYLINE.
    assert kinds.get("SPLINE", 0) >= 1, kinds          # arrow 샤프트
    assert kinds.get("CIRCLE", 0) >= 2, kinds          # circ + badge
    assert kinds.get("ELLIPSE", 0) >= 1, kinds         # ell
    assert kinds.get("LINE", 0) >= 1, kinds            # line
    assert kinds.get("LWPOLYLINE", 0) >= 4, kinds      # rect + sarrow + symbol(1+) + 화살촉2
    assert kinds.get("MTEXT", 0) >= 2, kinds           # txt + badge 번호
    # Y축 뒤집기: rect 좌상단 로컬(0,0)+pos(10,20) → world(10,20) → DXF(10,-20).
    rects = [e for e in msp if e.dxftype() == "LWPOLYLINE"]
    corners = [tuple(p[:2]) for e in rects for p in e.get_points()]
    assert any(abs(x - 10) < 1e-6 and abs(y + 20) < 1e-6 for x, y in corners), corners
    # 타입별 레이어 분리 확인.
    layers = {e.dxf.layer for e in msp}
    assert {"EC_RECT", "EC_ARROW", "EC_SARROW", "EC_SYMBOL", "EC_TEXT"} <= layers, layers




def test_new_symbol_kinds_export_dxf():
    # 심볼 확장(표준 4종: manual_input/manual_op/display/delay)의 다중 서브패스 경로가
    # DXF export에서 예외 없이 폴리라인으로 떨어지는지 확인. 곡선(화면출력 cubicTo·지연
    # arcTo)도 flatten 검증. (도메인 픽토그램 4종 카메라/증폭기/랙/안테나는 2026-08-03
    # 사용빈도·디자인 피드백으로 제거됨 — docs/history/2026-08.md 참조.)
    import ezdxf
    from PyQt6.QtGui import QPen
    new_kinds = ("manual_input", "manual_op", "display", "delay")
    w = CanvasWindow(); w.show()
    sc = w._scene
    for i, kind in enumerate(new_kinds):
        it = _SymbolItem(kind, QRectF(0, 0, 120, 72))
        it.setPen(QPen(QColor("black"))); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setPos(QPointF(0, i * 100))
        sc.addItem(it)
    path = os.path.join(_TMP, "new_symbols.dxf")
    assert export_dxf(sc, path)
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    poly_count = sum(1 for e in msp if e.dxftype() == "LWPOLYLINE")
    assert poly_count >= len(new_kinds)   # 최소 심볼당 1개(다중 서브패스는 그 이상)




def test_sketch_builder_accepts_new_symbol_kinds():
    # sketch_build._SYMBOL_KINDS(Qt 비의존 복제본)가 annotator_core 확장과 어긋나지 않는지.
    s = Sketch()
    n1 = s.symbol("manual_input", 0, 0, 120, 72, "IN-01")
    n2 = s.symbol("display", 200, 0, 120, 200, "출력")
    s.arrow(n1, n2)
    path = os.path.join(_TMP, "sketch_new_kinds.ecad")
    assert s.save(path) == 3
    w = CanvasWindow()
    assert load_document(w._scene, path) == 3
    kinds = {it._kind for it in w._scene.items() if isinstance(it, _SymbolItem)}
    assert kinds == {"manual_input", "display"}




def test_dxf_import_roundtrip():
    # Phase 3 후반: export→import 왕복에서 핵심 기하(꼭짓점·끝점·중심·텍스트·번호)가 보존되는지.
    # 소실 허용(설계 결정): 심볼 kind(→외곽선 _PathItem), 지속연결 바인딩, 자식 라벨(→독립),
    # 폭, 변환 필드값(회전/스케일은 월드 기하로만 보존). 판정은 dict 일치가 아니라 월드 기하 일치.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    from easycad.fileio.dxf_import import import_dxf

    def pen(c="#ffff0000", wd=3):
        p = QPen(QColor(c)); p.setWidthF(wd); return p

    sc = QGraphicsScene()
    # 네모(평행이동) + 회전 네모(회전 흡수 검증)
    rect = _RectItem(QRectF(0, 0, 100, 60)); rect.setPen(pen()); rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    rect.setPos(QPointF(10, 20)); sc.addItem(rect)
    rrot = _RectItem(QRectF(0, 0, 80, 40)); rrot.setPen(pen()); rrot.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    rrot.setPos(QPointF(600, 500)); rrot.setTransformOriginPoint(QPointF(40, 20)); rrot.setRotation(30); sc.addItem(rrot)
    # 정원 + 타원
    circ = _EllipseItem(QRectF(0, 0, 80, 80)); circ.setPen(pen("#ff0000ff")); circ.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    circ.setPos(QPointF(200, 0)); sc.addItem(circ)
    ell = _EllipseItem(QRectF(0, 0, 120, 60)); ell.setPen(pen("#ff0000ff")); ell.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    ell.setPos(QPointF(400, 0)); sc.addItem(ell)
    # 선
    line = _LineItem(QLineF(0, 0, 100, 50)); line.setPen(pen("#ff333333")); sc.addItem(line)
    # 곡선 화살표(끝쪽 촉) + 직선 화살표(시작쪽 촉 — 방향 복원 검증)
    ar = _ArrowItem(QColor("#ff00ff00"), 6, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 40)); ar._ctrl1 = QPointF(30, -20); ar._ctrl2 = QPointF(70, 60)
    sc.addItem(ar)
    ars = _ArrowItem(QColor("#ff00ff00"), 6, False)      # head_at_end=False
    ars.set_points(QPointF(0, 700), QPointF(150, 760)); sc.addItem(ars)
    # 직교 화살표
    sar = _PolyArrowItem(QColor("#ffff00ff"), 6, True)
    sar._pts = [QPointF(0, 0), QPointF(50, 0), QPointF(50, 40)]; sc.addItem(sar)
    # 텍스트
    txt = _TextItem(QColor("#ff000000")); txt.apply_font_size(20); txt.setPlainText("hello")
    txt.setPos(QPointF(0, 300)); sc.addItem(txt)
    # 번호 배지
    badge = _BadgeItem(7, QColor("#ffff9500")); badge.setPos(QPointF(300, 300)); badge.setScale(2.0); sc.addItem(badge)
    # 심볼(kind 소실 → 외곽선만)
    sym = _SymbolItem("decision", QRectF(0, 0, 100, 60)); sym.setPen(pen("#ff008080"))
    sym.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sym.setPos(QPointF(0, 400)); sc.addItem(sym)

    path = os.path.join(_TMP, "roundtrip_dxf.dxf")
    assert export_dxf(sc, path)
    sc2 = QGraphicsScene()
    import_dxf(sc2, path)

    # 네모 2개(평행이동·회전) — 월드 꼭짓점 집합 일치.
    rects = [it for it in sc2.items() if isinstance(it, _RectItem)]
    assert len(rects) == 2, len(rects)
    want = {tuple(_rect_world_corners(rect)), tuple(_rect_world_corners(rrot))}
    got = {tuple(_rect_world_corners(r)) for r in rects}
    assert got == want, (got, want)

    # 원/타원 — 월드 경계 꼭짓점 집합 일치(_RectItem과 같은 방식).
    ells = [it for it in sc2.items() if isinstance(it, _EllipseItem)]
    assert len(ells) == 2, len(ells)
    ewant = {tuple(_rect_world_corners(circ)), tuple(_rect_world_corners(ell))}
    egot = {tuple(_rect_world_corners(e)) for e in ells}
    assert egot == ewant, (egot, ewant)

    # 선 — 끝점 집합 일치 + 펜 두께(XDATA) 보존.
    lines = [it for it in sc2.items() if isinstance(it, _LineItem)]
    assert len(lines) == 1
    ln = lines[0].line()
    ends = sorted([(round(ln.x1(), 1), round(ln.y1(), 1)), (round(ln.x2(), 1), round(ln.y2(), 1))])
    assert ends == sorted([(0.0, 0.0), (100.0, 50.0)]), ends
    assert abs(lines[0].pen().widthF() - 3.0) < 1e-6, lines[0].pen().widthF()

    # 펜 두께 왕복 — 네모(3)·화살표(6)·직교화살(6)이 XDATA로 보존(기본값 1로 얇아지지 않음).
    r_thick = [r for r in rects if abs(r.pen().widthF() - 3.0) < 1e-6]
    assert len(r_thick) == 2, [r.pen().widthF() for r in rects]

    # 곡선 화살표 — 끝점+제어점(월드) 보존, 방향 복원.
    arrows = [it for it in sc2.items() if isinstance(it, _ArrowItem)]
    assert len(arrows) == 2, len(arrows)
    curved = [a for a in arrows if a._ctrl1 is not None]
    assert len(curved) == 1
    c = curved[0]
    assert _close(c.mapToScene(c._p1), QPointF(0, 0)) and _close(c.mapToScene(c._p2), QPointF(100, 40))
    assert _close(c.mapToScene(c._ctrl1), QPointF(30, -20)) and _close(c.mapToScene(c._ctrl2), QPointF(70, 60))
    assert c._head_at_end is True
    assert abs(c._width - 6.0) < 1e-6, c._width          # 화살표 폭 XDATA 보존
    straight = [a for a in arrows if a._ctrl1 is None][0]
    assert straight._head_at_end is False, "시작쪽 촉 방향이 복원돼야(무시+방향복원)"

    # 직교 화살표 — 정점 보존.
    sas = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    spts = [(round(p.x(), 1), round(p.y(), 1)) for p in sas[0]._pts]
    assert spts == [(0.0, 0.0), (50.0, 0.0), (50.0, 40.0)], spts

    # 텍스트 — 문자열+위치.
    texts = [it for it in sc2.items() if isinstance(it, _TextItem)]
    assert len(texts) == 1 and texts[0].toPlainText() == "hello"
    assert _close(texts[0].pos(), QPointF(0, 300), eps=1.5)

    # 배지 — 번호+중심+스케일(반경).
    badges = [it for it in sc2.items() if isinstance(it, _BadgeItem)]
    assert len(badges) == 1 and badges[0]._number == 7
    assert _close(badges[0].pos(), QPointF(300, 300), eps=1.0)
    assert abs(badges[0].scale() - 2.0) < 0.05, badges[0].scale()

    # 심볼 — kind 소실, 외곽선 _PathItem으로 복원(마름모 4변 영역 안).
    paths = [it for it in sc2.items() if isinstance(it, _PathItem)]
    assert len(paths) >= 1, "심볼 외곽선이 path로 복원돼야"
    dia = [p for p in paths if p.mapToScene(p.boundingRect()).boundingRect().center().y() > 380]
    assert dia, "심볼(y≈400 부근) 외곽선 path 존재해야"




def test_dxf_import_external_fallback():
    # 임의 외부 DXF(우리 레이어 관례 없음) → dxftype 폴백으로 손실 매핑(LINE·CIRCLE·TEXT).
    from PyQt6.QtWidgets import QGraphicsScene
    import ezdxf
    from easycad.fileio.dxf_import import import_dxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))                    # 레이어 "0"
    msp.add_circle((50, 50), 25)
    msp.add_text("EXT", dxfattribs={"insert": (10, 10)})
    path = os.path.join(_TMP, "external.dxf")
    doc.saveas(path)

    sc = QGraphicsScene()
    n = import_dxf(sc, path)
    assert n >= 3, n
    assert any(isinstance(it, _LineItem) for it in sc.items())
    assert any(isinstance(it, _EllipseItem) for it in sc.items())
    assert any(isinstance(it, _TextItem) for it in sc.items())




def test_dxf_import_insert_block():
    # [2026-07-29] 외부 무료 DXF 심볼/블록 라이브러리 흡수 — INSERT를 virtual_entities()로
    # 평탄화(배치 변환 baked-in) + 2개 이상 나오면 group_id로 한 블록처럼 묶기.
    from PyQt6.QtWidgets import QGraphicsScene
    import ezdxf
    from easycad.fileio.dxf_import import import_dxf, _compute_import_scale

    doc = ezdxf.new()
    blk = doc.blocks.new(name="CAM")
    blk.add_circle((0, 0), radius=5)
    blk.add_line((-5, 0), (5, 0))
    msp = doc.modelspace()
    msp.add_blockref("CAM", (100, 50), dxfattribs={"xscale": 2.0, "yscale": 2.0, "rotation": 30})
    msp.add_blockref("CAM", (300, 50))          # 스케일·회전 없는 두 번째 인스턴스
    msp.add_line((0, 0), (50, 0))                # 최상위(블록 아닌) 엔티티도 섞어서 확인
    path = os.path.join(_TMP, "insert_block.dxf")
    doc.saveas(path)

    # [2026-07-29] 순수 외부 DXF라 자동 재스케일 대상 — 절대좌표 대신 그 배율로 검증한다.
    expected_scale = _compute_import_scale(ezdxf.readfile(path).modelspace())

    sc = QGraphicsScene()
    n = import_dxf(sc, path)
    assert n == 5, n                              # 최상위 라인 1 + 블록 2개 × 엔티티 2개
    items = list(sc.items())
    gids = [getattr(it, "_group_id", None) for it in items]
    assert sum(1 for g in gids if g is None) == 1           # 최상위 라인만 무그룹
    groups = {g for g in gids if g}
    assert len(groups) == 2                                  # 인스턴스별로 서로 다른 그룹
    for g in groups:
        assert sum(1 for x in gids if x == g) == 2           # 인스턴스당 2개(원+선)
    # 스케일·회전이 없는 인스턴스(300,50) 원 반지름은 원본(5)×재스케일 배율, Y-flip만 적용.
    circles = [it for it in items if isinstance(it, _EllipseItem)]
    plain = [c for c in circles if abs(c.rect().width() / 2 - 5.0 * expected_scale) < 1e-3]
    assert len(plain) == 1
    c = plain[0].mapToScene(plain[0].rect().center())
    assert abs(c.x() - 300.0 * expected_scale) < 1e-3
    assert abs(c.y() - (-50.0 * expected_scale)) < 1e-3
    # 스케일 2배 인스턴스(100,50)는 반지름이 원본 대비 2배(10)×재스케일 배율로 baked-in.
    scaled = [c for c in circles if abs(c.rect().width() / 2 - 10.0 * expected_scale) < 1e-3]
    assert len(scaled) == 1




def test_dxf_import_nested_insert():
    # 블록 안에 또 다른 블록 참조(중첩 INSERT) — 재귀 평탄화로 두 단계 모두 풀려야 한다.
    from PyQt6.QtWidgets import QGraphicsScene
    import ezdxf
    from easycad.fileio.dxf_import import import_dxf, _compute_import_scale

    doc = ezdxf.new()
    inner = doc.blocks.new(name="LENS")
    inner.add_circle((0, 0), radius=2)
    outer = doc.blocks.new(name="CAM2")
    outer.add_line((-5, 0), (5, 0))
    outer.add_blockref("LENS", (3, 0))
    msp = doc.modelspace()
    msp.add_blockref("CAM2", (0, 0))
    path = os.path.join(_TMP, "nested_insert.dxf")
    doc.saveas(path)

    # [2026-07-29] 순수 외부 DXF라 자동 재스케일 대상 — 절대좌표 대신 그 배율로 검증한다.
    expected_scale = _compute_import_scale(ezdxf.readfile(path).modelspace())

    sc = QGraphicsScene()
    n = import_dxf(sc, path)
    assert n == 2
    ell = [it for it in sc.items() if isinstance(it, _EllipseItem)][0]
    c = ell.mapToScene(ell.rect().center())
    assert abs(c.x() - 3.0 * expected_scale) < 1e-3
    assert abs(c.y() - 0.0) < 1e-3
    gids = {getattr(it, "_group_id", None) for it in sc.items()}
    assert len(gids) == 1 and None not in gids               # 둘 다 같은(단일) 그룹


# ---- Phase 4: 이미지 삽입 ---------------------------------------------------


def test_image_item_basic():
    # rect 기반이라 박스 8핸들·리사이즈 기계를 물려받고, 픽스맵을 보관한다.
    it = _ImageItem(_mk_pixmap(), QRectF(0, 0, 40, 20))
    assert it._box_handles() is True          # setRect 보유 → 박스 핸들 경로
    assert it._pixmap.width() == 40 and it._pixmap.height() == 20
    c = it.clone()                            # 복제도 픽스맵·rect 보존
    assert isinstance(c, _ImageItem)
    assert c._pixmap.width() == 40 and c.rect() == QRectF(0, 0, 40, 20)




def test_image_aspect_lock_on_corner():
    # 꼭짓점 리사이즈는 원본 종횡비(2:1) 유지. 변 리사이즈는 자유(늘림 허용).
    it = _ImageItem(_mk_pixmap(40, 20), QRectF(0, 0, 40, 20))   # aspect 2.0
    it._box_orig_rect = QRectF(it.rect())
    it._box_bound = []
    it._box_snap = []
    it._box_resize = ("corner", 2)            # BR 꼭짓점(대각 고정 = TL)
    it._apply_box_resize(QPointF(100, 100))   # 자유라면 100×100(1:1)이 될 지점
    r = it.rect()
    assert abs(r.width() / r.height() - 2.0) < 1e-6   # 종횡비 고정됨
    # 변 드래그(오른쪽)는 종횡비 무시하고 자유.
    it2 = _ImageItem(_mk_pixmap(40, 20), QRectF(0, 0, 40, 20))
    it2._box_orig_rect = QRectF(it2.rect())
    it2._box_bound = []; it2._box_snap = []
    it2._box_resize = ("edge", "r")
    it2._apply_box_resize(QPointF(200, 0))
    r2 = it2.rect()
    assert r2.width() > 150 and abs(r2.height() - 20) < 1e-6   # 높이 불변, 폭만 늘어남




def test_image_roundtrip():
    # .ecad 저장/재열기에서 픽스맵 픽셀·크기·기하가 base64 embed로 보존되는지.
    w = CanvasWindow()
    it = _ImageItem(_mk_pixmap(40, 20, "#cc2233"), QRectF(0, 0, 40, 20))
    it.setPos(QPointF(120, 80))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    path = os.path.join(_TMP, "img.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    n = load_document(w2._scene, path)
    assert n == 1
    imgs = [x for x in w2._scene.items() if isinstance(x, _ImageItem)]
    assert len(imgs) == 1
    lo = imgs[0]
    assert lo._pixmap.width() == 40 and lo._pixmap.height() == 20
    assert _close(lo.pos(), QPointF(120, 80))
    assert lo.rect() == QRectF(0, 0, 40, 20)
    # 픽셀 색 보존(무손실 PNG embed) — 좌상단 픽셀이 원본 색.
    col = lo._pixmap.toImage().pixelColor(0, 0)
    assert (col.red(), col.green(), col.blue()) == (0xcc, 0x22, 0x33)




def test_image_insert_via_host():
    # host._insert_image_at: 파일 → 씬에 삽입(중심 배치·긴 변 축소·undo 등록).
    w = CanvasWindow()
    png = os.path.join(_TMP, "src.png")
    _mk_pixmap(800, 400, "#22aa55").save(png, "PNG")   # 대형 → 긴 변 400으로 축소돼야
    w._insert_image_at(png, QPointF(0, 0))
    imgs = [x for x in w._scene.items() if isinstance(x, _ImageItem)]
    assert len(imgs) == 1
    it = imgs[0]
    assert it._pixmap.width() == 800                    # 원본 해상도 보관(표시만 축소)
    assert abs(it.rect().width() - 400.0) < 1e-6        # 긴 변 = _IMG_LONG
    assert abs(it.rect().height() - 200.0) < 1e-6       # 종횡비 유지(2:1)
    assert _close(it.sceneBoundingRect().center(), QPointF(0, 0), eps=1.0)  # 중심 배치
    assert it.isSelected()
    w.undo()                                            # 삽입 undo로 제거
    assert not [x for x in w._scene.items() if isinstance(x, _ImageItem)]




def test_paste_clipboard_image_when_buffer_empty():
    # [신규기능] 내부 붙여넣기 버퍼가 비어 있으면 Ctrl+V(paste_selection)가 시스템
    # 클립보드 이미지를 뷰 중앙에 삽입한다.
    w = CanvasWindow(); w.show()
    assert not w._clip
    _app.clipboard().setPixmap(_mk_pixmap(80, 40, "#aa3366"))
    try:
        w.paste_selection()
        imgs = [x for x in w._scene.items() if isinstance(x, _ImageItem)]
        assert len(imgs) == 1
        assert imgs[0]._pixmap.width() == 80
        assert imgs[0].isSelected()
        w.undo()
        assert not [x for x in w._scene.items() if isinstance(x, _ImageItem)]
    finally:
        _app.clipboard().clear()




def test_paste_prefers_internal_clipboard_over_image():
    # 내부 붙여넣기 버퍼(copy_selection)가 있으면 시스템 클립보드 이미지는 무시 —
    # 기존 도형 복사/붙여넣기 동작이 이 신규기능으로 바뀌면 안 된다.
    w = CanvasWindow(); w.show()
    rect = _RectItem(QRectF(0, 0, 40, 20))
    rect.setFlags(rect.GraphicsItemFlag.ItemIsSelectable | rect.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(rect)
    rect.setSelected(True)
    w.copy_selection()
    _app.clipboard().setPixmap(_mk_pixmap(80, 40, "#336699"))
    try:
        w.paste_selection()
        assert not [x for x in w._scene.items() if isinstance(x, _ImageItem)]
        rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
        assert len(rects) == 2   # 원본 + 붙여넣기 사본
    finally:
        _app.clipboard().clear()




def test_image_skipped_in_dxf():
    # 범위 결정: DXF 내보내기는 이미지 제외(외부참조 배제). 씬에 이미지가 있어도
    # 크래시 없이 건너뛰고, 다른 엔티티(네모)는 정상 export.
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    img = _ImageItem(_mk_pixmap(40, 20), QRectF(0, 0, 40, 20))
    img.setFlags(img.GraphicsItemFlag.ItemIsSelectable | img.GraphicsItemFlag.ItemIsMovable)
    img.setPos(QPointF(200, 200)); w._scene.addItem(img)
    out = os.path.join(_TMP, "img_skip.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    types = [e.dxftype() for e in doc.modelspace()]
    assert "LWPOLYLINE" in types            # 네모는 export됨
    assert "IMAGE" not in types             # 이미지는 제외됨




def test_image_pdf_export():
    # 이미지가 포함된 씬도 PDF로 렌더된다(scene.render 경로).
    w = CanvasWindow()
    it = _ImageItem(_mk_pixmap(60, 40), QRectF(0, 0, 60, 40))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    out = os.path.join(_TMP, "img.pdf")
    assert export_pdf(w._scene, out, page="A4") is True
    assert os.path.getsize(out) > 0




def test_titleblock_roundtrip():
    # [Phase 4] 표제란/용지틀: 삽입 → 필드 설정 → .ecad 왕복에서 용지 크기·방향·필드값 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    tb = _TitleBlockItem("A2", "landscape",
                         {"number": "E-001", "title": "결선도", "scale": "1:50",
                          "client": "KBS", "author": "김민무", "reviewer": "홍길동",
                          "date": "2026-07-20"})
    tb.setFlags(tb.GraphicsItemFlag.ItemIsSelectable | tb.GraphicsItemFlag.ItemIsMovable)
    tb.setPos(QPointF(300, 400)); tb.setZValue(-1000.0)
    w._scene.addItem(tb)
    # 용지 치수: A2 가로 = 594 × 420
    pw, ph = tb.paper_wh()
    assert abs(pw - 594.0) < 0.1 and abs(ph - 420.0) < 0.1
    path = os.path.join(_TMP, "tb.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1
    got = [it for it in sc2.items() if isinstance(it, _TitleBlockItem)][0]
    assert got._size == "A2" and got._orient == "landscape"
    assert got._fields["number"] == "E-001"
    assert got._fields["scale"] == "1:50"
    assert got._fields["author"] == "김민무"
    assert _close(got.pos(), QPointF(300, 400))
    assert got.zValue() == -1000.0




def test_titleblock_drives_pdf_page():
    # 씬에 표제란이 있으면 PDF가 프레임 용지 경계를 기준으로 자동 전환(출력 성공).
    w = CanvasWindow()
    tb = _TitleBlockItem("A3", "portrait")
    tb.setFlags(tb.GraphicsItemFlag.ItemIsSelectable | tb.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tb)
    _mk_rect(w._scene, w.make_pen(), 40, 40, 120, 80)   # 용지 안 도형
    out = os.path.join(_TMP, "tb.pdf")
    # page 인자를 A4로 줘도 프레임(A3)이 우선함 — 성공 여부만 확인(실제 페이지는 실조건).
    assert export_pdf(w._scene, out, page="A4") is True
    assert os.path.getsize(out) > 0




def test_titleblock_shape_is_clickthrough():
    # 용지 내부는 히트영역에서 제외(shape 통과) → 그 위에 도형을 그리거나 잡을 수 있다.
    # 표제란 표 영역과 용지 테두리 밴드만 히트영역.
    tb = _TitleBlockItem("A2", "landscape")
    r = tb.rect()
    interior = QPointF(r.center().x(), r.top() + 60.0)   # 상단 여백 아래 내부
    assert not tb.shape().contains(interior)             # 내부는 통과(선택 안 됨)
    tbr = tb._tb_rect()
    assert tb.shape().contains(tbr.center())             # 표제란 표는 히트영역
    assert tb.shape().contains(QPointF(r.left() + 2.0, r.center().y()))  # 좌측 테두리 밴드




def test_titleblock_skipped_in_dxf():
    # 스코프: DXF 내보내기는 표제란 제외(조용히 skip), 다른 엔티티는 정상 export.
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    tb = _TitleBlockItem("A2", "landscape")
    tb.setFlags(tb.GraphicsItemFlag.ItemIsSelectable | tb.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tb)
    out = os.path.join(_TMP, "tb_skip.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    types = [e.dxftype() for e in doc.modelspace()]
    assert "LWPOLYLINE" in types            # 네모는 export됨




def test_table_cell_geometry():
    # [Phase 4] 표 격자 기하: 균등 분할 cell_rect·cell_at 왕복(로컬좌표).
    t = _TableItem(3, 4, QRectF(0, 0, 160, 60))   # 셀 40×20
    assert t.dims() == (3, 4)
    r00 = t.cell_rect(0, 0)
    assert r00 == QRectF(0, 0, 40, 20)
    r12 = t.cell_rect(1, 2)
    assert r12 == QRectF(80, 20, 40, 20)
    assert t.cell_at(QPointF(90, 25)) == (1, 2)     # (r=1, c=2)
    assert t.cell_at(QPointF(1, 1)) == (0, 0)
    assert t.cell_at(QPointF(159, 59)) == (2, 3)    # 우하단 셀
    assert t.cell_at(QPointF(-5, 5)) is None        # 격자 밖




def test_table_roundtrip():
    # 삽입 → 셀 텍스트 설정 → .ecad 왕복에서 rows·cols·header·rect·셀텍스트·기하 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    t = _TableItem(2, 3, QRectF(0, 0, 120, 40),
                   cells=[["번호", "명칭", "규격"], ["1", "카메라", "4K"]], header=True)
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    t.setPos(QPointF(200, 150)); t.setRotation(10)
    w._scene.addItem(t)
    path = os.path.join(_TMP, "table.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1
    got = [it for it in sc2.items() if isinstance(it, _TableItem)][0]
    assert got.dims() == (2, 3)
    assert got._header is True
    assert got.rect() == QRectF(0, 0, 120, 40)
    assert got.cell_text(0, 1) == "명칭"
    assert got.cell_text(1, 2) == "4K"
    assert _close(got.pos(), QPointF(200, 150))
    assert abs(got.rotation() - 10.0) < 1e-6




def test_table_clone():
    # 복제(그룹변형·복붙 경로): 셀 텍스트·차원·헤더가 독립 복사되고 원본과 분리.
    t = _TableItem(2, 2, QRectF(0, 0, 80, 40), cells=[["a", "b"], ["c", "d"]], header=False)
    c = t.clone()
    assert isinstance(c, _TableItem)
    assert c.dims() == (2, 2) and c._header is False
    assert c.cell_text(1, 0) == "c"
    c.set_cell_text(1, 0, "X")                       # 복제본 변경이 원본에 안 샘
    assert t.cell_text(1, 0) == "c"




def test_table_insert_via_host():
    # host._insert_table 경로: 다이얼로그를 건너뛰고 삽입 로직을 직접 검증하기 어려우니
    # _TableItem을 직접 넣어 undo/선택/PDF까지 통하는지 확인.
    w = CanvasWindow()
    t = _TableItem(3, 3, QRectF(0, 0, 120, 42))
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t)
    w.push_undo_add(t)
    assert [x for x in w._scene.items() if isinstance(x, _TableItem)]
    w.undo()
    assert not [x for x in w._scene.items() if isinstance(x, _TableItem)]




def test_table_skipped_in_dxf():
    # 스코프: DXF 내보내기는 표 제외(조용히 skip), 다른 엔티티는 정상 export.
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    t = _TableItem(2, 2, QRectF(0, 0, 80, 40))
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    t.setPos(QPointF(200, 200)); w._scene.addItem(t)
    out = os.path.join(_TMP, "table_skip.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    types = [e.dxftype() for e in doc.modelspace()]
    assert "LWPOLYLINE" in types            # 네모는 export됨




def test_table_inline_edit():
    # 인라인 편집 로직: 커밋·Tab 이동(줄넘김)·Esc 취소가 셀 텍스트에 정확히 반영되는지.
    w = CanvasWindow()
    t = _TableItem(2, 2, QRectF(0, 0, 80, 40))
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t)
    v = w._view
    v._begin_cell_edit(t, 0, 0)
    ed = v._cell_editor
    ed.setText("A"); ed._move(0, 1)                 # Tab → (0,1)로 이동하며 (0,0) 커밋
    assert t.cell_text(0, 0) == "A"
    ed = v._cell_editor
    assert (ed._r, ed._c) == (0, 1)
    ed.setText("B"); ed._move(0, 1)                 # 줄 끝 Tab → 다음 줄 첫 칸 (1,0)
    assert t.cell_text(0, 1) == "B"
    ed = v._cell_editor
    assert (ed._r, ed._c) == (1, 0)
    ed.setText("Z"); ed._cancel(); ed.close()       # Esc 취소 → 커밋 안 됨
    assert t.cell_text(1, 0) == ""




def test_table_pdf_export():
    # 표가 포함된 씬도 PDF로 렌더된다(scene.render → paint 경로).
    w = CanvasWindow()
    t = _TableItem(2, 3, QRectF(0, 0, 120, 40), cells=[["A", "B", "C"], ["1", "2", "3"]])
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t)
    out = os.path.join(_TMP, "table.pdf")
    assert export_pdf(w._scene, out, page="A4") is True
    assert os.path.getsize(out) > 0




def test_table_col_boundary_at_and_drag():
    # [열폭 드래그 2026-07-31] 경계 hover 판정 + 드래그로 폭 교환(표 전체폭 불변) + 최소폭 클램프.
    t = _TableItem(2, 3, QRectF(0, 0, 120, 40))   # 열폭 40균등, 내부 경계 x=40, x=80
    assert t._col_boundary_at(QPointF(40, 20)) == 0
    assert t._col_boundary_at(QPointF(80, 20)) == 1
    assert t._col_boundary_at(QPointF(60, 20)) is None       # 경계가 아닌 곳
    assert t._col_boundary_at(QPointF(40, -5)) is None       # 세로 범위 밖

    t._begin_col_drag(0)
    t._drag_col_boundary_to(60.0)                 # 경계0을 x=60으로 이동
    t._end_col_drag()
    edges = t._col_edges_local()
    assert abs(edges[1] - 60.0) < 1e-6
    assert abs(edges[0]) < 1e-6 and abs(edges[-1] - 120.0) < 1e-6   # 표 전체폭 불변
    assert abs(edges[2] - 80.0) < 1e-6            # 건드리지 않은 경계는 그대로

    # 최소폭 클램프 — 화면 밖으로 끌어도 _MIN_COL_W 이하로는 안 좁아짐
    t._begin_col_drag(0)
    t._drag_col_boundary_to(-500.0)
    t._end_col_drag()
    edges2 = t._col_edges_local()
    assert abs(edges2[1] - t._MIN_COL_W) < 1e-6




def test_table_col_widths_roundtrip():
    # 비균등 열폭이 .ecad 저장/로드에 보존되고, 옛 파일(col_widths 없음)은 균등폭으로 안전 로드.
    from PyQt6.QtWidgets import QGraphicsScene
    from easycad.fileio.document import dict_to_item
    w = CanvasWindow()
    t = _TableItem(2, 3, QRectF(0, 0, 120, 40))
    t._col_widths = [0.5, 0.3, 0.2]
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t)
    path = os.path.join(_TMP, "table_colw.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1
    got = [it for it in sc2.items() if isinstance(it, _TableItem)][0]
    assert [round(x, 6) for x in got._col_widths] == [0.5, 0.3, 0.2]

    d = item_to_dict(t); d.pop("col_widths")           # 옛 파일 흉내
    old_item = dict_to_item(d)
    assert all(abs(x - 1.0 / 3) < 1e-6 for x in old_item._col_widths)




def test_table_clone_col_widths():
    # 복제 시 열폭도 독립 복사(원본과 분리)되어야 함.
    t = _TableItem(2, 2, QRectF(0, 0, 80, 40))
    t._col_widths = [0.7, 0.3]
    c = t.clone()
    assert [round(x, 6) for x in c._col_widths] == [0.7, 0.3]
    c._col_widths[0] = 0.9
    assert t._col_widths[0] == 0.7




def test_table_col_drag_view_integration():
    # [열폭 드래그] hover 감지 → press·drag로 열폭 변경, 마우스 놓으면 undo 스냅샷 커밋.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    t = _TableItem(2, 3, QRectF(0, 0, 120, 40))   # 경계 x=40, 80
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t); t.setSelected(True)
    view = w._view

    vp = view.mapFromScene(QPointF(40, 20))       # 경계0 hover
    hit = view._table_col_boundary_at(vp)
    assert hit is not None and hit[0] is t and hit[1] == 0

    view._table_col_add = hit
    view.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(vp), QPointF(vp),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert view._table_col_drag is t
    tgt = view.mapFromScene(QPointF(60, 20))      # 경계를 x=60으로 끌기
    view.mouseMoveEvent(QMouseEvent(
        QEvent.Type.MouseMove, QPointF(tgt), QPointF(tgt),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    view.mouseReleaseEvent(QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(tgt), QPointF(tgt),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert view._table_col_drag is None
    edges = t._col_edges_local()
    assert abs(edges[1] - 60.0) < 1.0
    assert abs(edges[-1] - 120.0) < 1e-6          # 표 전체폭 불변

    w.undo()                                       # undo → 원래 균등폭 복원
    assert abs(t._col_edges_local()[1] - 40.0) < 1e-6




def test_symbol_label_optical_center():
    # 원기둥은 윗 타원을 피해 라벨을 rect 중심보다 아래(광학중심)로, 문서는 아래 물결을 피해
    # 살짝 위로. 상하 대칭 kind(마름모·스타디움 등)는 rect 중심 그대로.
    cyl = _SymbolItem("database", QRectF(0, 0, 120, 56))
    dia = _SymbolItem("decision", QRectF(0, 0, 120, 56))
    doc = _SymbolItem("document", QRectF(0, 0, 120, 56))
    assert cyl._label_anchor().y() > cyl.rect().center().y()      # 아래로
    assert doc._label_anchor().y() < doc.rect().center().y()      # 위로
    assert abs(dia._label_anchor().y() - dia.rect().center().y()) < 1e-6  # 대칭=보정없음
    # 리사이즈 후에도 광학중심 오프셋이 rect에 비례해 유지된다.
    cyl.setRect(QRectF(0, 0, 240, 120))
    assert cyl._label_anchor().y() > cyl.rect().center().y()




def test_mermaid_parse_core():
    # 핵심 부분집합: 방향·노드 모양 8종 매핑·엣지 4종·파이프 라벨.
    from easycad.fileio.mermaid_import import parse_mermaid
    g = parse_mermaid(
        "flowchart TD\n"
        "  A[start] --> B{cond}\n"
        "  B -->|yes| C([end])\n"
        "  B -->|no| D[retry]\n"
        "  D --> B\n"
        "  E[(db)] --- C\n")
    assert g.direction == "TD"
    assert set(g.nodes) == {"A", "B", "C", "D", "E"}
    assert g.nodes["B"].shape == "rhombus"
    assert g.nodes["C"].shape == "stadium"
    assert g.nodes["E"].shape == "cylinder"
    assert g.nodes["A"].label == "start"
    assert len(g.edges) == 5
    # 파이프 라벨 흡수
    yes = [e for e in g.edges if e.src == "B" and e.dst == "C"][0]
    assert yes.label == "yes" and yes.arrow is True
    # --- 는 화살촉 없는 선
    line = [e for e in g.edges if e.src == "E"][0]
    assert line.arrow is False




def test_mermaid_parse_lr_inline_and_styles():
    # LR 방향 + 인라인 라벨(-- txt -->) + 점선/굵은선 스타일 분류.
    from easycad.fileio.mermaid_import import parse_mermaid
    g = parse_mermaid(
        "graph LR\n"
        "  S([start]) -- go --> T[work]\n"
        "  T -.-> U{ok?}\n"
        "  U ==> V\n")
    assert g.direction == "LR"
    e_go = [e for e in g.edges if e.src == "S"][0]
    assert e_go.label == "go"
    assert [e for e in g.edges if e.src == "T"][0].style == "dotted"
    assert [e for e in g.edges if e.src == "U"][0].style == "thick"
    assert g.nodes["V"].label == "V"   # bare 참조는 id를 라벨로




def test_mermaid_layout_levels_no_cycle_blowup():
    # 사이클(D-->B)이 있어도 레벨이 발산하지 않는다(BFS 거리).
    from easycad.fileio.mermaid_import import parse_mermaid, layout_positions
    g = parse_mermaid("flowchart TD\n A-->B\n B-->C\n C-->B\n A-->D\n")
    pos = layout_positions(g, node_w=120, node_h=56)
    ys = {k: pos[k][1] for k in pos}
    assert ys["A"] < ys["B"]          # 레벨 0 < 레벨 1
    assert ys["B"] == ys["D"]         # 같은 레벨(둘 다 A의 자식/형제)
    assert max(ys.values()) < 1000    # 발산 없음(예전 버그는 y가 수천까지 치솟았음)




def test_mermaid_layout_lr_axis_swap():
    # LR은 흐름이 x축, TD는 y축.
    from easycad.fileio.mermaid_import import parse_mermaid, layout_positions
    g = parse_mermaid("flowchart LR\n A-->B-->C\n")
    pos = layout_positions(g, node_w=120, node_h=56)
    assert pos["A"][0] < pos["B"][0] < pos["C"][0]   # x 증가
    assert pos["A"][1] == pos["B"][1] == pos["C"][1]  # y 동일




def test_mermaid_empty_raises():
    from easycad.fileio.mermaid_import import parse_mermaid, MermaidError
    for bad in ("", "   \n  ", "flowchart TD\n"):
        try:
            parse_mermaid(bad)
            assert False, "MermaidError 기대"
        except MermaidError:
            pass




def test_mermaid_import_via_host():
    # 전체 빌더: 도형+화살표 개수·라벨·지속연결 바인딩·자동라우팅·단일 undo.
    w = CanvasWindow()
    n_nodes, n_arrows, direction = w._build_mermaid(
        "flowchart TD\n"
        "  A[시작] --> B{조건?}\n"
        "  B -->|예| C[처리]\n"
        "  B -->|아니오| D([종료])\n"
        "  C --> D\n"
        "  E[(DB)] --- C\n")
    assert direction == "TD"
    assert n_nodes == 5 and n_arrows == 5
    nodes = [it for it in w._scene.items()
             if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]
    arrows = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(nodes) == 5 and len(arrows) == 5
    assert all(it.has_label() for it in nodes)               # 노드 라벨 부착
    assert all(a.has_binding() and a._auto_route for a in arrows)  # 지속연결+직교라우팅
    # 심볼 kind 매핑(마름모=decision, 스타디움=terminal, 원기둥=database)
    kinds = {it._kind for it in nodes if isinstance(it, _SymbolItem)}
    assert {"decision", "terminal", "database"} <= kinds
    assert len(w._undo) == 1                                  # 배치 전체가 한 번의 undo




def test_mermaid_labels_centered_not_stuck_at_origin():
    # 회귀: 라벨을 씬에 넣기 '전'에 붙이면 _sync_label이 no-op해 라벨이 도형 좌상단(0,0)에
    # 박힌다(초기 버그). 빌드 후 각 노드 라벨의 중심이 도형 중심 근방(가로 정렬, 세로는 광학보정
    # 허용)인지 확인 — (0,0)에 박히면 가로 오프셋이 도형 반폭만큼 크게 벌어진다.
    w = CanvasWindow()
    w._build_mermaid(
        "flowchart TD\n A[처리] --> B{유효?}\n B -->|예| C([끝])\n B -->|아니오| D[(저장)]\n")
    nodes = [it for it in w._scene.items()
             if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem)) and it._label is not None]
    assert len(nodes) == 4
    for it in nodes:
        sc = it.sceneBoundingRect().center()
        lc = it._label.sceneBoundingRect().center()
        assert abs(lc.x() - sc.x()) < 4, (it, lc, sc)     # 가로 중앙(0,0 박힘이면 크게 벗어남)
        assert abs(lc.y() - sc.y()) < 12, (it, lc, sc)    # 세로 중앙 근방(원기둥 광학보정 여유)




def test_mermaid_roundtrip():
    # import한 도면을 .ecad로 저장→열기 하면 노드·화살표가 보존된다(기존 직렬화 재사용).
    w = CanvasWindow()
    w._build_mermaid("flowchart LR\n A[a] --> B{b}\n B -->|x| C([c])\n")
    n0 = len([it for it in w._scene.items()
              if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))])
    a0 = len([it for it in w._scene.items() if isinstance(it, _PolyArrowItem)])
    path = os.path.join(_TMP, "mermaid.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    load_document(w2._scene, path)
    n1 = len([it for it in w2._scene.items()
              if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))])
    a1 = len([it for it in w2._scene.items() if isinstance(it, _PolyArrowItem)])
    assert n1 == n0 == 3 and a1 == a0 == 2




def test_mermaid_pdf_export():
    # import 결과가 PDF로 렌더된다(paint 경로 안전).
    w = CanvasWindow()
    w._build_mermaid("flowchart TD\n A[a]-->B{b}\n B-->C([c])\n")
    out = os.path.join(_TMP, "mermaid.pdf")
    assert export_pdf(w._scene, out, page="A4") is True
    assert os.path.getsize(out) > 0


def test_pdf_menu_action_merged_no_selection_variant():
    # [§8 항목14, 2026-08-07] "전체"/"선택영역" 별도 메뉴 2개 → 1개(_act_pdf)로 통합,
    # 선택지는 _PdfExportDialog 안 라디오로 이동 — 옛 _act_pdf_sel 액션은 더 이상 없다.
    w = CanvasWindow()
    assert not w._act_pdf.icon().isNull()
    assert not hasattr(w, "_act_pdf_sel")


def test_pdf_export_dialog_no_selection_disables_selection_radio():
    w = CanvasWindow()
    _mk_pen_rect(w, x=0, y=0, ww=50, hh=50)
    dlg = _PdfExportDialog(None, w._scene, has_selection=False)
    assert dlg._rb_all.isChecked()
    assert not dlg._rb_sel.isEnabled()
    opts = dlg.result_options()
    assert opts == {"selection_only": False, "page": "A4", "orientation": "landscape"}


def test_pdf_export_dialog_locks_paper_controls_to_title_frame():
    # 표제란이 있고 "전체 도면"이면 용지크기/방향 컨트롤이 잠기고 프레임 값을 반영한다
    # (프레임이 이미 용지 선택을 대신함 — 사용자 확인 2026-08-07).
    w = CanvasWindow()
    frame = _TitleBlockItem(size="A2", orient="portrait")
    w._scene.addItem(frame)
    _mk_pen_rect(w, x=10, y=10, ww=30, hh=30)
    dlg = _PdfExportDialog(None, w._scene, has_selection=False)
    assert not dlg._size_cb.isEnabled()
    assert not dlg._orient_cb.isEnabled()
    assert dlg._size_cb.currentData() == "A2"
    assert dlg._orient_cb.currentData() == "portrait"
    # 다이얼로그를 실제로 show()하지 않아 isVisible()은 항상 False(최상위가 안 떠서) —
    # setVisible() 호출 여부만 보는 isHidden()으로 확인.
    assert not dlg._frame_note.isHidden()
    # "선택 영역"으로 바꾸면 프레임이 적용되지 않으므로(export_pdf와 동일 규칙) 다시 풀린다.
    dlg._rb_sel.setEnabled(True)
    dlg._rb_sel.setChecked(True)
    assert dlg._size_cb.isEnabled()
    assert dlg._orient_cb.isEnabled()
    assert dlg._frame_note.isHidden()


def test_pdf_export_dialog_live_preview_updates_and_empty_shows_none():
    w = CanvasWindow()
    _mk_pen_rect(w, x=0, y=0, ww=50, hh=50)
    dlg = _PdfExportDialog(None, w._scene, has_selection=False)
    assert dlg._preview.pixmap() is not None and not dlg._preview.pixmap().isNull()
    # 선택 없이 "선택 영역"은 비활성화라 실제로 못 고르지만, 내부 미리보기 갱신 로직 자체는
    # render_preview(selection_only=True)가 None을 반환하는 경우 안내 문구로 대체하는지 확인.
    dlg._rb_sel.setEnabled(True)
    dlg._rb_sel.setChecked(True)
    assert dlg._preview.pixmap().isNull()
    assert dlg._preview.text() == "출력할 내용이 없습니다."


def test_render_preview_orientation_manual_override_matches_export_pdf():
    # 라이브 미리보기가 export_pdf와 같은 geometry(_resolve_geometry)를 쓰므로, 미리보기의
    # 가로/세로 비율만 보고도 실제 PDF 방향을 신뢰할 수 있다는 전제를 확인.
    w = CanvasWindow()
    _mk_pen_rect(w, x=0, y=0, ww=50, hh=50)
    px_land = render_preview(w._scene, page="A4", orientation="landscape")
    px_port = render_preview(w._scene, page="A4", orientation="portrait")
    assert px_land is not None and px_port is not None
    assert px_land.width() > px_land.height()
    assert px_port.height() > px_port.width()
    out_land = os.path.join(_TMP, "orient_landscape.pdf")
    out_port = os.path.join(_TMP, "orient_portrait.pdf")
    assert export_pdf(w._scene, out_land, page="A4", orientation="landscape") is True
    assert export_pdf(w._scene, out_port, page="A4", orientation="portrait") is True
    assert os.path.getsize(out_land) > 0 and os.path.getsize(out_port) > 0


def test_render_preview_title_frame_ignores_manual_orientation():
    # 프레임이 있으면(전체 출력) orientation 인자를 무시하고 프레임 방향을 따른다.
    w = CanvasWindow()
    frame = _TitleBlockItem(size="A3", orient="portrait")
    w._scene.addItem(frame)
    px = render_preview(w._scene, page="A4", selection_only=False, orientation="landscape")
    assert px is not None
    assert px.height() > px.width()  # 프레임이 portrait이므로 orientation="landscape" 무시




def test_sketch_argb_normalizes_color():
    # 빌더 색 정규화 → .ecad HexArgb(#AARRGGBB, alpha 먼저). Qt 비의존 순수 파이썬.
    assert _argb("#000000") == "#ff000000"        # 6자리 → 불투명 부여
    assert _argb("#FF3B30") == "#ffff3b30"         # 대문자·불투명
    assert _argb("#ff112233") == "#ff112233"       # 8자리 그대로
    assert _argb("#0f0") == "#ff00ff00"            # 3자리 확장




def test_sketch_build_roundtrip():
    # Phase 5 핵심: Sketch 빌더 → .ecad → load_document 왕복. 노드·심볼 kind·화살표 지속연결·
    # 라벨이 모두 편집가능 아이템으로 복원되는지. 빌더가 Qt 없이 만든 JSON을 앱이 그대로 연다.
    s = Sketch()
    a = s.symbol("terminal", 60, 40, 160, 70, "시작")
    b = s.symbol("decision", 90, 170, 120, 100, "조건?")
    c = s.box(300, 185, 160, 70, "처리")
    d = s.ellipse(90, 340, 120, 70, "끝")
    s.arrow(a, b)
    s.arrow(b, c, label="예")
    s.arrow(b, d, label="아니오")
    path = os.path.join(_TMP, "sketch.ecad")
    n = s.save(path)
    assert n == 7                                            # 노드 4 + 화살표 3

    w = CanvasWindow()
    load_document(w._scene, path)
    nodes = [it for it in w._scene.items()
             if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]
    arrows = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(nodes) == 4 and len(arrows) == 3
    # 심볼 kind 복원(마름모=decision, 스타디움=terminal)
    kinds = {it._kind for it in nodes if isinstance(it, _SymbolItem)}
    assert kinds == {"terminal", "decision"}
    # 화살표: 양끝 지속연결 + 직교 자동라우팅
    assert all(ar.has_binding() and ar._auto_route for ar in arrows)
    # 라벨: 노드 4개 전부 중앙 라벨 복원(0,0 박힘 아님 — 가로 중앙 정렬)
    labeled = [it for it in nodes if it._label is not None]
    assert len(labeled) == 4
    for it in labeled:
        sc = it.sceneBoundingRect().center()
        lc = it._label.sceneBoundingRect().center()
        assert abs(lc.x() - sc.x()) < 4, (it, lc, sc)




def test_sketch_arrow_binding_follows_move():
    # 지속연결 검증: 로드 후 화살표가 도형에 붙어 reroute(재라우팅)가 동작한다.
    s = Sketch()
    a = s.box(0, 0, 100, 60, "A")
    b = s.box(300, 0, 100, 60, "B")
    s.arrow(a, b)
    path = os.path.join(_TMP, "sketch_bind.ecad")
    s.save(path)
    w = CanvasWindow()
    load_document(w._scene, path)
    ar = next(it for it in w._scene.items() if isinstance(it, _PolyArrowItem))
    assert ar.has_binding()
    ar.reroute()                                            # 부착점 추종 + 직교 엘보(예외 없이)
    assert len(ar._pts) >= 2                                # 유효한 폴리라인 유지




def test_sketch_arrow_port_side_hint():
    # 밀집 순서도용: from_side/to_side로 접속 변을 명시하면 그 변 중점 포트에 붙는다
    # (피드백 루프를 본선과 겹치지 않게 측면으로 빼는 용도). 생략 시 최근접(기존 동작).
    s = Sketch()
    a = s.box(0, 0, 100, 60, "A")          # cx=50, cy=30
    b = s.box(0, 200, 100, 60, "B")        # cx=50, cy=230
    s.arrow(a, b)                          # 자동: a S(50,60) → b N(50,200)
    s.arrow(b, a, from_side="E", to_side="E")   # 루프: 둘 다 오른쪽 변으로
    doc = s.to_dict()
    down, loop = doc["items"][2], doc["items"][3]
    assert down["bind1_pt"] == [50.0, 60.0] and down["bind2_pt"] == [50.0, 200.0]
    assert loop["bind1_pt"] == [100.0, 230.0]   # b E
    assert loop["bind2_pt"] == [100.0, 30.0]    # a E
    # 잘못된 방향은 즉시 실패
    try:
        s.arrow(a, b, from_side="X")
        assert False, "잘못된 포트 방향이 통과됨"
    except ValueError:
        pass




def test_sketch_arrow_outer_channel():
    # 긴 루프백을 외곽 채널로 우회: channel_x면 명시 4점 경로 + auto_route=False
    # (코어 라우터가 다른 화살표를 장애물로 안 봐 생기는 내부 교차를 손수 회피).
    s = Sketch()
    a = s.box(0, 0, 100, 60, "A")          # A E=(100,30)
    b = s.box(0, 400, 100, 60, "B")        # B E=(100,430)
    s.arrow(b, a, from_side="E", to_side="E", channel_x=300)
    ar = s.to_dict()["items"][2]
    assert ar["auto_route"] is False
    assert ar["pts"] == [[100.0, 430.0], [300.0, 430.0], [300.0, 30.0], [100.0, 30.0]]
    assert ar["bind1"] == 1 and ar["bind2"] == 0        # 바인딩은 유지(끝점 추종)
    # 채널 2개 동시 지정은 실패
    try:
        s.arrow(a, b, channel_x=1, channel_y=1)
        assert False, "channel_x/y 동시 지정이 통과됨"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# [Phase 6 M2] 되돌리기/다시 실행 — 단일 스냅샷 저널(create/remove/mut) + redo 대칭.
# ---------------------------------------------------------------------------


def test_undo_redo_add_delete():
    # create/remove op: add 되돌림=제거, redo=재추가 / delete 되돌림=복귀, redo=제거.
    w = CanvasWindow()
    it = _mk_pen_rect(w)
    w.push_undo_add(it)
    assert it.scene() is not None
    w.undo(); assert it.scene() is None
    w.redo(); assert it.scene() is not None
    w._scene.removeItem(it); w.push_undo_delete([it])
    assert it.scene() is None
    w.undo(); assert it.scene() is not None
    w.redo(); assert it.scene() is None




def test_undo_redo_move_xform_geom():
    # 기존 5종 중 move/xform/geom(=mut의 pos/xform/geom sub)이 undo AND redo 왕복.
    w = CanvasWindow()
    it = _mk_pen_rect(w)
    old = QPointF(it.pos()); it.setPos(QPointF(100, 50))
    w.push_undo_move([(it, old)])
    w.undo(); assert _close(it.pos(), old)
    w.redo(); assert _close(it.pos(), QPointF(100, 50))

    bx = (QPointF(it.pos()), it.rotation(), it.scale(), QPointF(it.transformOriginPoint()))
    it.setRotation(30); it.setScale(1.5)
    w.push_undo_xform([(it, bx[0], bx[1], bx[2], bx[3])])
    w.undo(); assert abs(it.rotation()) < 1e-6 and abs(it.scale() - 1.0) < 1e-6
    w.redo(); assert abs(it.rotation() - 30) < 1e-6 and abs(it.scale() - 1.5) < 1e-6

    bg = it.capture_geom(); it.setRect(QRectF(0, 0, 80, 60))
    w.push_undo_geom([(it, bg)])
    w.undo(); assert abs(it.rect().width() - 40) < 1e-6
    w.redo(); assert abs(it.rect().width() - 80) < 1e-6




def test_undo_redo_state_color():
    # 색 변경(이전엔 미추적)이 mut의 'state' sub로 되돌려진다 — M2 근본 목표.
    w = CanvasWindow()
    it = _mk_pen_rect(w)
    before = it.capture_state()
    it.apply_color(QColor("#ff0000"))
    w.push_undo_state([(it, before)])
    assert it.pen().color().name() == "#ff0000"
    w.undo(); assert it.pen().color().name() == "#111111"
    w.redo(); assert it.pen().color().name() == "#ff0000"




def test_undo_redo_state_arrow_width():
    # 화살표(_color/_width 속성 계열)의 capture_state/apply_state 분기 커버.
    w = CanvasWindow()
    ar = _ArrowItem(QColor("#111111"), 2.0, True)
    ar.set_points(QPointF(0, 0), QPointF(50, 0))
    w._scene.addItem(ar)
    before = ar.capture_state()
    ar.apply_width(6.0)
    w.push_undo_state([(ar, before)])
    assert abs(ar._width - 6.0) < 1e-6
    w.undo(); assert abs(ar._width - 2.0) < 1e-6
    w.redo(); assert abs(ar._width - 6.0) < 1e-6




# ---- [신규기능 §8-12] 포트-테두리 trim 워크플로우 -------------------------------

def test_triangle_symbol_kind_basic():
    # 삼각형은 새 클래스가 아니라 기존 심볼 시스템(_SYMBOL_KINDS) 재사용 — 팔레트·직렬화·
    # DXF export가 다른 9종과 동일 코드로 공짜로 따라오는지 최소 확인.
    assert "triangle" in _SYMBOL_KINDS
    tri = _SymbolItem("triangle", QRectF(0, 0, 160, 120))
    assert tri._sym_path().elementCount() > 0
    assert not tri.boundingRect().isEmpty()


def test_triangle_dxf_export_is_3vertex_polygon():
    w = CanvasWindow()
    tri = _SymbolItem("triangle", QRectF(0, 0, 160, 120))
    tri.setPen(w.make_pen()); tri.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    w._scene.addItem(tri)
    out = os.path.join(_TMP, "triangle.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    polys = list(doc.modelspace().query("LWPOLYLINE"))
    assert len(polys) == 1 and len(polys[0]) == 3


def test_port_attaches_to_rect_border_and_snaps():
    w = CanvasWindow()
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 2))   # 위쪽 변 근처(중점 아님)
    assert port.parentItem() is dev
    assert port in dev._ports
    center = port.mapToScene(port.rect().center())
    assert _close(center, QPointF(60, 0), eps=0.1)   # 테두리 위로 정확히 스냅(y=0)


def test_dragging_attached_port_keeps_it_snapped_to_host_border():
    # [실사용 버그 수정 2026-08-03] 사용자 리포트: 포트를 옮길 때 테두리에 SNAP이 안 됨.
    # 드래그 중(setPos 제안값) 테두리 밖 아무 좌표를 줘도 itemChange가 즉시 최근접 테두리
    # 점으로 되돌려야 한다 — 코너를 넘어가면 인접한 변으로 자연스럽게 전환.
    w = CanvasWindow()
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))

    port.setPos(QPointF(150, 500))   # 테두리에서 한참 벗어난 좌표
    c = port.mapToScene(port.rect().center())
    assert abs(c.y() - 100) < 0.5   # 가장 가까운 아래쪽 변으로 스냅

    port.setPos(QPointF(-50, 30))   # 왼쪽 바깥
    c = port.mapToScene(port.rect().center())
    assert abs(c.x() - 0) < 0.5     # 왼쪽 변으로 스냅

    port.setPos(QPointF(199, -5))   # 우상단 코너 근처 → 다른 변(우측)으로 자연스럽게 전환
    c = port.mapToScene(port.rect().center())
    assert abs(c.x() - 200) < 0.5


def test_port_does_not_attach_to_non_triangle_symbol():
    # 사각형+삼각형만 호스트 대상 — 마름모(판단) 등 다른 심볼 근처엔 부착되지 않는다.
    w = CanvasWindow()
    dec = _SymbolItem("decision", QRectF(0, 0, 160, 100))
    dec.setPen(w.make_pen()); dec.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    dec.setFlags(dec.GraphicsItemFlag.ItemIsSelectable | dec.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(dec)
    port = w._create_port_at("port_rect", QPointF(80, 2))
    assert port.parentItem() is not dec


def test_port_follows_host_resize_proportionally():
    w = CanvasWindow()
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))   # fx=0.3
    dev.setRect(QRectF(0, 0, 400, 100))   # 폭 2배
    center = port.mapToScene(port.rect().center())
    assert _close(center, QPointF(120, 0), eps=0.1)   # 0.3 * 400 = 120


def test_port_move_updates_frac_and_undo_redo_restore_it():
    w = CanvasWindow()
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))
    orig_frac = port._port_frac
    before = QPointF(port.pos())
    port.setPos(port.pos().x() + 40, port.pos().y())
    w.push_undo_move([(port, before)])
    assert abs(port._port_frac[0] - orig_frac[0]) > 1e-6   # 옮긴 뒤엔 frac도 바뀜
    w.undo()
    assert abs(port._port_frac[0] - orig_frac[0]) < 1e-9
    w.redo()
    assert abs(port._port_frac[0] - orig_frac[0]) > 1e-6


def test_port_delete_updates_host_ports_list_and_undo_restores():
    w = CanvasWindow()
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))
    w._scene.clearSelection(); port.setSelected(True)
    w.delete_selection()
    assert port.scene() is None and port not in dev._ports
    w.undo()
    assert port.scene() is w._scene and port in dev._ports and port.parentItem() is dev


def test_host_delete_cascades_port_and_undo_restores():
    w = CanvasWindow()
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))
    w._scene.clearSelection(); dev.setSelected(True)
    w.delete_selection()
    assert dev.scene() is None and port.scene() is None
    assert port.parentItem() is dev   # Qt가 캐스케이드 제거 중엔 부모 링크를 안 끊음(실측)
    w.undo()
    assert dev.scene() is w._scene and port.scene() is w._scene
    assert port.parentItem() is dev


def test_shape_ports_includes_attached_port_and_connector_can_start_there():
    # [2026-08-04, 3차 수정] 포트의 접속점은 더 이상 호스트의 `_shape_ports`에 중복 노출되지
    # 않는다 — 포트 정중앙이 반드시 죽은 지대여야 하는데, 호스트가 그 자리(거리 0)를 접속점으로
    # 계속 들고 있으면 정중앙이 다시 살아난다(실사용 리포트: 깜빡임의 원인이기도 했다). 대신
    # 포트 자신이 (선택 여부 무관하게) 4변 접속점을 직접 제공하므로 그중 하나(E)에서 드래그한다.
    w = CanvasWindow(); w.grid_enabled = False
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    target = _mk_pen_rect(w, x=400, y=300, ww=100, hh=60)
    port = w._create_port_at("port_rect", QPointF(60, 0))
    port_center = port.mapToScene(port.rect().center())
    assert not any(_close(p, port_center, eps=0.01) for p, _n in _shape_ports(dev))
    port_edge, _n = _shape_ports(port)[1]   # N,E,S,W 순서 — 인덱스1=E

    w._scene.clearSelection(); w.set_tool("select")
    before = len([x for x in w._scene.items() if isinstance(x, _PolyArrowItem)])
    _qc_drag(w._view, port_edge, QPointF(450, 330))
    arrows = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    assert len(arrows) == before + 1
    # [실사용 버그 수정 2026-08-03] 커넥터는 호스트가 아니라 포트 자신에 바인딩돼야 한다 —
    # 그래야 포트를 나중에 옮겼을 때 커넥터가 (호스트의 고정된 옛 자리가 아니라) 포트를
    # 따라간다. 아래 test_connector_follows_port_when_port_moves가 그 동작 자체를 검증.
    assert arrows[-1]._bind_start is port


def test_connector_follows_port_when_port_moves():
    # [실사용 버그 수정 2026-08-03] 사용자 실조건 리포트: 포트를 옮기면 화살표가 포트를
    # 안 따라가고 장비 테두리의 옛 자리에 그대로 남았다 — 원인은 커넥터가 host에(고정
    # local_pt로) 바인딩됐기 때문. 포트 자신에 바인딩되면 포트가 움직인 뒤 reroute()가
    # 새 위치를 정확히 반영해야 한다.
    # [2026-08-04, 3차 수정] 포트 정중앙은 죽은 지대라 드래그 시작점을 포트의 E 변 접속점으로
    # 바꿨다(위 테스트와 동일 이유).
    w = CanvasWindow(); w.grid_enabled = False
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    _mk_pen_rect(w, x=400, y=300, ww=100, hh=60)
    port = w._create_port_at("port_rect", QPointF(60, 0))
    port_edge, _n = _shape_ports(port)[1]
    w._scene.clearSelection(); w.set_tool("select")
    _qc_drag(w._view, port_edge, QPointF(450, 330))
    arrow = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)][-1]
    assert _close(QPointF(arrow.mapToScene(arrow._pts[0])), port_edge, eps=1.0)

    port.setPos(port.pos().x() + 60, port.pos().y())   # 포트를 다른 자리로 이동
    arrow.reroute()
    new_edge, _n = _shape_ports(port)[1]
    assert not _close(new_edge, port_edge, eps=1.0)   # 실제로 옮겨졌는지 확인(전제)
    assert _close(QPointF(arrow.mapToScene(arrow._pts[0])), new_edge, eps=1.0), \
        "커넥터 시작점이 옮긴 포트를 따라가야 한다"


def test_port_participates_normally_in_hover_and_qc_systems():
    # [실사용 버그 수정 2026-08-04, 4차 — 최종 설계] 3차에서 포트 전용 "정중앙 죽은 지대"
    # 코드를 여러 곳에 심었으나, 실사용 중 포트 근처 호버가 여전히 호스트의 동서남북 미리보기를
    # 잘못 띄우는 새 버그가 나왔다(원인: `_draw_port_dots`가 쓰는 `_port_dot_target`은 포트를
    # 후보에서 뺐더니 그다음으로 가까운 호스트를 대신 골랐다). 실사용 결정으로 포트를 다시
    # "완전히 평범한 도형"으로 되돌리고(전용 예외 코드 전부 제거), 대신 "드래그는 항상
    # 화살표만"이라는 규칙을 도형 전체에 공통 적용해 포트가 원하는 동작을 특례 없이 얻는다
    # (아래 테스트가 그 규칙을 검증). 포트 정중앙이 `_port_dot_target`에서 안 잡히는 건 포트가
    # 호스트 테두리 위에 정확히 얹혀 있어 `_shape_interior_contains`(경계 포함)가 호스트도
    # "내부"로 판정하는 기존 로직의 자연스러운 부작용이지, 포트 전용 특례가 아니다.
    w = CanvasWindow(); w.grid_enabled = False
    _mk_pen_rect(w, x=0, y=0, ww=200, hh=120)
    port = w._create_port_at("port_circle", QPointF(0, 35))
    w._scene.clearSelection()   # 생성 직후 자동선택 상태를 벗어나 실사용 호버 시나리오로

    port_edge, _n = _shape_ports(port)[1]   # N,E,S,W 순서 — 인덱스1=E
    hp = w._view._hover_port_at(w._view.mapFromScene(port_edge))
    assert hp is not None
    sh, sp, _n2, is_discrete = hp
    assert sh is port and is_discrete
    assert _close(sp, port_edge, eps=0.01)


def test_port_trimmed_host_border_is_not_snappable_or_hoverable():
    # [실사용 버그 수정 2026-08-09] 포트 트림은 진짜 기하 분절이 아니라 배경색으로 덮어 그리는
    # 시각효과라(`_paint_port_cover_if_needed`, 2026-08-03 Qt 버그 우회) 히트/스냅 기하는 온전한
    # 사각형 그대로였다 — 그래서 포트 몸통 한가운데인데도 ⓐ 커서가 십자선(커넥터)으로 뜨고
    # ⓑ 화살표가 "화면에 그려지지도 않은" 호스트 테두리 조각에 붙었다(사용자 스크린샷 3회 보고).
    # 사용자 표현: "포트 안쪽까지 뒤쪽 네모 테두리 snap이 고려될 필요 없다".
    # 판정을 `build_trimmed_border_path`와 같은 소스(_host_outline_local_polygon/_port_edge_gap)
    # 로 통일해 "스냅되는 곳 == 선이 그려진 곳"을 맞춘다.
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    port = w._create_port_at("port_rect", QPointF(0, 260))
    w._scene.clearSelection()
    pc = port.mapToScene(port.rect().center())

    # ⓐ 트림된 구간(포트가 덮은 자리)은 호스트 테두리로 안 잡힌다.
    assert _nearest_border_visible(host, pc) is None
    # 원본 `_nearest_border`는 그대로여야 한다 — 포트 부착·드래그가 이걸 쓰기 때문
    # (`_attach_port_to_host`/`_snap_port_pos_to_host_border`). 트림을 반영하면 포트가
    # 자기가 만든 구간에서 밀려난다.
    assert _close(_nearest_border(host, pc)[0], pc, eps=0.01)

    # ⓑ 트림 안 된 정상 테두리는 계속 잡혀야 한다(과잉 차단 방지).
    normal_pt = QPointF(0, 100)
    hit = _nearest_border_visible(host, normal_pt)
    assert hit is not None and _close(hit[0], normal_pt, eps=0.01)

    # ⓒ 화살표 도구 스냅이 트림 구간에서 호스트에 붙지 않는다(포트 자신엔 붙어도 됨).
    w.set_tool("arrow")
    snap = w._view._border_snap_at(w._view.mapFromScene(pc))
    assert snap is None or snap[2] is not host

    # ⓓ 호버도 마찬가지 — 포트 몸통에서 호스트가 호버 대상이 되면 안 된다.
    w.set_tool("select")
    hp = w._view._hover_port_at(w._view.mapFromScene(pc))
    assert hp is None or hp[0] is not host


def test_qc_drag_never_spawns_device_click_still_does_port_and_normal_shape():
    # [실사용 결정 2026-08-04, 4차] "큐닷을 클릭하면 도형 복제, 드래그하면 화살표만"이라는
    # 규칙을 포트에 국한하지 않고 전 도형 공통으로 통일했다 — 포트도 이 규칙 하나로 원하는
    # 동작(드래그해도 장비 안 생김)을 특례 코드 없이 만족한다. 포트·일반 도형 둘 다 확인.
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=200, hh=120)
    port = w._create_port_at("port_circle", QPointF(0, 35))
    w._scene.clearSelection()

    for src in (port, host):
        # 드래그(빈 캔버스) — 새 도형 없음, 끝이 비어있는 화살표.
        n0 = len(w._scene.items())
        edge_pt = _shape_ports(src)[1][0]
        arrow = w._view._hp_create_arrow(src, edge_pt, QPointF(900, 900))
        assert len(w._scene.items()) == n0 + 1
        assert arrow._bind_end is None

        # 클릭(드래그 없음) — 도형 복제 + 화살표(포트든 일반 도형이든 동일).
        n1 = len(w._scene.items())
        dup, arrow2 = w._view._qc_create(src, "r", None)
        assert len(w._scene.items()) == n1 + 2   # 복제 도형 + 화살표
        assert arrow2._bind_start is src and arrow2._bind_end is dup


def test_build_trimmed_border_path_has_gap_at_port():
    dev = _RectItem(QRectF(0, 0, 200, 100))
    port = _RectItem(QRectF(0, 0, 18, 18))
    _attach_port_to_host(port, dev, QPointF(60, 0))
    path = build_trimmed_border_path(dev)
    # 포트 없는 변(우·하·좌)은 각 1세그먼트, 포트 걸친 위쪽 변만 2세그먼트 → 총 elementCount 10.
    assert path.elementCount() == 10


def test_build_trimmed_border_path_no_ports_is_unused_by_paint_but_still_correct():
    # 포트 없는 도형은 애초에 _ports가 비어 build_trimmed_border_path를 호출할 일이 없지만
    # (화면은 _paint_port_cover_if_needed 쪽 트릭을 씀), 함수 자체는 빈 _ports에도 안전해야
    # DXF export(_export_rect)가 무조건 안전하게 호출할 수 있다.
    dev = _RectItem(QRectF(0, 0, 200, 100))
    path = build_trimmed_border_path(dev)
    assert path.elementCount() == 8   # 4변 × (moveTo+lineTo), 끊김 없음


def test_ecad_roundtrip_preserves_ports_on_rect_and_triangle():
    w = CanvasWindow()
    dev = _mk_pen_rect(w, x=50, y=60, ww=200, hh=100)
    w._create_port_at("port_rect", QPointF(50 + 60, 60))
    tri = _SymbolItem("triangle", QRectF(0, 0, 180, 130))
    tri.setPen(w.make_pen()); tri.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    tri.setFlags(tri.GraphicsItemFlag.ItemIsSelectable | tri.GraphicsItemFlag.ItemIsMovable)
    tri.setPos(400, 60)
    w._scene.addItem(tri)
    tri_port = w._create_port_at("port_circle", QPointF(400 + 90, 60 + 130))
    tri_port_scene = tri_port.mapToScene(tri_port.rect().center())

    path = os.path.join(_TMP, "ports.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    n = load_document(w2._scene, path)
    assert n == 2   # 포트는 최상위 아이템이 아니므로(라벨과 동일 취급) 개수에 안 잡힘

    dev2 = next(it for it in w2._scene.items()
                if isinstance(it, _RectItem) and not hasattr(it, "_port_host"))
    assert len(dev2._ports) == 1
    p2 = dev2._ports[0]
    assert p2.parentItem() is dev2 and p2.scene() is w2._scene
    assert _close(p2.mapToScene(p2.rect().center()), QPointF(110, 60), eps=0.01)

    tri2 = next(it for it in w2._scene.items()
                if isinstance(it, _SymbolItem) and it._kind == "triangle")
    assert len(tri2._ports) == 1
    tp2 = tri2._ports[0]
    assert _close(tp2.mapToScene(tp2.rect().center()), tri_port_scene, eps=0.01)


def test_dxf_export_trims_border_segments_with_ports():
    w = CanvasWindow()
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    w._create_port_at("port_rect", QPointF(60, 0))
    plain = _mk_pen_rect(w, x=400, y=0, ww=100, hh=60)   # 포트 없는 회귀 확인용

    out = os.path.join(_TMP, "trim.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    msp = doc.modelspace()
    lines = list(msp.query("LINE"))
    polys = list(msp.query("LWPOLYLINE"))
    # dev: 끊긴 위쪽 변 2개(LINE) + 나머지 3변(LINE) = 5 LINE. plain: 닫힌 4점 LWPOLYLINE 1개.
    # port_rect 자신도 작은 닫힌 LWPOLYLINE 1개로 나감(총 LWPOLYLINE 2개).
    assert len(lines) == 5
    assert len(polys) == 2 and all(len(p) == 4 for p in polys)


# ---- [실사용 버그 수정 2026-08-03] 포트 실조건 테스트에서 발견된 3건 ---------------------

def test_shift_corner_resize_keeps_aspect_ratio():
    # Shift 없이 코너를 끌면 자유 변형(기존 동작), Shift를 누르면 리사이즈 시작 시점의
    # 종횡비를 유지해야 한다 — 포트를 포함한 모든 rect 기반 도형에 공통.
    free = _RectItem(QRectF(0, 0, 100, 50))
    free._begin_box_geom()
    free._box_resize = ("corner", 2)   # BR, 대각 고정점=TL
    free._apply_box_resize(QPointF(100, 100), shift=False)
    assert abs(free.rect().width() - 100) < 1e-6 and abs(free.rect().height() - 100) < 1e-6

    locked = _RectItem(QRectF(0, 0, 100, 50))   # 종횡비 2:1
    locked._begin_box_geom()
    locked._box_resize = ("corner", 2)
    locked._apply_box_resize(QPointF(100, 100), shift=True)
    r = locked.rect()
    assert abs(r.width() / r.height() - 2.0) < 1e-6

    port = _RectItem(QRectF(0, 0, 18, 36))   # 종횡비 1:2 — 포트도 동일하게 적용되는지
    port._begin_box_geom()
    port._box_resize = ("corner", 2)
    port._apply_box_resize(QPointF(50, 50), shift=True)
    rp = port.rect()
    assert abs(rp.width() / rp.height() - 0.5) < 1e-6


def test_port_resize_ignores_grid_snap():
    # [실사용 요청 2026-08-03 2차] 포트는 보통 그리드 간격(20)과 비슷하거나 작아, 리사이즈가
    # 그리드에 맞춰지면 한 칸 단위로만 뛰어 미세조정이 안 됐다 — 포트만 그리드 스냅 제외.
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow(); w.grid_enabled = True
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))
    off_grid = QPointF(37.3, 41.7)   # 20의 배수가 아닌 임의 좌표
    assert port._grid_snap_local(off_grid) == off_grid   # 통과(스냅 없음)

    # 대조군: 포트가 아닌 일반 도형은 여전히 그리드에 맞는다(회귀 방지).
    assert dev._grid_snap_local(off_grid) != off_grid
    snapped = dev._grid_snap_local(off_grid)
    assert abs(snapped.x() % _GRID_SPACING) < 1e-6 and abs(snapped.y() % _GRID_SPACING) < 1e-6


def test_port_corner_resize_defaults_to_aspect_lock_shift_frees_it():
    # [실사용 요청 2026-08-03 2차] 포트는 일반 도형과 기본값이 반대다 — 꼭짓점 핸들이
    # Shift 없이도 기본으로 비율을 유지하고(정사각형 포트가 늘 정사각형으로), Shift를
    # 누르면 오히려 잠금을 풀어 자유 변형한다. 변 핸들은 여전히 항상 자유(축별 개별 조정).
    w = CanvasWindow(); w.grid_enabled = False
    dev = _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))   # 12x12 정사각형 시작
    assert abs(port.rect().width() - port.rect().height()) < 1e-6

    port._begin_box_geom()
    port._box_resize = ("corner", 2)
    port._apply_box_resize(port.mapFromScene(QPointF(port.pos().x() + 18, port.pos().y() + 60)),
                            shift=False)   # Shift 없이 세로만 길게 끌어도
    r = port.rect()
    assert abs(r.width() - r.height()) < 1e-6, "포트는 Shift 없이도 비율유지가 기본이어야 한다"

    port2 = w._create_port_at("port_rect", QPointF(140, 0))
    port2._begin_box_geom()
    port2._box_resize = ("corner", 2)
    port2._apply_box_resize(
        port2.mapFromScene(QPointF(port2.pos().x() + 18, port2.pos().y() + 60)), shift=True)
    r2 = port2.rect()
    assert abs(r2.width() - 18) < 1e-6 and abs(r2.height() - 60) < 1e-6, \
        "포트는 Shift를 누르면 비율잠금이 풀려야 한다"

    # 변 핸들은 포트든 아니든 항상 자유(축별 개별 조정) — 회귀 방지.
    port3 = w._create_port_at("port_rect", QPointF(180, 0))
    port3._begin_box_geom()
    port3._box_resize = ("edge", "b")
    port3._apply_box_resize(
        port3.mapFromScene(QPointF(port3.pos().x(), port3.pos().y() + 60)), shift=False)
    r3 = port3.rect()
    assert abs(r3.width() - 12) < 1e-6 and abs(r3.height() - 60) < 1e-6


def test_selected_port_hover_marker_does_not_duplicate_on_itself():
    # [실사용 버그 수정, 2026-08-04 3차 갱신] 원래는 "호스트가 노출한 포트-중앙 접속점"과
    # "선택된 포트 자신의 리사이즈 핸들"이 겹쳐 핸들이 뭉쳐 보이던 버그를 막는 테스트였다.
    # 3차 수정으로 호스트가 더 이상 포트 위치를 접속점으로 중복 노출하지 않으므로(포트 정중앙은
    # 항상 죽은 지대) 원래 충돌 자체가 구조적으로 사라졌다 — 이제 포트 자신의 4변 접속점이 그
    # 역할을 하므로, 한 포트를 선택해도 다른(미선택) 포트의 호버가 정상 작동하는지로 갱신한다.
    # [2026-08-04 4차] E(오른쪽) 점은 호스트의 상단 테두리 위이기도 해(포트가 그 위에 얹혀
    # 있으므로) 포트 선택 후에도 Pass 2 연속 폴백이 "호스트 테두리의 한 점"으로 다시 주울 수
    # 있다 — 이건 포트와 무관한 호스트 자체의 연속 호버 기능이라 회귀가 아니다. 포트가 자기
    # 소유인 게 명확한 N(바깥쪽) 점으로 검증한다.
    w = CanvasWindow(); w.set_tool("select")
    _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))
    port2 = w._create_port_at("port_circle", QPointF(140, 0))
    w._scene.clearSelection()

    n1, _n = _shape_ports(port)[0]
    assert w._view._hover_port_at(w._view.mapFromScene(n1)) is not None   # 미선택 상태에선 정상 노출

    port.setSelected(True)
    # 선택된 도형은 _hover_port_at 대상에서 제외(_connect_port_at가 대신 처리) — 회귀 없음.
    assert w._view._hover_port_at(w._view.mapFromScene(n1)) is None
    n2, _n = _shape_ports(port2)[0]
    assert w._view._hover_port_at(w._view.mapFromScene(n2)) is not None   # 다른(미선택) 포트는 정상


def _mk_moved_rect(w, x, y, ww, hh):
    # [2026-08-09] _mk_pen_rect는 좌표를 rect() 자체에 굽는다(pos()는 (0,0) 유지) — 실제 사용자
    # 도형은 드래그 이동 시 setPos()가 바뀐다. 포트의 "호스트 기준 로컬좌표 vs 씬좌표" 버그는
    # 후자가 아니면 재현되지 않으므로(pos()==(0,0)이면 로컬==씬이라 우연히 안 걸림), 이 헬퍼로
    # 명시적으로 setPos해 실제 시나리오를 재현한다.
    it = _RectItem(QRectF(0, 0, ww, hh))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    it.setPos(QPointF(x, y))
    w._scene.addItem(it)
    return it


def test_qc_create_click_duplicate_on_attached_port_lands_near_host():
    # [실사용 버그 수정 2026-08-09] 호스트가 setPos()로 씬 원점에서 먼 곳(500,500)에 있을 때,
    # 부착된 포트의 큐닷을 "클릭"(cursor_scene=None)하면 예전엔 dup.setPos(src.pos()+델타)가
    # src.pos()(호스트 기준 로컬좌표, 원점 근처인 (54,-6) 수준)를 씬좌표처럼 오인해 dup이 씬
    # 원점 근처로 튀었다(사용자 스크린샷 — 포트 옆이 아니라 화면 밖 엉뚱한 자리에 화살표로만
    # 이어짐). _mk_pen_rect는 좌표를 rect()에 굽고 pos()는 (0,0)이라 이 버그가 재현되지
    # 않으므로(로컬==씬이 우연히 성립) 반드시 setPos 기반 헬퍼를 쓴다.
    w = CanvasWindow(); w.set_tool("select")
    _mk_moved_rect(w, 500, 500, 200, 100)
    port = w._create_port_at("port_rect", QPointF(560, 500))   # 상단 변 위
    side = "t"
    dup, arrow = w._view._qc_create(port, side, None)
    # 호스트·포트가 (500,500) 근방이므로 정상이라면 dup도 그 근방이어야 한다(원점 근처면 버그).
    host_center = QPointF(600, 550)
    assert QLineF(dup.sceneBoundingRect().center(), host_center).length() < 300, (
        "복제 포트가 호스트에서 너무 멀리 떨어짐(원점쪽으로 튀는 옛 버그)",
        dup.sceneBoundingRect().center())
    assert QLineF(dup.sceneBoundingRect().center(), QPointF(0, 0)).length() > 300


def test_alt_press_on_unselected_port_bypasses_hover_port_hijack_and_duplicates():
    # [실사용 버그 수정 2026-08-09] 미선택 포트를 Alt+드래그하면 예전엔 `_hover_port_at`이
    # Alt 여부와 무관하게 먼저 press를 가로채 "화살표 뽑기"로 귀결됐다(_maybe_alt_drag_copy에
    # 도달 못 함 — 사용자 스크린샷 재현). Alt가 이 큐닷 체계보다 우선해야 한다.
    w = CanvasWindow(); w.show(); w.set_tool("select")
    _mk_pen_rect(w, x=0, y=0, ww=200, hh=100)
    port = w._create_port_at("port_rect", QPointF(60, 0))
    w._scene.clearSelection()
    n0 = len(w._scene.items())
    port_scene_pt = port.mapToScene(port.rect().center())
    ev = _mods_event("press", w._view, port_scene_pt, Qt.KeyboardModifier.AltModifier)
    w._view.mousePressEvent(ev)
    assert w._view._hp_dragging is False, "Alt+press가 여전히 화살표-뽑기 경로로 새고 있음"
    assert len(w._scene.items()) == n0 + 1, "Alt+press가 포트를 복제하지 않음"


def test_alt_drag_copy_on_selected_port_stays_free_until_release_then_reattaches():
    # [2026-08-09 2차, 실사용 재현] press 시점에 곧바로 setParentItem으로 재부착했더니, 곧이어
    # 실행되는 super().mousePressEvent()의 Qt 내부 드래그-그랩과 충돌해 실제 드래그가 먹지
    # 않는 버그가 발견됐다(합성 press+move로 이동량 0 확인). 그래서 지금은 press 시점엔
    # 최상위(부모 없음) 클론으로만 두고(_pending_port_reattach에 등록), 드래그가 끝나는
    # mouseReleaseEvent에서 최종 위치 근방 호스트를 찾아 그제서야 부착한다.
    w = CanvasWindow(); w.set_tool("select")
    host = _mk_moved_rect(w, 500, 500, 200, 100)   # setPos 기반 — 위 헬퍼 주석 참조
    port = w._create_port_at("port_rect", QPointF(560, 500))
    port.setSelected(True)
    n0 = len(w._scene.items())
    press_pt = port.mapToScene(port.rect().center())
    ev = _mods_event("press", w._view, press_pt, Qt.KeyboardModifier.AltModifier)
    w._view._maybe_alt_drag_copy(ev)
    assert len(w._scene.items()) == n0 + 1
    clones = [x for x in w._scene.selectedItems() if x is not port]
    assert len(clones) == 1, clones
    clone = clones[0]
    # press 직후: 아직 최상위(부모 없음)인 평범한 클론이어야 Qt 기본 드래그가 정상 동작한다.
    assert clone.parentItem() is None
    assert clone in w._view._pending_port_reattach
    assert _close(clone.scenePos(), port.scenePos())

    # release(드래그 없이 제자리) — 이제 최종 위치 근방에서 호스트를 찾아 부착해야 한다.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    vp = QPointF(w._view.mapFromScene(press_pt))
    release_ev = QMouseEvent(QEvent.Type.MouseButtonRelease, vp, vp,
                              Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                              Qt.KeyboardModifier.AltModifier)
    w._view.mouseReleaseEvent(release_ev)
    assert w._view._pending_port_reattach == []
    assert clone.parentItem() is host
    assert getattr(clone, "_port_host", None) is host
    assert _close(clone.scenePos() + QPointF(clone.rect().width() / 2, clone.rect().height() / 2),
                  port.scenePos() + QPointF(port.rect().width() / 2, port.rect().height() / 2))



def test_true_segmented_border_survives_scene_render_and_grab():
    # [§8 항목17 게이트 2026-08-09] TRIM/EXTEND 계획 전체가 이 성질에 걸려 있다.
    #
    # 2026-08-03 항목12(포트 trim) 때, 호스트 paint()에서 테두리를 진짜로 끊어 그리면
    # QGraphicsScene.render()/view.grab()에서 간격이 사라져(Qt 자식 아이템이 있을 때만)
    # 배경색 덮어그리기로 우회했었다(_paint_port_cover_if_needed docstring 참조).
    # 라벨은 _LabelMixin이 setParentItem으로 다는 '자식'이라 라벨 있는 도형은 전부 그
    # 조건이고, scene.render()는 PDF 내보내기·선택영역 복사·미니맵이 쓴다 — 재발하면
    # "화면은 잘렸는데 PDF는 안 잘림"이 된다.
    #
    # 계획 확정 스파이크에서 Qt 6.10/PyQt 6.10은 전 조건 통과했다. 그 성질이 유지되는지
    # (Qt 업그레이드 등으로 되돌아가지 않는지) 여기서 지킨다. _RectItem.paint는 이 테스트
    # 안에서만 바꿔치기하고 finally로 반드시 되돌린다.
    from PyQt6.QtGui import QImage, QPainter, QPen
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

    R = QRectF(0, 0, 200, 120)
    GAP_Y0, GAP_Y1 = 40.0, 80.0            # 오른쪽 변에서 비울 구간(로컬 y)

    def segmented_paint(self, painter, option, widget=None):
        r = self.rect()
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(self.brush())
            painter.drawRect(r)            # 채움은 닫힌 영역 그대로
        path = QPainterPath()
        path.moveTo(r.topRight()); path.lineTo(r.topLeft())
        path.lineTo(r.bottomLeft()); path.lineTo(r.bottomRight())
        path.lineTo(QPointF(r.right(), GAP_Y1))
        path.moveTo(QPointF(r.right(), GAP_Y0))    # 간격 건너뜀
        path.lineTo(r.topRight())
        painter.setPen(QPen(self.pen())); painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _build(with_label, with_fill, selected):
        scene = QGraphicsScene()
        scene.setSceneRect(-20, -20, 240, 160)
        scene.setBackgroundBrush(QColor("white"))
        it = _RectItem(QRectF(R))
        it.setPen(QPen(QColor("black"), 3))
        it.setBrush(QBrush(QColor("#cfe8ff")) if with_fill else QBrush(Qt.BrushStyle.NoBrush))
        scene.addItem(it)
        if with_label:
            it.ensure_label().setPlainText("EQUIP")   # setParentItem — Qt 자식 생성
        if selected:
            it.setFlag(it.GraphicsItemFlag.ItemIsSelectable, True); it.setSelected(True)
        return scene

    def _darkest(img, px, py):
        d = 255
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = QColor(img.pixel(px + dx, py + dy))
                d = min(d, (c.red() + c.green() + c.blue()) // 3)
        return d

    orig_paint = _RectItem.paint
    _RectItem.paint = segmented_paint
    try:
        for with_label in (False, True):
            for with_fill in (False, True):
                for selected in (False, True):
                    cond = f"label={with_label} fill={with_fill} sel={selected}"
                    # ⓐ scene.render() — PDF 내보내기·선택영역 복사·미니맵이 쓰는 경로
                    img = QImage(240, 160, QImage.Format.Format_RGB32)
                    img.fill(QColor("white"))
                    p = QPainter(img)
                    _build(with_label, with_fill, selected).render(
                        p, QRectF(0, 0, 240, 160), QRectF(-20, -20, 240, 160))
                    p.end()
                    # 씬(200,60)=간격 한가운데 → 이미지(220,80). 테두리(검정 3px)가 남았으면
                    # 평균이 100 밑으로 떨어진다. 채움색(#cfe8ff)만 남는 건 정상.
                    assert _darkest(img, 220, 80) > 150, f"scene.render 간격 소실: {cond}"

                    # ⓑ view.grab() — tools/screenshot.py가 쓰는 경로
                    view = QGraphicsView(_build(with_label, with_fill, selected))
                    view.setFrameStyle(0); view.resize(240, 160)
                    view.setSceneRect(QRectF(-20, -20, 240, 160))
                    view.fitInView(QRectF(-20, -20, 240, 160),
                                   Qt.AspectRatioMode.IgnoreAspectRatio)
                    view.show()
                    QApplication.processEvents()
                    gimg = view.grab().toImage()
                    sx, sy = gimg.width() / 240.0, gimg.height() / 160.0
                    assert _darkest(gimg, int(220 * sx), int(80 * sy)) > 150, \
                        f"view.grab 간격 소실: {cond}"
    finally:
        _RectItem.paint = orig_paint
