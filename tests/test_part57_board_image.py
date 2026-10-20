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
        assert "sources" not in json.loads(r.read()) and seen[-1] == "송신탑 그려줘"   # 날짜 말이 없으면 오늘 날짜도 안 붙임(붙이면 그림에 써 넣었음)
    assert "[오늘 날짜: " in seen[0]   # 「내일의 전주 날씨」 — 날짜 말이 있으면 오늘 날짜(그림 모델은 오늘을 모름)


def test_followup_keeps_first_request_and_facts():
    """그림 뒤 「날짜도 넣어 줘」(2026-10-20) — 마지막 말만이 아니라 처음 요청·찾은 정보를 이어서."""
    ms = [{"role": "user", "content": "내일의 전주 날씨를 고흐 느낌으로 그려줘."},
          {"role": "assistant", "content": "웹에서 찾은 정보로 그렸어요(sonar-x).\n- 최저 12℃, 최고 20℃ [4]\n\n그림 후보 2장 — 마음에 드는 것을 눌러 칠판에 붙여요"},
          {"role": "user", "content": "내일 날짜도 같이 그림에 반영하면 좋을듯한데"}]
    fu = board_image.followup(ms)
    assert fu["asks"] == ["내일의 전주 날씨를 고흐 느낌으로 그려줘."] and "최저 12℃, 최고 20℃" in fu["facts"] and "[4]" not in fu["facts"]
    p = board_image.followup_prompt(fu, ms[-1]["content"])
    assert p.index("고흐") < p.index("날짜도") and "12℃" in p and "그대로" in p
    ms += [{"role": "assistant", "content": "앞 그림의 …\n\n그림 후보 2장 — …"}, {"role": "user", "content": "제목 더 크게"}]   # 세 번째도 줄기를 이어 감
    fu = board_image.followup(ms)
    assert fu["asks"] == ["내일의 전주 날씨를 고흐 느낌으로 그려줘.", "내일 날짜도 같이 그림에 반영하면 좋을듯한데"] and "12℃" in fu["facts"]
    assert board_image.followup([{"role": "user", "content": "a"}, {"role": "assistant", "content": "그냥 답"}, {"role": "user", "content": "날짜도"}]) is None


def test_server_image_followup_routes_and_carries_context(server, monkeypatch):
    base, _ = server
    import server as srv
    seen = []
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, base_url="": seen.append(prompt) or {"images": [(JPG, "jpg")], "model": "img-m", "credits": 10.4})
    msgs = [{"role": "user", "content": "송신탑을 수채화로 그려줘"}, {"role": "assistant", "content": "그림 후보 2장 — 마음에 드는 것을 눌러 칠판에 붙여요"},
            {"role": "user", "content": "날짜도 넣어 줘"}]   # 종류 없이 — 그림 뒤 고칠 말이면 그림으로
    body = json.dumps({"board": "그림", "messages": msgs}).encode()
    with urllib.request.urlopen(urllib.request.Request(base + "/api/chat", data=body, method="POST", headers={"Content-Type": "application/json"})) as r:
        out = json.loads(r.read())
    assert out["kind"] == "image" and "수채화" in seen[-1] and "날짜도 넣어 줘" in seen[-1] and out["caption"] == "송신탑을 수채화로 그려줘"


def test_server_image_followup_edits_picked_image(server, monkeypatch):
    """고른 그림 고치기(2026-10-20, KAIROS 문서 `input_images`) — 칠판이 보낸 그 그림 파일을 data: 주소로 넣고 1장만, 원본 유지 지시."""
    base, data = server
    import server as srv
    calls = []
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, base_url="", **kw: calls.append((prompt, kw)) or {"images": [(JPG, "jpg")], "model": "img-m", "credits": 22.9})
    (data / "그림.img").mkdir()
    (data / "그림.img" / "1_aaaaaa.png").write_bytes(PNG)
    msgs = [{"role": "user", "content": "송신탑을 고흐 풍으로 그려줘"}, {"role": "assistant", "content": "그림 후보 2장 — 마음에 드는 것을 눌러 칠판에 붙여요"},
            {"role": "user", "content": "날짜도 넣어 줘"}]

    def ask(url):
        body = json.dumps({"board": "그림", "base_image": url, "messages": msgs}).encode()
        with urllib.request.urlopen(urllib.request.Request(base + "/api/chat", data=body, method="POST", headers={"Content-Type": "application/json"})) as r:
            return json.loads(r.read())
    out = ask("/api/img/" + urllib.parse.quote("그림") + "/1_aaaaaa.png")
    prompt, kw = calls[-1]
    assert kw["n"] == 1 and kw["input_images"][0].startswith("data:image/png;base64,") and "그대로 유지" in prompt and "날짜도 넣어 줘" in prompt
    assert out["kind"] == "image" and "고른 그림을 그대로" in out["content"]
    ask("/api/img/" + urllib.parse.quote("남의칠판") + "/1_aaaaaa.png")   # 다른 칠판 그림 = 못 씀 → 앞 요청 이어 새로 그리기
    assert "input_images" not in calls[-1][1] and "송신탑을 고흐 풍으로" in calls[-1][0]


def test_server_board_images_are_edited_and_not_logged(server, monkeypatch):
    """칠판에서 고른 그림 고치기(2026-10-20) — 요청에만 실린 data: 그림을 input_images로, 그림 말이 있으면 앞 대화 없이도 그림 길."""
    base, data = server
    import server as srv
    calls = []
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, base_url="", **kw: calls.append((prompt, kw)) or {"images": [(JPG, "jpg")], "model": "img-m", "credits": 22.9})
    img = "data:image/jpeg;base64,/9j/AAAA"
    body = json.dumps({"board": "그림", "board_images": [img, "javascript:alert(1)"], "messages": [{"role": "user", "content": "날짜 넣어 줘"}]}).encode()
    with urllib.request.urlopen(urllib.request.Request(base + "/api/chat", data=body, method="POST", headers={"Content-Type": "application/json"})) as r:
        out = json.loads(r.read())
    prompt, kw = calls[-1]
    assert out["kind"] == "image" and kw["input_images"] == [img] and kw["n"] == 1 and "그대로 유지" in prompt and "칠판에서 고른 그림 1장" in out["content"]
    assert board_image.edit_prompt("둘을 합쳐 줘", 2).startswith("넣은 이미지 2장")
