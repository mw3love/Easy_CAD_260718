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


def test_board_title_is_separate_from_address_and_people_per_board(server):
    """2026-10-28 사용자 — 칠판 이름 = 문서 `title`(주소 그대로라 남에게 준 링크가 안 끊김), 칠판 판 줄마다 지금 접속자(개수 대신)."""
    base, _, _ = server
    n = "k7p2qx9m"
    assert _req(f"{base}/api/patch/{n}", "POST", {"upsert": [], "delete": []})[0] == 200               # 열 때 빈 칠판을 바로 만듦(App) — 칠판 코드로도 찾힘
    assert [b["name"] for b in _req(base + "/api/boards?code=" + n)[1]["boards"]] == [n]
    assert _req(f"{base}/api/patch/{n}", "POST", {"meta": {"title": "송신소 점검"}})[0] == 200          # 이름 바꾸기 = 문서 이름만
    b = _req(base + "/api/boards?names=" + n)[1]["boards"][0]
    assert b["title"] == "송신소 점검" and b["items"] == 0
    assert _req(base + "/api/session?board=" + n)[1]["title"] == "송신소 점검"                        # 받은 링크의 이름 묻는 창 머리
    assert _req(f"{base}/api/doc/{n}", "PUT", DOC)[0] == 200                                           # 통째 저장(파일 열기·데스크톱 올리기) = 내용만 — 이름은 그대로
    assert _req(base + "/api/boards?names=" + n)[1]["boards"][0]["title"] == "송신소 점검"
    assert _req(f"{base}/api/presence/{n}", "POST", {"id": "c1", "name": "가"})[0] == 200
    ppl = _req(base + "/api/people?names=" + ",".join([n, "zzzzzzzz"]))[1]["people"]
    assert ppl == {n: [{"id": "c1", "name": "가"}], "zzzzzzzz": []}


def test_delete_board_moves_to_trash_and_blocks_revival(server):
    """2026-10-28 칠판 지우기 — 파일 전부 휴지통(`trash/<이름>-<때>/`), 지운 이름은 기억해 열기·저장이 되살리지 않음(410), 게시 링크도 끊김."""
    base, _, data = server
    n = "d3l3t3m3"
    assert _req(f"{base}/api/doc/{n}", "PUT", DOC)[0] == 200
    assert _req(f"{base}/api/chatlog/{n}", "PUT", {"messages": []})[0] == 200
    assert _req(f"{base}/api/publish/{n}", "POST", {"on": True})[0] == 200
    (data / f"{n}.img").mkdir()
    (data / f"{n}.img" / "1_abcdef.png").write_bytes(b"x")
    keep = "d3l3t3m3x"   # 이름이 앞만 같은 칠판은 그대로(「이름 + .」만 옮김)
    assert _req(f"{base}/api/doc/{keep}", "PUT", DOC)[0] == 200
    st, d = _req(f"{base}/api/delete/{n}", "POST", {})
    assert st == 200 and d["moved"] == 3                                            # .ecad·.chat.json·.img/
    assert not any(p.name == n or p.name.startswith(n + ".") for p in data.iterdir())
    trash = [p for p in (data / "trash").iterdir() if p.is_dir()]
    assert len(trash) == 1 and (trash[0] / f"{n}.ecad").exists() and (trash[0] / f"{n}.img" / "1_abcdef.png").exists()
    assert (data / f"{keep}.ecad").exists()
    assert _req(base + "/api/session?board=" + n)[1].get("gone") is True
    assert _req(f"{base}/api/doc/{n}")[0] == 410
    assert _req(f"{base}/api/since/{n}?rev=0")[0] == 410
    assert _req(f"{base}/api/patch/{n}", "POST", {"upsert": [], "delete": []})[0] == 410   # 열어 둔 창의 저장
    assert _req(f"{base}/api/doc/{n}", "PUT", DOC)[0] == 410
    assert not (data / f"{n}.ecad").exists()
    assert n not in json.loads((data / "publish.json").read_text(encoding="utf-8"))           # 게시 링크도 끊김
