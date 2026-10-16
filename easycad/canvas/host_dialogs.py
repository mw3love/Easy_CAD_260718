"""CanvasWindow이 띄우는 입력 다이얼로그 모음 — 용지 크기/표제란 필드/표 크기/
케이블 채번 접두사/단축키/AI 게이트웨이 설정, 그리고 「AI로 만들기」 패널이 쓰는 생성 워커·모델
목록 도우미(§8 항목36 6단계에서 옛 Mermaid·SVG 생성 창은 지움).

2026-08-02 host.py(3635줄) 분할분. host_fileio.py·host_context.py 믹스인이 이 모듈에서
다이얼로그 클래스를 가져다 쓴다. 순환 임포트를 피하려고 host.py·믹스인을 임포트하지 않는
잎(leaf) 모듈이다.
"""
import html
import io
import os
import re

from PyQt6.QtCore import (
    Qt, QSize, QBuffer, QIODevice, QByteArray, QThread, pyqtSignal,
)
from PyQt6.QtGui import (
    QKeySequence, QPixmap, QImage,
    QStandardItemModel, QStandardItem, QFontMetrics,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QToolButton, QLabel,
    QFileDialog, QMessageBox, QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QCheckBox, QHBoxLayout,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup, QScrollArea,
    QKeySequenceEdit,
)

from easycad.canvas.annotator_core import (
    PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
)
from easycad.canvas.host_widgets import (
    _ACCENT_CORAL, _act_icon, _current_icon_color,
)
from easycad.fileio.pdf_export import (
    render_preview, _list_title_frames, _reading_order, _DEFAULT_MARGINS_MM,
)
from easycad.fileio import symbol_library
from easycad.ai import gateway as gw
from easycad.ai.text_to_svg import generate_svg
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


def _attach_button_qss(col: str) -> str:
    """[실사용 피드백 2026-08-26 4차] `_ImageAttachMixin._build_attach_button`(이미지 첨부
    "+" 버튼)의 스타일시트를 함수로 뽑았다 — 이 버튼도 `_SECTION_TITLE_QSS`가 걸린 라벨과
    같은 문제(색이 생성 시점에 박제돼 팔레트만 바뀌어선 재도색이 안 됨)를 겪고 있었다.
    `_refresh_theme_colors()`가 현재 `_current_icon_color()`로 다시 걸어 재폴리시한다."""
    return (
        f"QToolButton {{ color:{col}; font-weight:700; font-size:18px; "
        "border:1px solid rgba(128,128,128,90); border-radius:6px; }"
        "QToolButton:hover { background:rgba(128,128,128,40); }"
    )

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
        # [§8 항목30, 2026-10-03] 여러 페이지 → PDF 1개 여러 쪽(사용자 결정: 배치 순서, 체크로
        # 고르기·기본 전부, PDF만). 프레임이 2개 이상이면 기본으로 켠다 — 끄면 위 드롭다운으로
        # 한 페이지만 내던 예전 방식 그대로.
        self._multi_cb = QCheckBox("모든 페이지를 한 PDF로 (여러 쪽)", self)
        self._multi_cb.setChecked(len(self._frames) >= 2)
        opts.addWidget(self._multi_cb)
        self._page_list = QListWidget(self)
        for i, fr in enumerate(_reading_order(self._frames)):
            item = QListWidgetItem(f"{i + 1}쪽 · {_frame_label(fr, i + 1)}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, fr)
            self._page_list.addItem(item)
        self._page_list.setMaximumHeight(140)
        opts.addWidget(self._page_list)
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
        self._format_cb.currentIndexChanged.connect(self._refresh)   # [항목30] 여러 쪽은 PDF만
        self._multi_cb.toggled.connect(self._refresh)
        self._page_list.itemChanged.connect(self._refresh)
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
        label = self._FORMAT_OK_LABEL[self._format()]
        if self._multi_active():
            n = len(self._checked_pages())
            label = f"{label} ({n}쪽)"
            self._ok_btn.setEnabled(n > 0)
        else:
            self._ok_btn.setEnabled(True)
        self._ok_btn.setText(label)

    def _multi_active(self) -> bool:
        """[§8 항목30] 여러 쪽 모드 — 프레임 2개+ · 전체 도면 · PDF · 체크 켜짐일 때만."""
        return (len(self._frames) >= 2 and not self._selection_only()
                and self._format() == "pdf" and self._multi_cb.isChecked())

    def _checked_pages(self) -> list:
        """체크된 페이지를 목록 순서(=캔버스 배치 순서)대로."""
        return [self._page_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self._page_list.count())
                if self._page_list.item(i).checkState() == Qt.CheckState.Checked]

    def _selection_only(self) -> bool:
        return self._rb_sel.isChecked()

    def _current_frame(self):
        """[다중 페이지 지원, 2026-08-14] 프레임 0개=None, 1개=그것, 2개+=드롭다운이 고른 것.
        [§8 항목30] 여러 쪽 모드면 미리보기용으로 체크된 첫 페이지(없으면 None)."""
        if not self._frames:
            return None
        if len(self._frames) == 1:
            return self._frames[0]
        if self._multi_active():
            pages = self._checked_pages()
            return pages[0] if pages else None
        return self._frame_cb.currentData()

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
        # [§8 항목30] 여러 쪽 모드면 드롭다운 대신 체크 목록.
        multi_ok = (len(self._frames) >= 2 and not self._selection_only()
                    and self._format() == "pdf")
        self._multi_cb.setVisible(multi_ok)
        self._page_list.setVisible(self._multi_active())
        self._frame_cb.setVisible(len(self._frames) >= 2 and not self._selection_only()
                                  and not self._multi_active())
        self._refresh_ok_label()
        if self._multi_active() and frame is None:   # 체크된 페이지가 하나도 없음
            self._preview.setPixmap(QPixmap())
            self._preview.setText("내보낼 페이지를 하나 이상 고르세요.")
            return
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
            # [§8 항목30] 여러 쪽 모드면 체크된 페이지(배치 순서), 아니면 None
            "pages": self._checked_pages() if self._multi_active() else None,
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
        btn.setStyleSheet(_attach_button_qss(_current_icon_color().name()))
        btn.setToolTip("이미지 첨부<br>· 드래그 앤 드롭<br>· Ctrl+V 붙여넣기")
        btn.clicked.connect(self._browse_image)
        return btn

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "이미지 선택", "", "이미지 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)")
        if path:
            self._load_image_path(path)

    def _load_image_path(self, path: str):
        from PIL import Image, ImageOps
        try:
            # 폰 사진은 누운 채 저장하고 "돌려서 보여라" 표시(EXIF 방향)만 붙이는 일이 많다 — 그대로 열면 90° 누워 보임(2026-10-06).
            img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
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


