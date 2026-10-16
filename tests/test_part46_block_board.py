"""§8 항목57 블록 조립식 보드(2026-10-16) — AI는 블록 종류·줄·칸 수·크기만, 앱이 12칸 격자에 겹치지 않게 놓는다.

시안 ③(논문)·④(회의 자료) https://claude.ai/artifact/Rpy4yHahposGC2EpJBojbS
"""
import json
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

import pytest

from easycad.ai import pdf_to_board as pb
from easycad.canvas.annotator_core import _BoardItem, _ImageItem, BOARD_ASPECT
from easycad.canvas.drawing_check import check_drawing
from test_part41_paper_board import (  # noqa: F401
    SPEC, _bar, _close, _sel_board, _wait_until, _window, figure_pdf,
)

FLOW = {"direction": "TD", "lanes": [], "steps": [{"id": "a", "text": "문장 입력", "kind": "start"},
                                                  {"id": "b", "text": "셀프 어텐션"}, {"id": "c", "text": "다음 단어", "kind": "end"}],
        "links": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}], "focus": "b"}
PAPER = {"kind": "block-board", "title": "Attention Is All You Need", "meta": "Vaswani 외, 2017",
         "subtitle": "문장 안 모든 단어가 서로를 한 번에 바라보게 해 번역을 빠르고 정확하게 만든 방법", "highlight": "한 번에 바라보게",
         "blocks": [
             {"type": "cards", "title": "핵심 개념", "row": 1, "span": 4, "items": [
                 {"name": "셀프 어텐션", "body": "단어마다 관련 깊은 단어에 점수를 준다.", "pages": "p.3"},
                 {"name": "멀티 헤드", "body": "여러 관점으로 동시에 본다.", "pages": "p.4"}]},
             {"type": "flow", "title": "어떻게 작동하나", "pages": "p.2–5", "row": 1, "span": 4, "flow": FLOW},
             {"type": "numbers", "title": "결과", "row": 1, "span": 4, "items": [
                 {"label": "영→독 BLEU", "value": "28.4", "note": "당시 최고", "pages": "p.8"},
                 {"label": "학습", "value": "3.5일", "note": "GPU 8장", "pages": "p.7"}]},
             {"type": "figure", "title": "Transformer 구조", "caption": "그림 1", "page": 1, "row": 2, "span": 6},
             {"type": "bars", "title": "BLEU 비교", "row": 2, "span": 6, "bars": [
                 {"label": "ConvS2S", "value": 25.16}, {"label": "Transformer", "value": 28.4, "mine": True}], "note": "0부터"},
             {"type": "verdict", "title": "의의와 한계", "row": 3, "span": 8, "items": [
                 {"type": "의의", "text": "이후 대형 언어 모델의 바탕.", "pages": "문서 밖 맥락"},
                 {"type": "한계", "text": "긴 문장은 계산이 많다.", "pages": "p.6"}]},
             {"type": "terms", "title": "용어", "row": 3, "span": 4, "items": [{"term": "BLEU", "meaning": "번역 점수"}]},
         ]}
MEETING = {"kind": "block-board", "title": "3분기 송출 장비 교체 회의", "meta": "기술국 · 2026-10-16",
           "subtitle": "노후 송신기 2대를 11월에 교체하고 시험 방송은 12월 첫 주에 한다", "highlight": "",
           "blocks": [
               {"type": "list", "title": "결정한 것", "row": 1, "span": 4,
                "items": ["송신기 2대 교체(11월)", "예비 부품 먼저 확보", "시험 방송 12월 첫 주"]},
               {"type": "table", "title": "할 일", "row": 1, "span": 8, "columns": ["할 일", "담당", "기한"],
                "rows": [["견적 받기", "송신팀", "10/30"], ["설치 일정 공지", "운영팀", "11/05"], ["시험 방송 계획", "기술팀", "11/20"]]},
               {"type": "timeline", "title": "일정", "row": 2, "span": 12, "items": [
                   {"when": "10월 말", "text": "견적"}, {"when": "11월", "text": "설치"}, {"when": "12월 첫 주", "text": "시험 방송"}]},
               {"type": "quote", "title": "", "row": 3, "span": 8, "text": "방송 사고 없이 바꾸는 것이 먼저다", "by": "국장"},
           ]}


def _items_of(added):
    return [it for it in added if not isinstance(it, _BoardItem)]


