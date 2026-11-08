"""그래프 = 표 + 모양(§8 항목66 1단계, 2026-10-25) — 웹 `web/src/next/chart.js`를 그대로 옮김.

표(.ecad `table`)의 웹 칸 `chart`('col'·'stack'·'row'·'line'·'combo'·'pie'·'donut' — 셋은 2026-11-08)가 있으면 표 대신 그래프로 그린다. 숫자는 표 칸 그대로 —
데스크톱에서 표 칸을 고치면 그래프가 따라간다(모양 바꾸기는 웹 속성 카드, 데스크톱은 아직 보이기·보존만).
계산(`chart_data`·`chart_why`·`chart_scene`)은 Qt 없이 웹과 같은 숫자를 내야 한다 — 대조 시험 `tests/test_part72`가
웹이 만든 `tests/fixtures/chart_cases.json`(`tools/export_chart_cases.mjs`)과 비교. 웹을 고치면 여기도 고치고 그 도구를 다시 돌린다.
"""
from __future__ import annotations

import math
import re

CHART_KINDS = [("table", "표"), ("col", "세로 막대"), ("stack", "누적 막대"), ("row", "가로 막대"), ("line", "꺾은선"), ("combo", "막대+꺾은선"), ("pie", "원"), ("donut", "도넛")]
CHART_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MAX_SERIES = len(CHART_COLORS)
# 색 순서(테마) — 같은 8색의 순서만(딥모드 디자인 묶음, 2026-10-25 — 웹 `chart.js` `CHART_THEMES`와 같게). 표 칸 `chart_theme`(없으면 기본)
CHART_THEMES = {"red": ["#e34948", "#eda100", "#e87ba4", "#008300", "#2a78d6", "#eb6834", "#6250d6", "#1baf7a"],
                "cool": ["#2a78d6", "#008300", "#e87ba4", "#eda100", "#e34948", "#6250d6", "#eb6834", "#1baf7a"]}


def chart_colors(it: dict) -> list:
    return CHART_THEMES.get(it.get("chart_theme") or "", CHART_COLORS)
INK = {"title": "#18181b", "text": "#3f3f46", "muted": "#71717a", "grid": "#e4e4e7", "base": "#a1a1aa", "card": "#ffffff", "edge": "#d4d4d8"}
PAD, HEAD, CAT, FS = 14, 24, 20, 11


def _r1(v: float) -> float:   # JS Math.round(v * 10) / 10 — .5는 위로(파이썬 round는 짝수 쪽)
    return math.floor(v * 10 + 0.5) / 10


def _js(n: float) -> str:      # JS 숫자 → 글(정수면 소수점 없음)
    return str(int(n)) if float(n).is_integer() else repr(float(n))


def num_of(s):
    """칸 글 → 숫자(못 읽으면 None) — 웹 `numOf`."""
    t = re.sub(r"(\d),(?=\d{3}(\D|$))", r"\1", str(s if s is not None else "").strip())
    t = re.sub(r"\s+", "", t)
    m = re.match(r"^[^\d+\-.]*([+-]?(?:\d+\.?\d*|\.\d+))([^\d]*)$", t)
    return float(m.group(1)) if m else None


def _unit_of(s) -> str:
    m = re.search(r"\d\s*([^\d\s][^\d]*)$", str(s if s is not None else "").strip())
    return m.group(1).strip() if m else ""


_WIDE = re.compile(r"[ᄀ-ᇿ⺀-鿿가-힯＀-￯]")


def text_w(s, fs: float) -> float:
    return sum(fs if _WIDE.match(ch) else fs * 0.56 for ch in str(s if s is not None else ""))


def fit_text(s, fs: float, max_w: float) -> str:
    s = str(s if s is not None else "")
    if text_w(s, fs) <= max_w:
        return s
    chars = list(s)
    while chars and text_w("".join(chars) + "…", fs) > max_w:
        chars.pop()
    return "".join(chars) + "…" if chars else ""


