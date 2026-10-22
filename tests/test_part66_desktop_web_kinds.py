"""§8 항목61 ④-3(2026-10-22) — 데스크톱이 웹 칠판 종류를 웹과 같은 모양으로 그리고, 메모는 고친다.

프레임·웹 카드·정리 문서·PDF·범례·메모가 각자 그림 클래스(`easycad/canvas/core_web.py`)로 열리고(전엔 글을 적은 대리 네모),
저장하면 원래 칸이 그대로다. 메모: 마크다운 ↔ 줄 왕복(꾸밈 지킴)·두 번 누르면 고치기 칸·할 일 상자 누르면 체크·Ctrl+Z.
화면 대조(두 앱 스크린숏 나란히)는 손으로 했다 — 여기는 그 결과가 깨지지 않게 잡는 시험.
"""
import copy
import os
import sys

from _shared import _app, _draw_helpers  # noqa: F401  (QApplication)
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from easycad.canvas import core_web as W  # noqa: E402
from easycad.canvas.core_memo import lines_to_md, md_to_lines, memo_layout  # noqa: E402
from easycad.canvas.host import CanvasWindow  # noqa: E402
from easycad.fileio.document import dict_to_item, item_to_dict  # noqa: E402

COMMON = {"scale": 1, "rotation": 0, "z": 1, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None}
LINES = [
    {"k": "h1", "t": "점검 메모"}, {"k": "p", "t": "굵게 강조와 색 글", "runs": [[0, 2, None, True], [6, 4, "#ffd44c47", False]]},
    {"k": "ul", "t": "첫째"}, {"k": "ul", "t": "깊은 것", "lv": 1}, {"k": "ol", "t": "하나"}, {"k": "ol", "t": "둘"},
    {"k": "todo", "t": "끝난 일", "done": True}, {"k": "todo", "t": "남은 일"}, {"k": "quote", "t": "인용"},
    {"k": "code", "t": "print('hi')"}, {"k": "code", "t": "x = 1"}, {"k": "hr", "t": ""},
    {"k": "table", "t": "", "rows": [["항목", "값"], ["전력", "3kW"]], "header": True, "cw": [0.4, 0.6]},
    {"k": "p", "t": "주소 https://example.com 링크"},
]
DOCS = {
    "memo": {**COMMON, "type": "memo", "uid": "m1", "pos": [0, 0], "rect": [0, 0, 340, 520], "fill": "#ffffffff", "lines": LINES, "fold": False},
    "frame": {**COMMON, "type": "frame", "uid": "f1", "pos": [0, 0], "rect": [0, 0, 900, 600], "no": 2, "name": "표지", "magnet": True},
    "web": {**COMMON, "type": "web", "uid": "w1", "pos": [400, 0], "rect": [0, 0, 300, 120], "url": "https://news.kbs.co.kr/a", "title": "KBS", "desc": "소식", "zoom": 0.8},
    "legend": {**COMMON, "type": "legend", "uid": "l1", "pos": [400, 200], "rect": [0, 0, 230, 120], "title": "범례", "names": {"a": "광케이블"},
               "rows": [{"key": "a", "color": "#ffe02424", "style": 2, "width": 2, "arrow": True}]},
    "doc": {**COMMON, "type": "doc", "uid": "d1", "pos": [800, 0], "rect": [0, 0, 300, 220], "title": "회의", "html": "<h1>회의</h1>", "model": "claude-opus-5-5"},
    "pdf": {**COMMON, "type": "pdf", "uid": "p1", "pos": [800, 300], "rect": [0, 0, 240, 360], "name": "보고서.pdf", "pages": 3,
            "url": "/api/pdf/x/1_abcdef", "sizes": [[600, 800]], "thumb": "data:image/jpeg;base64,AAAA", "text": "[1쪽]"},
}
CLS = {"memo": W._MemoItem, "frame": W._FrameItem, "web": W._WebCardItem, "legend": W._LegendItem, "doc": W._DocItem, "pdf": W._PdfItem}


def test_each_web_kind_opens_as_its_own_class_and_saves_unchanged():
    for t, d in DOCS.items():
        it = dict_to_item(copy.deepcopy(d))
        assert type(it) is CLS[t], t                       # 전엔 모두 _RectItem(대리 네모)
        assert not it.has_label()                           # 가운데 글(라벨)은 안 붙임 — 글은 웹 칸이 들고 그림
        assert item_to_dict(it) == d, t                     # 원래 칸 그대로(웹만 아는 칸 포함)
        c = it.clone()                                      # 복사·복제도 같은 종류·같은 칸(전엔 네모로 복제돼 웹 칸을 잃었음)
        assert type(c) is CLS[t] and item_to_dict(c) == d, t


