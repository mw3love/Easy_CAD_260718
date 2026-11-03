"""2026-10-25 사용자 검토 — 웹 「도면으로 베끼기」 서버 쪽(`easycad/ai/board_trace.py` = 데스크톱 베끼기 엔진을 그대로 부름)과
SVG 넣기 = 파일 하나 묶음 하나(데스크톱 `_insert_svgs_at`, 웹 `svgProtos`와 같게). KAIROS는 가짜.
웹 화면(구역 스켈레톤 → 그림 옆 묶음)은 `web/e2e/flow36-review1025.spec.js`, 진짜 KAIROS 실측은 `docs/history/2026-10.md` 끝.
"""
import io
import os
import uuid

from _shared import *  # noqa: F401,F403
from easycad.ai import board_trace

SPEC = {"ops": [
    {"op": "box", "id": "b1", "x1": 10, "y1": 10, "x2": 110, "y2": 60, "label": "TX-A", "font": 16},
    {"op": "text", "x": 200, "y": 20, "text": "연주소", "font": 14},
    {"op": "line", "pts": [[110, 35], [190, 35]], "head": True, "src": "b1"},
]}


def _png(w=400, h=200):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


def _fake(monkeypatch, seen):
    monkeypatch.setattr(board_trace.gw, "_client", lambda key, base, timeout=0: ("client", key))

    def gen(client, photo, *, model, progress=None, **_):
        seen.update(size=photo.size, model=model)
        if progress:
            progress(6, 6, "구역 6/6곳 끝")
        return SPEC, [{"tile": i} for i in range(6)]
    monkeypatch.setattr(board_trace, "generate_ops_tiled", gen)


def test_trace_width_scales_shapes_and_fonts_like_the_board_image(monkeypatch):
    """칠판 그림 폭(width)에 맞춰 좌표·글자 크기가 같은 비율 — 그림 옆에 같은 크기로 놓이게. 선 끝은 상자에 붙은 채."""
    seen, ticks = {}, []
    _fake(monkeypatch, seen)
    out = board_trace.trace("k", _png(400, 200), width=800, base_url="http://x", progress=lambda i, n, t: ticks.append((i, n)))
    assert seen == {"size": (400, 200), "model": board_trace.TRACE_MODEL} and ticks == [(6, 6)]
    assert (out["w"], out["h"]) == (800, 400) and out["skipped"] == 0
    rect = next(d for d in out["items"] if d["type"] == "rect")
    assert rect["rect"] == [20.0, 20.0, 200.0, 100.0]                       # 배율 2(= 800 / 400)
    text = next(d for d in out["items"] if d["type"] == "text")
    assert text["font"] == 14 and rect["label"]["font"] == 16              # SCALE(2)와 같은 배율이라 글자 그대로
    arrow = next(d for d in out["items"] if d["type"] == "sarrow")
    assert arrow["bind1"] == out["items"].index(rect)                       # 연결 그대로(웹 fromEcad가 _id로 바꿈)


def test_trace_smaller_width_shrinks_fonts_too(monkeypatch):
    _fake(monkeypatch, {})
    out = board_trace.trace("k", _png(400, 200), width=200, base_url="http://x")   # 배율 0.5 = SCALE의 1/4
    text = next(d for d in out["items"] if d["type"] == "text")
    assert text["font"] == 4 and out["w"] == 200                            # 14 / 4 = 3.5 → 4(바닥 2 — 작게 놓이면 글자도 작게)


def test_trace_big_photo_is_fitted_before_sending(monkeypatch):
    """폰 원본처럼 큰 그림은 줄여서 보냄(데스크톱 `fit_for_ai` — 게이트웨이 요청 크기 한도)"""
    seen = {}
    _fake(monkeypatch, seen)
    board_trace.trace("k", _png(4000, 2000), base_url="http://x")
    assert max(seen["size"]) <= 1600


