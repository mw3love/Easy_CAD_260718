"""순서도·안테나 심볼 모양(QRectF → QPainterPath 경로 팩토리) + `_SYMBOL_KINDS` 목록.

2026-10-03 `core_shapes.py`에서 떼어 냄 — 도형 클래스를 부르지 않는 경로 함수들이라 한
방향(core_shapes의 `_SymbolItem` → 여기)으로만 쓰인다. 바깥 import 경로는 그대로.
"""

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath



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


def _sym_manual_input(r: QRectF) -> QPainterPath:  # 수동입력 — 왼쪽이 낮은 사선 윗변
    p = QPainterPath()
    slant = r.height() * 0.22
    p.moveTo(r.left(), r.top() + slant)
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right(), r.bottom())
    p.lineTo(r.left(), r.bottom())
    p.closeSubpath()
    return p


def _sym_manual_op(r: QRectF) -> QPainterPath:     # 수동작업 — 역사다리꼴(아래가 좁음)
    p = QPainterPath()
    dx = r.width() * 0.18
    p.moveTo(r.left(), r.top())
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right() - dx, r.bottom())
    p.lineTo(r.left() + dx, r.bottom())
    p.closeSubpath()
    return p


def _sym_display(r: QRectF) -> QPainterPath:       # 화면출력 — 위아래 평평·우측 볼록·좌측 오목
    # 스타디움(terminal)과 헷갈리지 않도록 좌우를 비대칭으로: 왼쪽은 안으로 파인 오목 곡선(quadTo
    # 제어점이 도형 안쪽), 오른쪽만 화면 브라운관처럼 둥글게 볼록(cubicTo).
    p = QPainterPath()
    w, h = r.width(), r.height()
    cy = r.center().y()
    flat_x = r.left() + w * 0.6
    p.moveTo(r.left(), r.top())
    p.lineTo(flat_x, r.top())
    p.cubicTo(r.left() + w * 0.86, r.top(),
              r.right(), r.top() + h * 0.2,
              r.right(), cy)
    p.cubicTo(r.right(), r.bottom() - h * 0.2,
              r.left() + w * 0.86, r.bottom(),
              flat_x, r.bottom())
    p.lineTo(r.left(), r.bottom())
    p.quadTo(r.left() + w * 0.18, cy, r.left(), r.top())
    p.closeSubpath()
    return p


def _sym_delay(r: QRectF) -> QPainterPath:         # 지연 — 오른쪽 반원(D자형)
    p = QPainterPath()
    w, h = r.width(), r.height()
    straight_x = r.left() + w * 0.62
    radius = h / 2.0
    p.moveTo(r.left(), r.top())
    p.lineTo(straight_x, r.top())
    p.arcTo(QRectF(straight_x - radius, r.top(), 2 * radius, h), 90.0, -180.0)
    p.lineTo(r.left(), r.bottom())
    p.closeSubpath()
    return p


def _sym_triangle(r: QRectF) -> QPainterPath:      # [신규기능 §8-12] 삼각형 — 분배기 등 장비 도형
    # 2026-08-09 deep-interview: 실도면(HDA-3951 증폭기 등) 대조로 꼭짓점이 오른쪽(신호
    # 흐름 방향)을 향하는 형태가 기본으로 확정 — 평평한 변(왼쪽, 입력)·꼭짓점(오른쪽, 출력).
    # [2026-08-10 후속] 정삼각형으로 내접(`_tri_rect`)시키던 걸 버리고 bbox r을 그대로 채운다 —
    # Lucid 대조(실사용 지적): 정삼각형 유지는 필연적으로 한 축에 패딩을 만들어(비정사각
    # bbox에서), 리사이즈 핸들·qc-dot·TRIM 자국 핸들이 전부 실제 꼭짓점/변과 어긋나는
    # 근본 원인이었다. bbox를 그대로 채우면 뒤쪽 두 꼭짓점(TL·BL)이 항상 정확히 bbox 모서리와
    # 일치해 그 두 핸들은 특례 코드 없이 저절로 맞는다(Lucid의 "위 두 꼭짓점=bbox 모서리"와
    # 같은 구조, 우리는 90도 돌아간 배치라 왼쪽 두 모서리). "최대한 정삼각형에 가깝게"는
    # 기본 생성 크기(`_PALETTE_TRIANGLE_WH`)를 정삼각형 비율로 맞추는 쪽에서 담당 — 그
    # 비율 그대로 두면 이 함수가 실제로 정삼각형을 그린다(리사이즈하면 다른 도형처럼 늘어남,
    # 원을 늘이면 타원이 되는 것과 같은 통상적 동작).
    p = QPainterPath()
    p.moveTo(r.left(), r.top())
    p.lineTo(r.left(), r.bottom())
    p.lineTo(r.right(), r.center().y())
    p.closeSubpath()
    return p


