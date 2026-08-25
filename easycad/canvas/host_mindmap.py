"""CanvasWindow 믹스인 — Tab/Enter 마인드맵 뻗기(§8, 2026-08-24 deep-interview 확정).

키보드만으로 도형+화살표를 연속 생성하는 기능. 새 데이터모델은 없다 — 기존 도형+화살표
연결을 트리로 재해석한다(부모→자식 화살표 = 트리 엣지, `_arrows_bound_to`로 역추적).
배치는 전체 재배치가 아니라 증분 배치(새 노드만 빈 자리를 찾고 기존 노드는 절대 움직이지
않는다) — 1차 범위 확정(트리 탐색은 2차로 보류, docs/EasyCAD_계획.md §8 참조).

키보드 배선(실제 Tab/Enter 키 처리)은 이 파일이 아니라 core_view.py에 있다 — 여기는 순수
도형 조작(위치 계산·클론·연결·undo)만 담당해 키보드 없이도 독립적으로 테스트 가능하다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPointF, QRectF

from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _SymbolItem, _PolygonItem, _TextItem,
    _ArrowItem, _PolyArrowItem, _ConnectorLabel,
)
from easycad.canvas.host_widgets import _border_attach


_MM_NODE_TYPES = (_RectItem, _EllipseItem, _SymbolItem, _PolygonItem, _TextItem)
_MM_GAP_X = 60.0    # 부모→자식 가로 간격(scene 단위)
_MM_GAP_Y = 24.0    # 형제 사이 세로 간격


class _MindMapMixin:
    """CanvasWindow에 다중상속되는 믹스인. `self`는 항상 CanvasWindow 인스턴스."""

    def _mm_enter_edit_mode(self, new_node, view):
        """새 노드의 편집 모드 진입. _TextItem은 clone()이 원본 텍스트를 복사하므로 먼저
        비우고, 실제 진입은 `view.begin_edit_selected()`(범용 "선택 항목 편집 시작" —
        Ctrl+Enter와 공유하는 로직, core_view.py 참조)에 위임한다."""
        if isinstance(new_node, _TextItem):
            new_node.setPlainText("")
        view.begin_edit_selected(new_node)

    def mm_is_node(self, item) -> bool:
        # `_ConnectorLabel`은 `_TextItem`의 서브클래스지만(화살표를 따라 슬라이드하는
        # 라벨일 뿐 독립 노드가 아님) 마인드맵 대상에서 제외 — `_conn_shapes()`/
        # `_ConnectorLabel._qc_capable()`가 이미 같은 이유로 배제하는 것과 동일한 관례.
        return isinstance(item, _MM_NODE_TYPES) and not isinstance(item, _ConnectorLabel)

    def mm_children(self, item):
        """item에서 뻗어나간(=item이 시작점인) 화살표들의 도착 도형 목록.
        화살표는 마인드맵 노드가 아닌 도형(펜 궤적·선·열린 폴리라인 등, `.rect()`가 없음)
        에도 정상적으로 바인딩될 수 있으므로 `mm_is_node`로 반드시 걸러낸다 — 안 그러면
        호출부가 `.rect()`를 가정한 배치 계산에서 그대로 죽는다. 화살표가 편집 중 빈 라벨
        자기삭제 등으로 씬에서 빠져나간 뒤에도 남아있는 유령 바인딩은 `scene() is None`으로
        걸러낸다."""
        kids = []
        for arr, idx in self._arrows_bound_to(item):
            if idx != 0:
                continue
            other = arr._bind2 if isinstance(arr, _ArrowItem) else arr._bind_end
            if (other is not None and other is not item and other.scene() is not None
                    and self.mm_is_node(other)):
                kids.append(other)
        return kids

    def mm_parent(self, item):
        """item으로 들어오는 화살표의 시작 도형(없으면 None = 루트/고아).
        필터 근거는 `mm_children`과 동일(비-노드 바인딩·씬에서 빠진 유령 노드 배제)."""
        for arr, idx in self._arrows_bound_to(item):
            if idx == 0:
                continue
            other = arr._bind1 if isinstance(arr, _ArrowItem) else arr._bind_start
            if (other is not None and other is not item and other.scene() is not None
                    and self.mm_is_node(other)):
                return other
        return None

    def mm_node_rect_scene(self, item) -> QRectF:
        return item.mapRectToScene(item.rect())

    def mm_free_rect(self, rect: QRectF, step: tuple[float, float]) -> QRectF:
        """rect가 기존 마인드맵 노드와 안 겹칠 때까지 step 방향으로 밀어낸 결과.
        `items(rect, mode=...)`의 기본 판정(IntersectsItemShape)은 채움 없는 도형의 얇은
        테두리-링 히트영역만 보므로(core_shapes.py `_base_shape`) bbox 겹침을 놓친다 —
        반드시 IntersectsItemBoundingRect로 조회한다.

        [실사용 버그 수정 2026-08-25] 최종 겹침 판정은 `other.sceneBoundingRect()`가 아니라
        `mm_node_rect_scene(other)`(실제 도형 기하, 선택 장식 없음)를 써야 한다 — Enter로
        형제 노드를 만드는 순간 방금 만든 이전 형제가 아직 선택된 채인 경우가 흔한데(Tab 직후
        편집모드 종료 시점 자체가 그 노드에 대한 Enter이므로), 선택된 도형의 `boundingRect()`
        (`_HandleResizeMixin`)는 리사이즈 핸들·회전핸들·큐닷까지 포함해 실제 도형보다 훨씬
        크다 — 이 부풀려진 영역과 24px 세로 간격이 항상 겹쳐, `mm_free_rect`가 매번 통째로
        한 스텝(도형높이+간격) 더 밀어내고 있었다(Tab의 60px 가로 간격은 이 부풀림보다
        넉넉히 커서 안 걸림 — Tab은 괜찮고 Enter만 넓어 보이던 이유). 실측(사용자 스크린샷
        픽셀 대조): 예측된 밀림값(120+24=144)이 실제 관측 간격(167px)과 거의 정확히 일치."""
        dx, dy = step
        probe = QRectF(rect)
        guard = 0
        while guard < 200:
            collided = False
            for other in self._scene.items(probe, Qt.ItemSelectionMode.IntersectsItemBoundingRect):
                if self.mm_is_node(other) and self.mm_node_rect_scene(other).intersects(probe):
                    collided = True
                    break
            if not collided:
                return probe
            probe.translate(dx, dy)
            guard += 1
        return probe

    def mm_new_node_like(self, like_item, top_left: QPointF):
        """like_item과 같은 타입+스타일의 라벨 없는 새 노드를 top_left에 배치해 씬에 추가.
        회전·스케일은 물려받지 않는다(뻗어나간 자식이 부모의 임의 회전을 따라가면 계속
        누적돼 보기 어려워지므로 — 1차 범위 단순화)."""
        new = like_item.clone()
        new.setRotation(0.0)
        new.setScale(1.0)
        r = new.rect()
        new.setPos(top_left.x() - r.left(), top_left.y() - r.top())
        self._scene.addItem(new)
        return new

    def mm_parent_attach_point(self, parent_item):
        """[실사용 피드백] parent_item에서 이미 뻗어나간 마인드맵 화살표가 있으면 그
        부착점(씬좌표)을 반환 — 형제가 늘어날 때마다 `_border_attach`가 방향을 다시
        계산해 부착점이 오른쪽→아래쪽으로 슬금슬금 옮겨가던 버그 수정용. 없으면 None
        (호출부가 기존처럼 `_border_attach`로 새로 계산)."""
        for arr, idx in self._arrows_bound_to(parent_item):
            if idx != 0:
                continue
            other = arr._bind2 if isinstance(arr, _ArrowItem) else arr._bind_end
            if other is None or other.scene() is None or not self.mm_is_node(other):
                continue
            pt = arr._bind1_pt if isinstance(arr, _ArrowItem) else arr._bind_start_pt
            if pt is not None:
                return parent_item.mapToScene(pt)
        return None

    def mm_connect(self, src_item, dst_item, src_pt=None):
        """src_item -> dst_item 직교 자동라우팅 화살표(mermaid_import._make_mermaid_edge와
        동일 패턴 — 이미 검증된 지속연결 바인딩 재사용). src_pt를 주면 그 점을 그대로
        부착점으로 쓴다(형제 간 부착점 통일용, `mm_parent_attach_point` 참조)."""
        rs = self.mm_node_rect_scene(src_item)
        rd = self.mm_node_rect_scene(dst_item)
        a_src = src_pt if src_pt is not None else _border_attach(rs, rd.center())
        a_dst = _border_attach(rd, rs.center())
        arr = _PolyArrowItem(self.current_color, self.current_width, self.arrow_head_at_end)
        arr.set_points(a_src, a_dst)
        arr.set_bound(0, src_item, src_item.mapFromScene(a_src))
        arr.set_bound(len(arr._pts) - 1, dst_item, dst_item.mapFromScene(a_dst))
        arr._auto_route = True
        self._scene.addItem(arr)
        try:
            arr.build_elbow()
        except Exception:
            pass
        return arr

    def mm_create_child(self, parent_item, view):
        """[Tab] parent_item의 새 자식 노드+화살표 생성, 즉시 편집모드 진입.
        기존 자식이 있으면 그 아래(더 내려간 자리)에 쌓는다 — 기존 자식은 옮기지 않는다."""
        if not self.mm_is_node(parent_item):
            return None
        pr = self.mm_node_rect_scene(parent_item)
        kids = self.mm_children(parent_item)
        if kids:
            bottom = max(self.mm_node_rect_scene(k).bottom() for k in kids)
            top = bottom + _MM_GAP_Y
        else:
            top = pr.top()
        left = pr.right() + _MM_GAP_X
        candidate = QRectF(left, top, pr.width(), pr.height())
        candidate = self.mm_free_rect(candidate, (0.0, pr.height() + _MM_GAP_Y))
        new_node = self.mm_new_node_like(parent_item, candidate.topLeft())
        arrow = self.mm_connect(parent_item, new_node, src_pt=self.mm_parent_attach_point(parent_item))
        self.push_undo_add_many([new_node, arrow])
        self._scene.clearSelection()
        self._mm_enter_edit_mode(new_node, view)
        return new_node

    def mm_create_sibling(self, item, view):
        """[Enter] item과 같은 부모를 갖는 새 형제 노드 생성(부모가 없으면 item 아래에
        화살표 없는 고아 노드를 놓는다 — 두 번째 루트를 시작하는 것과 같음). 항상 부모의
        자식 목록 '끝'에 추가한다(v1: 중간 삽입이 아니라 append — 기존 형제는 안 밀어냄,
        docs/EasyCAD_계획.md §8 참조)."""
        if not self.mm_is_node(item):
            return None
        parent = self.mm_parent(item)
        if parent is None:
            ir = self.mm_node_rect_scene(item)
            candidate = QRectF(ir.left(), ir.bottom() + _MM_GAP_Y, ir.width(), ir.height())
            candidate = self.mm_free_rect(candidate, (0.0, ir.height() + _MM_GAP_Y))
            new_node = self.mm_new_node_like(item, candidate.topLeft())
            self.push_undo_add_many([new_node])
            self._scene.clearSelection()
            self._mm_enter_edit_mode(new_node, view)
            return new_node
        return self.mm_create_child(parent, view)

    # ---- [실사용 피드백 2026-08-25 후속] Alt+방향키 — 순수 생성 전용으로 재설계 -------
    # 이전엔 "그 방향에 이미 있으면 이동, 없으면 생성"(Lucid Alt+드래그 감각을 흉내낸 것)
    # 이었는데, 실사용 중 "새로 만들려 했는데 조용히 기존 도형으로 이동"·"이전 부모 밑에
    # 병렬로 생성돼버림" 혼란이 반복 보고됐다 — 두 의미가 같은 키에 얹혀있어 사용자가
    # 결과를 예측할 수 없었던 게 근본 원인. 순수 생성으로 단순화하면 이 혼란 자체가
    # 사라진다(대신 기존 노드 사이 자유 탐색은 범위 밖 — 마우스 클릭으로 대체, 재요청 시
    # 별도 설계). 왼쪽/위도 이제 생성 가능해져 기존(이동 전용)보다 기능이 늘었다.
    _MM_DIR_VEC = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}

    def mm_create_in_direction(self, item, direction, view):
        """[Alt+방향키] item에서 direction("right"/"left"/"down"/"up") 방향으로 새
        도형+화살표를 무조건 생성한다 — 그 자리에 이미 뭔가 있어도 이동하지 않고 새로
        만든다(mm_free_rect가 겹치는 도형만 피해서 배치, 그 결과 새 노드가 옆으로 밀려날
        수 있다). 부착점은 `mm_connect`의 기본 계산(목적지 중심 방향으로 재추정)을 안
        쓰고 direction으로 직접 결정한다 — 안 그러면 밀려난 새 노드의 중심 방향이
        바뀌어 항목①과 같은 부착점 드리프트가 재발한다(실측으로 확인,
        `mm_create_child`가 기존 화살표를 재사용해 피하는 것과 달리 여기는 direction
        자체가 이미 정답을 알고 있으므로 재계산 없이 바로 지정)."""
        if not self.mm_is_node(item):
            return None
        ir = self.mm_node_rect_scene(item)
        dx, dy = self._MM_DIR_VEC[direction]
        if dx:
            left = ir.right() + _MM_GAP_X if dx > 0 else ir.left() - _MM_GAP_X - ir.width()
            top = ir.top()
            step = (0.0, ir.height() + _MM_GAP_Y)
            src_pt = QPointF(ir.right() if dx > 0 else ir.left(), ir.center().y())
        else:
            left = ir.left()
            top = ir.bottom() + _MM_GAP_Y if dy > 0 else ir.top() - _MM_GAP_Y - ir.height()
            step = (ir.width() + _MM_GAP_X, 0.0)
            src_pt = QPointF(ir.center().x(), ir.bottom() if dy > 0 else ir.top())
        candidate = QRectF(left, top, ir.width(), ir.height())
        candidate = self.mm_free_rect(candidate, step)
        new_node = self.mm_new_node_like(item, candidate.topLeft())
        arrow = self.mm_connect(item, new_node, src_pt=src_pt)
        self.push_undo_add_many([new_node, arrow])
        self._scene.clearSelection()
        self._mm_enter_edit_mode(new_node, view)
        return new_node
