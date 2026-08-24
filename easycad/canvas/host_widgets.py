"""CanvasWindow과 무관한 독립 위젯·헬퍼 — 팔레트 버튼/미니맵 뷰/플로팅 패널/토스트/
색상 그리드 팝업 및 이들이 쓰는 아이콘·팔레트·다크테마·타입명 상수.

2026-08-02 host.py(3635줄) 분할분. CanvasWindow의 믹스인들(host_ui.py 등)이 이 모듈을
가져다 쓰고, host.py 자신도 __init__에서 일부(_ToastLabel/_UndoEntry/_SCENE_HALF)를 쓴다.
순환 임포트를 피하려고 이 파일은 host.py나 믹스인 쪽을 임포트하지 않는 잎(leaf) 모듈이다.
"""
from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QSize, QSettings, QTimer, QMimeData, QEvent, pyqtSignal,
)
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter,
    QPolygonF, QPainterPath, QPalette, QDrag, QFont,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPlainTextEdit,
    QSizePolicy, QColorDialog, QHBoxLayout, QMenu, QFrame,
    QListWidget, QListWidgetItem, QToolTip,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon, _nearest_border,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
    _svg_icon_pixmap, _min_stroke_render,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document, load_document_layers
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)


_MERMAID_SHAPE_ITEM = {
    "rect":          ("rect", None),
    "rounded":       ("rect", None),
    "stadium":       ("symbol", "terminal"),
    "rhombus":       ("symbol", "decision"),
    "hexagon":       ("symbol", "prep"),
    "parallelogram": ("symbol", "data"),
    "cylinder":      ("symbol", "database"),
    "circle":        ("ellipse", None),
}


# [Phase 6 M3 #17] 팔레트 드래그앤드롭 — 좌측 「도형·심볼」 버튼을 캔버스로 끌어 드롭.
_PALETTE_MIME = "application/x-easycad-tool"      # QDrag가 실어 나르는 tool_key 포맷
_PALETTE_DROP_WH = {"rect": (120.0, 72.0), "ellipse": (100.0, 100.0)}  # 기본 생성 크기
_PALETTE_SYM_WH = (120.0, 72.0)                   # 심볼(sym:*) 공통 기본 크기


