"""§8 항목61 「정리해 줘」 ①(2026-10-19) — 칠판 자료 → 정리 문서 한 장(HTML): 청소(스크립트·이벤트·외부 연결 지움)·제목·쉬운 글(`easycad/ai/board_report.py`),
서버 `/api/chat`의 report(고른 것 / 없으면 칠판 전체가 재료, 바로 앞 문서 + 「더 짧게」 = 고쳐 쓰기).

KAIROS는 부르지 않는다 — 가짜 클라이언트. 실제 호출은 따로 확인(Opus 5.5 40~55초).
"""
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))
from easycad.ai import board_find, board_report  # noqa: E402

DIRTY = """```html
<!doctype html><html><head><title>회의 브리핑 &amp; 할 일</title><link rel="stylesheet" href="https://x.kr/a.css">
<script>alert(1)</script></head><body onload="evil()"><h1>회의</h1><p>2번 송신기 <b>70%</b></p>
<a href="javascript:alert(2)">링크</a><img src="x.png" onerror="evil()"><iframe src="https://x.kr"></iframe><style>p{color:red}</style></body></html>
```"""


def test_clean_title_plain():
    h = board_report.clean_html(DIRTY)
    assert h.startswith("<!doctype html>") and "```" not in h
    for bad in ("<script", "alert(1)", "onload", "onerror", "javascript:", "<iframe", "<link"):
        assert bad not in h, bad
    assert "<style>" in h and "<b>70%</b>" in h   # 꾸밈은 남김
    assert board_report.title_of(h) == "회의 브리핑 & 할 일"
    assert board_report.plain_text(h) == "회의\n2번 송신기 70%\n링크"


class FakeClient:
    def __init__(self):
        self.seen = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.seen.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="<!doctype html><html><head><title>정리</title></head><body>ok</body></html>"))])


def test_make_new_and_revise():
    c = FakeClient()
    out = board_report.make(c, "(메모) 송신기 이상", "표로")
    assert out["title"] == "정리" and out["model"] == board_report.REPORT_MODEL
    assert "[칠판 자료]\n(메모) 송신기 이상" in c.seen[0]["messages"][1]["content"] and "[요청]\n표로" in c.seen[0]["messages"][1]["content"]
    board_report.make(c, "", "더 짧게", prev_html="<html>앞 문서</html>")
    assert "[앞 문서]\n<html>앞 문서</html>" in c.seen[1]["messages"][1]["content"] and "[고칠 점]\n더 짧게" in c.seen[1]["messages"][1]["content"]


def test_tone_same_as_deep_board_and_picked_by_name():
    """정리 문서 톤 = 칠판 딥모드 톤(`deepstyle.js` — 2026-10-25 장점 바꿔 쓰기): 같은 키·이름·강조색. 기본 차분, 요청에 톤 이름이면 그 톤."""
    import re
    js = open(os.path.join(ROOT, "web", "src", "next", "deepstyle.js"), encoding="utf-8").read()
    got = {k: (n, acc) for k, n, acc in re.findall(r"^  (\w+): tone\('([^']+)', '[^']*', \{ accent: '(#[0-9a-f]{6})'", js, re.M)}
    assert got == {k: (t["name"], t["accent"]) for k, t in board_report.TONES.items()}
    assert board_report.tone_of("신문 톤으로 해 줘") == "news" and board_report.tone_of("파랑으로") == "info" and board_report.tone_of("표로") == ""
    c = FakeClient()
    out = board_report.make(c, "(메모) 송신기 이상", "")
    assert out["tone"] == "calm" and "「차분」 톤" in c.seen[0]["messages"][1]["content"] and "#b4532f" in c.seen[0]["messages"][1]["content"]
    out = board_report.make(c, "", "더 짧게", prev_html="<html>앞</html>")
    assert out["tone"] == "" and "톤" not in c.seen[1]["messages"][1]["content"]   # 고칠 땐 톤을 말했을 때만 바꿈
    board_report.make(c, "", "남색 톤으로", prev_html="<html>앞</html>")
    assert "「남색」 톤" in c.seen[2]["messages"][1]["content"]


def test_unchecked_numbers_flags_numbers_not_in_material():
    """숫자 검사(딥모드 「숫자마다 출처」를 정리 문서에도) — 두 자리 이상 숫자 중 자료에 그대로 없는 것만, 쉼표는 같게 봄, 자료가 비면 안 견줌."""
    doc = "<html><head><title>2099 제목</title><style>p{margin:14mm}</style></head><body><p>출력 1,200W · 시청률 35.2% · 3단계 · 합계 4,800</p></body></html>"
    assert board_report.unchecked_numbers(doc, "송신기 출력 1200W, 시청률 35.2%") == ["4,800"]   # 머리·스타일은 안 봄, 한 자리 숫자는 안 셈
    assert board_report.unchecked_numbers(doc, "") == []


def test_doc_card_text_is_searchable():
    it = {"type": "doc", "uid": "d1", "title": "회의 브리핑", "html": "<html><body><h1>송신기 교체</h1><p>견적은 금요일</p></body></html>"}
    assert board_find.item_text(it) == "회의 브리핑\n송신기 교체\n견적은 금요일"


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    seen = []

    def fake_make(client, material, ask="", *, prev_html="", model=board_report.REPORT_MODEL):
        seen.append({"material": material, "ask": ask, "prev": prev_html})
        return {"html": "<html><title>T</title></html>", "title": "T", "model": model, "elapsed": 0.1, "tone": "calm", "unchecked": ["4,800"] if "합계" in ask else []}
    monkeypatch.setattr(srv.board_report, "make", fake_make)
    monkeypatch.setattr(srv.gw, "_client", lambda *a, **k: None)
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    (tmp_path / "공부.ecad").write_text(json.dumps({"format": "easycad-doc", "items": [
        {"type": "memo", "uid": "m1", "lines": [{"k": "p", "t": "송신기 이상 보고"}]}, {"type": "rect", "uid": "r1", "label": {"text": "UHD 회의"}}]}, ensure_ascii=False), encoding="utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def _post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


def test_server_report_material_whole_board_selection_and_revise(server):
    base, seen = server
    out = _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "이 칠판 정리해 줘"}]})
    assert out["kind"] == "report" and out["html"].startswith("<html>") and "「T」" in out["content"]
    assert "(메모) 송신기 이상 보고" in seen[-1]["material"] and "(상자) UHD 회의" in seen[-1]["material"]   # 고른 것이 없으면 칠판 전체
    _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "보고서로", "context": "- 고른 메모"}]})
    assert seen[-1]["material"] == "- 고른 메모"
    _post(base + "/api/chat", {"board": "공부", "prev_html": "<html>앞</html>", "messages": [{"role": "user", "content": "더 짧게"}]})
    assert seen[-1]["prev"] == "<html>앞</html>" and seen[-1]["ask"] == "더 짧게"   # 「더 짧게」 = 앞 문서 고치기
    out = _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "합계까지 보고서로", "context": "- 고른 메모"}]})
    assert "차분 톤" in out["content"] and "그대로 찾지 못한 숫자: 4,800" in out["content"]   # 숫자 검사는 답 글에 알림(막지 않음)
