"""§8 항목53 2단계 「한 장 보드」(2026-10-16) — 논문 PDF → AI 보드 설계서 → 앱이 보드 틀 위에 배치.

- `easycad/ai/pdf_to_board.py` — 설계서 읽기(너그럽게)·지시문·이어 고치기(PDF 경로는 AI에 안 보냄).
- `host_board._build_paper_board` — 시안 ④의 세 줄 배치, 16:9 보드, 논문 그림 잘라 붙이기, 「도면 검사」 0개.
- 결과 막대 — 흐름도와 같은 임시 결과·이어 고치기(바탕 = 보드 설계서).
"""
import json
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

import fitz
import pytest
from PyQt6.QtGui import QColor

from easycad.ai import pdf_to_board as pb
from easycad.ai.gateway import GatewayResult
from easycad.canvas.annotator_core import _BoardItem, _ImageItem, _PolyArrowItem, BOARD_ASPECT
from easycad.canvas.drawing_check import check_drawing

SPEC = {
    "kind": "paper-board", "title": "Attention Is All You Need", "meta": "Vaswani 외, 2017",
    "one_line": "문장 전체를 한꺼번에 보며 어느 단어에 주목할지만 계산한다.", "highlight": "어느 단어에 주목할지",
    "three_lines": [{"text": "예전 방식은 느렸다.", "pages": "p.1"}, {"text": "어텐션만 쓴다.", "pages": "p.2"},
                    {"text": "번역 점수 최고.", "pages": "p.8"}],
    "concepts": [{"name": "어텐션", "body": "참고할 단어에 점수를 준다.", "pages": "p.3"},
                 {"name": "위치 인코딩", "body": "단어 위치를 따로 알려 준다.", "pages": "p.6"}],
    "flow": {"title": "어떻게 작동하나", "pages": "p.2–5", "direction": "TD", "lanes": [],
             "steps": [{"id": "a", "text": "문장 입력", "kind": "start"}, {"id": "b", "text": "셀프 어텐션"},
                       {"id": "c", "text": "다음 단어", "kind": "end"}],
             "links": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}], "focus": "b"},
    "results": {"title": "BLEU", "pages": "p.8", "bars": [{"label": "ConvS2S", "value": "25.16점"},
                                                          {"label": "Transformer", "value": 28.4, "mine": True}],
                "note": "0부터"},
    "numbers": [{"label": "학습 시간", "value": "3.5일", "note": "GPU 8장", "pages": "p.7"}],
    "figure": {"caption": "그림 1", "page": "p.1"},
    "terms": [{"term": "BLEU", "meaning": "번역 점수"}],
    "verdict": [{"type": "의의", "text": "빨리 배운다.", "pages": "p.6"},
                {"type": "의의", "text": "이후 큰 모델의 바탕.", "pages": "논문 밖 맥락"},
                {"type": "한계", "text": "긴 문장은 계산이 많다.", "pages": "p.6"}],
}
SPEC_TEXT = json.dumps(SPEC, ensure_ascii=False)


@pytest.fixture
def figure_pdf(tmp_path):
    from PyQt6.QtGui import QImage
    img = QImage(300, 200, QImage.Format.Format_RGB32)
    img.fill(QColor("#3366cc"))
    png = str(tmp_path / "fig.png")
    img.save(png)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Paper text")
    page.insert_image(fitz.Rect(72, 100, 372, 300), filename=png)
    path = str(tmp_path / "paper.pdf")
    doc.save(path)
    doc.close()
    return path


# ── 설계서 ─────────────────────────────────────────────────────────────────────

def test_parse_board_is_lenient():
    spec = pb.parse_board("앞말\n```json\n" + SPEC_TEXT + "\n```")
    assert spec["results"]["bars"][0]["value"] == 25.16 and spec["results"]["bars"][1]["mine"] is True
    assert spec["figure"] == {"caption": "그림 1", "page": 1}
    assert [v["outside"] for v in spec["verdict"]] == [False, True, False]
    assert spec["flow"]["steps"][1]["text"] == "셀프 어텐션" and spec["flow"]["pages"] == "p.2–5"
    bad = dict(SPEC, highlight="없는 구절", flow={"steps": []})
    spec = pb.parse_board(json.dumps(bad, ensure_ascii=False))
    assert spec["highlight"] == "" and spec["flow"] is None
    for raw in ("그냥 글", '{"kind": "paper-board"}', "[1]"):
        with pytest.raises(pb.BoardSpecError):
            pb.parse_board(raw)
    assert pb.is_board_spec(pb.dump_board(pb.parse_board(SPEC_TEXT))) and not pb.is_board_spec('{"steps": []}')


