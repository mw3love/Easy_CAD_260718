"""웹 칠판 PDF 보기 카드(2026-10-21 사용자: 휠로 쭉 보다가 Alt+드래그로 칠판에 오려 오기) — 서버 `web/pdfview.py`·`/api/pdf/...`.

PDF 원본은 데이터 폴더 `<칠판>.pdf/`에, 칠판엔 주소·쪽 크기·첫 쪽 작은 그림·글(찾기용)만. 쪽 그림·오려 낸 그림·그 부분 글은 그때그때.
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
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

pymupdf = pytest.importorskip("pymupdf")


def _pdf() -> bytes:
    """2쪽 — 1쪽 위 절반에 「Alpha」, 아래 절반에 「Bravo」, 2쪽(가로)에 「Charlie」."""
    d = pymupdf.open()
    p = d.new_page(width=600, height=800)
    p.insert_text((50, 100), "Alpha", fontsize=24)
    p.insert_text((50, 600), "Bravo", fontsize=24)
    d.new_page(width=800, height=600).insert_text((50, 100), "Charlie", fontsize=24)
    return d.tobytes()


@pytest.fixture
def server(tmp_path):
    import server as srv
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()


def _post(url, data, name="보고서.pdf"):
    req = urllib.request.Request(url, data=data, method="POST", headers={"X-File-Name": urllib.parse.quote(name)})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


import urllib.parse  # noqa: E402


def _get(url):
    with urllib.request.urlopen(url) as r:
        return r.headers.get("Content-Type"), r.read()


def test_upload_keeps_file_on_server_and_returns_card_fields(server):
    base, data_dir = server
    out = _post(base + "/api/pdf/e2e_b", _pdf())
    assert out["url"].startswith("/api/pdf/e2e_b/") and out["name"] == "보고서.pdf"
    assert out["pages"] == 2 and out["sizes"] == [[600.0, 800.0], [800.0, 600.0]]
    assert out["thumb"].startswith("data:image/jpeg;base64,")
    assert "[1쪽]" in out["text"] and "Charlie" in out["text"]           # 찾기·대화 재료
    assert "\n\n" not in out["text"]                                    # 쪽 배치대로 뽑힌 여러 빈 줄은 한 줄로
    assert len(os.listdir(data_dir / "e2e_b.pdf")) == 1                  # 원본은 서버 폴더에(칠판 파일엔 주소만)
    ct, body = _get(base + out["url"])
    assert ct == "application/pdf" and body.startswith(b"%PDF")


def test_page_image_clip_and_text(server):
    base, _ = server
    url = base + _post(base + "/api/pdf/e2e_b", _pdf())["url"]
    ct, jpg = _get(url + "/page/1?w=400")
    assert ct == "image/jpeg"
    pm = pymupdf.Pixmap(jpg)
    assert (pm.width, pm.height) == (400, 300)                           # 2쪽 = 가로 쪽, 폭에 맞춘 높이
    ct, png = _get(url + "/clip/0?r=0,0,1,0.5")
    pm = pymupdf.Pixmap(png)
    assert ct == "image/png" and abs(pm.width - 600 * 200 / 72) <= 1 and abs(pm.height - 400 * 200 / 72) <= 1   # 위 절반, 200dpi(반올림 1px)
    _, t = _get(url + "/text/0?r=0,0,1,0.5")
    assert json.loads(t)["text"] == "Alpha"                              # 오린 부분 글만
    _, t = _get(url + "/text/0?r=0,0.5,1,1")
    assert json.loads(t)["text"] == "Bravo"


def test_bad_requests(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base + "/api/pdf/e2e_b", b"not a pdf")
    assert e.value.code == 400
    url = base + _post(base + "/api/pdf/e2e_b", _pdf())["url"]
    for bad in ("/page/9", "/clip/0?r=1,2", "/clip/0?r=0.5,0.5,0.5,0.5"):
        with pytest.raises(urllib.error.HTTPError) as e:
            _get(url + bad)
        assert e.value.code == 400, bad
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(base + "/api/pdf/other/1_abcdef")
    assert e.value.code == 404
