"""CanvasWindow 믹스인 — Undo/Redo 저널 — 스냅샷 push/apply, 되돌리기/다시실행.

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
from easycad.canvas.host_widgets import _ONESHOT_TOOLS, _UndoEntry

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




class _UndoMixin:
    def _reset_history(self):
        """[M2] 문서 교체(새로/열기/가져오기) 시 undo·redo 스택을 함께 비운다."""
        self._undo.clear()
        self._redo.clear()
        self._refresh_history_actions()


    def _push_entry(self, ops, key=None):
        """ops(연산 리스트)를 저널에 쌓는다. key가 직전 엔트리와 같으면 병합(연속 변이).
        새 변이가 실리면 redo 스택은 무효화된다(표준 undo 시맨틱)."""
        if not ops:
            return
        top = self._undo[-1] if self._undo else None
        if key is not None and top is not None and top.key == key:
            self._coalesce_into(top, ops)   # before 유지, after만 갱신
        else:
            self._undo.append(_UndoEntry(ops, key))
        self._redo.clear()
        self._refresh_history_actions()

    @staticmethod

    @staticmethod
    def _coalesce_into(entry, new_ops):
        """연속 변이 병합 — 같은 아이템·같은 sub의 mut는 before를 유지한 채 after만 갱신
        (예: Shift+휠 두께를 여러 번 굴려도 undo 1스텝). 그 외 op는 뒤에 덧붙인다."""
        index = {(id(o[1]), o[2]): i for i, o in enumerate(entry.ops)
                 if o[0] == "mut"}
        for o in new_ops:
            if o[0] == "mut" and (id(o[1]), o[2]) in index:
                i = index[(id(o[1]), o[2])]
                prev = entry.ops[i]
                entry.ops[i] = ("mut", o[1], o[2], prev[3], o[4])  # before 유지·after 갱신
            else:
                entry.ops.append(o)


    def push_undo_add(self, item):
        self._push_entry([("create", item)])
        self._maybe_oneshot_revert()


    def push_undo_add_many(self, items):
        """[2d] 여러 아이템(복제 도형+연결 화살표)을 한 번의 undo로 함께 제거."""
        self._push_entry([("create", it) for it in items])
        self._maybe_oneshot_revert()


    def _maybe_oneshot_revert(self):
        """[M2] 도형을 하나 커밋한 뒤 — pin이 꺼져 있고 지금 도구가 one-shot 대상이면
        선택모드로 되돌린다(그린 뒤 또 그려지는 오작동 차단). 진행 중 이벤트가 끝난 뒤
        적용하도록 singleShot(0)로 지연(현재 그리기 핸들러가 도구를 더 참조할 수 있으므로).
        붙여넣기·복제·빠른생성은 select 모드에서 일어나 여기 걸리지 않는다(가드)."""
        tool = self.current_tool
        armed = tool in _ONESHOT_TOOLS or (tool or "").startswith("sym:")
        if armed and not self.tool_pinned:
            QTimer.singleShot(0, lambda: self.set_tool("select"))


    def push_undo_delete(self, items):
        self._push_entry([("remove", it) for it in items])


    def push_undo_move(self, pairs, coalesce_key=None):
        self._push_entry(
            [("mut", it, "pos", QPointF(old), QPointF(it.pos())) for it, old in pairs],
            key=coalesce_key)


    def push_undo_xform(self, snaps):
        """[우리 확장] 그룹 변형(회전·스케일) 되돌리기 — 변형 전 pos/rotation/scale/origin 스냅샷.
        push_undo_move가 위치만 복원하는 것과 달리 회전·스케일까지 통째로 되돌린다."""
        self._push_entry([
            ("mut", it, "xform", (QPointF(pos), rot, scale, QPointF(org)),
             (QPointF(it.pos()), it.rotation(), it.scale(),
              QPointF(it.transformOriginPoint())))
            for it, pos, rot, scale, org in snaps])


    def push_undo_geom(self, snaps, coalesce_key=None):
        """[Stage2] 기하 리베이크(비균일 스케일·미러) 되돌리기 — capture_geom 토큰 스냅샷.
        xform과 달리 기하 자체(rect/끝점/정점/패스)+바인딩까지 통째로 복원한다.
        coalesce_key가 있으면 연속 조작(반경 스테퍼 등)을 undo 1스텝으로 병합한다."""
        self._push_entry([
            ("mut", it, "geom", before, it.capture_geom()) for it, before in snaps],
            key=coalesce_key)


    def push_undo_state(self, snaps, coalesce_key=None):
        """[M2] 속성·라벨 변경(색·두께·선스타일·폰트·텍스트) — before=capture_state 스냅샷
        (변경 전), after=현재. 저널의 'state' mut로 실려 되돌리기/다시 실행된다."""
        self._push_entry(
            [("mut", it, "state", before, it.capture_state()) for it, before in snaps],
            key=coalesce_key)


    def _apply_mut(self, it, sub, tok):
        """mut op의 sub별 복원 — undo는 before, redo는 after 토큰을 그대로 넘긴다."""
        if sub == "pos":
            it.setPos(tok)
        elif sub == "xform":
            pos, rot, scale, org = tok
            it.setTransformOriginPoint(org)
            it.setRotation(rot)
            it.setScale(scale)
            it.setPos(pos)
        elif sub == "geom":
            # 기하+바인딩 통째 복원 — apply_geom만으로 일관 복원(reroute 불필요).
            it.apply_geom(tok)
        elif sub == "state":
            it.apply_state(tok)
        elif sub == "z":
            it.setZValue(tok)
        elif sub == "group":
            it._group_id = tok
        elif sub == "lock":
            self._set_item_lock_flags(it, tok)
        elif sub == "layer":
            it._layer_id = tok
            self._sync_item_to_layer_state(it)   # undo/redo도 옮긴 레이어의 표시/잠금을 물려받음
            if hasattr(self, "_layers_list"):
                self._refresh_layers_panel()


    def _apply_entry(self, entry, redo):
        for op in entry.ops:
            kind = op[0]
            if kind == "create":
                it = op[1]
                if redo:
                    if it.scene() is None:
                        self._scene.addItem(it)
                elif it.scene() is not None:
                    self._scene.removeItem(it)
            elif kind == "remove":
                it = op[1]
                if redo:
                    if it.scene() is not None:
                        self._scene.removeItem(it)
                elif it.scene() is None:
                    self._scene.addItem(it)
            elif kind == "mut":
                _, it, sub, before, after = op
                self._apply_mut(it, sub, after if redo else before)


    def undo(self):
        if not self._undo:
            return
        entry = self._undo.pop()
        self._apply_entry(entry, redo=False)
        self._redo.append(entry)
        self._refresh_history_actions()
        self._repaint_overlays()   # 되돌리기도 프로그램 이동 — 그룹 박스 잔상 방지


    def redo(self):
        if not self._redo:
            return
        entry = self._redo.pop()
        self._apply_entry(entry, redo=True)
        self._undo.append(entry)
        self._refresh_history_actions()
        self._repaint_overlays()   # 다시 실행도 마찬가지


    def _refresh_history_actions(self):
        """undo/redo 툴바 액션의 활성 상태를 스택 유무에 맞춘다(빈 스택=disabled)."""
        act_u = getattr(self, "_act_undo", None)
        act_r = getattr(self, "_act_redo", None)
        if act_u is not None:
            act_u.setEnabled(bool(self._undo))
        if act_r is not None:
            act_r.setEnabled(bool(self._redo))

    # 복사 / 연속 붙여넣기
