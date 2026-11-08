"""2026-10-20 — 웹 칠판 대화창 길 고르기(`easycad/ai/route.py`): 판단 모델 jev + 손질 둘 + 낱말 규칙 바닥 + 주간 자가 시험."""
from _shared import *  # noqa: F401,F403

from easycad.ai import route


class _Resp:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


class _Http:
    """가짜 /decisions/ — 질문마다 정한 (길, 확신도, 확률) 또는 예외."""
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, json))
        a = self.answers(json["state"]) if callable(self.answers) else self.answers
        if isinstance(a, Exception):
            raise a
        if isinstance(a, int):
            return _Resp(a, {})
        choice, conf, probs = a
        return _Resp(200, {"answers": {"q": {"type": "choice", "choice": choice, "confidence": conf, "probabilities": probs}}})


def _route(text, answer, **kw):
    import os
    old = os.environ.pop("EASYCAD_ROUTE", None)   # conftest가 규칙으로 고정해 둠 — 이 시험만 판단 모델 길
    try:
        return route.route("k", text, http=_Http(answer), base_url="https://g", **kw)
    finally:
        if old is not None:
            os.environ["EASYCAD_ROUTE"] = old


def test_route_uses_model_choice_and_sends_criteria():
    http = _Http(("board", 0.84, {"board": 0.84, "chat": 0.1}))
    import os
    old = os.environ.pop("EASYCAD_ROUTE", None)
    try:
        assert route.route("k", "우리 송신소 점검 결과 어땠지?", http=http, base_url="https://g") == ("board", "ai")
    finally:
        os.environ["EASYCAD_ROUTE"] = old or "rules"
    url, body = next(c for c in http.calls if c[0].endswith("/decisions/"))   # 판정 대화 모델과 동시에 물음(2026-11-07)
    assert url == "https://g/decisions/" and body["model"] == route.ROUTE_MODEL
    assert set(body["questions"]["q"]["criteria"]) == {"search", "board", "chat", "image", "report"}


def test_route_fixes_diagram_image_and_low_confidence_search():
    assert _route("방송 송출 흐름도 그려 줘", ("image", 0.95, {"image": 0.95}))[0] == "diagram"   # 흐름도 그리기 = 🔷 고칠 수 있는 도형(2026-11-03 — 전엔 대화로 떨어져 SVG 코드 글)
    assert _route("KBS 수신료 지금 어떻게 걷어?", ("chat", 0.5, {"chat": 0.5, "search": 0.45}))[0] == "search"   # 애매하면 출처 붙는 쪽
    assert _route("엑셀 VLOOKUP", ("chat", 0.9, {"chat": 0.9, "search": 0.05}))[0] == "chat"


def test_route_falls_back_to_rules():
    assert _route("삼성전자 주가 얼마야", RuntimeError("timeout")) == (route.board_chat.guess_kind("삼성전자 주가 얼마야"), "rules")
    assert _route("내일 날씨", 500)[1] == "rules"
    assert route.route("k", "내일 날씨", http=_Http(("chat", 1, {})))[1] == "rules"   # conftest: EASYCAD_ROUTE=rules


def test_self_check_turns_model_off_when_worse_than_rules():
    right = {route._state_text(q, bool(c)): want for q, c, want in route.CASES}
    jev = lambda s: right[s] if right[s] in route.CRITERIA else "image"   # 아이콘 길은 판단 모델에 없음 — 그림으로 답해도 낱말 손질이 아이콘으로(§8 항목63)
    res = route.self_check("k", http=_Http(lambda s: (jev(s), 0.9, {jev(s): 0.9})), base_url="https://g")
    assert res["ai"] == len(route.CASES) and res["use_ai"] and route.state["ai"]
    res = route.self_check("k", http=_Http(("image", 0.9, {"image": 0.9})), base_url="https://g")   # 망가진 모델 = 거의 다 그림
    assert res["ai"] < res["rules"] and not res["use_ai"] and not route.state["ai"]
    route.state["ai"] = True


def test_route_explicit_draw_beats_search():
    """2026-10-20 사용자 실사용 — 「내일의 전주 날씨를 고흐 느낌으로 그려줘」가 jev 검색(0.56)으로 감 → 「그려 줘」가 분명하면 그림."""
    probs = {"search": 0.6, "image": 0.38, "chat": 0.02}
    assert _route("내일의 전주 날씨를 고흐 느낌으로 그려줘.", ("search", 0.56, probs))[0] == "image"
    assert _route("송출 흐름도 그려 줘", ("search", 0.56, probs))[0] != "image"   # 흐름도는 그림 아님


