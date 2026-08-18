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

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QGraphicsScene

from easycad.canvas.annotator_core import _AnnotatorView
from easycad.canvas.host_widgets import _SCENE_HALF, _UndoEntry


class CanvasDocument:
    """도면 하나(씬 + undo/redo + 레이어 + 저장경로 + 라우팅/성능 캐시)."""

    def __init__(self, window):
        self.scene = QGraphicsScene(window)
        self.scene.setSceneRect(-_SCENE_HALF, -_SCENE_HALF, 2 * _SCENE_HALF, 2 * _SCENE_HALF)
        self.scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        self.scene._owner_doc = self   # [§8 항목10] 씬 시그널 핸들러가 발신 문서를 역참조

        self.view = _AnnotatorView(self.scene, window)

        self.undo: list[_UndoEntry] = []
        self.redo: list[_UndoEntry] = []
        self.layers: list[dict] = [
            {"id": "default", "name": "기본", "visible": True, "locked": False}]
        self.doc_path: str | None = None
        self.dirty = False   # [§8 항목10 Stage C]
        self.untitled_n: int | None = None   # [§8 항목10 Stage B] host._create_doc()가 부여

        self.badge_n = 0
        self.paste_seq = 0
        self.pan_last: QPointF | None = None

        # 지속 연결 리라우팅 재진입 가드 + 드래그 중 미룬 화살표(host_canvas.py 참조).
        self.rerouting = False
        self.deferred_arrows: set = set()
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
