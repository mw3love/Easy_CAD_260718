"""정밀 편집(축고정/정렬가이드/그리드스냅)·화살표 프리뷰

tests/test_easycad.py 2026-08-02 분할분. 실행: python tests/test_easycad.py (전체) 또는 pytest test_part5_precision_edit.py.
"""
import math

from _shared import *  # noqa: F401,F403


def test_shiftwheel_width_coalesces_to_one_step():
    # Shift+휠 두께 연속 조절 = undo 1스텝(before 유지·after 갱신).
    w = CanvasWindow()
    it = _mk_pen_rect(w, width=2.0); it.setSelected(True)
    d0 = len(w._undo)
    w.adjust_item_property(it, +1)
    w.adjust_item_property(it, +1)
    w.adjust_item_property(it, +1)
    assert len(w._undo) == d0 + 1
    assert abs(it.pen().widthF() - 5.0) < 1e-6
    w.undo(); assert abs(it.pen().widthF() - 2.0) < 1e-6   # 병합해도 최초 before 복원
    w.redo(); assert abs(it.pen().widthF() - 5.0) < 1e-6




def test_redo_invalidation_and_action_state():
    # 되돌린 뒤 새 변이가 들어오면 redo 스택 무효화 + undo/redo 버튼 활성 상태 동기화.
    w = CanvasWindow()
    def add():
        r = _mk_pen_rect(w); w.push_undo_add(r); return r
    add()
    assert w._act_undo.isEnabled() and not w._act_redo.isEnabled()
    w.undo()
    assert not w._act_undo.isEnabled() and w._act_redo.isEnabled()
    add()                                   # 되돌린 상태에서 새 변이
    assert len(w._redo) == 0
    assert w._act_undo.isEnabled() and not w._act_redo.isEnabled()




def test_new_doc_clears_undo_and_redo():
    w = CanvasWindow()
    r = _mk_pen_rect(w); w.push_undo_add(r)
    w.undo()                                # redo에 1건
    w._new_doc()
    assert len(w._undo) == 0 and len(w._redo) == 0
    assert not w._act_undo.isEnabled() and not w._act_redo.isEnabled()


# ---------------------------------------------------------------------------
# [Phase 6 M2] one-shot 도구 + pin + 우클릭 취소 + sticky 기본값 + 비활성 아이콘.
# ---------------------------------------------------------------------------


def test_oneshot_reverts_to_select():
    w = CanvasWindow(); w.tool_pinned = False
    w.set_tool("rect")
    w.push_undo_add(_mk_pen_rect(w))
    _app.processEvents()               # singleShot(0) 실행
    assert w.current_tool == "select"




def test_pin_keeps_tool_armed():
    w = CanvasWindow(); w._toggle_pin(True)
    assert w.tool_pinned is True
    w.set_tool("rect")
    w.push_undo_add(_mk_pen_rect(w))
    _app.processEvents()
    assert w.current_tool == "rect"    # pin ON → 무장 유지(연속 그리기)


def test_pin_toolbar_button_next_to_drawing_tools_not_undo_redo():
    # [실사용 요청 2026-08-25] "도구 고정"은 그리기 도구의 동작 모드 토글이지 히스토리
    # 조작이 아니다 — 툴바에서 undo/redo 옆(옛 위치)이 아니라 그리기 도구 버튼 묶음 옆에
    # 있어야 한다. 그리기 도구는 QToolButton(addWidget)이라 tb.actions()엔 래핑 액션으로
    # 잡히므로, "화살표 도구 버튼의 액션보다 뒤, undo/redo보다는 훨씬 뒤"로 확인한다.
    w = CanvasWindow()
    actions = w._toolbar.actions()
    pin_i = actions.index(w._act_pin)
    redo_i = actions.index(w._act_redo)
    # QToolButton 자신이 아니라 그 버튼을 담은 QAction을 actions()에서 찾는다(addWidget 래핑).
    arrow_action = next(a for a in actions if w._toolbar.widgetForAction(a) is w._tool_buttons["arrow"])
    arrow_i = actions.index(arrow_action)
    assert pin_i > arrow_i > redo_i   # 핀은 undo/redo 그룹이 아니라 도구 그룹 뒤에




def test_oneshot_symbol_prefix_and_pen_exclusion():
    w = CanvasWindow(); w.tool_pinned = False
    w.set_tool("sym:decision")
    w.push_undo_add(_mk_pen_rect(w)); _app.processEvents()
    assert w.current_tool == "select"  # 심볼도 one-shot
    w.set_tool("pen")
    w.push_undo_add(_mk_pen_rect(w)); _app.processEvents()
    assert w.current_tool == "pen"     # pen은 제외 → 유지




def test_paste_does_not_disarm():
    w = CanvasWindow(); w.tool_pinned = False; w.set_tool("select")
    w.push_undo_add_many([_mk_pen_rect(w)])
    _app.processEvents()
    assert w.current_tool == "select"  # 붙여넣기는 select 모드라 one-shot에 안 걸림




def test_right_click_cancels_and_disarms():
    w = CanvasWindow(); v = w._view
    w.set_tool("rect")
    v._right_click_cancel()
    assert w.current_tool == "select"                   # 무장 해제
    # 진행 중 클릭 배치가 있으면 폐기 + 해제.
    w.set_tool("sarrow")
    it = _PolyArrowItem(QColor("#111111"), 2.0, True)
    it.set_points(QPointF(0, 0), QPointF(0, 0)); w._scene.addItem(it)
    v._place = it; v._place_tool = "sarrow"
    v._right_click_cancel()
    assert v._place is None and it.scene() is None       # 배치 폐기
    assert w.current_tool == "select"




def test_sticky_defaults_width_color_style():
    w = CanvasWindow()
    it = _mk_pen_rect(w, width=2.0, color="#111111"); it.setSelected(True)
    w._edit_width(9.0)
    assert abs(w.current_width - 9.0) < 1e-6
    di = w._pf_style.findData(Qt.PenStyle.DashLine)
    w._pf_style.setCurrentIndex(di)
    assert w.current_style == Qt.PenStyle.DashLine
    w._set_current_color(QColor("#00ff00"))
    assert w.current_color.name() == "#00ff00"
    pen = w.make_pen()                 # 다음 도형에 sticky 반영
    assert abs(pen.widthF() - 9.0) < 1e-6
    assert pen.style() == Qt.PenStyle.DashLine
    assert pen.color().name() == "#00ff00"




def test_shiftwheel_updates_default_width():
    w = CanvasWindow()
    it = _mk_pen_rect(w, width=2.0); it.setSelected(True)
    w.adjust_item_property(it, +3)     # 2 → 5
    assert abs(it.pen().widthF() - 5.0) < 1e-6
    assert abs(w.current_width - 5.0) < 1e-6   # sticky 기본값 갱신




def test_shiftwheel_font_size_on_text_item():
    # [실사용 피드백 2026-08-18] 텍스트(독립 텍스트 도구)는 두께가 아니라 폰트크기가 조절돼야 한다.
    w = CanvasWindow()
    it = _TextItem(QColor("#111111")); it.setPlainText("hello")
    w._scene.addItem(it); it.setSelected(True)
    assert it._base_pt == 16
    w.adjust_item_property(it, +3)
    assert it._base_pt == 19
    assert it.font().pointSize() == 19
    w.undo()
    assert it._base_pt == 16
    w.redo()
    assert it._base_pt == 19


def test_shiftwheel_font_size_on_shape_label_leaves_host_width_untouched():
    # [실사용 피드백 2026-08-18] 도형/화살표에 붙은 라벨도 같은 _TextItem이라 폰트크기가
    # 조절 대상 — 단, 호스트(도형) 자체의 선 두께는 라벨 조절과 별개로 그대로 유지돼야 한다.
    w = CanvasWindow()
    rect = _mk_pen_rect(w, width=2.0)
    lbl = rect.ensure_label(); lbl.setPlainText("A")
    before_base = lbl._base_pt
    before_pen_w = rect.pen().widthF()
    w.adjust_item_property(lbl, +2)
    assert lbl._base_pt == before_base + 2
    assert abs(rect.pen().widthF() - before_pen_w) < 1e-9


def test_adjust_selected_properties_applies_to_entire_multiselection():
    # [실사용 피드백 2026-08-18] 여러 개 선택 후 shift+휠 = 커서 아래 하나가 아니라
    # 선택된 것 전부에 일괄 적용 + undo 1스텝으로 묶인다.
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, width=2.0)
    b = _mk_pen_rect(w, x=100, width=2.0)
    a.setSelected(True); b.setSelected(True)
    d0 = len(w._undo)
    w.adjust_selected_properties([a, b], +2)
    assert abs(a.pen().widthF() - 4.0) < 1e-6
    assert abs(b.pen().widthF() - 4.0) < 1e-6
    assert len(w._undo) == d0 + 1
    w.undo()
    assert abs(a.pen().widthF() - 2.0) < 1e-6
    assert abs(b.pen().widthF() - 2.0) < 1e-6


def test_adjust_selected_properties_bulk_mixed_shape_and_text():
    # 도형(두께)+텍스트(폰트크기)가 섞인 다중선택도 각자 맞는 속성으로 한 번에 조절된다.
    w = CanvasWindow()
    rect = _mk_pen_rect(w, width=2.0)
    txt = _TextItem(QColor("#111111")); txt.setPlainText("hi")
    w._scene.addItem(txt)
    rect.setSelected(True); txt.setSelected(True)
    w.adjust_selected_properties([rect, txt], +2)
    assert abs(rect.pen().widthF() - 4.0) < 1e-6
    assert txt._base_pt == 18


def test_shiftwheel_event_prioritizes_label_over_host_shape():
    # 종단 검증 — 실제 QWheelEvent를 라벨 위치에 흘려, 두께 분기보다 먼저 라벨의
    # 폰트크기 분기가 잡히는지 확인(선택 여부와 무관하게 커서 위치가 우선).
    from PyQt6.QtGui import QWheelEvent
    w = CanvasWindow()
    rect = _mk_pen_rect(w, x=0, y=0, ww=200, hh=200, width=2.0)
    lbl = rect.ensure_label(); lbl.setPlainText("LBL")
    before_base = lbl._base_pt
    before_pen_w = rect.pen().widthF()
    local = QPointF(w._view.mapFromScene(lbl.sceneBoundingRect().center()))
    ev = QWheelEvent(local, local, QPoint(0, 0), QPoint(0, 120),
                      Qt.MouseButton.NoButton, Qt.KeyboardModifier.ShiftModifier,
                      Qt.ScrollPhase.NoScrollPhase, False)
    w._view.wheelEvent(ev)
    assert lbl._base_pt == before_base + 1
    assert abs(rect.pen().widthF() - before_pen_w) < 1e-9




def test_disabled_icon_has_dim_pixmap():
    from easycad.canvas.host_widgets import _act_icon
    from PyQt6.QtGui import QIcon
    from PyQt6.QtCore import QSize
    ic = _act_icon("undo")
    norm = ic.pixmap(QSize(24, 24), QIcon.Mode.Normal)
    dim = ic.pixmap(QSize(24, 24), QIcon.Mode.Disabled)
    assert not dim.isNull()
    assert norm.toImage() != dim.toImage()     # 흐림 사본이 원본과 다름




