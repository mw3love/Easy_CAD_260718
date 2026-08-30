"""Easy CAD 테스트 공용 픽스처·헬퍼 — tests/test_easycad.py(7181줄)를 2026-08-02에 분할.

원본 test_easycad.py의 상단 임포트/전역(_app/_TMP) + 테스트 전용이 아닌 헬퍼 함수 전부를 모았다.
각 test_part*.py는 `from _shared import *`로 이걸 가져와 쓴다. 개별 헬퍼의 의미는 그대로(이동만).
"""
import os
import sys
import tempfile
import uuid
from contextlib import contextmanager
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication, QToolButton
from PyQt6.QtCore import Qt, QRectF, QLineF, QPointF, QPoint
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPixmap

from easycad.canvas.host import CanvasWindow, _ToastLabel
from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem,
    _PolyArrowItem, _SymbolItem, _ImageItem, _TitleBlockItem, _TableItem, _SYMBOL_KINDS,
    _PolygonItem,
    _nearest_border, _nearest_border_visible, _shape_ports, _axis_scale_fn, _mirror_fn,
    _seg_cross_seg, _ConnectorLabel, _shape_ports, _RIDE_TOL,
    _attach_port_to_host, _detach_port_from_host, build_trimmed_border_path,
    _reposition_port_from_frac, _seg_seg_intersection, _seg_circle_intersections,
    _seg_ellipse_intersections, _host_outline_local_polygon, _add_border_cut,
    _border_pt_in_gap, _shape_ports_visible, _trim_candidate_segment,
    _open_item_local_pts, _item_local_edges, _trim_candidate_open_segment,
    _extend_candidate, _ray_seg_intersection, apply_open_item_trim, apply_extend,
    _tight_scene_bbox, _item_center_path, _merge_cuts_list, _restore_cut_candidate,
    _host_outline_edges, _closed_shape_trim_fragments, _host_outline_edge_spans,
    _destructive_trim_result, _curve_run_edges, _GroupBindProxy)
from easycad.fileio.pdf_export import export_pdf, _selection_rect, render_preview
from easycad.canvas.host_dialogs import _PdfExportDialog
from easycad.fileio.document import save_document, load_document, load_document_layers, item_to_dict
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.sketch_build import Sketch, _argb

_app = QApplication.instance() or QApplication([])
_TMP = tempfile.mkdtemp(prefix="easycad_test_")

# [2026-08-20 후속 — 커밋 9323180이 놓친 두 번째 경로] `conftest.py`의 autouse fixture는
# **pytest로 실행할 때만** 발동한다. `tests/test_easycad.py`(문서화된 "전체 실행 진입점",
# CLAUDE.md가 그대로 추천하는 명령)는 pytest 없이 테스트 함수를 직접 호출하는 자체 러너라
# 그 fixture가 아예 안 걸린다 — 이 경로로 실행하면 `test_part9_ai_mermaid.py`의
# `_clear_gateway_settings()`가 `gw._SETTINGS_ORG/_SETTINGS_APP`의 기본값("EasyCAD")을
# 그대로 참조해 실사용자 레지스트리(`HKCU\Software\EasyCAD\EasyCAD\ai_gateway_key`)를
# 또 지운다 — 실제로 이 세션에서 `python tests/test_easycad.py`를 두 차례 실행해 재발시켰다
# (실측: 수정 전 조회 시 `ai_gateway_key`가 빈 문자열). `_shared.py`는 pytest·자체 러너
# 어느 경로든 모든 test_part*.py가 제일 먼저 `from _shared import *`로 가져가므로, 여기서
# 모듈 임포트 시점에 한 번 재바인딩하면 두 경로 다 커버된다(`conftest.py`의 pytest-전용
# monkeypatch는 방어 한 겹으로 유지 — 매 테스트 teardown마다 이 값으로 되돌아갈 뿐이라
# 충돌 없음).
from easycad.ai import gateway as _gw
_gw._SETTINGS_ORG = "EasyCAD-pytest"
_gw._SETTINGS_APP = "EasyCAD-pytest"
# [최종 검수 Phase 1, 2026-08-25] `resolve_api_key()`가 QSettings보다 먼저 확인하는
# `SECRETS_FILE`(실제 사용자 게이트웨이 키 저장 경로)도 같은 이유로 격리 — conftest.py의
# autouse fixture와 동일 목적이지만 이 경로(자체 러너 `test_easycad.py`)는 pytest fixture가
# 안 걸리므로 여기서 모듈 임포트 시점에 재바인딩(위 `_SETTINGS_ORG/_APP`과 같은 관례).
import pathlib as _pathlib
_gw.SECRETS_FILE = _pathlib.Path(_TMP) / "no-such-secrets.key"

