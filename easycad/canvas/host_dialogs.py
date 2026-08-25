"""CanvasWindow이 띄우는 입력 다이얼로그 모음 — 용지 크기/표제란 필드/표 크기/
케이블 채번 접두사/Mermaid 붙여넣기.

2026-08-02 host.py(3635줄) 분할분. host_fileio.py·host_context.py 믹스인이 이 모듈에서
다이얼로그 클래스를 가져다 쓴다. 순환 임포트를 피하려고 host.py·믹스인을 임포트하지 않는
잎(leaf) 모듈이다.
"""
import html
import io
import os
import re
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
    QKeySequenceEdit,
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
    _clipboard_pixmap, _act_icon, _ACCENT_CORAL, _ICON_COLOR, _current_icon_color,
    _MERMAID_SHAPE_ITEM, _border_attach,
)
from easycad.fileio.pdf_export import (
    export_pdf, PAGE_SIZES, render_preview, _list_title_frames, _centered_target_rect,
    _DEFAULT_MARGINS_MM,
)
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document, load_document_layers
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)
from easycad.fileio.svg_import import parse_svg_string
from easycad.fileio import symbol_library
from easycad.ai import gateway as gw
from easycad.ai.text_to_svg import generate_svg, build_prompt, build_image_prompt
from easycad.canvas import shortcuts


# ---------------------------------------------------------------------------
# [Phase 4] 표제란 다이얼로그 — 삽입 시 용지 선택 / 더블클릭 시 필드 편집
# ---------------------------------------------------------------------------
_ORIENTS = [("landscape", "가로"), ("portrait", "세로")]


_ROUNDED_COMBO_QSS = (
    "QComboBox { border:1px solid rgba(128,128,128,90); border-radius:8px; "
    "padding:6px 10px; }"
    "QComboBox:hover { border-color:rgba(128,128,128,150); }"
    "QComboBox::drop-down { border:none; width:24px; }"
    "QComboBox QAbstractItemView { border:1px solid rgba(128,128,128,90); "
    "border-radius:6px; padding:2px; outline:0; }"
)

# [2026-08-20 피드백] 다이얼로그 섹션 캡션("Mermaid 코드", "미리보기" 등)을 본문 라벨과
# 구분되는 "제목"으로 보이게 — 굵기+크기만 올린다(Qt 스타일시트는 letter-spacing/
# text-transform 미지원이라 그 축은 배제, 색은 팔레트 기본 유지 — 코랄은 상태 전용이라는
# 기존 규칙(easy-cad.md) 유지).
_SECTION_TITLE_QSS = "font-weight:600; font-size:13px;"

