"""CanvasWindow이 띄우는 입력 다이얼로그 모음 — 용지 크기/표제란 필드/표 크기/
케이블 채번 접두사/Mermaid 붙여넣기.

2026-08-02 host.py(3635줄) 분할분. host_fileio.py·host_context.py 믹스인이 이 모듈에서
다이얼로그 클래스를 가져다 쓴다. 순환 임포트를 피하려고 host.py·믹스인을 임포트하지 않는
잎(leaf) 모듈이다.
"""
import io
import os
import time

from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QSize, QSettings, QEvent, QBuffer, QIODevice, QByteArray,
    QThread, pyqtSignal, QTimer,
)
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter, QImage,
    QFont, QPainterPath, QPalette, QTextCursor, QStandardItemModel, QStandardItem,
    QFontMetrics,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPlainTextEdit,
    QSizePolicy, QColorDialog, QHBoxLayout, QMenu, QFrame, QProgressBar,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup, QScrollArea,
)
from PyQt6.QtSvg import QSvgRenderer

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _TextItem, _tool_icon, _svg_icon,
    _svg_icon_pixmap, _nearest_border,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
)
from easycad.canvas.host_widgets import (
    _clipboard_pixmap, _act_icon, _ACCENT_CORAL, _ICON_COLOR,
    _MERMAID_SHAPE_ITEM, _border_attach,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES, render_preview, _list_title_frames
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document, load_document_layers
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)
from easycad.fileio.svg_import import parse_svg_string
from easycad.fileio import symbol_library
from easycad.ai import gateway as gw
from easycad.ai.text_to_svg import generate_svg


# ---------------------------------------------------------------------------
# [Phase 4] 표제란 다이얼로그 — 삽입 시 용지 선택 / 더블클릭 시 필드 편집
# ---------------------------------------------------------------------------
_ORIENTS = [("landscape", "가로"), ("portrait", "세로")]


_ROUNDED_COMBO_QSS = "QComboBox { border-radius:6px; }"


def _build_paper_combos(dlg, size: str, orient: str):
    """용지 크기·방향 콤보 2개를 만들어 (size_combo, orient_combo)로 반환.
    [2026-08-13 피드백] 각진 모서리 → 리프 위젯 각각에 개별 스타일시트(스핀박스가 없는
    폼이라 `docs/pitfalls.md`의 조상 스타일시트 함정과 무관, 위험 없음)."""
    size_cb = QComboBox(dlg)
    size_cb.setStyleSheet(_ROUNDED_COMBO_QSS)
    for k in PAPER_SIZES_MM:
        size_cb.addItem(k, k)
    idx = size_cb.findData(size)
    size_cb.setCurrentIndex(idx if idx >= 0 else 0)
    orient_cb = QComboBox(dlg)
    orient_cb.setStyleSheet(_ROUNDED_COMBO_QSS)
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


def _frame_label(frame, fallback_idx: int) -> str:
    """[다중 페이지 지원, 2026-08-14] PDF 프레임 드롭다운 표시 문구 — "도면번호 - 도면명"
    (deep-interview 확정). 한쪽만 있으면 있는 쪽만, 둘 다 비면 정렬 후 순번으로 폴백."""
    num = frame._fields.get("number", "").strip()
    title = frame._fields.get("title", "").strip()
    if num and title:
        return f"{num} - {title}"
    if num or title:
        return num or title
    return f"(이름 없음 #{fallback_idx})"


