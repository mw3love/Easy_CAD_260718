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
    _AnnotatorView, _ArrowItem, _PolyArrowItem,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES
from easycad.fileio.document import save_document, load_document

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
        self.snap_enabled = True         # o-snap 토글(F3) — 도형 테두리 달라붙기 켜고 끄기
        self.ortho_enabled = False       # Ortho 토글(F8) — 그리기·정점드래그를 수평/수직(0/90°)로 제약
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
        # 지속 연결: 도형/화살표가 움직이면 바인딩된 화살표 끝을 재계산(scene.changed 트리거).
        self._rerouting = False
        self._scene.changed.connect(self._on_scene_changed)
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

    # ---- 메뉴 (파일 → 저장/열기/PDF) ----------------------------------------
    def _build_menu(self):
        self._doc_path = None
        m = self.menuBar().addMenu("파일(&F)")

        a_new = QAction("새로 만들기", self)
        a_new.setShortcut(QKeySequence.StandardKey.New)
        a_new.triggered.connect(self._new_doc)
        m.addAction(a_new)

        a_open = QAction("열기…", self)
        a_open.setShortcut(QKeySequence.StandardKey.Open)
        a_open.triggered.connect(self._open_doc)
        m.addAction(a_open)

        a_save = QAction("저장…", self)
        a_save.setShortcut(QKeySequence.StandardKey.Save)
        a_save.triggered.connect(self._save_doc)
        m.addAction(a_save)

        m.addSeparator()

        a_full = QAction("PDF 내보내기 — 전체…", self)
        a_full.setShortcut(QKeySequence("Ctrl+P"))
        a_full.triggered.connect(lambda: self._export_pdf(selection_only=False))
        m.addAction(a_full)
        a_sel = QAction("PDF 내보내기 — 선택영역…", self)
        a_sel.setShortcut(QKeySequence("Ctrl+Shift+P"))
        a_sel.triggered.connect(lambda: self._export_pdf(selection_only=True))
        m.addAction(a_sel)

        # ---- 보기 메뉴 (기준 zoom / 스냅 토글) ----
        v = self.menuBar().addMenu("보기(&V)")
        a_100 = QAction("100% (1:1)", self)
        a_100.setShortcut(QKeySequence("Ctrl+0"))
        a_100.triggered.connect(self._zoom_reset)
        v.addAction(a_100)
        a_fit = QAction("전체 맞춤", self)
        a_fit.setShortcut(QKeySequence("Ctrl+9"))
        a_fit.triggered.connect(self._zoom_fit)
        v.addAction(a_fit)
        v.addSeparator()
        self._act_snap = QAction("스냅 (o-snap)", self)
        self._act_snap.setCheckable(True)
        self._act_snap.setChecked(True)
        self._act_snap.setShortcut(QKeySequence("F3"))
        self._act_snap.triggered.connect(self._toggle_snap)
        v.addAction(self._act_snap)
        self._act_ortho = QAction("직교 제약 (Ortho)", self)
        self._act_ortho.setCheckable(True)
        self._act_ortho.setChecked(False)
        self._act_ortho.setShortcut(QKeySequence("F8"))
        self._act_ortho.triggered.connect(self._toggle_ortho)
        v.addAction(self._act_ortho)

    # ---- 보기: 기준 zoom / 스냅 -------------------------------------------
    def _zoom_reset(self):
        """기준 zoom = 100%(1:1). 무한캔버스에서 돌아올 홈."""
        self._view.resetTransform()

    def _zoom_fit(self):
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            self._view.resetTransform()
            return
        pad = max(rect.width(), rect.height()) * 0.05 + 20
        self._view.fitInView(rect.adjusted(-pad, -pad, pad, pad),
                             Qt.AspectRatioMode.KeepAspectRatio)

    def _toggle_snap(self, checked: bool):
        self.snap_enabled = checked
        self.statusBar().showMessage(
            "스냅 켜짐" if checked else "스냅 꺼짐 — 자유 배치", 3000)

    def _toggle_ortho(self, checked: bool):
        self.ortho_enabled = checked
        self.statusBar().showMessage(
            "Ortho 켜짐 — 수평/수직만" if checked else "Ortho 꺼짐 — 자유 각도", 3000)

    # ---- 저장 / 열기 --------------------------------------------------------
    _DOC_FILTER = "Easy CAD 문서 (*.ecad)"

    def _new_doc(self):
        self._scene.clear()
        self._undo.clear()
        self._clip.clear()
        self._badge_n = 0
        self._doc_path = None

    def _open_doc(self):
        path, _ = QFileDialog.getOpenFileName(self, "열기", "", self._DOC_FILTER)
        if not path:
            return
        try:
            n = load_document(self._scene, path)
        except Exception as e:  # noqa: BLE001 — 사용자에게 오류만 전달
            QMessageBox.warning(self, "열기 실패", str(e))
            return
        self._undo.clear()
        self._doc_path = path
        # 번호 마커 카운터를 로드된 최대값 뒤로 재설정
        nums = [it._number for it in self._scene.items() if hasattr(it, "_number")]
        self._badge_n = max(nums) if nums else 0
        self.statusBar().showMessage(f"열기 완료: {n}개 객체 — {path}", 5000)

    def _save_doc(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "저장", self._doc_path or "", self._DOC_FILTER)
        if not path:
            return
        if not path.lower().endswith(".ecad"):
            path += ".ecad"
        try:
            save_document(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "저장 실패", str(e))
            return
        self._doc_path = path
        self.statusBar().showMessage(f"저장 완료: {path}", 5000)

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
        h.addWidget(QLabel("휠=줌 · Shift+휠=두께/크기 · 가운데버튼 드래그=이동 · "
                           "Ctrl+0=100% · Ctrl+9=전체맞춤 · F3=스냅 · F8=직교 · Del=삭제 · Ctrl+Z=되돌리기"))
        return bar

    # ---- 지속 연결 리라우트 -------------------------------------------------
    def _on_scene_changed(self, region):
        if self._rerouting:
            return  # 재진입 가드 — reroute가 유발한 changed로 되돌아오지 않게
        if getattr(self._view, "_drawing", False):
            return  # 화살표 그리는 중엔 _update_arrow_draw가 tip을 주도 — 간섭 방지
        self._rerouting = True
        try:
            for it in self._scene.items():
                if isinstance(it, _ArrowItem) and it.has_binding():
                    it.reroute(pin_pred=self._make_pin_pred(it))
        finally:
            self._rerouting = False

    @staticmethod
    def _make_pin_pred(arrow):
        # 끝점 idx를 도형에 재고정할지: 붙은 도형과 화살표가 '같은 선택'으로 함께 움직이면
        # 강체(재고정 안 함), 아니면 붙은 채 늘림. → 사용자 합의 규칙.
        def pred(idx):
            sh = arrow._bound(idx)
            if sh is not None and arrow.isSelected() and sh.isSelected():
                return False
            return True
        return pred

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
        # 도구를 바꾸면 진행 중이던 sarrow 클릭-드로우는 폐기(반쯤 그린 폴리라인이 남지 않게).
        view = getattr(self, "_view", None)
        if view is not None:
            view._cancel_poly_draw()
        self.current_tool = key
        for k, b in self._tool_buttons.items():
            b.setChecked(k == key)

    def next_badge_number(self) -> int:
        self._badge_n += 1
        return self._badge_n

    def adjust_item_property(self, item, step: int):
        if isinstance(item, (_ArrowItem, _PolyArrowItem)):
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
