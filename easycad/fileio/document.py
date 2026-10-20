"""네이티브 문서 저장/열기 (.ecad = JSON).

계획서 §3.B의 '문서모델 씨앗' — 각 QGraphics 아이템을 타입+기하+스타일로 직렬화한다.
이 구조가 Phase 3에서 DXF 엔티티 매핑의 기반이 된다(각 객체가 의미정보를 지님).

지원 타입: rect · ellipse · line · path(펜) · arrow(2점 베지어) · text · badge(번호)
공통: 위치·스케일·회전·z·변환원점.
"""
import base64
import json

from easycad.fileio.safe_write import write_via_temp

from PyQt6.QtCore import Qt, QRectF, QLineF, QPointF, QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QColor, QPen, QBrush, QPainterPath, QPixmap

from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem,
    _PolyArrowItem, _SymbolItem, _ImageItem, _TitleBlockItem, _TableItem, _PolygonItem,
    _ConnectorLabel, _reposition_port_from_frac, _TEXT, _GroupBindProxy, _BoardItem,
)

FORMAT = "easycad-doc"
VERSION = 1


def _col(c: QColor) -> str:
    return c.name(QColor.NameFormat.HexArgb)


def _label_to_dict(lbl) -> dict:
    """[우리 확장] 라벨 하나(_TextItem/_ConnectorLabel)를 dict로 — 도형 중앙 라벨(단수 "label")과
    화살표 라벨(복수 "labels") 양쪽이 공유한다. 화살표 라벨(`_conn_t`/`_conn_off` 보유)만
    경로 위 위치(t)+수직 오프셋(off)을 추가로 담는다(FigJam/Lucid 드래그)."""
    bg = lbl._bg
    d = {
        "text": lbl.toPlainText(),
        "color": _col(lbl.defaultTextColor()),
        # 중앙 라벨은 도형에 맞춰 렌더 폰트가 축소될 수 있으니 '기준' 크기(_base_pt)를 저장.
        "font": getattr(lbl, "_base_pt", lbl.font().pointSize()),
        "bg": None if bg is None else [bg.red(), bg.green(), bg.blue(), bg.alpha()],
    }
    runs = lbl.text_runs() if hasattr(lbl, "text_runs") else []
    if runs:   # [§8 항목60] 라벨 안 부분 강조·형광펜 — 없으면 키 생략(하위호환)
        d["runs"] = runs
    from easycad.fonts import BOARD_FONT
    if lbl.font().family() == BOARD_FONT:   # [§8 항목60] 보드 흐름도 상자 글꼴 — 다시 열면 앱 기본으로 돌아갔다
        d["family"] = BOARD_FONT
    if isinstance(lbl, _ConnectorLabel):
        d["t"] = getattr(lbl, "_conn_t", 0.5)
        d["off"] = getattr(lbl, "_conn_off", 0.0)
    return d


def _label_family(lbl, d: dict):
    """저장된 라벨 글꼴(보드 글꼴만 저장됨)을 되살린다."""
    if d.get("family"):
        from easycad.fonts import ensure_fonts
        ensure_fonts()
        f = lbl.font()
        f.setFamily(d["family"])
        lbl.setFont(f)


# ---- 공통 변환 -------------------------------------------------------------
def _common(it) -> dict:
    o = it.transformOriginPoint()
    d = {
        "pos": [it.pos().x(), it.pos().y()],
        "scale": it.scale(),
        "rotation": it.rotation(),
        "z": it.zValue(),
        "origin": [o.x(), o.y()],
        # [편의기능] 잠금·그룹 — 기본값(미잠금·무그룹)이면 어차피 로드 시 getattr 기본과 같지만
        # 명시 저장이 더 단순·안전하다(다른 pen/style 필드와 동일 관례).
        "locked": getattr(it, "_locked", False),
        "group_id": getattr(it, "_group_id", None),
        "layer_id": getattr(it, "_layer_id", None),   # [신규기능] 레이어 — None=기본 레이어
    }
    # [§8 항목56 검토 2026-10-17] AI 보드 안 아이템의 설계서 자리·칸 바탕 표시 — 없으면 키 생략(하위호환).
    # 저장 안 하면 다시 연 보드에서 「선택 N개」가 무엇을 골랐는지 AI에 못 알리고, 칸 바탕 더블클릭으로 보드 안에 못 들어갔다.
    if getattr(it, "_pb_part", None):
        d["pb_part"] = it._pb_part
    if getattr(it, "_pb_card", False):
        d["pb_card"] = True
    if getattr(it, "_pb_piece", None):   # [§8 항목59 ②] 펼친 조각 틀의 블록 설계서 — 다시 열어도 「보드로 정리」
        d["pb_piece"] = it._pb_piece
    return d