def test_figure_page_range_takes_first_page():
    """「p.3–5」 같은 쪽 범위를 35쪽으로 읽지 않는다(첫 숫자) — 2026-10-16 백지 검토."""
    spec = pb.parse_board(json.dumps(dict(SPEC, figure={"caption": "그림", "page": "p.3–5"}), ensure_ascii=False))
    assert spec["figure"]["page"] == 3

def test_refine_hides_local_path_and_keeps_it():
    code = pb.dump_board(dict(pb.parse_board(SPEC_TEXT), _pdf="C:/비밀/논문.pdf"))
    assert "C:/비밀" not in pb.build_refine_prompt("더 쉽게", code)
    seen = []

    def fake(_k, prompt, **_kw):
        seen.append(prompt)
        return GatewayResult(SPEC_TEXT, "m", None, 0.1)
    with _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=fake):
        out, _used = pb.refine_board("k", "더 쉽게", code, model="m")
    assert pb.parse_board(out)["_pdf"] == "C:/비밀/논문.pdf" and "더 쉽게" in seen[0]
    from easycad.ai import text_to_flow as ttf
    with _patch("easycad.ai.pdf_to_board.refine_board", return_value=("x", "m")) as rb:
        assert ttf.generate_flow("k", "더 쉽게", model="m", base_code=code) == ("x", "m")   # 막대 한 줄 이어 고치기 길
    assert rb.called


# ── 배치 ──────────────────────────────────────────────────────────────────────

def _window():
    w = CanvasWindow()
    w.resize(1600, 950)
    w.show()
    _app.processEvents()
    return w


def _close(w):
    for d in w._docs:
        d.dirty = False
    w.close()


def test_build_paper_board_layout(figure_pdf):
    w = _window()
    text = pb.dump_board(dict(pb.parse_board(SPEC_TEXT), _pdf=figure_pdf))
    n, a, kind, added = w._build_flow_items(text)
    board = added[0]
    assert isinstance(board, _BoardItem) and kind == "board" and (n, a) == (3, 2)
    r = board.mapRectToScene(board.rect())
    assert abs(r.width() / r.height() - BOARD_ASPECT) < 1e-6 and r.width() >= 1920
    for it in added[1:]:   # 모든 칸이 보드 안
        assert r.contains(it.sceneBoundingRect().center()), type(it).__name__
    texts = " ".join(it.toPlainText() for it in added if hasattr(it, "toPlainText"))
    for word in ("세 줄 요약", "핵심 개념 2가지", "어떻게 작동하나", "결과", "논문 속 그림", "용어 풀이", "의의와 한계",
                 "논문 밖 맥락", "p.2–5", "3.5일"):
        assert word in texts, word
    imgs = [it for it in added if isinstance(it, _ImageItem)]
    assert len(imgs) == 1 and imgs[0].rect().height() <= 240.5     # PDF 1쪽 그림을 잘라 붙임
    assert check_drawing(w._scene, items=added) == []
    assert len(w._undo) == 1 and w._undo[-1].ops[0][1] is board   # 한 번의 되돌리기
    w.undo()
    assert board.scene() is None and all(it.scene() is None for it in added)
    _close(w)


def test_board_in_dark_mode_has_readable_ink():
    w = _window()
    if not w._dark:
        w._toggle_theme()
    _n, _a, _k, added = w._build_flow_items(SPEC_TEXT)
    whites = [it for it in added if hasattr(it, "defaultTextColor") and it.defaultTextColor().name() == "#ffffff"]
    labels = [c for it in added for c in it.childItems()
              if hasattr(c, "defaultTextColor") and c.defaultTextColor().name() == "#ffffff"]
    arrows = [it for it in added if isinstance(it, _PolyArrowItem) and QColor(it._color).name() == "#ffffff"]
    assert not whites and not labels and not arrows    # 흰 보드 위 흰 잉크 없음(잉크 맞추기)
    _close(w)


