"""웹 칠판 메모를 데스크톱에서 그리고 고친다(§8 항목61 ④-3, 2026-10-22).

줄 배치는 웹 `web/src/next/render.jsx` `memoLayout`·`layoutText`, 줄 종류·치수는 `memo.js`(MEMO·MEMO_KIND)를 옮김 —
고치는 모습(웹 memoedit.jsx)과 그림이 같은 치수를 읽는 것처럼 여기도 같은 숫자. 웹을 고치면 여기도.
메모 칸: { rect, fill, pen?, fold?, lines: [{ k, t, runs?, done?, lv?, rows?, header?, cw? }] }
  k = p·h1·h2·h3·ul·ol·todo·code·quote·hr·table, runs = [시작, 길이, 색, 굵게, 배경?, 고정폭?, 꾸밈?]
"""
import re

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainterPath, QPen

MEMO = {"W": 340, "PAD": 14, "LPAD": 26, "GAP": 5, "INDENT": 18, "QUOTE": 14, "HR": 9, "CELL": 4}
MEMO_KIND = {
    "p": {"pt": 10.5}, "ul": {"pt": 10.5}, "ol": {"pt": 10.5}, "todo": {"pt": 10.5}, "quote": {"pt": 10.5},
    "h1": {"pt": 16, "bold": True, "gap": 10}, "h2": {"pt": 13.5, "bold": True, "gap": 8}, "h3": {"pt": 11.5, "bold": True, "gap": 6},
    "code": {"pt": 10, "mono": True}, "hr": {"pt": 10.5},
}
LISTY = {"ul", "ol", "todo"}
MUTED = "#8a8f98"
LINK = "#2f80ed"
CODE_BAND = QColor(127, 127, 127, round(0.14 * 255))
PT = 96 / 72
TEXT_MARGIN = 4
BOARD_M = {"ascent": 0.95, "lineSpacing": 1.193}   # 웹 geom.js METRICS.board(Pretendard)
FOLD_N = 6                                          # 웹 MEMO_FOLD_N
MONO_FAMILIES = ["Consolas", "Cascadia Mono", "D2Coding", "Malgun Gothic"]
_URL = re.compile(r"https?://[^\s<>\"'()\[\]]+")

_FONTS = {}


def _board_families():
    from easycad.fonts import board_family
    fam = board_family()
    return [fam, "Malgun Gothic"] if fam else ["Malgun Gothic"]


def font(px: float, weight: int = 400, mono: bool = False, italic: bool = False) -> QFont:
    key = (round(px, 3), weight, mono, italic)
    f = _FONTS.get(key)
    if f is None:
        f = QFont()
        f.setFamilies(MONO_FAMILIES if mono else _board_families())
        f.setPointSizeF(px / PT)   # 96dpi에서 px와 같음(웹 fontSize = px)
        f.setWeight(QFont.Weight(400 if mono else weight))
        f.setItalic(italic)
        _FONTS[key] = f
    return f


def _width(part: dict, px: float, weight: int) -> float:
    w = 400 if part.get("mono") else max(700, weight) if part.get("bold") else weight
    return QFontMetricsF(font(px, w, part.get("mono", False), "i" in (part.get("deco") or ""))).horizontalAdvance(part["text"])


def url_spans(text: str):
    out = []
    for m in _URL.finditer(text or ""):
        u = m.group(0).rstrip(".,;:!?")
        if len(u) > 8:
            out.append((m.start(), len(u), u))
    return out


