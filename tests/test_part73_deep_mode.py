"""§8 항목66 3-3 딥모드 서버(2026-10-25) — `easycad/ai/deep_mode.py`: 계획 다듬기·질문지 답·계획(앞 계획 + 고칠 말)·재료(공공 → 웹 갈아타기, 출처 번호 하나로)·본문,
서버 `/api/chat` `kind: 'deep'`(plan·build)와 `/api/models` `jobs.deep`. 화면 흐름은 `web/e2e/flow33-deep-chat.spec.js`(가짜 서버), 지면은 `flow31`.

KAIROS는 부르지 않는다 — 가짜 클라이언트·가짜 검색.
"""
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))
from easycad.ai import deep_mode  # noqa: E402


class FakeClient:
    """답을 차례로 돌려주는 가짜 KAIROS(보낸 messages를 적어 둠)."""
    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.sent.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answers.pop(0)))])


PLAN = {"title": "반도체 수출", "headline": "한 판에", "pages": 2, "sections": [
    {"title": "기억할 숫자", "question": "얼마?", "shape": "숫자 타일", "source": "ai", "size": "주인공"},
    {"title": "흐름", "shape": "그래프", "chart": "꺾은선", "source": "kr", "query": "반도체 수출 통계", "size": "주인공"},
    {"title": "원리", "shape": "단계 카드", "source": "ai"},
    {"title": "이상한 모양", "shape": "홀로그램", "source": "space"},
    {"title": "출처", "shape": "출처 카드", "source": "web", "size": "작게"}]}


def test_clean_plan_fixes_shapes_sources_heroes():
    p = deep_mode.clean_plan(PLAN)
    assert "pages" not in p and p["title"] == "반도체 수출"
    s = p["sections"]
    assert s[0]["source"] == "web" and s[0]["query"] == "기억할 숫자"     # 숫자 꼭지를 ai로 두면 웹 검색으로(검색 문장이 없으면 제목)
    assert [x["size"] for x in s[:2]] == ["주인공", "보통"]                 # 주인공은 하나
    assert s[1]["chart"] == "꺾은선" and s[2]["chart"] is None and s[2]["query"] is None
    assert s[3]["shape"] == "접힌 메모" and s[3]["source"] == "ai"         # 모르는 모양·출처
    assert s[4]["source"] == "ai" and s[4]["query"] is None                # 출처 카드 = 모은 출처를 보일 뿐(검색 안 함)
    many = deep_mode.clean_plan({"sections": [{"title": f"t{i}", "shape": "용어 풀이"} for i in range(14)]})
    assert len(many["sections"]) == deep_mode.MAX_SECTIONS and many["title"] == "t0"
    with pytest.raises(ValueError):
        deep_mode.clean_plan({"sections": []})
    with pytest.raises(ValueError):
        deep_mode.clean_plan("JSON 아님")


def test_brief_text_defaults_and_more():
    t = deep_mode.brief_text({"누구에게": "처음 보는 사람", "꼭 넣을 것": ["숫자·그래프", "확인 문제"], "더": "그림은 빼 줘"})
    assert "- 누구에게: 처음 보는 사람" in t and "- 무엇에: 알아서" in t and "- 꼭 넣을 것: 숫자·그래프, 확인 문제" in t
    assert "그림은 빼 줘" in t and "꼭 따름" in t
    assert "더" not in deep_mode.brief_text({})


def test_make_plan_and_replan_prompt():
    c = FakeClient("```json\n" + json.dumps(PLAN, ensure_ascii=False) + "\n```", json.dumps(PLAN, ensure_ascii=False))
    out = deep_mode.make_plan(c, "반도체 수출 동향", {"무엇에": "보고·결정"}, day="2026년 10월 25일")
    assert out["model"] == deep_mode.EDITOR_MODEL and len(out["plan"]["sections"]) == 6                 # + 앱이 넣은 요약 그림
    assert out["plan"]["sections"][1]["shape"] == deep_mode.SUMMARY                                      # 주인공 바로 뒤
    assert out["estimate"]["credits"][0] < out["estimate"]["credits"][1] and out["estimate"]["seconds"][0] >= 25   # 공공 꼭지가 있으면 더 오래
    sys_, user = c.sent[0]["messages"][0]["content"], c.sent[0]["messages"][1]["content"]
    assert "2026년 10월 25일" in sys_ and "움직이는 카드(한 판에 하나까지" in sys_   # 4단계부터 원리 꼭지 = 움직이는 카드(시험 `test_part74`)
    assert "- 무엇에: 보고·결정" in user and "앞 계획" not in user
    deep_mode.make_plan(c, "반도체 수출 동향", {}, prev=out["plan"], fix="그래프 하나 더")
    user2 = c.sent[1]["messages"][1]["content"]
    assert "[앞 계획" in user2 and "그래프 하나 더" in user2 and "흐름" in user2
    with pytest.raises(ValueError):
        deep_mode.make_plan(c, "  ", {})