# [2026-08-20 피드백] 연결 테스트 결과(성공/실패)를 색으로 구분 — "연결 잘 되면 좋은 일"
# 이라는 요청대로 성공은 초록, 실패는 빨강(둘 다 코랄 accent와 겹치지 않는 별도 색상,
# 코랄은 이 앱에서 "선택/액션" 전용이라는 기존 규칙 유지).
_STATUS_OK_COLOR = "#22c55e"
_STATUS_FAIL_COLOR = "#e5484d"


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
    """[§8 항목14, 2026-08-07] 내보내기 — 옛 "전체"/"선택영역" 별도 메뉴 2개를 이 다이얼로그
    하나로 통합. 전체/선택 라디오·용지크기·방향을 고르면 그 즉시 라이브 미리보기가 다시 렌더된다
    (deep-interview 확정 — 왕복 다이얼로그 대신 옵션·미리보기를 한 화면에). 씬에 표제란/용지틀이
    있고 "전체 도면"을 고른 상태면 그 프레임이 이미 용지 크기·방향을 정해둔 것이라 용지크기·방향
    컨트롤을 잠그고 프레임 값을 그대로 반영한다(프레임은 크롭 경계+출력 페이지 크기를 정하는
    것일 뿐 내부 도형의 실척 mm을 보장하지 않는다는 걸 사용자와 코드로 확인 후 결정 — 다른
    크기를 원하면 프레임 자체를 다시 만듦, 기존 UX와 일관).

    [다중 페이지 지원, 2026-08-14] 씬에 프레임이 2개 이상이면 "전체 도면" 옆에 드롭다운이
    자동으로 나타나 어느 프레임을 낼지 고른다(deep-interview 확정 — 새 라디오 옵션 대신
    기존 "전체 도면"의 자연스러운 확장). 프레임이 0~1개면 지금까지와 완전히 동일(드롭다운
    자체가 안 뜸, 무회귀).

    [내보내기 통합, 2026-08-20 실사용 피드백] PDF 전용이던 것을 PDF/PNG/PNG(투명배경)/SVG
    형식 콤보로 확장(Lucid의 "File format" 드롭다운과 같은 자리) — 우클릭 메뉴·File 메뉴
    두 진입점이 이 다이얼로그 하나를 공유하고, `default_format`/`default_selection_only`로
    진입점별 초기값만 다르게 준다(로직은 하나, 사용자가 안에서 서로 반대쪽으로 바꿀 수도 있음)."""

    _FORMAT_OPTIONS = (
        ("PDF", "pdf"), ("PNG", "png"), ("PNG (투명 배경)", "png_transparent"), ("SVG", "svg"))
    _FORMAT_OK_LABEL = {
        "pdf": "PDF로 저장…", "png": "PNG로 저장…",
        "png_transparent": "PNG로 저장…", "svg": "SVG로 저장…"}

    def __init__(self, parent, scene, has_selection: bool,
                default_format: str = "pdf", default_selection_only: bool = False):
        super().__init__(parent)
        self.setWindowTitle("내보내기")
        self._scene = scene
        self._frames = _list_title_frames(scene)

        opts = QVBoxLayout()
        self._format_cb = QComboBox(self)
        for label, key in self._FORMAT_OPTIONS:
            self._format_cb.addItem(label, key)
        fidx = self._format_cb.findData(default_format)
        self._format_cb.setCurrentIndex(fidx if fidx >= 0 else 0)
        form0 = QFormLayout()
        form0.addRow("형식", self._format_cb)
        opts.addLayout(form0)

        self._rb_all = QRadioButton("전체 도면")
        self._rb_sel = QRadioButton("선택 영역")
        self._rb_sel.setEnabled(has_selection)
        if default_selection_only and has_selection:
            self._rb_sel.setChecked(True)
        else:
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

        # [여백 상하좌우 개별 지정, 2026-08-23 실사용 피드백] 기존엔 margin_mm이 코드에만
        # 있고 다이얼로그가 값을 안 넘겨 항상 10mm 균등 고정·UI 비노출이었다 — 4개 숫자입력으로
        # 노출(전체 도면·선택 영역 둘 다 적용, 표제란 활성 시엔 크기/방향과 같은 이유로 잠금).
        margin_grid = QGridLayout()
        top_mm, right_mm, bottom_mm, left_mm = _DEFAULT_MARGINS_MM
        self._margin_top_sb = QSpinBox(self)
        self._margin_right_sb = QSpinBox(self)
        self._margin_bottom_sb = QSpinBox(self)
        self._margin_left_sb = QSpinBox(self)
        for sb, v in ((self._margin_top_sb, top_mm), (self._margin_right_sb, right_mm),
                     (self._margin_bottom_sb, bottom_mm), (self._margin_left_sb, left_mm)):
            sb.setRange(0, 100)
            sb.setValue(int(v))
            sb.setSuffix(" mm")
        margin_grid.addWidget(QLabel("여백", self), 0, 0)
        margin_grid.addWidget(QLabel("위", self), 0, 1)
        margin_grid.addWidget(self._margin_top_sb, 0, 2)
        margin_grid.addWidget(QLabel("아래", self), 0, 3)
        margin_grid.addWidget(self._margin_bottom_sb, 0, 4)
        margin_grid.addWidget(QLabel("왼쪽", self), 1, 1)
        margin_grid.addWidget(self._margin_left_sb, 1, 2)
        margin_grid.addWidget(QLabel("오른쪽", self), 1, 3)
        margin_grid.addWidget(self._margin_right_sb, 1, 4)
        opts.addLayout(margin_grid)

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
        self._ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(row)
        root.addWidget(btns)

        self._format_cb.currentIndexChanged.connect(self._refresh_ok_label)
        self._rb_all.toggled.connect(self._refresh)
        self._size_cb.currentIndexChanged.connect(self._refresh)
        self._orient_cb.currentIndexChanged.connect(self._refresh)
        self._frame_cb.currentIndexChanged.connect(self._refresh)   # [다중 페이지]
        for sb in (self._margin_top_sb, self._margin_right_sb,
                  self._margin_bottom_sb, self._margin_left_sb):
            sb.valueChanged.connect(self._refresh)
        self._refresh_ok_label()
        self._refresh()

    def _format(self) -> str:
        return self._format_cb.currentData()

    def _refresh_ok_label(self):
        self._ok_btn.setText(self._FORMAT_OK_LABEL[self._format()])

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

    def _margins_mm(self) -> tuple:
        return (self._margin_top_sb.value(), self._margin_right_sb.value(),
               self._margin_bottom_sb.value(), self._margin_left_sb.value())

    def _refresh(self):
        frame = self._current_frame()
        active = (not self._selection_only()) and frame is not None
        self._size_cb.setEnabled(not active)
        self._orient_cb.setEnabled(not active)
        for sb in (self._margin_top_sb, self._margin_right_sb,
                  self._margin_bottom_sb, self._margin_left_sb):
            sb.setEnabled(not active)
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
            margins_mm=self._margins_mm(),
        )
        if pixmap is None:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("출력할 내용이 없습니다.")
        else:
            self._preview.setText("")
            self._preview.setPixmap(pixmap)

    def result_options(self) -> dict:
        fmt = self._format()
        return {
            "selection_only": self._selection_only(),
            "page": self._size_cb.currentData(),
            "orientation": self._orient_cb.currentData(),
            "frame": self._current_frame() if not self._selection_only() else None,
            "format": "png" if fmt == "png_transparent" else fmt,
            "transparent": fmt == "png_transparent",
            "margins_mm": self._margins_mm(),
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

    def _build_attach_button(self, parent) -> QToolButton:
        """이미지 첨부 버튼 — 클립 아이콘 대신 "+ 새 폴더" 버튼(`host_ui.py`
        `_add_folder_btn`)과 같은 정사각 "+" 글리프로(2026-08-20 피드백: "클립 아이콘이
        작아서 눌러서 불러오거나 드래그된다는 느낌이 안 난다" — 새 아이콘을 그리는 대신
        앱이 이미 쓰던 "+" 버튼 스타일을 재사용, 다만 이 버튼은 헤더 안이 아니라 독립
        툴바 안이라 눌러볼 수 있는 경계가 보이도록 테두리를 추가했다)."""
        btn = QToolButton(parent)
        btn.setText("+")
        btn.setAutoRaise(True)
        btn.setFixedSize(QSize(28, 28))
        col = _current_icon_color().name()
        btn.setStyleSheet(
            f"QToolButton {{ color:{col}; font-weight:700; font-size:18px; "
            "border:1px solid rgba(128,128,128,90); border-radius:6px; }"
            "QToolButton:hover { background:rgba(128,128,128,40); }"
        )
        btn.setToolTip("이미지 첨부<br>· 드래그 앤 드롭<br>· Ctrl+V 붙여넣기")
        btn.clicked.connect(self._browse_image)
        return btn

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


_MODEL_VERSION_RE = re.compile(r"^(?:gemini|gpt)-(\d+(?:\.\d+)*)", re.IGNORECASE)


def _model_version_key(name: str) -> tuple:
    """이름 맨 앞 버전 번호("gemini-3.5-flash-lite" → (3, 5))를 비교 가능한 튜플로.
    버전을 못 찾으면 (0,)으로 가장 낮게 취급."""
    m = _MODEL_VERSION_RE.match(name)
    if not m:
        return (0,)
    return tuple(int(p) for p in m.group(1).split("."))


def _pick_fallback_model(candidates: list[str]) -> str | None:
    """추천 모델이 은퇴돼 목록에 없을 때 같은 계열(`candidates`) 안에서 대신 고를 모델.

    [2026-08-21 실사용 확정] "lite"가 붙은 이름 중 버전 번호가 가장 높은 것을
    최우선으로 한다 — 실측(gemini-3.5-flash-lite가 gpt-5.6 비-lite 계열 전체보다
    저렴·안정적으로 우수)을 일반화한 휴리스틱이다. **주의: 이건 확신이 아니라
    추측이다** — "lite"라는 이름이 실제로 저비용·양호품질을 뜻하는지는 이 게이트웨이의
    지금까지 관찰 사례로 유추한 것일 뿐, 새로 나오는 모델의 실제 성능·비용은 실측
    전까진 알 수 없다(모델 목록 API에 가격 정보가 없다 — 확인함). lite 후보가
    하나도 없으면 알파벳 순 첫 항목으로 폴백(기존 안전망 — 이것도 품질 보장은
    아니고 "완전히 죽은 모델에 머물지 않는다"는 최소 보장일 뿐)."""
    if not candidates:
        return None
    lite = [m for m in candidates if "lite" in m.lower()]
    if lite:
        return max(lite, key=_model_version_key)
    return sorted(candidates)[0]


def _fill_model_combo_grouped(combo: QComboBox, models: list, default_model: str,
                              prev: str | None = None, none_option: str | None = None):
    """Gemini·GPT 그룹 헤더가 있는 드롭다운으로 채운다 — 원래 `_MermaidDialog`
    전용이던 로직을 2026-08-20(SVG 창의 모델 슬롯 2개가 각자 실제 모델을 고를 수 있게
    확장하며)에 모듈 함수로 추출해 두 다이얼로그가 공유한다. 헤더 행은
    `QStandardItem.setEnabled(False)`로 선택 불가. `models`가 비어 있으면(조회 전·실패
    시) 추천 둘만으로 조용히 폴백. `prev`가 새 목록에도 있으면 유지, 없으면
    `default_model`(호출부가 정하는 이 콤보의 기본 모델 — Mermaid는 `TEXT_RECOMMEND_
    MERMAID` 고정, SVG는 슬롯 A/B가 `TEXT_RECOMMEND_1`/`_2`를 각각 쓴다).

    `none_option`(2026-08-25 재작업, SVG 슬롯 B 전용): 주어지면 맨 위에 그 라벨의
    선택 가능한 항목을 하나 더 두되 UserRole 데이터는 설정하지 않아(`_combo_selected_
    model_or_none`이 None으로 읽는다) "이 슬롯을 안 쓴다"는 뜻이 되게 한다. `prev`가
    None이면(최초 호출이거나, 직전에도 미선택 상태였거나 둘 다) `default_model` 대신
    이 항목을 기본 선택한다 — Mermaid·SVG 슬롯 A는 `none_option`을 안 넘기므로 기존
    동작 그대로다.

    [2026-08-21 실사용 버그 수정] 예전엔 실제 목록이 도착해도 추천 상수(r1/r2)를 항상
    풀에 강제로 합쳐 넣었다(`set(models) | {r1, r2}`) — 그 결과 게이트웨이가 추천
    모델을 은퇴시켜도(`gpt-5.4-mini` 404) UI가 존재하지 않는 모델을 계속 기본 선택한
    채로 남았다. 이제 `models`가 실제로 도착했을 때는 그 목록만 쓰고, 추천값이 그
    안에 없으면 같은 계열(gpt/gemini) 안에서 `_pick_fallback_model`로 대체 기본값을
    고른다 — 다음에 또 추천 모델이 은퇴돼도 조용히 죽은 모델에 머물지 않는다."""
    r1, r2 = gw.TEXT_RECOMMEND_1, gw.TEXT_RECOMMEND_2
    # [2026-08-21] `default_model`을 항상 포함시킨다 — Mermaid는 이제 `TEXT_RECOMMEND_
    # MERMAID`(r1/r2 어느 쪽도 아님)를 쓰므로, 목록 도착 전 placeholder 풀이 r1/r2만
    # 보여주면 정작 이 콤보의 기본값 자체가 빠지는 문제가 생긴다. SVG(default_model이
    # 이미 r1이나 r2)는 집합이 그대로라 동작 무변화.
    pool = sorted(set(models)) if models else sorted({default_model, r1, r2})
    gemini_models = sorted(m for m in pool if "gemini" in m.lower())
    gpt_models = sorted(m for m in pool if "gpt" in m.lower())

    std_model = QStandardItemModel(combo)

    if none_option is not None:
        std_model.appendRow(QStandardItem(none_option))   # UserRole 미설정 = None

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
    combo.setModel(std_model)

    if none_option is not None and prev is None:
        combo.setCurrentIndex(0)   # "(미선택)" 항목 — 최초 호출 또는 직전에도 미선택
        return

    target = prev if prev in pool else default_model
    if target not in pool:
        # default_model도(추천값이 은퇴돼) pool에 없으면 같은 계열 우선으로 대체.
        same_vendor = gpt_models if "gpt" in default_model.lower() else gemini_models
        fallback_pool = same_vendor or gemini_models or gpt_models
        target = _pick_fallback_model(fallback_pool)
    default_row = next(
        (i for i in range(std_model.rowCount())
         if std_model.item(i).data(Qt.ItemDataRole.UserRole) == target), -1)
    combo.setCurrentIndex(default_row if default_row >= 0 else
                          (1 if std_model.rowCount() > 1 else -1))


def _combo_selected_model(combo: QComboBox, fallback: str) -> str:
    idx = combo.currentIndex()
    data = combo.itemData(idx, Qt.ItemDataRole.UserRole) if idx >= 0 else None
    return data or fallback


def _combo_selected_model_or_none(combo: QComboBox) -> str | None:
    """`_combo_selected_model`과 달리 폴백하지 않는다 — `none_option` 항목(UserRole
    미설정이라 데이터가 None)이 선택돼 있으면 그대로 None을 돌려줘 "미선택" 상태를
    구분할 수 있게 한다(SVG 창 모델 B 전용, 2026-08-25 재작업)."""
    idx = combo.currentIndex()
    return combo.itemData(idx, Qt.ItemDataRole.UserRole) if idx >= 0 else None


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


_ORPHANED_WORKERS: set[QThread] = set()   # 아래 _detach_worker가 채움 — GC 방지용 임시 보관


def _detach_worker(worker: QThread | None) -> None:
    """다이얼로그가 닫힐 때 아직 도는 워커(`_ModelListWorker`/`_MermaidGenWorker`/
    `_SvgGenWorker`)를 죽은 다이얼로그와 분리해 크래시 없이 백그라운드에서 마저 끝나게
    한다(2026-08-23, 실사용 버그 — X·Cancel을 열자마자 누르면 안 닫히거나(모델목록
    조회를 "생성 중"과 같은 걸로 취급해 닫기 자체를 막던 방어코드) Cancel로 강제로
    닫으면 `reject()`가 그 방어코드(`closeEvent`)를 거치지 않고 곧장 다이얼로그를 없애
    parent로 물려있던 워커까지 함께 파괴돼(살아있는 QThread 파괴) 프로그램이 죽던 문제).
    닫기는 무엇이 돌든 항상 즉시 허용하고, 결과 시그널 연결을 끊어(결과는 버림) 워커가
    끝나도 죽은 다이얼로그를 건드리지 않게 하는 쪽으로 설계를 바꿨다."""
    if worker is None or not worker.isRunning():
        return
    try:
        worker.disconnect()   # 다이얼로그 쪽 슬롯 연결 전부 해제 — 결과는 버려짐
    except TypeError:
        pass   # 연결된 슬롯이 이미 없으면 PyQt6이 TypeError를 던짐(무해)
    worker.setParent(None)   # 다이얼로그가 사라져도 함께 파괴되지 않도록 분리
    _ORPHANED_WORKERS.add(worker)

    def _reap():
        _ORPHANED_WORKERS.discard(worker)
        worker.deleteLater()
    worker.finished.connect(_reap)


def _build_mermaid_preview_scene(text: str, pen_color: QColor | None = None) -> QGraphicsScene | None:
    """Mermaid 코드 → 미리보기용 QGraphicsScene(§8 항목23 Stage 5, 2026-08-19 —
    2026-08-21에 `_render_mermaid_preview_pixmap`에서 씬 조립 부분만 뽑아냈다: 정적
    픽스맵 렌더(`_render_mermaid_preview_pixmap`)와 실시간 휠줌/드래그팬 뷰
    (`_MermaidPreviewView`) 둘 다 같은 씬을 필요로 하므로). 실제 삽입 경로
    (`host_fileio._build_mermaid`/`_make_mermaid_node`/`_make_mermaid_edge`)와 똑같은
    파서(`parse_mermaid`)+배치(`layout_positions`)+도형매핑(`_MERMAID_SHAPE_ITEM`)+
    부착점(`_border_attach`)+직교라우팅(`_PolyArrowItem.build_elbow`)을 그대로 재사용해
    미리보기와 실제 삽입 결과가 어긋나지 않게 한다 — SVG 후보 미리보기
    (`_render_svg_candidate_pixmap`)와 같은 원칙. host_fileio.py 자체를 import하면
    이 잎 모듈의 순환 임포트 제약을 어기므로, host_fileio가 이미 재사용 가능한 형태로
    분리해둔 `host_widgets._MERMAID_SHAPE_ITEM`/`_border_attach`만 가져다 쓴다. 파싱
    실패·빈 입력이면 None(호출부가 안내 문구를 보여준다).

    `pen_color`(2026-08-21 실사용 피드백 — "도형이 너무 어두워서 잘 안보임") — 기본은
    `_ICON_COLOR`지만 `_render_svg_candidate_pixmap`과 같은 이유로 다크 테마 카드
    배경에서 대비가 약하다. 호출부(`_MermaidDialog`)가 테마에 맞는 밝은 색을 넘긴다."""
    try:
        graph = parse_mermaid(text)
    except MermaidError:
        return None
    w, h = 120.0, 56.0
    pos = layout_positions(graph, node_w=w, node_h=h)
    if not pos:
        return None

    scene = QGraphicsScene()
    pen = QPen(pen_color or _ICON_COLOR, 1.5)
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
        arr = _PolyArrowItem(pen_color or _ICON_COLOR, 1, e.arrow)
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

    return scene


def _render_mermaid_preview_pixmap(text: str, target_size: QSize,
                                    pen_color: QColor | None = None) -> QPixmap | None:
    """`_build_mermaid_preview_scene`을 target_size 픽스맵으로 래스터화(정적 이미지가
    필요한 자리 — 지금은 pytest 순수함수 테스트가 이 계약을 지킨다). 라이브 미리보기
    패널 자체는 더 이상 이 함수를 쓰지 않고 `_MermaidPreviewView`가 씬을 직접 든다
    (2026-08-21, 클릭-확대창 대신 패널 안 휠줌/드래그팬으로 교체하며)."""
    scene = _build_mermaid_preview_scene(text, pen_color)
    if scene is None:
        return None
    pm = QPixmap(target_size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = 10.0
    target = QRectF(margin, margin,
                    target_size.width() - 2 * margin, target_size.height() - 2 * margin)
    source = scene.itemsBoundingRect()
    if source.width() > 0 and source.height() > 0:
        # [2026-08-21 실사용 피드백] "가로든 세로든 중앙에" — `render(target, source,
        # KeepAspectRatio)`는 남는 여백을 target 왼쪽/위로 몰아붙이는 Qt 기본 동작(가운데
        # 정렬이 아님, `pdf_export._centered_target_rect` 도입 때 실측으로 이미 확인된
        # 함정과 같은 종류) — 같은 헬퍼를 재사용해 target을 미리 중앙 사각형으로 좁힌다.
        scene.render(p, _centered_target_rect(target, source), source,
                     Qt.AspectRatioMode.KeepAspectRatio)
    p.end()
    return pm


class _MermaidPreviewView(QGraphicsView):
    """Mermaid 미리보기 — 클릭하면 별도 창으로 확대하던 방식(`_ClickablePreviewLabel`
    +확대 다이얼로그) 대신, 패널 안에서 바로 휠로 확대·드래그로 이동하며 확인한다
    (2026-08-21 실사용 피드백: "클릭하면 확대 방식보다 그냥 미리보기에서 드래그
    휠방식으로 확대 축소하며 확인하는 방식은 어떤지"). 캔버스 본체의 줌 관례(휠 배율
    1.15, `AnchorUnderMouse` — `host_ui._on_wheel_zoom`)를 그대로 재사용해 새 줌
    공식을 만들지 않는다(손안의 카드). 도형을 선택·편집할 대상이 아닌 순수 읽기전용
    보기라, 좌클릭 드래그를 Qt 기본 `ScrollHandDrag`(손모양 패닝)에 그대로 맡길 수
    있다 — 별도 팬 로직이 필요 없다.

    코드가 바뀔 때마다(`set_mermaid_code`) 화면을 그 도형 전체가 보이도록 다시
    맞춘다(`fitInView`) — 이 자체가 "가로든 세로든 중앙에" 요구를 공짜로 만족시킨다
    (정적 픽스맵 렌더와 달리 `fitInView`는 Qt가 알아서 중앙 정렬한다). 그 이후의
    휠줌·드래그팬은 사용자 조작 그대로 유지되고, 다음 코드 변경이 오면 다시 맞춰진다
    — "최신 도형을 한눈에 보여주고, 그 다음은 직접 둘러본다"는 의도."""

    _PLACEHOLDER = "코드를 입력하면\n미리보기가 표시됩니다"
    _ERROR = "구문 오류 —\n미리보기를 표시할 수 없습니다"
    _ZOOM_FACTOR = 1.15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._message = self._PLACEHOLDER
        self._show_message(self._message)

    def has_content(self) -> bool:
        """실제 도형이 그려져 있으면 True, 안내문(플레이스홀더·구문오류)만 있으면 False
        — pytest가 QLabel 시절의 `pixmap().isNull()` 대신 이걸로 상태를 확인한다."""
        return not self._message

    def message_text(self) -> str:
        """현재 표시 중인 안내문(도형이 있으면 빈 문자열)."""
        return self._message

    def set_mermaid_code(self, text: str, pen_color: QColor | None = None):
        scene = _build_mermaid_preview_scene(text, pen_color)
        if scene is None:
            self._message = self._ERROR if text.strip() else self._PLACEHOLDER
            self._show_message(self._message)
            return
        self._message = ""
        self.setScene(scene)
        r = scene.itemsBoundingRect()
        margin = 12.0
        self.fitInView(r.adjusted(-margin, -margin, margin, margin),
                       Qt.AspectRatioMode.KeepAspectRatio)

    def _show_message(self, text: str):
        scene = QGraphicsScene(self)
        item = scene.addText(text)
        item.setDefaultTextColor(QColor("#8a8a8a"))
        self.setScene(scene)
        self.resetTransform()
        self.centerOn(item)

    def wheelEvent(self, e):
        if not self.has_content():
            return   # 안내문뿐일 땐 확대할 대상이 없음
        dy = e.angleDelta().y()
        if dy == 0:
            return
        factor = self._ZOOM_FACTOR if dy > 0 else 1.0 / self._ZOOM_FACTOR
        self.scale(factor, factor)


# [2026-08-21 실사용 피드백] Mermaid 코드 첫 줄의 방향 토큰 — `mermaid_import._HEADER_RE`와
# 같은 패턴이지만 그쪽은 파싱(가져오기) 전용 private이라 여기서 UI 동기화용으로 별도 소유.
_MERMAID_HEADER_RE = re.compile(r"^\s*(?:flowchart|graph)\s+(TD|TB|LR|RL|BT)\b", re.IGNORECASE)


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

    _SAMPLE = ("flowchart LR\n"
               "    A[시작] --> B{조건?}\n"
               "    B -->|예| C[처리]\n"
               "    B -->|아니오| D([종료])\n"
               "    C --> D")

    # [2026-08-21 실사용 피드백] 방향 드롭다운 항목 — 기본(0번, 콤보 초기 선택)은 가로(LR).
    _DIRECTIONS = [
        ("가로 (→)", "LR"),
        ("세로 (↓)", "TD"),
        ("세로 (↑)", "BT"),
        ("가로 (←)", "RL"),
    ]

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
        # [2026-08-21 실사용 피드백 — "도형이 너무 어두워서 잘 안보임"] 미리보기 펜 색 —
        # `_SvgAssetDialog._preview_pen_color`와 같은 이유·같은 값(다크 테마 카드 배경에서
        # `_ICON_COLOR` 기본값은 대비가 약하다).
        self._preview_pen_color = QColor("#f2f2f2") if dark else None

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
        # [2026-08-21 피드백] "텍스트 설명 상하 폭이 좁다, 아래 모델까지 합쳐 Mermaid
        # 코드칸과 1:1 비율이면 좋겠다" — 고정 높이 대신 최소 높이만 두고 카드(아래
        # `prompt_frame_lay.addWidget(self._prompt_edit, 1)`)와 상위 `top_col`의 stretch를
        # 타고 자라게 한다.
        self._prompt_edit.setMinimumHeight(64)
        self._prompt_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._prompt_edit.setFrameShape(QFrame.Shape.NoFrame)   # 테두리는 카드가 그림
        self._prompt_edit.setAcceptDrops(False)   # 드롭을 이 다이얼로그(dropEvent)로 넘김
        self._prompt_edit.installEventFilter(self)   # Enter 생성·Ctrl+V 이미지 첨부
        self._prompt_edit.setStyleSheet(
            "QPlainTextEdit { background:transparent; " +
            ("color:#241a15; }" if dark else "}")
        )
        prompt_frame_lay.addWidget(self._prompt_edit, 1)

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

        # [2026-08-20 피드백 재작업] 클립 아이콘 → "+" 정사각 버튼(`_build_attach_button`,
        # `_ImageAttachMixin` 공용) — "눌러서 불러오거나 드래그된다"는 느낌을 더 뚜렷하게.
        self._attach_btn = self._build_attach_button(toolbar_widget)
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
        # [2026-08-21 피드백] "텍스트 설명(+모델행)"과 "Mermaid 코드"가 1:1 비율로 세로공간을
        # 나눠 갖도록 각각을 별도 QVBoxLayout(top_col/bottom_col)으로 묶어 left_col에 stretch
        # 1씩 준다 — 이전엔 코드칸(`_edit`)만 stretch=1이라 창이 커질수록 코드칸만 자라고
        # 위쪽(텍스트 설명)은 그대로였다.
        top_col = QVBoxLayout()
        # [2026-08-20 피드백] 입력 카드 위에도 다른 두 섹션(코드·미리보기)과 같은 "제목"을
        # 달아 세 구역의 시각적 위계를 통일.
        prompt_title = QLabel("텍스트 설명", self)
        prompt_title.setStyleSheet(_SECTION_TITLE_QSS)
        top_col.addWidget(prompt_title)
        top_col.addWidget(prompt_frame, 1)

        self._progress = _GenProgressRow(self)
        top_col.addWidget(self._progress)

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
        top_col.addLayout(model_row)
        # [2026-08-20 재피드백] 모델 행 끝에 있던 설정 버튼이 줄맞춤을 깨뜨린다는 지적(SVG
        # 창과 동일) — 우하단 확인/취소 버튼 옆(부가 동작 자리)으로 옮긴다(아래 `bottom_row`).
        self._settings_btn = QToolButton(self)
        self._settings_btn.setIcon(_act_icon("settings"))
        self._settings_btn.setToolTip("AI 게이트웨이 설정(주소·키·연결 테스트)")
        self._settings_btn.clicked.connect(self._open_gateway_settings)
        self._populate_models()
        left_col.addLayout(top_col, 1)

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
        bottom_col = QVBoxLayout()
        code_label_row = QHBoxLayout()
        code_title = QLabel("Mermaid 코드 (직접 입력·붙여넣기 가능)", self)
        code_title.setStyleSheet(_SECTION_TITLE_QSS)
        code_label_row.addWidget(code_title)
        code_label_row.addStretch(1)
        # [2026-08-21 실사용 피드백] 방향 컨트롤 — 생성 후에도 세로↔가로를 쉽게 바꾸도록.
        # 콤보를 바꾸면 코드 첫 줄의 방향 토큰만 고쳐 쓰고(`_on_direction_changed`), 반대로
        # 코드가 바뀌면(직접 타이핑·AI 생성 결과 반영 둘 다) 콤보도 따라 동기화된다
        # (`_sync_direction_combo_from_code`, `_on_edit_text_changed`에서 호출).
        code_label_row.addWidget(QLabel("방향:", self))
        self._direction_combo = QComboBox(self)
        self._direction_combo.setStyleSheet(_ROUNDED_COMBO_QSS)
        for label, token in self._DIRECTIONS:
            self._direction_combo.addItem(label, token)
        self._direction_combo.currentIndexChanged.connect(self._on_direction_changed)
        code_label_row.addWidget(self._direction_combo)
        bottom_col.addLayout(code_label_row)
        self._edit = QPlainTextEdit(self)
        self._edit.setPlaceholderText(self._SAMPLE)
        self._edit.setMinimumSize(QSize(420, 260))
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        bottom_col.addWidget(self._edit, 1)
        left_col.addLayout(bottom_col, 1)

        split = QHBoxLayout()
        split.addLayout(left_col, 1)

        preview_col = QVBoxLayout()
        # [2026-08-21 실사용 피드백] "클릭하면 확대"에서 "휠로 확대·드래그로 이동"으로
        # 교체 — 제목도 그 조작법 안내로 바꾼다(패널 자체가 `_MermaidPreviewView`).
        preview_title = QLabel("미리보기 (휠로 확대·드래그로 이동)", self)
        preview_title.setStyleSheet(_SECTION_TITLE_QSS)
        preview_col.addWidget(preview_title)
        preview_frame = QFrame(self)
        preview_frame.setObjectName("mermaidPreviewFrame")
        preview_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        preview_frame.setStyleSheet(
            "QFrame#mermaidPreviewFrame { border:1px solid rgba(128,128,128,90); "
            "border-radius:8px; }"
        )
        # [2026-08-20 피드백] "미리보기 너비가 왼쪽 입력창들과 비슷했으면" — split은 이미
        # stretch 1:1이지만, 좌측은 `_edit.setMinimumSize(420, ...)`가 최소폭을 못박는 반면
        # 우측은 최소폭이 preview_view(160)뿐이라 다이얼로그 초기 sizeHint에서 좌우가
        # 비대칭이었다. 우측도 같은 420으로 맞춰 최초 오픈부터 균형이 잡히게 한다.
        preview_frame.setMinimumWidth(420)
        preview_frame_lay = QVBoxLayout(preview_frame)
        preview_frame_lay.setContentsMargins(6, 6, 6, 6)
        self._preview_view = _MermaidPreviewView(preview_frame)
        self._preview_view.setMinimumSize(160, 160)
        self._preview_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview_view.setStyleSheet("background:transparent; border:none;")
        preview_frame_lay.addWidget(self._preview_view)
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
        self._edit.textChanged.connect(self._on_edit_text_changed)

        self._btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                      | QDialogButtonBox.StandardButton.Cancel, self)
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        ok_btn = self._btns.button(QDialogButtonBox.StandardButton.Ok)
        # [2026-08-19 Stage 6] 목업 시각 언어 차용 — "OK" 대신 결과를 명시하는 라벨.
        ok_btn.setText("확인 (캔버스 삽입)")
        ok_btn.setStyleSheet(_CORAL_BTN_QSS)
        # [2026-08-20 재피드백] 설정 버튼을 여기(확인/취소 옆)로 옮겨왔다 — 부가 동작은
        # 왼쪽, 주 동작(확인/취소)은 오른쪽(SVG 창과 동일).
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self._settings_btn)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self._btns)
        lay.addLayout(bottom_row)

    def text(self):
        return self._edit.toPlainText()

    def _on_edit_text_changed(self):
        self._preview_timer.start()
        self._sync_direction_combo_from_code()

    def _sync_direction_combo_from_code(self):
        """코드 첫 줄의 방향 토큰을 읽어 방향 콤보를 맞춘다(직접 타이핑·AI 생성 결과
        둘 다 여기로 들어온다) — 콤보가 실제 코드와 다른 값을 보여주는 혼란을 막는다.
        `TB`는 Mermaid에서 `TD`와 같은 뜻이라 같은 항목으로 묶는다."""
        m = _MERMAID_HEADER_RE.match(self._edit.toPlainText())
        if not m:
            return
        token = m.group(1).upper()
        if token == "TB":
            token = "TD"
        idx = self._direction_combo.findData(token)
        if idx >= 0 and idx != self._direction_combo.currentIndex():
            self._direction_combo.blockSignals(True)
            self._direction_combo.setCurrentIndex(idx)
            self._direction_combo.blockSignals(False)

    def _on_direction_changed(self):
        """방향 콤보 선택 → 코드 첫 줄의 방향 토큰만 고쳐 쓴다(나머지 코드는 그대로).
        헤더가 아직 없으면(빈 칸) 바꿀 대상이 없으니 조용히 무시 — 다음 생성/입력에
        어차피 기본값(가로)이 적용된다."""
        m = _MERMAID_HEADER_RE.match(self._edit.toPlainText())
        if not m:
            return
        token = self._direction_combo.currentData()
        start, end = m.span(1)
        text = self._edit.toPlainText()
        if text[start:end].upper() == token:
            return
        cursor = self._edit.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(text[:start] + token + text[end:])

    def _update_preview(self):
        """디바운스 타이머 만료 시 호출 — `_preview_view`(실시간 휠줌/드래그팬 뷰)를
        새 코드로 다시 그린다."""
        self._preview_view.set_mermaid_code(self._edit.toPlainText(), self._preview_pen_color)

    def done(self, r):
        # X·Cancel·OK·Esc 전부 결국 여기로 모인다(QDialog 표준 흐름) — 닫기는 무엇이 돌든
        # 항상 즉시 허용하고, 아직 도는 워커는 `_detach_worker`로 분리해 결과를 버린다
        # (2026-08-23, 실사용 버그 수정 — 상세 이유는 `_detach_worker` 주석 참조. 예전엔
        # `closeEvent`에서 `e.ignore()`로 닫기 자체를 막았는데, Cancel 버튼의 `reject()`는
        # `closeEvent`를 거치지 않고 곧장 여기로 와 그 방어코드가 원천 무효였다).
        _detach_worker(self._worker)
        _detach_worker(self._model_list_worker)
        super().done(r)

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
        — 재피드백: "추천 설명은 빼자"). `models`가 비어 있으면(조회 전·실패 시) 추천
        둘만으로 조용히 폴백. 이전에 고른 모델이 새 목록에도 있으면 그대로 유지한다
        (백그라운드 갱신이 사용자가 막 고른 모델을 조용히 되돌리지 않도록). 실제 채우기는
        `_fill_model_combo_grouped`(모듈 함수, 2026-08-20 SVG 창과 공유하도록 추출).

        [2026-08-21] 기본값은 `TEXT_RECOMMEND_1`(GPT — SVG 창과 공유하는 "계열별 비교"용
        상수)이 아니라 `TEXT_RECOMMEND_MERMAID`를 쓴다 — gpt-5.6 계열이 "상세하게" 같은
        확장 요청에 실측으로 불안정함이 드러나 Mermaid 전용 기본값을 분리했다(SVG 슬롯
        A/B는 이번에 검증 안 해 `TEXT_RECOMMEND_1`/`_2` 그대로 유지)."""
        prev = self.model() if self._model_combo.count() else None
        _fill_model_combo_grouped(self._model_combo, models, gw.TEXT_RECOMMEND_MERMAID, prev)

    def model(self) -> str:
        return _combo_selected_model(self._model_combo, gw.TEXT_RECOMMEND_MERMAID)

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


class _ShortcutSettingsDialog(QDialog):
    """단축키 재할당 창 — [실사용 요청 2026-08-21] 편집(&E) → "단축키 설정…". 대상은
    `shortcuts.SHORTCUT_DEFS`(메뉴/툴바 QAction + `core_view.py`가 직접 매칭하는 뷰
    단축키를 하나로 묶은 레지스트리) 전부 — 카테고리(도구/편집/파일/삽입/보기/도움말)별로
    `QFormLayout`을 나눠 스크롤 영역에 쌓는다. 항목마다 `QKeySequenceEdit`+「초기화」.

    같은 키를 두 항목에 중복 지정하면(이산 매칭이라 먼저 검사되는 쪽만 항상 이겨 나머지가
    죽은 단축키가 된다) 실시간으로 감지해 OK를 막는다 — 저장 후에야 알아채면 원인을 못
    찾는 조용한 버그가 되므로 입력 시점 차단이 낫다는 판단.

    삭제=Backspace·다시 실행=Ctrl+Shift+Z는 `core_view.py`의 고정 별칭이라(재할당과
    무관하게 항상 동작) 이 창에 노출하지 않는 대신 상단 안내문으로 고지한다.

    OK를 눌러야 QSettings에 저장된다(Cancel은 변경 폐기, `_AIGatewaySettingsDialog`와
    같은 관례) — 기본값과 같아진 항목은 `reset_sequence()`로 QSettings 키 자체를 지워
    "저장된 커스터마이즈가 하나도 없음"과 "전부 기본값으로 되돌림"을 구분되게 둔다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("단축키 설정")
        self.resize(480, 580)
        outer = QVBoxLayout(self)

        hint = QLabel(
            "삭제는 Backspace, 다시 실행은 Ctrl+Shift+Z로도 항상 동작합니다(고정 별칭,"
            " 아래 목록과 별개).", self)
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self._conflict_label = QLabel("", self)
        self._conflict_label.setWordWrap(True)
        self._conflict_label.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self._conflict_label)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._edits: dict[str, QKeySequenceEdit] = {}
        last_cat = None
        form = None
        for sid, cat, label, _default in shortcuts.SHORTCUT_DEFS:
            if cat != last_cat:
                cat_font = self.font()
                cat_font.setBold(True)
                cat_lbl = QLabel(f"[{cat}]", self)
                cat_lbl.setFont(cat_font)
                body_lay.addWidget(cat_lbl)
                form = QFormLayout()
                body_lay.addLayout(form)
                last_cat = cat
            edit = QKeySequenceEdit(QKeySequence(shortcuts.current_sequence(sid)), self)
            edit.keySequenceChanged.connect(self._check_conflicts)
            reset_btn = QToolButton(self)
            reset_btn.setText("초기화")
            reset_btn.setToolTip(f"기본값으로: {shortcuts.default_sequence(sid) or '(없음)'}")
            reset_btn.clicked.connect(
                lambda _c=False, s=sid, e=edit:
                    e.setKeySequence(QKeySequence(shortcuts.default_sequence(s))))
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            row.addWidget(reset_btn)
            form.addRow(label, row)
            self._edits[sid] = edit

        btn_row = QHBoxLayout()
        reset_all_btn = QToolButton(self)
        reset_all_btn.setText("전체 초기화")
        reset_all_btn.clicked.connect(self._reset_all_fields)
        btn_row.addWidget(reset_all_btn)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        self._btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                      | QDialogButtonBox.StandardButton.Cancel, self)
        self._btns.accepted.connect(self._on_accept)
        self._btns.rejected.connect(self.reject)
        outer.addWidget(self._btns)

        self._check_conflicts()

    def _reset_all_fields(self):
        for sid, edit in self._edits.items():
            edit.setKeySequence(QKeySequence(shortcuts.default_sequence(sid)))

    def _check_conflicts(self, *_a):
        seen: dict[str, str] = {}
        conflicts: set[str] = set()
        for sid, edit in self._edits.items():
            seq = edit.keySequence()
            if seq.isEmpty():
                continue
            key = seq.toString()
            if key in seen:
                conflicts.add(sid)
                conflicts.add(seen[key])
            else:
                seen[key] = sid
        ok_btn = self._btns.button(QDialogButtonBox.StandardButton.Ok)
        if conflicts:
            names = ", ".join(shortcuts.label_of(s) for s in sorted(conflicts))
            self._conflict_label.setText(
                f"<span style='color:{_STATUS_FAIL_COLOR};'>같은 키가 중복 지정됨: "
                f"{html.escape(names)}</span>")
            ok_btn.setEnabled(False)
        else:
            self._conflict_label.setText("")
            ok_btn.setEnabled(True)

    def _on_accept(self):
        for sid, edit in self._edits.items():
            seq_str = edit.keySequence().toString()
            if not seq_str or seq_str == shortcuts.default_sequence(sid):
                shortcuts.reset_sequence(sid)
            else:
                shortcuts.set_sequence(sid, seq_str)
        self.accept()


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
        self._test_result_label.setTextFormat(Qt.TextFormat.RichText)
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
            self._test_result_label.setText(
                f"<span style='color:{_STATUS_FAIL_COLOR};'>API 키를 입력하세요.</span>")
            return
        self._test_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            lines = []
            try:
                models = gw.list_text_models(key, self.base_url(), timeout=10.0)
                n_gpt = sum(1 for m in models if "gpt" in m.lower())
                n_gemini = sum(1 for m in models if "gemini" in m.lower())
                lines.append(
                    f"<span style='color:{_STATUS_OK_COLOR};'>Gemini {n_gemini}개 · "
                    f"GPT {n_gpt}개 응답</span>")
            except Exception as e:
                lines.append(
                    f"<span style='color:{_STATUS_FAIL_COLOR};'>모델 조회 실패: "
                    f"{html.escape(str(e))}</span>")
            try:
                remaining, quota = gw.get_credit_balance(key, self.base_url())
                lines.append(
                    f"<span style='color:{_STATUS_OK_COLOR};'>크레딧 잔여 "
                    f"{remaining:.0f} / {quota:.0f}</span>")
            except Exception as e:
                lines.append(
                    f"<span style='color:{_STATUS_FAIL_COLOR};'>크레딧 확인 실패: "
                    f"{html.escape(str(e))}</span>")
            self._test_result_label.setText("<br>".join(lines))
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

