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


def test_web_code_runs_survive_desktop_save():
    """AI 카드 안 코드 줄(2026-10-18 — .ecad runs 여섯째 칸 = 고정폭)은 데스크톱이 Consolas로 보이고, 저장하면 다시 고정폭 표시로"""
    text = "합:\ndef add(a, b):\n    return a + b"
    d = dict(_BASE, type="rect", rect=[0.0, 0.0, 340.0, 120.0], pen="#ffd4d4d8", width=1.0, fill="#ffffffff", style=1, fit_text=True,
             label={"text": text, "color": "#ff1f1f1f", "font": 10.5, "bg": None, "align": "left",
                    "runs": [[0, 2, "#ff0000", True], [3, 14, None, False, None, True], [18, 16, None, False, None, True]]})
    out = _roundtrip(d)
    runs = out["label"]["runs"]
    mono = [text[s:s + n] for s, n, *rest in runs if len(rest) > 3 and rest[3]]
    assert mono == ["def add(a, b):", "    return a + b"]
    assert [0, 2, "#ff0000", True] in runs                       # 다른 조각은 그대로


def test_web_legend_marks_survive_desktop_save():
    """웹 범례(2026-10-18)는 보통 선·글·네모 — 데스크톱에서도 그대로 보이고, 다시 모을 때 쓰는 표시(legend·legend_key)는 저장해도 남는다"""
    frame = dict(_BASE, type="rect", rect=[0.0, 0.0, 200.0, 80.0], pen="#ffa1a1aa", width=1.0, fill=None, style=1, radius=8, legend=1.5, group_id="legend-ab12")
    line = dict(_BASE, type="line", line=[0.0, 0.0, 44.0, 0.0], pen="#ffff7f00", width=2.9, style=1, legend_key="ffff7f00|1|2.9", group_id="legend-ab12")
    text = dict(_BASE, type="text", text="SDI 케이블", color="#ff1f1f1f", font=10, bg=None, legend_key="ffff7f00|1|2.9", group_id="legend-ab12")
    sc = QGraphicsScene()
    outs = [item_to_dict(it) for it in insert_items(sc, [frame, line, text])]
    assert outs[0]["legend"] == 1.5 and outs[1]["legend_key"] == outs[2]["legend_key"] == "ffff7f00|1|2.9"
    assert outs[2]["text"] == "SDI 케이블" and all(o["group_id"] == "legend-ab12" for o in outs)



def test_web_memo_survives_desktop_save():
    """웹 메모(2026-10-18 — 줄마다 제목·목록·할 일·코드)는 데스크톱이 줄 글을 적은 둥근 네모로 열고, 저장하면 다시 memo로(줄·바탕색·답 시각 그대로, 보여 주려던 라벨은 뺌)"""
    lines = [{"k": "h2", "t": "회의"}, {"k": "todo", "t": "견적", "done": True}, {"k": "ol", "t": "하나"}, {"k": "ol", "t": "둘"},
             {"k": "ul", "t": "안", "lv": 1}, {"k": "code", "t": "  x = 1"}, {"k": "p", "t": "끝", "runs": [[0, 1, "#ff0000", True]]}]
    d = dict(_BASE, type="memo", rect=[0.0, 0.0, 340.0, 200.0], fill="#fffff8c5", lines=lines, chat_at=1792300000000)
    sc = QGraphicsScene()
    it = insert_items(sc, [d])[0]
    assert it._label.toPlainText() == "## 회의\n☑ 견적\n1. 하나\n2. 둘\n  • 안\n  x = 1\n끝"
    out = item_to_dict(it)
    assert out["type"] == "memo" and out["lines"] == lines and out["fill"] == "#fffff8c5" and out["chat_at"] == 1792300000000
    assert "label" not in out and out["rect"] == [0.0, 0.0, 340.0, 200.0]


def test_web_card_new_keys_and_legend_survive_desktop_save():
    """2026-10-19 — 웹 카드 새 칸(설명·아이콘·페이지 배율)과 범례 2판(표 모양, 줄은 웹이 도면에서 모음)도 데스크톱을 거쳐 그대로"""
    w = dict(_BASE, type="web", rect=[0.0, 0.0, 640.0, 460.0], url="https://ko.wikipedia.org/", title="위키", frameable=True,
             desc="설명", icon="data:image/png;base64,AAAA", zoom=0.5)
    out = _roundtrip(w)
    assert (out["desc"], out["icon"], out["zoom"]) == ("설명", "data:image/png;base64,AAAA", 0.5)
    rows = [{"key": "ff34c759|1|5", "color": "#ff34c759", "style": 1, "width": 5, "count": 2, "arrow": True}]
    lg = dict(_BASE, type="legend", rect=[0.0, 0.0, 256.0, 87.0], rows=rows, names={"ff34c759|1|5": "주 신호선"}, title="범례")
    sc = QGraphicsScene()
    it = insert_items(sc, [lg])[0]
    assert it._label.toPlainText() == "범례\n주 신호선 · 실선 · 5px"   # 데스크톱에선 줄 글이 보임
    out = item_to_dict(it)
    assert out["type"] == "legend" and out["rows"] == rows and out["names"] == lg["names"] and out["title"] == "범례" and "label" not in out


def test_web_deco_runs_survive_desktop_save():
    """2026-10-19 — 웹 드래그 꾸미기 막대의 기울임·밑줄·취소선(.ecad runs 일곱째 칸 'i'·'u'·'s')은 데스크톱이 Qt 글자 서식으로 보이고, 저장하면 그대로"""
    from easycad.fileio.document import insert_items
    text = "가나다 라마바 차카타"
    d = dict(_BASE, type="text", text=text, color="#ff111111", font=12, bg=None,
             runs=[[0, 3, None, False, None, False, "is"], [4, 3, "#337ea9", False], [8, 3, None, True, None, False, "u"]])
    sc = QGraphicsScene()
    it = insert_items(sc, [d])[0]
    from PyQt6.QtGui import QTextCursor
    c = QTextCursor(it.document()); c.setPosition(1)
    assert c.charFormat().fontItalic() and c.charFormat().fontStrikeOut()   # 데스크톱에서도 기울임·취소선
    out = item_to_dict(it)
    assert [0, 3, None, False, None, False, "is"] in out["runs"] and [8, 3, None, True, None, False, "u"] in out["runs"]
    assert [4, 3, "#337ea9", False] in out["runs"]
