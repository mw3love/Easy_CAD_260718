"""UI 패널·화살표 스타일/라우팅 기초·복제/선택 성능·팔레트 드래그

tests/test_easycad.py 2026-08-02 분할분. 실행: python tests/test_easycad.py (전체) 또는 pytest test_part1_ui_arrows.py.
"""
from _shared import *  # noqa: F401,F403


def test_host_construction():
    w = CanvasWindow()
    # 상단 툴바 = 그리기 도구 7종(네모·원은 왼쪽 「도형」 팔레트, 직선화살은 화살표 1개로 통합,
    # 2026-08-10 §8 항목17 4단계로 TRIM 추가 6→7).
    assert len(w._tool_buttons) == 7
    assert not ({"rect", "ellipse", "sarrow"} & set(w._tool_buttons))
    assert "arrow" in w._tool_buttons                      # 화살표 버튼 하나가 직선·곡선·직각 대표
    assert "trim" in w._tool_buttons
    # 왼쪽 팔레트: 기본도형(네모·원·삼각형) + 순서도(5종) + 내 심볼(폴더) + 레이어, 아코디언.
    # (2026-08-04: 옛 "순서도" 섹션 18종 제거(파라메트릭 심볼 전략 폐기) → 2026-08-12 좌측
    # 패널 아코디언 개편에서 Mermaid 문법이 직접 매핑하는 5종만 재추가.
    # 2026-08-10 §8 항목17 7단계: 포트□/포트○ 제거 — TRIM이 겹친 도형 자르기로 대체,
    # 백엔드(_create_port_at 등)는 유지해 기존 .ecad는 그대로 열림.)
    assert set(w._shape_tool_buttons) == {"rect", "ellipse", "triangle"}
    assert set(w._sym_buttons) == {"decision", "terminal", "data", "prep", "database"}
    r = w._scene.sceneRect()
    assert r.width() > 90000 and r.height() > 90000
    m0 = w._view.transform().m11()
    w._on_wheel_zoom(120)
    assert w._view.transform().m11() > m0




def test_toolbar_icons_and_actions():
    # [Phase 6 M1] 상단바 = QToolBar. 그리기 도구는 아이콘, 파일·보기 액션이 상단으로 이관되고
    # 아이콘을 가진다. 단축키 안내 라벨은 도움말 액션으로 분리.
    from easycad.canvas.host_widgets import _act_icon
    w = CanvasWindow()
    # 그리기 도구 7종 모두 아이콘 보유(텍스트 버튼 아님, 2026-08-10 TRIM 추가 6→7).
    assert len(w._tool_buttons) == 7
    for b in w._tool_buttons.values():
        assert not b.icon().isNull()
    # 파일/삽입/보기 액션이 아이콘을 가진다. [신규기능] DXF는 열기/저장(Ctrl+O/S)에
    # 통합돼 전용 액션(_act_dxf/_act_dxf_in)이 더 이상 없음(2026-07-29).
    for a in (w._act_new, w._act_open, w._act_save, w._act_pdf,
              w._act_img, w._act_tb, w._act_tbl, w._act_mmd,
              w._act_undo, w._act_redo, w._act_zoom100, w._act_fit, w._act_snap,
              w._act_ortho, w._act_help):
        assert not a.icon().isNull()
    # 모든 액션 아이콘 이름이 렌더 가능(빈 아이콘 없음).
    for nm in ("new", "open", "save", "pdf", "image",
               "table", "titleblock", "mermaid", "zoom_fit", "zoom_100",
               "snap", "ortho", "undo", "redo", "help"):
        assert not _act_icon(nm).isNull()
    # 상단 QToolBar가 실제로 존재하고 액션이 실려 있다.
    assert w._toolbar.actions()
    # 스냅/직교는 체크형, 스냅 기본 켜짐. 트리거 시 상태 반전이 owner에 반영.
    assert w._act_snap.isCheckable() and w._act_snap.isChecked()
    assert w.snap_enabled is True
    w._act_snap.trigger()
    assert w._act_snap.isChecked() is False and w.snap_enabled is False




def test_dark_mode_toggle():
    # [Phase 6 M1] 다크 기본 + 라이트 토글. 배경·아이콘·팔레트가 함께 바뀌고, PDF는 흰 배경 유지.
    from easycad.canvas.host_widgets import _act_icon
    w = CanvasWindow()
    assert w._dark is True                                   # 다크 기본
    assert w._scene.backgroundBrush().color().lightness() < 80   # 어두운 캔버스
    theme_ic = _act_icon("theme"); assert not theme_ic.isNull()
    # 라이트로 전환(테스트는 persist=False → 사용자 QSettings 미변경).
    w._apply_theme(False)
    assert w._dark is False
    assert w._scene.backgroundBrush().color().lightness() > 200   # 밝은 캔버스
    # 아이콘 재생성이 깨지지 않음(팔레트/액션).
    for b in w._shape_tool_buttons.values():
        assert not b.icon().isNull()
    for a in (w._act_new, w._act_snap, w._act_theme):
        assert not a.icon().isNull()
    # 다크로 복귀
    w._apply_theme(True)
    assert w._scene.backgroundBrush().color().lightness() < 80


def test_default_shape_color_follows_theme_until_user_picks_one():
    """[실사용 피드백 2026-08-18] 기본 도형색이 순수 흰색으로 고정되면 라이트 캔버스
    (#ffffff)에서 안 보인다 — 표제란/표와 같은 "테마 적응 잉크색"으로 대신 따라가되,
    사용자가 직접 색을 고르면 그 순간부터 sticky로 고정돼 테마를 안 따라간다."""
    from easycad.canvas.core_constants import _DEFAULT_INK_DARK, _DEFAULT_INK_LIGHT
    w = CanvasWindow()
    assert w._dark is True
    assert w.current_color.name() == QColor(_DEFAULT_INK_DARK).name()
    w._apply_theme(False)
    assert w.current_color.name() == QColor(_DEFAULT_INK_LIGHT).name()
    w._apply_theme(True)
    assert w.current_color.name() == QColor(_DEFAULT_INK_DARK).name()

    w._set_current_color(QColor("#e02424"))   # 사용자가 직접 색을 고름 — 이제부터 sticky
    w._apply_theme(False)
    assert w.current_color.name() == QColor("#e02424").name()   # 테마 전환에 안 바뀜




def test_pdf_export_forces_white_bg():
    # [Phase 6 M1] 다크 테마여도 PDF 배경은 흰색으로 강제되고, export 후 씬 배경은 복원된다.
    w = CanvasWindow()
    w._apply_theme(True)   # 다크(어두운 캔버스)
    _mk_rect(w._scene, w.make_pen(), 0, 0, 120, 60)
    before = w._scene.backgroundBrush().color().name()
    p = os.path.join(_TMP, "dark_export.pdf")
    assert export_pdf(w._scene, p, page="A4")
    assert os.path.exists(p)
    assert w._scene.backgroundBrush().color().name() == before   # 배경 복원됨




def test_floating_panels_and_zoom_readout():
    # [캔버스-퍼스트 레이아웃] 좌/우 QDockWidget → 콘텐츠 크기 플로팅 카드로 전환(deep-interview
    # 2026-07-29) — 좌측은 2026-08-12에 탭 2개에서 아코디언 섹션으로 개편(2026-08-13에 기본도형·
    # 순서도를 다시 하나로 병합해 지금은 기본도형/내 심볼/레이어 3섹션), 위치는 고정(자유 드래그
    # 재배치 없음), 도형 그리드는 항상 4열 고정(`_PALETTE_COLS`, 2026-08-12 후속 피드백 — 2열은
    # 패널 폭의 절반이 빈 공간으로 남아 밀도를 높임).
    w = CanvasWindow()
    assert w._left_panel.parent() is w
    assert w._props_panel.parent() is w
    assert w._minimap_panel.parent() is w
    basic_grid, basic_btns = w._shape_sections[0]
    last = basic_btns[-1]
    r, c, _rs, _cs = basic_grid.getItemPosition(basic_grid.indexOf(last))
    # [2026-08-13] 기본도형(네모·원·삼각형)+순서도(판단·시작/끝·입출력·준비·저장소) 8종이
    # 이제 한 그리드(4열 고정)에 고르게 줄바꿈된다 — 마지막 버튼(저장소, 8번째)은 (row1, col3).
    assert (r, c) == (1, 3)
    # 팔레트 버튼 키가 보존(테스트 계약).
    assert set(w._shape_tool_buttons) == {"rect", "ellipse", "triangle"}
    assert set(w._sym_buttons) == {"decision", "terminal", "data", "prep", "database"}
    # 버튼 고정 크기 — 패널이 넓어져도 커지거나 벌어지지 않는다(좌측 뭉침).
    b = w._shape_tool_buttons["rect"]
    assert b.minimumWidth() == b.maximumWidth() == 48
    # 속성 패널은 값(hex)이 안 잘리는 최소폭 바닥을 가진다(슬랙 없이 그 아래로 못 좁힘).
    assert w._props_panel._body_layout.itemAt(0).widget().minimumWidth() == 170
    # 패널은 창 리사이즈 후에도 뷰 영역 안쪽에 고정 위치(자유 드래그 없음의 반대증거).
    w.resize(1400, 900)
    w._reposition_panels()
    assert w._left_panel.pos().x() >= w._view.mapTo(w, QPoint(0, 0)).x()
    assert w._props_panel.pos().x() < w.width()
    # 줌 % 리드아웃 — 독립 배지가 아니라 미니맵 패널 제목에 "미니맵 (100%)"로 표기된다
    # (2026-08-01, 사용자 요청 — 제목 클릭이 곧 100%+정중앙 이동, test_zoom_title_click_recenters).
    assert w._minimap_panel._title_lbl.text() == "미니맵 (100%)"
    w._on_wheel_zoom(120)
    assert w._minimap_panel._title_lbl.text() != "미니맵 (100%)"
    w._zoom_reset()
    assert w._minimap_panel._title_lbl.text() == "미니맵 (100%)"




def test_zoom_title_click_recenters():
    # [2026-08-01, 사용자 요청] "%를 누르면 100%+정중앙 이동" — 배율만 리셋되고 스크롤 위치는
    # 그대로 남아 콘텐츠가 화면 밖일 수 있던 문제(사용자 재현 보고) 수정의 회귀 방지.
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 2000, 2000, 100, 60)   # 원점에서 먼 콘텐츠
    w._view.scale(2.5, 2.5)
    w._view.centerOn(0, 0)   # 콘텐츠에서 멀리 팬
    w._zoom_reset()
    assert abs(w._view.transform().m11() - 1.0) < 1e-6
    center_scene = w._view.mapToScene(w._view.viewport().rect().center())
    rect_center = w._scene.itemsBoundingRect().center()
    assert abs(center_scene.x() - rect_center.x()) < 2.0
    assert abs(center_scene.y() - rect_center.y()) < 2.0

    # 제목 클릭 배관(_FloatingPanel.set_title_click) 자체도 확인 — 실제 마우스 없이 이벤트필터
    # 경로만 재현(다른 패널의 제목엔 영향 없어야 함도 함께 확인).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    calls = []
    w._minimap_panel.set_title_click(lambda: calls.append(1))
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0), QPointF(0, 0),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    assert w._minimap_panel.eventFilter(w._minimap_panel._title_lbl, ev) is True
    assert calls == [1]
    assert w._props_panel.eventFilter(w._props_panel._title_lbl, ev) is False   # 다른 패널은 비클릭