class _PaletteButton(QToolButton):
    """[Phase 6 M3 #17] 좌측 팔레트 버튼 — 클릭=도구 무장(기존 clicked 유지) /
    임계(px)를 넘게 끌면 캔버스에 도형을 드롭 생성한다. 드래그 시엔 release가
    버튼에 안 와 clicked가 발화하지 않으므로 무장되지 않는다(의도 — 드래그와 무장 분리).

    [2026-08-19, 실사용 피드백] 임계를 넘는 순간 우선 `drag_begin_fn`(host_fileio.py
    `_palette_drag_begin`)을 불러 씬에 진짜 임시 도형을 만들 수 있는지 묻는다 — 되면
    이 버튼이 `grabMouse()`로 전역 마우스를 잡아 `drag_move_fn`/`drag_end_fn`으로 캔버스
    쪽에 좌표만 계속 통보한다(정렬 스냅이 기존 도형 이동과 똑같이 드래그 도중에도
    실시간으로 걸리게 하려는 설계 — 네이티브 `QDrag`는 OS가 고스트를 그려 앱이 위치를
    되돌릴 수 없어 이 체감을 못 냈다). False면(포트·커스텀심볼처럼 별도 배치 로직이
    있는 tool_key) 기존 네이티브 `QDrag` 경로로 폴백한다."""
    _DRAG_THRESH = 6

    def __init__(self, tool_key: str, parent=None, preview_fn=None,
                 drag_begin_fn=None, drag_move_fn=None, drag_end_fn=None,
                 tooltip_html_fn=None):
        super().__init__(parent)
        self._drag_tool_key = tool_key
        self._drag_press = None
        self._preview_fn = preview_fn   # [UX] 실물 미리보기 렌더 콜백(host._render_drag_preview) — 네이티브 폴백용
        self._drag_begin_fn = drag_begin_fn   # (tool_key) -> bool
        self._drag_move_fn = drag_move_fn     # (tool_key, global_pos: QPoint) -> None
        self._drag_end_fn = drag_end_fn       # (tool_key, global_pos: QPoint) -> None
        self._dragging = False   # 실물 드래그(씬 임시 도형) 진행 중 — grabMouse 소유 여부와 동일
        # [실사용 피드백 2026-08-19] 호버 확대 미리보기 — () -> HTML str, 지연 계산(전 항목을
        # 매 새로고침마다 렌더하면 심볼이 늘수록 비용이 커진다). None이면 평범한 setToolTip.
        self._tooltip_html_fn = tooltip_html_fn

    def event(self, e):
        if self._tooltip_html_fn is not None and e.type() == QEvent.Type.ToolTip:
            QToolTip.showText(e.globalPos(), self._tooltip_html_fn(), self)
            return True
        return super().event(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            if self._drag_move_fn:
                self._drag_move_fn(self._drag_tool_key, e.globalPosition().toPoint())
            return
        if (self._drag_press is not None and (e.buttons() & Qt.MouseButton.LeftButton)
                and (e.position().toPoint() - self._drag_press).manhattanLength()
                >= self._DRAG_THRESH):
            self._drag_press = None
            self.setDown(False)   # 드래그로 release를 못 받으니 눌림 상태 수동 해제
            started = self._drag_begin_fn(self._drag_tool_key) if self._drag_begin_fn else False
            if started:
                self._dragging = True
                self.grabMouse()
                if self._drag_move_fn:
                    self._drag_move_fn(self._drag_tool_key, e.globalPosition().toPoint())
            else:
                self._start_palette_drag()   # 폴백 — 포트·커스텀심볼 등
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_press = None
        if self._dragging:
            self._dragging = False
            self.releaseMouse()
            if self._drag_end_fn:
                self._drag_end_fn(self._drag_tool_key, e.globalPosition().toPoint())
            return
        super().mouseReleaseEvent(e)

    def _start_palette_drag(self):
        drag = QDrag(self)
        md = QMimeData()
        md.setData(_PALETTE_MIME, self._drag_tool_key.encode("utf-8"))
        drag.setMimeData(md)
        pm = self._preview_fn(self._drag_tool_key) if self._preview_fn else None
        if pm is None or pm.isNull():
            pm = self.icon().pixmap(QSize(30, 30))   # 폴백 — 미리보기 렌더 불가 시 기존 아이콘
        if not pm.isNull():
            drag.setPixmap(pm)
            drag.setHotSpot(QPoint(pm.width() // 2, pm.height() // 2))
        # setDown(False)는 호출부(mouseMoveEvent)가 분기 전에 이미 했다(드래그로 release를
        # 못 받으니 눌림 상태 수동 해제 — 네이티브 폴백·실물 드래그 두 경로 공통이라 위로 옮김).
        drag.exec(Qt.DropAction.CopyAction)


def _clipboard_pixmap() -> QPixmap | None:
    """[신규기능] 시스템 클립보드 이미지 → QPixmap. 표준 포맷(PNG 등)은 Qt가 pixmap()/
    image()로 직접 해석하고, Qt가 못 알아보는 raw 포맷(예: 헤더 없는 CF_DIB)만
    `_pixmap_from_data`(annotator_core, clipboard_monitor 이식 로직)로 폴백한다."""
    cb = QApplication.clipboard()
    pm = cb.pixmap()
    if not pm.isNull():
        return pm
    img = cb.image()
    if not img.isNull():
        return QPixmap.fromImage(img)
    md = cb.mimeData()
    for fmt in md.formats():
        if fmt.startswith("image/"):
            pm2 = _pixmap_from_data(bytes(md.data(fmt)))
            if pm2 is not None:
                return pm2
    return None


def _border_attach(rect_scene: QRectF, toward: QPointF) -> QPointF:
    """rect(scene)의 변 중점 중 toward 방향에 면한 점 — 화살표 부착점. 회전 없는 import
    도형이라 외접 사각형 변 중점으로 충분(_PolyArrowItem이 이후 직교 라우팅으로 다듬음)."""
    c = rect_scene.center()
    dx, dy = toward.x() - c.x(), toward.y() - c.y()
    if abs(dx) >= abs(dy):
        x = rect_scene.right() if dx >= 0 else rect_scene.left()
        return QPointF(x, c.y())
    y = rect_scene.bottom() if dy >= 0 else rect_scene.top()
    return QPointF(c.x(), y)

# 무한 캔버스: 아주 큰 sceneRect로 사실상 무한한 팬 범위 제공.
_SCENE_HALF = 50000.0


class _SharedClipboard:
    """[§8 항목10, 2026-08-18] 도형 클립보드 + 스타일 복사(format painter) — 여러 창이 실시간
    으로 공유할 수 있는 그릇(deep-interview 확정: "새 창"에서도 어디서 복사해도 어디든
    붙여넣기 가능해야 함). 모듈 레벨 싱글턴이 아니라 `CanvasWindow.__init__`이 매번 새
    인스턴스를 만든다 — 독립적으로 생성된 창(앱 시작·테스트의 `CanvasWindow()`)은 서로
    다른 인스턴스를 가져 완전히 격리되고, "새 창"(§8 항목10 Stage D)만 부모 창의 인스턴스를
    그대로 넘겨받아(생성자 인자) 진짜 라이브 공유가 된다. 처음에 모듈 레벨 싱글턴으로
    구현했다가 기존 테스트가 `CanvasWindow()`를 여러 번 만들 때마다 서로 클립보드를
    공유해버려(오염) 되돌렸다 — `docs/pitfalls.md` 참조 예정."""

    def __init__(self):
        self.clip: list = []
        self.clip_src: list = []
        self.style: dict | None = None


# [Phase 6 M1] 파일·보기 액션 아이콘 색(단색). 다크모드 도입 시 팔레트 기반으로 승격 예정.
_ICON_COLOR = QColor("#39434f")

# [디자인 베이크오프 2026-08-02] 코랄(Claude 브랜드톤) — 다크/라이트 공통 고정 accent.
# 여러 파일에서 "#da7756" 리터럴로 이미 반복 중이지만(host_ui.py `_apply_theme` 등),
# 접기 화살표·"+" 버튼처럼 테마 전환 로직 밖에서 한 번만 칠하는 곳은 이 상수를 쓴다.
_ACCENT_CORAL = "#da7756"


# [디자인 베이크오프 2라운드, 2026-08-02] 코랄 듀오톤 SVG로 새로 그린 액션 이름 —
# 상단 QToolBar에 실제로 노출되는 것들. 메뉴 전용(pdf/image/table/titleblock/mermaid/
# zoom_fit/zoom_100)은 이번 라운드 스코프 밖이라 아래 QPainter 코드를 그대로 유지.
_SVG_ACT_ICON_NAMES = frozenset({
    "new", "open", "save", "undo", "redo", "snap", "ortho", "grid", "theme", "help", "pin",
    # [§8 항목18 후속, 2026-08-12] AI 게이트웨이 설정·Mermaid 다이얼로그 아이콘화 요청으로 추가.
    "refresh", "settings", "generate", "connect",
    # [2026-08-20 실사용 버그 수정] "align"은 toolbar 노출 대상인데도 SVG/글리프 어디에도
    # 없어 완전히 빈 아이콘으로 그려지고 있었다(`align.svg` 신설로 수정).
    "align",
    # ["attach" 2026-08-20 제거 — 첨부 버튼이 이 SVG 클립 아이콘 대신 "+" 정사각 버튼으로
    # 바뀌어(`_ImageAttachMixin._build_attach_button`) 마지막 참조가 사라짐, `attach.svg`도 삭제.]
})


_ACT_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def _act_icon(name: str) -> QIcon:
    """[Phase 6 M1] 파일/삽입/보기 액션 아이콘. 상단바 노출 11종(`_SVG_ACT_ICON_NAMES`)은
    2026-08-02부터 SVG(`easycad/resources/icons/`)를 래스터화 — 나머지(메뉴 전용)는 기존
    QPainter 단색 라인 글리프 그대로(좌표는 icon_proposal 아티팩트에서 포팅). [같은 날 4차
    피드백] SVG 11종도 도형 팔레트와 같은 테마 적응 중립색(`_ICON_COLOR`)으로 재칠 — 아이콘
    색은 이제 상단바 전체가 중립, "활성 상태"만 버튼 배경 코랄 틴트가 담당한다.

    결과를 (이름, 현재 색) 키로 캐시한다 — 이전엔 매 호출마다 픽스맵을 새로 만들었는데,
    `_apply_theme()`가 매 CanvasWindow 생성·매 테마 전환마다 `_icon_actions` 전부(약 18개)에
    대해 이 함수를 다시 부른다. 불필요한 재작업을 없애 성능상 이득(디버깅 중 실측: 스모크
    전체 실행에서 `_svg_icon_pixmap` 호출이 캐시 없이도 36회로 이미 작았다 — 세그폴트의
    실제 원인은 호출 횟수가 아니라 `_svg_icon_pixmap` 내부의 재칠 방식이었다, 그쪽 함정
    주석 참조. 이 캐시는 그 수정과 별개로 유효한 성능 개선이라 남겨둠)."""
    key = (name, _ICON_COLOR.name())
    cached = _ACT_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    if name in _SVG_ACT_ICON_NAMES:
        pm = _svg_icon_pixmap(name, 24, color=_ICON_COLOR)
        icon = _finish_act_icon(pm)
        _ACT_ICON_CACHE[key] = icon
        return icon
    pm = QPixmap(24, 24)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = _ICON_COLOR
    p.setPen(QPen(col, 1.7, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)

    def line(x1, y1, x2, y2):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def poly(pts, close=True):
        pg = QPolygonF([QPointF(x, y) for x, y in pts])
        p.drawPolygon(pg) if close else p.drawPolyline(pg)

    if name == "pdf":
        poly([(6, 3.5), (13.5, 3.5), (17.5, 7.5), (17.5, 20.5), (6, 20.5)])
        poly([(13.5, 3.5), (13.5, 7.5), (17.5, 7.5)], close=False)
        p.save()
        p.setPen(QPen(col, 1.3, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        line(8.5, 15.5, 8.5, 11.5); line(8.5, 11.5, 10.7, 11.5)   # 'P' 힌트
        line(13, 15.5, 13, 11.5); line(15, 11.5, 15, 15.5)        # 'D' 힌트
        p.restore()
    elif name == "image":
        p.drawRoundedRect(QRectF(4, 5, 16, 14), 2, 2)
        p.save(); p.setBrush(col); p.setPen(QPen(col, 1))
        p.drawEllipse(QPointF(9, 10), 1.7, 1.7); p.restore()
        poly([(4, 16.5), (9.5, 12), (13, 15), (16, 12.5), (20, 16.5)], close=False)
    elif name == "table":
        p.drawRoundedRect(QRectF(4, 5, 16, 14), 1.5, 1.5)
        line(4, 10, 20, 10); line(4, 14.5, 20, 14.5); line(11, 5, 11, 19)
    elif name == "titleblock":
        p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 1, 1)
        line(12, 14.5, 20, 14.5); line(16, 14.5, 16, 19)
    elif name == "mermaid":
        p.drawRoundedRect(QRectF(3.5, 4, 7.5, 5), 1.5, 1.5)
        p.drawRoundedRect(QRectF(13, 15, 7.5, 5), 1.5, 1.5)
        path = QPainterPath(QPointF(11, 6.5))
        path.lineTo(15, 6.5); path.quadTo(17, 6.5, 17, 8.5); path.lineTo(17, 15)
        p.drawPath(path)
    elif name == "zoom_fit":
        poly([(4, 8), (4, 4), (8, 4)], close=False)
        poly([(16, 4), (20, 4), (20, 8)], close=False)
        poly([(20, 16), (20, 20), (16, 20)], close=False)
        poly([(8, 20), (4, 20), (4, 16)], close=False)
    elif name == "zoom_100":
        p.drawEllipse(QPointF(10.5, 10.5), 5, 5)
        line(14.2, 14.2, 19.5, 19.5)
    elif name == "copy":
        # [2026-08-20, SVG 창 "프롬프트 복사" 버튼 아이콘화] 겹친 종이 두 장 — 표준 복사
        # 픽토그램. 겹치는 자리의 선 교차는 이 앱의 다른 단순 라인 아이콘(mermaid 등)과
        # 같은 수준이라 별도 배경 지우기 없이 허용.
        p.drawRoundedRect(QRectF(4, 3, 12, 15), 1.5, 1.5)
        p.drawRoundedRect(QRectF(8, 7, 12, 15), 1.5, 1.5)
    elif name == "check":
        # [2026-08-20] 아이콘 전용 버튼의 "완료" 순간 피드백(예: 프롬프트 복사됨) — 텍스트
        # 라벨을 못 쓰는 자리에서 아이콘을 잠깐 이걸로 바꿔 보여준다.
        path = QPainterPath(QPointF(5, 12.5))
        path.lineTo(9.5, 17.5)
        path.lineTo(19, 6)
        p.drawPath(path)
    elif name == "stop":
        # [2026-08-25] AI SVG 생성 중 "AI로 생성" 버튼이 토글되는 취소 아이콘 — 미디어
        # 플레이어 관례의 정지(■) 픽토그램.
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(6.5, 6.5, 11, 11), 2, 2)
    elif name in ("align_left", "align_hcenter", "align_right"):
        # [2026-08-23, 정렬/분배 메뉴 아이콘화] 폭이 다른 막대 3개를 기준선에 맞춘 모양 —
        # 점선 기준선 + 그 선에 닿는 막대들로 "이 선에 맞춘다"는 뜻을 직관적으로 전달.
        widths = (7.0, 13.0, 10.0)
        ys = (5.0, 10.5, 16.0)
        if name == "align_left":
            guide_x = 5.0; xs = [guide_x] * 3
        elif name == "align_right":
            guide_x = 19.0; xs = [guide_x - w for w in widths]
        else:
            guide_x = 12.0; xs = [guide_x - w / 2.0 for w in widths]
        p.save()
        p.setPen(QPen(col, 1.2, Qt.PenStyle.DashLine))
        line(guide_x, 2.5, guide_x, 21.5)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(col)
        for x, y, w in zip(xs, ys, widths):
            p.drawRoundedRect(QRectF(x, y, w, 2.6), 1.0, 1.0)
        p.restore()
    elif name in ("align_top", "align_vcenter", "align_bottom"):
        heights = (7.0, 13.0, 10.0)
        xs = (5.0, 10.5, 16.0)
        if name == "align_top":
            guide_y = 5.0; ys = [guide_y] * 3
        elif name == "align_bottom":
            guide_y = 19.0; ys = [guide_y - h for h in heights]
        else:
            guide_y = 12.0; ys = [guide_y - h / 2.0 for h in heights]
        p.save()
        p.setPen(QPen(col, 1.2, Qt.PenStyle.DashLine))
        line(2.5, guide_y, 21.5, guide_y)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(col)
        for x, y, h in zip(xs, ys, heights):
            p.drawRoundedRect(QRectF(x, y, 2.6, h), 1.0, 1.0)
        p.restore()
    elif name in ("dist_even_h", "dist_gap_h"):
        # 균등 분배=크기가 다른 막대를 같은 틈으로 편 모양. 첫간격기준 분배=같은 크기
        # 막대+같은 틈+끝에 화살표(그 간격대로 계속 이어짐)로 구분.
        same_size = (name == "dist_gap_h")
        widths = (3.0, 3.0, 3.0) if same_size else (3.0, 8.0, 5.0)
        gap = 3.0 if same_size else 2.0
        p.save()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(col)
        x = 3.0
        for w in widths:
            p.drawRoundedRect(QRectF(x, 9.5, w, 5.0), 1.0, 1.0)
            x += w + gap
        if same_size:
            p.setPen(QPen(col, 1.5, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            line(x - gap + 0.5, 12.0, 21.0, 12.0)
            poly([(21.0, 12.0), (18.3, 10.2), (18.3, 13.8)])
        p.restore()
    elif name in ("dist_even_v", "dist_gap_v"):
        same_size = (name == "dist_gap_v")
        heights = (3.0, 3.0, 3.0) if same_size else (3.0, 8.0, 5.0)
        gap = 3.0 if same_size else 2.0
        p.save()
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(col)
        y = 3.0
        for h in heights:
            p.drawRoundedRect(QRectF(9.5, y, 5.0, h), 1.0, 1.0)
            y += h + gap
        if same_size:
            p.setPen(QPen(col, 1.5, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            line(12.0, y - gap + 0.5, 12.0, 21.0)
            poly([(12.0, 21.0), (10.2, 18.3), (13.8, 18.3)])
        p.restore()
    p.end()
    icon = _finish_act_icon(pm)
    _ACT_ICON_CACHE[key] = icon
    return icon


def _finish_act_icon(pm: QPixmap) -> QIcon:
    """공통 마무리 — 래스터화된 픽스맵(QPainter 그림 또는 SVG 래스터)을 QIcon으로 감싼다.
    [M2 #1] 비활성 상태 아이콘을 뚜렷하게 흐리게 — baked 단색 픽스맵은 Qt 기본 비활성
    처리가 약해 사용자가 활성/비활성을 구분하기 어려웠다(되돌리기 버튼 피드백). 저알파 사본을
    Disabled 모드로 명시 등록해 확실히 흐려 보이게 한다."""
    icon = QIcon(pm)
    dim = QPixmap(pm.size()); dim.fill(Qt.GlobalColor.transparent)
    dp = QPainter(dim); dp.setOpacity(0.30); dp.drawPixmap(0, 0, pm); dp.end()
    icon.addPixmap(dim, QIcon.Mode.Disabled, QIcon.State.Off)
    icon.addPixmap(dim, QIcon.Mode.Disabled, QIcon.State.On)
    return icon


# [Phase 6 M1] 캔버스 배경 — 테마별. 다크는 CAD 관습대로 어두운 모델공간.
_CANVAS_BG = {"dark": QColor("#1e2731"), "light": QColor("#ffffff")}
# [실사용 피드백 2026-08-20] 다크 테마 중립색을 은은한 오프화이트(#cdd8e3)에서 순백으로
# 환원 — 작은 아이콘(속성패널 선/화살표 콤보 등)이 이 색으로 그려지는데 옅은 톤이라 잘 안
# 보인다는 지적. 짙은 네이비 배경(#1e2731)에서 순백이 눈부실 정도는 아니라고 판단, 미묘한
# 눈편안함보다 작은 요소의 가독성을 우선(사용자 확인). `_dark_palette()`의 텍스트색도 같은
# 이유로 함께 환원.
# [같은 이유, 같은 날 후속] 라이트 테마는 그때 짙은 네이비 계열(#39434f, 순검정 아님)로
# 남겨뒀었는데, 다크 쪽만 순백으로 끝까지 밀어붙인 것과 대칭이 안 맞는다는 재지적 —
# 같은 "미묘함보다 가독성" 판단을 라이트에도 그대로 적용해 순검정으로 환원.
_ICON_COLOR_THEME = {"dark": QColor("#ffffff"), "light": QColor("#000000")}


def _set_icon_color(dark: bool) -> QColor:
    """[2026-08-02 버그 수정] 전역 아이콘 중립색을 테마에 맞게 갱신하는 유일한 통로.
    예전엔 `host_ui.py`의 `_apply_theme`가 `global _ICON_COLOR; _ICON_COLOR = ...`로 직접
    재바인딩했는데, 이는 `from host_widgets import _ICON_COLOR`로 이름을 가져간 host_ui.py
    **자신의** 로컬 사본만 바꿀 뿐이다(파이썬의 `from import`는 import 시점 스냅샷이라 원본
    모듈의 재바인딩이 반영 안 됨) — 이 모듈(host_widgets) 자신의 `_ICON_COLOR`는 그대로 남아,
    여기서 그 이름을 직접 참조하는 `_act_icon()`의 메뉴 전용 아이콘(pdf/image/table 등)이
    테마 전환 후에도 항상 초기값(라이트 톤)으로 그려지고 있었다(실측 확인). 이제 이 함수로만
    갱신하고, 읽을 땐 `_current_icon_color()`를 쓴다 — 두 모듈(host_ui.py/host_style.py) 모두
    이 getter를 호출 시점에 매번 실행해 항상 최신값을 받는다."""
    global _ICON_COLOR
    _ICON_COLOR = QColor(_ICON_COLOR_THEME["dark" if dark else "light"])
    return _ICON_COLOR


def _current_icon_color() -> QColor:
    return _ICON_COLOR


# [실사용 피드백 2026-08-21] QMenu 구분선이 Fusion 팔레트 계산값으론 배경과 거의 구별이
# 안 갔다(실측 확인 — `R.Mid`를 포함해 시도한 팔레트 롤 어느 것도 Fusion의 분리선 렌더에
# 영향을 안 줬다). `QMenu::separator` QSS는 확실히 먹히지만(실측 확인), `self`/QApplication에
# 걸면 그 하위 위젯 전부(형제 QAbstractSpinBox 포함)가 QStyleSheetStyle로 강제 전환돼
# sizeHint가 깨지는 기존 함정(`docs/pitfalls.md` "렌더링" — 스핀박스 sizeHint 사고와 같은
# 클래스)을 재현한다(실측으로 재현·확인) — 대신 QMenu 인스턴스 각각에 직접 건다(팝업은
# 메인윈도우 자식 트리 밖의 독립 최상위 위젯이라 다른 위젯에 안 번진다, 실측 확인:
# `_pf_width` 높이 무변화). 이 모듈이 색만 들고, `QMenu(...)`를 만드는 모든 곳
# (host_context/host_layers/host_ui)이 생성 직후 `_style_menu_separators(menu)`를 호출한다.
_MENU_SEP_COLOR_THEME = {"dark": "#3d4b5c", "light": "#c9d3dc"}
_MENU_SEP_COLOR = _MENU_SEP_COLOR_THEME["dark"]


def _set_menu_sep_color(dark: bool) -> None:
    global _MENU_SEP_COLOR
    _MENU_SEP_COLOR = _MENU_SEP_COLOR_THEME["dark" if dark else "light"]


def _style_menu_separators(menu) -> None:
    menu.setStyleSheet(
        f"QMenu::separator {{ background:{_MENU_SEP_COLOR}; height:1px; margin:4px 8px; }}")


def _dark_palette() -> QPalette:
    """다크 테마 팔레트(Fusion 스타일과 함께 쓰면 전 위젯에 안정 적용)."""
    c = QColor
    p = QPalette()
    R = QPalette.ColorRole
    p.setColor(R.Window, c("#171e26"));         p.setColor(R.WindowText, c("#ffffff"))
    p.setColor(R.Base, c("#0e1319"));           p.setColor(R.AlternateBase, c("#1d2632"))
    p.setColor(R.Text, c("#ffffff"));           p.setColor(R.PlaceholderText, c("#78889a"))
    p.setColor(R.Button, c("#1d2632"));         p.setColor(R.ButtonText, c("#ffffff"))
    p.setColor(R.ToolTipBase, c("#232f3d"));    p.setColor(R.ToolTipText, c("#ffffff"))
    # [디자인 베이크오프 2026-08-02] accent를 블루(#54a9ff/#2f6dbf)에서 코랄(Claude 브랜드톤)로 교체.
    p.setColor(R.Highlight, c("#a8583a"));      p.setColor(R.HighlightedText, c("#ffffff"))
    p.setColor(R.Link, c("#da7756"))
    D = QPalette.ColorGroup.Disabled
    p.setColor(D, R.Text, c("#5a6675"));        p.setColor(D, R.ButtonText, c("#5a6675"))
    p.setColor(D, R.WindowText, c("#5a6675"))
    return p


def _light_palette() -> QPalette:
    """라이트 테마 팔레트. [2026-08-02, 사용자 재현·버그 발견] 예전엔 `app.style().
    standardPalette()`(Fusion 기본값)를 그대로 썼는데, 이 PyQt6(6.10.2)/Windows 조합에서
    `styleHints().colorScheme()`가 OS 다크모드를 따라가 Fusion의 "표준" 팔레트 자체가
    다크(`Window #323232`)로 나왔다 — 라이트 토글이 캔버스 배경만 하얗게 바꾸고 패널
    본문·버튼·제목 텍스트·토스트 텍스트는 전부 다크 팔레트 색 그대로 남아 안 보이던 원인.
    다크 팔레트처럼 고정 색으로 명시해 OS 설정과 무관하게 만든다."""
    c = QColor
    p = QPalette()
    R = QPalette.ColorRole
    p.setColor(R.Window, c("#eef1f4"));         p.setColor(R.WindowText, c("#232a33"))
    p.setColor(R.Base, c("#ffffff"));           p.setColor(R.AlternateBase, c("#f4f6f8"))
    p.setColor(R.Text, c("#232a33"));           p.setColor(R.PlaceholderText, c("#8a94a0"))
    p.setColor(R.Button, c("#e5e9ed"));         p.setColor(R.ButtonText, c("#232a33"))
    p.setColor(R.ToolTipBase, c("#fffef2"));    p.setColor(R.ToolTipText, c("#232a33"))
    # [디자인 베이크오프 2026-08-02] 아이콘·버튼 accent가 다크/라이트 공통 코랄로 확정된 것과
    # 맞춰 팔레트 accent도 통일(예전엔 라이트만 블루 #1f7ae0 — 스코프 밖으로 남겨뒀던 것).
    p.setColor(R.Highlight, c("#da7756"));      p.setColor(R.HighlightedText, c("#ffffff"))
    p.setColor(R.Link, c("#da7756"))
    D = QPalette.ColorGroup.Disabled
    p.setColor(D, R.Text, c("#a3acb6"));        p.setColor(D, R.ButtonText, c("#a3acb6"))
    p.setColor(D, R.WindowText, c("#a3acb6"))
    return p


def _apply_native_titlebar_scheme(dark: bool) -> None:
    """[2026-08-13 피드백] Windows 네이티브 창 프레임(OS 타이틀바)은 `QPalette`가 못 닿는
    영역이라, 클라이언트 영역을 다크로 칠해도 타이틀바만 흰색으로 튄다. ctypes로 DWM
    (`DWMWA_USE_IMMERSIVE_DARK_MODE`/`DWMWA_CAPTION_COLOR`)을 직접 찔러본 시도 3종은 전부
    HRESULT 성공을 반환하고도 실제 창에서 시각 변화가 없었다(이 환경의 원격 화면 캡처가
    DWM 합성 효과를 못 잡는 것으로 추정 — 검증 자체가 이 환경에서 막힘). 대신 Qt 6.5+가
    제공하는 앱 전역 `styleHints().colorScheme()`을 쓴다 — 이건 Qt 자신이 내부적으로 같은
    DWM API를 호출해 신규·기존 창(다이얼로그 포함) 전체에 자동 반영하므로, 창마다 개별
    ctypes 호출을 걸 필요가 없다(macOS·구버전 Qt·Windows 10 구버전에서도 안전하게 무시됨).
    호출 시점: `_apply_theme`가 항상 다이얼로그 생성보다 먼저 실행되므로(앱 초기화 시
    1회 + 테마 토글마다) 여기 한 곳만 갱신하면 충분."""
    app = QApplication.instance()
    if app is None:
        return
    try:
        app.styleHints().setColorScheme(
            Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    except Exception:
        pass


# [Phase 6 M1] 속성 패널 표시용 — 아이템 클래스명 → 한글 종류, 펜 스타일 → 한글.
_TYPE_NAMES = {
    "_RectItem": "사각형", "_EllipseItem": "원", "_LineItem": "선",
    "_ArrowItem": "화살표", "_PolyArrowItem": "직선화살", "_TextItem": "텍스트",
    "_BadgeItem": "번호", "_PathItem": "펜", "_SymbolItem": "심볼",
    "_ImageItem": "이미지", "_TableItem": "표", "_TitleBlockItem": "표제란",
}
# [Phase 6 M2] one-shot 대상 도구 — 하나 그리면 자동으로 선택모드로 복귀(pin OFF일 때).
# 심볼(sym:*)은 prefix로 함께 처리. pen(자유 연속선)은 스트로크마다 해제되면 방해라 제외 —
# 연속으로 긋는 게 본질이므로 pin 없이도 무장 유지.
_ONESHOT_TOOLS = frozenset({"rect", "ellipse", "line", "arrow", "sarrow", "text", "badge"})

# [화살표 통합] 사용자에게 화살표는 하나 — 종류(직선·곡선·직각)는 선택 후 미니툴바에서 고른다.
# 내부적으로는 직선·곡선이 _ArrowItem(제어점 없음/있음), 직각이 _PolyArrowItem이라 그리기 도구만
# 종류에 따라 갈라 쓴다(사용자에겐 안 보임). 클래스를 합치지 않은 이유는 CLAUDE.md 참조.
_ARROW_KINDS = ("straight", "curved", "ortho")
_ARROW_KIND_LABELS = (("straight", "직선"), ("curved", "곡선"), ("ortho", "직각"))
_ARROW_KIND_TOOL = {"straight": "arrow", "curved": "arrow", "ortho": "sarrow"}


def _arrow_kind_of(item):
    """화살표 아이템의 현재 종류(straight/curved/ortho). 화살표가 아니면 None."""
    if isinstance(item, _PolyArrowItem):
        return "ortho" if item._is_ortho() else "straight"
    if isinstance(item, _ArrowItem):
        return "curved" if item._ctrl1 is not None else "straight"
    return None


# [양방향 화살표, 2026-08-21] 화살촉 위치 — _head_at_end/_head_at_start 두 독립 플래그의
# 조합을 사용자에게 보이는 4상태 하나로 표현(속성패널 아이콘 콤보용, _arrow_kind_of와 같은 관례).
_ARROW_HEAD_LABELS = (("none", "없음"), ("end", "끝만"), ("both", "양쪽"), ("start", "시작만"))


def _arrow_head_of(item):
    """화살표 아이템의 현재 화살촉 위치(none/end/both/start). 화살표가 아니면 None."""
    if not isinstance(item, (_ArrowItem, _PolyArrowItem)):
        return None
    e, s = bool(item._head_at_end), bool(getattr(item, "_head_at_start", False))
    if e and s:
        return "both"
    if e:
        return "end"
    if s:
        return "start"
    return "none"


def _is_rotatable(item) -> bool:
    """[신규기능 2026-08-21 회전각도] 회전 핸들·속성패널 회전 행의 공통 대상 판정 —
    끝점으로 모양을 정하는 도형(화살표·선·펜, `_uses_endpoints()` True)은 회전 핸들
    자체가 없다(core_shapes.py mousePressEvent 참조). `_HandleResizeMixin`을 아예 안 쓰는
    항목(예: `_TitleBlockItem`, 고정 크기)은 `_uses_endpoints` 속성 자체가 없어 함께 걸러진다."""
    return hasattr(item, "_uses_endpoints") and not item._uses_endpoints()


def _apply_arrow_head(item, kind: str):
    """`_arrow_head_of`의 역함수 — 화살표 아이템에 4상태 중 하나를 적용."""
    if kind == "both":
        item.set_head_at_end(True); item.set_head_at_start(True)
    elif kind == "start":
        item.set_head_at_end(False); item.set_head_at_start(True)
    elif kind == "none":
        item.set_head_at_end(False); item.set_head_at_start(False)
    else:   # "end"
        item.set_head_at_end(True); item.set_head_at_start(False)


class _UndoEntry:
    """[Phase 6 M2] 되돌리기/다시 실행의 원자 단위 — per-item 연산 리스트 하나.
    연산(op)은 딱 3종의 튜플:
      ("create", item)                        undo=씬에서 제거  / redo=씬에 추가
      ("remove", item)                        undo=씬에 추가    / redo=제거
      ("mut", item, sub, before, after)       undo=apply(before)/ redo=apply(after)
        sub ∈ {"pos","xform","geom","state"} — 각 sub가 복원 전략을 고른다.
    key: 연속 변이 병합용(같은 key면 직전 엔트리에 흡수, before 유지·after 갱신).
    이 단일 저널이 기존 add/delete/move/xform/geom 5종을 흡수하고 redo를 대칭으로 얻는다."""

    __slots__ = ("ops", "key")

    def __init__(self, ops, key=None):
        self.ops = ops
        self.key = key


class _MinimapView(QGraphicsView):
    """[미니맵] 메인 뷰와 같은 QGraphicsScene을 공유하는 축소 뷰. 자체 상호작용은 끄고
    (setInteractive(False)) 클릭/드래그로 메인 뷰를 그 위치로 이동시키는 내비게이션만 한다.
    [성능 조사 스파이크 2026-07-30 실측] 매 paintEvent마다 itemsBoundingRect()를 캐시 없이
    재계산하던 게 무거운 도면(아이템 ~1600개)에서 71ms — dirty 플래그(`_bounds_dirty`)로
    캐시해 O(n) 매 페인트 → 상각 O(1)로 줄였다(`_refit`/`_mark_bounds_dirty`는 이 스파이크의
    유산, 아래 스냅샷 전환 이후에도 그대로 유지 — 관련 테스트 8종이 이 계약을 직접 검증한다).

    [성능 최적화 2026-08-08] 위 캐시로도 여전히 무거웠던 진짜 원인은 itemsBoundingRect()가
    아니라 **"같은 씬을 보는 QGraphicsView라 Qt가 scene.changed마다 이 뷰도 자동 repaint
    스케줄링한다"는 구조 자체** — `super().paintEvent()`가 매번 아이템 ~1600개를 축소 배율로
    다시 페인트했다(tools/perf_bench.py 실측: 드래그 127ms/frame 중 75%, 선택 클릭 178ms 중
    82%가 미니맵 몫 — 화면 5% 면적 위젯이 프레임 비용 대부분을 먹었다). 해법: 미니맵을
    '씬을 매 프레임 직접 그리는 뷰'에서 '저해상도 QPixmap 스냅샷을 blit만 하는 뷰'로 바꾼다.
    실제 씬 렌더(`scene().render()`)는 `_rebuild_pixmap()` 한 곳에서만 일어나고, 그 호출은
    내용이 실제로 바뀐 뒤 150ms 디바운스로 최대 1회만 실행된다(`_rebuild_timer`) — 드래그
    한 프레임 한 프레임마다가 아니라 "잠깐 멈췄을 때 한 번"으로 상각. 트레이드오프: 드래그
    도중엔 미니맵 그림이 최대 150ms 지연된다(인디케이터 사각형은 별도 경로라 즉시 따라감) —
    Figma/Lucid도 쓰는 절충이고, deep-interview에서 사용자 승인 받음(2026-08-08).
    `fitInView`가 세팅하는 `self.transform()`(mapToScene/mapFromScene의 기반)은
    `_rebuild_pixmap()` 안에서만 갱신되므로, 순수 인디케이터 갱신(메인 뷰 줌·팬)은 그 transform을
    그대로 재사용 — 미니맵 자신의 배율은 메인 뷰 줌과 무관하므로 정확하다."""

    _REBUILD_DEBOUNCE_MS = 150

    def __init__(self, owner, scene):
        super().__init__(scene)
        self._owner = owner
        self.setInteractive(False)   # 아이템 선택/드래그 차단 — 클릭은 내비게이션 전용
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMinimumHeight(120)
        self._bounds_cache = QRectF()
        self._bounds_dirty = True
        self._pixmap_cache: QPixmap | None = None
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(self._REBUILD_DEBOUNCE_MS)
        self._rebuild_timer.timeout.connect(self._rebuild_pixmap)
        scene.changed.connect(self._mark_bounds_dirty)

    def _mark_bounds_dirty(self, _regions=None):
        self._bounds_dirty = True
        self._rebuild_timer.start()   # 재시작 — 변경이 몰리는 동안은 계속 미룸(디바운스)

    def _padded_bounds(self) -> QRectF:
        rect = self._bounds_cache
        if rect.isEmpty():
            return QRectF()
        pad = max(rect.width(), rect.height()) * 0.06 + 12
        return rect.adjusted(-pad, -pad, pad, pad)

    def _refit(self):
        if self._bounds_dirty:
            self._bounds_cache = self.scene().itemsBoundingRect()
            self._bounds_dirty = False
        padded = self._padded_bounds()
        if padded.isEmpty():
            return
        self.fitInView(padded, Qt.AspectRatioMode.KeepAspectRatio)

    def _rebuild_pixmap(self):
        """실제로 씬을 그리는 유일한 지점 — 위 클래스 docstring 참조. `scene().render()`는
        `tools/perf_bench.py`가 측정하는 '뷰 렌더' 시나리오와 같은 API라 비용 성격이 동일하고,
        다른 점은 오직 '매 프레임'이 아니라 '디바운스당 최대 1회' 불린다는 것뿐이다.

        [실사용 버그 수정 2026-08-08, 2차] `KeepAspectRatio`로 맞추면 콘텐츠 bbox 종횡비가
        미니맵 위젯(16:9)과 다를 때 레터박스(위아래 또는 좌우 여백)가 생긴다. `QGraphicsScene.
        render()`는 target 인자를 '이 사각형 전체에 맞춰라'로 받지, `fitInView()`처럼 안에서
        알아서 center하지 않는다(실측 확인: target을 pm 전체로 주면 스케일된 콘텐츠가 좌측/
        상단에 붙어 반대쪽에만 배경색 여백이 몰림). 그래서 대상 사각형을 직접 계산해 pm
        중앙에 배치한다 — 원본이 `super().paintEvent()`(내부적으로 `fitInView`가 세팅한 변환을
        그대로 씀 → 자동 center)로 얻던 것과 같은 그림. 배경 채움색은 `self.scene().
        backgroundBrush()`(host_ui.py `_apply_theme`가 테마 전환마다 갱신하는 실제 캔버스
        배경 — `QPalette` 추측이 아니라 원본이 보여주던 값과 정확히 같은 소스, 실측 픽셀
        #1e2731로 일치 확인) — 사용자가 실제 창에서 "미니맵에 검정 부분"으로 발견한 원인
        (이전엔 투명이라 부모 패널의 다른 색/미초기화 픽셀이 비쳤다)을 없애고, 라이트/다크
        테마 전환에도 자동으로 맞는 색을 쓴다."""
        # [성능계획 2-D] 메인 뷰가 드래그 프록시 중이면 씬 아이템이 `ItemHasNoContents`라
        # `scene().render()`가 **빈 그림**을 만든다 — 그 빈 스냅샷을 캐시에 굳히면 미니맵이
        # 드래그 내내 비어 보인다. 드래그가 끝날 때까지 미룬다(디바운스 타이머 재시작).
        main = getattr(self._owner, "_view", None)
        if main is not None and getattr(main, "_drag_proxy", None) is not None:
            self._rebuild_timer.start()
            return
        self._refit()
        padded = self._padded_bounds()
        vp = self.viewport().size()
        if padded.isEmpty() or vp.isEmpty():
            self._pixmap_cache = None
            return
        pm = QPixmap(vp)
        pm.fill(self.scene().backgroundBrush().color())
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        sw, sh = padded.width(), padded.height()
        scale = min(vp.width() / sw, vp.height() / sh) if sw > 0 and sh > 0 else 1.0
        draw_w, draw_h = sw * scale, sh * scale
        target = QRectF((vp.width() - draw_w) / 2.0, (vp.height() - draw_h) / 2.0, draw_w, draw_h)
        # [실사용 피드백 2026-08-18] 축소 렌더라 1px(기본 두께) 선이 안 보임 — 렌더 순간만
        # 최소 두께로 임시 상향(실제 도형 데이터는 무변경, _min_stroke_render 참조).
        with _min_stroke_render(self.scene().items()):
            self.scene().render(painter, target, padded, Qt.AspectRatioMode.KeepAspectRatio)
        painter.end()
        self._pixmap_cache = pm
        self.viewport().update()

    def paintEvent(self, event):
        # 캐시가 없거나(최초 페인트) 위젯 크기가 바뀌었으면(리사이즈) 이번만 동기 재생성 —
        # 그 외엔 blit + 인디케이터만(아이템 페인트 없음, 이게 이번 최적화의 핵심).
        if self._pixmap_cache is None or self._pixmap_cache.size() != self.viewport().size():
            self._rebuild_pixmap()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)   # 인디케이터 테두리용
        if self._pixmap_cache is not None:
            painter.drawPixmap(0, 0, self._pixmap_cache)
        self._paint_indicator(painter)
        painter.end()

    _INDICATOR_PX = 30   # [사용자 피드백 2026-07-29] 인디케이터 목표 픽셀 크기(폭 기준, 줌 무관 고정)

    def _indicator_scene_rect(self) -> QRectF:
        """메인 뷰가 지금 보여주는 영역 — 씬 좌표. `_paint_indicator`가 그대로 그릴 값이라
        테스트가 이중변환 회귀(그 메서드 주석 참조)를 잡을 수 있도록 별도 메서드로 뺐다."""
        main = self._owner._view
        return main.mapToScene(main.viewport().rect()).boundingRect()

    def _indicator_draw_rect(self) -> QRectF:
        """[사용자 피드백 2026-07-29] 처음엔 실제 가시 영역 비율 그대로 그렸는데, 메인 뷰를
        확대할수록 인디케이터가 작아져(≒ 화면에 보이는 씬 면적에 비례) 클릭으로 위치 잡기가
        불편하다는 지적 — StarCraft류 게임 미니맵처럼 **종횡비는 유지하되 크기는 항상 고정**으로
        바꾼다. 중심은 실제 가시 영역(`_indicator_scene_rect`)을 그대로 쓰고, 폭/높이만 미니맵
        자체 배율(`self.transform()` — KeepAspectRatio라 m11==m22)의 역수로 고정 픽셀 크기를
        씬 단위로 환산해 대체한다."""
        visible = self._indicator_scene_rect()
        scale = self.transform().m11() or 1.0
        aspect = (visible.width() / visible.height()) if visible.height() else 1.0
        w = self._INDICATOR_PX / scale
        h = w / aspect if aspect else w
        r = QRectF(0, 0, w, h)
        r.moveCenter(visible.center())
        return r

    def _paint_indicator(self, painter):
        """[성능 최적화 2026-08-08] 예전엔 `drawForeground`(Qt가 씬 좌표계로 painter를 미리
        매핑해 호출)였는데, `paintEvent`가 더 이상 `super().paintEvent()`를 안 타 Qt가
        `drawForeground`를 자동 호출하지 않는다 — 그래서 이 뷰 자신이 직접 부르는 일반
        메서드로 바꾸고, painter는 뷰포트 픽셀 좌표계(변환 없음)이므로 `mapFromScene`으로
        직접 매핑한다(옛 이중변환 버그 — 위 클래스 docstring — 는 씬좌표 painter에 픽셀좌표를
        그린 것이 원인이었지, 그 반대(픽셀좌표 painter에 씬좌표를 그리는 지금 이 실수)와는
        다르다 — 헷갈리지 않도록 명시)."""
        visible = self._indicator_draw_rect()
        view_rect = self.mapFromScene(visible).boundingRect()
        # [사용자 피드백] 처음엔 dock 제목줄 accent와 같은 블루(#54a9ff/#1f7ae0)+반투명 채움을
        # 썼더니 ⓐ 채움이 미니맵 속 도형을 뿌옇게 가려 시인성이 나쁘고 ⓑ 상단 dock 제목줄 밑
        # accent 선과 색이 같아 서로 다른 UI 요소인데 헷갈렸다. 채움을 없애 안쪽을 그대로 보이게
        # 하고(테두리만), 테마·accent와 무관한 고정 시안(cyan)으로 바꿔 dock 장식과 확실히 구분.
        indicator_color = QColor("#22d3ee")
        pen = QPen(indicator_color, 2.2); pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(view_rect)

    def _navigate_to(self, view_pos):
        self._owner._view.centerOn(self.mapToScene(view_pos))
        self.viewport().update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._navigate_to(event.position().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._navigate_to(event.position().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        event.ignore()   # 미니맵 자체 줌 없음 — 항상 전체 맞춤 유지(메인 뷰 휠은 별도)


class _FloatingPanel(QFrame):
    """[캔버스-퍼스트 레이아웃] `QDockWidget` 대신 캔버스 위에 뜨는 콘텐츠-크기 카드.
    Figma/Excalidraw처럼 패널이 콘텐츠만큼만 공간을 쓰고 나머지는 도면 영역으로 남는다
    (deep-interview 2026-07-29: QMainWindow dock 영역은 콘텐츠 크기와 무관하게 칼럼 전체를
    예약해 낭비 공간이 생기던 문제의 근본원인). 위치는 창 모서리에 고정(자유 드래그 재배치는
    스코프 밖 — Figma류도 패널 위치는 고정이 관례), 대신 제목줄 ▾/▸ 로 접기/펴기.
    포지셔닝 패턴은 선택 위 컨텍스트 툴바(M3 #15, 2026-07-31 폐지)가 쓰던 것을 그대로 따른다
    (QFrame(host) 부모 + host 좌표계 move — 규칙 2 손안의 카드)."""

    # [패널 관련 수정, 2026-08-19] 사용자 요청 — 패널 헤더 우클릭으로 닫고, 다시 보고 싶으면
    # 메뉴(host_ui._build_panel_menu)에서 재오픈. 접기(`_collapse_key`)와 별개 축(접기=내용만
    # 숨김, 닫기=패널 전체를 화면에서 뗌)이라 QSettings 키도 분리한다. 재오픈 메뉴의 체크상태를
    # 우클릭 닫기와도 동기화해야 해 신호로 알린다(메뉴는 패널보다 나중에 만들어져 생성 시점
    # 콜백 연결이 불가능 — host_ui._build_panel_menu 주석 참조).
    visibility_changed = pyqtSignal(bool)

    def __init__(self, host, title: str, collapse_key: str):
        super().__init__(host)
        self.setObjectName("floatPanel")
        self._host = host
        self._collapse_key = f"panel_collapsed_{collapse_key}"
        self._visible_key = f"panel_visible_{collapse_key}"
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        head = QWidget(); head.setObjectName("floatPanelHead")
        self._head = head
        head.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        head.customContextMenuRequested.connect(self._show_header_menu)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(9, 4, 4, 4); hl.setSpacing(4)
        self._title_lbl = QLabel(title)
        hl.addWidget(self._title_lbl, 1)
        self._collapse_btn = QToolButton()
        self._collapse_btn.setAutoRaise(True)
        self._collapse_btn.setFixedSize(QSize(21, 21))   # [2026-08-13 피드백] 18→21
        self._refresh_collapse_color()   # [2026-08-13 피드백] 코랄(눈에 띔) → 테마 적응 중립색
        self._collapse_btn.clicked.connect(self._toggle_collapsed)
        hl.addWidget(self._collapse_btn)
        v.addWidget(head)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self._body)

        self._collapsed = False
        want_collapsed = QSettings("EasyCAD", "EasyCAD").value(
            self._collapse_key, False, type=bool)
        if want_collapsed:
            self._set_collapsed(True, persist=False)
        else:
            self._update_collapse_icon()

        if not QSettings("EasyCAD", "EasyCAD").value(self._visible_key, True, type=bool):
            self.hide()   # 명시적 hide — 부모(창) show() 뒤에도 감춤 유지(Qt 관례)

    def _show_header_menu(self, pos):
        menu = QMenu(self)
        _style_menu_separators(menu)
        menu.addAction("닫기", self._close_panel)
        menu.exec(self._head.mapToGlobal(pos))

    def _close_panel(self):
        self.set_panel_visible(False)

    def set_panel_visible(self, visible: bool):
        """우클릭 「닫기」와 보기(V)→패널 메뉴 재오픈이 공유하는 단일 경로 — 상태 반영·
        영속화·신호 발신을 한 곳에서(둘 중 하나만 하면 다른 쪽이 동기화를 놓친다)."""
        self.setVisible(visible)
        QSettings("EasyCAD", "EasyCAD").setValue(self._visible_key, visible)
        self.visibility_changed.emit(visible)
        if visible:
            self._host._reposition_panels()

    def paintEvent(self, event):
        # [2026-07-31] 배경·테두리를 QSS(`#floatPanel {...}`) 대신 직접 그린다 — `setStyleSheet()`를
        # 이 패널(본문 폼의 조상) 자체에 걸면 Qt가 body 하위 위젯 전부(스핀박스 포함, 그 위젯을
        # 겨냥한 규칙이 없어도)를 QStyleSheetStyle로 강제 전환하는데, 이 프록시의 QSpinBox/
        # QDoubleSpinBox sizeHint가 네이티브 Fusion보다 짧게 나와 텍스트 디센더가 잘리고, 그
        # sizeHint로 계산되는 QFormLayout 행 간격도 실제 위젯 높이(setMinimumHeight로 강제한
        # 값)보다 좁게 잡혀 다음 행과 겹치는 문제까지 있었다(스턱루프 규칙 11-b — 위젯 레벨
        # 패치를 두 번 더 시도해도 같은 근본원인이라 계속 재발했다). 패널 자체엔 스타일시트를
        # 아예 걸지 않아 body의 모든 자손이 순정 Fusion 계산을 그대로 쓰게 하고, 제목줄 강조는
        # `_head`에만 스타일시트를 건다(head는 body의 조상이 아니라 형제라 body에 영향 없음).
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QBrush(self.palette().color(QPalette.ColorRole.Window)))
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1))
        painter.drawRoundedRect(rect, 6, 6)
        painter.end()
        super().paintEvent(event)

    def set_content(self, widget: QWidget):
        self._body_layout.addWidget(widget)

    def set_title_click(self, handler):
        """[줌 배지 통합 2026-08-01, 사용자 요청] 제목 텍스트를 클릭 가능하게 만든다(커서 변경
        + 클릭 시 handler 호출) — 기본은 비클릭이라 다른 패널(도형·속성)엔 영향 없음, 필요한
        패널만 명시적으로 호출한다(미니맵: 제목에 표기된 줌%를 클릭하면 100%+정중앙 이동)."""
        self._title_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_click = handler
        self._title_lbl.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._title_lbl and event.type() == QEvent.Type.MouseButtonPress \
                and getattr(self, "_title_click", None) is not None:
            self._title_click()
            return True
        return super().eventFilter(obj, event)

    def _toggle_collapsed(self):
        self._set_collapsed(not self._collapsed, persist=True)

    def _set_collapsed(self, collapsed: bool, persist: bool):
        self._collapsed = collapsed
        self._body.setVisible(not collapsed)
        self._update_collapse_icon()
        if persist:
            QSettings("EasyCAD", "EasyCAD").setValue(self._collapse_key, collapsed)
        self.adjustSize()
        self._host._reposition_panels()

    def _update_collapse_icon(self):
        self._collapse_btn.setText("▸" if self._collapsed else "▾")
        self._collapse_btn.setToolTip("펼치기" if self._collapsed else "접기")

    def _refresh_collapse_color(self):
        """[2026-08-13 피드백] 접기 화살표를 상단바 아이콘과 같은 테마 적응 중립색(`_ICON_COLOR`)
        으로 — 코랄은 "활성 상태" 전용 accent라는 기존 원칙(host_ui.py 아이콘 재칠 주석 참조)에
        맞춰, 테마 전환 시(`CanvasWindow._apply_theme`) 다시 호출돼야 갱신된다."""
        self._collapse_btn.setStyleSheet(
            f"QToolButton {{ color: {_current_icon_color().name()}; font-size: 13px; }}")


class _StaticSection(QWidget):
    """[좌측 패널 개편, 2026-08-19 실사용 피드백] 옛 `_AccordionSection`에서 접기 기능만 뺀
    정적 섹션 — "기본도형"·"내 심볼" 최상단은 더 이상 접지 않는다(실사용 보고: 이 최상단
    아코디언을 접었다 펼치면 패널이 부풀어 보이는 레이아웃 버그가 있었고, "내 심볼"은
    이제 폴더 단위로 접는 게 더 유용하다는 판단 — 폴더별 접기는 `host_ui._refresh_custom_
    symbol_section`의 `add_group`가 별도로 구현). `header_layout`을 그대로 공개해 제목
    옆에 버튼(내 심볼의 "+")을 끼우는 관례를 옛 클래스와 동일하게 유지한다."""

    def __init__(self, title: str):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(2, 4, 2, 2); hl.setSpacing(4)
        # [2026-08-13 버그 수정, 옛 _AccordionSection에서 이관] 색을 안 정한 `setStyleSheet()`는
        # QLabel을 QStyleSheetStyle로 전환해 앱 다크 팔레트(WindowText)를 안 따르고 검정으로
        # 렌더됐다 — 폰트는 스타일시트 대신 QFont로 걸어 팔레트 색 상속을 그대로 유지한다.
        title_lbl = QLabel(title)
        f = title_lbl.font(); f.setWeight(QFont.Weight.DemiBold); title_lbl.setFont(f)
        hl.addWidget(title_lbl, 1)
        self.header_layout = hl   # 확장 지점 — insertWidget(1, ...)으로 제목 옆에 버튼 삽입
        v.addWidget(head)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        # [2026-08-12 3차 피드백] 좌우 여백 축소(4→2) — 패널 폭을 속성/미니맵 패널(218px)에
        # 맞추기 위한 축소 시리즈의 일부.
        self.body_layout.setContentsMargins(2, 2, 2, 4); self.body_layout.setSpacing(4)
        v.addWidget(self.body)


class _SymbolFolderDropZone(QWidget):
    """[신규기능, 2026-08-12] '내 심볼' 폴더 그룹 — 커스텀 심볼 팔레트 버튼(`_PaletteButton`)을
    이 위로 드래그해 놓으면 이 폴더로 옮긴다. `_PaletteButton._start_palette_drag`가 이미
    보내는 `_PALETTE_MIME`(tool_key="customsym:<id>")를 그대로 받아 재사용 — 새 드래그 소스가
    필요 없다. folder=None은 미분류(최상단) 영역."""

    def __init__(self, folder: str | None, on_drop):
        super().__init__()
        self.setAcceptDrops(True)
        self._folder = folder
        self._on_drop = on_drop

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(_PALETTE_MIME) and bytes(
                md.data(_PALETTE_MIME)).decode("utf-8").startswith("customsym:"):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dropEvent(self, e):
        md = e.mimeData()
        tool_key = bytes(md.data(_PALETTE_MIME)).decode("utf-8")
        sym_id = tool_key[len("customsym:"):]
        e.acceptProposedAction()
        self._on_drop(sym_id, self._folder)


class _ToastLabel(QLabel):
    """[캔버스-퍼스트 레이아웃] `QStatusBar.showMessage()`를 대체하는 하단중앙 플로팅 토스트.
    Figma/Excalidraw는 창 전체 폭을 가로지르는 상태바 행을 상시 예약하지 않는다 — 메시지가
    있을 때만 캔버스 위에 잠깐 떠 있는 카드로 보여주고, 없으면 그 자리는 그대로 도면 영역."""

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self.setObjectName("toastLabel")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._current = ""
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def showMessage(self, text: str, timeout: int = 0):
        self._timer.stop()
        self._current = text or ""
        if not text:
            self.hide()
            return
        self.setText(text)
        self.adjustSize()
        self._host._reposition_toast()   # _reposition_toast는 이제 가시성과 무관하게 항상 동작
        self.show()
        self.raise_()
        if timeout and timeout > 0:
            self._timer.start(timeout)

    def _on_timeout(self):
        self._current = ""
        self.hide()

    def currentMessage(self) -> str:
        # QStatusBar 계약과 동일: 메시지가 있는 동안만 반환(만료·hide되면 빈 문자열).
        # isVisible()에 의존하지 않는다 — 헤드리스 테스트는 최상위 창을 show()하지 않아
        # 자식 위젯이 .show()를 호출해도 isVisible()이 항상 False로 읽힌다(Qt 가시성은
        # 조상 체인 전체가 보여야 True).
        return self._current

    def addPermanentWidget(self, widget, stretch: int = 0):
        pass   # [하위호환] 옛 QStatusBar API — 줌 배지는 이제 별도 플로팅 위젯이라 미사용


# [신규기능 · 색 선택 UX 단순화] 그리드 팝업의 기본 색상 열 — 무채색 1열(흰/회/검, 고정 3값)
# + 기존 _COLOR_PRESETS 5색(빨강·주황·노랑·초록·파랑)에 보라 1색을 더한 유채색 6열. 분홍은
# 첫 열(빨강)과 밝기만 다른 사실상 중복이라 뺐다(2026-07-31 사용자 피드백 — 그 자리는 아래
# "최근 사용한 색" 열로 대체). Apple 시스템 색상 관례를 그대로 잇는다(_COLOR_PRESETS와 동일 톤).
_COLOR_GRID_HUES = _COLOR_PRESETS[:5] + ["#AF52DE"]
_RECENT_COLOR_MAX = 3   # 그리드 한 열의 행 수와 맞춘 값 — 열 하나를 통째로 이 용도로 씀


def _color_grid_columns() -> list[list[QColor]]:
    """그리드 열 구성 — 무채색 1열 + 유채색 6열, 각 열은 위→아래 표준(기본)→연한색→어두운색
    순(2026-07-31 사용자 피드백 — Office 테마색 그리드 관례). 밝기 변형은
    QColor.lighter()/darker()로 생성(고정 팔레트 하드코딩 불필요). 무채색은 자연스러운
    '표준' 색조가 없어 회색을 표준으로 두고 기존 흰/검 값을 그대로 연한/어두운 자리에 재사용."""
    cols = [[QColor("#9E9E9E"), QColor("#FFFFFF"), QColor("#000000")]]
    for hexs in _COLOR_GRID_HUES:
        base = QColor(hexs)
        cols.append([base, base.lighter(150), base.darker(150)])
    return cols


def _strip_color_dialog_left_column(dlg: QColorDialog):
    """[신규기능] 비-네이티브 QColorDialog(알파 채널 때문에 Qt가 자동으로 네이티브 대신
    이 위젯을 씀)의 왼쪽 열(Basic colors·Pick Screen Color·Custom colors·Add to Custom
    Colors)을 숨긴다 — 우리 그리드 팝업의 표준색·"최근 사용한 색"과 중복이라는 사용자
    피드백(2026-07-31)으로 제거하고, 오른쪽 그라디언트+슬라이더+RGB/16진수 입력만 남긴다.

    ⚠ v1(고정 좌표 x<265·폭<=260)은 격리된 헤드리스 테스트에서만 맞았고 실제 앱(스타일
    Fusion·실제 Windows 폰트)에서는 왼쪽 열 폭 자체가 헤드리스 실측과 달라 그라디언트
    사각형·색상 슬라이더까지 함께 지워버렸다(실사용자 스크린샷으로 발견, 2026-07-31) —
    폰트 메트릭에 따라 sizeHint가 달라지는 내부 레이아웃을 고정 픽셀로 가정한 게 원인.
    v2는 절대 좌표 대신 "Basic colors"/"Custom colors" 라벨과 버튼(Qt 내부 고정 영문
    문자열 — 이 앱은 Qt 자체 번역을 안 실어서 로캘과 무관하게 항상 이 텍스트)을 앵커로
    찾고, 그 앵커들과 **같은 x, 같은 세로 범위**에 있는 이름 없는 위젯(실제 색상 그리드)만
    같이 숨긴다 — 오른쪽 열은 구조적으로 다른 x를 쓰므로 폰트가 달라져도 안전하게 제외된다.
    앵커 텍스트가 하나도 안 잡히면(Qt 버전 차이 등) 아무것도 숨기지 않는다 — 실패해도
    다이얼로그 자체는 정상 동작하고 그냥 옛(복잡한) 모양 그대로 보일 뿐이라 안전하다."""
    anchor_texts = {"&Basic colors", "&Custom colors", "&Pick Screen Color", "&Add to Custom Colors"}
    anchors = [w for w in dlg.children()
               if isinstance(w, QWidget) and getattr(w, "text", lambda: None)() in anchor_texts]
    if len(anchors) < 4:
        return
    left_x = anchors[0].geometry().x()
    y_top = min(w.geometry().y() for w in anchors)
    y_bottom = max(w.geometry().y() + w.geometry().height() for w in anchors)
    to_hide = list(anchors)
    for w in dlg.children():
        if not isinstance(w, QWidget) or w in to_hide:
            continue
        g = w.geometry()
        if abs(g.x() - left_x) <= 2 and y_top - 4 <= g.y() <= y_bottom + 4:
            to_hide.append(w)
    for w in to_hide:
        w.hide()


class _ColorGridPopup(QWidget):
    """Office류 색 선택 팝업 — 무채색+기본색 그리드(밝기 3단) + 최근 사용한 색(다른 색에서
    고른 색, 최대 3개) + '다른 색…'(왼쪽 열을 숨긴 비-네이티브 QColorDialog, 선·채움 공통) +
    (채움 전용) '없음'. 바깥을 클릭하면 자동으로 닫히는 Qt.Popup — 2026-07-28 코드정리에서
    삭제된 pasteflow 유산 `_ColorPalettePopup`과 동일한 패턴이다. 클릭 즉시 적용 + 팝업
    닫힘(확인 버튼 없음, 오피스 관례)."""

    _SW = 20   # 스와치 한 변(px)

    def __init__(self, parent: QWidget, initial: QColor | None, allow_none: bool,
                 show_alpha: bool, title: str, on_pick, recent: list[QColor] | None = None,
                 on_custom_picked=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self._initial = QColor(initial) if initial is not None else None
        self._show_alpha = show_alpha
        self._title = title
        self._on_pick = on_pick
        self._on_custom_picked = on_custom_picked
        self._anchor_parent = parent
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("colorGridPopup")
        self.setStyleSheet(
            "#colorGridPopup { background-color: palette(window);"
            " border: 1px solid palette(mid); border-radius: 6px; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8); outer.setSpacing(6)

        top = QHBoxLayout(); top.setSpacing(6)
        if allow_none:   # [요청③] "없음"을 별도 외부 버튼이 아니라 팝업 안 항목으로
            none_btn = QToolButton(); none_btn.setText("Ø")
            none_btn.setToolTip("채움 없음")
            none_btn.setFixedSize(QSize(26, 22))
            none_btn.clicked.connect(lambda: self._pick(None))
            top.addWidget(none_btn)
        other_btn = QToolButton(); other_btn.setText("다른 색…")
        other_btn.setToolTip("전체 색상표")
        other_btn.clicked.connect(self._pick_other)
        top.addWidget(other_btn, 1)
        outer.addLayout(top)

        grid = QGridLayout(); grid.setSpacing(4)
        columns = _color_grid_columns()
        recent_col = list((recent or [])[:_RECENT_COLOR_MAX])
        recent_col += [None] * (_RECENT_COLOR_MAX - len(recent_col))
        columns.append(recent_col)
        for col_i, col in enumerate(columns):
            for row_i, color in enumerate(col):
                b = QToolButton()
                b.setFixedSize(QSize(self._SW, self._SW))
                if color is None:
                    b.setEnabled(False)
                    b.setToolTip("다른 색에서 고른 색이 여기 표시됩니다")
                    b.setStyleSheet(
                        "background:transparent; border:1px dashed #666; border-radius:3px;")
                else:
                    b.setToolTip(color.name())
                    b.setStyleSheet(
                        f"background:{color.name()}; border:1px solid #0006; border-radius:3px;")
                    b.clicked.connect(lambda _c=False, c=QColor(color): self._pick(c))
                grid.addWidget(b, row_i, col_i)
        outer.addLayout(grid)

    def _pick(self, color: QColor | None):
        self._on_pick(color)
        self.close()

    def _pick_other(self):
        # [2026-07-31 통일] 예전엔 알파(반투명)가 필요한 채움만 비-네이티브 다이얼로그+왼쪽 열
        # 숨김을 적용하고, 알파가 필요 없는 선/텍스트 색은 OS 네이티브 다이얼로그를 그대로 썼다
        # — 네이티브는 창 자체가 OS가 그려서 내부 위젯을 숨길 방법이 없어 왼쪽 열이 그대로
        # 보였다. 사용자 피드백(2026-07-31): 인터페이스가 서로 달라 보임 → 알파 유무와 무관하게
        # 항상 비-네이티브 인스턴스를 만들어 왼쪽 열을 숨긴다(오른쪽 그라디언트+필드는 동일 재사용).
        parent = self._anchor_parent
        self.close()
        dlg = QColorDialog(parent)
        dlg.setWindowTitle(self._title)
        if self._show_alpha:
            dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setCurrentColor(self._initial or QColor("#ffffff"))
        dlg.adjustSize()
        _strip_color_dialog_left_column(dlg)
        dlg.adjustSize()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            col = dlg.selectedColor()
            if col.isValid():
                if self._on_custom_picked:
                    self._on_custom_picked(col)
                self._on_pick(col)
