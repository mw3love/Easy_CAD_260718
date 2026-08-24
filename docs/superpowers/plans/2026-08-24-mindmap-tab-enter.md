# Tab/Enter 마인드맵 뻗기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 캔버스에서 도형을 선택한 채로 `Tab`을 누르면 자식 도형+연결 화살표가 즉시 생성되고,
`Enter`를 누르면 같은 부모를 공유하는 형제 도형이 생성되며, 생성 즉시 텍스트 편집 모드로
들어가 마우스 없이 계속 타이핑만으로 마인드맵을 뻗어나갈 수 있게 한다.

**Architecture:** 새 데이터모델은 만들지 않는다 — 기존 도형+`_PolyArrowItem` 연결을 트리로
재해석한다(부모→자식 화살표 = 트리 엣지, `_arrows_bound_to`로 역추적). 새 노드는 항상
"뻗어나가는 원본 도형"을 `.clone()`해 같은 타입·스타일을 물려받는다(사각형에서 뻗으면
사각형, 심볼에서 뻗으면 같은 심볼). 배치는 전체 트리 재배치가 아니라 증분 배치 — 새 노드만
빈 자리를 찾아 놓고 기존 노드는 절대 움직이지 않는다. 새 파일 `easycad/canvas/host_mindmap.py`
(`_MindMapMixin`)가 순수 도형 조작 로직을 담당하고, 키보드 배선은 기존
`easycad/canvas/core_view.py`의 `_AnnotatorView.keyPressEvent`/`event()`에 최소 침습으로
얹는다(기존 화살표키 nudge·ESC·csym-place 분기는 무변경).

**Tech Stack:** PyQt6(QGraphicsScene/View), 기존 `_RectItem`/`_EllipseItem`/`_SymbolItem`/
`_PolygonItem`/`_TextItem`/`_PolyArrowItem` 클래스, `pytest`(+ `tests/test_easycad.py` 자체
러너로도 재확인).

**Spec:** 별도 스펙 파일 없음 — 이 세션의 deep-interview로 정리한 결정사항을 아래 Architecture
및 각 태스크에 그대로 반영했다(대화 요약: Tab=자식, Enter=형제, 캔버스 상시 확장, 모든 도형에
적용, 텍스트 편집 중에도 즉시 적용, 1차 범위는 "뻗기"만 — 트리 탐색(Alt+방향키)은 2차로 보류).

## Global Constraints

- 새 외부 의존성 추가 금지 — 기존 PyQt6 API + 이미 있는 `_arrows_bound_to`/`_begin_label_edit`/
  `push_undo_add_many`/`.clone()`만 재사용한다(규칙 2 손안의 카드: 이미 다 있음).
- 기존 방향키(단순=10px, Shift/Ctrl=1px 정밀이동) 동작은 절대 변경하지 않는다.
- `Shift+Enter`(라벨 줄바꿈)와 `Shift+Tab`(Backtab)은 이번 스코프에서 마인드맵 동작을 얻지
  않는다 — Backtab은 조용히 무시(트리 탐색은 2차 스코프).
- 새 노드가 적용되는 도형 타입은 `_RectItem, _EllipseItem, _SymbolItem, _PolygonItem,
  _TextItem`뿐이다(화살표·선·펜·표·이미지·표제란·커넥터라벨 제외).
- 기존 코드 포맷·주석 관례(한국어 주석, `[신규기능]`/`[우리 확장]` 태그)를 그대로 따른다.
- 테스트는 `pytest tests/test_part13_mindmap.py`와 `python tests/test_easycad.py`(전체
  스위트) 둘 다 통과해야 한다.
- 비자명 커밋에는 프로젝트 CLAUDE.md 규칙대로 `Rejected/Constraint/Confidence/Not-tested`
  트레일러 + `Co-Authored-By: Claude Opus 4.8`(또는 실제 실행 모델)를 붙인다.

---

## Task 1: 백엔드 — `host_mindmap.py`(`_MindMapMixin`) + `CanvasWindow` 배선

**Files:**
- Create: `easycad/canvas/host_mindmap.py`
- Modify: `easycad/canvas/host.py:26,72-75` (import 추가 + `CanvasWindow` 베이스 클래스에
  `_MindMapMixin` 추가)
- Test: `tests/test_part13_mindmap.py` (신규)

