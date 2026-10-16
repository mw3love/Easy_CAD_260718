"""빈 도면 가운데 입구 「무엇을 그릴까요?」(§8 항목39, 2026-10-16) — 처음 쓰는 직원이 말·사진으로 시작하는 자리.

끝난 모습 "두 층 한 앱"(CLAUDE.md `## 목표`)의 입구: 화면은 하나, 빈 도면 가운데에만 뜨고 첫 획을 그으면 사라진다
(숙련자는 지금 화면 그대로). 만드는 방식(엔진) 셋은 그대로 두고, 이 칸은 종류를 짐작해 오른쪽 AI 패널로 넘길
뿐이다(`host_aimake._on_start_prompt_submitted`) — 생성·임시 결과·기록은 패널과 완전히 같은 경로.

종류는 앱이 짐작하고(`guess_kind`, 단순 규칙) 칸 아래 버튼으로 한 번에 바꾼다 — 2026-10-05 "AI가 종류를 알아서
고르기"를 버린 이유(같은 사진도 베끼기·다시 배치 둘 다 말이 됨)를 "짐작 + 한 번에 바꾸기"로 푼 것.

⚠ 패널 자체엔 스타일시트를 걸지 않는다(`ai_panel.py`와 같은 함정 — 조상 QSS가 자손 sizeHint를 바꿈). 배경·테두리는
paintEvent, QSS는 잎 위젯에만.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from easycad.canvas.ai_panel import KIND_LABEL
from easycad.canvas.host_dialogs import _CORAL_BTN_QSS, _ImageAttachMixin, _attach_button_qss
from easycad.canvas.host_widgets import _ACCENT_CORAL, _current_icon_color

# 짐작 규칙(§8 항목39 — AI 없이 단순 규칙으로 충분, 사용자 승인 2026-10-16). 틀리면 사용자가 버튼으로 바꾼다.
_SYMBOL_WORDS = ("아이콘", "심볼", "기호", "부품", "로고", "픽토그램", "그림 하나")
_FLOW_WORDS = ("흐름", "순서도", "절차", "단계", "관계", "구조", "과정", "결재", "다시 배치")
_TRACE_WORDS = ("베끼", "그대로", "따라 그", "옮겨")

# (보이는 글, 넣을 글, 종류 고정 | None) — 지금 엔진이 실제로 잘 만드는 것만(직군별 문구는 항목44 동료 시험 뒤 정함).
EXAMPLES = (
    ("휴가 신청 결재 흐름도", "휴가 신청부터 결재까지 흐름도를 그려줘", None),
    ("방송 신호 흐름", "카메라에서 송출까지 방송 신호 흐름을 그려줘", None),
    ("카메라 아이콘", "방송용 카메라 아이콘", None),
    ("손그림 사진 베끼기", "", "trace"),
)


def guess_kind(text: str, has_image: bool) -> str:
    """말·첨부로 종류를 짐작한다 — "trace"(베끼기) | "symbol"(심볼) | "flow"(흐름도).

    사진이 있으면 기본은 베끼기(모양 그대로), 다만 "흐름·관계" 같은 말이 있으면 흐름도(관계만 읽어 다시 배치).
    사진이 없으면 "아이콘·부품" 같은 말이 있으면 심볼, 나머지는 흐름도.
    """
    t = (text or "").strip()
    if has_image:
        if any(w in t for w in _TRACE_WORDS):
            return "trace"
        return "flow" if any(w in t for w in _FLOW_WORDS) else "trace"
    if any(w in t for w in _SYMBOL_WORDS):
        return "symbol"
    return "flow"


class _StartPrompt(_ImageAttachMixin, QFrame):
    """빈 도면 가운데 카드. 호스트가 자리·보이기를 정한다(`host_aimake._sync_start_prompt`)."""

    WIDTH = 470
    submitted = pyqtSignal(str, str, object, str)   # 종류, 글, 그림(PIL | None), 그림 이름
    dismissed = pyqtSignal()                        # ✕ — 이 문서에선 다시 안 띄움

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("startPrompt")
        self.setFixedWidth(self.WIDTH)
        self.setAcceptDrops(True)
        self._init_image_attach_state()
        self._dark = True
        self._kind = "flow"
        self._kind_manual = False   # 사용자가 버튼으로 고르면 그 뒤로는 짐작이 덮어쓰지 않는다

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 14, 16)
        v.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self._title = QLabel("무엇을 그릴까요?", self)
        title_box.addWidget(self._title)
        self._sub = QLabel("말로 쓰거나 사진을 끌어다 놓으면, KAIROS가 고칠 수 있는 도형으로 만들어 드려요.", self)
        self._sub.setWordWrap(True)
        title_box.addWidget(self._sub)
        top.addLayout(title_box, 1)
        self._close_btn = QToolButton(self)
        self._close_btn.setAutoRaise(True)
        self._close_btn.setText("✕")
        self._close_btn.setToolTip("닫기 — 이 도면에서는 다시 안 떠요")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.clicked.connect(self.dismissed)
        top.addWidget(self._close_btn, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)

        # 입력 카드(글 + 첨부·종류·만들기 줄)
        self._card = QFrame(self)
        self._card.setObjectName("startPromptCard")
        cl = QVBoxLayout(self._card)
        cl.setContentsMargins(10, 8, 8, 8)
        cl.setSpacing(6)
        self._edit = QPlainTextEdit(self._card)
        self._edit.setPlaceholderText("예: 휴가 신청부터 결재까지 흐름도를 그려줘")
        self._edit.setFixedHeight(64)
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.installEventFilter(self)
        self._edit.textChanged.connect(self._regues)
        cl.addWidget(self._edit)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._attach_btn = self._build_attach_button(self._card)
        row.addWidget(self._attach_btn)
        row.addWidget(self._build_image_chip(self._card))
        row.addStretch(1)
        self._kind_btn = QToolButton(self._card)
        self._kind_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._kind_btn.setToolTip("앱이 짐작한 종류예요. 눌러서 바꿀 수 있어요")
        menu = QMenu(self._kind_btn)
        self._kind_actions: dict[str, QAction] = {}
        for key, hint in (("flow", "말을 읽어 상자·화살표로"), ("symbol", "부품 그림 후보 여러 개"),
                          ("trace", "도면 사진을 모양 그대로")):
            act = menu.addAction(f"{KIND_LABEL[key]} — {hint}")
            act.triggered.connect(lambda _c=False, k=key: self.set_kind(k, manual=True))
            self._kind_actions[key] = act
        self._kind_btn.setMenu(menu)
        row.addWidget(self._kind_btn)
        self._make_btn = QPushButton("만들기", self._card)
        self._make_btn.setStyleSheet(_CORAL_BTN_QSS)
        self._make_btn.clicked.connect(self.submit)
        row.addWidget(self._make_btn)
        cl.addLayout(row)
        v.addWidget(self._card)

        self._notice = QLabel("", self)
        self._notice.setWordWrap(True)
        self._notice.setStyleSheet(f"color:{_ACCENT_CORAL}; font-size:12px;")
        self._notice.setVisible(False)
        v.addWidget(self._notice)

        # 예시(누르면 칸에 채움 — 베끼기는 사진 고르기)
        ex = QWidget(self)
        el = QGridLayout(ex)   # 2×2 — 한 줄이면 칸 폭이 모자라 글자가 잘림(2026-10-16 실제 창 확인)
        el.setContentsMargins(0, 0, 0, 0)
        el.setHorizontalSpacing(6)
        el.setVerticalSpacing(6)
        self._example_btns: list[QPushButton] = []
        for i, (label, text, kind) in enumerate(EXAMPLES):
            b = QPushButton(label, ex)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, t=text, k=kind: self._use_example(t, k))
            el.addWidget(b, i // 2, i % 2)
            self._example_btns.append(b)
        v.addWidget(ex)

        self._foot = QLabel("그냥 그리기 시작하면 이 칸은 사라져요", self)
        v.addWidget(self._foot)

        self._set_image_drop_frame(self._card, "", "")
        self.set_kind("flow")
        self.refresh_theme(True)

    # ---- 그리기 -----------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        bg = QColor("#222b35") if self._dark else QColor("#ffffff")
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(128, 128, 128, 110), 1))
        p.drawRoundedRect(r, 12, 12)
        p.end()
        super().paintEvent(event)

    def refresh_theme(self, dark: bool):
        """테마 전환 때 호스트가 부른다(QSS에 박힌 색은 팔레트만 바꿔선 안 바뀜)."""
        self._dark = dark
        ink = _current_icon_color().name()
        # 글자색은 QSS로 직접 — 앱 팔레트는 라이트에서도 글자색이 흰색이라 QSS 없는 라벨이 흰 카드에 묻힌다(실제 창 확인)
        fg = "#e6ebf0" if dark else "#1b222b"
        muted = "#8995a3" if dark else "#6a737e"
        field_bg = "#1a222c" if dark else "#f6f7f9"
        normal = (f"QFrame#startPromptCard {{ border:1px solid rgba(128,128,128,110); border-radius:9px;"
                  f" background:{field_bg}; }}")
        active = (f"QFrame#startPromptCard {{ border:2px dashed {_ACCENT_CORAL}; border-radius:9px;"
                  f" background:{field_bg}; }}")
        self._set_image_drop_frame(self._card, normal, active)
        self._card.setStyleSheet(normal)
        self._title.setStyleSheet(f"color:{fg}; font-size:18px; font-weight:700;")
        self._edit.setStyleSheet(f"QPlainTextEdit {{ background:transparent; color:{fg}; font-size:13px; }}")
        self._sub.setStyleSheet(f"color:{muted}; font-size:12px;")
        self._foot.setStyleSheet(f"color:{muted}; font-size:11px;")
        self._close_btn.setStyleSheet(f"QToolButton {{ color:{ink}; font-size:12px; }}")
        self._attach_btn.setStyleSheet(_attach_button_qss(ink))
        hover = "rgba(255,255,255,22)" if dark else "rgba(0,0,0,14)"
        self._kind_btn.setStyleSheet(
            f"QToolButton {{ color:{fg}; border:1px solid rgba(128,128,128,120); border-radius:7px; padding:5px 9px; font-size:12px; }}"
            f"QToolButton:hover {{ background:{hover}; }}"
            "QToolButton::menu-indicator { image:none; width:0; }")
        for b in self._example_btns:
            b.setStyleSheet(
                f"QPushButton {{ color:{fg}; border:1px solid rgba(128,128,128,110); border-radius:12px; padding:4px 10px;"
                " font-size:12px; background:transparent; }"
                f"QPushButton:hover {{ background:{hover}; border-color:rgba(218,119,86,170); }}")
        self.update()

    # ---- 종류 -------------------------------------------------------------------

    def kind(self) -> str:
        return self._kind

    def set_kind(self, kind: str, manual: bool = False):
        self._kind = kind
        if manual:
            self._kind_manual = True
        self._kind_btn.setText(f"만들 것: {KIND_LABEL[kind]} ▾")
        for k, act in self._kind_actions.items():
            act.setCheckable(True)
            act.setChecked(k == kind)
        self._edit.setPlaceholderText(
            "고친 결과를 손볼 부분이 있으면 적어 주세요(비워도 돼요)" if kind == "trace" and self._attached_image is not None
            else "예: 휴가 신청부터 결재까지 흐름도를 그려줘")

    def _regues(self):
        if not self._kind_manual:
            self.set_kind(guess_kind(self._edit.toPlainText(), self._attached_image is not None))
        self._notice.setVisible(False)

    def _set_attached_image(self, pil_img, name: str):
        super()._set_attached_image(pil_img, name)
        self._regues()

    def _clear_image(self):
        super()._clear_image()
        self._regues()

    def _use_example(self, text: str, kind):
        if kind == "trace":
            self.set_kind("trace", manual=True)
            self._browse_image()
            return
        self._kind_manual = False
        self._edit.setPlainText(text)
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)

    # ---- 만들기 -----------------------------------------------------------------

    def submit(self):
        """「만들기」·Enter — 입력을 검사해 `submitted`로 넘기고 칸을 비운다. 돌려준 값(종류)은 테스트용."""
        text = self._edit.toPlainText().strip()
        image = self._attached_image
        kind = self._kind
        if kind == "trace" and image is None:
            self._show_notice("베끼기는 도면 사진이 필요해요. 사진을 끌어다 놓거나 Ctrl+V로 붙여 주세요.")
            return None
        if not text and image is None:
            self._show_notice("먼저 무엇을 그릴지 쓰거나 사진을 붙여 주세요.")
            return None
        name = self._attached_image_name if image is not None else ""
        self._edit.clear()
        if image is not None:
            self._attached_image = None   # 칩만 비운다(그림 객체는 패널로 넘어감)
            super()._clear_image()
        self._kind_manual = False
        self.set_kind("flow")
        self.submitted.emit(kind, text, image, name)
        return kind

    def _show_notice(self, text: str):
        self._notice.setText(text)
        self._notice.setVisible(True)

    def eventFilter(self, obj, event):
        if obj is self._edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False   # Shift+Enter = 줄바꿈
                self.submit()
                return True
            if self._maybe_intercept_paste_image(event):
                return True
        return super().eventFilter(obj, event)
