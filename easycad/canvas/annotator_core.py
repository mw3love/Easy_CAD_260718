"""이미지 주석 편집기 — CleanShot/Snipaste 스타일.

미리보기 팝업에서 Space(또는 우클릭 "주석 편집")로 진입한다. QGraphicsScene 기반이라
줌하면 주석이 이미지와 함께 스케일되고, 그린 도형은 선택·이동·크기조절·삭제가 가능하다.

도구 단축키: V 선택 · R 네모 · E 원 · L 선 · A 화살표 · P 펜 · T 텍스트 · C 번호 · Ctrl+Z 되돌리기 · Ctrl+C/V 주석 복사·붙여넣기.
Shift: 정사각형/정원/45° 스냅. 선택 후 우하단 핸들 드래그로 크기조절(균일 스케일).
완료 동작은 main이 처리한다(시그널만 emit): 클립보드 복사 / 새 히스토리 항목 / 파일 저장.
"""
import heapq
import io
import math
import struct
import time

from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QLineF, QSize, QBuffer, QIODevice, QTimer, QEvent,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QBrush, QColor, QPainterPath,
    QPainterPathStroker, QPolygonF, QFont, QFontMetricsF, QIcon, QCursor,
    QConicalGradient,
)
from PyQt6.QtWidgets import (
    QWidget, QGraphicsScene, QGraphicsView, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsTextItem, QGraphicsItem, QHBoxLayout,
    QPushButton, QToolButton, QButtonGroup, QLabel, QLineEdit,
    QStyle, QStyleOptionGraphicsItem,
)

from easycad.theme import (
    BASE as _BG, SURFACE0 as _SURFACE0, SURFACE1 as _BORDER,
    SURFACE2 as _SURFACE2, TEXT as _TEXT, BLUE as _BLUE, SUBTEXT0 as _SUBTEXT,
    PEACH as _PEACH, GREEN as _GREEN,
)

_MIN_WIDTH, _MAX_WIDTH, _DEFAULT_WIDTH = 1, 40, 6
_MIN_FONT, _MAX_FONT, _DEFAULT_FONT = 2, 200, 16  # 휠 축소 하한을 2pt로(그 이하는 크기조절 점)
# 번호 마커 지름(px). 기본 30 = _BadgeItem._R(15) * 2, scale 1.0에 대응.
_MIN_BADGE, _MAX_BADGE, _DEFAULT_BADGE = 12, 120, 30


def _clamp_int(v, lo, hi, default):
    """v를 int로 파싱해 [lo, hi]로 클램프. 파싱 실패(None·빈문자열 등)면 default."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(n, hi))

# 대표 프리셋 색상 (빨강·주황·노랑·초록·파랑·검정·흰색)
_COLOR_PRESETS = [
    "#FF3B30", "#FF9500", "#FFCC00", "#34C759",
    "#007AFF", "#000000", "#FFFFFF",
]
_DEFAULT_COLOR = _COLOR_PRESETS[0]

# 밝은 툴바(Snipaste식 pill) 위 중립 아이콘 색 — 어두운 회색(선택·되돌리기·복사·저장).
# 그리기 도구 아이콘은 current_color(색)로 칠해져 밝은 바에서도 보인다.
_ICON_DARK = "#3a3a3a"

# 그리기 도구가 만드는 도형(릴리스 시 너무 작으면 폐기 대상)
_SHAPE_TOOLS = ("rect", "ellipse", "line", "arrow", "sarrow")
# 현재 색으로 아이콘을 칠하는 도구(나머지는 중립색)
_DRAW_TOOLS = ("rect", "ellipse", "line", "arrow", "sarrow", "pen", "text", "badge")

# 텍스트 배경 선택지: 투명 / 흰 / 회 / 검 / 반투명 검 (자막·스티커 느낌). 스와치로 직접 선택.
_TEXT_BG_OPTIONS = [
    (None, "투명"),
    (QColor(0, 0, 0, 150), "반투명 검정"),
    (QColor("#FFFFFF"), "흰색"),
    (QColor("#808080"), "회색"),
    (QColor("#000000"), "검정"),
]

# 도구 정의: (key, 한글명, 단축키 라벨)
_TOOLS = [
    ("select", "선택", "1"), ("rect", "네모", "2"), ("arrow", "화살표", "3"),
    ("text", "텍스트", "4"), ("ellipse", "원", "5"), ("line", "선", "6"),
    ("pen", "펜", "7"), ("badge", "번호", "8"), ("sarrow", "직선화살", "9"),
]


# ---------------------------------------------------------------------------
# 이미지 데이터 → QPixmap (PNG·파일바이트·raw DIB 모두 처리)
# ---------------------------------------------------------------------------

def _to_png_full(data: bytes) -> bytes | None:
    """클립보드 image_data(PNG / JPEG·BMP 등 / raw CF_DIB)를 풀 해상도 PNG로 변환."""
    try:
        from PIL import Image
        if data[:4] == b"\x89PNG":
            img = Image.open(io.BytesIO(data))
        else:
            try:
                img = Image.open(io.BytesIO(data))
            except Exception:
                # raw DIB(BITMAPINFOHEADER) → 14바이트 BMP 파일 헤더 부착 (clipboard_monitor와 동일 로직)
                if len(data) < 40:
                    return None
                bi_size = struct.unpack_from("<I", data, 0)[0]
                bi_bit = struct.unpack_from("<H", data, 14)[0]
                bi_clr = struct.unpack_from("<I", data, 32)[0]
                if bi_clr == 0 and bi_bit in (1, 4, 8):
                    bi_clr = 1 << bi_bit
                pixel_offset = 14 + bi_size + bi_clr * 4
                file_size = 14 + len(data)
                hdr = b"BM" + struct.pack("<IHHI", file_size, 0, 0, pixel_offset)
                img = Image.open(io.BytesIO(hdr + data))
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def _pixmap_from_data(data: bytes) -> QPixmap | None:
    pm = QPixmap()
    if pm.loadFromData(data):
        return pm
    png = _to_png_full(data)
    if png and pm.loadFromData(png):
        return pm
    return None


# ---------------------------------------------------------------------------
# 아이콘 (QPainter로 그린 도형 — 그리기 도구는 현재 색, 나머지는 중립색)
# ---------------------------------------------------------------------------

def _tool_icon(tool: str, color=None, neutral_override=None) -> QIcon:
    # neutral_override: 중립색을 바꿔야 할 때(예: 밝은 제목바 위 어두운 닫기 X).
    neutral = QColor(neutral_override) if neutral_override is not None else QColor(_TEXT)
    col = QColor(color) if (color is not None and tool in _DRAW_TOOLS) else neutral
    pm = QPixmap(22, 22)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(col, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)

    if tool == "select":
        poly = QPolygonF([
            QPointF(4, 3), QPointF(4, 18), QPointF(8, 14),
            QPointF(11, 20), QPointF(13, 19), QPointF(10, 13), QPointF(15, 13),
        ])
        p.setBrush(neutral)
        p.setPen(QPen(neutral, 1))
        p.drawPolygon(poly)
    elif tool == "rect":
        p.drawRect(4, 5, 14, 12)
    elif tool == "ellipse":
        p.drawEllipse(4, 4, 14, 14)
    elif tool == "line":
        p.drawLine(4, 18, 18, 4)
    elif tool == "arrow":
        p.drawLine(4, 18, 14, 8)
        p.setBrush(col)
        p.setPen(QPen(col, 1))
        p.drawPolygon(QPolygonF([QPointF(18, 4), QPointF(11, 7), QPointF(15, 11)]))
    elif tool == "sarrow":
        # 꺾은선(직선 폴리라인) + 위 향한 촉 — 곡선 화살표와 구분되는 엘보 형태
        p.drawPolyline(QPolygonF([QPointF(4, 18), QPointF(13, 18), QPointF(13, 9)]))
        p.setBrush(col)
        p.setPen(QPen(col, 1))
        p.drawPolygon(QPolygonF([QPointF(13, 3), QPointF(10, 9), QPointF(16, 9)]))
    elif tool == "pen":
        path = QPainterPath(QPointF(4, 16))
        path.cubicTo(8, 5, 14, 21, 18, 7)
        p.drawPath(path)
    elif tool == "text":
        f = QFont()
        f.setBold(True)
        f.setPointSize(12)
        p.setFont(f)
        p.setPen(col)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "T")
    elif tool == "badge":
        p.setBrush(col)
        p.setPen(QPen(col, 1))
        p.drawEllipse(3, 3, 16, 16)
        f = QFont()
        f.setBold(True)
        f.setPointSize(9)
        p.setFont(f)
        p.setPen(QColor(_BG))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "1")
    elif tool == "eyedrop":
        # 드로퍼(스포이드) — 외곽선 캡(bulb) + 대각 몸통 + 좌하단 뾰족 끝(끝점만 작은 채움)
        p.setPen(QPen(neutral, 1.6, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(12, 2, 8, 8, 3, 3)            # 캡(bulb) — 외곽선만
        p.setPen(QPen(neutral, 2.2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(14, 9, 7, 16)                         # 대각 몸통
        p.setBrush(neutral)                              # 촉(끝점)만 작게 채움
        p.setPen(QPen(neutral, 1))
        p.drawPolygon(QPolygonF([
            QPointF(8, 14), QPointF(4, 18), QPointF(9, 15)]))
    elif tool == "undo":
        # 반시계 곡선 화살표
        p.setPen(QPen(neutral, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        path.arcMoveTo(QRectF(5, 5, 13, 13), 150)
        path.arcTo(QRectF(5, 5, 13, 13), 150, -250)
        p.drawPath(path)
        p.setBrush(neutral)
        p.setPen(QPen(neutral, 1))
        p.drawPolygon(QPolygonF([QPointF(5, 6), QPointF(10, 7), QPointF(7, 12)]))
    elif tool == "copy":
        # 겹친 두 문서 — 외곽선만(채움 없음). 뒤 문서는 보이는 가장자리(상단·좌측)만
        # 앞 문서 외곽선까지 이어 그려, 채움 없이도 '뒤에 겹친' 느낌을 낸다.
        p.setPen(QPen(neutral, 1.6, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(8, 7, 10, 12, 2, 2)            # 앞 문서(완전한 외곽선)
        back = QPainterPath()                            # 뒤 문서의 보이는 가장자리
        back.moveTo(14, 7)
        back.lineTo(14, 5)
        back.quadTo(14, 4, 13, 4)
        back.lineTo(6, 4)
        back.quadTo(5, 4, 5, 5)
        back.lineTo(5, 14)
        back.quadTo(5, 15, 6, 15)
        back.lineTo(8, 15)
        p.drawPath(back)
    elif tool == "save":
        # 플로피 디스크
        p.setPen(QPen(neutral, 1.6, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(4, 4, 14, 14, 1, 1)            # 본체
        p.setBrush(neutral)
        p.setPen(QPen(neutral, 1))
        p.drawRect(8, 4, 5, 4)                           # 상단 셔터
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(neutral, 1.4))
        p.drawRect(7, 12, 8, 5)                          # 하단 라벨
    elif tool == "close":
        p.setPen(QPen(neutral, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(6, 6, 16, 16)
        p.drawLine(16, 6, 6, 16)
    p.end()
    return QIcon(pm)


def _arrow_dir_icon(head_at_end: bool) -> QIcon:
    pm = QPixmap(24, 18)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor(_TEXT)
    p.setPen(QPen(col, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(5, 9, 19, 9)
    p.setBrush(col)
    p.setPen(QPen(col, 1))
    if head_at_end:
        p.drawPolygon(QPolygonF([QPointF(21, 9), QPointF(15, 5), QPointF(15, 13)]))
    else:
        p.drawPolygon(QPolygonF([QPointF(3, 9), QPointF(9, 5), QPointF(9, 13)]))
    p.end()
    return QIcon(pm)


def _rainbow_icon(current: QColor | None = None, size: int = 20) -> QIcon:
    """무지개 색 버튼 아이콘 — 무지개 링 + 가운데 현재 색 점(팔레트 팝업 진입점)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QConicalGradient(size / 2, size / 2, 90)
    for stop, hexs in (
        (0.00, "#FF3B30"), (0.17, "#FF9500"), (0.34, "#FFCC00"),
        (0.50, "#34C759"), (0.67, "#007AFF"), (0.84, "#AF52DE"),
        (1.00, "#FF3B30"),
    ):
        g.setColorAt(stop, QColor(hexs))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(1, 1, size - 2, size - 2)
    if current is not None:
        r = size * 0.30
        p.setBrush(QColor(current))
        p.setPen(QPen(QColor("#FFFFFF"), 1.4))
        p.drawEllipse(QPointF(size / 2, size / 2), r, r)
    p.end()
    return QIcon(pm)


def _bg_swatch_icon(bg) -> QIcon:
    """텍스트 배경 스와치 — 불투명색은 그대로 채움, 반투명색은 체커보드 위에 얹어(투명 표시
    관용) 회색 불투명과 헷갈리지 않게 한다. bg=None이면 투명(대각선)."""
    pm = QPixmap(20, 20)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(2, 2, 16, 16)
    if bg is None:
        p.setPen(QPen(QColor(_TEXT), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 3, 3)
        p.drawLine(5, 15, 15, 5)                         # 투명 표시 대각선
    else:
        clip = QPainterPath()
        clip.addRoundedRect(rect, 3, 3)
        p.setClipPath(clip)
        p.fillRect(rect, QColor("white"))
        if bg.alpha() < 255:
            # 반투명 → 체커보드 바탕(칸 4px)을 깔아 '뒤가 비친다'를 시각화
            cell = 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#bfbfbf"))
            yy = 2
            while yy < 18:
                xx = 2
                while xx < 18:
                    if ((int(xx) // cell) + (int(yy) // cell)) % 2 == 0:
                        p.drawRect(QRectF(xx, yy, cell, cell))
                    xx += cell
                yy += cell
        p.setBrush(QBrush(bg))                           # 실제 배경색(반투명이면 체커가 비침)
        p.drawRect(rect)
        p.setClipping(False)
        p.setPen(QPen(QColor(_SUBTEXT), 1))              # 테두리
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 3, 3)
    p.end()
    return QIcon(pm)


_ROTATE_CURSOR = None


def _rotate_cursor() -> QCursor:
    """회전 핸들 hover용 커스텀 커서(곡선 화살표). Qt 기본에 회전 커서가 없어 픽스맵으로
    1회 생성·캐시. 검은 본체 + 흰 halo라 밝은/어두운 배경 모두에서 보인다."""
    global _ROTATE_CURSOR
    if _ROTATE_CURSOR is not None:
        return _ROTATE_CURSOR
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(8, 8, 16, 16)               # 반지름 8, 중심 (16,16)
    path = QPainterPath()
    path.arcMoveTo(rect, 55)
    path.arcTo(rect, 55, 250)                 # 250° 열린 호
    pe = path.pointAtPercent(1.0)             # 호 끝 — 화살촉을 실제 두 점 방향으로(각도 규약 회피)
    pp = path.pointAtPercent(0.9)
    dx, dy = pe.x() - pp.x(), pe.y() - pp.y()
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    b = QPointF(pe.x() - ux * 6.0, pe.y() - uy * 6.0)
    tri = QPolygonF([QPointF(pe),
                     QPointF(b.x() + nx * 4.0, b.y() + ny * 4.0),
                     QPointF(b.x() - nx * 4.0, b.y() - ny * 4.0)])
    for core, aw in ((QColor("white"), 5.0), (QColor("#111111"), 2.4)):  # 흰 halo → 검은 본체
        pen = QPen(core, aw)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setBrush(QBrush(core))
        p.drawPolygon(tri)
    p.end()
    _ROTATE_CURSOR = QCursor(pm, 16, 16)
    return _ROTATE_CURSOR


# ---------------------------------------------------------------------------
# 크기조절 핸들 믹스인 — 선택 시 우하단 핸들 드래그로 균일 스케일
# ---------------------------------------------------------------------------

class _HandleResizeMixin:
    # 핸들(스케일 사각·회전 원·끝점 사각) 크기는 도형의 '획 두께'에 비례한다 — 얇은 선은
    # 작은 핸들, 굵은 선은 큰 핸들. 씬 단위로 [MIN,MAX] 클램프(못 잡을 만큼 작지도, 거슬릴
    # 만큼 크지도 않게). 획이 없는 도형(번호·텍스트)만 표시 크기 비례로 폴백한다.
    _HANDLE_FRAC = 0.22        # (폴백) 작은 변 대비 핸들 비율 — 번호·텍스트용
    _HANDLE_STROKE_FRAC = 1.4  # 획 두께 대비 핸들 비율 — 도형·선·화살표용
    _HANDLE_MIN = 5.0    # 씬 단위 하한(항상 잡히게)
    _HANDLE_MAX = 12.0   # 씬 단위 상한
    _EDGE_HIT_MIN = 8.0  # 속 빈 도형 테두리 클릭 최소 히트폭(씬 단위) — 얇은 선도 잡히게

    def _stroke_width(self) -> float:
        """핸들 크기 기준이 되는 획 두께(로컬 단위). 없으면 0(→ 크기 비례 폴백)."""
        if hasattr(self, "_width"):   # _ArrowItem
            return float(self._width)
        if hasattr(self, "pen"):      # rect/ellipse/line/path
            return float(self.pen().widthF())
        return 0.0

    def _handle_px(self) -> float:
        """핸들 한 변(로컬 단위). 획 두께에 비례 + [MIN,MAX] 클램프(획 없으면 크기 비례)."""
        s = self._scale_or_1()
        w = self._stroke_width()
        if w > 0:
            h_scene = max(self._HANDLE_MIN,
                          min(w * s * self._HANDLE_STROKE_FRAC, self._HANDLE_MAX))
            return h_scene / s
        cr = self._content_rect()
        scene_dim = min(cr.width(), cr.height()) * s  # 주석 작은 변(씬 단위)
        h_scene = max(self._HANDLE_MIN, min(scene_dim * self._HANDLE_FRAC, self._HANDLE_MAX))
        return h_scene / s

    # ---- 잡기 판정(시각 점과 분리) --------------------------------------
    # 그려지는 점은 작게(_handle_px) 두되, '잡히는' 영역은 화면 고정 px로 넉넉히
    # — Figma·일러스트레이터식. 얇은 화살표의 bend/끝점 점이 화면상 5~12px라 커서를
    # 정확히 맞춰야 손가락 커서가 되던 문제를 없앤다(hover·press·shape 모두 이 rect 사용).
    _HIT_MIN_PX = 24.0   # 화면 px — 핸들 잡기 최소 지름(줌 무관)

    def _hit_pad_local(self) -> float:
        """잡기 판정 반지름(로컬 단위). 화면 고정 px를 현재 뷰·아이템 배율로 환산."""
        view_s = 1.0
        sc = self.scene()
        if sc is not None and sc.views():
            view_s = sc.views()[0]._view_scale()
        total = max(view_s * self._scale_or_1(), 1e-6)
        return (self._HIT_MIN_PX / total) / 2.0

    def _inflate_to_hit(self, rect: QRectF) -> QRectF:
        """핸들 시각 rect를 잡기 최소 지름까지 부풀린 판정용 rect(이미 크면 그대로)."""
        grow = self._hit_pad_local() - rect.width() / 2.0
        if grow <= 0.0:
            return rect
        return rect.adjusted(-grow, -grow, grow, grow)

    def _init_resize(self):
        self._resizing = False
        self._rotating = False
        self._drag_endpoint = None  # 끝점 드래그 중인 인덱스(0·1, None=없음) — 선·화살표만
        self._press_scale = 1.0
        self._press_dist = 1.0
        self._press_rot = 0.0
        self._press_angle = 0.0
        # [2c] 네모·원 박스 리사이즈(꼭짓점 2D·변 1축, setRect 기반) 상태
        self._box_resize = None     # None | ("corner", 0..3) | ("edge", "l"/"r"/"t"/"b")
        self._box_orig_rect = None  # 드래그 시작 시 rect()(원본 기준 — 누적 방지)
        self._box_snap = None       # [(item, capture_geom()), ...] — geom undo
        self._box_bound = None      # _collect_bound_arrows 결과(부착점 상대유지)

    # ---- 끝점(양끝 이동) 모드 -------------------------------------------
    # 선·화살표처럼 '2점으로 완전히 결정되는' 도형은 회전+균일스케일 핸들 대신
    # 양끝점 핸들을 쓴다(끝점 2개면 길이·각도가 모두 결정 → 회전/스케일 중복). 기본은 off라
    # 네모·원·번호·텍스트는 기존 회전+스케일 핸들을 그대로 쓴다.
    def _uses_endpoints(self) -> bool:
        return False

    def _endpoints(self):
        """끝점들의 로컬 좌표 리스트(선·화살표가 override)."""
        return []

    def _set_endpoint(self, idx: int, p: QPointF):
        """끝점 idx를 로컬 좌표 p로 이동(선·화살표가 override)."""
        pass

    def _group_active(self) -> bool:
        """[우리 확장] 씬에 최상위(라벨 등 자식 제외) 선택 아이템이 2개 이상인가.
        참이면 개별 회전·크기·끝점 핸들을 숨기고 그룹 변형 오버레이(_GroupTransform)에 넘긴다."""
        sc = self.scene()
        if sc is None:
            return False
        n = 0
        for it in sc.selectedItems():
            if it.parentItem() is None:
                n += 1
                if n >= 2:
                    return True
        return False

    def _endpoint_active(self) -> bool:
        # 선택돼 있으면 어떤 도구에서든 끝점 이동·재스냅 가능(회전·크기조절 핸들과 동일 정책).
        # 단 다중선택(그룹 변형) 중엔 개별 끝점 핸들을 감춘다 — 그룹 오버레이가 대신 변형.
        return self.isSelected() and not self._group_active()

    def _endpoint_rect(self, idx: int) -> QRectF:
        d = self._handle_px()
        c = self._endpoints()[idx]
        return QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

    def _snap_endpoint(self, idx: int, p: QPointF) -> QPointF:
        """Shift 스냅: 반대쪽 끝점을 기준으로 0/45/90°에 스냅."""
        pts = self._endpoints()
        anchor = pts[1 - idx] if len(pts) == 2 else pts[idx]
        dx, dy = p.x() - anchor.x(), p.y() - anchor.y()
        dist = math.hypot(dx, dy)
        rad = math.radians(round(math.degrees(math.atan2(dy, dx)) / 45.0) * 45.0)
        return QPointF(anchor.x() + dist * math.cos(rad), anchor.y() + dist * math.sin(rad))

    def _ortho_endpoint(self, idx: int, p: QPointF) -> QPointF:
        """[우리 확장] F8 Ortho 정점 드래그: 인접 정점 기준 0/90°에 스냅(로컬 좌표).
        인접 = 이전 정점 우선(없으면 다음). |dx|≥|dy|면 수평, 아니면 수직."""
        pts = self._endpoints()
        if len(pts) < 2:
            return p
        anchor = pts[idx - 1] if idx > 0 else pts[idx + 1]
        if abs(p.x() - anchor.x()) >= abs(p.y() - anchor.y()):
            return QPointF(p.x(), anchor.y())
        return QPointF(anchor.x(), p.y())

    def _connects_to_border(self) -> bool:
        """이 아이템의 끝점이 도형 테두리에 재스냅되는가(화살표만 override)."""
        return False

    def _endpoint_border_snap(self, local_p: QPointF):
        """끝점 드래그 중 근처 네모/원 테두리에 스냅(생성 때와 동일 _border_snap_at 재사용).
        스냅되면 (로컬 최근접점, 바깥 법선 scene, shape), 아니면 None — 뗐다 다시 가져가도 붙는 경로.
        (shape는 지속 연결 바인딩용 — 기존 인덱서 [0]/[1]과 호환.)"""
        if not self._connects_to_border():
            return None
        sc = self.scene()
        if sc is None or not sc.views():
            return None
        view = sc.views()[0]
        snap = getattr(view, "_border_snap_at", None)
        if snap is None:
            return None
        res = snap(view.mapFromScene(self.mapToScene(local_p)))
        if res is None:
            return None
        return self.mapFromScene(res[0]), res[1], res[2]

    def _move_endpoint_with_snap(self, idx: int, local_p: QPointF):
        """끝점 idx를 이동하되 테두리 근처면 스냅(기본: 점 스냅만. 화살표는 S자 곡선 재계산 override)."""
        snapped = self._endpoint_border_snap(local_p)
        if snapped is not None:
            local_p = snapped[0]
        self._set_endpoint(idx, local_p)

    def _on_endpoint_drag_start(self, idx: int):
        """[우리 확장] 정점 핸들 드래그가 '시작'될 때 호출(mousePress choke point). 기본 no-op.
        _PolyArrowItem이 override해 자동 직교 라우팅을 해제한다(수동 정점 조작 = 수동 경로)."""
        pass

    def _paint_endpoint_handles(self, painter: QPainter):
        if not self._endpoint_active():
            return
        s = self._scale_or_1()
        painter.setPen(QPen(QColor("white"), 1.0 / s))
        painter.setBrush(QBrush(QColor(_BLUE)))
        for i in range(len(self._endpoints())):
            painter.drawRect(self._endpoint_rect(i))

    # 선택된 도형에 현재 색/두께 적용 — pen 기반(rect/ellipse/line/path) 공통 구현.
    # arrow/badge/text는 pen이 없거나 색 보관 방식이 달라 각자 오버라이드한다.
    def apply_color(self, color):
        if hasattr(self, "pen"):
            pen = self.pen()
            pen.setColor(QColor(color))
            self.setPen(pen)

    def apply_width(self, width):
        if hasattr(self, "pen"):
            pen = self.pen()
            pen.setWidthF(float(width))
            self.setPen(pen)

    # 복제 시 위치·스케일·회전·z·플래그(이동/선택 가능) 공통 복사. 타입별 기하/색은 각 clone()이 채운다.
    def _copy_common_to(self, dst):
        dst.setPos(self.pos())
        dst.setScale(self.scale())
        dst.setTransformOriginPoint(self.transformOriginPoint())
        dst.setRotation(self.rotation())
        dst.setZValue(self.zValue())
        dst.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        return dst

    # ---- [Stage2] 기하 리베이크(비균일 스케일·미러) — 스냅샷/복원/씬공간 변형 ----------
    # Stage1의 xform(pos/rot/scale/origin만)과 달리 '기하 자체'를 바꾼다. 씬공간 함수 fn을 받아
    # 각 기하 제어점을 fn(현재 씬위치)로 다시 굽는다(rebake). pos/rot/scale/origin은 그대로 두고
    # fn을 아이템 transform을 '통과'시켜 적용하므로(mapToScene→fn→mapFromScene) 기존 setScale·
    # 회전 상태와 안 엉킨다(회전=0·스케일 임의면 정확, 회전 도형은 로컬 AABB 근사 — 설계 합의).
    def capture_geom(self) -> dict:
        """undo·드래그 복원용 기하 스냅샷(pos/rot/scale/origin + 타입별 기하 + 바인딩)."""
        return {
            "pos": QPointF(self.pos()),
            "rot": self.rotation(),
            "scale": self.scale(),
            "org": QPointF(self.transformOriginPoint()),
            "geom": self._capture_geom_local(),
            "binds": self._capture_binds(),
        }

    def apply_geom(self, tok: dict):
        """capture_geom 스냅샷 복원(원복)."""
        self.prepareGeometryChange()
        self.setTransformOriginPoint(tok["org"])
        self.setRotation(tok["rot"])
        self.setScale(tok["scale"])
        self.setPos(tok["pos"])
        self._apply_geom_local(tok["geom"])
        self._apply_binds(tok["binds"])
        self.update()

    def _capture_geom_local(self):
        """타입별 기하 복사(하위 클래스 override)."""
        return None

    def _apply_geom_local(self, g):
        pass

    def _capture_binds(self):
        """지속연결 바인딩(도형·부착점) 복사 — 화살표만 override."""
        return None

    def _apply_binds(self, b):
        pass

    def _rebake_pt(self, fn, p_local: QPointF) -> QPointF:
        """로컬 제어점 → 씬 → fn → 로컬(아이템 transform 통과)."""
        return self.mapFromScene(fn(self.mapToScene(p_local)))

    def rebake_scene(self, fn):
        """기하 제어점을 씬공간 함수 fn으로 다시 굽는다(하위 클래스 override).
        기본(스칼라 폴백: 텍스트·번호)은 왜곡 대신 내용 중심을 fn으로 옮겨 위치만 따라가게 한다."""
        c = self.mapToScene(self._content_rect().center())
        d = fn(c) - c
        self.setPos(self.pos() + d)

    # [Stage2b] stretch — 이 아이템의 '정점(grip)' 씬좌표들. crossing 박스 안에 든 grip만
    # stretch 시 delta로 이동한다(밖은 고정). 하이라이트(●) 표시 전용 — 실제 이동은
    # rebake_scene(공간 fn)이 담당한다(네모·원은 걸친 모서리 AABB로 자연히 일치).
    # 기본: 끝점 보유형(선·화살표·폴리)은 끝점들, 아니면 내용 중심(텍스트·번호=스칼라 폴백).
    def _stretch_grips(self):
        if self._uses_endpoints():
            return [self.mapToScene(p) for p in self._endpoints()]
        return [self.mapToScene(self._content_rect().center())]

    def _scale_or_1(self) -> float:
        s = self.scale()
        return s if s else 1.0

    # 타이트 경계(선택박스·핸들 기준). 도형별로 override한다(기본은 Qt 기본 boundingRect).
    def _content_rect(self) -> QRectF:
        return super().boundingRect()

    # 핸들 hit-test의 기준 영역(선택 시 핸들 미포함). 기본은 Qt 기본 shape;
    # boundingRect 기반 shape를 쓰는 도형(arrow/badge)은 content_rect로 override해
    # 회전 핸들 여유분이 클릭 영역에 새는 것을 막는다.
    def _base_shape(self):
        return super().shape()

    # 실제 boundingRect = content ∪ 회전 핸들 영역(상시 예약 → 선택 해제 시 핸들 잔상 방지).
    # 위쪽뿐 아니라 좌우도 덮어야 함 — 얇은 도형(세로선 등)은 핸들 원이 content보다 가로로
    # 넓어 좌우로 삐져나오므로. 여유분은 scale 의존이라, 크기조절 중 mouseMove에서
    # prepareGeometryChange로 갱신한다.
    def boundingRect(self) -> QRectF:
        pad = 3.0 / self._scale_or_1()
        if self._uses_endpoints():
            r = self._content_rect()
            for i in range(len(self._endpoints())):
                # 시각 rect가 아니라 '잡기' rect까지 예약해야 넉넉한 hit-shape가
                # boundingRect 밖으로 나가 Qt에 컬링당하지 않는다.
                r = r.united(self._inflate_to_hit(self._endpoint_rect(i)))
            return r.adjusted(-pad, -pad, pad, pad)
        if self._box_handles():
            # 꼭짓점·변 핸들은 rect 경계서 half-handle 삐져나오고, 회전 핸들·빠른생성 도트는 바깥.
            h = self._handle_px()
            r = self._content_rect().united(self._box_rot_rect())
            for _k, dr in self._qc_dot_rects():
                r = r.united(dr)
            return r.adjusted(-h, -h, h, h)
        return self._content_rect().united(self._rot_handle_rect().adjusted(-pad, -pad, pad, pad))

    def _handle_local_rect(self) -> QRectF:
        h = self._handle_px()
        c = self._content_rect().bottomRight()
        return QRectF(c.x() - h, c.y() - h, h, h)

    def _rot_handle_center(self) -> QPointF:
        # 우상단 코너 안쪽 — 우하단 크기조절 점과 오른쪽 변에 위아래로 대칭인 점(줄기 없음).
        cr = self._content_rect()
        r = self._handle_px() * 0.5  # 원 반지름(= 크기조절 사각 변의 절반 → 같은 지름)
        return QPointF(cr.right() - r, cr.top() + r)

    def _rot_handle_rect(self) -> QRectF:
        d = self._handle_px()  # 원 지름 = 크기조절 사각 변
        c = self._rot_handle_center()
        return QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

    # ---- [2c] 네모·원 박스 핸들(꼭짓점 4·변 중점 4·좌상단 회전) ------------------
    # 텍스트·번호는 기존 단일 핸들(중심 균일 스케일)을 그대로 쓰고, setRect가 있는 네모·원만
    # Lucid식 8핸들로 자유 리사이즈한다. 핸들 위치·리사이즈 모두 '기하 rect()' 기준(펜 여유 없이
    # 정확). 선택 점선은 _content_rect(펜 밖)이라 핸들이 그 안쪽에 살짝 들어오지만 무해.
    def _box_handles(self) -> bool:
        return hasattr(self, "setRect") and not self._uses_endpoints()

    def _box_corner_rects(self):
        br = self.rect()
        h = self._handle_px()
        pts = [br.topLeft(), br.topRight(), br.bottomRight(), br.bottomLeft()]  # 0TL 1TR 2BR 3BL
        return [(i, QRectF(p.x() - h / 2, p.y() - h / 2, h, h)) for i, p in enumerate(pts)]

    def _box_edge_rects(self):
        br = self.rect()
        h = self._handle_px()
        mids = [("t", QPointF(br.center().x(), br.top())),
                ("r", QPointF(br.right(), br.center().y())),
                ("b", QPointF(br.center().x(), br.bottom())),
                ("l", QPointF(br.left(), br.center().y()))]
        return [(k, QRectF(p.x() - h / 2, p.y() - h / 2, h, h)) for k, p in mids]

    def _box_rot_center(self) -> QPointF:
        br = self.rect()
        gap = self._handle_px() * 1.6   # 좌상단서 대각으로 살짝 뗌
        return QPointF(br.left() - gap, br.top() - gap)

    def _box_rot_rect(self) -> QRectF:
        d = self._handle_px()
        c = self._box_rot_center()
        return QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

    # [2d] 빠른 생성 도트 — 상하좌우 테두리서 바깥으로 살짝 뗀 점. 드래그/클릭 시 그 방향으로
    # 연결 화살표 + 동일도형 복제 생성(호버 시 고스트 미리보기). 위치·hover·생성은 뷰가 담당.
    def _qc_dot_rects(self):
        br = self.rect()
        h = self._handle_px()
        gap = h * 2.5
        d = h * 0.9
        pos = [("t", QPointF(br.center().x(), br.top() - gap)),
               ("r", QPointF(br.right() + gap, br.center().y())),
               ("b", QPointF(br.center().x(), br.bottom() + gap)),
               ("l", QPointF(br.left() - gap, br.center().y()))]
        return [(k, QRectF(p.x() - d / 2, p.y() - d / 2, d, d)) for k, p in pos]

    def _box_handle_cursor(self, local_pt: QPointF):
        """local_pt가 어느 박스 핸들 위인지 → 커서('rotate' or Qt.CursorShape), 없으면 None."""
        if not (self._box_handles() and self._handle_active()):
            return None
        if self._box_rot_rect().contains(local_pt):
            return "rotate"
        for i, r in self._box_corner_rects():
            if r.contains(local_pt):   # TL·BR = ↖↘, TR·BL = ↗↙
                return (Qt.CursorShape.SizeFDiagCursor if i in (0, 2)
                        else Qt.CursorShape.SizeBDiagCursor)
        for k, r in self._box_edge_rects():
            if r.contains(local_pt):   # 좌우변=가로, 상하변=세로
                return (Qt.CursorShape.SizeHorCursor if k in ("l", "r")
                        else Qt.CursorShape.SizeVerCursor)
        return None

    def _host(self):
        sc = self.scene()
        if sc is not None and sc.views():
            return getattr(sc.views()[0], "_owner", None)
        return None

    def _begin_box_geom(self):
        """박스 리사이즈·회전 시작 — 원본 rect + undo 스냅샷(자신+부착 화살표) 확보."""
        self._box_orig_rect = QRectF(self.rect())
        self._box_bound = _collect_bound_arrows(self.scene(), [self])
        self._box_snap = [(it, it.capture_geom())
                          for it in _snapshot_set([self], self._box_bound)]

    def _set_box_rect(self, new_rect: QRectF):
        """rect 교체 + 부착 화살표 부착점을 '상대 위치 유지'로 재매핑 후 추종(reroute)."""
        old = self.rect()
        ow = old.width() if abs(old.width()) > 1e-6 else 1.0
        oh = old.height() if abs(old.height()) > 1e-6 else 1.0
        for arrow, idx, sh in (self._box_bound or []):
            bp = arrow._bind_pt(idx)
            if bp is None:
                continue
            relx = (bp.x() - old.left()) / ow
            rely = (bp.y() - old.top()) / oh
            arrow.set_bound(idx, sh, QPointF(new_rect.left() + relx * new_rect.width(),
                                             new_rect.top() + rely * new_rect.height()))
        self.prepareGeometryChange()
        self.setRect(new_rect)
        for arrow, idx, sh in (self._box_bound or []):
            arrow.reroute(pin_pred=lambda i: True)

    def _apply_box_resize(self, lp: QPointF):
        o = self._box_orig_rect
        kind, key = self._box_resize
        if kind == "corner":
            opp = [o.bottomRight(), o.bottomLeft(), o.topLeft(), o.topRight()][key]  # 대각 고정
            new = QRectF(opp, lp).normalized()
        else:
            left, top, right, bot = o.left(), o.top(), o.right(), o.bottom()
            if key == "l":
                left = lp.x()
            elif key == "r":
                right = lp.x()
            elif key == "t":
                top = lp.y()
            else:
                bot = lp.y()
            new = QRectF(QPointF(left, top), QPointF(right, bot)).normalized()
        MIN = 3.0
        if new.width() < MIN or new.height() < MIN:
            new = QRectF(new.x(), new.y(), max(new.width(), MIN), max(new.height(), MIN))
        new = self._constrain_box_rect(new, kind, key)
        self._set_box_rect(new)

    def _constrain_box_rect(self, new: QRectF, kind: str, key) -> QRectF:
        """박스 리사이즈 결과 rect 후처리 훅(기본 무변경). _ImageItem이 종횡비 고정에 override."""
        return new

    def _owner_tool(self):
        """현재 활성 도구를 뷰→owner 경로로 조회(없으면 None)."""
        sc = self.scene()
        if sc is not None and sc.views():
            owner = getattr(sc.views()[0], "_owner", None)
            if owner is not None:
                return getattr(owner, "current_tool", None)
        return None

    def _owner_ortho(self) -> bool:
        """[우리 확장] F8 Ortho 활성 여부를 뷰→owner로 조회(정점 드래그 0/90° 제약용)."""
        sc = self.scene()
        if sc is not None and sc.views():
            owner = getattr(sc.views()[0], "_owner", None)
            if owner is not None:
                return bool(getattr(owner, "ortho_enabled", False))
        return False

    def _handle_active(self) -> bool:
        if not self.isSelected():
            return False
        # 다중선택(그룹 변형) 중엔 개별 회전·크기 핸들을 감춘다 — 그룹 오버레이가 대신 변형.
        if self._group_active():
            return False
        # 선택돼 있으면 어떤 도구에서든 이동·회전·크기조절을 바로 할 수 있게 핸들을 띄운다
        # (선택 도구는 러버밴드 다중선택을 계속 담당). 도구 전환 없이 방금 그린 도형을 다듬기 위함.
        if isinstance(self, QGraphicsTextItem) and \
                self.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction:
            return False
        return True

    def _paint_handle(self, painter: QPainter):
        if self._uses_endpoints():
            self._paint_endpoint_handles(painter)
            return
        if not self._handle_active():
            return
        s = self._scale_or_1()
        if self._box_handles():
            # [2c] 꼭짓점 4 + 변 중점 4 = 파란 사각, 좌상단 회전 = 코랄 원.
            painter.setPen(QPen(QColor("white"), 1.0 / s))
            painter.setBrush(QBrush(QColor(_BLUE)))
            for _i, r in self._box_corner_rects():
                painter.drawRect(r)
            for _k, r in self._box_edge_rects():
                painter.drawRect(r)
            rh = self._handle_px() * 0.5
            painter.setBrush(QBrush(QColor(_PEACH)))
            painter.drawEllipse(self._box_rot_center(), rh, rh)
            # [2d] 빠른 생성 도트 — 옅은 파란 원(흰 테두리). 호버 시 뷰가 고스트 미리보기.
            painter.setPen(QPen(QColor("white"), 1.0 / s))
            painter.setBrush(QBrush(QColor(90, 150, 235)))
            for _k, dr in self._qc_dot_rects():
                painter.drawEllipse(dr)
            return
        # 회전 핸들 — 우상단 코너 안쪽 코랄 점(줄기 없음, 우하단 크기조절 점과 대칭)
        rc = self._rot_handle_center()
        rh = self._handle_px() * 0.5  # 반지름 — 지름이 크기조절 사각 변과 같게
        painter.setPen(QPen(QColor("white"), 1.0 / s))
        painter.setBrush(QBrush(QColor(_PEACH)))
        painter.drawEllipse(rc, rh, rh)
        # 크기조절 핸들 — 우하단 파란 사각
        r = self._handle_local_rect()
        painter.setPen(QPen(QColor("white"), 1.0 / s))
        painter.setBrush(QBrush(QColor(_BLUE)))
        painter.drawRect(r)

    def _paint_base(self, painter, option, widget):
        # Qt 기본 paint의 자동 선택 점선(회전 핸들까지 확장된 boundingRect 둘레)을 막고
        # 베이스 도형만 그린다. 선택 표시는 호출자가 직접 그린다.
        opt = QStyleOptionGraphicsItem(option)
        opt.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, opt, widget)

    def _paint_base_no_select(self, painter, option, widget):
        # 베이스 + 타이트 선택박스(_content_rect에만). 네모·원이 사용한다.
        self._paint_base(painter, option, widget)
        if self.isSelected():
            _draw_selection_box(painter, self._content_rect(), self._scale_or_1())

    def shape(self):
        # 선택 시 핸들 영역을 클릭 영역에 포함 — 속 빈 도형도 핸들을 잡을 수 있게.
        base = self._base_shape()
        if self._uses_endpoints():
            if self._endpoint_active():
                hp = QPainterPath()
                for i in range(len(self._endpoints())):
                    hp.addRect(self._inflate_to_hit(self._endpoint_rect(i)))
                return base.united(hp)
            return base
        if self._handle_active():
            hp = QPainterPath()
            if self._box_handles():
                for _i, r in self._box_corner_rects():
                    hp.addRect(r)
                for _k, r in self._box_edge_rects():
                    hp.addRect(r)
                hp.addEllipse(self._box_rot_rect())
            else:
                hp.addRect(self._handle_local_rect())
                hp.addEllipse(self._rot_handle_rect())
            return base.united(hp)
        return base

    def mousePressEvent(self, event):
        if self._uses_endpoints():
            if self._endpoint_active():
                for i in range(len(self._endpoints())):
                    if self._inflate_to_hit(self._endpoint_rect(i)).contains(event.pos()):
                        self._drag_endpoint = i
                        self._on_endpoint_drag_start(i)   # [Stage1] 수동 정점 드래그 → 자동 라우팅 해제 훅
                        event.accept()
                        return
            super().mousePressEvent(event)
            return
        if self._handle_active() and self._box_handles():
            # [2c] 네모·원: 회전(좌상단) → 꼭짓점 → 변 순으로 검사. setRect 자유 리사이즈.
            lp = event.pos()
            if self._box_rot_rect().contains(lp):
                self._rotating = True
                self.setTransformOriginPoint(self._content_rect().center())
                center = self.mapToScene(self._content_rect().center())
                self._press_angle = QLineF(center, event.scenePos()).angle()
                self._press_rot = self.rotation()
                self._begin_box_geom()   # 회전도 geom undo(기존 단일 핸들은 undo 없었음 — 개선)
                event.accept()
                return
            for i, r in self._box_corner_rects():
                if r.contains(lp):
                    self._box_resize = ("corner", i)
                    self._begin_box_geom()
                    event.accept()
                    return
            for k, r in self._box_edge_rects():
                if r.contains(lp):
                    self._box_resize = ("edge", k)
                    self._begin_box_geom()
                    event.accept()
                    return
            super().mousePressEvent(event)
            return
        if self._handle_active():
            # 회전 핸들이 바깥쪽이라 먼저 검사한다.
            if self._rot_handle_rect().contains(event.pos()):
                self._rotating = True
                self.setTransformOriginPoint(self._content_rect().center())
                center = self.mapToScene(self._content_rect().center())
                self._press_angle = QLineF(center, event.scenePos()).angle()
                self._press_rot = self.rotation()
                event.accept()
                return
            if self._handle_local_rect().contains(event.pos()):
                self._resizing = True
                self.setTransformOriginPoint(self._content_rect().center())
                center = self.mapToScene(self._content_rect().center())
                d = QLineF(center, event.scenePos()).length()
                self._press_dist = d if d > 1 else 1.0
                self._press_scale = self._scale_or_1()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_endpoint", None) is not None:
            self.prepareGeometryChange()  # 끝점이 boundingRect를 바꾼다
            p = event.pos()
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift = 각도 스냅(테두리 스냅과 상호배타)
                self._set_endpoint(self._drag_endpoint, self._snap_endpoint(self._drag_endpoint, p))
            elif self._owner_ortho():
                # [우리 확장] F8 Ortho = 인접 정점 기준 0/90° 제약(테두리 스냅보다 우선)
                self._set_endpoint(self._drag_endpoint, self._ortho_endpoint(self._drag_endpoint, p))
            else:
                # 근처 도형 테두리에 재스냅(뗐다 다시 붙이기). 화살표는 S자 곡선까지 복원.
                self._move_endpoint_with_snap(self._drag_endpoint, p)
            self.update()
            event.accept()
            return
        if self._box_resize is not None:   # [2c] 네모·원 자유 리사이즈(setRect)
            self._apply_box_resize(event.pos())
            event.accept()
            return
        if getattr(self, "_rotating", False):
            center = self.mapToScene(self._content_rect().center())
            cur = QLineF(center, event.scenePos()).angle()
            # QLineF.angle()은 반시계(+)·setRotation은 시계(+) → 부호 반전
            new_rot = self._press_rot - (cur - self._press_angle)
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                new_rot = round(new_rot / 15.0) * 15.0  # 15° 스냅
            self.setRotation(new_rot % 360)
            event.accept()
            return
        if getattr(self, "_resizing", False):
            self.prepareGeometryChange()  # 회전 여유분이 scale 의존 → 경계 캐시 갱신
            center = self.mapToScene(self._content_rect().center())
            d = QLineF(center, event.scenePos()).length()
            new = self._press_scale * (d / self._press_dist)
            self.setScale(max(0.15, min(new, 25.0)))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, "_drag_endpoint", None) is not None:
            self._drag_endpoint = None
            event.accept()
            return
        # [2c] 박스 리사이즈·회전 종료 — geom undo 커밋(자신+부착 화살표 통째 복원).
        if self._box_resize is not None or (self._rotating and self._box_handles()):
            self._box_resize = None
            self._rotating = False
            snap = self._box_snap
            self._box_snap = None
            self._box_bound = None
            self._box_orig_rect = None
            h = self._host()
            if snap and h is not None:
                h.push_undo_geom(snap)
            event.accept()
            return
        if getattr(self, "_rotating", False) or getattr(self, "_resizing", False):
            self._rotating = False
            self._resizing = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# 그래픽스 아이템 (전부 믹스인으로 크기조절 지원)
