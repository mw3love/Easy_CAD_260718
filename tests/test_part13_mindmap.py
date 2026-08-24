"""Tab/Enter 마인드맵 뻗기 — 백엔드(host_mindmap.py) 단독 검증. 키보드 배선(실제 Tab/
Enter 키 입력) 테스트는 Task 2에서 이 파일 하단에 추가된다.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest tests/test_part13_mindmap.py.
"""
from PyQt6.QtCore import Qt, QRectF, QPointF

from _shared import *  # noqa: F401,F403


def _mm_rect(w, x, y, wd=120.0, ht=120.0):
    it = _RectItem(QRectF(0, 0, wd, ht))
    it.setPen(w.make_pen())
    it.setBrush(w.make_brush())
    it.setPos(x, y)
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def _mm_text(w, x, y, text="Hello"):
    """_TextItem 생성 헬퍼. 마인드맵 노드로 사용 가능."""
    it = _TextItem(w.current_color)
    it.apply_font_size(w.current_font_size)
    it.set_bg(w.current_text_bg)
    it.setPlainText(text)
    it.setPos(x, y)
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def test_mm_is_node_accepts_shapes_rejects_arrows():
    w = CanvasWindow()
    rect = _mm_rect(w, 0, 0)
    arrow = _mk_arrow(w, 0, 0, 10, 10)
    assert w.mm_is_node(rect) is True
    assert w.mm_is_node(arrow) is False


def test_mm_connect_then_children_and_parent_roundtrip():
    w = CanvasWindow()
    a = _mm_rect(w, 0, 0)
    b = _mm_rect(w, 300, 0)
    arr = w.mm_connect(a, b)
    assert arr in w._scene.items()
    assert w.mm_children(a) == [b]
    assert w.mm_parent(b) is a
    assert w.mm_parent(a) is None
    assert w.mm_children(b) == []


def test_mm_free_rect_avoids_existing_node():
    w = CanvasWindow()
    existing = _mm_rect(w, 0, 0)
    probe = QRectF(0, 0, 120, 120)
    free = w.mm_free_rect(probe, (0.0, 144.0))
    assert not existing.sceneBoundingRect().intersects(free)
    assert free.top() >= 120.0 - 1e-6


def test_mm_create_child_places_to_the_right_and_connects():
    w = CanvasWindow()
    parent = _mm_rect(w, 0, 0)
    child = w.mm_create_child(parent, w._view)
    assert child is not None
    assert w.mm_parent(child) is parent
    cr = child.mapRectToScene(child.rect())
    pr = parent.mapRectToScene(parent.rect())
    assert cr.left() >= pr.right()
    fi = w._scene.focusItem()
    assert fi is not None and fi.parentItem() is child  # 즉시 편집모드(라벨 포커스)


def test_mm_create_child_second_child_stacks_below_first_without_overlap():
    w = CanvasWindow()
    parent = _mm_rect(w, 0, 0)
    kid1 = w.mm_create_child(parent, w._view)
    kid1_rect = kid1.mapRectToScene(kid1.rect())
    kid2 = w.mm_create_child(parent, w._view)
    kid2_rect = kid2.mapRectToScene(kid2.rect())
    assert kid2_rect.top() >= kid1_rect.bottom()
    assert not kid1_rect.intersects(kid2_rect)


def test_mm_create_sibling_with_parent_becomes_another_child_of_same_parent():
    w = CanvasWindow()
    parent = _mm_rect(w, 0, 0)
    kid1 = w.mm_create_child(parent, w._view)
    kid2 = w.mm_create_sibling(kid1, w._view)
    assert kid2 is not None
    assert w.mm_parent(kid2) is parent
    assert set(w.mm_children(parent)) == {kid1, kid2}