def test_align_rect_ignores_selection_handles():
    # [M5] 정렬 기준은 패딩 없는 실제 시각적 경계(`_smart_snap_srect`, 최종 검수 Phase 5에서
    # `_content_rect()` 직접 사용을 이걸로 교체 — 코어 boundingRect는 (선택 시) 핸들·빠른생성
    # 도트 자리를 예약해 도형마다 여백이 달라(정렬이 그만큼 어긋난다) 기준으로 쓸 수 없다.
    # [성능 조사 2026-07-30] 핸들 여백 예약이 선택 상태 조건부로 바뀌어(boundingRect가
    # 미선택 도형까지 매번 계산하던 비용 제거) — 정렬 대상은 실제로 항상 선택된 상태이므로
    # 그 상태로 검증한다.
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=0, y=0, ww=40, hh=30, width=0)
    it.setSelected(True)
    r = w._align_rect(it)
    assert abs(r.left() - 0.0) < 1.5 and abs(r.width() - 40.0) < 3.0
    assert it.sceneBoundingRect().width() > r.width() + 10     # 핸들 여백이 실제로 크다




def test_align_left_matches_true_visible_edges_across_differing_pen_widths():
    # [최종 검수 Phase 5, 2026-08-26] 옛 `_align_rect`는 `_content_rect()`(펜폭만큼 부풀린
    # 값)를 직접 썼다 — 펜 두께가 다른 두 도형을 "왼쪽 맞춤"해도 실제 보이는 왼쪽 변은
    # 정렬 안 되고 펜 두께 차이(pen/2)만큼 계속 어긋나 있었다(실측: 1.0 vs 9.0 펜 → 4.0
    # 유닛 차이). `_smart_snap_srect`(패딩 없는 실제 경계)로 교체해 해소.
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60, width=1.0)
    b = _mk_pen_rect(w, x=300, y=0, ww=100, hh=60, width=9.0)
    a.setSelected(True); b.setSelected(True)
    w.align_selection("left")
    left_a = a.mapToScene(a.rect().topLeft()).x()
    left_b = b.mapToScene(b.rect().topLeft()).x()
    assert abs(left_a - left_b) < 0.01, (left_a, left_b)


def test_align_selection_six_modes_and_undo():
    # [M5] 정렬 — 선택 bbox의 모서리·중심에 맞춘다. 이동만이라 undo 1스텝으로 전부 복원.
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=40, hh=30, width=0)
    b = _mk_pen_rect(w, x=100, y=50, ww=60, hh=20, width=0)
    for it in (a, b):
        it.setSelected(True)
    ar = w._align_rect
    pos0 = [QPointF(it.pos()) for it in (a, b)]
    edge = {"left": lambda r: r.left(), "right": lambda r: r.right(),
            "hcenter": lambda r: r.center().x(), "top": lambda r: r.top(),
            "bottom": lambda r: r.bottom(), "vcenter": lambda r: r.center().y()}
    anchor = {"left": "left", "right": "right", "hcenter": "left",
              "top": "top", "bottom": "bottom", "vcenter": "top"}
    for mode, f in edge.items():
        keep = f(ar(a)) if anchor[mode] in ("left", "top") else f(ar(b))
        w.align_selection(mode)
        assert abs(f(ar(a)) - f(ar(b))) < 0.5          # 둘이 같은 선에 섰다
        # bbox 기준이므로 그 방향의 극단에 있던 쪽은 제자리(정렬선이 밖으로 밀리지 않는다).
        if mode in ("left", "top"):
            assert abs(f(ar(a)) - keep) < 0.5
        elif mode in ("right", "bottom"):
            assert abs(f(ar(b)) - keep) < 0.5
        w.undo()
        assert _close(a.pos(), pos0[0]) and _close(b.pos(), pos0[1])




def test_distribute_selection_even_gaps():
    # [M5] 분배 — 양 끝 고정, 사이 '여백'이 균등해진다(크기가 달라도 보이는 틈이 같게).
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=40, hh=20, width=0)
    b = _mk_pen_rect(w, x=50, y=0, ww=20, hh=20, width=0)     # 치우쳐 있는 가운데
    c = _mk_pen_rect(w, x=200, y=0, ww=40, hh=20, width=0)
    for it in (a, b, c):
        it.setSelected(True)
    ar = w._align_rect
    ends = (ar(a).left(), ar(c).right())
    b_pos0 = QPointF(b.pos())
    w.distribute_selection("x")
    rs = sorted((ar(it) for it in (a, b, c)), key=lambda r: r.left())
    g1 = rs[1].left() - rs[0].right()
    g2 = rs[2].left() - rs[1].right()
    assert abs(g1 - g2) < 0.5                                 # 여백 균등
    assert abs(rs[0].left() - ends[0]) < 0.5                  # 양 끝은 그대로
    assert abs(rs[2].right() - ends[1]) < 0.5
    assert not _close(b.pos(), b_pos0)                        # 가운데는 실제로 움직였다
    w.undo()
    assert _close(b.pos(), b_pos0)                            # 되돌아옴

    # 2개뿐이면 나눌 사이가 없어 no-op(undo 스택도 안 쌓임).
    w._scene.clearSelection()
    a.setSelected(True); b.setSelected(True)
    n = len(w._undo)
    w.distribute_selection("x")
    assert len(w._undo) == n




def test_distribute_selection_fixed_gap_uses_first_pair():
    # [신규 2026-08-23] 첫 간격 기준 분배 — 처음 두 객체(위치순)는 고정, 그 간격을
    # 기준으로 세 번째부터 누적 이동한다(균등분배와 달리 마지막 객체도 밀릴 수 있음).
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=40, hh=20, width=0)
    b = _mk_pen_rect(w, x=60, y=0, ww=20, hh=20, width=0)      # a-b 간격 20
    c = _mk_pen_rect(w, x=200, y=0, ww=40, hh=20, width=0)     # b-c 간격 120(불균등)
    for it in (a, b, c):
        it.setSelected(True)
    ar = w._align_rect
    a_pos0, b_pos0, c_pos0 = QPointF(a.pos()), QPointF(b.pos()), QPointF(c.pos())
    w.distribute_selection_fixed_gap("x")
    ra, rb, rc = ar(a), ar(b), ar(c)
    gap1 = rb.left() - ra.right()
    gap2 = rc.left() - rb.right()
    assert abs(gap1 - 20.0) < 0.5                  # 기준 간격은 원래 a-b 간격 그대로
    assert abs(gap1 - gap2) < 0.5                   # 세 번째 간격이 기준 간격과 같아짐
    assert _close(a.pos(), a_pos0) and _close(b.pos(), b_pos0)   # 처음 두 개는 고정
    assert not _close(c.pos(), c_pos0)              # 세 번째는 실제로 움직였다
    w.undo()
    assert _close(c.pos(), c_pos0)                  # 되돌아옴

    # 2개뿐이면 기준만 있고 옮길 대상이 없어 no-op(undo 스택도 안 쌓임).
    w._scene.clearSelection()
    a.setSelected(True); b.setSelected(True)
    n = len(w._undo)
    w.distribute_selection_fixed_gap("x")
    assert len(w._undo) == n




def test_distribute_selection_fixed_gap_moves_bound_arrow_segments():
    # [간격분배 2026-08-23] 도형에 연결된(바인딩된) 화살표도 대표 세그먼트(가장 긴 매칭
    # 방향 세그먼트)만 옮겨 간격을 정리한다 — 끝점은 원래 붙은 자리 그대로 유지된다.
    # `docs/arrow_gap_distribute_design.md` 참조.
    w = CanvasWindow()

    def mk_bound_arrow(y, x_end=100):
        h0 = _mk_pen_rect(w, x=-30, y=y - 10, ww=20, hh=20, width=0)
        h1 = _mk_pen_rect(w, x=x_end + 10, y=y - 10, ww=20, hh=20, width=0)
        it = _PolyArrowItem(QColor("#111111"), 2.0, True)
        p0 = QPointF(0, y - 15); p3 = QPointF(x_end, y + 15)
        it._pts = [p0, QPointF(0, y), QPointF(x_end, y), p3]   # 스텁-수평-스텁(Z자)
        it._routing = "ortho"; it._auto_route = True
        it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
        w._scene.addItem(it)
        it.set_bound(0, h0, h0.mapFromScene(p0))
        it.set_bound(len(it._pts) - 1, h1, h1.mapFromScene(p3))
        return it

    a = mk_bound_arrow(0)
    b = mk_bound_arrow(20)      # a-b 간격 20
    c = mk_bound_arrow(200)     # b-c 간격 180(불균등)
    for it in (a, b, c):
        it.setSelected(True)
    seg_y = lambda it: it.mapToScene(it._pts[it.dominant_segment(True)]).y()
    endpoints0 = [(QPointF(it.mapToScene(it._pts[0])), QPointF(it.mapToScene(it._pts[-1])))
                  for it in (a, b, c)]
    n0 = len(w._undo)
    w.distribute_selection_fixed_gap("y")
    assert abs(seg_y(a) - 0.0) < 0.5 and abs(seg_y(b) - 20.0) < 0.5   # 처음 둘은 고정
    assert abs(seg_y(c) - 40.0) < 0.5                                 # 기준 간격(20)만큼 이동
    for it, (p0_before, p3_before) in zip((a, b, c), endpoints0):
        assert _close(it.mapToScene(it._pts[0]), p0_before)           # 끝점은 그대로
        assert _close(it.mapToScene(it._pts[-1]), p3_before)
        assert it.has_binding()
    assert len(w._undo) == n0 + 1
    w.undo()
    assert abs(seg_y(c) - 200.0) < 0.5                                # 되돌아옴




def test_align_targets_exclude_labels():
    # [M5] 라벨(자식 아이템)은 대상에서 빠진다 — selectable·movable이라 러버밴드에 딸려 오지만
    # 위치를 부모가 소유하고(재투영) moveBy 델타의 좌표계도 다르다.
    w = CanvasWindow()
    ar = _PolyArrowItem(QColor("#111111"), 2.0, True)
    ar.set_points(QPointF(0, 0), QPointF(200, 0))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    lb = ar.ensure_label(); lb.setPlainText("라벨"); ar._sync_label()
    assert lb.flags() & lb.GraphicsItemFlag.ItemIsMovable      # 라벨도 movable(전제 확인)
    it = _mk_pen_rect(w, x=300, y=40)
    for x in (lb, ar, it):
        x.setSelected(True)
    # 바인딩 없는 화살표는 평범한 객체라 포함, 라벨만 빠진다.
    assert set(map(id, w._align_targets())) == {id(ar), id(it)}




def test_align_targets_exclude_connectors_and_frame():
    # [M5] 대상 규칙 — 연결된 화살표는 reroute가 따라오므로 제외, 용지틀은 종이라 제외.
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=40, hh=30, width=0)
    b = _mk_pen_rect(w, x=200, y=90, ww=40, hh=30, width=0)
    ar = _PolyArrowItem(QColor("#111111"), 2.0, True)
    ar.set_points(QPointF(40, 15), QPointF(200, 105))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(40, 15)))
    ar.set_bound(1, b, b.mapFromScene(QPointF(200, 105)))
    tb = _TitleBlockItem("A4", "landscape")
    tb.setFlags(tb.GraphicsItemFlag.ItemIsSelectable | tb.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tb)
    for it in (a, b, ar, tb):
        it.setSelected(True)
    tgt = w._align_targets()
    assert set(map(id, tgt)) == {id(a), id(b)}                # 화살표·용지틀 제외
    tb_pos = QPointF(tb.pos())
    w.align_selection("top")
    assert abs(w._align_rect(a).top() - w._align_rect(b).top()) < 0.5
    assert _close(tb.pos(), tb_pos)                           # 용지틀은 안 움직임
    assert ar.has_binding()                                   # 연결은 유지(끝점은 reroute가 추종)




