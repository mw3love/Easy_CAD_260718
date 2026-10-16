"""§8 항목45(2026-10-16) — 논문 PDF 입력. §8 항목53(같은 날)부터 결과는 흐름도 하나가 아니라 「한 장 보드」(`pdf_to_board`).

엔진(`pdf_to_mermaid`: 쪽 글 뽑기·긴 문서 나눠 요약·지시문)·패널(네 번째 종류·PDF 첨부)·가운데 입구(PDF면 풀어 그리기)·
결과(흐름도와 같은 임시 결과·방향 막대).
"""
from contextlib import contextmanager
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

import fitz
import pytest

from easycad.ai import pdf_to_board as pb
from easycad.ai import pdf_to_mermaid as pm
from easycad.ai.gateway import GatewayResult

_FLOW = ('{"kind": "paper-board", "title": "IP 전환", "one_line": "IP로 바꾸는 이유",'
         ' "three_lines": [{"text": "선이 준다", "pages": "p.1"}]}')


def _make_pdf(path, pages):
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
    return str(path)


@pytest.fixture
def sample_pdf(tmp_path):
    return _make_pdf(tmp_path / "paper.pdf", ["Why IP: cabling and agility", "", "ST 2110 essence streams"])


def _wait_until(cond, ms=5000):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        _app.processEvents()
        if cond():
            return True
    return False


@contextmanager
def _fake(result=_FLOW):
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(result, "fake-model")) as gen:
        yield gen


# ---- 엔진 ----------------------------------------------------------------------

def test_extract_pages_keeps_page_numbers_and_skips_blank(sample_pdf):
    pages = pm.extract_pdf_pages(sample_pdf)
    assert [n for n, _t in pages] == [1, 3]
    assert pm.pages_to_text(pages).startswith("[p.1] Why IP")


def test_scanned_pdf_without_text_says_use_trace(tmp_path):
    blank = _make_pdf(tmp_path / "scan.pdf", ["", ""])
    with pytest.raises(pm.PdfTextError, match="베끼기"):
        pm.extract_pdf_pages(blank)


def test_chunk_pages_by_size():
    pages = [(i, "x" * 30) for i in range(1, 8)]
    chunks = pm.chunk_pages(pages, limit=100)
    assert [len(c) for c in chunks] == [3, 3, 1]
    assert [n for c in chunks for n, _t in c] == list(range(1, 8))


def test_prompt_asks_page_tags_and_user_view():
    p = pb.build_board_prompt("[p.1] body", note="IP 전환 이유 중심")
    assert '"pages"' in p and "IP 전환 이유 중심" in p and "block-board" in p and "[p.1] body" in p


def test_short_doc_is_one_call(sample_pdf):
    calls = []

    def fake(_key, prompt, **_k):
        calls.append(prompt)
        return GatewayResult("```json\n" + _FLOW + "\n```", "m1", None, 0.1)
    with _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=fake):
        code, used = pb.generate_board("k", sample_pdf, model="m1")
    assert len(calls) == 1 and pb.is_board_spec(code) and used == "m1"
    assert pb.parse_board(code)["_pdf"] == sample_pdf


def test_long_doc_summarizes_chunks_first(sample_pdf, monkeypatch):
    monkeypatch.setattr(pm, "SINGLE_PASS_CHARS", 10)   # 글 뽑기·나눠 요약은 `pdf_to_mermaid.pdf_body`(보드·흐름도 같이 씀)
    monkeypatch.setattr(pm, "CHUNK_CHARS", 20)
    calls = []

    def fake(_key, prompt, **_k):
        calls.append(prompt)
        return GatewayResult(_FLOW if "block-board" in prompt else "- 요약 (p.1)", "m1", None, 0.1)
    steps = []
    with _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=fake):
        pb.generate_board("k", sample_pdf, model="m1", progress=steps.append)
    assert len(calls) == 3, "쪽 묶음 2개 요약 + 보드 1번"
    assert "쪽 묶음별 요약" in calls[-1] and "- 요약 (p.1)" in calls[-1]
    assert steps[-1] == "보드 정리하는 중"


# ---- 요청(§8 항목51 — 옛 패널 자리는 관리 객체·가운데 칸) -----------------------------------------

def test_explain_needs_pdf():
    w = CanvasWindow()
    notes = []
    w._ai_ctrl.notice.connect(notes.append)
    assert w._ai_ctrl.request_make("요약", kind="explain") is None and "PDF" in notes[-1]


