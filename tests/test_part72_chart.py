"""§8 항목66 1단계(2026-10-25) — 그래프 = 표 + 모양. 웹 `chart.js` ↔ 데스크톱 `core_chart.py` 대조 + 데스크톱 보존·그리기.

대조 재료 `tests/fixtures/chart_cases.json`은 웹이 만든다(`node tools/export_chart_cases.mjs`) — 웹을 고치면 다시 돌리고 이 시험이 데스크톱을 잡는다.
"""
import json
import os
import re

import pytest

from _shared import QApplication  # noqa: F401 — QApplication 준비
from easycad.canvas import core_chart as cc

CASES = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "chart_cases.json"), encoding="utf-8"))
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _same(a, b, path=""):
    """조각 하나하나 같은지 — 숫자는 0.11 안(삼각함수 마지막 자리 차이로 반올림이 한 칸 갈릴 수 있음), 글은 그대로."""
    if isinstance(a, dict):
        assert set(a) == set(b), (path, sorted(a), sorted(b))
        for k in a:
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), (path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and not isinstance(a, bool) and a is not None and b is not None:
        assert abs(a - b) <= 0.11, (path, a, b)
    elif isinstance(a, str) and path.endswith(".d"):
        na, nb = [float(v) for v in _NUM.findall(a)], [float(v) for v in _NUM.findall(b)]
        assert re.sub(_NUM, "#", a) == re.sub(_NUM, "#", b), path
        assert len(na) == len(nb) and all(abs(x - y) <= 0.11 for x, y in zip(na, nb)), (path, a[:80], b[:80])
    else:
        assert a == b, (path, a, b)


@pytest.mark.parametrize("case", CASES, ids=[f"{i}-{c['it']['chart']}" for i, c in enumerate(CASES)])
def test_desktop_matches_web(case):
    it = case["it"]
    _same(cc.chart_data(it), case["data"], "data")
    assert cc.chart_whys(it) == case["whys"]
    assert cc.is_chart(it) == case["isChart"]
    _same(cc.chart_scene(it), case["scene"], "scene")


def test_num_of():
    assert cc.num_of("1,234") == 1234
    assert cc.num_of("45%") == 45
    assert cc.num_of("약 1.2억") == 1.2
    assert cc.num_of("1~3") is None
    assert cc.num_of("") is None


def test_desktop_keeps_chart_and_draws_it(tmp_path):
    """웹이 그래프로 바꾼 표 → 데스크톱이 열고(그래프로 그림) 칸을 고쳐 저장 → chart·table_wh 그대로, 숫자는 고친 값."""
    from PyQt6.QtGui import QImage, QPainter, QColor
    from easycad.fileio.document import dict_to_item, item_to_dict

    d = {"type": "table", "pos": [0, 0], "scale": 1, "rotation": 0, "z": 1, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None,
         "rect": [0, 0, 360, 240], "rows": 3, "cols": 2, "header": True, "cells": [["나라", "비중"], ["중국", "60"], ["미국", "40"]],
         "col_widths": [0.5, 0.5], "chart": "pie", "table_wh": [200, 90]}
    it = dict_to_item(d)
    assert it._chart_dict()["chart"] == "pie"
    img = QImage(400, 280, QImage.Format.Format_ARGB32)
    img.fill(QColor("#808080"))
    p = QPainter(img)
    it.paint(p, None)
    p.end()
    assert img.pixelColor(5, 5) != QColor("#808080") or img.pixelColor(100, 120).name() in cc.CHART_COLORS   # 흰 카드·조각을 그림
    blues = sum(1 for x in range(0, 360, 4) for y in range(0, 240, 4) if img.pixelColor(x, y).name() == cc.CHART_COLORS[0])
    assert blues > 50                                                       # 첫 조각(중국 60%) 색이 넓게
    it.set_cell_text(1, 1, "70")
    out = item_to_dict(it)
    assert out["chart"] == "pie" and out["table_wh"] == [200, 90]
    assert out["cells"][1][1] == "70"


def test_plain_table_unchanged():
    """chart 칸이 없거나 안 맞는 모양이면 표 그대로(그래프 dict 없음)."""
    from easycad.fileio.document import dict_to_item

    base = {"type": "table", "pos": [0, 0], "scale": 1, "rotation": 0, "z": 1, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None,
            "rect": [0, 0, 200, 90], "rows": 2, "cols": 2, "header": True, "cells": [["이름", "메모"], ["가", "나"]], "col_widths": [0.5, 0.5]}
    assert dict_to_item(base)._chart_dict() is None
    assert dict_to_item({**base, "chart": "col"})._chart_dict() is None   # 숫자 없음 = 표로
