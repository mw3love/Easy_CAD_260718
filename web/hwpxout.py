"""정리 문서(HTML) → 한글 파일(.hwpx)(2026-11-04 — 대회 검토: 공공기관 직원은 정리한 것을 바로 기안·보고서 한글 파일로 써야 함).

정리 문서는 AI가 모양을 자유롭게 짠 HTML(카드·표·SVG 그래프)이라 모양을 그대로 옮기지 않고 「글의 차례」만 옮긴다:
제목(h1~h3) = 한글 제목 문단 · 문단·목록 = 문단(목록은 「•」/「1.」) · 표 = 한글 표 · 작은 카드(짧은 글 몇 칸) = 한 줄로 묶음 ·
SVG 그래프 = 안의 글만 「[그림] …」 한 줄 · data: 그림 = 그림. 문서 만들기는 python-hwpx(Apache-2.0, `pip install python-hwpx==6.8.0`).
"""
from __future__ import annotations

import base64
import re
from html.parser import HTMLParser

BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "aside", "figure", "figcaption", "blockquote",
         "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "dl", "dt", "dd", "pre", "hr", "nav", "svg", "img", "details", "summary"}
SKIP = {"style", "script", "head", "noscript", "template"}
VOID = {"br", "img", "hr", "meta", "link", "input", "col", "source", "wbr"}
CARD_MAX = 90   # 이 글자 수 안의 작은 묶음(큰 숫자 + 설명 칸) = 한 줄로


class _Node:
    __slots__ = ("tag", "attrs", "kids", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.kids, self.parent = tag, dict(attrs or []), [], parent


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = _Node("root")

    def handle_starttag(self, tag, attrs):
        n = _Node(tag, attrs, self.cur)
        self.cur.kids.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:   # 닫는 태그가 어긋나도(AI HTML) 가장 가까운 같은 이름까지
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def _parse(html: str) -> _Node:
    t = _Tree()
    t.feed(html or "")
    t.close()
    return t.root


def _text(n, keep_br=True) -> str:
    """안의 글(인라인) — <br>는 줄바꿈, 숨긴 것·스타일은 뺌."""
    if isinstance(n, str):
        return n
    if n.tag in SKIP or n.tag in ("svg",):
        return ""
    if n.tag == "br":
        return "\n" if keep_br else " "
    out = _join(n.kids, keep_br)
    if n.tag in BLOCK and n.tag not in ("li",):
        out = "\n" + out + "\n"
    elif n.tag in ("td", "th"):
        out = out + " "
    return out


PARTICLE = tuple("가이은는을를의에와과로도만")


def _join(kids, keep_br=True) -> str:
    """인라인 글 잇기 — 화면에선 칸으로 떨어져 보이던 글이 붙지 않게 띄움:
    나란한 칸(<span>11/8</span><span>진공관 견적</span>)·맨 앞 이름표(<b>회의</b>11월 …, 뒤가 조사(「가·를…」)면 그대로 붙임)."""
    parts, prev_el, first = [], False, True
    for k in kids:
        s = _text(k, keep_br)
        el = not isinstance(k, str)
        if parts and s and not parts[-1][-1:].isspace() and not s[:1].isspace():
            if (el and prev_el) or (not el and prev_el and label and not s.startswith(PARTICLE)) or (el and not prev_el and k.tag in ("span", "small")):   # 마지막 = 「핵심 의견<span>작성자 의견</span>」
                parts.append(" ")
        parts.append(s)
        if el or (isinstance(k, str) and k.strip()):
            label = el and first and k.tag in ("b", "strong", "label", "span", "em")
            prev_el, first = el, False
    return "".join(parts)


def _clean(s: str) -> list:
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in s.split("\n")]
    return [ln for ln in lines if ln]


def _has_block(n) -> bool:
    return any(not isinstance(k, str) and (k.tag in BLOCK or _has_block(k)) for k in n.kids)


def _svg_words(n) -> str:
    words = []

    def walk(x):
        if isinstance(x, str):
            return
        if x.tag in ("text", "tspan", "title") and not any(not isinstance(k, str) and k.tag == "tspan" for k in x.kids):
            t = re.sub(r"\s+", " ", "".join(k for k in x.kids if isinstance(k, str))).strip()
            if t and t not in words:
                words.append(t)
        for k in x.kids:
            walk(k)
    walk(n)
    return " · ".join(words)[:400]


