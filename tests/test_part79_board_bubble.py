"""💬 AI 말풍선(2026-10-28 사용자 — 물건마다 작은 대화창, §8 항목68 「메모에 AI가 직접 쓰기」를 품음): `easycad/ai/board_bubble.py`의
messages(물건 글·그림은 마지막 질문에만)·답 읽기(메모만 고침, JSON이 아니면 글 그대로)와 서버 `/api/chat` `kind: 'bubble'`·`/api/threads/<칠판>` 저장.

KAIROS는 부르지 않는다 — 가짜 클라이언트. 실제 호출은 따로 확인(2026-10-28, gpt-6.1-sol: 메모 고쳐 쓰기 4.9초 · 묻기 2.0초 · 그림 4.1초).
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

from easycad.ai import board_bubble  # noqa: E402


def fake_client(answer, sent):
    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    sent.update(kw)
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer), finish_reason="stop")])
    return Client


def test_messages_put_item_and_image_on_last_question_only():
    hist = [{"role": "user", "content": "요약해 줘"}, {"role": "assistant", "content": "요약했어요"}, {"role": "user", "content": "더 짧게"}]
    msgs = board_bubble.build_messages({"type": "memo", "text": "# 점검\n- 안테나 정상"}, hist, image="data:image/png;base64,AAAA")
    assert msgs[0]["role"] == "system" and msgs[1] == {"role": "user", "content": "요약해 줘"}
    last = msgs[-1]["content"]
    assert last[0]["type"] == "text" and "[이 물건 — memo]" in last[0]["text"] and "안테나 정상" in last[0]["text"] and last[0]["text"].endswith("더 짧게")
    assert last[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    with pytest.raises(ValueError):
        board_bubble.build_messages({"type": "memo", "text": "x"}, [{"role": "assistant", "content": "답"}])


def test_reply_edits_only_editable_items():
    sent = {}
    ans = '```json\n{"reply": "할 일만 뽑아 붙였어요.", "edit": "# 점검\\n- [ ] 교체"}\n```'
    out = board_bubble.reply("k", {"type": "memo", "text": "# 점검", "edit": "memo"}, [{"role": "user", "content": "할 일 뽑아 줘"}], model="m", client=fake_client(ans, sent))
    assert out["content"] == "할 일만 뽑아 붙였어요." and out["edit"] == "# 점검\n- [ ] 교체" and sent["model"] == "m"
    assert "고칠 수 있음(메모)" in sent["messages"][-1]["content"]
    out = board_bubble.reply("k", {"type": "image", "text": ""}, [{"role": "user", "content": "고쳐 줘"}], client=fake_client(ans, {}))
    assert "edit" not in out                                                   # 고칠 수 있는 물건이 아니면 고치지 않음
    out = board_bubble.reply("k", {"type": "memo", "text": "x", "edit": "memo"}, [{"role": "user", "content": "뭐야?"}], client=fake_client("그냥 글 답", {}))
    assert out == {"content": "그냥 글 답", "model": board_bubble.gw.FALLBACK_DEFAULT_MODEL, "elapsed": out["elapsed"]}   # JSON이 아니면 답만
    assert board_bubble.parse('{"reply": "", "edit": "# 새 메모"}', True) == {"reply": "고쳤어요.", "edit": "# 새 메모"}
    assert board_bubble.parse('{"reply": "바꿈", "memo": "옛 이름"}', True) == {"reply": "바꿈", "edit": "옛 이름"}


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    monkeypatch.setattr(srv.Handler, "_balance", staticmethod(lambda key, base: None))
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()


def _req(base, path, body=None, method="POST"):
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})) as r:
        return json.loads(r.read())


def test_server_bubble_kind_and_threads_file(server, monkeypatch):
    base, data = server
    import server as srv
    calls = []
    monkeypatch.setattr(srv.board_bubble, "reply", lambda key, item, msgs, **kw: calls.append((item, msgs, kw)) or {"content": "고쳤어요", "edit": "# 새", "model": kw["model"], "elapsed": 0.1})
    monkeypatch.setattr(srv.route, "decide", lambda *a, **k: pytest.fail("말풍선은 길 고르기를 안 거침"))
    out = _req(base, "/api/chat", {"kind": "bubble", "board": "칠판", "model": "gpt-x", "item": {"type": "memo", "text": "# 옛", "edit": "memo", "image": "javascript:x"},
                                   "messages": [{"role": "user", "content": "고쳐 줘"}]})
    assert out["kind"] == "bubble" and out["edit"] == "# 새" and out["content"] == "고쳤어요"
    item, msgs, kw = calls[-1]
    assert item == {"type": "memo", "text": "# 옛", "edit": "memo"} and kw["image"] == "" and kw["model"] == "gpt-x" and msgs[-1]["content"] == "고쳐 줘"
    th = {"s1": [{"role": "user", "content": "고쳐 줘"}, {"role": "assistant", "content": "고쳤어요"}]}
    assert _req(base, "/api/threads/" + urllib.parse.quote("칠판"), th, method="PUT")["ok"] is True
    assert _req(base, "/api/threads/" + urllib.parse.quote("칠판"), method="GET") == th
    assert os.path.exists(os.path.join(data, "칠판.threads.json"))


def test_server_image_bubble_edit_saves_picture(server, monkeypatch):
    """그림 말풍선 2단계 — 고치는 말 = 원본 유지 그림 고치기(input_images 1장) → 칠판 그림 폴더에 저장한 주소, 묻는 말 = 답만."""
    base, data = server
    import server as srv
    gen = []
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, base_url="", **kw: gen.append((prompt, kw)) or {"images": [(b"\x89PNGx", "png")], "model": "img-m", "credits": 12.0})
    monkeypatch.setattr(srv.board_bubble, "reply", lambda key, item, msgs, **kw: {"content": "빨간 점", "model": "m", "elapsed": 0.1})
    img = "data:image/jpeg;base64,/9j/AAAA"
    out = _req(base, "/api/chat", {"kind": "bubble", "board": "그림판", "item": {"type": "image", "text": "", "image": img}, "messages": [{"role": "user", "content": "배경을 밝게 해 줘"}]})
    prompt, kw = gen[-1]
    assert kw["input_images"] == [img] and kw["n"] == 1 and "배경을 밝게" in prompt and "그대로 유지" in prompt
    assert out["kind"] == "bubble" and out["image_url"].startswith("/api/img/") and "edit" not in out
    assert any(f.endswith(".png") for f in os.listdir(os.path.join(data, "그림판.img")))
    out = _req(base, "/api/chat", {"kind": "bubble", "board": "그림판", "item": {"type": "image", "text": "", "image": img}, "messages": [{"role": "user", "content": "이 그림 뭐야?"}]})
    assert out["content"] == "빨간 점" and "image_url" not in out and len(gen) == 1
