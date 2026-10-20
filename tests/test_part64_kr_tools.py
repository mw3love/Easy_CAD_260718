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


def fake_client(calls, *more):
    """첫 번째 물음엔 `calls`, 그다음 물음엔 `more`를 차례로(다 쓰면 도구 없음 = 끝). `seen`은 첫 물음, `seen["rounds"]`는 물음마다의 messages."""
    rounds = [calls, *more]
    seen = {"rounds": []}

    def create(**k):
        if not seen["rounds"]:
            seen.update(k)
        seen["rounds"].append(list(k["messages"]))
        now = rounds[len(seen["rounds"]) - 1] if len(seen["rounds"]) <= len(rounds) else []
        tc = [SimpleNamespace(id=f"t{i}", function=SimpleNamespace(name=n, arguments=json.dumps(a, ensure_ascii=False))) for i, (n, a) in enumerate(now)]
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
    assert [t["function"]["name"].split("__")[0] for t in seen["tools"]] == ["kr-weather"]   # 날씨 말 = 날씨 묶음 도구만 보냄
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


def test_suites_are_picked_by_words():
    pick = kr_tools.pick_suites
    assert pick("근로기준법상 연차휴가는 며칠이야?") == ["korean-law"] and pick("방송법에서 재허가 기간은?") == ["korean-law"]
    assert pick("전북 인구 최근 5년 추이") == ["kr-macro"] and pick("요즘 기준금리 얼마야?") == ["kr-macro"]
    assert pick("지금 기상특보 있어?") == ["kr-weather", "kr-safety"] and pick("오늘 서울 미세먼지 어때?") == ["airkorea"]
    assert pick("'플래쉬'가 맞아 '플래시'가 맞아?") == ["kr-language"]
    for q in ("송신탑 구조 설명해 줘", "이게 맞아?", "좋은 방법은 뭐야?", "회의 내용 정리해 줘"):   # 관계없는 말 = 도구 안 씀(느려지지 않게)
        assert pick(q) == [] and not kr_tools.WORDS.search(q), q


def test_law_search_then_article_in_two_rounds():
    # 법령은 찾기(search_law → mst) 다음 물음에서 조문(get_law) — 앞 결과를 tool 메시지로 돌려줘야 둘째 물음이 mst를 앎
    kr_tools._defs.clear()
    law = {"search_law": '{\n  "items": [{"mst": "285279", "name": "근로기준법"}]\n}', "get_law": '{"name": "근로기준법", "articles": [{"no": "60", "text": "15일의 유급휴가"}]}'}
    http = FakeHttp(lambda p: law[p["name"]])
    client, seen = fake_client([("korean-law__search_law", {"query": "근로기준법"})], [("korean-law__get_law", {"mst": "285279", "article": "60"})])
    found = kr_tools.gather("k", "근로기준법상 연차휴가는 며칠이야?", base_url="https://g4", client=client, http=http)
    assert [f["tool"] for f in found] == ["search_law", "get_law"] and len(seen["rounds"]) == 3   # 셋째 물음에 도구 없음 = 끝
    second = seen["rounds"][1]
    assert second[-2]["tool_calls"][0]["id"] == "t0" and second[-1] == {"role": "tool", "tool_call_id": "t0", "content": found[0]["text"]}
    assert found[0]["text"] == '{"items":[{"mst":"285279","name":"근로기준법"}]}'   # 들여쓴 JSON을 빽빽하게
    assert kr_tools.sources(found) == [{"n": 1, "title": "국가법령정보센터", "url": "https://www.law.go.kr"}]
    assert kr_tools.context_text(found).count("[1] 국가법령정보센터 · ") == 2
    assert kr_tools.context_text(found).index("get_law") < kr_tools.context_text(found).index("search_law")   # 조문이 앞(재료가 잘려도 남게)


def test_sources_per_institution():
    found = [{"suite": "kr-macro", "tool": "get_statistics_data", "args": {}, "text": "x"},
             {"suite": "kr-macro", "tool": "get_bok_statistic", "args": {}, "text": "y"},
             {"suite": "kr-safety", "tool": "get_weather_warnings", "args": {}, "text": "z"},
             {"suite": "kr-weather", "tool": "get_forecast", "args": {}, "text": "w"}]
    assert [(s["n"], s["title"]) for s in kr_tools.sources(found)] == [(1, "통계청 KOSIS"), (2, "한국은행 ECOS"), (3, "기상청 날씨누리")]   # 특보·날씨 = 같은 기상청 한 번
    assert "[3] 기상청 날씨누리 · get_forecast" in kr_tools.context_text(found)


def test_tool_error_is_retried_once():
    # 에어코리아가 가끔 「This operation was aborted」(isError) — 한 번 더 부르면 됨(2026-10-21 실측)
    kr_tools._defs.clear()
    n = {"call": 0}

    class Flaky(FakeHttp):
        def post(self, url, headers, json, timeout):
            if json["method"] == "tools/call":
                n["call"] += 1
                if n["call"] == 1:
                    body = "data: " + __import__("json").dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "This operation was aborted"}], "isError": True}})
                    return SimpleNamespace(status_code=200, text=body)
            return super().post(url, headers, json, timeout)
    http = Flaky(lambda p: '{"stations": [{"station": "중구", "pm25": 19}]}')
    client, _ = fake_client([("airkorea__get_air_quality", {"sido": "서울"})])
    found = kr_tools.gather("k", "오늘 서울 미세먼지 어때?", base_url="https://g5", client=client, http=http)
    assert n["call"] == 2 and found[0]["text"] == '{"stations":[{"station":"중구","pm25":19}]}'
    assert kr_tools.sources(found)[0]["title"] == "에어코리아"


def test_finding_only_gets_one_nudge():
    # 법령을 찾기만 하고 멈추면 한 번 재촉 → 조문을 받음. 재촉은 한 번뿐(또 멈추면 끝)
    kr_tools._defs.clear()
    law = {"search_law": '{"items": [{"mst": "285279"}]}', "get_law": '{"articles": [{"no": "60"}]}'}
    http = FakeHttp(lambda p: law[p["name"]])
    client, seen = fake_client([("korean-law__search_law", {"query": "근로기준법"})], [], [("korean-law__get_law", {"mst": "285279"})])
    found = kr_tools.gather("k", "근로기준법 연차", base_url="https://g6", client=client, http=http)
    assert [f["tool"] for f in found] == ["search_law", "get_law"] and "아직 찾기 결과뿐" in seen["rounds"][2][-1]["content"]
    client2, seen2 = fake_client([("korean-law__search_law", {"query": "근로기준법"})])
    assert [f["tool"] for f in kr_tools.gather("k", "근로기준법 연차", base_url="https://g6", client=client2, http=http)] == ["search_law"]
    assert len(seen2["rounds"]) == 3   # 찾기 → 멈춤 → 재촉 → 또 멈춤 = 끝
