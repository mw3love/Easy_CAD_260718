"""사진→도면 실험용: 모델이 낸 "ops" JSON 명세를 .ecad로 만들고, 원본 사진과 같은 틀로 렌더한다.

2026-10-01 실험(`docs/history/2026-10.md` "사진→도면 재실험")에서 쓴 도구를 리포로 옮긴 것.
8월 앱 파이프라인(관계만 남기고 재배치 — 2026-08-12 폐기)과 달리, 원본 픽셀 좌표를 그대로
쓰고 선은 꺾이는 경로대로 고정한다. 앱 런타임 비의존(개발용).

ops 어휘(좌표는 원본 사진 픽셀, x 오른쪽·y 아래):
    box      {"id","x1","y1","x2","y2","label"?,"font"?}      직사각형(+중앙 글자)
    text     {"x","y","text","font"?}                          자유 글자((x,y)=왼쪽 위)
    line     {"pts":[[x,y],...],"head"?,"src"?,"dst"?}         고정 경로 연결선(끝을 상자 id에 지속연결)
    poly     {"pts":[[x,y],...],"closed"?}                     장식 꺾은선(안테나·스위치 내부 등)
    circle   {"id"?,"cx","cy","r"}
    dashrect {"x1","y1","x2","y2"}                             1점쇄선 테두리 영역

사용법:
    python tools/sketch_ops.py spec.json out.ecad [out.png 1252x733]   # .ecad 생성(+원본 크기로 렌더)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycad.fileio.sketch_build import Sketch, _argb

SCALE = 2.0      # 원본 픽셀 → 캔버스 좌표 배율(글자가 읽힐 크기)
WIDTH = 2.0      # 선 두께
_DASHDOT = 4     # Qt.PenStyle.DashDotLine


def build(spec: dict, out: str, *, dark: bool = False, scale: float = SCALE) -> tuple[int, int]:
    """ops 명세 → .ecad 저장. 반환 (아이템 수, 건너뛴 op 수). 잘못된 op는 건너뛰고 셈만 한다."""
    s = Sketch(dark=dark)
    ink = _argb(s._default_color)
    ids = {}

    def P(x, y):
        return [float(x) * scale, float(y) * scale]

    def rect_of(op):
        x1, y1, x2, y2 = (float(op[k]) for k in ("x1", "y1", "x2", "y2"))
        return x1 * scale, y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale

    skipped = 0
    for op in spec.get("ops", []):
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
                n = s.ellipse((cx - r) * scale, (cy - r) * scale, 2 * r * scale, 2 * r * scale,
                              width=WIDTH)
                if op.get("id"):
                    ids[op["id"]] = n
            elif k == "text":
                s.text(float(op["x"]) * scale, float(op["y"]) * scale, op["text"],
                       font=int(op.get("font", 13)))
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
        except (KeyError, TypeError, ValueError):
            skipped += 1
    return s.save(out), skipped


def render(ecad: str, out: str, size: tuple[int, int], *, scale: float = SCALE) -> None:
    """원본 사진 프레임(0,0)~size를 흰 배경으로 렌더 — 원본과 1:1로 겹쳐 비교하기 위함.
    실제 CanvasWindow에 불러와 그리므로(오프스크린이 아니면) 한글 글꼴까지 실화면과 같다."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtCore import QRectF
    from easycad.canvas.host import CanvasWindow
    from easycad.fileio.document import load_document

    app = QApplication.instance() or QApplication([])
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    load_document(w._scene, ecad)
    for _ in range(5):
        app.processEvents()
    sc = w._scene
    sc.clearSelection()
    sc.setBackgroundBrush(QColor("#ffffff"))
    img = QImage(size[0], size[1], QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    sc.render(p, QRectF(0, 0, size[0], size[1]), QRectF(0, 0, size[0] * scale, size[1] * scale))
    p.end()
    img.save(out)
    w.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    n, sk = build(spec, sys.argv[2])
    print(f"items={n} skipped={sk}")
    if len(sys.argv) > 4:
        wh = tuple(int(v) for v in sys.argv[4].lower().split("x"))
        render(sys.argv[2], sys.argv[3], wh)
        print("rendered", sys.argv[3])
