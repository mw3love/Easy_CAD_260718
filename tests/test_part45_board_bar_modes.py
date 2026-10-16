"""§8 항목56 보드 막대 세 상태·색 3개·입력 칸·모델 여러 개(2026-10-16 사용자 피드백 → 시안 2라운드 확정).

- 테두리 선택 = 「보드 · PDF로 새로」(원본 PDF + 처음 쓴 말, 결과는 오른쪽 새 보드)
- 보드 빈 곳 더블클릭 = 「보드 안 · 전체 고치기」(이 보드 설계서 바탕), Esc·보드 밖 클릭이면 나옴
- 보드 안 글·그림 선택 = 「보드 안 · 선택 N개」(고른 칸만 고치라고 AI에 알림)
"""
import json
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent

from easycad.canvas.annotator_core import _BoardItem
from test_part41_paper_board import SPEC, _bar, _close, _sel_board, _wait_until, _window, figure_pdf  # noqa: F401




def _place(w, pdf, text=""):
    spec = json.dumps(dict(SPEC, _pdf=pdf), ensure_ascii=False)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(spec, "m1")):
        w._ai_ctrl.request_make(text, kind="explain", pdf_path=pdf)
        assert _wait_until(lambda: _sel_board(w) is not None and not w._ai_jobs)
    return _sel_board(w)


def _boards(w):
    return [it for it in w._scene.items() if isinstance(it, _BoardItem)]


def test_outer_redo_uses_source_pdf_and_prefills_first_words(figure_pdf):
    w = _window()
    board = _place(w, figure_pdf, "처음 보는 사람용으로")
    bar = _bar(w)
    assert bar.mode == "outer" and bar.line.text() == "처음 보는 사람용으로"     # 처음 쓴 말을 채워 둠
    assert "paper.pdf" in bar.caption_label.text() and "m1" in bar.caption_label.text()
    assert not bar.exit_btn.isVisibleTo(bar)
    seen = []

    def gen(_key, pdf, note="", **_k):
        seen.append((pdf, note))
        return json.dumps(dict(SPEC, _pdf=pdf, title="새 제목"), ensure_ascii=False), "m2"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", side_effect=gen):
        bar.line.setText("중학생용으로")
        bar.go_btn.click()
        assert _wait_until(lambda: _sel_board(w) is not None and _sel_board(w) is not board and not w._ai_jobs)
    assert seen == [(figure_pdf, "중학생용으로")]                           # 바탕 설계서 없이 원본에서 새로
    new = _sel_board(w)
    assert board.scene() is w._scene and new.mapRectToScene(new.rect()).left() > board.mapRectToScene(board.rect()).right()
    assert new._ai["origin"] == "중학생용으로" and not new._ai["followup"]
    _close(w)


def test_outer_redo_missing_pdf_says_so(figure_pdf, tmp_path):
    import os
    import shutil
    pdf = str(tmp_path / "moved.pdf")
    shutil.copy(figure_pdf, pdf)
    w = _window()
    _place(w, pdf)
    os.remove(pdf)
    notes = []
    w._ai_ctrl.notice.connect(notes.append)
    got = []
    w._ai_ctrl.make_requested.connect(got.append)
    bar = _bar(w)
    assert w._board_redo(bar.board, "다시") is None and not got
    assert "moved.pdf" in w._ai_pill.text() or any("moved.pdf" in n for n in notes) or "moved.pdf" in w._ai_pill_notice
    _close(w)


def test_double_click_enters_inside_and_esc_or_outside_click_exits(figure_pdf):
    w = _window()
    board = _place(w, figure_pdf)
    view = w._view
    w._ai_ensure_visible(view, board.mapRectToScene(board.rect()))
    _app.processEvents()
    br = board.mapRectToScene(board.rect())
    # 보드 바탕(칸·글이 없는 왼쪽 아래 여백)
    empty = view.mapFromScene(QPointF(br.left() + 12, br.bottom() - 12))
    assert w._board_enter_at(view, empty) and w._board_inside is board
    bar = _bar(w)
    assert bar.mode == "inner_all" and "전체 고치기" in bar.name_label.text() and bar.exit_btn.isVisibleTo(bar)
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert w._board_inside is None and w.isVisible()                       # Esc = 보드 밖으로(편집기는 그대로)
    w._board_enter(board)
    outside = view.mapFromScene(QPointF(br.right() + 300, br.center().y()))
    w._board_view_press(view, outside)
    assert w._board_inside is None
    # 글자 위 더블클릭은 글 고치기 — 보드 안으로 가지 않는다
    text = next(it for it in w._board_scope(board) if hasattr(it, "toPlainText") and it.toPlainText() == SPEC["title"])
    assert not w._board_enter_at(view, view.mapFromScene(text.mapRectToScene(text.boundingRect()).center()))
    _close(w)