class _Http2(_Http):
    """가짜 /decisions/ + /chat/completions/(판정 대화 모델 — judge = 답 글 또는 예외)."""
    def __init__(self, answers, judge):
        super().__init__(answers); self.judge = judge

    def post(self, url, headers=None, json=None, timeout=None):
        if url.endswith("/chat/completions/"):
            self.calls.append((url, json))
            if isinstance(self.judge, Exception):
                raise self.judge
            return _Resp(200, {"choices": [{"message": {"content": self.judge}}]})
        return super().post(url, headers=headers, json=json, timeout=timeout)


def _decide2(text, jev, judge):
    import os
    old = os.environ.pop("EASYCAD_ROUTE", None)
    try:
        http = _Http2(jev, judge)
        return route.decide("k", text, http=http, base_url="https://g"), http
    finally:
        if old is not None:
            os.environ["EASYCAD_ROUTE"] = old


def test_judge_model_wins_when_it_answers():   # 2026-11-07 — Flash-Lite 30/31 vs JEV 28/31: 「회의 내용 정리해 줘」 JEV chat → 판정 모델 report
    (kind, how, asks), http = _decide2("오늘 회의 내용 정리해 줘", ("chat", 0.7, {"chat": 0.7, "report": 0.3}), "report")
    assert (kind, how, asks) == ("report", "ai", [])                     # 다르면 묻지 않고 판정 모델
    body = next(j for u, j in http.calls if u.endswith("/chat/completions/"))
    assert body["model"] == route.JUDGE_MODEL and "report" in body["messages"][0]["content"]


def test_judge_failure_falls_back_to_jev():
    (kind, how, _), _h = _decide2("우리 송신소 점검 결과 어땠지?", ("board", 0.84, {"board": 0.84, "chat": 0.1}), RuntimeError("시간 초과"))
    assert (kind, how) == ("board", "ai")
    (kind, how, _), _h = _decide2("우리 송신소 점검 결과 어땠지?", ("board", 0.84, {"board": 0.84}), "몰라요")   # 길 이름이 없는 답 = 실패
    assert (kind, how) == ("board", "ai")


def test_agree_keeps_jev_ask_when_close():   # 둘이 같은 답이면 JEV 확률로 지금처럼 되묻기(1·2등 차 < 0.3이고 비싼 길)
    (kind, how, asks), _h = _decide2("회의 내용 자료로 만들어 줘", ("chat", 0.49, {"chat": 0.49, "report": 0.45}), "chat")
    assert kind == "chat" and asks == ["chat", "report"]


def test_special_routes_without_plus():
    """2026-11-08 「+」 없애기 — 발표 자료·인포그래픽·인터랙티브 카드는 말로(낱말이 분명하면 바로, 아니면 판정 모델), 묻는 말은 대화."""
    assert route.decide("k", "송신소 점검 결과로 발표 자료 만들어 줘")[0] == "slides"
    assert route.decide("k", "올해 OTT 이용률 인포그래픽 만들어 줘")[0] == "infographic"
    assert route.decide("k", "가격 × 물량 = 수출액을 직접 움직여 볼 수 있게 만들어 줘")[0] == "live"
    assert route.board_chat.guess_kind("발표 자료 잘 만드는 법 알려줘") == "chat"
    (kind, how, asks), _h = _decide2("신입이 볼 10장짜리 교육 자료 준비해 줘", ("chat", 0.6, {"chat": 0.6, "report": 0.3}), "slides")
    assert kind == "slides" and how == "ai" and asks == []                       # 판정 대화 모델만 아는 길이 이김(JEV 선택지엔 없음)
    assert {"slides", "infographic", "live"} <= set(route.JUDGE_KINDS)            # 선택지 = KAIROS 기능 표
    from easycad.ai import features
    assert set(route.JUDGE_KINDS) == {f["kind"] for f in features.FEATURES} and features.ASK_FIRST == {"slides", "infographic"}
    assert features.credit_text("live") == "약 30~60크레딧" and features.credit_text("report") == ""
