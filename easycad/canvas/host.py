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
from PyQt6.QtCore import Qt, QPointF, QRectF, QSize, QSettings, QTimer
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter,
    QFont, QPolygonF, QPainterPath, QPalette,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QBoxLayout, QToolButton, QLabel, QFileDialog, QInputDialog, QMessageBox,
    QDockWidget, QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QCheckBox, QPlainTextEdit, QSizePolicy,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
)
from easycad.fileio.pdf_export import export_pdf, PAGE_SIZES
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.document import save_document, load_document
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
    elif name == "dxf_out":
        poly([(6.5, 8), (6.5, 4.5), (15, 4.5), (18, 7.5), (18, 20.5),
              (6.5, 20.5), (6.5, 16)], close=False)   # 왼쪽 변에 화살표 통과 gap
        line(3, 12, 11.5, 12)
        poly([(8.5, 9.5), (11.5, 12), (8.5, 14.5)], close=False)   # → 촉
    elif name == "dxf_in":
        poly([(17.5, 8), (17.5, 4.5), (9, 4.5), (6, 7.5), (6, 20.5),
              (17.5, 20.5), (17.5, 16)], close=False)
        line(21, 12, 12.5, 12)
        poly([(15.5, 9.5), (12.5, 12), (15.5, 14.5)], close=False)  # ← 촉
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
    p.end()
    return QIcon(pm)


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
_STYLE_NAMES = {
    Qt.PenStyle.SolidLine: "실선", Qt.PenStyle.DashLine: "점선",
    Qt.PenStyle.DotLine: "점선(도트)", Qt.PenStyle.DashDotLine: "일점쇄선",
    Qt.PenStyle.DashDotDotLine: "이점쇄선",
}


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


