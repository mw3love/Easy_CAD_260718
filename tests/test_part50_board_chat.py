"""§8 항목61 ⓒ(2026-10-17) — 웹 칠판 KAIROS 대화: 메시지 만들기(`easycad/ai/board_chat.py`)와 서버 길목(`web/server.py`).

KAIROS는 부르지 않는다(가짜 클라이언트·가짜 `board_chat.chat`) — 실제 호출은 브라우저에서 따로 확인.
"""
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

from easycad.ai import board_chat  # noqa: E402


def test_messages_carry_board_context_per_turn_and_start_with_question():
    hist = [{"role": "assistant", "content": "잘린 앞 답"},
            {"role": "user", "content": "이거 뭐야", "context": "- PTP 카드"},
            {"role": "assistant", "content": "시계 규약"},
            {"role": "error", "content": "무시"},
            {"role": "user", "content": "더 짧게"}]
    msgs = board_chat.build_messages(hist)
    assert msgs[0]["role"] == "system"
    assert [m["role"] for m in msgs[1:]] == ["user", "assistant", "user"]   # 답으로 시작하는 앞부분·오류는 뺀다
    assert msgs[1]["content"].startswith("[칠판에서 고른 내용]\n- PTP 카드") and msgs[1]["content"].endswith("이거 뭐야")
    assert msgs[3]["content"] == "더 짧게"
    with pytest.raises(ValueError):
        board_chat.build_messages([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])


def test_chat_sends_whole_conversation_to_chosen_model():
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="답"))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out = board_chat.chat("k", [{"role": "user", "content": "질문"}], model="m-1", context="고른 글", client=fake)
    assert out["content"] == "답" and out["model"] == "m-1"
    assert seen["model"] == "m-1" and "고른 글" in seen["messages"][-1]["content"]


def test_chat_marks_answer_cut_at_length_limit():
    # 2026-10-27 길이 상한에 걸린 답은 cut — 대화창이 「끊겼어요 · 이어서 쓰기」를 보임(끝난 답엔 없음)
    def fake(reason):
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="긴 연설문…"), finish_reason=reason)]))))
    assert board_chat.chat("k", [{"role": "user", "content": "연설문 길게 써 줘"}], model="m", kind="chat", client=fake("length"))["cut"] is True
    assert "cut" not in board_chat.chat("k", [{"role": "user", "content": "연설문 길게 써 줘"}], model="m", kind="chat", client=fake("stop"))


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    calls = []

    def fake_chat(key, messages, *, model, context="", kind="", board_refs=None, base_url=""):
        board_chat.build_messages(messages, context)   # 진짜와 같은 검사(질문 없으면 ValueError)
        calls.append((key, messages, model))
        return {"content": f"{len(messages)}번째 답", "model": model, "elapsed": 0.1}
    monkeypatch.setattr(srv.board_chat, "chat", fake_chat)
    srv.Handler.data_dir = str(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", calls, tmp_path
    httpd.shutdown()


def _req(url, method="GET", body=None):
    url = urllib.parse.quote(url, safe=":/")
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_server_chat_and_chat_log_round_trip(server):
    base, calls, data = server
    code, out = _req(base + "/api/chat", "POST", {"model": "m-2", "messages": [{"role": "user", "content": "안녕"}]})
    assert code == 200 and out == {"content": "1번째 답", "model": "m-2", "elapsed": 0.1}
    assert calls[0][0] == "test-key"   # 키는 서버에서만 — 브라우저 요청엔 없다
    # 대화 기록: 칠판마다 따로, 칠판 저장 파일과 안 섞인다
    assert _req(base + "/api/chatlog/공부")[0] == 404
    log = {"messages": [{"role": "user", "content": "안녕"}, {"role": "assistant", "content": "1번째 답", "cardId": "shape:x"}]}
    assert _req(base + "/api/chatlog/공부", "PUT", log)[0] == 200
    assert _req(base + "/api/chatlog/공부") == (200, {**log, "rev": 1})   # 판 번호 = 두 창 합치기(2026-10-26)
    assert os.path.exists(data / "공부.chat.json") and not os.path.exists(data / "공부.json")
    assert _req(base + "/api/chatlog/a.b")[0] == 400   # 점 든 이름 금지 — 칠판 이름과 파일이 겹치지 않게


def test_server_uses_my_key_header_and_never_stores_it(server):
    """「🔑 내 키」(2026-10-20) — 머리말 키가 있으면 그것으로 부르고, 이상한 값이면 서버 키. 키는 파일 어디에도 안 남음."""
    base, calls, data = server

    def ask(key):
        r = urllib.request.Request(base + "/api/chat", data=json.dumps({"messages": [{"role": "user", "content": "x"}]}).encode(), method="POST",
                                   headers={"Content-Type": "application/json", "X-Kairos-Key": key})
        with urllib.request.urlopen(r) as resp:
            return resp.status
    assert ask("my-own-key-1234") == 200 and calls[-1][0] == "my-own-key-1234"
    assert ask("short") == 200 and calls[-1][0] == "test-key"   # 키 모양이 아니면 무시
    log = {"messages": [], "past": [{"at": 1, "title": "지난 질문", "messages": [{"role": "user", "content": "지난 질문"}]}]}
    assert _req(base + "/api/chatlog/키", "PUT", log)[0] == 200 and _req(base + "/api/chatlog/키") == (200, {**log, "rev": 1})   # 지난 대화도 그대로 왕복
    for f in data.iterdir():
        assert b"my-own-key-1234" not in f.read_bytes()


def test_server_credits_use_request_key(server, monkeypatch):
    """대화창 머리줄 「남은 크레딧」(2026-10-21) — 이 요청의 키로(「🔑 내 키」면 그 사람 것), 못 받으면 502(화면은 숫자 안 보임)."""
    import server as srv
    base, _, _ = server
    seen = []
    monkeypatch.setattr(srv.gw, "get_credit_balance", lambda key, base_url="": seen.append(key) or (18401.6, 40000.0))
    assert _req(base + "/api/credits") == (200, {"remaining": 18401.6, "quota": 40000.0}) and seen == ["test-key"]
    r = urllib.request.Request(base + "/api/credits", headers={"X-Kairos-Key": "my-own-key-1234"})
    with urllib.request.urlopen(r) as resp:
        assert resp.status == 200 and seen[-1] == "my-own-key-1234"

    def boom(*_a, **_k):
        raise RuntimeError("HTTP 401")
    monkeypatch.setattr(srv.gw, "get_credit_balance", boom)
    assert _req(base + "/api/credits") == (502, {"error": "HTTP 401"})


def test_server_chat_errors_are_shown_not_hidden(server, monkeypatch):
    base, _, _ = server
    import server as srv
    assert _req(base + "/api/chat", "POST", {"messages": []})[0] == 400   # 질문 없음

    def boom(*a, **k):
        raise RuntimeError("HTTP 429 quota")
    monkeypatch.setattr(srv.board_chat, "chat", boom)
    code, out = _req(base + "/api/chat", "POST", {"messages": [{"role": "user", "content": "x"}]})
    assert code == 502 and "429" in out["error"]
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "")
    code, out = _req(base + "/api/chat", "POST", {"messages": [{"role": "user", "content": "x"}]})
    assert code == 503 and "키" in out["error"]