def test_missing_figure_shows_placeholder():
    w = _window()
    _n, _a, _k, added = w._build_flow_items(SPEC_TEXT)   # PDF 경로 없음
    assert not [it for it in added if isinstance(it, _ImageItem)]
    assert any("논문 그림 자리" in it.toPlainText() for it in added if hasattr(it, "toPlainText"))
    _close(w)


# ── 임시 결과 · 이어 고치기 ─────────────────────────────────────────────────────────

def _wait_until(cond, ms=5000):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        _app.processEvents()
        if cond():
            return True
    return False


def _sel_board(w):
    b = w._board_selected()
    return b if b is not None and getattr(b, "_ai", None) else None


def _bar(w):
    w._board_bar_sync(w._view)
    return w._board_bar


def _scope(w, board):
    return [board] + w._board_scope(board)


def test_pdf_request_places_board_and_followup_puts_new_board_beside(figure_pdf):
    # 2026-10-16 사용자 피드백: 만들면 바로 넣고(채택·버리기 없음) 새 보드를 골라 두어 보드 막대(하나로 통합)가 바로 뜬다.
    w = _window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(SPEC_TEXT, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: _sel_board(w) is not None)
    board = _sel_board(w)
    assert w._ai_staged is None and board._ai["spec"] == SPEC_TEXT
    bar = _bar(w)
    assert bar.isVisible() and bar.line is not None and bar.line.isVisibleTo(bar)
    assert bar.accept_btn is None and bar.discard_btn is None and bar.history_btn is None   # 채택·버리기·기록 없음
    assert len(bar.chips) == 3 and all(not c.text() and not c.icon().isNull() for c in bar.chips)   # 화이트·블랙·무지개
    assert [c for c in bar.chips if c.isChecked()][0].property("boardColor") == "#ffffff"
    assert bar.mode == "outer" and "PDF로 새로" in bar.name_label.text() and bar.go_btn.text() == "새로 만들기"
    seen = []
    w._board_enter(board)                                     # 보드 안 → 이 보드를 바탕으로 고치기
    bar = _bar(w)
    assert bar.mode == "inner_all" and bar.line.text() == "" and bar.go_btn.text() == "고치기"

    def gen(*_a, base_code="", **_k):
        seen.append(base_code)
        return SPEC_TEXT.replace("빨리 배운다.", "학습이 빠르다."), "m"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
        bar.line.setText("의의를 더 짧게")
        bar.line.returnPressed.emit()
        assert _wait_until(lambda: _sel_board(w) is not None and _sel_board(w) is not board)
    assert seen == [SPEC_TEXT]
    new = _sel_board(w)
    req = w._ai_ctrl.entries()[-1].request
    assert req.kind == "explain" and "흐름도" not in w._ai_pill.text()   # 보드로 이어 감(막대 예시·알약 이름)
    assert all(it.scene() is w._scene for it in _scope(w, board))           # 원래 보드는 그대로
    assert new.mapRectToScene(new.rect()).left() > board.mapRectToScene(board.rect()).right()   # 새 보드는 오른쪽
    assert not hasattr(new, "_ai_marks") and "주황" not in req.entry.status_text()   # 바뀐 칸 표시는 없앰(§8 항목56)
    assert w._board_inside is None and new._ai["origin"] == ""   # 새 보드를 골랐으니 보드 밖, 처음 쓴 말은 바탕 것을 물려받음
    bar = _bar(w)
    assert "의의를 더 짧게" in bar.caption_label.text() and "m" in bar.caption_label.text()
    _close(w)


