"""가운데 칸 「무엇을 그릴까요?」(§8 항목39 → 51, 2026-10-16) — AI의 **하나뿐인 입구**.

Magic Board 개편(§8 항목51): 빈 도면이면 저절로 뜨고(첫 획을 그으면 사라짐 — 숙련자는 지금 화면 그대로), 상단바 「AI」·
삽입 메뉴·단축키로는 도면이 차 있어도 그 위에 뜬다. 옛 오른쪽 패널은 없앴다. 종류(흐름도·심볼·베끼기·풀어 그리기)는 사용자가
고르지 않는다 — `ai_control.guess_kind`가 짐작하고, 틀리면 결과 막대 한 줄로 바꾼다. 메뉴로 종류를 정해 열었을 때만 안내글이
그 종류로 바뀐다(칩·버튼 없음).

파일은 끌어다 놓기·Ctrl+V·「+」(누르면 바로 파일 선택 창). 못 읽는 파일은 "되는 것: …" 안내. 모델은 「자동 ▾」(펼치면 모델마다
가격), 아래 줄에 남은 크레딧.

⚠ 칸 자체엔 스타일시트를 걸지 않는다(조상 QSS가 자손 sizeHint를 바꾸는 함정). 배경·테두리는 paintEvent, QSS는 잎 위젯에만.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QEvent, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton, QToolButton, QVBoxLayout,
    QWidget,
)

from easycad.canvas.ai_control import (
    AUTO, IMAGE_EXTS, KIND_LABEL, PLACEHOLDER, _AIController, guess_kind, unsupported_file_text,
)
from easycad.canvas.host_dialogs import _CORAL_BTN_QSS, _ImageAttachMixin, _attach_button_qss
from easycad.canvas.host_widgets import _ACCENT_CORAL, _current_icon_color

__all__ = ["_StartPrompt", "guess_kind", "EXAMPLES"]

# (보이는 글, 넣을 글, 종류 고정 | None) — 지금 엔진이 실제로 잘 만드는 것만.
EXAMPLES = (
    ("휴가 신청 결재 흐름도", "휴가 신청부터 결재까지 흐름도를 그려줘", None),
    ("카메라 아이콘", "방송용 카메라 아이콘", None),
    ("손그림 사진 베끼기", "", "trace"),
    ("논문 PDF 풀어 그리기", "", "explain"),
)
_DEFAULT_PLACEHOLDER = "예: 휴가 신청부터 결재까지 흐름도를 그려줘"


class _StartPrompt(_ImageAttachMixin, QFrame):
    """가운데 칸. 호스트가 자리·보이기를 정한다(`host_aimake._sync_start_prompt`)."""

    WIDTH = 500
    # [2026-10-16, 추정 예방] 클래스 기본값 — 10-11 `_PaletteButton`과 같은 함정: Python GC가 순환 정리 중 인스턴스 속성을 먼저
    # 비우고 C++ 위젯은 살아 이벤트를 받으면 `eventFilter`·`paintEvent`가 없는 속성을 읽다 예외 → 출력 없이 앱(pytest)이 끝난다.
    _edit = None
    _dark = True
    _kind_hint = None
    _ctrl = None
    _ACCEPT_PDF = True
    submitted = pyqtSignal(str, str, object, str)   # 종류, 글, 첨부(그림 PIL | 풀어 그리기면 PDF 경로 | None), 이름
    dismissed = pyqtSignal()                        # ✕·Esc

    def __init__(self, parent=None, controller: _AIController | None = None):
        super().__init__(parent)
        self.setObjectName("startPrompt")
        self.setFixedWidth(self.WIDTH)
        self.setAcceptDrops(True)
        self._init_image_attach_state()
        self._dark = True
        self._kind_hint = None     # 메뉴·단축키로 종류를 정해 열었을 때(안내글만 바뀜)
        self._ctrl = controller

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 14, 14)
        v.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self._title = QLabel("무엇을 그릴까요?", self)
        title_box.addWidget(self._title)
        self._sub = QLabel("", self)
        self._sub.setWordWrap(True)
        title_box.addWidget(self._sub)
        top.addLayout(title_box, 1)
        self._close_btn = QToolButton(self)
        self._close_btn.setAutoRaise(True)
        self._close_btn.setText("✕")
        self._close_btn.setToolTip("닫기 (Esc)")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.clicked.connect(self.dismissed)
        top.addWidget(self._close_btn, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)

        # 입력 카드(글 + 「+」·첨부·모델·만들기 줄)
        self._card = QFrame(self)
        self._card.setObjectName("startPromptCard")
        cl = QVBoxLayout(self._card)
        cl.setContentsMargins(10, 8, 8, 8)
        cl.setSpacing(6)
        self._edit = QPlainTextEdit(self._card)
        self._edit.setPlaceholderText(_DEFAULT_PLACEHOLDER)
        self._edit.setFixedHeight(64)
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.setAcceptDrops(False)   # 끌어다 놓기는 칸(dropEvent)이 받는다
        self._edit.installEventFilter(self)
        self._edit.textChanged.connect(self._hide_notice)
        cl.addWidget(self._edit)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._attach_btn = self._build_attach_button(self._card)
        self._attach_btn.setToolTip("파일 넣기 — 사진·PDF<br>· 끌어다 놓기<br>· Ctrl+V 붙여넣기")
        row.addWidget(self._attach_btn)
        row.addWidget(self._build_image_chip(self._card))
        row.addStretch(1)
        self._model_btn = QToolButton(self._card)
        self._model_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._model_btn.setToolTip("AI 모델 — 「자동」이면 만들 것에 맞춰 골라요. 펼치면 모델마다 가격이 보여요")
        self._model_menu = QMenu(self._model_btn)
        self._model_menu.aboutToShow.connect(self._fill_model_menu)
        self._model_btn.setMenu(self._model_menu)
        row.addWidget(self._model_btn)
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

        # 예시(누르면 칸에 채움 — 베끼기·풀어 그리기는 파일 고르기)
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

        self._credit_lbl = QLabel("", self)
        self._credit_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._credit_lbl.linkActivated.connect(self._on_credit_link)
        v.addWidget(self._credit_lbl)

        self._set_image_drop_frame(self._card, "", "")
        if controller is not None:
            controller.credit_changed.connect(self._credit_lbl.setText)
            controller.notice.connect(self._on_ctrl_notice)
            self._credit_lbl.setText(controller.credit_text)
        self.set_kind_hint(None)
        self._sync_model_btn()
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
        self._credit_lbl.setStyleSheet(f"color:{muted}; font-size:11px;")
        self._close_btn.setStyleSheet(f"QToolButton {{ color:{ink}; font-size:12px; }}")
        self._attach_btn.setStyleSheet(_attach_button_qss(ink))
        hover = "rgba(255,255,255,22)" if dark else "rgba(0,0,0,14)"
        self._model_btn.setStyleSheet(
            f"QToolButton {{ color:{fg}; border:1px solid rgba(128,128,128,120); border-radius:7px; padding:5px 9px; font-size:12px; }}"
            f"QToolButton:hover {{ background:{hover}; }}"
            "QToolButton::menu-indicator { image:none; width:0; }")
        for b in self._example_btns:
            b.setStyleSheet(
                f"QPushButton {{ color:{fg}; border:1px solid rgba(128,128,128,110); border-radius:12px; padding:4px 10px;"
                " font-size:12px; background:transparent; }"
                f"QPushButton:hover {{ background:{hover}; border-color:rgba(218,119,86,170); }}")
        self.update()

    # ---- 종류 안내(칩 없음) -----------------------------------------------------------

    def kind_hint(self):
        return self._kind_hint

    def set_kind_hint(self, kind):
        """메뉴·단축키로 종류를 정해 열 때 — 안내글만 그 종류로. None이면 짐작(기본)."""
        self._kind_hint = kind if kind in KIND_LABEL else None
        if self._kind_hint is None:
            self._sub.setText("말로 쓰거나 파일을 끌어다 놓으세요. 무엇을 만들지는 KAIROS가 알아서 정해요.")
            self._edit.setPlaceholderText(_DEFAULT_PLACEHOLDER)
        else:
            self._sub.setText(f"{KIND_LABEL[self._kind_hint]} 만들기 — 말로 쓰거나 파일을 끌어다 놓으세요.")
            self._edit.setPlaceholderText(PLACEHOLDER[self._kind_hint])
        self._edit.viewport().update()

    def kind(self) -> str:
        """지금 입력이면 무엇을 만들지(정해 연 종류가 있으면 그것, 아니면 짐작)."""
        if self._kind_hint is not None:
            return self._kind_hint
        return guess_kind(self._edit.toPlainText(), self._attached_image is not None, bool(self._attached_pdf))

    def _use_example(self, text: str, kind):
        if kind in ("trace", "explain"):
            self.set_kind_hint(kind)
            self._browse_image()
            return
        self._edit.setPlainText(text)
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)

    # ---- 모델 「자동 ▾」 ----------------------------------------------------------------

    def _sync_model_btn(self):
        choice = self._ctrl.model_choice() if self._ctrl is not None else AUTO
        self._model_btn.setText(f"모델 {'자동' if choice == AUTO else choice} ▾")

    def _fill_model_menu(self):
        """펼칠 때마다 다시 채운다 — 「자동(추천)」 + 받아 둔 가격표(없으면 받아 오는 중 안내)."""
        menu = self._model_menu
        menu.clear()
        ctrl = self._ctrl
        if ctrl is None:
            return
        group = QActionGroup(menu)
        choice = ctrl.model_choice()
        auto = menu.addAction("자동 (추천) — 만들 것에 맞춰 골라요")
        auto.setCheckable(True)
        auto.setChecked(choice == AUTO)
        auto.setData(AUTO)
        group.addAction(auto)
        info = ctrl.model_info()
        if info:
            head = menu.addAction("직접 고르기 — 100만 토큰당 $ (입력 / 출력)")
            head.setEnabled(False)
            for m in info:
                act = menu.addAction(ctrl.model_label(m))
                act.setCheckable(True)
                act.setChecked(m["id"] == choice)
                act.setData(m["id"])
                group.addAction(act)
        else:
            wait = menu.addAction("모델 목록·가격을 받아 오는 중… (KAIROS 키가 있어야 해요)")
            wait.setEnabled(False)
            ctrl.fetch_models()
        group.triggered.connect(self._on_model_picked)

    def _on_model_picked(self, act: QAction):
        if self._ctrl is not None:
            self._ctrl.set_model_choice(act.data())
        self._sync_model_btn()

    # ---- 크레딧·안내 -------------------------------------------------------------------

    def _on_credit_link(self, _href: str):
        if self._ctrl is not None:
            self._ctrl.open_gateway_settings(self.window())

    def _on_ctrl_notice(self, text: str):
        if self.isVisible():
            self._show_notice(text)

    def _show_notice(self, text: str):
        self._notice.setText(text)
        self._notice.setVisible(True)

    def _hide_notice(self):
        self._notice.setVisible(False)

    # ---- 파일(「+」·끌어다 놓기) -------------------------------------------------------------

    def _browse_image(self):
        """「+」 — 바로 파일 선택 창(하위 메뉴 없음). 모든 파일을 보이게 해, 못 읽는 걸 고르면 안내한다."""
        exts = " ".join(f"*{e}" for e in IMAGE_EXTS + (".pdf",))
        filt = f"사진·PDF ({exts});;모든 파일 (*)"
        if self._kind_hint == "explain":
            filt = "PDF (*.pdf);;" + filt
        path, _ = QFileDialog.getOpenFileName(self, "파일 넣기", "", filt)
        if path:
            self.attach_path(path)

    def attach_path(self, path: str) -> bool:
        """파일 하나 붙이기(「+」·끌어다 놓기 공용). 못 읽는 형식이면 안내하고 False."""
        low = path.lower()
        if low.endswith(".pdf"):
            self._set_attached_pdf(path)
            return True
        if low.endswith(IMAGE_EXTS):
            self._load_image_path(path)
            return True
        self._show_notice(unsupported_file_text(os.path.basename(path)))
        return False

    def _set_attached_image(self, pil_img, name: str):
        super()._set_attached_image(pil_img, name)
        self._hide_notice()

    def _set_attached_pdf(self, path: str):
        super()._set_attached_pdf(path)
        self._hide_notice()

    def dragEnterEvent(self, e):
        """지원하는 파일만이 아니라 아무 파일이나 받는다 — 못 읽는 건 놓았을 때 안내(§8 항목51)."""
        md = e.mimeData()
        if md.hasImage() or (md.hasUrls() and any(u.isLocalFile() for u in md.urls())):
            e.acceptProposedAction()
            self._set_drop_active(True)

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            for u in md.urls():
                if u.isLocalFile():
                    self._set_drop_active(False)
                    self.attach_path(u.toLocalFile())
                    e.acceptProposedAction()
                    return
        super().dropEvent(e)

    # ---- 만들기 -----------------------------------------------------------------

    def focus_prompt(self):
        self._edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def fill(self, text: str = "", image=None, image_name: str = "", pdf_path: str = ""):
        """기록 메뉴에서 고른 요청을 다시 채운다."""
        self._edit.setPlainText(text)
        super()._clear_image()
        if pdf_path:
            self._set_attached_pdf(pdf_path)
        elif image is not None:
            self._set_attached_image(image, image_name or "그림")

    def submit(self):
        """「만들기」·Enter — 입력을 검사해 `submitted`로 넘기고 칸을 비운다. 돌려준 값(종류)은 테스트용."""
        text = self._edit.toPlainText().strip()
        image = self._attached_image
        kind = self.kind()
        if kind == "trace" and image is None:
            self._show_notice("베끼기는 도면 사진이 필요해요. 사진을 끌어다 놓거나 Ctrl+V로 붙여 주세요.")
            return None
        if kind == "explain":
            pdf = self._attached_pdf
            if not pdf:
                self._show_notice("풀어 그리기는 PDF가 필요해요. PDF를 끌어다 놓거나 + 로 골라 주세요.")
                return None
            self._reset_input()
            self.submitted.emit(kind, text, pdf, os.path.basename(pdf))
            return kind
        if not text and image is None:
            self._show_notice("먼저 무엇을 그릴지 쓰거나 파일을 넣어 주세요.")
            return None
        name = self._attached_image_name if image is not None else ""
        self._reset_input()
        self.submitted.emit(kind, text, image, name)
        return kind

    def _reset_input(self):
        self._edit.clear()
        super()._clear_image()
        self.set_kind_hint(None)

    def eventFilter(self, obj, event):
        if obj is self._edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False   # Shift+Enter = 줄바꿈
                self.submit()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.dismissed.emit()
                return True
            if self._maybe_intercept_paste_image(event):
                return True
        return super().eventFilter(obj, event)
