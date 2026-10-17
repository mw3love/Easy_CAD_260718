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
import re

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from easycad.canvas.annotator_core import BOARD_ASPECT
from easycad.canvas.host_board import INK_ON_LIGHT, _ACCENT, _outline_rect

_BLOCK_NAME = {"text": "글", "list": "목록", "cards": "카드", "flow": "흐름", "steps": "단계", "bars": "막대", "numbers": "숫자", "figure": "그림",
               "table": "표", "terms": "용어", "timeline": "일정", "quote": "인용", "verdict": "의의와 한계"}
_SCALE = {"small": 0.9, "normal": 1.0, "big": 1.25}


def block_label(blk: dict) -> str:
    """보드 막대 「선택 N개 (…)」에 보일 블록 이름 — 제목이 있으면 제목, 없으면 종류."""
    return (blk.get("title") or _BLOCK_NAME.get(blk.get("type"), "블록"))[:14]


class _BlockBoardMixin:
    _BB_M, _BB_G, _BB_P = 64.0, 40.0, 16.0   # 바깥 여백 · 칸 사이 · 카드 안쪽 여백
    # 블록 역할별 모양(§8 항목58 ②) — 모든 블록을 같은 회색 상자로 그리던 것을: 주인공 하나는 진한 면, 숫자는 위 색 선, 카드는 왼쪽 색 띠,
    # 흐름도는 옅은 강조 면, 나머지는 상자 없이 위 가는 선. 진한 면·그 위 글은 일부러 무채색이 아니다 — 보드 잉크 맞추기(`_is_ink`)가
    # 흰/검정에 가까운 색만 바꾸므로, 무채색이면 흰 보드에서 크림 글자가 검정으로 뒤집혔다.
    _BB_HERO_BG = "#22303f"
    _BB_HERO_INK = "#fff4dd"
    _BB_HERO_MUTED = "#aebccc"
    _BB_BLUE = "#3d7fb8"
    _BB_PLUM = "#b0527a"
    # 무리 색(§8 항목59 ① — 시안처럼 같은 줄기 항목은 블록을 건너 같은 색). AI가 정한 groups 차례대로.
    _BB_GROUP_COLORS = (_ACCENT, "#3d7fb8", "#b0527a")

    def _bb_group_color(self, spec, item, default):
        g = (item or {}).get("group") if isinstance(item, dict) else ""
        groups = spec.get("groups") or []
        return self._BB_GROUP_COLORS[groups.index(g) % 3] if g and g in groups else default
    _BB_FLOW_FACE = QColor(218, 119, 86, 30)
    # 한 장 채우기(§8 항목58 ③) — 넘치면 2장으로 나누기 전에 이 차례로 조여 본다: (본문 배율, 그림 높이 배율, 간격 좁힘).
    # 본문 11pt → 10 → 9(출력해서 읽히는 바닥). 실측(1706.03762 보드 3개): 글자 크기보다 그림 높이·간격이 높이를 훨씬 많이 줄였다.
    _BB_MIN_W = 1280.0   # 내용이 적을 때 보드 폭 바닥
    _BB_FIT_STEPS = ((1.0, 1.0, False), (1.0, 0.7, True), (0.92, 0.6, True), (0.85, 0.5, True))
    _BB_TIGHT = (48.0, 28.0, 12.0)   # 좁힌 바깥 여백 · 칸 사이 · 카드 안쪽 여백
    _bb_k = 1.0
    _bb_figk = 1.0
    _bb_tight = False
    _bb_fig_extra: dict = {}
    _bb_masonry = False
    _bb_cards_cols: dict = {}
    _bb_cards_room: dict = {}   # 카드 블록이 채울 칸 높이(줄 맞춤 채우기)
    _bb_grow: dict = {}         # 블록 글 배율(줄 맞춤 채우기 — 줄보다 많이 낮은 글 블록, 최대 1.25배)
    _BB_GROW_TYPES = ("text", "list", "cards", "terms", "verdict", "timeline", "quote")

    def _bb_pad(self) -> float:
        return (self._BB_TIGHT if self._bb_tight else (self._BB_M, self._BB_G, self._BB_P))[2]

    def _bb_text_h(self, text, w, pt, bold=False) -> float:
        """글 높이만 잰다(그리지 않음) — `_pb_text`와 같은 줄바꿈."""
        from PyQt6.QtGui import QFontMetricsF
        from easycad.canvas.annotator_core import _TextItem
        from easycad.canvas.host_board import _emph_font, _pb_style, _wrap, split_emph
        t = _TextItem(QColor(INK_ON_LIGHT))
        _pb_style(t, pt, bold)
        room = max(10.0, w - 2 * t.document().documentMargin())
        plain, spans = split_emph(text)
        t.setPlainText(_wrap(plain, QFontMetricsF(_emph_font(t.font()) if spans else t.font()), room))
        return t.document().size().height()   # 카드 블록 열 수 상한(줄 맞춤 채우기 — 줄보다 많이 낮은 카드 4개는 2×2로)
    _bb_row_extra = 0.0   # 줄 사이에 더할 높이(세로 채우기 — 그림이 없을 때 남는 높이를 줄 사이에 고르게)
    _BB_FIG_H = {"small": 200.0, "normal": 300.0, "big": 460.0}   # big은 머리글 + 한 줄 + 그림이 1장 높이(BOARD_MAX_W/16:9) 안에

    # ---- 줄 짜기 -----------------------------------------------------------------------------

    _BB_FLOW_TARGET = 1.6   # 흐름도 블록이 바라는 모양(폭/높이) — 8단계 세로 흐름이 한 줄로 아주 길어 보드가 2장이 됐다(실제 KAIROS)
    _BB_FLOW_TARGET_TIGHT = 2.6   # 조이는 단계에선 더 가로로(§8 항목58 — 세로 흐름도 줄이 조여도 안 줄어 Sonnet 보드가 2장)

    def _bb_flow_target(self) -> float:
        return self._BB_FLOW_TARGET_TIGHT if self._bb_tight else self._BB_FLOW_TARGET

    def _bb_flow_size(self, flow) -> tuple:
        """흐름도 블록 크기(폭, 높이) — 멀리서 한 번 그려 재고 지운다(같은 설계서는 한 번만)."""
        key = (json.dumps(flow, ensure_ascii=False, sort_keys=True), self._bb_flow_target())
        cache = self.__dict__.setdefault("_bb_flow_cache", {})
        if key not in cache:
            _n, _a, _d, probe = self._build_flowspec_items(json.dumps(flow, ensure_ascii=False), QPointF(-1e6, -1e6),
                                                           push_undo=False, compact=True, wrap_target=self._bb_flow_target())
            box = _outline_rect(probe)
            self._pb_discard(probe)
            cache[key] = (box.width(), box.height())
        return cache[key]

    def _bb_rows(self, spec, col, skip=None) -> list:
        """블록 → 줄 목록 [[(설계서 자리, 블록, 칸 수), …], …]. `col` = 한 칸 폭(흐름도 칸 수 늘리기에 씀), `skip` = 옆 칸으로 뺀 블록 자리."""
        G, P = self._BB_G, self._BB_P
        big_fig = spec.get("_figure") == "big"
        keyed = []
        for order, blk in enumerate(spec["blocks"]):
            idx = blk.get("_i", order)
            if skip is not None and idx == skip:
                continue
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
        """보드 왼쪽 위 (0,0) 기준으로 한 번 놓는다 — 반환 (폭, 필요 높이, 단계 수, 화살표 수, 넣은 아이템, 칸 목록).
        칸 목록 = [(설계서 자리, 블록, x, 폭, 위 y, 높이, 아래에 다른 블록이 있나)]."""
        M, G, P = self._BB_TIGHT if self._bb_tight else (self._BB_M, self._BB_G, self._BB_P)
        content_w = width - 2 * M
        col = (content_w - 11 * G) / 12.0
        added: list = []
        y = 48.0
        self._pb_part_cur = "title"
        srcs = spec.get("_sources") or {}
        eyebrow = "한 장 정리 · Magic Board"
        if srcs:
            eyebrow += " · 자료 " + " · ".join(f"{k} {v.get('name', '')}" for k, v in sorted(srcs.items()))
        _t, h = self._pb_text(added, eyebrow, M, y, content_w, self._PB_SIZE["small"], _ACCENT, bold=600)   # 머리말은 코랄(§8 항목60 ②)
        y += h
        meta_w = content_w * 0.34 if spec.get("meta") else 0.0
        title_t, h = self._pb_text(added, spec["title"] or "(제목 없음)", M, y, content_w - meta_w - 24, self._PB_SIZE["title"], bold=800)
        if spec.get("meta"):   # 저자·출처는 오른쪽(§8 항목59 ① 시안 머리 — 제목은 왼쪽, 정보는 오른쪽)
            mt, mh = self._pb_text(added, spec["meta"], M, y, meta_w, 10, INK_ON_LIGHT)   # 흐린 회청은 "너무 흐릿"(§8 항목60 ②)
            mt.setPos(M + content_w - mt.document().size().width(), y + h - mh - 6)
        y += h
        if spec.get("subtitle"):
            self._pb_part_cur = "subtitle"
            y += 6
            sub, h = self._pb_text(added, spec["subtitle"], M, y, content_w, self._PB_SIZE["headline"], bold=600)
            if spec.get("highlight"):
                self._pb_mark(added, sub, spec["highlight"])
            y += h
        has_hero = any(b.get("hero") for b in spec["blocks"])
        if spec.get("headline") and not has_hero:   # 주인공 블록이 없으면 헤드라인은 머리에(있으면 주인공 면 위에 크게)
            self._pb_part_cur = "headline"
            y += 6
            _t, h = self._pb_text(added, spec["headline"], M, y, content_w, 20, self._bb_headline_ink(spec), bold=800)
            y += h
        self._pb_part_cur = "title"
        y += 10   # 머리 아래 굵은 구분선(시안 머리)
        self._pb_card(added, M, y, content_w, 2.0, fill=INK_ON_LIGHT, edge=INK_ON_LIGHT, width=0.0)
        y += 4
        self._pb_part_cur = None
        if spec.get("_note"):   # 여러 장 — 「→ 2장에 이어서: …」 / 「생략(한 장으로): …」
            _t, h = self._pb_text(added, spec["_note"], M, y + 6, content_w, 10, self._PB_MUTED)
            y += h + 6
        y_top = y + 28.0
        n_steps = n_arrows = 0
        # 두 가지 쌓기(§8 항목58 ③ → 2026-10-17 「격자 맞춤」):
        # - 줄 맞춤(기본) — 같은 줄 블록의 위 끝을 맞추고 줄 높이 = 가장 큰 블록. 면(주인공·흐름도)은 줄 높이만큼, 그림은 줄의 남는 높이만큼
        #   커진다(`_bb_fit`). 시안(아티팩트)과 나란히 보니 들쭉날쭉한 위 끝이 "정리 안 됨"으로 읽혔다(사용자 2026-10-17).
        # - 벽돌 쌓기(예비, `_bb_masonry`) — 블록마다 12칸 중 지금 가장 낮은 자리(같으면 AI가 줄에서 정한 자리). 줄 맞춤으로는 어느 조임 단계에서도
        #   한 장이 안 될 때만(키 큰 블록이 한 기둥에 몰린 경우 줄 맞춤보다 낮다).
        # 둘 다 차례·칸 수는 AI 그대로, 줄에 혼자인 좁은 블록은 가운데(「가운데로」 지시).
        masonry = self._bb_masonry
        cells, sky = [], [y_top] * 12   # cells: [start, end, x, w, blk, idx, y, h, 줄 높이] · sky: 칸마다 다음 블록이 놓일 y
        y_row = y_top
        # 세로로 긴 그림은 오른쪽 옆 칸에 여러 줄에 걸쳐 크게(§8 항목60 ③ — 시안처럼). 옆 칸과 나란한 줄은 왼쪽 좁은 12칸 격자에 놓고,
        # 그림 아래로 내려간 줄부터 다시 보드 폭 전체. 줄 맞춤에서만(벽돌 쌓기는 칸 하나하나를 쓰므로 옆 칸과 섞지 않는다).
        side = None if masonry else self._bb_side_figure(spec, width, col, y_top)
        side_bottom = y_top
        ncol = col
        if side is not None:
            s_idx, s_blk, s_w, s_h = side
            ncol = (content_w - s_w - G - 11 * G) / 12.0
            x_s = M + content_w - s_w
            self._pb_part_cur = f"blocks[{s_idx}]"
            start = len(added)
            h, _ns, _na = self._bb_block(added, spec, dict(s_blk, _side_h=s_h), x_s, y_top + P, s_w)
            cells.append([start, len(added), x_s, s_w, dict(s_blk, _side_h=s_h), s_idx, y_top, h + 2 * P, 0.0])
            side_bottom = y_top + h + 2 * P
        for row in self._bb_rows(spec, ncol, skip=side[0] if side else None):
            narrow = side is not None and y_row < side_bottom
            cw = ncol if narrow else col
            want = 0
            used = sum(span for _i, _b, span in row)
            if narrow and used < 12:   # 옆 칸으로 그림을 뺀 줄 — 남은 블록이 좁은 격자를 채우게
                row = [(i, b, sp * 12.0 / used) for i, b, sp in row]
                used = 12
            rcells = []
            for idx, blk, span in row:
                w = span * cw + (span - 1) * G
                if not masonry:   # 줄 맞춤 — 줄의 칸 합이 12보다 작으면 줄 전체를 가운데로(옛 배치와 같음)
                    c0 = (12 - used) / 2.0 + want
                    covered = range(int(c0), min(12, int(math.ceil(c0 + span))))
                    by = y_row
                elif len(row) == 1 and span < 12:   # 가운데(칸 경계에 안 맞아도 됨 — 걸치는 칸 모두 막음)
                    c0 = (12 - span) / 2.0
                    covered = range(int(c0), min(12, int(math.ceil(c0 + span))))
                    by = max(sky[c] for c in covered)
                else:
                    c0 = min(range(0, 13 - span), key=lambda c: (max(sky[c:c + span]), abs(c - want)))
                    covered = range(c0, c0 + span)
                    by = max(sky[c] for c in covered)
                want += span
                x = M + c0 * (cw + G)
                self._pb_part_cur = f"blocks[{idx}]"
                start = len(added)
                hero = bool(blk.get("hero"))
                inset = P if (hero or blk["type"] in self._BB_FACE_TYPES) else 0.0   # 면이 있는 블록만 안쪽 여백
                h, ns, na = self._bb_block(added, spec, blk, x + inset, by + P, w - 2 * inset)
                n_steps += ns
                n_arrows += na
                cell = [start, len(added), x, w, blk, idx, by, h + 2 * P, 0.0]
                cells.append(cell)
                rcells.append(cell)
                for c in covered:
                    sky[c] = by + h + 2 * P + G
            if not masonry:
                rh = max(c[7] for c in rcells)
                for c in rcells:
                    c[8] = rh
                y_row += rh + G + self._bb_row_extra
        bottom = max((c[6] + max(c[7], c[8]) for c in cells), default=y_top)
        info = []
        for c in cells:
            _s, _e, bx, bw, blk, idx, by, bh, rh = c
            below = [d[6] for d in cells if d[6] > by + 1 and d[2] < bx + bw - 1 and d[2] + d[3] > bx + 1]
            if masonry:
                room = (min(below) - G if below else bottom) - by
                if blk.get("hero") or blk["type"] in self._BB_FACE_TYPES:   # 면은 아래 이웃(또는 내용 끝)까지 — 너무 길어지면(텅 빈 큰 면) 그대로
                    if room <= bh * 1.6:
                        c[7] = max(bh, room)
            else:
                room = rh
                if blk.get("hero") or blk["type"] in self._BB_FACE_TYPES:   # 면은 줄 높이만큼(같은 줄 블록과 아래 끝이 맞게)
                    c[7] = rh
            # (자리, 블록, x, 폭, y, 높이, 아래에 다른 블록이 있나, 이 칸에서 쓸 수 있는 높이)
            info.append((f"blocks[{idx}]", blk, bx, bw, by, c[7], bool(below), room))
        for start, end, bx, bw, blk, idx, by, bh, _rh in reversed(cells):   # 뒤 칸부터(앞 칸의 자리 번호가 안 밀리게)
            self._pb_part_cur = f"blocks[{idx}]"
            if blk.get("hero"):
                self._bb_hero_ink(added[start:end])
                self._pb_card_under(added, start, bx, by, bw, bh, fill=self._BB_HERO_BG, edge=self._BB_HERO_BG)
            elif blk["type"] in self._BB_FACE_TYPES:
                # 흐름도는 상자 대신 채운 패스 — 상자면 그 안을 지나는 화살표가 「도면 검사」의 "상자를 지나가는 선"(옛 틀과 같은 이유)
                self._bb_face(added, start, bx, by, bw, bh, self._BB_FLOW_FACE)
            elif blk["type"] not in ("numbers", "cards"):   # 숫자·카드는 안의 선·띠가 모양을 맡는다
                self._pb_card(added, bx, by, bw, 1.5, fill=self._PB_EDGE, edge=self._PB_EDGE, width=0.0)
        self._pb_part_cur = None
        return width, bottom + 48.0, n_steps, n_arrows, added, info

    # ---- 블록 하나 -------------------------------------------------------------------------------

    def _bb_block(self, added, spec, blk, x, y, w):
        """블록 내용(카드 안쪽 x, y, w) — 반환 (높이, 단계 수, 화살표 수)."""
        s = _SCALE.get(blk.get("size"), 1.0) * self._bb_k   # 넘칠 때 본문 한 단계 줄이기(§8 항목58 ③)
        s *= self._bb_grow.get(self._pb_part_cur, 1.0)          # 칸이 남으면 그 블록 글을 키운다(줄 맞춤 채우기)
        t = blk["type"]
        y0 = y
        if blk.get("title") or blk.get("pages"):
            y += self._pb_heading(added, blk.get("title") or _BLOCK_NAME[t], blk.get("pages", ""), x, y, w) + 6
        if blk.get("hero") and spec.get("headline"):   # 주인공 면 위 헤드라인(§8 항목58 ②)
            _i, h = self._pb_text(added, spec["headline"], x, y + 4, w, 20, self._bb_headline_ink(spec), bold=800)
            y += h + 12
        ns = na = 0
        if t == "text":
            _i, h = self._pb_text(added, blk["body"], x, y, w, 11 * s)
            y += h
        elif t == "list":
            for it in blk["items"]:
                _i, h = self._pb_text(added, f"• {it}", x, y, w, 11 * s)
                y += h + 2
        elif t == "cards":
            room = self._bb_cards_room.get(self._pb_part_cur)   # 줄 맞춤 채우기 — 카드 행을 칸 아래 끝까지 늘린다
            y = self._bb_cards(added, blk["items"], x, y, w, s, bottom=(y0 + room - 2 * self._bb_pad()) if room else None, spec=spec)
        elif t == "flow":
            fw, fh = self._bb_flow_size(blk["flow"])
            ns, na, _d, items = self._build_flowspec_items(json.dumps(blk["flow"], ensure_ascii=False),
                                                           QPointF(x + w / 2.0, y + fh / 2.0), push_undo=False, compact=True,
                                                           wrap_target=self._bb_flow_target())
            for it in items:
                it._pb_part = self._pb_part_cur
            added += items
            y += fh
        elif t == "steps":
            y = self._bb_steps(added, blk, x, y, w, s)
        elif t == "bars":
            y = self._bb_bars(added, blk, x, y, w, s)
        elif t == "numbers":
            y = self._bb_numbers(added, blk["items"], x, y, w, s, spec=spec)
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
                start = len(added)
                tg, th = self._pb_text(added, tag, x + 4, y + 1, 140, 9, col, bold=True)
                tw = tg.document().size().width() + 8
                chip = QColor(col)
                chip.setAlpha(40)   # 색 딱지(칩) — 옅은 바탕 + 같은 색 글(§8 항목60 ⑤, 시안처럼)
                self._pb_card_under(added, start, x, y + 2, tw, th - 2, fill=chip, edge=chip)
                tw += 6
                body = v["text"] + (f"  ({v['pages']})" if v["pages"] and not v["outside"] else "")
                _i, h = self._pb_text(added, body, x + tw + 2, y, w - tw - 2, 10 * s)
                y += max(h, 20.0) + 2
        return y - y0, ns, na

    _BB_FACE_TYPES = ("flow", "steps")   # 옅은 강조 면을 까는 블록

    def _bb_steps(self, added, blk, x, y, w, s):
        """가로 단계 카드(§8 항목60 ④) — 왼쪽→오른쪽 한 줄, 번호·글·아래 기호. 핵심 단계(`focus`) 하나만 코랄 면·크림 글.
        흐름도 엔진은 16:9에 맞추려 꺾어 내리므로(`best_wrap`) 짧은 계산 순서가 꺾인 화살표로 읽혔다(사용자 2026-10-17)."""
        items = blk["items"]
        n = len(items)
        g = 10.0
        per_row = n if (w - g * (n - 1)) / n >= 96.0 else math.ceil(n / 2)   # 너무 좁으면 두 줄(그래도 왼쪽→오른쪽)
        cw = (w - g * (per_row - 1)) / per_row
        pad = 10.0
        rows = [items[i:i + per_row] for i in range(0, n, per_row)]
        for r, row in enumerate(rows):
            heights = []
            for it in row:
                h = self._bb_text_h(it["text"], cw - 2 * pad, 11 * s, True) + 18.0
                if it.get("sym"):
                    h += self._bb_text_h(it["sym"], cw - 2 * pad, 12 * s, True) + 14.0
                heights.append(h)
            ch = max(heights) + 2 * pad
            for k, it in enumerate(row):
                i = r * per_row + k
                cx = x + k * (cw + g)
                focus = blk.get("focus") == i + 1
                start = len(added)
                ink = self._BB_HERO_INK if focus else INK_ON_LIGHT
                self._pb_text(added, str(i + 1), cx + pad, y + pad, cw - 2 * pad, 9, self._BB_HERO_INK if focus else self._PB_MUTED, bold=True)
                self._pb_text(added, it["text"], cx + pad, y + pad + 16.0, cw - 2 * pad, 11 * s, ink, bold=True)
                if it.get("sym"):
                    sh = self._bb_text_h(it["sym"], cw - 2 * pad, 12 * s, True)
                    self._pb_text(added, it["sym"], cx + pad, y + ch - pad - sh, cw - 2 * pad, 12 * s, ink, bold=800)
                if focus:
                    self._pb_card_under(added, start, cx, y, cw, ch, fill=_ACCENT, edge=_ACCENT)
                else:
                    self._pb_card_under(added, start, cx, y, cw, ch)   # 회색 알파 — 흰·검정 보드 둘 다
                if k:   # 카드 사이 가는 선 — 차례를 잇는다
                    self._pb_card(added, cx - g, y + ch / 2.0, g, 1.5, fill=_ACCENT, edge=_ACCENT, width=0.0)
            y += ch + (g if r < len(rows) - 1 else 0.0)
        if blk.get("note"):
            _t, h = self._pb_text(added, blk["note"], x, y + 8, w, 10 * s, self._PB_MUTED)
            y += h + 8
        return y

    def _bb_cards(self, added, items, x, y, w, s, bottom=None, spec=None):
        """카드 여러 개 — 넓으면 2~3열 격자(행마다 높이 맞춤). `bottom`이 있으면 행을 고르게 늘려 그 높이까지 채운다."""
        g = 12.0
        cols = max(1, min(len(items), int((w + g) // 250)))
        cols = min(cols, self._bb_cards_cols.get(self._pb_part_cur, cols))   # 줄이 남으면 열을 줄여 키를 키운다(`_bb_fit`)
        cw = (w - g * (cols - 1)) / cols
        n_rows = (len(items) + cols - 1) // cols
        if bottom is not None:   # 먼저 재 보고(그리지 않고) 남는 높이를 행마다 나눈다
            natural = 0.0
            for r in range(0, len(items), cols):
                natural += max(self._bb_text_h(it["name"], cw - 24 - 60, 12 * s, True) + self._bb_text_h(it["body"], cw - 24, 10 * s) + 18
                               for it in items[r:r + cols]) + g
            add = max(0.0, (bottom - y - (natural - g)) / n_rows)
        else:
            add = 0.0
        for r in range(0, len(items), cols):
            cells = []
            for k, it in enumerate(items[r:r + cols]):
                cx = x + k * (cw + g)
                start = len(added)
                tag_w = 0.0
                if it.get("pages"):   # 쪽 번호를 먼저 재고 이름 폭에서 뺀다(§8 항목58 ④ — 폭 60에 갇혀 두 줄로 접혀 본문과 겹쳤다)
                    tag, _h = self._pb_text(added, it["pages"], cx, y + 11, cw * 0.45, 9, self._PB_MUTED)
                    tag_w = tag.document().size().width()
                    tag.setPos(cx + cw - 12 - tag_w, y + 11)
                _t, h1 = self._pb_text(added, it["name"], cx + 12, y + 8, cw - 24 - tag_w - 6, 12 * s, bold=True)
                _t, h2 = self._pb_text(added, it["body"], cx + 12, y + 8 + h1, cw - 24, 10 * s)
                cells.append((start, cx, h1 + h2 + 18))
            hmax = max(h for _s, _x, h in cells) + add
            for k, (_start, cx, _h) in enumerate(cells):   # 상자 대신 왼쪽 색 띠(§8 항목58 ②) — 색은 무리(§8 항목59 ①)
                col = self._bb_group_color(spec or {}, items[r + k], self._BB_BLUE)
                self._pb_card(added, cx, y + 4, 4.0, hmax - 8, fill=col, edge=col, width=0.0)
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

    def _bb_number_colors(self, spec, items) -> list:
        """숫자마다 색 — AI가 정한 무리 색, 그런데 모두 같은 색이고 단위가 다른 숫자가 섞였으면 많은 쪽 단위만 그 색, 나머지는 다른 색
        (§8 항목60 ⑤ — BLEU 둘과 「3.5일」이 같은 색이라 셋이 한 묶음으로 읽혔다. 시안은 점수 코랄·일수 파랑)."""
        cols = [self._bb_group_color(spec, num, _ACCENT) for num in items]
        units = [re.sub(r"^[\s\d.,+\-−~≈%]+", "", str(num.get("value", ""))).strip() for num in items]
        if len(set(cols)) == 1 and len(set(units)) > 1:
            main = max(set(units), key=units.count)
            other = self._BB_BLUE if cols[0] != self._BB_BLUE else _ACCENT
            cols = [c if u == main else other for c, u in zip(cols, units)]
        return cols

    def _bb_number_per_row(self, items, w, g, s) -> int:
        """한 줄 타일 수 — 많을수록 좋지만 타일이 115 이상이고 이름의 가장 긴 낱말이 안 끊길 때만(§8 항목60 — 옆 칸 옆 좁은 칸에서
        150 기준이면 셋이 두 줄로 줄이 높아져 진한 면이 텅 비었고, 그냥 줄이면 「영어→독일 / 어」처럼 낱말이 끊겼다 — 실제 KAIROS)."""
        from PyQt6.QtGui import QFontMetricsF
        from easycad.canvas.annotator_core import _TextItem
        from easycad.canvas.host_board import _pb_style
        t = _TextItem(QColor(INK_ON_LIGHT))
        _pb_style(t, 11 * s, False)
        fm = QFontMetricsF(t.font())
        longest = max((fm.horizontalAdvance(word) for num in items for word in str(num.get("label", "")).split()), default=0.0)
        margin = 2 * t.document().documentMargin() + 28.0   # 타일 안 여백(양쪽 14) + 글 상자 여백
        for per in range(len(items), 1, -1):
            nw = (w - g * (per - 1)) / per
            if nw >= 115.0 and longest + margin <= nw:
                return per
        return 1 if w < 230.0 else min(len(items), 2) if (w - g) / 2 >= longest + margin else 1

    def _bb_numbers(self, added, items, x, y, w, s, spec=None):
        """큰 숫자 타일들 — 숫자마다 얇은 테두리 타일 + 안쪽 위 색 선(무리 색), 단위는 작게(§8 항목59 ①). 좁으면 두 줄."""
        g = 12.0
        per = self._bb_number_per_row(items, w, g, s)
        cols = self._bb_number_colors(spec or {}, items)
        if per < len(items) and len(items) > 1 and w >= 260.0:
            return self._bb_numbers_stacked(added, items, cols, x, y, w, s)
        nw = (w - g * (per - 1)) / per
        for r in range(0, len(items), per):
            cells = []
            for k, num in enumerate(items[r:r + per]):
                nx = x + k * (nw + g)
                start = len(added)
                col = cols[r + k]
                h1 = self._bb_number_value(added, num["value"], nx + 14, y + 12, nw - 28, 26 * s, col)
                _t, h2 = self._pb_text(added, num["label"], nx + 14, y + 10 + h1, nw - 28, 11 * s)
                foot = " · ".join(p for p in (num.get("note", ""), num.get("pages", "")) if p)
                h3 = 0.0
                if foot:
                    _t, h3 = self._pb_text(added, foot, nx + 14, y + 10 + h1 + h2, nw - 28, 9, self._PB_MUTED)
                cells.append((start, nx, h1 + h2 + h3 + 24, col))
            hmax = max(c[2] for c in cells)
            for start, nx, _h, col in reversed(cells):   # 타일(얇은 테두리, 바탕 없음) + 안쪽 위 색 선 — 선이 타일 안에 쏙(「도면 검사」 묶음)
                self._pb_card_under(added, start, nx, y, nw, hmax, fill=QColor(0, 0, 0, 0), edge=self._PB_EDGE)
                self._pb_card(added, nx + 1, y + 1, nw - 2, 4.0, fill=col, edge=col, width=0.0)
            y += hmax + g
        return y - g

    def _bb_numbers_stacked(self, added, items, cols, x, y, w, s):
        """좁은 칸의 숫자 — 한 줄에 다 안 들면 누운 타일을 세로로(왼쪽 큰 숫자, 오른쪽 이름·설명, 왼쪽 무리 색 띠).
        세운 타일을 두 줄로 꺾으면 줄이 높아져 옆 진한 면이 텅 비었다(§8 항목60, 실제 KAIROS)."""
        g = 10.0
        left = min(150.0, w * 0.42)
        for num, col in zip(items, cols):
            start = len(added)
            h1 = self._bb_number_value(added, num["value"], x + 14, y + 8, left - 18, 24 * s, col)
            _t, h2 = self._pb_text(added, num["label"], x + left, y + 10, w - left - 10, 11 * s, bold=True)
            foot = " · ".join(p for p in (num.get("note", ""), num.get("pages", "")) if p)
            h3 = 0.0
            if foot:
                _t, h3 = self._pb_text(added, foot, x + left, y + 10 + h2, w - left - 10, 9, self._PB_MUTED)
            h = max(h1 + 16, h2 + h3 + 20)
            self._pb_card_under(added, start, x, y, w, h, fill=QColor(0, 0, 0, 0), edge=self._PB_EDGE)
            self._pb_card(added, x + 1, y + 1, 4.0, h - 2, fill=col, edge=col, width=0.0)
            y += h + g
        return y - g

    _BB_SIDE_RATIO = 1.15   # 그림 높이/폭이 이보다 크면 세로 그림 — 옆 칸으로

    def _bb_fig_ratio(self, spec, blk):
        """그림 높이/폭(못 읽으면 None) — 배치를 여러 번 재므로 자료·쪽마다 한 번만 읽는다."""
        src = (spec.get("_sources") or {}).get(blk.get("source", ""), {})
        key = (src.get("path") or spec.get("_pdf") or "", blk.get("page"))
        cache = self.__dict__.setdefault("_bb_ratio_cache", {})
        if key not in cache:
            pm = self._pb_figure_source(spec, blk)
            cache[key] = pm.height() / pm.width() if pm is not None and not pm.isNull() and pm.width() else None
        return cache[key]

    def _bb_side_figure(self, spec, width, col, y_top):
        """옆 칸에 놓을 세로 그림 — (설계서 자리, 블록, 옆 칸 폭, 그림 높이 한도) 또는 None.
        사용자가 고른 「그림 크게」(`_figure: big`, 가운데 한 줄)는 그대로 둔다."""
        if spec.get("_figure") == "big":
            return None
        M, G, P = self._BB_TIGHT if self._bb_tight else (self._BB_M, self._BB_G, self._BB_P)
        for order, blk in enumerate(spec["blocks"]):
            if blk["type"] != "figure":
                continue
            ratio = self._bb_fig_ratio(spec, blk)
            if not ratio or ratio < self._BB_SIDE_RATIO:
                return None
            cap = 28.0 if blk.get("caption") else 0.0
            room_h = width / BOARD_ASPECT - y_top - 48.0 - 2 * P - cap - self._bb_text_h(blk.get("title") or "", 300, self._PB_SIZE["heading"], True)
            h = max(260.0, room_h) * self._bb_figk
            n = min(5, max(3, math.ceil((h / ratio + 2 * P + G) / (col + G))))
            return blk.get("_i", order), blk, n * col + (n - 1) * G, h
        return None

    def _bb_figure(self, added, spec, blk, x, y, w):
        from PyQt6.QtCore import QRectF
        from easycad.canvas.annotator_core import _ImageItem
        pm = self._pb_figure_source(spec, blk)
        if pm is None or pm.isNull():
            _t, h = self._pb_text(added, f"[그림 자리 — 원문 p.{blk['page']}]", x, y, w, 10, self._PB_MUTED)
            return y + h
        # 사용자가 시킨 「그림 크게」는 한 장 맞추기에서도 줄이지 않는다(그 대신 다른 블록이 2장으로 — 옛 틀과 같은 원칙)
        base = self._BB_FIG_H.get(blk.get("size"), 300.0) * (1.0 if spec.get("_figure") == "big" else self._bb_figk)
        more = self._bb_fig_extra.get(self._pb_part_cur, 0.0)
        limit = base + (min(base * 0.6, more) if self._bb_masonry else more)   # 칸의 남는 높이만큼(벽돌 쌓기는 1.6배까지)
        if blk.get("_side_h"):   # 옆 칸 세로 그림 — 칸 폭과 보드 높이 안에서 가장 크게
            limit = blk["_side_h"]
        k = min(w / pm.width(), limit / pm.height())
        img = _ImageItem(pm, QRectF(0.0, 0.0, pm.width() * k, pm.height() * k))
        img.setPos(x + (w - pm.width() * k) / 2.0, y)
        img.setFlags(img.GraphicsItemFlag.ItemIsMovable | img.GraphicsItemFlag.ItemIsSelectable)
        img._pb_part = self._pb_part_cur
        self._scene.addItem(img)
        added.append(img)
        y += pm.height() * k
        if blk.get("caption"):   # 설명은 그림 아래(§8 항목60 ③ — 읽는 차례: 그림 → 설명)
            _t, h = self._pb_text(added, blk["caption"], x, y + 6, w, 10, self._PB_MUTED)
            y += h + 6
        return y

    def _bb_table(self, added, blk, x, y, w, s):
        cols = blk["columns"]
        cw = w / len(cols)
        line = self._PB_EDGE

        def row(cells, pt, yy, bold=False):
            hs = []
            for k, c in enumerate(cells):
                _t, h = self._pb_text(added, c, x + k * cw, yy, cw - 6, pt, bold=bold)
                hs.append(h)
            return max(hs) if hs else 0.0
        y += row(cols, 11 * s, y, bold=True) + 4
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
                _t, h1 = self._pb_text(added, it["when"], cx - seg / 2 + 4, ly + 12, seg - 8, 11 * s, bold=True)
                _t, h2 = self._pb_text(added, it["text"], cx - seg / 2 + 4, ly + 12 + h1, seg - 8, 10 * s)
                hs.append(h1 + h2)
            return ly + 12 + max(hs)
        for it in items:
            _t, h = self._pb_text(added, f"{it['when']} — {it['text']}", x, y, w, 10 * s)
            y += h + 2
        return y

    def _bb_number_value(self, added, value, x, y, w, pt, color) -> float:
        """큰 숫자 — 숫자는 크게, 뒤 단위(「일」·「시간」·「%」·「BLEU」)는 절반 크기로 바로 옆 아래 맞춤. 반환 높이."""
        m = re.match(r"^\s*([+\-−]?[\d][\d.,]*)\s*(\S.*)?$", value or "")
        if not m or not m.group(2):
            _t, h = self._pb_text(added, value, x, y, w, self._bb_num_pt(value, w, pt), color, bold=800)
            return h
        num, unit = m.group(1), m.group(2)
        big = self._bb_num_pt(num + unit[:2], w, pt)
        t, h = self._pb_text(added, num, x, y, w, big, color, bold=800)
        nw = t.document().idealWidth() if hasattr(t.document(), "idealWidth") else t.document().size().width()
        small = max(10, int(big * 0.5))
        u, uh = self._pb_text(added, unit, x + nw - 6, y, max(40.0, w - nw), small, color, bold=True)
        u.setPos(x + nw - 6, y + h - uh - h * 0.12)   # 숫자 아래쪽에 맞춤(대략 밑줄 맞춤)
        return h

    def _bb_num_pt(self, value, room, pt):
        """큰 숫자 글자 크기 — 한 줄에 안 들면 들 때까지 줄인다(§8 항목58 ④ — 좁은 칸에서 「12시/간」으로 접혔다). 바닥 14pt."""
        from PyQt6.QtGui import QFontMetricsF
        f = self._pb_small_font()
        f.setBold(True)
        size = int(pt)
        while size > 14:
            f.setPointSize(size)
            if QFontMetricsF(f).horizontalAdvance(value) + 12.0 <= room:   # 12 = 글 상자 안 여백
                break
            size -= 1
        return size

    @staticmethod
    def _bb_headline_ink(spec) -> str:
        """헤드라인 글색 — 「**구절**」이 있으면 잉크(그 구절만 코랄), 없으면 옛 보드처럼 전체 코랄(§8 항목60 ①)."""
        return INK_ON_LIGHT if "**" in (spec.get("headline") or "") else _ACCENT

    def _bb_hero_ink(self, items):
        """주인공 면 위 글 — 잉크는 크림, 흐린 글은 밝은 회청(강조색은 그대로)."""
        muted, ink = QColor(self._PB_MUTED).name(), QColor(INK_ON_LIGHT).name()
        for it in items:
            if not hasattr(it, "defaultTextColor"):
                continue
            c = it.defaultTextColor().name()
            if c == muted:
                it.apply_color(QColor(self._BB_HERO_MUTED))
            elif c == ink:
                it.apply_color(QColor(self._BB_HERO_INK))

    def _bb_face(self, added, start, x, y, w, h, color):
        """채운 패스 면(상자 아님 — 길찾기·「도면 검사」에서 빠짐) — `start`부터 넣은 것 밑에."""
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QBrush, QPainterPath, QPen
        from easycad.canvas.annotator_core import _PathItem
        path = QPainterPath()
        path.addRect(QRectF(0.0, 0.0, w, h))
        face = _PathItem(path)
        face.setPen(QPen(QColor(color), 0.0))
        face.setBrush(QBrush(QColor(color)))
        face.setPos(x, y)
        face.setZValue(-0.5)
        face.setFlags(face.GraphicsItemFlag.ItemIsMovable | face.GraphicsItemFlag.ItemIsSelectable)
        face._pb_part, face._pb_card = self._pb_part_cur, True
        self._scene.addItem(face)
        added.insert(start, face)
        return face

    # ---- 크기 맞추기 · 여러 장 ---------------------------------------------------------------------

    def _bb_fit(self, spec):
        """배치 한 번(+ 세로로 길면 넓혀서 한 번 더) + 채우기 한 번 — 반환 (_bb_layout 결과, 보드 폭).
        채우기: 그림은 자기 칸의 남는 높이만큼(줄 맞춤) 또는 아래가 비면 끝까지(벽돌), 그리고 보드 아래에 남는 높이는 그림 줄이 먹거나(줄 맞춤)
        줄 사이에 고르게. 채운 뒤 보드가 넘치면(소수점 차이 포함) 채우기 전으로 — 실제 KAIROS Sonnet 보드가 이 때문에 한 장에 들 것을 2장으로 갔다."""
        self._bb_fig_extra, self._bb_row_extra = {}, 0.0
        res = self._bb_layout(spec, 1920.0)
        if res[1] * BOARD_ASPECT < 1920.0 * 0.7:
            # 내용이 적으면 보드를 작게(바닥 1280) — 블록 3개로 「보드로 정리」한 보드가 1920폭에서 위만 차고 아래가 텅 비었다(실제 창)
            self._pb_discard(res[4])
            res = self._bb_layout(spec, max(self._BB_MIN_W, res[1] * BOARD_ASPECT * 1.15))
        if res[1] * BOARD_ASPECT > res[0] * 1.05:
            self._pb_discard(res[4])
            res = self._bb_layout(spec, min(res[1] * BOARD_ASPECT * 0.92, self.BOARD_MAX_W))
        if res[1] * BOARD_ASPECT > self.BOARD_MAX_W and res[0] < self.BOARD_MAX_W - 1.0:
            # 그래도 넘치면 폭을 끝(`BOARD_MAX_W`)까지 — 넓으면 글이 덜 접혀 낮아진다(실제 KAIROS Sonnet 보드: 2031폭에서 1.3% 넘침)
            self._pb_discard(res[4])
            res = self._bb_layout(spec, self.BOARD_MAX_W)
        width = res[0]
        bw0 = max(res[0], res[1] * BOARD_ASPECT)
        floor = max(res[1], width / BOARD_ASPECT) - 48.0 - 4.0   # 보드(16:9) 안 내용 아래 끝(4 = 반올림 여유)
        spare = max(0.0, floor - (res[1] - 48.0))               # 보드 아래에 남는 높이
        extra, row_extra, cards_cols = {}, 0.0, {}
        if not self._bb_masonry:   # 줄보다 많이 낮은 카드 블록(4개 이상)은 2열로 — 시안처럼 2×2로 칸을 채운다
            cards_cols = {part: 2 for part, blk, _x, _w, _y, h, _b, room in res[5]
                          if blk["type"] == "cards" and len(blk["items"]) >= 4 and room - h > 80.0}
            cards_room = {part: room for part, blk, _x, _w, _y, h, _b, room in res[5] if blk["type"] == "cards" and room - h > 30.0}
            # 글 높이는 배율의 제곱쯤으로 는다(줄 수 × 줄 높이) — 넘지 않게 제곱근에 여유 0.95
            grow = {part: min(1.25, 0.95 * (room / h) ** 0.5) for part, blk, _x, _w, _y, h, _b, room in res[5]
                    if blk["type"] in self._BB_GROW_TYPES and not blk.get("hero") and h > 0 and room / h > 1.3}
        else:
            cards_room, grow = {}, {}
        figs = [(part, y, h, below, room) for part, blk, _x, _w, y, h, below, room in res[5]
                if blk["type"] == "figure" and not blk.get("_side_h")]   # 옆 칸 그림은 이미 보드 높이만큼
        if self._bb_masonry:
            extra = {part: floor - (y + h) for part, y, h, below, _r in figs if not below and floor - (y + h) > 60.0}
        else:
            extra = {part: room - h for part, y, h, below, room in figs if room - h > 30.0}
            if figs and spare > 30.0:   # 남는 높이는 마지막 그림이 먹는다(그 줄이 커지는 만큼만 보드 안)
                part = figs[-1][0]
                extra[part] = extra.get(part, 0.0) + spare
            elif spare > 30.0:
                rows = len({y for _p, _b, _x, _w, y, *_r in res[5]})
                row_extra = min(48.0, spare / max(1, rows - 1)) if rows > 1 else 0.0   # 줄 사이는 조금만(다 주면 블록이 흩어짐)
        if extra or row_extra or cards_cols or cards_room or grow:
            self._pb_discard(res[4])
            self._bb_fig_extra, self._bb_row_extra, self._bb_cards_cols, self._bb_cards_room, self._bb_grow =                 extra, row_extra, cards_cols, cards_room, grow
            res2 = self._bb_layout(spec, width)
            self._bb_fig_extra, self._bb_row_extra, self._bb_cards_cols, self._bb_cards_room, self._bb_grow = {}, 0.0, {}, {}, {}
            # 채운 뒤에도 한 장(`BOARD_MAX_W`) 안이면 받는다 — 이미 넘치던 보드는 더 커지지 않을 때만
            if max(res2[0], res2[1] * BOARD_ASPECT) <= (self.BOARD_MAX_W if bw0 <= self.BOARD_MAX_W else bw0) + 0.5:
                res = res2
            else:   # 채우다 넘쳤다 — 채우기 전으로
                self._pb_discard(res2[4])
                res = self._bb_layout(spec, width)
        return res, max(res[0], res[1] * BOARD_ASPECT)

    def _bb_fit_steps(self, spec):
        """`_bb_fit`을 조이는 차례(`_BB_FIT_STEPS`)로 — 1장 폭(`BOARD_MAX_W`)에 처음 들어가는 것. 다 넘치면 첫 단계(장을 나눌 때는
        조이지 않은 크기로 — 넘쳐서 어차피 나눌 거면 글을 줄일 까닭이 없다)."""
        for masonry in (False, True):   # 줄 맞춤으로 모든 단계를 먼저, 안 되면 벽돌 쌓기로
            self._bb_masonry = masonry
            for step in self._BB_FIT_STEPS:
                self._bb_k, self._bb_figk, self._bb_tight = step
                res, bw = self._bb_fit(spec)
                if bw <= self.BOARD_MAX_W:
                    self._bb_masonry = False
                    return res, bw
                self._pb_discard(res[4])
        self._bb_masonry = False
        self._bb_k, self._bb_figk, self._bb_tight = self._BB_FIT_STEPS[0]
        return self._bb_fit(spec)

    def _build_block_board(self, spec, center=None, bg=None):
        """블록 설계서 → 보드(넘치면 2장) + 블록들(한 번의 되돌리기). 반환 모양은 흐름도와 같다."""
        import uuid
        blocks = [dict(b, _i=i) for i, b in enumerate(spec["blocks"])]
        self._bb_k, self._bb_figk, self._bb_tight = self._BB_FIT_STEPS[0]
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
            base = spec if k == 1 else dict(spec, subtitle="", highlight="", headline="",
                                            meta=(spec.get("meta") + " · " if spec.get("meta") else "") + f"{k}장 · 자세히")
            moved: list = []   # 다음 장(또는 생략)으로 보낸 블록(뒤쪽 줄부터)
            while True:
                s1 = dict(base, blocks=[b for b in rest if b["_i"] not in {m["_i"] for m in moved}])
                if moved:
                    names = " · ".join(block_label(b) for b in moved)
                    s1["_note"] = f"생략(한 장으로): {names}" if one else f"→ {k + 1}장에 이어서: {names}"
                res, bw = self._bb_fit_steps(s1)
                rows = self._bb_rows(s1, (bw - 2 * self._BB_M - 11 * self._BB_G) / 12.0)   # 나눌 자리만 보므로 간격은 기본으로
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
        self._bb_k, self._bb_figk, self._bb_tight = self._BB_FIT_STEPS[0]
        self.push_undo_add_many(added)
        self._scene.clearSelection()
        return n_steps, n_arrows, "board", added
