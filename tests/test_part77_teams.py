"""§8 항목67 팀별 칠판(2026-10-27) — 데이터 폴더 `teams.json` = 팀마다 비밀번호·KAIROS 키·칠판(`web/collab.py` `Teams`, `web/server.py` `_name`·`_key`).
끝의 기준(계획서): A팀 열쇠로 B팀 칠판의 길목이 전부 거절 · 목록에 B팀 칠판 없음 · 새 칠판은 A팀에 들어감 · 관리자는 다 열림 ·
팀 키가 대화에 쓰임 · `teams.json`이 없으면 그대로(→ test_part54)."""
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))
import collab  # noqa: E402

TEAMS = [{"name": "A팀", "password": "에이1234", "key": "key-of-team-A-0001", "boards": ["A회의"]},
         {"name": "B팀", "password": "비2345", "boards": ["B회의"]}]
DOC = {"format": "easycad-doc", "version": 1, "items": [{"uid": "u1", "type": "rect", "rect": [0, 0, 10, 10]}]}


@pytest.fixture
def srv(tmp_path):
    import server as s
    (tmp_path / "teams.json").write_text(json.dumps(TEAMS, ensure_ascii=False), encoding="utf-8")
    for name in ("A회의", "B회의", "main"):   # main = 팀 없는 옛 칠판(관리자만)
        (tmp_path / f"{name}.ecad").write_text(json.dumps(DOC), encoding="utf-8")
    s.Handler.data_dir, s.Handler.password = str(tmp_path), "관리자0000"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), s.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path, s
    httpd.shutdown()
    s.Handler.password = ""