def test_summary_and_timeline_in_plan():
    """요약 그림(2026-10-25) — 편집장 모양 목록엔 없고 앱이 한 판에 하나(주인공 뒤), 계획 카드에서 ×로 뺀 뒤 다시 짜도 안 넣음, 꼭지 수 한도에 안 셈.
    타임라인 = 때 순서(숫자·날짜라 ai면 웹으로)."""
    c = FakeClient(json.dumps(PLAN, ensure_ascii=False), json.dumps(PLAN, ensure_ascii=False))
    out = deep_mode.make_plan(c, "반도체", {})
    sys_ = c.sent[0]["messages"][0]["content"]
    assert deep_mode.SUMMARY not in sys_ and "타임라인" in sys_
    pic = out["plan"]["sections"][1]
    assert pic["shape"] == deep_mode.SUMMARY and pic["source"] == "ai" and pic["query"] is None
    est = deep_mode.estimate(out["plan"]), deep_mode.estimate(deep_mode.clean_plan(PLAN))
    assert est[0]["credits"][0] - est[1]["credits"][0] >= 10 and est[0]["seconds"][0] > est[1]["seconds"][0]   # 그림 한 장 값·시간
    dropped = {**out["plan"], "sections": [s for s in out["plan"]["sections"] if s["shape"] != deep_mode.SUMMARY]}
    again = deep_mode.make_plan(c, "반도체", {}, prev=dropped, fix="그래프 하나 더")
    assert all(s["shape"] != deep_mode.SUMMARY for s in again["plan"]["sections"])                      # × 뺀 것은 그대로 빠짐
    two = deep_mode.clean_plan({"sections": [{"title": f"t{i}", "shape": "용어 풀이"} for i in range(12)] + [{"title": "그림", "shape": deep_mode.SUMMARY}, {"title": "그림2", "shape": deep_mode.SUMMARY}]})
    assert sum(s["shape"] == deep_mode.SUMMARY for s in two["sections"]) <= 1
    ten = deep_mode.clean_plan({"sections": [{"title": "그림", "shape": deep_mode.SUMMARY}] + [{"title": f"t{i}", "shape": "용어 풀이"} for i in range(12)]})
    assert len(ten["sections"]) == deep_mode.MAX_SECTIONS + 1                                          # 그림은 꼭지 수에 안 셈
    tl = deep_mode.clean_plan({"sections": [{"title": "연혁", "shape": "타임라인", "source": "ai"}]})["sections"][0]
    assert tl["source"] == "web" and tl["query"] == "연혁" and "events" in deep_mode.SCHEMA["타임라인"]


def test_board_material_reads_as_much_as_report():
    """재료 「이 칠판」 = 정리 문서와 같은 4만 자(2026-10-25 — 8천 자에서 잘렸음)."""
    plan = deep_mode.clean_plan({"sections": [{"title": "칠판", "shape": "접힌 메모", "source": "board"}]})
    board = "가" * 30_000 + "끝표시"
    assert "끝표시" in deep_mode.material_text(plan, {"sources": [], "materials": [None]}, board)
    assert deep_mode.MAX_BOARD == 40_000


