"""캔버스 아이템·기하/라우팅 엔진 — annotator_core.py(8169줄) 2026-08-02 분할분.

`_HandleResizeMixin`(핸들·리사이즈·회전·stretch 공용) + 모든 아이템 클래스(사각형·원·심볼·
이미지·표제란·표·선·펜·화살표 2종·배지·텍스트) + 그 아이템들이 쓰는 최근접점/포트/A* 직교
라우팅/그룹 변형 함수 전부를 한 파일에 둔다. 이 셋(핸들믹스인·아이템·기하라우팅)은 실제로
서로를 호출하는 순환 의존 관계라(핸들믹스인이 화살표 재바인딩 때 라우팅을 부르고, 라우팅이
아이템 타입을 판별해 분기하고, 아이템이 핸들믹스인을 상속) 억지로 3파일로 쪼개면 함수-지역
임포트를 여러 곳에 흩뿌려야 해서 이 프로젝트에서 가장 버그가 잦았던 영역(docs/pitfalls.md
참조: A* 격자·정렬 게이트 등)의 위험만 키운다 — 하나로 유지하는 쪽이 더 안전하다는 판단.
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
    PEACH as _PEACH, GREEN as _GREEN, RED as _RED,
)


from easycad.canvas.core_constants import *  # noqa: F401,F403

class _HandleResizeMixin:
    # 핸들(스케일 사각·회전 원·끝점 사각) 크기는 도형 획 두께와 무관하게 고정이다(2026-07-30
    # 사용자 피드백 — 하한/상한 두 값을 두느니 고정값 하나로 통일). 1차로 16, 2차로 10(스냅
    # 마커 _draw_snap_marker 지름), 3차로 7(포트 예고점 _draw_port_dots 지름)을 썼으나 재피드백
    # (2026-07-30 3차 재수정)으로 기준을 다시 뒤집었다 — "선택/비선택 둘 다"의 기본 크기를
    # _draw_snap_marker(포트 하나에 정확히 호버했을 때 뜨는 그 강조점, 지름 10)로 맞추고,
    # _draw_port_dots(주변 포트 전체 예고, 이제 이것과 지름 통일)를 3.5→5.0으로 함께 올렸다.
    # 어느 핸들이 잡히는지는 hover 강조(흰 채움 반전, 아래 _hover_handle)로 알려준다 — 크기를
    # 더 키우지 않는다(호버로 커지는 게 아니라 애초에 그 크기가 기본값).
    _HANDLE_PX = 10.0   # 씬 단위 — 모든 핸들 공통 고정 크기(_draw_snap_marker 지름과 동일)
    _EDGE_HIT_MIN = 8.0  # 속 빈 도형 테두리 클릭 최소 히트폭(씬 단위) — 얇은 선도 잡히게
    # [실사용 지적 2026-08-11, Figma/Lucid 스크린샷 실측 재도입] 리사이즈 핸들(모서리·변)은
    # 두 레퍼런스 다 테두리 위에 딱 붙어 있고, 커넥터 점만 그보다 훨씬 멀리(약 20~25px) 떨어져
    # 있다 — "테두리 근처=리사이즈, 그보다 바깥=커넥터"로 영역 자체가 갈라져 있어 겹치지 않는다.
    # 이전엔 모서리 핸들과 큐닷이 같은 `_HANDLE_GAP_FACTOR`(6px)를 공유해 리사이즈 밴드(±4px)와
    # 큐닷이 겹쳤다 — 모서리는 테두리 위(오프셋 0)로 되돌리고, 큐닷만 이 전용 상수로 분리한다.
    _QC_DOT_GAP_PX = 24.0   # 씬 단위 — 큐닷 전용 오프셋(리사이즈 핸들과 공유하지 않음)

    def _qc_dot_gap(self) -> float:
        return self._QC_DOT_GAP_PX / self._scale_or_1()

    # [편의기능] 잠금·그룹 — 클래스 기본값(인스턴스는 host의 토글/그룹 메서드가 설정).
    # clone()은 이 필드를 모르므로 복제본은 항상 이 기본값(미잠금·무그룹)에서 시작한다.
    _locked = False
    _group_id = None

    # [성능 조사 2026-08-13] boundingRect()의 값 비교 캐시(선택된 도형의 qc-dot/모서리핸들
    # union 스킵용) — 클래스 기본값 None이면 최초 호출에서 항상 미스(안전한 콜드스타트).
    _bbox_cache_key = None
    _bbox_cache_rect = None

    # [호버 강조] 현재 커서 아래 있는 핸들 키(뷰가 매 프레임 갱신) — ("corner",i) / ("rot",None) /
    # ("qc",side) / ("ep",i) / ("scale",None) / None. paint()가 이 키와 자신의 핸들을 비교해
    # 그 점만 반전 강조(흰 채움+색 테두리)한다.
    _hover_handle = None

    def _handle_px(self, scale: float | None = None) -> float:
        """핸들 한 변(로컬 단위) — 고정 크기(씬 단위)를 아이템 배율로 환산.
        [화살표 boundingRect 최적화 2026-08-01] scale을 이미 알면 넘겨 재계산 생략
        (boundingRect가 정점마다 이 경로를 도는데 `_scale_or_1()` 자체가 view.transform()
        Qt 호출이라 반복 비용이 큼 — cProfile 실측, 아래 boundingRect 주석 참조)."""
        return self._HANDLE_PX / (scale if scale is not None else self._scale_or_1())

    def itemChange(self, change, value):
        """[성능 조사 2026-07-30] 선택 상태가 바뀌기 '직전'에 옛(핸들 포함) boundingRect를
        Qt에 미리 무효화시켜, boundingRect()가 선택 여부로 크기를 바꿔도(아래) 잔상 없이
        전환되게 한다 — prepareGeometryChange()가 '지금 boundingRect가 곧 달라진다'를 Qt에
        알리는 표준 방법이라, 매 페인트마다 핸들 영역을 상시 예약해두는 것보다 싸다."""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.prepareGeometryChange()
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # [실사용 버그 수정 2026-08-03] 포트를 드래그하는 동안 호스트 테두리에 계속
            # 달라붙어 있어야 한다("SNAP이 중요"하다는 사용자 지적) — 지금까지는 놓는
            # 순간의 위치로만 (fx,fy)를 계산해, 드래그 중엔 테두리를 벗어나 아무 데나
            # 놓을 수 있었다. 제안된 새 위치를 즉시 호스트 테두리 최근접점으로 되돌린다.
            host = getattr(self, "_port_host", None)
            if host is not None:
                return _snap_port_pos_to_host_border(self, host, value)
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # [신규기능 §8-12] 포트를 직접 드래그해 옮기면 새 위치를 (fx,fy)로 다시 저장하고
            # (호스트 리사이즈 때 이 새 상대위치를 유지) 호스트를 다시 그려 trim 자리를 갱신.
            host = getattr(self, "_port_host", None)
            if host is not None:
                _update_port_frac_from_pos(self, host)
                host.update()
        return super().itemChange(change, value)

    # ---- 잡기 판정(시각 점과 분리) --------------------------------------
    # 그려지는 점은 작게(_handle_px) 두되, '잡히는' 영역은 화면 고정 px로 넉넉히
    # — Figma·일러스트레이터식. 얇은 화살표의 bend/끝점 점이 화면상 5~12px라 커서를
    # 정확히 맞춰야 손가락 커서가 되던 문제를 없앤다(hover·press·shape 모두 이 rect 사용).
    _HIT_MIN_PX = 24.0   # 화면 px — 핸들 잡기 최소 지름(줌 무관)

    def _hit_pad_local(self, scale: float | None = None, view_zoom: float | None = None) -> float:
        """잡기 판정 반지름(로컬 단위). 화면 고정 px를 현재 뷰·아이템 배율로 환산.
        [최적화 2026-08-01] `view_s`는 `sc.views()[0]._view_scale()`로 매번 뷰 목록을 새로
        구성해 읽던 것을 `_view_zoom_factor()`(뷰 참조 캐시, 메인 인터랙티브 뷰만 대상 —
        이 앱은 메인 뷰가 항상 `sc.views()[0]`이라 값은 동일, 성능 조사 2026-07-30에서
        이미 검증된 캐시)로 교체 — 값 불변, 조회만 저렴해짐. scale·view_zoom 둘 다 호출부가
        이미 알면 넘겨받아 재조회를 생략한다(boundingRect가 정점마다 이 경로를 돈다)."""
        view_s = view_zoom if view_zoom is not None else _view_zoom_factor(self)
        s = scale if scale is not None else self._scale_or_1()
        total = max(view_s * s, 1e-6)
        return (self._HIT_MIN_PX / total) / 2.0

    def _inflate_to_hit(self, rect: QRectF, scale: float | None = None,
                         view_zoom: float | None = None) -> QRectF:
        """핸들 시각 rect를 잡기 최소 지름까지 부풀린 판정용 rect(이미 크면 그대로)."""
        grow = self._hit_pad_local(scale, view_zoom) - rect.width() / 2.0
        if grow <= 0.0:
            return rect
        return rect.adjusted(-grow, -grow, grow, grow)

    def _init_resize(self):
        self._resizing = False
        self._rotating = False
        self._drag_endpoint = None  # 끝점 드래그 중인 인덱스(0·1, None=없음) — 선·화살표만
        self._press_scale = 1.0
        self._press_dist = 1.0
        self._press_rot = 0.0
        self._press_angle = 0.0
        # [2c] 네모·원 박스 리사이즈(꼭짓점 2D·변 1축, setRect 기반) 상태
        self._box_resize = None     # None | ("corner", 0..3) | ("edge", "l"/"r"/"t"/"b")
        self._box_orig_rect = None  # 드래그 시작 시 rect()(원본 기준 — 누적 방지)
        self._box_snap = None       # [(item, capture_geom()), ...] — geom undo
        self._box_bound = None      # _collect_bound_arrows 결과(부착점 상대유지)
        # [신규기능 2026-08-10] TRIM 자국(_cuts) 경계 핸들 드래그 상태
        self._cut_drag = None       # None | (cut_index, "t0"|"t1")
        self._cut_drag_before = None   # 드래그 시작 시 _cuts 스냅샷(undo)

    # ---- 끝점(양끝 이동) 모드 -------------------------------------------
    # 선·화살표처럼 '2점으로 완전히 결정되는' 도형은 회전+균일스케일 핸들 대신
    # 양끝점 핸들을 쓴다(끝점 2개면 길이·각도가 모두 결정 → 회전/스케일 중복). 기본은 off라
    # 네모·원·번호·텍스트는 기존 회전+스케일 핸들을 그대로 쓴다.
    def _uses_endpoints(self) -> bool:
        return False

    def _endpoints(self):
        """끝점들의 로컬 좌표 리스트(선·화살표가 override)."""
        return []

    def _set_endpoint(self, idx: int, p: QPointF):
        """끝점 idx를 로컬 좌표 p로 이동(선·화살표가 override)."""
        pass

    def _group_active(self) -> bool:
        """[우리 확장] 씬에 최상위(라벨 등 자식 제외) 선택 아이템이 2개 이상인가.
        참이면 개별 회전·크기·끝점 핸들을 숨기고 그룹 변형 오버레이(_GroupTransform)에 넘긴다.
        [성능수정 2026-08-15] `selectedItems()`는 Qt가 매 호출마다 선택 전체 리스트를 새로
        만든다. 이 함수는 hover·paint 스캔에서 **아이템마다** 불려, 1000개 선택 시 마우스를
        한 번 움직이는 데만 1,260회 호출돼 157ms를 먹었다(병목 A와 같은 O(N²) 패턴).
        `CanvasWindow._sync_selection_count_cache`가 selectionChanged에서만 갱신하는
        `_sel_top_count_cache`를 O(1)로 읽고, 없으면(독립 씬) 기존 방식으로 폴백한다."""
        sc = self.scene()
        if sc is None:
            return False
        cached = getattr(sc, "_sel_top_count_cache", None)
        if cached is not None:
            return cached >= 2
        n = 0
        for it in sc.selectedItems():
            if it.parentItem() is None:
                n += 1
                if n >= 2:
                    return True
        return False

    def _endpoint_active(self) -> bool:
        # 선택돼 있으면 어떤 도구에서든 끝점 이동·재스냅 가능(회전·크기조절 핸들과 동일 정책).
        # 단 다중선택(그룹 변형) 중엔 개별 끝점 핸들을 감춘다 — 그룹 오버레이가 대신 변형.
        return self.isSelected() and not self._group_active()

    def _handle_indices(self):
        """끝점 핸들(파란 사각)을 그릴 정점 인덱스. 기본은 모든 끝점. [M4-4] _PolyArrowItem은
        양끝(시작·끝)만 노출해 중간 정점 자유드래그로 직교가 깨지는 걸 막는다(중간은 세그먼트 드래그)."""
        return list(range(len(self._endpoints())))

    def _endpoint_rect(self, idx: int, scale: float | None = None) -> QRectF:
        d = self._handle_px(scale)
        c = self._endpoints()[idx]
        return QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

    def _snap_endpoint(self, idx: int, p: QPointF) -> QPointF:
        """Shift 스냅: 반대쪽 끝점을 기준으로 0/45/90°에 스냅."""
        pts = self._endpoints()
        anchor = pts[1 - idx] if len(pts) == 2 else pts[idx]
        dx, dy = p.x() - anchor.x(), p.y() - anchor.y()
        dist = math.hypot(dx, dy)
        rad = math.radians(round(math.degrees(math.atan2(dy, dx)) / 45.0) * 45.0)
        return QPointF(anchor.x() + dist * math.cos(rad), anchor.y() + dist * math.sin(rad))

    def _ortho_endpoint(self, idx: int, p: QPointF) -> QPointF:
        """[우리 확장] F8 Ortho 정점 드래그: 인접 정점 기준 0/90°에 스냅(로컬 좌표).
        인접 = 이전 정점 우선(없으면 다음). |dx|≥|dy|면 수평, 아니면 수직."""
        pts = self._endpoints()
        if len(pts) < 2:
            return p
        anchor = pts[idx - 1] if idx > 0 else pts[idx + 1]
        if abs(p.x() - anchor.x()) >= abs(p.y() - anchor.y()):
            return QPointF(p.x(), anchor.y())
        return QPointF(anchor.x(), p.y())

    def _connects_to_border(self) -> bool:
        """이 아이템의 끝점이 도형 테두리에 재스냅되는가(화살표만 override)."""
        return False

    def _endpoint_border_snap(self, local_p: QPointF):
        """끝점 드래그 중 근처 네모/원 테두리에 스냅(생성 때와 동일 _border_snap_at 재사용).
        스냅되면 (로컬 최근접점, 바깥 법선 scene, shape), 아니면 None — 뗐다 다시 가져가도 붙는 경로.
        (shape는 지속 연결 바인딩용 — 기존 인덱서 [0]/[1]과 호환.)
        [실조건 2026-07-27 · 재부착 추종 실패 근본원인] `_border_snap_at`은 `exclude`를 받아 자기
        자신을 스냅 후보에서 뺄 수 있게 설계돼 있는데(그 함수 docstring: "exclude=자기 자신(끝점
        재스냅 시 self 제외)") 여기서 안 넘겼다. 그 결과 이 아이템(화살표) 자신의 다른 세그먼트/
        끝점이 M4-2b의 "선·화살표 몸통 스냅"(기하만, shape=None) 후보로 잡혀, 도형 테두리보다
        먼저·더 가깝게 자기 몸에 스냅될 수 있었다 — 시각적으로는 도형 근처라 붙은 것처럼 보이지만
        `set_bound(idx, None)`이 호출돼 바인딩이 전혀 안 걸린다(디버그 로그로 재현·확인)."""
        if not self._connects_to_border():
            return None
        sc = self.scene()
        if sc is None or not sc.views():
            return None
        view = sc.views()[0]
        snap = getattr(view, "_border_snap_at", None)
        if snap is None:
            return None
        res = snap(view.mapFromScene(self.mapToScene(local_p)), exclude=self)
        if res is None:
            return None
        return self.mapFromScene(res[0]), res[1], res[2]

    def _move_endpoint_with_snap(self, idx: int, local_p: QPointF):
        """끝점 idx를 이동하되 테두리 근처면 스냅(기본: 점 스냅만. 화살표는 S자 곡선 재계산 override)."""
        snapped = self._endpoint_border_snap(local_p)
        if snapped is not None:
            local_p = snapped[0]
        self._set_endpoint(idx, local_p)

    def _rebind_at_fixed_point(self, idx: int, local_p: QPointF):
        """[실조건 2026-07-27] Shift(각도 스냅)·F8(직교 제약) 드래그 전용 — **위치는 건드리지 않고
        바인딩만** 갱신한다. mouseMoveEvent의 그 두 분기는 `_move_endpoint_with_snap`을 거치지 않아
        (의도적으로 테두리 스냅보다 축 제약을 우선시킴) `set_bound`를 아예 호출하지 않았다. 그 결과:
          · 이미 뗀(unbound) 끝점을 그 두 모드로 도형 위에 시각적으로 올려도 바인딩이 안 걸려
            도형을 옮겨도 화살표가 따라오지 않았다(사용자 보고 — 중심점 아닌 곳에 재부착).
          · 이미 붙은 끝점을 축 제약으로 미세조정하면 옛 bind_pt(도형 로컬좌표)가 안 갱신돼,
            다음 도형 이동 때 방금 조정한 위치가 아니라 그 **옛 위치로 되돌아갔다.**
        `_endpoint_border_snap`으로 도형 판정만 재사용하고 반환된 좌표는 버린다(축 제약 위치 보존).
        근처에 도형이 없으면 unbind — 스텁 바인딩이 남아 다음 이동 때 엉뚱한 곳으로 튀는 것 방지.
        ⚠ `_LineItem`은 `_connects_to_border()`가 False이자 `set_bound` 자체가 없다(바인딩 미지원) —
        `_endpoint_border_snap`과 같은 가드로 여기서 먼저 걸러야 AttributeError가 안 난다."""
        if not self._connects_to_border():
            return
        snapped = self._endpoint_border_snap(local_p)
        shape = snapped[2] if snapped is not None else None
        if shape is not None:
            self.set_bound(idx, shape, shape.mapFromScene(self.mapToScene(local_p)))
        else:
            self.set_bound(idx, None)

    def _on_endpoint_drag_start(self, idx: int):
        """[우리 확장] 정점 핸들 드래그가 '시작'될 때 호출(mousePress choke point). 기본 no-op.
        _PolyArrowItem이 override해 자동 직교 라우팅을 해제한다(수동 정점 조작 = 수동 경로)."""
        pass

    def _on_endpoint_drag_end(self, idx: int):
        """[경유지 힌트] 정점 핸들 드래그가 '끝날' 때 호출(mouseRelease choke point). 기본 no-op.
        _PolyArrowItem이 override해 드래그한 중간 정점을 자동라우팅 경유 힌트로 커밋한다."""
        pass

    def _paint_endpoint_handles(self, painter: QPainter):
        if not self._endpoint_active():
            return
        s = self._scale_or_1()
        hv = self._hover_handle
        for i in self._handle_indices():
            self._set_handle_paint(painter, s, _BLUE, hv == ("ep", i))
            painter.drawRect(self._endpoint_rect(i))

    # 선택된 도형에 현재 색/두께 적용. pen 기반(rect/ellipse/line/path)은 QPen에,
    # arrow/badge는 `_color`/`_width` 필드에 저장 — 둘 다 여기서 분기(text는 색 보관 방식이
    # 아예 달라 setDefaultTextColor로 완전히 오버라이드). (2026-07-28 코드정리: arrow·
    # PolyArrow·badge 3곳에 byte-for-byte 동일하게 중복되던 `_color` 분기를 여기로 흡수 —
    # apply_style은 host.py의 hasattr(it,"apply_style") 분기가 "화살표냐 아니냐"를 가르는
    # 신호라 여기 흡수하면 pen 기반 도형의 점선 적용이 깨진다(의도적으로 남김).
    def apply_color(self, color):
        if hasattr(self, "_color"):
            self._color = QColor(color)
            self.update()
        elif hasattr(self, "pen"):
            pen = self.pen()
            pen.setColor(QColor(color))
            self.setPen(pen)

    def apply_width(self, width):
        if hasattr(self, "_width"):
            self.prepareGeometryChange()  # boundingRect가 _width에 의존
            self._width = width
            self.update()
        elif hasattr(self, "pen"):
            pen = self.pen()
            pen.setWidthF(float(width))
            self.setPen(pen)

    # 복제 시 위치·스케일·회전·z·플래그(이동/선택 가능) 공통 복사. 타입별 기하/색은 각 clone()이 채운다.
    def _copy_common_to(self, dst):
        dst.setPos(self.pos())
        dst.setScale(self.scale())
        dst.setTransformOriginPoint(self.transformOriginPoint())
        dst.setRotation(self.rotation())
        dst.setZValue(self.zValue())
        dst.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        return dst

    # ---- [Stage2] 기하 리베이크(비균일 스케일·미러) — 스냅샷/복원/씬공간 변형 ----------
    # Stage1의 xform(pos/rot/scale/origin만)과 달리 '기하 자체'를 바꾼다. 씬공간 함수 fn을 받아
    # 각 기하 제어점을 fn(현재 씬위치)로 다시 굽는다(rebake). pos/rot/scale/origin은 그대로 두고
    # fn을 아이템 transform을 '통과'시켜 적용하므로(mapToScene→fn→mapFromScene) 기존 setScale·
    # 회전 상태와 안 엉킨다(회전=0·스케일 임의면 정확, 회전 도형은 로컬 AABB 근사 — 설계 합의).
    def capture_geom(self) -> dict:
        """undo·드래그 복원용 기하 스냅샷(pos/rot/scale/origin + 타입별 기하 + 바인딩)."""
        return {
            "pos": QPointF(self.pos()),
            "rot": self.rotation(),
            "scale": self.scale(),
            "org": QPointF(self.transformOriginPoint()),
            "geom": self._capture_geom_local(),
            "binds": self._capture_binds(),
        }

    def apply_geom(self, tok: dict):
        """capture_geom 스냅샷 복원(원복)."""
        self.prepareGeometryChange()
        self.setTransformOriginPoint(tok["org"])
        self.setRotation(tok["rot"])
        self.setScale(tok["scale"])
        self.setPos(tok["pos"])
        self._apply_geom_local(tok["geom"])
        self._apply_binds(tok["binds"])
        self.update()

    # [Easy CAD 확장 · Phase 6 M2] 속성 스냅샷 — undo 저널의 'state' mutate용.
    # capture_geom(기하: pos/rot/scale/geom/binds)과 층이 다르다: 이건 '겉모습'
    # (색·두께·선스타일·폰트·텍스트)만 담는다. 색·두께 변경이 저널에 실리지 않아
    # 되돌려지지 않던 문제(M2 근본 원인)를 이 한 쌍이 받는다. 아이템 종류별 override
    # 없이 duck-typing으로 흡수한다(rect/ellipse=pen, arrow=_color/_width, text=폰트/내용).
    def capture_state(self) -> dict:
        st: dict = {}
        if hasattr(self, "pen"):
            p = self.pen()
            st["pen"] = (QColor(p.color()), p.widthF(), p.style())
        if hasattr(self, "_color"):
            st["color"] = QColor(self._color)
        if hasattr(self, "_width"):
            st["width"] = self._width
        if hasattr(self, "_style"):   # [M2 #3] 화살표 몸통 선스타일(pen 없는 화살표 전용)
            st["style"] = self._style
        if hasattr(self, "apply_fill"):   # [신규기능] 도형 채우기 — rect/ellipse/symbol만
            st["fill"] = (QColor(self.brush().color())
                          if self.brush().style() != Qt.BrushStyle.NoBrush else None)
        if hasattr(self, "_head_at_end") and hasattr(self, "set_head_at_end"):
            st["head"] = self._head_at_end   # [M3 #15] 화살표 방향 — 토글을 undo 가능하게
        if hasattr(self, "setDefaultTextColor"):
            st["tcolor"] = QColor(self.defaultTextColor())
        if hasattr(self, "toPlainText"):
            st["font_pt"] = getattr(self, "_base_pt", self.font().pointSize())
            st["text"] = self.toPlainText()
            st["bg"] = QColor(self._bg) if getattr(self, "_bg", None) is not None else None
        return st

    def apply_state(self, st: dict):
        # 가능한 한 기존 setter(apply_color/apply_width/apply_font_size/set_bg)를 통해 복원해
        # 각 아이템의 리프레시(prepareGeometryChange 등)를 그대로 태운다.
        if "pen" in st:
            col, w, style = st["pen"]
            p = self.pen()
            p.setColor(col); p.setWidthF(w); p.setStyle(style)
            self.setPen(p)
        if "color" in st and hasattr(self, "apply_color"):
            self.apply_color(st["color"])
        if "width" in st and hasattr(self, "apply_width"):
            self.apply_width(st["width"])
        if "style" in st and hasattr(self, "apply_style"):   # [M2 #3] 화살표 선스타일
            self.apply_style(st["style"])
        if "fill" in st and hasattr(self, "apply_fill"):   # [신규기능] 도형 채우기
            self.apply_fill(st["fill"])
        if "head" in st and hasattr(self, "set_head_at_end"):   # [M3 #15] 화살표 방향
            self.set_head_at_end(st["head"])
        if "tcolor" in st and hasattr(self, "setDefaultTextColor"):
            self.setDefaultTextColor(st["tcolor"])
        if "font_pt" in st and hasattr(self, "apply_font_size"):
            self.apply_font_size(st["font_pt"])
        if "text" in st and hasattr(self, "setPlainText") \
                and self.toPlainText() != st["text"]:
            self.setPlainText(st["text"])
        if "bg" in st and hasattr(self, "set_bg"):
            self.set_bg(st["bg"])
        self.update()

    def _capture_geom_local(self):
        """타입별 기하 복사(하위 클래스 override)."""
        return None

    def _apply_geom_local(self, g):
        pass

    def _capture_binds(self):
        """지속연결 바인딩(도형·부착점) 복사 — 화살표만 override."""
        return None

    def _apply_binds(self, b):
        pass

    def _rebake_pt(self, fn, p_local: QPointF) -> QPointF:
        """로컬 제어점 → 씬 → fn → 로컬(아이템 transform 통과)."""
        return self.mapFromScene(fn(self.mapToScene(p_local)))

    def rebake_scene(self, fn):
        """기하 제어점을 씬공간 함수 fn으로 다시 굽는다(하위 클래스 override).
        기본(스칼라 폴백: 텍스트·번호)은 왜곡 대신 내용 중심을 fn으로 옮겨 위치만 따라가게 한다."""
        c = self.mapToScene(self._content_rect().center())
        d = fn(c) - c
        self.setPos(self.pos() + d)

    # [Stage2b] stretch — 이 아이템의 '정점(grip)' 씬좌표들. crossing 박스 안에 든 grip만
    # stretch 시 delta로 이동한다(밖은 고정). 하이라이트(●) 표시 전용 — 실제 이동은
    # rebake_scene(공간 fn)이 담당한다(네모·원은 걸친 모서리 AABB로 자연히 일치).
    # 기본: 끝점 보유형(선·화살표·폴리)은 끝점들, 아니면 내용 중심(텍스트·번호=스칼라 폴백).
    def _stretch_grips(self):
        if self._uses_endpoints():
            return [self.mapToScene(p) for p in self._endpoints()]
        return [self.mapToScene(self._content_rect().center())]

    def _scale_or_1(self, view_zoom: float | None = None) -> float:
        # [화살표 boundingRect 최적화 2026-08-01] view_zoom을 이미 알면(호출부가 한 번만
        # `_view_zoom_factor()`를 읽어 여러 곳에 재사용) 넘겨받아 재조회를 생략한다.
        vz = view_zoom if view_zoom is not None else _view_zoom_factor(self)
        s = self.scale() * vz
        return s if s else 1.0

    # 타이트 경계(선택박스·핸들 기준). 도형별로 override한다(기본은 Qt 기본 boundingRect).
    def _content_rect(self) -> QRectF:
        return super().boundingRect()

    # 핸들 hit-test의 기준 영역(선택 시 핸들 미포함). 기본은 Qt 기본 shape;
    # boundingRect 기반 shape를 쓰는 도형(arrow/badge)은 content_rect로 override해
    # 회전 핸들 여유분이 클릭 영역에 새는 것을 막는다.
    def _base_shape(self):
        return super().shape()

    # 실제 boundingRect = content ∪ 회전 핸들 영역(상시 예약 → 선택 해제 시 핸들 잔상 방지).
    # 위쪽뿐 아니라 좌우도 덮어야 함 — 얇은 도형(세로선 등)은 핸들 원이 content보다 가로로
    # 넓어 좌우로 삐져나오므로. 여유분은 scale 의존이라, 크기조절 중 mouseMove에서
    # prepareGeometryChange로 갱신한다.
    # [성능 조사 2026-07-30] 박스 핸들(_box_handles) 분기만 선택 여부로 조건화한다 — 끝점형·
    # 폴백 분기는 그대로 둔다(끝점은 항상 히트 대상이라 필요, 폴백은 이 세션의 실측 핫스팟이
    # 아니었음). boundingRect()는 Qt가 인덱싱·히트테스트·페인트 판정마다 매우 자주 호출하는데,
    # qc-dot 4개+회전핸들 영역 계산(그 안의 _handle_px→_view_zoom_factor 체인 포함)을 '선택
    # 안 된' 도형까지 매번 하던 게 cProfile 실측으로 다중선택 드래그 비용의 가장 큰 비중을
    # 차지했다. 미선택 도형은 핸들이 그려지지도 히트테스트되지도 않으므로 이 영역이 필요 없다
    # — 선택 전환 시 잔상은 위 itemChange의 prepareGeometryChange()가 방지한다.
    def boundingRect(self) -> QRectF:
        # [화살표 boundingRect 최적화 2026-08-01] `_view_zoom_factor()`/`_scale_or_1()`을 이
        # 함수 전체에서 한 번씩만 읽어 아래로 넘긴다 — cProfile 실측(합성 화살표 200개
        # 다중드래그): 정점마다 `_endpoint_rect`·`_inflate_to_hit`·`_scale_or_1`이 각각 새로
        # `_view_zoom_factor()`(=view.transform().m11() 체인)를 불러 boundingRect 한 번에
        # 5회 넘게 호출되던 게 최대 비용원이었다(값은 그 사이 안 바뀌므로 재계산은 순수
        # 낭비). `_content_rect()`/`_head_points()`의 삼각함수 비용은 `_pts`에 의존하는 실제
        # 기하 계산이라 이번엔 손대지 않음(캐시하려면 모든 변경 지점에 무효화 훅이 필요해 이
        # CAD 앱에서 위험 대비 이득이 낮다고 판단).
        # [성능 최적화 2026-08-13, 시도했다 되돌림] `_PolyArrowItem`의 `_geom_version` 캐시를
        # 이 믹스인에도 확장해봤으나(cProfile상 291개 선택 드래그에서 qc-dot/모서리핸들 반복
        # 재계산이 컸음), `prepareGeometryChange()`는 Qt C++에서 virtual이 아니라 `setRect()`/
        # `setFont()`/`setPlainText()` 같은 **Qt 자체 네이티브 호출**이 내부적으로 부르는
        # prepareGeometryChange는 이 Python 오버라이드를 안 타 `_geom_version`이 안 올라간다
        # (`_PolyArrowItem`은 기하 변경이 전부 이 코드베이스의 파이썬 메서드를 거쳐 안전했지만,
        # 이 믹스인은 `_TextItem.setFont()` 등 네이티브 경로가 있어 전제가 다름). 실측 회귀로
        # 확인(`test_sketch_build_roundtrip` — 라벨 폰트 축소(`_fit_label_to_shape`의 setFont)
        # 후에도 옛(축소 전) boundingRect가 캐시에 남아 라벨이 중앙에서 11~32유닛 어긋남). 위
        # 2026-08-01 결정("무효화 훅이 여기저기 필요해 위험 대비 이득이 낮다")이 옳았다 — 되돌림.
        vz = _view_zoom_factor(self)
        s = self._scale_or_1(vz)
        pad = 3.0 / s
        if self._uses_endpoints():
            r = self._content_rect()
            for i in range(len(self._endpoints())):
                # 시각 rect가 아니라 '잡기' rect까지 예약해야 넉넉한 hit-shape가
                # boundingRect 밖으로 나가 Qt에 컬링당하지 않는다.
                r = r.united(self._inflate_to_hit(self._endpoint_rect(i, s), s, vz))
            return r.adjusted(-pad, -pad, pad, pad)
        if self._box_handles():
            # [성능수정 2026-08-15, 2-C(a)] 다중선택 중엔 개별 핸들·qc-dot이 **그려지지 않으므로**
            # (`_handle_active()`가 False) 그 자리를 예약할 이유도 없다. 예약하려면 아래에서
            # `_box_rot_rect`·`_qc_dot_rects`·`_box_corner_rects` 기하를 매번 계산해야 하는데,
            # 1000개 전체선택 드래그 실측에서 이 boundingRect 체인이 프레임 비용의 41%
            # (프레임당 10,500회 호출)였다. 오늘 고친 "다중선택이면 개별 핸들은 없는 것"
            # 규칙(`_group_owns_interaction`)이 여기에만 아직 적용 안 돼 있었다.
            # ⚠ 2개↔1개 경계를 넘을 때는 이 아이템 자신의 선택 상태가 안 바뀌어 Qt에
            # `prepareGeometryChange()`가 안 간다 — `CanvasWindow._sync_selection_count_cache`
            # 가 그 전환에서 명시적으로 무효화한다(안 하면 핸들이 잘려 보인다).
            if not self.isSelected() or self._group_active():
                return self._content_rect().adjusted(-pad, -pad, pad, pad)
            # 꼭짓점·변 핸들은 rect 경계서 half-handle 삐져나오고, 회전 핸들·접속점은 바깥.
            h = self._handle_px(s)
            cr = self._content_rect()
            # [성능 조사 2026-08-13, §8 항목0 후속] 이 분기(선택된 도형)는 다중선택 그룹드래그
            # 200개+에서 cProfile 실측상 프레임 비용의 86%를 차지했다 — `_qc_dot_rects()`가
            # 내부적으로 `_shape_ports`→`_nearest_border`→`_axis_forced_local_normal` 기하
            # 검색을 매 boundingRect() 호출마다(Qt가 인덱싱·히트테스트·페인트마다 부름) 처음부터
            # 다시 돈다. 순수 위치이동(그룹 드래그 = setPos만 바뀜)에서는 로컬 좌표인 이 결과가
            # 프레임마다 수학적으로 동일한데도 매번 재계산되고 있었다(`docs/perf_group_drag_200.md`
            # 실측 근거).
            #
            # [실패했던 접근 — 재시도 금지] 같은 날 앞서 `_geom_version`+`prepareGeometryChange()`
            # 버전키 캐시(`_PolyArrowItem`이 쓰는 패턴)를 이 믹스인에 확장했다가 되돌렸다 —
            # `prepareGeometryChange()`는 Qt에서 non-virtual이라, `_TextItem.setFont()` 같은
            # **네이티브** 호출이 내부적으로 부르는 prepareGeometryChange는 이 오버라이드를 안 타
            # 버전이 안 올라가고 캐시가 stale해졌다(`test_sketch_build_roundtrip` 회귀로 발견,
            # `docs/pitfalls.md` "Qt 시그널·이벤트 발화 조건" 참조).
            #
            # 여기서는 이벤트/시그널 무효화를 아예 안 쓴다 — 대신 이미 매 호출 계산해야 하는 저비용
            # 값(`cr`·`s`·`h`, 아래)을 캐시 키로 직접 비교한다. `_content_rect()`는 `_TextItem`의
            # 경우 `super().boundingRect()`(Qt 네이티브 텍스트 레이아웃)로 귀결돼 setFont() 직후
            # 항상 최신값이므로, 이 비교 자체가 native 경로를 우회할 수 없다(무효화를 "받는" 게
            # 아니라 매번 직접 "확인"하므로 구조적으로 stale이 불가능).
            key = (cr.x(), cr.y(), cr.width(), cr.height(), s, h)
            if self._bbox_cache_key == key:
                return self._bbox_cache_rect
            # [하나의 시스템으로 통합 2026-08-01 — 실측 발견] 회전 핸들은 좌상단에만 있어 그대로
            # union하면 boundingRect 중심이 좌상단으로 쏠린다. 종전엔 접속점이 미연결일 때 훨씬
            # 크게(gap) 떠 있어 이 쏠림을 우연히 덮었지만(4방향 모두 회전 핸들보다 멀리 나가
            # 있었음), 접속점이 항상 테두리에 붙는 지금은 그 우연한 상쇄가 사라져 실제로 드러난다
            # (image 삽입 중심좌표 테스트로 발견). 회전 핸들이 튀어나온 만큼을 네 변에 똑같이 줘서
            # 대칭을 유지한다.
            rot_r = self._box_rot_rect()
            extra = max(cr.left() - rot_r.left(), cr.top() - rot_r.top(), 0.0)
            r = cr.adjusted(-extra, -extra, extra, extra)
            for _k, dr in self._qc_dot_rects():
                r = r.united(dr)
            # [2026-08-03] 꼭짓점 핸들도 이제 바깥으로 띄우므로(_box_corner_rects) 실제 위치를
            # union — 아래 마지막 `h` 패딩만 믿지 않고 기하 그대로 반영해 안전하게 맞춘다.
            for _i, cr_rect in self._box_corner_rects():
                r = r.united(cr_rect)
            result = r.adjusted(-h, -h, h, h)
            self._bbox_cache_key = key
            self._bbox_cache_rect = result
            return result
        # [성능수정 2026-08-15, 2-C(a)] 핸들이 안 그려지는 상태(미선택 또는 다중선택)면 회전
        # 핸들 자리를 union하지 않는다 — `_rot_handle_rect`는 캐시가 없어 매 호출 계산된다.
        # 실측에서 가장 놀라웠던 지점: 도형 라벨(`_TextItem`)은 **선택되지도 않는데** 이 경로를
        # 타서, 1000개 문서 드래그 10프레임에 `_rot_handle_rect`가 49,990회 불렸다.
        if not self._handle_active():
            return self._content_rect().adjusted(-pad, -pad, pad, pad)
        return self._content_rect().united(self._rot_handle_rect().adjusted(-pad, -pad, pad, pad))

    def _handle_local_rect(self) -> QRectF:
        h = self._handle_px()
        c = self._content_rect().bottomRight()
        return QRectF(c.x() - h, c.y() - h, h, h)

    def _rot_handle_center(self) -> QPointF:
        # 우상단 코너 안쪽 — 우하단 크기조절 점과 오른쪽 변에 위아래로 대칭인 점(줄기 없음).
        cr = self._content_rect()
        r = self._handle_px() * 0.5  # 원 반지름(= 크기조절 사각 변의 절반 → 같은 지름)
        return QPointF(cr.right() - r, cr.top() + r)

    def _rot_handle_rect(self) -> QRectF:
        d = self._handle_px()  # 원 지름 = 크기조절 사각 변
        c = self._rot_handle_center()
        return QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

    # ---- [2c] 네모·원 박스 핸들(꼭짓점 4·변 중점 4·좌상단 회전) ------------------
    # 텍스트·번호는 기존 단일 핸들(중심 균일 스케일)을 그대로 쓰고, setRect가 있는 네모·원만
    # Lucid식 8핸들로 자유 리사이즈한다. 핸들 위치·리사이즈 모두 '기하 rect()' 기준(펜 여유 없이
    # 정확). 선택 점선은 _content_rect(펜 밖)이라 핸들이 그 안쪽에 살짝 들어오지만 무해.
    def _box_handles(self) -> bool:
        return hasattr(self, "setRect") and not self._uses_endpoints()

    # [Lucid 대조 2026-08-03 재도입 → 2026-08-11 모서리만 원복] 한때 꼭짓점·변 핸들과
    # qc-dot이 같은 gap(`_HANDLE_GAP_FACTOR`, 6px)을 공유해 테두리 밖으로 함께 떠 있었다 —
    # "핸들이 도형 자체가 아니라 별도 컨트롤"이라는 시각적 구분이 목적이었는데, 그 결과 qc-dot이
    # 변 리사이즈 밴드(`_box_edge_side`, ±4px)와 겹쳐 "변 중앙을 잡으면 리사이즈 대신 커넥터로
    # 새는" 실사용 혼동이 났다. Figma/Lucid 스크린샷 실측 결과 두 레퍼런스 다 리사이즈 핸들은
    # 테두리 위(오프셋 0)에 있고 커넥터 점만 훨씬 멀리(약 20~25px) 떨어져 있어, 시각적 구분은
    # 핸들 색(파란 사각 `_BLUE`, 아래 `_paint_handle`)으로 이미 충분하다고 판단 — 모서리는
    # 오프셋을 없애 테두리에 딱 붙이고(레퍼런스와 일치), qc-dot은 `_qc_dot_gap()`(24px, 위
    # `_QC_DOT_GAP_PX`)으로 완전히 분리했다. qc-dot의 "선택 순간 점이 튀는" 비일관성 방지
    # 규칙(선택·미선택 호버 양쪽에 동일 gap 함수 공유)은 그대로 유지 — 모서리 오프셋과는
    # 원래도 무관한 별개 버그였다.

    def _box_corner_rects(self):
        # [2026-08-10, 여러 차례 시행착오 끝에 원복] 삼각형 전용 특례(꼭짓점 핸들을 실제
        # 정점으로 옮기고, 앞쪽 꼭짓점은 TR·BR을 겹치거나 빼는 등)를 여러 번 시도했었다 —
        # 근본 원인이 "정삼각형으로 내접(`_tri_rect`)시키느라 생기는 패딩"이었음을 뒤늦게
        # 파악해 `_sym_triangle` 자체가 이제 bbox를 그대로 채우도록(Lucid 대조) 고쳤다. 그
        # 결과 뒤쪽 두 꼭짓점(TL·BL)은 이 함수를 손대지 않아도 이미 bbox 모서리와 정확히
        # 일치하고, 앞쪽 꼭짓점(TR·BR 자리)은 Lucid의 "안 쓰이는 모서리 두 개"와 같은 처지가
        # 된다 — 실제 꼭짓점은 그 대신 변 중점 접속점(east qc-dot, `_shape_ports`가 정확히
        # 계산)이 담당한다. 그래서 이 함수는 다른 도형(네모·원)과 동일한 순수 bbox 공식으로
        # 되돌아간다 — 특례 코드 없음.
        br = self.rect()
        h = self._handle_px()
        pts = [br.topLeft(), br.topRight(), br.bottomRight(), br.bottomLeft()]  # 0TL 1TR 2BR 3BL
        return [(i, QRectF(p.x() - h / 2, p.y() - h / 2, h, h)) for i, p in enumerate(pts)]

    def _box_rot_center(self) -> QPointF:
        br = self.rect()
        gap = self._handle_px() * 1.6   # 좌상단서 대각으로 살짝 뗌
        return QPointF(br.left() - gap, br.top() - gap)

    def _box_rot_rect(self) -> QRectF:
        d = self._handle_px()
        c = self._box_rot_center()
        return QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

    def _qc_dragging_now(self) -> bool:
        """뷰가 지금 이 도형에서 커넥터 점 드래그 중이면 True — `_paint_handle`이 드래그 동안
        무관한 핸들(모서리 리사이즈·회전)을 감춰 어수선함을 줄이는 데 쓴다(2026-08-01, Lucid
        대조). [하나의 시스템으로 통합 2026-08-01] 상태 필드가 `_hp_*`로 합쳐져 그쪽을 본다."""
        sc = self.scene()
        if sc is None:
            return False
        v = getattr(sc, "_interactive_view_cache", None)
        if v is None:
            for vv in sc.views():
                if vv.isInteractive():
                    v = vv
                    sc._interactive_view_cache = v
                    break
        if v is None:
            return False
        try:
            return getattr(v, "_hp_dragging", False) and v._hp_src is self
        except RuntimeError:
            return False

    # [하나의 시스템으로 통합 2026-08-01 → 2026-08-03 재도입 → 2026-08-11 전용 gap 분리]
    # 상하좌우 접속점. 2026-08-01엔 항상 테두리 위(gap 없음)로 통일했었다 — 종전엔 미연결
    # 상태의 선택된 도형만 gap을 줘서 선택 순간 점이 튀는 비일관성이 있었기 때문. 2026-08-03엔
    # 선택·미선택(`_draw_port_dots`) 양쪽에 동일한 gap을 적용해 비일관성 없이 되살렸는데, 당시
    # 리사이즈 핸들과 같은 계수(`_HANDLE_GAP_FACTOR`, 6px)를 썼다가 변 리사이즈 밴드와 겹치는
    # 문제가 실사용에서 드러났다(위 `_box_corner_rects` 주석 참조) — 이제 `_qc_dot_gap()`
    # (24px) 전용 함수로 분리하되, "선택·미선택 양쪽에 동일 gap"이라는 비일관성 방지 원칙 자체는
    # 그대로 유지한다(`core_view.py`의 `_draw_port_dots`도 같은 함수를 쓴다). 클릭=도형 복제+
    # 화살표, 드래그=화살표(대상 없으면 도형도 생성). 2026-07-30엔 이 점을 변 리사이즈(1축)와도
    # 통합했었으나, "바깥으로 쭉 당기는" 자연스러운 동작이 항상 리사이즈로 판정되는 문제가
    # 실사용에서 드러나 되돌림(사용자 확인 2026-08-01) — 단일축 리사이즈는 이 점 자체가 아니라
    # 변 나머지 구간(`_box_edge_side`)이 담당한다.
    def _qc_dots_hover_suppressed(self) -> bool:
        """[신규기능 2026-08-13, Lucid 대조] 이 도형이 선택된 채로 다른(미선택) 도형을 호버
        중이면 True — 그 상태에선 이 도형의 큐닷을 숨긴다. 오프셋된 큐닷이 호버 중인 다른
        도형의 포트점 위/근처에 겹쳐 있으면, 그 포트점에서 화살표를 뽑아 이 도형에 붙이려 할 때
        오프셋 점을 지나쳐야 해서 헷갈린다는 실사용 지적(선택된 도형 자신을 호버할 땐 억제 안 됨
        — `_port_dot_shape`는 항상 미선택 도형만 담으므로 자연히 구분된다)."""
        sc = self.scene()
        if sc is None or not sc.views():
            return False
        target = getattr(sc.views()[0], "_port_dot_shape", None)
        return target is not None and target is not self

    def _qc_dot_rects(self):
        # [2026-08-04, 3차 수정] 포트도 선택 여부와 무관하게 자신의 4변 접속점을 유지한다
        # (실사용 요구: 드래그해서 화살표를 뽑는 용도로 항상 있어야 함) — 여기서 걸러내지
        # 않는다. 대신 "빈 캔버스에 놓으면 새 도형이 함께 생기는" 결과만 포트일 때 억제한다
        # (`_hp_create_arrow`/`_qc_create` 참조) — 포트는 화살표만 남기고 장비 복제는 없다.
        h = self._handle_px()
        d = h * 0.9
        gap = self._qc_dot_gap()
        sides = ("t", "r", "b", "l")   # _shape_ports와 동일 순서(상·우·하·좌)
        # [2026-08-10 → 후속 원복] 한때 삼각형의 "r"(동쪽=앞쪽 꼭짓점) qc-dot을 리사이즈
        # 핸들과 자리가 겹친다는 이유로 뺐었다 — `_sym_triangle`이 이제 bbox를 그대로 채우면서
        # (Lucid 대조) 앞쪽 꼭짓점의 리사이즈 핸들(TR·BR)은 bbox 모서리(=변 중심이 아닌 자리)에
        # 남고 qc-dot "r"은 실제 꼭짓점(=변 중심)에 남아 서로 다른 자리가 됐다 — 더 이상 겹치지
        # 않으므로 특례 없이 되돌린다.
        out = []
        for k, (sp, n) in zip(sides, _shape_ports(self)):
            sp_out = QPointF(sp.x() + n.x() * gap, sp.y() + n.y() * gap)
            p = self.mapFromScene(sp_out)
            out.append((k, QRectF(p.x() - d / 2, p.y() - d / 2, d, d)))
        return out

    def _cut_handle_rects(self):
        """[신규기능 2026-08-10] TRIM 자국(`_cuts`) 경계 두 점(t0/t1)마다 핸들 하나(로컬좌표) —
        실사용 제안: "잘린 부분의 끝점도 선택점으로 표기해서 거기서 추가 조절을 할 수 있어야
        하지 않나"(눈에 보이는 건 다 만질 수 있다는 이 앱의 기존 관례와 일관). 선택된 도형에만
        뜬다(`_handle_active()` 게이트는 호출부 `_paint_handle`/`_hover_handle_at`이 이미 검사).
        cut이 없는 도형·타입은 빈 리스트(변화 없음)."""
        cuts = getattr(self, "_cuts", None)
        if not cuts:
            return []
        poly = _host_outline_local_polygon(self)
        n = len(poly)
        if n < 2:
            return []
        # [2026-08-10 후속] 크기를 0.8배(다른 핸들보다 작음)에서 다른 핸들과 같은 표준 크기로
        # 키웠다 — 사용자 요청("마름모 점 크기를 다른 점만큼 키우던지, 일단 키워보고"). 테두리
        # 바깥으로 띄우는 건(다른 핸들처럼) 아직 보류 — 지금은 정확한 위치(패딩 없음)가 오히려
        # 장점이라는 사용자 관찰(2026-08-10)이 있어, 별도 결정 전까진 위치는 그대로 둔다.
        h = self._handle_px()
        out = []
        for ci, (edge_i, t0, t1) in enumerate(cuts):
            if not (0 <= edge_i < n):
                continue
            a, b = poly[edge_i], poly[(edge_i + 1) % n]
            for which, t in (("t0", t0), ("t1", t1)):
                p = QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
                out.append(((ci, which), QRectF(p.x() - h / 2, p.y() - h / 2, h, h)))
        return out

    def _apply_cut_drag(self, local_pt: QPointF):
        """[신규기능 2026-08-10] `_cut_drag`(cut_index, "t0"/"t1")가 가리키는 경계를 그 변을
        따라 `local_pt`의 투영 위치로 옮긴다 — 자기 자신의 반대쪽 경계(t1 또는 t0)를 넘어가지
        않도록 최소 간격(MIN_GAP)만 클램프한다(다른 cut과의 겹침은 `build_trimmed_border_path`
        가 렌더 시점에 이미 병합하므로 여기서 막을 필요 없음, §8 항목17 2단계 관례)."""
        ci, which = self._cut_drag
        cuts = getattr(self, "_cuts", None) or []
        if not (0 <= ci < len(cuts)):
            return
        poly = _host_outline_local_polygon(self)
        n = len(poly)
        edge_i, t0, t1 = cuts[ci]
        if not (0 <= edge_i < n):
            return
        a, b = poly[edge_i], poly[(edge_i + 1) % n]
        t, _perp = _seg_param_and_perp(a, b, local_pt)
        MIN_GAP = 0.01
        if which == "t0":
            t0 = max(0.0, min(t, t1 - MIN_GAP))
        else:
            t1 = min(1.0, max(t, t0 + MIN_GAP))
        cuts[ci] = (edge_i, t0, t1)
        self.update()

    def _commit_cut_drag_undo(self, before_cuts):
        h = self._host()
        after = list(getattr(self, "_cuts", None) or [])
        if h is not None and before_cuts != after:
            h.push_undo_cut(self, before_cuts)

    def _box_edge_tol(self) -> float:
        """`_box_edge_side`/`_box_edge_band_rects`가 공유하는 변 리사이즈 대역 반폭(로컬 단위,
        화면상 약 4px로 줌 무관 고정) — 하나만 고치면 커서 판정과 클릭 히트영역이 항상 같이
        움직이게 분리."""
        return max(self._EDGE_HIT_MIN / self._scale_or_1(), self._handle_px() * 0.5) / 2.0

    def _box_edge_band_rects(self):
        """[실사용 버그 수정 2026-08-11] `_box_edge_side`가 리사이즈 커서로 인식하는 변 대역과
        똑같은 4개 밴드(로컬좌표) — `shape()`에 포함시켜야 그 자리를 실제로 클릭했을 때도
        리사이즈가 발동한다. 이전엔 `shape()`가 모서리 핸들·회전 핸들만 포함하고 이 밴드는
        빠져 있어, 커서는 리사이즈로 바뀌는데 테두리 바깥쪽(밴드의 바깥 절반)을 클릭하면 Qt가
        이 도형을 히트로 안 잡아 캔버스 빈 공간을 누른 것처럼 새던 버그(선택 해제 등)."""
        r = self.rect()
        tol = self._box_edge_tol()
        return [
            QRectF(r.left() - tol, r.top() - tol, r.width() + 2 * tol, 2 * tol),
            QRectF(r.left() - tol, r.bottom() - tol, r.width() + 2 * tol, 2 * tol),
            QRectF(r.left() - tol, r.top() - tol, 2 * tol, r.height() + 2 * tol),
            QRectF(r.right() - tol, r.top() - tol, 2 * tol, r.height() + 2 * tol),
        ]

    def _box_edge_side(self, local_pt: QPointF):
        """local_pt가 (모서리·qc-dot과 안 겹치는) 테두리 변 위 리사이즈 대역이면 그 변
        ('t'/'r'/'b'/'l'), 아니면 None. [2026-08-03 실사용 지적, Lucid 대조] 변 전체를 잡아
        단일축 리사이즈할 수 있어야 하는데, 변 중점(qc-dot)은 화살표 전용이라 그 점 자체와는
        겹치지 않아야 한다 — 통합 흐름(`_update_hover_cursor`·뷰의 mousePressEvent)에선 qc-dot
        쪽이 이 검사보다 먼저 걸러지지만, 이 함수가 독립적으로도(단위 테스트 등) qc-dot 자리에
        대해 안전하도록 여기서도 명시적으로 제외한다."""
        if not (self._box_handles() and self._handle_active()):
            return None
        for _i, r in self._box_corner_rects():
            if r.contains(local_pt):
                return None
        for _k, dr in self._qc_dot_rects():
            if dr.contains(local_pt):
                return None
        r = self.rect()
        # [실사용 버그 수정 2026-08-09] `_EDGE_HIT_MIN`은 다른 세 호출부(1522·1574·1936줄,
        # 속 빈 도형 클릭 스트로크 폭)에서 전부 `/ self._scale_or_1()`로 화면 고정 px로
        # 환산해 쓰는데, 여기만 그 나눗셈이 빠져 있었다 — 고배율 줌에서 `_EDGE_HIT_MIN`(8.0)
        # 이 그대로 로컬 단위 tol이 되어, 화면상 밴드 폭이 줌에 비례해 커졌다(2164% 줌에서
        # 변 안쪽·바깥쪽 86px까지 리사이즈 커서, 사용자 스크린샷으로 실측). 나머지 세 곳과
        # 같은 관례로 맞춘다 — 이제 화면상 약 4px로 줌 무관 고정.
        tol = self._box_edge_tol()
        x, y = local_pt.x(), local_pt.y()
        if not (r.left() - tol <= x <= r.right() + tol and r.top() - tol <= y <= r.bottom() + tol):
            return None
        if abs(y - r.top()) <= tol and r.left() <= x <= r.right():
            return "t"
        if abs(y - r.bottom()) <= tol and r.left() <= x <= r.right():
            return "b"
        if abs(x - r.left()) <= tol and r.top() <= y <= r.bottom():
            return "l"
        if abs(x - r.right()) <= tol and r.top() <= y <= r.bottom():
            return "r"
        return None

    def _box_handle_cursor(self, local_pt: QPointF):
        """local_pt가 어느 박스 핸들 위인지 → 커서('rotate' or Qt.CursorShape), 없으면 None."""
        if not (self._box_handles() and self._handle_active()):
            return None
        if self._box_rot_rect().contains(local_pt):
            return "rotate"
        for i, r in self._box_corner_rects():
            if r.contains(local_pt):   # TL·BR = ↖↘, TR·BL = ↗↙
                return (Qt.CursorShape.SizeFDiagCursor if i in (0, 2)
                        else Qt.CursorShape.SizeBDiagCursor)
        # [신규기능 2026-08-10] TRIM 자국 경계 핸들 — 변 리사이즈 커서(아래)보다 먼저 검사
        # (mousePressEvent와 같은 우선순위). 이동/재스냅 성격이라 끝점 핸들과 같은 커서.
        for _key, r in self._cut_handle_rects():
            if r.contains(local_pt):
                return Qt.CursorShape.PointingHandCursor
        # 변 중점(qc-dot) 자체는 화살표 전용 빠른 생성 점 — 그 커서는 _update_hover_cursor의
        # _qc_dot_at 분기가 CrossCursor로 먼저 처리한다(이 함수엔 도달 안 함).
        side = self._box_edge_side(local_pt)
        if side is not None:
            return Qt.CursorShape.SizeVerCursor if side in ("t", "b") else Qt.CursorShape.SizeHorCursor
        return None

    def _host(self):
        sc = self.scene()
        if sc is not None and sc.views():
            return getattr(sc.views()[0], "_owner", None)
        return None

    def _begin_box_geom(self):
        """박스 리사이즈·회전 시작 — 원본 rect + undo 스냅샷(자신+부착 화살표) 확보."""
        self._box_orig_rect = QRectF(self.rect())
        self._box_bound = _collect_bound_arrows(self.scene(), [self])
        self._box_snap = [(it, it.capture_geom())
                          for it in _snapshot_set([self], self._box_bound)]

    def _set_box_rect(self, new_rect: QRectF):
        """rect 교체 + 부착 화살표 부착점을 '상대 위치 유지'로 재매핑 후 추종(reroute)."""
        old = self.rect()
        ow = old.width() if abs(old.width()) > 1e-6 else 1.0
        oh = old.height() if abs(old.height()) > 1e-6 else 1.0
        for arrow, idx, sh in (self._box_bound or []):
            bp = arrow._bind_pt(idx)
            if bp is None:
                continue
            relx = (bp.x() - old.left()) / ow
            rely = (bp.y() - old.top()) / oh
            arrow.set_bound(idx, sh, QPointF(new_rect.left() + relx * new_rect.width(),
                                             new_rect.top() + rely * new_rect.height()))
        self.prepareGeometryChange()
        self.setRect(new_rect)
        for arrow, idx, sh in (self._box_bound or []):
            arrow.reroute(pin_pred=lambda i: True)

    def _grid_snap_local(self, lp: QPointF) -> QPointF:
        """[그리드 스냅] 로컬 좌표를 씬 격자 교차점에 스냅 — mapToScene/mapFromScene로 아이템의
        회전·스케일 변환을 그대로 통과시켜, 회전된 도형이라도 실제 씬 위치가 격자에 맞는다.
        owner.grid_enabled가 False면 원본 그대로.
        [실사용 요청 2026-08-03] 포트(호스트에 부착된 작은 사각/원)는 제외 — 포트 크기가 보통
        그리드 간격과 비슷하거나 작아, 격자에 맞추면 한 칸 단위로만 뛰어 미세조정이 안 됐다."""
        if getattr(self, "_port_host", None) is not None:
            return lp
        sc = self.scene()
        if sc is None or not sc.views():
            return lp
        owner = getattr(sc.views()[0], "_owner", None)
        if owner is None or not getattr(owner, "grid_enabled", True):
            return lp
        scene_pt = self.mapToScene(lp)
        sp = _GRID_SPACING
        snapped = QPointF(round(scene_pt.x() / sp) * sp, round(scene_pt.y() / sp) * sp)
        return self.mapFromScene(snapped)

    def _apply_box_resize(self, lp: QPointF, shift: bool = False):
        lp = self._grid_snap_local(lp)   # [그리드 스냅] 코너/변 리사이즈 — 스마트정렬은 리사이즈 중 원래 꺼짐
        o = self._box_orig_rect
        kind, key = self._box_resize
        if kind == "corner":
            opp = [o.bottomRight(), o.bottomLeft(), o.topLeft(), o.topRight()][key]  # 대각 고정
            new = QRectF(opp, lp).normalized()
        else:
            left, top, right, bot = o.left(), o.top(), o.right(), o.bottom()
            if key == "l":
                left = lp.x()
            elif key == "r":
                right = lp.x()
            elif key == "t":
                top = lp.y()
            else:
                bot = lp.y()
            new = QRectF(QPointF(left, top), QPointF(right, bot)).normalized()
        MIN = 3.0
        if new.width() < MIN or new.height() < MIN:
            new = QRectF(new.x(), new.y(), max(new.width(), MIN), max(new.height(), MIN))
        new = self._constrain_box_rect(new, kind, key, shift)
        self._set_box_rect(new)

    def _constrain_box_rect(self, new: QRectF, kind: str, key, shift: bool = False) -> QRectF:
        """박스 리사이즈 결과 rect 후처리 훅. [실사용 요청 2026-08-03] 기본은 Shift를 누른 채
        꼭짓점을 끌 때만(변 리사이즈는 원래 늘림 의도라 제외) 리사이즈 시작 시점의 종횡비를
        유지 — 포트를 포함한 모든 도형(사각형·원·삼각형 등)에 공통 적용. _ImageItem은 사진
        왜곡 방지를 위해 Shift 여부와 무관하게 항상 고정(override, 기존 동작 그대로 유지).
        [실사용 요청 2026-08-03 2차] 포트는 이 기본을 뒤집는다 — 꼭짓점 핸들이 기본값으로
        비율유지이고, Shift를 누르면 오히려 잠금을 풀어 자유 리사이즈한다(변 핸들은 원래부터
        축별 개별 조정이라 그대로 둠 — kind!="corner"는 항상 통과). `shift == is_port`일 때만
        건너뛰므로 XOR 관계: 일반 도형은 shift일 때만 잠금, 포트는 shift가 아닐 때만 잠금."""
        is_port = getattr(self, "_port_host", None) is not None
        if kind != "corner" or shift == is_port:
            return new
        o = self._box_orig_rect
        oh = o.height() if abs(o.height()) > 1e-6 else 1.0
        asp = o.width() / oh
        opp = [o.bottomRight(), o.bottomLeft(), o.topLeft(), o.topRight()][key]
        w = max(new.width(), new.height() * asp)
        h = w / asp
        sx = 1.0 if key in (1, 2) else -1.0   # TR·BR = 오른쪽, TL·BL = 왼쪽
        sy = 1.0 if key in (2, 3) else -1.0   # BR·BL = 아래,   TL·TR = 위
        return QRectF(opp, QPointF(opp.x() + sx * w, opp.y() + sy * h)).normalized()

    def _owner_tool(self):
        """현재 활성 도구를 뷰→owner 경로로 조회(없으면 None)."""
        sc = self.scene()
        if sc is not None and sc.views():
            owner = getattr(sc.views()[0], "_owner", None)
            if owner is not None:
                return getattr(owner, "current_tool", None)
        return None

    def _owner_ortho(self) -> bool:
        """[우리 확장] F8 Ortho 활성 여부를 뷰→owner로 조회(정점 드래그 0/90° 제약용)."""
        sc = self.scene()
        if sc is not None and sc.views():
            owner = getattr(sc.views()[0], "_owner", None)
            if owner is not None:
                return bool(getattr(owner, "ortho_enabled", False))
        return False

    # ---- [우리 확장 · M4-4 ⓓ] 도형의 '내부 빈공간' 클릭·이동 --------------------
    # 속 빈 도형은 테두리(_base_shape)만 클릭 영역이라 선택·이동하려면 가는 선을 조준해야
    # 했다. Lucid/FigJam은 선택 여부와 무관하게 내부 아무 데나 클릭·끌어도 선택/이동된다
    # (2026-08-03 실사용 지적 — 선택 중에만 얹던 것을 미선택으로 확장). ⚠ 그리기 도구가
    # 무장된 동안은 얹지 않는다 — 뷰의 _is_empty_area가 shape()로 판정하므로, 얹으면
    # '도형 안에서 새 주석 그리기'(기존 설계)가 막힌다. 이 게이트는 도구 하나로 충분하다.
    _INTERIOR_HIT_TOOLS = (None, "select")

    def _interior_path(self):
        """클릭 영역에 더할 내부 채움 경로. 속 빈 네모·원·심볼만 override(기본 없음)."""
        return None

    def _interior_hit_active(self) -> bool:
        # 뷰(창)에 물린 적 없는 아이템은 "현재 도구"라는 개념 자체가 없다 — _owner_tool()이
        # 그 경우도 None을 돌려주는데, 이걸 '손 도구(None)'와 같은 값으로 오인하면 씬 밖
        # 임시 아이템(예: fill 단위 테스트)까지 내부 히트가 켜져 버린다.
        sc = self.scene()
        if sc is None or not sc.views():
            return False
        return self._owner_tool() in self._INTERIOR_HIT_TOOLS

    def _handle_active(self) -> bool:
        if not self.isSelected():
            return False
        # 다중선택(그룹 변형) 중엔 개별 회전·크기 핸들을 감춘다 — 그룹 오버레이가 대신 변형.
        if self._group_active():
            return False
        # 선택돼 있으면 어떤 도구에서든 이동·회전·크기조절을 바로 할 수 있게 핸들을 띄운다
        # (선택 도구는 러버밴드 다중선택을 계속 담당). 도구 전환 없이 방금 그린 도형을 다듬기 위함.
        if isinstance(self, QGraphicsTextItem) and \
                self.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction:
            return False
        return True

    def _hover_handle_at(self, local_pt: QPointF):
        """[호버 강조] local_pt(로컬 좌표) 아래 핸들 키, 없으면 None. 뷰가 매 프레임 호출해
        _hover_handle에 저장 — 판정 rect는 기존 hit-test(_box_handle_cursor 등)와 동일 관례."""
        if not self._handle_active():
            return None
        if self._uses_endpoints():
            for i in self._handle_indices():
                if self._inflate_to_hit(self._endpoint_rect(i)).contains(local_pt):
                    return ("ep", i)
            return None
        if self._box_handles():
            if self._box_rot_rect().contains(local_pt):
                return ("rot", None)
            for i, r in self._box_corner_rects():
                if r.contains(local_pt):
                    return ("corner", i)
            if not self._qc_dots_hover_suppressed():
                for side, r in self._qc_dot_rects():
                    if r.contains(local_pt):
                        return ("qc", side)
            for key, r in self._cut_handle_rects():
                if self._inflate_to_hit(r).contains(local_pt):
                    return ("cut", key)
            return None
        if self._rot_handle_rect().contains(local_pt):
            return ("rot", None)
        if self._handle_local_rect().contains(local_pt):
            return ("scale", None)
        return None

    def _set_handle_paint(self, painter: QPainter, s: float, base_color, hovered: bool):
        """[호버 강조] 핸들 하나의 펜/브러시 세팅 — 평소=흰 테두리+색 채움, hover=색 테두리(굵게)+흰 채움
        (반전 강조, Figma류 hover 관례)."""
        if hovered:
            painter.setPen(QPen(QColor(base_color), 2.2 / s))
            painter.setBrush(QBrush(QColor("white")))
        else:
            painter.setPen(QPen(QColor("white"), 1.0 / s))
            painter.setBrush(QBrush(QColor(base_color)))

    def _paint_handle(self, painter: QPainter):
        if self._uses_endpoints():
            self._paint_endpoint_handles(painter)
            return
        if not self._handle_active():
            return
        s = self._scale_or_1()
        hv = self._hover_handle
        if self._box_handles():
            # [qc-dot 드래그 중 단순화 2026-08-01, Lucid 대조] 커넥터를 뽑는 동안은 꼭짓점
            # 리사이즈 사각·회전 점을 감추고 변 중점 점 4개만 남긴다 — 지금 하려는 동작(커넥터
            # 생성)과 무관한 핸들이 같이 떠 있으면 어수선하다는 사용자 지적. 드래그가 끝나면
            # (release) 다시 전부 보인다 — 이건 이 순간의 동작 힌트일 뿐 영구 상태가 아니다.
            if not self._qc_dragging_now():
                # [2c→2026-07-30] 꼭짓점 4 = 파란 사각(리사이즈 전용), 좌상단 회전 = 코랄 원.
                for i, r in self._box_corner_rects():
                    self._set_handle_paint(painter, s, _BLUE, hv == ("corner", i))
                    painter.drawRect(r)
                rh = self._handle_px() * 0.5
                self._set_handle_paint(painter, s, _PEACH, hv == ("rot", None))
                painter.drawEllipse(self._box_rot_center(), rh, rh)
            # [2d→2026-07-30 통합] 변 중점 겸용 점(리사이즈+커넥터) — 옅은 파란 원(흰 테두리).
            # 호버 시 뷰가 고스트 미리보기.
            # [신규기능 2026-08-13] 다른 도형을 호버 중이면 감춘다(_qc_dots_hover_suppressed).
            if not self._qc_dots_hover_suppressed():
                for k, dr in self._qc_dot_rects():
                    self._set_handle_paint(painter, s, QColor(90, 150, 235), hv == ("qc", k))
                    painter.drawEllipse(dr)
            # [신규기능 2026-08-10] TRIM 자국 경계 핸들 — 마름모(다이아몬드)로 사각(리사이즈)·
            # 원(qc-dot)과 확실히 구별하고, 색은 TRIM 미리보기(빨강 점선)와 같은 계열(_RED)로
            # "이건 잘린 자국과 관련된 점"이라는 의미를 잇는다.
            for key, cr in self._cut_handle_rects():
                self._set_handle_paint(painter, s, _RED, hv == ("cut", key))
                c = cr.center(); hw = cr.width() / 2.0
                diamond = QPolygonF([QPointF(c.x(), c.y() - hw), QPointF(c.x() + hw, c.y()),
                                     QPointF(c.x(), c.y() + hw), QPointF(c.x() - hw, c.y())])
                painter.drawPolygon(diamond)
            return
        # 회전 핸들 — 우상단 코너 안쪽 코랄 점(줄기 없음, 우하단 크기조절 점과 대칭)
        rc = self._rot_handle_center()
        rh = self._handle_px() * 0.5  # 반지름 — 지름이 크기조절 사각 변과 같게
        self._set_handle_paint(painter, s, _PEACH, hv == ("rot", None))
        painter.drawEllipse(rc, rh, rh)
        # 크기조절 핸들 — 우하단 파란 사각
        r = self._handle_local_rect()
        self._set_handle_paint(painter, s, _BLUE, hv == ("scale", None))
        painter.drawRect(r)

    def _paint_base(self, painter, option, widget):
        # Qt 기본 paint의 자동 선택 점선(회전 핸들까지 확장된 boundingRect 둘레)을 막고
        # 베이스 도형만 그린다. 선택 표시는 호출자가 직접 그린다.
        opt = QStyleOptionGraphicsItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, opt, widget)

    def _paint_base_no_select(self, painter, option, widget):
        # 베이스 + 선택 강조. 텍스트·(과거) 네모가 사용한다.
        self._paint_base(painter, option, widget)
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())

    # [선택 표시 통일 2026-08-01] 그동안 타입마다 제각각이었다 — 네모·원은 _content_rect
    # 기반 점선 박스(축정렬이라 회전·심볼류엔 안 맞음), 선/패스/화살표는 각자 커스텀
    # _paint_selection_outline(고정 +8px 패딩 밴드, 실제보다 훨씬 굵게 감쌈). 다중선택 시
    # 그룹 바운딩박스(_GroupTransform.paint, 동일 파란 점선)와도 스타일이 겹쳐 구분이 안 됐다
    # (사용자 실측 지적: Lucid 대조 스크린샷). Lucid 관례로 통일: 그룹 박스는 그대로 두고,
    # 개별 아이템은 실제 외곽선에 바깥쪽만 딱 맞는 실선(점선 아님) — 드래그 크로싱 미리보기
    # 강조선(_item_center_path/_highlight_band)과 완전히 같은 계산을 재사용해 일관성을 보장한다.
    # 이 기본 구현이 모든 서브클래스의 폴백이며, 개별 override는 전부 제거했다(중복 로직 흡수).
    def _paint_selection_outline(self, painter, scale):
        _paint_selection_highlight(painter, self, scale)

    # 기본 paint — 베이스 + (선택 시) 획 따라가는 outline + 핸들. _paint_selection_outline은
    # 위 기본 구현을 그대로 쓴다(과거엔 도형마다 override했으나 통일됨).
    # _LineItem·_PathItem이 byte-for-byte 동일하게 중복 정의하던 것을 흡수(2026-07-28 코드정리).
    def paint(self, painter, option, widget=None):
        self._paint_base(painter, option, widget)
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)

    def shape(self):
        # 선택 시 핸들 영역을 클릭 영역에 포함 — 속 빈 도형도 핸들을 잡을 수 있게.
        base = self._base_shape()
        # [우리 확장 · M4-4 ⓓ] 선택된 속 빈 도형은 '내부 빈공간'도 클릭 영역에 포함(Lucid/FigJam).
        if self._interior_hit_active():
            ip = self._interior_path()
            if ip is not None:
                base = base.united(ip)
        if self._uses_endpoints():
            if self._endpoint_active():
                hp = QPainterPath()
                for i in self._handle_indices():
                    hp.addRect(self._inflate_to_hit(self._endpoint_rect(i)))
                return base.united(hp)
            return base
        if self._handle_active():
            hp = QPainterPath()
            if self._box_handles():
                for _i, r in self._box_corner_rects():
                    hp.addRect(r)
                hp.addEllipse(self._box_rot_rect())
                for band in self._box_edge_band_rects():
                    hp.addRect(band)
            else:
                hp.addRect(self._handle_local_rect())
                hp.addEllipse(self._rot_handle_rect())
            return base.united(hp)
        return base

    def mousePressEvent(self, event):
        if self._uses_endpoints():
            if self._endpoint_active():
                for i in self._handle_indices():
                    if self._inflate_to_hit(self._endpoint_rect(i)).contains(event.pos()):
                        self._drag_endpoint = i
                        self._on_endpoint_drag_start(i)   # [Stage1] 수동 정점 드래그 → 자동 라우팅 해제 훅
                        event.accept()
                        return
            super().mousePressEvent(event)
            return
        if self._handle_active() and self._box_handles():
            # [2c] 네모·원: 회전(좌상단) → 꼭짓점 → 변 순으로 검사. setRect 자유 리사이즈.
            lp = event.pos()
            if self._box_rot_rect().contains(lp):
                self._rotating = True
                self.setTransformOriginPoint(self._content_rect().center())
                center = self.mapToScene(self._content_rect().center())
                self._press_angle = QLineF(center, event.scenePos()).angle()
                self._press_rot = self.rotation()
                self._begin_box_geom()   # 회전도 geom undo(기존 단일 핸들은 undo 없었음 — 개선)
                event.accept()
                return
            for i, r in self._box_corner_rects():
                if r.contains(lp):
                    self._box_resize = ("corner", i)
                    self._begin_box_geom()
                    event.accept()
                    return
            # [신규기능 2026-08-10] TRIM 자국 경계 핸들 — 변 리사이즈(아래 `_box_edge_side`)보다
            # 먼저 검사해야 한다(같은 변 위에 있어서 안 그러면 변 드래그가 먼저 가로챈다).
            for key, r in self._cut_handle_rects():
                if r.contains(lp):
                    self._cut_drag = key
                    self._cut_drag_before = list(self._cuts)
                    event.accept()
                    return
            # [2026-07-30] 변 중점(qc-dot 그 자체)은 더 이상 여기서 안 잡는다 — 뷰가 press를
            # 먼저 가로채(_qc_dot_at) 화살표 전용으로 처리한다(축 방향으로 당겨도 리사이즈
            # 아님, 2026-08-01 확정). [2026-08-03 실사용 지적] 그 점 '주변'(모서리·qc-dot과
            # 안 겹치는 변 나머지 구간)은 아직 아무 핸들도 없어 Lucid처럼 변 전체를 잡아
            # 단일축 리사이즈할 수 없었다 — `_apply_box_resize`의 "edge" 분기는 이미 있었지만
            # (과거 qc-dot 겸용 시절의 유산) 그걸 발동시킬 자리가 없었다. 여기서 새로 연결한다.
            side = self._box_edge_side(lp)
            if side is not None:
                self._box_resize = ("edge", side)
                self._begin_box_geom()
                event.accept()
                return
            super().mousePressEvent(event)
            return
        if self._handle_active():
            # 회전 핸들이 바깥쪽이라 먼저 검사한다.
            if self._rot_handle_rect().contains(event.pos()):
                self._rotating = True
                self.setTransformOriginPoint(self._content_rect().center())
                center = self.mapToScene(self._content_rect().center())
                self._press_angle = QLineF(center, event.scenePos()).angle()
                self._press_rot = self.rotation()
                event.accept()
                return
            if self._handle_local_rect().contains(event.pos()):
                self._resizing = True
                self.setTransformOriginPoint(self._content_rect().center())
                center = self.mapToScene(self._content_rect().center())
                d = QLineF(center, event.scenePos()).length()
                self._press_dist = d if d > 1 else 1.0
                self._press_scale = self._scale_or_1()
                event.accept()
                return
        super().mousePressEvent(event)

    def _resolve_drag_endpoint(self):
        """press 시점에 캡처한 끝점 인덱스(0 또는 그때의 마지막 인덱스)를 '지금 프레임'의 실제
        유효 인덱스로 보정. [실사용 크래시 2026-07-29] 끝점 드래그가 매 프레임 _apply_routing()
        으로 경로 전체를 다시 계산하게 되면서(재부착 시 특히) _pts 길이 자체가 프레임마다
        바뀔 수 있게 됐다 — press 시점 값을 그대로 쓰면 길이가 줄어든 다음 프레임에서
        IndexError로 크래시한다(실사용자 보고: 화살표 머리를 다른 도형에 재부착하는 도중
        드래그가 끊기고, 그 뒤 다시 클릭하면 프로그램이 꺼짐 — 끊긴 순간이 이 IndexError고,
        `_drag_endpoint`가 None으로 정리되지 못한 채 남아 다음 클릭에서도 stale 인덱스로
        재차 크래시했다). `_handle_indices()`는 항상 {0, 마지막}만 내놓으므로 "0이었나"만
        기억하면 충분 — 0이 아니면 항상 '지금의' 마지막 인덱스로 재계산한다. `_endpoints()`를
        쓰는 이유(self._pts 대신): `_ArrowItem`은 `_pts`가 아니라 `_p1`/`_p2`를 쓰므로, 두
        클래스 모두에서 옳게 동작하려면 폴리모픽한 `_endpoints()`(길이 2 보장)를 봐야 한다."""
        return 0 if self._drag_endpoint == 0 else len(self._endpoints()) - 1

    def mouseMoveEvent(self, event):
        if getattr(self, "_cut_drag", None) is not None:
            self._apply_cut_drag(event.pos())
            event.accept()
            return
        if getattr(self, "_drag_endpoint", None) is not None:
            self.prepareGeometryChange()  # 끝점이 boundingRect를 바꾼다
            idx = self._resolve_drag_endpoint()
            p = event.pos()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift = 각도 스냅(테두리 스냅과 상호배타) — 위치는 이 제약이 갖되, 바인딩은 갱신.
                p2 = self._snap_endpoint(idx, p)
                self._set_endpoint(idx, p2)
                self._rebind_at_fixed_point(idx, p2)
            elif self._owner_ortho():
                # [우리 확장] F8 Ortho = 인접 정점 기준 0/90° 제약(테두리 스냅보다 우선) — 동일하게
                # 위치는 유지하고 바인딩만 재판정(실조건 2026-07-27: 안 하면 지속 연결이 안 걸림).
                p2 = self._ortho_endpoint(idx, p)
                self._set_endpoint(idx, p2)
                self._rebind_at_fixed_point(idx, p2)
            else:
                # 근처 도형 테두리에 재스냅(뗐다 다시 붙이기). 화살표는 S자 곡선까지 복원.
                self._move_endpoint_with_snap(idx, p)
            self.update()
            event.accept()
            return
        if self._box_resize is not None:   # [2c] 네모·원 자유 리사이즈(setRect)
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._apply_box_resize(event.pos(), shift)   # [실사용 요청] Shift=종횡비 유지(코너만)
            event.accept()
            return
        if getattr(self, "_rotating", False):
            center = self.mapToScene(self._content_rect().center())
            cur = QLineF(center, event.scenePos()).angle()
            # QLineF.angle()은 반시계(+)·setRotation은 시계(+) → 부호 반전
            new_rot = self._press_rot - (cur - self._press_angle)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                new_rot = round(new_rot / 15.0) * 15.0  # 15° 스냅
            self.setRotation(new_rot % 360)
            event.accept()
            return
        if getattr(self, "_resizing", False):
            self.prepareGeometryChange()  # 회전 여유분이 scale 의존 → 경계 캐시 갱신
            center = self.mapToScene(self._content_rect().center())
            d = QLineF(center, event.scenePos()).length()
            new = self._press_scale * (d / self._press_dist)
            self.setScale(max(0.15, min(new, 25.0)))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, "_cut_drag", None) is not None:
            self._cut_drag = None
            before = self._cut_drag_before
            self._cut_drag_before = None
            if before is not None:
                self._commit_cut_drag_undo(before)
            event.accept()
            return
        if getattr(self, "_drag_endpoint", None) is not None:
            idx = self._resolve_drag_endpoint()   # 클리어 전에 '지금' 유효한 인덱스로 보정
            self._drag_endpoint = None
            self._on_endpoint_drag_end(idx)   # [경유지 힌트] 중간 정점 드래그 → 힌트 커밋(override)
            event.accept()
            return
        # [2c] 박스 리사이즈·회전 종료 — geom undo 커밋(자신+부착 화살표 통째 복원).
        if self._box_resize is not None or (self._rotating and self._box_handles()):
            self._box_resize = None
            self._rotating = False
            snap = self._box_snap
            self._box_snap = None
            self._box_bound = None
            self._box_orig_rect = None
            h = self._host()
            if snap and h is not None:
                h.push_undo_geom(snap)
            event.accept()
            return
        if getattr(self, "_rotating", False) or getattr(self, "_resizing", False):
            self._rotating = False
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# 그래픽스 아이템 (전부 믹스인으로 크기조절 지원)
# ---------------------------------------------------------------------------

def _item_center_path(it) -> QPainterPath:
    """[선택 표시 통일 2026-08-01] 아이템의 '패딩 없는' 로컬 원본 외곽선 — 개별 선택 강조와
    드래그 크로싱 미리보기가 공유한다(원래 뷰의 `_rb_highlight_outline`이던 것을 자유함수로
    승격해 아이템 자신의 paint()에서도 쓸 수 있게 함). 네모·원·심볼·패스·선은 각자 갖고 있는
    원본 기하를, 화살표류(전용 기하 접근자 없음)는 몸통 곡선/꺾은선+화살촉 폴리곤을 직접
    구성한다. 반경>0인 직각 화살표는 실제로 그려지는 둥근 버전을 쓴다.

    [실사용 지적 2026-08-10] 포트·cut이 있는 도형은 실제 렌더(`paint()`)가 이미
    `build_trimmed_border_path`(잘린 진짜 윤곽)를 쓰는데, 이 함수는 그걸 몰라 항상 안 잘린
    원본 경로를 돌려줬다 — 그 결과 선택할 때마다 이미 지워진 부분이 선택 강조선(단일 중심선·
    다중 밴드 둘 다 이 함수를 공유)에서 "유령처럼" 다시 나타나 보였다. 렌더와 같은 함수로
    통일해 선택 강조도 실제로 남아있는 부분만 따라가게 한다."""
    if isinstance(it, (_SymbolItem, QGraphicsEllipseItem, QGraphicsRectItem)) and \
            (getattr(it, "_ports", None) or getattr(it, "_cuts", None)):
        return build_trimmed_border_path(it)
    if isinstance(it, _SymbolItem):
        return it._sym_path()
    if isinstance(it, QGraphicsEllipseItem):
        p = QPainterPath(); p.addEllipse(it.rect()); return p
    if isinstance(it, QGraphicsRectItem):
        p = QPainterPath(); p.addRect(it.rect()); return p
    if isinstance(it, QGraphicsPathItem):
        return it.path()
    if isinstance(it, QGraphicsLineItem):
        ln = it.line()
        p = QPainterPath(); p.moveTo(ln.p1()); p.lineTo(ln.p2()); return p
    if isinstance(it, _PolyArrowItem):
        base = it._rounded_polyline_path() if it._corner_radius() > 0 else it._polyline_path()
        p = QPainterPath(base)
        p.addPolygon(QPolygonF(it._head_points()))
        return p
    if isinstance(it, _ArrowItem):
        p = QPainterPath()
        p.moveTo(it._p1)
        if it._ctrl1 is None:
            p.lineTo(it._p2)
        else:
            p.cubicTo(it._ctrl1, it._ctrl2, it._p2)
        p.addPolygon(QPolygonF(it._head_points()))
        return p
    return it._base_shape() if hasattr(it, "_base_shape") else it.shape()


def _expand_polygon(poly: QPolygonF, pad: float) -> QPolygonF:
    """[화살표 찌그러짐 수정 2026-08-01] 각 꼭짓점을 다각형 중심에서 바깥으로 `pad`만큼 밀어낸
    확대 다각형(모서리는 원본과 평행하지 않지만, 삼각형처럼 꼭짓점이 적은 볼록 다각형에서는
    '살짝 커진 같은 모양'으로 충분히 읽힌다) — 뾰족한 꼭짓점을 그대로 유지한다(라운딩 없음)."""
    pts = list(poly)
    if not pts:
        return poly
    cx = sum(p.x() for p in pts) / len(pts)
    cy = sum(p.y() for p in pts) / len(pts)
    out = []
    for p in pts:
        dx, dy = p.x() - cx, p.y() - cy
        d = math.hypot(dx, dy) or 1.0
        out.append(QPointF(p.x() + dx / d * pad, p.y() + dy / d * pad))
    return QPolygonF(out)


def _arrow_body_path(it) -> QPainterPath:
    """[화살표 찌그러짐 수정 2026-08-01] `_item_center_path`의 화살표 분기에서 화살촉 폴리곤을
    뺀 몸통(선/꺾은선)만 — 아래 `_highlight_band`가 몸통과 화살촉을 서로 다른 방식으로
    강조하기 위해 필요."""
    if isinstance(it, _PolyArrowItem):
        return it._rounded_polyline_path() if it._corner_radius() > 0 else it._polyline_path()
    p = QPainterPath()
    p.moveTo(it._p1)
    if it._ctrl1 is None:
        p.lineTo(it._p2)
    else:
        p.cubicTo(it._ctrl1, it._ctrl2, it._p2)
    return p


def _highlight_band_fast(it, extra_width: float = 3.0) -> QPainterPath | None:
    """[성능수정 2026-08-15, docs/perf_report_multiselect.md 병목 B/C] `_highlight_band`의
    사각형·원 경로는 `QPainterPathStroker.createStroke().simplified().subtracted()`(폴리곤
    불리언 연산, 도형당 수십µs — 다중선택·러버밴드 드래그에서 프레임당 선택개수만큼 반복돼
    누적)로 계산하지만, 결과 모양 자체는 순수 산술로 동일하게 만들 수 있다: RoundJoin 스트로크가
    사각형 모서리에 만드는 바깥쪽 둥근 부분은 반지름 band_w/2인 원호와 수학적으로 같으므로
    `addRoundedRect`(사각형)·`addEllipse`(타원) 표준 프리미티브로 대체 — 안쪽은 원본 경계
    그대로, 바깥쪽만 band_w/2 부풀린 뒤 `OddEvenFill`로 안쪽을 구멍으로 남긴다(불리언 연산 0회).
    포트·TRIM cut이 있으면(실제 외곽선이 단순 사각형/타원이 아님) 이 근사가 안 맞아 None을
    돌려주고, 호출자(`_highlight_band`)가 기존 정확한 방식으로 폴백한다.

    ⚠ **판정은 `isinstance`가 아니라 정확한 타입 화이트리스트다.** `_SymbolItem`(삼각형·마름모·
    원통·안테나 등 전부)이 `QGraphicsRectItem`을 **상속**하므로 `isinstance` 판정을 쓰면 심볼이
    이 경로로 새서 실제 모양 대신 사각형 밴드가 그려진다 — 이 커밋의 1차 구현이 정확히 그
    버그를 냈고, 오프스크린 렌더 대조로 잡았다(사각형·타원만 렌더해 본 자체검증은 못 잡았다).
    `_item_center_path`가 `_SymbolItem`을 `QGraphicsRectItem`보다 **먼저** 검사하는 것도 같은
    이유다. 블랙리스트(`and not isinstance(it, _SymbolItem)`)로 고치면 앞으로 추가되는 하위
    클래스가 같은 함정을 조용히 다시 밟으므로, 실제로 픽셀 대조까지 마친 두 타입만 화이트리스트에
    둔다 — 모르는 타입은 항상 정확한 기존 경로로 폴백(fail-safe). 나머지 사각형류
    (`_ImageItem`/`_TableItem`/`_TitleBlockItem`)는 문서당 몇 개뿐이라 성능 기여가 없어
    일부러 제외했다."""
    if type(it) is not _RectItem and type(it) is not _EllipseItem:
        return None
    if getattr(it, "_ports", None) or getattr(it, "_cuts", None):
        return None
    half = (max(it.pen().widthF(), 1.0) + extra_width) / 2.0
    r = it.rect()
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    if type(it) is _RectItem:
        # 사각형은 근사가 아니라 완전히 동일하다(픽셀 diff 0 확인) — 바깥 모서리의 RoundJoin
        # 원호 반지름이 정확히 half이고 안쪽은 원본 사각형 그대로다.
        path.addRoundedRect(r.adjusted(-half, -half, half, half), half, half)
        path.addRect(r)
    else:
        # ⚠ 타원만은 진짜 '근사'다 — 타원을 half만큼 바깥으로 오프셋한 곡선은 (원과 달리)
        # 타원이 아니다. 실측(면적 대칭차 기준): 원·보통 비율은 측정 노이즈 수준(~0.2%),
        # 400x40+펜2도 1.1%지만, 극단적으로 납작한 타원(400x20+펜10 = 5.2%,
        # 600x12+펜12 = 8.8%)에선 눈에 띌 수 있다. 밴드 반폭이 단축의 15%를 넘으면
        # 그 구간으로 보고 정확한 기존 경로로 폴백한다(비교 1회, 비용 0).
        if half > 0.15 * max(min(r.width(), r.height()), 1e-9):
            return None
        path.addEllipse(r.adjusted(-half, -half, half, half))
        path.addEllipse(r)
    return path


def _highlight_band(it, extra_width: float = 3.0) -> QPainterPath:
    """[선택 표시 통일 2026-08-01] 중심선을 도형 두께 비례 폭(pw+extra_width, 장면 단위)으로
    스트로크해 띠를 만들고, `band.subtracted(centerline)`로 안쪽 절반을 깎아 바깥쪽만 남긴다
    (Lucid 스타일). 네모·원·심볼처럼 centerline이 '닫힌'(채워진 영역이 있는) 경로면 안쪽이
    실제로 깎이고, 선·화살표 몸통처럼 '열린'(면적 0) 경로는 뺄 것이 없어 대칭 띠가 그대로
    유지된다 — 타입별 분기 없이 한 연산으로 둘 다 처리.
    [성능수정 2026-08-15] 먼저 `_highlight_band_fast`(불리언 연산 없는 산술 경로)를 시도 —
    성공하면(사각형·원, 포트/cut 없음) 그대로 반환, 실패하면(None) 아래 기존 방식으로 폴백.
    [화살표 찌그러짐 수정 2026-08-01, 실조건서 발견] 화살표(_ArrowItem/_PolyArrowItem)는 몸통과
    별개로 처리한다 — 화살촉(닫힌 삼각형)까지 몸통과 한 경로로 묶어 `QPainterPathStroker`로
    스트로크하면, RoundJoin이 삼각형의 뾰족한 꼭짓점(특히 tip)을 뭉툭한 혹으로 뭉개 실제
    화살촉과 어긋난 '찌그러진' 실루엣이 됐다(1차 수정에서 union만 추가했을 때 사용자가
    `python run.py` 스크린샷으로 지적). 해법: 몸통만 기존 방식대로 스트로크하고, 화살촉은
    스트로크 대신 `_expand_polygon`(꼭짓점을 중심에서 바깥으로 밀어냄, 라운딩 없음)으로 살짝
    키운 다각형을 그대로 union — 원래 화살촉과 같은 뾰족한 모양을 유지한 채 강조만 더한다.
    [찌그러짐 2차 수정 2026-08-01, 사용자 확대 재확인] 위 수정 후에도 tip이 여전히 뭉툭해
    보였다 — 몸통 경로가 tip까지 그대로 이어져, 그 끝의 RoundCap(반지름 (pw+extra)/2)이
    화살촉의 얇은 꼭짓점 폭보다 넓어 삼각형 옆으로 반원이 삐져나왔다(union으로도 안 가려짐).
    tip을 중심으로 그 반지름만큼의 원을 몸통 밴드에서 파내(subtract) 캡을 제거 — 그 자리는
    이미 확대된 화살촉이 덮으므로 시각적 손실 없이 삐져나온 반원만 사라진다."""
    fast = _highlight_band_fast(it, extra_width)
    if fast is not None:
        return fast
    if isinstance(it, (_ArrowItem, _PolyArrowItem)):
        pw = getattr(it, "_width", 1.0)
        band_w = max(pw, 1.0) + extra_width
        stroker = QPainterPathStroker()
        stroker.setWidth(band_w)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        body_band = stroker.createStroke(_arrow_body_path(it)).simplified()
        tip, _ang = it._tip_and_angle()
        cap_cut = QPainterPath()
        cap_cut.addEllipse(tip, band_w / 2.0 + 1.0, band_w / 2.0 + 1.0)
        body_band = body_band.subtracted(cap_cut)
        head = QPainterPath()
        head.addPolygon(_expand_polygon(QPolygonF(it._head_points()), extra_width))
        return body_band.united(head.simplified())
    centerline = _item_center_path(it)
    pw = it.pen().widthF() if hasattr(it, "pen") else getattr(it, "_width", 1.0)
    stroker = QPainterPathStroker()
    stroker.setWidth(max(pw, 1.0) + extra_width)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    band = stroker.createStroke(centerline).simplified()
    return band.subtracted(centerline)


def _selection_is_solo(it) -> bool:
    """[Lucid 대조 2026-08-03] 이 아이템이 지금 유일하게 선택된 아이템인지(다중선택 중 하나가
    아닌지). 씬이 없으면(테스트 등 고립 아이템) True로 취급 — 그런 맥락에선 항상 단일선택
    스타일을 기본으로 본다.
    [성능수정 2026-08-15, docs/perf_report_multiselect.md 병목 A] `scene().selectedItems()`
    는 Qt C++이 매 호출마다 선택된 아이템 전체 리스트를 새로 만들어 반환한다(O(선택수)) — 이게
    선택된 N개 각각의 paint()에서 불려 프레임당 O(N²)이 되던 게 다중선택 드래그 버벅임의
    핵심 원인이었다(실측: 200개 선택 시 10프레임에 selectedItems() 4192회, 115ms). `CanvasWindow`
    가 selectionChanged에서 갱신하는 `scene._sel_count_cache`(host_selection.py
    `_sync_selection_count_cache`)가 있으면 그걸 O(1)로 읽고, 없으면(다이얼로그 미리보기 등
    독립 QGraphicsScene) 기존처럼 직접 계산 — 정확성은 항상 보존, 캐시는 순수 가속."""
    sc = it.scene()
    if sc is None:
        return True
    cached = getattr(sc, "_sel_count_cache", None)
    if cached is not None:
        return cached <= 1
    return len(sc.selectedItems()) <= 1


def _drag_decor_suppressed(it) -> bool:
    """[성능계획 2-C(b), 2026-08-15] 지금 이 아이템의 **장식**(라벨·선택 밴드)을 그리지 말아야
    하는가 — 「드래그 중 + 다중선택」일 때만 참.

    결정 ⓐ(`docs/perf_plan_500_1000.md`): 누르고 있는 동안은 화면 품질을 과감히 낮추고 손을
    떼는 순간 정확히 복원한다. 1000개 전체선택 드래그 프로파일에서 라벨 페인트와 선택 밴드가
    각각 프레임당 1,000회씩 돌고 있었다.

    **다중선택 조건을 함께 거는 이유**: 도형 하나만 끌 때 그 라벨이 사라지면 눈에 띄게
    거슬리는데, 정작 비용은 거의 없다(움직인 것만 리페인트되므로). 비용이 실제로 터지는 건
    많은 아이템이 함께 움직이는 경우뿐이라, 이득이 있는 곳에서만 품질을 내준다.

    뷰는 `_interactive_view_cache`(`_view_zoom_factor`가 이미 관리하는 캐시)로 얻는다 —
    `scene().views()`는 호출마다 리스트를 새로 만들어 paint 핫패스에 두면 안 된다(이 세션에서
    `selectedItems()`로 같은 함정을 두 번 밟았다). 상태를 따로 저장하지 않고 매번 뷰에 직접
    물어보므로 stale이 구조적으로 불가능하다(드래그가 끝나면 다음 프레임에 바로 복원)."""
    sc = it.scene()
    if sc is None:
        return False
    if (getattr(sc, "_sel_top_count_cache", 0) or 0) < 2:
        return False
    v = getattr(sc, "_interactive_view_cache", None)
    if v is None:
        return False
    try:
        return bool(v.is_drag_session())
    except (RuntimeError, AttributeError):
        return False   # 뷰가 이미 삭제됐거나 이 뷰 종류엔 없는 개념 — 평소대로 그린다


def _paint_selection_centerline(painter: QPainter, it, scale: float = 1.0, path: QPainterPath | None = None):
    """[Lucid 대조 2026-08-03] 단일선택·화살표 전용 강조 — 바깥에 밴드를 두르는 대신 실제
    외곽선 중심에 얇은 선 하나. 다중선택(그룹 중 하나)일 때의 굵은 바깥 밴드보다 가늘어서
    "이것만 선택됨"이 한눈에 구분되고(사용자 실사용 지적: Lucid 대조), 화살표는 선택 개수와
    무관하게 항상 이 스타일이다 — 화살표 같은 '열린'(면적 0) 경로는 밴드가 안쪽을 깎아도
    중심선과 차이가 거의 없어 밴드를 쓸 이유가 없다.
    [실사용 지적 2026-08-03] 화살표는 `_item_center_path`가 아니라 `_arrow_body_path`를 쓴다 —
    전자는 화살촉을 '닫힌 다각형'으로 별도 추가해(밴드 계산엔 필요) 얇은 선으로 스트로크하면
    화살촉 윤곽을 따라 또 하나의 선이 겹쳐 보였다(꼬리~머리 한 가닥이어야 하는데 두 겹으로
    보임). `_arrow_body_path`는 몸통이 이미 tip(머리 끝점)까지 이어져 있어 화살촉 윤곽 없이
    꼬리부터 머리까지 선 하나로 끝난다(Lucid와 동일)."""
    if path is None:
        if isinstance(it, (_ArrowItem, _PolyArrowItem)):
            path = _arrow_body_path(it)
        else:
            path = _item_center_path(it)
    pen = QPen(QColor(_BLUE), 1.6 / (scale or 1.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def _paint_selection_highlight(painter: QPainter, it, scale: float = 1.0, band: QPainterPath | None = None):
    """[선택 표시 통일 2026-08-01 → 2026-08-03 Lucid 대조 갈래] 개별 아이템 선택 강조의 공통
    렌더. 화살표거나 단일선택이면 얇은 중심선(`_paint_selection_centerline`), 다중선택 중인
    도형(닫힌 도형만 해당)이면 기존 바깥 밴드 — 실제 외곽선에 바깥쪽만 딱 맞는 실선(점선
    아님). `_HandleResizeMixin._paint_selection_outline`이 기본으로 위임하고, 믹스인을 안 쓰는
    소수 클래스(`_TitleBlockItem`)는 직접 호출한다.
    [화살표 성능 2026-08-01] `band`를 이미 계산해 뒀으면(캐시) 그대로 받아 재사용 — 밴드를
    실제로 그릴 때만 의미가 있다(화살표는 이제 밴드 자체를 안 쓰므로 이 인자가 무시된다)."""
    # [성능계획 2-C(b)] 드래그 중 다중선택이면 개별 강조를 생략한다 — 어차피 그룹 변형
    # 오버레이(_GroupTransform)가 바운딩박스를 그려 "무엇이 선택됐나"는 계속 보인다.
    if _drag_decor_suppressed(it):
        return
    is_connector = isinstance(it, (_ArrowItem, _PolyArrowItem))
    if is_connector or _selection_is_solo(it):
        _paint_selection_centerline(painter, it, scale)
        return
    if band is None:
        band = _highlight_band(it)
    pen = QPen(QColor(_BLUE), 1.0 / (scale or 1.0))
    painter.setPen(pen)
    fill = QColor(_BLUE); fill.setAlpha(110)
    painter.setBrush(QBrush(fill))
    painter.drawPath(band)


def _font_px(painter, px: float, bold: bool = False):
    # 표제란·표가 동일하게 쓰던 static helper — 픽셀 단위 폰트 크기 지정(2026-07-28 코드정리).
    f = painter.font()
    f.setPixelSize(max(1, int(round(px))))
    f.setBold(bold)
    painter.setFont(f)


# ---------------------------------------------------------------------------
# [우리 확장] 라벨 믹스인 — 본체에 '부착'되어 함께 이동하는 자식 텍스트
#   _LabelMixin        : 공통 로직 + 선·화살표용 '중점 위쪽' 배치
#   _CenterLabelMixin  : 닫힌 도형(네모·원·심볼)용 '정중앙' 배치
# (도형 클래스보다 앞서야 상속 가능하므로 여기 둔다.)
# ---------------------------------------------------------------------------
class _LabelMixin:
    """더블클릭으로 다는 텍스트 라벨. 라벨은 자식(child _TextItem)이라 본체가 통째로
    이동하면 Qt가 자동으로 따라 옮기고, 로컬 기하가 바뀔 때만 _sync_label로 재배치한다.
    라벨은 부착 전용(독립 이동 불가). 기본 배치는 앵커 '위쪽'(선·화살표)."""

    def _init_label(self):
        self._label = None  # 자식 _TextItem or None

    def _label_anchor(self) -> QPointF:      # 하위 클래스 구현: 라벨을 붙일 로컬 기준점(중점)
        raise NotImplementedError

    def _label_color(self) -> QColor:        # 하위 클래스가 본체 색으로 override
        return QColor(_TEXT)

    def _label_alive(self) -> bool:
        lbl = getattr(self, "_label", None)
        return lbl is not None and lbl.scene() is not None

    def has_label(self) -> bool:
        return self._label_alive() and bool(self._label.toPlainText().strip())

    def _make_label(self):
        """라벨 아이템 생성(하위 클래스가 override 가능). 기본은 부착 전용 _TextItem."""
        return _TextItem(self._label_color())

    def ensure_label(self):
        """라벨이 없으면 생성해 중점에 부착하고 반환(있으면 그대로 반환)."""
        if not self._label_alive():
            lbl = self._make_label()
            lbl.setParentItem(self)
            # 부착 전용(편집·삭제는 가능, 단독 선택은 종류별로 갈림). 화살표(sarrow) 라벨은
            # _ConnectorLabel이라 드래그로 경로 위를 슬라이드하도록 선택+이동을 켠다(FigJam/Lucid)
            # — itemChange가 경로에 재투영.
            # [UX개선 2026-08-08] 도형 중앙 라벨(비-커넥터)은 플래그를 아예 안 준다 — Qt는
            # ItemIsSelectable/Movable이 둘 다 없는 아이템의 mousePressEvent를 기본적으로
            # ignore()해 그 아래(부모 도형)로 전파한다. 그래서 라벨 위를 한 번 클릭하면 라벨이
            # 아니라 도형 자체가 선택돼(실사용 피드백: "네모 안 텍스트가 별도로 선택될 필요가
            # 있나"), Lucid류처럼 "안은 이동 커서, 더블클릭해야 텍스트 편집"이 된다.
            # mouseDoubleClickEvent는 플래그와 무관하게 항상 hit-test로 이 라벨에 그대로 오므로
            # 더블클릭 진입은 그대로 동작(텍스트 편집 중엔 QGraphicsTextItem 내부 처리가 담당,
            # ItemIsSelectable과 무관).
            flags = QGraphicsItem.GraphicsItemFlag(0)
            if isinstance(lbl, _ConnectorLabel):
                # Movable=드래그, SendsGeometryChanges=itemChange(ItemPositionChange) 발화(경로 재투영에 필수).
                flags = (QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                          | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                          | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
            lbl.setFlags(flags)
            lbl.document().contentsChanged.connect(self._sync_label)  # 타이핑 중 중앙 유지
            self._label = lbl
        self._sync_label()
        return self._label

    def restore_label(self, d: dict):
        """문서 로드용 — 저장된 라벨(dict)을 자식으로 복원."""
        lbl = self.ensure_label()
        lbl.apply_font_size(d.get("font", 16))
        lbl.setPlainText(d.get("text", ""))
        lbl.apply_color(QColor(d.get("color", _TEXT)))
        if d.get("bg") is not None:
            lbl.set_bg(QColor(*d["bg"]))
        self._sync_label()
        return lbl

    def _sync_label(self):
        """라벨을 본체 중점 '위쪽'에 재배치. _content_rect(편집 프레임 여유 제외)을 써
        편집 중·완료 후 위치가 흔들리지 않게 한다."""
        if not self._label_alive():
            return
        a = self._label_anchor()
        br = self._label._content_rect()
        self._label.setPos(a.x() - br.width() / 2.0, a.y() - br.height() - 4.0)


# [우리 확장] 라벨 세로 광학정렬 — 글리프 '실제 잉크' 중심을 도형 중심에 맞춘다.
def _ink_center_dy(lbl) -> float:
    """라벨 글리프의 실제 잉크 세로중심이 문서박스 중심에서 벗어난 양(아래로 +).
    QGraphicsTextItem의 실렌더 글리프 배치가 baseline·폰트메트릭 추정과 어긋나(폰트·언어마다
    다름 — Malgun/폴백이 부호까지 반대), 어떤 공식으로도 못 맞춘다. 그래서 텍스트를 작은
    오프스크린에 그려 잉크를 픽셀로 직접 재 폰트·언어 무관하게 정확히 센터링한다.
    같은 (텍스트·폰트크기·여백)이면 캐시해 리사이즈 드래그 중 재계산을 피한다."""
    text = lbl.toPlainText()
    if not text.strip():
        return 0.0
    key = (text, round(lbl.font().pointSizeF(), 2), round(lbl.document().documentMargin(), 2))
    cached = getattr(lbl, "_ink_dy_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    br = lbl._content_rect()
    w = max(1, int(br.width()) + 2)
    h = max(1, int(br.height()) + 2)
    dy = 0.0
    if h > 2 and w > 2:
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            lbl.document().drawContents(p)   # 아이템 paint와 같은 문서 렌더 경로
        finally:
            p.end()
        top = bot = None
        for y in range(h):
            for x in range(w):
                if img.pixelColor(x, y).alpha() > 40:
                    if top is None:
                        top = y
                    bot = y
                    break
        if top is not None:
            dy = br.height() / 2.0 - (top + bot) / 2.0
    lbl._ink_dy_cache = (key, dy)
    return dy


class _CenterLabelMixin(_LabelMixin):
    """닫힌 도형(네모·원·심볼)용 라벨 — 선·화살표의 '중점 위쪽'과 달리 도형 '정중앙'에 놓고,
    rect가 바뀌면(그리기·박스 리사이즈·리베이크) 새 중앙으로 재동기한다. 앵커=rect 중심,
    색=테두리색. 셋이 공유해 중복을 없앤다. 세로는 문서박스가 아니라 글리프 '잉크' 중심을
    맞춘다(_ink_center_dy) — 폰트가 baseline 아래로 여유를 더 둬 글자가 위로 쏠려 보이는 것 교정."""

    def _label_anchor(self) -> QPointF:
        return self.rect().center()

    def _label_color(self) -> QColor:
        return QColor(self.pen().color())

    def _label_inset_ratio(self) -> float:
        """라벨이 들어갈 도형 내접 가용폭(도형폭 대비 비율). 이 폭을 넘기면 폰트를 축소해
        긴 텍스트가 빗변/곡선 밖으로 삐져나오지 않게 한다. 하위 클래스가 도형별로 override."""
        return 0.85

    _LABEL_MIN_PT = 5   # 축소 하한(이하로는 안 줄임 — 너무 작으면 차라리 도형을 키우는 게 답)

    def _fit_label_to_shape(self):
        """[우리 확장] 중앙 라벨을 도형 내접폭에 맞춰 '폰트 축소'로 맞춘다(단일 줄 유지, 줄바꿈 안 함).
        · 줄바꿈(wrap)은 마름모에서 줄 수가 폭발해 세로로 삐져나오는 결함이 있어 배제(실측). 폰트 축소는
          폭·세로를 동시에 보장한다. · 기준은 사용자 크기(_base_pt) — 도형이 커지면 그 값까지 되키운다.
        · 폭 측정은 _content_rect(문서 레이아웃)이 아니라 QFontMetricsF로 직접 한다 — contentsChanged
          콜백 시점엔 문서 레이아웃이 미완이라 _content_rect 폭이 stale이기 때문(실측). 멱등.
        · setFont이 contentsChanged를 재발화해 _sync_label→_fit이 재진입하면 서로의 폰트를 덮어써
          비결정적이 되므로 _fitting 가드로 재진입을 막는다(바깥 호출의 setFont 결과가 확정으로 남음)."""
        if getattr(self, "_fitting", False):
            return
        lbl = self._label
        self._fitting = True
        try:
            self._fit_label_impl(lbl)
        finally:
            self._fitting = False

    def _fit_label_impl(self, lbl):
        lbl.setTextWidth(-1)   # 단일 줄(폭은 폰트 축소로 맞춤)
        base = max(self._LABEL_MIN_PT, int(getattr(lbl, "_base_pt", lbl.font().pointSize() or 16)))
        margin = 2 * lbl.document().documentMargin()
        inner = max(1.0, self.rect().width() * self._label_inset_ratio())
        lines = lbl.toPlainText().split("\n") or [""]
        f = QFont(lbl.font())
        pt = base
        while pt > self._LABEL_MIN_PT:
            f.setPointSize(pt)
            fm = QFontMetricsF(f)
            widest = max((fm.horizontalAdvance(ln) for ln in lines), default=0.0)
            if widest + margin <= inner:
                break
            pt -= 1
        if lbl.font().pointSize() != pt:
            f2 = lbl.font()
            f2.setPointSize(pt)
            lbl.setFont(f2)

    def _sync_label(self):
        if not self._label_alive():
            return
        self._fit_label_to_shape()   # [우리 확장] 도형 내접폭에 맞춰 폰트 축소(넘침 방지)
        a = self._label_anchor()
        br = self._label._content_rect()
        dy = _ink_center_dy(self._label)
        self._label.setPos(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0 + dy)

    def setRect(self, *args):
        # rect가 바뀌면(그리기·박스 리사이즈·리베이크) 라벨을 새 중앙으로 재배치.
        super().setRect(*args)
        if self._label_alive():
            self._sync_label()
        self._sync_ports()

    def _sync_ports(self):
        """[신규기능 §8-12] 이 도형에 부착된 포트(작은 사각/원 자식)를 rect 변경 후 재배치.
        포트는 부착 시점의 '테두리 위 상대 위치'를 (fx, fy)(rect 폭·높이 대비 비율)로
        저장해 두므로, rect가 커지거나 작아져도 같은 상대 위치(변 중점·꼭짓점 등)를 유지한다
        — 사각형·삼각형(경로가 rect의 선형 함수인 심볼) 둘 다에서 성립."""
        ports = getattr(self, "_ports", None)
        if not ports:
            return
        for port in ports:
            _reposition_port_from_frac(port)


class _RectGeometryMixin:
    """rect 기반 도형(네모·원·심볼·이미지·표) 공용 [Stage2/2b] 기하 — 네 모서리를 씬변형 후
    로컬 AABB로 setRect(회전=0면 정확). _HandleResizeMixin의 스칼라 폴백(_capture_geom_local 등
    None/pass, _stretch_grips는 중심점 1개)을 rect 전용으로 override — 다섯 클래스가 byte-for-byte
    동일하게 중복 정의하던 것을 여기로 흡수(2026-07-28 코드정리)."""

    def _capture_geom_local(self):
        return QRectF(self.rect())

    def _apply_geom_local(self, g):
        self.setRect(g)

    def rebake_scene(self, fn):
        r = self.rect()
        pts = [self._rebake_pt(fn, c) for c in
               (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        self.prepareGeometryChange()
        self.setRect(QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))))

    def _stretch_grips(self):   # [Stage2b] grip = 네 모서리(걸친 모서리만 stretch 이동).
        r = self.rect()
        return [self.mapToScene(c) for c in
                (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]

    def _fill_path(self) -> QPainterPath:
        # [§8 항목17 2단계] cut 렌더(_paint_filled_trimmed_border)가 채움에 쓰는 닫힌 경로 —
        # 기본은 사각형. 타원·심볼은 자기 실제 외곽선으로 override(마름모 등에 뜬 채움이
        # bbox까지 번지지 않게).
        p = QPainterPath()
        p.addRect(self.rect())
        return p


class _RectItem(_CenterLabelMixin, _RectGeometryMixin, _HandleResizeMixin, QGraphicsRectItem):
    def __init__(self, *args):
        super().__init__(*args)
        self._init_resize()
        self._init_label()

    def clone(self):
        c = _RectItem(QRectF(self.rect()))
        c.setPen(QPen(self.pen()))
        c.setBrush(QBrush(self.brush()))
        return self._copy_common_to(c)

    def apply_fill(self, color):
        """[신규기능 · 도형 채우기] color=None이면 투명(NoBrush), 아니면 그 색으로 채움.
        rect/ellipse/symbol 세 클래스에만 명시적으로 둔다(이미지·표는 paint가 brush를 안 써서
        무의미하므로 믹스인에 안 얹음)."""
        self.prepareGeometryChange()   # 채움 유무가 _base_shape/_interior_path(클릭 영역)를 바꾼다
        self.setBrush(QBrush(QColor(color)) if color is not None else QBrush(Qt.BrushStyle.NoBrush))
        self.update()

    def _base_shape(self):
        # 속 빈 네모(NoBrush)는 '테두리 링'만 클릭 영역으로 — 내부를 통과시켜 네모 안에서
        # 다른 주석을 잡거나 새 도형(화살표 등)을 그릴 수 있게. 채움이 있으면 기본대로 전체.
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return super()._base_shape()
        path = QPainterPath()
        path.addRect(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), self._EDGE_HIT_MIN / self._scale_or_1()))
        return stroker.createStroke(path)

    def _interior_path(self):
        # [M4-4 ⓓ] 속 빈 네모의 내부(선택 중에만 shape()가 얹는다). 채움이 있으면 이미 포함.
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return None
        p = QPainterPath()
        p.addRect(self.rect())
        return p

    def paint(self, painter, option, widget=None):
        # [§8 항목17 7단계, 2026-08-10] 포트도 TRIM cut과 같은 렌더 경로(_paint_filled_
        # trimmed_border, build_trimmed_border_path가 _ports·_cuts 둘 다 이미 병합해 읽음)를
        # 탄다 — 옛 _paint_port_cover_if_needed(배경색 덮어그리기)는 폐지.
        if getattr(self, "_ports", None) or getattr(self, "_cuts", None):
            _paint_filled_trimmed_border(self, painter)
            if self.isSelected():
                self._paint_selection_outline(painter, self._scale_or_1())
        else:
            self._paint_base_no_select(painter, option, widget)
        self._paint_handle(painter)


class _EllipseItem(_CenterLabelMixin, _RectGeometryMixin, _HandleResizeMixin, QGraphicsEllipseItem):
    def __init__(self, *args):
        super().__init__(*args)
        self._init_resize()
        self._init_label()

    def _label_inset_ratio(self) -> float:
        return 0.72   # 타원은 세로중앙에서만 최대폭이라 네모보다 좁게 잡아 줄바꿈

    def clone(self):
        c = _EllipseItem(QRectF(self.rect()))
        c.setPen(QPen(self.pen()))
        c.setBrush(QBrush(self.brush()))
        return self._copy_common_to(c)

    def apply_fill(self, color):
        """[신규기능 · 도형 채우기] _RectItem.apply_fill과 동일 — 클래스별 명시 opt-in."""
        self.prepareGeometryChange()
        self.setBrush(QBrush(QColor(color)) if color is not None else QBrush(Qt.BrushStyle.NoBrush))
        self.update()

    def _content_rect(self):
        # _LineItem과 동일 사이클 방지: QGraphicsEllipseItem.boundingRect()는 펜 두께가
        # 0이 아니면 shape()를 호출하므로, 사각형 기하에서 직접 계산해 재귀를 끊는다.
        extra = self.pen().widthF() / 2.0 + 1.0
        return self.rect().adjusted(-extra, -extra, extra, extra)

    def _base_shape(self):
        # 속 빈 원(NoBrush)은 '테두리 링'만 클릭 영역으로(네모와 동일). QGraphicsEllipseItem
        # 기본 shape()는 boundingRect()를 부르지 않고 rect에서 직접 만드므로 재귀 없음.
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return super()._base_shape()
        path = QPainterPath()
        path.addEllipse(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), self._EDGE_HIT_MIN / self._scale_or_1()))
        return stroker.createStroke(path)

    def _interior_path(self):
        # [M4-4 ⓓ] 속 빈 원의 내부(선택 중에만). 곡선 기하 그대로 — 외접 박스 아님.
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return None
        p = QPainterPath()
        p.addEllipse(self.rect())
        return p

    def _fill_path(self) -> QPainterPath:
        # [§8 항목17 2단계] _RectGeometryMixin 기본(사각형) override — 채움이 실제 타원 모양.
        p = QPainterPath()
        p.addEllipse(self.rect())
        return p

    def paint(self, painter, option, widget=None):
        # [§8 항목17 7단계] _RectItem과 같은 이유로 포트도 이 경로를 탄다(옛 배경색 덮어
        # 그리기 폐지).
        if getattr(self, "_ports", None) or getattr(self, "_cuts", None):
            _paint_filled_trimmed_border(self, painter)
        else:
            self._paint_base(painter, option, widget)
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)


# ---------------------------------------------------------------------------
# [우리 확장] 심볼/스텐실 — 순서도 표준 도형(판단·입출력·준비 등)
# ---------------------------------------------------------------------------
# 설계: 종류마다 클래스를 만들지 않고 단일 _SymbolItem(rect 기반)에 kind만 달리한다.
# rect 기반이라 _RectItem이 쓰는 기계(_box_handles 리사이즈·회전·stretch·geom undo)를
# 그대로 물려받고, paint/shape만 kind별 경로로 갈아끼운다. 경로 팩토리는 QRectF→QPainterPath.
def _sym_decision(r: QRectF) -> QPainterPath:      # 판단 — 마름모
    p = QPainterPath()
    c = r.center()
    p.moveTo(c.x(), r.top())
    p.lineTo(r.right(), c.y())
    p.lineTo(c.x(), r.bottom())
    p.lineTo(r.left(), c.y())
    p.closeSubpath()
    return p


def _sym_terminal(r: QRectF) -> QPainterPath:      # 시작/끝 — 스타디움(둥근 양끝)
    p = QPainterPath()
    rad = min(r.width(), r.height()) / 2.0
    p.addRoundedRect(r, rad, rad)
    return p


def _sym_data(r: QRectF) -> QPainterPath:          # 입출력 — 평행사변형
    p = QPainterPath()
    dx = r.width() * 0.22
    p.moveTo(r.left() + dx, r.top())
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right() - dx, r.bottom())
    p.lineTo(r.left(), r.bottom())
    p.closeSubpath()
    return p


def _sym_prep(r: QRectF) -> QPainterPath:          # 준비 — 육각형
    p = QPainterPath()
    dx = r.width() * 0.2
    cy = r.center().y()
    p.moveTo(r.left() + dx, r.top())
    p.lineTo(r.right() - dx, r.top())
    p.lineTo(r.right(), cy)
    p.lineTo(r.right() - dx, r.bottom())
    p.lineTo(r.left() + dx, r.bottom())
    p.lineTo(r.left(), cy)
    p.closeSubpath()
    return p


def _sym_document(r: QRectF) -> QPainterPath:      # 문서 — 아래 물결
    p = QPainterPath()
    wave = r.height() * 0.14
    p.moveTo(r.left(), r.top())
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right(), r.bottom() - wave)
    p.cubicTo(r.right() - r.width() * 0.25, r.bottom() - wave * 3.0,
              r.left() + r.width() * 0.25, r.bottom() + wave,
              r.left(), r.bottom() - wave)
    p.closeSubpath()
    return p


def _sym_database(r: QRectF) -> QPainterPath:      # 저장소 — 원기둥
    p = QPainterPath()
    e = min(r.height() * 0.18, r.width() * 0.5)   # 윗/아랫 타원 반높이
    top = QRectF(r.left(), r.top(), r.width(), 2 * e)
    bot = QRectF(r.left(), r.bottom() - 2 * e, r.width(), 2 * e)
    p.addEllipse(top)                              # 윗면 타원(완전)
    p.moveTo(r.left(), r.top() + e)                # 몸통 왼쪽
    p.lineTo(r.left(), r.bottom() - e)
    p.arcTo(bot, 180.0, 180.0)                     # 아랫면 앞쪽 반원
    p.lineTo(r.right(), r.top() + e)               # 몸통 오른쪽
    return p


def _sym_manual_input(r: QRectF) -> QPainterPath:  # 수동입력 — 왼쪽이 낮은 사선 윗변
    p = QPainterPath()
    slant = r.height() * 0.22
    p.moveTo(r.left(), r.top() + slant)
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right(), r.bottom())
    p.lineTo(r.left(), r.bottom())
    p.closeSubpath()
    return p


def _sym_manual_op(r: QRectF) -> QPainterPath:     # 수동작업 — 역사다리꼴(아래가 좁음)
    p = QPainterPath()
    dx = r.width() * 0.18
    p.moveTo(r.left(), r.top())
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right() - dx, r.bottom())
    p.lineTo(r.left() + dx, r.bottom())
    p.closeSubpath()
    return p


def _sym_display(r: QRectF) -> QPainterPath:       # 화면출력 — 위아래 평평·우측 볼록·좌측 오목
    # 스타디움(terminal)과 헷갈리지 않도록 좌우를 비대칭으로: 왼쪽은 안으로 파인 오목 곡선(quadTo
    # 제어점이 도형 안쪽), 오른쪽만 화면 브라운관처럼 둥글게 볼록(cubicTo).
    p = QPainterPath()
    w, h = r.width(), r.height()
    cy = r.center().y()
    flat_x = r.left() + w * 0.6
    p.moveTo(r.left(), r.top())
    p.lineTo(flat_x, r.top())
    p.cubicTo(r.left() + w * 0.86, r.top(),
              r.right(), r.top() + h * 0.2,
              r.right(), cy)
    p.cubicTo(r.right(), r.bottom() - h * 0.2,
              r.left() + w * 0.86, r.bottom(),
              flat_x, r.bottom())
    p.lineTo(r.left(), r.bottom())
    p.quadTo(r.left() + w * 0.18, cy, r.left(), r.top())
    p.closeSubpath()
    return p


def _sym_delay(r: QRectF) -> QPainterPath:         # 지연 — 오른쪽 반원(D자형)
    p = QPainterPath()
    w, h = r.width(), r.height()
    straight_x = r.left() + w * 0.62
    radius = h / 2.0
    p.moveTo(r.left(), r.top())
    p.lineTo(straight_x, r.top())
    p.arcTo(QRectF(straight_x - radius, r.top(), 2 * radius, h), 90.0, -180.0)
    p.lineTo(r.left(), r.bottom())
    p.closeSubpath()
    return p


def _sym_triangle(r: QRectF) -> QPainterPath:      # [신규기능 §8-12] 삼각형 — 분배기 등 장비 도형
    # 2026-08-09 deep-interview: 실도면(HDA-3951 증폭기 등) 대조로 꼭짓점이 오른쪽(신호
    # 흐름 방향)을 향하는 형태가 기본으로 확정 — 평평한 변(왼쪽, 입력)·꼭짓점(오른쪽, 출력).
    # [2026-08-10 후속] 정삼각형으로 내접(`_tri_rect`)시키던 걸 버리고 bbox r을 그대로 채운다 —
    # Lucid 대조(실사용 지적): 정삼각형 유지는 필연적으로 한 축에 패딩을 만들어(비정사각
    # bbox에서), 리사이즈 핸들·qc-dot·TRIM 자국 핸들이 전부 실제 꼭짓점/변과 어긋나는
    # 근본 원인이었다. bbox를 그대로 채우면 뒤쪽 두 꼭짓점(TL·BL)이 항상 정확히 bbox 모서리와
    # 일치해 그 두 핸들은 특례 코드 없이 저절로 맞는다(Lucid의 "위 두 꼭짓점=bbox 모서리"와
    # 같은 구조, 우리는 90도 돌아간 배치라 왼쪽 두 모서리). "최대한 정삼각형에 가깝게"는
    # 기본 생성 크기(`_PALETTE_TRIANGLE_WH`)를 정삼각형 비율로 맞추는 쪽에서 담당 — 그
    # 비율 그대로 두면 이 함수가 실제로 정삼각형을 그린다(리사이즈하면 다른 도형처럼 늘어남,
    # 원을 늘이면 타원이 되는 것과 같은 통상적 동작).
    p = QPainterPath()
    p.moveTo(r.left(), r.top())
    p.lineTo(r.left(), r.bottom())
    p.lineTo(r.right(), r.center().y())
    p.closeSubpath()
    return p


# ---------------------------------------------------------------------------
# [신규기능 §8-13] 안테나 심볼 7종 — 모악산 송신소 실물 사진 대조 후 확정(deep-interview +
# artifact 시안 비교, 2026-08-04). 좌표는 사용자 확인을 거친 0~100 정규화 SVG 시안을 그대로
# 옮긴 것이라 `_n()` 헬퍼로 rect에 매핑한다(감사·재조정 시 시안과 나란히 비교하기 위함).
def _n(r: QRectF, x: float, y: float) -> QPointF:
    return QPointF(r.left() + x / 100.0 * r.width(), r.top() + y / 100.0 * r.height())


def _sym_mw_side(r: QRectF) -> QPainterPath:       # MW 파라볼릭(측면) — 겹친 원 2개로 두께감
    p = QPainterPath()
    s = min(r.width(), r.height()) / 100.0
    p.addEllipse(_n(r, 42, 50), 30 * s, 30 * s)
    p.addEllipse(_n(r, 60, 50), 26 * s, 26 * s)
    return p


def _sym_mw_front(r: QRectF) -> QPainterPath:      # MW 파라볼릭(정면) — 테두리 이중선으로 두께감
    p = QPainterPath()
    s = min(r.width(), r.height()) / 100.0
    c = _n(r, 50, 50)
    p.addEllipse(c, 32 * s, 32 * s)
    p.addEllipse(c, 28 * s, 28 * s)
    return p


def _sym_cp_dipole(r: QRectF) -> QPainterPath:     # CP 다이폴 — 사각 프레임 + 프레임 밖으로 나온 십자
    p = QPainterPath()
    p.addRect(QRectF(_n(r, 24, 24), _n(r, 76, 76)))
    p.moveTo(_n(r, 50, 12)); p.lineTo(_n(r, 50, 88))
    p.moveTo(_n(r, 12, 50)); p.lineTo(_n(r, 88, 50))
    return p


def _sym_cp_ring(r: QRectF) -> QPainterPath:       # CP RING — 가스통형(사각 몸통 + 완만한 노즈콘)
    p = QPainterPath()
    p.moveTo(_n(r, 30, 72))
    p.lineTo(_n(r, 30, 50))
    p.quadTo(_n(r, 27, 37), _n(r, 50, 27))
    p.quadTo(_n(r, 73, 37), _n(r, 70, 50))
    p.lineTo(_n(r, 70, 72))
    p.closeSubpath()
    return p


def _sym_dtv(r: QRectF) -> QPainterPath:           # DTV — 세로 패널(이중 테두리 베젤 + 모서리 사선)
    p = QPainterPath()
    p.addRect(QRectF(_n(r, 34, 8), _n(r, 66, 92)))
    p.addRect(QRectF(_n(r, 39, 13), _n(r, 61, 87)))
    p.moveTo(_n(r, 34, 8)); p.lineTo(_n(r, 39, 13))
    p.moveTo(_n(r, 66, 8)); p.lineTo(_n(r, 61, 13))
    p.moveTo(_n(r, 34, 92)); p.lineTo(_n(r, 39, 87))
    p.moveTo(_n(r, 66, 92)); p.lineTo(_n(r, 61, 87))
    return p


def _mesh_grid_path(r: QRectF) -> QPainterPath:    # MESH 공용 — 외곽원 + 대각격자 + 십자선(중앙점 제외)
    p = QPainterPath()
    s = min(r.width(), r.height()) / 100.0
    p.addEllipse(_n(r, 50, 50), 32 * s, 32 * s)
    for x1, y1, x2, y2 in ((22, 26, 74, 78), (18, 44, 56, 82), (44, 18, 82, 56),
                           (78, 26, 26, 78), (82, 44, 44, 82), (56, 18, 18, 56)):
        p.moveTo(_n(r, x1, y1)); p.lineTo(_n(r, x2, y2))
    p.moveTo(_n(r, 18, 50)); p.lineTo(_n(r, 82, 50))
    p.moveTo(_n(r, 50, 18)); p.lineTo(_n(r, 50, 82))
    return p


def _sym_mesh_hollow(r: QRectF) -> QPainterPath:   # MESH 파라볼릭(윤곽) — 중앙 급전부를 빈 원으로
    p = _mesh_grid_path(r)
    s = min(r.width(), r.height()) / 100.0
    p.addEllipse(_n(r, 50, 50), 6 * s, 6 * s)
    return p


def _sym_mesh_filled(r: QRectF) -> QPainterPath:   # MESH 파라볼릭(채움) — 중앙 원은 paint()가 강제로 검게 채움
    return _mesh_grid_path(r)


def _mesh_center_dot_rect(r: QRectF) -> QRectF:    # mesh_filled 전용 — 강제 채움 원의 사각형(paint()에서 사용)
    s = min(r.width(), r.height()) / 100.0
    c = _n(r, 50, 50)
    rad = 6 * s
    return QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad)


def _sym_lightning(r: QRectF) -> QPainterPath:     # 번개 표식 — 안테나 레이돔 로고 등, 다른 심볼 위에 얹어 쓰는 작은 데칼
    # Feather "zap" 아이콘의 검증된 폴리곤(0~24 box)을 0~100으로 스케일 이식 — 자체 zigzag를
    # 새로 설계하지 않고 이미 널리 쓰이는 번개 실루엣을 그대로 가져온 것.
    pts = [(13, 2), (3, 14), (12, 14), (11, 22), (21, 10), (12, 10)]
    p = QPainterPath()
    x0, y0 = pts[0]
    p.moveTo(_n(r, x0 / 24 * 100, y0 / 24 * 100))
    for x, y in pts[1:]:
        p.lineTo(_n(r, x / 24 * 100, y / 24 * 100))
    p.closeSubpath()
    return p


# kind → (한글 라벨, 경로 팩토리). 팔레트·직렬화·그리기가 이 하나를 공유한다.
# [2026-08-03] 카메라·증폭기·랙·안테나(도메인 픽토그램 4종)는 사용 빈도가 낮고 디자인
# 완성도도 떨어진다는 피드백으로 제거(구 .ecad 파일에 남아 있어도 _SymbolItem.__init__이
# 미지원 kind를 "decision"으로 폴백하므로 로드는 깨지지 않는다).
# [2026-08-04] 위 제거된 "안테나" 1종을 실물 사진 기반 7종(mw_side~mesh_hollow)으로 재도입
# — 디자인 완성도 문제였던 옛 픽토그램과 달리 deep-interview + artifact 시안 비교로 확정.
# 번개 표식(lightning)은 안테나 전용이 아니라 다른 심볼 위에 겹쳐 쓰는 범용 작은 데칼.
_SYMBOL_KINDS = {
    "decision":    ("판단", _sym_decision),
    "terminal":    ("시작/끝", _sym_terminal),
    "data":        ("입출력", _sym_data),
    "prep":        ("준비", _sym_prep),
    "document":    ("문서", _sym_document),
    "database":    ("저장소", _sym_database),
    "manual_input": ("수동입력", _sym_manual_input),
    "manual_op":   ("수동작업", _sym_manual_op),
    "display":     ("화면출력", _sym_display),
    "delay":       ("지연", _sym_delay),
    "triangle":    ("삼각형", _sym_triangle),
    "mw_side":     ("MW 파라볼릭(측면)", _sym_mw_side),
    "mw_front":    ("MW 파라볼릭(정면)", _sym_mw_front),
    "cp_dipole":   ("CP 다이폴", _sym_cp_dipole),
    "cp_ring":     ("CP RING", _sym_cp_ring),
    "dtv":         ("DTV", _sym_dtv),
    "mesh_filled": ("MESH 파라볼릭(채움)", _sym_mesh_filled),
    "mesh_hollow": ("MESH 파라볼릭(윤곽)", _sym_mesh_hollow),
    "lightning":   ("번개 표식", _sym_lightning),
}


# (_LabelMixin·_CenterLabelMixin은 도형 클래스보다 앞서야 해서 _RectItem 위로 이동함)


class _SymbolItem(_CenterLabelMixin, _RectGeometryMixin, _HandleResizeMixin, QGraphicsRectItem):
    """순서도 심볼 — rect 기반이라 _RectItem과 동일한 리사이즈·회전·stretch·undo를
    물려받고, paint/shape만 kind별 경로(_SYMBOL_KINDS)로 그린다. 더블클릭 중앙 라벨은
    _CenterLabelMixin이 네모·원과 공유한다.
    (_SYMBOL_KINDS를 참조하므로 경로 팩토리 뒤에 둔다.)"""

    def __init__(self, kind: str, rect: QRectF):
        super().__init__(rect)
        self._kind = kind if kind in _SYMBOL_KINDS else "decision"
        self._init_resize()
        self._init_label()

    def _sym_path(self) -> QPainterPath:
        return _SYMBOL_KINDS[self._kind][1](self.rect())

    def _label_inset_ratio(self) -> float:
        # kind별 내접 가용폭 — 마름모는 세로중앙 한 점에서만 최대폭이라 가장 좁게, 원기둥·문서·
        # 화면출력·지연 등 곡선 심볼은 중간, 상하 평행한 스타디움·평행사변형·육각형은 넉넉히.
        if self._kind == "triangle":
            # 2026-08-09 2차: 꼭짓점이 오른쪽이라 라벨 앵커가 놓인 세로중앙 행이 오히려
            # 삼각형에서 가장 넓은 행(마름모와 같은 사정) — 다만 정삼각형이 정사각 박스
            # 안에 내접해 실제 폭이 박스 폭의 0.87배뿐이라 마름모(0.6)보다 낮게 잡는다.
            return 0.5

        if self._kind == "decision":
            return 0.6
        if self._kind in ("database", "document", "display", "delay"):
            return 0.72
        if self._kind == "manual_op":
            return 0.7
        if self._kind in ("mw_side", "mw_front", "mesh_filled", "mesh_hollow"):
            return 0.55   # 원 반지름 32/100 — 실제 지름 비는 0.64, 여유를 두어 원 밖으로 안 나가게
        if self._kind == "cp_ring":
            return 0.4    # 몸통 폭 30~70 구간(0.4)만 안전 — 노즈콘 위쪽은 그보다 더 좁음
        if self._kind == "dtv":
            return 0.2    # 세로로 매우 좁은 패널 — 라벨은 대부분 줄바꿈됨을 전제
        if self._kind == "lightning":
            return 0.3    # 번개 허리(x 12.5~87.5 중 45.8~54.2)가 세로중앙에서 가장 좁음
        return 0.78

    def _label_anchor(self) -> QPointF:
        # 광학 중심 보정: 외접 rect 중심이 도형의 '보이는 무게중심'과 어긋나는 kind만 라벨을
        # 옮긴다. 원기둥(database)은 윗 타원이 중심을 위로 끌어 라벨이 윗 곡선에 겹치므로 아래로,
        # 문서(document)는 아래 물결이 무게를 아래로 내리므로 살짝 위로. 나머지(마름모·스타디움·
        # 평행사변형·육각형)는 상하 대칭이라 rect 중심이 곧 광학 중심 → 보정 없음.
        c = self.rect().center()
        r = self.rect()
        if self._kind == "database":
            e = min(r.height() * 0.18, r.width() * 0.5)   # 윗/아랫 타원 반높이(_sym_database와 동일)
            return QPointF(c.x(), c.y() + e * 0.7)
        if self._kind == "document":
            return QPointF(c.x(), c.y() - r.height() * 0.06)
        if self._kind == "triangle":
            # 2026-08-09 2차: 꼭짓점이 오른쪽으로 바뀌어 무게중심도 재계산 — 상하 대칭이라
            # 세로는 bbox 중심과 같고, 가로는 평평한 변(왼쪽)에서 1/3 지점(꼭짓점 쪽으로
            # 치우침)이 실제 삼각형 무게중심. [2026-08-10 후속] `_sym_triangle`이 이제
            # `_tri_rect` 없이 bbox r을 그대로 채우므로(Lucid 대조) 여기도 r을 직접 쓴다.
            return QPointF(r.left() + r.width() / 3.0, r.center().y())
        return c

    def clone(self):
        c = _SymbolItem(self._kind, QRectF(self.rect()))
        c.setPen(QPen(self.pen()))
        c.setBrush(QBrush(self.brush()))
        return self._copy_common_to(c)

    def apply_fill(self, color):
        """[신규기능 · 도형 채우기] _RectItem.apply_fill과 동일 — 클래스별 명시 opt-in."""
        self.prepareGeometryChange()
        self.setBrush(QBrush(QColor(color)) if color is not None else QBrush(Qt.BrushStyle.NoBrush))
        self.update()

    def _base_shape(self):
        # 속 빈 심볼(NoBrush)은 외곽선만 클릭 영역으로(네모와 동일 — 안에서 화살표 시작 가능),
        # 채움이 있으면 심볼 전체가 클릭 영역.
        path = self._sym_path()
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), self._EDGE_HIT_MIN / self._scale_or_1()))
        return stroker.createStroke(path)

    def _interior_path(self):
        # [M4-4 ⓓ] 속 빈 심볼의 내부 — 외접 박스가 아니라 심볼 실제 외곽선 안쪽(마름모 등).
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return None
        return self._sym_path()

    def _fill_path(self) -> QPainterPath:
        # [§8 항목17 2단계] _RectGeometryMixin 기본(사각형) override — 심볼 실제 외곽선.
        return self._sym_path()

    def paint(self, painter, option, widget=None):
        # 네모의 _paint_base_no_select(super().paint()가 사각을 그림) 대신 심볼 경로를 직접 그린다.
        # [§8 항목17 7단계] 이전엔 이 게이트가 `_cuts`만 봐서 삼각형 등에 붙은 포트가 있어도
        # 시각적으로 전혀 안 잘렸다(_RectItem/_EllipseItem과 달리 옛 배경색 덮어그리기 호출조차
        # 없었던 별개의 잠재 버그) — `_ports`도 함께 본다.
        if getattr(self, "_ports", None) or getattr(self, "_cuts", None):
            _paint_filled_trimmed_border(self, painter)
        else:
            painter.setPen(self.pen())
            painter.setBrush(self.brush())
            painter.drawPath(self._sym_path())
        if self._kind == "mesh_filled":
            # [§8-13] 중앙 급전부는 사용자의 채움색과 무관하게 항상 검게 — kind 식별용
            # 고정 디테일이라 apply_fill로 바뀌는 self.brush()에 기대지 않고 따로 그린다.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("black")))
            painter.drawEllipse(_mesh_center_dot_rect(self.rect()))
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)


# ---------------------------------------------------------------------------
# [우리 확장 · Phase 4] 삽입 이미지 — PNG/JPG를 도면에 배치
# ---------------------------------------------------------------------------
class _ImageItem(_RectGeometryMixin, _HandleResizeMixin, QGraphicsRectItem):
    """삽입 이미지 — rect 기반이라 _RectItem·_SymbolItem과 동일한 리사이즈·회전·stretch·undo를
    그대로 물려받고, paint만 원본 픽스맵을 rect에 스케일해 그리도록 갈아끼운다.
    원본 픽스맵(_pixmap)을 전체 해상도로 보관 → 저장/재열기·PDF에도 화질 손실 없음(rect는 표시 크기).
    종횡비는 꼭짓점 리사이즈에서 고정(_constrain_box_rect) — 변 리사이즈는 자유(의도적 늘림)."""

    def __init__(self, pixmap: QPixmap, rect: QRectF):
        super().__init__(rect)
        self._pixmap = pixmap
        self.setPen(QPen(Qt.PenStyle.NoPen))   # 테두리 없음 — 이미지 픽셀만 그린다
        self._init_resize()

    def _aspect(self) -> float:
        w, h = self._pixmap.width(), self._pixmap.height()
        return (w / h) if h else 1.0

    def clone(self):
        c = _ImageItem(QPixmap(self._pixmap), QRectF(self.rect()))
        return self._copy_common_to(c)

    def _content_rect(self) -> QRectF:
        return QRectF(self.rect())

    def _constrain_box_rect(self, new: QRectF, kind: str, key, shift: bool = False) -> QRectF:
        # 꼭짓점 드래그는 원본 종횡비를 유지(사진 왜곡 방지, Shift 여부 무관 — 항상 고정).
        # 대각 고정점(opp) 기준으로, 폭·높이 중 더 많이 자란 쪽에 비율을 맞춰 사각형을 다시 세운다.
        if kind != "corner":
            return new
        o = self._box_orig_rect
        opp = [o.bottomRight(), o.bottomLeft(), o.topLeft(), o.topRight()][key]  # 0TL 1TR 2BR 3BL
        asp = self._aspect()
        w = max(new.width(), new.height() * asp)
        h = w / asp
        sx = 1.0 if key in (1, 2) else -1.0   # TR·BR = 오른쪽, TL·BL = 왼쪽
        sy = 1.0 if key in (2, 3) else -1.0   # BR·BL = 아래,   TL·TR = 위
        return QRectF(opp, QPointF(opp.x() + sx * w, opp.y() + sy * h)).normalized()

    def paint(self, painter, option, widget=None):
        painter.drawPixmap(self.rect(), self._pixmap, QRectF(self._pixmap.rect()))
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)


# ---------------------------------------------------------------------------
# [우리 확장 · Phase 4] 표제란 / 용지틀 — 도면번호·축척·발주처가 들어가는 우하단 표 + A-size 용지경계
# ---------------------------------------------------------------------------
# 설계(deep-interview 2026-07-20): 진짜 paper space(뷰포트·이중좌표계)를 도입하지 않고,
# 무한 모델공간(mm 월드좌표) 위에 '용지 프레임 객체' 하나를 얹는다. 프레임은 A-size 고정
# (임의 리사이즈 금지 — '용지'의 의미 보존), 이동만 가능. 크기·방향은 삽입/편집 시 재선택.
# rect는 용지 mm 치수(0,0,W,H). 표제란 필드값은 dict로 보관하고 paint가 표 칸에 텍스트로 렌더.
# 참고 도면(docs/reference/)에 정형 표제란이 없어 표준 KS식 3행 표로 잡음(레이아웃은 조정 가능).

# 용지 mm 치수(세로 기준 w,h). 가로(landscape)는 w·h 교환.
PAPER_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
}

# 표제란 행 정의: (행 높이 가중치, [(라벨, 필드키, 열 폭 가중치), ...]).
# 각 행의 열 폭 가중치 합은 같아야(=5) 열이 세로로 정렬된다. 필드키 ""는 라벨만(값 칸 없음).
_TB_ROWS = [
    (1.2, [("발주처 / 프로젝트", "client", 3), ("도면번호", "number", 2)]),
    (1.2, [("도면명", "title", 3), ("축척", "scale", 2)]),
    (1.0, [("작성", "author", 2), ("검토", "reviewer", 2), ("날짜", "date", 1)]),
]
# 표제란 필드키(폼·직렬화 공용) — _TB_ROWS에서 실제 쓰는 키만.
TB_FIELD_KEYS = ("client", "number", "title", "scale", "author", "reviewer", "date")
TB_FIELD_LABELS = {
    "client": "발주처 / 프로젝트", "number": "도면번호", "title": "도면명",
    "scale": "축척", "author": "작성자", "reviewer": "검토자", "date": "날짜",
}


class _TitleBlockItem(QGraphicsRectItem):
    """용지틀 + 표제란 — A-size 용지경계 rect와 우하단 표제란 표를 그린다. rect 기반이지만
    _HandleResizeMixin은 쓰지 않는다(용지는 고정 크기, 이동만). 더블클릭 편집은 host의 폼
    다이얼로그가 처리(뷰가 _edit_titleblock으로 위임). 필드값(_fields)만 바뀌므로 paint로 반영.
    DXF 내보내기에서는 _RectItem이 아니라 isinstance 체인에 안 걸려 조용히 제외된다(스코프)."""

    _M = 10.0        # 용지 가장자리 → 도면 테두리 여백(mm)
    _TB_W = 180.0    # 표제란 표 폭(mm)
    _TB_H = 33.0     # 표제란 표 높이(mm)
    # [2026-08-03] 실제 캐드 관례로 변경 — 흰 종이를 흉내낸 배경 채움은 없애고 외곽 테두리
    # 선 + 우하단 표만 그린다(사용자 피드백: "이미지처럼 보이는 흰 배경 위에 작성" 대신
    # "외곽 틀 + 우하단 정보, 그게 다"). 선·잉크색은 테마에 맞춰 골라 다크 캔버스에서도
    # 보이게 한다(_view_is_dark) — PDF 인쇄 시엔 그 함수가 자동으로 라이트 판정을 내려
    # 기존 흑백 인쇄 관례(_LINE_LIGHT/_INK_LIGHT)를 그대로 쓴다.
    _LINE_LIGHT = QColor("#333333")
    _LINE_DARK = QColor("#cdd8e3")
    _INK_LIGHT = QColor("#111111")
    _INK_DARK = QColor("#cdd8e3")

    def _line_color(self) -> QColor:
        return self._LINE_DARK if _view_is_dark(self) else self._LINE_LIGHT

    def _ink_color(self) -> QColor:
        return self._INK_DARK if _view_is_dark(self) else self._INK_LIGHT

    def __init__(self, size: str = "A2", orient: str = "landscape", fields: dict | None = None):
        super().__init__()
        self._size = size if size in PAPER_SIZES_MM else "A2"
        self._orient = "portrait" if orient == "portrait" else "landscape"
        self._fields = {k: "" for k in TB_FIELD_KEYS}
        if fields:
            self._fields.update({k: str(v) for k, v in fields.items() if k in TB_FIELD_KEYS})
        self.setPen(QPen(Qt.PenStyle.NoPen))   # 테두리는 paint가 직접 그림
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._apply_paper_rect()

    # ---- 용지 치수 ----------------------------------------------------------
    def paper_wh(self) -> tuple[float, float]:
        w, h = PAPER_SIZES_MM[self._size]
        return (h, w) if self._orient == "landscape" else (w, h)

    def _apply_paper_rect(self):
        w, h = self.paper_wh()
        self.prepareGeometryChange()
        self.setRect(QRectF(0.0, 0.0, w, h))

    def set_paper(self, size: str, orient: str):
        if size in PAPER_SIZES_MM:
            self._size = size
        self._orient = "portrait" if orient == "portrait" else "landscape"
        self._apply_paper_rect()
        self.update()

    def set_fields(self, fields: dict):
        for k in TB_FIELD_KEYS:
            if k in fields:
                self._fields[k] = str(fields[k])
        self.update()

    def clone(self):
        c = _TitleBlockItem(self._size, self._orient, dict(self._fields))
        c.setPos(self.pos())
        c.setZValue(self.zValue())
        c.setFlags(self.flags())
        return c

    # ---- 표제란 표 영역(용지 로컬좌표, 도면 테두리 안쪽 우하단) --------------------
    def _tb_rect(self) -> QRectF:
        inner = self.rect().adjusted(self._M, self._M, -self._M, -self._M)
        w = min(self._TB_W, inner.width())
        return QRectF(inner.right() - w, inner.bottom() - self._TB_H, w, self._TB_H)

    # ---- 히트 영역: 용지 테두리 밴드 + 표제란만(내부는 통과시켜 위에 그리기 가능) --------
    def boundingRect(self) -> QRectF:
        return self.rect().adjusted(-3.0, -3.0, 3.0, 3.0)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        border = QPainterPath()
        border.addRect(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(self._M)
        path.addPath(stroker.createStroke(border))
        path.addRect(self._tb_rect())
        return path

    # ---- 렌더 ---------------------------------------------------------------

    def paint(self, painter, option, widget=None):
        r = self.rect()
        line = self._line_color()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 용지 경계선(채움 없음 — 캐드 관례대로 외곽 테두리만)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(line, 0.5))
        painter.drawRect(r)
        # 도면 테두리(안쪽, 굵게)
        inner = r.adjusted(self._M, self._M, -self._M, -self._M)
        painter.setPen(QPen(line, 1.2))
        painter.drawRect(inner)
        # 표제란 표
        self._paint_table(painter)
        painter.restore()
        if self.isSelected():
            _paint_selection_highlight(painter, self, self._scale_or_1())

    def _scale_or_1(self) -> float:
        s = self.scale() * _view_zoom_factor(self)
        return s if s else 1.0

    def _paint_table(self, painter):
        tb = self._tb_rect()
        line = self._line_color()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(line, 1.2))
        painter.drawRect(tb)
        painter.setPen(QPen(line, 0.5))
        h_weight = sum(rw for rw, _ in _TB_ROWS)
        y = tb.top()
        for ri, (rw, cells) in enumerate(_TB_ROWS):
            rh = tb.height() * (rw / h_weight)
            if ri > 0:  # 행 구분선
                painter.drawLine(QPointF(tb.left(), y), QPointF(tb.right(), y))
            c_weight = sum(cw for _l, _k, cw in cells)
            x = tb.left()
            for ci, (label, key, cw) in enumerate(cells):
                cwid = tb.width() * (cw / c_weight)
                cell = QRectF(x, y, cwid, rh)
                if ci > 0:  # 열 구분선
                    painter.setPen(QPen(line, 0.5))
                    painter.drawLine(QPointF(x, y), QPointF(x, y + rh))
                self._paint_cell(painter, cell, label, self._fields.get(key, ""))
                x += cwid
            y += rh

    def _paint_cell(self, painter, cell: QRectF, label: str, value: str):
        pad = 1.2
        ink = self._ink_color()
        # 라벨(작게, 좌상단)
        painter.setPen(QPen(ink))
        _font_px(painter, 2.6)
        lbl_rect = cell.adjusted(pad, pad, -pad, -pad)
        painter.drawText(lbl_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), label)
        # 값(크게, 가운데)
        if value:
            _font_px(painter, 3.8)
            painter.drawText(cell, int(Qt.AlignmentFlag.AlignCenter), value)


# ---------------------------------------------------------------------------
# [우리 확장 · Phase 4] 표(table) — NxM 균등 격자 + 셀 텍스트(인라인 편집)
# ---------------------------------------------------------------------------
# 설계(deep-interview 2026-07-20): rect 기반이라 _ImageItem·_TitleBlockItem처럼 리사이즈·회전·
# undo·그룹변형·PDF·복제를 그대로 상속(_HandleResizeMixin + setRect → 8핸들 자유 리사이즈).
# 균등 비례 격자(전체 리사이즈 시 모든 열·행이 같은 비율로 스케일 — 개별 열폭 조절은 후속 스코프).
# 셀 텍스트는 2차원 리스트(_cells[r][c]). 셀 편집은 뷰가 인라인 QLineEdit(_CellEditor)로 처리.
# 첫 행 헤더(_header=True면 굵게+옅은 배경). DXF 제외(isinstance 체인 밖), .ecad 직렬화.
class _TableItem(_RectGeometryMixin, _HandleResizeMixin, QGraphicsRectItem):
    """NxM 표. rect 기반 — _ImageItem과 동일한 자유 리사이즈(꼭짓점 2D·변 1축)를 상속.
    종횡비 고정은 하지 않는다(표는 임의 비율) — 기본 _constrain_box_rect(무변형)를 그대로 쓴다.
    행은 균등 높이, 열은 개별 폭 조절 가능(_col_widths — 표 전체폭 대비 비율, deep-interview
    2026-07-31: 행은 스코프 밖·표 전체폭 고정한 채 인접 열끼리 폭 교환·Excel/Word 관례)."""

    # [2026-08-03] _TitleBlockItem과 동일하게 흰 배경 채움을 없애고 테마 적응 선·잉크색으로
    # 전환 — 캐드 표 관례(채움 없이 격자선 + 헤더행은 굵게만으로 구분).
    _LINE_LIGHT = QColor("#333333")
    _LINE_DARK = QColor("#cdd8e3")
    _INK_LIGHT = QColor("#111111")
    _INK_DARK = QColor("#cdd8e3")
    _MIN_COL_W = 10.0    # 월드 단위 — 드래그로 열이 이보다 좁아지지 않음(기본 셀폭 40의 1/4)
    _COL_HIT_PX = 8.0    # 화면 px — 열 경계선 드래그 히트폭(_EDGE_HIT_MIN과 동일 관례)

    def _line_color(self) -> QColor:
        return self._LINE_DARK if _view_is_dark(self) else self._LINE_LIGHT

    def _ink_color(self) -> QColor:
        return self._INK_DARK if _view_is_dark(self) else self._INK_LIGHT

    def __init__(self, rows: int, cols: int, rect: QRectF,
                 cells: list | None = None, header: bool = True,
                 col_widths: list | None = None):
        super().__init__(rect)
        self._rows = max(1, int(rows))
        self._cols = max(1, int(cols))
        self._header = bool(header)
        self._cells = self._norm_cells(cells)
        self._col_widths = self._norm_col_widths(col_widths)
        self._col_drag = None   # 드래그 중인 열 경계 인덱스(0..cols-2), None=드래그 아님
        self.setPen(QPen(Qt.PenStyle.NoPen))     # 격자·외곽은 paint가 직접 그림
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._init_resize()

    def _norm_cells(self, cells) -> list:
        """cells를 rows×cols 문자열 격자로 정규화(부족분은 빈칸, 초과분은 잘라냄)."""
        grid = [["" for _ in range(self._cols)] for _ in range(self._rows)]
        if cells:
            for r in range(min(self._rows, len(cells))):
                row = cells[r] or []
                for c in range(min(self._cols, len(row))):
                    grid[r][c] = "" if row[c] is None else str(row[c])
        return grid

    def _norm_col_widths(self, col_widths) -> list:
        """[열폭 드래그] 열별 폭 비율(합=1.0)로 정규화 — 없거나 개수가 안 맞으면 균등폭."""
        if col_widths and len(col_widths) == self._cols:
            raw = [max(0.01, float(w)) for w in col_widths]
            total = sum(raw)
            if total > 0:
                return [w / total for w in raw]
        return [1.0 / self._cols] * self._cols

    # ---- 셀 접근(뷰 인라인 편집이 사용) --------------------------------------
    def dims(self) -> tuple[int, int]:
        return self._rows, self._cols

    def cell_text(self, r: int, c: int) -> str:
        return self._cells[r][c]

    def set_cell_text(self, r: int, c: int, text: str):
        if 0 <= r < self._rows and 0 <= c < self._cols:
            self._cells[r][c] = str(text)
            self.update()

    # ---- 셀 기하(로컬좌표) --------------------------------------------------
    def _col_edges_local(self) -> list:
        """[열폭 드래그] 열 경계선의 로컬 x좌표 목록(길이 cols+1) — _col_widths 비율을 표
        폭에 적용한 누적합. 마지막은 부동소수 오차 방지로 box.right()에 고정."""
        box = self.rect()
        edges = [box.left()]
        x = box.left()
        for w in self._col_widths:
            x += w * box.width()
            edges.append(x)
        edges[-1] = box.right()
        return edges

    def cell_rect(self, r: int, c: int) -> QRectF:
        box = self.rect()
        edges = self._col_edges_local()
        ch = box.height() / self._rows
        return QRectF(edges[c], box.top() + r * ch, edges[c + 1] - edges[c], ch)

    def cell_at(self, local: QPointF):
        """로컬좌표 local이 속한 (r, c) — 격자 밖이면 None."""
        box = self.rect()
        if not box.contains(local):
            return None
        ch = box.height() / self._rows
        if ch <= 0:
            return None
        edges = self._col_edges_local()
        c = self._cols - 1
        for i in range(self._cols):
            if local.x() < edges[i + 1]:
                c = i
                break
        r = min(max(int((local.y() - box.top()) / ch), 0), self._rows - 1)
        return (r, c)

    # ---- [열폭 드래그] 내부 경계선 잡기·이동(2026-07-31) ---------------------
    # 표 전체폭은 고정한 채 인접 열끼리 폭을 주고받는다(Excel/Word 관례) — 전체 크기 조절은
    # 기존 _HandleResizeMixin 박스 리사이즈 핸들이 담당해 역할이 겹치지 않는다. 행 높이는
    # 계속 균등(스코프 밖). 드래그는 뷰가 begin/drag/end 3단계로 진행(세그먼트 드래그와 동일 관례).
    def _col_boundary_at(self, local: QPointF):
        """local(로컬좌표) 근처에 내부 열 경계선이 있으면 그 인덱스(0..cols-2), 없으면 None.
        선택된 표에서만 호출(뷰가 selectedItems()만 순회 — 박스 핸들과 동일 관례)."""
        box = self.rect()
        if self._cols < 2 or local.y() < box.top() or local.y() > box.bottom():
            return None
        tol = self._COL_HIT_PX / self._scale_or_1()
        edges = self._col_edges_local()
        best = None
        for i in range(1, self._cols):
            d = abs(local.x() - edges[i])
            if d <= tol and (best is None or d < best[1]):
                best = (i - 1, d)
        return best[0] if best else None

    def _begin_col_drag(self, boundary_idx: int):
        self._col_drag = boundary_idx

    def _drag_col_boundary_to(self, local_x: float):
        """경계를 local_x로 이동 — 최소폭(_MIN_COL_W) 이하로는 안 좁아짐."""
        idx = self._col_drag
        if idx is None:
            return
        box = self.rect()
        if box.width() <= 0:
            return
        edges = self._col_edges_local()
        left_edge, right_edge = edges[idx], edges[idx + 2]
        span = right_edge - left_edge
        if span <= 0:
            return
        min_w = min(self._MIN_COL_W, span / 2.0)
        new_edge = min(max(local_x, left_edge + min_w), right_edge - min_w)
        self._col_widths[idx] = (new_edge - left_edge) / box.width()
        self._col_widths[idx + 1] = (right_edge - new_edge) / box.width()
        self.update()

    def _end_col_drag(self):
        self._col_drag = None

    def clone(self):
        c = _TableItem(self._rows, self._cols, QRectF(self.rect()),
                       [row[:] for row in self._cells], self._header,
                       list(self._col_widths))
        return self._copy_common_to(c)

    def _content_rect(self) -> QRectF:
        return QRectF(self.rect())

    # [열폭 드래그] geom undo에 col_widths도 함께 실어야 되돌리기가 폭까지 복원한다
    # (_RectGeometryMixin 기본은 rect()만 담아 여기서 override).
    def _capture_geom_local(self):
        return (QRectF(self.rect()), list(self._col_widths))

    def _apply_geom_local(self, g):
        rect, widths = g
        self.setRect(rect)
        if len(widths) == self._cols:
            self._col_widths = list(widths)

    def paint(self, painter, option, widget=None):
        box = self.rect()
        edges = self._col_edges_local()
        ch = box.height() / self._rows
        line = self._line_color()
        ink = self._ink_color()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        # 셀 텍스트(폰트 크기는 셀 치수에 맞춰 축소 — 열마다 폭이 다를 수 있어 열별로 계산).
        # 헤더행은 채움 대신 굵은 글씨로만 구분(캐드 표 관례 — 채움 없음).
        for r in range(self._rows):
            for c in range(self._cols):
                txt = self._cells[r][c]
                if not txt:
                    continue
                cw = edges[c + 1] - edges[c]
                fs = max(2.0, min(ch * 0.5, cw * 0.30))
                _font_px(painter, fs, bold=(self._header and r == 0))
                painter.setPen(QPen(ink))
                painter.drawText(
                    self.cell_rect(r, c).adjusted(1.0, 1.0, -1.0, -1.0),
                    int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), txt)
        # 내부 격자선
        painter.setPen(QPen(line, 0.5))
        for x in edges[1:-1]:
            painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))
        for j in range(1, self._rows):
            y = box.top() + j * ch
            painter.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
        # 헤더행 구분선(첫 행 아래, 본문보다 굵게)
        if self._header and self._rows > 1:
            painter.setPen(QPen(line, 1.0))
            painter.drawLine(QPointF(box.left(), box.top() + ch), QPointF(box.right(), box.top() + ch))
        # 외곽선
        painter.setPen(QPen(line, 1.0))
        painter.drawRect(box)
        painter.restore()
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)


class _CellEditor(QLineEdit):
    """[우리 확장 · Phase 4] 표 셀 인라인 편집기 — 뷰 viewport 위에 떠서 한 셀을 편집.
    Enter=아래 칸, Tab=오른쪽(줄 끝이면 다음 줄 첫 칸), Shift+Tab=왼쪽, Esc=취소, 포커스 상실=커밋.
    셀 편집은 undo 스코프 밖(표제란 필드와 동일) — set_cell_text로 직접 반영."""

    def __init__(self, view, item: "_TableItem", r: int, c: int):
        super().__init__(view.viewport())
        self._view = view
        self._item = item
        self._r = r
        self._c = c
        self._done = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(item.cell_text(r, c))
        self.selectAll()
        self._place()
        self.show()
        self.setFocus()

    def _place(self):
        """셀 rect(아이템 로컬)를 뷰 픽셀좌표로 매핑해 편집기 위치·크기 설정."""
        cell = self._item.cell_rect(self._r, self._c)
        pts = [self._view.mapFromScene(self._item.mapToScene(p)) for p in
               (cell.topLeft(), cell.topRight(), cell.bottomRight(), cell.bottomLeft())]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        self.setGeometry(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def _commit(self):
        if not self._done:
            self._done = True
            self._item.set_cell_text(self._r, self._c, self.text())

    def _cancel(self):
        self._done = True   # 커밋하지 않고 닫기

    def _move(self, dr: int, dc: int):
        rows, cols = self._item.dims()
        r, c = self._r + dr, self._c + dc
        while c >= cols:       # Tab 줄넘김(오른쪽 끝 → 다음 줄 첫 칸)
            c -= cols
            r += 1
        while c < 0:           # Shift+Tab 줄넘김(왼쪽 끝 → 이전 줄 마지막 칸)
            c += cols
            r -= 1
        self._commit()
        self.close()
        if 0 <= r < rows and 0 <= c < cols:
            self._view._begin_cell_edit(self._item, r, c)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._move(1, 0)
            return
        if key == Qt.Key.Key_Escape:
            self._cancel()
            self.close()
            return
        super().keyPressEvent(event)

    def event(self, e):
        # Tab/Backtab은 위젯 포커스 순회로 먼저 소비되므로 event()에서 가로챈다.
        if e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self._move(0, 1 if e.key() == Qt.Key.Key_Tab else -1)
            return True
        return super().event(e)

    def focusOutEvent(self, event):
        self._commit()
        self.close()
        super().focusOutEvent(event)


class _LineItem(_LabelMixin, _HandleResizeMixin, QGraphicsLineItem):
    def __init__(self, *args):
        super().__init__(*args)
        self._init_resize()
        self._init_label()

    def setLine(self, *args):
        super().setLine(*args)
        self._sync_label()   # 끝점 이동·그리기로 선 기하가 바뀌면 라벨을 중점에 재배치

    def _label_anchor(self) -> QPointF:
        line = self.line()
        return QPointF((line.x1() + line.x2()) / 2.0, (line.y1() + line.y2()) / 2.0)

    def _label_color(self) -> QColor:
        return self.pen().color()

    def clone(self):
        c = _LineItem(QLineF(self.line()))
        c.setPen(QPen(self.pen()))
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 두 끝점을 씬변형.
    def _capture_geom_local(self):
        return QLineF(self.line())

    def _apply_geom_local(self, g):
        self.setLine(g)

    def rebake_scene(self, fn):
        ln = self.line()
        self.setLine(QLineF(self._rebake_pt(fn, ln.p1()), self._rebake_pt(fn, ln.p2())))

    def _uses_endpoints(self):
        return True

    def _endpoints(self):
        line = self.line()
        return [line.p1(), line.p2()]

    def _set_endpoint(self, idx, p):
        line = self.line()
        if idx == 0:
            self.setLine(QLineF(QPointF(p), line.p2()))
        else:
            self.setLine(QLineF(line.p1(), QPointF(p)))

    def _content_rect(self):
        # Qt 기본 QGraphicsLineItem.boundingRect()는 펜 두께가 0이 아니면 내부적으로
        # shape()를 호출하는데, 믹스인 shape()가 핸들 계산에 다시 boundingRect()를 부르므로
        # 무한 재귀(스택 오버플로 → 프로세스 abort)가 된다. 선 기하에서 직접 계산해 사이클을 끊는다.
        line = self.line()
        extra = self.pen().widthF() / 2.0 + 1.0
        return QRectF(line.p1(), line.p2()).normalized().adjusted(-extra, -extra, extra, extra)

    def boundingRect(self):
        # 선택 외곽선(획+8)이 _content_rect보다 살짝 바깥으로 나가므로 여유를 더 준다
        # (안 그러면 수평/수직 선에서 점선 잔상이 남을 수 있음).
        pad = 5.0 / self._scale_or_1()
        return super().boundingRect().adjusted(-pad, -pad, pad, pad)

    # [선택 표시 통일 2026-08-01] 커스텀 _paint_selection_outline 제거 — 믹스인 기본 구현이
    # _item_center_path(QGraphicsLineItem 분기)로 동일한 결과를 낸다(중복 로직 흡수).


class _PathItem(_HandleResizeMixin, QGraphicsPathItem):
    def __init__(self, *args):
        super().__init__(*args)
        self._init_resize()
        self._sel_outline = None  # 선택 점선 외곽선 캐시(획·펜 불변 → 이동 중 재계산 회피)

    def setPath(self, path):
        self._sel_outline = None
        super().setPath(path)

    def setPen(self, pen):
        self._sel_outline = None
        super().setPen(pen)

    def clone(self):
        c = _PathItem(QPainterPath(self.path()))
        c.setPen(QPen(self.pen()))
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 패스 원소(Move/Line/Curve)의 모든 점을 씬변형.
    def _capture_geom_local(self):
        return QPainterPath(self.path())

    def _apply_geom_local(self, g):
        self.setPath(g)

    def rebake_scene(self, fn):
        old = self.path()
        np = QPainterPath()
        i, n = 0, old.elementCount()
        while i < n:
            el = old.elementAt(i)
            p = self._rebake_pt(fn, QPointF(el.x, el.y))
            if el.isMoveTo():
                np.moveTo(p)
                i += 1
            elif el.isCurveTo():   # 3개(제어1·제어2·끝점) 묶음
                e2 = old.elementAt(i + 1)
                e3 = old.elementAt(i + 2)
                np.cubicTo(p, self._rebake_pt(fn, QPointF(e2.x, e2.y)),
                           self._rebake_pt(fn, QPointF(e3.x, e3.y)))
                i += 3
            else:              # LineToElement
                np.lineTo(p)
                i += 1
        self.prepareGeometryChange()
        self.setPath(np)

    def _content_rect(self):
        # _LineItem과 동일 사이클 방지: QGraphicsPathItem.boundingRect()는 brush가 NoBrush일 때
        # shape()를 호출하므로, 패스 기하에서 직접 계산해 믹스인 shape()와의 재귀를 끊는다.
        extra = self.pen().widthF() / 2.0 + 1.0
        return self.path().boundingRect().adjusted(-extra, -extra, extra, extra)

    def _handle_active(self):
        # 펜은 회전·확대 핸들을 두지 않는다 — 그리기 전용이라 잘못 그리면 삭제·되돌리기로
        # 수정하지 변형하지 않는다. 선택 시 획 따라가는 점선만, 이동은 획 잡아 끌기(movable).
        return False

    def _base_shape(self):
        # 클릭 영역은 '획 위'만 — Qt 기본 QGraphicsPathItem.shape()는 스트로크에 원본 패스를
        # addPath로 더해, 닫힌(감싸는) 펜 획의 안쪽 면까지 클릭 영역에 포함한다. 그러면 도형을
        # 빙 둘러 그린 펜이 안쪽 빈 공간의 클릭을 통째로 가로채 안쪽 도형이 선택되지 않는다.
        # 획만 두껍게 스트로크한 밴드를 반환해(안쪽은 비움) 루프 안 도형이 정상 선택되게 한다.
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 10) + 4)   # 잡기 쉬운 폭
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.path())

    def boundingRect(self):
        # 선택 외곽선(획+8)이 _content_rect보다 살짝 바깥으로 나가므로 여유를 더 준다.
        pad = 5.0 / self._scale_or_1()
        return super().boundingRect().adjusted(-pad, -pad, pad, pad)

    def _paint_selection_outline(self, painter, scale):
        # [선택 표시 통일 2026-08-01 → 2026-08-03 Lucid 대조] 단일선택이면 얇은 중심선(가벼운
        # 연산 — 밴드 캐시 자체가 필요 없다). 다중선택 중 하나면 기존 바깥 밴드 — 자유곡선은
        # 점이 많아 스트로크+불리언 연산이 무겁고 획·펜이 안 바뀌면 결과가 동일하므로 그 경우만
        # 캐시를 유지한다(이동 중 매 프레임 재계산 회피, 기존 최적화 보존).
        if _selection_is_solo(self):
            _paint_selection_centerline(painter, self, scale)
            return
        if self._sel_outline is None:
            self._sel_outline = _highlight_band(self)
        pen = QPen(QColor(_BLUE), 1.0 / (scale or 1.0))
        painter.setPen(pen)
        fill = QColor(_BLUE); fill.setAlpha(110)
        painter.setBrush(QBrush(fill))
        painter.drawPath(self._sel_outline)


def _cubic_axis_extrema(p0: float, c1: float, c2: float, p3: float):
    """한 축(x 또는 y)에서 3차 베지어가 극값을 갖는 t(∈[0,1])들을 반환.
    B'(t)=0 → A t² + B t + C = 0 (A=−p0+3c1−3c2+p3의 미분 계수). 근만 반환(끝점 0·1은 콜러가 포함)."""
    a = c1 - p0
    b = c2 - c1
    c = p3 - c2
    A = a - 2 * b + c
    B = 2 * (b - a)
    C = a
    ts = []
    if abs(A) < 1e-9:
        if abs(B) > 1e-9:
            ts.append(-C / B)
    else:
        disc = B * B - 4 * A * C
        if disc >= 0:
            sq = math.sqrt(disc)
            ts.append((-B + sq) / (2 * A))
            ts.append((-B - sq) / (2 * A))
    return [t for t in ts if 0.0 < t < 1.0]


def _cubic_bezier_bbox(p1: QPointF, c1: QPointF, c2: QPointF, p2: QPointF) -> QRectF:
    """3차 베지어 곡선의 '타이트한' 경계 사각형(제어점 볼록껍질이 아니라 곡선이 실제로 지나는 범위).
    각 축에서 극값 t + 끝점(0·1)의 곡선 좌표를 모아 min/max."""
    def eval_at(t, a, b, cc, d):
        mt = 1.0 - t
        return (mt * mt * mt * a + 3 * mt * mt * t * b
                + 3 * mt * t * t * cc + t * t * t * d)

    xs = [p1.x(), p2.x()]
    ys = [p1.y(), p2.y()]
    for t in _cubic_axis_extrema(p1.x(), c1.x(), c2.x(), p2.x()):
        xs.append(eval_at(t, p1.x(), c1.x(), c2.x(), p2.x()))
    for t in _cubic_axis_extrema(p1.y(), c1.y(), c2.y(), p2.y()):
        ys.append(eval_at(t, p1.y(), c1.y(), c2.y(), p2.y()))
    return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))


# [Phase 6 M4-1] 화살표 라벨 정밀화 — 선-텍스트 갭을 좁히고(패딩 축소), 수직 오프셋을
# Lucid/FigJam처럼 3위치(선 위 / 한쪽 / 반대쪽)로만 제한한다. 선 따라 슬라이드(t)는 유지.
_LABEL_SIDE_GAP = 2.0   # 라벨을 옆으로 뺄 때 텍스트-선 사이 여백(px). 좁을수록 붙는다.


def _snap_label_off(n: QPointF, raw_off: float, br: QRectF) -> float:
    """수직 오프셋을 3위치 중 하나로 스냅: 선 위(0) / 한쪽(+D) / 반대쪽(-D).
    D = 라벨의 법선 방향 반너비 + 여백 → 옆 위치에서도 선과 살짝만 띄운다(과한 간격 제거).
    n=경로 접점의 왼쪽 단위법선, br=라벨 내용 사각형. |off|가 D 절반 미만이면 선 위로 흡수."""
    half = abs(n.x()) * br.width() / 2.0 + abs(n.y()) * br.height() / 2.0
    D = half + _LABEL_SIDE_GAP
    if abs(raw_off) < D * 0.5:
        return 0.0
    return D if raw_off > 0 else -D


class _ArrowItem(_LabelMixin, _HandleResizeMixin, QGraphicsItem):
    """선 + 끝점 삼각형 화살촉. 머리 방향(head_at_end) 선택 가능."""

    def __init__(self, color: QColor, width: int, head_at_end: bool = True):
        super().__init__()
        self._p1 = QPointF(0, 0)
        self._p2 = QPointF(0, 0)
        self._ctrl1 = None     # 3차 베지어 제어점 2개(None,None=직선). 로컬(=씬) 좌표.
        self._ctrl2 = None
        self._bend_idx = 0     # 드래그 중인 bend 핸들(1·2, 0=없음)
        self._color = QColor(color)
        self._width = width
        self._style = Qt.PenStyle.SolidLine   # [M2 #3] 몸통 선스타일(점선 등) — 화살촉은 항상 solid
        self._head_at_end = head_at_end
        self._bind1 = None     # 지속 연결: 끝점0이 묶인 도형(_RectItem/_EllipseItem) or None
        self._bind2 = None     # 끝점1이 묶인 도형 or None
        self._bind1_pt = None  # 그 도형의 '로컬 좌표' 부착점(고정) — 도형 이동/스케일 시 mapToScene로 추종
        self._bind2_pt = None
        # [우리 확장] 라벨 위치 = 곡선 길이 정규화 t(0~1) + 수직 오프셋 off (sarrow와 동일 FigJam/Lucid).
        self._label_t = 0.5
        self._label_off = 0.0
        self._init_resize()
        self._init_label()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    # ---- 라벨: 곡선 위 t 지점 + 수직 오프셋에 완전중앙 배치, paint가 그 자리에 갭(FigJam/Lucid) ----
    def _make_label(self):
        return _ConnectorLabel(self._label_color())   # 드래그로 곡선 위 슬라이드/오프셋

    def _point_at_t_normal(self, t: float):
        """곡선 위 t 지점의 (점, 왼쪽 단위법선). 유한차분 접선으로 법선을 구한다."""
        dt = 1e-3
        a = self._point_at(max(0.0, t - dt))
        b = self._point_at(min(1.0, t + dt))
        tx, ty = b.x() - a.x(), b.y() - a.y()
        L = math.hypot(tx, ty)
        if L < 1e-9:
            return self._point_at(t), QPointF(0.0, -1.0)
        return self._point_at(t), QPointF(-ty / L, tx / L)

    def _label_anchor(self) -> QPointF:
        p, n = self._point_at_t_normal(getattr(self, "_label_t", 0.5))
        off = getattr(self, "_label_off", 0.0)
        return QPointF(p.x() + n.x() * off, p.y() + n.y() * off)

    def _project_to_curve(self, p: QPointF):
        """로컬 점 p를 곡선에 투영해 (t, 부호있는 수직오프셋). 라벨 드래그 재투영용(샘플링 최근접)."""
        N = 120
        best_t, best_d = 0.5, None
        for i in range(N + 1):
            t = i / N
            q = self._point_at(t)
            d = (p.x() - q.x()) ** 2 + (p.y() - q.y()) ** 2
            if best_d is None or d < best_d:
                best_d, best_t = d, t
        pt, n = self._point_at_t_normal(best_t)
        off = (p.x() - pt.x()) * n.x() + (p.y() - pt.y()) * n.y()
        return best_t, off

    def _reproject_label(self, proposed_topleft: QPointF) -> QPointF:
        lbl = self._label
        br = lbl._content_rect()
        center = QPointF(proposed_topleft.x() + br.width() / 2.0,
                         proposed_topleft.y() + br.height() / 2.0)
        self._label_t, raw_off = self._project_to_curve(center)
        _, n = self._point_at_t_normal(self._label_t)   # [M4-1] 3위치 스냅용 법선
        self._label_off = _snap_label_off(n, raw_off, br)
        self.update()   # 라벨만 움직여도 부모 화살표 paint(갭)가 새 위치로 다시 그려지게
        a = self._label_anchor()
        return QPointF(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0)

    def _sync_label(self):
        """라벨을 곡선 위 앵커에 완전중앙 배치(선 위) — paint가 그 자리에 갭을 낸다."""
        if not self._label_alive():
            return
        a = self._label_anchor()
        br = self._label._content_rect()
        self._label._syncing = True
        self._label.setPos(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0)
        self._label._syncing = False

    _LABEL_GAP_PAD = 2.0   # [M4-1] 선-텍스트 갭 축소(5→2). 라벨 둘레로 선을 비우는 여유.

    def _label_gap_rect(self):
        """라벨이 차지하는 로컬 사각형(+패딩). paint에서 이 안의 선(직선/곡선)을 비운다(FigJam 갭)."""
        if not self.has_label():
            return None
        lbl = self._label
        br = lbl._content_rect()
        pos = lbl.pos()
        pad = self._LABEL_GAP_PAD
        return QRectF(pos.x() + br.x() - pad, pos.y() + br.y() - pad,
                     br.width() + 2 * pad, br.height() + 2 * pad)

    def _label_color(self) -> QColor:
        return QColor(self._color)

    def set_points(self, p1: QPointF, p2: QPointF):
        self.prepareGeometryChange()
        self._p1, self._p2 = p1, p2
        self.update()
        self._sync_label()

    # ---- [우리 확장 · 화살표 통합] 직선 ↔ 곡선 -------------------------------
    # 「직선」과 「곡선」은 별개 종류가 아니라 이 한 객체의 두 상태다(제어점 없음/있음).
    # 미니툴바의 종류 선택이 이 둘을 호출하고, 클래스가 바뀌는 건 「직각」뿐이다.
    _BOW_FRAC = 0.22   # 자유 화살표를 곡선으로 만들 때 부풀리는 정도(선분 길이 대비)

    def apply_straight(self):
        """곧게 편다 — 제어점을 버린다(미니툴바 「직선」)."""
        self.prepareGeometryChange()
        self._ctrl1 = self._ctrl2 = None
        self.update()
        self._sync_label()

    def apply_curved(self):
        """휘게 한다(미니툴바 「곡선」). 끝점이 도형에 붙어 있으면 그 바깥 법선을 이탈·도착 접선으로
        쓴 S자 — 그릴 때의 자동 S자와 같은 규칙(k=clamp(dist/2, 30, 200)). 양끝이 자유면 선분
        수직으로 완만히 부풀린 활. 너무 짧으면(<8px) 곡선이 의미 없어 그대로 둔다."""
        p1, p2 = self._p1, self._p2
        dist = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        if dist < 8:
            return
        self.prepareGeometryChange()
        ux, uy = (p2.x() - p1.x()) / dist, (p2.y() - p1.y()) / dist
        n1 = None if self._bind1 is None else _nearest_border(self._bind1, self.mapToScene(p1))[1]
        n2 = None if self._bind2 is None else _nearest_border(self._bind2, self.mapToScene(p2))[1]
        if n1 is None and n2 is None:
            off = dist * self._BOW_FRAC
            nx, ny = -uy, ux
            self._ctrl1 = QPointF(p1.x() + ux * dist / 3 + nx * off,
                                  p1.y() + uy * dist / 3 + ny * off)
            self._ctrl2 = QPointF(p2.x() - ux * dist / 3 + nx * off,
                                  p2.y() - uy * dist / 3 + ny * off)
        else:
            k = max(30.0, min(dist * 0.5, 200.0))
            ex, ey = (n1.x(), n1.y()) if n1 is not None else (ux, uy)
            bx, by = (n2.x(), n2.y()) if n2 is not None else (-ex, -ey)
            self._ctrl1 = QPointF(p1.x() + ex * k, p1.y() + ey * k)
            self._ctrl2 = QPointF(p2.x() + bx * k, p2.y() + by * k)
        self.update()
        self._sync_label()

    def set_head_at_end(self, value: bool):
        self._head_at_end = value
        self.update()

    def flip_head(self):
        self.set_head_at_end(not self._head_at_end)

    def apply_style(self, style):   # [M2 #3] 몸통 선스타일(점선 등)
        self._style = style
        self.update()

    def clone(self):
        c = _ArrowItem(QColor(self._color), self._width, self._head_at_end)
        c._style = self._style
        c.set_points(QPointF(self._p1), QPointF(self._p2))
        if self._ctrl1 is not None:
            c._ctrl1 = QPointF(self._ctrl1)
            c._ctrl2 = QPointF(self._ctrl2)
        c._bind1, c._bind2 = self._bind1, self._bind2  # 지속 연결 바인딩 유지
        c._bind1_pt = None if self._bind1_pt is None else QPointF(self._bind1_pt)
        c._bind2_pt = None if self._bind2_pt is None else QPointF(self._bind2_pt)
        c._label_t, c._label_off = self._label_t, self._label_off   # 라벨 위치(t·off) 유지
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 끝점·제어점을 씬변형(곡선 형태 보존). 바인딩 부착점은
    # 도형쪽 리베이크가 별도로 보정하므로 여기서 건드리지 않는다.
    def _capture_geom_local(self):
        return (QPointF(self._p1), QPointF(self._p2),
                None if self._ctrl1 is None else QPointF(self._ctrl1),
                None if self._ctrl2 is None else QPointF(self._ctrl2))

    def _apply_geom_local(self, g):
        self.prepareGeometryChange()
        self._p1, self._p2 = QPointF(g[0]), QPointF(g[1])
        self._ctrl1 = None if g[2] is None else QPointF(g[2])
        self._ctrl2 = None if g[3] is None else QPointF(g[3])
        self._sync_label()

    def _capture_binds(self):
        return (self._bind1, None if self._bind1_pt is None else QPointF(self._bind1_pt),
                self._bind2, None if self._bind2_pt is None else QPointF(self._bind2_pt))

    def _apply_binds(self, b):
        self._bind1, self._bind1_pt = b[0], (None if b[1] is None else QPointF(b[1]))
        self._bind2, self._bind2_pt = b[2], (None if b[3] is None else QPointF(b[3]))

    def rebake_scene(self, fn):
        self.prepareGeometryChange()
        self._p1 = self._rebake_pt(fn, self._p1)
        self._p2 = self._rebake_pt(fn, self._p2)
        if self._ctrl1 is not None:
            self._ctrl1 = self._rebake_pt(fn, self._ctrl1)
            self._ctrl2 = self._rebake_pt(fn, self._ctrl2)
        self._sync_label()
        self.update()

    # ---- 끝점(양끝 이동) 핸들 -------------------------------------------
    def _uses_endpoints(self):
        return True

    def _connects_to_border(self):
        return True  # 끝점을 뗐다 도형 테두리 근처로 다시 가져가면 재스냅

    def _endpoints(self):
        return [self._p1, self._p2]

    def _set_endpoint(self, idx, p):
        # 끝점을 옮길 때 곡선이면 그 쪽 제어점도 같은 delta로 따라가게 해 곡선 형태·접선을 유지.
        p = QPointF(p)
        if idx == 0:
            if self._ctrl1 is not None:
                self._ctrl1 = self._ctrl1 + (p - self._p1)
            self._p1 = p
        else:
            if self._ctrl2 is not None:
                self._ctrl2 = self._ctrl2 + (p - self._p2)
            self._p2 = p
        self._sync_label()   # 끝점(및 곡선 delta) 이동 시 라벨을 새 중점으로

    def _move_endpoint_with_snap(self, idx, local_p):
        # 끝점을 테두리에 재스냅하면 생성 때처럼 바깥 법선으로 제어점을 다시 잡아 S자(수직 도착/이탈)
        # 복원, 테두리 밖이면 끝점만 이동(수동으로 구부린 곡선은 delta 추종으로 보존).
        # 지속 연결: 스냅되면 그 도형의 '그 지점'(로컬 좌표)에 고정 바인딩,
        # 멀리 끌어 스냅 안 되면 바인딩 해제(unbind). 곡선은 기존 스냅 곡선 로직 유지.
        snapped = self._endpoint_border_snap(local_p)
        if snapped is None:
            self.set_bound(idx, None)
            self._set_endpoint(idx, local_p)
            return
        shape = snapped[2]
        if shape is not None:   # [M4-2b] 도형이면 지속 바인딩, 선·화살표(shape=None)면 기하 스냅만
            self.set_bound(idx, shape, shape.mapFromScene(self.mapToScene(snapped[0])))
        else:
            self.set_bound(idx, None)
        self._set_endpoint(idx, snapped[0])
        self._recompute_snap_curve(idx, snapped[1])

    # ---- 지속 연결(persistent connection) — 고정 부착점 방식 --------------
    def _bound(self, idx):
        return self._bind1 if idx == 0 else self._bind2

    def _bind_pt(self, idx):
        return self._bind1_pt if idx == 0 else self._bind2_pt

    def set_bound(self, idx, shape, local_pt=None):
        """끝점 idx를 shape에 고정. local_pt는 shape 로컬 좌표의 부착점(None이면 해제)."""
        if idx == 0:
            self._bind1, self._bind1_pt = shape, (None if shape is None else local_pt)
        else:
            self._bind2, self._bind2_pt = shape, (None if shape is None else local_pt)

    def has_binding(self) -> bool:
        return self._bind1 is not None or self._bind2 is not None

    def reroute(self, pin_pred=None, *, fast=False, defer_route=False) -> bool:
        """바인딩된 끝점을 '도형의 고정 부착점'(로컬→씬)으로 추종. 변경 있었으면 True.
        곡선은 재계산하지 않는다 — _set_endpoint가 제어점을 delta로 끌고 가 사용자가 그린 곡선을 보존.
        pin_pred(idx)가 False면 재고정 안 함(강체). 무변경이면 geometry 미변경으로 되먹임 루프 차단.
        `fast`/`defer_route`는 받기만 하고 무시한다 — 곡선은 애초에 A* 재라우팅을 안 하므로
        (`_PolyArrowItem.reroute`와 호출부(`host_canvas._on_scene_changed`)를 공유하기 위한
        시그니처 정합 목적)."""
        if not self.has_binding():
            return False
        changed = False
        for idx in (0, 1):
            sh = self._bound(idx)
            pt = self._bind_pt(idx)
            if sh is None or pt is None or sh.scene() is None:
                continue
            if pin_pred is not None and not pin_pred(idx):
                continue
            target = self.mapFromScene(sh.mapToScene(pt))   # 부착점의 현재 씬위치 → 화살표 로컬
            cur = self._endpoints()[idx]
            if abs(target.x() - cur.x()) > 1e-6 or abs(target.y() - cur.y()) > 1e-6:
                self._set_endpoint(idx, target)   # 제어점도 같은 delta로 따라감(곡선 보존)
                changed = True
        if changed:
            self.prepareGeometryChange()
            self.update()
        return changed

    def _scene_dir_to_local(self, d_scene: QPointF) -> QPointF:
        """scene 방향벡터 → 로컬 방향벡터(회전·스케일 반영, 위치 오프셋 제거)."""
        o = self.mapFromScene(QPointF(0.0, 0.0))
        v = self.mapFromScene(d_scene)
        return QPointF(v.x() - o.x(), v.y() - o.y())

    def _endpoint_border_normal(self, idx):
        """끝점 idx가 지금 도형 테두리 근처면 그 바깥 법선(scene), 아니면 None."""
        snapped = self._endpoint_border_snap(self._endpoints()[idx])
        return snapped[1] if snapped is not None else None

    def _recompute_snap_curve(self, dragged_idx, n_dragged_scene):
        # 두 끝의 바깥 법선(scene)을 모아 생성 때(_update_arrow_draw)와 같은 공식으로 제어점 재계산.
        # 드래그한 끝은 방금 스냅한 법선, 반대 끝은 여전히 테두리 위인지 재조회.
        normals = [None, None]
        normals[dragged_idx] = n_dragged_scene
        normals[1 - dragged_idx] = self._endpoint_border_normal(1 - dragged_idx)
        p1, p2 = self._p1, self._p2
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        dist = math.hypot(dx, dy)
        if (normals[0] is None and normals[1] is None) or dist < 8:
            self._ctrl1 = self._ctrl2 = None
            return
        k = max(30.0, min(dist * 0.5, 200.0))
        if normals[0] is not None:
            e1 = self._scene_dir_to_local(normals[0])          # 시작 테두리 이탈 접선(바깥 법선)
        else:
            e1 = QPointF(dx / dist, dy / dist)                 # tip 향해
        if normals[1] is not None:
            e2 = self._scene_dir_to_local(normals[1])          # tip 테두리 도착 접선(바깥 법선)
        else:
            e2 = QPointF(-e1.x(), -e1.y())                     # 시작과 평행(부드러운 S)
        self._ctrl1 = QPointF(p1.x() + e1.x() * k, p1.y() + e1.y() * k)
        self._ctrl2 = QPointF(p2.x() + e2.x() * k, p2.y() + e2.y() * k)

    # ---- 곡선(3차 베지어) 헬퍼 -------------------------------------------
    _BEND_TS = (1.0 / 3.0, 2.0 / 3.0)  # bend 핸들 2개의 곡선 파라미터(t)

    def _point_straight(self, t: float) -> QPointF:
        """직선(p1→p2) 위 파라미터 t 지점."""
        p1, p2 = self._p1, self._p2
        return QPointF(p1.x() + (p2.x() - p1.x()) * t,
                       p1.y() + (p2.y() - p1.y()) * t)

    def _point_at(self, t: float) -> QPointF:
        """곡선(직선이면 직선) 위 파라미터 t 지점."""
        if self._ctrl1 is None:
            return self._point_straight(t)
        p1, p2, c1, c2 = self._p1, self._p2, self._ctrl1, self._ctrl2
        mt = 1.0 - t
        a, b = mt * mt * mt, 3 * mt * mt * t
        c, d = 3 * mt * t * t, t * t * t
        return QPointF(a * p1.x() + b * c1.x() + c * c2.x() + d * p2.x(),
                       a * p1.y() + b * c1.y() + c * c2.y() + d * p2.y())

    def _bend_handle_rect(self, which: int) -> QRectF:
        d = self._handle_px()
        c = self._point_at(self._BEND_TS[which - 1])
        return QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

    def _bend_handle_index_at(self, local_pos) -> int:
        """local 좌표가 어느 bend 핸들 안이면 그 인덱스(1·2), 아니면 0."""
        if not self._bend_active():
            return 0
        for which in (1, 2):
            if self._inflate_to_hit(self._bend_handle_rect(which)).contains(local_pos):
                return which
        return 0

    def _solve_ctrl(self, which: int, target: QPointF):
        """bend 핸들 which(1=t 1/3, 2=t 2/3)가 target을 지나도록 해당 제어점을 역산(다른 제어점 고정).
        B(1/3)=8/27·p1+12/27·c1+6/27·c2+1/27·p2, B(2/3)=1/27·p1+6/27·c1+12/27·c2+8/27·p2 에서 유도."""
        p1, p2 = self._p1, self._p2
        if which == 1:
            c2 = self._ctrl2
            self._ctrl1 = QPointF(
                (27 * target.x() - 8 * p1.x() - 6 * c2.x() - p2.x()) / 12.0,
                (27 * target.y() - 8 * p1.y() - 6 * c2.y() - p2.y()) / 12.0)
        else:
            c1 = self._ctrl1
            self._ctrl2 = QPointF(
                (27 * target.x() - p1.x() - 6 * c1.x() - 8 * p2.x()) / 12.0,
                (27 * target.y() - p1.y() - 6 * c1.y() - 8 * p2.y()) / 12.0)

    def _bend_active(self) -> bool:
        # 선택돼 있으면 어떤 도구에서든 곡선 조절 가능(끝점·회전·크기조절 핸들과 동일 정책).
        return self.isSelected()

    def _tip_and_angle(self):
        """화살촉이 놓이는 tip 점과 그 지점의 진행 방향 각도(paint와 동일 규칙)."""
        tail, tip = (self._p1, self._p2) if self._head_at_end else (self._p2, self._p1)
        if self._ctrl1 is None:
            length = math.hypot(tip.x() - tail.x(), tip.y() - tail.y())
            angle = math.atan2(tip.y() - tail.y(), tip.x() - tail.x()) if length > 1e-6 else 0.0
        else:
            C2, P3 = (self._ctrl2, self._p2) if self._head_at_end else (self._ctrl1, self._p1)
            angle = math.atan2(P3.y() - C2.y(), P3.x() - C2.x())
        return tip, angle

    def _head_size(self) -> float:
        """화살촉 크기 — 선 두께에 비례(얇으면 작게, 굵으면 크게). 최소 7로 아주 얇은
        선에서도 머리가 보이되, 옛 max(14,…) 바닥값이 얇은 선에서 머리를 불비례로
        키우던 문제를 없앤다(두께 휠 조절 시 머리도 같이 줄고 커짐)."""
        return max(self._width * 2.5, 7.0)

    def _head_points(self):
        """화살촉 삼각형 세 꼭짓점(tip + 뒤쪽 두 점)."""
        tip, angle = self._tip_and_angle()
        size = self._head_size()
        a1 = angle + math.radians(150)
        a2 = angle - math.radians(150)
        return [
            QPointF(tip),
            QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1)),
            QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2)),
        ]

    def _content_rect(self) -> QRectF:
        if self._ctrl1 is None:
            r = QRectF(self._p1, self._p2).normalized()
        else:
            # 곡선이 '실제로 지나는' 타이트 경계(제어점 볼록껍질은 S자에서 과도하게 넓어짐).
            r = _cubic_bezier_bbox(self._p1, self._ctrl1, self._ctrl2, self._p2)
        # 선 몸통은 획 반폭만 여유(둥근 캡), 화살촉은 tip에만 튀어나오므로 삼각형 꼭짓점만 합친다
        # (옛 방식은 화살촉 크기를 네 변 모두에 더해 박스가 곡선보다 과하게 넓었음).
        stroke = self._width / 2.0 + 2
        r = r.adjusted(-stroke, -stroke, stroke, stroke)
        hx = [p.x() for p in self._head_points()]
        hy = [p.y() for p in self._head_points()]
        head_r = QRectF(QPointF(min(hx), min(hy)), QPointF(max(hx), max(hy)))
        return r.united(head_r.adjusted(-2, -2, 2, 2))

    def _base_shape(self):
        # 클릭/hit 영역은 '실제 선+화살촉'만 감싼다(박스 전체가 아니라). 그래야 곡선 안쪽
        # 빈/오목 공간이 _is_empty_area에서 '비어 있음'으로 잡혀 거기에 새 주석을 그릴 수 있다.
        body = QPainterPath()
        body.moveTo(self._p1)
        if self._ctrl1 is None:
            body.lineTo(self._p2)
        else:
            body.cubicTo(self._ctrl1, self._ctrl2, self._p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._width, 10) + 4)   # 잡기 쉬운 폭
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        shape = stroker.createStroke(body)
        shape.addPolygon(QPolygonF(self._head_points()))
        if self._bend_active():   # 초록 bend 핸들도 잡을 수 있게(넉넉한 잡기 영역)
            for which in (1, 2):
                shape.addEllipse(self._inflate_to_hit(self._bend_handle_rect(which)))
        return shape

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tail, tip = (self._p1, self._p2) if self._head_at_end else (self._p2, self._p1)
        length = math.hypot(tip.x() - tail.x(), tip.y() - tail.y())
        if self._ctrl1 is None and length < 1:
            return  # 클릭만 한 0길이 직선 화살표는 머리도 그리지 않음(깜빡임 방지)

        size = self._head_size()
        pen = QPen(self._color, self._width, self._style,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        # [FigJam 갭] 라벨이 있으면 그 사각형만 클립으로 비워 선/곡선이 텍스트를 관통하지 않게 한다.
        # 클립이라 3차 베지어의 매끄러움이 그대로 유지된다(선분 근사 아님). 화살촉은 클립 복원 뒤 그린다.
        gap = self._label_gap_rect()
        if gap is not None:
            painter.save()
            big = self.boundingRect().adjusted(-2000, -2000, 2000, 2000)
            clip = QPainterPath(); clip.addRect(big)
            hole = QPainterPath(); hole.addRect(gap)
            painter.setClipPath(clip.subtracted(hole))

        if self._ctrl1 is None:
            # 직선: 선은 화살촉 밑변까지만 그린다. 짧은 화살표에서 base가 tail 뒤로 넘어가
            # 선이 거꾸로 삐져나오지 않도록 tail~tip 구간 안으로 클램프한다.
            t = max(0.0, 1.0 - (size * 0.85) / length) if length > 1 else 0.0
            base = QPointF(tail.x() + (tip.x() - tail.x()) * t,
                           tail.y() + (tip.y() - tail.y()) * t)
            painter.setPen(pen)
            painter.drawLine(tail, base)
        else:
            # 곡선: p1→c1→c2→p2 3차 베지어. 머리 방향에 맞춰 그리기 순서(P0..P3)를 정렬한다
            # (head_at_end면 p1→p2, 아니면 곡선을 뒤집어 p2→p1 — 제어점도 c2·c1 순서로 뒤집음).
            # tip 쪽을 화살촉 밑변까지 잘라 그린다(안 자르면 굵은 선 끝이 화살촉 밖으로 삐져나옴):
            # tip 접선 크기 |B'(1)|=3·|P3−C2| 로 되돌릴 dt를 근사하고 De Casteljau로 [0,te] 분할.
            if self._head_at_end:
                P0, C1, C2, P3 = self._p1, self._ctrl1, self._ctrl2, self._p2
            else:
                P0, C1, C2, P3 = self._p2, self._ctrl2, self._ctrl1, self._p1
            seg = math.hypot(P3.x() - C2.x(), P3.y() - C2.y())
            dt = min(0.5, (size * 0.85) / (3 * seg)) if seg > 1e-6 else 0.0
            te = 1.0 - dt
            ax = P0.x() + (C1.x() - P0.x()) * te; ay = P0.y() + (C1.y() - P0.y()) * te
            bx = C1.x() + (C2.x() - C1.x()) * te; by = C1.y() + (C2.y() - C1.y()) * te
            cx = C2.x() + (P3.x() - C2.x()) * te; cy = C2.y() + (P3.y() - C2.y()) * te
            dx = ax + (bx - ax) * te; dyv = ay + (by - ay) * te
            ex = bx + (cx - bx) * te; ey = by + (cy - by) * te
            fx = dx + (ex - dx) * te; fy = dyv + (ey - dyv) * te  # 곡선 위 te 지점(화살촉 밑변)
            path = QPainterPath(P0)
            path.cubicTo(QPointF(ax, ay), QPointF(dx, dyv), QPointF(fx, fy))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        if gap is not None:
            painter.restore()   # 화살촉·핸들은 클립 없이 온전히 그린다

        head = QPolygonF(self._head_points())
        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(self._color, 1, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPolygon(head)
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)

    # [선택 표시 통일 2026-08-01 → 2026-08-03 Lucid 대조] 커스텀 _paint_selection_outline·
    # 밴드 캐시(_sel_band_cache) 제거 — 화살표는 이제 선택 개수와 무관하게 항상 얇은 중심선
    # (`_paint_selection_centerline`, `_item_center_path`만 있으면 되는 가벼운 연산)이라
    # 밴드(스트로크+불리언 subtract, 무거움)를 아예 계산하지 않는다. 믹스인 기본
    # `_paint_selection_outline`이 `_paint_selection_highlight`로 위임하면 그걸로 충분.

    def _paint_handle(self, painter):
        # 크기조절·회전 핸들(믹스인) + 곡선용 bend 핸들 2개(곡선 t=1/3·2/3 지점의 초록 원).
        super()._paint_handle(painter)
        if not self._bend_active():
            return
        s = self._scale_or_1()
        painter.setPen(QPen(QColor("white"), 1.0 / s))
        painter.setBrush(QBrush(QColor(_GREEN)))
        for which in (1, 2):
            painter.drawEllipse(self._bend_handle_rect(which))

    def shape(self):
        base = super().shape()  # 믹스인: base_shape + (선택 시)크기조절·회전 핸들
        if self._bend_active():
            hp = QPainterPath()
            for which in (1, 2):
                hp.addEllipse(self._inflate_to_hit(self._bend_handle_rect(which)))
            return base.united(hp)
        return base

    def boundingRect(self) -> QRectF:
        # 실제로 칠하는 것(선택 외곽선=선두께+8, 초록 bend 핸들)이 _content_rect보다 살짝
        # 바깥으로 나가므로 boundingRect에 모두 포함한다 — 안 그러면 bend 드래그 때 무효화가
        # 누락돼 초록점 궤적 잔상이 남는다(다음 전체 리페인트 전까지).
        r = super().boundingRect()
        if self._bend_active():
            for which in (1, 2):
                r = r.united(self._inflate_to_hit(self._bend_handle_rect(which)))
        pad = 4.0 + 4.0 / self._scale_or_1()   # 외곽선 초과분 + 점선 펜 + 안티에일리어싱 여유
        return r.adjusted(-pad, -pad, pad, pad)

    def mousePressEvent(self, event):
        # bend 핸들을 회전/크기조절보다 먼저 잡는다(곡선 조절점 2개).
        idx = self._bend_handle_index_at(event.pos())
        if idx:
            self._bend_idx = idx
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._bend_idx:
            self.prepareGeometryChange()  # 제어점이 boundingRect를 바꾼다
            m = event.pos()
            if self._ctrl1 is None:
                # 직선 → 곡선: 두 제어점을 직선의 1/3·2/3 지점에서 시작(그 순간엔 여전히 직선 모양).
                self._ctrl1 = self._point_straight(self._BEND_TS[0])
                self._ctrl2 = self._point_straight(self._BEND_TS[1])
            self._solve_ctrl(self._bend_idx, m)
            # 직선-복귀 스냅: 두 제어점이 모두 직선(1/3·2/3) 위(±thresh)면 직선으로 되돌린다.
            thresh = max(6.0, self._width * 2) / self._scale_or_1()
            s1, s2 = self._point_straight(self._BEND_TS[0]), self._point_straight(self._BEND_TS[1])
            if (math.hypot(self._ctrl1.x() - s1.x(), self._ctrl1.y() - s1.y()) < thresh
                    and math.hypot(self._ctrl2.x() - s2.x(), self._ctrl2.y() - s2.y()) < thresh):
                self._ctrl1 = self._ctrl2 = None
            self.update()
            self._sync_label()   # 곡선(중점) 변형 시 라벨 재배치
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._bend_idx:
            self._bend_idx = 0
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# [우리 확장] 직선(꺾은선) 화살표 — Lucid식 직선 커넥터
#   정점 리스트 폴리라인 + 끝 화살촉. 각 정점이 드래그 핸들(끝점 machinery 재사용),
#   선택 후 세그먼트 hover로 정점 추가(Stage A2). 곡선 스플라인은 Stage B에서 얹는다.
# ---------------------------------------------------------------------------
def _point_seg_proj(p: QPointF, a: QPointF, b: QPointF):
    """점 p를 선분 ab에 정사영. (선분 위 최근접점, p까지 거리) 반환(선분 밖이면 끝점으로 클램프)."""
    abx, aby = b.x() - a.x(), b.y() - a.y()
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        t = 0.0
    else:
        t = ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / denom
        t = max(0.0, min(1.0, t))
    proj = QPointF(a.x() + abx * t, a.y() + aby * t)
    return proj, math.hypot(p.x() - proj.x(), p.y() - proj.y())


def _seg_rect_interval(a: QPointF, b: QPointF, rect: QRectF):
    """[우리 확장] 선분 a→b가 rect '내부'를 지나는 파라미터 구간 (t0, t1)를 Liang-Barsky로
    구한다. 교차 없으면 None. 화살표 선을 라벨 자리에서 끊는(FigJam 갭) 데 쓴다."""
    x0, y0 = a.x(), a.y()
    dx, dy = b.x() - x0, b.y() - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - rect.left()), (dx, rect.right() - x0),
                 (-dy, y0 - rect.top()), (dy, rect.bottom() - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None            # 축에 평행하며 슬래브 밖 → 교차 없음
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return None
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return None
                if r < t1:
                    t1 = r
    return None if t0 > t1 else (t0, t1)


class _PolyArrowItem(_LabelMixin, _HandleResizeMixin, QGraphicsItem):
    """정점 리스트로 이루어진 직선 화살표. _endpoints()로 모든 정점을 노출하므로
    _HandleResizeMixin의 끝점 드래그 machinery가 정점 이동을 그대로 처리한다."""

    def __init__(self, color: QColor, width: int, head_at_end: bool = True):
        super().__init__()
        self._pts = [QPointF(0, 0), QPointF(0, 0)]   # 정점 리스트(최소 2)
        self._color = QColor(color)
        self._width = width
        self._style = Qt.PenStyle.SolidLine   # [M2 #3] 몸통 선스타일(점선 등) — 화살촉은 항상 solid
        self._head_at_end = head_at_end
        # [A3] 지속 연결 — 양 끝(시작=idx0, 끝=idx last)만 도형에 고정 부착(중간 waypoint 제외).
        # 곡선화살표와 같은 방식(도형 로컬좌표 부착점 + scene.changed 리라우트). waypoint 삽입·삭제로
        # 인덱스가 바뀌므로 절대 idx가 아닌 '시작/끝 역할'로 저장한다.
        self._bind_start = None
        self._bind_end = None
        self._bind_start_pt = None   # 시작이 붙은 도형의 로컬 부착점
        self._bind_end_pt = None
        # [M4-4 ③ · 통합] 라우팅 스타일 — "ortho"=직교 경로, "straight"=2점 직선(대각 허용) 둘뿐이다.
        # 각짐/둥긂은 모드가 아니라 **모서리 반경(_curve_r, 0=직각)** 이 정한다 — 옛 "ortho_curved"는
        # ortho+반경>0과 같은 그림이라 모드에서 흡수했다(직각 엘보 = 반경 0 프리셋). 그리기·바인딩 시
        # _apply_routing()이 이 스타일대로 _pts를 생성하고 paint가 반경대로 모서리를 둥글린다.
        self._routing = "ortho"
        # [M4-4 ⓑ] 곡선 엘보 모서리 반경(px). 0=직각(ortho와 같은 그림), 기본 _CORNER_R.
        # 플로팅 툴바의 반경 스테퍼(host)가 이 값을 조절한다 — Lucid의 커넥터 곡선값 spinner.
        self._curve_r = float(self._CORNER_R)
        # [Stage1] Lucid식 직교 자동 라우팅. True면 중간 정점(_pts[1:-1])은 라우터 소유물 —
        # 양끝 부착점에서 매 reroute마다 엘보로 재계산된다. [M4-4] 세그먼트를 드래그하면 False로
        # 내려가 '수동 직교 폴리라인'이 된다(끝점만 follow, 내부는 사용자 소유).
        self._auto_route = False
        # [경유지 힌트(2f)] 자동라우팅을 '유지'하면서 경로를 이 점 근처로 지나가게 강제하는 힌트.
        # 화살표당 최대 1개(리스트지만 길이 0 또는 1 — 직렬화 형식만 재사용, 2026-07-20 실측으로
        # 단일 제한: 여러 개 허용했더니 드래그할수록 힌트가 누적돼 계단식으로 지저분해졌다).
        # 상대좌표는 양 끝점 중점 기준 scene 오프셋 — 도형이 움직이면 커넥터와 함께 평행이동.
        # 중간 정점을 드래그하면 freeze 대신 힌트로 교체 커밋되고, 직선경로 근처로 되끌면 제거된다.
        self._route_hints = []
        self._hint_dragging = False       # 힌트 정점 드래그 진행 중(build_elbow 클로버 방지 가드)
        self._hint_undo = None            # 힌트 커밋 undo 스냅샷
        # [우리 확장] 라벨 위치를 절대좌표가 아니라 경로 길이 정규화 t(0~1)+수직 오프셋 off로 소유.
        # FigJam/Lucid식 — 리라우트돼도 라벨이 비율 자리를 지킨다(절대좌표면 재라우팅 때 튐).
        # 드래그하면 _reproject_label이 t·off를 갱신하고, paint가 그 자리에 선 갭을 낸다.
        self._label_t = 0.5
        self._label_off = 0.0
        # [성능 최적화 2026-08-08] `_content_rect`/`boundingRect` 메모이즈용 버전 카운터 —
        # 아래 `prepareGeometryChange()` 재정의 주석 참조. 2026-08-01엔 "무효화 지점을 전부
        # 놓치지 않을 자신이 없다"며 이 캐시를 명시적으로 보류했었다(`docs/history/2026-08.md`
        # "화살표 boundingRect 최적화" 항목) — 이번엔 그 우려를 해소할 근거가 있어 재검토했다:
        # `_pts`/`_width`/`_curve_r`/`_head_at_end`를 바꾸는 15개 지점 전부(끝점 드래그·세그먼트
        # 드래그·경유지 힌트·리베이크·apply_width 등)와 선택 상태 변경(`_HandleResizeMixin.
        # itemChange`)이 이미 `self.prepareGeometryChange()`를 호출한다 — Qt 자신이 "이 시점
        # 이후 boundingRect가 달라질 수 있다"를 요구하는 표준 계약이라 이미 다 지켜지고 있었다.
        # 즉 새 무효화 훅을 15곳에 추가하는 게 아니라, **이미 완비된 단일 지점**(prepareGeometryChange
        # 자신)에 올라타 캐시를 무효화한다 — 지점을 하나라도 놓치면 그 자체로 오늘도 이미
        # 버그(Qt 공간 인덱스가 stale)였을 것이므로, 이 캐시가 새로 만드는 위험은 없다.
        self._geom_version = 0
        self._content_rect_cache = None   # (version, QRectF) | None
        self._bounds_rect_cache = None    # (version, view_zoom, QRectF) | None — zoom도 키에 포함
        # [성능 최적화 2026-08-09, 4단계] `_head_points()`/`_trimmed_body_pts()`도 같은 계약
        # (`_pts`/`_width`/`_head_at_end`에만 의존, 줌 무관)이라 같은 `_geom_version` 키로
        # 메모이즈한다 — `_content_rect()`는 이미 이렇게 캐시돼 있었지만 `paint()`는 매 렌더마다
        # 이 둘을 직접 다시 불러 삼각함수·hypot를 반복했다(프로파일 실측: render_fit 시나리오에서
        # _PolyArrowItem.paint가 전체 cumtime의 46%, 그중 _head_points 7.6%/_trimmed_body_pts
        # 5.4%). "정적 화면을 여러 프레임 다시 그림"(뷰 렌더·줌·팬)에서 반복 계산을 없앤다.
        self._head_pts_cache = None       # (version, [QPointF x3]) | None
        self._trimmed_pts_cache = None    # (version, [QPointF...]) | None
        self._init_resize()
        self._init_label()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    def prepareGeometryChange(self):
        # [성능 최적화 2026-08-08] 위 __init__ 주석 참조 — 이 메서드는 이미 모든 기하 변경
        # 지점에서 호출되고 있었다(재정의 전 grep으로 15곳 전수 확인). 그 호출을 그대로 캐시
        # 무효화 신호로 재사용한다(줌 변화는 scene.changed를 안 타므로 여기 대신 boundingRect가
        # 직접 vz를 캐시 키에 넣어 비교 — `docs/pitfalls.md` "scene.changed는 순수 뷰 트랜스폼을
        # 안 탄다" 참조).
        # [실사용 버그 2026-08-09, 화살촉 찌그러짐] `super().prepareGeometryChange()`는 Qt
        # 내부적으로 scene 공간인덱스의 '옛 영역'을 무효화하려고 **이 호출 시점의** `boundingRect()`
        # (→ `_content_rect()` → `_head_points()`)를 동기 호출한다(계측으로 확인: build_elbow()
        # 중 `self._pts`가 아직 옛 2점 상태일 때 `boundingRect()`가 실제로 불림). 예전 순서
        # (버전 증가 → super() 호출)에선 이 동기 호출이 '이미 증가된 새 버전' 번호로 옛 `_pts`
        # 기준 머리 삼각형을 캐시에 박아버렸다 — 호출부는 관례대로 `prepareGeometryChange()`
        # 직후 `self._pts = new_val`로 진짜 새 기하를 대입하지만, 캐시는 이미 "새 버전"으로
        # 도장을 찍어 그 뒤로 다시는 무효화되지 않는다(다음 기하 변경 때 또 한 버전 밀려 반복).
        # 결과: 화살표를 옮기면(끝점 재스냅·라우팅 재계산 등 `_pts` 교체가 있는 모든 경로) 머리
        # 삼각형이 매번 '한 세대 전' 각도로 그려져 몸통과 어긋난 비대칭 모양이 됐다(실사용 스샷
        # 재현). 해법은 순서를 뒤집는 것뿐이다 — super() 호출(및 그 안의 동기 boundingRect())을
        # **옛 버전 번호가 아직 살아있는 동안** 먼저 끝내고, 그다음에 버전을 올린다. 그러면 이
        # 동기 호출로 캐시되는 값은 '옛 버전' 딱지가 붙어, 이어지는 `self._pts` 교체 후 다음
        # `_head_points()` 호출이 버전 불일치로 정상 재계산된다.
        super().prepareGeometryChange()
        self._geom_version += 1

    # ---- 정점 = 끝점 핸들(재사용) --------------------------------------
    def _uses_endpoints(self):
        return True

    def _handle_indices(self):
        # [M4-4] 양끝(시작·끝)만 사각 핸들로 노출 — 중간 정점은 세그먼트 드래그가 관리(직교 유지).
        end = len(self._pts) - 1
        return [0] if end == 0 else [0, end]

    _ROUTE_CLEARANCE = 12.0   # [Stage2] 라우팅이 장애물에서 유지할 여유(scene 단위)
    # [Stage3 철회 — 실조건 2026-07-26] 화살표-화살표 soft 회피(_ARROW_CROSS_PENALTY·
    # _obstacle_arrow_segs)를 뺐다. 라우터 입력에서 '다른 화살표'를 없애 **경로가 화살표 집합과
    # 무관**해진다. 그래야 ⓐ 같은 포트를 이으면 선점 화살표 유무와 상관없이 늘 같은 경로가 나오고
    # ⓑ 화살표를 지워도 남은 화살표가 제멋대로 재계산되지 않는다(사용자 의도 보존 > 자동 미화).
    # 대가: 밀집 도면 교차 증가(login_flow.ecad 실측 3→7). 정리는 세그먼트 드래그·경유지 힌트·
    # 정렬/분배 같은 수동 수단이 맡는다. _route_ortho/_astar_ortho의 avoid_segs·cross_penalty
    # 인자는 남겨 뒀다(기본값 비활성) — 되살릴 땐 아래 라우팅 호출 3곳에 다시 넘기면 된다.

    # ---- [A3] 지속 연결(도형 테두리 부착) — 곡선화살표 인프라 재사용 --------
    def _connects_to_border(self):
        return True   # 끝점을 도형 테두리 근처로 가져가면 재스냅·바인딩

    def _bound(self, idx):
        if idx == 0:
            return self._bind_start
        if idx == len(self._pts) - 1:
            return self._bind_end
        return None

    def _bind_pt(self, idx):
        if idx == 0:
            return self._bind_start_pt
        if idx == len(self._pts) - 1:
            return self._bind_end_pt
        return None

    def set_bound(self, idx, shape, local_pt=None):
        """끝점(시작/끝)만 shape에 고정. 중간 정점 idx는 무시."""
        if idx == 0:
            self._bind_start, self._bind_start_pt = shape, (None if shape is None else local_pt)
        elif idx == len(self._pts) - 1:
            self._bind_end, self._bind_end_pt = shape, (None if shape is None else local_pt)

    def has_binding(self) -> bool:
        return self._bind_start is not None or self._bind_end is not None

    def _move_endpoint_with_snap(self, idx, local_p):
        # 양 끝점만 테두리에 스냅·바인딩(중간 waypoint는 자유 이동). 멀리 끌면 unbind.
        # [실사용 버그 2026-07-29 5차 — 재설계] 끝점 드래그를 '새로 그리기'와 동일하게 취급한다
        # (deep-interview 확정 — 조금 전 정한 '스텁만 재정렬(다른 구간 보존)'을 뒤집음). 이유:
        # 그 결정은 '무관한 변경'(다른 도형 삭제 등)에 손대지 않은 경로가 바뀌면 안 된다는
        # 취지였는데, 지금은 사용자가 직접 이 화살표의 끝점을 옮기는 중이라 그 취지가 적용되지
        # 않는다 — 오히려 새 화살표를 그릴 때 이미 라이브 A* 미리보기를 쓰면서 기존 화살표
        # 끝점 이동만 다르게(마지막 관절만 patch) 다루는 게 일관성이 없다는 사용자 지적을 반영.
        # 옛 중간 정점을 그대로 두고 그중 하나만 옮기면(스턱루프였던 이전 방식) 옛 목적지 기준
        # 중간점들이 새 목적지와 무관해져 사선/우회가 남는다 — 아예 버리고 두 끝점만으로
        # set_ortho_preview와 동일하게 _apply_routing()에 전부 위임하면 이 문제 자체가 없다.
        is_end = idx == 0 or idx == len(self._pts) - 1
        other_idx = (len(self._pts) - 1) if idx == 0 else 0
        other_pt = QPointF(self._pts[other_idx])
        snapped = self._endpoint_border_snap(local_p) if is_end else None
        if snapped is None:
            if is_end:
                self.set_bound(idx, None)
            target = local_p
        else:
            shape = snapped[2]
            if shape is not None:   # [M4-2b] 도형이면 지속 바인딩, 선·화살표(shape=None)면 기하 스냅만
                self.set_bound(idx, shape, shape.mapFromScene(self.mapToScene(snapped[0])))
            else:
                self.set_bound(idx, None)
            target = snapped[0]
        if is_end and self._is_ortho():
            self._pts = [target, other_pt] if idx == 0 else [other_pt, target]
            self._apply_routing()
        else:
            self._set_endpoint(idx, local_p if snapped is None else snapped[0])

    def reroute(self, pin_pred=None, *, fast=False, defer_route=False) -> bool:
        """바인딩된 끝(시작·끝)을 도형의 고정 부착점(로컬→씬)으로 추종. 변경 있으면 True.
        [성능계획 2-B, 2026-08-15] `defer_route=True`면 **끝점 추종까지만 하고 A* 재라우팅
        (`_apply_routing`)은 건너뛴다.** 드래그하는 동안 쓰는 모드로, 화살표는 도형에 계속
        붙어 따라오지만 꺾인 경로는 직전 모양을 유지한다(결정 ⓐ: 드래그 중 품질 저하 허용).
        놓는 순간 호출부가 `defer_route` 없이 한 번 더 돌려 정확한 경로를 복원한다(결정 ⓑ).
        1-0 실측 근거: 1000개 문서에서 도형 1개 드래그 916.6ms 중 순수 렌더는 142.3ms뿐이고
        나머지 대부분이 이 A*였다.
        pin_pred(idx)=False면 재고정 안 함(강체). 무변경이면 되먹임 루프 차단.
        [Stage1] 자동 라우팅(_auto_route)이고 양끝 모두 바인딩이면 끝점 추종 후 직교 엘보를 재계산.
        [성능 최적화 2026-08-11] `fast=True`면 `_apply_routing`/`_route_ortho`에 그대로
        전달돼 클리어런스 폴리시 탐색을 건너뛴다(정확성 무영향) — 호출부(`host_canvas.
        _on_scene_changed`)가 한 프레임에 reroute가 몰리는 상황(그룹 드래그)이라고 판단할
        때만 켠다.
        [성능 최적화 2026-08-13] 양끝 도형이 둘 다 선택돼 정확히 같은 델타로 함께 움직이는
        중이면(다중선택 그룹 드래그, 화살표 자신은 미선택) 경로의 상대 기하가 그대로 보존되므로
        A* 재탐색 없이 `_pts` 전체를 그 델타만큼 평행이동만 한다 — 결과는 아래 일반 경로가
        내놓는 것과 동일하되 비용은 O(정점 수). cProfile 실측(도형 350·화살표 168·291개
        선택 드래그): reroute당 A* 재계산 840→280회, 프레임당 2677→1198ms(2.2배). `pin_pred`가
        이미 다른 강체 판정(화살표 자신도 선택돼 Qt가 직접 옮기는 경우)을 내린 끝점은 건드리지
        않는다 — 그 경로는 화살표 자신의 setPos가 이미 위치를 옮겨둔 별개 메커니즘이라 여기서
        또 손대면 이중 이동이 된다."""
        if not self.has_binding():
            return False
        end_idx = len(self._pts) - 1
        if pin_pred is None or (pin_pred(0) and pin_pred(end_idx)):
            sh0, sh1 = self._bound(0), self._bound(end_idx)
            pt0, pt1 = self._bind_pt(0), self._bind_pt(end_idx)
            if (sh0 is not None and sh1 is not None and pt0 is not None and pt1 is not None
                    and sh0.scene() is not None and sh1.scene() is not None
                    and sh0.isSelected() and sh1.isSelected()):
                t0 = self.mapFromScene(sh0.mapToScene(pt0))
                t1 = self.mapFromScene(sh1.mapToScene(pt1))
                d0 = t0 - self._pts[0]
                d1 = t1 - self._pts[end_idx]
                if abs(d0.x() - d1.x()) <= 1e-6 and abs(d0.y() - d1.y()) <= 1e-6:
                    if abs(d0.x()) > 1e-6 or abs(d0.y()) > 1e-6:
                        self._pts = [QPointF(p.x() + d0.x(), p.y() + d0.y()) for p in self._pts]
                        self.prepareGeometryChange()
                        self.update()
                        self._sync_label()
                        return True
                    return False
        changed = False
        manual_ortho = self._is_ortho() and not self._auto_route and len(self._pts) >= 3
        for idx in (0, len(self._pts) - 1):
            sh = self._bound(idx)
            pt = self._bind_pt(idx)
            if sh is None or pt is None or sh.scene() is None:
                continue
            if pin_pred is not None and not pin_pred(idx):
                continue
            target = self.mapFromScene(sh.mapToScene(pt))
            cur = self._pts[idx]
            if abs(target.x() - cur.x()) > 1e-6 or abs(target.y() - cur.y()) > 1e-6:
                # [M4-4 ⑦] 수동 직교 폴리라인(세그먼트 드래그 후)은 끝점을 따라가되 인접 정점을 함께
                # 옮겨 첫/끝 변(스텁)을 직교로 유지한다(auto_route면 아래 _apply_routing이 통째로 재계산).
                if manual_ortho:
                    nb_idx = 1 if idx == 0 else len(self._pts) - 2
                    nb = self._pts[nb_idx]
                    vertical = abs(cur.x() - nb.x()) <= abs(cur.y() - nb.y())  # 스텁이 세로(x 공유)?
                    self._pts[nb_idx] = (QPointF(target.x(), nb.y()) if vertical
                                         else QPointF(nb.x(), target.y()))
                self._set_endpoint(idx, target)
                changed = True
        # [M4-4 ⑦] 자동 라우팅이면 라우팅 스타일대로 재계산(straight=2점 유지 / ortho=엘보 재계산).
        # 한쪽만 바인딩돼도(has_binding) 재적용해 도형 이동 시 직교가 깨지지 않게 한다
        # (_apply_routing이 양끝 바인딩=A*, 한쪽=단순 엘보로 분기). 수동 세그먼트 편집(auto_route
        # False)은 끝점만 추종(사용자 경로 보존).
        if self._auto_route and self.has_binding() and not defer_route:
            if self._apply_routing(fast=fast):
                changed = True
        if changed:
            self.prepareGeometryChange()
            self.update()
        return changed

    def _bound_normal_scene(self, idx):
        """바인딩된 끝(idx=0 시작 / last 끝)의 도형 테두리 '바깥 단위 법선'(scene), 없으면 None.
        부착점이 정확히 테두리 위이므로 _nearest_border가 그 점의 법선을 돌려준다."""
        sh = self._bound(idx)
        pt = self._bind_pt(idx)
        if sh is None or pt is None or sh.scene() is None:
            return None
        try:
            _, n = _nearest_border(sh, sh.mapToScene(pt))
        except Exception:
            return None
        return n

    # [Stage4 철회 — 실조건 2026-07-26] 옛 _absorb_near_alignment는 두 끝의 교차축 어긋남이
    # _ALIGN_TOL(8px) 이하일 때 **부착점(bind_pt) 자체를 테두리 따라 미끄러뜨려** 미세 계단을
    # 없앴다. 그 대가가 컸다(사용자 보고 3건, 측정으로 확정):
    #   ⓐ 변 중심점(포트)에 붙였는데 도형을 옮기면 부착점이 최대 8px 밀려난다 — 네모 60·원 120·
    #      평행사변형 80건/이동 55회. 사용자가 고른 연결점은 데이터인데 라우터가 덮어썼다.
    #   ⓑ 포트가 아닌 자유 부착점은 드래그 중 붙었다 떨어졌다 하고 경로가 흔들린다(미끄러짐이
    #      매 마우스 이동마다 방향을 바꾸므로).
    # 계층이 틀렸다 — 8px 계단은 '그림'의 문제고 부착점은 '데이터'다. 그림 문제를 데이터를 고쳐
    # 해결하면 안 된다. 계단이 거슬리면 M5 정렬/분배로 도형 축을 실제로 맞추는 게 정답이다.
    # (부착점을 건드리지 않고 경로 쪽에서 계단을 흡수하는 안은 별도 과제로 남긴다.)

    def build_elbow(self, *, fast=False) -> bool:
        """[Stage1] 현재 양끝점 + 부착 변 법선으로 직교 엘보를 계산해 _pts를 교체. 변경 있으면 True.
        _pts[0]/_pts[-1](끝점)은 유지하고 중간 정점만 라우터가 생성한다.
        [경유지 힌트(2f)] _route_hints가 있으면 '출발→힌트…→도착'을 구간별로 A* 라우팅해
        힌트를 반드시 지나가되 각 구간은 계속 장애물을 자동 회피한다.
        [성능 최적화 2026-08-11] `fast=True`는 `_route_ortho`의 클리어런스 사다리(폴리시
        탐색)를 건너뛰라는 신호를 그대로 전달한다 — 정확성엔 영향 없음(`_route_ortho`
        docstring 참조), 기본 False."""
        if self._bind_start is None or self._bind_end is None:
            return False
        if self._hint_dragging:
            return False   # [경유지 힌트] 힌트 정점 드래그 중 — 라우터가 드래그 정점을 덮어쓰지 않게
        end_idx = len(self._pts) - 1
        s = self.mapToScene(self._pts[0])
        e = self.mapToScene(self._pts[end_idx])
        if abs(s.x() - e.x()) < 1e-6 and abs(s.y() - e.y()) < 1e-6:
            return False
        # [Stage4 철회] 부착점은 사용자 데이터 — 라우터가 옮기지 않는다(위 주석 참조).
        if self._route_hints:
            # [경유지 힌트(2f)] 힌트가 있으면 구간별 라우팅(내부적으로 Stage2/3 회피 동반).
            hint_scenes = [self._hint_to_scene(h) for h in self._route_hints]
            scene_pts, flags = self._route_with_hints(hint_scenes, fast=fast)
            merged, _mflag = self._dedup_hint(scene_pts, flags)
            new_local = [self.mapFromScene(p) for p in merged]
        else:
            ns = self._bound_normal_scene(0)
            ne = self._bound_normal_scene(end_idx)
            # [Stage2] 장애물(양끝 바인딩 도형 제외)을 피하는 직교 경로. 장애물이 없거나 Stage1
            # 엘보가 이미 안전하면 Stage1과 동일 결과 → 아래 무변경 가드가 되먹임 루프를 끊는다.
            mids = _route_ortho(s, e, ns, ne, self._obstacle_rects(), self._ROUTE_CLEARANCE,
                                conn_rects=self._connected_rects(), fast=fast)
            new_scene = _dedup_pts([s] + mids + [e])
            new_local = [self.mapFromScene(p) for p in new_scene]
        if len(new_local) == len(self._pts) and all(
                abs(a.x() - b.x()) <= 1e-6 and abs(a.y() - b.y()) <= 1e-6
                for a, b in zip(new_local, self._pts)):
            return False   # 동일 → 되먹임 루프 차단
        self.prepareGeometryChange()
        self._pts = new_local
        self.update()
        self._sync_label()
        return True

    # ---- [M4-4] 라우팅 스타일(#4) — 통합 경로 생성 ------------------------------
    def set_routing(self, mode: str):
        """[M4-4 #4] 라우팅 스타일 전환(straight/ortho). 자동 경로를 다시 켜고 _apply_routing으로
        즉시 재생성한다(세그먼트 수동편집 상태도 초기화). 반경(_curve_r)은 건드리지 않는다 —
        각짐/둥긂은 set_corner_radius의 몫. 옛 "ortho_curved"는 ortho 별칭으로 흡수(하위호환)."""
        if mode == "ortho_curved":
            mode = "ortho"
        if mode not in ("straight", "ortho"):
            return
        self._routing = mode
        self._auto_route = True   # 스타일 전환 = 라우터가 다시 경로 소유
        self._route_hints = []
        self.prepareGeometryChange()
        self._apply_routing()
        self.update()

    def _is_ortho(self) -> bool:
        return self._routing == "ortho"

    def _apply_routing(self, *, fast=False) -> bool:
        """[M4-4] 현재 _routing에 맞춰 _pts를 재생성(양끝점은 유지, 중간만 라우터 소유). 변경 시 True.
        · straight=2점 직선(대각 허용). · ortho=직교 경로(각짐·둥긂 무관) — 양끝 바인딩이면 build_elbow
          (A* 회피·법선·정렬흡수), 아니면 자유 끝점 사이 단순 L/HVH 엘보(_ortho_elbow).
        [성능 최적화 2026-08-11] `fast`는 `build_elbow`/`_route_ortho`로 그대로 전달(정확성
        무영향, `_route_ortho` docstring 참조)."""
        end_idx = len(self._pts) - 1
        s = self.mapToScene(self._pts[0])
        e = self.mapToScene(self._pts[end_idx])
        if self._routing == "straight":
            new_local = [self.mapFromScene(s), self.mapFromScene(e)]
        elif self._bind_start is not None and self._bind_end is not None:
            return self.build_elbow(fast=fast)   # 바인딩 직교 — 기존 A* 라우팅 재사용
        else:                            # 한쪽만 바인딩 / 완전 자유 직교
            ns = self._bound_normal_scene(0)
            ne = self._bound_normal_scene(end_idx)
            if self.has_binding():
                # 한쪽만 붙어도 build_elbow과 같은 _route_ortho로 회피(재진입·장애물·화살표) — 그리기
                # 라이브 미리보기(set_ortho_preview가 이 경로 위임)와 릴리스 결과를 일치시킨다.
                mids = _route_ortho(s, e, ns, ne, self._obstacle_rects(), self._ROUTE_CLEARANCE,
                                    conn_rects=self._connected_rects(), fast=fast)
            else:
                mids = _ortho_elbow(s, e, ns, ne)   # 완전 자유(무바인딩) = 단순 엘보(기존 유지)
            new_scene = _dedup_pts([s] + mids + [e])
            new_local = [self.mapFromScene(p) for p in new_scene]
        if len(new_local) == len(self._pts) and all(
                abs(a.x() - b.x()) <= 1e-6 and abs(a.y() - b.y()) <= 1e-6
                for a, b in zip(new_local, self._pts)):
            return False
        self.prepareGeometryChange()
        self._pts = new_local
        self.update()
        self._sync_label()
        return True

    # ---- [M4-4] 세그먼트 드래그(변 수직 이동, Lucid/FigJam 파란 세그먼트 핸들) -----------
    _SEG_HANDLE_PX = 12.0   # 세그먼트 핸들(알약) 화면 px 길이 반값 — 길쭉해 끝점 사각과 구별
    _SEG_MIN_PX = 26.0      # 이 화면 px보다 짧은 변엔 핸들 안 그림(끝점 핸들과 겹침 방지)

    def _segment_orientation(self, seg_idx: int) -> bool:
        a, b = self._pts[seg_idx], self._pts[seg_idx + 1]
        return abs(b.y() - a.y()) <= abs(b.x() - a.x())   # True=수평 변

    def _segment_handles(self):
        """[M4-4] 세그먼트 핸들을 그릴 (seg_idx, 중점 local, 수평여부) 목록. 직교 라우팅 + 충분히
        긴 변만(끝점 핸들과 겹치지 않게). straight 라우팅은 세그먼트 드래그 없음(빈 목록)."""
        if not self._is_ortho():
            return []
        s = self._scale_or_1()
        min_local = self._SEG_MIN_PX / max(s, 1e-6)
        out = []
        for i in range(len(self._pts) - 1):
            a, b = self._pts[i], self._pts[i + 1]
            if math.hypot(b.x() - a.x(), b.y() - a.y()) < min_local:
                continue
            mid = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
            out.append((i, mid, abs(b.y() - a.y()) <= abs(b.x() - a.x())))
        return out

    def _point_on_segment_pill(self, seg_idx: int, local_pt: QPointF) -> bool:
        """local_pt(그 변 위 최근접 투영점, 로컬)가 고정 알약(_segment_handles의 중점, 반경
        _SEG_HANDLE_PX) 안이면 True — [2026-08-03 Lucid 대조] press 시 변 전체 이동
        (`_begin_segment_drag`)과 부분 분할 이동(`_begin_subdivide_drag`)을 가르는 기준."""
        handles = dict((i, (mid, horiz)) for i, mid, horiz in self._segment_handles())
        h = handles.get(seg_idx)
        if h is None:
            return False
        mid, horizontal = h
        half = self._SEG_HANDLE_PX / max(self._scale_or_1(), 1e-6)
        d = abs(local_pt.x() - mid.x()) if horizontal else abs(local_pt.y() - mid.y())
        return d <= half

    def _segment_subdivide_preview_point(self, seg_idx: int, local_pt: QPointF) -> QPointF:
        """[2026-08-04 버그수정] 부분꺾임 미리보기 알약의 '고정' 위치 — local_pt(커서 투영점)가
        고정 알약(A~B 중점 M)의 어느 절반에 있는지만 보고, 그 절반 자체의 중점(A~M 또는 M~B)을
        반환한다. 커서를 계속 따라다니지 않고 절반이 바뀔 때만 위치가 바뀜 — press 시 실제
        삽입 지점(`_begin_subdivide_drag`가 항상 M에 끼움)과 그 다음 레벨에 새로 뜰 알약 자리가
        일치하도록. near_a 판정은 `_begin_subdivide_drag`와 동일 기준(A·B까지 거리 비교)."""
        a, b = self._pts[seg_idx], self._pts[seg_idx + 1]
        mid = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
        horizontal = self._segment_orientation(seg_idx)
        axis = (lambda q: q.x()) if horizontal else (lambda q: q.y())
        near_a = abs(axis(local_pt) - axis(a)) <= abs(axis(local_pt) - axis(b))
        if near_a:
            return QPointF((a.x() + mid.x()) / 2.0, (a.y() + mid.y()) / 2.0)
        return QPointF((mid.x() + b.x()) / 2.0, (mid.y() + b.y()) / 2.0)

    def _begin_subdivide_drag(self, seg_idx: int, near_local: QPointF):
        """[2026-08-03 Lucid 대조, rf 계정 Lucid 문서에서 직접 재현 확인] 알약이 아닌 위치를
        끌면 그 변의 고정 알약 자리(중점)에 새 정점을 끼워 둘로 나누고, 클릭 지점에 더 가까운
        쪽 절반만 `_begin_segment_drag`로 이동시킨다 — 원래 알약 자리는 그대로 고정 정점(앵커)
        으로 남아야 "중심(원래 알약)과 가까운 끝점 사이만" 꺾이고 반대쪽은 그대로 유지된다.
        ⚠ mid를 한 번만 끼우고 그 자리를 바로 `_begin_segment_drag`에 넘기면, 그 함수가
        '진짜 끝점(0·마지막 인덱스)'만 보호하므로 중간에 낀 mid는 그냥 이동 대상 세그먼트의
        한쪽 끝으로 취급돼 앵커 없이 같이 끌려간다(1차 구현에서 실측 발견) — mid를 앵커용
        사본과 이동용 사본으로 '두 벌' 끼워, 이동은 사본 쪽만 겪게 한다."""
        handles = dict((i, (mid, horiz)) for i, mid, horiz in self._segment_handles())
        mid, horizontal = handles[seg_idx]
        self.prepareGeometryChange()
        a, b = self._pts[seg_idx], self._pts[seg_idx + 1]
        axis = (lambda q: q.x()) if horizontal else (lambda q: q.y())
        near_a = abs(axis(near_local) - axis(a)) <= abs(axis(near_local) - axis(b))
        if near_a:
            # a쪽만 이동: [a, mid_이동용] 세그먼트를 끌고, [mid_앵커, b]는 그대로 둔다.
            self._pts.insert(seg_idx + 1, QPointF(mid))   # 이동용 사본
            self._pts.insert(seg_idx + 2, QPointF(mid))   # 고정 앵커
            self._begin_segment_drag(seg_idx)
        else:
            # b쪽만 이동: [a, mid_앵커]는 그대로, [mid_이동용, b] 세그먼트를 끈다.
            self._pts.insert(seg_idx + 1, QPointF(mid))   # 고정 앵커
            self._pts.insert(seg_idx + 2, QPointF(mid))   # 이동용 사본
            self._begin_segment_drag(seg_idx + 2)

    def _begin_segment_drag(self, seg_idx: int):
        """[M4-4] 세그먼트 드래그 시작 — 자동라우팅 해제(수동 직교)+경유힌트 폐기. 끝점(0·last)에
        닿은 변이면 그 끝점을 고정하려 복제 정점을 끼워 '움직일 수 있는 내부 변'으로 만든 뒤,
        이동할 두 정점 인덱스와 방향(수평/수직)을 기록한다. 이후 _drag_segment_to가 그 변을 수직 이동."""
        self._auto_route = False
        self._route_hints = []
        horizontal = self._segment_orientation(seg_idx)
        lo, hi = seg_idx, seg_idx + 1
        self.prepareGeometryChange()
        if lo == 0:                                  # 시작 끝점 보호
            self._pts.insert(1, QPointF(self._pts[0]))
            lo += 1
            hi += 1
        if hi == len(self._pts) - 1:                 # 끝 끝점 보호(삽입은 old last를 hi+1로 밀어냄)
            self._pts.insert(hi, QPointF(self._pts[hi]))
        self._seg_move = (lo, hi, horizontal)
        self.update()

    def _drag_segment_to(self, scene_p: QPointF):
        move = getattr(self, "_seg_move", None)
        if not move:
            return
        lo, hi, horizontal = move
        p = self.mapFromScene(scene_p)
        # [M4-4 ①b] 일직선 스냅 — 변을 끌 때 그 좌표가 양끝점·이웃 정점의 축과 가까우면 착 붙여
        # 완벽한 직선/정렬을 쉽게 만든다. 끝점과 나란해지면 U가 직선으로 붕괴.
        snap_px = 7.0 / max(self._scale_or_1(), 1e-6)
        axis = (lambda q: q.y()) if horizontal else (lambda q: q.x())
        cand = [axis(self._pts[0]), axis(self._pts[-1])]
        if lo - 1 >= 0:
            cand.append(axis(self._pts[lo - 1]))
        if hi + 1 <= len(self._pts) - 1:
            cand.append(axis(self._pts[hi + 1]))
        newc = axis(p)
        for t in cand:
            if abs(newc - t) < snap_px:
                newc = t
                break
        self.prepareGeometryChange()
        if horizontal:                               # 수평 변 → y만 이동
            self._pts[lo] = QPointF(self._pts[lo].x(), newc)
            self._pts[hi] = QPointF(self._pts[hi].x(), newc)
        else:                                        # 수직 변 → x만 이동
            self._pts[lo] = QPointF(newc, self._pts[lo].y())
            self._pts[hi] = QPointF(newc, self._pts[hi].y())
        self.update()
        self._sync_label()

    def _end_segment_drag(self):
        """드래그 종료 — 공선·중복 정점 정리(보호 삽입 잔재 접힘, 끝점은 보존)."""
        if getattr(self, "_seg_move", None) is None:
            return
        self._seg_move = None
        self.prepareGeometryChange()
        cleaned = _dedup_pts(self._pts)
        if len(cleaned) >= 2:
            self._pts = cleaned
        self.update()
        self._sync_label()

    def _paint_segment_handles(self, painter):
        """[M4-4] 각 직교 세그먼트 중점에 파란 알약 핸들(변 방향으로 길쭉). 끝점 사각 핸들과 구분."""
        if not self._endpoint_active():
            return
        handles = self._segment_handles()
        if not handles:
            return
        s = self._scale_or_1()
        half = self._SEG_HANDLE_PX / max(s, 1e-6)
        thick = 3.5 / max(s, 1e-6)   # 얇게 고정 → 길쭉한 알약(끝점 사각과 확실히 구별)
        painter.setPen(QPen(QColor("white"), 1.0 / self._scale_or_1()))
        painter.setBrush(QBrush(QColor(_BLUE)))
        for _i, mid, horizontal in handles:
            if horizontal:
                r = QRectF(mid.x() - half, mid.y() - thick, 2 * half, 2 * thick)
            else:
                r = QRectF(mid.x() - thick, mid.y() - half, 2 * thick, 2 * half)
            painter.drawRoundedRect(r, thick, thick)

    # ---- [경유지 힌트(2f)] 상대좌표 변환 · 구간별 라우팅 · 커밋 ------------------
    def _hint_midpoint_scene(self) -> QPointF:
        """힌트 상대좌표의 기준점 = 현재 양 끝점의 중점(scene). 도형이 움직이면 함께 이동."""
        s = self.mapToScene(self._pts[0])
        e = self.mapToScene(self._pts[-1])
        return QPointF((s.x() + e.x()) / 2.0, (s.y() + e.y()) / 2.0)

    def _hint_to_scene(self, h: QPointF) -> QPointF:
        m = self._hint_midpoint_scene()
        return QPointF(m.x() + h.x(), m.y() + h.y())

    def _scene_to_hint(self, ps: QPointF) -> QPointF:
        m = self._hint_midpoint_scene()
        return QPointF(ps.x() - m.x(), ps.y() - m.y())

    def _route_with_hints(self, hint_scenes, *, fast=False):
        """출발 s → 힌트들 → 도착 e를 구간별로 _route_ortho해 이어붙인 (scene 정점, hint 플래그).
        진짜 양끝만 테두리 법선 구속, 힌트점은 자유 통과. flags[i]=True면 그 정점이 힌트."""
        end_idx = len(self._pts) - 1
        s = self.mapToScene(self._pts[0])
        e = self.mapToScene(self._pts[end_idx])
        ns = self._bound_normal_scene(0)
        ne = self._bound_normal_scene(end_idx)
        obst = self._obstacle_rects()   # [Stage3 철회] 화살표는 회피 대상 아님 — 도형만
        waypts = [s] + list(hint_scenes) + [e]
        norms = [ns] + [None] * len(hint_scenes) + [ne]
        scene_pts = [s]
        flags = [False]
        for i in range(len(waypts) - 1):
            a, b = waypts[i], waypts[i + 1]
            mids = _route_ortho(a, b, norms[i], norms[i + 1], obst, self._ROUTE_CLEARANCE,
                                conn_rects=self._connected_rects(), fast=fast)
            for m in mids:
                scene_pts.append(m)
                flags.append(False)
            scene_pts.append(b)
            flags.append(i + 1 <= len(hint_scenes))   # 마지막 b(=e)만 False
        return scene_pts, flags

    @staticmethod
    def _dedup_hint(pts, flags, eps=1e-6):
        """_dedup_pts와 동일하되 '힌트 정점은 공선이어도 보존'(사용자가 다시 잡을 수 있게).
        연속 중복은 항상 접고(둘 중 하나라도 힌트면 힌트 유지), 공선 중간점은 비-힌트만 제거."""
        out_p, out_f = [pts[0]], [flags[0]]
        for p, f in zip(pts[1:], flags[1:]):
            if abs(p.x() - out_p[-1].x()) <= eps and abs(p.y() - out_p[-1].y()) <= eps:
                out_f[-1] = out_f[-1] or f
                continue
            out_p.append(p)
            out_f.append(f)
        i = 1
        while i < len(out_p) - 1:
            if out_f[i]:
                i += 1
                continue   # 힌트 정점은 접지 않는다
            a, b, c = out_p[i - 1], out_p[i], out_p[i + 1]
            cross = (b.x() - a.x()) * (c.y() - a.y()) - (b.y() - a.y()) * (c.x() - a.x())
            if abs(cross) <= eps:
                del out_p[i]
                del out_f[i]
            else:
                i += 1
        return out_p, out_f

    @staticmethod
    def _dist_to_polyline(p: QPointF, pts) -> float:
        best = float("inf")
        for i in range(len(pts) - 1):
            _proj, d = _point_seg_proj(p, pts[i], pts[i + 1])
            best = min(best, d)
        return best

    def _on_endpoint_drag_end(self, idx):
        """[경유지 힌트(2f)] 중간 정점 드래그 종료 — 드래그 위치를 힌트로 커밋(자동라우팅 유지).
        순수경로(무힌트)에 충분히 가까우면 힌트를 제거해 순수 자동으로 되돌린다.
        [단일 힌트 제한 — 2026-07-20 GUI 실측] 화살표당 힌트는 항상 최대 1개로 '교체'한다(누적 금지).
        애초 여러 힌트를 허용했더니, 이미 라우터가 만든 중간 꺾임점(힌트 아님)을 다시 잡을 때마다
        그게 별개 힌트로 또 추가돼 드래그할수록 계단식으로 지저분해졌다(실측으로 발견). 여러 지점을
        경유해야 하면 그건 자동라우팅의 영역이 아니라 완전 수동 폴리라인(waypoint 삽입)의 몫이다."""
        if not self._hint_dragging:
            # [실사용 버그 2026-07-29 5차] 힌트 드래그(중간 정점)가 아니면 끝점 드래그 —
            # _move_endpoint_with_snap이 매 프레임 _apply_routing()으로 이미 전체 재계산해
            # 두므로 여기선 추가로 할 일이 없다(새로 그리기와 동일하게 라이브==확정).
            return
        self._hint_dragging = False
        p_new = self.mapToScene(self._pts[idx])
        wo_scene, _f = self._route_with_hints([])   # 힌트 없는 순수경로 기준
        if self._dist_to_polyline(p_new, wo_scene) <= self._hint_drop_scene():
            self._route_hints = []                              # 순수경로 근처 → 힌트 제거
        else:
            self._route_hints = [self._scene_to_hint(p_new)]    # 단일 힌트로 교체(누적 아님)
        self.build_elbow()
        h = self._host()
        if self._hint_undo and h is not None:
            h.push_undo_geom(self._hint_undo)
        self._hint_undo = None

    def _obstacle_rects(self):
        """[Stage2] 라우팅이 피해야 할 장애물 사각형(scene, 축정렬 bbox). 양끝 바인딩 도형
        (출발/도착)은 제외. 원은 외접 사각형으로 근사(보수적). scene이 없으면 빈 리스트.

        [§8 항목19 F4 시도·되돌림, 2026-08-14] `scene.items()` 전체스캔을 코리도 사각형으로
        `scene.items(rect, IntersectsItemBoundingRect)` BSP 공간쿼리로 좁히는 시도를 했으나
        실측으로 역효과임을 확인해 되돌렸다. 원인: 이 프로젝트의 `boundingRect()` 구현들이
        가볍지 않다(2026-08-13 "200개+ 그룹드래그" 조사 — `_HandleResizeMixin.boundingRect()`
        →`_qc_dot_rects()`→`_shape_ports()`→`_nearest_border()` 체인이 전체비용 86%였을 정도).
        Qt의 rect 쿼리는 BSP 트리가 좁혀준 후보들의 `boundingRect()`를 하나하나 계산해 교차를
        재확인하는데, 그 계산 자체가 `scene.items()`가 하는 '포인터 리스트 그대로 반환'보다
        비쌌다 — cProfile 실측(`route_ladder_stress.ecad`, 부분선택 드래그): BSP `items()`
        호출 자체가 전체 비용의 43%(1.333초/3.105초)까지 치솟았고, `profile_obstacle_scan.py`
        (51→2051 아이템)에서도 `build_elbow`가 오히려 0.63→3.59ms(느려짐 전)에서 1.56→
        12.74ms로 후퇴했다. 근본원인: `_CORRIDOR_PAD_MIN`(400, 최소 여유)이 실사용 규모의
        도면 대부분을 이미 통째로 덮어(코리도가 좁혀주는 후보가 거의 없음) 쿼리 자체의
        오버헤드만 순수 추가됐다 — `_on_scene_changed`(host_canvas.py)가 "다건 변경(넓은
        영역)엔 전체스캔이 더 빠르다"고 이미 기록해 둔 것과 같은 함정(2026-08-08)이지만,
        거긴 그 조건을 가늠할 '변경 개수' 신호가 있어 조건부로 전환할 수 있었던 반면 여긴
        화살표 1개 호출마다인 데다 코리도가 항상 이렇게 넓어 조건부 전환의 여지가 없었다."""
        sc = self.scene()
        if sc is None:
            return []
        out = []
        for it in sc.items():
            if it is self._bind_start or it is self._bind_end:
                continue
            if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem)):
                out.append(it.mapRectToScene(it.rect()))
        return out

    def _connected_rects(self):
        """[M4-4 ⓐ] 양끝 바인딩 도형(출발/도착)의 scene bbox를 **(start|None, end|None) 2-튜플**로.
        _obstacle_rects가 회피에서 '제외'하는 바로 그 도형들이다 — 끝점이 이 도형 테두리 위라 통짜
        팽창 장애물로 못 넣기 때문. 대신 _route_ortho가 '원본 rect로 재진입/타기 판정 + stub↔stub
        A*엔 팽창본을 장애물로' 쓰는 데 이걸 받는다.
        ⚠ 리스트가 아니라 2-튜플인 이유: 타기 면제는 '그 끝점이 붙은 도형'에만 줘야 해서 어느
        rect가 출발/도착인지 알아야 한다(한쪽만 도형이면 그 자리는 None). 원·심볼은 bbox 근사라
        판정이 보수적: 실제 외곽선이 bbox 안으로 든 도형은 스텁이 팽창 bbox 안이면 base 유지."""
        return tuple(sh.mapRectToScene(sh.rect())
                     if isinstance(sh, (_RectItem, _EllipseItem, _SymbolItem)) else None
                     for sh in (self._bind_start, self._bind_end))

    # [경유지 힌트 — 2026-07-20 실측] 씬 단위 고정값(8.0)은 줌아웃 시 화면상 몇 px밖에 안 돼
    # 정밀 조작을 요구했다(사용자 피드백: "상당히 미세하게 해야 함"). _BORDER_SNAP_PX(14)와 같은
    # 관례로 화면 고정 px를 뷰 배율로 환산 — 줌과 무관하게 항상 같은 크기의 표적.
    _HINT_DROP_PX = 16.0   # 화면 px — 힌트를 순수경로 근처로 되끌면 제거되는 판정 반경

    def _hint_drop_scene(self) -> float:
        view_s = 1.0
        sc = self.scene()
        if sc is not None and sc.views():
            view_s = sc.views()[0]._view_scale()
        return self._HINT_DROP_PX / max(view_s, 1e-6)

    def _on_endpoint_drag_start(self, idx):
        # [경유지 힌트(2f)] 자동라우팅 중 '중간' 정점을 잡으면 freeze하지 않고 힌트 모드로 진입 —
        # 드래그가 끝나는 위치를 경유 힌트로 커밋해 자동라우팅을 살린 채 경로만 조정한다.
        is_middle = 0 < idx < len(self._pts) - 1
        if self._auto_route and is_middle:
            self._hint_dragging = True
            h = self._host()
            self._hint_undo = [(self, self.capture_geom())] if h is not None else None
            return
        self._hint_dragging = False
        if is_middle:
            # [Stage1] 이미 수동인 중간 정점(waypoint) 드래그 — 그대로 수동 유지.
            self._auto_route = False
            self._route_hints = []
        else:
            # [실사용 버그 2026-07-29 5차] 끝점 드래그 = 새로 그리기와 동일 취급(deep-interview
            # 확정) — auto_route를 끄지 않는다. _move_endpoint_with_snap이 매 프레임
            # _apply_routing()으로 전체 재계산하고, 드래그가 끝난 뒤에도 이 화살표가 새로 그린
            # 것처럼 계속 자동 재라우팅되길 기대하기 때문(도형이 나중에 움직여도 reroute가
            # 계속 따라감). 옛 경유 힌트만 폐기(새 목적지와는 무관해짐).
            self._route_hints = []

    def _endpoints(self):
        return self._pts

    def _set_endpoint(self, idx, p):
        self.prepareGeometryChange()
        self._pts[idx] = QPointF(p)
        self.update()
        self._sync_label()

    def set_points(self, p1: QPointF, p2: QPointF):
        """그리기용 — 2정점으로 초기화."""
        self.prepareGeometryChange()
        self._pts = [QPointF(p1), QPointF(p2)]
        self.update()
        self._sync_label()

    def set_ortho_preview(self, s_scene: QPointF, e_scene: QPointF, tip_shape=None):
        """[화살표 그리기 라이브 직각] 드래그 내내 '릴리스와 동일한' 직각 경로로 미리보기 — 단순
        엘보(도형 관통)로 그리다 릴리스 순간에만 회피로 튀던 것을 없앤다. 끝점 2개로 둔 뒤 릴리스가
        쓰는 바로 그 _apply_routing에 위임 → 미리보기==확정 보장(같은 코드).
        tip_shape: 드래그 중 끝점이 스냅된 도형(있으면). 그 도형을 끝 연결로 '라이브 바인딩'해야 —
        끝점이 그 테두리 위라 conn(재진입 회피)으로 처리돼 A* 도착노드가 유효하다. 미바인딩이면
        hard 장애물의 팽창 안에 도착점이 들어가 A*가 실패→단순 엘보 폴백(=릴리스 전 관통 버그). 떨어지면 해제."""
        self.prepareGeometryChange()
        self._pts = [self.mapFromScene(s_scene), self.mapFromScene(e_scene)]
        self.set_bound(len(self._pts) - 1, tip_shape,
                       None if tip_shape is None else tip_shape.mapFromScene(e_scene))
        self._apply_routing()   # 릴리스와 동일 라우터(변경 있으면 자체 update)
        self.update()
        self._sync_label()

    def insert_vertex(self, seg_idx: int, p: QPointF):
        """세그먼트 seg_idx(정점 seg_idx~seg_idx+1 사이)에 정점 p 삽입(waypoint 추가)."""
        self._auto_route = False   # [Stage1] waypoint 추가 = 수동 편집 → 자동 라우팅 해제
        self._route_hints = []     # [경유지 힌트] 수동 전환 → 힌트 폐기
        self.prepareGeometryChange()
        self._pts.insert(seg_idx + 1, QPointF(p))
        self.update()
        self._sync_label()

    def _nearest_segment(self, local_p: QPointF):
        """local_p에 가장 가까운 세그먼트 (seg_idx, 선분 위 최근접점(local), 거리) 반환."""
        best = None
        for i in range(len(self._pts) - 1):
            proj, d = _point_seg_proj(local_p, self._pts[i], self._pts[i + 1])
            if best is None or d < best[2]:
                best = (i, proj, d)
        return best

    def remove_vertex(self, idx: int) -> bool:
        """정점 삭제(최소 2정점은 유지). 삭제했으면 True."""
        if len(self._pts) <= 2:
            return False
        self._auto_route = False   # [Stage1] 정점 삭제 = 수동 편집 → 자동 라우팅 해제
        self._route_hints = []     # [경유지 힌트] 수동 전환 → 힌트 폐기
        self.prepareGeometryChange()
        del self._pts[idx]
        self.update()
        self._sync_label()
        return True

    # ---- 색/두께 -------------------------------------------------------
    def apply_style(self, style):   # [M2 #3] 몸통 선스타일(점선 등)
        self._style = style
        self.update()

    def set_head_at_end(self, value: bool):   # [Phase 6 M3 #15] 방향 토글(플로팅 툴바)
        self.prepareGeometryChange()          # 화살촉이 반대 끝으로 → bbox 재계산
        self._head_at_end = value
        self.update()

    def flip_head(self):
        self.set_head_at_end(not self._head_at_end)

    def clone(self):
        c = _PolyArrowItem(QColor(self._color), self._width, self._head_at_end)
        c._style = self._style
        c._pts = [QPointF(p) for p in self._pts]
        c._bind_start, c._bind_end = self._bind_start, self._bind_end   # [A3] 지속 연결 유지
        c._bind_start_pt = None if self._bind_start_pt is None else QPointF(self._bind_start_pt)
        c._bind_end_pt = None if self._bind_end_pt is None else QPointF(self._bind_end_pt)
        c._routing = self._routing   # [M4-4] 라우팅 스타일 유지
        c._curve_r = self._curve_r   # [M4-4 ⓑ] 곡선 반경 유지
        c._auto_route = self._auto_route   # [Stage1] 자동 라우팅 상태 유지
        c._route_hints = [QPointF(p) for p in self._route_hints]   # [경유지 힌트] 유지
        c._label_t, c._label_off = self._label_t, self._label_off   # 라벨 위치(t·off) 유지
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 모든 정점을 씬변형. 왜곡·미러는 자동 엘보가 되돌리지 않게
    # 수동 폴리라인으로 전환(_auto_route=False). undo 스냅샷은 원래 _auto_route·힌트를 복원한다.
    def _capture_geom_local(self):
        return ([QPointF(p) for p in self._pts], self._auto_route,
                [QPointF(p) for p in self._route_hints], self._routing, self._curve_r)

    def _apply_geom_local(self, g):
        self.prepareGeometryChange()
        self._pts = [QPointF(p) for p in g[0]]
        self._auto_route = g[1]
        self._route_hints = [QPointF(p) for p in g[2]] if len(g) > 2 else []
        if len(g) > 3:
            self._routing = g[3]   # [M4-4] 라우팅 스타일 복원
        if len(g) > 4:
            self._curve_r = g[4]   # [M4-4 ⓑ] 곡선 반경 복원
        self._sync_label()

    def _capture_binds(self):
        return (self._bind_start,
                None if self._bind_start_pt is None else QPointF(self._bind_start_pt),
                self._bind_end,
                None if self._bind_end_pt is None else QPointF(self._bind_end_pt))

    def _apply_binds(self, b):
        self._bind_start, self._bind_start_pt = b[0], (None if b[1] is None else QPointF(b[1]))
        self._bind_end, self._bind_end_pt = b[2], (None if b[3] is None else QPointF(b[3]))

    def rebake_scene(self, fn):
        self.prepareGeometryChange()
        self._pts = [self._rebake_pt(fn, p) for p in self._pts]
        self._auto_route = False
        self._route_hints = []   # [경유지 힌트] 임의 왜곡 후엔 힌트 무의미 → 폐기
        self._sync_label()
        self.update()

    # ---- 화살촉(끝 세그먼트 방향) --------------------------------------
    def _tip_and_angle(self):
        if self._head_at_end:
            tip, tail = self._pts[-1], self._pts[-2]
        else:
            tip, tail = self._pts[0], self._pts[1]
        ang = (math.atan2(tip.y() - tail.y(), tip.x() - tail.x())
               if tip != tail else 0.0)
        return tip, ang

    def _head_size(self) -> float:
        return max(self._width * 2.5, 7.0)

    def _head_points(self):
        # [성능 최적화 2026-08-09] __init__ 주석 참조 — `_geom_version` 키 캐시.
        cache = self._head_pts_cache
        if cache is not None and cache[0] == self._geom_version:
            return cache[1]
        tip, ang = self._tip_and_angle()
        size = self._head_size()
        a1, a2 = ang + math.radians(150), ang - math.radians(150)
        result = [
            QPointF(tip),
            QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1)),
            QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2)),
        ]
        self._head_pts_cache = (self._geom_version, result)
        return result

    def _polyline_path(self) -> QPainterPath:
        return self._segment_path(self._pts)

    @staticmethod
    def _segment_path(pts) -> QPainterPath:
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        return path

    _CORNER_R = 10.0   # [M4-4] 곡선 엘보 기본 모서리 반경(로컬 단위, 인접 변 절반으로 클램프)
    _CURVE_R_MAX = 40.0   # [M4-4 ⓑ] 반경 스테퍼 상한(그 이상은 인접 변 절반 클램프에 먹혀 무의미)

    def _corner_radius(self) -> float:
        """[M4-4 ③ · 통합] 실제로 적용할 모서리 반경. 직교 경로면 조절값(_curve_r, 0=직각),
        직선이면 0(둥글릴 모서리가 없다). 「직각 엘보」와 「곡선 엘보」를 가르는 유일한 값."""
        if not self._is_ortho():
            return 0.0
        return getattr(self, "_curve_r", self._CORNER_R)

    def set_corner_radius(self, r: float):
        """[M4-4 ⓑ] 곡선 엘보 반경 설정(0=직각, [0,_CURVE_R_MAX] 클램프). 시각만 바뀌고
        _pts·히트테스트·직렬화 기하는 그대로 — paint의 _rounded_polyline_path만 달라진다."""
        self.prepareGeometryChange()
        self._curve_r = max(0.0, min(float(r), self._CURVE_R_MAX))
        self.update()

    def _trimmed_body_pts(self):
        """[실사용 지적 2026-08-03] 화살촉 시작 지점 이후로는 몸통을 그리지 않도록 tip 쪽
        마지막 구간을 `_head_size()*0.85`만큼 뒤로 당긴 점열 — `_ArrowItem.paint()`가 직선·곡선
        양쪽에서 이미 하던 트림을 여기(_PolyArrowItem)에도 맞춘다. 화살촉이 tip에서 폭 0으로
        좁아지는데 몸통은 tip까지 고정 폭이라, 안 자르면 화살촉이 시작되는 어깨 양옆으로 몸통
        폭이 계단처럼 삐져나와 보였다(Lucid 대조 스크린샷으로 확인). 히트테스트(`_polyline_path`
        가 쓰는 `self._pts`)·직렬화는 원본 그대로 — 이건 paint 전용 시각 트림.

        [성능 최적화 2026-08-09] `_head_points()`와 같은 계약 — `_geom_version` 키 캐시."""
        cache = self._trimmed_pts_cache
        if cache is not None and cache[0] == self._geom_version:
            return cache[1]
        pts = list(self._pts)
        if len(pts) >= 2:
            size = self._head_size() * 0.85
            if self._head_at_end:
                a, b = pts[-2], pts[-1]
            else:
                a, b = pts[1], pts[0]
            seg_len = math.hypot(b.x() - a.x(), b.y() - a.y())
            if seg_len > 1e-6:
                t = max(0.0, 1.0 - size / seg_len)
                trimmed = QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
                if self._head_at_end:
                    pts[-1] = trimmed
                else:
                    pts[0] = trimmed
        self._trimmed_pts_cache = (self._geom_version, pts)
        return pts

    def _rounded_polyline_path(self, pts=None) -> QPainterPath:
        """[M4-4 #4] 반경>0인 직교 경로용 — 각 중간 정점의 모서리를 원호(quadTo)로 둥글린다.
        반경은 인접 두 변 길이의 절반으로 클램프(짧은 변에서 겹치지 않게). paint 전용(히트테스트·
        직렬화·라벨갭 사각형은 직선 폴리라인 그대로 — 시각만 둥글게).
        pts=None이면 `self._pts`(원본), paint()가 화살촉 트림을 적용할 땐 `_trimmed_body_pts()`를
        넘긴다 — 마지막 구간 길이만 짧아지므로 중간 모서리 라운딩 계산(la·lb)은 그대로다."""
        if pts is None:
            pts = self._pts
        if len(pts) < 3:
            return QPainterPath(pts[0]) if len(pts) == 1 else self._segment_path(pts)
        radius = self._corner_radius()   # [M4-4 ⓑ] 0이면 아래 클램프에서 직각으로 떨어진다
        path = QPainterPath(pts[0])
        for i in range(1, len(pts) - 1):
            a, c, b = pts[i - 1], pts[i], pts[i + 1]
            la = math.hypot(c.x() - a.x(), c.y() - a.y())
            lb = math.hypot(b.x() - c.x(), b.y() - c.y())
            r = min(radius, la / 2.0, lb / 2.0)
            if r < 1e-3:
                path.lineTo(c)
                continue
            p_in = QPointF(c.x() + (a.x() - c.x()) / la * r, c.y() + (a.y() - c.y()) / la * r)
            p_out = QPointF(c.x() + (b.x() - c.x()) / lb * r, c.y() + (b.y() - c.y()) / lb * r)
            path.lineTo(p_in)
            path.quadTo(c, p_out)
        path.lineTo(pts[-1])
        return path

    _LABEL_GAP_PAD = 2.0   # [M4-1] 선-텍스트 갭 축소(5→2). 라벨 둘레로 선을 끊을 때의 여유(px)

    def _label_gap_rect(self):
        """[우리 확장] 라벨(있으면)이 차지하는 로컬 사각형(+패딩). 이 안의 선을 지워 텍스트를 앉힌다.
        라벨이 선에서 멀리 떨어지면(오프셋 드래그) 이 사각형이 선과 안 겹쳐 자연히 갭이 사라진다."""
        if not self.has_label():
            return None
        lbl = self._label
        br = lbl._content_rect()
        pos = lbl.pos()
        pad = self._LABEL_GAP_PAD
        return QRectF(pos.x() + br.x() - pad, pos.y() + br.y() - pad,
                     br.width() + 2 * pad, br.height() + 2 * pad)

    def _visible_polyline_path(self, pts=None) -> QPainterPath:
        """[우리 확장 · FigJam 갭] 라벨 사각형과 겹치는 폴리라인 구간만 빼고 그린 경로.
        히트테스트(_base_shape)·선택외곽선·직렬화는 전체 폴리라인을 그대로 쓴다 — 시각 갭만.
        pts=None이면 `self._pts`, paint()는 화살촉 트림된 `_trimmed_body_pts()`를 넘긴다."""
        if pts is None:
            pts = self._pts
        rect = self._label_gap_rect()
        if rect is None:
            return self._segment_path(pts)
        path = QPainterPath()
        for a, b in zip(pts[:-1], pts[1:]):
            inside = _seg_rect_interval(a, b, rect)
            if inside is None:
                path.moveTo(a)
                path.lineTo(b)
                continue
            i0, i1 = inside
            dx, dy = b.x() - a.x(), b.y() - a.y()
            if i0 > 1e-6:
                path.moveTo(a)
                path.lineTo(QPointF(a.x() + dx * i0, a.y() + dy * i0))
            if i1 < 1.0 - 1e-6:
                path.moveTo(QPointF(a.x() + dx * i1, a.y() + dy * i1))
                path.lineTo(b)
        return path

    # ---- 라벨 앵커 = 경로 위 t(0~1) 지점 + 수직 오프셋 (FigJam/Lucid) ----
    def _make_label(self):
        return _ConnectorLabel(self._label_color())   # 드래그로 경로 위 슬라이드/오프셋

    def _label_color(self) -> QColor:
        return QColor(self._color)

    def _point_at_t(self, t: float):
        """경로 길이 정규화 파라미터 t(0~1) 지점의 (점, 왼쪽 단위법선). 라벨 앵커·오프셋에 쓴다."""
        segs, total = [], 0.0
        for a, b in zip(self._pts[:-1], self._pts[1:]):
            d = math.hypot(b.x() - a.x(), b.y() - a.y())
            segs.append((a, b, d))
            total += d
        if total < 1e-9:
            return QPointF(self._pts[0]), QPointF(0.0, -1.0)
        target, run = max(0.0, min(1.0, t)) * total, 0.0
        for i, (a, b, d) in enumerate(segs):
            if run + d >= target or i == len(segs) - 1:   # 마지막 세그먼트면 t=1 끝점도 여기서 잡음
                tt = (target - run) / d if d > 1e-9 else 0.0
                px, py = a.x() + (b.x() - a.x()) * tt, a.y() + (b.y() - a.y()) * tt
                if d > 1e-9:
                    n = QPointF(-(b.y() - a.y()) / d, (b.x() - a.x()) / d)   # 왼쪽 단위법선
                else:
                    n = QPointF(0.0, -1.0)
                return QPointF(px, py), n
            run += d
        return QPointF(self._pts[-1]), QPointF(0.0, -1.0)

    def _label_anchor(self) -> QPointF:
        p, n = self._point_at_t(getattr(self, "_label_t", 0.5))
        off = getattr(self, "_label_off", 0.0)
        return QPointF(p.x() + n.x() * off, p.y() + n.y() * off)

    def _project_to_path(self, p: QPointF):
        """로컬 점 p를 폴리라인에 투영해 (t, 부호있는 수직오프셋)을 반환. 라벨 드래그 재투영용.
        오프셋 부호는 _point_at_t의 왼쪽 법선과 같은 방향(양수=선 왼쪽)."""
        segs, total = [], 0.0
        for a, b in zip(self._pts[:-1], self._pts[1:]):
            d = math.hypot(b.x() - a.x(), b.y() - a.y())
            segs.append((a, b, d))
            total += d
        if total < 1e-9:
            return 0.5, 0.0
        best = None   # (거리, 경로누적길이, 부호오프셋)
        run = 0.0
        for a, b, d in segs:
            if d < 1e-9:
                continue
            dx, dy = b.x() - a.x(), b.y() - a.y()
            tt = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / (d * d)))
            projx, projy = a.x() + dx * tt, a.y() + dy * tt
            dist = math.hypot(p.x() - projx, p.y() - projy)
            if best is None or dist < best[0]:
                off = (-dy * (p.x() - projx) + dx * (p.y() - projy)) / d   # 왼쪽 법선 성분
                best = (dist, run + d * tt, off)
            run += d
        return best[1] / total, best[2]

    def _reproject_label(self, proposed_topleft: QPointF) -> QPointF:
        """[우리 확장] 라벨 자유 드래그(itemChange가 넘긴 top-left 후보)를 경로 위로 재투영해
        t·off를 갱신하고, 그 t·off에 대응하는 '구속된' top-left를 돌려준다(FigJam 슬라이드+Lucid 오프셋)."""
        lbl = self._label
        br = lbl._content_rect()
        center = QPointF(proposed_topleft.x() + br.width() / 2.0,
                         proposed_topleft.y() + br.height() / 2.0)
        self._label_t, raw_off = self._project_to_path(center)
        _, n = self._point_at_t(self._label_t)   # [M4-1] 3위치 스냅용 법선
        self._label_off = _snap_label_off(n, raw_off, br)
        self.update()   # 라벨(자식)만 움직여도 부모 화살표 paint(갭)가 새 위치로 다시 그려지게
        a = self._label_anchor()
        return QPointF(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0)

    def _sync_label(self):
        """[우리 확장] 라벨을 앵커에 '완전 중앙'(x·y)으로 놓는다 — 선·베지어의 '중점 위쪽'과 달리
        선 위에 앉히고 paint가 그 자리에 갭을 낸다. _syncing 가드로 setPos→itemChange 되먹임 차단."""
        if not self._label_alive():
            return
        a = self._label_anchor()
        br = self._label._content_rect()
        self._label._syncing = True
        self._label.setPos(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0)
        self._label._syncing = False

    # ---- 경계/외형 -----------------------------------------------------
    def _content_rect(self) -> QRectF:
        # [성능 최적화 2026-08-08] `_pts`/`_width`/`_head_at_end`에만 의존(줌 무관) — 위 __init__/
        # prepareGeometryChange 주석 참조. 무거운 도면(~1600개)에서 boundingRect 체인 중 가장
        # 비싼 부분이었다(정점 min/max + `_head_points()` 삼각함수, cProfile 실측 tottime 1위).
        cache = self._content_rect_cache
        if cache is not None and cache[0] == self._geom_version:
            return cache[1]
        xs = [p.x() for p in self._pts]
        ys = [p.y() for p in self._pts]
        r = QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))
        stroke = self._width / 2.0 + 2
        r = r.adjusted(-stroke, -stroke, stroke, stroke)
        hp = self._head_points()
        hx = [p.x() for p in hp]
        hy = [p.y() for p in hp]
        head_r = QRectF(QPointF(min(hx), min(hy)), QPointF(max(hx), max(hy)))
        result = r.united(head_r.adjusted(-2, -2, 2, 2))
        self._content_rect_cache = (self._geom_version, result)
        return result

    def boundingRect(self) -> QRectF:
        # [화살표 boundingRect 최적화 2026-08-01] `vz`/`s`를 한 번씩만 읽어 정점 루프에 넘긴다
        # (`_HandleResizeMixin.boundingRect()`와 동일한 근거 — 위 주석 참조).
        # [성능 최적화 2026-08-08] 정점 루프 자체도 (geom 버전, vz) 키로 캐시 — `_view_zoom_factor`
        # 조회는 이미 저렴하므로(뷰 캐시, 위 2026-08-01 최적화) 매번 다시 읽고 '바뀌었는지'만
        # 비교한다(줌은 scene.changed를 안 타 prepareGeometryChange가 못 잡음 — 그래서 여기서
        # 직접 비교). 안 바뀌었으면 union 루프·삼각함수 전부 건너뛴다.
        vz = _view_zoom_factor(self)
        cache = self._bounds_rect_cache
        if cache is not None and cache[0] == self._geom_version and cache[1] == vz:
            return cache[2]
        s = self._scale_or_1(vz)
        r = self._content_rect()
        for i in range(len(self._pts)):
            r = r.united(self._inflate_to_hit(self._endpoint_rect(i, s), s, vz))
        # [M4-4] 세그먼트 알약 핸들도 boundingRect에 포함(paint 잔상 방지).
        pad = (4.0 + self._SEG_HANDLE_PX) / max(s, 1e-6)
        result = r.adjusted(-pad, -pad, pad, pad)
        self._bounds_rect_cache = (self._geom_version, vz, result)
        return result

    def _base_shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._width, 10) + 4)   # 잡기 쉬운 폭
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        shape = stroker.createStroke(self._polyline_path())
        shape.addPolygon(QPolygonF(self._head_points()))
        return shape

    # [선택 표시 통일 2026-08-01 → 2026-08-03 Lucid 대조] 커스텀 _paint_selection_outline·
    # 밴드 캐시(_sel_band_cache) 제거 — _ArrowItem과 동일한 이유(화살표는 이제 항상 얇은
    # 중심선이라 밴드 자체를 계산할 필요가 없다).

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, self._width, self._style,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._corner_radius() > 0:
            # [M4-4 · 통합] 분기 기준은 '모드'가 아니라 '반경'이다 — 반경 0이면 아래 폴리라인 경로로
            # 내려가 옛 「직각 엘보」와 완전히 같은 코드로 그려진다(같은 그림을 두 코드로 그리던 중복 해소).
            # 둥근 모서리 — 세그먼트 클립 대신 QPainter 클립으로 라벨 갭을 낸다(원호 보존).
            gap = self._label_gap_rect()
            if gap is not None:
                painter.save()
                clip = QPainterPath()
                clip.addRect(self.boundingRect())
                hole = QPainterPath()
                hole.addRect(gap)
                painter.setClipPath(clip.subtracted(hole))
                painter.drawPath(self._rounded_polyline_path(self._trimmed_body_pts()))
                painter.restore()
            else:
                painter.drawPath(self._rounded_polyline_path(self._trimmed_body_pts()))
        else:
            # [FigJam 갭] 라벨 자리에서 선 끊음 + [실사용 지적] 화살촉 시작 지점까지만 몸통
            painter.drawPath(self._visible_polyline_path(self._trimmed_body_pts()))
        # [실사용 버그 2026-08-03] 화살촉 펜에 joinStyle을 반드시 명시한다 — QPen의 기본
        # joinStyle은 **BevelJoin**이라, 지정하지 않으면 화살촉 삼각형의 예각(30°) 어깨 두
        # 곳이 45°로 잘려 나간다(모따기). 펜 폭이 1로 고정이라 깎임 크기도 ~0.5 씬단위
        # 고정 → 100% 줌에선 안티에일리어싱에 묻혀 안 보이고 고배율(사용자 실측 2863%)에서만
        # 드러나, "직각 화살표만 머리 양쪽이 깎인다"는 보고를 3라운드 동안 재현 못 했다.
        # `_ArrowItem`(곡선·직선)은 처음부터 RoundJoin을 명시해 두어 멀쩡했던 것 — 그쪽과
        # 완전히 같은 펜으로 맞춘다.
        painter.setPen(QPen(self._color, 1, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QBrush(self._color))
        painter.drawPolygon(QPolygonF(self._head_points()))
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_segment_handles(painter)   # [M4-4] 변 중점 알약 핸들(끝점 사각 아래에)
        self._paint_endpoint_handles(painter)


def remap_grouped_bindings(pairs):
    """복사/붙여넣기·Ctrl+D·Alt-드래그 복제가 한 배치로 함께 만든 (원본, 새 아이템) 쌍 안에서,
    화살표가 같은 배치 안의 도형에 바인딩돼 있었다면 그 도형의 사본으로 재연결한다. clone()은
    _bind1/_bind2(또는 _bind_start/_bind_end)를 원본 참조 그대로 복사하므로(배치 밖 도형에
    붙은 경우를 보존하기 위해 의도적), 배치 안에서 함께 복제된 상대는 여기서 후처리로 갈아끼운다."""
    remap = dict(pairs)
    for new in remap.values():
        if hasattr(new, "_bind1"):
            if new._bind1 in remap:
                new._bind1 = remap[new._bind1]
            if new._bind2 in remap:
                new._bind2 = remap[new._bind2]
        elif hasattr(new, "_bind_start"):
            if new._bind_start in remap:
                new._bind_start = remap[new._bind_start]
            if new._bind_end in remap:
                new._bind_end = remap[new._bind_end]


def regroup_duplicated_items(pairs):
    """복제된 아이템이 원본에서 같은 그룹에 속해 있었다면, 사본끼리 새 그룹id로 묶는다.
    clone()은 _group_id를 복사하지 않아(원본 참조가 아니라 값이라 안전해 보이지만) 기본값
    None으로 시작하므로, 그대로 두면 사본이 그룹 해제 상태가 된다. 원본 그룹id를 그대로
    쓰면 사본이 원본 그룹에 합류해 버리므로(둘이 하나의 그룹으로 뭉침) 반드시 새 id를 쓴다."""
    remap = dict(pairs)
    by_gid = {}
    for old, new in remap.items():
        gid = getattr(old, "_group_id", None)
        if gid is not None:
            by_gid.setdefault(gid, []).append(new)
    for members in by_gid.values():
        if len(members) >= 2:
            new_gid = uuid.uuid4().hex[:8]
            for m in members:
                m._group_id = new_gid


class _BadgeItem(_HandleResizeMixin, QGraphicsItem):
    """원 배경 + 중앙 번호. 클릭 위치(pos)에 배치."""

    _R = 15

    def __init__(self, number: int, color: QColor):
        super().__init__()
        self._number = number
        self._color = QColor(color)
        self._init_resize()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    def _content_rect(self) -> QRectF:
        r = self._R + 2
        return QRectF(-r, -r, 2 * r, 2 * r)

    def _base_shape(self):
        p = QPainterPath()
        p.addEllipse(self._content_rect())
        return p

    def clone(self):
        c = _BadgeItem(self._number, QColor(self._color))
        return self._copy_common_to(c)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawEllipse(QPointF(0, 0), self._R, self._R)
        f = QFont()
        f.setBold(True)
        f.setPointSize(12)
        painter.setFont(f)
        painter.setPen(QPen(QColor("white")))
        painter.drawText(QRectF(-self._R, -self._R, 2 * self._R, 2 * self._R),
                         Qt.AlignmentFlag.AlignCenter, str(self._number))
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)


class _TextItem(_HandleResizeMixin, QGraphicsTextItem):
    """편집 종료(focus out) 시 이동/크기조절 가능해지고, 더블클릭으로 다시 편집."""

    def __init__(self, color: QColor):
        super().__init__("")
        self._init_resize()
        self._bg = None  # None=투명 / QColor=배경 채움
        self.setDefaultTextColor(QColor(color))
        f = self.font()
        f.setPointSize(16)
        self.setFont(f)
        # [우리 확장] 사용자가 의도한 '기준' 폰트 크기. 중앙 라벨은 도형에 맞춰 이보다 작게 축소해
        # 렌더할 수 있으나(_fit_label_to_shape), 저장·재적합의 기준은 항상 이 값이다(축소값 아님).
        self._base_pt = 16
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    def apply_color(self, color):
        self.setDefaultTextColor(QColor(color))

    def apply_font_size(self, size):
        self._base_pt = int(size)   # 기준 크기 갱신(중앙 라벨 축소의 상한)
        f = self.font()
        f.setPointSize(int(size))
        self.setFont(f)

    def set_bg(self, color):
        # color: QColor 또는 None(투명). 둥근 사각 배경으로 자막/스티커 느낌.
        self._bg = QColor(color) if color is not None else None
        self.update()

    def clone(self):
        c = _TextItem(self.defaultTextColor())
        c.setFont(QFont(self.font()))
        c.setPlainText(self.toPlainText())
        c.set_bg(self._bg)
        return self._copy_common_to(c)

    def boundingRect(self):
        # 편집 중(텍스트 입력)엔 회전 핸들 예약(우상단 여백)을 빼 Qt 편집 프레임이 글자에
        # 딱 맞게 한다 — 안 그러면 핸들 자리만큼 점선 프레임이 위·우로 크게 벌어진다.
        if self.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction:
            return self._content_rect()
        return super().boundingRect()

    def setTextInteractionFlags(self, flags):
        # 편집 진입/종료로 boundingRect가 바뀌므로 경계 캐시 갱신(프레임 잔상 방지).
        self.prepareGeometryChange()
        super().setTextInteractionFlags(flags)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        super().focusOutEvent(event)
        # 연속 텍스트 모드에서 빈 클릭으로 생긴 빈 텍스트는 정리(undo는 scene None 가드로 무해).
        if not self.toPlainText().strip():
            QTimer.singleShot(0, self._discard_if_empty)
        else:
            self.setSelected(False)  # 완료(ESC/Ctrl+Enter) 후 점선 없이 글자만 — 재편집은 V 도구로

    def _discard_if_empty(self):
        if not self.toPlainText().strip() and self.scene() is not None:
            self.scene().removeItem(self)

    def mouseDoubleClickEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        # Enter = 편집 종료(ESC와 동일), Shift+Enter = 줄바꿈. clearFocus → focusOut에서 정리.
        # (Ctrl+Enter도 종료로 유지 — 하위 호환.)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)  # 줄바꿈 삽입
                return
            self.clearFocus()  # Enter / Ctrl+Enter = 완료
            return
        super().keyPressEvent(event)

    def paint(self, painter, option, widget=None):
        # [성능계획 2-C(b), 2026-08-15] 도형·화살표에 붙은 **라벨**(자식 텍스트)은 드래그 중
        # 다중선택이면 그리지 않는다 — 1000개 전체선택 드래그에서 프레임당 1,000회 페인트되던
        # 자리다. 독립 텍스트 아이템(부모 없음)은 장식이 아니라 내용이므로 그대로 그린다.
        if self.parentItem() is not None and _drag_decor_suppressed(self):
            return
        if self._bg is not None:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._bg))
            painter.drawRoundedRect(self._content_rect().adjusted(1, 1, -1, -1), 4, 4)
        self._paint_base_no_select(painter, option, widget)
        self._paint_handle(painter)


class _ConnectorLabel(_TextItem):
    """[우리 확장] 화살표(sarrow)에 붙는 라벨 — 드래그하면 부모 폴리라인을 따라 슬라이드하고
    (FigJam), 선 옆으로 당기면 수직 오프셋으로 뜬다(Lucid). 위치는 부모(_PolyArrowItem)가
    t·off로 소유하며, itemChange가 Qt 기본 자유 이동을 경로 위로 재투영해 구속한다.
    _syncing 플래그가 켜진 동안(_sync_label의 setPos)엔 재투영을 건너뛴다(되먹임 차단)."""

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and not getattr(self, "_syncing", False)):
            parent = self.parentItem()
            if parent is not None and hasattr(parent, "_reproject_label"):
                return parent._reproject_label(value)
        return super().itemChange(change, value)


# ---------------------------------------------------------------------------
# 스포이드 루페 — 화면 픽셀 색 미리보기 (입력 투과)
# ---------------------------------------------------------------------------

class _ColorLoupe(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._color = QColor("black")
        self._hex = ""
        self.setFixedSize(104, 74)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self._hex = self._color.name().upper()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(_BG))
        p.setPen(QPen(QColor(_SURFACE2), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.fillRect(8, 8, self.width() - 16, 38, self._color)
        p.setPen(QPen(QColor(_SURFACE2), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(8, 8, self.width() - 16, 38)
        p.setPen(QColor(_TEXT))
        p.drawText(QRectF(0, 48, self.width(), 22),
                   Qt.AlignmentFlag.AlignCenter, self._hex)


# ---------------------------------------------------------------------------
# 크기 스테퍼 — 도구별 floating(글자/번호 크기), 휠/▾▴ 클릭으로 조절
# ---------------------------------------------------------------------------

class _SizeStepper(QWidget):
    changed = pyqtSignal(int)

    _REPEAT_DELAY = 400   # 길게 누르기 시작 후 첫 반복까지(ms)
    _REPEAT_RATE = 60     # 이후 반복 간격(ms)

    def __init__(self, value: int, vmin: int, vmax: int, suffix: str = "", tooltip: str = ""):
        super().__init__()
        self._min, self._max = vmin, vmax
        self._s = value
        self._suffix = suffix
        self.setFixedSize(64, 24)
        self.setToolTip(tooltip or "크기 — 휠 또는 ▾ ▴ (길게 누르면 연속)")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # ▾/▴ 길게 누르면 연속 증감 — 누르고 있는 동안 반복
        self._repeat_dir = 0
        self._repeat_timer = QTimer(self)
        self._repeat_timer.timeout.connect(self._repeat_tick)

    def set_value(self, value: int):
        self._s = max(self._min, min(int(value), self._max))
        self.update()

    def _bump(self, delta: int):
        self.set_value(self._s + delta)
        self.changed.emit(self._s)

    def wheelEvent(self, event):
        if event.angleDelta().y() == 0:
            return
        self._bump(1 if event.angleDelta().y() > 0 else -1)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        if x < self.width() * 0.28:
            self._repeat_dir = -1
        elif x > self.width() * 0.72:
            self._repeat_dir = 1
        else:
            return
        self._bump(self._repeat_dir)                 # 즉시 1단계
        self._repeat_timer.start(self._REPEAT_DELAY)  # 누르고 있으면 이후 연속

    def _repeat_tick(self):
        self._bump(self._repeat_dir)
        if self._repeat_timer.interval() != self._REPEAT_RATE:
            self._repeat_timer.setInterval(self._REPEAT_RATE)  # 첫 반복 후 가속

    def mouseReleaseEvent(self, event):
        self._repeat_timer.stop()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(_SURFACE0))
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        f = QFont()
        f.setPointSize(10)
        p.setFont(f)
        p.setPen(QColor(_SUBTEXT))
        p.drawText(QRectF(2, 0, 16, self.height()), Qt.AlignmentFlag.AlignCenter, "▾")
        p.drawText(QRectF(self.width() - 18, 0, 16, self.height()),
                   Qt.AlignmentFlag.AlignCenter, "▴")
        p.setPen(QColor(_TEXT))
        p.drawText(QRectF(16, 0, self.width() - 32, self.height()),
                   Qt.AlignmentFlag.AlignCenter, f"{self._s}{self._suffix}")


# ---------------------------------------------------------------------------
# 그래픽스 뷰 — 그리기 인터랙션 + 도구 단축키 (Shift 제약)
# ---------------------------------------------------------------------------

def _rect_nearest(r, p):
    """로컬 사각형 r 둘레에서 점 p 최근접점 + 바깥 단위 법선(로컬)."""
    left, right, top, bottom = r.left(), r.right(), r.top(), r.bottom()
    if left <= p.x() <= right and top <= p.y() <= bottom:
        # 내부 → 가장 가까운 변으로 투영
        dl, dr, dt, db = p.x() - left, right - p.x(), p.y() - top, bottom - p.y()
        m = min(dl, dr, dt, db)
        if m == dl:
            return QPointF(left, p.y()), QPointF(-1.0, 0.0)
        if m == dr:
            return QPointF(right, p.y()), QPointF(1.0, 0.0)
        if m == dt:
            return QPointF(p.x(), top), QPointF(0.0, -1.0)
        return QPointF(p.x(), bottom), QPointF(0.0, 1.0)
    # 외부 → 채운 사각형으로 클램프한 점이 최근접(모서리 밖이면 대각 법선)
    qx = min(max(p.x(), left), right)
    qy = min(max(p.y(), top), bottom)
    nx = -1.0 if (qx == left and p.x() < left) else (1.0 if (qx == right and p.x() > right) else 0.0)
    ny = -1.0 if (qy == top and p.y() < top) else (1.0 if (qy == bottom and p.y() > bottom) else 0.0)
    if nx == 0.0 and ny == 0.0:
        ny = -1.0  # 안전망(도달 안 함)
    L = math.hypot(nx, ny) or 1.0
    return QPointF(qx, qy), QPointF(nx / L, ny / L)


def _ellipse_nearest(r, p):
    """로컬 타원(사각형 r에 내접) 둘레에서 점 p 최근접점 + 바깥 단위 법선(로컬).
    파라미터 각 t에 대한 뉴턴 반복(초기값=방사각)으로 근사 — 테두리 근처에서 빠르게 수렴."""
    cx, cy = r.center().x(), r.center().y()
    a, b = r.width() / 2.0, r.height() / 2.0
    ux, uy = p.x() - cx, p.y() - cy
    if a < 1e-6 or b < 1e-6:
        return QPointF(cx, cy), QPointF(0.0, -1.0)
    t = math.atan2(a * uy, b * ux)
    for _ in range(4):
        ct, st = math.cos(t), math.sin(t)
        x, y = a * ct, b * st
        # f(t) = d/dt (½|(x,y)-u|²) = (x-ux)(-a·st) + (y-uy)(b·ct)
        f = (x - ux) * (-a * st) + (y - uy) * (b * ct)
        fp = (a * a) * st * st - a * ct * (x - ux) \
            + (b * b) * ct * ct - b * st * (y - uy)
        if abs(fp) < 1e-9:
            break
        t -= f / fp
    ct, st = math.cos(t), math.sin(t)
    q = QPointF(cx + a * ct, cy + b * st)
    nx, ny = ct / a, st / b   # 바깥 법선 ∝ (x/a², y/b²)
    L = math.hypot(nx, ny) or 1.0
    return q, QPointF(nx / L, ny / L)


def _seg_nearest(a: QPointF, b: QPointF, p: QPointF) -> QPointF:
    """선분 a-b 위에서 점 p 최근접점(로컬)."""
    abx, aby = b.x() - a.x(), b.y() - a.y()
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        return QPointF(a)
    t = ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / denom
    t = max(0.0, min(1.0, t))
    return QPointF(a.x() + t * abx, a.y() + t * aby)


def _symbol_nearest(item, p):
    """심볼의 실제 외곽선(_sym_path)에서 점 p(로컬) 최근접점 + 바깥 단위 법선(로컬).
    경로를 폴리곤으로 평탄화(곡선 포함)해 각 변에서 최근접점을 찾고, 법선은 중심 반대쪽(바깥)으로
    향한다. 마름모·평행사변형처럼 외접 박스와 어긋나는 도형도 '보이는 외곽선'에 정확히 스냅한다."""
    path = item._sym_path()
    c = item.rect().center()
    best_q = None
    best_seg = None
    best_d = float("inf")
    for poly in path.toSubpathPolygons():
        for i in range(poly.count() - 1):
            a, b = poly.at(i), poly.at(i + 1)
            q = _seg_nearest(a, b, p)
            d = (q.x() - p.x()) ** 2 + (q.y() - p.y()) ** 2
            if d < best_d:
                best_d, best_q, best_seg = d, q, (a, b)
    if best_q is None:                       # 방어(빈 경로) — 박스 폴백
        return _rect_nearest(item.rect(), p)
    a, b = best_seg
    nx, ny = -(b.y() - a.y()), (b.x() - a.x())   # 변에 수직
    if (best_q.x() - c.x()) * nx + (best_q.y() - c.y()) * ny < 0:
        nx, ny = -nx, -ny                        # 중심 반대(바깥)로 정렬
    L = math.hypot(nx, ny) or 1.0
    return best_q, QPointF(nx / L, ny / L)


def _path_nearest(item, p):
    """[외부 DXF 폴백/펜 도형] 임의 QPainterPath(_PathItem, item.rect() 없음)의 외곽선에서
    점 p(로컬) 최근접점 + 바깥 단위 법선(로컬). _symbol_nearest와 동일한 폴리곤 평탄화
    방식이나 기준 중심은 item.rect() 대신 path.boundingRect() 중심을 쓴다(임의 외곽선이라
    변형된 사각형 개념이 없음)."""
    path = item.path()
    c = path.boundingRect().center()
    best_q = None
    best_seg = None
    best_d = float("inf")
    for poly in path.toSubpathPolygons():
        for i in range(poly.count() - 1):
            a, b = poly.at(i), poly.at(i + 1)
            q = _seg_nearest(a, b, p)
            d = (q.x() - p.x()) ** 2 + (q.y() - p.y()) ** 2
            if d < best_d:
                best_d, best_q, best_seg = d, q, (a, b)
    if best_q is None:                       # 방어(빈 경로)
        return p, QPointF(0.0, -1.0)
    a, b = best_seg
    nx, ny = -(b.y() - a.y()), (b.x() - a.x())   # 변에 수직
    if (best_q.x() - c.x()) * nx + (best_q.y() - c.y()) * ny < 0:
        nx, ny = -nx, -ny                        # 중심 반대(바깥)로 정렬
    L = math.hypot(nx, ny) or 1.0
    return best_q, QPointF(nx / L, ny / L)


_CARDINAL_LOCAL_DIRS = (QPointF(0.0, -1.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0), QPointF(-1.0, 0.0))


def _axis_forced_local_normal(item, local_pt: QPointF, raw_n: QPointF) -> QPointF:
    """[실사용 버그 수정 2026-07-29] local_pt가 도형의 N/E/S/W 변 중점 또는(사각형이면) 대각
    꼭짓점과 겹치면 '의도된' 로컬 축 방향으로 법선을 강제하고, 그 외(연속 폴백 등 임의의 테두리
    점)는 raw_n 그대로 반환한다.

    근본 원인: 이 점들은 두 변이 만나는 진짜 꼭짓점(마름모의 N/E/S/W, 사각형의 대각 꼭짓점)이라
    `_ellipse_nearest`/`_symbol_nearest`/`_rect_nearest`가 어느 변을 최근접으로 잡느냐에 따라
    법선이 기울어지거나(마름모, 폭≠높이일수록 심함) 임의의 축으로 쏠린다(사각형, 탐색 순서상
    항상 세로 변이 이겨 정사각형으로 테스트해도 4개 모두 '수평'으로 나옴 — 도형 비율과 무관한
    코드 우연). N/E/S/W는 N/S=수직·E/W=수평으로, 사각형 대각 꼭짓점은 **가까운 변 기준**(가로가
    세로보다 길면 수평, 세로가 더 길면 수직 — 정사각형처럼 정확히 같으면 수평)으로 강제한다.

    [중요] `_nearest_border`에서 호출해야 `_shape_ports`(포트 목록)뿐 아니라 `_bound_normal_scene`
    (build_elbow·reroute가 쓰는 실제 라우팅 법선 — 지속 바인딩된 부착점에서 매번 다시 계산)도
    같이 고쳐진다. 처음엔 `_shape_ports`에만 넣었다가, 화살표를 그릴 때의 스냅 법선은 고쳐졌는데
    도형이 나중에 움직여 reroute()가 재계산할 땐 여전히 옛(잘못된) 법선을 쓰는 걸 실측으로
    발견 — 두 경로가 결국 같은 `_nearest_border`를 거치므로 여기 한 곳에 두면 자동으로 통일된다."""
    r = item.rect()
    cx, cy = r.center().x(), r.center().y()
    eps = 1e-4 * max(r.width(), r.height(), 1.0)
    cardinals = (QPointF(cx, r.top()), QPointF(r.right(), cy),
                 QPointF(cx, r.bottom()), QPointF(r.left(), cy))
    for i, c in enumerate(cardinals):
        if abs(local_pt.x() - c.x()) < eps and abs(local_pt.y() - c.y()) < eps:
            return _CARDINAL_LOCAL_DIRS[i]
    if isinstance(item, _RectItem):
        corners = (QPointF(r.left(), r.top()), QPointF(r.right(), r.top()),
                   QPointF(r.right(), r.bottom()), QPointF(r.left(), r.bottom()))
        for c in corners:
            if abs(local_pt.x() - c.x()) < eps and abs(local_pt.y() - c.y()) < eps:
                rect_horiz = r.width() >= r.height()
                sx = 1.0 if c.x() > cx else -1.0
                sy = 1.0 if c.y() > cy else -1.0
                return QPointF(sx, 0.0) if rect_horiz else QPointF(0.0, sy)
    return raw_n


def _shape_interior_contains(item, scene_pt):
    """[2026-08-04 연속 호버 §8 항목16] item의 실제 기하 외곽선(클릭 히트밴드가 아니라) 기준
    scene_pt가 내부인지. `shape()`/`_base_shape()`는 잡기 쉽도록 부풀린 히트 영역(속 빈 도형의
    `_EDGE_HIT_MIN` 등)이라 테두리 두께 중심을 가르는 판정에는 못 쓴다 — 바로 바깥도 항상
    '안쪽'으로 잘못 판정된다(실측 확인). select 도구 연속 호버 커서 분기(안쪽=이동/바깥쪽=
    커넥터, `_update_hover_cursor`) 전용."""
    p = item.mapFromScene(scene_pt)
    if isinstance(item, _EllipseItem):
        path = QPainterPath()
        path.addEllipse(item.rect())
        return path.contains(p)
    if isinstance(item, _PathItem):
        return item.path().contains(p)
    if isinstance(item, _SymbolItem):
        return item._sym_path().contains(p)
    return item.rect().contains(p)


def _nearest_border(item, scene_pt):
    """네모/원/심볼/(외부 DXF 폴백·펜)경로 테두리에서 scene_pt 최근접점 → (snap_scene,
    outward_unit_scene). 회전·스케일은 아이템 변환으로 왕복 환산(바깥 법선도 씬 방향으로 변환).
    [실사용 버그 수정 2026-07-29] N/E/S/W·사각형 대각 꼭짓점은 _axis_forced_local_normal로
    법선 방향만 보정(위치는 그대로) — 상세 이유는 그 함수 docstring 참조.
    [외부 도형 스냅 확장] _PathItem은 item.rect()가 없어(임의 QPainterPath) _axis_forced_local_
    normal(내부에서 item.rect() 호출)을 건너뛴다 — discrete 포트가 없는 도형이라 축 보정 대상도
    아니다(_shape_ports가 _PathItem을 다루지 않음, 연속 폴백에서만 쓰임)."""
    p = item.mapFromScene(scene_pt)
    if isinstance(item, _EllipseItem):
        q, n = _ellipse_nearest(item.rect(), p)
        n = _axis_forced_local_normal(item, q, n)
    elif isinstance(item, _SymbolItem):
        q, n = _symbol_nearest(item, p)
        n = _axis_forced_local_normal(item, q, n)
    elif isinstance(item, _PathItem):
        q, n = _path_nearest(item, p)
    else:
        q, n = _rect_nearest(item.rect(), p)
        n = _axis_forced_local_normal(item, q, n)
    sp = item.mapToScene(q)
    nd = item.mapToScene(QPointF(q.x() + n.x(), q.y() + n.y())) - sp
    L = math.hypot(nd.x(), nd.y()) or 1.0
    return sp, QPointF(nd.x() / L, nd.y() / L)


def _border_pt_in_gap(host, local_pt) -> bool:
    """[실사용 버그 2026-08-09, 2026-08-10 §8 항목17 3단계에서 cut 구간 일반형으로 확장]
    host의 로컬 좌표 `local_pt`가 부착 포트 또는 TRIM cut(`host._cuts`)에 가려 **화면에 안
    그려지는** 외곽선 구간에 있으면 True.

    [실사용 버그 2026-08-09 당시 배경] 그때는 포트 트림이 진짜 기하 분절이 아니라 배경색으로
    덮어 그리는 시각효과였어서(`_paint_port_cover_if_needed`, 2026-08-03 Qt 버그 우회) 히트/
    스냅 기하는 온전한 사각형 그대로였다 — 포트 몸통 한가운데서도 호스트 테두리가 스냅·
    호버에 잡히는 원인이었다. [§8 항목17 7단계, 2026-08-10] 그 우회는 폐지되고 포트도 이제
    `build_trimmed_border_path`로 진짜 분절 렌더를 쓰지만, 이 함수의 판정 로직(호버·스냅이
    "그려지는 선"과 같은 정의를 쓰게 하는 것)은 렌더 방식과 무관하게 여전히 필요하다 —
    `build_trimmed_border_path`와 **같은** 소스(`_host_outline_local_polygon`·`_port_edge_gap`·
    `host._cuts`)로 판정해 "스냅되는 곳 == 선이 그려진 곳"을 유지한다(TRIM으로 자른 자리에
    화살표가 붙는 것을 막는 게 3단계의 목적)."""
    ports = getattr(host, "_ports", None) or []
    cuts = getattr(host, "_cuts", None) or []
    if not ports and not cuts:
        return False                      # 포트도 cut도 없는 도형은 비용 0 — 즉시 통과
    poly = _host_outline_local_polygon(host)
    n = len(poly)
    if n < 2:
        return False

    def _pt_in_edge_range(edge_i: int, t0: float, t1: float) -> bool:
        a, b = poly[edge_i], poly[(edge_i + 1) % n]
        t, perp = _seg_param_and_perp(a, b, local_pt)
        # perp 허용치: 인자로 오는 건 이미 외곽선 위의 점이라 이론상 0이다. 변끼리는 도형
        # 크기만큼 떨어져 있어 넉넉히 잡아도 옆 변으로 샐 일이 없다(부동소수 잡음만 흡수).
        return perp <= 0.5 and t0 - 1e-9 <= t <= t1 + 1e-9

    # [성능] 이 함수는 호버·스냅 핫패스(마우스무브마다 근처 도형 수만큼)에 있다. `_port_edge_
    # gap`은 포트마다 변 4개에 투영을 돌려 비싸므로(포트 8개 실측 +165us/call, 7.2배), 먼
    # 포트는 중심거리 한 번으로 먼저 쳐낸다. 가려지는 구간은 포트가 변에 투영된 범위 안이라
    # 언제나 포트 중심에서 반대각선 거리 이내 — 여유를 더해도 판정이 안 바뀐다. cut은 이
    # 사전필터가 필요 없다 — 자기 변 인덱스를 이미 알고 있어(`host._cuts`에 직접 저장)
    # 어느 변인지 찾는 계산 자체가 없다.
    near_ports = []
    for port in ports:
        pr = port.rect()
        c = port.mapToParent(pr.center())
        reach = math.hypot(pr.width(), pr.height()) / 2.0 + 5.0
        if abs(c.x() - local_pt.x()) <= reach and abs(c.y() - local_pt.y()) <= reach:
            near_ports.append(port)
    for port in near_ports:
        hit = _port_edge_gap(poly, port)
        if hit is None:
            continue
        i, t0, t1 = hit
        if _pt_in_edge_range(i, t0, t1):
            return True
    for edge_i, t0, t1 in cuts:
        if 0 <= edge_i < n and _pt_in_edge_range(edge_i, t0, t1):
            return True
    return False


def _nearest_border_visible(item, scene_pt):
    """[실사용 버그 2026-08-09, 2026-08-10 §8 항목17 3단계에서 cut 구간까지 확장]
    `_nearest_border`와 같되, 최근접점이 부착 포트 또는 TRIM cut에 가려 화면에 없는 구간이면
    None — "스냅되는 곳 == 선이 그려진 곳"을 맞춘다.

    `_nearest_border` 자체는 건드리지 않는다. 그쪽은 포트를 호스트 테두리에 **부착**하고
    드래그로 슬라이드시키는 데도 쓰이는데(`_attach_port_to_host`·
    `_snap_port_pos_to_host_border`), 거기서 트림을 반영하면 포트가 제 자리(자기가 만든
    구간)에서 밀려나기 때문이다. 그래서 호버·스냅 호출부만 이 변형을 opt-in 한다."""
    sp, n = _nearest_border(item, scene_pt)
    if _border_pt_in_gap(item, item.mapFromScene(sp)):
        return None
    return sp, n


def _reposition_port_from_frac(port):
    """[신규기능 §8-12] 포트를 부착 당시 저장해 둔 (fx, fy)(호스트 rect 폭·높이 대비 비율)로
    재배치 — 호스트가 리사이즈될 때(`_sync_ports`) 및 undo/redo로 재부착될 때 공통 사용."""
    host = getattr(port, "_port_host", None)
    frac = getattr(port, "_port_frac", None)
    if host is None or frac is None:
        return
    r = host.rect()
    fx, fy = frac
    cx = r.left() + fx * max(r.width(), 1e-6)
    cy = r.top() + fy * max(r.height(), 1e-6)
    pr = port.rect()
    port.setPos(cx - pr.width() / 2.0, cy - pr.height() / 2.0)


def _snap_port_pos_to_host_border(port, host, proposed_pos: QPointF) -> QPointF:
    """[실사용 버그 수정 2026-08-03] 포트를 드래그하는 동안(ItemPositionChange, 확정 전)
    제안된 새 위치를 호스트 테두리 위 최근접점으로 즉시 되돌린다 — 포트가 항상 테두리에
    붙어서 슬라이드하는 느낌을 준다(코너를 넘어 다른 변으로도 자연스럽게 넘어간다,
    `_nearest_border`가 호스트 전체 외곽선 기준이라 변 경계에 갇히지 않음)."""
    pr = port.rect()
    half = QPointF(pr.width() / 2.0, pr.height() / 2.0)
    center_scene = host.mapToScene(proposed_pos + half)
    sp, _n = _nearest_border(host, center_scene)
    return host.mapFromScene(sp) - half


def _update_port_frac_from_pos(port, host):
    """[신규기능 §8-12] 포트를 사용자가 직접 드래그한 뒤(itemChange) 새 위치를 (fx, fy)로
    역산해 저장 — `_reposition_port_from_frac`의 역방향. 호스트 rect가 나중에 바뀌어도
    지금 사용자가 옮긴 상대위치를 그대로 유지하기 위함."""
    r = host.rect()
    pr = port.rect()
    center = port.pos() + QPointF(pr.width() / 2.0, pr.height() / 2.0)
    fx = (center.x() - r.left()) / max(r.width(), 1e-6)
    fy = (center.y() - r.top()) / max(r.height(), 1e-6)
    port._port_frac = (fx, fy)


def _attach_port_to_host(port, host, scene_pt):
    """[신규기능 §8-12] 포트를 호스트 장비(사각형/삼각형 등)의 테두리 위 scene_pt 최근접점에
    부착 — 실제 Qt 부모-자식(`setParentItem`)으로 만들어 호스트 이동·회전·스케일을 공짜로
    따라가게 하고, rect 대비 상대위치(fx, fy)를 저장해 리사이즈 시에도 같은 테두리 위치를
    유지한다(`_reposition_port_from_frac`). 호스트의 `_ports` 리스트에도 등록한다(trim
    렌더링·커넥터 연동이 이 목록을 참조)."""
    sp, _n = _nearest_border(host, scene_pt)
    local = host.mapFromScene(sp)
    r = host.rect()
    fx = (local.x() - r.left()) / max(r.width(), 1e-6)
    fy = (local.y() - r.top()) / max(r.height(), 1e-6)
    port.setParentItem(host)
    port._port_host = host
    port._port_frac = (fx, fy)
    ports = getattr(host, "_ports", None)
    if ports is None:
        ports = host._ports = []
    if port not in ports:
        ports.append(port)
    _reposition_port_from_frac(port)
    host.update()   # [버그수정] rect·pos는 안 바뀌므로 Qt가 자동으로 재도장하지 않는다 — 직접 요청.


def _find_port_host_near(view, scene_pt: QPointF):
    """[신규기능 §8-12] scene_pt 근방에서 포트가 부착 가능한 유효 호스트(사각형/삼각형,
    포트 자신은 호스트가 될 수 없음)를 찾아 반환 — 없으면 None(자유 도형으로 남김).
    새 포트 배치(`host_fileio._create_port_at`)와 Alt+드래그 복제 재부착
    (`core_view._maybe_alt_drag_copy`) 양쪽이 공유해 "포트가 어디에 붙는가" 판정을
    한 곳에서만 유지한다(중복이면 둘이 어긋날 위험)."""
    host, best_d = None, None
    for cand in view._conn_shapes_near(scene_pt, _PORT_ATTACH_MARGIN):
        if getattr(cand, "_port_host", None) is not None:
            continue   # 포트는 다른 포트의 호스트가 될 수 없음
        is_device = isinstance(cand, _RectItem) or (
            isinstance(cand, _SymbolItem) and cand._kind == "triangle")
        if not is_device:
            continue
        sp, _n = _nearest_border(cand, scene_pt)
        d = QLineF(sp, scene_pt).length()
        if d <= _PORT_ATTACH_MARGIN and (best_d is None or d < best_d):
            best_d, host = d, cand
    return host


def _detach_port_from_host(port):
    """[신규기능 §8-12] 포트를 호스트의 `_ports` 목록에서 제거(삭제·undo 경로 공용).
    Qt parentItem 자체는 건드리지 않는다 — scene.removeItem()이 호출되는 경로에서
    호출부가 그 전후 처리를 맡는다(host_undo.py 참조)."""
    host = getattr(port, "_port_host", None)
    if host is None:
        return
    ports = getattr(host, "_ports", None)
    if ports and port in ports:
        ports.remove(port)
        host.update()   # 포트가 빠졌으니 trim 자리도 다시 이어 그려야 함.


def _port_owner_at(host, scene_pt, eps: float = 1.0):
    """[실사용 버그 수정 2026-08-03] scene_pt가 host에 부착된 포트 중 하나의 중심과 거의
    일치하면 그 **포트 자신**을, 아니면 host를 그대로 반환한다.

    포트에서 커넥터를 뽑을 때 `set_bound(idx, shape, local_pt)`의 shape 인자가 지금까지
    항상 host였다 — local_pt는 host 좌표계의 '고정된 점'이라, 포트를 나중에 옮겨도
    커넥터는 host의 그 자리에 그대로 남아 마치 "화살표가 도형 변에 눌어붙는" 것처럼
    보였다(사용자 실조건 리포트). shape을 포트 자신으로 바꾸면 local_pt가 포트의 로컬
    중심이 되어, 포트가 움직일 때마다 `mapToScene`이 항상 포트의 현재 위치를 돌려준다."""
    for port in getattr(host, "_ports", None) or []:
        c = port.mapToScene(port.rect().center())
        if math.hypot(c.x() - scene_pt.x(), c.y() - scene_pt.y()) < eps:
            return port
    return host


def _flatten_closed_path_to_polygon(path: QPainterPath) -> list:
    """닫힌 QPainterPath → 정점 리스트(마지막=첫점 중복 없이). `_host_outline_local_polygon`의
    심볼·타원 분기가 공유한다(둘 다 곡선/복합경로를 평탄화해 같은 폴리곤 꼴로 맞추는 절차라
    2026-08-10 §8 항목17 2단계에서 중복 제거)."""
    polys = path.toSubpathPolygons()
    if not polys:
        return []
    poly = polys[0]
    pts = [poly.at(i) for i in range(poly.count())]
    if len(pts) >= 2 and _close_pt(pts[0], pts[-1]):
        pts.pop()
    return pts


def _host_outline_local_polygon(host) -> list:
    """[신규기능 §8-12, 2026-08-10 §8 항목17 2단계에서 타원 추가] 호스트의 로컬 외곽선 정점
    (닫힌 폴리곤, 마지막=첫점 중복 없이). 사각형은 네 모서리, 삼각형 등 심볼·타원은 곡선을
    평탄화 — 트림 계산이 세 종류 도형에서 같은 코드(변 인덱스+t)로 동작하게 한다.

    [타원 cut 파라미터 방식 선택 2026-08-10] 각도 구간(theta0, theta1)이 수학적으로는 더
    정확하지만 build_trimmed_border_path·_port_edge_gap이 도형 종류별로 갈라져야 했다 —
    여기서는 폴리곤 근사로 통일해 기존 (변 인덱스, t0, t1) 포맷·렌더 코드를 그대로 재사용한다
    (사용자 선택, "정확도보다 코드 단일화"). 세그먼트 수는 Qt 기본 평탄화 오차(로컬좌표 기준
    고정값)에 맡긴다 — 도형 크기가 커지면 세그먼트도 늘어 시각적 매끄러움이 유지된다."""
    if isinstance(host, _SymbolItem):
        return _flatten_closed_path_to_polygon(host._sym_path())
    if isinstance(host, _EllipseItem):
        path = QPainterPath()
        path.addEllipse(host.rect())
        return _flatten_closed_path_to_polygon(path)
    r = host.rect()
    return [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]


def _tight_scene_bbox(item) -> QRectF | None:
    """[2026-08-10] `_RectItem`/`_EllipseItem`/`_SymbolItem`의 패딩 없는 실제 외곽선 씬
    바운딩박스 — `_host_outline_local_polygon`(TRIM 커널) 재사용. 이 도형들은 `_content_rect()`
    를 override 안 해 `_HandleResizeMixin` 기본값(Qt `boundingRect()`, 펜폭/2 패딩)을 그대로
    쓰는데, 스마트 정렬 스냅(`core_view._apply_smart_snap`)과 다중선택 그룹 오버레이
    (`_GroupTransform.bbox`)가 둘 다 이 패딩 없는 값이 필요해 여기 한 곳으로 모았다 — 흩어져
    있으면(실제로 한 번 그랬다) 한쪽만 고치고 다른 쪽을 놓치는 재발이 반복된다. 해당 없는
    타입은 None(호출부가 `_content_rect()` 등으로 폴백)."""
    if not isinstance(item, (_RectItem, _EllipseItem, _SymbolItem)):
        return None
    poly = _host_outline_local_polygon(item)
    if not poly:
        return None
    pts = [item.mapToScene(p) for p in poly]
    xs = [p.x() for p in pts]; ys = [p.y() for p in pts]
    return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))


def _open_item_local_pts(item) -> list:
    """[§8 항목17 5단계] 열린 도형(_LineItem/_PolyArrowItem)의 로컬좌표 정점열 — TRIM/EXTEND가
    도형 종류 무관하게 세그먼트 체인으로 다루는 공통 인터페이스(`_conn_polyline_scene`의 로컬판,
    그쪽은 스냅용 씬좌표라 별도 유지). 그 외 타입은 빈 리스트(커터로 기여 없음)."""
    if isinstance(item, _LineItem):
        ln = item.line()
        return [ln.p1(), ln.p2()]
    if isinstance(item, _PolyArrowItem):
        return list(item._pts)
    return []


def _item_local_edges(item) -> list:
    """[§8 항목17 5단계] 항목의 변(선분) 목록, item 로컬좌표 — 닫힌 도형(사각·타원·심볼)은
    폐곡선(마지막→첫 변 포함), 열린 도형(선·직선화살)은 안 닫는다. TRIM 커터 순회를 도형
    종류 무관하게 만든다(이전엔 `_trim_candidate_segment`가 `_host_outline_local_polygon`만
    가정해 열린 도형을 커터로 쓰면 크래시했다 — host.rect() 미존재). 인식 못 하는 타입(화살표
    곡선·`_PathItem` 등)은 빈 리스트를 돌려줘 그냥 기여 없는 커터로 취급된다."""
    if isinstance(item, (_RectItem, _EllipseItem, _SymbolItem)):
        poly = _host_outline_local_polygon(item)
        n = len(poly)
        return [(poly[i], poly[(i + 1) % n]) for i in range(n)]
    pts = _open_item_local_pts(item)
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def _close_pt(a: QPointF, b: QPointF, eps: float = 1e-6) -> bool:
    return abs(a.x() - b.x()) < eps and abs(a.y() - b.y()) < eps


def _seg_param_and_perp(a: QPointF, b: QPointF, p: QPointF):
    """점 p를 선분 a→b(무한직선 기준)에 투영 — (t, 수선거리). t는 a=0, b=1 파라미터(클램프 없음)."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return 0.0, math.hypot(p.x() - a.x(), p.y() - a.y())
    t = ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / L2
    px, py = a.x() + t * dx, a.y() + t * dy
    return t, math.hypot(p.x() - px, p.y() - py)


def _port_edge_gap(poly: list, port):
    """포트가 호스트 외곽선(poly, 로컬좌표)의 어느 변에 걸쳐 있는지 찾아 (edge_index, t0, t1)
    반환(못 찾으면 None) — 포트 중심에서 가장 가까운 변을 고르고, 포트 폭/높이를 그 변
    방향으로 투영해 걸친 구간을 근사한다(축정렬 변은 정확, 대각/사선 변은 근사)."""
    n = len(poly)
    if n < 2:
        return None
    pr = port.rect()
    center_local = port.mapToParent(pr.center())
    half_w, half_h = pr.width() / 2.0, pr.height() / 2.0
    best = None
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        t_c, perp = _seg_param_and_perp(a, b, center_local)
        if perp > max(half_w, half_h) + 4.0:   # 변에서 너무 멀면(여유 4씬단위) 이 변 아님
            continue
        dx, dy = b.x() - a.x(), b.y() - a.y()
        edge_len = math.hypot(dx, dy) or 1.0
        ux, uy = dx / edge_len, dy / edge_len
        half_along = abs(half_w * ux) + abs(half_h * uy)
        half_t = half_along / edge_len
        t0, t1 = max(0.0, t_c - half_t), min(1.0, t_c + half_t)
        if best is None or perp < best[3]:
            best = (i, t0, t1, perp)
    return None if best is None else best[:3]


def _merge_cuts_list(cuts: list) -> list:
    """[신규기능 2026-08-10] 같은 변(edge_index) 위에서 겹치거나 맞닿은 cut을 하나로 합친다 —
    `build_trimmed_border_path`가 렌더할 때 쓰는 것과 같은 병합 규칙(t0 오름차순 정렬 후 인접/
    겹침 흡수)을 저장 시점에도 적용한다. 실사용 지적: TRIM을 같은 자리에 여러 번 하면(문지르기
    드래그로 살짝씩 겹치게 자르는 등) `_cuts`가 시각적으로는 자국 하나인데 리스트엔 계속
    쌓여서, 자국 경계 핸들(마름모)이 실제 눈에 보이는 자국 수보다 훨씬 많이 뜨는 문제가 있었다
    — 여기서 미리 합쳐 두면 핸들 개수가 "진짜 보이는 자국 수"만큼만 늘어난다."""
    by_edge: dict = {}
    for edge_i, t0, t1 in cuts:
        by_edge.setdefault(edge_i, []).append((t0, t1))
    out = []
    for edge_i, ranges in by_edge.items():
        ranges.sort()
        merged = []
        for t0, t1 in ranges:
            if merged and t0 <= merged[-1][1] + 1e-6:
                merged[-1] = (merged[-1][0], max(merged[-1][1], t1))
            else:
                merged.append((t0, t1))
        out.extend((edge_i, t0, t1) for t0, t1 in merged)
    return out


def _add_border_cut(host, edge_index: int, t0: float, t1: float) -> None:
    """[신규기능 §8 항목17 2단계] host에 cut 구간 하나를 추가(변 인덱스, 변 내 비율 t0<t1) —
    `_port_edge_gap` 반환형과 같은 꼴이라 build_trimmed_border_path의 gap 병합 코드를 포트와
    공유한다. TRIM 도구(4단계)가 문지르기로 호출할 지점.
    [2026-08-10 후속] 추가 직후 `_merge_cuts_list`로 같은 변 위 겹치는/맞닿은 cut을 즉시
    합친다 — 렌더 시 병합(`build_trimmed_border_path`, 여전히 유지: 포트처럼 별도 목록에서
    오는 gap까지 함께 병합해야 하는 렌더 전용 사정이 있어 저장 병합만으론 부족)과 별개로,
    저장 리스트 자체를 부풀리지 않아야 자국 경계 핸들 개수가 실제 자국 수와 일치한다."""
    cuts = getattr(host, "_cuts", None)
    if cuts is None:
        cuts = host._cuts = []
    cuts.append((edge_index, t0, t1))
    host._cuts = _merge_cuts_list(cuts)
    host.update()


def _restore_cut_candidate(host, scene_pt: QPointF):
    """[신규기능 §8 항목17 후속, 2026-08-10] EXTEND(Shift)가 열린 도형의 끝점뿐 아니라 닫힌
    도형의 TRIM 자국도 되돌릴 수 있게 하는 대칭 기능 — host의 `_cuts` 중 scene_pt에 가장 가까운
    자국 하나를 (cut_tuple, 로컬 최근접점, 로컬 거리)로 반환(자국이 없으면 None). 자국은 렌더 시
    "안 보이는" 구간이라 `_nearest_border_visible`로는 못 찾는다 — 전체 외곽선(포트 유무 무관)에
    투영해 t를 그 cut의 [t0,t1] 범위로 클램프한다(문지르기 커밋의 edge/t 포맷과 대칭)."""
    cuts = getattr(host, "_cuts", None) or []
    if not cuts:
        return None
    poly = _host_outline_local_polygon(host)
    n = len(poly)
    if n < 2:
        return None
    local_pt = host.mapFromScene(scene_pt)
    best = None
    for cut in cuts:
        edge_i, t0, t1 = cut
        if not (0 <= edge_i < n):
            continue
        a, b = poly[edge_i], poly[(edge_i + 1) % n]
        t, _perp = _seg_param_and_perp(a, b, local_pt)
        tc = max(t0, min(t1, t))
        px, py = a.x() + (b.x() - a.x()) * tc, a.y() + (b.y() - a.y()) * tc
        d = math.hypot(local_pt.x() - px, local_pt.y() - py)
        if best is None or d < best[2]:
            best = (cut, QPointF(px, py), d)
    return best


def _edge_point_line_eq(a: QPointF, b: QPointF, p: QPointF):
    """도형이 (dx,dy)만큼 강체 이동했을 때 "변 a→b가 점 p를 지난다"는 제약을 dx·dy에 대한
    선형방정식 A*dx + B*dy = C 계수로 반환 — 유도: 변 방향 u=b-a는 이동으로 안 변하므로,
    (p - (a+d))가 u와 평행 ⟺ cross(p-a-d, u)=0 ⟺ u.y*dx - u.x*dy = cross(p-a, u)."""
    ux, uy = b.x() - a.x(), b.y() - a.y()
    qx, qy = p.x() - a.x(), p.y() - a.y()
    return uy, -ux, qx * uy - qy * ux   # A, B, C


def _solve_two_edge_point_translation(edge0, p0: QPointF, edge1, p1: QPointF):
    """[신규기능 2026-08-10, §8 항목17 후속] "변0이 점0을, 변1이 점1을 동시에 지나야 한다"는
    두 선형 제약을 연립해 유일한 강체 이동량 (dx,dy)을 역산 — 두 변이 (거의) 평행이면 해가
    무한하거나 없어 None. 축별로 dx·dy를 독립적으로 고르는 `_apply_smart_snap`의 일반 스냅과
    달리, TRIM이 애초에 이 두 교차점에서 cut을 만들었으므로 두 변이 다시 정확히 그 두 점을
    지나도록 풀면 도형이 원래 겹쳤던 자리로 정확히 복원된다(대각선이라도 무관 — 방향이
    고정된 강체이동이라 이 두 제약이 dx·dy를 완전히 결정)."""
    a0, b0 = edge0
    a1, b1 = edge1
    A0, B0, C0 = _edge_point_line_eq(a0, b0, p0)
    A1, B1, C1 = _edge_point_line_eq(a1, b1, p1)
    det = A0 * B1 - A1 * B0
    if abs(det) < 1e-9:
        return None   # 두 변이 (거의) 평행 — 유일해 없음
    dx = (C0 * B1 - C1 * B0) / det
    dy = (A0 * C1 - A1 * C0) / det
    return dx, dy


def _best_edge_for_point(scene_edges: list, p: QPointF, thr: float, slack: float = 0.08):
    """scene_edges(씬좌표 (a,b) 목록) 중 p에 가장 가까운 변을 (인덱스, 수선거리)로 반환 —
    변의 [−slack, 1+slack] 구간(살짝 벗어난 것도 허용) 안에 투영점이 있고 수선거리가 thr
    이내인 것만 후보. 없으면 None."""
    best = None
    for i, (a, b) in enumerate(scene_edges):
        t, perp = _seg_param_and_perp(a, b, p)
        if -slack <= t <= 1.0 + slack and perp <= thr:
            if best is None or perp < best[1]:
                best = (i, perp)
    return best


def cut_restore_snap_delta(it, other_items: list, thr: float):
    """[신규기능 2026-08-10, §8 항목17 후속] '자국 복구' 스냅 — 드래그 중인 `it`의 변 두 개가
    다른 도형의 `_cuts` 경계 두 점(원래 TRIM이 교차로 만들어낸 바로 그 점들)을 동시에 지나도록
    강체 이동량을 역산해 돌려준다. 삼각형처럼 대각선 변이 사각형 테두리 "중간"(꼭짓점이 아닌
    임의 지점)을 지나며 만든 cut도 다룬다 — `_apply_smart_snap`의 일반 스냅(정점만, 축별
    독립)이 원리적으로 못 잡는 자리다(설계 논의 참조). 매칭 실패 시 None."""
    edges = _item_local_edges(it)
    if not edges:
        return None
    scene_edges = [(it.mapToScene(a), it.mapToScene(b)) for a, b in edges]

    best = None   # (score, dx, dy)
    for other in other_items:
        cuts = getattr(other, "_cuts", None) or []
        if not cuts:
            continue
        poly = _host_outline_local_polygon(other)
        n = len(poly)
        for edge_i, t0, t1 in cuts:
            if not (0 <= edge_i < n):
                continue
            a, b = poly[edge_i], poly[(edge_i + 1) % n]
            p0 = other.mapToScene(QPointF(a.x() + (b.x() - a.x()) * t0, a.y() + (b.y() - a.y()) * t0))
            p1 = other.mapToScene(QPointF(a.x() + (b.x() - a.x()) * t1, a.y() + (b.y() - a.y()) * t1))
            m0 = _best_edge_for_point(scene_edges, p0, thr)
            m1 = _best_edge_for_point(scene_edges, p1, thr)
            if m0 is None or m1 is None:
                continue
            i0, perp0 = m0
            i1, perp1 = m1
            sol = _solve_two_edge_point_translation(scene_edges[i0], p0, scene_edges[i1], p1)
            if sol is None:
                continue
            dx, dy = sol
            if math.hypot(dx, dy) > thr * 5.0:   # 안전밸브 — 거의 평행에 가까운 변이 만드는 폭주 해 배제
                continue
            score = perp0 + perp1
            if best is None or score < best[0]:
                best = (score, dx, dy)
    if best is None:
        return None
    return best[1], best[2]


def build_trimmed_border_path(host) -> QPainterPath:
    """[신규기능 §8-12, 2026-08-10 §8 항목17 2단계에서 cut 구간 일반형으로 확장] 호스트
    외곽선에서 부착된 포트가 걸친 구간 + `host._cuts`(TRIM으로 잘라낸 일반 구간)를 합쳐
    실제로 끊은 경로 — 닫힌 하나의 subpath가 아니라 남은 조각마다 별도 subpath(moveTo/lineTo)로
    그린다. 포트도 cut도 없으면 원래 외곽선과 동일(끊김 없음)."""
    poly = _host_outline_local_polygon(host)
    n = len(poly)
    path = QPainterPath()
    if n < 2:
        return path
    ports = getattr(host, "_ports", None) or []
    gaps_by_edge: dict = {}
    for port in ports:
        hit = _port_edge_gap(poly, port)
        if hit is None:
            continue
        i, t0, t1 = hit
        gaps_by_edge.setdefault(i, []).append((t0, t1))
    for edge_i, t0, t1 in getattr(host, "_cuts", None) or []:
        if 0 <= edge_i < n:
            gaps_by_edge.setdefault(edge_i, []).append((t0, t1))
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        gaps = sorted(gaps_by_edge.get(i, []))
        merged = []
        for t0, t1 in gaps:
            if merged and t0 <= merged[-1][1] + 1e-6:
                merged[-1] = (merged[-1][0], max(merged[-1][1], t1))
            else:
                merged.append((t0, t1))
        cursor = 0.0
        for t0, t1 in merged:
            if t0 > cursor + 1e-6:
                p0 = QPointF(a.x() + (b.x() - a.x()) * cursor, a.y() + (b.y() - a.y()) * cursor)
                p1 = QPointF(a.x() + (b.x() - a.x()) * t0, a.y() + (b.y() - a.y()) * t0)
                path.moveTo(p0)
                path.lineTo(p1)
            cursor = max(cursor, t1)
        if cursor < 1.0 - 1e-6:
            p0 = QPointF(a.x() + (b.x() - a.x()) * cursor, a.y() + (b.y() - a.y()) * cursor)
            path.moveTo(p0)
            path.lineTo(b)
    return path


def _paint_filled_trimmed_border(item, painter) -> None:
    """[신규기능 §8 항목17 2단계] `item._cuts`가 있는 도형의 채움+테두리를 실제 분절 경로로
    그린다 — item.paint()가 평소의 super().paint()/drawRect·drawEllipse·drawPath(sym) 대신
    이 함수로 갈아탄다. 채움은 데이터모델대로 닫힌 영역 그대로(비파괴, `item._fill_path()`),
    테두리만 build_trimmed_border_path로 cut 구간만큼 진짜로 끊어 그린다(1단계 렌더 게이트
    스파이크의 segmented_paint와 같은 두 단계 구조 — 그때는 테스트 안의 임시 함수였던 것을
    여기서 실제 코드로 승격)."""
    if item.brush().style() != Qt.BrushStyle.NoBrush:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(item.brush())
        painter.drawPath(item._fill_path())
    pen = item.pen()
    if pen.style() != Qt.PenStyle.NoPen:
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(build_trimmed_border_path(item))


def _trim_candidate_segment(host, scene_pt, other_shapes):
    """[신규기능 §8 항목17 4단계] TRIM(문지르기) 호버·커밋이 공유하는 핵심 계산 — host 테두리
    위 `scene_pt` 근처 변에서, `other_shapes`(cutter 후보)와의 교차점으로 갈리는 구간
    (edge_index, t0, t1)을 찾는다. cutter가 그 변에 하나도 안 걸리면 None(자를 게 없음 —
    "포트 대체 워크플로"처럼 실제 교차가 있어야 하는 툴 스코프, 빈 변 통째 삭제는 대상 아님).

    구현은 2단계 결정("타원도 폴리곤 근사로 통일")을 그대로 재사용한다 — host와 cutter 둘 다
    `_host_outline_local_polygon`으로 폴리곤화하면 원·타원 cutter도 특례 없이 `_seg_seg_
    intersection`(선분-선분) 하나로 처리된다(선분-원/타원 전용 커널은 이 경로에선 불필요 —
    5단계 EXTEND처럼 진짜 곡선 정밀도가 필요한 다른 용도를 위해 남겨둔다). cutter 폴리곤은
    `other.mapToScene`→`host.mapFromScene` 왕복으로 host 로컬좌표로 옮겨(1단계 결정: 커널은
    좌표계 무관, 호출부가 항상 대상 host 로컬좌표로 변환) 회전·스케일이 달라도 그대로 맞는다."""
    hit = _nearest_border_visible(host, scene_pt)
    if hit is None:
        return None
    local_pt = host.mapFromScene(hit[0])
    poly = _host_outline_local_polygon(host)
    n = len(poly)
    if n < 2:
        return None
    best_edge, best_t, best_perp = None, None, None
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        t, perp = _seg_param_and_perp(a, b, local_pt)
        if -1e-6 <= t <= 1.0 + 1e-6 and (best_perp is None or perp < best_perp):
            best_edge, best_t, best_perp = i, max(0.0, min(1.0, t)), perp
    if best_edge is None:
        return None
    a, b = poly[best_edge], poly[(best_edge + 1) % n]
    ts = [0.0, 1.0]
    for other in other_shapes:
        if other is host or isinstance(other, _PathItem):
            continue
        # [§8 항목17 5단계] 이전엔 `_host_outline_local_polygon(other)`만 가정해 열린 도형
        # (선·직선화살)을 커터로 넘기면 크래시했다 — `_item_local_edges`로 일반화해 임의 두
        # 도형/선의 교차(계획서 원문)를 실제로 허용한다.
        for c, d in _item_local_edges(other):
            c_h = host.mapFromScene(other.mapToScene(c))
            d_h = host.mapFromScene(other.mapToScene(d))
            p = _seg_seg_intersection(a, b, c_h, d_h)
            if p is None:
                continue
            t, _perp = _seg_param_and_perp(a, b, p)
            if -1e-6 <= t <= 1.0 + 1e-6:
                ts.append(max(0.0, min(1.0, t)))
    ts = sorted(set(round(t, 9) for t in ts))
    if len(ts) <= 2:
        return None   # 이 변에 걸친 cutter가 없음 — 자를 게 없다
    lo, hi = 0.0, 1.0
    for k in range(len(ts) - 1):
        if ts[k] - 1e-6 <= best_t <= ts[k + 1] + 1e-6:
            lo, hi = ts[k], ts[k + 1]
            break
    if hi - lo < 1e-6:
        return None
    return best_edge, lo, hi


def _open_item_bracket_points(pts: list, lo: tuple, hi: tuple):
    """[§8 항목17 5단계] `_trim_candidate_open_segment`가 반환하는 (seg, t) 마크 lo/hi를
    실제 로컬좌표 점으로 변환(host 로컬, pts=`_open_item_local_pts(host)`)."""
    def pt_at(mark):
        seg, t = mark
        a, b = pts[seg], pts[seg + 1]
        return QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
    return pt_at(lo), pt_at(hi)


def _trim_candidate_open_segment(host, scene_pt, other_shapes):
    """[§8 항목17 5단계] TRIM(문지르기)이 **열린 도형**(host: _LineItem/_PolyArrowItem) 위에서
    호출하는 버전 — `_trim_candidate_segment`(닫힌 도형, 변 하나 안에서만 자름)와 달리 host
    자신이 여러 변으로 이루어진 사슬이라 지울 구간이 변 하나를 넘어설 수 있다(예: 꺾인
    폴리라인의 두 교차점 사이에 꼭짓점이 끼어 있는 경우 — 그 꼭짓점째로 지워진다). 그래서
    구간을 (seg_index, t) 마크 2개로 표현한다: 전체 경로를 변 index + 변 내 t로 정렬한 전역
    순서(비교키 = seg+t)가 성립하므로 닫힌 도형의 "변 인덱스+t" 포맷을 그대로 확장한 것뿐이다.
    반환: ((seg_lo, t_lo), (seg_hi, t_hi)) 또는 None(이 지점에 걸친 cutter가 없음)."""
    pts = _open_item_local_pts(host)
    n = len(pts)
    if n < 2:
        return None
    local_pt = host.mapFromScene(scene_pt)
    best_seg, best_t, best_d = None, None, None
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        t, _perp = _seg_param_and_perp(a, b, local_pt)
        tc = max(0.0, min(1.0, t))
        px, py = a.x() + (b.x() - a.x()) * tc, a.y() + (b.y() - a.y()) * tc
        d = math.hypot(local_pt.x() - px, local_pt.y() - py)
        if best_d is None or d < best_d:
            best_seg, best_t, best_d = i, tc, d
    if best_seg is None:
        return None
    marks = [(0, 0.0), (n - 2, 1.0)]
    for other in other_shapes:
        if other is host or isinstance(other, _PathItem):
            continue
        edges = _item_local_edges(other)
        if not edges:
            continue
        oedges_h = [(host.mapFromScene(other.mapToScene(c)),
                     host.mapFromScene(other.mapToScene(d))) for c, d in edges]
        for i in range(n - 1):
            a, b = pts[i], pts[i + 1]
            for c, d in oedges_h:
                p = _seg_seg_intersection(a, b, c, d)
                if p is None:
                    continue
                t, _perp = _seg_param_and_perp(a, b, p)
                if -1e-6 <= t <= 1.0 + 1e-6:
                    marks.append((i, max(0.0, min(1.0, t))))

    def key(m):
        return m[0] + m[1]

    marks = sorted(set((i, round(t, 9)) for i, t in marks), key=key)
    if len(marks) <= 2:
        return None   # 이 경로에 걸친 cutter가 없음 — 자를 게 없다
    cursor_key = best_seg + best_t
    lo, hi = marks[0], marks[-1]
    for k in range(len(marks) - 1):
        if key(marks[k]) - 1e-6 <= cursor_key <= key(marks[k + 1]) + 1e-6:
            lo, hi = marks[k], marks[k + 1]
            break
    if key(hi) - key(lo) < 1e-6:
        return None
    return lo, hi


def apply_open_item_trim(host, lo: tuple, hi: tuple):
    """[§8 항목17 5단계] TRIM 커밋 — 열린 도형(host)에서 (lo, hi) 구간을 지운다. 닫힌 도형의
    `_add_border_cut`(비파괴 gap 목록)과 달리 host 자체가 진짜로 줄어들거나(한쪽만 남음)
    둘로 갈린다(계획서 원문 "조각 분리 시 아이템 복제"): 자국이 경로 중간이면 host는 앞쪽
    조각으로 줄어들고 뒤쪽 조각은 새 아이템으로 복제해 씬에 추가해 반환한다(없으면 None).
    양끝 경계에 닿은 자르기(경로 시작/끝을 포함)는 복제 없이 host 하나가 짧아지기만 한다 —
    적어도 한 조각은 항상 남는다(호출부가 이미 걸친 cutter 존재를 확인했으므로 전체 삭제는
    일어나지 않는다).

    바인딩(`_PolyArrowItem`만 해당)은 잘려나간 쪽 끝만 해제 — 남은 끝(원래 시작/끝 그대로인
    조각)은 원래 부착을 유지한다. 라벨은 host 자신(앞쪽 조각)은 원래 라벨을 그대로 들고
    가고, 복제된 뒤쪽 조각은 라벨을 새로 시작한다(`clone()`이 라벨을 복사하지 않는 기존
    관례를 그대로 따름 — 같은 텍스트가 두 조각에 중복 표시되는 것을 피한다)."""
    pts = _open_item_local_pts(host)
    lo_seg, lo_t = lo
    hi_seg, hi_t = hi
    lo_pt, hi_pt = _open_item_bracket_points(pts, lo, hi)
    before_pts = pts[:lo_seg + 1] + ([] if lo_t <= 1e-9 else [lo_pt])
    after_pts = ([] if hi_t >= 1.0 - 1e-9 else [hi_pt]) + pts[hi_seg + 1:]
    has_before = len(before_pts) >= 2
    has_after = len(after_pts) >= 2
    is_poly = isinstance(host, _PolyArrowItem)

    def geom_for(new_pts):
        if is_poly:
            return (new_pts, False, [], host._routing, host._curve_r)
        return QLineF(new_pts[0], new_pts[-1])

    clone = None
    if has_after and has_before:
        orig_bind_end = (host._bind_end, host._bind_end_pt) if is_poly else None
        clone = host.clone()
        clone._apply_geom_local(geom_for(after_pts))
        if is_poly:
            clone.set_bound(0, None)
            if orig_bind_end is not None:
                clone._bind_end, clone._bind_end_pt = orig_bind_end
        host._apply_geom_local(geom_for(before_pts))
        if is_poly:
            host.set_bound(len(host._pts) - 1, None)
        host.scene().addItem(clone)
    elif has_before:
        host._apply_geom_local(geom_for(before_pts))
        if is_poly:
            host.set_bound(len(host._pts) - 1, None)
    elif has_after:
        host._apply_geom_local(geom_for(after_pts))
        if is_poly:
            host.set_bound(0, None)
    host.update()
    return clone


def _ray_seg_intersection(origin: QPointF, direction: QPointF, a: QPointF, b: QPointF):
    """[§8 항목17 5단계] origin에서 direction(길이 무관) 방향으로 뻗는 반직선과 선분 a-b의
    교차점 — EXTEND가 끝점 연장선 앞쪽에서 처음 만나는 경계를 찾는 데 쓴다. 선분-선분 교차
    (`_seg_seg_intersection`)와 달리 한쪽이 유한 구간이 아니라 반직선(t>0만 유효, 뒤쪽/제자리
    교차는 "늘이기"가 아니므로 배제)."""
    dx, dy = direction.x(), direction.y()
    ex, ey = b.x() - a.x(), b.y() - a.y()
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-12:
        return None
    ax, ay = a.x() - origin.x(), a.y() - origin.y()
    t = (ax * ey - ay * ex) / denom
    s = (t * dy - ay) / ey if abs(ey) > 1e-12 else (t * dx - ax) / ex
    if t <= 1e-6 or s < -1e-6 or s > 1.0 + 1e-6:
        return None
    return QPointF(origin.x() + t * dx, origin.y() + t * dy)


def _extend_candidate(host, scene_pt, other_shapes):
    """[§8 항목17 5단계] EXTEND — host(_LineItem/_PolyArrowItem)의 더 가까운 끝점을, 그 끝
    세그먼트 방향의 연장선과 other_shapes 변의 첫 교차점까지 늘인다(닫힌 도형은 늘일 끝점이
    없어 대상 밖 — 계획서 확정). 반환: (endpoint_idx, new_local_pt) 또는 None(연장선 위에
    걸리는 경계가 없음)."""
    pts = _open_item_local_pts(host)
    n = len(pts)
    if n < 2:
        return None
    local_pt = host.mapFromScene(scene_pt)
    d_start = math.hypot(local_pt.x() - pts[0].x(), local_pt.y() - pts[0].y())
    d_end = math.hypot(local_pt.x() - pts[-1].x(), local_pt.y() - pts[-1].y())
    if d_start <= d_end:
        idx, origin, neighbor = 0, pts[0], pts[1]
    else:
        idx, origin, neighbor = n - 1, pts[-1], pts[-2]
    direction = QPointF(origin.x() - neighbor.x(), origin.y() - neighbor.y())
    if abs(direction.x()) < 1e-9 and abs(direction.y()) < 1e-9:
        return None
    best_pt, best_t = None, None
    for other in other_shapes:
        if other is host or isinstance(other, _PathItem):
            continue
        for a, b in _item_local_edges(other):
            a_h = host.mapFromScene(other.mapToScene(a))
            b_h = host.mapFromScene(other.mapToScene(b))
            p = _ray_seg_intersection(origin, direction, a_h, b_h)
            if p is None:
                continue
            t = math.hypot(p.x() - origin.x(), p.y() - origin.y())
            if best_t is None or t < best_t:
                best_t, best_pt = t, p
    return None if best_pt is None else (idx, best_pt)


def apply_extend(host, idx: int, new_pt: QPointF) -> None:
    """[§8 항목17 5단계] EXTEND 커밋 — host의 끝점 idx를 new_pt로 늘인다. `_set_endpoint`
    (끝점 드래그가 이미 쓰는 것과 같은 메서드)를 재사용해 라벨 재배치(`_sync_label`)까지
    공짜로 따라온다. 자동 라우팅 중이던 화살표는 수동 모드로 내려 라우터가 방금 늘인 끝점을
    되돌리지 않게 한다(세그먼트 드래그 후 수동 전환과 같은 패턴)."""
    host._set_endpoint(idx, new_pt)
    if isinstance(host, _PolyArrowItem):
        host._auto_route = False
        host._route_hints = []
        host.set_bound(idx, None)
    host.update()


def _shape_ports(item):
    """도형의 이산 접속점(포트) → [(scene_pt, 바깥법선), ...]. 변 중점 4개(N·E·S·W)를
    _nearest_border로 '실제 외곽선'에 투영한다 — 네모·원은 변 중점 그대로, 심볼은 슬랜트 변
    (평행사변형 등)이라 투영해야 붕 뜨지 않는다. 마름모는 4 꼭짓점이 그대로 N/E/S/W가 된다.
    회전·스케일은 _nearest_border가 아이템 변환으로 왕복 환산. 법선 축 보정은 _nearest_border→
    _axis_forced_local_normal이 담당(포트 목록·라우팅 양쪽에서 일관되도록 그쪽으로 이동).

    [2026-07-30 실사용 피드백으로 4점 축소] bbox 대각 꼭짓점 4개(NE/SE/SW/NW)를 포함한 8포트는
    2026-07-29에 완성했으나, 선택도구 호버·선택 상태에 항상 보이는 점이 너무 많다는 실사용
    피드백(Lucid 대조)으로 discrete 포트 목록은 다시 4개로 되돌린다. 대각 근처로 드래그해도
    스냅 자체는 여전히 된다 — `_border_snap_at`의 연속 폴백(Pass 2)이 `_nearest_border`를
    이 목록과 무관하게 직접 호출해 도형 외곽선 어디든(대각 포함) 투영하기 때문(무회귀).
    줄어드는 건 '포트 우선순위·상시 표시 점 개수'뿐, 대각 부착 능력 자체는 그대로다."""
    r = item.rect()
    cx, cy = r.center().x(), r.center().y()
    if isinstance(item, _SymbolItem) and item._kind == "triangle":
        # [실사용 지적 2026-08-10] 일반 로직(바운딩박스 N/E/S/W를 투영)은 뒤쪽 변(축정렬)만
        # 우연히 맞고, 위·아래 대각선 변에서는 "그 변의 중점"이 아니라 "박스 중심에서 내린
        # 최근접점"이 나와 어긋났다(실측: 진짜 중점 (188,94.5) vs 기존 결과 (150,66)). 삼각형은
        # 세 변의 진짜 중점(t·b·l)과 꼭짓점(r)을 직접 좌표로 준다 — 이미 테두리 위의 정확한
        # 점이라 아래 `_nearest_border`에 넣어도 그대로 되돌아오고, 회전·법선 보정
        # (`_axis_forced_local_normal`)은 다른 도형과 같은 파이프라인을 그대로 탄다.
        # [2026-08-10 후속] `_tri_rect` 내접을 버리고(Lucid 대조) bbox r을 직접 쓴다 —
        # l·r은 이제 아래 일반 공식과 값이 같아지지만(뒤쪽 변·꼭짓점이 bbox 모서리/변중심과
        # 정확히 일치), t·b는 여전히 대각선 변이라 일반 공식(박스 중심에서 내린 점)과 다르므로
        # 네 점 다 명시적으로 유지한다.
        tl, bl = QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom())
        apex = QPointF(r.right(), cy)
        pts = (QPointF((apex.x() + tl.x()) / 2.0, (apex.y() + tl.y()) / 2.0),   # t=위쪽 대각변 중점
               apex,                                                             # r=꼭짓점
               QPointF((bl.x() + apex.x()) / 2.0, (bl.y() + apex.y()) / 2.0),    # b=아래쪽 대각변 중점
               QPointF(tl.x(), cy))                                              # l=뒤쪽 변 중점
    else:
        pts = (QPointF(cx, r.top()), QPointF(r.right(), cy),
               QPointF(cx, r.bottom()), QPointF(r.left(), cy))
    out = []
    for p in pts:
        sp, n = _nearest_border(item, item.mapToScene(p))
        out.append((sp, n))
    # [신규기능 §8-12 → 2026-08-04 3차 수정으로 제거] 예전엔 부착된 포트의 중심을 호스트의
    # 접속점 목록에도 중복으로 넣었다. 지금은 포트 자신이 (선택 여부와 무관하게) 독립적으로
    # 4변 접속점을 제공하므로(_hover_port_at·_qc_dot_at이 포트를 후보로 직접 스캔) 이 중복이
    # 오히려 문제였다 — 포트 정중앙이 호스트의 이 점(거리 0)과 정확히 겹쳐, 커서가 정중앙 부근을
    # 살짝만 움직여도 "호스트의 중앙점"과 "포트 자신의 4변점" 사이에서 최근접 판정이 뒤집혀
    # 예고점이 깜빡였다(실사용 리포트). 포트 정중앙이 하나의 반응 지점으로 남는 것 자체가
    # "중앙은 무반응이어야 한다"는 요구와도 어긋나 통째로 없앤다.
    return out


def _shape_ports_visible(item):
    """[§8 항목17 3단계, 2026-08-10] `_shape_ports(item)`에서 포트 또는 TRIM cut에 가려
    화면에 안 그려지는 접속점만 뺀 목록 — **다른** 도형에 스냅/호버할 때 쓴다
    (`_border_snap_at` Pass1·`_qc_snap_target` 도형-내부 흡수·`_shape_ports_for_preview`).
    연속 폴백(`_nearest_border_visible`)이 이미 지키는 "스냅되는 곳 == 선이 그려진 곳" 원칙을
    이산 4점에도 적용한다. [스코프] 선택된 도형 자신의 qc-dot 드래그 핸들(`_qc_dot_rects`)은
    별도 민감 영역(클릭=선택/드래그=화살표 규칙이 얽힘)이라 여기서 안 건드린다 — TRIM 도구가
    실제로 붙는 4단계에서 재검토."""
    return [(sp, n) for sp, n in _shape_ports(item)
            if not _border_pt_in_gap(item, item.mapFromScene(sp))]


def _shape_ports_for_preview(item):
    """[실사용 버그 수정 2026-08-03, 2026-08-10 §8 항목17 3단계에서 cut 인식 추가]
    `_shape_ports_visible(item)`에서 **선택된 포트**의 위치만 뺀 목록 — 호버 미리보기/스냅
    (`_hover_port_at`·`_draw_port_dots`) 전용. 포트가 선택되면 그 포트 자신의 리사이즈
    핸들이 같은 자리에 이미 떠 있어, 호스트의 접속점 미리보기까지 겹치면 (사용자 리포트)
    핸들 여러 개가 한 점에 뭉쳐 조작이 안 되는 것처럼 보였다."""
    selected_centers = [p.mapToScene(p.rect().center())
                        for p in (getattr(item, "_ports", None) or []) if p.isSelected()]
    visible = _shape_ports_visible(item)
    if not selected_centers:
        return visible
    out = []
    for sp, n in visible:
        if any(math.hypot(sp.x() - c.x(), sp.y() - c.y()) < 1.0 for c in selected_centers):
            continue
        out.append((sp, n))
    return out


# ---- [Phase 6 M4-2b] 선·화살표를 스냅 대상으로 — 끝점끼리 + 끝점→몸통 -----------
def _conn_polyline_scene(it):
    """선/화살표 몸통을 잇는 씬 좌표 점열(스냅 근사용). 곡선 화살표는 샘플링."""
    if isinstance(it, _LineItem):
        ln = it.line()
        return [it.mapToScene(ln.p1()), it.mapToScene(ln.p2())]
    if isinstance(it, _PolyArrowItem):
        return [it.mapToScene(p) for p in it._pts]
    if isinstance(it, _ArrowItem):
        return [it.mapToScene(it._point_at(i / 16.0)) for i in range(17)]
    return []


def _conn_endpoint_dirs(it):
    """[(끝점_씬, 바깥 접선 단위), ...] — 끝점과 그 선을 잇는 바깥 방향(스냅 우선 대상)."""
    pl = _conn_polyline_scene(it)
    if len(pl) < 2:
        return []

    def unit(a, b):
        dx, dy = a.x() - b.x(), a.y() - b.y()
        L = math.hypot(dx, dy) or 1.0
        return QPointF(dx / L, dy / L)
    return [(pl[0], unit(pl[0], pl[1])), (pl[-1], unit(pl[-1], pl[-2]))]


def _nearest_on_polyline(pl, scene_pt):
    """점열 pl의 세그먼트 중 scene_pt 최근접점 → (점, 커서쪽 수직단위) 또는 (None, _)."""
    best, bestd, bestn = None, None, QPointF(0.0, -1.0)
    for a, b in zip(pl[:-1], pl[1:]):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            q, nx, ny = a, 0.0, -1.0
        else:
            t = max(0.0, min(1.0, ((scene_pt.x() - a.x()) * dx + (scene_pt.y() - a.y()) * dy) / L2))
            q = QPointF(a.x() + dx * t, a.y() + dy * t)
            L = math.sqrt(L2)
            nx, ny = -dy / L, dx / L
        d = (scene_pt.x() - q.x()) ** 2 + (scene_pt.y() - q.y()) ** 2
        if bestd is None or d < bestd:
            vx, vy = scene_pt.x() - q.x(), scene_pt.y() - q.y()
            if nx * vx + ny * vy < 0:   # 법선을 커서 쪽으로 향하게
                nx, ny = -nx, -ny
            bestd, best, bestn = d, q, QPointF(nx, ny)
    return best, bestn


# ---- [Stage1] Lucid식 직교 자동 라우팅(기본 엘보) -----------------------------
def _dedup_pts(pts, eps=1e-6):
    """연속 중복점 + 공선(collinear) 중간점 제거. 정렬된 도형 사이의 퇴화 엘보를 직선으로 접는다."""
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p.x() - out[-1].x()) <= eps and abs(p.y() - out[-1].y()) <= eps:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        cross = (b.x() - a.x()) * (c.y() - a.y()) - (b.y() - a.y()) * (c.x() - a.x())
        if abs(cross) <= eps:
            del out[i]   # b가 a-c 선분 위 → 불필요
        else:
            i += 1
    return out


def _ortho_elbow(s: QPointF, e: QPointF, ns, ne):
    """시작 s·끝 e(scene)와 부착 변의 바깥 법선 ns·ne로 직각 엘보의 '중간 정점들'을 계산.
    법선의 우세축(수평/수직)이 각 끝의 이탈·도착 축을 정한다:
      · 양끝 수평 → H-V-H (중간 x = 두 x의 중점)
      · 양끝 수직 → V-H-V (중간 y = 두 y의 중점)
      · 혼합(한쪽 수평·한쪽 수직) → L자(모서리 하나)
    법선이 없으면(방어) 두 점의 우세 델타로 축을 대체. 반환은 중간 정점 리스트(0~2개)."""
    dx, dy = e.x() - s.x(), e.y() - s.y()
    default_h = abs(dx) >= abs(dy)

    def is_horizontal(n):
        if n is None:
            return default_h
        return abs(n.x()) >= abs(n.y())

    sh = is_horizontal(ns)
    eh = is_horizontal(ne)
    if sh and eh:
        mx = (s.x() + e.x()) / 2.0
        return [QPointF(mx, s.y()), QPointF(mx, e.y())]
    if (not sh) and (not eh):
        my = (s.y() + e.y()) / 2.0
        return [QPointF(s.x(), my), QPointF(e.x(), my)]
    if sh and not eh:
        return [QPointF(e.x(), s.y())]   # 수평 이탈 → 수직 도착
    return [QPointF(s.x(), e.y())]       # 수직 이탈 → 수평 도착


# ---- [Stage2] 직교 라우팅 장애물 회피 — 충돌 없는 후보 엘보 선택 -------------------
# [§8 항목19 F3 성능수정, 2026-08-14] `_seg_hits_rect(a, b, r)`은 같은 세그먼트(a, b)를 여러
# 사각형과 반복 대조하는 호출부(`_path_hits_rects`의 rects 루프, `_astar_ortho_grid.edge_ok`의
# 후보 obstacle 루프)에서 매 사각형마다 a.y()/b.x() 등 QPointF 접근과 축판정·정렬을 처음부터
# 다시 했다 — 그 값들은 세그먼트 하나에 대해 전부 루프불변(loop-invariant)인데도 매번
# 재계산된 것(F2가 `_corridor_rect`에서 잡은 것과 같은 계열의 낭비, 다만 여긴 컴프리헨션이
# 아니라 함수 재호출이 원인). 새 스트레스 픽스처(`tools/route_ladder_stress.py`, 사다리가
# preferred 관통으로 실제 도는 배치)로 cProfile 확인: 부분선택 드래그(20/48) 10프레임에서
# `_seg_hits_rect` 단독 133,851회 호출·tottime 0.755초(전체 3.165초의 24%) — 세그먼트당 1회만
# 계산하면 되는 값을 사각형 개수만큼 반복한 게 그대로 비용이었다. `_seg_probe`로 세그먼트의
# 축판정 결과를 1회 추출해 `_probe_hits_rect`(사각형만 받는 저비용 판정)에 반복 전달하도록
# 분리 — 수학 자체는 원래 `_seg_hits_rect`와 동일(순수 리팩터, 결과 무변경).
def _seg_probe(a: QPointF, b: QPointF, eps=1e-6):
    """세그먼트 a-b를 여러 사각형과 대조하기 전 1회만 계산해 두는 축판정 결과.
    반환: (0, y, x0, x1)=수평(y 고정, x구간) / (1, x, y0, y1)=수직(x 고정, y구간) /
    (2, x0, x1, y0, y1)=대각선(엘보에선 미발생, 방어적 bbox 폴백)."""
    ay, by = a.y(), b.y()
    if abs(ay - by) <= eps:
        ax, bx = a.x(), b.x()
        x0, x1 = (ax, bx) if ax <= bx else (bx, ax)
        return (0, ay, x0, x1)
    ax, bx = a.x(), b.x()
    if abs(ax - bx) <= eps:
        y0, y1 = (ay, by) if ay <= by else (by, ay)
        return (1, ax, y0, y1)
    x0, x1 = (ax, bx) if ax <= bx else (bx, ax)
    y0, y1 = (ay, by) if ay <= by else (by, ay)
    return (2, x0, x1, y0, y1)


def _probe_hits_rect(probe, r: QRectF, eps=1e-6) -> bool:
    """`_seg_probe`가 뽑은 세그먼트 축판정 결과로 사각형 r의 '속'을 지나는지 판정
    (테두리 접촉은 통과로 봄) — `_seg_hits_rect`와 동일 수학, a/b 재접근 없음."""
    kind = probe[0]
    if kind == 0:
        _, y, x0, x1 = probe
        if y <= r.top() + eps or y >= r.bottom() - eps:
            return False
        return x1 > r.left() + eps and x0 < r.right() - eps
    if kind == 1:
        _, x, y0, y1 = probe
        if x <= r.left() + eps or x >= r.right() - eps:
            return False
        return y1 > r.top() + eps and y0 < r.bottom() - eps
    _, x0, x1, y0, y1 = probe
    return x1 > r.left() and x0 < r.right() and y1 > r.top() and y0 < r.bottom()


def _seg_hits_rect(a: QPointF, b: QPointF, r: QRectF, eps=1e-6) -> bool:
    """축정렬 선분 a-b가 사각형 r의 '속'을 지나는가(테두리 접촉은 통과로 봄).
    엘보 세그먼트는 전부 수평/수직이라 축별로 판정. 대각선(엘보에선 미발생)은 bbox 겹침으로 보수 판정.
    단발 호출용 — 같은 a·b를 여러 r과 반복 대조할 땐 `_seg_probe`+`_probe_hits_rect`를 직접 써서
    루프불변 계산을 세그먼트당 1회로 줄인다(아래 `_path_hits_rects` 참조)."""
    return _probe_hits_rect(_seg_probe(a, b, eps), r, eps)


def _path_hits_rects(pts, rects, eps=1e-6) -> bool:
    """정점 리스트 pts로 이루어진 폴리라인이 사각형들 중 하나라도 관통하면 True."""
    for i in range(len(pts) - 1):
        probe = _seg_probe(pts[i], pts[i + 1], eps)
        for r in rects:
            if _probe_hits_rect(probe, r, eps):
                return True
    return False


def _normal_stub(p: QPointF, n, d: float, clear_rect=None) -> QPointF:
    """부착 법선 n의 우세축으로 점 p를 d만큼 바깥으로 민 '스텁점'. n이 없으면 p 그대로.
    A* 라우팅 전 시작·끝에 강제해 ⓐ 테두리 수직 이탈/도착(미관) ⓑ 바인딩 도형을 가로지르지
    않게(스텁이 이미 도형 밖 clearance 거리) 한다.

    [B-lite — 실조건 2026-07-26] clear_rect(자기 연결 도형의 팽창 사각형)를 주면 스텁이 그
    사각형을 **확실히 벗어날 때까지** 밀어낸다. ⚠ 이게 없으면 실제 외곽선이 bbox 안으로 들어간
    도형(평행사변형·육각형·원)에서 부착점이 bbox 안쪽이라 d만큼 밀어도 여전히 팽창 안 → A*의
    시작/도착 노드가 고립돼 경로를 못 찾고 base로 폴백 → 그 폴백이 곧 관통이다(평행사변형
    E→W 이동 55회 중 105건 관통, 측정)."""
    if n is None:
        return p
    horiz = abs(n.x()) >= abs(n.y())
    sign = 1.0 if (n.x() if horiz else n.y()) >= 0 else -1.0
    if clear_rect is not None:
        # 법선 방향으로 팽창 사각형을 빠져나오는 데 필요한 최소 거리(+여유 1px)
        need = ((clear_rect.right() - p.x()) if sign > 0 else (p.x() - clear_rect.left())) if horiz \
            else ((clear_rect.bottom() - p.y()) if sign > 0 else (p.y() - clear_rect.top()))
        d = max(d, need + 1.0)
    return QPointF(p.x() + sign * d, p.y()) if horiz else QPointF(p.x(), p.y() + sign * d)


# ---- [Stage3 훅] 화살표-화살표 soft 회피용 세그먼트 교차 판정(avoid_segs/cross_penalty
# 재도입 시 사용 — 집계 래퍼 _count_seg_crossings는 호출부 3곳이 전부 이 판정을 감싸기만
# 하던 얇은 함수라 각 호출부에 인라인했다. 2026-07-28 코드정리) --------------------------
def _seg_cross_seg(a: QPointF, b: QPointF, c: QPointF, d: QPointF, eps=1e-9) -> bool:
    """두 선분 a-b, c-d의 '내부'가 진짜로 가로지르면 True. 끝점 공유·공선 접촉은 비교차로
    본다(끝점을 공유하는 화살표들이 부착 도형 근처에서 만나는 것을 교차로 오판하지 않게).
    orientation 4-부호(양쪽 모두 엄격히 반대 부호일 때만 교차)."""
    def orient(p, q, r):
        return (q.x() - p.x()) * (r.y() - p.y()) - (q.y() - p.y()) * (r.x() - p.x())
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    ab_split = (o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)
    cd_split = (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    return ab_split and cd_split


# ---- [§8 항목17 1단계] TRIM/EXTEND 기하 커널 — 좌표계 무관 순수함수 --------------------
# 위 _seg_cross_seg는 A* 라우팅 핫패스(간선마다 avoid_segs 전체와 대조)라 불린만 반환해
# 나눗셈을 피한다 — 그 성능 특성을 지키기 위해 아래 함수들과 통합하지 않고 분리해 둔다.
# 이 함수들은 "어느 좌표계인지" 모른 채 받은 점 그대로 계산한다 — 회전된 도형을 다룰 때는
# 호출부가 host.mapFromScene()으로 대상 기하를 host의 로컬좌표로 옮겨 넘긴다(2026-08-10
# deep-interview 확정). 기존 _host_outline_local_polygon·_port_edge_gap·cut 저장형식(변
# 인덱스+t, 로컬 비율)이 이미 이 패턴이라 Qt의 mapToScene/mapFromScene이 회전·스케일을
# 자동 반영해주므로 회전 특례 코드가 필요 없다.
def _seg_seg_intersection(a: QPointF, b: QPointF, c: QPointF, d: QPointF, eps=1e-9):
    """두 선분 a-b, c-d가 만나면 교차 '점'을(둘 다 [0,1] 파라미터 범위, 끝점 포함) 반환,
    평행·비교차면 None. _seg_cross_seg와 달리 끝점 접촉도 교차로 인정한다(TRIM 문지르기·
    EXTEND는 "정확히 끝점에서 만남"도 유효한 절단/연장 지점이라 배제할 이유가 없다 —
    _seg_cross_seg가 끝점을 제외하는 이유(화살표-도형 접촉 오판 방지)는 이 용도엔 해당 없음).
    Cramer 공식(선분을 a+t*(b-a), c+u*(d-c)로 매개화해 연립)."""
    dx1, dy1 = b.x() - a.x(), b.y() - a.y()
    dx2, dy2 = d.x() - c.x(), d.y() - c.y()
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < eps:
        return None
    t = ((c.x() - a.x()) * dy2 - (c.y() - a.y()) * dx2) / denom
    u = (dy1 * (c.x() - a.x()) - dx1 * (c.y() - a.y())) / denom
    if -eps <= t <= 1.0 + eps and -eps <= u <= 1.0 + eps:
        return QPointF(a.x() + t * dx1, a.y() + t * dy1)
    return None


def _seg_circle_intersections(p1: QPointF, p2: QPointF, center: QPointF, radius: float,
                              eps=1e-9) -> list:
    """선분 p1-p2와 원(center, radius)의 교차점(선분 위에 있는 것만, 0~2개) — 접선(tangent)은
    1개로 dedupe. 선분을 p1+t*(p2-p1)로 매개화한 이차방정식 |p1+t*d - center|=radius."""
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    fx, fy = p1.x() - center.x(), p1.y() - center.y()
    a = dx * dx + dy * dy
    if a < eps:
        return []
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return []
    sq = math.sqrt(disc)
    out = []
    for t in ((-b - sq) / (2.0 * a), (-b + sq) / (2.0 * a)):
        if -eps <= t <= 1.0 + eps:
            tc = min(1.0, max(0.0, t))
            pt = QPointF(p1.x() + tc * dx, p1.y() + tc * dy)
            if not out or QLineF(out[-1], pt).length() > eps:
                out.append(pt)
    return out


def _seg_ellipse_intersections(p1: QPointF, p2: QPointF, rect: QRectF, eps=1e-9) -> list:
    """선분 p1-p2와 타원(rect로 정의된 축정렬 타원 — `_EllipseItem.rect()`와 같은 꼴)의
    교차점. rx=rect.width()/2, ry=rect.height()/2로 스케일 역변환해 단위원 문제로 환원한
    뒤 `_seg_circle_intersections`를 재사용하고 다시 스케일해 되돌린다(계획서 §8 항목17
    1단계). rect 자체가 이미 축정렬(EllipseItem 정의상 회전 없음)이므로 host가 회전돼
    있어도 호출부가 p1/p2/rect를 host 로컬좌표로 넘기면 그대로 맞는다."""
    cx, cy = rect.center().x(), rect.center().y()
    rx, ry = max(rect.width() / 2.0, eps), max(rect.height() / 2.0, eps)
    up1 = QPointF((p1.x() - cx) / rx, (p1.y() - cy) / ry)
    up2 = QPointF((p2.x() - cx) / rx, (p2.y() - cy) / ry)
    upts = _seg_circle_intersections(up1, up2, QPointF(0.0, 0.0), 1.0, eps)
    return [QPointF(u.x() * rx + cx, u.y() * ry + cy) for u in upts]


# [성능최적화 2026-08-08, 1차 시도(회랑+실패시 전체 재시도)는 역효과라 되돌림 — 라우팅 사다리가
# '이 조합은 원래 못 찾음'을 정상 결과로 기대하며 여러 조합을 던지는 구조라, None이 나올 때마다
# 전체로 재시도하면 실패가 예정된 호출마다 비용이 2배가 됐다(실측: 도형드래그 중앙값 146ms→
# 447ms, 최악 4.1초). 실측으로 확인한 사실: 이 문서에서 None은 회랑이 좁아서가 아니라 그 특정
# 시도(스텁 조합)가 애초에 기하학적으로 안 풀려서였다 — 장애물 18개 전부로 돌려도 여전히 None.
# 즉 회랑 축소가 성공/실패 여부 자체를 바꾸지 않는다(실측: 3~5개로 줄인 시도와 16~18개 그대로인
# 시도가 같은 케이스에서 둘 다 None). 그래서 2차는 재시도 안전망 없이 회랑만 적용 — 대신 별도
# 스크립트로 회랑 적용 전/후 kbs_1tv_test.ecad 실도면 전체 화살표의 최종 경로가 정확히 같은지
# 직접 대조해 안전함을 확인했다(완전성 위반 0건).
_CORRIDOR_PAD_MIN = 400.0     # 최소 여유(scene 단위) — 재시도가 없으므로 넉넉하게 잡아 안전마진 확보
_CORRIDOR_PAD_CLEARANCE_MULT = 15.0


def _corridor_rect(a: QPointF, b: QPointF, clearance: float) -> QRectF:
    """[§8 항목19 F2 수정, 2026-08-14] a-b bbox를 `_CORRIDOR_PAD_MIN`/`_CORRIDOR_PAD_CLEARANCE_
    MULT`만큼 부풀린 회랑 사각형 — `_astar_ortho`가 매 호출마다 인라인으로 계산하던 것을
    추출(동작 변화 없음). `_route_ortho`가 `_route_score`/후보평가에 넘길 장애물 목록을 미리
    이걸로 걸러 두는 데도 재사용한다(아래 F2 참조)."""
    pad = max(_CORRIDOR_PAD_MIN, clearance * _CORRIDOR_PAD_CLEARANCE_MULT)
    lo_x, hi_x = (a.x(), b.x()) if a.x() <= b.x() else (b.x(), a.x())
    lo_y, hi_y = (a.y(), b.y()) if a.y() <= b.y() else (b.y(), a.y())
    return QRectF(lo_x - pad, lo_y - pad, (hi_x - lo_x) + 2 * pad, (hi_y - lo_y) + 2 * pad)


def _astar_ortho(start: QPointF, goal: QPointF, infl, clearance, eps=1e-6,
                 avoid_segs=(), cross_penalty=0.0):
    corridor = _corridor_rect(start, goal, clearance)
    local = [r for r in infl if r.intersects(corridor)]
    return _astar_ortho_grid(start, goal, local, clearance, eps, avoid_segs, cross_penalty)


def _astar_ortho_grid(start: QPointF, goal: QPointF, infl, clearance, eps=1e-6,
                 avoid_segs=(), cross_penalty=0.0):
    """[Stage2 승격] Hanan 그리드 위의 직교 A*. 팽창 장애물(infl)을 관통하지 않는 최단 직각
    경로의 '중간 정점'을 반환(없으면 None). 후보 스캔과 달리 임의 밀집 배치에서도 경로가
    존재하면 반드시 찾는다(Hanan 그리드 완전성: 직교 우회로가 있으면 장애물 모서리선 위에도 있다).

    격자선 = {start·goal 좌표} ∪ {각 장애물의 left/right(세로선)·top/bottom(가로선)}.
    노드는 이 선들의 교점, 간선은 인접 노드 사이 축정렬 선분(_seg_hits_rect로 관통 검사).
    회전 벌점(clearance*0.5)으로 엘보 수를 최소화해 경로를 깔끔하게. 상태에 진행축을 넣어
    벌점을 정확히 계산(Manhattan 휴리스틱은 벌점을 무시 → admissible).
    [§8 항목19 F7, 2026-08-14] 계수 `0.5`는 값 자체의 도출 근거(다른 배수 대비 실측 비교
    등)가 history에 남아있지 않다 — "회전 1회 = clearance 절반 거리만큼 손해"로 잡아
    직진 대비 우회 유인을 약하게 주는 정도의 튜닝값으로 추정. 바꿀 필요가 생기면 감(느낌)
    조정이 아니라 3단계(`docs/route_review_2026-08.md`)처럼 실제 배치를 렌더해 비교하며
    실측 기반으로 재조정할 것.

    [Stage3] avoid_segs(다른 화살표 세그먼트, 씬좌표)는 hard 장애물이 아니라 soft다:
    간선이 그걸 가로지르면 cross_penalty를 g에 가산(교차 최소화). 우회 레인은 도형 팽창 모서리
    격자선에서 나온다. ⚠ 화살표 좌표는 격자선에 넣지 않는다 — 넣으면 A* 노드가 교차점에 정확히
    얹혀 교차가 '끝점 접촉'이 되고 _seg_cross_seg가 이를 비교차로 처리해 벌점이 눈머는 함정.
    벌점은 비용에만 더하므로 Manhattan 휴리스틱은 여전히 admissible(과대추정 없음).
    avoid_segs가 비면 기존 순수 도형회피와 동일(무회귀)."""
    xs = sorted({start.x(), goal.x(), *(v for r in infl for v in (r.left(), r.right()))})
    ys = sorted({start.y(), goal.y(), *(v for r in infl for v in (r.top(), r.bottom()))})
    nx, ny = len(xs), len(ys)
    xi = {v: i for i, v in enumerate(xs)}
    yi = {v: i for i, v in enumerate(ys)}
    sx, sy = xi[start.x()], yi[start.y()]
    gx, gy = xi[goal.x()], yi[goal.y()]

    # [성능최적화 2026-08-08] edge_ok가 매 grid 간선마다 obstacle 전부(infl, O(장애물 수))를
    # 순회하던 게 병목이었다(밀집 도면에서 드래그 중 reroute 1회에 수 초) — 각 grid 행/열에
    # '실제로 걸칠 수 있는' obstacle만 미리 걸러둔다. 필터 임계값이 _seg_hits_rect의 조기
    # return 조건(수평: r.top()+eps < y < r.bottom()-eps, 수직: 대칭)과 정확히 같아서, 걸러진
    # obstacle은 어차피 _seg_hits_rect가 False를 반환했을 것들뿐 — edge_ok 최종 판정은 100%
    # 동일하다(순수 사전필터, 경로 결과 무회귀).
    row_obst = [[r for r in infl if r.top() + eps < y < r.bottom() - eps] for y in ys]
    col_obst = [[r for r in infl if r.left() + eps < x < r.right() - eps] for x in xs]

    # [§8 항목19 F3 성능수정, 2026-08-14] 예전엔 매 간선마다 QPointF a·b를 새로 만들어
    # `_seg_hits_rect`에 넘겼다 — 그 안에서 다시 축판정+정렬을 candidate 개수만큼 반복했다.
    # 그리드 간선은 애초에 ay==by(수평) 아니면 ax==bx(수직)로 축이 이미 확정돼 있으므로(방금
    # cands를 고르는 데 쓴 바로 그 조건), QPointF 생성·`_seg_probe`의 abs()판정 없이 축판정
    # 결과를 직접 구성해 `_probe_hits_rect`에 넘긴다(위 `_path_hits_rects`와 동일 패턴).
    def edge_ok(ax, ay, bx, by):
        if ay == by:
            xa, xb = xs[ax], xs[bx]
            x0, x1 = (xa, xb) if xa <= xb else (xb, xa)
            probe = (0, ys[ay], x0, x1)
            cands = row_obst[ay]
        else:
            ya, yb = ys[ay], ys[by]
            y0, y1 = (ya, yb) if ya <= yb else (yb, ya)
            probe = (1, xs[ax], y0, y1)
            cands = col_obst[ax]
        return not any(_probe_hits_rect(probe, r, eps) for r in cands)

    turn_cost = clearance * 0.5

    def h(ix, iy):
        return abs(xs[ix] - xs[gx]) + abs(ys[iy] - ys[gy])

    start_state = (sx, sy, 0)                 # axis: 0=출발(무), 1=수평, 2=수직
    dist = {start_state: 0.0}
    prev = {}
    pq = [(h(sx, sy), 0.0, start_state)]
    goal_state = None
    while pq:
        _f, g, st = heapq.heappop(pq)
        if g > dist.get(st, float("inf")):
            continue
        ix, iy, axis = st
        if ix == gx and iy == gy:
            goal_state = st
            break
        for dix, diy, nax in ((1, 0, 1), (-1, 0, 1), (0, 1, 2), (0, -1, 2)):
            jx, jy = ix + dix, iy + diy
            if not (0 <= jx < nx and 0 <= jy < ny):
                continue
            if not edge_ok(ix, iy, jx, jy):
                continue
            step = abs(xs[jx] - xs[ix]) + abs(ys[jy] - ys[iy])
            turn = turn_cost if (axis != 0 and axis != nax) else 0.0
            pen = 0.0
            if cross_penalty and avoid_segs:   # [Stage3] soft: 다른 화살표를 가로지르면 벌점
                ea, eb = QPointF(xs[ix], ys[iy]), QPointF(xs[jx], ys[jy])
                pen = cross_penalty * sum(1 for c, d in avoid_segs if _seg_cross_seg(ea, eb, c, d))
            ng = g + step + turn + pen
            nst = (jx, jy, nax)
            if ng < dist.get(nst, float("inf")):
                dist[nst] = ng
                prev[nst] = st
                heapq.heappush(pq, (ng + h(jx, jy), ng, nst))
    if goal_state is None:
        return None
    # 재구성 → 끝점 제외한 중간 정점만 반환(_dedup_pts가 공선점을 접는다).
    path = []
    st = goal_state
    while st is not None:
        ix, iy, _ax = st
        path.append(QPointF(xs[ix], ys[iy]))
        st = prev.get(st)
    path.reverse()
    return path[1:-1]


# [M4-4 ⓐ] 연결 도형 우회 여유 배수(제3도형 clearance 대비). 실조건 피드백(2026-07-24): 배수 1이면
# 선이 부착 도형 변에 바짝 붙어 답답 → 2로 벌려 숨통. 재진입 회피 케이스에만 적용(무회귀).
_CONN_CLEAR_MULT = 3.0

# [M4-4 ⓐ 잔여] '변 타기' 판정 — 경로가 도형을 관통하진 않지만 변 위에 포개져 테두리와 구분이
# 안 되는 케이스. _seg_hits_rect가 테두리 접촉을 의도적으로 통과시키기 때문에(부착점이 관통으로
# 잡히면 안 되므로) 관통 검사만으로는 안 걸린다.
_RIDE_TOL = 4.0          # 변과 이 거리 이내로 나란하면 '탄다'
_RIDE_MIN_OVERLAP = 4.0  # 겹치는 길이가 이보다 커야 유의미(모서리 스침 오탐 방지)


def _seg_ride_len(a: QPointF, b: QPointF, r: QRectF, n_at=None) -> float:
    """축정렬 선분 a-b가 사각형 r의 변과 나란히(거리 ≤ _RIDE_TOL) 겹치는 길이. 아니면 0.
    n_at: 이 선분이 '자기가 붙은' 부착점에 접해 있으면 그 법선 — 법선 방향으로 곧게 이탈/도착하는
    세그먼트는 정상이므로 면제한다(수직 이탈은 타기가 아니다)."""
    if n_at is not None:
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if abs(n_at.x()) >= abs(n_at.y()):
            if abs(dy) <= 1e-6 and abs(dx) > 1e-6:
                return 0.0            # 법선(수평) 방향으로 곧게 이탈 = 정상
        elif abs(dx) <= 1e-6 and abs(dy) > 1e-6:
            return 0.0                # 법선(수직) 방향으로 곧게 이탈 = 정상
    if abs(a.y() - b.y()) <= 1e-6 and abs(a.x() - b.x()) > 1e-6:      # 수평
        lo, hi = sorted((a.x(), b.x()))
        ov = min(hi, r.right()) - max(lo, r.left())
        if ov > _RIDE_MIN_OVERLAP and min(abs(a.y() - r.top()), abs(a.y() - r.bottom())) <= _RIDE_TOL:
            return ov
    elif abs(a.x() - b.x()) <= 1e-6 and abs(a.y() - b.y()) > 1e-6:    # 수직
        lo, hi = sorted((a.y(), b.y()))
        ov = min(hi, r.bottom()) - max(lo, r.top())
        if ov > _RIDE_MIN_OVERLAP and min(abs(a.x() - r.left()), abs(a.x() - r.right())) <= _RIDE_TOL:
            return ov
    return 0.0


def _path_ride_len(pts, conn_pairs, ns=None, ne=None) -> float:
    """폴리라인이 연결 도형 변을 타는 총 길이. conn_pairs=[(rect, 'start'|'end'), ...].
    ⚠ 면제는 '그 끝점이 붙어 있는 도형'에 대해서만 준다 — 같은 세그먼트라도 *다른* 도형의 변을
    타면 그건 타기다(부착 세그먼트라는 이유로 통째 면제하면 상대 도형 변 타기를 놓친다)."""
    pts = _dedup_pts(list(pts))
    tot = 0.0
    last = len(pts) - 2
    for i in range(len(pts) - 1):
        for r, owner in conn_pairs:
            n_at = None
            if i == 0 and owner == "start":
                n_at = ns
            elif i == last and owner == "end":
                n_at = ne
            tot += _seg_ride_len(pts[i], pts[i + 1], r, n_at)
    return tot


def _path_manhattan_len(pts) -> float:
    return sum(abs(pts[i + 1].x() - pts[i].x()) + abs(pts[i + 1].y() - pts[i].y())
               for i in range(len(pts) - 1))


def _route_score(mids, s, e, ns, ne, infl, conn_orig, conn_pairs, avoid_segs, rung=0):
    """경로 품질 점수 — 작을수록 좋다(사전식 비교).
      (도형관통, 연결도형재진입, 타기길이, 화살표교차, 정점수, 여유칸, 총길이)
    여유칸(rung)을 총길이보다 앞에 둬, 결함 없는 후보들 중에서는 '넉넉한 여유'를 고른다
    (_CONN_CLEAR_MULT의 실조건 피드백 '변에 바짝 붙으면 답답' 유지)."""
    full = _dedup_pts([s] + list(mids) + [e])
    crossings = (sum(1 for i in range(len(full) - 1) for p, q in avoid_segs
                      if _seg_cross_seg(full[i], full[i + 1], p, q))
                 if avoid_segs else 0)
    return (
        1 if (infl and _path_hits_rects(full, infl)) else 0,
        1 if (conn_orig and _path_hits_rects(full, conn_orig)) else 0,
        round(_path_ride_len(full, conn_pairs, ns, ne), 1) if conn_pairs else 0.0,
        crossings,
        len(full),
        rung,
        round(_path_manhattan_len(full), 1),
    )


def _route_ortho(s: QPointF, e: QPointF, ns, ne, obstacles, clearance=12.0,
                 avoid_segs=(), cross_penalty=0.0, conn_rects=(), fast=False):
    """[Stage2 승격] Stage1 엘보(_ortho_elbow)를 우선하되, 그 경로가 장애물을 관통하면
    Hanan 그리드 A*(_astar_ortho)로 우회로를 찾아 '중간 정점'을 반환.
      · 장애물 없음 또는 Stage1이 이미 안전(도형·화살표 모두) → Stage1 그대로(무변경·되먹임 없음).
      · 관통/교차 시 → 법선 스텁을 씌운 A* → (실패 시) 스텁 없는 A* → (실패 시) Stage1 폴백.
    후보 스캔(구현 (b))과 달리 밀집 배치에서도 우회로가 존재하면 반드시 찾는다(그리드 완전성).
    obstacles: scene 좌표 사각형(양끝 바인딩 도형은 호출부에서 이미 제외). clearance만큼 팽창해 여유 확보.
    [Stage3] avoid_segs/cross_penalty: 도형은 hard(관통 금지), 다른 화살표는 soft(교차 최소화).
    preferred가 도형은 안전하나 화살표를 가로지르면 A* 우회를 시도하되, 교차를 실제로 줄일 때만
    채택(개선 없으면 preferred 유지 → 불필요한 우회·되먹임 방지).
    [M4-4 ⓐ] conn_rects: 양끝 '연결 도형' bbox — **(start|None, end|None) 2-튜플**(끝점 소유권이
    타기 면제 판정에 필요). 끝점이 이 도형 테두리 위라 통짜 팽창 장애물로 못 넣는다(deferred 함정)
    → '재진입'만 원본 rect로 판정(부착점 바깥 스텁 접촉은 통과), 재진입 시에만 stub↔stub A*에
    팽창본을 장애물로 추가.
    [M4-4 ⓐ 잔여] 위 구조엔 두 구멍이 있었다(2026-07-26 전수 스윕 768케이스서 측정):
      · 두 연결 도형이 conn_clear보다 가까우면 한쪽 스텁이 반대쪽 팽창 사각형 *안*에 갇혀 A*가
        실패 → preferred 폴백 → 그 preferred가 곧 관통 경로(56/768 = 7.3%).
      · 변 위에 정확히 얹힌 경로는 _seg_hits_rect가 통과시켜 '안전'으로 남는다(48/768 = 6.2%).
    → 해법은 '오늘의 결과(base)를 먼저 계산하고, 추가 후보가 점수로 **엄격히 이길 때만** 교체'하는
    단조 개선 구조 + 연결도형 clearance 사다리(conn_clear→clearance→1→0). 오늘 결과가 깨끗하면
    후보를 만들지도 않으므로 경로·비용 모두 기존과 동일(무회귀).

    [성능 최적화 2026-08-11] `fast=True`면 **base가 이미 결함 없을 때만** 클리어런스 사다리
    (아래 "혹 감소" 폴리시 탐색)를 건너뛰고 base를 그대로 반환한다 — 사다리는 base가 결함
    없어도 매번 무조건 추가 A* 탐색(최대 4단×2회)을 도는데, 그 비용이 "화면당 1개 화살표"에선
    무해했지만 그룹 드래그처럼 한 프레임에 reroute가 수십 번 겹치면 지배적 비용이 됐다(실측:
    20개 그룹 드래그 675ms, 시간의 96%가 A*). ⚠ base가 아직 결함 있는 경우(밀집 장애물에서
    넉넉한 초기 클리어런스로 후보를 못 찾은 경우)는 `fast`여도 사다리를 그대로 돈다 — 사다리의
    좁은 rung들이 그 경우엔 "폴리시"가 아니라 "유일한 탈출구"일 수 있다는 게 코드 구조상
    이론적으로 가능해 보였다(실측 재현은 못 함, 아래 판정 조건 코드 주석 참조 — 코리도 패딩이
    넉넉해 실사용 규모에서 드문 것으로 추정). 이 체크는 이미 계산된 값 재사용이라 추가 비용이
    없어, 실증은 못 했어도 방어적으로 남겨뒀다. 기본값 False(기존 동작 무변경) — 호출부가
    "이번엔 배선 폭주 상황"이라고 판단할 때만(`host_canvas._on_scene_changed`, 다건 변경 시)
    명시적으로 켠다."""
    infl = ([r.adjusted(-clearance, -clearance, clearance, clearance) for r in obstacles]
            if obstacles else [])
    # [§8 항목19 F2 수정, 2026-08-14] 회랑 밖 장애물까지 infl에 그대로 들고 있으면, 뒤에서
    # 후보마다 도는 `_route_score`/`_path_hits_rects`가 경로와 무관한 먼 장애물까지 매번
    # 전부 훑는다(cProfile 실측: 프레임 비용의 47%가 이 반복 호출, `docs/route_review_2026-08.md`
    # 4단계 F3). `_astar_ortho`도 내부적으로 같은 회랑(`_corridor_rect`)으로 한 번 더 걸러
    # 안전하므로(그 필터가 이미 "완전성 손실 없음"을 보장한 것과 동일한 계산 — 여기서 먼저
    # 걸러도 A* 결과는 그대로) 매 후보 평가마다 반복하던 필터링을 함수당 1회로 당긴다.
    _corr = _corridor_rect(s, e, clearance)
    infl = [r for r in infl if r.intersects(_corr)]
    # [M4-4 ⓐ] 연결 도형: 원본 rect=재진입/타기 판정용, 팽창본=A* 장애물용. 여유는 제3도형
    # (clearance)보다 넉넉하게(conn_clear) — 부착 도형 변에 선이 딱 붙어 지나가면 답답해 보인다
    # (실조건 피드백 2026-07-24). 이탈/도착 스텁도 같은 거리로 밀어 격자선을 벌린다.
    conn_clear = clearance * _CONN_CLEAR_MULT
    conn_seq = tuple(conn_rects)[:2]
    conn_orig = [r for r in conn_seq if r is not None]
    conn_pairs = [(r, ("start", "end")[i]) for i, r in enumerate(conn_seq) if r is not None]
    conn_infl = [r.adjusted(-conn_clear, -conn_clear, conn_clear, conn_clear) for r in conn_orig]

    # [실사용 피드백 2026-07-30] preferred(무장애물 base)는 여태 법선 스텁 없이 s·e를 바로
    # _ortho_elbow에 넣어, 두 부착점의 좌표가 우연히 비슷하면(코너뿐 아니라 연속폴백 임의점도)
    # 첫 구간 길이가 0에 가까워져 법선 방향 이탈 없이 곧장 자기 도형 변을 타는 것처럼 보였다.
    # A* 우회(_candidates)가 이미 쓰던 _normal_stub(own-rect 팽창분까지 escape)을 base 계산
    # 자체로 옮겨, 항상 '자기 도형 밖으로 스텁 → 그 다음 엘보'가 되도록 통일한다.
    def _own_stub(p, n, rect):
        if rect is None:
            return _normal_stub(p, n, clearance)
        infl_rect = rect.adjusted(-conn_clear, -conn_clear, conn_clear, conn_clear)
        return _normal_stub(p, n, conn_clear, infl_rect)
    own_s = conn_seq[0] if len(conn_seq) > 0 else None
    own_e = conn_seq[1] if len(conn_seq) > 1 else None
    s_stub = _own_stub(s, ns, own_s)
    e_stub = _own_stub(e, ne, own_e)
    elbow_mid = _ortho_elbow(s_stub, e_stub, ns, ne)
    preferred = (([] if s_stub == s else [s_stub]) + elbow_mid
                 + ([] if e_stub == e else [e_stub]))

    def _cross_count(pts):   # [Stage3 훅] avoid_segs 비면 0 — 재도입 시 활성화되는 집계
        return (sum(1 for i in range(len(pts) - 1) for p, q in avoid_segs
                     if _seg_cross_seg(pts[i], pts[i + 1], p, q))
                if avoid_segs else 0)

    pref_full = [s] + preferred + [e]
    pref_hits_shape = _path_hits_rects(pref_full, infl) if infl else False
    pref_reenters = _path_hits_rects(pref_full, conn_orig) if conn_orig else False
    pref_rides = (_path_ride_len(pref_full, conn_pairs, ns, ne) > 0) if conn_pairs else False
    pref_cross = _cross_count(pref_full)
    # preferred가 도형 안전 + 재진입·타기 없음 + 화살표 교차 없음 → 그대로(기존 무변경 보장).
    if not pref_hits_shape and not pref_reenters and not pref_rides and pref_cross == 0:
        return preferred

    def _candidates(obst, push, cc=None):
        """(1) 법선 스텁을 강제한 A*(수직 이탈/도착·바인딩 도형 회피) → (2) 스텁 없는 A*
        (스텁이 막혔을 때 폴백). 경로를 못 찾은 시도는 건너뛴다.
        [B-lite] cc가 있으면 각 끝의 스텁을 '자기 연결 도형의 팽창 사각형 밖'까지 밀어낸다 —
        슬랜트·곡선 외곽선이라 부착점이 bbox 안쪽인 도형에서 A*가 출발조차 못 하던 것을 푼다."""
        def own(i):
            r = conn_seq[i] if i < len(conn_seq) else None
            if r is None or cc is None:
                return None
            return r.adjusted(-cc, -cc, cc, cc)
        s2 = _normal_stub(s, ns, push, own(0))
        e2 = _normal_stub(e, ne, push, own(1))
        for a, b, pre, post in ((s2, e2, [] if s2 == s else [s2], [] if e2 == e else [e2]),
                                (s, e, [], [])):
            interior = _astar_ortho(a, b, obst, clearance,
                                    avoid_segs=avoid_segs, cross_penalty=cross_penalty)
            if interior is not None:
                yield pre + interior + post

    # --- (1) base = 기존 알고리즘이 내던 결과 그대로 -----------------------------
    base = preferred
    if pref_hits_shape or pref_reenters:
        # [M4-4 ⓐ] 재진입할 때만 conn을 A* 장애물/검증에 편입 — 순수 제3도형 케이스는 기존과 동일.
        # 도형 관통·재진입 회피는 hard 요구 — 첫 안전 후보 채택(화살표는 벌점으로 A*가 이미 최소화).
        astar_obst = (infl + conn_infl) if pref_reenters else infl
        check_rects = (infl + conn_orig) if pref_reenters else infl
        push = conn_clear if pref_reenters else clearance
        for mids in _candidates(astar_obst, push):
            if not _path_hits_rects([s] + mids + [e], check_rects):
                base = mids
                break
    elif avoid_segs:
        # preferred가 도형은 안전하나 화살표를 가로지름 — 두 시도를 모두 평가해 '교차를 가장 많이
        # 줄이는' 도형-안전 후보만 채택(개선 없으면 preferred 유지 → 불필요한 우회·되먹임 방지).
        # [§8 항목19 F5 수정, 2026-08-14] avoid_segs가 비면(Stage3 비활성 — 현재 모든 호출부가
        # 그러함) 이 분기는 pref_rides=True일 때만 진입하는데(pref_cross는 항상 0), `c <
        # best_cross`가 `0 < 0`으로 구조적으로 거짓이라 base를 절대 못 바꾸면서 A*만 최대
        # 2회 낭비했다(pref_rides는 아래 클리어런스 사다리가 conn_pairs 기반 ride_len
        # 판정으로 이미 해소함 — 무회귀). Stage3 재도입 시(avoid_segs 비지 않음) 이 탐색이
        # 다시 필요해지므로 로직 자체는 그대로 두고 게이트만 추가.
        best_cross = pref_cross
        for mids in _candidates(infl, clearance):
            if _path_hits_rects([s] + mids + [e], infl):   # 도형 관통은 hard — 후보 기각
                continue
            c = _cross_count([s] + mids + [e])
            if c < best_cross:
                base, best_cross = mids, c

    base_score = _route_score(base, s, e, ns, ne, infl, conn_orig, conn_pairs, avoid_segs)

    # --- (2) 연결도형 clearance 사다리 — base를 '엄격히 이기는' 후보만 교체 -------
    # 넉넉한 여유부터 좁은 여유까지 훑되, 채택 기준은 점수뿐이라 오늘보다 나쁜 경로는 구조적으로
    # 나올 수 없다(사다리가 전부 실패해도 base 유지). 0.0칸은 '팽창 없음' — 부착점이 팽창 사각형
    # 안에 갇혀 A*가 아예 출발 못 하는 배치의 마지막 탈출구.
    # [혹 버그 수정 2026-07-27] base가 이미 결함 없음(관통·재진입·타기 0)이어도 여기서 조기
    # 반환하지 않는다 — base는 conn_clear(가장 넉넉한 여유)로 A*가 처음 찾은 경로일 뿐이라 결함은
    # 없어도 불필요하게 먼 우회('혹')일 수 있다(사다리가 그 우회를 줄여줄 기회조차 못 얻었던 게
    # 근본원인). 사다리는 base보다 엄격히 나은 후보만 채택하는 단조개선이라 **정확성 기준으로는**
    # 늘 실행해도 무해하다 — 단 이 "무해"는 성능 무해를 뜻하지 않는다(위 docstring "성능 최적화
    # 2026-08-11" 참조).
    #
    # [2026-08-11 방어적 강화 — 코드 정독으로 찾은 이론적 허점, 실측 재현은 못 함] 처음엔
    # `if fast: return base`로 사다리 전체를 무조건 건너뛰었다. `base`는 "결함 없음"이 아니라
    # "conn_clear(가장 넉넉한 클리어런스)로 첫 유효 후보를 찾으려 *시도*한 결과"일 뿐이므로,
    # 그 시도가 전부 실패하면(밀집 장애물) base가 여전히 preferred(관통하는 원본)로 남을 수
    # 있다는 게 코드 구조상 이론적으로 가능해 보였다 — 이 경우 사다리의 더 좁은 rung
    # (clearance→1.0→0.0)이 유일한 탈출구다("부착점이 팽창 사각형 안에 갇혀 A*가 아예 출발
    # 못 하는 배치의 마지막 탈출구", 바로 위 주석). ⚠ 실제 그룹 드래그(38개 화살표, 8프레임)
    # 로 검증해봤을 땐 이 시나리오를 못 만났다 — A* 코리도 패딩(`_CORRIDOR_PAD_MIN`=400
    # 이상)이 매우 넉넉해 실사용 도면 규모에서 conn_clear 시도가 완전히 막히는 경우가
    # 드문 것으로 보인다(처음 "회귀 재현"이라 여겼던 5건은 검증 스크립트가 관통 판정에
    # `boundingRect()`(펜폭 패딩 포함)를 써서 생긴 오탐이었고, `_obstacle_rects()`와 같은
    # 원본 `.rect()`로 다시 재니 수정 전/후 모두 0건이었다). 그래도 이 체크는 이미 계산된
    # `base_score`를 재사용해 **추가 비용이 0**이므로, 실증은 못 했어도 이론적 허점을 막아두는
    # 쪽을 택했다 — `base_score`의 앞 네 항목(관통·재진입·타기·교차, `_route_score` 정의
    # 참조)이 전부 0일 때만(=base가 실제로 결함 없을 때만) 사다리를 건너뛴다.
    if fast and base_score[0] == 0 and base_score[1] == 0 and base_score[2] == 0 and base_score[3] == 0:
        return base
    best, best_score = base, base_score
    for rung, cc in enumerate((conn_clear, clearance, 1.0, 0.0)):
        cinfl = [r.adjusted(-cc, -cc, cc, cc) for r in conn_orig]
        for mids in _candidates(infl + cinfl, cc, cc):
            sc = _route_score(mids, s, e, ns, ne, infl, conn_orig, conn_pairs, avoid_segs, rung)
            if sc < best_score:
                best, best_score = mids, sc

    # [§8 항목19 F1 수정, 2026-08-14] 최후 수단 — 위 사다리를 다 돌아도 여전히 제3자 도형을
    # 관통하면(best_score[0] != 0), 이 경우에 한해서만 제3자 장애물을 clearance로 안 부풀린
    # **원본 경계**로 다시 시도한다. 근본원인: 장애물이 연결 도형에 밀착하면 스텁 이탈점이
    # 부풀린 장애물 사각형 안쪽에 갇혀(도형 자신은 obstacle 목록에 없어 반대편 격자선이 아예
    # 없다) A*가 매 사다리 rung에서 전부 실패하고 관통 preferred로 폴백한다(재현·근본원인:
    # `docs/route_review_2026-08.md` 3단계 F1). 부풀리지 않은 원본 경계라면 시작/끝점이 그
    # 경계에 딱 붙어 있을 뿐 "안"은 아니라서(`_seg_hits_rect`의 접촉=통과 규약) A*가 격자
    # 노드를 하나 얻어 우회를 찾을 수 있다. 대가로 이 최후수단 경로는 그 장애물과의 안전
    # 여백(clearance)이 없다 — 그래도 "정말로 관통"보다는 낫다는 판단(자주 발동하면 미관
    # 재검토 여지, `docs/route_review_2026-08.md` 6단계 "미해결로 남긴 것" 참조). 안전
    # 여백판정(infl)이 아니라 원본(obstacles) 기준으로만 관통 여부를 재확인해 채택한다 —
    # 이미 결함 없는 정상 케이스는 best_score[0]==0이라 이 블록에 아예 진입하지 않는다(무회귀).
    if best_score[0] != 0 and obstacles:
        for mids in _candidates(obstacles, 0.0, 0.0):
            full = _dedup_pts([s] + mids + [e])
            if not _path_hits_rects(full, obstacles):
                best = mids
                break
    return best


# ---------------------------------------------------------------------------
# [우리 확장] 다중선택 그룹 변형 (회전·스케일) — Stage 1
# ---------------------------------------------------------------------------
def _rotate_about(p: QPointF, c: QPointF, deg: float) -> QPointF:
    """씬 좌표점 p를 중심 c 기준 deg만큼 회전(양수=시계, y-down 화면 규약 — setRotation과 동일)."""
    r = math.radians(deg)
    cos, sin = math.cos(r), math.sin(r)
    dx, dy = p.x() - c.x(), p.y() - c.y()
    return QPointF(c.x() + dx * cos - dy * sin, c.y() + dx * sin + dy * cos)


# ---------------------------------------------------------------------------
# [Stage2] 기하 리베이크 그룹 변형 — 비균일 스케일(1축)·미러 공통 machinery
# ---------------------------------------------------------------------------
def _axis_scale_fn(axis: str, anchor: float, f: float):
    """씬공간 1축 스케일 함수 — axis('x'|'y') 방향으로 anchor 좌표선 기준 f배(다른 축 불변)."""
    if axis == "x":
        return lambda p: QPointF(anchor + (p.x() - anchor) * f, p.y())
    return lambda p: QPointF(p.x(), anchor + (p.y() - anchor) * f)


def _mirror_fn(axis: str, c: float):
    """씬공간 반사 함수 — axis('x'|'y') 좌표를 c 기준 반전. axis='x'=좌우, 'y'=상하 미러."""
    if axis == "x":
        return lambda p: QPointF(2.0 * c - p.x(), p.y())
    return lambda p: QPointF(p.x(), 2.0 * c - p.y())


def _iter_bound_endpoints(arrow):
    """화살표의 '바인딩된' 끝점 (idx, shape) 나열(곡선=0·1, 직선=0·마지막)."""
    if isinstance(arrow, _ArrowItem):
        idxs = (0, 1)
    elif isinstance(arrow, _PolyArrowItem):
        idxs = (0, len(arrow._pts) - 1)
    else:
        return
    for idx in idxs:
        sh = arrow._bound(idx)
        if sh is not None:
            yield idx, sh


def _collect_bound_arrows(scene, shapes):
    """scene의 모든 화살표 중 shapes 안 도형에 끝점이 바인딩된 (arrow, idx, shape) 목록."""
    out = []
    if scene is None:
        return out
    shapeset = set(shapes)
    for it in scene.items():
        if isinstance(it, (_ArrowItem, _PolyArrowItem)):
            for idx, sh in _iter_bound_endpoints(it):
                if sh in shapeset:
                    out.append((it, idx, sh))
    return out


def _snapshot_set(geom_items, bound_info):
    """undo·드래그 복원 대상 = 변형할 아이템 ∪ 부착점만 바뀌는 (미선택) 화살표."""
    snap_set = list(geom_items)
    for arrow, _idx, _sh in bound_info:
        if arrow not in snap_set:
            snap_set.append(arrow)
    return snap_set


def _rebake_selection(geom_items, bound_info, fn):
    """geom_items 기하를 fn으로 리베이크 + 바인딩 부착점 fn 보정 + 미선택 추종 화살표 reroute.
    호출 전 각 아이템은 '원본 상태'여야 한다(드래그는 매 프레임 apply_geom로 원복 후 호출).
    도형 transform은 리베이크로 안 바뀌므로 부착점 보정에 mapTo/FromScene을 그대로 쓴다."""
    geomset = set(geom_items)
    # 부착점 보정 — 도형이 리베이크되면 그 로컬 부착점도 같은 씬변형으로 옮겨야 상대 테두리
    # 위치가 유지된다(먼저: 원본 부착점 기준으로 계산해야 하므로 기하 리베이크보다 앞).
    for arrow, idx, sh in bound_info:
        old = arrow._bind_pt(idx)
        if old is None:
            continue
        arrow.set_bound(idx, sh, sh.mapFromScene(fn(sh.mapToScene(old))))
    for it in geom_items:
        it.rebake_scene(fn)
    # 미선택(그룹에 안 든) 바인딩 화살표는 새 부착점으로 추종(선택된 화살표는 이미 리베이크됨).
    for arrow, _idx, _sh in bound_info:
        if arrow not in geomset:
            arrow.reroute(pin_pred=lambda i: True)


# ---------------------------------------------------------------------------
# [2d] 빠른 생성(quick-create) — 도트 방향으로 화살표+동일도형 생성
# ---------------------------------------------------------------------------
_QC_OPP = {"r": "l", "l": "r", "t": "b", "b": "t"}
_QC_GAP = 40.0   # 원본과 복제 사이 씬 간격(기본 배치)
_QC_SIDE_NORMAL = {  # 각 변의 바깥 단위 법선(scene) — 직각 엘보 미리보기/생성 시 이탈 방향으로 씀.
    "t": QPointF(0, -1), "r": QPointF(1, 0), "b": QPointF(0, 1), "l": QPointF(-1, 0),
}


def _far_enough_for_self_loop(p: QPointF, q: QPointF, eps: float = 1.0) -> bool:
    """[자기자신 연결 버그 수정 2026-07-30] 커넥터 시작점과 스냅된 종착점이 사실상 같은 점이면
    False(드래그 시작 직후 같은 포트로 도로 스냅되는 퇴화 0-길이 케이스 — 기존 'snap 도형이
    src면 무바인딩' 가드의 원래 의도). 그 외(같은 도형의 '다른' 포트로 진짜 자기연결을 의도한
    경우)는 True — 라우터(_route_ortho)는 자기연결(conn_rects 양끝이 같은 rect)을 이미 올바르게
    바깥으로 우회시키므로(검증됨), 더는 무바인딩으로 막을 이유가 없다."""
    return (p.x() - q.x()) ** 2 + (p.y() - q.y()) ** 2 > eps * eps


def _edge_mid(r: QRectF, side: str) -> QPointF:
    """씬 사각 r의 한 변(t/r/b/l) 중점."""
    if side == "r":
        return QPointF(r.right(), r.center().y())
    if side == "l":
        return QPointF(r.left(), r.center().y())
    if side == "t":
        return QPointF(r.center().x(), r.top())
    return QPointF(r.center().x(), r.bottom())


def _qc_default_delta(sr: QRectF, side: str) -> QPointF:
    """기본 배치 델타 — 원본 씬사각 sr에서 side 방향으로 (도형크기+간격)만큼."""
    if side == "r":
        return QPointF(sr.width() + _QC_GAP, 0.0)
    if side == "l":
        return QPointF(-(sr.width() + _QC_GAP), 0.0)
    if side == "b":
        return QPointF(0.0, sr.height() + _QC_GAP)
    return QPointF(0.0, -(sr.height() + _QC_GAP))


class _GroupTransform:
    """다중선택(최상위 2개 이상) 시 공통 바운딩 박스 + 회전·스케일 핸들.

    개별 아이템 변형(_HandleResizeMixin)이 '자기 중심' 기준인 것과 달리, 그룹 중심/모서리를
    기준으로 **여러 아이템을 한 번에** 강체 회전·균일 스케일한다. 각 아이템은 Qt의
    pos/rotation/scale만 바꾸므로(기하 리베이크 없음) 되돌리기·직렬화가 기존과 호환된다.

    핵심 수학: 아이템의 transformOrigin 씬점 A = mapToScene(origin) = pos+origin 은 회전·스케일과
    무관(Qt는 origin을 기준으로 회전·스케일하되 그 점의 씬 위치는 pos에만 의존). 그래서
    A를 그룹 기준으로 옮기고(pos 조정) rotation/scale을 더하면 아이템 전체가 강체로 변형된다.
    (비유: 회전목마 — 각 말은 제자리서 돌면서(회전) 동시에 축을 중심으로 공전(pos)한다.)
    """
    _HANDLE_PX = 10.0   # 화면 px — 모서리 사각 핸들 한 변(단일선택 _HandleResizeMixin과 통일)
    _HIT_PX = 24.0      # 화면 px — 핸들 잡기 지름(줌 무관)
    _ROT_GAP_PX = 22.0  # 화면 px — bbox 위 회전 핸들 간격

    def __init__(self, view):
        self._view = view
        self._active = None   # None | ("rotate",..) | ("scale",..) | ("scale_axis",axis,anchor,pt)
        self._snap = None     # 회전·균일스케일 전 상태 스냅샷(xform undo·기준값)
        self._center = None
        self._anchor = None
        self._start_angle = 0.0
        self._start_dx = 0.0
        self._start_dy = 0.0
        # [Stage2] 비균일 스케일(1축 변 핸들) — 기하 리베이크 기반
        self._axis = None          # "x" | "y"
        self._anchor_val = 0.0     # 고정 좌표선(반대 변)
        self._axis_start = 0.0     # 시작 델타(bbox 폭·높이)
        self._geom_snap = None     # [(item, capture_geom()), ...] — 원복·undo
        self._geom_items = None    # 기하 리베이크 대상(선택 아이템)
        self._bound_info = None    # _collect_bound_arrows 결과

    def _scene(self):
        return self._view.scene()

    def _s(self) -> float:
        return self._view._view_scale()

    def items(self):
        sc = self._scene()
        if sc is None:
            return []
        return [it for it in sc.selectedItems()
                if it.parentItem() is None and isinstance(it, _HandleResizeMixin)]

    def available(self) -> bool:
        """그룹 오버레이 표시·조작 조건 — 최상위 2개 이상 선택 & select/손 도구."""
        if len(self.items()) < 2:
            return False
        return getattr(self._view._owner, "current_tool", None) in ("select", None)

    def bbox(self) -> QRectF | None:
        its = self.items()
        if len(its) < 2:
            return None
        r = None
        for it in its:
            # [실사용 버그 수정 2026-08-10] 삼각형처럼 bbox와 실제 외곽선이 다른 도형은
            # `_content_rect()`(패딩된 자기 bbox)를 쓰면 그룹 점선 테두리가 실제 변보다
            # 바깥으로 떠 보였다(`_apply_smart_snap.srect()`와 같은 병, `_tight_scene_bbox`
            # 주석 참조) — 재사용해 통일.
            br = _tight_scene_bbox(it) or it.mapToScene(it._content_rect()).boundingRect()
            r = br if r is None else r.united(br)
        return r

    # ---- 핸들 기하(씬 좌표) --------------------------------------------------
    def _corners(self, b: QRectF):
        return [b.topLeft(), b.topRight(), b.bottomRight(), b.bottomLeft()]

    def _edges(self, b: QRectF):
        """변 중점 핸들 — (핸들점, 축, 고정좌표선(반대 변)). 축 방향으로 1축 비균일 스케일."""
        return [
            (QPointF(b.center().x(), b.top()),    "y", b.bottom()),  # 상
            (QPointF(b.right(), b.center().y()),  "x", b.left()),    # 우
            (QPointF(b.center().x(), b.bottom()), "y", b.top()),     # 하
            (QPointF(b.left(), b.center().y()),   "x", b.right()),   # 좌
        ]

    def _rot_center(self, b: QRectF) -> QPointF:
        return QPointF(b.center().x(), b.top() - self._ROT_GAP_PX / self._s())

    def handle_at(self, scene_pt: QPointF):
        """씬점이 회전/스케일/변 핸들 위면 조작 튜플, 아니면 None."""
        b = self.bbox()
        if b is None:
            return None
        hit = (self._HIT_PX / self._s()) / 2.0
        if QLineF(self._rot_center(b), scene_pt).length() <= hit:
            return ("rotate", b.center())
        corners = self._corners(b)
        for i, c in enumerate(corners):
            if QLineF(c, scene_pt).length() <= hit:
                return ("scale", corners[(i + 2) % 4], c)  # anchor = 대각 모서리
        for pt, axis, anchor_val in self._edges(b):        # [Stage2] 변 중점 = 1축 비균일
            if QLineF(pt, scene_pt).length() <= hit:
                return ("scale_axis", axis, anchor_val, pt)
        return None

    # ---- 페인트 -------------------------------------------------------------
    def paint(self, painter: QPainter, s: float):
        b = self.bbox()
        if b is None:
            return
        painter.setPen(QPen(QColor(_BLUE), 1.0 / s, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(b)
        h = self._HANDLE_PX / s
        painter.setPen(QPen(QColor("white"), 1.0 / s))
        painter.setBrush(QBrush(QColor(_BLUE)))
        for c in self._corners(b):
            painter.drawRect(QRectF(c.x() - h / 2, c.y() - h / 2, h, h))
        for pt, _axis, _av in self._edges(b):          # [Stage2] 변 중점 핸들(1축 비균일 스케일)
            painter.drawRect(QRectF(pt.x() - h / 2, pt.y() - h / 2, h, h))
        rc = self._rot_center(b)                       # 회전 핸들 — 코랄 원(개별 회전 핸들과 색 통일)
        painter.setBrush(QBrush(QColor(_PEACH)))
        painter.drawEllipse(rc, h / 2, h / 2)

    # ---- 변형 트랜잭션 ------------------------------------------------------
    def begin(self, hit, scene_pt: QPointF):
        self._active = hit
        if hit[0] == "scale_axis":
            self._axis = hit[1]
            self._anchor_val = hit[2]
            # [버그수정 2026-08-01] 이상적 변 중점(hit[3])이 아니라 실제 클릭점(scene_pt) 기준으로
            # 시작 벡터를 잡는다 — 핸들 히트존이 24px 폭이라 클릭이 중점에서 벗어나면(항상 벗어남)
            # f가 드래그 시작 즉시 1이 아니게 되어 클릭 순간 크기가 튀어 보였다.
            cur = scene_pt.x() if self._axis == "x" else scene_pt.y()
            self._axis_start = cur - self._anchor_val
            self._begin_geom()
            return
        # 회전·균일 스케일(Stage1) — pos/rot/scale/origin 스냅샷.
        self._snap = [(it, QPointF(it.pos()), it.rotation(), it._scale_or_1(),
                       QPointF(it.transformOriginPoint())) for it in self.items()]
        if hit[0] == "rotate":
            self._center = hit[1]
            self._start_angle = math.degrees(math.atan2(
                scene_pt.y() - self._center.y(), scene_pt.x() - self._center.x()))
        else:
            self._anchor = hit[1]
            # [버그수정 2026-08-01] 위 scale_axis와 동일 — 이상적 모서리(hit[2])가 아니라 실제
            # 클릭점(scene_pt) 기준 시작 벡터라야 f=1로 시작해 드래그 첫 프레임에 튀지 않는다.
            self._start_dx = scene_pt.x() - self._anchor.x()
            self._start_dy = scene_pt.y() - self._anchor.y()

    def _begin_geom(self):
        """[Stage2] 기하 리베이크용 스냅샷 — 선택 아이템 + 부착점 바뀌는 화살표까지."""
        self._geom_items = self.items()
        shapes = [it for it in self._geom_items
                  if not isinstance(it, (_ArrowItem, _PolyArrowItem))]
        self._bound_info = _collect_bound_arrows(self._scene(), shapes)
        self._geom_snap = [(it, it.capture_geom())
                           for it in _snapshot_set(self._geom_items, self._bound_info)]

    def update_to(self, scene_pt: QPointF, shift: bool = False):
        if self._active is None:
            return
        if self._active[0] == "scale_axis":
            cur = scene_pt.x() if self._axis == "x" else scene_pt.y()
            if abs(self._axis_start) < 1e-9:
                return
            f = (cur - self._anchor_val) / self._axis_start
            f = max(0.05, min(f, 20.0))   # 미러(음수)는 별도 액션 — 여기선 뒤집힘 방지
            self._apply_geom_fn(_axis_scale_fn(self._axis, self._anchor_val, f))
            return
        if self._active[0] == "rotate":
            cur = math.degrees(math.atan2(
                scene_pt.y() - self._center.y(), scene_pt.x() - self._center.x()))
            d = cur - self._start_angle
            if shift:
                d = round(d / 15.0) * 15.0
            self._apply_rotate(self._center, d)
        else:
            dx = scene_pt.x() - self._anchor.x()
            dy = scene_pt.y() - self._anchor.y()
            denom = self._start_dx * self._start_dx + self._start_dy * self._start_dy
            if denom < 1e-9:
                return
            # 대각선 방향에 커서를 투영 → 균일 스케일 배율(바깥=확대, 안쪽=축소). Stage1은
            # 미러(음수 뒤집기) 미지원이라 하한 클램프로 뒤집힘·소실 방지.
            f = (dx * self._start_dx + dy * self._start_dy) / denom
            f = max(0.05, min(f, 20.0))
            self._apply_scale(self._anchor, f)

    def _apply_rotate(self, center: QPointF, ddeg: float):
        for it, pos0, rot0, _sc0, org0 in self._snap:
            a = QPointF(pos0.x() + org0.x(), pos0.y() + org0.y())
            a2 = _rotate_about(a, center, ddeg)
            it.setRotation((rot0 + ddeg) % 360)
            it.setPos(a2.x() - org0.x(), a2.y() - org0.y())

    def _apply_scale(self, anchor: QPointF, f: float):
        for it, pos0, _rot0, sc0, org0 in self._snap:
            ax = pos0.x() + org0.x()
            ay = pos0.y() + org0.y()
            a2x = anchor.x() + (ax - anchor.x()) * f
            a2y = anchor.y() + (ay - anchor.y()) * f
            # 이 코드베이스의 boundingRect는 핸들 여유분이 scale 의존(_handle_px가 /scale)이라
            # scale 변경 전 경계 캐시를 무효화해야 잔상·페인트 잘림을 막는다(단일 리사이즈와 동일).
            it.prepareGeometryChange()
            it.setScale(sc0 * f)
            it.setPos(a2x - org0.x(), a2y - org0.y())

    def _apply_geom_fn(self, fn):
        """[Stage2] 원본 스냅샷으로 원복 후 fn으로 리베이크(매 프레임 — 누적 방지)."""
        for it, tok in self._geom_snap:
            it.apply_geom(tok)
        _rebake_selection(self._geom_items, self._bound_info, fn)

    def end(self):
        if self._active is not None:
            if self._active[0] == "scale_axis":
                if self._geom_snap:
                    self._view._owner.push_undo_geom(self._geom_snap)
            elif self._snap:
                self._view._owner.push_undo_xform(self._snap)
        self._active = None
        self._geom_snap = None
        self._geom_items = None
        self._bound_info = None
        self._snap = None




# core_view.py·annotator_core.py의 `import *`가 밑줄 접두 이름까지 넘겨받게 강제(위와 동일 이유).
# core_constants에서 이미 재수출받은 이름까지 포함해 전부 다시 내보낸다(연쇄 재수출).
__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
