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

import math
import time
from dataclasses import dataclass, field

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QSlider, QToolButton, QWidget,
)

from easycad.ai import gateway as gw
from easycad.canvas.ai_panel import _AIPanel, PENDING_TEXT, _ai_icon
from easycad.canvas.host_widgets import _current_icon_color
from easycad.canvas.host_dialogs import (
    _MERMAID_HEADER_RE, _MermaidGenWorker, _SaveToSymbolsFolderDialog, _SvgGenWorker, _detach_worker,
)
from easycad.canvas.photo_dialog import _PhotoOpsWorker, _pil_to_pixmap
from easycad.fileio import symbol_library
from easycad.fileio.photo_ops import SCALE as _PHOTO_SCALE, ops_to_sketch
from easycad.fileio.document import insert_items
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
_DIR_ICONS = {"LR": "ai_dir_right", "TD": "ai_dir_down", "BT": "ai_dir_up", "RL": "ai_dir_left"}
_FREE_MARGIN = 40.0       # 빈 자리 찾기: 기존 도형과 띄울 거리(씬 단위)
# 결과·준비 막대 버튼 — 채택(코랄)과 나머지(테두리만)를 같은 테두리 두께·여백·모서리·굵기로.
_BAR_BTN_QSS = ("QToolButton { border:1px solid rgba(128,128,128,150); border-radius:7px; padding:3px 10px;"
                " font-weight:600; background:transparent; }"
                "QToolButton:hover { background:rgba(128,128,128,45); }"
                "QToolButton:pressed, QToolButton:checked { background:rgba(218,119,86,90); border-color:#da7756; }"
                "QToolButton:disabled { color:rgba(128,128,128,150); }")
_BAR_CORAL_QSS = ("QToolButton { border:1px solid #da7756; border-radius:7px; padding:3px 10px; font-weight:600;"
                  " background:#da7756; color:#1b120d; }"
                  "QToolButton:hover { background:#e08a6c; }"
                  "QToolButton:pressed { background:#c2673f; }"
                  "QToolButton:disabled { background:#6b5148; border-color:#6b5148; }")
_FREE_RINGS = 8           # 빈 자리 찾기: 가운데에서 몇 바퀴까지 찾나
SYMBOL_COUNT = 6          # 심볼 후보 수(패널 입력칸 「후보 6」)
SYMBOL_GAP = 40.0         # 후보 칸 사이(씬 단위)
UNPICKED_TEXT = "고르지 않아 후보를 버렸어요"
# 이어 만들기(2026-10-05 피드백 6차): 심볼은 후보 줄을 아래로 쌓고, 흐름도는 원본 옆에 새 결과를 나란히 놓아 고른다.
KEPT_TEXT = "이어 만들기 — 후보는 그대로 두고 아래 줄에 추가"
ORIGINAL_TEXT = "원본 — 오른쪽 새 결과와 나란히 비교 중"
KEPT_BOTH_TEXT = "✓ 넣음(원본도 남김)"
CHOSE_NEW_TEXT = "새 결과를 골라 지움"
CHOSE_ORIGINAL_TEXT = "원본을 골라 버림"
LEFT_TEXT = "✓ 넣음(이어 고치기 비교에서 빠져 캔버스에 남김)"
_COMPARE_GAP = 120.0      # 흐름도 원본과 새 결과 사이(씬 단위)
_CHECK_PX = 16      # 후보 칸 체크 표시 크기(화면 px)
_CHECK_INSET_PX = 4
TRACE_HINT = "주황 점을 종이 네 귀퉁이로 끌어 맞추고 「만들기」"
TRACE_NO_PHOTO_TEXT = "베끼기 사진이 캔버스에 없어요 — 사진을 다시 붙여 주세요"
TRACE_BUSY_TEXT = "다른 베끼기가 만드는 중이에요 — 끝나거나 취소한 뒤에 다시"
CANCELLING_TEXT = "취소하는 중 — 지금 호출이 끝나면 멈춰요"
CANCELLED_TEXT = "취소함"
_TRACE_CORNER_HIT_PX = 14
# 베끼기 피드백(2026-10-06): 안내글을 코랄로(흐린 사진 위 회색이 안 보임), 결과는 사진을 도면에 넣지 않고 고르는 동안만 겹쳐 본다.
_TRACE_HINT_QSS = f"color:{_ACCENT_CORAL}; font-size:11px; padding:0 4px;"
_TRACE_HINT_RUNNING_QSS = _TRACE_HINT_QSS + " font-weight:700;"
# 결과 막대 「도면 ↔ 원본」 막대 기본(%) — 원본 사진을 도면 *위에* 이만큼 덮어 그린다(0=도면만, 100=원본만, 2026-10-06 2차).
TRACE_PHOTO_OPACITY = 40
_TRACE_VIEW_MAX_SIDE = 4000
# 부분 다시 베끼기(2026-10-06): 결과에서 틀린 곳만 상자로 골라 그 부분만 다시 그려 같은 결과(되돌리기 한 칸)에 바꿔 끼운다.
REGION_PICK_TEXT = "고칠 부분을 사진 위에 상자로 끌어 주세요"
REGION_HINT = "틀린 점을 오른쪽 입력칸에 적어도 돼요(비워도 됨)"
REGION_DONE_TEXT = "✓ 고른 부분을 다시 그려 바꿈"
REGION_LOST_TEXT = "결과가 이미 정리돼서 버렸어요"
_REGION_MIN_PX = 12   # 이보다 작게 끈 상자(화면 px)는 클릭으로 보고 무시   # 비교용으로 띄우는 원본(펴기만 하고 AI용 1600으로 줄이지 않음 — 확대해도 또렷하게)


@dataclass
class _TraceSetup:
    """베끼기 준비(사진을 캔버스 바닥에 깔고 모서리 4점 맞추기) → 만드는 중 → 결과가 오면 걷힌다."""
    doc: object
    original: object            # 첨부 원본(PIL)
    fitted: object              # AI에 보낼 크기로 줄인 것(PIL) — 화면 표시·모서리 좌표의 기준
    pixmap: object              # 흐리게 구운 표시용
    rect: QRectF                # 씬 위 사진 자리
    quad: list                  # 모서리 4점(fitted 픽셀, 왼위·오위·오아래·왼아래)
    bar: QWidget = None
    hint: QLabel = None
    make_btn: QToolButton = None
    rotate_btn: QToolButton = None
    reset_btn: QToolButton = None
    remove_btn: QToolButton = None
    cancel_btn: QToolButton = None
    running: bool = False
    req: object = None
    worker: object = None
    sent: object = None         # 실제로 보낸(펴고 줄인) 사진 — 결과 좌표의 기준
    view_img: object = None     # 같은 모서리로 편 원본 해상도 사진(결과 비교 표시용)
    drag: int = None
    last_vp: QRect = field(default_factory=QRect)


@dataclass
class _Cand:
    svg: str
    model: str
    items: list


@dataclass
class _AIJob:
    request: object
    worker: object
    t0: float
    progress: tuple = None      # 베끼기 (끝난 구역, 전체)


@dataclass
class _StagedResult:
    doc: object                 # CanvasDocument
    items: list
    undo_entry: object          # 이 결과를 넣은 되돌리기 한 칸(_UndoEntry)
    request: object             # AIRequest
    bar: QWidget = None
    last_vp: QRect = field(default_factory=QRect)
    discarding: bool = False
    # ---- 심볼 후보 줄(4단계) — slots가 있으면 후보 줄이다. 후보는 고르기 전엔 되돌리기 기록에 안 넣는다.
    slots: list = None          # 후보 칸(QRectF, 씬 좌표)
    cands: list = field(default_factory=list)   # 도착한 후보(_Cand) — 칸 순서 = 도착 순서
    pending: int = 0            # 아직 안 끝난 생성 수
    errors: list = field(default_factory=list)
    picked: set = field(default_factory=set)    # Ctrl+클릭으로 고른 후보 번호
    snap: tuple = None          # 후보를 띄울 때의 (기록 길이, 맨 위 칸) — 바뀌면 다른 작업이 있었던 것
    all_btn: QToolButton = None   # 후보 막대 「모두 선택/모두 풀기」
    clearing_sel: bool = False
    row_start: int = 0          # 이어 만들기로 붙인 지금 줄의 첫 칸 번호(앞 줄들은 그대로 남는다)
    base_marks: set = field(default_factory=set)   # 지금 줄의 바탕이 된 후보 번호(「바탕」 표시)
    # ---- 흐름도 이어 고치기 비교(피드백 6차) — alt는 왼쪽에 남겨 둔 원본(_StagedResult), marks는 상대편과 다른 도형.
    alt: object = None
    alt_bar: QWidget = None
    both_btn: QToolButton = None   # 비교 중 새 결과 막대의 「둘 다 넣기」
    marks: list = field(default_factory=list)
    alt_marks: list = field(default_factory=list)
    # ---- 베끼기 결과(2026-10-06) — 고르는 동안만 바닥에 겹쳐 보는 원본 사진(도형 아님 — 채택해도 도면에 안 남는다).
    photo: object = None        # QPixmap(원본 해상도로 편 것)
    photo_rect: QRectF = None   # 씬 좌표
    photo_shown: bool = True
    photo_opacity: int = TRACE_PHOTO_OPACITY
    trace_sent: object = None   # AI에 보낸 펴진 사진(PIL) — 부분 다시 베끼기도 같은 사진·좌표로
    trace_ops: list = None      # 지금 결과의 ops(원본 px) — 부분 다시 때 그 부분의 이전 결과로 같이 보냄
    region_btn: QToolButton = None
    region_picking: bool = False
    region_drag: tuple = None   # 끄는 중 (시작 씬 점, 지금 씬 점)
    region: tuple = None        # 고른 부분(원본 px x1,y1,x2,y2)
    region_bar: QWidget = None
    region_label: QLabel = None
    region_make_btn: QToolButton = None
    region_worker: object = None
    region_last_vp: QRect = field(default_factory=QRect)


class _TraceRegionWorker(QThread):
    """부분 다시 베끼기 — `generate_ops_region` 한 번(수십 초)을 메인 스레드 밖에서."""
    succeeded = pyqtSignal(dict, dict)
    failed = pyqtSignal(str)

    def __init__(self, api_key, base_url, photo, region, note, prev_ops, model, parent=None):
        super().__init__(parent)
        self._args = (api_key, base_url, photo, region, note, prev_ops, model)

    def run(self):
        from easycad.ai.photo_to_ops import generate_ops_region
        key, base_url, photo, region, note, prev_ops, model = self._args
        try:
            client = gw._client(key, base_url, timeout=600.0)
            spec, log = generate_ops_region(client, photo, region, model=model, note=note, prev_ops=prev_ops)
        except Exception as e:  # noqa: BLE001 — 실패 사유를 그대로 기록 칸에
            self.failed.emit(str(e))
            return
        self.succeeded.emit(spec, log)