def test_parse_blocks_is_lenient():
    raw = json.dumps(dict(PAPER, blocks=PAPER["blocks"] + [
        {"type": "unknown", "row": 1}, {"type": "list", "items": []},                  # 모르는 종류·빈 블록은 뺀다
        {"type": "table", "row": "2", "span": "20", "size": "huge", "columns": ["a"], "rows": [["x", "y"]]}]),
        ensure_ascii=False)
    spec = pb.parse_board("앞말\n```json\n" + raw + "\n```")
    assert pb.is_block_spec(spec) and pb.is_board_spec(raw)
    types = [b["type"] for b in spec["blocks"]]
    assert types == ["cards", "flow", "numbers", "figure", "bars", "verdict", "terms", "table"]
    t = spec["blocks"][-1]
    assert t["row"] == 2 and t["span"] == 12 and t["size"] == "normal" and t["rows"] == [["x"]]
    assert spec["blocks"][3]["page"] == 1 and spec["blocks"][5]["items"][0]["outside"] is True
    with pytest.raises(pb.BoardSpecError):
        pb.parse_board('{"kind": "block-board", "blocks": []}')


def test_refine_prompt_for_blocks_allows_layout_and_hides_paths():
    code = json.dumps(dict(PAPER, _pdf="C:/secret/a.pdf", _figure="big"), ensure_ascii=False)
    prompt = pb.build_refine_prompt("그림을 가운데로 크게", code)
    assert "row" in prompt and "span" in prompt and "secret" not in prompt and "_figure" not in prompt
    assert "block-board" in pb.build_board_prompt("본문", "")


@pytest.mark.parametrize("spec", [PAPER, MEETING], ids=["paper", "meeting"])
def test_block_board_layout_no_overlap_16x9(spec, figure_pdf):
    w = _window()
    text = pb.dump_board(dict(spec, _pdf=figure_pdf))
    _n, _a, kind, added = w._build_flow_items(text)
    boards = [it for it in added if isinstance(it, _BoardItem)]
    assert kind == "board" and len(boards) == 1
    br = boards[0].mapRectToScene(boards[0].rect())
    assert abs(br.width() / br.height() - BOARD_ASPECT) < 0.01
    items = _items_of(added)
    assert check_drawing(w._scene, items=items) == []
    for it in items:                                                     # 모두 보드 안
        assert br.adjusted(-1, -1, 1, 1).contains(it.sceneBoundingRect().center())
    parts = {getattr(it, "_pb_part", None) for it in items}
    assert {f"blocks[{i}]" for i in range(len(spec["blocks"]))} <= parts  # 블록마다 자리 표시
    _close(w)


def test_rows_center_short_row_and_flow_widens(figure_pdf):
    """칸이 남는 줄은 가운데로, 흐름도는 칸이 좁으면 칸 수를 늘린다."""
    w = _window()
    spec = dict(PAPER, _pdf=figure_pdf, blocks=[
        {"type": "text", "title": "가운데", "row": 1, "span": 6, "size": "normal", "pages": "", "body": "가운데에 놓일 글"},
        {"type": "flow", "title": "흐름", "row": 2, "span": 1, "size": "normal", "pages": "", "flow": FLOW}])
    _n, _a, _k, added = w._build_flow_items(pb.dump_board(spec))
    board = added[0]
    br = board.mapRectToScene(board.rect())
    text = next(it for it in added if getattr(it, "_pb_part", None) == "blocks[0]" and hasattr(it, "toPlainText")
                and "가운데에" in it.toPlainText())
    card = next(it for it in added if getattr(it, "_pb_part", None) == "blocks[0]" and getattr(it, "_pb_card", False))
    cr = card.mapRectToScene(card.rect())
    assert abs(cr.center().x() - br.center().x()) < 2.0 and text.sceneBoundingRect().center().x() < br.center().x()
    flow_items = [it for it in added if getattr(it, "_pb_part", None) == "blocks[1]" and hasattr(it, "build_elbow") is False
                  and not hasattr(it, "toPlainText")]
    from easycad.canvas.host_board import _outline_rect
    fr = _outline_rect(flow_items)
    col = (br.width() - 2 * w._BB_M - 11 * w._BB_G) / 12
    assert fr.width() > col                                              # span 1이었지만 흐름도 폭만큼 넓혔다
    assert abs(fr.center().x() - br.center().x()) < 4.0 and br.contains(fr)   # 혼자인 줄이라 가운데
    assert check_drawing(w._scene, items=_items_of(added)) == []
    _close(w)