def test_board_bar_same_for_new_and_reopened_board(figure_pdf, tmp_path):
    """만든 직후와 저장했다 다시 연 뒤에 같은 막대(색·내보내기·고칠 점) — 설계서를 보드에 적어 둔다."""
    w = _window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(SPEC_TEXT, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: _sel_board(w) is not None)
    path = str(tmp_path / "board.ecad")
    w._doc_path = path
    w._save_doc()
    _close(w)
    w2 = _window()
    w2._open_path(path)
    b2 = [it for it in w2._scene.items() if isinstance(it, _BoardItem)][0]
    assert b2._ai["spec"] == SPEC_TEXT and b2._ai["model"] == "m"
    w2._scene.clearSelection()
    b2.setSelected(True)
    bar = _bar(w2)
    assert bar.line.isVisibleTo(bar) and "m" in bar.caption_label.text()
    _close(w2)


def test_board_delete_takes_its_contents(figure_pdf):
    """보드를 골라 Del — 안의 것도 같이 지운다(되돌리기 한 칸으로 전부 돌아옴)."""
    w = _window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(SPEC_TEXT, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: _sel_board(w) is not None)
    board = _sel_board(w)
    items = _scope(w, board)
    assert len(items) > 5
    w.delete_selection()
    assert all(it.scene() is None for it in items)
    w.undo()
    assert all(it.scene() is w._scene for it in items)
    _close(w)


def test_tick_does_not_overwrite_status_after_answer(figure_pdf):
    """결과를 받은 뒤 작업자가 끝나기 전 틈에 1초 시계가 돌아도 「넣음」이 「만드는 중… N초」로 덮이지 않는다
    (실제 창 두 논문 보드에서 남았던 것 — 2026-10-16 백지 검토). 틈은 재현이 들쭉날쭉해 답 받은 작업을 직접 넣어 본다."""
    import time
    from easycad.canvas.host_aimake import _AIJob
    w = _window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(SPEC_TEXT, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: _sel_board(w) is not None and not w._ai_jobs)
    req = w._ai_ctrl.entries()[-1].request
    assert req.entry.status_text().startswith("✓ 보드를 넣음")
    w._ai_jobs[object()] = _AIJob(req, None, time.monotonic() - 81, answered=True)
    w._ai_tick()
    assert req.entry.status_text().startswith("✓ 보드를 넣음")
    w._ai_jobs.clear()
    _close(w)


# ── 2026-10-16 사용자 테스트 피드백 — 「그림을 가운데·크게」·막대 앞 「지시 · 모델 · 초」 ──────────────────────────

@pytest.fixture
def tall_figure_pdf(tmp_path):
    """세로로 긴 논문 그림(트랜스포머 구조도처럼) — 아래 칸(높이 240)에선 손톱만 해졌다."""
    from PyQt6.QtGui import QImage
    img = QImage(200, 600, QImage.Format.Format_RGB32)
    img.fill(QColor("#3366cc"))
    png = str(tmp_path / "tall.png")
    img.save(png)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(150, 80, 350, 680), filename=png)
    path = str(tmp_path / "tall.pdf")
    doc.save(path)
    doc.close()
    return path


def _place_board(w, pdf):
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board",
                   return_value=(json.dumps(dict(SPEC, _pdf=pdf), ensure_ascii=False), "gemini-x")):   # 진짜도 _pdf를 붙인다
        w._ai_ctrl.request_make("", kind="explain", pdf_path=pdf)
        assert _wait_until(lambda: _sel_board(w) is not None)
    return _sel_board(w)


def _say_board(w, text):
    w._board_enter(_sel_board(w))   # 보드 안에서 말하기(§8 항목56)
    bar = _bar(w)
    bar.line.setText(text)
    bar.line.returnPressed.emit()
    _app.processEvents()


