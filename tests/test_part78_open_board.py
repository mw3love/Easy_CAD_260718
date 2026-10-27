"""2026-10-27 밤 — 비밀번호 없는 서버 = 칠판 주소가 곧 열쇠(사용자: Excalidraw처럼 처음엔 빈 칠판, 공유한 순간부터 남이 들어옴).
서버(`web/server.py`): 전체 칠판 목록은 숨기고 아는 이름(`?names=`)만, `/api/session?board=` = 그 칠판이 있나(`exists` — 남의 링크면 이름을 물음),
서버 키 스위치(`--no-server-key` — 「🔑 내 키」 없는 KAIROS 요청은 `need_key`). 진짜 Handler를 시험 안에서 띄움.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))

DOC = {"format": "easycad-doc", "version": 1, "items": [{"type": "rect", "pos": [0, 0], "rect": [0, 0, 50, 30], "pen": "#ff1f1f1f", "width": 1, "style": 1, "fill": None}]}


@pytest.fixture
def server(tmp_path):
    import server as srv
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    srv.Handler.server_key = True
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", srv, tmp_path
    srv.Handler.server_key = True
    httpd.shutdown()


def _req(url, method="GET", body=None, headers=None):
    r = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(r, timeout=10) as res:
            return res.status, json.loads(res.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_open_server_hides_board_list_but_answers_known_names(server):
    base, _, _ = server
    for n in ("칠판-k7p2qx9m", "남의칠판-abcdefgh"):
        assert _req(f"{base}/api/doc/{urllib.request.quote(n)}", "PUT", DOC)[0] == 200
    assert _req(base + "/api/boards")[1] == {"boards": [], "hidden": True}                     # 전체 목록 = 남의 비밀 주소 → 숨김
    st, d = _req(base + "/api/boards?names=" + ",".join(map(urllib.request.quote, ["칠판-k7p2qx9m", "없는칠판-zzzzzzzz"])))
    assert st == 200 and [b["name"] for b in d["boards"]] == ["칠판-k7p2qx9m"] and d["boards"][0]["items"] == 1   # 아는 이름만, 없는 것(저장 안 한 새 칠판)은 빠짐
    ss = _req(base + "/api/session?board=" + urllib.request.quote("남의칠판-abcdefgh"))[1]
    assert ss["auth"] is False and ss["ok"] is True and ss["exists"] is True                    # 남이 준 링크 = 있는 칠판(화면이 이름을 물음)
    assert _req(base + "/api/session?board=" + urllib.request.quote("칠판-새것새것새것"))[1]["exists"] is False   # 새 비밀 주소 = 아직 없음


def test_password_server_still_lists_boards(server):
    base, srv, _ = server
    assert _req(f"{base}/api/doc/main", "PUT", DOC)[0] == 200
    srv.Handler.password = "pw1234"
    try:
        st, _ = _req(base + "/api/boards")
        assert st == 401                                                                        # 비밀번호 서버 = 로그인 먼저(전처럼)
    finally:
        srv.Handler.password = ""


def test_server_key_switch_needs_my_key(server):
    base, srv, _ = server
    srv.Handler.server_key = False
    st, d = _req(base + "/api/models")
    assert st == 503 and d["need_key"] is True and "내 KAIROS 키" in d["error"]                 # 키 없이 = 「🔑 내 키」 안내(대화창이 키 칸을 엶)
    assert _req(base + "/api/session")[1]["server_key"] is False
    h = srv.Handler.__new__(srv.Handler)                                                       # 내 키가 있으면 그 키 — 서버 키는 안 씀
    h.headers = {"X-Kairos-Key": "sk-mykey-123456"}
    assert h._key() == "sk-mykey-123456"
    h.headers = {}
    assert h._key() == ""
