"""CanvasWindow이 띄우는 입력 다이얼로그 모음 — 용지 크기/표제란 필드/표 크기/
케이블 채번 접두사/Mermaid 붙여넣기.

2026-08-02 host.py(3635줄) 분할분. host_fileio.py·host_context.py 믹스인이 이 모듈에서
다이얼로그 클래스를 가져다 쓴다. 순환 임포트를 피하려고 host.py·믹스인을 임포트하지 않는
잎(leaf) 모듈이다.
"""
import io
import math
import os

from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QSize, QSettings, QEvent, QBuffer, QIODevice, QByteArray,
)
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter, QImage,
    QFont, QPolygonF, QPainterPath, QPalette, QTextCursor,
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


def _recommend_star_icon(size: int = 14) -> QIcon:
    """모델 드롭다운의 "추천" 배지 — 금색 별. 코랄(#da7756)은 이 앱에서 버튼 상태(체크·
    호버) 전용 색이라(M6 디자인 베이크오프 관례) 배지에 재사용하면 의미가 겹친다 —
    "추천/즐겨찾기"의 흔한 관용색인 금색으로 분리."""
    cached = _RECOMMEND_STAR_CACHE.get(size)
    if cached is not None:
        return cached
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#f5b942"))
    cx, cy, r_out, r_in = size / 2, size / 2, size * 0.48, size * 0.19
    pts = []
    for i in range(10):
        ang = math.pi / 2 + i * math.pi / 5
        r = r_out if i % 2 == 0 else r_in
        pts.append(QPointF(cx + r * math.cos(ang), cy - r * math.sin(ang)))
    p.drawPolygon(QPolygonF(pts))
    p.end()
    icon = QIcon(pm)
    _RECOMMEND_STAR_CACHE[size] = icon
    return icon


_RECOMMEND_STAR_CACHE: dict[int, QIcon] = {}