def test_every_kind_paints_without_error():
    img = QImage(1200, 800, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    for d in DOCS.values():
        it = dict_to_item(copy.deepcopy(d))
        p.save()
        p.translate(*d["pos"])
        it.paint(p, None)
        p.restore()
    p.end()
    assert img.pixelColor(400 + 150, 10) != QColor("#ffffff")   # 웹 카드 위 띠가 그려짐


def test_memo_markdown_roundtrip_keeps_runs_and_tables():
    md = lines_to_md(LINES)
    assert "# 점검 메모" in md and "  - 깊은 것" in md and "[x] 끝난 일" in md and "```" in md and "| 항목 | 값 |" in md
    assert md_to_lines(md, LINES) == LINES                  # 꾸밈(굵게·색)·칸 너비까지 그대로
    edited = md.replace("[ ] 남은 일", "[x] 남은 일").replace("1. 둘", "1. 둘째") + "\n- 새 줄"
    out = md_to_lines(edited, LINES)
    assert out[1] == LINES[1]                               # 안 고친 줄 = 원래 줄(runs 포함)
    assert out[7] == {"k": "todo", "t": "남은 일", "done": True}
    assert out[5] == {"k": "ol", "t": "둘째"} and out[-1] == {"k": "ul", "t": "새 줄"}


def test_memo_layout_matches_web_numbers():
    """웹 memoLayout과 같은 치수 — 줄 수·접기 줄·높이가 글에 맞음."""
    lay = memo_layout({"lines": [{"k": "p", "t": f"{i}"} for i in range(10)], "fold": True}, 300)
    assert len(lay["rows"]) == 7 and lay["rows"][-1]["ln"].get("more")   # 앞 6줄 + 「… 4줄 더」
    assert memo_layout({"lines": LINES}, 340)["h"] > memo_layout({"lines": LINES[:3]}, 340)["h"]


def _win_with(*docs):
    w = CanvasWindow()
    w._confirm_close_doc = lambda doc: True   # 닫을 때 「저장할까요?」 창 없이(시험이 고친 문서)
    w.resize(1400, 900)
    w.show()
    QApplication.processEvents()
    items = [dict_to_item(copy.deepcopy(d)) for d in docs]
    for it in items:
        w._scene.addItem(it)
    QApplication.processEvents()
    return w, items


def test_frame_tags_number_like_web_order():
    a = {**DOCS["frame"], "uid": "a", "no": 1}
    b = {**DOCS["frame"], "uid": "b", "no": 1, "pos": [1000, 0]}
    c = {**DOCS["frame"], "uid": "c", "no": 2, "pos": [2000, 0], "name": ""}
    w, (fa, fb, fc) = _win_with(a, b, c)
    try:
        assert [f._tag()[1] for f in (fa, fb, fc)] == ["1 · 표지", "2 · 표지", "3"]   # 웹 orderedFrames: 번호, 같으면 문서 차례 → 1부터 다시
    finally:
        w.close()


def test_memo_todo_click_and_edit_then_undo():
    w, (memo,) = _win_with(DOCS["memo"])
    v = w._view
    try:
        press, release, click, move, drag_move, dbl = _draw_helpers(v)
        row = next(r for r in memo_layout(memo.raw, memo.rect().width())["rows"] if r["i"] == 7)   # 「남은 일」 상자
        b = row["box"]
        click(memo.mapToScene(memo.rect().topLeft() + QPointF(b["x"] + b["s"] / 2, b["y"] + b["s"] / 2)))
        assert memo.raw["lines"][7].get("done") is True                               # 상자 누르기 = 체크
        w.undo()
        assert not memo.raw["lines"][7].get("done")                                   # Ctrl+Z 한 번
        dbl(memo.mapToScene(memo.rect().center()))
        ed = v._memo_editor
        assert ed.isVisible() and ed.parentItem() is memo and "점검 메모" in ed.toPlainText()   # 두 번 누르기 = 메모 자리에서 고치기
        h0 = memo.rect().height()
        _type(ed, "\n- 하나 더\n또 하나")                                              # 「- 」 = 목록, 목록에서 Enter = 목록 이어짐
        ed.commit()
        assert memo.raw["lines"][-2:] == [{"k": "ul", "t": "하나 더"}, {"k": "ul", "t": "또 하나"}]
        assert memo.raw["lines"][1] == LINES[1]                                       # 안 고친 줄 꾸밈 그대로
        assert memo.rect().height() > h0                                              # 높이가 글에 맞춰 늘어남
        saved = item_to_dict(memo)
        assert saved["lines"][-1] == {"k": "ul", "t": "또 하나"} and saved["rect"][3] == memo.rect().height()
        w.undo()
        assert memo.raw["lines"] == LINES and memo.rect().height() == h0             # 고치기도 Ctrl+Z 한 번
    finally:
        w.close()


def test_web_card_double_click_does_not_add_label():
    from unittest.mock import patch
    w, (card,) = _win_with(DOCS["web"])
    opened = []
    try:
        *_, dbl = _draw_helpers(w._view)
        with patch.object(W.QDesktopServices, "openUrl", side_effect=lambda u: opened.append(u.toString()) or True):
            dbl(card.mapToScene(card.rect().center()))
        assert opened == ["https://news.kbs.co.kr/a"]                                   # 두 번 누르기 = 브라우저로
        assert not card.has_label() and "label" not in item_to_dict(card)
    finally:
        w.close()


def test_insert_memo_from_menu_opens_editor_and_saves_as_web_memo():
    w, _ = _win_with()
    try:
        w._act_memo.trigger()
        memo = next(it for it in w._scene.items() if isinstance(it, W._MemoItem))
        ed = w._view._memo_editor
        assert ed.isVisible() and memo.isSelected()                                  # 넣으면 바로 고치기 칸
        _type(ed, "# 오늘\n[] 점검표 쓰기")
        ed.commit()
        d = item_to_dict(memo)
        assert d["type"] == "memo" and d["lines"] == [{"k": "h1", "t": "오늘"}, {"k": "todo", "t": "점검표 쓰기"}]   # 웹 칠판이 그대로 여는 메모
        assert "메모" in [a.iconText() for a in w.findChildren(type(w._act_memo)) if a is w._act_memo]
    finally:
        w.close()


def test_memo_fill_from_properties_card_changes_web_fill_and_undoes():
    w, (memo,) = _win_with(DOCS["memo"])
    try:
        before = memo.capture_state()
        memo.apply_fill(QColor("#d3e5ef"))                      # 속성 카드 「채움」이 부르는 길
        w.push_undo_state([(memo, before)])
        assert item_to_dict(memo)["fill"] == "#ffd3e5ef"        # 웹 칸 그대로 바뀜(웹 칠판에서도 그 색)
        w.undo()
        assert item_to_dict(memo)["fill"] == "#ffffffff"
    finally:
        w.close()


def _key(v, k, mod=None):
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    v.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, mod or Qt.KeyboardModifier.NoModifier, ""))