def _render_svg_candidate_pixmap(svg_text: str, size: int,
                                 pen_color: QColor | None = None) -> QPixmap | None:
    """후보 미리보기 렌더 — 원본 SVG를 그대로 QSvgRenderer로 그리지 않고, 실제 삽입 때와
    동일한 파서(`parse_svg_string`)로 아이템을 만들어 임시 씬에 얹은 뒤 우리 펜(중립
    잉크색·NoBrush)으로 렌더한다. 프롬프트가 "색은 지정 안 해도 됨"을 허용하는데(
    `svg_import.py`가 원래 색을 애초에 무시하는 설계 — 항상 앱이 다시 칠함), 원본 SVG를
    그대로 QSvgRenderer로 렌더하면 SVG 기본값(stroke:none)상 선-아트가 통째로 안 보이거나
    반대로 닫힌 도형은 기본 fill:black 검은 덩어리로 나올 수 있다 — A단계 실측 때 진단
    스크립트가 실제로 겪은 함정과 같은 종류(`docs/history/2026-08.md` "§8 항목20" 참조).
    미리보기와 실제 삽입 결과가 달라지면 신뢰할 수 없으므로 항상 같은 경로로 렌더한다.
    파싱 실패·빈 결과면 None(호출부가 "미리보기 실패" 표시).

    `pen_color`(2026-08-20 피드백) — 기본은 `_ICON_COLOR`(캔버스 실삽입과 같은 중립
    잉크색)지만, 이 작은 카드 안에서는 다크 테마 카드 배경과 대비가 약해 흐리게 보인다는
    지적으로 호출부(다이얼로그)가 미리보기 전용 밝은 색을 넘길 수 있게 열어둔다 — **실제
    캔버스 삽입 색(`_ICON_COLOR`)은 이 인자와 무관하게 그대로**(여긴 미리보기 렌더 함수의
    펜 색만 바꾸는 것)."""
    try:
        items, vb = parse_svg_string(svg_text)
    except Exception:
        return None
    if not items:
        return None
    scene = QGraphicsScene()
    pen = QPen(pen_color or _ICON_COLOR, 1.5)
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
        # [2026-08-21] Mermaid 미리보기와 같은 함정·같은 수정 — `render(target, source,
        # KeepAspectRatio)`는 여백을 target 좌상단으로 몰아붙이는 Qt 기본 동작(가운데
        # 정렬 아님), `_centered_target_rect`(pdf_export.py)로 미리 중앙 사각형을 계산.
        scene.render(p, _centered_target_rect(target, source), source,
                     Qt.AspectRatioMode.KeepAspectRatio)
    p.end()
    return pm