**Interfaces:**
- Consumes(기존 코드, 조사로 확인 완료):
  - `self._arrows_bound_to(item) -> list[(arrow, idx)]` (`host_context.py:329`) — idx==0이면
    item이 화살표 시작점, idx!=0이면 끝점.
  - `self.push_undo_add_many(items: list)` (`host_undo.py:110`)
  - `self._scene` (CanvasWindow의 활성 문서 씬, `_PER_DOC_ATTRS` 프로퍼티)
  - `self.current_color / self.current_width / self.arrow_head_at_end`
  - `view._begin_label_edit(item)` (`core_view.py:3889`, `_AnnotatorView` 메서드 — 라벨
    생성+편집모드 진입+select-all까지 전부 처리, 라벨 생성은 자체적으로
    `push_undo_add(lbl)`까지 호출함)
  - `_border_attach(rect_scene, toward) -> QPointF` (`host_widgets.py:167`)
  - 각 아이템의 `.clone()`(`_RectItem`/`_EllipseItem`/`_SymbolItem`/`_PolygonItem`/
    `_TextItem` 전부 정의돼 있음, 라벨은 복사 안 함 — `core_shapes.py:407` `_copy_common_to`
    확인 완료) / `.rect()` / `.mapRectToScene()` / `.mapFromScene()`
  - `_PolyArrowItem(color, width, head_at_end)`, `.set_points(a, b)`,
    `.set_bound(idx, item, local_pt)`, `.build_elbow()`, `._pts`
- Produces(이 태스크가 새로 만드는 것, Task 2가 그대로 씀):
  - `CanvasWindow.mm_is_node(item) -> bool`
  - `CanvasWindow.mm_children(item) -> list[QGraphicsItem]`
  - `CanvasWindow.mm_parent(item) -> QGraphicsItem | None`
  - `CanvasWindow.mm_create_child(parent_item, view) -> QGraphicsItem | None`
  - `CanvasWindow.mm_create_sibling(item, view) -> QGraphicsItem | None`

- [ ] **Step 1: 실패하는 테스트부터 작성 — `tests/test_part13_mindmap.py`**

