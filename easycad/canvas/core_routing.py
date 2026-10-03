"""화살표 직교 자동 라우팅(엘보·장애물 회피·A* 격자) + 선분 교차 계산(TRIM/EXTEND 기하 커널).

2026-10-03 `core_shapes.py`(9천 줄)에서 떼어 냄 — 이 함수들은 도형 클래스를 하나도 부르지 않는
순수 기하 함수(점·사각형·선분만 다룸)라 한 방향(core_shapes → 여기)으로만 쓰인다. 바깥 import
경로는 그대로(`core_shapes`가 `import *`로 받아 `annotator_core`까지 넘김). 도형 종류를 판별하는
함수(`_iter_bound_endpoints` 등)는 core_shapes에 남겼다.
"""
import heapq
import math

from PyQt6.QtCore import QPointF, QRectF, QLineF



# ---- [Stage1] Lucid식 직교 자동 라우팅(기본 엘보) -----------------------------
def _dedup_pts(pts, eps=1e-6):
    """연속 중복점 + 공선(collinear) 중간점 제거. 정렬된 도형 사이의 퇴화 엘보를 직선으로 접는다.

    [실사용 버그 수정 2026-08-31] `cross`가 0이면 a·b·c가 한 직선 위에 있다는 것만 보장하고
    b가 a-c *구간 안*에 있다는 것은 보장하지 않는다 — b가 a-c 밖(양끝을 지나 반대로 꺾인
    '되돌아오기' 지점)이어도 cross는 여전히 0이라 똑같이 제거됐다. `_route_ortho`의 진입/이탈
    스텁이 만드는 엘보(예: 도형 밖으로 conn_clear만큼 밀었다가 다시 안쪽으로 꺾는 형태)가 이
    되돌아오기 모양이라, 의도한 여백(conn_clear≈36px)이 통째로 사라지고 화살촉이 꺾임과
    거의 맞닿는 결과를 냈다(정렬된 두 접속점 사이에서 재현: 최소 5px까지 관측). b가 a-c
    구간 '안'(between)일 때만 제거하도록 좁힌다 — 진짜 퇴화(일직선 위 불필요한 경유점)는
    그대로 접고, 되돌아오기(방향 반전)는 보존한다."""
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p.x() - out[-1].x()) <= eps and abs(p.y() - out[-1].y()) <= eps:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        cross = (b.x() - a.x()) * (c.y() - a.y()) - (b.y() - a.y()) * (c.x() - a.x())
        between = (min(a.x(), c.x()) - eps <= b.x() <= max(a.x(), c.x()) + eps
                   and min(a.y(), c.y()) - eps <= b.y() <= max(a.y(), c.y()) + eps)
        if abs(cross) <= eps and between:
            del out[i]   # b가 a-c 선분 '위'(구간 안) → 불필요
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
# [§8 항목19 F3 성능수정, 2026-08-14] `_seg_hits_rect(a, b, r)`은 같은 세그먼트(a, b)를 여러
# 사각형과 반복 대조하는 호출부(`_path_hits_rects`의 rects 루프, `_astar_ortho_grid.edge_ok`의
# 후보 obstacle 루프)에서 매 사각형마다 a.y()/b.x() 등 QPointF 접근과 축판정·정렬을 처음부터
# 다시 했다 — 그 값들은 세그먼트 하나에 대해 전부 루프불변(loop-invariant)인데도 매번
# 재계산된 것(F2가 `_corridor_rect`에서 잡은 것과 같은 계열의 낭비, 다만 여긴 컴프리헨션이
# 아니라 함수 재호출이 원인). 새 스트레스 픽스처(`tools/route_ladder_stress.py`, 사다리가
# preferred 관통으로 실제 도는 배치)로 cProfile 확인: 부분선택 드래그(20/48) 10프레임에서
# `_seg_hits_rect` 단독 133,851회 호출·tottime 0.755초(전체 3.165초의 24%) — 세그먼트당 1회만
# 계산하면 되는 값을 사각형 개수만큼 반복한 게 그대로 비용이었다. `_seg_probe`로 세그먼트의
# 축판정 결과를 1회 추출해 `_probe_hits_rect`(사각형만 받는 저비용 판정)에 반복 전달하도록
# 분리 — 수학 자체는 원래 `_seg_hits_rect`와 동일(순수 리팩터, 결과 무변경).
def _seg_probe(a: QPointF, b: QPointF, eps=1e-6):
    """세그먼트 a-b를 여러 사각형과 대조하기 전 1회만 계산해 두는 축판정 결과.
    반환: (0, y, x0, x1)=수평(y 고정, x구간) / (1, x, y0, y1)=수직(x 고정, y구간) /
    (2, x0, x1, y0, y1)=대각선(엘보에선 미발생, 방어적 bbox 폴백)."""
    ay, by = a.y(), b.y()
    if abs(ay - by) <= eps:
        ax, bx = a.x(), b.x()
        x0, x1 = (ax, bx) if ax <= bx else (bx, ax)
        return (0, ay, x0, x1)
    ax, bx = a.x(), b.x()
    if abs(ax - bx) <= eps:
        y0, y1 = (ay, by) if ay <= by else (by, ay)
        return (1, ax, y0, y1)
    x0, x1 = (ax, bx) if ax <= bx else (bx, ax)
    y0, y1 = (ay, by) if ay <= by else (by, ay)
    return (2, x0, x1, y0, y1)