def chart_data(it: dict) -> dict:
    cells = it.get("cells") or []
    rows = len(cells)
    cols = max([0] + [len(r) for r in cells])

    def at(r, c):
        try:
            v = cells[r][c]
        except (IndexError, TypeError):
            return ""
        return str(v if v is not None else "").strip()

    c0 = 1 if cols >= 2 else 0
    head_cells = [at(0, c) for c in range(c0, cols)]
    filled = [t for t in head_cells if t]
    year = lambda t: re.match(r"^(19|20)\d\d\s*년?$", t) is not None   # noqa: E731
    below = [at(r, c) for r in range(1, rows) for c in range(c0, cols) if at(r, c)]
    head = rows >= 2 and (bool(it.get("header")) or (len(filled) > 0 and (all(num_of(t) is None for t in filled) or (all(year(t) for t in filled) and not all(year(t) for t in below)))))
    r0 = 1 if head else 0
    data_rows = []
    for r in range(r0, rows):
        label = at(r, 0) if c0 else str(r - r0 + 1)
        anyv = any(num_of(at(r, c)) is not None for c in range(c0, cols))
        if (c0 and label) or anyv:
            data_rows.append(r)
    cats = [at(r, 0) if c0 else str(r - r0 + 1) for r in data_rows]
    series = []
    for c in range(c0, cols):
        texts = [at(r, c) for r in data_rows]
        values = [num_of(t) for t in texts]
        if not any(v is not None for v in values):
            continue
        units = [u for u in (_unit_of(t) for t, v in zip(texts, values) if v is not None) if u]
        unit = units[0] if units and all(u == units[0] for u in units) else ""
        series.append({"name": at(0, c) if head else "", "values": values, "texts": texts, "unit": unit})
    return {"cats": cats, "series": series}


_SHARE = re.compile(r"비중|비율|점유|구성비|몫|share|percent|%", re.I)


def chart_why(data: dict, kind: str) -> str:
    if kind == "table":
        return ""
    cats, series = data["cats"], data["series"]
    if not series or not cats:
        return "숫자 칸이 없어요 — 둘째 열부터 숫자를 넣으면 그래프가 돼요"
    if len(series) > MAX_SERIES:
        return f"숫자 열이 {MAX_SERIES}개를 넘으면 색으로 구별이 안 돼요 — 열을 줄여 주세요"
    if kind == "line" and len(cats) < 2:
        return "꺾은선은 항목이 둘 이상일 때만 — 시간 흐름에 써요"
    if kind == "stack":
        if len(series) < 2:
            return "누적 막대는 숫자 열이 둘 이상일 때만 — 항목마다 열을 쌓아 합계를 보여 줘요"
        if any(v is not None and v < 0 for s in series for v in s["values"]):
            return "누적 막대는 음수가 있으면 못 그려요"
    if kind == "combo":
        if len(series) < 2:
            return "막대+꺾은선은 숫자 열이 둘 이상일 때만 — 마지막 열이 꺾은선이 돼요"
        if len(cats) < 2:
            return "막대+꺾은선은 항목이 둘 이상일 때만"
        if len({s["unit"] for s in series if s["unit"]}) > 1:
            return "열마다 단위가 달라 한 눈금에 못 그려요 — 같은 단위의 열만 두세요"
    if kind in ("pie", "donut"):
        nm = "원 그래프는" if kind == "pie" else "도넛은"
        if len(series) != 1:
            return f"{nm} 숫자 열이 하나일 때만 — 전체 중 몫을 보여 줘요"
        v = [x for x in series[0]["values"] if x is not None]
        if any(x < 0 for x in v):
            return f"{nm} 음수가 있으면 못 그려요"
        if len(cats) > MAX_SERIES:
            return f"{nm} 조각 {MAX_SERIES}개까지 — 막대가 더 잘 읽혀요"
        total = sum(v)
        share = bool(_SHARE.search(series[0]["name"])) or (series[0]["unit"] == "%" and abs(total - 100) <= 2)
        if not share or total <= 0:
            return f"{nm} 합쳐서 전체가 되는 몫(비중·비율)에만 써요 — 열 이름에 「비중」을 쓰거나 합이 100인 %면 켜져요"
    return ""


