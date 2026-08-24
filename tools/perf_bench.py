"""[성능 최적화 2026-08-08, 0단계 안전망] 밀집 도면 상호작용 성능 자동 측정 하네스.

목적: "버벅인다"를 **프레임당 ms**라는 검증 가능한 수치로 바꾼다(전역 규칙 9). 성능 수정
전후로 이 스크립트를 돌려 개선을 숫자로 증명하고, `tools/perf_baseline_check.py`가 같은
수정이 **그림을 바꾸지 않았음**을 따로 증명한다(둘은 짝 — 하나만으로는 부족).

측정 대상은 사용자가 실제로 버벅임을 느끼는 상호작용 전부:
    load / settle / select / drag / drag_multi / zoom / pan / render / render_fit
    + 외부 도면 가져오기(dxf_export → dxf_import 왕복, svg_import)

⚠ offscreen(`QT_QPA_PLATFORM=offscreen`)으로 측정한다. 절대 ms는 실화면과 다를 수 있으나
   **수정 전후 비교**가 목적이라 상대값이면 충분하다(전역 규칙 11-c: 프록시 검증).
   실조건 체감은 `python run.py`로 사용자가 따로 확인한다.

⚠⚠ **2026-08-15 측정 방법론 수정 — 이 날 이전에 기록된 절대 ms와는 비교 불가.**
`docs/perf_plan_500_1000.md` 1-0에서 하네스 자체를 검증하다 결함 3개를 찾았다(실측 근거는
그 문서 §5). 고치기 전 수치는 **실제보다 크게 낙관적**이었다:

  1. **줌을 통제하지 않았다** — 기본 줌에선 문서 대부분이 뷰포트 밖이라 페인트가 거의 안 돌았다
     (도형 250개 드래그에 paint 8회/프레임). 사용자는 전체를 선택하려면 축소해서 보므로
     그게 진짜 조건이다. → `--zoom fit`(기본값)으로 문서 전체가 화면에 들어오게 고정.
  2. **`processEvents()` 한 번으론 프레임을 건너뛴다** — Qt가 페인트를 합쳐버려 실제 렌더
     비용이 빠졌다(도형 250개가 움직였는데 paint는 125회뿐). → 프레임형 시나리오는
     `processEvents()`를 여러 번 돌려 밀린 페인트를 정지 상태까지 흘려보낸다
     (`_paint_tick` 주석에 세 방식 실측 비교). `viewport().repaint()`는 더티 영역과 무관하게
     뷰포트 전체를 다시 그려 **부분 드래그를 과대측정**하므로 쓰지 않는다.
  3. **워밍업·반복 없이 단발 평균** — 첫 프레임의 지연 초기화가 섞이고 노이즈에 취약했다
     (같은 코드로 6%와 20% 개선이 둘 다 나온 전례). → 워밍업 후 **best-of-N**.

사용법:
    python tools/perf_bench.py                          # 기본 문서로 전 시나리오
    python tools/perf_bench.py --doc perf_1000.ecad     # (tools/make_perf_doc.py로 생성)
    python tools/perf_bench.py --no-minimap             # 미니맵 기여도 분리
    python tools/perf_bench.py --zoom current           # 옛 방식(문서 일부만 화면) 재현용
    python tools/perf_bench.py --trials 7               # best-of-N 횟수(기본 5)
    python tools/perf_bench.py --save before.json       # 결과 저장
    python tools/perf_bench.py --compare before.json    # 저장분 대비 증감 표시
    python tools/perf_bench.py --only drag,select       # 일부만
"""
import argparse
import json
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 표가 한글 라벨이라 콘솔이 cp949면 깨진다 — 출력 스트림만 UTF-8로 돌린다(측정과 무관).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import _RectItem, _ArrowItem, _PolyArrowItem
from easycad.fileio.document import load_document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DOC = os.path.join(ROOT, "heavy_perf_test.ecad")
FRAME_BUDGET_MS = 1000.0 / 60.0   # 16.67ms — 60fps 예산. 이걸 넘으면 사용자가 버벅임을 느낀다.
VIEW_W, VIEW_H = 1400, 900

