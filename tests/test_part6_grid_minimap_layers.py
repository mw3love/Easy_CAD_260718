"""그리드·미니맵·레이어·스타일복사·DXF/.ecad 통합

tests/test_easycad.py 2026-08-02 분할분. 실행: python tests/test_easycad.py (전체) 또는 pytest test_part6_grid_minimap_layers.py.
"""
from _shared import *  # noqa: F401,F403


def test_grid_snap_box_resize_corner_lands_on_grid():
    # [그리드] 코너 리사이즈 — 드래그한 코너가 격자 교차점에 정확히 놓인다(회전 0, key 무관).
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow()
    w.grid_enabled = True   # 기본값은 off(2026-08-11)이므로 이 테스트는 켠 상태를 명시
    for key in range(4):
        r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
        r._begin_box_geom()
        r._box_resize = ("corner", key)
        r._apply_box_resize(QPointF(133, 77))   # 격자 밖 → (140, 80)로 스냅
        pts = [r.rect().topLeft(), r.rect().topRight(),
               r.rect().bottomLeft(), r.rect().bottomRight()]
        assert any(_close(pt, QPointF(round(133 / _GRID_SPACING) * _GRID_SPACING,
                                      round(77 / _GRID_SPACING) * _GRID_SPACING)) for pt in pts)




def test_grid_snap_box_resize_edge_lands_on_grid():
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow()
    w.grid_enabled = True   # 기본값은 off(2026-08-11)이므로 이 테스트는 켠 상태를 명시
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    r._begin_box_geom()
    r._box_resize = ("edge", "r")
    r._apply_box_resize(QPointF(133, 10))
    assert abs(r.rect().right() - round(133 / _GRID_SPACING) * _GRID_SPACING) < 1e-6




