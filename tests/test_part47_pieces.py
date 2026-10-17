"""§8 항목59 ② 보드 옆 펼친 조각 · 「보드로 정리」(2026-10-17 심층 인터뷰).

첫 모습 = 한 장 보드 + 오른쪽 조각(AI 후보 `more` + 원문 그림), 조각을 골라 「보드로 정리」하면 AI 없이 새 보드.
"""
import json
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403
from PyQt6.QtCore import QPointF

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


def _drag(w, items, dx, dy):
    """끌어 놓기와 같은 길 — 옮기고 `push_undo_move`(마우스 놓을 때 뷰가 부르는 것), 다음 이벤트(다시 배치)까지 돌린다."""
    from PyQt6.QtCore import QPointF
    pairs = [(it, QPointF(it.pos())) for it in items]
    for it in items:
        it.setPos(it.pos() + QPointF(dx, dy))
    w.push_undo_move(pairs)
    for _ in range(5):
        _app.processEvents()


def test_drop_piece_into_board_and_take_block_out(figure_pdf):
    """[§8 항목59 ③] 조각을 보드 위에 놓으면 보드 설계서에 들어가 제자리에서 다시 배치, 보드 블록을 밖으로 끌면 설계서에서 빠져 조각으로.
    각각 되돌리기 한 번이면 취소."""
    w = _window()
    board = _make(w, figure_pdf)
    n0 = len(pb.parse_board(board._ai["spec"])["blocks"])
    quote = next(f for f in _frames(w) if json.loads(f._pb_piece)["type"] == "quote")
    group = [it for it in w._scene.items() if getattr(it, "_group_id", None) == quote._group_id]
    br = board.mapRectToScene(board.rect())
    c = quote.sceneBoundingRect().center()
    _drag(w, group, br.center().x() - c.x(), br.bottom() - 60 - c.y())   # 보드 아래쪽에 놓기
    nb = next(b for b in w._scene.items() if isinstance(b, _BoardItem) and b.isSelected())
    spec = pb.parse_board(nb._ai["spec"])
    assert len(spec["blocks"]) == n0 + 1 and any(b["type"] == "quote" for b in spec["blocks"])
    assert quote.scene() is None and not [f for f in _frames(w) if json.loads(f._pb_piece)["type"] == "quote"]
    assert check_drawing(w._scene, items=[it for it in w._board_scope(nb) if it is not nb]) == []
    w.undo()
    for _ in range(3):
        _app.processEvents()
    assert any(json.loads(f._pb_piece)["type"] == "quote" for f in _frames(w))   # 넣기 취소 → 조각이 돌아옴
    # 꺼내기: 표 블록의 글 하나를 보드 밖으로
    board = next(b for b in w._scene.items() if isinstance(b, _BoardItem) and (b._ai or {}).get("spec"))
    spec = pb.parse_board(board._ai["spec"])
    ti = next(i for i, b in enumerate(spec["blocks"]) if b["type"] == "table")
    cell = next(it for it in w._board_scope(board) if getattr(it, "_pb_part", None) == f"blocks[{ti}]" and hasattr(it, "toPlainText"))
    br = board.mapRectToScene(board.rect())
    _drag(w, [cell], 0, br.bottom() + 300 - cell.sceneBoundingRect().center().y())
    nb = next(b for b in w._scene.items() if isinstance(b, _BoardItem) and b.isSelected())
    assert not any(b["type"] == "table" for b in pb.parse_board(nb._ai["spec"])["blocks"])
    assert any(json.loads(f._pb_piece)["type"] == "table" for f in _frames(w))
    _close(w)


def test_pieces_to_pages_keeps_hand_layout_and_splits(figure_pdf):
    """[§8 항목59 ④] 「종이로」 — 고른 조각을 놓인 상대 위치 그대로 16:9 쪽에 담고, 넘치면 다음 쪽(조각은 안 자름). 쪽들은 한 묶음."""
    w = _window()
    _make(w, figure_pdf)
    frames = _frames(w)
    # 손으로 세로 한 줄로 길게 늘어놓은 것처럼(쪽 하나에 다 안 들어가게)
    y = 0.0
    for f in sorted(frames, key=lambda f: f.sceneBoundingRect().top()):
        members = [it for it in w._scene.items() if getattr(it, "_group_id", None) == f._group_id]
        d = QPointF(5000.0, y) - f.sceneBoundingRect().topLeft()
        for it in members:
            it.setPos(it.pos() + d)
        y += f.sceneBoundingRect().height() + 400.0
    w._scene.clearSelection()
    for f in frames:
        f.setSelected(True)
    rel = {id(f): f.sceneBoundingRect().topLeft() for f in frames}
    pages = w._pieces_to_pages()
    assert len(pages) >= 2 and len({b._set_id for b in pages}) == 1 and [b._page for b in pages] == list(range(1, len(pages) + 1))
    for f in frames:   # 조각마다 어느 한 쪽 안에 통째로
        assert sum(b.mapRectToScene(b.rect()).contains(f.sceneBoundingRect()) for b in pages) == 1
    first = [f for f in frames if pages[0].mapRectToScene(pages[0].rect()).contains(f.sceneBoundingRect())]
    if len(first) >= 2:   # 같은 쪽 안에선 손으로 놓은 간격 그대로
        a, b = first[0], first[1]
        assert abs((b.sceneBoundingRect().top() - a.sceneBoundingRect().top()) - (rel[id(b)].y() - rel[id(a)].y())) < 0.5
    ai_board = next(b for b in w._scene.items() if isinstance(b, _BoardItem) and (getattr(b, "_ai", None) or {}).get("spec"))
    assert not any(p.mapRectToScene(p.rect()).intersects(ai_board.mapRectToScene(ai_board.rect())) for p in pages)   # 빈 자리에
    for _ in range(5):
        _app.processEvents()
    assert all(p.scene() is w._scene for p in pages)   # 옮긴 조각이 「끌어다 넣기」로 처리돼 쪽이 사라지지 않음(실제 창 버그)
    w.undo()
    assert all(p.scene() is None for p in pages)
    _close(w)