class _PdfExportDialog(QDialog):
    """[§8 항목14, 2026-08-07] PDF 내보내기 — 옛 "전체"/"선택영역" 별도 메뉴 2개를 이 다이얼로그
    하나로 통합. 전체/선택 라디오·용지크기·방향을 고르면 그 즉시 라이브 미리보기가 다시 렌더된다
    (deep-interview 확정 — 왕복 다이얼로그 대신 옵션·미리보기를 한 화면에). 씬에 표제란/용지틀이
    있고 "전체 도면"을 고른 상태면 그 프레임이 이미 용지 크기·방향을 정해둔 것이라 용지크기·방향
    컨트롤을 잠그고 프레임 값을 그대로 반영한다(프레임은 크롭 경계+출력 페이지 크기를 정하는
    것일 뿐 내부 도형의 실척 mm을 보장하지 않는다는 걸 사용자와 코드로 확인 후 결정 — 다른
    크기를 원하면 프레임 자체를 다시 만듦, 기존 UX와 일관).

    [다중 페이지 지원, 2026-08-14] 씬에 프레임이 2개 이상이면 "전체 도면" 옆에 드롭다운이
    자동으로 나타나 어느 프레임을 낼지 고른다(deep-interview 확정 — 새 라디오 옵션 대신
    기존 "전체 도면"의 자연스러운 확장). 프레임이 0~1개면 지금까지와 완전히 동일(드롭다운
    자체가 안 뜸, 무회귀)."""

    def __init__(self, parent, scene, has_selection: bool):
        super().__init__(parent)
        self.setWindowTitle("PDF 내보내기")
        self._scene = scene
        self._frames = _list_title_frames(scene)

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
        self._frame_cb = QComboBox(self)   # [다중 페이지] 프레임 2개 이상일 때만 보임(아래 _refresh)
        for i, fr in enumerate(self._frames):
            self._frame_cb.addItem(_frame_label(fr, i + 1), fr)
        self._frame_cb.setVisible(False)
        opts.addWidget(self._frame_cb)
        opts.addStretch(1)

        self._preview = QLabel(self)
        self._preview.setMinimumSize(320, 320)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # [2026-08-13 피드백] 각진 모서리 → 네이티브 `StyledPanel` 대신 다른 카드들과 같은
        # 6px 라운드 테두리를 직접 그림(리프 위젯 단독 스타일시트, 위험 없음).
        self._preview.setStyleSheet(
            "border:1px solid palette(mid); border-radius:6px;")

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
        self._frame_cb.currentIndexChanged.connect(self._refresh)   # [다중 페이지]
        self._refresh()

    def _selection_only(self) -> bool:
        return self._rb_sel.isChecked()

    def _current_frame(self):
        """[다중 페이지 지원, 2026-08-14] 프레임 0개=None, 1개=그것, 2개+=드롭다운이 고른 것."""
        if not self._frames:
            return None
        if len(self._frames) == 1:
            return self._frames[0]
        return self._frame_cb.currentData()

    def _frame_active(self) -> bool:
        return (not self._selection_only()) and self._current_frame() is not None

    def _refresh(self):
        frame = self._current_frame()
        active = (not self._selection_only()) and frame is not None
        self._size_cb.setEnabled(not active)
        self._orient_cb.setEnabled(not active)
        self._frame_note.setVisible(active)
        # [다중 페이지] 드롭다운은 "전체 도면"이고 프레임이 2개 이상일 때만 노출.
        self._frame_cb.setVisible(len(self._frames) >= 2 and not self._selection_only())
        if active:
            idx = self._size_cb.findData(frame._size)
            if idx >= 0:
                self._size_cb.setCurrentIndex(idx)
            oidx = self._orient_cb.findData(frame._orient)
            if oidx >= 0:
                self._orient_cb.setCurrentIndex(oidx)
        pixmap = render_preview(
            self._scene, page=self._size_cb.currentData(),
            selection_only=self._selection_only(), orientation=self._orient_cb.currentData(),
            frame=frame if not self._selection_only() else None,
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
            "frame": self._current_frame() if not self._selection_only() else None,
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




# [2026-08-13 5차] "AI로 생성" 버튼의 코랄 강조를 OK 버튼에도 그대로 씌운다(피드백: "OK버튼도
# AI로 생성처럼 코랄색으로") — QToolButton·QPushButton 선택자를 함께 둬 두 버튼이 같은
# 문자열을 공유한다(중복 리터럴 방지).
_CORAL_BTN_QSS = (
    "QToolButton, QPushButton { background: #da7756; border: none; border-radius: 7px; "
    "padding: 6px 12px; color: #1b120d; font-weight:600; }"
    "QToolButton:hover, QPushButton:hover { background: #e08a6c; }"
    "QToolButton:pressed, QPushButton:pressed { background: #c2673f; }"
    "QToolButton:disabled, QPushButton:disabled { background: #6b5148; }"   # 채도 낮춘 비활성 코랄
)


def _handdrawn_down_arrow_pixmap(color: QColor, w: int = 30, h: int = 46) -> QPixmap:
    """입력→코드 커넥터용 화살표(2026-08-13 5차, 피드백: "원 안 화살표는 시인성이 낮다,
    원 없이 화살표만 크게, 손글씨 느낌이면 좋겠다") — 완만한 S자 곡선 몸통 + 열린 쉐브런
    화살촉. `_svg_icon_pixmap`의 정사각 캔버스 전제와 안 맞아(세로가 긴 화살표) 그 파이프라인
    대신 `_arrow_dir_icon`과 같은 관례(one-off는 QPainter 직접 드로잉)를 따른다."""
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(color, 3.0, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    cx = w / 2
    top_y, head_y = 3.0, h - 13.0
    shaft = QPainterPath(QPointF(cx - 2, top_y))
    shaft.cubicTo(QPointF(cx + 6, top_y + (head_y - top_y) * 0.35),
                  QPointF(cx - 6, top_y + (head_y - top_y) * 0.65),
                  QPointF(cx + 1, head_y))
    p.drawPath(shaft)
    tip = QPointF(cx + 1, h - 3.0)
    p.drawLine(QPointF(cx - 8, head_y - 1), tip)
    p.drawLine(QPointF(cx + 10, head_y - 1), tip)
    p.end()
    return pm


class _GenProgressRow(QWidget):
    """AI 생성 중 진행 표시 — marquee(무한) 진행바 + 경과시간 텍스트. 게이트웨이가
    스트리밍 진행률을 안 주는 단발 호출이라 결정형(%) 대신 이 형태를 쓴다(2026-08-19
    deep-interview 확정). `_MermaidDialog`·`_SvgAssetDialog`가 공유."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)
        self._bar = QProgressBar(self)
        self._bar.setRange(0, 0)   # marquee
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        lay.addWidget(self._bar, 1)
        self._label = QLabel("", self)
        self._label.setStyleSheet("color:#8a8a8a; font-size:11px;")
        lay.addWidget(self._label)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._t0 = 0.0
        self._text = ""
        self.setVisible(False)

    def start(self, text: str):
        self._text = text
        self._t0 = time.monotonic()
        self._label.setText(f"{text}… 0초")
        self.setVisible(True)
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.setVisible(False)

    def _tick(self):
        elapsed = int(time.monotonic() - self._t0)
        self._label.setText(f"{self._text}… {elapsed}초")


class _ImageAttachMixin:
    """이미지 첨부(찾아보기·드래그드롭·Ctrl+V) 공용 로직 — 원래 `_MermaidDialog` 전용
    이었던 것을 2026-08-19 Stage 3(SVG 이미지 입력, deep-interview 확정 — "Mermaid와
    동일한 첨부 UI 재사용")에서 `_SvgAssetDialog`와 공유하도록 추출. 상태
    (`_attached_image`/`_attached_image_name`)와 로직만 여기 두고, 칩 UI 자체
    (`_build_image_chip`)는 만들어 돌려주되 어느 레이아웃에 넣을지는 호출부(각 다이얼로그
    의 툴바 구성)가 정한다 — 두 다이얼로그의 툴바 모양이 달라 위젯 트리 배치까지는 공유
    하지 않는다. `dragEnterEvent`/`dropEvent`는 다이얼로그 자신에 걸리는 이벤트라 이
    믹스인을 상속한 QDialog가 `setAcceptDrops(True)`만 해두면 그대로 작동한다."""

    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")

    def _init_image_attach_state(self):
        self._attached_image = None       # PIL.Image.Image | None
        self._attached_image_name = ""
        self._drop_frame = None           # QFrame | None — 드래그 오버 시 강조할 카드
        self._drop_frame_normal_qss = ""
        self._drop_frame_active_qss = ""

    def _set_image_drop_frame(self, frame, normal_qss: str, active_qss: str):
        """[2026-08-20 피드백: "드래그해도 되는 느낌이 없다"] 드래그 오버 중 강조할 카드
        위젯을 등록 — dragEnterEvent/dragLeaveEvent/dropEvent가 이 카드 테두리를
        실선↔코랄 점선으로 실시간 토글해 드롭 가능 영역임을 보여준다."""
        self._drop_frame = frame
        self._drop_frame_normal_qss = normal_qss
        self._drop_frame_active_qss = active_qss

    def _set_drop_active(self, active: bool):
        if self._drop_frame is None:
            return
        self._drop_frame.setStyleSheet(
            self._drop_frame_active_qss if active else self._drop_frame_normal_qss)

    def _build_image_chip(self, parent) -> QWidget:
        """컴팩트 이미지 칩(썸네일+이름+제거 버튼, 첨부 시에만 노출) — 만들어서 돌려주기만
        하고 레이아웃에 얹는 건 호출부 몫."""
        chip = QWidget(parent)
        chip.setObjectName("imageChip")
        chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chip.setStyleSheet(
            "QWidget#imageChip { background:palette(alternate-base); "
            "border:1px solid rgba(128,128,128,90); border-radius:11px; }"
        )
        chip_lay = QHBoxLayout(chip)
        chip_lay.setContentsMargins(3, 2, 4, 2)
        chip_lay.setSpacing(4)
        self._image_thumb = QLabel(chip)
        self._image_thumb.setFixedSize(20, 20)
        self._image_thumb.setScaledContents(True)
        chip_lay.addWidget(self._image_thumb)
        self._image_name_label = QLabel("", chip)
        self._image_name_label.setStyleSheet("font-size:11px;")
        self._image_name_label.setMaximumWidth(140)
        chip_lay.addWidget(self._image_name_label)
        self._image_clear_btn = QToolButton(chip)
        self._image_clear_btn.setText("✕")
        self._image_clear_btn.setToolTip("이미지 제거")
        self._image_clear_btn.setFixedSize(16, 16)
        self._image_clear_btn.clicked.connect(self._clear_image)
        chip_lay.addWidget(self._image_clear_btn)
        chip.setVisible(False)
        self._image_chip = chip
        return chip

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
            QMessageBox.warning(self, self.windowTitle(), f"이미지를 읽을 수 없습니다: {e}")
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
        # 칩 폭이 좁으니(2026-08-12 4차, 컴팩트 칩) 긴 파일명은 가운데 생략 — 전체 이름은
        # 툴팁으로.
        fm = QFontMetrics(self._image_name_label.font())
        self._image_name_label.setText(
            fm.elidedText(name, Qt.TextElideMode.ElideMiddle, 130))
        self._image_name_label.setToolTip(name)
        self._image_chip.setVisible(True)

    def _clear_image(self):
        self._attached_image = None
        self._attached_image_name = ""
        self._image_thumb.clear()
        self._image_chip.setVisible(False)

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasImage() or (md.hasUrls() and any(
                u.toLocalFile().lower().endswith(self._IMG_EXTS) for u in md.urls())):
            e.acceptProposedAction()
            self._set_drop_active(True)

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dragLeaveEvent(self, e):
        self._set_drop_active(False)

    def dropEvent(self, e):
        self._set_drop_active(False)
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

    def _maybe_intercept_paste_image(self, event) -> bool:
        """Ctrl+V 키 이벤트를 받으면 클립보드에 이미지가 있는지 확인해 있으면 첨부로
        가로채고 True를 돌려준다(호출부 `eventFilter`가 이벤트를 소비). 없으면 False —
        보통의 텍스트 붙여넣기이므로 호출부가 기본 동작에 맡긴다."""
        if event.matches(QKeySequence.StandardKey.Paste):
            md = QApplication.clipboard().mimeData()
            img = md.imageData() if md.hasImage() else None
            if isinstance(img, QImage) and not img.isNull():
                self._set_attached_qimage(img, "붙여넣은 이미지")
                return True
        return False


class _MermaidGenWorker(QThread):
    """`generate_mermaid` 1회 호출을 메인(GUI) 스레드 밖에서 돈다(2026-08-19 —
    동기 호출+`WaitCursor`가 게이트웨이 응답을 기다리는 동안 이벤트 루프 자체를 막아
    창이 완전히 멈춘 것처럼 보이던 문제 수정). 성공/실패를 시그널로 알린다 — 수신자
    (`_MermaidDialog`)가 메인 스레드에 있으므로 Qt가 큐 연결로 안전하게 전달한다."""

    succeeded = pyqtSignal(str, str)   # (mermaid 텍스트, 실제 사용된 모델)
    failed = pyqtSignal(str)           # 에러 메시지

    def __init__(self, api_key, desc, model, base_url, image, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._desc = desc
        self._model = model
        self._base_url = base_url
        self._image = image

    def run(self):
        try:
            from easycad.ai.text_to_mermaid import generate_mermaid
            text, used = generate_mermaid(self._api_key, self._desc, model=self._model,
                                          base_url=self._base_url, image=self._image)
        except Exception as e:  # noqa: BLE001 — 실패 사유를 그대로 다이얼로그에 전달
            self.failed.emit(str(e))
            return
        self.succeeded.emit(text, used)


class _ModelListWorker(QThread):
    """`list_text_models` 1회 조회를 메인 스레드 밖에서 돈다(2026-08-20, 피드백: "Mermaid
    창 처음 열 때 느리다, 두 번째부터는 빠르다" — 검토 결과 `_populate_models`가 다이얼로그
    생성자 안에서 이 네트워크 호출을 동기로 하고 있어, 첫 오픈이 응답을 기다리는 동안
    다이얼로그 자체가 뜨지 않은 것처럼 보인 것이었다(연결 재사용으로 두 번째부터 빨라지는
    체감과 일치). 추천 모델 2개로 드롭다운을 즉시 채운 뒤, 실제 목록은 이 워커가 도착하는
    대로 갱신한다."""

    succeeded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, api_key, base_url, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url

    def run(self):
        try:
            models = gw.list_text_models(self._api_key, self._base_url, timeout=8.0)
        except Exception as e:  # noqa: BLE001 — 조회 실패는 조용히 폴백(추천 2개만 유지)
            self.failed.emit(str(e))
            return
        self.succeeded.emit(models)


def _render_mermaid_preview_pixmap(text: str, target_size: QSize) -> QPixmap | None:
    """Mermaid 코드 → 미리보기 픽스맵(§8 항목23 Stage 5, 2026-08-19). 실제 삽입 경로
    (`host_fileio._build_mermaid`/`_make_mermaid_node`/`_make_mermaid_edge`)와 똑같은
    파서(`parse_mermaid`)+배치(`layout_positions`)+도형매핑(`_MERMAID_SHAPE_ITEM`)+
    부착점(`_border_attach`)+직교라우팅(`_PolyArrowItem.build_elbow`)을 그대로 재사용해
    미리보기와 실제 삽입 결과가 어긋나지 않게 한다 — SVG 후보 미리보기
    (`_render_svg_candidate_pixmap`)와 같은 원칙. host_fileio.py 자체를 import하면
    이 잎 모듈의 순환 임포트 제약을 어기므로, host_fileio가 이미 재사용 가능한 형태로
    분리해둔 `host_widgets._MERMAID_SHAPE_ITEM`/`_border_attach`만 가져다 쓴다. 파싱
    실패·빈 입력이면 None(호출부가 안내 문구를 보여준다)."""
    try:
        graph = parse_mermaid(text)
    except MermaidError:
        return None
    w, h = 120.0, 56.0
    pos = layout_positions(graph, node_w=w, node_h=h)
    if not pos:
        return None

    scene = QGraphicsScene()
    pen = QPen(_ICON_COLOR, 1.5)
    items_by_id: dict[str, object] = {}
    for nid, node in graph.nodes.items():
        x, y = pos[nid]
        shape, kind = _MERMAID_SHAPE_ITEM.get(node.shape, ("rect", None))
        rect = QRectF(0.0, 0.0, w, h)
        if shape == "ellipse":
            it = _EllipseItem(rect)
        elif shape == "symbol":
            it = _SymbolItem(kind, rect)
        else:
            it = _RectItem(rect)
        it.setPen(QPen(pen))
        it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setPos(x, y)
        scene.addItem(it)
        if node.label:
            it.ensure_label().setPlainText(node.label)
        it._sync_label()
        items_by_id[nid] = it

    for e in graph.edges:
        s = items_by_id.get(e.src)
        d = items_by_id.get(e.dst)
        if s is None or d is None or s is d:
            continue
        rs = s.mapRectToScene(s.rect())
        rd = d.mapRectToScene(d.rect())
        a_src = _border_attach(rs, rd.center())
        a_dst = _border_attach(rd, rs.center())
        arr = _PolyArrowItem(_ICON_COLOR, 1, e.arrow)
        arr.set_points(a_src, a_dst)
        arr.set_bound(0, s, s.mapFromScene(a_src))
        arr.set_bound(len(arr._pts) - 1, d, d.mapFromScene(a_dst))
        arr._auto_route = True
        scene.addItem(arr)
        try:
            arr.build_elbow()
        except Exception:
            pass
        if e.label:
            arr.ensure_label().setPlainText(e.label)
        arr._sync_label()

    pm = QPixmap(target_size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = 10.0
    target = QRectF(margin, margin,
                    target_size.width() - 2 * margin, target_size.height() - 2 * margin)
    source = scene.itemsBoundingRect()
    if source.width() > 0 and source.height() > 0:
        scene.render(p, target, source, Qt.AspectRatioMode.KeepAspectRatio)
    p.end()
    return pm


class _ClickablePreviewLabel(QLabel):
    """미리보기 QLabel — 클릭하면 확대 보기를 연다(2026-08-20 피드백: "미리보기창을
    누르면 크게 보여주는 기능이 있으면 좋겠다")."""

    clicked = pyqtSignal()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class _MermaidDialog(_ImageAttachMixin, QDialog):
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid 가져오기")
        self.setAcceptDrops(True)
        self._init_image_attach_state()
        self._worker = None               # _MermaidGenWorker | None — 생성 중일 때만 설정
        self._model_list_worker = None    # _ModelListWorker | None — 조회 중일 때만 설정
        lay = QVBoxLayout(self)

        # [2026-08-13 5차] 옛 상단 3줄 안내(Enter·드래그/Ctrl+V·코드칸 직접입력)를 각자
        # 쓰이는 자리로 흩었다(피드백: "맨위 세줄 설명은 각자 위치로") — Enter 힌트는
        # 입력칸 아래 캡션(카드 안), 드래그/Ctrl+V는 첨부 버튼 툴팁, 직접입력 안내는
        # Mermaid 코드 라벨로. 상단이 비며 설정 버튼만 혼자 남던 것도 함께 해결. [6차]
        # 설정 버튼은 그 뒤 다시 옮겨 지금은 아래 모델 행(model_row) 맨 오른쪽에 있다.
        # ---- 입력 카드: 텍스트 입력(위) + 첨부·생성 툴바(아래) — 2026-08-12 4차, 디자인
        # 시안 합의로 버튼을 입력칸 옆이 아니라 아래 툴바로. 다크 테마에서도 입력칸만
        # 밝게 고정해 코드 편집기(어두운 배경)와 대비되게 한다(라이트 테마는 원래도 밝아
        # 변화 없음) — "여기 입력하세요" 신호를 항상 뚜렷하게 유지하려는 의도.
        # [2026-08-13 6차] 순백(#ffffff)이 어두운 배경 사이에서 너무 눈부시다는 피드백으로
        # 톤을 살짝 낮췄다(#e7e0d6, 따뜻한 아이보리) — 아래 Mermaid 코드칸(어두운 배경)과의
        # 대비는 유지하면서 시선을 덜 자극하게.
        dark = bool(getattr(self.parent(), "_dark", True))

        prompt_frame = QFrame(self)
        prompt_frame.setObjectName("promptCard")
        prompt_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        _prompt_bg = '#e7e0d6' if dark else 'palette(base)'
        _prompt_normal_qss = (
            "QFrame#promptCard { border:1px solid rgba(128,128,128,90); border-radius:8px; "
            f"background:{_prompt_bg}; }}"
        )
        # [2026-08-20 피드백] 드래그 오버 중엔 이 카드 테두리를 코랄 점선으로 바꿔 드롭
        # 가능 영역임을 실시간으로 알린다(`_ImageAttachMixin._set_drop_active`가 토글).
        _prompt_active_qss = (
            f"QFrame#promptCard {{ border:2px dashed {_ACCENT_CORAL}; border-radius:8px; "
            f"background:{_prompt_bg}; }}"
        )
        prompt_frame.setStyleSheet(_prompt_normal_qss)
        self._set_image_drop_frame(prompt_frame, _prompt_normal_qss, _prompt_active_qss)
        prompt_frame_lay = QVBoxLayout(prompt_frame)
        prompt_frame_lay.setContentsMargins(0, 0, 0, 0)
        prompt_frame_lay.setSpacing(0)

        self._prompt_edit = QPlainTextEdit(prompt_frame)
        self._prompt_edit.setPlaceholderText("예: 날씨를 예보하는 워크플로우")
        self._prompt_edit.setFixedHeight(64)
        self._prompt_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._prompt_edit.setFrameShape(QFrame.Shape.NoFrame)   # 테두리는 카드가 그림
        self._prompt_edit.setAcceptDrops(False)   # 드롭을 이 다이얼로그(dropEvent)로 넘김
        self._prompt_edit.installEventFilter(self)   # Enter 생성·Ctrl+V 이미지 첨부
        self._prompt_edit.setStyleSheet(
            "QPlainTextEdit { background:transparent; " +
            ("color:#241a15; }" if dark else "}")
        )
        prompt_frame_lay.addWidget(self._prompt_edit)

        # [2026-08-13 5차] 옛 상단 힌트 1번째 줄("Enter — AI로 생성")을 입력칸 안(카드 하단,
        # 툴바 위)의 작은 캡션으로 흡수 — 입력 중엔 눈에 거슬리지 않게 우측 정렬·저채도.
        enter_hint = QLabel("Enter 생성 · Shift+Enter 줄바꿈", prompt_frame)
        enter_hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        enter_hint.setStyleSheet("color:#8a8a8a; font-size:11px; background:transparent; "
                                  "padding:0 8px 3px 0;")
        prompt_frame_lay.addWidget(enter_hint)

        toolbar_widget = QWidget(prompt_frame)
        toolbar_widget.setObjectName("promptToolbar")
        toolbar_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        toolbar_widget.setStyleSheet(
            "QWidget#promptToolbar { background:palette(button); "
            "border-top:1px solid rgba(128,128,128,90); "
            "border-bottom-left-radius:8px; border-bottom-right-radius:8px; }"
        )
        toolbar_lay = QHBoxLayout(toolbar_widget)
        toolbar_lay.setContentsMargins(8, 6, 8, 6)
        toolbar_lay.setSpacing(8)

        self._attach_btn = QToolButton(toolbar_widget)
        self._attach_btn.setIcon(_act_icon("attach"))
        self._attach_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._attach_btn.setText("이미지 첨부")
        # [2026-08-13 5차] 옛 상단 힌트 2번째 줄(드래그·Ctrl+V)을 이 버튼 툴팁으로 흡수 —
        # Qt 툴팁은 HTML을 주면 자동으로 리치텍스트 처리해 불릿(<br>·)이 그대로 렌더된다.
        self._attach_btn.setToolTip("이미지 첨부<br>· 드래그 앤 드롭<br>· Ctrl+V 붙여넣기")
        self._attach_btn.clicked.connect(self._browse_image)
        toolbar_lay.addWidget(self._attach_btn)

        # 컴팩트 이미지 칩(첨부 시에만 노출) — 옛 전체폭 행 대신 툴바 안 작은 pill로
        # (2026-08-12 4차, "이미지첨부 자리에 썸네일만 작게" 피드백). Stage 3(2026-08-19)
        # 부터 `_ImageAttachMixin._build_image_chip`로 `_SvgAssetDialog`와 공유.
        toolbar_lay.addWidget(self._build_image_chip(toolbar_widget))

        toolbar_lay.addStretch(1)

        self._ai_btn = QToolButton(toolbar_widget)
        # [self-review 2026-08-12] _svg_icon_pixmap()만 쓰면 QIcon.Mode.Disabled 변형이 없어
        # setEnabled(False) 중에도(생성 진행 중) 아이콘이 그대로 진하게 남는다 — 실제
        # 창에서 활성/비활성 스크린샷을 비교해 발견(육안으로 구분 불가였음). 다른 상단바
        # 아이콘들이 쓰는 `_finish_act_icon`의 35% 알파 흐림 관례를 그대로 재현.
        gen_pm = _svg_icon_pixmap("generate", 18, QColor("#1b120d"))
        gen_icon = QIcon(gen_pm)
        gen_dim = QPixmap(gen_pm.size())
        gen_dim.fill(Qt.GlobalColor.transparent)
        _dp = QPainter(gen_dim)
        _dp.setOpacity(0.35)
        _dp.drawPixmap(0, 0, gen_pm)
        _dp.end()
        gen_icon.addPixmap(gen_dim, QIcon.Mode.Disabled, QIcon.State.Off)
        self._ai_btn.setIcon(gen_icon)
        self._ai_btn.setIconSize(QSize(16, 16))
        self._ai_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._ai_btn.setText("AI로 생성")
        self._ai_btn.setToolTip("AI로 생성 (Enter)")
        self._ai_btn.clicked.connect(self._on_ai_clicked)
        self._ai_btn.setStyleSheet(_CORAL_BTN_QSS)
        toolbar_lay.addWidget(self._ai_btn)

        prompt_frame_lay.addWidget(toolbar_widget)

        # [2026-08-20 피드백] 레이아웃 재구성 — 오른쪽(미리보기)이 세로 전체를 채우고,
        # 왼쪽(입력 카드+모델행+커넥터+코드칸)은 위아래로 쌓인 2분할 구조.
        left_col = QVBoxLayout()
        left_col.addWidget(prompt_frame)

        self._progress = _GenProgressRow(self)
        left_col.addWidget(self._progress)

        # ---- 모델 선택: 평범한 드롭다운(gemini/gpt 그룹 헤더, 추천 배지 없음) + 새로고침 +
        # 설정. [2026-08-13 6차] 옛 위치(코드칸 아래)에서 입력카드 바로 아래(화살표 꼬리
        # 위)로 옮기고, 커넥터 줄에 혼자 있던 설정 버튼도 이 행 맨 오른쪽(새로고침 옆)으로
        # 합쳐 "AI 생성에 관련된 것들"을 한 자리에 모았다(피드백: "설정버튼도 모델 드랍다운
        # 오른쪽으로").
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("모델:", self))
        self._model_combo = QComboBox(self)
        self._model_combo.setStyleSheet(_ROUNDED_COMBO_QSS)   # [2026-08-13] 각진 모서리 → 둥글게
        model_row.addWidget(self._model_combo, 1)
        # [2026-08-20 피드백] 전용 새로고침 버튼 제거 — "API 키를 만지는 설정 창의
        # 연결 테스트가 그 역할을 겸한다"는 지적으로, 설정 버튼만 남긴다.
        self._settings_btn = QToolButton(self)
        self._settings_btn.setIcon(_act_icon("settings"))
        self._settings_btn.setToolTip("AI 게이트웨이 설정(주소·키·연결 테스트)")
        self._settings_btn.clicked.connect(self._open_gateway_settings)
        model_row.addWidget(self._settings_btn)
        left_col.addLayout(model_row)
        self._populate_models()

        # ---- 입력→코드 커넥터 — 순서도 커넥터 느낌으로 "이 입력이 아래 코드로 바뀐다"를
        # 시각화(2026-08-12 4차, 디자인 시안 합의). [2026-08-13 5차] 원 테두리를 없애고
        # 화살표만 키움(시인성 피드백). [2026-08-13 6차] 설정 버튼이 위 모델 행으로 옮겨가
        # 이 줄은 다시 화살표 하나만 — 좌우 스트레치로 중앙 정렬.
        connector_row = QHBoxLayout()
        connector_row.addStretch(1)
        arrow_label = QLabel(self)
        arrow_label.setPixmap(_handdrawn_down_arrow_pixmap(QColor(_ACCENT_CORAL)))
        arrow_label.setFixedSize(30, 46)
        connector_row.addWidget(arrow_label)
        connector_row.addStretch(1)
        left_col.addLayout(connector_row)

        # ---- 2번 칸: Mermaid 코드(넉넉함) — AI 결과가 채워지거나 직접 타이핑/붙여넣기 ----
        # [2026-08-13 5차] 옛 상단 힌트 3번째 줄("아래 칸에 직접 입력·붙여넣기 가능")을
        # 라벨에 흡수. [2026-08-20 피드백] 레이아웃 재구성 — 미리보기가 세로 2분할 중
        # 오른쪽 전체를 채우고, 코드칸은 왼쪽(입력 카드 아래)에 남는다(옛 "옆(가로 분할)"
        # 배치에서 좌우 열 자체를 좌=입력전체/우=미리보기로 승격). 복사 버튼은 제거
        # (피드백: "드래그해서 복사하면 됨").
        code_label_row = QHBoxLayout()
        code_label_row.addWidget(QLabel("Mermaid 코드 (직접 입력·붙여넣기 가능):", self))
        code_label_row.addStretch(1)
        left_col.addLayout(code_label_row)
        self._edit = QPlainTextEdit(self)
        self._edit.setPlaceholderText(self._SAMPLE)
        self._edit.setMinimumSize(QSize(420, 260))
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        left_col.addWidget(self._edit, 1)

        split = QHBoxLayout()
        split.addLayout(left_col, 1)

        preview_col = QVBoxLayout()
        preview_col.addWidget(QLabel("미리보기 (클릭하면 확대):", self))
        preview_frame = QFrame(self)
        preview_frame.setObjectName("mermaidPreviewFrame")
        preview_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        preview_frame.setStyleSheet(
            "QFrame#mermaidPreviewFrame { border:1px solid rgba(128,128,128,90); "
            "border-radius:8px; }"
        )
        preview_frame_lay = QVBoxLayout(preview_frame)
        preview_frame_lay.setContentsMargins(6, 6, 6, 6)
        self._preview_label = _ClickablePreviewLabel(preview_frame)
        self._preview_label.setMinimumSize(160, 160)
        self._preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet("color:#8a8a8a; font-size:11px;")
        self._preview_label.setText("코드를 입력하면\n미리보기가 표시됩니다")
        self._preview_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preview_label.clicked.connect(self._show_enlarged_preview)
        preview_frame_lay.addWidget(self._preview_label)
        preview_col.addWidget(preview_frame, 1)
        split.addLayout(preview_col, 1)

        lay.addLayout(split, 1)

        # 코드 변경 350ms 후 재렌더(디바운스) — 타이핑마다 즉시 다시 그리면 무거워질 수
        # 있어 QTimer로 묶는다. `textChanged`는 인자가 없어 `QTimer.start`(무인자 오버로드)
        # 로 바로 연결 가능(재시작 = 디바운스).
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(350)
        self._preview_timer.timeout.connect(self._update_preview)
        self._edit.textChanged.connect(self._preview_timer.start)

        self._btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                      | QDialogButtonBox.StandardButton.Cancel, self)
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        ok_btn = self._btns.button(QDialogButtonBox.StandardButton.Ok)
        # [2026-08-19 Stage 6] 목업 시각 언어 차용 — "OK" 대신 결과를 명시하는 라벨.
        ok_btn.setText("확인 (캔버스 삽입)")
        ok_btn.setStyleSheet(_CORAL_BTN_QSS)
        lay.addWidget(self._btns)

    def text(self):
        return self._edit.toPlainText()

    def _show_enlarged_preview(self):
        """미리보기를 클릭하면 큰 창으로 다시 렌더해 보여준다(2026-08-20 피드백) — 작은
        패널 해상도로는 안 보이던 라벨·구조를 확인할 수 있게. 코드가 비어 있으면 무시."""
        text = self._edit.toPlainText()
        if not text.strip():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("미리보기 확대")
        v = QVBoxLayout(dlg)
        label = QLabel(dlg)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        size = QSize(900, 700)
        pm = _render_mermaid_preview_pixmap(text, size)
        if pm is None:
            label.setText("구문 오류 — 미리보기를 표시할 수 없습니다")
        else:
            label.setPixmap(pm)
        v.addWidget(label)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        dlg.resize(size)
        dlg.exec()

    def _update_preview(self):
        """디바운스 타이머 만료 시 호출 — `_render_mermaid_preview_pixmap`으로 다시 그린다."""
        text = self._edit.toPlainText()
        if not text.strip():
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText("코드를 입력하면\n미리보기가 표시됩니다")
            return
        pm = _render_mermaid_preview_pixmap(text, self._preview_label.size())
        if pm is None:
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText("구문 오류 —\n미리보기를 표시할 수 없습니다")
        else:
            self._preview_label.setText("")
            self._preview_label.setPixmap(pm)

    def closeEvent(self, e):
        # 생성 중(QThread 워커가 돎)에는 닫지 않는다 — 워커가 끝나기 전에 다이얼로그가
        # 사라지면 다른 스레드에서 이미 소멸된 위젯에 시그널을 전달하려다 죽을 위험이 있다
        # (2026-08-19, 이 프로젝트가 과거 겪은 Qt 라이프사이클 네이티브 크래시 계열과 같은 종류).
        if self._worker is not None and self._worker.isRunning():
            e.ignore()
            return
        if self._model_list_worker is not None and self._model_list_worker.isRunning():
            e.ignore()
            return
        super().closeEvent(e)

    def eventFilter(self, obj, event):
        if obj is self._prompt_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False   # Shift+Enter는 기본 동작(줄바꿈)에 맡김
                self._on_ai_clicked()
                return True
            if self._maybe_intercept_paste_image(event):
                return True
        return super().eventFilter(obj, event)

    # ---- 모델 선택(드롭다운) ----------------------------------------------------

    def _open_gateway_settings(self):
        """`_AIGatewaySettingsDialog`(주소·키·연결 테스트)를 이 Mermaid 창의 자식 모달로
        연다. 주소/키가 바뀌었을 수 있으니 닫힌 뒤 드롭다운을 다시(비동기로) 채운다."""
        if _AIGatewaySettingsDialog(self).exec() == QDialog.DialogCode.Accepted:
            self._populate_models()

    def _populate_models(self):
        """[2026-08-20 재작성 — 피드백: "Mermaid 창 처음 열 때 느리다, 두 번째부터는
        빠르다" 검토] 옛 코드는 게이트웨이 `/models`를 이 생성자 호출 경로에서 동기로
        불러 첫 오픈이 응답을 기다리는 동안 다이얼로그 자체가 못 뜨는 것처럼 보였다(연결
        재사용으로 두 번째부터 빨라지는 체감과 일치하는 원인). 이제는 추천 모델 2개로
        드롭다운을 즉시 채우고, 실제 목록은 `_ModelListWorker`(QThread)가 백그라운드로
        조회해 도착하면 갱신한다."""
        self._fill_model_combo([])
        key = gw.resolve_api_key()
        if not key:
            return
        if self._model_list_worker is not None and self._model_list_worker.isRunning():
            # 이미 조회 중(예: 설정 창을 열자마자 다시 닫는 경우) — 새로 또 띄우면
            # `self._model_list_worker`가 새 워커로 덮어써져 먼저 시작한 워커가 고아가
            # 되고, `closeEvent`가 그 고아 워커를 못 봐 다이얼로그가 먼저 닫혀버릴 수
            # 있다(이 프로젝트가 과거 겪은 Qt 라이프사이클 크래시와 같은 종류). 지금
            # 도는 조회가 끝나면 어차피 최신 결과로 갱신되므로 조용히 건너뛴다.
            return
        self._model_list_worker = _ModelListWorker(key, gw.resolve_base_url(), self)
        self._model_list_worker.succeeded.connect(self._on_models_listed)
        self._model_list_worker.start()

    def _on_models_listed(self, models):
        self._fill_model_combo(models)

    def _fill_model_combo(self, models):
        """gemini·gpt 그룹 헤더가 있는 평범한 드롭다운으로 채운다(추천 배지·설명은 없음
        — 재피드백: "추천 설명은 빼자"). 헤더 행은 `QStandardItem.setEnabled(False)`로
        선택 불가. `models`가 비어 있으면(조회 전·실패 시) 추천 둘만으로 조용히 폴백.
        이전에 고른 모델이 새 목록에도 있으면 그대로 유지한다(백그라운드 갱신이 사용자가
        막 고른 모델을 조용히 되돌리지 않도록)."""
        prev = self.model() if self._model_combo.count() else None
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

        target = prev if prev in pool else r1
        default_row = next(
            (i for i in range(std_model.rowCount())
             if std_model.item(i).data(Qt.ItemDataRole.UserRole) == target), -1)
        self._model_combo.setCurrentIndex(default_row if default_row >= 0 else
                                          (1 if std_model.rowCount() > 1 else -1))

    def model(self) -> str:
        idx = self._model_combo.currentIndex()
        data = self._model_combo.itemData(idx, Qt.ItemDataRole.UserRole) if idx >= 0 else None
        return data or gw.TEXT_RECOMMEND_1

    def _on_ai_clicked(self):
        """2026-08-19 비동기화 — 예전엔 `generate_mermaid`를 이 자리에서 동기 호출+
        `WaitCursor`로 감싸 게이트웨이 응답이 올 때까지(길면 20~28초) 창이 완전히
        멈춘 것처럼 보였다. `_MermaidGenWorker`(QThread)로 옮기고 marquee 진행바+
        경과시간(`_GenProgressRow`)으로 대체 — 이벤트 루프가 안 막히므로 창을
        옮기거나 다른 다이얼로그 조작도 가능하다."""
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
        self._btns.setEnabled(False)
        self._progress.start("AI로 생성 중")
        self._worker = _MermaidGenWorker(key, desc, self.model(), base_url, image, self)
        self._worker.succeeded.connect(self._on_gen_succeeded)
        self._worker.failed.connect(self._on_gen_failed)
        self._worker.finished.connect(self._on_gen_thread_finished)
        self._worker.start()

    def _on_gen_succeeded(self, text, _used):
        # [2칸 분리 후에도 유지] setPlainText()는 되돌리기 스택을 초기화해버려 이전에 손으로
        # 고친 코드를 잃는다 — QTextCursor 전체선택+치환은 `_edit`의 undo 스택에 남아
        # Ctrl+Z로 AI 생성 전 코드를 복구할 수 있다.
        cursor = self._edit.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text)
        # [2026-08-12 4차, 디자인 시안 합의] 크레딧 잔액 표시는 이 창에서 제거하고
        # `_AIGatewaySettingsDialog`의 "연결 테스트" 한 곳으로 통합했다(중복 표시 제거).

    def _on_gen_failed(self, err):
        QMessageBox.warning(self, "Mermaid 가져오기", f"생성 실패: {err}")

    def _on_gen_thread_finished(self):
        self._progress.stop()
        self._ai_btn.setEnabled(True)
        self._btns.setEnabled(True)
        self._worker = None


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

        # [2026-08-12 4차, 디자인 시안 합의] 옛 "모델 새로고침"+"크레딧 확인" 두 버튼을
        # "연결 테스트" 하나로 통합 — 클릭 한 번으로 모델 목록·크레딧 잔여를 함께 확인해
        # 두 번 누를 필요가 없다. 결과는 두 줄로 표시.
        test_row = QHBoxLayout()
        self._test_btn = QToolButton(self)
        self._test_btn.setIcon(_act_icon("refresh"))
        self._test_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._test_btn.setText("연결 테스트")
        self._test_btn.setToolTip("모델 목록 새로고침 + 크레딧 확인")
        self._test_btn.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self._test_btn)
        test_row.addStretch(1)
        lay.addLayout(test_row)

        self._test_result_label = QLabel("", self)
        self._test_result_label.setWordWrap(True)
        lay.addWidget(self._test_result_label)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def base_url(self) -> str:
        return self._url_edit.text().strip() or gw.BASE_URL

    def api_key(self) -> str:
        return self._key_edit.text().strip()

    def _on_test_clicked(self):
        """모델 목록·크레딧 잔여를 한 번에 확인(2026-08-12 4차, 두 버튼 통합). 모델·크레딧
        조회는 서로 독립이라 하나가 실패해도 다른 하나는 계속 시도해 각자 결과를 보여준다.
        크레딧은 "잔여" 문구로 남은 양임을 명확히 한다(Mermaid 창이 예전에 쓰던 표기와
        같은 어순, 옛 설정창의 "…사용"은 헷갈린다는 피드백으로 폐기)."""
        key = self.api_key()
        if not key:
            self._test_result_label.setText("API 키를 입력하세요.")
            return
        self._test_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            lines = []
            try:
                models = gw.list_text_models(key, self.base_url(), timeout=10.0)
                n_gpt = sum(1 for m in models if "gpt" in m.lower())
                n_gemini = sum(1 for m in models if "gemini" in m.lower())
                lines.append(f"Gemini {n_gemini}개 · GPT {n_gpt}개 응답")
            except Exception as e:
                lines.append(f"모델 조회 실패: {e}")
            try:
                remaining, quota = gw.get_credit_balance(key, self.base_url())
                lines.append(f"크레딧 잔여 {remaining:.0f} / {quota:.0f}")
            except Exception as e:
                lines.append(f"크레딧 확인 실패: {e}")
            self._test_result_label.setText("\n".join(lines))
        finally:
            QApplication.restoreOverrideCursor()
            self._test_btn.setEnabled(True)

    def _on_accept(self):
        gw.store_base_url(self.base_url())
        gw.store_api_key(self.api_key())
        self.accept()


# ---------------------------------------------------------------------------
# [§8 항목20 B단계, 2026-08-14] AI SVG 에셋 생성 — 텍스트 설명 → gpt/gemini 후보 → 클릭
# 선택 → 삽입(신규) 또는 도형 대체. Mermaid 다이얼로그와 통합하지 않고 별도 다이얼로그
# (계획서 확정 — 소비처가 다름: Mermaid는 캔버스 전체 레이아웃 대체, SVG는 도형 1개
# 생성/대체). 코랄 버튼 QSS 등 스타일만 그쪽 관례를 재사용.
# ---------------------------------------------------------------------------

def _render_svg_candidate_pixmap(svg_text: str, size: int) -> QPixmap | None:
    """후보 미리보기 렌더 — 원본 SVG를 그대로 QSvgRenderer로 그리지 않고, 실제 삽입 때와
    동일한 파서(`parse_svg_string`)로 아이템을 만들어 임시 씬에 얹은 뒤 우리 펜(중립
    잉크색·NoBrush)으로 렌더한다. 프롬프트가 "색은 지정 안 해도 됨"을 허용하는데(
    `svg_import.py`가 원래 색을 애초에 무시하는 설계 — 항상 앱이 다시 칠함), 원본 SVG를
    그대로 QSvgRenderer로 렌더하면 SVG 기본값(stroke:none)상 선-아트가 통째로 안 보이거나
    반대로 닫힌 도형은 기본 fill:black 검은 덩어리로 나올 수 있다 — A단계 실측 때 진단
    스크립트가 실제로 겪은 함정과 같은 종류(`docs/history/2026-08.md` "§8 항목20" 참조).
    미리보기와 실제 삽입 결과가 달라지면 신뢰할 수 없으므로 항상 같은 경로로 렌더한다.
    파싱 실패·빈 결과면 None(호출부가 "미리보기 실패" 표시)."""
    try:
        items, vb = parse_svg_string(svg_text)
    except Exception:
        return None
    if not items:
        return None
    scene = QGraphicsScene()
    pen = QPen(_ICON_COLOR, 1.5)
    for it in items:
        if not isinstance(it, _TextItem):
            it.setPen(pen)
            if hasattr(it, "setBrush"):
                it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        scene.addItem(it)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = 6.0
    target = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    source = scene.itemsBoundingRect()
    if source.width() > 0 and source.height() > 0:
        scene.render(p, target, source, Qt.AspectRatioMode.KeepAspectRatio)
    p.end()
    return pm


class _SvgCandidateCard(QFrame):
    """후보 1개 카드 — 체크박스 + 썸네일 + 모델명. 두 가지 독립된 선택 개념을 함께 담는다
    (2026-08-19 Stage 4, deep-interview 확정): ⓐ 카드 클릭 = 단일 선택(코랄 테두리) —
    OK 눌러 캔버스에 삽입/대체할 후보 하나. ⓑ 좌상단 체크박스 = 다중 선택 — "내 심볼로
    저장" 버튼으로 한꺼번에 심볼 팔레트에 등록할 후보들(0개 이상, 클릭 선택과 무관)."""

    def __init__(self, model_label: str, svg_text: str, pixmap: QPixmap | None,
                on_pick, parent=None):
        super().__init__(parent)
        self._svg_text = svg_text
        self._on_pick = on_pick
        self._selected = False
        self.setFixedSize(120, 156)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 6)
        self._save_check = QCheckBox("심볼로 저장", self)
        self._save_check.setStyleSheet("font-size:10px;")
        lay.addWidget(self._save_check)
        thumb = QLabel(self)
        thumb.setFixedSize(100, 100)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pixmap is not None:
            thumb.setPixmap(pixmap)
        else:
            thumb.setText("(미리보기 실패)")
            thumb.setWordWrap(True)
        lay.addWidget(thumb)
        name = QLabel(model_label, self)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size:11px;")
        lay.addWidget(name)
        self._apply_style()

    def svg_text(self) -> str:
        return self._svg_text

    def is_checked_for_save(self) -> bool:
        return self._save_check.isChecked()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        border = _ACCENT_CORAL if self._selected else "rgba(128,128,128,90)"
        width = 2 if self._selected else 1
        self.setStyleSheet(
            f"QFrame {{ border:{width}px solid {border}; border-radius:8px; }}")

    def mousePressEvent(self, e):
        self._on_pick(self)
        super().mousePressEvent(e)