def test_grid_snap_shape_creation():
    # [그리드] 네모를 격자 밖 지점으로 드래그해 그리면 결과 rect 모서리가 격자에 맞는다.
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow(); w.grid_enabled = True; w.show(); w.set_tool("rect"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    press(QPointF(3, 4))
    drag_move(QPointF(97, 66))
    release(QPointF(97, 66))
    items = [it for it in w._scene.items() if isinstance(it, _RectItem)]
    assert len(items) == 1
    it = items[0]
    tl = it.mapToScene(it.rect().topLeft())
    br = it.mapToScene(it.rect().bottomRight())
    for coord in (tl.x(), tl.y(), br.x(), br.y()):
        assert abs(coord % _GRID_SPACING) < 1e-6 or abs(coord % _GRID_SPACING - _GRID_SPACING) < 1e-6
    w.close()




def test_grid_snap_excluded_for_arrow_tool():
    # [그리드] 화살표류는 격자 스냅 대상에서 제외 — 테두리/포트 스냅이 항상 우선이어야 한다.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("arrow"); w._zoom_reset()
    view = w._view
    view._start = QPointF(3, 4)
    NO = Qt.KeyboardModifier.NoModifier
    vp = view.mapFromScene(QPointF(97, 61))
    e = QMouseEvent(QEvent.Type.MouseMove, QPointF(vp), QPointF(vp),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, NO)
    p = view._cur_point(e)
    assert p == QPointF(97, 61)
    w.close()




def test_grid_background_paints_without_error_when_visible():
    from PyQt6.QtGui import QPainter
    w = CanvasWindow(); w._zoom_reset()
    pm = QPixmap(200, 200); pm.fill()
    painter = QPainter(pm)
    w._view.drawBackground(painter, QRectF(0, 0, 200, 200))
    painter.end()




def test_grid_background_hidden_when_too_dense_or_disabled():
    # [그리드] 너무 촘촘(줌아웃)하거나 토글 꺼짐이면 조기 반환 — 두 경로 모두 예외 없이 완료.
    from easycad.canvas.annotator_core import _GRID_SPACING, _GRID_MIN_PX
    from PyQt6.QtGui import QPainter
    w = CanvasWindow()
    view = w._view
    scale = (_GRID_MIN_PX / _GRID_SPACING) * 0.5
    view.resetTransform(); view.scale(scale, scale)
    assert _GRID_SPACING * view._view_scale() < _GRID_MIN_PX
    pm = QPixmap(200, 200); pm.fill()
    painter = QPainter(pm)
    view.drawBackground(painter, QRectF(-2000, -2000, 4000, 4000))
    painter.end()

    view.resetTransform()
    w.grid_enabled = False
    painter2 = QPainter(pm)
    view.drawBackground(painter2, QRectF(0, 0, 200, 200))
    painter2.end()




def test_minimap_shares_scene_and_is_noninteractive():
    # [미니맵] 메인과 같은 QGraphicsScene을 공유(별도 캐시 없이 Qt 멀티뷰로 내용 자동반영) +
    # 자체 아이템 선택/드래그는 꺼서(setInteractive) 클릭이 항상 내비게이션으로만 쓰이게 한다.
    w = CanvasWindow()
    assert w._minimap.scene() is w._scene
    assert w._minimap.isInteractive() is False
    # [캔버스-퍼스트 레이아웃] 우측 QDockWidget 대신 우상단(속성 아래) 플로팅 카드.
    assert w._minimap_panel.parent() is w
    # [2026-08-01] 미니맵을 16:9로 넓혀 폭이 속성 패널과 달라졌다 — 둘 다 우측 정렬이므로
    # 왼쪽 x가 아니라 오른쪽 가장자리(x+width)가 같은 열임을 확인한다.
    mm_right = w._minimap_panel.pos().x() + w._minimap_panel.width()
    props_right = w._props_panel.pos().x() + w._props_panel.width()
    assert abs(mm_right - props_right) < 5   # 속성과 같은 우측 열
    assert w._minimap_panel.pos().y() > w._props_panel.pos().y()       # 속성 아래




def test_minimap_indicator_fixed_pixel_size_regardless_of_zoom():
    # [미니맵][사용자 피드백 2026-07-29] 인디케이터가 실제 가시 영역 비율대로 그려지면 메인 뷰를
    # 확대할수록 박스가 작아져(게임 미니맵과 다르게 동작) 클릭으로 위치 잡기가 불편하다는 지적 —
    # 종횡비는 유지하되 크기는 줌과 무관하게 고정(폭 _INDICATOR_PX 픽셀)이어야 한다.
    from easycad.canvas.annotator_core import _RectItem
    w = CanvasWindow(); w.resize(1200, 800); w.show()
    w._scene.addItem(_RectItem(QRectF(0, 0, 100, 60)))
    w._view.resetTransform(); w._view.centerOn(0, 0)
    px_w_1x = w._minimap._indicator_draw_rect().width() * w._minimap.transform().m11()
    w._view.scale(6.0, 6.0)
    px_w_6x = w._minimap._indicator_draw_rect().width() * w._minimap.transform().m11()
    assert abs(px_w_1x - px_w_6x) < 1.0
    assert abs(px_w_1x - w._minimap._INDICATOR_PX) < 1.0
    w.close()




def test_minimap_indicator_is_scene_coords_not_double_transformed():
    # [미니맵][실조건 버그 회귀] drawForeground의 painter는 이미 씬 좌표계로 매핑돼 있어
    # (offscreen 프로브로 실측 확인) 인디케이터도 씬 좌표를 그대로 써야 한다. 예전엔
    # mapFromScene으로 미니맵 '픽셀' 좌표로 한 번 더 바꾼 뒤 그 값을 그려 이중변환이었다 —
    # 씬 원점에서 멀리 팬한 뒤(사용자 실사용과 동일 조건) 인디케이터 씬 사각형이 실제로
    # 화면에 보이는 도형들을 포함해야 한다.
    from easycad.canvas.annotator_core import _RectItem
    w = CanvasWindow(); w.resize(1200, 800); w.show()
    it1 = _RectItem(QRectF(1080, 760, 180, 105)); it1.setPen(w.make_pen()); w._scene.addItem(it1)
    it2 = _RectItem(QRectF(1450, 885, 180, 120)); it2.setPen(w.make_pen()); w._scene.addItem(it2)
    w._view.resetTransform()
    w._view.centerOn(1300, 850)   # 원점에서 멀리 — 픽셀 스케일 값과 씬 좌표 값이 안 겹치는 영역
    indicator = w._minimap._indicator_scene_rect()
    items_bbox = w._scene.itemsBoundingRect()
    assert indicator.contains(items_bbox), (indicator, items_bbox)
    w.close()




def test_minimap_click_navigates_main_view():
    # [미니맵] 클릭한 지점이 메인 뷰의 새 중심이 된다.
    from PyQt6.QtCore import QPoint
    w = CanvasWindow(); w.resize(1200, 800); w.show()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    before = w._view.mapToScene(w._view.viewport().rect().center())
    tl = w._minimap.viewport().rect().topLeft()
    target_view_pos = QPoint(tl.x() + 5, tl.y() + 5)
    target_scene = w._minimap.mapToScene(target_view_pos)
    w._minimap._navigate_to(target_view_pos)
    after = w._view.mapToScene(w._view.viewport().rect().center())
    assert _close(after, target_scene, eps=2.0)
    assert not _close(after, before, eps=2.0)
    w.close()




def test_minimap_wheel_does_not_zoom():
    # [미니맵] 자체 줌 없음 — 휠은 항상 무시(전체 맞춤 유지가 목적).
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtCore import QPointF as _QPF, QPoint as _QP
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    mm = w._minimap
    before = mm.transform()
    ev = QWheelEvent(_QPF(10, 10), _QPF(10, 10), _QP(0, 0), _QP(0, 120),
                      Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                      Qt.ScrollPhase.NoScrollPhase, False)
    mm.wheelEvent(ev)
    assert mm.transform() == before




def test_minimap_refresh_hooked_to_zoom_and_resize():
    # [미니맵] scene.changed를 안 타는 순수 뷰 변환(줌·리사이즈)마다 명시적으로 갱신돼야 한다.
    w = CanvasWindow(); w.resize(1200, 800); w.show()
    calls = []
    w._minimap.viewport().update = lambda *a, **k: calls.append(1)
    w._on_wheel_zoom(120)
    assert len(calls) >= 1
    w._zoom_reset()
    assert len(calls) >= 2
    w._zoom_fit()
    assert len(calls) >= 3
    w.close()




def test_minimap_refit_empty_scene_noop():
    # [미니맵] 아이템 없는 씬에서도 예외 없이 완료(itemsBoundingRect가 빈 사각형).
    w = CanvasWindow()
    w._minimap._refit()




def test_minimap_bounds_cached_and_invalidated_by_scene_change():
    # [성능 조사 스파이크 2026-07-30] itemsBoundingRect()는 무거운 도면에서 비용이 커
    # (실측 ~1600아이템에 71ms) 매 paintEvent마다 재계산하면 휠줌·팬마다 그 비용을 문다.
    # scene.changed(콘텐츠 변경 시에만 발생 — 순수 뷰 변환인 줌/팬은 안 탐)로 dirty 플래그를
    # 걸어 캐시해야 한다.
    w = CanvasWindow()
    mm = w._minimap
    r1 = _mk_pen_rect(w, x=0, y=0, ww=50, hh=50)
    # addItem()의 scene.changed 방출은 비동기(이벤트 루프에 제어가 돌아갈 때 발행)라, 아직
    # 소비되기 전에 _refit()을 먼저 부르면 그 신호가 이후 processEvents()에서 뒤늦게 도착해
    # 아래 '줌은 dirty 안 켠다' 검증을 오염시킨다 — 먼저 비우고 나서 _refit()으로 소비한다.
    _app.processEvents()
    mm._refit()
    assert mm._bounds_dirty is False
    cached = mm._bounds_cache
    # 순수 뷰 변환(줌)은 scene.changed를 안 태우므로 dirty가 그대로 False 유지.
    w._on_wheel_zoom(1)
    _app.processEvents()
    assert mm._bounds_dirty is False
    # 아이템 이동(실제 콘텐츠 변경)은 scene.changed를 태워 dirty=True.
    # [Qt] scene.changed는 비동기 시그널(이벤트 루프에 제어가 돌아갈 때 발행) — processEvents 필요.
    r1.moveBy(500, 500)
    _app.processEvents()
    assert mm._bounds_dirty is True
    mm._refit()
    assert mm._bounds_dirty is False
    assert mm._bounds_cache != cached   # 재계산돼 새 bbox 반영




def test_minimap_refresh_hooked_to_viewport_resize_not_just_window():
    # [미니맵][실조건 버그] 사용자 GUI 확인: dock 스플리터를 드래그해 메인 뷰포트 크기가
    # 바뀌면(창 자체 크기는 그대로) CanvasWindow.resizeEvent가 안 불려 인디케이터가 갱신
    # 안 됐다. 원인 불문 항상 잡으려면 뷰포트 자체의 QResizeEvent를 잡아야 한다(eventFilter).
    from PyQt6.QtGui import QResizeEvent
    from PyQt6.QtCore import QSize
    w = CanvasWindow(); w.resize(1200, 800); w.show()
    calls = []
    w._minimap.viewport().update = lambda *a, **k: calls.append(1)
    ev = QResizeEvent(QSize(600, 800), QSize(872, 800))   # 창 resizeEvent 없이 뷰포트만 변경
    w.eventFilter(w._view.viewport(), ev)
    assert len(calls) >= 1
    w.close()




def test_style_copy_paste_pen_to_pen():
    # [스타일 복사] 색·두께·선스타일이 그대로 옮겨진다.
    from PyQt6.QtGui import QPen
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, width=5.0, color="#ff0000")
    a.setPen(QPen(QColor("#ff0000"), 5.0, Qt.PenStyle.DashLine))
    a.setSelected(True)
    w.copy_style_from_selection()
    assert w._style_clip is not None
    b = _mk_pen_rect(w, x=200, y=0, width=1.0, color="#000000")
    w._scene.clearSelection(); b.setSelected(True)
    w.paste_style_to_selection()
    assert b.pen().color().name() == "#ff0000"
    assert abs(b.pen().widthF() - 5.0) < 1e-6
    assert b.pen().style() == Qt.PenStyle.DashLine
    w.undo()
    assert abs(b.pen().widthF() - 1.0) < 1e-6