def test_gather_numbers_sources_once_and_kr_falls_back_to_web():
    plan = deep_mode.clean_plan(PLAN)
    asked = []

    def exa(q):
        asked.append(q)
        return f"{q} 답 [1] 그리고 [2] · 없는 [9]", {"search_results": [{"title": "가", "url": "https://a"}, {"title": "나", "url": "https://b/" + q[:2]}]}
    mat = deep_mode.gather("k", plan, exa=exa, kr=lambda q: [])           # 공공 데이터가 비면 웹 검색
    assert sorted(asked) == sorted(["기억할 숫자", "반도체 수출 통계"])                # 출처 카드는 재료를 안 모음
    assert [s["n"] for s in mat["sources"]] == list(range(1, len(mat["sources"]) + 1))
    assert sum(1 for s in mat["sources"] if s["url"] == "https://a") == 1     # 같은 주소 = 같은 번호
    t = mat["materials"][1]["text"]
    assert re.findall(r"\[(\d+)\]", t) and "[9]" not in t                      # 없는 번호는 지움
    assert mat["materials"][2] is None                                           # ai 꼭지는 재료 없음
    bad = deep_mode.gather("k", plan, exa=lambda q: (_ for _ in ()).throw(RuntimeError("402")), kr=lambda q: [])
    assert bad["materials"][0]["text"] == "" and "402" in bad["materials"][0]["error"]


def test_kr_material_without_numbers_or_off_topic_switches_to_web():
    """0단계: 공공 데이터 숫자 꼭지 셋 중 하나만 맞음 — 표만 찾고 끝남(숫자 없음)·다른 품목 표(반도체에 열전자관) → 웹 검색으로 갈아탐."""
    find = {"suite": "kr-macro", "tool": "search_statistics", "args": {"query": "반도체"}, "text": '{"tables":[{"title":"수출물량지수"}]}'}
    empty = {"suite": "kr-macro", "tool": "get_statistics_data", "args": {}, "text": '{"rows":[],"returned":0}'}
    rows = {"suite": "kr-macro", "tool": "get_statistics_data", "args": {}, "text": '{"rows":[{"category":"열전자관냉음극관 및 광전과","value":4574763,"unit":"천달러"}]}'}
    assert not deep_mode.has_data([find]) and not deep_mode.has_data([find, empty]) and deep_mode.has_data([find, rows])
    assert deep_mode.has_data([{"suite": "korean-law", "tool": "get_law_article", "args": {}, "text": "제1조 …"}])   # JSON 아닌 조문 = 받은 것
    plan = {"sections": [{"title": "표만", "source": "kr", "query": "a"}, {"title": "다른 품목", "source": "kr", "query": "b"}, {"title": "맞음", "source": "kr", "query": "c"}]}
    by_q = {"a": [find, empty], "b": [find, rows], "c": [find, rows]}
    judged, webbed = [], []
    def fit(sec, text):
        judged.append(sec["title"])
        return (sec["title"] == "맞음", "품목이 반도체가 아님")
    mat = deep_mode.gather("k", plan, exa=lambda q: (webbed.append(q) or "웹 답 [1]", {"search_results": [{"title": "웹", "url": "https://w/" + q}]}), kr=lambda q: by_q[q], fit=fit)
    m = mat["materials"]
    assert sorted(judged) == ["다른 품목", "맞음"]                                      # 숫자 없는 건 검사 전에 걸러냄(공짜)
    assert sorted(webbed) == ["a", "b"]
    assert "숫자를 못 받음" in m[0]["switched"] and "꼭지와 다름 — 품목이 반도체가 아님" in m[1]["switched"]
    assert "switched" not in m[2] and "열전자관" in m[2]["text"]
    c = FakeClient('{"ok": false, "why": "다른 품목"}', "JSON 아님")
    assert deep_mode.fits(c, {"title": "반도체 수출"}, "열전자관 …") == (False, "다른 품목") and c.sent[0]["model"] == deep_mode.FIT_MODEL
    assert deep_mode.fits(c, {"title": "반도체 수출"}, "…") == (True, "")                # 검사 답이 틀어지면 재료를 막지 않음


