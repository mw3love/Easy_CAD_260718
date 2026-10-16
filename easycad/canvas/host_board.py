"""CanvasWindow 믹스인 — 보드 틀(§8 항목53 1단계, 2026-10-16 Magic Board 「논문 한 장 보드」의 바탕).

보드는 작업영역 안의 16:9 틀(`core_shapes._BoardItem`). 소속은 위치로 정하고(가운데가 안에 있으면 그 보드), 보드를 끌면
그 순간 안에 있던 것이 같이 움직인다(`_BoardItem.itemChange`). 이 믹스인이 맡는 것:
- 「삽입 › 보드」 — 화면 가운데에 흰 보드.
- **잉크 맞추기** — 보드 위에 놓이거나 옮겨진 아이템의 잉크(흰색/검정에 가까운 선·글자 색)를 보드 바탕 밝기에 맞춘다.
  다크 화면의 기본 잉크는 흰색이라 흰 보드 위에 그리면 안 보인다. 되돌리기 기록 한 칸 안에 같이 실어(`_push_entry` 길목)
  Ctrl+Z 한 번에 함께 돌아간다. 다른 색(띠 색·강조 코랄 등)은 뜻이 있는 색이라 건드리지 않는다.
- 「보드 색」(우클릭) — 화이트·블랙·견본 8(계획서 §8 항목53, 사용자 확정)·직접 고르기. 바꾸면 안의 잉크도 같이.
출력은 늘 흰 종이: `pdf_export._swap_white_to_black_for_print`가 보드 바탕을 잠깐 흰색으로 바꾸고, 밝은 잉크(#fafafa)는
같은 함수의 "흰 잉크 → 검정" 규칙에 걸린다.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QMenu

from easycad.canvas.annotator_core import _BoardItem, _TitleBlockItem, BOARD_ASPECT, BOARD_W

# 보드 색 — 화이트(기본)·블랙 + 「다른 색 ▾」 견본 8(밝은 4 · 어두운 4, 시안 2차에서 사용자가 고른 원칙대로)
BOARD_COLORS = (("화이트", "#ffffff"), ("블랙", "#1d1d1f"))
BOARD_SWATCHES = (("밝은 미색", "#f4eedf"), ("하늘", "#dde9f3"), ("민트", "#dcece3"), ("라벤더", "#e7e2f0"),
                  ("어두운 칠판", "#24382f"), ("남색", "#1e2b45"), ("와인", "#3b2333"), ("진청록", "#173c40"))
INK_ON_LIGHT = "#1f1f1f"
INK_ON_DARK = "#fafafa"     # 인쇄 때 "흰 잉크 → 검정"(`_is_near_white` ≥250)에 걸리는 밝기


def _is_ink(c: QColor) -> bool:
    """흰색이나 검정에 가까운 "잉크" 색인가(뜻 있는 색은 아님)."""
    if c is None or c.alpha() < 60:
        return False
    hi, lo = max(c.red(), c.green(), c.blue()), min(c.red(), c.green(), c.blue())
    return hi - lo < 24 and (lo >= 215 or hi <= 60)


def _ink_of(it):
    col = getattr(it, "_color", None)
    if col is not None:
        return QColor(col)
    if hasattr(it, "defaultTextColor"):
        return it.defaultTextColor()
    if hasattr(it, "pen"):
        return it.pen().color()
    return None


class _BoardMixin:

    # ---- 넣기 ------------------------------------------------------------------------------

    def _insert_board(self):
        """「삽입 › 보드」 — 화면 가운데에 흰 16:9 보드(되돌리기 한 칸). 그린 도형들 뒤, 용지틀(-1000) 앞."""
        w, h = BOARD_W, BOARD_W / BOARD_ASPECT
        board = _BoardItem(QRectF(0.0, 0.0, w, h), QColor(BOARD_COLORS[0][1]))
        center = self._view.mapToScene(self._view.viewport().rect().center())
        board.setPos(center.x() - w / 2.0, center.y() - h / 2.0)
        zs = [it.zValue() for it in self._scene.items()
              if it.parentItem() is None and not isinstance(it, (_TitleBlockItem, _BoardItem))]
        board.setZValue(max(-999.0, min(zs, default=0.0) - 1.0))
        board.setFlags(board.GraphicsItemFlag.ItemIsMovable | board.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(board)
        self._scene.clearSelection()
        board.setSelected(True)
        self.push_undo_add(board)
        self.set_tool("select")
        # 처음 보면 화면을 꽉 채워 틀 가장자리가 안 보였다(실제 창 캡처) — 양옆 카드 사이에 다 들어오게 필요한 만큼만 축소.
        self._ai_ensure_visible(self._view, board.mapRectToScene(board.rect()))
        self.statusBar().showMessage("보드를 넣었어요 — 보드를 끌면 안의 것도 같이 움직여요. 색은 우클릭 「보드 색」", 5000)
        return board

    # ---- 잉크 맞추기 -------------------------------------------------------------------------

    def _board_at(self, it):
        """아이템 가운데가 들어 있는 보드(겹치면 위에 있는 것). 없으면 None."""
        cr = it._content_rect() if hasattr(it, "_content_rect") else it.boundingRect()
        p = it.mapRectToScene(cr).center()
        best = None
        for b in self._scene.items():
            if isinstance(b, _BoardItem) and b is not it and b.mapRectToScene(b.rect()).contains(p):
                if best is None or b.zValue() > best.zValue():
                    best = b
        return best

    def _board_ink_ops(self, ops) -> list:
        """`_push_entry` 길목 — 이번에 생기거나 옮겨진 아이템 중 보드 위에서 안 보이는 잉크를 고친 "state" 변이 목록.
        보드가 생기거나 옮겨졌으면 그 안의 것 전부를 본다."""
        if not any(isinstance(it, _BoardItem) for it in self._scene.items()):
            return []
        seen, cands = set(), []
        for o in ops:
            if o[0] == "create" or (o[0] == "mut" and o[2] in ("pos", "geom")):
                it = o[1]
                if isinstance(it, _BoardItem):
                    cands += [m for m in self._scene.items() if m.parentItem() is None and self._board_at(m) is it]
                else:
                    cands.append(it)
        out = []
        for it in cands:
            if id(it) in seen or it.scene() is not self._scene or it.parentItem() is not None \
                    or isinstance(it, (_BoardItem, _TitleBlockItem)):
                continue
            seen.add(id(it))
            board = self._board_at(it)
            if board is not None:
                out += self._ink_fix_ops(it, board.is_dark())
        return out

    def _ink_fix_ops(self, it, dark: bool) -> list:
        """`it`과 그 안 글자(라벨)의 잉크를 바탕 밝기에 맞춘다 — 이미 맞으면 빈 목록."""
        want = QColor(INK_ON_DARK if dark else INK_ON_LIGHT)
        out = []
        for x in [it] + [c for c in it.childItems() if hasattr(c, "toPlainText") and hasattr(c, "apply_color")]:
            if not hasattr(x, "apply_color") or not hasattr(x, "capture_state"):
                continue
            c = _ink_of(x)
            if not _is_ink(c):
                continue
            light = c.lightness() >= 128
            if light == dark:   # 어두운 바탕에 밝은 잉크 / 밝은 바탕에 어두운 잉크 — 그대로 둔다
                continue
            before = x.capture_state()
            x.apply_color(want)
            out.append(("mut", x, "state", before, x.capture_state()))
        return out

    # ---- 보드 색 --------------------------------------------------------------------------------

    def _build_board_color_menu(self, board, parent=None):
        menu = QMenu("보드 색", parent)
        for name, hexv in BOARD_COLORS:
            menu.addAction(name, lambda h=hexv: self._set_board_color(board, h))
        sub = menu.addMenu("다른 색")
        for name, hexv in BOARD_SWATCHES:
            sub.addAction(name, lambda h=hexv: self._set_board_color(board, h))
        sub.addSeparator()
        sub.addAction("직접 고르기…", lambda: self._pick_board_color(board))
        return menu

    def _pick_board_color(self, board):
        c = QColorDialog.getColor(board.bg(), self, "보드 색")
        if c.isValid():
            self._set_board_color(board, c.name())

    def _set_board_color(self, board, color):
        """보드 바탕색을 바꾸고 안 잉크를 새 밝기에 맞춘다(되돌리기 한 칸)."""
        if board.scene() is not self._scene:
            return
        before = board.capture_state()
        board.apply_color(QColor(color))
        ops = [("mut", board, "state", before, board.capture_state())]
        for it in self._scene.items():
            if it.parentItem() is None and not isinstance(it, (_BoardItem, _TitleBlockItem)) and self._board_at(it) is board:
                ops += self._ink_fix_ops(it, board.is_dark())
        self._push_entry(ops)
        board.update()

    # ---- 논문 한 장 보드(§8 항목53 2단계) ------------------------------------------------------------
    # 시안 ④(Artifact 81avA5GPjgcGjdaLsbcbQR `project/Board.dc.html`)의 세 줄: 위 = 제목·한 줄 요약 | 세 줄 요약,
    # 가운데 = 핵심 개념 | 어떻게 작동하나(52 흐름도) | 결과(막대·숫자 카드), 아래 = 논문 속 그림 | 용어 풀이 | 의의와 한계.
    # 크기는 1920×1080 기준(시안과 같은 px), 흐름도가 크면 가운데 칸이 넓어지고 보드를 16:9로 맞춰 키운다(줄이기·장 나누기는 4단계).
    # 색은 역할마다 하나 — 잉크(#1f1f1f, 어두운 보드면 잉크 맞추기가 밝게)·흐린 글(쪽 번호)·코랄(강조)·회색 알파 카드.
    _PB_M, _PB_GAP = 64.0, 48.0
    _PB_MUTED = "#6b7a8f"
    _PB_TAG = {"의의": "#2a9fb0", "한계": "#c9a227", "outside": "#8a6fd1"}
    _PB_CARD = QColor(128, 128, 128, 26)
    _PB_EDGE = QColor(128, 128, 128, 80)

    def _pb_text(self, added, text, x, y, w, pt, color=INK_ON_LIGHT):
        """글 하나(_TextItem) — 폭 `w`에 맞춰 줄을 나눠 넣는다(줄바꿈은 글에 직접 — 저장해도 그대로). 반환 (아이템, 높이)."""
        from PyQt6.QtGui import QFontMetricsF
        from easycad.canvas.annotator_core import _TextItem
        t = _TextItem(QColor(color))
        t.apply_font_size(pt)
        fm = QFontMetricsF(t.font())
        room = max(10.0, w - 2 * t.document().documentMargin())
        t.setPlainText(_wrap(text, fm, room))
        t.setPos(x, y)
        t.setFlags(t.GraphicsItemFlag.ItemIsMovable | t.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(t)
        added.append(t)
        return t, t.boundingRect().height()

    def _pb_card(self, added, x, y, w, h, fill=None, edge=None, width=1.0):
        from PyQt6.QtGui import QBrush, QPen
        from easycad.canvas.annotator_core import _RectItem
        r = _RectItem(QRectF(0.0, 0.0, w, h))
        r.setPen(QPen(QColor(edge) if edge is not None else self._PB_EDGE, width))
        r.setBrush(QBrush(QColor(fill) if fill is not None else self._PB_CARD))
        r.setPos(x, y)
        r.setFlags(r.GraphicsItemFlag.ItemIsMovable | r.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(r)
        added.append(r)
        return r

    def _pb_card_under(self, added, start, x, y, w, h):
        """`start`부터 넣은 글들 밑에 카드 — 목록에서도 글 앞으로(먼저 = 아래)."""
        card = self._pb_card(added, x, y, w, h)
        card.setZValue(-0.5)
        added.insert(start, added.pop())
        return card

    def _pb_heading(self, added, title, pages, x, y, w):
        """칸 제목 + 오른쪽 쪽 번호. 반환 높이."""
        _t, h = self._pb_text(added, title, x, y, w, 13)
        if pages:
            tag, _h = self._pb_text(added, pages, x, y + 3, w, 9, self._PB_MUTED)
            tag.setPos(x + w - tag.boundingRect().width(), y + 3)
        return h

    def _pb_figure_pixmap(self, pdf_path, page_no):
        """논문 그림 — 그 쪽에서 가장 큰 그림 자리를 잘라(없으면 쪽 전체) 그림으로. 못 읽으면 None."""
        try:
            import fitz
            from PyQt6.QtGui import QImage, QPixmap
            with fitz.open(pdf_path) as doc:
                if not (1 <= page_no <= doc.page_count):
                    return None
                page = doc[page_no - 1]
                area = page.rect.width * page.rect.height
                boxes = [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
                boxes = [b for b in boxes if b.width * b.height > area * 0.04]
                clip = max(boxes, key=lambda b: b.width * b.height) if boxes else page.rect
                pix = page.get_pixmap(clip=clip, dpi=150, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                return QPixmap.fromImage(img)
        except Exception:   # noqa: BLE001 — 그림을 못 얻으면 자리 표시만
            return None

    def _pb_mark(self, added, text_item, phrase):
        """한 줄 요약 안의 가장 중요한 구절 밑에 코랄 형광펜(옅은 사각형) — 강조는 보드에 하나(시안 ④)."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QBrush, QFontMetricsF, QPen
        from easycad.canvas.annotator_core import _RectItem
        fm = QFontMetricsF(text_item.font())
        margin = text_item.document().documentMargin()
        for i, ln in enumerate(text_item.toPlainText().split("\n")):
            k = ln.find(phrase)
            if k < 0:
                continue
            x = text_item.pos().x() + margin + fm.horizontalAdvance(ln[:k])
            y = text_item.pos().y() + margin + i * fm.lineSpacing() + fm.ascent() * 0.55
            mark = _RectItem(QRectF(0.0, 0.0, fm.horizontalAdvance(phrase), fm.lineSpacing() * 0.5))
            c = QColor(_ACCENT)
            c.setAlpha(80)
            mark.setPen(QPen(Qt.PenStyle.NoPen))
            mark.setBrush(QBrush(c))
            mark.setPos(x, y)
            mark.setZValue(-0.4)
            mark.setFlags(mark.GraphicsItemFlag.ItemIsMovable | mark.GraphicsItemFlag.ItemIsSelectable)
            self._scene.addItem(mark)
            added.append(mark)
            return mark
        return None

    def _build_paper_board(self, text, center=None):
        """보드 설계서 → 보드 틀 + 칸들(한 번의 되돌리기). 반환 모양은 흐름도와 같다: (단계 수, 화살표 수, "board", 넣은 아이템).
        내용이 세로로 길어 16:9 보드가 옆으로 넓어지면, 넓어진 만큼 칸들을 넓혀 한 번 더 배치한다(첫 시도는 양옆이 비었다 — 실제 창)."""
        from easycad.ai.pdf_to_board import parse_board
        spec = parse_board(text)
        res = self._pb_layout(spec, None)
        need_w, need_h = res[0], res[1]
        if need_h * BOARD_ASPECT > need_w * 1.05:
            for it in res[4]:
                if it.scene() is not None:
                    self._scene.removeItem(it)
            res = self._pb_layout(spec, need_h * BOARD_ASPECT * 0.92)
        return self._pb_place(*res, center)

    def _pb_layout(self, spec, want_w):
        """칸 배치 한 번(보드 왼쪽 위 (0,0) 기준) — 반환 (필요 폭, 필요 높이, 단계 수, 화살표 수, 넣은 아이템). `want_w`가 있으면
        그 폭에 맞춰 칸들을 고르게 넓힌다."""
        import json
        from PyQt6.QtCore import QPointF
        from easycad.canvas.annotator_core import _ImageItem
        M, G = self._PB_M, self._PB_GAP
        added: list = []

        # 흐름도 크기 먼저(가운데 칸 폭이 정해진다) — 멀리서 한 번 그려 재고 지운다(배치가 결정적이라 다시 그려도 같다).
        flow_json, flow_w, flow_h = "", 0.0, 0.0
        if spec.get("flow"):
            f = dict(spec["flow"])
            f.pop("pages", None)
            f["title"] = ""
            flow_json = json.dumps(f, ensure_ascii=False)
            _n, _a, _d, probe = self._build_flowspec_items(flow_json, QPointF(-1e6, -1e6), push_undo=False, compact=True)
            box = self._ai_items_rect([it for it in probe if not hasattr(it, "build_elbow")])   # 화살표 영역 캐시는 믿지 않음(아래 주석)
            flow_w, flow_h = box.width(), box.height()
            for it in probe:
                if it.scene() is not None:
                    self._scene.removeItem(it)
        k = 1.0
        if want_w:   # 칸 폭을 같은 비율로(가운데 칸은 흐름도보다 좁아지지 않게)
            k = max(1.0, (want_w - 2 * M - 2 * G - max(600.0, flow_w)) / (420.0 + 600.0))
        concept_w, result_w = 420.0 * k, 600.0 * k
        mid_w = max(600.0 * k, flow_w)
        content_w = max(1920.0 - 2 * M, concept_w + mid_w + result_w + 2 * G, (want_w or 0) - 2 * M)
        mid_w = content_w - concept_w - result_w - 2 * G   # 남는 폭은 가운데 칸에

        # 좌표는 보드 왼쪽 위(0,0) 기준으로 놓고, 마지막에 보드와 함께 옮긴다.
        x0 = M
        # ── 위: 제목 · 한 줄 요약 | 세 줄 요약
        side_w = 560.0 * k
        right_x = x0 + content_w - side_w
        left_w = right_x - G - x0
        y = 48.0
        _t, h = self._pb_text(added, "논문 한 장 정리 · Magic Board", x0, y, left_w, 9, self._PB_MUTED)
        y += h
        _t, h = self._pb_text(added, spec["title"] or "(제목 없음)", x0, y, left_w, 22)
        y += h
        if spec["meta"]:
            _t, h = self._pb_text(added, spec["meta"], x0, y, left_w, 10, self._PB_MUTED)
            y += h
        y += 10
        if spec["one_line"]:
            one, h = self._pb_text(added, spec["one_line"], x0, y, left_w, 15)
            if spec["highlight"]:
                self._pb_mark(added, one, spec["highlight"])
            y += h
        left_bottom = y
        ry = 48.0
        if spec["three_lines"]:
            start = len(added)
            yy = ry + 12 + self._pb_heading(added, "세 줄 요약", "", right_x + 16, ry + 12, side_w - 32) + 4
            for i, row in enumerate(spec["three_lines"]):   # 쪽 번호는 줄 오른쪽에(따로 한 줄을 쓰면 보드가 길어짐)
                _t, h = self._pb_text(added, f"{'①②③'[i]} {row['text']}", right_x + 16, yy, side_w - 32 - 72, 11)
                if row["pages"]:
                    tag, _h = self._pb_text(added, row["pages"], right_x, yy + 3, 72, 9, self._PB_MUTED)
                    tag.setPos(right_x + side_w - 16 - tag.boundingRect().width(), yy + 3)
                yy += h + 4
            self._pb_card_under(added, start, right_x, ry, side_w, yy - ry + 8)
            ry = yy + 8
        top = max(left_bottom, ry) + 32.0

        # ── 가운데: 핵심 개념 | 어떻게 작동하나 | 결과
        cx, fx, rx = x0, x0 + concept_w + G, x0 + concept_w + G + mid_w + G
        cy = top
        if spec["concepts"]:
            cy = top + self._pb_heading(added, f"핵심 개념 {len(spec['concepts'])}가지", "", cx, top, concept_w) + 8
        for c in spec["concepts"]:
            start = len(added)
            _t, h1 = self._pb_text(added, c["name"], cx + 14, cy + 10, concept_w - 28, 12)
            if c["pages"]:
                tag, _h = self._pb_text(added, c["pages"], cx, cy + 13, concept_w - 14, 9, self._PB_MUTED)
                tag.setPos(cx + concept_w - 14 - tag.boundingRect().width(), cy + 13)
            _t, h2 = self._pb_text(added, c["body"], cx + 14, cy + 10 + h1, concept_w - 28, 10)
            self._pb_card_under(added, start, cx, cy, concept_w, h1 + h2 + 22)
            cy += h1 + h2 + 22 + 12
        fy = top
        n_steps = n_arrows = 0
        if flow_json:
            fy = top + self._pb_heading(added, spec["flow"].get("title") or "어떻게 작동하나",
                                        spec["flow"].get("pages", ""), fx, top, mid_w) + 8
            n_steps, n_arrows, _d, flow_items = self._build_flowspec_items(
                flow_json, QPointF(fx + mid_w / 2.0, fy + flow_h / 2.0), push_undo=False, compact=True)
            added += flow_items
            fy += flow_h
        res = spec["results"]
        ryy = top
        if res["bars"] or spec["numbers"]:
            ryy = top + self._pb_heading(added, "결과", res["pages"], rx, top, result_w) + 8
        if res["bars"]:
            start = len(added)
            yy = ryy + 12
            if res["title"]:
                _t, h = self._pb_text(added, res["title"], rx + 16, yy, result_w - 32, 10)
                yy += h + 4
            vmax = max(b["value"] for b in res["bars"]) or 1.0
            label_w, val_w = 170.0 * k, 64.0
            bar_room = result_w - 32 - label_w - val_w
            for b in res["bars"]:
                _t, h = self._pb_text(added, b["label"], rx + 16, yy, label_w, 10)
                bw = max(2.0, bar_room * max(0.0, b["value"]) / vmax)   # 막대는 0부터(시안 ④)
                col = _ACCENT if b["mine"] else self._PB_MUTED
                self._pb_card(added, rx + 16 + label_w, yy + 6, bw, 16.0, fill=col, edge=col)
                self._pb_text(added, f"{b['value']:g}", rx + 16 + label_w + bw + 6, yy, val_w, 10)
                yy += max(h, 28.0)
            if res["note"]:
                _t, h = self._pb_text(added, res["note"], rx + 16, yy + 2, result_w - 32, 9, self._PB_MUTED)
                yy += h + 2
            self._pb_card_under(added, start, rx, ryy, result_w, yy - ryy + 10)
            ryy = yy + 10 + 16
        if spec["numbers"]:
            nw = (result_w - 16 * (len(spec["numbers"]) - 1)) / len(spec["numbers"])
            hs = []
            for i, num in enumerate(spec["numbers"]):
                nx = rx + i * (nw + 16)
                start = len(added)
                _t, h1 = self._pb_text(added, num["label"], nx + 14, ryy + 10, nw - 28, 10)
                _t, h2 = self._pb_text(added, num["value"], nx + 14, ryy + 10 + h1, nw - 28, 24, _ACCENT)
                _t, h3 = self._pb_text(added, " · ".join(p for p in (num["note"], num["pages"]) if p),
                                       nx + 14, ryy + 10 + h1 + h2, nw - 28, 9, self._PB_MUTED)
                hs.append((start, nx, h1 + h2 + h3 + 20))
            hmax = max(h for _s, _x, h in hs)
            for start, nx, _h in reversed(hs):
                self._pb_card_under(added, start, nx, ryy, nw, hmax)
            ryy += hmax
        y = max(cy, fy, ryy) + 40.0

        # ── 아래: 논문 속 그림 | 용어 풀이 | 의의와 한계
        bw1 = bw2 = 560.0 * k
        bw3 = content_w - bw1 - bw2 - 2 * G
        bx1, bx2, bx3 = x0, x0 + bw1 + G, x0 + bw1 + G + bw2 + G
        bottom = y
        fig = spec.get("figure")
        if fig:
            fy2 = y + self._pb_heading(added, "논문 속 그림", f"p.{fig['page']}", bx1, y, bw1) + 6
            if fig["caption"]:
                _t, h = self._pb_text(added, fig["caption"], bx1, fy2, bw1, 10, self._PB_MUTED)
                fy2 += h + 4
            pm = self._pb_figure_pixmap(spec.get("_pdf", ""), fig["page"]) if spec.get("_pdf") else None
            if pm is not None and not pm.isNull():
                k = min(bw1 / pm.width(), 240.0 / pm.height())   # 세로로 긴 그림이 아래 줄(보드)을 늘리지 않게
                img = _ImageItem(pm, QRectF(0.0, 0.0, pm.width() * k, pm.height() * k))
                img.setPos(bx1, fy2)
                img.setFlags(img.GraphicsItemFlag.ItemIsMovable | img.GraphicsItemFlag.ItemIsSelectable)
                self._scene.addItem(img)
                added.append(img)
                fy2 += pm.height() * k
            else:
                _t, h = self._pb_text(added, f"[논문 그림 자리 — 원문 p.{fig['page']}]", bx1, fy2, bw1, 10,
                                      self._PB_MUTED)
                fy2 += h
            bottom = max(bottom, fy2)
        if spec["terms"]:
            ty = y + self._pb_heading(added, "용어 풀이", "", bx2, y, bw2) + 6
            for t in spec["terms"]:
                _t, h = self._pb_text(added, f"{t['term']} — {t['meaning']}", bx2, ty, bw2, 10)
                ty += h + 2
            bottom = max(bottom, ty)
        if spec["verdict"]:
            vy = y + self._pb_heading(added, "의의와 한계", "", bx3, y, bw3) + 6
            for v in spec["verdict"]:
                tag = "논문 밖 맥락" if v["outside"] else v["type"]
                col = self._PB_TAG["outside"] if v["outside"] else self._PB_TAG[v["type"]]
                tg, _h = self._pb_text(added, tag, bx3, vy + 2, 120, 9, col)
                tw = tg.boundingRect().width()
                body = v["text"] + (f"  ({v['pages']})" if v["pages"] and not v["outside"] else "")
                _t, h = self._pb_text(added, body, bx3 + tw + 2, vy, bw3 - tw - 2, 10)
                vy += max(h, 20.0) + 2
            bottom = max(bottom, vy)

        return content_w + 2 * M, bottom + 48.0, n_steps, n_arrows, added

    def _pb_place(self, need_w, need_h, n_steps, n_arrows, added, center):
        """보드 틀(16:9)을 만들고 칸들을 보드 가운데로 옮겨 한 번의 되돌리기로 기록."""
        bw = max(need_w, need_h * BOARD_ASPECT)
        bh = bw / BOARD_ASPECT
        if center is None:
            center = self._view.mapToScene(self._view.viewport().rect().center())
        ox, oy = center.x() - bw / 2.0, center.y() - bh / 2.0
        zs = [it.zValue() for it in self._scene.items()
              if it.parentItem() is None and not isinstance(it, (_TitleBlockItem, _BoardItem)) and it not in added]
        board = _BoardItem(QRectF(0.0, 0.0, bw, bh), QColor(BOARD_COLORS[0][1]))
        board.setPos(ox, oy)
        board.setZValue(max(-999.0, min(zs + [it.zValue() for it in added], default=0.0) - 2.0))
        board.setFlags(board.GraphicsItemFlag.ItemIsMovable | board.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(board)
        dx = ox + (bw - need_w) / 2.0
        for it in added:   # 끝이 상자에 붙은 화살표는 상자를 따라 다시 그려진다 — 나머지만 옮긴다
            if not any(getattr(it, n, None) is not None for n in ("_bind_start", "_bind_end")):
                it.moveBy(dx, oy)
        for it in added:
            if hasattr(it, "reroute"):
                # 붙은 상자를 옮긴 뒤엔 `reroute`(끝점을 상자 따라 옮기고 길 다시 찾기) — `build_elbow`만 부르면 끝점이 옛 자리라
                # 화살표가 옮기기 전 자리에 남았다(실측: 화면 갱신 뒤에야 따라옴 → 임시 결과 점선·검사가 엉뚱하게 잼).
                try:
                    it.reroute()
                except Exception:   # noqa: BLE001
                    pass
                it._sync_label()
        added.insert(0, board)
        self.push_undo_add_many(added)
        self._scene.clearSelection()
        return n_steps, n_arrows, "board", added


_ACCENT = "#da7756"


def _wrap(text: str, fm, width: float) -> str:
    """폭에 맞춰 줄을 나눈다 — 띄어쓰기에서, 한 낱말이 폭보다 길면 글자 단위로. 이미 있는 줄바꿈은 지킨다."""
    out = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split(" "):
            cand = word if not line else line + " " + word
            if fm.horizontalAdvance(cand) <= width:
                line = cand
                continue
            if line:
                out.append(line)
            line = ""
            while fm.horizontalAdvance(word) > width and len(word) > 1:
                k = len(word)
                while k > 1 and fm.horizontalAdvance(word[:k]) > width:
                    k -= 1
                out.append(word[:k])
                word = word[k:]
            line = word
        out.append(line)
    return "\n".join(out)