def test_inside_selection_sends_only_picked_parts(figure_pdf):
    w = _window()
    board = _place(w, figure_pdf)
    concept = next(it for it in w._board_scope(board) if getattr(it, "_pb_part", None) == "concepts[1]"
                   and hasattr(it, "toPlainText") and it.toPlainText() == "위치 인코딩")
    w._scene.clearSelection()
    concept.setSelected(True)
    bar = _bar(w)
    assert bar.mode == "inner_sel" and "선택 1개" in bar.name_label.text() and "핵심 개념 2" in bar.name_label.text()
    seen = []

    def gen(_key, text, *_a, base_code="", **_k):
        seen.append(text)
        return base_code, "m2"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
        bar.line.setText("더 쉽게")
        bar.line.returnPressed.emit()
        assert _wait_until(lambda: _sel_board(w) is not None and _sel_board(w) is not board and not w._ai_jobs)
    said = seen[0]
    assert "concepts[1]" in said and "위치 인코딩" in said and said.endswith("지시: 더 쉽게")
    new = _sel_board(w)
    assert new._ai["text"] == "더 쉽게" and new._ai["followup"]            # 보드엔 사용자가 쓴 말만
    _close(w)


def test_color_chips_white_black_rainbow(figure_pdf):
    w = _window()
    board = _place(w, figure_pdf)
    bar = _bar(w)
    assert [c.property("boardColor") for c in bar.chips[:2]] == ["#ffffff", "#1d1d1f"] and bar.chips[2] is bar.rainbow
    swatches = [b for b in bar.rainbow_menu.findChildren(type(bar.rainbow)) if b.property("boardColor")]
    assert len(swatches) == 8
    swatches[4].click()                                                    # 「어두운 칠판」
    assert board.bg().name() == "#24382f"
    w._board_bar_sync(w._view)
    assert bar.rainbow.isChecked() and not bar.chips[0].isChecked()
    bar.chips[1].click()
    w._board_bar_sync(w._view)
    assert board.bg().name() == "#1d1d1f" and bar.chips[1].isChecked() and not bar.rainbow.isChecked()
    _close(w)


def test_board_line_starts_five_rows_grows_to_twelve(figure_pdf):
    w = _window()
    _place(w, figure_pdf)
    line = _bar(w).line
    fm = line.fontMetrics()
    line.setText("")
    h5 = line.height()
    assert h5 >= 5 * fm.lineSpacing()
    line.setText("\n".join(str(i) for i in range(9)))
    assert line.height() > h5
    line.setText("\n".join(str(i) for i in range(30)))
    h12 = line.height()
    line.setText("\n".join(str(i) for i in range(40)))
    assert line.height() == h12 and h12 < 13 * fm.lineSpacing() + 40      # 12줄에서 멈추고 칸 안 스크롤
    _close(w)


def test_two_models_make_two_boards_side_by_side(figure_pdf):
    w = _window()
    w._ai_ctrl.set_picks(["gpt-6.1-sol", "gemini-3.8-flash"])
    used = []

    def gen(_key, pdf, note="", model="", **_k):
        used.append(model)
        return json.dumps(dict(SPEC, _pdf=pdf), ensure_ascii=False), model
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", side_effect=gen):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: len(_boards(w)) == 2 and not w._ai_jobs)
    w._ai_ctrl.set_picks([])
    assert sorted(used) == ["gemini-3.8-flash", "gpt-6.1-sol"]
    a, b = [x.mapRectToScene(x.rect()) for x in _boards(w)]
    assert not a.intersects(b)                                             # 겹치지 않게 나란히
    assert sorted(x._ai["model"] for x in _boards(w)) == ["gemini-3.8-flash", "gpt-6.1-sol"]
    _close(w)