def test_bar_figure_big_relayouts_without_ai(tall_figure_pdf):
    w = _window()
    board = _place_board(w, tall_figure_pdf)
    w._set_board_color(board, "#1d1d1f")                               # 다시 배치해도 고른 보드 색 그대로
    small = [it for it in _scope(w, board) if isinstance(it, _ImageItem)]
    assert len(small) == 1 and small[0].rect().height() <= 240.5
    old_items, n_undo = _scope(w, board), len(w._undo)
    with _patch("easycad.ai.text_to_flow.generate_flow", side_effect=AssertionError("AI 부르면 안 됨")):
        _say_board(w, "그림 크게")
    board = _sel_board(w)
    items = _scope(w, board)
    assert pb.parse_board(board._ai["spec"])["_figure"] == "big" and len(w._undo) == n_undo + 1   # 되돌리기 한 칸
    assert all(it.scene() is None for it in old_items) and board.bg().name() == "#1d1d1f"
    img = next(it for it in items if isinstance(it, _ImageItem))
    assert img.rect().height() > 300                                   # 크게(1장에 남는 데까지)
    assert len([it for it in w._scene.items() if isinstance(it, _BoardItem)]) == 1   # 다른 칸을 2장으로 밀어내지 않는다
    b, r = board.sceneBoundingRect(), img.sceneBoundingRect()
    assert abs(r.center().x() - b.center().x()) < 2.0                  # 가운데
    assert check_drawing(w._scene, items=items) == []                  # 아래 칸과 겹치지 않음
    with _patch("easycad.ai.text_to_flow.generate_flow", side_effect=AssertionError("AI 부르면 안 됨")):
        _say_board(w, "그림 원래대로")
    assert [it for it in _scope(w, _sel_board(w)) if isinstance(it, _ImageItem)][0].rect().height() <= 240.5
    w.undo()
    w.undo()
    assert all(it.scene() is w._scene for it in old_items)             # Ctrl+Z로 처음 보드가 돌아옴
    _close(w)


def test_long_followup_with_figure_words_keeps_layout_flag(tall_figure_pdf):
    """「논문 그림을 가운데 배치하고 중학생 독자로 다시 써 줘」 — 배치는 앱이(바탕 설계서에 표시), 글은 AI로. 결과도 그림 크게."""
    w = _window()
    board = _place_board(w, tall_figure_pdf)
    first_req = w._ai_ctrl.entries()[-1].request
    seen = []

    def gen(_key, text, *_a, base_code="", **_k):
        seen.append((text, base_code))
        return base_code, "gemini-y"   # 글은 그대로 — 표시가 결과까지 이어지는지만 본다
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
        _say_board(w, "논문 그림을 가운데 배치하고 중학생 독자를 대상으로 다시 작성해줘")
        assert _wait_until(lambda: _sel_board(w) is not None and _sel_board(w) is not board)
    text, base = seen[0]
    assert "중학생" in text and pb.parse_board(base)["_figure"] == "big"
    new = _sel_board(w)
    assert [it for it in _scope(w, new) if isinstance(it, _ImageItem)][0].rect().height() > 300
    bar = _bar(w)
    cap = bar.caption_label.text()
    assert "gemini-y" in cap and "논문 그림을" in cap and "초" in cap   # 막대 앞 「지시 · 모델 · 초」
    assert "중학생" in bar.caption_label.toolTip()                      # 전체 지시는 툴팁
    new_req = w._ai_ctrl.entries()[-1].request
    assert "gemini-x" in first_req.entry.title() and "gemini-y" in new_req.entry.title()   # 기록 메뉴에도 모델
    _close(w)


def test_board_bar_switch_to_flow_uses_same_pdf(tall_figure_pdf):
    """보드 막대에 「흐름도로」 — 같은 PDF로 흐름도를 새로 만든다(보드는 그대로)."""
    w = _window()
    board = _place_board(w, tall_figure_pdf)
    got = []
    w._ai_ctrl.make_requested.connect(got.append)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value=""):   # 키 없음 — 요청 모양만 본다
        _say_board(w, "흐름도로 바꿔 줘")
    assert got and got[-1].kind == "flow" and got[-1].pdf_path == tall_figure_pdf
    assert board.scene() is w._scene
    _close(w)


def test_refine_keeps_figure_flag_and_hides_it_from_ai():
    spec = dict(SPEC, _figure="big", _pdf="C:/secret/paper.pdf")
    code = json.dumps(spec, ensure_ascii=False)
    prompt = pb.build_refine_prompt("중학생용으로", code)
    assert "_figure" not in prompt and "secret" not in prompt and "모든 글 칸" in prompt
    with _patch("easycad.ai.gateway.call_text_with_fallback", return_value=GatewayResult(SPEC_TEXT, "m", None, 0.1)):
        out, _m = pb.refine_board("k", "중학생용으로", code, model="m")
    assert pb.parse_board(out)["_figure"] == "big"