def runs_to_lines(text: str, runs, links=None):
    """글 + runs → 줄마다 조각(같은 꾸밈끼리) — 웹 geom.js runsToLines."""
    n = len(text)
    attr = [None] * n
    for r in runs or []:
        s, ln = int(r[0]), int(r[1])
        a = {"color": r[2] if len(r) > 2 else None, "bold": bool(r[3]) if len(r) > 3 else False,
             "bg": r[4] if len(r) > 4 else None, "mono": bool(r[5]) if len(r) > 5 else False, "deco": (r[6] if len(r) > 6 else "") or ""}
        for i in range(max(0, s), min(n, s + ln)):
            attr[i] = a
    for s, ln, url in links or []:
        for i in range(max(0, s), min(n, s + ln)):
            attr[i] = {**(attr[i] or {}), "link": url}
    def sig(a):
        a = a or {}
        return a.get("color"), bool(a.get("bold")), str(a.get("bg")), bool(a.get("mono")), a.get("deco") or "", a.get("link")

    same = lambda a, b: sig(a) == sig(b)   # noqa: E731
    lines, pos = [], 0
    for line in text.split("\n"):
        parts, i = [], 0
        while i < len(line):
            a = attr[pos + i]
            j = i + 1
            while j < len(line) and same(attr[pos + j], a):
                j += 1
            a = a or {}
            parts.append({"text": line[i:j], "color": a.get("color"), "bold": bool(a.get("bold")), "bg": a.get("bg"),
                          "mono": bool(a.get("mono")), "deco": a.get("deco") or "", "link": a.get("link")})
            i = j
        lines.append(parts)
        pos += len(line) + 1
    return lines


def _wrap(parts, max_w, wof):
    """한 줄을 폭 안으로 — 낱말 단위, 한 낱말이 폭보다 길면 글자 단위(웹 wrapParts)."""
    toks = [{**p, "text": t} for p in parts for t in re.split(r"(\s+)", p["text"]) if t]
    out, cur = [[]], 0.0
    for t in toks:
        sp, w = t["text"].isspace(), wof(t)
        if sp:
            if cur > 0 or t.get("mono"):
                out[-1].append(t)
                cur += w
            continue
        if cur > 0 and cur + w > max_w:
            while out[-1] and out[-1][-1]["text"].isspace():
                out[-1].pop()
            out.append([])
            cur = 0.0
        if w <= max_w:
            out[-1].append(t)
            cur += w
            continue
        acc = ""
        for ch in t["text"]:
            nx = acc + ch
            if cur + wof({**t, "text": nx}) > max_w and (acc or cur > 0):
                if acc:
                    out[-1].append({**t, "text": acc})
                    cur += wof({**t, "text": acc})
                out.append([])
                cur, acc = 0.0, ch
            else:
                acc = nx
        if acc:
            out[-1].append({**t, "text": acc})
            cur += wof({**t, "text": acc})
    return out


def layout_text(text, runs, px, weight=400, max_w=0.0, links=None):
    """글 배치 — 줄마다 조각 위치(웹 layoutText, family = board)."""
    wof = lambda p: _width(p, px, weight)   # noqa: E731
    src = runs_to_lines(text or "", runs, links)
    if max_w > 0:
        src = [ln for parts in src for ln in _wrap(parts, max_w, wof)]
    lines = []
    for parts in src:
        x, placed = 0.0, []
        for p in parts:
            w = wof(p)
            placed.append({**p, "x": x, "w": w})
            x += w
        lines.append({"parts": placed, "w": x, "code": bool(parts) and all(p.get("mono") for p in parts)})
    return {"lines": lines, "w": max([0.0] + [l["w"] for l in lines]), "h": len(lines) * BOARD_M["lineSpacing"] * px,
            "px": px, "weight": weight, "max_w": max_w}


def ol_numbers(lines):
    nums, cnt = {}, []
    for i, ln in enumerate(lines or []):
        lv = int(ln.get("lv") or 0)
        if ln.get("k") == "ol":
            del cnt[lv + 1:]
            cnt += [0] * (lv + 1 - len(cnt))
            cnt[lv] += 1
            nums[i] = cnt[lv]
        elif ln.get("k") in LISTY:
            del cnt[lv + 1:]
            cnt += [0] * (lv + 1 - len(cnt))
            cnt[lv] = 0
        else:
            cnt.clear()
    return nums


