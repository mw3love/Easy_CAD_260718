"""[§8 항목33, 2026-10-03] 벡터 PDF(AutoCAD 등 CAD 출력) 가져오기 — 선·곡선·채움·글자·그림을
좌표·색 그대로 `.ecad` 도형으로 옮긴다(PyMuPDF, AI 불필요).

실험 도구 `tools/pdf_vector_probe.py`(2026-10-01, `docs/history/2026-10.md` "0단계 재시험")의 변환
규칙을 앱 모듈로 옮긴 것. 사용자 결정(deep-interview 2026-10-03):
  - 진입점은 열기(Ctrl+O) — DXF/DWG처럼 새 탭에 연다(끌어놓기·최근 파일도 같은 경로).
  - 여러 쪽은 쪽마다 **빈 용지틀**(`_TitleBlockItem(plain=True)` — 우리 표제란 표 없음, CAD PDF엔
    자체 표제란이 있으므로)을 만들어 왼쪽부터 나란히 → §8 항목30 「모든 페이지를 한 PDF로」와 짝.
    용지가 A4~A0이 아니면 용지틀 없이 놓는다(용지틀은 그 크기만 지원).
  - 글자는 고칠 수 있는 글자 도형으로(글꼴이 달라 폭은 조금 어긋날 수 있음).
  - 도형이 많으면(`LARGE_COUNT` 초과) 개수를 알려 주고 계속/취소를 묻는다(`confirm` 콜백).

함정(`docs/pitfalls.md` "PDF 벡터 추출"): AutoCAD는 굵은 선을 삼각형 채움 여러 개로 낸다 → 끊긴
지점마다 별도 다각형. (0두께 직선의 `intersects` 함정은 구획 필터가 없는 이 모듈엔 해당 없음.)
"""
from __future__ import annotations

import base64
import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QFontMetricsF

from easycad.canvas.annotator_core import PAPER_SIZES_MM
from easycad.fileio.document import dict_to_item

SCALE = 4.0            # PDF pt → 캔버스 단위(실험 도구와 같음 — A3 한 쪽이 약 4,800단위)
LARGE_COUNT = 20000    # 이보다 많으면 열기 전에 확인(1,000개부터 무거워지는 앱, perf_plan_500_1000.md)
PAGE_GAP = 0.1         # 쪽 사이 간격(쪽 폭 대비)
_MIN_W = 0.8           # 0두께(헤어라인) 선의 화면 두께
_PAPER_TOL = 0.02      # 용지 크기 판정 허용오차(2%)


class PdfImportError(Exception):
    """사용자에게 그대로 보여줄 오류(의존성 없음·암호·빈 파일 등)."""


def _fitz():
    try:
        import fitz   # PyMuPDF — 이 기능에서만 쓰므로 지연 임포트(없어도 앱의 나머지는 정상)
    except ImportError as e:   # pragma: no cover — 설치 환경 의존
        raise PdfImportError("PDF를 열려면 PyMuPDF가 필요합니다.\n"
                             "명령 창에서 설치: pip install pymupdf") from e
    return fitz


def _col(c, alpha=None):
    if c is None:
        return None
    r, g, b = (max(0, min(255, round(v * 255))) for v in tuple(c)[:3])
    a = 255 if alpha is None else max(0, min(255, round(alpha * 255)))
    return "#%02x%02x%02x%02x" % (a, r, g, b)


def _dash_style(dashes) -> int | None:
    """PDF 대시 배열 → Qt PenStyle 값. 실선이면 None."""
    if not dashes:
        return None
    inner = str(dashes).split("]")[0].strip("[ ")
    nums = [v for v in inner.replace(",", " ").split() if v]
    if not nums:
        return None
    if len(nums) >= 6:
        return 5   # DashDotDotLine
    if len(nums) >= 4:
        return 4   # DashDotLine(1점쇄선)
    return 2       # DashLine


def paper_of(w_pt: float, h_pt: float):
    """쪽 크기(pt) → (용지 이름, 방향) 또는 None(A4~A0이 아님)."""
    w_mm, h_mm = w_pt * 25.4 / 72.0, h_pt * 25.4 / 72.0
    for name, (pw, ph) in PAPER_SIZES_MM.items():
        for orient, (a, b) in (("portrait", (pw, ph)), ("landscape", (ph, pw))):
            if abs(w_mm - a) <= a * _PAPER_TOL and abs(h_mm - b) <= b * _PAPER_TOL:
                return name, orient
    return None