def _apply_common(it, d: dict):
    it.setPos(QPointF(*d["pos"]))
    it.setTransformOriginPoint(QPointF(*d.get("origin", [0.0, 0.0])))
    sc = d.get("scale", 1.0)
    it.setScale(sc if sc else 1.0)
    it.setRotation(d.get("rotation", 0.0))
    it.setZValue(d.get("z", 0))
    it._group_id = d.get("group_id")
    it._layer_id = d.get("layer_id")
    if d.get("pb_part"):   # [§8 항목56 검토] AI 보드 안 설계서 자리 — `_common` 참조
        it._pb_part = d["pb_part"]
    if d.get("pb_card"):
        it._pb_card = True
    if d.get("pb_piece"):
        it._pb_piece = d["pb_piece"]
    locked = d.get("locked", False)
    it._locked = locked
    it.setFlags(
        it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable
    )
    if locked:   # [편의기능] 잠금 상태로 저장된 아이템은 로드 시에도 움직이지 않게
        it.setFlag(it.GraphicsItemFlag.ItemIsMovable, False)
        it.setFlag(it.GraphicsItemFlag.ItemIsSelectable, False)
    return it


# ---- [신규기능 §8-12] 포트(장비 테두리에 부착된 자식 사각/원) 직렬화 -----------
# 최상위 아이템 목록에는 안 실린다(Qt 자식이라 라벨과 동일하게 부모 dict 안에 중첩) —
# save_document()의 "parentItem() is None" 필터가 이미 포트를 최상위에서 자동 제외한다.
def _port_to_dict(port) -> dict:
    r = port.rect()
    return {
        "shape": "circle" if isinstance(port, _EllipseItem) else "rect",
        "size": [r.width(), r.height()],
        "pen": _col(port.pen().color()), "width": port.pen().widthF(),
        "fill": None if port.brush().style() == Qt.BrushStyle.NoBrush
        else _col(port.brush().color()),
        "frac": list(getattr(port, "_port_frac", (0.5, 0.0))),
    }


def _port_from_dict(pd: dict, host):
    w, h = pd.get("size", [18.0, 18.0])
    cls = _EllipseItem if pd.get("shape") == "circle" else _RectItem
    port = cls(QRectF(0.0, 0.0, w, h))
    port.setPen(_mkpen(pd))
    port.setBrush(_mkbrush(pd))
    port.setFlags(port.GraphicsItemFlag.ItemIsMovable | port.GraphicsItemFlag.ItemIsSelectable
                  | port.GraphicsItemFlag.ItemSendsGeometryChanges)
    port.setParentItem(host)
    port._port_host = host
    port._port_frac = tuple(pd.get("frac", [0.5, 0.0]))
    ports = getattr(host, "_ports", None)
    if ports is None:
        ports = host._ports = []
    ports.append(port)
    _reposition_port_from_frac(port)
    return port


def _mkpen(d: dict) -> QPen:
    pen = QPen(QColor(d["pen"]))
    pen.setWidthF(float(d.get("width", 1.0)))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    st = d.get("style")   # [M2 #2] 선스타일(실선/점선…) — 하위호환: 없으면 기본(실선) 유지
    if st is not None:
        pen.setStyle(Qt.PenStyle(int(st)))
    return pen


def _mkbrush(d: dict) -> QBrush:
    fill = d.get("fill")
    return QBrush(QColor(fill)) if fill else QBrush(Qt.BrushStyle.NoBrush)


def _apply_arrow_style(it, d: dict):
    """[M2 #3] 화살표(_ArrowItem/_PolyArrowItem)에 몸통 선스타일 복원.
    화살표는 pen()이 없어 _mkpen 경로를 못 타므로 _style을 직접 세팅한다.
    하위호환: style 키가 없으면 기본(SolidLine) 유지."""
    st = d.get("style")
    if st is not None:
        it._style = Qt.PenStyle(int(st))


# ---- 삽입 이미지 base64 embed (단일 .ecad 이동에도 이미지가 안 깨지게) ----------
def _pixmap_to_b64(pm: QPixmap) -> str:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")   # 원본 해상도 그대로 PNG 인코딩(무손실)
    buf.close()
    return base64.b64encode(bytes(ba)).decode("ascii")


def _b64_to_pixmap(s: str) -> QPixmap:
    pm = QPixmap()
    pm.loadFromData(base64.b64decode(s), "PNG")
    return pm


# ---- 펜(자유곡선) 경로 직렬화 ---------------------------------------------
def _path_elems(path: QPainterPath) -> list:
    out = []
    i, n = 0, path.elementCount()
    ET = QPainterPath.ElementType
    while i < n:
        e = path.elementAt(i)
        if e.type == ET.MoveToElement:
            out.append(["M", e.x, e.y]); i += 1
        elif e.type == ET.LineToElement:
            out.append(["L", e.x, e.y]); i += 1
        elif e.type == ET.CurveToElement:
            c2 = path.elementAt(i + 1)
            ep = path.elementAt(i + 2)
            out.append(["C", e.x, e.y, c2.x, c2.y, ep.x, ep.y]); i += 3
        else:
            i += 1
    return out


def _elems_to_path(elems: list) -> QPainterPath:
    p = QPainterPath()
    for e in elems:
        k = e[0]
        if k == "M":
            p.moveTo(e[1], e[2])
        elif k == "L":
            p.lineTo(e[1], e[2])
        elif k == "C":
            p.cubicTo(e[1], e[2], e[3], e[4], e[5], e[6])
    return p


