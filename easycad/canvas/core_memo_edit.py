"""데스크톱 메모를 메모 자리에서 그대로 고친다(§8 항목61 ④-3 2단계, 2026-10-22 사용자: 마크다운이 바로바로 반영 안 됨).

메모의 자식 글 상자(`QGraphicsTextItem`) — 칠판 안이라 확대·이동을 같이 따라가고, 고치는 동안 메모는 바탕만 그린다.
메모 줄 하나 = 문서 블록 하나(종류는 블록 속성), 메모 안 표 = 문서 표. 글자 꾸밈(굵게·색·기울임·밑줄·취소선·형광펜·고정폭)은
문서 글자 서식으로 들고 고친다 — 마칠 때 다시 메모 줄(`lines`·`runs`)로. 치수는 메모 그리기(`core_memo`)와 같은 숫자.
입력 규칙은 웹 TipTap과 같게: 줄 맨 앞 `# `·`## `·`### `·`- `·`1. `·`[] `·`> ` + 띄어쓰기, ```` ``` ````·`---` + Enter.
"""
import copy
import re

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QPainterPath, QPen, QTextBlockFormat, QTextCharFormat,
                         QTextCursor, QTextDocument, QTextFormat, QTextLength, QTextTableFormat)
from PyQt6.QtWidgets import QGraphicsTextItem

from easycad.canvas.core_memo import (BOARD_M, CODE_BAND, LISTY, MEMO, MEMO_KIND, MONO_FAMILIES, MUTED, PT, TEXT_MARGIN,
                                      _board_families, _qcolor, _table_widths, ol_numbers)

KIND = QTextFormat.Property.UserProperty + 1    # 블록 종류(p·h1·…·_skip = 표 앞뒤로 Qt가 넣는 빈 줄)
LV = QTextFormat.Property.UserProperty + 2      # 목록 깊이
DONE = QTextFormat.Property.UserProperty + 3    # 할 일 끝
DERIVED = QTextFormat.Property.UserProperty + 4  # 끝난 할 일의 회색 글(꾸밈이 아니라 보이기만 — 줄로 되돌릴 때 버림)
INK = QColor("#1f1f1f")


def _base_font(k: str) -> QFont:
    K = MEMO_KIND.get(k, MEMO_KIND["p"])
    f = QFont()
    f.setFamilies(MONO_FAMILIES if K.get("mono") else _board_families())
    f.setPointSizeF(K["pt"])   # 칠판 글과 같은 pt(96dpi에서 메모 그리기 px와 같음)
    f.setWeight(QFont.Weight(700 if K.get("bold") else 400))
    return f


def _indent(k: str, lv: int) -> float:
    return (lv + 1) * MEMO["INDENT"] if k in LISTY else MEMO["QUOTE"] if k == "quote" else 0.0


def _block_fmt(k: str, lv: int = 0, done: bool = False, first: bool = False, join_prev: bool = False) -> QTextBlockFormat:
    bf = QTextBlockFormat()
    bf.setProperty(KIND, k)
    bf.setProperty(LV, lv)
    bf.setProperty(DONE, bool(done))
    bf.setLeftMargin(_indent(k, lv))
    K = MEMO_KIND.get(k, MEMO_KIND["p"])
    gap = 0 if first or join_prev else K.get("gap", MEMO["GAP"]) + 2 * TEXT_MARGIN   # 메모 그리기: 줄 사이 = 여백 둘 + 간격
    bf.setTopMargin(gap)
    if k == "hr":
        bf.setTopMargin(gap + MEMO["HR"] - TEXT_MARGIN)
        bf.setBottomMargin(MEMO["HR"] - TEXT_MARGIN)
    return bf


