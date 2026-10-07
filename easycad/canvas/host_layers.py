"""CanvasWindow 믹스인 — 레이어 패널 — 추가/이름변경/삭제/표시·잠금 토글/아이템 소속 동기화.

2026-08-02 host.py(3635줄) 분할분. `class CanvasWindow(...)`이 이 믹스인들을 다중상속해
메서드를 합친다 — 동작·이름 전부 원본과 동일(이동만), annotator_core.py가 이미 쓰는 믹스인
패턴을 host.py에도 적용한 것.
"""
from __future__ import annotations

import uuid

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QToolButton, QLabel, QInputDialog, QHBoxLayout, QMenu, QListWidgetItem,
)

from easycad.canvas.annotator_core import (
    _svg_icon,
)
from easycad.canvas.host_widgets import _style_menu_separators, _current_icon_color

# Mermaid 중립 shape → 우리 아이템. ('rect'|'ellipse'|'symbol', symbol kind|None).
# deep-interview 2026-07-21 확정 매핑. 둥근사각형은 사각형으로(라운딩 손실), 미인식은 사각형 폴백.
_MERMAID_SHAPE_ITEM = {
    "rect":          ("rect", None),
    "rounded":       ("rect", None),
    "stadium":       ("symbol", "terminal"),
    "rhombus":       ("symbol", "decision"),
    "hexagon":       ("symbol", "prep"),
    "parallelogram": ("symbol", "data"),
    "cylinder":      ("symbol", "database"),
    "circle":        ("ellipse", None),
}


# [Phase 6 M3 #17] 팔레트 드래그앤드롭 — 좌측 「도형·심볼」 버튼을 캔버스로 끌어 드롭.
_PALETTE_MIME = "application/x-easycad-tool"      # QDrag가 실어 나르는 tool_key 포맷
_PALETTE_DROP_WH = {"rect": (120.0, 72.0), "ellipse": (100.0, 100.0)}  # 기본 생성 크기
_PALETTE_SYM_WH = (120.0, 72.0)                   # 심볼(sym:*) 공통 기본 크기




# [첫 화면 재디자인 2026-10-07, 시안 4라운드 L2] 레이어 색 점 — 구분 표시용(.ecad에만 저장, 도형 색은
# 안 바꿈). DXF는 도형 종류별 레이어(EC_*)라 앱 레이어가 안 나간다 — 연동은 계획서 별도 항목.
# 첫 색(기본 레이어)은 두 테마 모두에서 보이는 중립 회색.
_LAYER_COLORS = ["#8a98a8", "#5aa9ff", "#e8c15a", "#5fbf8a", "#e0646a", "#b48cf2", "#da7756", "#4fd1e0"]


def _layer_dot_icon(color: str, px: int = 12) -> QIcon:
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, px - 2, px - 2)
    p.end()
    return QIcon(pm)


