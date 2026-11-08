"""「이 장 움직이게」(계획 ⑤, 2026-11-08) — 장 하나 → 모션 HTML(→ 로 단계). 모델은 가짜, 진짜는 손 확인(docs/history 2026-11)."""
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web"))   # server.py

from easycad.ai import features, motion_slide  # noqa: E402

GOOD = "<!doctype html><html><body><script>window.mbSteps=3;window.mbStep=0;window.mbNext=()=>false;window.mbPrev=()=>false</script></body></html>"
SLIDE = {"title": "송신소는 무슨 일을 하나", "bullets": ["신호를 만든다", "전파로 바꾼다", "하늘로 쏜다"], "notes": "마지막 관문입니다.", "layout": "그림"}


class _Client:
    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(model=kw["model"], choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])


def test_make_sends_size_steps_and_reference_picture():
    c = _Client("```html\n" + GOOD + "\n```")
    out = motion_slide.make(c, SLIDE, w=1600, h=1067, ref_image="data:image/jpeg;base64,AAAA")
    assert out["html"] == GOOD and out["steps"] == 3 and out["title"] == SLIDE["title"]
    kw = c.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["max_tokens"] == 32000          # 16,000이면 끝이 잘렸음(11-07 실측)
    assert "1600×1067" in kw["messages"][0]["content"] and "mbPrev" in kw["messages"][0]["content"]   # 그림 장 비율 그대로
    user = kw["messages"][1]["content"]
    assert user[1]["image_url"]["url"].startswith("data:image/jpeg") and "참고 그림" in user[0]["text"] and "단계는 3개" in user[0]["text"]
    assert "layout" not in user[0]["text"]                                          # 장 글만(칠판 모양 값은 안 보냄)
    assert isinstance(motion_slide.make(_Client(GOOD), SLIDE)["html"], str)        # 그림 없는 글 장 = 글만
    assert isinstance(_Client(GOOD).calls, list)


def test_make_rejects_cut_or_stepless_html():
    with pytest.raises(ValueError, match="끊겼"):
        motion_slide.make(_Client(GOOD[:-10]), SLIDE)
    with pytest.raises(ValueError, match="mbNext"):
        motion_slide.make(_Client("<html><body>hi</body></html>"), SLIDE)
    with pytest.raises(ValueError, match="제목"):
        motion_slide.make(_Client(GOOD), {"bullets": ["a"]})
    assert motion_slide.steps_of({"bullets": list("abcdefgh")}) == 6 and motion_slide.steps_of({}) == 3


def test_feature_row_is_not_a_chat_route():
    assert features.BY_KIND["motion"]["credits"] == (270, 520) and "motion" not in features.judge_kinds()


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    monkeypatch.setattr(srv.Handler, "_balance", lambda self, key, base: None)
    monkeypatch.setattr(srv.Handler, "_spent", lambda self, key, base, b0: None)
    seen = {}
    monkeypatch.setattr(srv.motion_slide, "make", lambda client, slide, **kw: seen.update(slide=slide, **kw) or {"html": GOOD, "title": slide["title"], "steps": 3, "model": "claude-opus-5-5", "elapsed": 1.0})
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def test_server_motion_route(server):
    base, seen = server
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    body = {"board": "움직임", "kind": "motion", "motion": {"slide": SLIDE, "w": 1600, "h": 1067, "image": png}, "messages": [{"role": "user", "content": "「송신소」 장 움직이게"}]}
    req = urllib.request.Request(base + "/api/chat", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        out = json.loads(r.read())
    assert out["kind"] == "motion" and out["html"] == GOOD and "→" in out["content"]
    assert seen["slide"]["title"] == SLIDE["title"] and seen["h"] == 1067 and seen["ref_image"].startswith("data:image/")