# ---------------------------------------------------------------------------

def _draw_selection_box(painter: QPainter, rect: QRectF, scale: float = 1.0):
    painter.setPen(QPen(QColor(_BLUE), 1.0 / (scale or 1.0), Qt.PenStyle.DashLine))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect)


def _draw_selection_ellipse(painter: QPainter, rect: QRectF, scale: float = 1.0):
    # 원의 선택 표시는 네모 박스가 아니라 곡선을 따라가는 점선 타원(펜·획 밖을 살짝 감쌈).
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(_BLUE), 1.0 / (scale or 1.0), Qt.PenStyle.DashLine))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(rect)


# ---------------------------------------------------------------------------
# [우리 확장] 라벨 믹스인 — 본체에 '부착'되어 함께 이동하는 자식 텍스트
#   _LabelMixin        : 공통 로직 + 선·화살표용 '중점 위쪽' 배치
#   _CenterLabelMixin  : 닫힌 도형(네모·원·심볼)용 '정중앙' 배치
# (도형 클래스보다 앞서야 상속 가능하므로 여기 둔다.)
# ---------------------------------------------------------------------------
class _LabelMixin:
    """더블클릭으로 다는 텍스트 라벨. 라벨은 자식(child _TextItem)이라 본체가 통째로
    이동하면 Qt가 자동으로 따라 옮기고, 로컬 기하가 바뀔 때만 _sync_label로 재배치한다.
    라벨은 부착 전용(독립 이동 불가). 기본 배치는 앵커 '위쪽'(선·화살표)."""

    def _init_label(self):
        self._label = None  # 자식 _TextItem or None

    def _label_anchor(self) -> QPointF:      # 하위 클래스 구현: 라벨을 붙일 로컬 기준점(중점)
        raise NotImplementedError

    def _label_color(self) -> QColor:        # 하위 클래스가 본체 색으로 override
        return QColor(_TEXT)

    def _label_alive(self) -> bool:
        lbl = getattr(self, "_label", None)
        return lbl is not None and lbl.scene() is not None

    def has_label(self) -> bool:
        return self._label_alive() and bool(self._label.toPlainText().strip())

    def _make_label(self):
        """라벨 아이템 생성(하위 클래스가 override 가능). 기본은 부착 전용 _TextItem."""
        return _TextItem(self._label_color())

    def ensure_label(self):
        """라벨이 없으면 생성해 중점에 부착하고 반환(있으면 그대로 반환)."""
        if not self._label_alive():
            lbl = self._make_label()
            lbl.setParentItem(self)
            # 부착 전용(선택·편집·삭제 가능). 화살표(sarrow) 라벨은 _ConnectorLabel이라 드래그로
            # 경로 위를 슬라이드하도록 Movable도 켠다(FigJam/Lucid) — itemChange가 경로에 재투영.
            flags = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            if isinstance(lbl, _ConnectorLabel):
                # Movable=드래그, SendsGeometryChanges=itemChange(ItemPositionChange) 발화(경로 재투영에 필수).
                flags |= (QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                          | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
            lbl.setFlags(flags)
            lbl.document().contentsChanged.connect(self._sync_label)  # 타이핑 중 중앙 유지
            self._label = lbl
        self._sync_label()
        return self._label

    def restore_label(self, d: dict):
        """문서 로드용 — 저장된 라벨(dict)을 자식으로 복원."""
        lbl = self.ensure_label()
        lbl.apply_font_size(d.get("font", 16))
        lbl.setPlainText(d.get("text", ""))
        lbl.apply_color(QColor(d.get("color", _TEXT)))
        if d.get("bg") is not None:
            lbl.set_bg(QColor(*d["bg"]))
        self._sync_label()
        return lbl

    def _sync_label(self):
        """라벨을 본체 중점 '위쪽'에 재배치. _content_rect(편집 프레임 여유 제외)을 써
        편집 중·완료 후 위치가 흔들리지 않게 한다."""
        if not self._label_alive():
            return
        a = self._label_anchor()
        br = self._label._content_rect()
        self._label.setPos(a.x() - br.width() / 2.0, a.y() - br.height() - 4.0)


# [우리 확장] 라벨 세로 광학정렬 — 글리프 '실제 잉크' 중심을 도형 중심에 맞춘다.
def _ink_center_dy(lbl) -> float:
    """라벨 글리프의 실제 잉크 세로중심이 문서박스 중심에서 벗어난 양(아래로 +).
    QGraphicsTextItem의 실렌더 글리프 배치가 baseline·폰트메트릭 추정과 어긋나(폰트·언어마다
    다름 — Malgun/폴백이 부호까지 반대), 어떤 공식으로도 못 맞춘다. 그래서 텍스트를 작은
    오프스크린에 그려 잉크를 픽셀로 직접 재 폰트·언어 무관하게 정확히 센터링한다.
    같은 (텍스트·폰트크기·여백)이면 캐시해 리사이즈 드래그 중 재계산을 피한다."""
    text = lbl.toPlainText()
    if not text.strip():
        return 0.0
    key = (text, round(lbl.font().pointSizeF(), 2), round(lbl.document().documentMargin(), 2))
    cached = getattr(lbl, "_ink_dy_cache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    br = lbl._content_rect()
    w = max(1, int(br.width()) + 2)
    h = max(1, int(br.height()) + 2)
    dy = 0.0
    if h > 2 and w > 2:
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        try:
            lbl.document().drawContents(p)   # 아이템 paint와 같은 문서 렌더 경로
        finally:
            p.end()
        top = bot = None
        for y in range(h):
            for x in range(w):
                if img.pixelColor(x, y).alpha() > 40:
                    if top is None:
                        top = y
                    bot = y
                    break
        if top is not None:
            dy = br.height() / 2.0 - (top + bot) / 2.0
    lbl._ink_dy_cache = (key, dy)
    return dy


class _CenterLabelMixin(_LabelMixin):
    """닫힌 도형(네모·원·심볼)용 라벨 — 선·화살표의 '중점 위쪽'과 달리 도형 '정중앙'에 놓고,
    rect가 바뀌면(그리기·박스 리사이즈·리베이크) 새 중앙으로 재동기한다. 앵커=rect 중심,
    색=테두리색. 셋이 공유해 중복을 없앤다. 세로는 문서박스가 아니라 글리프 '잉크' 중심을
    맞춘다(_ink_center_dy) — 폰트가 baseline 아래로 여유를 더 둬 글자가 위로 쏠려 보이는 것 교정."""

    def _label_anchor(self) -> QPointF:
        return self.rect().center()

    def _label_color(self) -> QColor:
        return QColor(self.pen().color())

    def _label_inset_ratio(self) -> float:
        """라벨이 들어갈 도형 내접 가용폭(도형폭 대비 비율). 이 폭을 넘기면 폰트를 축소해
        긴 텍스트가 빗변/곡선 밖으로 삐져나오지 않게 한다. 하위 클래스가 도형별로 override."""
        return 0.85

    _LABEL_MIN_PT = 5   # 축소 하한(이하로는 안 줄임 — 너무 작으면 차라리 도형을 키우는 게 답)

    def _fit_label_to_shape(self):
        """[우리 확장] 중앙 라벨을 도형 내접폭에 맞춰 '폰트 축소'로 맞춘다(단일 줄 유지, 줄바꿈 안 함).
        · 줄바꿈(wrap)은 마름모에서 줄 수가 폭발해 세로로 삐져나오는 결함이 있어 배제(실측). 폰트 축소는
          폭·세로를 동시에 보장한다. · 기준은 사용자 크기(_base_pt) — 도형이 커지면 그 값까지 되키운다.
        · 폭 측정은 _content_rect(문서 레이아웃)이 아니라 QFontMetricsF로 직접 한다 — contentsChanged
          콜백 시점엔 문서 레이아웃이 미완이라 _content_rect 폭이 stale이기 때문(실측). 멱등.
        · setFont이 contentsChanged를 재발화해 _sync_label→_fit이 재진입하면 서로의 폰트를 덮어써
          비결정적이 되므로 _fitting 가드로 재진입을 막는다(바깥 호출의 setFont 결과가 확정으로 남음)."""
        if getattr(self, "_fitting", False):
            return
        lbl = self._label
        self._fitting = True
        try:
            self._fit_label_impl(lbl)
        finally:
            self._fitting = False

    def _fit_label_impl(self, lbl):
        lbl.setTextWidth(-1)   # 단일 줄(폭은 폰트 축소로 맞춤)
        base = max(self._LABEL_MIN_PT, int(getattr(lbl, "_base_pt", lbl.font().pointSize() or 16)))
        margin = 2 * lbl.document().documentMargin()
        inner = max(1.0, self.rect().width() * self._label_inset_ratio())
        lines = lbl.toPlainText().split("\n") or [""]
        f = QFont(lbl.font())
        pt = base
        while pt > self._LABEL_MIN_PT:
            f.setPointSize(pt)
            fm = QFontMetricsF(f)
            widest = max((fm.horizontalAdvance(ln) for ln in lines), default=0.0)
            if widest + margin <= inner:
                break
            pt -= 1
        if lbl.font().pointSize() != pt:
            f2 = lbl.font()
            f2.setPointSize(pt)
            lbl.setFont(f2)

    def _sync_label(self):
        if not self._label_alive():
            return
        self._fit_label_to_shape()   # [우리 확장] 도형 내접폭에 맞춰 폰트 축소(넘침 방지)
        a = self._label_anchor()
        br = self._label._content_rect()
        dy = _ink_center_dy(self._label)
        self._label.setPos(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0 + dy)

    def setRect(self, *args):
        # rect가 바뀌면(그리기·박스 리사이즈·리베이크) 라벨을 새 중앙으로 재배치.
        super().setRect(*args)
        if self._label_alive():
            self._sync_label()


class _RectItem(_CenterLabelMixin, _HandleResizeMixin, QGraphicsRectItem):
    def __init__(self, *args):
        super().__init__(*args)
        self._init_resize()
        self._init_label()

    def clone(self):
        c = _RectItem(QRectF(self.rect()))
        c.setPen(QPen(self.pen()))
        c.setBrush(QBrush(self.brush()))
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 네 모서리를 씬변형 후 로컬 AABB로 setRect(회전=0면 정확).
    def _capture_geom_local(self):
        return QRectF(self.rect())

    def _apply_geom_local(self, g):
        self.setRect(g)

    def rebake_scene(self, fn):
        r = self.rect()
        pts = [self._rebake_pt(fn, c) for c in
               (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        self.prepareGeometryChange()
        self.setRect(QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))))

    def _stretch_grips(self):   # [Stage2b] 네모 grip = 네 모서리(걸친 모서리만 stretch 이동).
        r = self.rect()
        return [self.mapToScene(c) for c in
                (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]

    def _base_shape(self):
        # 속 빈 네모(NoBrush)는 '테두리 링'만 클릭 영역으로 — 내부를 통과시켜 네모 안에서
        # 다른 주석을 잡거나 새 도형(화살표 등)을 그릴 수 있게. 채움이 있으면 기본대로 전체.
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return super()._base_shape()
        path = QPainterPath()
        path.addRect(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), self._EDGE_HIT_MIN / self._scale_or_1()))
        return stroker.createStroke(path)

    def paint(self, painter, option, widget=None):
        self._paint_base_no_select(painter, option, widget)
        self._paint_handle(painter)


class _EllipseItem(_CenterLabelMixin, _HandleResizeMixin, QGraphicsEllipseItem):
    def __init__(self, *args):
        super().__init__(*args)
        self._init_resize()
        self._init_label()

    def _label_inset_ratio(self) -> float:
        return 0.72   # 타원은 세로중앙에서만 최대폭이라 네모보다 좁게 잡아 줄바꿈

    def clone(self):
        c = _EllipseItem(QRectF(self.rect()))
        c.setPen(QPen(self.pen()))
        c.setBrush(QBrush(self.brush()))
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 네모와 동일(로컬 AABB setRect).
    def _capture_geom_local(self):
        return QRectF(self.rect())

    def _apply_geom_local(self, g):
        self.setRect(g)

    def rebake_scene(self, fn):
        r = self.rect()
        pts = [self._rebake_pt(fn, c) for c in
               (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        self.prepareGeometryChange()
        self.setRect(QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))))

    def _stretch_grips(self):   # [Stage2b] 원 grip = 외접 사각 네 모서리(네모와 동일).
        r = self.rect()
        return [self.mapToScene(c) for c in
                (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]

    def _content_rect(self):
        # _LineItem과 동일 사이클 방지: QGraphicsEllipseItem.boundingRect()는 펜 두께가
        # 0이 아니면 shape()를 호출하므로, 사각형 기하에서 직접 계산해 재귀를 끊는다.
        extra = self.pen().widthF() / 2.0 + 1.0
        return self.rect().adjusted(-extra, -extra, extra, extra)

    def _base_shape(self):
        # 속 빈 원(NoBrush)은 '테두리 링'만 클릭 영역으로(네모와 동일). QGraphicsEllipseItem
        # 기본 shape()는 boundingRect()를 부르지 않고 rect에서 직접 만드므로 재귀 없음.
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return super()._base_shape()
        path = QPainterPath()
        path.addEllipse(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), self._EDGE_HIT_MIN / self._scale_or_1()))
        return stroker.createStroke(path)

    def paint(self, painter, option, widget=None):
        # 네모와 달리 선택 표시를 곡선 따라가는 점선 타원으로 그린다(_paint_base_no_select의
        # 사각 박스 대신 _paint_base + 점선 타원).
        self._paint_base(painter, option, widget)
        if self.isSelected():
            _draw_selection_ellipse(painter, self._content_rect(), self._scale_or_1())
        self._paint_handle(painter)


# ---------------------------------------------------------------------------
# [우리 확장] 심볼/스텐실 — 순서도 표준 도형(판단·입출력·준비 등)
# ---------------------------------------------------------------------------
# 설계: 종류마다 클래스를 만들지 않고 단일 _SymbolItem(rect 기반)에 kind만 달리한다.
# rect 기반이라 _RectItem이 쓰는 기계(_box_handles 리사이즈·회전·stretch·geom undo)를
# 그대로 물려받고, paint/shape만 kind별 경로로 갈아끼운다. 경로 팩토리는 QRectF→QPainterPath.
def _sym_decision(r: QRectF) -> QPainterPath:      # 판단 — 마름모
    p = QPainterPath()
    c = r.center()
    p.moveTo(c.x(), r.top())
    p.lineTo(r.right(), c.y())
    p.lineTo(c.x(), r.bottom())
    p.lineTo(r.left(), c.y())
    p.closeSubpath()
    return p


def _sym_terminal(r: QRectF) -> QPainterPath:      # 시작/끝 — 스타디움(둥근 양끝)
    p = QPainterPath()
    rad = min(r.width(), r.height()) / 2.0
    p.addRoundedRect(r, rad, rad)
    return p


def _sym_data(r: QRectF) -> QPainterPath:          # 입출력 — 평행사변형
    p = QPainterPath()
    dx = r.width() * 0.22
    p.moveTo(r.left() + dx, r.top())
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right() - dx, r.bottom())
    p.lineTo(r.left(), r.bottom())
    p.closeSubpath()
    return p


def _sym_prep(r: QRectF) -> QPainterPath:          # 준비 — 육각형
    p = QPainterPath()
    dx = r.width() * 0.2
    cy = r.center().y()
    p.moveTo(r.left() + dx, r.top())
    p.lineTo(r.right() - dx, r.top())
    p.lineTo(r.right(), cy)
    p.lineTo(r.right() - dx, r.bottom())
    p.lineTo(r.left() + dx, r.bottom())
    p.lineTo(r.left(), cy)
    p.closeSubpath()
    return p


def _sym_document(r: QRectF) -> QPainterPath:      # 문서 — 아래 물결
    p = QPainterPath()
    wave = r.height() * 0.14
    p.moveTo(r.left(), r.top())
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right(), r.bottom() - wave)
    p.cubicTo(r.right() - r.width() * 0.25, r.bottom() - wave * 3.0,
              r.left() + r.width() * 0.25, r.bottom() + wave,
              r.left(), r.bottom() - wave)
    p.closeSubpath()
    return p


def _sym_database(r: QRectF) -> QPainterPath:      # 저장소 — 원기둥
    p = QPainterPath()
    e = min(r.height() * 0.18, r.width() * 0.5)   # 윗/아랫 타원 반높이
    top = QRectF(r.left(), r.top(), r.width(), 2 * e)
    bot = QRectF(r.left(), r.bottom() - 2 * e, r.width(), 2 * e)
    p.addEllipse(top)                              # 윗면 타원(완전)
    p.moveTo(r.left(), r.top() + e)                # 몸통 왼쪽
    p.lineTo(r.left(), r.bottom() - e)
    p.arcTo(bot, 180.0, 180.0)                     # 아랫면 앞쪽 반원
    p.lineTo(r.right(), r.top() + e)               # 몸통 오른쪽
    return p


# kind → (한글 라벨, 경로 팩토리). 팔레트·직렬화·그리기가 이 하나를 공유한다.
_SYMBOL_KINDS = {
    "decision": ("판단", _sym_decision),
    "terminal": ("시작/끝", _sym_terminal),
    "data":     ("입출력", _sym_data),
    "prep":     ("준비", _sym_prep),
    "document": ("문서", _sym_document),
    "database": ("저장소", _sym_database),
}


# (_LabelMixin·_CenterLabelMixin은 도형 클래스보다 앞서야 해서 _RectItem 위로 이동함)


class _SymbolItem(_CenterLabelMixin, _HandleResizeMixin, QGraphicsRectItem):
    """순서도 심볼 — rect 기반이라 _RectItem과 동일한 리사이즈·회전·stretch·undo를
    물려받고, paint/shape만 kind별 경로(_SYMBOL_KINDS)로 그린다. 더블클릭 중앙 라벨은
    _CenterLabelMixin이 네모·원과 공유한다.
    (_SYMBOL_KINDS를 참조하므로 경로 팩토리 뒤에 둔다.)"""

    def __init__(self, kind: str, rect: QRectF):
        super().__init__(rect)
        self._kind = kind if kind in _SYMBOL_KINDS else "decision"
        self._init_resize()
        self._init_label()

    def _sym_path(self) -> QPainterPath:
        return _SYMBOL_KINDS[self._kind][1](self.rect())

    def _label_inset_ratio(self) -> float:
        # kind별 내접 가용폭 — 마름모는 세로중앙 한 점에서만 최대폭이라 가장 좁게, 원기둥·문서 등
        # 곡선 심볼은 중간, 상하 평행한 스타디움·평행사변형·육각형은 넉넉히.
        if self._kind == "decision":
            return 0.6
        if self._kind in ("database", "document"):
            return 0.72
        return 0.78

    def _label_anchor(self) -> QPointF:
        # 광학 중심 보정: 외접 rect 중심이 도형의 '보이는 무게중심'과 어긋나는 kind만 라벨을
        # 옮긴다. 원기둥(database)은 윗 타원이 중심을 위로 끌어 라벨이 윗 곡선에 겹치므로 아래로,
        # 문서(document)는 아래 물결이 무게를 아래로 내리므로 살짝 위로. 나머지(마름모·스타디움·
        # 평행사변형·육각형)는 상하 대칭이라 rect 중심이 곧 광학 중심 → 보정 없음.
        c = self.rect().center()
        r = self.rect()
        if self._kind == "database":
            e = min(r.height() * 0.18, r.width() * 0.5)   # 윗/아랫 타원 반높이(_sym_database와 동일)
            return QPointF(c.x(), c.y() + e * 0.7)
        if self._kind == "document":
            return QPointF(c.x(), c.y() - r.height() * 0.06)
        return c

    def clone(self):
        c = _SymbolItem(self._kind, QRectF(self.rect()))
        c.setPen(QPen(self.pen()))
        c.setBrush(QBrush(self.brush()))
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 네모·원과 동일(로컬 AABB setRect).
    def _capture_geom_local(self):
        return QRectF(self.rect())

    def _apply_geom_local(self, g):
        self.setRect(g)

    def rebake_scene(self, fn):
        r = self.rect()
        pts = [self._rebake_pt(fn, c) for c in
               (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        self.prepareGeometryChange()
        self.setRect(QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))))

    def _stretch_grips(self):   # [Stage2b] grip = 외접 사각 네 모서리(네모와 동일).
        r = self.rect()
        return [self.mapToScene(c) for c in
                (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]

    def _base_shape(self):
        # 속 빈 심볼(NoBrush)은 외곽선만 클릭 영역으로(네모와 동일 — 안에서 화살표 시작 가능),
        # 채움이 있으면 심볼 전체가 클릭 영역.
        path = self._sym_path()
        if self.brush().style() != Qt.BrushStyle.NoBrush:
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), self._EDGE_HIT_MIN / self._scale_or_1()))
        return stroker.createStroke(path)

    def paint(self, painter, option, widget=None):
        # 네모의 _paint_base_no_select(super().paint()가 사각을 그림) 대신 심볼 경로를 직접 그린다.
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawPath(self._sym_path())
        if self.isSelected():
            _draw_selection_box(painter, self._content_rect(), self._scale_or_1())
        self._paint_handle(painter)


# ---------------------------------------------------------------------------
# [우리 확장 · Phase 4] 삽입 이미지 — PNG/JPG를 도면에 배치
# ---------------------------------------------------------------------------
class _ImageItem(_HandleResizeMixin, QGraphicsRectItem):
    """삽입 이미지 — rect 기반이라 _RectItem·_SymbolItem과 동일한 리사이즈·회전·stretch·undo를
    그대로 물려받고, paint만 원본 픽스맵을 rect에 스케일해 그리도록 갈아끼운다.
    원본 픽스맵(_pixmap)을 전체 해상도로 보관 → 저장/재열기·PDF에도 화질 손실 없음(rect는 표시 크기).
    종횡비는 꼭짓점 리사이즈에서 고정(_constrain_box_rect) — 변 리사이즈는 자유(의도적 늘림)."""

    def __init__(self, pixmap: QPixmap, rect: QRectF):
        super().__init__(rect)
        self._pixmap = pixmap
        self.setPen(QPen(Qt.PenStyle.NoPen))   # 테두리 없음 — 이미지 픽셀만 그린다
        self._init_resize()

    def _aspect(self) -> float:
        w, h = self._pixmap.width(), self._pixmap.height()
        return (w / h) if h else 1.0

    def clone(self):
        c = _ImageItem(QPixmap(self._pixmap), QRectF(self.rect()))
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 네모·심볼과 동일(로컬 AABB setRect).
    def _capture_geom_local(self):
        return QRectF(self.rect())

    def _apply_geom_local(self, g):
        self.setRect(g)

    def rebake_scene(self, fn):
        r = self.rect()
        pts = [self._rebake_pt(fn, c) for c in
               (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        self.prepareGeometryChange()
        self.setRect(QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))))

    def _stretch_grips(self):   # [Stage2b] grip = 네 모서리(네모와 동일).
        r = self.rect()
        return [self.mapToScene(c) for c in
                (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]

    def _content_rect(self) -> QRectF:
        return QRectF(self.rect())

    def _constrain_box_rect(self, new: QRectF, kind: str, key) -> QRectF:
        # 꼭짓점 드래그는 원본 종횡비를 유지(사진 왜곡 방지). 대각 고정점(opp) 기준으로,
        # 폭·높이 중 더 많이 자란 쪽에 비율을 맞춰 사각형을 다시 세운다.
        if kind != "corner":
            return new
        o = self._box_orig_rect
        opp = [o.bottomRight(), o.bottomLeft(), o.topLeft(), o.topRight()][key]  # 0TL 1TR 2BR 3BL
        asp = self._aspect()
        w = max(new.width(), new.height() * asp)
        h = w / asp
        sx = 1.0 if key in (1, 2) else -1.0   # TR·BR = 오른쪽, TL·BL = 왼쪽
        sy = 1.0 if key in (2, 3) else -1.0   # BR·BL = 아래,   TL·TR = 위
        return QRectF(opp, QPointF(opp.x() + sx * w, opp.y() + sy * h)).normalized()

    def paint(self, painter, option, widget=None):
        painter.drawPixmap(self.rect(), self._pixmap, QRectF(self._pixmap.rect()))
        if self.isSelected():
            _draw_selection_box(painter, self._content_rect(), self._scale_or_1())
        self._paint_handle(painter)


# ---------------------------------------------------------------------------
# [우리 확장 · Phase 4] 표제란 / 용지틀 — 도면번호·축척·발주처가 들어가는 우하단 표 + A-size 용지경계
# ---------------------------------------------------------------------------
# 설계(deep-interview 2026-07-20): 진짜 paper space(뷰포트·이중좌표계)를 도입하지 않고,
# 무한 모델공간(mm 월드좌표) 위에 '용지 프레임 객체' 하나를 얹는다. 프레임은 A-size 고정
# (임의 리사이즈 금지 — '용지'의 의미 보존), 이동만 가능. 크기·방향은 삽입/편집 시 재선택.
# rect는 용지 mm 치수(0,0,W,H). 표제란 필드값은 dict로 보관하고 paint가 표 칸에 텍스트로 렌더.
# 참고 도면(docs/reference/)에 정형 표제란이 없어 표준 KS식 3행 표로 잡음(레이아웃은 조정 가능).

# 용지 mm 치수(세로 기준 w,h). 가로(landscape)는 w·h 교환.
PAPER_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
}

# 표제란 행 정의: (행 높이 가중치, [(라벨, 필드키, 열 폭 가중치), ...]).
# 각 행의 열 폭 가중치 합은 같아야(=5) 열이 세로로 정렬된다. 필드키 ""는 라벨만(값 칸 없음).
_TB_ROWS = [
    (1.2, [("발주처 / 프로젝트", "client", 3), ("도면번호", "number", 2)]),
    (1.2, [("도면명", "title", 3), ("축척", "scale", 2)]),
    (1.0, [("작성", "author", 2), ("검토", "reviewer", 2), ("날짜", "date", 1)]),
]
# 표제란 필드키(폼·직렬화 공용) — _TB_ROWS에서 실제 쓰는 키만.
TB_FIELD_KEYS = ("client", "number", "title", "scale", "author", "reviewer", "date")
TB_FIELD_LABELS = {
    "client": "발주처 / 프로젝트", "number": "도면번호", "title": "도면명",
    "scale": "축척", "author": "작성자", "reviewer": "검토자", "date": "날짜",
}


class _TitleBlockItem(QGraphicsRectItem):
    """용지틀 + 표제란 — A-size 용지경계 rect와 우하단 표제란 표를 그린다. rect 기반이지만
    _HandleResizeMixin은 쓰지 않는다(용지는 고정 크기, 이동만). 더블클릭 편집은 host의 폼
    다이얼로그가 처리(뷰가 _edit_titleblock으로 위임). 필드값(_fields)만 바뀌므로 paint로 반영.
    DXF 내보내기에서는 _RectItem이 아니라 isinstance 체인에 안 걸려 조용히 제외된다(스코프)."""

    _M = 10.0        # 용지 가장자리 → 도면 테두리 여백(mm)
    _TB_W = 180.0    # 표제란 표 폭(mm)
    _TB_H = 33.0     # 표제란 표 높이(mm)
    _PAPER_FILL = QColor("#FFFFFF")
    _LINE = QColor("#333333")
    _INK = QColor("#111111")

    def __init__(self, size: str = "A2", orient: str = "landscape", fields: dict | None = None):
        super().__init__()
        self._size = size if size in PAPER_SIZES_MM else "A2"
        self._orient = "portrait" if orient == "portrait" else "landscape"
        self._fields = {k: "" for k in TB_FIELD_KEYS}
        if fields:
            self._fields.update({k: str(v) for k, v in fields.items() if k in TB_FIELD_KEYS})
        self.setPen(QPen(Qt.PenStyle.NoPen))   # 테두리는 paint가 직접 그림
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._apply_paper_rect()

    # ---- 용지 치수 ----------------------------------------------------------
    def paper_wh(self) -> tuple[float, float]:
        w, h = PAPER_SIZES_MM[self._size]
        return (h, w) if self._orient == "landscape" else (w, h)

    def _apply_paper_rect(self):
        w, h = self.paper_wh()
        self.prepareGeometryChange()
        self.setRect(QRectF(0.0, 0.0, w, h))

    def set_paper(self, size: str, orient: str):
        if size in PAPER_SIZES_MM:
            self._size = size
        self._orient = "portrait" if orient == "portrait" else "landscape"
        self._apply_paper_rect()
        self.update()

    def set_fields(self, fields: dict):
        for k in TB_FIELD_KEYS:
            if k in fields:
                self._fields[k] = str(fields[k])
        self.update()

    def clone(self):
        c = _TitleBlockItem(self._size, self._orient, dict(self._fields))
        c.setPos(self.pos())
        c.setZValue(self.zValue())
        c.setFlags(self.flags())
        return c

    # ---- 표제란 표 영역(용지 로컬좌표, 도면 테두리 안쪽 우하단) --------------------
    def _tb_rect(self) -> QRectF:
        inner = self.rect().adjusted(self._M, self._M, -self._M, -self._M)
        w = min(self._TB_W, inner.width())
        return QRectF(inner.right() - w, inner.bottom() - self._TB_H, w, self._TB_H)

    # ---- 히트 영역: 용지 테두리 밴드 + 표제란만(내부는 통과시켜 위에 그리기 가능) --------
    def boundingRect(self) -> QRectF:
        return self.rect().adjusted(-3.0, -3.0, 3.0, 3.0)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        border = QPainterPath()
        border.addRect(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(self._M)
        path.addPath(stroker.createStroke(border))
        path.addRect(self._tb_rect())
        return path

    # ---- 렌더 ---------------------------------------------------------------
    @staticmethod
    def _font_px(painter, px: float, bold: bool = False):
        f = painter.font()
        f.setPixelSize(max(1, int(round(px))))
        f.setBold(bold)
        painter.setFont(f)

    def paint(self, painter, option, widget=None):
        r = self.rect()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # 용지 바탕(흰 시트) + 용지 경계선
        painter.setBrush(QBrush(self._PAPER_FILL))
        painter.setPen(QPen(self._LINE, 0.5))
        painter.drawRect(r)
        # 도면 테두리(안쪽, 굵게)
        inner = r.adjusted(self._M, self._M, -self._M, -self._M)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._LINE, 1.2))
        painter.drawRect(inner)
        # 표제란 표
        self._paint_table(painter)
        painter.restore()
        if self.isSelected():
            _draw_selection_box(painter, r, self._scale_or_1())

    def _scale_or_1(self) -> float:
        s = self.scale()
        return s if s else 1.0

    def _paint_table(self, painter):
        tb = self._tb_rect()
        painter.setBrush(QBrush(self._PAPER_FILL))
        painter.setPen(QPen(self._LINE, 1.2))
        painter.drawRect(tb)
        painter.setPen(QPen(self._LINE, 0.5))
        h_weight = sum(rw for rw, _ in _TB_ROWS)
        y = tb.top()
        for ri, (rw, cells) in enumerate(_TB_ROWS):
            rh = tb.height() * (rw / h_weight)
            if ri > 0:  # 행 구분선
                painter.drawLine(QPointF(tb.left(), y), QPointF(tb.right(), y))
            c_weight = sum(cw for _l, _k, cw in cells)
            x = tb.left()
            for ci, (label, key, cw) in enumerate(cells):
                cwid = tb.width() * (cw / c_weight)
                cell = QRectF(x, y, cwid, rh)
                if ci > 0:  # 열 구분선
                    painter.setPen(QPen(self._LINE, 0.5))
                    painter.drawLine(QPointF(x, y), QPointF(x, y + rh))
                self._paint_cell(painter, cell, label, self._fields.get(key, ""))
                x += cwid
            y += rh

    def _paint_cell(self, painter, cell: QRectF, label: str, value: str):
        pad = 1.2
        # 라벨(작게, 좌상단)
        painter.setPen(QPen(self._INK))
        self._font_px(painter, 2.6)
        lbl_rect = cell.adjusted(pad, pad, -pad, -pad)
        painter.drawText(lbl_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), label)
        # 값(크게, 가운데)
        if value:
            self._font_px(painter, 3.8)
            painter.drawText(cell, int(Qt.AlignmentFlag.AlignCenter), value)