def _probe_hits_rect(probe, r: QRectF, eps=1e-6) -> bool:
    """`_seg_probe`가 뽑은 세그먼트 축판정 결과로 사각형 r의 '속'을 지나는지 판정
    (테두리 접촉은 통과로 봄) — `_seg_hits_rect`와 동일 수학, a/b 재접근 없음."""
    kind = probe[0]
    if kind == 0:
        _, y, x0, x1 = probe
        if y <= r.top() + eps or y >= r.bottom() - eps:
            return False
        return x1 > r.left() + eps and x0 < r.right() - eps
    if kind == 1:
        _, x, y0, y1 = probe
        if x <= r.left() + eps or x >= r.right() - eps:
            return False
        return y1 > r.top() + eps and y0 < r.bottom() - eps
    _, x0, x1, y0, y1 = probe
    return x1 > r.left() and x0 < r.right() and y1 > r.top() and y0 < r.bottom()


def _seg_hits_rect(a: QPointF, b: QPointF, r: QRectF, eps=1e-6) -> bool:
    """축정렬 선분 a-b가 사각형 r의 '속'을 지나는가(테두리 접촉은 통과로 봄).
    엘보 세그먼트는 전부 수평/수직이라 축별로 판정. 대각선(엘보에선 미발생)은 bbox 겹침으로 보수 판정.
    단발 호출용 — 같은 a·b를 여러 r과 반복 대조할 땐 `_seg_probe`+`_probe_hits_rect`를 직접 써서
    루프불변 계산을 세그먼트당 1회로 줄인다(아래 `_path_hits_rects` 참조)."""
    return _probe_hits_rect(_seg_probe(a, b, eps), r, eps)


def _path_hits_rects(pts, rects, eps=1e-6) -> bool:
    """정점 리스트 pts로 이루어진 폴리라인이 사각형들 중 하나라도 관통하면 True."""
    for i in range(len(pts) - 1):
        probe = _seg_probe(pts[i], pts[i + 1], eps)
        for r in rects:
            if _probe_hits_rect(probe, r, eps):
                return True
    return False


def _normal_stub(p: QPointF, n, d: float, clear_rect=None) -> QPointF:
    """부착 법선 n의 우세축으로 점 p를 d만큼 바깥으로 민 '스텁점'. n이 없으면 p 그대로.
    A* 라우팅 전 시작·끝에 강제해 ⓐ 테두리 수직 이탈/도착(미관) ⓑ 바인딩 도형을 가로지르지
    않게(스텁이 이미 도형 밖 clearance 거리) 한다.

    [B-lite — 실조건 2026-07-26] clear_rect(자기 연결 도형의 팽창 사각형)를 주면 스텁이 그
    사각형을 **확실히 벗어날 때까지** 밀어낸다. ⚠ 이게 없으면 실제 외곽선이 bbox 안으로 들어간
    도형(평행사변형·육각형·원)에서 부착점이 bbox 안쪽이라 d만큼 밀어도 여전히 팽창 안 → A*의
    시작/도착 노드가 고립돼 경로를 못 찾고 base로 폴백 → 그 폴백이 곧 관통이다(평행사변형
    E→W 이동 55회 중 105건 관통, 측정)."""
    if n is None:
        return p
    horiz = abs(n.x()) >= abs(n.y())
    sign = 1.0 if (n.x() if horiz else n.y()) >= 0 else -1.0
    if clear_rect is not None:
        # 법선 방향으로 팽창 사각형을 빠져나오는 데 필요한 최소 거리(+여유 1px)
        need = ((clear_rect.right() - p.x()) if sign > 0 else (p.x() - clear_rect.left())) if horiz \
            else ((clear_rect.bottom() - p.y()) if sign > 0 else (p.y() - clear_rect.top()))
        d = max(d, need + 1.0)
    return QPointF(p.x() + sign * d, p.y()) if horiz else QPointF(p.x(), p.y() + sign * d)


# ---- [Stage3 훅] 화살표-화살표 soft 회피용 세그먼트 교차 판정(avoid_segs/cross_penalty
# 재도입 시 사용 — 집계 래퍼 _count_seg_crossings는 호출부 3곳이 전부 이 판정을 감싸기만
# 하던 얇은 함수라 각 호출부에 인라인했다. 2026-07-28 코드정리) --------------------------
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


# ---- [§8 항목17 1단계] TRIM/EXTEND 기하 커널 — 좌표계 무관 순수함수 --------------------
# 위 _seg_cross_seg는 A* 라우팅 핫패스(간선마다 avoid_segs 전체와 대조)라 불린만 반환해
# 나눗셈을 피한다 — 그 성능 특성을 지키기 위해 아래 함수들과 통합하지 않고 분리해 둔다.
# 이 함수들은 "어느 좌표계인지" 모른 채 받은 점 그대로 계산한다 — 회전된 도형을 다룰 때는
# 호출부가 host.mapFromScene()으로 대상 기하를 host의 로컬좌표로 옮겨 넘긴다(2026-08-10
# deep-interview 확정). 기존 _host_outline_local_polygon·_port_edge_gap·cut 저장형식(변
# 인덱스+t, 로컬 비율)이 이미 이 패턴이라 Qt의 mapToScene/mapFromScene이 회전·스케일을
# 자동 반영해주므로 회전 특례 코드가 필요 없다.
def _seg_seg_intersection(a: QPointF, b: QPointF, c: QPointF, d: QPointF, eps=1e-9):
    """두 선분 a-b, c-d가 만나면 교차 '점'을(둘 다 [0,1] 파라미터 범위, 끝점 포함) 반환,
    평행·비교차면 None. _seg_cross_seg와 달리 끝점 접촉도 교차로 인정한다(TRIM 문지르기·
    EXTEND는 "정확히 끝점에서 만남"도 유효한 절단/연장 지점이라 배제할 이유가 없다 —
    _seg_cross_seg가 끝점을 제외하는 이유(화살표-도형 접촉 오판 방지)는 이 용도엔 해당 없음).
    Cramer 공식(선분을 a+t*(b-a), c+u*(d-c)로 매개화해 연립)."""
    dx1, dy1 = b.x() - a.x(), b.y() - a.y()
    dx2, dy2 = d.x() - c.x(), d.y() - c.y()
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < eps:
        return None
    t = ((c.x() - a.x()) * dy2 - (c.y() - a.y()) * dx2) / denom
    u = (dy1 * (c.x() - a.x()) - dx1 * (c.y() - a.y())) / denom
    if -eps <= t <= 1.0 + eps and -eps <= u <= 1.0 + eps:
        return QPointF(a.x() + t * dx1, a.y() + t * dy1)
    return None


