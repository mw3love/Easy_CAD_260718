"""CanvasWindow 믹스인 — 블록 조립식 보드(§8 항목57, 2026-10-16 시안 ③·④ https://claude.ai/artifact/Rpy4yHahposGC2EpJBojbS).

AI는 블록 설계서(`pdf_to_board._BLOCK_FORMAT`)로 **무엇을·어느 줄에·몇 칸으로·얼마나 크게**만 정하고, 좌표는 여기서 정한다:
- 12칸 격자(바깥 여백 `M`, 칸 사이 `G`). 블록은 `row` 차례로 줄을 이루고, 한 줄의 칸 수 합이 12를 넘으면 다음 줄로 넘긴다.
  합이 12보다 작은 줄은 **가운데로**(사용자 「이걸 가운데로」 = 그 줄에 혼자 + span < 12). 한 줄의 블록 카드는 높이를 맞춘다.
- 흐름도 블록은 미리 그려 크기를 재고, 칸이 좁으면 칸 수를 늘린다(흐름도가 칸 밖으로 나가지 않게).
- 「그림 크게」(앱 표시 `_figure: big`, AI 없이) = 그림 블록을 8칸·big으로 그 줄에 혼자(가운데).
- 크기 맞추기·여러 장은 옛 논문 틀과 같은 원칙: 16:9가 되게 넓히되 `BOARD_MAX_W`(출력 글자 바닥)까지, 넘치면 뒤쪽 줄부터 2장으로
  (「한 장으로」면 2장 대신 빼고 「생략」 표시).
- 아이템마다 설계서 자리 `_pb_part = "blocks[i]"`(보드 안 「선택 N개」가 AI에 알릴 자리 — `host_board._board_say`).

글 그리기·카드·그림 자르기·보드 틀은 `host_board._BoardMixin`의 `_pb_*` 도우미를 같이 쓴다.
"""
from __future__ import annotations

import json
import math

from PyQt6.QtCore import QPointF

from easycad.canvas.annotator_core import BOARD_ASPECT
from easycad.canvas.host_board import _ACCENT, _outline_rect

_BLOCK_NAME = {"text": "글", "list": "목록", "cards": "카드", "flow": "흐름", "bars": "막대", "numbers": "숫자", "figure": "그림",
               "table": "표", "terms": "용어", "timeline": "일정", "quote": "인용", "verdict": "의의와 한계"}
_SCALE = {"small": 0.9, "normal": 1.0, "big": 1.25}


def block_label(blk: dict) -> str:
    """보드 막대 「선택 N개 (…)」에 보일 블록 이름 — 제목이 있으면 제목, 없으면 종류."""
    return (blk.get("title") or _BLOCK_NAME.get(blk.get("type"), "블록"))[:14]


