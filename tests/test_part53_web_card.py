"""§8 항목61 4-b(2026-10-18) — 웹 카드 서버 길목(`web/server.py` `link_info`): 칸 안에 넣어도 되나·제목·대표 그림.
브라우저는 넣기를 막았는지 알 수 없어 서버가 응답 머리말로 판단한다(실제 인터넷 없이 가짜 응답으로 시험)."""
import os
import sys
from email.message import Message

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

import server as srv  # noqa: E402


def _headers(**kw):
    m = Message()
    for k, v in kw.items():
        for one in (v if isinstance(v, list) else [v]):
            m[k.replace("_", "-")] = one
    return m


class _Resp:
    def __init__(self, headers):
        self.headers = headers


def test_frame_blocked_reads_xfo_and_csp():
    assert srv.frame_blocked(_headers(X_Frame_Options="DENY"))
    assert srv.frame_blocked(_headers(X_Frame_Options="SAMEORIGIN"))
    assert srv.frame_blocked(_headers(Content_Security_Policy="default-src 'self'; frame-ancestors 'self' https://a.com"))
    assert not srv.frame_blocked(_headers(Content_Security_Policy="frame-ancestors *"))
    assert not srv.frame_blocked(_headers(Content_Type="text/html"))


def test_link_info_title_thumb_and_embed(monkeypatch):
    page = ('<html><head><meta charset="utf-8"><title>옛 제목</title>'
            '<meta content="노래 제목 &amp; 가수" property="og:title"><meta property="og:image" content="/img/a.jpg"></head></html>').encode("utf-8")
    calls = []

    def fake_open(url, limit):
        calls.append(url)
        if url.endswith("/img/a.jpg"):
            return _Resp(_headers(Content_Type="image/jpeg")), b"\xff\xd8jpg"
        if "embed" in url:
            return _Resp(_headers(Content_Type="text/html")), b""
        return _Resp(_headers(Content_Type="text/html; charset=utf-8", X_Frame_Options="SAMEORIGIN")), page
    monkeypatch.setattr(srv, "_open", fake_open)
    out = srv.link_info("https://www.youtube.com/watch?v=x1", "https://www.youtube.com/embed/x1")
    assert out["title"] == "노래 제목 & 가수"                     # og:title 먼저, 속성 차례 상관없이
    assert out["frameable"] is True                              # 보기 페이지는 막아도 재생 주소는 허락
    assert out["thumb"].startswith("data:image/jpeg;base64,")
    assert "https://www.youtube.com/img/a.jpg" in calls          # 상대 주소 그림


def test_link_info_blocked_site_and_unreachable(monkeypatch):
    monkeypatch.setattr(srv, "_open", lambda url, limit: (_Resp(_headers(Content_Type="text/html", X_Frame_Options="DENY")), b"<title>NAVER</title>"))
    out = srv.link_info("https://www.naver.com")
    assert out["frameable"] is False and out["title"] == "NAVER" and out["thumb"] == ""

    def boom(url, limit):
        raise OSError("no network")
    monkeypatch.setattr(srv, "_open", boom)
    out = srv.link_info("https://intra.example")
    assert out == {"url": "https://intra.example", "embed": "", "title": "", "desc": "", "icon": "", "thumb": "", "frameable": False}   # 못 열어도 오류 없이 「모름」
