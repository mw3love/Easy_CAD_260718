"""데스크톱 메모 편집기 = 웹 메모 편집기(TipTap)와 같은 입력 규칙·글쇠(2026-10-22 사용자: 데스크톱 = 웹 + 추가 기능).

규칙표(`core_memo_edit.LINE_RULES`·`MARK_RULES`·`KEYS`)의 줄마다 편집기에 실제로 글쇠를 쳐 보고 결과 메모 줄을 본다
(웹 `e2e/flow9-keys`가 `keys.js` 표를 줄마다 확인하는 방식). 전엔 `---`가 Enter를 기다렸고, `` `코드` ``가 안 됐고, Ctrl+Enter가 웹과 달랐다.
"""
import copy

from _shared import _app  # noqa: F401  (QApplication)
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QInputMethodEvent, QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QApplication

from test_part66_desktop_web_kinds import DOCS, _win_with
from easycad.canvas import core_memo_edit as E

NO = Qt.KeyboardModifier.NoModifier
CTRL, SHIFT, ALT = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.AltModifier


def _open(lines):
    w, (memo,) = _win_with({**copy.deepcopy(DOCS["memo"]), "lines": lines})
    memo.web_double_click(w._view, memo.sceneBoundingRect().center())
    return w, memo, w._view._memo_editor


def _type(ed, text):
    """글자마다 글쇠 하나 — \\n = Enter, \\b = Backspace, ↓ = 아래 화살표."""
    for ch in text:
        if ch == "\n":
            ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, NO, "\r"))
        elif ch == "\b":
            ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backspace, NO, ""))
        elif ch == "↓":
            ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, NO, ""))
        else:
            k = ord(ch.upper()) if ch.isascii() and ch.isalnum() else Qt.Key.Key_Space if ch == " " else Qt.Key.Key_unknown
            ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, NO, ch))


def _key(ed, key, mods=NO):
    ed.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods, ""))


def _result(text, lines=None):
    w, memo, ed = _open(lines or [{"k": "p", "t": ""}])
    try:
        _type(ed, text)
        ed.commit()
        return memo.raw["lines"]
    finally:
        w.close()


# (친 글, 결과 줄) — LINE_RULES 줄마다 하나 이상(아래 시험이 빠진 규칙이 없는지 셈)
LINE_CASES = [
    ("# 글", [{"k": "h1", "t": "글"}]), ("## 글", [{"k": "h2", "t": "글"}]), ("### 글", [{"k": "h3", "t": "글"}]),
    ("#\n글", [{"k": "h1", "t": "글"}]),                                           # JS \s = Enter도(웹과 같음)
    ("- 글", [{"k": "ul", "t": "글"}]), ("+ 글", [{"k": "ul", "t": "글"}]), ("* 글", [{"k": "ul", "t": "글"}]),
    ("1. 글", [{"k": "ol", "t": "글"}]), ("7. 글", [{"k": "ol", "t": "글"}]),
    ("[] 글", [{"k": "todo", "t": "글"}]), ("[ ] 글", [{"k": "todo", "t": "글"}]), ("[x] 글", [{"k": "todo", "t": "글", "done": True}]),
    ("> 글", [{"k": "quote", "t": "글"}]),
    ("``` 글", [{"k": "code", "t": "글"}]), ("```\n글", [{"k": "code", "t": "글"}]), ("```py 글", [{"k": "code", "t": "글"}]), ("~~~ 글", [{"k": "code", "t": "글"}]),
    ("---글", [{"k": "hr", "t": ""}, {"k": "p", "t": "글"}]),                      # 세 번째 `-`에 바로(전엔 Enter를 기다림)
    ("—-글", [{"k": "hr", "t": ""}, {"k": "p", "t": "글"}]),
    ("___ 글", [{"k": "hr", "t": ""}, {"k": "p", "t": "글"}]), ("*** 글", [{"k": "hr", "t": ""}, {"k": "p", "t": "글"}]),
    ("1.글", [{"k": "p", "t": "1.글"}]), ("a - 글", [{"k": "p", "t": "a - 글"}]), ("-- 글", [{"k": "p", "t": "-- 글"}]),   # 안 걸리는 것
]