class _BlockBoardMixin:
    _BB_M, _BB_G, _BB_P = 64.0, 40.0, 16.0   # 바깥 여백 · 칸 사이 · 카드 안쪽 여백
    _BB_FIG_H = {"small": 200.0, "normal": 300.0, "big": 460.0}   # big은 머리글 + 한 줄 + 그림이 1장 높이(BOARD_MAX_W/16:9) 안에

    # ---- 줄 짜기 -----------------------------------------------------------------------------

    _BB_FLOW_TARGET = 1.6   # 흐름도 블록이 바라는 모양(폭/높이) — 8단계 세로 흐름이 한 줄로 아주 길어 보드가 2장이 됐다(실제 KAIROS)

    def _bb_flow_size(self, flow) -> tuple:
        """흐름도 블록 크기(폭, 높이) — 멀리서 한 번 그려 재고 지운다(같은 설계서는 한 번만)."""
        key = json.dumps(flow, ensure_ascii=False, sort_keys=True)
        cache = self.__dict__.setdefault("_bb_flow_cache", {})
        if key not in cache:
            _n, _a, _d, probe = self._build_flowspec_items(json.dumps(flow, ensure_ascii=False), QPointF(-1e6, -1e6),
                                                           push_undo=False, compact=True, wrap_target=self._BB_FLOW_TARGET)
            box = _outline_rect(probe)
            self._pb_discard(probe)
            cache[key] = (box.width(), box.height())
        return cache[key]

    def _bb_rows(self, spec, col) -> list:
        """블록 → 줄 목록 [[(설계서 자리, 블록, 칸 수), …], …]. `col` = 한 칸 폭(흐름도 칸 수 늘리기에 씀)."""
        G, P = self._BB_G, self._BB_P
        big_fig = spec.get("_figure") == "big"
        keyed = []
        for order, blk in enumerate(spec["blocks"]):
            idx = blk.get("_i", order)
            span = blk["span"]
            alone = False
            if blk["type"] == "flow":
                fw, _fh = self._bb_flow_size(blk["flow"])
                span = max(span, min(12, math.ceil((fw + 2 * P + G) / (col + G))))
            if blk["type"] == "figure" and big_fig:
                span, alone = max(span, 8), True
                blk = dict(blk, size="big")
            keyed.append(((blk["row"], 0 if alone else 1, order), idx, blk, span, alone))
        keyed.sort(key=lambda k: k[0])
        rows, cur, cur_key, used = [], [], None, 0
        for key, idx, blk, span, alone in keyed:
            group = (key[0], key[1])
            if cur and (group != cur_key or used + span > 12 or alone):
                rows.append(cur)
                cur, used = [], 0
            cur.append((idx, blk, span))
            cur_key, used = group, used + span
            if alone:
                rows.append(cur)
                cur, used, cur_key = [], 0, None
        if cur:
            rows.append(cur)
        return rows

    # ---- 배치 한 번 ------------------------------------------------------------------------------

    def _bb_layout(self, spec, width):
        """보드 왼쪽 위 (0,0) 기준으로 한 번 놓는다 — 반환 (폭, 필요 높이, 단계 수, 화살표 수, 넣은 아이템, 줄마다 아래 끝 y)."""
        M, G, P = self._BB_M, self._BB_G, self._BB_P
        content_w = width - 2 * M
        col = (content_w - 11 * G) / 12.0
        added: list = []
        y = 48.0
        self._pb_part_cur = "title"
        srcs = spec.get("_sources") or {}
        eyebrow = "한 장 정리 · Magic Board"
        if srcs:
            eyebrow += " · 자료 " + " · ".join(f"{k} {v.get('name', '')}" for k, v in sorted(srcs.items()))
        _t, h = self._pb_text(added, eyebrow, M, y, content_w, 9, self._PB_MUTED)
        y += h
        _t, h = self._pb_text(added, spec["title"] or "(제목 없음)", M, y, content_w, 22)
        y += h
        if spec.get("meta"):
            _t, h = self._pb_text(added, spec["meta"], M, y, content_w, 10, self._PB_MUTED)
            y += h
        if spec.get("subtitle"):
            self._pb_part_cur = "subtitle"
            y += 6
            sub, h = self._pb_text(added, spec["subtitle"], M, y, content_w, 15)
            if spec.get("highlight"):
                self._pb_mark(added, sub, spec["highlight"])
            y += h
        self._pb_part_cur = None
        if spec.get("_note"):   # 여러 장 — 「→ 2장에 이어서: …」 / 「생략(한 장으로): …」
            _t, h = self._pb_text(added, spec["_note"], M, y + 6, content_w, 10, self._PB_MUTED)
            y += h + 6
        y += 28.0
        n_steps = n_arrows = 0
        row_bottoms = []
        for row in self._bb_rows(spec, col):
            used = sum(span for _i, _b, span in row)
            x = M + (12 - used) / 2.0 * (col + G)   # 칸이 남는 줄은 가운데로
            cells, hs = [], []
            for idx, blk, span in row:
                w = span * col + (span - 1) * G
                self._pb_part_cur = f"blocks[{idx}]"
                start = len(added)
                h, ns, na = self._bb_block(added, spec, blk, x + P, y + P, w - 2 * P)
                n_steps += ns
                n_arrows += na
                cells.append((start, x, w, blk, idx))
                hs.append(h + 2 * P)
                x += w + G
            rh = max(hs)
            for start, bx, bw, blk, idx in reversed(cells):   # 같은 줄 카드는 높이를 맞춘다(먼저 넣은 것 = 아래)
                # 숫자는 숫자마다 카드, 흐름도는 카드 없이(카드 안을 지나는 화살표가 「도면 검사」의 "상자를 지나가는 선" — 옛 틀도 같음)
                if blk["type"] not in ("numbers", "flow"):
                    self._pb_part_cur = f"blocks[{idx}]"
                    self._pb_card_under(added, start, bx, y, bw, rh)
            y += rh
            row_bottoms.append(y)
            y += G
        self._pb_part_cur = None
        return width, y - G + 48.0, n_steps, n_arrows, added, row_bottoms

    # ---- 블록 하나 -------------------------------------------------------------------------------

    def _bb_block(self, added, spec, blk, x, y, w):
        """블록 내용(카드 안쪽 x, y, w) — 반환 (높이, 단계 수, 화살표 수)."""
        s = _SCALE.get(blk.get("size"), 1.0)
        t = blk["type"]
        y0 = y
        if blk.get("title") or blk.get("pages"):
            y += self._pb_heading(added, blk.get("title") or _BLOCK_NAME[t], blk.get("pages", ""), x, y, w) + 6
        ns = na = 0
        if t == "text":
            _i, h = self._pb_text(added, blk["body"], x, y, w, 11 * s)
            y += h
        elif t == "list":
            for it in blk["items"]:
                _i, h = self._pb_text(added, f"• {it}", x, y, w, 11 * s)
                y += h + 2
        elif t == "cards":
            y = self._bb_cards(added, blk["items"], x, y, w, s)
        elif t == "flow":
            fw, fh = self._bb_flow_size(blk["flow"])
            ns, na, _d, items = self._build_flowspec_items(json.dumps(blk["flow"], ensure_ascii=False),
                                                           QPointF(x + w / 2.0, y + fh / 2.0), push_undo=False, compact=True,
                                                           wrap_target=self._BB_FLOW_TARGET)
            for it in items:
                it._pb_part = self._pb_part_cur
            added += items
            y += fh
        elif t == "bars":
            y = self._bb_bars(added, blk, x, y, w, s)
        elif t == "numbers":
            y = self._bb_numbers(added, blk["items"], x - self._BB_P, y, w + 2 * self._BB_P, s)
        elif t == "figure":
            y = self._bb_figure(added, spec, blk, x, y, w)
        elif t == "table":
            y = self._bb_table(added, blk, x, y, w, s)
        elif t == "terms":
            for it in blk["items"]:
                _i, h = self._pb_text(added, f"{it['term']} — {it['meaning']}", x, y, w, 10 * s)
                y += h + 2
        elif t == "timeline":
            y = self._bb_timeline(added, blk["items"], x, y, w, s)
        elif t == "quote":
            _i, h = self._pb_text(added, f"“{blk['text']}”", x, y, w, 15 * s)
            y += h
            if blk.get("by"):
                _i, h = self._pb_text(added, f"— {blk['by']}", x, y + 2, w, 10, self._PB_MUTED)
                y += h + 2
        else:   # verdict
            for v in blk["items"]:
                tag = "문서 밖 맥락" if v["outside"] else v["type"]
                col = self._PB_TAG["outside"] if v["outside"] else self._PB_TAG[v["type"]]
                tg, _h = self._pb_text(added, tag, x, y + 2, 140, 9, col)
                tw = tg.document().size().width()
                body = v["text"] + (f"  ({v['pages']})" if v["pages"] and not v["outside"] else "")
                _i, h = self._pb_text(added, body, x + tw + 2, y, w - tw - 2, 10 * s)
                y += max(h, 20.0) + 2
        return y - y0, ns, na

    def _bb_cards(self, added, items, x, y, w, s):
        """카드 여러 개 — 넓으면 2~3열 격자(행마다 높이 맞춤)."""
        g = 12.0
        cols = max(1, min(len(items), int((w + g) // 250)))
        cw = (w - g * (cols - 1)) / cols
        for r in range(0, len(items), cols):
            cells = []
            for k, it in enumerate(items[r:r + cols]):
                cx = x + k * (cw + g)
                start = len(added)
                _t, h1 = self._pb_text(added, it["name"], cx + 12, y + 8, cw - 24 - 44, 12 * s)
                if it.get("pages"):
                    tag, _h = self._pb_text(added, it["pages"], cx, y + 11, 60, 9, self._PB_MUTED)
                    tag.setPos(cx + cw - 12 - tag.document().size().width(), y + 11)
                _t, h2 = self._pb_text(added, it["body"], cx + 12, y + 8 + h1, cw - 24, 10 * s)
                cells.append((start, cx, h1 + h2 + 18))
            hmax = max(h for _s, _x, h in cells)
            for start, cx, _h in reversed(cells):
                self._pb_card_under(added, start, cx, y, cw, hmax)
            y += hmax + g
        return y - g

    def _bb_bars(self, added, blk, x, y, w, s):
        bars = blk["bars"]
        vmax = max(b["value"] for b in bars) or 1.0
        label_w, val_w = min(170.0, w * 0.32), 64.0
        room = max(20.0, w - label_w - val_w)
        for b in bars:
            _t, h = self._pb_text(added, b["label"], x, y, label_w, 10 * s)
            bw = max(2.0, room * max(0.0, b["value"]) / vmax)   # 막대는 0부터
            col = _ACCENT if b["mine"] else self._PB_MUTED
            self._pb_card(added, x + label_w, y + 6, bw, 16.0 * s, fill=col, edge=col)
            self._pb_text(added, f"{b['value']:g}", x + label_w + bw + 6, y, val_w, 10 * s)
            y += max(h, 28.0 * s)
        if blk.get("note"):
            _t, h = self._pb_text(added, blk["note"], x, y + 2, w, 9, self._PB_MUTED)
            y += h + 2
        return y

    def _bb_numbers(self, added, items, x, y, w, s):
        """큰 숫자 카드들 — 블록 바깥 카드 없이 숫자마다 카드(시안 ③). 좁으면 두 줄."""
        g = 12.0
        per = len(items) if w / len(items) >= 150 else max(1, int((w + g) // 150))
        nw = (w - g * (per - 1)) / per
        for r in range(0, len(items), per):
            cells = []
            for k, num in enumerate(items[r:r + per]):
                nx = x + k * (nw + g)
                start = len(added)
                _t, h1 = self._pb_text(added, num["value"], nx + 14, y + 10, nw - 28, 26 * s, _ACCENT)
                _t, h2 = self._pb_text(added, num["label"], nx + 14, y + 10 + h1, nw - 28, 11 * s)
                foot = " · ".join(p for p in (num.get("note", ""), num.get("pages", "")) if p)
                h3 = 0.0
                if foot:
                    _t, h3 = self._pb_text(added, foot, nx + 14, y + 10 + h1 + h2, nw - 28, 9, self._PB_MUTED)
                cells.append((start, nx, h1 + h2 + h3 + 20))
            hmax = max(h for _s, _x, h in cells)
            for start, nx, _h in reversed(cells):
                self._pb_card_under(added, start, nx, y, nw, hmax)
            y += hmax + g
        return y - g

    def _bb_figure(self, added, spec, blk, x, y, w):
        from PyQt6.QtCore import QRectF
        from easycad.canvas.annotator_core import _ImageItem
        if blk.get("caption"):
            _t, h = self._pb_text(added, blk["caption"], x, y, w, 10, self._PB_MUTED)
            y += h + 4
        pm = self._pb_figure_source(spec, blk)
        if pm is None or pm.isNull():
            _t, h = self._pb_text(added, f"[그림 자리 — 원문 p.{blk['page']}]", x, y, w, 10, self._PB_MUTED)
            return y + h
        k = min(w / pm.width(), self._BB_FIG_H.get(blk.get("size"), 300.0) / pm.height())
        img = _ImageItem(pm, QRectF(0.0, 0.0, pm.width() * k, pm.height() * k))
        img.setPos(x + (w - pm.width() * k) / 2.0, y)
        img.setFlags(img.GraphicsItemFlag.ItemIsMovable | img.GraphicsItemFlag.ItemIsSelectable)
        img._pb_part = self._pb_part_cur
        self._scene.addItem(img)
        added.append(img)
        return y + pm.height() * k

    def _bb_table(self, added, blk, x, y, w, s):
        cols = blk["columns"]
        cw = w / len(cols)
        line = self._PB_EDGE

        def row(cells, pt, yy):
            hs = []
            for k, c in enumerate(cells):
                _t, h = self._pb_text(added, c, x + k * cw, yy, cw - 6, pt)
                hs.append(h)
            return max(hs) if hs else 0.0
        y += row(cols, 11 * s, y) + 4
        self._pb_card(added, x, y, w, 1.0, fill=line, edge=line, width=0.5)
        y += 4
        for r in blk["rows"]:
            y += row(r, 10 * s, y) + 3
            self._pb_card(added, x, y, w, 1.0, fill=line, edge=line, width=0.5)
            y += 4
        return y

    def _bb_timeline(self, added, items, x, y, w, s):
        """넓으면 가로 선 + 점 + 아래 글, 좁으면 「언제 — 무엇」 목록."""
        n = len(items)
        if n >= 2 and w / n >= 150:
            seg = w / n
            ly = y + 8
            hs = []
            for k, it in enumerate(items):
                cx = x + seg * k + seg / 2
                if k:   # 점 사이 선(점과 겹치지 않게 — 겹치면 「도면 검사」의 겹친 상자)
                    self._pb_card(added, cx - seg + 10, ly - 1, seg - 20, 2.0, fill=self._PB_EDGE, edge=self._PB_EDGE)
                col = _ACCENT if k == 0 else self._PB_MUTED
                self._pb_card(added, cx - 6, ly - 6, 12, 12, fill=col, edge=col)
                _t, h1 = self._pb_text(added, it["when"], cx - seg / 2 + 4, ly + 12, seg - 8, 11 * s)
                _t, h2 = self._pb_text(added, it["text"], cx - seg / 2 + 4, ly + 12 + h1, seg - 8, 10 * s)
                hs.append(h1 + h2)
            return ly + 12 + max(hs)
        for it in items:
            _t, h = self._pb_text(added, f"{it['when']} — {it['text']}", x, y, w, 10 * s)
            y += h + 2
        return y

    # ---- 크기 맞추기 · 여러 장 ---------------------------------------------------------------------

    def _bb_fit(self, spec):
        """배치 한 번(+ 세로로 길면 넓혀서 한 번 더) — 반환 (_bb_layout 결과, 보드 폭)."""
        res = self._bb_layout(spec, 1920.0)
        if res[1] * BOARD_ASPECT > res[0] * 1.05:
            self._pb_discard(res[4])
            res = self._bb_layout(spec, min(res[1] * BOARD_ASPECT * 0.92, self.BOARD_MAX_W))
        return res, max(res[0], res[1] * BOARD_ASPECT)

    def _build_block_board(self, spec, center=None, bg=None):
        """블록 설계서 → 보드(넘치면 2장) + 블록들(한 번의 되돌리기). 반환 모양은 흐름도와 같다."""
        import uuid
        blocks = [dict(b, _i=i) for i, b in enumerate(spec["blocks"])]
        one = spec.get("_pages") == "one"
        moved: list = []   # 2장(또는 생략)으로 보낸 블록(뒤쪽 줄부터)
        # 넘치면 먼저 AI가 고른 "big"을 보통으로(실제 KAIROS: 큰 그림 하나 때문에 마지막 줄만 2장으로 가 2장이 텅 빔). 사용자가 고른
        # 「그림 크게」(`_figure`)는 그대로.
        # 줄여도 1장에 안 들어가면 크기는 그대로(「그림을 가운데로 크게」처럼 사용자가 시킨 big일 수 있다 — 실제 KAIROS 이어 고치기).
        res, bw = self._bb_fit(dict(spec, blocks=blocks))
        self._pb_discard(res[4])
        if bw > self.BOARD_MAX_W and any(b.get("size") == "big" for b in blocks):
            smaller = [dict(b, size="normal") if b.get("size") == "big" else b for b in blocks]
            res, bw = self._bb_fit(dict(spec, blocks=smaller))
            self._pb_discard(res[4])
            if bw <= self.BOARD_MAX_W:
                blocks = smaller
        # 장마다: 넘치면 뒤쪽 줄부터 다음 장으로 — 다음 장도 넘치면 또 그다음 장으로(2026-10-17 검토: 블록 12개·표 8줄에서 2장째가
        # `BOARD_MAX_W`의 2.5배였다). 장마다 첫 줄은 남기니 반드시 끝난다.
        pages, rest, k = [], blocks, 1
        while rest:
            base = spec if k == 1 else dict(spec, subtitle="", highlight="",
                                            meta=(spec.get("meta") + " · " if spec.get("meta") else "") + f"{k}장 · 자세히")
            moved: list = []   # 다음 장(또는 생략)으로 보낸 블록(뒤쪽 줄부터)
            while True:
                s1 = dict(base, blocks=[b for b in rest if b["_i"] not in {m["_i"] for m in moved}])
                if moved:
                    names = " · ".join(block_label(b) for b in moved)
                    s1["_note"] = f"생략(한 장으로): {names}" if one else f"→ {k + 1}장에 이어서: {names}"
                res, bw = self._bb_fit(s1)
                rows = self._bb_rows(s1, (bw - 2 * self._BB_M - 11 * self._BB_G) / 12.0)
                big_fig = s1.get("_figure") == "big"
                movable = [r for r in rows[1:] if not (big_fig and any(b["type"] == "figure" for _i, b, _s in r))]
                if bw <= self.BOARD_MAX_W or not movable:   # 「그림 크게」 줄은 1장에 남긴다(사용자가 고른 것 — 옛 틀과 같음)
                    break
                self._pb_discard(res[4])
                moved = [b for _i, b, _s in movable[-1]] + moved   # 뒤쪽 줄을 통째로
            pages.append(res[:5])
            if one:
                break
            rest, k = moved, k + 1
        set_id = uuid.uuid4().hex[:8] if len(pages) > 1 else None
        added, n_steps, n_arrows = [], 0, 0
        c = center if center is not None else self._view.mapToScene(self._view.viewport().rect().center())
        sizes = [max(r[0], r[1] * BOARD_ASPECT) for r in pages]
        top = c.y() - max(sizes) / BOARD_ASPECT / 2.0
        x = c.x() - (sum(sizes) + 120.0 * (len(pages) - 1)) / 2.0
        from PyQt6.QtGui import QColor
        for i, r in enumerate(pages):
            bw = sizes[i]
            items = self._pb_place(*r, QPointF(x + bw / 2.0, top + bw / BOARD_ASPECT / 2.0), push=False)
            board = items[0]
            if bg is not None:
                board.apply_color(QColor(bg))
            if set_id:
                board._set_id, board._page = set_id, i + 1
            added += items
            n_steps += r[2]
            n_arrows += r[3]
            x += bw + 120.0
        self.push_undo_add_many(added)
        self._scene.clearSelection()
        return n_steps, n_arrows, "board", added
