"""CanvasWindow 믹스인 — 「AI로 만들기」 패널(§8 항목36) 호스트 쪽: 켜기/끄기, 요청 받기, 임시 결과.

임시 결과(2단계, 2026-10-05): AI 결과는 **실제 도형으로 캔버스에 넣고(되돌리기 한 칸)** 주황 점선 + 결과 막대만
덧씌운다 — 캔버스가 곧 미리보기(사용자 확정). 채택하면 표시만 지우고, 버리면 그 한 칸을 되돌린다.
자동 채택(사용자 확정): 임시 결과가 남은 채 다른 편집이 기록되거나, 새로 만들거나, 저장하면 그대로 채택
(Ctrl+Z로 지울 수 있으니 잃는 게 없다). 판단 길목은 둘뿐이다:
  ① 되돌리기 기록이 바뀔 때마다 부르는 `_refresh_history_actions`(이 믹스인이 덮어 `_ai_staging_sync`를 부름)
  ② 캔버스 그리기 마지막 단계(`core_view.drawForeground` → `_draw_ai_staging`) — 점선을 그리고 막대 자리를 맞춘다
     (씬 좌표로 그리므로 줌·스크롤·이동을 저절로 따라간다. 막대는 viewport 자식이라 스크롤 땐 Qt가 같이 민다).
⚠ 모듈 이름 `host_ai`는 옛 폐기 모듈 가드(`test_sketch_pipeline_and_host_ai_modules_removed`)에 걸려 쓰지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6 import sip
from PyQt6.QtCore import QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QWidget

from easycad.canvas.ai_panel import _AIPanel, PENDING_TEXT
from easycad.canvas.host_dialogs import _CORAL_BTN_QSS
from easycad.canvas.host_widgets import _ACCENT_CORAL

STAGED_TEXT = "캔버스에 임시로 놓음 — 채택하거나 버리세요"
ACCEPTED_TEXT = "✓ 넣음"
DISCARDED_TEXT = "버림"
UNDONE_TEXT = "되돌림"


@dataclass
class _StagedResult:
    doc: object                 # CanvasDocument
    items: list
    undo_entry: object          # 이 결과를 넣은 되돌리기 한 칸(_UndoEntry)
    request: object             # AIRequest
    bar: QWidget = None
    last_vp: QRect = field(default_factory=QRect)
    discarding: bool = False


class _StagingBar(QFrame):
    """임시 결과 바로 위에 뜨는 막대 — 「채택 … 버리기」 공통, 가운데는 종류별 조절(extras)."""

    def __init__(self, parent, on_accept, on_retry, on_discard, extras=()):
        super().__init__(parent)
        self.setObjectName("aiStagingBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#aiStagingBar { background:palette(window); border:1px solid rgba(128,128,128,140);"
            " border-radius:8px; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(5)
        self.accept_btn = self._btn("채택", on_accept, coral=True)
        lay.addWidget(self.accept_btn)
        for w in extras:
            w.setParent(self)
            lay.addWidget(w)
        self.retry_btn = self._btn("다시", on_retry)
        self.retry_btn.setToolTip("같은 요청으로 다시 만들어 바꿔치기")
        lay.addWidget(self.retry_btn)
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:rgba(128,128,128,120);")
        lay.addWidget(sep)
        self.discard_btn = self._btn("버리기", on_discard)
        lay.addWidget(self.discard_btn)
        self.adjustSize()

    def _btn(self, text, slot, coral=False):
        b = QToolButton(self)
        b.setText(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if coral:
            b.setStyleSheet(_CORAL_BTN_QSS.replace("padding: 6px 12px", "padding: 3px 12px"))
        b.clicked.connect(slot)
        return b


class _AIMakeMixin:
    _AI_STAGE_PAD_PX = 8      # 점선을 결과에서 띄우는 여백(화면 px)
    _AI_BAR_GAP_PX = 6        # 점선과 막대 사이(화면 px)

    # ---- 패널 켜기/끄기 ----------------------------------------------------------

    def _build_ai_panel(self):
        """`CanvasWindow.__init__`이 중앙 위젯(탭 옆)에 붙인다. 기본은 꺼짐."""
        self._ai_staged = None
        self._ai_panel = _AIPanel(self)
        self._ai_panel.close_requested.connect(self._close_ai_panel)
        self._ai_panel.make_requested.connect(self._on_ai_make_requested)
        return self._ai_panel

    def _toggle_ai_panel(self, checked: bool = False):
        self._set_ai_panel_visible(bool(checked))

    def _close_ai_panel(self):
        self._set_ai_panel_visible(False)

    def _set_ai_panel_visible(self, visible: bool, kind: str | None = None):
        """켜기/끄기의 단일 경로(메뉴·상단바·패널 ✕). 켜고 끄면 뷰 폭이 바뀌는데 창 크기는 그대로라
        `resizeEvent`가 안 온다 — 레이아웃을 즉시 다시 잡고 플로팅 카드·미니맵 사각형을 직접 갱신한다."""
        panel = self._ai_panel
        if kind is not None:
            panel.set_kind(kind)
        panel.setVisible(visible)
        act = self._act_ai_make
        if act.isChecked() != visible:
            act.blockSignals(True)
            act.setChecked(visible)
            act.blockSignals(False)
        lay = self.centralWidget().layout() if self.centralWidget() is not None else None
        if lay is not None:
            lay.activate()
        self._reposition_panels()
        self._refresh_minimap()
        if visible:
            panel.focus_prompt()

    # ---- 요청 ------------------------------------------------------------------

    def _on_ai_make_requested(self, req):
        """패널의 「만들기」. 새로 만들면 남아 있던 임시 결과는 채택(사용자 확정). 결과를 놓을 자리는
        만들기를 누른 순간의 화면 가운데(사용자 확정) — 생성이 끝날 때 화면이 옮겨 가 있어도 여기로."""
        self._ai_accept_staged()
        req.doc = self._active_doc
        req.center = self._view.mapToScene(self._view.viewport().rect().center())
        req.entry.set_status(PENDING_TEXT)   # 종류별 생성은 3~5단계에서 여기서 갈라 붙인다

    # ---- 임시 결과 ---------------------------------------------------------------

    def _ai_stage(self, items, req, extras=()):
        """`items`는 **이미 씬에 넣고 `push_undo_add_many`까지 마친** 결과. 그 한 칸을 기억하고 점선·막대를 띄운다."""
        self._ai_accept_staged()
        items = [it for it in items if it.scene() is self._scene]
        if not items or not self._undo:
            return None
        view = self._view
        st = _StagedResult(doc=self._active_doc, items=items, undo_entry=self._undo[-1], request=req)
        st.bar = _StagingBar(view.viewport(), self._ai_accept_staged, self._ai_retry_staged,
                             self._ai_discard_staged, extras)
        self._ai_staged = st
        if req is not None and getattr(req, "entry", None) is not None:
            req.entry.set_status(STAGED_TEXT, running=True)
        self._ai_place_bar()
        st.bar.show()
        view.viewport().update()
        return st

    def _ai_finish_staging(self, status: str):
        """점선·막대를 걷고 기록 칸 상태를 적는다(도형은 건드리지 않음 — 지울지는 호출부가 정한다)."""
        st = self._ai_staged
        if st is None:
            return
        self._ai_staged = None
        if st.bar is not None and not sip.isdeleted(st.bar):
            st.bar.hide()
            st.bar.deleteLater()
        entry = getattr(st.request, "entry", None) if st.request is not None else None
        if entry is not None and not sip.isdeleted(entry):
            entry.set_status(status)
        view = getattr(st.doc, "view", None)
        if view is not None and not sip.isdeleted(view):
            view.viewport().update()

    def _ai_accept_staged(self):
        if self._ai_staged is not None:
            self._ai_finish_staging(ACCEPTED_TEXT)

    def _ai_discard_staged(self):
        """버리기 — 그 한 칸이 맨 위면 되돌리고 다시 실행 목록에서도 뺀다(Ctrl+Y로 살아나지 않게).
        맨 위가 아니면(자동 채택 규칙상 드묾) 지우기를 새 기록으로 남긴다."""
        st = self._ai_staged
        if st is None:
            return
        st.discarding = True
        if st.doc is self._active_doc and self._undo and self._undo[-1] is st.undo_entry:
            self.undo()
            if self._redo and self._redo[-1] is st.undo_entry:
                self._redo.pop()
                self._refresh_history_actions()
        else:
            alive = [it for it in st.items if it.scene() is not None]
            for it in alive:
                it.scene().removeItem(it)
            self.push_undo_delete(alive)
        self._ai_finish_staging(DISCARDED_TEXT)

    def _ai_retry_staged(self):
        """다시 — 지금 결과를 버리고 같은 요청(글·그림·모델·종류)을 새 기록 칸으로 다시 보낸다."""
        st = self._ai_staged
        if st is None:
            return
        req = st.request
        self._ai_discard_staged()
        if req is not None:
            self._ai_panel.resubmit(req)

    def _refresh_history_actions(self):
        """되돌리기 기록이 바뀌는 모든 길목(쌓기·되돌리기·다시 실행·탭 전환)이 부른다 — 여기서 임시 결과를 맞춘다."""
        super()._refresh_history_actions()
        self._ai_staging_sync()

    def _ai_staging_sync(self):
        st = getattr(self, "_ai_staged", None)
        if st is None or st.discarding:
            return
        if st.doc not in self._docs:            # 그 탭을 닫았다
            self._ai_finish_staging(DISCARDED_TEXT)
            return
        undo = st.doc.undo
        if st.undo_entry not in undo:           # Ctrl+Z로 결과가 빠졌다
            self._ai_finish_staging(UNDONE_TEXT)
        elif undo[-1] is not st.undo_entry:     # 다른 편집이 기록됐다 → 자동 채택
            self._ai_finish_staging(ACCEPTED_TEXT)

    # ---- 점선·막대 그리기 ------------------------------------------------------------

    def _ai_staged_scene_rect(self) -> QRectF:
        st = self._ai_staged
        rect = QRectF()
        for it in st.items:
            if it.scene() is not None:
                rect = rect.united(it.sceneBoundingRect())
        return rect

    def _draw_ai_staging(self, view, painter):
        """`core_view.drawForeground`가 부른다(우리 확장 훅)."""
        st = getattr(self, "_ai_staged", None)
        if st is None or st.doc.view is not view:
            return
        rect = self._ai_staged_scene_rect()
        if rect.isNull():
            return
        s = view.transform().m11() or 1.0
        pad = self._AI_STAGE_PAD_PX / s
        rect = rect.adjusted(-pad, -pad, pad, pad)
        pen = QPen(QColor(_ACCENT_CORAL), 2.0, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 6 / s, 6 / s)
        painter.restore()
        vp = view.mapFromScene(rect).boundingRect()
        if vp != st.last_vp:
            QTimer.singleShot(0, self._ai_place_bar)   # 그리는 도중 위젯을 옮기지 않는다

    def _ai_place_bar(self):
        """막대를 점선 위(자리가 없으면 아래)에, 화면 밖으로 안 나가게 놓는다."""
        st = self._ai_staged
        if st is None or st.bar is None or sip.isdeleted(st.bar):
            return
        view = st.doc.view
        rect = self._ai_staged_scene_rect()
        if rect.isNull():
            return
        s = view.transform().m11() or 1.0
        pad = self._AI_STAGE_PAD_PX / s
        vp = view.mapFromScene(rect.adjusted(-pad, -pad, pad, pad)).boundingRect()
        st.last_vp = vp
        bar = st.bar
        bar.adjustSize()
        vw, vh = view.viewport().width(), view.viewport().height()
        x = max(4, min(vp.left(), vw - bar.width() - 4))
        y = vp.top() - bar.height() - self._AI_BAR_GAP_PX
        if y < 4:
            y = min(vp.bottom() + self._AI_BAR_GAP_PX, vh - bar.height() - 4)
        bar.move(int(x), int(max(4, y)))
        bar.raise_()

