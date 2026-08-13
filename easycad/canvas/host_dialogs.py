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
    QFontMetrics,
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
from easycad.canvas.host_widgets import _clipboard_pixmap, _act_icon, _ACCENT_CORAL
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
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid 가져오기")
        self.setAcceptDrops(True)
        self._attached_image = None       # PIL.Image.Image | None
        self._attached_image_name = ""
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
        prompt_frame.setStyleSheet(
            "QFrame#promptCard { border:1px solid rgba(128,128,128,90); border-radius:8px; "
            f"background:{'#e7e0d6' if dark else 'palette(base)'}; }}"
        )
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
        # (2026-08-12 4차, "이미지첨부 자리에 썸네일만 작게" 피드백).
        self._image_chip = QWidget(toolbar_widget)
        self._image_chip.setObjectName("imageChip")
        self._image_chip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._image_chip.setStyleSheet(
            "QWidget#imageChip { background:palette(alternate-base); "
            "border:1px solid rgba(128,128,128,90); border-radius:11px; }"
        )
        chip_lay = QHBoxLayout(self._image_chip)
        chip_lay.setContentsMargins(3, 2, 4, 2)
        chip_lay.setSpacing(4)
        self._image_thumb = QLabel(self._image_chip)
        self._image_thumb.setFixedSize(20, 20)
        self._image_thumb.setScaledContents(True)
        chip_lay.addWidget(self._image_thumb)
        self._image_name_label = QLabel("", self._image_chip)
        self._image_name_label.setStyleSheet("font-size:11px;")
        self._image_name_label.setMaximumWidth(140)
        chip_lay.addWidget(self._image_name_label)
        self._image_clear_btn = QToolButton(self._image_chip)
        self._image_clear_btn.setText("✕")
        self._image_clear_btn.setToolTip("이미지 제거")
        self._image_clear_btn.setFixedSize(16, 16)
        self._image_clear_btn.clicked.connect(self._clear_image)
        chip_lay.addWidget(self._image_clear_btn)
        self._image_chip.setVisible(False)
        toolbar_lay.addWidget(self._image_chip)

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
        lay.addWidget(prompt_frame)

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
        self._model_refresh_btn = QToolButton(self)
        self._model_refresh_btn.setIcon(_act_icon("refresh"))
        self._model_refresh_btn.setToolTip("모델 목록 새로고침")
        self._model_refresh_btn.clicked.connect(self._populate_models)
        model_row.addWidget(self._model_refresh_btn)
        self._settings_btn = QToolButton(self)
        self._settings_btn.setIcon(_act_icon("settings"))
        self._settings_btn.setToolTip("AI 게이트웨이 설정(주소·키·모델 새로고침·크레딧 확인)")
        self._settings_btn.clicked.connect(self._open_gateway_settings)
        model_row.addWidget(self._settings_btn)
        lay.addLayout(model_row)
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
        lay.addLayout(connector_row)

        # ---- 2번 칸: Mermaid 코드(넉넉함) — AI 결과가 채워지거나 직접 타이핑/붙여넣기 ----
        # [2026-08-13 5차] 옛 상단 힌트 3번째 줄("아래 칸에 직접 입력·붙여넣기 가능")을
        # 라벨에 흡수.
        lay.addWidget(QLabel("Mermaid 코드 (직접 입력·붙여넣기 가능):", self))
        self._edit = QPlainTextEdit(self)
        self._edit.setPlaceholderText(self._SAMPLE)
        self._edit.setMinimumSize(QSize(460, 260))
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self._edit)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(_CORAL_BTN_QSS)
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
        # 칩 폭이 좁아졌으니(2026-08-12 4차, 컴팩트 칩) 긴 파일명은 가운데 생략 — 전체
        # 이름은 툴팁으로.
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
            text, _used = generate_mermaid(key, desc, model=self.model(), base_url=base_url,
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
        # [2026-08-12 4차, 디자인 시안 합의] 크레딧 잔액 표시는 이 창에서 제거하고
        # `_AIGatewaySettingsDialog`의 "연결 테스트" 한 곳으로 통합했다(중복 표시 제거).


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

