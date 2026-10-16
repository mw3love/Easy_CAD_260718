"""AI 요청 관리(§8 항목51, 2026-10-16) — 옛 오른쪽 「KAIROS로 만들기」 패널(§8 항목36, `ai_panel.py`)의 화면 없는 몸통.

Magic Board 개편(`docs/EasyCAD_계획.md` §8 항목51): 입구는 가운데 칸 하나(`start_prompt.py`), 이어 고치기는 결과 막대의 입력
한 줄(`host_aimake._StagingBar`), 진행·기록은 화면 아래 작은 상태 알약(`host_aimake._AIStatusPill`)이 맡는다. 그래서 패널이
들고 있던 것 중 화면이 아닌 것 — 요청 만들기·종류 짐작·기록·이어 만들기 바탕·모델 고르기(+가격)·남은 크레딧 — 만 여기 남긴다.
호스트(`host_aimake`)가 쓰는 이름(`request_make`·`resubmit`·`set_followup`·`followup`·`entries`·`make_requested`…)은 패널 때와
같게 두어 생성·임시 결과 쪽 코드는 그대로 쓴다.

**PyQt 위젯 없음**(QObject·시그널만) — 화면 쪽은 시그널(`status_changed`·`credit_changed`·`notice`·`models_changed`)을 받아 그린다.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QIcon

from easycad.ai import gateway as gw
from easycad.app_settings import app_settings
from easycad.canvas.core_constants import _svg_icon_pixmap
from easycad.canvas.host_dialogs import _AIGatewaySettingsDialog, _CreditWorker, _ModelInfoWorker, _detach_worker
from easycad.canvas.photo_dialog import PHOTO_MODELS

# 종류 이름(결과 기준 — 기술 이름 Mermaid·SVG를 쓰지 않음). 사용자는 고르지 않고 기록·상태 알약에만 보인다.
KIND_LABEL = {"symbol": "심볼", "flow": "흐름도", "trace": "베끼기", "explain": "한 장 보드"}   # §8 항목53 — 옛 「풀어 그리기」
# 메뉴·단축키로 종류를 정해 가운데 칸을 열 때의 안내글(종류 칩 대신 — §8 항목51 "종류 칩 없음").
PLACEHOLDER = {
    "symbol": "만들 부품을 적어 주세요 — 예: 파라볼라 안테나",
    "flow": "말하듯 써도 돼요 — 예: 송신기 내부 증폭 구조를 상세하게 그려줘",
    "trace": "도면 사진을 끌어다 놓기 · Ctrl+V · +",
    "explain": "PDF를 끌어다 놓고, 원하면 관점을 써 주세요 — 예: 처음 보는 사람용으로",
}
SYMBOL_COUNT_DEFAULT = 6
SYMBOL_COUNT_MAX = 10
_SYMBOL_COUNT_KEY = "ai_panel/symbol_count"      # 옛 패널 「후보 수」 값 — 남아 있으면 그대로 쓴다
_MODEL_CHOICE_KEY = "ai/model_choice"            # "auto" | 모델 id
_MODEL_INFO_KEY = "ai/model_info"                # 마지막으로 받은 가격표(JSON) — 키를 넣을 때 받아 둔다
AUTO = "auto"
# 종류별 추천 모델 — 「자동」일 때 쓴다.
DEFAULT_MODEL = {
    "symbol": gw.TEXT_RECOMMEND_1,
    "flow": gw.TEXT_RECOMMEND_MERMAID,
    "trace": PHOTO_MODELS[0][0],
    "explain": gw.TEXT_RECOMMEND_EXPLAIN,
}
PENDING_TEXT = "준비 중"

# 종류 짐작(§8 항목39 → 51). 사용자는 종류를 고르지 않는다 — 틀리면 결과 막대 한 줄로 바꾼다.
_SYMBOL_WORDS = ("아이콘", "심볼", "기호", "부품", "로고", "픽토그램", "그림 하나")
_FLOW_WORDS = ("흐름", "순서도", "절차", "단계", "관계", "구조", "과정", "결재", "다시 배치")
_TRACE_WORDS = ("베끼", "그대로", "따라 그", "옮겨")
# PDF와 같이 쓴 말(2026-10-16 사용자 요청: "간단한 이미지만 만들어 달라고 할 수도") — 말이 없으면 지금처럼 한 장 보드.
_BOARD_WORDS = ("보드", "한 장", "한장", "정리", "요약")
_PICTURE_WORDS = ("그림", "이미지", "일러스트")

# 가운데 칸이 받는 파일(§8 항목51 ③) — 나머지는 "아직 못 읽어요" 안내.
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")
SUPPORTED_TEXT = "사진(png·jpg·bmp·webp·gif), PDF"


# 조회 작업자(크레딧·가격표)는 창에 매달지 않는다 — 창이 닫히지 않고 GC로 지워질 때(테스트에서 흔함) 도는 QThread가 같이
# 파괴되면 "QThread: Destroyed while thread is still running"으로 앱이 출력 없이 꺼진다(2026-10-16 전체 pytest exit 127 원인과
# 같은 부류 — 이 칸이 창마다 열릴 때 조회를 시작하게 되면서 다시 걸렸다). 끝날 때까지 여기서 붙잡고, 끝나면 지운다.
_RUNNING_WORKERS: set = set()


def _start_detached(worker):
    gw.preload_network()   # 작업자끼리 첫 import 경합(교착) 막기
    _RUNNING_WORKERS.add(worker)

    def _reap():
        _RUNNING_WORKERS.discard(worker)
        worker.deleteLater()
    worker.finished.connect(_reap)
    worker.start()


def guess_kind(text: str, has_image: bool, has_pdf: bool = False) -> str:
    """말·첨부로 종류를 짐작한다 — "trace"(베끼기) | "symbol"(심볼) | "flow"(흐름도) | "explain"(풀어 그리기).

    PDF가 있으면 기본은 한 장 보드, 말이 "그림·아이콘"이면 심볼, "흐름·절차"면 흐름도(PDF 내용으로 — 2026-10-16, "보드·정리"가
    먼저 맞는다). 사진이 있으면 기본은 베끼기(모양 그대로), "흐름·관계" 같은 말이 있으면 흐름도(관계만 읽어
    다시 배치). 사진이 없으면 "아이콘·부품" 같은 말이 있으면 심볼, 나머지는 흐름도."""
    t = (text or "").strip()
    if has_pdf:
        if any(w in t for w in _BOARD_WORDS):
            return "explain"
        if any(w in t for w in _SYMBOL_WORDS + _PICTURE_WORDS):
            return "symbol"
        return "flow" if any(w in t for w in _FLOW_WORDS) else "explain"
    if has_image:
        if any(w in t for w in _TRACE_WORDS):
            return "trace"
        return "flow" if any(w in t for w in _FLOW_WORDS) else "trace"
    if any(w in t for w in _SYMBOL_WORDS):
        return "symbol"
    return "flow"


def unsupported_file_text(name: str) -> str:
    return f"이 파일은 아직 못 읽어요: {name} — 되는 것: {SUPPORTED_TEXT}"


def _ai_icon(name: str, color) -> QIcon:
    """resources/icons/<name>.svg를 그 색으로(옛 상단바 아이콘과 같은 재칠 방식, `core_constants._svg_icon_pixmap`)."""
    return QIcon(_svg_icon_pixmap(name, 32, QColor(color)))


@dataclass
class AIRequest:
    """「만들기」 한 번 — 호출부(호스트)가 받아 생성을 맡고, 진행·결과는 `entry.set_status`로 알린다."""
    kind: str
    text: str
    image: object = None          # PIL.Image | None
    image_name: str = ""
    model: str = ""
    entry: object = field(default=None, repr=False)   # _RequestRecord
    doc: object = field(default=None, repr=False)     # 만들기를 누른 탭(CanvasDocument) — 호스트가 채움
    center: object = None                             # 결과를 놓을 씬 좌표(만들기를 누른 순간의 화면 가운데)
    replace_target: object = field(default=None, repr=False)   # 우클릭 「AI로 바꾸기」의 대상 도형(심볼)
    count: int = SYMBOL_COUNT_DEFAULT                 # 심볼 후보 수
    # 이어 만들기: 심볼은 고른 후보 SVG(refs), 흐름도는 지금 결과 코드(base_code)를 지시와 함께 보낸다.
    refs: list = None
    base_code: str = ""
    base_text: str = ""                               # 원래 요청 글(지시가 비면 이걸로)
    followup_of: object = field(default=None, repr=False)   # 이어 만든 바탕 임시 결과(_StagedResult)
    pdf_path: str = ""                                # 「풀어 그리기」의 PDF(§8 항목45)
    sources: list = None                              # 여러 자료 A·B·C(§8 항목53 4단계) — [{"label","kind","name","path","image"}]
    model_used: str = ""                              # 실제로 답한 모델(폴백이면 고른 것과 다름) — 결과 막대에 보인다(2026-10-16)
    elapsed: float = 0.0                              # 보내고 답을 받기까지 초


class _RequestRecord(QObject):
    """기록 한 줄(옛 패널의 기록 칸) — 화면 없이 상태만 든다. 호스트는 패널 때처럼 `entry.set_status(...)`로 알리고,
    상태 알약·기록 메뉴가 `changed`를 받아 그린다."""

    changed = pyqtSignal(object)   # self

    def __init__(self, req: AIRequest, parent=None):
        super().__init__(parent)
        self.request = req
        self.kind = req.kind
        self.removed = False
        self.running = False
        self.time = time.strftime("%H:%M")
        self._status = ""

    def set_status(self, text: str, running: bool = False):
        self._status = text
        self.running = running
        self.changed.emit(self)

    def status_text(self) -> str:
        return self._status

    def title(self) -> str:
        """기록 메뉴·상태 알약에 보일 짧은 글 — "흐름도 · 휴가 신청부터 결재까지…"."""
        req = self.request
        body = req.text or (f"[{'PDF' if req.kind == 'explain' else '그림'}] {req.image_name}" if req.image_name else "")
        if req.refs or req.base_code:
            body = "[이어서] " + (req.text or "다듬기")
        if len(body) > 28:
            body = body[:27] + "…"
        head = f"{KIND_LABEL.get(req.kind, req.kind)} · {body}" if body else KIND_LABEL.get(req.kind, req.kind)
        return f"{head} · {req.model_used}" if req.model_used else head


class _AIController(QObject):
    """요청·기록·이어 만들기·모델·크레딧(위젯 없음). 호스트가 하나 만들어 들고 있다(`host_aimake._build_ai_control`)."""

    make_requested = pyqtSignal(object)   # AIRequest
    entry_removed = pyqtSignal(object)    # AIRequest — 기록을 지움(만드는 중이면 호스트가 취소)
    status_changed = pyqtSignal(object)   # _RequestRecord — 새 요청·상태가 바뀜(상태 알약)
    credit_changed = pyqtSignal(str)      # 「남은 크레딧 …」 한 줄(리치 글 — 키 넣기 링크 포함)
    models_changed = pyqtSignal()         # 가격표를 새로 받음
    notice = pyqtSignal(str)              # 한 줄 안내(빈 입력·첨부 필요 등) — 가운데 칸이나 상태 알약에

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self._entries: list[_RequestRecord] = []
        self._followup = None
        self._flow_code = ""
        self._credit_worker = None
        self._model_worker = None
        self.credit_text = ""
        self._model_choice = str(app_settings().value(_MODEL_CHOICE_KEY, AUTO) or AUTO)
        try:
            self._model_info = json.loads(app_settings().value(_MODEL_INFO_KEY, "[]") or "[]")
        except (TypeError, ValueError):
            self._model_info = []

    # ---- 모델(「자동 ▾」) -------------------------------------------------------------

    def model_choice(self) -> str:
        return self._model_choice

    def set_model_choice(self, mid: str):
        self._model_choice = mid or AUTO
        app_settings().setValue(_MODEL_CHOICE_KEY, self._model_choice)

    def model_for(self, kind: str) -> str:
        """「자동」이면 종류별 추천. 고른 모델은 글 종류에 쓰고, 베끼기는 사진용 모델을 골랐을 때만(다른 모델은 사진→도면 검증 안 됨)."""
        choice = self._model_choice
        if choice == AUTO:
            return DEFAULT_MODEL[kind]
        if kind == "trace" and choice not in {m for m, _ in PHOTO_MODELS}:
            return DEFAULT_MODEL["trace"]
        return choice

    def model_info(self) -> list:
        return list(self._model_info)

    def fetch_models(self):
        """가격표를 한 번 받아 온다(백그라운드). 키를 넣을 때·목록을 처음 펼칠 때."""
        key = gw.resolve_api_key()
        if not key:
            return
        w = self._model_worker
        try:
            if w is not None and w.isRunning():
                return
        except RuntimeError:
            pass
        self._model_worker = _ModelInfoWorker(key, gw.resolve_base_url())
        self._model_worker.succeeded.connect(self._on_models)
        _start_detached(self._model_worker)

    def _on_models(self, models):
        self._model_info = list(models)
        app_settings().setValue(_MODEL_INFO_KEY, json.dumps(self._model_info))
        self.models_changed.emit()

    @staticmethod
    def model_label(info: dict) -> str:
        """「gemini-3.6-flash   보통 · $0.75 / 3.75」 — 100만 토큰당 달러(입력 / 출력)."""
        tier = gw.price_tier(info.get("output"))
        if info.get("input") is None or info.get("output") is None:
            return info["id"]
        return f"{info['id']}   {tier} · ${info['input']:g} / {info['output']:g}"

    # ---- 남은 크레딧(§8 항목41) ---------------------------------------------------------

    @staticmethod
    def _link(text: str) -> str:
        return f"<a href='key' style='color:#da7756; text-decoration:none;'>{text}</a>"

    def _set_credit(self, text: str):
        self.credit_text = text
        self.credit_changed.emit(text)

    def refresh_credit(self):
        key = gw.resolve_api_key()
        if not key:
            self._set_credit("KAIROS 키가 아직 없어요 · " + self._link("키 넣기"))
            return
        w = self._credit_worker
        try:
            if w is not None and w.isRunning():
                return
        except RuntimeError:   # 떼어 낸 뒤 지워진 워커(`_detach_worker` 주석의 죽은 래퍼)
            pass
        if "남은 크레딧 " not in self.credit_text:
            self._set_credit("남은 크레딧 확인 중…")
        self._credit_worker = _CreditWorker(key, gw.resolve_base_url())
        self._credit_worker.succeeded.connect(self._on_credit)
        self._credit_worker.failed.connect(self._on_credit_failed)
        _start_detached(self._credit_worker)

    def _on_credit(self, remaining: float, quota: float):
        self._set_credit(f"남은 크레딧 {remaining:,.0f} / {quota:,.0f} · " + self._link("키 설정"))

    def _on_credit_failed(self, _err: str):
        self._set_credit("남은 크레딧을 못 읽었어요 · " + self._link("키 확인"))

    def open_gateway_settings(self, parent=None):
        from PyQt6.QtWidgets import QDialog
        if _AIGatewaySettingsDialog(parent or self._host).exec() == QDialog.DialogCode.Accepted:
            self.refresh_credit()
            self.fetch_models()

    def detach_workers(self):
        """창이 닫힐 때 호스트가 부른다 — 도는 조회는 떼어 내 결과를 버린다."""
        _detach_worker(self._credit_worker)
        self._credit_worker = None
        _detach_worker(self._model_worker)
        self._model_worker = None

    # ---- 이어 만들기 ---------------------------------------------------------------

    def set_followup(self, kind, label, pixmaps=(), *, refs=None, base_code="", base=None, base_text=""):
        """호스트(결과 막대)가 부른다 — 다음 요청을 그 결과를 바탕으로 한 이어 만들기로."""
        self._followup = {"kind": kind, "label": label, "pixmaps": list(pixmaps),
                          "refs": list(refs) if refs else None, "base_code": base_code,
                          "base": base, "base_text": base_text}

    def clear_followup(self):
        self._followup = None

    def followup(self):
        return self._followup

    # ---- 흐름도 코드(결과의 Mermaid — 「파일 › 가져오기」·테스트가 읽음) ---------------------------------

    def show_flow_code(self, code: str):
        self._flow_code = code

    def flow_code(self) -> str:
        return self._flow_code

    # ---- 요청 ---------------------------------------------------------------------

    def symbol_count(self) -> int:
        return max(1, min(SYMBOL_COUNT_MAX, app_settings().value(_SYMBOL_COUNT_KEY, SYMBOL_COUNT_DEFAULT, type=int)))

    def request_make(self, text: str = "", *, kind: str | None = None, image=None, image_name: str = "",
                     pdf_path: str = "", sources=None):
        """요청 하나를 만들어 기록에 남기고 `make_requested`로 넘긴다. 이어 만들기 바탕이 걸려 있으면 그 이어 만들기.
        입력이 모자라면 `notice`로 알리고 None. 종류를 안 주면 짐작한다(§8 항목51 — 사용자는 종류를 고르지 않음)."""
        text = (text or "").strip()
        fu = self._followup
        if fu is not None:
            if fu["kind"] in ("flow", "explain") and not text:
                self.notice.emit("어떻게 고칠지 적어 주세요. 예: 감시장치를 아래로")
                return None
            req = AIRequest(kind=fu["kind"], text=text,   # 보드 이어 고치기도 "explain"(§8 항목53 — 바탕 설계서로 `_FlowGenWorker`)
                            model=self.model_for(fu["kind"]), count=self.symbol_count(),
                            refs=fu["refs"], base_code=fu["base_code"], base_text=fu["base_text"])
            req.followup_of = fu["base"]
            self.clear_followup()
            self._add_entry(req)
            self.make_requested.emit(req)
            return req
        if kind is None:
            kind = guess_kind(text, image is not None, bool(pdf_path))
        if sources and len(sources) >= 2:   # 여러 자료 → 한 장 보드
            req = AIRequest(kind="explain", text=text, model=self.model_for("explain"), sources=list(sources),
                            image_name=f"자료 {len(sources)}개")
            self._add_entry(req)
            self.make_requested.emit(req)
            return req
        if kind == "explain":
            if not pdf_path:
                self.notice.emit("한 장 보드는 PDF가 필요해요. PDF를 끌어다 놓거나 + 로 골라 주세요.")
                return None
            req = AIRequest(kind="explain", text=text, model=self.model_for("explain"), pdf_path=pdf_path,
                            image_name=os.path.basename(pdf_path))
        else:
            if kind == "trace" and image is None:
                self.notice.emit("베끼기는 도면 사진이 필요해요. 사진을 끌어다 놓거나 Ctrl+V로 붙여 주세요.")
                return None
            if not text and image is None:
                self.notice.emit("먼저 무엇을 그릴지 쓰거나 그림을 붙여 주세요.")
                return None
            req = AIRequest(kind=kind, text=text, image=image, image_name=image_name if image is not None else "",
                            model=self.model_for(kind), count=self.symbol_count(),
                            pdf_path=pdf_path if kind in ("flow", "symbol") else "")   # PDF + 「흐름도로」·「그림 하나」
            if req.pdf_path and not req.image_name:
                req.image_name = os.path.basename(pdf_path)
        self._add_entry(req)
        self.make_requested.emit(req)
        return req

    def resubmit(self, req: AIRequest) -> AIRequest:
        """결과 막대 「다시」 — 같은 입력(종류·글·그림·모델)으로 새 기록을 만들어 다시 보낸다."""
        again = AIRequest(kind=req.kind, text=req.text, image=req.image, image_name=req.image_name,
                          model=req.model, replace_target=req.replace_target, count=req.count,
                          refs=req.refs, base_code=req.base_code, base_text=req.base_text,
                          pdf_path=req.pdf_path, sources=req.sources)
        self._add_entry(again)
        self.make_requested.emit(again)
        return again

    def add_record(self, req: AIRequest) -> _RequestRecord:
        """AI를 부르지 않는 요청(Mermaid 코드 가져오기 등)도 기록에 남긴다 — 결과 막대·상태 알약이 같은 길로 알린다."""
        return self._add_entry(req)

    def _add_entry(self, req: AIRequest) -> _RequestRecord:
        rec = _RequestRecord(req, self)
        req.entry = rec
        rec.changed.connect(self.status_changed)
        self._entries.append(rec)
        self.status_changed.emit(rec)
        return rec

    def remove_entry(self, rec: _RequestRecord):
        """기록 지우기(만드는 중이면 호스트가 취소)."""
        if rec.removed:
            return
        rec.removed = True
        self.status_changed.emit(rec)
        self.entry_removed.emit(rec.request)

    def entries(self) -> list:
        """지우지 않은 기록 전부(오래된 것부터)."""
        return [e for e in self._entries if not e.removed]