def test_left_panel_accordion_collapse_expand_resizes_panel():
    # [캔버스-퍼스트 레이아웃][좌측 패널 아코디언 개편, 2026-08-12] 옛 도형/레이어 탭
    # (QTabWidget → setVisible 토글로 교체했던 2026-07-29 수정)을 아코디언 4섹션으로 대체.
    # 이 회귀 테스트도 같은 계약을 확인한다 — 접힌 섹션을 펼치면 패널이 커지고, 다시 접으면
    # 스턱 없이 원래 크기로 정확히 복원돼야 한다(옛 탭 전환의 레이아웃 무효화 타이밍 함정과
    # 같은 클래스, `_relayout_left_panel`이 같은 activate()→adjustSize() 해법을 재사용).
    # ⚠ show() 필수 — 창을 띄우지 않으면 Qt가 레이아웃 무효화를 다르게(더 늦게) 처리해
    # adjustSize()가 stale한 값으로 멈춘다.
    # ⚠ [실측] `_layers_list`(QListWidget, 커스텀 행 위젯)의 `sizeHintForRow()`는 show() 직후
    # 첫 `.height()` 접근 전까지 실제보다 큰 값을 낸다(이 테스트가 만든 게 아니라
    # `_refresh_layers_panel`이 이미 갖고 있던 특성) — `CanvasWindow.showEvent`가 이제 이
    # settle을 자동으로 해준다(2026-08-12, 좌측 패널 왕복 비교로 처음 드러나 소스에 고정).
    # [2026-08-13] 옛 "flowchart" 섹션은 기본도형에 병합되어 사라졌다 — "layers"(레이어)로
    # 같은 계약을 확인한다("customsym"은 폴더 드롭존 등 동적 콘텐츠라 접기 왕복 시 sizeHint가
    # 자체적으로 안정되지 않아 대상에서 제외 — 실측 확인, `layers`는 정확히 원복됨).
    # 기본값은 펼침 시작(default_collapsed=False)이라 QSettings로 접힘 시작을 강제한다(다른
    # accordion 테스트와 같은 관례 — 실사용 QSettings에 이미 다른 상태가 저장돼 있을 수 있음).
    from PyQt6.QtCore import QSettings
    QSettings("EasyCAD", "EasyCAD").setValue("accordion_collapsed_layers", True)
    w = CanvasWindow(); w.show()
    collapsed_size = w._left_panel.size()
    layers_section = w._left_accordion_sections["layers"]
    assert layers_section._collapsed
    layers_section._toggle()                       # 펼치기
    assert not layers_section._collapsed
    expanded_size = w._left_panel.size()
    assert expanded_size.height() > collapsed_size.height()
    layers_section._toggle()                        # 다시 접기
    assert w._left_panel.size() == collapsed_size   # 왕복 후에도 스턱 없이 원래 크기로 복원
    w._active_doc.dirty = False   # [§8 항목10 Stage C] 이 테스트는 닫기확인창을 검증 대상이 아님
    w.close()
    QSettings("EasyCAD", "EasyCAD").remove("accordion_collapsed_layers")




def test_statusbar_proxy_is_floating_toast():
    # [캔버스-퍼스트 레이아웃] statusBar()는 이제 QMainWindow 실제 상태바가 아니라 하단중앙
    # 토스트 프록시 — 기존 20여 곳의 .showMessage() 호출부를 안 건드리고 그대로 동작해야 한다.
    w = CanvasWindow()
    assert isinstance(w.statusBar(), _ToastLabel)
    w.statusBar().showMessage("테스트 메시지", 3000)
    assert w.statusBar().currentMessage() == "테스트 메시지"
    assert not w._toast.isHidden()   # isVisible()은 헤드리스에서 최상위 미표시로 항상 False




def test_properties_dock_readout():
    # [Phase 6 M2 #2] 속성 dock 편집 컨트롤 — 선택에 맞춰 값·활성 상태가 채워진다.
    from PyQt6.QtGui import QPen
    w = CanvasWindow()
    w._scene.clearSelection(); w._refresh_properties()
    assert w._pf_type.text() == "—"
    # 선택 없으면 편집 컨트롤 비활성.
    assert not w._pf_width.isEnabled() and not w._pf_style.isEnabled()
    assert not w._pf_font.isEnabled()
    # 빨강 두께3 네모 단일 선택 → 값 채워지고 도형 속성 활성, 폰트만 비활성.
    pen = QPen(QColor("#ff0000")); pen.setWidthF(3.0)
    r = _mk_rect(w._scene, pen, 0, 0, 100, 50)
    r.setSelected(True); w._refresh_properties()
    assert w._pf_type.text() == "사각형"
    assert abs(w._pf_width.value() - 3.0) < 1e-6
    assert w._pf_color_val.text() == "#ff0000"
    assert w._pf_style.currentData() == Qt.PenStyle.SolidLine
    assert w._pf_width.isEnabled() and w._pf_style.isEnabled()
    assert not w._pf_font.isEnabled()        # 도형은 폰트 없음
    # 색이 다른 네모 추가 선택 → 색 '혼합' 표시, 두께는 동일 유지.
    pen2 = QPen(QColor("#00ff00")); pen2.setWidthF(3.0)
    r2 = _mk_rect(w._scene, pen2, 200, 0, 100, 50)
    r2.setSelected(True); w._refresh_properties()
    assert w._pf_color_val.text() == "혼합"
    assert abs(w._pf_width.value() - 3.0) < 1e-6
    # [실사용 피드백 2026-08-18] 단일종류 다중선택도 개수를 표시(이전엔 "사각형"만 표시돼
    # 몇 개가 선택됐는지 알 수 없었다).
    assert w._pf_type.text() == "사각형 2개"




def test_props_edit_width_color_font_undoable():
    # [M2 #2] dock 편집이 push_undo_state 경로로 undo/redo 된다(색·두께·폰트).
    w = CanvasWindow()
    it = _mk_pen_rect(w, width=2.0, color="#111111"); it.setSelected(True)
    w._edit_width(7.0)
    assert abs(it.pen().widthF() - 7.0) < 1e-6
    w.undo(); assert abs(it.pen().widthF() - 2.0) < 1e-6
    w.redo(); assert abs(it.pen().widthF() - 7.0) < 1e-6
    w._edit_items([it], lambda x: x.apply_color(QColor("#00ff00")))
    assert it.pen().color().name() == "#00ff00"
    w.undo(); assert it.pen().color().name() == "#111111"
    # 폰트(텍스트 아이템)
    t = _TextItem(QColor("#111111")); t.setPlainText("hi"); t.apply_font_size(16)
    w._scene.addItem(t); w._scene.clearSelection(); t.setSelected(True)
    w._edit_font(28)
    assert t.font().pointSize() == 28
    w.undo(); assert t.font().pointSize() == 16




def test_props_multiselect_width_single_undo():
    # 다중선택 두께 편집 = 전체 적용 + undo 1스텝(각자 원값으로 복원).
    w = CanvasWindow()
    a = _mk_pen_rect(w, width=2.0); b = _mk_pen_rect(w, x=200, width=3.0)
    a.setSelected(True); b.setSelected(True)
    d0 = len(w._undo)
    w._edit_width(8.0)
    assert len(w._undo) == d0 + 1
    assert abs(a.pen().widthF() - 8.0) < 1e-6 and abs(b.pen().widthF() - 8.0) < 1e-6
    w.undo()
    assert abs(a.pen().widthF() - 2.0) < 1e-6 and abs(b.pen().widthF() - 3.0) < 1e-6




def test_props_style_edit_and_ecad_roundtrip():
    # [M2 #2] 선스타일 편집(pen 기반) → undo/redo + .ecad 왕복 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    it = _mk_pen_rect(w); it.setSelected(True)
    di = w._pf_style.findData(Qt.PenStyle.DashLine)
    w._pf_style.setCurrentIndex(di)          # currentIndexChanged → _edit_style
    assert it.pen().style() == Qt.PenStyle.DashLine
    w.undo(); assert it.pen().style() == Qt.PenStyle.SolidLine
    w.redo(); assert it.pen().style() == Qt.PenStyle.DashLine
    p = os.path.join(_TMP, "style_rt.ecad")
    save_document(w._scene, p)
    sc2 = QGraphicsScene(); load_document(sc2, p)
    r2 = [x for x in sc2.items() if isinstance(x, _RectItem)][0]
    assert r2.pen().style() == Qt.PenStyle.DashLine




def test_arrow_style_roundtrip():
    # [M2 #3] 화살표(_ArrowItem·_PolyArrowItem) 몸통 선스타일이 .ecad 왕복에 보존된다.
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    ar = _ArrowItem(QColor("#ff0000"), 4, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0)); ar.apply_style(Qt.PenStyle.DashLine)
    sc.addItem(ar)
    sar = _PolyArrowItem(QColor("#00aa00"), 4, True)
    sar._pts = [QPointF(0, 50), QPointF(80, 50)]; sar.apply_style(Qt.PenStyle.DotLine)
    sc.addItem(sar)
    p = os.path.join(_TMP, "arrow_style_rt.ecad")
    save_document(sc, p)
    sc2 = QGraphicsScene(); load_document(sc2, p)
    a2 = [x for x in sc2.items() if isinstance(x, _ArrowItem)][0]
    s2 = [x for x in sc2.items() if isinstance(x, _PolyArrowItem)][0]
    assert a2._style == Qt.PenStyle.DashLine
    assert s2._style == Qt.PenStyle.DotLine




def test_arrow_style_backcompat_defaults_solid():
    # 옛 .ecad(style 키 없음) 로드 시 화살표는 기본 solid로 안전 복원.
    from PyQt6.QtWidgets import QGraphicsScene
    d = {"type": "arrow", "pos": [0, 0], "p1": [0, 0], "p2": [10, 0],
         "ctrl1": None, "ctrl2": None, "color": "#ff000000", "width": 3, "head": True}
    from easycad.fileio.document import dict_to_item
    it = dict_to_item(d)
    assert it._style == Qt.PenStyle.SolidLine




def test_sarrow_routing_roundtrip():
    # [M4-4 · 통합] _routing(straight/ortho) + 반경이 .ecad 왕복에 보존된다(각짐/둥긂=반경 소유).
    from PyQt6.QtWidgets import QGraphicsScene
    for mode, radius in (("straight", 0.0), ("ortho", 0.0), ("ortho", 10.0)):
        sc = QGraphicsScene()
        sar = _PolyArrowItem(QColor("#123456"), 3, True)
        sar._pts = [QPointF(0, 0), QPointF(80, 40)]
        sar._routing = mode; sar.set_corner_radius(radius)
        sc.addItem(sar)
        p = os.path.join(_TMP, f"routing_{mode}_{radius:.0f}.ecad")
        save_document(sc, p)
        sc2 = QGraphicsScene(); load_document(sc2, p)
        s2 = [x for x in sc2.items() if isinstance(x, _PolyArrowItem)][0]
        assert (s2._routing, s2._curve_r) == (mode, radius), (mode, radius)




