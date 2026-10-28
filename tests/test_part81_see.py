"""칠판 그림을 AI에게 보이기(2026-10-28) — `easycad/ai/see.py` 한 곳: 줄이기·칠판 파일에서 꺼내기·마지막 질문에 붙이기,
그리고 정리 문서·인터랙티브 HTML·발표 자료·딥모드 「이 칠판」·프레임 말풍선이 그 그림을 실어 보내는지(서버 `/api/chat`).

KAIROS는 부르지 않는다 — 가짜. 실제로 그림을 받는지는 따로 실측(2026-10-28: claude-opus-5-5·claude-sonnet-5-5·gpt-6.1-sol 모두 그림 속 글까지 읽음).
"""
import base64
import io
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

from easycad.ai import board_bubble, board_report, live_card, see, slides  # noqa: E402


def png(w=2000, h=1000, mode="RGBA"):
    from PIL import Image
    buf = io.BytesIO()
    Image.new(mode, (w, h), (255, 0, 0, 128) if mode == "RGBA" else "red").save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def size_of(url):
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).size


def fake_client(answer, sent):
    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    sent.update(kw)
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer), finish_reason="stop")])
    return Client


def pics(messages):
    c = messages[-1]["content"]
    return [p["image_url"]["url"] for p in c if p.get("type") == "image_url"] if isinstance(c, list) else []


def test_shrink_clean_from_doc():
    url = see.shrink("data:image/png;base64," + png())
    assert url.startswith("data:image/jpeg") and size_of(url) == (1024, 512)   # 긴 변 1024, 투명 → 흰 바탕 JPEG
    assert see.shrink("data:image/png;base64,깨짐") == "data:image/png;base64,깨짐"   # 못 읽으면 그대로
    assert see.clean(["javascript:x", 3, "data:image/png;base64," + png(10, 10)]) and len(see.clean(["data:image/png;base64," + png(10, 10)] * 9)) == see.MAX_IMAGES
    doc = {"items": [{"type": "image", "uid": "a", "data": png(10, 10)}, {"type": "memo", "uid": "m"}, {"type": "image", "uid": "b", "data": "data:image/png;base64," + png(20, 10)}]}
    assert len(see.from_doc(doc)) == 2 and [size_of(u) for u in see.from_doc(doc, ["b"])] == [(20, 10)] and see.from_doc(doc, []) == [] and see.from_doc({}) == []


def test_attach_and_note():
    m = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]
    assert see.attach(m, []) is m
    out = see.attach(m, ["data:image/jpeg;base64,AA"])
    assert out[-1]["content"][0] == {"type": "text", "text": "q"} and pics(out) == ["data:image/jpeg;base64,AA"] and m[-1]["content"] == "q"   # 원본은 안 바뀜
    assert pics(see.attach(out, ["data:image/jpeg;base64,BB"])) == ["data:image/jpeg;base64,AA", "data:image/jpeg;base64,BB"]   # 이미 조각이면 뒤에
    assert see.note(0) == "" and "그림 2장" in see.note(2)


def test_modules_put_images_on_last_question():
    img = ["data:image/jpeg;base64,AA"]
    sent = {}
    board_report.make(fake_client("<html><h1>제목</h1></html>", sent), "자료", images=img)
    assert pics(sent["messages"]) == img and "그림 1장" in sent["messages"][-1]["content"][0]["text"]
    board_report.make(fake_client("<html><h1>제목</h1></html>", sent), "", "짧게", prev_html="<html>앞</html>", images=img)
    assert pics(sent["messages"]) == []   # 고쳐 쓰기는 앞 문서가 재료
    live_card.make(fake_client("<html><title>t</title></html>", sent), "원리", images=img)
    assert pics(sent["messages"]) == img
    slides.make_plan(fake_client('{"title": "t", "slides": [{"title": "a", "point": "b", "source": "board"}, {"title": "c", "point": "d", "source": "ai"}]}', sent), "주제", {}, images=img)
    assert pics(sent["messages"]) == img and "[고른 자료]" in sent["messages"][-1]["content"][0]["text"]   # 그림만 골라도 고른 자료
    board_bubble.reply("k", {"type": "frame", "text": "안의 글"}, [{"role": "user", "content": "뭐가 있어?"}], client=fake_client("답", sent), images=img * 2)
    assert pics(sent["messages"]) == img * 2 and "그림 2장" in sent["messages"][-1]["content"][0]["text"]


def test_describe_sends_small_picture():
    from easycad.ai import board_ocr
    sent = {}
    out = board_ocr.describe("k", "data:image/png;base64," + png(), client=fake_client("  송신소 점검표 사진.  ", sent))
    assert out["text"] == "송신소 점검표 사진." and out["model"] == board_ocr.OCR_MODEL
    assert [size_of(u) for u in pics(sent["messages"])] == [(768, 384)] and "한두 문장" in sent["messages"][-1]["content"][0]["text"]


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