def test_align_removes_connector_stair():
    # [M5] 정렬의 실제 동기 — 축이 어긋난 두 도형을 잇는 직교 커넥터에는 기하적으로 계단이
    # 생긴다(코어 Stage4는 8px 이내만 흡수). 세로 가운데 정렬하면 포트가 같은 y에 서서
    # 계단이 사라지고 곧은 선이 된다.
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=120, hh=80, width=0)
    b = _mk_pen_rect(w, x=300, y=40, ww=120, hh=80, width=0)   # 40px 어긋남 = 계단
    e_a = _shape_ports(a)[1][0]                                # A의 E(오른쪽) 포트
    w_b = _shape_ports(b)[3][0]                                # B의 W(왼쪽) 포트
    ar = _PolyArrowItem(QColor("#111111"), 2.0, True)
    ar.set_points(e_a, w_b)
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(e_a))
    ar.set_bound(1, b, b.mapFromScene(w_b))
    ar._apply_routing()
    ys = {round(ar.mapToScene(p).y(), 1) for p in ar._pts}
    assert len(ys) > 1                                         # 정렬 전엔 계단(y가 여럿)
    for it in (a, b):
        it.setSelected(True)
    w.align_selection("vcenter")
    ar.reroute()
    ys = {round(ar.mapToScene(p).y(), 1) for p in ar._pts}
    assert len(ys) == 1                                        # 정렬 후엔 한 줄(계단 0)




def test_align_repaints_group_overlay():
    # [M5 실조건 fix] 그룹 선택 박스는 뷰의 drawForeground가 그려서, 프로그램이 아이템만 옮기면
    # 옛 점선이 남는다(사용자 화면서 확인). 정렬·분배·undo 모두 뷰포트 전체 갱신을 걸어야 한다.
    # 잔상 자체는 오프스크린서 재현 불가(render가 전면 재도색) → 갱신 호출 유무로 회귀를 막는다.
    w = CanvasWindow()
    calls = []
    w._repaint_overlays = lambda: calls.append(1)
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=120, y=90)   # 치우친 가운데
    c = _mk_pen_rect(w, x=400, y=30)
    for it in (a, b, c):
        it.setSelected(True)
    w.align_selection("top");      assert len(calls) == 1
    w.distribute_selection("x");   assert len(calls) == 2
    w.undo();                      assert len(calls) == 3
    w.redo();                      assert len(calls) == 4




def test_align_entry_points_visibility():
    # [디자인 재검토] 정렬/분배는 플로팅 툴바에서 제거하고 우클릭 메뉴로 일원화(중복 제거) —
    # 진입점은 우클릭 서브메뉴 1곳, '대상 2개 이상'에서만 뜬다.
    w = CanvasWindow()
    labels = lambda: [a.text() for a in w._build_context_menu().actions() if not a.isSeparator()]
    a = _mk_pen_rect(w, x=0, y=0); a.setSelected(True)
    assert "정렬 / 분배" not in labels()
    b = _mk_pen_rect(w, x=100, y=60); b.setSelected(True)
    assert "정렬 / 분배" in labels()
    # 메뉴 구성 = 정렬 6 + 분배 4(균등 2 + 첫 간격 반복 2). [2026-08-23] "첫 간격 기준
    # 분배"가 헷갈린다는 피드백으로 라벨을 "첫 간격 반복"으로 정리 + 서브메뉴 10개 전부
    # 아이콘 부착(`docs/arrow_gap_distribute_design.md`의 후속 작업).
    act_widgets = [x for x in w._build_align_menu().actions() if not x.isSeparator()]
    acts = [x.text() for x in act_widgets]
    assert acts == ["왼쪽 맞춤", "가로 가운데", "오른쪽 맞춤",
                    "위쪽 맞춤", "세로 가운데", "아래쪽 맞춤",
                    "가로 균등 분배", "세로 균등 분배",
                    "가로 첫 간격 반복", "세로 첫 간격 반복"]
    assert all(not x.icon().isNull() for x in act_widgets)




def test_align_entry_shows_for_arrow_only_selection():
    # [실사용 버그 2026-08-23] 도형 없이 바인딩된 화살표만 3개 이상 선택해도 분배가
    # 가능한데(화살표 대표 세그먼트), 메뉴 표시 게이트가 도형 개수(_align_targets)만 보고
    # 서브메뉴 자체를 숨기던 버그.
    w = CanvasWindow()

    def mk_bound_arrow(y, x_end=100):
        h0 = _mk_pen_rect(w, x=-30, y=y - 10, ww=20, hh=20, width=0)
        h1 = _mk_pen_rect(w, x=x_end + 10, y=y - 10, ww=20, hh=20, width=0)
        it = _PolyArrowItem(QColor("#111111"), 2.0, True)
        p0 = QPointF(0, y - 15); p3 = QPointF(x_end, y + 15)
        it._pts = [p0, QPointF(0, y), QPointF(x_end, y), p3]
        it._routing = "ortho"; it._auto_route = True
        it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
        w._scene.addItem(it)
        it.set_bound(0, h0, h0.mapFromScene(p0))
        it.set_bound(len(it._pts) - 1, h1, h1.mapFromScene(p3))
        return it

    for it in (mk_bound_arrow(0), mk_bound_arrow(20), mk_bound_arrow(200)):
        it.setSelected(True)
    labels = [a.text() for a in w._build_context_menu().actions() if not a.isSeparator()]
    assert "정렬 / 분배" in labels

    # 화살표가 2개뿐이면(대표 세그먼트 합쳐도 3개 미만) 여전히 안 뜬다.
    w._scene.clearSelection()
    for it in (mk_bound_arrow(400), mk_bound_arrow(420)):
        it.setSelected(True)
    labels2 = [a.text() for a in w._build_context_menu().actions() if not a.isSeparator()]
    assert "정렬 / 분배" not in labels2




def test_sarrow_does_not_ride_shared_edge():
    # [M4-4 ⓐ 잔여] 나란히 놓인 두 박스의 N포트끼리 잇기. 옛 라우터는 두 윗변 위에 정확히 포개진
    # 직선을 냈다(_seg_hits_rect가 테두리 접촉을 '안전'으로 통과시키므로 관통 검사엔 안 걸림).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), -300, 0, 100, 60)
    sa = _mk_bound_sarrow(w, a, b, 0, 0)          # N → N
    pts = [sa.mapToScene(p) for p in sa._pts]
    assert _close(pts[0], QPointF(50, 0)) and _close(pts[-1], QPointF(-250, 0)), pts
    reenter, ride = _sarrow_defects(sa)
    assert not reenter and ride == 0, ("변 타기 잔존", ride, pts)
    # 두 박스 '위'로 넘어가는 다리여야 한다(윗변보다 확실히 바깥).
    assert min(p.y() for p in pts) < -_RIDE_TOL, pts




def test_sarrow_no_unnecessary_hump_on_reenter_fix():
    # [혹 버그 수정 2026-07-27] 실도면(123.ecad) 재현 — 재진입 회피가 conn_clear(가장 넉넉한
    # 여유)의 첫 A* 결과를 결함 없다는 이유만으로 즉시 채택해, 사다리가 더 짧은 경로를 찾을 기회를
    # 못 얻었다. 왼쪽 박스 S포트 → 오른쪽 박스 E포트 연결이 (8,-52)→(8,-92)→(287,-92)→(287,4)
    # 식으로 불필요하게 위로 솟았다가 내려오는 '혹'을 만들던 실제 배치.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), -290, -213, 181, 125)
    b = _mk_rect(w._scene, w.make_pen(), 44, -56, 207, 120)
    sa = _mk_bound_sarrow(w, a, b, 2, 1)          # S(a) -> E(b)
    pts = [sa.mapToScene(p) for p in sa._pts]
    reenter, ride = _sarrow_defects(sa)
    assert not reenter, ("연결 도형 관통", pts)
    assert ride == 0, ("변 타기", ride, pts)
    # 혹 있는 옛 경로는 정점 7개(중간에 위로 솟았다 내려오는 왕복 2정점 추가) — 수정 후엔 단순
    # Z자형 5개여야 한다(엘보 하나만 더 필요한 최소 경로).
    assert len(pts) <= 5, ("정점 과다 — 혹 재발 의심", pts)
    # 중간 정점(시작·끝 포트 제외)이 오른쪽 도형(top=-56) 위로 과도하게 높이 솟으면 혹이 남은 것.
    assert min(p.y() for p in pts[1:-1]) > -80, ("불필요하게 높은 우회(혹)", pts)




def test_sarrow_drag_preview_matches_release_no_hump():
    # [혹 버그 수정 2026-07-27] 실제 press→drag→release 마우스 이벤트로 위 실도면 배치를 그대로
    # 재연 — 드래그 중 라이브 미리보기와 릴리스 후 확정 경로가 완전히 같아야 한다(둘 다 같은
    # _apply_routing에 위임하므로). 사용자가 "미리보기와 결과값이 다르다"고 보고했던 경로 —
    # 조사 결과 원인은 build_elbow가 아니라 set_ortho_preview의 시작점 바인딩 누락이라 의심했으나,
    # 실제 mousePressEvent는 도형 테두리 press 시 그 자리에서 바로 시작점을 바인딩해(다른 코드
    # 경로) 그 가설은 틀렸음을 이 테스트로 확인 — _route_ortho 혹 수정 하나로 이미 preview==release.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    a = _mk_rect(w._scene, w.make_pen(), -290, -213, 181, 125)
    b = _mk_rect(w._scene, w.make_pen(), 44, -56, 207, 120)
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)

    sp = _shape_ports(a)[2][0]   # S(a)
    ep = _shape_ports(b)[1][0]   # E(b)

    press(sp)
    drag_move(QPointF(ep.x() - 5, ep.y() - 5))   # 근처 통과
    drag_move(ep)                                 # 포트 위 — 스냅+라이브 바인딩
    live_pts = [view._temp.mapToScene(p) for p in view._temp._pts]
    release(ep)

    arrows = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(arrows) == 1, arrows
    final_pts = [arrows[0].mapToScene(p) for p in arrows[0]._pts]

    assert len(live_pts) == len(final_pts) and all(
        _close(x, y) for x, y in zip(live_pts, final_pts)), \
        ("미리보기≠확정", live_pts, final_pts)




def test_sarrow_no_reenter_when_conn_shapes_close():
    # [M4-4 ⓐ 잔여] 두 연결 도형이 conn_clear(36px)보다 가까우면 한쪽 스텁이 반대쪽 팽창 사각형
    # 안에 갇혀 A*가 실패 → 옛 코드는 preferred로 폴백했고 그 preferred가 곧 관통 경로였다.
    from easycad.canvas.annotator_core import _ortho_elbow, _path_hits_rects
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), -160, -60, 100, 60)
    sa = _mk_bound_sarrow(w, a, b, 1, 1)          # E → E (타깃이 서쪽)
    s0, e0 = QPointF(100, 30), QPointF(-60, -30)
    ns = sa._bound_normal_scene(0); ne = sa._bound_normal_scene(len(sa._pts) - 1)
    # 전제: 회피 없는 preferred는 실제로 A를 관통한다(테스트가 유의미하려면).
    pref = [s0] + _ortho_elbow(s0, e0, ns, ne) + [e0]
    assert _path_hits_rects(pref, [a.mapRectToScene(a.rect())]), pref
    pts = [sa.mapToScene(p) for p in sa._pts]
    assert _close(pts[0], s0) and _close(pts[-1], e0), pts
    reenter, ride = _sarrow_defects(sa)
    assert not reenter, ("연결 도형 관통", pts)
    assert ride == 0, ("변 타기", ride, pts)