class _LayerRow(QWidget):
    """레이어 한 줄 — 빈 곳(이름·개수 포함)을 누르면 「그리는 중」으로. 색 점·눈·자물쇠는 각자 버튼이라
    클릭을 먹고 여기까지 안 온다(QLabel은 누름을 받지 않아 부모로 넘긴다)."""

    def __init__(self, on_click):
        super().__init__()
        self._on_click = on_click
        self.setObjectName("layerRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(e)


class _LayersMixin:
    def _item_layer_id(self, it) -> str:
        return getattr(it, "_layer_id", None) or "default"


    def _layer_by_id(self, layer_id):
        return next((ly for ly in self._layers if ly["id"] == layer_id), None)


    def _items_in_layer(self, layer_id):
        return [it for it in self._zorder_pool() if self._item_layer_id(it) == layer_id]


    def _refresh_layers_panel(self):
        lst = self._layers_list
        lst.clear()
        for layer in self._layers:
            row = self._make_layer_row(layer)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            lst.addItem(item)
            lst.setItemWidget(item, row)
        # [캔버스-퍼스트] QListWidget의 기본 sizeHint는 항목 수와 무관하게 넓은 고정값(256×192)
        # 이라 플로팅 카드가 콘텐츠보다 훨씬 커진다 — 실제 행 높이 합으로 클램프해야 낭비
        # 공간이 안 생긴다(옛 dock이 칼럼 전체를 예약해 항목 0개에도 창 높이만큼 비던 문제의
        # 재발 방지). [2026-08-19] 폭은 더 이상 여기서 캡하지 않는다 — 레이어가 좌하단 독립
        # 패널로 분리되며 폭은 도형 패널 폭을 그대로 따라가야 해(`_sync_layers_panel_width`)
        # 고정 상한(200) 대신 그 함수가 매번 정확한 값으로 덮어쓴다.
        total_h = sum(lst.sizeHintForRow(i) for i in range(lst.count())) + 2 * lst.frameWidth() + 4
        lst.setFixedHeight(max(60, min(total_h, 320)))
        if getattr(self, "_layers_panel", None) is not None:
            self._sync_layers_panel_width()
            self._reposition_panels()


    def _make_layer_row(self, layer: dict) -> QWidget:
        """[첫 화면 재디자인 2026-10-07, 시안 4라운드 L2] 색 점 · 이름 · 「그리는 중」 · 개수 · 눈 · 자물쇠.
        줄을 누르면 그 레이어가 「그리는 중」(새 도형이 들어갈 곳)이 된다."""
        lid = layer["id"]
        row = _LayerRow(lambda i=lid: self.set_active_layer(i))
        h = QHBoxLayout(row)
        h.setContentsMargins(6, 3, 4, 3)
        h.setSpacing(6)
        active = lid == self._current_active_layer()
        row._layer_active = active
        self._style_layer_row(row)

        dot = QToolButton()
        dot.setAutoRaise(True)
        dot.setFixedSize(18, 18)
        dot.setIcon(_layer_dot_icon(self._layer_color(layer)))
        dot.setToolTip("레이어 색 바꾸기(구분용 — 도형 색은 그대로)")
        dot.clicked.connect(lambda _c=False, i=lid, b=dot: self._pick_layer_color(i, b))

        vis_btn = QToolButton()
        vis_btn.setCheckable(True)
        vis_btn.setChecked(layer["visible"])
        # [UI 검토 2026-09-25] 컬러 이모지(👁/🔒) → 다른 아이콘과 같은 중립색 SVG(Phosphor).
        # 테마 전환 때 `_refresh_layer_icons`가 `_layer_icon_pair`를 읽어 다시 칠한다.
        vis_btn._layer_icon_pair = ("layer_visible", "layer_hidden")
        self._set_layer_btn_icon(vis_btn)
        vis_btn.setToolTip("레이어 표시/숨김")
        vis_btn.toggled.connect(lambda checked, i=lid: self.set_layer_visible(i, checked))

        lock_btn = QToolButton()
        lock_btn.setCheckable(True)
        lock_btn.setChecked(layer["locked"])
        lock_btn._layer_icon_pair = ("layer_locked", "layer_unlocked")
        self._set_layer_btn_icon(lock_btn)
        lock_btn.setToolTip("레이어 잠금")
        lock_btn.toggled.connect(lambda checked, i=lid: self.set_layer_locked(i, checked))

        count = len(self._items_in_layer(lid))
        name_lbl = QLabel(layer["name"])
        name_lbl.setWordWrap(False)
        tag = QLabel("그리는 중")
        f = tag.font(); f.setPixelSize(11); tag.setFont(f)
        tag.setForegroundRole(QPalette.ColorRole.Link)   # 강조색(코랄) — "지금 활성"이라는 의미 있는 상태
        tag.setVisible(active)
        count_lbl = QLabel(str(count))
        count_lbl.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        # `_update_layer_counts`가 개수 글자만 갱신
        row._layer_name_lbl, row._layer_count_lbl, row._layer_id = name_lbl, count_lbl, lid

        h.addWidget(dot)
        h.addWidget(name_lbl)
        h.addWidget(tag)
        h.addStretch(1)
        h.addWidget(count_lbl)
        h.addWidget(vis_btn)
        h.addWidget(lock_btn)

        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(
            lambda pos, i=lid, r=row: self._show_layer_row_menu(r, i))
        return row


    def _schedule_layer_counts(self):
        """레이어 행의 「이름 (개수)」를 곧 다시 센다(2026-10-01 — 도형을 넣고 지우고 되돌려도
        개수는 레이어 조작 때만 갱신돼 「기본 (0)」에 머물던 문제). undo 기록이 쌓이거나 undo/redo될
        때 불린다. 0.15초 몰아서 한 번 — 드래그처럼 연달아 바뀌어도 한 번만 센다."""
        if not hasattr(self, "_layers_list"):
            return
        t = getattr(self, "_layer_count_timer", None)
        if t is None:
            t = self._layer_count_timer = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(150)
            t.timeout.connect(self._update_layer_counts)
        t.start()

    def _update_layer_counts(self):
        names = {layer["id"]: layer["name"] for layer in self._layers}
        lst = self._layers_list
        for i in range(lst.count()):
            row = lst.itemWidget(lst.item(i))
            lid = getattr(row, "_layer_id", None)
            if lid in names:
                row._layer_count_lbl.setText(str(len(self._items_in_layer(lid))))


    @staticmethod
    def _set_layer_btn_icon(btn: QToolButton) -> None:
        """레이어 표시/잠금 버튼 아이콘 — 체크 상태에 맞는 쪽을 현재 테마 중립색으로."""
        on_name, off_name = btn._layer_icon_pair
        btn.setIcon(_svg_icon(on_name if btn.isChecked() else off_name, 16,
                              _current_icon_color()))


    def _style_layer_row(self, row) -> None:
        """「그리는 중」 줄만 옅은 면. ⚠ `palette(alternate-base)`를 QSS에 쓰면 처음 칠할 때(테마 적용 전,
        라이트 팔레트)의 값으로 굳어 다크에서 흰 띠가 됐다(실측) — 테마별 색을 직접 넣고 테마 전환 때 다시 칠한다."""
        if getattr(row, "_layer_active", False):
            bg = "#2d3640" if getattr(self, "_dark", True) else "#dfe5eb"
            row.setStyleSheet(f"#layerRow {{ background:{bg}; border-radius:4px; }}")
        else:
            row.setStyleSheet("")

    def _refresh_layer_icons(self) -> None:
        """테마 전환 시 레이어 행 아이콘만 다시 칠한다(행 재구성 없이 — `_apply_theme`의
        위젯 재구축 금지 주석 참조)."""
        lst = getattr(self, "_layers_list", None)
        if lst is None:
            return
        for i in range(lst.count()):
            row = lst.itemWidget(lst.item(i))
            if row is not None:
                self._style_layer_row(row)
        for btn in lst.findChildren(QToolButton):
            if hasattr(btn, "_layer_icon_pair"):
                self._set_layer_btn_icon(btn)


    def _show_layer_row_menu(self, row: QWidget, layer_id: str):
        menu = QMenu(self)
        _style_menu_separators(menu)
        menu.addAction("이름 변경...", lambda: self._prompt_rename_layer(layer_id))
        if layer_id != "default":
            menu.addAction("삭제", lambda: self.delete_layer(layer_id))
        menu.exec(row.mapToGlobal(row.rect().center()))


    def _prompt_rename_layer(self, layer_id: str):
        layer = self._layer_by_id(layer_id)
        if layer is None:
            return
        name, ok = QInputDialog.getText(self, "레이어 이름 변경", "이름:", text=layer["name"])
        if ok:
            self.rename_layer(layer_id, name)


    def add_layer(self, name: str | None = None) -> dict:
        name = (name or "").strip() or f"레이어 {len(self._layers) + 1}"
        used = {ly.get("color") for ly in self._layers}
        color = next((c for c in _LAYER_COLORS if c not in used),
                     _LAYER_COLORS[len(self._layers) % len(_LAYER_COLORS)])
        layer = {"id": uuid.uuid4().hex[:8], "name": name, "visible": True, "locked": False,
                 "color": color}
        self._layers.append(layer)
        self._refresh_layers_panel()
        return layer

    # ---- 「그리는 중」 레이어 + 레이어 색 (첫 화면 재디자인 2026-10-07, 사용자 결정) ----
    def _current_active_layer(self) -> str:
        lid = getattr(self, "_active_layer", "default")
        return lid if self._layer_by_id(lid) is not None else "default"

    def set_active_layer(self, layer_id: str):
        layer = self._layer_by_id(layer_id)
        if layer is None or layer_id == self._current_active_layer():
            return
        self._active_layer = layer_id
        self._refresh_layers_panel()
        self.statusBar().showMessage(f'그리는 레이어: {layer["name"]}', 2500)

    def _assign_new_items_to_active_layer(self, ops):
        """`_push_entry`가 부른다 — 새로 생긴 도형(소속 없음)을 「그리는 중」 레이어로. 숨김·잠금
        레이어로는 안 넣는다(그리자마자 사라지거나 못 고치게 되므로 기본 레이어에 남긴다)."""
        lid = self._current_active_layer()
        if lid == "default":
            return
        layer = self._layer_by_id(lid)
        if not layer["visible"] or layer["locked"]:
            return
        for o in ops:
            if o[0] == "create" and getattr(o[1], "_layer_id", None) is None:
                o[1]._layer_id = lid

    def _layer_color(self, layer: dict) -> str:
        if not layer.get("color"):
            layer["color"] = _LAYER_COLORS[self._layers.index(layer) % len(_LAYER_COLORS)]
        return layer["color"]

    def _pick_layer_color(self, layer_id: str, anchor):
        layer = self._layer_by_id(layer_id)
        if layer is None:
            return

        def _on_pick(col):
            if col is None:
                return
            layer["color"] = QColor(col).name()
            self._mark_dirty()
            self._refresh_layers_panel()
        self._show_color_grid_popup(anchor, QColor(self._layer_color(layer)), False, False,
                                    "레이어 색", _on_pick)

    def _move_selection_to_active_layer(self):
        if not self._edit_targets():
            self.statusBar().showMessage("옮길 도형을 먼저 선택하세요", 2500)
            return
        self.move_selection_to_layer(self._current_active_layer())


    def rename_layer(self, layer_id: str, name: str):
        layer = self._layer_by_id(layer_id)
        if layer is not None and name.strip():
            layer["name"] = name.strip()
            self._refresh_layers_panel()


    def delete_layer(self, layer_id: str):
        """기본 레이어는 삭제 불가(최소 1개 유지). 소속 아이템은 기본 레이어로 소급."""
        if layer_id == "default" or self._layer_by_id(layer_id) is None:
            return
        for it in self._items_in_layer(layer_id):
            it._layer_id = None
            self._sync_item_to_layer_state(it)   # 기본 레이어의 현재 표시/잠금을 물려받음
        self._layers = [ly for ly in self._layers if ly["id"] != layer_id]
        if getattr(self, "_active_layer", "default") == layer_id:
            self._active_layer = "default"
        self._refresh_layers_panel()


    def set_layer_visible(self, layer_id: str, visible: bool):
        """[신규기능] 레이어 표시 토글 — undo 비대상(다크모드·그리드 토글과 같은 문서 설정,
        규칙 10-b 상시 갱신 대상이 아닌 뷰/구성 상태). 새로 만든 아이템은 자동배정하지 않는
        스코프 결정 때문에, 생성 시점엔 반영 안 되고 이 토글이 다시 눌릴 때 반영된다."""
        layer = self._layer_by_id(layer_id)
        if layer is None:
            return
        layer["visible"] = visible
        for it in self._items_in_layer(layer_id):
            it.setVisible(visible)
        if not visible and self._current_active_layer() == layer_id:
            self._active_layer = "default"   # 숨긴 레이어엔 못 그리니 「그리는 중」은 기본으로
        self._refresh_layers_panel()


    def set_layer_locked(self, layer_id: str, locked: bool):
        """레이어 잠금 — 개별 Ctrl+L과 같은 _locked 플래그를 재사용(별도 필드 없음).
        ⚠ 알려진 한계: 레이어 잠금을 풀면 그 안에서 개별로 잠갔던 아이템도 함께 풀린다
        (레이어-개별 잠금 상호작용은 1차 스코프 밖 — Not-tested)."""
        layer = self._layer_by_id(layer_id)
        if layer is None:
            return
        layer["locked"] = locked
        for it in self._items_in_layer(layer_id):
            self._set_item_lock_flags(it, locked)
        if locked and self._current_active_layer() == layer_id:
            self._active_layer = "default"   # 잠근 레이어엔 못 그리니 「그리는 중」은 기본으로
        self._refresh_layers_panel()


    def _sync_item_to_layer_state(self, it):
        """아이템의 표시/잠금을 현재 _layer_id가 가리키는 레이어 상태와 맞춘다 — 이동(forward)·
        undo/redo·삭제(기본으로 소급) 세 경로가 전부 이걸 거쳐야 '레이어를 옮기면 그 레이어의
        표시/잠금을 물려받는다'는 계약이 undo 후에도 깨지지 않는다(레이어 자체에는 별도 snapshot을
        안 남기고 _layer_id 하나로부터 항상 다시 계산 — single source of truth)."""
        layer = self._layer_by_id(self._item_layer_id(it)) or self._layer_by_id("default")
        if layer is not None:
            it.setVisible(layer["visible"])
            self._set_item_lock_flags(it, layer["locked"])


    def move_selection_to_layer(self, layer_id: str):
        if self._layer_by_id(layer_id) is None:
            return
        targets = self._edit_targets()
        if not targets:
            return
        snaps = [(it, getattr(it, "_layer_id", None)) for it in targets]
        for it in targets:
            it._layer_id = layer_id
            self._sync_item_to_layer_state(it)
        self._push_entry([("mut", it, "layer", old, layer_id) for it, old in snaps])
        self._refresh_layers_panel()
        self.statusBar().showMessage(
            f'레이어 이동: {len(targets)}개 → {self._layer_by_id(layer_id)["name"]}', 2500)


    def _build_layer_menu(self, title: str, parent=None) -> QMenu:
        m = QMenu(title, parent or self)
        _style_menu_separators(m)
        for layer in self._layers:
            m.addAction(layer["name"], lambda checked=False, i=layer["id"]:
                        self.move_selection_to_layer(i))
        return m


    def _apply_loaded_layers(self, layers):
        """열기 — 저장된 레이어 목록을 복원하고 표시/잠금을 아이템에 재적용.
        옛 .ecad(레이어 키 없음)는 기본 레이어로 리셋."""
        self._layers = layers if layers else [
            {"id": "default", "name": "기본", "visible": True, "locked": False}]
        for i, ly in enumerate(self._layers):   # 옛 .ecad(색 없음)는 순서대로 기본 색
            ly.setdefault("color", _LAYER_COLORS[i % len(_LAYER_COLORS)])
        self._active_layer = "default"   # 파일을 열면 「그리는 중」은 기본부터(사용자 결정)
        for it in self._zorder_pool():
            self._sync_item_to_layer_state(it)
        self._refresh_layers_panel()

    # ---- 속성 편집 → push_undo_state (M2 #2) --------------------------------
