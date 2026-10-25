"""§8 항목66 4-1·4-2 움직이는 카드(2026-10-25) — 그릇의 데스크톱 쪽: 웹 `web/src/next/livecard.js`와 같은 틀 글(CSP·크기 상한),
두 번 누르기로 브라우저에 여는 페이지(움직이는 카드 = sandbox 틀 안에서만 스크립트, 보통 문서 = 스크립트 끔), 저장하면 `live` 칸 그대로.
4-2 서버: 카드 만들기(`live_card`)·딥모드 원리 꼭지(본문과 동시)·`/api/chat` `kind: 'live'` — KAIROS는 가짜.
웹 화면(한 번 = 고르기·두 번 = 조작·인터넷/칠판 못 닿음)은 `web/e2e/flow34-live-card.spec.js`.
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
from _shared import _app  # noqa: F401  (QApplication)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))
from easycad.ai import deep_mode, live_card  # noqa: E402
from easycad.canvas import core_web as W  # noqa: E402
from easycad.fileio.document import dict_to_item, item_to_dict  # noqa: E402

JS = open(os.path.join(ROOT, "web", "src", "next", "livecard.js"), encoding="utf-8").read()
CARD = '<!doctype html><html><head><title>카드</title><script>x()</script></head><body><input type="range"></body></html>'
DOC = {"type": "doc", "pos": [0, 0], "rect": [0, 0, 480, 360], "scale": 1, "rotation": 0, "z": 1, "origin": [0, 0], "locked": False,
       "group_id": None, "layer_id": None, "title": "가격 × 물량", "html": CARD, "model": "gpt-6.1-sol", "live": True}


def _js_const(name):
    return re.search(rf'export const {name} = "([^"]+)"', JS).group(1)


def test_same_frame_as_web():
    assert W.LIVE_CSP == _js_const("LIVE_CSP")
    assert W.STATIC_CSP == _js_const("STATIC_CSP")
    assert f"LIVE_MAX = {W.LIVE_MAX:_}" in JS
    assert W._KICK in JS


def test_big_page_live_runs_only_inside_sandbox():
    p = W.big_page(DOC)
    assert p.startswith(f'<!doctype html><meta http-equiv="Content-Security-Policy" content="{W.LIVE_CSP}">')
    m = re.search(r'<iframe sandbox="allow-scripts" csp="[^"]+" srcdoc="([^"]*)"></iframe>', p)
    assert m and "allow-same-origin" not in p
    assert "<script" not in p.replace(m.group(0), "")          # 틀 밖 페이지엔 스크립트 없음
    assert "&lt;script&gt;x()" in m.group(1)                  # 카드 글은 틀 안(이스케이프)
    assert m.group(1).count("&lt;!doctype") == 1              # 우리 doctype 하나


def test_big_page_static_and_too_big():
    plain = W.big_page({**DOC, "live": False})
    assert plain.startswith(f'<!doctype html><meta http-equiv="Content-Security-Policy" content="{W.STATIC_CSP}">')
    assert "script-src" not in W.STATIC_CSP                   # 끌어 놓은 HTML 파일 속 스크립트도 꺼짐
    big = {**DOC, "html": "a" * (W.LIVE_MAX + 1)}
    assert not W.live_fits(big) and W.big_page(big).startswith(f'<!doctype html><meta http-equiv="Content-Security-Policy" content="{W.STATIC_CSP}">')


def test_live_kept_on_save():
    it = dict_to_item(dict(DOC))
    assert isinstance(it, W._DocItem)
    assert item_to_dict(it).get("live") is True


# ── 4-2 서버: 움직이는 카드 만들기(`easycad/ai/live_card.py`) · 딥모드 원리 꼭지 · `/api/chat` `kind: 'live'` — KAIROS는 가짜 ──
class FakeClient:
    """답을 차례로(같은 때 둘이 부르면 먼저 온 쪽부터) — 보낸 messages·모델을 적어 둠."""
    def __init__(self, *answers, by_model=None):
        self.answers, self.by_model, self.sent = list(answers), by_model or {}, []
        self.lock = threading.Lock()
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        with self.lock:
            self.sent.append(kw)
            a = self.by_model[kw["model"]] if kw["model"] in self.by_model else self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=a))], usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))


def test_make_cleans_fence_and_checks_whole_html():
    c = FakeClient("설명 먼저\n```html\n" + CARD + "\n```")
    out = live_card.make(c, "가격 × 물량", "(메모) 9월 수출 603억 달러")
    assert out["html"] == CARD and out["title"] == "카드" and out["model"] == live_card.LIVE_MODEL
    sys_, user = c.sent[0]["messages"][0]["content"], c.sent[0]["messages"][1]["content"]
    assert "기준 값" in sys_ and "720 × 세로 480" in sys_ and "[칠판 재료]\n(메모) 9월 수출 603억 달러" in user
    with pytest.raises(RuntimeError, match="끊김"):            # 글 한도에 걸려 끊긴 HTML(4-0 sonnet) = 오류로 알림
        live_card.make(FakeClient("<!doctype html><html><body><script>var a="), "x")
    with pytest.raises(RuntimeError, match="너무 커요"):
        live_card.make(FakeClient("<!doctype html><html>" + "a" * live_card.LIVE_MAX + "</html>"), "x")
    with pytest.raises(ValueError):
        live_card.make(FakeClient(), "  ")
    assert live_card.LIVE_MAX == W.LIVE_MAX                    # 칠판 상한과 같게
    r = FakeClient(CARD)
    live_card.make(r, "더 크게", prev_html="<html>앞</html>")
    assert "[앞 카드]\n<html>앞</html>" in r.sent[0]["messages"][1]["content"]


def test_plan_keeps_one_live_card_as_ai():
    p = deep_mode.clean_plan({"sections": [{"title": "원리", "shape": "움직이는 카드", "source": "web", "query": "q"},
                                           {"title": "또 원리", "shape": "움직이는 카드", "source": "ai"}]})
    assert [(s["shape"], s["source"], s["query"]) for s in p["sections"]] == [("움직이는 카드", "ai", None), ("단계 카드", "ai", None)]
    e0, e1 = deep_mode.estimate(deep_mode.clean_plan({"sections": [{"title": "a", "shape": "단계 카드"}]})), deep_mode.estimate(p)
    assert e1["credits"][0] >= e0["credits"][0] + 40 and e1["seconds"][1] >= 120


PLAN = {"title": "반도체", "headline": "가격과 물량", "sections": [
    {"title": "숫자", "shape": "숫자 타일", "source": "web", "query": "반도체 수출"},
    {"title": "가격 × 물량", "question": "왜 곱해지나", "shape": "움직이는 카드", "source": "ai"}]}
BODIES = json.dumps({"sections": [{"title": "숫자", "body": {"tiles": [["603억 달러", "9월", 1]]}}, {"title": "가격 × 물량", "body": {"note": "막대를 끌면 넓이"}}]}, ensure_ascii=False)
EXA = lambda q: ("9월 603억 달러 [1]", {"search_results": [{"title": "무역", "url": "https://a"}]})  # noqa: E731


def test_build_makes_card_alongside_bodies():
    c = FakeClient(by_model={deep_mode.WRITER_MODEL: BODIES, live_card.LIVE_MODEL: CARD})
    out = deep_mode.build("k", c, "반도체", {"누구에게": "신입"}, deep_mode.clean_plan(PLAN), exa=EXA, kr=lambda q: [])
    sec = out["plan"]["sections"][1]
    assert sec["body"]["note"] == "막대를 끌면 넓이" and sec["body"]["html"] == CARD and sec["body"]["card_model"] == live_card.LIVE_MODEL
    live = next(k for k in c.sent if k["model"] == live_card.LIVE_MODEL)
    assert "독자: 신입" in live["messages"][0]["content"]
    u = live["messages"][1]["content"]
    assert "[이 카드 꼭지] 가격 × 물량" in u and "9월 603억 달러 [1]" in u and "[1] 무역 — https://a" in u   # 다른 꼭지 재료·출처 번호를 같이
    bad = FakeClient(by_model={deep_mode.WRITER_MODEL: BODIES, live_card.LIVE_MODEL: RuntimeError("게이트웨이")})
    out2 = deep_mode.build("k", bad, "반도체", {}, deep_mode.clean_plan(PLAN), exa=EXA, kr=lambda q: [])
    assert "html" not in out2["plan"]["sections"][1]["body"] and any("움직이는 카드" in m for m in out2["missing"])   # 카드만 못 만들어도 판은 지음


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    seen = []

    def fake_make(client, ask, material="", prev_html="", **_k):
        seen.append((ask, material, prev_html))
        if "실패" in ask:
            raise RuntimeError("끊김")
        return {"html": CARD, "title": "카드", "model": "gpt-6.1-sol", "elapsed": 0.1}
    monkeypatch.setattr(srv.live_card, "make", fake_make)
    monkeypatch.setattr(srv.route, "decide", lambda *a, **k: ("chat", "rules", []))   # 길 고르기 = 대화(판단 모델 안 부름)
    monkeypatch.setattr(srv.gw, "_client", lambda *a, **k: None)
    monkeypatch.setattr(srv.board_chat, "models", lambda *a, **k: {"default": "m", "featured": {}})
    srv._MODELS.clear()
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def _post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_server_live_kind_and_models_job(server):
    url, seen = server
    st, out = _post(url + "/api/chat", {"kind": "live", "messages": [{"role": "user", "content": "가격 × 물량 움직여 보기"}], "context": "(메모) 603억"})
    assert st == 200 and out["kind"] == "live" and out["html"] == CARD and "두 번 누르면" in out["content"]
    assert seen == [("가격 × 물량 움직여 보기", "(메모) 603억", "")]
    st, out = _post(url + "/api/chat", {"kind": "live", "messages": [{"role": "user", "content": "실패"}]})
    assert st == 502 and "움직이는 카드 실패" in out["error"]
    with urllib.request.urlopen(url + "/api/models") as r:
        assert json.loads(r.read())["jobs"]["live"] == live_card.LIVE_MODEL


def test_server_live_followup_revises_previous_card(server):
    """4-3 말로 고치기 — 바로 앞 답이 카드이고(prev_kind) 고칠 말이면 그 카드를 바탕으로, 이름표를 단 채 새 요청이면 새 카드."""
    url, seen = server
    prev = {"prev_html": "<html>앞 카드</html>", "prev_kind": "live"}
    st, out = _post(url + "/api/chat", {"kind": "live", **prev, "messages": [{"role": "user", "content": "막대를 더 크게 해 줘"}]})
    assert st == 200 and seen[-1][2] == "<html>앞 카드</html>" and out["content"].startswith("말한 대로 고친")
    _post(url + "/api/chat", {"kind": "live", **prev, "messages": [{"role": "user", "content": "옴의 법칙"}]})
    assert seen[-1][2] == ""                                   # 고칠 말이 없으면 새 카드
    st, out = _post(url + "/api/chat", {**prev, "messages": [{"role": "user", "content": "글자를 키워 줘"}]})   # 이름표 없이 — 길이 「대화」면 그 카드 고치기
    assert st == 200 and out["kind"] == "live" and seen[-1] == ("글자를 키워 줘", "", "<html>앞 카드</html>")