def _seg_circle_intersections(p1: QPointF, p2: QPointF, center: QPointF, radius: float,
                              eps=1e-9) -> list:
    """선분 p1-p2와 원(center, radius)의 교차점(선분 위에 있는 것만, 0~2개) — 접선(tangent)은
    1개로 dedupe. 선분을 p1+t*(p2-p1)로 매개화한 이차방정식 |p1+t*d - center|=radius."""
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    fx, fy = p1.x() - center.x(), p1.y() - center.y()
    a = dx * dx + dy * dy
    if a < eps:
        return []
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return []
    sq = math.sqrt(disc)
    out = []
    for t in ((-b - sq) / (2.0 * a), (-b + sq) / (2.0 * a)):
        if -eps <= t <= 1.0 + eps:
            tc = min(1.0, max(0.0, t))
            pt = QPointF(p1.x() + tc * dx, p1.y() + tc * dy)
            if not out or QLineF(out[-1], pt).length() > eps:
                out.append(pt)
    return out


def _seg_ellipse_intersections(p1: QPointF, p2: QPointF, rect: QRectF, eps=1e-9) -> list:
    """선분 p1-p2와 타원(rect로 정의된 축정렬 타원 — `_EllipseItem.rect()`와 같은 꼴)의
    교차점. rx=rect.width()/2, ry=rect.height()/2로 스케일 역변환해 단위원 문제로 환원한
    뒤 `_seg_circle_intersections`를 재사용하고 다시 스케일해 되돌린다(계획서 §8 항목17
    1단계). rect 자체가 이미 축정렬(EllipseItem 정의상 회전 없음)이므로 host가 회전돼
    있어도 호출부가 p1/p2/rect를 host 로컬좌표로 넘기면 그대로 맞는다."""
    cx, cy = rect.center().x(), rect.center().y()
    rx, ry = max(rect.width() / 2.0, eps), max(rect.height() / 2.0, eps)
    up1 = QPointF((p1.x() - cx) / rx, (p1.y() - cy) / ry)
    up2 = QPointF((p2.x() - cx) / rx, (p2.y() - cy) / ry)
    upts = _seg_circle_intersections(up1, up2, QPointF(0.0, 0.0), 1.0, eps)
    return [QPointF(u.x() * rx + cx, u.y() * ry + cy) for u in upts]


# [성능최적화 2026-08-08, 1차 시도(회랑+실패시 전체 재시도)는 역효과라 되돌림 — 라우팅 사다리가
# '이 조합은 원래 못 찾음'을 정상 결과로 기대하며 여러 조합을 던지는 구조라, None이 나올 때마다
# 전체로 재시도하면 실패가 예정된 호출마다 비용이 2배가 됐다(실측: 도형드래그 중앙값 146ms→
# 447ms, 최악 4.1초). 실측으로 확인한 사실: 이 문서에서 None은 회랑이 좁아서가 아니라 그 특정
# 시도(스텁 조합)가 애초에 기하학적으로 안 풀려서였다 — 장애물 18개 전부로 돌려도 여전히 None.
# 즉 회랑 축소가 성공/실패 여부 자체를 바꾸지 않는다(실측: 3~5개로 줄인 시도와 16~18개 그대로인
# 시도가 같은 케이스에서 둘 다 None). 그래서 2차는 재시도 안전망 없이 회랑만 적용 — 대신 별도
# 스크립트로 회랑 적용 전/후 kbs_1tv_test.ecad 실도면 전체 화살표의 최종 경로가 정확히 같은지
# 직접 대조해 안전함을 확인했다(완전성 위반 0건).
_CORRIDOR_PAD_MIN = 400.0     # 최소 여유(scene 단위) — 재시도가 없으므로 넉넉하게 잡아 안전마진 확보
_CORRIDOR_PAD_CLEARANCE_MULT = 15.0


def _corridor_rect(a: QPointF, b: QPointF, clearance: float) -> QRectF:
    """[§8 항목19 F2 수정, 2026-08-14] a-b bbox를 `_CORRIDOR_PAD_MIN`/`_CORRIDOR_PAD_CLEARANCE_
    MULT`만큼 부풀린 회랑 사각형 — `_astar_ortho`가 매 호출마다 인라인으로 계산하던 것을
    추출(동작 변화 없음). `_route_ortho`가 `_route_score`/후보평가에 넘길 장애물 목록을 미리
    이걸로 걸러 두는 데도 재사용한다(아래 F2 참조)."""
    pad = max(_CORRIDOR_PAD_MIN, clearance * _CORRIDOR_PAD_CLEARANCE_MULT)
    lo_x, hi_x = (a.x(), b.x()) if a.x() <= b.x() else (b.x(), a.x())
    lo_y, hi_y = (a.y(), b.y()) if a.y() <= b.y() else (b.y(), a.y())
    return QRectF(lo_x - pad, lo_y - pad, (hi_x - lo_x) + 2 * pad, (hi_y - lo_y) + 2 * pad)


def _astar_ortho(start: QPointF, goal: QPointF, infl, clearance, eps=1e-6,
                 avoid_segs=(), cross_penalty=0.0):
    corridor = _corridor_rect(start, goal, clearance)
    local = [r for r in infl if r.intersects(corridor)]
    return _astar_ortho_grid(start, goal, local, clearance, eps, avoid_segs, cross_penalty)