def _char_fmt(k: str, part: dict | None = None, done: bool = False) -> QTextCharFormat:
    cf = QTextCharFormat()
    mono = k == "code" or bool(part and part.get("mono"))
    f = _base_font(k)
    if mono and k != "code":
        f.setFamilies(MONO_FAMILIES)
    cf.setFont(f)
    if part:
        if part.get("bold"):
            cf.setFontWeight(700)
        deco = part.get("deco") or ""
        cf.setFontItalic("i" in deco)
        cf.setFontUnderline("u" in deco)
        cf.setFontStrikeOut("s" in deco)
        if part.get("color"):
            cf.setForeground(QBrush(_qcolor(part["color"], "#1f1f1f")))
        if part.get("bg"):
            cf.setBackground(QBrush(_qcolor(part["bg"], "#00000000")))
            cf.setProperty(QTextFormat.Property.UserProperty + 9, part["bg"])   # 원래 값(배열 등) 그대로 되돌리려고
        if part.get("color"):
            cf.setProperty(QTextFormat.Property.UserProperty + 8, part["color"])
    if done and not (part and part.get("color")):
        cf.setForeground(QBrush(QColor(MUTED)))
        cf.setProperty(DERIVED, True)
    elif k == "quote" and not (part and part.get("color")):
        cf.setForeground(QBrush(QColor("#52525b")))
        cf.setProperty(DERIVED, True)
    return cf


def _parts(text: str, runs) -> list:
    from easycad.canvas.core_memo import runs_to_lines
    return [p for line in runs_to_lines(text, runs) for p in line]


def lines_to_doc(lines, doc: QTextDocument, width: float):
    """메모 줄 → 편집 문서."""
    doc.clear()
    doc.setDocumentMargin(TEXT_MARGIN)
    doc.setTextWidth(width)
    doc.setDefaultFont(_base_font("p"))
    cur = QTextCursor(doc)
    lines = list(lines or [{"k": "p", "t": ""}])
    reuse = True   # 첫 블록(문서에 처음부터 있는 것)·표 뒤 블록은 새로 만들지 않고 씀
    prev_k = None
    for i, ln in enumerate(lines):
        k = ln.get("k") or "p"
        if k == "table":
            if not reuse:
                cur.insertBlock(_block_fmt("_skip"))
            else:
                cur.setBlockFormat(_block_fmt("_skip"))
            rows = ln.get("rows") or [[""]]
            n = max(1, *[len(r) for r in rows])
            tf = QTextTableFormat()
            tf.setBorder(1)
            tf.setBorderBrush(QBrush(QColor("#d4d4d8")))
            tf.setCellPadding(MEMO["CELL"])
            tf.setCellSpacing(0)
            tf.setBorderCollapse(True)
            tf.setTopMargin(MEMO["GAP"] + TEXT_MARGIN)
            cw = ln.get("cw") if len(ln.get("cw") or []) == n else [1 / n] * n
            tf.setColumnWidthConstraints([QTextLength(QTextLength.Type.PercentageLength, f * 100) for f in cw])
            tf.setProperty(KIND, "table")
            tf.setProperty(LV, 1 if ln.get("header") else 0)
            tbl = cur.insertTable(len(rows), n, tf)
            tf.setBottomMargin(MEMO["GAP"])
            tbl.setFormat(tf)
            for r, row in enumerate(rows):
                for c in range(n):
                    if ln.get("header") and r == 0:   # 머리 행 회색 바탕(메모 그리기와 같게)
                        cell = tbl.cellAt(r, c)
                        cfmt = cell.format()
                        cfmt.setBackground(QBrush(QColor("#f4f4f5")))
                        cell.setFormat(cfmt)
                    cc = tbl.cellAt(r, c).firstCursorPosition()
                    cf = _char_fmt("p", {"bold": True} if ln.get("header") and r == 0 else None)
                    cc.insertText(row[c] if c < len(row) else "", cf)
            cur.movePosition(QTextCursor.MoveOperation.End)
            cur.setBlockFormat(_block_fmt("_skip"))
            reuse, prev_k = True, k
            continue
        bf = _block_fmt(k, int(ln.get("lv") or 0), bool(ln.get("done")), first=i == 0,
                        join_prev=prev_k == k and k in ("code", "quote"))
        if reuse:
            cur.setBlockFormat(bf)
            reuse = False
        else:
            cur.insertBlock(bf)
        cur.setBlockCharFormat(_char_fmt(k))
        done = k == "todo" and bool(ln.get("done"))
        for p in _parts(ln.get("t") or "", None if k == "code" else ln.get("runs")):
            cur.insertText(p["text"], _char_fmt(k, p, done))
        prev_k = k
    doc.clearUndoRedoStacks()


def _hex(c: QColor) -> str:
    return "#" + format(c.rgba() & 0xFFFFFFFF, "08x")


