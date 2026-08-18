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
import os
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
    QListWidget, QListWidgetItem, QTabWidget,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _tool_icon, _nearest_border,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _DEFAULT_INK_DARK, _DEFAULT_INK_LIGHT,
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
    _PaletteButton, _clipboard_pixmap, _act_icon, _dark_palette,
    _MinimapView, _FloatingPanel, _ToastLabel, _ColorGridPopup,
    _SharedClipboard, _CANVAS_BG,
)
from easycad.canvas.host_dialogs import (
    _PaperSizeDialog, _TitleBlockDialog, _TableSizeDialog, _CableNumberDialog,
    _MermaidDialog,
)
from easycad.canvas.document import CanvasDocument


class CanvasWindow(
    _UIBuildMixin, _FileIOMixin, _LayersMixin, _StyleMixin, _UndoMixin,
    _SelectionMixin, _ContextMixin, _CanvasMixin, QMainWindow,
):
    _PANEL_MARGIN = 10      # [캔버스-퍼스트] 플로팅 패널·줌배지·토스트와 창/뷰 경계 사이 여백(px)

    # [§8 항목10, 2026-08-18] 문서(CanvasDocument)별 상태 이름 — 클래스 하단의 루프가 이
    # 이름들로 self.<name> 프로퍼티를 생성해 "현재 활성 문서(self._active_doc)"로 투명
    # 포워딩한다. 기존 8개 믹스인의 메서드 본문(self._scene/self._undo/... 을 직접 읽고
    # 쓰는 코드)을 한 줄도 안 건드리기 위한 장치 — CanvasDocument 도입은 단일 문서 동작에
    # 아무 변화가 없는 순수 리팩터다(docs/EasyCAD_계획.md §8 10번, 계획 파일 참조).
    _PER_DOC_ATTRS = (
        "scene", "view", "undo", "redo", "layers", "doc_path", "dirty",
        "badge_n", "paste_seq", "pan_last", "rerouting", "deferred_arrows",
        "deferred_fast", "group_sync_active", "geom_snapshot",
        "last_geom_change_count", "uniform_translation", "uniform_moved_arrows",
        "moved_items", "arrow_pos_snapshot", "sel_version", "geom_version",
    )

    # [§8 항목10 Stage D] "새 창"으로 만든 CanvasWindow는 어떤 파이썬 변수도 붙잡고 있지
    # 않아 그냥 두면 즉시 가비지컬렉트된다 — 여기(클래스 속성이라 모든 인스턴스가 공유하는
    # 진짜 전역 리스트)에 살려둔다. closeEvent가 닫힐 때 제거.
    _live_windows: list = []

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Easy CAD")
        self.resize(1200, 800)
        # [캔버스-퍼스트] statusBar()를 QMainWindow 실제 상태바가 아니라 하단중앙 토스트로
        # 프록시 — 창 전체 폭을 가로지르는 항상-보이는 행을 없앤다. 다른 초기화보다 먼저 만들어
        # self.statusBar() 호출이 언제 와도 안전하게(20여 곳의 기존 .showMessage() 호출부는 무수정).
        self._toast = _ToastLabel(self)

        # ---- 편집 상태 (owner 인터페이스) — [§8 항목10] 창 전체(모든 탭)가 공유하는 sticky
        # 설정. 탭 전환에는 안 바뀐다. "새 창"은 생성 시점에 이 값들을 스냅샷 복사만 하고
        # 그 뒤론 독립(deep-interview 확정 — 진짜 실시간 공유는 아래 클립보드만).
        self.current_tool = "select"
        self._dark = QSettings("EasyCAD", "EasyCAD").value("dark", True, type=bool)  # 다크 기본
        self.current_color = QColor(_DEFAULT_INK_DARK if self._dark else _DEFAULT_INK_LIGHT)
        self._color_is_default = True   # [실사용 피드백] 사용자가 직접 색을 고르기 전엔 테마를 따라감
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
        self.grid_enabled = False        # [그리드] 표시+스냅 통합 토글(Shift+G) — 격자 표시·이동/리사이즈/생성 스냅. 기본 off(2026-08-11)
        self.align_guides_enabled = True # [정렬 가이드선] 이동 중 스마트 정렬 스냅+보라 참고선 토글(Shift+A)
        self._bg_item = None            # 배경 이미지 없음(무한 캔버스)

        # [§8 항목10] 도형 클립보드 + 스타일 복사 — 독립 생성된 창은 각자 새 인스턴스(격리).
        # "새 창"(Stage D)만 부모 창의 인스턴스를 그대로 넘겨받아 진짜 실시간 공유가 된다.
        self._clipboard = _SharedClipboard()

        self.setAcceptDrops(True)   # [Phase 4] 이미지 파일 드래그앤드롭 삽입

        # ---- 문서(§8 항목10) — 씬·undo/redo·레이어·저장경로·라우팅/성능 캐시는 전부
        # CanvasDocument가 갖는다(document.py). 위 _PER_DOC_ATTRS 프로퍼티가 self._scene 등을
        # "활성 문서"로 투명 포워딩하므로, 아래부터는 기존과 동일하게 self._view/self._scene을
        # 그대로 쓸 수 있다. 탭 위젯(Stage B) — 문서 1개로 시작, `_new_doc`("새로 만들기")/
        # `_open_doc`("열기")이 탭을 추가한다.
        self._untitled_seq = 0   # ["제목 없음N"] 탭 제목 번호 — 생성 순으로 증가, 안 겹침
        self._shown_once = False   # [§8 항목10 Stage B] showEvent 참조
        self._docs: list[CanvasDocument] = []
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        doc = self._create_doc()
        self._active_doc = doc
        self._tabs.addTab(doc.view, self._tab_title_for(doc))
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.tabCloseRequested.connect(self._close_tab_at)

        # [Phase 6 M1] 메뉴(=액션)를 먼저 만들고 → 상단 QToolBar가 그 액션을 재사용(setDefaultAction).
        self._build_menu()
        self.setCentralWidget(self._tabs)
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

    def _wire_document_signals(self, doc):
        """[§8 항목10] 새 CanvasDocument의 씬 시그널을 연결. 문서가 여러 개(탭)여도 전부 같은
        CanvasWindow 메서드로 모인다 — `_on_scene_changed`는 `self.sender()`로 발신 씬을
        스스로 구분해 그 문서의 상태만 갱신하고(host_canvas.py — 백그라운드 탭에 문서를 로드
        하는 도중에도 정확), 선택 관련 세 슬롯(`_sync_selection_count_cache`/
        `_sync_group_selection`/`_refresh_properties`)은 사용자가 실제로 조작 중인(=활성)
        탭에서만 발화함을 조사로 확인해 `self._active_doc` 포워딩만으로 충분하다
        (host_selection.py 주석 참조 — 로드는 selectionChanged를 발화하지 않음)."""
        doc.scene.changed.connect(self._on_scene_changed)
        doc.scene.selectionChanged.connect(self._sync_selection_count_cache)
        doc.scene.selectionChanged.connect(self._sync_group_selection)
        doc.scene.selectionChanged.connect(self._refresh_properties)

    def showEvent(self, event):
        """[§8 항목10 Stage B] `_create_doc()`가 하는 `view.centerOn(0, 0)`은 뷰가 아직 탭
        위젯에 붙기 전(=크기 0에 가까운 기본값)이라 부정확하다 — QGraphicsView는 그 뒤
        리사이즈에서 "그때의(잘못된) 중심"을 그대로 보존하므로, 나중에 크기가 맞아져도
        원점에서 크게 벗어난 채 남는다(실측으로 확인, 관련 pytest가 실제로 이 어긋남을
        잡아냄). 창이 처음 표시돼 실제 크기가 잡힌 뒤 한 번 더 센터링해 바로잡는다."""
        super().showEvent(event)
        if not self._shown_once:
            self._shown_once = True
            for doc in self._docs:
                doc.view.centerOn(0, 0)

    def _create_doc(self) -> CanvasDocument:
        """[§8 항목10 Stage B] 새 CanvasDocument를 만들고 뷰 초기설정+시그널 연결까지 마친 뒤
        `self._docs`에 등록한다. 탭에 `addTab`하는 건 호출부 책임(__init__ 최초 1개와
        `_open_new_tab`이 타이밍이 달라 여기서 안 함)."""
        doc = CanvasDocument(self)
        # [§8 항목10 실사용 버그 수정, 2026-08-18] CanvasDocument는 배경을 항상 흰색으로
        # 시작한다(테마를 모르는 잎 클래스라 의도된 것) — 원래 단일 문서 시절엔 __init__ 끝의
        # `_apply_theme(self._dark)` 한 번이 그 유일한 씬을 다시 칠해 문제가 없었지만, 탭
        # 도입 후 "새 탭"으로 만든 문서는 그 호출을 한 번도 못 받아 다크모드에서도 캔버스가
        # 계속 흰색으로 남았다(사용자 실사용 발견 — "새 탭만 흰색, 다크 껐다 켜면 정상화").
        # 여기서 생성 시점 테마를 바로 반영한다. `getattr` 폴백은 __init__ 최초 문서 생성
        # 시점엔 self._dark가 아직 없어서(그 줄이 이보다 뒤에 있음) 필요.
        doc.scene.setBackgroundBrush(QBrush(_CANVAS_BG["dark" if getattr(self, "_dark", True) else "light"]))
        doc.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        doc.view.centerOn(0, 0)
        # [M3 #17] 팔레트 드롭이 캔버스 뷰 위에서 무시되던 문제 — 뷰(QGraphicsView)가 드래그를
        # 먼저 가로채 우리 mime를 거부(금지 커서)하므로, 뷰포트에 이벤트 필터를 걸어 직접 받는다.
        doc.view.viewport().setAcceptDrops(True)
        doc.view.viewport().installEventFilter(self)
        self._wire_document_signals(doc)
        self._untitled_seq += 1
        doc.untitled_n = self._untitled_seq
        self._docs.append(doc)
        return doc

    def _tab_title_for(self, doc) -> str:
        """[§8 항목10 Stage B] 탭 제목 = 파일명(있으면) / "제목 없음N"(없으면, 생성 순번
        고정 — 다른 탭이 닫혀도 안 바뀜). [Stage C] dirty면 `*` 접두 — 저장 안 한 변경사항이
        있다는 표시(닫기 실수 방지가 이 접두의 목적)."""
        name = os.path.basename(doc.doc_path) if doc.doc_path else f"제목 없음{doc.untitled_n}"
        return f"*{name}" if doc.dirty else name

    def _update_tab_title(self, doc=None):
        doc = doc or self._active_doc
        idx = self._docs.index(doc)
        self._tabs.setTabText(idx, self._tab_title_for(doc))

    def _mark_dirty(self):
        """[§8 항목10 Stage C] 현재 활성 문서를 dirty로 표시 + 탭 제목에 즉시 반영. undo
        저널에 뭔가 쌓이는(`_push_entry`) 모든 변이·되돌리기/다시실행(`undo`/`redo`)이
        공유하는 단일 훅 지점(host_undo.py)."""
        self._active_doc.dirty = True
        self._update_tab_title()

    def _open_new_tab(self) -> CanvasDocument:
        """[§8 항목10 Stage B] 빈 문서를 새 탭으로 추가하고 활성화한다. "새로 만들기"
        (Ctrl+N, host_fileio._new_doc)와 "열기"(Ctrl+O, _open_doc — 로드 직전에 호출해 그
        빈 탭에 담음)가 공유한다."""
        doc = self._create_doc()
        idx = self._tabs.addTab(doc.view, self._tab_title_for(doc))
        self._tabs.setCurrentIndex(idx)   # -> _on_tab_changed가 self._active_doc을 갱신
        return doc

    def _new_window(self):
        """[§8 항목10 Stage D] 메뉴 "새 창"(Ctrl+Shift+N)."""
        _open_new_window(source=self)

    def _on_tab_changed(self, index):
        if index < 0 or index >= len(self._docs):
            return
        self._active_doc = self._docs[index]
        self._rebuild_minimap()
        self._refresh_layers_panel()
        self._refresh_properties()
        self._refresh_history_actions()
        self._update_zoom_label()

    def _close_tab_at(self, index):
        """[§8 항목10 Stage B→C] 탭 X 버튼. dirty면 `_confirm_close_doc`이 저장/버리기/취소를
        묻는다(취소면 아무 것도 안 함). 마지막 탭을 닫으면 창을 닫는다(표준 관례, Chrome/
        VSCode 동일) — `closeEvent`가 그 경로도 다시 훑지만, 여기서 이미 확정(저장 성공 또는
        명시적 버리기)된 문서는 dirty가 이미 꺼져 있어 두 번 안 묻는다."""
        doc = self._docs[index]
        if not self._confirm_close_doc(doc):
            return
        if len(self._docs) <= 1:
            self.close()
            return
        self._docs.pop(index)
        self._tabs.removeTab(index)
        # CanvasDocument.scene은 QGraphicsScene(window)로 window에 부모 지정돼 있어
        # 명시적으로 떼어내지 않으면 창이 닫힐 때까지 메모리에 남는다.
        doc.view.setParent(None)
        doc.view.deleteLater()
        doc.scene.setParent(None)
        doc.scene.deleteLater()

    def _confirm_close_doc(self, doc) -> bool:
        """[§8 항목10 Stage C] doc이 dirty면 저장/버리기/취소를 묻는다. True=닫아도 됨(저장
        성공 또는 명시적 버리기), False=취소(호출부가 닫기를 중단해야 함). "버리기"를 고르면
        `doc.dirty`를 여기서 꺼둔다 — 그래야 탭 닫기가 마지막 탭이라 곧바로 `closeEvent`로
        이어져도 같은 문서를 두 번 묻지 않는다."""
        if not doc.dirty:
            return True
        if doc is not self._active_doc:
            self._tabs.setCurrentIndex(self._docs.index(doc))   # 저장 다이얼로그가 이 문서를 대상으로
        name = self._tab_title_for(doc).lstrip("*")
        resp = QMessageBox.warning(
            self, "저장 안 한 변경사항",
            f"'{name}'에 저장하지 않은 변경사항이 있습니다. 저장할까요?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if resp == QMessageBox.StandardButton.Cancel:
            return False
        if resp == QMessageBox.StandardButton.Discard:
            doc.dirty = False
            return True
        self._save_doc()
        return not doc.dirty   # 저장 성공(=dirty 해제)했을 때만 닫기 허용, 취소/실패면 남김

    def closeEvent(self, event):
        """[§8 항목10 Stage C] 창을 닫기 전 dirty한 모든 탭을 확인한다(창 X 버튼·Alt+F4·
        마지막 탭 닫기 경로 전부 여길 지난다) — 하나라도 취소하면 창 닫기 전체를 중단."""
        for doc in list(self._docs):
            if not self._confirm_close_doc(doc):
                event.ignore()
                return
        event.accept()
        try:
            CanvasWindow._live_windows.remove(self)   # [§8 항목10 Stage D] "새 창"으로 만들었으면 해제
        except ValueError:
            pass   # main.py가 직접 만든 첫 창 등 — 애초에 이 목록에 없음, 정상

    def _rebuild_minimap(self):
        """[§8 항목10 Stage B] 탭 전환 시 활성 문서의 씬으로 미니맵을 다시 만든다 —
        `_MinimapView`는 생성자에서 scene을 받아 `scene.changed`를 직접 연결하므로
        (host_widgets.py) 씬만 바꿔 끼울 수 없어 재생성이 유일한 방법(조사로 확인)."""
        old_view = getattr(self, "_minimap_wired_view", None)
        if old_view is not None:
            for bar in (old_view.horizontalScrollBar(), old_view.verticalScrollBar()):
                try:
                    bar.valueChanged.disconnect(self._refresh_minimap)
                except TypeError:
                    pass
        old_minimap = getattr(self, "_minimap", None)
        if old_minimap is not None:
            old_minimap.setParent(None)
            old_minimap.deleteLater()
        minimap = _MinimapView(self, self._scene)
        w0 = self._props_panel.width() or 228
        minimap.setFixedSize(QSize(w0, round(w0 * 9 / 16)))
        self._minimap_panel.set_content(minimap)
        self._minimap = minimap
        self._view.horizontalScrollBar().valueChanged.connect(self._refresh_minimap)
        self._view.verticalScrollBar().valueChanged.connect(self._refresh_minimap)
        self._minimap_wired_view = self._view
        self._refresh_minimap()


# [§8 항목10] CanvasWindow._PER_DOC_ATTRS의 각 이름으로 self._<name> 프로퍼티를 생성해
# self._active_doc으로 포워딩 — 클래스 정의가 끝난 뒤에만 setattr(CanvasWindow, ...)로
# 붙일 수 있어 클래스 바깥(모듈 레벨)에 둔다.
def _make_doc_prop(name):
    def _get(self):
        return getattr(self._active_doc, name)

    def _set(self, value):
        setattr(self._active_doc, name, value)

    return property(_get, _set)


for _name in CanvasWindow._PER_DOC_ATTRS:
    setattr(CanvasWindow, f"_{_name}", _make_doc_prop(_name))
del _name


# [§8 항목10] 도형 클립보드 + 스타일 복사 — self._clipboard(인스턴스, __init__ 참조)로
# 포워딩. 위 문서별 프로퍼티와 달리 self._active_doc이 아니라 self._clipboard를 가리킨다 —
# 독립 생성된 창은 서로 다른 _clipboard 인스턴스라 격리되고, "새 창"(Stage D)이 부모의
# _clipboard 인스턴스를 그대로 넘겨받을 때만 실시간 공유가 된다.
def _make_clip_prop(shared_name):
    def _get(self):
        return getattr(self._clipboard, shared_name)

    def _set(self, value):
        setattr(self._clipboard, shared_name, value)

    return property(_get, _set)


for _win_name, _shared_name in (
    ("_clip", "clip"), ("_clip_src", "clip_src"), ("_style_clip", "style"),
):
    setattr(CanvasWindow, _win_name, _make_clip_prop(_shared_name))
del _win_name, _shared_name


# [§8 항목10 Stage D] "새 창"에서 부모 창의 값을 스냅샷 복사할 sticky 설정 — 문서별이
# 아니라 창 전체가 공유하는 것들(CanvasWindow.__init__ "편집 상태" 블록과 동일 목록,
# _bg_item 제외 — 항상 None이라 복사할 의미가 없음). current_tool은 set_tool()으로
# 따로 반영한다(툴바 버튼 체크상태까지 동기화해야 해서 단순 대입으론 부족).
_STICKY_SNAPSHOT_ATTRS = (
    "current_color", "current_width", "current_style", "current_font_size",
    "current_badge_size", "current_text_bg", "current_fill", "_recent_colors",
    "arrow_head_at_end", "current_arrow_kind", "current_curve_r", "tool_pinned",
    "snap_enabled", "ortho_enabled", "grid_enabled", "align_guides_enabled",
)


def _open_new_window(source: CanvasWindow | None = None) -> CanvasWindow:
    """[§8 항목10 Stage D] 같은 프로세스 안에 독립 `CanvasWindow`를 새로 연다.

    `source`가 있으면("새 창" 메뉴, `CanvasWindow._new_window`) 그 시점의 창 전체 sticky
    설정을 스냅샷 복사한다 — 그 뒤로는 독립(라이브 링크 없음, deep-interview 확정: 창A의
    색을 나중에 바꿔도 이미 열린 창B엔 안 옴). 도형 클립보드(`_clipboard`)만 예외 — 인스턴스
    자체를 그대로 공유해 진짜 실시간 공유가 된다(둘 사이 복사/붙여넣기 가능, 확정 사항).

    `source=None`이면(현재는 main.py가 첫 창을 직접 만들어 이 경로를 안 씀, 향후 대비)
    새 창은 완전히 기본값으로 시작한다.

    생성된 창은 `CanvasWindow._live_windows`에 등록해 가비지컬렉트를 막는다(어떤 파이썬
    변수도 이 창을 붙잡지 않으므로) — `closeEvent`가 닫힐 때 해제한다."""
    win = CanvasWindow()
    if source is not None:
        for name in _STICKY_SNAPSHOT_ATTRS:
            setattr(win, name, getattr(source, name))
        win.set_tool(source.current_tool)   # 툴바 체크상태까지 동기화
        win._clipboard = source._clipboard   # 유일한 진짜 실시간 공유(위 설명 참조)
    CanvasWindow._live_windows.append(win)
    win.show()
    return win