def test_style_copy_requires_single_selection():
    # [스타일 복사] 0개·2개 이상 선택 시 클립을 만들지 않는다(상태바 안내만).
    w = CanvasWindow()
    w.copy_style_from_selection()
    assert w._style_clip is None
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=100, y=0)
    a.setSelected(True); b.setSelected(True)
    w.copy_style_from_selection()
    assert w._style_clip is None




def test_style_paste_without_clip_noop():
    # [스타일 복사] 복사한 스타일이 없으면 붙여넣기는 조용히 무시(크래시·undo엔트리 없음).
    w = CanvasWindow()
    b = _mk_pen_rect(w, x=0, y=0, width=1.0); b.setSelected(True)
    before = len(w._undo)
    w.paste_style_to_selection()
    assert len(w._undo) == before
    assert abs(b.pen().widthF() - 1.0) < 1e-6




def test_style_copy_paste_cross_type_rect_to_arrow():
    # [스타일 복사] 타입이 달라도(네모→화살표) 색·두께·선스타일이 정규화돼 적용된다.
    from PyQt6.QtGui import QPen
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0)
    a.setPen(QPen(QColor("#00ff00"), 6.0, Qt.PenStyle.DotLine))
    a.setSelected(True)
    w.copy_style_from_selection()
    ar = _ArrowItem(QColor("#111111"), 2, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    w._scene.clearSelection(); ar.setSelected(True)
    w.paste_style_to_selection()
    assert ar._color.name() == "#00ff00"
    assert abs(ar._width - 6.0) < 1e-6
    assert ar._style == Qt.PenStyle.DotLine




def test_style_copy_excludes_text_content():
    # [스타일 복사] 텍스트 '내용'은 대상에 안 옮겨간다(서식만) — deep-interview 확정.
    a = _TextItem(QColor("#ff0000"))
    a.setPlainText("Hello")
    a.apply_font_size(30)
    b = _TextItem(QColor("#000000"))
    b.setPlainText("World")
    w = CanvasWindow()
    w._scene.addItem(a); w._scene.addItem(b)
    a.setSelected(True)
    w.copy_style_from_selection()
    w._scene.clearSelection(); b.setSelected(True)
    w.paste_style_to_selection()
    assert b.toPlainText() == "World"          # 내용 불변
    assert b.defaultTextColor().name() == "#ff0000"   # 서식은 옮겨감




def test_style_copy_paste_multi_target_single_undo():
    # [스타일 복사] 다중 대상 붙여넣기 — 전부 바뀌고 undo 한 번으로 전부 복원.
    from PyQt6.QtGui import QPen
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, width=7.0, color="#ff0000")
    a.setPen(QPen(QColor("#ff0000"), 7.0))
    a.setSelected(True)
    w.copy_style_from_selection()
    b = _mk_pen_rect(w, x=100, y=0, width=1.0)
    c = _mk_pen_rect(w, x=200, y=0, width=1.0)
    w._scene.clearSelection(); b.setSelected(True); c.setSelected(True)
    before_undo = len(w._undo)
    w.paste_style_to_selection()
    assert len(w._undo) == before_undo + 1     # 단일 undo 엔트리
    assert abs(b.pen().widthF() - 7.0) < 1e-6 and abs(c.pen().widthF() - 7.0) < 1e-6
    w.undo()
    assert abs(b.pen().widthF() - 1.0) < 1e-6 and abs(c.pen().widthF() - 1.0) < 1e-6




def test_style_shortcuts_ctrl_alt_dispatch():
    # [단축키] Ctrl+Alt+C/V가 스타일 복사/붙여넣기로 배선되고, Alt 없는 평범한 Ctrl+C/V는
    # 여전히 기존 아이템 복사/붙여넣기로 간다(회귀 방지 — Ctrl+C 체크를 Alt 제외로 수정했다).
    from PyQt6.QtGui import QKeyEvent, QPen
    from PyQt6.QtCore import QEvent
    CTRL = Qt.KeyboardModifier.ControlModifier
    CTRL_ALT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    w = CanvasWindow(); w.show(); w.set_tool("select")
    view = w._view
    a = _mk_pen_rect(w, x=0, y=0, width=9.0)
    a.setPen(QPen(QColor("#123456"), 9.0))
    a.setSelected(True)

    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, CTRL_ALT))
    assert w._style_clip is not None                       # Ctrl+Alt+C

    b = _mk_pen_rect(w, x=100, y=0, width=1.0)
    w._scene.clearSelection(); b.setSelected(True)
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, CTRL_ALT))
    assert abs(b.pen().widthF() - 9.0) < 1e-6               # Ctrl+Alt+V

    assert not w._clip                                       # 전제: 아직 아이템 복사 안 함
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, CTRL))
    assert w._clip                                           # 일반 Ctrl+C는 그대로 아이템 복사(회귀 없음)