class _SaveToSymbolsFolderDialog(QDialog):
    """"내 심볼로 저장" 대상 폴더 선택 — 기존 폴더 드롭다운 또는 새 폴더 이름(2026-08-19
    Stage 4, deep-interview 확정: "기존 폴더 또는 새폴더로"). `symbol_library.py`(fileio,
    host_selection.py 아님)만 참조해 이 잎 모듈의 순환 임포트 제약을 어기지 않는다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("내 심볼로 저장")
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("저장할 폴더:", self))
        self._folder_combo = QComboBox(self)
        self._folder_combo.addItem("(미분류)", None)
        for f in symbol_library.load_folders():
            self._folder_combo.addItem(f, f)
        self._folder_combo.addItem("새 폴더…", "__new__")
        self._folder_combo.setStyleSheet(_ROUNDED_COMBO_QSS)
        self._folder_combo.currentIndexChanged.connect(self._on_combo_changed)
        lay.addWidget(self._folder_combo)

        self._new_folder_edit = QLineEdit(self)
        self._new_folder_edit.setPlaceholderText("새 폴더 이름")
        self._new_folder_edit.setVisible(False)
        lay.addWidget(self._new_folder_edit)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(_CORAL_BTN_QSS)
        lay.addWidget(btns)

    def _on_combo_changed(self, _idx):
        self._new_folder_edit.setVisible(self._folder_combo.currentData() == "__new__")

    def chosen_folder(self) -> str | None:
        data = self._folder_combo.currentData()
        if data == "__new__":
            return self._new_folder_edit.text().strip() or None
        return data


class _SvgGenWorker(QThread):
    """`generate_svg` 1회 호출을 담당하는 워커 — 요청한 개수만큼 인스턴스를 만들어 전부
    동시에 `start()`하면 모델 간·모델 내부 완전 병렬이 된다(2026-08-19 deep-interview
    확정, §8 항목20 후속 Stage 2). Stage 1의 "워커 하나가 모델 리스트를 순차 호출"하던
    설계(당시는 프리징 해소만이 목표라 호출 의미를 그대로 유지)에서 "워커 하나 = 호출
    하나"로 재설계 — 모델당 후보 개수 확장(0~5개)과 완전 병렬화를 동시에 만족하는 가장
    단순한 형태. `_SvgAssetDialog`가 워커 목록을 들고 각자의 `finished`를 세어 전체
    완료를 판정한다."""

    candidate = pyqtSignal(str, str)      # (실제 사용된 모델, svg 텍스트)
    model_failed = pyqtSignal(str, str)   # (모델, 에러 메시지)

    def __init__(self, api_key, subject, model, base_url, image, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._subject = subject
        self._model = model
        self._base_url = base_url
        self._image = image   # PIL.Image.Image | None — Stage 3(2026-08-19)

    def run(self):
        try:
            svg_text, used = generate_svg(self._api_key, self._subject, model=self._model,
                                          base_url=self._base_url, image=self._image)
        except Exception as e:  # noqa: BLE001 — 개별 실패, 다른 워커는 계속 진행
            self.model_failed.emit(self._model, str(e))
            return
        self.candidate.emit(used, svg_text)


class _SvgAssetDialog(_ImageAttachMixin, QDialog):
    """AI SVG 에셋 생성 — 대상 설명 한 줄 + 모델별 후보 개수 드롭다운(GPT/Gemini 각각
    0~5개, 2026-08-19 deep-interview 확정 — §8 항목20 후속 Stage 2, 최대 10개까지 한
    번에 받아 마음에 드는 걸 고르고 싶다는 실사용 요청) + 생성 버튼 + 후보 카드 가로
    스크롤 나열(클릭 선택) + OK/Cancel. 진입점 2곳(메뉴 삽입·우클릭 대체)이 이 다이얼로그를
    그대로 공유한다 — 호출부가 `selected_svg()` 결과를 각자의 방식(새로 삽입 vs 기존 도형
    대체)으로 소비.

    진행 표시는 `_SvgGenWorker`(QThread, 호출 1건당 인스턴스 1개) + marquee 진행바·
    경과시간(`_GenProgressRow`). 요청한 후보 전부를 **동시에 병렬 호출**한다(모델 간·
    모델 내부 구분 없이 완전 병렬, deep-interview 확정 — 최악 10개 동시 호출도 실측으로
    확인함: gpt 5개는 ~7초, gemini 5개는 30~52초에 걸쳐 전부 성공, 실패 0건). 끝난
    순서대로 카드가 하나씩 채워지므로(gpt가 보통 먼저 도착) 전부 끝나기 전에도 고를 수
    있다.

    이미지 입력도 받는다(찾아보기·드래그드롭·Ctrl+V, `_ImageAttachMixin` — 2026-08-19
    Stage 3, `_MermaidDialog`와 동일한 첨부 UI를 재사용). 이미지가 첨부되면 대상 설명은
    선택 사항이 된다(`generate_svg`의 `image` 인자, `text_to_mermaid.generate_mermaid`와
    동일 관례)."""

    _MAX_PER_MODEL = 5

    def __init__(self, parent=None, confirm_label: str = "확인 (도형 삽입)"):
        super().__init__(parent)
        self.setWindowTitle("AI SVG 에셋 생성")
        self.setMinimumWidth(460)
        self.setAcceptDrops(True)
        self._init_image_attach_state()
        self._candidates: list[tuple[_SvgCandidateCard, str, str]] = []
        self._selected_card: _SvgCandidateCard | None = None
        self._workers: list[_SvgGenWorker] = []   # 생성 중일 때만 항목이 있음
        self._pending = 0          # 아직 안 끝난 워커 수
        self._gen_errors: list[str] = []
        lay = QVBoxLayout(self)

        # [2026-08-19 Stage 6] 목업("Mermaid 가져오기 Studio v2.0")의 시각 언어만 차용해
        # 입력카드+툴바 구성을 `_MermaidDialog`와 통일(2칸 분리 등 구조 자체는 그대로 —
        # deep-interview 확정: "시각 언어만 차용"). 입력칸(위, 밝게 고정) + 첨부·모델·생성
        # 툴바(아래) 카드 하나로 묶는다.
        dark = bool(getattr(self.parent(), "_dark", True))
        prompt_frame = QFrame(self)
        prompt_frame.setObjectName("svgPromptCard")
        prompt_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        _prompt_bg = '#e7e0d6' if dark else 'palette(base)'
        _prompt_normal_qss = (
            "QFrame#svgPromptCard { border:1px solid rgba(128,128,128,90); border-radius:8px; "
            f"background:{_prompt_bg}; }}"
        )
        # [2026-08-20 피드백] 드래그 오버 중엔 이 카드 테두리를 코랄 점선으로(Mermaid
        # 창과 동일 관례) — "드래그해도 되는 느낌이 없다".
        _prompt_active_qss = (
            f"QFrame#svgPromptCard {{ border:2px dashed {_ACCENT_CORAL}; border-radius:8px; "
            f"background:{_prompt_bg}; }}"
        )
        prompt_frame.setStyleSheet(_prompt_normal_qss)
        self._set_image_drop_frame(prompt_frame, _prompt_normal_qss, _prompt_active_qss)
        prompt_frame_lay = QVBoxLayout(prompt_frame)
        prompt_frame_lay.setContentsMargins(0, 0, 0, 0)
        prompt_frame_lay.setSpacing(0)

        label_row = QHBoxLayout()
        label_row.setContentsMargins(10, 8, 10, 0)
        label_row.addWidget(QLabel("생성할 대상(예: BNC 커넥터 아이콘):", self))
        prompt_frame_lay.addLayout(label_row)

        self._prompt_edit = QLineEdit(prompt_frame)
        self._prompt_edit.setPlaceholderText("예: 야기 안테나 아이콘")
        self._prompt_edit.setAcceptDrops(False)   # 드롭을 다이얼로그(dropEvent)로 넘김
        self._prompt_edit.installEventFilter(self)   # Ctrl+V 이미지 첨부
        self._prompt_edit.returnPressed.connect(self._on_generate_clicked)
        self._prompt_edit.setFrame(False)
        self._prompt_edit.setStyleSheet(
            "QLineEdit { background:transparent; padding:4px 10px; " +
            ("color:#241a15; }" if dark else "}")
        )
        prompt_frame_lay.addWidget(self._prompt_edit)

        toolbar_widget = QWidget(prompt_frame)
        toolbar_widget.setObjectName("svgPromptToolbar")
        toolbar_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        toolbar_widget.setStyleSheet(
            "QWidget#svgPromptToolbar { background:palette(button); "
            "border-top:1px solid rgba(128,128,128,90); "
            "border-bottom-left-radius:8px; border-bottom-right-radius:8px; }"
        )
        toolbar_lay = QHBoxLayout(toolbar_widget)
        toolbar_lay.setContentsMargins(8, 6, 8, 6)
        toolbar_lay.setSpacing(8)

        self._attach_btn = QToolButton(toolbar_widget)
        self._attach_btn.setIcon(_act_icon("attach"))
        self._attach_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._attach_btn.setText("이미지 첨부")
        self._attach_btn.setToolTip("이미지 첨부<br>· 드래그 앤 드롭<br>· Ctrl+V 붙여넣기")
        self._attach_btn.clicked.connect(self._browse_image)
        toolbar_lay.addWidget(self._attach_btn)
        toolbar_lay.addWidget(self._build_image_chip(toolbar_widget))
        toolbar_lay.addStretch(1)

        toolbar_lay.addWidget(QLabel(f"GPT ({gw.TEXT_RECOMMEND_1}):", toolbar_widget))
        self._gpt_count = QComboBox(toolbar_widget)
        self._gpt_count.addItems([str(i) for i in range(self._MAX_PER_MODEL + 1)])
        self._gpt_count.setCurrentIndex(1)   # 기본 1개(Stage 1과 동일 체감 유지)
        self._gpt_count.setStyleSheet(_ROUNDED_COMBO_QSS)
        toolbar_lay.addWidget(self._gpt_count)
        toolbar_lay.addSpacing(4)
        toolbar_lay.addWidget(QLabel(f"Gemini ({gw.TEXT_RECOMMEND_2}):", toolbar_widget))
        self._gemini_count = QComboBox(toolbar_widget)
        self._gemini_count.addItems([str(i) for i in range(self._MAX_PER_MODEL + 1)])
        self._gemini_count.setCurrentIndex(1)
        self._gemini_count.setStyleSheet(_ROUNDED_COMBO_QSS)
        toolbar_lay.addWidget(self._gemini_count)

        # [2026-08-20 피드백] 이 창엔 설정 진입점이 아예 없었다 — Mermaid 창과 같은 자리
        # (모델 관련 컨트롤 옆)에 추가(모델 목록 자체가 없어 새로고침할 것은 없음).
        self._settings_btn = QToolButton(toolbar_widget)
        self._settings_btn.setIcon(_act_icon("settings"))
        self._settings_btn.setToolTip("AI 게이트웨이 설정(주소·키·연결 테스트)")
        self._settings_btn.clicked.connect(self._open_gateway_settings)
        toolbar_lay.addWidget(self._settings_btn)

        self._gen_btn = QToolButton(toolbar_widget)
        self._gen_btn.setIcon(_act_icon("generate"))
        self._gen_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._gen_btn.setText("생성")
        self._gen_btn.setToolTip("생성 (Enter)")
        self._gen_btn.clicked.connect(self._on_generate_clicked)
        self._gen_btn.setStyleSheet(_CORAL_BTN_QSS)
        toolbar_lay.addWidget(self._gen_btn)

        prompt_frame_lay.addWidget(toolbar_widget)
        lay.addWidget(prompt_frame)

        self._progress = _GenProgressRow(self)
        lay.addWidget(self._progress)

        # 최대 10장까지 나올 수 있어(모델당 5개×2) 고정 QHBoxLayout만으론 다이얼로그 폭을
        # 넘친다 — 가로 스크롤 영역으로 감싼다(카드 자체 크기·스타일은 무변경).
        self._candidates_row = QHBoxLayout()
        self._candidates_row.addStretch(1)
        candidates_container = QWidget(self)
        candidates_container.setLayout(self._candidates_row)
        candidates_scroll = QScrollArea(self)
        candidates_scroll.setWidget(candidates_container)
        candidates_scroll.setWidgetResizable(True)
        candidates_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        candidates_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        candidates_scroll.setFixedHeight(176)   # 카드 156 + 여유(체크박스 추가로 카드가 커짐)
        candidates_scroll.setFrameShape(QFrame.Shape.NoFrame)
        lay.addWidget(candidates_scroll)

        hint_row = QHBoxLayout()
        self._hint_label = QLabel("후보를 클릭해 선택하세요.", self)
        self._hint_label.setStyleSheet("color:#8a8a8a; font-size:11px;")
        self._hint_label.setVisible(False)
        hint_row.addWidget(self._hint_label)
        hint_row.addStretch(1)
        self._save_symbols_btn = QToolButton(self)
        self._save_symbols_btn.setIcon(_act_icon("save"))
        self._save_symbols_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._save_symbols_btn.setText("내 심볼로 저장")
        self._save_symbols_btn.setToolTip("체크한 후보를 내 심볼 팔레트에 한꺼번에 저장")
        self._save_symbols_btn.setEnabled(False)
        self._save_symbols_btn.clicked.connect(self._on_save_to_symbols_clicked)
        hint_row.addWidget(self._save_symbols_btn)
        lay.addLayout(hint_row)

        self._btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                      | QDialogButtonBox.StandardButton.Cancel, self)
        self._ok_btn = self._btns.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)
        # [2026-08-19 Stage 6] 목업 시각 언어 차용 — "OK" 대신 결과를 명시하는 라벨.
        # 호출부가 삽입/대체 중 실제로 일어날 일을 넘겨준다(host_fileio.py는 기본값
        # "확인 (도형 삽입)" 그대로, host_context.py의 대체 진입점만 다르게 넘김).
        self._ok_btn.setText(confirm_label)
        self._ok_btn.setStyleSheet(_CORAL_BTN_QSS)
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        lay.addWidget(self._btns)

    def selected_svg(self) -> str:
        return self._selected_card.svg_text() if self._selected_card else ""

    def closeEvent(self, e):
        # 생성 중(워커가 하나라도 돎)에는 닫지 않는다 — `_MermaidDialog.closeEvent`와 같은
        # 이유(2026-08-19).
        if any(w.isRunning() for w in self._workers):
            e.ignore()
            return
        super().closeEvent(e)

    def eventFilter(self, obj, event):
        if obj is self._prompt_edit and event.type() == QEvent.Type.KeyPress:
            if self._maybe_intercept_paste_image(event):
                return True
        return super().eventFilter(obj, event)

    def _open_gateway_settings(self):
        """`_AIGatewaySettingsDialog`를 이 SVG 창의 자식 모달로 연다(2026-08-20 — Mermaid
        창과 동일한 진입점을 SVG 창에도 추가, 이전엔 이 창에 설정 진입점이 없었다).
        모델 드롭다운이 없어(개수 선택뿐) 닫힌 뒤 다시 채울 것도 없다."""
        _AIGatewaySettingsDialog(self).exec()

    def _requested_jobs(self) -> list[str]:
        """모델별 개수 드롭다운 → 호출할 모델 목록(개수만큼 반복) — 예: GPT 2·Gemini 1이면
        [gpt, gpt, gemini]. 워커 하나가 이 목록의 항목 하나씩을 맡는다."""
        n_gpt = int(self._gpt_count.currentText())
        n_gemini = int(self._gemini_count.currentText())
        return [gw.TEXT_RECOMMEND_1] * n_gpt + [gw.TEXT_RECOMMEND_2] * n_gemini

    def _on_generate_clicked(self):
        """2026-08-19 Stage 2 — 요청한 후보 전부를 워커 하나씩(`_SvgGenWorker`)으로
        동시에 시작해 완전 병렬 호출한다. 완료 처리는 `_on_candidate_ready`(후보 도착마다)
        ·`_on_one_worker_finished`(워커 하나가 끝날 때마다 `_pending`을 줄이고, 0이 되면
        전체 완료 처리 — 옛 "워커 하나=전체"였던 Stage 1의 finally 블록 역할을 카운터로
        대신한다)로 나뉜다."""
        subject = self._prompt_edit.text().strip()
        image = self._attached_image
        if not subject and image is None:
            QMessageBox.information(self, "AI SVG 에셋 생성",
                                    "먼저 생성할 대상을 입력하거나 이미지를 첨부하세요.")
            return
        jobs = self._requested_jobs()
        if not jobs:
            QMessageBox.information(self, "AI SVG 에셋 생성", "모델별 개수를 하나 이상 선택하세요.")
            return
        key = gw.resolve_api_key()
        if not key:
            QMessageBox.warning(self, "AI SVG 에셋 생성",
                                "게이트웨이 API 키가 없습니다. 먼저 설정해 주세요.")
            return
        base_url = gw.resolve_base_url()
        self._clear_candidates()
        self._gen_errors = []
        self._gen_btn.setEnabled(False)
        self._btns.setEnabled(False)
        self._gpt_count.setEnabled(False)
        self._gemini_count.setEnabled(False)
        self._progress.start("SVG 생성 중")
        self._pending = len(jobs)
        self._workers = []
        for model in jobs:
            w = _SvgGenWorker(key, subject, model, base_url, image, self)
            w.candidate.connect(self._on_candidate_ready)
            w.model_failed.connect(self._on_model_failed)
            w.finished.connect(self._on_one_worker_finished)
            self._workers.append(w)
        for w in self._workers:   # 전부 만든 뒤에 전부 시작 — 동시 발사
            w.start()

    def _on_candidate_ready(self, model_used, svg_text):
        self._add_candidate(model_used, svg_text)
        if len(self._candidates) == 1:
            self._hint_label.setVisible(True)
            self._pick_card(self._candidates[0][0])   # 첫 성공 후보를 기본 선택

    def _on_model_failed(self, model, err):
        self._gen_errors.append(f"{model}: {err}")

    def _on_one_worker_finished(self):
        self._pending -= 1
        if self._pending > 0:
            return   # 아직 다른 워커가 도는 중 — 전체 완료 처리는 마지막 하나가 담당
        self._progress.stop()
        self._gen_btn.setEnabled(True)
        self._btns.setEnabled(True)
        self._gpt_count.setEnabled(True)
        self._gemini_count.setEnabled(True)
        if self._gen_errors and not self._candidates:
            QMessageBox.warning(self, "AI SVG 에셋 생성",
                                "생성에 실패했습니다:\n" + "\n".join(self._gen_errors))
        elif self._gen_errors:
            QMessageBox.warning(self, "AI SVG 에셋 생성",
                                "일부 후보가 실패했습니다(성공한 후보만 표시):\n"
                                + "\n".join(self._gen_errors))
        self._workers = []

    def _clear_candidates(self):
        for card, _svg, _model in self._candidates:
            card.setParent(None)
            card.deleteLater()
        self._candidates = []
        self._selected_card = None
        self._ok_btn.setEnabled(False)
        self._hint_label.setVisible(False)
        self._save_symbols_btn.setEnabled(False)

    def _add_candidate(self, model_used: str, svg_text: str):
        pm = _render_svg_candidate_pixmap(svg_text, 100)
        card = _SvgCandidateCard(model_used, svg_text, pm, self._pick_card, self)
        card._save_check.stateChanged.connect(self._refresh_save_symbols_enabled)
        self._candidates_row.insertWidget(self._candidates_row.count() - 1, card)
        self._candidates.append((card, svg_text, model_used))

    def _pick_card(self, card: _SvgCandidateCard):
        for c, _svg, _model in self._candidates:
            c.set_selected(c is card)
        self._selected_card = card
        self._ok_btn.setEnabled(True)

    def _refresh_save_symbols_enabled(self, *_args):
        self._save_symbols_btn.setEnabled(
            any(c.is_checked_for_save() for c, _svg, _model in self._candidates))

    def _checked_for_save_candidates(self) -> list[tuple[str, str]]:
        """체크박스로 고른 (svg 텍스트, 사용된 모델) 목록 — 클릭 단일선택(`_selected_card`)
        과는 무관한 별개 선택."""
        return [(svg, model) for c, svg, model in self._candidates if c.is_checked_for_save()]

    def _on_save_to_symbols_clicked(self):
        """2026-08-19 Stage 4 — 체크한 후보 전부를 내 심볼 팔레트에 한 번에 등록한다.
        실제 등록(SVG→아이템 변환·썸네일 렌더·`symbol_library` 기록)은 이 다이얼로그가
        아니라 부모 `CanvasWindow`(host_fileio.py 믹스인)가 한다 — `host_dialogs.py`는
        순환 임포트를 피하려는 잎(leaf) 모듈이라 `host_selection.py`(썸네일 렌더 등)를
        직접 import할 수 없다(모듈 docstring 참조). `getattr`로 부모의 메서드를 이름으로만
        호출하는 방식(`_MermaidDialog`가 `self.parent()._dark`를 읽는 것과 같은 관례)으로
        결합을 느슨하게 유지한다."""
        entries = self._checked_for_save_candidates()
        if not entries:
            return
        folder_dlg = _SaveToSymbolsFolderDialog(self)
        if folder_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        folder = folder_dlg.chosen_folder()
        if folder and folder not in symbol_library.load_folders():
            symbol_library.create_folder(folder)
        parent = self.parent()
        save_fn = getattr(parent, "_save_svg_candidates_to_symbols", None)
        if save_fn is None:
            QMessageBox.warning(self, "내 심볼로 저장",
                                "지금 창에서는 심볼 저장을 사용할 수 없습니다.")
            return
        subject = self._prompt_edit.text().strip()
        saved = save_fn(entries, subject, folder)
        QMessageBox.information(self, "내 심볼로 저장", f"{saved}개를 내 심볼에 저장했습니다.")

