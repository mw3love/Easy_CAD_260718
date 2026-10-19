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