```python
"""Tab/Enter 마인드맵 뻗기 — 백엔드(host_mindmap.py) 단독 검증. 키보드 배선(실제 Tab/
Enter 키 입력) 테스트는 Task 2에서 이 파일 하단에 추가된다.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest tests/test_part13_mindmap.py.
"""
from PyQt6.QtCore import Qt, QRectF, QPointF

from _shared import *  # noqa: F401,F403


def _mm_rect(w, x, y, wd=120.0, ht=120.0):
    it = _RectItem(QRectF(0, 0, wd, ht))
    it.setPen(w.make_pen())
    it.setBrush(w.make_brush())
    it.setPos(x, y)
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def test_mm_is_node_accepts_shapes_rejects_arrows():
    w = CanvasWindow()
    rect = _mm_rect(w, 0, 0)
    arrow = _mk_arrow(w, 0, 0, 10, 10)
    assert w.mm_is_node(rect) is True
    assert w.mm_is_node(arrow) is False


def test_mm_connect_then_children_and_parent_roundtrip():
    w = CanvasWindow()
    a = _mm_rect(w, 0, 0)
    b = _mm_rect(w, 300, 0)
    arr = w.mm_connect(a, b)
    assert arr in w._scene.items()
    assert w.mm_children(a) == [b]
    assert w.mm_parent(b) is a
    assert w.mm_parent(a) is None
    assert w.mm_children(b) == []


def test_mm_free_rect_avoids_existing_node():
    w = CanvasWindow()
    existing = _mm_rect(w, 0, 0)
    probe = QRectF(0, 0, 120, 120)
    free = w.mm_free_rect(probe, (0.0, 144.0))
    assert not existing.sceneBoundingRect().intersects(free)
    assert free.top() >= 120.0 - 1e-6


def test_mm_create_child_places_to_the_right_and_connects():
    w = CanvasWindow()
    parent = _mm_rect(w, 0, 0)
    child = w.mm_create_child(parent, w._view)
    assert child is not None
    assert w.mm_parent(child) is parent
    cr = child.mapRectToScene(child.rect())
    pr = parent.mapRectToScene(parent.rect())
    assert cr.left() >= pr.right()
    fi = w._scene.focusItem()
    assert fi is not None and fi.parentItem() is child  # 즉시 편집모드(라벨 포커스)


def test_mm_create_child_second_child_stacks_below_first_without_overlap():
    w = CanvasWindow()
    parent = _mm_rect(w, 0, 0)
    kid1 = w.mm_create_child(parent, w._view)
    kid1_rect = kid1.mapRectToScene(kid1.rect())
    kid2 = w.mm_create_child(parent, w._view)
    kid2_rect = kid2.mapRectToScene(kid2.rect())
    assert kid2_rect.top() >= kid1_rect.bottom()
    assert not kid1_rect.intersects(kid2_rect)


def test_mm_create_sibling_with_parent_becomes_another_child_of_same_parent():
    w = CanvasWindow()
    parent = _mm_rect(w, 0, 0)
    kid1 = w.mm_create_child(parent, w._view)
    kid2 = w.mm_create_sibling(kid1, w._view)
    assert kid2 is not None
    assert w.mm_parent(kid2) is parent
    assert set(w.mm_children(parent)) == {kid1, kid2}


def test_mm_create_sibling_without_parent_makes_orphan_below_no_arrow():
    w = CanvasWindow()
    root = _mm_rect(w, 0, 0)
    before_arrows = [it for it in w._scene.items()
                      if isinstance(it, (_ArrowItem, _PolyArrowItem))]
    sib = w.mm_create_sibling(root, w._view)
    assert sib is not None
    assert w.mm_parent(sib) is None
    root_rect = root.mapRectToScene(root.rect())
    sib_rect = sib.mapRectToScene(sib.rect())
    assert sib_rect.top() >= root_rect.bottom()
    after_arrows = [it for it in w._scene.items()
                     if isinstance(it, (_ArrowItem, _PolyArrowItem))]
    assert after_arrows == before_arrows  # 화살표가 새로 생기지 않았다


def test_mm_create_child_undo_removes_node_and_arrow_and_label():
    w = CanvasWindow()
    parent = _mm_rect(w, 0, 0)
    before = len(w._scene.items())
    w.mm_create_child(parent, w._view)
    assert len(w._scene.items()) > before
    w.undo()  # 라벨 생성 되돌리기(_begin_label_edit이 별도 push_undo_add(lbl)를 쌓음)
    w.undo()  # 노드+화살표 되돌리기(push_undo_add_many 1건)
    assert len(w._scene.items()) == before


def test_mm_create_child_on_non_node_item_is_noop():
    w = CanvasWindow()
    arrow = _mk_arrow(w, 0, 0, 10, 10)
    assert w.mm_create_child(arrow, w._view) is None
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `pytest tests/test_part13_mindmap.py -v`
Expected: FAIL — `AttributeError: 'CanvasWindow' object has no attribute 'mm_is_node'` (그 외
전부 이 속성 부재로 연쇄 실패).

- [ ] **Step 3: `easycad/canvas/host_mindmap.py` 작성**

```python
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
    _ArrowItem, _PolyArrowItem,
)
from easycad.canvas.host_widgets import _border_attach


_MM_NODE_TYPES = (_RectItem, _EllipseItem, _SymbolItem, _PolygonItem, _TextItem)
_MM_GAP_X = 60.0    # 부모→자식 가로 간격(scene 단위)
_MM_GAP_Y = 24.0    # 형제 사이 세로 간격


class _MindMapMixin:
    """CanvasWindow에 다중상속되는 믹스인. `self`는 항상 CanvasWindow 인스턴스."""

    def mm_is_node(self, item) -> bool:
        return isinstance(item, _MM_NODE_TYPES)

    def mm_children(self, item):
        """item에서 뻗어나간(=item이 시작점인) 화살표들의 도착 도형 목록."""
        kids = []
        for arr, idx in self._arrows_bound_to(item):
            if idx != 0:
                continue
            other = arr._bind2 if isinstance(arr, _ArrowItem) else arr._bind_end
            if other is not None and other is not item:
                kids.append(other)
        return kids

    def mm_parent(self, item):
        """item으로 들어오는 화살표의 시작 도형(없으면 None = 루트/고아)."""
        for arr, idx in self._arrows_bound_to(item):
            if idx == 0:
                continue
            other = arr._bind1 if isinstance(arr, _ArrowItem) else arr._bind_start
            if other is not None and other is not item:
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
        view._begin_label_edit(new_node)
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
            view._begin_label_edit(new_node)
            return new_node
        return self.mm_create_child(parent, view)