def test_desktop_svg_insert_is_one_group_per_file():
    """2026-10-25 사용자: 아이콘은 모여 있어야 뜻이 있음 — 파일 하나 = 묶음 하나(옛 2026-08-04 「묶지 않음」을 뒤집음)"""
    svg = '<svg viewBox="0 0 100 100"><line x1="10" y1="10" x2="90" y2="90"/><rect x="20" y="20" width="30" height="30"/></svg>'
    paths = []
    for _ in range(2):
        p = os.path.join(_TMP, f"grp_{uuid.uuid4().hex}.svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(svg)
        paths.append(p)
    w = CanvasWindow()
    before = set(w._scene.items())
    w._insert_svgs_at(paths, QPointF(0, 0))
    new = [it for it in w._scene.items() if it not in before and getattr(it, "_group_id", None) is not None]
    gids = {it._group_id for it in new}
    assert len(new) == 4 and len(gids) == 2                                 # 파일마다 따로 묶음


# ---- 데스크톱 잠긴 도형 고르기(2026-10-25 — 웹 flow19와 같은 규칙) ----

def _mouse(v, etype, scene_pt, mods=Qt.KeyboardModifier.NoModifier):
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    vp = QPointF(v.mapFromScene(scene_pt))
    t = {"press": QEvent.Type.MouseButtonPress, "release": QEvent.Type.MouseButtonRelease, "move": QEvent.Type.MouseMove}[etype]
    btn = Qt.MouseButton.LeftButton
    e = QMouseEvent(t, vp, vp, btn if etype != "move" else Qt.MouseButton.NoButton, btn, mods)
    {"press": v.mousePressEvent, "release": v.mouseReleaseEvent, "move": v.mouseMoveEvent}[etype](e)


def _two_locked(w):
    a, b = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60), _mk_pen_rect(w, x=300, y=0, ww=100, hh=60)
    w._scene.clearSelection()
    a.setSelected(True); b.setSelected(True)
    w.toggle_lock_selection()
    return a, b


def test_desktop_locked_click_picks_but_never_moves_or_deletes():
    w = CanvasWindow()
    a, b = _two_locked(w)
    assert set(w._locked_sel()) == {a, b} and not w._scene.selectedItems()   # 잠근 뒤에도 골라진 채(🔒)
    w._set_locked_sel([])
    v = w._view
    _mouse(v, "press", QPointF(50, 30)); _mouse(v, "release", QPointF(50, 30))   # 제자리 누르기 = 그것만
    assert w._locked_sel() == [a]
    pos0 = QPointF(a.pos())
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    for k in (Qt.Key.Key_Delete, Qt.Key.Key_Right):
        v.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier))
    assert a.scene() is w._scene and a.pos() == pos0                    # 지우기·방향키 = 막힘
    assert "잠긴 도형" in w.statusBar().currentMessage()
    _mouse(v, "press", QPointF(50, 30)); _mouse(v, "move", QPointF(120, 50)); _mouse(v, "move", QPointF(250, 80)); _mouse(v, "release", QPointF(250, 80))
    assert a.pos() == pos0                                             # 잠긴 것 위에서 끌기 = 끌어 고르기(안 움직임)
    _mouse(v, "press", QPointF(350, 30), Qt.KeyboardModifier.ShiftModifier); _mouse(v, "release", QPointF(350, 30), Qt.KeyboardModifier.ShiftModifier)
    assert set(w._locked_sel()) == {b} or set(w._locked_sel()) == {a, b}   # Shift = 더하기(끌기 뒤 고름이 풀렸으면 b만)


def test_desktop_select_all_then_menu_unlocks_all_at_once():
    w = CanvasWindow()
    a, b = _two_locked(w)
    c = _mk_pen_rect(w, x=0, y=200)
    w._scene.clearSelection(); w._set_locked_sel([])
    w.select_all()
    assert c.isSelected() and set(w._locked_sel()) == {a, b}
    labels = [x.text() for x in w._build_context_menu().actions() if not x.isSeparator()]
    assert labels[0] == "잠금 해제 (2개)"
    w.unlock_locked_sel()
    assert not a._locked and not b._locked and a.isSelected() and b.isSelected()
    w.undo()
    assert a._locked and b._locked                                     # 되돌리기 한 칸