class _StagingBar(QFrame):
    """임시 결과 바로 위에 뜨는 막대 — 「채택 … 버리기」 공통, 가운데는 종류별 조절(extras)."""

    def __init__(self, parent, on_accept, on_retry, on_discard, extras=(), discard_text="버리기"):
        super().__init__(parent)
        self.setObjectName("aiStagingBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "QFrame#aiStagingBar { background:palette(window); border:1px solid rgba(128,128,128,140);"
            " border-radius:8px; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(5)
        self.accept_btn = self._btn("채택", on_accept, coral=True, icon="ai_check")
        lay.addWidget(self.accept_btn)
        for w in extras:
            w.setParent(self)
            lay.addWidget(w)
        self.retry_btn = None
        if on_retry is not None:   # 심볼 후보 막대엔 없음(2026-10-05 피드백 3차)
            self.retry_btn = self._btn("다시", on_retry, icon="refresh")
            self.retry_btn.setToolTip("같은 요청으로 다시 만들어 바꿔치기")
            lay.addWidget(self.retry_btn)
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:rgba(128,128,128,120);")
        lay.addWidget(sep)
        self.discard_btn = self._btn(discard_text, on_discard, icon="ai_trash")
        lay.addWidget(self.discard_btn)
        self.adjustSize()

    def _btn(self, text, slot, coral=False, icon=None):
        b = _icon_button(self, text, icon, coral=coral)
        b.clicked.connect(slot)
        return b


def _icon_button(parent, text, icon, coral=False, tip=None):
    """결과·준비 막대 버튼 — 아이콘 + 글(2026-10-05 시안 4차 1번, 사용자 선택). 아이콘 색은 그 순간 테마 색으로 굽는다
    (막대는 결과마다 새로 만들어 테마 전환 뒤에도 새 색)."""
    b = QToolButton(parent)
    b.setText(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setProperty("aiIcon", icon or "")
    b.setProperty("aiCoral", bool(coral))
    if icon:
        b.setIcon(_ai_icon(icon, "#1b120d" if coral else _current_icon_color()))
        b.setIconSize(QSize(14, 14))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    # 모든 막대 버튼을 같은 크기·여백·글씨로(2026-10-05 피드백 3차: 채택만 스타일이 있어 나머지 중심이 어긋나 보임).
    b.setStyleSheet(_BAR_CORAL_QSS if coral else _BAR_BTN_QSS)
    if tip:
        b.setToolTip(tip)
    return b


def _flow_diff_items(code, other_code, items) -> list:
    """`code`로 그린 `items`(`_build_mermaid_items`가 돌려준 순서: 노드들 → 화살표들) 가운데 `other_code`에 똑같은
    짝이 없는 것. 노드는 (글, 모양), 화살표는 (앞 노드 글, 뒤 노드 글, 화살표 글)로 맞춘다 — AI가 노드 id만 바꿔
    붙여도 글이 같으면 같은 것으로 본다. 코드를 못 읽거나 개수가 안 맞으면 빈 목록(표시만 안 할 뿐)."""
    from collections import Counter
    try:
        g, h = parse_mermaid(code), parse_mermaid(other_code)
    except MermaidError:
        return []

    def text(gr, nid):
        n = gr.nodes.get(nid)
        return ((n.label or n.id) if n is not None else nid).strip()

    def edges(gr):   # 빌더가 실제로 그리는 화살표만(양끝이 있고 자기 자신으로 가지 않는 것)
        return [e for e in gr.edges if e.src in gr.nodes and e.dst in gr.nodes and e.src != e.dst]

    def node_keys(gr):
        return [(text(gr, nid), gr.nodes[nid].shape) for nid in gr.nodes]

    def edge_keys(gr):
        return [(text(gr, e.src), text(gr, e.dst), (e.label or "").strip()) for e in edges(gr)]
    keys = node_keys(g) + edge_keys(g)
    if len(keys) != len(items):
        return []
    left = Counter(node_keys(h) + edge_keys(h))
    out = []
    for key, it in zip(keys, items):
        if left[key] > 0:
            left[key] -= 1
        else:
            out.append(it)
    return out


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
        self._ai_trace = None
        self._ai_panel.trace_photo_changed.connect(self._on_ai_trace_photo)
        self._ai_panel.entry_removed.connect(self._on_ai_entry_removed)
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
        base = getattr(req, "followup_of", None)
        center = None
        cur = self._ai_staged
        if base is not None and cur is not None and base is cur.alt:
            center = self._ai_items_rect(base.items).center()   # 비교 중인 원본 쪽에서 이어 고침 — 비교는 결과가 올 때 정리
        elif base is not None and base is self._ai_staged:
            # 이어 만들기 — 바탕 결과는 지우지 않는다(피드백 6차). 심볼은 후보 줄 아래에 새 줄을 붙이고
            # (`_ai_extend_candidates`), 흐름도는 새 결과가 오면 원본 옆에 나란히 놓아 고르게 한다(`_ai_place_flow`).
            center = self._ai_staged_scene_rect().center()
            if base.slots is not None and getattr(req, "replace_target", None) is None:
                req.replace_target = getattr(base.request, "replace_target", None)   # 「AI로 바꾸기」 줄이면 이어서도
        else:
            self._ai_accept_staged()
        req.doc = self._active_doc
        req.center = center if center is not None else self._view.mapToScene(self._view.viewport().rect().center())
        target, self._ai_replace_target = getattr(self, "_ai_replace_target", None), None
        if req.kind == "symbol" and target is not None and target.scene() is self._scene \
                and getattr(req, "replace_target", None) is None:
            req.replace_target = target   # 우클릭 「AI로 바꾸기」로 연 요청 — 고르면 그 도형 자리에 바뀜
        if req.kind == "flow":
            self._ai_start_job(req, _MermaidGenWorker, (req.text, req.model, gw.resolve_base_url(), req.image),
                               self._on_flow_generated, base_code=getattr(req, "base_code", "") or "")
        elif req.kind == "symbol":
            self._ai_start_symbol(req)
        elif req.kind == "trace":
            if base is not None and base is self._ai_staged and base.trace_sent is not None:
                self._ai_start_trace_region(req)
            else:
                self._ai_start_trace(req)
        else:
            req.entry.set_status(PENDING_TEXT)

    # ---- 생성 작업(백그라운드) ---------------------------------------------------------

    def _ai_start_job(self, req, worker_cls, args, on_success, **kw):
        """워커 하나 = 요청 하나. 여러 요청이 동시에 돌아도 된다(각자 기록 칸에 경과 시간). 결과 수신자는
        `self.sender()`로 자기 작업을 찾는다(QObject를 붙잡는 람다 연결 금지 — host_ui `_build_panel_menu` 주석의 크래시)."""
        key = gw.resolve_api_key()
        if not key:
            req.entry.set_status(NO_KEY_TEXT)
            return None
        worker = worker_cls(key, *args, parent=self, **kw)
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
        st = self._ai_staged
        for job in self._ai_jobs.values():
            entry = job.request.entry
            if entry is None or sip.isdeleted(entry):
                continue
            sec = int(now - job.t0)
            tr = self._ai_trace
            if job.request.kind == "symbol" and st is not None and st.request is job.request:
                entry.set_status(f"후보 {len(st.cands) - st.row_start}/{len(st.slots) - st.row_start} 도착 · {sec}초",
                                 running=True)
            elif job.request.kind == "trace":
                if getattr(job.worker, "_cancel", False):
                    continue   # 취소 중 — 「취소하는 중」 글을 덮지 않는다
                done = f"{job.progress[0]}/{job.progress[1]} 구역 · " if job.progress else ""
                text = f"만드는 중… {done}{sec // 60}분 {sec % 60}초" if sec >= 60 else f"만드는 중… {done}{sec}초"
                entry.set_status(text, running=True)
                if tr is not None and tr.req is job.request and tr.hint is not None:
                    tr.hint.setText(text)
                if st is not None and st.region_worker is job.worker and st.region_label is not None:
                    st.region_label.setText(f"고른 부분을 다시 그리는 중… {sec}초")
            else:
                entry.set_status(f"만드는 중… {sec}초", running=True)

    def _on_ai_job_failed(self, err):
        job = self._ai_job_of_sender()
        if job is not None:
            job.request.entry.set_status(f"실패: {err}")

    def _on_ai_job_finished(self):
        worker = self.sender()
        job = self._ai_jobs.pop(worker, None)
        if job is not None and job.request.kind == "symbol":
            self._ai_symbol_job_done(job.request)
        if not self._ai_jobs:
            self._ai_tick_timer.stop()
        if worker is not None:
            worker.deleteLater()

    def _ai_detach_jobs(self):
        """창이 닫힐 때 — 돌고 있는 생성은 떼어 내 결과를 버린다(`_detach_worker`가 끝날 때까지 살려 둠).
        베끼기는 남은 구역 호출(크레딧)을 막으려 취소부터 건다."""
        for worker in list(self._ai_jobs):
            cancel = getattr(worker, "request_cancel", None)
            if cancel is not None:
                try:
                    cancel()
                except RuntimeError:
                    pass
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

    def _ai_place_flow(self, req, code, alt=None):
        """Mermaid 코드 → 도형·화살표(옛 Mermaid 창과 같은 배치 `_build_mermaid_items`)를 요청 자리에 임시로 놓는다.
        이어 고치기 결과면 바탕(원본)을 지우지 않고 왼쪽에 남겨 새 결과를 그 오른쪽에 나란히 놓는다(피드백 6차 — 끝에만
        붙여 달라 해도 AI가 가운데를 고칠 수 있어 눈으로 비교). `alt`는 비교 중인 새 결과를 다시 그릴 때 넘기는 원본."""
        if not self._ai_goto_request_doc(req):
            return None
        base = getattr(req, "followup_of", None)
        cur = self._ai_staged
        if alt is None and base is not None and cur is not None and cur.slots is None \
                and base.doc is self._active_doc:
            # 이어 고치기를 거듭해도 비교는 늘 「바탕 ↔ 새 결과」 둘. 비교에 안 끼는 쪽은 지우지 않고 캔버스에 남긴다(사용자 결정).
            if base is cur and self._undo and self._undo[-1] is base.undo_entry:
                self._ai_end_alt(base, LEFT_TEXT)
                self._ai_staged = None           # 바탕은 임시 결과에서 내려 원본 자리로(막대는 아래에서 바꿔 단다)
                if base.bar is not None and not sip.isdeleted(base.bar):
                    base.bar.hide()
                    base.bar.deleteLater()
                base.bar = None
                alt = base
            elif base is cur.alt and base.undo_entry in self._undo:   # 원본 쪽에서 이어 고침 — 새 결과 쪽이 빠진다
                self._ai_end_alt(cur)
                self._ai_finish_staging(LEFT_TEXT)
                alt = base
            if alt is not None and base.request.entry is not None and not sip.isdeleted(base.request.entry):
                base.request.entry.set_status(ORIGINAL_TEXT, running=True)
        self._ai_accept_staged()
        try:
            _n, _a, direction, added = self._build_mermaid_items(code, req.center)
        except MermaidError as ex:
            req.entry.set_status(f"코드를 읽지 못했어요: {ex}")
            if alt is not None:
                self._ai_restage_flow(alt)
            return None
        # 기존 도면과 겹치면 가장 가까운 빈 자리로 다시 놓는다(배치는 결정적이라 옮겨 다시 그려도 같은 모양).
        # 비교 중이면 원본 오른쪽부터 찾는다.
        box = self._ai_items_rect(added)
        near = box.center()
        if alt is not None:
            ar = self._ai_items_rect(alt.items)
            near = QPointF(ar.right() + _COMPARE_GAP + box.width() / 2, ar.center().y())
        spot = self._ai_find_free_center(self._scene, box.width(), box.height(), near, exclude=added)
        if (spot - box.center()).manhattanLength() > 1.0:
            self._ai_undo_top_silently()
            _n, _a, direction, added = self._build_mermaid_items(code, req.center + (spot - box.center()))
        req.result_text = code
        self._ai_panel.show_flow_code(code)
        self.set_tool("select")
        # 흐름도 막대엔 「다시」가 없다(2026-10-05 피드백 5차 — 같은 요청은 기록 칸을 눌러 다시 채우면 됨).
        st = self._ai_stage(added, req, extras=self._ai_flow_extras(direction), retry=False)
        if st is not None and alt is not None:
            self._ai_begin_compare(st, alt, added)
        return st

    # ---- 흐름도 이어 고치기 비교(피드백 6차) ------------------------------------------------

    def _ai_begin_compare(self, st, alt, added):
        """새 결과(st) 왼쪽에 원본(alt)을 남겨 둔 비교 상태. 두 막대가 같은 조절(이걸로·방향·이어 고치기·버리기)을 갖고
        (피드백 6차 2회: 원본도 방향을 바꿔 보거나 이어 고칠 수 있게), 새 결과 막대엔 「둘 다 넣기」가 더 있다.
        서로 다른 도형은 주황으로 표시."""
        st.alt = alt
        self._ai_update_marks(st)
        st.bar.accept_btn.clicked.disconnect()
        st.bar.accept_btn.clicked.connect(self._ai_choose_new)
        st.bar.accept_btn.setText("이걸로")
        st.bar.accept_btn.setToolTip("새 결과를 쓰고 왼쪽 원본은 지우기")
        st.bar.discard_btn.setToolTip("새 결과를 버리고 원본으로 돌아가기")
        both = _icon_button(st.bar, "둘 다 넣기", "ai_check", tip="원본과 새 결과를 둘 다 캔버스에 넣기")
        both.clicked.connect(self._ai_keep_both)
        lay = st.bar.layout()
        lay.insertWidget(lay.count() - 2, both)   # 구분선·버리기 앞
        both.show()   # 떠 있는 막대에 넣은 버튼은 나중에 보여져 폭 계산에서 빠진다 — 글이 「이…기」로 잘림(실제 창)
        st.bar.adjustSize()
        st.both_btn = both
        view = st.doc.view
        self._ai_make_alt_bar(st)
        n = len(st.marks)
        if st.request.entry is not None:
            st.request.entry.set_status(
                f"원본과 다른 곳 {n}군데 주황 표시 — 「이걸로」로 고르세요" if n else "원본과 같아요 — 「이걸로」로 고르세요",
                running=True)
        self._ai_ensure_visible(view, self._ai_staged_scene_rect().united(self._ai_items_rect(alt.items)))
        self._ai_place_bar()
        view.viewport().update()

    def _ai_update_marks(self, st):
        alt = st.alt
        old_code = getattr(alt.request, "result_text", "")
        new_code = st.request.result_text
        st.marks = _flow_diff_items(new_code, old_code, [it for it in st.items if it.scene() is not None])
        st.alt_marks = _flow_diff_items(old_code, new_code, [it for it in alt.items if it.scene() is not None])

    def _ai_make_alt_bar(self, st):
        """원본 위 막대 — 「원본」 이름표 + 새 결과 막대와 같은 조절(방향·이어 고치기는 원본 쪽에 걸린다)."""
        if st.alt_bar is not None and not sip.isdeleted(st.alt_bar):
            st.alt_bar.hide()
            st.alt_bar.deleteLater()
        view = st.doc.view
        bar = QFrame(view.viewport())
        bar.setObjectName("aiStagingBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setStyleSheet(self._AI_BAR_QSS)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(5)
        lbl = QLabel("원본", bar)
        lbl.setStyleSheet("font-weight:600; padding:0 4px;")
        lay.addWidget(lbl)
        pick = _icon_button(bar, "이걸로", "ai_check", tip="원본을 쓰고 새 결과는 버리기")
        pick.clicked.connect(self._ai_choose_original)
        lay.addWidget(pick)
        m = _MERMAID_HEADER_RE.match(getattr(st.alt.request, "result_text", ""))
        for w in self._ai_flow_extras(m.group(1) if m else "TD", side="alt"):
            w.setParent(bar)
            lay.addWidget(w)
        sep = QFrame(bar)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:rgba(128,128,128,120);")
        lay.addWidget(sep)
        drop = _icon_button(bar, "버리기", "ai_trash", tip="원본만 버리고 새 결과는 남기기")
        drop.clicked.connect(self._ai_discard_alt)
        lay.addWidget(drop)
        bar.adjustSize()
        st.alt_bar = bar
        bar.show()
        return bar

    def _ai_end_alt(self, st, status=None):
        """비교 상태를 걷는다(원본 막대·「둘 다 넣기」 치우고 새 결과 막대를 보통으로). `status`가 있으면 원본 기록 칸에
        적는다. 원본 도형은 건드리지 않는다."""
        alt, st.alt = st.alt, None
        if st.alt_bar is not None and not sip.isdeleted(st.alt_bar):
            st.alt_bar.hide()
            st.alt_bar.deleteLater()
        st.alt_bar = None
        if st.both_btn is not None and not sip.isdeleted(st.both_btn):
            st.both_btn.hide()
            st.both_btn.deleteLater()
        st.both_btn = None
        if alt is not None and st.bar is not None and not sip.isdeleted(st.bar):
            st.bar.accept_btn.clicked.disconnect()
            st.bar.accept_btn.clicked.connect(self._ai_accept_staged)
            st.bar.accept_btn.setText("채택")
            st.bar.accept_btn.setToolTip("")
            st.bar.discard_btn.setToolTip("")
            st.bar.adjustSize()
        st.marks, st.alt_marks = [], []
        if alt is not None and status is not None:
            entry = getattr(alt.request, "entry", None)
            if entry is not None and not sip.isdeleted(entry):
                entry.set_status(status)
        return alt

    def _ai_keep_both(self):
        """새 결과 막대 「둘 다 넣기」 — 원본·새 결과 모두 채택(자동 채택과 같은 결과)."""
        if self._ai_staged is not None:
            self._ai_finish_staging(ACCEPTED_TEXT)

    def _ai_discard_alt(self):
        """원본 막대 「버리기」 — 원본만 지우고 새 결과는 보통 임시 결과로 남는다."""
        st = self._ai_staged
        if st is not None and st.alt is not None:
            self._ai_drop_alt(st, DISCARDED_TEXT)
            if st.request.entry is not None and not sip.isdeleted(st.request.entry):
                st.request.entry.set_status(STAGED_TEXT, running=True)
            self._ai_place_bar()
            st.doc.view.viewport().update()

    def _ai_redraw_alt(self, code):
        """원본 쪽 방향 바꾸기 — 원본을 제자리에서 다시 그린다. 원본 기록 칸은 새 결과 칸 밑이라, 다시 그린 기록을 같은
        자리에 바꿔 끼운다(기록 칸 수 그대로). 넓어져 새 결과에 닿으면 왼쪽으로 민다."""
        st = self._ai_staged
        alt = st.alt if st is not None else None
        if alt is None or alt.doc is not self._active_doc or alt.undo_entry not in self._undo:
            return None
        try:
            parse_mermaid(code)
        except MermaidError as ex:
            alt.request.entry.set_status(f"코드 오류 — 원본 유지: {ex}", running=True)
            return None
        undo = self._undo
        idx = undo.index(alt.undo_entry)
        old = self._ai_items_rect(alt.items)
        limit = self._ai_staged_scene_rect().left() - _COMPARE_GAP
        st.discarding = True   # 다시 그리는 동안 기록이 바뀌어도 자동 채택하지 않게
        try:
            for it in alt.items:
                if it.scene() is not None:
                    it.scene().removeItem(it)
            center = old.center()
            _n, _a, _d, added = self._build_mermaid_items(code, center)
            box = self._ai_items_rect(added)
            if box.right() > limit:
                self._ai_undo_top_silently()
                _n, _a, _d, added = self._build_mermaid_items(code, QPointF(center.x() - (box.right() - limit), center.y()))
            entry = undo.pop()
            undo[idx] = entry
        finally:
            st.discarding = False
        alt.items, alt.undo_entry = added, entry
        alt.request.result_text = code
        self._ai_update_marks(st)
        self._ai_make_alt_bar(st)
        self._refresh_history_actions()
        self._ai_ensure_visible(st.doc.view, self._ai_staged_scene_rect().united(self._ai_items_rect(added)))
        self._ai_place_bar()
        st.doc.view.viewport().update()
        return alt

    def _ai_drop_alt(self, st, status=None):
        """비교 중인 원본을 지운다. 그 기록 칸은 지금 결과 바로 밑이라(다른 편집이 끼면 자동 채택으로 비교가 끝난다)
        기록 목록에서 그 칸째 뺀다 — 지우기 기록을 새로 쌓으면 Ctrl+Z 한 번에 원본이 되살아나 헷갈린다."""
        alt = self._ai_end_alt(st, status or CHOSE_NEW_TEXT)
        if alt is None:
            return
        undo = alt.doc.undo
        for it in alt.items:
            if it.scene() is not None:
                it.scene().removeItem(it)
        if alt.undo_entry in undo:
            undo.remove(alt.undo_entry)
        else:
            self.push_undo_delete([it for it in alt.items])
        self._refresh_history_actions()

    def _ai_restage_flow(self, alt):
        """원본을 다시 임시 결과로(새 결과를 버렸거나 Ctrl+Z로 빠졌을 때) — 원본 기록 칸이 맨 위일 때만."""
        if alt.doc is not self._active_doc or not self._undo or self._undo[-1] is not alt.undo_entry:
            entry = getattr(alt.request, "entry", None)
            if entry is not None and not sip.isdeleted(entry):
                entry.set_status(ACCEPTED_TEXT)
            return None
        m = _MERMAID_HEADER_RE.match(getattr(alt.request, "result_text", ""))
        self._ai_panel.show_flow_code(getattr(alt.request, "result_text", ""))
        return self._ai_stage(alt.items, alt.request, extras=self._ai_flow_extras(m.group(1) if m else "TD"),
                              retry=False)

    def _ai_choose_new(self):
        """비교 막대 「이걸로」(새 결과) — 원본을 지우고 새 결과를 채택."""
        st = self._ai_staged
        if st is None:
            return
        if st.alt is not None:
            self._ai_drop_alt(st)
        self._ai_finish_staging(ACCEPTED_TEXT)

    def _ai_choose_original(self):
        """원본 막대 「이걸로」 — 새 결과를 버리고 원본을 채택."""
        st = self._ai_staged
        if st is None or st.alt is None:
            return
        alt = self._ai_end_alt(st)
        self._ai_drop_staged(st)
        self._ai_finish_staging(CHOSE_ORIGINAL_TEXT)
        entry = getattr(alt.request, "entry", None)
        if entry is not None and not sip.isdeleted(entry):
            entry.set_status(ACCEPTED_TEXT)
        self._ai_panel.show_flow_code(getattr(alt.request, "result_text", ""))

    def _ai_flow_extras(self, direction, side="new"):
        """방향 — 드롭다운 대신 화살표 버튼 4개(2026-10-05 피드백 2차: 한 번에 고르게), 지금 방향만 눌린 상태.
        `side`가 "alt"면 비교 중인 원본 쪽 막대용(버튼이 원본에 걸린다)."""
        token = "TD" if direction.upper() == "TB" else direction.upper()
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        hover = "rgba(128,128,128,40)"
        for i, (label, tok) in enumerate(FLOW_DIRECTIONS):
            b = QToolButton(box)
            b.setIcon(_ai_icon(_DIR_ICONS[tok], _current_icon_color()))
            b.setIconSize(QSize(15, 15))
            b.setCheckable(True)
            b.setChecked(tok == token)
            b.setToolTip(label)
            b.setProperty("dir", tok)
            b.setProperty("aiSide", side)
            b.setProperty("aiIcon", _DIR_ICONS[tok])
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            radius = "border-top-left-radius:6px; border-bottom-left-radius:6px;" if i == 0 else \
                ("border-top-right-radius:6px; border-bottom-right-radius:6px;" if i == len(FLOW_DIRECTIONS) - 1 else "")
            left = "" if i == 0 else "border-left:none;"
            b.setStyleSheet(f"QToolButton {{ border:1px solid rgba(128,128,128,140); {left} {radius} padding:3px 5px; }}"
                            f"QToolButton:hover {{ background:{hover}; }}"
                            f"QToolButton:checked {{ background:rgba(218,119,86,90); border-color:{_ACCENT_CORAL}; }}")
            b.clicked.connect(self._on_flow_direction_clicked)
            lay.addWidget(b)
        follow = _icon_button(None, "이어 고치기", "generate",
                              tip="이 결과를 바탕으로 고칠 점을 말해 다시 만들기(예: 감시장치를 아래로)")
        follow.setProperty("aiSide", side)
        follow.clicked.connect(self._ai_followup_flow)
        return (box, follow)

    def _on_flow_direction_clicked(self):
        st = self._ai_staged
        btn = self.sender()
        if st is None or st.request.kind != "flow" or btn is None:
            return
        on_alt = btn.property("aiSide") == "alt" and st.alt is not None
        code = getattr((st.alt if on_alt else st).request, "result_text", "")
        m = _MERMAID_HEADER_RE.match(code)
        tok = btn.property("dir")
        if not m or m.group(1).upper() == tok or (tok == "TD" and m.group(1).upper() == "TB"):
            btn.setChecked(True)   # 이미 그 방향 — 눌린 상태 유지
            return
        a, b = m.span(1)
        if on_alt:
            self._ai_redraw_alt(code[:a] + tok + code[b:])
        else:
            self._ai_replace_flow(code[:a] + tok + code[b:])

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
        alt = self._ai_end_alt(st)   # 비교 중이면 원본은 남긴 채 새 결과만 다시 그린다
        self._ai_drop_staged(st)
        self._ai_finish_staging("")
        return self._ai_place_flow(req, code, alt=alt)

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

    def _ai_stage(self, items, req, extras=(), retry=True):
        """`items`는 **이미 씬에 넣고 `push_undo_add_many`까지 마친** 결과. 그 한 칸을 기억하고 점선·막대를 띄운다."""
        self._ai_accept_staged()
        items = [it for it in items if it.scene() is self._scene]
        if not items or not self._undo:
            return None
        view = self._view
        st = _StagedResult(doc=self._active_doc, items=items, undo_entry=self._undo[-1], request=req)
        st.bar = _StagingBar(view.viewport(), self._ai_accept_staged, self._ai_retry_staged if retry else None,
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

    def _ai_ensure_visible(self, view=None, rect=None):
        """결과가 카드 사이 빈 띠에 다 안 들어오면 그만큼만 축소해 보여 준다(확대는 하지 않음) — 넓은 흐름도의
        왼쪽이 「도형」 카드 밑에 깔리고 막대의 「채택」까지 가려지던 것(2026-10-05 실제 창). 인자가 없으면 임시 결과."""
        if rect is None:
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
        if st.alt is not None:
            # 비교 중에 자동 채택(다른 편집·새 만들기·저장)되면 둘 다 남긴다 — Ctrl+Z로 지울 수 있으니 잃는 게 없다.
            self._ai_end_alt(st, ACCEPTED_TEXT)
            if status == ACCEPTED_TEXT:
                status = KEPT_BOTH_TEXT
        if st.slots is not None:
            try:
                st.doc.scene.selectionChanged.disconnect(self._ai_on_cand_selection)
            except (TypeError, RuntimeError):
                pass
            if not sip.isdeleted(st.doc.view):
                self._ai_sync_viewport_filter(st.doc.view)
        if st.trace_sent is not None:
            self._ai_region_clear(st)
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
        """자동 채택 길목(새 만들기·저장·다른 편집). 단 심볼 후보 줄은 고른 게 없으면 버린다(사용자 확정)."""
        st = self._ai_staged
        if st is None:
            return
        if st.slots is not None:   # 후보 줄: 고른 것이 있으면 넣고, 없으면 버림
            if st.picked:
                self._ai_commit_candidates(sorted(st.picked))
            else:
                self._ai_discard_candidates(UNPICKED_TEXT)
        else:
            self._ai_finish_staging(ACCEPTED_TEXT)

    def _ai_before_save(self) -> bool:
        """저장 직전(Ctrl+S·다른 이름으로) — 흐름도·베끼기 임시 결과는 채택, 심볼 후보 줄이 떠 있으면 물어본다
        (2026-10-05 피드백 3차: 후보는 다른 편집에도 남기되, 기록에 없는 임시 도형이라 저장 땐 정리). False면 저장 취소."""
        st = self._ai_staged
        if st is None:
            return True
        if st.slots is None:
            self._ai_finish_staging(ACCEPTED_TEXT)
            return True
        box = QMessageBox(self)
        box.setWindowTitle("심볼 후보")
        box.setText("캔버스에 아직 고르지 않은 심볼 후보가 있어요. 어떻게 저장할까요?")
        put = box.addButton(f"고른 {len(st.picked)}개 넣고 저장", QMessageBox.ButtonRole.AcceptRole) if st.picked else None
        drop = box.addButton("후보 버리고 저장", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if put is not None and clicked is put:
            self._ai_commit_candidates(sorted(st.picked))
            return True
        if clicked is drop:
            self._ai_discard_candidates(DISCARDED_TEXT)
            return True
        return False

    def _ai_discard_staged(self):
        """버리기 — 그 한 칸이 맨 위면 되돌리고 다시 실행 목록에서도 뺀다(Ctrl+Y로 살아나지 않게).
        맨 위가 아니면(자동 채택 규칙상 드묾) 지우기를 새 기록으로 남긴다."""
        st = self._ai_staged
        if st is None:
            return
        if st.slots is not None:
            self._ai_discard_candidates(DISCARDED_TEXT)
            return
        alt = self._ai_end_alt(st)
        self._ai_drop_staged(st)
        self._ai_finish_staging(DISCARDED_TEXT)
        if alt is not None:
            self._ai_restage_flow(alt)   # 이어 고친 새 결과를 버림 — 원본이 다시 임시 결과로

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
        if req is not None and req.kind == "trace" and req.image is not None:
            # 베끼기 준비(바닥 사진·모서리)는 결과가 오면서 걷혔다 — 같은 사진·같은 모서리로 되살린 뒤 다시 보낸다.
            self._ai_trace_clear()
            tr = self._ai_trace_setup(req.image)
            quad = getattr(req, "trace_quad", None)
            if quad:
                tr.quad = list(quad)
                self._ai_trace_sync_reset(tr)
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
        if st.slots is not None:                # 후보 줄은 다른 편집에도 남는다(피드백 3차) — 채택·버리기·저장 때 정리
            return
        if st.undo_entry not in undo:           # Ctrl+Z로 결과가 빠졌다
            alt = self._ai_end_alt(st)
            self._ai_finish_staging(UNDONE_TEXT)
            if alt is not None:
                self._ai_restage_flow(alt)      # 이어 고친 결과가 빠짐 — 원본을 다시 임시 결과로
        elif undo[-1] is not st.undo_entry:     # 다른 편집이 기록됐다 → 자동 채택
            self._ai_finish_staging(ACCEPTED_TEXT)

    # ---- 점선·막대 그리기 ------------------------------------------------------------

    def _ai_staged_scene_rect(self) -> QRectF:
        st = self._ai_staged
        rect = QRectF()
        if st.slots is not None:
            for r in st.slots:
                rect = rect.united(r)
            return rect
        for it in st.items:
            if it.scene() is not None:
                rect = rect.united(it.sceneBoundingRect())
        if st.photo_rect is not None:   # 베끼기 — 점선·막대가 사진 자리까지 감싸게(옛 밑깔기 사진이 도형이던 때와 같은 틀)
            rect = rect.united(st.photo_rect)
        return rect

    def _draw_ai_staging(self, view, painter):
        """`core_view.drawForeground`가 부른다(우리 확장 훅)."""
        self._draw_ai_trace_overlay(view, painter)
        st = getattr(self, "_ai_staged", None)
        if st is None or st.doc.view is not view:
            return
        if st.photo is not None and st.photo_shown and st.photo_opacity > 0:
            # 베끼기 결과의 원본 — 도면 *위에* 덮어 그려 100%면 원본만 또렷하게(2026-10-06 2차: 바닥에 깔면 도면 선·격자가
            # 늘 위를 덮어 100%에서도 원본만 볼 수 없었음).
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.setOpacity(st.photo_opacity / 100.0)
            painter.drawPixmap(st.photo_rect, st.photo, QRectF(st.photo.rect()))
            painter.restore()
        if st.trace_sent is not None:
            self._draw_ai_region(view, painter, st)
        rect = self._ai_staged_scene_rect()
        if rect.isNull():
            return
        s = view.transform().m11() or 1.0
        pad = self._AI_STAGE_PAD_PX / s
        rect = rect.adjusted(-pad, -pad, pad, pad)
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if st.slots is not None:
            # 후보 칸마다: 도착=주황 점선, 고름(Ctrl)=주황 실선, 아직=회색 점선
            for i, r in enumerate(st.slots):
                arrived = i < len(st.cands)
                color = QColor(_ACCENT_CORAL) if arrived else QColor(128, 128, 128, 160)
                style = Qt.PenStyle.SolidLine if i in st.picked else Qt.PenStyle.DashLine
                pen = QPen(color, 3.0 if i in st.picked else 2.0, style)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawRoundedRect(r, 6 / s, 6 / s)
                if not arrived:
                    painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "…")
                else:
                    self._ai_draw_check(painter, self._ai_check_scene_rect(r, s), i in st.picked, s)
                    if i in st.base_marks:
                        self._ai_draw_tag(view, painter, r, "바탕")
        else:
            pen = QPen(QColor(_ACCENT_CORAL), 2.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRoundedRect(rect, 6 / s, 6 / s)
            if st.alt is not None:   # 비교 중인 원본 — 회색 점선
                ar = self._ai_items_rect(st.alt.items)
                if not ar.isNull():
                    pen = QPen(QColor(128, 128, 128, 200), 2.0, Qt.PenStyle.DashLine)
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                    painter.drawRoundedRect(ar.adjusted(-pad, -pad, pad, pad), 6 / s, 6 / s)
            self._ai_draw_marks(painter, list(st.marks) + list(st.alt_marks), s)
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
        st.last_vp = self._ai_place_widget(view, st.bar, rect.adjusted(-pad, -pad, pad, pad))
        if st.alt is not None and st.alt_bar is not None and not sip.isdeleted(st.alt_bar):
            ar = self._ai_items_rect(st.alt.items)
            if not ar.isNull():
                self._ai_place_widget(view, st.alt_bar, ar.adjusted(-pad, -pad, pad, pad))
                if st.alt_bar.geometry().intersects(st.bar.geometry()):   # 멀리서 보면 두 막대가 겹친다 — 원본 막대를 한 칸 위로
                    y = st.bar.y() - st.alt_bar.height() - 4
                    st.alt_bar.move(st.alt_bar.x(), y if y >= 4 else st.bar.geometry().bottom() + 4)

    def _ai_place_widget(self, view, bar, scene_rect) -> QRect:
        """막대 위젯을 씬 사각형 위(자리가 없으면 아래)에, 떠 있는 카드 밑에 깔리지 않게 놓는다."""
        vp = view.mapFromScene(scene_rect).boundingRect()
        bar.adjustSize()
        vh = view.viewport().height()
        free = self._ai_free_viewport_rect(view)
        x = max(free.left() + 4, min(vp.left(), free.right() - bar.width() - 4))
        y = vp.top() - bar.height() - self._AI_BAR_GAP_PX
        if y < 4:
            y = min(vp.bottom() + self._AI_BAR_GAP_PX, vh - bar.height() - 4)
        bar.move(int(x), int(max(4, y)))
        bar.raise_()
        return vp

    @staticmethod
    def _ai_draw_marks(painter, items, s):
        """비교 중 상대편과 다른 도형 — 상자는 주황 테두리+옅은 칠, 화살표는 꺾은선을 따라 굵은 주황 띠."""
        fill = QColor(_ACCENT_CORAL)
        fill.setAlpha(45)
        for it in items:
            if it.scene() is None:
                continue
            pts = getattr(it, "_pts", None)
            if pts:
                band = QColor(_ACCENT_CORAL)
                band.setAlpha(120)
                pen = QPen(band, 7.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygonF([it.mapToScene(p) for p in pts]))
            else:
                pen = QPen(QColor(_ACCENT_CORAL), 2.5)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(fill)
                pad = 5 / s
                painter.drawRoundedRect(it.sceneBoundingRect().adjusted(-pad, -pad, pad, pad), 5 / s, 5 / s)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    @staticmethod
    def _ai_draw_tag(view, painter, scene_rect, text):
        """칸 왼쪽 위에 작은 주황 꼬리표(화면 px 고정 크기)."""
        pt = view.mapFromScene(scene_rect.topLeft())
        painter.save()
        painter.resetTransform()
        f = painter.font()
        f.setPixelSize(10)
        f.setBold(True)
        painter.setFont(f)
        fm = painter.fontMetrics()
        box = QRectF(pt.x() + 4, pt.y() + 4, fm.horizontalAdvance(text) + 8, fm.height() + 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_ACCENT_CORAL))
        painter.drawRoundedRect(box, 3, 3)
        painter.setPen(QColor("#1b120d"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()



    # ---- 심볼 후보 줄(4단계) -----------------------------------------------------------
    # 후보는 "결과"가 아니라 "고를 거리" — 고르기 전엔 씬에만 놓고 되돌리기 기록엔 넣지 않는다. 클릭(선택)한 것만
    # 기록 한 칸으로 남기고 나머지는 걷는다. 하나도 안 고른 채 다른 작업·새 만들기·저장을 하면 버린다(사용자 확정).

    def _ai_start_symbol(self, req):
        key = gw.resolve_api_key()
        if not key:
            req.entry.set_status(NO_KEY_TEXT)
            return None
        L = self._SVG_LONG
        n = max(1, int(getattr(req, "count", SYMBOL_COUNT) or SYMBOL_COUNT))
        cur = self._ai_staged
        if cur is not None and cur.slots is not None and getattr(req, "followup_of", None) is cur:
            self._ai_extend_candidates(req, n)
        else:
            target = getattr(req, "replace_target", None)
            if target is not None and target.scene() is self._scene:
                tr = target.mapToScene(QRectF(target.rect())).boundingRect()
                cx, cy = tr.center().x(), tr.bottom() + SYMBOL_GAP + L / 2   # 바꿀 도형 바로 아래 줄
            else:
                cx, cy = req.center.x(), req.center.y()
            row_w = n * L + (n - 1) * SYMBOL_GAP
            spot = self._ai_find_free_center(self._scene, row_w, L, QPointF(cx, cy),
                                             exclude=(target,) if target is not None else ())
            cx, cy = spot.x(), spot.y()
            x0 = cx - row_w / 2
            slots = [QRectF(x0 + i * (L + SYMBOL_GAP), cy - L / 2, L, L) for i in range(n)]
            self._ai_stage_candidates(req, slots)
        base_url = gw.resolve_base_url()
        now = time.monotonic()
        for _ in range(n):
            subject = req.text or getattr(req, "base_text", "")   # 이어 만들기에서 지시를 비우면 원래 대상으로
            worker = _SvgGenWorker(key, subject, req.model, base_url, req.image, self, refs=getattr(req, "refs", None))
            self._ai_jobs[worker] = _AIJob(req, worker, now)
            worker.candidate.connect(self._on_symbol_candidate)
            worker.model_failed.connect(self._on_symbol_failed)
            worker.finished.connect(self._on_ai_job_finished)
            worker.start()
        self._ai_staged.pending = n
        self._ai_tick()
        self._ai_tick_timer.start()
        return self._ai_staged

    def _ai_extend_candidates(self, req, n):
        """이어 만들기(피드백 6차) — 지금 후보 줄은 그대로 두고 그 아래에 새 줄을 붙인다(고를 거리가 늘어남). 앞 요청에서
        아직 안 온 후보는 끊는다(칸은 도착 순서로 채우므로 앞 줄이 다 닫혀야 새 줄 번호가 이어진다). 고름은 풀고, 바탕이 된
        후보엔 「바탕」 꼬리표."""
        st = self._ai_staged
        old = st.request
        for worker, job in list(self._ai_jobs.items()):
            if job.request is old:
                _detach_worker(worker)
                self._ai_jobs.pop(worker, None)
        st.slots = st.slots[:len(st.cands)]
        refs = getattr(req, "refs", None) or []
        st.base_marks = {i for i, c in enumerate(st.cands) if c.svg in refs}
        st.picked = set()
        entry = getattr(old, "entry", None)
        if entry is not None and not sip.isdeleted(entry):
            entry.set_status(KEPT_TEXT)
        L = self._SVG_LONG
        rect = self._ai_staged_scene_rect()
        row_w = n * L + (n - 1) * SYMBOL_GAP
        near = QPointF(rect.center().x(), rect.bottom() + SYMBOL_GAP + 2 + L / 2)
        spot = self._ai_find_free_center(st.doc.scene, row_w, L, near)
        x0 = spot.x() - row_w / 2
        st.row_start = len(st.slots)
        st.slots.extend(QRectF(x0 + i * (L + SYMBOL_GAP), spot.y() - L / 2, L, L) for i in range(n))
        st.request = req
        st.errors = []
        self._ai_update_pick_ui(st)
        self._ai_ensure_visible()
        return st

    def _ai_stage_candidates(self, req, slots):
        self._ai_accept_staged()
        view = self._view
        st = _StagedResult(doc=self._active_doc, items=[], undo_entry=None, request=req, slots=slots)
        st.snap = (len(self._undo), self._undo[-1] if self._undo else None)
        st.all_btn = _icon_button(None, "모두 선택", "ai_check", tip="도착한 후보를 모두 고르기/모두 풀기")
        st.all_btn.clicked.connect(self._ai_toggle_all_checks)
        follow_btn = _icon_button(None, "이어 만들기", "generate",
                                  tip="고른 후보를 바탕으로 고칠 점을 말해 새 후보 받기(예: 두 개를 섞어서)")
        follow_btn.clicked.connect(self._ai_followup_symbol)
        save_btn = _icon_button(None, "내 심볼에 저장", "save",
                                tip="고른 후보(없으면 도착한 후보 전부)를 내 심볼 팔레트에 저장")
        save_btn.clicked.connect(self._ai_save_candidates_to_symbols)
        st.bar = _StagingBar(view.viewport(), self._ai_commit_picked, None,
                             self._ai_discard_staged, extras=(st.all_btn, follow_btn, save_btn), discard_text="모두 버리기")
        st.bar.accept_btn.setToolTip("고른 후보(실선·☑)를 캔버스에 넣기 — 후보를 클릭하거나 드래그로 묶어 고름")
        self._ai_staged = st
        st.doc.scene.selectionChanged.connect(self._ai_on_cand_selection)
        self._ai_sync_viewport_filter(view)
        self._ai_ensure_visible()
        self._ai_place_bar()
        st.bar.show()
        view.viewport().update()
        return st

    def _on_symbol_candidate(self, used_model, svg):
        job = self._ai_job_of_sender()
        st = self._ai_staged
        if job is None or st is None or st.request is not job.request or len(st.cands) >= len(st.slots):
            return   # 이미 버렸거나 골랐다 — 늦게 온 후보는 버린다
        slot = st.slots[len(st.cands)]
        try:
            items = self._svg_text_to_items(svg, self._SVG_LONG, slot.center())
        except Exception as e:  # noqa: BLE001 — 후보 하나가 깨져도 나머지는 계속
            st.errors.append(f"SVG 해석 실패: {e}")
            return
        if not items:
            st.errors.append("빈 SVG")
            return
        for it in items:
            st.doc.scene.addItem(it)
        st.cands.append(_Cand(svg, used_model, items))
        self._ai_tick()
        st.doc.view.viewport().update()

    def _on_symbol_failed(self, model, err):
        job = self._ai_job_of_sender()
        st = self._ai_staged
        if job is not None and st is not None and st.request is job.request:
            st.errors.append(f"{model}: {err}")

    def _ai_symbol_job_done(self, req):
        st = self._ai_staged
        if st is None or st.request is not req or st.slots is None:
            return
        st.pending -= 1
        if st.pending > 0:
            return
        if len(st.cands) == st.row_start:
            why = st.errors[0] if st.errors else "응답 없음"
            if not st.row_start:
                self._ai_finish_staging(f"실패: 후보를 하나도 못 받았어요 — {why}")
                return
            # 이어 만든 줄만 실패 — 앞 줄 후보는 그대로 두고 고를 수 있게(피드백 6차).
            st.slots = st.slots[:st.row_start]
            req.entry.set_status(f"실패: 새 후보를 못 받았어요 — {why} (앞 후보는 그대로)", running=True)
            st.doc.view.viewport().update()
            self._ai_place_bar()
            return
        # 다 왔다 — 못 받은 칸은 줄에서 뺀다(빈 회색 칸이 남지 않게).
        st.slots = st.slots[:len(st.cands)]
        req.entry.set_status(f"후보 {len(st.cands) - st.row_start}개 — 클릭해 넣거나 □로 여러 개 고르세요", running=True)
        st.doc.view.viewport().update()
        self._ai_place_bar()

    def _ai_cand_hits(self, st) -> list:
        sel = set(st.doc.scene.selectedItems())
        return [i for i, c in enumerate(st.cands) if any(it in sel for it in c.items)]

    def _ai_on_cand_selection(self):
        """후보 자체를 클릭(선택)하면 그 하나만 바로 넣는다. 여러 개는 칸 모서리 □로 모아 「N개 채택」.
        (2026-10-05 피드백: 처음엔 Ctrl+클릭으로 모았는데, 이 캔버스는 선택 추가가 Shift라 Ctrl+클릭이 선택을 바꿔 버려
        마지막 하나만 골라졌다 — 실제 창 재현으로 확인. 눈에 보이는 체크 표시로 바꿈.)"""
        st = self._ai_staged
        if st is None or st.slots is None or getattr(st, "clearing_sel", False):
            return
        hits = self._ai_cand_hits(st)
        if not hits:
            return
        # 피드백 3차: 클릭 하나로 나머지가 사라지는 건 가혹 — 클릭은 고름/풀기만(테두리 실선 + ☑), 넣기는 「채택」.
        # 한 개 클릭은 켜고 끄기, 드래그로 여럿 묶으면 그것들을 고름.
        if len(hits) == 1:
            st.picked ^= {hits[0]}
        else:
            st.picked |= set(hits)
        QTimer.singleShot(0, self._ai_clear_cand_selection)   # 선택 신호 도중 씬을 바꾸지 않는다
        self._ai_update_pick_ui(st)

    def _ai_clear_cand_selection(self):
        """후보를 고르고 나면 캔버스 선택(손잡이)은 걷는다 — 고름 표시는 실선·☑가 맡는다."""
        st = self._ai_staged
        if st is None or st.slots is None:
            return
        st.clearing_sel = True
        try:
            for c in st.cands:
                for it in c.items:
                    if it.isSelected():
                        it.setSelected(False)
        finally:
            st.clearing_sel = False

    def _ai_commit_picked(self):
        """막대 「채택」 — □로 고른 후보들."""
        st = self._ai_staged
        if st is None or st.slots is None:
            return
        if not st.picked:
            self.statusBar().showMessage("넣을 후보를 클릭해 고르세요(드래그로 여러 개, 「모두 선택」)", 3000)
            return
        self._ai_commit_candidates(sorted(st.picked))

    def _ai_check_scene_rect(self, slot, s) -> QRectF:
        size, inset = _CHECK_PX / s, _CHECK_INSET_PX / s
        return QRectF(slot.right() - inset - size, slot.top() + inset, size, size)

    def _ai_draw_check(self, painter, r, on, s):
        pen = QPen(QColor(_ACCENT_CORAL), 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(_ACCENT_CORAL) if on else QColor(255, 255, 255, 40))
        painter.drawRoundedRect(r, 3 / s, 3 / s)
        if on:
            mark = QPen(QColor("#1b120d"), 2.0)
            mark.setCosmetic(True)
            painter.setPen(mark)
            painter.drawPolyline(QPolygonF([QPointF(r.left() + r.width() * 0.22, r.top() + r.height() * 0.55),
                                            QPointF(r.left() + r.width() * 0.43, r.top() + r.height() * 0.75),
                                            QPointF(r.left() + r.width() * 0.8, r.top() + r.height() * 0.28)]))
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _ai_toggle_check(self, i):
        st = self._ai_staged
        st.picked ^= {i}
        self._ai_update_pick_ui(st)

    def _ai_toggle_all_checks(self):
        st = self._ai_staged
        if st is None or st.slots is None:
            return
        every = set(range(len(st.cands)))
        st.picked = set() if every and st.picked >= every else every
        self._ai_update_pick_ui(st)

    def _ai_update_pick_ui(self, st):
        n = len(st.picked)
        st.bar.accept_btn.setText(f"{n}개 채택" if n else "채택")
        every = set(range(len(st.cands)))
        all_btn = getattr(st, "all_btn", None)
        if all_btn is not None:
            all_btn.setText("모두 풀기" if every and st.picked >= every else "모두 선택")
        st.doc.view.viewport().update()
        self._ai_place_bar()

    def _ai_sync_viewport_filter(self, view):
        """viewport 이벤트 필터(베끼기 모서리 끌기·후보 □ 누르기)는 한 viewport에 하나만 걸린다 — 한쪽이 끝날 때
        다른 쪽 것까지 떼지 않도록, 그 viewport에 지금 필요한지 보고 걸거나 뗀다."""
        tr = getattr(self, "_ai_trace", None)
        st = getattr(self, "_ai_staged", None)
        need = (tr is not None and tr.doc.view is view) or \
            (st is not None and (st.slots is not None or st.region_picking) and st.doc.view is view)
        vp = view.viewport()
        vp.removeEventFilter(self)
        if need:
            vp.installEventFilter(self)

    def _ai_commit_candidates(self, indices):
        """고른 후보만 남기고 나머지는 걷는다 — 고른 것은 되돌리기 한 칸. 바꾸기 요청이면 고른 첫 후보로 그 도형을
        바꾼다(옛 `_generate_svg_replace`와 같은 규칙: 도형 긴 변에 맞춰, 같은 가운데, 지우기+만들기 한 칸)."""
        st = self._ai_staged
        scene = st.doc.scene
        chosen = [st.cands[i] for i in indices if 0 <= i < len(st.cands)]
        for i, c in enumerate(st.cands):
            if i not in indices:
                for it in c.items:
                    if it.scene() is not None:
                        it.scene().removeItem(it)
        target = getattr(st.request, "replace_target", None)
        replacing = target is not None and target.scene() is scene and chosen
        self._ai_finish_staging(f"✓ 도형을 바꿈" if replacing else f"✓ {len(chosen)}개 넣음")
        scene.clearSelection()
        if replacing:
            c = chosen[0]
            for other in chosen:
                for it in other.items:
                    if it.scene() is not None:
                        it.scene().removeItem(it)
            tr = target.mapToScene(QRectF(target.rect())).boundingRect()
            new_items = self._svg_text_to_items(c.svg, max(tr.width(), tr.height()), tr.center())
            scene.removeItem(target)
            for it in new_items:
                scene.addItem(it)
                it.setSelected(True)
            self._push_entry([("remove", target)] + [("create", it) for it in new_items])
        else:
            items = [it for c in chosen for it in c.items]
            for it in items:
                it.setSelected(True)
            self.push_undo_add_many(items)
        self.set_tool("select")
        self._refresh_properties()

    def _ai_discard_candidates(self, status):
        st = self._ai_staged
        for c in st.cands:
            for it in c.items:
                if it.scene() is not None:
                    it.scene().removeItem(it)
        self._ai_finish_staging(status)

    def _ai_save_candidates_to_symbols(self):
        """후보를 내 심볼에 — 고른 것(Ctrl+클릭)이 있으면 그것만, 없으면 도착한 후보 전부(옛 SVG 창과 같은 저장 경로)."""
        st = self._ai_staged
        if st is None or st.slots is None or not st.cands:
            return 0
        idx = sorted(st.picked) if st.picked else range(len(st.cands))
        entries = [(st.cands[i].svg, st.cands[i].model) for i in idx]
        dlg = _SaveToSymbolsFolderDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return 0
        folder = dlg.chosen_folder()
        if folder and folder not in symbol_library.load_folders():
            symbol_library.create_folder(folder)
        name = getattr(st.request, "base_text", "") or st.request.text   # 이어 만든 줄이면 원래 대상 이름으로
        saved = self._save_svg_candidates_to_symbols(entries, name, folder)
        self.statusBar().showMessage(f"내 심볼에 {saved}개 저장", 4000)
        return saved

    def _ai_open_for_replace(self, item):
        """우클릭 「AI로 바꾸기…」 — 패널을 심볼로 열고, 다음 「만들기」의 후보를 그 도형 아래 줄에 놓는다."""
        self._ai_replace_target = item
        self._set_ai_panel_visible(True, kind="symbol")
        self._ai_panel.show_notice("고른 도형을 바꿀 심볼을 적고 「만들기」 — 후보를 클릭하면 그 자리가 바뀌어요")


    # ---- 그대로 베끼기(5단계) -----------------------------------------------------------
    # 사진을 붙이면 캔버스 바닥에 흐리게 깔고(도형 아님 — `core_view.drawBackground` 훅) 모서리 4점을 띄운다. 점은 viewport
    # 이벤트 필터로 끈다(캔버스 코어의 마우스 처리를 건드리지 않음). 「만들기」는 그 4점으로 사진을 펴서(`rectify`) 구역별
    # 동시 생성(`_PhotoOpsWorker`)에 보내고, 2~3분 동안 캔버스는 계속 쓸 수 있다. 결과는 사진 자리 가운데에 임시 결과로.

    def _on_ai_trace_photo(self, img):
        tr = self._ai_trace
        if tr is not None and img is tr.original:
            return   # 같은 사진(베끼기 탭을 다시 누름 등) — 맞춰 둔 모서리를 지우지 않는다
        if tr is not None and tr.running:
            if img is not None and img is not tr.original:
                self._ai_panel.show_notice(TRACE_BUSY_TEXT)
            return
        self._ai_trace_clear()
        if img is not None:
            self._ai_trace_setup(img)

    def _ai_trace_setup(self, img):
        from easycad.ai.photo_to_ops import fit_for_ai
        fitted = fit_for_ai(img)
        faint = fitted.convert("RGBA")
        faint.putalpha(self._PHOTO_UNDERLAY_ALPHA)
        w, h = fitted.size
        view = self._view
        c = self._ai_find_free_center(self._scene, w * _PHOTO_SCALE, h * _PHOTO_SCALE,
                                      view.mapToScene(view.viewport().rect().center()))
        rect = QRectF(c.x() - w * _PHOTO_SCALE / 2, c.y() - h * _PHOTO_SCALE / 2, w * _PHOTO_SCALE, h * _PHOTO_SCALE)
        tr = _TraceSetup(doc=self._active_doc, original=img, fitted=fitted, pixmap=_pil_to_pixmap(faint), rect=rect,
                         quad=[(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))])
        bar = QFrame(view.viewport())
        bar.setObjectName("aiStagingBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setStyleSheet("QFrame#aiStagingBar { background:palette(window); border:1px solid rgba(128,128,128,140);"
                          " border-radius:8px; }")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(5)
        tr.hint = QLabel(TRACE_HINT, bar)
        tr.hint.setStyleSheet(_TRACE_HINT_QSS)
        lay.addWidget(tr.hint)
        # 「만들기」를 사진 위에도(피드백 2026-10-06: 패널 입력칸에만 있어 어디를 눌러야 할지 헷갈림) — 패널 버튼과 같은 길.
        tr.make_btn = _icon_button(bar, "만들기", "generate", coral=True, tip="이 모서리로 베끼기 시작(패널 「만들기」와 같음)")
        tr.make_btn.clicked.connect(self._ai_panel.request_make)
        lay.addWidget(tr.make_btn)
        tr.rotate_btn = _icon_button(bar, "90° 돌리기", "ai_rotate", tip="사진을 시계 방향으로 90° 돌림(모서리는 처음 자리로)")
        tr.rotate_btn.clicked.connect(self._ai_trace_rotate)
        lay.addWidget(tr.rotate_btn)
        tr.reset_btn = _icon_button(bar, "모서리 초기화", "ai_corners")
        tr.reset_btn.clicked.connect(self._ai_trace_reset_corners)
        tr.reset_btn.setVisible(False)   # 모서리를 움직였을 때만(2026-10-06 2차)
        lay.addWidget(tr.reset_btn)
        tr.remove_btn = _icon_button(bar, "취소", "ai_close", tip="사진을 걷고 베끼기를 그만둠")
        tr.remove_btn.clicked.connect(self._ai_panel.clear_attached_image)
        lay.addWidget(tr.remove_btn)
        tr.cancel_btn = _icon_button(bar, "취소", "ai_stop", tip="남은 구역 생성을 멈춤(지금 도는 호출은 끝까지 감)")
        tr.cancel_btn.clicked.connect(self._ai_trace_cancel)
        tr.cancel_btn.setVisible(False)
        lay.addWidget(tr.cancel_btn)
        tr.bar = bar
        self._ai_trace = tr
        self._ai_sync_viewport_filter(view)
        self._ai_ensure_visible(view, rect)
        tr.last_vp = self._ai_place_widget(view, bar, rect)
        bar.show()
        view.viewport().update()
        return tr

    def _ai_trace_clear(self):
        tr = self._ai_trace
        if tr is None:
            return
        self._ai_trace = None
        view = getattr(tr.doc, "view", None)
        if view is not None and not sip.isdeleted(view):
            self._ai_sync_viewport_filter(view)
            view.viewport().update()
        if tr.bar is not None and not sip.isdeleted(tr.bar):
            tr.bar.hide()
            tr.bar.deleteLater()

    def _ai_trace_set_running(self, on: bool):
        tr = self._ai_trace
        tr.running = on
        tr.drag = None
        tr.hint.setStyleSheet(_TRACE_HINT_RUNNING_QSS if on else _TRACE_HINT_QSS)
        tr.make_btn.setVisible(not on)
        tr.rotate_btn.setVisible(not on)
        tr.reset_btn.setVisible(not on and self._ai_trace_corners_moved(tr))
        tr.remove_btn.setVisible(not on)
        tr.cancel_btn.setVisible(on)
        tr.cancel_btn.setEnabled(on)
        if not on:
            tr.hint.setText(TRACE_HINT)
        tr.doc.view.viewport().update()
        self._ai_place_widget(tr.doc.view, tr.bar, tr.rect)

    def _ai_trace_reset_corners(self):
        tr = self._ai_trace
        if tr is None or tr.running:
            return
        w, h = tr.fitted.size
        tr.quad = [(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))]
        self._ai_trace_sync_reset(tr)
        tr.doc.view.viewport().update()

    @staticmethod
    def _ai_trace_corners_moved(tr) -> bool:
        w, h = tr.fitted.size
        return tr.quad != [(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))]

    def _ai_trace_sync_reset(self, tr):
        """「모서리 초기화」는 모서리를 움직였을 때만 보인다 — 바뀌면 막대 크기·자리를 다시 잡는다."""
        want = not tr.running and self._ai_trace_corners_moved(tr)
        if tr.reset_btn.isVisibleTo(tr.bar) != want:
            tr.reset_btn.setVisible(want)
            self._ai_place_widget(tr.doc.view, tr.bar, tr.rect)

    def _ai_trace_rotate(self):
        """90° 돌리기 — 패널에 붙인 사진 자체를 돌려 다시 붙인다(그래야 「다시」·기록도 돌린 사진을 쓴다).
        `trace_photo_changed`가 새 사진으로 준비를 다시 깔아 모서리는 처음 자리로 돌아간다."""
        from PIL import Image
        tr = self._ai_trace
        p = self._ai_panel
        if tr is None or tr.running or p._attached_image is None:
            return
        p._set_attached_image(p._attached_image.transpose(Image.Transpose.ROTATE_270), p._attached_image_name)

    def _ai_trace_corner_scene(self, tr, i) -> QPointF:
        x, y = tr.quad[i]
        return QPointF(tr.rect.left() + x * _PHOTO_SCALE, tr.rect.top() + y * _PHOTO_SCALE)

    def _draw_ai_trace_photo(self, view, painter):
        """`core_view.drawBackground` 훅 — 준비·만드는 중인 사진을 바닥에 흐리게."""
        tr = getattr(self, "_ai_trace", None)
        if tr is None or tr.doc.view is not view:
            return
        painter.drawPixmap(tr.rect, tr.pixmap, QRectF(tr.pixmap.rect()))

    def _draw_ai_trace_overlay(self, view, painter):
        tr = getattr(self, "_ai_trace", None)
        if tr is None or tr.doc.view is not view:
            return
        s = view.transform().m11() or 1.0
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if tr.running:
            pen = QPen(QColor(_ACCENT_CORAL), 2.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(tr.rect)
        else:
            pts = [self._ai_trace_corner_scene(tr, i) for i in range(4)]
            pen = QPen(QColor(_ACCENT_CORAL), 1.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawPolygon(QPolygonF(pts))
            painter.setBrush(QColor(_ACCENT_CORAL))
            for q in pts:
                painter.drawEllipse(q, 6.0 / s, 6.0 / s)
        painter.restore()
        vp = view.mapFromScene(tr.rect).boundingRect()
        if vp != tr.last_vp:
            tr.last_vp = vp
            QTimer.singleShot(0, self._ai_trace_place_bar)

    def _ai_trace_place_bar(self):
        tr = self._ai_trace
        if tr is not None and tr.bar is not None and not sip.isdeleted(tr.bar):
            self._ai_place_widget(tr.doc.view, tr.bar, tr.rect)

    def eventFilter(self, obj, event):
        """베끼기 모서리 점 끌기·후보 칸 □ 누르기 — 그 탭 캔버스의 viewport에만 건다. 점·□ 위 누름이 아니면 캔버스로 넘긴다."""
        st = getattr(self, "_ai_staged", None)
        if st is not None and st.region_picking and obj is st.doc.view.viewport():
            if self._ai_region_event(st, event):
                return True
        if st is not None and st.slots is not None and obj is st.doc.view.viewport() \
                and event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            view = st.doc.view
            s = view.transform().m11() or 1.0
            pos = event.position()
            for i in range(len(st.cands)):
                box = view.mapFromScene(self._ai_check_scene_rect(st.slots[i], s)).boundingRect().adjusted(-3, -3, 3, 3)
                if box.contains(pos.toPoint()):
                    self._ai_toggle_check(i)
                    return True
            # 피드백 4차: 칸 안 빈 곳(테두리와 도형 사이)을 눌러도 고름/풀기 — 도형 선만 잡히던 것.
            for i in range(len(st.cands)):
                if view.mapFromScene(st.slots[i]).boundingRect().contains(pos.toPoint()):
                    self._ai_toggle_check(i)
                    return True
        tr = getattr(self, "_ai_trace", None)
        if tr is not None and not tr.running and obj is tr.doc.view.viewport():
            et = event.type()
            view = tr.doc.view
            if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                pos = event.position()
                best, dist = None, None
                for i in range(4):
                    d = (QPointF(view.mapFromScene(self._ai_trace_corner_scene(tr, i))) - pos).manhattanLength()
                    if dist is None or d < dist:
                        best, dist = i, d
                if dist is not None and dist <= _TRACE_CORNER_HIT_PX:
                    tr.drag = best
                    return True
            elif et == QEvent.Type.MouseMove and tr.drag is not None:
                sp = view.mapToScene(event.position().toPoint())
                w, h = tr.fitted.size
                x = min(max((sp.x() - tr.rect.left()) / _PHOTO_SCALE, 0.0), float(w))
                y = min(max((sp.y() - tr.rect.top()) / _PHOTO_SCALE, 0.0), float(h))
                tr.quad[tr.drag] = (x, y)
                view.viewport().update()
                return True
            elif et == QEvent.Type.MouseButtonRelease and tr.drag is not None:
                tr.drag = None
                self._ai_trace_sync_reset(tr)
                return True
        return super().eventFilter(obj, event)

    def _ai_start_trace(self, req):
        tr = self._ai_trace
        if tr is None or tr.doc is not self._active_doc:
            req.entry.set_status(TRACE_NO_PHOTO_TEXT)
            return None
        if tr.running:
            req.entry.set_status(TRACE_BUSY_TEXT)
            return None
        key = gw.resolve_api_key()
        if not key:
            req.entry.set_status(NO_KEY_TEXT)
            return None
        from easycad.ai.photo_to_ops import fit_for_ai, rectify
        k = tr.original.size[0] / tr.fitted.size[0]
        try:
            flat = rectify(tr.original, [(x * k, y * k) for x, y in tr.quad])
            sent = fit_for_ai(flat)
            tr.view_img = fit_for_ai(flat, _TRACE_VIEW_MAX_SIDE)
        except ValueError as e:
            req.entry.set_status(f"모서리로 사진을 펼 수 없어요: {e}")
            return None
        worker = _PhotoOpsWorker(key, gw.resolve_base_url(), sent, req.model, self)
        self._ai_jobs[worker] = _AIJob(req, worker, time.monotonic())
        worker.progressed.connect(self._on_trace_progress)
        worker.succeeded.connect(self._on_trace_done)
        worker.failed.connect(self._on_trace_failed)
        worker.cancelled.connect(self._on_trace_cancelled)
        worker.finished.connect(self._on_ai_job_finished)
        tr.req, tr.worker, tr.sent = req, worker, sent
        req.trace_quad = list(tr.quad)   # 결과 막대 「다시」가 같은 모서리로 되살리게
        self._ai_trace_set_running(True)
        worker.start()
        self._ai_tick()
        self._ai_tick_timer.start()
        return worker

    def _ai_trace_cancel(self):
        tr = self._ai_trace
        if tr is None or not tr.running or tr.worker is None:
            return
        tr.worker.request_cancel()
        tr.cancel_btn.setEnabled(False)
        tr.hint.setText(CANCELLING_TEXT)
        tr.req.entry.set_status(CANCELLING_TEXT, running=True)

    def _on_trace_progress(self, i, n, _text):
        job = self._ai_job_of_sender()
        if job is not None:
            job.progress = (i, n)
            self._ai_tick()

    def _ai_trace_of_sender(self):
        job = self._ai_job_of_sender()
        tr = self._ai_trace
        if job is None or tr is None or tr.req is not job.request:
            return None, job
        return tr, job

    def _on_trace_done(self, spec, log):
        tr, job = self._ai_trace_of_sender()
        if tr is None:
            return
        req = job.request
        if not self._ai_goto_request_doc(req):
            self._ai_trace_clear()
            return
        added, _skipped = self._build_photo_drawing(spec, tr.sent, underlay=False, center=tr.rect.center())
        self._ai_trace_clear()
        self._ai_panel.clear_attached_image()
        # 피드백(2026-10-06): 사진은 도면에 넣지 않고 고르는 동안만 겹쳐 본다 — 켜고 끄기·진하기로 대조(채택하면 사라짐).
        W, H = tr.sent.size
        c = tr.rect.center()
        show = QCheckBox("원본 보기")
        show.setChecked(True)
        show.setToolTip("원본 사진을 결과에 겹쳐 보기(비교용 — 채택하면 도면에는 안 남음)")
        # 도면 ↔ 원본 막대(2026-10-06 2차): 0=도면만, 100=원본만. 양 끝 글씨로 무엇을 조절하는지 보이게.
        mix = QWidget()
        mix_lay = QHBoxLayout(mix)
        mix_lay.setContentsMargins(0, 0, 0, 0)
        mix_lay.setSpacing(4)
        opacity = QSlider(Qt.Orientation.Horizontal, mix)
        opacity.setRange(0, 100)
        opacity.setValue(TRACE_PHOTO_OPACITY)
        opacity.setFixedWidth(90)
        opacity.setToolTip("왼쪽 끝 = 도면만 · 오른쪽 끝 = 원본만")
        mix_lay.addWidget(QLabel("도면", mix))
        mix_lay.addWidget(opacity)
        mix_lay.addWidget(QLabel("원본", mix))
        show.toggled.connect(self._on_trace_photo_shown)
        show.toggled.connect(mix.setEnabled)
        opacity.valueChanged.connect(self._on_trace_photo_opacity)
        region_btn = _icon_button(None, "부분 다시", "ai_region",
                                  tip="틀린 곳만 상자로 골라 그 부분만 다시 그림(전체를 다시 만들지 않음)")
        region_btn.setCheckable(True)
        region_btn.clicked.connect(self._ai_region_toggle_pick)
        st = self._ai_stage(added, req, extras=(show, mix, region_btn))
        if st is not None:
            st.trace_sent = tr.sent
            st.trace_ops = [op for op in spec.get("ops", []) if isinstance(op, dict)]
            st.region_btn = region_btn
            st.photo = _pil_to_pixmap(tr.view_img if tr.view_img is not None else tr.sent)
            st.photo_rect = QRectF(c.x() - W * _PHOTO_SCALE / 2, c.y() - H * _PHOTO_SCALE / 2, W * _PHOTO_SCALE, H * _PHOTO_SCALE)
            st.doc.view.viewport().update()
        bad = sum(1 for e in log if "error" in e)
        if st is not None and bad:
            req.entry.set_status(f"{STAGED_TEXT} · {len(log)}구역 중 {bad}곳을 못 읽어 비어 있어요", running=True)

    def _on_trace_photo_shown(self, on: bool):
        st = self._ai_staged
        if st is not None and st.photo is not None:
            st.photo_shown = on
            st.doc.view.viewport().update()

    def _on_trace_photo_opacity(self, value: int):
        st = self._ai_staged
        if st is not None and st.photo is not None:
            st.photo_opacity = value
            st.doc.view.viewport().update()

    def _on_trace_failed(self, err):
        tr, job = self._ai_trace_of_sender()
        if job is not None:
            job.request.entry.set_status(f"실패: {err}")
        if tr is not None:
            self._ai_trace_set_running(False)

    def _on_trace_cancelled(self):
        tr, job = self._ai_trace_of_sender()
        if job is not None:
            job.request.entry.set_status(CANCELLED_TEXT)
        if tr is not None:
            self._ai_trace_set_running(False)

    # ---- 부분 다시 베끼기(2026-10-06) ------------------------------------------------------------
    # 결과 막대 「부분 다시」 → 사진 위에 상자를 끌어 고름 → 상자 위 작은 막대 「이 부분 다시 그리기」(패널 입력칸의 글은
    # 이어 만들기처럼 "틀린 점"으로 같이 보냄) → 그 부분만 한 번 호출 → 상자 안 도형을 새 것으로 바꿔 같은 결과(되돌리기
    # 한 칸)에 합친다. 상자 안/밖은 도형 가운데로 가른다(새 도형도 같은 기준이라 겹쳐 남지 않음).

    def _ai_region_scene_rect(self, st, region) -> QRectF:
        o = st.photo_rect.topLeft()
        x1, y1, x2, y2 = region
        return QRectF(o.x() + x1 * _PHOTO_SCALE, o.y() + y1 * _PHOTO_SCALE,
                      (x2 - x1) * _PHOTO_SCALE, (y2 - y1) * _PHOTO_SCALE)

    def _ai_region_toggle_pick(self, checked: bool = False):
        st = self._ai_staged
        if st is None or st.trace_sent is None:
            return
        if st.region_worker is not None:      # 다시 그리는 중엔 새로 고르지 않는다
            st.region_btn.setChecked(False)
            return
        self._ai_region_clear(st)
        if checked:
            st.region_picking = True
            st.region_btn.setChecked(True)
            st.doc.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self._ai_panel.show_notice(REGION_PICK_TEXT)
        self._ai_sync_viewport_filter(st.doc.view)
        st.doc.view.viewport().update()

    def _ai_region_event(self, st, event) -> bool:
        view = st.doc.view
        et = event.type()
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            p = view.mapToScene(event.position().toPoint())
            st.region_drag = (p, p)
            return True
        if et == QEvent.Type.MouseMove and st.region_drag is not None:
            st.region_drag = (st.region_drag[0], view.mapToScene(event.position().toPoint()))
            view.viewport().update()
            return True
        if et == QEvent.Type.MouseButtonRelease and st.region_drag is not None:
            a, b = st.region_drag
            st.region_drag = None
            r = QRectF(a, b).normalized().intersected(st.photo_rect)
            s = view.transform().m11() or 1.0
            if r.width() * s < _REGION_MIN_PX or r.height() * s < _REGION_MIN_PX:
                view.viewport().update()
                return True   # 클릭만 함 — 계속 고르는 중
            o = st.photo_rect.topLeft()
            self._ai_region_set(st, ((r.left() - o.x()) / _PHOTO_SCALE, (r.top() - o.y()) / _PHOTO_SCALE,
                                     (r.right() - o.x()) / _PHOTO_SCALE, (r.bottom() - o.y()) / _PHOTO_SCALE))
            return True
        # 왼쪽 누름만 고르기 몫 — 휠·가운데·오른쪽 끌기 이동과 휠 확대는 캔버스로(2026-10-06 실사용: 다 막혀 있었음).
        return et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick) \
            and event.button() == Qt.MouseButton.LeftButton

    def _ai_region_set(self, st, region):
        """부분을 골랐다 — 고르기를 끝내고, 상자 위 막대를 띄우고, 패널을 이어 만들기(부분)로."""
        st.region_picking = False
        st.region = tuple(region)
        st.doc.view.viewport().unsetCursor()
        st.region_btn.setChecked(False)
        self._ai_sync_viewport_filter(st.doc.view)
        bar = QFrame(st.doc.view.viewport())
        bar.setObjectName("aiStagingBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setStyleSheet("QFrame#aiStagingBar { background:palette(window); border:1px solid rgba(128,128,128,140);"
                          " border-radius:8px; }")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(5)
        st.region_label = QLabel(REGION_HINT, bar)
        st.region_label.setStyleSheet(_TRACE_HINT_QSS)
        lay.addWidget(st.region_label)
        st.region_make_btn = _icon_button(bar, "이 부분 다시 그리기", "generate", coral=True,
                                          tip="고른 부분만 다시 그려 바꿈(입력칸의 글도 같이 보냄)")
        st.region_make_btn.clicked.connect(self._ai_region_make)
        lay.addWidget(st.region_make_btn)
        cancel = _icon_button(bar, "취소", "ai_close")
        cancel.clicked.connect(self._ai_region_cancel)
        lay.addWidget(cancel)
        st.region_bar = bar
        st.region_last_vp = self._ai_place_widget(st.doc.view, bar, self._ai_region_scene_rect(st, st.region))
        bar.show()
        self._ai_region_followup(st)
        st.doc.view.viewport().update()

    def _ai_region_followup(self, st):
        x1, y1, x2, y2 = (int(round(v)) for v in st.region)
        thumb = _pil_to_pixmap(st.trace_sent.crop((x1, y1, max(x2, x1 + 1), max(y2, y1 + 1))))
        self._ai_panel.set_followup("trace", "고른 부분", [thumb], base=st)

    def _ai_region_make(self):
        """상자 위 「이 부분 다시 그리기」 — 패널 「만들기」와 같은 길(입력칸 글을 틀린 점으로)."""
        st = self._ai_staged
        if st is None or st.region is None or st.region_worker is not None:
            return
        fu = self._ai_panel.followup()
        if fu is None or fu.get("base") is not st:   # 패널에서 이어 만들기를 ✕로 닫았으면 다시 건다
            self._ai_region_followup(st)
        self._ai_panel.request_make()

    def _ai_region_cancel(self):
        """상자 막대 「취소」 — 고른 부분을 걷는다. 다시 그리는 중이면 그 호출 결과를 버린다(호출 자체는 못 끊음)."""
        st = self._ai_staged
        if st is not None:
            self._ai_region_clear(st, CANCELLED_TEXT)

    def _ai_region_clear(self, st, status=REGION_LOST_TEXT):
        """고르기·고른 부분·상자 막대를 걷는다(도는 호출이 있으면 떼어 결과를 버리고 기록 칸에 `status`)."""
        if st.region_worker is not None:
            job = self._ai_jobs.pop(st.region_worker, None)
            _detach_worker(st.region_worker)
            st.region_worker = None
            if not self._ai_jobs:
                self._ai_tick_timer.stop()
            if job is not None and job.request.entry is not None and not sip.isdeleted(job.request.entry):
                job.request.entry.set_status(status)
        was_picking = st.region_picking
        st.region_picking = False
        st.region_drag = None
        st.region = None
        if st.region_btn is not None and not sip.isdeleted(st.region_btn):
            st.region_btn.setChecked(False)
        if st.region_bar is not None and not sip.isdeleted(st.region_bar):
            st.region_bar.hide()
            st.region_bar.deleteLater()
        st.region_bar = st.region_label = st.region_make_btn = None
        fu = self._ai_panel.followup()
        if fu is not None and fu.get("base") is st:
            self._ai_panel.clear_followup()
        view = getattr(st.doc, "view", None)
        if view is not None and not sip.isdeleted(view):
            if was_picking:
                view.viewport().unsetCursor()
            self._ai_sync_viewport_filter(view)
            view.viewport().update()

    def _ai_start_trace_region(self, req):
        st = req.followup_of
        if st.region is None:
            req.entry.set_status("다시 그릴 부분을 먼저 상자로 골라 주세요")
            return None
        from easycad.ai.photo_to_ops import ops_in_region
        prev = ops_in_region(st.trace_ops or [], st.region)
        worker = self._ai_start_job(req, _TraceRegionWorker,
                                    (gw.resolve_base_url(), st.trace_sent, st.region, req.text, prev, req.model),
                                    self._on_trace_region_done)
        if worker is None:
            return None
        worker.failed.connect(self._on_trace_region_failed)
        st.region_worker = worker
        st.region_make_btn.setVisible(False)
        st.region_label.setStyleSheet(_TRACE_HINT_RUNNING_QSS)
        self._ai_tick()
        self._ai_place_widget(st.doc.view, st.region_bar, self._ai_region_scene_rect(st, st.region))
        return worker

    def _on_trace_region_done(self, spec, _log):
        job = self._ai_job_of_sender()
        st = self._ai_staged
        if job is None:
            return
        if st is None or st.region_worker is not self.sender():
            job.request.entry.set_status(REGION_LOST_TEXT)
            return
        st.region_worker = None
        added = self._ai_region_replace(st, spec)
        job.request.entry.set_status(f"{REGION_DONE_TEXT}({len(added)}개)")
        self._ai_region_clear(st)

    def _on_trace_region_failed(self, _err):
        st = self._ai_staged
        if st is not None and st.region_worker is self.sender():
            st.region_worker = None
            st.region_make_btn.setVisible(True)
            st.region_label.setStyleSheet(_TRACE_HINT_QSS)
            st.region_label.setText(REGION_HINT)
            self._ai_place_widget(st.doc.view, st.region_bar, self._ai_region_scene_rect(st, st.region))

    def _ai_region_replace(self, st, spec) -> list:
        """상자 안(도형 가운데 기준) 옛 도형을 걷고 새 도형을 넣어, 같은 결과의 되돌리기 한 칸에 합친다."""
        from easycad.ai.photo_to_ops import op_center
        R = self._ai_region_scene_rect(st, st.region)
        scene = st.doc.scene
        o = st.photo_rect.topLeft()
        sk, _skipped = ops_to_sketch(spec, dark=getattr(self, "_dark", True), offset=(o.x(), o.y()))
        z0 = max((it.zValue() for it in st.items if it.scene() is not None), default=0.0) + 1.0
        for d in sk._items:
            d["z"] = d["z"] + z0
        new = insert_items(scene, sk._items)
        added = []
        for it in new:
            if R.contains(it.sceneBoundingRect().center()):
                added.append(it)
            else:
                scene.removeItem(it)   # 대표점은 안이었지만 그린 모양이 밖으로 — 바깥은 그대로 두는 게 약속
        gone = [it for it in st.items if it.scene() is not None and R.contains(it.sceneBoundingRect().center())]
        for it in gone:
            scene.removeItem(it)
        gone_ids = {id(it) for it in gone}
        st.items = [it for it in st.items if id(it) not in gone_ids] + added
        st.undo_entry.ops = [op for op in st.undo_entry.ops if id(op[1]) not in gone_ids] + \
            [("create", it) for it in added]
        x1, y1, x2, y2 = st.region
        keep = []
        for op in st.trace_ops or []:
            c = op_center(op)
            if c is None or not (x1 <= c[0] <= x2 and y1 <= c[1] <= y2):
                keep.append(op)
        st.trace_ops = keep + list(spec.get("ops", []))
        scene.clearSelection()
        st.doc.view.viewport().update()
        self._refresh_minimap()   # 되돌리기 기록을 안 거쳐 미니맵이 옛 모양으로 남던 것(실제 창)
        return added

    def _draw_ai_region(self, view, painter, st):
        """고르는 중인 상자·고른 부분 — 주황 실선(다시 그리는 중엔 점선), 상자 막대 자리도 맞춘다."""
        r = None
        if st.region_drag is not None:
            r = QRectF(st.region_drag[0], st.region_drag[1]).normalized()
        elif st.region is not None:
            r = self._ai_region_scene_rect(st, st.region)
        if r is None:
            return
        painter.save()
        fill = QColor(_ACCENT_CORAL)
        fill.setAlpha(35)
        painter.setBrush(fill)
        style = Qt.PenStyle.DashLine if st.region_worker is not None else Qt.PenStyle.SolidLine
        pen = QPen(QColor(_ACCENT_CORAL), 2.5, style)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(r)
        painter.restore()
        if st.region_bar is not None and st.region is not None:
            vp = view.mapFromScene(r).boundingRect()
            if vp != st.region_last_vp:
                st.region_last_vp = vp
                QTimer.singleShot(0, self._ai_region_place_bar)

    def _ai_region_place_bar(self):
        st = self._ai_staged
        if st is not None and st.region_bar is not None and not sip.isdeleted(st.region_bar) and st.region is not None:
            self._ai_place_widget(st.doc.view, st.region_bar, self._ai_region_scene_rect(st, st.region))

    # ---- 빈 자리·기록 지우기(2026-10-05 피드백 2차) -------------------------------------------

    @staticmethod
    def _ai_items_rect(items) -> QRectF:
        r = QRectF()
        for it in items:
            if it.scene() is not None:
                r = r.united(it.sceneBoundingRect())
        return r

    def _ai_find_free_center(self, scene, w, h, near, exclude=()) -> QPointF:
        """w×h를 기존 도형과 `_FREE_MARGIN` 이상 띄워 놓을 수 있는, `near`에서 가장 가까운 가운데점.
        가운데부터 바깥으로(가로 반칸·세로 반칸 격자) 고리를 넓히며 씬 공간 색인(`scene.items(rect)`)으로 빈지 본다.
        못 찾으면 도면 전체의 오른쪽 바깥(사용자 결정: 겹치지 않게)."""
        ex = {e for e in exclude if e is not None}
        m = _FREE_MARGIN

        def free(cx, cy):
            r = QRectF(cx - w / 2 - m, cy - h / 2 - m, w + 2 * m, h + 2 * m)
            for it in scene.items(r):
                top = it.topLevelItem()
                if top in ex or it in ex or not top.isVisible():
                    continue
                return False
            return True
        if free(near.x(), near.y()):
            return QPointF(near)
        sx, sy = w / 2 + m, h / 2 + m
        cands = []
        for i in range(-_FREE_RINGS, _FREE_RINGS + 1):
            for j in range(-_FREE_RINGS, _FREE_RINGS + 1):
                if i or j:
                    cands.append((math.hypot(i * sx, j * sy), i, j))
        cands.sort()
        for _d, i, j in cands:
            cx, cy = near.x() + i * sx, near.y() + j * sy
            if free(cx, cy):
                return QPointF(cx, cy)
        tops = [it for it in scene.items() if it.parentItem() is None and it not in ex]
        allr = self._ai_items_rect(tops)
        return QPointF(allr.right() + m + w / 2, near.y()) if not allr.isNull() else QPointF(near)

    def _ai_undo_top_silently(self):
        """방금 쌓은 되돌리기 한 칸을 되돌리고 다시 실행 목록에서도 뺀다(자리 옮겨 다시 그릴 때)."""
        if not self._undo:
            return
        entry = self._undo[-1]
        self.undo()
        if self._redo and self._redo[-1] is entry:
            self._redo.pop()
            self._refresh_history_actions()

    def _on_ai_entry_removed(self, req):
        """기록 칸을 지움 — 그 요청이 아직 만드는 중이면 취소한다. 후보 줄도 함께 버린다(결과가 이미 놓였으면 그대로)."""
        for worker, job in list(self._ai_jobs.items()):
            if job.request is not req:
                continue
            cancel = getattr(worker, "request_cancel", None)
            if cancel is not None:
                cancel()   # 베끼기 — 지금 호출이 끝나면 멈추고 준비 단계로(취소 신호)
            else:
                _detach_worker(worker)   # 흐름도·심볼 — 결과를 버린다
                self._ai_jobs.pop(worker, None)
        if not self._ai_jobs:
            self._ai_tick_timer.stop()
        st = self._ai_staged
        if st is not None and st.request is req and st.slots is not None:
            self._ai_discard_candidates(DISCARDED_TEXT)

    _AI_BAR_QSS = ("QFrame#aiStagingBar { background:palette(window); border:1px solid rgba(128,128,128,140);"
                   " border-radius:8px; }")

    def _ai_refresh_theme(self):
        """테마 전환 — 떠 있는 결과·준비 막대도 스타일·아이콘을 다시 칠한다(QSS 걸린 위젯은 팔레트만 바뀌어선
        처음 색에 남는 함정 — 라이트로 바꿔도 막대만 어둡게 남던 것, 2026-10-05 실제 창)."""
        bars = []
        st = getattr(self, "_ai_staged", None)
        if st is not None and st.bar is not None:
            bars.append(st.bar)
        if st is not None and st.alt_bar is not None:
            bars.append(st.alt_bar)
        tr = getattr(self, "_ai_trace", None)
        if tr is not None and tr.bar is not None:
            bars.append(tr.bar)
        for bar in bars:
            if sip.isdeleted(bar):
                continue
            bar.setStyleSheet("")
            bar.setStyleSheet(self._AI_BAR_QSS)
            for b in bar.findChildren(QToolButton):
                name = b.property("aiIcon")
                if name:
                    b.setIcon(_ai_icon(name, "#1b120d" if b.property("aiCoral") else _current_icon_color()))
                ss = b.styleSheet()
                if ss:
                    b.setStyleSheet("")
                    b.setStyleSheet(ss)
            for v in (getattr(st, "doc", None), getattr(tr, "doc", None)):
                if v is not None and not sip.isdeleted(v.view):
                    v.view.viewport().update()

    # ---- 이어 만들기(2026-10-05 피드백 4차) ---------------------------------------------

    @staticmethod
    def _ai_svg_thumb(svg_text, size=56):
        from PyQt6.QtCore import QByteArray
        from PyQt6.QtGui import QImage, QPainter, QPixmap
        from PyQt6.QtSvg import QSvgRenderer
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.white)
        r = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if r.isValid():
            r.render(p, QRectF(4, 4, size - 8, size - 8))
        p.end()
        return QPixmap.fromImage(img)

    def _ai_followup_symbol(self):
        """후보 막대 「이어 만들기」 — 고른 후보(최대 4개)를 바탕으로 패널 입력칸에 붙인다. 「만들기」하면 새 줄이 아래에 붙는다."""
        st = self._ai_staged
        if st is None or st.slots is None:
            return
        if not st.picked:
            self.statusBar().showMessage("바탕으로 쓸 후보를 먼저 클릭해 고르세요", 3000)
            return
        idx = sorted(st.picked)[:4]
        refs = [st.cands[i].svg for i in idx]
        self._ai_panel.set_followup("symbol", f"고른 후보 {len(refs)}개", [self._ai_svg_thumb(v) for v in refs],
                                    refs=refs, base=st, base_text=getattr(st.request, "base_text", "") or st.request.text)

    def _ai_followup_flow(self):
        """흐름도 막대 「이어 고치기」 — 지금 결과 코드를 바탕으로 패널 입력칸에 붙인다. 새 결과는 원본 옆에 나란히."""
        st = self._ai_staged
        if st is None or st.slots is not None or st.request.kind != "flow":
            return
        btn = self.sender()
        base = st.alt if (btn is not None and btn.property("aiSide") == "alt" and st.alt is not None) else st
        code = getattr(base.request, "result_text", "")
        if not code:
            return
        n = sum(1 for line in code.splitlines()[1:] if line.strip())
        label = f"원본 흐름도({n}줄)" if base is not st else f"지금 흐름도({n}줄)"
        self._ai_panel.set_followup("flow", label, base_code=code, base=base, base_text=base.request.text)