def test_attaching_pdf_makes_explain(sample_pdf):
    w = CanvasWindow()
    sp = w._start_prompt
    sp._set_attached_pdf(sample_pdf)
    assert sp.kind() == "explain" and sp._attached_pdf == sample_pdf and sp._attached_image is None
    assert sp._image_chip.isVisibleTo(sp)


def test_pdf_with_words_follows_the_words():
    """2026-10-16 사용자: PDF만 넣으면 보드, 말을 쓰면 그 말대로("간단한 그림 하나만" → 심볼, "흐름도로" → 흐름도)."""
    from easycad.canvas.ai_control import guess_kind
    assert guess_kind("", False, True) == "explain"
    assert guess_kind("흐름도로", False, True) == "flow"
    assert guess_kind("간단한 그림 하나만", False, True) == "symbol"
    assert guess_kind("핵심 아이콘", False, True) == "symbol"
    assert guess_kind("작동 흐름을 한 장 보드로 정리", False, True) == "explain"   # 「보드·정리」가 먼저


def test_pdf_flow_request_sends_pdf_text_as_material(sample_pdf):
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    sp = w._start_prompt
    w._open_ai_prompt()
    sp._set_attached_pdf(sample_pdf)
    sp._edit.setPlainText("흐름도로 그려 줘")
    prompts = []

    def fake(_key, prompt, **_k):
        prompts.append(prompt)
        return GatewayResult('{"direction":"LR","steps":[{"id":"a","text":"A"},{"id":"b","text":"B"}],'
                             '"links":[{"from":"a","to":"b"}]}', "m", None, 0.1)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=fake):
        assert sp.submit() == "flow"
        req = w._ai_ctrl.entries()[-1].request
        assert req.kind == "flow" and req.pdf_path == sample_pdf
        assert _wait_until(lambda: w._ai_staged is not None)
    assert len(prompts) == 1 and "흐름도로 그려 줘" in prompts[0] and "[p.1]" in prompts[0] and "ST 2110" in prompts[0]
    for d in w._docs:
        d.dirty = False
    w.close()


def test_pdf_symbol_request_adds_pdf_text_to_subject(sample_pdf):
    w = CanvasWindow()
    out = w._ai_pdf_subject("핵심 그림 하나", sample_pdf)
    assert out.startswith("핵심 그림 하나") and "ST 2110" in out


def test_explain_generates_and_stages_like_flow(sample_pdf):
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    p = w._ai_ctrl
    sp = w._start_prompt
    w._open_ai_prompt("explain")
    sp._set_attached_pdf(sample_pdf)
    sp._edit.setPlainText("처음 보는 사람용")
    with _fake() as gen:
        assert sp.submit() == "explain"
        req = p.entries()[-1].request
        assert req.kind == "explain" and req.pdf_path == sample_pdf
        assert _wait_until(lambda: w._board_selected() is not None)   # 보드는 바로 넣고 골라 둔다(2026-10-16)
        assert gen.call_args.args[1] == sample_pdf and gen.call_args.args[2] == "처음 보는 사람용"
        first = w._board_selected()
        assert sp._attached_pdf == "", "보낸 뒤 첨부 칩은 비움"
        # 「다시」도 가짜 안에서 끝까지 기다린다 — 밖에서 부르면 작업자가 진짜 게이트웨이에 접속해 몇 초 돌고, 그 사이 GC가
        # 창을 지우면 "QThread: Destroyed while thread is still running"으로 전체 pytest가 exit 127(2026-10-16 원인).
        again = p.resubmit(req)
        assert _wait_until(lambda: w._board_selected() is not None and w._board_selected() is not first
                           and not w._ai_jobs)
    assert again.pdf_path == sample_pdf, "「다시」도 같은 PDF로"


# ---- 가운데 입구 -------------------------------------------------------------------

def test_start_prompt_pdf_goes_to_explain(sample_pdf):
    from easycad.canvas.start_prompt import guess_kind
    assert guess_kind("아무 말", False, True) == "explain"
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    _app.processEvents()
    sp = w._start_prompt
    sp._set_attached_pdf(sample_pdf)
    assert sp.kind() == "explain"
    with _fake():
        assert sp.submit() == "explain"
        assert _wait_until(lambda: w._board_selected() is not None)
    ents = w._ai_ctrl.entries()
    assert len(ents) == 1 and ents[0].kind == "explain"