def test_route_ortho_clean_path_stub_then_elbow():
    # [M4-4 ⓐ 잔여 → 2026-07-30 stub-out 수정] 결함 없는 배치도 이제 항상 법선 스텁을 먼저
    # 낸다(변 타기 방지 — 실사용 피드백 2026-07-30). 이 테스트가 지키는 불변식은 '사다리·A*가
    # 깨끗한 경로에 개입하지 않는다'는 원래 취지 그대로다 — 결과는 raw _ortho_elbow이 아니라
    # '스텁 → 그 스텁점 사이 엘보'와 정확히 같아야 하고(추가 우회 없음), conn_rects 유무로는
    # 스텁 거리만 달라진다(own-rect 팽창 이스케이프 vs flat clearance).
    from easycad.canvas.annotator_core import (
        _route_ortho, _ortho_elbow, _normal_stub, _CONN_CLEAR_MULT)
    s, e = QPointF(100, 30), QPointF(300, 30)     # E → W, 마주보고 같은 높이
    ns, ne = QPointF(1, 0), QPointF(-1, 0)
    clearance = 12.0

    plain = _route_ortho(s, e, ns, ne, [], clearance)
    s_stub = _normal_stub(s, ns, clearance)
    e_stub = _normal_stub(e, ne, clearance)
    expect_plain = [s_stub] + _ortho_elbow(s_stub, e_stub, ns, ne) + [e_stub]
    assert plain == expect_plain, (plain, expect_plain)

    conn_clear = clearance * _CONN_CLEAR_MULT
    A, B = QRectF(0, 0, 100, 60), QRectF(300, 0, 100, 60)
    with_conn = _route_ortho(s, e, ns, ne, [], clearance, conn_rects=(A, B))
    A_infl = A.adjusted(-conn_clear, -conn_clear, conn_clear, conn_clear)
    B_infl = B.adjusted(-conn_clear, -conn_clear, conn_clear, conn_clear)
    s_stub2 = _normal_stub(s, ns, conn_clear, A_infl)
    e_stub2 = _normal_stub(e, ne, conn_clear, B_infl)
    expect_conn = [s_stub2] + _ortho_elbow(s_stub2, e_stub2, ns, ne) + [e_stub2]
    assert with_conn == expect_conn, (with_conn, expect_conn)




def test_route_ortho_ride_exemption_is_per_owner():
    # [M4-4 ⓐ 잔여] 타기 면제는 '그 끝점이 붙은 도형'에만 준다 — 같은 세그먼트라도 *다른* 도형의
    # 변을 타면 타기다. (이 구분이 없으면 '내 도형에서 수직 이탈 = 통째 면제'가 되어 상대 도형
    # 변 타기를 통으로 놓친다 — 설계 검토서 실제로 걸린 구멍.)
    from easycad.canvas.annotator_core import _path_ride_len
    A = QRectF(0, 0, 100, 60)          # 출발 도형
    B = QRectF(-50, -260, 100, 60)     # 도착 도형(아랫변 y=-200)
    pts = [QPointF(0, 30), QPointF(0, -200)]   # A의 W포트에서 수직으로 올라가 B 아랫변에 도착
    ns, ne = QPointF(-1, 0), QPointF(0, 1)
    # 이 수직선은 A의 좌변(x=0) 위를 30px 탄다. 도착 끝점 면제(ne)가 A에까지 번지면 0이 된다.
    assert _path_ride_len(pts, [(A, "start"), (B, "end")], ns, ne) == 30
    # 반대로 자기 도형에서 법선대로 곧게 이탈하는 세그먼트는 면제 — 타기 0.
    ok = [QPointF(100, 30), QPointF(136, 30)]
    assert _path_ride_len(ok, [(A, "start")], QPointF(1, 0), None) == 0




def test_sarrow_routing_is_idempotent():
    # [M4-4 ⓐ 잔여] 되먹임 없음 — 라우터는 끝점·법선·장애물만 보고 결정하므로 재호출해도 같은
    # 경로여야 한다(두 번째 build_elbow는 '변경 없음'=False). 사다리·점수화 도입 후에도 유지.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), -300, 0, 100, 60)
    sa = _mk_bound_sarrow(w, a, b, 0, 0)
    first = [sa.mapToScene(p) for p in sa._pts]
    assert sa.build_elbow() is False, "재호출이 경로를 바꿈(되먹임 위험)"
    again = [sa.mapToScene(p) for p in sa._pts]
    assert all(_close(x, y) for x, y in zip(first, again)), (first, again)




def test_connected_rects_is_endpoint_tuple():
    # [M4-4 ⓐ 잔여] _connected_rects는 (start|None, end|None) 2-튜플 — 타기 면제가 어느 끝점의
    # 도형인지 알아야 하기 때문. 한쪽만 도형에 붙은 커넥터는 그 자리가 None으로 남는다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(300, 30))
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30))
    rects = sa._connected_rects()
    assert isinstance(rects, tuple) and len(rects) == 2, rects
    assert rects[0] is not None and rects[1] is None, rects




def test_ortho_drag_still_rebinds_endpoint():
    # [실조건 2026-07-27] F8(직교 제약)로 끝점을 도형 위 비-포트 지점으로 재부착해도, mouseMoveEvent의
    # 그 분기는 _move_endpoint_with_snap을 안 거쳐(축 제약이 테두리 스냅보다 우선) set_bound를 아예
    # 호출하지 않았다 — 시각적으로는 붙어 보여도 지속 연결이 안 걸려 도형을 옮겨도 화살표가 그대로
    # 남았다(사용자 보고). _rebind_at_fixed_point가 위치는 유지한 채 바인딩만 갱신해야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 150, 90)
    b = _mk_rect(w._scene, w.make_pen(), 600, 0, 150, 90)
    sp = _shape_ports(a)[1][0]; ep = _shape_ports(b)[3][0]
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(sp, ep)
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, sp); sa.set_bound(1, b, ep)
    sa._auto_route = True; sa.build_elbow()

    # 뗀다(빈 공간으로) — mouseMoveEvent의 일반 분기와 동일 경로.
    sa._on_endpoint_drag_start(0)
    sa._move_endpoint_with_snap(0, sa.mapFromScene(QPointF(300, 300)))
    sa._on_endpoint_drag_end(0)
    assert sa._bound(0) is None

    # F8로 A의 변 위 '비-포트' 지점에 재부착 — mouseMoveEvent의 F8 분기를 그대로 재현.
    # [2026-07-29 갱신] _ortho_endpoint는 현재 이웃 정점(_pts[1]) 기준으로 축을 제약하는데,
    # 끝점 드래그가 '새로 그리기'와 동일하게 매 프레임 전체 재계산되도록 바뀌면서(위 detach
    # 단계에서 이미 A* 우회 경로가 생겨 이웃 정점 위치가 달라짐) 그 축 제약 결과가 도형 A와
    # 무관한 곳으로 나올 수 있다 — 이 테스트가 검증하려는 건 그 축 제약 계산 자체가 아니라
    # `_rebind_at_fixed_point`가 위치를 유지한 채 바인딩만 거는지이므로, 목표 지점을 직접
    # 지정해 그 부분만 검증한다.
    sa._on_endpoint_drag_start(0)
    target = sa.mapFromScene(QPointF(150, 20))   # A의 우측 변 위, 포트 아닌 지점
    sa._set_endpoint(0, target)
    sa._rebind_at_fixed_point(0, target)
    sa._on_endpoint_drag_end(0)
    assert sa._bound(0) is a, ("F8 재부착이 바인딩을 안 걸음", sa._bound(0))
    assert _close(sa.mapToScene(sa._pts[0]), sa.mapToScene(target)), "위치가 바뀜(축 제약 훼손)"

    # 도형을 옮기면 이제 따라와야 한다.
    before = sa.mapToScene(sa._pts[0])
    a.setPos(QPointF(37, 41)); w._on_scene_changed(None)
    after = sa.mapToScene(sa._pts[0])
    assert (after - before).manhattanLength() > 10, ("도형 이동에 안 따라옴", before, after)




def test_ortho_drag_endpoint_unbinds_away_from_shape():
    # 위와 대칭 — F8로 도형에서 먼 자유 공간으로 옮기면 unbind돼야 한다(스텁 바인딩 잔존 방지).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 150, 90)
    b = _mk_rect(w._scene, w.make_pen(), 600, 0, 150, 90)
    sp = _shape_ports(a)[1][0]; ep = _shape_ports(b)[3][0]
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(sp, ep)
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, sp); sa.set_bound(1, b, ep)
    sa._auto_route = True; sa.build_elbow()

    sa._on_endpoint_drag_start(0)
    target = sa._ortho_endpoint(0, sa.mapFromScene(QPointF(400, 400)))
    sa._set_endpoint(0, target)
    sa._rebind_at_fixed_point(0, target)
    sa._on_endpoint_drag_end(0)
    assert sa._bound(0) is None, "먼 지점인데 바인딩이 남음"




def test_line_endpoint_ortho_drag_does_not_crash():
    # _LineItem은 _connects_to_border()=False에 set_bound 자체가 없다 — 가드 없이 부르면
    # AttributeError. Shift·F8 분기에서도 안전해야 한다.
    w = CanvasWindow()
    ln = _LineItem(0, 0, 150, 0)
    ln.setPen(w.make_pen())
    ln.setFlags(ln.GraphicsItemFlag.ItemIsSelectable | ln.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ln)
    ln._rebind_at_fixed_point(0, QPointF(10, 10))   # 크래시 안 하면 통과




def test_border_snap_prefers_shape_port_over_arrow_endpoint():
    # [실조건 2026-07-26] 포트에 이미 화살표가 붙어 있으면 그 끝점이 포트와 거리 0으로 동일해,
    # 나중에 도는 선·화살표 루프가 `<=` 때문에 항상 이겼다 → ⓐ shape=None이라 지속 연결이 안
    # 걸리고 ⓑ 이탈 법선이 상대 화살표 방향(정반대)으로 잡혔다. 동점은 도형이 이겨야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 150, 90)
    b = _mk_rect(w._scene, w.make_pen(), 600, 0, 150, 90)
    port_e, n_e = _shape_ports(a)[1]                  # A의 E 포트
    view_pos = w._view.mapFromScene(port_e)
    first = w._view._border_snap_at(view_pos)
    assert first is not None and first[2] is a, first
    assert _close(first[1], n_e), (first[1], n_e)     # 바깥 법선 = +x

    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    ep = _shape_ports(b)[3][0]
    sa.set_points(port_e, ep)
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, port_e); sa.set_bound(1, b, ep)
    sa._auto_route = True; sa.build_elbow()

    again = w._view._border_snap_at(view_pos)
    assert again is not None and again[2] is a, ("포트를 화살표 끝점에 뺏김", again)
    assert _close(again[1], n_e), ("이탈 법선이 뒤집힘", again[1], n_e)
    # 포트에서 떨어진 화살표 몸통은 여전히 스냅 대상(M4-2b 회귀 아님).
    mid = sa.mapToScene(sa._pts[len(sa._pts) // 2])
    got = w._view._border_snap_at(w._view.mapFromScene(mid))
    assert got is not None, "화살표 몸통 스냅이 죽음"


# ---------------------------------------------------------------------------
# [편의기능] Alt+드래그 복사 / Shift+드래그 축 고정 / Z-order / 그룹 / 잠금
# ---------------------------------------------------------------------------


def test_alt_drag_copy_clones_selection():
    # Alt+press = 제자리 복제 + 복제본 선택(원본은 선택 해제). 이어지는 Qt 기본 드래그가
    # 그 복제본을 옮기므로, 여기서는 뷰의 분기(복제·선택 전환·undo)까지만 검증한다
    # (Qt 내부 grabber를 통한 실제 드래그 이동은 오프스크린서 재현 불가 — CLAUDE.md M4-3 전례).
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=10, y=10, ww=40, hh=30)
    it.setSelected(True)
    n0 = len(w._scene.items())
    u0 = len(w._undo)
    ev = _mods_event("press", w._view, QPointF(30, 25), Qt.KeyboardModifier.AltModifier)
    w._view._maybe_alt_drag_copy(ev)
    assert len(w._scene.items()) == n0 + 1
    assert len(w._undo) == u0 + 1
    clones = [x for x in w._scene.selectedItems() if x is not it]
    assert len(clones) == 1, clones
    clone = clones[0]
    assert not it.isSelected()          # 원본은 선택 해제
    assert _close(clone.pos(), it.pos())  # 제자리(오프셋 없음)




def test_alt_drag_copy_noop_without_alt():
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=10, y=10, ww=40, hh=30)
    it.setSelected(True)
    n0 = len(w._scene.items())
    ev = _mods_event("press", w._view, QPointF(30, 25), Qt.KeyboardModifier.NoModifier)
    w._view._maybe_alt_drag_copy(ev)
    assert len(w._scene.items()) == n0   # Alt 없으면 복제 없음




