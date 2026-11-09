"""재료 찾기(옛 딥모드 §8 항목66에서 남긴 `easycad/ai/deep_mode.py`) — 질문지 답 글·재료 모으기(공공 → 웹 갈아타기, 출처 번호 하나로).
지면 「한 판」(계획·본문·꼭지 다시 쓰기)은 2026-11-09 문서 통합 3단계에서 뺌 — 그 시험도 같이 뺐다(git에 있음).

KAIROS는 부르지 않는다 — 가짜 클라이언트·가짜 검색.
"""
import os
import re
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from easycad.ai import deep_mode  # noqa: E402


class FakeClient:
    """답을 차례로 돌려주는 가짜 KAIROS(보낸 messages를 적어 둠)."""
    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.sent.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answers.pop(0)))])


def test_brief_text_defaults_and_more():
    t = deep_mode.brief_text({"누구에게": "처음 보는 사람", "꼭 넣을 것": ["숫자·그래프", "확인 문제"], "더": "그림은 빼 줘"})
    assert "- 누구에게: 처음 보는 사람" in t and "- 무엇에: 알아서" in t and "- 꼭 넣을 것: 숫자·그래프, 확인 문제" in t
    assert "그림은 빼 줘" in t and "꼭 따름" in t
    assert "더" not in deep_mode.brief_text({})


def test_gather_numbers_sources_once_and_kr_falls_back_to_web():
    plan = {"sections": [{"title": "기억할 숫자", "source": "web"}, {"title": "흐름", "source": "kr", "query": "반도체 수출 통계"},
                         {"title": "원리", "source": "ai"}, {"title": "출처", "source": None}]}
    asked = []

    def exa(q):
        asked.append(q)
        return f"{q} 답 [1] 그리고 [2] · 없는 [9]", {"search_results": [{"title": "가", "url": "https://a"}, {"title": "나", "url": "https://b/" + q[:2]}]}
    mat = deep_mode.gather("k", plan, exa=exa, kr=lambda q: [])           # 공공 데이터가 비면 웹 검색
    assert sorted(asked) == sorted(["기억할 숫자", "반도체 수출 통계"])                # 출처 카드는 재료를 안 모음
    assert [s["n"] for s in mat["sources"]] == list(range(1, len(mat["sources"]) + 1))
    assert sum(1 for s in mat["sources"] if s["url"] == "https://a") == 1     # 같은 주소 = 같은 번호
    t = mat["materials"][1]["text"]
    assert re.findall(r"\[(\d+)\]", t) and "[9]" not in t                      # 없는 번호는 지움
    assert mat["materials"][2] is None                                           # ai 꼭지는 재료 없음
    bad = deep_mode.gather("k", plan, exa=lambda q: (_ for _ in ()).throw(RuntimeError("402")), kr=lambda q: [])
    assert bad["materials"][0]["text"] == "" and "402" in bad["materials"][0]["error"]


def test_kr_material_without_numbers_or_off_topic_switches_to_web():
    """0단계: 공공 데이터 숫자 꼭지 셋 중 하나만 맞음 — 표만 찾고 끝남(숫자 없음)·다른 품목 표(반도체에 열전자관) → 웹 검색으로 갈아탐."""
    find = {"suite": "kr-macro", "tool": "search_statistics", "args": {"query": "반도체"}, "text": '{"tables":[{"title":"수출물량지수"}]}'}
    empty = {"suite": "kr-macro", "tool": "get_statistics_data", "args": {}, "text": '{"rows":[],"returned":0}'}
    rows = {"suite": "kr-macro", "tool": "get_statistics_data", "args": {}, "text": '{"rows":[{"category":"열전자관냉음극관 및 광전과","value":4574763,"unit":"천달러"}]}'}
    assert not deep_mode.has_data([find]) and not deep_mode.has_data([find, empty]) and deep_mode.has_data([find, rows])
    assert deep_mode.has_data([{"suite": "korean-law", "tool": "get_law_article", "args": {}, "text": "제1조 …"}])   # JSON 아닌 조문 = 받은 것
    plan = {"sections": [{"title": "표만", "source": "kr", "query": "a"}, {"title": "다른 품목", "source": "kr", "query": "b"}, {"title": "맞음", "source": "kr", "query": "c"}]}
    by_q = {"a": [find, empty], "b": [find, rows], "c": [find, rows]}
    judged, webbed = [], []
    def fit(sec, text):
        judged.append(sec["title"])
        return (sec["title"] == "맞음", "품목이 반도체가 아님")
    mat = deep_mode.gather("k", plan, exa=lambda q: (webbed.append(q) or "웹 답 [1]", {"search_results": [{"title": "웹", "url": "https://w/" + q}]}), kr=lambda q: by_q[q], fit=fit)
    m = mat["materials"]
    assert sorted(judged) == ["다른 품목", "맞음"]                                      # 숫자 없는 건 검사 전에 걸러냄(공짜)
    assert sorted(webbed) == ["a", "b"]
    assert "숫자를 못 받음" in m[0]["switched"] and "꼭지와 다름 — 품목이 반도체가 아님" in m[1]["switched"]
    assert "switched" not in m[2] and "열전자관" in m[2]["text"]
    c = FakeClient('{"ok": false, "why": "다른 품목"}', "JSON 아님")
    assert deep_mode.fits(c, {"title": "반도체 수출"}, "열전자관 …") == (False, "다른 품목") and c.sent[0]["model"] == deep_mode.FIT_MODEL
    assert deep_mode.fits(c, {"title": "반도체 수출"}, "…") == (True, "")                # 검사 답이 틀어지면 재료를 막지 않음


def test_friendly_error_is_korean_and_keeps_our_own_reasons():
    from easycad.ai import gateway as gw
    assert gw.friendly_error(RuntimeError("Error code: 402 - {'error': 'insufficient credits'}")).startswith("KAIROS 크레딧이 모자라요")
    assert gw.friendly_error(RuntimeError("Request timed out.")).startswith("KAIROS 답이 너무 오래 걸려")
    assert gw.friendly_error(RuntimeError("Error code: 503 - unavailable")).startswith("KAIROS가 지금 바빠요")
    assert gw.friendly_error(RuntimeError("Connection error.")).startswith("KAIROS에 연결하지 못했어요")
    assert gw.friendly_error(ValueError("녹음이 40분을 넘어요")) == "녹음이 40분을 넘어요"
    assert gw.friendly_error(RuntimeError("weird")) == "KAIROS 처리 중 오류가 났어요 — 다시 해 주세요 (weird)"
