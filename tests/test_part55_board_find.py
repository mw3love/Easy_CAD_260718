"""§8 항목61 ③-2(2026-10-19) — 웹 칠판 「뜻으로 찾기」: 칠판 글 뽑기·뜻 점수·낱말 가산·뜻 숫자 모아 두기(`easycad/ai/board_find.py`),
「칠판에서」 답하기(`board_chat` kind="board")와 서버 길목(`/api/find`, `/api/chat`의 board).

KAIROS는 부르지 않는다 — 가짜 임베딩(글에 든 낱말 묶음으로 숫자를 만듦). 실제 호출은 브라우저에서 따로 확인.
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

from easycad.ai import board_chat, board_find  # noqa: E402

# 뜻 묶음 — 같은 묶음 낱말이면 같은 축(「송신 장비 고장」과 「송신기 이상 보고」가 낱말은 달라도 가깝게)
AXES = [("송신", "송출"), ("고장", "이상", "저하"), ("점심", "찌개", "메뉴"), ("UHD", "일정"), ("회의",)]


class FakeEmb:
    def __init__(self):
        self.calls = []
        self.embeddings = SimpleNamespace(create=self.create)

    def create(self, model, input):
        self.calls.append(list(input))
        vec = lambda t: [float(any(w in t for w in ax)) for ax in AXES] + [0.05]
        return SimpleNamespace(data=[SimpleNamespace(embedding=vec(t)) for t in input])


DOC = {"format": "easycad-doc", "items": [
    {"type": "memo", "uid": "m1", "lines": [{"k": "h1", "t": "송신기 이상 보고"}, {"k": "p", "t": "2번 출력 저하"}, {"k": "hr", "t": ""}]},
    {"type": "memo", "uid": "m2", "lines": [{"k": "p", "t": "점심 메뉴: 김치찌개"}]},
    {"type": "rect", "uid": "r1", "label": {"text": "UHD 일정 회의"}},
    {"type": "table", "uid": "t1", "cells": [["항목", "값"], ["전원", "220V"]]},
    {"type": "web", "uid": "w1", "title": "PTP 시계", "url": "https://x.kr/ptp", "desc": ""},
    {"type": "rect", "label": {"text": "이름표 없는 상자"}},
    {"type": "rect", "uid": "r2"},
]}


def test_item_texts_cover_kinds_and_skip_unnamed_or_empty():
    items = {it["uid"]: it["text"] for it in board_find.board_items(DOC)}
    assert set(items) == {"m1", "m2", "r1", "t1", "w1"}   # 이름표 없는 것·글 없는 것은 뺌
    assert items["m1"] == "송신기 이상 보고\n2번 출력 저하"
    assert items["t1"] == "항목 | 값\n전원 | 220V" and "https://x.kr/ptp" in items["w1"]
    assert board_find.item_text({"type": "image", "uid": "g1", "alt": "송신탑 그려줘"}) == "송신탑 그려줘"   # 그림 = 만든 요청(2026-10-20)


def test_find_by_meaning_and_word_bonus_and_cache(tmp_path):
    emb, cache = FakeEmb(), str(tmp_path / "b.emb.json")
    res = board_find.find(emb, DOC, "송신 장비 고장", cache_path=cache)
    assert res[0]["uid"] == "m1" and res[0]["kind"] == "메모"                # 낱말이 달라도 뜻으로 1등
    assert "m2" not in [r["uid"] for r in res]                              # 관련 없는 메모는 빠짐
    assert len(emb.calls[0]) == 6                                           # 글 다섯 + 질문
    res = board_find.find(emb, DOC, "220V", cache_path=cache)               # 뜻 숫자는 모아 둔 것 — 질문만 새로
    assert emb.calls[1] == ["220V"] and res[0]["uid"] == "t1"               # 낱말이 그대로 있으면 뜻 점수가 낮아도 넣음
    doc2 = {"items": DOC["items"][:1] + [{"type": "memo", "uid": "m3", "lines": [{"k": "p", "t": "송출 장비 점검"}]}]}
    board_find.find(emb, doc2, "점검", cache_path=cache)
    assert emb.calls[2] == ["송출 장비 점검", "점검"]                         # 바뀐 글만 다시
    assert len(json.load(open(cache, encoding="utf-8"))["vecs"]) == 2        # 지워진 글의 숫자는 버림


def test_guess_board_and_chat_board_returns_cited_refs():
    assert board_chat.guess_kind("지난번 송신소 점검 뭐였지?") == "board"
    assert board_chat.guess_kind("우리가 정리한 UHD 일정") == "board"
    assert board_chat.guess_kind("오늘 뉴스") == "search" and board_chat.guess_kind("PTP가 뭐야") == "chat"
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="2번 송신기 출력이 떨어졌어요.[칠판 2]"))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    refs = [{"uid": "r1", "kind": "상자", "text": "UHD 일정 회의"}, {"uid": "m1", "kind": "메모", "text": "송신기 이상 보고"}]
    out = board_chat.chat("k", [{"role": "user", "content": "지난번 송신기 뭐였지?"}], model="m-1", board_refs=refs, client=fake)
    assert out["kind"] == "board" and seen["model"] == "m-1"
    assert "[칠판 2] (메모) 송신기 이상 보고" in seen["messages"][-1]["content"] and "칠판에서 못 찾았어요" in seen["messages"][0]["content"]
    assert out["refs"] == [{"n": 2, "uid": "m1", "kind": "메모", "text": "송신기 이상 보고"}]


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    emb = FakeEmb()
    monkeypatch.setattr(srv.gw, "_client", lambda *a, **k: emb)
    seen = []

    def fake_chat(key, messages, *, model, context="", kind="", board_refs=None, base_url=""):
        seen.append((kind, board_refs))
        return {"content": "답", "model": model, "elapsed": 0.1, "kind": kind}
    monkeypatch.setattr(srv.board_chat, "chat", fake_chat)
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    (tmp_path / "공부.ecad").write_text(json.dumps(DOC, ensure_ascii=False), encoding="utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen, tmp_path
    httpd.shutdown()


def _post(url, body):
    r = urllib.request.Request(urllib.parse.quote(url, safe=":/"), data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


def test_server_find_and_chat_board(server):
    import urllib.parse  # noqa: F401
    base, seen, data = server
    out = _post(base + "/api/find/공부", {"q": "송신 장비 고장"})
    assert out["results"][0]["uid"] == "m1" and os.path.exists(data / "공부.emb.json")
    assert _post(base + "/api/find/없는칠판", {"q": "x"}) == {"results": []}
    _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "지난번 송신기 고장 뭐였지?"}]})
    kind, refs = seen[-1]
    assert kind == "board" and refs[0]["uid"] == "m1"                        # 서버가 짐작하고 칠판에서 찾아 넘김
    _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "PTP가 뭐야"}]})
    assert seen[-1] == ("chat", None)
