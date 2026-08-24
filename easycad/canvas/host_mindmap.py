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
        """새 노드의 편집 모드 진입. _TextItem과 일반 도형(sub-label 있음) 분기 처리."""
        if isinstance(new_node, _TextItem):
            # _TextItem은 clone()이 원본의 텍스트를 복사하므로 먼저 비운다.
            new_node.setPlainText("")
            # 텍스트 도구와 동일한 방식으로 편집 시작(view._begin_label_edit은 _TextItem
            # 메서드 부재로 사용 불가).
            new_node.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            new_node.setFocus()
            self._scene.clearSelection()
        else:
            # 일반 도형(사각형, 원, 심볼, 다각형)은 sub-label을 가지므로 기존 경로 사용.
            view._begin_label_edit(new_node)

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
        반드시 IntersectsItemBoundingRect로 조회한다."""
        dx, dy = step
        probe = QRectF(rect)
        guard = 0
        while guard < 200:
            collided = False
            for other in self._scene.items(probe, Qt.ItemSelectionMode.IntersectsItemBoundingRect):
                if self.mm_is_node(other) and other.sceneBoundingRect().intersects(probe):
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

    def mm_connect(self, src_item, dst_item):
        """src_item -> dst_item 직교 자동라우팅 화살표(mermaid_import._make_mermaid_edge와
        동일 패턴 — 이미 검증된 지속연결 바인딩 재사용)."""
        rs = self.mm_node_rect_scene(src_item)
        rd = self.mm_node_rect_scene(dst_item)
        a_src = _border_attach(rs, rd.center())
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
        arrow = self.mm_connect(parent_item, new_node)
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