def test_mm_create_sibling_without_parent_makes_orphan_below_no_arrow():
    w = CanvasWindow()
    root = _mm_rect(w, 0, 0)
    before_arrows = [it for it in w._scene.items()
                      if isinstance(it, (_ArrowItem, _PolyArrowItem))]
    sib = w.mm_create_sibling(root, w._view)
    assert sib is not None
    assert w.mm_parent(sib) is None
    root_rect = root.mapRectToScene(root.rect())
    sib_rect = sib.mapRectToScene(sib.rect())
    assert sib_rect.top() >= root_rect.bottom()
    after_arrows = [it for it in w._scene.items()
                     if isinstance(it, (_ArrowItem, _PolyArrowItem))]
    assert after_arrows == before_arrows  # 화살표가 새로 생기지 않았다


def test_mm_create_child_undo_removes_node_and_arrow_and_label():
    w = CanvasWindow()
    parent = _mm_rect(w, 0, 0)
    before = len(w._scene.items())
    w.mm_create_child(parent, w._view)
    assert len(w._scene.items()) > before
    w.undo()  # 라벨 생성 되돌리기(_begin_label_edit이 별도 push_undo_add(lbl)를 쌓음)
    w.undo()  # 노드+화살표 되돌리기(push_undo_add_many 1건)
    assert len(w._scene.items()) == before


def test_mm_create_child_on_non_node_item_is_noop():
    w = CanvasWindow()
    arrow = _mk_arrow(w, 0, 0, 10, 10)
    assert w.mm_create_child(arrow, w._view) is None


def test_mm_create_child_with_text_item_parent_no_crash():
    """_TextItem 부모에서 자식을 생성해도 crash하지 않고, 자식도 _TextItem이며 텍스트는 비어 있어야 한다.
    _TextItem.clone()이 원본 텍스트를 복사하는 문제 검증."""
    w = CanvasWindow()
    parent = _mm_text(w, 0, 0, text="Parent Text")
    child = w.mm_create_child(parent, w._view)
    assert child is not None
    assert isinstance(child, _TextItem)
    assert child.toPlainText() == ""  # clone이 복사한 텍스트를 clear했어야 함
    assert w.mm_parent(child) is parent
    fi = w._scene.focusItem()
    assert fi is child  # 즉시 편집모드(TextItem 자신이 focus)


def test_mm_create_sibling_with_text_item_orphan_no_crash():
    """_TextItem 고아에서 형제(또 다른 고아)를 생성해도 crash하지 않고, 형제도 _TextItem이며 텍스트는 비어 있어야 한다."""
    w = CanvasWindow()
    root = _mm_text(w, 0, 0, text="Root Text")
    sib = w.mm_create_sibling(root, w._view)
    assert sib is not None
    assert isinstance(sib, _TextItem)
    assert sib.toPlainText() == ""  # clone이 복사한 텍스트를 clear했어야 함
    assert w.mm_parent(sib) is None
    assert w.mm_parent(root) is None
    fi = w._scene.focusItem()
    assert fi is sib  # 즉시 편집모드(TextItem 자신이 focus)


# ---- Task 2: 키보드 배선 (Tab/Enter) 테스트 ----

from PyQt6.QtTest import QTest


def test_tab_key_on_selected_node_creates_child_and_focuses_new_label():
    w = CanvasWindow()
    w.set_tool("select")
    parent = _mm_rect(w, 0, 0)
    parent.setSelected(True)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)
    kids = w.mm_children(parent)
    assert len(kids) == 1
    fi = w._scene.focusItem()
    assert fi is not None and fi.parentItem() is kids[0]


def test_enter_key_while_editing_label_commits_text_and_creates_sibling():
    w = CanvasWindow()
    w.set_tool("select")
    parent = _mm_rect(w, 0, 0)
    kid = w.mm_create_child(parent, w._view)   # 이미 편집모드(라벨 포커스) 상태
    lbl = w._scene.focusItem()
    lbl.setPlainText("first")
    QTest.keyClick(w._view, Qt.Key.Key_Return)
    # mm_children()의 반환 순서는 QGraphicsScene.items()의 스태킹 순서를 따르므로(삽입
    # 순서와 같다는 보장이 없다) 인덱스가 아니라 원본 kid 객체 자체로 골라낸다.
    kids = w.mm_children(parent)
    assert len(kids) == 2
    assert kid in kids
    assert kid.has_label() and kid._label.toPlainText() == "first"
    new_fi = w._scene.focusItem()
    assert new_fi is not None
    sibling = new_fi.parentItem()
    assert sibling in kids and sibling is not kid


