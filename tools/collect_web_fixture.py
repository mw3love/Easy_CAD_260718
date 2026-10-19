"""웹이 실제로 만든 칠판 문서를 모아 데스크톱 왕복 시험 재료로 — `tests/fixtures/web_made.ecad`(§8 항목61 ④-1, 2026-10-19).

화면 시험(`cd web && npm run e2e`)을 돌리면 시험 서버 폴더 `web/.e2e-data/`에 흐름마다 웹이 만든 칠판(.ecad)이 남는다
(메모·검색 묶음·회의록·그림 묶음·프레임·웹 카드·표·화살표…). 그 아이템을 한 문서로 이어 붙여(화살표 bind 순번은 옮겨 맞춤) 저장한다.
웹에 새 종류·새 칸이 생기면 화면 시험에 흐름을 더한 뒤 이 도구를 다시 돌린다 → `tests/test_part58_roundtrip.py`가 데스크톱 왕복을 확인.

    python tools/collect_web_fixture.py
"""
from __future__ import annotations

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "web", ".e2e-data")
OUT = os.path.join(ROOT, "tests", "fixtures", "web_made.ecad")


def main() -> None:
    items, layers, kinds = [], [], {}
    for f in sorted(glob.glob(os.path.join(SRC, "*.ecad"))):
        if f.endswith(".prev.ecad"):
            continue
        with open(f, encoding="utf-8") as fh:
            doc = json.load(fh)
        base = len(items)   # 화살표 bind 순번만 옮김(자리는 그대로 — 겹쳐도 왕복 시험엔 상관없음)
        for it in doc.get("items") or []:
            it = dict(it)
            for k in ("bind1", "bind2"):
                if isinstance(it.get(k), int):
                    it[k] += base
            if it.get("type") == "image" and len(it.get("data", "")) > 4000:   # 큰 그림은 재료만 남기고 줄임(픽스처가 커지지 않게) — 2×2 흰 PNG
                it["data"] = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDAxMDAwMDAwAkBgMBmjUs8QAAAABJRU5ErkJggg=="
            items.append(it)
            kinds[it.get("type")] = kinds.get(it.get("type"), 0) + 1
        for ly in doc.get("layers") or []:
            if ly.get("id") not in {x.get("id") for x in layers}:
                layers.append(ly)
    out = {"format": "easycad-doc", "version": 1, "items": items}
    if layers:
        out["layers"] = layers
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"{OUT} — 아이템 {len(items)}개: " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))


if __name__ == "__main__":
    main()
