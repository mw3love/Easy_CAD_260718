"""CanvasWindow 믹스인 — 레이어 패널 — 추가/이름변경/삭제/표시·잠금 토글/아이템 소속 동기화.

2026-08-02 host.py(3635줄) 분할분. `class CanvasWindow(...)`이 이 믹스인들을 다중상속해
메서드를 합친다 — 동작·이름 전부 원본과 동일(이동만), annotator_core.py가 이미 쓰는 믹스인
패턴을 host.py에도 적용한 것.
"""
from __future__ import annotations

import re
import uuid

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QSize, QSettings, QTimer, QMimeData, QEvent
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter,
    QFont, QPolygonF, QPainterPath, QPalette, QDrag,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPlainTextEdit,
    QSizePolicy, QColorDialog, QHBoxLayout, QMenu, QFrame,
    QListWidget, QListWidgetItem,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon, _nearest_border,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document, load_document_layers
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)

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
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(6)
        lid = layer["id"]

        vis_btn = QToolButton()
        vis_btn.setCheckable(True)
        vis_btn.setChecked(layer["visible"])
        vis_btn.setText("👁" if layer["visible"] else "🚫")
        vis_btn.setToolTip("레이어 표시/숨김")
        vis_btn.toggled.connect(lambda checked, i=lid: self.set_layer_visible(i, checked))

        lock_btn = QToolButton()
        lock_btn.setCheckable(True)
        lock_btn.setChecked(layer["locked"])
        lock_btn.setText("🔒" if layer["locked"] else "🔓")
        lock_btn.setToolTip("레이어 잠금")
        lock_btn.toggled.connect(lambda checked, i=lid: self.set_layer_locked(i, checked))

        count = len(self._items_in_layer(lid))
        name_lbl = QLabel(f'{layer["name"]} ({count})')
        name_lbl.setWordWrap(False)

        h.addWidget(vis_btn)
        h.addWidget(lock_btn)
        h.addWidget(name_lbl, 1)

        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(
            lambda pos, i=lid, r=row: self._show_layer_row_menu(r, i))
        return row


    def _show_layer_row_menu(self, row: QWidget, layer_id: str):
        menu = QMenu(self)
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
        layer = {"id": uuid.uuid4().hex[:8], "name": name, "visible": True, "locked": False}
        self._layers.append(layer)
        self._refresh_layers_panel()
        return layer


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
        for layer in self._layers:
            m.addAction(layer["name"], lambda checked=False, i=layer["id"]:
                        self.move_selection_to_layer(i))
        return m


    def _reset_layers(self):
        """새 문서 — 레이어를 기본 하나로 리셋."""
        self._layers = [{"id": "default", "name": "기본", "visible": True, "locked": False}]
        if hasattr(self, "_layers_list"):
            self._refresh_layers_panel()


    def _apply_loaded_layers(self, layers):
        """열기 — 저장된 레이어 목록을 복원하고 표시/잠금을 아이템에 재적용.
        옛 .ecad(레이어 키 없음)는 기본 레이어로 리셋."""
        self._layers = layers if layers else [
            {"id": "default", "name": "기본", "visible": True, "locked": False}]
        for it in self._zorder_pool():
            self._sync_item_to_layer_state(it)
        self._refresh_layers_panel()

    # ---- 속성 편집 → push_undo_state (M2 #2) --------------------------------