def _clip_mono(t, px, max_w):
    fm = QFontMetricsF(font(px, 400, True))
    if fm.horizontalAdvance(t) <= max_w:
        return t
    lo, hi = 0, len(t)
    while lo < hi:
        m = (lo + hi + 1) // 2
        if fm.horizontalAdvance(t[:m] + "…") <= max_w:
            lo = m
        else:
            hi = m - 1
    return t[:lo] + "…"


def memo_layout(d: dict, w: float):
    """메모 안 줄 배치(아이템 rect 왼쪽 위 기준) — 웹 memoLayout과 같은 rows·h."""
    all_ = d.get("lines") or [{"k": "p", "t": ""}]
    folded = d.get("fold") is True and len(all_) > FOLD_N + 1
    lines = all_[:FOLD_N] if folded else all_
    inner = max(20.0, w - MEMO["LPAD"] - MEMO["PAD"])
    nums, rows = ol_numbers(all_), []
    y = float(MEMO["PAD"])
    for i, ln in enumerate(lines):
        k = ln.get("k") or "p"
        K = MEMO_KIND.get(k, MEMO_KIND["p"])
        px = K["pt"] * PT
        prev = lines[i - 1] if i > 0 else None
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        join_prev = i > 0 and k in ("code", "quote") and prev.get("k") == k
        join_next = bool(nxt) and k in ("code", "quote") and nxt.get("k") == k
        if i > 0 and not join_prev:
            y += K.get("gap", MEMO["GAP"])
        if not join_prev:
            y += TEXT_MARGIN
        if k == "hr":
            h = MEMO["HR"] * 2
            rows.append({"ln": ln, "i": i, "x": MEMO["LPAD"], "y": y - TEXT_MARGIN, "h": h, "cy": y - TEXT_MARGIN + h / 2, "hr": True})
            y += h - TEXT_MARGIN
            continue
        if k == "table":
            rws = ln.get("rows") or [[""]]
            n = max(1, *[len(r) for r in rws])
            cw = ln.get("cw") if len(ln.get("cw") or []) == n else [1 / n] * n
            cpx = MEMO_KIND["p"]["pt"] * PT
            xs = [0.0]
            for f in cw:
                xs.append(xs[-1] + f * inner)
            ty, cells, row_y = 0.0, [], [0.0]
            for ri, r in enumerate(rws):
                hd = bool(ln.get("header")) and ri == 0
                lays = [layout_text(r[c] if c < len(r) else "", None, cpx, 700 if hd else 400,
                                    max(10.0, xs[c + 1] - xs[c] - 2 * MEMO["CELL"] - 2 * TEXT_MARGIN)) for c in range(n)]
                rh = max(l["h"] for l in lays) + 2 * TEXT_MARGIN + 2 * MEMO["CELL"]
                cells += [{"lay": lay, "x": xs[c] + MEMO["CELL"], "y": ty + MEMO["CELL"]} for c, lay in enumerate(lays)]
                ty += rh
                row_y.append(ty)
            rows.append({"ln": ln, "i": i, "x": MEMO["LPAD"], "y": y - TEXT_MARGIN, "h": ty, "cy": y - TEXT_MARGIN + ty / 2,
                         "table": {"xs": xs, "row_y": row_y, "cells": cells, "w": inner}})
            y += ty - TEXT_MARGIN
            continue
        ind = (int(ln.get("lv") or 0) + 1) * MEMO["INDENT"] if k in LISTY else MEMO["QUOTE"] if k == "quote" else 0
        links = None if k == "code" or ln.get("nolink") else url_spans(ln.get("t") or "")
        room = max(10.0, inner - ind - 2 * TEXT_MARGIN)
        if K.get("mono"):
            ct = _clip_mono(ln.get("t") or "", px, room)
            lay = layout_text(ct, [[0, len(ct), None, False, None, True]], px, 400, 0)
        else:
            lay = layout_text(ln.get("t") or "", ln.get("runs"), px, 700 if K.get("bold") else 400, room, links or None)
        x = MEMO["LPAD"] + ind
        lh = BOARD_M["lineSpacing"] * px
        cy = y + TEXT_MARGIN + lh / 2
        marker = "•◦▪"[int(ln.get("lv") or 0) % 3] if k == "ul" else f"{nums.get(i)}." if k == "ol" else None
        box = {"x": x - MEMO["INDENT"] + 2, "y": cy - TEXT_MARGIN - px * 0.45, "s": px * 0.9} if k == "todo" else None
        rows.append({"ln": ln, "i": i, "x": x, "y": y - TEXT_MARGIN, "lay": lay, "px": px, "marker": marker, "box": box,
                     "cy": cy - TEXT_MARGIN, "lh": lh, "join_prev": join_prev, "join_next": join_next})
        y += lay["h"] + (0 if join_next else TEXT_MARGIN)
    if folded or (d.get("fold") is False and len(all_) > FOLD_N + 1):
        t = f"… {len(all_) - FOLD_N}줄 더 — 웹 칠판에서 펼치기" if folded else "▴ 접기"
        px = MEMO_KIND["p"]["pt"] * PT
        lh = BOARD_M["lineSpacing"] * px
        y += MEMO["GAP"] + TEXT_MARGIN
        lay = layout_text(t, None, px, 400, max(10.0, inner - 2 * TEXT_MARGIN))
        rows.append({"ln": {"k": "p", "t": t, "more": True}, "i": len(all_), "x": MEMO["LPAD"], "y": y - TEXT_MARGIN, "lay": lay, "px": px,
                     "marker": None, "box": None, "cy": y + lh / 2, "lh": lh, "join_prev": False, "join_next": False})
        y += lay["h"] + TEXT_MARGIN
    return {"rows": rows, "h": int(-(-(y + MEMO["PAD"]) // 1))}


def _qcolor(c, default) -> QColor:
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        return QColor(int(c[0]), int(c[1]), int(c[2]), int(c[3]) if len(c) > 3 else 255)
    q = QColor(c) if isinstance(c, str) and c else QColor(default)
    return q if q.isValid() else QColor(default)


def paint_lines(p, lay, left, top, color, band=True):
    """글 그리기 — (left, top) = 문서 상자 왼쪽 위(여백 포함), 웹 TextLines."""
    px, weight = lay["px"], lay["weight"]
    asc, ls = BOARD_M["ascent"] * px, BOARD_M["lineSpacing"] * px
    th = max(0.6, px * 0.06)
    for i, ln in enumerate(lay["lines"]):
        base = top + TEXT_MARGIN + asc + i * ls
        x0 = left + TEXT_MARGIN
        if ln["code"] and band:
            p.fillRect(QRectF(x0 - 4, base - asc, (lay["max_w"] or lay["w"]) + 8, ls), CODE_BAND)
        for part in ln["parts"]:
            if part.get("mono") and not part.get("bg") and not ln["code"]:
                p.fillRect(QRectF(x0 + part["x"], base - asc, part["w"], ls), CODE_BAND)
            if part.get("bg"):
                p.fillRect(QRectF(x0 + part["x"], base - asc, part["w"], ls), _qcolor(part["bg"], "#00000000"))
            if part.get("link"):
                p.fillRect(QRectF(x0 + part["x"], base + px * 0.12, part["w"], max(0.6, px * 0.06)), QColor(LINK))
        for part in ln["parts"]:
            w = 400 if part.get("mono") else max(700, weight) if part.get("bold") else weight
            c = QColor(LINK) if part.get("link") else _qcolor(part.get("color"), color) if part.get("color") else QColor(color)
            p.setFont(font(px, w, part.get("mono", False), "i" in (part.get("deco") or "")))
            p.setPen(QPen(c))
            p.drawText(QPointF(x0 + part["x"], base), part["text"])
            deco = part.get("deco") or ""
            if deco and not part.get("link"):
                if "u" in deco:
                    p.fillRect(QRectF(x0 + part["x"], base + px * 0.12, part["w"], th), c)
                if "s" in deco:
                    p.fillRect(QRectF(x0 + part["x"], base - px * 0.32, part["w"], th), c)


def paint_memo(p, r: QRectF, d: dict):
    """메모 줄 그리기(바탕 네모는 부르는 쪽이 그림) — 웹 render.jsx 'memo'."""
    x, y, w = r.x(), r.y(), r.width()
    ml = memo_layout(d, w)
    ink0 = "#1f1f1f"
    for row in ml["rows"]:
        ln = row["ln"]
        if row.get("hr"):
            p.setPen(QPen(QColor("#d4d4d8"), 1))
            p.drawLine(QPointF(x + row["x"], y + row["cy"]), QPointF(x + w - MEMO["PAD"], y + row["cy"]))
            continue
        tb = row.get("table")
        if tb:
            X, Y, H = x + row["x"], y + row["y"], tb["row_y"][-1]
            if ln.get("header"):
                p.fillRect(QRectF(X, Y, tb["w"], tb["row_y"][1]), QColor("#f4f4f5"))
            for c in tb["cells"]:
                paint_lines(p, c["lay"], X + c["x"], Y + c["y"], ink0)
            p.setPen(QPen(QColor("#d4d4d8"), 1))
            for ry in tb["row_y"]:
                p.drawLine(QPointF(X, Y + ry), QPointF(X + tb["w"], Y + ry))
            for cx in tb["xs"]:
                p.drawLine(QPointF(X + cx, Y), QPointF(X + cx, Y + H))
            continue
        k, lay = ln.get("k"), row["lay"]
        done = k == "todo" and ln.get("done")
        col = MUTED if done or ln.get("more") else "#52525b" if k == "quote" else ink0
        jp, jn = row["join_prev"], row["join_next"]
        band_y = y + row["y"] + (TEXT_MARGIN if jp else 0)
        band_h = lay["h"] + (0 if jp else TEXT_MARGIN) + (0 if jn else TEXT_MARGIN)
        if k == "quote":
            p.fillRect(QRectF(x + MEMO["LPAD"], band_y, 3, band_h), QColor("#d4d4d8"))
        if k == "code":   # 코드 블록 = 한 덩어리 바탕
            p.fillRect(QRectF(x + row["x"] - 4, band_y, w - MEMO["PAD"] - row["x"] + 8, band_h), CODE_BAND)
        if row["marker"]:
            f = font(row["px"])
            p.setFont(f)
            p.setPen(QPen(QColor(ink0)))
            tw = QFontMetricsF(f).horizontalAdvance(row["marker"])
            p.drawText(QRectF(x + row["x"] - 6 - tw - 40, y + row["cy"] - row["px"], tw + 40, row["px"] * 2),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), row["marker"])
        b = row["box"]
        if b:
            br = QRectF(x + b["x"], y + b["y"], b["s"], b["s"])
            p.setPen(QPen(QColor("#2f80ed" if done else "#a1a1aa"), 1.2))
            p.setBrush(QColor("#2f80ed" if done else "#ffffff"))
            p.drawRoundedRect(br, b["s"] * 0.18, b["s"] * 0.18)
            if done:
                chk = QPainterPath(QPointF(br.x() + b["s"] * 0.22, br.y() + b["s"] * 0.52))
                chk.lineTo(br.x() + b["s"] * 0.43, br.y() + b["s"] * 0.72)
                chk.lineTo(br.x() + b["s"] * 0.8, br.y() + b["s"] * 0.3)
                pen = QPen(QColor("#ffffff"), 1.6)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(chk)
        paint_lines(p, lay, x + row["x"] - TEXT_MARGIN, y + row["y"], col, band=k != "code")
        if done:
            p.setPen(QPen(QColor(MUTED), 1))
            for j, l in enumerate(lay["lines"]):
                ly = y + row["y"] + TEXT_MARGIN + (j + 0.55) * row["lh"]
                p.drawLine(QPointF(x + row["x"], ly), QPointF(x + row["x"] + l["w"], ly))


def todo_at(d: dict, w: float, q: QPointF):
    """메모 안 좌표(rect 왼쪽 위 기준) q에 있는 할 일 상자의 줄 번호 — 없으면 None(상자 둘레 4px까지)."""
    for row in memo_layout(d, w)["rows"]:
        b = row.get("box")
        if b and QRectF(b["x"] - 4, b["y"] - 4, b["s"] + 8, b["s"] + 8).contains(q):
            return row["i"]
    return None


# ── 고치기: 줄 ↔ 마크다운 글(데스크톱 메모 편집 칸, 웹 메모 「마크다운 입력」과 같은 표시) ──
_MD_HEAD = {"h1": "# ", "h2": "## ", "h3": "### "}


def lines_to_md(lines) -> str:
    """메모 줄 → 고칠 글. 코드 줄은 ``` 울타리로 묶고, 표는 | 칸 | 줄(머리 행 밑 |---|)."""
    out, i, lines = [], 0, list(lines or [])
    while i < len(lines):
        ln = lines[i]
        k, t, ind = ln.get("k") or "p", ln.get("t") or "", "  " * int(ln.get("lv") or 0)
        if k == "code":
            out.append("```")
            while i < len(lines) and lines[i].get("k") == "code":
                out.append(lines[i].get("t") or "")
                i += 1
            out.append("```")
            continue
        if k == "table":
            rows = ln.get("rows") or [[""]]
            for ri, r in enumerate(rows):
                out.append("| " + " | ".join(c.replace("|", "／") for c in r) + " |")
                if ri == 0 and ln.get("header"):
                    out.append("|" + "|".join("---" for _ in r) + "|")
        elif k == "hr":
            out.append("---")
        elif k in _MD_HEAD:
            out.append(_MD_HEAD[k] + t)
        elif k == "ul":
            out.append(f"{ind}- {t}")
        elif k == "ol":
            out.append(f"{ind}1. {t}")
        elif k == "todo":
            out.append(f"{ind}[{'x' if ln.get('done') else ' '}] {t}")
        elif k == "quote":
            out.append("> " + t)
        else:
            out.append(t)
        i += 1
    return "\n".join(out)


_LIST_RE = re.compile(r"^( *)(?:([-*•])|(\d+)[.)]|\[( |x|X)\])\s+(.*)$")


def _table_widths(rows):
    """웹 memo.js tableWidths — 칸 너비 = 글 길이 비율(한글 두 칸, 2~24자, 여백 2자)."""
    n = max(1, *[len(r) for r in rows])
    w = [2 + min(24, max(2, *[sum(2 if ord(ch) > 0x2E80 else 1 for ch in (r[c] if c < len(r) else "")) / 2 for r in rows])) for c in range(n)]
    s = sum(w)
    return [round(v / s, 4) for v in w]


def md_to_lines(text: str, old_lines=None):
    """고친 글 → 메모 줄. 글·종류가 그대로인 줄은 원래 줄(굵게·색 등 꾸밈 포함)을 그대로 쓴다."""
    old = list(old_lines or [])
    pool = {}
    for ln in old:   # (종류, 글, 깊이) → 원래 줄들(같은 줄이 여럿이면 차례대로)
        pool.setdefault((ln.get("k"), ln.get("t") or "", int(ln.get("lv") or 0)), []).append(ln)
    old_tables = [ln for ln in old if ln.get("k") == "table"]

    def keep(new):
        hit = pool.get((new["k"], new.get("t") or "", int(new.get("lv") or 0)))
        if hit:
            o = dict(hit.pop(0))
            if new["k"] == "todo":   # 체크만 바꾼 할 일
                o.pop("done", None)
                if new.get("done"):
                    o["done"] = True
            return o
        return new

    src, out, i = (text or "").split("\n"), [], 0
    while i < len(src):
        s = src[i]
        if s.strip() == "```":
            i += 1
            while i < len(src) and src[i].strip() != "```":
                out.append({"k": "code", "t": src[i]})
                i += 1
            i += 1
            continue
        if s.strip().startswith("|"):
            rows, header = [], False
            while i < len(src) and src[i].strip().startswith("|"):
                cells = [c.strip() for c in src[i].strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) and rows:
                    header = len(rows) == 1
                else:
                    rows.append(cells)
                i += 1
            n = max(1, *[len(r) for r in rows])
            rows = [r + [""] * (n - len(r)) for r in rows]
            L = {"k": "table", "t": "", "rows": rows, "header": header, "cw": _table_widths(rows)}
            prev = old_tables.pop(0) if old_tables else None
            if prev and len(prev.get("cw") or []) == n:   # 칸 수가 같으면 칸 너비는 그대로(웹과 같게)
                L["cw"] = prev["cw"]
            out.append(L)
            continue
        i += 1
        st = s.strip()
        if re.fullmatch(r"([-*_])(\s*\1){2,}", st):
            out.append({"k": "hr", "t": ""})
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", st)
        if m:
            out.append(keep({"k": f"h{len(m.group(1))}", "t": m.group(2)}))
            continue
        if st.startswith(">"):
            out.append(keep({"k": "quote", "t": st[1:].lstrip()}))
            continue
        m = _LIST_RE.match(s.replace("\t", "  "))
        if m:
            lv = len(m.group(1)) // 2
            k = "ul" if m.group(2) else "ol" if m.group(3) else "todo"
            L = {"k": k, "t": m.group(5)}
            if lv:
                L["lv"] = lv
            if k == "todo" and m.group(4) in ("x", "X"):
                L["done"] = True
            out.append(keep(L))
            continue
        out.append(keep({"k": "p", "t": s}))
    return out or [{"k": "p", "t": ""}]


# ---- 메모 줄 고르기·옮기기(웹 memo.js lineUnit·selUnits·moveLines·pickLines·convertLine·recolorLine·toggleTodos 옮김 — 웹을 고치면 여기도) ----
# 줄 색(노션 「색」 — 글자 / 배경). 배경은 옅게(형광펜처럼 글자 뒤) — 웹 LINE_COLORS
LINE_COLORS = [("기본", None, None), ("회색", "#787774", "#55e3e2e0"), ("갈색", "#9f6b53", "#55eee0da"), ("주황", "#d9730d", "#55fadec9"),
               ("노랑", "#cb912f", "#66fdecc8"), ("초록", "#448361", "#55dbeddb"), ("파랑", "#337ea9", "#55d3e5ef"), ("보라", "#9065b0", "#55e8deee"),
               ("분홍", "#c14c8a", "#55f5e0e9"), ("빨강", "#d44c47", "#55ffe2dd")]


def line_unit(lines, i):
    """i번 줄이 속한 덩어리 [s, e) — 코드·인용은 이어진 줄 전부, 목록은 더 깊은 아래 줄까지."""
    if not (0 <= i < len(lines)):
        return [i, i]
    k = lines[i].get("k")
    if k in ("code", "quote"):
        s, e = i, i + 1
        while s > 0 and lines[s - 1].get("k") == k:
            s -= 1
        while e < len(lines) and lines[e].get("k") == k:
            e += 1
        return [s, e]
    e = i + 1
    if k in LISTY:
        while e < len(lines) and lines[e].get("k") in LISTY and (lines[e].get("lv") or 0) > (lines[i].get("lv") or 0):
            e += 1
    return [i, e]


def sel_units(ls):
    return sorted([list(u) for u in ls.get("more") or []] + [[ls["s"], ls["e"]]])


def sel_idx(ls):
    return [i for s, e in sel_units(ls) for i in range(s, e)]


def move_lines(lines, idx, to, copy_=False):
    """고른 줄들을 to 자리로(같은 메모) — copy_ = 원래 줄은 둠. 끼울 자리는 원래 줄 번호 기준."""
    import copy as _c
    on = set(idx)
    picked = [_c.deepcopy(lines[i]) if copy_ else lines[i] for i in idx]
    rest = list(lines) if copy_ else [l for i, l in enumerate(lines) if i not in on]
    at = to if copy_ else to - len([i for i in idx if i < to])
    return rest[:at] + picked + rest[at:]


def pick_lines(lines, idx):
    """고른 줄들 떼어 내기(다른 메모·새 메모로) — 깊이는 맨 앞 줄 기준 0부터."""
    import copy as _c
    base = lines[idx[0]].get("lv") or 0 if idx else 0
    out = []
    for i in idx:
        o = _c.deepcopy(lines[i])
        lv = (o.get("lv") or 0) - base
        if lv > 0:
            o["lv"] = lv
        else:
            o.pop("lv", None)
        out.append(o)
    return out


def convert_line(ln, k):
    """줄 종류 바꾸기(전환) — 코드는 부분 서식 없이, 할 일이 아니면 체크 없음, 목록이 아니면 깊이 없음. 구분선·표는 그대로."""
    if ln.get("k") in ("hr", "table"):
        return ln
    o = {**ln, "k": k}
    if k == "code":
        o.pop("runs", None)
    if k != "todo":
        o.pop("done", None)
    if k not in LISTY:
        o.pop("lv", None)
    return o


def recolor_line(ln, color=..., bg=...):
    """줄 전체 글자색·배경 — 다른 꾸밈(굵게·고정폭·기울임 등)은 그대로. ... = 그 칸은 안 바꿈."""
    t = ln.get("t") or ""
    n = len(t)
    if not n or ln.get("k") in ("code", "hr"):
        return ln
    at = [[None, False, None, False, ""] for _ in range(n)]
    for r in ln.get("runs") or []:
        s, length = int(r[0]), int(r[1])
        for i in range(max(0, s), min(n, s + length)):
            at[i] = [r[2] if len(r) > 2 else None, bool(r[3]) if len(r) > 3 else False, r[4] if len(r) > 4 else None,
                     bool(r[5]) if len(r) > 5 else False, (r[6] if len(r) > 6 else "") or ""]
    for a in at:
        if color is not ...:
            a[0] = color
        if bg is not ...:
            a[2] = bg
    runs, i = [], 0
    while i < n:
        j = i + 1
        while j < n and at[j] == at[i]:
            j += 1
        c, b, g, m, d = at[i]
        if d:
            runs.append([i, j - i, c, b, g, m, d])
        elif m:
            runs.append([i, j - i, c, b, g, True])
        elif c or b or g:
            runs.append([i, j - i, c, b, *([g] if g else [])])
        i = j
    o = dict(ln)
    if runs:
        o["runs"] = runs
    else:
        o.pop("runs", None)
    return o


def toggle_todos(lines, idx):
    """고른 줄 중 할 일만 — 하나라도 안 끝났으면 모두 끝, 모두 끝났으면 모두 풂. 할 일이 없으면 None."""
    todo = [i for i in idx if 0 <= i < len(lines) and lines[i].get("k") == "todo"]
    if not todo:
        return None
    done = not all(lines[i].get("done") for i in todo)
    out = []
    for j, l in enumerate(lines):
        if j in todo:
            l = dict(l)
            if done:
                l["done"] = True
            else:
                l.pop("done", None)
        out.append(l)
    return out
