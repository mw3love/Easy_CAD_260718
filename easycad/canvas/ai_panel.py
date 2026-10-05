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

from PyQt6.QtCore import QEvent, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QScrollArea,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from easycad.ai import gateway as gw
from easycad.canvas.host_dialogs import (
    _AIGatewaySettingsDialog, _CORAL_BTN_QSS, _ImageAttachMixin, _ROUNDED_COMBO_QSS, _attach_button_qss,
    _combo_selected_model, _fill_model_combo_grouped,
)
from easycad.canvas.host_widgets import _ACCENT_CORAL, _act_icon, _current_icon_color
from easycad.canvas.photo_dialog import PHOTO_MODELS

# (키, 탭 이름, 안내 카드 제목, 안내 카드 설명, 안내 카드 예시) — 이름은 결과 기준(기술 이름 Mermaid·SVG를 쓰지 않음).
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
INPUT_HINT = {"symbol": "후보 6", "flow": "", "trace": "약 2~3분"}
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


class _KindCard(QFrame):
    """빈 상태(기록 없음)의 종류 안내 카드 — 누르면 그 종류로 바뀐다."""

    clicked = pyqtSignal(str)

    def __init__(self, key, title, desc, example, parent=None):
        super().__init__(parent)
        self._key = key
        self.setObjectName("aiKindCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 7, 9, 7)
        lay.setSpacing(2)
        t = QLabel(title, self)
        t.setStyleSheet("font-weight:600;")
        d = QLabel(desc, self)
        d.setWordWrap(True)
        d.setStyleSheet(f"color:{_MUTED}; font-size:11px;")
        e = QLabel(example, self)
        e.setStyleSheet(f"color:{_ACCENT_CORAL}; font-size:11px;")
        for wdg in (t, d, e):
            lay.addWidget(wdg)
        self.set_active(False)

    def set_active(self, active: bool):
        self._active = active
        border = _ACCENT_CORAL if active else _CARD_BORDER
        self.setStyleSheet("")   # 같은 문자열이면 다시 칠하지 않을 수 있어 비웠다가 건다(테마 전환 재도색)
        self.setStyleSheet(f"QFrame#aiKindCard {{ border:1px solid {border}; border-radius:7px; }}")

    def restyle(self):
        """테마 전환 — QSS 걸린 카드 안 글자는 팔레트만 바뀌어선 처음 색에 남는다(라이트에서 흰 글자)."""
        self.set_active(self._active)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self._key)
        super().mouseReleaseEvent(e)


class _HistoryEntry(QFrame):
    """기록 한 칸 — "종류 · 시각", 요청 글(또는 그림 이름), 상태 한 줄."""

    def __init__(self, kind: str, text: str, image_name: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("aiHistEntry")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
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
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
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

    def restyle(self):
        """테마 전환 — `_KindCard.restyle`과 같은 이유로 칸 QSS를 비웠다가 다시 건다."""
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

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self.setObjectName("aiPanel")
        self.setFixedWidth(self.WIDTH)
        self.setAcceptDrops(True)   # 패널 위 그림 끌어놓기 = 첨부(캔버스 끌어놓기는 창이 받는 그대로)
        self._init_image_attach_state()
        self._kind = "symbol"
        self._models: dict[str, str] = dict(DEFAULT_MODEL)   # 종류별로 마지막에 고른 모델
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

        # ---- 빈 상태: 종류 안내 카드 3장
        self._empty = QWidget(body)
        el = QVBoxLayout(self._empty)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(7)
        el.addStretch(1)
        self._kind_cards: dict[str, _KindCard] = {}
        for key, _short, title, desc, example in KINDS:
            card = _KindCard(key, title, desc, example, self._empty)
            card.clicked.connect(self.set_kind)
            el.addWidget(card)
            self._kind_cards[key] = card
        el.addStretch(1)
        bl.addWidget(self._empty, 1)

        # ---- 기록(요청이 하나라도 생기면 빈 상태 대신)
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
        self._hist_scroll.setVisible(False)
        bl.addWidget(self._hist_scroll, 1)

        # ---- 고급(접힘): 모델 + 게이트웨이 설정. 코드 칸은 흐름도 단계(3단계)에서 여기에 붙는다.
        self._adv_btn = QToolButton(body)
        self._adv_btn.setAutoRaise(True)
        self._adv_btn.setCheckable(True)
        self._adv_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._adv_btn.toggled.connect(self._on_adv_toggled)
        bl.addWidget(self._adv_btn)
        self._adv_box = QWidget(body)
        al = QHBoxLayout(self._adv_box)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
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
        self._adv_box.setVisible(False)
        bl.addWidget(self._adv_box)

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
        for card in getattr(self, "_kind_cards", {}).values():
            card.restyle()
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
        for key, card in self._kind_cards.items():
            card.set_active(key == kind)
        self._prompt_edit.setPlaceholderText(PLACEHOLDER[kind])
        self._hint_lbl.setText(INPUT_HINT[kind])
        self._hint_lbl.setVisible(bool(INPUT_HINT[kind]))
        self._fill_models()
        self._update_adv_label()
        self._hide_notice()

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
            # 1단계는 추천 모델만(목록 조회는 생성을 붙이는 단계에서 — 옛 창의 `_ModelListWorker` 재사용 예정).
            _fill_model_combo_grouped(combo, [], DEFAULT_MODEL[self._kind], self._models[self._kind])
        combo.blockSignals(False)

    def _on_model_changed(self, _i):
        self._models[self._kind] = self.model()

    def model(self) -> str:
        if self._kind == "trace":
            return self._model_combo.currentData() or DEFAULT_MODEL["trace"]
        return _combo_selected_model(self._model_combo, DEFAULT_MODEL[self._kind])

    def _update_adv_label(self):
        arrow = "▾" if self._adv_btn.isChecked() else "▸"
        self._adv_btn.setText(f"{arrow} 고급 — 모델")

    def _on_adv_toggled(self, on: bool):
        self._adv_box.setVisible(on)
        self._update_adv_label()

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
                        model=self.model())
        req.entry = self._add_entry(req)
        self._prompt_edit.clear()
        if image is not None:
            self._clear_image()
        self.make_requested.emit(req)
        return req

    def resubmit(self, req: AIRequest) -> AIRequest:
        """결과 막대 「다시」 — 같은 입력(종류·글·그림·모델)으로 새 기록 칸을 만들어 다시 보낸다."""
        again = AIRequest(kind=req.kind, text=req.text, image=req.image, image_name=req.image_name,
                          model=req.model)
        again.entry = self._add_entry(again)
        self.make_requested.emit(again)
        return again

    def _add_entry(self, req: AIRequest) -> _HistoryEntry:
        inner = self._hist_scroll.widget()
        entry = _HistoryEntry(req.kind, req.text, req.image_name, inner)
        self._hist_layout.insertWidget(self._hist_layout.count() - 1, entry)   # 마지막 stretch 앞(오래된 것이 위)
        self._entries.append(entry)
        self._empty.setVisible(False)
        self._hist_scroll.setVisible(True)
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

    def entries(self) -> list:
        return list(self._entries)