# ---- 아이템 ↔ dict --------------------------------------------------------
def item_to_dict(it) -> dict | None:
    d = _common(it)
    if isinstance(it, _TitleBlockItem):
        d.update(type="titleblock", size=it._size, orient=it._orient,
                 fields=dict(it._fields))
        if getattr(it, "_plain", False):   # [§8 항목33] 빈 용지틀 — 없으면 키 생략(하위호환)
            d["plain"] = True
    elif isinstance(it, _BoardItem):   # [§8 항목53] 보드 틀
        r = it.rect()
        d.update(type="board", rect=[r.x(), r.y(), r.width(), r.height()], bg=_col(it.bg()))
        if getattr(it, "_set_id", None):   # 여러 장 묶음(4단계) — PDF 여러 쪽 순서
            d.update(set=it._set_id, page=it._page)
        if getattr(it, "_ai", None):   # AI 보드의 설계서·요청 정보 — 다시 열어도 보드 막대로 이어 고치기(2026-10-16)
            d["ai"] = dict(it._ai)
    elif isinstance(it, _TableItem):
        r = it.rect()
        d.update(type="table", rows=it._rows, cols=it._cols, header=it._header,
                 rect=[r.x(), r.y(), r.width(), r.height()],
                 cells=[row[:] for row in it._cells],
                 col_widths=list(it._col_widths))
    elif isinstance(it, _ImageItem):
        r = it.rect()
        d.update(type="image", rect=[r.x(), r.y(), r.width(), r.height()],
                 data=_pixmap_to_b64(it._pixmap))
    elif isinstance(it, _ArrowItem):
        d.update(
            type="arrow",
            p1=[it._p1.x(), it._p1.y()], p2=[it._p2.x(), it._p2.y()],
            ctrl1=None if it._ctrl1 is None else [it._ctrl1.x(), it._ctrl1.y()],
            ctrl2=None if it._ctrl2 is None else [it._ctrl2.x(), it._ctrl2.y()],
            color=_col(it._color), width=it._width, head=it._head_at_end,
            head_start=it._head_at_start,   # [양방향 화살표, 2026-08-21]
            head_scale=it._head_scale,   # [화살촉 크기 배율, 2026-08-21]
            style=int(it._style.value),   # [M2 #3] 몸통 선스타일(점선 등)
        )
    elif isinstance(it, _SymbolItem):
        r = it.rect()
        d.update(type="symbol", kind=it._kind, rect=[r.x(), r.y(), r.width(), r.height()],
                 pen=_col(it.pen().color()), width=it.pen().widthF(),
                 fill=None if it.brush().style() == Qt.BrushStyle.NoBrush
                 else _col(it.brush().color()))
    elif isinstance(it, _PolygonItem):
        # [§8 항목21] rect는 리사이즈 상태 복원용, pts는 그 rect 기준 로컬 정점 그대로
        # (local_pts()가 정규화좌표×rect를 이미 계산해 줌 — 왕복 시 손실 없음).
        r = it.rect()
        d.update(type="polygon", closed=it._closed,
                 rect=[r.x(), r.y(), r.width(), r.height()],
                 pts=[[p.x(), p.y()] for p in it.local_pts()],
                 pen=_col(it.pen().color()), width=it.pen().widthF(),
                 fill=None if it.brush().style() == Qt.BrushStyle.NoBrush
                 else _col(it.brush().color()))
    elif isinstance(it, _RectItem):
        r = it.rect()
        d.update(type="rect", rect=[r.x(), r.y(), r.width(), r.height()],
                 pen=_col(it.pen().color()), width=it.pen().widthF(),
                 fill=None if it.brush().style() == Qt.BrushStyle.NoBrush
                 else _col(it.brush().color()))
        if getattr(it, "_radius", 0):   # [2026-10-18] 모서리 둥글기 — 없으면 키 생략(하위호환)
            d["radius"] = it._radius
    elif isinstance(it, _EllipseItem):
        r = it.rect()
        d.update(type="ellipse", rect=[r.x(), r.y(), r.width(), r.height()],
                 pen=_col(it.pen().color()), width=it.pen().widthF(),
                 fill=None if it.brush().style() == Qt.BrushStyle.NoBrush
                 else _col(it.brush().color()))
    elif isinstance(it, _PolyArrowItem):
        d.update(type="sarrow", pts=[[p.x(), p.y()] for p in it._pts],
                 color=_col(it._color), width=it._width, head=it._head_at_end,
                 head_start=it._head_at_start,   # [양방향 화살표, 2026-08-21]
                 head_scale=it._head_scale,   # [화살촉 크기 배율, 2026-08-21]
                 style=int(it._style.value),   # [M2 #3] 몸통 선스타일(점선 등)
                 auto_route=it._auto_route,   # [Stage1] 직교 자동 라우팅 상태
                 routing=it._routing,         # [M4-4] 라우팅 스타일(#4)
                 curve_r=it._curve_r,         # [M4-4 ⓑ] 곡선 엘보 반경(0=직각)
                 route_hints=[[h.x(), h.y()] for h in it._route_hints])  # [경유지 힌트(2f)]
    elif isinstance(it, _LineItem):
        ln = it.line()
        d.update(type="line", line=[ln.x1(), ln.y1(), ln.x2(), ln.y2()],
                 pen=_col(it.pen().color()), width=it.pen().widthF())
    elif isinstance(it, _PathItem):
        d.update(type="path", elements=_path_elems(it.path()),
                 pen=_col(it.pen().color()), width=it.pen().widthF())
        # [§8 항목31, 2026-10-03] 채운 패스(다른 CAD 해치 가져오기 — 구멍은 홀짝 규칙). 없으면 키 생략(하위호환).
        if it.brush().style() != Qt.BrushStyle.NoBrush:
            d["fill"] = _col(it.brush().color())
        # [실사용 요청 2026-08-25] select 유휴호버 억제 표식 — 펜으로 그렸을 때만 True.
        # SVG/DXF 폴백 곡선은 애초에 안 세우므로 키 자체를 생략(하위호환, `cuts`와 같은 관례).
        if getattr(it, "_freehand", False):
            d["freehand"] = True
    elif isinstance(it, _TextItem):
        bg = it._bg
        d.update(type="text", text=it.toPlainText(),
                 color=_col(it.defaultTextColor()), font=it.font().pointSize(),
                 bg=None if bg is None else [bg.red(), bg.green(), bg.blue(), bg.alpha()])
        if it.font().bold():   # [§8 항목58 ①] 굵게 — 없으면 키 생략(하위호환)
            d["bold"] = True
        w = it.font().weight()
        if w not in (400, 700):   # [§8 항목60 ②] 약간 굵게(600)·아주 굵게(800) — 보통·굵게는 위 bold로 충분
            d["weight"] = int(w)
        from easycad.fonts import BOARD_FONT
        if it.font().family() == BOARD_FONT:   # [§8 항목60 ②] 앱에 실은 보드 글꼴 — 다른 글꼴은 앱 기본이라 생략(하위호환)
            d["family"] = BOARD_FONT
        runs = it.text_runs()
        if runs:   # [§8 항목60 ①] 부분 강조 — 없으면 키 생략(하위호환)
            d["runs"] = runs
    elif isinstance(it, _BadgeItem):
        d.update(type="badge", number=it._number, color=_col(it._color))
    else:
        return None
    # [M2 #2] pen 기반 도형(심볼·네모·원·선·펜)의 선스타일 직렬화 — 이들만 "pen" 키를 갖는다.
    # 화살표 dash·DXF linetype은 Phase 6 M3(#3)로 별도. 기본(실선)은 저장 생략해도 무방하나
    # 명시 저장이 더 단순·안전하다(로드는 하위호환으로 없으면 실선).
    if "pen" in d:
        d["style"] = int(it.pen().style().value)
    # [우리 확장] 선·화살표·닫힌도형(네모·원·심볼)에 붙은 라벨 — 본체 dict 안에 함께 직렬화.
    if isinstance(it, (_ArrowItem, _PolyArrowItem)) and it.has_label():
        # [다중 라벨 2026-08-21] 화살표는 라벨을 여러 개 가질 수 있어 리스트("labels")로
        # 저장한다 — 옛 단수 "label" 키는 하위호환 로드 전용(아래 dict_to_item)이고, 새로
        # 저장하는 파일은 항상 "labels"만 쓴다(1개짜리도 리스트 원소 1개).
        d["labels"] = [_label_to_dict(lbl) for lbl in it._live_labels() if lbl.toPlainText().strip()]
    elif isinstance(it, (_LineItem, _SymbolItem, _RectItem, _EllipseItem, _PolygonItem)) \
            and it.has_label():
        d["label"] = _label_to_dict(it._label)
    # [신규기능 §8-12] 부착된 포트 — 라벨과 동일하게 부모 dict 안에 중첩 직렬화.
    if getattr(it, "_ports", None):
        d["ports"] = [_port_to_dict(p) for p in it._ports]
    # [§8 항목17 6단계] TRIM cut 구간(닫힌 도형: 사각·원·심볼) — (변 인덱스, t0, t1) 그대로
    # JSON 배열로. 없으면(하위호환) 키 자체를 생략 — 로드 시 getattr 기본(None)과 동일.
    if getattr(it, "_cuts", None):
        d["cuts"] = [[edge_i, t0, t1] for edge_i, t0, t1 in it._cuts]
    # [웹 칠판 2026-10-18] 웹만 아는 칸은 받은 그대로 돌려 쓴다(`dict_to_item` 참조) — 데스크톱이 열었다 저장해도 웹 카드·표 꾸밈이 안 망가지게
    for k, v in (getattr(it, "_web_extra", None) or {}).items():
        if k == "label.align":
            if "label" in d:
                d["label"]["align"] = v
        elif k == "type":   # 웹 프레임·웹 카드 — 네모로 열었던 것을 다시 frame·web으로
            d["type"] = v
            if v in ("web", "memo", "legend", "doc"):   # 보이려고 붙인 라벨(제목·주소 / 메모·범례 줄 글)은 웹에선 안 씀
                d.pop("label", None)
        elif k not in d:
            d[k] = v
    raw = getattr(it, "_web_raw", None)
    if raw is not None:   # 웹 종류(프레임·웹 카드·메모·범례) = 원래 칸 + 데스크톱이 정하는 자리·크기·묶음만. 데스크톱이 보이려고 붙인 테두리·라벨 칸은 안 남김
        return {**raw, **{k: d[k] for k in _DESK_KEYS if k in d and k != "type"}}
    return d


