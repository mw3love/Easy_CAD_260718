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
             col_widths=[0.5, 0.5], font=9, color="#ff0055aa", pen="#ff888888",
             cell_styles={"0,1": {"bold": True, "fill": "#55e8c15a"}}, cell_runs={"1,0": [[0, 1, "#ff3b30", False]]}, row_heights=[0.3, 0.7])
    out = _roundtrip(d)
    assert (out["font"], out["color"], out["pen"]) == (9, "#ff0055aa", "#ff888888")
    assert out["cell_styles"] == {"0,1": {"bold": True, "fill": "#55e8c15a"}} and out["cell_runs"] == {"1,0": [[0, 1, "#ff3b30", False]]}
    assert out["row_heights"] == [0.3, 0.7]


def test_unknown_keys_are_not_resurrected():
    # 알려진 웹 칸만 돌려 쓴다 — 아무 칸이나 되살리지 않음(데스크톱에서 지운 라벨 등이 되살아나면 안 됨)
    d = dict(_BASE, type="rect", rect=[0.0, 0.0, 50.0, 30.0], pen="#ff000000", width=1.0, fill=None, style=1, mystery=1)
    it = dict_to_item(d)
    out = item_to_dict(it)
    assert "mystery" not in out and "label" not in out


def test_rect_radius_roundtrip_and_paint():
    # 2026-10-18 네모 모서리 둥글기(.ecad `radius`) — 데스크톱도 그리고(둥근 클릭 영역) 저장한다
    d = dict(_BASE, type="rect", rect=[0.0, 0.0, 100.0, 60.0], pen="#ff000000", width=1.0, fill="#ffffffff", style=1, radius=12)
    sc = QGraphicsScene()
    it = insert_items(sc, [d])[0]
    assert it._radius == 12 and item_to_dict(it)["radius"] == 12
    from PyQt6.QtCore import QPointF
    assert not it._base_shape().contains(QPointF(0.5, 0.5))      # 둥근 모서리 바깥은 클릭 안 됨
    assert it._base_shape().contains(QPointF(50, 30))
    plain = insert_items(sc, [dict(d, radius=None)])[0]
    assert "radius" not in item_to_dict(plain)                   # 각진 네모는 키 생략(하위호환)


def test_web_frame_survives_desktop_save():
    """웹 프레임(2026-10-18)은 데스크톱이 점선 네모로 열고, 저장하면 다시 frame으로 — 이름·번호·비율·같이 움직임 그대로"""
    d = dict(_BASE, type="frame", rect=[0.0, 0.0, 640.0, 360.0], name="표지", no=2, ratio="16:9", magnet=False)
    out = _roundtrip(d)
    assert out["type"] == "frame" and out["rect"] == [0.0, 0.0, 640.0, 360.0]
    assert (out["name"], out["no"], out["ratio"], out["magnet"]) == ("표지", 2, "16:9", False)


def test_web_card_survives_desktop_save():
    """웹 카드(2026-10-18 — 유튜브·웹페이지)는 데스크톱이 제목·주소를 적은 네모로 열고, 저장하면 다시 web으로(보여 주려고 붙인 라벨은 뺌)"""
    d = dict(_BASE, type="web", rect=[0.0, 0.0, 480.0, 310.0], url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", title="노래",
             embed="https://www.youtube.com/embed/dQw4w9WgXcQ", thumb="data:image/jpeg;base64,AAAA", frameable=True)
    sc = QGraphicsScene()
    it = insert_items(sc, [d])[0]
    assert it._label is not None and "youtube.com" in it._label.toPlainText()   # 데스크톱에선 주소가 보임
    out = item_to_dict(it)
    assert out["type"] == "web" and out["rect"] == [0.0, 0.0, 480.0, 310.0] and "label" not in out
    assert (out["url"], out["title"], out["embed"], out["thumb"], out["frameable"]) == (d["url"], "노래", d["embed"], d["thumb"], True)