def test_shift_enter_while_editing_label_still_inserts_newline_not_mindmap():
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    w._view._begin_label_edit(node)
    lbl = w._scene.focusItem()
    QTest.keyClick(w._view, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert lbl.toPlainText() == "\n"
    assert w.mm_children(node) == []


def test_backtab_while_editing_does_not_create_node():
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    w._view._begin_label_edit(node)
    QTest.keyClick(w._view, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert w.mm_children(node) == []


def test_tab_with_multiple_selected_nodes_is_noop():
    w = CanvasWindow()
    w.set_tool("select")
    a = _mm_rect(w, 0, 0)
    b = _mm_rect(w, 300, 0)
    a.setSelected(True)
    b.setSelected(True)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)
    assert w.mm_children(a) == []
    assert w.mm_children(b) == []


def test_shift_enter_on_selected_node_does_not_create_sibling():
    """Regression test: Shift+Enter on selected node (not editing) should NOT create sibling.
    Must match behavior of Shift+Enter while editing (creates newline, not mindmap node)."""
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    node.setSelected(True)
    QTest.keyClick(w._view, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert w.mm_children(node) == []


def test_tab_key_on_standalone_text_item_branches_into_new_text_item():
    w = CanvasWindow()
    w.set_tool("select")
    txt = _TextItem(w.current_color)
    w._scene.addItem(txt)
    txt.setSelected(True)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)
    kids = w.mm_children(txt)
    assert len(kids) == 1
    assert isinstance(kids[0], _TextItem)


# ---- 최종 전체 브랜치 리뷰 수정 라운드(2026-08-24) — C1/I1/I2/I3 회귀 테스트 ----
#
# 대상 finding:
#   C1 — mm_children/mm_parent가 mm_is_node 필터 없이 화살표의 반대쪽을 그대로 돌려줘,
#        펜 궤적(_PathItem)·선(_LineItem)처럼 .rect()가 없는 이웃이 있으면 mm_create_child가
#        keyPressEvent(재구현된 Qt virtual) 안에서 AttributeError → PyQt6 qFatal() → 프로세스
#        전체 abort.
#   I1 — _ConnectorLabel(화살표를 따라 슬라이드하는 라벨)은 _TextItem 서브클래스라 mm_is_node가
#        잘못 True를 돌려줌 — 독립 노드가 아닌데 Tab으로 뻗을 수 있었다.
#   I2 — Ctrl+Enter(라벨 편집 종료 하위호환)·Ctrl+Tab(탭 전환)·Alt+Tab을 마인드맵이 가로챔.
#   I3 — Tab으로 만든 빈 _TextItem 노드를 Escape로 취소하면 _TextItem.focusOutEvent가 스스로
#        씬에서 제거하는데, mm_children/mm_parent가 그 유령 바인딩을 계속 돌려줌.

def _mk_line_item(w, x1, y1, x2, y2):
    """마인드맵 노드가 아닌(.rect() 없는) 화살표 바인딩 대상 — 선."""
    it = _LineItem(QLineF(x1, y1, x2, y2))
    it.setPen(w.make_pen())
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def _mk_path_item(w, x1, y1, x2, y2):
    """마인드맵 노드가 아닌(.rect() 없는) 화살표 바인딩 대상 — 펜 궤적류."""
    path = QPainterPath(QPointF(x1, y1))
    path.lineTo(QPointF(x2, y2))
    it = _PathItem(path)
    it.setPen(w.make_pen())
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def _bind_arrow(w, a, pa, b, pb):
    """a<->b 사이에 지속 연결(바인딩)된 화살표 하나를 만든다. `mm_connect`와 달리 a/b 중
    하나가 .rect()가 없는 비-노드 도형이어도 된다(C1이 재현하는 정확한 조건)."""
    sa = _PolyArrowItem(QColor("#ff0000ff"), 2, True)
    sa.set_points(pa, pb)
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, a.mapFromScene(pa))
    sa.set_bound(len(sa._pts) - 1, b, b.mapFromScene(pb))
    return sa