def test_sarrow_routing_legacy_three_values():
    # [M4-4 · 통합] 옛 3값 .ecad 하위호환: "ortho"(옛 직각 엘보)는 반경 0으로 읽어야 예전처럼
    # 각지게 그려진다(기본 반경으로 읽으면 옛 도면의 직각 커넥터가 전부 둥글어짐). "ortho_curved"는
    # 반경 있는 직교로 흡수. set_routing도 옛 값을 별칭으로 받는다.
    from easycad.fileio.document import dict_to_item
    base = {"type": "sarrow", "pos": [0, 0], "pts": [[0, 0], [50, 0], [50, 30]],
            "color": "#ff000000", "width": 3, "head": True}
    sharp = dict_to_item({**base, "routing": "ortho"})            # 옛 직각(반경 키 없음)
    assert (sharp._routing, sharp._curve_r) == ("ortho", 0.0)
    curved = dict_to_item({**base, "routing": "ortho_curved"})    # 옛 곡선
    assert (curved._routing, curved._curve_r) == ("ortho", _PolyArrowItem._CORNER_R)
    it = _PolyArrowItem(QColor("#111111"), 3, True)
    it.set_routing("ortho_curved")                                # 별칭 → ortho
    assert it._routing == "ortho"




def test_curve_radius_model():
    # [M4-4 ⓑ] 곡선 반경 — 0이면 원호가 사라져 직각(요소 수 감소), 상한은 클램프.
    sar = _PolyArrowItem(QColor("#111111"), 3, True)
    sar._pts = [QPointF(0, 0), QPointF(50, 0), QPointF(50, 40)]
    sar._routing = "ortho"
    n_curved = sar._rounded_polyline_path().elementCount()
    sar.set_corner_radius(0)
    assert sar._curve_r == 0.0
    assert sar._rounded_polyline_path().elementCount() < n_curved   # 원호(quadTo) 없음 = 직각
    sar.set_corner_radius(999)
    assert sar._curve_r == _PolyArrowItem._CURVE_R_MAX               # 상한 클램프
    assert sar.clone()._curve_r == _PolyArrowItem._CURVE_R_MAX       # 복제도 반경 유지




def test_curve_radius_roundtrip_and_backcompat():
    # [M4-4 ⓑ] 반경이 .ecad 왕복에 보존되고, 옛 파일(curve_r 키 없음)은 기본값으로 안전 복원.
    from PyQt6.QtWidgets import QGraphicsScene
    from easycad.fileio.document import dict_to_item, item_to_dict
    sc = QGraphicsScene()
    sar = _PolyArrowItem(QColor("#123456"), 3, True)
    sar._pts = [QPointF(0, 0), QPointF(80, 0), QPointF(80, 40)]
    sar._routing = "ortho"; sar.set_corner_radius(4)
    sc.addItem(sar)
    p = os.path.join(_TMP, "curve_r.ecad")
    save_document(sc, p)
    sc2 = QGraphicsScene(); load_document(sc2, p)
    assert [x for x in sc2.items() if isinstance(x, _PolyArrowItem)][0]._curve_r == 4.0

    d = item_to_dict(sar); d.pop("curve_r")            # 옛 파일 흉내(routing="ortho"=옛 직각)
    assert dict_to_item(d)._curve_r == 0.0




def test_properties_panel_curve_radius_stepper():
    # [M4-4 ⓑ → 미니패널 통합 2026-07-31] 반경 스테퍼: 직교 커넥터 단일 선택 시 노출, 값 변경이
    # 반경에 반영되고 undo로 복원. 옛 선택-추종 플로팅 툴바에서 속성 dock 행으로 이관.
    w = CanvasWindow()
    ar = _PolyArrowItem(QColor("#111111"), 3.0, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 60))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar); ar.setSelected(True)
    w._floating_set_arrow_kind("ortho")         # 직각 커넥터 → 각짐(반경) 스테퍼 대상
    assert not w._pf_radius.isHidden()
    # 키보드 포커스를 가져가면 Del·Ctrl+D(뷰 keyPressEvent 처리)가 캔버스로 안 간다 → NoFocus 고정.
    assert w._pf_radius.focusPolicy() == Qt.FocusPolicy.NoFocus
    poly = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)][0]
    assert w._pf_radius.value() == int(_PolyArrowItem._CORNER_R)   # 현재 값 동기화
    w._pf_radius.setValue(2)                                       # 사용자 조작
    assert poly._curve_r == 2.0 and w.current_curve_r == 2.0          # sticky 반영
    w.undo()
    assert poly._curve_r == _PolyArrowItem._CORNER_R
    # 곡선 화살표에서는 각짐 조절이 없어 스테퍼를 숨긴다.
    w._floating_set_arrow_kind("curved")
    assert w._pf_radius.isHidden()




def test_arrow_kind_menu_labels():
    # [화살표 통합] 종류 메뉴는 직선·곡선·직각 3개. 상단 툴바가 아니라 여기서 종류를 고른다.
    w = CanvasWindow()
    assert [a.text() for a in w._build_routing_menu().actions()] == ["직선", "곡선", "직각"]




def test_straight_kind_flattens_on_draw():
    # [화살표 통합] sticky 종류가 '직선'이면 도형에 스냅돼 자동 S자로 그려진 화살표라도 곧게 편다.
    # '곡선'이면 자동 S자 그대로 둔다(그린 대로).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, _click, _move, drag_move, _d = _draw_helpers(view)

    def draw_arrow_to_border():
        press(QPointF(-50, 30)); drag_move(QPointF(295, 30)); release(QPointF(305, 30))
        return [it for it in w._scene.items() if isinstance(it, _ArrowItem)]

    w.current_arrow_kind = "curved"; w.set_tool("arrow")
    a = draw_arrow_to_border()[-1]
    assert a._ctrl1 is not None                            # 곡선 종류 → 자동 S자 유지

    for it in list(w._scene.items()):
        if isinstance(it, _ArrowItem):
            w._scene.removeItem(it)
    w.current_arrow_kind = "straight"; w.set_tool("arrow")
    b = draw_arrow_to_border()[-1]
    assert b._ctrl1 is None                                # 직선 종류 → 곧게 폄




def test_straight_kind_flattens_live_preview():
    # [화살표 통합 · 버그] sticky 종류가 '직선'이면 릴리스 전 드래그 중 미리보기도 곧아야 한다.
    # 종전엔 _update_arrow_draw가 종류를 안 보고 스냅 시 자동 S자를 그렸다가 릴리스에서만
    # _apply_arrow_kind_on_create가 곧게 펴, 드래그 중엔 곡선 → 뗄 때 직선으로 바뀌어 보였다
    # (2026-07-27 사용자 GUI 보고).
    w = CanvasWindow(); w.show(); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, _click, _move, drag_move, _d = _draw_helpers(view)

    w.current_arrow_kind = "straight"; w.set_tool("arrow")
    press(QPointF(-50, 30))
    drag_move(QPointF(295, 30))   # 테두리 근처 — 자유였다면 자동 S자가 걸릴 지점
    assert view._temp._ctrl1 is None and view._temp._ctrl2 is None   # 드래그 중에도 이미 직선
    release(QPointF(305, 30))
    a = [it for it in w._scene.items() if isinstance(it, _ArrowItem)][-1]
    assert a._ctrl1 is None                                # 릴리스 후에도 그대로 직선




def test_sarrow_routing_backcompat():
    # [M4-4] 옛 .ecad(routing 키 없음): auto_route→ortho / 없으면 straight로 유추(무손실).
    from easycad.fileio.document import dict_to_item
    base = {"type": "sarrow", "pos": [0, 0], "pts": [[0, 0], [50, 0], [50, 30]],
            "color": "#ff000000", "width": 3, "head": True}
    it_auto = dict_to_item({**base, "auto_route": True})
    assert it_auto._routing == "ortho"
    it_manual = dict_to_item({**base, "auto_route": False})
    assert it_manual._routing == "straight"




def test_sarrow_set_routing_regenerates():
    # [M4-4] set_routing: straight=2점 직선 / ortho=자유 끝점 사이 직교(대각→계단).
    sar = _PolyArrowItem(QColor("#111111"), 3, True)
    sar.set_points(QPointF(0, 0), QPointF(100, 60))
    sar.set_routing("ortho")
    assert len(sar._pts) >= 3                 # 대각선이 직교 계단으로
    assert all(abs(a.x() - b.x()) < 1e-6 or abs(a.y() - b.y()) < 1e-6
               for a, b in zip(sar._pts[:-1], sar._pts[1:]))   # 모든 변이 수직/수평
    sar.set_routing("straight")
    assert len(sar._pts) == 2                  # 다시 2점 직선




def test_sarrow_straight_routing_survives_reroute():
    # [M4-4] straight 라우팅 + 바인딩 커넥터는 도형 이동(reroute) 후에도 2점 직선(엘보로 안 튐).
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    a = _RectItem(QRectF(0, 0, 80, 50)); a.setPos(QPointF(0, 0)); sc.addItem(a)
    b = _RectItem(QRectF(0, 0, 80, 50)); b.setPos(QPointF(300, 20)); sc.addItem(b)
    it = _PolyArrowItem(QColor("#111111"), 3, True)
    pa, pb = QPointF(80, 25), QPointF(0, 25)
    it.set_points(a.mapToScene(pa), b.mapToScene(pb))
    it.set_bound(0, a, pa); it.set_bound(1, b, pb)
    it._routing = "straight"; it._auto_route = True
    sc.addItem(it)
    b.setPos(QPointF(300, 140))               # 도형 이동 → reroute
    it.reroute()
    assert it._routing == "straight" and len(it._pts) == 2   # 직선 유지
    it.set_routing("ortho"); it.reroute()     # ortho로 바꾸면 엘보 재계산
    assert len(it._pts) >= 3




def test_sarrow_one_bound_stays_ortho_on_move():
    # [M4-4 ⑦] 한쪽만 바인딩된 직교 커넥터도 도형 이동(reroute) 후 직교 유지(대각선 안 생김).
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    a = _RectItem(QRectF(0, 0, 80, 50)); a.setPos(QPointF(0, 0)); sc.addItem(a)
    it = _PolyArrowItem(QColor("#111111"), 3, True)
    pa = QPointF(80, 25)
    it.set_points(a.mapToScene(pa), QPointF(400, 200))   # 끝은 자유
    it.set_bound(0, a, pa)
    it._routing = "ortho"; it._auto_route = True
    sc.addItem(it); it.build_elbow()
    a.setPos(QPointF(0, 150))                            # 바인딩 도형 이동 → reroute
    it.reroute()
    assert all(abs(p1.x() - p2.x()) < 1e-6 or abs(p1.y() - p2.y()) < 1e-6
               for p1, p2 in zip(it._pts[:-1], it._pts[1:]))   # 모든 변 직교




def test_sarrow_manual_ortho_stays_ortho_on_move():
    # [M4-4 ⑦] 세그먼트 드래그(수동 직교, auto_route off)한 커넥터도 도형 이동 시 스텁을 직교로 유지.
    from PyQt6.QtWidgets import QGraphicsScene
    sc = QGraphicsScene()
    a = _RectItem(QRectF(0, 0, 80, 50)); a.setPos(QPointF(0, 0)); sc.addItem(a)
    b = _RectItem(QRectF(0, 0, 80, 50)); b.setPos(QPointF(300, 20)); sc.addItem(b)
    it = _PolyArrowItem(QColor("#111111"), 3, True)
    pa, pb = QPointF(80, 25), QPointF(0, 25)
    it.set_points(a.mapToScene(pa), b.mapToScene(pb))
    it.set_bound(0, a, pa); it.set_bound(1, b, pb)
    it._routing = "ortho"; it._auto_route = True
    sc.addItem(it); it.build_elbow()
    it._begin_segment_drag(1); it._drag_segment_to(QPointF(150, 200)); it._end_segment_drag()
    assert not it._auto_route                          # 수동 직교로 전환
    b.setPos(QPointF(300, 260)); it.reroute()          # 도형 이동
    assert all(abs(p1.x() - p2.x()) < 1e-6 or abs(p1.y() - p2.y()) < 1e-6
               for p1, p2 in zip(it._pts[:-1], it._pts[1:]))   # 여전히 전부 직교