class _ClickableRow(QWidget):
    """헤더 행 전체가 클릭 가능(모델 패널 접기/펴기) — 자식 버튼(새로고침) 클릭은 Qt가
    자식 위젯에 먼저 전달하므로 자동으로 분리된다(부모까지 안 올라옴)."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(e)


class _MermaidDialog(QDialog):
    """Mermaid flowchart 입력창 — 설명 텍스트/이미지와 Mermaid 코드를 한 칸에서 같이 받는다.

    §8 항목18(AI 이미지→도면) 후속(2026-08-12) — 처음엔 프롬프트 칸과 Mermaid 칸을
    분리했었으나(AI가 실수로 편집 중인 내용을 덮어쓸 위험 때문), 실사용 결과 그 위험보다
    "칸 하나에서 타이핑도 붙여넣기도 다 되고, 키보드만으로 바로 변환"이 훨씬 중요하다는
    피드백으로 단일 칸으로 되돌렸다. 대신 AI 생성 결과 반영은 `setPlainText()`(되돌리기
    스택을 초기화함) 대신 `QTextCursor` 전체선택+치환으로 해 Ctrl+Z로 원래 입력을 복구할
    수 있게 안전망을 남겼다. Ctrl+Enter(칸 안에서)로 마우스 없이 바로 AI 생성 트리거.

    이미지 입력도 받는다(찾아보기·드래그드롭·Ctrl+V, 옛 `_AIImageImportDialog`와 같은
    3경로). 이미지가 첨부되면 텍스트 칸은 "보충 설명(선택)"으로 격하되고
    (`text_to_mermaid.generate_mermaid`의 `image` 인자), 좌표 없는 Mermaid 출력이라 옛
    파이프라인처럼 타일링·좌표 복원이 전혀 필요 없다 — 단일 vision 호출뿐.
    ⚠ 모델 목록은 텍스트 전용 목록(`list_text_models`)을 그대로 재사용한다 — 이
    게이트웨이에서 어떤 gpt/gemini 항목이 실제로 이미지 입력을 받는지는 실키로 확인 못
    했다(Not-tested, 실사용 중 특정 모델이 이미지를 거부하면 다른 모델로 바꿔 재시도).

    **디자인 베이크오프 라운드 2(2026-08-12) 반영** — 첨부·생성 버튼을 입력칸 테두리
    안쪽에 내장(사용자 피드백: "생성 버튼이 입력칸과 종속되게 느껴지길 원함"). Qt는 HTML
    처럼 textarea 안에 진짜 겹쳐 그리는 게 아니라, `_edit`의 자식 위젯으로 버튼을 만들고
    `setViewportMargins()`로 텍스트 뷰포트 자체를 줄여 그 여백에 버튼을 놓는 방식(텍스트가
    스크롤돼도 버튼 밑을 지나가지 않도록 진짜 공간을 예약 — CSS padding 방식보다 안전).
    모델 선택은 "접으면 요약 한 줄(G2 스타일) / 펼치면 gemini·gpt 2열 병렬 패널(G4 스타일)"
    하나로 합쳤다 — `_model_header`(클릭 시 토글) + `_model_body`(두 열, 라디오버튼)."""

    _SAMPLE = ("예: 날씨를 예보하는 워크플로우\n\n"
               "또는 Mermaid 코드를 직접 붙여넣어도 됩니다:\n"
               "flowchart TD\n"
               "    A[시작] --> B{조건?}\n"
               "    B -->|예| C[처리]\n"
               "    B -->|아니오| D([종료])\n"
               "    C --> D")

    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")
    _EMBED_MARGIN = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid 가져오기")
        self.setAcceptDrops(True)
        self._attached_image = None       # PIL.Image.Image | None
        self._attached_image_name = ""
        lay = QVBoxLayout(self)

        # [2026-08-12 피드백] 첨부(회색)·AI생성(코랄) 두 버튼이 입력칸 안에 같이 있으니
        # 색이 달라 "같은 창의 한 툴바"로 안 읽혔다(사용자: "서로 다른 색이라 같은 칸인 줄
        # 몰랐다") — 첨부는 라벨 줄로 빼 완전히 분리하고, 입력칸 안에는 AI 버튼 하나만
        # 남겨 그 영역 전체가 "코랄=AI 생성"이라는 단일 색 의미로 읽히게 한다.
        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("설명을 입력하거나 Mermaid 코드를 직접 붙여넣으세요"
                             "(드래그드롭·Ctrl+V로 이미지 첨부 가능):"), 1)
        self._attach_btn = QToolButton(self)
        self._attach_btn.setIcon(_act_icon("attach"))
        self._attach_btn.setToolTip("이미지 첨부(드래그드롭·Ctrl+V도 가능)")
        self._attach_btn.clicked.connect(self._browse_image)
        label_row.addWidget(self._attach_btn)
        lay.addLayout(label_row)

        self._edit = QPlainTextEdit(self)
        self._edit.setPlaceholderText(self._SAMPLE)
        self._edit.setMinimumSize(QSize(460, 280))
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._edit.setAcceptDrops(False)   # 드롭을 이 다이얼로그(dropEvent)로 넘김
        self._edit.installEventFilter(self)   # Ctrl+Enter·이미지 붙여넣기·리사이즈 재배치
        # AI 생성 버튼이 앉을 공간을 텍스트 뷰포트 자체에서 예약(패딩이 아니라 진짜
        # 레이아웃 여백이라 스크롤해도 버튼 밑으로 글자가 절대 지나가지 않는다).
        self._edit.setViewportMargins(0, 0, 0, 44)
        lay.addWidget(self._edit)

        self._ai_btn = QToolButton(self._edit)
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
        self._ai_btn.setToolTip("AI로 생성 (Ctrl+Enter)")
        self._ai_btn.clicked.connect(self._on_ai_clicked)
        self._ai_btn.setStyleSheet(
            "QToolButton { background: #da7756; border: none; border-radius: 7px; }"
            "QToolButton:hover { background: #e08a6c; }"
            "QToolButton:pressed { background: #c2673f; }"
            "QToolButton:disabled { background: #6b5148; }"   # 채도 낮춘 비활성 코랄
        )
        self._reposition_embedded_buttons()

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

        # ---- 모델 선택: 접이식(요약 한 줄) / 펼침(gemini·gpt 2열 병렬) ----------
        self._model_frame = QFrame(self)
        self._model_frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_lay = QVBoxLayout(self._model_frame)
        frame_lay.setContentsMargins(0, 0, 0, 0)
        frame_lay.setSpacing(0)

        self._model_header = _ClickableRow(self._toggle_model_panel, self._model_frame)
        header_lay = QHBoxLayout(self._model_header)
        header_lay.setContentsMargins(10, 8, 8, 8)
        self._model_chevron = QLabel("▸", self._model_header)
        header_lay.addWidget(self._model_chevron)
        self._model_summary = QLabel("", self._model_header)
        header_lay.addWidget(self._model_summary, 1)
        # [2026-08-12 재피드백] 게이트웨이 설정(주소·키·연결테스트)이 한때 상단 메뉴/툴바로
        # 나갔었는데(상시 노출 목적), 실사용 결과 "Mermaid 창 안에 있어야 한다"(예전 방식)로
        # 되돌림 — CanvasWindow의 메뉴·툴바 액션은 제거하고 여기 버튼 하나로 흡수.
        self._settings_btn = QToolButton(self._model_header)
        self._settings_btn.setIcon(_act_icon("settings"))
        self._settings_btn.setToolTip("AI 게이트웨이 설정(주소·키)")
        self._settings_btn.clicked.connect(self._open_gateway_settings)
        header_lay.addWidget(self._settings_btn)
        # [실사용 피드백 2026-08-12] 새 모델이 수시로 나오므로 다이얼로그를 다시 열지
        # 않고도 목록을 즉석에서 다시 불러올 수 있어야 한다는 요청.
        self._refresh_btn = QToolButton(self._model_header)
        self._refresh_btn.setIcon(_act_icon("refresh"))
        self._refresh_btn.setToolTip("모델 목록 새로고침")
        self._refresh_btn.clicked.connect(self._populate_models)
        header_lay.addWidget(self._refresh_btn)
        frame_lay.addWidget(self._model_header)

        self._model_body = QWidget(self._model_frame)
        body_lay = QHBoxLayout(self._model_body)
        body_lay.setContentsMargins(10, 8, 10, 10)
        self._gemini_col = QVBoxLayout()
        self._gpt_col = QVBoxLayout()
        body_lay.addLayout(self._gemini_col)
        body_lay.addLayout(self._gpt_col)
        self._model_body.setVisible(False)
        frame_lay.addWidget(self._model_body)

        self._model_group = QButtonGroup(self)
        lay.addWidget(self._model_frame)
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
        if obj is self._edit and event.type() == QEvent.Type.Resize:
            self._reposition_embedded_buttons()
        if obj is self._edit and event.type() == QEvent.Type.KeyPress:
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
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

    def _reposition_embedded_buttons(self):
        """`_edit`(QPlainTextEdit) 자식으로 얹은 AI생성 버튼을 우하단 여백에 배치(첨부는
        2026-08-12부터 라벨 줄로 분리돼 더 이상 여기서 다루지 않음). `eventFilter`의
        Resize 이벤트가 다이얼로그 크기 변경 때마다 재호출한다."""
        m = self._EMBED_MARGIN
        er = self._edit.rect()
        self._ai_btn.move(er.width() - self._ai_btn.sizeHint().width() - m,
                          er.height() - self._ai_btn.sizeHint().height() - m)

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

    # ---- 모델 선택(접이식 병렬 패널) --------------------------------------------

    def _open_gateway_settings(self):
        """[2026-08-12] `_AIGatewaySettingsDialog`(주소·키·연결테스트, 클래스 자체는 무변경)를
        이 Mermaid 창의 자식 모달로 연다 — 예전(CanvasWindow 상위 메뉴/툴바로 옮기기 전)
        방식으로 되돌림. 주소/키가 바뀌었을 수 있으니 닫힌 뒤 모델 목록을 다시 불러온다."""
        if _AIGatewaySettingsDialog(self).exec() == QDialog.DialogCode.Accepted:
            self._populate_models()

    def _toggle_model_panel(self):
        opening = self._model_body.isHidden()
        self._model_body.setVisible(opening)
        self._model_chevron.setText("▾" if opening else "▸")

    def _clear_model_columns(self):
        for btn in list(self._model_group.buttons()):
            self._model_group.removeButton(btn)
            btn.deleteLater()
        for col in (self._gemini_col, self._gpt_col):
            while col.count():
                item = col.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()

    def _populate_models(self):
        """게이트웨이 `/models`를 실호출해 gpt·gemini 계열 **전체**를 채우고(`list_text_models`
        — 필터만 걸 뿐 개수 제한은 없다), gemini·gpt를 2열 병렬 패널(`_gemini_col`/
        `_gpt_col`)로 나눠 보여준다(디자인 베이크오프 라운드 2, "G4처럼 병렬로" 반영).
        계열별 가성비 최선 하나씩(`gateway.TEXT_RECOMMEND_1/2`)에는 금색 별 아이콘
        (`_recommend_star_icon`)을 붙인다. 조회 실패(키 없음·네트워크 오류) 시 추천
        둘만으로 조용히 폴백. "새로고침" 버튼이 이 메서드를 그대로 재호출한다."""
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

        self._clear_model_columns()
        star = _recommend_star_icon()

        def add_column(layout, group_models):
            for m in group_models:
                suffix = " (추천1)" if m == r1 else (" (추천2)" if m == r2 else "")
                rb = QRadioButton(f"{m}{suffix}", self._model_body)
                rb.setProperty("model_id", m)
                if m in (r1, r2):
                    rb.setIcon(star)
                rb.toggled.connect(lambda checked: self._update_model_summary() if checked else None)
                layout.addWidget(rb)
                self._model_group.addButton(rb)
                if m == r1:
                    rb.setChecked(True)

        add_column(self._gemini_col, gemini_models)
        add_column(self._gpt_col, gpt_models)
        if self._model_group.checkedButton() is None:
            first = self._model_group.buttons()[0] if self._model_group.buttons() else None
            if first is not None:
                first.setChecked(True)
        self._update_model_summary()

    def _update_model_summary(self):
        checked = self._model_group.checkedButton()
        if checked is None:
            self._model_summary.setText("(모델 없음)")
            return
        prefix = "★ " if not checked.icon().isNull() else ""
        self._model_summary.setText(f"{prefix}{checked.text()}")

    def model(self) -> str:
        checked = self._model_group.checkedButton()
        if checked is not None:
            return checked.property("model_id") or gw.TEXT_RECOMMEND_1
        return gw.TEXT_RECOMMEND_1

    def _on_ai_clicked(self):
        desc = self._edit.toPlainText().strip()
        image = self._attached_image
        if not desc and image is None:
            QMessageBox.information(self, "Mermaid 가져오기",
                                    "먼저 설명을 입력하거나 Mermaid 코드를 붙여넣거나, "
                                    "이미지를 첨부하세요.")
            return
        key = gw.resolve_api_key()
        if not key:
            QMessageBox.warning(self, "Mermaid 가져오기",
                                "게이트웨이 API 키가 없습니다. "
                                "상단 툴바의 'AI 게이트웨이 설정'에서 입력해 주세요.")
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
        # [단일 입력칸 통합 시 안전망] setPlainText()는 되돌리기 스택을 초기화해버려
        # 입력한 원문을 잃는다 — QTextCursor 전체선택+치환은 이 칸 자체의 undo 스택에
        # 남아 Ctrl+Z로 AI 생성 전 내용(오타로 잘못 눌렀을 때 등)을 복구할 수 있다.
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
    """AI 게이트웨이 연결 설정 — 게이트웨이 주소 + API 키를 앱 안에서 직접 입력·저장·
    테스트한다(2026-08-12, 실사용 요청).

    이전엔 secrets 파일(`~/.claude/.secrets/easycad-gateway.key`)이나 환경변수로만 키를
    넣을 수 있어 앱만 켜서 쓰는 사용자에겐 진입장벽이었다. OK를 눌러야 QSettings에
    저장된다(Cancel은 변경 폐기) — `resolve_api_key`의 우선순위 사슬에서 QSettings는
    secrets 파일보다 아래이므로, secrets 파일이 이미 있으면 이 창에서 바꿔도 secrets
    파일 쪽이 계속 우선한다(의도된 동작 — 파일 관례가 더 안전한 소스).

    [실사용 피드백 2026-08-12] 진입점이 한때 CanvasWindow 상단 메뉴/툴바(항상 노출)로
    나갔다가, 재피드백으로 다시 `_MermaidDialog._open_gateway_settings`(모델 목록 헤더의
    설정 버튼)로 돌아왔다 — Mermaid 가져오기를 열 때만 필요한 설정이라 그 창 밖에 있으면
    맥락이 끊긴다는 지적. 이 클래스 자체는 두 진입점 어느 쪽이든 무변경으로 재사용 가능."""

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

        test_row = QHBoxLayout()
        self._test_btn = QToolButton(self)
        self._test_btn.setIcon(_act_icon("connect"))
        self._test_btn.setToolTip("연결 테스트")
        self._test_btn.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self._test_btn)
        self._test_label = QLabel("", self)
        test_row.addWidget(self._test_label, 1)
        lay.addLayout(test_row)

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
        key = self.api_key()
        if not key:
            self._test_label.setText("API 키를 입력하세요.")
            return
        self._test_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            models = gw.list_models(key, self.base_url(), timeout=10.0)
        except Exception as e:
            self._test_label.setText(f"실패: {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self._test_btn.setEnabled(True)
        self._test_label.setText(f"연결 성공 — 모델 {len(models)}개 확인")

    def _on_accept(self):
        gw.store_base_url(self.base_url())
        gw.store_api_key(self.api_key())
        self.accept()