def test_line_rules_table_every_row_typed():
    hit = set()
    for typed, want in LINE_CASES:
        assert _result(typed) == want, typed
        prefix = typed.split("글")[0]                                               # 규칙에 걸리는 앞부분(띄어쓰기·Enter까지)
        hit |= {i for i, (rx, _) in enumerate(E.LINE_RULES) if rx.search(prefix)}
    assert hit == set(range(len(E.LINE_RULES)))                                     # 표의 줄을 하나도 빼먹지 않음


def test_mark_rules_bold_and_inline_code_then_plain_after():
    assert _result("a **굵게** b") == [{"k": "p", "t": "a 굵게 b", "runs": [[2, 2, None, True]]}]   # 뒤 「 b」는 안 굵음
    assert _result("__굵게__") == [{"k": "p", "t": "굵게", "runs": [[0, 2, None, True]]}]
    assert _result("값 `x = 1` 끝") == [{"k": "p", "t": "값 x = 1 끝", "runs": [[2, 5, None, False, None, True]]}]
    assert _result("a**b**") == [{"k": "p", "t": "a**b**"}]                       # 앞이 띄어쓰기·줄 처음일 때만(웹 정규식)
    assert _result("``x`") == [{"k": "p", "t": "``x`"}]                            # 백틱 둘 뒤는 안 걸림
    assert _result("``` a `b`", None)[0]["k"] == "code"                            # 코드 줄 안에선 꾸밈 규칙 없음
    assert _result("``` a `b`")[0]["t"] == "a `b`"


def test_backspace_right_after_rule_undoes_it():
    assert _result("- \b글") == [{"k": "p", "t": "- 글"}]                         # TipTap undoInputRule
    assert _result("---\b") == [{"k": "p", "t": "---"}]
    assert _result("`코`\b") == [{"k": "p", "t": "`코`"}]
    assert _result("- 가\b\b") == [{"k": "p", "t": ""}]                             # 다른 글을 친 뒤엔 보통 지우기 → 줄 맨 앞에서 목록 풂


def test_code_block_exits_on_third_enter_and_arrow_down():
    assert _result("```\na\n\n\n끝") == [{"k": "code", "t": "a"}, {"k": "p", "t": "끝"}]          # 빈 줄 두 번(Enter 세 번) = 코드 밖(exitOnTripleEnter)
    assert _result("```\na\n\n끝") == [{"k": "code", "t": "a"}, {"k": "code", "t": ""}, {"k": "code", "t": "끝"}]   # 빈 줄 하나는 코드 안
    assert _result("```\na↓끝") == [{"k": "code", "t": "a"}, {"k": "p", "t": "끝"}]                # 끝 줄에서 ↓ = 밖(exitOnArrowDown)
    assert _result("```\na\nb", None) == [{"k": "code", "t": "a"}, {"k": "code", "t": "b"}]
    w, memo, ed = _open([{"k": "code", "t": "a"}, {"k": "code", "t": "b"}])
    try:
        cur = ed.textCursor()
        cur.setPosition(ed.document().findBlockByNumber(1).position())
        ed.setTextCursor(cur)
        _type(ed, "\b")                                                              # 코드 줄 맨 앞 지우기 = 앞 줄과 붙음(전엔 보통 글이 됐음)
        ed.commit()
        assert memo.raw["lines"] == [{"k": "code", "t": "ab"}]
    finally:
        w.close()


def test_nested_list_enter_and_backspace_go_one_level_out():
    assert _result("\n", [{"k": "ul", "t": "", "lv": 1}]) == [{"k": "ul", "t": ""}]           # 빈 깊은 줄 Enter = 한 단계 바깥
    assert _result("\n\n", [{"k": "ul", "t": "", "lv": 1}]) == [{"k": "p", "t": ""}]          # 맨 바깥에서 한 번 더 = 보통 글
    w, memo, ed = _open([{"k": "ol", "t": "가", "lv": 2}])
    try:
        cur = ed.textCursor()
        cur.setPosition(0)
        ed.setTextCursor(cur)
        _type(ed, "\b")
        ed.commit()
        assert memo.raw["lines"] == [{"k": "ol", "t": "가", "lv": 1}]                         # 줄 맨 앞 지우기 = 한 단계 바깥(liftListItem)
    finally:
        w.close()


