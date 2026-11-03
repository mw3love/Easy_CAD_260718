"""🔷 도형 그리기 대조 재료 — 진짜 KAIROS 설계서(`tests/fixtures/flow_specs.json`, 2026-11-03 0단계 실측)를 서버 자리 계산(`board_diagram.place`)에
돌려 `web/test/fixtures/flow_place.json`으로. 웹 `flowboard.test.mjs`·화면 시험 `e2e/flow58`이 이 자리로 칠판을 짓는다.
배치 규칙(`flow_spec.layout`·`board_diagram.box_sizes`)을 고치면 다시 돌린다: python tools/export_flow_place.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from easycad.ai.board_diagram import place  # noqa: E402

src = json.load(open(os.path.join(ROOT, "tests", "fixtures", "flow_specs.json"), encoding="utf-8"))
out = {name: {"ask": v["ask"], "model": v["model"], "spec": json.dumps(v["spec"], ensure_ascii=False), "place": place(json.dumps(v["spec"], ensure_ascii=False))}
       for name, v in src.items()}
dst = os.path.join(ROOT, "web", "test", "fixtures", "flow_place.json")
with open(dst, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(dst, {k: (len(v["place"]["steps"]), v["place"]["width"], v["place"]["height"]) for k, v in out.items()})
