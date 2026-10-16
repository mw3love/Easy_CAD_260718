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


def test_pdf_request_stages_board_and_followup_sends_board(figure_pdf):
    w = _window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(SPEC_TEXT, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    assert isinstance(st.items[0], _BoardItem) and st.request.result_text == SPEC_TEXT
    seen = []

    def gen(*_a, base_code="", **_k):
        seen.append(base_code)
        return SPEC_TEXT.replace("빨리 배운다.", "학습이 빠르다."), "m"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
        line = st.bar.line
        line.setText("의의를 더 짧게")
        line.returnPressed.emit()
        assert _wait_until(lambda: w._ai_staged is not None and w._ai_staged is not st)
    assert seen == [SPEC_TEXT]
    new = w._ai_staged
    assert new.alt is st and isinstance(new.items[0], _BoardItem)
    assert new.request.kind == "explain" and "흐름도" not in w._ai_pill.text()   # 보드로 이어 감(막대 예시·알약 이름)
    assert "나란히" in new.request.entry.status_text()
    assert w._ai_items_rect(new.items).left() > w._ai_items_rect(st.items).right()   # 원본 옆에 나란히
    _close(w)


def test_tick_does_not_overwrite_status_after_answer(figure_pdf):
    """결과를 받은 뒤 작업자가 끝나기 전 틈에 1초 시계가 돌아도 「임시로 놓음」이 「만드는 중… N초」로 덮이지 않는다
    (실제 창 두 논문 보드에서 남았던 것 — 2026-10-16 백지 검토). 틈은 재현이 들쭉날쭉해 답 받은 작업을 직접 넣어 본다."""
    import time
    from easycad.canvas.host_aimake import STAGED_TEXT, _AIJob
    w = _window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(SPEC_TEXT, "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=figure_pdf)
        assert _wait_until(lambda: w._ai_staged is not None and not w._ai_jobs)
    req = w._ai_staged.request
    assert req.entry.status_text().startswith(STAGED_TEXT)
    w._ai_jobs[object()] = _AIJob(req, None, time.monotonic() - 81, answered=True)
    w._ai_tick()
    assert req.entry.status_text().startswith(STAGED_TEXT)
    w._ai_jobs.clear()
    _close(w)