def test_alt_drag_copy_rebinds_arrow_within_group():
    # Alt+드래그 복제도 duplicate_selection/paste_selection과 동일한 배치내 재연결이 필요하다
    # (같은 clone() 경유 버그 — 세 진입점 모두 remap_grouped_bindings를 거친다).
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=10, y=10, ww=40, hh=30)
    b = _mk_pen_rect(w, x=300, y=20, ww=40, hh=30)
    ar = _ArrowItem(QColor("#111111"), 3, True)
    pa, pb = QPointF(40, 15), QPointF(0, 15)
    ar.set_points(a.mapToScene(pa), b.mapToScene(pb))
    ar.set_bound(0, a, pa); ar.set_bound(1, b, pb)
    w._scene.addItem(ar)
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    ev = _mods_event("press", w._view, a.mapToScene(QPointF(20, 15)), Qt.KeyboardModifier.AltModifier)
    w._view._maybe_alt_drag_copy(ev)
    rects = [x for x in w._scene.items() if isinstance(x, _RectItem)]
    arrows = [x for x in w._scene.items() if isinstance(x, _ArrowItem)]
    assert len(rects) == 4 and len(arrows) == 2
    new_ar = [x for x in arrows if x is not ar][0]
    new_a = [r for r in rects if r is not a and r.rect() == a.rect()][0]
    new_b = [r for r in rects if r is not b and r.rect() == b.rect()][0]
    assert new_ar._bind1 is new_a and new_ar._bind2 is new_b   # 사본끼리 재연결
    assert ar._bind1 is a and ar._bind2 is b                   # 원본은 불변




def test_axis_lock_constrains_to_dominant_axis():
    # Shift+드래그 — 첫 유의미한 편차가 더 큰 축으로 고정, 반대 축 성분은 되돌린다.
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=0, y=0, ww=40, hh=30)
    it.setSelected(True)
    view = w._view
    view._snapshot_movable()
    old = QPointF(it.pos())
    it.setPos(QPointF(old.x() + 20, old.y() + 3))   # 수평이 지배적
    ev = _mods_event("move", view, QPointF(0, 0), Qt.KeyboardModifier.ShiftModifier)
    view._apply_axis_lock(ev)
    assert view._axis_lock == "h"
    assert _close(it.pos(), QPointF(old.x() + 20, old.y()))   # y는 원위치로 복원




def test_axis_lock_with_multiple_scene_items():
    # 회귀: _move_snap은 씬의 '모든' movable 아이템을 담는데(선택 무관), 델타를 스냅 리스트의
    # 첫 아이템으로 재면 그게 드래그 중인 아이템이 아닐 때(도형 2개 이상이면 흔함) 축 고정이
    # 영영 안 걸린다. 안 움직이는 other를 먼저 만들어 스냅 리스트 앞자리를 차지하게 한다.
    # scene.items()는 동일 z에서 '나중에 추가된 것이 먼저'(맨 위) 순으로 나온다 — other를
    # it보다 나중에 추가해야 _move_snap[0]을 차지해 회귀 시나리오가 재현된다.
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=0, y=0, ww=40, hh=30)
    other = _mk_pen_rect(w, x=500, y=500, ww=40, hh=30)   # 선택 안 됨 — 절대 안 움직임
    other_pos0 = QPointF(other.pos())   # rect 좌표가 아니라 pos()(기본 0,0) 기준으로 비교
    it.setSelected(True)
    view = w._view
    view._snapshot_movable()
    assert view._move_snap[0][0] is other, "테스트 전제 붕괴: other가 스냅 리스트 첫 자리가 아님"
    old = QPointF(it.pos())
    it.setPos(QPointF(old.x() + 20, old.y() + 3))
    ev = _mods_event("move", view, QPointF(0, 0), Qt.KeyboardModifier.ShiftModifier)
    view._apply_axis_lock(ev)
    assert view._axis_lock == "h", "다른 정지 아이템 때문에 축 고정이 발동 안 함(회귀)"
    assert _close(it.pos(), QPointF(old.x() + 20, old.y()))
    assert _close(other.pos(), other_pos0)   # other는 그대로(선택 안 됐으니 손대면 안 됨)




def test_axis_lock_off_without_shift():
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=0, y=0, ww=40, hh=30)
    it.setSelected(True)
    view = w._view
    view._snapshot_movable()
    it.setPos(QPointF(20, 3))
    ev = _mods_event("move", view, QPointF(0, 0), Qt.KeyboardModifier.NoModifier)
    view._apply_axis_lock(ev)
    assert view._axis_lock is None
    assert _close(it.pos(), QPointF(20, 3))   # Shift 없으면 손대지 않음




def test_bring_to_front_send_to_back():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0)
    b = _mk_pen_rect(w, x=100, y=0)
    a.setSelected(True)
    w.bring_to_front()
    assert a.zValue() > b.zValue()
    w.undo()
    assert a.zValue() == 0.0 and b.zValue() == 0.0
    w.redo()
    assert a.zValue() > b.zValue()
    a.setSelected(False); b.setSelected(True)
    w.send_to_back()
    assert b.zValue() < a.zValue()




def test_zorder_excludes_titleblock():
    w = CanvasWindow()
    tb = _TitleBlockItem("A4", "landscape")
    w._scene.addItem(tb)
    r = _mk_pen_rect(w, x=0, y=0)
    tb.setSelected(True); r.setSelected(True)
    assert tb not in w._edit_targets()
    assert r in w._edit_targets()




def test_group_ungroup_and_selection_sync():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0)
    b = _mk_pen_rect(w, x=100, y=0)
    a.setSelected(True); b.setSelected(True)
    u0 = len(w._undo)
    w.group_selection()
    assert len(w._undo) == u0 + 1
    assert a._group_id is not None and a._group_id == b._group_id
    # 하나만 선택해도 selectionChanged를 통해 그룹 전체가 딸려온다.
    w._scene.clearSelection()
    a.setSelected(True)
    assert b.isSelected(), "그룹 동반선택 실패"
    w.ungroup_selection()
    assert a._group_id is None and b._group_id is None
    w.undo()
    assert a._group_id is not None and a._group_id == b._group_id   # 그룹 해제 undo




def test_group_requires_two_or_more():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0)
    a.setSelected(True)
    w.group_selection()
    assert a._group_id is None   # 1개 선택은 그룹화하지 않음




def test_lock_toggle_blocks_selection_and_move():
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=0, y=0)
    it.setSelected(True)
    w.toggle_lock_selection()
    assert it._locked is True
    assert not it.isSelected()
    assert not (it.flags() & it.GraphicsItemFlag.ItemIsSelectable)
    assert not (it.flags() & it.GraphicsItemFlag.ItemIsMovable)
    # 잠긴 객체는 select_all로도 안 잡힌다.
    w.select_all()
    assert not it.isSelected()
    w.unlock_all()
    assert it._locked is False
    assert it.flags() & it.GraphicsItemFlag.ItemIsSelectable
    assert it.flags() & it.GraphicsItemFlag.ItemIsMovable




def test_lock_toggle_undo():
    w = CanvasWindow()
    it = _mk_pen_rect(w, x=0, y=0)
    it.setSelected(True)
    w.toggle_lock_selection()
    assert it._locked is True
    w.undo()
    assert it._locked is False
    assert it.flags() & it.GraphicsItemFlag.ItemIsSelectable




def test_convenience_keyboard_shortcuts_dispatch():
    # keyPressEvent 배선 자체(host 메서드 직접호출이 아니라 실제 단축키 경로)를 검증.
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    CTRL = Qt.KeyboardModifier.ControlModifier
    CTRL_SHIFT = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    w = CanvasWindow(); w.show(); w.set_tool("select")
    view = w._view
    a = _mk_pen_rect(w, x=0, y=0)
    b = _mk_pen_rect(w, x=100, y=0)
    a.setSelected(True); b.setSelected(True)

    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_G, CTRL))
    assert a._group_id is not None and a._group_id == b._group_id   # Ctrl+G

    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_G, CTRL_SHIFT))
    assert a._group_id is None and b._group_id is None              # Ctrl+Shift+G

    w._scene.clearSelection(); a.setSelected(True)
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketRight, CTRL))
    assert a.zValue() > b.zValue()                                  # Ctrl+]

    w._scene.clearSelection(); a.setSelected(True)
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_BracketLeft, CTRL))
    assert a.zValue() < b.zValue()                                  # Ctrl+[

    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_L, CTRL))
    assert a._locked is True                                        # Ctrl+L(선택은 a만)




def test_no_duplicate_window_action_shortcuts():
    # [실조건 버그] 위 테스트처럼 view.keyPressEvent를 직접 호출하면 Qt의 실제 단축키 라우팅을
    # 건너뛰어, 상단바/메뉴 QAction에 같은 단축키가 이미 배정돼 있으면(WindowShortcut이 우선
    # 가로채 뷰의 keyPressEvent 분기가 영영 발화 못 함) 오프스크린 스모크로는 안 잡힌다. 실제로
    # Mermaid 가져오기(Ctrl+Shift+G)가 그룹 해제(Ctrl+Shift+G, 뷰 raw 핸들러)를 막고 있었다
    # (Ctrl+Shift+F로 재배정해 해소). 이 불변조건으로 향후 재충돌을 정적으로 잡는다.
    from PyQt6.QtGui import QAction
    w = CanvasWindow()
    seen = {}
    dups = []
    for a in w.findChildren(QAction):
        ks = a.shortcut()
        if ks.isEmpty():
            continue
        key = ks.toString()
        if key in seen and seen[key] is not a:
            dups.append((key, seen[key].text(), a.text()))
        else:
            seen[key] = a
    assert not dups, f"중복 단축키 발견: {dups}"