# [실사용 요청 2026-08-21, 단축키 설정] 같은 이유로 `easycad.canvas.shortcuts`도 실사용자
# 레지스트리("EasyCAD"/"EasyCAD" — 다크모드 등 다른 설정과 같은 그룹)를 안 건드리게 격리.
from easycad.canvas import shortcuts as _shortcuts
_shortcuts._SETTINGS_ORG = "EasyCAD-pytest"
_shortcuts._SETTINGS_APP = "EasyCAD-pytest"


def _close(a, b, eps=0.5):
    return abs(a.x() - b.x()) < eps and abs(a.y() - b.y()) < eps


def _mk_rect(scene, pen, x, y, w, h):
    it = _RectItem(QRectF(x, y, w, h)); it.setPen(pen); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    scene.addItem(it); return it


def _rmb(v, etype, local, glob=None):
    # [M3 #16] 우클릭 마우스 이벤트 합성 — press/release=RightButton, move=RightButton held.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    glob = glob if glob is not None else local
    if etype == "press":
        e = QMouseEvent(QEvent.Type.MouseButtonPress, local, glob,
                        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                        Qt.KeyboardModifier.NoModifier)
        v.mousePressEvent(e)
    elif etype == "move":
        e = QMouseEvent(QEvent.Type.MouseMove, local, glob,
                        Qt.MouseButton.NoButton, Qt.MouseButton.RightButton,
                        Qt.KeyboardModifier.NoModifier)
        v.mouseMoveEvent(e)
    else:
        e = QMouseEvent(QEvent.Type.MouseButtonRelease, local, glob,
                        Qt.MouseButton.RightButton, Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier)
        v.mouseReleaseEvent(e)


