"""[성능 계획 1-0, 2026-08-15] 성능 측정용 `.ecad` 재현 문서 생성기 — 결정론적(시드 고정).

`docs/perf_plan_500_1000.md` 1-0의 산출물. 지금까지 성능 측정은 `heavy_perf_test.ecad`
(도형 800 + 화살표 799) 하나에 의존했는데, 목표 규모(500 / 1000)와 혼합비를 재현할 문서가
없어 목표 대비 판정을 할 수 없었다. 이 스크립트가 그 축을 만든다.

**왜 새로 만들지 않고 `Sketch`를 쓰는가**(규칙 2 손안의 카드): `easycad/fileio/sketch_build.py`
가 이미 Qt 없이 `.ecad` JSON을 만들고, 화살표의 **지속연결 바인딩 + 직교 자동라우팅**까지
정확히 세팅해 준다. 여기서 스키마를 다시 쓰면 드리프트만 생긴다.

**결정론**: 같은 인자 → 항상 같은 파일(시드 고정 `random.Random`). A/B 측정이 문서 차이로
오염되지 않게 하는 것이 이 스크립트의 존재 이유다.

**산출물은 커밋하지 않는다** — 리포 루트 `*.ecad`는 `.gitignore` 대상이고, 이 스크립트만
있으면 언제 어디서든 똑같이 재생성된다.

사용법:
    python tools/make_perf_doc.py --preset 500      # perf_500.ecad  (도형250 + 화살표250)
    python tools/make_perf_doc.py --preset 1000     # perf_1000.ecad (도형500 + 화살표500)
    python tools/make_perf_doc.py --shapes 300 --arrows 700 --out custom.ecad
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from easycad.fileio.sketch_build import Sketch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 도형 크기·격자 간격. 셀(220x160)이 도형(120x72)보다 넉넉해 도형 사이에 통로가 남는다 —
# A* 직교 라우팅이 '장애물을 실제로 피하는' 상황을 만들어야 화살표 비용이 현실적으로 잡힌다
# (빈틈없이 붙여 두면 라우터가 매번 최악 경로를 타 측정이 과장된다).
SHAPE_W, SHAPE_H = 120.0, 72.0
CELL_W, CELL_H = 220.0, 160.0

PRESETS = {
    "500":  dict(shapes=250, arrows=250, out="perf_500.ecad"),
    "1000": dict(shapes=500, arrows=500, out="perf_1000.ecad"),
}


def build(shapes: int, arrows: int, seed: int, cols: int | None) -> Sketch:
    rnd = random.Random(seed)
    if not cols:
        # 대략 정사각형 배치 — 한 축으로 길쭉하면 '전체 축소' 렌더가 비현실적으로 유리해진다.
        cols = max(1, int(shapes ** 0.5 + 0.5))

    s = Sketch()
    nodes = []
    for i in range(shapes):
        r, c = divmod(i, cols)
        nodes.append(s.box(c * CELL_W, r * CELL_H, SHAPE_W, SHAPE_H, f"N{i}"))

    # 화살표는 '이웃끼리'를 기본으로 하되 일부는 멀리 잇는다. 이웃만 이으면 경로가 전부 짧아
    # A* 비용이 과소평가되고, 전부 랜덤이면 실제 순서도와 동떨어진다.
    used = set()
    made = 0
    guard = 0
    while made < arrows and guard < arrows * 40:
        guard += 1
        a = rnd.randrange(shapes)
        if rnd.random() < 0.85:                     # 85% 이웃(오른쪽/아래)
            b = a + (1 if rnd.random() < 0.5 else cols)
            if b >= shapes or (b % cols == 0 and b == a + 1):
                continue                            # 행 끝을 넘어가는 '오른쪽'은 버림
        else:                                       # 15% 원거리 — 페이지를 가로지르는 긴 경로
            b = rnd.randrange(shapes)
        if a == b or (a, b) in used or (b, a) in used:
            continue
        used.add((a, b))
        s.arrow(nodes[a], nodes[b])
        made += 1

    if made < arrows:
        print(f"⚠ 요청 {arrows}개 중 {made}개만 생성(격자에서 만들 수 있는 쌍이 부족)")
    return s


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=sorted(PRESETS), help="500 또는 1000")
    ap.add_argument("--shapes", type=int)
    ap.add_argument("--arrows", type=int)
    ap.add_argument("--out")
    ap.add_argument("--seed", type=int, default=20260815, help="고정 시드(결정론)")
    ap.add_argument("--cols", type=int, help="격자 열 수(생략 시 정사각형에 가깝게)")
    a = ap.parse_args(argv)

    if a.preset:
        cfg = dict(PRESETS[a.preset])
        shapes = a.shapes if a.shapes is not None else cfg["shapes"]
        arrows = a.arrows if a.arrows is not None else cfg["arrows"]
        out = a.out or cfg["out"]
    else:
        if a.shapes is None or a.arrows is None or not a.out:
            ap.error("--preset 이거나 --shapes/--arrows/--out 을 모두 줘야 합니다")
        shapes, arrows, out = a.shapes, a.arrows, a.out

    s = build(shapes, arrows, a.seed, a.cols)
    path = out if os.path.isabs(out) else os.path.join(ROOT, out)
    n = s.save(path)
    print(f"저장: {path}")
    print(f"  아이템 {n}개 (도형 {shapes} / 화살표 {arrows}) · seed={a.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