```

- [ ] **Step 4: `CanvasWindow`에 믹스인 배선 — `easycad/canvas/host.py`**

`host.py:26` 근처(다른 `from easycad.canvas.host_*` 임포트들 옆)에 추가:

```python
from easycad.canvas.host_mindmap import _MindMapMixin
```

`host.py:72-75`의 클래스 선언을 수정:

```python
class CanvasWindow(
    _UIBuildMixin, _FileIOMixin, _LayersMixin, _StyleMixin, _UndoMixin,
    _SelectionMixin, _ContextMixin, _CanvasMixin, _MindMapMixin, QMainWindow,
):
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `pytest tests/test_part13_mindmap.py -v`
Expected: PASS (9개 전부)

- [ ] **Step 6: 전체 회귀 스위트 재확인**

Run: `python tests/test_easycad.py`
Expected: 기존 전체 통과 + 9종 추가(회귀 없음).

- [ ] **Step 7: 커밋**

```bash
git add easycad/canvas/host_mindmap.py easycad/canvas/host.py tests/test_part13_mindmap.py
git commit -m "$(cat <<'EOF'
feat(mindmap): Tab/Enter 마인드맵 뻗기 백엔드(host_mindmap.py) 추가

Rejected: 전체 트리 재배치(layout_positions 재사용) | 수동 배치가 매번 흐트러짐, 증분
배치(새 노드만 빈 자리 탐색)로 확정 — deep-interview 2026-08-24
Constraint: 새 데이터모델 금지 — 기존 화살표 연결을 트리 엣지로 재해석
Confidence: high
Not-tested: 키보드 배선(Task 2에서 이어짐) — 이 태스크는 mm_* API 직접호출로만 검증

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 키보드 배선 — `Tab`/`Enter`를 `core_view.py`의 `_AnnotatorView`에 연결

**Files:**
- Modify: `easycad/canvas/core_view.py:4013-4020` (편집 중 분기 추가),
  `easycad/canvas/core_view.py:4032-4051` (미편집 분기 추가), 새 `event()` 메서드 추가
  (`keyPressEvent` 바로 위, 3983번 줄 앞)
- Test: `tests/test_part13_mindmap.py`(Task 1에서 만든 파일에 이어서 추가)

**Interfaces:**
- Consumes: Task 1이 만든 `CanvasWindow.mm_is_node/mm_create_child/mm_create_sibling`
- Produces: 없음(이 태스크가 최종 사용자 기능 완성 지점)

- [ ] **Step 1: 실패하는 테스트부터 작성 — `tests/test_part13_mindmap.py`에 이어서 추가**

```python
from PyQt6.QtTest import QTest


def test_tab_key_on_selected_node_creates_child_and_focuses_new_label():
    w = CanvasWindow()
    w.set_tool("select")
    parent = _mm_rect(w, 0, 0)
    parent.setSelected(True)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)
    kids = w.mm_children(parent)
    assert len(kids) == 1
    fi = w._scene.focusItem()
    assert fi is not None and fi.parentItem() is kids[0]


def test_enter_key_while_editing_label_commits_text_and_creates_sibling():
    w = CanvasWindow()
    w.set_tool("select")
    parent = _mm_rect(w, 0, 0)
    kid = w.mm_create_child(parent, w._view)   # 이미 편집모드(라벨 포커스) 상태
    lbl = w._scene.focusItem()
    lbl.setPlainText("first")
    QTest.keyClick(w._view, Qt.Key.Key_Return)
    # mm_children()의 반환 순서는 QGraphicsScene.items()의 스태킹 순서를 따르므로(삽입
    # 순서와 같다는 보장이 없다) 인덱스가 아니라 원본 kid 객체 자체로 골라낸다.
    kids = w.mm_children(parent)
    assert len(kids) == 2
    assert kid in kids
    assert kid.has_label() and kid._label.toPlainText() == "first"
    new_fi = w._scene.focusItem()
    assert new_fi is not None
    sibling = new_fi.parentItem()
    assert sibling in kids and sibling is not kid


