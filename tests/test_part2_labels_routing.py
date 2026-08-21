"""커넥터 라벨·PDF 내보내기·라우팅 프리뷰·장애물 회피

tests/test_easycad.py 2026-08-02 분할분. 실행: python tests/test_easycad.py (전체) 또는 pytest test_part2_labels_routing.py.
"""
from _shared import *  # noqa: F401,F403


def test_shape_swap_preserves_and_rebinds():
    # [M4-3] 도형 교체 — 종류 변환, 크기·라벨 유지, 연결 화살표 재바인딩, 단일 undo.
    w = CanvasWindow()
    r = _mk_pen_rect(w, x=0, y=0, ww=80, hh=50)
    r.ensure_label().setPlainText("Box"); r._sync_label()
    arr = _PolyArrowItem(QColor("#ff111111"), 3, True)
    arr.set_points(QPointF(200, 25), QPointF(80, 25))
    arr.setFlags(arr.GraphicsItemFlag.ItemIsSelectable | arr.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(arr)
    arr.set_bound(1, r, r.mapFromScene(QPointF(80, 25)))
    d0 = len(w._undo)
    w._swap_shape(r, "ellipse")
    ells = [x for x in w._scene.items() if isinstance(x, _EllipseItem)]
    assert len(ells) == 1
    new = ells[0]
    assert r.scene() is None and new.scene() is not None
    assert abs(new.rect().width() - 80) < 1e-6 and abs(new.rect().height() - 50) < 1e-6
    assert new.has_label() and new._label.toPlainText() == "Box"
    assert arr._bind_end is new                  # 화살표가 new로 재바인딩
    assert len(w._undo) == d0 + 1                # 단일 undo 엔트리
    w.undo()                                     # rect 복귀 + 화살표 재바인딩 원복
    assert new.scene() is None and r.scene() is not None
    assert arr._bind_end is r
    r.setSelected(True); w._swap_shape(r, "sym:decision")
    syms = [x for x in w._scene.items() if isinstance(x, _SymbolItem)]
    assert len(syms) == 1 and syms[0]._kind == "decision"
    labels = [a.text() for a in w._build_swap_menu().actions() if not a.isSeparator()]
    assert labels[:2] == ["사각형", "원"] and "판단" in labels


def test_swap_menu_hides_symbols_not_in_palette():
    # [실사용 피드백 2026-08-21] `_build_swap_menu`가 백엔드 _SYMBOL_KINDS 전체(19종)를
    # 나열해 2026-08-04에 팔레트에서 뺀 옛 흐름도/안테나 심볼까지 유령처럼 노출되던 버그.
    # 팔레트 기본도형 그리드와 정확히 같은 8종(사각형·원 + 심볼 6종)만 남아야 한다.
    w = CanvasWindow()
    labels = [a.text() for a in w._build_swap_menu().actions() if not a.isSeparator()]
    assert labels == ["사각형", "원", "삼각형", "판단", "시작/끝", "입출력", "준비", "저장소"]
    assert "문서" not in labels and "MW 파라볼릭(측면)" not in labels and "번개 표식" not in labels


def test_arrow_endpoint_drag_onto_line_no_crash():
    # [M4-2b regression] 화살표 끝점을 다른 선 근처로 드래그하면 _border_snap_at이 shape=None을
    # 돌려준다 → 예외 없이 기하 스냅만(바인딩 없음). 옛 크래시: NoneType.mapFromScene.
    w = CanvasWindow()
    ln = _LineItem(QLineF(100, 200, 400, 200)); ln.setPen(w.make_pen())
    ln.setFlags(ln.GraphicsItemFlag.ItemIsSelectable | ln.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ln)
    # 곡선 화살표(_ArrowItem) 끝점을 선 위(250,200)로 드래그.
    arr = _ArrowItem(QColor("#111111"), 2, True)
    arr.set_points(QPointF(100, 100), QPointF(250, 120))
    arr.setFlags(arr.GraphicsItemFlag.ItemIsSelectable | arr.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(arr)
    arr._move_endpoint_with_snap(1, arr.mapFromScene(QPointF(250, 200)))   # 예외 없어야
    assert arr._bind2 is None                              # 선(shape=None)엔 바인딩 없음
    assert abs(arr.mapToScene(arr._p2).y() - 200) < 2      # 끝점은 선 위로 기하 스냅
    # 직선화살표(_PolyArrowItem)도 동일.
    sar = _PolyArrowItem(QColor("#111111"), 2, True)
    sar.set_points(QPointF(100, 300), QPointF(250, 320))
    sar.setFlags(sar.GraphicsItemFlag.ItemIsSelectable | sar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sar)
    sar._move_endpoint_with_snap(len(sar._pts) - 1, sar.mapFromScene(QPointF(250, 200)))
    assert sar._bind_end is None




def test_qc_drag_absorbs_onto_shape():
    # [M4-2 fix] 드래그 끝점이 다른 도형 '내부'면 테두리 정밀 조준 없이 그 도형에 흡수·바인딩.
    w = CanvasWindow(); v = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=80, hh=50); r.setSelected(True)
    tgt = _mk_pen_rect(w, x=400, y=-50, ww=160, hh=120)   # 큰 타깃
    center = tgt.mapToScene(tgt.rect().center())          # 한가운데(테두리서 멀다)
    arr = v._qc_create(r, "r", center)                    # 도형 한가운데에 드롭
    assert isinstance(arr, _PolyArrowItem)
    assert arr._bind_start is r and arr._bind_end is tgt  # 시작=src, 끝=흡수된 타깃




def test_swap_to_asymmetric_keeps_arrow_on_outline():
    # [M4-3 fix] 비대칭 도형(평행사변형)으로 교체 시 화살표 끝점이 옛 테두리 좌표에 남아 뜨지 않고
    # new 실제 외곽선에 재투영된다(옛 버그: 원·심볼로 바꾸면 끝점이 도형에서 떨어짐).
    w = CanvasWindow()
    r = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)
    arr = _PolyArrowItem(QColor("#111111"), 3, True)
    arr.set_points(QPointF(200, 30), QPointF(100, 30))    # 끝점 = rect 우변 중점
    arr.setFlags(arr.GraphicsItemFlag.ItemIsSelectable | arr.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(arr)
    arr.set_bound(1, r, r.mapFromScene(QPointF(100, 30)))
    r.setSelected(True)
    w._swap_shape(r, "sym:data")                          # 평행사변형(우변 슬랜트)
    new = [x for x in w._scene.items() if isinstance(x, _SymbolItem)][0]
    assert arr._bind_end is new
    ep = arr.mapToScene(arr._pts[-1])
    q, _n = _nearest_border(new, ep)
    gap = ((ep.x() - q.x()) ** 2 + (ep.y() - q.y()) ** 2) ** 0.5
    assert gap < 1.0, gap                                 # 끝점이 new 외곽선 위(뜨지 않음)




def test_selected_shape_interior_is_hit():
    # [M4-4 ⓓ → 2026-08-03 실사용 지적으로 미선택까지 확장] select 도구에선 속 빈 도형도
    # 선택 여부와 무관하게 내부 빈공간이 히트 → 가는 테두리를 조준하지 않고 안쪽 아무 데나
    # 클릭·끌어서 선택·이동(Lucid/FigJam). 그리기 도구가 무장된 동안만 내부가 통과된다
    # (test_interior_hit_off_while_drawing_tool_armed 참조).
    w = CanvasWindow(); w.set_tool("select")
    r = _mk_pen_rect(w, x=0, y=0, ww=200, hh=120)
    inner = r.rect().center()
    assert r.shape().contains(inner)          # 선택 전에도 이동/선택 히트
    r.setSelected(True)
    assert r.shape().contains(inner)          # 선택 후에도 그대로




def test_interior_hit_off_while_drawing_tool_armed():
    # [M4-4 ⓓ] 그리기 도구가 무장된 동안은 내부 히트를 끈다 — 뷰의 _is_empty_area가 shape()로
    # 판정하므로, 켜 두면 '도형 안에서 새 화살표·네모 그리기'(기존 설계)가 막힌다.
    w = CanvasWindow(); w.set_tool("select")
    r = _mk_pen_rect(w, x=0, y=0, ww=200, hh=120); r.setSelected(True)
    inner = r.rect().center()
    assert r.shape().contains(inner)
    for tool in ("rect", "ellipse", "arrow", "sarrow", "pen", "text"):
        w.set_tool(tool)
        assert not r.shape().contains(inner), tool
    w.set_tool("select")
    assert r.shape().contains(inner)




def test_interior_hit_follows_real_outline():
    # [M4-4 ⓓ] 내부 히트 영역은 외접 박스가 아니라 '실제 외곽선 안쪽' — 원은 곡선, 마름모는
    # 마름모. (핸들 영역이 섞이지 않게 _interior_path를 직접 본다.)
    from PyQt6.QtGui import QPen
    w = CanvasWindow()
    el = _EllipseItem(QRectF(0, 0, 200, 100))
    el.setPen(QPen(QColor("#111111"), 2.0)); el.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    w._scene.addItem(el)
    ip = el._interior_path()
    assert ip.contains(QPointF(100, 50)) and not ip.contains(QPointF(2, 2))   # 모서리는 타원 밖

    sym = _SymbolItem("decision", QRectF(0, 0, 200, 120))
    sym.setPen(QPen(QColor("#111111"), 2.0)); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    w._scene.addItem(sym)
    sp = sym._interior_path()
    assert sp.contains(QPointF(100, 60)) and not sp.contains(QPointF(4, 4))   # 마름모 밖

    # 채움이 있는 도형은 이미 전체가 히트라 얹지 않는다(중복 방지).
    el.setBrush(QBrush(QColor("#ffcc00")))
    assert el._interior_path() is None




def test_pdf_export():
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 120, 60)
    r2 = _mk_rect(w._scene, w.make_pen(), 300, 0, 120, 60)
    for pg in ("A4", "A1"):
        p = os.path.join(_TMP, f"full_{pg}.pdf")
        assert export_pdf(w._scene, p, page=pg)
        data = open(p, "rb").read()
        assert data[:5] == b"%PDF-" and b"/Page" in data
    w._scene.clearSelection(); r2.setSelected(True)
    assert export_pdf(w._scene, os.path.join(_TMP, "sel.pdf"), selection_only=True)
    assert _selection_rect(w._scene).width() < w._scene.itemsBoundingRect().width()
    w._scene.clearSelection()
    assert export_pdf(w._scene, os.path.join(_TMP, "empty.pdf"), selection_only=True) is False