# (글쇠, 꾸밈키, 처음 줄, 결과 줄) — KEYS 표 줄마다
KEY_CASES = [
    ((Qt.Key.Key_B, CTRL), [{"k": "p", "t": "가나"}], [{"k": "p", "t": "가나", "runs": [[0, 2, None, True]]}]),
    ((Qt.Key.Key_I, CTRL), [{"k": "p", "t": "가나"}], [{"k": "p", "t": "가나", "runs": [[0, 2, None, False, None, False, "i"]]}]),
    ((Qt.Key.Key_U, CTRL), [{"k": "p", "t": "가나"}], [{"k": "p", "t": "가나", "runs": [[0, 2, None, False, None, False, "u"]]}]),
    ((Qt.Key.Key_X, CTRL | SHIFT), [{"k": "p", "t": "가나"}], [{"k": "p", "t": "가나", "runs": [[0, 2, None, False, None, False, "s"]]}]),
    ((Qt.Key.Key_E, CTRL), [{"k": "p", "t": "가나"}], [{"k": "p", "t": "가나", "runs": [[0, 2, None, False, None, True]]}]),
    ((Qt.Key.Key_7, CTRL | SHIFT), [{"k": "p", "t": "가"}], [{"k": "ol", "t": "가"}]),
    ((Qt.Key.Key_Ampersand, CTRL | SHIFT), [{"k": "p", "t": "가"}], [{"k": "ol", "t": "가"}]),   # Shift+7이 「&」로 와도
    ((Qt.Key.Key_8, CTRL | SHIFT), [{"k": "p", "t": "가"}], [{"k": "ul", "t": "가"}]),
    ((Qt.Key.Key_9, CTRL | SHIFT), [{"k": "p", "t": "가"}], [{"k": "todo", "t": "가"}]),
    ((Qt.Key.Key_8, CTRL | SHIFT), [{"k": "ul", "t": "가"}], [{"k": "p", "t": "가"}]),           # 한 번 더 = 끔
    ((Qt.Key.Key_8, CTRL | SHIFT), [{"k": "ol", "t": "가", "lv": 1}], [{"k": "ul", "t": "가", "lv": 1}]),   # 목록끼리 바꾸면 깊이 그대로
    ((Qt.Key.Key_1, CTRL | ALT), [{"k": "p", "t": "가"}], [{"k": "h1", "t": "가"}]),
    ((Qt.Key.Key_2, CTRL | ALT), [{"k": "p", "t": "가"}], [{"k": "h2", "t": "가"}]),
    ((Qt.Key.Key_3, CTRL | ALT), [{"k": "p", "t": "가"}], [{"k": "h3", "t": "가"}]),
    ((Qt.Key.Key_0, CTRL | ALT), [{"k": "h2", "t": "가"}], [{"k": "p", "t": "가"}]),
    ((Qt.Key.Key_B, CTRL | SHIFT), [{"k": "p", "t": "가"}], [{"k": "quote", "t": "가"}]),
    ((Qt.Key.Key_C, CTRL | ALT), [{"k": "p", "t": "가"}], [{"k": "code", "t": "가"}]),
    ((Qt.Key.Key_Return, CTRL), [{"k": "todo", "t": "가"}], [{"k": "todo", "t": "가", "done": True}]),
    ((Qt.Key.Key_Return, CTRL), [{"k": "todo", "t": "가", "done": True}], [{"k": "todo", "t": "가"}]),
]


def test_keys_table_every_row_pressed():
    seen = set()
    for (key, mods), start, want in KEY_CASES:
        w, memo, ed = _open(start)
        try:
            cur = ed.textCursor()
            cur.select(QTextCursor.SelectionType.Document)                          # 꾸밈 글쇠는 고른 글에
            ed.setTextCursor(cur)
            ev = QKeyEvent(QEvent.Type.KeyPress, key, mods, "")
            seen.add(E.KEYS[E.key_name(ev)])
            ed.keyPressEvent(ev)
            assert ed.isVisible(), (key, mods)                                       # 할 일 줄 Ctrl+Enter는 체크만(안 끝남)
            ed.commit()
            assert memo.raw["lines"] == want, (key, mods, start)
        finally:
            w.close()
    assert seen == set(E.KEYS.values()) - {"turn"}                                 # 표의 동작을 다 눌러 봄(전환 메뉴는 아래 따로)