def read_pdf(path: str) -> list[dict]:
    """PDF를 읽어 쪽마다 원자료를 모은다(Qt 비의존). 느린 부분(get_drawings)이 여기 몰려 있어
    호출부가 대기 표시를 띄운다. 반환: [{"w","h","drawings","lines","images","matrix"}, ...]."""
    fitz = _fitz()
    try:
        doc = fitz.open(path)
    except Exception as e:  # noqa: BLE001
        raise PdfImportError(f"PDF를 열 수 없습니다:\n{e}") from e
    if doc.needs_pass:
        raise PdfImportError("암호가 걸린 PDF는 열 수 없습니다.")
    if doc.page_count == 0:
        raise PdfImportError("쪽이 없는 PDF입니다.")
    pages = []
    for page in doc:
        # 회전된 쪽: get_drawings·get_text 좌표는 회전 전 기준이라 화면 방향으로 돌려 준다.
        m = page.rotation_matrix if page.rotation else None
        lines = []
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                lines.append(ln)
        images = []
        for info in page.get_image_info(xrefs=True):
            images.append({"bbox": tuple(info["bbox"]), "png": _image_png(fitz, doc, info.get("xref", 0))})
        pages.append({"w": page.rect.width, "h": page.rect.height, "drawings": page.get_drawings(),
                      "lines": lines, "images": images, "matrix": m})
    return pages


def _image_png(fitz, doc, xref):
    """그림 xref → PNG 바이트(실패·인라인 그림이면 None)."""
    if not xref:
        return None
    try:
        pix = fitz.Pixmap(doc, xref)
        smask = doc.extract_image(xref).get("smask", 0)
        if smask:
            pix = fitz.Pixmap(pix, fitz.Pixmap(doc, smask))
        if pix.n - pix.alpha >= 4:   # CMYK 등 → RGB
            pix = fitz.Pixmap(fitz.csRGB, pix)
        return pix.tobytes("png")
    except Exception:  # noqa: BLE001 — 그림 하나 실패는 건너뛰고 개수만 센다
        return None


def estimate_count(pages) -> int:
    """만들어질 도형 수 어림(채움 하위경로 분리 전 기준 — 실제는 조금 더 많을 수 있음)."""
    n = 0
    for pg in pages:
        n += len(pg["drawings"]) + len(pg["images"])
        n += sum(len(ln["spans"]) for ln in pg["lines"])
    return n


def build_dicts(pages, stats: dict | None = None) -> list[dict]:
    """원자료 → item dict 목록(Qt 비의존). 쪽은 왼쪽부터 나란히, 쪽마다 빈 용지틀 1개.
    글자 dict는 위치를 아직 모르는 상태로 `_baseline`(기준선 왼쪽 점)·`_angle`을 달아 두고,
    `create_items`가 글꼴 높이를 재서 자리를 잡는다."""
    fitz = _fitz()
    st = stats if stats is not None else {}
    st.setdefault("no_frame", 0)
    st.setdefault("skipped_images", 0)
    out = []
    z = [0.0]
    x_off = 0.0

    def common(pos=(0.0, 0.0)):
        z[0] += 1
        return {"pos": [pos[0], pos[1]], "scale": 1.0, "rotation": 0.0, "z": z[0], "origin": [0.0, 0.0]}

    for pg in pages:
        m = pg["matrix"]
        pw, ph = pg["w"] * SCALE, pg["h"] * SCALE

        def P(pt, _m=m, _x=x_off):
            if _m is not None:
                pt = pt * _m
            return [pt.x * SCALE + _x, pt.y * SCALE]

        paper = paper_of(pg["w"], pg["h"])
        if paper:
            size, orient = paper
            fw = PAPER_SIZES_MM[size][1 if orient == "landscape" else 0]
            out.append({"type": "titleblock", "size": size, "orient": orient, "fields": {},
                        "plain": True, "pos": [x_off, 0.0], "scale": pw / fw, "rotation": 0.0,
                        "z": -1000.0, "origin": [0.0, 0.0]})
        else:
            st["no_frame"] += 1

        # 그림(맨 아래) — 회전·뒤집힌 그림도 둘레 상자에 똑바로 놓는다(CAD PDF엔 드묾).
        for im in pg["images"]:
            if not im["png"]:
                st["skipped_images"] += 1
                continue
            x0, y0, x1, y1 = im["bbox"]
            if m is not None:
                r = fitz.Rect(x0, y0, x1, y1) * m
                x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
            d = common()
            d.update(type="image", data=base64.b64encode(im["png"]).decode("ascii"),
                     rect=[x0 * SCALE + x_off, y0 * SCALE, (x1 - x0) * SCALE, (y1 - y0) * SCALE])
            out.append(d)

        for dr in pg["drawings"]:
            out.extend(_drawing_dicts(dr, P, common))

        for ln in pg["lines"]:
            dx, dy = ln["dir"]
            if m is not None:
                v = (dx * m.a + dy * m.c, dx * m.b + dy * m.d)
                dx, dy = v
            ang = math.degrees(math.atan2(dy, dx))
            for sp in ln["spans"]:
                t = sp["text"]
                if not t.strip():
                    continue
                bx, by = P(fitz.Point(*sp["origin"]))
                font = max(1, round(sp["size"] * SCALE * 0.75))   # 글자 높이(px) → pt(96dpi)
                d = common()
                d.update(type="text", text=t, color="#ff%06x" % (sp["color"] & 0xFFFFFF),
                         font=font, bg=None, _baseline=[bx, by], _angle=ang)
                out.append(d)
        x_off += pw * (1.0 + PAGE_GAP)
    return out


