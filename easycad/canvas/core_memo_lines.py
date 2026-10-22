"""메모 줄 손잡이(⠿)·줄 고르기·줄 끌어 옮기기 — 웹 Editor.jsx 「메모 2차」를 옮김(2026-10-22, 데스크톱 = 웹 + 추가 기능).

- 마우스를 메모 줄에 올리면 왼쪽 여백에 ⠿. 누르기 = 그 줄 고르기 + 메뉴(전환·색·링크·복제·삭제), 끌기 = 줄 순서(다른 메모로도),
  메모 밖에 놓기 = 새 메모(칠판으로 꺼내기, 비게 된 메모는 지움), Alt 끌기 = 복사.
- 고른 줄: Shift+클릭 = 이어서, Ctrl·Alt+Shift 클릭 = 따로따로 · Esc 풀기 · Del 지우기 · Ctrl+D 복제 · Ctrl+/ 전환 · Ctrl+Enter 할 일 ·
  Enter 고치기(그 줄 끝에 커서) · ↑↓ 옮겨 고르기(Shift = 넓히기). 메모 고치는 중 Esc = 마치고 커서 줄 고르기.
- 줄 계산은 `core_memo`(line_unit·move_lines·pick_lines·convert_line·recolor_line·toggle_todos), 화면 크기(손잡이 16×22px)는 확대와 상관없이 같게.
"""
import copy

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPen
from PyQt6.QtWidgets import QMenu

from easycad.canvas.core_memo import (LINE_COLORS, MEMO, TEXT_MARGIN, convert_line, line_unit, memo_layout, move_lines, pick_lines,
                                      recolor_line, sel_idx, sel_units, toggle_todos, url_spans)

BLUE = QColor("#2f80ed")
SEL = QColor(137, 180, 250, 71)   # rgba(137,180,250,.28)
HW, HH = 16, 22                   # 손잡이 화면 크기(px)


def _zoom(view, item) -> float:
    return abs(view.transform().m11()) * (item.scale() or 1.0)


def _rows(item):
    return memo_layout(item.raw, item.rect().width())["rows"]


def _memos_at(view, scene_pos, margin=0.0, pad=0.0):
    """scene_pos의 메모들(맨 위부터) — margin = 왼쪽 여유, pad = 위·아래·오른쪽 여유(화면 px)."""
    out = []
    vz = abs(view.transform().m11()) or 1.0
    e = (margin + pad) / vz   # 마우스 둘레만 찾음(장면 색인) — 큰 도면에서 마우스를 움직일 때마다 모든 도형을 훑지 않게
    for it in view.scene().items(QRectF(scene_pos.x() - e, scene_pos.y() - e, 2 * e, 2 * e)):
        if not hasattr(it, "line_press") or it.scene() is None or getattr(it, "_locked", False):
            continue
        k = _zoom(view, it)
        q, r = it.mapFromScene(scene_pos), it.rect()
        if r.left() - margin / k <= q.x() <= r.right() + pad / k and r.top() - pad / k <= q.y() <= r.bottom() + pad / k:
            out.append(it)
    return out


def memo_hover(view, scene_pos):
    """마우스 이동(누르지 않음) — 맨 위 메모 줄에 손잡이, 다른 메모는 끔.
    돌려줌: "handle"(손잡이 위 — 손 커서) · "text"(고치는 중인 메모 안 — 글 커서) · None."""
    hits = _memos_at(view, scene_pos, 28, 0)
    top = hits[0] if hits else None
    old = getattr(view, "_hov_memo", None)
    if old is not None and old is not top and old.scene() is not None:
        old.set_hover(None)
    view._hov_memo = top
    if top is None:
        return None
    q = top.mapFromScene(scene_pos)
    if getattr(top, "_editor", None) is not None:   # 고치는 중에도 줄 손잡이(웹 memoedit ⠿) — 자리는 편집기 줄에서
        ed = top._editor
        hit = ed.line_at_y(ed.mapFromParent(q).y()) if top.rect().adjusted(-28 / _zoom(view, top), 0, 0, 0).contains(q) else None
        hov = (hit[0], ed.mapToParent(QPointF(0, hit[1])).y()) if hit else None
        if hov != top._edit_hov:
            top._edit_hov = hov
            top.update()
        if hov and top.edit_handle_rect(_zoom(view, top)).contains(q):
            return "handle"
        return "text" if top.rect().contains(q) else None
    top.set_hover(q)
    return "handle" if top.handle_hit(q, _zoom(view, top)) is not None else None