def test_ctrl_enter_outside_todo_finishes_and_keys_beat_window_shortcuts():
    w, memo, ed = _open([{"k": "p", "t": "가"}])
    try:
        _key(ed, Qt.Key.Key_Return, CTRL)
        assert not ed.isVisible() and memo._editor is None                          # 할 일이 아니면 마침(웹 Finish)
    finally:
        w.close()
    w, memo, ed = _open([{"k": "p", "t": "가"}])
    try:
        ov = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_C, CTRL | ALT, "")
        ov.ignore()
        ed.sceneEvent(ov)
        assert ov.isAccepted()                                                       # 창의 Ctrl+Alt+C(스타일 복사)보다 편집기가 먼저
    finally:
        w.close()


def test_korean_ime_commit_runs_rules_but_preedit_does_not():
    w, memo, ed = _open([{"k": "p", "t": ""}])
    try:
        _type(ed, "`")
        ed.inputMethodEvent(QInputMethodEvent("코", []))                            # 조합 중 — 규칙 안 걸림
        e = QInputMethodEvent()
        e.setCommitString("코드")
        ed.inputMethodEvent(e)
        _type(ed, "`")
        ed.commit()
        assert memo.raw["lines"] == [{"k": "p", "t": "코드", "runs": [[0, 2, None, False, None, True]]}]
    finally:
        w.close()


def test_paste_is_plain_text_and_lines_continue_like_enter():
    w, memo, ed = _open([{"k": "ul", "t": ""}])
    try:
        QApplication.clipboard().setText("첫째\r\n둘째")
        _key(ed, Qt.Key.Key_V, CTRL)
        ed.commit()
        assert memo.raw["lines"] == [{"k": "ul", "t": "첫째"}, {"k": "ul", "t": "둘째"}]
    finally:
        w.close()


def _select_all(ed):
    cur = ed.textCursor()
    cur.select(QTextCursor.SelectionType.Document)
    ed.setTextCursor(cur)
    ed._sync_bar()


def test_format_bar_shows_on_selection_and_buttons_style_text():
    """웹 formatbar.jsx — 글을 고르면 위에 뜨고, 고른 게 없으면 숨음. 버튼을 눌러도 고치기가 안 끝남(포커스 안 뺏음)."""
    w, memo, ed = _open([{"k": "p", "t": "가나다"}, {"k": "quote", "t": "인용"}])
    try:
        ed._sync_bar()
        assert ed._bar is None or not ed._bar.isVisible()                            # 고른 게 없으면 없음
        _select_all(ed)
        bar = ed._bar
        assert bar.isVisible() and bar.b["bold"].focusPolicy() == Qt.FocusPolicy.NoFocus
        bar.b["bold"].click()
        assert bar.b["bold"].property("on") is True and ed.isVisible()              # 켜진 버튼은 강조, 편집은 계속
        bar.b["color"].click()
        assert bar.pal.isVisible()
        red = next(b for b in bar.pal.findChildren(type(bar.b["bold"])) if b.toolTip() == "빨강")
        red.click()
        assert not bar.pal.isVisible()
        ed.commit()
        assert memo.raw["lines"] == [{"k": "p", "t": "가나다", "runs": [[0, 3, "#ffd44c47", True]]},
                                     {"k": "quote", "t": "인용", "runs": [[0, 2, "#ffd44c47", True]]}]   # 인용 회색 위에 고른 색이 저장됨
    finally:
        w.close()


def test_format_bar_highlight_toggles_and_clear_resets_to_line_default():
    w, memo, ed = _open([{"k": "p", "t": "가나", "runs": [[0, 2, "#ffd44c47", True]]}, {"k": "quote", "t": "인용", "runs": [[0, 2, "#ffd44c47", False]]}])
    try:
        _select_all(ed)
        ed._bar.b["hl"].click()
        doc = ed.document()
        assert all(f.charFormat().hasProperty(E.QTextFormat.Property.BackgroundBrush) for f in [doc.begin().begin().fragment()])
        ed._bar.b["hl"].click()                                                      # 다시 누르면 지움
        assert not doc.begin().begin().fragment().charFormat().hasProperty(E.QTextFormat.Property.BackgroundBrush)
        ed._bar.b["hl"].click()
        ed._bar.b["clear"].click()                                                   # 꾸밈 지우기 = 줄 기본(인용은 회색 그대로 보이기만)
        ed.commit()
        assert memo.raw["lines"] == [{"k": "p", "t": "가나"}, {"k": "quote", "t": "인용"}]
    finally:
        w.close()