def chart_whys(it: dict) -> dict:
    d = chart_data(it)
    return {k: chart_why(d, k) for k, _ in CHART_KINDS}


def is_chart(it: dict) -> bool:
    k = it.get("chart")
    return it.get("type", "table") == "table" and bool(k) and k != "table" and not chart_why(chart_data(it), k)


def nice_ticks(lo: float, hi: float) -> list:
    lo, hi = min(0.0, lo), max(0.0, hi)
    if hi - lo < 1e-12:
        hi = lo + 1
    raw = (hi - lo) / 4
    p = 10 ** math.floor(math.log10(raw))
    step = next(s for s in (k * p for k in (1, 2, 2.5, 5, 10)) if s >= raw)
    a = math.floor(lo / step + 1e-9) * step
    b = math.ceil(hi / step - 1e-9) * step
    out, v = [], a
    while v <= b + step * 1e-6:
        out.append(round(v, 10) + 0.0)
        v += step
    return out


def _loc(x: float) -> str:   # JS toLocaleString('en-US') — 천 단위 쉼표, 소수 셋째 자리까지
    s = f"{x:,.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def tick_text(v: float) -> str:
    a = abs(v)
    if a >= 1e4:
        return _loc(round(v / 1e4, 0 if a >= 1e5 else 1)) + "만"
    return _loc(round(v, 4))


def _bar_path(x, y, w, h, d) -> str:
    r = max(0.0, min(4.0, w / 2, h / 2))
    X, Y = x + w, y + h
    f = lambda n: _js(_r1(n))   # noqa: E731
    if d == "up":
        return f"M{f(x)},{f(Y)} L{f(x)},{f(y + r)} Q{f(x)},{f(y)} {f(x + r)},{f(y)} L{f(X - r)},{f(y)} Q{f(X)},{f(y)} {f(X)},{f(y + r)} L{f(X)},{f(Y)} Z"
    if d == "down":
        return f"M{f(x)},{f(y)} L{f(X)},{f(y)} L{f(X)},{f(Y - r)} Q{f(X)},{f(Y)} {f(X - r)},{f(Y)} L{f(x + r)},{f(Y)} Q{f(x)},{f(Y)} {f(x)},{f(Y - r)} Z"
    if d == "right":
        return f"M{f(x)},{f(y)} L{f(X - r)},{f(y)} Q{f(X)},{f(y)} {f(X)},{f(y + r)} L{f(X)},{f(Y - r)} Q{f(X)},{f(Y)} {f(X - r)},{f(Y)} L{f(x)},{f(Y)} Z"
    return f"M{f(X)},{f(y)} L{f(X)},{f(Y)} L{f(x + r)},{f(Y)} Q{f(x)},{f(Y)} {f(x)},{f(Y - r)} L{f(x)},{f(y + r)} Q{f(x)},{f(y)} {f(x + r)},{f(y)} Z"


def _val_text(s: dict, k: int) -> str:
    return (s["texts"][k] or "").strip() or tick_text(s["values"][k])


