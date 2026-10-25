"""웹 칠판 종류를 데스크톱에서 웹과 같은 모양으로 그린다(§8 항목61 ④-3, 2026-10-22).

프레임·웹 카드·정리 문서·PDF 보기 카드·범례·메모. 전엔 「글을 적은 네모」(대리 그림)였다.
모두 `_RectItem`을 물려받아 고르기·옮기기·크기·화살표 붙이기·레이어는 네모 그대로 — 바꾼 것은 그리기뿐.
그리는 숫자(띠 높이·여백·색·글자 크기)는 웹 `web/src/next/render.jsx`·`webcard.js`·`legend.js`·`geom.js`를 옮김 —
웹을 고치면 여기도. 저장은 원래 칸 통째(`_web_raw`, `fileio/document.py`)라 웹만 아는 칸도 안 잃는다.
"""
import base64

import copy
import html as _html
import re

from PyQt6.QtCore import QPointF, QRectF, Qt, QUrl
from PyQt6.QtGui import QBrush, QColor, QDesktopServices, QFont, QFontMetricsF, QPainterPath, QPen, QPixmap

from easycad.canvas.core_memo_lines import _MemoLinesMixin
from easycad.canvas.core_shapes import _RectItem

WEB_TYPES = ("frame", "web", "memo", "legend", "doc", "pdf")
WEB_HEAD = 40                                    # 웹 webcard.js WEB_HEAD — 위 띠(제목 + 주소)
APP_FAMILIES = ["Segoe UI", "Malgun Gothic"]     # 웹 geom.js APP_FONT
LEGEND = {"PAD": 10, "TITLE": 13, "HEAD": 30, "ROW": 26, "FONT": 12, "SAMPLE": 48, "GAP": 12}   # 웹 legend.js LEGEND
STYLE_NAMES = {1: "실선", 2: "파선", 3: "점선", 4: "일점쇄선", 5: "이점쇄선"}
DASH = {2: [4, 2], 3: [1, 2], 4: [4, 2, 1, 2], 5: [4, 2, 1, 2, 1, 2]}   # 웹 geom.js dashArray(굵기 배수)

_PIX = {}   # data: 그림 → QPixmap(같은 그림을 매번 풀지 않게)


def _font(px: float, weight: int = 400) -> QFont:
    f = QFont()
    f.setFamilies(APP_FAMILIES)
    f.setPixelSize(max(1, round(px)))
    f.setWeight(QFont.Weight(weight))
    return f


def _pixmap(src) -> QPixmap | None:
    """data:image/... 주소만 그림으로(인터넷 주소는 데스크톱이 받지 않음 — 대신 자리 그림)."""
    if not isinstance(src, str) or not src.startswith("data:image") or "," not in src:
        return None
    if src not in _PIX:
        pm = QPixmap()
        try:
            pm.loadFromData(base64.b64decode(src.split(",", 1)[1]))
        except (ValueError, TypeError):
            pm = QPixmap()
        _PIX[src] = pm if not pm.isNull() else None
    return _PIX[src]


def _color(c, default="#ffffff") -> QColor:
    q = QColor(c) if isinstance(c, str) and c else QColor(default)
    return q if q.isValid() else QColor(default)


def _text(p, x, y, s, px, color, weight=400, max_w=None, align=Qt.AlignmentFlag.AlignLeft):
    """글 한 줄 — y = 글줄 가운데(웹 dominantBaseline="central"), max_w를 넘으면 …"""
    f = _font(px, weight)
    p.setFont(f)
    p.setPen(QPen(_color(color)))
    if max_w is not None:
        s = QFontMetricsF(f).elidedText(s, Qt.TextElideMode.ElideRight, max(0.0, max_w))
    h = px * 2
    r = QRectF(x, y - h / 2, 100000, h) if align == Qt.AlignmentFlag.AlignLeft else QRectF(x - 50000, y - h / 2, 100000, h)
    p.drawText(r, int(align | Qt.AlignmentFlag.AlignVCenter), s)