def test_document_roundtrip():
    from PyQt6.QtWidgets import QGraphicsScene

    def pen(c="#ffff0000", wd=6):
        from PyQt6.QtGui import QPen
        p = QPen(QColor(c)); p.setWidthF(wd); return p

    sc = QGraphicsScene()
    r = _mk_rect(sc, pen(), 0, 0, 120, 60)
    r.setPos(QPointF(10, 20)); r.setRotation(15); r.setTransformOriginPoint(QPointF(60, 30)); r.setScale(1.5)
    e = _EllipseItem(QRectF(0, 0, 80, 80)); e.setPen(pen("#ff0000ff", 4)); e.setBrush(QBrush(Qt.BrushStyle.NoBrush)); e.setPos(QPointF(200, 0)); sc.addItem(e)
    ln = _LineItem(QLineF(0, 0, 100, 50)); ln.setPen(pen("#ff333333", 3)); sc.addItem(ln)
    pp = QPainterPath(QPointF(0, 0)); pp.lineTo(30, 10); pp.cubicTo(40, 40, 60, 40, 80, 10)
    pa = _PathItem(pp); pa.setPen(pen("#ff00aaff", 5)); pa.setPos(QPointF(0, 300)); sc.addItem(pa)
    ar = _ArrowItem(QColor("#ffff9500"), 6, True); ar.set_points(QPointF(120, 30), QPointF(300, 60)); ar._ctrl1 = QPointF(180, -20); ar._ctrl2 = QPointF(260, 120); sc.addItem(ar)
    tx = _TextItem(QColor("#ff000000")); tx.apply_font_size(20); tx.setPlainText("흐름 A\n둘째"); tx.set_bg(QColor(0, 0, 0, 150)); tx.setPos(QPointF(400, 200)); sc.addItem(tx)
    bd = _BadgeItem(7, QColor("#ffff3b30")); bd.setPos(QPointF(500, 500)); bd.setScale(2.0); sc.addItem(bd)

    before = [item_to_dict(it) for it in reversed(sc.items())]
    path = os.path.join(_TMP, "roundtrip.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 7
    after = [item_to_dict(it) for it in reversed(sc2.items())]

    def norm(d):
        out = {}
        for k, v in d.items():
            if isinstance(v, float):
                out[k] = round(v, 4)
            elif isinstance(v, list):
                out[k] = [round(x, 4) if isinstance(x, (int, float)) else x for x in v]
            else:
                out[k] = v
        return out

    for b, a in zip(before, after):
        assert norm(b) == norm(a), (b.get("type"), norm(b), norm(a))




def test_persistent_connection():
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    ar = _ArrowItem(QColor("#ffff0000"), 6, True)
    # 고정 부착점: 우측 테두리 (100,30)에 tip 고정, 시작은 자유(500,30)
    ar.set_points(QPointF(500, 30), QPointF(100, 30))
    ar.set_bound(1, r, QPointF(100, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)

    ar.reroute(pin_pred=lambda i: True)
    assert _close(ar.mapToScene(ar._p2), QPointF(100, 30))     # 고정점에 붙음

    r.setPos(QPointF(200, 0)); w._on_scene_changed(None)
    assert _close(ar.mapToScene(ar._p2), QPointF(300, 30))     # 도형 따라 이동(상대점 유지)

    # 반대편(far side) 부착 — 최근접이 아니라 '떨군 자리'를 지킨다(버그 수정 검증)
    r.setPos(QPointF(0, 0))
    ar.set_bound(1, r, QPointF(0, 30))    # 좌측 테두리에 고정
    ar.reroute(pin_pred=lambda i: True)
    assert _close(ar.mapToScene(ar._p2), QPointF(0, 30)), "far-side attach must hold"

    # 곡선 보존: 수동 제어점이 리라우트(도형 무이동)로 사라지지 않음
    ar.set_bound(1, r, QPointF(100, 30)); ar.reroute(pin_pred=lambda i: True)
    ar._ctrl1 = QPointF(200, -50); ar._ctrl2 = QPointF(150, 80)
    ar.reroute(pin_pred=lambda i: True)   # 도형 안 움직였으니 곡선 그대로여야
    assert ar._ctrl1 == QPointF(200, -50) and ar._ctrl2 == QPointF(150, 80), "curve preserved"

    # 강체/늘림 규칙
    r.setSelected(True); ar.setSelected(True)
    assert w._make_pin_pred(ar)(1) is False                    # 둘 다 선택 = 강체
    r.setSelected(False)
    assert w._make_pin_pred(ar)(1) is True                     # 도형만 제자리 = 늘림

    # 왕복: 바인딩 + 고정점 재연결
    path = os.path.join(_TMP, "conn.ecad")
    save_document(w._scene, path)
    from PyQt6.QtWidgets import QGraphicsScene
    sc2 = QGraphicsScene()
    load_document(sc2, path)
    a2 = [it for it in sc2.items() if isinstance(it, _ArrowItem)][0]
    r2 = [it for it in sc2.items() if isinstance(it, _RectItem)][0]
    assert a2._bound(1) is r2 and a2._bound(0) is None
    assert a2._bind_pt(1) == QPointF(100, 30)




def test_view_controls():
    w = CanvasWindow(); w.show()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    vpos = w._view.mapFromScene(QPointF(100, 30))   # 우측 테두리 근처

    # o-snap 토글: 켜짐이면 스냅, 꺼짐이면 None
    w.snap_enabled = True
    assert w._view._border_snap_at(vpos) is not None
    w.snap_enabled = False
    assert w._view._border_snap_at(vpos) is None
    w.snap_enabled = True

    # 기준 zoom(100%) 복귀
    w._view.scale(2.5, 2.5)
    assert abs(w._view.transform().m11() - 2.5) < 1e-6
    w._zoom_reset()
    assert abs(w._view.transform().m11() - 1.0) < 1e-6

    # 전체 맞춤 — 크래시 없이 변환 적용
    w._zoom_fit()
    assert w._view.transform().m11() > 0




def test_zoom_fit_idempotent():
    # ⚠ [버그 수정 회귀 2026-08-01] 도형 boundingRect()의 핸들/히트 패딩은 현재 뷰 줌으로 나눠
    # 씬 단위로 환산된다(_view_zoom_factor) — 리셋 없이 그대로 itemsBoundingRect()를 재면 그
    # 측정값 자체가 직전 줌에 의존해, 전체맞춤을 눌러도 결과가 계속 바뀌었다(사용자 재현 보고).
    # 반복 호출은 항상 같은 결과여야 한다(멱등) — 극단적 줌에서 시작해도 마찬가지.
    w = CanvasWindow(); w.resize(900, 700); w.show()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    w._view.scale(7.0, 7.0)
    w._zoom_fit()
    t1 = w._view.transform()
    w._zoom_fit()
    t2 = w._view.transform()
    assert abs(t1.m11() - t2.m11()) < 1e-9
    assert abs(t1.dx() - t2.dx()) < 1e-6
    assert abs(t1.dy() - t2.dy()) < 1e-6




def test_direction_rubber_band():
    # 방향 감지 러버밴드: 왼→오=window(완전포함), 오→왼=crossing(걸침), Shift=추가선택.
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    view = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)     # 상자에 완전 포함될 도형
    b = _mk_rect(w._scene, w.make_pen(), 450, 0, 100, 60)   # 상자 우측 경계를 걸치는 도형
    tl = view.mapFromScene(QPointF(-10, -10))               # 상자 좌상단(view 좌표)
    br = view.mapFromScene(QPointF(500, 300))               # 상자 우하단(view 좌표)

    # window(왼→오): 완전 포함만 → a만
    view._rb_origin, view._rb_current = tl, br
    assert view._rb_is_window() is True
    view._apply_rubber_selection()
    assert set(w._scene.selectedItems()) == {a}, set(w._scene.selectedItems())

    # crossing(오→왼): 걸치기만 해도 → a, b 둘 다
    view._rb_origin, view._rb_current = br, tl
    assert view._rb_is_window() is False
    view._apply_rubber_selection()
    assert set(w._scene.selectedItems()) == {a, b}, set(w._scene.selectedItems())

    # Shift 추가선택: 기존 선택(b)을 유지한 채 window(a) 결과를 더함
    view._rb_base = [b]
    view._rb_origin, view._rb_current = tl, br
    view._apply_rubber_selection()
    assert set(w._scene.selectedItems()) == {a, b}
    view._rb_base = []

    # 보이는 외형에 딱 맞는(핸들 여유 제외) window 박스도 잡혀야 함(사용자 리포트 회귀).
    # 예전엔 sceneBoundingRect의 핸들 패딩 때문에 보이는 것보다 넓게 그려야만 잡혔다.
    snug_tl = view.mapFromScene(QPointF(-4, -4))
    snug_br = view.mapFromScene(QPointF(104, 64))     # a(0,0,100,60) + 4px 여유
    view._rb_origin, view._rb_current = snug_tl, snug_br
    view._apply_rubber_selection()
    assert a in set(w._scene.selectedItems()), "snug window box must select fully-visible item"
    view._rb_origin = view._rb_current = None




def test_rubber_band_drag_defers_real_selection_to_release():
    # [성능 조사 2026-07-30, Lucid 대조 사용자 피드백] 드래그 '중'엔 매 프레임 실제
    # setSelected() 캐스케이드(_apply_rubber_selection) 대신 저비용 미리보기(_rb_preview)만
    # 갱신하고, 실제 선택은 release 시점에 1회 확정한다 — 실측(200아이템,30프레임) 194.61ms
    # /frame → 30.68ms/frame(약 84%↓). mousePressEvent→mouseMoveEvent(들)→mouseReleaseEvent
    # 전체 경로로 검증(내부 메서드 직접 호출이 아니라 실제 이벤트 디스패치).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    view = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 450, 0, 100, 60)

    def mk(etype, pt, buttons_held=Qt.MouseButton.LeftButton):
        btn = Qt.MouseButton.LeftButton if etype != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
        ptf = QPointF(pt)
        return QMouseEvent(etype, ptf, ptf, btn, buttons_held, Qt.KeyboardModifier.NoModifier)

    start = view.mapFromScene(QPointF(-10, -10))          # 빈 영역(방향: 왼→오 = window)
    mid = view.mapFromScene(QPointF(200, 100))
    end = view.mapFromScene(QPointF(600, 300))             # a, b 둘 다 완전포함하는 상자(b는 550까지)

    view.mousePressEvent(mk(QEvent.Type.MouseButtonPress, start))
    assert view._rb_active is True

    view.mouseMoveEvent(mk(QEvent.Type.MouseMove, mid))
    assert len(view._rb_preview) >= 1                      # 미리보기는 갱신됨
    assert w._scene.selectedItems() == []                  # 실제 선택은 아직 안 바뀜(핵심)

    view.mouseMoveEvent(mk(QEvent.Type.MouseMove, end))
    assert set(view._rb_preview) == {a, b}
    assert w._scene.selectedItems() == []                  # release 전까진 여전히 비어있음

    view.mouseReleaseEvent(mk(QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.NoButton))
    assert set(w._scene.selectedItems()) == {a, b}          # release에서 정확히 확정
    assert view._rb_active is False and view._rb_preview == set()




def test_line_arrow_label():
    # 선/화살표 라벨: 자식으로 부착 → 본체 이동·끝점 이동 시 중점 추종, .ecad 왕복 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    ln = _LineItem(QLineF(0, 0, 100, 0)); ln.setPen(w.make_pen())
    ln.setFlags(ln.GraphicsItemFlag.ItemIsSelectable | ln.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ln)

    lbl = ln.ensure_label(); lbl.setPlainText("L1"); ln._sync_label()
    assert lbl.parentItem() is ln                       # 자식으로 부착
    lc = lbl.mapToScene(lbl._content_rect().center())
    assert abs(lc.x() - 50) < 2 and lc.y() < 0          # 중점 x≈50, 선 위쪽

    ln.setPos(QPointF(200, 0))                          # 본체 이동 → 자식 자동 추종
    assert abs(lbl.mapToScene(lbl._content_rect().center()).x() - 250) < 2

    ln.setPos(QPointF(0, 0))
    ln._set_endpoint(1, QPointF(0, 100))                # (0,0)-(0,100), 중점 (0,50)
    lc3 = lbl.mapToScene(lbl._content_rect().center())
    assert abs(lc3.x()) < 2 and abs(lc3.y() - 50) < 30  # 끝점 이동 추종

    ar = _ArrowItem(QColor("#ffff0000"), 6, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    albl = ar.ensure_label(); albl.setPlainText("A1"); ar._sync_label()
    assert abs(albl.mapToScene(albl._content_rect().center()).x() - 50) < 2
    ar._set_endpoint(1, QPointF(100, 100))              # 중점 (50,50)
    ac2 = albl.mapToScene(albl._content_rect().center())
    assert abs(ac2.x() - 50) < 2 and abs(ac2.y() - 50) < 40

    # .ecad 왕복 — 라벨은 자식이라 최상위 카운트 제외, 텍스트 보존
    path = os.path.join(_TMP, "label.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 2                # 선 + 화살표(라벨 제외)
    tops = [it for it in sc2.items() if it.parentItem() is None]
    lines = [it for it in tops if isinstance(it, _LineItem)]
    arrows = [it for it in tops if isinstance(it, _ArrowItem)]
    assert len(lines) == 1 and lines[0].has_label() and lines[0]._label.toPlainText() == "L1"
    assert len(arrows) == 1 and arrows[0].has_label() and arrows[0]._label.toPlainText() == "A1"




def test_click_outside_finishes_text_edit():
    # 편집 중 텍스트 바깥을 좌클릭하면 편집을 마무리(clearFocus)해야 한다. 실제 포커스 해제는
    # 활성창이 필요해 offscreen에선 관측 불가 → '바깥 클릭이면 clearFocus 호출, 텍스트 위면
    # 미호출'이라는 우리 분기 판정만 검증(실제 종료는 GUI에서 확인).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select")
    tx = _TextItem(QColor("#ff000000")); tx.setPlainText("hi")
    tx.setFlags(tx.GraphicsItemFlag.ItemIsSelectable | tx.GraphicsItemFlag.ItemIsMovable)
    tx.setPos(QPointF(50, 50)); w._scene.addItem(tx)
    tx.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
    tx.setFocus()
    calls = []
    tx.clearFocus = lambda: calls.append(1)   # 호출 여부 감지(offscreen 무해)

    def press_at(scene_pt):
        vp = w._view.mapFromScene(scene_pt)
        w._view.mousePressEvent(QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(vp), QPointF(vp),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        w._view.mouseReleaseEvent(QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(vp), QPointF(vp),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))

    press_at(QPointF(55, 55))          # 텍스트 '위' 클릭 = 캐럿 이동, 종료 안 함
    assert not calls, "click inside editing text must not finish edit"
    press_at(QPointF(5000, 5000))      # 텍스트 '바깥' 빈 영역 = 편집 종료 호출
    assert calls, "click outside editing text must finish edit"




def test_arrow_label_3_positions_and_gap():
    # [M4-1] 라벨 수직 오프셋이 3위치(선 위 0 / ±D)로만 스냅 + 갭 패딩 축소(5→2).
    # along-line t(0.5)는 유지된다(수평 슬라이드 자유).
    from easycad.canvas.annotator_core import _snap_label_off, _LABEL_SIDE_GAP
    w = CanvasWindow()
    for cls in (_ArrowItem, _PolyArrowItem):
        ar = cls(QColor("#ff111111"), 4, True)
        ar.set_points(QPointF(0, 0), QPointF(100, 0))       # 수평선 → 법선 (0,1)
        ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
        w._scene.addItem(ar)
        lbl = ar.ensure_label(); lbl.setPlainText("Lx"); ar._sync_label()
        br = lbl._content_rect()
        D = br.height() / 2.0 + _LABEL_SIDE_GAP
        assert cls._LABEL_GAP_PAD == 2.0                    # 갭 패딩 축소
        # 큰 아래 오프셋 → +D 스냅, t 유지 ([다중 라벨] _reproject_label은 이제 어느 라벨인지
        # 명시로 받는다 — 화살표당 라벨이 여러 개일 수 있어서).
        ar._reproject_label(lbl, QPointF(50 - br.width() / 2, 40 - br.height() / 2))
        assert abs(ar._label_off - D) < 1e-6 and abs(ar._label_t - 0.5) < 0.05
        # 큰 위 오프셋 → -D 스냅
        ar._reproject_label(lbl, QPointF(50 - br.width() / 2, -40 - br.height() / 2))
        assert abs(ar._label_off + D) < 1e-6
        # 선 근처(작은 오프셋) → 0(선 위)로 흡수
        ar._reproject_label(lbl, QPointF(50 - br.width() / 2, 1 - br.height() / 2))
        assert ar._label_off == 0.0
        w._scene.removeItem(ar)




def test_straight_arrow():
    # 직선(꺾은선) 화살표: 정점 드래그(끝점 재사용)·waypoint 삽입·라벨·.ecad 왕복.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(0, 0), QPointF(100, 0))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    assert len(sa._endpoints()) == 2                       # 정점 = 끝점 핸들

    sa.insert_vertex(0, QPointF(50, 40))                   # 세그먼트0에 waypoint 삽입
    assert len(sa._pts) == 3 and sa._pts[1] == QPointF(50, 40)
    sa._set_endpoint(2, QPointF(100, 80))                  # 정점 드래그(끝점 machinery 경로)
    assert sa._pts[2] == QPointF(100, 80)

    tip, _ang = sa._tip_and_angle()                        # 화살촉 = 마지막 정점
    assert tip == QPointF(100, 80)

    lbl = sa.ensure_label(); lbl.setPlainText("S1"); sa._sync_label()
    assert lbl.parentItem() is sa

    path = os.path.join(_TMP, "sarrow.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1                   # 라벨은 자식이라 카운트 제외
    tops = [it for it in sc2.items() if it.parentItem() is None]
    sas = [it for it in tops if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    assert [(p.x(), p.y()) for p in sas[0]._pts] == [(0, 0), (50, 40), (100, 80)]
    assert sas[0].has_label() and sas[0]._label.toPlainText() == "S1"




def test_sarrow_label_gap_breaks_line():
    # [FigJam 갭] 라벨이 있으면 그 자리에서 선을 끊고(가시 경로가 쪼개짐), 없으면 연속(2요소).
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    sa = _PolyArrowItem(QColor("#000000ff"), 3, True)
    sa._pts = [QPointF(0, 0), QPointF(200, 0)]
    sc.addItem(sa)
    assert sa._visible_polyline_path().elementCount() == 2      # 라벨 없음 = 통짜 선(move+line)
    sa.ensure_label().setPlainText("예"); sa._sync_label()
    assert isinstance(sa._label, _ConnectorLabel)
    assert sa._visible_polyline_path().elementCount() > 2        # 라벨 자리에서 끊김
    # 히트/직렬화 경로는 전체 폴리라인 그대로(갭은 시각뿐).
    assert sa._polyline_path().elementCount() == 2




def test_sarrow_label_drag_slides_and_offsets():
    # 라벨 드래그(Movable+itemChange 재투영) — 슬라이드(t)는 자유, 수직 오프셋은 [M4-1] 3위치 스냅.
    from PyQt6.QtWidgets import QGraphicsScene
    from easycad.canvas.annotator_core import _LABEL_SIDE_GAP, _ink_center_dy
    sc = QGraphicsScene()
    sa = _PolyArrowItem(QColor("#000000ff"), 3, True)
    sa._pts = [QPointF(0, 0), QPointF(200, 0)]
    sc.addItem(sa)
    lbl = sa.ensure_label(); lbl.setPlainText("예"); sa._sync_label()
    assert (round(sa._label_t, 3), round(sa._label_off, 3)) == (0.5, 0.0)
    br = lbl._content_rect()
    D = br.height() / 2.0 + _LABEL_SIDE_GAP                       # 수평선 → 법선 (0,1)
    # t≈0.25(x=50)로 슬라이드는 자유, 위로 크게 뺀 오프셋은 -D(위쪽)로 스냅.
    lbl.setPos(QPointF(50 - br.width() / 2, -15 - br.height() / 2))
    assert abs(sa._label_t - 0.25) < 0.02                        # 슬라이드 유지(자유)
    assert abs(sa._label_off - (-D)) < 0.5                       # 3위치 스냅(-15→-D)
    a = sa._label_anchor()                                        # 구속 중심 == 앵커(+잉크보정 dy)
    dy = _ink_center_dy(lbl)   # [실사용 지적 2026-08-21] 박스중심이 아니라 글자잉크가 앵커에 옴
    c = QPointF(lbl.pos().x() + br.width() / 2, lbl.pos().y() + br.height() / 2)
    assert abs(c.x() - a.x()) < 0.5 and abs(c.y() - dy - a.y()) < 0.5




def test_sarrow_label_t_off_roundtrip():
    # 라벨 위치(t·off)가 .ecad 저장/열기로 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    sa = _PolyArrowItem(QColor("#000000ff"), 3, True)
    sa._pts = [QPointF(0, 0), QPointF(200, 0)]
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.ensure_label().setPlainText("예"); sa._label_t = 0.3; sa._label_off = 12.0; sa._sync_label()
    path = os.path.join(_TMP, "sarrow_label_pos.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene(); load_document(sc2, path)
    a2 = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)][0]
    assert abs(a2._label_t - 0.3) < 1e-6 and abs(a2._label_off - 12.0) < 1e-6




def test_arrow_curved_label_gap_drag_roundtrip():
    # [FigJam 갭·드래그] 곡선(베지어) 화살표도 라벨 자리에 갭 + 드래그로 곡선 위 슬라이드/오프셋.
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    a = _ArrowItem(QColor("#e02424ff"), 4, True); sc.addItem(a)
    a._p1 = QPointF(0, 0); a._p2 = QPointF(300, 0)
    a._ctrl1 = QPointF(100, -120); a._ctrl2 = QPointF(200, -120)   # 아치형 곡선
    assert a._label_gap_rect() is None                             # 라벨 없음 = 갭 없음
    lbl = a.ensure_label(); lbl.setPlainText("반가워"); a._sync_label()
    assert isinstance(a._label, _ConnectorLabel)
    assert a._label_gap_rect() is not None                         # 라벨 = 갭 사각형 생김
    assert (round(a._label_t, 2), round(a._label_off, 2)) == (0.5, 0.0)
    # 드래그: 곡선 위 t≈0.25 지점 근처 + 바깥으로 당김 → t·off 갱신, 중심이 앵커에 구속(+잉크보정).
    from easycad.canvas.annotator_core import _ink_center_dy
    br = lbl._content_rect(); q = a._point_at(0.25)
    lbl.setPos(QPointF(q.x() - br.width() / 2, q.y() - 30 - br.height() / 2))
    assert abs(a._label_t - 0.25) < 0.08 and abs(a._label_off) > 5
    dy = _ink_center_dy(lbl)   # [실사용 지적 2026-08-21] 박스중심이 아니라 글자잉크가 앵커에 옴
    c = QPointF(lbl.pos().x() + br.width() / 2, lbl.pos().y() + br.height() / 2)
    a2anchor = a._label_anchor()
    assert abs(c.x() - a2anchor.x()) < 0.5 and abs(c.y() - dy - a2anchor.y()) < 0.5
    # .ecad 왕복으로 t·off 보존.
    w = CanvasWindow()
    path = os.path.join(_TMP, "arrow_curve_label.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene(); load_document(sc2, path)
    a3 = [it for it in sc2.items() if isinstance(it, _ArrowItem)][0]
    assert abs(a3._label_t - a._label_t) < 1e-6 and abs(a3._label_off - a._label_off) < 1e-6




def test_center_label_shrinks_not_wraps():
    # 마름모 중앙 라벨은 넘칠 때 폰트 축소(단일 줄), 세로로 안 삐져나온다(wrap 결함 회피).
    # (_sync_label의 폰트 적합은 라벨이 씬에 있을 때만 돈다 — 실제 사용과 동일하게 씬에 넣는다.)
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    d = _SymbolItem("decision", QRectF(0, 0, 150, 92)); sc.addItem(d)
    d.ensure_label().setPlainText("검색 결과 있음 판정 오래된 것")   # 아주 긴 라벨
    d._sync_label()
    lbl = d._label
    assert lbl.textWidth() == -1                                   # 줄바꿈 안 함(단일 줄)
    assert lbl.font().pointSize() < lbl._base_pt                   # 넘쳐서 축소됨
    assert lbl._content_rect().height() < d.rect().height()        # 세로로 안 넘침(spill 없음)
    # 짧은 라벨은 축소 없이 기준 크기 유지.
    d2 = _SymbolItem("decision", QRectF(0, 0, 150, 92)); sc.addItem(d2)
    d2.ensure_label().setPlainText("예"); d2._sync_label()
    assert d2._label.font().pointSize() == d2._label._base_pt




def test_sarrow_segment_drag():
    # [M4-4] 세그먼트 위 hover 감지 → press·drag로 그 변을 수직 이동(끝점은 고정, 직교 유지).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)   # 기본 라우팅=ortho
    sa.set_points(QPointF(0, 0), QPointF(100, 0))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa); sa.setSelected(True)
    view = w._view

    vp = view.mapFromScene(QPointF(50, 0))          # 세그먼트0 중앙 hover
    hit = view._segment_add_at(vp)
    assert hit is not None and hit[0] is sa and hit[1] == 0

    view._seg_add = hit                              # press → 세그먼트 드래그 시작
    view.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(vp), QPointF(vp),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    assert view._seg_drag is sa
    tgt = view.mapFromScene(QPointF(50, 40))         # 변을 아래(y=40)로 끌기
    view.mouseMoveEvent(QMouseEvent(
        QEvent.Type.MouseMove, QPointF(tgt), QPointF(tgt),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    view.mouseReleaseEvent(QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(tgt), QPointF(tgt),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert view._seg_drag is None
    assert not sa._auto_route                        # 세그먼트 드래그 = 수동 직교로 전환
    # 끝점은 (0,0)·(100,0) 그대로, 중간 변이 y=40로 내려가 U자(모든 변 직교).
    assert abs(sa._pts[0].x()) < 1 and abs(sa._pts[0].y()) < 1
    assert abs(sa._pts[-1].x() - 100) < 1 and abs(sa._pts[-1].y()) < 1
    assert any(abs(p.y() - 40) < 3 for p in sa._pts)
    assert all(abs(a.x() - b.x()) < 1e-6 or abs(a.y() - b.y()) < 1e-6
               for a, b in zip(sa._pts[:-1], sa._pts[1:]))
    w.undo()                                         # undo → 원래 2점 직선 복원
    assert len(sa._pts) == 2

    # 정점 위(끝점) hover는 세그먼트 이동이 아니라 끝점 이동 우선 → None
    vtx = view.mapFromScene(QPointF(0, 0))
    assert view._segment_add_at(vtx) is None




def test_segment_off_pill_drag_subdivides_near_half_only():
    # [2026-08-03 Lucid 대조, rf 계정 Lucid 문서에서 실제 재현 확인] 고정 알약(변 중점)이 아닌
    # 위치를 끌면 그 알약 자리에 새 정점이 생겨 변이 둘로 나뉘고, 클릭 지점에 더 가까운 쪽
    # 절반만 꺾인다 — 알약 반대쪽(먼 쪽)은 그대로 유지된다.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(0, 0), QPointF(100, 100))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa); sa.setSelected(True)
    sa._auto_route = False
    sa._pts = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100)]
    sa.prepareGeometryChange()
    view = w._view

    # segment 0: (0,0)->(100,0), pill at (50,0). Hover near the (0,0) end, off the pill.
    vp = view.mapFromScene(QPointF(20, 0))
    hit = view._segment_add_at(vp)
    assert hit is not None and hit[0] is sa and hit[1] == 0 and hit[3] is False, "off-pill"

    view._seg_add = hit
    view.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(vp), QPointF(vp),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    tgt = view.mapFromScene(QPointF(20, -30))
    view.mouseMoveEvent(QMouseEvent(
        QEvent.Type.MouseMove, QPointF(tgt), QPointF(tgt),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    view.mouseReleaseEvent(QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(tgt), QPointF(tgt),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

    # 원래 알약 자리(50,0)는 그대로 고정 정점으로 남고, 그 뒤(코너~끝점)는 완전히 그대로.
    assert any(abs(p.x() - 50) < 1 and abs(p.y()) < 1 for p in sa._pts), "원래 알약 자리 보존"
    assert sa._pts[-2] == QPointF(100, 0) and sa._pts[-1] == QPointF(100, 100), "먼 쪽 그대로"
    # 가까운 쪽(0,0 근처)만 y=-30으로 꺾임 — 새 지그재그가 생겼다.
    assert any(abs(p.y() + 30) < 1 for p in sa._pts), "가까운 쪽만 이동"


def test_segment_subdivide_preview_fixed_not_cursor_tracking():
    # [2026-08-04 버그수정] 미리보기 알약은 커서를 따라가지 않고, 커서가 있는 절반(A~M 또는
    # M~B)의 자체 중점에 고정된다 — 실제 삽입이 항상 고정 알약(M) 자리에서 일어나는 것과 위치가
    # 일치해야 한다(사용자 실측: 예전엔 알약이 몸통선을 따라 미끄러지듯 보여 오해를 줬다).
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(0, 0), QPointF(100, 0))   # 세그먼트0, M=(50,0)

    # A쪽(0~50) 절반 어디를 호버하든 미리보기는 A~M 중점(25,0)에 고정.
    q1 = sa._segment_subdivide_preview_point(0, QPointF(5, 0))
    q2 = sa._segment_subdivide_preview_point(0, QPointF(45, 0))
    assert abs(q1.x() - 25) < 1e-6 and q1 == q2, "A쪽 절반은 항상 같은 고정 위치"

    # B쪽(50~100) 절반 어디를 호버하든 미리보기는 M~B 중점(75,0)에 고정.
    q3 = sa._segment_subdivide_preview_point(0, QPointF(55, 0))
    q4 = sa._segment_subdivide_preview_point(0, QPointF(95, 0))
    assert abs(q3.x() - 75) < 1e-6 and q3 == q4, "B쪽 절반은 항상 같은 고정 위치"
    assert sa._pts[0] == QPointF(0, 0), "먼 원래 끝점 좌표 유지(고정)"


def test_interior_press_takes_move_branch_not_rubberband():
    # [M4-4 ⓓ → 2026-08-03 실사용 지적으로 미선택까지 확장] 실제 press 경로: 속 빈 네모의
    # '내부'를 누르면 선택 여부와 무관하게 뷰가 러버밴드가 아니라 아이템 선택/이동 분기
    # (_snapshot_movable → super)로 간다 — Lucid/FigJam처럼 내부 클릭만으로 선택까지 된다.
    # ⚠ Qt의 아이템 grab(실제 이동)까지는 이 오프스크린 하네스에서 재현되지 않아(합성 이벤트가
    #    씬으로 배달되지 않음) 뷰의 분기 선택까지만 검증한다 — 이동 자체는 실조건 몫.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    r = _mk_pen_rect(w, x=-100, y=-60, ww=200, hh=120)
    view = w._view
    inside = view.mapFromScene(QPointF(0, 0))          # 도형 한가운데(테두리서 멀다)

    def press():
        view.mousePressEvent(QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(inside), QPointF(inside),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))

    # ⓐ 선택 전 — 내부가 이미 '아이템 위' → 클릭만으로 바로 선택+이동 분기(러버밴드 아님)
    assert not view._is_empty_area(inside)
    press()
    assert not view._rb_active and view._move_active
    assert any(it is r for it, _p in view._move_snap)   # 이동 undo 스냅샷에 포함
    view.mouseReleaseEvent(QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(inside), QPointF(inside),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

    # ⓑ 선택 후 — 같은 자리가 여전히 '아이템 위' → 이동 분기 그대로
    r.setSelected(True)
    view._move_active = False
    assert not view._is_empty_area(inside)
    press()
    assert not view._rb_active and view._move_active
    assert any(it is r for it, _p in view._move_snap)   # 이동 undo 스냅샷에 포함




def test_ortho_constraint():
    # F8 Ortho 제약 계산: start 기준 0/90°. |dx|≥|dy|=수평(y 고정), 아니면 수직(x 고정).
    from easycad.canvas.annotator_core import _AnnotatorView
    c = _AnnotatorView._constrain
    assert c(QPointF(0, 0), QPointF(100, 20), "ortho") == QPointF(100, 0)   # 수평
    assert c(QPointF(0, 0), QPointF(20, 100), "ortho") == QPointF(0, 100)   # 수직
    assert c(QPointF(50, 50), QPointF(10, 55), "ortho") == QPointF(10, 50)  # 수평(음의 dx)

    # 정점 드래그 ortho: 인접 정점(이전 우선) 기준 0/90° 스냅.
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(0, 0), QPointF(100, 0))
    # 끝점 1 드래그(anchor=pts[0]=(0,0)). (90,30) → |dx|90≥|dy|30 → 수평 → (90,0)
    assert sa._ortho_endpoint(1, QPointF(90, 30)) == QPointF(90, 0)
    # (30,90) → 수직 → x=anchor.x=0 → (0,90)
    assert sa._ortho_endpoint(1, QPointF(30, 90)) == QPointF(0, 90)
    # 끝점 0 드래그(anchor=pts[1]=(100,0)). (70,90) → dx=-30,dy=90 → 수직 → x=100 → (100,90)
    assert sa._ortho_endpoint(0, QPointF(70, 90)) == QPointF(100, 90)




def test_straight_arrow_click_draw():
    # 하이브리드 클릭 배치(직선화살표): 클릭→이동→클릭으로 정점 누적, 더블클릭 마무리, Esc=마지막 점까지 확정.
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    NO = Qt.KeyboardModifier.NoModifier
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    view = w._view
    _p, _r, click, move, _dm, dbl = _draw_helpers(view)

    # 첫 클릭(드래그 없음) = 배치 시작(v0 + 미리보기 정점)
    click(QPointF(0, 0))
    assert view._place is not None and view._place_tool == "sarrow"
    assert len(view._place._pts) == 2

    move(QPointF(100, 0))
    assert _close(view._place._pts[-1], QPointF(100, 0))

    click(QPointF(100, 0))                 # 둘째 클릭 = 정점 확정
    assert len(view._place._pts) == 3

    move(QPointF(80, 100))
    dbl(QPointF(80, 100))                   # 더블클릭 = 마무리
    assert view._place is None
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    pts = [(round(p.x()), round(p.y())) for p in sas[0]._pts]
    assert pts == [(0, 0), (100, 0), (80, 100)], pts
    assert sas[0].isSelected()

    # [개정] Esc = 취소가 아니라 '지금까지 놓은 점으로 확정'(마지막 커서 추종 미리보기만 버림)
    before = len([it for it in w._scene.items() if isinstance(it, _PolyArrowItem)])
    click(QPointF(300, 300)); move(QPointF(400, 300)); click(QPointF(400, 300))
    move(QPointF(500, 300))                 # 미리보기만 이동(확정 안 함)
    assert view._place is not None
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NO))
    assert view._place is None
    sas2 = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas2) == before + 1, "Esc는 놓은 점까지 확정해야 함(폐기 아님)"
    committed = [s for s in sas2 if s.isSelected()][0]
    pts = [(round(p.x()), round(p.y())) for p in committed._pts]
    assert pts == [(300, 300), (400, 300)], pts   # 미리보기(500,300)는 버려짐

    # 시작점만 놓고 Esc → 확정할 정점 부족(1개) → 폐기
    before2 = len([it for it in w._scene.items() if isinstance(it, _PolyArrowItem)])
    click(QPointF(700, 700))
    assert view._place is not None
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NO))
    assert view._place is None
    after2 = len([it for it in w._scene.items() if isinstance(it, _PolyArrowItem)])
    assert after2 == before2, "시작점만 있으면 Esc는 폐기(2정점 미만)"




def test_straight_arrow_click_draw_ortho():
    # F8 Ortho + 클릭 배치: 미리보기 정점이 직전 정점 기준 0/90°로 스냅.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    w.ortho_enabled = True
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    click(QPointF(0, 0))
    move(QPointF(100, 20))                  # |dx|>|dy| → 수평 → y=0
    assert _close(view._place._pts[-1], QPointF(100, 0))
    move(QPointF(20, 100))                   # 수직 → x=0
    assert _close(view._place._pts[-1], QPointF(0, 100))
    view._cancel_place()
    assert view._place is None




def test_hybrid_two_click_shapes():
    # 2점 도구(선·네모)를 투클릭으로: 클릭→이동→클릭 = 확정(드래그 안 해도 그려짐).
    w = CanvasWindow(); w.show(); w._zoom_reset()
    w.grid_enabled = False   # [그리드] 이 테스트는 클릭 배치 좌표 자체를 검증 — 격자 스냅은 별도 테스트
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    # 선: 투클릭
    w.set_tool("line")
    click(QPointF(0, 0))
    assert view._place is not None and view._place_tool == "line"
    move(QPointF(100, 50))
    click(QPointF(100, 50))                  # 둘째 클릭 = 확정
    assert view._place is None
    lines = [it for it in w._scene.items() if isinstance(it, _LineItem)]
    assert len(lines) == 1
    ln = lines[0].line()
    assert _close(ln.p1(), QPointF(0, 0)) and _close(ln.p2(), QPointF(100, 50))
    assert lines[0].isSelected()

    # 네모: 투클릭
    w.set_tool("rect")
    click(QPointF(200, 0)); move(QPointF(320, 80)); click(QPointF(320, 80))
    assert view._place is None
    rects = [it for it in w._scene.items() if isinstance(it, _RectItem)]
    assert len(rects) == 1
    r = rects[0].rect()
    assert abs(r.width() - 120) < 2 and abs(r.height() - 80) < 2, (r.width(), r.height())




def test_hybrid_drag_still_works():
    # 드래그(press-move(버튼)-release, 이동>=임계) = 즉시 확정(기존 동작 보존).
    w = CanvasWindow(); w.show(); w._zoom_reset()
    view = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)

    # 네모 드래그
    w.set_tool("rect")
    press(QPointF(0, 0)); drag_move(QPointF(120, 80)); release(QPointF(120, 80))
    assert view._place is None and view._drawing is False
    rects = [it for it in w._scene.items() if isinstance(it, _RectItem)]
    assert len(rects) == 1 and rects[0].isSelected()

    # 직선화살 드래그 = 2점 직선(멀티정점 아님)
    w.set_tool("sarrow")
    press(QPointF(0, 200)); drag_move(QPointF(150, 200)); release(QPointF(150, 200))
    assert view._place is None
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1 and len(sas[0]._pts) == 2
    assert sas[0].isSelected()




