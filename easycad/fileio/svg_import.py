"""SVG 가져오기 — 외부(손으로 그리거나 AI로 생성한) SVG를 우리 앱 네이티브 벡터 아이템
(line/rect/ellipse/path/text)으로 변환한다. dxf_import.py와 같은 취지(§8 항목8 커스텀 심볼
팔레트의 등록 대상 확장) — 래스터로 박아넣지 않고 실제 지오메트리로 들여와야 테마 적응
잉크색·리사이즈·펜 두께 편집이 다른 도형과 동일하게 된다.

색은 일부러 안 읽는다(텍스트 제외) — 원본 stroke/fill을 따라가면 다크 캔버스에서 안 보이거나
앱의 잉크색 관례(테마 적응)와 어긋난다. 좌표(geometry)만 가져오고 펜은 항상 호출부
(host_fileio._insert_svgs_at)가 현재 그리기색으로 입힌다 — 그래야 어떤 SVG를 넣어도 다른
손그림 도형과 시각적으로 통일된다. 배치 스케일·이동(sx/sy/dx/dy)은 DXF import의 `_uf()`와
같은 패턴 — 좌표를 읽는 시점에 바로 적용해, 나중에 아이템 종류별 재베이크 API 차이에
기대지 않는다.

지원 요소: <line>·<rect>·<circle>·<ellipse>·<polyline>·<polygon>·<text>(색만)·
<path>(M/L/H/V/Q/C/S/T/A/Z, 대소문자=절대/상대 — A는 SVG 표준 끝점→중심 매개변수 변환 후
3차 베지어로 근사, S/T는 반사 제어점 계산까지 구현). 미지원(스코프 밖 — 실사용 세트가
transform 없는 평평한 구조라 우선순위 낮음, 2026-08-04 실제 Lucid export로 확인):
<g transform=…>·중첩 변환·<use>+<defs>(Lucid가 텍스트를 벡터 글리프로 내보낼 때 씀)·
그라디언트/클립·flag가 공백/쉼표 없이 붙어 쓰인 arc(예 "01" 한 토큰). 이런 요소는 조용히
건너뛰고 나머지는 계속 변환한다(전부 실패 대신 부분 성공) — 단 인식 못 하는 path 커맨드
문자를 만나면 토큰화 자체가 깨지지 않도록 그 지점까지만 쓰고 서브패스를 끊는다(과거
버그: 인식 못 하는 글자가 토큰 목록에서 통째로 사라져 이후 좌표가 밀리며 훨씬 뒤에서
엉뚱한 ValueError로 터졌다 — 실제 Lucid 파일의 "S" 커맨드로 재현·수정)."""
import math
import re
import xml.etree.ElementTree as ET

from PyQt6.QtCore import QRectF, QLineF, QPointF
from PyQt6.QtGui import QPainterPath, QColor

from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _PolygonItem, _TextItem,
)

