"""벡터 PDF(AutoCAD 등 CAD 출력) → .ecad — AI 없이 선·곡선·채움·글자를 좌표·색 그대로 옮기는 실험 도구.

2026-10-01 실험(`docs/history/2026-10.md` "0단계 재시험", 계획서 §8 후보29). 개발용, 앱 런타임 비의존.
    python tools/pdf_vector_probe.py drawing.pdf out.ecad [x0,y0,x1,y1]   # 구획(pt)만 옮기려면 마지막 인자
"""
import json, sys
import fitz

S = 4.0   # pt → 캔버스


def col(c, default="#000000"):
    if c is None:
        return None
    r, g, b = (max(0, min(255, round(v * 255))) for v in c[:3])
    return "#ff%02x%02x%02x" % (r, g, b)


def main(pdf, out, clip=None):
    doc = fitz.open(pdf)
    p = doc[0]
    clip = fitz.Rect(*clip) if clip else p.rect
    ox, oy = clip.x0, clip.y0
    P = lambda pt: [(pt.x - ox) * S, (pt.y - oy) * S]
    items = []
    z = [0]

    def common():
        z[0] += 1
        return {"pos": [0.0, 0.0], "scale": 1.0, "rotation": 0.0, "z": float(z[0]), "origin": [0.0, 0.0]}

    stats = {"path": 0, "rect": 0, "poly": 0, "text": 0, "skip": 0}
    for dr in p.get_drawings():
        rr = fitz.Rect(dr["rect"]); rr.x1 += .01; rr.y1 += .01   # 0두께 직선도 포함
        if not rr.intersects(clip):
            continue
        stroke, fill = col(dr.get("color")), col(dr.get("fill"))
        w = max((dr.get("width") or 0) * S, 0.8)
        its = dr["items"]
        # 채운 도형: 닫힌 다각형(곡선은 샘플링)으로 — _PathItem은 채움을 저장하지 않음
        if fill is not None:
            # 하위 경로(끊긴 지점)마다 따로 닫힌 다각형 — AutoCAD는 굵은 선을 삼각형 여러 개로 낸다
            subs, cur, last = [], [], None
            def flush():
                if len(cur) >= 3:
                    subs.append(list(cur))
            for it in its:
                if it[0] == "l":
                    a, b = it[1], it[2]
                    if last is None or abs(last.x - a.x) > 1e-3 or abs(last.y - a.y) > 1e-3:
                        flush(); cur.clear(); cur.append(P(a))
                    cur.append(P(b)); last = b
                elif it[0] == "c":
                    a, b, c_, d = it[1:5]
                    if last is None or abs(last.x - a.x) > 1e-3 or abs(last.y - a.y) > 1e-3:
                        flush(); cur.clear(); cur.append(P(a))
                    for t_ in (.25, .5, .75, 1):
                        mt = 1 - t_
                        x = mt**3*a.x + 3*mt*mt*t_*b.x + 3*mt*t_*t_*c_.x + t_**3*d.x
                        y = mt**3*a.y + 3*mt*mt*t_*b.y + 3*mt*t_*t_*c_.y + t_**3*d.y
                        cur.append(P(fitz.Point(x, y)))
                    last = d
                elif it[0] in ("re", "qu"):
                    flush(); cur.clear(); last = None
                    q = it[1].quad if it[0] == "re" else it[1]
                    subs.append([P(q.ul), P(q.ur), P(q.lr), P(q.ll)])
            flush()
            for pts in subs:
                xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
                d = common()
                d.update(type="polygon", closed=True,
                         rect=[min(xs), min(ys), max(max(xs)-min(xs), 1), max(max(ys)-min(ys), 1)],
                         pts=pts, pen=fill, width=0.3, fill=fill)
                items.append(d); stats["poly"] += 1
            if subs:
                continue
        if stroke is None:
            stats["skip"] += 1
            continue
        # 사각형 하나뿐이면 rect(편집 시 리사이즈 핸들이 의미 있음)
        if len(its) == 1 and its[0][0] == "re":
            r = its[0][1]
            d = common()
            d.update(type="rect", rect=[(r.x0-ox)*S, (r.y0-oy)*S, r.width*S, r.height*S],
                     pen=stroke, width=w, fill=None)
            items.append(d); stats["rect"] += 1
            continue
        el = []
        last = None
        for it in its:
            k = it[0]
            if k == "l":
                a, b = P(it[1]), P(it[2])
                if last is None or abs(last[0]-a[0]) > .01 or abs(last[1]-a[1]) > .01:
                    el.append(["M", *a])
                el.append(["L", *b]); last = b
            elif k == "c":
                a, b, c_, d_ = (P(q) for q in it[1:5])
                if last is None or abs(last[0]-a[0]) > .01 or abs(last[1]-a[1]) > .01:
                    el.append(["M", *a])
                el.append(["C", *b, *c_, *d_]); last = d_
            elif k == "re":
                r = it[1]
                el += [["M", *P(r.tl)], ["L", *P(r.tr)], ["L", *P(r.br)], ["L", *P(r.bl)], ["L", *P(r.tl)]]
                last = None
            elif k == "qu":
                q = it[1]
                el += [["M", *P(q.ul)], ["L", *P(q.ur)], ["L", *P(q.lr)], ["L", *P(q.ll)], ["L", *P(q.ul)]]
                last = None
        if dr.get("closePath") and el:
            m = el[0]
            el.append(["L", m[1], m[2]])
        if not el:
            stats["skip"] += 1
            continue
        d = common()
        d.update(type="path", elements=el, pen=stroke, width=w)
        if dr.get("dashes") and dr["dashes"] not in ("[] 0", "[] 0.0"):
            d["style"] = 2   # DashLine
        items.append(d); stats["path"] += 1

    td = p.get_text("dict", clip=clip)
    for b in td["blocks"]:
        for ln in b.get("lines", []):
            dx, dy = ln["dir"]
            for sp in ln["spans"]:
                t = sp["text"]
                if not t.strip():
                    continue
                c = sp["color"]
                color = "#ff%06x" % c
                size = sp["size"] * S                      # 글자 높이(px)
                font = max(1, round(size * 0.75))           # px → pt(96dpi)
                x0, y0 = sp["origin"]                       # 기준선 왼쪽
                d = common()
                # QGraphicsTextItem: pos=왼쪽위, 문서여백 4px, 기준선은 대략 위에서 여백+ascent
                asc = sp.get("ascender", 0.9) * size
                d.update(type="text", text=t, color=color, font=font, bg=None)
                rot = 0.0
                if abs(dx - 1) > 1e-3:
                    import math
                    rot = math.degrees(math.atan2(dy, dx))
                d["pos"] = [(x0 - ox) * S - 4, (y0 - oy) * S - asc - 4]
                d["rotation"] = rot
                items.append(d); stats["text"] += 1

    json.dump({"format": "easycad-doc", "version": 1, "items": items},
              open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(len(items), stats)


if __name__ == "__main__":
    clip = [float(v) for v in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
    main(sys.argv[1], sys.argv[2], clip)
