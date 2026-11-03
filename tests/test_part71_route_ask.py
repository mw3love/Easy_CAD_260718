"""§8 항목64(2026-10-23) — 웹 칠판 대화창 되묻기: 애매하고 비싼 갈림길에서만 한 번, 버튼으로(`route.decide`·서버 `/api/chat` kind "ask").

판단 모델은 가짜(test_part63과 같은 `_Http`). 점수는 0단계 실측(jev-latest 41문항 × 3번, docs/history/2026-10.md 끝)에서 옮김.
"""
import json
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from test_part63_route import _Http
from easycad.ai import board_chat, route


def _decide(text, answer, **kw):
    old = os.environ.pop("EASYCAD_ROUTE", None)   # conftest가 규칙으로 고정해 둠
    try:
        return route.decide("k", text, http=_Http(answer), base_url="https://g", **kw)
    finally:
        if old is not None:
            os.environ["EASYCAD_ROUTE"] = old


def test_close_costly_scores_ask():
    # 「발표 자료 만들어 줘」 — 실측 chat 0.52 / report 0.47(같은 질문이 3번 중 chat 2·report 1)
    assert _decide("발표 자료 만들어 줘", ("chat", 0.42, {"chat": 0.52, "report": 0.47, "image": 0.01})) == ("chat", "ai", ["chat", "report"])
    # 고른 길(chat)과 점수 1등(report)이 어긋남 — 실측 2026-10-23(같은 질문 4번 중 1번)
    assert _decide("발표 자료 만들어 줘", ("chat", 0.39, {"chat": 0.486, "report": 0.494, "image": 0.01})) == ("chat", "ai", ["chat", "report"])
    assert _decide("오늘 한 일 정리",("report", 0.3, {"report": 0.41, "chat": 0.26, "board": 0.19}))[2] == ["report", "chat"]


def test_clear_or_cheap_or_word_fixed_does_not_ask():
    assert _decide("엑셀 VLOOKUP", ("chat", 1.0, {"chat": 1.0, "search": 0.0}))[2] == []                      # 분명함
    assert _decide("KBS 수신료 지금 어떻게 걷어?", ("chat", 0.5, {"chat": 0.59, "search": 0.41}))[2] == []   # 가깝지만 둘 다 싼 길
    # 「고흐 날씨」 — search 0.6 / image 0.39로 가깝지만 「그려줘」 낱말이 길을 정함(말이 분명)
    assert _decide("내일의 전주 날씨를 고흐 느낌으로 그려줘.", ("search", 0.5, {"search": 0.6, "image": 0.39})) == ("image", "ai", [])
    # 비싼 길이 3등이면 안 물음(1·2등 안에 있어야) — 옛 정리정돈 길은 2026-10-25 뺐다
    assert _decide("이거 정리해 줘", ("chat", 0.46, {"chat": 0.55, "search": 0.31, "report": 0.11}))[2] == []


def test_icon_words_ask_by_words_and_remember():
    # 판단 모델엔 아이콘 길이 없어 「펭귄 아이콘」을 image 1.0으로 확신 — 낱말로 물음(판단 모델은 안 부름)
    http = _Http(("image", 1.0, {"image": 1.0}))
    assert route.decide("k", "펭귄 아이콘 그려줘", http=http) == ("image", "rules", ["image", "icon"])
    assert http.calls == []
    assert route.decide("k", "KBS 로고 그려 줘")[2] == ["image", "icon"]
    assert route.decide("k", "펭귄 아이콘 그려줘", prefs={"icon|image": "icon"}) == ("icon", "rules", [])   # 두 번 연달아 고른 길 = 바로
    assert route.decide("k", "펭귄 아이콘 그려줘", prefs={"icon|image": "nope"})[2] == ["image", "icon"]
    assert not board_chat.maybe_icon("파라볼라 안테나를 SVG로 그려 줘")   # 뜻이 분명 — 바로 아이콘
    assert not board_chat.maybe_icon("아이콘 만드는 법 알려줘")
    assert not board_chat.maybe_icon("엑셀 아이콘 어디 있어?")
    assert route.route("k", "펭귄 아이콘 그려줘") == ("image", "rules")   # 안 물었으면 갈 길은 그대로(주간 자가 시험 `CASES`)


def test_diagram_word_구성도():   # 2026-10-23 그림으로 갔음 → 11-03부터 🔷 도형(고칠 수 있는 상자 + 화살표)
    assert route.adjust("송신소 구성도 만들어 줘", "image", 0.8, {"image": 0.8, "chat": 0.2}) == "diagram"
    assert board_chat.guess_kind("송신소 구성도 그려 줘") == "diagram"


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    made = []
    monkeypatch.setattr(srv.board_icon, "make", lambda key, ask, base_svg="", image_url="", base_url="", **_: made.append(ask) or
                        {"svgs": ["<svg/>"], "model": "icon-m", "elapsed": 1.0})
    monkeypatch.setattr(srv.board_image, "make", lambda *a, **k: made.append("image") or {"images": [], "model": "img-m", "elapsed": 1.0}, raising=False)
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", made
    httpd.shutdown()


