"""무한 캔버스 호스트 — pasteflow 편집기 코어(annotator_core)를 독립 앱으로 승격.

annotator_core의 _AnnotatorView·아이템 클래스는 그대로 재사용하고(스냅·베지어 UX 보존),
무거운 _EditorMixin(이미지 배경·스포이드·클립보드 아이콘 툴바) 대신 무한 캔버스에 맞는
얇은 owner + 최소 툴바를 새로 짠다.

owner가 _AnnotatorView에 제공해야 하는 인터페이스(뷰 소스에서 추출):
  속성: current_tool/color/width, arrow_head_at_end, current_font_size,
        current_text_bg, current_badge_size, _bg_item
  메서드: is_edit_mode/toggle_edit_mode/_on_escape/make_pen/set_tool/
          next_badge_number/adjust_item_property/_on_wheel_zoom/
          _win_drag_start/_win_drag_move/_win_drag_end/
          push_undo_add/push_undo_delete/push_undo_move/undo/
          copy_selection/paste_selection
"""
import re
import uuid

from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QSize, QSettings, QTimer, QMimeData, QEvent
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter,
    QFont, QPolygonF, QPainterPath, QPalette, QDrag,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPlainTextEdit,
    QSizePolicy, QColorDialog, QHBoxLayout, QMenu, QFrame,
    QListWidget, QListWidgetItem,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon, _nearest_border,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document, load_document_layers
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)