def test_desktop_only_locked_picked_menu_is_unlock_and_toggle():
    w = CanvasWindow()
    a, b = _two_locked(w)
    w._set_locked_sel([a])
    labels = [x.text() for x in w._build_context_menu().actions() if not x.isSeparator()]
    assert labels == ["잠금 해제 (1개)", "잠금 전환\tCtrl+L"]
    w.toggle_lock_selection()                                          # 잠긴 것만 = 풀기
    assert not a._locked and a.isSelected() and b._locked


def test_trace_font_missing_still_scales(monkeypatch):
    """AI가 글자 크기를 안 적어도 기본값(글 13)에 배율 — 작게 놓인 그림 옆에서 글이 상자 밖으로 넘치지 않게(10-25 실조건)"""
    monkeypatch.setattr(board_trace.gw, "_client", lambda key, base, timeout=0: None)
    monkeypatch.setattr(board_trace, "generate_ops_tiled", lambda *a, **k: ({"ops": [{"op": "text", "x": 0, "y": 0, "text": "가"}]}, []))
    out = board_trace.trace("k", _png(400, 200), width=200, base_url="http://x")
    assert out["items"][0]["font"] == 3                                # 13 / 4 = 3.25 → 3


def test_trace_box_fonts_are_evened_and_fit_the_box():
    """상자 글자 크기 고르기(2026-11-02 실검증 — 「마이크로웨이브」는 아주 작고 「송신기」는 상자를 넘쳤음):
    가운데 값 ±15% 안으로, 상자 폭을 넘으면 줄이되 가운데 값의 65%까지만."""
    box = lambda label, font, w=60: {"op": "box", "x1": 0, "y1": 0, "x2": w, "y2": 40, "label": label, "font": font}
    spec = {"ops": [box("스튜디오", 16), box("필터", 15), box("안테나", 16), box("송신기", 40), box("마이크로웨이브", 5), {"op": "text", "x": 0, "y": 0, "text": "메모", "font": 30}]}
    f = [op["font"] for op in board_trace._even_box_fonts(spec)["ops"]]
    assert f[0] == 16 and f[1] == 15 and f[2] == 16      # 고른 것은 그대로(상자 폭 120에 들어감)
    assert f[3] == 18                                    # 40 → 가운데 값 16 × 1.15
    assert f[4] == 11                                    # 5 → 13.6(0.85배) → 일곱 자가 폭 120에 들어가는 11.3으로(65% = 10.4보다 큼)
    assert f[5] == 30                                    # 자유 글자는 안 건드림
    assert board_trace._even_box_fonts({"ops": [box("하나", 40)]})["ops"][0]["font"] == 40   # 상자 하나면 비교할 것이 없음


def test_trace_free_text_inside_unlabeled_box_becomes_its_label():
    """이름 없는 상자 안의 자유 글자 = 그 상자 이름(2026-11-02 실검증 — 따로 놓인 글이라 가운데에 안 오고 크기 고르기에서도 빠졌음).
    상자 밖 글·돌린 글·이미 이름 있는 상자는 그대로, 두 줄이면 위에서 아래로."""
    spec = {"ops": [
        {"op": "box", "x1": 0, "y1": 0, "x2": 100, "y2": 50},
        {"op": "text", "x": 10, "y": 10, "text": "마이크로웨이브", "font": 6},
        {"op": "text", "x": 30, "y": 30, "text": "링크", "font": 6},
        {"op": "text", "x": 10, "y": 60, "text": "- 1Gbps", "font": 10},           # 상자 밑 = 그대로
        {"op": "box", "x1": 200, "y1": 0, "x2": 300, "y2": 50, "label": "송신기", "font": 15},
        {"op": "text", "x": 210, "y": 20, "text": "메모", "font": 10},              # 이름 있는 상자 안 = 그대로
        {"op": "text", "x": 20, "y": 20, "text": "세로", "font": 10, "rot": 90},    # 돌린 글 = 그대로
    ]}
    ops = board_trace._texts_into_boxes(spec)["ops"]
    assert ops[0]["label"] == "마이크로웨이브\n링크" and ops[0]["font"] == 6
    assert [o.get("text") for o in ops if o["op"] == "text"] == ["- 1Gbps", "메모", "세로"]
    assert len(ops) == 5