def test_too_many_rows_go_to_second_board_or_dropped_when_one(figure_pdf):
    w = _window()
    many = [{"type": "text", "title": f"글 {i}", "row": i + 1, "span": 12, "size": "big", "pages": "",
             "body": "긴 글 " * 120} for i in range(8)]
    spec = dict(PAPER, _pdf=figure_pdf, blocks=many)
    _n, _a, _k, added = w._build_flow_items(pb.dump_board(spec))
    boards = [it for it in added if isinstance(it, _BoardItem)]
    assert len(boards) == 2
    assert max(b.mapRectToScene(b.rect()).width() for b in boards) <= w.BOARD_MAX_W + 1
    for it in list(w._scene.items()):
        w._scene.removeItem(it)
    _n, _a, _k, added = w._build_flow_items(pb.dump_board(dict(spec, _pages="one")))
    boards = [it for it in added if isinstance(it, _BoardItem)]
    assert len(boards) == 1
    notes = [it.toPlainText() for it in added if hasattr(it, "toPlainText") and it.toPlainText().startswith("생략(한 장으로)")]
    assert notes
    _close(w)


def test_figure_big_relayout_puts_figure_alone_centered(figure_pdf):
    w = _window()
    spec = json.dumps(dict(PAPER, _pdf=figure_pdf), ensure_ascii=False)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(spec, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: _sel_board(w) is not None and not w._ai_jobs)
    board = _sel_board(w)
    small = next(it for it in w._board_scope(board) if isinstance(it, _ImageItem))
    w._board_enter(board)
    bar = _bar(w)
    bar.line.setText("그림 크게")
    with _patch("easycad.ai.text_to_flow.generate_flow", side_effect=AssertionError("AI 부르면 안 됨")):
        bar.line.returnPressed.emit()
    board = _sel_board(w)
    img = next(it for it in w._board_scope(board) if isinstance(it, _ImageItem))
    br = board.mapRectToScene(board.rect())
    assert img.rect().height() > small.rect().height() and abs(img.sceneBoundingRect().center().x() - br.center().x()) < 2.0
    assert check_drawing(w._scene, items=[it for it in w._board_scope(board) if it is not board]) == []
    _close(w)


def test_inside_selection_names_block_title(figure_pdf):
    w = _window()
    spec = json.dumps(dict(MEETING, _pdf=figure_pdf), ensure_ascii=False)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(spec, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: _sel_board(w) is not None and not w._ai_jobs)
    board = _sel_board(w)
    cell = next(it for it in w._board_scope(board) if getattr(it, "_pb_part", None) == "blocks[1]"
                and hasattr(it, "toPlainText") and it.toPlainText() == "운영팀")
    w._scene.clearSelection()
    cell.setSelected(True)
    bar = _bar(w)
    assert bar.mode == "inner_sel" and "할 일" in bar.name_label.text()
    seen = []

    def gen(_key, text, *_a, base_code="", **_k):
        seen.append(text)
        return base_code, "m2"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
        bar.line.setText("이 표를 가운데로 크게")
        bar.line.returnPressed.emit()
        assert _wait_until(lambda: _sel_board(w) is not None and _sel_board(w) is not board and not w._ai_jobs)
    assert "blocks[1]" in seen[0] and "row·span" in seen[0] and "할 일" in seen[0]
    _close(w)


def test_reopened_board_keeps_block_parts(figure_pdf, tmp_path):
    """[§8 항목56 검토 2026-10-17] 다시 연 .ecad에서도 블록 자리(`_pb_part`)·칸 바탕(`_pb_card`)이 남아 — 그림을 골라
    「그림 크게」면 AI 없이 다시 배치(전엔 자리가 사라져 무엇을 골랐는지 없이 AI로 갔다)."""
    w = _window()
    spec = json.dumps(dict(PAPER, _pdf=figure_pdf), ensure_ascii=False)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(spec, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: _sel_board(w) is not None and not w._ai_jobs)
    board = _sel_board(w)
    parts = sorted(str(getattr(it, "_pb_part", "")) for it in w._board_scope(board))
    path = str(tmp_path / "board.ecad")
    w._do_save_ecad(path)
    w._open_new_tab()
    w._do_open_ecad(path)
    b2 = next(it for it in w._scene.items() if isinstance(it, _BoardItem))
    assert sorted(str(getattr(it, "_pb_part", "")) for it in w._board_scope(b2)) == parts
    assert any(getattr(it, "_pb_card", False) for it in w._board_scope(b2))
    img = next(it for it in w._board_scope(b2) if isinstance(it, _ImageItem))
    w._scene.clearSelection()
    img.setSelected(True)
    bar = _bar(w)
    assert bar.mode == "inner_sel" and "Transformer 구조" in bar.name_label.text()
    with _patch("easycad.ai.text_to_flow.generate_flow", side_effect=AssertionError("AI를 부르면 안 됨")):
        bar.line.setText("그림 크게")
        bar.line.returnPressed.emit()
    nb = _sel_board(w)
    assert nb is not None and nb is not b2 and pb.parse_board(nb._ai["spec"]).get("_figure") == "big"
    _close(w)