def chart_scene(it: dict) -> list:
    """그릴 조각들 — 웹 `chartScene`과 같은 dict 목록(t·x·y·…)."""
    x, y, w, h = it["rect"]
    kind = it.get("chart")
    data = chart_data(it)
    cats, series = data["cats"], data["series"]
    out = [{"t": "rect", "x": x, "y": y, "w": w, "h": h, "rx": 8, "f": INK["card"], "s": INK["edge"], "sw": 1}]
    COL = chart_colors(it)
    if chart_why(data, kind):
        out.append({"t": "text", "x": x + w / 2, "y": y + h / 2, "s": fit_text("숫자 칸이 없어요", FS, w - 2 * PAD), "fs": FS, "c": INK["muted"], "a": "middle"})
        return out
    L, R, T = x + PAD, x + w - PAD, y + PAD
    round_ = kind in ("pie", "donut")
    if not round_:
        if len(series) == 1:
            if series[0]["name"]:
                out.append({"t": "text", "x": L, "y": T + 8, "s": fit_text(series[0]["name"], 13, R - L), "fs": 13, "b": 1, "c": INK["title"], "a": "start"})
        else:
            share = (R - L) / len(series)
            sx = L
            for j, s in enumerate(series):
                name = fit_text(s["name"] or f"계열 {j + 1}", FS, share - 20)
                if kind == "combo" and j == len(series) - 1:   # 꺾은선 열 = 선 견본
                    out.append({"t": "line", "x1": _r1(sx), "y1": T + 8, "x2": _r1(sx + 10), "y2": T + 8, "s": COL[j], "sw": 2})
                else:
                    out.append({"t": "rect", "x": _r1(sx), "y": T + 3, "w": 10, "h": 10, "rx": 2, "f": COL[j]})
                out.append({"t": "text", "x": _r1(sx + 14), "y": T + 8, "s": name, "fs": FS, "c": INK["text"], "a": "start"})
                sx += 14 + text_w(name, FS) + 16
    top, bottom = T + HEAD, y + h - PAD
    if round_:
        return _pie_scene(out, data, L, top - HEAD + 4, R, bottom, COL, kind == "donut")
    sums = [sum((s["values"][i] or 0) for s in series) for i in range(len(cats))]   # 누적 막대 = 항목마다 합
    allv = sums if kind == "stack" else [v for s in series for v in s["values"] if v is not None]
    ticks = nice_ticks(min(allv), max(allv))
    lo, hi = ticks[0], ticks[-1]

    def tip(c, s, i):
        return f"{c}{' · ' + s['name'] if s['name'] else ''}: {_val_text(s, i)}"

    if kind == "row":
        lab_w = min((R - L) * 0.35, max(text_w(c, FS) for c in cats) + 8)
        pl, pb = L + lab_w, bottom - CAT
        band = (pb - top) / len(cats)
        X = lambda v: pl + ((v - lo) / (hi - lo)) * (R - 6 - pl)   # noqa: E731
        for v in ticks:
            out.append({"t": "line", "x1": _r1(X(v)), "y1": top, "x2": _r1(X(v)), "y2": pb, "s": INK["base"] if v == 0 else INK["grid"], "sw": 1 if v == 0 else 0.75})
            out.append({"t": "text", "x": _r1(X(v)), "y": pb + 10, "s": tick_text(v), "fs": 10, "c": INK["muted"], "a": "middle"})
        inner = band * 0.7
        bh = max(1.0, (inner - 2 * (len(series) - 1)) / len(series))
        labels = len(cats) * len(series) <= 12 and bh >= 10
        for i, c in enumerate(cats):
            cy = top + band * i + band / 2
            out.append({"t": "text", "x": pl - 6, "y": _r1(cy), "s": fit_text(c, FS, lab_w - 8), "fs": FS, "c": INK["text"], "a": "end"})
            for j, s in enumerate(series):
                v = s["values"][i]
                if v is None:
                    continue
                by, x0, x1 = cy - inner / 2 + j * (bh + 2), X(0), X(v)
                out.append({"t": "path", "d": _bar_path(min(x0, x1), by, abs(x1 - x0), bh, "right" if v >= 0 else "left"), "f": COL[j], "tip": tip(c, s, i)})
                if labels:
                    out.append({"t": "text", "x": _r1(x1 + 4 if v >= 0 else x1 - 4), "y": _r1(by + bh / 2), "s": _val_text(s, i), "fs": 10, "c": INK["text"], "a": "start" if v >= 0 else "end"})
        return out
    tw = max(text_w(tick_text(v), 10) for v in ticks) + 6
    pl, pb = L + tw, bottom - CAT
    band = (R - pl) / len(cats)
    Y = lambda v: pb - ((v - lo) / (hi - lo)) * (pb - top - 6)   # noqa: E731
    for v in ticks:
        out.append({"t": "line", "x1": pl, "y1": _r1(Y(v)), "x2": R, "y2": _r1(Y(v)), "s": INK["base"] if v == 0 else INK["grid"], "sw": 1 if v == 0 else 0.75})
        out.append({"t": "text", "x": pl - 6, "y": _r1(Y(v)), "s": tick_text(v), "fs": 10, "c": INK["muted"], "a": "end"})
    for i, c in enumerate(cats):
        out.append({"t": "text", "x": _r1(pl + band * i + band / 2), "y": pb + 11, "s": fit_text(c, FS, band - 4), "fs": FS, "c": INK["text"], "a": "middle"})
    if kind == "stack":   # 아래부터 열 순서로 쌓음, 맨 위 조각만 끝이 둥글고 조각 사이는 흰 선 1px, 위에 합계
        bw = band * 0.6
        units = [s["unit"] for s in series]
        unit = units[0] if units[0] and all(u == units[0] for u in units) else ""
        for i, c in enumerate(cats):
            bx = pl + band * i + (band - bw) / 2
            js = [j for j, s in enumerate(series) if s["values"][i] is not None and s["values"][i] > 0]
            acc = 0.0
            for j in js:
                s = series[j]
                v = s["values"][i]
                y0, y1 = Y(acc), Y(acc + v)
                if j == js[-1]:
                    out.append({"t": "path", "d": _bar_path(bx, y1, bw, y0 - y1, "up"), "f": COL[j], "s": INK["card"], "sw": 1, "tip": tip(c, s, i)})
                else:
                    out.append({"t": "rect", "x": _r1(bx), "y": _r1(y1), "w": _r1(bw), "h": _r1(y0 - y1), "rx": 0, "f": COL[j], "s": INK["card"], "sw": 1, "tip": tip(c, s, i)})
                acc += v
            if js and len(cats) <= 12 and bw >= 16:
                out.append({"t": "text", "x": _r1(bx + bw / 2), "y": _r1(Y(sums[i]) - 8), "s": tick_text(sums[i]) + unit, "fs": 10, "b": 1, "c": INK["text"], "a": "middle"})
        return out
    if kind in ("col", "combo"):   # 막대+꺾은선 = 마지막 열만 꺾은선, 앞 열들은 막대
        bars = series[:-1] if kind == "combo" else series
        inner = band * 0.7
        bw = max(1.0, (inner - 2 * (len(bars) - 1)) / len(bars))
        labels = len(cats) * len(bars) <= 12 and bw >= 16 and kind == "col"
        for i, c in enumerate(cats):
            for j, s in enumerate(bars):
                v = s["values"][i]
                if v is None:
                    continue
                bx, y0, y1 = pl + band * i + (band - inner) / 2 + j * (bw + 2), Y(0), Y(v)
                out.append({"t": "path", "d": _bar_path(bx, min(y0, y1), bw, abs(y1 - y0), "up" if v >= 0 else "down"), "f": COL[j], "tip": tip(c, s, i)})
                if labels:
                    out.append({"t": "text", "x": _r1(bx + bw / 2), "y": _r1(y1 - 8 if v >= 0 else y1 + 8), "s": _val_text(s, i), "fs": 10, "c": INK["text"], "a": "middle"})
        if kind == "col":
            return out
    for j, s in enumerate(series):
        if kind == "combo" and j < len(series) - 1:
            continue
        pts = [None if v is None else [_r1(pl + band * i + band / 2), _r1(Y(v))] for i, v in enumerate(s["values"])]
        d, pen = "", False
        for p in pts:
            if not p:
                pen = False
                continue
            d += f"{' L' if pen else (' M' if d else 'M')}{_js(p[0])},{_js(p[1])}"
            pen = True
        if d:
            out.append({"t": "path", "d": d, "s": COL[j], "sw": 2})
        for i, p in enumerate(pts):
            if not p:
                continue
            out.append({"t": "circle", "cx": p[0], "cy": p[1], "r": 4, "f": COL[j], "s": INK["card"], "sw": 2, "tip": tip(cats[i], s, i)})
            if kind == "line" and len(series) == 1 and len(cats) <= 8:
                out.append({"t": "text", "x": p[0], "y": _r1(p[1] - 12), "s": _val_text(s, i), "fs": 10, "c": INK["text"], "a": "middle"})
    return out