# [§8 항목61 ④-1] 웹 종류 — 데스크톱은 아직 대리 네모로 그림(④-3에서 똑같이), 저장은 원래 칸 통째(`_web_raw`)
_WEB_TYPES = ("frame", "web", "memo", "legend", "doc")   # doc = 정리 문서 카드(「정리해 줘」 ①, 2026-10-19)
# 데스크톱이 정하는 칸(옮기기·크기·돌리기·쌓는 순서·잠금·묶음·레이어·포트·자국·AI 보드 표시) — 웹 종류도 이것만은 데스크톱 값이 이김
_DESK_KEYS = ("type", "pos", "scale", "rotation", "z", "origin", "locked", "group_id", "layer_id", "rect", "ports", "cuts", "pb_part", "pb_card", "pb_piece")

_WEB_ONLY_KEYS_ALL =("fit_text", "chat_at", "legend", "legend_key", "uid")   # legend·legend_key = 웹 범례 표시(다시 모을 때 이름 지키기), uid = 웹 공동작업 도형 이름표(2026-10-18)


def _web_card_label(d: dict):
    """웹 카드를 데스크톱에서 볼 때 네모 안 글(제목·주소) — 저장할 땐 빼고 다시 web으로(`item_to_dict`)."""
    if d.get("type") == "memo":   # 메모 줄 → 쉬운 글(웹 memo.js `memoText`와 같은 표시)
        marks = {"h1": "# ", "h2": "## ", "h3": "### ", "ul": "• ", "quote": "│ "}
        n, out = 0, []
        for ln in d.get("lines") or []:
            k = ln.get("k", "p")
            n = n + 1 if k == "ol" else 0
            mk = f"{n}. " if k == "ol" else ("☑ " if ln.get("done") else "☐ ") if k == "todo" else marks.get(k, "")
            out.append("  " * int(ln.get("lv") or 0) + mk + (ln.get("t") or ""))
        return {"text": "\n".join(out), "color": "#ff1f1f1f", "font": 10, "bg": None, "align": "left"}
    if d.get("type") == "legend":   # [웹 칠판 2026-10-19] 범례 2판 — 줄마다 「이름 · 모양」(웹 legend.js `rowName`·`descOf`와 같은 표시)
        sn = {1: "실선", 2: "파선", 3: "점선", 4: "일점쇄선", 5: "이점쇄선"}
        rows = [f"{(d.get('names') or {}).get(e.get('key'), '선')} · {sn.get(e.get('style'), '실선')} · {e.get('width')}px" for e in d.get("rows") or []]
        return {"text": "\n".join([d.get("title") or "범례", *rows]), "color": "#ff1f1f1f", "font": 10, "bg": None, "align": "left"}
    if d.get("type") == "doc":   # 정리 문서 — 제목 + 안내(본문 HTML은 웹 칠판에서 봄)
        return {"text": f"📄 {d.get('title') or '정리 문서'}\n(웹 칠판에서 보기·인쇄)", "color": "#ff1f1f1f", "font": 11, "bg": None}
    if d.get("type") != "web":
        return None
    return {"text": ((d.get("title") or "") + "\n" + (d.get("url") or "")).strip(), "color": "#ff18181b", "font": 10, "bg": None}