# Mermaid 중립 shape → 우리 아이템. ('rect'|'ellipse'|'symbol', symbol kind|None).
# deep-interview 2026-07-21 확정 매핑. 둥근사각형은 사각형으로(라운딩 손실), 미인식은 사각형 폴백.
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
    임계(px)를 넘게 끌면 QDrag로 캔버스에 도형을 드롭 생성한다. 드래그 시엔 release가
    버튼에 안 와 clicked가 발화하지 않으므로 무장되지 않는다(의도 — 드래그와 무장 분리)."""
    _DRAG_THRESH = 6

    def __init__(self, tool_key: str, parent=None, preview_fn=None):
        super().__init__(parent)
        self._drag_tool_key = tool_key
        self._drag_press = None
        self._preview_fn = preview_fn   # [UX] 실물 미리보기 렌더 콜백(host._render_drag_preview)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if (self._drag_press is not None and (e.buttons() & Qt.MouseButton.LeftButton)
                and (e.position().toPoint() - self._drag_press).manhattanLength()
                >= self._DRAG_THRESH):
            self._drag_press = None
            self._start_palette_drag()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_press = None
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
        self.setDown(False)   # 드래그로 release를 못 받으니 눌림 상태 수동 해제
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

# [Phase 6 M1] 파일·보기 액션 아이콘 색(단색). 다크모드 도입 시 팔레트 기반으로 승격 예정.
_ICON_COLOR = QColor("#39434f")


def _act_icon(name: str) -> QIcon:
    """[Phase 6 M1] 파일/삽입/보기 액션 아이콘 — QPainter 단색 라인 글리프.
    좌표는 icon_proposal 아티팩트(24-단위 뷰박스)에서 그대로 포팅. 그리기 도구 아이콘은
    코어 `_tool_icon`이 담당하고, 여기선 앱 레벨 액션(문서 없는 상단바 버튼)만 그린다."""
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

    if name == "new":
        poly([(6.5, 3.5), (13, 3.5), (17.5, 8), (17.5, 20.5), (6.5, 20.5)])
        poly([(13, 3.5), (13, 8), (17.5, 8)], close=False)
        line(12, 12, 12, 17); line(9.5, 14.5, 14.5, 14.5)
    elif name == "open":
        poly([(3.5, 6.5), (9, 6.5), (11, 8.5), (20.5, 8.5), (20.5, 18), (3.5, 18)])
    elif name == "save":
        poly([(4.5, 4.5), (16.5, 4.5), (19.5, 7.5), (19.5, 19.5), (4.5, 19.5)])
        poly([(7.5, 4.5), (7.5, 9), (15, 9), (15, 4.5)], close=False)
        p.drawRect(QRectF(8, 13, 8, 6.5))
    elif name == "pdf":
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
    elif name == "snap":
        path = QPainterPath(QPointF(6.5, 4.5))
        path.lineTo(6.5, 11.5)
        path.arcTo(QRectF(6.5, 6, 11, 11), 180, -180)
        path.lineTo(17.5, 4.5)
        p.drawPath(path)
        p.save(); p.setBrush(col); p.setPen(QPen(col, 1))
        p.drawRect(QRectF(5, 4, 3.3, 3.2)); p.drawRect(QRectF(15.7, 4, 3.3, 3.2))
        p.restore()
    elif name == "ortho":
        poly([(6, 4), (6, 19), (20, 19)], close=False)
        poly([(6, 15.5), (9.5, 15.5), (9.5, 19)], close=False)
    elif name == "grid":
        p.save(); p.setBrush(col); p.setPen(QPen(col, 1))
        for gx in (5.5, 12, 18.5):
            for gy in (5.5, 12, 18.5):
                p.drawEllipse(QPointF(gx, gy), 1.5, 1.5)
        p.restore()
    elif name == "undo":
        poly([(8, 7), (4.3, 10.5), (8, 14)], close=False)
        path = QPainterPath(QPointF(4.3, 10.5))
        path.lineTo(14, 10.5)
        path.arcTo(QRectF(8.8, 10.5, 10.4, 10.4), 90, -180)
        path.lineTo(9.5, 20.9)
        p.drawPath(path)
    elif name == "redo":
        # undo 글리프를 수평 반전(→ 오른쪽으로 굽는 화살표).
        p.save()
        p.translate(24, 0); p.scale(-1, 1)
        poly([(8, 7), (4.3, 10.5), (8, 14)], close=False)
        path = QPainterPath(QPointF(4.3, 10.5))
        path.lineTo(14, 10.5)
        path.arcTo(QRectF(8.8, 10.5, 10.4, 10.4), 90, -180)
        path.lineTo(9.5, 20.9)
        p.drawPath(path)
        p.restore()
    elif name == "help":
        p.drawEllipse(QPointF(12, 12), 8.3, 8.3)
        f = QFont(); f.setBold(True); f.setPointSizeF(11)
        p.save(); p.setFont(f); p.setPen(col)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "?")
        p.restore()
    elif name == "theme":
        # 초승달 — 다크/라이트 토글.
        moon = QPainterPath()
        moon.addEllipse(QPointF(12, 12), 8.2, 8.2)
        cut = QPainterPath()
        cut.addEllipse(QPointF(15.5, 9.5), 7.2, 7.2)
        p.save(); p.setBrush(col); p.setPen(QPen(col, 1))
        p.drawPath(moon.subtracted(cut))
        p.restore()
    elif name == "pin":
        # 압정(도구 고정) — 머리+핀. 체크 시 눌린 상태로 강조되어 무장 유지를 알린다.
        p.save(); p.setBrush(col); p.setPen(QPen(col, 1.4))
        head = QPainterPath()
        head.addEllipse(QPointF(12, 9), 5.2, 5.2)
        p.drawPath(head)
        p.restore()
        line(12, 14, 12, 20)
    p.end()
    icon = QIcon(pm)
    # [M2 #1] 비활성 상태 아이콘을 뚜렷하게 흐리게 — baked 단색 픽스맵은 Qt 기본 비활성
    # 처리가 약해 사용자가 활성/비활성을 구분하기 어려웠다(되돌리기 버튼 피드백). 저알파 사본을
    # Disabled 모드로 명시 등록해 확실히 흐려 보이게 한다.
    dim = QPixmap(pm.size()); dim.fill(Qt.GlobalColor.transparent)
    dp = QPainter(dim); dp.setOpacity(0.30); dp.drawPixmap(0, 0, pm); dp.end()
    icon.addPixmap(dim, QIcon.Mode.Disabled, QIcon.State.Off)
    icon.addPixmap(dim, QIcon.Mode.Disabled, QIcon.State.On)
    return icon


# [Phase 6 M1] 캔버스 배경 — 테마별. 다크는 CAD 관습대로 어두운 모델공간.
_CANVAS_BG = {"dark": QColor("#1e2731"), "light": QColor("#ffffff")}
_ICON_COLOR_THEME = {"dark": QColor("#cdd8e3"), "light": QColor("#39434f")}


def _dark_palette() -> QPalette:
    """다크 테마 팔레트(Fusion 스타일과 함께 쓰면 전 위젯에 안정 적용)."""
    c = QColor
    p = QPalette()
    R = QPalette.ColorRole
    p.setColor(R.Window, c("#171e26"));         p.setColor(R.WindowText, c("#cdd8e3"))
    p.setColor(R.Base, c("#0e1319"));           p.setColor(R.AlternateBase, c("#1d2632"))
    p.setColor(R.Text, c("#cdd8e3"));           p.setColor(R.PlaceholderText, c("#78889a"))
    p.setColor(R.Button, c("#1d2632"));         p.setColor(R.ButtonText, c("#cdd8e3"))
    p.setColor(R.ToolTipBase, c("#232f3d"));    p.setColor(R.ToolTipText, c("#cdd8e3"))
    p.setColor(R.Highlight, c("#2f6dbf"));      p.setColor(R.HighlightedText, c("#ffffff"))
    p.setColor(R.Link, c("#54a9ff"))
    D = QPalette.ColorGroup.Disabled
    p.setColor(D, R.Text, c("#5a6675"));        p.setColor(D, R.ButtonText, c("#5a6675"))
    p.setColor(D, R.WindowText, c("#5a6675"))
    return p


# [Phase 6 M1] 속성 패널 표시용 — 아이템 클래스명 → 한글 종류, 펜 스타일 → 한글.
_TYPE_NAMES = {
    "_RectItem": "네모", "_EllipseItem": "원", "_LineItem": "선",
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
    """[미니맵] 메인 뷰와 같은 QGraphicsScene을 공유하는 축소 뷰 — 별도 캐시·갱신 로직 없이
    Qt가 내용 변경(아이템 추가·이동)을 모든 뷰에 자동 반영한다(같은 scene을 보는 다른
    QGraphicsView라 scene.changed 훅이 따로 필요 없음 — 규칙 2 손안의 카드: Qt 멀티뷰가
    이미 제공). 자체 상호작용은 끄고(setInteractive(False)) 클릭/드래그로 메인 뷰를 그
    위치로 이동시키는 내비게이션만 한다.
    [성능 조사 스파이크 2026-07-30 실측] 매 paintEvent마다 itemsBoundingRect()를 캐시 없이
    재계산하던 게 무거운 도면(아이템 ~1600개)에서 71ms — 미니맵 paintEvent 전체는 98ms(60fps
    프레임 예산의 약 6배). 휠줌·팬·리사이즈마다 _refresh_minimap()이 이 repaint를 예약해
    무거운 도면에서 휠줌이 씹히는 원인으로 확인. scene.changed(아이템 추가·이동·삭제 시에만
    발생 — 줌/팬 같은 순수 뷰 변환은 안 탐)로 dirty 플래그를 걸어 캐시, 실제 내용 변경 때만
    재계산한다(O(n) 매 페인트 → 상각 O(1))."""

    def __init__(self, owner, scene):
        super().__init__(scene)
        self._owner = owner
        self.setInteractive(False)   # 아이템 선택/드래그 차단 — 클릭은 내비게이션 전용
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMinimumHeight(120)
        self._bounds_cache = QRectF()
        self._bounds_dirty = True
        scene.changed.connect(self._mark_bounds_dirty)

    def _mark_bounds_dirty(self, _regions=None):
        self._bounds_dirty = True

    def _refit(self):
        if self._bounds_dirty:
            self._bounds_cache = self.scene().itemsBoundingRect()
            self._bounds_dirty = False
        rect = self._bounds_cache
        if rect.isEmpty():
            return
        pad = max(rect.width(), rect.height()) * 0.06 + 12
        self.fitInView(rect.adjusted(-pad, -pad, pad, pad), Qt.AspectRatioMode.KeepAspectRatio)

    def paintEvent(self, event):
        self._refit()
        super().paintEvent(event)

    _INDICATOR_PX = 30   # [사용자 피드백 2026-07-29] 인디케이터 목표 픽셀 크기(폭 기준, 줌 무관 고정)

    def _indicator_scene_rect(self) -> QRectF:
        """메인 뷰가 지금 보여주는 영역 — 씬 좌표. drawForeground에서 그대로 그릴 값이라
        테스트가 이중변환 회귀(아래 주석)를 잡을 수 있도록 별도 메서드로 뺐다."""
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

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        # ⚠ [실조건 버그 근본원인] drawForeground의 painter는 Qt가 이미 "씬 좌표계"로 매핑해
        # 넘겨준다(QGraphicsItem.paint()의 로컬 좌표계와 같은 설계) — 실측 확인(offscreen 프로브):
        # drawForeground의 rect 인자가 뷰 픽셀(0..w)이 아니라 fitInView된 씬 범위 그대로였다.
        # 이전 코드는 main의 가시 영역(씬 좌표)을 self.mapFromScene()으로 미니맵 '픽셀' 좌표로
        # 또 변환한 뒤, 이미 씬 좌표계인 painter에 그 픽셀값을 그렸다 — 이중 변환이라 인디케이터가
        # 항상 잘못된 크기·위치로 그려졌다(폴링으로는 못 고치는 종류의 버그 — 매번 같은 잘못된
        # 값을 다시 그릴 뿐). 씬 좌표를 그대로 그리면 된다(변환 불필요) — 단 크기는 아래처럼 고정.
        visible = self._indicator_draw_rect()
        # [사용자 피드백] 처음엔 dock 제목줄 accent와 같은 블루(#54a9ff/#1f7ae0)+반투명 채움을
        # 썼더니 ⓐ 채움이 미니맵 속 도형을 뿌옇게 가려 시인성이 나쁘고 ⓑ 상단 dock 제목줄 밑
        # accent 선과 색이 같아 서로 다른 UI 요소인데 헷갈렸다. 채움을 없애 안쪽을 그대로 보이게
        # 하고(테두리만), 테마·accent와 무관한 고정 시안(cyan)으로 바꿔 dock 장식과 확실히 구분.
        indicator_color = QColor("#22d3ee")
        pen = QPen(indicator_color, 2.2); pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(visible)

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

    def __init__(self, host, title: str, collapse_key: str):
        super().__init__(host)
        self.setObjectName("floatPanel")
        self._host = host
        self._collapse_key = f"panel_collapsed_{collapse_key}"
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        head = QWidget(); head.setObjectName("floatPanelHead")
        self._head = head
        hl = QHBoxLayout(head)
        hl.setContentsMargins(9, 4, 4, 4); hl.setSpacing(4)
        self._title_lbl = QLabel(title)
        hl.addWidget(self._title_lbl, 1)
        self._collapse_btn = QToolButton()
        self._collapse_btn.setAutoRaise(True)
        self._collapse_btn.setFixedSize(QSize(18, 18))
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
        self._host._reposition_toast()
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


class CanvasWindow(QMainWindow):
    _PANEL_MARGIN = 10      # [캔버스-퍼스트] 플로팅 패널·줌배지·토스트와 창/뷰 경계 사이 여백(px)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Easy CAD")
        self.resize(1200, 800)
        # [캔버스-퍼스트] statusBar()를 QMainWindow 실제 상태바가 아니라 하단중앙 토스트로
        # 프록시 — 창 전체 폭을 가로지르는 항상-보이는 행을 없앤다. 다른 초기화보다 먼저 만들어
        # self.statusBar() 호출이 언제 와도 안전하게(20여 곳의 기존 .showMessage() 호출부는 무수정).
        self._toast = _ToastLabel(self)

        # ---- 편집 상태 (owner 인터페이스) ----
        self.current_tool = "select"
        self.current_color = QColor(_DEFAULT_COLOR)
        self.current_width = _DEFAULT_WIDTH
        self.current_style = Qt.PenStyle.SolidLine   # [M2] 새 도형 기본 선스타일(sticky)
        self.current_font_size = _DEFAULT_FONT
        self.current_badge_size = _DEFAULT_BADGE
        self.current_text_bg = None
        self.current_fill = None   # [신규기능] 도형 채우기 — sticky, 기본 투명(NoBrush)
        self._recent_colors = self._load_recent_colors()   # [신규기능] 색 그리드 팝업 "최근 사용한 색"
        self.arrow_head_at_end = True
        # [화살표 통합] 화살표는 상단 도구 1개. '어떤 종류로 그릴지'는 마지막에 고른 종류를 기억
        # (sticky — 색·두께·선스타일과 같은 관례). 최초 기본은 직각(순서도 위주 사용 — 실사용
        # 피드백 2026-07-30, 이전 기본은 곡선).
        self.current_arrow_kind = "ortho"          # straight | curved | ortho
        self.current_curve_r = _PolyArrowItem._CORNER_R   # 직각 커넥터의 모서리 반경(sticky)
        # [M2] 도구 고정(pin) — False면 도형 1개 그리면 자동으로 선택모드(one-shot),
        # True면 도구가 계속 무장(연속 그리기). 상단 🔒 토글로 전환.
        self.tool_pinned = False
        self.snap_enabled = True         # o-snap 토글(F3) — 도형 테두리 달라붙기 켜고 끄기
        self.ortho_enabled = False       # Ortho 토글(F8) — 그리기·정점드래그를 수평/수직(0/90°)로 제약
        self.grid_enabled = True         # [그리드] 표시+스냅 통합 토글(Shift+G) — 격자 표시·이동/리사이즈/생성 스냅
        self.align_guides_enabled = True # [정렬 가이드선] 이동 중 스마트 정렬 스냅+보라 참고선 토글(Shift+A)
        self._bg_item = None            # 배경 이미지 없음(무한 캔버스)
        self._badge_n = 0
        self._undo: list[_UndoEntry] = []   # 저널(뒤로) — 최신이 끝
        self._redo: list[_UndoEntry] = []   # 다시 실행(앞으로) — 새 변이 시 비워짐
        self._clip: list = []
        self._clip_src: list = []
        self._style_clip: dict | None = None   # [신규기능] 스타일 복사(format painter) 클립
        # [신규기능] 레이어 — 사용자 정의 이름 레이어(AutoCAD식, DXF 타입별 고정 레이어와 별개).
        # 최소 1개("기본") 유지. 표시/잠금은 undo 비대상(다크모드·그리드 토글과 같은 문서 설정),
        # 아이템→레이어 배정은 undo 대상('mut'/'layer'). 새 아이템 자동배정은 하지 않음(명시적
        # 이동만 — 그리기/붙여넣기/드롭 등 생성 경로 전부를 안 건드리려는 스코프 축소, deep-interview).
        self._layers: list[dict] = [
            {"id": "default", "name": "기본", "visible": True, "locked": False}]
        self._paste_seq = 0
        self._pan_last = None
        self._group_sync_active = False   # [편의기능] 그룹 동반선택 재진입 가드

        # ---- 씬 / 뷰 ----
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-_SCENE_HALF, -_SCENE_HALF, 2 * _SCENE_HALF, 2 * _SCENE_HALF)
        self._scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        # 지속 연결: 도형/화살표가 움직이면 바인딩된 화살표 끝을 재계산(scene.changed 트리거).
        self._rerouting = False
        self._scene.changed.connect(self._on_scene_changed)
        # [편의기능] 그룹 멤버 중 하나가 선택되면 같은 그룹 전체를 함께 선택.
        self._scene.selectionChanged.connect(self._sync_group_selection)
        self._view = _AnnotatorView(self._scene, self)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.centerOn(0, 0)
        self.setAcceptDrops(True)   # [Phase 4] 이미지 파일 드래그앤드롭 삽입

        # [Phase 6 M1] 메뉴(=액션)를 먼저 만들고 → 상단 QToolBar가 그 액션을 재사용(setDefaultAction).
        # 뷰는 중앙 위젯 자체로(별도 QWidget 래퍼 불필요 — 툴바가 QToolBar 영역으로 이동).
        self._dark = QSettings("EasyCAD", "EasyCAD").value("dark", True, type=bool)  # 다크 기본
        self._build_menu()
        self.setCentralWidget(self._view)
        # [M3 #17] 팔레트 드롭이 캔버스 뷰 위에서 무시되던 문제 — 뷰(QGraphicsView)가 드래그를
        # 먼저 가로채 우리 mime를 거부(금지 커서)하므로, 뷰포트에 이벤트 필터를 걸어 직접 받는다.
        self._view.viewport().setAcceptDrops(True)
        self._view.viewport().installEventFilter(self)
        self._build_toolbar()
        # [캔버스-퍼스트 레이아웃, deep-interview 2026-07-29] 좌/우 QDockWidget(칼럼 전체를
        # 콘텐츠 크기와 무관하게 예약해 낭비 공간을 만들던 근본원인)을 캔버스 위 플로팅
        # 카드(`_FloatingPanel`)로 교체 — Figma/Excalidraw처럼 패널이 콘텐츠만큼만 쓰고
        # 나머지는 도면 영역. 위치는 고정(자유 드래그 재배치는 스코프 밖), 대신 접기/펴기.
        self._build_left_panel()          # 도형 + 레이어(탭), 좌상단
        self._build_properties_panel()    # 속성, 우상단(도형바꾸기·화살표종류·반경·방향도 여기 포함)
        self._build_minimap_panel()       # [신규기능] 미니맵 — 우하단, 제목에 줌%까지 표기(클릭 가능)
        self.set_tool("select")
        self._apply_theme(self._dark)   # 저장된 테마 적용(아이콘·배경·팔레트 일괄)
        self._reposition_panels()

    # ---- 메뉴 (파일 → 저장/열기/PDF) ----------------------------------------
    def _make_action(self, text, icon, slot, shortcut=None, checkable=False):
        """[Phase 6 M1] 메뉴·상단 툴바가 공유할 QAction 하나를 만든다(아이콘 포함).
        상단 QToolBar는 이 액션을 setDefaultAction으로 재사용 → 상태(체크 등) 자동 동기화."""
        a = QAction(text, self)
        if icon:
            a.setIcon(_act_icon(icon))
            self._icon_actions.append((a, icon))   # 테마 전환 시 아이콘 재생성용 등록
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if checkable:
            a.setCheckable(True)
        a.triggered.connect(slot)
        return a

    def _build_menu(self):
        self._doc_path = None
        self._icon_actions: list[tuple[QAction, str]] = []   # (액션, 아이콘이름) — 테마 재생성용
        m = self.menuBar().addMenu("파일(&F)")

        self._act_new = self._make_action("새로 만들기", "new", self._new_doc,
                                          QKeySequence.StandardKey.New)
        self._act_open = self._make_action("열기…", "open", self._open_doc,
                                           QKeySequence.StandardKey.Open)
        self._act_save = self._make_action("저장…", "save", self._save_doc,
                                           QKeySequence.StandardKey.Save)
        for a in (self._act_new, self._act_open, self._act_save):
            m.addAction(a)
        m.addSeparator()

        self._act_pdf = self._make_action("PDF 내보내기 — 전체…", "pdf",
            lambda: self._export_pdf(selection_only=False), "Ctrl+P")
        self._act_pdf_sel = self._make_action("PDF 내보내기 — 선택영역…", "pdf",
            lambda: self._export_pdf(selection_only=True), "Ctrl+Shift+P")
        # [신규기능] DXF 가져오기/내보내기 통합 — 옛 전용 메뉴·단축키(Ctrl+Shift+D/I)는
        # 폐지하고 열기(Ctrl+O)/저장(Ctrl+S)이 확장자로 분기(아래 _open_doc/_save_doc).
        for a in (self._act_pdf, self._act_pdf_sel):
            m.addAction(a)
        m.addSeparator()

        self._act_img = self._make_action("이미지 삽입…", "image",
            self._insert_image, "Ctrl+Shift+M")
        self._act_tb = self._make_action("표제란 / 용지틀 삽입…", "titleblock",
            self._insert_titleblock, "Ctrl+Shift+T")
        self._act_tbl = self._make_action("표 삽입…", "table",
            self._insert_table, "Ctrl+Shift+B")
        self._act_mmd = self._make_action("Mermaid 가져오기…", "mermaid",
            self._insert_mermaid, "Ctrl+Shift+F")
        for a in (self._act_img, self._act_tb, self._act_tbl, self._act_mmd):
            m.addAction(a)

        # 편집(상단 툴바 전용 — 메뉴엔 없던 undo/redo를 액션으로. Ctrl+Z/Ctrl+Y 키는 뷰가 처리).
        self._act_undo = self._make_action("되돌리기", "undo", self.undo)
        self._act_redo = self._make_action("다시 실행", "redo", self.redo)
        # [M2] 도구 고정 — 켜면 도형을 그려도 도구가 유지(연속 그리기), 끄면 one-shot(그리면 선택모드).
        self._act_pin = self._make_action("도구 고정", "pin", self._toggle_pin, checkable=True)
        self._act_pin.setToolTip("도구 고정 — 켜면 연속으로 그리기(끄면 하나 그린 뒤 선택모드)")

        # ---- 보기 메뉴 (기준 zoom / 스냅 토글) ----
        v = self.menuBar().addMenu("보기(&V)")
        self._act_zoom100 = self._make_action("100% (1:1)", "zoom_100",
            self._zoom_reset, "Ctrl+0")
        self._act_fit = self._make_action("전체 맞춤", "zoom_fit",
            self._zoom_fit, "Ctrl+9")
        v.addAction(self._act_zoom100)
        v.addAction(self._act_fit)
        v.addSeparator()
        self._act_snap = self._make_action("스냅 (o-snap)", "snap",
            self._toggle_snap, "F3", checkable=True)
        self._act_snap.setChecked(True)
        self._act_ortho = self._make_action("직교 제약 (Ortho)", "ortho",
            self._toggle_ortho, "F8", checkable=True)
        self._act_grid = self._make_action("격자 (스냅투그리드)", "grid",
            self._toggle_grid, "Shift+G", checkable=True)
        self._act_grid.setChecked(True)
        self._act_align = self._make_action("정렬 가이드선", "align",
            self._toggle_align_guides, "Shift+A", checkable=True)
        self._act_align.setChecked(True)
        v.addAction(self._act_snap)
        v.addAction(self._act_ortho)
        v.addAction(self._act_grid)
        v.addAction(self._act_align)
        v.addSeparator()
        self._act_theme = self._make_action("다크/라이트 전환", "theme",
            self._toggle_theme, "Ctrl+Shift+L")
        v.addAction(self._act_theme)
        self._act_help = self._make_action("단축키 도움말…", "help",
            self._show_shortcuts, "F1")
        v.addAction(self._act_help)

    # ---- 보기: 기준 zoom / 스냅 -------------------------------------------
    def _zoom_reset(self):
        """기준 zoom = 100%(1:1) + 콘텐츠 정중앙으로 이동 — 무한캔버스에서 돌아올 홈.
        [2026-08-01, 사용자 요청] 배율만 리셋하면 스크롤 위치는 그대로 남아 콘텐츠가 화면
        밖일 수 있다는 지적으로, `_zoom_fit`과 같은 기준(itemsBoundingRect 중심)으로 재센터링을
        더했다. `_zoom_fit`과의 차이는 배율 — 이건 항상 정확히 100%로 고정, 전체가 화면에
        들어오도록 줌아웃하지 않는다(목적이 다름: 전체맞춤=조망, 이건=정확한 배율의 홈 위치)."""
        self._view.resetTransform()
        rect = self._scene.itemsBoundingRect()
        if not rect.isEmpty():
            self._view.centerOn(rect.center())
        self._update_zoom_label()
        self._refresh_minimap()

    def _zoom_fit(self):
        # ⚠ [버그 수정 2026-08-01] 도형 boundingRect()의 핸들/히트 패딩은 고정 화면px를
        # `_view_zoom_factor()`(현재 뷰 줌)로 나눠 씬 단위로 환산한다 — 즉 itemsBoundingRect()의
        # 크기 자체가 "지금 줌이 얼마인가"에 달려 있다. 이 함수가 매번 그 줌을 바꾸면 다음 호출의
        # 측정값도 함께 바뀌어, 반복해서 눌러도 값이 수렴하지 않고 계속 바뀌는 것처럼 보였다
        # (사용자 재현 보고). 측정 전 항상 1:1로 리셋해 매번 같은 기준에서 재도록 고정하면
        # 반복 호출 결과가 항상 동일해진다(멱등).
        self._view.resetTransform()
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            self._update_zoom_label()
            self._refresh_minimap()
            return
        pad = max(rect.width(), rect.height()) * 0.05 + 20
        self._view.fitInView(rect.adjusted(-pad, -pad, pad, pad),
                             Qt.AspectRatioMode.KeepAspectRatio)
        self._update_zoom_label()
        self._refresh_minimap()

    def _refresh_minimap(self):
        """[미니맵] 메인 뷰포트 사각형 갱신 — scene.changed를 안 타는 순수 뷰 변환(줌·팬·
        리사이즈) 시점마다 호출. 미니맵 dock 생성 전(초기화 중) 호출 대비 getattr 가드."""
        minimap = getattr(self, "_minimap", None)
        if minimap is not None:
            minimap.viewport().update()

    # ---- 상태 위젯 (토스트) — [캔버스-퍼스트] QStatusBar 대체 ----------------
    def statusBar(self):
        """QMainWindow의 실제 상태바 대신 하단중앙 토스트를 반환 — 기존 `.showMessage()`
        호출부(20여 곳)를 안 건드리고 그대로 흘려보낸다."""
        return self._toast

    def _update_zoom_label(self):
        # [줌 배지 통합 2026-08-01, 사용자 요청] 독립 배지 위젯 대신 미니맵 패널 제목에
        # "미니맵 (100%)"로 직접 표기 — 제목 자체가 클릭 가능(`set_title_click`,
        # `_build_minimap_panel`에서 연결)해 클릭하면 `_zoom_reset`(100%+정중앙 이동)이 뜬다.
        # 휠줌은 배율에 상한이 없어(극단적으로 계속 굴리면 세 자리를 넘는 %도 가능) 긴 텍스트가
        # 제목줄(전체맞춤·접기 버튼과 폭을 나눠 씀)을 밀어 패널이 속성 패널 폭보다 넓어질 수
        # 있다 — 헤더에 남는 여유폭만큼만 표시하고 넘치면 말줄임(가운데 %가 아니라 끝 정보가
        # 덜 중요하므로 ElideRight)으로 자른다.
        panel = getattr(self, "_minimap_panel", None)
        if panel is not None:
            pct = round(self._view.transform().m11() * 100)
            full = f"미니맵 ({pct}%)"
            avail_w = max(40, (self._props_panel.width() or 228) - 57)  # 57≈전체맞춤+접기 버튼·여백
            elided = panel._title_lbl.fontMetrics().elidedText(
                full, Qt.TextElideMode.ElideRight, avail_w)
            panel._title_lbl.setText(elided)
            self._reposition_panels()

    def _toggle_pin(self, checked: bool):
        self.tool_pinned = checked
        self.statusBar().showMessage(
            "도구 고정 — 연속 그리기" if checked else "도구 고정 해제 — 하나 그리면 선택모드", 3000)

    def _toggle_snap(self, checked: bool):
        self.snap_enabled = checked
        self.statusBar().showMessage(
            "스냅 켜짐" if checked else "스냅 꺼짐 — 자유 배치", 3000)

    def _toggle_ortho(self, checked: bool):
        self.ortho_enabled = checked
        self.statusBar().showMessage(
            "Ortho 켜짐 — 수평/수직만" if checked else "Ortho 꺼짐 — 자유 각도", 3000)

    def _toggle_grid(self, checked: bool):
        self.grid_enabled = checked
        self._view.viewport().update()   # 점 격자 즉시 표시/숨김
        self.statusBar().showMessage(
            "격자 켜짐 — 표시 + 스냅" if checked else "격자 꺼짐", 3000)

    def _toggle_align_guides(self, checked: bool):
        self.align_guides_enabled = checked
        self.statusBar().showMessage(
            "정렬 가이드선 켜짐" if checked else "정렬 가이드선 꺼짐 — 스마트 정렬 스냅도 함께 꺼짐", 3000)

    # ---- 저장 / 열기 --------------------------------------------------------
    # [신규기능] DXF/.ecad 통합(2026-07-29 deep-interview) — 옛 「DXF 내보내기/가져오기」
    # 전용 메뉴·단축키(Ctrl+Shift+D/I)를 없애고, 열기(Ctrl+O)/저장(Ctrl+S) 하나가 고른
    # 파일의 확장자로 분기한다. 저장 다이얼로그의 기본 필터는 DXF를 열었던 직후라도
    # 항상 .ecad(무손실)가 먼저 뜨도록 유지 — DXF 가져오기/내보내기는 _doc_path를
    # 갱신하지 않는다(기존 동작 그대로).
    _DOC_FILTER = "Easy CAD 문서 (*.ecad);;DXF 파일 (*.dxf)"
    _OPEN_FILTER = "지원 파일 (*.ecad *.dxf);;Easy CAD 문서 (*.ecad);;DXF 파일 (*.dxf)"

    def _reset_history(self):
        """[M2] 문서 교체(새로/열기/가져오기) 시 undo·redo 스택을 함께 비운다."""
        self._undo.clear()
        self._redo.clear()
        self._refresh_history_actions()

    def _new_doc(self):
        self._scene.clear()
        self._reset_history()
        self._clip.clear()
        self._badge_n = 0
        self._doc_path = None
        self._reset_layers()

    def _open_doc(self):
        """[통합] 확장자로 분기 — .dxf는 DXF 가져오기, 그 외는 .ecad 네이티브 열기.
        둘 다 현재 씬을 통째로 교체(열기 시맨틱) — DXF를 기존 도면 위에 추가 삽입하는
        기능은 스코프 밖(deep-interview 2026-07-29 확정)."""
        path, _ = QFileDialog.getOpenFileName(self, "열기", "", self._OPEN_FILTER)
        if not path:
            return
        if path.lower().endswith(".dxf"):
            if not self._confirm_dxf_open_once():
                return
            self._do_open_dxf(path)
        else:
            self._do_open_ecad(path)

    def _do_open_ecad(self, path: str):
        try:
            n = load_document(self._scene, path)
            layers = load_document_layers(path)
        except Exception as e:  # noqa: BLE001 — 사용자에게 오류만 전달
            QMessageBox.warning(self, "열기 실패", str(e))
            return
        self._reset_history()
        self._doc_path = path
        self._apply_loaded_layers(layers)
        # 번호 마커 카운터를 로드된 최대값 뒤로 재설정
        nums = [it._number for it in self._scene.items() if hasattr(it, "_number")]
        self._badge_n = max(nums) if nums else 0
        self.statusBar().showMessage(f"열기 완료: {n}개 객체 — {path}", 5000)

    def _do_open_dxf(self, path: str):
        try:
            n = import_dxf(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DXF 열기", f"가져오기에 실패했습니다:\n{e}")
            return
        self._reset_history()
        nums = [it._number for it in self._scene.items() if hasattr(it, "_number")]
        self._badge_n = max(nums) if nums else 0
        # [2026-07-29] 외부 DXF는 우리 앱과 원점·스케일이 무관해 가져온 직후 화면 밖이거나
        # 100% 줌에서 너무 작게/크게 보일 수 있다 — 열기 직후 항상 전체 맞춤(Ctrl+9와 동일).
        self._zoom_fit()
        self.statusBar().showMessage(f"가져오기 완료: {n}개 객체 — {path}", 5000)

    def _confirm_dxf_open_once(self) -> bool:
        """[통합] DXF 열기 안내 — 앱 생애 처음 1회만(사용자 요청, QSettings 플래그).
        현재 도면을 통째로 교체한다는 점 + 외부 CAD 도형은 근사 변환될 수 있음을 고지."""
        settings = QSettings("EasyCAD", "EasyCAD")
        if settings.value("dxf_open_notified", False, type=bool):
            return True
        settings.setValue("dxf_open_notified", True)
        resp = QMessageBox.information(
            self, "DXF 열기",
            "DXF를 열면 현재 도면을 통째로 교체합니다(추가 삽입 아님).\n"
            "외부 CAD에서 만든 도형 중 일부(INSERT 배열·클리핑 등)는 근사 변환될 수 있습니다.\n\n"
            "계속 열까요?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        return resp == QMessageBox.StandardButton.Ok

    def _save_doc(self):
        """[통합] 저장 다이얼로그에서 고른 확장자로 분기 — 기본 필터는 항상 .ecad
        (DXF를 방금 열었어도 마찬가지, deep-interview 2026-07-29 결정)."""
        path, _ = QFileDialog.getSaveFileName(
            self, "저장", self._doc_path or "", self._DOC_FILTER)
        if not path:
            return
        if path.lower().endswith(".dxf"):
            if not self._confirm_dxf_save_once():
                return
            self._do_export_dxf(path)
        else:
            if not path.lower().endswith(".ecad"):
                path += ".ecad"
            self._do_save_ecad(path)

    def _do_save_ecad(self, path: str):
        try:
            save_document(self._scene, path, layers=self._layers)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "저장 실패", str(e))
            return
        self._doc_path = path
        self.statusBar().showMessage(f"저장 완료: {path}", 5000)

    def _confirm_dxf_save_once(self) -> bool:
        """[통합] DXF 저장 손실 경고 — 앱 생애 처음 1회만(QSettings 플래그), 이후는 조용히 진행."""
        settings = QSettings("EasyCAD", "EasyCAD")
        if settings.value("dxf_save_warned", False, type=bool):
            return True
        settings.setValue("dxf_save_warned", True)
        resp = QMessageBox.warning(
            self, "DXF로 저장",
            "DXF는 다른 CAD 프로그램과 호환되는 교환 포맷입니다.\n"
            "화살표 지속연결·라벨 위치·심볼 종류·레이어 소속 등 Easy CAD 전용 정보는 "
            "저장되지 않습니다(도형·텍스트·색상·두께·좌표는 보존).\n\n계속 저장할까요?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        return resp == QMessageBox.StandardButton.Ok

    def _export_pdf(self, selection_only: bool):
        if selection_only and not self._scene.selectedItems():
            QMessageBox.information(self, "PDF 내보내기", "선택된 객체가 없습니다.")
            return
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "PDF 내보내기", "출력할 객체가 없습니다.")
            return
        pages = list(PAGE_SIZES.keys())
        page, ok = QInputDialog.getItem(self, "용지 크기", "용지:", pages, 0, False)
        if not ok:
            return
        path, _ = QFileDialog.getSaveFileName(self, "PDF로 저장", "", "PDF 파일 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if export_pdf(self._scene, path, page=page, selection_only=selection_only):
            QMessageBox.information(self, "PDF 내보내기", f"저장 완료:\n{path}")
        else:
            QMessageBox.warning(self, "PDF 내보내기", "저장에 실패했습니다.")

    def _do_export_dxf(self, path: str):
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "DXF로 저장", "저장할 객체가 없습니다.")
            return
        try:
            export_dxf(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DXF로 저장", f"저장에 실패했습니다:\n{e}")
            return
        QMessageBox.information(self, "DXF로 저장", f"저장 완료:\n{path}")

    # ---- 이미지 삽입 (Phase 4) ---------------------------------------------
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
    _IMG_LONG = 400.0   # 삽입 시 긴 변 기본 크기(씬 단위) — 대형 사진이 캔버스를 뒤덮지 않게

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "이미지 삽입", "", "이미지 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not path:
            return
        center = self._view.mapToScene(self._view.viewport().rect().center())
        self._insert_image_at(path, center)

    def _insert_image_at(self, path: str, scene_pos: QPointF):
        """path의 이미지를 scene_pos를 중심으로 삽입(긴 변 _IMG_LONG로 축소, 종횡비 유지)."""
        pm = QPixmap(path)
        if pm.isNull():
            QMessageBox.warning(self, "이미지 삽입", f"이미지를 열 수 없습니다:\n{path}")
            return
        self._insert_pixmap_at(pm, scene_pos, f"이미지 삽입: {pm.width()}×{pm.height()}px — {path}")

    def _insert_pixmap_at(self, pm: QPixmap, scene_pos: QPointF, status_msg: str):
        """QPixmap을 scene_pos 중심에 삽입(긴 변 _IMG_LONG로 축소, 종횡비 유지) — 파일 경로
        유무와 무관한 공통 경로(파일 삽입·드래그앤드롭·클립보드 붙여넣기가 공유)."""
        w, h = pm.width(), pm.height()
        s = min(1.0, self._IMG_LONG / max(w, h)) if max(w, h) > 0 else 1.0
        W, H = w * s, h * s
        item = _ImageItem(pm, QRectF(0.0, 0.0, W, H))
        item.setPos(scene_pos.x() - W / 2.0, scene_pos.y() - H / 2.0)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(status_msg, 4000)

    def _create_shape_at(self, tool_key: str, scene_pos: QPointF):
        """[Phase 6 M3 #17] 팔레트에서 드롭한 도구를 scene_pos 중심에 기본 크기로 생성.
        무장 후 드래그로 그리는 경로(_AnnotatorView.mousePressEvent)와 같은 아이템·펜·플래그를
        써 이후 편집(리사이즈·회전·undo·저장)이 전부 동일하게 동작한다."""
        if tool_key.startswith("sym:"):
            w, h = _PALETTE_SYM_WH
            it = _SymbolItem(tool_key[4:], QRectF(0.0, 0.0, w, h))
        elif tool_key in _PALETTE_DROP_WH:
            w, h = _PALETTE_DROP_WH[tool_key]
            it = (_EllipseItem if tool_key == "ellipse" else _RectItem)(QRectF(0.0, 0.0, w, h))
        else:
            return None
        it.setPen(self.make_pen())
        it.setBrush(self.make_brush())   # [신규기능] sticky 채움색
        it.setPos(scene_pos.x() - w / 2.0, scene_pos.y() - h / 2.0)
        it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(it)
        self._scene.clearSelection()
        it.setSelected(True)
        self.push_undo_add(it)
        return it

    def resizeEvent(self, e):
        # [미니맵] 창 크기가 바뀌면 메인 뷰의 보이는 씬 영역도 바뀐다(스크롤·줌 변화가 없어도) —
        # scene.changed를 안 타므로 명시적으로 미니맵 사각형을 갱신.
        super().resizeEvent(e)
        self._refresh_minimap()
        self._reposition_panels()

    # ---- [캔버스-퍼스트] 플로팅 패널·토스트 위치 계산 -------------------------
    def _reposition_panels(self):
        """좌상단=도형/레이어, 우상단=속성(편집 클러스터). 우하단=미니맵(탐색 클러스터 — 지도 +
        제목에 표기된 줌%, 한 카드 — 줌 배지는 독립 위젯이 아니라 미니맵 패널 제목 자체다,
        `_build_minimap_panel`/`_update_zoom_label` 참조). [2026-08-01 폭 통일] 미니맵 폭을
        속성 패널 폭에 맞춰 매 호출마다 동기화 — 두 패널이 나란히 있을 때 폭이 어긋나 튀어
        보이던 문제(사용자 지적)를 "미니맵이 속성 폭을 따라간다"로 해소. 선택 상태에 따라 속성
        패널 폭이 미세하게 바뀌어도 계속 맞음. 전부 `self._view`가 차지하는 실제 캔버스 영역
        (메뉴·상단툴바 아래) 기준 — `self._view.mapTo(self, ...)` 좌표 관례."""
        panels = (getattr(self, "_left_panel", None), getattr(self, "_props_panel", None),
                  getattr(self, "_minimap_panel", None))
        if any(p is None for p in panels):
            return   # 초기화 중 조기 호출 가드
        left_panel, props_panel, minimap_panel = panels
        m = self._PANEL_MARGIN
        vx, vy = self._view.mapTo(self, QPoint(0, 0)).x(), self._view.mapTo(self, QPoint(0, 0)).y()
        vw, vh = self._view.width(), self._view.height()

        left_panel.adjustSize()
        left_panel.move(vx + m, vy + m)
        left_panel.raise_()

        props_panel.adjustSize()
        props_panel.move(vx + vw - m - props_panel.width(), vy + m)
        props_panel.raise_()

        # ⚠ 속성 패널이 접히면 폭이 헤더만큼 좁아지는데, 그 순간값을 그대로 따라가면 미니맵도
        # 함께 쪼그라들어 "접기 버튼이 미니맵까지 반응한다"는 착시가 생긴다(2026-08-01 사용자
        # 지적). 펼쳐졌을 때 폭만 캐시해 접힘 중엔 그 값을 유지 — 접기는 속성 패널 자기 자신만의
        # 상태여야 한다.
        if not props_panel._collapsed:
            self._props_expanded_w = props_panel.width()
        target_w = getattr(self, "_props_expanded_w", props_panel.width())
        target_h = round(target_w * 9 / 16)
        if self._minimap.width() != target_w or self._minimap.height() != target_h:
            self._minimap.setFixedSize(target_w, target_h)

        minimap_panel.adjustSize()
        minimap_panel.move(vx + vw - m - minimap_panel.width(),
                            vy + vh - m - minimap_panel.height())
        minimap_panel.raise_()

        self._reposition_toast()

    def _reposition_toast(self):
        toast = getattr(self, "_toast", None)
        if toast is None or not toast.isVisible():
            return
        m = self._PANEL_MARGIN
        vpos = self._view.mapTo(self, QPoint(0, 0))
        vx, vy, vw, vh = vpos.x(), vpos.y(), self._view.width(), self._view.height()
        x = vx + (vw - toast.width()) // 2
        y = vy + vh - m - toast.height()
        toast.move(max(vx, x), y)

    # 파일 탐색기에서 이미지를 캔버스로 끌어다 놓기 — QMainWindow가 드롭을 받는다(코어 뷰 무수정).
    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(_PALETTE_MIME) or (
                md.hasUrls() and any(u.toLocalFile().lower().endswith(self._IMG_EXTS)
                                     for u in md.urls())):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(_PALETTE_MIME) or md.hasUrls():
            e.acceptProposedAction()

    def eventFilter(self, obj, event):
        # [M3 #17] 캔버스 뷰포트 위의 팔레트 드래그를 여기서 직접 처리(뷰가 가로채기 전에).
        # 뷰포트 좌표 → mapToScene 로 놓은 자리에 도형 생성. 팔레트 mime가 아니면 통과.
        if obj is self._view.viewport():
            et = event.type()
            if et == QEvent.Type.Resize:
                # [미니맵 실조건 버그] dock 스플리터 드래그로 메인 뷰포트 크기가 바뀌면
                # CanvasWindow.resizeEvent(창 자체 리사이즈)는 안 불려 미니맵 인디케이터가
                # 갱신 안 됐다(사용자 GUI 확인 — 창 크기는 그대로인데 dock 배치만 바뀐 경우).
                # 뷰포트 자체의 resize를 잡아야 원인 불문 항상 정확하다.
                self._refresh_minimap()
            if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasFormat(_PALETTE_MIME):
                    event.acceptProposedAction()
                    return True
            elif et == QEvent.Type.Drop and event.mimeData().hasFormat(_PALETTE_MIME):
                tool_key = bytes(event.mimeData().data(_PALETTE_MIME)).decode("utf-8")
                scene_pos = self._view.mapToScene(event.position().toPoint())
                if self._create_shape_at(tool_key, scene_pos) is not None:
                    event.acceptProposedAction()
                return True
        return super().eventFilter(obj, event)

    def dropEvent(self, e):
        md = e.mimeData()
        # [M3 #17] 팔레트 도형 드롭 — 놓은 위치에 기본 크기로 생성.
        if md.hasFormat(_PALETTE_MIME):
            tool_key = bytes(md.data(_PALETTE_MIME)).decode("utf-8")
            view_pt = self._view.mapFrom(self, e.position().toPoint())
            scene_pos = self._view.mapToScene(view_pt)
            if self._create_shape_at(tool_key, scene_pos) is not None:
                e.acceptProposedAction()
            return
        if not md.hasUrls():
            return
        view_pt = self._view.mapFrom(self, e.position().toPoint())
        scene_pos = self._view.mapToScene(view_pt)
        n = 0
        for u in md.urls():
            p = u.toLocalFile()
            if p.lower().endswith(self._IMG_EXTS):
                self._insert_image_at(p, scene_pos)
                scene_pos = QPointF(scene_pos.x() + 20.0, scene_pos.y() + 20.0)
                n += 1
        if n:
            e.acceptProposedAction()

    # ---- 표제란 / 용지틀 (Phase 4) ------------------------------------------
    def _insert_titleblock(self):
        """용지 크기·방향을 고르고 표제란 프레임을 삽입. 프레임은 뷰 중앙 근처에 좌상단 배치."""
        existing = self._find_titleblock()
        if existing is not None:
            QMessageBox.information(
                self, "표제란", "이미 표제란/용지틀이 있습니다.\n"
                "더블클릭해 내용을 편집하거나, 지운 뒤 다시 삽입하세요.")
            self._scene.clearSelection()
            existing.setSelected(True)
            return
        dlg = _PaperSizeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        size, orient = dlg.result_size_orient()
        item = _TitleBlockItem(size, orient)
        w, h = item.paper_wh()
        center = self._view.mapToScene(self._view.viewport().rect().center())
        item.setPos(center.x() - w / 2.0, center.y() - h / 2.0)
        item.setZValue(-1000.0)   # 용지는 그린 도형들 뒤에(시트처럼)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(
            f"표제란/용지틀 삽입: {size} {orient} — 더블클릭해 필드 입력", 5000)

    def _edit_titleblock(self, item):
        """표제란 더블클릭 → 필드 편집 폼(용지 크기·방향 포함)."""
        dlg = _TitleBlockDialog(self, item)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        size, orient = dlg.result_size_orient()
        item.set_paper(size, orient)
        item.set_fields(dlg.result_fields())
        self.statusBar().showMessage("표제란 갱신됨", 3000)

    def _find_titleblock(self):
        for it in self._scene.items():
            if isinstance(it, _TitleBlockItem):
                return it
        return None

    # ---- 표(table) 삽입 (Phase 4) -------------------------------------------
    _CELL_W, _CELL_H = 40.0, 14.0   # 삽입 시 셀 기본 치수(mm 월드좌표)

    def _insert_table(self):
        """행·열 개수를 고르고 균등 격자 표를 삽입(뷰 중앙에 배치). 셀은 더블클릭해 인라인 편집."""
        dlg = _TableSizeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rows, cols, header = dlg.result()
        W, H = cols * self._CELL_W, rows * self._CELL_H
        item = _TableItem(rows, cols, QRectF(0.0, 0.0, W, H), header=header)
        center = self._view.mapToScene(self._view.viewport().rect().center())
        item.setPos(center.x() - W / 2.0, center.y() - H / 2.0)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(
            f"표 삽입: {rows}×{cols} — 셀 더블클릭해 편집(Enter/Tab 이동)", 5000)

    # ---- Mermaid 가져오기 (Phase 4) -----------------------------------------
    _MMD_NODE_W, _MMD_NODE_H = 120.0, 56.0   # 노드 기본 치수(mermaid_import 레이아웃 상수와 동일)

    def _insert_mermaid(self):
        """Mermaid flowchart 코드를 붙여넣어 편집가능 도형+화살표로 자동배치(뷰 중앙 기준).
        노드는 _RectItem/_EllipseItem/_SymbolItem, 엣지는 _PolyArrowItem 직교 라우팅으로 연결."""
        dlg = _MermaidDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            n_nodes, n_arrows, direction = self._build_mermaid(dlg.text())
        except MermaidError as ex:
            QMessageBox.warning(self, "Mermaid 가져오기", str(ex))
            return
        self.set_tool("select")
        self.statusBar().showMessage(
            f"Mermaid 가져오기: 노드 {n_nodes} · 화살표 {n_arrows} "
            f"(방향 {direction}) — 도형을 개별 이동·편집 가능", 6000)

    def _build_mermaid(self, text):
        """텍스트 → 도형·화살표를 씬에 배치(한 번의 undo). (노드수, 화살표수, 방향) 반환.
        파싱 실패 시 MermaidError를 올린다(UI 없음 — 스모크에서 그대로 호출 가능)."""
        graph = parse_mermaid(text)   # 실패 시 MermaidError

        W, H = self._MMD_NODE_W, self._MMD_NODE_H
        pos = layout_positions(graph, node_w=W, node_h=H)
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        min_x, min_y = (min(xs), min(ys)) if xs else (0.0, 0.0)
        span_x = (max(xs) - min_x + W) if xs else 0.0
        span_y = (max(ys) - min_y + H) if ys else 0.0
        center = self._view.mapToScene(self._view.viewport().rect().center())
        ox = center.x() - span_x / 2.0 - min_x
        oy = center.y() - span_y / 2.0 - min_y

        pen = self.make_pen()
        items_by_id: dict[str, object] = {}
        added: list = []
        for nid, node in graph.nodes.items():
            x, y = pos[nid]
            it = self._make_mermaid_node(node, ox + x, oy + y, W, H, pen)
            self._scene.addItem(it)
            it._sync_label()   # 라벨 중앙 정렬은 씬에 든 뒤라야 동작(_label_alive가 씬 멤버십을 봄)
            items_by_id[nid] = it
            added.append(it)

        arrows: list = []
        for e in graph.edges:
            s = items_by_id.get(e.src)
            d = items_by_id.get(e.dst)
            if s is None or d is None or s is d:   # self-loop은 스킵(직교 엘보 무의미)
                continue
            arr = self._make_mermaid_edge(e, s, d)
            self._scene.addItem(arr)
            arrows.append(arr)
            added.append(arr)

        # 노드·화살표를 모두 씬에 올린 뒤 직교 엘보를 계산(장애물·부착 법선이 씬 존재를 전제).
        for arr in arrows:
            try:
                arr.build_elbow()
            except Exception:
                pass
            arr._sync_label()   # 엣지 라벨도 씬에 든 뒤 재동기(build_elbow가 무변경이면 sync 생략되므로)

        self.push_undo_add_many(added)
        self._scene.clearSelection()
        return len(items_by_id), len(arrows), graph.direction

    def _make_mermaid_node(self, node, x, y, w, h, pen):
        shape, kind = _MERMAID_SHAPE_ITEM.get(node.shape, ("rect", None))
        rect = QRectF(0.0, 0.0, w, h)
        if shape == "ellipse":
            it = _EllipseItem(rect)
        elif shape == "symbol":
            it = _SymbolItem(kind, rect)
        else:
            it = _RectItem(rect)
        it.setPen(QPen(pen))
        it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setPos(x, y)
        it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable)
        if node.label:
            it.ensure_label().setPlainText(node.label)
        return it

    def _make_mermaid_edge(self, edge, src_it, dst_it):
        rs = src_it.mapRectToScene(src_it.rect())
        rd = dst_it.mapRectToScene(dst_it.rect())
        a_src = _border_attach(rs, rd.center())
        a_dst = _border_attach(rd, rs.center())
        arr = _PolyArrowItem(self.current_color, self.current_width, edge.arrow)
        arr.set_points(a_src, a_dst)   # arrow pos=(0,0) → local==scene 좌표
        # 지속 연결 — 도형 이동 시 화살표가 따라오도록 양끝을 부착점에 바인딩(부착점=변 중점 로컬좌표).
        arr.set_bound(0, src_it, src_it.mapFromScene(a_src))
        arr.set_bound(len(arr._pts) - 1, dst_it, dst_it.mapFromScene(a_dst))
        arr._auto_route = True   # 직교 자동 엘보(양끝 바인딩 → build_elbow가 경로 생성)
        if edge.label:
            arr.ensure_label().setPlainText(edge.label)
        return arr

    # ---- 상단 툴바 (QToolBar) -----------------------------------------------
    # [Phase 6 M1] 텍스트 버튼 → 아이콘, 파일·보기 액션을 상단으로 이관, 긴 단축키 라벨은
    # `?` 도움말로 분리. QToolBar를 쓰는 이유: 창을 좁히면 넘치는 버튼이 ≫ 오버플로우로
    # 접혀 창 최소폭이 작아진다(사용자 요청 "축소 유연성"). 그리기 도구는 체크형 커스텀
    # 버튼(set_tool 토글 동기화 유지 → `_tool_buttons`), 나머지는 공유 QAction.
    def _build_toolbar(self):
        tb = self.addToolBar("주 도구모음")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        # 파일 (내보내기·삽입 5종은 이미 「파일」 메뉴에 있어 상단바에서 제거 — 아이콘만으론
        # 기능을 구분하기 어렵다는 사용자 피드백. 단축키(Ctrl+P 등)는 메뉴에서 그대로).
        for a in (self._act_new, self._act_open, self._act_save):
            tb.addAction(a)
        tb.addSeparator()

        # 그리기 도구(체크형) — 네모·원은 왼쪽 「도형」 팔레트로 이관(단축키 2·5는 유지).
        # [화살표 통합] 직선화살(sarrow) 버튼 제거 — 화살표 버튼 하나가 종류(직선·곡선·직각)를
        # 대표한다. [미니패널 통합, 2026-07-31] 상단바 클릭 시 종류를 고르는 메뉴(InstantPopup)는
        # 폐지 — 클릭은 항상 현재 sticky 종류(기본 직각)로 바로 무장/해제하고, 종류 변경은 그린
        # 뒤 속성 dock의 「화살표」 행에서 한다(사용자 피드백: 그리기 전 선택지가 하나 더 있는 게
        # 번거로움, 이미 dock에 같은 메뉴가 있어 중복).
        self._tool_buttons: dict[str, QToolButton] = {}
        for key, name, sc in _TOOLS:
            if key in ("rect", "ellipse", "sarrow"):
                continue
            btn = QToolButton()
            btn.setIcon(_tool_icon(key, self.current_color))
            btn.setIconSize(QSize(20, 20))
            tip = "화살표 (3 — 그린 뒤 속성 패널에서 종류 변경)" \
                if key == "arrow" else f"{name} ({sc})"
            btn.setToolTip(tip)
            btn.setCheckable(True)
            if key == "arrow":
                btn.clicked.connect(lambda _c=False: self.arm_arrow_tool())
            else:
                btn.clicked.connect(
                    lambda _c=False, k=key: self.set_tool(None if self.current_tool == k else k))
            tb.addWidget(btn)
            self._tool_buttons[key] = btn
        self._refresh_arrow_tool_button()   # [화살표 통합] 아이콘을 현재 종류에 맞춤
        # [그룹 재정리 2026-08-01, 사용자 요청] 핀은 "무엇으로 그리는가"에 붙는 도구 옵션이라
        # 그리기 도구 묶음(선택~도형류) 끝으로 옮긴다 — 다음 그룹(되돌리기 이하)과 분리.
        tb.addAction(self._act_pin)
        tb.addSeparator()

        # 편집 / 보기. [100%·전체맞춤 제거 2026-08-01] 휠줌으로 충분히 빠르고(사용자 판단),
        # 전체맞춤은 미니맵 패널 헤더로 이관(공간적 개요라는 같은 맥락) — 메뉴·단축키(Ctrl+0/9)는 유지.
        for a in (self._act_undo, self._act_redo, self._act_snap, self._act_ortho, self._act_grid):
            tb.addAction(a)
        self._refresh_history_actions()   # undo/redo 버튼 초기 활성 상태(둘 다 비어 disabled)

        # 우측 정렬 스페이서 → 도움말.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self._act_theme)
        tb.addAction(self._act_help)
        self._toolbar = tb

    # ---- 테마 (다크 기본 + 라이트 토글) -------------------------------------
    def _apply_theme(self, dark: bool, persist: bool = False):
        """[Phase 6 M1] 다크/라이트 일괄 적용 — 팔레트(Fusion)·캔버스 배경·아이콘 색.
        아이콘은 baked QPixmap이라 테마색이 바뀌면 액션·팔레트 아이콘을 재생성한다.
        persist=True일 때만 QSettings에 저장(테스트가 사용자 설정을 덮지 않도록 분리)."""
        global _ICON_COLOR
        self._dark = dark
        key = "dark" if dark else "light"
        _ICON_COLOR = QColor(_ICON_COLOR_THEME[key])
        app = QApplication.instance()
        if app is not None:
            app.setStyle("Fusion")   # 두 테마 모두 Fusion — 팔레트가 전 위젯에 안정 반영
            app.setPalette(_dark_palette() if dark else app.style().standardPalette())
        self._scene.setBackgroundBrush(QBrush(_CANVAS_BG[key]))
        # 아이콘 재생성: 액션(중립색) + 팔레트/심볼(중립색). 그리기 도구는 draw-color라 무관.
        for act, name in getattr(self, "_icon_actions", ()):
            act.setIcon(_act_icon(name))
        for k, b in getattr(self, "_shape_tool_buttons", {}).items():
            b.setIcon(self._shape_icon(k))
        for k, b in getattr(self, "_sym_buttons", {}).items():
            b.setIcon(self._shape_icon(k))
        # [캔버스-퍼스트] 플로팅 패널 제목줄 = accent 밑줄 + 틴트 배경(옛 dock 제목표시줄과 같은
        # '잡아 눈에 띄는 카드' 언어 유지, 자유 드래그는 없지만 접기 버튼이 있는 자리라 여전히
        # 상호작용 영역으로 보여야 함).
        accent = "#54a9ff" if dark else "#1f7ae0"
        title_bg = "#232f3d" if dark else "#e8eef5"
        # ⚠ [2026-07-31, 스턱루프 규칙 11-b — 3차 접근 전환] 속성 dock의 QSpinBox/QDoubleSpinBox
        # ("두께"·"폰트"·"반경")만 텍스트 디센더가 잘리는 버그 + (2차 시도인 setMinimumHeight
        # 이후) 그 행이 다음 행과 겹치는 새 증상까지 — 둘 다 근본원인은 같았다: `panel.
        # setStyleSheet(...)`를 패널(body의 조상)에 걸면 Qt가 body 하위 위젯 전부를
        # QStyleSheetStyle로 강제 전환해 QAbstractSpinBox의 sizeHint가 네이티브 Fusion보다
        # 짧게 나오고, QFormLayout 행 간격도 그 짧은 sizeHint로 계산돼 실제 위젯 높이
        # (setMinimumHeight로 늘린 값)보다 좁아 다음 행과 겹쳤다. 위젯 레벨 패치(QSS padding→
        # setMinimumHeight)를 두 번 거치고도 같은 자리에서 재발해 메커니즘을 바꿨다: 패널
        # 자체엔 스타일시트를 아예 안 걸어(배경·테두리는 `_FloatingPanel.paintEvent`가 직접
        # 그림) body 전체가 순정 Fusion 계산을 쓰게 하고, 제목줄 강조만 `_head`(body의 조상이
        # 아니라 형제)에 스타일시트로 남긴다.
        head_qss = (
            f"#floatPanelHead {{ background:{title_bg}; border-top-left-radius:5px;"
            f" border-top-right-radius:5px; border-bottom:2px solid {accent}; font-weight:600; }}")
        for panel in (getattr(self, "_left_panel", None), getattr(self, "_props_panel", None),
                      getattr(self, "_minimap_panel", None)):
            if panel is not None:
                panel._head.setStyleSheet(head_qss)
                panel.update()
        # [그룹 구분 디자인 2026-08-01, 사용자 요청] 기본 QToolBar 구분선은 Fusion에서 거의
        # 안 보일 정도로 옅다 — 파일(새로 만들기~저장) / 도구(선택~핀) / 편집·보기(되돌리기~격자)
        # 3그룹이 한눈에 갈리도록 구분선을 굵고 여백 있게 강조.
        toolbar = getattr(self, "_toolbar", None)
        if toolbar is not None:
            sep_color = "#3d4b5c" if dark else "#c9d3dc"
            toolbar.setStyleSheet(
                f"QToolBar::separator {{ background:{sep_color}; width:1px; margin:6px 9px; }}")
        toast = getattr(self, "_toast", None)
        if toast is not None:
            toast.setStyleSheet(
                f"#toastLabel {{ background:{title_bg}; border:1px solid {accent};"
                " border-radius:6px; padding:4px 12px; }")
        minimap = getattr(self, "_minimap", None)
        if minimap is not None:
            minimap.viewport().update()   # 씬 배경색(다크/라이트)이 바뀌므로 재도색
        if persist:
            QSettings("EasyCAD", "EasyCAD").setValue("dark", dark)

    def _toggle_theme(self):
        self._apply_theme(not self._dark, persist=True)
        self.statusBar().showMessage("다크 모드" if self._dark else "라이트 모드", 2500)

    def _show_shortcuts(self):
        """[Phase 6 M1] 상단바에서 뺀 단축키 안내를 도움말 다이얼로그로."""
        rows = [
            ("휠", "확대·축소 (커서 기준)"),
            ("Shift + 휠", "선 두께·도형 크기 조절"),
            ("가운데버튼 드래그", "화면 이동(팬)"),
            ("Ctrl+0 / Ctrl+9", "100%(1:1) / 전체 맞춤"),
            ("F3 / F8", "스냅 / 직교 제약 토글"),
            ("Shift+G", "격자 표시/스냅투그리드 토글"),
            ("Shift+A", "정렬 가이드선(스마트 정렬 스냅) 토글"),
            ("Del", "선택 객체 삭제"),
            ("Ctrl+Z", "되돌리기"),
            ("Ctrl+C / Ctrl+V", "복사 / 연속 붙여넣기(버퍼 없으면 클립보드 이미지)"),
            ("Ctrl+D", "제자리 복제"),
            ("1·3·4·6·7·8", "선택·화살표·텍스트·선·펜·번호"),
            ("3", "화살표(그린 뒤 미니툴바서 직선·곡선·직각 선택)"),
            ("2 / 5", "네모 / 원"),
        ]
        body = "\n".join(f"{k:<20}{d}" for k, d in rows)
        box = QMessageBox(self)
        box.setWindowTitle("단축키 도움말")
        box.setText("Easy CAD 단축키")
        box.setInformativeText(body)
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.exec()

    # ---- 도형 팔레트 (좌측 dock) — 기본(네모·원) + 순서도/결선도(심볼 14종) -----------
    @staticmethod
    def _shape_icon(kind: str, px: int = 30) -> QIcon:
        """팔레트 아이콘 — 캔버스 도형과 같은 모양으로 그린다. 심볼은 경로 팩토리,
        기본 도형(rect/ellipse)은 직접."""
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(_ICON_COLOR)); pen.setWidthF(1.6)   # 테마색(다크/라이트 적응)
        p.setPen(pen); p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        m = 4
        r = QRectF(m, m, px - 2 * m, px - 2 * m)
        if kind == "rect":
            p.drawRect(r)
        elif kind == "ellipse":
            p.drawEllipse(r)
        else:
            p.drawPath(_SYMBOL_KINDS[kind][1](r))
        p.end()
        return QIcon(pm)

    def _render_drag_preview(self, tool_key: str) -> QPixmap | None:
        """[UX] 팔레트 드래그 픽스맵을 툴 아이콘 대신 실제 생성될 도형(현재 색·두께·비율)으로
        렌더 — 드롭 전에도 크기·모양을 직관적으로 파악하게. 현재 줌 배율을 반영하되, 극단 줌에서
        드래그 커서가 점이 되거나 거대해지지 않도록 최종 픽셀 크기를 클램프한다."""
        if tool_key.startswith("sym:"):
            kind = tool_key[4:]
            if kind not in _SYMBOL_KINDS:
                return None
            w, h = _PALETTE_SYM_WH
            path_fn = _SYMBOL_KINDS[kind][1]
        elif tool_key in _PALETTE_DROP_WH:
            kind = tool_key
            w, h = _PALETTE_DROP_WH[tool_key]
            path_fn = None
        else:
            return None
        scale = self._view.transform().m11()
        pw, ph = w * scale, h * scale
        long_side = max(pw, ph)
        if long_side < 24.0:
            f = 24.0 / long_side
            pw *= f; ph *= f
        elif long_side > 220.0:
            f = 220.0 / long_side
            pw *= f; ph *= f
        pw, ph = max(1, round(pw)), max(1, round(ph))
        pen = self.make_pen()
        margin = pen.widthF() / 2.0 + 2.0
        pm = QPixmap(pw, ph)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(pen)
        p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        r = QRectF(margin, margin, max(1.0, pw - 2 * margin), max(1.0, ph - 2 * margin))
        if kind == "rect":
            p.drawRect(r)
        elif kind == "ellipse":
            p.drawEllipse(r)
        else:
            p.drawPath(path_fn(r))
        p.end()
        return pm

    def _palette_button(self, label: str, icon_kind: str, tooltip: str, tool_key: str) -> QToolButton:
        btn = _PaletteButton(tool_key, preview_fn=self._render_drag_preview)   # [M3 #17] 클릭=무장 / 드래그=캔버스 드롭 생성
        btn.setText(label)
        btn.setIcon(self._shape_icon(icon_kind))
        btn.setIconSize(QSize(30, 30))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(QSize(64, 56))   # 고정 크기 — dock이 넓어도 버튼이 커지거나 벌어지지 않게
        btn.clicked.connect(
            lambda _c=False, k=tool_key: self.set_tool(None if self.current_tool == k else k))
        return btn

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#888; font-size:11px; padding:3px 2px 1px 2px;")
        return lbl

    def _make_shape_section(self, title, entries, store) -> QWidget:
        """[Phase 6 M1] 팔레트 한 섹션(제목+그리드)을 독립 위젯으로."""
        sec = QWidget()
        v = QVBoxLayout(sec)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(4)
        v.addWidget(self._section_label(title))
        grid = QGridLayout(); grid.setSpacing(4)
        btns = []
        for label, icon_kind, tooltip, tool_key in entries:
            btn = self._palette_button(label, icon_kind, tooltip, tool_key)
            store[icon_kind] = btn   # 기본=rect/ellipse, 심볼=kind(=icon_kind)로 키
            btns.append(btn)
        v.addLayout(grid)
        self._shape_sections.append((grid, btns))
        return sec

    def _relayout_sections(self, horiz: bool = False):
        """[캔버스-퍼스트] 각 섹션 그리드를 2열로 배치. `horiz` 인자는 옛 dock 상/하 재도킹 시
        한 줄로 눕히던 반응형 레이아웃의 흔적(플로팅 패널은 위치 고정이라 대상 없음) — 항상
        False로만 호출되지만, 초기 빌드 호출부(`_build_left_panel`)와의 계약을 그대로 둔다."""
        for grid, btns in self._shape_sections:
            for b in btns:
                grid.removeWidget(b)
            cols = len(btns) if horiz else 2
            for i, b in enumerate(btns):
                grid.addWidget(b, i // cols, i % cols)
            # 스트레치 초기화 후 실제 열 다음 빈 열에만 1 → 넓어져도 버튼은 좌측 정렬 유지.
            for ci in range(len(btns) + 2):
                grid.setColumnStretch(ci, 0)
            grid.setColumnStretch(cols, 1)

    def _build_left_panel(self):
        """[캔버스-퍼스트] 도형 + 레이어를 탭 하나로 묶은 좌상단 플로팅 카드.
        [self-review 수정, 실사용 피드백 2026-07-29] 처음엔 `QTabWidget`으로 구현했는데,
        내부 `QStackedLayout`의 sizeHint()가 **탭 전환과 무관하게 모든 페이지의 최대 크기**로
        고정되는 Qt 기본 동작 때문에, 콘텐츠가 짧은 레이어 탭을 봐도 패널이 더 긴 도형 탭
        크기(272×320) 그대로 남아 빈 공간이 생겼다(실측: 도형/레이어 두 탭 모두 274×348로
        동일 — 레이어 페이지 자체 sizeHint는 268×95에 불과한데 반영이 안 됨). 대신 두 콘텐츠
        위젯을 같은 `QVBoxLayout`에 넣고 `setVisible()`로 토글 — 일반 레이아웃은 숨긴 위젯을
        sizeHint 계산에서 제외하므로(= `_FloatingPanel`의 접기 버튼과 같은 원리, 이미 검증됨)
        보이는 쪽 크기로만 정확히 줄어든다."""
        panel = _FloatingPanel(self, "", "left")
        self._left_panel = panel
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        tab_row = QWidget()
        tr = QHBoxLayout(tab_row)
        tr.setContentsMargins(4, 4, 4, 0); tr.setSpacing(2)
        self._left_tab_buttons: dict[str, QToolButton] = {}
        for key, label in (("shapes", "도형"), ("layers", "레이어")):
            b = QToolButton(); b.setText(label); b.setCheckable(True)
            b.clicked.connect(lambda _c=False, k=key: self._switch_left_tab(k))
            tr.addWidget(b)
            self._left_tab_buttons[key] = b
        tr.addStretch(1)
        outer.addWidget(tab_row)

        shapes_page = QWidget()
        box = QVBoxLayout(shapes_page)
        box.setContentsMargins(6, 6, 6, 6); box.setSpacing(10)
        self._shape_tool_buttons: dict[str, QToolButton] = {}
        self._sym_buttons: dict[str, QToolButton] = {}
        self._shape_sections: list = []   # (grid, buttons)
        basic = self._make_shape_section("기본", [
            ("네모", "rect", "네모 — 클릭 후 캔버스에 드래그", "rect"),
            ("원", "ellipse", "원 — 클릭 후 캔버스에 드래그", "ellipse"),
        ], self._shape_tool_buttons)
        sym_entries = [(label, kind, f"{label} 심볼 — 클릭 후 캔버스에 드래그", f"sym:{kind}")
                       for kind, (label, _fn) in _SYMBOL_KINDS.items()]
        syms = self._make_shape_section("순서도", sym_entries, self._sym_buttons)
        box.addWidget(basic); box.addWidget(syms)
        self._relayout_sections(horiz=False)   # 항상 세로(2열) — 반응형 전환 없음
        outer.addWidget(shapes_page)
        self._left_pages = {"shapes": shapes_page}

        layers_page = QWidget()
        v = QVBoxLayout(layers_page)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)
        self._layers_list = QListWidget()
        self._layers_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        v.addWidget(self._layers_list)
        add_btn = QToolButton()
        add_btn.setText("+ 레이어 추가")
        add_btn.clicked.connect(lambda: self.add_layer())
        v.addWidget(add_btn)
        outer.addWidget(layers_page)
        self._left_pages["layers"] = layers_page

        self._left_container = container
        panel.set_content(container)
        self._switch_left_tab("shapes")
        self._refresh_layers_panel()

    def _switch_left_tab(self, key: str):
        for k, page in self._left_pages.items():
            page.setVisible(k == key)
        for k, btn in self._left_tab_buttons.items():
            btn.setChecked(k == key)
        # [self-review 수정] setVisible() 직후 곧바로 adjustSize()를 부르면 레이아웃 무효화가
        # 아직 반영되기 전이라 sizeHint()가 한 박자 stale해 패널이 이전(더 큰) 크기에 멈춰버렸다
        # (실측: 도형→레이어→도형으로 돌아가도 레이어 탭 크기 그대로 남음). 레이아웃을 명시적으로
        # activate()해 즉시 재계산시킨 뒤 adjustSize — `_compact_shapes_dock`가 겪었던 것과 같은
        # 부류의 Qt 레이아웃 타이밍 함정이지만, 여긴 QTimer.singleShot 없이 activate()만으로 충분.
        self._left_container.layout().activate()
        self._left_panel.layout().activate()
        self._left_panel.adjustSize()
        self._reposition_panels()

    # ---- 속성 패널 (M2 #2: 편집 — 색·두께·선스타일·폰트를 push_undo_state 경로로) ----
    _PEN_STYLE_ITEMS = [
        (Qt.PenStyle.SolidLine, "실선"), (Qt.PenStyle.DashLine, "점선"),
        (Qt.PenStyle.DotLine, "점선(도트)"), (Qt.PenStyle.DashDotLine, "일점쇄선"),
        (Qt.PenStyle.DashDotDotLine, "이점쇄선"),
    ]

    def _build_properties_panel(self):
        panel = _FloatingPanel(self, "속성", "props")
        self._props_panel = panel
        self._pf_updating = False   # 프로그램적 값 세팅 중엔 편집 시그널 무시(피드백 차단)
        content = QWidget()
        content.setMinimumWidth(170)   # 값·컨트롤이 안 잘리는 바닥폭 — 이 아래로는 못 좁힘(슬랙 없음)
        form = QFormLayout(content)
        form.setContentsMargins(10, 10, 10, 10); form.setSpacing(8)

        self._pf_type = QLabel("—")

        # 색 — 스와치 버튼(현재색 표시) → 클릭 시 QColorDialog.
        self._pf_color = QToolButton()
        self._pf_color.setFixedSize(QSize(48, 20))
        self._pf_color.setToolTip("클릭: 색 선택")
        self._pf_color.clicked.connect(self._edit_color)
        self._pf_color_val = QLabel("—"); self._pf_color_val.setStyleSheet("color:#888;")
        color_row = QWidget(); ch = QHBoxLayout(color_row)
        ch.setContentsMargins(0, 0, 0, 0); ch.setSpacing(6)
        ch.addWidget(self._pf_color); ch.addWidget(self._pf_color_val, 1)

        # [신규기능] 채움 — 스와치 하나(클릭=그리드 팝업, "없음"도 팝업 안 항목). rect/ellipse/
        # symbol 전용, 대상 없으면 행 자체를 비활성화(has_fill로 판정, _refresh_properties).
        self._pf_fill = QToolButton()
        self._pf_fill.setFixedSize(QSize(48, 20))
        self._pf_fill.setToolTip("클릭: 채움색 선택")
        self._pf_fill.clicked.connect(self._edit_fill)
        self._pf_fill_val = QLabel("—"); self._pf_fill_val.setStyleSheet("color:#888;")
        fill_row = QWidget(); fh = QHBoxLayout(fill_row)
        fh.setContentsMargins(0, 0, 0, 0); fh.setSpacing(6)
        fh.addWidget(self._pf_fill); fh.addWidget(self._pf_fill_val, 1)

        # 두께 — 스핀박스(px).
        self._pf_width = QDoubleSpinBox()
        self._pf_width.setRange(0.5, 50.0); self._pf_width.setSingleStep(0.5)
        self._pf_width.setDecimals(1); self._pf_width.setSuffix(" px")
        self._pf_width.valueChanged.connect(self._edit_width)

        # 선스타일 — 콤보(pen 기반 도형 전용; 화살표·DXF는 #3).
        self._pf_style = QComboBox()
        for st, name in self._PEN_STYLE_ITEMS:
            self._pf_style.addItem(name, st)
        self._pf_style.currentIndexChanged.connect(self._edit_style)

        # 폰트 — 스핀박스(pt; 텍스트/라벨 전용).
        self._pf_font = QSpinBox()
        self._pf_font.setRange(_MIN_FONT, _MAX_FONT); self._pf_font.setSuffix(" pt")
        self._pf_font.valueChanged.connect(self._edit_font)

        form.addRow("종류", self._pf_type)
        form.addRow("색", color_row)
        form.addRow("채움", fill_row)
        form.addRow("두께", self._pf_width)
        form.addRow("선", self._pf_style)
        form.addRow("폰트", self._pf_font)

        # [미니패널 통합, 2026-07-31] 선택 위를 따라다니던 플로팅 컨텍스트 툴바(M3 #15)를
        # 폐지하고 그 안의 타입 전용 액션 4개를 여기로 이관 — 사용자 피드백: 우측 속성 dock과
        # 겹치는 부분(색·선스타일)이 많아 따라다니는 패널이 방해로 느껴짐. 색·선스타일은 위 행이
        # 이미 대신하고, 아래 4개는 dock에 없던 것들이라 새로 추가한다. 핸들러(_swap_selected·
        # _floating_set_arrow_kind·_floating_set_radius·_floating_flip_arrows)는 플로팅 툴바가
        # 쓰던 것을 그대로 재사용(로직 변경 없음), 행 노출만 옛 _reposition_floating_toolbar의
        # show_swap/show_routing/curved/show_dir 판정을 그대로 옮겨 _refresh_properties가 담당.
        self._pf_swap_btn = QToolButton(); self._pf_swap_btn.setText("⬗ 바꾸기")
        self._pf_swap_btn.setToolTip("도형 바꾸기(크기·연결 유지)")
        self._pf_swap_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._pf_swap_btn.setMenu(self._build_swap_menu())
        form.addRow("도형", self._pf_swap_btn)

        self._pf_routing_btn = QToolButton(); self._pf_routing_btn.setText("⌐▾ 종류")
        self._pf_routing_btn.setToolTip("화살표 종류(직선·곡선·직각)")
        self._pf_routing_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._pf_routing_btn.setMenu(self._build_routing_menu())
        form.addRow("화살표", self._pf_routing_btn)

        self._pf_radius = QSpinBox()
        self._pf_radius.setRange(0, int(_PolyArrowItem._CURVE_R_MAX))
        self._pf_radius.setSingleStep(2)
        self._pf_radius.setSuffix(" px")
        self._pf_radius.setKeyboardTracking(False)   # 타이핑 중 매 글자 커밋 방지
        # ⚠ NoFocus 필수 — Del·Ctrl+D·도구 숫자키는 뷰의 keyPressEvent가 처리한다(윈도 QAction이
        # 아님). 스핀박스가 포커스를 가져가면 반경을 만진 뒤 그 단축키들이 캔버스로 안 간다.
        self._pf_radius.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pf_radius.setToolTip("곡선 반경(0=직각)")
        self._pf_radius.valueChanged.connect(self._floating_set_radius)
        form.addRow("반경", self._pf_radius)

        self._pf_dir_btn = QToolButton(); self._pf_dir_btn.setText("⇄ 뒤집기")
        self._pf_dir_btn.setToolTip("화살표 방향 뒤집기")
        self._pf_dir_btn.clicked.connect(self._floating_flip_arrows)
        form.addRow("방향", self._pf_dir_btn)

        self._pf_hint = QLabel("객체를 선택하면 속성을 편집할 수 있습니다.")
        self._pf_hint.setStyleSheet("color:#888; font-size:11px;")
        self._pf_hint.setWordWrap(True)   # 줄바꿈 허용 → 안내문이 패널 최소폭을 붙잡지 않게
        form.addRow(self._pf_hint)
        panel.set_content(content)
        self._props_form = form
        self._scene.selectionChanged.connect(self._refresh_properties)
        self._refresh_properties()

    # ---- 미니맵 패널 (신규기능 — deep-interview 2026-07-28) ------------------
    def _build_minimap_panel(self):
        """메인과 같은 scene을 공유하는 축소 뷰. 내용 갱신은 Qt가 자동(멀티뷰) — 여기선 메인
        뷰의 줌/팬/리사이즈(scene.changed를 안 타는 순수 뷰 변환) 시점에만 명시적으로 미니맵을
        다시 그리도록 훅을 건다."""
        panel = _FloatingPanel(self, "미니맵 (100%)", "minimap")
        self._minimap_panel = panel
        # [줌 배지 통합 2026-08-01, 사용자 요청 2차] 처음엔 독립 배지 → 미니맵 하단 푸터 행으로
        # 옮겼다가, "숫자를 '미니맵(50%)'처럼 제목에 표기하고 그 %를 클릭하면 100%+정중앙
        # 이동"이라는 후속 요청으로 한 번 더 바뀌었다 — 별도 배지 위젯 없이 제목 자체가 표기와
        # 클릭을 겸한다(`set_title_click`). 지도 위 오버레이로 그리지 않는 이유는 그대로다:
        # 2026-07-28 미니맵 인디케이터 이중변환 사고 같은 좌표계 버그를 또 만들 여지를 피한다.
        panel.set_title_click(self._zoom_reset)
        # [사용자 요청 2026-08-01] 전체 맞춤(Ctrl+9)을 상단바에서 빼고 여기로 이관 — 공간
        # 개요라는 같은 맥락(미니맵도 "전체가 어디 있나"를 보여주는 도구). 기존 `_act_fit`을
        # 그대로 재사용해(아이콘·툴팁·단축키 동기화 유지) 제목과 접기버튼 사이에 끼운다.
        fit_btn = QToolButton()
        fit_btn.setDefaultAction(self._act_fit)
        fit_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        fit_btn.setAutoRaise(True)
        fit_btn.setFixedSize(QSize(18, 18))
        fit_btn.setIconSize(QSize(14, 14))
        panel._head.layout().insertWidget(1, fit_btn)
        self._minimap = _MinimapView(self, self._scene)
        # [폭 통일 2026-08-01, 사용자 요청] 옛 228×128 고정폭이 속성 패널(콘텐츠 기준 ~200px대)
        # 보다 넓어 두 패널이 나란히 있을 때 튀어 보였다 — 미니맵 폭을 속성 패널 폭에 맞춘다.
        # 이 초기값은 `_reposition_panels()`가 매 호출마다 다시 동기화한다(선택 상태에 따라
        # 속성 패널 폭이 미세하게 바뀌어도 계속 따라가게 — _INDICATOR_PX 고정px 전환
        # 이후로는 폭을 줄여도 인디케이터가 작아 보이던 옛 버그가 재발하지 않는다). 세로는
        # 실제 작업 화면(16:9) 비율 유지.
        w0 = self._props_panel.width() or 228
        self._minimap.setFixedSize(QSize(w0, round(w0 * 9 / 16)))
        panel.set_content(self._minimap)

        self._view.horizontalScrollBar().valueChanged.connect(self._refresh_minimap)
        self._view.verticalScrollBar().valueChanged.connect(self._refresh_minimap)
        # [실조건 재현 후 접근 전환 — 규칙 11-b] 창 리사이즈·dock 스플리터 리사이즈·뷰포트
        # 이벤트를 각각 정확히 잡으려던 두 차례 시도(커밋 16c7551계열·2bd6827)가 실사용에서도
        # 여전히 어긋났다 — Qt의 dock 레이아웃 재계산 시점과 이벤트 발화 시점이 어긋날 수 있어
        # 트리거를 더 정밀하게 좁히는 접근 자체가 계속 빈틈을 남긴다. 트리거를 놓치지 않으려
        # 애쓰는 대신 **짧은 주기 폴링**으로 전환 — 미니맵은 도형 몇 개짜리 작은 뷰라 200ms마다
        # 다시 그리는 비용이 무시할 수준이고, 어떤 이벤트를 놓치든 최대 200ms 안에 저절로 맞는다.
        # 기존 이벤트 훅(줌·스크롤바·리사이즈)은 즉각 반응용으로 그대로 두고 이 타이머는 안전망.
        self._minimap_timer = QTimer(self)
        self._minimap_timer.timeout.connect(self._refresh_minimap)
        self._minimap_timer.start(200)

    def _item_layer_id(self, it) -> str:
        return getattr(it, "_layer_id", None) or "default"

    def _layer_by_id(self, layer_id):
        return next((ly for ly in self._layers if ly["id"] == layer_id), None)

    def _items_in_layer(self, layer_id):
        return [it for it in self._zorder_pool() if self._item_layer_id(it) == layer_id]

    def _refresh_layers_panel(self):
        lst = self._layers_list
        lst.clear()
        for layer in self._layers:
            row = self._make_layer_row(layer)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            lst.addItem(item)
            lst.setItemWidget(item, row)
        # [캔버스-퍼스트] QListWidget의 기본 sizeHint는 항목 수와 무관하게 넓은 고정값이라
        # 플로팅 카드가 콘텐츠보다 훨씬 커진다 — 실제 행 높이 합으로 클램프해야 낭비 공간이
        # 안 생긴다(옛 dock이 칼럼 전체를 예약해 항목 0개에도 창 높이만큼 비던 문제의 재발 방지).
        total_h = sum(lst.sizeHintForRow(i) for i in range(lst.count())) + 2 * lst.frameWidth() + 4
        lst.setFixedHeight(max(60, min(total_h, 320)))
        if getattr(self, "_left_panel", None) is not None:
            self._reposition_panels()

    def _make_layer_row(self, layer: dict) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(6)
        lid = layer["id"]

        vis_btn = QToolButton()
        vis_btn.setCheckable(True)
        vis_btn.setChecked(layer["visible"])
        vis_btn.setText("👁" if layer["visible"] else "🚫")
        vis_btn.setToolTip("레이어 표시/숨김")
        vis_btn.toggled.connect(lambda checked, i=lid: self.set_layer_visible(i, checked))

        lock_btn = QToolButton()
        lock_btn.setCheckable(True)
        lock_btn.setChecked(layer["locked"])
        lock_btn.setText("🔒" if layer["locked"] else "🔓")
        lock_btn.setToolTip("레이어 잠금")
        lock_btn.toggled.connect(lambda checked, i=lid: self.set_layer_locked(i, checked))

        count = len(self._items_in_layer(lid))
        name_lbl = QLabel(f'{layer["name"]} ({count})')
        name_lbl.setWordWrap(False)

        h.addWidget(vis_btn)
        h.addWidget(lock_btn)
        h.addWidget(name_lbl, 1)

        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(
            lambda pos, i=lid, r=row: self._show_layer_row_menu(r, i))
        return row

    def _show_layer_row_menu(self, row: QWidget, layer_id: str):
        menu = QMenu(self)
        menu.addAction("이름 변경...", lambda: self._prompt_rename_layer(layer_id))
        if layer_id != "default":
            menu.addAction("삭제", lambda: self.delete_layer(layer_id))
        menu.exec(row.mapToGlobal(row.rect().center()))

    def _prompt_rename_layer(self, layer_id: str):
        layer = self._layer_by_id(layer_id)
        if layer is None:
            return
        name, ok = QInputDialog.getText(self, "레이어 이름 변경", "이름:", text=layer["name"])
        if ok:
            self.rename_layer(layer_id, name)

    def add_layer(self, name: str | None = None) -> dict:
        name = (name or "").strip() or f"레이어 {len(self._layers) + 1}"
        layer = {"id": uuid.uuid4().hex[:8], "name": name, "visible": True, "locked": False}
        self._layers.append(layer)
        self._refresh_layers_panel()
        return layer

    def rename_layer(self, layer_id: str, name: str):
        layer = self._layer_by_id(layer_id)
        if layer is not None and name.strip():
            layer["name"] = name.strip()
            self._refresh_layers_panel()

    def delete_layer(self, layer_id: str):
        """기본 레이어는 삭제 불가(최소 1개 유지). 소속 아이템은 기본 레이어로 소급."""
        if layer_id == "default" or self._layer_by_id(layer_id) is None:
            return
        for it in self._items_in_layer(layer_id):
            it._layer_id = None
            self._sync_item_to_layer_state(it)   # 기본 레이어의 현재 표시/잠금을 물려받음
        self._layers = [ly for ly in self._layers if ly["id"] != layer_id]
        self._refresh_layers_panel()

    def set_layer_visible(self, layer_id: str, visible: bool):
        """[신규기능] 레이어 표시 토글 — undo 비대상(다크모드·그리드 토글과 같은 문서 설정,
        규칙 10-b 상시 갱신 대상이 아닌 뷰/구성 상태). 새로 만든 아이템은 자동배정하지 않는
        스코프 결정 때문에, 생성 시점엔 반영 안 되고 이 토글이 다시 눌릴 때 반영된다."""
        layer = self._layer_by_id(layer_id)
        if layer is None:
            return
        layer["visible"] = visible
        for it in self._items_in_layer(layer_id):
            it.setVisible(visible)
        self._refresh_layers_panel()

    def set_layer_locked(self, layer_id: str, locked: bool):
        """레이어 잠금 — 개별 Ctrl+L과 같은 _locked 플래그를 재사용(별도 필드 없음).
        ⚠ 알려진 한계: 레이어 잠금을 풀면 그 안에서 개별로 잠갔던 아이템도 함께 풀린다
        (레이어-개별 잠금 상호작용은 1차 스코프 밖 — Not-tested)."""
        layer = self._layer_by_id(layer_id)
        if layer is None:
            return
        layer["locked"] = locked
        for it in self._items_in_layer(layer_id):
            self._set_item_lock_flags(it, locked)
        self._refresh_layers_panel()

    def _sync_item_to_layer_state(self, it):
        """아이템의 표시/잠금을 현재 _layer_id가 가리키는 레이어 상태와 맞춘다 — 이동(forward)·
        undo/redo·삭제(기본으로 소급) 세 경로가 전부 이걸 거쳐야 '레이어를 옮기면 그 레이어의
        표시/잠금을 물려받는다'는 계약이 undo 후에도 깨지지 않는다(레이어 자체에는 별도 snapshot을
        안 남기고 _layer_id 하나로부터 항상 다시 계산 — single source of truth)."""
        layer = self._layer_by_id(self._item_layer_id(it)) or self._layer_by_id("default")
        if layer is not None:
            it.setVisible(layer["visible"])
            self._set_item_lock_flags(it, layer["locked"])

    def move_selection_to_layer(self, layer_id: str):
        if self._layer_by_id(layer_id) is None:
            return
        targets = self._edit_targets()
        if not targets:
            return
        snaps = [(it, getattr(it, "_layer_id", None)) for it in targets]
        for it in targets:
            it._layer_id = layer_id
            self._sync_item_to_layer_state(it)
        self._push_entry([("mut", it, "layer", old, layer_id) for it, old in snaps])
        self._refresh_layers_panel()
        self.statusBar().showMessage(
            f'레이어 이동: {len(targets)}개 → {self._layer_by_id(layer_id)["name"]}', 2500)

    def _build_layer_menu(self, title: str, parent=None) -> QMenu:
        m = QMenu(title, parent or self)
        for layer in self._layers:
            m.addAction(layer["name"], lambda checked=False, i=layer["id"]:
                        self.move_selection_to_layer(i))
        return m

    def _reset_layers(self):
        """새 문서 — 레이어를 기본 하나로 리셋."""
        self._layers = [{"id": "default", "name": "기본", "visible": True, "locked": False}]
        if hasattr(self, "_layers_list"):
            self._refresh_layers_panel()

    def _apply_loaded_layers(self, layers):
        """열기 — 저장된 레이어 목록을 복원하고 표시/잠금을 아이템에 재적용.
        옛 .ecad(레이어 키 없음)는 기본 레이어로 리셋."""
        self._layers = layers if layers else [
            {"id": "default", "name": "기본", "visible": True, "locked": False}]
        for it in self._zorder_pool():
            self._sync_item_to_layer_state(it)
        self._refresh_layers_panel()

    # ---- 속성 편집 → push_undo_state (M2 #2) --------------------------------
    def _edit_items(self, targets, fn, key=None):
        """선택 대상 targets에 fn을 적용하고 하나의 undo 엔트리(state)로 저널에 싣는다.
        key가 있으면 연속 편집(스핀박스 드래그)을 undo 1스텝으로 병합."""
        if self._pf_updating or not targets:
            return
        snaps = [(it, it.capture_state()) for it in targets]
        for it in targets:
            fn(it)
        self.push_undo_state(snaps, coalesce_key=key)
        self._refresh_properties()

    def arm_arrow_tool(self):
        """[화살표 통합] 사용자가 '화살표'를 무장하는 단일 진입점(툴바 버튼·단축키 3·9).
        현재 종류(sticky)가 내부 도구를 정한다 — 곡선·직선=arrow, 직각=sarrow. 이미 화살표가
        무장돼 있으면 끈다(토글). set_tool은 리터럴로 남겨 두고(테스트·내부 호출이 정확히 그 도구를
        받게) 이 메서드만 종류→도구 변환을 담당한다."""
        if self.current_tool in ("arrow", "sarrow"):
            self.set_tool(None)
            return
        self.set_tool(_ARROW_KIND_TOOL.get(self.current_arrow_kind, "arrow"))

    def _refresh_arrow_tool_button(self):
        """[화살표 통합] 툴바 화살표 아이콘을 현재 종류에 맞춘다 — 직각이면 직각 커넥터 아이콘."""
        btn = getattr(self, "_tool_buttons", {}).get("arrow")
        if btn is not None:
            btn.setIcon(_tool_icon(_ARROW_KIND_TOOL.get(self.current_arrow_kind, "arrow"),
                                   self.current_color))

    def _set_current_color(self, color: QColor):
        """[M2 #A] 현재 색을 갱신하고 상단 그리기 도구 아이콘을 그 색으로 다시 칠한다
        (도구 아이콘은 draw-color라 테마와 무관 — 여기서만 갱신). 새 도형·화살표에 반영."""
        self.current_color = QColor(color)
        for key, b in getattr(self, "_tool_buttons", {}).items():
            b.setIcon(_tool_icon(key, self.current_color))
        self._refresh_arrow_tool_button()   # [화살표 통합] 화살표만 종류별 아이콘이라 덮어쓴다

    def _show_color_grid_popup(self, anchor: QWidget, initial, allow_none: bool,
                                show_alpha: bool, title: str, on_pick):
        """[신규기능 · 색 선택 UX 단순화] 스와치 클릭 시 무거운 QColorDialog 대신 먼저 이
        그리드 팝업(무채색+기본색 3단 + '다른 색…')을 anchor 아래에 띄운다. '다른 색…'을
        고르면 그 안에서 왼쪽 열(기본색 그리드)만 숨긴 QColorDialog로 폴백한다(선·채움 동일 UI,
        2026-07-31 통일 — 이전엔 채움만 이렇게 하고 선 색은 OS 네이티브 다이얼로그를 그대로 써서
        둘의 인터페이스가 달라 보였다)."""
        pop = _ColorGridPopup(self, initial, allow_none, show_alpha, title, on_pick,
                              recent=self._recent_colors, on_custom_picked=self._remember_recent_color)
        pop.adjustSize()
        pop.move(anchor.mapToGlobal(QPoint(0, anchor.height() + 2)))
        pop.show()
        self._last_color_popup = pop   # 테스트 훅 — 실사용 흐름엔 영향 없음

    def _load_recent_colors(self) -> list[QColor]:
        raw = QSettings("EasyCAD", "EasyCAD").value("recent_colors", [], type=list) or []
        return [QColor(h) for h in raw if QColor(h).isValid()][:_RECENT_COLOR_MAX]

    def _remember_recent_color(self, col: QColor):
        """[신규기능] "다른 색…"에서 고른 색을 그리드 팝업의 "최근 사용한 색" 열에 남긴다
        (그리드 스와치를 직접 클릭한 건 대상 아님 — 이미 항상 보이는 색이라 기억할 필요 없음).
        QSettings에 영구 저장(다크모드 설정과 같은 관례) — 앱을 재시작해도 유지된다."""
        col = QColor(col)
        key = col.name(QColor.NameFormat.HexArgb)
        self._recent_colors = [c for c in self._recent_colors
                               if c.name(QColor.NameFormat.HexArgb) != key]
        self._recent_colors.insert(0, col)
        self._recent_colors = self._recent_colors[:_RECENT_COLOR_MAX]
        QSettings("EasyCAD", "EasyCAD").setValue(
            "recent_colors", [c.name(QColor.NameFormat.HexArgb) for c in self._recent_colors])

    def _edit_color(self):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "apply_color")]
        if not sel:
            return
        init = self._read_props(sel[0])["color"] or QColor("#000000")
        anchor = self.sender() if isinstance(self.sender(), QWidget) else self._pf_color

        def on_pick(col):
            if col is None:   # 선 색은 "없음" 미지원 — 팝업이 allow_none=False라 실제로 안 옴
                return
            self._edit_items(sel, lambda it: it.apply_color(QColor(col)))
            self._set_current_color(col)   # [M2 #A] 다음 도형 기본 색으로(sticky)

        self._show_color_grid_popup(anchor, init, False, False, "색 선택", on_pick)

    def _edit_fill(self):
        """[신규기능] 채움색 선택 — 스와치 클릭. 그리드 팝업의 "다른 색…"은 알파 채널 허용
        (반투명 채움, .ecad가 이미 HexArgb로 왕복 지원 — document.py 무변경)."""
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "apply_fill")]
        if not sel:
            return
        init = self._read_props(sel[0])["fill"] or QColor("#ffffff")

        def on_pick(col):
            if col is None:
                self._clear_fill()
                return
            self._edit_items(sel, lambda it: it.apply_fill(QColor(col)))
            self.current_fill = QColor(col)   # sticky

        self._show_color_grid_popup(self._pf_fill, init, True, True, "채움색 선택", on_pick)

    def _clear_fill(self):
        """채움을 투명으로(None) — 그리드 팝업의 "없음" 항목이 호출(요청③: 별도 외부 버튼
        대신 팝업 안 항목)."""
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "apply_fill")]
        if not sel:
            return
        self._edit_items(sel, lambda it: it.apply_fill(None))
        self.current_fill = None

    def _edit_width(self, val):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "apply_width")]
        self._edit_items(sel, lambda it: it.apply_width(float(val)),
                         key=("width", tuple(sorted(id(it) for it in sel))))
        if sel:
            self.current_width = float(val)   # [M2 #A] 다음 도형 기본 두께로(sticky)

    def _edit_style(self, _idx):
        style = self._pf_style.currentData()
        # [M2 #3] pen 기반 도형 + 화살표(apply_style) 모두 대상.
        sel = [it for it in self._scene.selectedItems()
               if hasattr(it, "pen") or hasattr(it, "apply_style")]
        def apply(it):
            if hasattr(it, "apply_style"):   # 화살표(_ArrowItem/_PolyArrowItem)
                it.apply_style(style)
            else:
                p = it.pen(); p.setStyle(style); it.setPen(p)
        self._edit_items(sel, apply)
        if sel and style is not None:
            self.current_style = style   # [M2 #A] 다음 도형 기본 선스타일로(sticky)

    def _edit_font(self, val):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "apply_font_size")]
        self._edit_items(sel, lambda it: it.apply_font_size(int(val)),
                         key=("font", tuple(sorted(id(it) for it in sel))))

    @staticmethod
    def _read_props(item) -> dict:
        """아이템의 색·두께·선스타일·폰트를 duck-typing으로 읽는다(화살표=_color/_width,
        도형=pen(), 텍스트=font()). 없는 값은 None."""
        col = getattr(item, "_color", None)
        if col is None and hasattr(item, "pen"):
            try: col = item.pen().color()
            except Exception: col = None
        width = getattr(item, "_width", None)
        if width is None and hasattr(item, "pen"):
            try: width = item.pen().widthF()
            except Exception: width = None
        style = getattr(item, "_style", None)   # [M2 #3] 화살표 몸통 선스타일
        if style is None and hasattr(item, "pen"):
            try: style = item.pen().style()
            except Exception: style = None
        font = None
        if hasattr(item, "font"):
            try:
                fs = item.font().pointSizeF()
                font = fs if fs and fs > 0 else None
            except Exception:
                font = None
        # [신규기능] 채움색 — rect/ellipse/symbol만 지원(apply_fill 존재로 판정). fill=None은
        # "지원하지만 지금 투명"이라 has_fill과 분리해야 한다(color/width처럼 항상 값이 있는
        # 속성과 달리, 채움은 "이 항목이 채움 자체를 지원하는가"를 따로 알아야 함).
        has_fill = hasattr(item, "apply_fill")
        fill = None
        if has_fill:
            try:
                fill = (QColor(item.brush().color())
                       if item.brush().style() != Qt.BrushStyle.NoBrush else None)
            except Exception:
                fill = None
        return {
            "type": _TYPE_NAMES.get(type(item).__name__, "객체"),
            "color": QColor(col) if col is not None else None,
            "width": width, "style": style, "font": font,
            "has_fill": has_fill, "fill": fill,
        }

    # ---- 스타일 복사(format painter) — deep-interview 2026-07-28 -------------
    def _capture_paint_style(self, item) -> dict:
        """[스타일 복사] 서식만 캡처(텍스트 '내용'은 제외) — color/width/style/font는
        속성 dock이 이미 쓰는 _read_props(pen 기반↔화살표 정규화)를 그대로 재사용(규칙 2
        손안의 카드), tcolor·bg·head(화살표 방향)만 추가로 얹는다."""
        st = dict(self._read_props(item))
        if hasattr(item, "setDefaultTextColor"):
            st["tcolor"] = QColor(item.defaultTextColor())
        if hasattr(item, "toPlainText"):
            st["bg"] = QColor(item._bg) if getattr(item, "_bg", None) is not None else None
        if hasattr(item, "_head_at_end") and hasattr(item, "set_head_at_end"):
            st["head"] = item._head_at_end
        return st

    def _apply_paint_style(self, item, st: dict):
        """[스타일 복사] 타입이 달라도 항상 적용(deep-interview 확정) — 없는 속성은 조용히
        건너뜀(hasattr 가드). 선스타일은 화살표(apply_style)/pen 기반을 갈라 _edit_style과
        동일하게 처리."""
        if st.get("color") is not None and hasattr(item, "apply_color"):
            item.apply_color(QColor(st["color"]))
        if st.get("width") is not None and hasattr(item, "apply_width"):
            item.apply_width(float(st["width"]))
        if st.get("style") is not None:
            if hasattr(item, "apply_style"):
                item.apply_style(st["style"])
            elif hasattr(item, "pen"):
                p = item.pen(); p.setStyle(st["style"]); item.setPen(p)
        if st.get("font") is not None and hasattr(item, "apply_font_size"):
            item.apply_font_size(int(st["font"]))
        # [신규기능] 채움 — "지원 대상일 때만" 옮긴다(has_fill로 판정). fill 값 자체는 None(투명)도
        # 유효한 서식이라 color/width와 달리 None 체크 없이 그대로 적용.
        if st.get("has_fill") and hasattr(item, "apply_fill"):
            item.apply_fill(st.get("fill"))
        if "tcolor" in st and hasattr(item, "setDefaultTextColor"):
            item.setDefaultTextColor(st["tcolor"])
        if "bg" in st and hasattr(item, "set_bg"):
            item.set_bg(st["bg"])
        if "head" in st and hasattr(item, "set_head_at_end"):
            item.set_head_at_end(st["head"])

    def copy_style_from_selection(self):
        sel = self._scene.selectedItems()
        if len(sel) != 1:
            self.statusBar().showMessage(
                "스타일 복사 — 도형을 하나만 선택하세요" if sel else "스타일 복사 — 먼저 도형을 선택하세요",
                2500)
            return
        self._style_clip = self._capture_paint_style(sel[0])
        self.statusBar().showMessage("스타일 복사됨", 2000)

    def paste_style_to_selection(self):
        st = getattr(self, "_style_clip", None)
        if st is None:
            self.statusBar().showMessage("붙여넣을 스타일이 없습니다 — 먼저 스타일을 복사하세요", 2500)
            return
        sel = self._scene.selectedItems()
        if not sel:
            return
        snaps = [(it, it.capture_state()) for it in sel]
        for it in sel:
            self._apply_paint_style(it, st)
        self.push_undo_state(snaps)
        self.statusBar().showMessage(f"스타일 붙여넣기 — {len(sel)}개", 2000)

    def _swatch_css(self, color: QColor | None) -> str:
        """스와치 버튼 배경 — 단색이면 그 색, 혼합/없음이면 체크무늬 느낌의 중립 표시."""
        if color is None:
            return "background:transparent; border:1px solid #888; border-radius:3px;"
        return (f"background:{color.name()}; border:1px solid #888; border-radius:3px;")

    def _resize_props_panel(self):
        """행 표시가 바뀐 뒤 `_props_panel`을 새 콘텐츠 크기로 맞춘다.
        ⚠ [2026-08-01] `_props_form.activate()` 하나만으론 세로 길이가 가끔 줄지 않고 이전
        선택(예: 화살표 9행)의 큰 크기로 눌어붙는 경우가 있었다(실측: offscreen에서 재현 —
        `_props_form`은 `content` 위젯의 레이아웃이고, `content`는 `_props_panel._body`의
        `_body_layout` 안에, 그 `_body`는 다시 `_props_panel` 자신의 최상위 레이아웃 안에
        중첩돼 있는데, `setRowVisible()`이 만드는 크기변경 통지가 이 조상 레이아웃들에게는
        Qt 이벤트루프가 처리하는 지연 포스트 이벤트로만 전달돼, 같은 시그널 핸들러 안에서
        즉시 `adjustSize()`를 부르면 조상 레이아웃의 캐시가 아직 옛 값 그대로일 수 있었다).
        중첩된 각 레이아웃을 안쪽부터 바깥쪽까지 전부 명시적으로 `activate()`해 이벤트루프
        타이밍과 무관하게 항상 최신 크기로 즉시 반영한다."""
        self._props_form.activate()
        self._props_panel._body.layout().activate()
        self._props_panel.layout().activate()
        self._props_panel.adjustSize()

    def _refresh_properties(self):
        """선택에 맞춰 편집 컨트롤 값·활성 상태를 채운다. _pf_updating로 편집 시그널을 막아
        프로그램적 세팅이 다시 편집 핸들러를 트리거하지 않게 한다(피드백 차단)."""
        self._pf_updating = True
        try:
            sel = self._scene.selectedItems()
            has = bool(sel)
            for w in (self._pf_color, self._pf_width, self._pf_style, self._pf_font):
                w.setEnabled(has)
            if not has:
                self._pf_type.setText("—")
                self._pf_color_val.setText("—")
                self._pf_color.setStyleSheet(self._swatch_css(None))
                self._pf_fill.setEnabled(False)
                self._pf_fill_val.setText("—")
                self._pf_fill.setStyleSheet(self._swatch_css(None))
                self._pf_hint.setText("객체를 선택하면 속성을 편집할 수 있습니다.")
                for w in (self._pf_swap_btn, self._pf_routing_btn, self._pf_radius, self._pf_dir_btn):
                    self._props_form.setRowVisible(w, False)
                # 아래 "선택 있음" 분기와 동일 — 행을 숨긴 뒤 패널을 그 크기로 다시 줄이지
                # 않으면, 직전에 화살표 등 확장 행이 있던 선택에서 커진 패널 크기가 선택
                # 해제 후에도 그대로 남아 빈 공간만 길게 남는다.
                self._resize_props_panel()
                self._reposition_panels()
                return
            props = [self._read_props(it) for it in sel]
            types = {p["type"] for p in props}
            self._pf_type.setText(next(iter(types)) if len(types) == 1
                                  else f"{len(sel)}개 · 혼합")
            self._pf_hint.setText("")

            # 색 — 스와치 + hex(혼합이면 표시만).
            cols = [p["color"] for p in props if p["color"] is not None]
            uniform = cols and len(cols) == len(props) and len({c.name() for c in cols}) == 1
            self._pf_color.setEnabled(bool(cols))
            self._pf_color.setStyleSheet(self._swatch_css(cols[0] if uniform else None))
            self._pf_color_val.setText(cols[0].name() if uniform
                                       else ("혼합" if cols else "—"))

            # [신규기능] 채움 — 지원 대상(has_fill)에서만 균일성 판정. None(투명)도 유효한 값이라
            # color처럼 "값 있는 것만 필터"하면 안 되고, has_fill인 항목 전부를 모아야 한다.
            fillable = [p["fill"] for p in props if p["has_fill"]]
            has_fillable = bool(fillable)
            self._pf_fill.setEnabled(has_fillable)
            if has_fillable:
                names = {(f.name(QColor.NameFormat.HexArgb) if f is not None else None)
                        for f in fillable}
                uniform_fill = len(names) == 1
                cur = fillable[0] if uniform_fill else None
                self._pf_fill.setStyleSheet(self._swatch_css(cur))
                if not uniform_fill:
                    self._pf_fill_val.setText("혼합")
                elif cur is None:
                    self._pf_fill_val.setText("없음")
                else:
                    self._pf_fill_val.setText(cur.name())
            else:
                self._pf_fill.setStyleSheet(self._swatch_css(None))
                self._pf_fill_val.setText("—")

            # 두께 — 균일하면 값, 아니면 대상 있음만 활성(값은 첫 대상).
            widths = [p["width"] for p in props if p["width"] is not None]
            self._pf_width.setEnabled(bool(widths))
            if widths:
                self._pf_width.setValue(widths[0])

            # 선스타일 — pen 기반만. 대상 없으면 비활성.
            styles = [p["style"] for p in props if p["style"] is not None]
            self._pf_style.setEnabled(bool(styles))
            if styles:
                i = self._pf_style.findData(styles[0])
                self._pf_style.setCurrentIndex(i if i >= 0 else 0)

            # 폰트 — 텍스트/라벨만.
            fonts = [p["font"] for p in props if p["font"] is not None]
            self._pf_font.setEnabled(bool(fonts))
            if fonts:
                self._pf_font.setValue(int(round(fonts[0])))

            # [미니패널 통합] 타입 전용 행 노출 — 옛 _reposition_floating_toolbar의 판정을 그대로.
            show_swap = len(sel) == 1 and isinstance(sel[0], (_RectItem, _EllipseItem, _SymbolItem))
            show_routing = len(sel) == 1 and isinstance(sel[0], (_ArrowItem, _PolyArrowItem))
            show_dir = any(isinstance(it, (_ArrowItem, _PolyArrowItem)) for it in sel)
            curved = (len(sel) == 1 and isinstance(sel[0], _PolyArrowItem) and sel[0]._is_ortho())
            self._props_form.setRowVisible(self._pf_swap_btn, show_swap)
            self._props_form.setRowVisible(self._pf_routing_btn, show_routing)
            self._props_form.setRowVisible(self._pf_radius, curved)
            self._props_form.setRowVisible(self._pf_dir_btn, show_dir)
            # ⚠ [2026-07-31, 진짜 원인 확정 — 실기기에서 직접 반복 재현해 확인] 선택 종류가
            # 바뀌어 행 개수가 달라져도(예: 네모 7행 → 화살표 9행) `_props_panel` 위젯 자체의
            # 크기(`adjustSize()`로만 커짐)는 창 리사이즈 때만 호출되는 `_reposition_panels()`
            # 에서만 갱신됐다 — `_refresh_properties()`는 행 노출만 토글하고 패널을 그 새 크기에
            # 맞게 키우질 않아, 늘어난 행들이 옛 크기의 좁은 패널 안에 짓눌려 들어갔다(실측:
            # 네모 선택 시 두께 행 21px, 화살표 선택 시 13px인데 패널 size()는 두 경우 완전히
            # 동일 — 창을 리사이즈하면 그제야 `_reposition_panels()`가 불려 패널이 커지고
            # 그 뒤로 유지되는 것과 정확히 일치). [2026-08-01 갱신] 이 호출은 `_resize_props_panel()`
            # 로 옮겼다 — 축소 방향(화살표→선택해제)에선 `_props_form.activate()`만으론 조상
            # 레이아웃(`_body_layout`·패널 자체 레이아웃) 캐시가 안 갱신돼 큰 크기에 눌어붙는
            # 별도 버그가 있었다(상세는 `_resize_props_panel` docstring).
            self._resize_props_panel()
            self._reposition_panels()
            if curved:
                self._pf_radius.blockSignals(True)   # 값 동기화가 편집 신호로 되돌아오지 않게
                self._pf_radius.setValue(int(round(sel[0]._curve_r)))
                self._pf_radius.blockSignals(False)
        finally:
            self._pf_updating = False

    # ---- 지속 연결 리라우트 -------------------------------------------------
    def _on_scene_changed(self, region):
        """[성능 조사 2026-07-30] scene.changed가 넘겨주는 region(실제 변경 영역)을 무시하고
        씬의 모든 바인딩 화살표를 매번 전부 reroute하던 게 다중선택 드래그 버벅임의 핵심
        원인이었다(cProfile 실측: 박스 40+화살표 39짜리 작은 씬에서도 15프레임에 reroute 자체
        69ms). region과 화살표 자신의 (여유 있는) bbox가 겹칠 때만 reroute — 바인딩 도형이
        움직인 경우든, 무관한 장애물이 경로 근처로 들어와 A* 회피를 재트리거해야 하는 경우든
        둘 다 화살표 자신의 bbox 기준으로 커버된다(바인딩 도형만 보면 장애물-회피 케이스를 놓침).
        region=None은 필터 없이 전부 재검토(테스트 등에서 실제 시그널 없이 강제 호출할 때 쓰는
        기존 관례 — 실제 scene.changed 시그널은 항상 리스트를 준다)."""
        if self._rerouting:
            return  # 재진입 가드 — reroute가 유발한 changed로 되돌아오지 않게
        if getattr(self._view, "_drawing", False):
            return  # 화살표 그리는 중엔 _update_arrow_draw가 tip을 주도 — 간섭 방지
        if getattr(self._view, "_place", None) is not None:
            return  # 클릭 배치 중엔 배치 로직이 끝점을 주도 — 간섭 방지
        if region is None:
            union = None
        else:
            union = QRectF()
            for r in region:
                union = union.united(r)
            if union.isEmpty():
                return
        margin = _PolyArrowItem._ROUTE_CLEARANCE  # 기존 장애물-회피 여유와 동일 감도로 재사용
        self._rerouting = True
        try:
            for it in self._scene.items():
                # 곡선화살표(_ArrowItem)·직선화살표(_PolyArrowItem) 모두 지속 연결 리라우트.
                if isinstance(it, (_ArrowItem, _PolyArrowItem)) and it.has_binding():
                    if union is None or it.sceneBoundingRect().adjusted(
                            -margin, -margin, margin, margin).intersects(union):
                        it.reroute(pin_pred=self._make_pin_pred(it))
        finally:
            self._rerouting = False

    @staticmethod
    def _make_pin_pred(arrow):
        # 끝점 idx를 도형에 재고정할지: 붙은 도형과 화살표가 '같은 선택'으로 함께 움직이면
        # 강체(재고정 안 함), 아니면 붙은 채 늘림. → 사용자 합의 규칙.
        def pred(idx):
            sh = arrow._bound(idx)
            if sh is not None and arrow.isSelected() and sh.isSelected():
                return False
            return True
        return pred

    # ---- owner 인터페이스 ---------------------------------------------------
    def is_edit_mode(self) -> bool:
        return True

    def toggle_edit_mode(self):
        pass  # 단일 모드 앱 — 항상 편집

    def _on_escape(self):
        pass  # Phase 0: ESC로 앱 닫지 않음

    def make_pen(self) -> QPen:
        pen = QPen(QColor(self.current_color))
        pen.setWidthF(float(self.current_width))
        pen.setStyle(self.current_style)   # [M2] sticky 선스타일 반영
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def make_brush(self) -> QBrush:
        """[신규기능] make_pen과 대칭 — 새 도형(rect/ellipse/symbol)의 sticky 채움색.
        기본 None=투명(NoBrush), 지금까지의 동작 불변."""
        if self.current_fill is None:
            return QBrush(Qt.BrushStyle.NoBrush)
        return QBrush(QColor(self.current_fill))

    def set_tool(self, key):
        # 도구를 바꾸면 진행 중이던 클릭 배치는 폐기(반쯤 그린 도형이 남지 않게).
        view = getattr(self, "_view", None)
        if view is not None:
            view._cancel_place()
        self.current_tool = key
        for k, b in self._tool_buttons.items():
            # [화살표 통합] 화살표 버튼 1개가 내부 두 도구(arrow·sarrow)를 대표한다.
            b.setChecked(k == key or (k == "arrow" and key == "sarrow"))
        # 왼쪽 「도형」 팔레트 버튼 동기화: 기본(네모·원)은 key 직접, 심볼은 sym:kind.
        for k, b in getattr(self, "_shape_tool_buttons", {}).items():
            b.setChecked(k == key)
        for k, b in getattr(self, "_sym_buttons", {}).items():
            b.setChecked(f"sym:{k}" == key)

    def next_badge_number(self) -> int:
        self._badge_n += 1
        return self._badge_n

    def adjust_item_property(self, item, step: int):
        # [M2] Shift+휠 두께 조절도 저널에 실어 되돌릴 수 있게 한다(이전엔 미추적).
        # 연속 굴림은 (아이템별) coalesce_key로 undo 1스텝에 병합.
        before = item.capture_state()
        if isinstance(item, (_ArrowItem, _PolyArrowItem)):
            new_w = max(1, item._width + step)
            item.apply_width(new_w)
        elif hasattr(item, "pen"):
            new_w = max(1.0, item.pen().widthF() + step)
            item.apply_width(new_w)
        else:
            return
        self.push_undo_state([(item, before)], coalesce_key=("width", id(item)))
        self.current_width = float(new_w)   # [M2 #A] 바꾼 두께를 다음 도형 기본값으로(sticky)
        self._refresh_properties()          # [M2 #3] 속성 패널 값 실시간 반영

    # 줌 (커서 기준 — 뷰가 AnchorUnderMouse)
    def _on_wheel_zoom(self, dy: int):
        factor = 1.15 if dy > 0 else 1.0 / 1.15
        self._view.scale(factor, factor)
        self._update_zoom_label()
        self._refresh_minimap()

    # 팬 (창 이동 대신 캔버스 스크롤)
    def _win_drag_start(self, gpos):
        self._pan_last = gpos

    def _win_drag_move(self, gpos):
        if self._pan_last is None:
            return
        delta = gpos - self._pan_last
        self._pan_last = gpos
        hs, vs = self._view.horizontalScrollBar(), self._view.verticalScrollBar()
        hs.setValue(hs.value() - delta.x())
        vs.setValue(vs.value() - delta.y())

    def _win_drag_end(self):
        self._pan_last = None

    # ---- 되돌리기 / 다시 실행 — 단일 스냅샷 저널(create/remove/mut 3-op) -------
    # [Phase 6 M2] 기존 add/delete/move/xform/geom 5종을 _UndoEntry 하나로 흡수하고
    # redo를 대칭으로 얻는다. push_undo_* 시그니처는 하위호환 유지(호출부 무변경) —
    # 내부에서 저널 엔트리로 변환한다. 각 mut op는 before/after 스냅샷을 함께 담아
    # undo=before·redo=after로 동일 로직에서 복원된다.
    def _push_entry(self, ops, key=None):
        """ops(연산 리스트)를 저널에 쌓는다. key가 직전 엔트리와 같으면 병합(연속 변이).
        새 변이가 실리면 redo 스택은 무효화된다(표준 undo 시맨틱)."""
        if not ops:
            return
        top = self._undo[-1] if self._undo else None
        if key is not None and top is not None and top.key == key:
            self._coalesce_into(top, ops)   # before 유지, after만 갱신
        else:
            self._undo.append(_UndoEntry(ops, key))
        self._redo.clear()
        self._refresh_history_actions()

    @staticmethod
    def _coalesce_into(entry, new_ops):
        """연속 변이 병합 — 같은 아이템·같은 sub의 mut는 before를 유지한 채 after만 갱신
        (예: Shift+휠 두께를 여러 번 굴려도 undo 1스텝). 그 외 op는 뒤에 덧붙인다."""
        index = {(id(o[1]), o[2]): i for i, o in enumerate(entry.ops)
                 if o[0] == "mut"}
        for o in new_ops:
            if o[0] == "mut" and (id(o[1]), o[2]) in index:
                i = index[(id(o[1]), o[2])]
                prev = entry.ops[i]
                entry.ops[i] = ("mut", o[1], o[2], prev[3], o[4])  # before 유지·after 갱신
            else:
                entry.ops.append(o)

    def push_undo_add(self, item):
        self._push_entry([("create", item)])
        self._maybe_oneshot_revert()

    def push_undo_add_many(self, items):
        """[2d] 여러 아이템(복제 도형+연결 화살표)을 한 번의 undo로 함께 제거."""
        self._push_entry([("create", it) for it in items])
        self._maybe_oneshot_revert()

    def _maybe_oneshot_revert(self):
        """[M2] 도형을 하나 커밋한 뒤 — pin이 꺼져 있고 지금 도구가 one-shot 대상이면
        선택모드로 되돌린다(그린 뒤 또 그려지는 오작동 차단). 진행 중 이벤트가 끝난 뒤
        적용하도록 singleShot(0)로 지연(현재 그리기 핸들러가 도구를 더 참조할 수 있으므로).
        붙여넣기·복제·빠른생성은 select 모드에서 일어나 여기 걸리지 않는다(가드)."""
        tool = self.current_tool
        armed = tool in _ONESHOT_TOOLS or (tool or "").startswith("sym:")
        if armed and not self.tool_pinned:
            QTimer.singleShot(0, lambda: self.set_tool("select"))

    def push_undo_delete(self, items):
        self._push_entry([("remove", it) for it in items])

    def push_undo_move(self, pairs, coalesce_key=None):
        self._push_entry(
            [("mut", it, "pos", QPointF(old), QPointF(it.pos())) for it, old in pairs],
            key=coalesce_key)

    def push_undo_xform(self, snaps):
        """[우리 확장] 그룹 변형(회전·스케일) 되돌리기 — 변형 전 pos/rotation/scale/origin 스냅샷.
        push_undo_move가 위치만 복원하는 것과 달리 회전·스케일까지 통째로 되돌린다."""
        self._push_entry([
            ("mut", it, "xform", (QPointF(pos), rot, scale, QPointF(org)),
             (QPointF(it.pos()), it.rotation(), it.scale(),
              QPointF(it.transformOriginPoint())))
            for it, pos, rot, scale, org in snaps])

    def push_undo_geom(self, snaps, coalesce_key=None):
        """[Stage2] 기하 리베이크(비균일 스케일·미러) 되돌리기 — capture_geom 토큰 스냅샷.
        xform과 달리 기하 자체(rect/끝점/정점/패스)+바인딩까지 통째로 복원한다.
        coalesce_key가 있으면 연속 조작(반경 스테퍼 등)을 undo 1스텝으로 병합한다."""
        self._push_entry([
            ("mut", it, "geom", before, it.capture_geom()) for it, before in snaps],
            key=coalesce_key)

    def push_undo_state(self, snaps, coalesce_key=None):
        """[M2] 속성·라벨 변경(색·두께·선스타일·폰트·텍스트) — before=capture_state 스냅샷
        (변경 전), after=현재. 저널의 'state' mut로 실려 되돌리기/다시 실행된다."""
        self._push_entry(
            [("mut", it, "state", before, it.capture_state()) for it, before in snaps],
            key=coalesce_key)

    def _apply_mut(self, it, sub, tok):
        """mut op의 sub별 복원 — undo는 before, redo는 after 토큰을 그대로 넘긴다."""
        if sub == "pos":
            it.setPos(tok)
        elif sub == "xform":
            pos, rot, scale, org = tok
            it.setTransformOriginPoint(org)
            it.setRotation(rot)
            it.setScale(scale)
            it.setPos(pos)
        elif sub == "geom":
            # 기하+바인딩 통째 복원 — apply_geom만으로 일관 복원(reroute 불필요).
            it.apply_geom(tok)
        elif sub == "state":
            it.apply_state(tok)
        elif sub == "z":
            it.setZValue(tok)
        elif sub == "group":
            it._group_id = tok
        elif sub == "lock":
            self._set_item_lock_flags(it, tok)
        elif sub == "layer":
            it._layer_id = tok
            self._sync_item_to_layer_state(it)   # undo/redo도 옮긴 레이어의 표시/잠금을 물려받음
            if hasattr(self, "_layers_list"):
                self._refresh_layers_panel()

    def _apply_entry(self, entry, redo):
        for op in entry.ops:
            kind = op[0]
            if kind == "create":
                it = op[1]
                if redo:
                    if it.scene() is None:
                        self._scene.addItem(it)
                elif it.scene() is not None:
                    self._scene.removeItem(it)
            elif kind == "remove":
                it = op[1]
                if redo:
                    if it.scene() is not None:
                        self._scene.removeItem(it)
                elif it.scene() is None:
                    self._scene.addItem(it)
            elif kind == "mut":
                _, it, sub, before, after = op
                self._apply_mut(it, sub, after if redo else before)

    def undo(self):
        if not self._undo:
            return
        entry = self._undo.pop()
        self._apply_entry(entry, redo=False)
        self._redo.append(entry)
        self._refresh_history_actions()
        self._repaint_overlays()   # 되돌리기도 프로그램 이동 — 그룹 박스 잔상 방지

    def redo(self):
        if not self._redo:
            return
        entry = self._redo.pop()
        self._apply_entry(entry, redo=True)
        self._undo.append(entry)
        self._refresh_history_actions()
        self._repaint_overlays()   # 다시 실행도 마찬가지

    def _refresh_history_actions(self):
        """undo/redo 툴바 액션의 활성 상태를 스택 유무에 맞춘다(빈 스택=disabled)."""
        act_u = getattr(self, "_act_undo", None)
        act_r = getattr(self, "_act_redo", None)
        if act_u is not None:
            act_u.setEnabled(bool(self._undo))
        if act_r is not None:
            act_r.setEnabled(bool(self._redo))

    # 복사 / 연속 붙여넣기
    def copy_selection(self):
        sel = [it for it in self._scene.selectedItems() if hasattr(it, "clone")]
        self._clip_src = sel               # 원본 참조 보관 — paste 시 배치내 바인딩 재연결용
        self._clip = [it.clone() for it in sel]
        self._paste_seq = 0

    def paste_selection(self):
        if not self._clip:
            self._paste_clipboard_image()   # [신규기능] 내부 버퍼가 비면 시스템 클립보드 이미지로 폴백
            return
        self._paste_seq += 1
        off = 20.0 * self._paste_seq
        self._scene.clearSelection()
        new_items = []
        for tmpl in self._clip:
            c = tmpl.clone()
            c.moveBy(off, off)
            self._scene.addItem(c)
            c.setSelected(True)
            new_items.append(c)
        # clone()이 _bind1/_bind2 등을 원본 그대로 복사해 왔으므로(clip 세대를 거쳐도 불변),
        # 같이 복사된 도형끼리는 여기서 사본으로 재연결한다(배치 밖 도형 바인딩은 그대로 유지).
        remap_grouped_bindings(zip(self._clip_src, new_items))
        regroup_duplicated_items(zip(self._clip_src, new_items))   # 그룹째 복사 시 사본도 새 그룹으로
        if new_items:
            self.push_undo_add_many(new_items)

    # [신규기능] 클립보드 이미지 붙여넣기 — Ctrl+V 하나 공유. 내부 붙여넣기 버퍼(copy_selection)가
    # 있으면 항상 그쪽이 우선(기존 동작 불변, 위 paste_selection 분기), 버퍼가 비어 있을 때만
    # 시스템 클립보드의 이미지(스크린샷·다른 앱에서 복사한 그림)를 뷰 중앙에 삽입한다.
    def _paste_clipboard_image(self):
        pm = _clipboard_pixmap()
        if pm is None or pm.isNull():
            return
        center = self._view.mapToScene(self._view.viewport().rect().center())
        self._insert_pixmap_at(pm, center, f"클립보드 이미지 붙여넣기: {pm.width()}×{pm.height()}px")

    # [M2 #3] Ctrl+D 제자리 복제 — 클립보드를 건드리지 않고 선택 객체를 오프셋해 복제.
    # paste_selection과 동형이나 clip/paste_seq와 독립(복사 버퍼 오염 없음).
    def duplicate_selection(self):
        src = [it for it in self._scene.selectedItems() if hasattr(it, "clone")]
        if not src:
            return
        self._scene.clearSelection()
        new_items = []
        for it in src:
            c = it.clone()
            c.moveBy(20.0, 20.0)
            self._scene.addItem(c)
            c.setSelected(True)
            new_items.append(c)
        remap_grouped_bindings(zip(src, new_items))
        regroup_duplicated_items(zip(src, new_items))   # 그룹째 복제 시 사본도 새 그룹으로
        if new_items:
            self.push_undo_add_many(new_items)

    # [Phase 6 M3 #16] 우클릭 컨텍스트 메뉴 — 유휴 우클릭 탭 시 뷰가 호출.
    def delete_selection(self):
        """선택 객체 삭제 + undo. 뷰의 Del 키 핸들러와 동일 동작(메뉴 재사용용)."""
        sel = list(self._scene.selectedItems())
        if not sel:
            return
        for it in sel:
            self._scene.removeItem(it)
        self.push_undo_delete(sel)

    def select_all(self):
        for it in self._scene.items():
            if it.flags() & it.GraphicsItemFlag.ItemIsSelectable:
                it.setSelected(True)

    def _cut_selection(self):
        self.copy_selection()
        self.delete_selection()

    # ---- [편의기능] Z-order / 그룹 / 잠금 — 공용 대상 헬퍼 --------------------
    def _zorder_pool(self):
        """Z-order·그룹·잠금 후보 전체 — 배경·용지틀 제외한 최상위 아이템."""
        bg = getattr(self, "_bg_item", None)
        return [it for it in self._scene.items()
                if it.parentItem() is None and it is not bg
                and not isinstance(it, _TitleBlockItem)]

    def _edit_targets(self):
        """위 후보 중 현재 선택된 것만."""
        pool_ids = {id(it) for it in self._zorder_pool()}
        return [it for it in self._scene.selectedItems() if id(it) in pool_ids]

    # ---- [편의기능] Z-order(맨 앞으로/맨 뒤로 보내기) --------------------------
    def bring_to_front(self):
        sel = self._edit_targets()
        if not sel:
            return
        top_z = max((it.zValue() for it in self._zorder_pool()), default=0.0)
        snaps = [(it, it.zValue()) for it in sel]
        for i, it in enumerate(sorted(sel, key=lambda x: x.zValue())):
            it.setZValue(top_z + 1.0 + i)
        self._push_entry([("mut", it, "z", old, it.zValue()) for it, old in snaps])

    def send_to_back(self):
        sel = self._edit_targets()
        if not sel:
            return
        bottom_z = min((it.zValue() for it in self._zorder_pool()), default=0.0)
        snaps = [(it, it.zValue()) for it in sel]
        for i, it in enumerate(sorted(sel, key=lambda x: -x.zValue())):
            it.setZValue(bottom_z - 1.0 - i)
        self._push_entry([("mut", it, "z", old, it.zValue()) for it, old in snaps])

    # ---- [편의기능] Group / Ungroup --------------------------------------
    def _sync_group_selection(self):
        """그룹 멤버 하나가 선택되면 같은 그룹 전체를 함께 선택(재진입 가드로 무한루프 방지)."""
        if self._group_sync_active:
            return
        sel = self._scene.selectedItems()
        gids = {getattr(it, "_group_id", None) for it in sel} - {None}
        if not gids:
            return
        missing = [it for it in self._zorder_pool()
                   if getattr(it, "_group_id", None) in gids and not it.isSelected()]
        if not missing:
            return
        self._group_sync_active = True
        try:
            for it in missing:
                it.setSelected(True)
        finally:
            self._group_sync_active = False

    def group_selection(self):
        sel = self._edit_targets()
        if len(sel) < 2:
            return
        gid = uuid.uuid4().hex[:8]
        snaps = [(it, getattr(it, "_group_id", None)) for it in sel]
        for it in sel:
            it._group_id = gid
        self._push_entry([("mut", it, "group", old, gid) for it, old in snaps])
        self.statusBar().showMessage(f"그룹 지정: {len(sel)}개 객체", 3000)

    def ungroup_selection(self):
        sel = self._edit_targets()
        gids = {it._group_id for it in sel if getattr(it, "_group_id", None)}
        if not gids:
            return
        members = [it for it in self._zorder_pool() if getattr(it, "_group_id", None) in gids]
        snaps = [(it, it._group_id) for it in members]
        for it in members:
            it._group_id = None
        self._push_entry([("mut", it, "group", old, None) for it, old in snaps])
        self.statusBar().showMessage(f"그룹 해제: {len(members)}개 객체", 3000)

    # ---- [편의기능] 객체 잠금 ---------------------------------------------
    def _set_item_lock_flags(self, it, locked: bool):
        """잠금 = ItemIsMovable·ItemIsSelectable을 직접 꺼서 Qt가 클릭·드래그·러버밴드를
        전부 자연히 걸러내게 한다(각 이벤트 핸들러에 별도 잠금 체크를 심을 필요가 없음)."""
        it._locked = locked
        it.setFlag(it.GraphicsItemFlag.ItemIsMovable, not locked)
        it.setFlag(it.GraphicsItemFlag.ItemIsSelectable, not locked)
        if locked:
            it.setSelected(False)

    def toggle_lock_selection(self):
        """선택 중 하나라도 미잠금이면 전부 잠금, 전부 이미 잠겼으면 전부 해제(공통 토글 UX)."""
        sel = self._edit_targets()
        if not sel:
            return
        lock_to = any(not getattr(it, "_locked", False) for it in sel)
        snaps = [(it, getattr(it, "_locked", False)) for it in sel]
        for it in sel:
            self._set_item_lock_flags(it, lock_to)
        self._push_entry([("mut", it, "lock", old, lock_to) for it, old in snaps])

    def unlock_all(self):
        """잠긴 객체는 선택이 안 돼 개별 우클릭으로 못 푸므로, 빈 영역 메뉴에 두는 탈출구."""
        locked = [it for it in self._zorder_pool() if getattr(it, "_locked", False)]
        if not locked:
            return
        snaps = [(it, True) for it in locked]
        for it in locked:
            self._set_item_lock_flags(it, False)
        self._push_entry([("mut", it, "lock", old, False) for it, old in snaps])

    def _build_context_menu(self):
        """[M3 #16] 유휴 우클릭 탭 메뉴 구성 — 선택/클립보드 유무로 항목을 정한다.
        전부 기존 편집 경로(copy/paste/duplicate/delete/select_all)를 재사용해 undo 일관.
        exec는 _show_context_menu가 하고, 이 메서드는 구성만(스모크 테스트용 분리)."""
        menu = QMenu(self)
        sel = self._scene.selectedItems()
        has_sel = bool(sel)
        has_clip = bool(getattr(self, "_clip", None))
        if has_sel:
            menu.addAction("복사\tCtrl+C", self.copy_selection)
            menu.addAction("잘라내기", self._cut_selection)
            menu.addAction("복제\tCtrl+D", self.duplicate_selection)
            menu.addAction("삭제\tDel", self.delete_selection)
        # [신규기능 · 스타일 복사] 단일 선택=복사 진입점, 스타일 클립 있으면=붙여넣기 진입점.
        has_style_clip = getattr(self, "_style_clip", None) is not None
        if len(sel) == 1 or has_style_clip:
            menu.addSeparator()
            if len(sel) == 1:
                menu.addAction("스타일 복사\tCtrl+Alt+C", self.copy_style_from_selection)
            if has_sel and has_style_clip:
                menu.addAction("스타일 붙여넣기\tCtrl+Alt+V", self.paste_style_to_selection)
        if len(self._align_targets()) >= 2:      # [M5] 여럿 선택 시만 정렬/분배 서브메뉴
            menu.addSeparator()
            menu.addMenu(self._build_align_menu("정렬 / 분배", parent=menu))
        if len(self._arrow_targets()) >= 1:      # [신규기능] 화살표 선택 시만 채번 진입점
            menu.addSeparator()
            menu.addAction("케이블 번호 매기기...", self._prompt_cable_numbers)
        targets = self._edit_targets()           # [편의기능] Z-order/그룹/잠금 대상
        if targets:
            menu.addSeparator()
            menu.addAction("맨 앞으로 보내기\tCtrl+]", self.bring_to_front)
            menu.addAction("맨 뒤로 보내기\tCtrl+[", self.send_to_back)
            menu.addAction("잠금 전환\tCtrl+L", self.toggle_lock_selection)
            if len(targets) >= 2:
                menu.addAction("그룹\tCtrl+G", self.group_selection)
            if any(getattr(it, "_group_id", None) for it in targets):
                menu.addAction("그룹 해제\tCtrl+Shift+G", self.ungroup_selection)
            menu.addMenu(self._build_layer_menu("레이어로 이동", parent=menu))  # [신규기능]
        if has_clip:
            if has_sel:
                menu.addSeparator()
            menu.addAction("붙여넣기\tCtrl+V", self.paste_selection)
        if not has_sel:
            if has_clip:
                menu.addSeparator()
            menu.addAction("전체 선택\tCtrl+A", self.select_all)
            if any(getattr(it, "_locked", False) for it in self._zorder_pool()):
                menu.addAction("잠금 해제 (전체)", self.unlock_all)
        return menu if not menu.isEmpty() else None

    def _show_context_menu(self, global_pos):
        menu = self._build_context_menu()
        if menu is not None:
            menu.exec(global_pos)

    # ---- [Phase 6 M3 #15] 플로팅 컨텍스트 툴바 ------------------------------
    # [미니패널 통합, 2026-07-31] 선택 위를 따라다니던 플로팅 컨텍스트 툴바를 폐지 — 색·선스타일은
    # 속성 dock과 중복이었고 도형바꾸기·화살표종류·곡선반경·방향뒤집기 4개는 dock 폼에 행으로
    # 이관(`_build_properties_panel`). 아래는 그 핸들러들(로직 변경 없이 재사용).
    def _floating_flip_arrows(self):
        arrows = [it for it in self._scene.selectedItems()
                  if isinstance(it, (_ArrowItem, _PolyArrowItem))]
        if not arrows:
            return
        self._edit_items(arrows, lambda it: it.flip_head())

    def _build_routing_menu(self):
        """[화살표 통합] 화살표 종류 메뉴 — 직선·곡선·직각. 상단 툴바가 아니라 여기서 종류를
        고른다(선택 후 컨텍스트). 세 항목 모두 누르는 즉시 눈에 보이는 변화가 있어야 한다."""
        m = QMenu(self)
        for kind, label in _ARROW_KIND_LABELS:
            m.addAction(label, lambda k=kind: self._floating_set_arrow_kind(k))
        return m

    def _floating_set_arrow_kind(self, kind):
        """[화살표 통합] 선택된 화살표를 kind로 바꾼다. 직선↔곡선은 같은 객체의 상태 변경이라
        곡률을 기억하고, ↔직각은 클래스 교체(_swap_arrow)라 곡률·경유힌트가 초기화된다
        (되돌리기로 복구). 고른 종류는 sticky — 다음에 그릴 화살표의 기본이 된다."""
        sel = [it for it in self._scene.selectedItems()
               if isinstance(it, (_ArrowItem, _PolyArrowItem))]
        self.current_arrow_kind = kind
        self._refresh_arrow_tool_button()
        # [화살표 통합 · 핀 버그] 화살표 도구가 이미 무장 중(핀)이면 종류 변경을 무장에도 반영한다.
        # 안 그러면 곡선(arrow)으로 무장된 채 종류만 직각으로 바꿔 다음 화살표가 옛 도구로 그려진다.
        # 핀이 꺼져 있으면 그리기 후 선택모드로 빠져 다음 무장 때 arm_arrow_tool이 새 종류를 읽는다.
        want = _ARROW_KIND_TOOL.get(kind, "arrow")
        if self.current_tool in ("arrow", "sarrow") and self.current_tool != want:
            self.set_tool(want)
        for it in list(sel):
            if _arrow_kind_of(it) == kind:
                continue
            if (kind == "ortho") != isinstance(it, _PolyArrowItem):
                self._swap_arrow(it, kind)      # 클래스가 바뀜 — remove+create 단일 엔트리
                continue
            before = it.capture_geom()          # 같은 클래스 — 기하 변경 하나로 충분
            if isinstance(it, _PolyArrowItem):
                it.set_routing("ortho" if kind == "ortho" else "straight")
            elif kind == "straight":
                it.apply_straight()
            else:
                it.apply_curved()
            self.push_undo_geom([(it, before)])
        self._refresh_properties()
        self._view.viewport().update()

    def _make_swapped_arrow(self, item, kind):
        """item과 같은 끝점·색·두께·선스타일·머리방향·라벨·연결을 가진 kind용 새 화살표."""
        is_poly = isinstance(item, _PolyArrowItem)
        p1 = item.mapToScene(item._pts[0] if is_poly else item._p1)
        p2 = item.mapToScene(item._pts[-1] if is_poly else item._p2)
        if kind == "ortho":
            new = _PolyArrowItem(QColor(item._color), item._width, item._head_at_end)
            new._curve_r = float(self.current_curve_r)   # 반경도 sticky
        else:
            new = _ArrowItem(QColor(item._color), item._width, item._head_at_end)
        new._style = item._style
        new.setZValue(item.zValue())
        new.setFlags(new.GraphicsItemFlag.ItemIsMovable | new.GraphicsItemFlag.ItemIsSelectable)
        new.set_points(p1, p2)
        for idx, (sh, pt) in enumerate((
                (item._bind_start, item._bind_start_pt) if is_poly else (item._bind1, item._bind1_pt),
                (item._bind_end, item._bind_end_pt) if is_poly else (item._bind2, item._bind2_pt))):
            if sh is not None and pt is not None:
                new.set_bound(idx, sh, QPointF(pt))
        if item.has_label() and item._label is not None:
            txt = item._label.toPlainText()
            if txt:
                new.ensure_label().setPlainText(txt)
        return new

    def _swap_arrow(self, item, kind):
        """[화살표 통합] 화살표를 다른 클래스로 교체(M4-3 도형 교체와 같은 패턴).
        remove(old)+create(new)를 하나의 undo 엔트리로 묶어 한 번에 되돌린다."""
        new = self._make_swapped_arrow(item, kind)
        was_selected = item.isSelected()
        self._scene.removeItem(item)
        self._scene.addItem(new)
        # ⚠ 라벨 정렬·경로 계산은 씬에 들어간 뒤에 해야 한다(씬 멤버십 가드로 no-op되는 함정).
        if kind == "ortho":
            new._auto_route = True
            new._apply_routing()
        elif kind == "curved":
            new.apply_curved()
        new._sync_label()
        self._push_entry([("remove", item), ("create", new)])
        if was_selected:
            self._scene.clearSelection()
            new.setSelected(True)
        self._refresh_properties()
        return new

    def _floating_set_radius(self, value: int):
        """[M4-4 ⓑ] 선택된 직각 커넥터의 모서리 각짐(0=완전 직각). 스테퍼 연속 조작은 undo 1스텝으로
        병합한다(스핀박스 화살표를 여러 번 눌러도 되돌리기 한 번). 값 동기화(setValue)는
        blockSignals로 되먹임을 막으므로 여기 오는 건 사용자 조작뿐이다. 바꾼 값은 sticky."""
        sel = [it for it in self._scene.selectedItems() if isinstance(it, _PolyArrowItem)]
        if not sel:
            return
        snaps = [(it, it.capture_geom()) for it in sel]
        for it in sel:
            it.set_corner_radius(value)
        self.current_curve_r = float(value)   # 다음 직각 커넥터의 기본 각짐(sticky)
        self.push_undo_geom(snaps, coalesce_key=("curve_r", id(sel[0])))
        self._view.viewport().update()

    # ---- [Phase 6 M4-3] 도형 바로 바꾸기 -----------------------------------
    def _build_swap_menu(self):
        """도형 교체 대상 메뉴 — 네모·원 + 심볼 14종. 트리거 시 현재 단일 선택 도형을 변환."""
        m = QMenu(self)
        m.addAction("네모", lambda: self._swap_selected("rect"))
        m.addAction("원", lambda: self._swap_selected("ellipse"))
        m.addSeparator()
        for kind, (label, _f) in _SYMBOL_KINDS.items():
            m.addAction(label, lambda k=kind: self._swap_selected(f"sym:{k}"))
        return m

    def _swap_selected(self, target_kind):
        sel = [it for it in self._scene.selectedItems()
               if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]
        if len(sel) == 1:
            self._swap_shape(sel[0], target_kind)

    def _make_swapped(self, item, target_kind):
        """item과 같은 rect·pos·회전·스케일·펜·라벨을 가진 target_kind 새 아이템(연결은 별도 이관)."""
        rect = QRectF(item.rect())
        if target_kind == "rect":
            new = _RectItem(rect)
        elif target_kind == "ellipse":
            new = _EllipseItem(rect)
        elif target_kind.startswith("sym:"):
            new = _SymbolItem(target_kind[4:], rect)
        else:
            return None
        new.setPen(QPen(item.pen()))
        new.setBrush(item.brush())
        new.setTransformOriginPoint(item.transformOriginPoint())
        new.setRotation(item.rotation())
        new.setScale(item.scale())
        new.setPos(item.pos())
        new.setFlags(new.GraphicsItemFlag.ItemIsMovable | new.GraphicsItemFlag.ItemIsSelectable)
        if item.has_label() and item._label is not None:
            txt = item._label.toPlainText()
            if txt:
                new.ensure_label().setPlainText(txt)
                new._sync_label()
        return new

    def _arrows_bound_to(self, item):
        """item에 지속 연결된 화살표 목록 → [(arrow, idx0/1), ...]. 곡선·직선 화살표 모두."""
        out = []
        for it in self._scene.items():
            if isinstance(it, _ArrowItem):
                if it._bind1 is item:
                    out.append((it, 0))
                if it._bind2 is item:
                    out.append((it, 1))
            elif isinstance(it, _PolyArrowItem):
                if it._bind_start is item:
                    out.append((it, 0))
                if it._bind_end is item:
                    out.append((it, 1))
        return out

    def _rebind_arrow(self, arr, idx, new):
        """화살표 끝점(idx)을 new 도형에 다시 바인딩. [M4-3 fix] 옛 도형 테두리 위 좌표를 그대로
        쓰면 원·평행사변형처럼 외곽선이 안쪽으로 든 도형에선 끝점이 떠 버린다 → new의 실제
        외곽선에 투영한 뒤 reroute로 끌어붙인다."""
        if isinstance(arr, _ArrowItem):
            ep = arr._p1 if idx == 0 else arr._p2
        else:
            ep = arr._pts[0] if idx == 0 else arr._pts[-1]
        ep_scene = arr.mapToScene(ep)
        q_scene, _n = _nearest_border(new, ep_scene)   # new 외곽선 최근접점(회전·심볼 슬랜트 반영)
        arr.set_bound(idx, new, new.mapFromScene(q_scene))
        arr.reroute()   # 끝점을 new 외곽선 위로 즉시 이동(뜬 채로 남지 않게)

    def _swap_shape(self, item, target_kind):
        """[M4-3] 도형을 target_kind로 즉석 변환(크기·위치·라벨 유지). 연결 화살표는 new로
        재바인딩. remove(old)+create(new)+화살표 geom 변경을 하나의 undo 엔트리로 묶는다."""
        new = self._make_swapped(item, target_kind)
        if new is None:
            return
        befores = [(arr, idx, arr.capture_geom()) for arr, idx in self._arrows_bound_to(item)]
        self._scene.removeItem(item)
        self._scene.addItem(new)
        ops = [("remove", item), ("create", new)]
        for arr, idx, before in befores:
            self._rebind_arrow(arr, idx, new)
            arr.update()
            ops.append(("mut", arr, "geom", before, arr.capture_geom()))
        self._push_entry(ops)
        self._scene.clearSelection()
        new.setSelected(True)
        self._refresh_properties()

    # ---- [Phase 6 M5] 정렬 / 분배 -------------------------------------------
    # 계획서 §5 #4 흡수. 선택 bbox를 기준으로 붙이고(정렬), 양 끝을 고정한 채 사이 여백을
    # 균등하게 편다(분배). 이동만 하므로 push_undo_move 하나로 되돌아간다.
    # ⚠ 연결된 화살표는 대상이 아니다 — 도형이 움직이면 _on_scene_changed의 reroute가 끝점을
    #   다시 도형에 붙이므로, 화살표까지 옮겨 봐야 그 이동이 곧 덮어써지고 bbox만 흐트러진다.
    #   커넥터는 '정렬되는 것'이 아니라 '따라오는 것'.
    _ALIGN_MODES = (
        ("left",    "왼쪽 맞춤"),
        ("hcenter", "가로 가운데"),
        ("right",   "오른쪽 맞춤"),
        ("top",     "위쪽 맞춤"),
        ("vcenter", "세로 가운데"),
        ("bottom",  "아래쪽 맞춤"),
    )

    def _align_targets(self):
        """정렬·분배 대상 — 선택된 '움직일 수 있는' 최상위 아이템에서 연결 화살표와 용지틀을 뺀 것.
        용지틀(_TitleBlockItem)은 내용이 아니라 종이 자체라 함께 밀리면 안 된다.
        ⚠ 자식 아이템(라벨)은 제외 — 라벨도 selectable·movable이라 러버밴드에 딸려 들어오는데,
          ⓐ 위치를 부모가 소유해(itemChange가 경로 위로 재투영) 옮겨도 되돌아오고
          ⓑ moveBy 델타는 부모 좌표계라, 씬 좌표로 계산한 이동량이 회전된 부모에선 어긋난다."""
        out = []
        for it in self._scene.selectedItems():
            if it.parentItem() is not None:
                continue
            if not (it.flags() & it.GraphicsItemFlag.ItemIsMovable):
                continue
            if isinstance(it, _TitleBlockItem):
                continue
            if isinstance(it, (_ArrowItem, _PolyArrowItem)) and it.has_binding():
                continue
            out.append(it)
        return out

    # ---- [신규기능] 케이블 번호 자동채번 — deep-interview 2026-07-28 -----------
    def _arrow_targets(self):
        """채번 대상 — 선택 중 화살표(직선/곡선/직각 전부)만. 도형·표 등은 무시."""
        return [it for it in self._scene.selectedItems()
                if isinstance(it, (_ArrowItem, _PolyArrowItem))]

    def apply_cable_numbers(self, prefix: str, start: int):
        """선택된 화살표에 위치순(좌상단→우하단)으로 '{prefix}-{n}: ' 라벨을 매긴다.
        기존 라벨 텍스트는 보존(뒤에 이어붙임), 재실행 시 같은 접두사의 옛 번호는 교체된다.
        신규 라벨 생성(create)과 기존 라벨 수정(mut/state)을 한 undo 엔트리로 묶는다."""
        targets = self._arrow_targets()
        if not targets:
            return
        anchored = [(it, it.mapToScene(it._label_anchor())) for it in targets]
        anchored.sort(key=lambda pair: (round(pair[1].y()), round(pair[1].x())))
        targets = [it for it, _ in anchored]
        # 현재 접두사의 옛 번호만 인식해 교체 — 접두사가 다르면(예: 이전 CABLE→이번 CAM)
        # 옛 패턴은 매칭 안 되고 그대로 보존된 채 새 번호가 앞에 붙는다(의도된 동작).
        num_re = re.compile(r"^" + re.escape(prefix) + r"-\d+:?\s*")
        ops = []
        for i, it in enumerate(targets, start=start):
            is_new = not it._label_alive()
            lbl = it.ensure_label()
            before = None if is_new else lbl.capture_state()
            old_text = lbl.toPlainText()
            m = num_re.match(old_text)
            rest = old_text[m.end():] if m else old_text
            new_text = f"{prefix}-{i}: {rest}" if rest else f"{prefix}-{i}"
            lbl.setPlainText(new_text)
            if is_new:
                ops.append(("create", lbl))
            else:
                ops.append(("mut", lbl, "state", before, lbl.capture_state()))
        self._push_entry(ops)
        self.statusBar().showMessage(f"케이블 번호 매김 — {len(targets)}개", 2000)

    def _prompt_cable_numbers(self):
        dlg = _CableNumberDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        prefix, start = dlg.result()
        self.apply_cable_numbers(prefix, start)

    def _repaint_overlays(self):
        """뷰 전체를 다시 칠한다. 프로그램이 아이템을 옮긴 뒤 반드시 필요 —
        ⚠ 다중선택 그룹 박스·정렬 가이드는 아이템이 아니라 뷰의 drawForeground가 그리는데,
        Qt는 '움직인 아이템의 boundingRect'만 무효화하므로 선택 bbox 가장자리에 그려진 옛
        점선이 지워지지 않고 남는다(실조건 2026-07-26 사용자 화면에서 확인).
        마우스 드래그로 옮길 땐 이어지는 이동 이벤트가 어차피 다시 칠해 드러나지 않는다."""
        self._view.viewport().update()

    @staticmethod
    def _align_rect(it) -> QRectF:
        """정렬 기준이 되는 '보이는 도형'의 씬 사각형.
        ⚠ sceneBoundingRect()를 쓰면 안 된다 — 코어의 boundingRect()는 선택 핸들·회전 핸들·
        빠른생성 도트 자리를 상시 예약하므로 도형마다 여백이 제각각이고(실측 26px vs 19.75px)
        그만큼 어긋나게 정렬된다. _content_rect()가 획까지만 포함한 실제 내용 사각형."""
        r = it._content_rect() if hasattr(it, "_content_rect") else it.boundingRect()
        return it.mapToScene(r).boundingRect()   # 회전·스케일 반영

    def align_selection(self, mode):
        """선택 bbox의 해당 모서리(또는 중심)에 대상들을 맞춘다. 기준을 '먼저 고른 객체'가 아니라
        bbox로 두는 것은 선택 순서가 Qt에서 보장되지 않기 때문(Figma·Lucid의 기본과 동일)."""
        boxes = [(it, self._align_rect(it)) for it in self._align_targets()]
        if len(boxes) < 2:
            return
        box = QRectF()
        for _it, r in boxes:
            box = box.united(r)
        pairs = [(it, QPointF(it.pos())) for it, _r in boxes]
        moved = False
        for it, r in boxes:
            dx = dy = 0.0
            if mode == "left":
                dx = box.left() - r.left()
            elif mode == "right":
                dx = box.right() - r.right()
            elif mode == "hcenter":
                dx = box.center().x() - r.center().x()
            elif mode == "top":
                dy = box.top() - r.top()
            elif mode == "bottom":
                dy = box.bottom() - r.bottom()
            elif mode == "vcenter":
                dy = box.center().y() - r.center().y()
            if dx or dy:
                it.moveBy(dx, dy)
                moved = True
        if moved:
            self.push_undo_move(pairs)
            self._repaint_overlays()

    def distribute_selection(self, axis):
        """가로("x")/세로("y") 균등 분배 — 양 끝은 그대로 두고 사이 '여백'을 같게 편다.
        중심 간격이 아니라 여백을 나누는 것은 크기가 제각각인 도형에서도 눈에 보이는 틈이
        같아야 하기 때문. 3개 미만이면 나눌 사이가 없어 아무 일도 하지 않는다."""
        targets = self._align_targets()
        if len(targets) < 3:
            return
        horiz = (axis == "x")
        boxes = sorted(((it, self._align_rect(it)) for it in targets),
                       key=lambda p: p[1].left() if horiz else p[1].top())
        first, last = boxes[0][1], boxes[-1][1]
        span = (last.right() - first.left()) if horiz else (last.bottom() - first.top())
        used = sum((r.width() if horiz else r.height()) for _it, r in boxes)
        gap = (span - used) / (len(boxes) - 1)   # 겹쳐 있으면 음수 — 그래도 균등해진다
        pairs = [(it, QPointF(it.pos())) for it, _r in boxes]
        cur = first.left() if horiz else first.top()
        prev = first.width() if horiz else first.height()
        moved = False
        for it, r in boxes[1:-1]:
            cur += prev + gap
            d = cur - (r.left() if horiz else r.top())
            if d:
                it.moveBy(d, 0.0) if horiz else it.moveBy(0.0, d)
                moved = True
            prev = r.width() if horiz else r.height()
        if moved:
            self.push_undo_move(pairs)
            self._repaint_overlays()

    def _build_align_menu(self, title="", parent=None):
        """정렬 6 + 분배 2 메뉴. 미니툴바 드롭다운과 우클릭 서브메뉴가 같은 메뉴를 쓴다.
        우클릭 메뉴는 매번 새로 만들어지므로 parent를 그 메뉴로 줘서 함께 정리되게 한다."""
        m = QMenu(title, parent or self)
        for mode, label in self._ALIGN_MODES[:3]:
            m.addAction(label, lambda md=mode: self.align_selection(md))
        m.addSeparator()
        for mode, label in self._ALIGN_MODES[3:]:
            m.addAction(label, lambda md=mode: self.align_selection(md))
        m.addSeparator()
        m.addAction("가로 균등 분배", lambda: self.distribute_selection("x"))
        m.addAction("세로 균등 분배", lambda: self.distribute_selection("y"))
        return m


# ---------------------------------------------------------------------------
# [Phase 4] 표제란 다이얼로그 — 삽입 시 용지 선택 / 더블클릭 시 필드 편집
# ---------------------------------------------------------------------------
_ORIENTS = [("landscape", "가로"), ("portrait", "세로")]


def _build_paper_combos(dlg, size: str, orient: str):
    """용지 크기·방향 콤보 2개를 만들어 (size_combo, orient_combo)로 반환."""
    size_cb = QComboBox(dlg)
    for k in PAPER_SIZES_MM:
        size_cb.addItem(k, k)
    idx = size_cb.findData(size)
    size_cb.setCurrentIndex(idx if idx >= 0 else 0)
    orient_cb = QComboBox(dlg)
    for key, label in _ORIENTS:
        orient_cb.addItem(label, key)
    oidx = orient_cb.findData(orient)
    orient_cb.setCurrentIndex(oidx if oidx >= 0 else 0)
    return size_cb, orient_cb


class _PaperSizeDialog(QDialog):
    """표제란 삽입 시 용지 크기·방향만 고르는 작은 다이얼로그."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("용지 선택")
        form = QFormLayout(self)
        self._size_cb, self._orient_cb = _build_paper_combos(self, "A2", "landscape")
        form.addRow("용지 크기", self._size_cb)
        form.addRow("방향", self._orient_cb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result_size_orient(self):
        return self._size_cb.currentData(), self._orient_cb.currentData()


class _TitleBlockDialog(QDialog):
    """표제란 필드 편집 폼 + 용지 크기·방향 재선택."""

    def __init__(self, parent, item):
        super().__init__(parent)
        self.setWindowTitle("표제란 편집")
        form = QFormLayout(self)
        self._size_cb, self._orient_cb = _build_paper_combos(self, item._size, item._orient)
        form.addRow("용지 크기", self._size_cb)
        form.addRow("방향", self._orient_cb)
        self._edits = {}
        for key in TB_FIELD_KEYS:
            ed = QLineEdit(item._fields.get(key, ""), self)
            self._edits[key] = ed
            form.addRow(TB_FIELD_LABELS[key], ed)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result_size_orient(self):
        return self._size_cb.currentData(), self._orient_cb.currentData()

    def result_fields(self):
        return {k: ed.text() for k, ed in self._edits.items()}


class _TableSizeDialog(QDialog):
    """표 삽입 시 행·열 개수와 헤더 행 여부를 고르는 작은 다이얼로그."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("표 삽입")
        form = QFormLayout(self)
        self._rows_sb = QSpinBox(self)
        self._rows_sb.setRange(1, 100)
        self._rows_sb.setValue(3)
        self._cols_sb = QSpinBox(self)
        self._cols_sb.setRange(1, 50)
        self._cols_sb.setValue(3)
        self._header_cb = QCheckBox("첫 행을 헤더로(굵게)", self)
        self._header_cb.setChecked(True)
        form.addRow("행", self._rows_sb)
        form.addRow("열", self._cols_sb)
        form.addRow(self._header_cb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result(self):
        return self._rows_sb.value(), self._cols_sb.value(), self._header_cb.isChecked()


class _CableNumberDialog(QDialog):
    """[신규기능] 케이블 번호 자동채번 — 접두사·시작번호를 고르는 작은 다이얼로그."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("케이블 번호 매기기")
        form = QFormLayout(self)
        self._prefix_le = QLineEdit("CABLE", self)
        self._start_sb = QSpinBox(self)
        self._start_sb.setRange(0, 99999)
        self._start_sb.setValue(1)
        form.addRow("접두사", self._prefix_le)
        form.addRow("시작번호", self._start_sb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def result(self):
        prefix = self._prefix_le.text().strip() or "CABLE"
        return prefix, self._start_sb.value()


class _MermaidDialog(QDialog):
    """Mermaid flowchart 코드를 붙여넣는 입력창(붙여넣기 다이얼로그 — deep-interview 확정)."""

    _SAMPLE = ("flowchart TD\n"
               "    A[시작] --> B{조건?}\n"
               "    B -->|예| C[처리]\n"
               "    B -->|아니오| D([종료])\n"
               "    C --> D")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mermaid 가져오기")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Mermaid flowchart 코드를 붙여넣으세요 "
                             "(flowchart TD/LR … · 노드 모양·화살표·라벨 지원):"))
        self._edit = QPlainTextEdit(self)
        self._edit.setPlaceholderText(self._SAMPLE)
        self._edit.setMinimumSize(QSize(460, 280))
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self._edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def text(self):
        return self._edit.toPlainText()