class _MermaidGenWorker(QThread):
    """`generate_mermaid` 1회 호출을 메인(GUI) 스레드 밖에서 돈다(2026-08-19 —
    동기 호출+`WaitCursor`가 게이트웨이 응답을 기다리는 동안 이벤트 루프 자체를 막아
    창이 완전히 멈춘 것처럼 보이던 문제 수정). 성공/실패를 시그널로 알린다 — 수신자
    (`_MermaidDialog`)가 메인 스레드에 있으므로 Qt가 큐 연결로 안전하게 전달한다."""

    succeeded = pyqtSignal(str, str)   # (mermaid 텍스트, 실제 사용된 모델)
    failed = pyqtSignal(str)           # 에러 메시지

    def __init__(self, api_key, desc, model, base_url, image, parent=None, base_code=""):
        super().__init__(parent)
        self._api_key = api_key
        self._desc = desc
        self._model = model
        self._base_url = base_url
        self._image = image
        self._base_code = base_code   # [§8 항목36] AI 패널 「이어 고치기」 — 지금 결과 코드

    def run(self):
        try:
            from easycad.ai.text_to_mermaid import generate_mermaid
            # 이어 고치기일 때만 base_code를 넘긴다 — 옛 창과 그 테스트가 쓰는 호출 모양은 그대로.
            extra = {"base_code": self._base_code} if self._base_code else {}
            text, used = generate_mermaid(self._api_key, self._desc, model=self._model,
                                          base_url=self._base_url, image=self._image, **extra)
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