_WEB_ONLY_KEYS ={"table": ("font", "color", "pen", "cell_styles", "cell_runs", "row_heights"), "image": ("alt",)}  # row_heights = 행 높이 비율(웹 2026-10-18, 데스크톱은 같은 높이로 그림)


def dict_to_item(d: dict):
    t = d.get("type")
    if t == "titleblock":
        it = _TitleBlockItem(d.get("size", "A2"), d.get("orient", "landscape"),
                             d.get("fields"), d.get("plain", False))
    elif t == "table":
        it = _TableItem(d.get("rows", 1), d.get("cols", 1), QRectF(*d["rect"]),
                        d.get("cells"), d.get("header", True), d.get("col_widths"))
    elif t == "image":
        it = _ImageItem(_b64_to_pixmap(d["data"]), QRectF(*d["rect"]))
    elif t == "arrow":
        it = _ArrowItem(QColor(d["color"]), d["width"], d.get("head", True),
                        d.get("head_start", False),   # [양방향 화살표] 하위호환 기본 False
                        d.get("head_scale", 1.0))     # [화살촉 크기 배율] 하위호환 기본 1.0
        it.set_points(QPointF(*d["p1"]), QPointF(*d["p2"]))
        if d.get("ctrl1") is not None:
            it._ctrl1 = QPointF(*d["ctrl1"])
            it._ctrl2 = QPointF(*d["ctrl2"])
        _apply_arrow_style(it, d)   # [M2 #3] 하위호환: 없으면 solid 유지
    elif t == "board":
        it = _BoardItem(QRectF(*d["rect"]), QColor(d.get("bg", "#ffffffff")))
        if d.get("set"):
            it._set_id, it._page = d["set"], int(d.get("page", 1))
        if isinstance(d.get("ai"), dict):
            it._ai = dict(d["ai"])
    elif t == "symbol":
        it = _SymbolItem(d.get("kind", "decision"), QRectF(*d["rect"]))
        it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
    elif t == "polygon":
        pts = [QPointF(*xy) for xy in d["pts"]]
        it = _PolygonItem(pts, d.get("closed", True), rect=QRectF(*d["rect"]))
        it.setPen(_mkpen(d))
        if it._closed:
            it.setBrush(_mkbrush(d))
    elif t == "frame":   # [웹 칠판 2026-10-18] 프레임(출력 한 쪽·슬라이드 영역) — 데스크톱은 아직 모름: 점선 네모로 보이고, 저장할 때 다시 frame으로(`_web_extra["type"]`)
        fd = {"pen": "#ff8a98a8", "width": 1.5, "style": 2, "fill": None}
        it = _RectItem(QRectF(*d["rect"])); it.setPen(_mkpen(fd)); it.setBrush(_mkbrush(fd))
    elif t == "web":   # [웹 칠판 2026-10-18] 웹 카드(유튜브·웹페이지) — 데스크톱은 아직 모름: 제목·주소를 적은 네모로 보이고, 저장할 때 다시 web으로
        wd = {"pen": "#ffa1a1aa", "width": 1.0, "style": 1, "fill": "#fff4f4f5"}
        it = _RectItem(QRectF(*d["rect"])); it.setPen(_mkpen(wd)); it.setBrush(_mkbrush(wd)); it._radius = 8.0
    elif t == "memo":   # [웹 칠판 2026-10-18] 메모(줄마다 제목·목록·할 일·코드·인용) — 데스크톱은 아직 모름: 줄 글을 적은 둥근 네모로 보이고, 저장할 때 다시 memo로
        md = {"pen": "#ffd4d4d8", "width": 1.0, "style": 1, "fill": d.get("fill") or "#ffffffff"}
        it = _RectItem(QRectF(*d["rect"])); it.setPen(_mkpen(md)); it.setBrush(_mkbrush(md)); it._radius = 10.0
    elif t == "doc":   # [웹 칠판 2026-10-19] 정리 문서 카드(AI가 쓴 HTML 한 장) — 데스크톱은 아직 모름: 제목을 적은 네모로 보이고, 저장은 원래 칸 통째(`_web_raw`)
        dd = {"pen": "#ffa1a1aa", "width": 1.0, "style": 1, "fill": "#ffffffff"}
        it = _RectItem(QRectF(*d["rect"])); it.setPen(_mkpen(dd)); it.setBrush(_mkbrush(dd)); it._radius = 6.0
    elif t == "legend":   # [웹 칠판 2026-10-19] 범례 2판(표 모양, 줄은 도면에서 저절로) — 데스크톱은 아직 모름: 줄 글을 적은 둥근 네모로 보이고, 저장할 때 다시 legend로
        ld = {"pen": "#ffd4d4d8", "width": 1.0, "style": 1, "fill": "#ffffffff"}
        it = _RectItem(QRectF(*d["rect"])); it.setPen(_mkpen(ld)); it.setBrush(_mkbrush(ld)); it._radius = 8.0
    elif t == "rect":
        it = _RectItem(QRectF(*d["rect"])); it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
        it._radius = float(d.get("radius") or 0)
    elif t == "ellipse":
        it = _EllipseItem(QRectF(*d["rect"])); it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
    elif t == "sarrow":
        it = _PolyArrowItem(QColor(d["color"]), d["width"], d.get("head", True),
                            d.get("head_start", False),   # [양방향 화살표] 하위호환 기본 False
                            d.get("head_scale", 1.0))     # [화살촉 크기 배율] 하위호환 기본 1.0
        it._pts = [QPointF(*xy) for xy in d["pts"]]
        it._auto_route = d.get("auto_route", False)   # [Stage1] 직교 자동 라우팅 상태
        # [M4-4] 라우팅 스타일 — 신규 필드. 옛 파일은 auto_route→ortho / 아니면 straight로 유추(무손실).
        raw_routing = d.get("routing", "ortho" if it._auto_route else "straight")
        # [M4-4 · 통합] 옛 3값(straight/ortho/ortho_curved) → 2값. 각짐/둥긂은 반경이 소유하므로
        # ⚠ 옛 "ortho"(=직각 엘보)는 반경 0으로 읽어야 예전 그대로 각지게 렌더된다(기본값 10을 쓰면
        # 옛 도면의 직각 커넥터가 전부 둥글어진다). 옛 "ortho_curved"는 기본 반경.
        it._routing = "straight" if raw_routing == "straight" else "ortho"
        it._route_hints = [QPointF(*xy) for xy in d.get("route_hints", [])]  # [경유지 힌트(2f)]
        it._curve_r = float(d.get("curve_r", 0.0 if raw_routing == "ortho" else it._CORNER_R))
        _apply_arrow_style(it, d)   # [M2 #3] 하위호환: 없으면 solid 유지
    elif t == "line":
        it = _LineItem(QLineF(*d["line"])); it.setPen(_mkpen(d))
    elif t == "path":
        it = _PathItem(_elems_to_path(d["elements"])); it.setPen(_mkpen(d))
        if d.get("fill") is not None:   # [§8 항목31]
            it.setBrush(_mkbrush(d))
        it._freehand = bool(d.get("freehand", False))
    elif t == "text":
        it = _TextItem(QColor(d["color"])); it.apply_font_size(d.get("font", 16))
        if d.get("bold") or d.get("weight") or d.get("family"):
            from PyQt6.QtGui import QFont
            f = it.font()
            if d.get("family"):
                from easycad.fonts import ensure_fonts
                ensure_fonts()
                f.setFamily(d["family"])
            if d.get("bold"):
                f.setBold(True)
            if d.get("weight"):
                f.setWeight(QFont.Weight(int(d["weight"])))
            it.setFont(f)
        it.setPlainText(d.get("text", ""))
        it.apply_runs(d.get("runs"))
        if d.get("bg") is not None:
            it.set_bg(QColor(*d["bg"]))
    elif t == "badge":
        it = _BadgeItem(d["number"], QColor(d["color"]))
    else:
        return None
    it = _apply_common(it, d)
    # [웹 칠판 2026-10-18] 웹 칠판만 아는 칸(AI 카드 `fit_text`·`chat_at`·라벨 `align`, 표 `font`·`color`·`pen`) — 데스크톱은 아직 그리지 않지만
    # 저장할 때 그대로 돌려 쓴다(`item_to_dict` 끝). 알려진 칸만 골라 담는다 — 아무 칸이나 되살리면 데스크톱에서 지운 라벨 등이 되살아남.
    extra = {k: d[k] for k in _WEB_ONLY_KEYS.get(t, ()) + _WEB_ONLY_KEYS_ALL if k in d}
    if (d.get("label") or {}).get("align"):
        extra["label.align"] = d["label"]["align"]
    if t == "frame":
        extra.update({"type": "frame", **{k: d[k] for k in ("name", "no", "ratio", "magnet") if k in d}})
    if t == "web":
        extra.update({"type": "web", **{k: d[k] for k in ("url", "title", "thumb", "embed", "frameable", "desc", "icon", "zoom") if k in d}})   # desc·icon·zoom = 2026-10-19
    if t == "memo":
        extra.update({"type": "memo", **{k: d[k] for k in ("lines",) if k in d}})
    if t == "legend":
        extra.update({"type": "legend", **{k: d[k] for k in ("rows", "names", "title") if k in d}})
    if extra:
        it._web_extra = extra
    if t in _WEB_TYPES:   # [§8 항목61 ④-1 2026-10-19] 웹 종류는 원래 칸을 통째로 — 칸 목록을 적는 방식은 웹에 새 칸이 생길 때마다 잃었음(메모 `fold`)
        it._web_raw = {k: v for k, v in d.items() if k not in _DESK_KEYS or k == "type"}
    for pd in d.get("ports", []):
        _port_from_dict(pd, it)
    # [§8 항목17 6단계] TRIM cut 구간 복원 — _add_border_cut을 안 쓰고 직접 대입한다(그
    # 함수는 host.update()까지 호출하는데 이 시점엔 아직 씬에 안 들어가 있을 수 있어 불필요).
    cuts = d.get("cuts")
    if cuts:
        it._cuts = [(c[0], c[1], c[2]) for c in cuts]
    return it


