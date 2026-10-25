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
    assert text["font"] == 6 and out["w"] == 200                            # 14 / 4 → 4 → 바닥 6


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
