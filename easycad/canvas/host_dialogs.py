"""CanvasWindow이 띄우는 입력 다이얼로그 모음 — 용지 크기/표제란 필드/표 크기/
케이블 채번 접두사/Mermaid 붙여넣기.

2026-08-02 host.py(3635줄) 분할분. host_fileio.py·host_context.py 믹스인이 이 모듈에서
다이얼로그 클래스를 가져다 쓴다. 순환 임포트를 피하려고 host.py·믹스인을 임포트하지 않는
잎(leaf) 모듈이다.
"""
import os
import re
import tempfile

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QSize, QSettings, QTimer, QMimeData, QEvent
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter, QImage,
    QFont, QPolygonF, QPainterPath, QPalette, QDrag,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPlainTextEdit,
    QSizePolicy, QColorDialog, QHBoxLayout, QMenu, QFrame,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup, QProgressBar,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon, _nearest_border,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
)
from easycad.canvas.host_widgets import _clipboard_pixmap
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
    """이미지 선택(찾아보기·드래그드롭·Ctrl+V 전부 가능) + 보충설명 + 모델 선택.
    확인 버튼은 이미지를 고르기 전엔 비활성 — 파이프라인은 몇 분 걸리므로 빈 경로로
    시작해 사용자를 헷갈리게 하지 않는다.

    ⚠ 드래그드롭·Ctrl+V는 이 다이얼로그가 열려 있을 때만 받는다 — 캔버스 자체의 드롭·
    붙여넣기(기존 "그림으로 삽입" 동작, `host_fileio.py`/`host_selection.py`)와 겹치면
    안 되므로 건드리지 않고, 이 다이얼로그의 이벤트만 오버라이드했다(2026-08-11)."""

    _IMAGE_FILTER = "이미지 (*.png *.jpg *.jpeg *.bmp *.webp)"
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")
    _OVERVIEW_DEFAULT = gw.DEFAULT_MODEL       # P1 개괄 — 실측 기본(전체 이미지 완주)
    _TILE_DEFAULT = "gpt-5.4-mini"             # P2 타일 — 2026-08-11 4모델 실측 비교로 확정
                                                # (claude-sonnet-5와 shapes·edges 동일, 비용 1/18)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 이미지→도면")
        self.setAcceptDrops(True)
        self._temp_image_path = None   # Ctrl+V/이미지데이터 드롭으로 만든 임시 PNG(정리 대상)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("도면 이미지를 골라주세요(찾아보기 · 드래그드롭 · Ctrl+V 전부 가능):"))

        row = QHBoxLayout()
        self._path_edit = QLineEdit(self)
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("이미지를 여기로 끌어놓거나 Ctrl+V로 붙여넣어도 됩니다…")
        row.addWidget(self._path_edit)
        browse = QToolButton(self)
        browse.setText("찾아보기…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        lay.addLayout(row)

        # [실사용 피드백 2026-08-11] 이미지니까 어떤 걸 골랐는지 눈으로 바로 확인되면 좋겠다는
        # 요청 — 선택/붙여넣기/드롭 직후 작은 썸네일을 보여준다.
        self._thumb_label = QLabel(self)
        self._thumb_label.setFixedSize(160, 100)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("border: 1px solid palette(mid);")
        self._thumb_label.setText("(미리보기 없음)")
        lay.addWidget(self._thumb_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Ctrl+V가 안 먹던 실사용 버그(2026-08-11) — QDialog.keyPressEvent를 오버라이드해도
        # 포커스가 있는 자식 위젯(QLineEdit/QPlainTextEdit)이 표준 붙여넣기 키를 자기
        # keyPressEvent 안에서 먼저 처리·accept()해버려 부모까지 이벤트가 올라오지 않는다
        # (Qt의 흔한 함정 — 다이얼로그 레벨 keyPressEvent는 포커스 위젯이 그 키를 명시적으로
        # 안 쓸 때만 도달한다). 포커스를 받을 수 있는 위젯에 이벤트 필터를 직접 걸어야
        # 실제로 가로채진다.
        self._path_edit.installEventFilter(self)

        lay.addWidget(QLabel("보충설명(도면 종류 등, 생략 가능):"))
        self._note_edit = QPlainTextEdit(self)
        self._note_edit.setPlaceholderText("예: 방송 송신소 계통도, 굵은 실선만 실제 연결선")
        self._note_edit.setMaximumHeight(70)
        self._note_edit.installEventFilter(self)
        lay.addWidget(self._note_edit)

        model_grid = QGridLayout()
        model_grid.addWidget(QLabel("개요 모델(P1, 전체 훑기):"), 0, 0)
        self._overview_combo = QComboBox(self)
        model_grid.addWidget(self._overview_combo, 0, 1)
        model_grid.addWidget(QLabel("세부 모델(P2, 구획 확대):"), 1, 0)
        self._tile_combo = QComboBox(self)
        model_grid.addWidget(self._tile_combo, 1, 1)
        lay.addLayout(model_grid)
        self._populate_models()

        lay.addWidget(QLabel("⚠ 밀집 도면은 여러 번 나눠 인식해 수 분 걸릴 수 있습니다."))

        self._btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                      | QDialogButtonBox.StandardButton.Cancel, self)
        self._btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._btns.accepted.connect(self.accept)
        self._btns.rejected.connect(self.reject)
        lay.addWidget(self._btns)

    # ---- 모델 목록 ----------------------------------------------------------

    def _populate_models(self):
        """게이트웨이 `/models`를 실호출해 전체 목록을 채우고 실측 기본값을 "(추천)"으로
        표시·사전선택한다. 짧은 timeout(8초)로 호출 — 이 메서드는 다이얼로그 `__init__`
        안에서 동기 호출되므로(별도 스레드를 안 씀 — 보통 1초 내외라 그 정도 지연은
        감수할 만하다는 판단), 네트워크가 죽어 있을 때 기본 600초 타임아웃을 그대로
        물려받으면 다이얼로그 자체가 못 뜬다. 조회 실패 시 기본값 둘만으로 조용히 폴백."""
        models: list[str] = []
        try:
            key = gw.resolve_api_key()
            if key:
                models = gw.list_models(key, timeout=8.0)
        except Exception:
            models = []
        pool = sorted(set(models) | {self._OVERVIEW_DEFAULT, self._TILE_DEFAULT})
        for combo, default in ((self._overview_combo, self._OVERVIEW_DEFAULT),
                               (self._tile_combo, self._TILE_DEFAULT)):
            combo.clear()
            for m in pool:
                combo.addItem(f"{m} (추천)" if m == default else m, m)
            idx = combo.findData(default)
            combo.setCurrentIndex(idx if idx >= 0 else 0)

    def overview_model(self) -> str:
        return self._overview_combo.currentData() or self._OVERVIEW_DEFAULT

    def tile_model(self) -> str:
        return self._tile_combo.currentData() or self._TILE_DEFAULT

    # ---- 이미지 입력(찾아보기·드래그드롭·Ctrl+V) ------------------------------

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "이미지 선택", "", self._IMAGE_FILTER)
        if path:
            self._set_image_path(path)

    def _set_image_path(self, path: str):
        self._path_edit.setText(path)
        self._btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(path))
        pm = QPixmap(path)
        if pm.isNull():
            self._thumb_label.setText("(미리보기 없음)")
            self._thumb_label.setPixmap(QPixmap())
        else:
            self._thumb_label.setText("")
            self._thumb_label.setPixmap(pm.scaled(
                self._thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def _save_temp_image(self, pm: QPixmap) -> str:
        fd, path = tempfile.mkstemp(suffix=".png", prefix="ai_sketch_paste_")
        os.close(fd)
        pm.save(path, "PNG")
        self._temp_image_path = path
        return path

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
                    self._set_image_path(p)
                    e.acceptProposedAction()
                    return
        if md.hasImage():
            img = md.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self._set_image_path(self._save_temp_image(QPixmap.fromImage(img)))
                e.acceptProposedAction()

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.KeyPress and event.matches(QKeySequence.StandardKey.Paste)
                and obj in (self._path_edit, self._note_edit)):
            md = QApplication.clipboard().mimeData()
            has_image = md.hasImage() or (md.hasUrls() and any(
                u.toLocalFile().lower().endswith(self._IMG_EXTS) for u in md.urls()))
            # path_edit는 읽기전용이라 텍스트 붙여넣기가 의미 없어 항상 가로챈다.
            # note_edit는 진짜 텍스트 입력창이므로, 클립보드에 이미지가 있을 때만 가로채고
            # 아니면(보통의 텍스트 붙여넣기) 위젯의 기본 동작에 그대로 맡긴다.
            if obj is self._path_edit or has_image:
                self._paste_from_clipboard()
                return True
        return super().eventFilter(obj, event)

    def _paste_from_clipboard(self):
        md = QApplication.clipboard().mimeData()
        if md.hasUrls():
            for u in md.urls():
                p = u.toLocalFile()
                if p and p.lower().endswith(self._IMG_EXTS):
                    self._set_image_path(p)
                    return
        pm = _clipboard_pixmap()
        if pm is not None and not pm.isNull():
            self._set_image_path(self._save_temp_image(pm))

    def image_path(self) -> str:
        return self._path_edit.text()

    def note(self) -> str:
        return self._note_edit.toPlainText().strip()

    def cleanup_temp_image(self):
        """Ctrl+V/이미지데이터 드롭으로 만든 임시 파일 정리 — 호출자가 파이프라인이
        이미지를 다 읽은 뒤(또는 다이얼로그가 취소된 뒤) 명시적으로 부른다."""
        if self._temp_image_path:
            try:
                os.remove(self._temp_image_path)
            except OSError:
                pass
            self._temp_image_path = None


class _AISketchProgressDialog(QDialog):
    """AI 이미지→도면 처리 중 진행 상태를 보여주는 모달. 닫기(X) 버튼을 없앴다 —
    진행 중인 게이트웨이 호출을 안전하게 중단할 방법이 없어 취소는 이번 라운드
    스코프 밖(`host_ai.py` 참조), 닫기를 허용하면 "취소됐다"는 착각을 줄 수 있다.

    진행 막대는 P2 타일 단계에서만 결정형(N개 중 몇 번째)이다 — P1은 몇 초 걸릴지
    호출 전엔 알 수 없어 무한 로딩으로 둔다(정확한 ETA는 실측상 호출별 편차가
    15~56초로 커서 신빙성 있게 못 낸다, `docs/ai_image_import.md` 참조 — 대신 경과
    시간만 보여준다)."""

    _TILE_RE = re.compile(r"\[P2 타일 (\d+)/(\d+)\]")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 이미지→도면 — 처리 중")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("도면을 분석하는 중입니다 — 밀집 도면은 수 분 걸릴 수 있습니다."))

        status_row = QHBoxLayout()
        self._status_label = QLabel("준비 중…", self)
        status_row.addWidget(self._status_label, 1)
        self._elapsed_label = QLabel("경과: 0:00", self)
        status_row.addWidget(self._elapsed_label)
        lay.addLayout(status_row)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)   # 시작은 무한 로딩(P1)
        lay.addWidget(self._progress)

        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMinimumSize(QSize(440, 220))
        lay.addWidget(self._log)

        self._elapsed_sec = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_elapsed)

    def showEvent(self, e):
        super().showEvent(e)
        self._elapsed_sec = 0
        self._elapsed_label.setText("경과: 0:00")
        self._timer.start(1000)

    def _tick_elapsed(self):
        self._elapsed_sec += 1
        m, s = divmod(self._elapsed_sec, 60)
        self._elapsed_label.setText(f"경과: {m}:{s:02d}")

    def append(self, msg: str):
        self._log.appendPlainText(msg)
        self._status_label.setText(msg)
        m = self._TILE_RE.search(msg)
        if m:
            i, n = int(m.group(1)) + 1, int(m.group(2))   # 완료 개수 느낌으로 1-based 표시
            self._progress.setRange(0, n)
            self._progress.setValue(i)

    def accept(self):
        self._timer.stop()
        super().accept()

    def reject(self):
        self._timer.stop()
        super().reject()