def test_reroute_rigid_translate_skips_astar_when_both_ends_selected():
    # [성능 최적화 2026-08-13] 양끝 도형이 둘 다 선택돼 같은 델타로 함께 움직이면(다중선택
    # 그룹 드래그), reroute()가 build_elbow(A*)를 다시 안 돌리고 _pts를 그 델타만큼
    # 평행이동만 해야 한다 — 결과 기하는 일반 경로(build_elbow)와 동일해야 함.
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsItem
    from unittest.mock import patch
    sc = QGraphicsScene()
    sel_flags = QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    a = _RectItem(QRectF(0, 0, 80, 50)); a.setPos(QPointF(0, 0)); a.setFlags(sel_flags); sc.addItem(a)
    b = _RectItem(QRectF(0, 0, 80, 50)); b.setPos(QPointF(300, 20)); b.setFlags(sel_flags); sc.addItem(b)
    it = _PolyArrowItem(QColor("#111111"), 3, True)
    pa, pb = QPointF(80, 25), QPointF(0, 25)
    it.set_points(a.mapToScene(pa), b.mapToScene(pb))
    it.set_bound(0, a, pa); it.set_bound(1, b, pb)
    it._routing = "ortho"; it._auto_route = True
    sc.addItem(it); it.build_elbow()
    pts_before = list(it._pts)

    a.setSelected(True); b.setSelected(True)
    a.setPos(a.pos() + QPointF(15, 7)); b.setPos(b.pos() + QPointF(15, 7))
    with patch.object(_PolyArrowItem, "build_elbow", autospec=True) as mock_elbow:
        changed = it.reroute()
    assert changed
    assert mock_elbow.call_count == 0                     # A* 재탐색 없이 끝남
    expect = [QPointF(p.x() + 15, p.y() + 7) for p in pts_before]
    assert all(abs(p1.x() - p2.x()) < 1e-6 and abs(p1.y() - p2.y()) < 1e-6
               for p1, p2 in zip(it._pts, expect))         # 순수 평행이동과 일치


def test_reroute_falls_back_to_astar_when_only_one_end_selected():
    # 한쪽만 선택(마퀴가 한쪽만 잡거나 독립 이동)돼 델타가 다르면 안전하게 기존 경로(끝점 추종
    # + build_elbow 재계산)로 폴백해야 한다 — 강체 지름길을 잘못 타면 안 됨.
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsItem
    sc = QGraphicsScene()
    sel_flags = QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    a = _RectItem(QRectF(0, 0, 80, 50)); a.setPos(QPointF(0, 0)); a.setFlags(sel_flags); sc.addItem(a)
    b = _RectItem(QRectF(0, 0, 80, 50)); b.setPos(QPointF(300, 20)); b.setFlags(sel_flags); sc.addItem(b)
    it = _PolyArrowItem(QColor("#111111"), 3, True)
    pa, pb = QPointF(80, 25), QPointF(0, 25)
    it.set_points(a.mapToScene(pa), b.mapToScene(pb))
    it.set_bound(0, a, pa); it.set_bound(1, b, pb)
    it._routing = "ortho"; it._auto_route = True
    sc.addItem(it); it.build_elbow()

    a.setSelected(True)   # b는 미선택
    a.setPos(a.pos() + QPointF(15, 7))
    it.reroute()
    # 시작점은 a의 새 부착점을 정확히 추종(강체 평행이동이 아니라 재추적 경로여야 함).
    start_scene = it.mapToScene(it._pts[0])
    assert abs(start_scene.x() - a.mapToScene(pa).x()) < 1e-6
    assert abs(start_scene.y() - a.mapToScene(pa).y()) < 1e-6
    # 끝점은 b(안 움직임)를 그대로 추종.
    end_scene = it.mapToScene(it._pts[-1])
    assert abs(end_scene.x() - b.mapToScene(pb).x()) < 1e-6
    assert abs(end_scene.y() - b.mapToScene(pb).y()) < 1e-6


def test_sarrow_segment_drag_snaps_straight():
    # [M4-4 ①b] 세그먼트 드래그가 끝점 축에 가까우면 착 붙어 완벽한 직선이 된다.
    it = _PolyArrowItem(QColor("#111111"), 3, True)
    it._pts = [QPointF(0, 0), QPointF(0, 40), QPointF(200, 40), QPointF(200, 0)]  # U자
    it._routing = "ortho"
    it._begin_segment_drag(1)                    # 중간 수평 변(y=40) 잡기
    it._drag_segment_to(QPointF(100, 3))         # y=0(끝점 축)에서 3px 이내로 끌기 → 스냅
    it._end_segment_drag()
    assert any(abs(p.y()) < 1e-6 for p in it._pts[1:-1]) or len(it._pts) == 2  # 끝점 축(y=0)에 스냅




def test_sarrow_curved_rounded_path():
    # [M4-4] ortho_curved 둥근 경로 — 3정점 이상이면 원호(quadTo)가 들어가 요소 수가 늘어난다.
    sar = _PolyArrowItem(QColor("#111111"), 3, True)
    sar._pts = [QPointF(0, 0), QPointF(50, 0), QPointF(50, 40)]
    straight = sar._polyline_path()
    rounded = sar._rounded_polyline_path()
    assert rounded.elementCount() > straight.elementCount()




def test_arrow_style_edit_and_undo():
    # [M2 #3] 속성 dock 선스타일 콤보가 화살표에도 적용되고 undo/redo 된다.
    w = CanvasWindow()
    ar = _ArrowItem(QColor("#111111"), 3, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar); ar.setSelected(True)
    w._refresh_properties()
    assert w._pf_style.isEnabled()                 # 화살표도 선스타일 콤보 활성
    di = w._pf_style.findData(Qt.PenStyle.DashLine)
    w._pf_style.setCurrentIndex(di)                # currentIndexChanged → _edit_style
    assert ar._style == Qt.PenStyle.DashLine
    w.undo(); assert ar._style == Qt.PenStyle.SolidLine
    w.redo(); assert ar._style == Qt.PenStyle.DashLine




def test_dxf_arrow_linetype_roundtrip():
    # [M2 #3] 화살표 점선이 DXF linetype으로 실려 export→import 왕복에 보존된다.
    from PyQt6.QtWidgets import QGraphicsScene
    from easycad.fileio.dxf_import import import_dxf
    sc = QGraphicsScene()
    sar = _PolyArrowItem(QColor("#ffff00ff"), 5, True)
    sar._pts = [QPointF(0, 0), QPointF(120, 0)]; sar.apply_style(Qt.PenStyle.DashLine)
    sc.addItem(sar)
    ar = _ArrowItem(QColor("#ff00ff00"), 5, True)
    ar.set_points(QPointF(0, 200), QPointF(120, 200)); ar.apply_style(Qt.PenStyle.DashDotLine)
    sc.addItem(ar)
    path = os.path.join(_TMP, "arrow_linetype.dxf")
    assert export_dxf(sc, path)
    sc2 = QGraphicsScene(); import_dxf(sc2, path)
    s2 = [x for x in sc2.items() if isinstance(x, _PolyArrowItem)]
    a2 = [x for x in sc2.items() if isinstance(x, _ArrowItem)]
    assert s2 and s2[0]._style == Qt.PenStyle.DashLine
    assert a2 and a2[0]._style == Qt.PenStyle.DashDotLine




def test_dxf_penshape_linetype_roundtrip():
    # [M2 #3] pen 기반 도형(네모·선·원)의 점선도 DXF linetype으로 왕복 보존(버그: 이전엔 실선화).
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    from easycad.fileio.dxf_import import import_dxf
    def dpen(style):
        p = QPen(QColor("#ff0000")); p.setWidthF(2.0); p.setStyle(style); return p
    sc = QGraphicsScene()
    rect = _RectItem(QRectF(0, 0, 100, 60)); rect.setPen(dpen(Qt.PenStyle.DashLine))
    rect.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sc.addItem(rect)
    line = _LineItem(QLineF(0, 200, 150, 260)); line.setPen(dpen(Qt.PenStyle.DotLine)); sc.addItem(line)
    ell = _EllipseItem(QRectF(0, 400, 80, 80)); ell.setPen(dpen(Qt.PenStyle.DashDotLine))
    ell.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sc.addItem(ell)
    path = os.path.join(_TMP, "penshape_linetype.dxf")
    assert export_dxf(sc, path)
    sc2 = QGraphicsScene(); import_dxf(sc2, path)
    r2 = [x for x in sc2.items() if isinstance(x, _RectItem)][0]
    l2 = [x for x in sc2.items() if isinstance(x, _LineItem)][0]
    e2 = [x for x in sc2.items() if isinstance(x, _EllipseItem)][0]
    assert r2.pen().style() == Qt.PenStyle.DashLine
    assert l2.pen().style() == Qt.PenStyle.DotLine
    assert e2.pen().style() == Qt.PenStyle.DashDotLine




def test_dxf_lineweight_for_external_cad():
    # [M2 #3] export가 표준 lineweight를 병행 저장(외부 CAD 두께 표시) + $LWDISPLAY 켜짐.
    # XDATA(1040) 무손실 왕복은 그대로 유지(우리 import는 여전히 정확한 px 복원).
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    from easycad.fileio.dxf_import import import_dxf
    from easycad.fileio.dxf_export import _px_to_lineweight
    import ezdxf
    assert _px_to_lineweight(3.0) == 30 and _px_to_lineweight(0.5) == 5
    sc = QGraphicsScene()
    rect = _RectItem(QRectF(0, 0, 100, 60))
    p = QPen(QColor("#ff0000")); p.setWidthF(3.0); rect.setPen(p)
    rect.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sc.addItem(rect)
    path = os.path.join(_TMP, "lineweight.dxf")
    assert export_dxf(sc, path)
    doc = ezdxf.readfile(path)
    assert doc.header["$LWDISPLAY"] == 1
    lws = [e.dxf.lineweight for e in doc.modelspace() if e.dxftype() == "LWPOLYLINE"]
    assert 30 in lws, lws
    # XDATA 왕복은 무손실 유지 — 우리 import가 정확히 3.0px 복원.
    sc2 = QGraphicsScene(); import_dxf(sc2, path)
    r2 = [x for x in sc2.items() if isinstance(x, _RectItem)][0]
    assert abs(r2.pen().widthF() - 3.0) < 1e-6




def test_arrow_sticky_style_on_draw():
    # [M2 #3] 선스타일을 점선으로 바꾼 뒤 새로 그리는 화살표도 그 스타일로 시작(sticky).
    # _begin_draw 초크포인트가 current_style을 스탬프한다(화살표는 make_pen 밖).
    w = CanvasWindow()
    w.current_style = Qt.PenStyle.DashLine
    ar = _ArrowItem(w.current_color, w.current_width, True)
    w._view._begin_draw(ar)
    assert ar._style == Qt.PenStyle.DashLine
    sar = _PolyArrowItem(w.current_color, w.current_width, True)
    w._view._begin_draw(sar)
    assert sar._style == Qt.PenStyle.DashLine