def test_group_body_gap_drag_moves_selection():
    # [편의기능] 다중선택 바운딩박스 안쪽인데 실제 도형이 없는 '빈틈'을 눌러 끌어도, 선택된
    # 도형 전체가 함께 이동해야 한다(Lucid/FigJam). 종전엔 그 자리에 아이템이 없어 Qt가 못
    # 잡고 러버밴드(재선택)로 오인됐다.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select")
    view = w._view
    a = _mk_pen_rect(w, x=0, y=0, ww=40, hh=30)
    b = _mk_pen_rect(w, x=300, y=20, ww=40, hh=30)
    a.setSelected(True); b.setSelected(True)
    bbox = view._group.bbox()
    gap = QPointF(bbox.center().x(), bbox.center().y())   # 두 네모 사이 빈 공간(실제 도형 없음)
    assert view._is_empty_area(view.mapFromScene(gap))    # 전제: 이 지점엔 진짜 아이템이 없다
    assert view._group_body_area_at(view.mapFromScene(gap))  # 하지만 그룹 바운딩박스 안쪽이다

    a0, b0 = QPointF(a.pos()), QPointF(b.pos())
    u0 = len(w._undo)

    def _ev(etype, scene_pt, buttons, mods=Qt.KeyboardModifier.NoModifier):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, Qt.MouseButton.LeftButton, buttons, mods)

    NB = Qt.MouseButton.NoButton
    L = Qt.MouseButton.LeftButton
    view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, gap, L))
    assert view._group_body_drag
    moved_to = QPointF(gap.x() + 25, gap.y() + 15)
    view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, moved_to, L))
    view.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, moved_to, NB))
    assert not view._group_body_drag

    assert _close(a.pos(), QPointF(a0.x() + 25, a0.y() + 15))
    assert _close(b.pos(), QPointF(b0.x() + 25, b0.y() + 15))
    assert len(w._undo) == u0 + 1
    w.undo()
    assert _close(a.pos(), a0) and _close(b.pos(), b0)


def test_group_body_gap_alt_drag_copies_selection():
    # [버그 수정 2026-08-19] 실사용 보고: 다중선택 후 도형을 직접 눌러 Alt+드래그하면
    # 복제되는데, 같은 선택의 바운딩박스 안쪽 '빈틈'(도형이 없는 곳)에서 Alt+드래그하면
    # 복제 없이 그냥 원본이 이동만 됐다 — `_group_body_area_at` 경로가 `_maybe_alt_drag_copy`를
    # 아예 호출하지 않던 것이 원인.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select")
    view = w._view
    a = _mk_pen_rect(w, x=0, y=0, ww=40, hh=30)
    b = _mk_pen_rect(w, x=300, y=20, ww=40, hh=30)
    a.setSelected(True); b.setSelected(True)
    bbox = view._group.bbox()
    gap = QPointF(bbox.center().x(), bbox.center().y())
    assert view._is_empty_area(view.mapFromScene(gap))
    assert view._group_body_area_at(view.mapFromScene(gap))

    a0, b0 = QPointF(a.pos()), QPointF(b.pos())
    n0 = len(w._scene.items())
    u0 = len(w._undo)

    def _ev(etype, scene_pt, buttons, mods=Qt.KeyboardModifier.NoModifier):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, Qt.MouseButton.LeftButton, buttons, mods)

    NB = Qt.MouseButton.NoButton
    L = Qt.MouseButton.LeftButton
    ALT = Qt.KeyboardModifier.AltModifier
    view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, gap, L, ALT))
    assert view._group_body_drag
    # 원본 자리에 복제본이 새로 생기고, 이제 선택은 복제본이어야 한다(원본은 선택 해제).
    assert len(w._scene.items()) == n0 + 2
    assert not a.isSelected() and not b.isSelected()
    moved_to = QPointF(gap.x() + 25, gap.y() + 15)
    view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, moved_to, L, ALT))
    view.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, moved_to, NB, ALT))
    assert not view._group_body_drag

    # 원본은 제자리에 그대로 남아 있고, 이동한 것은 복제본이다.
    assert _close(a.pos(), a0) and _close(b.pos(), b0)
    clones = [x for x in view.scene().selectedItems() if x not in (a, b)]
    assert len(clones) == 2
    assert len(w._undo) == u0 + 2   # 복제(add_many) 1건 + 이동 1건


def test_group_ungroup_shows_status_message():
    # [편의기능] 그룹/그룹해제는 눈에 띄는 되돌림 없이 조용히 상태만 바뀌던 것 — 상태바 메시지로
    # 즉시 인지 가능해야 한다.
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=100, y=0)
    a.setSelected(True); b.setSelected(True)
    w.group_selection()
    assert "그룹" in w.statusBar().currentMessage()
    w.ungroup_selection()
    assert "해제" in w.statusBar().currentMessage()




def test_group_lock_ecad_roundtrip():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0)
    b = _mk_pen_rect(w, x=100, y=0)
    c = _mk_pen_rect(w, x=200, y=0)   # 그룹과 무관한 별도 객체 — 잠금 대상
    a.setSelected(True); b.setSelected(True)
    w.group_selection()
    w._scene.clearSelection()
    c.setSelected(True)
    w.toggle_lock_selection()   # c만 잠금(a·b를 선택하면 그룹 동반선택으로 둘 다 딸려온다)
    path = os.path.join(_TMP, "group_lock.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    load_document(w2._scene, path)
    items = [it for it in w2._scene.items() if hasattr(it, "_group_id")]
    locked = [it for it in items if it._locked]
    grouped = [it for it in items if it._group_id]
    assert len(locked) == 1
    assert len(grouped) == 2 and grouped[0]._group_id == grouped[1]._group_id
    assert not (locked[0].flags() & locked[0].GraphicsItemFlag.ItemIsMovable)




def test_grid_toggle_action():
    # [그리드] 표시+스냅 통합 토글(Shift+G) — 기본 꺼짐(2026-08-11), 트리거 시 owner.grid_enabled에 반영.
    from easycad.canvas.host_widgets import _act_icon
    w = CanvasWindow()
    assert w._act_grid.isCheckable() and not w._act_grid.isChecked()
    assert w.grid_enabled is False
    assert not _act_icon("grid").isNull()
    w._act_grid.trigger()
    assert w._act_grid.isChecked() is True and w.grid_enabled is True




def test_grid_snap_scene_quantizes():
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow()
    w.grid_enabled = True   # 기본값은 off(2026-08-11)이므로 이 테스트는 켠 상태를 명시
    p = w._view._grid_snap_scene(QPointF(7, 13))
    assert p == QPointF(round(7 / _GRID_SPACING) * _GRID_SPACING,
                         round(13 / _GRID_SPACING) * _GRID_SPACING)




def test_grid_snap_scene_disabled_noop():
    w = CanvasWindow()
    w.grid_enabled = False
    assert w._view._grid_snap_scene(QPointF(7, 13)) == QPointF(7, 13)




def test_grid_snap_move_quantizes_position():
    # [그리드] 단일 도형 이동 — 콘텐츠 rect의 실제 씬 위치가 격자 교차점으로 양자화(항상,
    # 임계값 없음). pos()가 아니라 mapToScene된 화면 기준점으로 검증 — pos() 자체는 아이템
    # 로컬 원점(대개 (0,0))과 무관해 격자 정렬을 보장하지 않는다(회귀: 아래 anchor 테스트).
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow()
    w.grid_enabled = True   # 기본값은 off(2026-08-11)이므로 이 테스트는 켠 상태를 명시
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    r.setPos(QPointF(7, 13)); r.setSelected(True)
    w._view._apply_grid_snap_move(False, False)
    anchor = r.mapToScene(r._content_rect().topLeft())
    assert abs(anchor.x() % _GRID_SPACING) < 1e-6
    assert abs(anchor.y() % _GRID_SPACING) < 1e-6




def test_grid_snap_move_respects_skip_axis():
    # [그리드] 스마트정렬/축고정이 이미 처리한 축은 skip_*로 건드리지 않는다(우선순위 위계).
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow()
    w.grid_enabled = True   # 기본값은 off(2026-08-11)이므로 이 테스트는 켠 상태를 명시
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    r.setPos(QPointF(7, 13)); r.setSelected(True)
    before = r.mapToScene(r._content_rect().topLeft())
    w._view._apply_grid_snap_move(True, False)   # x축 skip
    after = r.mapToScene(r._content_rect().topLeft())
    assert abs(after.x() - before.x()) < 1e-6       # x축 불변
    assert abs(after.y() % _GRID_SPACING) < 1e-6    # y축만 격자로




def test_grid_snap_move_disabled_noop():
    w = CanvasWindow()
    w.grid_enabled = False
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    r.setPos(QPointF(7, 13)); r.setSelected(True)
    w._view._apply_grid_snap_move(False, False)
    assert r.pos() == QPointF(7, 13)




def test_grid_snap_move_uses_scene_anchor_not_raw_pos():
    # [그리드][회귀] 마우스로 그린 도형은 로컬 rect가 클릭 시점 씬 좌표를 그대로 품고(pos()는
    # (0,0)에 남는 게 보통) — pos()만 격자에 맞추면 실제 화면 위치는 격자 밖일 수 있었다(1차 시도).
    # 아이템 로컬 원점(0,0)을 mapToScene해도 같은 함정(그 점은 실제 그려진 도형과 무관, pos()와
    # 동치일 뿐 — 2차 시도에서 발견). 콘텐츠 rect의 실제 화면 위치로 검증해야 한다.
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow()
    w.grid_enabled = True   # 기본값은 off(2026-08-11)이므로 이 테스트는 켠 상태를 명시
    r = _mk_rect(w._scene, w.make_pen(), 307, 53, 100, 60)   # 로컬 rect 원점 = (307,53), pos=(0,0)
    r.setSelected(True)
    assert r.pos() == QPointF(0, 0)   # 전제: pos()는 (0,0)에 남는다(실제 그리기 패턴과 동일)
    before = r.mapToScene(r._content_rect().topLeft())
    assert abs(before.x() % _GRID_SPACING) > 1e-6   # 전제: 시작 위치는 격자 밖(307%20=7)
    w._view._apply_grid_snap_move(False, False)
    anchor = r.mapToScene(r._content_rect().topLeft())
    assert abs(anchor.x() % _GRID_SPACING) < 1e-6
    assert abs(anchor.y() % _GRID_SPACING) < 1e-6




def test_grid_snap_move_skips_multiselect():
    # [그리드] 스마트정렬과 동일 관례 — 다중선택(그룹 변형 영역)엔 적용하지 않는다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b.setPos(QPointF(7, 13))
    a.setSelected(True); b.setSelected(True)
    w._view._apply_grid_snap_move(False, False)
    assert b.pos() == QPointF(7, 13)




def test_grid_snap_local_quantizes_unrotated():
    from easycad.canvas.annotator_core import _GRID_SPACING
    w = CanvasWindow()
    w.grid_enabled = True   # 기본값은 off(2026-08-11)이므로 이 테스트는 켠 상태를 명시
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)   # pos=(0,0) → local==scene
    snapped = r._grid_snap_local(QPointF(37, 51))
    assert snapped == QPointF(round(37 / _GRID_SPACING) * _GRID_SPACING,
                               round(51 / _GRID_SPACING) * _GRID_SPACING)




def test_grid_snap_local_disabled_noop():
    w = CanvasWindow()
    w.grid_enabled = False
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    lp = QPointF(37, 51)
    assert r._grid_snap_local(lp) == lp


# ---------------------------------------------------------------------------
# [실사용 버그 수정 2026-08-19] 펜 궤적 서브픽셀 정밀도 + 완성 시 스무딩
# ---------------------------------------------------------------------------


