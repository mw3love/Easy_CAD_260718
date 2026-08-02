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

from easycad.canvas.host_ui import _UIBuildMixin
from easycad.canvas.host_fileio import _FileIOMixin
from easycad.canvas.host_layers import _LayersMixin
from easycad.canvas.host_style import _StyleMixin
from easycad.canvas.host_undo import _UndoMixin
from easycad.canvas.host_selection import _SelectionMixin
from easycad.canvas.host_context import _ContextMixin
from easycad.canvas.host_canvas import _CanvasMixin

from easycad.canvas.host_widgets import (
    _PaletteButton, _clipboard_pixmap, _act_icon, _dark_palette, _UndoEntry,
    _MinimapView, _FloatingPanel, _ToastLabel, _ColorGridPopup,
    _SCENE_HALF,
)
from easycad.canvas.host_dialogs import (
    _PaperSizeDialog, _TitleBlockDialog, _TableSizeDialog, _CableNumberDialog,
    _MermaidDialog,
)


class CanvasWindow(
    _UIBuildMixin, _FileIOMixin, _LayersMixin, _StyleMixin, _UndoMixin,
    _SelectionMixin, _ContextMixin, _CanvasMixin, QMainWindow,
):
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