def test_context_menu_style_entries_visibility():
    # [스타일 복사] 단일 선택=복사 진입점 노출, 클립 있고 선택 있으면=붙여넣기도 노출.
    w = CanvasWindow()
    labels = lambda: [act.text() for act in w._build_context_menu().actions() if not act.isSeparator()]
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=100, y=0)
    a.setSelected(True)
    assert any(t.startswith("스타일 복사") for t in labels())
    assert not any(t.startswith("스타일 붙여넣기") for t in labels())
    w.copy_style_from_selection()
    assert any(t.startswith("스타일 붙여넣기") for t in labels())
    a.setSelected(True); b.setSelected(True)
    assert not any(t.startswith("스타일 복사") for t in labels())   # 다중선택엔 복사 진입점 없음
    assert any(t.startswith("스타일 붙여넣기") for t in labels())    # 붙여넣기는 다중선택도 가능




def test_cable_numbers_orders_by_position():
    # [케이블 번호] 위치순(좌상단→우하단)으로 번호가 매겨진다 — 선택/그리기 순서 무관.
    w = CanvasWindow()
    bottom = _mk_arrow(w, 0, 200, 100, 200)   # 아래쪽에 먼저 생성
    top = _mk_arrow(w, 0, 0, 100, 0)          # 위쪽은 나중에 생성
    bottom.setSelected(True); top.setSelected(True)
    w.apply_cable_numbers("CABLE", 1)
    assert top._label.toPlainText() == "CABLE-1"
    assert bottom._label.toPlainText() == "CABLE-2"




def test_cable_numbers_works_on_polyarrow():
    # [케이블 번호] 직각 커넥터(_PolyArrowItem)에도 동일하게 적용된다(직선 전용 아님).
    w = CanvasWindow()
    sar = _PolyArrowItem(QColor("#111111"), 3, True)
    sar._pts = [QPointF(0, 0), QPointF(80, 0), QPointF(80, 40)]
    sar.setFlags(sar.GraphicsItemFlag.ItemIsSelectable | sar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sar)
    sar.setSelected(True)
    w.apply_cable_numbers("CABLE", 1)
    assert sar._label.toPlainText() == "CABLE-1"




def test_cable_numbers_preserves_existing_label_text():
    # [케이블 번호] 이미 라벨이 있으면 번호를 앞에 붙이고 기존 텍스트는 보존한다.
    w = CanvasWindow()
    a = _mk_arrow(w, 0, 0, 100, 0)
    a.ensure_label().setPlainText("메인전원")
    a.setSelected(True)
    w.apply_cable_numbers("CABLE", 1)
    assert a._label.toPlainText() == "CABLE-1: 메인전원"




def test_cable_numbers_rerun_replaces_same_prefix():
    # [케이블 번호] 같은 접두사로 재실행하면 옛 번호가 새 번호로 교체(누적 안 됨).
    w = CanvasWindow()
    a = _mk_arrow(w, 0, 0, 100, 0)
    a.setSelected(True)
    w.apply_cable_numbers("CABLE", 1)
    assert a._label.toPlainText() == "CABLE-1"
    w.apply_cable_numbers("CABLE", 5)
    assert a._label.toPlainText() == "CABLE-5"




def test_cable_numbers_different_prefix_appends():
    # [케이블 번호] 접두사가 바뀌면 옛 번호 패턴은 못 알아보고 그대로 보존한 채 앞에 새로 붙는다.
    w = CanvasWindow()
    a = _mk_arrow(w, 0, 0, 100, 0)
    a.setSelected(True)
    w.apply_cable_numbers("CABLE", 1)
    w.apply_cable_numbers("CAM", 1)
    assert a._label.toPlainText() == "CAM-1: CABLE-1"




def test_cable_numbers_undo_restores():
    # [케이블 번호] 신규 라벨 생성은 undo로 사라지고, 기존 라벨 수정은 원문으로 복원 — 단일 undo.
    w = CanvasWindow()
    fresh = _mk_arrow(w, 0, 0, 100, 0)                  # 라벨 없음 → 새로 생성됨
    existing = _mk_arrow(w, 0, 100, 100, 100)
    existing.ensure_label().setPlainText("기존라벨")     # 라벨 있음 → 수정됨
    fresh.setSelected(True); existing.setSelected(True)
    before_undo = len(w._undo)
    w.apply_cable_numbers("CABLE", 1)
    assert len(w._undo) == before_undo + 1              # 단일 undo 엔트리
    assert fresh._label_alive() and existing._label.toPlainText().startswith("CABLE-")
    w.undo()
    assert not fresh._label_alive()
    assert existing._label.toPlainText() == "기존라벨"




def test_arrow_targets_filters_non_arrows():
    # [케이블 번호] 선택에 도형이 섞여 있어도 화살표만 대상이 된다.
    w = CanvasWindow()
    r = _mk_pen_rect(w, x=0, y=0)
    a = _mk_arrow(w, 0, 100, 100, 100)
    r.setSelected(True); a.setSelected(True)
    targets = w._arrow_targets()
    assert targets == [a]




def test_context_menu_cable_number_entry_visibility():
    # [케이블 번호] 화살표 선택 시만 우클릭 메뉴에 진입점이 뜬다(도형만 선택 시는 안 뜸).
    w = CanvasWindow()
    labels = lambda: [act.text() for act in w._build_context_menu().actions() if not act.isSeparator()]
    r = _mk_pen_rect(w, x=0, y=0)
    r.setSelected(True)
    assert not any(t.startswith("케이블 번호") for t in labels())
    a = _mk_arrow(w, 0, 100, 100, 100)
    w._scene.clearSelection(); a.setSelected(True)
    assert any(t.startswith("케이블 번호") for t in labels())