class _CreditWorker(QThread):
    """남은 크레딧 1회 조회(§8 항목41, 2026-10-16) — AI 패널 아래 「남은 크레딧」 줄. 패널을 켤 때·생성이 끝날 때 부른다.
    네트워크 호출이라 메인 스레드 밖에서(`_ModelListWorker`와 같은 이유)."""

    succeeded = pyqtSignal(float, float)   # 남은 양, 이번 달 배정
    failed = pyqtSignal(str)

    def __init__(self, api_key, base_url, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url

    def run(self):
        try:
            remaining, quota = gw.get_credit_balance(self._api_key, self._base_url)
        except Exception as e:  # noqa: BLE001 — 조회 실패는 줄에 짧게만
            self.failed.emit(str(e))
            return
        self.succeeded.emit(float(remaining), float(quota))


_ORPHANED_WORKERS: set[QThread] = set()   # 아래 _detach_worker가 채움 — GC 방지용 임시 보관


def _detach_worker(worker: QThread | None) -> None:
    """다이얼로그가 닫힐 때 아직 도는 워커(`_ModelListWorker`/`_MermaidGenWorker`/
    `_SvgGenWorker`)를 죽은 다이얼로그와 분리해 크래시 없이 백그라운드에서 마저 끝나게
    한다(2026-08-23, 실사용 버그 — X·Cancel을 열자마자 누르면 안 닫히거나(모델목록
    조회를 "생성 중"과 같은 걸로 취급해 닫기 자체를 막던 방어코드) Cancel로 강제로
    닫으면 `reject()`가 그 방어코드(`closeEvent`)를 거치지 않고 곧장 다이얼로그를 없애
    parent로 물려있던 워커까지 함께 파괴돼(살아있는 QThread 파괴) 프로그램이 죽던 문제).
    닫기는 무엇이 돌든 항상 즉시 허용하고, 결과 시그널 연결을 끊어(결과는 버림) 워커가
    끝나도 죽은 다이얼로그를 건드리지 않게 하는 쪽으로 설계를 바꿨다.

    [실사용 크래시 2026-08-26] 아래 `_reap`이 `deleteLater()`로 C++ 객체를 지우고 나면
    호출부가 들고 있던 파이썬 래퍼는 "죽은 래퍼"가 된다 — 그 상태로 다시 들어오면
    `worker.isRunning()`이 곧장 `RuntimeError`를 던지고, 이 함수는 `QDialog.done()`
    (Qt 가상함수 재구현) 안에서 불리므로 그 예외가 PyQt6의 `qFatal()`→`abort()`로
    이어져 **앱 전체가 죽었다**(minidump의 0xC0000409 + fastfail 7 = FATAL_APP_EXIT과
    일치). 근본 원인(호출부의 낡은 참조)은 각 `done()`에서 참조를 비우는 것으로
    고치되, 공용 헬퍼인 이 함수도 죽은 래퍼를 만나면 조용히 넘어가게 한다."""
    if worker is None:
        return
    try:
        if not worker.isRunning():
            return
    except RuntimeError:
        return   # 이미 파괴된 C++ 객체 — 더 볼 것 없음
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


# [2026-08-21 실사용 피드백] Mermaid 코드 첫 줄의 방향 토큰 — `mermaid_import._HEADER_RE`와
# 같은 패턴이지만 그쪽은 파싱(가져오기) 전용 private이라 여기서 UI 동기화용으로 별도 소유.
_MERMAID_HEADER_RE = re.compile(r"^\s*(?:flowchart|graph)\s+(TD|TB|LR|RL|BT)\b", re.IGNORECASE)


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

    def __init__(self, parent=None, reason: str = ""):
        super().__init__(parent)
        # [§8 항목41, 2026-10-16] 처음 쓰는 직원(심사위원 포함)이 자기 KAIROS 키를 넣는 창 — 쉬운 말로, 키 칸을 맨 위에.
        # 게이트웨이 주소는 바꿀 일이 거의 없어 「주소 바꾸기」 아래로 접는다. `reason`은 "만들려는데 키가 없어서" 연 경우의 한 줄.
        self.setWindowTitle("KAIROS 연결")
        self.setMinimumWidth(420)   # 기본 주소 전문(50자)이 스크롤 없이 한눈에 보이게
        lay = QVBoxLayout(self)

        if reason:
            why = QLabel(reason, self)
            why.setWordWrap(True)
            why.setStyleSheet(f"color:{_ACCENT_CORAL}; font-weight:600;")
            lay.addWidget(why)
        intro = QLabel("KAIROS에서 받은 내 API 키를 붙여 넣어 주세요. 키는 이 PC에만 저장되고, "
                       "AI를 쓸 때마다 내 몫의 크레딧에서 빠져요.", self)
        intro.setWordWrap(True)
        lay.addWidget(intro)

        lay.addWidget(QLabel("내 KAIROS API 키:"))
        self._key_edit = QLineEdit(self)
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("여기에 붙여 넣기(Ctrl+V)")
        self._key_edit.setText(gw.resolve_api_key())
        lay.addWidget(self._key_edit)

        # [2026-08-12 4차, 디자인 시안 합의] 옛 "모델 새로고침"+"크레딧 확인" 두 버튼을
        # "연결 테스트" 하나로 통합 — 클릭 한 번으로 모델 목록·크레딧 잔여를 함께 확인해
        # 두 번 누를 필요가 없다. 결과는 두 줄로 표시.
        test_row = QHBoxLayout()
        self._test_btn = QToolButton(self)
        self._test_btn.setIcon(_act_icon("refresh"))
        self._test_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._test_btn.setText("연결 확인")
        self._test_btn.setToolTip("키가 맞는지, 남은 크레딧이 얼마인지 확인")
        self._test_btn.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self._test_btn)
        test_row.addStretch(1)
        self._url_toggle = QToolButton(self)
        self._url_toggle.setText("주소 바꾸기 ▸")
        self._url_toggle.setAutoRaise(True)
        self._url_toggle.setCheckable(True)
        self._url_toggle.setToolTip("게이트웨이 주소 — 보통은 바꿀 필요가 없어요")
        test_row.addWidget(self._url_toggle)
        lay.addLayout(test_row)

        self._test_result_label = QLabel("", self)
        self._test_result_label.setWordWrap(True)
        self._test_result_label.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self._test_result_label)

        self._url_box = QWidget(self)
        ul = QVBoxLayout(self._url_box)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.addWidget(QLabel("게이트웨이 주소:", self._url_box))
        self._url_edit = QLineEdit(self._url_box)
        self._url_edit.setText(gw.resolve_base_url())   # 저장값 없으면 gw.BASE_URL 기본값이 그대로 채워짐
        ul.addWidget(self._url_edit)
        self._url_box.setVisible(False)
        self._url_toggle.toggled.connect(self._on_url_toggled)
        lay.addWidget(self._url_box)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_url_toggled(self, on: bool):
        self._url_toggle.setText("주소 바꾸기 ▾" if on else "주소 바꾸기 ▸")
        self._url_box.setVisible(on)
        self.adjustSize()

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
                f"<span style='color:{_STATUS_FAIL_COLOR};'>먼저 키를 붙여 넣어 주세요.</span>")
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
                    f"<span style='color:{_STATUS_OK_COLOR};'>남은 크레딧 "
                    f"{remaining:,.0f} / {quota:,.0f}</span>")
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
        # [실사용 피드백 2026-10-11] 「(미분류)」 없음 — 늘 폴더를 고른다. 처음엔 마지막에 쓴 폴더, 폴더가 하나도
        # 없으면 「새 폴더…」에 기본 이름을 채워 둔다.
        for f in symbol_library.load_folders():
            self._folder_combo.addItem(f, f)
        self._folder_combo.addItem("새 폴더…", "__new__")
        pref = symbol_library.preferred_folder()
        if pref is not None:
            self._folder_combo.setCurrentIndex(self._folder_combo.findData(pref))
        self._folder_combo.setStyleSheet(_ROUNDED_COMBO_QSS)
        self._folder_combo.currentIndexChanged.connect(self._on_combo_changed)
        lay.addWidget(self._folder_combo)

        self._new_folder_edit = QLineEdit(self)
        self._new_folder_edit.setPlaceholderText("새 폴더 이름")
        if pref is None:
            self._new_folder_edit.setText(symbol_library.DEFAULT_FOLDER)
        self._new_folder_edit.setVisible(self._folder_combo.currentData() == "__new__")
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

    def __init__(self, api_key, subject, model, base_url, image, parent=None, refs=None):
        super().__init__(parent)
        self._api_key = api_key
        self._subject = subject
        self._model = model
        self._base_url = base_url
        self._image = image   # PIL.Image.Image | None — Stage 3(2026-08-19)
        self._refs = refs     # [§8 항목36] AI 패널 「이어 만들기」 — 고른 후보 SVG들

    def run(self):
        try:
            extra = {"refs": self._refs} if self._refs else {}   # 이어 만들기일 때만(옛 호출 모양 유지)
            svg_text, used = generate_svg(self._api_key, self._subject, model=self._model,
                                          base_url=self._base_url, image=self._image, **extra)
        except Exception as e:  # noqa: BLE001 — 개별 실패, 다른 워커는 계속 진행
            self.model_failed.emit(self._model, str(e))
            return
        self.candidate.emit(used, svg_text)