def _block_line(b) -> dict:
    """문서 블록 → 메모 줄(꾸밈 = runs)."""
    bf = b.blockFormat()
    k = bf.property(KIND) or "p"
    text = b.text()
    if k == "hr" and text:
        k = "p"
    ln = {"k": k, "t": text}
    lv = int(bf.property(LV) or 0)
    if k in LISTY and lv:
        ln["lv"] = lv
    if k == "todo" and bf.property(DONE):
        ln["done"] = True
    if k in ("code", "hr") or not text:
        return ln
    K = MEMO_KIND.get(k, MEMO_KIND["p"])
    at = []
    it = b.begin()
    while not it.atEnd():
        fr = it.fragment()
        cf = fr.charFormat()
        derived = bool(cf.property(DERIVED))
        has_fg = cf.hasProperty(QTextFormat.Property.ForegroundBrush)
        color = None if derived or not has_fg else (cf.property(QTextFormat.Property.UserProperty + 8) or _hex(cf.foreground().color()))
        bold = cf.fontWeight() >= 600 and not K.get("bold")
        bg = (cf.property(QTextFormat.Property.UserProperty + 9) or _hex(cf.background().color())) if cf.hasProperty(QTextFormat.Property.BackgroundBrush) else None
        mono = bool(set(cf.fontFamilies() or []) & {"Consolas", "Cascadia Mono", "D2Coding"})
        deco = ("i" if cf.fontItalic() else "") + ("u" if cf.fontUnderline() else "") + ("s" if cf.fontStrikeOut() else "")
        at += [(color, bold, bg, mono, deco)] * len(fr.text())
        it += 1
    runs, i, n = [], 0, len(at)
    while i < n:
        j = i + 1
        while j < n and at[j] == at[i]:
            j += 1
        color, bold, bg, mono, deco = at[i]
        if deco:
            runs.append([i, j - i, color, bold, bg, mono, deco])
        elif mono:
            runs.append([i, j - i, color, bold, bg, True])
        elif color or bold or bg:
            runs.append([i, j - i, color, bold, *([bg] if bg else [])])
        i = j
    if runs:
        ln["runs"] = runs
    return ln


def doc_to_lines(doc: QTextDocument, old_lines=None) -> list:
    """편집 문서 → 메모 줄. 글·종류·꾸밈이 그대로인 줄은 원래 줄을 그대로 씀(웹만 아는 칸까지 안 잃게)."""
    out = []
    root = doc.rootFrame()
    it = root.begin()
    while not it.atEnd():
        fr, b = it.currentFrame(), it.currentBlock()
        if fr is not None:
            tbl = fr
            tf = tbl.format()
            rows = [[_cell_text(tbl, r, c) for c in range(tbl.columns())] for r in range(tbl.rows())]
            cw = [round(l.rawValue() / 100, 4) for l in tf.toTableFormat().columnWidthConstraints()] if tf.isTableFormat() else []
            L = {"k": "table", "t": "", "rows": rows, "header": bool(tf.property(LV)), "cw": cw if len(cw) == tbl.columns() else _table_widths(rows)}
            out.append(L)
        elif b.isValid():
            k = b.blockFormat().property(KIND)
            if not (k == "_skip" and not b.text()):
                out.append(_block_line(b))
        it += 1
    out = out or [{"k": "p", "t": ""}]
    pool = {}
    for ln in old_lines or []:
        pool.setdefault(_sig(ln), []).append(ln)
    return [copy.deepcopy(pool[_sig(ln)].pop(0)) if pool.get(_sig(ln)) else ln for ln in out]


def _cell_text(tbl, r, c) -> str:
    cell = tbl.cellAt(r, c)
    cur = cell.firstCursorPosition()
    cur.setPosition(cell.lastCursorPosition().position(), QTextCursor.MoveMode.KeepAnchor)
    return cur.selectedText().replace(" ", " ").strip()


def _norm_color(c):
    if c is None:
        return None
    q = _qcolor(c, "#00000000")
    return q.rgba()


