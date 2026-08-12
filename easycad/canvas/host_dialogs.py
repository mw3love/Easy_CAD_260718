"""CanvasWindow이 띄우는 입력 다이얼로그 모음 — 용지 크기/표제란 필드/표 크기/
케이블 채번 접두사/Mermaid 붙여넣기.

2026-08-02 host.py(3635줄) 분할분. host_fileio.py·host_context.py 믹스인이 이 모듈에서
다이얼로그 클래스를 가져다 쓴다. 순환 임포트를 피하려고 host.py·믹스인을 임포트하지 않는
잎(leaf) 모듈이다.
"""
import io
import os

from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QSize, QSettings, QEvent, QBuffer, QIODevice, QByteArray,
)
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter, QImage,
    QFont, QPainterPath, QPalette, QTextCursor, QStandardItemModel, QStandardItem,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPlainTextEdit,
    QSizePolicy, QColorDialog, QHBoxLayout, QMenu, QFrame,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon, _svg_icon, _svg_icon_pixmap,
    _nearest_border,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
)
from easycad.canvas.host_widgets import _clipboard_pixmap, _act_icon
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES, render_preview, _find_title_frame
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document, load_document_layers
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)
from easycad.ai import gateway as gw


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


class _PdfExportDialog(QDialog):
    """[§8 항목14, 2026-08-07] PDF 내보내기 — 옛 "전체"/"선택영역" 별도 메뉴 2개를 이 다이얼로그
    하나로 통합. 전체/선택 라디오·용지크기·방향을 고르면 그 즉시 라이브 미리보기가 다시 렌더된다
    (deep-interview 확정 — 왕복 다이얼로그 대신 옵션·미리보기를 한 화면에). 씬에 표제란/용지틀이
    있고 "전체 도면"을 고른 상태면 그 프레임이 이미 용지 크기·방향을 정해둔 것이라 용지크기·방향
    컨트롤을 잠그고 프레임 값을 그대로 반영한다(프레임은 크롭 경계+출력 페이지 크기를 정하는
    것일 뿐 내부 도형의 실척 mm을 보장하지 않는다는 걸 사용자와 코드로 확인 후 결정 — 다른
    크기를 원하면 프레임 자체를 다시 만듦, 기존 UX와 일관)."""

    def __init__(self, parent, scene, has_selection: bool):
        super().__init__(parent)
        self.setWindowTitle("PDF 내보내기")
        self._scene = scene
        self._frame = _find_title_frame(scene)

        opts = QVBoxLayout()
        self._rb_all = QRadioButton("전체 도면")
        self._rb_sel = QRadioButton("선택 영역")
        self._rb_sel.setEnabled(has_selection)
        self._rb_all.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self._rb_all)
        grp.addButton(self._rb_sel)
        opts.addWidget(self._rb_all)
        opts.addWidget(self._rb_sel)

        form = QFormLayout()
        self._size_cb, self._orient_cb = _build_paper_combos(self, "A4", "landscape")
        form.addRow("용지 크기", self._size_cb)
        form.addRow("방향", self._orient_cb)
        opts.addLayout(form)
        self._frame_note = QLabel("표제란 용지 설정을 따름", self)
        self._frame_note.setVisible(False)
        opts.addWidget(self._frame_note)
        opts.addStretch(1)

        self._preview = QLabel(self)
        self._preview.setMinimumSize(320, 320)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setFrameShape(QFrame.Shape.StyledPanel)

        row = QHBoxLayout()
        row.addLayout(opts)
        row.addWidget(self._preview, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("PDF로 저장…")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(row)
        root.addWidget(btns)

        self._rb_all.toggled.connect(self._refresh)
        self._size_cb.currentIndexChanged.connect(self._refresh)
        self._orient_cb.currentIndexChanged.connect(self._refresh)
        self._refresh()

    def _selection_only(self) -> bool:
        return self._rb_sel.isChecked()

    def _frame_active(self) -> bool:
        return (not self._selection_only()) and self._frame is not None

    def _refresh(self):
        active = self._frame_active()
        self._size_cb.setEnabled(not active)
        self._orient_cb.setEnabled(not active)
        self._frame_note.setVisible(active)
        if active:
            idx = self._size_cb.findData(self._frame._size)
            if idx >= 0:
                self._size_cb.setCurrentIndex(idx)
            oidx = self._orient_cb.findData(self._frame._orient)
            if oidx >= 0:
                self._orient_cb.setCurrentIndex(oidx)
        pixmap = render_preview(
            self._scene, page=self._size_cb.currentData(),
            selection_only=self._selection_only(), orientation=self._orient_cb.currentData(),
        )
        if pixmap is None:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("출력할 내용이 없습니다.")
        else:
            self._preview.setText("")
            self._preview.setPixmap(pixmap)

    def result_options(self) -> dict:
        return {
            "selection_only": self._selection_only(),
            "page": self._size_cb.currentData(),
            "orientation": self._orient_cb.currentData(),
        }


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


class _CableNumberDialog(QDialog):
    """[신규기능] 케이블 번호 자동채번 — 접두사·시작번호를 고르는 작은 다이얼로그."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("케이블 번호 매기기")
        form = QFormLayout(self)
        self._prefix_le = QLineEdit("CABLE", self)
        self._start_sb = QSpinBox(self)
        self._start_sb.setRange(0, 99999)
        self._start_sb.setValue(1)
        form.addRow("접두사", self._prefix_le)
        form.addRow("시작번호", self._start_sb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result(self):
        prefix = self._prefix_le.text().strip() or "CABLE"
        return prefix, self._start_sb.value()




class _MermaidDialog(QDialog):
    """Mermaid flowchart 입력창 — 프롬프트(AI 지시)와 Mermaid 코드를 별개 칸으로 받는다.

    §8 항목18(AI 이미지→도면) 후속(2026-08-12) — 하루 사이 이 축을 두 번 오갔다: 처음엔
    2칸 → "AI가 편집 중인 내용을 덮어쓸 위험보다 한 칸이 편하다"는 피드백으로 1칸 →
    "텍스트 입력과 Mermaid 코드가 헷갈린다(둘 다 같은 칸이라 AI 버튼을 눌러야만 하는 게
    안 보임)"는 재피드백으로 다시 2칸으로 복귀. 이번엔 각 칸이 서로 다른 Enter 의미를
    가져 원래의 "덮어쓸 위험" 우려도 없다 — `_prompt_edit`(위, 짧음)는 Enter로 AI 생성을
    트리거하고 Shift+Enter만 줄바꿈(참고 이미지의 다른 AI 입력창 관례를 그대로 채용),
    `_edit`(아래, 넉넉함)는 평범한 멀티라인 코드 편집기라 Enter가 항상 줄바꿈이다 — 두
    칸의 역할이 다르므로 실수로 서로를 덮어쓸 상황 자체가 구조적으로 없다. `_edit`은
    AI 생성 결과가 채워지는 곳이자 동시에 사용자가 직접 타이핑·붙여넣기도 가능한 최종
    Mermaid 코드 칸(OK를 누르면 이 칸의 내용이 실제로 가져와진다, `text()` 참조) —
    "1번 칸 없이 바로 2번 칸에 Mermaid를 쓰는" 경로도 그대로 지원된다.

    이미지 입력도 받는다(찾아보기·드래그드롭·Ctrl+V, 옛 `_AIImageImportDialog`와 같은
    3경로). 이미지가 첨부되면 프롬프트 칸은 "보충 설명(선택)"으로 격하되고
    (`text_to_mermaid.generate_mermaid`의 `image` 인자), 좌표 없는 Mermaid 출력이라 옛
    파이프라인처럼 타일링·좌표 복원이 전혀 필요 없다 — 단일 vision 호출뿐.
    ⚠ 모델 목록은 텍스트 전용 목록(`list_text_models`)을 그대로 재사용한다 — 이
    게이트웨이에서 어떤 gpt/gemini 항목이 실제로 이미지 입력을 받는지는 실키로 확인 못
    했다(Not-tested, 실사용 중 특정 모델이 이미지를 거부하면 다른 모델로 바꿔 재시도).

    **디자인 3차 정리(2026-08-12)** — 다른 AI 입력창 참고 이미지를 기준으로 정리:
    설정 버튼은 우상단 단독으로, 안내문은 불릿 목록, 첨부는 "+" 아이콘, 모델은 추천
    배지 없는 평범한 드롭다운(gemini·gpt 그룹 헤더만 구분). 새로고침은 더 이상 이 창에
    없다 — "API 키를 만지는 곳(설정 창)에서 함께 해야 한다"는 지적으로
    `_AIGatewaySettingsDialog` 쪽으로 옮겼다(그쪽에서 gpt/gemini 개수와 크레딧까지 함께
    확인 가능)."""

    _SAMPLE = ("flowchart TD\n"
               "    A[시작] --> B{조건?}\n"
               "    B -->|예| C[처리]\n"
               "    B -->|아니오| D([종료])\n"
               "    C --> D")
    _HINT = ("• Enter — AI로 Mermaid 생성 (Shift+Enter는 줄바꿈)\n"
             "• 드래그·Ctrl+V — 이미지 첨부\n"
             "• 아래 칸에 Mermaid 코드를 직접 입력·붙여넣기도 가능")

    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid 가져오기")
        self.setAcceptDrops(True)
        self._attached_image = None       # PIL.Image.Image | None
        self._attached_image_name = ""
        lay = QVBoxLayout(self)

        # [2026-08-12 3차] 설정은 이 창의 어느 특정 행에 종속된 기능이 아니라 창 전체의
        # 환경설정이라 우상단 단독 배치(참고 이미지 관례).
        top_row = QHBoxLayout()
        top_row.addStretch(1)
        self._settings_btn = QToolButton(self)
        self._settings_btn.setIcon(_act_icon("settings"))
        self._settings_btn.setToolTip("AI 게이트웨이 설정(주소·키·모델 새로고침·크레딧 확인)")
        self._settings_btn.clicked.connect(self._open_gateway_settings)
        top_row.addWidget(self._settings_btn)
        lay.addLayout(top_row)

        hint = QLabel(self._HINT, self)
        hint.setStyleSheet("color:#8a8a8a;")
        lay.addWidget(hint)

        # ---- 1번 칸: AI 프롬프트(짧음) + 첨부("+") + AI 생성(코랄) ------------------
        prompt_row = QHBoxLayout()
        self._prompt_edit = QPlainTextEdit(self)
        self._prompt_edit.setPlaceholderText("예: 날씨를 예보하는 워크플로우")
        self._prompt_edit.setFixedHeight(64)
        self._prompt_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._prompt_edit.setAcceptDrops(False)   # 드롭을 이 다이얼로그(dropEvent)로 넘김
        self._prompt_edit.installEventFilter(self)   # Enter 생성·Ctrl+V 이미지 첨부
        prompt_row.addWidget(self._prompt_edit, 1)

        self._attach_btn = QToolButton(self)
        self._attach_btn.setText("+")   # [2026-08-12 3차] 클립 아이콘 → "+"(참고 이미지 관례)
        self._attach_btn.setToolTip("이미지 첨부(드래그드롭·Ctrl+V도 가능)")
        self._attach_btn.clicked.connect(self._browse_image)
        prompt_row.addWidget(self._attach_btn)

        self._ai_btn = QToolButton(self)
        # [self-review 2026-08-12] _svg_icon()만 쓰면 QIcon.Mode.Disabled 변형이 없어
        # setEnabled(False) 중에도(생성 진행 중) 아이콘이 그대로 진하게 남는다 — 실제
        # 창에서 활성/비활성 스크린샷을 비교해 발견(육안으로 구분 불가였음). 다른 상단바
        # 아이콘들이 쓰는 `_finish_act_icon`의 35% 알파 흐림 관례를 그대로 재현.
        gen_pm = _svg_icon_pixmap("generate", 20, QColor("#1b120d"))
        gen_icon = QIcon(gen_pm)
        gen_dim = QPixmap(gen_pm.size())
        gen_dim.fill(Qt.GlobalColor.transparent)
        _dp = QPainter(gen_dim)
        _dp.setOpacity(0.35)
        _dp.drawPixmap(0, 0, gen_pm)
        _dp.end()
        gen_icon.addPixmap(gen_dim, QIcon.Mode.Disabled, QIcon.State.Off)
        self._ai_btn.setIcon(gen_icon)
        self._ai_btn.setIconSize(QSize(18, 18))
        self._ai_btn.setToolTip("AI로 생성 (Enter)")
        self._ai_btn.clicked.connect(self._on_ai_clicked)
        self._ai_btn.setStyleSheet(
            "QToolButton { background: #da7756; border: none; border-radius: 7px; padding: 6px; }"
            "QToolButton:hover { background: #e08a6c; }"
            "QToolButton:pressed { background: #c2673f; }"
            "QToolButton:disabled { background: #6b5148; }"   # 채도 낮춘 비활성 코랄
        )
        prompt_row.addWidget(self._ai_btn)
        lay.addLayout(prompt_row)

        image_row = QHBoxLayout()
        self._image_thumb = QLabel(self)
        self._image_thumb.setFixedSize(40, 40)
        self._image_thumb.setScaledContents(True)
        image_row.addWidget(self._image_thumb)
        self._image_name_label = QLabel("", self)
        image_row.addWidget(self._image_name_label, 1)
        self._image_clear_btn = QToolButton(self)
        self._image_clear_btn.setText("✕")
        self._image_clear_btn.setToolTip("이미지 제거")
        self._image_clear_btn.clicked.connect(self._clear_image)
        image_row.addWidget(self._image_clear_btn)
        self._image_row_widget = QWidget(self)
        self._image_row_widget.setLayout(image_row)
        self._image_row_widget.setVisible(False)
        lay.addWidget(self._image_row_widget)

        # ---- 2번 칸: Mermaid 코드(넉넉함) — AI 결과가 채워지거나 직접 타이핑/붙여넣기 ----
        lay.addWidget(QLabel("Mermaid 코드:", self))
        self._edit = QPlainTextEdit(self)
        self._edit.setPlaceholderText(self._SAMPLE)
        self._edit.setMinimumSize(QSize(460, 260))
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self._edit)

        # ---- 모델 선택: 평범한 드롭다운(gemini/gpt 그룹 헤더, 추천 배지 없음) ----------
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("모델:", self))
        self._model_combo = QComboBox(self)
        model_row.addWidget(self._model_combo, 1)
        lay.addLayout(model_row)
        self._populate_models()

        self._credit_label = QLabel("", self)   # AI 생성 성공 후에만 채움(크레딧 잔액, 부가정보)
        lay.addWidget(self._credit_label)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def text(self):
        return self._edit.toPlainText()

    def eventFilter(self, obj, event):
        if obj is self._prompt_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False   # Shift+Enter는 기본 동작(줄바꿈)에 맡김
                self._on_ai_clicked()
                return True
            if event.matches(QKeySequence.StandardKey.Paste):
                md = QApplication.clipboard().mimeData()
                img = md.imageData() if md.hasImage() else None
                if isinstance(img, QImage) and not img.isNull():
                    self._set_attached_qimage(img, "붙여넣은 이미지")
                    return True
                # 클립보드에 이미지가 없으면(보통의 텍스트 붙여넣기) 위젯 기본 동작에 맡긴다.
        return super().eventFilter(obj, event)

    # ---- 이미지 첨부(찾아보기·드래그드롭·Ctrl+V) --------------------------------

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "이미지 선택", "", "이미지 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)")
        if path:
            self._load_image_path(path)

    def _load_image_path(self, path: str):
        from PIL import Image
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            QMessageBox.warning(self, "Mermaid 가져오기", f"이미지를 읽을 수 없습니다: {e}")
            return
        self._set_attached_image(img, os.path.basename(path))

    def _set_attached_qimage(self, qimg: QImage, name: str):
        """붙여넣기/드롭으로 받은 QImage → PIL Image 변환(임시파일 없이 메모리에서만
        처리 — 옛 `_AIImageImportDialog`의 temp 파일+정리 관례를 이번엔 안 씀)."""
        from PIL import Image
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")
        pil_img = Image.open(io.BytesIO(bytes(ba.data()))).convert("RGB")
        self._set_attached_image(pil_img, name)

    def _set_attached_image(self, pil_img, name: str):
        self._attached_image = pil_img
        self._attached_image_name = name
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        pm = QPixmap()
        pm.loadFromData(buf.getvalue())
        self._image_thumb.setPixmap(pm)
        self._image_name_label.setText(name)
        self._image_row_widget.setVisible(True)

    def _clear_image(self):
        self._attached_image = None
        self._attached_image_name = ""
        self._image_thumb.clear()
        self._image_row_widget.setVisible(False)

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasImage() or (md.hasUrls() and any(
                u.toLocalFile().lower().endswith(self._IMG_EXTS) for u in md.urls())):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            for u in md.urls():
                p = u.toLocalFile()
                if p.lower().endswith(self._IMG_EXTS):
                    self._load_image_path(p)
                    e.acceptProposedAction()
                    return
        if md.hasImage():
            img = md.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self._set_attached_qimage(img, "드롭한 이미지")
                e.acceptProposedAction()

    # ---- 모델 선택(드롭다운) ----------------------------------------------------

    def _open_gateway_settings(self):
        """`_AIGatewaySettingsDialog`(주소·키·모델 새로고침·크레딧 확인)를 이 Mermaid 창의
        자식 모달로 연다. 주소/키/모델 목록이 바뀌었을 수 있으니 닫힌 뒤 드롭다운을
        다시 채운다."""
        if _AIGatewaySettingsDialog(self).exec() == QDialog.DialogCode.Accepted:
            self._populate_models()

    def _populate_models(self):
        """게이트웨이 `/models`를 실호출해(옛 코드와 동일한 지점 — 별도 캐시 계층은 안 둔다,
        `_AIGatewaySettingsDialog`의 새로고침도 자기 몫의 확인용으로 독립 호출) gemini·gpt
        그룹 헤더가 있는 평범한 드롭다운으로 채운다. 추천 배지·설명은 뺐다(재피드백: "추천
        설명은 빼자") — 그룹 구분만 명확히 남긴다. 헤더 행은 `QStandardItem.setEnabled(False)`
        로 선택 불가. 조회 실패(키 없음·네트워크 오류) 시 추천 둘만으로 조용히 폴백."""
        models: list[str] = []
        try:
            key = gw.resolve_api_key()
            if key:
                models = gw.list_text_models(key, gw.resolve_base_url(), timeout=8.0)
        except Exception:
            models = []
        r1, r2 = gw.TEXT_RECOMMEND_1, gw.TEXT_RECOMMEND_2
        pool = sorted(set(models) | {r1, r2})
        gemini_models = sorted(m for m in pool if "gemini" in m.lower())
        gpt_models = sorted(m for m in pool if "gpt" in m.lower())

        std_model = QStandardItemModel(self._model_combo)

        def add_group(label, group_models):
            header = QStandardItem(label)
            header.setEnabled(False)
            f = header.font(); f.setBold(True); header.setFont(f)
            std_model.appendRow(header)
            for m in group_models:
                it = QStandardItem(m)
                it.setData(m, Qt.ItemDataRole.UserRole)
                std_model.appendRow(it)

        add_group("Gemini", gemini_models)
        add_group("GPT", gpt_models)
        self._model_combo.setModel(std_model)

        default_row = next(
            (i for i in range(std_model.rowCount())
             if std_model.item(i).data(Qt.ItemDataRole.UserRole) == r1), -1)
        self._model_combo.setCurrentIndex(default_row if default_row >= 0 else
                                          (1 if std_model.rowCount() > 1 else -1))

    def model(self) -> str:
        idx = self._model_combo.currentIndex()
        data = self._model_combo.itemData(idx, Qt.ItemDataRole.UserRole) if idx >= 0 else None
        return data or gw.TEXT_RECOMMEND_1

    def _on_ai_clicked(self):
        desc = self._prompt_edit.toPlainText().strip()
        image = self._attached_image
        if not desc and image is None:
            QMessageBox.information(self, "Mermaid 가져오기",
                                    "먼저 설명을 입력하거나 이미지를 첨부하세요.")
            return
        key = gw.resolve_api_key()
        if not key:
            QMessageBox.warning(self, "Mermaid 가져오기",
                                "게이트웨이 API 키가 없습니다. "
                                "우상단 설정 버튼에서 입력해 주세요.")
            return
        base_url = gw.resolve_base_url()
        self._ai_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from easycad.ai.text_to_mermaid import generate_mermaid
            text, used = generate_mermaid(key, desc, model=self.model(), base_url=base_url,
                                          image=image)
        except Exception as e:
            QMessageBox.warning(self, "Mermaid 가져오기", f"생성 실패: {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self._ai_btn.setEnabled(True)
        # [2칸 분리 후에도 유지] setPlainText()는 되돌리기 스택을 초기화해버려 이전에 손으로
        # 고친 코드를 잃는다 — QTextCursor 전체선택+치환은 `_edit`의 undo 스택에 남아
        # Ctrl+Z로 AI 생성 전 코드를 복구할 수 있다.
        cursor = self._edit.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        # [실사용 피드백 계승, §8 항목18 C단계] 크레딧 잔액 표시 — 실패해도 본 결과
        # (Mermaid 채우기)에는 영향 없어야 하므로 조용히 무시.
        try:
            remaining, quota = gw.get_credit_balance(key, base_url)
            self._credit_label.setText(f"{used} · 크레딧 잔여 {remaining:.0f}/{quota:.0f}")
        except Exception:
            self._credit_label.setText(used)


class _AIGatewaySettingsDialog(QDialog):
    """AI 게이트웨이 연결 설정 — 게이트웨이 주소·API 키 입력·저장에 더해 모델 목록
    새로고침·크레딧 확인까지 한곳에서(2026-08-12 3차, 재피드백 — "새로고침은 API 설정
    있는 쪽에서 해야 할 듯"·"크레딧 확인도 같이 하면 좋을듯", 참고 이미지의 Mindlogic
    Gateway 설정 패널 구성을 따름).

    이전엔 secrets 파일(`~/.claude/.secrets/easycad-gateway.key`)이나 환경변수로만 키를
    넣을 수 있어 앱만 켜서 쓰는 사용자에겐 진입장벽이었다. OK를 눌러야 QSettings에
    저장된다(Cancel은 변경 폐기) — `resolve_api_key`의 우선순위 사슬에서 QSettings는
    secrets 파일보다 아래이므로, secrets 파일이 이미 있으면 이 창에서 바꿔도 secrets
    파일 쪽이 계속 우선한다(의도된 동작 — 파일 관례가 더 안전한 소스).

    진입점은 `_MermaidDialog._open_gateway_settings`(우상단 설정 버튼, 2026-08-12 3차 —
    한때 CanvasWindow 상단 메뉴/툴바로 나갔다가 되돌아온 뒤 다시 자리를 옮긴 것) 하나뿐
    이지만, 클래스 자체는 어느 부모에서 열든 무관하게 재사용 가능."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 게이트웨이 설정")
        self.setMinimumWidth(420)   # 기본 주소 전문(50자)이 스크롤 없이 한눈에 보이게
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("게이트웨이 주소:"))
        self._url_edit = QLineEdit(self)
        self._url_edit.setText(gw.resolve_base_url())   # 저장값 없으면 gw.BASE_URL 기본값이 그대로 채워짐
        lay.addWidget(self._url_edit)

        lay.addWidget(QLabel("API 키:"))
        self._key_edit = QLineEdit(self)
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setText(gw.resolve_api_key())
        lay.addWidget(self._key_edit)

        # [2026-08-12 3차] 옛 "연결 테스트"(모델 개수만 확인)를 "모델 새로고침"으로
        # 확장 — `_MermaidDialog`의 드롭다운이 실제로 쓸 gpt/gemini 개수를 그대로 보여줘
        # 사용자가 요청한 "gpt N개, gemini N개 호출 성공" 형식을 만족시키면서, 별도
        # 새로고침 버튼을 두 곳에 중복으로 두지 않는다(연결 확인 겸용).
        refresh_row = QHBoxLayout()
        self._refresh_btn = QToolButton(self)
        self._refresh_btn.setIcon(_act_icon("refresh"))
        self._refresh_btn.setToolTip("모델 목록 새로고침(연결 확인 겸용)")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        refresh_row.addWidget(self._refresh_btn)
        self._refresh_label = QLabel("", self)
        refresh_row.addWidget(self._refresh_label, 1)
        lay.addLayout(refresh_row)

        credit_row = QHBoxLayout()
        self._credit_btn = QToolButton(self)
        self._credit_btn.setText("크레딧 확인")
        self._credit_btn.clicked.connect(self._on_credit_clicked)
        credit_row.addWidget(self._credit_btn)
        self._credit_label = QLabel("", self)
        credit_row.addWidget(self._credit_label, 1)
        lay.addLayout(credit_row)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def base_url(self) -> str:
        return self._url_edit.text().strip() or gw.BASE_URL

    def api_key(self) -> str:
        return self._key_edit.text().strip()

    def _on_refresh_clicked(self):
        key = self.api_key()
        if not key:
            self._refresh_label.setText("API 키를 입력하세요.")
            return
        self._refresh_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            models = gw.list_text_models(key, self.base_url(), timeout=10.0)
        except Exception as e:
            self._refresh_label.setText(f"실패: {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self._refresh_btn.setEnabled(True)
        n_gpt = sum(1 for m in models if "gpt" in m.lower())
        n_gemini = sum(1 for m in models if "gemini" in m.lower())
        self._refresh_label.setText(f"gpt {n_gpt}개, gemini {n_gemini}개 호출 성공")

    def _on_credit_clicked(self):
        key = self.api_key()
        if not key:
            self._credit_label.setText("API 키를 입력하세요.")
            return
        self._credit_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            remaining, quota = gw.get_credit_balance(key, self.base_url())
        except Exception as e:
            self._credit_label.setText(f"크레딧 확인 실패: {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self._credit_btn.setEnabled(True)
        self._credit_label.setText(f"✓ 크레딧 {remaining:.0f}/{quota:.0f} 사용")

    def _on_accept(self):
        gw.store_base_url(self.base_url())
        gw.store_api_key(self.api_key())
        self.accept()