def test_build_writes_bodies_and_fills_source_card():
    plan = deep_mode.clean_plan(PLAN)
    bodies = {"sections": [{"title": "기억할 숫자", "body": {"tiles": [["603억 달러", "9월", 1]]}}, {"title": "흐름 (바뀐 제목)", "body": {"rows": [["달", "수출"], ["1월", "60 [1]"]], "kind": "line"}},
                           {"title": "원리", "body": {"steps": [["a", "b"]]}}, {"title": "이상한 모양", "body": "글"}, {"title": "출처", "body": {}}]}
    c = FakeClient(json.dumps(bodies, ensure_ascii=False))
    out = deep_mode.build("k", c, "반도체", {"누구에게": "윗사람(보고)"}, plan, exa=lambda q: ("답 [1]", {"search_results": [{"title": "가", "url": "https://a"}]}), kr=lambda q: [])
    secs = out["plan"]["sections"]
    assert out["model"] == deep_mode.WRITER_MODEL and out["plan"]["sources"] == [{"n": 1, "title": "가", "url": "https://a"}]
    assert secs[0]["body"]["tiles"][0][0] == "603억 달러" and secs[1]["body"]["kind"] == "line"   # 제목이 바뀌어 와도 차례로
    assert secs[3]["body"] == {} and secs[4]["body"] == {"links": [1]}                              # 칸이 틀린 body는 비움, 출처 카드 = 쓴 번호
    w = c.sent[0]["messages"]
    assert "독자: 윗사람(보고)" in w[0]["content"] and "[출처 번호]\n[1] 가" in w[1]["content"]


def test_build_draws_summary_from_bodies_after_writing():
    """요약 그림 = 기자 본문을 다 쓴 뒤 그 본문으로(숫자·단계, [n]·굵게 표시는 뺌), 그림 칸 = 주소·크기. 그리기가 없거나 실패하면 그 꼭지만 안내(판은 지음)."""
    plan = deep_mode.with_summary(deep_mode.clean_plan(PLAN))
    bodies = {"sections": [{"title": "기억할 숫자", "body": {"tiles": [["603억 달러", "9월 **수출** [1]", 1]]}}, {"title": "한눈에 보기", "body": {}},
                           {"title": "흐름", "body": {"rows": [["달", "수출"], ["1월", "60 [1]"]], "kind": "line"}}, {"title": "원리", "body": {"steps": [["설계", "b"], ["제조", "c"]]}},
                           {"title": "이상한 모양", "body": {"md": "- x"}}, {"title": "출처", "body": {}}]}
    asked = []

    def image(prompt):
        asked.append(prompt)
        return {"img": "/api/img/공부/1_abc.png", "w": 1536, "h": 1152, "model": "flare", "credits": 11}
    web = lambda q: ("답 [1]", {"search_results": [{"title": "가", "url": "https://a"}]})
    out = deep_mode.build("k", FakeClient(json.dumps(bodies, ensure_ascii=False)), "반도체", {}, plan, exa=web, kr=lambda q: [], image=image)
    secs = out["plan"]["sections"]
    assert secs[1]["body"] == {"img": "/api/img/공부/1_abc.png", "w": 1536, "h": 1152, "model": "flare"}
    assert len(asked) == 1 and "603억 달러 9월 수출" in asked[0] and "설계 → 제조" in asked[0] and "[1]" not in asked[0].split("\n\n", 1)[1]
    assert "목록에 없는 숫자" in asked[0]
    out = deep_mode.build("k", FakeClient(json.dumps(bodies, ensure_ascii=False)), "반도체", {}, plan, exa=web, kr=lambda q: [], image=None)
    assert "error" in out["plan"]["sections"][1]["body"] and any("요약 그림" in m for m in out["missing"])
    bad = lambda p: (_ for _ in ()).throw(RuntimeError("HTTP 500"))
    out = deep_mode.build("k", FakeClient(json.dumps(bodies, ensure_ascii=False)), "반도체", {}, plan, exa=web, kr=lambda q: [], image=bad)
    assert "HTTP 500" in out["plan"]["sections"][1]["body"]["error"] and out["plan"]["sections"][0]["body"]["tiles"]   # 그림이 틀어져도 판은


def test_redo_summary_redraws_with_ask():
    plan = {**BUILT, "sections": [BUILT["sections"][0], {"title": "한눈에 보기", "shape": deep_mode.SUMMARY, "source": "ai", "size": "보통", "body": {"img": "/old.png", "w": 4, "h": 3}}] + BUILT["sections"][1:]}
    asked = []
    out = deep_mode.redo("k", FakeClient(), plan, [1], {}, "숫자를 더 크게", image=lambda p: asked.append(p) or {"img": "/new.png", "w": 4, "h": 3, "model": "flare"})
    assert out["sections"] == [{**plan["sections"][1], "i": 1, "body": {"img": "/new.png", "w": 4, "h": 3, "model": "flare"}}]
    assert "[고칠 점]\n숫자를 더 크게" in asked[0] and "옛 문단" in asked[0] and out["model"] == "flare"