def test_turn_menu_ctrl_slash_arrows_enter_and_esc_only_closes_menu():
    """웹 memoedit.jsx 전환 메뉴 — Ctrl+/ 또는 막대 「줄 ▾」, ↑↓ Enter, Esc = 메뉴만 닫음, 다른 글쇠 = 닫고 글로."""
    w, memo, ed = _open([{"k": "p", "t": "가"}])
    try:
        _key(ed, Qt.Key.Key_Slash, CTRL)
        assert ed._turn is not None and [b.text() for b in ed._turn.items][:3] == ["텍스트", "제목1", "제목2"]
        _key(ed, Qt.Key.Key_Escape)
        assert ed._turn is None and ed.isVisible()                                   # 메뉴만 닫힘
        _key(ed, Qt.Key.Key_Slash, CTRL)
        _key(ed, Qt.Key.Key_Down)
        _key(ed, Qt.Key.Key_Down)
        _key(ed, Qt.Key.Key_Return)                                                  # 제목2
        assert ed._turn is None
        _key(ed, Qt.Key.Key_Slash, CTRL)
        _key(ed, Qt.Key.Key_Up)                                                      # 맨 위에서 ↑ = 맨 아래(인용)로 돎
        _key(ed, Qt.Key.Key_Return)
        _type(ed, "\n")                                                              # (인용에서 Enter = 인용 이어짐)
        _key(ed, Qt.Key.Key_Slash, CTRL)
        _type(ed, "x")                                                               # 다른 글쇠 = 메뉴 닫고 글
        assert ed._turn is None
        ed.commit()
        assert memo.raw["lines"] == [{"k": "quote", "t": "가"}, {"k": "quote", "t": "x"}]
    finally:
        w.close()
    w, memo, ed = _open([{"k": "ul", "t": "가", "lv": 2}])
    try:
        _select_all(ed)
        ed._bar.b["turn"].click()                                                    # 막대 「줄 ▾」도 같은 메뉴, 열린 동안 막대는 숨음
        assert ed._turn is not None and not ed._bar.isVisible()
        ed._turn.items[6].click()                                                    # 할 일 목록 — 목록에서 빠져나온 뒤(깊이 0)
        ed.commit()
        assert memo.raw["lines"] == [{"k": "todo", "t": "가"}]
    finally:
        w.close()


# ---- 줄 손잡이 ⠿·줄 고르기·끌어 옮기기(웹 Editor.jsx 「메모 2차」) ----
LL = [{"k": "h2", "t": "제목"}, {"k": "ul", "t": "가"}, {"k": "ul", "t": "가-1", "lv": 1}, {"k": "p", "t": "나"}, {"k": "todo", "t": "다"}]


def _memo_win(lines=LL):
    return _win_with({**copy.deepcopy(DOCS["memo"]), "lines": copy.deepcopy(lines)})


def _row_scene(memo, i):
    from easycad.canvas.core_memo import memo_layout
    r = next(x for x in memo_layout(memo.raw, memo.rect().width())["rows"] if x["i"] == i)
    return memo.mapToScene(QPointF(memo.rect().left() + 60, memo.rect().top() + r["cy"]))


def _handle_scene(w, memo, i):
    from easycad.canvas.core_memo import line_unit
    from easycad.canvas.core_memo_lines import _zoom
    memo._hov = tuple(line_unit(memo.raw["lines"], i))                                 # 마우스를 그 줄에 올린 것과 같음
    return memo.mapToScene(memo.handle_rect(memo._hov[0], _zoom(w._view, memo)).center())


