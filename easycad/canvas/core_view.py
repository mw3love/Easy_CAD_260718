"""_AnnotatorView — 무한캔버스 QGraphicsView 서브클래스. annotator_core.py(8169줄)
2026-08-02 분할분. 마우스/키 이벤트, 드래그 선택, 스냅, 팬/줌, 커넥터 프리뷰 등 사용자
입력을 실제 아이템·라우팅 조작으로 옮기는 상호작용 표면 — core_shapes.py의 아이템·기하·
라우팅 함수를 소비하기만 하고(단방향), 역참조는 없다(순환 없음, 안전하게 분리 가능했음).
"""
import heapq
import io
import math
import struct
import uuid

from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QLineF, QSize, QTimer, QEvent,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QBrush, QColor, QPainterPath,
    QPainterPathStroker, QPolygonF, QFont, QFontMetricsF, QIcon, QCursor,
    QConicalGradient,
)
from PyQt6.QtWidgets import (
    QWidget, QGraphicsScene, QGraphicsView, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsTextItem, QGraphicsItem, QHBoxLayout,
    QPushButton, QToolButton, QButtonGroup, QLabel, QLineEdit,
    QStyle, QStyleOptionGraphicsItem,
)

from easycad.theme import (
    BASE as _BG, SURFACE0 as _SURFACE0, SURFACE1 as _BORDER,
    SURFACE2 as _SURFACE2, TEXT as _TEXT, BLUE as _BLUE, SUBTEXT0 as _SUBTEXT,
    PEACH as _PEACH, GREEN as _GREEN,
)


from easycad.canvas.core_constants import *  # noqa: F401,F403
from easycad.canvas.core_shapes import *  # noqa: F401,F403