def test_memo_keys_open_editor_not_label_or_mindmap():
    """2026-10-22 사용자 검토 뒤 — Ctrl+Enter가 메모 가운데에 글 상자(라벨)를 만들고, Enter는 마인드맵 형제 상자를 만들었음 → 셋 다 메모 고치기"""
    from PyQt6.QtCore import Qt
    for k, mod in ((Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier), (Qt.Key.Key_Return, None), (Qt.Key.Key_F2, None)):
        w, (memo,) = _win_with(DOCS["memo"])
        try:
            memo.setSelected(True)
            n0 = len(w._scene.items())
            _key(w._view, k, mod)
            assert not memo._label_alive() and w._view._memo_editor.isVisible(), k
            assert len(w._scene.items()) == n0 + 1, k                                    # 새 상자 없음(+1 = 메모 안 편집 글 상자)
            w._view._memo_editor.close()
        finally:
            w.close()


def test_memo_editor_lives_inside_memo():
    """편집 글 상자 = 메모의 자식(칠판 안) — 확대·이동을 원리적으로 같이 따라감(전엔 화면 위 창이라 그 자리에 남아 메모가 둘로 보였음 — 사용자 스크린숏)"""
    w, (memo,) = _win_with(DOCS["memo"])
    try:
        *_, dbl = _draw_helpers(w._view)
        dbl(memo.mapToScene(memo.rect().center()))
        ed = w._view._memo_editor
        assert ed.parentItem() is memo and ed.scene() is w._scene
        ed.close()
        assert ed.scene() is None and memo._editor is None                             # 마치면 떼어 냄
    finally:
        w.close()


def _type(ed, text):
    """편집 글 상자에 글쇠로 치기 — \\n = Enter, 띄어쓰기 = Space(입력 규칙이 걸리게)."""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    for ch in text:
        k = Qt.Key.Key_Return if ch == "\n" else Qt.Key.Key_Space if ch == " " else Qt.Key.Key_unknown
        ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier, "\r" if ch == "\n" else ch))


def _fresh_editor(lines):
    w, (memo,) = _win_with({**DOCS["memo"], "lines": lines})
    memo.web_double_click(w._view, memo.sceneBoundingRect().center())
    return w, memo, w._view._memo_editor