def _site(url: str) -> str:
    u = (url or "").split("://", 1)[-1]
    return u.split("/", 1)[0].removeprefix("www.")


def color_name(c) -> str:
    """선 색 → 쉬운 이름(웹 legend.js colorName과 같게)."""
    q = QColor(c) if isinstance(c, str) else QColor()
    if not q.isValid():
        return "색"
    r, g, b = q.redF(), q.greenF(), q.blueF()
    mx, mn = max(r, g, b), min(r, g, b)
    s = (mx - mn) / mx if mx else 0
    if s < 0.18 or mx - mn < 0.08:
        return "검정" if mx < 0.25 else "흰색" if mx > 0.85 else "회색"
    if mx == r:
        hue = ((g - b) / (mx - mn)) % 6
    elif mx == g:
        hue = (b - r) / (mx - mn) + 2
    else:
        hue = (r - g) / (mx - mn) + 4
    hue = (hue * 60 + 360) % 360
    if hue < 15:
        return "빨강"
    if hue < 42:
        return "갈색" if mx < 0.85 else "주황"
    for lim, name in ((68, "노랑"), (160, "초록"), (200, "하늘"), (255, "파랑"), (290, "보라"), (335, "자홍")):
        if hue < lim:
            return name
    return "빨강"


class _WebItem(_RectItem):
    """웹 종류 공통 — 네모 그대로 + 그리기만 웹 모양. 라벨(가운데 글)은 안 씀(웹 칸이 글을 들고 있음)."""
    _is_web_item = True
    RADIUS = 0.0

    def __init__(self, rect: QRectF, raw: dict):
        super().__init__(rect)
        self._web_raw = dict(raw)
        self._radius = self.RADIUS
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(QColor("#ffffff")))   # 속이 찬 것으로 — 안쪽을 눌러도 고름(웹 카드와 같게)

    @property
    def raw(self) -> dict:
        return self._web_raw

    def has_label(self):
        return False

    def clone(self):
        # 복사·복제 — 원래 칸까지 통째로(전엔 `_RectItem`으로 복제돼 웹 칸을 잃었음)
        from easycad.fileio.document import dict_to_item, item_to_dict
        c = dict_to_item(item_to_dict(self))
        return self._copy_common_to(c)

    def web_double_click(self, view, scene_pos) -> bool:
        """두 번 누르기 — 종류마다(웹 카드 = 브라우저로). 처리했으면 True."""
        return False

    def plain_text(self) -> str:
        """안의 글을 쉬운 글로(DXF 내보내기 등) — 종류마다."""
        d = self._web_raw
        return "\n".join(x for x in (d.get("title") or d.get("name"), d.get("url")) if x)

    # 되돌리기 — 원래 칸·크기까지(메모 고치기·할 일 체크가 `push_undo_state`로 실림)
    def capture_state(self) -> dict:
        st = super().capture_state()
        st["web_raw"] = copy.deepcopy(self._web_raw)
        st["web_rect"] = QRectF(self.rect())
        return st

    def apply_state(self, st: dict):
        super().apply_state(st)
        if "web_raw" in st:
            self._web_raw = copy.deepcopy(st["web_raw"])
        if "web_rect" in st and st["web_rect"] != self.rect():
            self.prepareGeometryChange()
            self.setRect(QRectF(st["web_rect"]))
        self.update()

    def _host(self):
        sc = self.scene()
        views = sc.views() if sc is not None else []
        return getattr(views[0], "_owner", None) if views else None

    def change_raw(self, fn):
        """원래 칸 고치기 + 되돌리기 한 칸 — fn(raw)가 raw를 고침."""
        before = self.capture_state()
        fn(self._web_raw)
        self.update()
        host = self._host()
        if host is not None and hasattr(host, "push_undo_state"):
            host.push_undo_state([(self, before)])

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setRenderHint(painter.RenderHint.TextAntialiasing)
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
        self.paint_card(painter, self.rect())
        painter.restore()
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)

    def paint_card(self, p, r: QRectF):
        raise NotImplementedError

    # 위 띠 카드(웹·문서·PDF) 공통 — 몸통 + 띠 + 테두리 + 제목 둘째 줄 + ↗ 단추
    def _paint_head_card(self, p, r, head_fill, line_c, border_c, title, sub, body):
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        H = min(WEB_HEAD, h)
        clip = QPainterPath()
        clip.addRoundedRect(r, self.RADIUS, self.RADIUS)
        p.save()
        p.setClipPath(clip)
        p.fillRect(r, QColor("#ffffff"))
        p.fillRect(QRectF(x, y, w, H), QColor(head_fill))
        if h - H > 0:
            body(p, QRectF(x, y + H, w, h - H))
        p.restore()
        if h - H > 0:
            p.setPen(QPen(QColor(line_c), 1))
            p.drawLine(QPointF(x, y + H), QPointF(x + w, y + H))
        p.setPen(QPen(QColor(border_c), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, self.RADIUS, self.RADIUS)
        s = 24
        ob = QRectF(x + w - s - 8, y + (WEB_HEAD - s) / 2, s, s)   # 웹 openBtnRect
        tw = w - ob.width() - 26
        _text(p, x + 10, y + 15, title, 13, "#18181b", 700, tw)
        _text(p, x + 10, y + 31, sub, 10, "#71717a", 400, tw)
        p.setPen(QPen(QColor("#d4d4d8"), 1))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(ob, 5, 5)
        arrow = QPainterPath(QPointF(ob.x() + 10, ob.y() + 7))
        arrow.lineTo(ob.x() + 17, ob.y() + 7)
        arrow.lineTo(ob.x() + 17, ob.y() + 14)
        arrow.moveTo(ob.x() + 17, ob.y() + 7)
        arrow.lineTo(ob.x() + 8, ob.y() + 16)
        pen = QPen(QColor("#52525b"), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(arrow)


class _FrameItem(_WebItem):
    """프레임 — 얇은 테두리 + 위 왼쪽 이름표(웹 render.jsx 'frame'). 속은 비어 안의 것을 고를 수 있음."""
    _seq = 0

    def __init__(self, rect, raw):
        super().__init__(rect, raw)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        _FrameItem._seq += 1
        self._order = _FrameItem._seq   # 문서 차례(같은 번호끼리 앞뒤)

    def _page(self):
        """출력·발표 차례(1부터) — 웹 edit.js orderedFrames와 같게: 저장된 번호, 같으면 문서 차례. 장면 밖이면 저장된 번호."""
        sc = self.scene()
        if sc is None:
            return self._web_raw.get("no")
        key = lambda f: (f._web_raw.get("no") if f._web_raw.get("no") is not None else 1e9, f._order)   # noqa: E731
        frames = sorted((it for it in sc.items() if isinstance(it, _FrameItem)), key=key)
        return frames.index(self) + 1

    def _tag(self, page=None):
        r = self.rect()
        fs = max(12.0, min(r.width(), r.height()) * 0.03)   # 웹 frameTagFs
        no, name = self._page() if page is None else page, self._web_raw.get("name")
        tag = f"{'' if no is None else no}{' · ' + name if name else ''}" or "프레임"
        return fs, tag

    def plain_text(self):
        return self._tag(getattr(self, "_last_page", None) or self._web_raw.get("no"))[1]

    def _content_rect(self):
        # 크기 계산에선 장면을 훑지 않음(장면이 크기를 물을 때 또 장면을 훑어 끝없이 돌았음) — 마지막으로 그린 번호, 넉넉히 세 자리
        r = super()._content_rect()
        fs, tag = self._tag(getattr(self, "_last_page", None) or 100)
        tw = QFontMetricsF(_font(fs, 600)).horizontalAdvance(tag) + fs
        return r.united(QRectF(self.rect().x(), self.rect().y() - fs * 1.7, tw, fs * 1.7))

    def paint_card(self, p, r):
        pen = QPen(QColor("#8a98a8"), 1.5)
        pen.setCosmetic(True)   # 웹 vectorEffect="non-scaling-stroke"
        p.setPen(pen)
        # 딥모드 판 = 흰 종이(웹 render.jsx `isDeepPaper` — 투명 메모 제목이 어두운 화면에 묻혔음, 2026-10-25). 그리기만 — 고르기는 그대로 테두리
        deep = self._web_raw.get("deep_plan") or self._web_raw.get("deep_of")
        p.setBrush(QColor("#ffffff") if deep else Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        page = self._page()
        if page != getattr(self, "_last_page", None):
            self.prepareGeometryChange()
            self._last_page = page
        fs, tag = self._tag(page)
        tw = QFontMetricsF(_font(fs, 600)).horizontalAdvance(tag) + fs
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#3f3f46"))
        p.drawRoundedRect(QRectF(r.x(), r.y() - fs * 1.7, tw, fs * 1.45), fs * 0.3, fs * 0.3)
        _text(p, r.x() + fs / 2, r.y() - fs * 0.97, tag, fs, "#ffffff", 600)


class _WebCardItem(_WebItem):
    """웹 카드 — 위 띠(제목·주소·↗) + 대표 그림(없으면 아이콘 + 설명). 칸 안 페이지는 웹 칠판에서만."""
    RADIUS = 8.0

    def paint_card(self, p, r):
        d = self._web_raw
        url = d.get("url") or ""

        def body(p, b):
            thumb = _pixmap(d.get("thumb"))
            if thumb is not None:   # 웹 preserveAspectRatio="xMidYMid slice"
                k = max(b.width() / thumb.width(), b.height() / thumb.height())
                sw, sh = b.width() / k, b.height() / k
                p.drawPixmap(b, thumb, QRectF((thumb.width() - sw) / 2, (thumb.height() - sh) / 2, sw, sh))
                return
            if not d.get("embed") and b.height() >= 30:   # 아이콘 + 설명(웹 info())
                s = min(36.0, b.height() - 16)
                icon = _pixmap(d.get("icon"))
                ir = QRectF(b.x() + 12, b.y() + (b.height() - s) / 2, s, s)
                if icon is not None:
                    p.drawPixmap(ir, icon, QRectF(icon.rect()))
                else:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor("#e4e4e7"))
                    p.drawRoundedRect(ir, s / 4, s / 4)
                    _text(p, ir.center().x(), ir.center().y(), _site(url)[:1].upper(), s / 2, "#71717a", 700, align=Qt.AlignmentFlag.AlignHCenter)
                _text(p, b.x() + s + 22, b.y() + b.height() / 2, d.get("desc") or _site(url), 12, "#52525b", 400, b.width() - s - 34)
                return
            p.fillRect(b, QColor("#e4e4e7"))
            _text(p, b.center().x(), b.center().y(), "▶" if d.get("embed") else _site(url), min(28.0, b.height() / 3), "#71717a",
                  align=Qt.AlignmentFlag.AlignHCenter)

        self._paint_head_card(p, r, "#f4f4f5", "#d4d4d8", "#a1a1aa", d.get("title") or _site(url), url, body)

    def web_double_click(self, view, scene_pos):
        url = self._web_raw.get("url")
        if url:
            QDesktopServices.openUrl(QUrl(url))
        return bool(url)


def _server_url(path: str) -> QUrl | None:
    """웹 칠판 서버의 /api/... 주소 → 전체 주소(「파일 › 웹 칠판 › 설정」의 서버 주소)."""
    try:
        from easycad.app_settings import app_settings
        from easycad.fileio import web_board
        base = str(app_settings().value("web_board/url", "") or web_board.DEFAULT_URL).rstrip("/")
    except Exception:   # 설정을 못 읽으면 열지 않음(두 번 누르기가 아무 일도 안 함)
        base = ""
    return QUrl(base + path) if base and path else None


# 움직이는 카드(§8 항목66 4단계) — 웹 `web/src/next/livecard.js`와 같은 틀: 카드 HTML 맨 앞에 CSP(인터넷 금지), 스크립트는 sandbox 칸 안에서만.
# 브라우저로 여는 페이지 자체엔 스크립트가 없어야 함(스크립트 없는 문서는 STATIC_CSP로 끔). 글을 바꾸면 웹도 — `test_part74`가 두 파일이 같은지 봄
LIVE_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:"
STATIC_CSP = "default-src 'none'; style-src 'unsafe-inline' https:; img-src data: blob: https: http:; font-src data: https:"
LIVE_MAX = 200_000
_KICK = "<script>addEventListener('load',()=>(function k(){innerWidth?dispatchEvent(new Event('resize')):requestAnimationFrame(k)})())</script>"


def _head(csp: str) -> str:
    return f'<!doctype html><meta http-equiv="Content-Security-Policy" content="{csp}"><meta charset="utf-8">'


def _body(html: str) -> str:
    return re.sub(r"^\s*(?:<!--.*?-->\s*)*<!doctype[^>]*>", "", html or "", flags=re.I | re.S)


def live_fits(d: dict) -> bool:
    return bool(d.get("live")) and bool(d.get("html")) and len(d["html"]) <= LIVE_MAX


def big_page(d: dict) -> str:
    """두 번 누르기로 브라우저에 열 페이지 — 웹 `bigPage`와 같은 글."""
    if not live_fits(d):
        return _head(STATIC_CSP) + _body(d.get("html"))
    inner = _head(LIVE_CSP) + _KICK + _body(d["html"])
    return (_head(LIVE_CSP) + f"<title>{_html.escape(d.get('title') or '인터랙티브 HTML')}</title>"
            "<style>html,body{margin:0;height:100%;background:#fff}iframe{border:0;width:100%;height:100%;display:block}</style>"
            f'<iframe sandbox="allow-scripts" csp="{LIVE_CSP}" srcdoc="{_html.escape(inner, quote=True)}"></iframe>')


class _DocItem(_WebItem):
    """정리 문서 카드(「정리해 줘」 ①) — 보라 띠 + 자리 글. 두 번 누르기 = 문서를 브라우저로(HTML을 임시 파일로).
    움직이는 카드(`live`)도 같은 카드 — 칠판 안에선 자리 글, 두 번 누르기 = 브라우저에서 움직임(스크립트는 틀 안에서만)."""
    RADIUS = 6.0

    def paint_card(self, p, r):
        d = self._web_raw
        lv = bool(d.get("live"))

        def body(p, b):
            p.fillRect(b, QColor("#fafafa"))
            msg = ("▶ 인터랙티브 HTML — 두 번 누르면 브라우저에서 움직여요" if live_fits(d) else "▶ 인터랙티브 HTML — 너무 커서 못 띄워요") if lv else "📄 정리 문서 — 웹 칠판에서 크게 보기·인쇄"
            _text(p, b.center().x(), b.center().y(), msg, min(16.0, b.height() / 6), "#8a8f98",
                  max_w=b.width() - 16, align=Qt.AlignmentFlag.AlignHCenter)

        sub = f"HTML 파일 · {d['file']}" if d.get("file") else f"{'인터랙티브 HTML' if lv else '정리 문서'} · KAIROS {d.get('model') or ''}"
        self._paint_head_card(p, r, "#f5f3ff", "#ddd6fe", "#a78bfa", ("▶ " if lv else "📄 ") + (d.get("title") or ("인터랙티브 HTML" if lv else "정리 문서")), sub, body)

    def web_double_click(self, view, scene_pos):
        html = self._web_raw.get("html")
        if not html:
            return False
        import os
        import tempfile
        path = os.path.join(tempfile.gettempdir(), f"easycad_doc_{abs(hash(html)) % 10**8}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(big_page(self._web_raw))   # 끌어 놓은 HTML 파일 속 스크립트도 끔(웹 「크게 보기」와 같게)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return True


class _PdfItem(_WebItem):
    """PDF 보기 카드 — 빨강 띠 + 첫 쪽 작은 그림. 쪽 넘겨 보기는 웹 칠판에서(두 번 누르기 = 원본을 브라우저로)."""
    RADIUS = 6.0

    def paint_card(self, p, r):
        d = self._web_raw

        def body(p, b):
            p.fillRect(b, QColor("#e4e4e7"))
            thumb = _pixmap(d.get("thumb"))
            if thumb is not None:   # 웹 xMidYMin meet, 높이 = 첫 쪽 비율
                sz = (d.get("sizes") or [[0, 0]])[0]
                th = b.width() * sz[1] / sz[0] if sz and sz[0] else b.height()
                k = min(b.width() / thumb.width(), th / thumb.height())
                dw, dh = thumb.width() * k, thumb.height() * k
                p.drawPixmap(QRectF(b.x() + (b.width() - dw) / 2, b.y(), dw, dh), thumb, QRectF(thumb.rect()))

        self._paint_head_card(p, r, "#fef2f2", "#fecaca", "#f87171", "📕 " + (d.get("name") or "PDF"), f"PDF · {d.get('pages') or 0}쪽", body)

    def web_double_click(self, view, scene_pos):
        u = _server_url(self._web_raw.get("url") or "")
        if u is None:
            return False
        QDesktopServices.openUrl(u)
        return True


class _LegendItem(_WebItem):
    """범례 — 제목 + 표(견본 선 | 이름 | 모양). 줄은 저장된 것 그대로(도면 따라 저절로 바뀌는 건 웹 칠판)."""
    RADIUS = 8.0

    def plain_text(self):
        rows = [f"{self._name(e)} · {STYLE_NAMES.get(e.get('style'), '실선')} · {e.get('width')}px" for e in self._rows()]
        return "\n".join([self._web_raw.get("title") or "범례", *rows])

    def _rows(self):
        return self._web_raw.get("rows") or []

    def _name(self, e):
        return (self._web_raw.get("names") or {}).get(e.get("key"), color_name(e.get("color")))

    def paint_card(self, p, r):
        L, rows = LEGEND, self._rows()
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        px = L["FONT"]
        fm, fmb = QFontMetricsF(_font(px)), QFontMetricsF(_font(px, 600))
        desc = lambda e: f"{STYLE_NAMES.get(e.get('style'), '실선')} · {e.get('width')}px"   # noqa: E731
        name_w = max([fmb.horizontalAdvance("이름")] + [fm.horizontalAdvance(self._name(e)) for e in rows])
        c0 = L["PAD"]
        c1 = c0 + L["SAMPLE"] + L["GAP"]
        c2 = c1 + name_w + L["GAP"] * 2
        ty = y + L["HEAD"]
        row_y = lambda j: ty + L["ROW"] * (j + 1)   # noqa: E731
        p.setPen(QPen(QColor("#d4d4d8"), 1))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(r, 8, 8)
        _text(p, x + L["PAD"], y + L["HEAD"] / 2 + 1, self._web_raw.get("title") or "범례", L["TITLE"], "#18181b", 700)
        p.fillRect(QRectF(x + 1, ty, w - 2, L["ROW"]), QColor("#f4f4f5"))
        for t, cx in (("견본", c0), ("이름", c1), ("모양", c2)):
            _text(p, x + cx, ty + L["ROW"] / 2, t, px - 1, "#71717a", 600)
        p.setPen(QPen(QColor("#e4e4e7"), 1))
        for j in [0, *range(1, len(rows) + 1)]:
            p.drawLine(QPointF(x, row_y(j)), QPointF(x + w, row_y(j)))
        p.drawLine(QPointF(x, ty), QPointF(x + w, ty))
        for cx in (c1 - L["GAP"] / 2, c2 - L["GAP"]):
            p.drawLine(QPointF(x + cx, ty), QPointF(x + cx, row_y(len(rows))))
        for j, e in enumerate(rows):
            cy = row_y(j) + L["ROW"] / 2
            col = _color(e.get("color"), "#ff000000")
            wd = float(e.get("width") or 1)
            hw, sw = min(wd, 4), min(wd, 6)
            x1, x2 = x + c0, x + c0 + L["SAMPLE"]
            pen = QPen(col, sw)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            if e.get("style") in DASH:   # 웹 dashArray = 무늬 × 굵기(Qt 무늬는 이미 굵기 배수)
                pen.setDashPattern([float(v) for v in DASH[e["style"]]])
            p.setPen(pen)
            p.drawLine(QPointF(x1, cy), QPointF(x2 - (6 + hw if e.get("arrow") else 0), cy))
            if e.get("arrow"):
                tri = QPainterPath(QPointF(x2, cy))
                tri.lineTo(x2 - 8 - hw, cy - 4 - hw / 2)
                tri.lineTo(x2 - 8 - hw, cy + 4 + hw / 2)
                tri.closeSubpath()
                p.fillPath(tri, col)
            _text(p, x + c1, cy, self._name(e), px, "#27272a")
            _text(p, x + c2, cy, desc(e), px, "#71717a")
        if not rows:
            _text(p, x + L["PAD"], row_y(0) + L["ROW"] / 2, "색 있는 선·화살표를 그리면 저절로 채워져요", px, "#71717a")


class _MemoItem(_MemoLinesMixin, _WebItem):
    """메모 — 채운 둥근 네모 + 줄마다 글(제목·목록·할 일·인용·코드). 줄 배치는 웹 memo.js를 옮김.
    두 번 누르기 = 메모 자리에서 고치기(`core_memo_edit._MemoTextEdit`), 할 일 상자 누르기 = 체크,
    줄 손잡이 ⠿·줄 고르기·끌어 옮기기는 `core_memo_lines._MemoLinesMixin`."""
    RADIUS = 10.0

    def __init__(self, rect, raw):
        super().__init__(rect, raw)
        self.setBrush(QBrush(_color(raw.get("fill"), "#ffffffff")))   # 속성 카드 「채움」이 메모 바탕색을 보이게

    def apply_fill(self, color):
        """속성 카드 「채움」 = 메모 바탕색(웹 칸 `fill`) — 투명은 흰색으로(메모는 늘 채운 카드)."""
        q = QColor(color) if color is not None else QColor("#ffffff")
        self._web_raw["fill"] = "#" + format(q.rgba() & 0xFFFFFFFF, "08x")
        self.setBrush(QBrush(q))
        self.update()

    def plain_text(self):
        from easycad.canvas.core_memo import lines_to_md
        return lines_to_md(self._web_raw.get("lines"))

    def setRect(self, *args):
        """폭이 바뀌면(크기 손잡이·되돌리기) 높이를 글에 맞춤 — 웹 메모와 같게(전엔 줄이 더 꺾여도 높이가 그대로라 글이 넘쳤음).
        폭이 같으면 그대로(웹이 저장한 높이를 열 때 바꾸지 않음 — 왕복 시험)."""
        r = QRectF(*args) if len(args) == 4 else QRectF(args[0])
        if abs(r.width() - self.rect().width()) > 0.5:
            from easycad.canvas.core_memo import memo_layout
            r = QRectF(r.x(), r.y(), r.width(), memo_layout(self._web_raw, r.width())["h"])
        super().setRect(r)

    def _fit_height(self, raw):
        """높이를 글에 맞춤(웹 메모처럼 — 줄을 더하면 늘고 지우면 줆)."""
        from easycad.canvas.core_memo import memo_layout
        h = memo_layout(raw, self.rect().width())["h"]
        r = self.rect()
        if abs(h - r.height()) > 0.5:
            self.prepareGeometryChange()
            self.setRect(QRectF(r.x(), r.y(), r.width(), h))

    def set_lines(self, lines):
        def fn(raw):
            raw["lines"] = lines
            self._fit_height(raw)
        self.change_raw(fn)

    def web_double_click(self, view, scene_pos, caret=None, at=None):
        """caret = 커서를 둘 줄 번호(고른 줄에서 Enter — 그 줄 끝), at = 두 번 누른 자리(장면 좌표 — 그 글자에 커서, 웹 spec.at), 둘 다 없으면 맨 끝."""
        if getattr(self, "_editor", None) is not None:   # 이미 고치는 중
            return True
        from easycad.canvas.core_memo_edit import _MemoTextEdit
        self.set_line_sel(None)
        self._hov = None
        self._edit_rect0 = QRectF(self.rect())
        self._editor = _MemoTextEdit(self)
        view._memo_editor = self._editor
        self.update()
        self._editor.start(caret)
        if at is not None and caret is None:
            self._editor.place_caret(self._editor.mapFromScene(at))
        return True

    def _end_edit(self, editor, new_lines):
        """고치기 끝 — 글 상자를 떼고, 바뀌었으면 메모 줄로 저장(되돌리기 한 칸 — 고치기 전 크기부터)."""
        if self._editor is not editor:
            return
        self._editor = None
        sc = editor.scene()
        editor.setParentItem(None)
        if sc is not None:
            sc.removeItem(editor)
        r0 = self._edit_rect0
        self.prepareGeometryChange()
        super().setRect(r0)   # 고치는 동안 늘었던 높이를 되돌린 뒤 기록(되돌리기가 고치기 전 모습으로)
        if new_lines is not None and new_lines != self._web_raw.get("lines"):
            self.set_lines(new_lines)
        self.update()

    def toggle_todo_at(self, local: QPointF) -> bool:
        """local(아이템 좌표)에 할 일 상자가 있으면 체크를 바꾸고 True."""
        from easycad.canvas.core_memo import todo_at
        r = self.rect()
        i = todo_at(self._web_raw, r.width(), local - r.topLeft())
        if i is None:
            return False

        def fn(raw):
            lines = [dict(l) for l in raw.get("lines") or []]
            if lines[i].get("done"):
                lines[i].pop("done", None)
            else:
                lines[i]["done"] = True
            raw["lines"] = lines
        self.change_raw(fn)
        return True

    def paint_card(self, p, r):
        d = self._web_raw
        p.setPen(QPen(_color(d.get("pen"), "#ffd4d4d8"), 1))
        p.setBrush(_color(d.get("fill"), "#ffffffff"))
        p.drawRoundedRect(r, 10, 10)
        if getattr(self, "_editor", None) is not None:   # 고치는 중 = 글은 편집 글 상자가 그림(손잡이 ⠿만)
            self.paint_edit_handle(p)
            return
        from easycad.canvas.core_memo import paint_memo
        paint_memo(p, r, d)
        self.paint_lines_ui(p, r)


_CLASSES = {"frame": _FrameItem, "web": _WebCardItem, "doc": _DocItem, "pdf": _PdfItem, "legend": _LegendItem, "memo": _MemoItem}


def web_item_from_dict(d: dict, raw: dict):
    """.ecad 칸 → 웹 종류 아이템(자리·크기·묶음 등 공통 칸은 `document._apply_common`이 씀)."""
    return _CLASSES[d["type"]](QRectF(*d["rect"]), raw)
