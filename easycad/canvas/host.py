"""무한 캔버스 호스트 — pasteflow 편집기 코어(annotator_core)를 독립 앱으로 승격.

annotator_core의 _AnnotatorView·아이템 클래스는 그대로 재사용하고(스냅·베지어 UX 보존),
무거운 _EditorMixin(이미지 배경·스포이드·클립보드 아이콘 툴바) 대신 무한 캔버스에 맞는
얇은 owner + 최소 툴바를 새로 짠다.

owner가 _AnnotatorView에 제공해야 하는 인터페이스(뷰 소스에서 추출):
  속성: current_tool/color/width, arrow_head_at_end, current_font_size,
        current_text_bg, current_badge_size, _bg_item
  메서드: is_edit_mode/toggle_edit_mode/_on_escape/make_pen/set_tool/
          next_badge_number/adjust_item_property/_on_wheel_zoom/
          _win_drag_start/_win_drag_move/_win_drag_end/
          push_undo_add/push_undo_delete/push_undo_move/undo/
          copy_selection/paste_selection
"""
from PyQt6.QtCore import Qt, QPointF, QSize
from PyQt6.QtGui import QPen, QColor, QBrush, QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QHBoxLayout, QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES

# 무한 캔버스: 아주 큰 sceneRect로 사실상 무한한 팬 범위 제공.
_SCENE_HALF = 50000.0


class CanvasWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Easy CAD — Phase 0")
        self.resize(1200, 800)

        # ---- 편집 상태 (owner 인터페이스) ----
        self.current_tool = "select"
        self.current_color = QColor(_DEFAULT_COLOR)
        self.current_width = _DEFAULT_WIDTH
        self.current_font_size = _DEFAULT_FONT
        self.current_badge_size = _DEFAULT_BADGE
        self.current_text_bg = None
        self.arrow_head_at_end = True
        self._bg_item = None            # 배경 이미지 없음(무한 캔버스)
        self._badge_n = 0
        self._undo: list[tuple[str, list]] = []
        self._clip: list = []
        self._paste_seq = 0
        self._pan_last = None

        # ---- 씬 / 뷰 ----
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-_SCENE_HALF, -_SCENE_HALF, 2 * _SCENE_HALF, 2 * _SCENE_HALF)
        self._scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        self._view = _AnnotatorView(self._scene, self)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.centerOn(0, 0)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_toolbar())
        lay.addWidget(self._view, 1)
        self.setCentralWidget(central)
        self._build_menu()
        self.set_tool("select")

    # ---- 메뉴 (파일 → PDF 출력) --------------------------------------------
    def _build_menu(self):
        m = self.menuBar().addMenu("파일(&F)")
        a_full = QAction("PDF 내보내기 — 전체…", self)
        a_full.setShortcut(QKeySequence("Ctrl+P"))
        a_full.triggered.connect(lambda: self._export_pdf(selection_only=False))
        m.addAction(a_full)
        a_sel = QAction("PDF 내보내기 — 선택영역…", self)
        a_sel.setShortcut(QKeySequence("Ctrl+Shift+P"))
        a_sel.triggered.connect(lambda: self._export_pdf(selection_only=True))
        m.addAction(a_sel)

    def _export_pdf(self, selection_only: bool):
        if selection_only and not self._scene.selectedItems():
            QMessageBox.information(self, "PDF 내보내기", "선택된 객체가 없습니다.")
            return
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "PDF 내보내기", "출력할 객체가 없습니다.")
            return
        pages = list(PAGE_SIZES.keys())
        page, ok = QInputDialog.getItem(self, "용지 크기", "용지:", pages, 0, False)
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(self, "PDF로 저장", "", "PDF 파일 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if export_pdf(self._scene, path, page=page, selection_only=selection_only):
            QMessageBox.information(self, "PDF 내보내기", f"저장 완료:\n{path}")
        else:
            QMessageBox.warning(self, "PDF 내보내기", "저장에 실패했습니다.")

    # ---- 툴바 (최소) --------------------------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(4)
        self._tool_buttons: dict[str, QToolButton] = {}
        for key, name, sc in _TOOLS:
            btn = QToolButton()
            btn.setText(f"{name}")
            btn.setToolTip(f"{name} ({sc})")
            btn.setCheckable(True)
            btn.setMinimumSize(QSize(48, 28))
            btn.clicked.connect(
                lambda _c=False, k=key: self.set_tool(None if self.current_tool == k else k))
            h.addWidget(btn)
            self._tool_buttons[key] = btn
        h.addStretch(1)
        h.addWidget(QLabel("스크롤=줌 · 가운데버튼/손모드 드래그=이동 · Del=삭제 · Ctrl+Z=되돌리기"))
        return bar

    # ---- owner 인터페이스 ---------------------------------------------------
    def is_edit_mode(self) -> bool:
        return True

    def toggle_edit_mode(self):
        pass  # 단일 모드 앱 — 항상 편집

    def _on_escape(self):
        pass  # Phase 0: ESC로 앱 닫지 않음

    def make_pen(self) -> QPen:
        pen = QPen(QColor(self.current_color))
        pen.setWidthF(float(self.current_width))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def set_tool(self, key):
        self.current_tool = key
        for k, b in self._tool_buttons.items():
            b.setChecked(k == key)

    def next_badge_number(self) -> int:
        self._badge_n += 1
        return self._badge_n

    def adjust_item_property(self, item, step: int):
        if isinstance(item, _ArrowItem):
            item.apply_width(max(1, item._width + step))
        elif hasattr(item, "pen"):
            item.apply_width(max(1.0, item.pen().widthF() + step))

    # 줌 (커서 기준 — 뷰가 AnchorUnderMouse)
    def _on_wheel_zoom(self, dy: int):
        factor = 1.15 if dy > 0 else 1.0 / 1.15
        self._view.scale(factor, factor)

    # 팬 (창 이동 대신 캔버스 스크롤)
    def _win_drag_start(self, gpos):
        self._pan_last = gpos

    def _win_drag_move(self, gpos):
        if self._pan_last is None:
            return
        delta = gpos - self._pan_last
        self._pan_last = gpos
        hs, vs = self._view.horizontalScrollBar(), self._view.verticalScrollBar()
        hs.setValue(hs.value() - delta.x())
        vs.setValue(vs.value() - delta.y())

    def _win_drag_end(self):
        self._pan_last = None

    # 되돌리기 (간단 스택)
    def push_undo_add(self, item):
        self._undo.append(("add", [item]))

    def push_undo_delete(self, items):
        self._undo.append(("delete", list(items)))

    def push_undo_move(self, pairs, coalesce_key=None):
        self._undo.append(("move", [(it, QPointF(old)) for it, old in pairs]))

    def undo(self):
        if not self._undo:
            return
        kind, payload = self._undo.pop()
        if kind == "add":
            for it in payload:
                if it.scene() is not None:
                    self._scene.removeItem(it)
        elif kind == "delete":
            for it in payload:
                self._scene.addItem(it)
        elif kind == "move":
            for it, old in payload:
                it.setPos(old)

    # 복사 / 연속 붙여넣기
    def copy_selection(self):
        self._clip = [it.clone() for it in self._scene.selectedItems()
                      if hasattr(it, "clone")]
        self._paste_seq = 0

    def paste_selection(self):
        if not self._clip:
            return
        self._paste_seq += 1
        off = 20.0 * self._paste_seq
        self._scene.clearSelection()
        new_items = []
        for tmpl in self._clip:
            c = tmpl.clone()
            c.moveBy(off, off)
            self._scene.addItem(c)
            c.setSelected(True)
            new_items.append(c)
        if new_items:
            self._undo.append(("add", new_items))