def _pie_scene(out, data, L, top, R, bottom, COL=CHART_COLORS, hole=False):
    """원(hole = 도넛 — 안 반지름 0.58, 가운데에 가장 큰 조각의 몫과 이름)."""
    cats, s = data["cats"], data["series"][0]
    vals = [0.0 if v is None else v for v in s["values"]]
    total = sum(vals)
    list_w = min((R - L) * 0.45, max(text_w(c, FS) for c in cats) + 64)
    if s["name"]:
        out.append({"t": "text", "x": L, "y": top + 4, "s": fit_text(s["name"], 13, R - L), "fs": 13, "b": 1, "c": INK["title"], "a": "start"})
        top += HEAD
    size = min(R - L - list_w - 12, bottom - top)
    x0 = L + max(0.0, (R - L - (size + 20 + list_w)) / 2)   # 원 + 목록 한 덩어리를 가운데(넓은 칸에서 원과 목록 사이가 벌어졌음 — 2026-10-25 사용자)
    cx, cy, rad = x0 + size / 2, (top + bottom) / 2, size / 2
    a = -90.0
    for i, v in enumerate(vals):
        if v <= 0:
            continue
        sweep = (v / total) * 360
        n = max(2, math.ceil(sweep / 2))

        def arc(r, a=a, sweep=sweep, n=n):
            q = []
            for k in range(n + 1):
                t = ((a + (sweep * k) / n) * math.pi) / 180
                q.append([cx + r * math.cos(t), cy + r * math.sin(t)])
            return q
        pts = arc(rad) + arc(rad * 0.58)[::-1] if hole else [[cx, cy]] + arc(rad)
        d = "M" + " L".join(f"{_js(_r1(p[0]))},{_js(_r1(p[1]))}" for p in pts) + " Z"
        out.append({"t": "path", "d": d, "f": COL[i], "s": INK["card"], "sw": 2, "tip": f"{cats[i]}: {_val_text(s, i)} ({round_half_up(v / total * 100)}%)"})
        a += sweep
    if hole and total > 0:   # 가운데 = 가장 큰 조각(같으면 앞 것)
        k = 0
        for i, v in enumerate(vals):
            if v > vals[k]:
                k = i
        in_w = rad * 0.58 * 2 * 0.86
        out.append({"t": "text", "x": _r1(cx), "y": _r1(cy - 7), "s": f"{round_half_up(vals[k] / total * 100)}%", "fs": 18, "b": 1, "c": INK["title"], "a": "middle"})
        out.append({"t": "text", "x": _r1(cx), "y": _r1(cy + 12), "s": fit_text(cats[k], FS, in_w), "fs": FS, "c": INK["muted"], "a": "middle"})
    lx, row_h = x0 + size + 20, 20
    ly0 = cy - (len(cats) * row_h) / 2 + row_h / 2
    for i, c in enumerate(cats):
        ly = _r1(ly0 + i * row_h)
        out.append({"t": "rect", "x": lx, "y": ly - 5, "w": 10, "h": 10, "rx": 2, "f": COL[i]})
        out.append({"t": "text", "x": lx + 14, "y": ly, "s": fit_text(c, FS, list_w - 56), "fs": FS, "c": INK["text"], "a": "start"})
        out.append({"t": "text", "x": lx + list_w - 4, "y": ly, "s": f"{round_half_up(vals[i] / total * 100)}%" if total > 0 else "", "fs": FS, "b": 1, "c": INK["title"], "a": "end"})
    return out


