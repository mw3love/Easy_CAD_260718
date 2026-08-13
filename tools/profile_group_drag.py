"""[성능 조사 2026-08-13] 200개+ 전체 선택 그룹 드래그 프레임당 비용 프로파일링.

배경: `tools/perf_bench.py --only drag_all`(2026-08-13 신설)로 사용자 제공 실측 문서
(`200.ecad`, 도형 200개·화살표 0개)에서 전체 선택 드래그가 121.81ms/frame(60fps 예산
16.67ms 대비 x7.3 초과)로 확인됐다. `drag_multi`(20개 고정)는 18.61ms로 이미 예산을
살짝 넘지만 배수가 훨씬 작다 — 20→200으로 늘 때 병목이 선형(선택 개수 비례)인지
비선형(씬 전체 순회 등)인지는 cProfile 함수별 누적시간으로만 구분 가능하다.

사용법:
    python tools/profile_group_drag.py --doc "C:\\Users\\aros\\Desktop\\200.ecad"
    python tools/profile_group_drag.py --doc <path> --frames 10 --lines 25
"""
import argparse
import cProfile
import io
import os
import pstats
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 결과 상태만 필요 — 화면 확인은 별도

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import _RectItem
from easycad.fileio.document import load_document


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", required=True, help="측정할 .ecad 문서(전체 도형을 선택해 드래그)")
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--lines", type=int, default=25)
    ap.add_argument("--no-minimap", action="store_true", help="미니맵 기여도 분리(perf_bench.py와 동일 관례)")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    w = CanvasWindow()
    load_document(w._scene, args.doc)
    w.show()
    app.processEvents()
    app.processEvents()  # load_document 후 지연 reroute 정착(profile_reroute.py와 동일 근거)
    if args.no_minimap:
        for attr in ("_minimap", "_minimap_panel"):
            wgt = getattr(w, attr, None)
            if wgt is not None:
                wgt.hide()
        app.processEvents()

    rects = [it for it in w._scene.items() if isinstance(it, _RectItem)]
    if not rects:
        raise SystemExit("측정할 도형(_RectItem)이 문서에 없습니다")
    print(f"씬 아이템 {len(w._scene.items())}개 / 도형 {len(rects)}개 / "
          f"프레임 {args.frames}회 전체선택 드래그")

    w._scene.clearSelection()
    for r in rects:
        r.setSelected(True)
    app.processEvents()

    pr = cProfile.Profile()
    pr.enable()
    for _ in range(args.frames):
        for r in rects:
            r.setPos(r.pos() + QPointF(2, 1))
        app.processEvents()
    pr.disable()

    st = pstats.Stats(pr)
    st.sort_stats("cumulative")
    buf = io.StringIO()
    st.stream = buf
    st.print_stats(args.lines)
    print(buf.getvalue())


if __name__ == "__main__":
    main()