def test_duplicate_offset():
    # [M2 #3] Ctrl+D 복제 — 개수 +1, (20,20) 오프셋, 클립보드 미오염, undo 1스텝.
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=10, y=10); it.setSelected(True)
    n0 = len(w._scene.items()); d0 = len(w._undo)
    w.duplicate_selection()
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    assert len(w._scene.items()) == n0 + 1 and len(rects) == 2
    dup = [r for r in rects if r is not it][0]
    assert abs(dup.pos().x() - (it.pos().x() + 20)) < 1e-6
    assert abs(dup.pos().y() - (it.pos().y() + 20)) < 1e-6
    assert dup.isSelected() and not it.isSelected()   # 사본만 선택
    assert len(w._undo) == d0 + 1
    w.undo(); assert len([x for x in w._scene.items() if isinstance(x, _RectItem)]) == 1




def test_duplicate_regroups_copied_group_members():
    # [편의기능] 그룹을 통째로 Ctrl+D 복제하면, clone()이 _group_id를 안 옮겨서 사본이
    # 그룹 해제 상태가 되던 버그. 사본끼리는 원본과 다른 새 그룹id로 묶여야 한다
    # (원본 gid를 그대로 쓰면 사본이 원본 그룹에 합류해 6개가 한 그룹이 되어 버린다).
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=100, y=0)
    a.setSelected(True); b.setSelected(True)
    w.group_selection()
    orig_gid = a._group_id
    w.duplicate_selection()
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    assert len(rects) == 4
    new_a = [r for r in rects if r is not a and r.rect() == a.rect()][0]
    new_b = [r for r in rects if r is not b and r.rect() == b.rect()][0]
    assert a._group_id == orig_gid and b._group_id == orig_gid          # 원본 불변
    assert new_a._group_id is not None and new_a._group_id == new_b._group_id
    assert new_a._group_id != orig_gid                                  # 원본 그룹과 분리된 새 그룹




def test_duplicate_rebinds_arrow_within_group():
    # 함께 선택한 도형+화살표를 Ctrl+D로 복제하면, 사본 화살표는 사본 도형에 붙어야 한다
    # (원본 도형 참조를 그대로 들고 있으면 원본을 옮길 때 사본 화살표가 딸려온다 — 버그).
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=20)
    ar = _ArrowItem(QColor("#111111"), 3, True)
    pa, pb = QPointF(40, 15), QPointF(0, 15)
    ar.set_points(a.mapToScene(pa), b.mapToScene(pb))
    ar.set_bound(0, a, pa); ar.set_bound(1, b, pb)
    w._scene.addItem(ar)
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    w.duplicate_selection()
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    arrows = [x for x in w._scene.items() if isinstance(x, _ArrowItem)]
    assert len(rects) == 4 and len(arrows) == 2
    new_ar = [x for x in arrows if x is not ar][0]
    # _mk_pen_rect는 pos()가 아니라 rect() 로컬좌표에 x/y를 싣는다 — rect()로 원본 대응관계 식별.
    new_a = [r for r in rects if r is not a and r.rect() == a.rect()][0]
    new_b = [r for r in rects if r is not b and r.rect() == b.rect()][0]
    assert new_ar._bind1 is new_a and new_ar._bind2 is new_b   # 사본끼리 재연결
    assert ar._bind1 is a and ar._bind2 is b                   # 원본은 불변

    # 대조군: 도형 없이 화살표만 복제하면 배치 밖 도형이라 원본 바인딩 유지(기존 동작 보존).
    w2 = CanvasWindow()
    a2 = _mk_pen_rect(w2, x=0, y=0); b2 = _mk_pen_rect(w2, x=300, y=20)
    ar2 = _ArrowItem(QColor("#111111"), 3, True)
    ar2.set_points(a2.mapToScene(pa), b2.mapToScene(pb))
    ar2.set_bound(0, a2, pa); ar2.set_bound(1, b2, pb)
    w2._scene.addItem(ar2)
    ar2.setSelected(True)
    w2.duplicate_selection()
    new_ar2 = [x for x in w2._scene.items() if isinstance(x, _ArrowItem) and x is not ar2][0]
    assert new_ar2._bind1 is a2 and new_ar2._bind2 is b2




def test_copy_paste_rebinds_arrow_within_group():
    # copy_selection + paste_selection도 동일 — 사본끼리 재연결(여러 번 붙여넣어도 매번 정확).
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=20)
    ar = _ArrowItem(QColor("#111111"), 3, True)
    pa, pb = QPointF(40, 15), QPointF(0, 15)
    ar.set_points(a.mapToScene(pa), b.mapToScene(pb))
    ar.set_bound(0, a, pa); ar.set_bound(1, b, pb)
    w._scene.addItem(ar)
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    w.copy_selection()
    w.paste_selection()
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    arrows = [x for x in w._scene.items() if isinstance(x, _ArrowItem)]
    assert len(rects) == 4 and len(arrows) == 2
    new_ar = [x for x in arrows if x is not ar][0]
    assert new_ar._bind1 in rects and new_ar._bind1 is not a
    assert new_ar._bind2 in rects and new_ar._bind2 is not b
    assert new_ar._bind1 is not new_ar._bind2

    w.paste_selection()   # 두 번째 붙여넣기도 사본끼리 정확히 재연결되는지
    arrows2 = [x for x in w._scene.items() if isinstance(x, _ArrowItem)]
    assert len(arrows2) == 3
    newest_ar = [x for x in arrows2 if x not in (ar, new_ar)][0]
    rects2 = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    assert newest_ar._bind1 in rects2 and newest_ar._bind2 in rects2
    assert newest_ar._bind1 is not newest_ar._bind2




def test_bulk_select_avoids_quadratic_property_refresh():
    # [성능조사 2026-08-01] paste_selection/duplicate_selection/select_all이 새 아이템마다
    # setSelected(True)를 개별 호출하면 selectionChanged→_refresh_properties가 매번 그 시점까지
    # 선택된 전체를 다시 읽어 O(n²)가 됐다(cProfile 실측: 300개 붙여넣기서 _read_props
    # 45,150회 = 1+2+...+300). _bulk_select로 시그널을 묶어 마지막에 한 번만 갱신되는지 확인
    # (호출 횟수를 n과 무관한 상수로 단언 — 회귀 시 n에 비례해 폭증).
    calls = []
    orig = CanvasWindow._refresh_properties
    def wrapped(self):
        calls.append(1)
        return orig(self)
    CanvasWindow._refresh_properties = wrapped
    try:
        w = CanvasWindow()   # __init__이 selectionChanged를 wrapped 바인딩으로 연결
        items = [_mk_pen_rect(w, x=i * 60, y=0) for i in range(60)]
        calls.clear()
        w._bulk_select(items)
    finally:
        CanvasWindow._refresh_properties = orig
    assert len(calls) <= 2, calls   # n=60에 비례하면 60+회가 됐을 것
    assert all(it.isSelected() for it in items)




def test_paste_many_items_all_selected_and_fast_path():
    # 대량 붙여넣기 후에도 전부 선택 상태가 되는지(=_bulk_select가 개별 setSelected와
    # 동일한 최종 결과를 내는지) — 성능 최적화가 정확성을 깨지 않았는지의 핵심 확인.
    w = CanvasWindow()
    src = [_mk_pen_rect(w, x=i * 60, y=0) for i in range(50)]
    for it in src:
        it.setSelected(True)
    w.copy_selection()
    w.paste_selection()
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    assert len(rects) == 100
    new_items = [r for r in rects if r not in src]
    assert len(new_items) == 50
    assert all(it.isSelected() for it in new_items)
    assert not any(it.isSelected() for it in src)   # 원본은 선택 해제(기존 동작 불변)




def test_rubber_band_bulk_select_still_syncs_groups():
    # [성능조사 2026-08-01] _apply_rubber_selection도 같은 O(n²) 패턴을 owner._bulk_select로
    # 옮겼다 — 드래그가 그룹 멤버 중 하나만 걸쳐도 _sync_group_selection이 여전히 그룹 전체를
    # 딸려오는지(배치 최적화가 이 기능을 깨지 않았는지) 확인.
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=500, y=0)
    a.setSelected(True); b.setSelected(True)
    w.group_selection()
    view = w._view
    view._rb_base = []
    # a만 걸치는 작은 창(window) 선택 — b는 범위 밖.
    view._rb_scene_rect = lambda: QRectF(-10, -10, 60, 50)
    view._rb_is_window = lambda: True
    view._rb_origin = QPointF(0, 0); view._rb_current = QPointF(1, 1)
    view._apply_rubber_selection()
    assert a.isSelected() and b.isSelected()   # 그룹 동반선택으로 b도 딸려옴




def test_select_all_bulk_selects_everything():
    w = CanvasWindow()
    items = [_mk_pen_rect(w, x=i * 60, y=0) for i in range(30)]
    w.select_all()
    assert all(it.isSelected() for it in items)




def test_shape_palette_arms_tool():
    # 팔레트 네모 버튼 클릭 → rect 도구 무장 + 버튼 체크 동기화. 단축키 경로도 유지.
    w = CanvasWindow()
    w._shape_tool_buttons["rect"].click()
    assert w.current_tool == "rect" and w._shape_tool_buttons["rect"].isChecked()
    w.set_tool("select")
    assert not w._shape_tool_buttons["rect"].isChecked()
    # 심볼 무장(팔레트 버튼은 없어졌지만 백엔드 도구는 유지 — Mermaid 가져오기 등에서 사용)
    # 시에도 기본 버튼은 해제 유지.
    w.set_tool("sym:decision")
    assert not w._shape_tool_buttons["rect"].isChecked()




def test_palette_drag_drop_creates_shape():
    # [M3 #17] 팔레트 버튼을 캔버스로 드래그앤드롭 → 놓은 위치 중심에 기본 크기 도형 생성.
    from easycad.canvas.host_widgets import _PALETTE_MIME, _PaletteButton
    from PyQt6.QtCore import QMimeData
    w = CanvasWindow()
    # 팔레트 버튼이 draggable(_PaletteButton)이며 tool_key를 싣는다.
    assert isinstance(w._shape_tool_buttons["rect"], _PaletteButton)
    assert w._shape_tool_buttons["rect"]._drag_tool_key == "rect"
    # 심볼 팔레트 버튼은 없어졌지만, 백엔드 도구(sym:*)는 유지 — mime 왕복은 도구 키만 검증.
    # QDrag가 싣는 mime 왕복(dropEvent 디코드 경로와 동일).
    md = QMimeData(); md.setData(_PALETTE_MIME, "sym:decision".encode("utf-8"))
    assert bytes(md.data(_PALETTE_MIME)).decode("utf-8") == "sym:decision"

    # 생성: 드롭 지점이 도형 중심 + 선택 + undo 1스텝.
    d0 = len(w._undo)
    r = w._create_shape_at("rect", QPointF(200, 100))
    assert isinstance(r, _RectItem) and r.isSelected()
    assert _close(r.mapToScene(r.rect().center()), QPointF(200, 100))
    assert len(w._undo) == d0 + 1
    w.undo(); assert r not in w._scene.items()
    # 원·심볼·미지원 키.
    assert isinstance(w._create_shape_at("ellipse", QPointF(0, 0)), _EllipseItem)
    s = w._create_shape_at("sym:decision", QPointF(0, 0))
    assert isinstance(s, _SymbolItem) and s._kind == "decision"
    assert w._create_shape_at("bogus", QPointF(0, 0)) is None

    # 뷰포트 이벤트 필터가 팔레트 드롭을 받아 생성(뷰가 가로채기 전 처리).
    from PyQt6.QtGui import QDropEvent
    from PyQt6.QtCore import QEvent
    md2 = QMimeData(); md2.setData(_PALETTE_MIME, b"ellipse")
    de = QDropEvent(QPointF(30, 40), Qt.DropAction.CopyAction, md2,
                    Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QEvent.Type.Drop)
    n1 = len([x for x in w._scene.items() if isinstance(x, _EllipseItem)])
    assert w.eventFilter(w._view.viewport(), de) is True
    assert len([x for x in w._scene.items() if isinstance(x, _EllipseItem)]) == n1 + 1




