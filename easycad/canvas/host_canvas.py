"""CanvasWindow 믹스인 — 펜/브러시·현재 도구·배지 번호·편집모드·씬 변경 리라우팅 등 핵심 캔버스 상태 플루밍.

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




class _CanvasMixin:
    def _on_scene_changed(self, region):
        """[성능 조사 2026-07-30] scene.changed가 넘겨주는 region(실제 변경 영역)을 무시하고
        씬의 모든 바인딩 화살표를 매번 전부 reroute하던 게 다중선택 드래그 버벅임의 핵심
        원인이었다(cProfile 실측: 박스 40+화살표 39짜리 작은 씬에서도 15프레임에 reroute 자체
        69ms). region과 화살표 자신의 (여유 있는) bbox가 겹칠 때만 reroute — 바인딩 도형이
        움직인 경우든, 무관한 장애물이 경로 근처로 들어와 A* 회피를 재트리거해야 하는 경우든
        둘 다 화살표 자신의 bbox 기준으로 커버된다(바인딩 도형만 보면 장애물-회피 케이스를 놓침).
        region=None은 필터 없이 전부 재검토(테스트 등에서 실제 시그널 없이 강제 호출할 때 쓰는
        기존 관례 — 실제 scene.changed 시그널은 항상 리스트를 준다)."""
        if self._rerouting:
            return  # 재진입 가드 — reroute가 유발한 changed로 되돌아오지 않게
        if getattr(self._view, "_drawing", False):
            return  # 화살표 그리는 중엔 _update_arrow_draw가 tip을 주도 — 간섭 방지
        if getattr(self._view, "_place", None) is not None:
            return  # 클릭 배치 중엔 배치 로직이 끝점을 주도 — 간섭 방지
        if region is None:
            union = None
        else:
            union = QRectF()
            for r in region:
                union = union.united(r)
            if union.isEmpty():
                return
        margin = _PolyArrowItem._ROUTE_CLEARANCE  # 기존 장애물-회피 여유와 동일 감도로 재사용
        self._rerouting = True
        try:
            for it in self._scene.items():
                # 곡선화살표(_ArrowItem)·직선화살표(_PolyArrowItem) 모두 지속 연결 리라우트.
                if isinstance(it, (_ArrowItem, _PolyArrowItem)) and it.has_binding():
                    if union is None or it.sceneBoundingRect().adjusted(
                            -margin, -margin, margin, margin).intersects(union):
                        it.reroute(pin_pred=self._make_pin_pred(it))
        finally:
            self._rerouting = False

    @staticmethod

    @staticmethod
    def _make_pin_pred(arrow):
        # 끝점 idx를 도형에 재고정할지: 붙은 도형과 화살표가 '같은 선택'으로 함께 움직이면
        # 강체(재고정 안 함), 아니면 붙은 채 늘림. → 사용자 합의 규칙.
        def pred(idx):
            sh = arrow._bound(idx)
            if sh is not None and arrow.isSelected() and sh.isSelected():
                return False
            return True
        return pred

    # ---- owner 인터페이스 ---------------------------------------------------

    def is_edit_mode(self) -> bool:
        return True


    def toggle_edit_mode(self):
        pass  # 단일 모드 앱 — 항상 편집


    def _on_escape(self):
        pass  # Phase 0: ESC로 앱 닫지 않음


    def make_pen(self) -> QPen:
        pen = QPen(QColor(self.current_color))
        pen.setWidthF(float(self.current_width))
        pen.setStyle(self.current_style)   # [M2] sticky 선스타일 반영
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen


    def make_brush(self) -> QBrush:
        """[신규기능] make_pen과 대칭 — 새 도형(rect/ellipse/symbol)의 sticky 채움색.
        기본 None=투명(NoBrush), 지금까지의 동작 불변."""
        if self.current_fill is None:
            return QBrush(Qt.BrushStyle.NoBrush)
        return QBrush(QColor(self.current_fill))


    def set_tool(self, key):
        # 도구를 바꾸면 진행 중이던 클릭 배치는 폐기(반쯤 그린 도형이 남지 않게).
        view = getattr(self, "_view", None)
        if view is not None:
            view._cancel_place()
        self.current_tool = key
        for k, b in self._tool_buttons.items():
            # [화살표 통합] 화살표 버튼 1개가 내부 두 도구(arrow·sarrow)를 대표한다.
            b.setChecked(k == key or (k == "arrow" and key == "sarrow"))
        # 왼쪽 「도형」 팔레트 버튼 동기화: 기본(네모·원)은 key 직접, 심볼은 sym:kind.
        for k, b in getattr(self, "_shape_tool_buttons", {}).items():
            b.setChecked(k == key)
        for k, b in getattr(self, "_sym_buttons", {}).items():
            b.setChecked(f"sym:{k}" == key)


    def next_badge_number(self) -> int:
        self._badge_n += 1
        return self._badge_n


    def adjust_item_property(self, item, step: int):
        # [M2] Shift+휠 두께 조절도 저널에 실어 되돌릴 수 있게 한다(이전엔 미추적).
        # 연속 굴림은 (아이템별) coalesce_key로 undo 1스텝에 병합.
        before = item.capture_state()
        if isinstance(item, (_ArrowItem, _PolyArrowItem)):
            new_w = max(1, item._width + step)
            item.apply_width(new_w)
        elif hasattr(item, "pen"):
            new_w = max(1.0, item.pen().widthF() + step)
            item.apply_width(new_w)
        else:
            return
        self.push_undo_state([(item, before)], coalesce_key=("width", id(item)))
        self.current_width = float(new_w)   # [M2 #A] 바꾼 두께를 다음 도형 기본값으로(sticky)
        self._refresh_properties()          # [M2 #3] 속성 패널 값 실시간 반영

    # 줌 (커서 기준 — 뷰가 AnchorUnderMouse)