def test_pasted_image_source_kept_as_file(figure_pdf):
    """[§8 항목56 검토 2026-10-17] Ctrl+V로 붙인 그림 자료(경로 없음)도 파일로 남아 — 보드 그림 블록에 그 그림이 들어가고
    「PDF로 새로」가 원본을 다시 연다(전엔 「그림 자리」 빈칸 + "원본 자료를 찾을 수 없어요")."""
    from PIL import Image
    w = _window()
    sources = [{"label": "A", "kind": "pdf", "name": "paper.pdf", "path": figure_pdf},
               {"label": "B", "kind": "image", "name": "그림", "path": "", "image": Image.new("RGB", (300, 200), "#3366cc")}]
    ans = json.dumps({"kind": "block-board", "title": "T", "subtitle": "S", "blocks": [
        {"type": "text", "title": "글", "body": "본문", "row": 1, "span": 6},
        {"type": "figure", "title": "붙인 그림", "source": "B", "page": 1, "row": 1, "span": 6}]}, ensure_ascii=False)

    class _Res:
        content, model_used = ans, "m"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.gateway.call_text_with_fallback", return_value=_Res()):
        w._ai_ctrl.request_make("", sources=sources)
        assert _wait_until(lambda: _sel_board(w) is not None and not w._ai_jobs)
    board = _sel_board(w)
    assert sources[1]["path"] == ""   # 넘긴 목록은 그대로(사본에 경로)
    assert any(isinstance(it, _ImageItem) for it in w._board_scope(board))
    src_b = pb.parse_board(board._ai["spec"])["_sources"]["B"]
    assert src_b["path"] and os.path.exists(src_b["path"])
    with _patch.object(w._ai_ctrl, "request_make", return_value="sent") as rm:
        assert w._board_redo(board, "다시") == "sent"
    assert [s["path"] for s in rm.call_args.kwargs["sources"]][1] == src_b["path"]
    _close(w)


def test_many_blocks_split_into_more_pages_within_max_width():
    """[2026-10-17 검토] 블록이 많으면 2장에서 멈추지 않고 3장 이상으로 — 전엔 2장째 폭이 `BOARD_MAX_W`의 2.5배(글자가 아주 작게 인쇄)."""
    w = _window()
    long = "긴 설명 문장이 이어집니다. " * 40
    blocks = []
    for i in range(12):
        if i % 3 == 0:
            b = {"type": "text", "title": f"글 {i}", "body": long}
        elif i % 3 == 1:
            b = {"type": "table", "title": f"표 {i}", "columns": ["할 일", "담당", "기한", "메모"],
                 "rows": [[f"일 {k} " * 5, "팀", "10/30", "메모 " * 10] for k in range(8)]}
        else:
            b = {"type": "list", "title": f"목록 {i}", "items": ["항목 " * 15] * 8}
        blocks.append(dict(b, row=i + 1, span=12))
    spec = json.dumps({"kind": "block-board", "title": "큰 보드", "subtitle": "요약", "blocks": blocks}, ensure_ascii=False)
    _n, _a, _d, added = w._build_paper_board(spec)
    boards = [it for it in added if isinstance(it, _BoardItem)]
    assert len(boards) >= 3
    assert all(b.rect().width() <= w.BOARD_MAX_W + 1 for b in boards)
    assert sorted(b._page for b in boards) == list(range(1, len(boards) + 1))
    parts = {it._pb_part for it in added if getattr(it, "_pb_part", None)}
    assert {f"blocks[{i}]" for i in range(12)} <= parts   # 빠진 블록 없음
    notes = [it.toPlainText() for it in added if hasattr(it, "toPlainText") and "장에 이어서" in it.toPlainText()]
    assert any("→ 3장에 이어서" in t for t in notes)
    _close(w)