def _astar_ortho_grid(start: QPointF, goal: QPointF, infl, clearance, eps=1e-6,
                 avoid_segs=(), cross_penalty=0.0):
    """[Stage2 승격] Hanan 그리드 위의 직교 A*. 팽창 장애물(infl)을 관통하지 않는 최단 직각
    경로의 '중간 정점'을 반환(없으면 None). 후보 스캔과 달리 임의 밀집 배치에서도 경로가
    존재하면 반드시 찾는다(Hanan 그리드 완전성: 직교 우회로가 있으면 장애물 모서리선 위에도 있다).

    격자선 = {start·goal 좌표} ∪ {각 장애물의 left/right(세로선)·top/bottom(가로선)}.
    노드는 이 선들의 교점, 간선은 인접 노드 사이 축정렬 선분(_seg_hits_rect로 관통 검사).
    회전 벌점(clearance*0.5)으로 엘보 수를 최소화해 경로를 깔끔하게. 상태에 진행축을 넣어
    벌점을 정확히 계산(Manhattan 휴리스틱은 벌점을 무시 → admissible).
    [§8 항목19 F7, 2026-08-14] 계수 `0.5`는 값 자체의 도출 근거(다른 배수 대비 실측 비교
    등)가 history에 남아있지 않다 — "회전 1회 = clearance 절반 거리만큼 손해"로 잡아
    직진 대비 우회 유인을 약하게 주는 정도의 튜닝값으로 추정. 바꿀 필요가 생기면 감(느낌)
    조정이 아니라 3단계(`docs/route_review_2026-08.md`)처럼 실제 배치를 렌더해 비교하며
    실측 기반으로 재조정할 것.

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

    # [성능최적화 2026-08-08] edge_ok가 매 grid 간선마다 obstacle 전부(infl, O(장애물 수))를
    # 순회하던 게 병목이었다(밀집 도면에서 드래그 중 reroute 1회에 수 초) — 각 grid 행/열에
    # '실제로 걸칠 수 있는' obstacle만 미리 걸러둔다. 필터 임계값이 _seg_hits_rect의 조기
    # return 조건(수평: r.top()+eps < y < r.bottom()-eps, 수직: 대칭)과 정확히 같아서, 걸러진
    # obstacle은 어차피 _seg_hits_rect가 False를 반환했을 것들뿐 — edge_ok 최종 판정은 100%
    # 동일하다(순수 사전필터, 경로 결과 무회귀).
    row_obst = [[r for r in infl if r.top() + eps < y < r.bottom() - eps] for y in ys]
    col_obst = [[r for r in infl if r.left() + eps < x < r.right() - eps] for x in xs]

    # [§8 항목19 F3 성능수정, 2026-08-14] 예전엔 매 간선마다 QPointF a·b를 새로 만들어
    # `_seg_hits_rect`에 넘겼다 — 그 안에서 다시 축판정+정렬을 candidate 개수만큼 반복했다.
    # 그리드 간선은 애초에 ay==by(수평) 아니면 ax==bx(수직)로 축이 이미 확정돼 있으므로(방금
    # cands를 고르는 데 쓴 바로 그 조건), QPointF 생성·`_seg_probe`의 abs()판정 없이 축판정
    # 결과를 직접 구성해 `_probe_hits_rect`에 넘긴다(위 `_path_hits_rects`와 동일 패턴).
    def edge_ok(ax, ay, bx, by):
        if ay == by:
            xa, xb = xs[ax], xs[bx]
            x0, x1 = (xa, xb) if xa <= xb else (xb, xa)
            probe = (0, ys[ay], x0, x1)
            cands = row_obst[ay]
        else:
            ya, yb = ys[ay], ys[by]
            y0, y1 = (ya, yb) if ya <= yb else (yb, ya)
            probe = (1, xs[ax], y0, y1)
            cands = col_obst[ax]
        return not any(_probe_hits_rect(probe, r, eps) for r in cands)

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


# [M4-4 ⓐ] 연결 도형 우회 여유 배수(제3도형 clearance 대비). 실조건 피드백(2026-07-24): 배수 1이면
# 선이 부착 도형 변에 바짝 붙어 답답 → 2로 벌려 숨통. 재진입 회피 케이스에만 적용(무회귀).
_CONN_CLEAR_MULT = 3.0

# [M4-4 ⓐ 잔여] '변 타기' 판정 — 경로가 도형을 관통하진 않지만 변 위에 포개져 테두리와 구분이
# 안 되는 케이스. _seg_hits_rect가 테두리 접촉을 의도적으로 통과시키기 때문에(부착점이 관통으로
# 잡히면 안 되므로) 관통 검사만으로는 안 걸린다.
_RIDE_TOL = 4.0          # 변과 이 거리 이내로 나란하면 '탄다'
_RIDE_MIN_OVERLAP = 4.0  # 겹치는 길이가 이보다 커야 유의미(모서리 스침 오탐 방지)


def _seg_ride_len(a: QPointF, b: QPointF, r: QRectF, n_at=None) -> float:
    """축정렬 선분 a-b가 사각형 r의 변과 나란히(거리 ≤ _RIDE_TOL) 겹치는 길이. 아니면 0.
    n_at: 이 선분이 '자기가 붙은' 부착점에 접해 있으면 그 법선 — 법선 방향으로 곧게 이탈/도착하는
    세그먼트는 정상이므로 면제한다(수직 이탈은 타기가 아니다)."""
    if n_at is not None:
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if abs(n_at.x()) >= abs(n_at.y()):
            if abs(dy) <= 1e-6 and abs(dx) > 1e-6:
                return 0.0            # 법선(수평) 방향으로 곧게 이탈 = 정상
        elif abs(dx) <= 1e-6 and abs(dy) > 1e-6:
            return 0.0                # 법선(수직) 방향으로 곧게 이탈 = 정상
    if abs(a.y() - b.y()) <= 1e-6 and abs(a.x() - b.x()) > 1e-6:      # 수평
        lo, hi = sorted((a.x(), b.x()))
        ov = min(hi, r.right()) - max(lo, r.left())
        if ov > _RIDE_MIN_OVERLAP and min(abs(a.y() - r.top()), abs(a.y() - r.bottom())) <= _RIDE_TOL:
            return ov
    elif abs(a.x() - b.x()) <= 1e-6 and abs(a.y() - b.y()) > 1e-6:    # 수직
        lo, hi = sorted((a.y(), b.y()))
        ov = min(hi, r.bottom()) - max(lo, r.top())
        if ov > _RIDE_MIN_OVERLAP and min(abs(a.x() - r.left()), abs(a.x() - r.right())) <= _RIDE_TOL:
            return ov
    return 0.0


def _path_ride_len(pts, conn_pairs, ns=None, ne=None) -> float:
    """폴리라인이 연결 도형 변을 타는 총 길이. conn_pairs=[(rect, 'start'|'end'), ...].
    ⚠ 면제는 '그 끝점이 붙어 있는 도형'에 대해서만 준다 — 같은 세그먼트라도 *다른* 도형의 변을
    타면 그건 타기다(부착 세그먼트라는 이유로 통째 면제하면 상대 도형 변 타기를 놓친다)."""
    pts = _dedup_pts(list(pts))
    tot = 0.0
    last = len(pts) - 2
    for i in range(len(pts) - 1):
        for r, owner in conn_pairs:
            n_at = None
            if i == 0 and owner == "start":
                n_at = ns
            elif i == last and owner == "end":
                n_at = ne
            tot += _seg_ride_len(pts[i], pts[i + 1], r, n_at)
    return tot


def _path_manhattan_len(pts) -> float:
    return sum(abs(pts[i + 1].x() - pts[i].x()) + abs(pts[i + 1].y() - pts[i].y())
               for i in range(len(pts) - 1))


def _route_score(mids, s, e, ns, ne, infl, conn_orig, conn_pairs, avoid_segs, rung=0):
    """경로 품질 점수 — 작을수록 좋다(사전식 비교).
      (도형관통, 연결도형재진입, 타기길이, 화살표교차, 정점수, 여유칸, 총길이)
    여유칸(rung)을 총길이보다 앞에 둬, 결함 없는 후보들 중에서는 '넉넉한 여유'를 고른다
    (_CONN_CLEAR_MULT의 실조건 피드백 '변에 바짝 붙으면 답답' 유지)."""
    full = _dedup_pts([s] + list(mids) + [e])
    crossings = (sum(1 for i in range(len(full) - 1) for p, q in avoid_segs
                      if _seg_cross_seg(full[i], full[i + 1], p, q))
                 if avoid_segs else 0)
    return (
        1 if (infl and _path_hits_rects(full, infl)) else 0,
        1 if (conn_orig and _path_hits_rects(full, conn_orig)) else 0,
        round(_path_ride_len(full, conn_pairs, ns, ne), 1) if conn_pairs else 0.0,
        crossings,
        len(full),
        rung,
        round(_path_manhattan_len(full), 1),
    )


def _route_ortho(s: QPointF, e: QPointF, ns, ne, obstacles, clearance=12.0,
                 avoid_segs=(), cross_penalty=0.0, conn_rects=(), fast=False):
    """[Stage2 승격] Stage1 엘보(_ortho_elbow)를 우선하되, 그 경로가 장애물을 관통하면
    Hanan 그리드 A*(_astar_ortho)로 우회로를 찾아 '중간 정점'을 반환.
      · 장애물 없음 또는 Stage1이 이미 안전(도형·화살표 모두) → Stage1 그대로(무변경·되먹임 없음).
      · 관통/교차 시 → 법선 스텁을 씌운 A* → (실패 시) 스텁 없는 A* → (실패 시) Stage1 폴백.
    후보 스캔(구현 (b))과 달리 밀집 배치에서도 우회로가 존재하면 반드시 찾는다(그리드 완전성).
    obstacles: scene 좌표 사각형(양끝 바인딩 도형은 호출부에서 이미 제외). clearance만큼 팽창해 여유 확보.
    [Stage3] avoid_segs/cross_penalty: 도형은 hard(관통 금지), 다른 화살표는 soft(교차 최소화).
    preferred가 도형은 안전하나 화살표를 가로지르면 A* 우회를 시도하되, 교차를 실제로 줄일 때만
    채택(개선 없으면 preferred 유지 → 불필요한 우회·되먹임 방지).
    [M4-4 ⓐ] conn_rects: 양끝 '연결 도형' bbox — **(start|None, end|None) 2-튜플**(끝점 소유권이
    타기 면제 판정에 필요). 끝점이 이 도형 테두리 위라 통짜 팽창 장애물로 못 넣는다(deferred 함정)
    → '재진입'만 원본 rect로 판정(부착점 바깥 스텁 접촉은 통과), 재진입 시에만 stub↔stub A*에
    팽창본을 장애물로 추가.
    [M4-4 ⓐ 잔여] 위 구조엔 두 구멍이 있었다(2026-07-26 전수 스윕 768케이스서 측정):
      · 두 연결 도형이 conn_clear보다 가까우면 한쪽 스텁이 반대쪽 팽창 사각형 *안*에 갇혀 A*가
        실패 → preferred 폴백 → 그 preferred가 곧 관통 경로(56/768 = 7.3%).
      · 변 위에 정확히 얹힌 경로는 _seg_hits_rect가 통과시켜 '안전'으로 남는다(48/768 = 6.2%).
    → 해법은 '오늘의 결과(base)를 먼저 계산하고, 추가 후보가 점수로 **엄격히 이길 때만** 교체'하는
    단조 개선 구조 + 연결도형 clearance 사다리(conn_clear→clearance→1→0). 오늘 결과가 깨끗하면
    후보를 만들지도 않으므로 경로·비용 모두 기존과 동일(무회귀).

    [성능 최적화 2026-08-11] `fast=True`면 **base가 이미 결함 없을 때만** 클리어런스 사다리
    (아래 "혹 감소" 폴리시 탐색)를 건너뛰고 base를 그대로 반환한다 — 사다리는 base가 결함
    없어도 매번 무조건 추가 A* 탐색(최대 4단×2회)을 도는데, 그 비용이 "화면당 1개 화살표"에선
    무해했지만 그룹 드래그처럼 한 프레임에 reroute가 수십 번 겹치면 지배적 비용이 됐다(실측:
    20개 그룹 드래그 675ms, 시간의 96%가 A*). ⚠ base가 아직 결함 있는 경우(밀집 장애물에서
    넉넉한 초기 클리어런스로 후보를 못 찾은 경우)는 `fast`여도 사다리를 그대로 돈다 — 사다리의
    좁은 rung들이 그 경우엔 "폴리시"가 아니라 "유일한 탈출구"일 수 있다는 게 코드 구조상
    이론적으로 가능해 보였다(실측 재현은 못 함, 아래 판정 조건 코드 주석 참조 — 코리도 패딩이
    넉넉해 실사용 규모에서 드문 것으로 추정). 이 체크는 이미 계산된 값 재사용이라 추가 비용이
    없어, 실증은 못 했어도 방어적으로 남겨뒀다. 기본값 False(기존 동작 무변경) — 호출부가
    "이번엔 배선 폭주 상황"이라고 판단할 때만(`host_canvas._on_scene_changed`, 다건 변경 시)
    명시적으로 켠다."""
    infl = ([r.adjusted(-clearance, -clearance, clearance, clearance) for r in obstacles]
            if obstacles else [])
    # [§8 항목19 F2 수정, 2026-08-14] 회랑 밖 장애물까지 infl에 그대로 들고 있으면, 뒤에서
    # 후보마다 도는 `_route_score`/`_path_hits_rects`가 경로와 무관한 먼 장애물까지 매번
    # 전부 훑는다(cProfile 실측: 프레임 비용의 47%가 이 반복 호출, `docs/route_review_2026-08.md`
    # 4단계 F3). `_astar_ortho`도 내부적으로 같은 회랑(`_corridor_rect`)으로 한 번 더 걸러
    # 안전하므로(그 필터가 이미 "완전성 손실 없음"을 보장한 것과 동일한 계산 — 여기서 먼저
    # 걸러도 A* 결과는 그대로) 매 후보 평가마다 반복하던 필터링을 함수당 1회로 당긴다.
    _corr = _corridor_rect(s, e, clearance)
    infl = [r for r in infl if r.intersects(_corr)]
    # [M4-4 ⓐ] 연결 도형: 원본 rect=재진입/타기 판정용, 팽창본=A* 장애물용. 여유는 제3도형
    # (clearance)보다 넉넉하게(conn_clear) — 부착 도형 변에 선이 딱 붙어 지나가면 답답해 보인다
    # (실조건 피드백 2026-07-24). 이탈/도착 스텁도 같은 거리로 밀어 격자선을 벌린다.
    conn_clear = clearance * _CONN_CLEAR_MULT
    conn_seq = tuple(conn_rects)[:2]
    conn_orig = [r for r in conn_seq if r is not None]
    conn_pairs = [(r, ("start", "end")[i]) for i, r in enumerate(conn_seq) if r is not None]
    conn_infl = [r.adjusted(-conn_clear, -conn_clear, conn_clear, conn_clear) for r in conn_orig]

    # [실사용 피드백 2026-07-30] preferred(무장애물 base)는 여태 법선 스텁 없이 s·e를 바로
    # _ortho_elbow에 넣어, 두 부착점의 좌표가 우연히 비슷하면(코너뿐 아니라 연속폴백 임의점도)
    # 첫 구간 길이가 0에 가까워져 법선 방향 이탈 없이 곧장 자기 도형 변을 타는 것처럼 보였다.
    # A* 우회(_candidates)가 이미 쓰던 _normal_stub(own-rect 팽창분까지 escape)을 base 계산
    # 자체로 옮겨, 항상 '자기 도형 밖으로 스텁 → 그 다음 엘보'가 되도록 통일한다.
    own_s = conn_seq[0] if len(conn_seq) > 0 else None
    own_e = conn_seq[1] if len(conn_seq) > 1 else None
    # [실사용 버그 수정 2026-08-31 후속] 부착 도형 둘 다 같은 축(H-H 또는 V-V)의 마주보는
    # 접속점으로 이어지는데 실제 간격이 conn_clear*2보다 좁으면, 양쪽 스텁이 서로의 escape
    # 방향으로 상대를 지나쳐 밀려나 `_ortho_elbow`의 my/mx 평균이 원래 진행 방향을 거슬러
    # '되돌아오는' 하이핀 모양을 만든다(위 `_dedup_pts` 수정으로 그동안 가려져 있던 이
    # 도형이 드러남 — 실사용 재현: 좁게 배치된 두 도형을 마주보는 포트로 이으면 진입 직전
    # 선이 180도 가까이 꺾여 돌아온다). 두 스텁의 escape 거리를 실제 간격의 절반으로 상한
    # 지어 겹침 자체를 막는다 — 간격이 충분하면(≥ conn_clear*2) `min`이 항상 conn_clear를
    # 골라 기존과 완전히 동일(무회귀).
    own_push = conn_clear
    if own_s is not None and own_e is not None and ns is not None and ne is not None:
        ns_h = abs(ns.x()) >= abs(ns.y())
        ne_h = abs(ne.x()) >= abs(ne.y())
        if ns_h == ne_h:
            gap = abs(e.x() - s.x()) if ns_h else abs(e.y() - s.y())
            own_push = min(conn_clear, gap / 2.0)

    def _own_stub(p, n, rect):
        if rect is None:
            return _normal_stub(p, n, clearance)
        infl_rect = rect.adjusted(-own_push, -own_push, own_push, own_push)
        return _normal_stub(p, n, own_push, infl_rect)
    s_stub = _own_stub(s, ns, own_s)
    e_stub = _own_stub(e, ne, own_e)
    elbow_mid = _ortho_elbow(s_stub, e_stub, ns, ne)
    preferred = (([] if s_stub == s else [s_stub]) + elbow_mid
                 + ([] if e_stub == e else [e_stub]))

    def _cross_count(pts):   # [Stage3 훅] avoid_segs 비면 0 — 재도입 시 활성화되는 집계
        return (sum(1 for i in range(len(pts) - 1) for p, q in avoid_segs
                     if _seg_cross_seg(pts[i], pts[i + 1], p, q))
                if avoid_segs else 0)

    pref_full = [s] + preferred + [e]
    pref_hits_shape = _path_hits_rects(pref_full, infl) if infl else False
    pref_reenters = _path_hits_rects(pref_full, conn_orig) if conn_orig else False
    pref_rides = (_path_ride_len(pref_full, conn_pairs, ns, ne) > 0) if conn_pairs else False
    pref_cross = _cross_count(pref_full)
    # preferred가 도형 안전 + 재진입·타기 없음 + 화살표 교차 없음 → 그대로(기존 무변경 보장).
    if not pref_hits_shape and not pref_reenters and not pref_rides and pref_cross == 0:
        return preferred

    def _candidates(obst, push, cc=None):
        """(1) 법선 스텁을 강제한 A*(수직 이탈/도착·바인딩 도형 회피) → (2) 스텁 없는 A*
        (스텁이 막혔을 때 폴백). 경로를 못 찾은 시도는 건너뛴다.
        [B-lite] cc가 있으면 각 끝의 스텁을 '자기 연결 도형의 팽창 사각형 밖'까지 밀어낸다 —
        슬랜트·곡선 외곽선이라 부착점이 bbox 안쪽인 도형에서 A*가 출발조차 못 하던 것을 푼다."""
        def own(i):
            r = conn_seq[i] if i < len(conn_seq) else None
            if r is None or cc is None:
                return None
            return r.adjusted(-cc, -cc, cc, cc)
        s2 = _normal_stub(s, ns, push, own(0))
        e2 = _normal_stub(e, ne, push, own(1))
        for a, b, pre, post in ((s2, e2, [] if s2 == s else [s2], [] if e2 == e else [e2]),
                                (s, e, [], [])):
            interior = _astar_ortho(a, b, obst, clearance,
                                    avoid_segs=avoid_segs, cross_penalty=cross_penalty)
            if interior is not None:
                yield pre + interior + post

    # --- (1) base = 기존 알고리즘이 내던 결과 그대로 -----------------------------
    base = preferred
    if pref_hits_shape or pref_reenters:
        # [M4-4 ⓐ] 재진입할 때만 conn을 A* 장애물/검증에 편입 — 순수 제3도형 케이스는 기존과 동일.
        # 도형 관통·재진입 회피는 hard 요구 — 첫 안전 후보 채택(화살표는 벌점으로 A*가 이미 최소화).
        astar_obst = (infl + conn_infl) if pref_reenters else infl
        check_rects = (infl + conn_orig) if pref_reenters else infl
        push = conn_clear if pref_reenters else clearance
        for mids in _candidates(astar_obst, push):
            if not _path_hits_rects([s] + mids + [e], check_rects):
                base = mids
                break
    elif avoid_segs:
        # preferred가 도형은 안전하나 화살표를 가로지름 — 두 시도를 모두 평가해 '교차를 가장 많이
        # 줄이는' 도형-안전 후보만 채택(개선 없으면 preferred 유지 → 불필요한 우회·되먹임 방지).
        # [§8 항목19 F5 수정, 2026-08-14] avoid_segs가 비면(Stage3 비활성 — 현재 모든 호출부가
        # 그러함) 이 분기는 pref_rides=True일 때만 진입하는데(pref_cross는 항상 0), `c <
        # best_cross`가 `0 < 0`으로 구조적으로 거짓이라 base를 절대 못 바꾸면서 A*만 최대
        # 2회 낭비했다(pref_rides는 아래 클리어런스 사다리가 conn_pairs 기반 ride_len
        # 판정으로 이미 해소함 — 무회귀). Stage3 재도입 시(avoid_segs 비지 않음) 이 탐색이
        # 다시 필요해지므로 로직 자체는 그대로 두고 게이트만 추가.
        best_cross = pref_cross
        for mids in _candidates(infl, clearance):
            if _path_hits_rects([s] + mids + [e], infl):   # 도형 관통은 hard — 후보 기각
                continue
            c = _cross_count([s] + mids + [e])
            if c < best_cross:
                base, best_cross = mids, c

    base_score = _route_score(base, s, e, ns, ne, infl, conn_orig, conn_pairs, avoid_segs)

    # --- (2) 연결도형 clearance 사다리 — base를 '엄격히 이기는' 후보만 교체 -------
    # 넉넉한 여유부터 좁은 여유까지 훑되, 채택 기준은 점수뿐이라 오늘보다 나쁜 경로는 구조적으로
    # 나올 수 없다(사다리가 전부 실패해도 base 유지). 0.0칸은 '팽창 없음' — 부착점이 팽창 사각형
    # 안에 갇혀 A*가 아예 출발 못 하는 배치의 마지막 탈출구.
    # [혹 버그 수정 2026-07-27] base가 이미 결함 없음(관통·재진입·타기 0)이어도 여기서 조기
    # 반환하지 않는다 — base는 conn_clear(가장 넉넉한 여유)로 A*가 처음 찾은 경로일 뿐이라 결함은
    # 없어도 불필요하게 먼 우회('혹')일 수 있다(사다리가 그 우회를 줄여줄 기회조차 못 얻었던 게
    # 근본원인). 사다리는 base보다 엄격히 나은 후보만 채택하는 단조개선이라 **정확성 기준으로는**
    # 늘 실행해도 무해하다 — 단 이 "무해"는 성능 무해를 뜻하지 않는다(위 docstring "성능 최적화
    # 2026-08-11" 참조).
    #
    # [2026-08-11 방어적 강화 — 코드 정독으로 찾은 이론적 허점, 실측 재현은 못 함] 처음엔
    # `if fast: return base`로 사다리 전체를 무조건 건너뛰었다. `base`는 "결함 없음"이 아니라
    # "conn_clear(가장 넉넉한 클리어런스)로 첫 유효 후보를 찾으려 *시도*한 결과"일 뿐이므로,
    # 그 시도가 전부 실패하면(밀집 장애물) base가 여전히 preferred(관통하는 원본)로 남을 수
    # 있다는 게 코드 구조상 이론적으로 가능해 보였다 — 이 경우 사다리의 더 좁은 rung
    # (clearance→1.0→0.0)이 유일한 탈출구다("부착점이 팽창 사각형 안에 갇혀 A*가 아예 출발
    # 못 하는 배치의 마지막 탈출구", 바로 위 주석). ⚠ 실제 그룹 드래그(38개 화살표, 8프레임)
    # 로 검증해봤을 땐 이 시나리오를 못 만났다 — A* 코리도 패딩(`_CORRIDOR_PAD_MIN`=400
    # 이상)이 매우 넉넉해 실사용 도면 규모에서 conn_clear 시도가 완전히 막히는 경우가
    # 드문 것으로 보인다(처음 "회귀 재현"이라 여겼던 5건은 검증 스크립트가 관통 판정에
    # `boundingRect()`(펜폭 패딩 포함)를 써서 생긴 오탐이었고, `_obstacle_rects()`와 같은
    # 원본 `.rect()`로 다시 재니 수정 전/후 모두 0건이었다). 그래도 이 체크는 이미 계산된
    # `base_score`를 재사용해 **추가 비용이 0**이므로, 실증은 못 했어도 이론적 허점을 막아두는
    # 쪽을 택했다 — `base_score`의 앞 네 항목(관통·재진입·타기·교차, `_route_score` 정의
    # 참조)이 전부 0일 때만(=base가 실제로 결함 없을 때만) 사다리를 건너뛴다.
    if fast and base_score[0] == 0 and base_score[1] == 0 and base_score[2] == 0 and base_score[3] == 0:
        return base
    best, best_score = base, base_score
    for rung, cc in enumerate((conn_clear, clearance, 1.0, 0.0)):
        cinfl = [r.adjusted(-cc, -cc, cc, cc) for r in conn_orig]
        for mids in _candidates(infl + cinfl, cc, cc):
            sc = _route_score(mids, s, e, ns, ne, infl, conn_orig, conn_pairs, avoid_segs, rung)
            if sc < best_score:
                best, best_score = mids, sc

    # [§8 항목19 F1 수정, 2026-08-14] 최후 수단 — 위 사다리를 다 돌아도 여전히 제3자 도형을
    # 관통하면(best_score[0] != 0), 이 경우에 한해서만 제3자 장애물을 clearance로 안 부풀린
    # **원본 경계**로 다시 시도한다. 근본원인: 장애물이 연결 도형에 밀착하면 스텁 이탈점이
    # 부풀린 장애물 사각형 안쪽에 갇혀(도형 자신은 obstacle 목록에 없어 반대편 격자선이 아예
    # 없다) A*가 매 사다리 rung에서 전부 실패하고 관통 preferred로 폴백한다(재현·근본원인:
    # `docs/route_review_2026-08.md` 3단계 F1). 부풀리지 않은 원본 경계라면 시작/끝점이 그
    # 경계에 딱 붙어 있을 뿐 "안"은 아니라서(`_seg_hits_rect`의 접촉=통과 규약) A*가 격자
    # 노드를 하나 얻어 우회를 찾을 수 있다. 대가로 이 최후수단 경로는 그 장애물과의 안전
    # 여백(clearance)이 없다 — 그래도 "정말로 관통"보다는 낫다는 판단(자주 발동하면 미관
    # 재검토 여지, `docs/route_review_2026-08.md` 6단계 "미해결로 남긴 것" 참조). 안전
    # 여백판정(infl)이 아니라 원본(obstacles) 기준으로만 관통 여부를 재확인해 채택한다 —
    # 이미 결함 없는 정상 케이스는 best_score[0]==0이라 이 블록에 아예 진입하지 않는다(무회귀).
    if best_score[0] != 0 and obstacles:
        for mids in _candidates(obstacles, 0.0, 0.0):
            full = _dedup_pts([s] + mids + [e])
            if not _path_hits_rects(full, obstacles):
                best = mids
                break
    return best


# core_shapes.py의 `import *`(→ core_view·annotator_core 연쇄)가 밑줄 접두 이름까지 넘겨받게 강제
# (core_constants·core_shapes와 같은 이유).
__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]
