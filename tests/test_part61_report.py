"""§8 항목61 「정리해 줘」 ①(2026-10-19) — 칠판 자료 → 정리 문서 한 장(HTML): 청소(스크립트·이벤트·외부 연결 지움)·제목·쉬운 글(`easycad/ai/board_report.py`),
서버 `/api/chat`의 report(고른 것 / 없으면 칠판 전체가 재료, 바로 앞 문서 + 「더 짧게」 = 고쳐 쓰기).

KAIROS는 부르지 않는다 — 가짜 클라이언트. 실제 호출은 따로 확인(Opus 5.5 40~55초).
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
from easycad.ai import board_find, board_report  # noqa: E402

DIRTY = """```html
<!doctype html><html><head><title>회의 브리핑 &amp; 할 일</title><link rel="stylesheet" href="https://x.kr/a.css">
<script>alert(1)</script></head><body onload="evil()"><h1>회의</h1><p>2번 송신기 <b>70%</b></p>
<a href="javascript:alert(2)">링크</a><img src="x.png" onerror="evil()"><iframe src="https://x.kr"></iframe><style>p{color:red}</style></body></html>
```"""


def test_clean_title_plain():
    h = board_report.clean_html(DIRTY)
    assert h.startswith("<!doctype html>") and "```" not in h
    for bad in ("<script", "alert(1)", "onload", "onerror", "javascript:", "<iframe", "<link"):
        assert bad not in h, bad
    assert "<style>" in h and "<b>70%</b>" in h   # 꾸밈은 남김
    assert board_report.title_of(h) == "회의 브리핑 & 할 일"
    assert board_report.plain_text(h) == "회의\n2번 송신기 70%\n링크"


class FakeClient:
    def __init__(self):
        self.seen = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.seen.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="<!doctype html><html><head><title>정리</title></head><body>ok</body></html>"))])


def test_make_new_and_revise():
    c = FakeClient()
    out = board_report.make(c, "(메모) 송신기 이상", "표로")
    assert out["title"] == "정리" and out["model"] == board_report.REPORT_MODEL
    assert "[칠판 자료]\n(메모) 송신기 이상" in c.seen[0]["messages"][1]["content"] and "[요청]\n표로" in c.seen[0]["messages"][1]["content"]
    board_report.make(c, "", "더 짧게", prev_html="<html>앞 문서</html>")
    assert "[앞 문서]\n<html>앞 문서</html>" in c.seen[1]["messages"][1]["content"] and "[고칠 점]\n더 짧게" in c.seen[1]["messages"][1]["content"]


def test_tone_same_as_deep_board_and_picked_by_name():
    """정리 문서 톤 = 칠판 딥모드 톤(`deepstyle.js` — 2026-10-25 장점 바꿔 쓰기): 같은 키·이름·강조색. 기본 차분, 요청에 톤 이름이면 그 톤."""
    import re
    js = open(os.path.join(ROOT, "web", "src", "next", "deepstyle.js"), encoding="utf-8").read()
    got = {k: (n, acc) for k, n, acc in re.findall(r"^  (\w+): tone\('([^']+)', '[^']*', \{ accent: '(#[0-9a-f]{6})'", js, re.M)}
    assert got == {k: (t["name"], t["accent"]) for k, t in board_report.TONES.items()}
    assert board_report.tone_of("신문 톤으로 해 줘") == "news" and board_report.tone_of("파랑으로") == "info" and board_report.tone_of("표로") == ""
    c = FakeClient()
    out = board_report.make(c, "(메모) 송신기 이상", "", style="present")
    assert out["tone"] == "calm" and "「차분」 톤" in c.seen[0]["messages"][1]["content"] and "#b4532f" in c.seen[0]["messages"][1]["content"]
    out = board_report.make(c, "", "더 짧게", prev_html="<html>앞</html>")
    assert out["tone"] == "" and "톤" not in c.seen[1]["messages"][1]["content"]   # 고칠 땐 톤을 말했을 때만 바꿈
    board_report.make(c, "", "남색 톤으로", prev_html="<html>앞</html>")
    assert "「남색」 톤" in c.seen[2]["messages"][1]["content"]


def test_unchecked_numbers_flags_numbers_not_in_material():
    """숫자 검사(딥모드 「숫자마다 출처」를 정리 문서에도) — 두 자리 이상 숫자 중 자료에 그대로 없는 것만, 쉼표는 같게 봄, 자료가 비면 안 견줌."""
    doc = "<html><head><title>2099 제목</title><style>p{margin:14mm}</style></head><body><p>출력 1,200W · 시청률 35.2% · 3단계 · 합계 4,800</p></body></html>"
    assert board_report.unchecked_numbers(doc, "송신기 출력 1200W, 시청률 35.2%") == ["4,800"]   # 머리·스타일은 안 봄, 한 자리 숫자는 안 셈
    assert board_report.unchecked_numbers(doc, "") == []


def test_doc_card_text_is_searchable():
    it = {"type": "doc", "uid": "d1", "title": "회의 브리핑", "html": "<html><body><h1>송신기 교체</h1><p>견적은 금요일</p></body></html>"}
    assert board_find.item_text(it) == "회의 브리핑\n송신기 교체\n견적은 금요일"


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    seen = []

    def fake_make(client, material, ask="", *, prev_html="", model=board_report.REPORT_MODEL, images=None, style="present"):
        seen.append({"material": material, "ask": ask, "prev": prev_html, "style": style})
        return {"html": f"<html><title>T {style}</title></html>", "title": f"T {style}", "model": model, "elapsed": 0.1, "tone": "calm" if style == "present" else "",
                "unchecked": ["4,800"] if "합계" in ask else [], "style": style}
    monkeypatch.setattr(srv.board_report, "make", fake_make)
    monkeypatch.setattr(srv.gw, "_client", lambda *a, **k: None)
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    (tmp_path / "공부.ecad").write_text(json.dumps({"format": "easycad-doc", "items": [
        {"type": "memo", "uid": "m1", "lines": [{"k": "p", "t": "송신기 이상 보고"}]}, {"type": "rect", "uid": "r1", "label": {"text": "UHD 회의"}}]}, ensure_ascii=False), encoding="utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def _post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


def test_server_report_material_whole_board_selection_and_revise(server):
    base, seen = server
    out = _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "이 칠판 정리해 줘"}]})
    assert out["kind"] == "report" and out["html"].startswith("<html>") and "「T read」" in out["content"] and "「T present」" not in out["content"]   # 2026-11-09 기본 = 문서 한 장
    assert "(메모) 송신기 이상 보고" in seen[-1]["material"] and "(상자) UHD 회의" in seen[-1]["material"]   # 고른 것이 없으면 칠판 전체
    _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "보고서로", "context": "- 고른 메모"}]})
    assert seen[-1]["material"] == "- 고른 메모"
    _post(base + "/api/chat", {"board": "공부", "prev_html": "<html>앞</html>", "messages": [{"role": "user", "content": "더 짧게"}]})
    assert seen[-1]["prev"] == "<html>앞</html>" and seen[-1]["ask"] == "더 짧게" and seen[-1]["style"] == "present"   # 「더 짧게」 = 앞 문서 고치기(옛 한 장 = 발표용으로)
    out = _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "발표용으로 합계까지 보고서로", "context": "- 고른 메모"}]})
    assert "차분 톤" in out["content"] and "그대로 찾지 못한 숫자: 4,800" in out["content"]   # 숫자 검사는 답 글에 알림(막지 않음)


def test_unchecked_numbers_skips_times_and_dates_written_differently():
    """2026-10-26 점검 — 회의 「오후 2시」를 14:00으로, 기사 날짜 2026-07-31을 2026.7.31·9.21로 쓴 것까지 「못 찾은 숫자」로 떴음."""
    material = "다음 회의는 월요일 오후 2시. 기사 2026-07-31 · yna.co.kr, 2026-09-21 · ddaily. 송신기 출력 1200W"
    doc = "<p>다음 회의 14:00</p><p>7월 31일 KBS, 9.21 kt ENA, 2026.7.31 정리</p><p>출력 1200W → 4,800W, 시청률 35.2%</p>"
    assert board_report.unchecked_numbers(doc, material) == ["4,800", "35.2"]
    assert board_report.unchecked_numbers("<p>2026.8.15 발표</p>", material) == ["2026.8", "15"]   # 자료에 없는 날짜는 그대로 알림


def test_two_styles_present_and_read():
    """2026-11-05 두 장 → 2026-11-09 문서 통합 1단계: 기본 = 읽기용 한 장(A/B에서 고른 edu식, 1000px), 발표용은 말했을 때만."""
    assert board_report.STYLES == {"present": "발표용", "read": "읽기용"}
    assert board_report.style_of("발표용으로만 만들어 줘") == "present" and board_report.style_of("읽기용으로") == "read" and board_report.style_of("차분하게 정리") == "read"
    assert board_report.style_of("정리해 줘") == "" and board_report.style_of("발표용이랑 읽기용 둘 다") == ""
    assert "지어 넣지 않는다" in board_report.SYSTEM                                  # 발표용도 칠판에 없는 연결·계산 표는 안 지어냄(A/B에서 A가 담당 칸·칼로리 표를 지어냄)
    for rule in ("결론", "용어", "구조", "keep-all", "칸 높이를 고정하지"):
        assert rule in board_report.SYSTEM_READ, rule
    assert "Pretendard" not in board_report.SYSTEM_READ and "흰 바탕" not in board_report.SYSTEM_READ   # 모양은 모델이(베껴 적어 굳지 않게)
    c = FakeClient()
    out = board_report.make(c, "(메모) 송신기 이상", "", style="read")
    assert out["style"] == "read" and out["tone"] == "" and c.seen[0]["messages"][0]["content"] == board_report.SYSTEM_READ
    assert "톤" not in c.seen[0]["messages"][1]["content"]                            # 읽기용 색은 모델이 — 톤은 말했을 때만
    out = board_report.make(c, "(메모) 송신기 이상", "신문 톤으로", style="read")
    assert out["tone"] == "news" and "「신문」 톤" in c.seen[1]["messages"][1]["content"]
    out = board_report.make(c, "(메모) 송신기 이상", "", style="present")
    assert out["style"] == "present" and out["tone"] == "calm" and c.seen[2]["messages"][0]["content"] == board_report.SYSTEM and out["page_w"] == 794
    out = board_report.make(c, "(메모) 송신기 이상", "")
    assert out["style"] == "read" and out["page_w"] == 1000                                     # 기본 = 문서(읽기용)
    for rule in ("핵심 의견", "1000px", "세로축 둘", "점선 아님", "줄이지 않는다"):
        assert rule in board_report.SYSTEM_READ, rule
    assert "1~2쪽" not in board_report.SYSTEM_READ                                            # 분량을 줄이라고 하지 않음(사용자)


def test_server_report_two_docs_pick_one_and_revise_each(server):
    base, seen = server
    n = len(seen)
    out = _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "정리해 줘", "context": "- 고른 메모"}]})
    assert len(seen) == n + 1 and seen[-1]["style"] == "read" and [d["style"] for d in out["docs"]] == ["read"] and "두 장" not in out["content"]   # 기본 = 한 장
    n = len(seen)
    out = _post(base + "/api/chat", {"board": "공부", "messages": [{"role": "user", "content": "발표용으로 정리해 줘", "context": "- 고른 메모"}]})
    assert len(seen) == n + 1 and seen[-1]["style"] == "present" and [d["style"] for d in out["docs"]] == ["present"]
    n = len(seen)
    _post(base + "/api/chat", {"board": "공부", "prev_html": "<html>읽기</html>", "prev_style": "read", "messages": [{"role": "user", "content": "더 짧게"}]})
    assert len(seen) == n + 1 and seen[-1]["style"] == "read" and seen[-1]["prev"] == "<html>읽기</html>"   # 앞 문서 모양 그대로 고쳐 씀
    prev = [{"style": "present", "html": "<html>발표</html>"}, {"style": "read", "html": "<html>읽기</html>"}]
    n = len(seen)
    out = _post(base + "/api/chat", {"board": "공부", "prev_docs": prev, "messages": [{"role": "user", "content": "더 짧게"}]})
    assert out["kind"] == "report" and len(seen) == n + 2 and len(out["docs"]) == 2             # 「더 짧게」 = 두 장 각자 고치기
    assert {(x["style"], x["prev"]) for x in seen[-2:]} == {("present", "<html>발표</html>"), ("read", "<html>읽기</html>")}
    n = len(seen)
    _post(base + "/api/chat", {"board": "공부", "prev_docs": prev, "messages": [{"role": "user", "content": "발표용만 더 크게"}]})
    assert len(seen) == n + 1 and seen[-1]["style"] == "present" and seen[-1]["prev"] == "<html>발표</html>"   # 하나를 말하면 그것만


class _Said:
    """정해 둔 답을 돌려주는 가짜 클라이언트(찾을 질문 고르기)."""
    def __init__(self, text):
        self.text, self.seen = text, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.seen.append(kw)
        if isinstance(self.text, Exception):
            raise self.text
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))])


def test_find_gaps_only_when_material_lacks_facts():
    """찾아 보태기(2026-11-09) — 찾을 질문 최대 3개, 빈 자료·망가진 답·오류면 [](문서는 칠판 자료만으로)."""
    c = _Said('```json\n{"queries": [{"q": "2024년 국내 OTT 이용률", "source": "kr"}, {"q": "지상파 광고매출 추이", "source": "x"}, {"q": "a"}, {"q": "b"}]}\n```')
    got = board_report.find_gaps(c, "OTT 때문에 지상파가 얼마나 줄었나", "문서로", today="2026-11-09")
    assert got == [{"q": "2024년 국내 OTT 이용률", "source": "kr"}, {"q": "지상파 광고매출 추이", "source": "web"}, {"q": "a", "source": "web"}]
    assert "오늘: 2026-11-09" in c.seen[0]["messages"][0]["content"] and "OTT 때문에" in c.seen[0]["messages"][1]["content"]
    assert board_report.find_gaps(_Said('{"queries": []}'), "회의록 — 할 일 셋") == []
    assert board_report.find_gaps(_Said("모르겠어요"), "자료") == []
    assert board_report.find_gaps(_Said(RuntimeError("끊김")), "자료") == []
    assert board_report.find_gaps(None, "자료") == [] and board_report.find_gaps(_Said("{}"), "  ") == []


def test_make_with_found_material_cites_and_skips_its_numbers():
    c = _Said("<!doctype html><html><head><title>OTT</title></head><body>OTT 이용률 79% [1] · 칠판에 없는 1234</body></html>")
    found = {"text": "· 2024년 OTT 이용률\n이용률은 79%예요 [1]", "sources": [{"n": 1, "title": "KOSIS", "url": "https://kosis.kr"}], "asked": 1}
    out = board_report.make(c, "(메모) OTT 조사", "읽기용으로", style="read", found=found)
    user = c.seen[0]["messages"][1]["content"]
    assert "[찾아 보탠 자료" in user and "이용률은 79%예요 [1]" in user and "[1] KOSIS — https://kosis.kr" in user
    assert out["unchecked"] == ["1234"]                                                   # 찾아 보탠 숫자(79)는 「못 찾은 숫자」가 아님


def test_server_report_looks_up_only_for_new_docs(server, monkeypatch):
    import server as srv
    base, seen = server
    asked, gathered = [], []
    monkeypatch.setattr(srv.board_report, "find_gaps", lambda client, material, ask="", **k: asked.append(material) or [{"q": "OTT 이용률", "source": "kr"}])
    monkeypatch.setattr(srv.deep_mode, "gather", lambda key, plan, **k: gathered.append(plan) or {"sources": [{"n": 1, "title": "KOSIS", "url": "https://kosis.kr"}], "materials": [{"text": "79% [1]"}]})
    fakes = []
    def rec(client, material, ask="", **k):
        fakes.append(k.get("found"))
        return {"html": "<html><title>T</title></html>", "title": "T", "model": "m", "elapsed": 0.1, "tone": "", "unchecked": [], "style": k.get("style", "present")}
    monkeypatch.setattr(srv.board_report, "make", rec)
    out = _post(base + "/api/chat", {"board": "공부", "kind": "report", "messages": [{"role": "user", "content": "읽기용 문서로", "context": "- OTT 조사 메모"}]})
    assert asked == ["- OTT 조사 메모"] and gathered[0]["sections"] == [{"source": "kr", "query": "OTT 이용률", "title": "OTT 이용률"}]
    assert fakes[-1] == {"text": "· OTT 이용률\n79% [1]", "sources": [{"n": 1, "title": "KOSIS", "url": "https://kosis.kr"}], "asked": 1}
    assert "찾아 보탰어요(찾아본 질문 1개)" in out["content"]
    _post(base + "/api/chat", {"board": "공부", "kind": "report", "prev_html": "<html>앞</html>", "messages": [{"role": "user", "content": "더 짧게"}]})
    assert len(asked) == 1 and fakes[-1] is None                                          # 고쳐 쓰기 = 찾지 않음


def test_ensure_blocks_numbers_top_chunks_and_keeps_model_blocks():
    """블록(2026-11-09 문서 통합 1단계) — 모델이 안 달면 본문 맨 위 덩어리마다 b1…·종류, 감싼 상자는 벗기고 셈, 모델이 단 것은 그대로."""
    d = ('<!doctype html><html><head><title>x</title><style>p{}</style></head><body><main class="page"><div class="wrap"><h1>결론</h1><p>설명</p>'
         '<section><h2>추이</h2><svg viewBox="0 0 10 10"><path d="M0 0"/></svg></section><table><tr><td>1</td></tr></table><figure><img src="a"></figure><br>'
         '<div class="note">아직 못 찾은 것</div></div></main></body></html>')
    out = board_report.ensure_blocks(d)
    import re
    got = re.findall(r'<(\w+)[^>]*data-block="(b\d+)" data-kind="(\w+)"', out)
    assert got == [("h1", "b1", "text"), ("p", "b2", "text"), ("section", "b3", "chart"), ("table", "b4", "table"), ("figure", "b5", "image"), ("div", "b6", "box")]
    assert board_report.plain_text(out) == board_report.plain_text(d)                      # 글은 그대로
    mine = '<html><body><div data-block="b1" data-kind="text">가</div><div data-block="b2" data-kind="box">나</div></body></html>'
    assert board_report.ensure_blocks(mine) == mine                                        # 모델이 단 블록은 손대지 않음
    assert board_report.ensure_blocks("<html><body><p>하나뿐</p></body></html>") == "<html><body><p>하나뿐</p></body></html>"
    assert "[블록" in board_report.SYSTEM and "[블록" in board_report.SYSTEM_READ and "data-block" in board_report.REVISE


def test_make_adds_blocks_and_counts_them():
    c = _Said('<!doctype html><html><head><title>T</title></head><body><h1>결론</h1><p>가</p><ul><li>나</li></ul></body></html>')
    out = board_report.make(c, "(메모) 가", "읽기용으로", style="read")
    assert out["blocks"] == 3 and 'data-block="b3" data-kind="text"' in out["html"]


DOC3 = ('<!doctype html><html><head><style>.k{color:red}</style></head><body><main><h1 data-block="b1" data-kind="text">결론</h1>'
        '<section class="k" data-block="b2" data-kind="box"><div><img src="x"><br></div><p>OTT 81.8% [1]</p></section><p data-block="b3" data-kind="text">끝</p></main></body></html>')


def test_block_find_splice_and_reject():
    """블록 하나 다시 쓰기(2026-11-09 문서 통합 2단계) — 찾기·끼우기, 요소가 둘이거나 번호가 다르면 거절, 청소."""
    assert board_report.block_of(DOC3, "b2").startswith('<section class="k"') and board_report.block_of(DOC3, "b2").endswith("</section>")
    out = board_report.splice_block(DOC3, "b2", '<section class="k" data-block="b2" data-kind="table"><table></table></section>')
    assert board_report.block_of(out, "b1") == board_report.block_of(DOC3, "b1") and board_report.block_of(out, "b3") == board_report.block_of(DOC3, "b3")
    assert board_report.block_of(DOC3, "b9") == ""
    for bad in ('<p data-block="b2">가</p><p>나</p>', '<p data-block="b3">가</p>', '그냥 글'):
        with pytest.raises(ValueError):
            board_report.clean_block(bad, "b2")
    assert board_report.clean_block('```html\n<div data-block="b2" onclick="x()"><script>a()</script>ok</div>\n```', "b2") == '<div data-block="b2">ok</div>'


def test_rewrite_block_sends_doc_and_block_and_puts_picture():
    c = _Said('<section class="k" data-block="b2" data-kind="image"><img src="{{그림}}" alt="막대"><p>OTT 81.8% [1]</p></section>')
    out = board_report.rewrite_block(c, DOC3, "b2", "그림 넣어 줘", history=[{"role": "user", "content": "전에 한 말"}], image_uri="data:image/jpeg;base64,AAAA")
    sys_msg, user = c.seen[0]["messages"][0]["content"], c.seen[0]["messages"][1]["content"]
    assert 'data-block="b2"' in sys_msg and "{{그림}}" in sys_msg and "[문서 전체 — 참고만]" in user and "[고칠 블록 b2]" in user and "전에 한 말" in user
    assert c.seen[0]["model"] == board_report.BLOCK_MODEL and out["before"] == board_report.block_of(DOC3, "b2")
    assert 'src="data:image/jpeg;base64,AAAA"' in board_report.block_of(out["html"], "b2") and board_report.block_of(out["html"], "b1") == '<h1 data-block="b1" data-kind="text">결론</h1>'


def test_server_block_route(server, monkeypatch):
    import server as srv
    base, _seen = server
    calls = []
    monkeypatch.setattr(srv.board_report, "rewrite_block", lambda client, doc, bid, ask, **k: calls.append((bid, ask, k.get("image_uri", ""))) or {"html": doc.replace("끝", "끝!"), "block": "", "before": "", "model": "m", "elapsed": 0.1})
    monkeypatch.setattr(srv.board_image, "generate", lambda key, prompt, **k: calls.append(("그림", prompt)) or {"images": [(b"\x89PNG", "png")], "model": "g", "credits": 1})
    out = _post(base + "/api/chat", {"kind": "block", "board": "공부", "doc": DOC3, "block": "b3", "messages": [{"role": "user", "content": "쉬운 말로"}]})
    assert out["kind"] == "block" and out["block"] == "b3" and "끝!" in out["html"] and calls[-1] == ("b3", "쉬운 말로", "")
    _post(base + "/api/chat", {"kind": "block", "board": "공부", "doc": DOC3, "block": "b2", "messages": [{"role": "user", "content": "그림 넣어 줘"}]})
    assert calls[-2][0] == "그림" and "OTT 81.8%" in calls[-2][1] and calls[-1][2].startswith("data:image/")
    import urllib.error
    with pytest.raises(urllib.error.HTTPError):
        _post(base + "/api/chat", {"kind": "block", "board": "공부", "doc": DOC3, "block": "b9", "messages": [{"role": "user", "content": "x"}]})