def round_half_up(v: float) -> int:   # JS Math.round
    return math.floor(v + 0.5)


# ── Qt로 그리기(데스크톱 표 paint가 부름) ──
def paint_chart(painter, it: dict) -> None:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainterPath, QPen

    from easycad.canvas.core_web import APP_FAMILIES

    def pen(c, w):
        return QPen(QColor(c), w) if c and w else QPen(Qt.PenStyle.NoPen)

    def brush(c):
        return QBrush(QColor(c)) if c else QBrush(Qt.BrushStyle.NoBrush)

    for p in chart_scene(it):
        t = p["t"]
        if t == "rect":
            painter.setPen(pen(p.get("s"), p.get("sw", 0)))
            painter.setBrush(brush(p.get("f")))
            path = QPainterPath()
            path.addRoundedRect(QRectF(p["x"], p["y"], p["w"], p["h"]), p.get("rx", 0), p.get("rx", 0))
            painter.drawPath(path)
        elif t == "line":
            painter.setPen(pen(p["s"], p["sw"]))
            painter.drawLine(QPointF(p["x1"], p["y1"]), QPointF(p["x2"], p["y2"]))
        elif t == "path":
            pn = pen(p.get("s"), p.get("sw", 0))
            pn.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pn.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pn)
            painter.setBrush(brush(p.get("f")))
            painter.drawPath(_qpath(p["d"], QPainterPath, QPointF))
        elif t == "circle":
            painter.setPen(pen(p["s"], p["sw"]))
            painter.setBrush(brush(p["f"]))
            painter.drawEllipse(QPointF(p["cx"], p["cy"]), p["r"], p["r"])
        else:
            f = QFont()
            f.setFamilies(APP_FAMILIES)
            f.setPixelSize(max(1, round(p["fs"])))
            f.setWeight(QFont.Weight.Bold if p.get("b") else QFont.Weight.Normal)
            fm = QFontMetricsF(f)
            tw = fm.horizontalAdvance(p["s"])
            x0 = p["x"] - (tw / 2 if p["a"] == "middle" else tw if p["a"] == "end" else 0)
            painter.setFont(f)
            painter.setPen(QPen(QColor(p["c"])))
            painter.drawText(QPointF(x0, p["y"] + (fm.ascent() - fm.descent()) / 2), p["s"])   # 웹 dominantBaseline="central"


def _qpath(d: str, QPainterPath, QPointF):
    """M·L·Q·Z만 읽음(chart_scene이 그것만 씀)."""
    path = QPainterPath()
    toks = re.findall(r"[MLQZ]|-?\d+(?:\.\d+)?(?:e-?\d+)?", d)
    i, cmd = 0, None
    while i < len(toks):
        tk = toks[i]
        if tk in "MLQZ":
            cmd = tk
            i += 1
            if cmd == "Z":
                path.closeSubpath()
            continue
        if cmd == "M":
            path.moveTo(float(toks[i]), float(toks[i + 1]))
            i += 2
        elif cmd == "L":
            path.lineTo(float(toks[i]), float(toks[i + 1]))
            i += 2
        elif cmd == "Q":
            path.quadTo(QPointF(float(toks[i]), float(toks[i + 1])), QPointF(float(toks[i + 2]), float(toks[i + 3])))
            i += 4
        else:
            i += 1
    return path
