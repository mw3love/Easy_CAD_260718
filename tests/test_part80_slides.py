"""📽 발표 자료(§8 항목69, 2026-10-28): `easycad/ai/slides.py` 장 계획 다듬기·장 수·만들기(웹 재료 = 딥모드 `gather` 재사용)와 서버 `/api/chat` `kind: 'slides'`.

KAIROS는 부르지 않는다 — 가짜 클라이언트·가짜 Exa. 실제 호출은 따로 확인(2026-10-28, claude-sonnet-5-5: 계획 3.9~4.6초 · 5~6장 본문 14~22초 · 약 19크레딧).
"""
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

from easycad.ai import slides  # noqa: E402


def fake_client(answer, sent):
    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    sent.append(kw)
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer), finish_reason="stop")])
    return Client


def test_count_and_clean_plan():
    assert slides.count_of({"장 수": "5장"}) == 5 and slides.count_of({"장 수": "알아서"}) == 8 and slides.count_of({"장 수": "40장"}) == slides.MAX_SLIDES
    p = slides.clean_plan({"title": "점검", "slides": [{"title": "표지", "source": "board", "query": "x"}, {"title": " ", "source": "web"}, {"title": "숫자", "source": "ai", "query": "연료 기준"}, {"title": "끝", "source": "이상한"}]})
    assert [s["title"] for s in p["slides"]] == ["표지", "숫자", "끝"]
    assert p["slides"][0]["query"] is None and p["slides"][1]["source"] == "web" and p["slides"][2]["source"] == "ai"   # 검색 문장이 있는 ai = web, 모르는 출처 = ai
    with pytest.raises(ValueError):
        slides.clean_plan({"slides": [{"title": "하나"}]})
    e = slides.estimate(p)
    assert e["credits"][0] < e["credits"][1] and e["seconds"][0] < e["seconds"][1]


def test_make_plan_sends_material_and_fix():
    sent = []
    ans = json.dumps({"title": "점검 공유", "slides": [{"title": "표지", "point": "", "source": "board"}, {"title": "결과", "point": "", "source": "board"}]}, ensure_ascii=False)
    out = slides.make_plan(fake_client(ans, sent), "점검", {"장 수": "5장"}, material="(메모) 안테나 정상", prev={"slides": [{"title": "옛 장"}]}, fix="사례 더", model="m")
    assert out["plan"]["title"] == "점검 공유" and out["model"] == "m" and "estimate" in out
    sys_msg, user = sent[0]["messages"][0]["content"], sent[0]["messages"][1]["content"]
    assert "5장 안팎" in sys_msg and "안테나 정상" in user and "옛 장" in user and "사례 더" in user


def test_build_gathers_web_only_for_web_slides_and_fills_missing():
    sent, asked = [], []
    plan = {"title": "점검", "slides": [{"title": "표지", "source": "board"}, {"title": "연료 기준", "source": "web", "query": "발전기 연료 기준"}, {"title": "끝", "source": "ai", "point": "정리"}]}
    exa = lambda q: asked.append(q) or ("8시간분 이상 비축 [1]", {"search_results": [{"title": "지침", "url": "https://ex.com/a"}]})
    ans = json.dumps({"slides": [{"title": "표지", "bullets": ["10월 27일"], "notes": "나눕니다"}, {"title": "연료 기준", "bullets": ["8시간분 [1]"], "notes": "시간으로"}, {"title": "끝", "bullets": []}]}, ensure_ascii=False)
    out = slides.build("k", fake_client(ans, sent), "점검", {"듣는 사람": "아는 동료"}, plan, material="(메모) 안테나 정상", model="w", exa=exa)
    assert asked == ["발전기 연료 기준"]                                                     # 웹 장만 검색
    deck = out["deck"]
    assert [s["title"] for s in deck["slides"]] == ["표지", "연료 기준", "끝"] and deck["sources"] == [{"n": 1, "title": "지침", "url": "https://ex.com/a"}]
    assert deck["slides"][2]["bullets"] == ["정리"] and out["missing"] == ["끝"]             # 못 쓴 장 = 요점 한 줄
    user = sent[0]["messages"][1]["content"]
    assert "8시간분 이상 비축 [1]" in user and "안테나 정상" in user and "아는 동료" in sent[0]["messages"][0]["content"]


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    monkeypatch.setattr(srv.Handler, "_balance", staticmethod(lambda key, base: None))
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _post(base, body):
    with urllib.request.urlopen(urllib.request.Request(base + "/api/chat", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})) as r:
        return json.loads(r.read())