# ---- 파일 저장/열기 -------------------------------------------------------
def save_document(scene, path: str, layers: list | None = None):
    # 아래→위(stacking) 순으로 저장해 열 때 순서·겹침이 보존되게 한다.
    # 자식 아이템(선/화살표에 부착된 라벨)은 부모 dict 안에 직렬화하므로 최상위에서 제외.
    serial = [(it, item_to_dict(it)) for it in reversed(scene.items())
              if it.parentItem() is None]
    serial = [(it, d) for it, d in serial if d is not None]
    idx_of = {id(it): i for i, (it, _d) in enumerate(serial)}
    # 화살표의 지속 연결 바인딩을 '저장 리스트 인덱스' + 고정 부착점(도형 로컬좌표)으로 기록.
    # 곡선(arrow)은 끝점 idx 0·1, 직선(sarrow)은 시작 idx 0·끝 idx last를 bind1·bind2에 매핑.
    for it, d in serial:
        if d["type"] in ("arrow", "sarrow"):
            end_idx = [0, 1] if d["type"] == "arrow" else [0, len(it._pts) - 1]
            for (key, pkey, gkey), bi in zip(
                    (("bind1", "bind1_pt", "bind1_group"), ("bind2", "bind2_pt", "bind2_group")),
                    end_idx):
                sh = it._bound(bi)
                pt = it._bind_pt(bi)
                # [그룹 프레임 2026-08-25] `_GroupBindProxy`는 저장 리스트 안의 실제 아이템이
                # 아니라 group_id 문자열을 직접 참조 — `_group_id`가 이미 .ecad에 왕복되므로
                # (`_common`/`_apply_common`) 인덱스 없이도 저장·복원된다. `pt`는 이 경우
                # 도형 로컬좌표가 아니라 그룹 bbox 대비 분수좌표(0~1)다(`_GroupBindProxy.
                # mapFromScene`).
                if isinstance(sh, _GroupBindProxy) and pt is not None:
                    d[key] = None
                    d[gkey] = sh.group_id
                    d[pkey] = [pt.x(), pt.y()]
                elif sh is not None and id(sh) in idx_of and pt is not None:
                    d[key] = idx_of[id(sh)]
                    d[gkey] = None
                    d[pkey] = [pt.x(), pt.y()]
                else:
                    d[key] = None
                    d[gkey] = None
                    d[pkey] = None
    items = [d for _it, d in serial]
    doc = {"format": FORMAT, "version": VERSION, "items": items}
    if layers is not None:   # [신규기능] 레이어 목록(이름·표시·잠금) — 문서 레벨 메타
        doc["layers"] = layers
    # [점검 1단계 2026-10-03] 대상 파일을 직접 열어 쓰지 않는다 — 임시 파일에 다 쓴 뒤
    # 바꿔치기(safe_write.py). 쓰는 도중 크래시·예외가 나도 원래 파일은 멀쩡히 남는다.
    def _write(tmp):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
    write_via_temp(path, _write)


