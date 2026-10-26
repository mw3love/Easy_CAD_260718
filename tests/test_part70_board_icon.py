"""§8 항목63 2단계(2026-10-23) — 웹 칠판 아이콘: 「○○ 아이콘 그려 줘」 짐작, `board_icon.make`(후보 둘·못 읽는 답 빼기·고치기 한 개·그림 보고),
서버 `/api/chat` icon 길(아이콘 말 · 아이콘 뒤 「선을 더 굵게」 = 고른 아이콘 고치기 · 칠판에서 고른 그림 + 「아이콘으로」).

KAIROS는 부르지 않는다 — `generate_svg`를 가짜로. 실제 호출은 0단계 실측(claude-sonnet-5-5 3~4초).
"""
import base64
import io
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

from easycad.ai import board_chat, board_icon, route  # noqa: E402

ICON = '<svg viewBox="0 0 10 10"><rect x="1" y="1" width="8" height="8"/></svg>'


def test_guess_icon_only_with_make_words():
    assert board_chat.guess_kind("파라볼라 안테나를 SVG로 그려 줘") == "icon"
    assert board_chat.guess_kind("마이크를 선 그림으로 그려줘") == "icon"
    assert board_chat.guess_kind("카메라를 고칠 수 있게 벡터로 만들어 줘") == "icon"
    assert board_chat.guess_kind("펭귄 아이콘 그려줘") == "image"          # 「아이콘」은 뜻이 둘 — 자동은 그림, 도형은 「+ › ✏️ 아이콘」(2026-10-23 사용자)
    assert board_chat.guess_kind("송신기 심볼 하나 그려 줘") == "image"
    assert board_chat.guess_kind("SVG 만드는 법 알려줘") == "chat"
    assert board_chat.guess_kind("엑셀 아이콘 어디 있어?") == "chat"
    assert route.adjust("송신기를 선 그림으로 만들어 줘", "image", 0.9, {"image": 0.9}) == "icon"   # 판단 모델엔 이 길이 없음 — 낱말이 이김
    assert ("펭귄 아이콘 그려줘", 0, "image") in route.CASES


def test_make_two_candidates_drops_unusable(monkeypatch):
    calls = []

    def fake(key, ask, *, model, image=None, refs=None, base_url=""):
        calls.append((ask, model, image, refs))
        return (ICON if len(calls) == 1 else "죄송해요, 그릴 수 없어요"), model
    monkeypatch.setattr(board_icon, "generate_svg", fake)
    out = board_icon.make("k", "안테나 아이콘 그려 줘")
    assert len(calls) == 2 and calls[0][1] == board_icon.ICON_MODEL and calls[0][3] is None
    assert out["svgs"] == [ICON] and out["model"] == board_icon.ICON_MODEL


def test_make_refine_is_one_and_errors_surface(monkeypatch):
    seen = []
    monkeypatch.setattr(board_icon, "generate_svg", lambda key, ask, **kw: seen.append(kw) or (ICON, kw["model"]))
    board_icon.make("k", "선을 더 굵게", base_svg=ICON)
    assert len(seen) == 1 and seen[0]["refs"] == [ICON] and seen[0]["image"] is None   # 고치기 = 한 개, 고른 아이콘이 참고

    def boom(*a, **kw):
        raise RuntimeError("HTTP 500")
    monkeypatch.setattr(board_icon, "generate_svg", boom)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        board_icon.make("k", "안테나 아이콘")


def test_usable():
    assert board_icon.usable(ICON)
    assert not board_icon.usable("<svg><defs/></svg>")        # 우리 요소 없음
    assert not board_icon.usable("<svg><rect></svg>")        # XML 깨짐
    assert not board_icon.usable("<div><rect/></div>")


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    seen = []
    monkeypatch.setattr(srv.board_icon, "make", lambda key, ask, base_svg="", image_url="", base_url="", **_: seen.append((ask, base_svg, image_url)) or
                        {"svgs": [ICON, ICON], "model": "icon-m", "elapsed": 3.2})
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def _ask(base, **body):
    req = urllib.request.Request(base + "/api/chat", data=json.dumps({"board": "아이콘", **body}).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_server_icon_paths(server):
    base, seen = server
    out = _ask(base, kind="icon", messages=[{"role": "user", "content": "파라볼라 안테나"}])   # 대화창 「+ › ✏️ 아이콘」 이름표
    assert out["kind"] == "icon" and out["svgs"] == [ICON, ICON] and out["model"] == "icon-m" and "후보 2개" in out["content"]
    assert seen[-1] == ("파라볼라 안테나", "", "")
    assert _ask(base, messages=[{"role": "user", "content": "마이크를 선 그림으로 그려줘"}])["kind"] == "icon"   # 뜻이 분명한 말은 자동으로도

    out = _ask(base, base_svg=ICON, messages=[{"role": "user", "content": "선을 더 굵게"}])   # 아이콘 답 뒤 — 대화창이 고른 아이콘을 실어 보냄
    assert out["kind"] == "icon" and seen[-1] == ("선을 더 굵게", ICON, "") and "고쳤어요" in out["content"]
    assert "속성 카드" in out["content"]   # 굵기는 칠판 펜이 정함 — 「굵게」면 바꾸는 곳을 알려 줌

    png = io.BytesIO()
    from PIL import Image
    Image.new("RGB", (4, 4), "white").save(png, "PNG")
    url = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()
    out = _ask(base, kind="icon", board_images=[url], messages=[{"role": "user", "content": "이 그림 아이콘으로"}])   # 고른 그림 + 아이콘 이름표 = 그 그림을 보고
    assert out["kind"] == "icon" and seen[-1] == ("이 그림 아이콘으로", "", url)

    with urllib.request.urlopen(base + "/api/models") as r:   # 기다리는 줄에 실제로 일하는 모델
        pass


def test_make_reads_board_image(monkeypatch):
    from PIL import Image
    png = io.BytesIO()
    Image.new("RGB", (6, 3), "red").save(png, "PNG")
    got = []
    monkeypatch.setattr(board_icon, "generate_svg", lambda key, ask, **kw: got.append(kw["image"]) or (ICON, kw["model"]))
    board_icon.make("k", "아이콘으로", image_url="data:image/png;base64," + base64.b64encode(png.getvalue()).decode())
    assert len(got) == 2 and got[0].size == (6, 3)