_NS = "{http://www.w3.org/2000/svg}"
_PATH_TOKEN_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def _f(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _parse_viewbox(root) -> QRectF:
    vb = root.get("viewBox")
    if vb:
        parts = re.split(r"[\s,]+", vb.strip())
        if len(parts) == 4:
            return QRectF(_f(parts[0]), _f(parts[1]), _f(parts[2]), _f(parts[3]))
    return QRectF(0, 0, _f(root.get("width"), 100.0), _f(root.get("height"), 100.0))


def _arc_to_beziers(x0, y0, rx, ry, phi_deg, large_arc, sweep, x, y):
    """SVG 끝점 매개변수 타원호 → 3차 베지어 세그먼트 리스트[(c1,c2,end), ...] (원본 좌표계).
    SVG 1.1 스펙 부록 F.6(끝점→중심 매개변수 변환) 표준 절차 — 이 앱에 이미 있는 코드 없음
    (DXF import는 원호를 ezdxf가 이미 처리해 주므로 자체 변환기가 없었다), 여기서 처음 필요."""
    if rx == 0 or ry == 0 or (x0 == x and y0 == y):
        return [((x0, y0), (x, y), (x, y))]  # 퇴화 — 직선으로 취급
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg % 360)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x0 - x) / 2.0, (y0 - y) / 2.0
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2
    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s; ry *= s
    sign = -1.0 if large_arc == sweep else 1.0
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = sign * math.sqrt(max(num, 0.0) / den) if den > 0 else 0.0
    cxp = co * (rx * y1p / ry)
    cyp = co * (-ry * x1p / rx)
    ccx = cos_phi * cxp - sin_phi * cyp + (x0 + x) / 2.0
    ccy = sin_phi * cxp + cos_phi * cyp + (y0 + y) / 2.0

    def ang(ux, uy, vx, vy):
        length = math.hypot(ux, uy) * math.hypot(vx, vy)
        a = math.acos(max(-1.0, min(1.0, (ux * vx + uy * vy) / length))) if length else 0.0
        return a if (ux * vy - uy * vx) >= 0 else -a

    theta1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi

    n_seg = max(1, int(math.ceil(abs(dtheta) / (math.pi / 2))))
    seg_theta = dtheta / n_seg
    k = 4.0 / 3.0 * math.tan(seg_theta / 4.0)

    def ellipse_pt(ct, st):
        return (ccx + rx * ct * cos_phi - ry * st * sin_phi,
                ccy + rx * ct * sin_phi + ry * st * cos_phi)

    def ellipse_deriv(ct, st):
        return (-rx * st * cos_phi - ry * ct * sin_phi,
                -rx * st * sin_phi + ry * ct * cos_phi)

    segs = []
    theta = theta1
    for _ in range(n_seg):
        theta_next = theta + seg_theta
        c1a, s1a = math.cos(theta), math.sin(theta)
        c2a, s2a = math.cos(theta_next), math.sin(theta_next)
        p_start, p_end = ellipse_pt(c1a, s1a), ellipse_pt(c2a, s2a)
        d1x, d1y = ellipse_deriv(c1a, s1a)
        d2x, d2y = ellipse_deriv(c2a, s2a)
        c1 = (p_start[0] + k * d1x, p_start[1] + k * d1y)
        c2 = (p_end[0] - k * d2x, p_end[1] - k * d2y)
        segs.append((c1, c2, p_end))
        theta = theta_next
    return segs