def test_layers_default_layer_exists():
    # [레이어] 새 창은 "기본" 레이어 1개로 시작.
    w = CanvasWindow()
    assert len(w._layers) == 1
    assert w._layers[0]["id"] == "default"
    assert w._layers[0]["name"] == "기본"




def test_layer_add_rename_delete_moves_items_to_default():
    # [레이어] 추가·이름변경 정상, 삭제하면 소속 아이템이 기본 레이어로 소급.
    w = CanvasWindow()
    layer = w.add_layer("배선")
    assert len(w._layers) == 2 and layer["name"] == "배선"
    w.rename_layer(layer["id"], "전원")
    assert w._layer_by_id(layer["id"])["name"] == "전원"
    r = _mk_pen_rect(w, x=0, y=0)
    r._layer_id = layer["id"]
    w.delete_layer(layer["id"])
    assert len(w._layers) == 1
    assert w._item_layer_id(r) == "default"




def test_layer_delete_default_is_noop():
    # [레이어] 기본 레이어는 삭제 불가(최소 1개 유지).
    w = CanvasWindow()
    w.delete_layer("default")
    assert len(w._layers) == 1




def test_move_selection_to_layer_single_undo():
    # [레이어] 선택 이동은 단일 undo 엔트리, undo로 원래 레이어 복원.
    w = CanvasWindow()
    layer = w.add_layer("배선")
    a = _mk_pen_rect(w, x=0, y=0)
    b = _mk_pen_rect(w, x=100, y=0)
    a.setSelected(True); b.setSelected(True)
    before_undo = len(w._undo)
    w.move_selection_to_layer(layer["id"])
    assert len(w._undo) == before_undo + 1
    assert w._item_layer_id(a) == layer["id"] and w._item_layer_id(b) == layer["id"]
    w.undo()
    assert w._item_layer_id(a) == "default" and w._item_layer_id(b) == "default"




def test_layer_visibility_hides_only_that_layer():
    # [레이어] 표시 끄면 그 레이어 아이템만 숨겨지고 다른 레이어는 그대로.
    w = CanvasWindow()
    layer = w.add_layer("배선")
    a = _mk_pen_rect(w, x=0, y=0)
    b = _mk_pen_rect(w, x=100, y=0)
    b.setSelected(True)
    w.move_selection_to_layer(layer["id"])
    w.set_layer_visible(layer["id"], False)
    assert b.isVisible() is False
    assert a.isVisible() is True
    w.set_layer_visible(layer["id"], True)
    assert b.isVisible() is True




def test_layer_lock_applies_to_member_items():
    # [레이어] 잠금 토글 시 소속 아이템 전체가 개별 Ctrl+L과 같은 플래그로 잠긴다.
    w = CanvasWindow()
    layer = w.add_layer("배선")
    a = _mk_pen_rect(w, x=0, y=0)
    a.setSelected(True)
    w.move_selection_to_layer(layer["id"])
    w.set_layer_locked(layer["id"], True)
    assert getattr(a, "_locked", False) is True
    assert not (a.flags() & a.GraphicsItemFlag.ItemIsMovable)
    w.set_layer_locked(layer["id"], False)
    assert getattr(a, "_locked", False) is False




def test_layer_roundtrip_ecad():
    # [레이어] 저장/재열기 후 레이어 목록·아이템 소속·표시/잠금 상태가 복원된다.
    w = CanvasWindow()
    layer = w.add_layer("배선")
    a = _mk_pen_rect(w, x=0, y=0)
    a.setSelected(True)
    w.move_selection_to_layer(layer["id"])
    w.set_layer_locked(layer["id"], True)
    path = os.path.join(_TMP, "layers_rt.ecad")
    save_document(w._scene, path, layers=w._layers)
    w2 = CanvasWindow()
    n = load_document(w2._scene, path)
    layers2 = load_document_layers(path)
    w2._apply_loaded_layers(layers2)
    assert n == 1
    assert any(l["name"] == "배선" and l["locked"] for l in w2._layers)
    it2 = [x for x in w2._scene.items() if isinstance(x, _RectItem)][0]
    assert w2._item_layer_id(it2) == layer["id"]
    assert getattr(it2, "_locked", False) is True




def test_layer_roundtrip_legacy_ecad_no_layers_key():
    # [레이어] 레이어 키 없는 옛 .ecad는 기본 레이어 하나로 안전 복원.
    w = CanvasWindow()
    _mk_pen_rect(w, x=0, y=0)
    path = os.path.join(_TMP, "layers_legacy.ecad")
    save_document(w._scene, path)   # layers 인자 없이 저장 = 옛 파일 흉내
    w2 = CanvasWindow()
    load_document(w2._scene, path)
    layers2 = load_document_layers(path)
    assert layers2 is None
    w2._apply_loaded_layers(layers2)
    assert len(w2._layers) == 1 and w2._layers[0]["id"] == "default"




def test_context_menu_layer_menu_lists_layers():
    # [레이어] 우클릭 "레이어로 이동" 서브메뉴가 대상 있을 때만 뜨고 레이어 이름을 나열한다.
    w = CanvasWindow()
    w.add_layer("배선")
    r = _mk_pen_rect(w, x=0, y=0)
    menu = w._build_context_menu()
    submenu_titles = [act.text() for act in menu.actions() if act.menu() is not None]
    assert not any(t == "레이어로 이동" for t in submenu_titles)   # 선택 없으면 없음
    r.setSelected(True)
    menu2 = w._build_context_menu()
    layer_action = next(act for act in menu2.actions() if act.text() == "레이어로 이동")
    names = [a.text() for a in layer_action.menu().actions()]
    assert "기본" in names and "배선" in names




def test_do_open_save_ecad_roundtrip():
    # [신규기능] DXF/.ecad 통합(2026-07-29) — 확장자 분기용 얇은 래퍼 _do_save_ecad/_do_open_ecad
    # 가 여전히 save_document/load_document를 정확히 호출하는지(_doc_path 갱신 포함).
    w = CanvasWindow()
    _mk_pen_rect(w, x=10, y=20)
    path = os.path.join(_TMP, "do_ecad_rt.ecad")
    w._do_save_ecad(path)
    assert w._doc_path == path
    assert os.path.exists(path)
    w2 = CanvasWindow()
    w2._do_open_ecad(path)
    assert w2._doc_path == path
    assert len([x for x in w2._scene.items() if isinstance(x, _RectItem)]) == 1




