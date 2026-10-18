"""2026-10-18 웹 칠판이 .ecad에 새 칸을 씀(AI 카드 `fit_text`·`chat_at`·라벨 `align`, 표 `font`·`color`·`pen`).
데스크톱은 아직 그리지 않지만 열었다 저장해도 그대로 돌려 써야 한다 — 안 그러면 웹 카드가 가운데 글로 망가진다(`document.dict_to_item`·`item_to_dict`).
"""
from _shared import *  # noqa: F401,F403
from PyQt6.QtWidgets import QGraphicsScene
from easycad.fileio.document import dict_to_item, insert_items, item_to_dict


def _roundtrip(d):   # 실제 열기 경로(라벨은 씬에 넣은 뒤 붙음) → 저장
    sc = QGraphicsScene()
    return item_to_dict(insert_items(sc, [d])[0])

_BASE = {"pos": [10.0, 20.0], "scale": 1.0, "rotation": 0.0, "z": 3.0, "origin": [0.0, 0.0], "locked": False, "group_id": None, "layer_id": None}


def test_web_card_keys_survive_desktop_save():
    d = dict(_BASE, type="rect", rect=[0.0, 0.0, 340.0, 120.0], pen="#ffd4d4d8", width=1.0, fill="#ffffffff", style=1,
             fit_text=True, chat_at=1792300000000,
             label={"text": "답 글", "color": "#ff1f1f1f", "font": 10.5, "bg": None, "family": "Pretendard", "align": "left"})
    out = _roundtrip(d)
    assert out["fit_text"] is True and out["chat_at"] == 1792300000000
    assert out["label"]["align"] == "left" and out["label"]["text"] == "답 글"


def test_web_table_style_keys_survive_desktop_save():
    d = dict(_BASE, type="table", rows=2, cols=2, header=True, rect=[0.0, 0.0, 80.0, 28.0], cells=[["a", "b"], ["c", "d"]],
             col_widths=[0.5, 0.5], font=9, color="#ff0055aa", pen="#ff888888")
    out = _roundtrip(d)
    assert (out["font"], out["color"], out["pen"]) == (9, "#ff0055aa", "#ff888888")


def test_unknown_keys_are_not_resurrected():
    # 알려진 웹 칸만 돌려 쓴다 — 아무 칸이나 되살리지 않음(데스크톱에서 지운 라벨 등이 되살아나면 안 됨)
    d = dict(_BASE, type="rect", rect=[0.0, 0.0, 50.0, 30.0], pen="#ff000000", width=1.0, fill=None, style=1, mystery=1)
    it = dict_to_item(d)
    out = item_to_dict(it)
    assert "mystery" not in out and "label" not in out