def _parse_path_d(d: str, sx: float, sy: float, dx: float, dy: float) -> QPainterPath:
    """SVG path 'd' 문자열 → QPainterPath, 좌표는 (x*sx+dx, y*sy+dy)로 즉시 배치 변환해 담는다.
    S/T(스무스 곡선)의 반사 제어점은 원본(비스케일) 좌표계에서 계산한 뒤 put()으로 배치한다
    — 직전 명령이 같은 계열(C/S 또는 Q/T)일 때만 반사, 아니면 현재점을 제어점으로 쓴다
    (SVG 1.1 스펙 §8.3.6/§8.3.7)."""
    path = QPainterPath()
    toks = [g[0] or g[1] for g in _PATH_TOKEN_RE.findall(d)]
    i, n = 0, len(toks)
    cx = cy = start_x = start_y = 0.0
    last_c2 = None   # 직전 C/S의 두 번째 제어점(원본 좌표) — S 반사용
    last_q1 = None   # 직전 Q/T의 제어점(원본 좌표) — T 반사용
    cmd = None

    def nextf():
        nonlocal i
        v = float(toks[i]); i += 1
        return v

    def put(px, py):
        return px * sx + dx, py * sy + dy

    while i < n:
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
        if cmd is None:
            break
        c = cmd.upper()
        rel = cmd.islower()
        if c != "S":
            last_c2 = None   # 계열이 끊기면 다음 S는 반사 없이 현재점 기준
        if c != "T":
            last_q1 = None
        if c == "M":
            x, y = nextf(), nextf()
            if rel:
                x += cx; y += cy
            path.moveTo(*put(x, y))
            cx, cy = x, y
            start_x, start_y = x, y
            cmd = "l" if rel else "L"   # SVG 스펙: M 뒤 추가 좌표쌍은 암묵적 LineTo
        elif c == "L":
            x, y = nextf(), nextf()
            if rel:
                x += cx; y += cy
            path.lineTo(*put(x, y))
            cx, cy = x, y
        elif c == "H":
            x = nextf()
            if rel:
                x += cx
            path.lineTo(*put(x, cy))
            cx = x
        elif c == "V":
            y = nextf()
            if rel:
                y += cy
            path.lineTo(*put(cx, y))
            cy = y
        elif c == "Q":
            x1, y1, x, y = nextf(), nextf(), nextf(), nextf()
            if rel:
                x1 += cx; y1 += cy; x += cx; y += cy
            path.quadTo(*put(x1, y1), *put(x, y))
            cx, cy = x, y
            last_q1 = (x1, y1)
        elif c == "T":
            x, y = nextf(), nextf()
            if rel:
                x += cx; y += cy
            x1, y1 = (2 * cx - last_q1[0], 2 * cy - last_q1[1]) if last_q1 else (cx, cy)
            path.quadTo(*put(x1, y1), *put(x, y))
            cx, cy = x, y
            last_q1 = (x1, y1)
        elif c == "C":
            x1, y1, x2, y2, x, y = (nextf() for _ in range(6))
            if rel:
                x1 += cx; y1 += cy; x2 += cx; y2 += cy; x += cx; y += cy
            path.cubicTo(*put(x1, y1), *put(x2, y2), *put(x, y))
            cx, cy = x, y
            last_c2 = (x2, y2)
        elif c == "S":
            x2, y2, x, y = nextf(), nextf(), nextf(), nextf()
            if rel:
                x2 += cx; y2 += cy; x += cx; y += cy
            x1, y1 = (2 * cx - last_c2[0], 2 * cy - last_c2[1]) if last_c2 else (cx, cy)
            path.cubicTo(*put(x1, y1), *put(x2, y2), *put(x, y))
            cx, cy = x, y
            last_c2 = (x2, y2)
        elif c == "A":
            rx, ry, rot = nextf(), nextf(), nextf()
            large_arc, sweep = nextf(), nextf()
            x, y = nextf(), nextf()
            if rel:
                x += cx; y += cy
            for c1, c2, end in _arc_to_beziers(cx, cy, rx, ry, rot, large_arc != 0, sweep != 0, x, y):
                path.cubicTo(*put(*c1), *put(*c2), *put(*end))
            cx, cy = x, y
        elif c == "Z":
            path.closeSubpath()
            cx, cy = start_x, start_y
        else:
            break   # 미지원 커맨드 — 이 서브패스는 여기서 멈추고 지금까지만 사용(전부 실패 대신 부분 성공)
    return path


