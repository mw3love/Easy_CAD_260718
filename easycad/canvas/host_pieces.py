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

from easycad.canvas.annotator_core import _BoardItem
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
        for i, blk in enumerate(blocks):
            c = min(range(self._PC_COLS), key=lambda k: tops[k])
            x, y = x0 + c * (self._PC_W + self._PC_GAP), tops[c]
            self._pb_part_cur = f"more[{i}]"
            start = len(added)
            h, _ns, _na = self._bb_block(added, spec, dict(blk, hero=False), x + self._PC_PAD, y + self._PC_PAD,
                                         self._PC_W - 2 * self._PC_PAD)
            # 종이색 틀(포스트잇) — 조각은 보드 밖 캔버스 위라 어두운 테마에서 검정 글이 안 보였다(실제 창). 흰색에 가까운
            # 무채색은 인쇄 때 흰→검정 바꾸기에 걸리므로 살짝 미색.
            frame = self._pb_card_under(added, start, x, y, self._PC_W, h + 2 * self._PC_PAD,
                                        fill=self._PC_PAPER, edge=self._PB_EDGE)
            piece = {k: v for k, v in blk.items() if k not in ("row", "span", "_i")}
            frame._pb_piece = json.dumps(piece, ensure_ascii=False)
            gid = uuid.uuid4().hex[:8]
            for it in added[start:]:
                it._group_id = gid
                it._pb_part = None   # 조각은 보드의 설계서 자리가 아니다
            tops[c] = y + h + 2 * self._PC_PAD + self._PC_GAP
        self._pb_part_cur = None
        if push:
            self.push_undo_add_many(added)
        return added

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
        bar.label, bar.go_btn = label, go
        bar.adjustSize()
        return bar