def _sig(ln: dict):
    """줄 같음 판정 — 색은 숫자로(웹이 쓴 「#ff…」·배열 표기가 달라도 같은 색이면 같음)."""
    runs = tuple(tuple([r[0], r[1], _norm_color(r[2] if len(r) > 2 else None), bool(r[3]) if len(r) > 3 else False,
                        _norm_color(r[4] if len(r) > 4 else None), bool(r[5]) if len(r) > 5 else False, (r[6] if len(r) > 6 else "") or ""])
                 for r in ln.get("runs") or [])
    rows = tuple(tuple(r) for r in ln.get("rows") or [])
    return (ln.get("k"), ln.get("t") or "", int(ln.get("lv") or 0), bool(ln.get("done")), runs, rows, bool(ln.get("header")))


_PREFIX = [(re.compile(r"^###$"), "h3"), (re.compile(r"^##$"), "h2"), (re.compile(r"^#$"), "h1"), (re.compile(r"^[-*•]$"), "ul"),
           (re.compile(r"^\d+[.)]$"), "ol"), (re.compile(r"^\[ ?\]$"), "todo"), (re.compile(r"^\[[xX]\]$"), "todo_done"), (re.compile(r"^>$"), "quote")]


class _MemoTextEdit(QGraphicsTextItem):
    """메모 자리 편집 글 상자 — 메모(`core_web._MemoItem`)의 자식. 마치면(Esc·바깥 누르기) 메모 줄로 저장."""

    def __init__(self, memo):
        super().__init__(memo)
        self._memo, self._done = memo, False
        r = memo.rect()
        self.setPos(r.x() + MEMO["LPAD"] - TEXT_MARGIN, r.y() + MEMO["PAD"])
        self.setDefaultTextColor(INK)
        lines_to_doc(memo.raw.get("lines"), self.document(), max(20.0, r.width() - MEMO["LPAD"] - MEMO["PAD"]) + 2 * TEXT_MARGIN)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.document().contentsChanged.connect(self._grow)
        self.setZValue(1)

    # 메모 높이 = 글 높이(고치는 동안 늘고 줆 — 기록은 마칠 때 한 번)
    def _grow(self):
        need = self.boundingRect().height() + 2 * MEMO["PAD"] - TEXT_MARGIN * 0
        r = self._memo.rect()
        if abs(need - r.height()) > 0.5:
            self._memo.prepareGeometryChange()
            super(type(self._memo), self._memo).setRect(QRectF(r.x(), r.y(), r.width(), need))

    def start(self):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cur)

    # ---- 마치기 ----
    def commit(self):
        if self._done:
            return
        self._done = True
        memo = self._memo
        new = doc_to_lines(self.document(), memo.raw.get("lines"))
        memo._end_edit(self, new)

    def cancel(self):
        if self._done:
            return
        self._done = True
        self._memo._end_edit(self, None)

    def close(self):   # 옛 편집 칸과 같은 이름(시험·호출부) — 저장하고 닫음
        self.commit()

    def isVisible(self):
        return not self._done and super().isVisible()

    def toPlainText(self):
        return super().toPlainText()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if event.reason() != Qt.FocusReason.PopupFocusReason:
            self.commit()

    # ---- 블록 종류 ----
    def _set_kind(self, cur: QTextCursor, k: str, lv: int | None = None, done: bool = False):
        b = cur.block()
        old = b.blockFormat()
        lv = int(old.property(LV) or 0) if lv is None else lv
        first = b.blockNumber() == 0
        prev = b.previous()
        join = prev.isValid() and prev.blockFormat().property(KIND) == k and k in ("code", "quote")
        cur.setBlockFormat(_block_fmt(k, lv if k in LISTY else 0, done, first=first, join_prev=join))
        # 글자 크기·굵기를 새 종류로(사용자가 준 색·꾸밈은 지킴)
        c2 = QTextCursor(b)
        c2.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        base = _char_fmt(k, None, done and k == "todo")
        c2.setBlockCharFormat(base)
        if c2.hasSelection():
            m = QTextCharFormat()
            m.setFont(base.font(), QTextCharFormat.FontPropertiesInheritanceBehavior.FontPropertiesSpecifiedOnly)
            m.setFontFamilies(base.fontFamilies())
            m.setFontPointSize(base.fontPointSize())
            m.setFontWeight(base.fontWeight())
            c2.mergeCharFormat(m)
        self.update()

    def _kind(self, cur=None):
        cur = cur or self.textCursor()
        return cur.block().blockFormat().property(KIND) or "p"

    def keyPressEvent(self, e):
        cur = self.textCursor()
        k, key, mods = self._kind(cur), e.key(), e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key.Key_Escape:
            self.commit()
            return
        if ctrl and key in (Qt.Key.Key_B, Qt.Key.Key_I, Qt.Key.Key_U):   # 굵게·기울임·밑줄
            cf = cur.charFormat()
            m = QTextCharFormat()
            if key == Qt.Key.Key_B:
                m.setFontWeight(400 if cf.fontWeight() >= 600 else 700)
            elif key == Qt.Key.Key_I:
                m.setFontItalic(not cf.fontItalic())
            else:
                m.setFontUnderline(not cf.fontUnderline())
            cur.mergeCharFormat(m)
            self.setTextCursor(cur)
            return
        if key == Qt.Key.Key_Space and not ctrl and k == "p" and not cur.hasSelection():   # 줄 맨 앞 입력 규칙
            before = cur.block().text()[:cur.positionInBlock()]
            for rx, nk in _PREFIX:
                if rx.match(before) and cur.positionInBlock() == len(before):
                    c2 = QTextCursor(cur.block())
                    c2.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, len(before))
                    c2.removeSelectedText()
                    self._set_kind(cur, "todo" if nk == "todo_done" else nk, 0, done=nk == "todo_done")
                    return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not ctrl and not (mods & Qt.KeyboardModifier.ShiftModifier):
            text = cur.block().text()
            if k == "p" and text.strip() == "```":
                self._clear_block(cur)
                self._set_kind(cur, "code")
                return
            if k == "p" and re.fullmatch(r"([-*_])\1{2,}", text.strip()):
                self._clear_block(cur)
                self._set_kind(cur, "hr")
                cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                cur.insertBlock(_block_fmt("p"), _char_fmt("p"))
                self.setTextCursor(cur)
                return
            if k in LISTY | {"quote"} and not text:   # 빈 목록 줄에서 Enter = 목록 끝
                self._set_kind(cur, "p")
                return
            if k == "code" and not text and cur.block().previous().blockFormat().property(KIND) == "code":
                self._set_kind(cur, "p")
                return
            nk = k if k in LISTY | {"code", "quote"} else "p"
            lv = int(cur.block().blockFormat().property(LV) or 0)
            cur.insertBlock(_block_fmt(nk, lv if nk in LISTY else 0, join_prev=nk in ("code", "quote")), _char_fmt(nk))
            self.setTextCursor(cur)
            return
        if key == Qt.Key.Key_Backspace and cur.positionInBlock() == 0 and not cur.hasSelection() and k not in ("p", "_skip"):
            self._set_kind(cur, "p")   # 줄 맨 앞 지우기 = 종류만 풂(노션·TipTap)
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and k in LISTY:
            lv = int(cur.block().blockFormat().property(LV) or 0)
            lv = max(0, lv - 1) if key == Qt.Key.Key_Backtab or mods & Qt.KeyboardModifier.ShiftModifier else min(5, lv + 1)
            self._set_kind(cur, k, lv, bool(cur.block().blockFormat().property(DONE)))
            return
        super().keyPressEvent(e)
        self.update()

    def sceneEvent(self, e):
        # Tab은 뷰·창의 포커스 이동이 먼저 가져가므로 여기서 받음
        from PyQt6.QtCore import QEvent
        if e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.keyPressEvent(e)
            return True
        return super().sceneEvent(e)

    def _clear_block(self, cur):
        c2 = QTextCursor(cur.block())
        c2.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        c2.removeSelectedText()

    # ---- 할 일 상자 누르기 ----
    def _box_at(self, pos: QPointF):
        doc, lay = self.document(), self.document().documentLayout()
        b = doc.begin()
        while b.isValid():
            bf = b.blockFormat()
            if bf.property(KIND) == "todo":
                r = lay.blockBoundingRect(b)
                px = MEMO_KIND["todo"]["pt"] * PT
                lh = BOARD_M["lineSpacing"] * px
                s = px * 0.9
                box = QRectF(TEXT_MARGIN + bf.leftMargin() - MEMO["INDENT"] + 2 - 4, r.y() + lh / 2 - s / 2 - 4, s + 8, s + 8)   # 그린 상자 둘레 4px
                if box.contains(pos):
                    return b
            b = b.next()
        return None

    def mousePressEvent(self, e):
        b = self._box_at(e.pos())
        if b is not None:
            cur = QTextCursor(b)
            done = not bool(b.blockFormat().property(DONE))
            self._set_kind(cur, "todo", None, done)
            e.accept()
            return
        super().mousePressEvent(e)

    # ---- 그리기: 코드 바탕·인용 막대·글머리·번호·할 일 상자·구분선 (글은 Qt가 그림) ----
    def paint(self, p, option, widget=None):
        doc, lay = self.document(), self.document().documentLayout()
        blocks, b = [], doc.begin()
        while b.isValid():
            blocks.append(b)
            b = b.next()
        lines = [{"k": x.blockFormat().property(KIND) or "p", "lv": int(x.blockFormat().property(LV) or 0)} for x in blocks]
        nums = ol_numbers(lines)
        w = self.document().textWidth()
        for i, b in enumerate(blocks):
            bf = b.blockFormat()
            k = lines[i]["k"]
            r = lay.blockBoundingRect(b)   # y = 글 첫 줄 위(위 여백은 이미 빠짐)
            top, h = r.y(), b.layout().boundingRect().height()
            px = MEMO_KIND.get(k, MEMO_KIND["p"])["pt"] * PT
            lh = b.layout().lineAt(0).height() if b.layout().lineCount() else BOARD_M["lineSpacing"] * px
            if k == "code":
                p.fillRect(QRectF(TEXT_MARGIN - 4, top - (0 if i and lines[i - 1]["k"] == "code" else TEXT_MARGIN), w - TEXT_MARGIN + 4,
                                  h + (0 if i and lines[i - 1]["k"] == "code" else TEXT_MARGIN) + (0 if i + 1 < len(lines) and lines[i + 1]["k"] == "code" else TEXT_MARGIN)), CODE_BAND)
            elif k == "quote":
                p.fillRect(QRectF(TEXT_MARGIN, top, 3, h), QColor("#d4d4d8"))
            elif k == "hr":
                p.setPen(QPen(QColor("#d4d4d8"), 1))
                p.drawLine(QPointF(TEXT_MARGIN, top + h / 2), QPointF(w - TEXT_MARGIN, top + h / 2))
            elif k in ("ul", "ol"):
                f = _base_font("p")
                p.setFont(f)
                p.setPen(QPen(INK))
                mk = "•◦▪"[lines[i]["lv"] % 3] if k == "ul" else f"{nums.get(i)}."
                x = TEXT_MARGIN + bf.leftMargin() - 6
                p.drawText(QRectF(x - 60, top, 60, lh), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), mk)
            elif k == "todo":
                s = px * 0.9
                done = bool(bf.property(DONE))
                box = QRectF(TEXT_MARGIN + bf.leftMargin() - MEMO["INDENT"] + 2, top + lh / 2 - s / 2, s, s)
                p.setPen(QPen(QColor("#2f80ed" if done else "#a1a1aa"), 1.2))
                p.setBrush(QColor("#2f80ed" if done else "#ffffff"))
                p.drawRoundedRect(box, s * 0.18, s * 0.18)
                if done:
                    chk = QPainterPath(QPointF(box.x() + s * 0.22, box.y() + s * 0.52))
                    chk.lineTo(box.x() + s * 0.43, box.y() + s * 0.72)
                    chk.lineTo(box.x() + s * 0.8, box.y() + s * 0.3)
                    pen = QPen(QColor("#ffffff"), 1.6)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawPath(chk)
                    p.setPen(QPen(QColor(MUTED), 1))
                    lw = QFontMetricsF(_base_font("todo")).horizontalAdvance(b.text())
                    x0 = TEXT_MARGIN + bf.leftMargin()
                    p.drawLine(QPointF(x0, top + lh * 0.55), QPointF(x0 + min(lw, w - x0), top + lh * 0.55))
        from PyQt6.QtWidgets import QStyle, QStyleOptionGraphicsItem
        opt = QStyleOptionGraphicsItem(option)
        opt.state &= ~(QStyle.StateFlag.State_HasFocus | QStyle.StateFlag.State_Selected)   # Qt 기본 점선 테두리 끔(메모 테두리가 곧 편집 자리)
        super().paint(p, opt, widget)