# ---------------------------------------------------------------------------
# [우리 확장 · Phase 4] 표(table) — NxM 균등 격자 + 셀 텍스트(인라인 편집)
# ---------------------------------------------------------------------------
# 설계(deep-interview 2026-07-20): rect 기반이라 _ImageItem·_TitleBlockItem처럼 리사이즈·회전·
# undo·그룹변형·PDF·복제를 그대로 상속(_HandleResizeMixin + setRect → 8핸들 자유 리사이즈).
# 균등 비례 격자(전체 리사이즈 시 모든 열·행이 같은 비율로 스케일 — 개별 열폭 조절은 후속 스코프).
# 셀 텍스트는 2차원 리스트(_cells[r][c]). 셀 편집은 뷰가 인라인 QLineEdit(_CellEditor)로 처리.
# 첫 행 헤더(_header=True면 굵게+옅은 배경). DXF 제외(isinstance 체인 밖), .ecad 직렬화.
class _TableItem(_HandleResizeMixin, QGraphicsRectItem):
    """NxM 균등 격자 표. rect 기반 — _ImageItem과 동일한 자유 리사이즈(꼭짓점 2D·변 1축)를 상속.
    종횡비 고정은 하지 않는다(표는 임의 비율) — 기본 _constrain_box_rect(무변형)를 그대로 쓴다."""

    _LINE = QColor("#333333")
    _INK = QColor("#111111")
    _HEADER_FILL = QColor("#EEEEEE")

    def __init__(self, rows: int, cols: int, rect: QRectF,
                 cells: list | None = None, header: bool = True):
        super().__init__(rect)
        self._rows = max(1, int(rows))
        self._cols = max(1, int(cols))
        self._header = bool(header)
        self._cells = self._norm_cells(cells)
        self.setPen(QPen(Qt.PenStyle.NoPen))     # 격자·외곽은 paint가 직접 그림
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._init_resize()

    def _norm_cells(self, cells) -> list:
        """cells를 rows×cols 문자열 격자로 정규화(부족분은 빈칸, 초과분은 잘라냄)."""
        grid = [["" for _ in range(self._cols)] for _ in range(self._rows)]
        if cells:
            for r in range(min(self._rows, len(cells))):
                row = cells[r] or []
                for c in range(min(self._cols, len(row))):
                    grid[r][c] = "" if row[c] is None else str(row[c])
        return grid

    # ---- 셀 접근(뷰 인라인 편집이 사용) --------------------------------------
    def dims(self) -> tuple[int, int]:
        return self._rows, self._cols

    def cell_text(self, r: int, c: int) -> str:
        return self._cells[r][c]

    def set_cell_text(self, r: int, c: int, text: str):
        if 0 <= r < self._rows and 0 <= c < self._cols:
            self._cells[r][c] = str(text)
            self.update()

    # ---- 셀 기하(로컬좌표) --------------------------------------------------
    def cell_rect(self, r: int, c: int) -> QRectF:
        box = self.rect()
        cw = box.width() / self._cols
        ch = box.height() / self._rows
        return QRectF(box.left() + c * cw, box.top() + r * ch, cw, ch)

    def cell_at(self, local: QPointF):
        """로컬좌표 local이 속한 (r, c) — 격자 밖이면 None."""
        box = self.rect()
        if not box.contains(local):
            return None
        cw = box.width() / self._cols
        ch = box.height() / self._rows
        if cw <= 0 or ch <= 0:
            return None
        c = min(max(int((local.x() - box.left()) / cw), 0), self._cols - 1)
        r = min(max(int((local.y() - box.top()) / ch), 0), self._rows - 1)
        return (r, c)

    def clone(self):
        c = _TableItem(self._rows, self._cols, QRectF(self.rect()),
                       [row[:] for row in self._cells], self._header)
        return self._copy_common_to(c)

    # [Stage2] rect 기반 리베이크·grip — _ImageItem과 동일(로컬 AABB setRect).
    def _capture_geom_local(self):
        return QRectF(self.rect())

    def _apply_geom_local(self, g):
        self.setRect(g)

    def rebake_scene(self, fn):
        r = self.rect()
        pts = [self._rebake_pt(fn, cc) for cc in
               (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        self.prepareGeometryChange()
        self.setRect(QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))))

    def _stretch_grips(self):
        r = self.rect()
        return [self.mapToScene(cc) for cc in
                (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]

    def _content_rect(self) -> QRectF:
        return QRectF(self.rect())

    @staticmethod
    def _font_px(painter, px: float, bold: bool = False):
        f = painter.font()
        f.setPixelSize(max(1, int(round(px))))
        f.setBold(bold)
        painter.setFont(f)

    def paint(self, painter, option, widget=None):
        box = self.rect()
        cw = box.width() / self._cols
        ch = box.height() / self._rows
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        # 헤더 행 옅은 배경
        if self._header:
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(self._HEADER_FILL))
            painter.drawRect(QRectF(box.left(), box.top(), box.width(), ch))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        # 셀 텍스트(폰트 크기는 셀 치수에 맞춰 축소)
        fs = max(2.0, min(ch * 0.5, cw * 0.30))
        for r in range(self._rows):
            for c in range(self._cols):
                txt = self._cells[r][c]
                if not txt:
                    continue
                self._font_px(painter, fs, bold=(self._header and r == 0))
                painter.setPen(QPen(self._INK))
                painter.drawText(
                    self.cell_rect(r, c).adjusted(1.0, 1.0, -1.0, -1.0),
                    int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), txt)
        # 내부 격자선
        painter.setPen(QPen(self._LINE, 0.5))
        for i in range(1, self._cols):
            x = box.left() + i * cw
            painter.drawLine(QPointF(x, box.top()), QPointF(x, box.bottom()))
        for j in range(1, self._rows):
            y = box.top() + j * ch
            painter.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
        # 외곽선
        painter.setPen(QPen(self._LINE, 1.0))
        painter.drawRect(box)
        painter.restore()
        if self.isSelected():
            _draw_selection_box(painter, box, self._scale_or_1())
        self._paint_handle(painter)


class _CellEditor(QLineEdit):
    """[우리 확장 · Phase 4] 표 셀 인라인 편집기 — 뷰 viewport 위에 떠서 한 셀을 편집.
    Enter=아래 칸, Tab=오른쪽(줄 끝이면 다음 줄 첫 칸), Shift+Tab=왼쪽, Esc=취소, 포커스 상실=커밋.
    셀 편집은 undo 스코프 밖(표제란 필드와 동일) — set_cell_text로 직접 반영."""

    def __init__(self, view, item: "_TableItem", r: int, c: int):
        super().__init__(view.viewport())
        self._view = view
        self._item = item
        self._r = r
        self._c = c
        self._done = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(item.cell_text(r, c))
        self.selectAll()
        self._place()
        self.show()
        self.setFocus()

    def _place(self):
        """셀 rect(아이템 로컬)를 뷰 픽셀좌표로 매핑해 편집기 위치·크기 설정."""
        cell = self._item.cell_rect(self._r, self._c)
        pts = [self._view.mapFromScene(self._item.mapToScene(p)) for p in
               (cell.topLeft(), cell.topRight(), cell.bottomRight(), cell.bottomLeft())]
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        self.setGeometry(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def _commit(self):
        if not self._done:
            self._done = True
            self._item.set_cell_text(self._r, self._c, self.text())

    def _cancel(self):
        self._done = True   # 커밋하지 않고 닫기

    def _move(self, dr: int, dc: int):
        rows, cols = self._item.dims()
        r, c = self._r + dr, self._c + dc
        while c >= cols:       # Tab 줄넘김(오른쪽 끝 → 다음 줄 첫 칸)
            c -= cols
            r += 1
        while c < 0:           # Shift+Tab 줄넘김(왼쪽 끝 → 이전 줄 마지막 칸)
            c += cols
            r -= 1
        self._commit()
        self.close()
        if 0 <= r < rows and 0 <= c < cols:
            self._view._begin_cell_edit(self._item, r, c)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._move(1, 0)
            return
        if key == Qt.Key.Key_Escape:
            self._cancel()
            self.close()
            return
        super().keyPressEvent(event)

    def event(self, e):
        # Tab/Backtab은 위젯 포커스 순회로 먼저 소비되므로 event()에서 가로챈다.
        if e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self._move(0, 1 if e.key() == Qt.Key.Key_Tab else -1)
            return True
        return super().event(e)

    def focusOutEvent(self, event):
        self._commit()
        self.close()
        super().focusOutEvent(event)


class _LineItem(_LabelMixin, _HandleResizeMixin, QGraphicsLineItem):
    def __init__(self, *args):
        super().__init__(*args)
        self._init_resize()
        self._init_label()

    def setLine(self, *args):
        super().setLine(*args)
        self._sync_label()   # 끝점 이동·그리기로 선 기하가 바뀌면 라벨을 중점에 재배치

    def _label_anchor(self) -> QPointF:
        line = self.line()
        return QPointF((line.x1() + line.x2()) / 2.0, (line.y1() + line.y2()) / 2.0)

    def _label_color(self) -> QColor:
        return self.pen().color()

    def clone(self):
        c = _LineItem(QLineF(self.line()))
        c.setPen(QPen(self.pen()))
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 두 끝점을 씬변형.
    def _capture_geom_local(self):
        return QLineF(self.line())

    def _apply_geom_local(self, g):
        self.setLine(g)

    def rebake_scene(self, fn):
        ln = self.line()
        self.setLine(QLineF(self._rebake_pt(fn, ln.p1()), self._rebake_pt(fn, ln.p2())))

    def _uses_endpoints(self):
        return True

    def _endpoints(self):
        line = self.line()
        return [line.p1(), line.p2()]

    def _set_endpoint(self, idx, p):
        line = self.line()
        if idx == 0:
            self.setLine(QLineF(QPointF(p), line.p2()))
        else:
            self.setLine(QLineF(line.p1(), QPointF(p)))

    def _content_rect(self):
        # Qt 기본 QGraphicsLineItem.boundingRect()는 펜 두께가 0이 아니면 내부적으로
        # shape()를 호출하는데, 믹스인 shape()가 핸들 계산에 다시 boundingRect()를 부르므로
        # 무한 재귀(스택 오버플로 → 프로세스 abort)가 된다. 선 기하에서 직접 계산해 사이클을 끊는다.
        line = self.line()
        extra = self.pen().widthF() / 2.0 + 1.0
        return QRectF(line.p1(), line.p2()).normalized().adjusted(-extra, -extra, extra, extra)

    def boundingRect(self):
        # 선택 외곽선(획+8)이 _content_rect보다 살짝 바깥으로 나가므로 여유를 더 준다
        # (안 그러면 수평/수직 선에서 점선 잔상이 남을 수 있음).
        pad = 5.0 / self._scale_or_1()
        return super().boundingRect().adjusted(-pad, -pad, pad, pad)

    def _paint_selection_outline(self, painter, scale):
        # 화살표와 동일하게 '선을 따라가는' 점선(네모 박스 아님). 획을 살짝 넓게 감싼다.
        line = self.line()
        body = QPainterPath()
        body.moveTo(line.p1())
        body.lineTo(line.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(self.pen().widthF() + 8)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        outline = stroker.createStroke(body)
        painter.setPen(QPen(QColor(_BLUE), 1.0 / (scale or 1.0), Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(outline.simplified())

    def paint(self, painter, option, widget=None):
        self._paint_base(painter, option, widget)
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)


class _PathItem(_HandleResizeMixin, QGraphicsPathItem):
    def __init__(self, *args):
        super().__init__(*args)
        self._init_resize()
        self._sel_outline = None  # 선택 점선 외곽선 캐시(획·펜 불변 → 이동 중 재계산 회피)

    def setPath(self, path):
        self._sel_outline = None
        super().setPath(path)

    def setPen(self, pen):
        self._sel_outline = None
        super().setPen(pen)

    def clone(self):
        c = _PathItem(QPainterPath(self.path()))
        c.setPen(QPen(self.pen()))
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 패스 원소(Move/Line/Curve)의 모든 점을 씬변형.
    def _capture_geom_local(self):
        return QPainterPath(self.path())

    def _apply_geom_local(self, g):
        self.setPath(g)

    def rebake_scene(self, fn):
        old = self.path()
        np = QPainterPath()
        i, n = 0, old.elementCount()
        while i < n:
            el = old.elementAt(i)
            p = self._rebake_pt(fn, QPointF(el.x, el.y))
            if el.isMoveTo():
                np.moveTo(p)
                i += 1
            elif el.isCurveTo():   # 3개(제어1·제어2·끝점) 묶음
                e2 = old.elementAt(i + 1)
                e3 = old.elementAt(i + 2)
                np.cubicTo(p, self._rebake_pt(fn, QPointF(e2.x, e2.y)),
                           self._rebake_pt(fn, QPointF(e3.x, e3.y)))
                i += 3
            else:              # LineToElement
                np.lineTo(p)
                i += 1
        self.prepareGeometryChange()
        self.setPath(np)

    def _content_rect(self):
        # _LineItem과 동일 사이클 방지: QGraphicsPathItem.boundingRect()는 brush가 NoBrush일 때
        # shape()를 호출하므로, 패스 기하에서 직접 계산해 믹스인 shape()와의 재귀를 끊는다.
        extra = self.pen().widthF() / 2.0 + 1.0
        return self.path().boundingRect().adjusted(-extra, -extra, extra, extra)

    def _handle_active(self):
        # 펜은 회전·확대 핸들을 두지 않는다 — 그리기 전용이라 잘못 그리면 삭제·되돌리기로
        # 수정하지 변형하지 않는다. 선택 시 획 따라가는 점선만, 이동은 획 잡아 끌기(movable).
        return False

    def _base_shape(self):
        # 클릭 영역은 '획 위'만 — Qt 기본 QGraphicsPathItem.shape()는 스트로크에 원본 패스를
        # addPath로 더해, 닫힌(감싸는) 펜 획의 안쪽 면까지 클릭 영역에 포함한다. 그러면 도형을
        # 빙 둘러 그린 펜이 안쪽 빈 공간의 클릭을 통째로 가로채 안쪽 도형이 선택되지 않는다.
        # 획만 두껍게 스트로크한 밴드를 반환해(안쪽은 비움) 루프 안 도형이 정상 선택되게 한다.
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 10) + 4)   # 잡기 쉬운 폭
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.path())

    def boundingRect(self):
        # 선택 외곽선(획+8)이 _content_rect보다 살짝 바깥으로 나가므로 여유를 더 준다.
        pad = 5.0 / self._scale_or_1()
        return super().boundingRect().adjusted(-pad, -pad, pad, pad)

    def _paint_selection_outline(self, painter, scale):
        # 펜 획을 따라가는 점선(네모 박스 아님) — 획을 살짝 넓게 감싼다.
        # 스트로크 생성·단순화는 무겁고 획·펜이 안 바뀌면 결과가 동일하므로 캐시해
        # 이동(평행이동) 중 매 프레임 재계산을 피한다(버벅임 제거).
        if self._sel_outline is None:
            stroker = QPainterPathStroker()
            stroker.setWidth(self.pen().widthF() + 8)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self._sel_outline = stroker.createStroke(self.path()).simplified()
        painter.setPen(QPen(QColor(_BLUE), 1.0 / (scale or 1.0), Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._sel_outline)

    def paint(self, painter, option, widget=None):
        self._paint_base(painter, option, widget)
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)


def _cubic_axis_extrema(p0: float, c1: float, c2: float, p3: float):
    """한 축(x 또는 y)에서 3차 베지어가 극값을 갖는 t(∈[0,1])들을 반환.
    B'(t)=0 → A t² + B t + C = 0 (A=−p0+3c1−3c2+p3의 미분 계수). 근만 반환(끝점 0·1은 콜러가 포함)."""
    a = c1 - p0
    b = c2 - c1
    c = p3 - c2
    A = a - 2 * b + c
    B = 2 * (b - a)
    C = a
    ts = []
    if abs(A) < 1e-9:
        if abs(B) > 1e-9:
            ts.append(-C / B)
    else:
        disc = B * B - 4 * A * C
        if disc >= 0:
            sq = math.sqrt(disc)
            ts.append((-B + sq) / (2 * A))
            ts.append((-B - sq) / (2 * A))
    return [t for t in ts if 0.0 < t < 1.0]


def _cubic_bezier_bbox(p1: QPointF, c1: QPointF, c2: QPointF, p2: QPointF) -> QRectF:
    """3차 베지어 곡선의 '타이트한' 경계 사각형(제어점 볼록껍질이 아니라 곡선이 실제로 지나는 범위).
    각 축에서 극값 t + 끝점(0·1)의 곡선 좌표를 모아 min/max."""
    def eval_at(t, a, b, cc, d):
        mt = 1.0 - t
        return (mt * mt * mt * a + 3 * mt * mt * t * b
                + 3 * mt * t * t * cc + t * t * t * d)

    xs = [p1.x(), p2.x()]
    ys = [p1.y(), p2.y()]
    for t in _cubic_axis_extrema(p1.x(), c1.x(), c2.x(), p2.x()):
        xs.append(eval_at(t, p1.x(), c1.x(), c2.x(), p2.x()))
    for t in _cubic_axis_extrema(p1.y(), c1.y(), c2.y(), p2.y()):
        ys.append(eval_at(t, p1.y(), c1.y(), c2.y(), p2.y()))
    return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))