def _press(w, scene, mods=NO, release_at=None):
    from PyQt6.QtGui import QMouseEvent
    v = w._view

    def ev(t, p, btn, btns):
        vp = v.mapFromScene(p)
        return QMouseEvent(t, QPointF(vp), QPointF(v.viewport().mapToGlobal(vp)), btn, btns, mods)
    v.mousePressEvent(ev(QEvent.Type.MouseButtonPress, scene, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    end = scene
    if release_at is not None:
        for t in (0.3, 0.7, 1.0):
            v.mouseMoveEvent(ev(QEvent.Type.MouseMove, scene + (release_at - scene) * t, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
        end = release_at
    v.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))
    QApplication.processEvents()


def test_line_unit_and_handle_rect_follow_web():
    from easycad.canvas.core_memo import line_unit
    assert [line_unit(LL, i) for i in range(5)] == [[0, 1], [1, 3], [2, 3], [3, 4], [4, 5]]   # 목록 = 더 깊은 아래 줄까지
    w, (memo,) = _memo_win()
    try:
        b = memo.handle_rect(1, 1.0)
        assert b.width() == 16 and b.right() <= memo.rect().left() + 26                 # 왼쪽 여백 안, 화면 16×22
        assert memo.handle_rect(1, 0.25).right() < memo.rect().left()                   # 많이 줄이면 바깥으로
        assert tuple(memo.row_at(memo.mapFromScene(_row_scene(memo, 2)))) == (2, 3)
    finally:
        w.close()


def test_handle_click_selects_line_and_menu_then_shift_ctrl_pick():
    from unittest.mock import patch
    from PyQt6.QtWidgets import QMenu
    w, (memo,) = _memo_win()
    try:
        with patch.object(QMenu, "popup") as pop:
            _press(w, _handle_scene(w, memo, 1))                                         # 누르기 = 그 덩어리(가 + 가-1) 고르기 + 메뉴
        assert memo._line_sel == {"s": 1, "e": 3} and pop.called and w._view._line_memo is memo
        _press(w, _row_scene(memo, 4), SHIFT)                                            # 고른 채 Shift+줄 글자 = 이어서
        assert memo._line_sel == {"s": 1, "e": 5}
        memo.set_line_sel({"s": 0, "e": 1})
        _press(w, _row_scene(memo, 3), CTRL)                                             # Ctrl+클릭 = 따로 더함
        assert memo._line_sel == {"s": 3, "e": 4, "more": [[0, 1]]}
        _press(w, _row_scene(memo, 0), CTRL)                                             # 다시 Ctrl+클릭 = 뺌
        assert memo._line_sel == {"s": 3, "e": 4}
        _press(w, memo.mapToScene(memo.rect().center()) + QPointF(0, 300))              # 다른 데 누르기 = 풂
        assert memo._line_sel is None
    finally:
        w.close()


def test_selected_lines_keys_delete_dup_todo_arrows_enter_and_undo():
    w, (memo,) = _memo_win()
    v = w._view
    key = lambda k, m=NO: v.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, m, ""))   # noqa: E731
    try:
        memo.set_line_sel({"s": 3, "e": 4})                                              # 「나」
        key(Qt.Key.Key_D, CTRL)
        assert [l["t"] for l in memo.raw["lines"]] == ["제목", "가", "가-1", "나", "나", "다"] and memo._line_sel == {"s": 4, "e": 5}
        key(Qt.Key.Key_Down, SHIFT)                                                      # 넓히기
        assert memo._line_sel == {"s": 4, "e": 6}
        key(Qt.Key.Key_Return, CTRL)                                                     # 고른 할 일 체크
        assert memo.raw["lines"][5].get("done") is True
        key(Qt.Key.Key_Delete)
        assert [l["t"] for l in memo.raw["lines"]] == ["제목", "가", "가-1", "나"] and memo._line_sel is None
        w.undo()
        assert [l["t"] for l in memo.raw["lines"]] == ["제목", "가", "가-1", "나", "나", "다"]   # 지우기도 Ctrl+Z 한 칸
        memo.set_line_sel({"s": 1, "e": 3})
        key(Qt.Key.Key_Up)                                                               # 옮겨 고르기 = 위 덩어리
        assert memo._line_sel == {"s": 0, "e": 1}
        key(Qt.Key.Key_Escape)
        assert memo._line_sel is None and v._line_memo is None
        memo.set_line_sel({"s": 1, "e": 3})
        key(Qt.Key.Key_Return)                                                           # Enter = 고치기, 커서는 그 줄 끝
        ed = v._memo_editor
        assert ed.isVisible() and ed.textCursor().block().text() == "가"
        _type(ed, "!")
        key(Qt.Key.Key_Escape)                                                           # 고치는 중 Esc(창 경로) = 마치고 커서 줄 고르기
        assert memo.raw["lines"][1]["t"] == "가!" and memo._line_sel == {"s": 1, "e": 3} and memo._editor is None
    finally:
        w.close()


