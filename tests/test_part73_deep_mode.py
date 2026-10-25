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
    assert out["model"] == deep_mode.EDITOR_MODEL and len(out["plan"]["sections"]) == 5
    assert out["estimate"]["credits"][0] < out["estimate"]["credits"][1] and out["estimate"]["seconds"][0] >= 25   # 공공 꼭지가 있으면 더 오래
    sys_, user = c.sent[0]["messages"][0]["content"], c.sent[0]["messages"][1]["content"]
    assert "2026년 10월 25일" in sys_ and "움직이는 카드(한 판에 하나까지" in sys_   # 4단계부터 원리 꼭지 = 움직이는 카드(시험 `test_part74`)
    assert "- 무엇에: 보고·결정" in user and "앞 계획" not in user
    deep_mode.make_plan(c, "반도체 수출 동향", {}, prev=out["plan"], fix="그래프 하나 더")
    user2 = c.sent[1]["messages"][1]["content"]
    assert "[앞 계획" in user2 and "그래프 하나 더" in user2 and "흐름" in user2
    with pytest.raises(ValueError):
        deep_mode.make_plan(c, "  ", {})


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
    ans = {"sections": [{"title": "흐름", "body": {"rows": [["달", "수출"], ["1월", "60 [1]"], ["2월", "70 [3]"]], "header": True, "kind": "line"}}]}
    c = FakeClient(json.dumps(ans, ensure_ascii=False))
    out = deep_mode.redo("k", c, BUILT, [1, 3], {"누구에게": "윗사람(보고)"}, "", exa=exa, kr=lambda q: [])
    assert [s["i"] for s in out["sections"]] == [1] and out["missing"] == []                  # 출처 카드는 다시 쓸 게 없어 뺌
    assert out["sections"][0]["body"]["rows"][2] == ["2월", "70 [3]"] and out["sections"][0]["shape"] == "그래프"
    assert out["sources"] == BUILT["sources"] + [{"n": 3, "title": "다", "url": "https://c"}]    # 같은 주소 = 같은 번호, 새 출처 = 뒤 번호
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
    assert seen[-1] == ("plan", "반도체", {"깊이": "보통"}, None, "")
    _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "plan", "topic": "반도체", "brief": {}, "prev": out["plan"], "fix": "하나 더"}, "messages": msgs})
    assert seen[-1][3] == out["plan"] and seen[-1][4] == "하나 더"
    plan = {**out["plan"], "sections": out["plan"]["sections"] + [{"title": "칠판에서", "shape": "접힌 메모", "source": "board"}]}
    got = _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "build", "topic": "반도체", "brief": {}, "plan": plan, "style": "news"}, "messages": msgs})
    assert got["kind"] == "deep" and got["model"] == "sonnet" and len(got["plan"]["sections"]) == 6
    assert "송신기 점검 메모" in seen[-1][3]                                    # 재료가 「이 칠판」인 꼭지가 있으면 칠판 글을 같이
    sec = _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "section", "plan": plan, "idx": [0], "ask": "더 쉽게", "brief": {}}, "messages": msgs})
    assert sec["step"] == "section" and sec["sections"][0]["i"] == 0 and seen[-1][:3] == ("section", [0], "더 쉽게") and seen[-1][3] == ""   # 고른 꼭지가 칠판 재료가 아니면 칠판 글 안 읽음
    _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "section", "plan": plan, "idx": [5], "brief": {}}, "messages": msgs})
    assert "송신기 점검 메모" in seen[-1][3]
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base + "/api/chat", {"board": "공부", "kind": "deep", "deep": {"step": "??"}, "messages": msgs})
    assert e.value.code == 400
