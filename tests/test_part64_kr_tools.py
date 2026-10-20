"""2026-10-20 KAIROS 문서 검토 — 웹 칠판 대화·그림의 공공 데이터 도구(`easycad/ai/kr_tools.py`): 기상청 날씨·천문연 달력(KAIROS MCP).

KAIROS는 부르지 않는다 — 가짜 클라이언트(도구 고르기)·가짜 http(MCP). 실제 호출은 따로 확인(서울 예보·올해 공휴일·전주 일출, 전주 날씨는 안 씀).
"""
import json
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from easycad.ai import board_image, kr_tools  # noqa: E402

SLOTS = [{"date": "2026-10-21", "time": f"{h:02d}:00", "tempC": t, "precipProbPct": p, "sky": s, "precipType": r}
         for h, t, p, s, r in [(3, 9, 0, "흐림", "없음"), (9, 12, 60, "흐림", "비"), (15, 16, 20, "맑음", "없음")]] + \
        [{"date": "2026-10-22", "time": "09:00", "tempC": 5, "precipProbPct": 0, "sky": "맑음", "precipType": "없음"}]


class FakeHttp:
    """MCP 흉내 — tools/list는 도구 하나씩, tools/call은 `answers[이름]`(돌아온 도시를 바꿔 서울로 떨어지는 것도 흉내)."""
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def post(self, url, headers, json, timeout):
        assert headers["Accept"] == "application/json, text/event-stream"   # 없으면 406
        suite = url.rstrip("/").rsplit("/", 1)[1]
        self.calls.append((suite, json["method"], json.get("params")))
        if json["method"] == "tools/list":
            tools = [{"name": "get_forecast", "inputSchema": {"$schema": "x", "type": "object", "properties": {"city": {"type": "string"}}}}] if suite == "kr-weather" \
                else [{"name": "get_holidays", "inputSchema": {"type": "object"}}]
            res = {"tools": tools}
        else:
            res = {"content": [{"type": "text", "text": self.answers(json["params"])}]}
        body = "event: message\ndata: " + __import__("json").dumps({"jsonrpc": "2.0", "id": 1, "result": res}) + "\n\n"
        return SimpleNamespace(status_code=200, text=body)


def fake_client(calls):
    tc = [SimpleNamespace(function=SimpleNamespace(name=n, arguments=json.dumps(a, ensure_ascii=False))) for n, a in calls]
    seen = {}

    def create(**k):
        seen.update(k)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=tc, content=None))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), seen


def weather(params):
    city = params["arguments"].get("city", "서울")
    return json.dumps({"city": city if city in kr_tools.CITIES else "서울", "base": {"date": "20261020"}, "slots": SLOTS}, ensure_ascii=False)


def test_forecast_is_called_whole_and_summarised_per_day():
    kr_tools._defs.clear()
    http = FakeHttp(weather)
    client, seen = fake_client([("kr-weather__get_forecast", {"city": "서울", "limit": 8})])
    found = kr_tools.gather("k", "내일 서울 날씨 어때?", base_url="https://g", client=client, http=http, today="2026년 10월 20일(화)")
    assert seen["model"] == kr_tools.TOOL_MODEL and "2026년 10월 20일" in seen["messages"][0]["content"]
    assert seen["tools"][0]["function"]["name"] == "kr-weather__get_forecast" and "$schema" not in seen["tools"][0]["function"]["parameters"]
    assert [c[2]["arguments"]["limit"] for c in http.calls if c[1] == "tools/call"] == [8, 200]   # 모델이 작게 줘도 사흘 치 다시
    day = json.loads(found[0]["text"])["days"][0]
    assert (day["minC"], day["maxC"], day["rainProbMaxPct"], day["skyAM"], day["skyPM"], day["precipType"]) == (9, 16, 60, "흐림", "맑음", "비")
    assert kr_tools.sources(found) == [{"n": 1, "title": "기상청 날씨누리", "url": "https://www.weather.go.kr"}]
    assert kr_tools.context_text(found).startswith("[1] 기상청 날씨누리 · get_forecast")


def test_unknown_city_is_not_used_and_fallback_to_seoul_is_dropped():
    # 전주는 도구가 모름 → 서울 날씨가 옴(실측). 목록 밖이면 안 부르고, 돌아온 도시가 다르면 버림
    kr_tools._defs.clear()
    http = FakeHttp(weather)
    client, _ = fake_client([("kr-weather__get_forecast", {"city": "전주"})])
    assert kr_tools.gather("k", "내일 전주 날씨", base_url="https://g", client=client, http=http) == []
    assert not [c for c in http.calls if c[1] == "tools/call"]
    http2 = FakeHttp(lambda p: json.dumps({"city": "서울", "slots": SLOTS}))
    client2, _ = fake_client([("kr-weather__get_forecast", {"city": "부산"})])
    assert kr_tools.gather("k", "내일 부산 날씨", base_url="https://g2", client=client2, http=http2) == []


def test_calendar_and_no_words_and_test_mode():
    kr_tools._defs.clear()
    http = FakeHttp(lambda p: '{"year": 2026, "items": [{"date": "2026-12-25", "name": "기독탄신일"}]}')
    client, _ = fake_client([("kr-calendar__get_holidays", {"year": 2026})])
    found = kr_tools.gather("k", "올해 남은 공휴일", base_url="https://g3", client=client, http=http)
    assert found[0]["tool"] == "get_holidays" and "기독탄신일" in found[0]["text"] and kr_tools.sources(found)[0]["title"].startswith("한국천문연구원")
    assert kr_tools.gather("k", "송신탑 그려줘", base_url="https://g3", client=client, http=http) == []   # 날씨·달력 말 없음 = 안 부름
    assert os.environ.get("EASYCAD_ROUTE") == "rules"
    assert kr_tools.gather("k", "내일 서울 날씨", base_url="https://g3") == []   # 시험 스위치 — 진짜 KAIROS를 안 부름


def test_image_followup_keeps_public_data_facts():
    msgs = [{"role": "user", "content": "내일 서울 날씨 그려줘"},
            {"role": "assistant", "content": kr_tools.TOOL_HEAD + "(기상청·천문연 자료).\n내일 서울 9~16도, 오전 비 [1]\n\n그림 후보 2장 — 마음에 드는 것을 눌러 칠판에 붙여요"},
            {"role": "user", "content": "날짜도 넣어 줘"}]
    fu = board_image.followup(msgs)
    assert fu["facts"] == "내일 서울 9~16도, 오전 비" and fu["asks"] == ["내일 서울 날씨 그려줘"]