def test_straight_arrow_binding():
    # [A3] 직선화살표 끝점을 도형 테두리에 지속 연결 → 도형 이동 시 추종, waypoint는 제외, .ecad 왕복.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(500, 30), QPointF(100, 30))     # 끝(idx1)을 우측 테두리(100,30)에
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)

    sa.set_bound(1, r, QPointF(100, 30))                  # 끝을 도형 로컬(100,30)에 고정
    assert sa.has_binding()
    sa.reroute(pin_pred=lambda i: True)
    assert _close(sa.mapToScene(sa._pts[1]), QPointF(100, 30))

    r.setPos(QPointF(200, 0)); w._on_scene_changed(None)   # 도형 이동 → 끝점 추종
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(300, 30))

    r.setSelected(True); sa.setSelected(True)              # 둘 다 선택 = 강체
    assert w._make_pin_pred(sa)(1) is False
    r.setSelected(False)                                   # 도형만 = 늘림
    assert w._make_pin_pred(sa)(1) is True

    # 중간 waypoint 삽입 → 끝 바인딩은 '역할'로 새 끝(idx2)에 유지, 중간(idx1)은 무바인딩
    r.setPos(QPointF(0, 0)); sa.set_bound(1, r, QPointF(100, 30)); sa.reroute(pin_pred=lambda i: True)
    sa.insert_vertex(0, QPointF(300, 100))                 # pts=[(500,30),(300,100),(100,30)]
    assert sa._bound(2) is r and sa._bound(1) is None

    # .ecad 왕복 — 바인딩 보존
    path = os.path.join(_TMP, "sabind.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    load_document(sc2, path)
    a2 = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)][0]
    r2 = [it for it in sc2.items() if isinstance(it, _RectItem)][0]
    last = len(a2._pts) - 1
    assert a2._bound(last) is r2 and a2._bound(0) is None
    assert a2._bind_pt(last) == QPointF(100, 30)