def _post(base, **body):
    req = urllib.request.Request(base + "/api/chat", data=json.dumps({"board": "되묻기", **body}).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_server_asks_before_making(server):
    base, made = server
    q = [{"role": "user", "content": "펭귄 아이콘 그려줘"}]
    out = _post(base, messages=q)
    assert out["kind"] == "ask" and out["choices"] == ["image", "icon"] and out["key"] == "icon|image" and out["default"] == "image"
    assert made == []                                                   # 만들기 전에 물음 — 크레딧 안 씀
    assert _post(base, kind="icon", messages=q)["kind"] == "icon"       # 버튼 = 그 길 이름표로 다시
    assert _post(base, ask_pref={"icon|image": "icon"}, messages=q)["kind"] == "icon"   # 기억된 길이면 안 물음
    assert made == ["펭귄 아이콘 그려줘", "펭귄 아이콘 그려줘"]


def test_pick_from_typed_reply():
    both = ["image", "icon"]
    assert route.pick_from("선으로 해 줘", both) == "icon"
    assert route.pick_from("선 그림으로", both) == "icon"          # 「그림」보다 「선 그림」이 먼저
    assert route.pick_from("그림인데 수채화로", both) == "image"
    assert route.pick_from("음 잘 모르겠어", both) == ""            # 못 알아들음 — 서버는 원래 1등 길(다시 안 물음)
    assert route.pick_from("문서로", ["chat", "report"]) == "report"
    assert route.pick_from("문서로", both) == ""                    # 버튼에 없는 길은 안 고름


def test_server_typed_reply_and_remembered_flag(server):
    base, made = server
    q = [{"role": "user", "content": "펭귄 아이콘 그려줘\n선으로 해 줘"}]
    out = _post(base, ask_add="선으로 해 줘", ask_reply={"choices": ["image", "icon"], "default": "image"}, messages=q)
    assert out["kind"] == "icon" and "remembered" not in out
    out = _post(base, ask_add="음 잘 모르겠어", ask_reply={"choices": ["image", "icon"], "default": "icon"}, messages=q)
    assert out["kind"] == "icon"                                     # 못 알아들으면 원래 1등 길 — 다시 묻지 않음
    out = _post(base, ask_pref={"icon|image": "icon"}, messages=[{"role": "user", "content": "펭귄 아이콘 그려줘"}])
    assert out["remembered"] == {"key": "icon|image", "choices": ["image", "icon"]}   # 대화창이 「그림으로 바꾸기」를 붙임
    assert "remembered" not in _post(base, kind="icon", messages=[{"role": "user", "content": "펭귄 아이콘 그려줘"}])   # 버튼·이름표로 고른 건 기억이 아님


def test_diagram_draw_goes_to_shapes_and_style_words_mean_picture():
    """2026-11-03 사용자 검토 — 「손으로 그린 듯한 … 계통도를 그려 줘. 연필 스케치 느낌」이 「계통도」 때문에 대화로 떨어져 SVG 코드 글이 나왔음.
    그림 느낌 말 = 그림. 없이 「계통도 그려 줘」 = 처음엔 아이콘 vs 그림을 물었지만 같은 날 저녁 사용자 결정으로 묻지 않고 🔷 도형(`board_diagram`)."""
    mine = "손으로 그린 듯한 방송 송신소 계통도를 그려 줘. 흰 종이에 연필 스케치 느낌. 상자 5개를 화살표로 연결."
    assert board_chat.guess_kind(mine) == "image" and route.adjust(mine, "image", 0.6, {"image": 0.6, "chat": 0.3}) == "image"
    assert route.decide("k", mine)[0] == "image"
    assert route.decide("k", "송신소 계통도 그려 줘") == ("diagram", "rules", [])
    assert route.decide("k", "송신소 계통도 그려 줘", prefs={"icon|image": "image"}) == ("diagram", "rules", [])   # 옛 갈림길 기억은 상관없음
    assert route.decide("k", "점검 순서 흐름도 만들어 줘")[0] == "diagram" and route.decide("k", "KBS 조직도 그려줘")[0] == "diagram"
    assert route.decide("k", "흐름도 그리는 방법 알려 줘") == ("chat", "rules", []) and route.decide("k", "구성도를 표로 정리해 줘")[0] != "diagram"


def test_chat_answer_svg_code_goes_to_picture_slot():
    """대화 답에 섞인 SVG 코드 = 코드는 빼서 그림 칸(`svgs` — 누르면 칠판에 도형), 「저장해 브라우저에서 열면」 문장도 뺌(2026-11-03 사용자 검토)."""
    ans = "**연필 느낌 계통도**입니다. 아래를 `송신소.svg`로 저장해 브라우저에서 열면 그림으로 볼 수 있습니다.\n\n```svg\n<svg xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"9\" height=\"9\"/></svg>\n```"
    out = board_chat.split_svg({"content": ans, "model": "m"})
    assert out["svgs"] == ['<svg xmlns="http://www.w3.org/2000/svg"><rect width="9" height="9"/></svg>'] and out["model"] == "m"
    assert "<svg" not in out["content"] and ".svg" not in out["content"] and "브라우저" not in out["content"]
    assert out["content"].startswith("**연필 느낌 계통도**입니다.") and out["content"].endswith(board_chat.SVG_NOTE)
    assert board_chat.split_svg({"content": "그냥 답"}) == {"content": "그냥 답"}


def test_link_and_site_words_need_web_meaning():
    """「마이크로웨이브 링크」·「송신 사이트」 = 장비·현장 말이라 검색 아님(2026-11-03 실검증 — 손그림 요청이 그리기 전 웹 검색을 거쳐 출처 5개가 붙었음)."""
    assert not board_chat._SEARCH_WORDS.search("스튜디오 → 마이크로웨이브 링크 → 송신기") and not board_chat._SEARCH_WORDS.search("송신 사이트 점검 순서")
    assert board_chat._SEARCH_WORDS.search("관련 링크 알려 줘") and board_chat._SEARCH_WORDS.search("KBS 웹사이트 주소 알려 줘")
