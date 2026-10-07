"""§8 항목26(2026-10-03) — 마인드맵: Tab/Enter로 막 만든 노드를 빈 채로 끝내면 노드+화살표+기록째 취소.
사용자 결정: 아무것도 안 친 것만 빈 것(공백만 쳤으면 남김) · 되돌리기 기록째 없앰 · Esc·클릭·Enter 등 모든 경로 ·
빈 새 노드에서 또 뻗으면 빈 노드는 지우고 원래 동작을 다시."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtTest import QTest

from _shared import *  # noqa: F401,F403


def _win():
    # 실제 focusOutEvent가 나오려면 씬이 진짜 입력 포커스를 가져야 한다(test_part13 I3 관례).
    w = CanvasWindow()
    w.show()
    w.activateWindow()
    QApplication.setActiveWindow(w)
    w.set_tool("select")
    w._view.setFocus(Qt.FocusReason.OtherFocusReason)
    return w


def _rect(w, x=0, y=0):
    it = _RectItem(QRectF(0, 0, 120, 60))
    it.setPen(w.make_pen())
    it.setPos(x, y)
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def _text(w, text="Root"):
    it = _TextItem(w.current_color)
    it.setPlainText(text)
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def _arrows(w):
    return [it for it in w._scene.items() if isinstance(it, (_ArrowItem, _PolyArrowItem))]


def _settle():
    for _ in range(3):
        _app.processEvents()


def _start(w, root, key=Qt.Key.Key_Tab):
    w._scene.clearSelection()
    root.setSelected(True)
    undo_before = len(w._undo)
    QTest.keyClick(w._view, key)
    return undo_before


def _close(w):
    w._active_doc.dirty = False
    w.close()


def test_tab_then_escape_on_shape_removes_node_arrow_and_history():
    w = _win()
    root = _rect(w)
    undo_before = _start(w, root)
    assert len(w.mm_children(root)) == 1 and len(_arrows(w)) == 1
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _settle()
    assert w.mm_children(root) == [] and _arrows(w) == []
    assert len(w._undo) == undo_before          # 만든 기록째 없어짐
    w.undo()                                    # Ctrl+Z로 빈 노드가 되살아나지 않음
    assert _arrows(w) == []
    _close(w)


def test_tab_then_escape_on_text_node_leaves_no_orphan_arrow():
    # 원래 증상: 글자 노드는 스스로 지워지고 화살표만 허공에 남았다.
    w = _win()
    root = _text(w)
    _start(w, root)
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _settle()
    assert _arrows(w) == []
    assert [it for it in w._scene.items() if isinstance(it, _TextItem)] == [root]
    _close(w)


def test_click_elsewhere_counts_as_cancel_too():
    w = _win()
    root = _rect(w)
    _start(w, root)
    w._scene.focusItem().clearFocus()           # 다른 곳 클릭 = 포커스가 빠짐
    _settle()
    assert w.mm_children(root) == [] and _arrows(w) == []
    _close(w)


def test_typed_text_keeps_node_and_normal_undo():
    w = _win()
    root = _rect(w)
    undo_before = _start(w, root)
    w._scene.focusItem().setPlainText("A")
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _settle()
    kids = w.mm_children(root)
    assert len(kids) == 1 and kids[0]._label.toPlainText() == "A"
    assert len(w._undo) > undo_before
    _close(w)


def test_typed_then_erased_counts_as_empty():
    w = _win()
    root = _rect(w)
    _start(w, root)
    lbl = w._scene.focusItem()
    lbl.setPlainText("A")
    lbl.setPlainText("")
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _settle()
    assert w.mm_children(root) == [] and _arrows(w) == []
    _close(w)


def test_whitespace_only_text_node_is_kept_with_its_arrow():
    # 사용자 결정: 공백만 친 것은 빈 것으로 보지 않는다(평소 빈 글자 정리에서 예외).
    w = _win()
    root = _text(w)
    _start(w, root)
    node = w._scene.focusItem()
    node.setPlainText("  ")
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _settle()
    assert node.scene() is not None and w.mm_children(root) == [node]
    assert len(_arrows(w)) == 1
    _close(w)


def test_tab_on_empty_new_node_redoes_from_original_parent():
    w = _win()
    root = _rect(w)
    undo_before = _start(w, root)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)     # 빈 채로 또 Tab
    _settle()
    kids = w.mm_children(root)
    assert len(kids) == 1 and len(_arrows(w)) == 1   # 빈 노드는 지워지고 새로 하나만
    fi = w._scene.focusItem()
    assert fi is not None and fi.parentItem() is kids[0]
    assert len(w._undo) == undo_before + 2      # 새 노드 1건 + 새 라벨 1건(옛 것은 없어짐)
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _settle()
    assert w.mm_children(root) == [] and len(w._undo) == undo_before
    _close(w)


def test_enter_on_root_without_parent_then_escape():
    w = _win()
    root = _rect(w)
    count = len(w._scene.items())
    _start(w, root, Qt.Key.Key_Return)          # 부모 없는 형제(화살표 없음)
    assert len(w._scene.items()) > count
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _settle()
    assert len(w._scene.items()) == count
    _close(w)


def test_chain_typed_then_empty_only_last_removed():
    w = _win()
    root = _rect(w)
    _start(w, root)
    w._scene.focusItem().setPlainText("A")
    QTest.keyClick(w._view, Qt.Key.Key_Return)  # A 확정 + 형제 생성(빈)
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    _settle()
    kids = w.mm_children(root)
    assert len(kids) == 1 and kids[0]._label.toPlainText() == "A"
    assert len(_arrows(w)) == 1
    _close(w)


def test_layer_count_updates_after_cancel():
    # 실제 창 확인 중 발견: 취소 뒤 레이어 패널이 「기본 (3)」으로 남아 있었다.
    w = _win()
    root = _rect(w)
    _start(w, root)
    import time
    end = time.time() + 0.4                     # 개수 재계산(0.15초 몰아서)이 Tab 뒤에 먼저 한 번 돌게
    while time.time() < end:
        _app.processEvents()
    QTest.keyClick(w._view, Qt.Key.Key_Escape)
    end = time.time() + 0.5
    while time.time() < end:
        _app.processEvents()
    texts = [w._layers_list.item(i).text() for i in range(w._layers_list.count())]
    widgets = [w._layers_list.itemWidget(w._layers_list.item(i)) for i in range(w._layers_list.count())]
    from PyQt6.QtWidgets import QLabel
    labels = [lb.text() for wd in widgets if wd is not None for lb in wd.findChildren(QLabel)]
    assert any(t in ("1", "(1)") or "(1)" in t for t in texts + labels), texts + labels   # 2026-10-07 개수 따로
    _close(w)
