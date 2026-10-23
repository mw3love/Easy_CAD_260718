"""웹 칠판 SVG → 도형(web/src/next/svgin.js)이 데스크톱 `fileio/svg_import.py`와 같은 도형을 내는지 맞춰 볼 시험 사례(§8 항목63 1단계, 2026-10-23).

손으로 쓴 사례(요소마다·상대/절대·S/T 반사·호·Z 뒤 이어 그리기·<g> 안·글자) + KAIROS가 실제로 만든 아이콘(`tests/fixtures/svg_ai/`, 0단계 실측 19개)을
데스크톱으로 읽어 .ecad 항목(`document.item_to_dict`)을 `web/test/fixtures/svg_cases.json`에 쓴다. 웹 시험(`web/test/svgin.test.mjs`)이 같은 입력으로 비교한다.
데스크톱 SVG 읽기를 고치면 이 도구를 다시 돌려 웹도 따라가게 한다.

실행: python tools/export_svg_cases.py
"""
import glob
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from easycad.fileio.document import item_to_dict  # noqa: E402
from easycad.fileio.svg_import import parse_svg_string  # noqa: E402

W = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">{body}</svg>'
HAND = {
    "요소마다": ("0 0 100 80", '<line x1="0" y1="0" x2="10" y2="10"/><rect x="5" y="5" width="20" height="10"/><circle cx="50" cy="40" r="10"/>'
                              '<ellipse cx="60" cy="20" rx="12" ry="5"/><polygon points="1,1 20,1 10,15"/><polyline points="1 1 5 5 9 1"/>'),
    "절대 경로": ("0 0 100 100", '<path d="M10 10 L40 10 H60 V40 C60 60 40 70 20 60 Q5 50 10 10 Z"/>'),
    "상대 경로": ("0 0 100 100", '<path d="m10 10 l30 0 h20 v30 c0 20 -20 30 -40 20 q-15 -10 -10 -50 z"/>'),
    "M 뒤 좌표 = 선": ("0 0 50 50", '<path d="M5 5 20 5 20 20 m5 5 10 0 0 10"/>'),
    "S 반사": ("0 0 100 50", '<path d="M10 25 C20 5 30 5 40 25 S60 45 70 25 s10 -20 20 0"/><path d="M10 40 S20 30 30 40"/>'),
    "T 반사": ("0 0 100 50", '<path d="M10 25 Q20 5 30 25 T50 25 t20 0"/><path d="M10 45 T30 45"/>'),
    "호": ("0 0 120 120", '<path d="M20 60 A40 40 0 0 1 100 60"/><path d="M20 60 A40 40 0 1 0 100 60"/><path d="M10 10 a20 10 30 1 1 30 20"/>'
                         '<path d="M60 100 A5 5 0 0 1 100 100"/><path d="M5 115 A0 5 0 0 1 20 115"/>'),
    "Z 뒤 이어 그리기": ("0 0 60 60", '<path d="M10 10 L30 10 L30 30 Z L50 50"/><path d="M5 50 L20 50 L5 50 Z"/>'),
    "붙은 숫자": ("0 0 60 60", '<path d="M10-5.5.5 20L30,30l-5-5"/>'),
    "모르는 명령": ("0 0 60 60", '<path d="M10 10 L20 20 X 30 30 L40 40"/>'),
    "g 안": ("0 0 60 60", '<g stroke="black"><rect x="1" y="2" width="3" height="4"/><g><line x1="5" y1="5" x2="9" y2="9"/></g></g>'),
    "글자": ("0 0 100 60", '<text x="10" y="40" font-size="12">안테나 &amp; 랙</text><text x="10" y="55" fill="#ff0000">작은 글</text><text x="1" y="1">  </text>'),
    "같은 점": ("0 0 60 60", '<path d="M10 10 L10 10 L20 20 C20 20 20 20 20 20 Q20 20 20 20 L30 30"/>'),
    "M 두 번": ("0 0 60 60", '<path d="M10 10 M20 20 L30 30"/><path d="M5 5"/>'),
    "끝에 M": ("0 0 60 60", '<path d="M10 10 L20 20 M30 30"/><path d="M10 10 L20 20 M30 30 M40 40"/><path d="M10 10 L20 20 Z M40 40 L50 50"/><path d="L20 20 L30 10"/>'),
    "viewBox 없음": (None, '<rect x="10" y="10" width="30" height="20"/>'),
}


def case(name, svg, long_side=160.0, center=(0.0, 0.0)):
    items, _vb = parse_svg_string(svg, long_side, QPointF(*center))
    keep = ("type", "pos", "line", "rect", "closed", "pts", "elements", "text", "color", "font")
    return {"name": name, "svg": svg, "long": long_side, "center": list(center),
            "items": [{k: d[k] for k in keep if k in d} for d in (item_to_dict(it) for it in items)]}


def main():
    app = QApplication.instance() or QApplication([])  # noqa: F841 — 담아 두지 않으면 바로 사라져 도형을 만들다 꺼짐
    out = []
    for name, (vb, body) in HAND.items():
        svg = W.format(vb=vb, body=body) if vb else f'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40">{body}</svg>'
        out.append(case(name, svg))
        out.append(case(name + " · 다른 자리", svg, 90.0, (300.0, -120.0)))
    for f in sorted(glob.glob(os.path.join(ROOT, "tests", "fixtures", "svg_ai", "*.svg"))):
        out.append(case("AI " + os.path.basename(f), open(f, encoding="utf-8").read(), 160.0, (40.0, 25.0)))
    dst = os.path.join(ROOT, "web", "test", "fixtures", "svg_cases.json")
    with open(dst, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=0)
    print(f"{len(out)}개 사례 → {dst}")


if __name__ == "__main__":
    main()
