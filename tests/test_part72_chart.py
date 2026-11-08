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


def test_desktop_chart_theme_colors_and_keeps_it():
    """딥모드 디자인 색 순서(`chart_theme`) — 데스크톱도 그 순서로 칠하고, 열었다 저장해도 칸이 남음."""
    from PyQt6.QtGui import QImage, QPainter, QColor
    from easycad.fileio.document import dict_to_item, item_to_dict

    d = {"type": "table", "pos": [0, 0], "scale": 1, "rotation": 0, "z": 1, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None,
         "rect": [0, 0, 360, 240], "rows": 3, "cols": 2, "header": True, "cells": [["나라", "비중"], ["중국", "60"], ["미국", "40"]],
         "col_widths": [0.5, 0.5], "chart": "pie", "table_wh": [200, 90], "chart_theme": "red"}
    it = dict_to_item(d)
    img = QImage(400, 280, QImage.Format.Format_ARGB32)
    img.fill(QColor("#808080"))
    p = QPainter(img)
    it.paint(p, None)
    p.end()
    reds = sum(1 for x in range(0, 360, 4) for y in range(0, 240, 4) if img.pixelColor(x, y).name() == cc.CHART_THEMES["red"][0])
    assert reds > 50                                                        # 첫 조각 = 빨강(기본 파랑이 아님)
    assert item_to_dict(it)["chart_theme"] == "red"
    assert cc.chart_colors({"chart_theme": "없는 이름"}) == cc.CHART_COLORS


def test_plain_table_unchanged():
    """chart 칸이 없거나 안 맞는 모양이면 표 그대로(그래프 dict 없음)."""
    from easycad.fileio.document import dict_to_item

    base = {"type": "table", "pos": [0, 0], "scale": 1, "rotation": 0, "z": 1, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None,
            "rect": [0, 0, 200, 90], "rows": 2, "cols": 2, "header": True, "cells": [["이름", "메모"], ["가", "나"]], "col_widths": [0.5, 0.5]}
    assert dict_to_item(base)._chart_dict() is None
    assert dict_to_item({**base, "chart": "col"})._chart_dict() is None   # 숫자 없음 = 표로



def test_new_kinds_sit_in_their_own_column():
    """누적 막대·막대+꺾은선(2026-11-08) — 항목마다 제 칸에 서고(첫 시도에선 누적 막대가 모두 첫 칸에 겹쳤음 — 웹·데스크톱이 같이 틀려 대조 시험은 통과), 합계는 위에."""
    cells = [["달", "2025", "2026"], ["1월", "10", "12"], ["2월", "11", "15"], ["3월", "9", "16"]]
    st = cc.chart_scene({"type": "table", "rect": [0, 0, 360, 240], "cells": cells, "chart": "stack"})
    xs = sorted({p["x"] for p in st if p["t"] == "rect" and p.get("rx") == 0})
    assert len(xs) == 3 and xs[1] - xs[0] > 50                                # 셋째 줄까지 칸마다 다른 자리
    assert [p["s"] for p in st if p["t"] == "text" and p.get("b") and p["fs"] == 10] == ["22", "26", "25"]
    co = cc.chart_scene({"type": "table", "rect": [0, 0, 360, 240], "cells": cells, "chart": "combo"})
    assert len([p for p in co if p["t"] == "path" and p.get("f")]) == 3      # 막대 = 첫 열만
    assert len([p for p in co if p["t"] == "circle"]) == 3                   # 점 = 마지막 열
    assert cc.chart_why(cc.chart_data({"cells": [["나라", "인구"], ["가", "3"], ["나", "4"]]}), "donut").startswith("도넛은 ")


def test_desktop_paints_new_kinds(tmp_path):
    """데스크톱이 세 모양을 실제로 칠함(계열 색이 넓게)."""
    from PyQt6.QtGui import QImage, QPainter, QColor

    for kind, cells in (("stack", [["달", "가", "나"], ["1월", "10", "12"], ["2월", "11", "15"]]),
                        ("combo", [["달", "가", "나"], ["1월", "10", "12"], ["2월", "11", "15"]]),
                        ("donut", [["나라", "비중"], ["중국", "60%"], ["미국", "40%"]])):
        img = QImage(400, 280, QImage.Format.Format_ARGB32)
        img.fill(QColor("#808080"))
        p = QPainter(img)
        cc.paint_chart(p, {"type": "table", "rect": [0, 0, 360, 240], "cells": cells, "chart": kind})
        p.end()
        img.save(str(tmp_path / f"{kind}.png"))
        blues = sum(1 for x in range(0, 360, 3) for y in range(0, 240, 3) if img.pixelColor(x, y).name() == cc.CHART_COLORS[0])
        assert blues > 40, kind