# ── 웹 검색(§8 항목61 ② 담는 법, 2026-10-19) — 종류 짐작·쓰인 번호의 출처만 ──
def test_guess_kind_search_words_but_board_text_stays_chat():
    assert board_chat.guess_kind("오늘 KBS 뉴스 알려줘") == "search"
    assert board_chat.guess_kind("최신 ATSC 3.0 동향") == "search"
    assert board_chat.guess_kind("PTP가 뭐야") == "chat"
    assert board_chat.guess_kind("송신소 점검 순서 알려줘") == "chat"
    assert board_chat.guess_kind("최근 이 메모 요약해 줘", has_context=True) == "chat"   # 칠판에서 고른 글을 다루는 말
    assert board_chat.guess_kind("최근 이 메모 정리해 줘", has_context=True) == "report"   # 「정리해 줘」 = 정리 문서(2026-10-19 사용자)


def test_cited_sources_keeps_only_used_numbers_with_titles():
    raw = {"citations": ["https://a.kr/1", "https://b.kr/2", "https://c.kr/3", "https://d.kr/4"],
           "search_results": [{"url": "https://b.kr/2", "title": "둘째 기사", "date": "2026-10-19"}, {"url": "https://d.kr/4", "title": "넷째"}]}
    out = board_chat.cited_sources("결론이에요.[2] 그리고 또.[4][2] 없는 번호[9]", raw)
    assert out == [{"n": 2, "url": "https://b.kr/2", "title": "둘째 기사", "date": "2026-10-19"}, {"n": 4, "url": "https://d.kr/4", "title": "넷째", "date": ""}]
    assert [s["n"] for s in board_chat.cited_sources("번호 없음", raw)] == [1, 2, 3]   # 번호가 없으면 앞 셋


