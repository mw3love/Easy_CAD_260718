"""CanvasWindow이 띄우는 입력 다이얼로그 모음 — 용지 크기/표제란 필드/표 크기/
케이블 채번 접두사/Mermaid 붙여넣기.

2026-08-02 host.py(3635줄) 분할분. host_fileio.py·host_context.py 믹스인이 이 모듈에서
다이얼로그 클래스를 가져다 쓴다. 순환 임포트를 피하려고 host.py·믹스인을 임포트하지 않는
잎(leaf) 모듈이다.
"""
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QSize, QSettings, QTimer, QMimeData, QEvent
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter,
    QFont, QPolygonF, QPainterPath, QPalette, QDrag,
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
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon, _nearest_border,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES, render_preview, _find_title_frame
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document, load_document_layers
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)


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
    """Mermaid flowchart 코드를 붙여넣는 입력창(붙여넣기 다이얼로그 — deep-interview 확정)."""

    _SAMPLE = ("flowchart TD\n"
               "    A[시작] --> B{조건?}\n"
               "    B -->|예| C[처리]\n"
               "    B -->|아니오| D([종료])\n"
               "    C --> D")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid 가져오기")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Mermaid flowchart 코드를 붙여넣으세요 "
                             "(flowchart TD/LR … · 노드 모양·화살표·라벨 지원):"))
        self._edit = QPlainTextEdit(self)
        self._edit.setPlaceholderText(self._SAMPLE)
        self._edit.setMinimumSize(QSize(460, 280))
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self._edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def text(self):
        return self._edit.toPlainText()


# ---------------------------------------------------------------------------
# [§8 항목18 C단계] AI 이미지→도면 입력창 — 이미지 파일 + 보충설명 텍스트.
# ---------------------------------------------------------------------------
class _AIImageImportDialog(QDialog):
    """이미지 파일 선택 + 보충설명(도면 종류 등) 입력. 확인 버튼은 이미지를 고르기 전엔
    비활성 — 파이프라인은 몇 분 걸리므로 빈 경로로 시작해 사용자를 헷갈리게 하지 않는다."""

    _IMAGE_FILTER = "이미지 (*.png *.jpg *.jpeg *.bmp *.webp)"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 이미지→도면")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("도면 이미지를 골라주세요 — 편집 가능한 도형으로 변환합니다:"))

        row = QHBoxLayout()
        self._path_edit = QLineEdit(self)
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("이미지 파일을 선택하세요…")
        row.addWidget(self._path_edit)
        browse = QToolButton(self)
        browse.setText("찾아보기…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        lay.addLayout(row)

        lay.addWidget(QLabel("보충설명(도면 종류 등, 생략 가능):"))
        self._note_edit = QPlainTextEdit(self)
        self._note_edit.setPlaceholderText("예: 방송 송신소 계통도, 굵은 실선만 실제 연결선")
        self._note_edit.setMaximumHeight(70)
        lay.addWidget(self._note_edit)

        lay.addWidget(QLabel("⚠ 밀집 도면은 여러 번 나눠 인식해 수 분 걸릴 수 있습니다."))

        self._btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                      | QDialogButtonBox.StandardButton.Cancel, self)
        self._btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        lay.addWidget(self._btns)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "이미지 선택", "", self._IMAGE_FILTER)
        if path:
            self._path_edit.setText(path)
            self._btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def image_path(self) -> str:
        return self._path_edit.text()

    def note(self) -> str:
        return self._note_edit.toPlainText().strip()


class _AISketchProgressDialog(QDialog):
    """AI 이미지→도면 처리 중 진행 로그만 보여주는 모달. 닫기(X) 버튼을 없앴다 —
    진행 중인 게이트웨이 호출을 안전하게 중단할 방법이 없어 취소는 이번 라운드
    스코프 밖(`host_ai.py` 참조), 닫기를 허용하면 "취소됐다"는 착각을 줄 수 있다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 이미지→도면 — 처리 중")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("도면을 분석하는 중입니다 — 밀집 도면은 수 분 걸릴 수 있습니다."))
        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMinimumSize(QSize(440, 220))
        lay.addWidget(self._log)

    def append(self, msg: str):
        self._log.appendPlainText(msg)
