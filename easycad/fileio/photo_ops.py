"""사진→도면 ops 명세 → `.ecad` 아이템 (§8 항목28, 2026-10-01). **순수 파이썬 — PyQt 비의존.**

AI(또는 사람)가 사진을 보고 쓴 "ops" JSON을 `Sketch`(`sketch_build.py`) 아이템으로 바꾼다.
2026-08 파이프라인(관계만 남기고 재배치 — 2026-08-12 폐기, 회귀 가드
`test_sketch_pipeline_and_host_ai_modules_removed`)과 달리 원본 픽셀 좌표를 그대로 쓰고 선은
꺾이는 경로대로 고정한다. 실험 경위: `docs/history/2026-10.md` "사진→도면 재실험".

ops 어휘(좌표는 원본 사진 픽셀, x 오른쪽·y 아래):
    box      {"id","x1","y1","x2","y2","label"?,"font"?}      직사각형(+중앙 글자)
    text     {"x","y","text","font"?,"rot"?}                   자유 글자. rot 없음/0이면 (x,y)=왼쪽 위.
                                                               rot(도, 시계방향 +)이면 (x,y)=읽기 시작점의
                                                               글줄 가운데 — 그 점을 축으로 돌린다.
    line     {"pts":[[x,y],...],"head"?,"src"?,"dst"?}         고정 경로 연결선(끝을 상자 id에 지속연결)
    poly     {"pts":[[x,y],...],"closed"?}                     장식 꺾은선(안테나·스위치 내부 등)
    circle   {"id"?,"cx","cy","r"}
    dashrect {"x1","y1","x2","y2"}                             1점쇄선 테두리 영역
"""
from easycad.fileio.sketch_build import Sketch, _argb

SCALE = 2.0      # 원본 픽셀 → 캔버스 좌표 배율(글자가 읽힐 크기)
WIDTH = 2.0      # 선 두께
_DASHDOT = 4     # Qt.PenStyle.DashDotLine


def _line_height(font: int) -> float:
    """_TextItem 한 줄 높이 근사(캔버스 단위). 2026-10-01 실측: font 12/18/24/36 → 35/46/57/78."""
    return 1.8 * font + 13.0


def ops_to_sketch(spec: dict, *, dark: bool = False, scale: float = SCALE,
                  offset: tuple[float, float] = (0.0, 0.0)) -> tuple[Sketch, int]:
    """ops 명세 → Sketch. 반환 (Sketch, 건너뛴 op 수). 잘못된 op는 건너뛰고 셈만 한다.
    좌표는 원본 픽셀 × scale + offset(캔버스 단위) — offset으로 사진 왼쪽 위를 캔버스 어디에 둘지 정한다.

    선(line)은 다른 op를 다 만든 뒤에 만든다 — 선이 자기보다 뒤에 적힌 상자 id를 가리켜도
    지속연결이 빠지지 않게(2026-10-01 세션 직접 작성본에서 발견). 그래서 선은 항상 도형 위(z)에 온다."""
    s = Sketch(dark=dark)
    ink = _argb(s._default_color)
    ids = {}

    ox, oy = float(offset[0]), float(offset[1])

    def P(x, y):
        return [float(x) * scale + ox, float(y) * scale + oy]

    def rect_of(op):
        x1, y1, x2, y2 = (float(op[k]) for k in ("x1", "y1", "x2", "y2"))
        return x1 * scale + ox, y1 * scale + oy, (x2 - x1) * scale, (y2 - y1) * scale

    ops = spec.get("ops", [])
    if not isinstance(ops, list):
        return s, 0
    shapes = [op for op in ops if not (isinstance(op, dict) and op.get("op") == "line")]
    lines = [op for op in ops if isinstance(op, dict) and op.get("op") == "line"]

    skipped = 0
    for op in shapes + lines:
        try:
            k = op["op"]
            if k == "box":
                n = s.box(*rect_of(op), op.get("label") or None, width=WIDTH)
                if op.get("label"):
                    s._items[-1]["label"]["font"] = int(op.get("font", 15))
                if op.get("id"):
                    ids[op["id"]] = n
            elif k == "dashrect":
                s._items.append(dict(s._common(), type="rect", rect=list(rect_of(op)),
                                     pen=ink, width=WIDTH, fill=None, style=_DASHDOT))
            elif k == "circle":
                cx, cy, r = float(op["cx"]), float(op["cy"]), float(op["r"])
                n = s.ellipse((cx - r) * scale + ox, (cy - r) * scale + oy, 2 * r * scale, 2 * r * scale,
                              width=WIDTH)
                if op.get("id"):
                    ids[op["id"]] = n
            elif k == "text":
                font = int(op.get("font", 13))
                x, y = P(op["x"], op["y"])
                rot = float(op.get("rot") or 0.0)
                if rot % 360.0:
                    # 축 = 글줄 가운데 왼쪽 끝(로컬 (0, h/2)). pos+origin이 (x,y)에 오게.
                    half = _line_height(font) / 2.0
                    s.text(x, y - half, op["text"], font=font)
                    s._items[-1].update(rotation=rot, origin=[0.0, half])
                else:
                    s.text(x, y, op["text"], font=font)
            elif k == "line":
                q = [P(*p) for p in op["pts"]]
                if len(q) < 2:
                    raise ValueError("pts<2")
                d = s._common()
                d.update(type="sarrow", pts=q, color=ink, width=WIDTH, head=bool(op.get("head", False)),
                         auto_route=False, routing="straight", curve_r=0.0)
                src, dst = ids.get(op.get("src")), ids.get(op.get("dst"))
                if src is not None:
                    d.update(bind1=src.idx, bind1_pt=q[0])
                if dst is not None:
                    d.update(bind2=dst.idx, bind2_pt=q[-1])
                s._items.append(d)
            elif k == "poly":
                q = [P(*p) for p in op["pts"]]
                xs = [p[0] for p in q]
                ys = [p[1] for p in q]
                d = s._common()
                d.update(type="polygon", closed=bool(op.get("closed", False)),
                         rect=[min(xs), min(ys), max(max(xs) - min(xs), 1), max(max(ys) - min(ys), 1)],
                         pts=q, pen=ink, width=WIDTH, fill=None)
                s._items.append(d)
            else:
                skipped += 1
        except (KeyError, TypeError, ValueError, IndexError):
            skipped += 1
    return s, skipped
