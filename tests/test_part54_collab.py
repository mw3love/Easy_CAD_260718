"""§8 항목61 ⓕ 공동작업 1단계(2026-10-18) — 도형 단위 합치기·연결 순번 ↔ uid·공용 비밀번호·게시·접속자(`web/collab.py`, `web/server.py`)."""
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
import collab  # noqa: E402


def _doc():
    return {"format": "easycad-doc", "version": 1, "layers": [{"id": "default"}], "items": [
        {"uid": "a", "type": "rect", "rect": [0, 0, 10, 10]},
        {"uid": "b", "type": "rect", "rect": [0, 0, 20, 20]},
        {"uid": "c", "type": "sarrow", "pts": [[0, 0], [5, 5]], "bind1": 0, "bind2": 1, "bind1_pt": [1, 1], "bind2_pt": [2, 2]}]}


def test_two_people_editing_different_items_both_survive_and_binds_follow_uids():
    d = _doc()
    # 갑: a를 고침, 을: 새 도형 d를 맨 앞에 넣음(을의 화면에선 순번이 다름) — 둘 다 같은 rev 0에서 출발
    d1 = collab.apply_patch(d, {"base": 0, "upsert": [{"uid": "a", "type": "rect", "rect": [0, 0, 99, 10]}]})
    d2 = collab.apply_patch(d1, {"base": 0, "upsert": [{"uid": "d", "type": "text", "text": "새 글"}]})
    assert d2["rev"] == 2 and [it["uid"] for it in d2["items"]] == ["a", "b", "c", "d"]
    assert d2["items"][0]["rect"][2] == 99 and d2["items"][3]["text"] == "새 글"
    assert (d2["items"][2]["bind1"], d2["items"][2]["bind2"]) == (0, 1)   # 화살표는 여전히 a·b에
    # a를 지우면 화살표 그 끝은 끊김(웹·데스크톱 규칙), 남은 연결은 새 순번으로
    d3 = collab.apply_patch(d2, {"delete": ["a"]})
    arrow = next(it for it in d3["items"] if it["uid"] == "c")
    assert arrow["bind1"] is None and arrow["bind1_pt"] is None and arrow["bind2"] == 0
    # 화살표를 uid로 붙여 보냄 → 저장은 순번
    d4 = collab.apply_patch(d3, {"upsert": [dict(arrow, bind1="d")], "meta": {"layers": [{"id": "default"}, {"id": "x"}], "rev": 999}})
    assert next(it for it in d4["items"] if it["uid"] == "c")["bind1"] == 2 and len(d4["layers"]) == 2 and d4["rev"] == 4


def test_ensure_uids_fills_missing_and_duplicates():
    d = {"items": [{"type": "rect"}, {"uid": "x"}, {"uid": "x"}]}
    assert collab.ensure_uids(d) is True
    us = [it["uid"] for it in d["items"]]
    assert len(set(us)) == 3 and us[1] == "x"
    assert collab.ensure_uids(d) is False


def test_presence_forgets_after_ttl():
    p = collab.Presence(ttl=10)
    assert p.ping("b", "1", "기자", now=100) == ["기자"]
    assert p.ping("b", "2", "작가", now=105) == ["기자", "작가"]
    assert p.ping("b", "2", "작가", now=112) == ["작가"]


@pytest.fixture
def server(tmp_path):
    import server as srv
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = "방송1234"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()
    srv.Handler.password = ""


def _req(url, method="GET", body=None, cookie=""):
    r = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode("utf-8"),
                               headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, None, e.headers


def test_server_password_patch_since_publish(server):
    base, data = server
    (data / "b1.ecad").write_text(json.dumps(_doc() | {"items": [{"type": "rect", "rect": [0, 0, 1, 1]}]}), encoding="utf-8")
    assert _req(base + "/api/session")[1] == {"auth": True, "ok": False}
    assert _req(base + "/api/doc/b1")[0] == 401                       # 비밀번호 전엔 못 봄
    assert _req(base + "/api/chat", "POST", {"messages": []})[0] == 401   # 크레딧도 못 씀
    assert _req(base + "/api/login", "POST", {"password": "틀림"})[0] == 403
    code, _, h = _req(base + "/api/login", "POST", {"password": "방송1234"})
    cookie = h["Set-Cookie"].split(";")[0]
    assert code == 200 and "HttpOnly" in h["Set-Cookie"]
    code, doc, h = _req(base + "/api/doc/b1", cookie=cookie)
    uid = doc["items"][0]["uid"]                                       # 서버가 처음 열 때 uid를 붙여 저장
    assert code == 200 and uid and json.loads((data / "b1.ecad").read_text(encoding="utf-8"))["items"][0]["uid"] == uid
    assert _req(base + f"/api/since/b1?rev={doc.get('rev', 0)}", cookie=cookie)[0] == 204
    code, out, _ = _req(base + "/api/patch/b1", "POST", {"base": 0, "upsert": [{"uid": "n1", "type": "text", "text": "가"}]}, cookie=cookie)
    assert code == 200 and out["rev"] == doc.get("rev", 0) + 1
    code, doc2, _ = _req(base + f"/api/since/b1?rev={doc.get('rev', 0)}", cookie=cookie)
    assert code == 200 and [it["uid"] for it in doc2["items"]] == [uid, "n1"]
    # 게시 — 켜면 토큰, 로그인 없이 보기만(고치기·대화 안 됨), 끄면 막힘, 다시 만들면 옛 링크 막힘
    code, pub, _ = _req(base + "/api/publish/b1", "POST", {"on": True}, cookie=cookie)
    tok = pub["token"]
    code, view, _ = _req(base + f"/api/pub/{tok}")
    assert code == 200 and len(view["items"]) == 2 and view["board"] == "b1"
    assert _req(base + "/api/patch/b1", "POST", {"upsert": []})[0] == 401
    tok2 = _req(base + "/api/publish/b1", "POST", {"on": True, "renew": True}, cookie=cookie)[1]["token"]
    assert tok2 != tok and _req(base + f"/api/pub/{tok}")[0] == 404 and _req(base + f"/api/pub/{tok2}")[0] == 200
    _req(base + "/api/publish/b1", "POST", {"on": False}, cookie=cookie)
    assert _req(base + f"/api/pub/{tok2}")[0] == 404
    # 접속자
    _req(base + "/api/presence/b1", "POST", {"id": "c1", "name": "기자"}, cookie=cookie)
    assert _req(base + "/api/presence/b1", "POST", {"id": "c2", "name": "작가"}, cookie=cookie)[1]["people"] == ["기자", "작가"]