def _drawing_dicts(dr, P, common) -> list[dict]:
    its = dr["items"]
    stroke = _col(dr.get("color"), dr.get("stroke_opacity"))
    fill = _col(dr.get("fill"), dr.get("fill_opacity"))
    w = max((dr.get("width") or 0) * SCALE, _MIN_W)
    style = _dash_style(dr.get("dashes"))
    out = []
    if fill is not None:
        # 채움 + (있으면) 테두리. 채움만이면 같은 색 얇은 테두리로 안티앨리어스 틈을 메운다.
        pen, pw_ = (stroke, w) if stroke is not None else (fill, 0.3)
        subs = _subpaths(its, P)
        if dr.get("even_odd") and len(subs) > 1:
            # 구멍 있는 채움 — 한 패스(홀짝 규칙, _PathItem 채움 기본값)로 정확히.
            el = [e for s in subs for e in s["el"]]
            d = common(); d.update(type="path", elements=el, pen=pen, width=pw_, fill=fill)
            out.append(d)
            return out
        for s in subs:
            if s["curved"]:
                d = common(); d.update(type="path", elements=s["el"], pen=pen, width=pw_, fill=fill)
            else:
                pts = s["pts"]
                if len(pts) < 3:
                    continue
                xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
                d = common()
                d.update(type="polygon", closed=True,
                         rect=[min(xs), min(ys), max(max(xs) - min(xs), 1), max(max(ys) - min(ys), 1)],
                         pts=pts, pen=pen, width=pw_, fill=fill)
            if style is not None and stroke is not None:
                d["style"] = style
            out.append(d)
        return out
    if stroke is None:
        return out
    # 사각형 하나뿐이면 rect(편집 시 리사이즈 핸들이 의미 있음) — 회전 쪽이면 일반 경로로.
    if len(its) == 1 and its[0][0] == "re":
        a, b = P(its[0][1].tl), P(its[0][1].br)
        if a[0] <= b[0] and a[1] <= b[1]:
            d = common()
            d.update(type="rect", rect=[a[0], a[1], b[0] - a[0], b[1] - a[1]],
                     pen=stroke, width=w, fill=None)
            if style is not None:
                d["style"] = style
            out.append(d)
            return out
    el = [e for s in _subpaths(its, P) for e in s["el"]]
    if dr.get("closePath") and el:
        m0 = el[0]
        el.append(["L", m0[1], m0[2]])
    if not el:
        return out
    d = common()
    d.update(type="path", elements=el, pen=stroke, width=w)
    if style is not None:
        d["style"] = style
    out.append(d)
    return out


