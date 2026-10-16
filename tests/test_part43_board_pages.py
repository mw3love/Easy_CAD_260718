"""§8 항목53 4단계(가) 여러 장(2026-10-16) — 보드가 출력 바닥(BOARD_MAX_W)보다 커지면 덜 중요한 칸부터 2장으로,
흐름도 혼자 크면 흐름도부터, 「한 장으로」면 2장 대신 빼고 「생략」 표시, 묶음은 PDF 여러 쪽, 배치는 줌과 무관.
"""
import json
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

import fitz

from easycad.ai import pdf_to_board as pb
from easycad.canvas.annotator_core import _BoardItem

BASE = {
    "kind": "paper-board", "title": "논문", "meta": "저자, 2017", "one_line": "한 줄 요약.",
    "three_lines": [{"text": "첫째", "pages": "p.1"}],
    "concepts": [{"name": "개념", "body": "설명", "pages": "p.2"}],
    "flow": {"direction": "TD", "lanes": [], "steps": [{"id": "a", "text": "입력"}, {"id": "b", "text": "출력"}],
             "links": [{"from": "a", "to": "b"}]},
    "results": {"title": "점수", "pages": "p.8", "bars": [{"label": "우리", "value": 3, "mine": True}], "note": ""},
    "numbers": [], "figure": None, "terms": [{"term": "용어", "meaning": "뜻"}],
    "verdict": [{"type": "한계", "text": "작다", "pages": "p.9"}],
}


N = 40   # 꺾어 내려도(2026-10-16) 1장 가운데 칸에 안 들어가는 긴 흐름도


def _heavy(pages=None):
    d = json.loads(json.dumps(BASE))
    d["flow"] = {"direction": "TD", "lanes": ["앞", "뒤"],
                 "steps": [{"id": f"s{i}", "text": f"단계 {i}", "lane": "앞" if i < N // 2 else "뒤"} for i in range(1, N + 1)],
                 "links": [{"from": f"s{i}", "to": f"s{i + 1}"} for i in range(1, N)]}
    if pages:
        d["_pages"] = pages
    return json.dumps(d, ensure_ascii=False)


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


def _boards(items):
    return [it for it in items if isinstance(it, _BoardItem)]


def _texts(items):
    return [it.toPlainText() for it in items if hasattr(it, "toPlainText")]


def test_small_board_stays_one_page():
    w = _window()
    _n, _a, _k, added = w._build_flow_items(json.dumps(BASE, ensure_ascii=False))
    b = _boards(added)
    assert len(b) == 1 and b[0]._set_id is None and b[0].rect().width() <= w.BOARD_MAX_W
    _close(w)


def test_big_flow_goes_to_page_two():
    w = _window()
    _n, _a, _k, added = w._build_flow_items(_heavy())
    b1, b2 = _boards(added)
    assert b1._set_id and b1._set_id == b2._set_id and (b1._page, b2._page) == (1, 2)
    assert b1.rect().width() <= w.BOARD_MAX_W
    assert abs(b1.mapRectToScene(b1.rect()).top() - b2.mapRectToScene(b2.rect()).top()) < 1   # 위를 맞춤
    assert b2.mapRectToScene(b2.rect()).left() > b1.mapRectToScene(b1.rect()).right()
    on1 = [it for it in added if w._board_at(it) is b1]
    on2 = [it for it in added if w._board_at(it) is b2]
    assert any("→ 2장에 이어서: 작동 흐름" in t for t in _texts(on1))
    assert not [it for it in on1 if getattr(it, "_flow_key", None)]          # 흐름도는 1장에 없음
    assert len([it for it in on2 if getattr(it, "_flow_key", None)]) == 2 * N - 1   # 단계 N + 연결 N-1
    assert any("2장 · 자세히" in t for t in _texts(on2))
    assert len(w._undo) == 1                                                  # 두 장이 한 번의 되돌리기
    _close(w)


def test_one_page_mode_omits_instead():
    w = _window()
    _n, _a, _k, added = w._build_flow_items(_heavy("one"))
    b = _boards(added)
    assert len(b) == 1 and b[0]._set_id is None
    assert any(t.startswith("생략(한 장으로): 작동 흐름") for t in _texts(added))
    _close(w)


def test_layout_does_not_depend_on_zoom():
    w = _window()
    _n, _a, _k, a1 = w._build_flow_items(_heavy())
    widths1 = [round(b.rect().width()) for b in _boards(a1)]
    w._view.scale(0.25, 0.25)
    _n, _a, _k, a2 = w._build_flow_items(_heavy())
    assert [round(b.rect().width()) for b in _boards(a2)] == widths1
    _close(w)


def test_set_exports_pdf_pages_and_bar_label(tmp_path):
    w = _window()
    _n, _a, _k, added = w._build_flow_items(_heavy())
    b1, b2 = _boards(added)
    w._scene.clearSelection()
    b2.setSelected(True)
    w._board_bar_sync(w._view)
    assert w._board_bar.name_label.text() == "보드 2/2" and "PDF 2쪽" in w._board_bar.pdf_action.text()
    path = w._board_export(b2, "pdf", path=str(tmp_path / "set.pdf"))
    with fitz.open(path) as doc:
        assert doc.page_count == 2
    assert w._scene.selectedItems() == [b2]                                   # 선택 되돌림
    _close(w)


def test_set_survives_save_and_load(tmp_path):
    from easycad.fileio.document import load_document, save_document
    w = _window()
    w._build_flow_items(_heavy())
    path = str(tmp_path / "p.ecad")
    save_document(w._scene, path)
    w2 = _window()
    load_document(w2._scene, path)
    boards = sorted(_boards(w2._scene.items()), key=lambda b: b._page)
    assert [b._page for b in boards] == [1, 2] and boards[0]._set_id == boards[1]._set_id
    _close(w)
    _close(w2)


def _wait_until(cond, ms=5000):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        _app.processEvents()
        if cond():
            return True
    return False


def test_bar_line_one_page_and_split_without_ai(tmp_path):
    w = _window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board", return_value=(_heavy(), "m")):
        w._ai_ctrl.request_make("", kind="explain", pdf_path=str(tmp_path / "x.pdf"))
        assert _wait_until(lambda: w._board_selected() is not None)
    assert len(_boards(w._scene.items())) == 2

    def say(text):
        w._board_enter(w._board_selected())   # 다시 배치 말은 보드 안에서(§8 항목56 — 테두리를 고르면 「PDF로 새로」)
        w._board_bar_sync(w._view)
        w._board_bar.line.setText(text)
        w._board_bar.line.returnPressed.emit()
        _app.processEvents()
    with _patch("easycad.ai.text_to_flow.generate_flow", side_effect=AssertionError("AI 부르면 안 됨")):
        say("한 장으로")
        assert len(_boards(w._scene.items())) == 1
        assert pb.parse_board(w._board_selected()._ai["spec"])["_pages"] == "one"
        say("나눠서")
        assert len(_boards(w._scene.items())) == 2
    _close(w)