def test_trace_legend_like_box_keeps_its_texts():
    """줄이 넷 넘거나 긴 글이 든 상자(범례·설명)는 합치지 않음 — 합치면 가운데 정렬돼 선 견본과 어긋났음(2026-11-02 실검증)."""
    spec = {"ops": [{"op": "box", "x1": 0, "y1": 0, "x2": 300, "y2": 200}] + [{"op": "text", "x": 40, "y": 20 + 30 * i, "text": f"선 {i}", "font": 10} for i in range(4)]}
    assert board_trace._texts_into_boxes(spec)["ops"] == spec["ops"]


def test_trace_ops_keep_color_width_dash_fill():
    """베끼기 꾸밈(2026-11-03 사용자 「색·굵기 같은 부가 요소」 — 빨간 수정 글·굵은 전원선·점선 감시선이 다 검정 실선이었음):
    color·w·dash·fill이 .ecad 칸으로. 검정에 가까운 색·흰 칠은 기본(어두운 화면에서 보이게), 이상한 값은 무시."""
    from easycad.fileio.photo_ops import ops_to_sketch, WIDTH
    spec = {"ops": [
        {"op": "box", "id": "b", "x1": 0, "y1": 0, "x2": 50, "y2": 30, "label": "송신기", "color": "#d32f2f", "w": 2, "fill": "#fff3c4"},
        {"op": "box", "x1": 60, "y1": 0, "x2": 90, "y2": 30, "color": "#111111", "fill": "#ffffff", "dash": True, "w": 9},
        {"op": "text", "x": 0, "y": 40, "text": "수정", "color": "#e53935"},
        {"op": "text", "x": 0, "y": 60, "text": "보통", "color": "빨강"},
        {"op": "line", "pts": [[0, 80], [100, 80]], "w": 3},
        {"op": "line", "pts": [[0, 90], [100, 90]], "dash": True, "color": "#1e88e5", "src": "b"},
        {"op": "poly", "pts": [[0, 100], [10, 110]], "dash": True},
        {"op": "circle", "cx": 5, "cy": 5, "r": 3, "color": "#2e7d32"},
    ]}
    sk, skipped = ops_to_sketch(spec, dark=False, scale=1)
    it = sk._items
    assert skipped == 0
    assert it[0]["pen"] == "#ffd32f2f" and it[0]["label"]["color"] == "#ffd32f2f" and it[0]["width"] == WIDTH * 2 and it[0]["fill"] == "#fffff3c4"
    assert it[1]["pen"] == "#ff000000" and it[1]["fill"] is None and it[1]["style"] == 2 and it[1]["width"] == WIDTH * 3   # 굵기는 3배까지
    assert it[2]["color"] == "#ffe53935" and it[3]["color"] == "#ff000000"
    assert it[5]["type"] == "ellipse" and it[5]["pen"] == "#ff2e7d32"                   # 원(선은 맨 뒤로 감)
    lines = [d for d in it if d["type"] == "sarrow"]
    assert lines[0]["width"] == WIDTH * 3 and "style" not in lines[0]
    assert lines[1]["style"] == 2 and lines[1]["color"] == "#ff1e88e5" and "bind1" in lines[1]
    poly = [d for d in it if d["type"] == "polygon"][0]
    assert poly["style"] == 2
    # 꾸밈 없는 옛 결과는 그대로(검정·기본 굵기·실선)
    plain, _ = ops_to_sketch(SPEC, dark=False, scale=1)
    assert all("style" not in d for d in plain._items) and plain._items[0]["width"] == WIDTH


