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
    def _sync_geom_snapshot(self) -> QRectF | None:
        """[성능수정 2026-08-07] `self._geom_snapshot`(item→직전 타이트 rect)과 현재 씬을 비교해
        실제로 지오메트리(이동/리사이즈/생성/삭제)가 바뀐 아이템들의 rect 합집합만 반환한다.
        `sceneBoundingRect()`가 아니라 `_content_rect()`(선택 시 핸들 여백 미포함)를 씬좌표로
        매핑해 비교하므로, 클릭으로 선택 상태만 바뀌어 boundingRect가 핸들 여백만큼 커지는 것은
        '변경 없음'으로 정확히 걸러진다(아래 `_on_scene_changed` 버그의 근본 원인).

        [성능수정 2026-08-08] 화살표(`_ArrowItem`/`_PolyArrowItem`)는 애초에 이 스냅샷에서
        제외한다 — `_obstacle_rects()`(도형만 반환, 2026-07-26 "화살표-화살표 soft 회피 철회"
        결정)와 `set_bound()` 실사용(도형만 바인딩 대상, "도형만 지속 바인딩")이 이미 "화살표는
        다른 화살표의 라우팅에 절대 영향을 못 준다"를 보장하므로, 화살표 자신의 지오메트리
        변경을 여기서 집계해 봐야 다른 화살표를 트리거할 이유가 없다(트리거해도 입력이 그대로라
        결과가 항상 동일 — 순수 낭비). 세그먼트 알약 드래그처럼 화살표 자신의 pts가 매 프레임
        바뀌는 상호작용에서 이 낭비가 밀집 도면 기준 reroute 캐스케이드 1회 초 단위로 커졌다."""
        changed = None
        changed_n = 0   # [성능 최적화 2026-08-08] 아래 _on_scene_changed 주석 참조
        current = set()
        for it in self._scene.items():
            if isinstance(it, (_ArrowItem, _PolyArrowItem)):
                continue
            current.add(it)
            cr = getattr(it, "_content_rect", None)
            rect = it.mapRectToScene(cr()) if cr is not None else it.sceneBoundingRect()
            prev = self._geom_snapshot.get(it)
            if prev is None or prev != rect:
                self._geom_snapshot[it] = QRectF(rect)
                delta = rect if prev is None else prev.united(rect)
                changed = delta if changed is None else changed.united(delta)
                changed_n += 1
        for it in [k for k in self._geom_snapshot if k not in current]:
            delta = self._geom_snapshot.pop(it)
            changed = delta if changed is None else changed.united(delta)
            changed_n += 1
        self._last_geom_change_count = changed_n
        return changed

    def _on_scene_changed(self, region):
        """[성능 조사 2026-07-30] scene.changed가 넘겨주는 region(실제 변경 영역)을 무시하고
        씬의 모든 바인딩 화살표를 매번 전부 reroute하던 게 다중선택 드래그 버벅임의 핵심
        원인이었다(cProfile 실측: 박스 40+화살표 39짜리 작은 씬에서도 15프레임에 reroute 자체
        69ms). region과 화살표 자신의 (여유 있는) bbox가 겹칠 때만 reroute — 바인딩 도형이
        움직인 경우든, 무관한 장애물이 경로 근처로 들어와 A* 회피를 재트리거해야 하는 경우든
        둘 다 화살표 자신의 bbox 기준으로 커버된다(바인딩 도형만 보면 장애물-회피 케이스를 놓침).
        region=None은 필터 없이 전부 재검토(테스트 등에서 실제 시그널 없이 강제 호출할 때 쓰는
        기존 관례 — 실제 scene.changed 시그널은 항상 리스트를 준다).

        [성능수정 2026-08-07] 위 region은 '리페인트가 일어난 영역'일 뿐이라 실제 지오메트리
        변경과 선택강조(핸들 표시) 리페인트를 구분 못 했다 — 화살표가 캔버스 전역에 넓게 뻗은
        밀집 도면에서는 도형 하나를 선택만 해도(이동 없음) 그 리페인트 region이 거의 모든
        화살표 bbox와 겹쳐 전체 재라우팅이 돌았다(KBS 실도면 재현: 클릭 5회 → reroute 39회 →
        56초, `tools/profile_reroute.py`). region 대신 `_sync_geom_snapshot()`이 계산한 '실제로
        움직인 아이템들의 rect 합집합'으로 화살표 겹침을 판정해, 순수 선택 클릭은 아예 reroute를
        건너뛴다. region=None(테스트 강제호출)은 기존처럼 무조건 전체 재검토로 유지."""
        if self._rerouting:
            return  # 재진입 가드 — reroute가 유발한 changed로 되돌아오지 않게
        if getattr(self._view, "_drawing", False):
            return  # 화살표 그리는 중엔 _update_arrow_draw가 tip을 주도 — 간섭 방지
        if getattr(self._view, "_place", None) is not None:
            return  # 클릭 배치 중엔 배치 로직이 끝점을 주도 — 간섭 방지
        geom_changed = self._sync_geom_snapshot()
        if region is None:
            union = None
        else:
            union = QRectF()
            for r in region:
                union = union.united(r)
            if union.isEmpty():
                return
            if geom_changed is None:
                return  # 실제 지오메트리 변경 없음(순수 선택 등 리페인트만) — reroute 불필요
            union = geom_changed
        margin = _PolyArrowItem._ROUTE_CLEARANCE  # 기존 장애물-회피 여유와 동일 감도로 재사용
        self._rerouting = True
        try:
            # [성능 최적화 2026-08-08] `self._scene.items()`(전체 ~1600개) 순회 대신 Qt의 BSP
            # 트리 공간 인덱스로 후보를 좁힌다 — `_rb_preview_hits()`(core_view.py)가 이미 같은
            # 목적으로 쓰는 검증된 패턴(규칙 2 손안의 카드: Qt가 이미 제공)을 재사용. 정확성
            # 근거: 아래 조건은 원래도 "화살표 bbox를 margin만큼 부풀려 union과 겹치는가"였다 —
            # 대칭 패딩 AABB 교차는 "A를 부풀려 B와 겹침"과 "B를 부풀려 A와 겹침"이 동치이므로,
            # union을 margin만큼 부풀린 사각형으로 `scene.items(rect, Intersects...)`를 쿼리하면
            # 원래 조건을 만족할 수 있는 아이템 전부(그 이상은 아무것도 놓치지 않음)를 후보로
            # 얻는다. 그 후보만 아래에서 기존과 동일한 정밀 조건으로 재확인하므로 결과 집합은
            # 불변 — 인덱스 정확성은 `prepareGeometryChange()`가 보장(Stage2 캐싱 도입 시 전수
            # 확인한 것과 같은 계약).
            #
            # [실측 되돌림 — 다건 변경엔 전체스캔이 더 빠름] 처음엔 union이 있으면 항상 공간
            # 쿼리를 썼는데, 20개 도형 동시 드래그로 재측정하니 오히려 20.2→26.7ms로 악화됐다
            # (cProfile 확인: BSP `items(rect,mode)` 자체의 트리순회+리스트생성 오버헤드가, 변경
            # 영역이 넓어 후보를 별로 못 줄이는 경우엔 순수 `items()` 전체스캔보다 비쌌다 — 도형
            # 1개 드래그에선 반대로 8.2→5.9ms로 확실히 이겼다). 그래서 "이번 사이클에 실제로
            # 바뀐 아이템 수"(`_last_geom_change_count`, 위 `_sync_geom_snapshot`)가 적을 때만
            # 공간 쿼리를 쓴다 — 바뀐 아이템이 적으면 union도 좁아 공간 쿼리가 확실히 이기고,
            # 많으면(다중선택 드래그) 검증된 전체스캔으로 안전하게 폴백한다.
            _FEW_CHANGED = 4   # 실측 경계(1건=승, 20건=패)에서 넉넉히 보수적으로 잡은 값
            if union is None or self._last_geom_change_count > _FEW_CHANGED:
                candidates = self._scene.items()   # 강제 전체 재검토 / 다건 변경 — 검증된 경로
            else:
                query_rect = union.adjusted(-margin, -margin, margin, margin)
                candidates = self._scene.items(
                    query_rect, Qt.ItemSelectionMode.IntersectsItemBoundingRect)
            for it in candidates:
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
        for k, b in getattr(self, "_custom_sym_buttons", {}).items():   # [신규기능 §8-8]
            b.setChecked(f"customsym:{k}" == key)


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
