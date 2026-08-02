"""캔버스 코어 상수·아이콘·기본 헬퍼 — annotator_core.py(8169줄) 2026-08-02 분할분.

도구/색/크기 기본값, 그리드 상수, base64 픽스맵 인코딩, 아이콘·커서 팩토리를 모은
잎(leaf) 모듈 — 다른 core 서브모듈에만 쓰이고 이쪽은 그것들을 가져오지 않는다.
"""
import heapq
import io
import math
import struct
import sys
import uuid
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QLineF, QSize, QTimer, QEvent,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QBrush, QColor, QPainterPath,
    QPainterPathStroker, QPolygonF, QFont, QFontMetricsF, QIcon, QCursor,
    QConicalGradient,
)
from PyQt6.QtSvg import QSvgRenderer
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


_MIN_WIDTH, _MAX_WIDTH, _DEFAULT_WIDTH = 1, 40, 1
_MIN_FONT, _MAX_FONT, _DEFAULT_FONT = 2, 200, 16  # 휠 축소 하한을 2pt로(그 이하는 크기조절 점)
# 번호 마커 지름(px). 기본 30 = _BadgeItem._R(15) * 2, scale 1.0에 대응.
_MIN_BADGE, _MAX_BADGE, _DEFAULT_BADGE = 12, 120, 30

# [그리드/스냅투그리드] 씬 단위 고정 간격(줌에 비례해 화면 밀도가 변함 — CAD/Figma 관행).
# 표시(점)와 스냅은 하나의 토글(Shift+G, owner.grid_enabled)로 묶여 있다. 너무 촘촘해지면
# (_GRID_MIN_PX 미만) 자동으로 숨기고, 뷰 크기·줌 조합이 극단적이어도 프레임 랙이 없도록
# 그릴 점 개수 상한(_GRID_MAX_DOTS)을 세이프가드로 둔다(둘 다 조용히 숨김 — 사용자 설정 아님).
_GRID_SPACING = 20.0
_GRID_MIN_PX = 4.0
_GRID_MAX_DOTS = 6000
_GRID_DOT_RGBA = (150, 150, 150, 115)


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
# 아이콘 (SVG 래스터화 — 2026-08-02 디자인 베이크오프 2라운드: 코랄 듀오톤 외곽선+포인트
# 채움 스타일 확정, SVG는 easycad/resources/icons/<name>.svg에 저장. [같은 날 4차 피드백]
# 상단바 전체가 코랄이면 "진짜 활성 상태"(checked)의 신호력이 떨어진다는 지적으로, 아이콘
# 색은 도형 팔레트와 같은 테마 적응 중립색으로 다시 바꿨다 — SVG 파일 자체는 여전히 코랄로
# 그려져 있지만(모양=외곽선+포인트 채움 구조는 색과 무관하게 유지), 렌더 시 `color` 인자를
# 주면 픽셀 루프로 그 색 하나로 통째로 재칠한다(파일을 두 벌 관리하거나 SVG 안에 currentColor를
# 쓰는 대신, 이미 있는 파일을 그대로 두고 픽스맵 단계에서 재칠 — 듀오톤의 "외곽선/채움 비중
# 차이"는 알파(선폭·불투명도)로 이미 표현돼 있어 단색으로 재칠해도 형태 구분은 그대로 남는다.
# QPainter 합성모드 대신 픽셀 루프를 쓰는 이유는 `_svg_icon_pixmap`의 함정 주석 참조).
# ---------------------------------------------------------------------------

def _icons_dir() -> Path:
    """resources/icons 폴더 경로 — 개발 실행과 (미래) PyInstaller 프리즌 빌드 양쪽 대응.
    현재 이 프로젝트는 PyInstaller로 패키징하지 않는다(스펙 파일 없음) — sys._MEIPASS
    분기는 나중에 패키징이 붙을 때를 위한 최소 대비일 뿐, 지금은 else 경로만 실제로 탄다."""
    base = Path(sys._MEIPASS) if hasattr(sys, "_MEIPASS") else Path(__file__).resolve().parents[1]
    return base / "resources" / "icons"


def _svg_icon_pixmap(name: str, size: int = 22, color: QColor | None = None) -> QPixmap:
    """resources/icons/<name>.svg를 size×size로 래스터화한 QPixmap(캐시 없음 — 호출부가
    비활성 상태용 흐린 사본 등을 더 만들 수 있어 QIcon 캐시(`_svg_icon`)와 분리).
    `color`를 주면 SVG 파일 자체의 색(코랄)과 무관하게 그 색 하나로 재칠(형태는 알파로 유지).

    ⚠ [2026-08-02 세그폴트 수정, 스턱루프 규칙 11-b] 재칠은 픽셀 루프로 한다(QPainter
    합성모드 금지) — `python tests/test_easycad.py` 전체 실행(짧은 시간에 CanvasWindow
    수십 개 생성) 중 재현 가능한 네이티브 세그폴트를 만났다. 5회 반복 재현 스크립트로
    이분탐색한 결과, 원인은 재칠 "여부"나 "빈도"가 아니라 **QPainter의 합성모드
    (CompositionMode_SourceIn/DestinationIn) 자체**였다 — QPixmap 2장 방식, QImage
    한 장으로 축소, premultiplied↔non-premultiplied 포맷 전환까지 4가지 변형을 각각
    5회씩 테스트했지만 전부 재현됐고(색을 고정 단일값으로 캐시 다양성을 없애도 재현 —
    "캐시된 픽스맵 개수" 가설도 기각), **합성모드를 아예 안 쓰고 `QImage.setPixelColor`
    픽셀 루프로 바꾼 버전만 5/5 통과**했다. 즉 이 환경(오프스크린 플랫폼 플러그인)에서
    `QPainter` 합성모드가 반복적인 SVG 렌더와 얽힐 때 불안정한 것으로 보인다(정확한
    Qt/PyQt6 내부 원인은 확인 못 함 — `Not-tested`). 아이콘이 22~24px라 픽셀 루프
    비용은 무시 가능(호출 자체도 `_svg_icon`/`_act_icon` 캐시로 사실상 1회성)."""
    renderer = QSvgRenderer(str(_icons_dir() / f"{name}.svg"))
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    if color is not None:
        c = QColor(color)
        r, g, b = c.red(), c.green(), c.blue()
        for y in range(size):
            for x in range(size):
                a = img.pixelColor(x, y).alpha()
                if a:
                    img.setPixelColor(x, y, QColor(r, g, b, a))
    return QPixmap.fromImage(img)