BUILT = {"title": "반도체 수출", "headline": "한 판에", "sources": [{"n": 1, "title": "가", "url": "https://a"}, {"n": 2, "title": "나", "url": "https://b"}], "sections": [
    {"title": "핵심", "question": "왜?", "shape": "주인공 글", "source": "ai", "size": "주인공", "body": {"text": ["옛 문단"]}},
    {"title": "흐름", "question": "얼마?", "shape": "그래프", "chart": "꺾은선", "source": "web", "query": "반도체 수출 통계", "size": "보통",
     "body": {"rows": [["달", "수출"], ["1월", "60 [1]"]], "header": True, "kind": "line"}},
    {"title": "만져 보기", "shape": "움직이는 카드", "source": "ai", "size": "보통", "body": {"note": "막대를 끌면", "html": "<!doctype html><html><title>옛</title></html>", "card_model": "sol"}},
    {"title": "출처", "shape": "출처 카드", "source": "ai", "size": "작게", "body": {"links": [1, 2]}}]}


def test_redo_rewrites_only_picked_sections_and_continues_source_numbers():
    asked = []

    def exa(q):
        asked.append(q)
        return "새 숫자 [1] · 옛 주소 [2]", {"search_results": [{"title": "다", "url": "https://c"}, {"title": "가", "url": "https://a"}]}
    ans = {"sections": [{"title": "흐름", "change": "2월 숫자를 더했어요", "body": {"rows": [["달", "수출"], ["1월", "60 [1]"], ["2월", "70 [3]"]], "header": True, "kind": "line"}}]}
    c = FakeClient(json.dumps(ans, ensure_ascii=False))
    out = deep_mode.redo("k", c, BUILT, [1, 3], {"누구에게": "윗사람(보고)"}, "", exa=exa, kr=lambda q: [])
    assert [s["i"] for s in out["sections"]] == [1] and out["missing"] == []                  # 출처 카드는 다시 쓸 게 없어 뺌
    assert out["sections"][0]["body"]["rows"][2] == ["2월", "70 [3]"] and out["sections"][0]["shape"] == "그래프"
    assert out["sources"] == BUILT["sources"] + [{"n": 3, "title": "다", "url": "https://c"}]    # 같은 주소 = 같은 번호, 새 출처 = 뒤 번호
    assert out["changes"] == [{"i": 1, "title": "흐름", "text": "2월 숫자를 더했어요"}] and "change" not in out["sections"][0]   # 고친 것 한 줄 = 대화창 답에만(계획엔 안 넣음)
    assert asked == ["반도체 수출 통계"]                                                        # 고칠 말이 없으면 원래 검색 문장
    sys_, user = c.sent[0]["messages"][0]["content"], c.sent[0]["messages"][1]["content"]
    assert "고칠 꼭지만" in sys_ and "독자: 윗사람(보고)" in sys_ and "- 표:" not in sys_         # 모양 바꾸기 말이 없으면 그 모양 칸만
    assert "[지금 본문]" in user and "60 [1]" in user and deep_mode.MORE in user and "[판의 다른 꼭지 — 겹치지 않게] 핵심 · 만져 보기 · 출처" in user
    assert "새 숫자 [3] · 옛 주소 [1]" in user                                                   # 재료 속 번호도 판 번호로
    assert BUILT["sections"][1]["body"]["rows"][-1] == ["1월", "60 [1]"]                         # 들어온 판은 안 건드림