def test_mm_is_node_rejects_non_node_neighbor_types_table():
    """I1 + 표 형태 — 화살표가 합법적으로 붙을 수 있는 비-노드 도형 4종 전부 mm_is_node()가
    False여야 한다."""
    w = CanvasWindow()
    cases = {
        "_ArrowItem": _mk_arrow(w, 0, 0, 10, 10),
        "_LineItem": _mk_line_item(w, 0, 0, 10, 10),
        "_PathItem": _mk_path_item(w, 0, 0, 10, 10),
        "_ConnectorLabel": _ConnectorLabel(QColor("#111111")),
    }
    for name, item in cases.items():
        assert w.mm_is_node(item) is False, f"{name} should not be a mindmap node"


def test_c1_tab_with_non_node_arrow_neighbor_does_not_crash_table():
    """C1 회귀(핵심 재현) — 이미 비-노드 이웃(선/펜 궤적)과 화살표로 연결된 도형에서 Tab을
    눌러도(=mm_create_child 호출) crash하지 않고, 새 자식만 정상 생성되며 비-노드 이웃은
    mm_children()에 섞여 나오지 않아야 한다. 수정 전 코드에서는 mm_create_child가
    `mm_node_rect_scene(k).bottom()`에서 AttributeError를 던졌다(k = 비-노드 이웃)."""
    for label, make_neighbor in (
        ("_LineItem", lambda w: _mk_line_item(w, 400, 0, 460, 60)),
        ("_PathItem", lambda w: _mk_path_item(w, 400, 0, 460, 60)),
    ):
        w = CanvasWindow()
        w.set_tool("select")
        node = _mm_rect(w, 0, 0)
        neighbor = make_neighbor(w)
        p_node = node.mapToScene(node.rect().center())
        p_neighbor = neighbor.sceneBoundingRect().center()
        _bind_arrow(w, node, p_node, neighbor, p_neighbor)   # node -> neighbor (idx=0 쪽)
        node.setSelected(True)
        child = w.mm_create_child(node, w._view)   # 수정 전엔 여기서 AttributeError → qFatal
        assert child is not None, label
        kids = w.mm_children(node)
        assert neighbor not in kids, label
        assert child in kids, label
        assert len(kids) == 1, label


def test_mm_parent_filters_out_non_node_neighbor():
    """C1 회귀 — mm_parent도 동일하게 비-노드 이웃을 걸러야 한다(mm_children과 대칭)."""
    w = CanvasWindow()
    node = _mm_rect(w, 300, 0)
    neighbor = _mk_line_item(w, 0, 0, 60, 60)
    p_node = node.mapToScene(node.rect().center())
    p_neighbor = neighbor.sceneBoundingRect().center()
    _bind_arrow(w, neighbor, p_neighbor, node, p_node)   # neighbor -> node (idx!=0 쪽)
    assert w.mm_parent(node) is None


def test_i1_connector_label_selected_tab_creates_no_node():
    """I1 회귀(키보드 경로) — 화살표에 붙은 _ConnectorLabel을 선택하고 Tab을 눌러도 새
    노드가 생기면 안 된다(마인드맵 대상이 아님)."""
    w = CanvasWindow()
    w.set_tool("select")
    a = _mm_rect(w, 0, 0)
    b = _mm_rect(w, 300, 0)
    arr = w.mm_connect(a, b)
    lbl = arr.ensure_label()
    assert isinstance(lbl, _ConnectorLabel)
    before = len(w._scene.items())
    lbl.setSelected(True)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)
    assert len(w._scene.items()) == before


