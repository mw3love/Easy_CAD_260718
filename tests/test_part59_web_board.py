"""§8 항목61 ④-2(2026-10-19) — 데스크톱 「웹 칠판」: 서버 칠판 목록·받기·올리기(`easycad/fileio/web_board.py`)와
「파일 › 웹 칠판」 열기·올리기(host_fileio `_web_open`·`_web_upload`). 진짜 서버(`web/server.py` Handler)를 시험 안에서 띄움 — 가짜 없음.
"""
import os
import sys
import threading
from http.server import ThreadingHTTPServer

import pytest
from _shared import *  # noqa: F401,F403  (QApplication·CanvasWindow·_mk_rect)
from PyQt6.QtWidgets import QInputDialog, QMessageBox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))
from easycad.app_settings import app_settings  # noqa: E402
from easycad.fileio import web_board  # noqa: E402


@pytest.fixture
def server(tmp_path):
    import server as srv
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", srv, tmp_path
    srv.Handler.password = ""
    httpd.shutdown()


DOC = {"format": "easycad-doc", "version": 1, "items": [{"type": "rect", "pos": [0, 0], "rect": [0, 0, 50, 30], "pen": "#ff1f1f1f", "width": 1, "style": 1, "fill": None}]}


def test_client_put_list_get_and_password(server):
    base, srv, data = server
    cl = web_board.WebBoardClient(base)
    assert cl.list_boards() == []
    assert cl.put_doc("송신소_도면", DOC) == 1
    (data / "송신소_도면.prev.ecad").write_text("{}", encoding="utf-8")   # 되돌림용 앞 판은 목록에 안 나옴
    boards = cl.list_boards()
    assert [b["name"] for b in boards] == ["송신소_도면"] and boards[0]["items"] == 1
    got = cl.get_doc("송신소_도면")
    assert got["items"][0]["type"] == "rect" and got["items"][0]["uid"] and got["rev"] == 1   # 서버가 이름표·판 번호를 붙임
    with pytest.raises(web_board.WebBoardError, match="없어요"):
        cl.get_doc("없는칠판")
    with pytest.raises(web_board.WebBoardError, match="이름"):
        cl.put_doc("a/b", DOC)
    srv.Handler.password = "pw"
    with pytest.raises(web_board.WebBoardError, match="비밀번호가 필요"):
        web_board.WebBoardClient(base).list_boards()
    with pytest.raises(web_board.WebBoardError, match="맞지 않아요"):
        web_board.WebBoardClient(base, "틀림").list_boards()
    assert web_board.WebBoardClient(base, "pw").put_doc("송신소_도면", DOC) == 2
    assert web_board.clean_name(" UHD 계통도.v2 ") == "UHD_계통도v2"


def test_client_unreachable_server_message():
    with pytest.raises(web_board.WebBoardError, match="연결하지 못했어요"):
        web_board.WebBoardClient("http://127.0.0.1:9", timeout=2).list_boards()


def test_desktop_upload_then_open_from_web(server, monkeypatch):
    base, srv, data = server
    s = app_settings()
    s.setValue("web_board/url", base)
    s.setValue("web_board/password", "")
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    _mk_rect(w._scene, w.make_pen(), 100, 0, 40, 30)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("UHD 계통도", True)))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)   # 「올렸어요」 창 — 닫기
    w._web_upload()
    got = web_board.WebBoardClient(base).get_doc("UHD_계통도")
    assert sum(1 for it in got["items"] if it["type"] == "rect") == 2
    assert w._active_doc.web_board == "UHD_계통도"
    assert "🌐 UHD_계통도" in w._tabs.tabText(w._tabs.currentIndex())   # 파일 경로 없는 탭 = 올린 칠판 이름

    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: (asked.append(a[2]), QMessageBox.StandardButton.No)[1]))
    w._open_new_tab()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("UHD_계통도", True)))
    w._web_upload()                                   # 다른 탭에서 같은 이름 → 덮어쓸지 물음(아니오 = 안 올림)
    assert asked and "이미 있어요" in asked[0]
    assert sum(1 for it in web_board.WebBoardClient(base).get_doc("UHD_계통도")["items"] if it["type"] == "rect") == 2

    n_tabs = len(w._docs)
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda parent, title, label, rows, *a, **k: (rows[0], True)))
    w._web_open()
    assert len(w._docs) == n_tabs + 1
    assert w._active_doc.web_board == "UHD_계통도" and w._doc_path is None and not w._active_doc.dirty
    assert "🌐 UHD_계통도" in w._tabs.tabText(w._tabs.currentIndex())
    assert sum(1 for it in w._scene.items() if type(it).__name__ == "_RectItem") == 2
