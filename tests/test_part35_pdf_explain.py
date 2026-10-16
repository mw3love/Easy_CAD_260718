"""§8 항목45(2026-10-16) — 「풀어 그리기」: 논문·보고서 PDF → 핵심을 풀어 그린 흐름도(쪽 번호 붙음).

엔진(`pdf_to_mermaid`: 쪽 글 뽑기·긴 문서 나눠 요약·지시문)·패널(네 번째 종류·PDF 첨부)·가운데 입구(PDF면 풀어 그리기)·
결과(흐름도와 같은 임시 결과·방향 막대).
"""
from contextlib import contextmanager
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

import fitz
import pytest

from easycad.ai import pdf_to_mermaid as pm
from easycad.ai.gateway import GatewayResult

_FLOW = "flowchart TD\n    A[IP 전환 이유 · p.1] -->|핵심 표준| B[ST 2110 · p.2]"


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
            _patch("easycad.ai.pdf_to_mermaid.generate_explain", return_value=(result, "fake-model")) as gen:
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
    p = pm.build_explain_prompt("[p.1] body", note="IP 전환 이유 중심")
    assert "· p.N" in p and "IP 전환 이유 중심" in p and "ID[라벨]" in p and "[p.1] body" in p


def test_short_doc_is_one_call(sample_pdf):
    calls = []

    def fake(_key, prompt, **_k):
        calls.append(prompt)
        return GatewayResult("```mermaid\n" + _FLOW + "\n```", "m1", None, 0.1)
    with _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=fake):
        code, used = pm.generate_explain("k", sample_pdf, model="m1")
    assert len(calls) == 1 and code.startswith("flowchart TD") and used == "m1"


def test_long_doc_summarizes_chunks_first(sample_pdf, monkeypatch):
    monkeypatch.setattr(pm, "SINGLE_PASS_CHARS", 10)
    monkeypatch.setattr(pm, "CHUNK_CHARS", 20)
    calls = []

    def fake(_key, prompt, **_k):
        calls.append(prompt)
        return GatewayResult(_FLOW if "flowchart" in prompt else "- 요약 (p.1)", "m1", None, 0.1)
    steps = []
    with _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=fake):
        pm.generate_explain("k", sample_pdf, model="m1", progress=steps.append)
    assert len(calls) == 3, "쪽 묶음 2개 요약 + 그리기 1번"
    assert "쪽 묶음별 요약" in calls[-1] and "- 요약 (p.1)" in calls[-1]
    assert steps[-1] == "그리는 중"


# ---- 패널 ----------------------------------------------------------------------

def test_panel_has_fourth_kind_and_needs_pdf():
    w = CanvasWindow()
    p = w._ai_panel
    assert "explain" in p._kind_buttons and p._kind_buttons["explain"].text() == "풀어 그리기"
    p.set_kind("explain")
    assert p.request_make() is None and "PDF" in p._notice.text()


def test_attaching_pdf_switches_to_explain(sample_pdf):
    w = CanvasWindow()
    p = w._ai_panel
    p.set_kind("flow")
    p._set_attached_pdf(sample_pdf)
    assert p.kind() == "explain" and p._attached_pdf == sample_pdf and p._attached_image is None
    assert p._image_chip.isVisibleTo(p)


def test_explain_generates_and_stages_like_flow(sample_pdf):
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    p = w._ai_panel
    w._set_ai_panel_visible(True, kind="explain")
    p._set_attached_pdf(sample_pdf)
    p._prompt_edit.setPlainText("처음 보는 사람용")
    with _fake() as gen:
        req = p.request_make()
        assert req.kind == "explain" and req.pdf_path == sample_pdf
        assert _wait_until(lambda: w._ai_staged is not None)
    assert gen.call_args.args[1] == sample_pdf and gen.call_args.args[2] == "처음 보는 사람용"
    assert w._ai_staged.request.kind == "explain"
    assert p._attached_pdf == "", "보낸 뒤 첨부 칩은 비움"
    again = p.resubmit(req)
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
        assert _wait_until(lambda: w._ai_staged is not None)
    assert w._ai_panel.kind() == "explain" and len(w._ai_panel.entries()) == 1
