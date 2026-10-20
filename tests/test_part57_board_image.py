"""§8 항목61 ③-4(2026-10-19) — 웹 칠판 그림: KAIROS 그림 응답 읽기(`easycad/ai/board_image.py` — data: 주소·b64·http 주소),
「그려줘」 짐작(흐름도·도면은 대화로), 서버 `/api/chat`의 image(칠판 옆 폴더에 저장·주소만 돌려줌)·`/api/img` 내주기.

KAIROS는 부르지 않는다 — 가짜 http. 실제 호출은 따로 확인(후보 2장 4.1초·68크레딧).
"""
import base64
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

from easycad.ai import board_chat, board_image  # noqa: E402

JPG, PNG = b"\xff\xd8\xff\xe0jpgdata", b"\x89PNGpngdata"


class FakeHttp:
    def __init__(self):
        self.sent = None

    def post(self, url, headers, json, timeout):
        self.sent = (url, json)
        return SimpleNamespace(status_code=200, text="", json=lambda: {"data": [
            {"url": "data:image/jpeg;base64," + base64.b64encode(JPG).decode()}, {"b64_json": base64.b64encode(PNG).decode()},
            {"url": "https://cdn.x/a.webp"}], "credits_charged": 68.2})

    def get(self, url, timeout):
        return SimpleNamespace(content=b"WEBPdata", headers={"content-type": "image/webp"})


def test_generate_reads_data_url_b64_and_http():
    http = FakeHttp()
    out = board_image.generate("k", "송신탑 그려줘", base_url="https://g", http=http)
    assert http.sent == ("https://g/images/generate/", {"model": board_image.IMAGE_MODEL, "prompt": "송신탑 그려줘", "number_of_images": 2, "aspect_ratio": "4:3"})
    assert out["images"] == [(JPG, "jpg"), (PNG, "png"), (b"WEBPdata", "webp")] and out["credits"] == 68.2


def test_guess_image_but_diagrams_stay_chat():
    assert board_chat.guess_kind("산 위 송신탑 그려줘") == "image"
    assert board_chat.guess_kind("송신탑 일러스트 만들어 줘") == "image"
    assert board_chat.guess_kind("로그인 흐름도 그려줘") == "chat"          # 칠판 도형으로 그릴 것은 그림 모델이 아님
    assert board_chat.guess_kind("지난번 그린 그림 뭐였지") == "board"
    assert board_chat.guess_kind("그림 그리는 법 알려줘") == "chat"


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, base_url="": {"images": [(JPG, "jpg"), (PNG, "png")], "model": "img-m", "credits": 68.2})
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()


def test_server_image_saves_files_and_serves_them(server):
    base, data = server
    body = json.dumps({"board": "공부", "messages": [{"role": "user", "content": "송신탑 그려줘"}]}).encode()
    with urllib.request.urlopen(urllib.request.Request(base + "/api/chat", data=body, method="POST", headers={"Content-Type": "application/json"})) as r:
        out = json.loads(r.read())
    assert out["kind"] == "image" and out["model"] == "img-m" and out["credits"] == 68.2 and len(out["images"]) == 2
    assert sorted(os.listdir(data / "공부.img"))[0].endswith((".jpg", ".png"))
    with urllib.request.urlopen(base + urllib.parse.quote(urllib.parse.unquote(out["images"][0]["url"]), safe="/")) as r:
        assert r.read() == JPG and r.headers["Content-Type"] == "image/jpeg"
    with pytest.raises(urllib.error.HTTPError) as e:   # 이름 규칙에 맞지만 없는 그림
        urllib.request.urlopen(base + "/api/img/" + urllib.parse.quote("공부") + "/123_abcdef.png")
    assert e.value.code == 404
    (data / "secret.png").write_bytes(b"SECRET")   # 칠판 폴더 밖 파일 — 이름 규칙에 안 맞아 그림 길목을 안 탐(첫 화면 html이 나갈 뿐)
    with urllib.request.urlopen(base + "/api/img/" + urllib.parse.quote("공부") + "/../secret.png") as r:
        assert b"SECRET" not in r.read()


def test_server_infographic_uses_report_material(server, monkeypatch):
    """「🎨 그림으로도」(2026-10-20) — 질문 글이 아니라 정리 문서와 같은 자료(고른 것의 글, 없으면 칠판 전체)로 인포그래픽 지시."""
    base, data = server
    import server as srv
    seen = []
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, base_url="": seen.append(prompt) or {"images": [(JPG, "jpg")], "model": "img-m", "credits": 10.4})

    def ask(msg):
        body = json.dumps({"board": "점검", "kind": "image", "infographic": True, "messages": [msg]}).encode()
        with urllib.request.urlopen(urllib.request.Request(base + "/api/chat", data=body, method="POST", headers={"Content-Type": "application/json"})) as r:
            return json.loads(r.read())
    assert ask({"role": "user", "content": "「점검」 인포그래픽 그림", "context": "발전기 연료 62%"})["kind"] == "image"
    assert "인포그래픽" in seen[-1] and "발전기 연료 62%" in seen[-1] and "지어" not in seen[-1] and "넣지 마" in seen[-1]
    (data / "점검.ecad").write_text(json.dumps({"format": "easycad-doc", "version": 1, "items": [
        {"type": "memo", "uid": "u1", "pos": [0, 0], "rect": [0, 0, 340, 40], "lines": [{"k": "p", "t": "VSWR 1.12"}]}]}, ensure_ascii=False), encoding="utf-8")
    ask({"role": "user", "content": "「점검」 인포그래픽 그림"})   # 고른 것 없음 = 칠판 전체
    assert "VSWR 1.12" in seen[-1]


def test_server_image_with_live_info_searches_first(server, monkeypatch):
    """「내일 날씨를 고흐 느낌으로 그려줘」(2026-10-20) — 최신 정보가 필요한 그림 = 웹 검색 → 그 사실을 넣어 그리기, 답에 검색 내용·출처."""
    base, _ = server
    import server as srv
    seen = []
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, base_url="": seen.append(prompt) or {"images": [(JPG, "jpg")], "model": "img-m", "credits": 10.4})
    monkeypatch.setattr(srv.board_chat, "chat", lambda key, msgs, **kw: {"content": "내일 전주: 오전 비 뒤 맑음, 12~17도[1]", "model": "sonar-x", "kind": kw.get("kind"),
                                                                      "sources": [{"n": 1, "url": "https://weather.go.kr", "title": "기상청"}]})
    body = json.dumps({"board": "그림", "kind": "image", "messages": [{"role": "user", "content": "내일의 전주 날씨를 고흐 느낌으로 그려줘"}]}).encode()
    with urllib.request.urlopen(urllib.request.Request(base + "/api/chat", data=body, method="POST", headers={"Content-Type": "application/json"})) as r:
        out = json.loads(r.read())
    assert "12~17도" in seen[-1] and "[1]" not in seen[-1].split("[그림에 반영할")[1]
    assert out["kind"] == "image" and "12~17도" in out["content"] and out["sources"][0]["url"] == "https://weather.go.kr"
    body = json.dumps({"board": "그림", "kind": "image", "messages": [{"role": "user", "content": "송신탑 그려줘"}]}).encode()   # 최신 정보 말 없음 = 검색 안 함
    with urllib.request.urlopen(urllib.request.Request(base + "/api/chat", data=body, method="POST", headers={"Content-Type": "application/json"})) as r:
        assert "sources" not in json.loads(r.read()) and seen[-1] == "송신탑 그려줘"
