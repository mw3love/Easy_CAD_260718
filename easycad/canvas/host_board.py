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