def _draw_helpers(view):
    """뷰 이벤트 시뮬 헬퍼(핸들러 직접 호출 — 클릭 배치·드래그 경로는 아이템 라우팅 불요)."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    NO = Qt.KeyboardModifier.NoModifier
    L = Qt.MouseButton.LeftButton
    NB = Qt.MouseButton.NoButton

    def _ev(t, sp, btn, btns):
        vp = view.mapFromScene(sp)
        return QMouseEvent(t, QPointF(vp), QPointF(vp), btn, btns, NO)

    def press(sp):
        view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, sp, L, L))

    def release(sp):
        view.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, sp, L, NB))

    def click(sp):
        press(sp); release(sp)

    def move(sp):
        view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, sp, NB, NB))

    def drag_move(sp):
        view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, sp, NB, L))

    def dbl(sp):
        press(sp)
        view.mouseDoubleClickEvent(_ev(QEvent.Type.MouseButtonDblClick, sp, L, L))
        release(sp)

    return press, release, click, move, drag_move, dbl


def _assert_all_segments_axis_aligned(pts, msg):
    for p1, p2 in zip(pts[:-1], pts[1:]):
        assert abs(p1.x() - p2.x()) < 1e-6 or abs(p1.y() - p2.y()) < 1e-6, (msg, p1, p2)


def _hint_arrow(w):
    """[경유지 힌트(2f)] 오프셋 배치 두 도형 + 자동라우팅 화살표(H-V-H, 중간정점 2개) 준비."""
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)       # 우측 (100,30), 법선 +x
    b = _mk_rect(w._scene, w.make_pen(), 400, 200, 100, 60)   # 좌측 (400,230), 법선 -x
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(400, 230))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30)); sa.set_bound(1, b, QPointF(400, 230))
    sa._auto_route = True; sa.build_elbow()
    return a, b, sa


def _drag_vertex(sa, idx, to_scene):
    """실제 마우스 드래그를 프록시: 정점 idx를 to_scene으로 끌어 힌트 커밋 파이프라인을 태운다."""
    sa._on_endpoint_drag_start(idx)
    sa._set_endpoint(idx, sa.mapFromScene(to_scene))
    sa._on_endpoint_drag_end(idx)


def _idx_near(sa, scene_pt):
    return min(range(len(sa._pts)),
               key=lambda i: (sa.mapToScene(sa._pts[i]) - scene_pt).manhattanLength())


def _mk_loopback_scene(w, with_edges=True):
    """밀집 배치 축소판 — 세로 전진엣지 4개를 가로지르는 긴 수평 루프백.
    with_edges=False면 루프백만 놓아 '다른 화살표가 없을 때'의 기준 경로를 얻는다."""
    sc = w._scene
    rects, arrows = [], []

    def arrow(a, pa, b, pb):
        sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
        sa.set_points(pa, pb)
        sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
        sc.addItem(sa)
        sa.set_bound(0, a, a.mapFromScene(pa)); sa.set_bound(1, b, b.mapFromScene(pb))
        sa._auto_route = True
        return sa

    for k in range(4):                       # 세로 전진엣지 4개(x=130,230,330,430)
        x = 100 * (k + 1)
        top = _mk_rect(sc, w.make_pen(), x, -100, 60, 60)
        bot = _mk_rect(sc, w.make_pen(), x, 300, 60, 60)
        rects += [top, bot]
        if with_edges:
            arrows.append(arrow(top, QPointF(x + 30, -40), bot, QPointF(x + 30, 300)))
    L = _mk_rect(sc, w.make_pen(), 0, 120, 60, 60)     # E 포트 (60,150)
    R = _mk_rect(sc, w.make_pen(), 500, 120, 60, 60)   # W 포트 (500,150)
    rects += [L, R]
    arrows.append(arrow(R, QPointF(500, 150), L, QPointF(60, 150)))   # 긴 수평 루프백
    for _ in range(4):                       # 안정될 때까지(다른 화살표 최종 경로 반영)
        if not any(sa.build_elbow() for sa in arrows):
            break
    return rects, arrows


def _arrow_cross_and_hits(rects, arrows):
    from easycad.canvas.annotator_core import _path_hits_rects
    segs = []
    for sa in arrows:
        pts = [sa.mapToScene(p) for p in sa._pts]
        segs.append([(pts[i], pts[i + 1]) for i in range(len(pts) - 1)])
    cross = 0
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            for a, b in segs[i]:
                cross += sum(1 for c, d in segs[j] if _seg_cross_seg(a, b, c, d))
    rr = [r.mapRectToScene(r.rect()) for r in rects]
    hits = 0
    for sa in arrows:
        pts = [sa.mapToScene(p) for p in sa._pts]
        for r, box in zip(rects, rr):
            if r is sa._bind_start or r is sa._bind_end:
                continue
            if _path_hits_rects(pts, [box]):
                hits += 1
    return cross, hits


def _route_vertical_pair(w, dx):
    """위/아래 박스를 세로연결 — 아래 박스 center-x를 dx만큼 어긋냄. 안정 라우팅 후
    (화살표, 세그먼트 수)를 반환."""
    sc = w._scene
    top = _mk_rect(sc, w.make_pen(), 100, 0, 60, 40)          # S-port center-x = 130
    bot = _mk_rect(sc, w.make_pen(), 100 + dx, 200, 60, 40)   # N-port center-x = 130+dx
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    s, e = QPointF(130, 40), QPointF(130 + dx, 200)
    sa.set_points(s, e)
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    sc.addItem(sa)
    sa.set_bound(0, top, top.mapFromScene(s)); sa.set_bound(1, bot, bot.mapFromScene(e))
    sa._auto_route = True
    for _ in range(4):
        if not sa.build_elbow():
            break
    return sa, len(sa._pts) - 1, top, bot


def _rot(p, c, deg):
    import math
    r = math.radians(deg); cs, sn = math.cos(r), math.sin(r)
    dx, dy = p.x() - c.x(), p.y() - c.y()
    return QPointF(c.x() + dx * cs - dy * sn, c.y() + dx * sn + dy * cs)


def _box_drag(item, kind, key, lp, host):
    """[2c] 박스 리사이즈 한 번 시뮬레이트(press→move→release) + geom undo 커밋.
    [그리드] 이 헬퍼는 순수 리사이즈 수학을 검증하는 용도라 격자 스냅(기본 켜짐)을 끈다 —
    격자 자체 검증은 test_grid_snap_box_resize_* 가 별도로 담당한다."""
    host.grid_enabled = False
    item._begin_box_geom()
    item._box_resize = (kind, key)
    item._apply_box_resize(lp)
    snap = item._box_snap
    item._box_resize = None
    item._box_snap = None
    item._box_bound = None
    item._box_orig_rect = None
    if snap:
        host.push_undo_geom(snap)


def _qc_drag(view, scene_from, scene_to):
    """겸용 변 점(qc-dot) press→move→release 시뮬레이트(실제 QMouseEvent 경유)."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, scene_from, L, L))
    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, scene_to, NB, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, scene_to, L, NB))


