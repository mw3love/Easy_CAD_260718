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

import time
from dataclasses import dataclass, field

from PyQt6 import sip
from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from easycad.ai import gateway as gw
from easycad.canvas.ai_panel import _AIPanel, PENDING_TEXT
from easycad.canvas.host_dialogs import _CORAL_BTN_QSS, _MERMAID_HEADER_RE, _MermaidGenWorker, _detach_worker
from easycad.canvas.host_widgets import _ACCENT_CORAL
from easycad.fileio.mermaid_import import MermaidError, parse_mermaid

STAGED_TEXT = "캔버스에 임시로 놓음 — 채택하거나 버리세요"
ACCEPTED_TEXT = "✓ 넣음"
DISCARDED_TEXT = "버림"
UNDONE_TEXT = "되돌림"
NO_KEY_TEXT = "게이트웨이 키가 없어요 — 고급 ▸ ⚙ 설정에서 넣어 주세요"
TAB_CLOSED_TEXT = "만드는 사이 그 탭이 닫혀서 버렸어요"
# 흐름도 결과 막대의 방향 고르기 — 옛 Mermaid 창 `_DIRECTIONS`와 같은 네 가지.
FLOW_DIRECTIONS = (("가로 →", "LR"), ("세로 ↓", "TD"), ("세로 ↑", "BT"), ("가로 ←", "RL"))