def test_do_open_export_dxf_roundtrip_no_doc_path():
    # [신규기능] DXF는 열기/저장 둘 다 _doc_path를 갱신하지 않는다(deep-interview 결정 —
    # 통합 저장 다이얼로그의 기본 필터가 항상 .ecad로 뜨게 하기 위함).
    # ⚠ _do_export_dxf 성공 경로가 QMessageBox.information("저장 완료")을 띄운다 —
    # 헤드리스(offscreen)에서 실제 .exec()는 클릭할 사용자가 없어 영원히 블로킹되므로
    # 반드시 모킹한다(실제로 이 모킹 없이 전체 스모크 스위트가 멈춘 사고 — 2026-07-29).
    from PyQt6.QtWidgets import QMessageBox
    orig_info, orig_warn = QMessageBox.information, QMessageBox.warning
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    try:
        w = CanvasWindow()
        _mk_pen_rect(w, x=5, y=5, ww=80, hh=40)
        path = os.path.join(_TMP, "do_dxf_rt.dxf")
        prior_doc_path = w._doc_path
        w._do_export_dxf(path)
        assert os.path.exists(path)
        assert w._doc_path == prior_doc_path
        w2 = CanvasWindow()
        w2._do_open_dxf(path)
        assert any(isinstance(x, _RectItem) for x in w2._scene.items())
        assert w2._doc_path is None
    finally:
        QMessageBox.information, QMessageBox.warning = orig_info, orig_warn




def test_save_doc_dispatches_by_extension():
    # [신규기능] 옛 「DXF 내보내기」 전용 메뉴·단축키(Ctrl+Shift+D) 폐지 — 저장(Ctrl+S) 하나가
    # 파일 다이얼로그에서 고른 확장자로 _do_save_ecad/_do_export_dxf에 분기하는지 확인.
    from PyQt6.QtWidgets import QFileDialog
    from PyQt6.QtCore import QSettings
    QSettings("EasyCAD", "EasyCAD").setValue("dxf_save_warned", True)   # 손실 확인창 스킵(헤드리스)
    w = CanvasWindow()
    calls = []
    w._do_save_ecad = lambda path: calls.append(("ecad", path))
    w._do_export_dxf = lambda path: calls.append(("dxf", path))
    orig = QFileDialog.getSaveFileName
    try:
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("out.ecad", ""))
        w._save_doc()
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("out.dxf", ""))
        w._save_doc()
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("out_noext", ""))
        w._save_doc()   # 확장자 없이 저장 → .ecad 기본(deep-interview 결정) 적용 확인
    finally:
        QFileDialog.getSaveFileName = orig
    assert calls == [("ecad", "out.ecad"), ("dxf", "out.dxf"), ("ecad", "out_noext.ecad")]




def test_open_doc_dispatches_by_extension():
    from PyQt6.QtWidgets import QFileDialog
    from PyQt6.QtCore import QSettings
    QSettings("EasyCAD", "EasyCAD").setValue("dxf_open_notified", True)   # 안내창 스킵(헤드리스)
    w = CanvasWindow()
    calls = []
    w._do_open_ecad = lambda path: calls.append(("ecad", path))
    w._do_open_dxf = lambda path: calls.append(("dxf", path))
    orig = QFileDialog.getOpenFileName
    try:
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("in.ecad", ""))
        w._open_doc()
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("in.dxf", ""))
        w._open_doc()
    finally:
        QFileDialog.getOpenFileName = orig
    assert calls == [("ecad", "in.ecad"), ("dxf", "in.dxf")]




def test_dxf_confirm_dialogs_show_once_via_qsettings():
    # [신규기능] "다만 열기 했을때 한번 알림 창 띄우면 좋을듯" — 저장·열기 둘 다 앱 생애
    # 처음 1회만 확인창을 띄우고, 이후는 QSettings 플래그로 조용히 통과한다.
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QMessageBox
    settings = QSettings("EasyCAD", "EasyCAD")
    settings.remove("dxf_save_warned")
    settings.remove("dxf_open_notified")
    w = CanvasWindow()
    orig_warning, orig_info = QMessageBox.warning, QMessageBox.information
    shown = []
    try:
        QMessageBox.warning = staticmethod(
            lambda *a, **k: shown.append("warn") or QMessageBox.StandardButton.Ok)
        QMessageBox.information = staticmethod(
            lambda *a, **k: shown.append("info") or QMessageBox.StandardButton.Ok)
        assert w._confirm_dxf_save_once() is True
        assert w._confirm_dxf_save_once() is True   # 2번째부터는 창 없이 True
        assert w._confirm_dxf_open_once() is True
        assert w._confirm_dxf_open_once() is True
    finally:
        QMessageBox.warning, QMessageBox.information = orig_warning, orig_info
    assert shown == ["warn", "info"]   # 각 종류 첫 호출에만 창이 뜸
    assert settings.value("dxf_save_warned", False, type=bool) is True
    assert settings.value("dxf_open_notified", False, type=bool) is True




def test_shape_fill_apply_and_undo():
    # [신규기능] 도형 채우기 — rect/ellipse/symbol만 apply_fill을 갖고, 선/화살표/텍스트는 없다.
    w = CanvasWindow()
    r = _mk_pen_rect(w)
    e = _EllipseItem(QRectF(0, 0, 40, 30)); w._scene.addItem(e)
    s = _SymbolItem("decision", QRectF(0, 0, 40, 30)); w._scene.addItem(s)
    for it in (r, e, s):
        assert hasattr(it, "apply_fill")
        assert it.brush().style() == Qt.BrushStyle.NoBrush   # 기본 투명
    ln = _LineItem(QLineF(0, 0, 10, 10)); w._scene.addItem(ln)
    ar = _ArrowItem(QColor("#ff0000"), 2, True); w._scene.addItem(ar)
    t = _TextItem(QColor("#000000")); w._scene.addItem(t)
    for it in (ln, ar, t):
        assert not hasattr(it, "apply_fill")

    r.setSelected(True)
    w._edit_items([r], lambda x: x.apply_fill(QColor("#ffcc00")))
    assert r.brush().style() != Qt.BrushStyle.NoBrush
    assert r.brush().color().name() == "#ffcc00"
    w.undo()
    assert r.brush().style() == Qt.BrushStyle.NoBrush   # 되돌리면 다시 투명
    w.redo()
    assert r.brush().color().name() == "#ffcc00"
    # apply_fill(None) = 다시 투명으로.
    r.apply_fill(None)
    assert r.brush().style() == Qt.BrushStyle.NoBrush