def test_rmb_busy_cancel_vs_idle_pan():
    # [M3 #16] 우클릭 상태 분기: BUSY(무장)=취소 / 유휴=드래그 팬(release로 메뉴/팬 분기).
    w = CanvasWindow(); v = w._view
    # BUSY: 그리기 도구 무장 → 우클릭 press = 취소(도구 select 복귀), 팬/메뉴 후보 아님.
    w.set_tool("rect")
    assert v._rmb_is_busy()
    _rmb(v, "press", QPointF(100, 100))
    assert w.current_tool == "select" and v._rmb_press is None
    # IDLE: 우클릭 press → press 지점 기록(팬/메뉴 후보), 도구 유지.
    assert not v._rmb_is_busy()
    _rmb(v, "press", QPointF(100, 100))
    assert v._rmb_press is not None and v._rmb_panning is False
    # 임계(6px) 초과 드래그(로컬 이동) → 팬 시작.
    _rmb(v, "move", QPointF(140, 140), QPointF(140, 140))
    assert v._rmb_panning is True and w._pan_last is not None
    # 릴리스(팬 후) → 상태 리셋(메뉴 안 뜸).
    _rmb(v, "release", QPointF(140, 140), QPointF(140, 140))
    assert v._rmb_press is None and v._rmb_panning is False




def test_rmb_context_menu_states():
    # [M3 #16] 컨텍스트 메뉴 구성 — 선택/클립보드 유무로 항목이 달라진다. 액션은 기존 편집 경로.
    w = CanvasWindow()
    labels = lambda: [a.text() for a in w._build_context_menu().actions() if not a.isSeparator()]
    assert labels() == ["전체 선택\tCtrl+A"]                       # 빈 캔버스
    it = _mk_pen_rect(w); it.setSelected(True)
    assert labels()[:4] == ["복사\tCtrl+C", "잘라내기", "복제\tCtrl+D", "삭제\tDel"]
    w.copy_selection()
    assert "붙여넣기\tCtrl+V" in labels()                          # 클립 채우면 붙여넣기
    # delete_selection·undo 왕복(메뉴 액션이 기존 undo 경로를 탄다).
    w._scene.clearSelection(); it.setSelected(True)
    n0 = len([x for x in w._scene.items() if isinstance(x, _RectItem)])
    w.delete_selection()
    assert len([x for x in w._scene.items() if isinstance(x, _RectItem)]) == n0 - 1
    w.undo()
    assert len([x for x in w._scene.items() if isinstance(x, _RectItem)]) == n0
    # select_all → 선택 가능한 모든 아이템 선택.
    w._scene.clearSelection(); w.select_all()
    assert it.isSelected()




def test_qc_drag_creates_arrow_only_onto_existing_shape():
    # [M4-2a] 네방향점 드래그해 스냅 대상(다른 도형)에 이으면 = 화살표만(추가 복제 없음) /
    # 클릭(None) = 도형복제+화살표. [① 빈 캔버스 드롭 2026-08-01] 스냅 대상이 없는 진짜 빈
    # 캔버스로의 드래그는 더 이상 이 분기가 아니다 — test_qc_create_drag_position이 검증.
    w = CanvasWindow(); v = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=80, hh=50); r.setSelected(True)
    tgt = _mk_pen_rect(w, x=300, y=0, ww=80, hh=50)
    n0 = len([x for x in w._scene.items() if isinstance(x, _RectItem)])
    d0 = len(w._undo)
    arr = v._qc_create(r, "r", tgt.mapToScene(tgt.rect().center()))   # 드래그 → 기존 도형에 흡수
    assert isinstance(arr, _PolyArrowItem)
    assert len([x for x in w._scene.items() if isinstance(x, _RectItem)]) == n0   # 도형 안 늘어남
    assert arr._bind_start is r and arr._bind_end is tgt
    assert len(w._undo) == d0 + 1
    w.undo(); assert arr not in w._scene.items()
    r.setSelected(True)
    dup, arr2 = v._qc_create(r, "r", None)                    # 클릭 = 도형복제 + 화살표
    assert isinstance(dup, _RectItem) and isinstance(arr2, _PolyArrowItem)
    assert len([x for x in w._scene.items() if isinstance(x, _RectItem)]) == n0 + 1




def test_qc_drag_free_end_still_makes_ortho_elbow():
    # [편의기능] 네방향점 드래그로 화살표를 만들 때, 도착점이 다른 도형에 안 붙어도(자유 끝)
    # 직각 엘보로 나와야 한다 — 종전엔 스냅 안 되면 시작-끝 2점 직선(대각선)으로 남았다
    # (2026-07-27 사용자 피드백: "기본이 직선으로 나온다").
    w = CanvasWindow(); v = w._view
    r = _mk_pen_rect(w, x=0, y=0, ww=80, hh=50); r.setSelected(True)
    # 대각선 방향 도착점(대각이면 직선과 엘보 차이가 뚜렷) — 우측 변에서 우측-아래로.
    arr = v._qc_create(r, "r", QPointF(300, 200))
    assert isinstance(arr, _PolyArrowItem)
    assert arr._auto_route is True                    # 도형 이동해도 계속 엘보 재계산되도록
    assert len(arr._pts) >= 3, "자유 끝인데도 2점 직선이면 버그(엘보가 안 생김)"
    # 엘보의 모든 변은 축정렬(수평 또는 수직)이어야 한다(대각선 세그먼트가 있으면 실패).
    for p1, p2 in zip(arr._pts[:-1], arr._pts[1:]):
        assert abs(p1.x() - p2.x()) < 1e-6 or abs(p1.y() - p2.y()) < 1e-6




def test_qc_drag_arrow_uses_sticky_curve_radius():
    # [편의기능] 미니툴바 곡선 반경 스테퍼로 바꾼 sticky 값(current_curve_r)이 네방향점 드래그
    # 화살표에도 이어져야 한다(사용자 피드백 2026-07-27: "지속사용 하고 싶다는 뜻일 것").
    # 종전엔 _qc_create_arrow_only가 _begin_draw를 안 거쳐 항상 클래스 기본 반경으로 고정됐다.
    w = CanvasWindow(); v = w._view
    w.current_curve_r = 2.0
    r = _mk_pen_rect(w, x=0, y=0, ww=80, hh=50); r.setSelected(True)
    arr = v._qc_create(r, "r", QPointF(300, 200))
    assert arr._curve_r == 2.0




def test_qc_drag_ghost_matches_final_route():
    # [미리보기≠확정 버그 수정 2026-07-27] 네방향점을 드래그해 다른 도형에 이을 때, 드래그 중
    # 고스트 미리보기(_qc_paint_ghost)는 장애물·재진입 회피가 없는 _ortho_elbow만 썼는데,
    # 릴리스가 실제로 만드는 화살표(_qc_create_arrow_only)는 build_elbow와 같은 _route_ortho를
    # 써서 재진입/근접 배치에서 둘이 서로 다른 경로를 보였다(사용자 실조건 재현: 어긋나게 배치한
    # 두 네모를 선택도구로 네방향점 드래그해 이을 때). 고스트도 같은 _route_ortho를 쓰도록
    # _qc_route_context를 추가해 고쳤다 — 이 테스트는 그 계산 결과가 실제 결과와 일치하는지 확인.
    from easycad.canvas.annotator_core import (
        _edge_mid, _QC_SIDE_NORMAL, _route_ortho, _dedup_pts, _PolyArrowItem)
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    a = _mk_rect(w._scene, w.make_pen(), -290, -213, 181, 125)
    b = _mk_rect(w._scene, w.make_pen(), 44, -56, 207, 120)
    view = w._view
    a.setSelected(True)
    side = "b"
    p_src = _edge_mid(view._qc_src_scene_rect(a), side)
    cursor = QPointF(251, 4)   # b의 E 포트 — 재진입 회피가 실제로 갈리는 배치(혹 버그 재현과 동일)

    snap = view._qc_snap_target(cursor, a)
    end = snap[0] if snap is not None else cursor
    ns = _QC_SIDE_NORMAL[side]
    ne = snap[1] if snap is not None else None
    target = snap[2] if snap is not None else None
    obstacles, conn_rects = view._qc_route_context(a, target)
    mids = _route_ortho(p_src, end, ns, ne, obstacles, _PolyArrowItem._ROUTE_CLEARANCE,
                        conn_rects=conn_rects)
    ghost_pts = _dedup_pts([p_src] + mids + [end])

    arrow = view._qc_create_arrow_only(a, side, cursor)
    final_pts = [arrow.mapToScene(p) for p in arrow._pts]

    assert len(ghost_pts) == len(final_pts) and all(
        _close(x, y) for x, y in zip(ghost_pts, final_pts)), \
        ("고스트≠확정", ghost_pts, final_pts)




def test_snap_to_line_and_arrow_endpoints():
    # [M4-2b] 스냅 대상에 선·화살표(끝점 우선 + 몸통 폴백) 포함, 바인딩은 도형만(shape=None).
    w = CanvasWindow(); v = w._view
    ln = _LineItem(QLineF(100, 0, 300, 0)); ln.setPen(w.make_pen())
    ln.setFlags(ln.GraphicsItemFlag.ItemIsSelectable | ln.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ln)
    # 끝점 (300,0) 근처 → 그 끝점으로 스냅, shape=None(바인딩 없음)
    snap = v._border_snap_at(v.mapFromScene(QPointF(302, 1)))
    assert snap is not None and snap[2] is None
    assert abs(snap[0].x() - 300) < 1.5 and abs(snap[0].y()) < 1.5
    # 몸통 (200,0) 근처(끝점 아님) → 몸통 최근접점 스냅
    snap2 = v._border_snap_at(v.mapFromScene(QPointF(200, 3)))
    assert snap2 is not None and snap2[2] is None
    assert abs(snap2[0].x() - 200) < 2 and abs(snap2[0].y()) < 2
    # 자기 자신 제외 → 다른 대상 없으면 스냅 없음
    assert v._border_snap_at(v.mapFromScene(QPointF(302, 1)), exclude=ln) is None
    # 도형은 여전히 바인딩(shape 반환)
    r = _mk_pen_rect(w, x=400, y=-25, ww=50, hh=50)
    snr = v._border_snap_at(v.mapFromScene(QPointF(400, 0)))
    assert snr is not None and snr[2] is r




