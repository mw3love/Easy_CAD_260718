"""[성능 최적화 2026-08-09, 4단계 착수 전 프로파일링] "뷰 렌더(전체 축소)" 시나리오 병목 확인.

배경: 3단계 완료 후 유일하게 60fps 예산을 초과한 시나리오(render_fit, 86.3ms = 5.2배,
`tools/_perf_after_stage3.json`). 착수 전 "item.paint() 자체인지, Qt 내부 dirty-region/
BSP 순회인지"부터 확인하라는 지시(전 세션 인수인계 프롬프트) — cProfile로 Python 레벨
(paint() 오버라이드 전부는 우리 코드)과 QGraphicsView.render() 자체(C++, cProfile에는
단일 프레임으로만 잡힘)의 시간 비중을 나눠본다.

사용법:
    python tools/profile_render_fit.py                # 5회 반복 프로파일, 상위 25줄
    python tools/profile_render_fit.py --reps 10 --lines 40
"""
import argparse
import cProfile
import io
import os
import pstats
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 표가 한글 라벨이라 콘솔이 cp949면 깨진다 — 출력 스트림만 UTF-8로 돌린다(perf_bench.py와 동일).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

from easycad.canvas.host import CanvasWindow
from easycad.fileio.document import load_document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DOC = os.path.join(ROOT, "heavy_perf_test.ecad")
VIEW_W, VIEW_H = 1400, 900


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=DEFAULT_DOC)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--lines", type=int, default=25)
    args = ap.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    win = CanvasWindow()
    win.resize(VIEW_W, VIEW_H)
    win.show()
    app.processEvents()

    load_document(win._scene, args.doc)
    app.processEvents()
    app.processEvents()

    win._view.fitInView(win._scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
    app.processEvents()

    img = QImage(VIEW_W, VIEW_H, QImage.Format.Format_ARGB32)
    items = win._scene.items()
    print(f"items={len(items)}  view={VIEW_W}x{VIEW_H}  reps={args.reps}")

    # 벽시계 기준 1회 평균(cProfile 계측 오버헤드 없이) — Qt 내부 C++ 시간이 얼마인지
    # 가늠하는 대조군.
    t0 = time.perf_counter()
    for _ in range(args.reps):
        p = QPainter(img)
        win._view.render(p)
        p.end()
    wall_ms = (time.perf_counter() - t0) * 1000.0 / args.reps
    print(f"벽시계 1회 평균: {wall_ms:.2f} ms")

    pr = cProfile.Profile()
    pr.enable()
    for _ in range(args.reps):
        p = QPainter(img)
        win._view.render(p)
        p.end()
    pr.disable()

    st = pstats.Stats(pr)
    st.sort_stats("cumulative")
    buf = io.StringIO()
    st.stream = buf
    st.print_stats(args.lines)
    print(buf.getvalue())

    # paint() 계열만 따로 합산 — "우리 Python paint 코드가 총 시간의 몇 %인가"를 직접 답한다.
    stats_dict = st.stats  # {(file, line, func): (cc, nc, tt, ct, callers)}
    paint_self = 0.0
    for (filename, lineno, funcname), (cc, nc, tt, ct, callers) in stats_dict.items():
        if funcname == "paint" and "core_shapes.py" in filename:
            paint_self += tt
    total_self = sum(v[2] for v in stats_dict.values())
    print(f"paint() 자체 시간(self) 합계: {paint_self*1000:.2f} ms / 프로파일 전체 self 합계 {total_self*1000:.2f} ms "
          f"({paint_self/total_self*100:.1f}%)")
    print("(나머지는 QGraphicsView.render()/QPainter C++ 내부 — cProfile은 render() 호출 1건으로만 잡음)")


if __name__ == "__main__":
    main()