class _ArrowItem(_LabelMixin, _HandleResizeMixin, QGraphicsItem):
    """선 + 끝점 삼각형 화살촉. 머리 방향(head_at_end) 선택 가능."""

    def __init__(self, color: QColor, width: int, head_at_end: bool = True):
        super().__init__()
        self._p1 = QPointF(0, 0)
        self._p2 = QPointF(0, 0)
        self._ctrl1 = None     # 3차 베지어 제어점 2개(None,None=직선). 로컬(=씬) 좌표.
        self._ctrl2 = None
        self._bend_idx = 0     # 드래그 중인 bend 핸들(1·2, 0=없음)
        self._color = QColor(color)
        self._width = width
        self._head_at_end = head_at_end
        self._bind1 = None     # 지속 연결: 끝점0이 묶인 도형(_RectItem/_EllipseItem) or None
        self._bind2 = None     # 끝점1이 묶인 도형 or None
        self._bind1_pt = None  # 그 도형의 '로컬 좌표' 부착점(고정) — 도형 이동/스케일 시 mapToScene로 추종
        self._bind2_pt = None
        # [우리 확장] 라벨 위치 = 곡선 길이 정규화 t(0~1) + 수직 오프셋 off (sarrow와 동일 FigJam/Lucid).
        self._label_t = 0.5
        self._label_off = 0.0
        self._init_resize()
        self._init_label()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    # ---- 라벨: 곡선 위 t 지점 + 수직 오프셋에 완전중앙 배치, paint가 그 자리에 갭(FigJam/Lucid) ----
    def _make_label(self):
        return _ConnectorLabel(self._label_color())   # 드래그로 곡선 위 슬라이드/오프셋

    def _point_at_t_normal(self, t: float):
        """곡선 위 t 지점의 (점, 왼쪽 단위법선). 유한차분 접선으로 법선을 구한다."""
        dt = 1e-3
        a = self._point_at(max(0.0, t - dt))
        b = self._point_at(min(1.0, t + dt))
        tx, ty = b.x() - a.x(), b.y() - a.y()
        L = math.hypot(tx, ty)
        if L < 1e-9:
            return self._point_at(t), QPointF(0.0, -1.0)
        return self._point_at(t), QPointF(-ty / L, tx / L)

    def _label_anchor(self) -> QPointF:
        p, n = self._point_at_t_normal(getattr(self, "_label_t", 0.5))
        off = getattr(self, "_label_off", 0.0)
        return QPointF(p.x() + n.x() * off, p.y() + n.y() * off)

    def _project_to_curve(self, p: QPointF):
        """로컬 점 p를 곡선에 투영해 (t, 부호있는 수직오프셋). 라벨 드래그 재투영용(샘플링 최근접)."""
        N = 120
        best_t, best_d = 0.5, None
        for i in range(N + 1):
            t = i / N
            q = self._point_at(t)
            d = (p.x() - q.x()) ** 2 + (p.y() - q.y()) ** 2
            if best_d is None or d < best_d:
                best_d, best_t = d, t
        pt, n = self._point_at_t_normal(best_t)
        off = (p.x() - pt.x()) * n.x() + (p.y() - pt.y()) * n.y()
        return best_t, off

    def _reproject_label(self, proposed_topleft: QPointF) -> QPointF:
        lbl = self._label
        br = lbl._content_rect()
        center = QPointF(proposed_topleft.x() + br.width() / 2.0,
                         proposed_topleft.y() + br.height() / 2.0)
        self._label_t, self._label_off = self._project_to_curve(center)
        self.update()   # 라벨만 움직여도 부모 화살표 paint(갭)가 새 위치로 다시 그려지게
        a = self._label_anchor()
        return QPointF(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0)

    def _sync_label(self):
        """라벨을 곡선 위 앵커에 완전중앙 배치(선 위) — paint가 그 자리에 갭을 낸다."""
        if not self._label_alive():
            return
        a = self._label_anchor()
        br = self._label._content_rect()
        self._label._syncing = True
        self._label.setPos(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0)
        self._label._syncing = False

    _LABEL_GAP_PAD = 5.0

    def _label_gap_rect(self):
        """라벨이 차지하는 로컬 사각형(+패딩). paint에서 이 안의 선(직선/곡선)을 비운다(FigJam 갭)."""
        if not self.has_label():
            return None
        lbl = self._label
        br = lbl._content_rect()
        pos = lbl.pos()
        pad = self._LABEL_GAP_PAD
        return QRectF(pos.x() + br.x() - pad, pos.y() + br.y() - pad,
                     br.width() + 2 * pad, br.height() + 2 * pad)

    def _label_color(self) -> QColor:
        return QColor(self._color)

    def set_points(self, p1: QPointF, p2: QPointF):
        self.prepareGeometryChange()
        self._p1, self._p2 = p1, p2
        self.update()
        self._sync_label()

    def set_head_at_end(self, value: bool):
        self._head_at_end = value
        self.update()

    def flip_head(self):
        self.set_head_at_end(not self._head_at_end)

    def apply_color(self, color):
        self._color = QColor(color)
        self.update()

    def apply_width(self, width):
        self.prepareGeometryChange()  # boundingRect가 _width에 의존
        self._width = width
        self.update()

    def clone(self):
        c = _ArrowItem(QColor(self._color), self._width, self._head_at_end)
        c.set_points(QPointF(self._p1), QPointF(self._p2))
        if self._ctrl1 is not None:
            c._ctrl1 = QPointF(self._ctrl1)
            c._ctrl2 = QPointF(self._ctrl2)
        c._bind1, c._bind2 = self._bind1, self._bind2  # 지속 연결 바인딩 유지
        c._bind1_pt = None if self._bind1_pt is None else QPointF(self._bind1_pt)
        c._bind2_pt = None if self._bind2_pt is None else QPointF(self._bind2_pt)
        c._label_t, c._label_off = self._label_t, self._label_off   # 라벨 위치(t·off) 유지
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 끝점·제어점을 씬변형(곡선 형태 보존). 바인딩 부착점은
    # 도형쪽 리베이크가 별도로 보정하므로 여기서 건드리지 않는다.
    def _capture_geom_local(self):
        return (QPointF(self._p1), QPointF(self._p2),
                None if self._ctrl1 is None else QPointF(self._ctrl1),
                None if self._ctrl2 is None else QPointF(self._ctrl2))

    def _apply_geom_local(self, g):
        self.prepareGeometryChange()
        self._p1, self._p2 = QPointF(g[0]), QPointF(g[1])
        self._ctrl1 = None if g[2] is None else QPointF(g[2])
        self._ctrl2 = None if g[3] is None else QPointF(g[3])
        self._sync_label()

    def _capture_binds(self):
        return (self._bind1, None if self._bind1_pt is None else QPointF(self._bind1_pt),
                self._bind2, None if self._bind2_pt is None else QPointF(self._bind2_pt))

    def _apply_binds(self, b):
        self._bind1, self._bind1_pt = b[0], (None if b[1] is None else QPointF(b[1]))
        self._bind2, self._bind2_pt = b[2], (None if b[3] is None else QPointF(b[3]))

    def rebake_scene(self, fn):
        self.prepareGeometryChange()
        self._p1 = self._rebake_pt(fn, self._p1)
        self._p2 = self._rebake_pt(fn, self._p2)
        if self._ctrl1 is not None:
            self._ctrl1 = self._rebake_pt(fn, self._ctrl1)
            self._ctrl2 = self._rebake_pt(fn, self._ctrl2)
        self._sync_label()
        self.update()

    # ---- 끝점(양끝 이동) 핸들 -------------------------------------------
    def _uses_endpoints(self):
        return True

    def _connects_to_border(self):
        return True  # 끝점을 뗐다 도형 테두리 근처로 다시 가져가면 재스냅

    def _endpoints(self):
        return [self._p1, self._p2]

    def _set_endpoint(self, idx, p):
        # 끝점을 옮길 때 곡선이면 그 쪽 제어점도 같은 delta로 따라가게 해 곡선 형태·접선을 유지.
        p = QPointF(p)
        if idx == 0:
            if self._ctrl1 is not None:
                self._ctrl1 = self._ctrl1 + (p - self._p1)
            self._p1 = p
        else:
            if self._ctrl2 is not None:
                self._ctrl2 = self._ctrl2 + (p - self._p2)
            self._p2 = p
        self._sync_label()   # 끝점(및 곡선 delta) 이동 시 라벨을 새 중점으로

    def _move_endpoint_with_snap(self, idx, local_p):
        # 끝점을 테두리에 재스냅하면 생성 때처럼 바깥 법선으로 제어점을 다시 잡아 S자(수직 도착/이탈)
        # 복원, 테두리 밖이면 끝점만 이동(수동으로 구부린 곡선은 delta 추종으로 보존).
        # 지속 연결: 스냅되면 그 도형의 '그 지점'(로컬 좌표)에 고정 바인딩,
        # 멀리 끌어 스냅 안 되면 바인딩 해제(unbind). 곡선은 기존 스냅 곡선 로직 유지.
        snapped = self._endpoint_border_snap(local_p)
        if snapped is None:
            self.set_bound(idx, None)
            self._set_endpoint(idx, local_p)
            return
        shape = snapped[2]
        self.set_bound(idx, shape, shape.mapFromScene(self.mapToScene(snapped[0])))
        self._set_endpoint(idx, snapped[0])
        self._recompute_snap_curve(idx, snapped[1])

    # ---- 지속 연결(persistent connection) — 고정 부착점 방식 --------------
    def _bound(self, idx):
        return self._bind1 if idx == 0 else self._bind2

    def _bind_pt(self, idx):
        return self._bind1_pt if idx == 0 else self._bind2_pt

    def set_bound(self, idx, shape, local_pt=None):
        """끝점 idx를 shape에 고정. local_pt는 shape 로컬 좌표의 부착점(None이면 해제)."""
        if idx == 0:
            self._bind1, self._bind1_pt = shape, (None if shape is None else local_pt)
        else:
            self._bind2, self._bind2_pt = shape, (None if shape is None else local_pt)

    def has_binding(self) -> bool:
        return self._bind1 is not None or self._bind2 is not None

    def reroute(self, pin_pred=None) -> bool:
        """바인딩된 끝점을 '도형의 고정 부착점'(로컬→씬)으로 추종. 변경 있었으면 True.
        곡선은 재계산하지 않는다 — _set_endpoint가 제어점을 delta로 끌고 가 사용자가 그린 곡선을 보존.
        pin_pred(idx)가 False면 재고정 안 함(강체). 무변경이면 geometry 미변경으로 되먹임 루프 차단."""
        if not self.has_binding():
            return False
        changed = False
        for idx in (0, 1):
            sh = self._bound(idx)
            pt = self._bind_pt(idx)
            if sh is None or pt is None or sh.scene() is None:
                continue
            if pin_pred is not None and not pin_pred(idx):
                continue
            target = self.mapFromScene(sh.mapToScene(pt))   # 부착점의 현재 씬위치 → 화살표 로컬
            cur = self._endpoints()[idx]
            if abs(target.x() - cur.x()) > 1e-6 or abs(target.y() - cur.y()) > 1e-6:
                self._set_endpoint(idx, target)   # 제어점도 같은 delta로 따라감(곡선 보존)
                changed = True
        if changed:
            self.prepareGeometryChange()
            self.update()
        return changed

    def _scene_dir_to_local(self, d_scene: QPointF) -> QPointF:
        """scene 방향벡터 → 로컬 방향벡터(회전·스케일 반영, 위치 오프셋 제거)."""
        o = self.mapFromScene(QPointF(0.0, 0.0))
        v = self.mapFromScene(d_scene)
        return QPointF(v.x() - o.x(), v.y() - o.y())

    def _endpoint_border_normal(self, idx):
        """끝점 idx가 지금 도형 테두리 근처면 그 바깥 법선(scene), 아니면 None."""
        snapped = self._endpoint_border_snap(self._endpoints()[idx])
        return snapped[1] if snapped is not None else None

    def _recompute_snap_curve(self, dragged_idx, n_dragged_scene):
        # 두 끝의 바깥 법선(scene)을 모아 생성 때(_update_arrow_draw)와 같은 공식으로 제어점 재계산.
        # 드래그한 끝은 방금 스냅한 법선, 반대 끝은 여전히 테두리 위인지 재조회.
        normals = [None, None]
        normals[dragged_idx] = n_dragged_scene
        normals[1 - dragged_idx] = self._endpoint_border_normal(1 - dragged_idx)
        p1, p2 = self._p1, self._p2
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        dist = math.hypot(dx, dy)
        if (normals[0] is None and normals[1] is None) or dist < 8:
            self._ctrl1 = self._ctrl2 = None
            return
        k = max(30.0, min(dist * 0.5, 200.0))
        if normals[0] is not None:
            e1 = self._scene_dir_to_local(normals[0])          # 시작 테두리 이탈 접선(바깥 법선)
        else:
            e1 = QPointF(dx / dist, dy / dist)                 # tip 향해
        if normals[1] is not None:
            e2 = self._scene_dir_to_local(normals[1])          # tip 테두리 도착 접선(바깥 법선)
        else:
            e2 = QPointF(-e1.x(), -e1.y())                     # 시작과 평행(부드러운 S)
        self._ctrl1 = QPointF(p1.x() + e1.x() * k, p1.y() + e1.y() * k)
        self._ctrl2 = QPointF(p2.x() + e2.x() * k, p2.y() + e2.y() * k)

    # ---- 곡선(3차 베지어) 헬퍼 -------------------------------------------
    _BEND_TS = (1.0 / 3.0, 2.0 / 3.0)  # bend 핸들 2개의 곡선 파라미터(t)

    def _point_straight(self, t: float) -> QPointF:
        """직선(p1→p2) 위 파라미터 t 지점."""
        p1, p2 = self._p1, self._p2
        return QPointF(p1.x() + (p2.x() - p1.x()) * t,
                       p1.y() + (p2.y() - p1.y()) * t)

    def _point_at(self, t: float) -> QPointF:
        """곡선(직선이면 직선) 위 파라미터 t 지점."""
        if self._ctrl1 is None:
            return self._point_straight(t)
        p1, p2, c1, c2 = self._p1, self._p2, self._ctrl1, self._ctrl2
        mt = 1.0 - t
        a, b = mt * mt * mt, 3 * mt * mt * t
        c, d = 3 * mt * t * t, t * t * t
        return QPointF(a * p1.x() + b * c1.x() + c * c2.x() + d * p2.x(),
                       a * p1.y() + b * c1.y() + c * c2.y() + d * p2.y())

    def _bend_handle_rect(self, which: int) -> QRectF:
        d = self._handle_px()
        c = self._point_at(self._BEND_TS[which - 1])
        return QRectF(c.x() - d / 2, c.y() - d / 2, d, d)

    def _bend_handle_index_at(self, local_pos) -> int:
        """local 좌표가 어느 bend 핸들 안이면 그 인덱스(1·2), 아니면 0."""
        if not self._bend_active():
            return 0
        for which in (1, 2):
            if self._inflate_to_hit(self._bend_handle_rect(which)).contains(local_pos):
                return which
        return 0

    def _solve_ctrl(self, which: int, target: QPointF):
        """bend 핸들 which(1=t 1/3, 2=t 2/3)가 target을 지나도록 해당 제어점을 역산(다른 제어점 고정).
        B(1/3)=8/27·p1+12/27·c1+6/27·c2+1/27·p2, B(2/3)=1/27·p1+6/27·c1+12/27·c2+8/27·p2 에서 유도."""
        p1, p2 = self._p1, self._p2
        if which == 1:
            c2 = self._ctrl2
            self._ctrl1 = QPointF(
                (27 * target.x() - 8 * p1.x() - 6 * c2.x() - p2.x()) / 12.0,
                (27 * target.y() - 8 * p1.y() - 6 * c2.y() - p2.y()) / 12.0)
        else:
            c1 = self._ctrl1
            self._ctrl2 = QPointF(
                (27 * target.x() - p1.x() - 6 * c1.x() - 8 * p2.x()) / 12.0,
                (27 * target.y() - p1.y() - 6 * c1.y() - 8 * p2.y()) / 12.0)

    def _bend_active(self) -> bool:
        # 선택돼 있으면 어떤 도구에서든 곡선 조절 가능(끝점·회전·크기조절 핸들과 동일 정책).
        return self.isSelected()

    def _tip_and_angle(self):
        """화살촉이 놓이는 tip 점과 그 지점의 진행 방향 각도(paint와 동일 규칙)."""
        tail, tip = (self._p1, self._p2) if self._head_at_end else (self._p2, self._p1)
        if self._ctrl1 is None:
            length = math.hypot(tip.x() - tail.x(), tip.y() - tail.y())
            angle = math.atan2(tip.y() - tail.y(), tip.x() - tail.x()) if length > 1e-6 else 0.0
        else:
            C2, P3 = (self._ctrl2, self._p2) if self._head_at_end else (self._ctrl1, self._p1)
            angle = math.atan2(P3.y() - C2.y(), P3.x() - C2.x())
        return tip, angle

    def _head_size(self) -> float:
        """화살촉 크기 — 선 두께에 비례(얇으면 작게, 굵으면 크게). 최소 7로 아주 얇은
        선에서도 머리가 보이되, 옛 max(14,…) 바닥값이 얇은 선에서 머리를 불비례로
        키우던 문제를 없앤다(두께 휠 조절 시 머리도 같이 줄고 커짐)."""
        return max(self._width * 2.5, 7.0)

    def _head_points(self):
        """화살촉 삼각형 세 꼭짓점(tip + 뒤쪽 두 점)."""
        tip, angle = self._tip_and_angle()
        size = self._head_size()
        a1 = angle + math.radians(150)
        a2 = angle - math.radians(150)
        return [
            QPointF(tip),
            QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1)),
            QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2)),
        ]

    def _content_rect(self) -> QRectF:
        if self._ctrl1 is None:
            r = QRectF(self._p1, self._p2).normalized()
        else:
            # 곡선이 '실제로 지나는' 타이트 경계(제어점 볼록껍질은 S자에서 과도하게 넓어짐).
            r = _cubic_bezier_bbox(self._p1, self._ctrl1, self._ctrl2, self._p2)
        # 선 몸통은 획 반폭만 여유(둥근 캡), 화살촉은 tip에만 튀어나오므로 삼각형 꼭짓점만 합친다
        # (옛 방식은 화살촉 크기를 네 변 모두에 더해 박스가 곡선보다 과하게 넓었음).
        stroke = self._width / 2.0 + 2
        r = r.adjusted(-stroke, -stroke, stroke, stroke)
        hx = [p.x() for p in self._head_points()]
        hy = [p.y() for p in self._head_points()]
        head_r = QRectF(QPointF(min(hx), min(hy)), QPointF(max(hx), max(hy)))
        return r.united(head_r.adjusted(-2, -2, 2, 2))

    def _base_shape(self):
        # 클릭/hit 영역은 '실제 선+화살촉'만 감싼다(박스 전체가 아니라). 그래야 곡선 안쪽
        # 빈/오목 공간이 _is_empty_area에서 '비어 있음'으로 잡혀 거기에 새 주석을 그릴 수 있다.
        body = QPainterPath()
        body.moveTo(self._p1)
        if self._ctrl1 is None:
            body.lineTo(self._p2)
        else:
            body.cubicTo(self._ctrl1, self._ctrl2, self._p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._width, 10) + 4)   # 잡기 쉬운 폭
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        shape = stroker.createStroke(body)
        shape.addPolygon(QPolygonF(self._head_points()))
        if self._bend_active():   # 초록 bend 핸들도 잡을 수 있게(넉넉한 잡기 영역)
            for which in (1, 2):
                shape.addEllipse(self._inflate_to_hit(self._bend_handle_rect(which)))
        return shape

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tail, tip = (self._p1, self._p2) if self._head_at_end else (self._p2, self._p1)
        length = math.hypot(tip.x() - tail.x(), tip.y() - tail.y())
        if self._ctrl1 is None and length < 1:
            return  # 클릭만 한 0길이 직선 화살표는 머리도 그리지 않음(깜빡임 방지)

        size = self._head_size()
        pen = QPen(self._color, self._width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        # [FigJam 갭] 라벨이 있으면 그 사각형만 클립으로 비워 선/곡선이 텍스트를 관통하지 않게 한다.
        # 클립이라 3차 베지어의 매끄러움이 그대로 유지된다(선분 근사 아님). 화살촉은 클립 복원 뒤 그린다.
        gap = self._label_gap_rect()
        if gap is not None:
            painter.save()
            big = self.boundingRect().adjusted(-2000, -2000, 2000, 2000)
            clip = QPainterPath(); clip.addRect(big)
            hole = QPainterPath(); hole.addRect(gap)
            painter.setClipPath(clip.subtracted(hole))

        if self._ctrl1 is None:
            # 직선: 선은 화살촉 밑변까지만 그린다. 짧은 화살표에서 base가 tail 뒤로 넘어가
            # 선이 거꾸로 삐져나오지 않도록 tail~tip 구간 안으로 클램프한다.
            t = max(0.0, 1.0 - (size * 0.85) / length) if length > 1 else 0.0
            base = QPointF(tail.x() + (tip.x() - tail.x()) * t,
                           tail.y() + (tip.y() - tail.y()) * t)
            painter.setPen(pen)
            painter.drawLine(tail, base)
        else:
            # 곡선: p1→c1→c2→p2 3차 베지어. 머리 방향에 맞춰 그리기 순서(P0..P3)를 정렬한다
            # (head_at_end면 p1→p2, 아니면 곡선을 뒤집어 p2→p1 — 제어점도 c2·c1 순서로 뒤집음).
            # tip 쪽을 화살촉 밑변까지 잘라 그린다(안 자르면 굵은 선 끝이 화살촉 밖으로 삐져나옴):
            # tip 접선 크기 |B'(1)|=3·|P3−C2| 로 되돌릴 dt를 근사하고 De Casteljau로 [0,te] 분할.
            if self._head_at_end:
                P0, C1, C2, P3 = self._p1, self._ctrl1, self._ctrl2, self._p2
            else:
                P0, C1, C2, P3 = self._p2, self._ctrl2, self._ctrl1, self._p1
            seg = math.hypot(P3.x() - C2.x(), P3.y() - C2.y())
            dt = min(0.5, (size * 0.85) / (3 * seg)) if seg > 1e-6 else 0.0
            te = 1.0 - dt
            ax = P0.x() + (C1.x() - P0.x()) * te; ay = P0.y() + (C1.y() - P0.y()) * te
            bx = C1.x() + (C2.x() - C1.x()) * te; by = C1.y() + (C2.y() - C1.y()) * te
            cx = C2.x() + (P3.x() - C2.x()) * te; cy = C2.y() + (P3.y() - C2.y()) * te
            dx = ax + (bx - ax) * te; dyv = ay + (by - ay) * te
            ex = bx + (cx - bx) * te; ey = by + (cy - by) * te
            fx = dx + (ex - dx) * te; fy = dyv + (ey - dyv) * te  # 곡선 위 te 지점(화살촉 밑변)
            path = QPainterPath(P0)
            path.cubicTo(QPointF(ax, ay), QPointF(dx, dyv), QPointF(fx, fy))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        if gap is not None:
            painter.restore()   # 화살촉·핸들은 클립 없이 온전히 그린다

        head = QPolygonF(self._head_points())
        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(self._color, 1, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPolygon(head)
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_handle(painter)

    def _paint_selection_outline(self, painter, scale):
        # 선택 표시를 네모가 아니라 '선을 따라가는' 점선으로 — 선+화살촉을 살짝 넓게 감싼 외곽선.
        body = QPainterPath()
        body.moveTo(self._p1)
        if self._ctrl1 is None:
            body.lineTo(self._p2)
        else:
            body.cubicTo(self._ctrl1, self._ctrl2, self._p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(self._width + 8)   # 선보다 살짝 넓게 감싸 점선이 선 양옆을 훑게
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        outline = stroker.createStroke(body)
        outline.addPolygon(QPolygonF(self._head_points()))
        painter.setPen(QPen(QColor(_BLUE), 1.0 / (scale or 1.0), Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(outline.simplified())

    def _paint_handle(self, painter):
        # 크기조절·회전 핸들(믹스인) + 곡선용 bend 핸들 2개(곡선 t=1/3·2/3 지점의 초록 원).
        super()._paint_handle(painter)
        if not self._bend_active():
            return
        s = self._scale_or_1()
        painter.setPen(QPen(QColor("white"), 1.0 / s))
        painter.setBrush(QBrush(QColor(_GREEN)))
        for which in (1, 2):
            painter.drawEllipse(self._bend_handle_rect(which))

    def shape(self):
        base = super().shape()  # 믹스인: base_shape + (선택 시)크기조절·회전 핸들
        if self._bend_active():
            hp = QPainterPath()
            for which in (1, 2):
                hp.addEllipse(self._inflate_to_hit(self._bend_handle_rect(which)))
            return base.united(hp)
        return base

    def boundingRect(self) -> QRectF:
        # 실제로 칠하는 것(선택 외곽선=선두께+8, 초록 bend 핸들)이 _content_rect보다 살짝
        # 바깥으로 나가므로 boundingRect에 모두 포함한다 — 안 그러면 bend 드래그 때 무효화가
        # 누락돼 초록점 궤적 잔상이 남는다(다음 전체 리페인트 전까지).
        r = super().boundingRect()
        if self._bend_active():
            for which in (1, 2):
                r = r.united(self._inflate_to_hit(self._bend_handle_rect(which)))
        pad = 4.0 + 4.0 / self._scale_or_1()   # 외곽선 초과분 + 점선 펜 + 안티에일리어싱 여유
        return r.adjusted(-pad, -pad, pad, pad)

    def mousePressEvent(self, event):
        # bend 핸들을 회전/크기조절보다 먼저 잡는다(곡선 조절점 2개).
        idx = self._bend_handle_index_at(event.pos())
        if idx:
            self._bend_idx = idx
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._bend_idx:
            self.prepareGeometryChange()  # 제어점이 boundingRect를 바꾼다
            m = event.pos()
            if self._ctrl1 is None:
                # 직선 → 곡선: 두 제어점을 직선의 1/3·2/3 지점에서 시작(그 순간엔 여전히 직선 모양).
                self._ctrl1 = self._point_straight(self._BEND_TS[0])
                self._ctrl2 = self._point_straight(self._BEND_TS[1])
            self._solve_ctrl(self._bend_idx, m)
            # 직선-복귀 스냅: 두 제어점이 모두 직선(1/3·2/3) 위(±thresh)면 직선으로 되돌린다.
            thresh = max(6.0, self._width * 2) / self._scale_or_1()
            s1, s2 = self._point_straight(self._BEND_TS[0]), self._point_straight(self._BEND_TS[1])
            if (math.hypot(self._ctrl1.x() - s1.x(), self._ctrl1.y() - s1.y()) < thresh
                    and math.hypot(self._ctrl2.x() - s2.x(), self._ctrl2.y() - s2.y()) < thresh):
                self._ctrl1 = self._ctrl2 = None
            self.update()
            self._sync_label()   # 곡선(중점) 변형 시 라벨 재배치
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._bend_idx:
            self._bend_idx = 0
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# [우리 확장] 직선(꺾은선) 화살표 — Lucid식 직선 커넥터
#   정점 리스트 폴리라인 + 끝 화살촉. 각 정점이 드래그 핸들(끝점 machinery 재사용),
#   선택 후 세그먼트 hover로 정점 추가(Stage A2). 곡선 스플라인은 Stage B에서 얹는다.
# ---------------------------------------------------------------------------
def _point_seg_proj(p: QPointF, a: QPointF, b: QPointF):
    """점 p를 선분 ab에 정사영. (선분 위 최근접점, p까지 거리) 반환(선분 밖이면 끝점으로 클램프)."""
    abx, aby = b.x() - a.x(), b.y() - a.y()
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        t = 0.0
    else:
        t = ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / denom
        t = max(0.0, min(1.0, t))
    proj = QPointF(a.x() + abx * t, a.y() + aby * t)
    return proj, math.hypot(p.x() - proj.x(), p.y() - proj.y())


def _seg_rect_interval(a: QPointF, b: QPointF, rect: QRectF):
    """[우리 확장] 선분 a→b가 rect '내부'를 지나는 파라미터 구간 (t0, t1)를 Liang-Barsky로
    구한다. 교차 없으면 None. 화살표 선을 라벨 자리에서 끊는(FigJam 갭) 데 쓴다."""
    x0, y0 = a.x(), a.y()
    dx, dy = b.x() - x0, b.y() - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - rect.left()), (dx, rect.right() - x0),
                 (-dy, y0 - rect.top()), (dy, rect.bottom() - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return None            # 축에 평행하며 슬래브 밖 → 교차 없음
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return None
                if r > t0:
                    t0 = r
            else:
                if r < t0:
                    return None
                if r < t1:
                    t1 = r
    return None if t0 > t1 else (t0, t1)


class _PolyArrowItem(_LabelMixin, _HandleResizeMixin, QGraphicsItem):
    """정점 리스트로 이루어진 직선 화살표. _endpoints()로 모든 정점을 노출하므로
    _HandleResizeMixin의 끝점 드래그 machinery가 정점 이동을 그대로 처리한다."""

    def __init__(self, color: QColor, width: int, head_at_end: bool = True):
        super().__init__()
        self._pts = [QPointF(0, 0), QPointF(0, 0)]   # 정점 리스트(최소 2)
        self._color = QColor(color)
        self._width = width
        self._head_at_end = head_at_end
        # [A3] 지속 연결 — 양 끝(시작=idx0, 끝=idx last)만 도형에 고정 부착(중간 waypoint 제외).
        # 곡선화살표와 같은 방식(도형 로컬좌표 부착점 + scene.changed 리라우트). waypoint 삽입·삭제로
        # 인덱스가 바뀌므로 절대 idx가 아닌 '시작/끝 역할'로 저장한다.
        self._bind_start = None
        self._bind_end = None
        self._bind_start_pt = None   # 시작이 붙은 도형의 로컬 부착점
        self._bind_end_pt = None
        # [Stage1] Lucid식 직교 자동 라우팅. True면 중간 정점(_pts[1:-1])은 라우터 소유물 —
        # 양끝 부착점에서 매 reroute마다 엘보로 재계산된다. 사용자가 정점 핸들을 드래그하거나
        # waypoint를 추가/삭제하면 False로 내려가 '수동 폴리라인'이 된다(경로 그대로 유지).
        self._auto_route = False
        # [우리 확장] 라벨 위치를 절대좌표가 아니라 경로 길이 정규화 t(0~1)+수직 오프셋 off로 소유.
        # FigJam/Lucid식 — 리라우트돼도 라벨이 비율 자리를 지킨다(절대좌표면 재라우팅 때 튐).
        # 드래그하면 _reproject_label이 t·off를 갱신하고, paint가 그 자리에 선 갭을 낸다.
        self._label_t = 0.5
        self._label_off = 0.0
        self._init_resize()
        self._init_label()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    # ---- 정점 = 끝점 핸들(재사용) --------------------------------------
    def _uses_endpoints(self):
        return True

    _ROUTE_CLEARANCE = 12.0   # [Stage2] 라우팅이 장애물에서 유지할 여유(scene 단위)
    _ARROW_CROSS_PENALTY = 200.0   # [Stage3] 다른 화살표를 가로지를 때 A* 간선에 더할 soft 벌점
    _ALIGN_TOL = 8.0   # [Stage4] 근접정렬 흡수 임계(px) — 이하 어긋남만 흡수, 의도적 오프셋은 보존

    # ---- [A3] 지속 연결(도형 테두리 부착) — 곡선화살표 인프라 재사용 --------
    def _connects_to_border(self):
        return True   # 끝점을 도형 테두리 근처로 가져가면 재스냅·바인딩

    def _bound(self, idx):
        if idx == 0:
            return self._bind_start
        if idx == len(self._pts) - 1:
            return self._bind_end
        return None

    def _bind_pt(self, idx):
        if idx == 0:
            return self._bind_start_pt
        if idx == len(self._pts) - 1:
            return self._bind_end_pt
        return None

    def set_bound(self, idx, shape, local_pt=None):
        """끝점(시작/끝)만 shape에 고정. 중간 정점 idx는 무시."""
        if idx == 0:
            self._bind_start, self._bind_start_pt = shape, (None if shape is None else local_pt)
        elif idx == len(self._pts) - 1:
            self._bind_end, self._bind_end_pt = shape, (None if shape is None else local_pt)

    def has_binding(self) -> bool:
        return self._bind_start is not None or self._bind_end is not None

    def _move_endpoint_with_snap(self, idx, local_p):
        # 양 끝점만 테두리에 스냅·바인딩(중간 waypoint는 자유 이동). 멀리 끌면 unbind.
        is_end = idx == 0 or idx == len(self._pts) - 1
        snapped = self._endpoint_border_snap(local_p) if is_end else None
        if snapped is None:
            if is_end:
                self.set_bound(idx, None)
            self._set_endpoint(idx, local_p)
            return
        shape = snapped[2]
        self.set_bound(idx, shape, shape.mapFromScene(self.mapToScene(snapped[0])))
        self._set_endpoint(idx, snapped[0])

    def reroute(self, pin_pred=None) -> bool:
        """바인딩된 끝(시작·끝)을 도형의 고정 부착점(로컬→씬)으로 추종. 변경 있으면 True.
        pin_pred(idx)=False면 재고정 안 함(강체). 무변경이면 되먹임 루프 차단.
        [Stage1] 자동 라우팅(_auto_route)이고 양끝 모두 바인딩이면 끝점 추종 후 직교 엘보를 재계산."""
        if not self.has_binding():
            return False
        changed = False
        for idx in (0, len(self._pts) - 1):
            sh = self._bound(idx)
            pt = self._bind_pt(idx)
            if sh is None or pt is None or sh.scene() is None:
                continue
            if pin_pred is not None and not pin_pred(idx):
                continue
            target = self.mapFromScene(sh.mapToScene(pt))
            cur = self._pts[idx]
            if abs(target.x() - cur.x()) > 1e-6 or abs(target.y() - cur.y()) > 1e-6:
                self._set_endpoint(idx, target)
                changed = True
        if self._auto_route and self._bind_start is not None and self._bind_end is not None:
            if self.build_elbow():
                changed = True
        if changed:
            self.prepareGeometryChange()
            self.update()
        return changed

    def _bound_normal_scene(self, idx):
        """바인딩된 끝(idx=0 시작 / last 끝)의 도형 테두리 '바깥 단위 법선'(scene), 없으면 None.
        부착점이 정확히 테두리 위이므로 _nearest_border가 그 점의 법선을 돌려준다."""
        sh = self._bound(idx)
        pt = self._bind_pt(idx)
        if sh is None or pt is None or sh.scene() is None:
            return None
        try:
            _, n = _nearest_border(sh, sh.mapToScene(pt))
        except Exception:
            return None
        return n

    def _absorb_near_alignment(self) -> bool:
        """[Stage4] 양끝의 교차축 어긋남이 _ALIGN_TOL 이하면 부착점을 공통 축으로 스냅해 직교 라우터가
        넣는 미세 계단([A]백엣지·[B]수렴부·decision 연결)을 직선으로 붕괴시킨다. 실제로 옮겼으면 True.
        · 교차축 = 두 끝점의 '지배적 분리축'의 수직(가로연결 |dx|≥|dy|→Y정렬 / 세로연결→X정렬). 법선이
          아니라 분리축으로 판정 — 마름모 꼭짓점의 대각 법선에 안 속는다(직전 실조건서 6px 계단 놓친 갭).
        · 정렬 목표는 후보(상대 끝점 좌표 → 자기 좌표 → 중점) 중 두 부착점이 모두 도형 '테두리 위'에
          남는 첫 값 — 꼭짓점은 축 밖으로 못 나가 자연히 '움직일 수 있는 쪽(박스 변)'만 옮긴다(폭 다른
          E-E는 양쪽 다 테두리 밖이라 미적용 → build에서 폭 통일로 처리).
        · 큰(의도적) 어긋남은 임계 밖이라 미변경, 스냅 후 어긋남=0이라 멱등(되먹임 없음)."""
        end_idx = len(self._pts) - 1
        s = self.mapToScene(self._pts[0])
        e = self.mapToScene(self._pts[end_idx])
        horizontal = abs(e.x() - s.x()) >= abs(e.y() - s.y())
        c0 = s.y() if horizontal else s.x()
        c1 = e.y() if horizontal else e.x()
        if abs(c0 - c1) <= 1e-6 or abs(c0 - c1) > self._ALIGN_TOL:
            return False
        sh0, sh1 = self._bound(0), self._bound(end_idx)

        def on_border(sh, sp):   # 이동한 부착점이 도형 테두리 위에 남는가(꼭짓점 이탈 방지)
            if sh is None or sh.scene() is None:
                return True
            try:
                bp, _ = _nearest_border(sh, sp)
            except Exception:
                return False
            return (bp - sp).manhattanLength() <= 0.5

        def at(p, target):
            return QPointF(p.x(), target) if horizontal else QPointF(target, p.y())

        for target in (c1, c0, (c0 + c1) / 2.0):
            p0, p1 = at(s, target), at(e, target)
            if on_border(sh0, p0) and on_border(sh1, p1):
                for idx, sh, np in ((0, sh0, p0), (end_idx, sh1, p1)):
                    if sh is not None:
                        self.set_bound(idx, sh, sh.mapFromScene(np))
                    self._set_endpoint(idx, self.mapFromScene(np))
                return True
        return False

    def build_elbow(self) -> bool:
        """[Stage1] 현재 양끝점 + 부착 변 법선으로 직교 엘보를 계산해 _pts를 교체. 변경 있으면 True.
        _pts[0]/_pts[-1](끝점)은 유지하고 중간 정점만 라우터가 생성한다."""
        if self._bind_start is None or self._bind_end is None:
            return False
        end_idx = len(self._pts) - 1
        s = self.mapToScene(self._pts[0])
        e = self.mapToScene(self._pts[end_idx])
        if abs(s.x() - e.x()) < 1e-6 and abs(s.y() - e.y()) < 1e-6:
            return False
        ns = self._bound_normal_scene(0)
        ne = self._bound_normal_scene(end_idx)
        # [Stage4] 라우팅 전 근접정렬 흡수 — 미세 어긋남(≤_ALIGN_TOL)을 직선으로 붕괴. 옮겼으면 s·e 갱신.
        if self._absorb_near_alignment():
            s = self.mapToScene(self._pts[0])
            e = self.mapToScene(self._pts[end_idx])
        # [Stage2] 장애물(양끝 바인딩 도형 제외)을 피하는 직교 경로. 장애물이 없거나 Stage1
        # 엘보가 이미 안전하면 Stage1과 동일 결과 → 아래 무변경 가드가 되먹임 루프를 끊는다.
        mids = _route_ortho(s, e, ns, ne, self._obstacle_rects(), self._ROUTE_CLEARANCE,
                            avoid_segs=self._obstacle_arrow_segs(),
                            cross_penalty=self._ARROW_CROSS_PENALTY)
        new_scene = _dedup_pts([s] + mids + [e])
        new_local = [self.mapFromScene(p) for p in new_scene]
        if len(new_local) == len(self._pts) and all(
                abs(a.x() - b.x()) <= 1e-6 and abs(a.y() - b.y()) <= 1e-6
                for a, b in zip(new_local, self._pts)):
            return False   # 동일 → 되먹임 루프 차단
        self.prepareGeometryChange()
        self._pts = new_local
        self.update()
        self._sync_label()
        return True

    def _obstacle_rects(self):
        """[Stage2] 라우팅이 피해야 할 장애물 사각형(scene, 축정렬 bbox). 양끝 바인딩 도형
        (출발/도착)은 제외. 원은 외접 사각형으로 근사(보수적). scene이 없으면 빈 리스트."""
        sc = self.scene()
        if sc is None:
            return []
        out = []
        for it in sc.items():
            if it is self._bind_start or it is self._bind_end:
                continue
            if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem)):
                out.append(it.mapRectToScene(it.rect()))
        return out

    def _obstacle_arrow_segs(self):
        """[Stage3] soft 회피용 — 다른 화살표(self 제외)의 렌더 폴리라인을 씬좌표 선분 리스트로.
        _PolyArrowItem=엘보 전체 정점, _ArrowItem=양끝 코드(베지어는 직선 근사). 장애물이 아니라
        비용에만 반영하므로 self의 현재 경로는 넣지 않는다(되먹임 방지). scene 없으면 빈 리스트."""
        sc = self.scene()
        if sc is None:
            return []
        segs = []
        for it in sc.items():
            if it is self or not isinstance(it, (_ArrowItem, _PolyArrowItem)):
                continue
            pts = [it.mapToScene(p) for p in it._endpoints()]
            for i in range(len(pts) - 1):
                segs.append((pts[i], pts[i + 1]))
        return segs

    def _on_endpoint_drag_start(self, idx):
        # [Stage1] 정점 핸들을 손으로 잡는 순간 자동 라우팅 해제 — 이후 경로는 사용자 소유(수동).
        self._auto_route = False

    def _endpoints(self):
        return self._pts

    def _set_endpoint(self, idx, p):
        self.prepareGeometryChange()
        self._pts[idx] = QPointF(p)
        self.update()
        self._sync_label()

    def set_points(self, p1: QPointF, p2: QPointF):
        """그리기용 — 2정점으로 초기화."""
        self.prepareGeometryChange()
        self._pts = [QPointF(p1), QPointF(p2)]
        self.update()
        self._sync_label()

    def insert_vertex(self, seg_idx: int, p: QPointF):
        """세그먼트 seg_idx(정점 seg_idx~seg_idx+1 사이)에 정점 p 삽입(waypoint 추가)."""
        self._auto_route = False   # [Stage1] waypoint 추가 = 수동 편집 → 자동 라우팅 해제
        self.prepareGeometryChange()
        self._pts.insert(seg_idx + 1, QPointF(p))
        self.update()
        self._sync_label()

    def _nearest_segment(self, local_p: QPointF):
        """local_p에 가장 가까운 세그먼트 (seg_idx, 선분 위 최근접점(local), 거리) 반환."""
        best = None
        for i in range(len(self._pts) - 1):
            proj, d = _point_seg_proj(local_p, self._pts[i], self._pts[i + 1])
            if best is None or d < best[2]:
                best = (i, proj, d)
        return best

    def remove_vertex(self, idx: int) -> bool:
        """정점 삭제(최소 2정점은 유지). 삭제했으면 True."""
        if len(self._pts) <= 2:
            return False
        self._auto_route = False   # [Stage1] 정점 삭제 = 수동 편집 → 자동 라우팅 해제
        self.prepareGeometryChange()
        del self._pts[idx]
        self.update()
        self._sync_label()
        return True

    # ---- 색/두께 -------------------------------------------------------
    def apply_color(self, color):
        self._color = QColor(color)
        self.update()

    def apply_width(self, width):
        self.prepareGeometryChange()
        self._width = width
        self.update()

    def clone(self):
        c = _PolyArrowItem(QColor(self._color), self._width, self._head_at_end)
        c._pts = [QPointF(p) for p in self._pts]
        c._bind_start, c._bind_end = self._bind_start, self._bind_end   # [A3] 지속 연결 유지
        c._bind_start_pt = None if self._bind_start_pt is None else QPointF(self._bind_start_pt)
        c._bind_end_pt = None if self._bind_end_pt is None else QPointF(self._bind_end_pt)
        c._auto_route = self._auto_route   # [Stage1] 자동 라우팅 상태 유지
        c._label_t, c._label_off = self._label_t, self._label_off   # 라벨 위치(t·off) 유지
        return self._copy_common_to(c)

    # [Stage2] 기하 리베이크 — 모든 정점을 씬변형. 왜곡·미러는 자동 엘보가 되돌리지 않게
    # 수동 폴리라인으로 전환(_auto_route=False). undo 스냅샷은 원래 _auto_route를 복원한다.
    def _capture_geom_local(self):
        return ([QPointF(p) for p in self._pts], self._auto_route)

    def _apply_geom_local(self, g):
        self.prepareGeometryChange()
        self._pts = [QPointF(p) for p in g[0]]
        self._auto_route = g[1]
        self._sync_label()

    def _capture_binds(self):
        return (self._bind_start,
                None if self._bind_start_pt is None else QPointF(self._bind_start_pt),
                self._bind_end,
                None if self._bind_end_pt is None else QPointF(self._bind_end_pt))

    def _apply_binds(self, b):
        self._bind_start, self._bind_start_pt = b[0], (None if b[1] is None else QPointF(b[1]))
        self._bind_end, self._bind_end_pt = b[2], (None if b[3] is None else QPointF(b[3]))

    def rebake_scene(self, fn):
        self.prepareGeometryChange()
        self._pts = [self._rebake_pt(fn, p) for p in self._pts]
        self._auto_route = False
        self._sync_label()
        self.update()

    # ---- 화살촉(끝 세그먼트 방향) --------------------------------------
    def _tip_and_angle(self):
        if self._head_at_end:
            tip, tail = self._pts[-1], self._pts[-2]
        else:
            tip, tail = self._pts[0], self._pts[1]
        ang = (math.atan2(tip.y() - tail.y(), tip.x() - tail.x())
               if tip != tail else 0.0)
        return tip, ang

    def _head_size(self) -> float:
        return max(self._width * 2.5, 7.0)

    def _head_points(self):
        tip, ang = self._tip_and_angle()
        size = self._head_size()
        a1, a2 = ang + math.radians(150), ang - math.radians(150)
        return [
            QPointF(tip),
            QPointF(tip.x() + size * math.cos(a1), tip.y() + size * math.sin(a1)),
            QPointF(tip.x() + size * math.cos(a2), tip.y() + size * math.sin(a2)),
        ]

    def _polyline_path(self) -> QPainterPath:
        path = QPainterPath(self._pts[0])
        for pt in self._pts[1:]:
            path.lineTo(pt)
        return path

    _LABEL_GAP_PAD = 5.0   # [우리 확장] 라벨 사각형 둘레로 선을 끊을 때의 여유(px)

    def _label_gap_rect(self):
        """[우리 확장] 라벨(있으면)이 차지하는 로컬 사각형(+패딩). 이 안의 선을 지워 텍스트를 앉힌다.
        라벨이 선에서 멀리 떨어지면(오프셋 드래그) 이 사각형이 선과 안 겹쳐 자연히 갭이 사라진다."""
        if not self.has_label():
            return None
        lbl = self._label
        br = lbl._content_rect()
        pos = lbl.pos()
        pad = self._LABEL_GAP_PAD
        return QRectF(pos.x() + br.x() - pad, pos.y() + br.y() - pad,
                     br.width() + 2 * pad, br.height() + 2 * pad)

    def _visible_polyline_path(self) -> QPainterPath:
        """[우리 확장 · FigJam 갭] 라벨 사각형과 겹치는 폴리라인 구간만 빼고 그린 경로.
        히트테스트(_base_shape)·선택외곽선·직렬화는 전체 폴리라인을 그대로 쓴다 — 시각 갭만."""
        rect = self._label_gap_rect()
        if rect is None:
            return self._polyline_path()
        path = QPainterPath()
        for a, b in zip(self._pts[:-1], self._pts[1:]):
            inside = _seg_rect_interval(a, b, rect)
            if inside is None:
                path.moveTo(a)
                path.lineTo(b)
                continue
            i0, i1 = inside
            dx, dy = b.x() - a.x(), b.y() - a.y()
            if i0 > 1e-6:
                path.moveTo(a)
                path.lineTo(QPointF(a.x() + dx * i0, a.y() + dy * i0))
            if i1 < 1.0 - 1e-6:
                path.moveTo(QPointF(a.x() + dx * i1, a.y() + dy * i1))
                path.lineTo(b)
        return path

    # ---- 라벨 앵커 = 경로 위 t(0~1) 지점 + 수직 오프셋 (FigJam/Lucid) ----
    def _make_label(self):
        return _ConnectorLabel(self._label_color())   # 드래그로 경로 위 슬라이드/오프셋

    def _label_color(self) -> QColor:
        return QColor(self._color)

    def _point_at_t(self, t: float):
        """경로 길이 정규화 파라미터 t(0~1) 지점의 (점, 왼쪽 단위법선). 라벨 앵커·오프셋에 쓴다."""
        segs, total = [], 0.0
        for a, b in zip(self._pts[:-1], self._pts[1:]):
            d = math.hypot(b.x() - a.x(), b.y() - a.y())
            segs.append((a, b, d))
            total += d
        if total < 1e-9:
            return QPointF(self._pts[0]), QPointF(0.0, -1.0)
        target, run = max(0.0, min(1.0, t)) * total, 0.0
        for i, (a, b, d) in enumerate(segs):
            if run + d >= target or i == len(segs) - 1:   # 마지막 세그먼트면 t=1 끝점도 여기서 잡음
                tt = (target - run) / d if d > 1e-9 else 0.0
                px, py = a.x() + (b.x() - a.x()) * tt, a.y() + (b.y() - a.y()) * tt
                if d > 1e-9:
                    n = QPointF(-(b.y() - a.y()) / d, (b.x() - a.x()) / d)   # 왼쪽 단위법선
                else:
                    n = QPointF(0.0, -1.0)
                return QPointF(px, py), n
            run += d
        return QPointF(self._pts[-1]), QPointF(0.0, -1.0)

    def _label_anchor(self) -> QPointF:
        p, n = self._point_at_t(getattr(self, "_label_t", 0.5))
        off = getattr(self, "_label_off", 0.0)
        return QPointF(p.x() + n.x() * off, p.y() + n.y() * off)

    def _project_to_path(self, p: QPointF):
        """로컬 점 p를 폴리라인에 투영해 (t, 부호있는 수직오프셋)을 반환. 라벨 드래그 재투영용.
        오프셋 부호는 _point_at_t의 왼쪽 법선과 같은 방향(양수=선 왼쪽)."""
        segs, total = [], 0.0
        for a, b in zip(self._pts[:-1], self._pts[1:]):
            d = math.hypot(b.x() - a.x(), b.y() - a.y())
            segs.append((a, b, d))
            total += d
        if total < 1e-9:
            return 0.5, 0.0
        best = None   # (거리, 경로누적길이, 부호오프셋)
        run = 0.0
        for a, b, d in segs:
            if d < 1e-9:
                continue
            dx, dy = b.x() - a.x(), b.y() - a.y()
            tt = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / (d * d)))
            projx, projy = a.x() + dx * tt, a.y() + dy * tt
            dist = math.hypot(p.x() - projx, p.y() - projy)
            if best is None or dist < best[0]:
                off = (-dy * (p.x() - projx) + dx * (p.y() - projy)) / d   # 왼쪽 법선 성분
                best = (dist, run + d * tt, off)
            run += d
        return best[1] / total, best[2]

    def _reproject_label(self, proposed_topleft: QPointF) -> QPointF:
        """[우리 확장] 라벨 자유 드래그(itemChange가 넘긴 top-left 후보)를 경로 위로 재투영해
        t·off를 갱신하고, 그 t·off에 대응하는 '구속된' top-left를 돌려준다(FigJam 슬라이드+Lucid 오프셋)."""
        lbl = self._label
        br = lbl._content_rect()
        center = QPointF(proposed_topleft.x() + br.width() / 2.0,
                         proposed_topleft.y() + br.height() / 2.0)
        self._label_t, self._label_off = self._project_to_path(center)
        self.update()   # 라벨(자식)만 움직여도 부모 화살표 paint(갭)가 새 위치로 다시 그려지게
        a = self._label_anchor()
        return QPointF(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0)

    def _sync_label(self):
        """[우리 확장] 라벨을 앵커에 '완전 중앙'(x·y)으로 놓는다 — 선·베지어의 '중점 위쪽'과 달리
        선 위에 앉히고 paint가 그 자리에 갭을 낸다. _syncing 가드로 setPos→itemChange 되먹임 차단."""
        if not self._label_alive():
            return
        a = self._label_anchor()
        br = self._label._content_rect()
        self._label._syncing = True
        self._label.setPos(a.x() - br.width() / 2.0, a.y() - br.height() / 2.0)
        self._label._syncing = False

    # ---- 경계/외형 -----------------------------------------------------
    def _content_rect(self) -> QRectF:
        xs = [p.x() for p in self._pts]
        ys = [p.y() for p in self._pts]
        r = QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))
        stroke = self._width / 2.0 + 2
        r = r.adjusted(-stroke, -stroke, stroke, stroke)
        hp = self._head_points()
        hx = [p.x() for p in hp]
        hy = [p.y() for p in hp]
        head_r = QRectF(QPointF(min(hx), min(hy)), QPointF(max(hx), max(hy)))
        return r.united(head_r.adjusted(-2, -2, 2, 2))

    def boundingRect(self) -> QRectF:
        r = self._content_rect()
        for i in range(len(self._pts)):
            r = r.united(self._inflate_to_hit(self._endpoint_rect(i)))
        pad = 4.0 / self._scale_or_1()
        return r.adjusted(-pad, -pad, pad, pad)

    def _base_shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._width, 10) + 4)   # 잡기 쉬운 폭
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        shape = stroker.createStroke(self._polyline_path())
        shape.addPolygon(QPolygonF(self._head_points()))
        return shape

    def _paint_selection_outline(self, painter, scale):
        stroker = QPainterPathStroker()
        stroker.setWidth(self._width + 8)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        outline = stroker.createStroke(self._polyline_path())
        painter.setPen(QPen(QColor(_BLUE), 1.0 / (scale or 1.0), Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(outline.simplified())

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, self._width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._visible_polyline_path())   # [FigJam 갭] 라벨 자리에서 선 끊음
        painter.setPen(QPen(self._color, 1))
        painter.setBrush(QBrush(self._color))
        painter.drawPolygon(QPolygonF(self._head_points()))
        if self.isSelected():
            self._paint_selection_outline(painter, self._scale_or_1())
        self._paint_endpoint_handles(painter)


class _BadgeItem(_HandleResizeMixin, QGraphicsItem):
    """원 배경 + 중앙 번호. 클릭 위치(pos)에 배치."""

    _R = 15

    def __init__(self, number: int, color: QColor):
        super().__init__()
        self._number = number
        self._color = QColor(color)
        self._init_resize()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    def _content_rect(self) -> QRectF:
        r = self._R + 2
        return QRectF(-r, -r, 2 * r, 2 * r)

    def _base_shape(self):
        p = QPainterPath()
        p.addEllipse(self._content_rect())
        return p

    def apply_color(self, color):
        self._color = QColor(color)
        self.update()

    def clone(self):
        c = _BadgeItem(self._number, QColor(self._color))
        return self._copy_common_to(c)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawEllipse(QPointF(0, 0), self._R, self._R)
        f = QFont()
        f.setBold(True)
        f.setPointSize(12)
        painter.setFont(f)
        painter.setPen(QPen(QColor("white")))
        painter.drawText(QRectF(-self._R, -self._R, 2 * self._R, 2 * self._R),
                         Qt.AlignmentFlag.AlignCenter, str(self._number))
        if self.isSelected():
            _draw_selection_box(painter, self._content_rect(), self._scale_or_1())
        self._paint_handle(painter)


class _TextItem(_HandleResizeMixin, QGraphicsTextItem):
    """편집 종료(focus out) 시 이동/크기조절 가능해지고, 더블클릭으로 다시 편집."""

    def __init__(self, color: QColor):
        super().__init__("")
        self._init_resize()
        self._bg = None  # None=투명 / QColor=배경 채움
        self.setDefaultTextColor(QColor(color))
        f = self.font()
        f.setPointSize(16)
        self.setFont(f)
        # [우리 확장] 사용자가 의도한 '기준' 폰트 크기. 중앙 라벨은 도형에 맞춰 이보다 작게 축소해
        # 렌더할 수 있으나(_fit_label_to_shape), 저장·재적합의 기준은 항상 이 값이다(축소값 아님).
        self._base_pt = 16
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    def apply_color(self, color):
        self.setDefaultTextColor(QColor(color))

    def apply_font_size(self, size):
        self._base_pt = int(size)   # 기준 크기 갱신(중앙 라벨 축소의 상한)
        f = self.font()
        f.setPointSize(int(size))
        self.setFont(f)

    def set_bg(self, color):
        # color: QColor 또는 None(투명). 둥근 사각 배경으로 자막/스티커 느낌.
        self._bg = QColor(color) if color is not None else None
        self.update()

    def clone(self):
        c = _TextItem(self.defaultTextColor())
        c.setFont(QFont(self.font()))
        c.setPlainText(self.toPlainText())
        c.set_bg(self._bg)
        return self._copy_common_to(c)

    def boundingRect(self):
        # 편집 중(텍스트 입력)엔 회전 핸들 예약(우상단 여백)을 빼 Qt 편집 프레임이 글자에
        # 딱 맞게 한다 — 안 그러면 핸들 자리만큼 점선 프레임이 위·우로 크게 벌어진다.
        if self.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction:
            return self._content_rect()
        return super().boundingRect()

    def setTextInteractionFlags(self, flags):
        # 편집 진입/종료로 boundingRect가 바뀌므로 경계 캐시 갱신(프레임 잔상 방지).
        self.prepareGeometryChange()
        super().setTextInteractionFlags(flags)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        super().focusOutEvent(event)
        # 연속 텍스트 모드에서 빈 클릭으로 생긴 빈 텍스트는 정리(undo는 scene None 가드로 무해).
        if not self.toPlainText().strip():
            QTimer.singleShot(0, self._discard_if_empty)
        else:
            self.setSelected(False)  # 완료(ESC/Ctrl+Enter) 후 점선 없이 글자만 — 재편집은 V 도구로

    def _discard_if_empty(self):
        if not self.toPlainText().strip() and self.scene() is not None:
            self.scene().removeItem(self)

    def mouseDoubleClickEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus()
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        # Enter = 편집 종료(ESC와 동일), Shift+Enter = 줄바꿈. clearFocus → focusOut에서 정리.
        # (Ctrl+Enter도 종료로 유지 — 하위 호환.)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)  # 줄바꿈 삽입
                return
            self.clearFocus()  # Enter / Ctrl+Enter = 완료
            return
        super().keyPressEvent(event)

    def paint(self, painter, option, widget=None):
        if self._bg is not None:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._bg))
            painter.drawRoundedRect(self._content_rect().adjusted(1, 1, -1, -1), 4, 4)
        self._paint_base_no_select(painter, option, widget)
        self._paint_handle(painter)