class _MemoLinesMixin:
    """`core_web._MemoItem`이 물려받음 — 줄 고르기 상태·손잡이·끌기·글쇠·메뉴."""

    _line_sel = None   # {"s", "e", "more"?} — 웹 lineSel
    _hov = None        # 손잡이를 띄울 줄 덩어리 (s, e)
    _drop = None       # 끌어 놓을 자리 표시 y(아이템 좌표)
    _edit_hov = None   # 고치는 중 손잡이 (줄 번호, 가운데 y — 아이템 좌표)

    def edit_handle_rect(self, k: float) -> QRectF:
        """고치는 중 ⠿ 자리 — 가로는 평소 손잡이와 같고, 세로는 편집기 줄 가운데."""
        w, h, R = HW / k, HH / k, self.rect()
        x = R.left() + MEMO["LPAD"] - w - 3 / k if w + 5 / k <= MEMO["LPAD"] else R.left() - w - 4 / k
        return QRectF(x, self._edit_hov[1] - h / 2, w, h)

    def _paint_handle_at(self, p, b: QRectF, k: float):
        p.save()
        p.translate(b.topLeft())
        p.scale(1 / k, 1 / k)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(127, 127, 127, 41))
        p.drawRoundedRect(QRectF(0, 0, HW, HH), 4, 4)
        f = QFont()
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#8a8f98"))
        p.drawText(QRectF(0, 0, HW, HH), int(Qt.AlignmentFlag.AlignCenter), "⠿")
        p.restore()

    def paint_edit_handle(self, p):
        """고치는 중 ⠿(paint_card가 글 대신 부름)."""
        if self._edit_hov is not None:
            k = abs(p.worldTransform().m11()) or 1.0
            self._paint_handle_at(p, self.edit_handle_rect(k), k)

    def _view(self):
        sc = self.scene()
        return sc.views()[0] if sc is not None and sc.views() else None

    # ---- 자리 ----
    def row_at(self, q: QPointF):
        """아이템 좌표 q가 든 줄 덩어리 [s, e)(펼치기·접기 줄은 줄이 아님)."""
        rows = [r for r in _rows(self) if not r["ln"].get("more")]
        if not rows:
            return None
        r, y0 = rows[0], self.rect().top()
        for row in rows:
            if q.y() >= y0 + row["y"]:
                r = row
        return line_unit(self.raw.get("lines") or [], r["i"])

    def handle_rect(self, s: int, k: float) -> QRectF:
        """⠿ 자리(아이템 좌표) — 메모 왼쪽 여백 안(글 바로 옆), 화면에서 늘 같은 크기. 여백보다 커지면 바깥으로(웹 memoHandleRect)."""
        rows = _rows(self)
        r = next((x for x in rows if x["i"] == s), rows[0] if rows else {"cy": MEMO["PAD"]})
        w, h, R = HW / k, HH / k, self.rect()
        x = R.left() + MEMO["LPAD"] - w - 3 / k if w + 5 / k <= MEMO["LPAD"] else R.left() - w - 4 / k
        return QRectF(x, R.top() + r["cy"] - h / 2, w, h)

    def handle_hit(self, q: QPointF, k: float):
        if self._hov is None:
            return None
        return self._hov if self.handle_rect(self._hov[0], k).contains(q) else None

    # ---- 마우스 올림 = 손잡이(뷰가 마우스 이동마다 `memo_hover`로 알려 줌 — 이 앱은 Qt 올림 이벤트 대신 뷰가 직접 계산) ----
    def set_hover(self, q):
        hov = None
        if q is not None and getattr(self, "_editor", None) is None and not getattr(self, "_locked", False):
            hov = tuple(self.row_at(q) or ()) or None
        if hov != self._hov:
            self._hov = hov
            self.update()

    # ---- 그리기(고른 줄·손잡이·놓을 자리) — paint_card 끝에서 ----
    def paint_lines_ui(self, p, r: QRectF):
        rows = _rows(self)
        if self._line_sel:
            by_i = {x["i"]: x for x in rows}
            for s0, e0 in sel_units(self._line_sel):
                a = by_i.get(s0)
                if a is None:
                    continue
                bot = by_i[e0]["y"] - MEMO["GAP"] / 2 if e0 in by_i else r.height() - MEMO["PAD"] + TEXT_MARGIN
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(SEL)
                p.drawRoundedRect(QRectF(r.left() + MEMO["LPAD"] - 4, r.top() + a["y"], r.width() - MEMO["LPAD"] - MEMO["PAD"] + 8, bot - a["y"]), 4, 4)
        k = abs(p.worldTransform().m11()) or 1.0
        if self._drop is not None:
            pen = QPen(BLUE, 3 / k)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(r.left() + MEMO["LPAD"], self._drop), QPointF(r.right() - MEMO["PAD"], self._drop))
        if self._hov is not None and not getattr(self, "_locked", False):
            self._paint_handle_at(p, self.handle_rect(self._hov[0], k), k)

    # ---- 고르기 ----
    def set_line_sel(self, ls):
        self._line_sel = ls
        v = self._view()
        if v is not None:
            if ls:
                old = getattr(v, "_line_memo", None)
                if old is not None and old is not self:
                    old.set_line_sel(None)
                v._line_memo = self
                self.scene().clearSelection()
                self.setSelected(True)
            elif getattr(v, "_line_memo", None) is self:
                v._line_memo = None
        self.update()

    def line_press(self, view, q: QPointF, mods, scene_pos) -> bool:
        """누르기 — 손잡이(또는 고른 채 Shift·Ctrl+줄)면 처리하고 True(웹 onDown 「⠿」)."""
        k = _zoom(view, self)
        ed = getattr(self, "_editor", None)
        if ed is not None:   # 고치는 중 ⠿ 누르기 = 고치기를 마치고 그 줄 끌기·(놓으면) 메뉴로(웹 grab)
            if self._edit_hov is None or not self.edit_handle_rect(k).contains(q):
                return False
            i = self._edit_hov[0]
            self._edit_hov = None
            ed.commit()
            lines = self.raw.get("lines") or []
            if not (0 <= i < len(lines)):
                return True
            s, e = line_unit(lines, i)
            view._mline = {"memo": self, "units": [[s, e]], "copy": False, "start": QPointF(scene_pos), "moved": False}
            return True
        ls = self._line_sel
        mh = self.handle_hit(q, k)
        if mh is None and ls and mods & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
            mh = tuple(self.row_at(q) or ()) or None
        if mh is None:
            return False
        s, e = mh
        ctrl, shift, alt = (bool(mods & m) for m in (Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.AltModifier))
        toggle, rng = (ctrl and not shift) or (alt and shift), shift and not alt
        if toggle:   # 따로따로 — 이미 고른 덩어리면 뺌
            if not ls:
                self.set_line_sel({"s": s, "e": e})
                return True
            us = sel_units(ls)
            has = next((j for j, (a, b) in enumerate(us) if s >= a and e <= b), -1)
            if has < 0:
                self.set_line_sel({"s": s, "e": e, "more": us})
                return True
            left = [u for j, u in enumerate(us) if j != has]
            if not left:
                self.set_line_sel(None)
                return True
            a0, *rest = list(reversed(left))
            self.set_line_sel({"s": a0[0], "e": a0[1], **({"more": rest} if rest else {})})
            return True
        if rng:      # 이어서 — 고른 덩어리부터 누른 덩어리까지
            if ls:
                s1, e1 = min(ls["s"], s), max(ls["e"], e)
                more = [u for u in ls.get("more") or [] if u[1] <= s1 or u[0] >= e1]
                self.set_line_sel({"s": s1, "e": e1, **({"more": more} if more else {})})
            else:
                self.set_line_sel({"s": s, "e": e})
            return True
        in_sel = ls and any(s >= a and e <= b for a, b in sel_units(ls))
        view._mline = {"memo": self, "units": sel_units(ls) if in_sel else [[s, e]], "copy": alt, "start": QPointF(scene_pos), "moved": False}
        return True

    # ---- 끌기 ----
    def _drop_at(self, view, scene_pos):
        """끌어 놓을 자리 — 메모 위(손잡이 띠·가장자리 여유 포함)면 (메모, 줄 번호, y), 확실히 벗어나면 None(새 메모 — 웹 memoDropAt)."""
        hits = _memos_at(view, scene_pos, 48, 20)
        if not hits:
            return None
        it = hits[0]
        q, rows, R = it.mapFromScene(scene_pos), _rows(it), it.rect()
        rows = [x for x in rows if not x["ln"].get("more")]
        for j, r in enumerate(rows):
            if r.get("join_prev"):
                continue
            bot = rows[j + 1]["y"] if j + 1 < len(rows) else R.height() - MEMO["PAD"]
            if q.y() < R.top() + (r["y"] + bot) / 2:
                return it, r["i"], R.top() + r["y"] - MEMO["GAP"] / 2
        return it, len(it.raw.get("lines") or []), R.bottom() - MEMO["PAD"] + 2

    def line_drag_move(self, view, scene_pos):
        s = view._mline
        if not s["moved"] and (QPointF(scene_pos) - s["start"]).manhattanLength() * abs(view.transform().m11()) < 4:
            return
        s["moved"] = True
        view.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        tg = self._drop_at(view, scene_pos)
        marked = s.setdefault("marked", set())   # 놓을 자리 선을 그린 메모들(지울 때 다시 찾지 않게)
        for it in list(marked) + ([tg[0]] if tg else []):
            want = tg[2] if tg and tg[0] is it else None
            if it._drop != want:
                it._drop = want
                it.update()
            (marked.add if want is not None else marked.discard)(it)
        view._mline_out = None if tg else QPointF(scene_pos)
        view.viewport().update()

    def line_drag_end(self, view, scene_pos, global_pos):
        s, view._mline = view._mline, None
        view._mline_out = None
        for it in s.get("marked") or ():
            it._drop = None
            it.update()
        view.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        units = s["units"]
        if not s["moved"]:   # 제자리 = 그 줄 고르기 + 메뉴
            a0, *rest = list(reversed(units))
            self.set_line_sel({"s": a0[0], "e": a0[1], **({"more": rest} if rest else {})})
            self.line_menu(units).popup(global_pos)
            return
        self.set_line_sel(None)
        self._line_drop(view, units, s["copy"], scene_pos)

    def _line_drop(self, view, units, copy_, scene_pos):
        """놓기 — 같은 메모 = 순서, 다른 메모 = 옮겨 넣기, 밖 = 새 메모(웹 memoLineDrop). 되돌리기 한 칸."""
        host = getattr(view, "_owner", None)
        lines = self.raw.get("lines") or []
        idx = [i for a, b in sorted(units) for i in range(a, b)]
        tg = self._drop_at(view, scene_pos)
        if tg and tg[0] is self:
            self.set_lines(_nonempty(move_lines(lines, idx, tg[1], copy_)))
            return
        on = set(idx)
        unit = pick_lines(lines, idx)
        rest = lines if copy_ else [l for i, l in enumerate(lines) if i not in on]
        gone = not copy_ and all(not (l.get("t") or "").strip() for l in rest)   # 끌어내다 비게 된 메모는 지움(직접 비운 메모는 남김)
        ops = []
        if gone:
            self.scene().removeItem(self)
            ops.append(("remove", self))
        elif not copy_:
            b0 = self.capture_state()
            self._put_lines(rest)
            ops.append(("mut", self, "state", b0, self.capture_state()))
        if tg:
            dst, to = tg[0], tg[1]
            b1 = dst.capture_state()
            dl = dst.raw.get("lines") or []
            dst._put_lines(dl[:to] + unit + dl[to:])
            ops.append(("mut", dst, "state", b1, dst.capture_state()))
            sel = dst
        else:
            from easycad.fileio.document import dict_to_item
            sc = self.scale() or 1.0
            nw = dict_to_item({"type": "memo", "rect": [0, 0, self.rect().width(), 40], "fill": self.raw.get("fill") or "#ffffffff", "lines": unit,
                               "pos": [0, 0], "scale": sc, "rotation": 0, "z": 0, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None})
            nw._fit_height(nw.raw)
            nw.setPos(scene_pos.x() - 24 * sc, scene_pos.y() - 16 * sc)
            nw.setZValue(max([x.zValue() for x in view.scene().items()] + [0]) + 1)
            view.scene().addItem(nw)
            ops.append(("create", nw))
            sel = nw
        view.scene().clearSelection()
        sel.setSelected(True)
        if host is not None and hasattr(host, "_push_entry"):
            host._push_entry(ops)

    def _put_lines(self, lines):
        """줄만 바꿈(되돌리기는 부른 쪽이 묶어서 — 여러 메모를 한 칸에)."""
        self._web_raw["lines"] = _nonempty(lines)
        self._fit_height(self._web_raw)
        self.update()

    # ---- 고른 줄 글쇠 ----
    def line_key(self, view, e) -> bool:
        ls = self._line_sel
        if not ls:
            return False
        lines = self.raw.get("lines") or []
        key, mods = e.key(), e.modifiers()
        ctrl, shift = bool(mods & Qt.KeyboardModifier.ControlModifier), bool(mods & Qt.KeyboardModifier.ShiftModifier)
        idx = sel_idx(ls)
        if key == Qt.Key.Key_Escape:
            self.set_line_sel(None)
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            on = set(idx)
            self.set_lines(_nonempty([l for i, l in enumerate(lines) if i not in on]))
            self.set_line_sel(None)
        elif ctrl and key == Qt.Key.Key_D:
            self._dup(idx)
        elif ctrl and key == Qt.Key.Key_Slash:
            us = sel_units(ls)
            b = self.handle_rect(us[0][0], _zoom(view, self))
            self.line_menu(us, kinds_only=True).popup(view.viewport().mapToGlobal(view.mapFromScene(self.mapToScene(b.bottomRight()))))
        elif ctrl and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            nx = toggle_todos(lines, idx)
            if nx:
                self.set_lines(nx)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2):
            first = sel_units(ls)[0][0]
            self.set_line_sel(None)
            self.web_double_click(view, self.sceneBoundingRect().center(), caret=first)
        elif key == Qt.Key.Key_Down:
            if ls["e"] < len(lines):
                ne = line_unit(lines, ls["e"])[1]
                self.set_line_sel({**ls, "e": ne} if shift else {"s": ls["e"], "e": ne})
        elif key == Qt.Key.Key_Up:
            if ls["s"] > 0:
                s0 = line_unit(lines, ls["s"] - 1)[0]
                self.set_line_sel({**ls, "s": s0} if shift else {"s": s0, "e": line_unit(lines, s0)[1]})
        else:
            return False
        return True

    def to_board_table(self, i):
        """메모 표 줄 → 칠판 표(메모 오른쪽 옆, 웹 「칠판 표로 바꾸기」) — 메모엔 그 줄을 뺌, 되돌리기 한 칸, 새 표를 고름."""
        from easycad.canvas.core_shapes import _TableItem
        lines = self.raw.get("lines") or []
        ln = lines[i] if 0 <= i < len(lines) else {}
        rows = [list(r) for r in ln.get("rows") or []]
        if ln.get("k") != "table" or not rows:
            return None
        n = max(len(r) for r in rows)
        cells = [[str(r[c]) if c < len(r) else "" for c in range(n)] for r in rows]
        R = self.rect()
        t = _TableItem(len(rows), n, QRectF(0.0, 0.0, max(120.0, R.width() - MEMO["LPAD"] - MEMO["PAD"]), 28.0 * len(rows)),
                       cells, bool(ln.get("header")), ln.get("cw") if len(ln.get("cw") or []) == n else None)
        t.setFlags(t.GraphicsItemFlag.ItemIsMovable | t.GraphicsItemFlag.ItemIsSelectable)
        t.setScale(self.scale() or 1.0)
        t.setPos(self.mapToScene(QPointF(R.right() + 24, R.top())))
        sc = self.scene()
        t.setZValue(max([x.zValue() for x in sc.items()] + [0]) + 1)
        b0 = self.capture_state()
        self._put_lines([l for j, l in enumerate(lines) if j != i])
        sc.addItem(t)
        self.set_line_sel(None)
        sc.clearSelection()
        t.setSelected(True)
        host = getattr(self._view(), "_owner", None)
        if host is not None and hasattr(host, "_push_entry"):
            host._push_entry([("mut", self, "state", b0, self.capture_state()), ("create", t)])
        return t

    def _dup(self, idx):
        lines = self.raw.get("lines") or []
        last = idx[-1] + 1
        self.set_lines(lines[:last] + [copy.deepcopy(lines[i]) for i in idx] + lines[last:])
        self.set_line_sel({"s": last, "e": last + len(idx)})

    # ---- 메뉴(웹 lineMenuEntries) ----
    def line_menu(self, units, kinds_only=False) -> QMenu:
        lines = self.raw.get("lines") or []
        idx = [i for a, b in sorted(units) for i in range(a, b)]
        on = set(idx)
        cur = lines[idx[0]] if idx and idx[0] < len(lines) else {"k": "p"}
        v = self._view()
        menu = QMenu(v.viewport() if v is not None else None)

        def each(f, label):
            def run():
                self.set_lines([f(l) if i in on else l for i, l in enumerate(self.raw.get("lines") or [])])
            return run

        from easycad.canvas.core_memo_edit import LINE_KINDS
        kinds = menu if kinds_only else menu.addMenu("전환\tCtrl+/")
        for k, name in LINE_KINDS:
            kinds.addAction(("✓ " if cur.get("k") == k else "") + name, each(lambda l, k=k: convert_line(l, k), "줄 전환"))
        if kinds_only:
            return menu
        col = menu.addMenu("색")
        for n, c, _b in LINE_COLORS:
            col.addAction(f"{n} 텍스트", each(lambda l, c=c: recolor_line(l, color=c), "줄 색"))   # 웹과 같은 값 그대로(「#787774」)
        col.addSeparator()
        for n, _c, b in LINE_COLORS:
            col.addAction(f"{n} 배경", each(lambda l, b=b: recolor_line(l, bg=b), "줄 배경"))
        if any(url_spans(lines[i].get("t") or "") for i in idx if i < len(lines)):   # 링크 끄기/켜기(고칠 때 자꾸 열려 불편할 때)
            on2 = any(url_spans(lines[i].get("t") or "") and not lines[i].get("nolink") for i in idx if i < len(lines))
            menu.addAction("링크 끄기" if on2 else "링크 켜기",
                           each(lambda l: {**l, "nolink": True} if on2 else {kk: vv for kk, vv in l.items() if kk != "nolink"}, "링크"))
        if len(idx) == 1 and cur.get("k") == "table":   # 칸 꾸밈·합치기처럼 메모 표 줄이 못 하는 것(웹 2026-10-21)
            menu.addAction("칠판 표로 바꾸기", lambda: self.to_board_table(idx[0]))
        menu.addSeparator()
        menu.addAction("복제\tCtrl+D", lambda: self._dup(idx))
        menu.addAction("삭제\tDel", lambda: (self.set_lines(_nonempty([l for i, l in enumerate(self.raw.get("lines") or []) if i not in on])), self.set_line_sel(None)))
        return menu


def _nonempty(lines):
    return lines if lines else [{"k": "p", "t": ""}]
