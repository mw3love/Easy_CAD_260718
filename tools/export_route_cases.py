"""웹 칠판 길 찾기(web/src/route.js)가 데스크톱 `_route_ortho`와 같은 답을 내는지 맞춰 볼 시험 사례를 만든다(§8 항목61, 2026-10-17).

임의 배치(연결 상자 둘 + 다른 상자 0~4개, 포트·테두리 자리·떠 있는 끝)를 데스크톱 엔진으로 풀어
`web/test/fixtures/route_cases.json`에 쓴다. 웹 시험(`web/test/route.test.mjs`)이 같은 입력으로 같은 꼭짓점이 나오는지 본다.
데스크톱 라우팅을 고치면 이 도구를 다시 돌려 웹도 따라가게 한다.

실행: python tools/export_route_cases.py [--n 300] [--seed 7]
"""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF, QRectF  # noqa: E402

from easycad.canvas.core_routing import _dedup_pts, _route_ortho  # noqa: E402

SIDES = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def _rect(rnd):
    w, h = rnd.choice([80, 120, 160]), rnd.choice([60, 80, 120])
    return [rnd.randrange(-400, 400, 10), rnd.randrange(-300, 300, 10), w, h]


def _overlap(a, b, pad=8):
    return a[0] < b[0] + b[2] + pad and b[0] < a[0] + a[2] + pad and a[1] < b[1] + b[3] + pad and b[1] < a[1] + a[3] + pad


def _anchor(rnd, r):
    side = rnd.choice(list(SIDES))
    t = 0.5 if rnd.random() < 0.6 else round(rnd.uniform(0.15, 0.85), 2)   # 포트 또는 테두리 아무 자리
    x, y, w, h = r
    p = {"left": (x, y + t * h), "right": (x + w, y + t * h), "top": (x + t * w, y), "bottom": (x + t * w, y + h)}[side]
    return [round(p[0], 2), round(p[1], 2)], side


def make_case(rnd):
    rects = []
    while len(rects) < 2 + rnd.randrange(0, 5):
        r = _rect(rnd)
        if not any(_overlap(r, q) for q in rects):
            rects.append(r)
    a, b, others = rects[0], rects[1], rects[2:]
    s, ss = _anchor(rnd, a)
    if rnd.random() < 0.15:   # 떠 있는 끝(안 붙음)
        e, es, conn_e = [rnd.randrange(-400, 400, 10), rnd.randrange(-300, 300, 10)], None, None
    else:
        e, es = _anchor(rnd, b)
        conn_e = b
    return {"s": s, "ns": ss, "e": e, "ne": es, "conn": [a, conn_e], "obstacles": others, "minStub": [0, 25]}


def solve(c):
    q = lambda p: QPointF(*p)
    n = lambda side: None if side is None else QPointF(*SIDES[side])
    rr = lambda r: None if r is None else QRectF(*r)
    s, e = q(c["s"]), q(c["e"])
    mids = _route_ortho(s, e, n(c["ns"]), n(c["ne"]), [rr(r) for r in c["obstacles"]], 12.0,
                        conn_rects=tuple(rr(r) for r in c["conn"]), min_stub=tuple(c["minStub"]))
    return [[round(p.x(), 4), round(p.y(), 4)] for p in _dedup_pts([s] + mids + [e])]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args(argv)
    rnd = random.Random(a.seed)
    cases = []
    for _ in range(a.n):
        c = make_case(rnd)
        c["expect"] = solve(c)
        cases.append(c)
    out = os.path.join(ROOT, "web", "test", "fixtures", "route_cases.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"seed": a.seed, "cases": cases}, f, ensure_ascii=False)
    print(f"{len(cases)}개 → {out}")


if __name__ == "__main__":
    main()