def test_trace_colored_text_inside_box_colors_its_label():
    """상자 안 빨간 글이 상자 이름이 되면 이름도 빨강(색이 섞이면 기본)."""
    from easycad.fileio.photo_ops import ops_to_sketch
    spec = {"ops": [{"op": "box", "x1": 0, "y1": 0, "x2": 100, "y2": 50},
                    {"op": "text", "x": 10, "y": 10, "text": "N+1", "font": 10, "color": "#d32f2f"}]}
    ops = board_trace._texts_into_boxes(spec)["ops"]
    assert ops[0]["tcolor"] == "#d32f2f"
    sk, _ = ops_to_sketch({"ops": ops}, dark=False, scale=1)
    assert sk._items[0]["label"]["color"] == "#ffd32f2f" and sk._items[0]["pen"] == "#ff000000"


def test_trace_seam_join_keeps_colors_apart():
    """구역 경계에서 잘린 선 잇기 — 색이 다르면 안 이음, 굵기만 다르면 이음(구역마다 굵기를 다르게 읽을 수 있음)."""
    from easycad.ai.photo_to_ops import _seam_join
    def piece(tile, pts, cut_at_end, **style):
        ends = [{"cut": not cut_at_end, "node": None, "head": False}, {"cut": cut_at_end, "node": None, "head": False}]
        return {"tile": tile, "base": {"op": "line", **style}, "pts": [list(p) for p in pts], "ends": ends, "closed": False}
    same = _seam_join([piece(0, [[0, 0], [50, 0]], True, w=2), piece(1, [[50, 0], [100, 0]], False)])
    assert len(same) == 1
    apart = _seam_join([piece(0, [[0, 0], [50, 0]], True, color="#d32f2f"), piece(1, [[50, 0], [100, 0]], False)])
    assert len(apart) == 2


def _hits(spec):
    ts = [o for o in spec["ops"] if o["op"] == "text" and not o.get("rot")]
    boxes = [board_trace._text_box(t) for t in ts]
    return sum(1 for i, a in enumerate(boxes) for b in boxes[i + 1:]
               if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]))


def test_trace_untangle_overlapping_side_by_side_texts():
    """설명 글 겹침 줄이기(2026-11-03 사용자 — 「- 10kW」·「VSWR 1.1」, 「- 스튜디오 신호」·「- 1Gbps」): AI가 글 크기를 크게 적어 옆 글과 겹침 →
    설명 글 크기 상한으로 함께 줄여 안 겹치게. 자리는 그대로(작게만), 겹치지 않던 작은 글은 안 줄임."""
    spec = {"ops": [
        {"op": "text", "x": 38, "y": 329, "text": "- 스튜디오 신호", "font": 43},
        {"op": "text", "x": 222, "y": 323, "text": "- 1Gbps", "font": 43},
        {"op": "text", "x": 707, "y": 164, "text": "- 10kW", "font": 40},
        {"op": "text", "x": 795, "y": 174, "text": "VSWR 1.1", "font": 34, "color": "#d32f2f"},
        {"op": "text", "x": 1200, "y": 600, "text": "- 30m", "font": 40},
        {"op": "text", "x": 900, "y": 900, "text": "세로 글", "font": 60, "rot": 90},
    ]}
    assert _hits(spec) == 2
    out = board_trace._untangle_texts(spec)
    assert _hits(out) == 0
    o = out["ops"]
    assert [(t["x"], t["y"]) for t in o[:4]] == [(t["x"], t["y"]) for t in spec["ops"][:4]]   # 자리는 그대로
    assert o[0]["font"] < 43 and o[2]["font"] < 40 and o[3]["color"] == "#d32f2f"
    assert o[5] == spec["ops"][5]                                                              # 돌린 글은 안 건드림
    assert board_trace._untangle_texts({"ops": spec["ops"][4:]})["ops"] == spec["ops"][4:]    # 안 겹치면 그대로


