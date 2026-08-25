"""CanvasWindow 믹스인 — 선택 항목 편집 — 복사/붙여넣기/복제/삭제/Z-order/그룹/잠금.

2026-08-02 host.py(3635줄) 분할분. `class CanvasWindow(...)`이 이 믹스인들을 다중상속해
메서드를 합친다 — 동작·이름 전부 원본과 동일(이동만), annotator_core.py가 이미 쓰는 믹스인
패턴을 host.py에도 적용한 것.
"""
from __future__ import annotations

import html
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
    _detach_port_from_host,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
    _min_stroke_render,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import (
    save_document, load_document, load_document_layers,
    item_to_dict, dict_to_item, _pixmap_to_b64, _b64_to_pixmap,
)
from easycad.fileio import symbol_library
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)
from easycad.canvas.host_widgets import _clipboard_pixmap, _style_menu_separators
from easycad.canvas.host_ui import _PALETTE_ICON_PX, _PALETTE_SYM_ICON_PX

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

# [실사용 피드백 2026-08-19] '내 심볼' 호버 확대 미리보기 해상도 — 팔레트 아이콘
# (`_PALETTE_SYM_ICON_PX`=28)보다 훨씬 커서 다중 도형 조합도 형태를 알아볼 수 있게.
_SYMBOL_PREVIEW_PX = 160


def _group_scene_rect(items) -> QRectF:
    """아이템 목록의 '보이는 도형' 기준 합집합 씬 사각형(§8-8 커스텀 심볼 등록/배치 공용).
    sceneBoundingRect()는 핸들·빠른생성 도트 여백이 도형마다 달라 기준으로 못 쓴다
    (M5 align_rect와 동일한 이유, `_content_rect` 우선)."""
    def _rect(it):
        r = it._content_rect() if hasattr(it, "_content_rect") else it.boundingRect()
        return it.mapToScene(r).boundingRect()
    box = _rect(items[0])
    for it in items[1:]:
        box = box.united(_rect(it))
    return box


def _render_symbol_thumbnail(items, box: QRectF, size: int = _PALETTE_SYM_ICON_PX) -> str:
    """items(아직 scene 미소속인 임시 인스턴스)를 정사각 PNG로 렌더해 base64로 반환.
    팔레트 아이콘·호버 미리보기가 공유하는 저해상도 렌더라 임시 QGraphicsScene을 그때그때
    만든다. [실사용 버그 수정 2026-08-19] 예전엔 64px로 렌더한 뒤 팔레트가 그 PNG를 다시
    `_PALETTE_ICON_PX`(18)로 스무스 축소했다 — 두 번째 축소가 1px대 선을 서브픽셀로
    지워 기본 도형 아이콘(`_shape_icon`, 18px에서 직접 그림)보다 훨씬 흐리고 얇아 보였다
    (2026-08-18 `_min_stroke_render` 처방은 64px 기준 3px였는데, 18px로 다시 줄면
    ~0.8px밖에 안 남아 부족했다). 이 이중축소 자체를 없애려 최종 아이콘 해상도에서
    바로 렌더한다 — margin도 `_shape_icon`과 동일값이라 형제 아이콘과 같은 크기 envelope.
    [실사용 피드백 2026-08-19 후속] 기본값을 `_PALETTE_ICON_PX`(18, 기본도형용)에서
    `_PALETTE_SYM_ICON_PX`(28, 내 심볼 전용)로 올림 — 다중 도형 조합은 기본도형과 같은
    18px에서는 형태가 안 보인다는 보고. 호출부는 팔레트 아이콘(기본값)과 호버 미리보기
    (`size=_SYMBOL_PREVIEW_PX`로 명시 호출)로 이 함수를 공유한다."""
    scene = QGraphicsScene()
    for it in items:
        scene.addItem(it)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    margin = 4.0   # `_shape_icon`(host_ui.py)과 동일 — 팔레트에서 같은 크기로 보이게.
    avail = size - 2 * margin
    scale = min(avail / box.width(), avail / box.height()) if box.width() > 0 and box.height() > 0 else 1.0
    w, h = box.width() * scale, box.height() * scale
    target = QRectF(margin + (avail - w) / 2, margin + (avail - h) / 2, w, h)
    # 목표 최종 두께(1.6px)는 `_shape_icon`의 `pen.setWidthF(1.6)`과 맞춘 값 — 심볼마다
    # box 크기(=scale)가 달라 씬 단위 최소두께를 매번 역산해야 한 값으로 고정 못 한다.
    target_px = 1.6
    min_scene = target_px / scale if scale > 0 else target_px
    with _min_stroke_render(items, min_width=min_scene):
        scene.render(p, target, box)
    p.end()
    return _pixmap_to_b64(pm)