@dataclass
class _AIJob:
    request: object
    worker: object
    t0: float


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
        self._ai_jobs: dict = {}   # 워커 → _AIJob(돌고 있는 생성)
        self._ai_tick_timer = QTimer(self)
        self._ai_tick_timer.setInterval(1000)
        self._ai_tick_timer.timeout.connect(self._ai_tick)
        self._ai_panel = _AIPanel(self)
        self._ai_panel.close_requested.connect(self._close_ai_panel)
        self._ai_panel.make_requested.connect(self._on_ai_make_requested)
        self._ai_panel.code_insert_requested.connect(self._on_ai_code_insert)
        self._ai_panel.code_edited.connect(self._on_ai_code_edited)
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
        if req.kind == "flow":
            self._ai_start_job(req, _MermaidGenWorker, (req.text, req.model, gw.resolve_base_url(), req.image),
                               self._on_flow_generated)
        else:
            req.entry.set_status(PENDING_TEXT)   # 심볼·베끼기는 4~5단계에서 여기서 갈라 붙인다

    # ---- 생성 작업(백그라운드) ---------------------------------------------------------

    def _ai_start_job(self, req, worker_cls, args, on_success):
        """워커 하나 = 요청 하나. 여러 요청이 동시에 돌아도 된다(각자 기록 칸에 경과 시간). 결과 수신자는
        `self.sender()`로 자기 작업을 찾는다(QObject를 붙잡는 람다 연결 금지 — host_ui `_build_panel_menu` 주석의 크래시)."""
        key = gw.resolve_api_key()
        if not key:
            req.entry.set_status(NO_KEY_TEXT)
            return None
        worker = worker_cls(key, *args, parent=self)
        self._ai_jobs[worker] = _AIJob(req, worker, time.monotonic())
        worker.succeeded.connect(on_success)
        worker.failed.connect(self._on_ai_job_failed)
        worker.finished.connect(self._on_ai_job_finished)
        worker.start()
        self._ai_tick()
        self._ai_tick_timer.start()
        return worker

    def _ai_job_of_sender(self):
        return self._ai_jobs.get(self.sender())

    def _ai_tick(self):
        now = time.monotonic()
        for job in self._ai_jobs.values():
            entry = job.request.entry
            if entry is not None and not sip.isdeleted(entry):
                entry.set_status(f"만드는 중… {int(now - job.t0)}초", running=True)

    def _on_ai_job_failed(self, err):
        job = self._ai_job_of_sender()
        if job is not None:
            job.request.entry.set_status(f"실패: {err}")

    def _on_ai_job_finished(self):
        worker = self.sender()
        self._ai_jobs.pop(worker, None)
        if not self._ai_jobs:
            self._ai_tick_timer.stop()
        if worker is not None:
            worker.deleteLater()

    def _ai_detach_jobs(self):
        """창이 닫힐 때 — 돌고 있는 생성은 떼어 내 결과를 버린다(`_detach_worker`가 끝날 때까지 살려 둠)."""
        for worker in list(self._ai_jobs):
            _detach_worker(worker)
        self._ai_jobs.clear()
        self._ai_tick_timer.stop()
        self._ai_panel.detach_workers()

    def _ai_goto_request_doc(self, req) -> bool:
        """결과는 「만들기」를 누른 탭으로 — 그 사이 다른 탭으로 갔으면 되돌아가고, 닫혔으면 버린다."""
        if req.doc not in self._docs:
            req.entry.set_status(TAB_CLOSED_TEXT)
            return False
        if req.doc is not self._active_doc:
            self._tabs.setCurrentIndex(self._docs.index(req.doc))
        return True

    # ---- 흐름도 ------------------------------------------------------------------

    def _on_flow_generated(self, code, _used_model):
        job = self._ai_job_of_sender()
        if job is not None:
            self._ai_place_flow(job.request, code)

    def _ai_place_flow(self, req, code):
        """Mermaid 코드 → 도형·화살표(옛 Mermaid 창과 같은 배치 `_build_mermaid_items`)를 요청 자리에 임시로 놓는다."""
        if not self._ai_goto_request_doc(req):
            return None
        self._ai_accept_staged()
        try:
            _n, _a, direction, added = self._build_mermaid_items(code, req.center)
        except MermaidError as ex:
            req.entry.set_status(f"코드를 읽지 못했어요: {ex}")
            return None
        req.result_text = code
        self._ai_panel.show_flow_code(code)
        self.set_tool("select")
        return self._ai_stage(added, req, extras=self._ai_flow_extras(direction))

    def _ai_flow_extras(self, direction):
        lbl = QLabel("방향")
        lbl.setStyleSheet("color:#8a8a8a; font-size:11px; padding:0 2px;")
        combo = QComboBox()
        for label, token in FLOW_DIRECTIONS:
            combo.addItem(label, token)
        token = "TD" if direction.upper() == "TB" else direction.upper()
        combo.setCurrentIndex(max(0, combo.findData(token)))
        combo.currentIndexChanged.connect(self._on_flow_direction_changed)
        return (lbl, combo)

    def _on_flow_direction_changed(self, _i):
        st = self._ai_staged
        combo = self.sender()
        if st is None or st.request.kind != "flow" or combo is None:
            return
        code = getattr(st.request, "result_text", "")
        m = _MERMAID_HEADER_RE.match(code)
        if not m:
            return
        a, b = m.span(1)
        self._ai_replace_flow(code[:a] + combo.currentData() + code[b:])

    def _ai_replace_flow(self, code):
        """임시 흐름도를 새 코드로 다시 그린다(방향 바꾸기·코드 칸 고치기) — 되돌리기 기록은 늘지 않는다.
        코드가 틀리면 지금 결과를 그대로 두고 기록 칸에만 알린다."""
        st = self._ai_staged
        if st is None or st.request.kind != "flow":
            return None
        req = st.request
        # 파서는 머리줄 없는 글도 상자 하나로 받아 준다 — 고치는 도중의 반쪽 글로 결과가 갈아엎히지 않게 머리줄을 요구.
        if not _MERMAID_HEADER_RE.match(code):
            req.entry.set_status("코드 오류 — 이전 결과 유지: 첫 줄이 flowchart LR 같은 형식이어야 해요", running=True)
            return None
        try:
            parse_mermaid(code)
        except MermaidError as ex:
            req.entry.set_status(f"코드 오류 — 이전 결과 유지: {ex}", running=True)
            return None
        self._ai_drop_staged(st)
        self._ai_finish_staging("")
        return self._ai_place_flow(req, code)

    def _on_ai_code_insert(self, req):
        """고급 「코드로 넣기」 — AI 없이 코드 그대로(옛 Mermaid 창의 "직접 붙여넣기" 길)."""
        self._ai_accept_staged()
        req.doc = self._active_doc
        req.center = self._view.mapToScene(self._view.viewport().rect().center())
        self._ai_place_flow(req, self._ai_panel.flow_code())

    def _on_ai_code_edited(self, code):
        st = self._ai_staged
        if st is not None and st.request.kind == "flow" and code.strip() \
                and code != getattr(st.request, "result_text", ""):
            self._ai_replace_flow(code)

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
        self._ai_ensure_visible()
        self._ai_place_bar()
        st.bar.show()
        view.viewport().update()
        return st

    def _ai_free_viewport_rect(self, view) -> QRect:
        """viewport 안에서 양옆 떠 있는 카드(도형·레이어 / 속성·미니맵)에 가리지 않는 가운데 띠."""
        vp = view.viewport()
        origin = vp.mapTo(self, QPoint(0, 0))
        x0, x1 = 0, vp.width()
        for name, left_side in (("_left_panel", True), ("_layers_panel", True),
                                ("_props_panel", False), ("_minimap_panel", False)):
            panel = getattr(self, name, None)
            if panel is None or panel.isHidden():
                continue
            g = panel.geometry().translated(-origin.x(), -origin.y())
            if left_side:
                x0 = max(x0, g.right() + 8)
            else:
                x1 = min(x1, g.left() - 8)
        if x1 - x0 < 200:   # 창이 너무 좁으면 카드는 무시
            x0, x1 = 0, vp.width()
        return QRect(x0, 0, x1 - x0, vp.height())

    def _ai_ensure_visible(self):
        """결과가 카드 사이 빈 띠에 다 안 들어오면 그만큼만 축소해 보여 준다(확대는 하지 않음) — 넓은 흐름도의
        왼쪽이 「도형」 카드 밑에 깔리고 막대의 「채택」까지 가려지던 것(2026-10-05 실제 창)."""
        st = self._ai_staged
        view = st.doc.view
        rect = self._ai_staged_scene_rect()
        if rect.isNull():
            return
        free = self._ai_free_viewport_rect(view)
        room_px = (free.width() - 48, free.height() - 120)   # 양옆 여백 + 위 막대 자리
        s = view.transform().m11() or 1.0
        need = (rect.width() * s, rect.height() * s)
        if need[0] <= room_px[0] and need[1] <= room_px[1]:
            vis = view.mapToScene(free.adjusted(24, 60, -24, -24)).boundingRect()
            if vis.contains(rect):
                return
            factor = 1.0
        else:
            factor = min(room_px[0] / need[0], room_px[1] / need[1])
        if factor < 1.0:
            view.scale(factor, factor)
        # 빈 띠의 가운데에 결과 가운데를 맞춘다(viewport 가운데와 띠 가운데의 차이만큼 보정).
        view.centerOn(rect.center())
        dx = free.center().x() - view.viewport().rect().center().x()
        if dx:
            bar = view.horizontalScrollBar()
            bar.setValue(bar.value() - dx)
        self._update_zoom_label()
        self._refresh_minimap()

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
        self._ai_drop_staged(st)
        self._ai_finish_staging(DISCARDED_TEXT)

    def _ai_drop_staged(self, st):
        """임시 결과의 도형을 걷어 낸다(점선·막대는 그대로 — 호출부가 `_ai_finish_staging`한다)."""
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
        vh = view.viewport().height()
        free = self._ai_free_viewport_rect(view)   # 떠 있는 카드 밑에 깔리지 않게
        x = max(free.left() + 4, min(vp.left(), free.right() - bar.width() - 4))
        y = vp.top() - bar.height() - self._AI_BAR_GAP_PX
        if y < 4:
            y = min(vp.bottom() + self._AI_BAR_GAP_PX, vh - bar.height() - 4)
        bar.move(int(x), int(max(4, y)))
        bar.raise_()