def test_scene_pos_precise_keeps_subpixel_fraction():
    # event.position().toPoint()로 정수 뷰포트 픽셀에 반올림하던 옛 경로와 달리,
    # _scene_pos_precise는 분수 좌표를 그대로 씬으로 환산해야 한다.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow()
    view = w._view
    vp = QPointF(140.37, 62.81)   # 정수가 아닌 뷰포트 픽셀 위치
    evt = QMouseEvent(QEvent.Type.MouseMove, vp, vp,
                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)
    precise = view._scene_pos_precise(evt)
    rounded = view.mapToScene(vp.toPoint())   # 옛(버그) 경로 — 정수 반올림 후 변환
    # 뷰가 확대·이동 없는 기본 상태라 스케일 ~1 → 반올림 오차(최대 0.71px)가 그대로 드러난다.
    assert abs(precise.x() - rounded.x()) > 0.05 or abs(precise.y() - rounded.y()) > 0.05
    # 왕복 검증 — 뷰 변환의 역행렬을 직접 곱한 값과 일치해야 한다(간접 mapToScene 우회 확인).
    inv, ok = view.viewportTransform().inverted()
    assert ok
    expect = inv.map(vp)
    assert abs(precise.x() - expect.x()) < 1e-6 and abs(precise.y() - expect.y()) < 1e-6


def test_smooth_freehand_path_converts_polyline_to_curve():
    # 픽셀 양자화로 생긴 계단형 지그재그(마우스 원시 샘플을 흉내)를 스무딩하면 lineTo가 아니라
    # cubicTo로 이어지는 매끄러운 곡선이 되어야 하고, 시작·끝점은 원본과 정확히 같아야 한다.
    from easycad.canvas.annotator_core import _smooth_freehand_path
    raw = QPainterPath(QPointF(0, 0))
    # 대각선을 따라가지만 축별로 번갈아 튀는 "계단" 패턴(정수 픽셀 반올림의 전형적 모양).
    for i in range(1, 21):
        x = i * 5 if i % 2 == 0 else (i - 1) * 5
        y = i * 5 if i % 2 else (i - 1) * 5
        raw.lineTo(QPointF(x, y))
    smoothed = _smooth_freehand_path(raw)
    n = smoothed.elementCount()
    assert n > 1
    has_curve = any(smoothed.elementAt(i).isCurveTo() for i in range(n))
    assert has_curve   # 이제 3차 베지어로 이어짐 — 원시 lineTo 폴리라인이 아니다
    first, last_raw = raw.elementAt(0), raw.elementAt(raw.elementCount() - 1)
    last_smooth = smoothed.elementAt(n - 1)
    assert _close(QPointF(smoothed.elementAt(0).x, smoothed.elementAt(0).y),
                  QPointF(first.x, first.y))
    assert _close(QPointF(last_smooth.x, last_smooth.y), QPointF(last_raw.x, last_raw.y))


def test_smooth_freehand_path_noop_below_three_points():
    from easycad.canvas.annotator_core import _smooth_freehand_path
    raw = QPainterPath(QPointF(0, 0))
    raw.lineTo(QPointF(10, 10))
    smoothed = _smooth_freehand_path(raw)
    assert smoothed.elementCount() == raw.elementCount()
    for i in range(raw.elementCount()):
        a, b = raw.elementAt(i), smoothed.elementAt(i)
        assert abs(a.x - b.x) < 1e-9 and abs(a.y - b.y) < 1e-9


def test_pen_tool_draw_commits_smoothed_curve():
    # 종단 시나리오 — 실제 뷰 마우스 이벤트로 펜 드래그(계단형 지그재그)를 흘려서, 그리는
    # 중엔 원시 폴리라인이던 것이 손을 뗀 순간 곡선으로 바뀌는지 확인.
    # [2026-08-19 실시간 스무딩 시도 → 같은 날 되돌림] 매 프레임 전체 재계산이 이미 그려진
    # 구간까지 흔드는 "울렁거림"을 실사용에서 유발해(RDP가 새 점마다 과거 critical point
    # 선택을 바꿈), 그리는 중엔 다시 원시 폴리라인만 보여준다 — 최종 스무딩만 유지.
    w = CanvasWindow(); w.set_tool("pen")
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    press(QPointF(0, 0))
    pts = [QPointF(10, 0), QPointF(10, 10), QPointF(20, 10), QPointF(20, 20),
           QPointF(30, 20), QPointF(30, 30)]
    for p in pts:
        drag_move(p)
    live = view._temp
    assert live is not None
    live_n = live.path().elementCount()
    assert live_n >= 3
    assert not any(live.path().elementAt(i).isCurveTo() for i in range(live_n))   # 그리는 중=직선
    release(pts[-1])
    items = [it for it in w._scene.items() if isinstance(it, _PathItem)]
    assert len(items) == 1
    final_path = items[0].path()
    n = final_path.elementCount()
    assert any(final_path.elementAt(i).isCurveTo() for i in range(n))   # 확정 후=곡선


def test_pen_tool_release_smooths_long_stroke_and_preserves_endpoint():
    # 긴 획(30점)도 놓는 순간 원시 누적(`self._path`)에서 스무딩되고, 끝점은 정확히 보존되는지.
    w = CanvasWindow(); w.set_tool("pen")
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    press(QPointF(0, 0))
    pts = [QPointF(i * 4, 20 * (1 - ((i - 15) / 15.0) ** 2)) for i in range(1, 31)]
    for p in pts:
        drag_move(p)
    assert not any(view._temp.path().elementAt(i).isCurveTo()
                   for i in range(view._temp.path().elementCount()))   # 그리는 중=여전히 직선
    release(pts[-1])
    final_path = [it for it in w._scene.items() if isinstance(it, _PathItem)][0].path()
    n = final_path.elementCount()
    assert any(final_path.elementAt(i).isCurveTo() for i in range(n))
    last = final_path.elementAt(n - 1)
    assert _close(QPointF(last.x, last.y), pts[-1])   # 끝점은 정확히 보존(궤적이 일그러지지 않음)


# ---------------------------------------------------------------------------
# [실사용 요청 2026-08-19] 펜 궤적(_PathItem) 양 끝 이산 포트
# ---------------------------------------------------------------------------


def test_shape_ports_pathitem_returns_two_endpoints():
    from easycad.canvas.annotator_core import _shape_ports
    it = _PathItem(QPainterPath(QPointF(0, 0)))
    p = QPainterPath(QPointF(0, 0))
    p.lineTo(QPointF(60, 0))
    p.lineTo(QPointF(100, 40))
    it.setPath(p)
    it.setPos(QPointF(500, 300))   # 아이템 위치가 있어도 scene 변환이 맞는지 함께 확인
    ports = _shape_ports(it)
    assert len(ports) == 2
    (sp0, n0), (sp1, n1) = ports
    assert _close(sp0, QPointF(500, 300))          # 시작점 = 로컬(0,0) + pos
    assert _close(sp1, QPointF(600, 340))          # 끝점 = 로컬(100,40) + pos
    assert abs(math.hypot(n0.x(), n0.y()) - 1.0) < 1e-6   # 법선은 단위벡터
    assert abs(math.hypot(n1.x(), n1.y()) - 1.0) < 1e-6
    assert n0.x() < 0   # 시작점 법선은 궤적이 뻗어나가는 반대(왼쪽=바깥)


def test_shape_ports_pathitem_too_short_returns_empty():
    from easycad.canvas.annotator_core import _shape_ports
    it = _PathItem(QPainterPath(QPointF(0, 0)))   # moveTo만, 점 하나
    assert _shape_ports(it) == []


def test_hover_port_at_shows_pathitem_endpoint():
    # 종단 — 미선택 펜 궤적 근처를 호버하면(다른 도형과 동일하게) 이산 끝점이 잡혀야 한다.
    w = CanvasWindow(); w.set_tool("select")
    view = w._view
    p = QPainterPath(QPointF(0, 0))
    p.lineTo(QPointF(50, 0))
    p.lineTo(QPointF(120, 60))
    it = _PathItem(p)
    it.setPen(w.make_pen())
    w._scene.addItem(it)
    hp = view._hover_port_at(view.mapFromScene(QPointF(120, 60)))
    assert hp is not None
    sh, sp, _n, is_discrete = hp
    assert sh is it and is_discrete
    assert _close(sp, QPointF(120, 60))


def test_border_snap_at_prefers_pathitem_endpoint_over_continuous():
    # 끝점 근처는 이산 포트(넓은 반경)가, 몸통 중간은 연속 폴백이 잡아야 한다 — 둘 다 살아있는지.
    w = CanvasWindow()
    view = w._view
    p = QPainterPath(QPointF(0, 0))
    p.lineTo(QPointF(200, 0))
    it = _PathItem(p)
    it.setPen(w.make_pen())
    w._scene.addItem(it)
    near_end = view._border_snap_at(view.mapFromScene(QPointF(198, 4)))
    assert near_end is not None and _close(near_end[0], QPointF(200, 0))
    mid = view._border_snap_at(view.mapFromScene(QPointF(100, 2)))
    assert mid is not None and _close(mid[0], QPointF(100, 0))   # 연속 폴백은 여전히 작동


def test_draw_port_dots_shown_on_idle_select_hover_for_shapes():
    # [실사용 지적 2026-08-19 → 2026-08-19 범위 재조정] 도형(사각형/원/심볼)은 화살표와 밀접히
    # 엮여 있어 select 도구의 유휴 호버(드래그 중 아님)에서도 포트점이 계속 보여야 화살표를
    # 넣고 빼기 편하다 — 처음엔 이 아래 펜(_PathItem) 케이스와 함께 도형까지 억제됐던 것을
    # 재확인해 도형만 원상복구(아래 별도 테스트가 펜은 여전히 억제됨을 확인).
    from unittest.mock import MagicMock
    w = CanvasWindow(); w.grid_enabled = False
    view = w._view
    rect = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    center = rect.sceneBoundingRect().center()
    view.mapFromGlobal = lambda gp: view.mapFromScene(center)

    w.set_tool("select")
    assert view._port_dot_target(center) is rect
    painter = MagicMock()
    view._draw_port_dots(painter, 1.0)
    assert painter.drawEllipse.called   # 도형은 유휴 호버에서도 그려야 함

    w.set_tool("arrow")
    painter2 = MagicMock()
    view._draw_port_dots(painter2, 1.0)
    assert painter2.drawEllipse.called

    # 활성 커넥터 드래그 중(_hp_dragging)이면 select여도 계속 그린다(실시간 부착 피드백).
    w.set_tool("select")
    view._hp_dragging = True
    painter3 = MagicMock()
    view._draw_port_dots(painter3, 1.0)
    assert painter3.drawEllipse.called
    view._hp_dragging = False


def test_draw_port_dots_suppressed_on_idle_select_hover_for_pen_only():
    # [실사용 지적 2026-08-19 → 2026-08-19 범위 재조정] 펜 궤적(`_PathItem`)은 화살표와 그런
    # 밀접한 관계가 없어 — select 도구의 유휴 호버에서 점이 뜨면 노이즈라는 원래 지적이 이
    # 케이스였다. [2026-08-25 좁힘] `_PathItem`은 SVG 가져오기/생성·DXF 폴백도 겸하게 되며
    # 억제 대상을 타입 전체가 아니라 `_freehand` 표식(펜 도구가 그릴 때만 True)으로 좁혔다 —
    # 이 테스트는 그 표식이 실제로 켜진 손그림 궤적만 계속 억제되는지 확인(위 도형 테스트와 대칭).
    from unittest.mock import MagicMock
    w = CanvasWindow(); w.grid_enabled = False
    view = w._view
    p = QPainterPath(QPointF(0, 0)); p.lineTo(QPointF(100, 0))
    pen_it = _PathItem(p)
    pen_it._freehand = True
    pen_it.setPen(w.make_pen())
    w._scene.addItem(pen_it)
    center = QPointF(50, 0)
    view.mapFromGlobal = lambda gp: view.mapFromScene(center)

    w.set_tool("select")
    assert view._port_dot_target(center) is pen_it
    painter = MagicMock()
    view._draw_port_dots(painter, 1.0)
    assert not painter.drawEllipse.called   # 펜은 유휴 호버에서 억제되어야 함

    w.set_tool("arrow")
    painter2 = MagicMock()
    view._draw_port_dots(painter2, 1.0)
    assert painter2.drawEllipse.called


