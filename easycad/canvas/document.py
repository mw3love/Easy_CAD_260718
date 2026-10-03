"""CanvasDocument — 문서(씬) 하나가 갖는 상태를 담는 그릇.

[§8 항목10, 2026-08-18] 다중 도면(탭+새 창) 지원의 1단계. 예전에는 이 모든 속성이
`CanvasWindow.__init__`에 인스턴스 속성으로 흩어져 있어 창=문서 1:1을 전제했다. 탭을
도입하며 "문서별로 분리돼야 하는 상태"만 이 클래스로 이설하고, `CanvasWindow`는 활성
문서로 그대로 포워딩하는 프로퍼티를 둔다(host.py 참조) — 8개 믹스인 6,500여 줄의 메서드
본문(`self._scene`, `self._undo` 등을 직접 읽고 쓰는 코드)은 전혀 손대지 않아도 되게 하기
위한 설계다.

창 전체(모든 탭)가 공유하는 sticky 설정(현재 도구·색·굵기·snap 토글 등)과 프로세스 전체가
공유하는 클립보드(`_clip`/`_clip_src`/`_style_clip`)는 여기 안 담는다 — 그건 각각
`CanvasWindow` 인스턴스 속성(변경 없음) / `host_widgets._SharedClipboard` 싱글턴이 맡는다.
"""
from __future__ import annotations

from contextlib import contextmanager

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPolygonF
from PyQt6.QtWidgets import QGraphicsScene

from easycad.canvas.annotator_core import _AnnotatorView
from easycad.canvas.host_widgets import _SCENE_HALF, _UndoEntry


class _DocScene(QGraphicsScene):
    """[점검 2단계 2026-10-03] 씬에서 빼는 최상위 아이템마다 "바로 위에 겹쳐 있던 최상위
    아이템"을 기억해 둔다(`_restack_above`). Qt는 removeItem→addItem하면 같은 z 안에서 항상
    맨 위로 올리고 원래 겹침 순서를 잊는다 — 그래서 삭제·도형 바꾸기·화살표 종류 바꾸기를
    되돌리면 채운 도형이 위에 있던 도형을 가렸다. 빼는 경로(삭제·TRIM·바꾸기·undo 등)가 여러
    곳이라 한 곳(여기)에서 기록하고, 되살리는 쪽(host_undo._apply_entry)이 `stackBefore`로
    제자리에 넣는다. 겹치지 않는 아이템끼리의 순서는 눈에 안 보이므로 겹치는 것만 본다."""

    _RESTACK_KEEP = 8   # 위쪽 후보 몇 개까지 — 바로 위가 같이 지워졌거나 사라져도 그다음으로

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._batch_depth = 0
        self._batch_order = None   # 일괄 편집 시작 시점의 최상위 쌓임 순서(위→아래)
        self._batch_pos = None

    @contextmanager
    def batch(self):
        """[점검 2단계 후속 2026-10-03] 한꺼번에 많이 빼는 동안(전체 삭제·undo/redo) 위/아래
        이웃을 겹침 검사 대신 **시작 시점의 전체 쌓임 순서 한 번**에서 고른다 — 개당 겹침 검사가
        Qt의 boundingRect 호출 13만 회(1000개 삭제에 ~1.2초)를 만들었다. 전체 순서 기준이라
        겹침 기준보다 오히려 정확하다."""
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._batch_order = self._batch_pos = None

    def _record_from_batch(self, item):
        if self._batch_order is None:
            self._batch_order = [it for it in self.items(Qt.SortOrder.DescendingOrder)
                                 if it.parentItem() is None]
            self._batch_pos = {it: i for i, it in enumerate(self._batch_order)}
        i = self._batch_pos.get(item)
        if i is None:   # 일괄 편집 도중 새로 들어온 아이템 — 겹침 방식으로
            return False
        k = self._RESTACK_KEEP
        item._restack_above = self._batch_order[max(0, i - k):i][::-1]   # 바로 위부터
        item._restack_below = self._batch_order[i + 1:i + 1 + k]
        return True

    def _safe_scene_rect(self, item):
        """지우는 순간의 아이템 범위 — **아이템의 boundingRect를 부르지 않는다**. 화살표 그리기를
        Esc로 끝내는 순간처럼 점이 1개만 남은 미완성 아이템은 boundingRect 자체가 실패해 앱이
        통째로 죽는다(전체 테스트에서 exit 127로 실측). 도형은 host가 이미 기억해 둔 마지막
        타이트 rect(`geom_snapshot`)를, 점 목록이 있는 것(화살표·다각형)은 점 좌표를 직접 쓴다.
        점이 2개 미만이면 None(기록 생략)."""
        doc = getattr(self, "_owner_doc", None)
        r = doc.geom_snapshot.get(item) if doc is not None else None
        if r is not None:
            return QRectF(r)
        pts = getattr(item, "_pts", None)
        if pts is None and hasattr(item, "_p1"):
            pts = [item._p1, item._p2]
        if pts is None:   # 점 목록이 없는 도형(사각형·원·글자 등) — 미완성 상태가 없어 안전
            return item.sceneBoundingRect()
        if len(pts) < 2:
            return None
        return item.mapToScene(QPolygonF(list(pts))).boundingRect()

    def removeItem(self, item):
        if (self._batch_depth and item.parentItem() is None and item.scene() is self
                and self._record_from_batch(item)):
            super().removeItem(item)
            return
        rect = (self._safe_scene_rect(item)
                if item.parentItem() is None and item.scene() is self else None)
        if rect is not None:
            above, below, seen_self = [], [], False
            # 테두리에 딱 닿은 화살표 끝도 선 두께만큼은 겹쳐 보이므로 조금 넓혀서 찾는다
            # (QRectF는 변이 닿기만 하면 "안 겹침"으로 본다).
            rect = rect.adjusted(-4, -4, 4, 4)
            for o in self.items(rect, Qt.ItemSelectionMode.IntersectsItemBoundingRect,
                                Qt.SortOrder.DescendingOrder):
                top = o.topLevelItem()
                if top is item:
                    seen_self = True
                elif not seen_self:
                    if top not in above:
                        above.append(top)
                elif top not in below and len(below) < self._RESTACK_KEEP:
                    below.append(top)
            # 내림차순이라 above의 끝쪽이 item에 가까운 것 — "바로 위"부터 위로 거슬러 오르는 순서.
            # below는 "바로 아래"부터 — 같이 지운 아래쪽 아이템은 위쪽이 먼저 사라져 above가
            # 비므로, 함께 되살릴 때 서로의 위아래를 맞추는 데 쓴다(host_undo._apply_entry).
            item._restack_above = above[::-1][:self._RESTACK_KEEP]
            item._restack_below = below
        super().removeItem(item)