def insert_items(scene, items: list[dict]) -> list:
    """`items`(item dict 목록, `bind1`/`bind2`는 **이 목록 안에서의 인덱스**)를 기존
    씬에 그대로 추가한다 — `scene.clear()`를 하지 않는다는 점만 `load_document`와 다르고
    생성→바인딩 재연결→라벨 복원 3-pass 로직은 동일(둘이 공유하도록 여기로 추출,
    2026-08-11 §8 항목18 C단계 — AI 이미지→도면 결과를 기존 문서에 "삽입"하려면
    `load_document`의 `scene.clear()`가 걸림돌이었다).

    반환은 실제로 생성된 아이템 리스트(None 필터링됨) — 호출자가 `push_undo_add_many()`
    등으로 undo에 등록하거나 배치를 옮기는 데 쓴다."""
    created = [dict_to_item(d) for d in items]
    for it in created:
        if it is not None:
            scene.addItem(it)
    for d, it in zip(items, created):
        if it is None or d.get("type") not in ("arrow", "sarrow"):
            continue
        end_idx = [0, 1] if d["type"] == "arrow" else [0, len(it._pts) - 1]
        for (key, pkey, gkey), bi in zip(
                (("bind1", "bind1_pt", "bind1_group"), ("bind2", "bind2_pt", "bind2_group")),
                end_idx):
            pt = d.get(pkey)
            gid = d.get(gkey)
            if gid is not None and pt is not None:
                # [그룹 프레임 2026-08-25] group_id만으로 복원 — 대상 그룹 멤버가 실제로
                # 씬에 있는지는 안 따진다(멤버가 아직 없거나 나중에 지워져도 `_GroupBindProxy.
                # scene()`이 None을 돌려줘 `reroute()`가 조용히 무해화한다).
                it.set_bound(bi, _GroupBindProxy(scene, gid), QPointF(*pt))
                continue
            j = d.get(key)
            if j is not None and 0 <= j < len(created) and created[j] is not None and pt is not None:
                it.set_bound(bi, created[j], QPointF(*pt))
    # [우리 확장] 선·화살표 라벨 복원(본체가 씬에 들어간 뒤라 자식 부착 가능).
    # [다중 라벨 2026-08-21] 화살표/직선화살은 새 "labels"(리스트) 키를 우선 읽고, 없으면
    # 옛 파일의 단수 "label" 키로 하위호환 폴백한다(둘 다 없으면 아무것도 안 함).
    for d, it in zip(items, created):
        if it is None:
            continue
        if isinstance(it, (_ArrowItem, _PolyArrowItem)) and d.get("labels"):
            for ld in d["labels"]:
                lbl = it.add_label_at_t(ld.get("t", 0.5), ld.get("off", 0.0))
                _label_family(lbl, ld)
                lbl.apply_font_size(ld.get("font", 16))
                lbl.setPlainText(ld.get("text", ""))
                lbl.apply_runs(ld.get("runs"))
                lbl.apply_color(QColor(ld.get("color", _TEXT)))
                if ld.get("bg") is not None:
                    lbl.set_bg(QColor(*ld["bg"]))
            it._sync_label()
        elif (d.get("label") or _web_card_label(d)) and hasattr(it, "restore_label"):
            it.restore_label(d.get("label") or _web_card_label(d))
            # [우리 확장] 화살표 라벨의 경로/곡선 위 위치(t·off) 복원 후 재배치(없으면 기본 중점).
            if isinstance(it, (_ArrowItem, _PolyArrowItem)):
                it._label_t = d["label"].get("t", 0.5)
                it._label_off = d["label"].get("off", 0.0)
                it._sync_label()
    return [it for it in created if it is not None]


