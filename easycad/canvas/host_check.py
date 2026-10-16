"""CanvasWindow 믹스인 — 「도면 검사」(§8 항목48, 2026-10-16): 찾기는 `drawing_check`, 여기선 결과 카드·캔버스 표시·이동.

도구 메뉴 「도면 검사」(Ctrl+Shift+K) → 문제 자리마다 주황 점선 사각형 + 화면 위쪽 가운데 결과 카드(「2 / 5 · 연결 안 된 화살표 끝」,
◀ ▶로 그 자리로 이동·선택, 「다시 검사」, ✕). AI 흐름도 결과가 놓이면 그 결과만 자동 검사해 문제가 있으면 알림 한 줄.
표시는 문서(탭)마다 — 다른 탭에선 안 그린다. 카드를 닫거나 다시 검사하기 전까진 남는다(고친 뒤 「다시 검사」로 0개 확인).
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout

from easycad.canvas.drawing_check import check_drawing, summary
from easycad.canvas.host_widgets import _ACCENT_CORAL, _current_icon_color


class _CheckCard(QFrame):
    """결과 카드 — 배경·테두리는 paintEvent(조상 QSS 함정, `ai_panel.py` 주석), 글자색은 잎 위젯 QSS."""

    _dark = True   # 클래스 기본값 — GC 순서 함정 예방(`start_prompt._StartPrompt` 주석)

    def __init__(self, parent, on_prev, on_next, on_rerun, on_close):
        super().__init__(parent)
        self.setObjectName("checkCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 8, 8, 10)
        v.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(6)
        self._title = QLabel("도면 검사", self)
        top.addWidget(self._title)
        top.addStretch(1)
        self._prev = self._btn("◀", "앞 문제로", on_prev)
        self._next = self._btn("▶", "다음 문제로", on_next)
        self._rerun = self._btn("다시 검사", "고친 뒤 다시 찾기", on_rerun)
        self._close = self._btn("✕", "검사 표시 닫기", on_close)
        for b in (self._prev, self._next, self._rerun, self._close):
            top.addWidget(b)
        v.addLayout(top)
        self._summary = QLabel("", self)
        self._summary.setWordWrap(True)
        v.addWidget(self._summary)
        self._current = QLabel("", self)
        self._current.setWordWrap(True)
        v.addWidget(self._current)
        self.setFixedWidth(420)
        self.refresh_theme(True)

    def _btn(self, text, tip, slot):
        b = QToolButton(self)
        b.setText(text)
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.clicked.connect(slot)
        return b

    def refresh_theme(self, dark: bool):
        self._dark = dark
        fg = "#e6ebf0" if dark else "#1b222b"
        muted = "#8995a3" if dark else "#6a737e"
        self._title.setStyleSheet(f"color:{fg}; font-size:14px; font-weight:700;")
        self._summary.setStyleSheet(f"color:{muted}; font-size:12px;")
        self._current.setStyleSheet(f"color:{fg}; font-size:13px;")
        hover = "rgba(255,255,255,22)" if dark else "rgba(0,0,0,14)"
        for b in (self._prev, self._next, self._rerun, self._close):
            b.setStyleSheet(f"QToolButton {{ color:{fg}; border:1px solid rgba(128,128,128,110); border-radius:6px; padding:2px 8px; }}"
                            f"QToolButton:hover {{ background:{hover}; }}"
                            f"QToolButton:disabled {{ color:{muted}; }}")
        self.update()

    def show_issue(self, issues, idx):
        n = len(issues)
        self._summary.setText(summary(issues) if n else "찾은 문제가 없어요")
        if n:
            it = issues[idx]
            note = f" — {it.note}" if it.note else ""
            self._current.setText(f"<b style='color:{_ACCENT_CORAL}'>{idx + 1} / {n}</b> · {it.title}{note}")
        else:
            self._current.setText("")
        self._current.setVisible(bool(n))
        self._prev.setEnabled(n > 1)
        self._next.setEnabled(n > 1)
        self.adjustSize()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor("#222b35") if self._dark else QColor("#ffffff")))
        p.setPen(QPen(QColor(_ACCENT_CORAL), 1.2))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        p.end()
        super().paintEvent(event)


class _CheckMixin:
    """`_check` 상태: (문서, 문제 목록, 지금 번호) 또는 None."""

    _check = None
    _check_card = None

    # ---- 실행 ---------------------------------------------------------------------

    def _run_drawing_check(self):
        """도구 메뉴 「도면 검사」. 돌려준 값(문제 목록)은 테스트용."""
        issues = check_drawing(self._scene)
        if not issues:
            self._close_drawing_check()
            self.statusBar().showMessage("도면 검사 — 찾은 문제가 없어요", 4000)
            return issues
        self._check = [self._active_doc, issues, 0]
        card = self._ensure_check_card()
        card.show()
        self._check_goto(0)
        return issues

    def _ensure_check_card(self):
        if self._check_card is None:
            self._check_card = _CheckCard(self, lambda: self._check_step(-1), lambda: self._check_step(1),
                                          self._run_drawing_check, self._close_drawing_check)
            self._check_card.refresh_theme(getattr(self, "_dark", True))
        return self._check_card

    def _check_step(self, d):
        if not self._check:
            return
        n = len(self._check[1])
        self._check_goto((self._check[2] + d) % n)

    def _check_goto(self, idx):
        doc, issues, _ = self._check
        if doc is not self._active_doc:
            return
        self._check[2] = idx
        it = issues[idx]
        self._view.centerOn(it.where.center())
        self._scene.clearSelection()
        if it.item.scene() is self._scene and it.item.flags() & it.item.GraphicsItemFlag.ItemIsSelectable:
            it.item.setSelected(True)
        card = self._ensure_check_card()
        card.show_issue(issues, idx)
        self._place_check_card()
        card.raise_()
        self._view.viewport().update()

    def _close_drawing_check(self):
        self._check = None
        if self._check_card is not None:
            self._check_card.hide()
        self._view.viewport().update()

    def _place_check_card(self):
        card = self._check_card
        if card is None or not card.isVisible():
            return
        view = self._view
        o = view.mapTo(self, view.rect().topLeft())
        card.adjustSize()
        card.move(o.x() + (view.width() - card.width()) // 2, o.y() + 10)

    # ---- 그리기(`host_aimake._draw_ai_staging`가 부름) ------------------------------------

    def _draw_check_marks(self, view, painter):
        if not self._check:
            return
        doc, issues, cur = self._check
        if doc.view is not view:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        coral = QColor(_ACCENT_CORAL)
        for i, it in enumerate(issues):
            pen = QPen(coral, 3.0 if i == cur else 1.6, Qt.PenStyle.SolidLine if i == cur else Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            fill = QColor(coral)
            fill.setAlpha(40 if i == cur else 0)
            painter.setBrush(QBrush(fill))
            painter.drawRoundedRect(it.where.adjusted(-6, -6, 6, 6), 6, 6)
        painter.restore()

    # ---- AI 결과 자동 검사 ---------------------------------------------------------------

    def _check_ai_result(self, items):
        """AI 흐름도 임시 결과가 놓인 직후 — 그 결과만 검사해 문제가 있으면 알림 한 줄(표시는 「도면 검사」로)."""
        issues = check_drawing(self._scene, items=items)
        if issues:
            self.statusBar().showMessage(f"도면 검사: {summary(issues)} — 도구 ▸ 도면 검사로 자리를 볼 수 있어요", 6000)
        return issues