def _snap_scene_rect(o):
    # [2026-08-10] `_apply_smart_snap`의 `srect()`/`_GroupTransform.bbox()`와 동일 기준 —
    # 사각형·심볼·타원은 `_tight_scene_bbox`(패딩 없는 실제 외곽선), 그 외 타입은
    # `_content_rect()` 폴백. 예전엔 이 헬퍼들이 `_content_rect()`(펜폭/2 패딩)를 그대로
    # 썼는데, 그건 딱 그 스냅 구현이 쓰던 값이라 "정답"처럼 보였을 뿐 실제 테두리 위치는
    # 아니었다(펜폭 1.0 → 0.5유닛 어긋남, 4354% 줌에서 실사용으로 드러남).
    return _tight_scene_bbox(o) or o.mapToScene(o._content_rect()).boundingRect()


def _cleft(o):
    return _snap_scene_rect(o).left()


def _ctop(o):
    return _snap_scene_rect(o).top()


def _cbottom(o):
    return _snap_scene_rect(o).bottom()


def _cright(o):
    return _snap_scene_rect(o).right()


def _rect_world_corners(it):
    r = it.rect()
    pts = [(r.left(), r.top()), (r.right(), r.top()), (r.right(), r.bottom()), (r.left(), r.bottom())]
    return sorted((round(it.mapToScene(QPointF(x, y)).x(), 1),
                   round(it.mapToScene(QPointF(x, y)).y(), 1)) for x, y in pts)


def _mk_pixmap(w=40, h=20, color="#3366cc"):
    pm = QPixmap(w, h)
    pm.fill(QColor(color))
    return pm


def _mk_pen_rect(w, x=0, y=0, ww=40, hh=30, width=2.0, color="#111111"):
    from PyQt6.QtGui import QPen
    it = _RectItem(QRectF(x, y, ww, hh))
    it.setPen(QPen(QColor(color), width))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def _mk_bound_sarrow(w, a, b, pa, pb):
    """[M4-4 ⓐ 잔여] 두 도형의 포트(N=0·E=1·S=2·W=3)를 잇는 자동라우팅 직각 커넥터."""
    sp = _shape_ports(a)[pa][0]
    ep = _shape_ports(b)[pb][0]
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(sp, ep)
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, sp); sa.set_bound(1, b, ep)
    sa._auto_route = True
    sa.build_elbow()
    return sa