def test_line_menu_turn_color_link_dup_delete():
    w, (memo,) = _memo_win([{"k": "p", "t": "주소 https://a.kr 보기"}, {"k": "p", "t": "둘"}])
    try:
        def act(menu, text):
            for a in menu.actions():
                if a.menu() is not None:
                    if act(a.menu(), text):
                        return True
                elif a.text().split("\t")[0] == text:
                    a.trigger()
                    return True
            return False
        assert act(memo.line_menu([[0, 1]]), "제목1")
        assert memo.raw["lines"][0]["k"] == "h1"
        assert act(memo.line_menu([[0, 2]]), "빨강 텍스트")                            # 여러 줄 한꺼번에(웹과 같은 색 값)
        assert memo.raw["lines"][1]["runs"] == [[0, 1, "#d44c47", False]]
        assert act(memo.line_menu([[1, 2]]), "노랑 배경")
        assert memo.raw["lines"][1]["runs"] == [[0, 1, "#d44c47", False, "#66fdecc8"]]
        assert act(memo.line_menu([[0, 1]]), "링크 끄기") and memo.raw["lines"][0]["nolink"] is True
        assert "링크 켜기" in [a.text() for a in memo.line_menu([[0, 1]]).actions()]
        assert act(memo.line_menu([[1, 2]]), "복제") and len(memo.raw["lines"]) == 3
        assert act(memo.line_menu([[1, 3]]), "삭제") and len(memo.raw["lines"]) == 1
        kinds = memo.line_menu([[0, 1]], kinds_only=True)                                 # Ctrl+/ = 전환 목록만
        assert [a.text() for a in kinds.actions()][:2] == ["텍스트", "✓ 제목1"]
    finally:
        w.close()


def test_drag_handle_reorders_moves_to_other_memo_and_out_to_new_memo():
    from easycad.canvas.core_web import _MemoItem
    other = {**copy.deepcopy(DOCS["memo"]), "uid": "m2", "pos": [700, 0], "lines": [{"k": "p", "t": "다른"}]}
    w, (memo, m2) = _win_with({**copy.deepcopy(DOCS["memo"]), "lines": copy.deepcopy(LL)}, other)
    m2._fit_height(m2.raw)
    try:
        _press(w, _handle_scene(w, memo, 3), release_at=_row_scene(memo, 0) - QPointF(0, 6))   # 「나」를 맨 위로
        assert [l["t"] for l in memo.raw["lines"]] == ["나", "제목", "가", "가-1", "다"]
        w.undo()
        assert [l["t"] for l in memo.raw["lines"]] == [l["t"] for l in LL]
        _press(w, _handle_scene(w, memo, 1), release_at=m2.mapToScene(m2.rect().bottomLeft()) + QPointF(60, -4))   # 「가」 덩어리를 다른 메모 끝으로
        assert [l["t"] for l in m2.raw["lines"]] == ["다른", "가", "가-1"] and m2.raw["lines"][2]["lv"] == 1
        assert [l["t"] for l in memo.raw["lines"]] == ["제목", "나", "다"]
        w.undo()                                                                           # 두 메모가 Ctrl+Z 한 칸에
        assert [l["t"] for l in m2.raw["lines"]] == ["다른"] and len(memo.raw["lines"]) == 5
        n0 = len([x for x in w._scene.items() if isinstance(x, _MemoItem)])
        _press(w, _handle_scene(w, memo, 4), release_at=memo.mapToScene(memo.rect().bottomLeft()) + QPointF(0, 400))   # 밖 = 새 메모
        memos = [x for x in w._scene.items() if isinstance(x, _MemoItem)]
        assert len(memos) == n0 + 1 and [l["t"] for l in memo.raw["lines"]] == ["제목", "가", "가-1", "나"]
        new = next(x for x in memos if x not in (memo, m2))
        assert new.raw["lines"] == [{"k": "todo", "t": "다"}] and new.isSelected()
        w.undo()
        assert len([x for x in w._scene.items() if isinstance(x, _MemoItem)]) == n0
        _press(w, _handle_scene(w, m2, 0), release_at=memo.mapToScene(memo.rect().bottomLeft()) + QPointF(0, 400))   # 마지막 줄을 끌어내면 빈 메모는 지움
        assert m2.scene() is None
        w.undo()
        assert m2.scene() is w._scene and m2.raw["lines"] == [{"k": "p", "t": "다른"}]
    finally:
        w.close()
