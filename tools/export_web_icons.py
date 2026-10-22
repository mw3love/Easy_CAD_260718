"""데스크톱 위 막대 아이콘(손그림 A2 SVG)을 웹 칠판 위 막대용으로 뽑는다(2026-10-22 디자인 점검 — 아이콘 W1).

`easycad/resources/icons/<이름>.svg`의 코랄(#da7756)을 currentColor로 바꿔 `web/src/next/icons.json`에 쓴다 —
웹은 글자색(--mb-icon, 데스크톱 `_ICON_COLOR_THEME`과 같은 중립색)으로 칠한다. 아이콘을 고치거나 늘리면 다시 돌린다.
실행: python tools/export_web_icons.py
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "easycad", "resources", "icons")
OUT = os.path.join(ROOT, "web", "src", "next", "icons.json")
# 웹 위 막대가 쓰는 것만(이름 = 파일 이름)
NAMES = ["board", "open", "save", "download", "pdf", "undo", "redo", "select", "sarrow", "text", "line", "polygon",
         "pen", "badge", "present", "frame", "table", "memo", "web", "zoom_fit", "share", "generate", "theme"]


def main():
    out = {}
    for n in NAMES:
        with open(os.path.join(SRC, n + ".svg"), encoding="utf-8") as f:
            s = f.read()
        s = re.sub(r'\s+xmlns="[^"]*"', "", s).replace("#da7756", "currentColor")
        out[n] = re.sub(r"\s+", " ", s).strip()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{len(out)}개 → {OUT}")


if __name__ == "__main__":
    main()