def _sarrow_defects(sa):
    """(재진입 여부, 타기 길이) — 연결 도형 bbox 기준. 둘 다 0이어야 깨끗한 경로."""
    from easycad.canvas.annotator_core import _path_hits_rects, _path_ride_len
    pts = [sa.mapToScene(p) for p in sa._pts]
    pairs = [(sh.mapRectToScene(sh.rect()), o)
             for sh, o in ((sa._bind_start, "start"), (sa._bind_end, "end"))
             if isinstance(sh, (_RectItem, _EllipseItem, _SymbolItem))]
    ns = sa._bound_normal_scene(0); ne = sa._bound_normal_scene(len(sa._pts) - 1)
    return (_path_hits_rects(pts, [r for r, _ in pairs]),
            _path_ride_len(pts, pairs, ns, ne))


def _mods_event(etype, view, scene_pt, modifiers):
    """지정한 모디파이어를 실은 합성 마우스 이벤트(뷰 좌표로 변환해 생성)."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    vp = QPointF(view.mapFromScene(scene_pt))
    if etype == "press":
        return QMouseEvent(QEvent.Type.MouseButtonPress, vp, vp,
                            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, modifiers)
    return QMouseEvent(QEvent.Type.MouseMove, vp, vp,
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, modifiers)


def _mk_arrow(w, x1, y1, x2, y2, color="#111111"):
    ar = _ArrowItem(QColor(color), 2, True)
    ar.set_points(QPointF(x1, y1), QPointF(x2, y2))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    return ar


@contextmanager
def _isolated_symbol_library():
    """[§8-8] symbol_library가 실제 사용자 AppData가 아니라 격리된 임시 파일에 읽고 쓰게
    한다 — 테스트가 실제 팔레트 라이브러리를 오염시키지 않도록."""
    from easycad.fileio import symbol_library
    path = os.path.join(_TMP, f"symlib_{uuid.uuid4().hex}.json")
    with patch.object(symbol_library, "_library_path", return_value=path):
        yield


@contextmanager
def _isolated_shortcuts():
    """[실사용 요청 2026-08-21] 단축키 설정을 매 테스트 시작/종료에 초기화 — `_shortcuts.
    _SETTINGS_ORG/_APP`은 이미 격리값("EasyCAD-pytest")이라 실사용자 설정은 안 건드리지만,
    그 격리된 그룹 자체엔 이전 테스트 실행이 남긴 값이 계속 쌓일 수 있어(디스크/레지스트리에
    실제로 저장되므로) 테스트 간 서로 오염되지 않게 항상 리셋한다."""
    from easycad.canvas import shortcuts
    shortcuts.reset_all()
    try:
        yield
    finally:
        shortcuts.reset_all()


def _mock_color_dialog_exec(picked: QColor):
    """QColorDialog.exec()을 실제 모달 없이 '사용자가 picked를 고르고 확인' 상태로
    흉내낸다 — done(Accepted) 후 selectedColor()가 그 색을 돌려주는 걸 실측 확인(2026-07-31)."""
    from PyQt6.QtWidgets import QColorDialog, QDialog
    def fake_exec(self):
        self.setCurrentColor(picked)
        self.done(QDialog.DialogCode.Accepted)
        return QDialog.DialogCode.Accepted
    return fake_exec


# `from _shared import *`가 언더스코어 접두 이름(클래스·헬퍼 전부)까지 넘겨받게 강제.
# __all__이 없으면 `import *`는 기본적으로 밑줄로 시작하는 이름을 제외하는데, 이 모듈의
# 실질적 export 전부(_RectItem·_ArrowItem·_close·_mk_rect 등)가 밑줄 접두라 반드시 필요하다.
__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]

