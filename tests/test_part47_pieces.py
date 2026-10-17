"""§8 항목59 ② 보드 옆 펼친 조각 · 「보드로 정리」(2026-10-17 심층 인터뷰).

첫 모습 = 한 장 보드 + 오른쪽 조각(AI 후보 `more` + 원문 그림), 조각을 골라 「보드로 정리」하면 AI 없이 새 보드.
"""
import json
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

from easycad.ai import pdf_to_board as pb
from easycad.canvas.annotator_core import _BoardItem
from easycad.canvas.drawing_check import check_drawing
from test_part41_paper_board import _bar, _close, _sel_board, _wait_until, _window, figure_pdf  # noqa: F401
from test_part46_block_board import MEETING

MORE = [{"type": "quote", "title": "한 문장", "text": "방송 사고 없이 바꾸는 것이 먼저다", "by": "국장"},
        {"type": "numbers", "title": "예산", "items": [{"label": "교체 비용", "value": "3억원"}]},
        {"type": "list", "title": "남은 일", "items": ["예비 부품 목록", "시험 방송 대본"]}]


def _make(w, pdf):
    spec = json.dumps(dict(MEETING, more=MORE, _pdf=pdf), ensure_ascii=False)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(spec, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=pdf)
        assert _wait_until(lambda: _sel_board(w) is not None and not w._ai_jobs)
    return _sel_board(w)


def _frames(w):
    return [it for it in w._scene.items() if it.parentItem() is None and getattr(it, "_pb_piece", None)]


def test_more_is_parsed_like_blocks():
    spec = pb.parse_board(json.dumps(dict(MEETING, more=MORE + [{"type": "nope"}]), ensure_ascii=False))
    assert [b["type"] for b in spec["more"]] == ["quote", "numbers", "list"] and not any(b.get("hero") for b in spec["more"])


def test_new_board_spreads_pieces_and_pieces_make_board(figure_pdf, tmp_path):
    w = _window()
    board = _make(w, figure_pdf)
    frames = _frames(w)
    types = sorted(json.loads(f._pb_piece)["type"] for f in frames)
    assert types == ["figure", "list", "numbers", "quote"]          # AI 후보 3 + 원문 그림 1(보드에 안 쓴 쪽)
    br = board.mapRectToScene(board.rect())
    assert all(f.sceneBoundingRect().left() > br.right() for f in frames)   # 보드 오른쪽
    assert len({f._group_id for f in frames}) == len(frames)                 # 조각마다 한 묶음
    pick = [f for f in frames if json.loads(f._pb_piece)["type"] in ("quote", "numbers")]
    w._scene.clearSelection()
    for f in pick:
        f.setSelected(True)
    w._board_bar_sync(w._view)
    w._piece_bar_sync(w._view)
    assert w._piece_bar.isVisible() and w._piece_bar.label.text() == "조각 2개"
    nb = w._pieces_to_board()
    assert nb is not None and nb is not board
    spec = pb.parse_board(nb._ai["spec"])
    assert sorted(b["type"] for b in spec["blocks"]) == ["numbers", "quote"] and spec["title"] == MEETING["title"]
    assert check_drawing(w._scene, items=[it for it in w._board_scope(nb) if it is not nb]) == []
    path = str(tmp_path / "p.ecad")
    w._do_save_ecad(path)
    w._open_new_tab()
    w._do_open_ecad(path)
    assert len(_frames(w)) == 4
    _close(w)