class _QuickLookDialog(QDialog):
    """확대 보기 — 후보 갤러리 뷰어(2026-08-20 3차 피드백으로 확장). 다이얼로그(`_svg_
    dialog`) 하나당 인스턴스 하나만 재사용하며, "지금 몇 번째를 보는지"(`_index`)만 바꿔
    다시 그린다.

    ⓐ **닫기** — 우상단 X·Esc(`QDialog` 기본 `reject()`)에 더해, 창 포커스를 잃으면
    (다른 곳 클릭·창 전환) 자동으로 닫힌다. ⚠ **재재재피드백(2026-08-20) — 바깥 클릭이
    실사용에선 안 먹혔다**: 처음엔 `changeEvent()`에서 `QEvent.Type.WindowDeactivate`를
    잡으려 했는데, 실측(두 개 진짜 top-level 창을 띄우고 하나를 활성화해 다른 하나가 받는
    이벤트를 직접 로그)해보니 **`WindowDeactivate`는 `changeEvent()`가 아니라 `event()`로
    직접 전달된다** — `changeEvent()`는 그 대신 `QEvent.Type.ActivationChange`만 받는다.
    이전 검증(pytest)이 `changeEvent()`를 직접 호출해 통과시켰던 것 자체가 함정이었다 —
    Qt가 실제로 그 경로를 타는지 확인 없이 메서드를 직접 불러 "확인됨"으로 착각한
    프록시검증(전역 규칙 11-c 위반 사례). `event()` 오버라이드로 교체.

    ⓑ **탐색** — `←`/`→` 키 또는 하단 ‹›버튼으로 후보를 넘기며, 이동은 메인 그리드의
    단일선택(`_svg_dialog._pick_card`)과 양방향 동기화된다(카드 클릭 → 확대창 갱신도,
    확대창 이동 → 카드 선택 갱신도 됨). 상단엔 "n / N · 모델명"만 표시.

    ⓒ **심볼로 저장 토글** — 지금 보는 후보의 "심볼로 저장" 체크박스를 `_SvgCandidateCard.
    _save_check`와 같은 상태로 공유(다중 후보 골라 한꺼번에 저장하는 기존 기능과 자연히
    맞물림). Space 키 또는 하단 가운데 버튼 클릭 둘 다로 토글한다.

    [실사용 피드백 2026-08-25] 하단이 작은 회색 안내 텍스트(11px, #8a8a8a) 하나뿐이라
    ⓐ 위쪽 카운터보다 눈에 덜 띄고 ⓑ 사실은 "클릭 가능한 버튼"이 아니라 Space 전용
    안내문이라 마우스로는 토글할 방법이 아예 없었다 — 상단 ‹›버튼을 하단으로 내려
    체크 토글 버튼과 한 줄에 가운데 정렬하고(모두 실제 버튼, 크게), 상단엔 카운터만
    남겼다. 네비 버튼은 여전히 `NoFocus`로 둬 Space가 항상 이 다이얼로그의
    `keyPressEvent`로 온다(버튼이 포커스를 채가면 Space가 "버튼 클릭"으로 먼저
    소비돼버린다)."""

    _NAV_BTN_PX = 44          # [2026-08-25] 재배치 — 기존 기본 크기보다 확대
    _BOTTOM_FONT_PX = 16

    def __init__(self, svg_dialog, parent=None):
        super().__init__(parent)
        self._svg_dialog = svg_dialog
        self._index = 0
        self.setWindowTitle("SVG 후보 확대")

        v = QVBoxLayout(self)
        self._counter_label = QLabel(self)
        self._counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = self._counter_label.font(); f.setPointSize(f.pointSize() + 1); self._counter_label.setFont(f)
        v.addWidget(self._counter_label)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self._label, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)
        bottom_row.addStretch(1)
        self._prev_btn = QToolButton(self)
        self._prev_btn.setText("‹")
        self._prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._prev_btn.setFixedSize(QSize(self._NAV_BTN_PX, self._NAV_BTN_PX))
        self._prev_btn.setStyleSheet(f"font-size:{self._BOTTOM_FONT_PX + 6}px;")
        self._prev_btn.clicked.connect(lambda: self._step(-1))
        bottom_row.addWidget(self._prev_btn)

        self._check_btn = QToolButton(self)
        self._check_btn.setCheckable(True)
        self._check_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._check_btn.setToolTip("단축키: Space")
        self._check_btn.setStyleSheet(
            f"QToolButton {{ font-size:{self._BOTTOM_FONT_PX}px; padding:8px 16px; }}")
        self._check_btn.clicked.connect(self._on_check_btn_clicked)
        bottom_row.addWidget(self._check_btn)

        self._next_btn = QToolButton(self)
        self._next_btn.setText("›")
        self._next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._next_btn.setFixedSize(QSize(self._NAV_BTN_PX, self._NAV_BTN_PX))
        self._next_btn.setStyleSheet(f"font-size:{self._BOTTOM_FONT_PX + 6}px;")
        self._next_btn.clicked.connect(lambda: self._step(1))
        bottom_row.addWidget(self._next_btn)
        bottom_row.addStretch(1)
        v.addLayout(bottom_row)

        self.resize(QSize(640, 640))

    def _on_check_btn_clicked(self):
        """[2026-08-25] 하단 버튼 클릭으로도 Space와 동일하게 토글 — `_check_btn`이
        `setCheckable(True)`라 클릭 시점엔 이미 새 상태로 바뀌어 있으므로, 그 값을
        그대로 카드에 반영한다(카드의 `stateChanged`가 "내 심볼로 저장" 버튼 활성화도
        같이 갱신, 기존 관례)."""
        candidates = self._svg_dialog._candidates
        if not candidates or not (0 <= self._index < len(candidates)):
            return
        card = candidates[self._index][0]
        card._save_check.setChecked(self._check_btn.isChecked())
        self._update_check_hint(card)

    def show_index(self, index: int):
        """`index`번째 후보를 그린다 — 카드 클릭(`_pick_card`)·화살표 탐색(`_step`)·
        더블클릭(`_show_enlarged_candidate`) 세 진입점이 전부 이걸 부른다."""
        candidates = self._svg_dialog._candidates
        if not candidates:
            self.close()
            return
        index = max(0, min(index, len(candidates) - 1))
        self._index = index
        card, svg_text, model_used = candidates[index]
        pm = _render_svg_candidate_pixmap(svg_text, 600, self._svg_dialog._preview_pen_color)
        if pm is None:
            self._label.setPixmap(QPixmap())
            self._label.setText("구문 오류 — 미리보기를 표시할 수 없습니다")
        else:
            self._label.setText("")
            self._label.setPixmap(pm)
        self._counter_label.setText(f"{index + 1} / {len(candidates)}  ·  {model_used}")
        self._prev_btn.setEnabled(index > 0)
        self._next_btn.setEnabled(index < len(candidates) - 1)
        self._update_check_hint(card)
        self.show()
        self.raise_()
        self.activateWindow()

    def _update_check_hint(self, card: "_SvgCandidateCard"):
        checked = card.is_checked_for_save()
        self._check_btn.setChecked(checked)
        mark = "☑" if checked else "☐"
        self._check_btn.setText(f"{mark}  심볼로 저장")

    def _step(self, delta: int):
        candidates = self._svg_dialog._candidates
        if not candidates:
            return
        new_index = self._index + delta
        if not (0 <= new_index < len(candidates)):
            return
        self.show_index(new_index)
        self._svg_dialog._pick_card(candidates[new_index][0])

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Left:
            self._step(-1)
            return
        if e.key() == Qt.Key.Key_Right:
            self._step(1)
            return
        if e.key() == Qt.Key.Key_Space:
            candidates = self._svg_dialog._candidates
            if candidates and 0 <= self._index < len(candidates):
                card = candidates[self._index][0]
                card._save_check.setChecked(not card._save_check.isChecked())
                self._update_check_hint(card)
            return
        super().keyPressEvent(e)

    def event(self, e):
        # ⚠ 위 클래스 docstring ⓐ 참조 — `WindowDeactivate`는 `changeEvent()`가 아니라
        # 여기(`event()`)로 온다. 실측으로 확인된 함정이라 되풀이하지 않도록 주석 유지.
        if e.type() == QEvent.Type.WindowDeactivate:
            self.close()
        return super().event(e)