def test_shape_fill_ecad_roundtrip():
    # [신규기능] .ecad는 이미 fill 필드를 왕복 지원(document.py 기존 코드) — UI만 신규였음을 확인.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    r = _RectItem(QRectF(0, 0, 40, 30)); r.apply_fill(QColor("#11aa33")); w._scene.addItem(r)
    e = _EllipseItem(QRectF(0, 0, 40, 30)); e.apply_fill(None); w._scene.addItem(e)  # 명시적 투명
    s = _SymbolItem("decision", QRectF(0, 0, 40, 30))
    s.apply_fill(QColor("#8000ffcc"))   # 알파 채널 포함(반투명)
    w._scene.addItem(s)
    p = os.path.join(_TMP, "fill_rt.ecad")
    save_document(w._scene, p)
    sc2 = QGraphicsScene(); load_document(sc2, p)
    r2 = [x for x in sc2.items() if isinstance(x, _RectItem)][0]
    e2 = [x for x in sc2.items() if isinstance(x, _EllipseItem)][0]
    s2 = [x for x in sc2.items() if isinstance(x, _SymbolItem)][0]
    assert r2.brush().color().name() == "#11aa33"
    assert e2.brush().style() == Qt.BrushStyle.NoBrush
    assert s2.brush().color().alpha() == 0x80




def test_shape_fill_clone_and_interior_hit():
    # 채움이 생기면 clone도 함께 옮기고, 클릭 판정(_base_shape)이 테두리 링 → 전체 내부로 바뀐다
    # (기존 코드가 이미 brush().style()로 분기해 두던 부분 — 채움 자체가 없어 죽은 코드였음).
    r = _RectItem(QRectF(0, 0, 100, 60))
    from PyQt6.QtCore import QPointF as _P
    assert not r.contains(_P(50, 30))   # 투명 — 정중앙은 클릭 영역 밖(테두리 링만)
    r.apply_fill(QColor("#00aaff"))
    assert r.contains(_P(50, 30))       # 채워지면 내부 전체가 클릭 영역
    c = r.clone()
    assert c.brush().color().name() == "#00aaff"




def test_properties_panel_fill_row():
    # 속성 dock 「채움」 행 — 단일선택 값 표시, 혼합 감지, 화살표만 선택 시 비활성.
    from PyQt6.QtGui import QPen
    w = CanvasWindow()
    sel_flags = _RectItem.GraphicsItemFlag.ItemIsSelectable | _RectItem.GraphicsItemFlag.ItemIsMovable
    r = _RectItem(QRectF(0, 0, 40, 30)); r.setPen(QPen(QColor("#000000"))); r.setFlags(sel_flags)
    r.apply_fill(QColor("#ff00ff")); w._scene.addItem(r)
    r.setSelected(True); w._refresh_properties()
    assert w._pf_fill.isEnabled()
    assert w._pf_fill_val.text() == "#ff00ff"

    e = _EllipseItem(QRectF(100, 0, 40, 30)); e.setPen(QPen(QColor("#000000"))); e.setFlags(sel_flags)
    w._scene.addItem(e)   # 채움 없음(투명) — 다른 값
    e.setSelected(True); w._refresh_properties()
    assert w._pf_fill_val.text() == "혼합"

    w._scene.clearSelection()
    ar = _ArrowItem(QColor("#ff0000"), 2, True); ar.setFlags(sel_flags)
    ar.set_points(QPointF(0, 0), QPointF(50, 0)); w._scene.addItem(ar)
    ar.setSelected(True); w._refresh_properties()
    assert not w._pf_fill.isEnabled()   # 화살표는 채움 미지원




def test_edit_fill_and_clear_fill_sticky():
    # _edit_fill이 그리드 팝업을 띄우고, "다른 색…"(알파 지원 QColorDialog, 실제 exec는
    # 모킹) 경로가 undo 저널 + sticky current_fill 둘 다 갱신. _clear_fill은 팝업 "없음"
    # 항목이 호출하는 메서드.
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QColorDialog
    QSettings("EasyCAD", "EasyCAD").remove("recent_colors")
    w = CanvasWindow()
    r = _mk_pen_rect(w); r.setSelected(True)
    orig_exec = QColorDialog.exec
    try:
        QColorDialog.exec = _mock_color_dialog_exec(QColor("#123456"))
        w._edit_fill()
        w._last_color_popup._pick_other()   # "다른 색…" 클릭 시뮬레이션
    finally:
        QColorDialog.exec = orig_exec
    assert r.brush().color().name() == "#123456"
    assert w.current_fill.name() == "#123456"
    assert w._recent_colors[0].name() == "#123456"   # "다른 색"에서 고른 색은 최근색으로 기억
    w.undo()
    assert r.brush().style() == Qt.BrushStyle.NoBrush
    w._clear_fill()   # 선택 유지된 상태에서 다시 투명으로(redo 상태 위에 새 편집)
    assert w.current_fill is None