def test_server_slides_steps_and_material_rule(server, monkeypatch):
    import server as srv
    calls = []
    monkeypatch.setattr(srv.slides, "make_plan", lambda client, topic, brief, **kw: calls.append(("plan", topic, brief, kw)) or {"plan": {"title": "t", "slides": []}, "estimate": {}, "model": kw["model"], "elapsed": 0.1})
    monkeypatch.setattr(srv.slides, "build", lambda key, client, topic, brief, plan, **kw: calls.append(("build", topic, brief, kw)) or {"deck": {"title": "t", "slides": [], "sources": []}, "model": kw["model"], "elapsed": 0.1, "missing": []})
    monkeypatch.setattr(srv.route, "decide", lambda *a, **k: pytest.fail("발표 자료는 길 고르기를 안 거침"))
    out = _post(server, {"kind": "slides", "board": "b", "slides": {"step": "plan", "topic": "점검", "brief": {"재료": "고른 자료"}, "material": "(메모) 안테나"}})
    assert out["kind"] == "slides" and calls[-1][3]["material"] == "(메모) 안테나" and calls[-1][3]["model"] == slides.PLAN_MODEL
    out = _post(server, {"kind": "slides", "board": "b", "slides": {"step": "build", "topic": "점검", "brief": {"재료": "웹 검색"}, "material": "(메모) 안테나", "plan": {"slides": []}}})
    assert out["kind"] == "slides" and "deck" in out and calls[-1][3]["material"] == ""      # 재료 = 웹 검색이면 고른 것을 안 씀


def test_build_keeps_layouts_and_falls_back_when_empty():
    plan = {"title": "점검", "slides": [{"title": "표지", "source": "board"}, {"title": "숫자", "source": "board"}, {"title": "빈 숫자", "source": "board"}, {"title": "단계", "source": "board"}, {"title": "끝", "source": "board"}]}
    ans = json.dumps({"slides": [
        {"title": "표지", "layout": "글머리", "bullets": ["부제"]},
        {"title": "숫자", "layout": "숫자", "bullets": ["a"], "numbers": [{"value": "70%", "label": "연료"}, {"value": "2대", "label": "교체"}]},
        {"title": "빈 숫자", "layout": "숫자", "bullets": ["b"], "numbers": [{"value": "1", "label": "x"}]},
        {"title": "단계", "layout": "단계", "bullets": ["c"], "steps": ["전환", "분리", "설치"]},
        {"title": "끝", "layout": "이상한", "bullets": ["d"]}]}, ensure_ascii=False)
    out = slides.build("k", fake_client(ans, []), "점검", {}, plan, model="w")
    got = [(s["title"], s["layout"]) for s in out["deck"]["slides"]]
    assert got == [("표지", "표지"), ("숫자", "숫자"), ("빈 숫자", "글머리"), ("단계", "단계"), ("끝", "마무리")]   # 첫 장 = 표지, 숫자 하나뿐 = 글머리, 모르는 끝 장 = 마무리
    assert out["deck"]["slides"][1]["numbers"][0] == {"value": "70%", "label": "연료"} and out["deck"]["slides"][3]["steps"] == ["전환", "분리", "설치"]


def test_build_draws_cover_beside_writing_and_survives_failure():
    plan = {"title": "점검", "slides": [{"title": "표지", "source": "board"}, {"title": "결과", "source": "board"}]}
    ans = json.dumps({"slides": [{"title": "표지", "bullets": ["부제"]}, {"title": "결과", "bullets": ["정상"]}]}, ensure_ascii=False)
    asked = []
    out = slides.build("k", fake_client(ans, []), "점검", {}, plan, model="w", image=lambda p: asked.append(p) or {"img": "/api/img/b/1.png", "w": 4, "h": 3, "model": "img-m", "extra": 1})
    assert out["deck"]["cover"] == {"img": "/api/img/b/1.png", "w": 4, "h": 3, "model": "img-m"} and "주제: 점검" in asked[0] and "결과" in asked[0]
    def boom(p):
        raise RuntimeError("quota")
    out = slides.build("k", fake_client(ans, []), "점검", {}, plan, model="w", image=boom)
    assert "cover" not in out["deck"] and "quota" in out["cover_error"] and len(out["deck"]["slides"]) == 2