# ---------------------------------------------------------------------------
# [신규기능 §8-13] 안테나 심볼 7종 — 모악산 송신소 실물 사진 대조 후 확정(deep-interview +
# artifact 시안 비교, 2026-08-04). 좌표는 사용자 확인을 거친 0~100 정규화 SVG 시안을 그대로
# 옮긴 것이라 `_n()` 헬퍼로 rect에 매핑한다(감사·재조정 시 시안과 나란히 비교하기 위함).
def _n(r: QRectF, x: float, y: float) -> QPointF:
    return QPointF(r.left() + x / 100.0 * r.width(), r.top() + y / 100.0 * r.height())


def _sym_mw_side(r: QRectF) -> QPainterPath:       # MW 파라볼릭(측면) — 겹친 원 2개로 두께감
    p = QPainterPath()
    s = min(r.width(), r.height()) / 100.0
    p.addEllipse(_n(r, 42, 50), 30 * s, 30 * s)
    p.addEllipse(_n(r, 60, 50), 26 * s, 26 * s)
    return p


def _sym_mw_front(r: QRectF) -> QPainterPath:      # MW 파라볼릭(정면) — 테두리 이중선으로 두께감
    p = QPainterPath()
    s = min(r.width(), r.height()) / 100.0
    c = _n(r, 50, 50)
    p.addEllipse(c, 32 * s, 32 * s)
    p.addEllipse(c, 28 * s, 28 * s)
    return p


def _sym_cp_dipole(r: QRectF) -> QPainterPath:     # CP 다이폴 — 사각 프레임 + 프레임 밖으로 나온 십자
    p = QPainterPath()
    p.addRect(QRectF(_n(r, 24, 24), _n(r, 76, 76)))
    p.moveTo(_n(r, 50, 12)); p.lineTo(_n(r, 50, 88))
    p.moveTo(_n(r, 12, 50)); p.lineTo(_n(r, 88, 50))
    return p


def _sym_cp_ring(r: QRectF) -> QPainterPath:       # CP RING — 가스통형(사각 몸통 + 완만한 노즈콘)
    p = QPainterPath()
    p.moveTo(_n(r, 30, 72))
    p.lineTo(_n(r, 30, 50))
    p.quadTo(_n(r, 27, 37), _n(r, 50, 27))
    p.quadTo(_n(r, 73, 37), _n(r, 70, 50))
    p.lineTo(_n(r, 70, 72))
    p.closeSubpath()
    return p


def _sym_dtv(r: QRectF) -> QPainterPath:           # DTV — 세로 패널(이중 테두리 베젤 + 모서리 사선)
    p = QPainterPath()
    p.addRect(QRectF(_n(r, 34, 8), _n(r, 66, 92)))
    p.addRect(QRectF(_n(r, 39, 13), _n(r, 61, 87)))
    p.moveTo(_n(r, 34, 8)); p.lineTo(_n(r, 39, 13))
    p.moveTo(_n(r, 66, 8)); p.lineTo(_n(r, 61, 13))
    p.moveTo(_n(r, 34, 92)); p.lineTo(_n(r, 39, 87))
    p.moveTo(_n(r, 66, 92)); p.lineTo(_n(r, 61, 87))
    return p


def _mesh_grid_path(r: QRectF) -> QPainterPath:    # MESH 공용 — 외곽원 + 대각격자 + 십자선(중앙점 제외)
    p = QPainterPath()
    s = min(r.width(), r.height()) / 100.0
    p.addEllipse(_n(r, 50, 50), 32 * s, 32 * s)
    for x1, y1, x2, y2 in ((22, 26, 74, 78), (18, 44, 56, 82), (44, 18, 82, 56),
                           (78, 26, 26, 78), (82, 44, 44, 82), (56, 18, 18, 56)):
        p.moveTo(_n(r, x1, y1)); p.lineTo(_n(r, x2, y2))
    p.moveTo(_n(r, 18, 50)); p.lineTo(_n(r, 82, 50))
    p.moveTo(_n(r, 50, 18)); p.lineTo(_n(r, 50, 82))
    return p


