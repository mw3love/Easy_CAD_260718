"""§8 항목61 ⓒ(2026-10-17) — 웹 칠판 KAIROS 대화: 메시지 만들기(`easycad/ai/board_chat.py`)와 서버 길목(`web/server.py`).

KAIROS는 부르지 않는다(가짜 클라이언트·가짜 `board_chat.chat`) — 실제 호출은 브라우저에서 따로 확인.
"""
import json
import os
import sys
import threading
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
    assert _req(base + "/api/chatlog/공부") == (200, log)
    assert os.path.exists(data / "공부.chat.json") and not os.path.exists(data / "공부.json")
    assert _req(base + "/api/chatlog/a.b")[0] == 400   # 점 든 이름 금지 — 칠판 이름과 파일이 겹치지 않게


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
    assert board_chat.guess_kind("최근 이 메모 정리해 줘", has_context=True) == "chat"   # 칠판에서 고른 글을 다루는 말


def test_cited_sources_keeps_only_used_numbers_with_titles():
    raw = {"citations": ["https://a.kr/1", "https://b.kr/2", "https://c.kr/3", "https://d.kr/4"],
           "search_results": [{"url": "https://b.kr/2", "title": "둘째 기사", "date": "2026-10-19"}, {"url": "https://d.kr/4", "title": "넷째"}]}
    out = board_chat.cited_sources("결론이에요.[2] 그리고 또.[4][2] 없는 번호[9]", raw)
    assert out == [{"n": 2, "url": "https://b.kr/2", "title": "둘째 기사", "date": "2026-10-19"}, {"n": 4, "url": "https://d.kr/4", "title": "넷째", "date": ""}]
    assert [s["n"] for s in board_chat.cited_sources("번호 없음", raw)] == [1, 2, 3]   # 번호가 없으면 앞 셋


def test_chat_search_switches_model_and_returns_sources():
    seen = {}

    class Resp(SimpleNamespace):
        def model_dump(self):
            return {"citations": ["https://x.kr/a", "https://y.kr/b"], "search_results": [{"url": "https://y.kr/b", "title": "B"}]}

    def create(**kw):
        seen.update(kw)
        return Resp(choices=[SimpleNamespace(message=SimpleNamespace(content="요약이에요.[2]"))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out = board_chat.chat("k", [{"role": "user", "content": "오늘 뉴스 찾아줘"}], model="m-1", client=fake)
    assert seen["model"] == board_chat.SEARCH_MODEL and out["kind"] == "search" and out["model"] == board_chat.SEARCH_MODEL
    assert "출처 번호" in seen["messages"][0]["content"]
    assert out["sources"] == [{"n": 2, "url": "https://y.kr/b", "title": "B", "date": ""}]
    out = board_chat.chat("k", [{"role": "user", "content": "오늘 뉴스 찾아줘"}], model="m-1", kind="chat", client=fake)   # 대화창에서 바꿔 다시
    assert seen["model"] == "m-1" and out["kind"] == "chat" and "sources" not in out
