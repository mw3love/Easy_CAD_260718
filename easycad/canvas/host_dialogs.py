"""CanvasWindow이 띄우는 입력 다이얼로그 모음 — 용지 크기/표제란 필드/표 크기/
케이블 채번 접두사/Mermaid 붙여넣기.

2026-08-02 host.py(3635줄) 분할분. host_fileio.py·host_context.py 믹스인이 이 모듈에서
다이얼로그 클래스를 가져다 쓴다. 순환 임포트를 피하려고 host.py·믹스인을 임포트하지 않는
잎(leaf) 모듈이다.
"""
import math

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QSize, QSettings, QEvent
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter,
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
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon, _nearest_border,
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


class _MermaidDialog(QDialog):
    """Mermaid flowchart 입력창 — 설명 텍스트와 Mermaid 코드를 한 칸에서 같이 받는다.

    §8 항목18(AI 이미지→도면) 후속(2026-08-12) — 처음엔 프롬프트 칸과 Mermaid 칸을
    분리했었으나(AI가 실수로 편집 중인 내용을 덮어쓸 위험 때문), 실사용 결과 그 위험보다
    "칸 하나에서 타이핑도 붙여넣기도 다 되고, 키보드만으로 바로 변환"이 훨씬 중요하다는
    피드백으로 단일 칸으로 되돌렸다. 대신 AI 생성 결과 반영은 `setPlainText()`(되돌리기
    스택을 초기화함) 대신 `QTextCursor` 전체선택+치환으로 해 Ctrl+Z로 원래 입력을 복구할
    수 있게 안전망을 남겼다. Ctrl+Enter(칸 안에서)로 마우스 없이 바로 AI 생성 트리거."""

    _SAMPLE = ("예: 날씨를 예보하는 워크플로우\n\n"
               "또는 Mermaid 코드를 직접 붙여넣어도 됩니다:\n"
               "flowchart TD\n"
               "    A[시작] --> B{조건?}\n"
               "    B -->|예| C[처리]\n"
               "    B -->|아니오| D([종료])\n"
               "    C --> D")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid 가져오기")
        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("설명을 입력하거나 Mermaid 코드를 직접 붙여넣으세요:"))
        self._edit = QPlainTextEdit(self)
        self._edit.setPlaceholderText(self._SAMPLE)
        self._edit.setMinimumSize(QSize(460, 280))
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._edit.installEventFilter(self)   # Ctrl+Enter → AI 생성
        lay.addWidget(self._edit)

        control_row = QHBoxLayout()
        self._model_combo = QComboBox(self)
        control_row.addWidget(self._model_combo, 1)
        # [실사용 피드백 2026-08-12] 새 모델이 수시로 나오므로 다이얼로그를 다시 열지
        # 않고도 목록을 즉석에서 다시 불러올 수 있어야 한다는 요청.
        self._refresh_btn = QToolButton(self)
        self._refresh_btn.setIcon(_act_icon("refresh"))
        self._refresh_btn.setToolTip("모델 목록 새로고침")
        self._refresh_btn.clicked.connect(self._populate_models)
        control_row.addWidget(self._refresh_btn)
        self._ai_btn = QToolButton(self)
        self._ai_btn.setIcon(_act_icon("generate"))
        self._ai_btn.setToolTip("AI로 생성 (Ctrl+Enter)")
        self._ai_btn.clicked.connect(self._on_ai_clicked)
        control_row.addWidget(self._ai_btn)
        lay.addLayout(control_row)
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
        if (obj is self._edit and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._on_ai_clicked()
            return True
        return super().eventFilter(obj, event)

    # ---- AI 보조 생성 ---------------------------------------------------------

    def _populate_models(self):
        """게이트웨이 `/models`를 실호출해 gpt·gemini 계열 **전체**를 채우고(`list_text_models`
        — 필터만 걸 뿐 개수 제한은 없다), gemini/gpt 계열을 구분선(`insertSeparator`)으로
        묶어서 보여준다. 계열별 가성비 최선 하나씩(`gateway.TEXT_RECOMMEND_1/2`)에는 금색
        별 아이콘(`_recommend_star_icon`)을 붙인다. 조회 실패(키 없음·네트워크 오류) 시
        추천 둘만으로 조용히 폴백. "새로고침" 버튼이 이 메서드를 그대로 재호출한다."""
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
        other_models = sorted(m for m in pool if m not in gemini_models and m not in gpt_models)

        self._model_combo.clear()
        star = _recommend_star_icon()
        groups = [g for g in (gemini_models, gpt_models, other_models) if g]
        for gi, group in enumerate(groups):
            if gi > 0:
                self._model_combo.insertSeparator(self._model_combo.count())
            for m in group:
                icon = star if m in (r1, r2) else QIcon()
                suffix = " (추천1)" if m == r1 else (" (추천2)" if m == r2 else "")
                self._model_combo.addItem(icon, f"{m}{suffix}", m)
        idx = self._model_combo.findData(r1)
        self._model_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def model(self) -> str:
        return self._model_combo.currentData() or gw.TEXT_RECOMMEND_1

    def _on_ai_clicked(self):
        desc = self._edit.toPlainText().strip()
        if not desc:
            QMessageBox.information(self, "Mermaid 가져오기",
                                    "먼저 설명을 입력하거나 Mermaid 코드를 붙여넣으세요.")
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
            text, used = generate_mermaid(key, desc, model=self.model(), base_url=base_url)
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

    [실사용 피드백 2026-08-12] 이 다이얼로그를 여는 진입점은 더 이상 Mermaid 가져오기
    다이얼로그 안쪽 버튼이 아니다 — CanvasWindow 상단 툴바(항상 노출)로 옮겼다
    (`host_ui.py._open_ai_gateway_settings`). 이 클래스 자체는 무변경."""

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