def test_memo_input_rules_turn_lines_as_you_type():
    """웹 TipTap과 같은 입력 규칙 — 줄 맨 앞에서 치는 순간 바뀜(전엔 마칠 때 한 번에)"""
    from easycad.canvas.core_memo_edit import KIND
    w, memo, ed = _fresh_editor([{"k": "p", "t": ""}])
    try:
        _type(ed, "# ")
        assert ed.textCursor().block().blockFormat().property(KIND) == "h1"           # 치는 순간 제목
        # 목록·인용·코드 안 Enter = 같은 종류 이어짐, 빈 줄에서 Enter = 그 줄이 보통 글로(TipTap과 같게)
        _type(ed, "제목\n- 하나\n둘\n\n1. 가\n\n[] 할 일\n\n> 인용\n\n```\ncode()\n\n---\n끝")
        ed.commit()
        assert memo.raw["lines"] == [{"k": "h1", "t": "제목"}, {"k": "ul", "t": "하나"}, {"k": "ul", "t": "둘"}, {"k": "ol", "t": "가"},
                                     {"k": "todo", "t": "할 일"}, {"k": "quote", "t": "인용"}, {"k": "code", "t": "code()"},
                                     {"k": "hr", "t": ""}, {"k": "p", "t": "끝"}]
    finally:
        w.close()


def test_memo_editor_tab_bold_backspace_and_todo_click():
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent, QTextCursor
    w, memo, ed = _fresh_editor([{"k": "ul", "t": "위"}, {"k": "ul", "t": "아래"}, {"k": "todo", "t": "일"}])
    try:
        key = lambda k, m=Qt.KeyboardModifier.NoModifier: ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, m, ""))   # noqa: E731
        cur = ed.textCursor()
        cur.setPosition(ed.document().findBlockByNumber(1).position())
        ed.setTextCursor(cur)
        key(Qt.Key.Key_Tab)                                                             # 깊이 +1
        cur = ed.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)
        key(Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)                         # 굵게
        cur = ed.textCursor()
        cur.setPosition(ed.document().findBlockByNumber(0).position())
        ed.setTextCursor(cur)
        key(Qt.Key.Key_Backspace)                                                       # 줄 맨 앞 지우기 = 목록 풂
        blk = ed.document().findBlockByNumber(2)
        from easycad.canvas.core_memo import MEMO, MEMO_KIND, PT, TEXT_MARGIN, BOARD_M
        from easycad.canvas.core_memo_edit import DONE
        r = ed.document().documentLayout().blockBoundingRect(blk)
        bf, px = blk.blockFormat(), MEMO_KIND["todo"]["pt"] * PT
        box_c = QPointF(TEXT_MARGIN + bf.leftMargin() - MEMO["INDENT"] + 2 + px * 0.45, r.y() + BOARD_M["lineSpacing"] * px / 2)
        assert ed._box_at(box_c) is not None and ed._box_at(QPointF(r.right() - 2, box_c.y())) is None   # 그린 상자 자리 = 누를 자리
        ed._set_kind(QTextCursor(blk), "todo", None, True)                              # 상자 누르기와 같은 길
        assert blk.blockFormat().property(DONE)
        ed.commit()
        assert memo.raw["lines"] == [{"k": "p", "t": "위"}, {"k": "ul", "t": "아래", "lv": 1, "runs": [[0, 2, None, True]]},
                                     {"k": "todo", "t": "일", "done": True}]
    finally:
        w.close()


def test_memo_width_change_refits_height():
    memo = dict_to_item(copy.deepcopy(DOCS["memo"]))
    h_wide = memo.rect().height()
    memo.setRect(QRectF(0, 0, 200, h_wide))                                            # 폭만 줄임(크기 손잡이)
    assert memo.rect().height() == memo_layout(memo.raw, 200)["h"] > h_wide            # 줄이 더 꺾인 만큼 높이도


def test_dxf_export_keeps_web_kind_text(tmp_path):
    import ezdxf
    from PyQt6.QtWidgets import QGraphicsScene
    from easycad.fileio.dxf_export import export_dxf
    sc = QGraphicsScene()
    for t in ("memo", "web", "legend"):
        sc.addItem(dict_to_item(copy.deepcopy(DOCS[t])))
    p = tmp_path / "w.dxf"
    export_dxf(sc, str(p))
    texts = " ".join(e.text for e in ezdxf.readfile(str(p)).modelspace() if e.dxftype() == "MTEXT")
    assert "점검 메모" in texts and "news.kbs.co.kr" in texts and "광케이블" in texts          # 전엔 테두리만 나가 글이 빠졌음