class _SelectionMixin:
    def copy_selection(self):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "clone")]
        self._clip_src = sel               # 원본 참조 보관 — paste 시 배치내 바인딩 재연결용
        self._clip = [it.clone() for it in sel]
        self._paste_seq = 0


    def paste_selection(self):
        if not self._clip:
            self._paste_clipboard_image()   # [신규기능] 내부 버퍼가 비면 시스템 클립보드 이미지로 폴백
            return
        self._paste_seq += 1
        off = 20.0 * self._paste_seq
        self._scene.clearSelection()
        new_items = []
        for tmpl in self._clip:
            c = tmpl.clone()
            c.moveBy(off, off)
            self._scene.addItem(c)
            new_items.append(c)
        # clone()이 _bind1/_bind2 등을 원본 그대로 복사해 왔으므로(clip 세대를 거쳐도 불변),
        # 같이 복사된 도형끼리는 여기서 사본으로 재연결한다(배치 밖 도형 바인딩은 그대로 유지).
        remap_grouped_bindings(zip(self._clip_src, new_items))
        regroup_duplicated_items(zip(self._clip_src, new_items))   # 그룹째 복사 시 사본도 새 그룹으로
        self._bulk_select(new_items)   # [성능] 개별 setSelected 대신 한 번에 — O(n²) 회피
        if new_items:
            self.push_undo_add_many(new_items)

    # [신규기능] 클립보드 이미지 붙여넣기 — Ctrl+V 하나 공유. 내부 붙여넣기 버퍼(copy_selection)가
    # 있으면 항상 그쪽이 우선(기존 동작 불변, 위 paste_selection 분기), 버퍼가 비어 있을 때만
    # 시스템 클립보드의 이미지(스크린샷·다른 앱에서 복사한 그림)를 뷰 중앙에 삽입한다.

    def _paste_clipboard_image(self):
        pm = _clipboard_pixmap()
        if pm is None or pm.isNull():
            return
        center = self._view.mapToScene(self._view.viewport().rect().center())
        self._insert_pixmap_at(pm, center, f"클립보드 이미지 붙여넣기: {pm.width()}×{pm.height()}px")

    # [M2 #3] Ctrl+D 제자리 복제 — 클립보드를 건드리지 않고 선택 객체를 오프셋해 복제.
    # paste_selection과 동형이나 clip/paste_seq와 독립(복사 버퍼 오염 없음).

    def duplicate_selection(self):
        src = [it for it in self._scene.selectedItems() if hasattr(it, "clone")]
        if not src:
            return
        self._scene.clearSelection()
        new_items = []
        for it in src:
            c = it.clone()
            c.moveBy(20.0, 20.0)
            self._scene.addItem(c)
            new_items.append(c)
        remap_grouped_bindings(zip(src, new_items))
        regroup_duplicated_items(zip(src, new_items))   # 그룹째 복제 시 사본도 새 그룹으로
        self._bulk_select(new_items)   # [성능] 개별 setSelected 대신 한 번에 — O(n²) 회피
        if new_items:
            self.push_undo_add_many(new_items)

    # [Phase 6 M3 #16] 우클릭 컨텍스트 메뉴 — 유휴 우클릭 탭 시 뷰가 호출.

    def delete_selection(self):
        """선택 객체 삭제 + undo. 뷰의 Del 키 핸들러와 동일 동작(메뉴 재사용용)."""
        sel = list(self._scene.selectedItems())
        if not sel:
            return
        for it in sel:
            _detach_port_from_host(it)   # [신규기능 §8-12] 호스트의 _ports 목록도 정리
            self._scene.removeItem(it)
        self.push_undo_delete(sel)


    def select_all(self):
        self._bulk_select([it for it in self._scene.items()
                           if it.flags() & it.GraphicsItemFlag.ItemIsSelectable])


    def _cut_selection(self):
        self.copy_selection()
        self.delete_selection()

    # ---- [편의기능] Z-order / 그룹 / 잠금 — 공용 대상 헬퍼 --------------------

    def _zorder_pool(self):
        """Z-order·그룹·잠금 후보 전체 — 배경·용지틀 제외한 최상위 아이템."""
        bg = getattr(self, "_bg_item", None)
        return [it for it in self._scene.items()
                if it.parentItem() is None and it is not bg
                and not isinstance(it, _TitleBlockItem)]


    def _edit_targets(self):
        """위 후보 중 현재 선택된 것만."""
        pool_ids = {id(it) for it in self._zorder_pool()}
        return [it for it in self._scene.selectedItems() if id(it) in pool_ids]

    # ---- [편의기능] Z-order(맨 앞으로/맨 뒤로 보내기) --------------------------

    def bring_to_front(self):
        sel = self._edit_targets()
        if not sel:
            return
        top_z = max((it.zValue() for it in self._zorder_pool()), default=0.0)
        snaps = [(it, it.zValue()) for it in sel]
        for i, it in enumerate(sorted(sel, key=lambda x: x.zValue())):
            it.setZValue(top_z + 1.0 + i)
        self._push_entry([("mut", it, "z", old, it.zValue()) for it, old in snaps])


    def send_to_back(self):
        sel = self._edit_targets()
        if not sel:
            return
        bottom_z = min((it.zValue() for it in self._zorder_pool()), default=0.0)
        snaps = [(it, it.zValue()) for it in sel]
        for i, it in enumerate(sorted(sel, key=lambda x: -x.zValue())):
            it.setZValue(bottom_z - 1.0 - i)
        self._push_entry([("mut", it, "z", old, it.zValue()) for it, old in snaps])

    # ---- [성능] 대량 선택 공용 헬퍼 ------------------------------------------

    def _bulk_select(self, items):
        """[성능조사 2026-08-01] 여러 아이템을 한 번에 선택 — 개별 setSelected(True) 루프는
        매 호출마다 selectionChanged(→_refresh_properties가 그 시점까지 선택된 전체를
        _read_props로 재계산)가 발화해 n개 선택이 O(n²)이 된다(cProfile 실측: 300개
        붙여넣기에서 _read_props 45,150회 = 1+2+...+300 — 선택이 늘어날수록 매번 처음부터
        다시 읽은 흔적). paste_selection/duplicate_selection/select_all이 공유 — 시그널을
        루프 동안 끊고 끝나면 한 번만 재계산."""
        if not items:
            return
        sig = self._scene.selectionChanged
        sig.disconnect(self._refresh_properties)
        sig.disconnect(self._sync_group_selection)
        sig.disconnect(self._sync_selection_count_cache)
        try:
            for it in items:
                it.setSelected(True)
        finally:
            sig.connect(self._sync_selection_count_cache)
            sig.connect(self._sync_group_selection)
            sig.connect(self._refresh_properties)
        self._sync_selection_count_cache()
        self._sync_group_selection()
        self._refresh_properties()

    # ---- [성능수정 2026-08-15] 선택 개수 캐시 -----------------------------

    def _sync_selection_count_cache(self):
        """[docs/perf_report_multiselect.md 병목 A] `selectionChanged`가 발화할 때만
        `scene._sel_count_cache`를 갱신 — `_selection_is_solo`(core_shapes.py)가 paint마다
        `scene().selectedItems()`(O(N))를 직접 부르던 것을 O(1) 읽기로 대체하기 위한 캐시.
        `_bulk_select`가 이 시그널을 다른 두 슬롯과 함께 묶어 대량선택 중엔 끄고 끝나면 1회만
        부른다(아래).

        [2026-08-15 확장] `_sel_top_count_cache`(최상위=라벨 등 자식 제외 선택 수)도 함께
        갱신한다. `_group_active()`(core_shapes)가 같은 O(N²)를 호버 경로에서 재현하고 있었다 —
        마우스를 한 번 움직일 때마다 `selectedItems()`가 1,260회 호출돼 호버 하나에 157ms가
        들었다(1000개 선택 실측). 두 캐시를 한 슬롯에서 갱신해 무효화 지점을 하나로 유지한다."""
        sel = self._scene.selectedItems()
        self._sel_version = getattr(self, "_sel_version", 0) + 1   # [2-H] 그룹 캐시 무효화
        prev_top = getattr(self._scene, "_sel_top_count_cache", 0)
        top = sum(1 for it in sel if it.parentItem() is None)
        self._scene._sel_count_cache = len(sel)
        self._scene._sel_top_count_cache = top
        # [2-C(a) 2026-08-15] 다중선택 경계(2개↔1개)를 넘으면 **남아 있는 선택 아이템들의
        # boundingRect가 달라진다**(다중선택이면 개별 핸들 자리를 예약 안 함, core_shapes
        # `boundingRect` 참조). 그런데 그 아이템들 자신의 선택 상태는 안 바뀌었으므로 Qt에
        # `prepareGeometryChange()`가 가지 않는다 — 안 알려주면 Qt가 옛 bbox로 컬링해 핸들이
        # 잘려 보인다(이 레포가 반복해서 밟은 캐시 무효화 함정과 같은 부류). 경계를 넘는
        # 순간에만 명시적으로 알린다(선택 변경당 1회, 드래그 중엔 안 돈다).
        if (prev_top >= 2) != (top >= 2):
            for it in sel:
                if it.parentItem() is None:
                    it.prepareGeometryChange()
                    it.update()

    # ---- [편의기능] Group / Ungroup --------------------------------------

    def _sync_group_selection(self):
        """그룹 멤버 하나가 선택되면 같은 그룹 전체를 함께 선택(재진입 가드로 무한루프 방지)."""
        if self._group_sync_active:
            return
        sel = self._scene.selectedItems()
        gids = {getattr(it, "_group_id", None) for it in sel} - {None}
        if not gids:
            return
        missing = [it for it in self._zorder_pool()
                   if getattr(it, "_group_id", None) in gids and not it.isSelected()]
        if not missing:
            return
        self._group_sync_active = True
        try:
            for it in missing:
                it.setSelected(True)
        finally:
            self._group_sync_active = False


    def group_selection(self):
        sel = self._edit_targets()
        if len(sel) < 2:
            return
        gid = uuid.uuid4().hex[:8]
        snaps = [(it, getattr(it, "_group_id", None)) for it in sel]
        for it in sel:
            it._group_id = gid
        self._push_entry([("mut", it, "group", old, gid) for it, old in snaps])
        self.statusBar().showMessage(f"그룹 지정: {len(sel)}개 객체", 3000)


    def ungroup_selection(self):
        sel = self._edit_targets()
        gids = {it._group_id for it in sel if getattr(it, "_group_id", None)}
        if not gids:
            return
        members = [it for it in self._zorder_pool() if getattr(it, "_group_id", None) in gids]
        snaps = [(it, it._group_id) for it in members]
        for it in members:
            it._group_id = None
        self._push_entry([("mut", it, "group", old, None) for it, old in snaps])
        self.statusBar().showMessage(f"그룹 해제: {len(members)}개 객체", 3000)

    # ---- [신규기능 §8-8] 커스텀 심볼 팔레트 등록 ------------------------------

    def _build_register_symbol_menu(self, title: str = "팔레트에 등록...", parent=None) -> QMenu:
        """["팔레트에 등록" 서브메뉴화, 2026-08-25 실사용 요청] `_build_layer_menu`와 같은
        패턴 — 기존 폴더는 클릭 한 번으로 확정되고 그 뒤엔 심볼 이름만 물어 팝업이 항상
        1개로 끝난다. 새 폴더만 폴더명→심볼명 2단(레이어와 달리 심볼은 이름이 항상 필수라
        서브메뉴 자체가 그 입력을 없애주진 못한다 — 대신 흔한 경로인 "기존 폴더"를
        최소 클릭으로 만드는 게 이번 개편의 실익).
        [실사용 버그 수정 2026-08-25] `_build_layer_menu`처럼 `QMenu(title, parent)`로
        만들어야 하는데 title 인자를 빼먹어 이 서브메뉴를 여는 상위 항목 글자가 빈 줄로
        보이던 버그 — `title` 매개변수를 받아 생성자에 전달한다."""
        m = QMenu(title, parent or self)
        _style_menu_separators(m)
        m.addAction("(미분류)", lambda checked=False: self.register_selection_as_symbol(folder=None))
        folders = symbol_library.load_folders()
        if folders:
            m.addSeparator()
            for f in folders:
                m.addAction(f, lambda checked=False, name=f:
                            self.register_selection_as_symbol(folder=name))
        m.addSeparator()
        m.addAction("새 폴더...", self._register_selection_as_symbol_new_folder)
        return m

    def _register_selection_as_symbol_new_folder(self):
        """서브메뉴 "새 폴더..." — `host_ui._prompt_create_symbol_folder`와 같은 관례(이름
        하나만 입력)로 폴더를 만들고 바로 그 폴더에 등록한다."""
        name, ok = QInputDialog.getText(self, "새 폴더", "폴더 이름:")
        name = name.strip()
        if not ok or not name:
            return
        symbol_library.create_folder(name)
        self.register_selection_as_symbol(folder=name)

    def register_selection_as_symbol(self, folder: str | None = None):
        """선택(주로 DXF에서 가져온 심볼)을 앱 전역 팔레트에 등록해 다른 도면에서도 재사용.
        위치는 그대로 보존하되 화살표의 지속연결 바인딩은 저장하지 않는다(모듈 docstring 참조).
        `folder`는 호출부(`_build_register_symbol_menu`)가 서브메뉴 클릭으로 미리 정해온다."""
        targets = self._edit_targets()
        if not targets:
            return
        dicts = [d for d in (item_to_dict(it) for it in targets) if d is not None]
        if not dicts:
            QMessageBox.information(self, "팔레트에 등록", "이 항목은 등록할 수 없습니다.")
            return
        name, ok = QInputDialog.getText(self, "팔레트에 등록", "심볼 이름:")
        name = name.strip()
        if not ok or not name:
            return
        tmp = [it for it in (dict_to_item(d) for d in dicts) if it is not None]
        if not tmp:
            return
        box = _group_scene_rect(tmp)
        for d in dicts:
            d["pos"][0] -= box.left()
            d["pos"][1] -= box.top()
        thumb = _render_symbol_thumbnail(tmp, box)
        symbol_library.add_symbol(name, dicts, thumb, folder=folder)
        self._refresh_custom_symbol_section()
        self.statusBar().showMessage(f"팔레트에 등록: {name}", 3000)

    def _ensure_symbol_thumb_current(self, entry: dict) -> dict:
        """[실사용 피드백 2026-08-19] 2026-08-19 이전에 등록된 심볼은 옛 64px 렌더+이중축소
        방식 썸네일(흐릿함, `_render_symbol_thumbnail` 개편 참조)을 그대로 갖고 있다 —
        재등록해야만 고쳐진다는 게 기존 관례였지만, 실사용자가 자기 심볼로 바로 재현해
        "여전히 안 보인다"고 재보고해 자동 치유로 정책을 바꿨다. 새 포맷 썸네일은 항상
        정확히 `_PALETTE_SYM_ICON_PX` 크기이므로 그 자체가 버전 마커 — 별도 스키마 필드 없이
        팔레트를 다시 그릴 때마다(`_refresh_custom_symbol_section`) 감지해 조용히 재렌더한다.
        [같은 날 후속] 마커 크기를 `_PALETTE_ICON_PX`(18, 기본도형용)에서 `_PALETTE_SYM_
        ICON_PX`(28)로 올림 — 아이콘 자체를 키운 라운드가 이 값도 같이 옮겨, 옛 18px
        썸네일(이 라운드 전 등록분 포함)도 같은 경로로 자동 치유된다.

        [정정 2026-08-19] 처음엔 `symbol_library.update_symbol_thumb`로 디스크에도 영구
        저장했다가, 전체 스모크에서 무관해 보이는 다른 테스트(`test_minimap_bounds_cached_
        and_invalidated_by_scene_change`)가 실패해 그 파일 쓰기가 원인이라고 잠정 결론
        내렸었다 — 하지만 이후 **변경 전 베이스라인(git stash)만으로 5회 반복 실행해도
        같은 테스트가 3/5 실패**함을 확인해 그 결론은 틀렸다(이 테스트는 이 세션의 어떤
        변경과도 무관하게 이미 간헐적으로 실패하던 기존 결함, 원인 미상). 영구 저장을
        포기한 결정 자체는 유지한다(디스크 I/O를 매 팔레트 리프레시의 UI 경로에서 빼는
        것은 그 자체로 무해하고 방어적) — 다만 "그것이 저 플레이키 테스트의 원인이었다"는
        주장은 폐기. 팔레트를 새로 그릴 때마다 재구성해 화면에 보여주는 것만으로 목적
        (눈에 보이는 흐림 해결)은 충분히 달성되고 재렌더 비용도 작은 아이콘 하나뿐이라
        저렴하다(디스크의 옛 썸네일은 그대로 남지만 팔레트에는 항상 최신 렌더가 보인다)."""
        pm = _b64_to_pixmap(entry.get("thumb", ""))
        if pm.width() == _PALETTE_SYM_ICON_PX and pm.height() == _PALETTE_SYM_ICON_PX:
            return entry
        items = [it for it in (dict_to_item(d) for d in entry.get("items", [])) if it is not None]
        if not items:
            return entry
        box = _group_scene_rect(items)
        new_thumb = _render_symbol_thumbnail(items, box)
        return {**entry, "thumb": new_thumb}

    def _symbol_preview_html(self, entry: dict) -> str:
        """[실사용 피드백 2026-08-19] '내 심볼' 버튼 호버 확대 미리보기 — 팔레트 아이콘을
        `_PALETTE_SYM_ICON_PX`(28)로 키워도 다중 도형 조합(예: 사각형 2개+화살표 2개인
        작은 흐름도)은 여전히 형태 구분이 어렵다는 보고에 대한 답. 버튼을 더 키우는 대신
        저장된 items json에서 그때그때 고해상도로 다시 그려 툴팁 이미지로 보여준다 —
        호버할 때만 계산되므로(`host_widgets._PaletteButton.event`) 심볼이 아무리 많아져도
        팔레트 새로고침 자체의 비용은 늘지 않는다(등록 개수 증가에 대한 사용자의 확장성
        우려에 대한 답이기도 함). host_ui.py는 host_selection.py를 임포트할 수 없어(순환
        임포트, `_ensure_symbol_thumb_current`와 같은 제약) 이 메서드를 여기 두고
        `self._symbol_preview_html(...)`로 호출한다."""
        name = html.escape(entry.get("name", ""))
        items = [it for it in (dict_to_item(d) for d in entry.get("items", [])) if it is not None]
        if not items:
            return name
        box = _group_scene_rect(items)
        b64 = _render_symbol_thumbnail(items, box, size=_SYMBOL_PREVIEW_PX)
        return f'<div>{name}<br><img src="data:image/png;base64,{b64}"></div>'

    # ---- [편의기능] 객체 잠금 ---------------------------------------------

    def _set_item_lock_flags(self, it, locked: bool):
        """잠금 = ItemIsMovable·ItemIsSelectable을 직접 꺼서 Qt가 클릭·드래그·러버밴드를
        전부 자연히 걸러내게 한다(각 이벤트 핸들러에 별도 잠금 체크를 심을 필요가 없음)."""
        it._locked = locked
        it.setFlag(it.GraphicsItemFlag.ItemIsMovable, not locked)
        it.setFlag(it.GraphicsItemFlag.ItemIsSelectable, not locked)
        if locked:
            it.setSelected(False)


    def toggle_lock_selection(self):
        """선택 중 하나라도 미잠금이면 전부 잠금, 전부 이미 잠겼으면 전부 해제(공통 토글 UX)."""
        sel = self._edit_targets()
        if not sel:
            return
        lock_to = any(not getattr(it, "_locked", False) for it in sel)
        snaps = [(it, getattr(it, "_locked", False)) for it in sel]
        for it in sel:
            self._set_item_lock_flags(it, lock_to)
        self._push_entry([("mut", it, "lock", old, lock_to) for it, old in snaps])


    def unlock_all(self):
        """잠긴 객체는 선택이 안 돼 개별 우클릭으로 못 푸므로, 빈 영역 메뉴에 두는 탈출구."""
        locked = [it for it in self._zorder_pool() if getattr(it, "_locked", False)]
        if not locked:
            return
        snaps = [(it, True) for it in locked]
        for it in locked:
            self._set_item_lock_flags(it, False)
        self._push_entry([("mut", it, "lock", old, False) for it, old in snaps])

