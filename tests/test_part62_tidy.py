"""§8 항목61 「정리해 줘」 ② 레고형 정리정돈(2026-10-19) — 칠판 조각 → 주제별 묶음 목록(`easycad/ai/board_tidy.py`):
말 짐작(정돈·묶어 = tidy, 「정리해 줘」·보고서 = report), AI 답 다듬기(없는·겹친 uid 빼기, 빠진 것 「기타」), 서버 `/api/chat` tidy.
자리 잡기는 칠판(`web/src/next/tidy.js` — `npm test`), 화면 흐름은 `web/e2e/flow17-tidy.spec.js`.

KAIROS는 부르지 않는다 — 가짜 클라이언트.
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
from easycad.ai import board_chat, board_tidy  # noqa: E402


def test_guess_kind_tidy_vs_report():
    for q in ("주제별로 정돈해 줘", "비슷한 것끼리 묶어 줘", "이것들 그룹으로 모아 줘", "분류해 봐"):
        assert board_chat.guess_kind(q) == "tidy", q
    for q in ("정리해 줘", "주제별로 묶어서 보고서로", "한 장으로 정리해 줘"):
        assert board_chat.guess_kind(q) == "report", q
    assert board_chat.guess_kind("송신기 출력 몇이야") == "chat"


def test_guess_kind_report_needs_board_material():
    """「○○ 정리해 줘」 — 주제가 붙고 고른 게 없으면 정리 문서가 아니라 보통 짐작(2026-10-19 사용자 선택)."""
    for q in ("이거 정리해 줘", "칠판 내용 다 정리해 줘", "지금까지 모은 것 깔끔하게 정리해 주세요", "송신소 점검 결과 보고서로 정리해 줘"):
        assert board_chat.guess_kind(q) == "report", q
    assert board_chat.guess_kind("송신소 정전 대비 점검 순서 정리해줘 목록으로") == "chat"
    assert board_chat.guess_kind("지난번 송신기 회의 정리해 줘") == "board"
    assert board_chat.guess_kind("오늘 KBS 뉴스 정리해 줘") == "search"
    assert board_chat.guess_kind("송신소 점검 순서 정리해 줘", has_context=True) == "report"   # 고른 것이 있으면 그것으로 문서


def test_tidy_words_same_as_web():
    """칠판이 조각 목록을 같이 보낼지 정하는 말(`tidy.js` TIDY_RE)과 서버가 짐작하는 말이 같아야 한다."""
    js = open(os.path.join(ROOT, "web", "src", "next", "tidy.js"), encoding="utf-8").read()
    m = re.search(r"export const TIDY_RE = /(.+)/\n", js)
    assert m and m.group(1) == board_chat.TIDY_WORDS


def test_normalize_drops_unknown_dupes_and_collects_leftovers():
    plan = {"title": "점검", "opinion": "교체가 먼저", "sections": [
        {"title": "송신기", "items": ["a", "b", "zz", "a"], "note": "출력 이상"},
        {"title": "빈 묶음", "items": ["zz"]},
        {"title": "회의", "items": ["b", "c"]}]}
    out = board_tidy.normalize(plan, ["a", "b", "c", "d"])
    assert [s["title"] for s in out["sections"]] == ["송신기", "회의", "기타"]
    assert [s["items"] for s in out["sections"]] == [["a", "b"], ["c"], ["d"]]
    assert out["opinion"] == "교체가 먼저" and out["sections"][0]["note"] == "출력 이상"
    many = board_tidy.normalize({"sections": [{"title": f"s{i}", "items": [f"u{i}"]} for i in range(12)]}, [f"u{i}" for i in range(12)])
    assert len(many["sections"]) == board_tidy.MAX_SECTIONS and many["sections"][-1]["title"] == "기타" and len(many["sections"][-1]["items"]) == 4


class FakeClient:
    def __init__(self, answer):
        self.seen, self.answer = [], answer
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.seen.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))])


def test_make_sends_pieces_not_coordinates_and_parses_fenced_json():
    c = FakeClient('```json\n{"title": "T", "sections": [{"title": "가", "items": ["m1", "m2"], "note": "n"}], "opinion": "o"}\n```')
    out = board_tidy.make(c, [{"uid": "m1", "type": "memo", "text": "송신기\n이상", "w": 340, "h": 90}, {"uid": "m2", "type": "rect", "text": "", "w": 80, "h": 40}], "두 묶음으로")
    sent = c.seen[0]["messages"][1]["content"]
    assert "- m1 · memo · 340x90 · 송신기 이상" in sent and "- m2 · rect · 80x40 · (글 없음)" in sent and "[요청]\n두 묶음으로" in sent
    assert c.seen[0]["model"] == board_tidy.TIDY_MODEL
    assert out["plan"]["sections"][0]["items"] == ["m1", "m2"] and "1묶음" in out["content"] and "핵심 의견: o" in out["content"]
    with pytest.raises(ValueError):
        board_tidy.make(c, [{"uid": "m1"}])


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    seen = []

    def fake_make(client, items, ask="", *, model=board_tidy.TIDY_MODEL):
        seen.append({"items": items, "ask": ask})
        plan = board_tidy.normalize({"title": "T", "sections": [{"title": "가", "items": [items[0]["uid"]]}]}, [it["uid"] for it in items])
        return {"plan": plan, "content": board_tidy.summary(plan), "model": model, "elapsed": 0.1}
    monkeypatch.setattr(srv.board_tidy, "make", fake_make)
    monkeypatch.setattr(srv.gw, "_client", lambda *a, **k: None)
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def _post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


def test_server_tidy(server):
    base, seen = server
    items = [{"uid": "a", "type": "memo", "text": "x", "w": 10, "h": 10}, {"uid": "b", "type": "memo", "text": "y", "w": 10, "h": 10}]
    out = _post(base + "/api/chat", {"board": "공부", "items": items, "messages": [{"role": "user", "content": "주제별로 정돈해 줘"}]})
    assert out["kind"] == "tidy" and [s["items"] for s in out["plan"]["sections"]] == [["a"], ["b"]]   # 빠진 b = 기타
    assert seen[-1]["items"] == items and seen[-1]["ask"] == "주제별로 정돈해 줘"
    out = _post(base + "/api/chat", {"board": "공부", "kind": "tidy", "items": items, "messages": [{"role": "user", "content": "고른 것을 주제별로 묶어 정돈해 줘"}]})
    assert out["kind"] == "tidy"
    with pytest.raises(urllib.error.HTTPError) as e:   # 조각이 없으면 알아듣게
        _post(base + "/api/chat", {"board": "공부", "kind": "tidy", "messages": [{"role": "user", "content": "정돈해 줘"}]})
    assert e.value.code == 400 and "2개 이상" in json.loads(e.value.read())["error"]