class CanvasWindow(QMainWindow):
    # 콤팩트 목표는 콘텐츠 최소보다 작게 → Qt가 '진짜 최소'로 클램프(수동으로 더 못 줄이게).
    _SHAPES_DOCK_W = 80     # 세로 dock → 버튼 2열 최소(≈144px)로 클램프
    _SHAPES_DOCK_H = 80     # 가로 dock → 제목+라벨+버튼 1줄 최소로 클램프
    _PROPS_DOCK_W = 120     # 속성 dock → 폼 최소로 클램프(안내문 줄바꿈 후 좁아짐)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Easy CAD")
        self.resize(1200, 800)

        # ---- 편집 상태 (owner 인터페이스) ----
        self.current_tool = "select"
        self.current_color = QColor(_DEFAULT_COLOR)
        self.current_width = _DEFAULT_WIDTH
        self.current_font_size = _DEFAULT_FONT
        self.current_badge_size = _DEFAULT_BADGE
        self.current_text_bg = None
        self.arrow_head_at_end = True
        self.snap_enabled = True         # o-snap 토글(F3) — 도형 테두리 달라붙기 켜고 끄기
        self.ortho_enabled = False       # Ortho 토글(F8) — 그리기·정점드래그를 수평/수직(0/90°)로 제약
        self._bg_item = None            # 배경 이미지 없음(무한 캔버스)
        self._badge_n = 0
        self._undo: list[_UndoEntry] = []   # 저널(뒤로) — 최신이 끝
        self._redo: list[_UndoEntry] = []   # 다시 실행(앞으로) — 새 변이 시 비워짐
        self._clip: list = []
        self._paste_seq = 0
        self._pan_last = None

        # ---- 씬 / 뷰 ----
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-_SCENE_HALF, -_SCENE_HALF, 2 * _SCENE_HALF, 2 * _SCENE_HALF)
        self._scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        # 지속 연결: 도형/화살표가 움직이면 바인딩된 화살표 끝을 재계산(scene.changed 트리거).
        self._rerouting = False
        self._scene.changed.connect(self._on_scene_changed)
        self._view = _AnnotatorView(self._scene, self)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.centerOn(0, 0)
        self.setAcceptDrops(True)   # [Phase 4] 이미지 파일 드래그앤드롭 삽입

        # [Phase 6 M1] 메뉴(=액션)를 먼저 만들고 → 상단 QToolBar가 그 액션을 재사용(setDefaultAction).
        # 뷰는 중앙 위젯 자체로(별도 QWidget 래퍼 불필요 — 툴바가 QToolBar 영역으로 이동).
        self._dark = QSettings("EasyCAD", "EasyCAD").value("dark", True, type=bool)  # 다크 기본
        self._build_menu()
        self.setCentralWidget(self._view)
        self._build_toolbar()
        self._build_shapes_dock()
        self._build_properties_dock()
        self._build_statusbar()
        self.set_tool("select")
        self._apply_theme(self._dark)   # 저장된 테마 적용(아이콘·배경·팔레트 일괄)
        # 패널 기본 폭을 콤팩트하게 — 처음 뜰 때 너무 넓어 수동 축소해야 했던 문제(사용자 피드백).
        self.resizeDocks([self._shapes_dock, self._props_dock],
                         [self._SHAPES_DOCK_W, self._PROPS_DOCK_W],
                         Qt.Orientation.Horizontal)

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
        self._act_dxf = self._make_action("DXF 내보내기…", "dxf_out",
            self._export_dxf, "Ctrl+Shift+D")
        self._act_dxf_in = self._make_action("DXF 가져오기…", "dxf_in",
            self._import_dxf, "Ctrl+Shift+I")
        for a in (self._act_pdf, self._act_pdf_sel, self._act_dxf, self._act_dxf_in):
            m.addAction(a)
        m.addSeparator()

        self._act_img = self._make_action("이미지 삽입…", "image",
            self._insert_image, "Ctrl+Shift+M")
        self._act_tb = self._make_action("표제란 / 용지틀 삽입…", "titleblock",
            self._insert_titleblock, "Ctrl+Shift+T")
        self._act_tbl = self._make_action("표 삽입…", "table",
            self._insert_table, "Ctrl+Shift+B")
        self._act_mmd = self._make_action("Mermaid 가져오기…", "mermaid",
            self._insert_mermaid, "Ctrl+Shift+G")
        for a in (self._act_img, self._act_tb, self._act_tbl, self._act_mmd):
            m.addAction(a)

        # 편집(상단 툴바 전용 — 메뉴엔 없던 undo/redo를 액션으로. Ctrl+Z/Ctrl+Y 키는 뷰가 처리).
        self._act_undo = self._make_action("되돌리기", "undo", self.undo)
        self._act_redo = self._make_action("다시 실행", "redo", self.redo)

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
        v.addAction(self._act_snap)
        v.addAction(self._act_ortho)
        v.addSeparator()
        self._act_theme = self._make_action("다크/라이트 전환", "theme",
            self._toggle_theme, "Ctrl+Shift+L")
        v.addAction(self._act_theme)
        self._act_help = self._make_action("단축키 도움말…", "help",
            self._show_shortcuts, "F1")
        v.addAction(self._act_help)

    # ---- 보기: 기준 zoom / 스냅 -------------------------------------------
    def _zoom_reset(self):
        """기준 zoom = 100%(1:1). 무한캔버스에서 돌아올 홈."""
        self._view.resetTransform()
        self._update_zoom_label()

    def _zoom_fit(self):
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            self._view.resetTransform()
            self._update_zoom_label()
            return
        pad = max(rect.width(), rect.height()) * 0.05 + 20
        self._view.fitInView(rect.adjusted(-pad, -pad, pad, pad),
                             Qt.AspectRatioMode.KeepAspectRatio)
        self._update_zoom_label()

    # ---- 상태바 (줌 %) ------------------------------------------------------
    def _build_statusbar(self):
        self._zoom_btn = QToolButton()
        self._zoom_btn.setText("100 %")
        self._zoom_btn.setAutoRaise(True)
        self._zoom_btn.setToolTip("클릭: 100%(1:1)로")
        self._zoom_btn.clicked.connect(self._zoom_reset)
        self.statusBar().addPermanentWidget(self._zoom_btn)

    def _update_zoom_label(self):
        btn = getattr(self, "_zoom_btn", None)
        if btn is not None:
            btn.setText(f"{round(self._view.transform().m11() * 100)} %")

    def _toggle_snap(self, checked: bool):
        self.snap_enabled = checked
        self.statusBar().showMessage(
            "스냅 켜짐" if checked else "스냅 꺼짐 — 자유 배치", 3000)

    def _toggle_ortho(self, checked: bool):
        self.ortho_enabled = checked
        self.statusBar().showMessage(
            "Ortho 켜짐 — 수평/수직만" if checked else "Ortho 꺼짐 — 자유 각도", 3000)

    # ---- 저장 / 열기 --------------------------------------------------------
    _DOC_FILTER = "Easy CAD 문서 (*.ecad)"

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

    def _open_doc(self):
        path, _ = QFileDialog.getOpenFileName(self, "열기", "", self._DOC_FILTER)
        if not path:
            return
        try:
            n = load_document(self._scene, path)
        except Exception as e:  # noqa: BLE001 — 사용자에게 오류만 전달
            QMessageBox.warning(self, "열기 실패", str(e))
            return
        self._reset_history()
        self._doc_path = path
        # 번호 마커 카운터를 로드된 최대값 뒤로 재설정
        nums = [it._number for it in self._scene.items() if hasattr(it, "_number")]
        self._badge_n = max(nums) if nums else 0
        self.statusBar().showMessage(f"열기 완료: {n}개 객체 — {path}", 5000)

    def _save_doc(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "저장", self._doc_path or "", self._DOC_FILTER)
        if not path:
            return
        if not path.lower().endswith(".ecad"):
            path += ".ecad"
        try:
            save_document(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "저장 실패", str(e))
            return
        self._doc_path = path
        self.statusBar().showMessage(f"저장 완료: {path}", 5000)

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

    def _export_dxf(self):
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "DXF 내보내기", "출력할 객체가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "DXF로 저장", "", "DXF 파일 (*.dxf)")
        if not path:
            return
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        try:
            export_dxf(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DXF 내보내기", f"저장에 실패했습니다:\n{e}")
            return
        QMessageBox.information(self, "DXF 내보내기", f"저장 완료:\n{path}")

    def _import_dxf(self):
        # 현재 씬을 대체하는 '열기' 시맨틱(import_dxf clear=True 기본).
        path, _ = QFileDialog.getOpenFileName(self, "DXF 가져오기", "", "DXF 파일 (*.dxf)")
        if not path:
            return
        try:
            n = import_dxf(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DXF 가져오기", f"가져오기에 실패했습니다:\n{e}")
            return
        self._reset_history()
        nums = [it._number for it in self._scene.items() if hasattr(it, "_number")]
        self._badge_n = max(nums) if nums else 0
        self.statusBar().showMessage(f"가져오기 완료: {n}개 객체 — {path}", 5000)

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
        self.statusBar().showMessage(f"이미지 삽입: {w}×{h}px — {path}", 4000)

    # 파일 탐색기에서 이미지를 캔버스로 끌어다 놓기 — QMainWindow가 드롭을 받는다(코어 뷰 무수정).
    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasUrls() and any(u.toLocalFile().lower().endswith(self._IMG_EXTS)
                                for u in md.urls()):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
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

        # 파일 / 삽입
        for a in (self._act_new, self._act_open, self._act_save):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self._act_pdf, self._act_dxf, self._act_dxf_in, self._act_img,
                  self._act_tbl, self._act_tb, self._act_mmd):
            tb.addAction(a)
        tb.addSeparator()

        # 그리기 도구(체크형) — 네모·원은 왼쪽 「도형」 팔레트로 이관(단축키 2·5는 유지).
        self._tool_buttons: dict[str, QToolButton] = {}
        for key, name, sc in _TOOLS:
            if key in ("rect", "ellipse"):
                continue
            btn = QToolButton()
            btn.setIcon(_tool_icon(key, self.current_color))
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(f"{name} ({sc})")
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda _c=False, k=key: self.set_tool(None if self.current_tool == k else k))
            tb.addWidget(btn)
            self._tool_buttons[key] = btn
        tb.addSeparator()

        # 편집 / 보기
        for a in (self._act_undo, self._act_redo, self._act_zoom100, self._act_fit,
                  self._act_snap, self._act_ortho):
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
        # dock 제목표시줄 = '잡아 옮기는 바'로 보이게(accent 밑줄 + 틴트 배경). 회색이라 안 보이던 문제.
        accent = "#54a9ff" if dark else "#1f7ae0"
        title_bg = "#232f3d" if dark else "#e8eef5"
        dock_qss = ("QDockWidget { font-weight:600; }"
                    f"QDockWidget::title {{ background:{title_bg}; padding:5px 9px;"
                    f" text-align:left; border-bottom:2px solid {accent}; }}")
        for dock in (getattr(self, "_shapes_dock", None), getattr(self, "_props_dock", None)):
            if dock is not None:
                dock.setStyleSheet(dock_qss)
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
            ("Del", "선택 객체 삭제"),
            ("Ctrl+Z", "되돌리기"),
            ("Ctrl+C / Ctrl+V", "복사 / 연속 붙여넣기"),
            ("1·3·4·6·7·8·9", "선택·화살표·텍스트·선·펜·번호·직선화살"),
            ("2 / 5", "네모 / 원"),
        ]
        body = "\n".join(f"{k:<20}{d}" for k, d in rows)
        box = QMessageBox(self)
        box.setWindowTitle("단축키 도움말")
        box.setText("Easy CAD 단축키")
        box.setInformativeText(body)
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.exec()

    # ---- 도형 팔레트 (좌측 dock) — 기본(네모·원) + 순서도(심볼 6종) -----------
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

    def _palette_button(self, label: str, icon_kind: str, tooltip: str, tool_key: str) -> QToolButton:
        btn = QToolButton()
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
        """[Phase 6 M1] 팔레트 한 섹션(제목+그리드)을 독립 위젯으로. 섹션을 위젯으로 감싸야
        가로/세로 dock 전환 시 '제목 위 그리드' 구조를 유지한 채 섹션끼리 좌우/상하로 흐른다.
        그리드 열 수는 _relayout_sections가 방향에 맞춰 정한다(세로=2열, 가로=한 줄)."""
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

    def _relayout_sections(self, horiz: bool):
        """[Phase 6 M1] 각 섹션 그리드 열 수를 dock 방향에 맞춘다 — 세로 dock=2열(정사각),
        가로(상/하) dock=한 줄로 눕혀 위아래 폭을 최소화(사용자 요청: 가로 dock은 가로 길게).
        여분 폭은 실제 열 뒤 빈 열이 흡수 → 버튼이 왼쪽으로 뭉쳐 벌어지지 않는다(사용자 피드백)."""
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

    def _build_shapes_dock(self):
        dock = QDockWidget("⋮⋮  도형", self)     # 그립 글리프로 '잡아 옮기는 바'임을 표시
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)   # 상/하/좌/우 전체
        self._shapes_dock = dock
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(6, 6, 6, 6); box.setSpacing(10)
        self._dock_box = box

        self._shape_tool_buttons: dict[str, QToolButton] = {}
        self._sym_buttons: dict[str, QToolButton] = {}
        self._shape_sections: list = []   # (grid, buttons) — 방향 전환 시 재배치
        basic = self._make_shape_section("기본", [
            ("네모", "rect", "네모 — 클릭 후 캔버스에 드래그", "rect"),
            ("원", "ellipse", "원 — 클릭 후 캔버스에 드래그", "ellipse"),
        ], self._shape_tool_buttons)
        sym_entries = [(label, kind, f"{label} 심볼 — 클릭 후 캔버스에 드래그", f"sym:{kind}")
                       for kind, (label, _fn) in _SYMBOL_KINDS.items()]
        syms = self._make_shape_section("순서도", sym_entries, self._sym_buttons)

        box.addWidget(basic); box.addWidget(syms); box.addStretch(1)
        self._relayout_sections(horiz=False)   # 초기 좌측 dock = 세로(2열)
        dock.setWidget(panel)
        dock.dockLocationChanged.connect(self._on_dock_moved)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _on_dock_moved(self, area):
        """[Phase 6 M1] 상/하 dock이면 섹션을 가로로 나란히 + 버튼도 한 줄로 눕혀 위아래 폭 최소화."""
        horiz = area in (Qt.DockWidgetArea.TopDockWidgetArea,
                         Qt.DockWidgetArea.BottomDockWidgetArea)
        self._dock_box.setDirection(QBoxLayout.Direction.LeftToRight if horiz
                                    else QBoxLayout.Direction.TopToBottom)
        self._relayout_sections(horiz)
        # 재도킹 시 Qt가 콘텐츠 폭만큼 넓게 잡아 매번 수동 축소해야 했던 문제 → 콤팩트로 자동 조정.
        # 드래그가 settle된 뒤 적용(singleShot 0).
        QTimer.singleShot(0, lambda: self._compact_shapes_dock(horiz))

    def _compact_shapes_dock(self, horiz: bool):
        """도형 dock을 콤팩트 크기로 — 세로 dock=좁은 폭, 가로 dock=낮은 높이."""
        dock = self._shapes_dock
        if horiz:
            self.resizeDocks([dock], [self._SHAPES_DOCK_H], Qt.Orientation.Vertical)
        else:
            self.resizeDocks([dock], [self._SHAPES_DOCK_W], Qt.Orientation.Horizontal)

    # ---- 속성 dock (M1: 값 표시만 — 편집은 M2에서 Undo 개편과 함께) -----------
    def _build_properties_dock(self):
        dock = QDockWidget("⋮⋮  속성", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._props_dock = dock
        panel = QWidget()
        panel.setMinimumWidth(170)   # 값(hex 등)이 안 잘리는 바닥폭 — 이 아래로는 못 좁힘(슬랙 없음)
        form = QFormLayout(panel)
        form.setContentsMargins(10, 10, 10, 10); form.setSpacing(8)
        self._pf_type = QLabel("—")
        self._pf_color = QLabel("—"); self._pf_color.setTextFormat(Qt.TextFormat.RichText)
        self._pf_width = QLabel("—")
        self._pf_style = QLabel("—")
        self._pf_font = QLabel("—")
        form.addRow("종류", self._pf_type)
        form.addRow("색", self._pf_color)
        form.addRow("두께", self._pf_width)
        form.addRow("선", self._pf_style)
        form.addRow("폰트", self._pf_font)
        hint = QLabel("값 표시(읽기전용) — 편집은 곧(M2)")
        hint.setStyleSheet("color:#888; font-size:11px;")
        hint.setWordWrap(True)   # 줄바꿈 허용 → 이 안내문이 속성 dock 최소폭을 붙잡지 않게
        form.addRow(hint)
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._scene.selectionChanged.connect(self._refresh_properties)
        self._refresh_properties()

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
        style = None
        if hasattr(item, "pen"):
            try: style = item.pen().style()
            except Exception: style = None
        font = None
        if hasattr(item, "font"):
            try:
                fs = item.font().pointSizeF()
                font = fs if fs and fs > 0 else None
            except Exception:
                font = None
        return {
            "type": _TYPE_NAMES.get(type(item).__name__, "객체"),
            "color": QColor(col) if col is not None else None,
            "width": width, "style": style, "font": font,
        }

    @staticmethod
    def _agg_num(vals, fmt) -> str:
        """다중선택 수치 집계 — 모두 있고 같으면 값, 섞이면 '혼합', 없으면 '—'."""
        present = [v for v in vals if v is not None]
        if not present:
            return "—"
        if len(present) == len(vals) and (max(present) - min(present) < 0.05):
            return fmt.format(present[0])
        return "혼합"

    def _refresh_properties(self):
        sel = self._scene.selectedItems()
        if not sel:
            for lb in (self._pf_type, self._pf_color, self._pf_width,
                       self._pf_style, self._pf_font):
                lb.setText("—")
            return
        props = [self._read_props(it) for it in sel]
        types = {p["type"] for p in props}
        self._pf_type.setText(next(iter(types)) if len(types) == 1
                              else f"{len(sel)}개 · 혼합")
        cols = [p["color"] for p in props if p["color"] is not None]
        if cols and len(cols) == len(props) and len({c.name() for c in cols}) == 1:
            n = cols[0].name()
            self._pf_color.setText(f'<span style="color:{n}; font-size:15px">■</span> {n}')
        else:
            self._pf_color.setText("혼합" if cols else "—")
        self._pf_width.setText(self._agg_num([p["width"] for p in props], "{:.1f} px"))
        styles = [p["style"] for p in props if p["style"] is not None]
        if styles and len(styles) == len(props) and len(set(styles)) == 1:
            self._pf_style.setText(_STYLE_NAMES.get(styles[0], "실선"))
        else:
            self._pf_style.setText("혼합" if styles else "—")
        self._pf_font.setText(self._agg_num([p["font"] for p in props], "{:.0f} pt"))

    # ---- 지속 연결 리라우트 -------------------------------------------------
    def _on_scene_changed(self, region):
        if self._rerouting:
            return  # 재진입 가드 — reroute가 유발한 changed로 되돌아오지 않게
        if getattr(self._view, "_drawing", False):
            return  # 화살표 그리는 중엔 _update_arrow_draw가 tip을 주도 — 간섭 방지
        if getattr(self._view, "_place", None) is not None:
            return  # 클릭 배치 중엔 배치 로직이 끝점을 주도 — 간섭 방지
        self._rerouting = True
        try:
            for it in self._scene.items():
                # 곡선화살표(_ArrowItem)·직선화살표(_PolyArrowItem) 모두 지속 연결 리라우트.
                if isinstance(it, (_ArrowItem, _PolyArrowItem)) and it.has_binding():
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
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def set_tool(self, key):
        # 도구를 바꾸면 진행 중이던 클릭 배치는 폐기(반쯤 그린 도형이 남지 않게).
        view = getattr(self, "_view", None)
        if view is not None:
            view._cancel_place()
        self.current_tool = key
        for k, b in self._tool_buttons.items():
            b.setChecked(k == key)
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
            item.apply_width(max(1, item._width + step))
        elif hasattr(item, "pen"):
            item.apply_width(max(1.0, item.pen().widthF() + step))
        else:
            return
        self.push_undo_state([(item, before)], coalesce_key=("width", id(item)))

    # 줌 (커서 기준 — 뷰가 AnchorUnderMouse)
    def _on_wheel_zoom(self, dy: int):
        factor = 1.15 if dy > 0 else 1.0 / 1.15
        self._view.scale(factor, factor)
        self._update_zoom_label()

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

    def push_undo_add_many(self, items):
        """[2d] 여러 아이템(복제 도형+연결 화살표)을 한 번의 undo로 함께 제거."""
        self._push_entry([("create", it) for it in items])

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

    def push_undo_geom(self, snaps):
        """[Stage2] 기하 리베이크(비균일 스케일·미러) 되돌리기 — capture_geom 토큰 스냅샷.
        xform과 달리 기하 자체(rect/끝점/정점/패스)+바인딩까지 통째로 복원한다."""
        self._push_entry([
            ("mut", it, "geom", before, it.capture_geom()) for it, before in snaps])

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

    def redo(self):
        if not self._redo:
            return
        entry = self._redo.pop()
        self._apply_entry(entry, redo=True)
        self._undo.append(entry)
        self._refresh_history_actions()

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
        self._clip = [it.clone() for it in self._scene.selectedItems()
                      if hasattr(it, "clone")]
        self._paste_seq = 0

    def paste_selection(self):
        if not self._clip:
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
        if new_items:
            self.push_undo_add_many(new_items)


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