def test_shift_enter_while_editing_label_still_inserts_newline_not_mindmap():
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    w._view._begin_label_edit(node)
    lbl = w._scene.focusItem()
    QTest.keyClick(w._view, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert lbl.toPlainText() == "\n"
    assert w.mm_children(node) == []


def test_backtab_while_editing_does_not_create_node():
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    w._view._begin_label_edit(node)
    QTest.keyClick(w._view, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert w.mm_children(node) == []


def test_tab_with_multiple_selected_nodes_is_noop():
    w = CanvasWindow()
    w.set_tool("select")
    a = _mm_rect(w, 0, 0)
    b = _mm_rect(w, 300, 0)
    a.setSelected(True)
    b.setSelected(True)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)
    assert w.mm_children(a) == []
    assert w.mm_children(b) == []


def test_tab_in_viewer_mode_is_noop():
    w = CanvasWindow()
    w.set_tool("select")
    node = _mm_rect(w, 0, 0)
    node.setSelected(True)
    w.toggle_edit_mode()
    assert not w.is_edit_mode()
    QTest.keyClick(w._view, Qt.Key.Key_Tab)
    assert w.mm_children(node) == []


def test_tab_key_on_standalone_text_item_branches_into_new_text_item():
    w = CanvasWindow()
    w.set_tool("select")
    txt = _TextItem(w.current_color)
    w._scene.addItem(txt)
    txt.setSelected(True)
    QTest.keyClick(w._view, Qt.Key.Key_Tab)
    kids = w.mm_children(txt)
    assert len(kids) == 1
    assert isinstance(kids[0], _TextItem)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `pytest tests/test_part13_mindmap.py -v -k "tab_key or enter_key or shift_enter or backtab or multiple_selected or viewer_mode or standalone_text"`
Expected: FAIL — Tab/Enter 입력 후에도 `mm_children`이 빈 리스트(아직 키보드 배선이 없어
아무 일도 안 일어남).

- [ ] **Step 3: `easycad/canvas/core_view.py` 수정**

`class _AnnotatorView`에 `event()` 오버라이드를 `keyPressEvent` 정의(현재 3983번 줄)
바로 앞에 추가한다. 정확한 삽입 지점을 찾기 위한 앵커:

```python
    # ---- 키 (Space 토글 / 도구 단축키 / Delete / Ctrl+Z / Esc) -------------
    def keyPressEvent(self, event):
```

이 두 줄 바로 위에 삽입:

```python
    def event(self, e):
        """[마인드맵 뻗기] Tab/Backtab은 기본적으로 위젯 포커스 순회로 먼저 소비되므로
        (표 셀 편집기 `_CellEditor.event()`와 동일한 이유 — core_shapes.py 참조)
        keyPressEvent에 도달하기 전에 여기서 가로챈다. Backtab(Shift+Tab)도 함께 삼켜
        엉뚱하게 위젯 포커스가 캔버스 밖으로 튀는 것을 막지만, Tab과 달리 마인드맵 생성은
        트리거하지 않는다(트리 탐색은 2차 범위 — keyPressEvent가 Backtab을 그냥 무시)."""
        if e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.keyPressEvent(e)
            return True
        return super().event(e)

    # ---- 키 (Space 토글 / 도구 단축키 / Delete / Ctrl+Z / Esc) -------------
    def keyPressEvent(self, event):
```

`keyPressEvent` 안, 기존 편집-중-ESC 분기 바로 뒤에 마인드맵 분기를 추가한다. 앵커(현재
4013-4020번 줄):

```python
        if editing_text and key == Qt.Key.Key_Escape:
            # 텍스트 편집 중 ESC = 편집기 닫기가 아니라 텍스트 완료(=Ctrl+Enter와 동일).
            # clearFocus → focusOutEvent가 정리(빈 텍스트 폐기 / 비어있지 않으면 선택 해제).
            fi.clearFocus()
            return
        if not editing_text and key == Qt.Key.Key_Space:
```

`fi.clearFocus()` / `return` 다음, `if not editing_text and key == Qt.Key.Key_Space:` 앞에
삽입:

```python
        # [마인드맵 뻗기, 2026-08-24] 텍스트 편집 중에도 Tab/Enter가 즉시 다음 노드를
        # 만든다(deep-interview 확정 — "쓰면서 뻗어나가는" 흐름이 핵심). Shift+Enter(줄바꿈)
        # 는 제외해야 하므로 모디파이어를 명시적으로 검사한다.
        if editing_text and key in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and not (mods & Qt.KeyboardModifier.ShiftModifier):
            shape = fi.parentItem() if fi.parentItem() is not None else fi
            if self._owner.mm_is_node(shape):
                fi.clearFocus()
                if key == Qt.Key.Key_Tab:
                    self._owner.mm_create_child(shape, self)
                else:
                    self._owner.mm_create_sibling(shape, self)
                return
        if not editing_text and key == Qt.Key.Key_Space:
```

마지막으로 `if self._owner.is_edit_mode() and not editing_text:` 블록(현재 4032번 줄)의
맨 앞에 삽입한다. 앵커:

```python
        if self._owner.is_edit_mode() and not editing_text:
            # 화살표키 — 선택된 주석 이동. 기본은 넓게(10px), Shift/Ctrl로 세밀하게(1px). 도구와 무관.
            arrow = {
```

`if self._owner.is_edit_mode() and not editing_text:` 바로 다음 줄에 삽입(화살표키 주석보다
앞):

```python
        if self._owner.is_edit_mode() and not editing_text:
            # [마인드맵 뻗기, 2026-08-24] 텍스트 편집 중이 아니어도(마우스로 도형만 선택한
            # 상태) Tab/Enter는 동일하게 뻗는다 — "모든 도형에 상시 적용" 확정(다중선택·
            # 비-노드 타입은 mm_create_*가 각각 None을 반환해 조용히 no-op).
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                sel = self.scene().selectedItems()
                if len(sel) == 1 and self._owner.mm_is_node(sel[0]):
                    if key == Qt.Key.Key_Tab:
                        self._owner.mm_create_child(sel[0], self)
                    else:
                        self._owner.mm_create_sibling(sel[0], self)
                    return
            # 화살표키 — 선택된 주석 이동. 기본은 넓게(10px), Shift/Ctrl로 세밀하게(1px). 도구와 무관.
            arrow = {
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `pytest tests/test_part13_mindmap.py -v`
Expected: PASS (Task 1의 9개 + Task 2의 7개 = 16개 전부)

- [ ] **Step 5: 전체 회귀 스위트 재확인(기존 단축키·화살표키 nudge·ESC 흐름 무회귀 확인)**

Run: `python tests/test_easycad.py`
Expected: 전체 통과. 특히 `tests/test_part12_shortcuts.py`(방향키/Tab 인접 로직)와
`tests/test_part2_labels_routing.py`(라벨 편집 Enter/Shift+Enter 관련)가 무회귀인지 확인.

- [ ] **Step 6: 실제 창에서 자체 확인(전역 CLAUDE.md 규칙 11-d)**

```
python tools/screenshot.py
```
로는 상호작용(Tab 연타)을 못 잡으므로, `python run.py`를 오프스크린 강제 없이 직접 실행해
사각형 하나 만들고 Tab→Tab→Enter를 실제로 눌러 자식/형제가 뻗어나가는지, 새 도형마다 바로
타이핑 가능한지 눈으로 확인한다(마우스 클릭 자체가 아니라 결과 상태 확인이 목적이므로
가능하면 스크린샷으로 남긴다).

- [ ] **Step 7: 커밋**

```bash
git add easycad/canvas/core_view.py tests/test_part13_mindmap.py
git commit -m "$(cat <<'EOF'
feat(mindmap): Tab/Enter 키보드 배선 — 캔버스 상시 마인드맵 뻗기 완성

Rejected: 전용 마인드맵 모드/도구 신설 | deep-interview에서 "캔버스 상시 확장"으로 확정,
별도 진입 없이 어떤 도형에서도 바로 동작하는 쪽을 선택
Rejected: Alt+방향키 트리 탐색 동시 구현 | 1차 범위는 "뻗기"만으로 확정, 탐색은 실사용 후
필요성 재확인 뒤 2차로(docs/EasyCAD_계획.md §8 갱신 필요)
Constraint: 기존 방향키 nudge(단순/Shift/Ctrl)·Shift+Enter 줄바꿈 동작 무변경
Confidence: high(pytest 실제 QKeyEvent 경유 확인) — 다만 아래 Not-tested 참조
Not-tested: 실제 OS 마우스+키보드 입력으로 python run.py 직접 확인(Step 6에서 진행 예정),
회전된 도형에서 뻗었을 때 시각적 결과에 대한 실사용 피드백

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review 체크리스트(실행 전 참고용)

- **스펙 커버리지**: Tab=자식/Enter=형제(Task1+2) ✓, 캔버스 상시+모든 도형(Task2 `mm_is_node`
  게이트) ✓, 편집 중 즉시 적용(Task2 editing_text 분기) ✓, 새 데이터모델 없음(화살표 연결
  재해석, Task1) ✓, 기존 방향키 무변경(Task2는 그 블록 위에 삽입만, 코드 그대로) ✓,
  1차 범위=뻗기만·탐색 제외(Alt+방향키 관련 코드 없음) ✓.
- **플레이스홀더 스캔**: 전 단계 실행 가능한 실제 코드/명령으로 채움, TBD 없음.
- **타입 일관성**: `mm_create_child(parent_item, view)` / `mm_create_sibling(item, view)`
  시그니처가 Task1 정의·Task2 호출부 전부 동일.
