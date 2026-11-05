"""2026-11-05 — 칠판 그림 따로 보내기(사용자: 노트북에서 큰 칠판이 다 뜨기까지 5초 — 검증 본부 4.2MB 중 75%가 그림).
웹 화면(`?lite=1`)에만 그림 데이터 대신 주소(`_ref`)를 보내고, 그림은 지문 이름(`/api/blob/`)으로 오래 기억시킨다.
디스크·데스크톱이 받는 칠판은 그대로 통째, 채우기 전에 옮긴 그림(`data: ''`)은 서버 데이터를 지킨다(`web/docblobs.py`).
"""
import base64
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

JPG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 30
B64 = base64.b64encode(JPG).decode()


def _img(uid, data, x=0):
    return {"type": "image", "pos": [x, 0], "rect": [0, 0, 100, 80], "data": data, "uid": uid}


@pytest.fixture
def server(tmp_path):
    import server as srv
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()


def _req(url, method="GET", body=None):
    r = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as res:
            return res.status, res.read(), dict(res.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def _put(base, items):
    code, _, _ = _req(f"{base}/api/doc/blobtest", "PUT", {"format": "easycad-doc", "version": 1, "items": items})
    assert code == 200


def _disk(tmp):
    with open(os.path.join(tmp, "blobtest.ecad"), encoding="utf-8") as f:
        return json.load(f)


def test_lite_doc_sends_address_and_blob_is_cached(server):
    base, tmp = server
    _put(base, [_img("a", B64), _img("b", "data:image/jpeg;base64," + B64, 200), _img("c", "abc")])   # c = 작은 그림 = 그대로
    _, raw, _ = _req(f"{base}/api/doc/blobtest?lite=1")
    a, b, c = json.loads(raw)["items"]
    assert a["data"] == "" and a["_ref"].startswith("/api/blob/") and a["_ref"].endswith(".jpg") and a["_pre"] == ""
    assert b["data"] == "" and b["_ref"] == a["_ref"] and b["_pre"] == "data:image/jpeg;base64,"   # 같은 그림 = 같은 주소(한 번만 받음)
    assert c["data"] == "abc" and "_ref" not in c
    code, body, hd = _req(base + a["_ref"])
    assert code == 200 and body == JPG and "immutable" in hd["Cache-Control"] and hd["Content-Type"] == "image/jpeg"
    _, full, _ = _req(f"{base}/api/doc/blobtest")   # 데스크톱·내려받기 = 그대로 통째
    assert json.loads(full)["items"][0]["data"] == B64
    _, since, _ = _req(f"{base}/api/since/blobtest?lite=1&rev=0")   # 받아 오기도 가볍게
    assert json.loads(since)["items"][0]["data"] == ""


def test_non_canonical_base64_stays_inline(server):
    base, _ = server
    odd = B64[:76] + "\n" + B64[76:]   # 줄바꿈 든 base64 = 브라우저가 다시 만든 글과 달라짐 → 빼지 않음
    _put(base, [_img("a", odd)])
    _, raw, _ = _req(f"{base}/api/doc/blobtest?lite=1")
    assert json.loads(raw)["items"][0]["data"] == odd


def test_moved_before_fill_keeps_server_data(server):
    base, tmp = server
    _put(base, [_img("a", B64), _img("b", B64, 200)])
    code, _, _ = _req(f"{base}/api/patch/blobtest", "POST", {"base": 1, "upsert": [_img("a", "", 50)], "delete": []})   # 채우기 전에 옮김
    assert code == 200
    a = _disk(tmp)["items"][0]
    assert a["pos"] == [50, 0] and a["data"] == B64
    _put(base, [_img("a", "", 70), dict(_img("b", B64, 200), _ref="/api/blob/x.jpg")])   # 통째 저장도 같음, `_ref`는 디스크에 안 남김
    a, b = _disk(tmp)["items"]
    assert a["pos"] == [70, 0] and a["data"] == B64 and "_ref" not in b


def test_fonts_are_cached(server):
    base, _ = server
    _, _, hd = _req(f"{base}/fonts.css")
    assert "max-age=2592000" in hd.get("Cache-Control", "")
