"""데스크톱 순서도·안테나 심볼 모양을 웹 칠판용 SVG 경로로 뽑는다(§8 항목61).

`core_symbols._SYMBOL_KINDS`의 경로 팩토리를 100×100 상자에 그려 `web/src/symbols.json`에 쓴다 —
웹은 이 경로를 상자 크기에 맞춰 늘려 그린다(데스크톱과 같은 모양을 손으로 다시 그리지 않으려고).
상자 비율에 따라 모양이 달라지는 것(시작/끝의 둥근 끝, 지연의 반원)은 "fit": "rect"로 표시 — 웹이 직접 그린다.
비율을 지키는 안테나 그림은 "fit": "keep"(가운데 맞춤), 나머지는 "stretch".
실행: python tools/export_web_symbols.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtCore import QRectF  # noqa: E402
from PyQt6.QtGui import QPainterPath  # noqa: E402

from easycad.canvas.core_symbols import _SYMBOL_KINDS  # noqa: E402


def to_svg(path: QPainterPath) -> str:
    out, i, n = [], 0, path.elementCount()
    ET = QPainterPath.ElementType
    while i < n:
        e = path.elementAt(i)
        if e.type == ET.MoveToElement:
            out.append(f"M{e.x:.2f},{e.y:.2f}"); i += 1
        elif e.type == ET.LineToElement:
            out.append(f"L{e.x:.2f},{e.y:.2f}"); i += 1
        elif e.type == ET.CurveToElement:
            c2, ep = path.elementAt(i + 1), path.elementAt(i + 2)
            out.append(f"C{e.x:.2f},{e.y:.2f} {c2.x:.2f},{c2.y:.2f} {ep.x:.2f},{ep.y:.2f}"); i += 3
        else:
            i += 1
    return " ".join(out)


def _stretches(a: str, b: str) -> bool:
    """100×100 경로를 가로로 두 배 늘린 것이 200×100 경로와 같은가."""
    import re
    na = [float(x) for x in re.findall(r"-?\d+\.\d+", a)]
    nb = [float(x) for x in re.findall(r"-?\d+\.\d+", b)]
    return len(na) == len(nb) and all(abs((x * 2 if i % 2 == 0 else x) - y) < 0.5 for i, (x, y) in enumerate(zip(na, nb)))


if __name__ == "__main__":
    def fit(k, fn):
        if k in ("terminal", "delay"):
            return "rect"
        a, b = to_svg(fn(QRectF(0, 0, 100, 100))), to_svg(fn(QRectF(0, 0, 200, 100)))
        return "stretch" if a.count(" ") == b.count(" ") and _stretches(a, b) else "keep"

    data = {k: {"name": name, "fit": fit(k, fn), "d": to_svg(fn(QRectF(0, 0, 100, 100)))} for k, (name, fn) in _SYMBOL_KINDS.items()}
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "src", "symbols.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(out, len(data))