class CanvasDocument:
    """도면 하나(씬 + undo/redo + 레이어 + 저장경로 + 라우팅/성능 캐시)."""

    def __init__(self, window):
        self.scene = _DocScene(window)
        self.scene.setSceneRect(-_SCENE_HALF, -_SCENE_HALF, 2 * _SCENE_HALF, 2 * _SCENE_HALF)
        self.scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        self.scene._owner_doc = self   # [§8 항목10] 씬 시그널 핸들러가 발신 문서를 역참조

        self.view = _AnnotatorView(self.scene, window)

        self.undo: list[_UndoEntry] = []
        self.redo: list[_UndoEntry] = []
        self.layers: list[dict] = [
            {"id": "default", "name": "기본", "visible": True, "locked": False}]
        self.doc_path: str | None = None
        # [실사용 피드백 2026-08-26] DXF/DWG는 손실 변환이라 `doc_path`(Ctrl+S 빠른저장
        # 대상)로 취급하지 않는다(host_fileio._do_save_ecad 주석 참조) — 그래도 탭 제목엔
        # 그 파일명을 보여주는 게 자연스러워, 표시 전용 경로를 별도로 둔다.
        self.external_path: str | None = None
        self.dirty = False   # [§8 항목10 Stage C]
        # [점검 1단계 2026-10-03] 자동 저장(fileio/autosave.py) — 복구 폴더 파일 id(첫 자동
        # 저장 때 부여)와 "마지막 자동 저장 뒤로 바뀐 게 있음" 표시.
        self.autosave_id: str | None = None
        self.autosave_pending = False
        self.untitled_n: int | None = None   # [§8 항목10 Stage B] host._create_doc()가 부여

        self.badge_n = 0
        self.paste_seq = 0
        self.pan_last: QPointF | None = None

        # 지속 연결 리라우팅 재진입 가드 + 드래그 중 미룬 화살표(host_canvas.py 참조).
        self.rerouting = False
        self.deferred_arrows: set = set()
        # [점검 2단계 후속 2026-10-03] undo/redo로 되살아난 화살표 — 지워질 때의 경로를 그대로
        # 갖고 돌아오므로 바로 다음 재라우팅 1회에서 뺀다(host_canvas._on_scene_changed).
        self.skip_reroute_once: set = set()
        self.deferred_fast = False

        self.group_sync_active = False   # [편의기능] 그룹 동반선택 재진입 가드

        # [성능수정 2026-08-07~2026-08-15] item → 마지막으로 관측한 '타이트' scene rect 등,
        # `_sync_geom_snapshot`/`_on_scene_changed`(host_canvas.py)가 쓰는 캐시.
        self.geom_snapshot: dict = {}
        self.last_geom_change_count = 0
        self.uniform_translation = False
        self.uniform_moved_arrows: set = set()
        self.moved_items: set = set()
        self.arrow_pos_snapshot: dict = {}

        # [2-H] 그룹 오버레이 캐시(core_shapes._GroupTransform._cache_key) 무효화 도장.
        self.sel_version = 0
        self.geom_version = 0

        self.scene._sel_count_cache = 0
        self.scene._sel_top_count_cache = 0
