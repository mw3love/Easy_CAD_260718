"""CanvasWindow 믹스인 — 우클릭 컨텍스트 메뉴 + 플로팅 툴바 동작(도형·화살표 교체/라우팅/반경)·정렬·분배·케이블 채번.

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
from easycad.canvas.host_widgets import _ARROW_KIND_TOOL, _arrow_kind_of
from easycad.canvas.host_dialogs import _CableNumberDialog, _SvgAssetDialog

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




class _ContextMixin:
    def _build_context_menu(self):
        """[M3 #16] 유휴 우클릭 탭 메뉴 구성 — 선택/클립보드 유무로 항목을 정한다.
        전부 기존 편집 경로(copy/paste/duplicate/delete/select_all)를 재사용해 undo 일관.
        exec는 _show_context_menu가 하고, 이 메서드는 구성만(스모크 테스트용 분리)."""
        menu = QMenu(self)
        sel = self._scene.selectedItems()
        has_sel = bool(sel)
        has_clip = bool(getattr(self, "_clip", None))
        if has_sel:
            menu.addAction("복사\tCtrl+C", self.copy_selection)
            menu.addAction("잘라내기", self._cut_selection)
            menu.addAction("복제\tCtrl+D", self.duplicate_selection)
            menu.addAction("삭제\tDel", self.delete_selection)
        # [신규기능 · 스타일 복사] 단일 선택=복사 진입점, 스타일 클립 있으면=붙여넣기 진입점.
        has_style_clip = getattr(self, "_style_clip", None) is not None
        if len(sel) == 1 or has_style_clip:
            menu.addSeparator()
            if len(sel) == 1:
                menu.addAction("스타일 복사\tCtrl+Alt+C", self.copy_style_from_selection)
                # [§8 항목20 B단계] AI SVG 대체 — 도형 바꾸기(_build_swap_menu)와 같은
                # 대상 타입(사각형/원/심볼)만 허용. 화살표·라벨·표·용지틀은 "대체"라는
                # 개념 자체가 안 맞아 제외.
                if isinstance(sel[0], (_RectItem, _EllipseItem, _SymbolItem)):
                    menu.addAction("SVG로 생성...", lambda it=sel[0]: self._generate_svg_replace(it))
            if has_sel and has_style_clip:
                menu.addAction("스타일 붙여넣기\tCtrl+Alt+V", self.paste_style_to_selection)
        if len(self._align_targets()) >= 2:      # [M5] 여럿 선택 시만 정렬/분배 서브메뉴
            menu.addSeparator()
            menu.addMenu(self._build_align_menu("정렬 / 분배", parent=menu))
        if len(self._arrow_targets()) >= 1:      # [신규기능] 화살표 선택 시만 채번 진입점
            menu.addSeparator()
            menu.addAction("케이블 번호 매기기...", self._prompt_cable_numbers)
        targets = self._edit_targets()           # [편의기능] Z-order/그룹/잠금 대상
        if targets:
            menu.addSeparator()
            menu.addAction("맨 앞으로 보내기\tCtrl+]", self.bring_to_front)
            menu.addAction("맨 뒤로 보내기\tCtrl+[", self.send_to_back)
            menu.addAction("잠금 전환\tCtrl+L", self.toggle_lock_selection)
            if len(targets) >= 2:
                menu.addAction("그룹\tCtrl+G", self.group_selection)
            if any(getattr(it, "_group_id", None) for it in targets):
                menu.addAction("그룹 해제\tCtrl+Shift+G", self.ungroup_selection)
            menu.addMenu(self._build_layer_menu("레이어로 이동", parent=menu))  # [신규기능]
            menu.addAction("팔레트에 등록...", self.register_selection_as_symbol)  # [신규기능 §8-8]
        if has_sel:
            # [내보내기 통합, 2026-08-20 실사용 피드백] 선택 상태에서 바로 내보내기 —
            # File 메뉴 「내보내기」와 같은 다이얼로그를 공유하되 범위 기본값만 "선택
            # 영역"으로 다르게 연다(다이얼로그 안에서 "전체 도면"으로도 바꿀 수 있음).
            menu.addSeparator()
            export_menu = menu.addMenu("내보내기")
            export_menu.addAction("PDF…", lambda: self._export_document("pdf", True))
            export_menu.addAction("이미지 (PNG)…", lambda: self._export_document("png", True))
            export_menu.addAction("SVG…", lambda: self._export_document("svg", True))
        if has_clip:
            if has_sel:
                menu.addSeparator()
            menu.addAction("붙여넣기\tCtrl+V", self.paste_selection)
        if not has_sel:
            if has_clip:
                menu.addSeparator()
            menu.addAction("전체 선택\tCtrl+A", self.select_all)
            if any(getattr(it, "_locked", False) for it in self._zorder_pool()):
                menu.addAction("잠금 해제 (전체)", self.unlock_all)
        return menu if not menu.isEmpty() else None


    def _show_context_menu(self, global_pos):
        menu = self._build_context_menu()
        if menu is not None:
            menu.exec(global_pos)

    # ---- [Phase 6 M3 #15] 플로팅 컨텍스트 툴바 ------------------------------
    # [미니패널 통합, 2026-07-31] 선택 위를 따라다니던 플로팅 컨텍스트 툴바를 폐지 — 색·선스타일은
    # 속성 dock과 중복이었고 도형바꾸기·화살표종류·곡선반경·방향뒤집기 4개는 dock 폼에 행으로
    # 이관(`_build_properties_panel`). 아래는 그 핸들러들(로직 변경 없이 재사용).

    def _floating_flip_arrows(self):
        arrows = [it for it in self._scene.selectedItems()
                  if isinstance(it, (_ArrowItem, _PolyArrowItem))]
        if not arrows:
            return
        self._edit_items(arrows, lambda it: it.flip_head())


    def _floating_set_arrow_kind(self, kind):
        """[화살표 통합] 선택된 화살표를 kind로 바꾼다. 직선↔곡선은 같은 객체의 상태 변경이라
        곡률을 기억하고, ↔직각은 클래스 교체(_swap_arrow)라 곡률·경유힌트가 초기화된다
        (되돌리기로 복구). 고른 종류는 sticky — 다음에 그릴 화살표의 기본이 된다."""
        sel = [it for it in self._scene.selectedItems()
               if isinstance(it, (_ArrowItem, _PolyArrowItem))]
        self.current_arrow_kind = kind
        self._refresh_arrow_tool_button()
        # [화살표 통합 · 핀 버그] 화살표 도구가 이미 무장 중(핀)이면 종류 변경을 무장에도 반영한다.
        # 안 그러면 곡선(arrow)으로 무장된 채 종류만 직각으로 바꿔 다음 화살표가 옛 도구로 그려진다.
        # 핀이 꺼져 있으면 그리기 후 선택모드로 빠져 다음 무장 때 arm_arrow_tool이 새 종류를 읽는다.
        want = _ARROW_KIND_TOOL.get(kind, "arrow")
        if self.current_tool in ("arrow", "sarrow") and self.current_tool != want:
            self.set_tool(want)
        for it in list(sel):
            if _arrow_kind_of(it) == kind:
                continue
            if (kind == "ortho") != isinstance(it, _PolyArrowItem):
                self._swap_arrow(it, kind)      # 클래스가 바뀜 — remove+create 단일 엔트리
                continue
            before = it.capture_geom()          # 같은 클래스 — 기하 변경 하나로 충분
            if isinstance(it, _PolyArrowItem):
                it.set_routing("ortho" if kind == "ortho" else "straight")
            elif kind == "straight":
                it.apply_straight()
            else:
                it.apply_curved()
            self.push_undo_geom([(it, before)])
        self._refresh_properties()
        self._view.viewport().update()


    def _make_swapped_arrow(self, item, kind):
        """item과 같은 끝점·색·두께·선스타일·머리방향·라벨·연결을 가진 kind용 새 화살표."""
        is_poly = isinstance(item, _PolyArrowItem)
        p1 = item.mapToScene(item._pts[0] if is_poly else item._p1)
        p2 = item.mapToScene(item._pts[-1] if is_poly else item._p2)
        if kind == "ortho":
            new = _PolyArrowItem(QColor(item._color), item._width, item._head_at_end)
            new._curve_r = float(self.current_curve_r)   # 반경도 sticky
        else:
            new = _ArrowItem(QColor(item._color), item._width, item._head_at_end)
        new._style = item._style
        new.setZValue(item.zValue())
        new.setFlags(new.GraphicsItemFlag.ItemIsMovable | new.GraphicsItemFlag.ItemIsSelectable)
        new.set_points(p1, p2)
        for idx, (sh, pt) in enumerate((
                (item._bind_start, item._bind_start_pt) if is_poly else (item._bind1, item._bind1_pt),
                (item._bind_end, item._bind_end_pt) if is_poly else (item._bind2, item._bind2_pt))):
            if sh is not None and pt is not None:
                new.set_bound(idx, sh, QPointF(pt))
        if item.has_label() and item._label is not None:
            txt = item._label.toPlainText()
            if txt:
                new.ensure_label().setPlainText(txt)
        return new


    def _swap_arrow(self, item, kind):
        """[화살표 통합] 화살표를 다른 클래스로 교체(M4-3 도형 교체와 같은 패턴).
        remove(old)+create(new)를 하나의 undo 엔트리로 묶어 한 번에 되돌린다."""
        new = self._make_swapped_arrow(item, kind)
        was_selected = item.isSelected()
        self._scene.removeItem(item)
        self._scene.addItem(new)
        # ⚠ 라벨 정렬·경로 계산은 씬에 들어간 뒤에 해야 한다(씬 멤버십 가드로 no-op되는 함정).
        if kind == "ortho":
            new._auto_route = True
            new._apply_routing()
        elif kind == "curved":
            new.apply_curved()
        new._sync_label()
        self._push_entry([("remove", item), ("create", new)])
        if was_selected:
            self._scene.clearSelection()
            new.setSelected(True)
        self._refresh_properties()
        return new


    def _floating_set_radius(self, value: int):
        """[M4-4 ⓑ] 선택된 직각 커넥터의 모서리 각짐(0=완전 직각). 스테퍼 연속 조작은 undo 1스텝으로
        병합한다(스핀박스 화살표를 여러 번 눌러도 되돌리기 한 번). 값 동기화(setValue)는
        blockSignals로 되먹임을 막으므로 여기 오는 건 사용자 조작뿐이다. 바꾼 값은 sticky."""
        sel = [it for it in self._scene.selectedItems() if isinstance(it, _PolyArrowItem)]
        if not sel:
            return
        snaps = [(it, it.capture_geom()) for it in sel]
        for it in sel:
            it.set_corner_radius(value)
        self.current_curve_r = float(value)   # 다음 직각 커넥터의 기본 각짐(sticky)
        self.push_undo_geom(snaps, coalesce_key=("curve_r", id(sel[0])))
        self._view.viewport().update()

    # ---- [Phase 6 M4-3] 도형 바로 바꾸기 -----------------------------------

    def _build_swap_menu(self):
        """도형 교체 대상 메뉴 — 네모·원 + 심볼 14종. 트리거 시 현재 단일 선택 도형을 변환."""
        m = QMenu(self)
        m.addAction("사각형", lambda: self._swap_selected("rect"))
        m.addAction("원", lambda: self._swap_selected("ellipse"))
        m.addSeparator()
        for kind, (label, _f) in _SYMBOL_KINDS.items():
            m.addAction(label, lambda k=kind: self._swap_selected(f"sym:{k}"))
        return m


    def _swap_selected(self, target_kind):
        sel = [it for it in self._scene.selectedItems()
               if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]
        if len(sel) == 1:
            self._swap_shape(sel[0], target_kind)


    def _make_swapped(self, item, target_kind):
        """item과 같은 rect·pos·회전·스케일·펜·라벨을 가진 target_kind 새 아이템(연결은 별도 이관)."""
        rect = QRectF(item.rect())
        if target_kind == "rect":
            new = _RectItem(rect)
        elif target_kind == "ellipse":
            new = _EllipseItem(rect)
        elif target_kind.startswith("sym:"):
            new = _SymbolItem(target_kind[4:], rect)
        else:
            return None
        new.setPen(QPen(item.pen()))
        new.setBrush(item.brush())
        new.setTransformOriginPoint(item.transformOriginPoint())
        new.setRotation(item.rotation())
        new.setScale(item.scale())
        new.setPos(item.pos())
        new.setFlags(new.GraphicsItemFlag.ItemIsMovable | new.GraphicsItemFlag.ItemIsSelectable)
        if item.has_label() and item._label is not None:
            txt = item._label.toPlainText()
            if txt:
                new.ensure_label().setPlainText(txt)
                new._sync_label()
        return new


    def _arrows_bound_to(self, item):
        """item에 지속 연결된 화살표 목록 → [(arrow, idx0/1), ...]. 곡선·직선 화살표 모두."""
        out = []
        for it in self._scene.items():
            if isinstance(it, _ArrowItem):
                if it._bind1 is item:
                    out.append((it, 0))
                if it._bind2 is item:
                    out.append((it, 1))
            elif isinstance(it, _PolyArrowItem):
                if it._bind_start is item:
                    out.append((it, 0))
                if it._bind_end is item:
                    out.append((it, 1))
        return out


    def _rebind_arrow(self, arr, idx, new):
        """화살표 끝점(idx)을 new 도형에 다시 바인딩. [M4-3 fix] 옛 도형 테두리 위 좌표를 그대로
        쓰면 원·평행사변형처럼 외곽선이 안쪽으로 든 도형에선 끝점이 떠 버린다 → new의 실제
        외곽선에 투영한 뒤 reroute로 끌어붙인다."""
        if isinstance(arr, _ArrowItem):
            ep = arr._p1 if idx == 0 else arr._p2
        else:
            ep = arr._pts[0] if idx == 0 else arr._pts[-1]
        ep_scene = arr.mapToScene(ep)
        q_scene, _n = _nearest_border(new, ep_scene)   # new 외곽선 최근접점(회전·심볼 슬랜트 반영)
        arr.set_bound(idx, new, new.mapFromScene(q_scene))
        arr.reroute()   # 끝점을 new 외곽선 위로 즉시 이동(뜬 채로 남지 않게)


    def _swap_shape(self, item, target_kind):
        """[M4-3] 도형을 target_kind로 즉석 변환(크기·위치·라벨 유지). 연결 화살표는 new로
        재바인딩. remove(old)+create(new)+화살표 geom 변경을 하나의 undo 엔트리로 묶는다."""
        new = self._make_swapped(item, target_kind)
        if new is None:
            return
        befores = [(arr, idx, arr.capture_geom()) for arr, idx in self._arrows_bound_to(item)]
        self._scene.removeItem(item)
        self._scene.addItem(new)
        ops = [("remove", item), ("create", new)]
        for arr, idx, before in befores:
            self._rebind_arrow(arr, idx, new)
            arr.update()
            ops.append(("mut", arr, "geom", before, arr.capture_geom()))
        self._push_entry(ops)
        self._scene.clearSelection()
        new.setSelected(True)
        self._refresh_properties()


    def _generate_svg_replace(self, item):
        """[§8 항목20 B단계] 선택 도형을 AI SVG로 대체 — 대체 도형 바운딩박스 긴 변 기준
        리스케일(SVG 자체 종횡비는 유지, 2026-08-14 deep-interview 확정), 중심 위치 유지.
        연결 화살표는 `_swap_shape`와 달리 재바인딩하지 않는다 — 계획서 확정 스코프:
        `delete_selection()`이 이미 "도형만 지우면 화살표가 `sh.scene() is not None`
        가드에 걸려 그 자리에 얼어붙는다"는 동작을 공짜로 제공하므로, 여기선 단순
        remove+create만 하나의 undo 엔트리로 묶으면 같은 결과가 난다(별도 언바인드 불필요).
        `item.rect()` 기반 bbox 계산은 `_make_swapped`와 동일 관례 — `sceneBoundingRect()`
        대신 쓰는 이유는 그쪽이 펜 두께만큼 부풀려진 값이라 실제 도형 크기가 아니기
        때문(`docs/pitfalls.md` "좌표계·변환" 참조)."""
        rect_scene = item.mapToScene(QRectF(item.rect())).boundingRect()
        long_side = max(rect_scene.width(), rect_scene.height())
        center = rect_scene.center()
        dlg = _SvgAssetDialog(self, confirm_label="확인 (도형 대체)")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        svg_text = dlg.selected_svg()
        if not svg_text:
            return
        try:
            new_items = self._svg_text_to_items(svg_text, long_side, center)
        except Exception as e:  # noqa: BLE001 — AI 응답 파싱 실패(구조 손상 등)
            QMessageBox.warning(self, "SVG로 생성", f"생성 실패: {e}")
            return
        if not new_items:
            QMessageBox.information(self, "SVG로 생성", "가져올 도형이 없습니다.")
            return
        self._scene.removeItem(item)
        for it in new_items:
            self._scene.addItem(it)
        ops = [("remove", item)] + [("create", it) for it in new_items]
        self._push_entry(ops)
        self._scene.clearSelection()
        for it in new_items:
            it.setSelected(True)
        self._refresh_properties()

    # ---- [Phase 6 M5] 정렬 / 분배 -------------------------------------------
    # 계획서 §5 #4 흡수. 선택 bbox를 기준으로 붙이고(정렬), 양 끝을 고정한 채 사이 여백을
    # 균등하게 편다(분배). 이동만 하므로 push_undo_move 하나로 되돌아간다.
    # ⚠ 연결된 화살표는 대상이 아니다 — 도형이 움직이면 _on_scene_changed의 reroute가 끝점을
    #   다시 도형에 붙이므로, 화살표까지 옮겨 봐야 그 이동이 곧 덮어써지고 bbox만 흐트러진다.
    #   커넥터는 '정렬되는 것'이 아니라 '따라오는 것'.
    _ALIGN_MODES = (
        ("left",    "왼쪽 맞춤"),
        ("hcenter", "가로 가운데"),
        ("right",   "오른쪽 맞춤"),
        ("top",     "위쪽 맞춤"),
        ("vcenter", "세로 가운데"),
        ("bottom",  "아래쪽 맞춤"),
    )


    def _align_targets(self):
        """정렬·분배 대상 — 선택된 '움직일 수 있는' 최상위 아이템에서 연결 화살표와 용지틀을 뺀 것.
        용지틀(_TitleBlockItem)은 내용이 아니라 종이 자체라 함께 밀리면 안 된다.
        ⚠ 자식 아이템(라벨)은 제외 — 라벨도 selectable·movable이라 러버밴드에 딸려 들어오는데,
          ⓐ 위치를 부모가 소유해(itemChange가 경로 위로 재투영) 옮겨도 되돌아오고
          ⓑ moveBy 델타는 부모 좌표계라, 씬 좌표로 계산한 이동량이 회전된 부모에선 어긋난다."""
        out = []
        for it in self._scene.selectedItems():
            if it.parentItem() is not None:
                continue
            if not (it.flags() & it.GraphicsItemFlag.ItemIsMovable):
                continue
            if isinstance(it, _TitleBlockItem):
                continue
            if isinstance(it, (_ArrowItem, _PolyArrowItem)) and it.has_binding():
                continue
            out.append(it)
        return out

    # ---- [신규기능] 케이블 번호 자동채번 — deep-interview 2026-07-28 -----------

    def _arrow_targets(self):
        """채번 대상 — 선택 중 화살표(직선/곡선/직각 전부)만. 도형·표 등은 무시."""
        return [it for it in self._scene.selectedItems()
                if isinstance(it, (_ArrowItem, _PolyArrowItem))]


    def apply_cable_numbers(self, prefix: str, start: int):
        """선택된 화살표에 위치순(좌상단→우하단)으로 '{prefix}-{n}: ' 라벨을 매긴다.
        기존 라벨 텍스트는 보존(뒤에 이어붙임), 재실행 시 같은 접두사의 옛 번호는 교체된다.
        신규 라벨 생성(create)과 기존 라벨 수정(mut/state)을 한 undo 엔트리로 묶는다."""
        targets = self._arrow_targets()
        if not targets:
            return
        anchored = [(it, it.mapToScene(it._label_anchor())) for it in targets]
        anchored.sort(key=lambda pair: (round(pair[1].y()), round(pair[1].x())))
        targets = [it for it, _ in anchored]
        # 현재 접두사의 옛 번호만 인식해 교체 — 접두사가 다르면(예: 이전 CABLE→이번 CAM)
        # 옛 패턴은 매칭 안 되고 그대로 보존된 채 새 번호가 앞에 붙는다(의도된 동작).
        num_re = re.compile(r"^" + re.escape(prefix) + r"-\d+:?\s*")
        ops = []
        for i, it in enumerate(targets, start=start):
            is_new = not it._label_alive()
            lbl = it.ensure_label()
            before = None if is_new else lbl.capture_state()
            old_text = lbl.toPlainText()
            m = num_re.match(old_text)
            rest = old_text[m.end():] if m else old_text
            new_text = f"{prefix}-{i}: {rest}" if rest else f"{prefix}-{i}"
            lbl.setPlainText(new_text)
            if is_new:
                ops.append(("create", lbl))
            else:
                ops.append(("mut", lbl, "state", before, lbl.capture_state()))
        self._push_entry(ops)
        self.statusBar().showMessage(f"케이블 번호 매김 — {len(targets)}개", 2000)


    def _prompt_cable_numbers(self):
        dlg = _CableNumberDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        prefix, start = dlg.result()
        self.apply_cable_numbers(prefix, start)


    def _repaint_overlays(self):
        """뷰 전체를 다시 칠한다. 프로그램이 아이템을 옮긴 뒤 반드시 필요 —
        ⚠ 다중선택 그룹 박스·정렬 가이드는 아이템이 아니라 뷰의 drawForeground가 그리는데,
        Qt는 '움직인 아이템의 boundingRect'만 무효화하므로 선택 bbox 가장자리에 그려진 옛
        점선이 지워지지 않고 남는다(실조건 2026-07-26 사용자 화면에서 확인).
        마우스 드래그로 옮길 땐 이어지는 이동 이벤트가 어차피 다시 칠해 드러나지 않는다."""
        self._view.viewport().update()

    @staticmethod

    @staticmethod
    def _align_rect(it) -> QRectF:
        """정렬 기준이 되는 '보이는 도형'의 씬 사각형.
        ⚠ sceneBoundingRect()를 쓰면 안 된다 — 코어의 boundingRect()는 선택 핸들·회전 핸들·
        빠른생성 도트 자리를 상시 예약하므로 도형마다 여백이 제각각이고(실측 26px vs 19.75px)
        그만큼 어긋나게 정렬된다. _content_rect()가 획까지만 포함한 실제 내용 사각형."""
        r = it._content_rect() if hasattr(it, "_content_rect") else it.boundingRect()
        return it.mapToScene(r).boundingRect()   # 회전·스케일 반영


    def align_selection(self, mode):
        """선택 bbox의 해당 모서리(또는 중심)에 대상들을 맞춘다. 기준을 '먼저 고른 객체'가 아니라
        bbox로 두는 것은 선택 순서가 Qt에서 보장되지 않기 때문(Figma·Lucid의 기본과 동일)."""
        boxes = [(it, self._align_rect(it)) for it in self._align_targets()]
        if len(boxes) < 2:
            return
        box = QRectF()
        for _it, r in boxes:
            box = box.united(r)
        pairs = [(it, QPointF(it.pos())) for it, _r in boxes]
        moved = False
        for it, r in boxes:
            dx = dy = 0.0
            if mode == "left":
                dx = box.left() - r.left()
            elif mode == "right":
                dx = box.right() - r.right()
            elif mode == "hcenter":
                dx = box.center().x() - r.center().x()
            elif mode == "top":
                dy = box.top() - r.top()
            elif mode == "bottom":
                dy = box.bottom() - r.bottom()
            elif mode == "vcenter":
                dy = box.center().y() - r.center().y()
            if dx or dy:
                it.moveBy(dx, dy)
                moved = True
        if moved:
            self.push_undo_move(pairs)
            self._repaint_overlays()


    def distribute_selection(self, axis):
        """가로("x")/세로("y") 균등 분배 — 양 끝은 그대로 두고 사이 '여백'을 같게 편다.
        중심 간격이 아니라 여백을 나누는 것은 크기가 제각각인 도형에서도 눈에 보이는 틈이
        같아야 하기 때문. 3개 미만이면 나눌 사이가 없어 아무 일도 하지 않는다."""
        targets = self._align_targets()
        if len(targets) < 3:
            return
        horiz = (axis == "x")
        boxes = sorted(((it, self._align_rect(it)) for it in targets),
                       key=lambda p: p[1].left() if horiz else p[1].top())
        first, last = boxes[0][1], boxes[-1][1]
        span = (last.right() - first.left()) if horiz else (last.bottom() - first.top())
        used = sum((r.width() if horiz else r.height()) for _it, r in boxes)
        gap = (span - used) / (len(boxes) - 1)   # 겹쳐 있으면 음수 — 그래도 균등해진다
        pairs = [(it, QPointF(it.pos())) for it, _r in boxes]
        cur = first.left() if horiz else first.top()
        prev = first.width() if horiz else first.height()
        moved = False
        for it, r in boxes[1:-1]:
            cur += prev + gap
            d = cur - (r.left() if horiz else r.top())
            if d:
                it.moveBy(d, 0.0) if horiz else it.moveBy(0.0, d)
                moved = True
            prev = r.width() if horiz else r.height()
        if moved:
            self.push_undo_move(pairs)
            self._repaint_overlays()


    def _build_align_menu(self, title="", parent=None):
        """정렬 6 + 분배 2 메뉴. 미니툴바 드롭다운과 우클릭 서브메뉴가 같은 메뉴를 쓴다.
        우클릭 메뉴는 매번 새로 만들어지므로 parent를 그 메뉴로 줘서 함께 정리되게 한다."""
        m = QMenu(title, parent or self)
        for mode, label in self._ALIGN_MODES[:3]:
            m.addAction(label, lambda md=mode: self.align_selection(md))
        m.addSeparator()
        for mode, label in self._ALIGN_MODES[3:]:
            m.addAction(label, lambda md=mode: self.align_selection(md))
        m.addSeparator()
        m.addAction("가로 균등 분배", lambda: self.distribute_selection("x"))
        m.addAction("세로 균등 분배", lambda: self.distribute_selection("y"))
        return m