class _AnnotatorView(QGraphicsView):
    # [화살표 통합] 화살표는 도구 하나 → 단축키도 3 하나. 9는 비운다(사용자가 후속 전면 조정 예정).
    _SHORTCUTS = {
        Qt.Key.Key_1: "select", Qt.Key.Key_2: "rect", Qt.Key.Key_3: "arrow",
        Qt.Key.Key_4: "text", Qt.Key.Key_5: "ellipse", Qt.Key.Key_6: "line",
        Qt.Key.Key_7: "pen", Qt.Key.Key_8: "badge",
    }

    def __init__(self, scene: QGraphicsScene, owner):
        super().__init__(scene)
        self._owner = owner  # 호스트 위젯(CanvasWindow) — copy_selection/paste_selection 등 구현
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # [UX] 무한캔버스 + %줌 상태바 조합에서 스크롤바는 항상 켜진 채(씬이 사실상 무한이라
        # ScrollBarAsNeeded도 늘 표시됨)로 뜨는데 실제 이동은 손모드 드래그로 하므로 시각적 잡음만
        # 됨. 팬은 스크롤바 값을 직접 조작해 구현돼 있어(_win_drag_move) 정책만 꺼도 기능엔 무관.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self._drawing = False
        self._temp: QGraphicsItem | None = None
        # [우리 확장] 하이브리드 클릭 배치(투클릭/멀티클릭) 진행 상태 — 모든 도형 도구 공통.
        # press-drag-release로 끝나는 '드래그'와 달리 클릭으로 점을 놓으므로 _drawing/_temp와
        # 분리한다(release로 끝나지 않게). None=진행 중 아님. 2점 도구는 둘째 클릭이 확정,
        # 직선화살(sarrow)은 클릭마다 정점 추가·더블클릭/Enter 마무리. 마지막 점은 커서 추종.
        self._place: QGraphicsItem | None = None   # 배치 중 아이템
        self._place_tool: str | None = None        # 그 도구 키
        # 실제 press 지점(씬) — 드래그/클릭 판정 기준. self._start는 테두리 스냅으로 '점프'할 수
        # 있어(시작 스냅), 그걸로 이동량을 재면 가만히 클릭해도 드래그로 오인된다(→극소 화살표).
        self._press_scene = QPointF()
        self._start = QPointF()
        self._path: QPainterPath | None = None
        self._move_snap = None       # 드래그 이동 전 위치 스냅샷([(item, QPointF), ...]) — undo용
        # [편의기능] Shift+드래그 축 고정 — "h"(수평만)/"v"(수직만)/None(미고정). press마다 리셋.
        self._axis_lock = None
        # [2e] 스마트 정렬 가이드 — 단일 도형 이동 중 근처 도형과 모서리·중심 정렬 시 스냅+가상선.
        self._move_active = False    # 도형 드래그(이동/핸들) 진행 중(_snapshot_movable서 set)
        self._align_guides = []      # 그릴 가이드선 [("v", x, y0, y1) | ("h", y, x0, x1)]
        # 테두리 스냅(화살표 도구 전용) — 도형 테두리 어디든 최근접점에 붙음
        self._snap_preview = None    # 화살표 도구 유휴 시 커서 근처 테두리 최근접점(마커 표시), 씬 좌표 or None
        self._arrow_snap_exit = None # 그리는 화살표 시작이 테두리에 스냅됐으면 그 바깥 법선(이탈 접선), or None
        self._arrow_tip_snap = None  # 그리는 화살표 tip이 테두리에 스냅된 지점(씬 좌표) or None
        self._none_win_dragging = False  # 손 모드(도구 없음) 빈영역 좌드래그 = 창 이동 중
        # [Phase 6 M3 #16] 유휴 우클릭 재정의 — 드래그=팬 / 제자리 탭=컨텍스트 메뉴.
        # BUSY(무장·그리기 중)면 대신 취소(M2 탈출구). press 지점을 기록해 move/release로 분기한다.
        self._rmb_press = None            # 유휴 우클릭 press 지점(view) — None이면 팬/메뉴 후보 아님
        self._rmb_panning = False         # 임계 넘겨 팬이 시작됨
        # [우리 확장] 방향 감지 러버밴드(AutoCAD window/crossing) — Qt 기본 RubberBandDrag 대체.
        # 왼→오 = window(완전포함, 파란 실선) / 오→왼 = crossing(걸침, 초록 점선).
        self._rb_active = False           # 러버밴드 드래그 중
        self._rb_origin = None            # 시작점(view 좌표) — 방향 판정 기준
        self._rb_current = None           # 현재점(view 좌표)
        self._rb_base = []                # Shift 추가선택용 기존 선택 스냅샷
        self._rb_preview = set()          # [성능 조사 2026-07-30] 드래그 중 미리보기 후보(실제 선택 아님)
        # [M4-4] 직선화살표 세그먼트 hover 시 (item, seg_idx, 씬 최근접점) or None.
        # ortho 라우팅 sarrow의 변 위(정점 아님)에 커서 → 클릭·드래그로 그 변을 수직 이동.
        self._seg_add = None
        self._seg_drag = None   # [M4-4] 세그먼트 드래그 중인 sarrow(변 수직 이동)
        self._seg_undo = None
        # [열폭 드래그 2026-07-31] 선택된 표의 내부 열 경계선 hover/드래그 상태.
        self._table_col_add = None   # (item, boundary_idx) or None
        self._table_col_drag = None  # 드래그 중인 _TableItem or None
        self._table_col_undo = None
        # [우리 확장] 다중선택 그룹 변형(회전·스케일) — 2개 이상 선택 시 공통 bbox+핸들.
        self._group = _GroupTransform(self)
        self._group_dragging = False
        # [편의기능] 다중선택 바운딩박스 안쪽 빈틈(실제 도형이 없는 자리) 드래그 — 전체 이동.
        self._group_body_drag = False
        self._group_body_anchor = None
        # [Stage2b] AutoCAD 정통 stretch — crossing 박스에 걸친 정점만 이동(명시적 S 모드).
        # crossing(또는 window) 러버밴드 선택 → S로 무장 → 기준점 클릭 → 도착 클릭. Esc=취소.
        self._last_sel_rect = None    # 마지막 러버밴드 씬 사각(crossing 박스 '기억')
        self._stretch_arm = False     # S로 무장 — 기준점 클릭 대기
        self._stretch_active = False  # 기준점 클릭 후 — 도착점 대기(실시간 프리뷰)
        self._stretch_box = None      # 걸친 정점 판정 박스(씬, 원본 위치 기준)
        self._stretch_base = None     # 기준점(씬)
        self._stretch_cursor = None   # 현재 커서(씬) — 프리뷰 선
        self._stretch_items = None    # 변형 대상 선택 아이템
        self._stretch_binds = None    # _collect_bound_arrows 결과(부착점 추종)
        self._stretch_snap = None     # 기하 스냅샷([(item, capture_geom), ...]) — 원복·undo
        self._stretch_grip_pts = []   # 걸친 grip 하이라이트 점(씬)
        # [2026-08-01 되돌림] 2026-07-30에 qc-dot을 변 리사이즈 핸들과 통합했으나, 점이 테두리에서
        # 이미 리사이즈 축 방향으로 offset돼 있어 "바깥으로 쭉 당기는" 가장 자연스러운 동작이 항상
        # 리사이즈로 판정되는 문제가 실사용에서 드러나(화살표가 안 나오고 도형만 늘어남) 화살표
        # 전용으로 되돌림(사용자 확인 2026-08-01). 단일축 리사이즈는 이 점에서 더 이상 지원 안 함
        # (모서리 대각 핸들은 그대로 유지).
        # [하나의 시스템으로 통합 2026-08-01, Lucid 대조] qc-dot(선택된 도형)·hover-port(미선택
        # 도형) 드래그 상태 필드를 이 하나로 합쳤다 — 둘 다 이제 같은 점(_shape_ports, 항상 테두리
        # 위)·같은 클릭/드래그 생성 로직을 쓰므로 "선택된 도형이냐 아니냐"는 **어느 도구에서
        # 잡히느냐**(qc-dot 쪽은 어느 도구에서든, hover-port 쪽은 select 도구에서만 — 그리기 도구
        # 사용 중 다른 도형 테두리 근처를 클릭했을 때 그리기를 방해하지 않기 위한 기존의 의도적
        # 구분)만 남기고 상태·생성 경로는 하나로 합친다(_connect_port_at이 그 진입점).
        self._hp_hover = None       # (item, port_pt, normal) — 유휴 hover(스냅 마커용) or None
        self._port_dot_shape = None  # [2026-08-03 잔상/불규칙 표시 수정] _draw_port_dots가 그릴
        # 대상(미선택 도형 하나) — mouseMoveEvent가 이 값이 바뀔 때만 update()를 부르던 게 아니라
        # _hp_hover(포트 정밀 스냅, 훨씬 좁은 반경) 변화에만 반응해 왔다. 두 판정 반경이 달라
        # "포트 예고점이 뜨는 넓은 영역"에 들어가도 정밀 스냅 반경에 닿기 전엔 다시 그려지지
        # 않았고(뜸이 늦음), 반대로 넓은 영역을 벗어나도 정밀 반경 상태가 그대로면 다시 그려지지
        # 않아(잔상) 이전 프레임 점이 남았다 — 실사용 보고(불규칙·잔상)의 원인.
        self._hp_dragging = False
        self._hp_src = None         # 원본 도형(미선택)
        self._hp_port = None        # 시작 포트(씬)
        self._hp_normal = None      # 시작 포트 바깥 법선(씬)
        self._hp_cursor = None      # 드래그 중 커서(씬). None=드래그 임계 미달(release 시 평소 선택으로 폴백)
        self._hp_press_scene = None # press 지점(씬) — 형태 판정 기준
        # [실사용 버그 수정 2026-08-04] press 시점의 이산(discrete=4점)/연속(Pass2) 구분을 release
        # 까지 들고 간다 — 드래그(커넥터 생성)는 둘 다 동일해야 하지만(테두리 어디서든 끌면
        # 커넥터), 드래그 안 한 클릭의 결과는 갈린다: 이산=즉시 도형복제+화살표, 연속=그냥 선택.
        self._hp_is_discrete = True
        # [호버 강조 2026-07-30] 선택된 도형의 핸들(모서리·회전·qc-dot·끝점) 위 hover — (item, key)
        # or None. 크기를 고정으로 통일하며 "이 점이 잡힌다"를 색 반전으로 대신 알려준다.
        self._handle_hover = None
        # 선택이 바뀌면 그룹 오버레이(bbox·핸들)를 다시 그린다(개별 아이템 repaint와 별개).
        scene.selectionChanged.connect(self.viewport().update)

    def _is_empty_area(self, view_pos) -> bool:
        """클릭 위치에 선택 가능한 주석 아이템이 없으면(배경뿐) True."""
        for it in self.items(view_pos):
            if it is getattr(self._owner, "_bg_item", None):
                continue
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return False
        return True

    def _group_body_area_at(self, view_pos) -> bool:
        """[편의기능] 다중선택(그룹) 바운딩박스 안쪽 — 실제 도형이 없는 빈틈도 이동 영역으로
        취급한다(Lucid/FigJam — 선택 박스 안 아무 데나 끌면 전체가 움직인다). 개별 도형의
        속 빈 내부는 이미 _interior_hit_active가 채워 주지만, 서로 떨어진 도형들 '사이' 빈
        공간은 어느 도형의 shape()에도 안 걸려 여전히 빈 영역으로 판정되던 것을 보완한다."""
        if not self._group.available():
            return False
        b = self._group.bbox()
        return b is not None and b.contains(self.mapToScene(view_pos))

    def _bend_handle_at(self, view_pos):
        """커서(view 좌표) 아래에 활성 bend 핸들이 있으면 그 화살표, 없으면 None.
        호버 커서를 몸통(이동)과 구분하는 데 쓴다. 선택된 아이템을 직접 순회하므로
        넉넉한 잡기 영역이 shape 컬링에 걸리지 않는다(끝점 판정과 동일 방식)."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if isinstance(it, _ArrowItem) and it._bend_active() \
                    and it._bend_handle_index_at(it.mapFromScene(scene_pt)):
                return it
        return None

    def _box_handle_at(self, view_pos):
        """[2c] 커서가 선택된 네모·원의 박스 핸들 위면 커서('rotate' or Qt.CursorShape), 없으면 None."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            f = getattr(it, "_box_handle_cursor", None)
            if f is None:
                continue
            c = f(it.mapFromScene(scene_pt))
            if c is not None:
                return c
        return None

    def _handle_hover_at(self, view_pos):
        """[호버 강조] 커서가 선택된 아이템의 핸들 위면 (item, key), 없으면 None. 실제 하이라이트
        적용은 mouseMoveEvent가 이 결과를 item._hover_handle에 반영 + update()한다."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            f = getattr(it, "_hover_handle_at", None)
            if f is None:
                continue
            key = f(it.mapFromScene(scene_pt))
            if key is not None:
                return (it, key)
        return None

    # ---- [2d] 빠른 생성(quick-create) ---------------------------------------
    def _qc_dot_at(self, view_pos):
        """커서가 선택된 네모·원의 외부 도트 위면 (item, side), 아니면 None.
        [2d] 핸들과 동일하게 '어느 도구에서든' 작동 — 그린 직후 도구 전환 없이 빠른 생성."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if getattr(it, "_box_handles", None) is None or not it._box_handles():
                continue
            if not it._handle_active():
                continue
            lp = it.mapFromScene(scene_pt)
            for side, dr in it._qc_dot_rects():
                if dr.contains(lp):
                    return (it, side)
        return None

    def _qc_src_scene_rect(self, src) -> QRectF:
        """원본 도형의 씬 사각(회전 무시한 축정렬 bbox — 배치·고스트 기준)."""
        return src.mapToScene(src.rect()).boundingRect()

    def _qc_target_center(self, src, side, cursor_scene):
        """복제 도형 중심(씬) — 드래그 중이면 커서, 아니면 기본 배치 델타."""
        sr = self._qc_src_scene_rect(src)
        if cursor_scene is not None:
            return QPointF(cursor_scene)
        return sr.center() + _qc_default_delta(sr, side)

    def _qc_create(self, src, side, cursor_scene):
        """[2d] 네방향점 클릭=도형 복제+연결 화살표 / [M4-2] 드래그=화살표만.
        cursor_scene가 있으면(드래그) 화살표만, None이면(클릭) 복제 도형+화살표.
        [2026-08-04, 4차 — 포트도 예외 없이 동일] 포트(호스트에 부착된 작은 도형)도 다른
        도형과 똑같이 클릭=복제. 포트별 특례 대신 "드래그는 항상 화살표만"이라는 규칙을
        전 도형 공통으로 두어(`_hp_create_arrow` 참조) 포트가 원하는 동작을 특례 없이 얻는다."""
        if cursor_scene is not None:
            return self._qc_create_arrow_only(src, side, cursor_scene)
        sr = self._qc_src_scene_rect(src)
        center = self._qc_target_center(src, side, cursor_scene)
        dup = src.clone()
        self.scene().addItem(dup)
        dup.setPos(src.pos() + (center - sr.center()))   # 복제 중심 = 목표 중심
        # 연결 화살표 — 원본 side 변 중점 → 복제 반대 변 중점(양끝 도형 바인딩).
        opp = _QC_OPP[side]
        p_src = _edge_mid(self._qc_src_scene_rect(src), side)
        p_dup = _edge_mid(self._qc_src_scene_rect(dup), opp)
        owner = self._owner
        arrow = _PolyArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
        arrow._style = getattr(owner, "current_style", arrow._style)   # [M2 #3] sticky 선스타일
        arrow.set_points(p_src, p_dup)
        arrow.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                       | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        arrow.set_bound(0, src, src.mapFromScene(p_src))
        arrow.set_bound(1, dup, dup.mapFromScene(p_dup))
        self.scene().addItem(arrow)
        self._owner.push_undo_add_many([dup, arrow])
        self.scene().clearSelection()
        dup.setSelected(True)
        return dup, arrow

    def _qc_create_arrow_only(self, src, side, cursor_scene):
        """[M4-2 → 2026-08-04 4차 갱신] 네방향점 드래그 = 화살표만 생성(도형 복제 없이). 시작은
        src의 side 포트에 바인딩, 끝은 커서 위치 — 그 자리에 다른 도형이 있으면 그 테두리에
        스냅+바인딩. 스냅 대상이 없으면(빈 캔버스) 끝이 비어있는(미결) 화살표로 남는다 —
        도형 복제는 클릭 경로(`_qc_create`)만의 몫이다(실사용 결정: 드래그=항상 화살표만).
        [편의기능] 시작이 항상 바인딩되므로(has_binding) 자유 끝이어도 _apply_routing이 회피
        경로 포함 직각 엘보를 만든다 — 종전엔 스냅 안 됐을 때만 직선으로 남았다(2026-07-27 피드백)."""
        owner = self._owner
        p_src = _edge_mid(self._qc_src_scene_rect(src), side)
        arrow = _PolyArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
        arrow._style = getattr(owner, "current_style", arrow._style)   # sticky 선스타일
        arrow._curve_r = float(getattr(owner, "current_curve_r", arrow._curve_r))  # sticky 모서리 반경
        arrow.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                       | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        arrow.set_bound(0, src, src.mapFromScene(p_src))
        snap = self._qc_snap_target(cursor_scene, src)
        end = snap[0] if snap is not None else cursor_scene
        arrow.set_points(p_src, end)
        if snap is not None and snap[2] is not None and (
                snap[2] is not src or _far_enough_for_self_loop(p_src, end)):
            arrow.set_bound(1, snap[2], snap[2].mapFromScene(end))
        arrow._auto_route = True   # 도형 이동 시에도 계속 엘보로 재계산(reroute가 이 값을 봄)
        self.scene().addItem(arrow)
        arrow._apply_routing()
        self._owner.push_undo_add(arrow)
        self.scene().clearSelection()
        arrow.setSelected(True)
        return arrow

    def _qc_snap_target(self, cursor_scene, src):
        """[M4-2] QC 드래그 끝점 스냅 → (scene_pt, exit_unit, shape) 또는 None.
        테두리·포트 스냅(_border_snap_at) 우선, 없으면 커서가 다른 도형 '내부'면 그 도형 최근접
        포트로 흡수 — 테두리 정밀 조준 없이 도형 위에 놓기만 하면 붙게 한다."""
        snap = self._border_snap_at(self.mapFromScene(cursor_scene))
        if snap is not None:
            return snap
        for sh in self._conn_shapes():   # 위(나중 그린 것)부터
            if sh is src:
                continue
            # rect()로 판정 — 채움 없는 도형은 shape()가 외곽선만이라 contains가 내부를 못 잡는다.
            if sh.rect().contains(sh.mapFromScene(cursor_scene)):
                best, bestd = None, None
                for sp, n in _shape_ports(sh):
                    d = QLineF(sp, cursor_scene).length()
                    if bestd is None or d < bestd:
                        bestd, best = d, (sp, n, sh)
                return best
        return None

    def _qc_route_context(self, src, target):
        """[미리보기≠확정 버그 수정 2026-07-27] _hp_paint_ghost가 쓸 obstacles/conn_rects —
        _PolyArrowItem._obstacle_rects·_connected_rects와 같은 판정을 화살표 없이 계산(고스트는
        아직 실제 아이템이 아니므로). src·target 자신은 회피 대상에서 제외해야 릴리스 때
        _hp_create_arrow가 만드는 실제 화살표와 같은 입력이 된다."""
        sc = self.scene()
        obstacles = []
        if sc is not None:
            for it in sc.items():
                if it is src or it is target:
                    continue
                if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem)):
                    obstacles.append(it.mapRectToScene(it.rect()))

        def _rect_of(sh):
            return (sh.mapRectToScene(sh.rect())
                    if isinstance(sh, (_RectItem, _EllipseItem, _SymbolItem)) else None)
        return obstacles, (_rect_of(src), _rect_of(target))

    def _rot_handle_at(self, view_pos) -> bool:
        """커서가 '선택된' 도형의 회전 점 안이면 True — hover 회전 커서 판정용."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if getattr(it, "_box_handles", None) is not None and it._box_handles():
                continue   # [2c] 네모·원은 _box_handle_at이 담당
            rr = getattr(it, "_rot_handle_rect", None)
            active = getattr(it, "_handle_active", None)
            if rr is None or active is None or not active():
                continue
            if it._uses_endpoints():   # 선·화살표는 회전 핸들 없음(끝점 핸들 사용)
                continue
            if rr().contains(it.mapFromScene(scene_pt)):
                return True
        return False

    def _scale_handle_at(self, view_pos) -> bool:
        """커서가 '선택된' 도형의 크기조절(우하단 파란 사각) 핸들 안이면 True — hover 리사이즈
        커서 판정용. press 처리는 리사이즈로 받는데 커서만 이동으로 뜨던 불일치를 없앤다."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if getattr(it, "_box_handles", None) is not None and it._box_handles():
                continue   # [2c] 네모·원은 _box_handle_at이 담당
            hr = getattr(it, "_handle_local_rect", None)
            active = getattr(it, "_handle_active", None)
            if hr is None or active is None or not active():
                continue
            if it._uses_endpoints():   # 선·화살표는 크기조절 사각 없음(끝점 핸들 사용)
                continue
            if hr().contains(it.mapFromScene(scene_pt)):
                return True
        return False

    def _selected_endpoint_item(self, view_pos):
        """커서가 '선택된' 선·화살표의 끝점 핸들 안이면 그 아이템, 아니면 None."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            uses = getattr(it, "_uses_endpoints", None)
            if uses and it._uses_endpoints() and it._endpoint_active():
                local = it.mapFromScene(scene_pt)
                for i in it._handle_indices():
                    if it._inflate_to_hit(it._endpoint_rect(i)).contains(local):
                        return it
        return None

    def _over_selected_endpoint(self, view_pos) -> bool:
        """커서가 '선택된' 선·화살표의 끝점 핸들 안이면 True(hover 커서 판정용)."""
        return self._selected_endpoint_item(view_pos) is not None

    def _segment_add_at(self, view_pos):
        """[M4-4 → 2026-08-03 Lucid 대조] 선택된 직선화살표(ortho 라우팅)의 '세그먼트 위'(정점
        핸들 아님)에 커서가 있으면 (item, seg_idx, 씬 최근접점, on_pill), 아니면 None. 정점 위는
        이동(끝점 드래그)이 우선한다. `on_pill`=True면 그 변의 고정 알약(_segment_handles) 위 —
        press 시 변 전체를 수직 이동(`_begin_segment_drag`, 기존 동작). False면 알약이 아닌
        나머지 구간 — press 시 알약 자리에 새 정점을 끼워 나눈 뒤 가까운 쪽 절반만 이동
        (`_begin_subdivide_drag`, Lucid 실측: 알약 없는 위치를 끌면 그 자리에 새 알약이 생기고
        중심 알약~가까운 끝점 사이만 꺾인다 — 사용자 rf 계정 Lucid 문서에서 직접 재현·확인)."""
        if self._selected_endpoint_item(view_pos) is not None:
            return None   # 정점 핸들 위 = 이동 우선
        top = self.items(view_pos)
        if top and isinstance(top[0], _ConnectorLabel):
            return None   # 라벨 위 press = 라벨 드래그 우선
        scene_pt = self.mapToScene(view_pos)
        total = self._view_scale()
        best = None
        for it in self.scene().selectedItems():
            if not isinstance(it, _PolyArrowItem) or not it._is_ortho():
                continue
            local = it.mapFromScene(scene_pt)
            seg = it._nearest_segment(local)
            if seg is None:
                continue
            px = seg[2] * total * it._scale_or_1()   # 화면 px 거리
            if px <= 10.0 and (best is None or px < best[0]):
                best = (px, it, seg[0], seg[1])
        if best is None:
            return None
        _px, it, seg_idx, proj_local = best
        on_pill = it._point_on_segment_pill(seg_idx, proj_local)
        return (it, seg_idx, it.mapToScene(proj_local), on_pill)

    def _table_col_boundary_at(self, view_pos):
        """[열폭 드래그 2026-07-31] 커서가 선택된 표의 내부 열 경계선 근처면
        (item, boundary_idx), 아니면 None. 박스 핸들과 동일하게 선택된 아이템만 순회."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if not isinstance(it, _TableItem):
                continue
            idx = it._col_boundary_at(it.mapFromScene(scene_pt))
            if idx is not None:
                return (it, idx)
        return None

    # ---- [우리 확장] 방향 감지 러버밴드 (AutoCAD window/crossing) -----------
    def _rb_is_window(self) -> bool:
        """왼→오 드래그(현재 x ≥ 시작 x) = window(완전포함). 오→왼 = crossing(걸침)."""
        return self._rb_current.x() >= self._rb_origin.x()

    def _rb_scene_rect(self) -> QRectF:
        return QRectF(self.mapToScene(self._rb_origin),
                      self.mapToScene(self._rb_current)).normalized()

    # [선택 표시 통일 2026-08-01] 옛 `_rb_highlight_outline` 메서드는 모듈 레벨 `_item_center_path`
    # 로 승격됐다 — 개별 선택 강조(paint())와 완전히 같은 계산을 공유하기 위함. 아래 두 호출부
    # (`_rb_preview_hits`·`drawForeground`)는 `_item_center_path(it)`를 직접 쓴다.

    def _rb_preview_hits(self):
        """[성능 조사 2026-07-30] 러버밴드 드래그 '중'에 쓰는 저비용 미리보기 후보 집합 —
        실제 Qt 선택(setSelected)은 걸지 않는다(Lucid 대조 사용자 피드백: "드래그 중엔 각
        객체 색만 바꾸고, 놓는 순간에만 정확한 상자를 잡는다"). _apply_rubber_selection이
        매 마우스무브마다 씬 전체를 수동 순회 + clearSelection()+setSelected() 캐스케이드를
        걸던 것 — 특히 setSelected()는 [수정 3] boundingRect() 선택조건부화 이후 선택될 때마다
        prepareGeometryChange 유발까지 겹쳐 부하가 컸다. 여기선 Qt의 BSP 트리 공간 인덱스
        (scene.items(rect, mode))로 근사(boundingRect 기준, _content_rect/_base_shape 정밀
        판정은 생략 — 미리보기라 완전 정밀할 필요 없음)만 빠르게 구해 하이라이트 표시에 쓰고,
        정확한 최종 선택은 release 시점 _apply_rubber_selection() 단 1회로 확정한다."""
        if self._rb_origin is None or self._rb_current is None:
            return set()
        rect = self._rb_scene_rect()
        window = self._rb_is_window()
        mode = (Qt.ItemSelectionMode.ContainsItemBoundingRect if window
                else Qt.ItemSelectionMode.IntersectsItemBoundingRect)
        bg = getattr(self._owner, "_bg_item", None)
        hits = {it for it in self.scene().items(rect, mode)
                if it is not bg and (it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)}
        if not window:
            # [실외곽선 정밀화 2026-08-01] boundingRect는 축정렬 사각형이라, 대각/꺾인 화살표는
            # 빈 모서리 공간까지 포함한다 — 그 빈 공간만 스쳐도 broad-phase가 후보로 잡아,
            # 사용자 눈엔 "화살표를 안 건드렸는데 걸린다"로 보였다(실제로는 눈에 안 보이는
            # bbox와 걸친 것). broad-phase가 이미 후보를 크게 추려놨으므로, 여기서
            # _item_center_path()(스트로커 없는 가벼운 실기하)으로 한 번 더 정밀 교차
            # 검사해 진짜 걸친 것만 남긴다 — 후보 수가 적어 narrow-phase 비용은 작다.
            sel_path = QPainterPath(); sel_path.addRect(rect)
            hits = {it for it in hits
                    if it.mapToScene(_item_center_path(it)).intersects(sel_path)}
        return hits | set(self._rb_base)

    def _apply_rubber_selection(self):
        """드래그 방향으로 window/crossing을 정해 선택을 실시간 재계산.
        window: 아이템이 상자에 '완전 포함'되어야 선택(sceneBoundingRect 포함).
        crossing: 아이템 외형(shape)이 상자와 '겹치기만' 하면 선택(AutoCAD와 동일)."""
        if self._rb_origin is None or self._rb_current is None:
            return
        rect = self._rb_scene_rect()
        window = self._rb_is_window()
        sel_path = QPainterPath()
        sel_path.addRect(rect)
        bg = getattr(self._owner, "_bg_item", None)
        self.scene().clearSelection()
        to_select = [it for it in self._rb_base if it.scene() is not None]   # Shift 추가선택: 기존 선택 유지
        for it in self.scene().items():
            if it is bg:
                continue
            if not (it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            if window:
                # 완전 포함 판정은 '보이는 외형'(_content_rect) 기준 — 선택·회전 핸들 여유가
                # 들어간 sceneBoundingRect로 하면 보이는 것보다 박스를 더 넓게 그려야 잡혔다.
                cr = it._content_rect() if hasattr(it, "_content_rect") \
                    else it.boundingRect()
                hit = rect.contains(it.mapToScene(cr).boundingRect())
            else:
                # 걸침 판정도 '보이는 외형'(_base_shape) 기준 — shape()는 선택 시 핸들 잡기
                # 영역이 붙어 보이지 않는 곳에서 잡히므로 base 외형만 쓴다.
                outline = it._base_shape() if hasattr(it, "_base_shape") else it.shape()
                hit = it.mapToScene(outline).intersects(sel_path)
            if hit:
                to_select.append(it)
        # [성능 조사 2026-08-01] 개별 setSelected() 루프는 매 호출마다 selectionChanged를 쏴
        # _refresh_properties가 그 시점까지 선택된 전체를 다시 읽어 O(n²)가 된다(paste와 동일
        # 근본원인, cProfile로 확인). owner의 공용 배치 선택 헬퍼로 한 번에 커밋.
        self._owner._bulk_select(to_select)

    def _snapshot_movable(self):
        """드래그 이동 전 이동 가능 아이템들의 위치를 기록(release에서 변경분만 undo에 커밋)."""
        self._move_active = True   # [2e] 도형 드래그 시작(이동/핸들) — 스마트 정렬 스냅 판정 활성
        self._axis_lock = None     # [편의기능] Shift+드래그 축 고정 — 새 드래그마다 재판정
        self._move_snap = [
            (it, QPointF(it.pos())) for it in self.scene().items()
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            and not isinstance(it, _ConnectorLabel)   # 라벨 드래그는 t·off 소유라 위치-undo 스코프 밖
        ]

    def _maybe_alt_drag_copy(self, event):
        """[편의기능] Alt+드래그 시작 — 선택 항목을 제자리 복제하고 복제본을 선택한다.
        복제본이 원본과 같은 자리·zValue에 놓여 Qt의 기본 히트테스트가 복제본을 잡으므로,
        곧바로 이어지는 super().mousePressEvent()가 복제본을 자연스럽게 드래그한다
        (Qt 내부 grabber를 직접 다루는 대신 '위에 새로 얹기'로 우회 — 더 견고함)."""
        if not (event.modifiers() & Qt.KeyboardModifier.AltModifier):
            return
        vpos = event.position().toPoint()
        top = self.items(vpos)
        if not top:
            return
        sel = self.scene().selectedItems()
        src = sel if top[0] in sel else [top[0]]
        src = [it for it in src if hasattr(it, "clone") and it.parentItem() is None]
        if not src:
            return
        clones = []
        for it in src:
            c = it.clone()
            c.setPos(it.pos())
            c.setZValue(it.zValue())
            self.scene().addItem(c)
            clones.append(c)
        remap_grouped_bindings(zip(src, clones))   # 배치 안에서 함께 복제된 도형끼리 재연결
        regroup_duplicated_items(zip(src, clones)) # 그룹째 복제 시 사본도 새 그룹으로
        self.scene().clearSelection()
        # [성능조사 2026-08-01] paste/duplicate/rubber-band와 동일한 O(n²) 함정 — 다중선택
        # Alt+드래그 복제 시 개별 setSelected 대신 owner의 배치 선택 헬퍼로 한 번에.
        self._owner._bulk_select(clones)
        if hasattr(self._owner, "push_undo_add_many"):
            self._owner.push_undo_add_many(clones)

    def _apply_axis_lock(self, event):
        """[편의기능] Shift+드래그 — 첫 유의미한 편차 방향(수평/수직)으로 축을 고정해 그 축으로만
        움직이게 한다(일러스트레이터·Figma 관행). 스마트 정렬 스냅보다 사용자 의도가 강하므로,
        축이 고정된 동안은 mouseMoveEvent에서 스마트 스냅을 건너뛴다."""
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._axis_lock = None
            return
        snap = self._move_snap
        if not snap:
            return
        # ⚠ _move_snap은 씬의 '이동 가능한 모든' 아이템을 담는다(선택 여부 무관) — snap[0]이
        # 실제로 드래그 중인 아이템이라는 보장이 없다(도형이 2개 이상이면 대개 아니다).
        # Qt 기본 드래그는 '선택된' movable 아이템들만 함께 옮기므로, 델타는 그중에서 재야 한다.
        moving = [(it, old) for it, old in snap if it.scene() is not None and it.isSelected()]
        if not moving:
            return
        it0, old0 = moving[0]
        delta = it0.pos() - old0
        if self._axis_lock is None:
            thr = 3.0 / self._view_scale()
            if abs(delta.x()) < thr and abs(delta.y()) < thr:
                return   # 방향이 아직 불명확 — 다음 move에서 재판정
            self._axis_lock = "h" if abs(delta.x()) >= abs(delta.y()) else "v"
        if self._axis_lock == "h" and delta.y() != 0:
            for it, old in moving:
                it.setPos(QPointF(it.pos().x(), old.y()))
        elif self._axis_lock == "v" and delta.x() != 0:
            for it, old in moving:
                it.setPos(QPointF(old.x(), it.pos().y()))

    def _apply_smart_snap(self):
        """[2e] 단일 도형 이동 중 — 근처 도형과 모서리(좌/우/상/하)·중심 정렬 시 스냅 + 가상선.
        Qt가 커서로 옮긴 뒤 호출돼, 임계 내면 정렬 좌표로 살짝 당기고 가이드선을 기록한다.
        핸들 조작(리사이즈·회전·끝점) 중이거나 단일 선택이 아니면 건드리지 않는다."""
        self._align_guides = []
        if not getattr(self._owner, "align_guides_enabled", True):
            return   # [토글] 꺼져 있으면 스냅도 가이드선도 전부 스킵
        sel = [it for it in self.scene().selectedItems() if it.parentItem() is None]
        if len(sel) != 1:
            return
        it = sel[0]
        if (getattr(it, "_resizing", False) or getattr(it, "_rotating", False)
                or getattr(it, "_box_resize", None) is not None
                or getattr(it, "_drag_endpoint", None) is not None):
            return
        bg = getattr(self._owner, "_bg_item", None)

        def srect(o):   # 보이는 외형(_content_rect) 기준 씬 사각 — 핸들·도트 여유 제외.
            cr = o._content_rect() if hasattr(o, "_content_rect") else o.boundingRect()
            return o.mapToScene(cr).boundingRect()

        others = [srect(o) for o in self.scene().items()
                  if o is not it and o is not bg and o.parentItem() is None
                  and (o.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)]
        if not others:
            return
        nr = srect(it)
        # 실사용 재현(2026-08-01, 로그 확인) — 6화면px는 게이트·로직 자체는 정상 작동했지만
        # (로그상 인접 스냅이 수십 프레임·수십 유닛 구간에서 계속 유지됨을 확인) 실제 손 드래그
        # 속도로는 그 폭(화면에서 2mm 미만)을 그냥 지나쳐 버려 "닿기 직전까진 전혀 반응 없다가
        # 닿는 순간 나타난다"는 체감으로 이어졌다. 로직이 아니라 문턱 자체가 좁았던 것 — 10px로
        # 넉넉히 늘린다(과발화 원인이었던 교차조합·전역 tie 도용은 이미 별도로 막아 뒀으므로,
        # 문턱만 넓혀도 그 문제들이 재발하진 않는다).
        thr = 10.0 / self._view_scale()
        # 동률(같은 크기 도형끼리는 좌/중심/우 또는 상/중심/하의 "얼마나 가까운가"가 수학적으로
        # 완전히 같아짐) 시 승자를 하나만 골라 보여주면, 같은 크기 도형끼리는 그 하나(예: 중심)만
        # 영원히 뜨고 나머지 역할은 절대 못 본다 — 실사용 로그로 확인(2026-08-01): 같은 크기
        # 도형끼리는 항상 좌/중심/우 거리가 소수점까지 정확히 일치했다. 그래서 "승자 하나"가 아니라
        # **동률인 역할을 전부** 가이드선으로 보여준다(Figma·Lucid도 여러 정렬이 동시에 맞으면
        # 선을 여러 개 함께 보여준다). 이동량(dx/dy)은 동률 후보끼리 델타가 같아 아무거나 써도
        # 결과가 같지만, 가이드선은 역할마다 그리는 좌표(그 변·중심의 실제 위치)가 달라 하나만
        # 고르면 정보가 사라진다.
        tie_eps = 1.5 / self._view_scale()

        def pick_local(cands):
            """임계 내 후보 중 최솟값과, 그와 근접 동률인 역할 전부를 (ad,d,coord,role) 리스트로
            반환(표시용). 리스트[0]이 가장 가까운 진짜 승자 — 스냅 이동량은 이것만 쓴다."""
            scored = [(abs(other_val - my_val), other_val - my_val, other_val, role)
                      for my_val, other_val, role in cands]
            scored = [c for c in scored if c[0] <= thr]
            if not scored:
                return None
            scored.sort(key=lambda c: c[0])
            best_ad = scored[0][0]
            return [c for c in scored if c[0] <= best_ad + tie_eps]

        bx_winners = by_winners = None   # [(ad,d,coord,role), ...] — 최적 상대 도형 기준 전체 동률
        bx_orr = by_orr = None

        for orr in others:
            # 후보는 축당 5개 — 같은 역할 3개(좌-좌/중심-중심/우-우, 상-상/중심-중심/하-하)와
            # **마주보는 변** 2개(내 우변=상대 좌변, 내 좌변=상대 우변 / 내 아랫변=상대 윗변,
            # 내 윗변=상대 아랫변). 배제하는 것은 「좌-중심」·「중심-우」처럼 기하적으로 의미
            # 없는 교차 조합뿐이다(원래 과발화의 원인은 그 4개였다).
            # ⚠ 마주보는 변에 "교차축이 겹칠 때만"이라는 게이트를 걸면 안 된다 — 실사용 로그로
            # 확정(2026-08-01): 두 도형이 가로로 134유닛 떨어져 나란히 있고 내 윗변이 상대
            # 아랫변과 4유닛(임계 6 이내)까지 맞았는데도, x범위가 안 겹친다는 이유로 후보에
            # 오르지도 못했다(로그 `x_gate=False ... adj_top_bottom=4.00 → by=None`). 심지어
            # 두 변이 정확히 0으로 일치한 프레임도 같은 이유로 무시됐다. "붙여야만 뜬다"는
            # 증상의 정체가 이 게이트였고(붙어야 교차축이 겹쳐 게이트가 열림), 게이트를 thr만큼
            # 넓히는 완화로는 수십~수백 유닛 떨어진 이 케이스를 못 살린다. 같은 역할 매칭에는
            # 애초에 이런 게이트가 없다는 점에서도 인접에만 거는 것은 비대칭이었다.
            x_cands = [(nr.left(), orr.left(), "left"),
                       (nr.center().x(), orr.center().x(), "center"),
                       (nr.right(), orr.right(), "right"),
                       (nr.right(), orr.left(), "adj"),
                       (nr.left(), orr.right(), "adj")]
            y_cands = [(nr.top(), orr.top(), "top"),
                       (nr.center().y(), orr.center().y(), "center"),
                       (nr.bottom(), orr.bottom(), "bottom"),
                       (nr.bottom(), orr.top(), "adj"),
                       (nr.top(), orr.bottom(), "adj")]
            local_x = pick_local(x_cands)
            if local_x is not None and (bx_winners is None or local_x[0][0] < bx_winners[0][0]):
                bx_winners, bx_orr = local_x, orr
            local_y = pick_local(y_cands)
            if local_y is not None and (by_winners is None or local_y[0][0] < by_winners[0][0]):
                by_winners, by_orr = local_y, orr
        dx = bx_winners[0][1] if bx_winners else 0.0
        dy = by_winners[0][1] if by_winners else 0.0
        if dx or dy:
            it.moveBy(dx, dy)
            nr = srect(it)
        if bx_winners:
            o = bx_orr
            y0, y1 = min(nr.top(), o.top()), max(nr.bottom(), o.bottom())
            seen = set()
            for _ad, _d, coord, _role in bx_winners:
                if coord not in seen:
                    seen.add(coord)
                    self._align_guides.append(("v", coord, y0, y1))
        if by_winners:
            o = by_orr
            x0, x1 = min(nr.left(), o.left()), max(nr.right(), o.right())
            seen = set()
            for _ad, _d, coord, _role in by_winners:
                if coord not in seen:
                    seen.add(coord)
                    self._align_guides.append(("h", coord, x0, x1))

    def _apply_grid_snap_move(self, skip_x: bool, skip_y: bool):
        """[그리드 스냅] 단일 도형 이동 중 — 스마트정렬·축고정이 이미 자리를 정한 축은 skip_*로
        건드리지 않고, 나머지 축만 격자 교차점으로 양자화한다. 우선순위는 축고정(Shift) >
        스마트정렬(2e) > 격자스냅 순 — 호출부(mouseMoveEvent)가 skip_*로 강제.
        ⚠ pos()를 직접 스냅하면 안 된다 — 마우스 드래그로 그린 도형은 로컬 도형이 클릭 시점의
        씬 좌표를 그대로 품고(`QRectF(sp, sp)`) pos()는 (0,0)에 남는 게 보통이라(실측: rect(300,
        50,100,60), pos=(0,0)), pos()만 격자에 맞춰도 실제 화면 위치는 격자 밖일 수 있다.
        ⚠ 아이템 좌표계 원점(로컬 (0,0))을 mapToScene해도 안 된다 — (0,0)은 pos()와 같아질 뿐
        실제로 그려진 도형(로컬 rect)과 무관한 점이라 같은 함정을 이름만 바꿔 반복한다(1차 시도의
        회귀 — 실측: rect(307,53,100,60)에서 mapToScene(0,0)이 그대로 (0,0)이라 스냅이 무효화됨).
        `_apply_smart_snap`의 `srect()`와 동일하게 **콘텐츠 rect**(`_content_rect()`, 없으면
        boundingRect)의 좌상단을 mapToScene한 실제 화면 기준점을 격자로 당기고 moveBy로 적용한다."""
        if not getattr(self._owner, "grid_enabled", True):
            return
        sel = [it for it in self.scene().selectedItems() if it.parentItem() is None]
        if len(sel) != 1:
            return
        it = sel[0]
        if (getattr(it, "_resizing", False) or getattr(it, "_rotating", False)
                or getattr(it, "_box_resize", None) is not None
                or getattr(it, "_drag_endpoint", None) is not None):
            return
        cr = it._content_rect() if hasattr(it, "_content_rect") else it.boundingRect()
        anchor = it.mapToScene(cr.topLeft())
        sp = _GRID_SPACING
        tx = round(anchor.x() / sp) * sp if not skip_x else anchor.x()
        ty = round(anchor.y() / sp) * sp if not skip_y else anchor.y()
        dx, dy = tx - anchor.x(), ty - anchor.y()
        if dx or dy:
            it.moveBy(dx, dy)

    def _commit_move(self):
        """release 시 실제로 위치가 바뀐 아이템만 이동 undo로 기록."""
        snap = self._move_snap
        self._move_snap = None
        if not snap:
            return
        moved = [(it, old) for it, old in snap
                 if it.scene() is not None and it.pos() != old]
        if moved:
            self._owner.push_undo_move(moved)

    # ---- 테두리 스냅 (화살표 도구가 네모/원 테두리에서 시작·도착하면 붙음) ----
    _BORDER_SNAP_PX = 14.0  # 커서~테두리 최근접점이 이 픽셀 이내면 스냅(시작·tip 공통, 뷰 픽셀)
    _PORT_SNAP_PX = 18.0    # 포트(변 중점 접속점) 우선 스냅 반경 — 연속보다 넓어 먼저 끌린다(뷰 픽셀)
    # [2026-08-09] 위 스냅 반경(잡히는 범위)과 별개로, 커서 모양을 가르는 "체감" 반경 — 이걸 더
    # 좁게 둬야 포트처럼 몸통 자체가 스냅 반경보다 작은 도형에서 몸통 전체가 CrossCursor로
    # 뒤덮이지 않는다(`_update_hover_cursor` 참조). 실제 포트 기본 크기가 18×18(scene 단위,
    # `_PALETTE_DROP_WH`)이라 절반(9)보다 확실히 작아야 몸통 대부분이 이동 커서로 남는다 —
    # `_draw_port_dots`가 그리는 예고점 반지름(5.0)과 같은 값을 재사용(이미 "포트 점의 시각적
    # 크기"로 검증된 값이라 새 매직넘버를 만들지 않는다).
    _PORT_CURSOR_PX = 5.0

    def _view_scale(self) -> float:
        m = self.transform().m11()
        return m if m > 1e-6 else 1.0

    def _view_dist(self, scene_pt, view_pos) -> float:
        vp = self.mapFromScene(scene_pt)
        return math.hypot(vp.x() - view_pos.x(), vp.y() - view_pos.y())

    def _conn_shapes(self):
        """씬의 네모·원·심볼 아이템(위→아래 순) — 화살표 테두리 스냅·지속연결 대상."""
        return [it for it in self.scene().items()
                if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]

    def _conn_paths(self):
        """[외부 DXF 폴백/펜] _PathItem — 연속 폴백(Pass 2)만 지원, 이산 포트는 없음(임의
        외곽선이라 N/E/S/W 개념이 불분명 — 계획서 §8 항목 5 확정). 지속연결 바인딩은 지원."""
        return [it for it in self.scene().items() if isinstance(it, _PathItem)]

    def _conn_lines(self, exclude=None):
        """[M4-2b] 스냅 대상 선·화살표 — 그리기 중(_temp)·클릭배치 중(_place)·exclude는 제외해
        자기 자신에 스냅하지 않게 한다(자기 preview 정점에 붙어 조기 마무리되던 문제)."""
        skip = (self._temp, getattr(self, "_place", None), exclude)
        return [it for it in self.scene().items()
                if isinstance(it, (_LineItem, _ArrowItem, _PolyArrowItem)) and it not in skip]

    def _border_snap_at(self, view_pos, exclude=None):
        """커서 근처 도형/선/화살표에 스냅 → (snap_scene, exit_unit, shape) 또는 None.
        [우리 확장] 포트/끝점 우선(_PORT_SNAP_PX) + 연속 폴백(_BORDER_SNAP_PX). 도형은 shape로
        지속연결 바인딩, [M4-2b] 선·화살표(끝점·몸통)는 shape=None(기하 스냅만, 바인딩 없음).
        exclude=자기 자신(끝점 재스냅 시 self 제외). owner.snap_enabled가 False면 스냅 전체 off."""
        if not getattr(self._owner, "snap_enabled", True):
            return None
        scene_pt = self.mapToScene(view_pos)
        shapes = self._conn_shapes()
        lines = self._conn_lines(exclude)
        # Pass 1: 이산 우선 — 도형 포트 + 선/화살표 끝점(반경이 연속보다 넓어 먼저 끌린다).
        bestp = None
        bestpd = self._PORT_SNAP_PX
        pexit = None
        pshape = None
        for sh in shapes:
            for sp, n in _shape_ports(sh):
                d = self._view_dist(sp, view_pos)
                if d <= bestpd:
                    bestpd, bestp, pexit, pshape = d, sp, n, sh
        for cl in lines:
            for ep, ed in _conn_endpoint_dirs(cl):
                d = self._view_dist(ep, view_pos)
                # ⚠ 동점은 도형 포트가 이긴다(`<`, `<=` 아님) — 실조건 2026-07-26: 포트에 이미
                # 화살표가 붙어 있으면 그 끝점이 포트와 **거리 0으로 동일**해 나중에 오는 이 루프가
                # 항상 이겼다. 그 결과 ⓐ 바인딩이 None이 되어 지속 연결이 안 걸리고 ⓑ 이탈 법선이
                # 상대 화살표 방향(정반대)으로 잡혀 같은 포트인데 경로가 달라졌다. 바인딩은 기하
                # 스냅보다 정보량이 크므로 같은 거리면 도형을 택한다.
                if d < bestpd:
                    bestpd, bestp, pexit, pshape = d, ep, ed, None   # 선/화살표=바인딩 없음
        if bestp is not None:
            return bestp, pexit, pshape
        # Pass 2: 연속 폴백 — 도형 외곽선 + 선/화살표 몸통 최근접점.
        best = None
        bestd = self._BORDER_SNAP_PX
        bexit = None
        bshape = None
        for sh in shapes:
            sp, n = _nearest_border(sh, scene_pt)
            d = self._view_dist(sp, view_pos)
            if d <= bestd:
                bestd, best, bexit, bshape = d, sp, n, sh
        for pit in self._conn_paths():
            sp, n = _nearest_border(pit, scene_pt)
            d = self._view_dist(sp, view_pos)
            if d <= bestd:
                bestd, best, bexit, bshape = d, sp, n, pit
        for cl in lines:
            q, qn = _nearest_on_polyline(_conn_polyline_scene(cl), scene_pt)
            if q is None:
                continue
            d = self._view_dist(q, view_pos)
            if d <= bestd:
                bestd, best, bexit, bshape = d, q, qn, None
        if best is None:
            return None
        return best, bexit, bshape

    def _update_snap_preview(self, view_pos):
        """화살표 도구 유휴 시 커서 근처 테두리 최근접점을 마커로 예고(스냅 발동 가능 표시)."""
        prev = self._snap_preview
        new = None
        # 커서가 이미 선택된 화살표의 끝점/곡선 핸들 위면(= 이동·재스냅 모드, 손가락 커서)
        # '새 화살표 시작' 예고 마커를 띄우지 않는다 — 끝점이 도형 테두리에 붙어 있어
        # 생성-스냅점과 겹칠 때 큰 파란 점이 손가락 커서와 함께 남던 문제 방지.
        if (self._owner.is_edit_mode() and self._owner.current_tool in ("arrow", "sarrow")
                and not self._drawing
                and self._selected_endpoint_item(view_pos) is None
                and self._bend_handle_at(view_pos) is None):
            snap = self._border_snap_at(view_pos)
            if snap is not None:
                new = snap[0]
        self._snap_preview = new
        if new != prev:
            self.viewport().update()

    def _update_arrow_draw(self, event, it=None):
        """화살표 그리기 갱신 — tip=커서(테두리 근처면 스냅). 시작·tip 중 하나라도 테두리에
        스냅되면 그 바깥 법선을 이탈/도착 접선으로 쓴 3차 베지어(자동 S자), 둘 다 자유면 직선.
        it=None이면 드래그 중(self._temp), 아니면 클릭 배치 중 아이템."""
        if it is None:
            it = self._temp
        view_pos = event.position().toPoint()
        tip = self._cur_point(event)   # Shift 각도 제약 반영(스냅되면 아래에서 덮어씀)
        # tip 스냅 — 도형 테두리 최근접점
        snap = self._border_snap_at(view_pos)
        # [이슈2] 시작점 바로 근처의 tip 스냅은 무시 — 시작·끝이 같은 테두리에 겹쳐 보이지 않는
        # 극소 화살표가 만들어지는 것을 막는다(사용자: '가상점은 유지되는데 클릭하면 안 생김').
        if (snap is not None
                and self._view_dist(snap[0], self.mapFromScene(self._start)) < self._MIN_SNAP_SPAN_PX):
            snap = None
        back = None
        if snap is not None:
            tip, back = snap[0], snap[1]   # 타깃 바깥 법선 쪽에 ctrl2 → 수직 도착
        self._arrow_tip_snap = snap[0] if snap is not None else None
        if snap is not None and snap[2] is not None:  # 지속 연결: tip이 붙은 도형 + 그 지점 고정
            it.set_bound(1, snap[2], snap[2].mapFromScene(snap[0]))
        else:   # [M4-2b] 선·화살표(snap[2]=None)면 tip 기하 스냅만, 바인딩 없음
            it.set_bound(1, None)
        start = self._start
        exit_dir = self._arrow_snap_exit
        dist = math.hypot(tip.x() - start.x(), tip.y() - start.y())
        it.prepareGeometryChange()
        it._p2 = QPointF(tip)
        # [화살표 통합] sticky 종류가 '직선'이면 라이브 미리보기도 곧게 — 안 그러면 드래그 중엔
        # 자동 S자로 보이다가 릴리스(_apply_arrow_kind_on_create)에서만 펴져 미리보기와 결과가
        # 어긋난다(2026-07-27 사용자 GUI 보고).
        straight_kind = getattr(self._owner, "current_arrow_kind", "curved") == "straight"
        if straight_kind or (exit_dir is None and back is None) or dist < 8:
            it._ctrl1 = it._ctrl2 = None   # 양끝 자유거나 너무 짧으면 직선
        else:
            k = max(30.0, min(dist * 0.5, 200.0))
            if exit_dir is not None:
                ex, ey = exit_dir.x(), exit_dir.y()          # 시작 테두리 이탈 접선
            else:
                ex, ey = (tip.x() - start.x()) / dist, (tip.y() - start.y()) / dist  # tip 향해
            if back is not None:
                bx, by = back.x(), back.y()                  # tip 테두리 도착 접선(바깥 법선)
            else:
                bx, by = -ex, -ey                            # 시작과 평행하게 도착(부드러운 S)
            it._ctrl1 = QPointF(start.x() + ex * k, start.y() + ey * k)
            it._ctrl2 = QPointF(tip.x() + bx * k, tip.y() + by * k)
        it.update()
        self.viewport().update()   # tip 마커 갱신

    def _draw_snap_marker(self, painter, sp, s):
        base = 5.0 / s
        painter.setPen(QPen(QColor("white"), 1.5 / s))
        painter.setBrush(QBrush(QColor(_BLUE)))
        painter.drawEllipse(sp, base, base)

    def _conn_shapes_near(self, scene_pt: QPointF, margin: float):
        """[성능 조사 2026-07-30] scene.items(rect) 공간 인덱스(Qt BSP 트리)로 scene_pt 근방만
        질의 — _conn_shapes()의 전체 스캔 대체. _draw_port_dots·_hover_port_at가 매 페인트·매
        마우스무브마다 씬 전체를 수동 순회하던 게(cProfile 실측) 다중선택 드래그 버벅임과
        무거운 도면 호버 클러터의 원인이었다. 반환은 근사 후보 목록 — 정밀 판정(마진 사각형
        contains)은 호출부가 그대로 한다.
        [2026-08-04 연속 호버 §8 항목16] _PathItem(DXF 폴백 도형)도 후보에 포함 — 이산 포트가
        없어 Pass 1(discrete)에선 호출부가 스킵하지만, Pass 2(연속 폴백)는 _nearest_border가
        이미 _PathItem을 지원하므로 대상에 넣어 화살표-그리기 스냅과 동작을 통일한다.
        [2026-08-04, 3차 수정] 포트를 여기서 걸러내지 않는다 — 포트도 이 후보 목록을 타는
        `_hover_port_at`(미선택 4점)·`_qc_dot_at`을 통해 자신의 4변 접속점을 항상 제공해야
        하기 때문(실사용 요구: 선택 여부 무관하게 4변 중심점은 살아있어야 함). 포트를
        "장비 전체"처럼 취급해 중심을 눌러도 반응하는 문제는 이 함수가 아니라
        `_port_dot_target`(장비 하나를 통째로 미리보기하는 별도 시스템) 쪽에서만 걸러낸다."""
        rect = QRectF(scene_pt.x() - margin, scene_pt.y() - margin, margin * 2, margin * 2)
        return [it for it in self.scene().items(rect)
                if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem, _PathItem))]

    def _port_dot_target(self, scene_c):
        """[2026-08-03 분리 — _draw_port_dots·mouseMoveEvent 공용] 지금 예고점을 그릴 도형
        하나(가장 가까운 미선택 도형) or None. 페인트와 '다시 그려야 하는가' 판정이 서로 다른
        기준을 쓰면(과거 버그: 페인트는 이 넓은 margin, 갱신 트리거는 훨씬 좁은 _hp_hover 스냅
        반경) 판정 따로 반영 따로 놀아 예고점이 늦게 뜨거나(반경 진입해도 안 그려짐) 잔상으로
        남는다(반경 이탈해도 안 지워짐) — 실사용 보고. 하나의 함수로 통일해 이 어긋남을 없앤다."""
        tool = self._owner.current_tool
        if not self._owner.is_edit_mode() or tool not in ("arrow", "sarrow", "select"):
            return None
        if (self._move_active or self._group_dragging or self._group_body_drag
                or self._stretch_active or self._seg_drag is not None
                or self._table_col_drag is not None or self._rb_active):
            return None
        select_mode = tool == "select"
        margin = 30.0 / self._view_scale()
        near = self._conn_shapes_near(scene_c, margin)
        # [실사용 지적 2026-08-09, 2차] 자기 몸통 안(select_mode 기존 규칙)뿐 아니라, 겹쳐 있는
        # *다른* 도형의 몸통 안일 때도 예고점이 뜨면 안 된다 — 선택·미선택을 가리지 않는다
        # (겹치는 도형이 아직 선택 전인 포트여도 재현됨). 이 목록은 "차지된" 도형 전부이고,
        # 아래 루프의 자기-내부 skip과 합쳐 최종적으로 "살아남은 후보가 이 목록에 없으면
        # (=자기 몸통 밖의 남의 도형이 대신 뽑힌 것) 억제"로 판정한다 — 그래야 포트 정중앙처럼
        # 자기 자신이 죽은 지대가 되는 기존 동작(안 뜸)은 그대로 두고, 포트 몸통의 다른 지점에서
        # 뒤쪽 호스트가 엉뚱하게 뽑히는 새 버그만 골라 막는다.
        occluders = [sh for sh in near if _shape_interior_contains(sh, scene_c)] if select_mode else []
        best_sh, best_d = None, None
        for sh in near:
            if sh.isSelected():
                continue
            br = sh.sceneBoundingRect().adjusted(-margin, -margin, margin, margin)
            if not br.contains(scene_c):
                continue
            if select_mode and sh in occluders:
                continue
            d = QLineF(sh.sceneBoundingRect().center(), scene_c).length()
            if best_d is None or d < best_d:
                best_d, best_sh = d, sh
        if best_sh is not None and occluders:
            return None
        return best_sh

    def _draw_port_dots(self, painter, s):
        """[우리 확장] 화살표 도구로 도형 근처에 가면 그 도형의 포트(8점)를 속 빈 점으로 예고.
        [8포트 select-hover 2026-07-29] select 도구에서도 동일하게 예고하되, 선택된 도형은
        제외(리사이즈·회전 핸들과 자리가 겹침 — 그건 qc-dot(4방향점)이 담당).
        [성능 조사 2026-07-30] 가장 가까운 도형 '하나'만 그린다(이전엔 마진 안의 모든 도형을
        전부 그려, Ctrl+D로 겹쳐 복제한 도형들 위에서 호버하면 포트 점이 잔뜩 뒤덮이는 클러터가
        났다 — _hover_port_at은 원래도 최근접 하나만 골랐으니 미리보기 쪽을 그와 맞췄다).
        [드래그 중 억제 2026-08-01] 도형 이동/변형 드래그 중엔 커서가 자연히 다른 도형 위를
        지나가는데, 그때마다 그 도형에 예고점이 뜨는 게 방해된다는 사용자 피드백 — 커넥터를
        만들 의도가 없는 상태이므로 다른 드래그 계열 상태와 동일하게 억제한다.
        [2026-08-03 중복 제거] 예전엔 이 예고점과 별개로 drawForeground가 `_hp_hover` 위치에
        `_draw_snap_marker`(테두리 위 채운 점)를 하나 더 그렸다 — 예고점이 테두리 밖으로
        떨어져 뜨는 지금은 그 둘이 서로 다른 자리에 보여 "점이 중복으로 생긴다"는 실사용
        지적을 받았다. 그 별도 마커를 없애고, 대신 지금 targeted(= `_hp_hover`가 가리키는)
        점 자신을 반전 스타일로 강조한다 — 선택된 qc-dot이 `_hover_handle`로 자신을 강조하는
        것과 같은 패턴.
        [2026-08-04 연속 호버 §8 항목16, deep-interview] `_hp_hover`가 이제 이산 4점과 무관한
        테두리 임의 위치(Pass 2 연속 폴백, `_hover_port_at`)일 수 있다 — 그 경우 아래 고정 4점
        루프의 어느 것과도 안 맞아 강조점이 안 뜨므로, 루프 뒤에서 한 번 더 확인해 그 정확한
        위치에 별도 강조점을 그린다. `_PathItem`(DXF 폴백 도형)은 이산 포트 자체가 없으므로
        고정 4점 루프를 건너뛰고 이 연속 강조점만 그린다."""
        scene_c = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        best_sh = self._port_dot_target(scene_c)
        if best_sh is None:
            return
        r = 5.0 / s
        hp = self._hp_hover
        # [2026-08-03] 선택 시 qc-dot(_qc_dot_rects)과 같은 gap 규칙 — 선택 여부로 점 위치가
        # 바뀌는 비일관성을 만들지 않는다(둘 다 `_HANDLE_GAP_FACTOR` 공유).
        gap = best_sh._handle_px() * best_sh._HANDLE_GAP_FACTOR
        targeted_pt = hp[1] if (hp is not None and hp[0] is best_sh) else None
        matched = False
        if not isinstance(best_sh, _PathItem):
            for sp, n in _shape_ports_for_preview(best_sh):
                p = QPointF(sp.x() + n.x() * gap, sp.y() + n.y() * gap)
                targeted = (targeted_pt is not None
                            and abs(targeted_pt.x() - sp.x()) < 0.5 and abs(targeted_pt.y() - sp.y()) < 0.5)
                if targeted:
                    matched = True
                    painter.setPen(QPen(QColor("white"), 1.5 / s))
                    painter.setBrush(QBrush(QColor(_BLUE)))
                else:
                    painter.setPen(QPen(QColor(_BLUE), 1.4 / s))
                    painter.setBrush(QBrush(QColor("white")))
                painter.drawEllipse(p, r, r)
        if targeted_pt is not None and not matched:
            n = hp[2]
            p = QPointF(targeted_pt.x() + n.x() * gap, targeted_pt.y() + n.y() * gap)
            painter.setPen(QPen(QColor("white"), 1.5 / s))
            painter.setBrush(QBrush(QColor(_BLUE)))
            painter.drawEllipse(p, r, r)

    def _draw_segment_preview_pill(self, painter, s):
        """[2026-08-03 Lucid 대조, rf 계정 Lucid 문서에서 직접 재현 확인 / 2026-08-04 위치 고정
        버그수정] 선택된 직교 화살표의 변 위, 고정 알약이 아닌 위치를 호버하면 속 빈(hollow)
        알약을 미리보기로 그린다 — 실제 알약(_paint_segment_handles, 항상 칠해진 파랑)과
        시각적으로 구분되고, 여기를 눌러 끌면 그 자리에 새 정점이 생긴다(`_begin_subdivide_drag`).
        위치는 커서를 따라다니지 않는다 — 고정 알약을 기준으로 커서가 있는 절반의 자체 중점에만
        찍힌다(`_segment_subdivide_preview_point`). 실제 삽입은 항상 고정 알약 자리(M)에서
        일어나므로, 커서 위치를 그대로 보여주면 "여기에 생긴다"는 오해를 준다(사용자 실측 버그
        — 알약이 마우스를 따라 몸통선을 미끄러지는 것처럼 보임). 드래그 중엔 그리지 않는다
        (그 사이 실제 지오메트리가 바뀌어 자리가 안 맞음)."""
        sa = self._seg_add
        if sa is None or self._seg_drag is not None:
            return
        item, seg_idx, scene_pt, on_pill = sa
        if on_pill:
            return
        q_local = item._segment_subdivide_preview_point(seg_idx, item.mapFromScene(scene_pt))
        scene_pt = item.mapToScene(q_local)
        horizontal = item._segment_orientation(seg_idx)
        half = item._SEG_HANDLE_PX / max(s, 1e-6)
        thick = 3.5 / max(s, 1e-6)
        if horizontal:
            r = QRectF(scene_pt.x() - half, scene_pt.y() - thick, 2 * half, 2 * thick)
        else:
            r = QRectF(scene_pt.x() - thick, scene_pt.y() - half, 2 * thick, 2 * half)
        painter.setPen(QPen(QColor(_BLUE), 1.4 / s))
        painter.setBrush(QBrush(QColor("white")))
        painter.drawRoundedRect(r, thick, thick)

    def _connect_port_at(self, view_pos):
        """[하나의 시스템으로 통합 2026-08-01, Lucid 대조] 선택된 도형의 접속점 →
        (shape, port_pt, normal) or None. `_qc_dot_at`(선택된 도형 대상, 어느 도구에서든 작동)의
        rect 판정을 그대로 재사용하되 `_shape_ports`로 실제 scene 점+법선을 함께 돌려줘
        `_hover_port_at`과 동일한 반환 계약으로 맞춘다 — 이 계약 하나로 press/move/release/paint가
        선택 여부와 무관하게 한 경로(`_hp_*` 상태 필드)를 탄다."""
        hit = self._qc_dot_at(view_pos)
        if hit is None:
            return None
        item, side = hit
        idx = {"t": 0, "r": 1, "b": 2, "l": 3}[side]
        sp, n = _shape_ports(item)[idx]
        return (item, sp, n)

    def _hover_port_at(self, view_pos):
        """[8포트 select-hover] 미선택 도형 근처 접속점 → (shape, port_pt, normal, is_discrete)
        or None. 선택된 도형은 제외 — `_connect_port_at`가 이미 그 경로를 처리해(mousePressEvent
        상단에서 어느 도구든 우선 검사), 여기서 또 잡으면 렌더가 중복된다.
        [2026-08-04 연속 호버 §8 항목16, deep-interview] Pass 1(이산 4포트, _PORT_SNAP_PX)이
        없으면 Pass 2(테두리 임의 위치 최근접점, _BORDER_SNAP_PX)로 폴백 — `_border_snap_at`의
        화살표-그리기 2단 우선순위(이산 우선, 연속 폴백)와 동일 패턴. Pass 2는 이산 포트가 없는
        _PathItem(DXF 폴백 도형)도 포함한다. `is_discrete`는 호출부(커서 분기)가 Pass 1/2를
        구분해, Pass 1은 항상 커넥터 커서·Pass 2는 테두리 안쪽/바깥쪽으로 커서를 가르는 데 쓴다."""
        margin = 30.0 / self._view_scale()
        scene_pt = self.mapToScene(view_pos)
        all_near = self._conn_shapes_near(scene_pt, margin)
        # [실사용 지적 2026-08-09] 커서가 "선택된" 도형(예: 포트로 쓰는 원)의 실제 몸통 안에
        # 있으면, 그 밑에 겹친 다른 도형의 접속점도 잡히면 안 된다. 선택된 도형은 아래 `near`에서
        # 통째로 후보 제외되기 때문에(그 도형 자신의 처리는 `_connect_port_at`가 별도로 함),
        # 이 배제로 생긴 빈자리를 겹쳐 있던 다른(미선택) 도형이 대신 차지해버리는 게 문제다.
        # [주의] 이 판정은 "선택된 도형"에만 건다 — 미선택 도형끼리는 아래 두 Pass 모두 순수
        # 거리경쟁(elimination 없음)이라 자기 것이 항상 더 가까워 자연히 이긴다. 반대로 여기를
        # "겹치면 무조건" 식으로 넓히면, 포트 자신의 접속점(도형 경계선 위의 점이라 그 도형의
        # 엄밀한 '내부' 판정 자체가 항상 거짓이 되기 쉬움)까지 오탐으로 막아
        # `test_port_participates_normally_in_hover_and_qc_systems`가 깨진다(실측 확인).
        if any(sh.isSelected() and _shape_interior_contains(sh, scene_pt) for sh in all_near):
            return None
        near = [sh for sh in all_near if not sh.isSelected()]
        best = None
        bestd = self._PORT_SNAP_PX
        for sh in near:
            if isinstance(sh, _PathItem):
                continue
            br = sh.sceneBoundingRect().adjusted(-margin, -margin, margin, margin)
            if not br.contains(scene_pt):
                continue
            for sp, n in _shape_ports_for_preview(sh):
                d = self._view_dist(sp, view_pos)
                if d <= bestd:
                    bestd, best = d, (sh, sp, n)
        if best is not None:
            return (*best, True)
        best2 = None
        bestd2 = self._BORDER_SNAP_PX
        for sh in near:
            sp, n = _nearest_border(sh, scene_pt)
            # [2026-08-04] 선택된 포트의 위치는 연속 폴백에서도 제외 — Pass 1이 discrete 4점에서
            # 이미 이 규칙을 지킨다(_shape_ports_for_preview, "선택된 포트의 리사이즈 핸들과
            # 겹침 방지"), 연속 투영점이 우연히 그 자리와 같아도 예외가 아니다.
            selected_centers = [p.mapToScene(p.rect().center())
                                 for p in (getattr(sh, "_ports", None) or []) if p.isSelected()]
            if any(math.hypot(sp.x() - c.x(), sp.y() - c.y()) < 1.0 for c in selected_centers):
                continue
            d = self._view_dist(sp, view_pos)
            if d <= bestd2:
                bestd2, best2 = d, (sh, sp, n)
        return (*best2, False) if best2 is not None else None

    def _hp_paint_ghost(self, painter, src, port_pt, port_normal, cursor_scene):
        """[하나의 시스템으로 통합 2026-08-01] 접속점 드래그 중 커넥터 고스트 — 선택 여부와
        무관하게(qc-dot·hover-port 공통) 이 하나로 그린다. 빈 캔버스에 드롭해도(아래
        _hp_create_arrow) 화살표만 생기므로(2026-08-04 4차) 도형 미리보기 자체가 없다 —
        이 함수는 처음부터 화살표 몸통·화살촉만 그린다.
        [2026-08-04 실사용 지적] 점선은 시인성이 떨어진다 — 실제 생성 결과(항상 실선)와
        동일하게 실선으로 미리보인다."""
        pen = QPen(QColor(90, 150, 235), 1.5, Qt.PenStyle.SolidLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        snap = self._qc_snap_target(cursor_scene, src)
        end = snap[0] if snap is not None else cursor_scene
        ne = snap[1] if snap is not None else None
        target = snap[2] if snap is not None else None
        obstacles, conn_rects = self._qc_route_context(src, target)
        mids = _route_ortho(port_pt, end, port_normal, ne, obstacles, _PolyArrowItem._ROUTE_CLEARANCE,
                            conn_rects=conn_rects)
        pts = _dedup_pts([port_pt] + mids + [end])
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])
        if len(pts) >= 2:
            self._draw_ghost_arrowhead(painter, pts[-2], pts[-1])
        if snap is not None:
            self._draw_snap_marker(painter, end, self._view_scale())

    def _draw_ghost_arrowhead(self, painter, tail: QPointF, tip: QPointF):
        """[UX 2026-08-01] qc-dot/hover-port 커넥터 고스트에 화살촉 미리보기 추가 — 기존엔
        몸통 선만 그려 실제 생성 결과(_hp_create_arrow, 항상 화살촉 있음)와 미리보기가
        달라 보였다(사용자 지적: Lucid는 드래그 중에도 화살촉까지 미리보인다)."""
        if tail == tip:
            return
        ang = math.atan2(tip.y() - tail.y(), tip.x() - tail.x())
        size = max(getattr(self._owner, "current_width", 1.0) * 2.5, 7.0)
        a1, a2 = ang + math.radians(150), ang - math.radians(150)
        head = QPolygonF([
            tip,
            QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1)),
            QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2)),
        ])
        painter.save()
        pen = painter.pen()
        pen.setStyle(Qt.PenStyle.SolidLine)
        # [실사용 버그 2026-08-03] 실제 화살촉(`_PolyArrowItem.paint`)과 같은 이유로 joinStyle
        # 명시 — 기본 BevelJoin이면 어깨가 깎여 미리보기와 생성 결과가 달라 보인다(이 고스트의
        # 존재 이유가 "미리보기 = 결과"이므로 렌더 규칙도 같이 맞춘다).
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        fill = QColor(pen.color()); fill.setAlpha(160)
        painter.setBrush(QBrush(fill))
        painter.drawPolygon(head)
        painter.restore()

    def _draw_hp_hover_preview(self, painter, src, port_pt, nrm):
        """[실사용 요청 2026-08-04, 참고 이미지 재현] 4방향 접속점을 드래그 없이 그냥 hover만
        해도, 클릭 시 실제로 생길 결과(도형 복제+연결 화살표, `_qc_create`의 클릭 경로와 동일
        기본 배치)를 미리 보여준다. 종전엔 이 미리보기가 `_hp_dragging`(실제로 눌러서 끄는 중)
        에만 그려져, 누르기 전까지는 작은 점 하나(`_draw_port_dots`)만 보였다 — 참고 이미지는
        누르지 않은 상태에서도 점선 고스트 사각형+화살표가 보이길 기대한다.
        배치는 `_qc_target_center(src, side, None)`(= 클릭 시 기본 델타)를 그대로 재사용해
        "미리보기 = 실제 결과"를 보장한다(고스트 시스템 전체의 기존 관례). 포트도 예외 없이
        같은 미리보기를 받는다 — 클릭=복제는 포트에도 그대로 적용되는 규칙이라(2026-08-04
        4차) 이 전제가 깨지지 않는다."""
        side = _side_from_normal(nrm)
        sr = self._qc_src_scene_rect(src)
        center = self._qc_target_center(src, side, None)
        target_rect = sr.translated(center - sr.center())
        pen = QPen(QColor(90, 150, 235), 1.3, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(target_rect)
        p_dup = _edge_mid(target_rect, _QC_OPP[side])
        painter.drawLine(port_pt, p_dup)
        self._draw_ghost_arrowhead(painter, port_pt, p_dup)

    def _hp_create_arrow(self, src, port_pt, cursor_scene):
        """[하나의 시스템으로 통합 2026-08-01 → 2026-08-04 4차 갱신] 도형(선택 여부 무관)의
        접속점에서 드래그 종료 — 스냅 대상 있으면 커넥터만, 없으면(빈 캔버스) 끝이 비어있는
        (미결) 화살표만 남긴다. _qc_create_arrow_only와 종착 스냅·라우팅 로직을 공유 — 그쪽은
        side 문자 기반 API로 테스트·기존 호출부용으로 남겨둔다.
        [2026-08-04 4차 — 실사용 결정] 예전엔 빈 캔버스에 놓으면 원본과 같은 도형을 복제해
        같이 바인딩했다(`_qc_spawn_dup`) — 포트에 이 규칙이 적용되면 "포트는 화살표만"이라는
        요구와 충돌해 여러 특례가 필요했다. 도형 종류를 가리지 않고 "클릭=복제(`_qc_create`,
        안 바뀜) / 드래그=화살표만(여기)"으로 규칙 자체를 통일해, 포트만의 예외 코드 없이
        포트가 원하는 동작(드래그=화살표만)을 저절로 만족시킨다(실사용 제안)."""
        owner = self._owner
        arrow = _PolyArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
        arrow._style = getattr(owner, "current_style", arrow._style)      # sticky 선스타일
        arrow._curve_r = float(getattr(owner, "current_curve_r", arrow._curve_r))  # sticky 모서리 반경
        arrow.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                       | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        arrow.set_bound(0, src, src.mapFromScene(port_pt))
        snap = self._qc_snap_target(cursor_scene, src)
        end = snap[0] if snap is not None else cursor_scene
        arrow.set_points(port_pt, end)
        if snap is not None and snap[2] is not None and (
                snap[2] is not src or _far_enough_for_self_loop(port_pt, end)):
            arrow.set_bound(1, snap[2], snap[2].mapFromScene(end))
        arrow._auto_route = True
        self.scene().addItem(arrow)
        arrow._apply_routing()
        self._owner.push_undo_add(arrow)
        self.scene().clearSelection()
        arrow.setSelected(True)
        return arrow

    def leaveEvent(self, event):
        # 커서가 뷰를 벗어나면 스냅·waypoint 예고 마커 정리(잔상 방지).
        if (self._snap_preview is not None or self._seg_add is not None or self._hp_hover is not None
                or self._port_dot_shape is not None):
            self._snap_preview = None
            self._seg_add = None
            self._hp_hover = None
            self._port_dot_shape = None
            self._table_col_add = None
            self.viewport().update()
        super().leaveEvent(event)

    def drawBackground(self, painter, rect):
        """[그리드/스냅투그리드] 점 격자 — 씬 단위 고정 간격, 화면 밀도가 너무 촘촘해지면
        (줌아웃) 자동 숨김. 표시되는 rect(이미 화면에 보이는 영역)만 순회해 무한캔버스에서도
        비용이 줌·팬과 무관하게 유계 — 그래도 극단적 조합을 대비해 점 개수 상한을 둔다."""
        super().drawBackground(painter, rect)
        if not getattr(self._owner, "grid_enabled", True):
            return
        s = self._view_scale()
        sp = _GRID_SPACING
        if sp * s < _GRID_MIN_PX:
            return
        x0 = math.floor(rect.left() / sp) * sp
        y0 = math.floor(rect.top() / sp) * sp
        cols = int((rect.right() - x0) / sp) + 2
        rows = int((rect.bottom() - y0) / sp) + 2
        if cols * rows > _GRID_MAX_DOTS:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(*_GRID_DOT_RGBA)))
        r = 1.1 / s
        y = y0
        for _ in range(rows):
            x = x0
            for _ in range(cols):
                painter.drawEllipse(QPointF(x, y), r, r)
                x += sp
            y += sp
        painter.restore()

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if not self._owner.is_edit_mode():
            return
        s = self._view_scale()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # [우리 확장] 화살표 도구로 도형 근처면 포트 점 예고(스냅 마커보다 먼저 그려 아래 깔림).
        self._draw_port_dots(painter, s)
        self._draw_segment_preview_pill(painter, s)
        # 그리는 중(드래그)이거나 클릭 배치 중이면 스냅된 시작·tip에 마커(곡선·직선화살 공통).
        drawing = (self._drawing and self._temp is not None) or (self._place is not None)
        if drawing:
            if self._arrow_snap_exit is not None:
                self._draw_snap_marker(painter, self._start, s)
            if self._arrow_tip_snap is not None:
                self._draw_snap_marker(painter, self._arrow_tip_snap, s)
        elif self._snap_preview is not None:
            # 유휴 — 화살표 도구가 테두리 근처(스냅 발동 예고)
            self._draw_snap_marker(painter, self._snap_preview, s)
        # [우리 확장] 방향 감지 러버밴드 박스 — window=파란 실선, crossing=초록 점선(AutoCAD).
        if self._rb_active and self._rb_origin is not None \
                and self._rb_origin != self._rb_current:
            rect = self._rb_scene_rect()
            window = self._rb_is_window()
            color = QColor(70, 130, 220) if window else QColor(90, 190, 90)
            fill = QColor(color); fill.setAlpha(45)
            pen = QPen(color, 1.0)
            pen.setCosmetic(True)  # 줌과 무관하게 1px(선 두께 흔들림 방지)
            if not window:
                pen.setStyle(Qt.PenStyle.DashLine)  # crossing = 점선
            painter.setPen(pen)
            painter.setBrush(QBrush(fill))
            painter.drawRect(rect)
            # [성능 조사 2026-07-30] 드래그 중 실제 선택(setSelected) 대신 저비용 하이라이트만 —
            # Lucid처럼 "닿은 객체 색만 바꾸고, 놓는 순간 정확히 확정"하는 느낌을 재현.
            # [강조선 위치·굵기 재설계 2026-08-01, 3차] 앞선 두 시도(패딩 제거 → 얇아짐, cosmetic
            # 폭 수정)는 전부 '중심선 위에 딱 겹쳐 그리기'를 유지한 채였다. 사용자가 Lucid와
            # 대조해 지목한 진짜 차이는 위치 자체 — 우리는 테두리 "중심"에 겹쳐 그려서 (a) 도형
            # 자체 선(보통 1px)과 정확히 겹쳐 안티에일리어싱이 섞여 옅어 보이고 (b) 줌이 커지면
            # 도형 자체 선은 장면(scene) 단위라 함께 굵어지는데 강조선만 화면(device) 고정폭이라
            # 상대적으로 더 얇아 보였다. Lucid는 테두리 "바깥"에 갭을 두고 감싼다 — 그러면 도형
            # 자체 선과 겹칠 일이 없어 항상 또렷하고, 갭·굵기를 장면 단위로 잡으면 줌에 비례해
            # 커져 도형과 시각적 비중이 항상 맞는다. 이 앱이 이미 같은 패턴을 쓰고 있다(손안의
            # 카드) — 평소 단일 선택 표시(`_content_rect`)가 `pen.widthF()/2 + 여유` 만큼 장면
            # 단위로 부풀린 사각을 그린다. 그 관례를 그대로 확장: `_highlight_band()`(모듈
            # 레벨 — 개별 선택 강조 `_paint_selection_highlight`와 완전히 같은 함수, 2026-08-01
            # 통일)가 패딩 없는 중심선을 도형 자체 펜 두께에 비례한 폭으로 스트로크해 '띠'로
            # 만들고, 바깥쪽만 남기고 안쪽은 깎는다(Lucid 스타일) — _base_shape()의 옛 8px+
            # 고정 패딩과 달리 폭이 도형 두께에 비례해 계산되므로 얇은 선엔 얇게, 굵은 선엔
            # 그만큼 굵게 뜨고, 안쪽 절반이 도형 내부와 겹쳐 낭비되지 않는다.
            edge_pen = QPen(color, 1.0)
            edge_pen.setCosmetic(True)
            painter.setPen(edge_pen)
            fill2 = QColor(color); fill2.setAlpha(90)
            painter.setBrush(QBrush(fill2))
            for it in self._rb_preview:
                painter.drawPath(it.mapToScene(_highlight_band(it)))
        # [하나의 시스템으로 통합 2026-08-01] 접속점 드래그 중 커넥터 고스트 — 선택 여부와
        # 무관하게 한 경로(_hp_*)로 처리. [2026-08-03 중복 제거] 유휴 hover 강조는 더 이상
        # 여기서 테두리 위에 별도 마커를 그리지 않는다 — 선택된 도형은 이미 `_hover_handle`
        # 경로가 qc-dot 자신을(오프셋 위치 그대로) 강조하고, 미선택 도형은 `_draw_port_dots`가
        # 대상 점 자신을 강조한다(아래) — 실사용 지적: 오프셋 점이 이미 있는데 테두리 위에
        # 점이 "또" 생겨 중복으로 보였다.
        if self._hp_dragging and self._hp_src is not None and self._hp_cursor is not None:
            self._hp_paint_ghost(painter, self._hp_src, self._hp_port, self._hp_normal, self._hp_cursor)
        # [실사용 요청 2026-08-04] 누르지 않고 4방향 접속점만 hover해도 위 고스트를 미리 보여준다.
        # `_hp_hover`는 선택 도형(`_connect_port_at`, 3-tuple, 항상 discrete)·미선택 도형
        # (`_hover_port_at`, 4-tuple, `is_discrete` 포함) 두 경로가 공유하는 필드 — 연속 폴백
        # (Pass 2, is_discrete=False)은 접속점이 아니라 테두리 임의 위치이므로 제외한다.
        elif self._hp_hover is not None and len(self._hp_hover) in (3, 4) and (
                len(self._hp_hover) == 3 or self._hp_hover[3]):
            hh_src, hh_port, hh_nrm = self._hp_hover[0], self._hp_hover[1], self._hp_hover[2]
            self._draw_hp_hover_preview(painter, hh_src, hh_port, hh_nrm)
        # [2e] 스마트 정렬 가이드선 — 이동 중 정렬 맞은 축에 마젠타 실선. 인접(맞닿음) 매칭은
        # 정의상 가이드 좌표가 도형 자신의 테두리(선택 파란 테두리 등)와 정확히 겹쳐, 색이 섞여
        # 거의 안 보이는 문제가 실사용에서 발견됨(GIF 프레임 픽셀 분석으로 확인 — 로직·렌더링
        # 자체는 정상, 다른 UI 색과 겹쳐 묻히는 것만 문제). 검정 헤일로를 먼저 깔아 어떤 배경
        # 색과 겹쳐도 마젠타가 도드라지게 한다(Figma류 가이드선 관례).
        if self._align_guides:
            halo = QPen(QColor(0, 0, 0, 180), 3.0)
            halo.setCosmetic(True)
            core = QPen(QColor(230, 60, 160), 1.5)
            core.setCosmetic(True)
            for pen in (halo, core):
                painter.setPen(pen)
                for g in self._align_guides:
                    if g[0] == "v":
                        painter.drawLine(QPointF(g[1], g[2]), QPointF(g[1], g[3]))
                    else:
                        painter.drawLine(QPointF(g[2], g[1]), QPointF(g[3], g[1]))
        # [M4-4] 세그먼트 핸들은 아이템(_paint_segment_handles)이 직접 그린다 — 여기선 마커 없음.
        # [우리 확장] 다중선택 그룹 변형 오버레이 — 공통 bbox + 모서리(스케일)·상단(회전) 핸들.
        # stretch 진행 중엔 그리지 않는다(두 오버레이 겹침 방지 — 그때 조작은 stretch가 소유).
        if self._group.available() and not (self._stretch_arm or self._stretch_active):
            self._group.paint(painter, s)
        # [Stage2b] stretch 오버레이 — 무장(걸친 정점 ●)·활성(기준점→커서 프리뷰선) + crossing 박스.
        if self._stretch_arm or self._stretch_active:
            self._paint_stretch(painter, s)

    # ---- 줌 (휠) — 주석 위면 속성 변경, 아니면 owner의 hug-zoom(창이 이미지에 맞게) ----
    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        if dy == 0:
            return
        # 무한캔버스는 줌이 잦으므로 '그냥 휠 = 항상 줌'. 커서 아래 주석의 속성 조절
        # (도형=두께 / 텍스트·번호=크기)은 'Shift+휠'로 옮긴다(휠-줌 충돌 방지).
        if (self._owner.is_edit_mode()
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            bg = getattr(self._owner, "_bg_item", None)
            for it in self.items(event.position().toPoint()):
                if it is bg:
                    continue
                if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                    self._owner.adjust_item_property(it, 1 if dy > 0 else -1)
                    event.accept()
                    return
        self._owner._on_wheel_zoom(dy)

    # ---- Shift 제약 적용 ---------------------------------------------------
    @staticmethod
    def _constrain(start: QPointF, cur: QPointF, mode: str) -> QPointF:
        dx, dy = cur.x() - start.x(), cur.y() - start.y()
        if mode == "square":
            side = max(abs(dx), abs(dy))
            return QPointF(start.x() + (side if dx >= 0 else -side),
                           start.y() + (side if dy >= 0 else -side))
        if mode == "angle":
            length = math.hypot(dx, dy)
            snapped = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            return QPointF(start.x() + length * math.cos(snapped),
                           start.y() + length * math.sin(snapped))
        if mode == "ortho":
            # [우리 확장] F8 Ortho — start 기준 0°/90°만. |dx|≥|dy|면 수평(y 고정), 아니면 수직(x 고정).
            if abs(dx) >= abs(dy):
                return QPointF(cur.x(), start.y())
            return QPointF(start.x(), cur.y())
        return cur

    def _cur_point(self, event) -> QPointF:
        sp = self.mapToScene(event.position().toPoint())
        tool = self._owner.current_tool
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if tool in ("rect", "ellipse"):
                return self._constrain(self._start, sp, "square")
            if tool in ("line", "arrow", "sarrow"):
                return self._constrain(self._start, sp, "angle")
        # [우리 확장] F8 Ortho — Shift(45°)가 없을 때 선·화살표 드래그를 0/90°로 제약.
        # (sarrow 멀티정점 클릭 배치는 _poly_apply_ortho가 별도 처리 — 여기선 드래그 2점만)
        if getattr(self._owner, "ortho_enabled", False) and tool in ("line", "arrow", "sarrow"):
            return self._constrain(self._start, sp, "ortho")
        # [그리드 스냅] 새 도형 생성 드래그(네모·원·심볼·선)에만 — 화살표류는 제외(테두리/포트
        # 스냅이 항상 우선이어야 하는 커넥터라 격자가 끼어들면 지속연결이 어긋난다).
        if tool in ("rect", "ellipse", "line") or tool.startswith("sym:"):
            return self._grid_snap_scene(sp)
        return sp

    def _grid_snap_scene(self, pt: QPointF) -> QPointF:
        """[그리드 스냅] 씬 좌표를 격자 교차점으로 양자화. owner.grid_enabled False면 그대로."""
        if not getattr(self._owner, "grid_enabled", True):
            return pt
        sp = _GRID_SPACING
        return QPointF(round(pt.x() / sp) * sp, round(pt.y() / sp) * sp)

    # ---- 그리기 ------------------------------------------------------------
    def mousePressEvent(self, event):
        # 휠(가운데) 버튼 드래그 = 창(이미지) 이동 — 편집/뷰어 모두. 좌클릭은 그리기에 쓰이므로.
        if event.button() == Qt.MouseButton.MiddleButton:
            self._owner._win_drag_start(event.globalPosition().toPoint())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        # [Phase 6 M3 #16] 우클릭 재정의(승인 설계) — 상태 분기:
        #   BUSY(무장/그리기 중) → 취소(M2 탈출구 그대로, press 즉시) / 유휴(select·손, 진행중 없음)
        #   → 드래그=캔버스 팬 · 제자리 탭=컨텍스트 메뉴. 유휴는 move/release로 팬/메뉴를 가른다.
        # (M2에서 우클릭이 '취소'로 유효하던 경우와 BUSY를 정확히 일치시켜 그 탈출구를 보존한다.)
        if event.button() == Qt.MouseButton.RightButton and self._owner.is_edit_mode():
            if self._rmb_is_busy():
                self._right_click_cancel()
            else:
                self._rmb_press = event.position().toPoint()
                self._rmb_panning = False
            return
        # [우리 확장] 클릭 배치 진행 중 좌클릭 = 다음 점(2점도구 확정·sarrow 정점추가).
        # (릴리스로 끝내지 않으므로 이 분기가 최우선 — 끝점/세그먼트 판정보다 앞선다.)
        if self._place is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._place_click(event)
                return
        # 뷰어 모드: 좌클릭 드래그 = 창 이동 (그리기·선택 안 함)
        if not self._owner.is_edit_mode():
            if event.button() == Qt.MouseButton.LeftButton:
                self._owner._win_drag_start(event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._press_scene = self.mapToScene(event.position().toPoint())   # 실제 클릭 지점(스냅 전)
        # [Stage2b] stretch 진행 — 활성(기준점 이미 찍음) 클릭=도착점 확정, 무장 클릭=기준점. 최우선.
        if self._stretch_active:
            self._stretch_apply(self._press_scene)
            self._stretch_commit()
            return
        if self._stretch_arm:
            self._stretch_begin(self._press_scene)
            return
        # [우리 확장] 편집 중 텍스트가 있고 이번 좌클릭이 그 텍스트 위가 아니면 편집을 마무리한다.
        # (빈 영역 클릭은 아래 러버밴드 분기가 super 전에 return해 focusOut이 안 나던 문제 보완 —
        #  clearFocus → focusOutEvent가 빈 텍스트는 폐기, 아니면 완료. 그 텍스트 위 클릭은 캐럿 이동.)
        fi = self.scene().focusItem()
        if isinstance(fi, QGraphicsTextItem) \
                and fi.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction \
                and fi not in self.items(event.position().toPoint()):
            fi.clearFocus()
        # 이미 선택된 화살표/선의 끝점·곡선(bend) 조절 핸들 위 press는 겹친 도형 테두리보다 우선한다
        # (선택된 아이템의 핸들이 먼저 작동해야 함). 끝점/핸들은 도형 테두리에 딱 붙는 일이 잦아
        # Z-order 배달로는 아래 도형이 press를 가로챈다 → 그 아이템을 잠깐 최상단으로 올려 Qt가
        # 그 아이템에 press를 배달(=grab)하게 한 뒤 Z를 즉시 복원한다(grab은 Z와 무관하게 유지).
        # 끝점 우선은 "새 연결 화살표 생성"(arrow 도구)보다도 앞서야 겹칠 때 새 화살표가 안 생긴다.
        vpos = event.position().toPoint()
        # 커서 맨 위가 화살표 라벨이면 라벨 드래그 우선(끝점·bend 핸들보다) — 라벨이 핸들과 겹칠 때 대비.
        _top = self.items(vpos)
        _on_label = bool(_top) and isinstance(_top[0], _ConnectorLabel)
        grab = None if _on_label else (self._selected_endpoint_item(vpos) or self._bend_handle_at(vpos))
        if grab is not None:
            if self._snap_preview is not None:
                # 끝점/핸들 드래그 시작 → 유휴 테두리 스냅 예고 마커를 즉시 제거(드래그 중엔
                # 버튼 눌림으로 _update_snap_preview가 안 돌아 이전 마커가 도형에 남던 잔상 방지).
                self._snap_preview = None
                self.viewport().update()
            old_z = grab.zValue()
            grab.setZValue(1e9)
            super().mousePressEvent(event)
            grab.setZValue(old_z)
            return
        # [M4-4 → 2026-08-03] 직선화살표 세그먼트 위 press(정점 아님). 알약 위면 변 전체를
        # 수직 이동(기존), 알약이 아닌 위치면 그 자리에 새 정점을 끼워 가까운 쪽 절반만 이동
        # (Lucid 대조, _segment_add_at 참조).
        if self._seg_add is not None and event.button() == Qt.MouseButton.LeftButton:
            item, seg_idx, scene_pt, on_pill = self._seg_add
            self._seg_add = None
            self._seg_undo = [(item, item.capture_geom())]   # 드래그 전 스냅샷(undo)
            if on_pill:
                item._begin_segment_drag(seg_idx)
            else:
                item._begin_subdivide_drag(seg_idx, item.mapFromScene(scene_pt))
            self._seg_drag = item
            self.viewport().update()
            return
        # [열폭 드래그 2026-07-31] 선택된 표의 내부 열 경계선 press = 그 경계를 잡아 좌우로
        # 이동(양옆 열끼리 폭 교환, 표 전체폭은 불변).
        if self._table_col_add is not None and event.button() == Qt.MouseButton.LeftButton:
            item, idx = self._table_col_add
            self._table_col_add = None
            self._table_col_undo = [(item, item.capture_geom())]   # 드래그 전 스냅샷(undo)
            item._begin_col_drag(idx)
            self._table_col_drag = item
            self.viewport().update()
            return
        # [우리 확장] 다중선택 그룹 변형 핸들(회전·스케일) press — 선택/이동보다 우선.
        if self._group.available():
            hit = self._group.handle_at(self.mapToScene(vpos))
            if hit is not None:
                self._group.begin(hit, self.mapToScene(vpos))
                self._group_dragging = True
                return
        # [하나의 시스템으로 통합 2026-08-01, Lucid 대조] 접속점 press(이동/선택보다 우선) —
        # 클릭=복제+화살표, 드래그=화살표(대상 없으면 도형도 생성). 선택된 도형은 어느
        # 도구에서든 잡힌다(그린 직후 도구 전환 없이 바로 체이닝하기 위한 기존 의도 유지) —
        # 여기서 못 잡으면 아래 tool=="select" 분기가 미선택 도형의 hover-port를 마저 검사한다.
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._connect_port_at(vpos)
            if hit is not None:
                src, port_pt, nrm = hit
                self._hp_src = _port_owner_at(src, port_pt)   # [실사용 버그 수정] 포트면 포트에 바인딩
                self._hp_port, self._hp_normal = port_pt, nrm
                self._hp_dragging = True
                self._hp_is_discrete = True   # 선택된 도형의 qc-dot은 정의상 항상 이산 4점
                self._hp_cursor = None   # 릴리스까지 이동(임계 초과) 없으면 즉시 생성(클릭)
                self._hp_press_scene = self.mapToScene(vpos)
                self._hp_hover = None
                return
        tool = self._owner.current_tool
        # 화살표 도구 + 도형 테두리 근처 press → 테두리에 스냅된 곡선 화살표 시작(도형 선택/이동보다 우선).
        # 이 분기가 빈영역/도형-위 선택 판정보다 앞서야 테두리에서 새 화살표가 시작된다(이슈 A).
        if tool == "arrow":
            snap = self._border_snap_at(event.position().toPoint())
            if snap is not None:
                owner = self._owner
                it = _ArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
                self._start = snap[0]
                self._arrow_snap_exit = snap[1]
                self._arrow_tip_snap = None
                if snap[2] is not None:   # [M4-2b] 도형이면 시작 고정 부착점, 선·화살표면 기하 스냅만
                    it.set_bound(0, snap[2], snap[2].mapFromScene(snap[0]))
                it.set_points(self._start, self._start)
                self._begin_draw(it)
                return
        # 직선화살(sarrow)도 도형 테두리 근처 press면 테두리-스냅 시작(도형 선택/이동보다 우선).
        # sarrow는 멀티정점이라 드래그 전용으로 두지 않는다(테두리에서도 클릭 배치 허용).
        if tool == "sarrow":
            snap = self._border_snap_at(event.position().toPoint())
            if snap is not None:
                owner = self._owner
                it = _PolyArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
                self._start = snap[0]
                self._arrow_snap_exit = snap[1]   # 시작 마커
                self._arrow_tip_snap = None
                if snap[2] is not None:   # [M4-2b] 도형이면 시작 고정 부착점, 선·화살표면 기하 스냅만
                    it.set_bound(0, snap[2], snap[2].mapFromScene(snap[0]))
                it.set_points(self._start, self._start)
                self._begin_draw(it)
                return
        if tool is None:
            # 손 모드: 빈 영역 좌드래그 = 창 이동, 주석 위 = 단일 선택/이동(하이브리드).
            if self._is_empty_area(event.position().toPoint()):
                self._owner._win_drag_start(event.globalPosition().toPoint())
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                self._none_win_dragging = True
                return
            self._maybe_alt_drag_copy(event)   # [편의기능] Alt+드래그 = 제자리 복제 후 드래그
            self._snapshot_movable()   # 주석 드래그 이동을 undo로 되돌리기 위해
            return super().mousePressEvent(event)
        if tool == "select":
            # [8포트 select-hover] 미선택 도형의 포트 근처 press — 드래그 여부는 release에서 가른다
            # (포트가 테두리 위라 클릭=선택과 자리가 겹침, deep-interview 2026-07-29). Shift는
            # 다중선택 토글 의도이므로 건드리지 않는다.
            # [실사용 버그 수정 2026-08-04, 2차] `is_discrete=False`(Pass 2 연속 폴백, §8 항목16)도
            # press는 여전히 여기서 잡는다 — 테두리 어디서든 드래그하면 커넥터가 시작돼야 하기
            # 때문(1차 수정에서 여기를 통째로 건너뛰게 했더니 연속 위치 드래그로 화살표를 못
            # 그리는 회귀가 남 — 실사용 지적: "드래그하면 화살표로 작동해야하는데 안됨"). 다만
            # "드래그 안 하고 그냥 클릭"의 결과는 이산/연속이 갈라야 한다 — 그건 release에서
            # `_hp_is_discrete`로 분기(이산=즉시 도형복제+화살표, 연속=그냥 선택).
            if event.button() == Qt.MouseButton.LeftButton and not (
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                hp = self._hover_port_at(vpos)
                if hp is not None:
                    src, port_pt, nrm, is_discrete = hp
                    self._hp_src = _port_owner_at(src, port_pt)   # [실사용 버그 수정] 포트면 포트에 바인딩
                    self._hp_port, self._hp_normal = port_pt, nrm
                    self._hp_dragging = True
                    self._hp_is_discrete = is_discrete
                    self._hp_cursor = None
                    self._hp_press_scene = self.mapToScene(vpos)
                    self._hp_hover = None
                    return
            # 빈 영역 드래그 = 방향 감지 러버밴드(window/crossing), 아이템 위 = 이동/선택.
            # 창 이동은 상단 코랄 드래그바로. (편집 모드 본문 pan은 제거)
            if self._is_empty_area(vpos):
                # [편의기능] 다중선택 바운딩박스 안쪽 빈틈이면 러버밴드 대신 그룹 전체 이동으로
                # 취급(Shift는 추가선택 의도이므로 기존 러버밴드 경로 그대로 둠). 실제 도형이
                # 없어 Qt가 못 잡으므로 델타를 직접 계산해 선택 아이템들에 moveBy한다.
                if self._group_body_area_at(vpos) and not (
                        event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._snapshot_movable()
                    self._group_body_drag = True
                    self._group_body_anchor = self.mapToScene(vpos)
                    return
                # [우리 확장] Qt 기본 RubberBandDrag 대신 커스텀 밴드 시작(방향별 window/crossing).
                self._rb_active = True
                self._rb_origin = QPoint(vpos)
                self._rb_current = QPoint(vpos)
                # Shift면 기존 선택에 더하고, 아니면 새로 시작(빈영역 클릭=선택해제와 일관).
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._rb_base = list(self.scene().selectedItems()) if shift else []
                self._apply_rubber_selection()
                self.viewport().update()
                return
            self._maybe_alt_drag_copy(event)   # [편의기능] Alt+드래그 = 제자리 복제 후 드래그
            self._snapshot_movable()   # 아이템 드래그 이동을 undo로 되돌리기 위해
            return super().mousePressEvent(event)

        # 도형 도구는 기존 주석 위를 클릭하면 그리기 대신 선택/이동.
        # 단, 펜은 빽빽이 겹쳐 그리므로 항상 그린다(펜 선의 선택/이동은 V 도구로).
        if tool != "pen" and not self._is_empty_area(event.position().toPoint()):
            self._maybe_alt_drag_copy(event)   # [편의기능] Alt+드래그 = 제자리 복제 후 드래그
            self._snapshot_movable()
            return super().mousePressEvent(event)

        sp = self.mapToScene(event.position().toPoint())
        # [그리드 스냅] 생성 시작점도 이동 중(_cur_point)과 동일 대상(네모·원·심볼·선)에 맞춘다 —
        # 안 하면 시작 모서리는 격자 밖에 남고 드래그로 옮긴 반대쪽 모서리만 격자에 맞아 어긋난다.
        if tool in ("rect", "ellipse", "line") or tool.startswith(("sym:", "customsym:")):
            sp = self._grid_snap_scene(sp)
        self._start = sp
        owner = self._owner
        pen = owner.make_pen()

        if tool.startswith("customsym:"):
            # [신규기능 §8-8] 커스텀 심볼은 그룹이라 rect처럼 드래그로 그릴 수 없다 —
            # sym:*와 달리 클릭 즉시 원본 비율 그대로 배치(text/badge와 같은 단발 배치).
            owner._create_shape_at(tool, sp)
            return
        if tool == "rect":
            it = _RectItem(QRectF(sp, sp))
            it.setPen(pen)
            it.setBrush(owner.make_brush())   # [신규기능] sticky 채움색(기본 투명)
            self._begin_draw(it)
        elif tool.startswith("sym:"):
            # [우리 확장] 심볼/스텐실 — 네모와 동일한 드래그 그리기(setRect 기반).
            it = _SymbolItem(tool[4:], QRectF(sp, sp))
            it.setPen(pen)
            it.setBrush(owner.make_brush())
            self._begin_draw(it)
        elif tool == "ellipse":
            it = _EllipseItem(QRectF(sp, sp))
            it.setPen(pen)
            it.setBrush(owner.make_brush())
            self._begin_draw(it)
        elif tool == "line":
            it = _LineItem(QLineF(sp, sp))
            it.setPen(pen)
            self._begin_draw(it)
        elif tool == "arrow":
            it = _ArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
            it.set_points(sp, sp)
            self._arrow_snap_exit = None   # 자유 시작(테두리 스냅 아님) → 직선/자유 곡선
            self._arrow_tip_snap = None
            self._begin_draw(it)
        elif tool == "sarrow":
            # [우리 확장] 하이브리드: 다른 도형처럼 드래그로 시작(드래그=2점 직선, 릴리스 시
            # 이동이 없으면 클릭 배치 모드로 전환돼 멀티정점 폴리라인이 된다).
            it = _PolyArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
            # [A3] 시작점이 도형 테두리 근처면 스냅(라이브 시작 마커 + 확정 시 _bind_poly_ends가 바인딩).
            ssnap = self._border_snap_at(event.position().toPoint())
            if ssnap is not None:
                self._start = ssnap[0]
                self._arrow_snap_exit = ssnap[1]   # drawForeground 시작 마커 트리거
            else:
                self._arrow_snap_exit = None
            it.set_points(self._start, self._start)
            self._begin_draw(it)
        elif tool == "pen":
            self._path = QPainterPath(sp)
            it = _PathItem(self._path)
            it.setPen(pen)
            self._begin_draw(it)
        elif tool == "text":
            it = _TextItem(owner.current_color)
            it.apply_font_size(owner.current_font_size)
            it.set_bg(owner.current_text_bg)
            # I-beam(세로 막대 중심)이 클릭점 → 캐럿이 그 자리에 오도록 배치 보정.
            # documentMargin만큼 왼쪽, 첫 줄 높이 절반만큼 위로 당긴다(안 하면 글자가 처져 보임).
            margin = it.document().documentMargin()
            line_h = QFontMetricsF(it.font()).height()
            it.setPos(QPointF(sp.x() - margin, sp.y() - margin - line_h / 2))
            self.scene().addItem(it)
            owner.push_undo_add(it)
            it.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            it.setFocus()
            # setFocus가 이전 편집 텍스트의 focusOut→재선택을 유발하므로, 그 뒤에 비운다.
            # (새 텍스트 시작 = 다른 항목 선택 해제. 새 텍스트는 selected 아닌 편집 상태로 둠)
            self.scene().clearSelection()
            # 다른 도구처럼 텍스트 도구를 유지해 연속 배치 가능(빈 텍스트는 focusOut 시 정리).
        elif tool == "badge":
            it = _BadgeItem(owner.next_badge_number(), owner.current_color)
            it.setScale(owner.current_badge_size / float(_DEFAULT_BADGE))
            it.setPos(sp)
            self.scene().addItem(it)
            owner.push_undo_add(it)
            self.scene().clearSelection()
            it.setSelected(True)
        elif tool in ("port_rect", "port_circle"):
            # [신규기능 §8-12] 포트는 badge/text처럼 단발 클릭 배치 — 드래그로 그리지 않는다.
            owner._create_port_at(tool, sp)

    def _begin_draw(self, item: QGraphicsItem):
        # [M2 #3] 화살표는 pen()이 없어 make_pen의 sticky current_style을 못 받는다 →
        # 그리기 시작 시 여기서 스탬프(pen 기반 도형은 make_pen이 이미 반영, hasattr로 no-op).
        if hasattr(item, "_style"):
            item._style = getattr(self._owner, "current_style", item._style)
        # [화살표 통합] 직교 커넥터의 모서리 반경도 같은 초크포인트에서 sticky 값을 스탬프한다.
        if hasattr(item, "_curve_r"):
            item._curve_r = float(getattr(self._owner, "current_curve_r", item._curve_r))
        item.setZValue(1)
        self.scene().addItem(item)
        self._temp = item
        self._drawing = True
        self._snap_preview = None   # 그리기 시작 → 유휴 스냅 예고 마커 정리
        self.viewport().update()

    # ---- [우리 확장] 하이브리드 클릭 배치 (모든 도형 도구) ------------------
    # 드래그(press-move-release)로 그릴 수도, 클릭으로 점을 놓을 수도 있다. 릴리스 시
    # 이동량이 임계 미만(=끌지 않은 클릭)이면 _enter_click_place로 전환한다.
    #   · 2점 도구(rect/ellipse/line/arrow): 둘째 클릭이 확정.
    #   · sarrow: 클릭마다 정점 추가, 더블클릭/Enter/우클릭 마무리.
    # 마지막 점은 커서를 따라다니는 미리보기. F8 Ortho면 직전 점 기준 0/90°. Esc·도구전환=폐기.
    def _poly_apply_ortho(self, it: "_PolyArrowItem", scene_p: QPointF) -> QPointF:
        if not getattr(self._owner, "ortho_enabled", False) or len(it._pts) < 2:
            return scene_p
        anchor = it.mapToScene(it._pts[-2])   # 직전(확정) 정점
        return self._constrain(anchor, scene_p, "ortho")

    _MIN_SNAP_SPAN_PX = 30.0  # tip 스냅점이 직전 점에서 이 픽셀 미만이면 무시(극소 화살표 방지)

    def _snap_ortho_to_border(self, ortho_p: QPointF, anchor_scene: QPointF) -> QPointF:
        """[A3] F8일 때도 ortho'd 점이 도형 테두리 근처면 그 테두리점으로 스냅(+마커).
        수직 모서리에 수평선이 닿으면 최근접점이 같은 y라 축(수평/수직)이 보존된다.
        직전 점(anchor)에서 너무 가까운 스냅은 무시(극소 세그먼트 방지)."""
        snap = self._border_snap_at(self.mapFromScene(ortho_p))
        if (snap is not None and snap[2] is not None
                and self._view_dist(snap[0], self.mapFromScene(anchor_scene)) >= self._MIN_SNAP_SPAN_PX):
            self._arrow_tip_snap = snap[0]
            self._arrow_tip_snap_shape = snap[2]   # [라이브 직각] tip 도형 — 미리보기 conn 바인딩용
            return snap[0]
        self._arrow_tip_snap = None
        self._arrow_tip_snap_shape = None
        return ortho_p

    def _poly_place_point(self, event, item):
        """[버그수정] sarrow 배치·미리보기 공통 점 — 미리보기(move)와 클릭(_place_click)이 항상
        같은 좌표를 쓰게 한다(전엔 미리보기=테두리스냅 / 클릭=ortho로 어긋나, F8에서 수평이
        더블클릭 때만 되던 문제). F8 Ortho면 직전 점 기준 0/90° + 테두리 근처면 그 위로 스냅
        (축 보존), 아니면 테두리 스냅, 둘 다 아니면 커서."""
        anchor = item.mapToScene(item._pts[-2])
        if getattr(self._owner, "ortho_enabled", False):
            ortho_p = self._constrain(anchor, self.mapToScene(event.position().toPoint()), "ortho")
            return self._snap_ortho_to_border(ortho_p, anchor)
        snapped = self._poly_border_snap_tip(event, anchor)
        return snapped if snapped is not None else self.mapToScene(event.position().toPoint())

    def _poly_border_snap_tip(self, event, anchor_scene=None):
        """[A3] 직선화살 끝점 라이브 스냅 — 도형 테두리 근처면 그 씬점(+마커), 아니면 None(+마커 해제).
        곡선화살처럼 그리는 중 끝점이 테두리에 시각적으로 달라붙어 사용자가 붙일 위치를 본다.
        단 직전 점(anchor)에서 너무 가까운 스냅은 무시 — 같은 테두리에 겹친 극소 세그먼트 방지."""
        snap = self._border_snap_at(event.position().toPoint())
        if (snap is not None and anchor_scene is not None
                and self._view_dist(snap[0], self.mapFromScene(anchor_scene)) < self._MIN_SNAP_SPAN_PX):
            snap = None
        self._arrow_tip_snap = snap[0] if snap is not None else None
        self._arrow_tip_snap_shape = snap[2] if snap is not None else None   # [라이브 직각] tip 도형
        return snap[0] if snap is not None else None

    def _enter_click_place(self, item, tool):
        """드래그 없는 클릭 → 클릭 배치 모드 진입. item은 이미 시작점을 가진 상태(퇴화)."""
        # [화살표 그리기 라이브 직각] 클릭(무드래그)인데 미리보기가 엘보로 늘어났으면 시작점 2개로
        # 되돌려 클릭배치를 깨끗한 상태에서 시작(3점↑ 잔재가 수동 폴리라인으로 새지 않게).
        if isinstance(item, _PolyArrowItem) and len(item._pts) > 2:
            s = QPointF(item._pts[0])
            item.set_points(s, s)
        self._place = item
        self._place_tool = tool
        self._snap_preview = None
        self.scene().clearSelection()
        self.viewport().update()

    def _update_place(self, event):
        """배치 중 아이템의 '현재 점'을 커서로 갱신(드래그 move와 동일 기하 로직 재사용)."""
        item, tool = self._place, self._place_tool
        if tool == "arrow":
            self._update_arrow_draw(event, item)   # 테두리 스냅 + 자동 S자 + 바인딩
            return
        if tool == "sarrow":
            p = self._poly_place_point(event, item)   # 클릭과 동일 계산(미리보기 일치)
            item._set_endpoint(len(item._pts) - 1, item.mapFromScene(p))
            self.viewport().update()   # 스냅 마커 갱신
            return
        sp = self._cur_point(event)
        if tool in ("rect", "ellipse") or tool.startswith("sym:"):
            item.setRect(QRectF(self._start, sp).normalized())
        elif tool == "line":
            item.setLine(QLineF(self._start, sp))
        self.viewport().update()

    def _place_click(self, event):
        """좌클릭: sarrow=정점 추가(계속) / 2점 도구=둘째 클릭 확정."""
        if self._place_tool == "sarrow":
            it = self._place
            p = self._poly_place_point(event, it)   # 미리보기(_update_place)와 동일 계산 + _arrow_tip_snap 갱신
            local = QPointF(it.mapFromScene(p))
            it.prepareGeometryChange()
            it._pts[-1] = QPointF(local)      # 미리보기 → 확정
            it._pts.append(QPointF(local))    # 새 미리보기(커서 추종) — _finish_place가 pop
            it.update()
            # [우리 확장] 클릭점이 도형 테두리에 스냅됐으면 그 점이 종점 — 더블클릭 없이 자동 마무리.
            # (시작점은 _enter_click_place로 배치되므로 이 경로를 안 타 조기 종료되지 않는다.)
            if self._arrow_tip_snap is not None:
                self._finish_place()
                return
            self.viewport().update()
        else:
            self._finish_place(event)

    def _place_nondegenerate(self, it, tool) -> bool:
        """2점 도구가 '점 하나'로 퇴화하지 않았는지(너무 작지 않은지)."""
        if tool in ("rect", "ellipse") or tool.startswith("sym:"):
            r = it.rect()
            return abs(r.width()) >= 2 or abs(r.height()) >= 2
        if tool == "line":
            ln = it.line()
            return math.hypot(ln.dx(), ln.dy()) >= 2
        if tool == "arrow":
            return math.hypot(it._p2.x() - it._p1.x(), it._p2.y() - it._p1.y()) >= 2
        return True

    def _finish_place(self, event=None):
        """더블클릭/Enter/우클릭/2점 둘째 클릭 — 확정(undo+선택), 유효하지 않으면 폐기."""
        it, tool = self._place, self._place_tool
        if it is None:
            self._place = self._place_tool = None
            return
        if tool == "sarrow":
            it.prepareGeometryChange()
            if it._pts:
                it._pts.pop()             # 커서 추종 미리보기 정점 제거
            valid = len(it._pts) >= 2
        else:
            if event is not None:
                self._update_place(event)  # 마지막 클릭 위치로 2nd point 확정
            valid = self._place_nondegenerate(it, tool)
        self._place = None
        self._place_tool = None
        self._arrow_snap_exit = None
        self._arrow_tip_snap = None
        if valid:
            if isinstance(it, _PolyArrowItem):
                self._bind_poly_ends(it)   # [A3] 끝점이 도형 테두리 근처면 스냅+바인딩
            self._apply_arrow_kind_on_create(it)   # [화살표 통합] sticky 종류(직선이면 곧게)
            it.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            self._owner.push_undo_add(it)
            self.scene().clearSelection()
            it.setSelected(True)
            if hasattr(it, "_sync_label"):
                it._sync_label()
            it.update()
        elif it.scene() is not None:
            self.scene().removeItem(it)   # 퇴화/정점 부족 → 폐기
        self.viewport().update()

    def _apply_arrow_kind_on_create(self, item):
        """[화살표 통합] 방금 그린 화살표에 현재 sticky 종류를 반영한다. 곡선 화살표(_ArrowItem)는
        도형에 스냅되면 자동 S자로 그려지는데, 종류가 '직선'이면 그 곡률을 곧게 편다(직각은 애초에
        sarrow 도구라 여기 안 옴). 종류가 '곡선'이면 그린 그대로(자동 S 또는 자유 직선) 둔다."""
        if isinstance(item, _ArrowItem) and \
                getattr(self._owner, "current_arrow_kind", "curved") == "straight":
            item.apply_straight()

    def _cancel_place(self):
        """Esc/도구 전환 — 진행 중 배치를 통째로 폐기(있을 때만)."""
        it = self._place
        self._place = None
        self._place_tool = None
        self._arrow_snap_exit = None
        self._arrow_tip_snap = None
        self._hp_hover = None   # 도구 전환 시 접속점 고스트도 지움
        self._port_dot_shape = None
        if it is not None and it.scene() is not None:
            self.scene().removeItem(it)
            self.viewport().update()

    def _cancel_drag_draw(self):
        """[Phase 6 M2] 진행 중이던 드래그 그리기를 통째로 폐기(우클릭 취소용)."""
        it = self._temp
        self._drawing = False
        self._temp = None
        self._path = None
        if it is not None and it.scene() is not None:
            self.scene().removeItem(it)
        self.viewport().update()

    def _right_click_cancel(self):
        """[Phase 6 M2] 우클릭 — 진행 중 그리기를 폐기하고 무장 도구를 선택모드로 되돌린다.
        아무것도 진행 중이 아니고 이미 select면 아무 일도 하지 않는다(무해)."""
        if self._place is not None:
            self._cancel_place()
        elif self._drawing:
            self._cancel_drag_draw()
        if self._owner.current_tool not in (None, "select"):
            self._owner.set_tool("select")

    def _rmb_is_busy(self) -> bool:
        """[M3 #16] 우클릭이 '취소'여야 하는 상태인가 — 진행 중 배치/그리기 또는 무장된 그리기 도구.
        M2가 실제로 취소하던 경우와 정확히 일치(그 외 유휴는 팬/메뉴로 넘긴다)."""
        if self._place is not None or self._drawing:
            return True
        return self._owner.current_tool not in (None, "select")

    def _bind_poly_ends(self, it):
        """[A3] 직선화살표 확정 시 — 시작·끝 정점이 도형 테두리 근처면 그 지점으로 스냅하고
        지속 연결 바인딩(도형 이동 시 추종). o-snap(F3) 꺼짐이면 _border_snap_at이 None → 무바인딩."""
        for idx in (0, len(it._pts) - 1):
            vscene = it.mapToScene(it._pts[idx])
            snap = self._border_snap_at(self.mapFromScene(vscene), exclude=it)
            if snap is not None:
                it._set_endpoint(idx, it.mapFromScene(snap[0]))   # [M4-2b] 기하 스냅(선/화살표 끝점 포함)
                if snap[2] is not None:
                    it.set_bound(idx, snap[2], snap[2].mapFromScene(snap[0]))   # 도형만 지속 바인딩
        # [M4-4] 드래그로 그린(2정점) 직선화살은 라우팅 스타일대로 확정 — ortho(기본)면 직교 경로 생성
        # (양끝 바인딩=A* 회피 자동라우팅, 자유=단순 엘보), straight면 2점 직선 유지. 멀티정점 클릭배치
        # (3정점↑)는 사용자가 손으로 놓은 경로이므로 건드리지 않는다(수동 폴리라인 보존).
        if len(it._pts) == 2 and it._is_ortho():
            if it.has_binding():   # [⑦] 한쪽만 붙어도 자동라우팅 켜기 → 도형 이동 시 직교 유지
                it._auto_route = True
            it._apply_routing()

    def _editing_text_hover(self, view_pos) -> str | None:
        """편집 중인 텍스트 위 hover면 'text'(내부=캐럿) / 'move'(테두리 band=이동), 아니면 None.
        테두리 band는 화면 8px 두께로 잡아 뷰·아이템 스케일과 무관하게 일정하게 보이게 한다."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.items(view_pos):
            if isinstance(it, _TextItem) and \
                    it.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction:
                cr = it._content_rect()
                band = 8.0 / (self._view_scale() * it._scale_or_1())  # 화면 8px → 로컬 두께
                inner = cr.adjusted(band, band, -band, -band)
                if inner.width() <= 0 or inner.height() <= 0:
                    return "text"  # 너무 작으면 전부 캐럿(편집 중이므로 I빔 우선)
                return "text" if inner.contains(it.mapFromScene(scene_pt)) else "move"
        return None

    def mirror_selection(self, axis: str):
        """[Stage2] 선택(1개↑)을 공통 bbox 중심 기준 반사. axis='x'=좌우, 'y'=상하.
        도형·선·화살표는 기하 반전(화살촉 방향은 기하에서 자동 보정), 텍스트·번호는 위치만
        반사(글자 가독 유지). 도형에 붙은 화살표 부착점도 함께 반사돼 연결 유지."""
        sel = [it for it in self.scene().selectedItems()
               if it.parentItem() is None and isinstance(it, _HandleResizeMixin)]
        if not sel:
            return
        r = None
        for it in sel:
            br = it.mapToScene(it._content_rect()).boundingRect()
            r = br if r is None else r.united(br)
        if r is None:
            return
        c = r.center().x() if axis == "x" else r.center().y()
        fn = _mirror_fn(axis, c)
        shapes = [it for it in sel if not isinstance(it, (_ArrowItem, _PolyArrowItem))]
        bound = _collect_bound_arrows(self.scene(), shapes)
        snaps = [(it, it.capture_geom()) for it in _snapshot_set(sel, bound)]
        _rebake_selection(sel, bound, fn)
        self._owner.push_undo_geom(snaps)
        self.viewport().update()

    # ---- [Stage2b] AutoCAD 정통 stretch — crossing 박스에 걸친 정점만 이동 ----------
    # 명시적 모드(암묵 트리거 금지 — 과거 '이동 폴백' 혼동으로 롤백된 전례): crossing(또는
    # window) 러버밴드 선택으로 박스를 '기억'(_last_sel_rect) → S로 무장(_stretch_arm) →
    # 기준점 클릭(_stretch_begin) → 이동(프리뷰) → 도착 클릭(_stretch_commit). Esc=취소.
    # 이동은 '전체 아이템 fn' 리베이크가 아니라 '박스 안 grip만 +delta'인 공간 fn을 기존
    # _rebake_selection에 흘려보내 재사용한다: 점 기반(선·화살표·폴리)=정점별 이동, 네모·원=
    # 걸친 모서리 AABB, 바인딩 부착점=박스 안이면 fn으로 따라옴 → "걸친 쪽만 따라온다".
    # 완전포함 도형은 모든 grip이 박스 안 → 전부 +delta → 강체 이동. 판정은 항상 '원본 위치'
    # 기준(매 프레임 스냅샷 원복 후 fn 적용)이라 박스가 고정된다.
    @staticmethod
    def _stretch_inside_fn(box: QRectF, delta: QPointF):
        def fn(p):
            return (QPointF(p.x() + delta.x(), p.y() + delta.y())
                    if box.contains(p) else QPointF(p))
        return fn

    def _stretch_arm_now(self):
        """S키 — 러버밴드 박스가 기억돼 있고 선택이 있으면 stretch 무장."""
        if self._stretch_active or self._stretch_arm:
            return
        sel = [it for it in self.scene().selectedItems()
               if it.parentItem() is None and isinstance(it, _HandleResizeMixin)]
        box = self._last_sel_rect
        if not sel or box is None or box.width() < 1e-6 or box.height() < 1e-6:
            return
        self._stretch_box = QRectF(box)
        self._stretch_items = sel
        self._stretch_grip_pts = [g for it in sel for g in it._stretch_grips()
                                  if self._stretch_box.contains(g)]
        self._stretch_arm = True
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.viewport().update()

    def _stretch_begin(self, base_scene: QPointF):
        """무장 상태에서 기준점 클릭 — 기하 스냅샷 + 트랜잭션 시작."""
        items = self._stretch_items
        shapes = [it for it in items if not isinstance(it, (_ArrowItem, _PolyArrowItem))]
        self._stretch_binds = _collect_bound_arrows(self.scene(), shapes)
        self._stretch_snap = [(it, it.capture_geom())
                              for it in _snapshot_set(items, self._stretch_binds)]
        self._stretch_base = QPointF(base_scene)
        self._stretch_cursor = QPointF(base_scene)
        self._stretch_arm = False
        self._stretch_active = True

    def _stretch_apply(self, cur_scene: QPointF):
        """프리뷰/확정 공통 — 매 프레임 원복 후 공간 fn으로 리베이크. F8이면 기준점서 0/90°."""
        if not self._stretch_active:
            return
        base = self._stretch_base
        if getattr(self._owner, "ortho_enabled", False):
            cur_scene = self._constrain(base, cur_scene, "ortho")
        delta = QPointF(cur_scene.x() - base.x(), cur_scene.y() - base.y())
        for it, tok in self._stretch_snap:   # 원복(누적 방지)
            it.apply_geom(tok)
        fn = self._stretch_inside_fn(self._stretch_box, delta)
        _rebake_selection(self._stretch_items, self._stretch_binds, fn)
        self._stretch_cursor = QPointF(cur_scene)
        self.viewport().update()

    def _stretch_commit(self):
        if self._stretch_snap:
            self._owner.push_undo_geom(self._stretch_snap)
        self._stretch_clear()

    def _stretch_cancel(self):
        if self._stretch_active and self._stretch_snap:
            for it, tok in self._stretch_snap:
                it.apply_geom(tok)   # 원본으로 되돌림(커밋 안 함)
        self._stretch_clear()

    def _stretch_clear(self):
        was = self._stretch_arm or self._stretch_active
        self._stretch_arm = self._stretch_active = False
        self._stretch_box = self._stretch_base = self._stretch_cursor = None
        self._stretch_items = self._stretch_binds = self._stretch_snap = None
        self._stretch_grip_pts = []
        if was:
            self.viewport().unsetCursor()
            self.viewport().update()

    def _paint_stretch(self, painter, s):
        """[Stage2b] stretch 오버레이 — crossing 박스 + 걸친 정점(●) 또는 기준점→커서 프리뷰선."""
        if self._stretch_box is not None:
            pen = QPen(QColor(90, 190, 90), 1.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._stretch_box)
        r = 4.0 / s
        if self._stretch_arm:   # 무장 — 걸친 정점을 빨간 도트로(무엇이 움직일지 예고)
            painter.setPen(QPen(QColor("white"), 1.0 / s))
            painter.setBrush(QBrush(QColor(230, 60, 60)))
            for g in self._stretch_grip_pts:
                painter.drawEllipse(g, r, r)
        if self._stretch_active and self._stretch_base is not None \
                and self._stretch_cursor is not None:
            pen = QPen(QColor(90, 190, 90), 1.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(self._stretch_base, self._stretch_cursor)
            painter.setPen(QPen(QColor("white"), 1.0 / s))
            painter.setBrush(QBrush(QColor(90, 190, 90)))
            painter.drawEllipse(self._stretch_base, r, r)   # 기준점

    def _update_hover_cursor(self, view_pos):
        """편집 모드 hover 커서: 주석 위=이동, 도형 도구+빈영역=십자, select+빈영역=손바닥.
        편집 중 텍스트는 예외 — 내부=캐럿(I빔), 테두리만 이동."""
        vp = self.viewport()
        tool = self._owner.current_tool
        edit_text = self._editing_text_hover(view_pos)
        # [우리 확장] 그룹 변형 핸들 hover — 회전(코랄 커서)·스케일(대각 리사이즈).
        if self._group.available():
            g = self._group.handle_at(self.mapToScene(view_pos))
            if g is not None:
                if g[0] == "rotate":
                    vp.setCursor(_rotate_cursor())
                elif g[0] == "scale_axis":                       # [Stage2] 1축 비균일
                    vp.setCursor(Qt.CursorShape.SizeHorCursor if g[1] == "x"
                                 else Qt.CursorShape.SizeVerCursor)
                else:
                    vp.setCursor(Qt.CursorShape.SizeFDiagCursor)
                return
        if self._qc_dot_at(view_pos) is not None:            # 선택된 도형의 접속점(어느 도구에서든)
            vp.setCursor(Qt.CursorShape.CrossCursor)         # [실사용 피드백 2026-07-30] 이동 커서와
            return                                            # 구분되게 커넥터 의도를 십자선으로 표시
        box_h = self._box_handle_at(view_pos)
        if box_h is not None:                                # [2c] 네모·원 박스 핸들
            vp.setCursor(_rotate_cursor() if box_h == "rotate" else box_h)
            return
        if self._table_col_add is not None:   # [열폭 드래그] 표 내부 경계선 위 — 좌우 리사이즈 커서
            vp.setCursor(Qt.CursorShape.SplitHCursor)
            return
        if tool == "select":
            hp = self._hover_port_at(view_pos)
            if hp is not None:
                # [실사용 피드백 2026-07-30] 미선택 도형의 포트 위 — 예전엔 아래 '주석 위=이동'
                # 분기로 떨어져 SizeAllCursor(이동 커서)로 보였다. 여기서 드래그는 이동이 아니라
                # 커넥터 생성(_hp_create_arrow)이므로 십자선으로 구분한다.
                # [2026-08-04 연속 호버 §8 항목16] Pass 2(테두리 임의 위치 연속 폴백)는 테두리
                # 두께 중심으로 안쪽/바깥쪽을 갈라, 안쪽이면 이 분기를 건너뛰어 아래 '주석 위=이동'
                # 분기(SizeAllCursor)로 자연히 떨어지게 한다. `sh.contains()`(Qt shape())는 잡기
                # 쉽도록 부풀린 히트 영역이라 못 쓰고(실측 확인), 실제 기하 외곽선 기준인
                # `_shape_interior_contains`를 쓴다.
                # [실사용 지적 2026-08-09] Pass 1(이산 4점)은 예전엔 무조건 CrossCursor였다 — 큰
                # 도형은 이산 포트가 테두리 위라 사실상 "테두리 근처=Cross, 몸통 깊숙=Move"와
                # 결과가 같아 티가 안 났지만, 포트처럼 몸통 자체가 스냅 반경(`_PORT_SNAP_PX`)보다
                # 작은 도형은 몸통 전체가 "이산 포트 근처"가 되어 계속 CrossCursor로 뒤덮였다.
                # `_shape_interior_contains`로 똑같이 안/밖만 가르면(한 차례 시도 후 되돌림)
                # 그 함수의 기본(rect) 분기가 경계 포함(inclusive)이라 이산 포트 정확히 그 자리
                # (원래 늘 Cross여야 할 자리)까지 Move로 뒤집혀 모든 도형의 접속점에서 커넥터
                # 신호 자체가 사라지는 더 큰 회귀였다(실측 확인). 그래서 "스냅에 잡히는 범위"
                # (`_PORT_SNAP_PX`, 넉넉해야 정확히 조준 안 해도 잡힘)와 "커서를 Cross로 보일
                # 범위"(`_PORT_CURSOR_PX`, 훨씬 좁음)를 분리한다 — 접속점 바로 근처(좁은 반경)는
                # 여전히 Cross, 그보다 안쪽으로 들어가면(포트처럼 작은 도형에서만 의미 있는 차이)
                # 일반 도형과 같은 Move로 자연히 떨어진다.
                sh, sp, _n, is_discrete = hp
                near_point = is_discrete and self._view_dist(sp, view_pos) <= self._PORT_CURSOR_PX
                if near_point or not _shape_interior_contains(sh, self.mapToScene(view_pos)):
                    vp.setCursor(Qt.CursorShape.CrossCursor)
                    return
        if self._bend_handle_at(view_pos) is not None:
            vp.setCursor(Qt.CursorShape.PointingHandCursor)  # 곡선 조절 손잡이(이동과 구분)
        elif self._over_selected_endpoint(view_pos):
            vp.setCursor(Qt.CursorShape.PointingHandCursor)  # 끝점 핸들(이동/재스냅) — 곡선 핸들과 동일
        elif self._seg_add is not None:
            # [M4-4] 세그먼트 hover — 변 방향에 수직인 이동 커서(수평 변=상하, 수직 변=좌우).
            item, seg_idx = self._seg_add[0], self._seg_add[1]
            horiz = item._segment_orientation(seg_idx)
            vp.setCursor(Qt.CursorShape.SizeVerCursor if horiz else Qt.CursorShape.SizeHorCursor)
        elif self._rot_handle_at(view_pos):
            vp.setCursor(_rotate_cursor())                   # 회전 점 — 곡선 화살표 커서
        elif self._scale_handle_at(view_pos):
            vp.setCursor(Qt.CursorShape.SizeFDiagCursor)     # 크기조절 점(우하단) — 대각 리사이즈(↖↘)
        elif edit_text == "text":
            vp.setCursor(Qt.CursorShape.IBeamCursor)         # 편집 중 텍스트 내부 — 캐럿
        elif edit_text == "move":
            vp.setCursor(Qt.CursorShape.SizeAllCursor)       # 편집 중 텍스트 테두리 — 이동
        elif tool in ("arrow", "sarrow") and self._snap_preview is not None:
            vp.setCursor(Qt.CursorShape.CrossCursor)          # 테두리 스냅 — 화살표 시작(도형 위여도)
        elif tool == "pen":
            vp.setCursor(Qt.CursorShape.CrossCursor)         # 펜 — 주석 위에서도 항상 그리기
        elif not self._is_empty_area(view_pos):
            vp.setCursor(Qt.CursorShape.SizeAllCursor)       # 주석 위 — 선택/이동
        elif self._group_body_area_at(view_pos):
            vp.setCursor(Qt.CursorShape.SizeAllCursor)       # [편의기능] 그룹 바운딩박스 빈틈 — 이동
        elif tool is None:
            vp.setCursor(Qt.CursorShape.OpenHandCursor)      # 손 모드 빈 영역 — 창 이동
        elif tool == "select":
            vp.setCursor(Qt.CursorShape.ArrowCursor)         # 빈 영역 — 러버밴드 선택
        elif tool == "text":
            vp.setCursor(Qt.CursorShape.IBeamCursor)         # 텍스트 — 캐럿 위치 표시
        else:
            vp.setCursor(Qt.CursorShape.CrossCursor)         # 도형 그리기

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.MiddleButton:
            self._owner._win_drag_move(event.globalPosition().toPoint())
            return
        # [Phase 6 M3 #16] 유휴 우클릭 드래그 — 임계 넘으면 팬 시작/지속(가운데버튼 팬과 동일 메커니즘).
        if (event.buttons() & Qt.MouseButton.RightButton) and self._rmb_press is not None:
            if self._rmb_panning:
                self._owner._win_drag_move(event.globalPosition().toPoint())
            elif (event.position().toPoint() - self._rmb_press).manhattanLength() >= 6:
                self._rmb_panning = True
                self._owner._win_drag_start(event.globalPosition().toPoint())
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self._none_win_dragging:  # 손 모드 빈영역 좌드래그 = 창 이동
            self._owner._win_drag_move(event.globalPosition().toPoint())
            return
        if self._seg_drag is not None:  # [M4-4] 세그먼트 드래그 — 변을 커서 위치로 수직 이동
            self._seg_drag._drag_segment_to(self.mapToScene(event.position().toPoint()))
            self.viewport().update()
            return
        if self._table_col_drag is not None:  # [열폭 드래그] 경계를 커서 x로 이동
            item = self._table_col_drag
            local = item.mapFromScene(self.mapToScene(event.position().toPoint()))
            item._drag_col_boundary_to(local.x())
            self.viewport().update()
            return
        if self._rb_active:  # [우리 확장] 방향 감지 러버밴드 — 드래그 중엔 저비용 미리보기만
            # [성능 조사 2026-07-30] 매 프레임 실제 setSelected() 캐스케이드(_apply_rubber_selection)
            # 대신 _rb_preview_hits()의 저비용 근사만 — 실제 선택은 release에서 1회 확정.
            self._rb_current = event.position().toPoint()
            self._rb_preview = self._rb_preview_hits()
            self.viewport().update()
            return
        if self._group_dragging:  # [우리 확장] 그룹 변형 드래그 — 회전·스케일 실시간 적용
            self._group.update_to(self.mapToScene(event.position().toPoint()),
                                  bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            self.viewport().update()
            return
        if self._group_body_drag:  # [편의기능] 그룹 바운딩박스 빈틈 드래그 — 선택 전체를 델타만큼 이동
            scene_pt = self.mapToScene(event.position().toPoint())
            delta = scene_pt - self._group_body_anchor
            self._group_body_anchor = scene_pt
            if delta.x() or delta.y():
                for it in self.scene().selectedItems():
                    if it.parentItem() is None and (
                            it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable):
                        it.moveBy(delta.x(), delta.y())
            self.viewport().update()
            return
        if self._hp_dragging:  # [하나의 시스템으로 통합] 임계 넘게 끌면 커넥터 프리뷰, 아니면 보류(release=클릭)
            cur = self.mapToScene(event.position().toPoint())
            # [2026-08-04 실사용 지적] 출구 법선 축(수평/수직)에서 조금만 벗어나도 직교 라우터가
            # 꺾임(짧은 지그재그)을 넣어 똑바로 그리려 해도 한 번에 안 됐다 — 시작점에서 그 축
            # 방향으로 충분히 가까우면(스냅 반경 안) 그 축 위로 당겨 한 번에 일직선이 되게 한다.
            if self._hp_port is not None and self._hp_normal is not None:
                snap_px = 10.0 / self._view_scale()
                n = self._hp_normal
                if abs(n.x()) >= abs(n.y()):   # 수평 출구 — 커서 y를 시작점 y에 맞춘다
                    if abs(cur.y() - self._hp_port.y()) <= snap_px:
                        cur = QPointF(cur.x(), self._hp_port.y())
                else:                          # 수직 출구 — 커서 x를 시작점 x에 맞춘다
                    if abs(cur.x() - self._hp_port.x()) <= snap_px:
                        cur = QPointF(self._hp_port.x(), cur.y())
            thr = 8.0 / self._view_scale()
            self._hp_cursor = cur if (self._hp_press_scene is not None
                                      and QLineF(self._hp_press_scene, cur).length() > thr) else None
            self.viewport().update()
            return
        if self._stretch_active:  # [Stage2b] stretch 프리뷰 — 버튼 없이 이동해도 갱신(클릭-이동-클릭)
            self._stretch_apply(self.mapToScene(event.position().toPoint()))
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            return
        if self._stretch_arm:     # [Stage2b] 무장 — 기준점 클릭 대기(십자 커서 유지)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            return
        if not self._owner.is_edit_mode():
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._owner._win_drag_move(event.globalPosition().toPoint())
            else:
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        # [우리 확장] 클릭 배치 진행 중 — 버튼 없이 이동해도 마지막 점을 커서로 미리보기.
        if self._place is not None:
            if self._owner.current_tool != self._place_tool:
                self._cancel_place()   # 도구가 바뀌었으면 진행 중 배치 폐기 후 정상 처리로
            else:
                self._update_place(event)
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
                return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self._update_snap_preview(event.position().toPoint())
            prev = self._seg_add
            self._seg_add = self._segment_add_at(event.position().toPoint())
            if (prev is None) != (self._seg_add is None) or (
                    prev is not None and self._seg_add is not None
                    and prev[2] != self._seg_add[2]):
                self.viewport().update()   # waypoint 예고 마커 갱신
            # [열폭 드래그] 표 내부 경계선 hover 갱신.
            prev_col = self._table_col_add
            self._table_col_add = self._table_col_boundary_at(event.position().toPoint())
            if (prev_col is None) != (self._table_col_add is None):
                self.viewport().update()
            # [호버 강조 2026-07-30] 선택 핸들 위 hover — 그 점만 색 반전 강조.
            prev_hh = self._handle_hover
            self._handle_hover = self._handle_hover_at(event.position().toPoint())
            if prev_hh != self._handle_hover:
                if prev_hh is not None and prev_hh[0].scene() is not None:
                    prev_hh[0]._hover_handle = None
                    prev_hh[0].update()
                if self._handle_hover is not None:
                    self._handle_hover[0]._hover_handle = self._handle_hover[1]
                    self._handle_hover[0].update()
            # [하나의 시스템으로 통합 2026-08-01] 접속점 유휴 hover — 선택된 도형은 어느
            # 도구에서든, 미선택 도형은 select 도구에서만(그리기 방해 방지) 검사해 하나의
            # _hp_hover로 합친다(고스트 미리보기·스냅 마커 모두 이걸 본다).
            prev_hp = self._hp_hover
            hp = self._connect_port_at(event.position().toPoint())
            if hp is None and self._owner.current_tool == "select":
                hp = self._hover_port_at(event.position().toPoint())
            self._hp_hover = hp
            if prev_hp != self._hp_hover:
                self.viewport().update()
            # [2026-08-03] 포트 예고점(넓은 margin 판정)은 _hp_hover(좁은 스냅 반경)와 갱신
            # 시점이 달라 위 update()만으로는 늦게 뜨거나 잔상이 남았다 — 별도로 변화 감지.
            prev_pd = self._port_dot_shape
            self._port_dot_shape = self._port_dot_target(self.mapToScene(event.position().toPoint()))
            if prev_pd is not self._port_dot_shape:
                self.viewport().update()
            self._update_hover_cursor(event.position().toPoint())
        if self._drawing and self._temp is not None:
            tool = self._owner.current_tool
            if tool == "arrow":
                self._update_arrow_draw(event)   # 테두리 스냅 + 자동 S자
                return
            sp = self._cur_point(event)
            if tool in ("rect", "ellipse") or tool.startswith("sym:"):
                self._temp.setRect(QRectF(self._start, sp).normalized())
            elif tool == "line":
                self._temp.setLine(QLineF(self._start, sp))
            elif tool == "sarrow":
                if getattr(self._owner, "ortho_enabled", False):
                    # F8: sp가 이미 ortho 처리됨 + 테두리 근처면 그 위로 스냅(축 보존)
                    tip = self._snap_ortho_to_border(sp, self._start)
                else:
                    snapped = self._poly_border_snap_tip(event, self._start)   # [A3] 라이브 테두리 스냅
                    tip = snapped if snapped is not None else sp
                # [화살표 그리기 라이브 직각] 드래그 내내 릴리스와 동일한 직각 회피 경로로 미리보기
                # (관통→릴리스 튐 제거). tip이 도형에 스냅됐으면 그 도형을 라이브 바인딩해 conn 처리.
                self._temp.set_ortho_preview(self._start, tip,
                                             getattr(self, "_arrow_tip_snap_shape", None))
                self.viewport().update()   # 스냅 마커 갱신
            elif tool == "pen" and self._path is not None:
                self._path.lineTo(sp)
                self._temp.setPath(self._path)
            return
        # [2e] 도형 이동 드래그 — Qt로 옮긴 뒤 스마트 정렬 스냅 + 가이드선.
        if self._move_active and (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            self._apply_axis_lock(event)   # [편의기능] Shift+드래그 축 고정 — 스냅보다 먼저(더 강한 제약)
            if self._axis_lock is None:
                self._apply_smart_snap()
                # [그리드 스냅] 스마트정렬이 이미 맞춘 축(가이드선 존재)은 건드리지 않고 나머지만.
                skip_x = any(g[0] == "v" for g in self._align_guides)
                skip_y = any(g[0] == "h" for g in self._align_guides)
            else:
                self._align_guides = []    # 축 고정 중엔 정렬 가이드선도 끔(서로 다른 제약 혼선 방지)
                # 축고정이 고정한 축은 old 값 그대로 유지돼야 하므로 격자스냅에서도 제외.
                skip_x = self._axis_lock == "v"
                skip_y = self._axis_lock == "h"
            self._apply_grid_snap_move(skip_x, skip_y)
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._owner._win_drag_end()
            self.viewport().unsetCursor()
            return
        # [Phase 6 M3 #16] 유휴 우클릭 종료 — 끌었으면 팬 종료, 제자리 탭이면 컨텍스트 메뉴.
        if event.button() == Qt.MouseButton.RightButton and self._rmb_press is not None:
            panned = self._rmb_panning
            self._rmb_press = None
            self._rmb_panning = False
            if panned:
                self._owner._win_drag_end()
                self.viewport().unsetCursor()
            elif hasattr(self._owner, "_show_context_menu"):
                self._owner._show_context_menu(event.globalPosition().toPoint())
            return
        if self._none_win_dragging:  # 손 모드 창 이동 종료
            self._owner._win_drag_end()
            self._none_win_dragging = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self._seg_drag is not None:  # [M4-4] 세그먼트 드래그 종료 — 정점 정리 + undo 커밋
            item = self._seg_drag
            self._seg_drag = None
            item._end_segment_drag()
            if self._seg_undo:
                self._owner.push_undo_geom(self._seg_undo)
            self._seg_undo = None
            self.viewport().update()
            return
        if self._table_col_drag is not None:  # [열폭 드래그] 종료 — undo 커밋
            item = self._table_col_drag
            self._table_col_drag = None
            item._end_col_drag()
            if self._table_col_undo:
                self._owner.push_undo_geom(self._table_col_undo)
            self._table_col_undo = None
            self.viewport().update()
            return
        if self._rb_active:  # [우리 확장] 러버밴드 종료 — 드래그 중엔 미리보기만이라 여기서
            # 정확한 최종 선택을 1회 확정한다(_apply_rubber_selection, 기존 정밀 로직 그대로).
            self._rb_current = event.position().toPoint()
            self._apply_rubber_selection()
            self._last_sel_rect = self._rb_scene_rect()   # [Stage2b] 박스 '기억'(S stretch용)
            self._rb_active = False
            self._rb_origin = self._rb_current = None
            self._rb_base = []
            self._rb_preview = set()
            self.viewport().update()
            return
        if self._group_dragging:  # [우리 확장] 그룹 변형 종료 — undo에 변형 트랜잭션 커밋
            self._group.end()
            self._group_dragging = False
            self.viewport().update()
            return
        if self._group_body_drag:  # [편의기능] 그룹 바운딩박스 빈틈 드래그 종료 — 이동 undo 커밋
            self._group_body_drag = False
            self._commit_move()
            self.viewport().update()
            return
        if self._hp_dragging:  # [하나의 시스템으로 통합] 종료 — 드래그했으면 커넥터, 클릭이면 즉시 생성
            src, port, nrm, cur = self._hp_src, self._hp_port, self._hp_normal, self._hp_cursor
            is_discrete = self._hp_is_discrete
            self._hp_dragging = False
            self._hp_src = self._hp_port = self._hp_normal = self._hp_cursor = None
            self._hp_press_scene = None
            self._hp_is_discrete = True
            if src is not None and src.scene() is not None:
                if cur is not None:
                    self._hp_create_arrow(src, port, cur)
                elif is_discrete:
                    # [④ 즉시 생성 2026-08-01, Lucid 대조] 실제로 끌지 않았으면(클릭) 선택 여부와
                    # 무관하게 즉시 도형 복제+화살표를 만든다 — 종전엔 미선택 도형에서 그냥
                    # 선택만 하고 접속점이 뜬 뒤 한 번 더 눌러야 새 도형이 생겼다(사용자 피드백:
                    # "4분면 점에서 바로 생겨야 맞을듯"). 이산(4점)에서만 — 연속은 아래로.
                    side = _side_from_normal(nrm) if nrm is not None else "r"
                    self._qc_create(src, side, None)
                else:
                    # [실사용 버그 수정 2026-08-04, 2차] 연속 폴백(테두리 임의 위치)에서 끌지 않은
                    # 클릭은 커넥터·복제 둘 다 아니라 그냥 선택 — press에서 여기를 가로챘으므로
                    # Qt 기본 클릭-선택이 못 돌았다, 그 자리에서 우리가 대신 선택해 준다.
                    self.scene().clearSelection()
                    src.setSelected(True)
            self.viewport().update()
            return
        # [우리 확장] 클릭 배치 진행 중이면 릴리스는 무시 — 점은 클릭(press)으로만 놓는다.
        if self._place is not None:
            return
        if not self._owner.is_edit_mode():
            self._owner._win_drag_end()
            return
        if self._drawing and self._temp is not None:
            item = self._temp
            tool = self._owner.current_tool
            self._drawing = False
            self._temp = None
            self._path = None
            self.viewport().update()   # 스냅 마커 지우기
            # 시작점→놓은 점 이동량으로 '드래그'인지 '클릭'인지 판정(boundingRect는 펜 두께·
            # 화살촉만큼 부풀어 못 씀). 이동이 임계 미만이면 클릭 → 하이브리드 클릭 배치로 전환.
            release = self.mapToScene(event.position().toPoint())
            # 실제 press 지점 기준 이동량 — 시작 스냅 점프를 드래그로 오인하지 않게(버그 수정).
            moved = max(abs(release.x() - self._press_scene.x()),
                        abs(release.y() - self._press_scene.y()))
            if (tool in _SHAPE_TOOLS or tool.startswith("sym:")) and moved < 4:
                # 끌지 않은 클릭 → 폐기 대신 투클릭/멀티클릭 배치 모드로 진입(점은 유지).
                # 곡선·직선화살 모두 테두리에서도 클릭 배치 허용(하이브리드 일관).
                self._enter_click_place(item, tool)
                return
            # 드래그로 그린 경우 — 즉시 확정.
            self._arrow_snap_exit = None
            self._arrow_tip_snap = None
            if isinstance(item, _PolyArrowItem):
                # [화살표 그리기 라이브 직각] 드래그 미리보기로 늘어난 정점을 시작·끝 2점으로 되돌린다
                # — _bind_poly_ends는 len==2일 때만 자동라우팅(build_elbow)하고 3점↑는 수동 폴리라인
                #   으로 보존하기 때문. 되돌린 뒤 바인딩→A* 회피 경로로 정식 대체된다.
                if len(item._pts) > 2:
                    item.set_points(QPointF(item._pts[0]), QPointF(item._pts[-1]))
                self._bind_poly_ends(item)   # [A3] 끝점이 도형 테두리 근처면 스냅+바인딩
            self._apply_arrow_kind_on_create(item)   # [화살표 통합] sticky 종류(직선이면 곧게)
            item.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            self._owner.push_undo_add(item)
            # 방금 그린 주석을 바로 선택 — 추가 클릭 없이 이동/색·두께 수정 가능.
            # 단 펜은 연속 그리기라 선택 네모가 거슬리므로 선택하지 않는다.
            self.scene().clearSelection()
            if tool != "pen":
                item.setSelected(True)
            return
        self._commit_move()   # 드래그 이동이 있었으면 undo에 기록
        if self._move_active or self._align_guides:   # [2e] 스마트 정렬 상태 정리
            self._move_active = False
            self._align_guides = []
            self.viewport().update()
        super().mouseReleaseEvent(event)

    def _labelable_at(self, view_pos):
        """[우리 확장] 커서 아래 '맨 위 선택가능 아이템'이 선/화살표면 그 아이템, 아니면 None.
        위에 텍스트·도형이 있으면 None(그쪽 기본 동작을 살린다 — 라벨 더블클릭=그 라벨 편집)."""
        for it in self.items(view_pos):
            if it is getattr(self._owner, "_bg_item", None):
                continue
            if isinstance(it, (_LineItem, _ArrowItem, _PolyArrowItem,
                               _SymbolItem, _RectItem, _EllipseItem)):
                return it
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return None
        return None

    def _titleblock_at(self, view_pos):
        """[우리 확장 · Phase 4] 커서 아래 '맨 위 선택형'이 표제란 프레임이면 그것, 아니면 None.
        프레임(z 최하단) 위에 도형이 얹혀 있으면 그 도형의 기본 동작(라벨 편집)을 살린다."""
        for it in self.items(view_pos):   # 위→아래 stacking 순
            if it is getattr(self._owner, "_bg_item", None):
                continue
            if isinstance(it, _TitleBlockItem):
                return it
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return None
        return None

    def _table_cell_at(self, view_pos):
        """[우리 확장 · Phase 4] view_pos 아래의 표 셀 (item, r, c) — 표가 없거나 격자 밖이면 None.
        표 위에 다른 선택형 아이템이 얹혀 있으면(위 stacking) 그쪽 우선이라 None."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.items(view_pos):
            if isinstance(it, _TableItem):
                rc = it.cell_at(it.mapFromScene(scene_pt))
                return (it, rc[0], rc[1]) if rc is not None else None
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return None
        return None

    def _begin_cell_edit(self, item, r, c):
        """[우리 확장 · Phase 4] 표 셀 (r, c)에 인라인 편집기를 띄운다."""
        self._cell_editor = _CellEditor(self, item, r, c)

    def _begin_label_edit(self, item):
        """[우리 확장] 선/화살표의 라벨을 생성(없으면)하고 편집 모드로 진입."""
        new = not item._label_alive()
        lbl = item.ensure_label()
        if new:
            self._owner.push_undo_add(lbl)   # 라벨 생성 되돌리기(빈 채 나가면 자동 폐기됨)
        self.scene().clearSelection()
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        lbl.setFocus()
        cur = lbl.textCursor()               # 기존 텍스트 전체 선택(빠른 교체)
        cur.select(cur.SelectionType.Document)
        lbl.setTextCursor(cur)

    def mouseDoubleClickEvent(self, event):
        # 뷰어 모드: 더블클릭 = 닫기 (편집 모드는 텍스트 재편집 등 기본 동작 유지)
        if not self._owner.is_edit_mode():
            if event.button() == Qt.MouseButton.LeftButton:
                self._owner.close()
            return
        # [우리 확장] 클릭 배치 마무리(더블클릭). 이 더블클릭의 첫 press가 이미 점을
        # 놓았으므로(sarrow), 마무리 시 커서 추종 미리보기 점만 떼면 그 자리가 끝점이 된다.
        if self._place is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._finish_place(event)
                event.accept()
            return
        # [우리 확장 · Phase 4] 표제란 프레임 더블클릭 = 필드 편집 폼(host가 소유).
        if event.button() == Qt.MouseButton.LeftButton:
            tb = self._titleblock_at(event.position().toPoint())
            if tb is not None and hasattr(self._owner, "_edit_titleblock"):
                self._owner._edit_titleblock(tb)
                event.accept()
                return
        # [우리 확장 · Phase 4] 표 셀 더블클릭 = 인라인 편집(엑셀식).
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._table_cell_at(event.position().toPoint())
            if hit is not None:
                self._begin_cell_edit(*hit)
                event.accept()
                return
        # [우리 확장] 선/화살표 더블클릭 = 라벨 달기/편집(위에 다른 선택형이 없을 때만).
        if event.button() == Qt.MouseButton.LeftButton:
            target = self._labelable_at(event.position().toPoint())
            if target is not None:
                self._begin_label_edit(target)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    # ---- 키 (Space 토글 / 도구 단축키 / Delete / Ctrl+Z / Esc) -------------
    def keyPressEvent(self, event):
        fi = self.scene().focusItem()
        editing_text = (
            isinstance(fi, QGraphicsTextItem)
            and fi.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction
        )
        key = event.key()
        mods = event.modifiers()
        # [우리 확장] 클릭 배치 진행 중(텍스트 편집 아님): Enter=마무리 / Esc=취소. 최우선.
        if self._place is not None and not editing_text:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._finish_place()
                return
            if key == Qt.Key.Key_Escape:
                # [우리 확장] sarrow는 Esc=전체취소가 아니라 '지금까지 놓은 점으로 확정'(마지막 커서
                # 추종 미리보기만 버림). 확정할 정점이 부족하면(시작점만) _finish_place가 알아서 폐기.
                # 다른 도구(2점)는 종전대로 취소.
                if self._place_tool == "sarrow":
                    self._finish_place()
                else:
                    self._cancel_place()
                return
        if editing_text and key == Qt.Key.Key_Escape:
            # 텍스트 편집 중 ESC = 편집기 닫기가 아니라 텍스트 완료(=Ctrl+Enter와 동일).
            # clearFocus → focusOutEvent가 정리(빈 텍스트 폐기 / 비어있지 않으면 선택 해제).
            fi.clearFocus()
            return
        if not editing_text and key == Qt.Key.Key_Space:
            self._owner.toggle_edit_mode()
            return
        if not editing_text and key == Qt.Key.Key_Escape:
            if self._stretch_arm or self._stretch_active:   # [Stage2b] stretch 취소 최우선
                self._stretch_cancel()
                return
            # 선택된 주석이 있으면 ESC는 선택(파란 점선)만 해제 — 편집기는 안 닫는다.
            # 선택이 없을 때만 편집기 종료로 넘어간다(주석 → 뷰어 → 닫기 단계적 취소).
            if self.scene().selectedItems():
                self.scene().clearSelection()
                return
            self._owner._on_escape()
            return
        if self._owner.is_edit_mode() and not editing_text:
            # 화살표키 — 선택된 주석 이동. 기본은 넓게(10px), Shift/Ctrl로 세밀하게(1px). 도구와 무관.
            arrow = {
                Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1),
            }.get(key)
            if arrow is not None:
                sel = self.scene().selectedItems()
                if sel:
                    # 이동 전 위치 기록(Ctrl+Z 원복). 같은 선택의 연속 nudge는 하나로 합쳐
                    # undo 폭주를 막는다(coalesce_key=선택 집합).
                    self._owner.push_undo_move(
                        [(it, QPointF(it.pos())) for it in sel],
                        coalesce_key=frozenset(sel))
                    fine = mods & (Qt.KeyboardModifier.ShiftModifier
                                   | Qt.KeyboardModifier.ControlModifier)
                    step = 1 if fine else 10
                    for it in sel:
                        it.moveBy(arrow[0] * step, arrow[1] * step)
                    return
            if (mods & Qt.KeyboardModifier.ShiftModifier) and key == Qt.Key.Key_H:
                self.mirror_selection("x")   # [Stage2] 좌우 반전
                return
            if (mods & Qt.KeyboardModifier.ShiftModifier) and key == Qt.Key.Key_V:
                self.mirror_selection("y")   # [Stage2] 상하 반전
                return
            if (key == Qt.Key.Key_S and not (mods & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.ShiftModifier))
                    and self._owner.current_tool in ("select", None)):
                self._stretch_arm_now()   # [Stage2b] 러버밴드 선택 후 S = stretch 무장
                return
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_A:
                # [성능조사 2026-08-01] 개별 setSelected 루프는 O(n²) — owner._bulk_select로 일괄.
                self._owner._bulk_select([
                    it for it in self.scene().items()
                    if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable])
                return
            # [신규기능] Ctrl+Alt+C/V = 스타일 복사/붙여넣기 — 일반 Ctrl+C/V(아이템 복사)보다
            # 먼저 검사해야 한다(Alt를 함께 눌러도 아래 Ctrl+C 체크가 먼저 걸리면 항상 이김).
            if (mods & Qt.KeyboardModifier.ControlModifier) and (mods & Qt.KeyboardModifier.AltModifier) \
                    and key == Qt.Key.Key_C and hasattr(self._owner, "copy_style_from_selection"):
                self._owner.copy_style_from_selection()
                return
            if (mods & Qt.KeyboardModifier.ControlModifier) and (mods & Qt.KeyboardModifier.AltModifier) \
                    and key == Qt.Key.Key_V and hasattr(self._owner, "paste_style_to_selection"):
                self._owner.paste_style_to_selection()
                return
            if (mods & Qt.KeyboardModifier.ControlModifier) and not (mods & Qt.KeyboardModifier.AltModifier) \
                    and key == Qt.Key.Key_C:
                self._owner.copy_selection()
                return
            if (mods & Qt.KeyboardModifier.ControlModifier) and not (mods & Qt.KeyboardModifier.AltModifier) \
                    and key == Qt.Key.Key_V:
                self._owner.paste_selection()
                return
            # [M2 #3] Ctrl+D = 제자리 복제(오프셋). Easy CAD 호스트만 제공 → hasattr 가드.
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_D \
                    and hasattr(self._owner, "duplicate_selection"):
                self._owner.duplicate_selection()
                return
            # [편의기능] Ctrl+G=그룹, Ctrl+Shift+G=그룹 해제. Easy CAD 호스트만 제공 → hasattr 가드.
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_G \
                    and hasattr(self._owner, "group_selection"):
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    self._owner.ungroup_selection()
                else:
                    self._owner.group_selection()
                return
            # [편의기능] Ctrl+L = 선택 잠금 전환.
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_L \
                    and not (mods & Qt.KeyboardModifier.ShiftModifier) \
                    and hasattr(self._owner, "toggle_lock_selection"):
                self._owner.toggle_lock_selection()
                return
            # [편의기능] Ctrl+] = 맨 앞으로, Ctrl+[ = 맨 뒤로.
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_BracketRight \
                    and hasattr(self._owner, "bring_to_front"):
                self._owner.bring_to_front()
                return
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_BracketLeft \
                    and hasattr(self._owner, "send_to_back"):
                self._owner.send_to_back()
                return
            if key in self._SHORTCUTS and not (mods & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.ShiftModifier)):
                tool = self._SHORTCUTS[key]
                # [화살표 통합] 화살표 단축키(3·9)는 종류→도구 변환 진입점을 탄다(도구는 하나).
                if tool in ("arrow", "sarrow") and hasattr(self._owner, "arm_arrow_tool"):
                    self._owner.arm_arrow_tool()
                else:
                    self._owner.set_tool(tool)
                return
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                selected = list(self.scene().selectedItems())
                if selected:
                    for it in selected:
                        _detach_port_from_host(it)   # [신규기능 §8-12] 호스트의 _ports 목록도 정리
                        self.scene().removeItem(it)
                    self._owner.push_undo_delete(selected)
                    return
            if key == Qt.Key.Key_Z and (mods & Qt.KeyboardModifier.ControlModifier):
                # Ctrl+Shift+Z = 다시 실행(redo), Ctrl+Z = 되돌리기. redo는 Easy CAD 호스트만
                # 제공하므로 hasattr 가드(pasteflow 독립 owner엔 없음).
                if (mods & Qt.KeyboardModifier.ShiftModifier) and hasattr(self._owner, "redo"):
                    self._owner.redo()
                else:
                    self._owner.undo()
                return
            if key == Qt.Key.Key_Y and (mods & Qt.KeyboardModifier.ControlModifier) \
                    and hasattr(self._owner, "redo"):
                self._owner.redo()
                return
        super().keyPressEvent(event)



# annotator_core.py의 `import *`가 밑줄 접두 이름까지 넘겨받게 강제(위 두 파일과 동일 이유).
__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
