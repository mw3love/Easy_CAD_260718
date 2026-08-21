"""CanvasWindow 믹스인 — 속성(색·채움·두께·선스타일·폰트) 편집 + 속성 dock 표시/스타일 복사(format painter).

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
from easycad.canvas.host_widgets import _current_icon_color, _arrow_kind_of
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document, load_document_layers
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)
from easycad.canvas.host_widgets import _TYPE_NAMES, _RECENT_COLOR_MAX, _ARROW_KIND_TOOL, _ColorGridPopup

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




class _StyleMixin:
    def _edit_items(self, targets, fn, key=None):
        """선택 대상 targets에 fn을 적용하고 하나의 undo 엔트리(state)로 저널에 싣는다.
        key가 있으면 연속 편집(스핀박스 드래그)을 undo 1스텝으로 병합."""
        if self._pf_updating or not targets:
            return
        snaps = [(it, it.capture_state()) for it in targets]
        for it in targets:
            fn(it)
        self.push_undo_state(snaps, coalesce_key=key)
        self._refresh_properties()


    def arm_arrow_tool(self):
        """[화살표 통합] 사용자가 '화살표'를 무장하는 단일 진입점(툴바 버튼·단축키 3·9).
        현재 종류(sticky)가 내부 도구를 정한다 — 곡선·직선=arrow, 직각=sarrow. 이미 화살표가
        무장돼 있으면 끈다(토글). set_tool은 리터럴로 남겨 두고(테스트·내부 호출이 정확히 그 도구를
        받게) 이 메서드만 종류→도구 변환을 담당한다."""
        if self.current_tool in ("arrow", "sarrow"):
            self.set_tool(None)
            return
        self.set_tool(_ARROW_KIND_TOOL.get(self.current_arrow_kind, "arrow"))


    def _refresh_arrow_tool_button(self):
        """[화살표 통합] 툴바·도구(&T) 메뉴의 화살표 아이콘을 현재 종류에 맞춘다 —
        직각이면 직각 커넥터 아이콘."""
        icon = _tool_icon(_ARROW_KIND_TOOL.get(self.current_arrow_kind, "arrow"),
                          _current_icon_color())
        btn = getattr(self, "_tool_buttons", {}).get("arrow")
        if btn is not None:
            btn.setIcon(icon)
        act = getattr(self, "_tool_menu_actions", {}).get("arrow")
        if act is not None:
            act.setIcon(icon)


    def _set_current_color(self, color: QColor):
        """[M2 #A] 현재 색을 갱신, 새 도형·화살표에 반영. [2026-08-02] 상단 도구 아이콘은
        디자인 베이크오프 2라운드로 코랄 고정 스타일이 돼 더 이상 draw-color를 반영하지
        않는다 — 예전엔 여기서 아이콘을 다시 칠했지만 이제 그 루프는 불필요.
        [실사용 피드백 2026-08-18] 사용자가 직접 고른 색이므로 이제부터 테마 전환에
        안 따라간다 — `_color_is_default`를 내려 `_apply_theme`의 자동 갱신 대상에서 뺀다."""
        self.current_color = QColor(color)
        self._color_is_default = False


    def _show_color_grid_popup(self, anchor: QWidget, initial, allow_none: bool,
                                show_alpha: bool, title: str, on_pick):
        """[신규기능 · 색 선택 UX 단순화] 스와치 클릭 시 무거운 QColorDialog 대신 먼저 이
        그리드 팝업(무채색+기본색 3단 + '다른 색…')을 anchor 아래에 띄운다. '다른 색…'을
        고르면 그 안에서 왼쪽 열(기본색 그리드)만 숨긴 QColorDialog로 폴백한다(선·채움 동일 UI,
        2026-07-31 통일 — 이전엔 채움만 이렇게 하고 선 색은 OS 네이티브 다이얼로그를 그대로 써서
        둘의 인터페이스가 달라 보였다)."""
        pop = _ColorGridPopup(self, initial, allow_none, show_alpha, title, on_pick,
                              recent=self._recent_colors, on_custom_picked=self._remember_recent_color)
        pop.adjustSize()
        pop.move(anchor.mapToGlobal(QPoint(0, anchor.height() + 2)))
        pop.show()
        self._last_color_popup = pop   # 테스트 훅 — 실사용 흐름엔 영향 없음


    def _load_recent_colors(self) -> list[QColor]:
        raw = QSettings("EasyCAD", "EasyCAD").value("recent_colors", [], type=list) or []
        return [QColor(h) for h in raw if QColor(h).isValid()][:_RECENT_COLOR_MAX]


    def _remember_recent_color(self, col: QColor):
        """[신규기능] "다른 색…"에서 고른 색을 그리드 팝업의 "최근 사용한 색" 열에 남긴다
        (그리드 스와치를 직접 클릭한 건 대상 아님 — 이미 항상 보이는 색이라 기억할 필요 없음).
        QSettings에 영구 저장(다크모드 설정과 같은 관례) — 앱을 재시작해도 유지된다."""
        col = QColor(col)
        key = col.name(QColor.NameFormat.HexArgb)
        self._recent_colors = [c for c in self._recent_colors
                               if c.name(QColor.NameFormat.HexArgb) != key]
        self._recent_colors.insert(0, col)
        self._recent_colors = self._recent_colors[:_RECENT_COLOR_MAX]
        QSettings("EasyCAD", "EasyCAD").setValue(
            "recent_colors", [c.name(QColor.NameFormat.HexArgb) for c in self._recent_colors])


    def _edit_color(self):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "apply_color")]
        if not sel:
            return
        init = self._read_props(sel[0])["color"] or QColor("#000000")
        anchor = self.sender() if isinstance(self.sender(), QWidget) else self._pf_color

        def on_pick(col):
            if col is None:   # 선 색은 "없음" 미지원 — 팝업이 allow_none=False라 실제로 안 옴
                return
            self._edit_items(sel, lambda it: it.apply_color(QColor(col)))
            self._set_current_color(col)   # [M2 #A] 다음 도형 기본 색으로(sticky)

        self._show_color_grid_popup(anchor, init, False, False, "색 선택", on_pick)


    def _edit_fill(self):
        """[신규기능] 채움색 선택 — 스와치 클릭. 그리드 팝업의 "다른 색…"은 알파 채널 허용
        (반투명 채움, .ecad가 이미 HexArgb로 왕복 지원 — document.py 무변경).
        [버그 수정] 텍스트(_TextItem/_ConnectorLabel)는 apply_fill이 없어 이 스와치가 항상
        비활성으로 굳어 있었다 — 대신 이미 구현돼 있던 `set_bg`(자막/스티커 배경, 지금까지
        UI에 안 걸려 있던 죽은 기능)를 "채움"이 그대로 대신 쓰도록 연결한다(실사용 보고:
        "속성에서 채움도 안되는듯")."""
        sel = [it for it in self._scene.selectedItems()
               if hasattr(it, "apply_fill") or hasattr(it, "set_bg")]
        if not sel:
            return
        init = self._read_props(sel[0])["fill"] or QColor("#ffffff")

        def on_pick(col):
            if col is None:
                self._clear_fill()
                return
            self._edit_items(sel, lambda it: it.apply_fill(QColor(col))
                             if hasattr(it, "apply_fill") else it.set_bg(QColor(col)))
            self.current_fill = QColor(col)   # sticky

        self._show_color_grid_popup(self._pf_fill, init, True, True, "채움색 선택", on_pick)


    def _clear_fill(self):
        """채움을 투명으로(None) — 그리드 팝업의 "없음" 항목이 호출(요청③: 별도 외부 버튼
        대신 팝업 안 항목)."""
        sel = [it for it in self._scene.selectedItems()
               if hasattr(it, "apply_fill") or hasattr(it, "set_bg")]
        if not sel:
            return
        self._edit_items(sel, lambda it: it.apply_fill(None)
                         if hasattr(it, "apply_fill") else it.set_bg(None))
        self.current_fill = None


    def _edit_width(self, val):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "apply_width")]
        self._edit_items(sel, lambda it: it.apply_width(float(val)),
                         key=("width", tuple(sorted(id(it) for it in sel))))
        if sel:
            self.current_width = float(val)   # [M2 #A] 다음 도형 기본 두께로(sticky)


    def _edit_style(self, _idx):
        style = self._pf_style.currentData()
        # [M2 #3] pen 기반 도형 + 화살표(apply_style) 모두 대상.
        sel = [it for it in self._scene.selectedItems()
               if hasattr(it, "pen") or hasattr(it, "apply_style")]
        def apply(it):
            if hasattr(it, "apply_style"):   # 화살표(_ArrowItem/_PolyArrowItem)
                it.apply_style(style)
            else:
                p = it.pen(); p.setStyle(style); it.setPen(p)
        self._edit_items(sel, apply)
        if sel and style is not None:
            self.current_style = style   # [M2 #A] 다음 도형 기본 선스타일로(sticky)


    def _edit_arrow_kind_combo(self, _idx):
        """[실사용 피드백 2026-08-20] 속성패널의 '화살표' 종류 콤보(옛 QToolButton+QMenu를
        아이콘 콤보로 통일) — _pf_updating 중(=_refresh_properties가 현재 선택값으로 콤보를
        동기화하는 중)엔 되돌아오는 신호를 무시한다(_edit_style과 동일 관례, _floating_
        set_arrow_kind 자체엔 이 가드가 없어 여기서 걸어야 함)."""
        if self._pf_updating:
            return
        kind = self._pf_routing_btn.currentData()
        if kind is not None:
            self._floating_set_arrow_kind(kind)


    def _edit_font(self, val):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "apply_font_size")]
        self._edit_items(sel, lambda it: it.apply_font_size(int(val)),
                         key=("font", tuple(sorted(id(it) for it in sel))))

    @staticmethod

    @staticmethod
    def _read_props(item) -> dict:
        """아이템의 색·두께·선스타일·폰트를 duck-typing으로 읽는다(화살표=_color/_width,
        도형=pen(), 텍스트=font()). 없는 값은 None."""
        col = getattr(item, "_color", None)
        if col is None and hasattr(item, "pen"):
            try: col = item.pen().color()
            except Exception: col = None
        # [버그 수정] 텍스트(_TextItem/_ConnectorLabel)는 _color도 pen()도 없어(글자색은
        # QGraphicsTextItem.defaultTextColor() 소유) 위 두 분기가 항상 실패 → color가 계속
        # None으로 읽혀 "색" 스와치가 비활성화된 채 굳어 있었다(실사용 보고: 텍스트·화살표
        # 라벨 선택 시 색 편집이 아예 안 먹힘).
        if col is None and hasattr(item, "defaultTextColor"):
            try: col = item.defaultTextColor()
            except Exception: col = None
        width = getattr(item, "_width", None)
        if width is None and hasattr(item, "pen"):
            try: width = item.pen().widthF()
            except Exception: width = None
        style = getattr(item, "_style", None)   # [M2 #3] 화살표 몸통 선스타일
        if style is None and hasattr(item, "pen"):
            try: style = item.pen().style()
            except Exception: style = None
        font = None
        if hasattr(item, "font"):
            try:
                fs = item.font().pointSizeF()
                font = fs if fs and fs > 0 else None
            except Exception:
                font = None
        # [신규기능] 채움색 — rect/ellipse/symbol은 apply_fill(브러시), 텍스트류는 set_bg
        # (자막/스티커 배경 — 버그 수정으로 "채움" 스와치가 대신 이걸 쓰도록 연결됨, 위
        # _edit_fill 참조)로 판정. fill=None은 "지원하지만 지금 투명"이라 has_fill과
        # 분리해야 한다(color/width처럼 항상 값이 있는 속성과 달리, 채움은 "이 항목이
        # 채움 자체를 지원하는가"를 따로 알아야 함).
        has_fill = hasattr(item, "apply_fill") or hasattr(item, "set_bg")
        fill = None
        if hasattr(item, "apply_fill"):
            try:
                fill = (QColor(item.brush().color())
                       if item.brush().style() != Qt.BrushStyle.NoBrush else None)
            except Exception:
                fill = None
        elif hasattr(item, "set_bg"):
            bg = getattr(item, "_bg", None)
            fill = QColor(bg) if bg is not None else None
        # [실사용 피드백 2026-08-21] `_TYPE_NAMES`엔 `_SymbolItem` 클래스 하나에 "심볼"
        # 한 단어뿐이라, 삼각형·판단·저장소 등 19종 심볼이 전부 그 이름으로 뭉개졌다 —
        # 실제 종류(`_kind`)가 이미 있으니 그대로 쓴다("종류" 콤보가 그 값을 그대로 표시).
        if isinstance(item, _SymbolItem) and item._kind in _SYMBOL_KINDS:
            type_name = _SYMBOL_KINDS[item._kind][0]
        else:
            type_name = _TYPE_NAMES.get(type(item).__name__, "객체")
        return {
            "type": type_name,
            "color": QColor(col) if col is not None else None,
            "width": width, "style": style, "font": font,
            "has_fill": has_fill, "fill": fill,
        }

    # ---- 스타일 복사(format painter) — deep-interview 2026-07-28 -------------

    def _capture_paint_style(self, item) -> dict:
        """[스타일 복사] 서식만 캡처(텍스트 '내용'은 제외) — color/width/style/font는
        속성 dock이 이미 쓰는 _read_props(pen 기반↔화살표 정규화)를 그대로 재사용(규칙 2
        손안의 카드), tcolor·bg·head(화살표 방향)만 추가로 얹는다."""
        st = dict(self._read_props(item))
        if hasattr(item, "setDefaultTextColor"):
            st["tcolor"] = QColor(item.defaultTextColor())
        if hasattr(item, "toPlainText"):
            st["bg"] = QColor(item._bg) if getattr(item, "_bg", None) is not None else None
        if hasattr(item, "_head_at_end") and hasattr(item, "set_head_at_end"):
            st["head"] = item._head_at_end
        return st


    def _apply_paint_style(self, item, st: dict):
        """[스타일 복사] 타입이 달라도 항상 적용(deep-interview 확정) — 없는 속성은 조용히
        건너뜀(hasattr 가드). 선스타일은 화살표(apply_style)/pen 기반을 갈라 _edit_style과
        동일하게 처리."""
        if st.get("color") is not None and hasattr(item, "apply_color"):
            item.apply_color(QColor(st["color"]))
        if st.get("width") is not None and hasattr(item, "apply_width"):
            item.apply_width(float(st["width"]))
        if st.get("style") is not None:
            if hasattr(item, "apply_style"):
                item.apply_style(st["style"])
            elif hasattr(item, "pen"):
                p = item.pen(); p.setStyle(st["style"]); item.setPen(p)
        if st.get("font") is not None and hasattr(item, "apply_font_size"):
            item.apply_font_size(int(st["font"]))
        # [신규기능] 채움 — "지원 대상일 때만" 옮긴다(has_fill로 판정). fill 값 자체는 None(투명)도
        # 유효한 서식이라 color/width와 달리 None 체크 없이 그대로 적용.
        if st.get("has_fill") and hasattr(item, "apply_fill"):
            item.apply_fill(st.get("fill"))
        if "tcolor" in st and hasattr(item, "setDefaultTextColor"):
            item.setDefaultTextColor(st["tcolor"])
        if "bg" in st and hasattr(item, "set_bg"):
            item.set_bg(st["bg"])
        if "head" in st and hasattr(item, "set_head_at_end"):
            item.set_head_at_end(st["head"])


    def copy_style_from_selection(self):
        sel = self._scene.selectedItems()
        if len(sel) != 1:
            self.statusBar().showMessage(
                "스타일 복사 — 도형을 하나만 선택하세요" if sel else "스타일 복사 — 먼저 도형을 선택하세요",
                2500)
            return
        self._style_clip = self._capture_paint_style(sel[0])
        self.statusBar().showMessage("스타일 복사됨", 2000)


    def paste_style_to_selection(self):
        st = getattr(self, "_style_clip", None)
        if st is None:
            self.statusBar().showMessage("붙여넣을 스타일이 없습니다 — 먼저 스타일을 복사하세요", 2500)
            return
        sel = self._scene.selectedItems()
        if not sel:
            return
        snaps = [(it, it.capture_state()) for it in sel]
        for it in sel:
            self._apply_paint_style(it, st)
        self.push_undo_state(snaps)
        self.statusBar().showMessage(f"스타일 붙여넣기 — {len(sel)}개", 2000)


    def _swatch_css(self, color: QColor | None) -> str:
        """스와치 버튼 배경 — 단색이면 그 색, 혼합/없음이면 체크무늬 느낌의 중립 표시."""
        if color is None:
            return "background:transparent; border:1px solid #888; border-radius:3px;"
        return (f"background:{color.name()}; border:1px solid #888; border-radius:3px;")


    def _resize_props_panel(self):
        """행 표시가 바뀐 뒤 `_props_panel`을 새 콘텐츠 크기로 맞춘다.
        ⚠ [2026-08-01] `_props_form.activate()` 하나만으론 세로 길이가 가끔 줄지 않고 이전
        선택(예: 화살표 9행)의 큰 크기로 눌어붙는 경우가 있었다(실측: offscreen에서 재현 —
        `_props_form`은 `content` 위젯의 레이아웃이고, `content`는 `_props_panel._body`의
        `_body_layout` 안에, 그 `_body`는 다시 `_props_panel` 자신의 최상위 레이아웃 안에
        중첩돼 있는데, `setRowVisible()`이 만드는 크기변경 통지가 이 조상 레이아웃들에게는
        Qt 이벤트루프가 처리하는 지연 포스트 이벤트로만 전달돼, 같은 시그널 핸들러 안에서
        즉시 `adjustSize()`를 부르면 조상 레이아웃의 캐시가 아직 옛 값 그대로일 수 있었다).
        중첩된 각 레이아웃을 안쪽부터 바깥쪽까지 전부 명시적으로 `activate()`해 이벤트루프
        타이밍과 무관하게 항상 최신 크기로 즉시 반영한다."""
        self._props_form.activate()
        self._props_panel._body.layout().activate()
        self._props_panel.layout().activate()
        self._props_panel.adjustSize()


    def _refresh_properties(self):
        """선택에 맞춰 편집 컨트롤 값·활성 상태를 채운다. _pf_updating로 편집 시그널을 막아
        프로그램적 세팅이 다시 편집 핸들러를 트리거하지 않게 한다(피드백 차단)."""
        self._pf_updating = True
        try:
            sel = self._scene.selectedItems()
            has = bool(sel)
            for w in (self._pf_color, self._pf_width, self._pf_style, self._pf_font):
                w.setEnabled(has)
            if not has:
                self._pf_type.setText("—")
                self._pf_type_stack.setCurrentWidget(self._pf_type)   # [종류+도형 통합] 라벨 페이지로
                self._pf_color_val.setText("—")
                self._pf_color.setStyleSheet(self._swatch_css(None))
                self._pf_fill.setEnabled(False)
                self._pf_fill_val.setText("—")
                self._pf_fill.setStyleSheet(self._swatch_css(None))
                self._pf_hint.setText("객체를 선택하면 속성을 편집할 수 있습니다.")
                for w in (self._pf_routing_btn, self._pf_radius, self._pf_dir_btn):
                    self._props_form.setRowVisible(w, False)
                # 아래 "선택 있음" 분기와 동일 — 행을 숨긴 뒤 패널을 그 크기로 다시 줄이지
                # 않으면, 직전에 화살표 등 확장 행이 있던 선택에서 커진 패널 크기가 선택
                # 해제 후에도 그대로 남아 빈 공간만 길게 남는다.
                self._resize_props_panel()
                self._reposition_panels()
                return
            props = [self._read_props(it) for it in sel]
            types = {p["type"] for p in props}
            if len(types) != 1:
                self._pf_type.setText(f"{len(sel)}개 · 혼합")
            elif len(sel) > 1:
                # [실사용 피드백 2026-08-18] 단일종류 다중선택도 개수를 보여준다 —
                # 이전엔 혼합 선택일 때만 개수를 붙여, 같은 종류 3개를 선택해도 "사각형"만
                # 표시돼 몇 개가 선택됐는지 알 수 없었다.
                self._pf_type.setText(f"{next(iter(types))} {len(sel)}개")
            else:
                self._pf_type.setText(next(iter(types)))
            self._pf_hint.setText("")

            # 색 — 스와치 + hex(혼합이면 표시만).
            cols = [p["color"] for p in props if p["color"] is not None]
            uniform = cols and len(cols) == len(props) and len({c.name() for c in cols}) == 1
            self._pf_color.setEnabled(bool(cols))
            self._pf_color.setStyleSheet(self._swatch_css(cols[0] if uniform else None))
            self._pf_color_val.setText(cols[0].name() if uniform
                                       else ("혼합" if cols else "—"))

            # [신규기능] 채움 — 지원 대상(has_fill)에서만 균일성 판정. None(투명)도 유효한 값이라
            # color처럼 "값 있는 것만 필터"하면 안 되고, has_fill인 항목 전부를 모아야 한다.
            fillable = [p["fill"] for p in props if p["has_fill"]]
            has_fillable = bool(fillable)
            self._pf_fill.setEnabled(has_fillable)
            if has_fillable:
                names = {(f.name(QColor.NameFormat.HexArgb) if f is not None else None)
                        for f in fillable}
                uniform_fill = len(names) == 1
                cur = fillable[0] if uniform_fill else None
                self._pf_fill.setStyleSheet(self._swatch_css(cur))
                if not uniform_fill:
                    self._pf_fill_val.setText("혼합")
                elif cur is None:
                    self._pf_fill_val.setText("없음")
                else:
                    self._pf_fill_val.setText(cur.name())
            else:
                self._pf_fill.setStyleSheet(self._swatch_css(None))
                self._pf_fill_val.setText("—")

            # 두께 — 균일하면 값, 아니면 대상 있음만 활성(값은 첫 대상).
            widths = [p["width"] for p in props if p["width"] is not None]
            self._pf_width.setEnabled(bool(widths))
            if widths:
                self._pf_width.setValue(widths[0])

            # 선스타일 — pen 기반만. 대상 없으면 비활성.
            styles = [p["style"] for p in props if p["style"] is not None]
            self._pf_style.setEnabled(bool(styles))
            if styles:
                i = self._pf_style.findData(styles[0])
                self._pf_style.setCurrentIndex(i if i >= 0 else 0)

            # 폰트 — 텍스트/라벨만.
            fonts = [p["font"] for p in props if p["font"] is not None]
            self._pf_font.setEnabled(bool(fonts))
            if fonts:
                self._pf_font.setValue(int(round(fonts[0])))

            # [미니패널 통합] 타입 전용 행 노출 — 옛 _reposition_floating_toolbar의 판정을 그대로.
            show_swap = len(sel) == 1 and isinstance(sel[0], (_RectItem, _EllipseItem, _SymbolItem))
            show_routing = len(sel) == 1 and isinstance(sel[0], (_ArrowItem, _PolyArrowItem))
            show_dir = any(isinstance(it, (_ArrowItem, _PolyArrowItem)) for it in sel)
            curved = (len(sel) == 1 and isinstance(sel[0], _PolyArrowItem) and sel[0]._is_ortho())
            # [실사용 피드백 2026-08-20, 종류+도형 통합] 바꿀 수 있는 도형이면 '종류' 행
            # 자체가 바꾸기 버튼(현재 종류 표시 + 클릭 시 변경 메뉴)으로, 아니면 읽기전용
            # 라벨로. 별도 '도형' 행은 더 이상 없다.
            if show_swap:
                self._pf_swap_btn.setText(f"{self._pf_type.text()} ▾")
                self._pf_type_stack.setCurrentWidget(self._pf_swap_btn)
            else:
                self._pf_type_stack.setCurrentWidget(self._pf_type)
            self._props_form.setRowVisible(self._pf_routing_btn, show_routing)
            self._props_form.setRowVisible(self._pf_radius, curved)
            self._props_form.setRowVisible(self._pf_dir_btn, show_dir)
            if show_routing:   # [아이콘화] 콤보 현재 선택을 실제 화살표 종류로 동기화
                i = self._pf_routing_btn.findData(_arrow_kind_of(sel[0]))
                if i >= 0:
                    self._pf_routing_btn.setCurrentIndex(i)
            # ⚠ [2026-07-31, 진짜 원인 확정 — 실기기에서 직접 반복 재현해 확인] 선택 종류가
            # 바뀌어 행 개수가 달라져도(예: 네모 7행 → 화살표 9행) `_props_panel` 위젯 자체의
            # 크기(`adjustSize()`로만 커짐)는 창 리사이즈 때만 호출되는 `_reposition_panels()`
            # 에서만 갱신됐다 — `_refresh_properties()`는 행 노출만 토글하고 패널을 그 새 크기에
            # 맞게 키우질 않아, 늘어난 행들이 옛 크기의 좁은 패널 안에 짓눌려 들어갔다(실측:
            # 네모 선택 시 두께 행 21px, 화살표 선택 시 13px인데 패널 size()는 두 경우 완전히
            # 동일 — 창을 리사이즈하면 그제야 `_reposition_panels()`가 불려 패널이 커지고
            # 그 뒤로 유지되는 것과 정확히 일치). [2026-08-01 갱신] 이 호출은 `_resize_props_panel()`
            # 로 옮겼다 — 축소 방향(화살표→선택해제)에선 `_props_form.activate()`만으론 조상
            # 레이아웃(`_body_layout`·패널 자체 레이아웃) 캐시가 안 갱신돼 큰 크기에 눌어붙는
            # 별도 버그가 있었다(상세는 `_resize_props_panel` docstring).
            self._resize_props_panel()
            self._reposition_panels()
            if curved:
                self._pf_radius.blockSignals(True)   # 값 동기화가 편집 신호로 되돌아오지 않게
                self._pf_radius.setValue(int(round(sel[0]._curve_r)))
                self._pf_radius.blockSignals(False)
        finally:
            self._pf_updating = False

    # ---- 지속 연결 리라우트 -------------------------------------------------