_SVG_ICON_CACHE: dict[tuple, QIcon] = {}


def _svg_icon(name: str, size: int = 22, color: QColor | None = None) -> QIcon:
    """resources/icons/<name>.svg를 size×size(+선택적 재칠 색)로 래스터화해 QIcon으로(결과
    캐시 — 캐시 키에 색을 포함해 테마별로 별도 캐시된다)."""
    key = (name, size, QColor(color).name() if color is not None else None)
    icon = _SVG_ICON_CACHE.get(key)
    if icon is not None:
        return icon
    icon = QIcon(_svg_icon_pixmap(name, size, color))
    _SVG_ICON_CACHE[key] = icon
    return icon


# _tool_icon이 실제로 받는 도구 이름 전부(상단 툴바 6종 + 화살표 종류전환용 sarrow).
_TOOL_ICON_NAMES = frozenset({"select", "arrow", "text", "line", "pen", "badge", "sarrow"})


def _tool_icon(tool: str, color: QColor | None = None) -> QIcon:
    return _svg_icon(tool, 22, color)


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


def _view_zoom_factor(item) -> float:
    """[2026-07-29] 실사용 피드백 — 휠줌 시 선택박스·핸들 두께가 도면과 함께 커져서
    화면상 부담스러워졌다. 원인: `_scale_or_1()`이 아이템 자체의 `.scale()`(보통 1.0)만
    보고 뷰의 줌 배율은 무시해, 줌해도 화면 픽셀 크기가 그대로 늘어났다(선택박스만 예외적으로
    작아 보이는 게 아니라 도형과 '똑같이' 커지는 게 문제). 해법: 이 아이템이 그려지는
    '상호작용 가능한' 뷰(메인 캔버스 — 미니맵은 `setInteractive(False)`라 클릭·선택이
    없어 제외)의 현재 줌 배율을 함께 곱해, `_EDGE_HIT_MIN`/핸들 크기 등 화면-px 기준
    상수들이 줌과 무관하게 화면에서 항상 같은 크기로 보이게 한다(Figma·AutoCAD 관례).
    뷰가 없으면(뷰 미부착 QGraphicsScene 단독 오프스크린 테스트 등) 1.0 — 기존 동작 그대로.

    [성능 조사 스파이크 2026-07-30 실측] 이 함수는 boundingRect()(Qt가 트랜스폼 변경 시
    아이템마다 여러 번 재조회)를 통해 간접 호출돼, 무거운 도면(~800개)에서 줌 20틱에
    287,950회 호출됐다(cProfile 실측 — boundingRect 체인이 전체 줌 비용의 70%+ 차지).
    `sc.views()` 순회+`isInteractive()` 필터링이 매번 반복되는 게 비용의 핵심 — 상호작용
    가능한 뷰는 CanvasWindow 생애주기 동안 사실상 고정이므로(재부착 없음) 씬에 발견한 뷰를
    캐시해 그 순회를 생략한다. `.transform().m11()`은 캐시하지 않고 매번 새로 읽어(줌 값 자체는
    항상 최신 — staleness 없음), 캐시가 잘못돼도 최악의 경우 '뷰 재탐색'(느려질 뿐 틀리지 않음)."""
    sc = item.scene()
    if sc is None:
        return 1.0
    cached = getattr(sc, "_interactive_view_cache", None)
    if cached is not None:
        try:
            if cached.scene() is sc:
                m = cached.transform().m11()
                return m if m else 1.0
        except RuntimeError:
            pass   # 캐시된 뷰가 Qt 쪽에서 이미 삭제됨 — 아래 재탐색으로 폴백
    for v in sc.views():
        if v.isInteractive():
            sc._interactive_view_cache = v
            m = v.transform().m11()
            return m if m else 1.0
    return 1.0


# ---------------------------------------------------------------------------
# 크기조절 핸들 믹스인 — 선택 시 우하단 핸들 드래그로 균일 스케일
# ---------------------------------------------------------------------------



# `from easycad.canvas.core_constants import *`가 밑줄 접두 이름(거의 전부)까지 넘겨받게
# 강제 — __all__ 없으면 import *는 밑줄 시작 이름을 기본적으로 제외한다.
__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