def _parse_points(s: str):
    nums = [float(t) for t in re.findall(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?", s or "")]
    return list(zip(nums[0::2], nums[1::2]))


def parse_svg_items(path: str, long_side: float | None = None, center=None):
    """SVG 파일 → (아이템 리스트, viewBox). 나머지는 `_parse_svg_root` 참조."""
    root = ET.parse(path).getroot()
    return _parse_svg_root(root, long_side, center)


def parse_svg_string(text: str, long_side: float | None = None, center=None):
    """SVG 문자열(파일 없이 메모리 상의 텍스트, 예: AI 게이트웨이 응답) → (아이템 리스트,
    viewBox) — §8 항목20 B단계, `parse_svg_items`와 동일 동작을 `ET.fromstring`으로."""
    root = ET.fromstring(text)
    return _parse_svg_root(root, long_side, center)


def _parse_svg_root(root, long_side: float | None, center):
    """`parse_svg_items`/`parse_svg_string` 공통 본문. `long_side`/`center`를 주면 viewBox의
    긴 변이 `long_side`(씬 단위)가 되도록 축소하고 그 중심이 `center`(QPointF, 씬 좌표)에
    오도록 배치까지 좌표를 읽는 시점에 끝마친다(DXF import `_uf()`와 동일 패턴) — 둘 다
    None이면 변환 없이 원본 SVG 좌표 그대로(단위 테스트·좌표 확인용). 펜·플래그는 호출부
    (host_fileio._insert_svgs_at/_svg_text_to_items)가 마저 채운다. viewBox는 원본
    좌표계 참고용으로 그대로 반환한다(반환값 자체는 이미 배치가 끝난 좌표라 호출부가
    다시 옮기지 않는다)."""
    vb = _parse_viewbox(root)
    if long_side is not None and center is not None and max(vb.width(), vb.height()) > 0:
        s = long_side / max(vb.width(), vb.height())
        sx = sy = s
        dx = center.x() - vb.x() * s - vb.width() * s / 2.0
        dy = center.y() - vb.y() * s - vb.height() * s / 2.0
    else:
        sx = sy = 1.0
        dx = dy = 0.0

    def coord(x, y):
        return x * sx + dx, y * sy + dy

    items = []
    for el in root.iter():
        tag = el.tag.replace(_NS, "")
        if tag == "line":
            x1, y1 = coord(_f(el.get("x1")), _f(el.get("y1")))
            x2, y2 = coord(_f(el.get("x2")), _f(el.get("y2")))
            it = _LineItem(QLineF(x1, y1, x2, y2))
        elif tag == "rect":
            x, y = coord(_f(el.get("x")), _f(el.get("y")))
            it = _RectItem(QRectF(x, y, _f(el.get("width")) * sx, _f(el.get("height")) * sy))
        elif tag in ("circle", "ellipse"):
            cx, cy = _f(el.get("cx")), _f(el.get("cy"))
            rx = _f(el.get("r")) if tag == "circle" else _f(el.get("rx"))
            ry = _f(el.get("r")) if tag == "circle" else _f(el.get("ry"))
            x0, y0 = coord(cx - rx, cy - ry)
            it = _EllipseItem(QRectF(x0, y0, rx * 2 * sx, ry * 2 * sy))
        elif tag in ("polyline", "polygon"):
            # [실사용 요청 2026-08-19] §8 항목21로 닫힌/열린 다각형 전용 `_PolygonItem`이
            # 생기기 전엔 임의 QPainterPath 컨테이너인 `_PathItem`(펜과 동일 타입)으로만
            # 담을 수 있었다 — 이제 `_PolygonItem`이 있으므로 box 리사이즈·이산 포트·TRIM을
            # 그대로 얻도록 옮긴다. `<path>`(베지어·호)는 대상 밖(정점 목록이 아니라 임의
            # 곡선이라 여전히 `_PathItem`이 맞는 선택).
            pts = _parse_points(el.get("points"))
            if len(pts) < 2:
                continue
            qpts = [QPointF(*coord(*p)) for p in pts]
            it = _PolygonItem(qpts, closed=(tag == "polygon"))
        elif tag == "path":
            d = el.get("d")
            if not d:
                continue
            it = _PathItem(_parse_path_d(d, sx, sy, dx, dy))
        elif tag == "text":
            txt = (el.text or "").strip()
            if not txt:
                continue
            it = _TextItem(QColor(el.get("fill") or "black"))
            it.setPlainText(txt)
            fs = _f(el.get("font-size"), 12.0)
            it.apply_font_size(max(6, int(fs * sx)))
            x, y = coord(_f(el.get("x")), _f(el.get("y")))
            it.setPos(x, y - fs * sx)   # SVG 텍스트 기준점은 baseline — 대략 위로 한 줄 높이만큼 보정
        else:
            continue
        items.append(it)
    return items, vb
