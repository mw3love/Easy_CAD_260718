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
from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter,
)
from PyQt6.QtWidgets import (
    QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QHBoxLayout, QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QDockWidget, QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QCheckBox,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
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
        self.setAcceptDrops(True)   # [Phase 4] 이미지 파일 드래그앤드롭 삽입

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_toolbar())
        lay.addWidget(self._view, 1)
        self.setCentralWidget(central)
        self._build_menu()
        self._build_shapes_dock()
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

        a_dxf = QAction("DXF 내보내기…", self)      # Phase 3 — CAD 상호운용
        a_dxf.setShortcut(QKeySequence("Ctrl+Shift+D"))
        a_dxf.triggered.connect(self._export_dxf)
        m.addAction(a_dxf)

        a_dxf_in = QAction("DXF 가져오기…", self)    # Phase 3 후반 — 역방향
        a_dxf_in.setShortcut(QKeySequence("Ctrl+Shift+I"))
        a_dxf_in.triggered.connect(self._import_dxf)
        m.addAction(a_dxf_in)

        m.addSeparator()

        a_img = QAction("이미지 삽입…", self)          # Phase 4 — PNG/JPG 삽입
        a_img.setShortcut(QKeySequence("Ctrl+Shift+M"))
        a_img.triggered.connect(self._insert_image)
        m.addAction(a_img)

        a_tb = QAction("표제란 / 용지틀 삽입…", self)     # Phase 4 — title block / paper frame
        a_tb.setShortcut(QKeySequence("Ctrl+Shift+T"))
        a_tb.triggered.connect(self._insert_titleblock)
        m.addAction(a_tb)

        a_tbl = QAction("표 삽입…", self)                  # Phase 4 — NxM 균등 격자 표
        a_tbl.setShortcut(QKeySequence("Ctrl+Shift+B"))
        a_tbl.triggered.connect(self._insert_table)
        m.addAction(a_tbl)

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

    def _export_dxf(self):
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "DXF 내보내기", "출력할 객체가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "DXF로 저장", "", "DXF 파일 (*.dxf)")
        if not path:
            return
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        try:
            export_dxf(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DXF 내보내기", f"저장에 실패했습니다:\n{e}")
            return
        QMessageBox.information(self, "DXF 내보내기", f"저장 완료:\n{path}")

    def _import_dxf(self):
        # 현재 씬을 대체하는 '열기' 시맨틱(import_dxf clear=True 기본).
        path, _ = QFileDialog.getOpenFileName(self, "DXF 가져오기", "", "DXF 파일 (*.dxf)")
        if not path:
            return
        try:
            n = import_dxf(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DXF 가져오기", f"가져오기에 실패했습니다:\n{e}")
            return
        self._undo.clear()
        nums = [it._number for it in self._scene.items() if hasattr(it, "_number")]
        self._badge_n = max(nums) if nums else 0
        self.statusBar().showMessage(f"가져오기 완료: {n}개 객체 — {path}", 5000)

    # ---- 이미지 삽입 (Phase 4) ---------------------------------------------
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
    _IMG_LONG = 400.0   # 삽입 시 긴 변 기본 크기(씬 단위) — 대형 사진이 캔버스를 뒤덮지 않게

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "이미지 삽입", "", "이미지 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not path:
            return
        center = self._view.mapToScene(self._view.viewport().rect().center())
        self._insert_image_at(path, center)

    def _insert_image_at(self, path: str, scene_pos: QPointF):
        """path의 이미지를 scene_pos를 중심으로 삽입(긴 변 _IMG_LONG로 축소, 종횡비 유지)."""
        pm = QPixmap(path)
        if pm.isNull():
            QMessageBox.warning(self, "이미지 삽입", f"이미지를 열 수 없습니다:\n{path}")
            return
        w, h = pm.width(), pm.height()
        s = min(1.0, self._IMG_LONG / max(w, h)) if max(w, h) > 0 else 1.0
        W, H = w * s, h * s
        item = _ImageItem(pm, QRectF(0.0, 0.0, W, H))
        item.setPos(scene_pos.x() - W / 2.0, scene_pos.y() - H / 2.0)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(f"이미지 삽입: {w}×{h}px — {path}", 4000)

    # 파일 탐색기에서 이미지를 캔버스로 끌어다 놓기 — QMainWindow가 드롭을 받는다(코어 뷰 무수정).
    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasUrls() and any(u.toLocalFile().lower().endswith(self._IMG_EXTS)
                                for u in md.urls()):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        if not md.hasUrls():
            return
        view_pt = self._view.mapFrom(self, e.position().toPoint())
        scene_pos = self._view.mapToScene(view_pt)
        n = 0
        for u in md.urls():
            p = u.toLocalFile()
            if p.lower().endswith(self._IMG_EXTS):
                self._insert_image_at(p, scene_pos)
                scene_pos = QPointF(scene_pos.x() + 20.0, scene_pos.y() + 20.0)
                n += 1
        if n:
            e.acceptProposedAction()

    # ---- 표제란 / 용지틀 (Phase 4) ------------------------------------------
    def _insert_titleblock(self):
        """용지 크기·방향을 고르고 표제란 프레임을 삽입. 프레임은 뷰 중앙 근처에 좌상단 배치."""
        existing = self._find_titleblock()
        if existing is not None:
            QMessageBox.information(
                self, "표제란", "이미 표제란/용지틀이 있습니다.\n"
                "더블클릭해 내용을 편집하거나, 지운 뒤 다시 삽입하세요.")
            self._scene.clearSelection()
            existing.setSelected(True)
            return
        dlg = _PaperSizeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        size, orient = dlg.result_size_orient()
        item = _TitleBlockItem(size, orient)
        w, h = item.paper_wh()
        center = self._view.mapToScene(self._view.viewport().rect().center())
        item.setPos(center.x() - w / 2.0, center.y() - h / 2.0)
        item.setZValue(-1000.0)   # 용지는 그린 도형들 뒤에(시트처럼)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(
            f"표제란/용지틀 삽입: {size} {orient} — 더블클릭해 필드 입력", 5000)

    def _edit_titleblock(self, item):
        """표제란 더블클릭 → 필드 편집 폼(용지 크기·방향 포함)."""
        dlg = _TitleBlockDialog(self, item)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        size, orient = dlg.result_size_orient()
        item.set_paper(size, orient)
        item.set_fields(dlg.result_fields())
        self.statusBar().showMessage("표제란 갱신됨", 3000)

    def _find_titleblock(self):
        for it in self._scene.items():
            if isinstance(it, _TitleBlockItem):
                return it
        return None

    # ---- 표(table) 삽입 (Phase 4) -------------------------------------------
    _CELL_W, _CELL_H = 40.0, 14.0   # 삽입 시 셀 기본 치수(mm 월드좌표)

    def _insert_table(self):
        """행·열 개수를 고르고 균등 격자 표를 삽입(뷰 중앙에 배치). 셀은 더블클릭해 인라인 편집."""
        dlg = _TableSizeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rows, cols, header = dlg.result()
        W, H = cols * self._CELL_W, rows * self._CELL_H
        item = _TableItem(rows, cols, QRectF(0.0, 0.0, W, H), header=header)
        center = self._view.mapToScene(self._view.viewport().rect().center())
        item.setPos(center.x() - W / 2.0, center.y() - H / 2.0)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(
            f"표 삽입: {rows}×{cols} — 셀 더블클릭해 편집(Enter/Tab 이동)", 5000)

    # ---- 툴바 (최소) --------------------------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(4)
        self._tool_buttons: dict[str, QToolButton] = {}
        for key, name, sc in _TOOLS:
            # 네모·원(닫힌 도형)은 왼쪽 「도형」 팔레트로 이동 — 상단은 그리기 도구만(정리).
            # 단축키(2·5)는 팔레트 버튼과 무관하게 계속 동작.
            if key in ("rect", "ellipse"):
                continue
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

    # ---- 도형 팔레트 (좌측 dock) — 기본(네모·원) + 순서도(심볼 6종) -----------
    @staticmethod
    def _shape_icon(kind: str, px: int = 30) -> QIcon:
        """팔레트 아이콘 — 캔버스 도형과 같은 모양으로 그린다. 심볼은 경로 팩토리,
        기본 도형(rect/ellipse)은 직접."""
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#333333")); pen.setWidthF(1.6)
        p.setPen(pen); p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        m = 4
        r = QRectF(m, m, px - 2 * m, px - 2 * m)
        if kind == "rect":
            p.drawRect(r)
        elif kind == "ellipse":
            p.drawEllipse(r)
        else:
            p.drawPath(_SYMBOL_KINDS[kind][1](r))
        p.end()
        return QIcon(pm)

    def _palette_button(self, label: str, icon_kind: str, tooltip: str, tool_key: str) -> QToolButton:
        btn = QToolButton()
        btn.setText(label)
        btn.setIcon(self._shape_icon(icon_kind))
        btn.setIconSize(QSize(30, 30))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setMinimumSize(QSize(64, 56))
        btn.clicked.connect(
            lambda _c=False, k=tool_key: self.set_tool(None if self.current_tool == k else k))
        return btn

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#888; font-size:11px; padding:3px 2px 1px 2px;")
        return lbl

    def _build_shapes_dock(self):
        dock = QDockWidget("도형", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        # 기본 도형(네모·원) — 상단 툴바에서 이관.
        vbox.addWidget(self._section_label("기본"))
        basic_grid = QGridLayout()
        basic_grid.setSpacing(4)
        self._shape_tool_buttons: dict[str, QToolButton] = {}
        for i, (key, label) in enumerate((("rect", "네모"), ("ellipse", "원"))):
            btn = self._palette_button(label, key, f"{label} — 클릭 후 캔버스에 드래그", key)
            basic_grid.addWidget(btn, i // 2, i % 2)
            self._shape_tool_buttons[key] = btn
        vbox.addLayout(basic_grid)

        # 순서도 심볼 6종.
        vbox.addWidget(self._section_label("순서도"))
        sym_grid = QGridLayout()
        sym_grid.setSpacing(4)
        self._sym_buttons: dict[str, QToolButton] = {}
        for i, (kind, (label, _fn)) in enumerate(_SYMBOL_KINDS.items()):
            btn = self._palette_button(label, kind, f"{label} 심볼 — 클릭 후 캔버스에 드래그",
                                       f"sym:{kind}")
            sym_grid.addWidget(btn, i // 2, i % 2)
            self._sym_buttons[kind] = btn
        vbox.addLayout(sym_grid)

        vbox.addStretch(1)
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    # ---- 지속 연결 리라우트 -------------------------------------------------
    def _on_scene_changed(self, region):
        if self._rerouting:
            return  # 재진입 가드 — reroute가 유발한 changed로 되돌아오지 않게
        if getattr(self._view, "_drawing", False):
            return  # 화살표 그리는 중엔 _update_arrow_draw가 tip을 주도 — 간섭 방지
        if getattr(self._view, "_place", None) is not None:
            return  # 클릭 배치 중엔 배치 로직이 끝점을 주도 — 간섭 방지
        self._rerouting = True
        try:
            for it in self._scene.items():
                # 곡선화살표(_ArrowItem)·직선화살표(_PolyArrowItem) 모두 지속 연결 리라우트.
                if isinstance(it, (_ArrowItem, _PolyArrowItem)) and it.has_binding():
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
        # 도구를 바꾸면 진행 중이던 클릭 배치는 폐기(반쯤 그린 도형이 남지 않게).
        view = getattr(self, "_view", None)
        if view is not None:
            view._cancel_place()
        self.current_tool = key
        for k, b in self._tool_buttons.items():
            b.setChecked(k == key)
        # 왼쪽 「도형」 팔레트 버튼 동기화: 기본(네모·원)은 key 직접, 심볼은 sym:kind.
        for k, b in getattr(self, "_shape_tool_buttons", {}).items():
            b.setChecked(k == key)
        for k, b in getattr(self, "_sym_buttons", {}).items():
            b.setChecked(f"sym:{k}" == key)

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

    def push_undo_add_many(self, items):
        """[2d] 여러 아이템(복제 도형+연결 화살표)을 한 번의 undo로 함께 제거."""
        self._undo.append(("add", list(items)))

    def push_undo_delete(self, items):
        self._undo.append(("delete", list(items)))

    def push_undo_move(self, pairs, coalesce_key=None):
        self._undo.append(("move", [(it, QPointF(old)) for it, old in pairs]))

    def push_undo_xform(self, snaps):
        """[우리 확장] 그룹 변형(회전·스케일) 되돌리기 — 변형 전 pos/rotation/scale/origin 스냅샷.
        push_undo_move가 위치만 복원하는 것과 달리 회전·스케일까지 통째로 되돌린다."""
        self._undo.append(("xform", [
            (it, QPointF(pos), rot, scale, QPointF(org)) for it, pos, rot, scale, org in snaps]))

    def push_undo_geom(self, snaps):
        """[Stage2] 기하 리베이크(비균일 스케일·미러) 되돌리기 — capture_geom 토큰 스냅샷.
        xform과 달리 기하 자체(rect/끝점/정점/패스)+바인딩까지 통째로 복원한다."""
        self._undo.append(("geom", list(snaps)))

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
        elif kind == "xform":
            for it, pos, rot, scale, org in payload:
                it.setTransformOriginPoint(org)
                it.setRotation(rot)
                it.setScale(scale)
                it.setPos(pos)
        elif kind == "geom":
            # [Stage2] 기하+바인딩 통째 복원. 도형·바인딩 화살표를 모두 스냅샷에 담았으므로
            # apply_geom만으로 일관 복원된다(reroute 불필요).
            for it, tok in payload:
                it.apply_geom(tok)

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


# ---------------------------------------------------------------------------
# [Phase 4] 표제란 다이얼로그 — 삽입 시 용지 선택 / 더블클릭 시 필드 편집
# ---------------------------------------------------------------------------
_ORIENTS = [("landscape", "가로"), ("portrait", "세로")]


def _build_paper_combos(dlg, size: str, orient: str):
    """용지 크기·방향 콤보 2개를 만들어 (size_combo, orient_combo)로 반환."""
    size_cb = QComboBox(dlg)
    for k in PAPER_SIZES_MM:
        size_cb.addItem(k, k)
    idx = size_cb.findData(size)
    size_cb.setCurrentIndex(idx if idx >= 0 else 0)
    orient_cb = QComboBox(dlg)
    for key, label in _ORIENTS:
        orient_cb.addItem(label, key)
    oidx = orient_cb.findData(orient)
    orient_cb.setCurrentIndex(oidx if oidx >= 0 else 0)
    return size_cb, orient_cb


class _PaperSizeDialog(QDialog):
    """표제란 삽입 시 용지 크기·방향만 고르는 작은 다이얼로그."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("용지 선택")
        form = QFormLayout(self)
        self._size_cb, self._orient_cb = _build_paper_combos(self, "A2", "landscape")
        form.addRow("용지 크기", self._size_cb)
        form.addRow("방향", self._orient_cb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result_size_orient(self):
        return self._size_cb.currentData(), self._orient_cb.currentData()


class _TitleBlockDialog(QDialog):
    """표제란 필드 편집 폼 + 용지 크기·방향 재선택."""

    def __init__(self, parent, item):
        super().__init__(parent)
        self.setWindowTitle("표제란 편집")
        form = QFormLayout(self)
        self._size_cb, self._orient_cb = _build_paper_combos(self, item._size, item._orient)
        form.addRow("용지 크기", self._size_cb)
        form.addRow("방향", self._orient_cb)
        self._edits = {}
        for key in TB_FIELD_KEYS:
            ed = QLineEdit(item._fields.get(key, ""), self)
            self._edits[key] = ed
            form.addRow(TB_FIELD_LABELS[key], ed)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result_size_orient(self):
        return self._size_cb.currentData(), self._orient_cb.currentData()

    def result_fields(self):
        return {k: ed.text() for k, ed in self._edits.items()}


class _TableSizeDialog(QDialog):
    """표 삽입 시 행·열 개수와 헤더 행 여부를 고르는 작은 다이얼로그."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("표 삽입")
        form = QFormLayout(self)
        self._rows_sb = QSpinBox(self)
        self._rows_sb.setRange(1, 100)
        self._rows_sb.setValue(3)
        self._cols_sb = QSpinBox(self)
        self._cols_sb.setRange(1, 50)
        self._cols_sb.setValue(3)
        self._header_cb = QCheckBox("첫 행을 헤더로(굵게)", self)
        self._header_cb.setChecked(True)
        form.addRow("행", self._rows_sb)
        form.addRow("열", self._cols_sb)
        form.addRow(self._header_cb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result(self):
        return self._rows_sb.value(), self._cols_sb.value(), self._header_cb.isChecked()
