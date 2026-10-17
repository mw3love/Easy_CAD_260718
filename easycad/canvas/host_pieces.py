"""CanvasWindow 믹스인 — 보드 옆 펼친 조각 · 「보드로 정리」(§8 항목59 ②, 2026-10-17 심층 인터뷰).

사용자 구상: "칠판이 무한이면 네모일 필요 없다 — 다 펼치고 골라 재정렬, 네모는 마지막". 정한 모양:
- 첫 모습 = 한 장 보드(지금 그대로) + 보드 오른쪽 무한 캔버스에 조각. 처음 쓰는 사람은 한 장을 바로, 숙련자는 조각으로.
- 조각 = AI 블록 후보(설계서 `more`, 보드와 같은 블록 형식) + 원문 그림(앱이 PDF에서 직접 — AI 호출 없음).
- 조각 하나 = 얇은 테두리 틀 + 블록 내용, 한 묶음(`_group_id`)이라 하나를 집으면 통째로 움직인다. 틀에 블록 설계서(`_pb_piece`, .ecad 저장).
- 「보드로 정리」 = 고른 조각들의 블록으로 새 보드(AI 없이, 앱의 배치 엔진 그대로) — 원래 보드 제목·무리 색을 물려받아 오른쪽에.
"""
from __future__ import annotations

import json
import uuid

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor

from easycad.canvas.annotator_core import BOARD_ASPECT, _BoardItem
from easycad.canvas.host_board import _outline_rect


