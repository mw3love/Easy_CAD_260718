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

사용법:
    python tools/perf_bench.py                          # 기본 문서로 전 시나리오
    python tools/perf_bench.py --doc heavy_perf_test.ecad
    python tools/perf_bench.py --no-minimap             # 미니맵 기여도 분리
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

    def __init__(self, doc_path: str, hide_minimap: bool):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.doc_path = doc_path
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

    def _time(self, key: str, reps: int, fn):
        """fn을 reps회 돌려 1회 평균 ms를 기록. reps는 시나리오마다 다르다(비용 규모가 달라서)."""
        t0 = time.perf_counter()
        for i in range(reps):
            fn(i)
        dt = (time.perf_counter() - t0) * 1000.0 / max(reps, 1)
        self.results[key] = dt
        return dt

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
            self._tick()
        self._time("select", 10, one)

    def scn_drag(self):
        r = self._rects()[0]
        self.win._scene.clearSelection()
        r.setSelected(True)
        self._tick()
        # 실제 드래그와 같은 경로: setPos → scene.changed → reroute/repaint 체인 전부 탄다.
        def one(i):
            r.setPos(r.pos() + QPointF(3, 2))
            self._tick()
        self._time("drag", 20, one)
        self.win._scene.clearSelection()
        self._tick()

    def scn_drag_multi(self):
        rects = self._rects()[:20]
        self.win._scene.clearSelection()
        for r in rects:
            r.setSelected(True)
        self._tick()
        def one(i):
            for r in rects:
                r.setPos(r.pos() + QPointF(2, 1))
            self._tick()
        self._time("drag_multi", 10, one)
        self.win._scene.clearSelection()
        self._tick()

    def scn_zoom(self):
        def one(i):
            self.win._on_wheel_zoom(120 if i % 2 == 0 else -120)
            self._tick()
        self._time("zoom", 20, one)

    def scn_pan(self):
        # 팬은 스크롤바 값 직접 조작으로 구현돼 있다(core_view 주석 참조) — 같은 경로로 흉내낸다.
        hb = self.win._view.horizontalScrollBar()
        vb = self.win._view.verticalScrollBar()
        def one(i):
            hb.setValue(hb.value() + 7)
            vb.setValue(vb.value() + 5)
            self._tick()
        self._time("pan", 20, one)

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
    args = ap.parse_args()

    if not os.path.exists(args.doc):
        raise SystemExit(f"문서를 찾을 수 없습니다: {args.doc}")

    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    def want(name: str) -> bool:
        return only is None or name in only

    b = Bench(args.doc, hide_minimap=args.no_minimap)
    b.scn_load()                                    # 문서가 있어야 나머지가 성립 — 항상 실행
    print()
    print(f"문서   : {os.path.basename(args.doc)}")
    print(f"씬     : {b.scene_summary()}")
    print(f"미니맵 : {'숨김' if args.no_minimap else '표시'}    "
          f"뷰 {VIEW_W}x{VIEW_H}    60fps 예산 {FRAME_BUDGET_MS:.2f} ms")
    print()

    if want("select"):      b.scn_select()
    if want("drag"):        b.scn_drag()
    if want("drag_multi"):  b.scn_drag_multi()
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