def test_snap_to_external_path_item():
    # [계획서 §8 항목5] 외부 DXF 폴백 도형(_PathItem, item.rect() 없음)도 화살표 스냅+지속연결
    # 대상이어야 한다 — 기존엔 _conn_shapes()가 rect/ellipse/symbol만 인식해 안 잡혔음.
    w = CanvasWindow(); v = w._view
    pp = QPainterPath(QPointF(500, 500))
    pp.lineTo(600, 500); pp.lineTo(600, 600); pp.lineTo(500, 600); pp.closeSubpath()
    pit = _PathItem(pp); pit.setPen(w.make_pen())
    pit.setFlags(pit.GraphicsItemFlag.ItemIsSelectable | pit.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(pit)
    # 변 (550,500) 근처 → 그 변으로 연속 폴백 스냅 + 바인딩(shape=pit)
    snap = v._border_snap_at(v.mapFromScene(QPointF(550, 502)))
    assert snap is not None and snap[2] is pit
    assert abs(snap[0].x() - 550) < 2 and abs(snap[0].y() - 500) < 2
    assert abs(snap[1].y() - (-1.0)) < 1e-6   # 위쪽 변 → 바깥 법선 위(-y)

    # 바인딩된 화살표가 도형 이동에 추종(reroute가 _nearest_border(_PathItem)를 재호출)
    arrow = _PolyArrowItem(QColor("black"), 2, True)
    arrow.set_points(QPointF(500, 300), QPointF(550, 500))
    w._scene.addItem(arrow)
    arrow.set_bound(1, pit, pit.mapFromScene(QPointF(550, 500)))
    arrow.reroute()
    before = arrow.mapToScene(arrow._pts[-1])
    pit.moveBy(20, 0)
    arrow.reroute()
    after = arrow.mapToScene(arrow._pts[-1])
    assert abs(after.x() - before.x() - 20) < 1e-6 and abs(after.y() - before.y()) < 1e-6




def test_properties_panel_type_rows_hidden_without_selection():
    # [미니패널 통합 2026-07-31] 선택이 없으면 도형바꾸기·화살표종류·반경·방향 4개 행은 전부
    # 숨어야 한다(빈 dock에 죽은 버튼이 남지 않게) — 옛 플로팅 툴바의 "바 전체 숨김"과 동일 취지.
    w = CanvasWindow()
    for widget in (w._pf_swap_btn, w._pf_routing_btn, w._pf_radius, w._pf_dir_btn):
        assert widget.isHidden()




def test_properties_panel_grows_when_row_count_increases():
    # [2026-07-31, 실사용자 실기기 재현] 선택 종류가 바뀌어 노출 행 수가 늘어도(네모 7행→
    # 화살표 9행) `_props_panel` 위젯 자체가 창 리사이즈 없이 그 크기에 맞춰 커져야 한다.
    # 옛 버그: `_refresh_properties()`가 행 노출만 토글하고 패널을 안 키워, 창을 한 번도
    # 리사이즈 안 한 앱 기본 크기에서 스핀박스("두께"·"폰트"·"반경")가 옛(더 좁은) 패널 크기에
    # 짓눌려 13px까지 줄고 텍스트 디센더가 잘렸다(실기기 콘솔 로그로 원인 확정). 창을 한 번도
    # 안 건드린 채로(=이 테스트처럼 CanvasWindow 생성 직후) 재현·검증해야 의미가 있다.
    w = CanvasWindow(); w.show()
    empty_h = w._props_panel.height()   # 선택 없는 기본 크기(축소 회귀의 정답 기준)

    rect = _RectItem(QRectF(0, 0, 150, 90))
    rect.setFlags(rect.GraphicsItemFlag.ItemIsSelectable | rect.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(rect); rect.setSelected(True)
    rect_h = w._props_panel.height()
    assert w._pf_width.geometry().height() >= 20   # 잘림 없는 정상 높이

    w._scene.clearSelection()
    ar = _PolyArrowItem(QColor("#111111"), 3.0, True)
    ar.set_points(QPointF(-150, -155), QPointF(180, -170))
    w._scene.addItem(ar); ar.setSelected(True)
    arrow_h = w._props_panel.height()
    assert arrow_h > rect_h   # 화살표는 행이 2개 더 많아 패널이 더 커야 한다
    assert w._pf_width.geometry().height() >= 20   # 행이 늘어도 두께 행은 짓눌리지 않는다

    # [2026-08-01, 실사용자 스크린샷 재현] 화살표(9행)를 본 뒤 선택을 해제하면, 그 큰 크기가
    # 그대로 눌어붙어 빈 공간만 길게 남는 축소 방향 회귀가 있었다 — 반드시 선택 없는 기본
    # 크기(`empty_h`)로 돌아가야 한다(직전 선택의 rect_h가 아니라 진짜 빈 상태 기준).
    w._scene.clearSelection()
    w._refresh_properties()
    assert w._props_panel.height() <= empty_h + 2




def test_properties_panel_arrow_flip_undo():
    # [M3 #15 → 미니패널 통합 2026-07-31] 화살표 선택 시 속성 dock의 방향 행 노출 + flip이
    # capture_state로 undo(코어 보강). 옛 선택-추종 플로팅 툴바에서 이관.
    w = CanvasWindow()
    ar = _PolyArrowItem(QColor("#111111"), 3.0, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar); ar.setSelected(True)
    assert not w._pf_dir_btn.isHidden()               # 화살표 → 방향 행 노출
    before = ar._head_at_end
    st = ar.capture_state(); assert "head" in st          # 방향이 상태 스냅샷에 포함
    w._floating_flip_arrows()
    assert ar._head_at_end != before
    w.undo(); assert ar._head_at_end == before            # 방향 토글이 되돌려진다




def test_properties_panel_arrow_kind_dropdown():
    # [화살표 통합 → 미니패널 통합 2026-07-31] 단일 화살표 선택 시 속성 dock에 종류 드롭다운
    # 행 노출. 직선↔곡선은 같은 객체(_ArrowItem)의 상태 변경(곡률 기억), ↔직각은 클래스 교체
    # (_PolyArrowItem)이고 각각 단일 undo.
    from easycad.canvas.host_widgets import _arrow_kind_of
    w = CanvasWindow()
    ar = _ArrowItem(QColor("#111111"), 3.0, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 60))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar); ar.setSelected(True)
    assert not w._pf_routing_btn.isHidden()            # 화살표 → 종류 행 노출
    assert _arrow_kind_of(ar) == "straight"

    w._floating_set_arrow_kind("curved")                  # 같은 객체 — 휜다
    assert ar._ctrl1 is not None and _arrow_kind_of(ar) == "curved"
    w.undo(); assert ar._ctrl1 is None                    # 곡률 되돌림

    w._floating_set_arrow_kind("curved")
    w._floating_set_arrow_kind("ortho")                   # 클래스 교체 → _PolyArrowItem
    poly = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    assert len(poly) == 1 and _arrow_kind_of(poly[0]) == "ortho"
    assert ar.scene() is None                             # 옛 곡선 화살표는 씬에서 빠짐
    w.undo()                                              # 교체 되돌림 → 곡선 화살표 복귀
    assert ar.scene() is not None and not [x for x in w._scene.items()
                                           if isinstance(x, _PolyArrowItem)]




def test_arrow_kind_sticky_and_tool_unified():
    # [화살표 통합] 상단 툴바엔 화살표 1개(sarrow 버튼 없음). arm_arrow_tool이 종류→내부 도구를
    # 정한다(곡선·직선=arrow, 직각=sarrow). set_tool은 리터럴로 남아 테스트·내부 호출이 그대로 받음.
    w = CanvasWindow()
    assert "sarrow" not in w._tool_buttons and "arrow" in w._tool_buttons
    assert w.current_arrow_kind == "ortho"                # [2026-07-30] 최초 기본 = 직각(순서도 위주)
    w.arm_arrow_tool()
    assert w.current_tool == "sarrow"                      # 직각 → 내부 sarrow 도구
    assert w._tool_buttons["arrow"].isChecked()           # 화살표 버튼 하나가 둘을 대표
    w.arm_arrow_tool()                                     # 다시 = 토글 해제
    assert w.current_tool != "sarrow"
    w.current_arrow_kind = "curved"
    w.arm_arrow_tool()
    assert w.current_tool == "arrow"                       # 곡선 → 내부 arrow 도구
    assert w._tool_buttons["arrow"].isChecked()           # 곡선이어도 화살표 버튼이 켜짐




def test_arrow_kind_change_rearms_pinned_tool():
    # [화살표 통합 · 핀 버그] 화살표 도구가 무장된 상태(핀)에서 미니툴바로 종류를 바꾸면 무장도
    # 새 종류에 맞게 재무장돼야 한다 — 안 그러면 다음에 그리는 화살표가 옛 종류로 나온다.
    w = CanvasWindow()
    ar = _ArrowItem(QColor("#111111"), 3.0, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 60))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar); ar.setSelected(True)
    w.current_arrow_kind = "curved"   # [2026-07-30] 기본값은 이제 직각 — 이 테스트는 곡선에서 시작
    w.arm_arrow_tool()
    assert w.current_tool == "arrow"                      # 곡선 무장
    w._floating_set_arrow_kind("ortho")                   # 종류를 직각으로
    assert w.current_tool == "sarrow"                     # 무장도 직각 도구로 따라감
    w._floating_set_arrow_kind("curved")
    assert w.current_tool == "arrow"                      # 다시 곡선 도구로
    # 무장이 안 된 상태(선택 모드)에서는 종류만 바꾸고 도구는 건드리지 않는다.
    w.set_tool("select")
    poly = [x for x in w._scene.items() if isinstance(x, _PolyArrowItem)]
    (poly[0] if poly else ar).setSelected(True)
    w._floating_set_arrow_kind("straight")
    assert w.current_tool == "select"                     # 도구는 그대로






