"""AI 만들기 패널(§8 항목36, 2026-10-05) — Mermaid 가져오기·AI SVG 에셋 생성·사진→도면 세 창을 합칠
오른쪽 기둥 패널. 설계: `docs/EasyCAD_계획.md` §8 항목36(시안 3차 확정).

역할 나눔(사용자 확정): 패널 = 입력 + 기록(세 종류가 같은 모양), 결과에 딸린 조절은 캔버스 위 결과 막대(2단계~).
1단계(이 파일의 지금 범위)는 뼈대만 — 「만들기」는 기록에 요청을 남기고 `make_requested`를 내보낼 뿐, 실제 생성은
3~5단계에서 종류별로 붙인다(그때까지 옛 창 세 개는 삽입 메뉴에 그대로).

⚠ 패널 자체에는 스타일시트를 걸지 않는다 — 조상에 QSS가 걸리면 자손 위젯 sizeHint가 바뀌는 함정
(`host_widgets._FloatingPanel.paintEvent` 주석). 배경·테두리는 paintEvent가 그리고, QSS는 잎 위젯에만.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from PyQt6.QtCore import QEvent, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QFont, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QScrollArea,
    QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from easycad.ai import gateway as gw
from easycad.app_settings import app_settings
from easycad.canvas.host_dialogs import (
    _AIGatewaySettingsDialog, _CORAL_BTN_QSS, _ImageAttachMixin, _ModelListWorker, _ROUNDED_COMBO_QSS,
    _attach_button_qss, _combo_selected_model, _detach_worker, _fill_model_combo_grouped,
)
from easycad.canvas.host_widgets import _ACCENT_CORAL, _act_icon, _current_icon_color
from easycad.canvas.photo_dialog import PHOTO_MODELS

# (키, 탭 이름, 제목, 설명, 예시) — 이름은 결과 기준(기술 이름 Mermaid·SVG를 쓰지 않음). 설명·예시는 탭 바로 아래 한 줄로.
KINDS = (
    ("symbol", "심볼", "심볼 하나",
     "부품 아이콘을 후보 여러 개로 만들어요. 도면 옆에 줄지어 놓이고 클릭해서 골라요.", "예: BNC 커넥터 아이콘"),
    ("flow", "흐름도", "흐름도",
     "설명이나 손그림에서 관계만 읽어 상자·화살표를 줄 맞춰 놓아요.", "예: 송신기 → 결합기 → 안테나"),
    ("trace", "베끼기", "그대로 베끼기",
     "도면 사진 속 위치 그대로 선·글자로 옮겨요. 사진이 필요하고 2~3분 걸려요.", "사진을 끌어다 놓기 · Ctrl+V"),
)
KIND_LABEL = {k[0]: k[1] for k in KINDS}
PLACEHOLDER = {
    "symbol": "만들 부품을 적어 주세요",
    "flow": "설명을 쓰거나 손그림을 끌어 놓기",
    "trace": "도면 사진을 끌어다 놓기 · Ctrl+V",
}
INPUT_HINT = {"symbol": "후보 {n}", "flow": "", "trace": "약 2~3분"}
SYMBOL_COUNT_DEFAULT = 6
SYMBOL_COUNT_MAX = 10      # 옛 SVG 창 최대(모델 A 5 + B 5)와 같은 상한
_SYMBOL_COUNT_KEY = "ai_panel/symbol_count"
# 종류별 추천 모델(평소엔 이것을 자동으로 — 「고급」을 펼쳐야 바꿀 수 있다).
DEFAULT_MODEL = {
    "symbol": gw.TEXT_RECOMMEND_1,
    "flow": gw.TEXT_RECOMMEND_MERMAID,
    "trace": PHOTO_MODELS[0][0],
}
PENDING_TEXT = "준비 중 — 지금은 삽입 메뉴의 옛 창을 쓰세요"   # 1단계 임시 문구(3~5단계에서 종류별로 사라짐)

_MUTED = "#8a8a8a"
_CARD_BORDER = "rgba(128,128,128,90)"


@dataclass
class AIRequest:
    """「만들기」 한 번 — 호출부(호스트)가 받아 생성을 맡고, 진행·결과는 `entry.set_status`로 알린다."""
    kind: str
    text: str
    image: object = None          # PIL.Image | None
    image_name: str = ""
    model: str = ""
    entry: object = field(default=None, repr=False)   # _HistoryEntry
    doc: object = field(default=None, repr=False)     # 만들기를 누른 탭(CanvasDocument) — 호스트가 채움
    center: object = None                             # 결과를 놓을 씬 좌표(만들기를 누른 순간의 화면 가운데)
    replace_target: object = field(default=None, repr=False)   # 우클릭 「AI로 바꾸기」의 대상 도형(심볼)
    count: int = SYMBOL_COUNT_DEFAULT                 # 심볼 후보 수(고급에서 고름)


class _HistoryEntry(QFrame):
    """기록 한 칸 — "종류 · 시각", 요청 글(또는 그림 이름), 상태 한 줄. 누르면 그 요청을 입력칸에 다시 채운다
    (사용자 결정 2026-10-05 — 고쳐서 다시 만들기용)."""

    clicked = pyqtSignal(object)   # self

    def __init__(self, kind: str, text: str, image_name: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.request = None   # AIRequest — 패널이 붙인다
        self.setObjectName("aiHistEntry")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("누르면 이 요청을 입력칸에 다시 채워요")
        self._running = False
        self.restyle()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        who = QLabel(f"{KIND_LABEL.get(kind, kind)} · {time.strftime('%H:%M')}", self)
        who.setStyleSheet(f"color:{_MUTED}; font-size:10px;")
        lay.addWidget(who)
        body = text
        if image_name:
            body = f"[그림] {image_name}" + (f"\n{text}" if text else "")
        self._text_lbl = QLabel(body, self)
        self._text_lbl.setWordWrap(True)   # 글 고르기(드래그 선택)는 끔 — 칸 누르기와 겹친다
        lay.addWidget(self._text_lbl)
        self._status_lbl = QLabel("", self)
        self._status_lbl.setWordWrap(True)
        lay.addWidget(self._status_lbl)
        self.set_status("")

    def set_status(self, text: str, running: bool = False):
        self._running = running
        self._status_lbl.setText(text)
        self._status_lbl.setVisible(bool(text))
        color = _ACCENT_CORAL if running else _MUTED
        self._status_lbl.setStyleSheet(f"color:{color}; font-size:11px;")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self)
        super().mouseReleaseEvent(e)

    def restyle(self):
        """테마 전환 — QSS 걸린 칸 안 글자는 팔레트만 바뀌어선 처음 색에 남는다(라이트에서 흰 글자) — 비웠다가 다시 건다."""
        self.setStyleSheet("")
        self.setStyleSheet(f"QFrame#aiHistEntry {{ border:1px solid {_CARD_BORDER}; border-radius:7px; }}")

    def status_text(self) -> str:
        return self._status_lbl.text()


class _AIPanel(_ImageAttachMixin, QFrame):
    """오른쪽 기둥 패널 본체. 호스트(`CanvasWindow`)가 중앙 위젯의 탭 옆에 붙이고, 켜고 끈다
    (`host_ui._set_ai_panel_visible`). 켜져 있는 동안 기록은 모든 탭 공통(사용자 확정), 앱을 끄면 사라진다."""

    WIDTH = 300
    make_requested = pyqtSignal(object)   # AIRequest
    close_requested = pyqtSignal()
    code_insert_requested = pyqtSignal(object)   # AIRequest — 고급 「코드로 넣기」(AI 없이 Mermaid 코드 그대로)
    code_edited = pyqtSignal(str)                # 고급 코드 칸을 손으로 고침(0.5초 묶음) — 임시 흐름도를 바꿔 그림
    trace_photo_changed = pyqtSignal(object)     # 베끼기 사진(PIL | None) — 호스트가 캔버스에 깔고 모서리 점을 띄움

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self.setObjectName("aiPanel")
        self.setFixedWidth(self.WIDTH)
        self.setAcceptDrops(True)   # 패널 위 그림 끌어놓기 = 첨부(캔버스 끌어놓기는 창이 받는 그대로)
        self._init_image_attach_state()
        self._kind = "symbol"
        self._models: dict[str, str] = dict(DEFAULT_MODEL)   # 종류별로 마지막에 고른 모델
        self._listed_models: list = []        # 게이트웨이 전체 글 모델 목록(고급을 처음 펼칠 때 받아 옴)
        self._model_list_worker = None
        self._entries: list[_HistoryEntry] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(1, 0, 0, 0)   # 왼쪽 1px = paintEvent가 그리는 경계선 자리
        v.setSpacing(0)

        # ---- 제목줄(다른 패널과 같은 #floatPanelHead — 스타일은 호스트 `_apply_theme`이 건다)
        head = QWidget(self)
        head.setObjectName("floatPanelHead")
        self._head = head
        hl = QHBoxLayout(head)
        hl.setContentsMargins(9, 4, 4, 4)
        hl.setSpacing(4)
        self._title_lbl = QLabel("AI로 만들기", head)
        hl.addWidget(self._title_lbl, 1)
        self._close_btn = QToolButton(head)
        self._close_btn.setAutoRaise(True)
        self._close_btn.setText("✕")
        self._close_btn.setToolTip("패널 닫기")
        self._close_btn.setFixedSize(21, 21)
        self._close_btn.clicked.connect(self.close_requested)
        hl.addWidget(self._close_btn)
        v.addWidget(head)

        body = QWidget(self)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(9, 9, 9, 9)
        bl.setSpacing(8)

        # ---- 종류 탭(한 줄 세그먼트)
        seg = QWidget(body)
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self._kind_group = QButtonGroup(self)
        self._kind_group.setExclusive(True)
        self._kind_buttons: dict[str, QToolButton] = {}
        for i, (key, short, *_rest) in enumerate(KINDS):
            b = QToolButton(seg)
            b.setText(short)
            b.setCheckable(True)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setProperty("kind", key)
            b.setProperty("segPos", "first" if i == 0 else ("last" if i == len(KINDS) - 1 else "mid"))
            self._kind_group.addButton(b)
            sl.addWidget(b)
            self._kind_buttons[key] = b
        self._kind_group.buttonClicked.connect(self._on_kind_button)
        bl.addWidget(seg)

        # ---- 고른 종류 설명(누를 수 없는 글) — 2026-10-05 피드백: 탭과 안내 카드가 둘 다 버튼이라 시선이 갈라짐 →
        # 버튼은 위 탭 하나, 설명은 그 바로 아래 한두 줄.
        self._desc_lbl = QLabel("", body)
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._desc_lbl.setStyleSheet(f"color:{_MUTED}; font-size:11px; padding:0 2px;")
        bl.addWidget(self._desc_lbl)

        # ---- 기록
        self._hist_scroll = QScrollArea(body)
        self._hist_scroll.setWidgetResizable(True)
        self._hist_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._hist_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self._hist_layout = QVBoxLayout(inner)
        self._hist_layout.setContentsMargins(0, 0, 0, 0)
        self._hist_layout.setSpacing(6)
        self._hist_layout.addStretch(1)
        self._hist_scroll.setWidget(inner)
        bl.addWidget(self._hist_scroll, 1)

        # ---- 고급(접힘): 모델 + 게이트웨이 설정. 코드 칸은 흐름도 단계(3단계)에서 여기에 붙는다.
        self._adv_btn = QToolButton(body)
        self._adv_btn.setAutoRaise(True)
        self._adv_btn.setCheckable(True)
        self._adv_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._adv_btn.toggled.connect(self._on_adv_toggled)
        bl.addWidget(self._adv_btn)
        self._adv_box = QWidget(body)
        avl = QVBoxLayout(self._adv_box)
        avl.setContentsMargins(0, 0, 0, 0)
        avl.setSpacing(6)
        al = QHBoxLayout()
        al.setSpacing(6)
        avl.addLayout(al)
        al.addWidget(QLabel("모델", self._adv_box))
        self._model_combo = QComboBox(self._adv_box)
        self._model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        al.addWidget(self._model_combo, 1)
        self._settings_btn = QToolButton(self._adv_box)
        self._settings_btn.setAutoRaise(True)
        self._settings_btn.setToolTip("AI 게이트웨이 설정(주소·키·연결 테스트)")
        self._settings_btn.clicked.connect(self._open_gateway_settings)
        al.addWidget(self._settings_btn)
        # 심볼 후보 수(사용자 결정: 고급 안) — 마지막 값 기억.
        self._count_row = QWidget(self._adv_box)
        crl = QHBoxLayout(self._count_row)
        crl.setContentsMargins(0, 0, 0, 0)
        crl.addWidget(QLabel("후보 수", self._count_row))
        self._count_spin = QSpinBox(self._count_row)
        self._count_spin.setRange(1, SYMBOL_COUNT_MAX)
        self._count_spin.setValue(max(1, min(SYMBOL_COUNT_MAX, app_settings().value(
            _SYMBOL_COUNT_KEY, SYMBOL_COUNT_DEFAULT, type=int))))
        self._count_spin.valueChanged.connect(self._on_count_changed)
        crl.addWidget(self._count_spin)
        crl.addStretch(1)
        avl.addWidget(self._count_row)
        self._adv_box.setVisible(False)
        bl.addWidget(self._adv_box)

        # ---- 고급 안 Mermaid 코드 칸(흐름도만) — AI 결과가 채워지고, 고치면 임시 결과가 바뀌고, AI 없이 넣는 길도 여기.
        self._code_box = QWidget(body)
        cbl = QVBoxLayout(self._code_box)
        cbl.setContentsMargins(0, 0, 0, 0)
        cbl.setSpacing(4)
        code_lbl = QLabel("Mermaid 코드 — 고치면 캔버스 결과도 바뀜", self._code_box)
        code_lbl.setStyleSheet(f"color:{_MUTED}; font-size:11px;")
        cbl.addWidget(code_lbl)
        self._code_edit = QPlainTextEdit(self._code_box)
        self._code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._code_edit.setFont(mono)
        self._code_edit.setFixedHeight(120)
        self._code_edit.setPlaceholderText(
            "flowchart LR\n    A[시작] --> B{조건?}\n    B -->|예| C[처리]")
        self._code_edit.textChanged.connect(self._on_code_text_changed)
        cbl.addWidget(self._code_edit)
        crow = QHBoxLayout()
        crow.addStretch(1)
        self._code_insert_btn = QToolButton(self._code_box)
        self._code_insert_btn.setText("코드로 넣기")
        self._code_insert_btn.setToolTip("AI 없이 위 코드를 그대로 캔버스에 놓기")
        self._code_insert_btn.clicked.connect(self._on_code_insert)
        crow.addWidget(self._code_insert_btn)
        cbl.addLayout(crow)
        self._code_box.setVisible(False)
        bl.addWidget(self._code_box)
        self._code_timer = QTimer(self)
        self._code_timer.setSingleShot(True)
        self._code_timer.setInterval(500)
        self._code_timer.timeout.connect(self._emit_code_edited)
        self._code_programmatic = False

        # ---- 알림 한 줄(빈 입력으로 만들기 등) — 모달 창 대신. 다시 입력하면 사라진다.
        self._notice = QLabel("", body)
        self._notice.setWordWrap(True)
        self._notice.setStyleSheet(f"color:{_ACCENT_CORAL}; font-size:11px;")
        self._notice.setVisible(False)
        bl.addWidget(self._notice)

        # ---- 입력 카드: 글(위) + 첨부·힌트·만들기(아래) — 옛 Mermaid/SVG 창의 카드와 같은 언어
        self._card = QFrame(body)
        self._card.setObjectName("aiPromptCard")
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        cl = QVBoxLayout(self._card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self._prompt_edit = QPlainTextEdit(self._card)
        self._prompt_edit.setMinimumHeight(64)
        self._prompt_edit.setMaximumHeight(140)
        self._prompt_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._prompt_edit.setFrameShape(QFrame.Shape.NoFrame)
        self._prompt_edit.setAcceptDrops(False)   # 드롭은 패널(dropEvent)이 받는다
        self._prompt_edit.installEventFilter(self)   # Enter=만들기 · Ctrl+V 그림 첨부
        self._prompt_edit.textChanged.connect(self._hide_notice)
        cl.addWidget(self._prompt_edit, 1)
        bar = QWidget(self._card)
        bar.setObjectName("aiPromptBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setStyleSheet(
            "QWidget#aiPromptBar { background:palette(button); border-top:1px solid rgba(128,128,128,90);"
            " border-bottom-left-radius:8px; border-bottom-right-radius:8px; }")
        tl = QHBoxLayout(bar)
        tl.setContentsMargins(7, 5, 7, 5)
        tl.setSpacing(6)
        self._attach_btn = self._build_attach_button(bar)
        tl.addWidget(self._attach_btn)
        tl.addWidget(self._build_image_chip(bar))
        self._image_name_label.setMaximumWidth(90)   # 패널 폭이 좁아 칩 이름을 더 짧게
        self._hint_lbl = QLabel("", bar)
        self._hint_lbl.setStyleSheet(f"color:{_MUTED}; font-size:11px;")
        tl.addWidget(self._hint_lbl)
        tl.addStretch(1)
        self._make_btn = QToolButton(bar)
        self._make_btn.setText("만들기")
        self._make_btn.setToolTip("만들기 (Enter · 줄바꿈은 Shift+Enter)")
        self._make_btn.setStyleSheet(_CORAL_BTN_QSS)
        self._make_btn.clicked.connect(self.request_make)
        tl.addWidget(self._make_btn)
        cl.addWidget(bar)
        bl.addWidget(self._card)
        self._set_image_drop_frame(self._card, "", "")   # 실제 QSS는 refresh_theme이 채운다

        v.addWidget(body, 1)

        self._dark = bool(getattr(host, "_dark", True))
        self.refresh_theme(self._dark)
        self.set_kind("symbol")
        self.hide()   # 기본은 꺼짐 — 「AI로 만들기」로 켠다

    # ---- 그리기·테마 ----------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QBrush(self.palette().color(QPalette.ColorRole.Window)))
        p.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1))
        p.drawLine(QPointF(0.5, 0), QPointF(0.5, self.height()))
        p.end()
        super().paintEvent(event)

    def refresh_theme(self, dark: bool):
        """테마 전환 때 호스트가 부른다 — 색이 박힌 QSS를 그 순간 팔레트로 다시 건다
        (QSS 걸린 위젯은 팔레트만 바뀌어선 재도색이 안 되는 함정, `_MermaidDialog._refresh_theme_colors` 참조)."""
        self._dark = dark
        bg = "#e7e0d6" if dark else "palette(base)"   # 다크에선 입력칸만 밝게(옛 창과 같은 아이보리)
        normal = (f"QFrame#aiPromptCard {{ border:1px solid {_CARD_BORDER}; border-radius:8px;"
                  f" background:{bg}; }}")
        active = (f"QFrame#aiPromptCard {{ border:2px dashed {_ACCENT_CORAL}; border-radius:8px;"
                  f" background:{bg}; }}")
        self._set_image_drop_frame(self._card, normal, active)
        self._card.setStyleSheet(normal)
        self._prompt_edit.setStyleSheet(
            "QPlainTextEdit { background:transparent; " + ("color:#241a15; }" if dark else "}"))
        self._attach_btn.setStyleSheet(_attach_button_qss(_current_icon_color().name()))
        self._settings_btn.setIcon(_act_icon("settings"))
        self._model_combo.setStyleSheet(_ROUNDED_COMBO_QSS)
        self._close_btn.setStyleSheet(
            f"QToolButton {{ color:{_current_icon_color().name()}; font-size:12px; }}")
        self._adv_btn.setStyleSheet(f"QToolButton {{ color:{_MUTED}; font-size:11px; border:none; }}")
        hover = "rgba(255,255,255,22)" if dark else "rgba(0,0,0,18)"
        for b in self._kind_buttons.values():
            pos = b.property("segPos")
            radius = {"first": "border-top-left-radius:6px; border-bottom-left-radius:6px;",
                      "last": "border-top-right-radius:6px; border-bottom-right-radius:6px;"}.get(pos, "")
            left = "" if pos == "first" else "border-left:none;"
            b.setStyleSheet(
                f"QToolButton {{ border:1px solid rgba(128,128,128,110); {left} {radius} padding:4px 0; }}"
                f"QToolButton:hover {{ background:{hover}; }}"
                f"QToolButton:checked {{ background:rgba(218,119,86,70); font-weight:600; }}")
        for entry in getattr(self, "_entries", []):
            entry.restyle()
        self.update()

    # ---- 종류 ---------------------------------------------------------------

    def kind(self) -> str:
        return self._kind

    def set_kind(self, kind: str):
        if kind not in KIND_LABEL:
            return
        self._kind = kind
        self._kind_buttons[kind].setChecked(True)
        _key, _short, _title, desc, example = next(k for k in KINDS if k[0] == kind)
        self._desc_lbl.setText(f"{desc}<br><span style='color:{_ACCENT_CORAL}'>{example}</span>")
        self._prompt_edit.setPlaceholderText(PLACEHOLDER[kind])
        self._update_input_hint()
        self._count_row.setVisible(kind == "symbol")
        self._fill_models()
        self._update_adv_label()
        self._sync_code_box()
        self._hide_notice()
        self.trace_photo_changed.emit(self._attached_image if kind == "trace" else None)

    def _on_kind_button(self, btn):
        self.set_kind(btn.property("kind"))

    # ---- 고급(모델) -----------------------------------------------------------

    def _fill_models(self):
        combo = self._model_combo
        combo.blockSignals(True)
        if self._kind == "trace":
            combo.clear()
            for mid, label in PHOTO_MODELS:
                combo.addItem(label, mid)
            idx = combo.findData(self._models["trace"])
            combo.setCurrentIndex(max(0, idx))
        else:
            # 고급을 처음 펼칠 때 받아 온 전체 목록(없으면 추천만) — 옛 Mermaid·SVG 창과 같은 그룹 드롭다운.
            _fill_model_combo_grouped(combo, self._listed_models, DEFAULT_MODEL[self._kind], self._models[self._kind])
        combo.blockSignals(False)

    def _fetch_model_list(self):
        """게이트웨이 글 모델 목록을 한 번 받아 온다(백그라운드 — 옛 창 `_populate_models`와 같은 이유로 동기 호출 금지)."""
        key = gw.resolve_api_key()
        if not key or self._listed_models:
            return
        w = self._model_list_worker
        try:
            if w is not None and w.isRunning():
                return
        except RuntimeError:
            pass
        self._model_list_worker = _ModelListWorker(key, gw.resolve_base_url(), self)
        self._model_list_worker.succeeded.connect(self._on_models_listed)
        self._model_list_worker.start()

    def _on_models_listed(self, models):
        self._listed_models = list(models)
        self._fill_models()

    def detach_workers(self):
        """창이 닫힐 때 호스트가 부른다 — 도는 목록 조회는 떼어 내 결과를 버린다."""
        _detach_worker(self._model_list_worker)
        self._model_list_worker = None

    def _on_model_changed(self, _i):
        self._models[self._kind] = self.model()

    def model(self) -> str:
        if self._kind == "trace":
            return self._model_combo.currentData() or DEFAULT_MODEL["trace"]
        return _combo_selected_model(self._model_combo, DEFAULT_MODEL[self._kind])

    def _update_input_hint(self):
        hint = INPUT_HINT[self._kind].format(n=self.symbol_count())
        self._hint_lbl.setText(hint)
        self._hint_lbl.setVisible(bool(hint))

    def symbol_count(self) -> int:
        return self._count_spin.value()

    def _on_count_changed(self, n):
        app_settings().setValue(_SYMBOL_COUNT_KEY, int(n))
        self._update_input_hint()

    def _update_adv_label(self):
        arrow = "▾" if self._adv_btn.isChecked() else "▸"
        what = {"flow": "모델 · 코드", "symbol": "모델 · 후보 수"}.get(self._kind, "모델")
        self._adv_btn.setText(f"{arrow} 고급 — {what}")

    def _on_adv_toggled(self, on: bool):
        self._adv_box.setVisible(on)
        self._sync_code_box()
        self._update_adv_label()
        if on:
            self._fetch_model_list()

    # ---- 고급 코드 칸(흐름도) -------------------------------------------------------

    def _sync_code_box(self):
        self._code_box.setVisible(self._adv_btn.isChecked() and self._kind == "flow")

    def flow_code(self) -> str:
        return self._code_edit.toPlainText()

    def show_flow_code(self, code: str):
        """호스트가 결과 코드를 채운다 — 사람이 고친 게 아니므로 `code_edited`를 내보내지 않는다."""
        if self._code_edit.toPlainText() == code:
            return
        self._code_programmatic = True
        self._code_edit.setPlainText(code)
        self._code_programmatic = False
        self._code_timer.stop()

    def _on_code_text_changed(self):
        if not self._code_programmatic:
            self._code_timer.start()

    def _emit_code_edited(self):
        self.code_edited.emit(self._code_edit.toPlainText())

    def _on_code_insert(self):
        code = self._code_edit.toPlainText().strip()
        if not code:
            self._show_notice("코드 칸이 비어 있어요.")
            return
        req = AIRequest(kind="flow", text="(코드로 넣기)", model="")
        req.entry = self._add_entry(req)
        self.code_insert_requested.emit(req)

    def _open_gateway_settings(self):
        if _AIGatewaySettingsDialog(self).exec() == QDialog.DialogCode.Accepted:
            self._fill_models()

    # ---- 입력·만들기 ------------------------------------------------------------

    def focus_prompt(self):
        self._prompt_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def eventFilter(self, obj, event):
        if obj is self._prompt_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False   # Shift+Enter = 줄바꿈
                self.request_make()
                return True
            if self._maybe_intercept_paste_image(event):
                return True
        return super().eventFilter(obj, event)

    def show_notice(self, text: str):
        """호스트가 패널에 한 줄 안내를 띄울 때(예: 우클릭 「AI로 바꾸기」)."""
        self._show_notice(text)

    def _show_notice(self, text: str):
        self._notice.setText(text)
        self._notice.setVisible(True)

    def _hide_notice(self):
        self._notice.setVisible(False)

    def _set_attached_image(self, pil_img, name: str):
        super()._set_attached_image(pil_img, name)
        # 믹스인은 130px로 줄이는데 패널 칸이 좁아 더 줄인다(전체 이름은 툴팁에 그대로).
        fm = self._image_name_label.fontMetrics()
        self._image_name_label.setText(fm.elidedText(name, Qt.TextElideMode.ElideMiddle, 80))
        self._hide_notice()
        if self._kind == "trace":
            self.trace_photo_changed.emit(pil_img)

    def _clear_image(self):
        super()._clear_image()
        if self._kind == "trace":
            self.trace_photo_changed.emit(None)

    def clear_attached_image(self):
        """호스트가 베끼기를 끝냈을 때 첨부 칩을 비운다."""
        if self._attached_image is not None:
            self._clear_image()

    def request_make(self):
        """「만들기」(버튼·Enter) — 입력을 검사하고, 기록에 한 칸을 남긴 뒤 `make_requested`로 넘긴다.
        입력 칸과 그림은 비운다(채팅 입력창 관례 — 같은 요청은 기록에 남아 있다). 돌려준 값은 테스트용."""
        text = self._prompt_edit.toPlainText().strip()
        image = self._attached_image
        if self._kind == "trace" and image is None:
            self._show_notice("베끼기는 도면 사진이 필요해요. 사진을 끌어다 놓거나 Ctrl+V로 붙여 주세요.")
            return None
        if not text and image is None:
            self._show_notice("먼저 설명을 쓰거나 그림을 붙여 주세요.")
            return None
        req = AIRequest(kind=self._kind, text=text, image=image,
                        image_name=self._attached_image_name if image is not None else "",
                        model=self.model(), count=self.symbol_count())
        req.entry = self._add_entry(req)
        self._prompt_edit.clear()
        if image is not None and self._kind != "trace":
            self._clear_image()   # 베끼기는 사진이 캔버스에 깔린 채 만드는 중이라 남긴다(끝나면 호스트가 비움)
        self.make_requested.emit(req)
        return req

    def resubmit(self, req: AIRequest) -> AIRequest:
        """결과 막대 「다시」 — 같은 입력(종류·글·그림·모델)으로 새 기록 칸을 만들어 다시 보낸다."""
        again = AIRequest(kind=req.kind, text=req.text, image=req.image, image_name=req.image_name,
                          model=req.model, replace_target=req.replace_target, count=req.count)
        again.entry = self._add_entry(again)
        self.make_requested.emit(again)
        return again

    def _add_entry(self, req: AIRequest) -> _HistoryEntry:
        inner = self._hist_scroll.widget()
        entry = _HistoryEntry(req.kind, req.text, req.image_name, inner)
        entry.request = req
        entry.clicked.connect(self._on_entry_clicked)
        self._hist_layout.insertWidget(self._hist_layout.count() - 1, entry)   # 마지막 stretch 앞(오래된 것이 위)
        self._entries.append(entry)
        bar = self._hist_scroll.verticalScrollBar()
        bar.rangeChanged.connect(self._scroll_to_bottom_once)
        return entry

    def _scroll_to_bottom_once(self, _lo, hi):
        bar = self._hist_scroll.verticalScrollBar()
        bar.setValue(hi)
        try:
            bar.rangeChanged.disconnect(self._scroll_to_bottom_once)
        except TypeError:
            pass

    def _on_entry_clicked(self, entry):
        """기록 칸 누르기 — 그 요청(종류·글·그림·후보 수)을 입력칸에 다시 채운다. 「코드로 넣기」 칸은 코드 칸에."""
        req = entry.request
        if req is None:
            return
        self.set_kind(req.kind)
        if req.kind == "flow" and req.text == "(코드로 넣기)":
            if not self._adv_btn.isChecked():
                self._adv_btn.setChecked(True)
            self.show_flow_code(getattr(req, "result_text", "") or self.flow_code())
            self._prompt_edit.clear()
        else:
            self._prompt_edit.setPlainText(req.text)
        if req.image is not None:
            self._set_attached_image(req.image, req.image_name or "그림")
        elif self._attached_image is not None:
            self._clear_image()
        if req.kind == "symbol":
            self._count_spin.setValue(req.count)
        self.focus_prompt()
        self._prompt_edit.moveCursor(self._prompt_edit.textCursor().MoveOperation.End)

    def entries(self) -> list:
        return list(self._entries)