def test_redo_shape_change_only_when_asked_and_bad_body_keeps_old():
    table = {"sections": [{"title": "흐름", "shape": "표", "body": {"rows": [["", "수출"], ["1월", "60 [1]"]], "header": True}}]}
    c, asked = FakeClient(json.dumps(table, ensure_ascii=False)), []
    out = deep_mode.redo("k", c, BUILT, [1], {}, "표로 바꿔 줘", exa=lambda q: (asked.append(q) or "", {"search_results": []}), kr=lambda q: [])
    s = out["sections"][0]
    assert s["shape"] == "표" and s["chart"] is None and "- 표:" in c.sent[0]["messages"][0]["content"]
    assert asked == ["반도체 수출 통계 표로 바꿔 줘"] and "[새 재료 없음" in c.sent[0]["messages"][1]["content"]   # 재료 다시 = 검색 문장 + 고칠 말
    c2 = FakeClient(json.dumps(table, ensure_ascii=False))
    assert deep_mode.redo("k", c2, BUILT, [0], {}, "", exa=None)["missing"] == ["핵심"]           # 주인공 글에 표 칸(text 없음) = 그대로 두고 알림
    c3 = FakeClient(json.dumps({"sections": [{"title": "핵심", "shape": "움직이는 카드", "body": {"text": ["새"]}}]}, ensure_ascii=False))
    assert deep_mode.redo("k", c3, BUILT, [0], {}, "카드로 바꿔")["sections"][0]["shape"] == "주인공 글"   # 카드로는 못 바꿈
    with pytest.raises(ValueError):
        deep_mode.redo("k", c3, BUILT, [3], {}, "")


def test_redo_card_revises_old_html():
    c = FakeClient("<!doctype html><html><title>새 카드</title><body>x</body></html>")
    out = deep_mode.redo("k", c, BUILT, [2], {}, "글자를 크게")
    b = out["sections"][0]["body"]
    assert "새 카드" in b["html"] and b["note"] == "막대를 끌면" and out["model"] == deep_mode.live_card.LIVE_MODEL
    user = c.sent[0]["messages"][1]["content"]
    assert "[앞 카드]" in user and "<title>옛</title>" in user and "글자를 크게" in user        # 대화창 4-3과 같은 고치기 지시문


def test_web_and_server_agree_on_shapes_and_brief():
    """칠판(`deepboard.js`)이 그릴 줄 아는 모양만 계획에 · 대화창 질문지(`deepchat.jsx`) 질문 = 서버가 읽는 질문."""
    board = open(os.path.join(ROOT, "web", "src", "next", "deepboard.js"), encoding="utf-8").read()
    for sh in deep_mode.SHAPES:
        assert f"case '{sh}'" in board, sh
    chat = open(os.path.join(ROOT, "web", "src", "next", "deepchat.jsx"), encoding="utf-8").read()
    qs = re.findall(r"^  \['([^']+)', \[", chat, re.M)
    assert qs == ["누구에게", "무엇에", "깊이", "꼭 넣을 것", "재료"]
    for q in qs:
        assert f"- {q}:" in deep_mode.brief_text({})


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    seen = []

    def fake_plan(client, topic, brief, *, prev=None, fix="", **_k):
        seen.append(("plan", topic, brief, prev, fix))
        p = deep_mode.clean_plan(PLAN)
        return {"plan": p, "estimate": deep_mode.estimate(p), "model": "opus", "elapsed": 0.1}

    def fake_build(key, client, topic, brief, plan, *, base_url="", board="", **_k):
        seen.append(("build", topic, plan, board))
        return {"plan": {**plan, "sources": [], "sections": [{**s, "body": {}} for s in plan["sections"]]}, "model": "sonnet", "elapsed": 0.2, "missing": []}
    monkeypatch.setattr(srv.deep_mode, "make_plan", fake_plan)
    monkeypatch.setattr(srv.deep_mode, "build", fake_build)

    def fake_redo(key, client, plan, idx, brief, ask="", *, base_url="", board="", **_k):
        seen.append(("section", idx, ask, board))
        return {"sections": [{"i": idx[0], **plan["sections"][idx[0]], "body": {"text": ["새"]}}], "sources": plan.get("sources") or [], "model": "sonnet", "elapsed": 0.1, "missing": []}
    monkeypatch.setattr(srv.deep_mode, "redo", fake_redo)
    bal = iter(range(1000, 0, -7))   # 부를 때마다 7씩 줄어드는 잔액 = 일 하나에 7크레딧
    monkeypatch.setattr(srv.gw, "get_credit_balance", lambda *a, **k: (float(next(bal)), 40000.0))
    monkeypatch.setattr(srv.time, "sleep", lambda s: None)
    monkeypatch.setattr(srv.gw, "_client", lambda *a, **k: None)
    monkeypatch.setattr(srv.board_chat, "models", lambda *a, **k: {"default": "m", "featured": {}})
    srv._MODELS.clear()
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    with open(tmp_path / "공부.ecad", "w", encoding="utf-8") as f:
        json.dump({"items": [{"uid": "m1", "type": "memo", "lines": [{"t": "송신기 점검 메모"}], "pos": [0, 0], "rect": [0, 0, 100, 40]}]}, f, ensure_ascii=False)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def _post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