class _PiecesMixin:
    _PC_W = 620.0          # 조각 폭
    _PC_GAP = 36.0         # 조각 사이
    _PC_COLS = 2           # 조각 기둥 수
    _PC_PAD = 18.0         # 틀 안쪽 여백
    _PC_MAX_FIGS = 6       # 원문 그림 조각 상한
    _PC_PAPER = "#f7f5ef"  # 조각 틀 바탕(종이색)

    # ---- 펼치기 ---------------------------------------------------------------------------------

    def _pdf_figure_pages(self, pdf_path, skip=()) -> list:
        """그림이 있는 쪽 번호(쪽 넓이의 4% 넘는 그림, 큰 것부터) — `skip` 쪽은 뺀다(보드에 이미 쓴 그림)."""
        try:
            import fitz
            out = []
            with fitz.open(pdf_path) as doc:
                for i, page in enumerate(doc):
                    area = page.rect.width * page.rect.height
                    big = max((fitz.Rect(b["bbox"]).width * fitz.Rect(b["bbox"]).height for b in page.get_image_info()), default=0.0)
                    if big > area * 0.04 and (i + 1) not in skip:
                        out.append((big, i + 1))
            return [p for _a, p in sorted(out, reverse=True)][: self._PC_MAX_FIGS]
        except Exception:   # noqa: BLE001 — 그림을 못 읽으면 그림 조각만 없다
            return []

    def _piece_blocks(self, spec) -> list:
        """펼칠 조각 블록 목록 — AI 후보(`more`) + 원문 그림(보드에 쓴 쪽은 빼고)."""
        out = [dict(b) for b in spec.get("more") or []]
        used = {b.get("page") for b in spec.get("blocks") or [] if b.get("type") == "figure"}
        if spec.get("_pdf") and not spec.get("_sources"):
            for p in self._pdf_figure_pages(spec["_pdf"], skip=used):
                out.append({"type": "figure", "title": f"원문 그림 p.{p}", "pages": f"p.{p}", "page": p, "caption": "", "size": "normal",
                            "_source": "pdf"})
        return out

    def _pieces_place(self, spec, near_rect: QRectF, push=True) -> list:
        """조각들을 `near_rect`(보드 묶음) 오른쪽에 두 기둥으로 펼친다(벽돌 쌓기). 반환: 넣은 아이템(되돌리기 한 칸)."""
        blocks = self._piece_blocks(spec)
        if not blocks:
            return []
        added: list = []
        x0 = near_rect.right() + 160.0
        y0 = near_rect.top()
        self._pb_part_cur = None
        head, hh = self._pb_text(added, f"조각 {len(blocks)}개 — 골라서 「보드로 정리」", x0, y0, self._PC_W * 2, 13,
                                 self._PB_MUTED, bold=True)   # 흐린 회청 — 밝은·어두운 캔버스 둘 다 읽힘
        tops = [y0 + hh + 16.0] * self._PC_COLS
        for blk in blocks:
            c = min(range(self._PC_COLS), key=lambda k: tops[k])
            x, y = x0 + c * (self._PC_W + self._PC_GAP), tops[c]
            items, h = self._piece_make(spec, blk, x, y)
            added += items
            tops[c] = y + h + self._PC_GAP
        self._pb_part_cur = None
        if push:
            self.push_undo_add_many(added)
        return added

    def _piece_make(self, spec, blk, x, y):
        """조각 하나(종이색 틀 + 블록 내용, 한 묶음)를 (x, y) 왼쪽 위에 — 반환 (아이템들, 높이). 되돌리기는 부르는 쪽이."""
        added: list = []
        self._pb_part_cur = "piece"
        h, _ns, _na = self._bb_block(added, spec, dict(blk, hero=False), x + self._PC_PAD, y + self._PC_PAD,
                                     self._PC_W - 2 * self._PC_PAD)
        # 종이색 틀(포스트잇) — 조각은 보드 밖 캔버스 위라 어두운 테마에서 검정 글이 안 보였다(실제 창). 흰색에 가까운
        # 무채색은 인쇄 때 흰→검정 바꾸기에 걸리므로 살짝 미색.
        frame = self._pb_card_under(added, 0, x, y, self._PC_W, h + 2 * self._PC_PAD, fill=self._PC_PAPER, edge=self._PB_EDGE)
        piece = {k: v for k, v in blk.items() if k not in ("row", "span", "_i", "hero")}
        frame._pb_piece = json.dumps(piece, ensure_ascii=False)
        gid = uuid.uuid4().hex[:8]
        for it in added:
            it._group_id = gid
            it._pb_part = None   # 조각은 보드의 설계서 자리가 아니다
        self._pb_part_cur = None
        return added, h + 2 * self._PC_PAD

    # ---- 고르기 · 「보드로 정리」 -------------------------------------------------------------------

    def _pieces_selected(self) -> list:
        """고른 조각들의 블록 설계서(위에서 아래·왼쪽에서 오른쪽 차례, 묶음마다 하나)."""
        frames = {}
        for it in self._scene.selectedItems():
            if it.parentItem() is None and getattr(it, "_pb_piece", None):
                frames[id(it)] = it
        order = sorted(frames.values(), key=lambda f: (round(f.sceneBoundingRect().top() / 40.0), f.sceneBoundingRect().left()))
        out = []
        for f in order:
            try:
                out.append(json.loads(f._pb_piece))
            except ValueError:
                continue
        return out

    def _pieces_base_spec(self, frames):
        """조각이 나온 보드의 설계서(제목·무리·원본 PDF를 물려받으려고) — 가장 가까운 AI 보드. 없으면 빈 틀."""
        from easycad.ai.pdf_to_board import parse_board
        boards = [b for b in self._scene.items() if isinstance(b, _BoardItem) and (getattr(b, "_ai", None) or {}).get("spec")]
        if boards and frames:
            c = _outline_rect(frames).center()
            b = min(boards, key=lambda b: (b.sceneBoundingRect().center() - c).manhattanLength())
            try:
                return parse_board(b._ai["spec"]), b
            except ValueError:
                pass
        return {"kind": "block-board", "title": "", "meta": "", "subtitle": "", "highlight": "", "headline": "", "groups": [],
                "blocks": []}, None

    def _pieces_to_board(self):
        """「보드로 정리」 — 고른 조각들로 새 보드(AI 없이). 두 개씩 한 줄(칸 6), 남는 하나는 가운데. 반환: 새 보드(없으면 None)."""
        from easycad.ai.pdf_to_board import BLOCK_KIND, dump_board
        frames = [it for it in self._scene.selectedItems() if it.parentItem() is None and getattr(it, "_pb_piece", None)]
        pieces = self._pieces_selected()
        if not pieces:
            return None
        base, src = self._pieces_base_spec(frames)
        blocks = []
        for i, b in enumerate(pieces):
            blk = {k: v for k, v in b.items() if not k.startswith("_")}
            blk.update(row=i // 2 + 1, span=6, size=blk.get("size") or "normal")
            blocks.append(blk)
        spec = {k: v for k, v in base.items() if k not in ("blocks", "more", "_pages", "_figure")}
        spec.update(kind=BLOCK_KIND, blocks=blocks, headline="")
        code = dump_board(spec)
        everything = _outline_rect([it for it in self._scene.items() if it.parentItem() is None]) if self._scene.items() else QRectF()
        center = QPointF(everything.right() + 1400.0, (src.sceneBoundingRect().center().y() if src is not None
                                                      else everything.center().y()))
        _n, _a, _d, added = self._build_paper_board(code, center)
        new_boards = [it for it in added if isinstance(it, _BoardItem)]
        info = dict(getattr(src, "_ai", None) or {})
        info.update(spec=code, text="조각으로 정리", followup=True, origin=info.get("origin", ""))
        for b in new_boards:
            b._ai = dict(info)
        self._scene.clearSelection()
        if new_boards:
            new_boards[0].setSelected(True)
            self._ai_ensure_visible(self._view, self._ai_items_rect(new_boards))
        self._refresh_minimap()
        return new_boards[0] if new_boards else None

    # ---- 끌어다 놓기(§8 항목59 ③) — 조각을 보드에 넣기 · 보드 블록을 밖으로 꺼내기 ------------------------------------
    # `_push_entry` 길목(옮긴 기록이 쌓인 직후)에서 보고, 실제 바꾸기는 다음 이벤트에서(옮기기 기록과 따로 한 칸 — Ctrl+Z 한 번이면 넣기/꺼내기만 취소).

    def _pieces_after_push(self, ops):
        from PyQt6.QtCore import QTimer
        if getattr(self, "_pc_busy", False):
            return
        moves = [o for o in ops if o[0] == "mut" and o[2] == "pos"]
        if not moves:
            return
        boards = [(b, r) for b, r in self._boards() if self._board_block_spec(b) is not None]
        if not boards:
            return
        task = None
        for o in moves:   # 조각 틀이 보드 안에 떨어졌나
            f = o[1]
            if getattr(f, "_pb_piece", None):
                c = f.sceneBoundingRect().center()
                hit = [b for b, r in boards if r.contains(c)]
                if hit:
                    task = ("in", f, hit[0], c)
                    break
        if task is None:   # 보드 블록이 보드 밖으로 나갔나
            for o in moves:
                it, part = o[1], getattr(o[1], "_pb_part", None) or ""
                if not part.startswith("blocks[") or not hasattr(o[3], "x"):
                    continue
                c_new = it.sceneBoundingRect().center()
                c_old = c_new - (o[4] - o[3])
                for b, r in boards:
                    if r.contains(c_old) and not r.contains(c_new):
                        task = ("out", b, part, c_new)
                        break
                if task:
                    break
        if task is not None:
            QTimer.singleShot(0, lambda t=task: self._pieces_apply(t))

    def _board_block_spec(self, board):
        from easycad.ai.pdf_to_board import is_block_spec, parse_board
        info = getattr(board, "_ai", None) or {}
        if not info.get("spec"):
            return None
        try:
            spec = parse_board(info["spec"])
        except ValueError:
            return None
        return spec if is_block_spec(spec) else None

    def _pieces_apply(self, task):
        if task[0] == "in":
            _k, frame, board, c = task
            if frame.scene() is self._scene and board.scene() is self._scene:
                return self._piece_drop_into(frame, board, c)
        else:
            _k, board, part, c = task
            if board.scene() is self._scene:
                return self._piece_take_out(board, part, c)
        return None

    def _board_block_rects(self, board) -> dict:
        """보드 안 블록 자리 → 씬 사각형(그 블록 아이템들을 합친 것)."""
        rects = {}
        for b in self._board_set(board):
            for it in self._board_scope(b):
                p = getattr(it, "_pb_part", None) or ""
                if p.startswith("blocks["):
                    r = it.sceneBoundingRect()
                    rects[p] = rects[p].united(r) if p in rects else r
        return rects

    @staticmethod
    def _renumber_rows(blocks):
        """줄 번호를 1부터 차례로(빈 번호 없이) — 블록 차례는 그대로."""
        order = sorted({b["row"] for b in blocks})
        m = {r: i + 1 for i, r in enumerate(order)}
        for b in blocks:
            b["row"] = m[b["row"]]

    @staticmethod
    def _fit_row_spans(blocks, row):
        """한 줄의 칸 합이 12를 넘으면 고르게 나눈다(바닥 3칸)."""
        rb = [b for b in blocks if b["row"] == row]
        if sum(b["span"] for b in rb) > 12:
            for b in rb:
                b["span"] = max(3, 12 // len(rb))

    def _piece_drop_into(self, frame, board, c):
        """조각을 보드에 넣는다 — 놓은 높이의 블록과 같은 줄(그 블록 앞/뒤), 맨 위·맨 아래면 새 줄. 보드는 제자리에 다시 배치."""
        spec = self._board_block_spec(board)
        try:
            piece = json.loads(frame._pb_piece)
        except ValueError:
            return None
        blocks = [dict(b) for b in spec["blocks"]]
        rects = self._board_block_rects(board)
        blk = {k: v for k, v in piece.items() if not k.startswith("_")}
        blk.update(span=6, size=blk.get("size") or "normal")
        same = [(int(p[7:-1]), r) for p, r in rects.items() if r.top() <= c.y() <= r.bottom() and int(p[7:-1]) < len(blocks)]
        if same:
            j, r = min(same, key=lambda t: abs(t[1].center().x() - c.x()))
            blk["row"] = blocks[j]["row"]
            blocks.insert(j + 1 if c.x() > r.center().x() else j, blk)
            self._fit_row_spans(blocks, blk["row"])
        else:
            tops = [r.top() for r in rects.values()] or [c.y()]
            first = c.y() < min(tops)
            rows = [b["row"] for b in blocks] or [1]
            blk["row"] = (min(rows) - 0.5) if first else (max(rows) + 1)
            blocks.insert(0 if first else len(blocks), blk)
        self._renumber_rows(blocks)
        spec["blocks"] = blocks
        group = [it for it in self._scene.items() if it.parentItem() is None
                 and getattr(it, "_group_id", None) == getattr(frame, "_group_id", None)]
        new_boards = self._board_rebuild(board, spec, extra_remove=group or [frame])
        self.statusBar().showMessage("조각을 보드에 넣었어요 — 되돌리기 Ctrl+Z", 4000)
        return new_boards[0] if new_boards else None

    def _piece_take_out(self, board, part, c):
        """보드 블록을 밖으로 — 설계서에서 빼고 보드를 다시 배치, 놓은 자리에 조각으로(되돌리기 한 칸)."""
        spec = self._board_block_spec(board)
        i = int(part[7:-1])
        if i >= len(spec["blocks"]) or len(spec["blocks"]) <= 1:
            return None
        blk = spec["blocks"].pop(i)
        self._renumber_rows(spec["blocks"])
        stray = [it for it in self._scene.items() if it.parentItem() is None and getattr(it, "_pb_part", None) == part
                 and self._board_at(it) is None]   # 밖으로 끌어낸 그 블록 조각들(보드 안 범위에 안 들어 따로 걷는다)
        new_boards = self._board_rebuild(board, spec, extra_remove=stray)
        items, _h = self._piece_make(spec, blk, c.x() - self._PC_W / 2.0, c.y() - 20.0)
        self._undo[-1].ops += [("create", it) for it in items]
        self.statusBar().showMessage("블록을 보드에서 꺼냈어요(조각으로) — 되돌리기 Ctrl+Z", 4000)
        return items

    def _board_rebuild(self, board, spec, extra_remove=()) -> list:
        """보드(여러 장이면 묶음)를 새 설계서로 제자리에 다시 그린다 — 옛 것 걷기 + 새로 놓기를 되돌리기 한 칸으로. 색·`_ai`는 이어받는다."""
        from easycad.ai.pdf_to_board import dump_board
        self._pc_busy = True
        try:
            info = dict(getattr(board, "_ai", None) or {})
            boards = self._board_set(board)
            old = []
            for b in boards:
                old += [b] + self._board_scope(b)
            old = list(dict.fromkeys(old + list(extra_remove)))   # 한 번씩만(보드 범위에 보드 자신이 또 들어 있을 수 있다)
            center = self._ai_items_rect(boards).center()
            bg = board.bg().name()
            for it in old:
                if it.scene() is not None:
                    it.scene().removeItem(it)
            code = dump_board(spec)
            _n, _a, _d, added = self._build_paper_board(code, center, bg=bg)
            self._undo[-1].ops[0:0] = [("remove", it) for it in old]
            info["spec"] = code
            new_boards = [it for it in added if isinstance(it, _BoardItem)]
            for b in new_boards:
                b._ai = dict(info)
            self._scene.clearSelection()
            if new_boards:
                new_boards[0].setSelected(True)
            self._refresh_minimap()
            return new_boards
        finally:
            self._pc_busy = False

    # ---- 「종이로」(§8 항목59 ④) — 손으로 놓은 조각을 놓인 차례대로 쪽(16:9 보드 틀)에 나눠 담기 -----------------------------

    _PG_W, _PG_M = 1920.0, 64.0   # 쪽 폭 · 쪽 안 여백

    def _piece_groups(self, frames) -> list:
        """고른 조각 틀마다 (틀, 그 묶음 아이템들, 묶음 범위) — 읽는 차례(위→아래, 같은 높이면 왼→오)."""
        out = []
        for f in frames:
            gid = getattr(f, "_group_id", None)
            members = [it for it in self._scene.items() if it.parentItem() is None and gid and getattr(it, "_group_id", None) == gid] or [f]
            out.append((f, members, _outline_rect(members)))
        return sorted(out, key=lambda t: (round(t[2].top() / 60.0), t[2].left()))

    def _pieces_to_pages(self):
        """「종이로」 — 고른 조각을 지금 놓인 상대 위치 그대로 쪽마다 담는다(조각은 자르지 않고, 넘치면 다음 쪽). 쪽 = 16:9 보드 틀,
        여러 쪽이면 한 묶음(보드 막대 「내보내기 ▾」가 PDF 여러 쪽). 쪽들은 고른 곳 오른쪽에. 되돌리기 한 칸. 반환: 쪽 보드들."""
        frames = [it for it in self._scene.selectedItems() if it.parentItem() is None and getattr(it, "_pb_piece", None)]
        groups = self._piece_groups(frames)
        if not groups:
            return []
        cw = self._PG_W - 2 * self._PG_M
        ch = self._PG_W / BOARD_ASPECT - 2 * self._PG_M
        left = min(r.left() for _f, _m, r in groups)
        pages, cur, oy = [], [], None
        for g in groups:
            r = g[2]
            if cur and (r.right() - left > cw or r.bottom() - oy > ch or r.top() < oy - 60.0):
                pages.append((oy, cur))
                cur, oy = [], None
            if oy is None:
                oy = r.top()
            cur.append(g)
        if cur:
            pages.append((oy, cur))
        area = _outline_rect([it for _f, m, _r in groups for it in m])
        # 쪽 묶음은 빈 자리에 — 다른 보드 위에 겹쳐 놓으면 옮긴 조각이 그 보드에 「끌어다 넣기」로 들어갔다(실제 창)
        total_w = len(pages) * self._PG_W + (len(pages) - 1) * 120.0
        total_h = self._PG_W / BOARD_ASPECT
        moving = [it for _f, m, _r in groups for it in m]
        spot = self._ai_find_free_center(self._scene, total_w, total_h,
                                         QPointF(area.right() + 240.0 + total_w / 2.0, area.top() + total_h / 2.0), exclude=moving)
        x = spot.x() - total_w / 2.0
        top = spot.y() - total_h / 2.0
        set_id = uuid.uuid4().hex[:8] if len(pages) > 1 else None
        ops, boards = [], []
        zs = [it.zValue() for it in self._scene.items() if it.parentItem() is None and not isinstance(it, _BoardItem)]
        z = max(-999.0, min(zs, default=0.0) - 1.0)
        for k, (oy, gs) in enumerate(pages):
            h = self._PG_W / BOARD_ASPECT
            board = _BoardItem(QRectF(0.0, 0.0, self._PG_W, h), QColor("#ffffff"))
            board.setPos(x, top)
            board.setZValue(z)
            board.setFlags(board.GraphicsItemFlag.ItemIsMovable | board.GraphicsItemFlag.ItemIsSelectable)
            if set_id:
                board._set_id, board._page = set_id, k + 1
            self._scene.addItem(board)
            ops.append(("create", board))
            boards.append(board)
            d = QPointF(x + self._PG_M - left, top + self._PG_M - oy)
            for _f, members, _r in gs:
                for it in members:
                    old = QPointF(it.pos())
                    it.setPos(old + d)
                    ops.append(("mut", it, "pos", old, QPointF(it.pos())))
            x += self._PG_W + 120.0
        self._pc_busy = True   # 이 옮기기는 「끌어다 넣기」가 아니다
        try:
            self._push_entry(ops)
        finally:
            self._pc_busy = False
        self._scene.clearSelection()
        boards[0].setSelected(True)   # 보드 막대(색·내보내기 ▾ — PDF N쪽)가 바로 뜬다
        self._ai_ensure_visible(self._view, self._ai_items_rect(boards))
        self._refresh_minimap()
        self.statusBar().showMessage(f"조각을 {len(pages)}쪽에 담았어요 — 위 막대 「내보내기 ▾」에서 PDF로", 5000)
        return boards

    # ---- 조각 막대(고른 조각 위) ----------------------------------------------------------------------

    def _piece_bar_sync(self, view):
        """그리기 마지막 단계 훅 — 조각이 골라져 있으면 그 위에 「조각 N개 · 보드로 정리」 막대, 아니면 숨김."""
        from PyQt6 import sip
        bar = getattr(self, "_piece_bar", None)
        frames = [it for it in self._scene.selectedItems() if it.parentItem() is None and getattr(it, "_pb_piece", None)] \
            if view is self._view else []
        if not frames:
            if bar is not None and not sip.isdeleted(bar):
                bar.hide()
            return
        if bar is None or sip.isdeleted(bar) or bar.parent() is not view.viewport():
            bar = self._piece_bar = self._make_piece_bar(view)
        bar.label.setText(f"조각 {len(frames)}개")
        rect = _outline_rect(frames)
        self._ai_place_widget(view, bar, rect)
        bar.show()

    def _make_piece_bar(self, view):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
        from easycad.canvas.host_aimake import _BAR_BTN_QSS
        from easycad.canvas.host_dialogs import _CORAL_BTN_QSS
        bar = QFrame(view.viewport())
        bar.setObjectName("aiStagingBar")
        bar.setStyleSheet(self._AI_BAR_QSS)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(8)
        label = QLabel("조각", bar)
        label.setStyleSheet("font-weight:700; font-size:12px;")
        lay.addWidget(label)
        go = QPushButton("보드로 정리", bar)
        go.setToolTip("고른 조각들로 새 보드를 만들어 오른쪽에 — AI 없이(크레딧 안 듦)")
        go.setStyleSheet(_CORAL_BTN_QSS)
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.clicked.connect(self._pieces_to_board)
        lay.addWidget(go)
        paper = QPushButton("종이로", bar)
        paper.setToolTip("고른 조각을 지금 놓인 차례 그대로 쪽(16:9)에 나눠 담기 — 조각은 자르지 않음, 「내보내기 ▾」로 PDF 여러 쪽")
        paper.setStyleSheet(_BAR_BTN_QSS)
        paper.setCursor(Qt.CursorShape.PointingHandCursor)
        paper.clicked.connect(self._pieces_to_pages)
        lay.addWidget(paper)
        bar.label, bar.go_btn, bar.paper_btn = label, go, paper
        bar.adjustSize()
        return bar