def _sym_mesh_hollow(r: QRectF) -> QPainterPath:   # MESH 파라볼릭(윤곽) — 중앙 급전부를 빈 원으로
    p = _mesh_grid_path(r)
    s = min(r.width(), r.height()) / 100.0
    p.addEllipse(_n(r, 50, 50), 6 * s, 6 * s)
    return p


def _sym_mesh_filled(r: QRectF) -> QPainterPath:   # MESH 파라볼릭(채움) — 중앙 원은 paint()가 강제로 검게 채움
    return _mesh_grid_path(r)


def _mesh_center_dot_rect(r: QRectF) -> QRectF:    # mesh_filled 전용 — 강제 채움 원의 사각형(paint()에서 사용)
    s = min(r.width(), r.height()) / 100.0
    c = _n(r, 50, 50)
    rad = 6 * s
    return QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad)


def _sym_lightning(r: QRectF) -> QPainterPath:     # 번개 표식 — 안테나 레이돔 로고 등, 다른 심볼 위에 얹어 쓰는 작은 데칼
    # Feather "zap" 아이콘의 검증된 폴리곤(0~24 box)을 0~100으로 스케일 이식 — 자체 zigzag를
    # 새로 설계하지 않고 이미 널리 쓰이는 번개 실루엣을 그대로 가져온 것.
    pts = [(13, 2), (3, 14), (12, 14), (11, 22), (21, 10), (12, 10)]
    p = QPainterPath()
    x0, y0 = pts[0]
    p.moveTo(_n(r, x0 / 24 * 100, y0 / 24 * 100))
    for x, y in pts[1:]:
        p.lineTo(_n(r, x / 24 * 100, y / 24 * 100))
    p.closeSubpath()
    return p


# kind → (한글 라벨, 경로 팩토리). 팔레트·직렬화·그리기가 이 하나를 공유한다.
# [2026-08-03] 카메라·증폭기·랙·안테나(도메인 픽토그램 4종)는 사용 빈도가 낮고 디자인
# 완성도도 떨어진다는 피드백으로 제거(구 .ecad 파일에 남아 있어도 _SymbolItem.__init__이
# 미지원 kind를 "decision"으로 폴백하므로 로드는 깨지지 않는다).
# [2026-08-04] 위 제거된 "안테나" 1종을 실물 사진 기반 7종(mw_side~mesh_hollow)으로 재도입
# — 디자인 완성도 문제였던 옛 픽토그램과 달리 deep-interview + artifact 시안 비교로 확정.
# 번개 표식(lightning)은 안테나 전용이 아니라 다른 심볼 위에 겹쳐 쓰는 범용 작은 데칼.
_SYMBOL_KINDS = {
    "decision":    ("판단", _sym_decision),
    "terminal":    ("시작/끝", _sym_terminal),
    "data":        ("입출력", _sym_data),
    "prep":        ("준비", _sym_prep),
    "document":    ("문서", _sym_document),
    "database":    ("저장소", _sym_database),
    "manual_input": ("수동입력", _sym_manual_input),
    "manual_op":   ("수동작업", _sym_manual_op),
    "display":     ("화면출력", _sym_display),
    "delay":       ("지연", _sym_delay),
    "triangle":    ("삼각형", _sym_triangle),
    "mw_side":     ("MW 파라볼릭(측면)", _sym_mw_side),
    "mw_front":    ("MW 파라볼릭(정면)", _sym_mw_front),
    "cp_dipole":   ("CP 다이폴", _sym_cp_dipole),
    "cp_ring":     ("CP RING", _sym_cp_ring),
    "dtv":         ("DTV", _sym_dtv),
    "mesh_filled": ("MESH 파라볼릭(채움)", _sym_mesh_filled),
    "mesh_hollow": ("MESH 파라볼릭(윤곽)", _sym_mesh_hollow),
    "lightning":   ("번개 표식", _sym_lightning),
}


# core_shapes.py의 `import *`(→ core_view·annotator_core 연쇄)가 밑줄 접두 이름까지 넘겨받게 강제
# (core_constants·core_shapes와 같은 이유).
__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