# 시나리오별 '한 번'의 의미 — 표에 단위를 정확히 찍기 위한 메타.
# frame=True면 60fps 예산과 비교(프레임당 비용), False면 1회성 작업(로드 등).
SCENARIOS = {
    "load":        ("`.ecad` 로드",            False),
    "settle":      ("로드 후 정착",            False),
    "select":      ("도형 선택 클릭",          True),
    "drag":        ("도형 1개 드래그",         True),
    "drag_multi":  ("20개 그룹 드래그",        True),
    "drag_all":    ("전체 선택 그룹 드래그",    True),
    "drag_subset": ("큰 씬 / 30개만 드래그",   True),
    "rubberband":  ("러버밴드 드래그 중",      True),
    "release":     ("놓는 순간 일괄 정리",     False),
    "zoom":        ("휠 줌 1틱",               True),
    "pan":         ("팬 1프레임",              True),
    "render":      ("뷰 렌더(현재 줌)",        True),
    "render_fit":  ("뷰 렌더(전체 축소)",      True),
    "dxf_export":  ("DXF 내보내기",            False),
    "dxf_import":  ("DXF 가져오기",            False),
    "svg_import":  ("SVG 심볼 6종 파싱",       False),
}


class Bench:
    """측정 컨텍스트 — 창 1개를 만들어 시나리오들을 순서대로 돌린다."""

    def __init__(self, doc_path: str, hide_minimap: bool, trials: int = 5, zoom: str = "fit"):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.doc_path = doc_path
        self.trials = max(1, trials)
        self.zoom_mode = zoom
        self.results: dict[str, float] = {}
        self.win = CanvasWindow()
        self.win.resize(VIEW_W, VIEW_H)
        self.win.show()
        self.app.processEvents()
        if hide_minimap:
            self._hide_minimap()
        self.img = QImage(VIEW_W, VIEW_H, QImage.Format.Format_ARGB32)

    def _hide_minimap(self):
        """미니맵 기여도 분리용 — 위젯과 그 부모 패널까지 숨겨 paintEvent 자체를 막는다.
        (`hide()`만으로 Qt가 repaint를 안 보내는 것을 이용 — 코드는 안 건드림.)"""
        mm = getattr(self.win, "_minimap", None)
        panel = getattr(self.win, "_minimap_panel", None)
        for wgt in (mm, panel):
            if wgt is not None:
                wgt.hide()
        self.app.processEvents()

    # ---- 측정 원시도구 -----------------------------------------------------

    def _tick(self):
        self.app.processEvents()

    _PAINT_FLUSH = 3

    def _paint_tick(self):
        """[2026-08-15] 프레임형 시나리오 전용 — 밀린 페인트를 **정지 상태까지 흘려보낸다**.

        세 방식을 실측해 고른 것이다(도형 250 + 화살표 250 문서, fit 줌, `_RectItem.paint` 계수):

            방식                이동 1개      이동 250개(전체)
            processEvents x1    paint  54      paint 125   ← 250개가 움직였는데 125회뿐(누락)
            processEvents x3    paint 108      paint 250   ← 이동분과 정확히 일치
            viewport().repaint() paint 304     paint 375   ← 1개만 움직여도 전체 재도색(과대)

        `repaint()`는 더티 영역과 무관하게 뷰포트 전체를 다시 그려, 부분 드래그의 렌더 비용을
        실제보다 크게 부풀린다(실사용에선 Qt가 더티 영역만 그린다). `processEvents()` 한 번은
        반대로 페인트를 합쳐 누락한다. 세 번 돌리면 Qt의 정상 더티 전파를 그대로 쓰면서
        큐에 남은 페인트까지 소진돼, 이동한 만큼만 정확히 그려진다."""
        for _ in range(self._PAINT_FLUSH):
            self.app.processEvents()

    def apply_zoom(self):
        """[2026-08-15] 줌 상태를 명시적으로 고정한다 — 이걸 안 하면 문서 크기·기본 줌에 따라
        화면 밖 도형이 페인트를 건너뛰어 같은 코드가 문서마다 다른 결론을 낸다.
        `fit` = 문서 전체가 화면에(전체선택 드래그의 실제 조건), `current` = 옛 방식."""
        if self.zoom_mode == "fit":
            rect = self.win._scene.itemsBoundingRect()
            if not rect.isEmpty():
                self.win._view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._tick()

    def visible_shape_count(self) -> int:
        """현재 뷰포트 안에 실제로 들어온 도형 수 — 측정이 무엇을 재고 있는지 표에 찍는다."""
        vp = self.win._view.viewport().rect()
        n = 0
        for it in self._rects():
            if vp.intersects(self.win._view.mapFromScene(it.sceneBoundingRect()).boundingRect()):
                n += 1
        return n

    def begin_drag(self):
        """[성능계획 2-B, 2026-08-15] 실제 드래그 수명주기를 흉내낸다.
        예전 시나리오는 `setPos`만 불러 press~release 상태를 만들지 않았다 — 그래서
        '드래그 중에만' 켜지는 최적화(2-B 재라우팅 지연 등)가 벤치에선 아예 발동하지 않아
        효과가 0%로 나왔다(실제 앱에선 발동함). 실사용과 같은 상태를 만들어야 측정이 맞다.

        [성능계획 2-D, 2026-08-15] 같은 이유로 드래그 프록시 진입점도 여기서 부른다 —
        실제 앱은 `mouseMoveEvent`가 이걸 부르는데 벤치는 마우스 이벤트를 안 흘리므로,
        안 부르면 2-D가 벤치에서만 통째로 발동하지 않아 "효과 0%"를 또 찍게 된다."""
        self.win._view._move_active = True
        self.win._view._ensure_drag_proxy()

    def end_drag(self):
        """놓는 순간 — 실제 `mouseReleaseEvent`가 finally에서 부르는 그 함수를 그대로 쓴다
        (드래그 세션 해제 + 프록시 복원 + 미뤄둔 재라우팅 flush + 리페인트). 여기서 별도
        구현을 흉내내면 실사용 경로와 조용히 어긋난다."""
        self.win._view._end_drag_session()
        self._tick()

    def begin_pan(self):
        """[성능 후속 2026-08-24] 팬 진입 상태를 흉내낸다 — `begin_drag`와 같은 이유다.
        실제 앱은 `mouseMoveEvent`가 매번 `_ensure_drag_proxy()`를 부르는데, 그 게이트가
        보는 `_pan_last`(호스트 팬 상태)는 이제 팬도 프록시 대상으로 잡으므로(`core_view.
        _is_panning`), 마우스 이벤트를 안 흘리는 이 벤치도 그 상태를 직접 세워야 프록시가
        켜진 채로 재진다 — 안 하면 이 수정의 효과가 벤치에서만 0%로 찍힌다."""
        self.win._win_drag_start(QPointF(0, 0))
        self.win._view._ensure_drag_proxy()

    def end_pan(self):
        """팬 종료 — 실제 `mouseReleaseEvent`가 부르는 정리 경로 그대로(`_end_drag_session`
        이 프록시 해제까지 겸한다) + `_pan_last` 해제."""
        self.win._win_drag_end()
        self.win._view._end_drag_session()
        self._tick()

    def drag_reset(self, snap):
        """드래그 시나리오용 reset — 세션을 끝내 미룬 것을 정리한 뒤 배치를 복원하고 다시 시작."""
        self.end_drag()
        self.restore_positions(snap)
        self.begin_drag()

    def snapshot_positions(self):
        """씬 아이템들의 현재 위치를 저장 — 시나리오 간 간섭 차단용(아래 `_time` 참조)."""
        return [(it, QPointF(it.pos())) for it in self.win._scene.items()
                if it.parentItem() is None]

    def restore_positions(self, snap):
        for it, pos in snap:
            if it.pos() != pos:
                it.setPos(pos)
        self.win._on_scene_changed(None)      # 되돌린 배치로 라우팅도 원상복구
        self._tick()

    def _time(self, key: str, reps: int, fn, frame: bool = True, reset=None):
        """[2026-08-15 방법론 수정] 워밍업 후 **best-of-N**을 기록한다.

        예전엔 워밍업 없이 한 번만 돌려 평균을 냈다 — 첫 프레임의 지연 초기화(캐시 콜드,
        Qt 내부 할당)가 섞이고 배경 노이즈에 그대로 노출돼, 같은 코드 변경을 두고 6%와
        20%가 둘 다 나오는 일이 실제로 있었다. 최소값을 쓰는 이유: 성능 측정에서 노이즈는
        항상 **더 느린 쪽으로만** 작용하므로 최소값이 참값에 가장 가깝다.

        ⚠ **`reset`이 없으면 이 하네스는 거짓말을 한다**(2026-08-15 실측으로 발견).
        드래그 시나리오는 도형을 실제로 옮긴 채 끝난다. 그래서 ⓐ 다음 시나리오가 어긋난
        배치에서 시작하고 ⓑ best-of-N의 각 시도가 **서로 다른 배치**를 재게 된다 — 노이즈
        제거가 아니라 '가장 싼 배치 고르기'가 된다. 특히 일부만 옮기면 도형이 서로 겹쳐
        A* 라우팅이 급등해, 30개 드래그(504ms)가 250개 전체 드래그(197ms)보다 느리다는
        물리적으로 불가능한 결과가 나왔다. `reset`은 매 시도 **직전**에 원래 배치로 되돌려
        모든 시도가 같은 일을 재게 한다.
        """
        warm = 2 if frame else 1
        if reset:
            reset()
        for i in range(warm):
            fn(i)
        best = None
        for _ in range(self.trials):
            if reset:
                reset()
            t0 = time.perf_counter()
            for i in range(reps):
                fn(i)
            dt = (time.perf_counter() - t0) * 1000.0 / max(reps, 1)
            best = dt if best is None else min(best, dt)
        if reset:
            reset()                            # 다음 시나리오를 위해 원상복구
        self.results[key] = best
        return best

    # ---- 시나리오 ----------------------------------------------------------

    def scn_load(self):
        t0 = time.perf_counter()
        load_document(self.win._scene, self.doc_path)
        self.results["load"] = (time.perf_counter() - t0) * 1000.0
        # 로드 직후 예약된 scene.changed(바인딩 정규화 reroute의 지연 신호)는 두 번째 틱에야
        # 전달된다 — 실사용에선 클릭이 도착하기 훨씬 전 소진되는 1회성 비용이라, 이후 시나리오에
        # 섞이지 않게 여기서 따로 재고 흘려보낸다(tools/profile_reroute.py와 같은 근거).
        t0 = time.perf_counter()
        self._tick()
        self._tick()
        self.results["settle"] = (time.perf_counter() - t0) * 1000.0

    def scn_select(self):
        rects = self._rects()
        def one(i):
            self.win._scene.clearSelection()
            rects[i % len(rects)].setSelected(True)
            self._paint_tick()
        self._time("select", 10, one)

    def scn_drag(self):
        snap = self.snapshot_positions()
        r = self._rects()[0]
        self.win._scene.clearSelection()
        r.setSelected(True)
        self._tick()
        # 실제 드래그와 같은 경로: setPos → scene.changed → reroute/repaint 체인 전부 탄다.
        def one(i):
            r.setPos(r.pos() + QPointF(3, 2))
            self._paint_tick()
        self._time("drag", 20, one, reset=lambda: self.drag_reset(snap))
        self.end_drag()
        self.win._scene.clearSelection()
        self._tick()

    def scn_drag_multi(self):
        snap = self.snapshot_positions()
        rects = self._rects()[:20]
        self.win._scene.clearSelection()
        for r in rects:
            r.setSelected(True)
        self._tick()
        def one(i):
            for r in rects:
                r.setPos(r.pos() + QPointF(2, 1))
            self._paint_tick()
        self._time("drag_multi", 10, one, reset=lambda: self.drag_reset(snap))
        self.end_drag()
        self.win._scene.clearSelection()
        self._tick()

    def scn_drag_all(self):
        """[성능조사 2026-08-13] drag_multi(20개 고정)는 200개+ 선택 규모를 재현하지 못한다 —
        문서에 있는 도형 전부를 선택해 한 번에 옮겨, 선택 개수 자체가 큰 시나리오를 잡는다."""
        snap = self.snapshot_positions()
        rects = self._rects()
        self.win._scene.clearSelection()
        for r in rects:
            r.setSelected(True)
        self._tick()
        def one(i):
            for r in rects:
                r.setPos(r.pos() + QPointF(2, 1))
            self._paint_tick()
        self._time("drag_all", 10, one, reset=lambda: self.drag_reset(snap))
        self.end_drag()
        self.win._scene.clearSelection()
        self._tick()

    def scn_drag_subset(self):
        """[성능계획 1-0, 2026-08-15] 결정 ⓒ — **씬은 크고 선택은 작은** 경우.
        `drag_all`은 씬 규모와 선택 규모가 같아 둘을 분리할 수 없다(`docs/perf_group_drag_200.md`가
        "별도 문서로 재실측해야 확정된다"고 남겨둔 항목). 실사용 빈도는 이쪽이 더 높다 —
        큰 도면을 열어놓고 그중 몇십 개만 옮긴다. 여기서 비싼 게 남으면 그건 **선택 개수와
        무관하게 씬 전체에 비례하는 비용**(매 프레임 씬 순회 등)이라는 뜻이다."""
        snap = self.snapshot_positions()
        rects = self._rects()
        if len(rects) < 40:
            return                      # 씬이 작으면 '씬≫선택'이 성립 안 함 — 측정 스킵
        subset = rects[:30]
        self.win._scene.clearSelection()
        for r in subset:
            r.setSelected(True)
        self._tick()
        def one(i):
            for r in subset:
                r.setPos(r.pos() + QPointF(2, 1))
            self._paint_tick()
        self._time("drag_subset", 10, one, reset=lambda: self.drag_reset(snap))
        self.end_drag()
        self.win._scene.clearSelection()
        self._tick()

    def scn_rubberband(self):
        """[성능계획 1-0] 러버밴드로 영역을 끄는 **동안**의 비용(선택 확정 전).
        `drawForeground`가 매 프레임 후보들을 훑어 미리보기 강조를 그리는 경로라
        아이템 `paint()`와 별개다(옛 병목 C). 뷰의 실제 진행 상태를 그대로 세팅해 잰다."""
        v = self.win._view
        rect = self.win._scene.itemsBoundingRect()
        self.win._scene.clearSelection()
        self._tick()
        # 실제 mouseMove 경로(core_view.py `_rb_active` 분기)와 같은 상태를 만든다:
        #   _rb_current 갱신 → _rb_preview = _rb_preview_hits() → 화면 갱신.
        v._rb_active = True
        v._rb_origin = v.mapFromScene(rect.topLeft())
        def one(i):
            # 밴드를 조금씩 키우며 끈다 — 후보 수가 점점 늘어나는 실제 조작과 같은 모양.
            frac = 0.2 + 0.8 * ((i % 10) + 1) / 10.0
            v._rb_current = v.mapFromScene(QPointF(rect.left() + rect.width() * frac,
                                                   rect.top() + rect.height() * frac))
            v._rb_preview = v._rb_preview_hits()
            self._paint_tick()
        self._time("rubberband", 10, one)
        v._rb_active = False
        v._rb_origin = v._rb_current = None
        v._rb_preview = set()
        self._tick()

    def scn_release(self):
        """[성능계획 1-0 → 2-B로 정의 갱신] 드래그를 **놓는 순간**만의 비용(결정 ⓑ 0.5초 상한).

        ⚠ 측정 구간이 정확히 '릴리스'여야 한다. 드래그 프레임까지 한 덩어리로 재면 그 비용이
        섞여 상한 판정이 무의미해진다(실제로 처음엔 그렇게 재서 819ms가 나왔다). 그래서
        **이동은 `reset`(타이밍 밖)에서 해 두고, 타이밍 안에서는 `end_drag()`만** 부른다 —
        `end_drag`가 곧 실제 mouseReleaseEvent가 하는 일(미룬 재라우팅 flush)이다."""
        snap = self.snapshot_positions()
        # ⚠ **부분 선택**으로 잰다. 전체를 함께 옮기면 도형·화살표가 같은 델타라 강체
        # 평행이동으로 처리돼 A*가 애초에 안 돈다 — 미룰 일이 없어 릴리스가 공짜로 나오고
        # (실측 8.8ms) 예산 판정이 무의미해진다. 실제로 밀린 A*가 쌓이는 건 경계를 넘는
        # 화살표가 생기는 부분 선택이고, 0.5초 상한은 그 최악을 견디는지 보려는 것이다.
        rects = self._rects()[:30]
        self.win._scene.clearSelection()
        for r in rects:
            r.setSelected(True)
        self._tick()
        def prime():
            # 타이밍 밖: 배치를 되돌리고, 드래그 세션 안에서 옮겨 '미뤄진 상태'를 만든다.
            self.end_drag()
            self.restore_positions(snap)
            self.begin_drag()
            for r in rects:
                r.setPos(r.pos() + QPointF(1, 1))
            self._paint_tick()

        def one(i):
            self.end_drag()          # = 실제 릴리스(미룬 재라우팅 flush)
            self._paint_tick()
        self._time("release", 1, one, frame=False, reset=prime)
        # ⚠ [하네스 오염 수정 2026-08-15, 2-D] `_time`은 마지막에 `reset()`을 한 번 더 부르는데
        # 여기서 그 reset은 `prime()`이고, prime의 끝은 `begin_drag()`다 — 즉 이 시나리오는
        # **드래그 세션을 켠 채로** 끝나고 있었다. 다른 드래그 시나리오는 전부 뒤에
        # `end_drag()`가 있는데 여기만 빠져 있어서, 뒤따르는 zoom/pan/render 시나리오가
        # "드래그 중"으로 측정됐다(2-C 장식 억제·2-D 프록시가 켜진 화면 = 실제보다 싼 값).
        # 다른 드래그 시나리오와 같은 뒷정리를 붙인다.
        self.end_drag()
        self.win._scene.clearSelection()
        self._tick()

    def scn_zoom(self):
        # [2026-08-24] in/out 교대라 트라이얼 내부에서는 거의 상쇄되지만, 다른 프레임형
        # 시나리오와 관례를 맞추기 위해(그리고 부동소수 누적오차 방지) 트라이얼 사이에도
        # 원래 변환으로 되돌린다.
        xf0 = self.win._view.transform()
        def reset():
            self.win._view.setTransform(xf0)
            self._tick()
        def one(i):
            self.win._on_wheel_zoom(120 if i % 2 == 0 else -120)
            self._tick()
        self._time("zoom", 20, one, reset=reset)

    def scn_pan(self):
        """팬은 스크롤바 값 직접 조작으로 구현돼 있다(core_view 주석 참조) — 같은 경로로
        흉내낸다.

        [2026-08-24 방법론 수정] `reset` 없이 20스텝 × trial을 계속 이어 붙이면 스크롤
        위치가 시도마다 누적 이동해 콘텐츠 밖(빈 캔버스)까지 벗어날 수 있다 — best-of-N이
        "가장 먼저 빈 화면에 닿은 시도"를 고르는 셈이라 실제보다 낙관적인 값이 나온다
        (사용자 실사용 보고로 발견: 이 버그가 있는 채로는 1000개 문서에서 "OK"가 찍혔지만,
        매 스텝 콘텐츠 안에 머무는 sustained 측정은 60fps 예산의 4배 이상이었다). 드래그
        시나리오(`drag_reset`)와 같은 관례로 시도 전 원위치로 되돌린다.

        [같은 수정, 팬 프록시 반영] 팬도 이제 드래그 프록시 대상이다(`core_view.
        _is_panning`, 2026-08-24) — `begin_pan`/`end_pan`으로 실제 진입 상태를 세운다."""
        hb = self.win._view.horizontalScrollBar()
        vb = self.win._view.verticalScrollBar()
        h0, v0 = hb.value(), vb.value()
        def reset():
            self.end_pan()
            hb.setValue(h0)
            vb.setValue(v0)
            self.begin_pan()
        def one(i):
            hb.setValue(hb.value() + 7)
            vb.setValue(vb.value() + 5)
            self._tick()
        self._time("pan", 20, one, reset=reset)
        self.end_pan()

    def scn_render(self):
        def one(i):
            p = QPainter(self.img)
            self.win._view.render(p)
            p.end()
        self._time("render", 5, one)

    def scn_render_fit(self):
        # 사용자가 도면 전체를 보려고 축소한 상태 = 1600개가 전부 화면에 있는 최악의 렌더.
        self.win._view.fitInView(self.win._scene.itemsBoundingRect(),
                                 Qt.AspectRatioMode.KeepAspectRatio)
        self._tick()
        def one(i):
            p = QPainter(self.img)
            self.win._view.render(p)
            p.end()
        self._time("render_fit", 5, one)

    def scn_dxf_roundtrip(self, tmp_dir: str):
        """외부 도면 가져오기 경로 — 전용 DXF 샘플이 없으므로 현재 씬을 내보낸 뒤 다시 읽는다.
        1600엔티티짜리 실제 왕복이라 가져오기 스트레스 샘플로 충분하다."""
        from easycad.fileio.dxf_export import export_dxf
        from easycad.fileio.dxf_import import import_dxf
        path = os.path.join(tmp_dir, "_perf_bench.dxf")
        t0 = time.perf_counter()
        export_dxf(self.win._scene, path)
        self.results["dxf_export"] = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        n = import_dxf(self.win._scene, path, clear=True)
        self._tick()
        self._tick()
        self.results["dxf_import"] = (time.perf_counter() - t0) * 1000.0
        self._dxf_items = n
        try:
            os.remove(path)
        except OSError:
            pass

    def scn_svg_import(self):
        from easycad.fileio.svg_import import parse_svg_items
        svg_dir = os.path.join(ROOT, "broadcast_svg_set")
        files = sorted(f for f in os.listdir(svg_dir)) if os.path.isdir(svg_dir) else []
        files = [os.path.join(svg_dir, f) for f in files if f.lower().endswith(".svg")]
        if not files:
            return
        def one(i):
            for f in files:
                parse_svg_items(f, long_side=120.0)
        self._time("svg_import", 3, one)

    # ---- 헬퍼 -------------------------------------------------------------

    def _rects(self):
        rects = [it for it in self.win._scene.items() if isinstance(it, _RectItem)]
        if not rects:
            raise SystemExit("측정할 도형(_RectItem)이 문서에 없습니다 — --doc 확인")
        return rects

    def scene_summary(self) -> str:
        items = self.win._scene.items()
        arrows = [it for it in items if isinstance(it, (_ArrowItem, _PolyArrowItem))]
        bound = [a for a in arrows if a.has_binding()]
        return (f"아이템 {len(items)}개 (도형 {len(self._rects())} / 화살표 {len(arrows)} "
                f"/ 그중 바인딩 {len(bound)})")