def _post(base, body):
    req = urllib.request.Request(base + "/api/chat", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_server_routes_pass_images(server, monkeypatch):
    base, data = server
    import server as srv
    with open(os.path.join(data, "판.ecad"), "w", encoding="utf-8") as f:
        json.dump({"items": [{"type": "image", "uid": "g1", "data": png(30, 20)}, {"type": "image", "uid": "g2", "data": png(40, 20)}]}, f)
    got = {}
    monkeypatch.setattr(srv.board_report, "make", lambda client, material, ask, **kw: got.update(report=(material, kw["images"])) or {"html": "<h1>t</h1>", "title": "t", "model": "m", "elapsed": 0})
    monkeypatch.setattr(srv.live_card, "make", lambda client, ask, material, **kw: got.update(live=kw["images"]) or {"html": "<html></html>", "title": "t", "model": "m", "elapsed": 0})
    monkeypatch.setattr(srv.slides, "make_plan", lambda client, topic, brief, **kw: got.update(slides=kw["images"]) or {"plan": {"title": "t", "slides": []}, "estimate": {}, "model": "m", "elapsed": 0})
    monkeypatch.setattr(srv.board_bubble, "reply", lambda key, item, msgs, **kw: got.update(bubble=kw["images"]) or {"content": "답", "model": "m", "elapsed": 0})
    sel = "data:image/png;base64," + png(3000, 1500)
    # 정리 문서 — 고른 그림(대화창이 보냄)은 줄여서, 고른 게 없으면 칠판 파일의 글·그림 전부
    _post(base, {"kind": "report", "board": "판", "messages": [{"role": "user", "content": "정리해 줘"}], "context": "고른 글", "board_images": [sel]})
    assert got["report"][0] == "고른 글" and [size_of(u) for u in got["report"][1]] == [(1024, 512)]
    _post(base, {"kind": "report", "board": "판", "messages": [{"role": "user", "content": "정리해 줘"}]})
    assert got["report"][0] == "(글 없음 — 그림만)" and [size_of(u) for u in got["report"][1]] == [(30, 20), (40, 20)]
    _post(base, {"kind": "live", "board": "판", "messages": [{"role": "user", "content": "원리"}], "board_images": [sel]})
    assert len(got["live"]) == 1
    # 발표 자료 — 이름표만 받아 칠판 파일에서
    _post(base, {"kind": "slides", "board": "판", "slides": {"step": "plan", "topic": "t", "brief": {}, "image_uids": ["g2"]}, "messages": [{"role": "user", "content": "t"}]})
    assert [size_of(u) for u in got["slides"]] == [(40, 20)]
    _post(base, {"kind": "slides", "board": "판", "slides": {"step": "plan", "topic": "t", "brief": {"재료": "웹 검색"}, "image_uids": ["g2"]}, "messages": [{"role": "user", "content": "t"}]})
    assert got["slides"] == []   # 웹 검색만 쓰기로 했으면 고른 것도 안 실음
    _post(base, {"kind": "bubble", "board": "판", "item": {"type": "frame", "text": "x", "images": [sel, "javascript:x"]}, "messages": [{"role": "user", "content": "뭐야"}]})
    assert len(got["bubble"]) == 1
    # 딥모드 — 「이 칠판」 꼭지가 있을 때만 칠판 그림
    monkeypatch.setattr(srv.deep_mode, "build", lambda key, client, topic, brief, plan, **kw: got.update(deep=(kw["board"], kw["images"])) or {"plan": {"sources": []}, "model": "m", "elapsed": 0, "missing": []})
    _post(base, {"kind": "deep", "board": "판", "deep": {"step": "build", "topic": "t", "plan": {"sections": [{"source": "board"}]}}, "messages": [{"role": "user", "content": "t"}]})
    assert got["deep"][0] == "(글 없음 — 그림만)" and len(got["deep"][1]) == 2
    _post(base, {"kind": "deep", "board": "판", "deep": {"step": "build", "topic": "t", "plan": {"sections": [{"source": "web"}]}}, "messages": [{"role": "user", "content": "t"}]})
    assert got["deep"] == ("", [])


def test_server_describe_switch(server, monkeypatch):
    """그림 설명 `/api/describe` — 화면 시험은 끔(EASYCAD_DESCRIBE=off → 빈 글, KAIROS 안 부름), data: 그림이 아니면 빈 글."""
    base, data = server
    import server as srv
    calls = []
    monkeypatch.setattr(srv.board_ocr, "describe", lambda key, url, **kw: calls.append(url) or {"text": "빨간 사각형", "model": "m", "elapsed": 0.1})

    def post(body):
        req = urllib.request.Request(base + "/api/describe", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    url = "data:image/png;base64," + png(10, 10)
    assert post({"data": url})["text"] == "빨간 사각형" and calls == [url]
    assert post({"data": "javascript:x"}) == {"text": ""}
    monkeypatch.setenv("EASYCAD_DESCRIBE", "off")
    assert post({"data": url}) == {"text": ""} and len(calls) == 1