def test_server_deep_plan_build_and_models(server):
    base, seen = server
    with urllib.request.urlopen(base + "/api/models") as r:
        assert json.loads(r.read())["jobs"]["deep"] == deep_mode.EDITOR_MODEL   # 대화창 「+ › 딥모드」가 보이는 조건
    msgs = [{"role": "user", "content": "반도체"}]
    out = _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "plan", "topic": "반도체", "brief": {"깊이": "보통"}}, "messages": msgs})
    assert out["kind"] == "deep" and len(out["plan"]["sections"]) == 5 and out["estimate"]["credits"]
    assert out["credits"] == 7.0                                                # 쓴 크레딧 = 일 앞뒤 잔액 차이(대화 모델 답엔 값이 없음)
    assert seen[-1] == ("plan", "반도체", {"깊이": "보통"}, None, "")
    _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "plan", "topic": "반도체", "brief": {}, "prev": out["plan"], "fix": "하나 더"}, "messages": msgs})
    assert seen[-1][3] == out["plan"] and seen[-1][4] == "하나 더"
    plan = {**out["plan"], "sections": out["plan"]["sections"] + [{"title": "칠판에서", "shape": "접힌 메모", "source": "board"}]}
    got = _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "build", "topic": "반도체", "brief": {}, "plan": plan, "style": "news"}, "messages": msgs})
    assert got["kind"] == "deep" and got["model"] == "sonnet" and len(got["plan"]["sections"]) == 6
    assert "송신기 점검 메모" in seen[-1][3]                                    # 재료가 「이 칠판」인 꼭지가 있으면 칠판 글을 같이
    sec = _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "section", "plan": plan, "idx": [0], "ask": "더 쉽게", "brief": {}}, "messages": msgs})
    assert got["credits"] == 7.0 and sec["credits"] == 7.0                      # 만들기·꼭지 다시 쓰기도
    assert sec["step"] == "section" and sec["sections"][0]["i"] == 0 and seen[-1][:3] == ("section", [0], "더 쉽게") and seen[-1][3] == ""   # 고른 꼭지가 칠판 재료가 아니면 칠판 글 안 읽음
    _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "section", "plan": plan, "idx": [5], "brief": {}}, "messages": msgs})
    assert "송신기 점검 메모" in seen[-1][3]
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "??"}, "messages": msgs})
    assert e.value.code == 400


def test_server_deep_image_saves_picture_next_to_board(server, monkeypatch):
    """서버 요약 그림 = KAIROS 그림 한 장 → 칠판 옆 `<이름>.img/`, 칠판엔 주소·실제 크기만. 칠판 이름이 없으면 그리기 없음."""
    import io
    import server as srv
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (40, 30), "white").save(buf, "PNG")
    calls = []
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, **kw: calls.append((prompt, kw)) or {"images": [(buf.getvalue(), "png")], "model": "flare", "credits": 11})

    def build(key, client, topic, brief, plan, *, image=None, **_k):
        return {"plan": {**plan, "sources": [], "sections": [{**s, "body": image("요약 지시") if s.get("shape") == deep_mode.SUMMARY else {}} for s in plan["sections"]]}, "model": "sonnet", "elapsed": 0.1, "missing": []}
    monkeypatch.setattr(srv.deep_mode, "build", build)
    base, _ = server
    plan = {"title": "t", "sections": [{"title": "그림", "shape": deep_mode.SUMMARY}]}
    got = _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "build", "topic": "t", "brief": {}, "plan": plan}, "messages": [{"role": "user", "content": "t"}]})
    body = got["plan"]["sections"][0]["body"]
    assert body["w"] == 40 and body["h"] == 30 and body["model"] == "flare" and calls[0][1]["n"] == 1
    with urllib.request.urlopen(base + body["img"].replace("공부", urllib.parse.quote("공부"))) as r:
        assert r.read() == buf.getvalue()
    assert srv.Handler.__dict__["_deep_image"](SimpleNamespace(_name=lambda raw: ""), "", "k", "b") is None
