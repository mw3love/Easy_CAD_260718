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
    url, body = http.calls[0]
    assert url == "https://g/decisions/" and body["model"] == route.ROUTE_MODEL
    assert set(body["questions"]["q"]["criteria"]) == {"search", "board", "chat", "image", "report", "tidy"}


def test_route_fixes_diagram_image_and_low_confidence_search():
    assert _route("방송 송출 흐름도 그려 줘", ("image", 0.95, {"image": 0.95}))[0] == "chat"   # 흐름도는 칠판 도형으로
    assert _route("KBS 수신료 지금 어떻게 걷어?", ("chat", 0.5, {"chat": 0.5, "search": 0.45}))[0] == "search"   # 애매하면 출처 붙는 쪽
    assert _route("엑셀 VLOOKUP", ("chat", 0.9, {"chat": 0.9, "search": 0.05}))[0] == "chat"


def test_route_falls_back_to_rules():
    assert _route("삼성전자 주가 얼마야", RuntimeError("timeout")) == (route.board_chat.guess_kind("삼성전자 주가 얼마야"), "rules")
    assert _route("내일 날씨", 500)[1] == "rules"
    assert _route("이것들 묶어 줘", ("tidy", 0.9, {"tidy": 0.9}), has_items=False)[1] == "rules"   # 조각 목록 없이는 정돈 못 함
    assert route.route("k", "내일 날씨", http=_Http(("chat", 1, {})))[1] == "rules"   # conftest: EASYCAD_ROUTE=rules


def test_self_check_turns_model_off_when_worse_than_rules():
    right = {route._state_text(q, bool(c)): want for q, c, want in route.CASES}
    res = route.self_check("k", http=_Http(lambda s: (right[s], 0.9, {right[s]: 0.9})), base_url="https://g")
    assert res["ai"] == len(route.CASES) and res["use_ai"] and route.state["ai"]
    res = route.self_check("k", http=_Http(("image", 0.9, {"image": 0.9})), base_url="https://g")   # 망가진 모델 = 거의 다 그림
    assert res["ai"] < res["rules"] and not res["use_ai"] and not route.state["ai"]
    route.state["ai"] = True
