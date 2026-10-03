"""CanvasWindow 믹스인 — Undo/Redo 저널 — 스냅샷 push/apply, 되돌리기/다시실행.

2026-08-02 host.py(3635줄) 분할분. `class CanvasWindow(...)`이 이 믹스인들을 다중상속해
메서드를 합친다 — 동작·이름 전부 원본과 동일(이동만), annotator_core.py가 이미 쓰는 믹스인
패턴을 host.py에도 적용한 것.
"""
from __future__ import annotations


from PyQt6.QtCore import QPointF, QTimer

from easycad.canvas.annotator_core import (
    _ArrowItem, _PolyArrowItem, _ImageItem, _reposition_port_from_frac, arrow_end_indices,
    _GroupBindProxy,
)
from easycad.canvas.host_widgets import _ONESHOT_TOOLS, _UndoEntry

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




class _UndoMixin:
    def _reset_history(self):
        """[M2] 문서 교체(새로/열기/가져오기) 시 undo·redo 스택을 함께 비운다."""
        self._undo.clear()
        self._redo.clear()
        self._refresh_history_actions()
        # [2026-10-03] 개수는 기록이 쌓일 때 다시 세는데, 문서를 통째로 바꾸는 열기는 기록 없이
        # 도형을 넣는다 — DXF·PDF를 연 직후 「기본 (0)」으로 남던 것(.ecad는 레이어 복원이 따로 셈).
        self._schedule_layer_counts()


    def _push_entry(self, ops, key=None):
        """ops(연산 리스트)를 저널에 쌓는다. key가 직전 엔트리와 같으면 병합(연속 변이).
        새 변이가 실리면 redo 스택은 무효화된다(표준 undo 시맨틱)."""
        if not ops:
            return
        top = self._undo[-1] if self._undo else None
        if key is not None and top is not None and top.key == key:
            self._coalesce_into(top, ops)   # before 유지, after만 갱신
        else:
            self._undo.append(_UndoEntry(ops, key))
        self._redo.clear()
        if any(isinstance(o[1], _ImageItem) for o in ops):
            self._trim_history_images()   # [§8 항목35] 그림이 오갈 때만 검사(드묾)
        self._refresh_history_actions()
        self._mark_dirty()   # [§8 항목10 Stage C]
        self._schedule_layer_counts()   # 레이어 패널 「이름 (개수)」 갱신

    # [§8 항목35, 2026-10-03] 되돌리기 기록 상한 — 사용자 결정: 그림 메모리만 제한.
    # 실측: 도형 5만 개를 지워 쌓아도 +80MB, 한 도형 5,000번 이동 +4MB인데, 1,200만 화소 사진은
    # 넣었다 지우기 10번에 +458MB(장당 약 46MB). 그래서 기록만 붙잡고 있는(씬에 없는) 그림이
    # 이 값을 넘으면 가장 오래된 기록부터 버린다. 도형 작업은 지금처럼 끝까지 되돌릴 수 있다.
    _UNDO_IMAGE_BUDGET = 500 * 2**20

    def _history_image_bytes(self) -> int:
        seen, total = set(), 0
        for entry in list(self._undo) + list(self._redo):
            for o in entry.ops:
                it = o[1]
                if isinstance(it, _ImageItem) and id(it) not in seen and it.scene() is None:
                    seen.add(id(it))
                    pm = it._pixmap
                    total += pm.width() * pm.height() * 4
        return total

    def _trim_history_images(self):
        dropped = 0
        while len(self._undo) > 1 and self._history_image_bytes() > self._UNDO_IMAGE_BUDGET:
            self._undo.pop(0)   # 가장 오래된 기록 — 방금 쌓은 기록은 남긴다
            dropped += 1
        if dropped:
            self.statusBar().showMessage(
                f"지운 그림이 메모리를 많이 차지해 오래된 되돌리기 기록 {dropped}개를 정리했습니다", 5000)

    @staticmethod
    def _coalesce_into(entry, new_ops):
        """연속 변이 병합 — 같은 아이템·같은 sub의 mut는 before를 유지한 채 after만 갱신
        (예: Shift+휠 두께를 여러 번 굴려도 undo 1스텝). 그 외 op는 뒤에 덧붙인다."""
        index = {(id(o[1]), o[2]): i for i, o in enumerate(entry.ops)
                 if o[0] == "mut"}
        for o in new_ops:
            if o[0] == "mut" and (id(o[1]), o[2]) in index:
                i = index[(id(o[1]), o[2])]
                prev = entry.ops[i]
                entry.ops[i] = ("mut", o[1], o[2], prev[3], o[4])  # before 유지·after 갱신
            else:
                entry.ops.append(o)


    def push_undo_add(self, item):
        self._push_entry([("create", item)])
        self._maybe_oneshot_revert()


    def push_undo_add_many(self, items):
        """[2d] 여러 아이템(복제 도형+연결 화살표)을 한 번의 undo로 함께 제거."""
        self._push_entry([("create", it) for it in items])
        self._maybe_oneshot_revert()


    def _maybe_oneshot_revert(self):
        """[M2] 도형을 하나 커밋한 뒤 — pin이 꺼져 있고 지금 도구가 one-shot 대상이면
        선택모드로 되돌린다(그린 뒤 또 그려지는 오작동 차단). 진행 중 이벤트가 끝난 뒤
        적용하도록 singleShot(0)로 지연(현재 그리기 핸들러가 도구를 더 참조할 수 있으므로).
        붙여넣기·복제·빠른생성은 select 모드에서 일어나 여기 걸리지 않는다(가드)."""
        tool = self.current_tool
        armed = tool in _ONESHOT_TOOLS or (tool or "").startswith(("sym:", "customsym:"))
        if armed and not self.tool_pinned:
            QTimer.singleShot(0, lambda: self.set_tool("select"))


    def push_undo_delete(self, items, coalesce_key=None):
        """[2026-08-30] `coalesce_key`(선택) — TRIM 문지르기 드래그 전체를 undo 1스텝으로
        묶는 `_trim_undo_key`와 같은 패턴(`push_undo_cut`/`push_undo_open_trim` 참조).
        기존 호출부(Delete 키 등)는 인자를 안 넘겨 None(코얼레스 없음) 그대로 유지."""
        self._push_entry([("remove", it) for it in items], key=coalesce_key)


    def push_undo_move(self, pairs, coalesce_key=None):
        """`pairs`=(아이템, 이동 전 pos) — **이미 옮긴 뒤** 호출한다(after=현재 pos).
        [점검 2단계 2026-10-03, 사용자 결정] 연결된 화살표를 통째로 옮기면(드래그·방향키),
        같이 옮겨지지 않은 도형과의 연결은 푼다. 예전엔 연결된 채로 도형에서 떨어져 떠 있었고,
        나중에 그 도형이 다시 계산되면 끝점만 도형으로 끌려가 되돌리기 뒤 화살표가 상자 안으로
        파고드는 일이 생겼다(재현: 연결 화살표 이동→상자 삭제→전부 되돌리기). 연결 풀기는 같은
        undo 단계에 'geom'(pos 포함 스냅샷)으로 실어 한 번에 되돌아간다."""
        moved = {it for it, _old in pairs}
        moved_gids = {g for g in (getattr(it, "_group_id", None) for it in moved) if g}
        top = (self._undo[-1] if coalesce_key is not None and self._undo
               and self._undo[-1].key == coalesce_key else None)
        ops = []
        for it, old in pairs:
            left = [idx for idx in arrow_end_indices(it)
                    if self._left_behind(it._bound(idx), moved, moved_gids)]
            # 연속 방향키(코얼레스)에서 첫 번에 geom으로 실렸으면 계속 geom으로 — 그래야 병합된다
            had_geom = top is not None and any(
                o[0] == "mut" and o[1] is it and o[2] == "geom" for o in top.ops)
            if left or had_geom:
                before = it.capture_geom()
                before["pos"] = QPointF(old)
                for idx in left:
                    it.set_bound(idx, None)
                ops.append(("mut", it, "geom", before, it.capture_geom()))
            else:
                ops.append(("mut", it, "pos", QPointF(old), QPointF(it.pos())))
        self._push_entry(ops, key=coalesce_key)

    @staticmethod
    def _left_behind(host, moved, moved_gids) -> bool:
        """화살표 끝이 붙은 host가 이번 이동에 같이 안 옮겨졌나(포트처럼 자식이면 조상까지 본다)."""
        if host is None:
            return False
        if isinstance(host, _GroupBindProxy):
            return host.group_id not in moved_gids
        x = host
        while x is not None:
            if x in moved:
                return False
            x = x.parentItem()
        return True


    def push_undo_xform(self, snaps):
        """[우리 확장] 그룹 변형(회전·스케일) 되돌리기 — 변형 전 pos/rotation/scale/origin 스냅샷.
        push_undo_move가 위치만 복원하는 것과 달리 회전·스케일까지 통째로 되돌린다."""
        self._push_entry([
            ("mut", it, "xform", (QPointF(pos), rot, scale, QPointF(org)),
             (QPointF(it.pos()), it.rotation(), it.scale(),
              QPointF(it.transformOriginPoint())))
            for it, pos, rot, scale, org in snaps])


    def push_undo_geom(self, snaps, coalesce_key=None):
        """[Stage2] 기하 리베이크(비균일 스케일·미러) 되돌리기 — capture_geom 토큰 스냅샷.
        xform과 달리 기하 자체(rect/끝점/정점/패스)+바인딩까지 통째로 복원한다.
        coalesce_key가 있으면 연속 조작(반경 스테퍼 등)을 undo 1스텝으로 병합한다."""
        self._push_entry([
            ("mut", it, "geom", before, it.capture_geom()) for it, before in snaps],
            key=coalesce_key)


    def push_undo_state(self, snaps, coalesce_key=None):
        """[M2] 속성·라벨 변경(색·두께·선스타일·폰트·텍스트) — before=capture_state 스냅샷
        (변경 전), after=현재. 저널의 'state' mut로 실려 되돌리기/다시 실행된다."""
        self._push_entry(
            [("mut", it, "state", before, it.capture_state()) for it, before in snaps],
            key=coalesce_key)


    def push_undo_cut(self, host, before_cuts, coalesce_key=None):
        """[§8 항목17 6단계] 닫힌 도형 TRIM(cut 구간 추가) 되돌리기 — `host._cuts`는
        `capture_geom()`이 안 건드리는 별도 속성이라(리사이즈 등 기존 geom mut과 개념이
        다름 — cut은 리사이즈로 안 지워져야 하므로) `group`(`_group_id`)과 같은 전용
        `mut` sub("cuts")를 하나 더 둔다. coalesce_key를 문지르기 드래그 세션과 공유하면
        `_coalesce_into`가 같은 host의 연속 cut을 "드래그 시작 전 before" 하나로 병합해
        Ctrl+Z 한 번에 그 드래그 전체가 되돌아간다(`push_undo_move`와 같은 패턴)."""
        self._push_entry(
            [("mut", host, "cuts", list(before_cuts),
              list(getattr(host, "_cuts", None) or []))],
            key=coalesce_key)


    def push_undo_open_trim(self, host, before_geom, clone=None, coalesce_key=None):
        """[§8 항목17 6단계] 열린 도형(_LineItem/_PolyArrowItem) TRIM 분리·EXTEND 되돌리기 —
        host 기하(+바인딩, 이미 `capture_geom()`/`apply_geom()`이 pts·auto_route·바인딩까지
        전부 포괄) mut 스냅샷과, 분리로 새로 생긴 clone(있으면)의 `create`를 한 엔트리로
        묶는다(그룹 복제가 여러 아이템을 한 undo로 묶는 `push_undo_add_many`와 같은 다중 op
        패턴) — Ctrl+Z 한 번에 host 복원 + clone 제거가 함께 일어난다. EXTEND는 clone이
        없으므로 host mut 하나짜리 엔트리가 된다."""
        ops = [("mut", host, "geom", before_geom, host.capture_geom())]
        if clone is not None:
            ops.append(("create", clone))
        self._push_entry(ops, key=coalesce_key)


    def _apply_mut(self, it, sub, tok):
        """mut op의 sub별 복원 — undo는 before, redo는 after 토큰을 그대로 넘긴다."""
        if sub == "pos":
            it.setPos(tok)
        elif sub == "xform":
            pos, rot, scale, org = tok
            it.setTransformOriginPoint(org)
            it.setRotation(rot)
            it.setScale(scale)
            it.setPos(pos)
        elif sub == "geom":
            # 기하+바인딩 통째 복원 — apply_geom만으로 일관 복원(reroute 불필요).
            it.apply_geom(tok)
        elif sub == "state":
            it.apply_state(tok)
        elif sub == "z":
            it.setZValue(tok)
        elif sub == "group":
            it._group_id = tok
        elif sub == "cuts":
            it._cuts = list(tok)
            it.update()
        elif sub == "lock":
            self._set_item_lock_flags(it, tok)
        elif sub == "layer":
            it._layer_id = tok
            self._sync_item_to_layer_state(it)   # undo/redo도 옮긴 레이어의 표시/잠금을 물려받음
            if hasattr(self, "_layers_list"):
                self._refresh_layers_panel()


    def _reattach_port_if_needed(self, it):
        """[신규기능 §8-12] `scene.addItem()`은 Qt parentItem을 None으로 초기화한다(실측
        확인) — 포트(장비의 Qt 자식)를 undo/redo로 되살릴 때마다 원래 호스트에 다시
        `setParentItem`하고 상대위치(fx,fy)로 재배치 + 호스트의 `_ports` 목록에도 재등록한다."""
        host = getattr(it, "_port_host", None)
        if host is None:
            return
        it.setParentItem(host)
        _reposition_port_from_frac(it)
        ports = getattr(host, "_ports", None)
        if ports is None:
            ports = host._ports = []
        if it not in ports:
            ports.append(it)
        host.update()   # rect·pos는 안 바뀌므로 Qt가 자동으로 재도장하지 않는다.

    def _detach_port_if_needed(self, it):
        """포트를 씬에서 제거하기 전, 호스트의 `_ports` 목록에서 먼저 빼둔다(trim 렌더링이
        더 이상 존재하지 않는 포트를 참조하지 않도록)."""
        host = getattr(it, "_port_host", None)
        if host is None:
            return
        ports = getattr(host, "_ports", None)
        if ports and it in ports:
            ports.remove(it)
            host.update()

    def _apply_entry(self, entry, redo):
        revived = []   # [점검 2단계] 되살린 아이템 — 아래에서 원래 겹침 순서로 되돌린다
        for op in entry.ops:
            kind = op[0]
            if kind == "create":
                it = op[1]
                if redo:
                    if it.scene() is None:
                        self._scene.addItem(it)
                        self._reattach_port_if_needed(it)
                        revived.append(it)
                elif it.scene() is not None:
                    self._detach_port_if_needed(it)
                    self._scene.removeItem(it)
            elif kind == "remove":
                it = op[1]
                if redo:
                    if it.scene() is not None:
                        self._detach_port_if_needed(it)
                        self._scene.removeItem(it)
                elif it.scene() is None:
                    self._scene.addItem(it)
                    self._reattach_port_if_needed(it)
                    revived.append(it)
            elif kind == "mut":
                _, it, sub, before, after = op
                self._apply_mut(it, sub, after if redo else before)
        # [점검 2단계 2026-10-03] 다 되살린 뒤에 한꺼번에 — 같이 지워졌던 위쪽 아이템이 아직
        # 안 돌아왔을 수 있어 순서와 무관하게 하려고 두 번째 패스로 둔다(_DocScene 주석 참조).
        self._restack_revived([it for it in revived if it.parentItem() is None])
        # [점검 2단계 후속] 되살린 화살표는 지워질 때의 경로를 그대로 가졌다 — 다음 재라우팅 1회 제외
        self._active_doc.skip_reroute_once.update(
            it for it in revived if isinstance(it, (_ArrowItem, _PolyArrowItem)))

    @staticmethod
    def _restack_revived(items):
        """[점검 2단계 2026-10-03] 되살린 최상위 아이템들을 지울 때 기록한 위/아래 이웃
        (`_DocScene.removeItem`)대로 다시 쌓는다. ① 되살린 것끼리 위아래 관계로 위→아래 순서를
        정하고 ② 위에서부터 차례로: 기록한 위쪽 이웃 중 지금 씬에 있는 첫 아이템 바로 아래로,
        그런 이웃이 없으면(같이 지워져 기록이 비었으면) 바로 앞에 놓은 되살린 아이템 아래로."""
        if not items:
            return
        rev = set(items)
        above = {it: [a for a in (getattr(it, "_restack_above", None) or ())] for it in items}
        below = {it: [b for b in (getattr(it, "_restack_below", None) or ())] for it in items}
        over = {it: set() for it in items}   # over[x] = x보다 위에 있어야 하는 되살린 아이템
        for it in items:
            for a in above[it]:
                if a in rev and a is not it:
                    over[it].add(a)
            for b in below[it]:
                if b in rev and b is not it:
                    over[b].add(it)
        # 위→아래 순서(Kahn) — 이웃 기록이 아이템당 최대 8개라 거의 선형(예전 구현은 매번 남은
        # 목록 전체를 훑어 1000개 되돌리기에 ~1초가 더 들었다)
        under = {it: [] for it in items}   # under[a] = a 바로 아래에 와야 하는 되살린 아이템들
        need = {it: len(over[it]) for it in items}
        for it in items:
            for a in over[it]:
                under[a].append(it)
        queue = [it for it in items if need[it] == 0]
        order, qi = [], 0
        while qi < len(queue):
            a = queue[qi]; qi += 1
            order.append(a)
            for b in under[a]:
                need[b] -= 1
                if need[b] == 0:
                    queue.append(b)
        if len(order) < len(items):   # 순환(이론상 없음) — 남은 것은 원래 순서대로 뒤에
            placed_set = set(order)
            order += [it for it in items if it not in placed_set]
        placed = set()
        prev = None
        for it in order:
            tgt = next((a for a in above[it]
                        if a.scene() is it.scene() and a.parentItem() is None
                        and (a not in rev or a in placed)), None)
            if tgt is None:
                tgt = prev
            if tgt is not None:
                it.stackBefore(tgt)
            placed.add(it)
            prev = it


    def undo(self):
        if not self._undo:
            return
        entry = self._undo.pop()
        with self._bulk_scene_edit():   # [점검 2단계 후속] 대량 되살리기 O(n²) 방지
            self._apply_entry(entry, redo=False)
        self._redo.append(entry)
        self._refresh_history_actions()
        self._schedule_layer_counts()
        self._mark_dirty()   # [§8 항목10 Stage C] — 저장 후 되돌리기도 다시 dirty
        self._repaint_overlays()   # 되돌리기도 프로그램 이동 — 그룹 박스 잔상 방지


    def redo(self):
        if not self._redo:
            return
        entry = self._redo.pop()
        with self._bulk_scene_edit():
            self._apply_entry(entry, redo=True)
        self._undo.append(entry)
        self._refresh_history_actions()
        self._schedule_layer_counts()
        self._mark_dirty()   # [§8 항목10 Stage C]
        self._repaint_overlays()   # 다시 실행도 마찬가지


    def _refresh_history_actions(self):
        """undo/redo 툴바 액션의 활성 상태를 스택 유무에 맞춘다(빈 스택=disabled)."""
        act_u = getattr(self, "_act_undo", None)
        act_r = getattr(self, "_act_redo", None)
        if act_u is not None:
            act_u.setEnabled(bool(self._undo))
        if act_r is not None:
            act_r.setEnabled(bool(self._redo))

    # 복사 / 연속 붙여넣기