def test_straight_arrow_draw_binds():
    # [A3] 드래그로 그린 직선화살표의 끝이 도형 테두리 근처면 확정 시 스냅+바인딩(그리기-시점 부착).
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    r = _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)   # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)

    press(QPointF(0, 30)); drag_move(QPointF(305, 30)); release(QPointF(305, 30))
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    sa = sas[0]
    assert sa.has_binding()
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(300, 30)), sa.mapToScene(sa._pts[-1])
    assert sa._bound(0) is None                             # 시작(0,30)은 테두리에서 멀어 무바인딩

    # o-snap(F3) 꺼짐이면 새로 그려도 바인딩 안 됨
    w.snap_enabled = False
    press(QPointF(0, 130)); drag_move(QPointF(305, 130)); release(QPointF(305, 130))
    sas2 = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    newest = [s for s in sas2 if s is not sa][0]
    assert not newest.has_binding()
    w.snap_enabled = True




def test_straight_arrow_live_snap():
    # [이슈] sarrow 그리는 중 끝점이 도형 테두리에 '라이브 스냅'(마커) + 직전 점 근처 스냅은 무시.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)

    # 시작(0,30) 멀리 → 끝을 테두리 근처(305,30)로 드래그 → 라이브 tip 마커 = 테두리점(300,30)
    press(QPointF(0, 30)); drag_move(QPointF(305, 30))
    assert view._arrow_tip_snap is not None and _close(view._arrow_tip_snap, QPointF(300, 30))
    release(QPointF(305, 30))

    # 직전 점 바로 근처(30px 이내)의 테두리 스냅은 무시 — 겹친 극소 화살표 방지
    press(QPointF(295, 30)); drag_move(QPointF(305, 30))   # 시작이 테두리에 스냅→끝이 그 30px내
    assert view._arrow_tip_snap is None, "직전 점 근처 스냅은 무시돼야(극소 화살표 방지)"
    view._cancel_place() if view._place is not None else release(QPointF(305, 30))




def test_arrow_border_start_gestures():
    # [이슈] sarrow·곡선화살 모두 테두리에서 시작 가능(하이브리드): 드래그도 클릭(투클릭)도.
    w = CanvasWindow(); w.show(); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, click, move, drag_move, _d = _draw_helpers(view)

    # sarrow: 테두리 근처(305,30)서 press → 드래그 → 시작이 테두리에 스냅·바인딩된 화살표
    w.set_tool("sarrow")
    press(QPointF(305, 30)); drag_move(QPointF(500, 30)); release(QPointF(500, 30))
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    assert _close(sas[0].mapToScene(sas[0]._pts[0]), QPointF(300, 30))   # 시작 테두리 스냅
    assert sas[0]._bound(0) is not None                                   # 시작 바인딩

    # 곡선화살: 테두리 근처 클릭 → 배치 모드(하이브리드 복원, sarrow와 동일) — 시작 바인딩.
    # 앞서 그린 sarrow 선택 해제 + 그 sarrow와 안 겹치는 상단 테두리(y=0)에서 시작.
    w.set_tool("arrow")
    w._scene.clearSelection()
    click(QPointF(250, 3))                                                # 네모 상단 테두리 근처
    assert view._place is not None and view._place_tool == "arrow"
    assert view._place._bound(0) is not None                             # 시작이 테두리에 바인딩
    view._cancel_place()

    # 곡선화살: 테두리서 드래그도 정상 생성
    n0 = len([it for it in w._scene.items() if isinstance(it, _ArrowItem)])
    press(QPointF(250, 3)); drag_move(QPointF(250, 300)); release(QPointF(250, 300))
    assert len([it for it in w._scene.items() if isinstance(it, _ArrowItem)]) == n0 + 1




def test_line_tool_snaps_to_border_on_drag():
    # [실사용 지적 2026-08-10] "화살표는 되는데 선은 안 됨" — _LineItem은 지속연결 바인딩
    # (set_bound)이 없는 단순 도형이라 그동안 _border_snap_at 검사 자체를 안 탔다. 좌표
    # 스냅(바인딩 없이)만이라도 화살표·직선화살과 동등해야 한다.
    w = CanvasWindow(); w.show(); w.set_tool("line"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, click, move, drag_move, _d = _draw_helpers(view)

    press(QPointF(0, 30)); drag_move(QPointF(305, 30))
    assert view._arrow_tip_snap is not None and _close(view._arrow_tip_snap, QPointF(300, 30))
    release(QPointF(305, 30))
    lines = [it for it in w._scene.items() if isinstance(it, _LineItem)]
    assert len(lines) == 1
    assert _close(lines[0].line().p2(), QPointF(300, 30))


def test_line_tool_snaps_to_border_on_press_start():
    w = CanvasWindow(); w.show(); w.set_tool("line"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)
    view = w._view
    press, release, click, move, drag_move, _d = _draw_helpers(view)

    press(QPointF(305, 30)); drag_move(QPointF(500, 30)); release(QPointF(500, 30))
    lines = [it for it in w._scene.items() if isinstance(it, _LineItem)]
    assert len(lines) == 1
    assert _close(lines[0].line().p1(), QPointF(300, 30))   # 시작이 테두리 스냅
    assert not hasattr(lines[0], "_bound")   # _LineItem은 지속연결 바인딩 개념 자체가 없음(좌표 스냅만)


def test_line_tool_idle_hover_shows_snap_preview_and_cross_cursor():
    # [실사용 지적 2026-08-10, 직전 커밋 후속] "선을 선택하고 도형에 가면 화살표처럼 예고점이
    # 안 보임. 이동커서만 보임" — `_update_snap_preview`/`_update_hover_cursor`가 그리기
    # *전*(유휴 hover) 예고를 arrow·sarrow로만 국한해서, line은 테두리 좌표 스냅(직전 커밋)이
    # 있어도 그리기 시작 전엔 아무 신호가 없었다. 두 곳 다 "line"을 추가해야 한다.
    w = CanvasWindow(); w.show(); w.set_tool("line"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    _p, _r, _c, move, _dm, _d = _draw_helpers(view)

    move(QPointF(305, 30))   # 그리기 시작 전, 도형 근처로 그냥 hover
    assert view._snap_preview is not None and _close(view._snap_preview, QPointF(300, 30))
    view._update_hover_cursor(view.mapFromScene(QPointF(305, 30)))
    assert view.viewport().cursor().shape() == Qt.CursorShape.CrossCursor




def test_sarrow_click_near_border_no_tiny_arrow():
    # [버그] 테두리 근처 '가만히 클릭'은 시작 스냅 점프를 드래그로 오인해 극소 화살표를 만들면 안 됨.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    _p, _r, click, _m, _dm, _d = _draw_helpers(view)

    click(QPointF(308, 30))          # 테두리(300,30)서 8px 떨어진 곳을 가만히 클릭
    assert view._place is not None, "가만히 클릭은 배치 모드로 들어가야(드래그 오인 금지)"
    pts = [(round(p.x()), round(p.y())) for p in view._place._pts]
    assert pts == [(300, 30), (300, 30)], pts   # 시작이 테두리 스냅, 둘 다 같은 점(배치 대기)
    view._cancel_place()




def test_sarrow_ortho_preview_matches_click():
    # [버그] F8 Ortho에서 미리보기(move)와 클릭(_place_click)이 같은 좌표여야(전엔 더블클릭 때만 수평).
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    w.ortho_enabled = True
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    click(QPointF(0, 30))            # 시작
    move(QPointF(200, 50))           # dx=200>dy=20 → 수평 → y=30
    assert _close(view._place._pts[-1], QPointF(200, 30)), "미리보기가 수평이어야"
    click(QPointF(200, 50))          # 클릭 배치 — 미리보기와 같은 (200,30)
    assert _close(view._place._pts[-2], QPointF(200, 30)), "클릭 배치가 미리보기와 일치해야"
    view._cancel_place()




def test_sarrow_ortho_snaps_to_border():
    # [버그] F8 Ortho에서도 끝이 도형 테두리 근처면 스냅+마커(수직 모서리면 수평 유지).
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    w.ortho_enabled = True
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)     # 우측 테두리 x=300, y[0..60]
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    click(QPointF(0, 30))            # 시작(테두리와 같은 y=30)
    move(QPointF(305, 40))           # 우측 테두리 근처. ortho→y=30, 근처면 (300,30)로 스냅
    assert view._arrow_tip_snap is not None and _close(view._arrow_tip_snap, QPointF(300, 30))
    assert _close(view._place._pts[-1], QPointF(300, 30)), "수평(y=30) 유지 + 테두리 스냅"
    view._cancel_place()




def test_sarrow_snap_click_auto_finishes():
    # [개정] 클릭 배치 중 도형 테두리에 스냅된 클릭 = 종점 → 더블클릭 없이 자동 마무리.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    click(QPointF(0, 30))                 # 시작(테두리에서 멂) → 배치 모드
    assert view._place is not None
    move(QPointF(305, 30)); click(QPointF(305, 30))   # 테두리 근처 클릭 = 스냅 → 자동 마무리
    assert view._place is None, "스냅점 클릭은 더블클릭 없이 마무리돼야"
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    sa = sas[0]
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(300, 30)), sa.mapToScene(sa._pts[-1])
    assert sa._bound(len(sa._pts) - 1) is not None   # 종점이 도형에 바인딩

    # 시작점이 테두리 근처여도(_enter_click_place 경로) 조기 종료되지 않는다.
    w2 = CanvasWindow(); w2.show(); w2.set_tool("sarrow"); w2._zoom_reset()
    _mk_rect(w2._scene, w2.make_pen(), 200, 0, 100, 60)
    v2 = w2._view
    _p2, _r2, click2, _m2, _dm2, _d2 = _draw_helpers(v2)
    click2(QPointF(305, 30))              # 시작이 테두리 스냅
    assert v2._place is not None, "시작 스냅은 마무리 트리거가 아님(배치 계속)"
    v2._cancel_place()