def blocks(html: str) -> list:
    """HTML → [("h", level, 글) | ("p", 글) | ("li", 글, 표식) | ("table", [[칸 글]]) | ("img", 바이트, 형식) | ("fig", 글)] — 차례 그대로."""
    out = []

    def para(s, kind="p"):
        for ln in _clean(s):
            out.append((kind, ln))

    def table(n):
        rows = []

        def walk(x):
            if isinstance(x, str) or x.tag in SKIP:
                return
            if x.tag == "tr":
                rows.append([" ".join(_clean(_text(c, keep_br=False))) for c in x.kids if not isinstance(c, str) and c.tag in ("td", "th")])
                return
            for k in x.kids:
                walk(k)
        walk(n)
        rows = [r for r in rows if r]
        if rows:
            w = max(len(r) for r in rows)
            out.append(("table", [r + [""] * (w - len(r)) for r in rows]))

    def lst(n, depth):
        i = 0
        for k in n.kids:
            if isinstance(k, str) or k.tag != "li":
                continue
            i += 1
            mark = f"{i}." if n.tag == "ol" else "•"
            inline = _join([c for c in k.kids if isinstance(c, str) or c.tag not in ("ul", "ol")])
            lines = _clean(inline)
            if lines:
                out.append(("li", "  " * depth + mark + " " + " ".join(lines)))
            for c in k.kids:
                if not isinstance(c, str) and c.tag in ("ul", "ol"):
                    lst(c, depth + 1)

    def walk(n):
        if isinstance(n, str):
            para(n)
            return
        tag = n.tag
        if tag in SKIP or tag == "title":
            return
        if re.fullmatch(r"h[1-6]", tag):
            t = " ".join(_clean(_text(n, keep_br=False)))
            if t:
                out.append(("h", min(int(tag[1]), 3), t))
            return
        if tag == "table":
            table(n)
            return
        if tag in ("ul", "ol"):
            lst(n, 0)
            return
        if tag == "svg":
            w = _svg_words(n)
            if w:
                out.append(("fig", "[그림] " + w))
            return
        if tag == "img":
            src = n.attrs.get("src") or ""
            m = re.match(r"data:image/(png|jpe?g|gif|bmp);base64,(.+)", src, re.S)
            if m:
                try:
                    out.append(("img", base64.b64decode(m.group(2)), "jpg" if m.group(1).startswith("j") else m.group(1)))
                except ValueError:
                    pass
            elif n.attrs.get("alt"):
                out.append(("fig", "[그림] " + n.attrs["alt"]))
            return
        if tag in ("hr", "input", "meta", "link"):
            return
        if tag in ("root", "html", "body") or _has_block(n):
            small = [k for k in n.kids if not (isinstance(k, str) and not k.strip())]
            # 작은 카드 — 안이 짧은 글 칸 몇 개뿐(표·목록·제목·그림 없음)이면 한 줄로(「42% · 줄어든 대기 시간」)
            if tag not in ("root", "html", "body") and 1 < len(small) <= 4 and all(
                    not isinstance(k, str) and k.tag in ("div", "span", "p", "small", "strong", "b", "em") and not _has_block(k) for k in small):
                parts = [" ".join(_clean(_text(k, keep_br=False))) for k in small]
                parts = [p for p in parts if p]
                if parts and sum(map(len, parts)) <= CARD_MAX:
                    out.append(("p", " · ".join(parts)))
                    return
            run = []   # 블록 사이 인라인 글은 모아서 한 문단

            def flush():
                if run:
                    para("".join(_text(x) for x in run))
                    run.clear()
            for k in n.kids:
                if isinstance(k, str) or not (k.tag in BLOCK or _has_block(k)):
                    run.append(k)
                else:
                    flush()
                    walk(k)
            flush()
            return
        para(_text(n))

    walk(_parse(html))
    return out


def to_hwpx(html: str, title: str = "") -> bytes:
    """정리 문서 HTML → .hwpx 바이트. python-hwpx가 없으면 ImportError."""
    from hwpx import HwpxDocument
    doc = HwpxDocument.new()
    bl = blocks(html)
    if title and not any(b[0] == "h" for b in bl[:3]):
        bl.insert(0, ("h", 1, title))
    first = True
    for b in bl:
        kind = b[0]
        if kind == "h":
            doc.add_heading(b[2], b[1])
        elif kind in ("p", "li", "fig"):
            doc.add_paragraph(b[1])
        elif kind == "table":
            rows = b[1]
            t = doc.add_table(len(rows), len(rows[0]))
            for r, row in enumerate(rows):
                for c, s in enumerate(row):
                    t.set_cell_text(r, c, s)
        elif kind == "img":
            try:
                doc.add_picture(b[1], b[2], width_mm=150)
            except Exception:   # 못 읽는 그림은 건너뜀(글은 다 남김)
                pass
        first = False
    if first:
        doc.add_paragraph(title or "(빈 문서)")
    return doc.to_bytes()