def _subpaths(its, P) -> list[dict]:
    """PDF 경로 조각 → 끊긴 지점(이전 끝 ≠ 다음 시작)마다 나눈 하위 경로 목록.
    각 항목: {"el": 패스 요소, "pts": 정점(곡선은 샘플), "curved": 곡선 포함 여부}."""
    subs, cur, last = [], None, None

    def start(a):
        nonlocal cur
        cur = {"el": [["M", *a]], "pts": [a], "curved": False}
        subs.append(cur)

    for it in its:
        k = it[0]
        if k == "l":
            a, b = P(it[1]), P(it[2])
            if cur is None or last is None or abs(last[0] - a[0]) > .01 or abs(last[1] - a[1]) > .01:
                start(a)
            cur["el"].append(["L", *b]); cur["pts"].append(b); last = b
        elif k == "c":
            a, b, c_, d_ = (P(q) for q in it[1:5])
            if cur is None or last is None or abs(last[0] - a[0]) > .01 or abs(last[1] - a[1]) > .01:
                start(a)
            cur["el"].append(["C", *b, *c_, *d_]); cur["curved"] = True
            for t in (.25, .5, .75, 1.0):
                mt = 1 - t
                cur["pts"].append([mt ** 3 * a[0] + 3 * mt * mt * t * b[0] + 3 * mt * t * t * c_[0] + t ** 3 * d_[0],
                                   mt ** 3 * a[1] + 3 * mt * mt * t * b[1] + 3 * mt * t * t * c_[1] + t ** 3 * d_[1]])
            last = d_
        elif k in ("re", "qu"):
            q = it[1].quad if k == "re" else it[1]
            corners = [P(q.ul), P(q.ur), P(q.lr), P(q.ll)]
            start(corners[0])
            for c in corners[1:] + [corners[0]]:
                cur["el"].append(["L", *c])
            cur["pts"] = corners
            last = None
    for s in subs:   # 닫힌 다각형 정점에서 시작점 중복 제거
        p = s["pts"]
        if len(p) > 3 and abs(p[0][0] - p[-1][0]) < .01 and abs(p[0][1] - p[-1][1]) < .01:
            p.pop()
    return subs


def create_items(dicts, progress=None) -> list | None:
    """item dict → 씬 아이템(Qt). 글자는 기준선 왼쪽 점에 맞춰 자리를 잡는다.
    `progress(done, total)`이 False를 돌려주면 중단하고 None."""
    items = []
    total = len(dicts)
    for i, d in enumerate(dicts):
        if progress is not None and i % 500 == 0 and progress(i, total) is False:
            return None
        if d.get("type") == "text":
            d = dict(d)
            bx, by = d.pop("_baseline")
            ang = d.pop("_angle")
            it = dict_to_item(d)
            if it is None:
                continue
            # QGraphicsTextItem: 글자는 문서 여백 + ascent 아래 기준선에 놓인다(dxf_import._text_item와 같은 방식)
            mg = it.document().documentMargin()
            ox, oy = mg, mg + QFontMetricsF(it.font()).ascent()
            it.setTransformOriginPoint(QPointF(ox, oy))
            it.setPos(QPointF(bx - ox, by - oy))
            it.setRotation(ang)
        else:
            it = dict_to_item(d)
            if it is None:
                continue
        items.append(it)
    if progress is not None:
        progress(total, total)
    return items


def import_pdf(scene, path: str, *, confirm=None, progress=None, stats: dict | None = None) -> int | None:
    """PDF를 씬에 가져온다(기존 내용 지움). 가져온 도형 수, 사용자가 취소하면 None.
    `confirm(count)` — 많을 때(`LARGE_COUNT` 초과) 계속할지. `progress(done, total)` — create_items 참조.
    `stats`에 no_frame(용지틀 못 만든 쪽 수)·skipped_images·pages·vector(벡터 있었나)를 채운다."""
    st = stats if stats is not None else {}
    pages = read_pdf(path)
    st["pages"] = len(pages)
    st["vector"] = any(pg["drawings"] or pg["lines"] for pg in pages)
    count = estimate_count(pages)
    if count > LARGE_COUNT and confirm is not None and not confirm(count):
        return None
    dicts = build_dicts(pages, st)
    items = create_items(dicts, progress)
    if items is None:
        return None
    scene.clear()
    for it in items:
        scene.addItem(it)
    return len(items)