def test_ortho_elbow_pure():
    # [Stage1] _ortho_elbow / _dedup_pts 순수함수 — 법선 우세축으로 엘보 정점 생성 + 퇴화 접힘.
    from easycad.canvas.annotator_core import _ortho_elbow, _dedup_pts
    P = QPointF
    s, e = P(100, 30), P(300, 230)
    # 양끝 수평 법선 → H-V-H (중간 x=200)
    mids = _ortho_elbow(s, e, P(1, 0), P(-1, 0))
    assert [(round(m.x()), round(m.y())) for m in mids] == [(200, 30), (200, 230)]
    # 양끝 수직 법선 → V-H-V (중간 y=130)
    mids = _ortho_elbow(s, e, P(0, 1), P(0, -1))
    assert [(round(m.x()), round(m.y())) for m in mids] == [(100, 130), (300, 130)]
    # 혼합(시작 수평·끝 수직) → L자 모서리 하나 = (e.x, s.y)
    mids = _ortho_elbow(s, e, P(1, 0), P(0, -1))
    assert [(round(m.x()), round(m.y())) for m in mids] == [(300, 30)]
    # 수평 정렬(같은 y) + 양끝 수평 → 엘보가 직선으로 접힘(공선 제거)
    full = _dedup_pts([P(100, 30)] + _ortho_elbow(P(100, 30), P(300, 30), P(1, 0), P(-1, 0)) + [P(300, 30)])
    assert [(round(m.x()), round(m.y())) for m in full] == [(100, 30), (300, 30)]




def test_sarrow_auto_elbow_route():
    # [Stage1] 양끝 바인딩 직선화살 → 직교 엘보 자동 생성 / 도형 이동 시 엘보 재계산.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)       # 우측 테두리 (100,30), 법선 +x
    b = _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)   # 좌측 테두리 (300,230), 법선 -x
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(300, 230))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30))
    sa.set_bound(1, b, QPointF(300, 230))
    sa._auto_route = True
    assert sa.build_elbow()
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp) == 4, sp
    assert _close(sp[0], QPointF(100, 30)) and _close(sp[-1], QPointF(300, 230))
    assert _close(sp[1], QPointF(200, 30)) and _close(sp[2], QPointF(200, 230))   # H-V-H, mx=200

    # 도형 이동 → reroute가 끝점 추종 + 엘보 재계산
    b.setPos(QPointF(0, 100))            # b 좌측 테두리 → 씬 (300,330)
    w._on_scene_changed(None)
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert _close(sp[-1], QPointF(300, 330)), sp[-1]
    assert _close(sp[1], QPointF(200, 30)) and _close(sp[2], QPointF(200, 330)), sp




def test_sarrow_manual_edit_disables_auto():
    # [Stage1/2f, 2026-07-29 5차로 (1b) 갱신] waypoint 삽입/삭제 → 자동 해제. 자동 중 '중간'
    # 정점 드래그는 [경유지 힌트]로 바뀌어 해제하지 않는다(freeze 아님 — test_route_hint_*가
    # 커밋 경로를 커버). 끝점 드래그는 더는 auto_route를 끄지 않는다(새로 그리기와 동일 취급 —
    # deep-interview로 옛 '수동 전환' 결정을 뒤집음, 아래 (1b) 참조).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(300, 230))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30)); sa.set_bound(1, b, QPointF(300, 230))
    sa._auto_route = True; sa.build_elbow()

    # (1a) [2f] 자동라우팅 중 중간 정점 드래그 시작 → freeze 아님(힌트 모드 진입)
    sa._on_endpoint_drag_start(1)
    assert sa._auto_route is True and sa._hint_dragging is True
    sa._hint_dragging = False   # 정리(커밋 없이 종료)

    # (1b) [실사용 버그 2026-07-29 5차] 끝점 드래그 시작도 auto_route를 끄지 않는다 — 새로
    # 그린 화살표처럼, 도형이 나중에 움직여도 계속 전체가 자동으로 재라우팅돼야 한다.
    sa._on_endpoint_drag_start(0)
    assert sa._auto_route is True
    b.setPos(QPointF(0, 100)); w._on_scene_changed(None)   # b(끝점 idx last) 이동
    assert all(abs(p1.x() - p2.x()) < 1e-6 or abs(p1.y() - p2.y()) < 1e-6
               for p1, p2 in zip(sa._pts[:-1], sa._pts[1:])), "자동 재라우팅 후에도 직교 유지"

    # (2) waypoint 삽입은 여전히 해제 트리거(수동 폴리라인 편집 — 끝점 드래그와 별개 기능)
    sa2 = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa2.set_points(QPointF(0, 0), QPointF(400, 400)); w._scene.addItem(sa2)
    sa2._auto_route = True
    sa2.insert_vertex(0, QPointF(200, 0))
    assert sa2._auto_route is False




def test_polyarrow_endpoint_drag_recomputes_whole_path():
    # [실사용 버그 2026-07-29 5차 — 재설계] 도형에 붙은 직각 화살표를 뗐다가 다른 경로에
    # 붙이면 직각이 풀어지고 경로도 이상해진다는 사용자 지적(deep-interview 확정) — 끝점
    # 드래그를 '새로 그리기'와 동일하게 취급해 전체 경로를 다시 계산해야 한다. 옛 '스텁만
    # 재정렬(나머지 보존)' 결정(2026-07-29 3차)을 뒤집는다: 옛 목적지 기준 중간점을 그대로
    # 두면 새 목적지와 무관해져 사선/우회가 남았다. 이제는 두 끝점만으로 매 프레임
    # _apply_routing()에 전부 위임 — auto_route도 새로 그린 화살표처럼 True로 유지돼야
    # 도형이 나중에 움직여도 계속 자동 재라우팅된다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(300, 230))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30)); sa.set_bound(1, b, QPointF(300, 230))
    sa._auto_route = True; sa.build_elbow()

    sa._on_endpoint_drag_start(0)                       # 끝점 드래그 시작 — 새로 그리기 취급
    assert sa._auto_route is True, "끝점 드래그도 새로 그린 화살표처럼 auto_route 유지돼야 함"
    sa._move_endpoint_with_snap(0, QPointF(-40, -77))   # 완전히 다른 자유 위치로 재부착
    sa._on_endpoint_drag_end(0)

    _assert_all_segments_axis_aligned(sa._pts, "재부착 후 경로 전체가 직교여야 함")




def test_polyarrow_endpoint_rebind_to_different_axis_port_stays_orthogonal():
    # [실사용 버그 2026-07-29 2차] 왼쪽 변 중심(수평 포트) → 위쪽 변 중심(수직 포트)처럼
    # 축이 다른 포트로 재부착해도, 전체 재계산 경로답게 처음부터 끝까지 직교여야 하고
    # 새 포트의 실제 이탈 축(수직)과도 일치해야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 200, 120)
    b = _mk_rect(w._scene, w.make_pen(), 500, -200, 100, 60)
    w_port = _shape_ports(a)[3][0]   # W(왼쪽 변 중심, 수평 포트)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 3, True)
    sa.set_points(w_port, QPointF(550, -170))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, a.mapFromScene(w_port))
    sa.set_bound(1, b, b.mapFromScene(QPointF(550, -170)))
    sa._auto_route = True; sa.build_elbow()

    sa._on_endpoint_drag_start(0)
    n_port = _shape_ports(a)[0][0]   # N(위쪽 변 중심, 수직 포트) — 축이 다른 포트로 재부착
    sa._move_endpoint_with_snap(0, sa.mapFromScene(n_port))
    sa._on_endpoint_drag_end(0)

    _assert_all_segments_axis_aligned(sa._pts, "재부착 후 경로가 직교여야 함")
    p0, p1 = sa._pts[0], sa._pts[1]
    assert abs(p0.x() - p1.x()) < 1e-6, \
        ("N 포트는 수직 이탈이어야 하는데 변을 타는 경로가 됨", p0, p1)




def test_resolve_drag_endpoint_survives_pts_length_change():
    # [실사용 크래시 2026-07-29] 끝점 드래그가 매 프레임 _apply_routing()으로 경로 전체를
    # 다시 계산하게 되면서 _pts 길이가 프레임 사이에 바뀔 수 있게 됐는데, 아이템의
    # mousePressEvent가 press 시점에 캡처한 인덱스(_drag_endpoint)를 매 프레임 그대로 쓰면
    # 길이가 줄어든 뒤 그 인덱스가 범위를 벗어나 IndexError로 프로그램이 죽었다(실사용자 보고:
    # 화살표 머리를 다른 도형에 재부착하는 도중 드래그가 끊기고, 다음 클릭에서 프로그램 종료 —
    # 끊긴 순간이 이 크래시였고 _drag_endpoint가 못 지워진 채 남아 다음 클릭도 죽였다).
    # _resolve_drag_endpoint()가 "0이었나"만 기억해 매 프레임 실제 유효한 인덱스로 다시
    # 계산해야 한다.
    w = CanvasWindow()
    sa = _PolyArrowItem(QColor("#ff0000ff"), 3, True)
    sa.set_points(QPointF(0, 0), QPointF(10, 10))
    w._scene.addItem(sa)

    sa._pts = [QPointF(0, 0), QPointF(1, 1), QPointF(2, 2), QPointF(3, 3)]
    sa._drag_endpoint = 3   # press 시점에 캡처한 '그때의' 마지막 인덱스
    assert sa._resolve_drag_endpoint() == 3

    sa._pts = [QPointF(0, 0), QPointF(9, 9)]   # 다음 프레임에 재계산으로 2점으로 줄어듦
    idx = sa._resolve_drag_endpoint()
    assert idx == 1, ("길이 변화 후에도 옛 인덱스를 그대로 쓰면 안 됨", idx)
    sa._pts[idx] = QPointF(99, 99)   # 옛 코드라면 idx=3이라 여기서 IndexError

    sa._drag_endpoint = 0   # 시작점(꼬리) 쪽은 항상 0으로 안정적이어야 함
    assert sa._resolve_drag_endpoint() == 0




def test_polyarrow_multiframe_drag_through_opposite_side_stays_clean():
    # [실사용 버그 2026-07-29 3차 → 5차 재설계] 매 프레임 스텁만 재정렬하던 시절엔 자유 위치
    # 프레임들이 서로 결과를 덮어써 이웃점이 표류했다(도형 반대편을 스쳐 지나가는 것만으로도
    # 재현). 이제는 매 프레임 _apply_routing()으로 두 끝점만 갖고 전부 다시 계산하므로,
    # 다중 프레임 왕복 후 결과가 동일 지점으로 '직접' 드래그한 결과와 완전히 같아야 한다
    # (경로 이력에 의존하지 않는 순수 함수가 됐는지 확인).
    def build(w):
        a = _mk_rect(w._scene, w.make_pen(), 0, 0, 200, 120)
        b = _mk_rect(w._scene, w.make_pen(), 500, -200, 100, 60)
        w_port = _shape_ports(a)[3][0]
        sa = _PolyArrowItem(QColor("#ff0000ff"), 3, True)
        sa.set_points(w_port, QPointF(550, -170))
        sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
        w._scene.addItem(sa)
        sa.set_bound(0, a, a.mapFromScene(w_port))
        sa.set_bound(1, b, b.mapFromScene(QPointF(550, -170)))
        sa._auto_route = True; sa.build_elbow()
        return a, sa, w_port

    def lerp(p0, p1, t):
        return QPointF(p0.x() + (p1.x() - p0.x()) * t, p0.y() + (p1.y() - p0.y()) * t)

    w1 = CanvasWindow()
    a1, sa1, w_port1 = build(w1)
    # [2026-07-30] NW 꼭짓점은 더 이상 _shape_ports 목록에 없다(8→4 축소) — 예전 index 4와
    # 동일한 점을 _nearest_border로 직접 투영(디아고날 스냅 자체는 연속 폴백으로 여전히 유효).
    nw, _nw_n = _nearest_border(a1, a1.mapToScene(QPointF(a1.rect().left(), a1.rect().top())))
    e_port = _shape_ports(a1)[1][0]
    sa1._on_endpoint_drag_start(0)
    n = 20
    for leg in ((w_port1, nw), (nw, e_port), (e_port, nw)):   # 원위치 -> 코너 -> 반대변 -> 코너
        for i in range(1, n + 1):
            p = lerp(leg[0], leg[1], i / n)
            sa1._move_endpoint_with_snap(0, sa1.mapFromScene(p))
    sa1._on_endpoint_drag_end(0)

    w2 = CanvasWindow()
    a2, sa2, _w_port2 = build(w2)
    sa2._on_endpoint_drag_start(0)
    sa2._move_endpoint_with_snap(0, sa2.mapFromScene(nw))   # 직접 한 번에 이동
    sa2._on_endpoint_drag_end(0)

    _assert_all_segments_axis_aligned(sa1._pts, "다중 프레임 왕복 후 경로가 직교여야 함")
    assert len(sa1._pts) == len(sa2._pts) and all(
        _close(x, y) for x, y in zip(sa1._pts, sa2._pts)), \
        ("다중 프레임 왕복 결과가 직접 이동과 달라짐(경로 이력에 오염됨)", sa1._pts, sa2._pts)




def test_diamond_auto_route_uses_axis_forced_normal():
    # [실사용 버그 2026-07-29 — 근본원인 재확인] _shape_ports만 고치면 화살표를 새로 스냅해
    # 그릴 때는 맞는데, build_elbow/reroute(자동 라우팅 — 가장 흔한 경로)는 _bound_normal_scene을
    # 통해 매번 법선을 다시 계산하고 그건 _nearest_border를 직접 썼다. 보정을 _nearest_border
    # 자체로 옮겨야 두 경로(포트 목록·실제 라우팅) 모두 일관되게 고쳐진다.
    w = CanvasWindow()
    dia = _SymbolItem("decision", QRectF(0, 0, 185, 106))
    dia.setFlags(dia.GraphicsItemFlag.ItemIsSelectable | dia.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(dia)
    r = _mk_rect(w._scene, w.make_pen(), 500, 0, 100, 60)
    e_port = _shape_ports(dia)[1][0]   # 마름모 E 꼭짓점 — 좌우 꼭짓점이라 수평 이탈이어야 함
    sa = _PolyArrowItem(QColor("#ff0000ff"), 3, True)
    sa.set_points(e_port, QPointF(500, 30))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, dia, dia.mapFromScene(e_port))
    sa.set_bound(1, r, r.mapFromScene(QPointF(500, 30)))
    sa._auto_route = True; sa.build_elbow()

    n = sa._bound_normal_scene(0)
    assert _close(n, QPointF(1.0, 0.0)), ("E 꼭짓점 법선이 수평이어야 함", n)
    p0, p1 = sa._pts[0], sa._pts[1]
    assert abs(p0.y() - p1.y()) < 1e-6, ("E 꼭짓점 첫 구간은 수평이어야 하는데 수직으로 나옴", p0, p1)

    r.setPos(QPointF(0, 300)); sa.reroute()   # 도형 이동 후 reroute도 같은 보정을 써야 함
    p0, p1 = sa._pts[0], sa._pts[1]
    assert abs(p0.y() - p1.y()) < 1e-6, ("이동 후 reroute도 첫 구간이 수평이어야 함", p0, p1)