def test_arrowhead_shoulders_not_beveled():
    # [실사용 버그 2026-08-03] 화살촉 삼각형의 예각 어깨가 45°로 깎이던 회귀 방지.
    # 원인은 QPen의 **기본 joinStyle이 BevelJoin**이라는 것 — `_PolyArrowItem.paint()`가
    # 화살촉 펜에 joinStyle을 명시하지 않아 어깨가 모따기됐다(`_ArrowItem`은 처음부터
    # RoundJoin을 명시해 두어 멀쩡했고, 그래서 "직각 화살표만 깎인다"로 보고됐다).
    # 화살촉 펜 폭이 1로 고정이라 깎임 크기도 ~0.5 씬단위 고정 → 100% 줌에선 안티에일리어싱에
    # 묻혀 안 보이고 고배율(사용자 실측 2863%)에서만 드러난다. 눈으로 3라운드 동안 못 잡은
    # 종류의 버그라 '실제 렌더 픽셀'로 못 박는다: 어깨 꼭짓점에서 바깥으로 0.4 떨어진 점이
    # 칠해져 있어야 한다(RoundJoin이면 반지름 0.5 원으로 덮이고, BevelJoin이면 잘려 배경색).
    import math
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QImage, QPainter

    SCALE, SX, SY, SPAN = 20, -6.0, -9.0, 12.0
    px = int(SPAN * SCALE)

    def shoulders_filled(item):
        """실제 paint() 경로(scene.render)로 그린 뒤 양쪽 어깨 바깥 점의 채움 여부."""
        sc = QGraphicsScene()
        sc.addItem(item)
        img = QImage(px, px, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sc.render(p, QRectF(0, 0, px, px), QRectF(SX, SY, SPAN, SPAN))
        p.end()
        tip, bl, br = item._head_points()
        cx = (tip.x() + bl.x() + br.x()) / 3.0
        cy = (tip.y() + bl.y() + br.y()) / 3.0
        out = []
        for v in (bl, br):                       # 양쪽 어깨 모두
            dx, dy = v.x() - cx, v.y() - cy
            L = math.hypot(dx, dy) or 1.0
            probe_x = v.x() + dx / L * 0.4
            probe_y = v.y() + dy / L * 0.4
            ix = int(round((probe_x - SX) * SCALE))
            iy = int(round((probe_y - SY) * SCALE))
            c = QColor(img.pixel(ix, iy))
            out.append(c.red() > 200 and c.green() < 120 and c.blue() < 120)
        return out

    ortho = _PolyArrowItem(QColor("#ff0000"), 1.0, True)
    ortho._pts = [QPointF(0, -40), QPointF(0, 0)]
    ortho._auto_route = False
    ortho.prepareGeometryChange()
    assert all(shoulders_filled(ortho)), "직각 화살촉 어깨가 깎였다(joinStyle 미지정 회귀)"

    curved = _ArrowItem(QColor("#ff0000"), 1.0, True)
    curved.set_points(QPointF(0, -40), QPointF(0, 0))
    assert all(shoulders_filled(curved)), "곡선 화살촉 어깨가 깎였다"


# --- 다중선택 강조 밴드 고속경로(2026-08-15 성능수정) 회귀 -------------------
# `_highlight_band_fast`가 스트로크+불리언 연산을 산술 프리미티브로 대체하는데, 이 경로에
# 잘못된 도형이 새면 "선택 강조만 조용히 딴 모양"이 되는 시각 버그가 된다. 1차 구현이 실제로
# 그 버그를 냈다(`_SymbolItem`이 `QGraphicsRectItem` 하위라 isinstance 판정에 걸려 삼각형·
# 마름모가 사각형 밴드로 그려짐) — 기존 스모크 어디에도 선택 밴드를 검사하는 테스트가 없어
# 못 잡았고, `tools/perf_baseline_check.py`도 선택 상태를 렌더하지 않아 못 잡는다.

def _band_area(path):
    """QPainterPath의 채움 면적(신발끈 공식) — 밴드 비교용."""
    total = 0.0
    for poly in path.toFillPolygons():
        s = 0.0
        n = poly.count()
        for i in range(n):
            p1, p2 = poly.at(i), poly.at((i + 1) % n)
            s += p1.x() * p2.y() - p2.x() * p1.y()
        total += abs(s) / 2.0
    return total


def test_highlight_band_fast_skips_symbol_items():
    """심볼은 고속경로에 절대 들어가면 안 된다(`QGraphicsRectItem` 상속 함정)."""
    from PyQt6.QtGui import QPen
    from easycad.canvas.core_shapes import _highlight_band, _highlight_band_fast

    sym = _SymbolItem("triangle", QRectF(0, 0, 130, 110))
    pen = QPen(QColor("#222222")); pen.setWidthF(2.0); sym.setPen(pen)

    assert _highlight_band_fast(sym) is None, "심볼이 사각형 고속경로로 샜다"

    # 밴드가 실제 삼각형 외곽선을 따라가는지 기하로 확인. 삼각형은 (0,0)-(0,110)-(130,55)이라
    # 위쪽 빗변 중점 바로 바깥인 (65, 26.5)는 삼각형 밖(≈0.9 유닛)이면서 bbox 안이다 —
    # 삼각형 밴드는 이 점을 품고, (버그 시의) 사각형 밴드는 bbox 바깥만 감싸므로 못 품는다.
    band = _highlight_band(sym)
    assert band.contains(QPointF(65, 26.5)), "밴드가 삼각형 빗변을 안 따라간다(사각형 밴드 회귀)"


def test_highlight_band_fast_matches_slow_path_for_rect():
    """사각형 고속경로는 근사가 아니라 기존 스트로크+불리언 결과와 동일해야 한다."""
    from PyQt6.QtGui import QPen, QPainterPathStroker
    from easycad.canvas.core_shapes import _highlight_band_fast, _item_center_path

    r = _RectItem(QRectF(0, 0, 150, 90))
    pen = QPen(QColor("#222222")); pen.setWidthF(2.0); r.setPen(pen)

    fast = _highlight_band_fast(r)
    assert fast is not None, "사각형이 고속경로를 못 탔다"

    centerline = _item_center_path(r)
    stroker = QPainterPathStroker()
    stroker.setWidth(max(2.0, 1.0) + 3.0)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    slow = stroker.createStroke(centerline).simplified().subtracted(centerline)

    a_slow = _band_area(slow)
    a_xor = _band_area(fast.united(slow)) - _band_area(fast.intersected(slow))
    assert a_xor / a_slow < 0.01, f"사각형 밴드가 기존 경로와 다르다(대칭차 {a_xor / a_slow:.1%})"


def test_highlight_band_fast_falls_back_for_eccentric_ellipse():
    """납작한 타원 + 굵은 펜은 '타원의 오프셋 곡선은 타원이 아니다' 오차가 커져 폴백해야 한다."""
    from PyQt6.QtGui import QPen
    from easycad.canvas.core_shapes import _highlight_band_fast

    def mk(w, h, pw):
        e = _EllipseItem(QRectF(0, 0, w, h))
        pen = QPen(QColor("#222222")); pen.setWidthF(pw); e.setPen(pen)
        return e

    assert _highlight_band_fast(mk(150, 90, 2.0)) is not None    # 통상 비율 — 고속경로
    assert _highlight_band_fast(mk(400, 40, 2.0)) is not None    # 실측 오차 1.1% — 허용
    assert _highlight_band_fast(mk(400, 20, 10.0)) is None       # 실측 5.2% — 폴백
    assert _highlight_band_fast(mk(600, 12, 12.0)) is None       # 실측 8.8% — 폴백


def test_highlight_band_fast_falls_back_for_ports_and_cuts():
    """포트·TRIM 자국이 있으면 실제 외곽선이 단순 사각형이 아니므로 폴백해야 한다."""
    from PyQt6.QtGui import QPen
    from easycad.canvas.core_shapes import _highlight_band_fast

    r = _RectItem(QRectF(0, 0, 150, 90))
    pen = QPen(QColor("#222222")); pen.setWidthF(2.0); r.setPen(pen)
    assert _highlight_band_fast(r) is not None

    r._cuts = [(0, 0.3, 0.6)]        # 위쪽 변 일부가 잘린 상태
    assert _highlight_band_fast(r) is None, "cut이 있는데도 고속경로를 탔다"


# --- 드래그 중 장식 숨김(성능계획 2-C(b), 2026-08-15) -----------------------

def test_drag_decor_suppressed_only_when_dragging_and_multi():
    """억제 조건은 「드래그 중 + 다중선택」 둘 다. 도형 하나만 끌 때 라벨이 사라지면
    눈에 띄게 거슬리는데 정작 비용은 거의 없으므로(움직인 것만 리페인트), 이득이 있는
    곳에서만 품질을 내준다."""
    from easycad.canvas.core_shapes import _drag_decor_suppressed
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=72)
    b = _mk_pen_rect(w, x=300, y=200, ww=120, hh=72)
    a.boundingRect()          # _interactive_view_cache 준비(_view_zoom_factor가 채움)

    a.setSelected(True); b.setSelected(True)
    assert _drag_decor_suppressed(a) is False, "드래그 중이 아닌데 장식을 숨겼다"

    w._view._move_active = True
    assert _drag_decor_suppressed(a) is True, "다중선택 드래그인데 장식을 안 숨겼다"

    b.setSelected(False)      # 단일선택 드래그
    assert _drag_decor_suppressed(a) is False, "단일 드래그인데 라벨을 숨겼다"

    b.setSelected(True)
    w._view._move_active = False
    assert _drag_decor_suppressed(a) is False, "드래그가 끝났는데 계속 숨긴다"


def test_label_text_stays_visible_during_multi_drag():
    """[사용자 판단 2026-08-15] 도형 안 텍스트는 드래그 중에도 계속 보여야 한다.
    한때 성능을 위해 숨겼다가 되돌렸다 — 기여도를 갈라 재보니 1000개 전체선택 드래그에서
    라벨 억제 몫은 20.3ms뿐(선택밴드 억제 100.5ms, 2-C(a) 202ms)이라, 전체 개선폭 323ms의
    6%를 위해 내용이 사라지는 건 손해였다. 이 테스트가 그 결정을 고정한다."""
    from PyQt6.QtGui import QImage, QPainter
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=200, hh=120)
    b = _mk_pen_rect(w, x=400, y=300, ww=200, hh=120)
    a.ensure_label().setPlainText("LABEL")     # 헤드리스 폰트에서도 나오는 ASCII
    a._sync_label()
    a.boundingRect()
    a.setSelected(True); b.setSelected(True)

    src = a._label.sceneBoundingRect()
    bg = w._scene.backgroundBrush().color().rgb()

    def ink():
        """배경색과 다른 픽셀 수 = 실제로 그려진 것(글자). ⚠ '알파가 있는 픽셀'로 세면
        씬 배경이 불투명하게 깔려 전 픽셀이 걸리므로 아무것도 측정하지 못한다(실제로 겪음)."""
        img = QImage(120, 60, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        w._scene.render(p, QRectF(0, 0, 120, 60), src)
        p.end()
        return sum(1 for y in range(60) for x in range(120)
                   if (img.pixel(x, y) & 0xFFFFFF) != (bg & 0xFFFFFF))

    w._view._move_active = False
    idle = ink()
    w._view._move_active = True
    dragging = ink()

    assert idle > 0, "유휴 상태에서 라벨이 아예 안 그려졌다(테스트 전제 실패)"
    assert dragging == idle, f"드래그 중 라벨 글자가 사라졌다(유휴 {idle} / 드래그 {dragging})"


def test_selection_band_suppressed_during_multi_drag():
    """선택 밴드는 드래그 중 다중선택이면 안 그린다 — 진짜 장식이고, 무엇이 선택됐는지는
    그룹 변형 오버레이의 바운딩박스가 계속 보여준다. 2-C(b)에서 실제로 일한 부분(-100.5ms)."""
    from easycad.canvas.core_shapes import _drag_decor_suppressed, _paint_selection_highlight
    from PyQt6.QtGui import QImage, QPainter
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=200, hh=120)
    b = _mk_pen_rect(w, x=400, y=300, ww=200, hh=120)
    a.boundingRect()
    a.setSelected(True); b.setSelected(True)

    img = QImage(40, 40, QImage.Format.Format_ARGB32)

    def band_ink():
        img.fill(0)
        p = QPainter(img)
        p.translate(20, 20)
        _paint_selection_highlight(p, a, 1.0)
        p.end()
        return sum(1 for y in range(40) for x in range(40) if (img.pixel(x, y) >> 24) & 0xFF)

    w._view._move_active = False
    assert _drag_decor_suppressed(a) is False
    idle = band_ink()
    w._view._move_active = True
    assert _drag_decor_suppressed(a) is True
    assert band_ink() < idle, "드래그 중인데 선택 밴드를 그대로 그린다"