def test_i2_ctrl_enter_while_editing_finishes_without_creating_sibling():
    """I2 회귀 — Ctrl+Enter는 `_TextItem`의 하위호환 "편집 종료" 제스처로만 동작해야
    하고, 형제 노드를 만들면 안 된다. `node`는 루트라 `mm_create_sibling(node,...)`이
    (수정 전 코드 경로) 실행돼도 orphan 형제는 node의 부모/자식 그래프와 무관해
    `mm_children(node)`만 보면 통과해버린다 — 반드시 씬 아이템 개수(새 도형이 실제로
    생겼는지)로 검증해야 한다."""
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    w._view._begin_label_edit(node)
    lbl = w._scene.focusItem()
    lbl.setPlainText("keep")
    before = len(w._scene.items())
    QTest.keyClick(w._view, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert len(w._scene.items()) == before   # 새 형제 노드가 생기면 안 된다
    assert w.mm_children(node) == []
    assert lbl.toPlainText() == "keep"


def test_i2_ctrl_tab_does_not_create_child():
    """I2 회귀 — Ctrl+Tab(다음 문서 탭 전환 단축키)은 마인드맵 액션으로 해석되면 안
    된다. `event()`가 Ctrl 조합은 애초에 가로채지 않으므로(→ QTabWidget으로), 설령
    keyPressEvent까지 도달해도 모디파이어 가드가 다시 막는다(이중 방어 확인)."""
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    node.setSelected(True)
    before = len(w._scene.items())
    QTest.keyClick(w._view, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
    assert len(w._scene.items()) == before
    assert w.mm_children(node) == []


def test_i2_alt_tab_does_not_create_child():
    """I2 회귀 — Alt+Tab(OS 창 전환 제스처)도 마인드맵 액션이 되면 안 된다."""
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    node.setSelected(True)
    before = len(w._scene.items())
    QTest.keyClick(w._view, Qt.Key.Key_Tab, Qt.KeyboardModifier.AltModifier)
    assert len(w._scene.items()) == before
    assert w.mm_children(node) == []


def test_i3_tab_then_escape_on_empty_new_textitem_no_phantom_child():
    """I3 회귀 — Tab으로 만든 새 _TextItem 노드를 아무것도 안 쓰고 Escape로 취소하면
    (`_TextItem.focusOutEvent`가 빈 텍스트 노드를 스스로 씬에서 제거) mm_children()이
    그 유령 노드를 더 이상 돌려주면 안 된다.
    [오프스크린 한계] `QGraphicsItem.clearFocus()`가 실제 focusOutEvent를 내보내려면
    씬이 진짜 입력 포커스를 가져야 한다(단순히 `scene().focusItem()`으로 지정돼 있는 것과는
    별개) — `w.show()`+`activateWindow()`+뷰 `setFocus()`로 그 조건을 명시적으로 맞춘다
    (`test_part1_ui_arrows.py`의 클릭포커스 스핀박스 테스트와 동일 관례)."""
    w = CanvasWindow()
    w.show()
    w.activateWindow()
    QApplication.setActiveWindow(w)
    w.set_tool("select")
    root = _mm_text(w, 0, 0, text="Root")
    root.setSelected(True)
    w._view.setFocus(Qt.FocusReason.OtherFocusReason)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)   # 새 _TextItem 자식 생성, 편집모드 진입
    kids = w.mm_children(root)
    assert len(kids) == 1
    new_node = kids[0]
    fi = w._scene.focusItem()
    assert fi is new_node
    # 편집 중 Escape = 완료(빈 텍스트면 자기삭제, core_shapes.py _discard_if_empty 참조).
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _app.processEvents()
    _app.processEvents()
    assert new_node.scene() is None   # 실제로 씬에서 빠졌는지(전제 확인)
    assert w.mm_children(root) == []   # 유령 자식이 남으면 안 된다