def test_sarrow_draw_between_shapes_auto_routes():
    # [Stage1] 드래그로 양끝을 도형 테두리에 붙이면 확정 시 자동 직교 엘보로 전환.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)          # 우측 (100,30)
    _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)      # 좌측 (300,230)
    view = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    press(QPointF(100, 30)); drag_move(QPointF(300, 230)); release(QPointF(300, 230))
    sa = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)][0]
    last = len(sa._pts) - 1
    assert sa._bound(0) is not None and sa._bound(last) is not None
    assert sa._auto_route is True
    assert len(sa._pts) == 4, [(round(p.x()), round(p.y())) for p in sa._pts]

    # .ecad 왕복 — auto_route 상태 보존
    from PyQt6.QtWidgets import QGraphicsScene
    path = os.path.join(_TMP, "sa_autoroute.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene(); load_document(sc2, path)
    a2 = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)][0]
    assert a2._auto_route is True




def test_route_ortho_pure():
    # [Stage2 → 2026-07-30 stub-out 수정] _route_ortho 순수함수 — 장애물 없으면 '법선 스텁 +
    # Stage1'(raw _ortho_elbow가 아니라, 변 타기 방지를 위해 먼저 스텁을 낸 뒤의 엘보) 그대로,
    # 있으면 관통 없는 경로 선택.
    from easycad.canvas.annotator_core import (
        _route_ortho, _ortho_elbow, _path_hits_rects, _normal_stub)
    P = QPointF
    s, e = P(100, 30), P(300, 230)
    ns, ne = P(1, 0), P(-1, 0)   # 양끝 수평 → Stage1은 H-V-H(x=200)
    clearance = 12.0

    def expected_clean():
        s2 = _normal_stub(s, ns, clearance)
        e2 = _normal_stub(e, ne, clearance)
        return [s2] + _ortho_elbow(s2, e2, ns, ne) + [e2]

    # (1) 장애물 없음 → 스텁+Stage1
    assert _route_ortho(s, e, ns, ne, [], clearance) == expected_clean()
    # (2) 수직 채널(x=200) 위에 장애물 → 우회 경로가 그 사각형을 관통하지 않음
    obs = QRectF(180, 110, 40, 40)   # x180..220, y110..150 — 채널 x=200 가로막음
    mids = _route_ortho(s, e, ns, ne, [obs], clearance)
    assert not _path_hits_rects([s] + mids + [e], [obs]), mids
    # 우회는 스텁+Stage1과 달라야 함(관통했으므로 대체됨)
    assert mids != expected_clean()
    # (3) 장애물이 경로에서 비켜 있으면(멀리) 스텁+Stage1 유지
    far = QRectF(1000, 1000, 40, 40)
    assert _route_ortho(s, e, ns, ne, [far], clearance) == expected_clean()




def test_route_ortho_astar_dense():
    # [Stage2 승격] Hanan 그리드 A* — 엇갈린 장애물 벽(단순 후보로는 못 뚫는 밀집 배치)에서도
    #   관통 0 우회로 보장. 직교성·끝점 보존·실제 우회(Stage1 관통) 함께 검증.
    from easycad.canvas.annotator_core import _route_ortho, _ortho_elbow, _path_hits_rects
    P = QPointF
    c = 12.0
    s, e = P(0, 0), P(300, 0)
    ns, ne = P(1, 0), P(-1, 0)          # 양끝 수평 → Stage1은 y=0 직선(같은 y)
    # y=0 선을 엇갈려 막는 세 기둥 — 좁은 세로 틈으로만 통과 가능(밀집).
    obs = [QRectF(80, -50, 40, 60),     # x80..120,  y-50..10
           QRectF(160, -10, 40, 60),    # x160..200, y-10..50
           QRectF(240, -50, 40, 60)]    # x240..280, y-50..10
    infl = [r.adjusted(-c, -c, c, c) for r in obs]

    # 전제: Stage1 직선은 세 기둥을 관통한다(우회가 실제로 필요한 밀집 상황).
    pref = _ortho_elbow(s, e, ns, ne)
    assert _path_hits_rects([s] + pref + [e], infl), "테스트 전제: Stage1이 관통해야 함"

    mids = _route_ortho(s, e, ns, ne, obs, c)
    full = [s] + mids + [e]
    # (a) 관통 0 — 팽창 장애물에도 안 걸림(핵심 보장)
    assert not _path_hits_rects(full, infl), (mids, "관통 발생")
    # (b) 원본 장애물에도 당연히 관통 0
    assert not _path_hits_rects(full, obs), mids
    # (c) 전 구간 직교(수평 또는 수직)
    for a, b in zip(full, full[1:]):
        assert abs(a.x() - b.x()) < 1e-6 or abs(a.y() - b.y()) < 1e-6, (a, b)
    # (d) 끝점 보존
    assert _close(full[0], s) and _close(full[-1], e), full
    # (e) 실제로 우회했다(Stage1과 다름)
    assert mids != pref




def test_route_ortho_fast_skips_ladder_when_base_already_clean():
    """[성능 최적화 2026-08-11] fast=True는 base(첫 유효 후보)가 이미 결함 없을 때만
    클리어런스 사다리("혹 감소" 폴리시 탐색)를 건너뛴다 — 사다리가 어차피 base보다 나은
    후보를 못 찾는 상황이므로 fast=True/False 결과가 완전히 같아야 한다(단순 조기 반환이라
    다른 경로가 나오면 회귀)."""
    from easycad.canvas.annotator_core import _route_ortho
    P = QPointF
    s, e = P(0, 0), P(300, 0)
    ns, ne = P(1, 0), P(-1, 0)
    obs = [QRectF(80, -50, 40, 60), QRectF(160, -10, 40, 60), QRectF(240, -50, 40, 60)]
    slow = _route_ortho(s, e, ns, ne, obs, 12.0)
    fast = _route_ortho(s, e, ns, ne, obs, 12.0, fast=True)
    assert fast == slow, (fast, slow)


def test_route_ortho_fast_never_returns_a_hitting_base():
    """[성능 최적화 2026-08-11] fast=True 경로가 관통하는 base를 그대로 반환하지 않는지
    회귀 방지(방어적 체크, `_route_ortho`의 "2026-08-11 방어적 강화" 주석 참조). ⚠ 이
    구체적 장애물 배치가 "base가 conn_clear 첫 시도에서 이미 결함 없이 확정되는" 흔한
    경로와 "첫 시도가 전부 실패해 사다리의 좁은 rung까지 가야 하는" 드문 경로 중 어느 쪽을
    타는지는 확인 안 됨(A* 코리도 패딩이 400+ 단위로 넉넉해, 후자를 합성 장애물로 안정적으로
    재현하지 못했다 — 실제 그룹 드래그 재현도 마찬가지). 그래도 어느 경로를 타든 "fast=True
    결과가 실제 장애물을 관통하면 안 된다"는 불변조건 자체는 항상 성립해야 하므로, 이 밀집
    배치로 그 불변조건만 고정해 둔다."""
    from easycad.canvas.annotator_core import _route_ortho, _path_hits_rects
    P = QPointF
    s, e = P(0, 0), P(300, 0)
    ns, ne = P(1, 0), P(-1, 0)
    obs = [QRectF(80, -50, 30, 55), QRectF(150, -5, 30, 55), QRectF(220, -50, 30, 55)]
    infl = [r.adjusted(-12.0, -12.0, 12.0, 12.0) for r in obs]

    fast_mids = _route_ortho(s, e, ns, ne, obs, 12.0, fast=True)
    full = [s] + fast_mids + [e]
    assert not _path_hits_rects(full, infl), (fast_mids, "fast=True가 관통 경로를 반환함")
    assert not _path_hits_rects(full, obs), fast_mids




def test_route_ortho_obstacle_flush_against_connected_shape_no_penetration():
    """[§8 항목19 F1 수정, 2026-08-14] 제3자 장애물이 연결 도형(시작쪽) 바로 옆에 밀착하면
    스텁 이탈점이 그 장애물의 팽창 사각형 안에 갇혀(반대편은 도형 자신의 몸통이라 격자선이
    없음) 클리어런스 사다리 4단이 전부 실패하고 관통 preferred로 폴백하던 버그
    (`docs/route_review_2026-08.md` 3단계 F1, 실제 KBS 도면에도 동일 메커니즘으로 존재
    확인). 간격을 0~10유닛(1차 트랩)·30유닛(반대쪽 도형 쪽 2차 트랩)으로 스윕해 둘 다
    더 이상 관통하지 않는지 확인한다."""
    from easycad.canvas.annotator_core import _route_ortho, _path_hits_rects
    P = QPointF
    s, e = P(-1940, -1970), P(-1880, -1970)
    ns, ne = P(1.0, 0.0), P(-1.0, 0.0)
    a_rect = QRectF(-2000, -2000, 60, 60)
    b_rect = QRectF(-1880, -2000, 60, 60)
    for gap in (0.0, 5.0, 10.0, 30.0):
        wall = QRectF(-1940 + gap, -2300, 20, 660)
        mids = _route_ortho(s, e, ns, ne, [wall], 12.0, conn_rects=(a_rect, b_rect))
        full = [s] + mids + [e]
        assert not _path_hits_rects(full, [wall]), (gap, mids, "관통 발생")
        assert _close(full[0], s) and _close(full[-1], e), (gap, full)


def test_sarrow_routes_around_obstacle():
    # [Stage2] 양끝 도형 사이 세 번째 도형이 경로를 가로막으면 우회 라우팅 / 장애물 이동 시 재라우팅 /
    #          양끝 바인딩 도형은 장애물에서 제외.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)       # 우측 (100,30), 법선 +x
    b = _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)   # 좌측 (300,230), 법선 -x
    c = _mk_rect(w._scene, w.make_pen(), 700, 700, 60, 60)    # 처음엔 경로 밖(멀리)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(300, 230))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30)); sa.set_bound(1, b, QPointF(300, 230))
    sa._auto_route = True

    # 바인딩 도형(a,b)은 장애물에서 제외 — c만 장애물
    obst = sa._obstacle_rects()
    assert len(obst) == 1, obst

    # (1) 장애물이 경로 밖 → Stage1 H-V-H(x=200) 그대로
    sa.build_elbow()
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp) == 4 and _close(sp[1], QPointF(200, 30)) and _close(sp[2], QPointF(200, 230)), sp

    # (2) 장애물을 수직 채널(x=200) 위로 이동 → reroute가 우회 경로로 재계산 → c 관통 안 함
    c.setPos(QPointF(-520, -580))    # 700-520=180 → x180..240, 700-580=120 → y120..180 (채널 가로막음)
    w._on_scene_changed(None)
    from easycad.canvas.annotator_core import _path_hits_rects
    c_rect = c.mapRectToScene(c.rect())
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert _close(sp[0], QPointF(100, 30)) and _close(sp[-1], QPointF(300, 230)), sp
    assert not _path_hits_rects(sp, [c_rect]), (sp, c_rect)
    assert len(sp) > 2   # 여전히 직교 엘보(≥1 모서리)

    # (3) 장애물을 다시 치우면 Stage1로 복귀(우회 해제) — 무변경 가드가 되먹임 없이 안정
    c.setPos(QPointF(0, 0))          # 다시 (700,700) 멀리
    w._on_scene_changed(None)
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp) == 4 and _close(sp[1], QPointF(200, 30)) and _close(sp[2], QPointF(200, 230)), sp




def test_sarrow_avoids_reenter_connected_shape():
    # [M4-4 ⓐ] 연결 도형 재진입 회피. A 우측(+x)에서 출발했는데 타깃 B가 왼쪽/아래라 preferred
    # 엘보의 첫 세그먼트가 A 몸통으로 되돌아 들어가는(재진입) 배치 → 라우터가 A를 우회해야 한다.
    from easycad.canvas.annotator_core import _path_hits_rects, _route_ortho
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)      # 우측 (100,30), 법선 +x
    b = _mk_rect(w._scene, w.make_pen(), 20, 200, 100, 60)   # 상단 (70,200), 법선 -y (A의 왼쪽 아래)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(70, 200))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30)); sa.set_bound(1, b, QPointF(70, 200))
    sa._auto_route = True

    a_rect = a.mapRectToScene(a.rect())
    b_rect = b.mapRectToScene(b.rect())
    ns = sa._bound_normal_scene(0); ne = sa._bound_normal_scene(1)

    # 전제 확인: 회피 없는 preferred 엘보는 실제로 A로 재진입한다(테스트가 유의미하려면).
    from easycad.canvas.annotator_core import _ortho_elbow
    s0, e0 = QPointF(100, 30), QPointF(70, 200)
    pref = [s0] + _ortho_elbow(s0, e0, ns, ne) + [e0]
    assert _path_hits_rects(pref, [a_rect]), ("preferred가 재진입 안 함 — 배치 재설계 필요", pref)

    # 수정된 라우터: A를 우회해 재진입하지 않는다(부착부 정상 접촉은 stub 바깥이라 통과).
    sa.build_elbow()
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert _close(sp[0], QPointF(100, 30)) and _close(sp[-1], QPointF(70, 200)), sp
    assert not _path_hits_rects(sp, [a_rect]), ("A 재진입", sp)
    assert not _path_hits_rects(sp, [b_rect]), ("B 관통", sp)

    # 보수성(무회귀) 확인: 재진입이 없던 깔끔한 배치는 A* 우회가 안 낀다 — conn 유무는
    # [2026-07-30 stub-out 수정] 이제 스텁 거리(own-rect 팽창 이스케이프 vs flat clearance)
    # 만 바꾼다(경로가 통째로 달라지는 회귀가 아님 — 아래서 그 스텁 공식과 정확히 일치하는지 확인).
    #   A 우측(+x) → B 좌측(-x), 같은 y → 직선.
    from easycad.canvas.annotator_core import _normal_stub, _CONN_CLEAR_MULT
    s1, e1 = QPointF(100, 30), QPointF(300, 30)
    ns1, ne1 = QPointF(1, 0), QPointF(-1, 0)
    m_no_conn = _route_ortho(s1, e1, ns1, ne1, [], 12.0)
    s2 = _normal_stub(s1, ns1, 12.0)
    e2 = _normal_stub(e1, ne1, 12.0)
    assert m_no_conn == [s2] + _ortho_elbow(s2, e2, ns1, ne1) + [e2], m_no_conn

    b2_rect = QRectF(300, 0, 100, 60)
    m_conn = _route_ortho(s1, e1, ns1, ne1, [], 12.0, conn_rects=[a_rect, b2_rect])
    cc = 12.0 * _CONN_CLEAR_MULT
    s3 = _normal_stub(s1, ns1, cc, a_rect.adjusted(-cc, -cc, cc, cc))
    e3 = _normal_stub(e1, ne1, cc, b2_rect.adjusted(-cc, -cc, cc, cc))
    assert m_conn == [s3] + _ortho_elbow(s3, e3, ns1, ne1) + [e3], m_conn




def test_sarrow_live_ortho_preview():
    # [화살표 그리기 라이브 직각] 드래그 미리보기가 직선이 아니라 직각 엘보를 만든다(첫 클릭부터 직각).
    w = CanvasWindow()
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    w._scene.addItem(sa)
    sa.set_points(QPointF(0, 0), QPointF(0, 0))
    sa.set_ortho_preview(QPointF(0, 0), QPointF(200, 120))
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp) >= 3, ("직선이 아니라 직각 엘보여야", sp)
    for i in range(len(sp) - 1):     # 모든 세그먼트가 수평/수직(직각)
        a, b = sp[i], sp[i + 1]
        assert abs(a.x() - b.x()) < 1e-6 or abs(a.y() - b.y()) < 1e-6, ("대각 세그먼트", a, b)
    assert _close(sp[0], QPointF(0, 0)) and _close(sp[-1], QPointF(200, 120)), sp
    # 릴리스 정리 시뮬: 2점으로 되돌리면 build_elbow가 정상 자동라우팅(len==2 경로) 가능해야 한다.
    sa.set_points(QPointF(sa._pts[0]), QPointF(sa._pts[-1]))
    assert len(sa._pts) == 2, sa._pts