class _ConnectorLabel(_TextItem):
    """[우리 확장] 화살표(sarrow)에 붙는 라벨 — 드래그하면 부모 폴리라인을 따라 슬라이드하고
    (FigJam), 선 옆으로 당기면 수직 오프셋으로 뜬다(Lucid). 위치는 부모(_PolyArrowItem)가
    t·off로 소유하며, itemChange가 Qt 기본 자유 이동을 경로 위로 재투영해 구속한다.
    _syncing 플래그가 켜진 동안(_sync_label의 setPos)엔 재투영을 건너뛴다(되먹임 차단)."""

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
                and not getattr(self, "_syncing", False)):
            parent = self.parentItem()
            if parent is not None and hasattr(parent, "_reproject_label"):
                return parent._reproject_label(value)
        return super().itemChange(change, value)


# ---------------------------------------------------------------------------
# 스포이드 루페 — 화면 픽셀 색 미리보기 (입력 투과)
# ---------------------------------------------------------------------------

class _ColorLoupe(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._color = QColor("black")
        self._hex = ""
        self.setFixedSize(104, 74)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self._hex = self._color.name().upper()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(_BG))
        p.setPen(QPen(QColor(_SURFACE2), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.fillRect(8, 8, self.width() - 16, 38, self._color)
        p.setPen(QPen(QColor(_SURFACE2), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(8, 8, self.width() - 16, 38)
        p.setPen(QColor(_TEXT))
        p.drawText(QRectF(0, 48, self.width(), 22),
                   Qt.AlignmentFlag.AlignCenter, self._hex)


# ---------------------------------------------------------------------------
# 크기 스테퍼 — 도구별 floating(글자/번호 크기), 휠/▾▴ 클릭으로 조절
# ---------------------------------------------------------------------------

class _SizeStepper(QWidget):
    changed = pyqtSignal(int)

    _REPEAT_DELAY = 400   # 길게 누르기 시작 후 첫 반복까지(ms)
    _REPEAT_RATE = 60     # 이후 반복 간격(ms)

    def __init__(self, value: int, vmin: int, vmax: int, suffix: str = "", tooltip: str = ""):
        super().__init__()
        self._min, self._max = vmin, vmax
        self._s = value
        self._suffix = suffix
        self.setFixedSize(64, 24)
        self.setToolTip(tooltip or "크기 — 휠 또는 ▾ ▴ (길게 누르면 연속)")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # ▾/▴ 길게 누르면 연속 증감 — 누르고 있는 동안 반복
        self._repeat_dir = 0
        self._repeat_timer = QTimer(self)
        self._repeat_timer.timeout.connect(self._repeat_tick)

    def set_value(self, value: int):
        self._s = max(self._min, min(int(value), self._max))
        self.update()

    def _bump(self, delta: int):
        self.set_value(self._s + delta)
        self.changed.emit(self._s)

    def wheelEvent(self, event):
        if event.angleDelta().y() == 0:
            return
        self._bump(1 if event.angleDelta().y() > 0 else -1)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        if x < self.width() * 0.28:
            self._repeat_dir = -1
        elif x > self.width() * 0.72:
            self._repeat_dir = 1
        else:
            return
        self._bump(self._repeat_dir)                 # 즉시 1단계
        self._repeat_timer.start(self._REPEAT_DELAY)  # 누르고 있으면 이후 연속

    def _repeat_tick(self):
        self._bump(self._repeat_dir)
        if self._repeat_timer.interval() != self._REPEAT_RATE:
            self._repeat_timer.setInterval(self._REPEAT_RATE)  # 첫 반복 후 가속

    def mouseReleaseEvent(self, event):
        self._repeat_timer.stop()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(_SURFACE0))
        p.setPen(QPen(QColor(_BORDER), 1))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        f = QFont()
        f.setPointSize(10)
        p.setFont(f)
        p.setPen(QColor(_SUBTEXT))
        p.drawText(QRectF(2, 0, 16, self.height()), Qt.AlignmentFlag.AlignCenter, "▾")
        p.drawText(QRectF(self.width() - 18, 0, 16, self.height()),
                   Qt.AlignmentFlag.AlignCenter, "▴")
        p.setPen(QColor(_TEXT))
        p.drawText(QRectF(16, 0, self.width() - 32, self.height()),
                   Qt.AlignmentFlag.AlignCenter, f"{self._s}{self._suffix}")


# ---------------------------------------------------------------------------
# 그래픽스 뷰 — 그리기 인터랙션 + 도구 단축키 (Shift 제약)
# ---------------------------------------------------------------------------

def _rect_nearest(r, p):
    """로컬 사각형 r 둘레에서 점 p 최근접점 + 바깥 단위 법선(로컬)."""
    left, right, top, bottom = r.left(), r.right(), r.top(), r.bottom()
    if left <= p.x() <= right and top <= p.y() <= bottom:
        # 내부 → 가장 가까운 변으로 투영
        dl, dr, dt, db = p.x() - left, right - p.x(), p.y() - top, bottom - p.y()
        m = min(dl, dr, dt, db)
        if m == dl:
            return QPointF(left, p.y()), QPointF(-1.0, 0.0)
        if m == dr:
            return QPointF(right, p.y()), QPointF(1.0, 0.0)
        if m == dt:
            return QPointF(p.x(), top), QPointF(0.0, -1.0)
        return QPointF(p.x(), bottom), QPointF(0.0, 1.0)
    # 외부 → 채운 사각형으로 클램프한 점이 최근접(모서리 밖이면 대각 법선)
    qx = min(max(p.x(), left), right)
    qy = min(max(p.y(), top), bottom)
    nx = -1.0 if (qx == left and p.x() < left) else (1.0 if (qx == right and p.x() > right) else 0.0)
    ny = -1.0 if (qy == top and p.y() < top) else (1.0 if (qy == bottom and p.y() > bottom) else 0.0)
    if nx == 0.0 and ny == 0.0:
        ny = -1.0  # 안전망(도달 안 함)
    L = math.hypot(nx, ny) or 1.0
    return QPointF(qx, qy), QPointF(nx / L, ny / L)


def _ellipse_nearest(r, p):
    """로컬 타원(사각형 r에 내접) 둘레에서 점 p 최근접점 + 바깥 단위 법선(로컬).
    파라미터 각 t에 대한 뉴턴 반복(초기값=방사각)으로 근사 — 테두리 근처에서 빠르게 수렴."""
    cx, cy = r.center().x(), r.center().y()
    a, b = r.width() / 2.0, r.height() / 2.0
    ux, uy = p.x() - cx, p.y() - cy
    if a < 1e-6 or b < 1e-6:
        return QPointF(cx, cy), QPointF(0.0, -1.0)
    t = math.atan2(a * uy, b * ux)
    for _ in range(4):
        ct, st = math.cos(t), math.sin(t)
        x, y = a * ct, b * st
        # f(t) = d/dt (½|(x,y)-u|²) = (x-ux)(-a·st) + (y-uy)(b·ct)
        f = (x - ux) * (-a * st) + (y - uy) * (b * ct)
        fp = (a * a) * st * st - a * ct * (x - ux) \
            + (b * b) * ct * ct - b * st * (y - uy)
        if abs(fp) < 1e-9:
            break
        t -= f / fp
    ct, st = math.cos(t), math.sin(t)
    q = QPointF(cx + a * ct, cy + b * st)
    nx, ny = ct / a, st / b   # 바깥 법선 ∝ (x/a², y/b²)
    L = math.hypot(nx, ny) or 1.0
    return q, QPointF(nx / L, ny / L)


def _seg_nearest(a: QPointF, b: QPointF, p: QPointF) -> QPointF:
    """선분 a-b 위에서 점 p 최근접점(로컬)."""
    abx, aby = b.x() - a.x(), b.y() - a.y()
    denom = abx * abx + aby * aby
    if denom < 1e-12:
        return QPointF(a)
    t = ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / denom
    t = max(0.0, min(1.0, t))
    return QPointF(a.x() + t * abx, a.y() + t * aby)


def _symbol_nearest(item, p):
    """심볼의 실제 외곽선(_sym_path)에서 점 p(로컬) 최근접점 + 바깥 단위 법선(로컬).
    경로를 폴리곤으로 평탄화(곡선 포함)해 각 변에서 최근접점을 찾고, 법선은 중심 반대쪽(바깥)으로
    향한다. 마름모·평행사변형처럼 외접 박스와 어긋나는 도형도 '보이는 외곽선'에 정확히 스냅한다."""
    path = item._sym_path()
    c = item.rect().center()
    best_q = None
    best_seg = None
    best_d = float("inf")
    for poly in path.toSubpathPolygons():
        for i in range(poly.count() - 1):
            a, b = poly.at(i), poly.at(i + 1)
            q = _seg_nearest(a, b, p)
            d = (q.x() - p.x()) ** 2 + (q.y() - p.y()) ** 2
            if d < best_d:
                best_d, best_q, best_seg = d, q, (a, b)
    if best_q is None:                       # 방어(빈 경로) — 박스 폴백
        return _rect_nearest(item.rect(), p)
    a, b = best_seg
    nx, ny = -(b.y() - a.y()), (b.x() - a.x())   # 변에 수직
    if (best_q.x() - c.x()) * nx + (best_q.y() - c.y()) * ny < 0:
        nx, ny = -nx, -ny                        # 중심 반대(바깥)로 정렬
    L = math.hypot(nx, ny) or 1.0
    return best_q, QPointF(nx / L, ny / L)


def _nearest_border(item, scene_pt):
    """네모/원/심볼 테두리에서 scene_pt 최근접점 → (snap_scene, outward_unit_scene).
    회전·스케일은 아이템 변환으로 왕복 환산(바깥 법선도 씬 방향으로 변환)."""
    p = item.mapFromScene(scene_pt)
    r = item.rect()
    if isinstance(item, _EllipseItem):
        q, n = _ellipse_nearest(r, p)
    elif isinstance(item, _SymbolItem):
        q, n = _symbol_nearest(item, p)
    else:
        q, n = _rect_nearest(r, p)
    sp = item.mapToScene(q)
    nd = item.mapToScene(QPointF(q.x() + n.x(), q.y() + n.y())) - sp
    L = math.hypot(nd.x(), nd.y()) or 1.0
    return sp, QPointF(nd.x() / L, nd.y() / L)


def _shape_ports(item):
    """도형의 이산 접속점(포트) → [(scene_pt, 바깥법선), ...]. 변 중점 4개(N·E·S·W)를
    _nearest_border로 '실제 외곽선'에 투영한다 — 네모·원은 변 중점 그대로, 심볼은 슬랜트 변
    (평행사변형 등)이라 투영해야 붕 뜨지 않는다. 마름모는 4 꼭짓점이 그대로 N/E/S/W가 된다.
    회전·스케일은 _nearest_border가 아이템 변환으로 왕복 환산."""
    r = item.rect()
    cx, cy = r.center().x(), r.center().y()
    cardinals = (QPointF(cx, r.top()), QPointF(r.right(), cy),
                 QPointF(cx, r.bottom()), QPointF(r.left(), cy))
    return [_nearest_border(item, item.mapToScene(cl)) for cl in cardinals]


# ---- [Stage1] Lucid식 직교 자동 라우팅(기본 엘보) -----------------------------
def _dedup_pts(pts, eps=1e-6):
    """연속 중복점 + 공선(collinear) 중간점 제거. 정렬된 도형 사이의 퇴화 엘보를 직선으로 접는다."""
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p.x() - out[-1].x()) <= eps and abs(p.y() - out[-1].y()) <= eps:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        cross = (b.x() - a.x()) * (c.y() - a.y()) - (b.y() - a.y()) * (c.x() - a.x())
        if abs(cross) <= eps:
            del out[i]   # b가 a-c 선분 위 → 불필요
        else:
            i += 1
    return out


def _ortho_elbow(s: QPointF, e: QPointF, ns, ne):
    """시작 s·끝 e(scene)와 부착 변의 바깥 법선 ns·ne로 직각 엘보의 '중간 정점들'을 계산.
    법선의 우세축(수평/수직)이 각 끝의 이탈·도착 축을 정한다:
      · 양끝 수평 → H-V-H (중간 x = 두 x의 중점)
      · 양끝 수직 → V-H-V (중간 y = 두 y의 중점)
      · 혼합(한쪽 수평·한쪽 수직) → L자(모서리 하나)
    법선이 없으면(방어) 두 점의 우세 델타로 축을 대체. 반환은 중간 정점 리스트(0~2개)."""
    dx, dy = e.x() - s.x(), e.y() - s.y()
    default_h = abs(dx) >= abs(dy)

    def is_horizontal(n):
        if n is None:
            return default_h
        return abs(n.x()) >= abs(n.y())

    sh = is_horizontal(ns)
    eh = is_horizontal(ne)
    if sh and eh:
        mx = (s.x() + e.x()) / 2.0
        return [QPointF(mx, s.y()), QPointF(mx, e.y())]
    if (not sh) and (not eh):
        my = (s.y() + e.y()) / 2.0
        return [QPointF(s.x(), my), QPointF(e.x(), my)]
    if sh and not eh:
        return [QPointF(e.x(), s.y())]   # 수평 이탈 → 수직 도착
    return [QPointF(s.x(), e.y())]       # 수직 이탈 → 수평 도착


# ---- [Stage2] 직교 라우팅 장애물 회피 — 충돌 없는 후보 엘보 선택 -------------------
def _seg_hits_rect(a: QPointF, b: QPointF, r: QRectF, eps=1e-6) -> bool:
    """축정렬 선분 a-b가 사각형 r의 '속'을 지나는가(테두리 접촉은 통과로 봄).
    엘보 세그먼트는 전부 수평/수직이라 축별로 판정. 대각선(엘보에선 미발생)은 bbox 겹침으로 보수 판정."""
    if abs(a.y() - b.y()) <= eps:          # 수평
        y = a.y()
        if y <= r.top() + eps or y >= r.bottom() - eps:
            return False
        x0, x1 = (a.x(), b.x()) if a.x() <= b.x() else (b.x(), a.x())
        return x1 > r.left() + eps and x0 < r.right() - eps
    if abs(a.x() - b.x()) <= eps:          # 수직
        x = a.x()
        if x <= r.left() + eps or x >= r.right() - eps:
            return False
        y0, y1 = (a.y(), b.y()) if a.y() <= b.y() else (b.y(), a.y())
        return y1 > r.top() + eps and y0 < r.bottom() - eps
    x0, x1 = (a.x(), b.x()) if a.x() <= b.x() else (b.x(), a.x())
    y0, y1 = (a.y(), b.y()) if a.y() <= b.y() else (b.y(), a.y())
    return x1 > r.left() and x0 < r.right() and y1 > r.top() and y0 < r.bottom()


def _path_hits_rects(pts, rects, eps=1e-6) -> bool:
    """정점 리스트 pts로 이루어진 폴리라인이 사각형들 중 하나라도 관통하면 True."""
    for i in range(len(pts) - 1):
        for r in rects:
            if _seg_hits_rect(pts[i], pts[i + 1], r, eps):
                return True
    return False


def _normal_stub(p: QPointF, n, d: float) -> QPointF:
    """부착 법선 n의 우세축으로 점 p를 d만큼 바깥으로 민 '스텁점'. n이 없으면 p 그대로.
    A* 라우팅 전 시작·끝에 강제해 ⓐ 테두리 수직 이탈/도착(미관) ⓑ 바인딩 도형을 가로지르지
    않게(스텁이 이미 도형 밖 clearance 거리) 한다."""
    if n is None:
        return p
    if abs(n.x()) >= abs(n.y()):
        return QPointF(p.x() + (d if n.x() >= 0 else -d), p.y())
    return QPointF(p.x(), p.y() + (d if n.y() >= 0 else -d))


# ---- [Stage3] 화살표-화살표 soft 회피 — 세그먼트 교차 판정/집계 --------------------
def _seg_cross_seg(a: QPointF, b: QPointF, c: QPointF, d: QPointF, eps=1e-9) -> bool:
    """두 선분 a-b, c-d의 '내부'가 진짜로 가로지르면 True. 끝점 공유·공선 접촉은 비교차로
    본다(끝점을 공유하는 화살표들이 부착 도형 근처에서 만나는 것을 교차로 오판하지 않게).
    orientation 4-부호(양쪽 모두 엄격히 반대 부호일 때만 교차)."""
    def orient(p, q, r):
        return (q.x() - p.x()) * (r.y() - p.y()) - (q.y() - p.y()) * (r.x() - p.x())
    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    ab_split = (o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)
    cd_split = (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
    return ab_split and cd_split


def _count_seg_crossings(pts, segs) -> int:
    """폴리라인 pts가 회피 세그먼트 segs를 가로지르는 총 횟수(soft 벌점·진단 공용)."""
    if not segs:
        return 0
    n = 0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        for c, d in segs:
            if _seg_cross_seg(a, b, c, d):
                n += 1
    return n


def _astar_ortho(start: QPointF, goal: QPointF, infl, clearance, eps=1e-6,
                 avoid_segs=(), cross_penalty=0.0):
    """[Stage2 승격] Hanan 그리드 위의 직교 A*. 팽창 장애물(infl)을 관통하지 않는 최단 직각
    경로의 '중간 정점'을 반환(없으면 None). 후보 스캔과 달리 임의 밀집 배치에서도 경로가
    존재하면 반드시 찾는다(Hanan 그리드 완전성: 직교 우회로가 있으면 장애물 모서리선 위에도 있다).

    격자선 = {start·goal 좌표} ∪ {각 장애물의 left/right(세로선)·top/bottom(가로선)}.
    노드는 이 선들의 교점, 간선은 인접 노드 사이 축정렬 선분(_seg_hits_rect로 관통 검사).
    회전 벌점(clearance*0.5)으로 엘보 수를 최소화해 경로를 깔끔하게. 상태에 진행축을 넣어
    벌점을 정확히 계산(Manhattan 휴리스틱은 벌점을 무시 → admissible).

    [Stage3] avoid_segs(다른 화살표 세그먼트, 씬좌표)는 hard 장애물이 아니라 soft다:
    간선이 그걸 가로지르면 cross_penalty를 g에 가산(교차 최소화). 우회 레인은 도형 팽창 모서리
    격자선에서 나온다. ⚠ 화살표 좌표는 격자선에 넣지 않는다 — 넣으면 A* 노드가 교차점에 정확히
    얹혀 교차가 '끝점 접촉'이 되고 _seg_cross_seg가 이를 비교차로 처리해 벌점이 눈머는 함정.
    벌점은 비용에만 더하므로 Manhattan 휴리스틱은 여전히 admissible(과대추정 없음).
    avoid_segs가 비면 기존 순수 도형회피와 동일(무회귀)."""
    xs = sorted({start.x(), goal.x(), *(v for r in infl for v in (r.left(), r.right()))})
    ys = sorted({start.y(), goal.y(), *(v for r in infl for v in (r.top(), r.bottom()))})
    nx, ny = len(xs), len(ys)
    xi = {v: i for i, v in enumerate(xs)}
    yi = {v: i for i, v in enumerate(ys)}
    sx, sy = xi[start.x()], yi[start.y()]
    gx, gy = xi[goal.x()], yi[goal.y()]

    def edge_ok(ax, ay, bx, by):
        a = QPointF(xs[ax], ys[ay])
        b = QPointF(xs[bx], ys[by])
        return not any(_seg_hits_rect(a, b, r, eps) for r in infl)

    turn_cost = clearance * 0.5

    def h(ix, iy):
        return abs(xs[ix] - xs[gx]) + abs(ys[iy] - ys[gy])

    start_state = (sx, sy, 0)                 # axis: 0=출발(무), 1=수평, 2=수직
    dist = {start_state: 0.0}
    prev = {}
    pq = [(h(sx, sy), 0.0, start_state)]
    goal_state = None
    while pq:
        _f, g, st = heapq.heappop(pq)
        if g > dist.get(st, float("inf")):
            continue
        ix, iy, axis = st
        if ix == gx and iy == gy:
            goal_state = st
            break
        for dix, diy, nax in ((1, 0, 1), (-1, 0, 1), (0, 1, 2), (0, -1, 2)):
            jx, jy = ix + dix, iy + diy
            if not (0 <= jx < nx and 0 <= jy < ny):
                continue
            if not edge_ok(ix, iy, jx, jy):
                continue
            step = abs(xs[jx] - xs[ix]) + abs(ys[jy] - ys[iy])
            turn = turn_cost if (axis != 0 and axis != nax) else 0.0
            pen = 0.0
            if cross_penalty and avoid_segs:   # [Stage3] soft: 다른 화살표를 가로지르면 벌점
                ea, eb = QPointF(xs[ix], ys[iy]), QPointF(xs[jx], ys[jy])
                pen = cross_penalty * sum(1 for c, d in avoid_segs if _seg_cross_seg(ea, eb, c, d))
            ng = g + step + turn + pen
            nst = (jx, jy, nax)
            if ng < dist.get(nst, float("inf")):
                dist[nst] = ng
                prev[nst] = st
                heapq.heappush(pq, (ng + h(jx, jy), ng, nst))
    if goal_state is None:
        return None
    # 재구성 → 끝점 제외한 중간 정점만 반환(_dedup_pts가 공선점을 접는다).
    path = []
    st = goal_state
    while st is not None:
        ix, iy, _ax = st
        path.append(QPointF(xs[ix], ys[iy]))
        st = prev.get(st)
    path.reverse()
    return path[1:-1]


def _route_ortho(s: QPointF, e: QPointF, ns, ne, obstacles, clearance=12.0,
                 avoid_segs=(), cross_penalty=0.0):
    """[Stage2 승격] Stage1 엘보(_ortho_elbow)를 우선하되, 그 경로가 장애물을 관통하면
    Hanan 그리드 A*(_astar_ortho)로 우회로를 찾아 '중간 정점'을 반환.
      · 장애물 없음 또는 Stage1이 이미 안전(도형·화살표 모두) → Stage1 그대로(무변경·되먹임 없음).
      · 관통/교차 시 → 법선 스텁을 씌운 A* → (실패 시) 스텁 없는 A* → (실패 시) Stage1 폴백.
    후보 스캔(구현 (b))과 달리 밀집 배치에서도 우회로가 존재하면 반드시 찾는다(그리드 완전성).
    obstacles: scene 좌표 사각형(양끝 바인딩 도형은 호출부에서 이미 제외). clearance만큼 팽창해 여유 확보.
    [Stage3] avoid_segs/cross_penalty: 도형은 hard(관통 금지), 다른 화살표는 soft(교차 최소화).
    preferred가 도형은 안전하나 화살표를 가로지르면 A* 우회를 시도하되, 교차를 실제로 줄일 때만
    채택(개선 없으면 preferred 유지 → 불필요한 우회·되먹임 방지)."""
    preferred = _ortho_elbow(s, e, ns, ne)
    infl = ([r.adjusted(-clearance, -clearance, clearance, clearance) for r in obstacles]
            if obstacles else [])
    pref_hits_shape = _path_hits_rects([s] + preferred + [e], infl) if infl else False
    pref_cross = _count_seg_crossings([s] + preferred + [e], avoid_segs)
    # preferred가 도형 안전 + 화살표 교차 없음 → 그대로(기존 무변경 보장).
    if not pref_hits_shape and pref_cross == 0:
        return preferred
    s2 = _normal_stub(s, ns, clearance)
    e2 = _normal_stub(e, ne, clearance)
    # (1) 법선 스텁을 강제한 A*(수직 이탈/도착·바인딩 도형 회피) → (2) 스텁 없는 A*(스텁이
    #     막혔을 때 폴백). 각 후보는 s→...→e 전체 경로의 도형 관통을 최종 확인한 뒤에만 채택.
    attempts = [
        (s2, e2, ([] if s2 == s else [s2]), ([] if e2 == e else [e2])),
        (s, e, [], []),
    ]
    if pref_hits_shape:
        # 도형 관통 회피는 hard 요구 — 기존대로 첫 안전 후보 채택(화살표는 벌점으로 A*가 이미 최소화).
        for a, b, pre, post in attempts:
            interior = _astar_ortho(a, b, infl, clearance,
                                    avoid_segs=avoid_segs, cross_penalty=cross_penalty)
            if interior is None:
                continue
            mids = pre + interior + post
            if not _path_hits_rects([s] + mids + [e], infl):
                return mids
        return preferred
    # preferred가 도형은 안전하나 화살표를 가로지름 — 두 시도를 모두 평가해 '교차를 가장 많이
    # 줄이는' 도형-안전 후보만 채택(개선 없으면 preferred 유지 → 불필요한 우회·되먹임 방지).
    best, best_cross = preferred, pref_cross
    for a, b, pre, post in attempts:
        interior = _astar_ortho(a, b, infl, clearance,
                                avoid_segs=avoid_segs, cross_penalty=cross_penalty)
        if interior is None:
            continue
        mids = pre + interior + post
        if _path_hits_rects([s] + mids + [e], infl):   # 도형 관통은 hard — 후보 기각
            continue
        c = _count_seg_crossings([s] + mids + [e], avoid_segs)
        if c < best_cross:
            best, best_cross = mids, c
    return best


# ---------------------------------------------------------------------------
# [우리 확장] 다중선택 그룹 변형 (회전·스케일) — Stage 1
# ---------------------------------------------------------------------------
def _rotate_about(p: QPointF, c: QPointF, deg: float) -> QPointF:
    """씬 좌표점 p를 중심 c 기준 deg만큼 회전(양수=시계, y-down 화면 규약 — setRotation과 동일)."""
    r = math.radians(deg)
    cos, sin = math.cos(r), math.sin(r)
    dx, dy = p.x() - c.x(), p.y() - c.y()
    return QPointF(c.x() + dx * cos - dy * sin, c.y() + dx * sin + dy * cos)


# ---------------------------------------------------------------------------
# [Stage2] 기하 리베이크 그룹 변형 — 비균일 스케일(1축)·미러 공통 machinery
# ---------------------------------------------------------------------------
def _axis_scale_fn(axis: str, anchor: float, f: float):
    """씬공간 1축 스케일 함수 — axis('x'|'y') 방향으로 anchor 좌표선 기준 f배(다른 축 불변)."""
    if axis == "x":
        return lambda p: QPointF(anchor + (p.x() - anchor) * f, p.y())
    return lambda p: QPointF(p.x(), anchor + (p.y() - anchor) * f)


def _mirror_fn(axis: str, c: float):
    """씬공간 반사 함수 — axis('x'|'y') 좌표를 c 기준 반전. axis='x'=좌우, 'y'=상하 미러."""
    if axis == "x":
        return lambda p: QPointF(2.0 * c - p.x(), p.y())
    return lambda p: QPointF(p.x(), 2.0 * c - p.y())


def _iter_bound_endpoints(arrow):
    """화살표의 '바인딩된' 끝점 (idx, shape) 나열(곡선=0·1, 직선=0·마지막)."""
    if isinstance(arrow, _ArrowItem):
        idxs = (0, 1)
    elif isinstance(arrow, _PolyArrowItem):
        idxs = (0, len(arrow._pts) - 1)
    else:
        return
    for idx in idxs:
        sh = arrow._bound(idx)
        if sh is not None:
            yield idx, sh


def _collect_bound_arrows(scene, shapes):
    """scene의 모든 화살표 중 shapes 안 도형에 끝점이 바인딩된 (arrow, idx, shape) 목록."""
    out = []
    if scene is None:
        return out
    shapeset = set(shapes)
    for it in scene.items():
        if isinstance(it, (_ArrowItem, _PolyArrowItem)):
            for idx, sh in _iter_bound_endpoints(it):
                if sh in shapeset:
                    out.append((it, idx, sh))
    return out


def _snapshot_set(geom_items, bound_info):
    """undo·드래그 복원 대상 = 변형할 아이템 ∪ 부착점만 바뀌는 (미선택) 화살표."""
    snap_set = list(geom_items)
    for arrow, _idx, _sh in bound_info:
        if arrow not in snap_set:
            snap_set.append(arrow)
    return snap_set


def _rebake_selection(geom_items, bound_info, fn):
    """geom_items 기하를 fn으로 리베이크 + 바인딩 부착점 fn 보정 + 미선택 추종 화살표 reroute.
    호출 전 각 아이템은 '원본 상태'여야 한다(드래그는 매 프레임 apply_geom로 원복 후 호출).
    도형 transform은 리베이크로 안 바뀌므로 부착점 보정에 mapTo/FromScene을 그대로 쓴다."""
    geomset = set(geom_items)
    # 부착점 보정 — 도형이 리베이크되면 그 로컬 부착점도 같은 씬변형으로 옮겨야 상대 테두리
    # 위치가 유지된다(먼저: 원본 부착점 기준으로 계산해야 하므로 기하 리베이크보다 앞).
    for arrow, idx, sh in bound_info:
        old = arrow._bind_pt(idx)
        if old is None:
            continue
        arrow.set_bound(idx, sh, sh.mapFromScene(fn(sh.mapToScene(old))))
    for it in geom_items:
        it.rebake_scene(fn)
    # 미선택(그룹에 안 든) 바인딩 화살표는 새 부착점으로 추종(선택된 화살표는 이미 리베이크됨).
    for arrow, _idx, _sh in bound_info:
        if arrow not in geomset:
            arrow.reroute(pin_pred=lambda i: True)


# ---------------------------------------------------------------------------
# [2d] 빠른 생성(quick-create) — 도트 방향으로 화살표+동일도형 생성
# ---------------------------------------------------------------------------
_QC_OPP = {"r": "l", "l": "r", "t": "b", "b": "t"}
_QC_GAP = 40.0   # 원본과 복제 사이 씬 간격(기본 배치)


def _edge_mid(r: QRectF, side: str) -> QPointF:
    """씬 사각 r의 한 변(t/r/b/l) 중점."""
    if side == "r":
        return QPointF(r.right(), r.center().y())
    if side == "l":
        return QPointF(r.left(), r.center().y())
    if side == "t":
        return QPointF(r.center().x(), r.top())
    return QPointF(r.center().x(), r.bottom())


def _qc_default_delta(sr: QRectF, side: str) -> QPointF:
    """기본 배치 델타 — 원본 씬사각 sr에서 side 방향으로 (도형크기+간격)만큼."""
    if side == "r":
        return QPointF(sr.width() + _QC_GAP, 0.0)
    if side == "l":
        return QPointF(-(sr.width() + _QC_GAP), 0.0)
    if side == "b":
        return QPointF(0.0, sr.height() + _QC_GAP)
    return QPointF(0.0, -(sr.height() + _QC_GAP))


class _GroupTransform:
    """다중선택(최상위 2개 이상) 시 공통 바운딩 박스 + 회전·스케일 핸들.

    개별 아이템 변형(_HandleResizeMixin)이 '자기 중심' 기준인 것과 달리, 그룹 중심/모서리를
    기준으로 **여러 아이템을 한 번에** 강체 회전·균일 스케일한다. 각 아이템은 Qt의
    pos/rotation/scale만 바꾸므로(기하 리베이크 없음) 되돌리기·직렬화가 기존과 호환된다.

    핵심 수학: 아이템의 transformOrigin 씬점 A = mapToScene(origin) = pos+origin 은 회전·스케일과
    무관(Qt는 origin을 기준으로 회전·스케일하되 그 점의 씬 위치는 pos에만 의존). 그래서
    A를 그룹 기준으로 옮기고(pos 조정) rotation/scale을 더하면 아이템 전체가 강체로 변형된다.
    (비유: 회전목마 — 각 말은 제자리서 돌면서(회전) 동시에 축을 중심으로 공전(pos)한다.)
    """
    _HANDLE_PX = 9.0    # 화면 px — 모서리 사각 핸들 한 변
    _HIT_PX = 24.0      # 화면 px — 핸들 잡기 지름(줌 무관)
    _ROT_GAP_PX = 22.0  # 화면 px — bbox 위 회전 핸들 간격

    def __init__(self, view):
        self._view = view
        self._active = None   # None | ("rotate",..) | ("scale",..) | ("scale_axis",axis,anchor,pt)
        self._snap = None     # 회전·균일스케일 전 상태 스냅샷(xform undo·기준값)
        self._center = None
        self._anchor = None
        self._start_angle = 0.0
        self._start_dx = 0.0
        self._start_dy = 0.0
        # [Stage2] 비균일 스케일(1축 변 핸들) — 기하 리베이크 기반
        self._axis = None          # "x" | "y"
        self._anchor_val = 0.0     # 고정 좌표선(반대 변)
        self._axis_start = 0.0     # 시작 델타(bbox 폭·높이)
        self._geom_snap = None     # [(item, capture_geom()), ...] — 원복·undo
        self._geom_items = None    # 기하 리베이크 대상(선택 아이템)
        self._bound_info = None    # _collect_bound_arrows 결과

    def _scene(self):
        return self._view.scene()

    def _s(self) -> float:
        return self._view._view_scale()

    def items(self):
        sc = self._scene()
        if sc is None:
            return []
        return [it for it in sc.selectedItems()
                if it.parentItem() is None and isinstance(it, _HandleResizeMixin)]

    def available(self) -> bool:
        """그룹 오버레이 표시·조작 조건 — 최상위 2개 이상 선택 & select/손 도구."""
        if len(self.items()) < 2:
            return False
        return getattr(self._view._owner, "current_tool", None) in ("select", None)

    def bbox(self) -> QRectF | None:
        its = self.items()
        if len(its) < 2:
            return None
        r = None
        for it in its:
            br = it.mapToScene(it._content_rect()).boundingRect()
            r = br if r is None else r.united(br)
        return r

    # ---- 핸들 기하(씬 좌표) --------------------------------------------------
    def _corners(self, b: QRectF):
        return [b.topLeft(), b.topRight(), b.bottomRight(), b.bottomLeft()]

    def _edges(self, b: QRectF):
        """변 중점 핸들 — (핸들점, 축, 고정좌표선(반대 변)). 축 방향으로 1축 비균일 스케일."""
        return [
            (QPointF(b.center().x(), b.top()),    "y", b.bottom()),  # 상
            (QPointF(b.right(), b.center().y()),  "x", b.left()),    # 우
            (QPointF(b.center().x(), b.bottom()), "y", b.top()),     # 하
            (QPointF(b.left(), b.center().y()),   "x", b.right()),   # 좌
        ]

    def _rot_center(self, b: QRectF) -> QPointF:
        return QPointF(b.center().x(), b.top() - self._ROT_GAP_PX / self._s())

    def handle_at(self, scene_pt: QPointF):
        """씬점이 회전/스케일/변 핸들 위면 조작 튜플, 아니면 None."""
        b = self.bbox()
        if b is None:
            return None
        hit = (self._HIT_PX / self._s()) / 2.0
        if QLineF(self._rot_center(b), scene_pt).length() <= hit:
            return ("rotate", b.center())
        corners = self._corners(b)
        for i, c in enumerate(corners):
            if QLineF(c, scene_pt).length() <= hit:
                return ("scale", corners[(i + 2) % 4], c)  # anchor = 대각 모서리
        for pt, axis, anchor_val in self._edges(b):        # [Stage2] 변 중점 = 1축 비균일
            if QLineF(pt, scene_pt).length() <= hit:
                return ("scale_axis", axis, anchor_val, pt)
        return None

    # ---- 페인트 -------------------------------------------------------------
    def paint(self, painter: QPainter, s: float):
        b = self.bbox()
        if b is None:
            return
        painter.setPen(QPen(QColor(_BLUE), 1.0 / s, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(b)
        h = self._HANDLE_PX / s
        painter.setPen(QPen(QColor("white"), 1.0 / s))
        painter.setBrush(QBrush(QColor(_BLUE)))
        for c in self._corners(b):
            painter.drawRect(QRectF(c.x() - h / 2, c.y() - h / 2, h, h))
        for pt, _axis, _av in self._edges(b):          # [Stage2] 변 중점 핸들(1축 비균일 스케일)
            painter.drawRect(QRectF(pt.x() - h / 2, pt.y() - h / 2, h, h))
        rc = self._rot_center(b)                       # 회전 핸들 — 코랄 원(개별 회전 핸들과 색 통일)
        painter.setBrush(QBrush(QColor(_PEACH)))
        painter.drawEllipse(rc, h / 2, h / 2)

    # ---- 변형 트랜잭션 ------------------------------------------------------
    def begin(self, hit, scene_pt: QPointF):
        self._active = hit
        if hit[0] == "scale_axis":
            self._axis = hit[1]
            self._anchor_val = hit[2]
            hp = hit[3]
            self._axis_start = (hp.x() if self._axis == "x" else hp.y()) - self._anchor_val
            self._begin_geom()
            return
        # 회전·균일 스케일(Stage1) — pos/rot/scale/origin 스냅샷.
        self._snap = [(it, QPointF(it.pos()), it.rotation(), it._scale_or_1(),
                       QPointF(it.transformOriginPoint())) for it in self.items()]
        if hit[0] == "rotate":
            self._center = hit[1]
            self._start_angle = math.degrees(math.atan2(
                scene_pt.y() - self._center.y(), scene_pt.x() - self._center.x()))
        else:
            self._anchor = hit[1]
            self._start_dx = hit[2].x() - self._anchor.x()
            self._start_dy = hit[2].y() - self._anchor.y()

    def _begin_geom(self):
        """[Stage2] 기하 리베이크용 스냅샷 — 선택 아이템 + 부착점 바뀌는 화살표까지."""
        self._geom_items = self.items()
        shapes = [it for it in self._geom_items
                  if not isinstance(it, (_ArrowItem, _PolyArrowItem))]
        self._bound_info = _collect_bound_arrows(self._scene(), shapes)
        self._geom_snap = [(it, it.capture_geom())
                           for it in _snapshot_set(self._geom_items, self._bound_info)]

    def update_to(self, scene_pt: QPointF, shift: bool = False):
        if self._active is None:
            return
        if self._active[0] == "scale_axis":
            cur = scene_pt.x() if self._axis == "x" else scene_pt.y()
            if abs(self._axis_start) < 1e-9:
                return
            f = (cur - self._anchor_val) / self._axis_start
            f = max(0.05, min(f, 20.0))   # 미러(음수)는 별도 액션 — 여기선 뒤집힘 방지
            self._apply_geom_fn(_axis_scale_fn(self._axis, self._anchor_val, f))
            return
        if self._active[0] == "rotate":
            cur = math.degrees(math.atan2(
                scene_pt.y() - self._center.y(), scene_pt.x() - self._center.x()))
            d = cur - self._start_angle
            if shift:
                d = round(d / 15.0) * 15.0
            self._apply_rotate(self._center, d)
        else:
            dx = scene_pt.x() - self._anchor.x()
            dy = scene_pt.y() - self._anchor.y()
            denom = self._start_dx * self._start_dx + self._start_dy * self._start_dy
            if denom < 1e-9:
                return
            # 대각선 방향에 커서를 투영 → 균일 스케일 배율(바깥=확대, 안쪽=축소). Stage1은
            # 미러(음수 뒤집기) 미지원이라 하한 클램프로 뒤집힘·소실 방지.
            f = (dx * self._start_dx + dy * self._start_dy) / denom
            f = max(0.05, min(f, 20.0))
            self._apply_scale(self._anchor, f)

    def _apply_rotate(self, center: QPointF, ddeg: float):
        for it, pos0, rot0, _sc0, org0 in self._snap:
            a = QPointF(pos0.x() + org0.x(), pos0.y() + org0.y())
            a2 = _rotate_about(a, center, ddeg)
            it.setRotation((rot0 + ddeg) % 360)
            it.setPos(a2.x() - org0.x(), a2.y() - org0.y())

    def _apply_scale(self, anchor: QPointF, f: float):
        for it, pos0, _rot0, sc0, org0 in self._snap:
            ax = pos0.x() + org0.x()
            ay = pos0.y() + org0.y()
            a2x = anchor.x() + (ax - anchor.x()) * f
            a2y = anchor.y() + (ay - anchor.y()) * f
            # 이 코드베이스의 boundingRect는 핸들 여유분이 scale 의존(_handle_px가 /scale)이라
            # scale 변경 전 경계 캐시를 무효화해야 잔상·페인트 잘림을 막는다(단일 리사이즈와 동일).
            it.prepareGeometryChange()
            it.setScale(sc0 * f)
            it.setPos(a2x - org0.x(), a2y - org0.y())

    def _apply_geom_fn(self, fn):
        """[Stage2] 원본 스냅샷으로 원복 후 fn으로 리베이크(매 프레임 — 누적 방지)."""
        for it, tok in self._geom_snap:
            it.apply_geom(tok)
        _rebake_selection(self._geom_items, self._bound_info, fn)

    def end(self):
        if self._active is not None:
            if self._active[0] == "scale_axis":
                if self._geom_snap:
                    self._view._owner.push_undo_geom(self._geom_snap)
            elif self._snap:
                self._view._owner.push_undo_xform(self._snap)
        self._active = None
        self._geom_snap = None
        self._geom_items = None
        self._bound_info = None
        self._snap = None


class _AnnotatorView(QGraphicsView):
    _SHORTCUTS = {
        Qt.Key.Key_1: "select", Qt.Key.Key_2: "rect", Qt.Key.Key_3: "arrow",
        Qt.Key.Key_4: "text", Qt.Key.Key_5: "ellipse", Qt.Key.Key_6: "line",
        Qt.Key.Key_7: "pen", Qt.Key.Key_8: "badge", Qt.Key.Key_9: "sarrow",
    }

    def __init__(self, scene: QGraphicsScene, owner):
        super().__init__(scene)
        self._owner = owner  # _EditorMixin 인터페이스를 구현한 호스트 위젯
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMouseTracking(True)
        self._drawing = False
        self._temp: QGraphicsItem | None = None
        # [우리 확장] 하이브리드 클릭 배치(투클릭/멀티클릭) 진행 상태 — 모든 도형 도구 공통.
        # press-drag-release로 끝나는 '드래그'와 달리 클릭으로 점을 놓으므로 _drawing/_temp와
        # 분리한다(release로 끝나지 않게). None=진행 중 아님. 2점 도구는 둘째 클릭이 확정,
        # 직선화살(sarrow)은 클릭마다 정점 추가·더블클릭/Enter 마무리. 마지막 점은 커서 추종.
        self._place: QGraphicsItem | None = None   # 배치 중 아이템
        self._place_tool: str | None = None        # 그 도구 키
        # 실제 press 지점(씬) — 드래그/클릭 판정 기준. self._start는 테두리 스냅으로 '점프'할 수
        # 있어(시작 스냅), 그걸로 이동량을 재면 가만히 클릭해도 드래그로 오인된다(→극소 화살표).
        self._press_scene = QPointF()
        self._start = QPointF()
        self._path: QPainterPath | None = None
        self._move_snap = None       # 드래그 이동 전 위치 스냅샷([(item, QPointF), ...]) — undo용
        # [2e] 스마트 정렬 가이드 — 단일 도형 이동 중 근처 도형과 모서리·중심 정렬 시 스냅+가상선.
        self._move_active = False    # 도형 드래그(이동/핸들) 진행 중(_snapshot_movable서 set)
        self._align_guides = []      # 그릴 가이드선 [("v", x, y0, y1) | ("h", y, x0, x1)]
        # 테두리 스냅(화살표 도구 전용) — 도형 테두리 어디든 최근접점에 붙음
        self._snap_preview = None    # 화살표 도구 유휴 시 커서 근처 테두리 최근접점(마커 표시), 씬 좌표 or None
        self._arrow_snap_exit = None # 그리는 화살표 시작이 테두리에 스냅됐으면 그 바깥 법선(이탈 접선), or None
        self._arrow_tip_snap = None  # 그리는 화살표 tip이 테두리에 스냅된 지점(씬 좌표) or None
        self._none_win_dragging = False  # 손 모드(도구 없음) 빈영역 좌드래그 = 창 이동 중
        # [우리 확장] 방향 감지 러버밴드(AutoCAD window/crossing) — Qt 기본 RubberBandDrag 대체.
        # 왼→오 = window(완전포함, 파란 실선) / 오→왼 = crossing(걸침, 초록 점선).
        self._rb_active = False           # 러버밴드 드래그 중
        self._rb_origin = None            # 시작점(view 좌표) — 방향 판정 기준
        self._rb_current = None           # 현재점(view 좌표)
        self._rb_base = []                # Shift 추가선택용 기존 선택 스냅샷
        # [우리 확장] 직선화살표 waypoint 추가 예고 — 선택된 폴리라인 세그먼트 hover 시
        # (item, seg_idx, 씬 최근접점) or None. 클릭하면 그 자리에 정점 삽입 후 바로 드래그.
        self._seg_add = None
        # [우리 확장] 다중선택 그룹 변형(회전·스케일) — 2개 이상 선택 시 공통 bbox+핸들.
        self._group = _GroupTransform(self)
        self._group_dragging = False
        # [Stage2b] AutoCAD 정통 stretch — crossing 박스에 걸친 정점만 이동(명시적 S 모드).
        # crossing(또는 window) 러버밴드 선택 → S로 무장 → 기준점 클릭 → 도착 클릭. Esc=취소.
        self._last_sel_rect = None    # 마지막 러버밴드 씬 사각(crossing 박스 '기억')
        self._stretch_arm = False     # S로 무장 — 기준점 클릭 대기
        self._stretch_active = False  # 기준점 클릭 후 — 도착점 대기(실시간 프리뷰)
        self._stretch_box = None      # 걸친 정점 판정 박스(씬, 원본 위치 기준)
        self._stretch_base = None     # 기준점(씬)
        self._stretch_cursor = None   # 현재 커서(씬) — 프리뷰 선
        self._stretch_items = None    # 변형 대상 선택 아이템
        self._stretch_binds = None    # _collect_bound_arrows 결과(부착점 추종)
        self._stretch_snap = None     # 기하 스냅샷([(item, capture_geom), ...]) — 원복·undo
        self._stretch_grip_pts = []   # 걸친 grip 하이라이트 점(씬)
        # [2d] 빠른 생성 — 선택된 네모·원의 외부 도트 hover/drag 상태.
        self._qc_hover = None       # (item, side) — 도트 위 hover(고스트 미리보기) or None
        self._qc_dragging = False
        self._qc_src = None         # 원본 도형
        self._qc_side = None        # "t"/"r"/"b"/"l"
        self._qc_cursor = None      # 드래그 중 커서 씬좌표(복제 중심). None=기본 배치(클릭)
        self._qc_press_scene = None # 도트 press 지점(씬) — 클릭/드래그 판정 기준
        # 선택이 바뀌면 그룹 오버레이(bbox·핸들)를 다시 그린다(개별 아이템 repaint와 별개).
        scene.selectionChanged.connect(self.viewport().update)

    def _is_empty_area(self, view_pos) -> bool:
        """클릭 위치에 선택 가능한 주석 아이템이 없으면(배경뿐) True."""
        for it in self.items(view_pos):
            if it is getattr(self._owner, "_bg_item", None):
                continue
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return False
        return True

    def _bend_handle_at(self, view_pos):
        """커서(view 좌표) 아래에 활성 bend 핸들이 있으면 그 화살표, 없으면 None.
        호버 커서를 몸통(이동)과 구분하는 데 쓴다. 선택된 아이템을 직접 순회하므로
        넉넉한 잡기 영역이 shape 컬링에 걸리지 않는다(끝점 판정과 동일 방식)."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if isinstance(it, _ArrowItem) and it._bend_active() \
                    and it._bend_handle_index_at(it.mapFromScene(scene_pt)):
                return it
        return None

    def _box_handle_at(self, view_pos):
        """[2c] 커서가 선택된 네모·원의 박스 핸들 위면 커서('rotate' or Qt.CursorShape), 없으면 None."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            f = getattr(it, "_box_handle_cursor", None)
            if f is None:
                continue
            c = f(it.mapFromScene(scene_pt))
            if c is not None:
                return c
        return None

    # ---- [2d] 빠른 생성(quick-create) ---------------------------------------
    def _qc_dot_at(self, view_pos):
        """커서가 선택된 네모·원의 외부 도트 위면 (item, side), 아니면 None.
        [2d] 핸들과 동일하게 '어느 도구에서든' 작동 — 그린 직후 도구 전환 없이 빠른 생성."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if getattr(it, "_box_handles", None) is None or not it._box_handles():
                continue
            if not it._handle_active():
                continue
            lp = it.mapFromScene(scene_pt)
            for side, dr in it._qc_dot_rects():
                if dr.contains(lp):
                    return (it, side)
        return None

    def _qc_src_scene_rect(self, src) -> QRectF:
        """원본 도형의 씬 사각(회전 무시한 축정렬 bbox — 배치·고스트 기준)."""
        return src.mapToScene(src.rect()).boundingRect()

    def _qc_target_center(self, src, side, cursor_scene):
        """복제 도형 중심(씬) — 드래그 중이면 커서, 아니면 기본 배치 델타."""
        sr = self._qc_src_scene_rect(src)
        if cursor_scene is not None:
            return QPointF(cursor_scene)
        return sr.center() + _qc_default_delta(sr, side)

    def _qc_target_rect(self, src, side, cursor_scene) -> QRectF:
        sr = self._qc_src_scene_rect(src)
        c = self._qc_target_center(src, side, cursor_scene)
        return QRectF(c.x() - sr.width() / 2, c.y() - sr.height() / 2, sr.width(), sr.height())

    def _qc_create(self, src, side, cursor_scene):
        """복제 도형 + 연결 화살표 생성(양끝 바인딩). 한 undo로 둘 다 되돌림."""
        sr = self._qc_src_scene_rect(src)
        center = self._qc_target_center(src, side, cursor_scene)
        dup = src.clone()
        self.scene().addItem(dup)
        dup.setPos(src.pos() + (center - sr.center()))   # 복제 중심 = 목표 중심
        # 연결 화살표 — 원본 side 변 중점 → 복제 반대 변 중점(양끝 도형 바인딩).
        opp = _QC_OPP[side]
        p_src = _edge_mid(self._qc_src_scene_rect(src), side)
        p_dup = _edge_mid(self._qc_src_scene_rect(dup), opp)
        owner = self._owner
        arrow = _PolyArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
        arrow.set_points(p_src, p_dup)
        arrow.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                       | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        arrow.set_bound(0, src, src.mapFromScene(p_src))
        arrow.set_bound(1, dup, dup.mapFromScene(p_dup))
        self.scene().addItem(arrow)
        self._owner.push_undo_add_many([dup, arrow])
        self.scene().clearSelection()
        dup.setSelected(True)
        return dup, arrow

    def _qc_paint_ghost(self, painter, src, side, cursor_scene):
        """빠른 생성 고스트 — 복제 도형 점선 외곽 + 연결선(원본 side변 → 타깃 반대변)."""
        tr = self._qc_target_rect(src, side, cursor_scene)
        pen = QPen(QColor(90, 150, 235), 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        p_src = _edge_mid(self._qc_src_scene_rect(src), side)
        p_tgt = _edge_mid(tr, _QC_OPP[side])
        painter.drawLine(p_src, p_tgt)
        if isinstance(src, _EllipseItem):
            painter.drawEllipse(tr)
        else:
            painter.drawRect(tr)

    def _rot_handle_at(self, view_pos) -> bool:
        """커서가 '선택된' 도형의 회전 점 안이면 True — hover 회전 커서 판정용."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if getattr(it, "_box_handles", None) is not None and it._box_handles():
                continue   # [2c] 네모·원은 _box_handle_at이 담당
            rr = getattr(it, "_rot_handle_rect", None)
            active = getattr(it, "_handle_active", None)
            if rr is None or active is None or not active():
                continue
            if it._uses_endpoints():   # 선·화살표는 회전 핸들 없음(끝점 핸들 사용)
                continue
            if rr().contains(it.mapFromScene(scene_pt)):
                return True
        return False

    def _scale_handle_at(self, view_pos) -> bool:
        """커서가 '선택된' 도형의 크기조절(우하단 파란 사각) 핸들 안이면 True — hover 리사이즈
        커서 판정용. press 처리는 리사이즈로 받는데 커서만 이동으로 뜨던 불일치를 없앤다."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            if getattr(it, "_box_handles", None) is not None and it._box_handles():
                continue   # [2c] 네모·원은 _box_handle_at이 담당
            hr = getattr(it, "_handle_local_rect", None)
            active = getattr(it, "_handle_active", None)
            if hr is None or active is None or not active():
                continue
            if it._uses_endpoints():   # 선·화살표는 크기조절 사각 없음(끝점 핸들 사용)
                continue
            if hr().contains(it.mapFromScene(scene_pt)):
                return True
        return False

    def _selected_endpoint_item(self, view_pos):
        """커서가 '선택된' 선·화살표의 끝점 핸들 안이면 그 아이템, 아니면 None."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.scene().selectedItems():
            uses = getattr(it, "_uses_endpoints", None)
            if uses and it._uses_endpoints() and it._endpoint_active():
                local = it.mapFromScene(scene_pt)
                for i in range(len(it._endpoints())):
                    if it._inflate_to_hit(it._endpoint_rect(i)).contains(local):
                        return it
        return None

    def _over_selected_endpoint(self, view_pos) -> bool:
        """커서가 '선택된' 선·화살표의 끝점 핸들 안이면 True(hover 커서 판정용)."""
        return self._selected_endpoint_item(view_pos) is not None

    def _segment_add_at(self, view_pos):
        """[우리 확장] 선택된 직선화살표의 '세그먼트 위'(정점 핸들 아님)에 커서가 있으면
        (item, seg_idx, 씬 최근접점), 아니면 None. 정점 위는 이동(끝점 드래그)이 우선한다."""
        if self._selected_endpoint_item(view_pos) is not None:
            return None   # 정점 핸들 위 = 이동 우선
        top = self.items(view_pos)
        if top and isinstance(top[0], _ConnectorLabel):
            return None   # 라벨 위 press = 라벨 드래그 우선(waypoint 삽입 안 함)
        scene_pt = self.mapToScene(view_pos)
        total = self._view_scale()
        best = None
        for it in self.scene().selectedItems():
            if not isinstance(it, _PolyArrowItem):
                continue
            local = it.mapFromScene(scene_pt)
            seg = it._nearest_segment(local)
            if seg is None:
                continue
            px = seg[2] * total * it._scale_or_1()   # 화면 px 거리
            if px <= 10.0 and (best is None or px < best[0]):
                best = (px, it, seg[0], it.mapToScene(seg[1]))
        return None if best is None else (best[1], best[2], best[3])

    # ---- [우리 확장] 방향 감지 러버밴드 (AutoCAD window/crossing) -----------
    def _rb_is_window(self) -> bool:
        """왼→오 드래그(현재 x ≥ 시작 x) = window(완전포함). 오→왼 = crossing(걸침)."""
        return self._rb_current.x() >= self._rb_origin.x()

    def _rb_scene_rect(self) -> QRectF:
        return QRectF(self.mapToScene(self._rb_origin),
                      self.mapToScene(self._rb_current)).normalized()

    def _apply_rubber_selection(self):
        """드래그 방향으로 window/crossing을 정해 선택을 실시간 재계산.
        window: 아이템이 상자에 '완전 포함'되어야 선택(sceneBoundingRect 포함).
        crossing: 아이템 외형(shape)이 상자와 '겹치기만' 하면 선택(AutoCAD와 동일)."""
        if self._rb_origin is None or self._rb_current is None:
            return
        rect = self._rb_scene_rect()
        window = self._rb_is_window()
        sel_path = QPainterPath()
        sel_path.addRect(rect)
        bg = getattr(self._owner, "_bg_item", None)
        self.scene().clearSelection()
        for it in self._rb_base:            # Shift 추가선택: 기존 선택 유지
            if it.scene() is not None:
                it.setSelected(True)
        for it in self.scene().items():
            if it is bg:
                continue
            if not (it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            if window:
                # 완전 포함 판정은 '보이는 외형'(_content_rect) 기준 — 선택·회전 핸들 여유가
                # 들어간 sceneBoundingRect로 하면 보이는 것보다 박스를 더 넓게 그려야 잡혔다.
                cr = it._content_rect() if hasattr(it, "_content_rect") \
                    else it.boundingRect()
                hit = rect.contains(it.mapToScene(cr).boundingRect())
            else:
                # 걸침 판정도 '보이는 외형'(_base_shape) 기준 — shape()는 선택 시 핸들 잡기
                # 영역이 붙어 보이지 않는 곳에서 잡히므로 base 외형만 쓴다.
                outline = it._base_shape() if hasattr(it, "_base_shape") else it.shape()
                hit = it.mapToScene(outline).intersects(sel_path)
            if hit:
                it.setSelected(True)

    def _snapshot_movable(self):
        """드래그 이동 전 이동 가능 아이템들의 위치를 기록(release에서 변경분만 undo에 커밋)."""
        self._move_active = True   # [2e] 도형 드래그 시작(이동/핸들) — 스마트 정렬 스냅 판정 활성
        self._move_snap = [
            (it, QPointF(it.pos())) for it in self.scene().items()
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            and not isinstance(it, _ConnectorLabel)   # 라벨 드래그는 t·off 소유라 위치-undo 스코프 밖
        ]

    def _apply_smart_snap(self):
        """[2e] 단일 도형 이동 중 — 근처 도형과 모서리(좌/우/상/하)·중심 정렬 시 스냅 + 가상선.
        Qt가 커서로 옮긴 뒤 호출돼, 임계 내면 정렬 좌표로 살짝 당기고 가이드선을 기록한다.
        핸들 조작(리사이즈·회전·끝점) 중이거나 단일 선택이 아니면 건드리지 않는다."""
        self._align_guides = []
        sel = [it for it in self.scene().selectedItems() if it.parentItem() is None]
        if len(sel) != 1:
            return
        it = sel[0]
        if (getattr(it, "_resizing", False) or getattr(it, "_rotating", False)
                or getattr(it, "_box_resize", None) is not None
                or getattr(it, "_drag_endpoint", None) is not None):
            return
        bg = getattr(self._owner, "_bg_item", None)

        def srect(o):   # 보이는 외형(_content_rect) 기준 씬 사각 — 핸들·도트 여유 제외.
            cr = o._content_rect() if hasattr(o, "_content_rect") else o.boundingRect()
            return o.mapToScene(cr).boundingRect()

        others = [srect(o) for o in self.scene().items()
                  if o is not it and o is not bg and o.parentItem() is None
                  and (o.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)]
        if not others:
            return
        nr = srect(it)
        thr = 6.0 / self._view_scale()
        bx = by = None   # (absdiff, delta, snap_coord, other_rect)
        for orr in others:
            for myx in (nr.left(), nr.center().x(), nr.right()):
                for ox in (orr.left(), orr.center().x(), orr.right()):
                    d = ox - myx
                    if abs(d) <= thr and (bx is None or abs(d) < bx[0]):
                        bx = (abs(d), d, ox, orr)
            for myy in (nr.top(), nr.center().y(), nr.bottom()):
                for oy in (orr.top(), orr.center().y(), orr.bottom()):
                    d = oy - myy
                    if abs(d) <= thr and (by is None or abs(d) < by[0]):
                        by = (abs(d), d, oy, orr)
        dx = bx[1] if bx else 0.0
        dy = by[1] if by else 0.0
        if dx or dy:
            it.moveBy(dx, dy)
            nr = srect(it)
        if bx:
            o = bx[3]
            self._align_guides.append(("v", bx[2], min(nr.top(), o.top()),
                                       max(nr.bottom(), o.bottom())))
        if by:
            o = by[3]
            self._align_guides.append(("h", by[2], min(nr.left(), o.left()),
                                       max(nr.right(), o.right())))

    def _commit_move(self):
        """release 시 실제로 위치가 바뀐 아이템만 이동 undo로 기록."""
        snap = self._move_snap
        self._move_snap = None
        if not snap:
            return
        moved = [(it, old) for it, old in snap
                 if it.scene() is not None and it.pos() != old]
        if moved:
            self._owner.push_undo_move(moved)

    # ---- 테두리 스냅 (화살표 도구가 네모/원 테두리에서 시작·도착하면 붙음) ----
    _BORDER_SNAP_PX = 14.0  # 커서~테두리 최근접점이 이 픽셀 이내면 스냅(시작·tip 공통, 뷰 픽셀)
    _PORT_SNAP_PX = 18.0    # 포트(변 중점 접속점) 우선 스냅 반경 — 연속보다 넓어 먼저 끌린다(뷰 픽셀)

    def _view_scale(self) -> float:
        m = self.transform().m11()
        return m if m > 1e-6 else 1.0

    def _view_dist(self, scene_pt, view_pos) -> float:
        vp = self.mapFromScene(scene_pt)
        return math.hypot(vp.x() - view_pos.x(), vp.y() - view_pos.y())

    def _conn_shapes(self):
        """씬의 네모·원·심볼 아이템(위→아래 순) — 화살표 테두리 스냅·지속연결 대상."""
        return [it for it in self.scene().items()
                if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]

    def _border_snap_at(self, view_pos):
        """커서 근처 도형에 스냅 → (snap_scene, exit_unit, shape) 또는 None.
        [우리 확장] 포트 우선 + 연속 폴백: 커서가 어떤 포트(변 중점 접속점)의 _PORT_SNAP_PX
        이내면 그 포트로 딱 붙고(깔끔), 아니면 기존처럼 외곽선 최근접점에 _BORDER_SNAP_PX로 스냅.
        (shape는 지속 연결 바인딩용.) owner.snap_enabled가 False면 스냅 전체 off."""
        if not getattr(self._owner, "snap_enabled", True):
            return None
        scene_pt = self.mapToScene(view_pos)
        shapes = self._conn_shapes()
        # Pass 1: 포트 우선 — 포트 반경이 연속보다 살짝 넓어 먼저 끌린다.
        bestp = None
        bestpd = self._PORT_SNAP_PX
        pexit = None
        pshape = None
        for sh in shapes:
            for sp, n in _shape_ports(sh):
                d = self._view_dist(sp, view_pos)
                if d <= bestpd:
                    bestpd, bestp, pexit, pshape = d, sp, n, sh
        if bestp is not None:
            return bestp, pexit, pshape
        # Pass 2: 연속 외곽선 폴백(포트에서 먼 변 중간 등).
        best = None
        bestd = self._BORDER_SNAP_PX
        bexit = None
        bshape = None
        for sh in shapes:
            sp, n = _nearest_border(sh, scene_pt)
            d = self._view_dist(sp, view_pos)
            if d <= bestd:
                bestd, best, bexit, bshape = d, sp, n, sh
        if best is None:
            return None
        return best, bexit, bshape

    def _update_snap_preview(self, view_pos):
        """화살표 도구 유휴 시 커서 근처 테두리 최근접점을 마커로 예고(스냅 발동 가능 표시)."""
        prev = self._snap_preview
        new = None
        # 커서가 이미 선택된 화살표의 끝점/곡선 핸들 위면(= 이동·재스냅 모드, 손가락 커서)
        # '새 화살표 시작' 예고 마커를 띄우지 않는다 — 끝점이 도형 테두리에 붙어 있어
        # 생성-스냅점과 겹칠 때 큰 파란 점이 손가락 커서와 함께 남던 문제 방지.
        if (self._owner.is_edit_mode() and self._owner.current_tool in ("arrow", "sarrow")
                and not self._drawing
                and self._selected_endpoint_item(view_pos) is None
                and self._bend_handle_at(view_pos) is None):
            snap = self._border_snap_at(view_pos)
            if snap is not None:
                new = snap[0]
        self._snap_preview = new
        if new != prev:
            self.viewport().update()

    def _update_arrow_draw(self, event, it=None):
        """화살표 그리기 갱신 — tip=커서(테두리 근처면 스냅). 시작·tip 중 하나라도 테두리에
        스냅되면 그 바깥 법선을 이탈/도착 접선으로 쓴 3차 베지어(자동 S자), 둘 다 자유면 직선.
        it=None이면 드래그 중(self._temp), 아니면 클릭 배치 중 아이템."""
        if it is None:
            it = self._temp
        view_pos = event.position().toPoint()
        tip = self._cur_point(event)   # Shift 각도 제약 반영(스냅되면 아래에서 덮어씀)
        # tip 스냅 — 도형 테두리 최근접점
        snap = self._border_snap_at(view_pos)
        # [이슈2] 시작점 바로 근처의 tip 스냅은 무시 — 시작·끝이 같은 테두리에 겹쳐 보이지 않는
        # 극소 화살표가 만들어지는 것을 막는다(사용자: '가상점은 유지되는데 클릭하면 안 생김').
        if (snap is not None
                and self._view_dist(snap[0], self.mapFromScene(self._start)) < self._MIN_SNAP_SPAN_PX):
            snap = None
        back = None
        if snap is not None:
            tip, back = snap[0], snap[1]   # 타깃 바깥 법선 쪽에 ctrl2 → 수직 도착
        self._arrow_tip_snap = snap[0] if snap is not None else None
        if snap is not None:   # 지속 연결: tip이 붙은 도형 + 그 지점(로컬 좌표) 고정
            it.set_bound(1, snap[2], snap[2].mapFromScene(snap[0]))
        else:
            it.set_bound(1, None)
        start = self._start
        exit_dir = self._arrow_snap_exit
        dist = math.hypot(tip.x() - start.x(), tip.y() - start.y())
        it.prepareGeometryChange()
        it._p2 = QPointF(tip)
        if (exit_dir is None and back is None) or dist < 8:
            it._ctrl1 = it._ctrl2 = None   # 양끝 자유거나 너무 짧으면 직선
        else:
            k = max(30.0, min(dist * 0.5, 200.0))
            if exit_dir is not None:
                ex, ey = exit_dir.x(), exit_dir.y()          # 시작 테두리 이탈 접선
            else:
                ex, ey = (tip.x() - start.x()) / dist, (tip.y() - start.y()) / dist  # tip 향해
            if back is not None:
                bx, by = back.x(), back.y()                  # tip 테두리 도착 접선(바깥 법선)
            else:
                bx, by = -ex, -ey                            # 시작과 평행하게 도착(부드러운 S)
            it._ctrl1 = QPointF(start.x() + ex * k, start.y() + ey * k)
            it._ctrl2 = QPointF(tip.x() + bx * k, tip.y() + by * k)
        it.update()
        self.viewport().update()   # tip 마커 갱신

    def _draw_snap_marker(self, painter, sp, s):
        base = 5.0 / s
        painter.setPen(QPen(QColor("white"), 1.5 / s))
        painter.setBrush(QBrush(QColor(_BLUE)))
        painter.drawEllipse(sp, base, base)

    def _draw_port_dots(self, painter, s):
        """[우리 확장] 화살표 도구로 도형 근처에 가면 그 도형의 포트(변 중점 4점)를 속 빈 점으로
        예고. 실제 스냅된 포트는 _draw_snap_marker(채운 파란 점)가 위에 덮어 강조한다."""
        if not self._owner.is_edit_mode() or self._owner.current_tool not in ("arrow", "sarrow"):
            return
        scene_c = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        margin = 30.0 / s
        r = 3.5 / s
        painter.setPen(QPen(QColor(_BLUE), 1.4 / s))
        painter.setBrush(QBrush(QColor("white")))
        for sh in self._conn_shapes():
            br = sh.sceneBoundingRect().adjusted(-margin, -margin, margin, margin)
            if not br.contains(scene_c):
                continue
            for sp, _n in _shape_ports(sh):
                painter.drawEllipse(sp, r, r)

    def leaveEvent(self, event):
        # 커서가 뷰를 벗어나면 스냅·waypoint 예고 마커 정리(잔상 방지).
        if self._snap_preview is not None or self._seg_add is not None:
            self._snap_preview = None
            self._seg_add = None
            self.viewport().update()
        super().leaveEvent(event)

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if not self._owner.is_edit_mode():
            return
        s = self._view_scale()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # [우리 확장] 화살표 도구로 도형 근처면 포트 점 예고(스냅 마커보다 먼저 그려 아래 깔림).
        self._draw_port_dots(painter, s)
        # 그리는 중(드래그)이거나 클릭 배치 중이면 스냅된 시작·tip에 마커(곡선·직선화살 공통).
        drawing = (self._drawing and self._temp is not None) or (self._place is not None)
        if drawing:
            if self._arrow_snap_exit is not None:
                self._draw_snap_marker(painter, self._start, s)
            if self._arrow_tip_snap is not None:
                self._draw_snap_marker(painter, self._arrow_tip_snap, s)
        elif self._snap_preview is not None:
            # 유휴 — 화살표 도구가 테두리 근처(스냅 발동 예고)
            self._draw_snap_marker(painter, self._snap_preview, s)
        # [우리 확장] 방향 감지 러버밴드 박스 — window=파란 실선, crossing=초록 점선(AutoCAD).
        if self._rb_active and self._rb_origin is not None \
                and self._rb_origin != self._rb_current:
            rect = self._rb_scene_rect()
            window = self._rb_is_window()
            color = QColor(70, 130, 220) if window else QColor(90, 190, 90)
            fill = QColor(color); fill.setAlpha(45)
            pen = QPen(color, 1.0)
            pen.setCosmetic(True)  # 줌과 무관하게 1px(선 두께 흔들림 방지)
            if not window:
                pen.setStyle(Qt.PenStyle.DashLine)  # crossing = 점선
            painter.setPen(pen)
            painter.setBrush(QBrush(fill))
            painter.drawRect(rect)
        # [2d] 빠른 생성 고스트 — 도트 hover(기본 배치) 또는 드래그(커서 위치)에 복제 도형+연결선 미리보기.
        if self._qc_dragging and self._qc_src is not None:
            self._qc_paint_ghost(painter, self._qc_src, self._qc_side, self._qc_cursor)
        elif self._qc_hover is not None and self._qc_hover[0].isSelected() \
                and self._qc_hover[0].scene() is not None:
            self._qc_paint_ghost(painter, self._qc_hover[0], self._qc_hover[1], None)
        # [2e] 스마트 정렬 가이드선 — 이동 중 정렬 맞은 축에 마젠타 실선.
        if self._align_guides:
            pen = QPen(QColor(230, 60, 160), 1.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for g in self._align_guides:
                if g[0] == "v":
                    painter.drawLine(QPointF(g[1], g[2]), QPointF(g[1], g[3]))
                else:
                    painter.drawLine(QPointF(g[2], g[1]), QPointF(g[3], g[1]))
        # [우리 확장] 직선화살표 waypoint 추가 예고 — 세그먼트 위 hover 지점에 '+' 고스트 마커.
        if self._seg_add is not None:
            c = self._seg_add[2]
            r = 5.0 / s
            painter.setPen(QPen(QColor("white"), 1.0 / s))
            painter.setBrush(QBrush(QColor(_BLUE)))
            painter.drawEllipse(c, r, r)
            painter.setPen(QPen(QColor("white"), 1.4 / s))
            painter.drawLine(QPointF(c.x() - r * 0.6, c.y()), QPointF(c.x() + r * 0.6, c.y()))
            painter.drawLine(QPointF(c.x(), c.y() - r * 0.6), QPointF(c.x(), c.y() + r * 0.6))
        # [우리 확장] 다중선택 그룹 변형 오버레이 — 공통 bbox + 모서리(스케일)·상단(회전) 핸들.
        # stretch 진행 중엔 그리지 않는다(두 오버레이 겹침 방지 — 그때 조작은 stretch가 소유).
        if self._group.available() and not (self._stretch_arm or self._stretch_active):
            self._group.paint(painter, s)
        # [Stage2b] stretch 오버레이 — 무장(걸친 정점 ●)·활성(기준점→커서 프리뷰선) + crossing 박스.
        if self._stretch_arm or self._stretch_active:
            self._paint_stretch(painter, s)

    # ---- 줌 (휠) — 주석 위면 속성 변경, 아니면 owner의 hug-zoom(창이 이미지에 맞게) ----
    def wheelEvent(self, event):
        dy = event.angleDelta().y()
        if dy == 0:
            return
        # 무한캔버스는 줌이 잦으므로 '그냥 휠 = 항상 줌'. 커서 아래 주석의 속성 조절
        # (도형=두께 / 텍스트·번호=크기)은 'Shift+휠'로 옮긴다(휠-줌 충돌 방지).
        if (self._owner.is_edit_mode()
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            bg = getattr(self._owner, "_bg_item", None)
            for it in self.items(event.position().toPoint()):
                if it is bg:
                    continue
                if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                    self._owner.adjust_item_property(it, 1 if dy > 0 else -1)
                    event.accept()
                    return
        self._owner._on_wheel_zoom(dy)

    # ---- Shift 제약 적용 ---------------------------------------------------
    @staticmethod
    def _constrain(start: QPointF, cur: QPointF, mode: str) -> QPointF:
        dx, dy = cur.x() - start.x(), cur.y() - start.y()
        if mode == "square":
            side = max(abs(dx), abs(dy))
            return QPointF(start.x() + (side if dx >= 0 else -side),
                           start.y() + (side if dy >= 0 else -side))
        if mode == "angle":
            length = math.hypot(dx, dy)
            snapped = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            return QPointF(start.x() + length * math.cos(snapped),
                           start.y() + length * math.sin(snapped))
        if mode == "ortho":
            # [우리 확장] F8 Ortho — start 기준 0°/90°만. |dx|≥|dy|면 수평(y 고정), 아니면 수직(x 고정).
            if abs(dx) >= abs(dy):
                return QPointF(cur.x(), start.y())
            return QPointF(start.x(), cur.y())
        return cur

    def _cur_point(self, event) -> QPointF:
        sp = self.mapToScene(event.position().toPoint())
        tool = self._owner.current_tool
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if tool in ("rect", "ellipse"):
                return self._constrain(self._start, sp, "square")
            if tool in ("line", "arrow", "sarrow"):
                return self._constrain(self._start, sp, "angle")
        # [우리 확장] F8 Ortho — Shift(45°)가 없을 때 선·화살표 드래그를 0/90°로 제약.
        # (sarrow 멀티정점 클릭 배치는 _poly_apply_ortho가 별도 처리 — 여기선 드래그 2점만)
        if getattr(self._owner, "ortho_enabled", False) and tool in ("line", "arrow", "sarrow"):
            return self._constrain(self._start, sp, "ortho")
        return sp

    # ---- 그리기 ------------------------------------------------------------
    def mousePressEvent(self, event):
        # 휠(가운데) 버튼 드래그 = 창(이미지) 이동 — 편집/뷰어 모두. 좌클릭은 그리기에 쓰이므로.
        if event.button() == Qt.MouseButton.MiddleButton:
            self._owner._win_drag_start(event.globalPosition().toPoint())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        # [우리 확장] 클릭 배치 진행 중이면: 좌클릭=다음 점(2점도구 확정·sarrow 정점추가),
        # 우클릭=마무리. (릴리스로 끝내지 않으므로 이 분기가 최우선 — 끝점/세그먼트 판정보다 앞선다.)
        if self._place is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._place_click(event)
                return
            if event.button() == Qt.MouseButton.RightButton:
                self._finish_place(event)
                return
        # 뷰어 모드: 좌클릭 드래그 = 창 이동 (그리기·선택 안 함)
        if not self._owner.is_edit_mode():
            if event.button() == Qt.MouseButton.LeftButton:
                self._owner._win_drag_start(event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._press_scene = self.mapToScene(event.position().toPoint())   # 실제 클릭 지점(스냅 전)
        # [Stage2b] stretch 진행 — 활성(기준점 이미 찍음) 클릭=도착점 확정, 무장 클릭=기준점. 최우선.
        if self._stretch_active:
            self._stretch_apply(self._press_scene)
            self._stretch_commit()
            return
        if self._stretch_arm:
            self._stretch_begin(self._press_scene)
            return
        # [우리 확장] 편집 중 텍스트가 있고 이번 좌클릭이 그 텍스트 위가 아니면 편집을 마무리한다.
        # (빈 영역 클릭은 아래 러버밴드 분기가 super 전에 return해 focusOut이 안 나던 문제 보완 —
        #  clearFocus → focusOutEvent가 빈 텍스트는 폐기, 아니면 완료. 그 텍스트 위 클릭은 캐럿 이동.)
        fi = self.scene().focusItem()
        if isinstance(fi, QGraphicsTextItem) \
                and fi.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction \
                and fi not in self.items(event.position().toPoint()):
            fi.clearFocus()
        # 이미 선택된 화살표/선의 끝점·곡선(bend) 조절 핸들 위 press는 겹친 도형 테두리보다 우선한다
        # (선택된 아이템의 핸들이 먼저 작동해야 함). 끝점/핸들은 도형 테두리에 딱 붙는 일이 잦아
        # Z-order 배달로는 아래 도형이 press를 가로챈다 → 그 아이템을 잠깐 최상단으로 올려 Qt가
        # 그 아이템에 press를 배달(=grab)하게 한 뒤 Z를 즉시 복원한다(grab은 Z와 무관하게 유지).
        # 끝점 우선은 "새 연결 화살표 생성"(arrow 도구)보다도 앞서야 겹칠 때 새 화살표가 안 생긴다.
        vpos = event.position().toPoint()
        # 커서 맨 위가 화살표 라벨이면 라벨 드래그 우선(끝점·bend 핸들보다) — 라벨이 핸들과 겹칠 때 대비.
        _top = self.items(vpos)
        _on_label = bool(_top) and isinstance(_top[0], _ConnectorLabel)
        grab = None if _on_label else (self._selected_endpoint_item(vpos) or self._bend_handle_at(vpos))
        if grab is not None:
            if self._snap_preview is not None:
                # 끝점/핸들 드래그 시작 → 유휴 테두리 스냅 예고 마커를 즉시 제거(드래그 중엔
                # 버튼 눌림으로 _update_snap_preview가 안 돌아 이전 마커가 도형에 남던 잔상 방지).
                self._snap_preview = None
                self.viewport().update()
            old_z = grab.zValue()
            grab.setZValue(1e9)
            super().mousePressEvent(event)
            grab.setZValue(old_z)
            return
        # [우리 확장] 직선화살표 세그먼트 위 press(정점 아님) = 그 자리에 waypoint 삽입 후 바로 드래그.
        if self._seg_add is not None:
            item, seg_idx, scene_pt = self._seg_add
            self._seg_add = None
            item.insert_vertex(seg_idx, item.mapFromScene(scene_pt))
            old_z = item.zValue()
            item.setZValue(1e9)
            super().mousePressEvent(event)   # 커서 아래 새 정점 핸들을 끝점 machinery가 잡음
            item.setZValue(old_z)
            self.viewport().update()
            return
        # [우리 확장] 다중선택 그룹 변형 핸들(회전·스케일) press — 선택/이동보다 우선.
        if self._group.available():
            hit = self._group.handle_at(self.mapToScene(vpos))
            if hit is not None:
                self._group.begin(hit, self.mapToScene(vpos))
                self._group_dragging = True
                return
        # [2d] 빠른 생성 도트 press → 그 방향으로 복제+연결화살표 생성 드래그 시작(이동/선택보다 우선).
        if event.button() == Qt.MouseButton.LeftButton:
            dot = self._qc_dot_at(vpos)
            if dot is not None:
                self._qc_src, self._qc_side = dot
                self._qc_dragging = True
                self._qc_cursor = None   # 릴리스까지 이동(임계 초과) 없으면 기본 배치
                self._qc_press_scene = self.mapToScene(vpos)
                self._qc_hover = None
                return
        tool = self._owner.current_tool
        # 화살표 도구 + 도형 테두리 근처 press → 테두리에 스냅된 곡선 화살표 시작(도형 선택/이동보다 우선).
        # 이 분기가 빈영역/도형-위 선택 판정보다 앞서야 테두리에서 새 화살표가 시작된다(이슈 A).
        if tool == "arrow":
            snap = self._border_snap_at(event.position().toPoint())
            if snap is not None:
                owner = self._owner
                it = _ArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
                self._start = snap[0]
                self._arrow_snap_exit = snap[1]
                self._arrow_tip_snap = None
                it.set_bound(0, snap[2], snap[2].mapFromScene(snap[0]))  # 시작 고정 부착점
                it.set_points(self._start, self._start)
                self._begin_draw(it)
                return
        # 직선화살(sarrow)도 도형 테두리 근처 press면 테두리-스냅 시작(도형 선택/이동보다 우선).
        # sarrow는 멀티정점이라 드래그 전용으로 두지 않는다(테두리에서도 클릭 배치 허용).
        if tool == "sarrow":
            snap = self._border_snap_at(event.position().toPoint())
            if snap is not None:
                owner = self._owner
                it = _PolyArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
                self._start = snap[0]
                self._arrow_snap_exit = snap[1]   # 시작 마커
                self._arrow_tip_snap = None
                it.set_bound(0, snap[2], snap[2].mapFromScene(snap[0]))  # 시작 고정 부착점
                it.set_points(self._start, self._start)
                self._begin_draw(it)
                return
        if tool is None:
            # 손 모드: 빈 영역 좌드래그 = 창 이동, 주석 위 = 단일 선택/이동(하이브리드).
            if self._is_empty_area(event.position().toPoint()):
                self._owner._win_drag_start(event.globalPosition().toPoint())
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                self._none_win_dragging = True
                return
            self._snapshot_movable()   # 주석 드래그 이동을 undo로 되돌리기 위해
            return super().mousePressEvent(event)
        if tool == "select":
            # 빈 영역 드래그 = 방향 감지 러버밴드(window/crossing), 아이템 위 = 이동/선택.
            # 창 이동은 상단 코랄 드래그바로. (편집 모드 본문 pan은 제거)
            if self._is_empty_area(vpos):
                # [우리 확장] Qt 기본 RubberBandDrag 대신 커스텀 밴드 시작(방향별 window/crossing).
                self._rb_active = True
                self._rb_origin = QPoint(vpos)
                self._rb_current = QPoint(vpos)
                # Shift면 기존 선택에 더하고, 아니면 새로 시작(빈영역 클릭=선택해제와 일관).
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._rb_base = list(self.scene().selectedItems()) if shift else []
                self._apply_rubber_selection()
                self.viewport().update()
                return
            self._snapshot_movable()   # 아이템 드래그 이동을 undo로 되돌리기 위해
            return super().mousePressEvent(event)

        # 도형 도구는 기존 주석 위를 클릭하면 그리기 대신 선택/이동.
        # 단, 펜은 빽빽이 겹쳐 그리므로 항상 그린다(펜 선의 선택/이동은 V 도구로).
        if tool != "pen" and not self._is_empty_area(event.position().toPoint()):
            self._snapshot_movable()
            return super().mousePressEvent(event)

        sp = self.mapToScene(event.position().toPoint())
        self._start = sp
        owner = self._owner
        pen = owner.make_pen()

        if tool == "rect":
            it = _RectItem(QRectF(sp, sp))
            it.setPen(pen)
            it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._begin_draw(it)
        elif tool.startswith("sym:"):
            # [우리 확장] 심볼/스텐실 — 네모와 동일한 드래그 그리기(setRect 기반).
            it = _SymbolItem(tool[4:], QRectF(sp, sp))
            it.setPen(pen)
            it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._begin_draw(it)
        elif tool == "ellipse":
            it = _EllipseItem(QRectF(sp, sp))
            it.setPen(pen)
            it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._begin_draw(it)
        elif tool == "line":
            it = _LineItem(QLineF(sp, sp))
            it.setPen(pen)
            self._begin_draw(it)
        elif tool == "arrow":
            it = _ArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
            it.set_points(sp, sp)
            self._arrow_snap_exit = None   # 자유 시작(테두리 스냅 아님) → 직선/자유 곡선
            self._arrow_tip_snap = None
            self._begin_draw(it)
        elif tool == "sarrow":
            # [우리 확장] 하이브리드: 다른 도형처럼 드래그로 시작(드래그=2점 직선, 릴리스 시
            # 이동이 없으면 클릭 배치 모드로 전환돼 멀티정점 폴리라인이 된다).
            it = _PolyArrowItem(owner.current_color, owner.current_width, owner.arrow_head_at_end)
            # [A3] 시작점이 도형 테두리 근처면 스냅(라이브 시작 마커 + 확정 시 _bind_poly_ends가 바인딩).
            ssnap = self._border_snap_at(event.position().toPoint())
            if ssnap is not None:
                self._start = ssnap[0]
                self._arrow_snap_exit = ssnap[1]   # drawForeground 시작 마커 트리거
            else:
                self._arrow_snap_exit = None
            it.set_points(self._start, self._start)
            self._begin_draw(it)
        elif tool == "pen":
            self._path = QPainterPath(sp)
            it = _PathItem(self._path)
            it.setPen(pen)
            self._begin_draw(it)
        elif tool == "text":
            it = _TextItem(owner.current_color)
            it.apply_font_size(owner.current_font_size)
            it.set_bg(owner.current_text_bg)
            # I-beam(세로 막대 중심)이 클릭점 → 캐럿이 그 자리에 오도록 배치 보정.
            # documentMargin만큼 왼쪽, 첫 줄 높이 절반만큼 위로 당긴다(안 하면 글자가 처져 보임).
            margin = it.document().documentMargin()
            line_h = QFontMetricsF(it.font()).height()
            it.setPos(QPointF(sp.x() - margin, sp.y() - margin - line_h / 2))
            self.scene().addItem(it)
            owner.push_undo_add(it)
            it.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            it.setFocus()
            # setFocus가 이전 편집 텍스트의 focusOut→재선택을 유발하므로, 그 뒤에 비운다.
            # (새 텍스트 시작 = 다른 항목 선택 해제. 새 텍스트는 selected 아닌 편집 상태로 둠)
            self.scene().clearSelection()
            # 다른 도구처럼 텍스트 도구를 유지해 연속 배치 가능(빈 텍스트는 focusOut 시 정리).
        elif tool == "badge":
            it = _BadgeItem(owner.next_badge_number(), owner.current_color)
            it.setScale(owner.current_badge_size / float(_DEFAULT_BADGE))
            it.setPos(sp)
            self.scene().addItem(it)
            owner.push_undo_add(it)
            self.scene().clearSelection()
            it.setSelected(True)

    def _begin_draw(self, item: QGraphicsItem):
        item.setZValue(1)
        self.scene().addItem(item)
        self._temp = item
        self._drawing = True
        self._snap_preview = None   # 그리기 시작 → 유휴 스냅 예고 마커 정리
        self.viewport().update()

    # ---- [우리 확장] 하이브리드 클릭 배치 (모든 도형 도구) ------------------
    # 드래그(press-move-release)로 그릴 수도, 클릭으로 점을 놓을 수도 있다. 릴리스 시
    # 이동량이 임계 미만(=끌지 않은 클릭)이면 _enter_click_place로 전환한다.
    #   · 2점 도구(rect/ellipse/line/arrow): 둘째 클릭이 확정.
    #   · sarrow: 클릭마다 정점 추가, 더블클릭/Enter/우클릭 마무리.
    # 마지막 점은 커서를 따라다니는 미리보기. F8 Ortho면 직전 점 기준 0/90°. Esc·도구전환=폐기.
    def _poly_apply_ortho(self, it: "_PolyArrowItem", scene_p: QPointF) -> QPointF:
        if not getattr(self._owner, "ortho_enabled", False) or len(it._pts) < 2:
            return scene_p
        anchor = it.mapToScene(it._pts[-2])   # 직전(확정) 정점
        return self._constrain(anchor, scene_p, "ortho")

    _MIN_SNAP_SPAN_PX = 30.0  # tip 스냅점이 직전 점에서 이 픽셀 미만이면 무시(극소 화살표 방지)

    def _snap_ortho_to_border(self, ortho_p: QPointF, anchor_scene: QPointF) -> QPointF:
        """[A3] F8일 때도 ortho'd 점이 도형 테두리 근처면 그 테두리점으로 스냅(+마커).
        수직 모서리에 수평선이 닿으면 최근접점이 같은 y라 축(수평/수직)이 보존된다.
        직전 점(anchor)에서 너무 가까운 스냅은 무시(극소 세그먼트 방지)."""
        snap = self._border_snap_at(self.mapFromScene(ortho_p))
        if (snap is not None and snap[2] is not None
                and self._view_dist(snap[0], self.mapFromScene(anchor_scene)) >= self._MIN_SNAP_SPAN_PX):
            self._arrow_tip_snap = snap[0]
            return snap[0]
        self._arrow_tip_snap = None
        return ortho_p

    def _poly_place_point(self, event, item):
        """[버그수정] sarrow 배치·미리보기 공통 점 — 미리보기(move)와 클릭(_place_click)이 항상
        같은 좌표를 쓰게 한다(전엔 미리보기=테두리스냅 / 클릭=ortho로 어긋나, F8에서 수평이
        더블클릭 때만 되던 문제). F8 Ortho면 직전 점 기준 0/90° + 테두리 근처면 그 위로 스냅
        (축 보존), 아니면 테두리 스냅, 둘 다 아니면 커서."""
        anchor = item.mapToScene(item._pts[-2])
        if getattr(self._owner, "ortho_enabled", False):
            ortho_p = self._constrain(anchor, self.mapToScene(event.position().toPoint()), "ortho")
            return self._snap_ortho_to_border(ortho_p, anchor)
        snapped = self._poly_border_snap_tip(event, anchor)
        return snapped if snapped is not None else self.mapToScene(event.position().toPoint())

    def _poly_border_snap_tip(self, event, anchor_scene=None):
        """[A3] 직선화살 끝점 라이브 스냅 — 도형 테두리 근처면 그 씬점(+마커), 아니면 None(+마커 해제).
        곡선화살처럼 그리는 중 끝점이 테두리에 시각적으로 달라붙어 사용자가 붙일 위치를 본다.
        단 직전 점(anchor)에서 너무 가까운 스냅은 무시 — 같은 테두리에 겹친 극소 세그먼트 방지."""
        snap = self._border_snap_at(event.position().toPoint())
        if (snap is not None and anchor_scene is not None
                and self._view_dist(snap[0], self.mapFromScene(anchor_scene)) < self._MIN_SNAP_SPAN_PX):
            snap = None
        self._arrow_tip_snap = snap[0] if snap is not None else None
        return snap[0] if snap is not None else None

    def _enter_click_place(self, item, tool):
        """드래그 없는 클릭 → 클릭 배치 모드 진입. item은 이미 시작점을 가진 상태(퇴화)."""
        self._place = item
        self._place_tool = tool
        self._snap_preview = None
        self.scene().clearSelection()
        self.viewport().update()

    def _update_place(self, event):
        """배치 중 아이템의 '현재 점'을 커서로 갱신(드래그 move와 동일 기하 로직 재사용)."""
        item, tool = self._place, self._place_tool
        if tool == "arrow":
            self._update_arrow_draw(event, item)   # 테두리 스냅 + 자동 S자 + 바인딩
            return
        if tool == "sarrow":
            p = self._poly_place_point(event, item)   # 클릭과 동일 계산(미리보기 일치)
            item._set_endpoint(len(item._pts) - 1, item.mapFromScene(p))
            self.viewport().update()   # 스냅 마커 갱신
            return
        sp = self._cur_point(event)
        if tool in ("rect", "ellipse") or tool.startswith("sym:"):
            item.setRect(QRectF(self._start, sp).normalized())
        elif tool == "line":
            item.setLine(QLineF(self._start, sp))
        self.viewport().update()

    def _place_click(self, event):
        """좌클릭: sarrow=정점 추가(계속) / 2점 도구=둘째 클릭 확정."""
        if self._place_tool == "sarrow":
            it = self._place
            p = self._poly_place_point(event, it)   # 미리보기(_update_place)와 동일 계산 + _arrow_tip_snap 갱신
            local = QPointF(it.mapFromScene(p))
            it.prepareGeometryChange()
            it._pts[-1] = QPointF(local)      # 미리보기 → 확정
            it._pts.append(QPointF(local))    # 새 미리보기(커서 추종) — _finish_place가 pop
            it.update()
            # [우리 확장] 클릭점이 도형 테두리에 스냅됐으면 그 점이 종점 — 더블클릭 없이 자동 마무리.
            # (시작점은 _enter_click_place로 배치되므로 이 경로를 안 타 조기 종료되지 않는다.)
            if self._arrow_tip_snap is not None:
                self._finish_place()
                return
            self.viewport().update()
        else:
            self._finish_place(event)

    def _place_nondegenerate(self, it, tool) -> bool:
        """2점 도구가 '점 하나'로 퇴화하지 않았는지(너무 작지 않은지)."""
        if tool in ("rect", "ellipse") or tool.startswith("sym:"):
            r = it.rect()
            return abs(r.width()) >= 2 or abs(r.height()) >= 2
        if tool == "line":
            ln = it.line()
            return math.hypot(ln.dx(), ln.dy()) >= 2
        if tool == "arrow":
            return math.hypot(it._p2.x() - it._p1.x(), it._p2.y() - it._p1.y()) >= 2
        return True

    def _finish_place(self, event=None):
        """더블클릭/Enter/우클릭/2점 둘째 클릭 — 확정(undo+선택), 유효하지 않으면 폐기."""
        it, tool = self._place, self._place_tool
        if it is None:
            self._place = self._place_tool = None
            return
        if tool == "sarrow":
            it.prepareGeometryChange()
            if it._pts:
                it._pts.pop()             # 커서 추종 미리보기 정점 제거
            valid = len(it._pts) >= 2
        else:
            if event is not None:
                self._update_place(event)  # 마지막 클릭 위치로 2nd point 확정
            valid = self._place_nondegenerate(it, tool)
        self._place = None
        self._place_tool = None
        self._arrow_snap_exit = None
        self._arrow_tip_snap = None
        if valid:
            if isinstance(it, _PolyArrowItem):
                self._bind_poly_ends(it)   # [A3] 끝점이 도형 테두리 근처면 스냅+바인딩
            it.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            self._owner.push_undo_add(it)
            self.scene().clearSelection()
            it.setSelected(True)
            if hasattr(it, "_sync_label"):
                it._sync_label()
            it.update()
        elif it.scene() is not None:
            self.scene().removeItem(it)   # 퇴화/정점 부족 → 폐기
        self.viewport().update()

    def _cancel_place(self):
        """Esc/도구 전환 — 진행 중 배치를 통째로 폐기(있을 때만)."""
        it = self._place
        self._place = None
        self._place_tool = None
        self._arrow_snap_exit = None
        self._arrow_tip_snap = None
        self._qc_hover = None   # [2d] 도구 전환 시 빠른 생성 고스트도 지움
        if it is not None and it.scene() is not None:
            self.scene().removeItem(it)
            self.viewport().update()

    def _bind_poly_ends(self, it):
        """[A3] 직선화살표 확정 시 — 시작·끝 정점이 도형 테두리 근처면 그 지점으로 스냅하고
        지속 연결 바인딩(도형 이동 시 추종). o-snap(F3) 꺼짐이면 _border_snap_at이 None → 무바인딩."""
        for idx in (0, len(it._pts) - 1):
            vscene = it.mapToScene(it._pts[idx])
            snap = self._border_snap_at(self.mapFromScene(vscene))
            if snap is not None and snap[2] is not None:
                it._set_endpoint(idx, it.mapFromScene(snap[0]))
                it.set_bound(idx, snap[2], snap[2].mapFromScene(snap[0]))
        # [Stage1] 양끝이 모두 도형에 붙고 수동 waypoint가 없는(2정점) 직선화살은 자동 직교 엘보로 전환.
        # 수동 폴리라인(정점 3개↑)은 사용자 경로이므로 건드리지 않는다.
        if it._bind_start is not None and it._bind_end is not None and len(it._pts) == 2:
            it._auto_route = True
            it.build_elbow()

    def _editing_text_hover(self, view_pos) -> str | None:
        """편집 중인 텍스트 위 hover면 'text'(내부=캐럿) / 'move'(테두리 band=이동), 아니면 None.
        테두리 band는 화면 8px 두께로 잡아 뷰·아이템 스케일과 무관하게 일정하게 보이게 한다."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.items(view_pos):
            if isinstance(it, _TextItem) and \
                    it.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction:
                cr = it._content_rect()
                band = 8.0 / (self._view_scale() * it._scale_or_1())  # 화면 8px → 로컬 두께
                inner = cr.adjusted(band, band, -band, -band)
                if inner.width() <= 0 or inner.height() <= 0:
                    return "text"  # 너무 작으면 전부 캐럿(편집 중이므로 I빔 우선)
                return "text" if inner.contains(it.mapFromScene(scene_pt)) else "move"
        return None

    def mirror_selection(self, axis: str):
        """[Stage2] 선택(1개↑)을 공통 bbox 중심 기준 반사. axis='x'=좌우, 'y'=상하.
        도형·선·화살표는 기하 반전(화살촉 방향은 기하에서 자동 보정), 텍스트·번호는 위치만
        반사(글자 가독 유지). 도형에 붙은 화살표 부착점도 함께 반사돼 연결 유지."""
        sel = [it for it in self.scene().selectedItems()
               if it.parentItem() is None and isinstance(it, _HandleResizeMixin)]
        if not sel:
            return
        r = None
        for it in sel:
            br = it.mapToScene(it._content_rect()).boundingRect()
            r = br if r is None else r.united(br)
        if r is None:
            return
        c = r.center().x() if axis == "x" else r.center().y()
        fn = _mirror_fn(axis, c)
        shapes = [it for it in sel if not isinstance(it, (_ArrowItem, _PolyArrowItem))]
        bound = _collect_bound_arrows(self.scene(), shapes)
        snaps = [(it, it.capture_geom()) for it in _snapshot_set(sel, bound)]
        _rebake_selection(sel, bound, fn)
        self._owner.push_undo_geom(snaps)
        self.viewport().update()

    # ---- [Stage2b] AutoCAD 정통 stretch — crossing 박스에 걸친 정점만 이동 ----------
    # 명시적 모드(암묵 트리거 금지 — 과거 '이동 폴백' 혼동으로 롤백된 전례): crossing(또는
    # window) 러버밴드 선택으로 박스를 '기억'(_last_sel_rect) → S로 무장(_stretch_arm) →
    # 기준점 클릭(_stretch_begin) → 이동(프리뷰) → 도착 클릭(_stretch_commit). Esc=취소.
    # 이동은 '전체 아이템 fn' 리베이크가 아니라 '박스 안 grip만 +delta'인 공간 fn을 기존
    # _rebake_selection에 흘려보내 재사용한다: 점 기반(선·화살표·폴리)=정점별 이동, 네모·원=
    # 걸친 모서리 AABB, 바인딩 부착점=박스 안이면 fn으로 따라옴 → "걸친 쪽만 따라온다".
    # 완전포함 도형은 모든 grip이 박스 안 → 전부 +delta → 강체 이동. 판정은 항상 '원본 위치'
    # 기준(매 프레임 스냅샷 원복 후 fn 적용)이라 박스가 고정된다.
    @staticmethod
    def _stretch_inside_fn(box: QRectF, delta: QPointF):
        def fn(p):
            return (QPointF(p.x() + delta.x(), p.y() + delta.y())
                    if box.contains(p) else QPointF(p))
        return fn

    def _stretch_arm_now(self):
        """S키 — 러버밴드 박스가 기억돼 있고 선택이 있으면 stretch 무장."""
        if self._stretch_active or self._stretch_arm:
            return
        sel = [it for it in self.scene().selectedItems()
               if it.parentItem() is None and isinstance(it, _HandleResizeMixin)]
        box = self._last_sel_rect
        if not sel or box is None or box.width() < 1e-6 or box.height() < 1e-6:
            return
        self._stretch_box = QRectF(box)
        self._stretch_items = sel
        self._stretch_grip_pts = [g for it in sel for g in it._stretch_grips()
                                  if self._stretch_box.contains(g)]
        self._stretch_arm = True
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.viewport().update()

    def _stretch_begin(self, base_scene: QPointF):
        """무장 상태에서 기준점 클릭 — 기하 스냅샷 + 트랜잭션 시작."""
        items = self._stretch_items
        shapes = [it for it in items if not isinstance(it, (_ArrowItem, _PolyArrowItem))]
        self._stretch_binds = _collect_bound_arrows(self.scene(), shapes)
        self._stretch_snap = [(it, it.capture_geom())
                              for it in _snapshot_set(items, self._stretch_binds)]
        self._stretch_base = QPointF(base_scene)
        self._stretch_cursor = QPointF(base_scene)
        self._stretch_arm = False
        self._stretch_active = True

    def _stretch_apply(self, cur_scene: QPointF):
        """프리뷰/확정 공통 — 매 프레임 원복 후 공간 fn으로 리베이크. F8이면 기준점서 0/90°."""
        if not self._stretch_active:
            return
        base = self._stretch_base
        if getattr(self._owner, "ortho_enabled", False):
            cur_scene = self._constrain(base, cur_scene, "ortho")
        delta = QPointF(cur_scene.x() - base.x(), cur_scene.y() - base.y())
        for it, tok in self._stretch_snap:   # 원복(누적 방지)
            it.apply_geom(tok)
        fn = self._stretch_inside_fn(self._stretch_box, delta)
        _rebake_selection(self._stretch_items, self._stretch_binds, fn)
        self._stretch_cursor = QPointF(cur_scene)
        self.viewport().update()

    def _stretch_commit(self):
        if self._stretch_snap:
            self._owner.push_undo_geom(self._stretch_snap)
        self._stretch_clear()

    def _stretch_cancel(self):
        if self._stretch_active and self._stretch_snap:
            for it, tok in self._stretch_snap:
                it.apply_geom(tok)   # 원본으로 되돌림(커밋 안 함)
        self._stretch_clear()

    def _stretch_clear(self):
        was = self._stretch_arm or self._stretch_active
        self._stretch_arm = self._stretch_active = False
        self._stretch_box = self._stretch_base = self._stretch_cursor = None
        self._stretch_items = self._stretch_binds = self._stretch_snap = None
        self._stretch_grip_pts = []
        if was:
            self.viewport().unsetCursor()
            self.viewport().update()

    def _paint_stretch(self, painter, s):
        """[Stage2b] stretch 오버레이 — crossing 박스 + 걸친 정점(●) 또는 기준점→커서 프리뷰선."""
        if self._stretch_box is not None:
            pen = QPen(QColor(90, 190, 90), 1.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._stretch_box)
        r = 4.0 / s
        if self._stretch_arm:   # 무장 — 걸친 정점을 빨간 도트로(무엇이 움직일지 예고)
            painter.setPen(QPen(QColor("white"), 1.0 / s))
            painter.setBrush(QBrush(QColor(230, 60, 60)))
            for g in self._stretch_grip_pts:
                painter.drawEllipse(g, r, r)
        if self._stretch_active and self._stretch_base is not None \
                and self._stretch_cursor is not None:
            pen = QPen(QColor(90, 190, 90), 1.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(self._stretch_base, self._stretch_cursor)
            painter.setPen(QPen(QColor("white"), 1.0 / s))
            painter.setBrush(QBrush(QColor(90, 190, 90)))
            painter.drawEllipse(self._stretch_base, r, r)   # 기준점

    def _update_hover_cursor(self, view_pos):
        """편집 모드 hover 커서: 주석 위=이동, 도형 도구+빈영역=십자, select+빈영역=손바닥.
        편집 중 텍스트는 예외 — 내부=캐럿(I빔), 테두리만 이동."""
        vp = self.viewport()
        tool = self._owner.current_tool
        edit_text = self._editing_text_hover(view_pos)
        # [우리 확장] 그룹 변형 핸들 hover — 회전(코랄 커서)·스케일(대각 리사이즈).
        if self._group.available():
            g = self._group.handle_at(self.mapToScene(view_pos))
            if g is not None:
                if g[0] == "rotate":
                    vp.setCursor(_rotate_cursor())
                elif g[0] == "scale_axis":                       # [Stage2] 1축 비균일
                    vp.setCursor(Qt.CursorShape.SizeHorCursor if g[1] == "x"
                                 else Qt.CursorShape.SizeVerCursor)
                else:
                    vp.setCursor(Qt.CursorShape.SizeFDiagCursor)
                return
        if self._qc_dot_at(view_pos) is not None:            # [2d] 빠른 생성 도트
            vp.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        box_h = self._box_handle_at(view_pos)
        if box_h is not None:                                # [2c] 네모·원 박스 핸들
            vp.setCursor(_rotate_cursor() if box_h == "rotate" else box_h)
            return
        if self._bend_handle_at(view_pos) is not None:
            vp.setCursor(Qt.CursorShape.PointingHandCursor)  # 곡선 조절 손잡이(이동과 구분)
        elif self._over_selected_endpoint(view_pos):
            vp.setCursor(Qt.CursorShape.PointingHandCursor)  # 끝점 핸들(이동/재스냅) — 곡선 핸들과 동일
        elif self._seg_add is not None:
            vp.setCursor(Qt.CursorShape.CrossCursor)         # 직선화살표 세그먼트 — waypoint 추가
        elif self._rot_handle_at(view_pos):
            vp.setCursor(_rotate_cursor())                   # 회전 점 — 곡선 화살표 커서
        elif self._scale_handle_at(view_pos):
            vp.setCursor(Qt.CursorShape.SizeFDiagCursor)     # 크기조절 점(우하단) — 대각 리사이즈(↖↘)
        elif edit_text == "text":
            vp.setCursor(Qt.CursorShape.IBeamCursor)         # 편집 중 텍스트 내부 — 캐럿
        elif edit_text == "move":
            vp.setCursor(Qt.CursorShape.SizeAllCursor)       # 편집 중 텍스트 테두리 — 이동
        elif tool in ("arrow", "sarrow") and self._snap_preview is not None:
            vp.setCursor(Qt.CursorShape.CrossCursor)          # 테두리 스냅 — 화살표 시작(도형 위여도)
        elif tool == "pen":
            vp.setCursor(Qt.CursorShape.CrossCursor)         # 펜 — 주석 위에서도 항상 그리기
        elif not self._is_empty_area(view_pos):
            vp.setCursor(Qt.CursorShape.SizeAllCursor)       # 주석 위 — 선택/이동
        elif tool is None:
            vp.setCursor(Qt.CursorShape.OpenHandCursor)      # 손 모드 빈 영역 — 창 이동
        elif tool == "select":
            vp.setCursor(Qt.CursorShape.ArrowCursor)         # 빈 영역 — 러버밴드 선택
        elif tool == "text":
            vp.setCursor(Qt.CursorShape.IBeamCursor)         # 텍스트 — 캐럿 위치 표시
        else:
            vp.setCursor(Qt.CursorShape.CrossCursor)         # 도형 그리기

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.MiddleButton:
            self._owner._win_drag_move(event.globalPosition().toPoint())
            return
        if self._none_win_dragging:  # 손 모드 빈영역 좌드래그 = 창 이동
            self._owner._win_drag_move(event.globalPosition().toPoint())
            return
        if self._rb_active:  # [우리 확장] 방향 감지 러버밴드 — 드래그 중 실시간 선택
            self._rb_current = event.position().toPoint()
            self._apply_rubber_selection()
            self.viewport().update()
            return
        if self._group_dragging:  # [우리 확장] 그룹 변형 드래그 — 회전·스케일 실시간 적용
            self._group.update_to(self.mapToScene(event.position().toPoint()),
                                  bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            self.viewport().update()
            return
        if self._qc_dragging:  # [2d] 빠른 생성 드래그 — 임계 넘게 끌면 커서 위치, 아니면 기본 배치
            cur = self.mapToScene(event.position().toPoint())
            thr = 8.0 / self._view_scale()
            self._qc_cursor = cur if (self._qc_press_scene is not None
                                      and QLineF(self._qc_press_scene, cur).length() > thr) else None
            self.viewport().update()
            return
        if self._stretch_active:  # [Stage2b] stretch 프리뷰 — 버튼 없이 이동해도 갱신(클릭-이동-클릭)
            self._stretch_apply(self.mapToScene(event.position().toPoint()))
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            return
        if self._stretch_arm:     # [Stage2b] 무장 — 기준점 클릭 대기(십자 커서 유지)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            return
        if not self._owner.is_edit_mode():
            if event.buttons() & Qt.MouseButton.LeftButton:
                self._owner._win_drag_move(event.globalPosition().toPoint())
            else:
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        # [우리 확장] 클릭 배치 진행 중 — 버튼 없이 이동해도 마지막 점을 커서로 미리보기.
        if self._place is not None:
            if self._owner.current_tool != self._place_tool:
                self._cancel_place()   # 도구가 바뀌었으면 진행 중 배치 폐기 후 정상 처리로
            else:
                self._update_place(event)
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
                return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self._update_snap_preview(event.position().toPoint())
            prev = self._seg_add
            self._seg_add = self._segment_add_at(event.position().toPoint())
            if (prev is None) != (self._seg_add is None) or (
                    prev is not None and self._seg_add is not None
                    and prev[2] != self._seg_add[2]):
                self.viewport().update()   # waypoint 예고 마커 갱신
            # [2d] 빠른 생성 도트 hover — 고스트 미리보기 갱신.
            prev_qc = self._qc_hover
            self._qc_hover = self._qc_dot_at(event.position().toPoint())
            if prev_qc != self._qc_hover:
                self.viewport().update()
            self._update_hover_cursor(event.position().toPoint())
        if self._drawing and self._temp is not None:
            tool = self._owner.current_tool
            if tool == "arrow":
                self._update_arrow_draw(event)   # 테두리 스냅 + 자동 S자
                return
            sp = self._cur_point(event)
            if tool in ("rect", "ellipse") or tool.startswith("sym:"):
                self._temp.setRect(QRectF(self._start, sp).normalized())
            elif tool == "line":
                self._temp.setLine(QLineF(self._start, sp))
            elif tool == "sarrow":
                if getattr(self._owner, "ortho_enabled", False):
                    # F8: sp가 이미 ortho 처리됨 + 테두리 근처면 그 위로 스냅(축 보존)
                    tip = self._snap_ortho_to_border(sp, self._start)
                    self._temp.set_points(self._start, tip)
                else:
                    snapped = self._poly_border_snap_tip(event, self._start)   # [A3] 라이브 테두리 스냅
                    self._temp.set_points(self._start, snapped if snapped is not None else sp)
                self.viewport().update()   # 스냅 마커 갱신
            elif tool == "pen" and self._path is not None:
                self._path.lineTo(sp)
                self._temp.setPath(self._path)
            return
        # [2e] 도형 이동 드래그 — Qt로 옮긴 뒤 스마트 정렬 스냅 + 가이드선.
        if self._move_active and (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            self._apply_smart_snap()
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._owner._win_drag_end()
            self.viewport().unsetCursor()
            return
        if self._none_win_dragging:  # 손 모드 창 이동 종료
            self._owner._win_drag_end()
            self._none_win_dragging = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self._rb_active:  # [우리 확장] 러버밴드 종료 — 최종 선택은 이미 반영됨, 밴드만 지움
            self._rb_current = event.position().toPoint()
            self._apply_rubber_selection()
            self._last_sel_rect = self._rb_scene_rect()   # [Stage2b] 박스 '기억'(S stretch용)
            self._rb_active = False
            self._rb_origin = self._rb_current = None
            self._rb_base = []
            self.viewport().update()
            return
        if self._group_dragging:  # [우리 확장] 그룹 변형 종료 — undo에 변형 트랜잭션 커밋
            self._group.end()
            self._group_dragging = False
            self.viewport().update()
            return
        if self._qc_dragging:  # [2d] 빠른 생성 종료 — 복제 도형 + 연결 화살표 생성
            src, side, cur = self._qc_src, self._qc_side, self._qc_cursor
            self._qc_dragging = False
            self._qc_src = self._qc_side = self._qc_cursor = None
            self._qc_press_scene = None
            self._qc_hover = None
            if src is not None and src.scene() is not None:
                self._qc_create(src, side, cur)   # cur=None이면 기본 배치(클릭)
            self.viewport().update()
            return
        # [우리 확장] 클릭 배치 진행 중이면 릴리스는 무시 — 점은 클릭(press)으로만 놓는다.
        if self._place is not None:
            return
        if not self._owner.is_edit_mode():
            self._owner._win_drag_end()
            return
        if self._drawing and self._temp is not None:
            item = self._temp
            tool = self._owner.current_tool
            self._drawing = False
            self._temp = None
            self._path = None
            self.viewport().update()   # 스냅 마커 지우기
            # 시작점→놓은 점 이동량으로 '드래그'인지 '클릭'인지 판정(boundingRect는 펜 두께·
            # 화살촉만큼 부풀어 못 씀). 이동이 임계 미만이면 클릭 → 하이브리드 클릭 배치로 전환.
            release = self.mapToScene(event.position().toPoint())
            # 실제 press 지점 기준 이동량 — 시작 스냅 점프를 드래그로 오인하지 않게(버그 수정).
            moved = max(abs(release.x() - self._press_scene.x()),
                        abs(release.y() - self._press_scene.y()))
            if (tool in _SHAPE_TOOLS or tool.startswith("sym:")) and moved < 4:
                # 끌지 않은 클릭 → 폐기 대신 투클릭/멀티클릭 배치 모드로 진입(점은 유지).
                # 곡선·직선화살 모두 테두리에서도 클릭 배치 허용(하이브리드 일관).
                self._enter_click_place(item, tool)
                return
            # 드래그로 그린 경우 — 즉시 확정.
            self._arrow_snap_exit = None
            self._arrow_tip_snap = None
            if isinstance(item, _PolyArrowItem):
                self._bind_poly_ends(item)   # [A3] 끝점이 도형 테두리 근처면 스냅+바인딩
            item.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
            self._owner.push_undo_add(item)
            # 방금 그린 주석을 바로 선택 — 추가 클릭 없이 이동/색·두께 수정 가능.
            # 단 펜은 연속 그리기라 선택 네모가 거슬리므로 선택하지 않는다.
            self.scene().clearSelection()
            if tool != "pen":
                item.setSelected(True)
            return
        self._commit_move()   # 드래그 이동이 있었으면 undo에 기록
        if self._move_active or self._align_guides:   # [2e] 스마트 정렬 상태 정리
            self._move_active = False
            self._align_guides = []
            self.viewport().update()
        super().mouseReleaseEvent(event)

    def _labelable_at(self, view_pos):
        """[우리 확장] 커서 아래 '맨 위 선택가능 아이템'이 선/화살표면 그 아이템, 아니면 None.
        위에 텍스트·도형이 있으면 None(그쪽 기본 동작을 살린다 — 라벨 더블클릭=그 라벨 편집)."""
        for it in self.items(view_pos):
            if it is getattr(self._owner, "_bg_item", None):
                continue
            if isinstance(it, (_LineItem, _ArrowItem, _PolyArrowItem,
                               _SymbolItem, _RectItem, _EllipseItem)):
                return it
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return None
        return None

    def _titleblock_at(self, view_pos):
        """[우리 확장 · Phase 4] 커서 아래 '맨 위 선택형'이 표제란 프레임이면 그것, 아니면 None.
        프레임(z 최하단) 위에 도형이 얹혀 있으면 그 도형의 기본 동작(라벨 편집)을 살린다."""
        for it in self.items(view_pos):   # 위→아래 stacking 순
            if it is getattr(self._owner, "_bg_item", None):
                continue
            if isinstance(it, _TitleBlockItem):
                return it
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return None
        return None

    def _table_cell_at(self, view_pos):
        """[우리 확장 · Phase 4] view_pos 아래의 표 셀 (item, r, c) — 표가 없거나 격자 밖이면 None.
        표 위에 다른 선택형 아이템이 얹혀 있으면(위 stacking) 그쪽 우선이라 None."""
        scene_pt = self.mapToScene(view_pos)
        for it in self.items(view_pos):
            if isinstance(it, _TableItem):
                rc = it.cell_at(it.mapFromScene(scene_pt))
                return (it, rc[0], rc[1]) if rc is not None else None
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                return None
        return None

    def _begin_cell_edit(self, item, r, c):
        """[우리 확장 · Phase 4] 표 셀 (r, c)에 인라인 편집기를 띄운다."""
        self._cell_editor = _CellEditor(self, item, r, c)

    def _begin_label_edit(self, item):
        """[우리 확장] 선/화살표의 라벨을 생성(없으면)하고 편집 모드로 진입."""
        new = not item._label_alive()
        lbl = item.ensure_label()
        if new:
            self._owner.push_undo_add(lbl)   # 라벨 생성 되돌리기(빈 채 나가면 자동 폐기됨)
        self.scene().clearSelection()
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        lbl.setFocus()
        cur = lbl.textCursor()               # 기존 텍스트 전체 선택(빠른 교체)
        cur.select(cur.SelectionType.Document)
        lbl.setTextCursor(cur)

    def mouseDoubleClickEvent(self, event):
        # 뷰어 모드: 더블클릭 = 닫기 (편집 모드는 텍스트 재편집 등 기본 동작 유지)
        if not self._owner.is_edit_mode():
            if event.button() == Qt.MouseButton.LeftButton:
                self._owner.close()
            return
        # [우리 확장] 클릭 배치 마무리(더블클릭). 이 더블클릭의 첫 press가 이미 점을
        # 놓았으므로(sarrow), 마무리 시 커서 추종 미리보기 점만 떼면 그 자리가 끝점이 된다.
        if self._place is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._finish_place(event)
                event.accept()
            return
        # [우리 확장 · Phase 4] 표제란 프레임 더블클릭 = 필드 편집 폼(host가 소유).
        if event.button() == Qt.MouseButton.LeftButton:
            tb = self._titleblock_at(event.position().toPoint())
            if tb is not None and hasattr(self._owner, "_edit_titleblock"):
                self._owner._edit_titleblock(tb)
                event.accept()
                return
        # [우리 확장 · Phase 4] 표 셀 더블클릭 = 인라인 편집(엑셀식).
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._table_cell_at(event.position().toPoint())
            if hit is not None:
                self._begin_cell_edit(*hit)
                event.accept()
                return
        # [우리 확장] 선/화살표 더블클릭 = 라벨 달기/편집(위에 다른 선택형이 없을 때만).
        if event.button() == Qt.MouseButton.LeftButton:
            target = self._labelable_at(event.position().toPoint())
            if target is not None:
                self._begin_label_edit(target)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    # ---- 키 (Space 토글 / 도구 단축키 / Delete / Ctrl+Z / Esc) -------------
    def keyPressEvent(self, event):
        fi = self.scene().focusItem()
        editing_text = (
            isinstance(fi, QGraphicsTextItem)
            and fi.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction
        )
        key = event.key()
        mods = event.modifiers()
        # [우리 확장] 클릭 배치 진행 중(텍스트 편집 아님): Enter=마무리 / Esc=취소. 최우선.
        if self._place is not None and not editing_text:
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._finish_place()
                return
            if key == Qt.Key.Key_Escape:
                # [우리 확장] sarrow는 Esc=전체취소가 아니라 '지금까지 놓은 점으로 확정'(마지막 커서
                # 추종 미리보기만 버림). 확정할 정점이 부족하면(시작점만) _finish_place가 알아서 폐기.
                # 다른 도구(2점)는 종전대로 취소.
                if self._place_tool == "sarrow":
                    self._finish_place()
                else:
                    self._cancel_place()
                return
        if editing_text and key == Qt.Key.Key_Escape:
            # 텍스트 편집 중 ESC = 편집기 닫기가 아니라 텍스트 완료(=Ctrl+Enter와 동일).
            # clearFocus → focusOutEvent가 정리(빈 텍스트 폐기 / 비어있지 않으면 선택 해제).
            fi.clearFocus()
            return
        if not editing_text and key == Qt.Key.Key_Space:
            self._owner.toggle_edit_mode()
            return
        if not editing_text and key == Qt.Key.Key_Escape:
            if self._stretch_arm or self._stretch_active:   # [Stage2b] stretch 취소 최우선
                self._stretch_cancel()
                return
            # 선택된 주석이 있으면 ESC는 선택(파란 점선)만 해제 — 편집기는 안 닫는다.
            # 선택이 없을 때만 편집기 종료로 넘어간다(주석 → 뷰어 → 닫기 단계적 취소).
            if self.scene().selectedItems():
                self.scene().clearSelection()
                return
            self._owner._on_escape()
            return
        if self._owner.is_edit_mode() and not editing_text:
            # 화살표키 — 선택된 주석 이동. 기본은 넓게(10px), Shift/Ctrl로 세밀하게(1px). 도구와 무관.
            arrow = {
                Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1),
            }.get(key)
            if arrow is not None:
                sel = self.scene().selectedItems()
                if sel:
                    # 이동 전 위치 기록(Ctrl+Z 원복). 같은 선택의 연속 nudge는 하나로 합쳐
                    # undo 폭주를 막는다(coalesce_key=선택 집합).
                    self._owner.push_undo_move(
                        [(it, QPointF(it.pos())) for it in sel],
                        coalesce_key=frozenset(sel))
                    fine = mods & (Qt.KeyboardModifier.ShiftModifier
                                   | Qt.KeyboardModifier.ControlModifier)
                    step = 1 if fine else 10
                    for it in sel:
                        it.moveBy(arrow[0] * step, arrow[1] * step)
                    return
            if (mods & Qt.KeyboardModifier.ShiftModifier) and key == Qt.Key.Key_H:
                self.mirror_selection("x")   # [Stage2] 좌우 반전
                return
            if (mods & Qt.KeyboardModifier.ShiftModifier) and key == Qt.Key.Key_V:
                self.mirror_selection("y")   # [Stage2] 상하 반전
                return
            if (key == Qt.Key.Key_S and not (mods & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.ShiftModifier))
                    and self._owner.current_tool in ("select", None)):
                self._stretch_arm_now()   # [Stage2b] 러버밴드 선택 후 S = stretch 무장
                return
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_A:
                for it in self.scene().items():
                    if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                        it.setSelected(True)
                return
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_C:
                self._owner.copy_selection()
                return
            if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_V:
                self._owner.paste_selection()
                return
            if key in self._SHORTCUTS and not (mods & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                    | Qt.KeyboardModifier.ShiftModifier)):
                self._owner.set_tool(self._SHORTCUTS[key])
                return
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                selected = list(self.scene().selectedItems())
                if selected:
                    for it in selected:
                        self.scene().removeItem(it)
                    self._owner.push_undo_delete(selected)
                    return
            if key == Qt.Key.Key_Z and (mods & Qt.KeyboardModifier.ControlModifier):
                self._owner.undo()
                return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# 드래그 핸들 (프레임리스 창 이동)
# ---------------------------------------------------------------------------

class _DragBar(QWidget):
    def __init__(self, win: QWidget):
        super().__init__()
        self._win = win
        self._press = None
        self.setFixedHeight(26)
        # plain QWidget은 QSS background-color가 기본 미적용 — 명시적으로 켠다
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._win.move(event.globalPosition().toPoint() - self._press)

    def mouseReleaseEvent(self, event):
        self._press = None


class _ColorPalettePopup(QWidget):
    """무지개 버튼 색 팔레트 팝업. 바깥 클릭 시 자동으로 닫히는 Qt.Popup이며,
    닫힌 시각(hidden_at)을 기록해 '버튼 재클릭=토글 off'를 안정적으로 구현하게 한다
    (팝업이 열린 상태로 버튼을 누르면 Popup이 먼저 닫히므로, 그 직후 재오픈을 막아야 함)."""

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Popup)
        self.hidden_at = 0.0

    def hideEvent(self, event):
        self.hidden_at = time.monotonic()
        super().hideEvent(event)


# ---------------------------------------------------------------------------
# 편집기 다이얼로그
# ---------------------------------------------------------------------------

def flatten_scene_to_png(scene: QGraphicsScene) -> bytes:
    """씬을 이미지 해상도 PNG bytes로 평탄화(주석 포함). 선택 핸들은 렌더 전 해제."""
    scene.clearSelection()
    rect = scene.sceneRect()
    img = QImage(int(round(rect.width())), int(round(rect.height())),
                 QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    scene.render(painter, QRectF(0, 0, img.width(), img.height()), rect)
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


class _EditorMixin:
    """주석 편집 동작(도구·색·두께·스포이드·undo). 호스트 QWidget이 상속해 사용한다.

    호스트가 갖춰야 할 것:
      - self._scene(QGraphicsScene), self._view(_AnnotatorView) — _init_editor_state 전에 생성
      - 시그널 annotated_copy_requested(bytes) / export_file_requested(bytes)
      - 메서드 is_edit_mode()/toggle_edit_mode()/_on_escape()/_win_drag_start/_win_drag_move/
        _win_drag_end/_on_wheel_zoom/close — _AnnotatorView가 호출
    """

    # 마지막으로 쓴 획 두께·글자 크기·번호 크기를 기억 — 새 편집기(다음에 연 이미지)도
    # 기본값이 아니라 이 값으로 시작한다(매번 기본으로 리셋되던 불편 해소, 크기 스테퍼 제거의 근거).
    # DB에도 저장돼 앱 재시작 후에도 유지: 시작 시 main이 load_last_values로 주입,
    # 변경 시 _persist_cb(main 등록)로 DB에 기록. (미등록이면 세션 내 기억만.)
    _last_width = _DEFAULT_WIDTH
    _last_font_size = _DEFAULT_FONT
    _last_badge_size = _DEFAULT_BADGE
    _persist_cb = None   # callable(width, font, badge) → DB 저장 (main이 시작 시 1회 등록)

    @classmethod
    def load_last_values(cls, width, font, badge):
        """앱 시작 시 DB에 저장된 마지막 두께·글자·번호 크기를 주입(파싱실패·범위 밖은 기본값)."""
        cls._last_width = _clamp_int(width, _MIN_WIDTH, _MAX_WIDTH, _DEFAULT_WIDTH)
        cls._last_font_size = _clamp_int(font, _MIN_FONT, _MAX_FONT, _DEFAULT_FONT)
        cls._last_badge_size = _clamp_int(badge, _MIN_BADGE, _MAX_BADGE, _DEFAULT_BADGE)

    def _persist_last_values(self):
        """마지막 값 변경 시 DB에 기록(콜백 미등록이면 세션 내 기억만)."""
        cb = _EditorMixin._persist_cb
        if cb is not None:
            cb(_EditorMixin._last_width, _EditorMixin._last_font_size,
               _EditorMixin._last_badge_size)

    def _init_editor_state(self):
        self.current_tool = "select"
        self.current_color = QColor(_DEFAULT_COLOR)
        self.current_width = _EditorMixin._last_width
        self.current_font_size = _EditorMixin._last_font_size  # 새 텍스트의 기본 글자 크기(pt)
        self.current_badge_size = _EditorMixin._last_badge_size  # 새 번호 마커의 기본 지름(px)
        self.arrow_head_at_end = True
        self.current_text_bg = None  # 새 텍스트의 기본 배경(None=투명)
        self._undo: list[tuple[str, list]] = []
        self._last_move_key = None   # 직전 move undo의 합침 키(연속 화살표키 nudge 병합용)
        self._clip: list = []        # Ctrl+C로 담아둔 주석 복제 템플릿
        self._paste_seq = 0          # 연속 붙여넣기 오프셋 카운터
        # 스포이드 상태
        self._eyedrop_active = False
        self._eyedrop_timer = None
        self._loupe = None
        self._eyedrop_prev_lbtn = False
        self._eyedrop_last = None
        self._tool_buttons: dict[str, QToolButton] = {}
        self._preset_buttons: list[tuple[QColor, QToolButton]] = []

    # ---- 툴바 / 액션바 (호스트가 배치) -------------------------------------
    def _build_toolbar(self) -> QHBoxLayout:
        tools = QHBoxLayout()
        tools.setContentsMargins(6, 2, 6, 2)
        tools.setSpacing(3)

        # 우측 배치는 호스트(chrome_l AlignRight)가 담당 — pill이 내용에 딱 맞게 hug하도록 stretch 없음.

        # 도구 (아이콘)
        group = QButtonGroup(self)
        group.setExclusive(False)  # '0개 선택'(손 모드) 허용 — set_tool이 체크를 직접 관리
        for key, name, sc in _TOOLS:
            btn = QToolButton()
            btn.setIconSize(QSize(18, 18))
            btn.setCheckable(True)
            btn.setToolTip(f"{name} ({sc})")
            # 활성 도구를 다시 누르면 손 모드(None)로 복귀 — 토글.
            btn.clicked.connect(lambda _c, k=key: self.set_tool(None if self.current_tool == k else k))
            group.addButton(btn)
            tools.addWidget(btn)
            self._tool_buttons[key] = btn

        # 되돌리기 — 도구 행 끝(번호 옆)
        undo_btn = QToolButton()
        undo_btn.setIcon(_tool_icon("undo", neutral_override=_ICON_DARK))
        undo_btn.setIconSize(QSize(18, 18))
        undo_btn.setToolTip("되돌리기 (Ctrl+Z)")
        undo_btn.clicked.connect(self.undo)
        tools.addWidget(undo_btn)

        tools.addWidget(self._vsep())

        # 색상: 무지개 버튼 1개 — 클릭하면 프리셋 7색 + 스포이드 팔레트 팝업(공간 절약).
        # 현재 색은 무지개 버튼 가운데 점으로 표시한다.
        self._color_palette = self._build_color_palette()
        self._color_btn = QToolButton()
        self._color_btn.setIcon(_rainbow_icon(self.current_color))
        self._color_btn.setIconSize(QSize(20, 20))
        self._color_btn.setToolTip("색 — 클릭하면 팔레트(프리셋·스포이드)")
        self._color_btn.clicked.connect(self._show_color_palette)
        tools.addWidget(self._color_btn)

        tools.addWidget(self._vsep())

        # 두께 조절은 주석 위에서 휠로 대체(adjust_item_property) — 별도 두께 위젯 제거.

        # 완료 액션 — 아이콘 버튼, 색 옆 고정 (이미지 줌으로 창이 넓어져도 위치 불변).
        # 복사/저장은 같은 중립색으로 통일. 닫기는 이미지 우상단 floating(호스트가 배치).
        copy_btn = QToolButton()
        copy_btn.setIcon(_tool_icon("copy", neutral_override=_ICON_DARK))
        copy_btn.setIconSize(QSize(18, 18))
        copy_btn.setToolTip("복사 — 클립보드에 복사 (히스토리에도 새 항목으로 저장)")
        copy_btn.clicked.connect(self._do_copy)
        tools.addWidget(copy_btn)

        export_btn = QToolButton()
        export_btn.setIcon(_tool_icon("save", neutral_override=_ICON_DARK))
        export_btn.setIconSize(QSize(18, 18))
        export_btn.setToolTip("저장 — PNG 파일로 저장")
        export_btn.clicked.connect(self._do_export)
        tools.addWidget(export_btn)

        # 화살표 방향 토글 — 평소 숨김, 화살표 도구 활성 시 화살표 버튼 아래 floating
        self._arrow_dir_btn = QToolButton(self)
        self._arrow_dir_btn.setIcon(_arrow_dir_icon(self.arrow_head_at_end))
        self._arrow_dir_btn.setIconSize(QSize(24, 18))
        self._arrow_dir_btn.setToolTip("화살표 방향 바꾸기 (선택된 화살표도 뒤집음)")
        self._arrow_dir_btn.clicked.connect(self._toggle_arrow_dir)
        self._arrow_dir_btn.setVisible(False)

        # 텍스트 하위 옵션 바 — 텍스트 도구 활성 시 T 버튼 위에 수평 floating(배경 스와치만).
        # 글자·번호 크기 스테퍼는 제거 — 크기는 주석 위 휠로 조절하고 마지막 값을 기억한다.
        self._text_opts_bar = self._build_text_opts_bar()
        self._text_opts_bar.setVisible(False)
        return tools

    # ---- 색 팔레트 팝업 (무지개 버튼 클릭 시) -------------------------------
    def _build_color_palette(self) -> QWidget:
        """프리셋 7색 + 스포이드를 담은 팝업. 무지개 버튼 클릭 시 아래에 뜨고,
        Popup 플래그라 바깥을 클릭하면 자동으로 닫힌다."""
        pal = _ColorPalettePopup(self)
        pal.setObjectName("colorpalette")
        pal.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        pal.setStyleSheet(
            f"QWidget#colorpalette {{ background-color: {_SURFACE0};"
            f" border: 1px solid {_BORDER}; border-radius: 6px; }}"
            f"QToolButton {{ background-color: {_SURFACE0}; border: 1px solid {_BORDER};"
            f" border-radius: 4px; padding: 2px; }}"
            f"QToolButton:hover {{ background-color: {_SURFACE2}; }}"
        )
        row = QHBoxLayout(pal)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(4)
        for hexs in _COLOR_PRESETS:
            color = QColor(hexs)
            btn = QToolButton()
            btn.setObjectName("swatch")
            btn.setFixedSize(20, 20)
            btn.setCheckable(True)
            btn.setToolTip(hexs)
            btn.setStyleSheet(self._swatch_style(color, False))
            btn.clicked.connect(lambda _c, cc=color: self._pick_palette_color(cc))
            row.addWidget(btn)
            self._preset_buttons.append((color, btn))
        self._eyedrop_btn = QToolButton()
        self._eyedrop_btn.setIcon(_tool_icon("eyedrop"))
        self._eyedrop_btn.setIconSize(QSize(18, 18))
        self._eyedrop_btn.setToolTip("스포이드 — 화면에서 색 따오기 (클릭으로 선택, ESC 취소)")
        self._eyedrop_btn.clicked.connect(self._pick_palette_eyedrop)
        row.addWidget(self._eyedrop_btn)
        pal.adjustSize()
        return pal

    def _show_color_palette(self):
        # 토글: 열려 있으면 닫는다. 또한 팝업이 열린 상태에서 버튼을 누르면 Qt.Popup이
        # 먼저 자동으로 닫히므로(hideEvent), 그 직후(<0.25s) 클릭은 재오픈하지 않아
        # '한 번 더 누르면 사라진다'가 성립한다.
        pal = self._color_palette
        if pal.isVisible():
            pal.hide()
            return
        if time.monotonic() - pal.hidden_at < 0.25:
            return
        pal.adjustSize()
        pos = self._color_btn.mapToGlobal(QPoint(0, self._color_btn.height() + 4))
        pal.move(pos)
        pal.show()
        pal.raise_()
        pal.activateWindow()

    def _pick_palette_color(self, color):
        self._set_color(color)
        self._color_palette.hide()

    def _pick_palette_eyedrop(self):
        self._color_palette.hide()
        self._start_eyedropper()

    def _update_color_btn(self):
        btn = getattr(self, "_color_btn", None)
        if btn is not None:
            btn.setIcon(_rainbow_icon(self.current_color))

    def _build_text_opts_bar(self) -> QWidget:
        bar = QWidget(self)
        bar.setObjectName("textopts")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(5, 3, 5, 3)
        row.setSpacing(4)
        # 배경 스와치 — 투명/흰/회/검/반투명을 모두 펼쳐 한 번에 직접 선택
        self._bg_buttons: list[tuple] = []
        bg_group = QButtonGroup(bar)
        bg_group.setExclusive(True)
        for bg, label in _TEXT_BG_OPTIONS:
            btn = QToolButton()
            btn.setObjectName("bgswatch")
            btn.setCheckable(True)
            btn.setIcon(_bg_swatch_icon(bg))
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(f"텍스트 배경: {label} (선택된 텍스트에도 적용)")
            btn.clicked.connect(lambda _c, b=bg: self._set_text_bg(b))
            bg_group.addButton(btn)
            row.addWidget(btn)
            self._bg_buttons.append((bg, btn))
        bar.adjustSize()
        self._sync_bg_buttons()
        return bar

    def _vsep(self) -> QLabel:
        sep = QLabel()
        sep.setFixedWidth(1)
        # 밝은 툴바 pill 위 구분선 — 옅은 회색(어두운 _BORDER는 밝은 바에서 너무 튐).
        sep.setStyleSheet("background-color: #d0d0d0;")
        return sep

    @staticmethod
    def _swatch_style(color: QColor, selected: bool) -> str:
        border = f"2px solid {_BLUE}" if selected else f"1px solid {_BORDER}"
        return (f"QToolButton#swatch {{ background-color: {color.name()};"
                f" border: {border}; border-radius: 3px; }}")

    def _editor_stylesheet(self, view_border: str) -> str:
        """편집 UI 전체 스타일시트. view_border로 그래픽스뷰(이미지) 테두리 색을 바꿔
        호스트가 활성/비활성 테두리(코랄=활성/회색=비활성)를 표현한다."""
        return f"""
            QWidget {{
                background-color: {_BG};
                color: {_TEXT};
                font-size: 12px;
            }}
            QToolButton#editclose {{
                background-color: rgba(0, 0, 0, 0.45);
                border: none;
                border-radius: 13px;
                padding: 3px;
            }}
            QToolButton#editclose:hover {{ background-color: {_PEACH}; }}
            QToolButton {{
                background-color: {_SURFACE0};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 2px;
            }}
            QToolButton:hover {{ background-color: {_SURFACE2}; }}
            QToolButton:checked {{
                background-color: {_BLUE};
                border: 1px solid {_BLUE};
            }}
            QWidget#textopts {{
                background-color: {_SURFACE0};
                border: 1px solid {_BORDER};
                border-radius: 5px;
            }}
            QToolButton#bgswatch {{
                background-color: {_SURFACE0};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 2px;
            }}
            QToolButton#bgswatch:checked {{
                background-color: {_SURFACE0};
                border: 2px solid {_BLUE};
            }}
            QPushButton {{
                background-color: {_SURFACE0};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{ background-color: {_SURFACE2}; }}
            QPushButton#primary {{
                background-color: {_BLUE};
                color: {_BG};
                border: 1px solid {_BLUE};
            }}
            QGraphicsView {{
                background-color: {_SURFACE0};
                border: 2px solid {view_border};
            }}
        """

    # ---- 도구/색/두께 상태 -------------------------------------------------
    def set_tool(self, tool):
        self.current_tool = tool
        if tool == "select":
            self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        # 버튼 체크 상태 직접 관리(그룹 비배타) — 손 모드(None)면 전부 해제.
        for k, b in self._tool_buttons.items():
            if b.isChecked() != (k == tool):
                b.setChecked(k == tool)
        # 도구 기본 커서 — hover 이벤트 전 stale 방지(주석 위 SizeAll은 다음 move에서 갱신)
        self._view.viewport().setCursor(
            Qt.CursorShape.OpenHandCursor if tool is None
            else Qt.CursorShape.ArrowCursor if tool == "select"
            else Qt.CursorShape.IBeamCursor if tool == "text"
            else Qt.CursorShape.CrossCursor
        )
        # 선택 항목 repaint — 핸들이 선택(V) 도구에서만 보이므로 도구 전환 시 즉시 반영
        for it in self._scene.selectedItems():
            it.update()
        self._update_arrow_dir_btn()
        self._update_text_opts_bar()

    def _update_text_opts_bar(self):
        """텍스트 도구가 활성이고 편집 모드일 때만 T 버튼 위에 텍스트 옵션 바 floating."""
        bar = getattr(self, "_text_opts_bar", None)
        if bar is None:
            return
        edit = self.is_edit_mode() if hasattr(self, "is_edit_mode") else True
        if self.current_tool == "text" and edit:
            text_btn = self._tool_buttons.get("text")
            if text_btn is not None:
                bar.adjustSize()
                # 툴바가 창 하단이라 버튼 '위'로 띄운다(아래면 창 밖으로 잘림).
                bar.move(text_btn.mapTo(self, QPoint(0, -bar.height() - 2)))
            bar.setVisible(True)
            bar.raise_()
        else:
            bar.setVisible(False)

    def _set_text_bg(self, bg):
        self.current_text_bg = QColor(bg) if bg is not None else None
        self._sync_bg_buttons()
        # 작성 중인 텍스트 우선, 없으면 선택된 텍스트에 즉시 적용(글자 크기와 동일 대상 규칙).
        for it in self._font_size_targets():
            it.set_bg(self.current_text_bg)

    def _sync_bg_buttons(self):
        """현재 배경(current_text_bg)에 해당하는 스와치만 체크 표시."""
        cur = self.current_text_bg
        for bg, btn in getattr(self, "_bg_buttons", []):
            same = (bg is None and cur is None) or (
                bg is not None and cur is not None and QColor(bg) == QColor(cur))
            btn.setChecked(same)

    def _update_arrow_dir_btn(self):
        """방향 토글 버튼 배치: 선택된 화살표가 있으면 그 화살표 근처에(대상에서 멀지 않게),
        없고 화살표 도구가 활성이면 툴바 화살표 버튼 아래(새 화살표 기본 방향 토글)."""
        btn = getattr(self, "_arrow_dir_btn", None)
        if btn is None:
            return
        edit = self.is_edit_mode() if hasattr(self, "is_edit_mode") else True
        if not edit:
            btn.setVisible(False)
            return
        sel_arrows = [it for it in self._scene.selectedItems() if isinstance(it, _ArrowItem)]
        if sel_arrows:
            arrow = sel_arrows[0]
            # 화살표 중간점을 호스트(창) 좌표로 변환해 그 위쪽에 버튼 배치(대상 근처).
            scene_mid = arrow.mapToScene(arrow._point_at(0.5))
            vp_pt = self._view.mapFromScene(scene_mid)
            host = self.mapFromGlobal(self._view.viewport().mapToGlobal(vp_pt))
            btn.setIcon(_arrow_dir_icon(arrow._head_at_end))  # 그 화살표의 실제 방향 표시
            btn.resize(32, 24)
            x = max(2, min(host.x() + 12, self.width() - btn.width() - 2))
            y = max(2, min(host.y() - btn.height() - 12, self.height() - btn.height() - 2))
            btn.move(x, y)
            btn.setVisible(True)
            btn.raise_()
            return
        if self.current_tool == "arrow":
            arrow_btn = self._tool_buttons.get("arrow")
            if arrow_btn is not None:
                btn.resize(arrow_btn.width(), 22)
                # 툴바가 창 하단이라 버튼 '위'로 띄운다(아래면 창 밖으로 잘림).
                btn.move(arrow_btn.mapTo(self, QPoint(0, -btn.height() - 2)))
            btn.setIcon(_arrow_dir_icon(self.arrow_head_at_end))
            btn.setVisible(True)
            btn.raise_()
            return
        btn.setVisible(False)

    def make_pen(self) -> QPen:
        return QPen(self.current_color, self.current_width, Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

    def next_badge_number(self) -> int:
        # 씬에 남은 번호 마커의 최대값+1 (삭제 후 재생성 시 빈 번호를 다시 씀)
        nums = [it._number for it in self._scene.items() if isinstance(it, _BadgeItem)]
        return max(nums, default=0) + 1

    def _refresh_tool_icons(self):
        for key, btn in self._tool_buttons.items():
            btn.setIcon(_tool_icon(key, self.current_color, neutral_override=_ICON_DARK))

    def _set_color(self, color: QColor):
        self.current_color = QColor(color)
        # 현재 색은 무지개 버튼 가운데 점으로 표시(팔레트 팝업 진입점)
        self._update_color_btn()
        name = self.current_color.name().lower()
        for c, btn in self._preset_buttons:
            sel = c.name().lower() == name
            btn.setChecked(sel)
            btn.setStyleSheet(self._swatch_style(c, sel))
        self._refresh_tool_icons()
        # 선택된 도형이 있으면 그 색도 즉시 변경
        for it in self._scene.selectedItems():
            if hasattr(it, "apply_color"):
                it.apply_color(self.current_color)

    def _font_size_targets(self) -> list:
        fi = self._scene.focusItem()
        if isinstance(fi, _TextItem) and \
                fi.textInteractionFlags() != Qt.TextInteractionFlag.NoTextInteraction:
            return [fi]  # 작성 중인 텍스트만 — 기존 선택 텍스트가 같이 커지지 않게
        return [it for it in self._scene.selectedItems() if isinstance(it, _TextItem)]

    def adjust_item_property(self, item, step: int):
        """주석 위 휠 — 도형은 두께(±1), 텍스트·번호는 크기(±2)를 step 방향으로 조절.
        조절값을 도구 기본값·툴바에도 반영해 다음에 그리는 주석도 같은 두께·크기가 되게 한다
        (undo는 색·두께 변경과 동일하게 미추적)."""
        if isinstance(item, _TextItem):
            new = max(_MIN_FONT, min(item.font().pointSize() + step * 2, _MAX_FONT))
            item.apply_font_size(new)
            self.current_font_size = new
            _EditorMixin._last_font_size = new   # 마지막 글자 크기 기억 → 다음 편집기도 이 값으로
        elif isinstance(item, _BadgeItem):
            cur = round(item.scale() * _DEFAULT_BADGE)
            new = max(_MIN_BADGE, min(cur + step * 2, _MAX_BADGE))
            item.setScale(new / float(_DEFAULT_BADGE))
            self.current_badge_size = new
            _EditorMixin._last_badge_size = new  # 마지막 번호 크기 기억 → 다음 편집기도 이 값으로
        else:
            if isinstance(item, _ArrowItem):
                new = max(_MIN_WIDTH, min(item._width + step, _MAX_WIDTH))
            elif hasattr(item, "apply_width") and hasattr(item, "pen"):
                new = max(_MIN_WIDTH, min(int(round(item.pen().widthF())) + step, _MAX_WIDTH))
            else:
                return
            item.apply_width(new)
            self.current_width = new
            _EditorMixin._last_width = new   # 마지막 두께 기억 → 다음 편집기도 이 값으로 시작
        self._persist_last_values()   # 변경된 마지막 값을 DB에 기록(재시작 후 유지)

    def _toggle_arrow_dir(self):
        # 선택된 화살표가 있으면 각자 자기 방향을 뒤집고 기본값·아이콘을 첫 화살표에 맞춘다.
        # 없으면 새 화살표 기본 방향만 토글.
        sel = [it for it in self._scene.selectedItems() if isinstance(it, _ArrowItem)]
        if sel:
            for it in sel:
                it.flip_head()
            self.arrow_head_at_end = sel[0]._head_at_end
        else:
            self.arrow_head_at_end = not self.arrow_head_at_end
        self._arrow_dir_btn.setIcon(_arrow_dir_icon(self.arrow_head_at_end))

    # ---- 스포이드 (화면 픽셀 색 따오기) ------------------------------------
    def _start_eyedropper(self):
        if self._eyedrop_active:
            return
        import ctypes
        # 로컬 WinDLL 인스턴스 — 핸들 안전 restype/argtypes를 지정해도 전역
        # ctypes.windll.user32(paste_interceptor 등 공유)에 영향을 주지 않는다.
        # 64비트 Windows에서 HDC는 64비트이므로 기본 restype(c_int)이면 핸들이 잘린다.
        self._user32 = ctypes.WinDLL("user32")
        self._gdi32 = ctypes.WinDLL("gdi32")
        self._user32.GetDC.restype = ctypes.c_void_p
        self._user32.GetDC.argtypes = [ctypes.c_void_p]
        self._user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._gdi32.GetPixel.restype = ctypes.c_uint  # COLORREF
        self._gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

        self._eyedrop_active = True
        self._eyedrop_last = None
        self._loupe = _ColorLoupe()
        self._loupe.show()
        self._eyedrop_prev_lbtn = bool(self._user32.GetAsyncKeyState(0x01) & 0x8000)
        self._eyedrop_timer = QTimer(self)
        self._eyedrop_timer.setInterval(25)
        self._eyedrop_timer.timeout.connect(self._eyedrop_tick)
        self._eyedrop_timer.start()

    def _eyedrop_tick(self):
        import ctypes
        from ctypes import wintypes
        user32 = self._user32
        gdi32 = self._gdi32

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        hdc = user32.GetDC(None)
        cref = gdi32.GetPixel(hdc, pt.x, pt.y)
        user32.ReleaseDC(None, hdc)
        if cref != 0xFFFFFFFF:  # CLR_INVALID
            r = cref & 0xFF
            g = (cref >> 8) & 0xFF
            b = (cref >> 16) & 0xFF
            col = QColor(r, g, b)
            self._eyedrop_last = col
            if self._loupe is not None:
                self._loupe.set_color(col)
                gp = QCursor.pos()
                self._loupe.move(gp.x() + 18, gp.y() + 18)

        if (user32.GetAsyncKeyState(0x1B) & 0x8000) or (user32.GetAsyncKeyState(0x02) & 0x8000):
            self._stop_eyedropper(False)
            return
        lbtn = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
        if lbtn and not self._eyedrop_prev_lbtn:
            self._stop_eyedropper(True)
            return
        self._eyedrop_prev_lbtn = lbtn

    def _stop_eyedropper(self, picked: bool):
        self._eyedrop_active = False
        if self._eyedrop_timer is not None:
            self._eyedrop_timer.stop()
            self._eyedrop_timer = None
        if self._loupe is not None:
            self._loupe.close()
            self._loupe = None
        if picked and self._eyedrop_last is not None:
            self._set_color(self._eyedrop_last)
        self.activateWindow()
        self.raise_()

    # ---- Undo --------------------------------------------------------------
    def push_undo_add(self, item: QGraphicsItem):
        self._undo.append(("add", [item]))

    def push_undo_delete(self, items: list):
        self._undo.append(("delete", list(items)))

    def push_undo_move(self, pairs: list, coalesce_key=None):
        """이동(pos 변경) 되돌리기 기록. pairs=[(item, 이동 전 QPointF), ...].
        coalesce_key가 직전 move와 같으면(연속 화살표키 nudge) 새 항목을 쌓지 않아
        undo 폭주를 막는다 — 기존 항목이 더 오래된(원래) 위치를 이미 보유하므로."""
        if not pairs:
            return
        if coalesce_key is not None and self._undo \
                and self._undo[-1][0] == "move" and self._last_move_key == coalesce_key:
            return
        self._undo.append(("move", pairs))
        self._last_move_key = coalesce_key

    def undo(self):
        # 이미 사라진 빈 텍스트의 "add"처럼 무의미한 항목은 건너뛰고 실제 동작 1건을 되돌린다.
        self._last_move_key = None  # undo 후엔 다음 nudge를 새 그룹으로(합침 끊기)
        while self._undo:
            action, items = self._undo.pop()
            if action == "add":
                removed = [it for it in items if it.scene() is not None]
                for it in removed:
                    self._scene.removeItem(it)
                if removed:
                    return
                continue
            if action == "delete":
                for it in items:
                    self._scene.addItem(it)
                return
            if action == "move":
                # items = [(item, 이동 전 pos)]. 씬에 남은 항목만 원위치로.
                restored = False
                for it, old_pos in items:
                    if it.scene() is not None:
                        it.setPos(old_pos)
                        restored = True
                if restored:
                    return
                continue

    # ---- 복사 / 붙여넣기 (주석 내부 복제, OS 클립보드 아님) ------------------
    def copy_selection(self):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "clone")]
        if not sel:
            return
        self._clip = [it.clone() for it in sel]  # 분리된 클론을 템플릿으로 보관
        self._paste_seq = 0

    def paste_selection(self):
        if not self._clip:
            return
        self._scene.clearSelection()
        self._paste_seq += 1
        off = QPointF(12 * self._paste_seq, 12 * self._paste_seq)
        pasted = []
        for template in self._clip:
            it = template.clone()  # 반복 붙여넣기를 위해 템플릿에서 매번 새로 복제
            it.setPos(it.pos() + off)
            self._scene.addItem(it)
            if isinstance(it, _BadgeItem):
                it._number = self.next_badge_number()  # 중복 번호 방지(추가 후 계산)
                it.update()
            it.setSelected(True)
            pasted.append(it)
        if pasted:
            self._undo.append(("add", pasted))

    # ---- 완료 액션 (호스트 시그널 emit) ------------------------------------
    def _do_copy(self):
        self.annotated_copy_requested.emit(flatten_scene_to_png(self._scene))

    def _do_export(self):
        self.export_file_requested.emit(flatten_scene_to_png(self._scene))

    # ---- 키 / 생명주기 -----------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self._eyedrop_active:
                self._stop_eyedropper(False)
            else:
                self.close()
            return
        if event.key() == Qt.Key.Key_Z and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.undo()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._eyedrop_active:
            self._stop_eyedropper(False)
        type(self)._instances = [d for d in type(self)._instances if d is not self]
        super().closeEvent(event)
