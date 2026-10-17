"""웹 칠판 붙는 규칙(web/src/next/connect.js)이 데스크톱 `_nearest_border`·`_shape_ports`와 같은 답을 내는지 맞춰 볼 시험 사례(§8 항목61 3단계, 2026-10-17).

도형(상자·원·심볼 여러 종류·닫힌 다각형, 회전·배율 섞음)마다 포트 넷과 주변 임의 점의 외곽선 최근접점·바깥 법선을
데스크톱 엔진으로 풀어 `web/test/fixtures/connect_cases.json`에 쓴다. 웹 시험(`web/test/connect.test.mjs`)이 같은 입력으로 비교한다.
데스크톱 붙는 규칙을 고치면 이 도구를 다시 돌려 웹도 따라가게 한다.

실행: python tools/export_connect_cases.py [--seed 7]
"""
import argparse
import json
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from easycad.canvas.core_shapes import _nearest_border, _shape_ports  # noqa: E402
from easycad.fileio.document import dict_to_item  # noqa: E402

KINDS = ["decision", "data", "terminal", "delay", "database", "triangle", "document", "display", "prep", "manual_input"]


def _base(rnd, typ, w, h, **extra):
    rot = rnd.choice([0, 0, 0, 30, 90, 135])
    d = {"type": typ, "rect": [0, 0, w, h], "pos": [rnd.randrange(-200, 200, 10), rnd.randrange(-200, 200, 10)],
         "scale": rnd.choice([1, 1, 1, 1.5, 0.75]), "rotation": rot, "origin": [w / 2, h / 2] if rot else [0, 0], "z": 0,
         "pen": "#ff000000", "width": 2, "fill": None}
    d.update(extra)
    return d


def shapes(rnd):
    out = []
    for w, h in [(120, 60), (80, 80), (160, 90)]:
        out.append(_base(rnd, "rect", w, h))
        out.append(_base(rnd, "ellipse", w, h))
    for k in KINDS:
        out.append(_base(rnd, "symbol", rnd.choice([100, 140]), rnd.choice([60, 100]), kind=k))
    pts = [[0, 0], [120, 10], [90, 80], [20, 60]]
    out.append(_base(rnd, "polygon", 120, 80, closed=True, pts=pts))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    rnd = random.Random(a.seed)
    _app = QApplication.instance() or QApplication(sys.argv)
    cases = []
    for d in shapes(rnd):
        it = dict_to_item(d)
        r = lambda v: round(v, 4)  # noqa: E731
        ports = [[r(p.x()), r(p.y()), r(n.x()), r(n.y())] for p, n in _shape_ports(it)]
        c = it.mapToScene(it.rect().center())
        probes = []
        for _ in range(24):
            q = QPointF(c.x() + rnd.uniform(-160, 160), c.y() + rnd.uniform(-120, 120))
            p, n = _nearest_border(it, q)
            probes.append([r(q.x()), r(q.y()), r(p.x()), r(p.y()), r(n.x()), r(n.y())])
        cases.append({"item": d, "ports": ports, "probes": probes})
    out = os.path.join(ROOT, "web", "test", "fixtures", "connect_cases.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False)
    print(f"{len(cases)}개 도형 → {out}")


if __name__ == "__main__":
    main()