def test_sarrow_live_preview_avoids_reenter():
    # [화살표 그리기 라이브 직각] 드래그 미리보기(시작만 바인딩)가 이미 회피 경로 — 클릭 놓기 전에
    # 도형을 관통했다가 릴리스에 튀지 않는다(preview==release). 사용자 실조건 피드백 2026-07-24.
    from easycad.canvas.annotator_core import _path_hits_rects, _ortho_elbow
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)      # 우측 (100,30), 법선 +x
    b = _mk_rect(w._scene, w.make_pen(), 20, 200, 100, 60)   # 타깃(왼쪽 아래) — 재진입 유발
    prev = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    w._scene.addItem(prev)
    prev.set_points(QPointF(100, 30), QPointF(100, 30))
    prev.set_bound(0, a, QPointF(100, 30))                   # 드래그 상태 = 시작만 바인딩
    ns = prev._bound_normal_scene(0)
    # 전제: 단순 엘보라면 A를 관통(테스트 유의미성)
    s0, e0 = QPointF(100, 30), QPointF(70, 200)
    assert _path_hits_rects([s0] + _ortho_elbow(s0, e0, ns, None) + [e0],
                            [a.mapRectToScene(a.rect())]), "단순 엘보가 재진입 안 함"
    # 미리보기(커서=B 상단점, tip이 B에 스냅 → 라이브 바인딩)는 이미 A를 우회
    prev.set_ortho_preview(s0, e0, b)
    pv = [prev.mapToScene(p) for p in prev._pts]
    assert not _path_hits_rects(pv, [a.mapRectToScene(a.rect())]), ("미리보기가 A 관통", pv)




def test_route_hint_create_and_persist():
    # [경유지 힌트(2f)] 중간정점을 경로 밖으로 끌면 힌트로 커밋 — 자동라우팅 유지·직교·끝점보존,
    #   경로가 힌트를 통과, .ecad 왕복에 힌트 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    from easycad.canvas.annotator_core import _path_hits_rects
    w = CanvasWindow()
    a, b, sa = _hint_arrow(w)
    sp0 = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp0) == 4 and _close(sp0[1], QPointF(250, 30))   # Stage1 H-V-H(x=250)

    # 상단 수평선 위 중간정점(250,30)을 위로(경로 밖) 끌기 → 힌트 (250,-40)
    _drag_vertex(sa, 1, QPointF(250, -40))
    assert sa._auto_route is True                       # 자동 유지(freeze 아님)
    assert len(sa._route_hints) == 1                    # 힌트 1개 생성
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert _close(sp[0], QPointF(100, 30)) and _close(sp[-1], QPointF(400, 230))  # 끝점 보존
    assert any(_close(p, QPointF(250, -40)) for p in sp)  # 경로가 힌트를 통과
    for u, v in zip(sp, sp[1:]):                        # 전 구간 직교
        assert abs(u.x() - v.x()) < 1e-6 or abs(u.y() - v.y()) < 1e-6, (u, v)

    # .ecad 왕복 — 힌트 보존
    path = os.path.join(_TMP, "hint.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene(); load_document(sc2, path)
    sa2 = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)][0]
    assert len(sa2._route_hints) == 1
    assert _close(sa2._route_hints[0], sa._route_hints[0])




def test_route_hint_follows_shape_move():
    # [경유지 힌트(2f)] 힌트는 끝점 중점 기준 상대좌표 — 도형을 옮기면 힌트도 함께 평행이동해
    #   경로가 계속 (이동한) 힌트를 지난다. 저장값(오프셋)은 불변.
    w = CanvasWindow()
    a, b, sa = _hint_arrow(w)
    _drag_vertex(sa, 1, QPointF(250, -40))
    off = QPointF(sa._route_hints[0])                  # 상대 오프셋(불변이어야)

    b.setPos(QPointF(0, 100))                           # 도착 도형 아래로 100 이동
    w._on_scene_changed(None)                           # reroute → 힌트 유지 재라우팅
    assert _close(sa._route_hints[0], off)              # 오프셋 저장값 불변
    mid = QPointF((100 + 400) / 2, (30 + 330) / 2)      # 새 끝점 중점
    hint_scene = QPointF(mid.x() + off.x(), mid.y() + off.y())  # (250,10)
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert _close(sp[-1], QPointF(400, 330))            # 끝점이 도형 추종
    assert any(_close(p, hint_scene) for p in sp), (sp, hint_scene)  # 경로가 이동한 힌트 통과




def test_route_hint_remove_and_manual_clear():
    # [경유지 힌트(2f)] 힌트를 순수경로 근처로 되끌면 제거(순수 자동 복귀) / 드래그 중 가드로
    #   라우터가 정점을 덮어쓰지 않음 / waypoint 삽입(수동 전환)은 힌트를 폐기.
    w = CanvasWindow()
    a, b, sa = _hint_arrow(w)
    _drag_vertex(sa, 1, QPointF(250, -40))
    assert len(sa._route_hints) == 1

    # (가드) 힌트 드래그 중엔 build_elbow가 정점을 덮어쓰지 않는다
    sa._hint_dragging = True
    before = [QPointF(p) for p in sa._pts]
    assert sa.build_elbow() is False
    assert all(_close(p, q) for p, q in zip(sa._pts, before))
    sa._hint_dragging = False

    # (제거) 힌트 정점을 순수경로(Stage1 세로선 x=250) 위로 되끌기 → 힌트 삭제 → Stage1 복귀
    hi = _idx_near(sa, QPointF(250, -40))
    _drag_vertex(sa, hi, QPointF(250, 80))
    assert len(sa._route_hints) == 0
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp) == 4 and _close(sp[1], QPointF(250, 30))   # 순수 Stage1 H-V-H

    # (수동 전환) 힌트 재생성 후 waypoint 삽입 → auto 해제 + 힌트 폐기
    _drag_vertex(sa, 1, QPointF(250, -40))
    assert len(sa._route_hints) == 1
    sa.insert_vertex(0, QPointF(150, 0))
    assert sa._auto_route is False and len(sa._route_hints) == 0




def test_route_hint_never_accumulates():
    # [경유지 힌트(2f) — 2026-07-20 GUI 실측 회귀] 힌트가 있는 상태에서 라우터가 만든(힌트가
    #   아닌) 다른 중간 꺾임점을 반복해서 잡아 옮기면, 매번 별개 힌트로 추가돼 계단식으로
    #   지저분해지던 버그. 몇 번을 다시 잡아도 힌트는 항상 1개 이하여야 하고(누적 금지),
    #   최종 정점 개수도 '단일 경유 힌트' 경로의 상한(끝점 2 + 힌트 1 + 구간당 엘보 최대 2×2구간 = 7)
    #   을 넘지 않는다.
    w = CanvasWindow()
    a, b, sa = _hint_arrow(w)

    _drag_vertex(sa, 1, QPointF(250, -40))
    assert len(sa._route_hints) == 1

    # 이제 라우터가 새로 만든(힌트 아닌) 다른 중간 정점을 골라 또 옮긴다 — 예전엔 이게 추가 힌트였다.
    other_idx = None
    hint_scene = sa._hint_to_scene(sa._route_hints[0])
    for i in range(1, len(sa._pts) - 1):
        if not _close(sa.mapToScene(sa._pts[i]), hint_scene):
            other_idx = i
            break
    assert other_idx is not None, "테스트 전제: 힌트 아닌 다른 중간 정점이 있어야 함"
    _drag_vertex(sa, other_idx, QPointF(350, 260))

    assert len(sa._route_hints) <= 1, sa._route_hints   # 누적 금지 — 항상 최대 1개
    assert len(sa._pts) <= 7, [(round(p.x()), round(p.y())) for p in sa._pts]

    # 반복해서 여러 번 더 잡아 옮겨도 마찬가지(계단식 증가 없음)
    for target in (QPointF(260, -60), QPointF(300, 260), QPointF(220, -20)):
        idx = 1 if len(sa._pts) > 2 else None
        if idx is None:
            break
        _drag_vertex(sa, idx, target)
        assert len(sa._route_hints) <= 1, sa._route_hints
        assert len(sa._pts) <= 7, [(round(p.x()), round(p.y())) for p in sa._pts]




# --- 드래그 중 재라우팅 지연(성능계획 2-B/2-F, 2026-08-15) ------------------

def _two_boxes_with_arrow():
    """도형 2개 + 그 사이 자동라우팅 화살표 1개. 세 번째 도형은 장애물로 둔다."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=500, y=400, ww=120, hh=72)
    arrow = _PolyArrowItem(QColor("#333333"), 2.0, True)
    arrow._pts = [QPointF(60, 72), QPointF(560, 400)]
    arrow._auto_route = True
    w._scene.addItem(arrow)
    arrow.set_bound(0, a, a.mapFromScene(QPointF(60, 72)))
    arrow.set_bound(len(arrow._pts) - 1, b, b.mapFromScene(QPointF(560, 400)))
    w._on_scene_changed(None)
    return w, a, b, arrow


def test_reroute_is_immediate_and_accurate_during_drag():
    """[실시간 재라우팅 실험, 2026-08-19] 사용자 요청으로 2-B(드래그 중 A* 정지)를
    비활성화했다 — 드래그 중에도 매 프레임 정확히 재라우팅되고, 더 이상 미룰 빚
    (`_deferred_arrows`)이 쌓이지 않는다(대가는 `docs/perf_plan_500_1000.md` §4 2-B 참조)."""
    w, a, b, arrow = _two_boxes_with_arrow()
    a.setSelected(True)

    w._view._move_active = True          # 드래그 세션 시작
    a.setPos(a.pos() + QPointF(140, 90))
    w._on_scene_changed(None)
    assert not w._deferred_arrows, "드래그 중인데 재라우팅이 여전히 미뤄지고 있다"

    # 끝점은 드래그 중에도 이미 도형을 따라갔어야 한다(화살표가 떨어져 보이면 안 됨).
    tgt = arrow.mapFromScene(a.mapToScene(arrow._bind_pt(0)))
    assert abs(arrow._pts[0].x() - tgt.x()) < 1e-6
    assert abs(arrow._pts[0].y() - tgt.y()) < 1e-6

    w._view._move_active = False         # 놓기 — flush는 이제 미룬 게 없어 no-op이어야 한다
    w.flush_deferred_reroute()
    assert not w._deferred_arrows


def test_deferred_reroute_final_path_matches_undeferred():
    """같은 이동을 '매 프레임 재라우팅'과 '미뤘다 놓기'로 각각 했을 때 최종 경로가 동일해야 한다.
    이게 깨지면 2-B는 성능이 아니라 그림을 바꾼 것이다."""
    def run(defer):
        w, a, b, arrow = _two_boxes_with_arrow()
        a.setSelected(True)
        w._view._move_active = bool(defer)
        for _ in range(5):
            a.setPos(a.pos() + QPointF(37, 23))
            w._on_scene_changed(None)
        w._view._move_active = False
        w.flush_deferred_reroute()
        return [(round(p.x(), 6), round(p.y(), 6)) for p in arrow._pts]

    assert run(defer=False) == run(defer=True)


def test_flush_is_noop_without_deferral():
    """드래그가 아닌 평범한 조작 뒤엔 flush가 아무 일도 하지 않아야 한다 —
    무조건 전체 재라우팅을 돌면 클릭 한 번에 1000개 문서 기준 수백 ms를 물게 된다."""
    w, a, b, arrow = _two_boxes_with_arrow()
    a.setPos(a.pos() + QPointF(50, 50))
    w._on_scene_changed(None)                 # 드래그 세션 아님 → 즉시 라우팅
    assert not w._deferred_arrows
    before = [(p.x(), p.y()) for p in arrow._pts]
    w.flush_deferred_reroute()
    assert [(p.x(), p.y()) for p in arrow._pts] == before


# --- 씬 전체 평행이동이면 라우팅을 건너뛴다(실사용 버그 2026-08-15) ---------
# Ctrl+A 후 드래그하면 화살표까지 함께 선택돼 Qt가 통째로 옮긴다 — 상대 기하가 하나도
# 안 바뀌는데도 500개를 전부 '미룬 빚'으로 쌓고 놓는 순간 A*를 500번 돌려 실화면 5초를
# 멈췄다(실측 2249ms). 반대로 도형만 옮기고 화살표는 제자리면 끝점이 따라가야 하므로
# 건너뛰면 안 된다 — 두 경우를 정확히 갈라야 한다.

def _scene_all_bound(w=None):
    w = w or CanvasWindow()
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


def test_uniform_translation_skips_routing_and_defers_nothing():
    """Ctrl+A 드래그 — 도형·화살표가 전부 같은 델타로 움직이면 미룰 빚이 0이어야 한다."""
    w, a, b, arrow = _scene_all_bound()
    for it in (a, b, arrow):
        it.setSelected(True)
    w._view._move_active = True

    d = QPointF(37, 23)
    for it in (a, b, arrow):
        it.setPos(it.pos() + d)
    w._on_scene_changed(None)

    assert w._uniform_translation is True, "전체 평행이동인데 uniform으로 판정 안 됨"
    assert not w._deferred_arrows, "상대 기하가 안 바뀌었는데 재라우팅을 빚으로 쌓았다"


def test_partial_move_is_not_uniform_and_still_reroutes():
    """도형 하나만 옮기면 상대 기하가 바뀐 것 — uniform이 아니고 정상 처리돼야 한다."""
    w, a, b, arrow = _scene_all_bound()
    a.setSelected(True)
    w._view._move_active = True
    a.setPos(a.pos() + QPointF(60, 40))
    w._on_scene_changed(None)

    assert w._uniform_translation is False
    tgt = arrow.mapFromScene(a.mapToScene(arrow._bind_pt(0)))
    assert abs(arrow._pts[0].x() - tgt.x()) < 1e-6 and abs(arrow._pts[0].y() - tgt.y()) < 1e-6, \
        "부분 이동인데 화살표가 도형을 따라가지 않았다(재라우팅 안 됨)"


def test_shapes_move_without_arrow_still_follows():
    """도형은 전부 옮기고 화살표는 제자리(선택 안 됨) — uniform이어도 끝점이 따라와야 한다.
    여기서 건너뛰면 화살표가 도형에서 떨어져 남는다."""
    w, a, b, arrow = _scene_all_bound()
    a.setSelected(True); b.setSelected(True)      # 화살표는 선택 안 함
    before = QPointF(arrow._pts[0])

    d = QPointF(50, 30)
    a.setPos(a.pos() + d)
    b.setPos(b.pos() + d)
    w._on_scene_changed(None)                     # 드래그 세션 아님 — 즉시 라우팅

    after = arrow._pts[0]
    assert (abs(after.x() - before.x()) > 1e-6 or abs(after.y() - before.y()) > 1e-6), \
        "도형이 옮겨졌는데 화살표 끝점이 따라오지 않았다"


def test_arrow_stays_orthogonal_during_drag():
    """[실사용 보고 2026-08-15] 드래그 중에도 화살표가 직각을 유지해야 한다.

    2-B가 드래그 중 라우팅을 통째로 멈추자 끝점만 도형을 따라가고 중간 정점은 제자리에
    남아 경로가 비스듬히 일그러졌다("직선으로 바뀌었다가 다시 그려진다"). 이제 드래그
    중에는 A* 회피 대신 값싼 직각 엘보(`_apply_routing(cheap=True)`)로 모양만 유지하고,
    정확한 회피 경로는 손을 떼는 순간 복원한다."""
    w, a, b, arrow = _scene_all_bound()

    def diagonal_segments(pts):
        return [i for i in range(len(pts) - 1)
                if abs(pts[i + 1].x() - pts[i].x()) > 1e-6
                and abs(pts[i + 1].y() - pts[i].y()) > 1e-6]

    assert diagonal_segments(arrow._pts) == [], "드래그 전부터 비직각(테스트 전제 실패)"

    a.setSelected(True)
    w._view._move_active = True
    for _ in range(4):
        a.setPos(a.pos() + QPointF(40, 25))
        w._on_scene_changed(None)
    assert diagonal_segments(arrow._pts) == [], "드래그 중 경로가 비스듬해졌다"

    w._view._move_active = False
    w.flush_deferred_reroute()
    assert diagonal_segments(arrow._pts) == [], "놓은 뒤에도 비직각이 남았다"


def test_only_connected_arrows_reroute_not_bystanders():
    """[설계 변경 2026-08-15 「낙장불입」] 움직인 도형에 **붙어 있는** 화살표만 다시 그린다.

    예전엔 "경로 bbox가 변경영역과 겹치면" 전부 다시 그렸다(무관한 장애물이 끼어들면 알아서
    비켜가게 하려던 의도). 실측하니 도형 1개 이동에 재계산 13개 중 11개(85%)가 그 도형과
    아무 관계 없는 화살표였고, 동작도 이상했다 — 도형 하나를 옮겼는데 화면 반대편 화살표가
    제멋대로 모양이 바뀐다.

    ⚠ 결과(경로 좌표)가 아니라 **재계산 대상 집합**을 직접 검사한다. 좌표로 재면 우연히
    같은 경로가 나올 때 통과해버려 판정이 무디다(실제로 옛 코드에서도 통과했다)."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=500, y=0, ww=120, hh=72)
    c = _mk_pen_rect(w, x=0, y=400, ww=120, hh=72)
    d = _mk_pen_rect(w, x=500, y=400, ww=120, hh=72)

    def connect(src, dst):
        ar = _PolyArrowItem(QColor("#333333"), 2.0, True)
        sp = src.sceneBoundingRect().center()
        dp = dst.sceneBoundingRect().center()
        ar._pts = [sp, dp]
        ar._auto_route = True
        w._scene.addItem(ar)
        ar.set_bound(0, src, src.mapFromScene(sp))
        ar.set_bound(len(ar._pts) - 1, dst, dst.mapFromScene(dp))
        return ar

    mine = connect(a, b)          # 움직일 도형(a)에 붙은 화살표
    bystander = connect(c, d)     # a와 무관하지만 a가 지나갈 자리에 있는 화살표
    w._on_scene_changed(None)

    # [실시간 재라우팅 실험, 2026-08-19] `_deferred_arrows`는 더 이상 재계산 대상을 모아두지
    # 않는다(2-B 비활성화, 즉시 처리) — 대신 `reroute` 호출 자체를 직접 가로채 관찰한다.
    calls = []
    for it in (mine, bystander):
        orig = it.reroute
        def _make_wrapper(item, orig_fn):
            def _wrapper(*args, **kwargs):
                calls.append(item)
                return orig_fn(*args, **kwargs)
            return _wrapper
        it.reroute = _make_wrapper(it, orig)

    a.setSelected(True)
    w._view._move_active = True
    a.setPos(a.pos() + QPointF(120, 380))     # bystander 경로를 가로지르도록 크게 이동
    w._on_scene_changed([a.sceneBoundingRect()])

    assert mine in calls, "연결된 화살표가 재계산 대상에서 빠졌다"
    assert bystander not in calls, "무관한 화살표까지 재계산 대상에 들어갔다(낙장불입 위반)"