def _fmt_row(key: str, ms: float, baseline: dict | None) -> str:
    label, is_frame = SCENARIOS[key]
    verdict = ""
    if is_frame:
        # 60fps 예산 대비 배수 — 1.0 이하면 통과.
        ratio = ms / FRAME_BUDGET_MS
        verdict = "OK" if ratio <= 1.0 else f"x{ratio:.1f} 초과"
    delta = ""
    if baseline and key in baseline:
        prev = baseline[key]
        if prev > 0:
            change = (ms - prev) / prev * 100.0
            arrow = "개선" if change < -2 else ("악화" if change > 2 else "동일")
            delta = f"{prev:9.1f}   {change:+6.1f}%  {arrow}"
    return f"{label:<22} {ms:9.2f}   {verdict:<12} {delta}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC, help="측정할 .ecad 문서")
    ap.add_argument("--no-minimap", action="store_true", help="미니맵을 숨기고 측정(기여도 분리)")
    ap.add_argument("--save", help="결과를 JSON으로 저장")
    ap.add_argument("--compare", help="이 JSON 대비 증감 표시")
    ap.add_argument("--only", help="쉼표로 구분한 시나리오만 실행(예: drag,select)")
    ap.add_argument("--trials", type=int, default=5,
                    help="best-of-N 반복 횟수(기본 5) — 노이즈 저항")
    ap.add_argument("--zoom", choices=("fit", "current"), default="fit",
                    help="fit=문서 전체가 화면에(기본·실사용 조건) / current=옛 방식")
    args = ap.parse_args()

    if not os.path.exists(args.doc):
        raise SystemExit(f"문서를 찾을 수 없습니다: {args.doc}")

    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    def want(name: str) -> bool:
        return only is None or name in only

    b = Bench(args.doc, hide_minimap=args.no_minimap, trials=args.trials, zoom=args.zoom)
    b.scn_load()                                    # 문서가 있어야 나머지가 성립 — 항상 실행
    b.apply_zoom()                                  # [2026-08-15] 측정 전 줌 상태 고정
    print()
    print(f"문서   : {os.path.basename(args.doc)}")
    print(f"씬     : {b.scene_summary()}")
    print(f"미니맵 : {'숨김' if args.no_minimap else '표시'}    "
          f"뷰 {VIEW_W}x{VIEW_H}    60fps 예산 {FRAME_BUDGET_MS:.2f} ms")
    print(f"측정   : zoom={args.zoom}(화면 안 도형 {b.visible_shape_count()}/{len(b._rects())}) "
          f"· best-of-{args.trials} · 프레임형은 페인트 flush x{Bench._PAINT_FLUSH} · 시도마다 배치 복원")
    print()

    if want("select"):      b.scn_select()
    if want("drag"):        b.scn_drag()
    if want("drag_multi"):  b.scn_drag_multi()
    if want("drag_all"):    b.scn_drag_all()
    if want("drag_subset"): b.scn_drag_subset()
    if want("rubberband"):  b.scn_rubberband()
    if want("release"):     b.scn_release()
    if want("zoom"):        b.scn_zoom()
    if want("pan"):         b.scn_pan()
    if want("render"):      b.scn_render()
    if want("render_fit"):  b.scn_render_fit()
    if want("svg_import"):  b.scn_svg_import()
    # DXF 왕복은 씬을 갈아엎으므로(clear=True) 반드시 맨 마지막.
    if want("dxf_import"):  b.scn_dxf_roundtrip(os.path.dirname(os.path.abspath(__file__)))

    baseline = None
    if args.compare:
        with open(args.compare, encoding="utf-8") as f:
            baseline = json.load(f).get("results", {})

    head = f"{'시나리오':<20} {'ms/회':>9}   {'60fps 판정':<12}"
    if baseline:
        head += f" {'이전 ms':>9}   {'증감':>7}"
    print(head)
    print("-" * (len(head) + 8))
    for key in SCENARIOS:
        if key in b.results:
            print(_fmt_row(key, b.results[key], baseline))
    print()

    over = [k for k, v in b.results.items()
            if SCENARIOS[k][1] and v > FRAME_BUDGET_MS]
    if over:
        print(f"60fps 미달: {', '.join(over)}")
    else:
        print("모든 프레임 시나리오가 60fps 예산 이내.")

    if args.save:
        payload = {
            "doc": os.path.basename(args.doc),
            "minimap": not args.no_minimap,
            "view": [VIEW_W, VIEW_H],
            "results": b.results,
        }
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"저장: {args.save}")


if __name__ == "__main__":
    main()