def _req(url, method="GET", body=None, cookie="", headers=None, raw=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"))
    h = {"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {}), **(headers or {})}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method=method, data=data, headers=h)) as r:
            b = r.read()
            try:
                return r.status, (json.loads(b) if b else None), r.headers
            except ValueError:
                return r.status, b, r.headers
    except urllib.error.HTTPError as e:
        return e.code, None, e.headers


def _login(base, pw):
    code, _, h = _req(base + "/api/login", "POST", {"password": pw})
    assert code == 200, pw
    return h["Set-Cookie"].split(";")[0]


def q(name):
    return urllib.parse.quote(name)


def test_team_login_list_and_session(srv):
    base, data, _ = srv
    assert _req(base + "/api/session")[1] == {"auth": True, "ok": False}
    assert _req(base + "/api/login", "POST", {"password": "틀림"})[0] == 403
    a, b, admin = _login(base, "에이1234"), _login(base, "비2345"), _login(base, "관리자0000")
    assert len({a, b, admin}) == 3
    names = lambda c: sorted(x["name"] for x in _req(base + "/api/boards", cookie=c)[1]["boards"])
    assert names(a) == ["A회의"] and names(b) == ["B회의"] and names(admin) == ["A회의", "B회의", "main"]
    ss = _req(base + "/api/session?board=" + q("B회의"), cookie=a)[1]
    assert ss == {"auth": True, "ok": True, "team": "A팀", "board_ok": False, "home": "A회의"}
    assert _req(base + "/api/session?board=" + q("A회의"), cookie=a)[1]["board_ok"] is True
    assert _req(base + "/api/session?board=" + q("새칠판"), cookie=a)[1]["board_ok"] is True   # 아직 아무도 안 쓴 이름
    assert _req(base + "/api/session?board=main", cookie=admin)[1] == {"auth": True, "ok": True, "team": None, "board_ok": True}
    # 세션을 묻는 것(GET)만으로는 새 이름을 가져가지 않음
    assert "새칠판" not in json.loads((data / "teams.json").read_text(encoding="utf-8"))[0]["boards"]


def test_other_team_board_is_closed_on_every_path(srv):
    base, data, _ = srv
    a = _login(base, "에이1234")
    os.makedirs(data / "B회의.img"); (data / "B회의.img" / "1_abcdef.png").write_bytes(b"\x89PNG")
    os.makedirs(data / "B회의.pdf"); (data / "B회의.pdf" / "1_abcdef.pdf").write_bytes(b"%PDF-1.4")
    B = q("B회의")
    gets = [f"/api/doc/{B}", f"/api/since/{B}?rev=0", f"/api/chatlog/{B}", f"/api/meetdraft/{B}", f"/api/publish/{B}", f"/api/invite/{B}",
            f"/api/img/{B}/1_abcdef.png", f"/api/pdf/{B}/1_abcdef", f"/api/pdf/{B}/1_abcdef/page/0"]
    for p in gets:
        assert _req(base + p, cookie=a)[0] in (400, 404), p
    posts = [(f"/api/patch/{B}", {"upsert": [{"uid": "x", "type": "text"}]}), (f"/api/presence/{B}", {"id": "c", "name": "가"}),
             (f"/api/publish/{B}", {"on": True}), (f"/api/invite/{B}", {"on": True}), (f"/api/find/{B}", {"q": "가"}),
             (f"/api/meeting/{B}/live", {"segments": [{"text": "가"}]}), (f"/api/trace/{B}", {"data": "aGk="})]
    for p, body in posts:
        assert _req(base + p, "POST", body, cookie=a)[0] in (400, 404, 413), p
    assert _req(base + f"/api/pdf/{B}", "POST", raw=b"%PDF-1.4 x", cookie=a, headers={"Content-Type": "application/pdf"})[0] == 400
    assert _req(base + f"/api/meeting/{B}", "POST", raw=b"RIFF", cookie=a, headers={"Content-Type": "audio/wav", "X-File-Name": "a.wav"})[0] == 400
    for p in (f"/api/doc/{B}", f"/api/chatlog/{B}", f"/api/meetdraft/{B}"):
        assert _req(base + p, "PUT", {"items": []}, cookie=a)[0] == 400, p
    # 아무것도 안 바뀜 — B팀 문서·게시 표·팀 표
    assert json.loads((data / "B회의.ecad").read_text(encoding="utf-8")) == DOC
    assert not (data / "publish.json").exists() and not (data / "invite.json").exists() and not (data / "B회의.chat.json").exists()
    # 팀 없는 옛 칠판(main)도 팀은 못 엶 — 대소문자만 바꾼 이름으로 새로 만드는 것도(윈도에선 같은 파일)
    assert _req(base + "/api/doc/main", cookie=a)[0] == 400
    assert _req(base + "/api/patch/Main", "POST", {"upsert": []}, cookie=a)[0] == 400
    assert _req(base + "/api/patch/" + q("b회의"), "POST", {"upsert": []}, cookie=a)[0] == 400


def test_new_board_goes_to_the_team_that_saves_first(srv):
    base, data, _ = srv
    a, b, admin = _login(base, "에이1234"), _login(base, "비2345"), _login(base, "관리자0000")
    assert _req(base + "/api/doc/" + q("새판"), cookie=a)[0] == 404              # 보기만 = 아직 안 가져감
    assert _req(base + "/api/presence/" + q("새판"), "POST", {"id": "c", "name": "가"}, cookie=a)[0] == 200   # 접속 신호도 안 가져감
    assert "새판" not in json.loads((data / "teams.json").read_text(encoding="utf-8"))[0]["boards"]
    assert _req(base + "/api/patch/" + q("새판"), "POST", {"upsert": [{"uid": "n", "type": "text", "text": "가"}]}, cookie=a)[0] == 200
    saved = json.loads((data / "teams.json").read_text(encoding="utf-8"))
    assert saved[0]["boards"] == ["A회의", "새판"] and saved[0]["key"] == "key-of-team-A-0001"   # 사람이 적은 칸은 그대로
    assert [x["name"] for x in _req(base + "/api/boards", cookie=a)[1]["boards"]].count("새판") == 1
    assert _req(base + "/api/doc/" + q("새판"), cookie=b)[0] == 400                # B팀은 이제 못 씀
    assert _req(base + "/api/patch/" + q("새판"), "POST", {"upsert": []}, cookie=b)[0] == 400
    assert _req(base + "/api/doc/" + q("새판"), cookie=admin)[0] == 200            # 관리자는 다 열림
    # 대화 기록 저장(PUT)도 새 이름을 가져감
    assert _req(base + "/api/chatlog/" + q("B새판"), "PUT", {"messages": []}, cookie=b)[0] == 200
    assert "B새판" in json.loads((data / "teams.json").read_text(encoding="utf-8"))[1]["boards"]
    assert _req(base + "/api/chatlog/" + q("B새판"), cookie=a)[0] == 400


def test_team_key_is_used_for_kairos(srv, monkeypatch):
    base, _, s = srv
    seen = []
    monkeypatch.setattr(s.gw, "get_credit_balance", lambda key, base_url: (seen.append(key), (10.0, 100.0))[1])
    monkeypatch.setattr(s.gw, "resolve_api_key", lambda: "server-key-0000")
    a, b, admin = _login(base, "에이1234"), _login(base, "비2345"), _login(base, "관리자0000")
    for c in (a, b, admin):
        assert _req(base + "/api/credits", cookie=c)[1] == {"remaining": 10.0, "quota": 100.0}
    _req(base + "/api/credits", cookie=a, headers={"X-Kairos-Key": "my-own-key-0000"})   # 「🔑 내 키」가 먼저
    assert seen == ["key-of-team-A-0001", "server-key-0000", "server-key-0000", "my-own-key-0000"]


def test_invite_link_gives_that_boards_team_and_publish_still_works(srv):
    base, _, _ = srv
    a, b = _login(base, "에이1234"), _login(base, "비2345")
    tok = _req(base + "/api/invite/" + q("B회의"), "POST", {"on": True}, cookie=b)[1]["token"]
    code, _, h = _req(base + "/api/join", "POST", {"board": "B회의", "token": tok}, cookie=a)   # A팀 열쇠를 든 채 B팀 초대를 누름
    joined = h["Set-Cookie"].split(";")[0]
    assert code == 200 and joined == b and _req(base + "/api/doc/" + q("B회의"), cookie=joined)[0] == 200
    assert _req(base + "/api/join", "POST", {"board": "B회의", "token": "틀린토큰12345"})[0] == 403
    pub = _req(base + "/api/publish/" + q("B회의"), "POST", {"on": True}, cookie=b)[1]["token"]
    code, view, _ = _req(base + f"/api/pub/{pub}")                                     # 게시 링크 = 로그인 없이 보기
    assert code == 200 and view["board"] == "B회의"


def test_teams_without_admin_password_and_broken_file(srv):
    base, data, s = srv
    s.Handler.password = ""
    assert _req(base + "/api/session")[1]["auth"] is True and _req(base + "/api/doc/main")[0] == 401   # 팀만 있어도 잠김
    a = _login(base, "에이1234")
    assert _req(base + "/api/doc/main", cookie=a)[0] == 400
    (data / "teams.json").write_text("[{깨짐", encoding="utf-8")
    assert _req(base + "/api/session")[1]["auth"] is True                      # 깨진 파일 = 열리지 않음
    assert _req(base + "/api/doc/" + q("A회의"), cookie=a)[0] == 401          # 팀 열쇠도 안 통함
    assert _req(base + "/api/login", "POST", {"password": "에이1234"})[0] == 403
    (data / "teams.json").unlink()
    assert _req(base + "/api/session")[1] == {"auth": False, "ok": True}       # 파일을 지우면 예전처럼(비밀번호 없음 = 누구나)


def test_teams_clean_drops_bad_and_duplicate_entries(tmp_path):
    raw = [{"name": "A", "password": "1"}, {"name": "", "password": "2"}, {"name": "a", "password": "3"}, {"name": "C", "password": "1"},
           {"name": "D|E", "password": "4"}, {"name": "F", "password": "5", "boards": ["x", "X", 3]}, {"name": "G", "password": "6", "boards": ["x"]}, "글"]
    out = collab.Teams._clean(raw)
    assert [t["name"] for t in out] == ["A", "F", "G"]
    assert out[1]["boards"] == ["x"] and out[2]["boards"] == []   # 같은 칠판은 앞 팀이 가짐(대소문자 무시)
    assert collab.team_key(out[0]) != collab.edit_key("1")       # 팀 열쇠 ≠ 같은 비밀번호의 관리자 열쇠


def test_desktop_web_board_client_sees_only_its_team(srv):
    """데스크톱 「파일 › 웹 칠판」(`fileio/web_board.py`)도 같은 로그인 — 팀 비밀번호면 그 팀 목록, 남의 칠판은 알아듣는 말로 거절"""
    from easycad.fileio.web_board import WebBoardClient, WebBoardError
    base, data, _ = srv
    c = WebBoardClient(base, "에이1234")
    assert [b["name"] for b in c.list_boards()] == ["A회의"]
    assert c.get_doc("A회의")["items"][0]["uid"] == "u1"
    with pytest.raises(WebBoardError, match="다른 팀 칠판"):
        c.get_doc("B회의")
    with pytest.raises(WebBoardError, match="다른 팀이 쓰는 이름"):
        c.put_doc("B회의", DOC)
    assert c.put_doc("데스크톱판", DOC) == 1
    assert "데스크톱판" in json.loads((data / "teams.json").read_text(encoding="utf-8"))[0]["boards"]