class _SvgCandidateCard(QFrame):
    """후보 1개 카드 — 체크박스 + 썸네일 + 모델명. 세 가지 독립된 상호작용을 함께 담는다:
    ⓐ 카드 클릭 = 단일 선택(코랄 테두리, 2026-08-19 Stage 4) — OK 눌러 캔버스에
    삽입/대체할 후보 하나. ⓑ 좌상단 체크박스 = 다중 선택(2026-08-19 Stage 4) — "내 심볼로
    저장" 버튼으로 한꺼번에 심볼 팔레트에 등록할 후보들(0개 이상, 클릭 선택과 무관).
    ⓒ 더블클릭(2026-08-20) = 확대 보기 — 미리보기 패널을 없앤 자리를 대신한다."""

    doubleClicked = pyqtSignal()

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

    def set_checked_for_save(self, checked: bool):
        self._save_check.setChecked(checked)

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

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(e)


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
    """AI SVG 에셋 생성 — 대상 설명 한 줄 + 모델 슬롯 2개(각각 실제 모델 선택 + 후보
    개수 0~5, 최대 10개) + 생성 버튼 + 후보 카드 그리드(클릭 선택·더블클릭 확대) +
    OK/Cancel. 진입점 2곳(메뉴 삽입·우클릭 대체)이 이 다이얼로그를 그대로 공유한다 —
    호출부가 `selected_svg()` 결과를 각자의 방식(새로 삽입 vs 기존 도형 대체)으로 소비.

    **2026-08-20 재작업** — 옛 "GPT/Gemini 두 가족 고정, 개수만 선택"(Stage 2)을
    "슬롯 A/B 각각 실제 모델(Mermaid와 같은 `list_text_models` 목록)+개수" 로 확장(사용자
    확정: "여러 모델은 과하다, 2개면 충분 — 대신 모델도 사용자가 고르게"). 그룹 드롭다운
    채우기는 `_fill_model_combo_grouped`(모듈 함수로 추출, `_MermaidDialog`와 공유)가
    맡는다. 같은 세션에서 미리보기 패널을 제거하고 후보 그리드가 그 자리를 대신하며
    (더블클릭=확대), 프롬프트 복사 버튼(외부 AI에 이 창의 AI 지시 프롬프트를 그대로 줘서
    SVG를 받아오는 워크플로 지원)과 "생성할 대상" 제목을 카드 밖으로 옮기는 것(Mermaid와
    동일 위치)도 함께 반영했다.

    진행 표시는 `_SvgGenWorker`(QThread, 호출 1건당 인스턴스 1개) + marquee 진행바·
    경과시간(`_GenProgressRow`). 요청한 후보 전부를 **동시에 병렬 호출**한다(슬롯 간·
    슬롯 내부 구분 없이 완전 병렬, 2026-08-19 deep-interview 확정 — 최악 10개 동시 호출도
    실측으로 확인함: gpt 5개는 ~7초, gemini 5개는 30~52초에 걸쳐 전부 성공, 실패 0건).
    끝난 순서대로 카드가 하나씩 채워지므로(gpt가 보통 먼저 도착) 전부 끝나기 전에도 고를
    수 있다.

    이미지 입력도 받는다(찾아보기·드래그드롭·Ctrl+V, `_ImageAttachMixin` — 2026-08-19
    Stage 3, `_MermaidDialog`와 동일한 첨부 UI를 재사용). 이미지가 첨부되면 대상 설명은
    선택 사항이 된다(`generate_svg`의 `image` 인자, `text_to_mermaid.generate_mermaid`와
    동일 관례)."""

    _MAX_PER_MODEL = 5
    _CANDIDATE_COLS = 3   # [2026-08-20] 후보 그리드 열 수 — 카드 120px+간격이 왼쪽 열 폭에 맞음

    def __init__(self, parent=None, confirm_label: str = "확인 (도형 삽입)"):
        super().__init__(parent)
        self.setWindowTitle("AI SVG 에셋 생성")
        self.setAcceptDrops(True)
        self._init_image_attach_state()
        self._candidates: list[tuple[_SvgCandidateCard, str, str]] = []
        self._selected_card: _SvgCandidateCard | None = None
        # [2026-08-20 3차 피드백] 확대 보기를 매번 새로 만들지 않고 인스턴스 하나를 계속
        # 재사용(카드 클릭·화살표 탐색·더블클릭이 전부 `_QuickLookDialog.show_index`를 부름).
        self._quicklook: _QuickLookDialog | None = None
        self._workers: list[_SvgGenWorker] = []   # 생성 중일 때만 항목이 있음
        self._pending = 0          # 아직 안 끝난 워커 수
        self._gen_errors: list[str] = []
        self._generating = False   # [2026-08-25] 취소 버튼 토글용 — _set_generating() 참조
        lay = QVBoxLayout(self)

        # [2026-08-19 Stage 6] 목업("Mermaid 가져오기 Studio v2.0")의 시각 언어만 차용해
        # 입력카드+툴바 구성을 `_MermaidDialog`와 통일(2칸 분리 등 구조 자체는 그대로 —
        # deep-interview 확정: "시각 언어만 차용"). 입력칸(위, 밝게 고정) + 첨부·모델·생성
        # 툴바(아래) 카드 하나로 묶는다.
        dark = bool(getattr(self.parent(), "_dark", True))
        # [2026-08-20 피드백] "후보 미리보기 선이 배경과 비슷해 흐리다" — 다크 테마에서만
        # 밝은 미리보기 전용 펜 색으로(라이트 테마는 흰 배경에 흰 선이 안 보이므로 그대로
        # 기본 잉크색). `_render_svg_candidate_pixmap`이 이 값을 안 받으면 실삽입과 같은
        # `_ICON_COLOR`로 폴백.
        self._preview_pen_color = QColor("#f2f2f2") if dark else None
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

        # [2026-08-20 재피드백] "3줄 정도는 입력할 수 있게" — 한 줄 전용 `QLineEdit`에서
        # Mermaid `_prompt_edit`과 같은 `QPlainTextEdit`(고정 높이)으로 전환, Enter=생성
        # 규칙도 그대로 가져와 Shift+Enter=줄바꿈이 자연히 딸려온다(Mermaid는 64px=~2줄,
        # 여기는 90px=~3줄).
        self._prompt_edit = QPlainTextEdit(prompt_frame)
        self._prompt_edit.setPlaceholderText("예: 야기 안테나 아이콘")
        self._prompt_edit.setFixedHeight(90)
        self._prompt_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._prompt_edit.setFrameShape(QFrame.Shape.NoFrame)   # 테두리는 카드가 그림
        self._prompt_edit.setAcceptDrops(False)   # 드롭을 다이얼로그(dropEvent)로 넘김
        self._prompt_edit.installEventFilter(self)   # Enter 생성·Ctrl+V 이미지 첨부
        self._prompt_edit.setStyleSheet(
            "QPlainTextEdit { background:transparent; " +
            ("color:#241a15; }" if dark else "}")
        )
        prompt_frame_lay.addWidget(self._prompt_edit)

        enter_hint = QLabel("Enter 생성 · Shift+Enter 줄바꿈", prompt_frame)
        enter_hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        enter_hint.setStyleSheet("color:#8a8a8a; font-size:11px; background:transparent; "
                                  "padding:0 8px 3px 0;")
        prompt_frame_lay.addWidget(enter_hint)

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

        # [2026-08-20 피드백 재작업] Mermaid 창과 동일 — "+" 정사각 버튼(`_build_attach_button`).
        self._attach_btn = self._build_attach_button(toolbar_widget)
        toolbar_lay.addWidget(self._attach_btn)
        toolbar_lay.addWidget(self._build_image_chip(toolbar_widget))
        toolbar_lay.addStretch(1)

        # [2026-08-20 피드백] GPT/Gemini 개수·설정 버튼을 카드 툴바에서 빼서(아래 model_row로)
        # Mermaid처럼 카드 툴바엔 첨부+생성 버튼만 남긴다 — 한 줄에 다 몰려 있던 게 SVG 창이
        # Mermaid보다 훨씬 빽빽해 보이던 가장 큰 원인이었다.
        self._gen_btn = QToolButton(toolbar_widget)
        self._gen_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # [2026-08-25 실사용 피드백] 느린/실패하는 모델 하나 때문에 이미 도착한 후보를
        # 못 쓰고 전체 완료까지 기다려야 했다 — 버튼 자체를 생성 중엔 "취소"로 토글해
        # 즉시 대기 상태로 돌아올 수 있게 한다(이미 만들어진 후보는 그대로 유지,
        # `_cancel_generation` 참조). `_set_generating(False)`가 초기 라벨/아이콘을 맞춘다.
        self._gen_btn.clicked.connect(self._on_gen_btn_clicked)
        self._gen_btn.setStyleSheet(_CORAL_BTN_QSS)
        self._set_generating(False)
        toolbar_lay.addWidget(self._gen_btn)

        prompt_frame_lay.addWidget(toolbar_widget)

        # [2026-08-20 재검토] "완전히 똑같아도 된다"는 피드백으로 Mermaid와 똑같이 카드·
        # 모델행·코드칸을 전부 왼쪽 열(`left_col`) 하나에 쌓고, 오른쪽 열은 후보 갤러리로
        # (미리보기 패널은 제거 — 아래 참조).
        left_col = QVBoxLayout()
        # [2026-08-20 재피드백: "제목이 입력창 안에 있어서 잘 안 보인다"] 카드 안(입력칸과
        # 같은 밝은 배경)에 있던 라벨을 카드 밖(다이얼로그 중립 배경)으로 — Mermaid의
        # "텍스트 설명" 라벨과 완전히 같은 자리·같은 스타일.
        prompt_title = QLabel("생성할 대상(예: BNC 커넥터 아이콘):", self)
        prompt_title.setStyleSheet(_SECTION_TITLE_QSS)
        left_col.addWidget(prompt_title)
        left_col.addWidget(prompt_frame)

        self._progress = _GenProgressRow(self)
        left_col.addWidget(self._progress)

        # ---- 모델 선택(슬롯 2개, 각각 모델+개수) — 2026-08-20 재작업: 옛 "GPT/Gemini
        # 고정 2종" 대신 Mermaid와 같은 실제 모델 목록(`list_text_models`)에서 슬롯마다
        # 원하는 모델을 고르고, 슬롯마다 개수(0~5)를 매긴다(사용자 확정: "여러 모델은
        # 과하다, 2개 슬롯 + 각각 모델·개수 선택"). `_populate_models`가 두 콤보를 함께
        # 채운다 — Mermaid의 `_fill_model_combo`/`_ModelListWorker`를 그대로 재사용
        # (`_fill_model_combo_grouped`로 모듈 함수 추출, 아래 참조).
        # [2026-08-25 재작업] "GPT vs Gemini 나란히 비교" bake-off에서 "슬롯 A만 기본
        # 사용, 슬롯 B는 필요할 때만 켜는 옵션"으로 설계 변경(사용자 확정) — 슬롯 A는
        # 기본 모델(`gw.TEXT_RECOMMEND_1`, 2026-08-25부로 gemini lite 계열로 교체,
        # `gateway.py` 주석 참조) + 개수 기본 3개(같은 날 후속 요청). 슬롯 B는 모델
        # "(미선택)"이 곧 꺼짐이다(같은 날 후속 재작업 — 아래 `_count_b` 참조).
        model_row1 = QHBoxLayout()
        model_row1.addWidget(QLabel("모델 A:", self))
        self._model_combo_a = QComboBox(self)
        self._model_combo_a.setStyleSheet(_ROUNDED_COMBO_QSS)
        model_row1.addWidget(self._model_combo_a, 1)
        model_row1.addWidget(QLabel("개수:", self))
        self._count_a = QComboBox(self)
        self._count_a.addItems([str(i) for i in range(self._MAX_PER_MODEL + 1)])
        self._count_a.setCurrentIndex(3)   # [2026-08-25] 기본 3개로 상향(사용자 요청)
        self._count_a.setStyleSheet(_ROUNDED_COMBO_QSS)
        model_row1.addWidget(self._count_a)
        left_col.addLayout(model_row1)

        model_row2 = QHBoxLayout()
        model_row2.addWidget(QLabel("모델 B:", self))
        self._model_combo_b = QComboBox(self)
        self._model_combo_b.setStyleSheet(_ROUNDED_COMBO_QSS)
        model_row2.addWidget(self._model_combo_b, 1)
        model_row2.addWidget(QLabel("개수:", self))
        self._count_b = QComboBox(self)
        self._count_b.addItems([str(i) for i in range(self._MAX_PER_MODEL + 1)])
        self._count_b.setCurrentIndex(1)   # [2026-08-25 재작업] on/off는 이제 모델 선택
                                            # 여부가 가른다(아래 참조) — 개수는 미선택일 땐
                                            # 안 쓰이므로 1로 둬도 무해하고, 모델을 고르는
                                            # 순간 바로 1개가 생성된다.
        self._count_b.setStyleSheet(_ROUNDED_COMBO_QSS)
        model_row2.addWidget(self._count_b)
        left_col.addLayout(model_row2)
        # [2026-08-25 재작업] "개수=0"으로 켜짐/꺼짐을 표현하면 콤보엔 멀쩡한 모델명이
        # 떠 있는데 실제론 안 쓰이는 상태가 한눈에 안 들어온다(사용자 지적) — 대신
        # 모델 B 콤보 자체에 "(미선택)" 항목을 두고 그게 곧 "B 안 씀"이 되도록 한다.
        # `_requested_jobs()`가 이 상태를 개수와 무관하게 0개로 강제한다.
        self._model_combo_b.currentIndexChanged.connect(self._on_model_b_changed)
        # [2026-08-20 재피드백] 모델 행 끝에 있던 설정 버튼이 "모델 B/개수" 줄맞춤을
        # 깨뜨린다는 지적 — 우하단 확인/취소 버튼 옆(부가 동작 자리)으로 옮긴다
        # (아래 `bottom_row` 참조, Mermaid도 동일).
        self._settings_btn = QToolButton(self)
        self._settings_btn.setIcon(_act_icon("settings"))
        self._settings_btn.setToolTip("AI 게이트웨이 설정(주소·키·연결 테스트)")
        self._settings_btn.clicked.connect(self._open_gateway_settings)
        self._model_list_worker = None    # _ModelListWorker | None — 조회 중일 때만 설정
        self._populate_models()

        # ---- SVG 코드(왼쪽 열 마지막 칸) — Mermaid와 동일 구조. 후보를 클릭하면 이 칸에
        # 채워지고, OK는 항상 이 칸의 내용을 쓴다(카드 선택 여부와 무관) — 그래서 외부
        # AI(게이트웨이 밖)가 준 SVG를 직접 붙여넣어도 그대로 삽입된다.
        connector_row = QHBoxLayout()
        connector_row.addStretch(1)
        arrow_label = QLabel(self)
        arrow_label.setPixmap(_handdrawn_down_arrow_pixmap(QColor(_ACCENT_CORAL)))
        arrow_label.setFixedSize(30, 46)
        connector_row.addWidget(arrow_label)
        connector_row.addStretch(1)
        left_col.addLayout(connector_row)

        code_row = QHBoxLayout()
        code_title = QLabel("SVG 코드 (직접 입력·붙여넣기 가능):", self)
        code_title.setStyleSheet(_SECTION_TITLE_QSS)
        code_row.addWidget(code_title)
        code_row.addStretch(1)
        # [2026-08-20 재피드백] "외부 AI에 우리 프롬프트를 주고 SVG를 받아와 붙여넣는"
        # 워크플로 지원 버튼 — 위쪽 툴바(생성 관련 버튼들)가 아니라 이 붙여넣는 코드칸
        # 제목 옆으로 옮기고(그 워크플로가 실제로 끝나는 자리), 텍스트 대신 아이콘+
        # 호버 툴팁으로(상시 노출되는 텍스트 라벨보다 이 창에서 자주 쓰는 동작은 아니므로).
        self._copy_prompt_btn = QToolButton(self)
        self._copy_prompt_btn.setIcon(_act_icon("copy"))
        self._copy_prompt_btn.setToolTip(
            "이 창이 쓰는 AI 지시 프롬프트를 클립보드에 복사합니다.\n"
            "외부 AI(Claude, ChatGPT 등)에 붙여넣어 SVG를 받은 뒤,\n"
            "그 결과를 이 코드칸에 붙여넣으면 그대로 사용할 수 있습니다.")
        self._copy_prompt_btn.clicked.connect(self._copy_prompt_to_clipboard)
        code_row.addWidget(self._copy_prompt_btn)
        left_col.addLayout(code_row)
        self._code_edit = QPlainTextEdit(self)
        self._code_edit.setPlaceholderText(
            '<svg viewBox="0 0 100 100">...</svg>\n외부 AI가 준 SVG 코드를 여기 붙여넣어도 됩니다.')
        # [2026-08-20 재피드백] "왼쪽 입력창 폭이 오른쪽 후보 테두리보다 좁다" — Mermaid는
        # 양쪽에 같은 상수(420)를 줘서 균일하게 맞춘 것과 같은 방식으로, 여기도 오른쪽
        # 열(카드 3열 폭, 아래 `_candidates_scroll`과 정확히 같은 계산식)을 공용 최소폭으로
        # 왼쪽에도 그대로 적용한다.
        self._lr_min_width = self._CANDIDATE_COLS * 120 + (self._CANDIDATE_COLS - 1) * 8 + 16
        self._code_edit.setMinimumSize(QSize(self._lr_min_width, 200))
        self._code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        left_col.addWidget(self._code_edit, 1)

        split = QHBoxLayout()
        split.addLayout(left_col, 1)

        # ---- 오른쪽 열: 생성 후보 갤러리(2026-08-20 재작업 — 미리보기 패널 제거, 그
        # 자리를 후보 갤러리가 대신 채운다: 클릭=선택(코드칸에 채움), 더블클릭=확대
        # 보기(`_show_enlarged_candidate`, 옛 미리보기 확대창과 동일 렌더 함수 재사용) —
        # 별도 미리보기 없이도 후보 자체로 "보기"까지 겸한다). 가로 1줄 스크롤 대신
        # 고정 열(`_CANDIDATE_COLS`) 그리드로 바꿔 늘어난 세로 공간을 활용한다.
        right_col = QVBoxLayout()
        candidates_title = QLabel("생성 후보 (클릭=선택 · 더블클릭=확대):", self)
        candidates_title.setStyleSheet(_SECTION_TITLE_QSS)
        # [실사용 피드백 2026-08-25] 후보가 여러 개일 때 "심볼로 저장" 체크박스를 하나씩
        # 누르지 않고 한 번에 켜고 끌 수 있게 — 개별 체크 상태를 되읽어 tri-state로
        # 동기화하진 않는다(단순한 일괄 액션, 새로 추가되는 후보엔 영향 없음).
        title_row = QHBoxLayout()
        title_row.addWidget(candidates_title)
        title_row.addStretch(1)
        self._select_all_check = QCheckBox("전체선택", self)
        self._select_all_check.setStyleSheet("font-size:11px;")
        self._select_all_check.toggled.connect(self._on_select_all_toggled)
        title_row.addWidget(self._select_all_check)
        right_col.addLayout(title_row)

        # 최대 10장까지 나올 수 있어(슬롯당 5개×2) 그리드 + 세로 스크롤로 감싼다(카드 자체
        # 크기·스타일은 무변경 — 열 개수만 창 폭에 반응, `_update_candidate_columns` 참조).
        self._candidate_cols = self._CANDIDATE_COLS   # [2026-08-20 재피드백] 반응형 열 수
        self._candidates_grid = QGridLayout()
        self._candidates_grid.setSpacing(8)
        self._candidates_grid.setContentsMargins(6, 6, 6, 6)
        candidates_container = QWidget(self)
        candidates_container.setLayout(self._candidates_grid)
        self._candidates_scroll = QScrollArea(self)
        # [2026-08-20 재피드백] "미리보기처럼 사각 테두리를 크게 둬서 별도 창인 걸
        # 나타내달라" — `QScrollArea`도 `QFrame`이라 Mermaid `preview_frame`과 같은 QSS를
        # 직접 줄 수 있다(별도 래퍼 프레임 불필요). ⚠ 재재피드백(같은 날): 처음엔
        # `setFrameShape(NoFrame)`을 빼고 QSS `border`만 줬더니 꼭짓점이 잘려 보였다 —
        # `QScrollArea`(=`QAbstractScrollArea`)의 기본 `frameShape`는 일반 `QFrame`과
        # 달리 `StyledPanel`(사각 눌린 프레임)이라, 그 네이티브 프레임이 내 QSS 둥근
        # 테두리 위에 겹쳐 그려져(모서리만 튀어나온 것처럼) 각져 보인 것 — `NoFrame`으로
        # 네이티브 프레임을 끄고 QSS `border`만 그리게 해야 Mermaid의 평범한 `QFrame`과
        # 같은 결과가 난다.
        self._candidates_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._candidates_scroll.setObjectName("svgCandidatesFrame")
        self._candidates_scroll.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._candidates_scroll.setStyleSheet(
            "QScrollArea#svgCandidatesFrame { border:1px solid rgba(128,128,128,90); "
            "border-radius:8px; }"
        )
        self._candidates_scroll.setWidget(candidates_container)
        self._candidates_scroll.setWidgetResizable(True)
        self._candidates_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._candidates_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # [2026-08-20 피드백 → 재피드백] "생성후보 너비를 왼쪽 입력창들과 비슷하게" —
        # 처음엔 이 값(3열×카드120px+간격)만 오른쪽에 줬는데, 왼쪽 `_code_edit`이 그보다
        # 좁은 300을 쓰고 있어 여전히 비대칭이었다 — 위에서 계산한 `self._lr_min_width`
        # (왼쪽·오른쪽 공용)로 통일.
        self._candidates_scroll.setMinimumWidth(self._lr_min_width)
        right_col.addWidget(self._candidates_scroll, 1)

        split.addLayout(right_col, 1)
        lay.addLayout(split, 1)

        hint_row = QHBoxLayout()
        self._hint_label = QLabel("후보를 클릭해 선택하세요.", self)
        self._hint_label.setStyleSheet("color:#8a8a8a; font-size:11px;")
        self._hint_label.setVisible(False)
        hint_row.addWidget(self._hint_label)
        hint_row.addStretch(1)
        # [2026-08-20 재피드백] 텍스트 라벨 제거, 아이콘 전용+호버 툴팁으로(프롬프트 복사
        # 버튼과 같은 축약).
        self._save_symbols_btn = QToolButton(self)
        self._save_symbols_btn.setIcon(_act_icon("save"))
        self._save_symbols_btn.setToolTip("체크한 후보를 내 심볼 팔레트에 한꺼번에 저장")
        self._save_symbols_btn.setEnabled(False)
        self._save_symbols_btn.clicked.connect(self._on_save_to_symbols_clicked)
        hint_row.addWidget(self._save_symbols_btn)
        lay.addLayout(hint_row)

        self._code_edit.textChanged.connect(self._on_code_changed)

        self._btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                      | QDialogButtonBox.StandardButton.Cancel, self)
        self._ok_btn = self._btns.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setEnabled(False)
        # [2026-08-19 Stage 6] 목업 시각 언어 차용 — "OK" 대신 결과를 명시하는 라벨.
        # 호출부가 삽입/대체 중 실제로 일어날 일을 넘겨준다(host_fileio.py는 기본값
        # "확인 (도형 삽입)" 그대로, host_context.py의 대체 진입점만 다르게 넘김).
        # [2026-08-25, 인스턴스 재사용 신설] 두 진입점이 이제 같은 인스턴스를 공유해
        # 매번 새로 안 만들므로, 열 때마다 `set_confirm_label()`로 라벨을 다시 맞춘다.
        self._ok_btn.setText(confirm_label)
        self._ok_btn.setStyleSheet(_CORAL_BTN_QSS)
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        # [2026-08-20 재피드백] 설정 버튼을 여기(확인/취소 옆)로 옮겨왔다 — 부가 동작은
        # 왼쪽, 주 동작(확인/취소)은 오른쪽.
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self._settings_btn)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self._btns)
        lay.addLayout(bottom_row)

    def _on_code_changed(self):
        """SVG 코드칸이 항상 최종 소스 — Mermaid `_edit`와 동일 관례. 후보 클릭이든 직접
        타이핑/붙여넣기든 이 칸에 뭔가 있으면 OK를 누를 수 있다."""
        self._ok_btn.setEnabled(bool(self._code_edit.toPlainText().strip()))

    def _show_enlarged_candidate(self, index: int):
        """후보 카드 더블클릭 시 확대 보기(2026-08-20 — 미리보기 패널 제거를 대체:
        단일클릭=선택은 이미 카드가 담당하므로 확대는 더블클릭으로 분리했다).

        [2026-08-20 3차 피드백] 매번 새 다이얼로그를 만들지 않고 `self._quicklook`
        인스턴스 하나를 재사용 — 화살표 탐색·카드 클릭 동기화가 "같은 창"이어야 자연스럽기
        때문(`_QuickLookDialog` 클래스 docstring 참조)."""
        if not self._candidates:
            return
        if self._quicklook is None:
            self._quicklook = _QuickLookDialog(self, self)
        self._quicklook.show_index(index)

    def _copy_prompt_to_clipboard(self):
        """"프롬프트 복사" 버튼 — 외부 AI(Claude, ChatGPT 등)에 이 창과 같은 조건으로
        SVG를 요청할 수 있게, `text_to_svg`가 실제로 쓰는 프롬프트(형식 규칙 포함)를
        그대로 클립보드에 담는다. 이미지가 첨부돼 있으면 이미지용 프롬프트로."""
        subject = self._prompt_edit.toPlainText().strip()
        if not subject and self._attached_image is None:
            QMessageBox.information(self, "AI SVG 에셋 생성",
                                    "먼저 생성할 대상을 입력하거나 이미지를 첨부하세요.")
            return
        prompt = (build_image_prompt(subject) if self._attached_image is not None
                  else build_prompt(subject))
        QApplication.clipboard().setText(prompt)
        # [2026-08-20 재피드백] 아이콘 전용 버튼이라 텍스트로 "복사됨"을 보여줄 수 없다 —
        # 아이콘을 잠깐 체크 표시로 바꿨다가 되돌린다.
        self._copy_prompt_btn.setIcon(_act_icon("check"))
        QTimer.singleShot(1200, lambda: self._copy_prompt_btn.setIcon(_act_icon("copy")))

    def selected_svg(self) -> str:
        """OK가 실제로 가져가는 값 — 카드 클릭이 아니라 코드칸(`_code_edit`)이 최종 소스다
        (Mermaid `_edit`와 동일 관례, 2026-08-20). 카드를 클릭하면 그 SVG가 코드칸에
        채워지므로 결과적으로 같지만, 클릭 없이 코드칸에 직접 타이핑/붙여넣기만 해도 된다."""
        return self._code_edit.toPlainText().strip()

    def set_confirm_label(self, text: str):
        """[2026-08-25, 인스턴스 재사용 신설] 삽입/대체 두 진입점이 인스턴스를 공유하므로
        여는 쪽이 매번 자기 맥락에 맞는 라벨로 다시 맞춘다(생성자 인자 `confirm_label`은
        최초 생성 시 기본값일 뿐)."""
        self._ok_btn.setText(text)

    def svgs_for_insert(self) -> list[str]:
        """[실사용 피드백 2026-08-25] "도형삽입"이 체크한 후보를 다 받아가야 한다는 지적
        — 체크박스는 원래 "심볼로 저장" 전용(`_checked_for_save_candidates`)이었는데,
        체크된 게 있으면 그걸 그대로 삽입 대상으로도 쓴다(체크=이 후보들을 채택한다는
        의미로 통합). 체크가 하나도 없으면 기존처럼 `selected_svg()` 1개(코드칸)만
        돌려줘 하위호환 유지 — "도형 대체"(1개 도형 전용, `_generate_svg_replace`)는
        이 메서드를 안 쓰고 여전히 `selected_svg()`를 직접 부른다."""
        checked = self._checked_for_save_candidates()
        if checked:
            return [svg for svg, _model in checked]
        single = self.selected_svg()
        return [single] if single else []

    def done(self, r):
        # `_MermaidDialog.done`과 동일한 이유(2026-08-23) — X·Cancel·OK·Esc 전부 여기로
        # 모이므로, 닫기는 항상 즉시 허용하고 아직 도는 워커는 분리해 결과를 버린다.
        for w in self._workers:
            _detach_worker(w)
        _detach_worker(self._model_list_worker)
        super().done(r)

    def eventFilter(self, obj, event):
        if obj is self._prompt_edit and event.type() == QEvent.Type.KeyPress:
            # [2026-08-20 재피드백] `QPlainTextEdit`으로 전환하며 `returnPressed` 시그널이
            # 없어졌다 — Mermaid `_prompt_edit`과 동일하게 Enter=생성/Shift+Enter=줄바꿈을
            # 여기서 직접 가로챈다.
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False   # Shift+Enter는 기본 동작(줄바꿈)에 맡김
                # [2026-08-25] 버튼과 동일한 디스패처를 타야 한다 — 생성 중 Enter가 그냥
                # `_on_generate_clicked()`를 다시 부르면 워커가 중복으로 시작된다(버튼은
                # `_gen_btn.setEnabled(False)`로 막혀 있었지만 이 경로는 그 가드를 안 탐).
                self._on_gen_btn_clicked()
                return True
            if self._maybe_intercept_paste_image(event):
                return True
        return super().eventFilter(obj, event)

    def _open_gateway_settings(self):
        """`_AIGatewaySettingsDialog`를 이 SVG 창의 자식 모달로 연다. 주소/키가 바뀌었을
        수 있으니(2026-08-20 — 이제 이 창도 실제 모델 목록을 쓰므로) 닫힌 뒤 두 모델
        콤보를 Mermaid와 동일하게 다시 채운다."""
        if _AIGatewaySettingsDialog(self).exec() == QDialog.DialogCode.Accepted:
            self._populate_models()

    def _populate_models(self):
        """모델 슬롯 A/B 콤보를 채운다 — `_MermaidDialog._populate_models`와 동일 패턴
        (추천 모델로 즉시 채운 뒤 `_ModelListWorker`가 백그라운드로 실제 목록을 가져오면
        갱신). 슬롯 A 기본값은 `TEXT_RECOMMEND_1`(항상 실제 모델). 슬롯 B는
        `none_option`으로 "(미선택)" 항목을 두고 기본 선택되게 한다(2026-08-25 재작업 —
        B를 쓸지 여부를 개수가 아니라 이 콤보 자체가 가른다)."""
        _fill_model_combo_grouped(self._model_combo_a, [], gw.TEXT_RECOMMEND_1)
        _fill_model_combo_grouped(self._model_combo_b, [], gw.TEXT_RECOMMEND_2,
                                  none_option="(미선택)")
        key = gw.resolve_api_key()
        if not key:
            return
        if self._model_list_worker is not None and self._model_list_worker.isRunning():
            return   # `_MermaidDialog._populate_models`와 동일한 이유로 조용히 건너뜀
        self._model_list_worker = _ModelListWorker(key, gw.resolve_base_url(), self)
        self._model_list_worker.succeeded.connect(self._on_models_listed)
        self._model_list_worker.start()

    def _on_models_listed(self, models):
        prev_a = (_combo_selected_model(self._model_combo_a, gw.TEXT_RECOMMEND_1)
                  if self._model_combo_a.count() else None)
        prev_b = (_combo_selected_model_or_none(self._model_combo_b)
                  if self._model_combo_b.count() else None)
        _fill_model_combo_grouped(self._model_combo_a, models, gw.TEXT_RECOMMEND_1, prev_a)
        _fill_model_combo_grouped(self._model_combo_b, models, gw.TEXT_RECOMMEND_2, prev_b,
                                  none_option="(미선택)")

    def _on_model_b_changed(self):
        """모델 B가 "(미선택)"이면 개수 콤보는 안 쓰이는 값이라 비활성화해 혼란을
        막는다(생성 중엔 `_on_generate_clicked`가 이미 비활성화하므로 그 상태는
        건드리지 않는다)."""
        if self._generating:
            return
        self._count_b.setEnabled(
            _combo_selected_model_or_none(self._model_combo_b) is not None)

    def _requested_jobs(self) -> list[str]:
        """슬롯 A/B의 (모델, 개수) → 호출할 모델 목록(개수만큼 반복) — 예: A=gpt-5.4-mini
        2개·B=gemini-3.6-flash 1개면 [gpt-5.4-mini, gpt-5.4-mini, gemini-3.6-flash].
        워커 하나가 이 목록의 항목 하나씩을 맡는다. B가 "(미선택)"이면 개수와 무관하게
        0개로 취급한다(2026-08-25 재작업 — on/off는 모델 선택 여부가 가른다)."""
        n_a = int(self._count_a.currentText())
        model_a = _combo_selected_model(self._model_combo_a, gw.TEXT_RECOMMEND_1)
        model_b = _combo_selected_model_or_none(self._model_combo_b)
        n_b = int(self._count_b.currentText()) if model_b is not None else 0
        return [model_a] * n_a + [model_b] * n_b

    def _on_gen_btn_clicked(self):
        """[2026-08-25] `_gen_btn`(＝Enter 키)의 단일 진입점 — 생성 중이 아니면 생성을
        시작하고, 생성 중이면(버튼이 이미 "취소"로 바뀐 상태) 취소한다. Enter 단축키도
        이걸 통해야 생성 중 재입력이 중복 워커를 만들지 않는다(가드가 여기 한 곳뿐이라
        버튼 클릭이든 Enter든 항상 같은 분기를 탄다)."""
        if self._generating:
            self._cancel_generation()
        else:
            self._on_generate_clicked()

    def _set_generating(self, flag: bool):
        """[2026-08-25] 생성 버튼을 "AI로 생성" ↔ "취소"로 토글 — 별도 취소 버튼을 새로
        만드는 대신 같은 버튼이 상태에 따라 다른 동작을 하게 한다(사용자 제안)."""
        self._generating = flag
        if flag:
            self._gen_btn.setIcon(_act_icon("stop"))
            self._gen_btn.setText("취소")
            self._gen_btn.setToolTip("생성 취소 — 이미 도착한 후보는 그대로 남습니다")
        else:
            self._gen_btn.setIcon(_act_icon("generate"))
            self._gen_btn.setText("AI로 생성")
            self._gen_btn.setToolTip("AI로 생성 (Enter)")

    def _on_generate_clicked(self):
        """2026-08-19 Stage 2 — 요청한 후보 전부를 워커 하나씩(`_SvgGenWorker`)으로
        동시에 시작해 완전 병렬 호출한다. 완료 처리는 `_on_candidate_ready`(후보 도착마다)
        ·`_on_one_worker_finished`(워커 하나가 끝날 때마다 `_pending`을 줄이고, 0이 되면
        전체 완료 처리 — 옛 "워커 하나=전체"였던 Stage 1의 finally 블록 역할을 카운터로
        대신한다)로 나뉜다."""
        subject = self._prompt_edit.toPlainText().strip()
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
        self._set_generating(True)
        self._btns.setEnabled(False)
        self._model_combo_a.setEnabled(False)
        self._model_combo_b.setEnabled(False)
        self._count_a.setEnabled(False)
        self._count_b.setEnabled(False)
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

    def _reset_generation_ui(self):
        """생성 종료(정상 완료·취소 공통) 시 원상복구 — 진행바 끄고 버튼·콤보를 되돌린다."""
        self._progress.stop()
        self._set_generating(False)
        self._btns.setEnabled(True)
        self._model_combo_a.setEnabled(True)
        self._model_combo_b.setEnabled(True)
        self._count_a.setEnabled(True)
        self._on_model_b_changed()   # count_b는 무조건 켜지 않고 미선택 상태를 존중

    def _cancel_generation(self):
        """[2026-08-25 실사용 피드백] 느리거나(수십 초) 실패하는(타임아웃) 모델 하나
        때문에 이미 도착한 후보를 못 쓰고 전체 완료까지 기다려야 하던 문제 — 아직 안
        끝난 워커를 `_detach_worker`(다이얼로그를 닫을 때와 같은 메커니즘)로 분리해
        결과를 버리고 즉시 대기 상태로 돌아온다. 네트워크 호출 자체를 강제로 끊을 순
        없어 워커는 백그라운드에서 마저 끝나지만, 이 다이얼로그에는 더 이상 영향을 주지
        않는다. `self._candidates`는 손대지 않으므로 이미 도착한 후보는 그대로 남는다."""
        for w in self._workers:
            _detach_worker(w)
        self._workers = []
        self._pending = 0
        self._reset_generation_ui()

    def _on_one_worker_finished(self):
        self._pending -= 1
        if self._pending > 0:
            return   # 아직 다른 워커가 도는 중 — 전체 완료 처리는 마지막 하나가 담당
        self._reset_generation_ui()
        if self._gen_errors and not self._candidates:
            QMessageBox.warning(self, "AI SVG 에셋 생성",
                                "생성에 실패했습니다:\n" + "\n".join(self._gen_errors))
        elif self._gen_errors:
            QMessageBox.warning(self, "AI SVG 에셋 생성",
                                "일부 후보가 실패했습니다(성공한 후보만 표시):\n"
                                + "\n".join(self._gen_errors))
        self._workers = []

    def _clear_candidates(self):
        if self._quicklook is not None:
            self._quicklook.close()   # 인덱스가 통째로 무의미해지므로 열려 있으면 닫는다
        for card, _svg, _model in self._candidates:
            card.setParent(None)
            card.deleteLater()
        self._candidates = []
        self._selected_card = None
        self._code_edit.clear()   # textChanged가 OK 비활성화·미리보기 초기화까지 처리
        self._hint_label.setVisible(False)
        self._save_symbols_btn.setEnabled(False)
        self._select_all_check.blockSignals(True)   # 새 생성 라운드 — 일괄체크 표시 초기화
        self._select_all_check.setChecked(False)
        self._select_all_check.blockSignals(False)

    def _on_select_all_toggled(self, checked: bool):
        for card, _svg, _model in self._candidates:
            card.set_checked_for_save(checked)

    def _add_candidate(self, model_used: str, svg_text: str):
        # [2026-08-20 자체발견] 다이얼로그가 막 열린 직후 등 아직 `resizeEvent`가 최종
        # 크기로 한 번도 안 온 시점에 후보가 추가되면 `_candidate_cols`가 초기값(또는 오래된
        # 값)에 머물러 있을 수 있다 — 배치 직전에 항상 한 번 최신화(변화 없으면 무비용
        # no-op이라 실사용 경로엔 영향 없음).
        self._update_candidate_columns()
        pm = _render_svg_candidate_pixmap(svg_text, 100, self._preview_pen_color)
        card = _SvgCandidateCard(model_used, svg_text, pm, self._pick_card, self)
        card._save_check.stateChanged.connect(self._refresh_save_symbols_enabled)
        idx = len(self._candidates)
        # [2026-08-20 3차 피드백] 더블클릭 확대가 이제 갤러리 뷰어(`_QuickLookDialog`,
        # 화살표 탐색·n/N)라 svg 텍스트가 아니라 "몇 번째냐"(인덱스)를 넘긴다.
        card.doubleClicked.connect(lambda i=idx: self._show_enlarged_candidate(i))
        row, col = divmod(idx, self._candidate_cols)
        self._candidates_grid.addWidget(card, row, col)
        self._candidates.append((card, svg_text, model_used))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_candidate_columns()

    def _update_candidate_columns(self):
        """[2026-08-20 피드백] "창 크기에 따라 후보 크기도 변하게" — 카드 자체 픽셀
        크기(120×156)는 고정해 리사이즈 드래그마다 SVG를 다시 래스터화하는 비용·버벅임을
        피하고(더블클릭 확대가 이미 "크게 보기" 역할을 함, 손안의 카드), 대신 가용 폭에
        맞춰 **열 개수**를 늘리거나 줄여 넓은 창을 실제로 활용한다. 열 수가 안 바뀌면
        아무 것도 다시 안 그림(매 리사이즈 이벤트마다 무의미한 재배치 방지)."""
        avail = self._candidates_scroll.viewport().width()
        card_w, spacing = 120, 8
        cols = max(1, (avail + spacing) // (card_w + spacing))
        if cols == self._candidate_cols:
            return
        self._candidate_cols = cols
        for idx, (card, _svg, _model) in enumerate(self._candidates):
            row, col = divmod(idx, cols)
            self._candidates_grid.addWidget(card, row, col)

    def _pick_card(self, card: _SvgCandidateCard):
        for c, _svg, _model in self._candidates:
            c.set_selected(c is card)
        self._selected_card = card
        # setPlainText가 textChanged를 발화해 OK 활성화·미리보기 갱신까지 같이 일어난다.
        self._code_edit.setPlainText(card.svg_text())
        # [2026-08-20 3차 피드백] "클릭으로 선택 바꾸면 이미 열린 확대창도 갱신" — 확대창이
        # 열려 있을 때만, 자기 자신을 다시 부르는 `_QuickLookDialog._step`의 역방향.
        if self._quicklook is not None and self._quicklook.isVisible():
            idx = next((i for i, (c, _s, _m) in enumerate(self._candidates) if c is card), None)
            if idx is not None:
                self._quicklook.show_index(idx)

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
        subject = self._prompt_edit.toPlainText().strip()
        saved = save_fn(entries, subject, folder)
        QMessageBox.information(self, "내 심볼로 저장", f"{saved}개를 내 심볼에 저장했습니다.")

