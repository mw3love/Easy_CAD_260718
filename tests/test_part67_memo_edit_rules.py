"""데스크톱 메모 편집기 = 웹 메모 편집기(TipTap)와 같은 입력 규칙·글쇠(2026-10-22 사용자: 데스크톱 = 웹 + 추가 기능).

규칙표(`core_memo_edit.LINE_RULES`·`MARK_RULES`·`KEYS`)의 줄마다 편집기에 실제로 글쇠를 쳐 보고 결과 메모 줄을 본다
(웹 `e2e/flow9-keys`가 `keys.js` 표를 줄마다 확인하는 방식). 전엔 `---`가 Enter를 기다렸고, `` `코드` ``가 안 됐고, Ctrl+Enter가 웹과 달랐다.
"""
import copy

from _shared import _app  # noqa: F401  (QApplication)
from PyQt6.QtCore import QEvent, Qt
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
    assert seen == set(E.KEYS.values())                                            # 표의 동작을 다 눌러 봄


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