def test_draw_port_dots_not_suppressed_for_non_freehand_path():
    # [실사용 요청 2026-08-25] SVG 가져오기/생성은 `_PathItem`으로 매핑되지만 `_freehand`가
    # 없다(False) — 손그림이 아니라 구조적 도형이므로 다른 도형처럼 select 유휴 호버에서도
    # 큐닷 예고점이 바로 보여야 화살표를 붙일 수 있다(위 테스트와 대칭 회귀 가드).
    from unittest.mock import MagicMock
    w = CanvasWindow(); w.grid_enabled = False
    view = w._view
    p = QPainterPath(QPointF(0, 0)); p.lineTo(QPointF(100, 0))
    svg_it = _PathItem(p)   # _freehand 미설정 — svg_import.parse_svg_* 결과와 동일 상태
    svg_it.setPen(w.make_pen())
    w._scene.addItem(svg_it)
    center = QPointF(50, 0)
    view.mapFromGlobal = lambda gp: view.mapFromScene(center)

    w.set_tool("select")
    assert view._port_dot_target(center) is svg_it
    painter = MagicMock()
    view._draw_port_dots(painter, 1.0)
    assert painter.drawEllipse.called   # 펜이 아니므로 억제되면 안 됨


# ---------------------------------------------------------------------------
# [실사용 요청 2026-08-19] 펜 궤적(_PathItem) 선택 시 양 끝점 드래그 핸들
# ---------------------------------------------------------------------------


def test_pathitem_uses_endpoints_and_matches_path_ends():
    p = QPainterPath(QPointF(10, 20))
    p.lineTo(QPointF(40, 20))
    p.lineTo(QPointF(90, 70))
    it = _PathItem(p)
    assert it._uses_endpoints() is True
    eps = it._endpoints()
    assert len(eps) == 2
    assert _close(eps[0], QPointF(10, 20))
    assert _close(eps[1], QPointF(90, 70))
    assert it._handle_indices() == [0, 1]


def test_pathitem_set_endpoint_line_moves_only_that_end():
    p = QPainterPath(QPointF(0, 0))
    p.lineTo(QPointF(50, 0))
    p.lineTo(QPointF(100, 0))
    it = _PathItem(p)
    it._set_endpoint(1, QPointF(100, 80))   # 끝점만 이동
    pts = it._endpoints()
    assert _close(pts[0], QPointF(0, 0))    # 시작점 불변
    assert _close(pts[1], QPointF(100, 80))
    mid = it.path().elementAt(1)
    assert _close(QPointF(mid.x, mid.y), QPointF(50, 0))   # 중간 정점도 불변


def test_pathitem_set_endpoint_curve_keeps_tangent_via_control_point_shift():
    # 스무딩(cubicTo)된 궤적의 끝점을 옮기면, 그 끝의 제어점도 같은 delta로 따라가야
    # 접선이 유지된다(끝만 툭 꺾이지 않음) — `_ArrowItem`과 동일 패턴 회귀 확인.
    from easycad.canvas.annotator_core import _smooth_freehand_path
    raw = QPainterPath(QPointF(0, 0))
    for x, y in [(10, 0), (20, 10), (30, 10), (40, 20), (50, 20)]:
        raw.lineTo(QPointF(x, y))
    smoothed = _smooth_freehand_path(raw, min_seg=0.0, epsilon=0.0)   # 전부 보존 → 확실히 곡선화
    it = _PathItem(smoothed)
    n0 = it.path().elementCount()
    assert it.path().elementAt(1).isCurveTo()   # 전제: 시작 직후가 곡선 제어점
    c1_before = it.path().elementAt(1)
    c1_before = QPointF(c1_before.x, c1_before.y)
    delta = QPointF(30, -15)
    start0 = it._endpoints()[0]
    it._set_endpoint(0, start0 + delta)
    assert it.path().elementCount() == n0   # 원소 개수(구조)는 안 바뀜
    assert _close(it._endpoints()[0], start0 + delta)
    c1_after = it.path().elementAt(1)
    c1_after = QPointF(c1_after.x, c1_after.y)
    assert _close(c1_after, c1_before + delta)   # c1도 같은 delta로 따라감(접선 유지)
    # 반대쪽 끝은 전혀 안 건드림.
    last_el = it.path().elementAt(n0 - 1)
    assert _close(QPointF(last_el.x, last_el.y), it._endpoints()[1])


def test_pathitem_endpoint_drag_end_to_end_via_view():
    w = CanvasWindow(); w.set_tool("select")
    view = w._view
    p = QPainterPath(QPointF(0, 0))
    p.lineTo(QPointF(100, 0))
    it = _PathItem(p)
    it.setPen(w.make_pen())
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    it.setSelected(True)

    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    end_local = it._endpoint_rect(1).center()
    press(it.mapToScene(end_local))
    assert it._drag_endpoint == 1   # 끝점 핸들이 실제로 히트됨
    drag_move(QPointF(100, 60))
    release(QPointF(100, 60))
    assert _close(it._endpoints()[1], QPointF(100, 60))
    assert _close(it._endpoints()[0], QPointF(0, 0))   # 반대쪽은 그대로


def test_arrow_endpoint_detach_reattach_handle_turns_green_when_bound():
    # [실사용 버그 수정 2026-08-19] "화살표를 처음 그릴 때 다른 도형에 가면 예고점이 보이는데
    # 한번 붙이고 뗐다가 다시 붙이면 예고점 안 보임(스냅은 됨)" — 부착(바인딩) 자체는 항상
    # 정상이었다. 처음엔 새로 그리기(`_update_arrow_draw`)처럼 view의 예고점 필드
    # (`_arrow_tip_snap`)를 갱신하는 방식으로 고쳤으나, 실사용 재확인 결과 그 마커(반경
    # 5/s 파란 원)가 바로 이 끝점 핸들 사각형(같은 파랑, 같은 위치·크기 — `_HANDLE_PX`가
    # 애초에 "_draw_snap_marker 지름과 동일")과 완전히 겹쳐 시각적으로 아무 차이가 없었다
    # (`drawForeground`가 아이템 자신의 `paint()`보다 나중에 그려져 오히려 핸들을 덮기까지
    # 했다). 최종 해법은 새 마커를 얹는 대신 핸들 자체의 색을 바꾸는 것 —
    # `_paint_endpoint_handles`가 그 인덱스의 `bound_shapes()`를 확인해 붙어 있으면 초록,
    # 아니면 기존 파랑으로 그린다(핸들 사각형의 실제 렌더 색을 픽셀로 검증).
    w = CanvasWindow(); w.set_tool("arrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, click, move, drag_move, _d = _draw_helpers(view)

    press(QPointF(0, 30)); drag_move(QPointF(305, 30)); release(QPointF(305, 30))
    arrow = [it for it in w._scene.items() if isinstance(it, _ArrowItem)][0]
    assert arrow.isSelected() and arrow._bind2 is not None

    w.set_tool("select")
    end_scene = arrow.mapToScene(arrow._endpoint_rect(1).center())
    press(end_scene)
    assert arrow._drag_endpoint == 1

    drag_move(QPointF(150, 200))   # 뗀다 — 도형에서 멀어짐
    assert arrow._bind2 is None
    assert arrow._handle_indices() == [0, 1]   # 아래 bound_shapes()[1] 인덱싱 전제 확인
    assert arrow.bound_shapes()[1] is None     # 핸들 색 판정이 보는 값 자체(파랑이어야 함)

    drag_move(QPointF(305, 30))    # 같은 테두리에 다시 붙인다
    assert arrow._bind2 is not None
    assert arrow.bound_shapes()[1] is not None   # 핸들 색 판정이 보는 값(초록이어야 함)

    release(QPointF(305, 30))
    assert arrow.bound_shapes()[1] is not None   # 릴리스 후에도 유지(색이 계속 초록이어야 함)


def test_arrow_endpoint_handle_pixel_color_reflects_binding():
    # 위 테스트의 데이터 계층(bound_shapes) 검증을 실제 렌더 픽셀로 한 번 더 — 핸들이
    # `_paint_endpoint_handles`를 실제로 타서 파랑/초록으로 그려지는지 육안 대신 픽셀로 확인.
    from easycad.canvas.core_shapes import _GREEN, _BLUE
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QColor

    w = CanvasWindow(); w.set_tool("arrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)
    view = w._view
    press, release, click, move, drag_move, _d = _draw_helpers(view)

    press(QPointF(0, 30)); drag_move(QPointF(305, 30)); release(QPointF(305, 30))
    arrow = [it for it in w._scene.items() if isinstance(it, _ArrowItem)][0]
    w.set_tool("select")
    press(arrow.mapToScene(arrow._endpoint_rect(1).center()))

    def dominant_color_at(scene_pt):
        img = view.viewport().grab().toImage()
        vp = view.mapFromScene(scene_pt)
        counts = {}
        for dx in range(-6, 7):
            for dy in range(-6, 7):
                c = img.pixelColor(QPoint(vp.x() + dx, vp.y() + dy)).name()
                counts[c] = counts.get(c, 0) + 1
        return max(counts, key=counts.get)

    drag_move(QPointF(150, 200))   # 뗀다 — 미부착이면 파랑
    assert dominant_color_at(arrow.mapToScene(arrow._endpoint_rect(1).center())) == QColor(_BLUE).name()

    drag_move(QPointF(305, 30))    # 다시 붙인다 — 부착되면 초록
    assert dominant_color_at(arrow.mapToScene(arrow._endpoint_rect(1).center())) == QColor(_GREEN).name()

    release(QPointF(305, 30))


# ---- [실사용 버그 수정 2026-08-19] Shift 정사각형 제약 — 심볼(sym:*) 드래그-그리기 ----------

def test_shift_square_constraint_applies_to_symbol_draw_tool_too():
    # `_cur_point`(core_view.py)의 Shift 정사각형/정원 제약이 rect/ellipse에만 걸려 있고
    # 심볼(sym:*, 예: 삼각형)은 같은 QRectF(sp,sp) 드래그-그리기 경로를 쓰는데도 빠져 있었다
    # — 팔레트에서 드래그해 꺼낸 뒤 리사이즈할 때의 Shift(종횡비 유지, 별개 메커니즘)와
    # 혼동하기 쉬운 다른 경로.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent

    w = CanvasWindow(); w.set_tool("sym:triangle")
    view = w._view

    def _ev(etype, scene_pt, buttons, mods=Qt.KeyboardModifier.NoModifier):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, Qt.MouseButton.LeftButton, buttons, mods)

    NB = Qt.MouseButton.NoButton
    L = Qt.MouseButton.LeftButton
    SHIFT = Qt.KeyboardModifier.ShiftModifier

    start = QPointF(50, 50)
    end = QPointF(150, 90)   # dx=100, dy=40 — shift 없으면 정사각형이 아님
    view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, start, L))
    view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, end, L, SHIFT))
    view.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, end, NB, SHIFT))

    items = [it for it in w._scene.items() if isinstance(it, _SymbolItem)]
    assert len(items) == 1
    r = items[0].rect()
    assert abs(r.width() - r.height()) < 1e-6