def test_color_dialog_left_column_stripped_for_alpha():
    # [요청] Basic/Custom colors(우리 그리드와 중복)는 숨기고 오른쪽 그라디언트+필드만 남김
    # — "Basic colors"/"Custom colors" 라벨 앵커 기반 판정(v2, 2026-07-31)이 실제로
    # 다이얼로그를 좁혀주면서 오른쪽 그라디언트 사각형은 지우지 않는지 실측.
    # (v1은 고정 좌표 임계값이라 실제 앱(Fusion 스타일+실제 폰트)에서 그라디언트 사각형까지
    # 함께 지워버리는 회귀가 실사용자 스크린샷으로 발견됨 — 이 테스트가 그 재발을 막는다.)
    from PyQt6.QtWidgets import QColorDialog, QFrame, QWidget
    from easycad.canvas.host_widgets import _strip_color_dialog_left_column
    dlg = QColorDialog()
    dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
    dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    dlg.adjustSize()
    before = dlg.width()
    # 그라디언트 사각형은 dlg의 "직접" 자식 중 타입이 정확히 QFrame인 것(QLabel도 Qt
    # 상속구조상 QFrame의 서브클래스라 isinstance만 쓰면 "&Basic colors" 라벨을 잘못
    # 집는다 — 실측으로 발견, type(w) is QFrame으로 정확히 판정).
    gradient = next(w for w in dlg.children() if type(w) is QFrame)
    _strip_color_dialog_left_column(dlg)
    dlg.adjustSize()
    assert dlg.width() < before - 200   # 왼쪽 열(≈254px)만큼 좁아짐
    assert not gradient.isHidden()   # 핵심 회귀 방지 — 그라디언트는 절대 숨겨지면 안 됨
    # OK/Cancel 버튼줄(폭이 훨씬 넓음)은 실수로 숨겨지지 않아야 한다.
    # (isVisible()이 아니라 isHidden() — 다이얼로그를 show() 안 한 헤드리스 테스트에선
    # 조상 체인이 안 보여 isVisible()이 항상 False로 읽힌다, CLAUDE.md 기존 함정과 동일.)
    from PyQt6.QtWidgets import QDialogButtonBox
    bbox = dlg.findChild(QDialogButtonBox)
    assert bbox is not None and not bbox.isHidden()




def test_color_grid_popup_fill_has_none_item_color_does_not():
    # [요청③] "없음"은 채움 전용 — 팝업 안 항목으로만 존재, 선 색 팝업엔 안 뜬다.
    w = CanvasWindow()
    r = _mk_pen_rect(w); r.setSelected(True)
    w._edit_fill()
    fill_pop = w._last_color_popup
    assert any(b.text() == "Ø" for b in fill_pop.findChildren(QToolButton))
    w._edit_color()
    color_pop = w._last_color_popup
    assert not any(b.text() == "Ø" for b in color_pop.findChildren(QToolButton))




def test_color_grid_popup_swatch_click_applies_immediately():
    # 그리드 스와치를 누르면 다이얼로그 없이 그 자리에서 바로 적용된다(오피스 관례).
    # 열 구성: 무채색 1 + 유채색 6 + 최근색 1 = 8열 x 3행. 각 열은 위→아래 표준→연한→어두움
    # 순(2026-07-31 재배치) — 무채색 열의 "표준"은 회색.
    w = CanvasWindow()
    r = _mk_pen_rect(w); r.setSelected(True)
    w._edit_fill()
    pop = w._last_color_popup
    swatches = [b for b in pop.findChildren(QToolButton) if b.text() not in ("Ø", "다른 색…")]
    assert len(swatches) == 8 * 3
    swatches[0].click()   # 무채색 열의 첫 행 = 표준(회색)
    assert r.brush().color().name() == QColor("#9E9E9E").name()
    assert w.current_fill.name() == QColor("#9E9E9E").name()




def test_color_grid_popup_none_item_clears_fill():
    w = CanvasWindow()
    r = _mk_pen_rect(w); r.setSelected(True)
    r.apply_fill(QColor("#123456"))
    w._edit_fill()
    pop = w._last_color_popup
    none_btn = next(b for b in pop.findChildren(QToolButton) if b.text() == "Ø")
    none_btn.click()
    assert r.brush().style() == Qt.BrushStyle.NoBrush
    assert w.current_fill is None




def test_color_grid_popup_recent_column_shows_and_persists():
    # "다른 색"에서 고른 색이 다음 팝업의 "최근 사용한 색" 열(맨 오른쪽, 위→최신)에 뜨고,
    # QSettings로 재시작 후에도 유지된다(다크모드와 같은 sticky 관례).
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QColorDialog
    QSettings("EasyCAD", "EasyCAD").remove("recent_colors")
    w = CanvasWindow()
    r = _mk_pen_rect(w); r.setSelected(True)
    orig_exec = QColorDialog.exec
    try:
        QColorDialog.exec = _mock_color_dialog_exec(QColor("#abcdef"))
        w._edit_fill()
        w._last_color_popup._pick_other()
    finally:
        QColorDialog.exec = orig_exec

    w._edit_fill()
    pop = w._last_color_popup
    swatches = [b for b in pop.findChildren(QToolButton) if b.text() not in ("Ø", "다른 색…")]
    recent_col = swatches[-3:]   # 맨 오른쪽 열
    assert recent_col[0].isEnabled() and recent_col[0].toolTip() == "#abcdef"
    assert not recent_col[1].isEnabled()   # 아직 빈 슬롯(대시 테두리 플레이스홀더)

    w2 = CanvasWindow()   # 새 창(=재시작 흉내)도 QSettings에서 그대로 불러온다
    assert w2._recent_colors and w2._recent_colors[0].name() == "#abcdef"
    QSettings("EasyCAD", "EasyCAD").remove("recent_colors")   # 다른 테스트 오염 방지




def test_new_shape_uses_sticky_fill():
    # make_brush()가 current_fill을 반영 — 새 도형 생성 경로(팔레트 드롭)에서 확인.
    w = CanvasWindow()
    assert w.make_brush().style() == Qt.BrushStyle.NoBrush   # 기본은 투명
    w.current_fill = QColor("#00ff88")
    it = w._create_shape_at("rect", QPointF(100, 100))
    assert it.brush().color().name() == "#00ff88"




def test_paint_style_copy_includes_fill():
    # [스타일 복사] 채움도 서식의 일부로 옮겨진다 — has_fill 대상끼리만, 타입이 달라도 적용.
    w = CanvasWindow()
    sel_flags = _RectItem.GraphicsItemFlag.ItemIsSelectable | _RectItem.GraphicsItemFlag.ItemIsMovable
    src = _RectItem(QRectF(0, 0, 40, 30)); src.setFlags(sel_flags)
    src.apply_fill(QColor("#abcdef")); w._scene.addItem(src)
    dst = _EllipseItem(QRectF(100, 0, 40, 30)); dst.setFlags(sel_flags); w._scene.addItem(dst)
    src.setSelected(True)
    w.copy_style_from_selection()
    w._scene.clearSelection()
    dst.setSelected(True)
    w.paste_style_to_selection()
    assert dst.brush().color().name() == "#abcdef"
    w.undo()
    assert dst.brush().style() == Qt.BrushStyle.NoBrush