# ---------------------------------------------------------------------------
# [다중 라벨 2026-08-21] 화살표 하나에 라벨 여러 개 — deep-interview로 확정한 설계:
# 임의 위치·개수 제한 없음, 화살표 선 위 빈 자리 더블클릭=새 라벨, 라벨 클릭+Delete=그
# 하나만 삭제. 기존 단일-라벨 API(ensure_label/_label/_label_t/_label_off)는 전부
# "첫 번째 라벨" 하위호환으로 그대로 유지된다(위 기존 테스트 전부 무변경으로 통과).
# ---------------------------------------------------------------------------

def test_arrow_add_label_at_t_multiple_independent_positions():
    # add_label_at_t로 라벨을 두 개 붙이면 서로 다른 t를 각자 유지하고, 둘 다 살아있다.
    for cls in (_ArrowItem, _PolyArrowItem):
        w = CanvasWindow()
        ar = cls(QColor("#ff111111"), 4, True)
        ar.set_points(QPointF(0, 0), QPointF(200, 0))
        ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
        w._scene.addItem(ar)
        l1 = ar.add_label_at_t(0.2); l1.setPlainText("A"); ar._sync_label()
        l2 = ar.add_label_at_t(0.8); l2.setPlainText("B"); ar._sync_label()
        assert l1 is not l2
        assert {l.toPlainText() for l in ar._live_labels()} == {"A", "B"}
        assert abs(l1._conn_t - 0.2) < 1e-6 and abs(l2._conn_t - 0.8) < 1e-6
        # 하위호환: _label/_label_t는 첫 번째(생성 순서상 l1)를 가리킨다.
        assert ar._label is l1
        assert abs(ar._label_t - 0.2) < 1e-6
        # 서로 다른 앵커(경로 위 다른 지점)에 놓인다 — 겹치지 않음.
        a1, a2 = ar._label_anchor_for(l1), ar._label_anchor_for(l2)
        assert abs(a1.x() - a2.x()) > 50


def test_arrow_ensure_label_reuses_first_does_not_duplicate():
    # 기존 단일-라벨 API(ensure_label)는 여러 번 불러도 같은 라벨을 계속 반환한다
    # (다중 라벨을 만드는 건 add_label_at_t/add_label_at_scene_pos 뿐).
    ar = _PolyArrowItem(QColor("#ff111111"), 4, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0))
    w = CanvasWindow(); w._scene.addItem(ar)
    l1 = ar.ensure_label(); l1.setPlainText("only")
    l2 = ar.ensure_label()
    assert l1 is l2
    assert len(ar._live_labels()) == 1


def test_arrow_vertical_label_gap_is_symmetric_top_bottom():
    # [실사용 지적 2026-08-21] 세로선(위→아래) 위 라벨은 문서박스 전체가 아니라 실제 잉크
    # 구간만 갭으로 잡아야 위/아래 여백이 좌우 여백과 똑같이 pad만큼만 남는다 — 전에는
    # 폰트 줄간격 때문에 위쪽 여백이 아래쪽의 거의 2배였다(실측: ghjghj 기준 11px vs 6px).
    from easycad.canvas.annotator_core import _ink_vertical_span
    for cls in (_ArrowItem, _PolyArrowItem):
        ar = cls(QColor("#ff111111"), 4, True)
        ar.set_points(QPointF(0, 0), QPointF(0, 300))          # 순수 수직선
        w = CanvasWindow(); w._scene.addItem(ar)
        lbl = ar.ensure_label(); lbl.setPlainText("ghjghj"); ar._sync_label()
        gap = ar._label_gap_rects()[0]
        ink_top, ink_bot = _ink_vertical_span(lbl)
        pos = lbl.pos(); br = lbl._content_rect()
        top_ws = (pos.y() + br.y() + ink_top) - gap.top()
        bottom_ws = gap.bottom() - (pos.y() + br.y() + ink_bot)
        assert abs(top_ws - ar._LABEL_GAP_PAD) < 0.5
        assert abs(bottom_ws - ar._LABEL_GAP_PAD) < 0.5
        w._scene.removeItem(ar)


def test_arrow_multi_label_gap_rects_and_visible_path_has_two_gaps():
    # 라벨 2개 = 갭 사각형 2개, 폴리라인 시각 경로가 두 라벨 자리 모두에서 끊긴다.
    ar = _PolyArrowItem(QColor("#ff111111"), 4, True)
    ar.set_points(QPointF(0, 0), QPointF(300, 0))
    w = CanvasWindow(); w._scene.addItem(ar)
    assert ar._label_gap_rects() == []                     # 라벨 없음 = 갭 없음
    l1 = ar.add_label_at_t(0.2); l1.setPlainText("A"); ar._sync_label()
    l2 = ar.add_label_at_t(0.8); l2.setPlainText("B"); ar._sync_label()
    rects = ar._label_gap_rects()
    assert len(rects) == 2
    path = ar._visible_polyline_path()
    # 열린 폴리라인(면적 없음)이라 contains()는 못 쓴다 — 연속 구간(subpath)별 x범위로 확인.
    polys = path.toSubpathPolygons()
    assert len(polys) == 3, "라벨 2개가 만드는 갭 2개로 시각 경로가 3구간으로 끊겨야 함"
    covered = [(min(p.x() for p in poly), max(p.x() for p in poly)) for poly in polys]

    def _covered(x):
        return any(lo - 1e-6 <= x <= hi + 1e-6 for lo, hi in covered)

    # 두 라벨 중심 x좌표는 시각 경로가 지나지 않아야 한다(갭으로 비워짐).
    for lbl in (l1, l2):
        cx = lbl.pos().x() + lbl._content_rect().center().x()
        assert not _covered(cx)
    # 라벨 사이(t=0.5 부근)는 여전히 그려진다.
    assert _covered(150)


def test_arrow_multi_label_delete_one_keeps_other():
    # 라벨 하나를 씬에서 제거해도(=선택+Delete와 동일한 결과) 나머지 라벨은 그대로 남는다.
    ar = _PolyArrowItem(QColor("#ff111111"), 4, True)
    ar.set_points(QPointF(0, 0), QPointF(200, 0))
    w = CanvasWindow(); w._scene.addItem(ar)
    l1 = ar.add_label_at_t(0.2); l1.setPlainText("A")
    l2 = ar.add_label_at_t(0.8); l2.setPlainText("B")
    w._scene.removeItem(l1)                                 # Delete키 경로가 하는 것과 동일
    assert ar._live_labels() == [l2]
    assert ar.has_label() and ar._label is l2


def test_arrow_multi_label_document_roundtrip():
    # .ecad 저장/로드로 라벨 2개(텍스트·색·폰트·t·off)가 모두 보존된다(새 "labels" 리스트 포맷).
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    ar = _PolyArrowItem(QColor("#ff111111"), 4, True)
    ar.set_points(QPointF(0, 0), QPointF(300, 0))
    sc.addItem(ar)
    l1 = ar.add_label_at_t(0.2); l1.setPlainText("Alpha"); l1.apply_color(QColor("#ff0000"))
    l2 = ar.add_label_at_t(0.8, off=10.0); l2.setPlainText("Beta"); l2.apply_font_size(20)
    ar._sync_label()
    d = item_to_dict(ar)
    assert "labels" in d and len(d["labels"]) == 2 and "label" not in d
    path = os.path.join(_TMP, "arrow_multi_label.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene(); load_document(sc2, path)
    ar2 = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)][0]
    texts = {l.toPlainText() for l in ar2._live_labels()}
    assert texts == {"Alpha", "Beta"}
    alpha = next(l for l in ar2._live_labels() if l.toPlainText() == "Alpha")
    beta = next(l for l in ar2._live_labels() if l.toPlainText() == "Beta")
    assert abs(alpha._conn_t - 0.2) < 1e-6
    assert abs(beta._conn_t - 0.8) < 1e-6 and abs(beta._conn_off - 10.0) < 1e-6
    assert beta.font().pointSize() == 20 or beta._base_pt == 20


def test_old_singular_label_format_still_loads_into_arrow():
    # [하위호환] 옛 파일 포맷(단수 "label" 키, "labels" 없음)도 화살표에 그대로 로드된다.
    from easycad.fileio.document import insert_items
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    d = {
        "type": "sarrow", "pos": [0, 0], "scale": 1.0, "rotation": 0.0, "z": 0.0,
        "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None,
        "pts": [[0, 0], [100, 0]], "color": "#ffff0000", "width": 2.0, "head": True,
        "style": 1, "auto_route": False, "routing": "ortho", "curve_r": 10.0,
        "route_hints": [],
        "label": {"text": "옛형식", "color": "#ffffffff", "font": 16, "bg": None,
                  "t": 0.35, "off": 5.0},
    }
    created = insert_items(sc, [d])
    assert len(created) == 1
    ar = created[0]
    assert ar.has_label() and ar._label.toPlainText() == "옛형식"
    assert abs(ar._label_t - 0.35) < 1e-6 and abs(ar._label_off - 5.0) < 1e-6


def test_begin_label_edit_on_empty_line_spot_creates_new_label_not_reuse():
    # [UI] 화살표 선 위 빈 자리를 더블클릭 = 그 자리에 새 라벨(기존 라벨 재편집 아님).
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    ar = _PolyArrowItem(QColor("#ff111111"), 4, True)
    ar.set_points(QPointF(0, 0), QPointF(200, 0))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    view = w._view

    view._begin_label_edit(ar, QPointF(30, 0))     # 첫 번째: 선 왼쪽 부근
    lbl1 = ar._live_labels()[-1]
    lbl1.setPlainText("First")
    lbl1.clearFocus()                              # focusOut → 편집 종료(빈 텍스트 아니므로 유지)

    view._begin_label_edit(ar, QPointF(170, 0))    # 두 번째: 선 오른쪽 부근 — 새 라벨이어야 함
    labels = ar._live_labels()
    assert len(labels) == 2, "두 번째 더블클릭이 새 라벨을 만들지 않고 기존 것을 재사용했다"
    lbl2 = labels[-1]
    assert lbl2 is not lbl1
    assert lbl2._conn_t > lbl1._conn_t             # 오른쪽에 놓인 라벨이 더 큰 t


def test_double_click_on_existing_label_reedits_same_one():
    # [UI] 이미 있는 라벨 자리를 더블클릭하면 새로 만들지 않고 그 라벨 자체가 편집모드로 들어간다
    # (Qt 히트테스트가 _labelable_at보다 먼저 라벨 자신에게 이벤트를 보낸다).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    ar = _PolyArrowItem(QColor("#ff111111"), 4, True)
    ar.set_points(QPointF(0, 0), QPointF(200, 0))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    view = w._view
    view._begin_label_edit(ar, QPointF(100, 0))
    lbl = ar._live_labels()[0]
    lbl.setPlainText("Solo")
    lbl.clearFocus()

    target = view._labelable_at(view.mapFromScene(lbl.mapToScene(lbl.boundingRect().center())))
    assert target is None, "라벨이 있는 자리인데 _labelable_at이 화살표를 돌려줘 새 라벨을 만들 위험"
    assert len(ar._live_labels()) == 1