def load_document(scene, path: str, info: dict | None = None) -> int:
    """path의 문서를 scene에 로드(기존 내용 지움). 로드한 객체 수 반환.
    레이어 목록은 반환값에 안 실음(기존 25+ 호출부의 `== n` 계약을 안 깨려고) —
    필요하면 load_document_layers(path)를 별도 호출.
    [점검 1단계 2026-10-03] `info` dict를 넘기면 파일의 형식 버전을 `info["version"]`에,
    이 프로그램보다 새 버전이면 `info["newer"] = True`를 채운다 — 거부하지 않고 읽을 수
    있는 만큼 읽되, 호출부(host)가 "일부가 빠졌을 수 있다"고 알리게 하려는 것."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != FORMAT:
        raise ValueError("Magic Board 문서(.ecad)가 아닙니다.")
    if info is not None:
        ver = doc.get("version", 1)
        info["version"] = ver
        info["newer"] = isinstance(ver, (int, float)) and ver > VERSION
    scene.clear()
    return len(insert_items(scene, doc.get("items", [])))


def load_document_layers(path: str):
    """[신규기능] .ecad의 문서 레벨 레이어 목록만 읽는다(이름·표시·잠금).
    레이어 목록이 없는 옛 .ecad는 None(호출측이 기본 레이어로 리셋)."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return doc.get("layers")