def test_trace_untangle_raises_tiny_texts_and_fits_legend_box():
    """아주 작게 적힌 설명 글은 다른 글과 안 겹치는 만큼 키우고(「- 자동 절체」 25 → 상한 쪽), 범례 틀 안 글이 오른쪽 변을 넘으면 맞게 줄임."""
    spec = {"ops": [
        {"op": "text", "x": 0, "y": 0, "text": "- 48kHz/24bit", "font": 40},
        {"op": "text", "x": 150, "y": 0, "text": "- MPEG-2", "font": 40},
        {"op": "text", "x": 600, "y": 300, "text": "- 자동 절체", "font": 20},
        {"op": "box", "x1": 1000, "y1": 0, "x2": 1260, "y2": 200},
        {"op": "text", "x": 1050, "y": 20, "text": "신호선 (RF/오디오/데이터)", "font": 30},
        {"op": "text", "x": 1050, "y": 80, "text": "점선", "font": 30},
    ]}
    out = board_trace._untangle_texts(spec)["ops"]
    assert _hits({"ops": out}) == 0
    cap = out[1]["font"]
    assert 20 < out[2]["font"] <= cap                                       # 작은 글은 키움(상한까지)
    x0, _, x1, _ = board_trace._text_box(out[4])
    assert x1 <= 1260 and 18 <= out[4]["font"] < 30                             # 범례 글은 틀 안으로(처음 크기의 60%까지)
    assert out[5]["font"] == spec["ops"][5]["font"] or out[5]["font"] <= 30


def test_trace_clear_lines_box_names_scraps_icons_and_edge_strokes():
    """글과 그림 겹침(2026-11-03 사용자): 상자 이름 위 작은 낙서(「송신기#1」의 「#」)는 빼고, 이름을 덮는 아이콘(「감시 서버」 모니터)이 있으면
    이름을 빈 쪽 자유 글로 옮기고(아이콘에 붙은 작은 조각 = 받침은 남김), 테두리를 한 번 더 그은 겹선은 그림으로 안 침(「UPS · 발전기」)."""
    spec = {"ops": [
        {"op": "box", "x1": 0, "y1": 0, "x2": 120, "y2": 40, "label": "송신기 1", "font": 20},
        {"op": "poly", "pts": [[58, 14], [62, 10], [64, 16]]},                                   # 이름 위 낙서
        {"op": "box", "x1": 200, "y1": 0, "x2": 400, "y2": 60, "label": "감시 서버", "font": 30},
        {"op": "poly", "pts": [[330, 12], [390, 12], [390, 44], [330, 44]], "closed": True},     # 모니터
        {"op": "poly", "pts": [[356, 44], [356, 50], [364, 50]]},                               # 받침(모니터에 붙음)
        {"op": "box", "x1": 500, "y1": 0, "x2": 700, "y2": 60, "label": "UPS · 발전기", "font": 30},
        {"op": "poly", "pts": [[600, 2], [698, 2], [698, 58]]},                                   # 테두리 겹선
    ]}
    out = board_trace._clear_lines(spec)["ops"]
    polys = [o for o in out if o["op"] == "poly"]
    assert len(polys) == 3 and [[58, 14], [62, 10], [64, 16]] not in [p["pts"] for p in polys]   # 낙서만 빠짐
    assert out[0]["label"] == "송신기 1"
    server = [o for o in out if o["op"] == "box"][1]
    assert "label" not in server
    moved = [o for o in out if o["op"] == "text" and o["text"] == "감시 서버"][0]
    x0, y0, x1, y1 = board_trace._text_box(moved)
    assert 200 <= x0 and x1 <= 330 and 0 <= y0 and y1 <= 60                                   # 모니터 왼쪽 빈 곳 안
    assert [o for o in out if o["op"] == "box"][2]["label"] == "UPS · 발전기"                   # 겹선 상자는 그대로


def test_trace_clear_lines_moves_text_off_a_line_and_evens_repeats():
    """세로선이 글 가운데를 지나면 옆으로 비킴(옆 글과 겹치면 조금 줄여서), 같은 글이 여러 번이면 크기를 같게(「VSWR 1.1」 셋)."""
    spec = {"ops": [
        {"op": "text", "x": 707, "y": 164, "text": "- 10kW", "font": 28},
        {"op": "text", "x": 795, "y": 174, "text": "VSWR 1.1", "font": 34},
        {"op": "line", "pts": [[880, 126], [881, 294]]},
        {"op": "text", "x": 795, "y": 474, "text": "VSWR 1.1", "font": 34},
    ]}
    out = board_trace._clear_lines(spec)["ops"]
    v = out[1]
    r = board_trace._text_box(v)
    assert r[2] < 880 and not board_trace._meet(r, board_trace._text_box(out[0]))              # 선 왼쪽으로, 「- 10kW」와 안 겹침
    assert out[3]["font"] == v["font"] < 34                                                    # 같은 글 = 같은 크기
    plain = {"ops": [{"op": "text", "x": 0, "y": 0, "text": "글", "font": 20}, {"op": "line", "pts": [[100, 0], [100, 50]]}]}
    assert board_trace._clear_lines(plain)["ops"] == plain["ops"]                              # 안 겹치면 그대로