def test_renumber_sources_makes_numbers_sequential():
    src = [{"n": 1, "url": "a"}, {"n": 6, "url": "b"}, {"n": 10, "url": "c"}]
    text, out = board_chat.renumber_sources("흐림.[1][6][10] 우산.[6] 없는 번호[9]", src)
    assert text == "흐림.[1][2][3] 우산.[2] 없는 번호[9]"
    assert [(s["n"], s["url"]) for s in out] == [(1, "a"), (2, "b"), (3, "c")]


def test_chat_search_switches_model_and_returns_sources():
    # 검색 = Exa(`/exa/answer/`, 2026-10-21) — 질문 한 줄 + 지시문(오늘 날짜·앞 대화), 출처는 Exa `citations`
    seen, calls = {}, []

    class Http:
        def post(self, url, headers, json, timeout):
            seen.update(url=url, **json)
            return SimpleNamespace(status_code=200, json=lambda: {"answer": "요약이에요.[2]", "citations": [
                {"url": "https://x.kr/a", "title": "A"}, {"url": "https://y.kr/b", "title": "B", "publishedDate": "2026-10-20T01:00:00Z"}]})

    def create(**kw):   # 이어 묻는 말 바꾸기(REWRITE_MODEL)는 「전주 」를 앞에 붙여 흉내
        calls.append(kw)
        last = kw["messages"][-1]["content"]
        text = "전주 " + last.split("[마지막 질문]\n", 1)[1] if kw["model"] == board_chat.REWRITE_MODEL else "대화 답"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    hist = [{"role": "user", "content": "전주 날씨"}, {"role": "assistant", "content": "어느 날이요?"}, {"role": "user", "content": "내일 날씨 찾아줘"}]
    out = board_chat.chat("k", hist, model="m-1", client=fake, http=Http(), base_url="https://g")
    assert seen["url"] == "https://g/exa/answer/" and out["kind"] == "search" and out["model"] == board_chat.SEARCH_MODEL
    assert [c["model"] for c in calls] == [board_chat.REWRITE_MODEL]   # 앞 대화가 있으면 혼자 통하는 검색 문장으로(Exa는 앞 대화를 못 봄)
    assert re.match(r"전주 내일\(\d{4}년 \d+월 \d+일\(.\)\) 날씨 찾아줘", seen["query"])   # 「내일」에 날짜를 붙임
    assert "출처 번호" in seen["systemPrompt"] and "오늘은 " in seen["systemPrompt"] and "나: 전주 날씨" in seen["systemPrompt"]
    assert out["sources"] == [{"n": 1, "url": "https://y.kr/b", "title": "B", "date": "2026-10-20"}] and out["content"] == "요약이에요.[1]"   # 번호는 1부터 다시
    out = board_chat.chat("k", hist, model="m-1", kind="chat", client=fake, http=Http())   # 대화창에서 바꿔 다시
    assert calls[-1]["model"] == "m-1" and out["kind"] == "chat" and "sources" not in out
    calls.clear()
    board_chat.chat("k", hist[-1:], model="m-1", kind="search", client=fake, http=Http())
    assert not calls and seen["query"].startswith("내일(")   # 처음 묻는 말은 바꾸지 않음


def test_search_falls_back_when_exa_fails():
    class Down:
        def post(self, url, headers, json, timeout):
            return SimpleNamespace(status_code=402, text="no credits")

    class Resp(SimpleNamespace):
        def model_dump(self):
            return {"citations": ["https://x.kr/a"], "search_results": [{"url": "https://x.kr/a", "title": "A"}]}
    seen = {}

    def create(**kw):
        seen.update(kw)
        return Resp(choices=[SimpleNamespace(message=SimpleNamespace(content="옛 검색 답.[1]"))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out = board_chat.chat("k", [{"role": "user", "content": "오늘 뉴스 찾아줘"}], model="m-1", client=fake, http=Down())
    assert seen["model"] == board_chat.SEARCH_FALLBACK and out["model"] == board_chat.SEARCH_FALLBACK and out["sources"][0]["title"] == "A"
    assert seen["messages"][-1]["content"].startswith("오늘(") and "오늘은 " in seen["messages"][0]["content"]


def test_absolute_dates():
    now = time.mktime((2026, 10, 21, 1, 0, 0, 0, 0, -1))
    assert board_chat.absolute_dates("내일 전주 날씨, 모레는?", now) == "내일(2026년 10월 22일(목)) 전주 날씨, 모레(2026년 10월 23일(금))는?"
    assert board_chat.absolute_dates("어제 뉴스", now) == "어제(2026년 10월 20일(화)) 뉴스"
    assert board_chat.absolute_dates("내일(10월 22일) 날씨", now) == "내일(10월 22일) 날씨"   # 이미 날짜가 있으면 그대로