def test_desktop_multiline_box_label_centers_each_line_and_reads_web_ha():
    """데스크톱 상자 이름 여러 줄 = 줄마다 가운데(웹 `CenterLabel`과 같게 — 2026-11-03, 전엔 「마이크로웨이브 / 링크」의 「링크」가 왼쪽에 붙음),
    웹 `label.ha`(왼쪽·오른쪽)는 도형 안 여백 끝에 붙음. 저장하면 `ha`는 그대로 돌아감."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QGraphicsScene
    from easycad.fileio.document import insert_items, item_to_dict
    base = {"type": "rect", "pos": [0, 0], "scale": 1, "rotation": 0, "z": 0, "origin": [0, 0], "rect": [0, 0, 200, 80],
            "pen": "#ff000000", "width": 2, "fill": None}
    sc = QGraphicsScene()
    it, left = insert_items(sc, [{**base, "label": {"text": "마이크로웨이브\n링크", "color": "#ff000000", "font": 12, "bg": None}},
                                 {**base, "label": {"text": "왼쪽", "color": "#ff000000", "font": 12, "bg": None, "ha": "left"}}])
    lbl = it._label
    assert lbl.document().defaultTextOption().alignment() & Qt.AlignmentFlag.AlignHCenter
    lay = lbl.document().begin().next().layout().lineAt(0)
    first = lbl.document().begin().layout().lineAt(0)
    mid = lambda ln: ln.cursorToX(ln.textStart())[0] + ln.naturalTextWidth() / 2   # cursorToX = 정렬이 반영된 줄 시작
    assert abs(mid(lay) - mid(first)) < 1.0                                   # 둘째 줄도 첫 줄과 같은 가운데
    box = lbl.mapRectToParent(lbl.boundingRect())
    assert abs(box.center().x() - 100) < 3                                    # 이름 덩어리는 상자 가운데
    assert left._label.pos().x() < 30                                          # 여백 끝(폭 200 × 0.85 → 왼쪽 15)
    assert item_to_dict(left)["label"]["ha"] == "left"


def test_trace_clear_lines_pushes_text_past_legend_sample_arrow():
    """범례 견본 화살표 끝이 글 머리에 걸리면(2026-11-03 진짜 단추 시험 — 「신호선 (RF/오디오/데이터)」만 화살표 끝보다 앞에서 시작) 글을 화살표 끝 뒤로.
    이미 화살표 뒤에서 시작하는 글·화살표가 가리키는 글(세로선)은 그대로."""
    spec = {"ops": [
        {"op": "line", "pts": [[0, 100], [70, 100]], "head": True},
        {"op": "text", "x": 40, "y": 92, "text": "신호선 (RF/오디오/데이터)", "font": 16},   # 화살표(y 100)가 글 줄 가운데
        {"op": "line", "pts": [[0, 140], [70, 140]], "head": True},
        {"op": "text", "x": 80, "y": 128, "text": "감시 신호 (이더넷)", "font": 18},
        {"op": "line", "pts": [[300, 0], [300, 60]], "head": True},
        {"op": "text", "x": 280, "y": 62, "text": "- 50Ω", "font": 16},
    ]}
    out = board_trace._clear_lines(spec)["ops"]
    assert out[1]["x"] > 70                                     # 화살표 끝(70) 뒤로
    assert out[3]["x"] == 80 and out[5]["x"] == 280             # 그 밖은 그대로
