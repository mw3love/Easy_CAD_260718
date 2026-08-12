"""CanvasWindow 믹스인 — 창 구성 — 메뉴/툴바/좌측 도형·심볼 패널/속성패널 골격/미니맵 패널/줌·테마·단축키 도움말/리사이즈·패널 재배치.

2026-08-02 host.py(3635줄) 분할분. `class CanvasWindow(...)`이 이 믹스인들을 다중상속해
메서드를 합친다 — 동작·이름 전부 원본과 동일(이동만), annotator_core.py가 이미 쓰는 믹스인
패턴을 host.py에도 적용한 것.
"""
from __future__ import annotations

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
from easycad.fileio.document import save_document, load_document, load_document_layers, _b64_to_pixmap
from easycad.fileio import symbol_library
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)
from easycad.canvas.host_widgets import (
    _CANVAS_BG, _set_icon_color, _current_icon_color,
    _act_icon, _dark_palette, _light_palette, _FloatingPanel, _PaletteButton, _MinimapView,
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
_PALETTE_DROP_WH = {
    # 사각형 기본 120×120(정사각) — 2026-08-09 deep-interview: "포트가 붙는 한 변 기준으로
    # 포트 10개 폭"이라는 사용자 어림값(포트 변 12 × 10)을 그대로 채택, 가로세로 비대칭일
    # 이유가 없어 정사각으로(구 120×72).
    "rect": (120.0, 120.0), "ellipse": (100.0, 100.0),
    "port_rect": (12.0, 12.0), "port_circle": (12.0, 12.0),   # 포트 기본 크기 — 2026-08-09
    # deep-interview: 실도면 대조로 텍스트 라벨보다 작은 절대 고정 크기(구 18→12)로 축소.
}
_PALETTE_SYM_WH = (120.0, 72.0)                   # 심볼(sym:*) 공통 기본 크기 (삼각형은 예외 — 아래)
# [신규기능, 2026-08-09 deep-interview → 2026-08-10 후속] 삼각형은 정삼각형 기본을 원한다.
# [2026-08-10 후속] _sym_triangle()이 이제 bbox를 그대로 채운다(Lucid 대조 — 정삼각형 내접은
# 리사이즈 핸들이 실제 꼭짓점과 어긋나는 근본 원인이었다) — "정삼각형처럼 보이는" 몫은 여기
# 기본 박스 비율(높이 대비 폭 = sqrt(3)/2)이 담당한다. 리사이즈하면 다른 도형처럼 그 비율이
# 깨지는 게 정상(원을 늘이면 타원 되는 것과 같음) — 기본 생성 시점만 정삼각형 보장.
_PALETTE_TRIANGLE_WH = (77.94, 90.0)




class _UIBuildMixin:
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

        # [§8 항목14, 2026-08-07] 옛 "전체"/"선택영역" 별도 메뉴 2개를 1개로 통합 —
        # 전체/선택 선택지는 _PdfExportDialog 안의 라디오로 이동(옵션+라이브 미리보기).
        self._act_pdf = self._make_action("PDF 내보내기…", "pdf", self._export_pdf, "Ctrl+P")
        # [신규기능] DXF 가져오기/내보내기 통합 — 옛 전용 메뉴·단축키(Ctrl+Shift+D/I)는
        # 폐지하고 열기(Ctrl+O)/저장(Ctrl+S)이 확장자로 분기(아래 _open_doc/_save_doc).
        m.addAction(self._act_pdf)
        m.addSeparator()

        self._act_img = self._make_action("이미지 삽입…", "image",
            self._insert_image, "Ctrl+Shift+M")
        self._act_tb = self._make_action("표제란 / 용지틀 삽입…", "titleblock",
            self._insert_titleblock, "Ctrl+Shift+T")
        self._act_tbl = self._make_action("표 삽입…", "table",
            self._insert_table, "Ctrl+Shift+B")
        # [§8 항목18 후속, 2026-08-12] "Mermaid 가져오기"가 AI 보조 생성까지 흡수 —
        # 옛 "AI 이미지→도면…"(이미지 입력, Ctrl+Shift+A)은 실사용 결과 이미지 경로를
        # 폐기하기로 하며 이 메뉴로 통합됐다(_MermaidDialog 안 프롬프트칸+AI버튼 참조).
        self._act_mmd = self._make_action("Mermaid 가져오기…", "mermaid",
            self._insert_mermaid, "Ctrl+Shift+F")
        # [신규기능 2026-08-04] SVG 가져오기 — 손그림/AI로 만든 아이콘을 네이티브 벡터로
        # 들여와 "팔레트에 등록"(§8-8)에 태우는 용도(안테나 심볼 실사용 피드백 대체).
        self._act_svg = self._make_action("SVG 가져오기…", "image",
            self._insert_svg, "Ctrl+Shift+V")
        for a in (self._act_img, self._act_tb, self._act_tbl, self._act_mmd, self._act_svg):
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
        self._act_grid.setChecked(False)
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
        # [2026-08-02 버그 수정] `isVisible()` 가드가 있으면 `showMessage()`가 `.show()` 전에
        # 이 메서드를 부를 때(당시엔 아직 hide() 상태) 조용히 건너뛰어 토스트가 기본 위치(좌상단)에
        # 남았다 — 이후 창 리사이즈로 다시 불릴 때(그땐 이미 보이는 상태)만 하단중앙으로 옮겨가서
        # "처음엔 좌상단, 몇 번 쓰면 하단중앙"으로 보였다(사용자 재현 보고). 가시성과 무관하게
        # 항상 재배치하면(숨겨진 토스트를 옮겨도 부작용 없음) 호출 순서에 안전해진다.
        toast = getattr(self, "_toast", None)
        if toast is None:
            return
        m = self._PANEL_MARGIN
        vpos = self._view.mapTo(self, QPoint(0, 0))
        vx, vy, vw, vh = vpos.x(), vpos.y(), self._view.width(), self._view.height()
        x = vx + (vw - toast.width()) // 2
        y = vy + vh - m - toast.height()
        toast.move(max(vx, x), y)

    # 파일 탐색기에서 이미지를 캔버스로 끌어다 놓기 — QMainWindow가 드롭을 받는다(코어 뷰 무수정).

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
            btn.setIcon(_tool_icon(key, _current_icon_color()))
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
        self._dark = dark
        key = "dark" if dark else "light"
        _set_icon_color(dark)   # host_widgets._ICON_COLOR 갱신(host_widgets._act_icon()이 읽는 실제 전역)
        app = QApplication.instance()
        if app is not None:
            app.setStyle("Fusion")   # 두 테마 모두 Fusion — 팔레트가 전 위젯에 안정 반영
            # [2026-08-02 버그 수정] 예전엔 라이트에 `app.style().standardPalette()`를 썼는데,
            # 이 Qt6/Windows 조합은 OS 다크모드를 따라 Fusion "표준" 팔레트 자체가 다크로
            # 나온다(`styleHints().colorScheme()`가 Dark) — 라이트 토글이 캔버스만 하얘지고
            # 패널·버튼·제목/토스트 텍스트는 다크 색 그대로 남아 안 보이던 원인. `_dark_palette()`처럼
            # 고정 색 팔레트(`_light_palette()`)로 OS 설정과 무관하게 만들어 해결.
            app.setPalette(_dark_palette() if dark else _light_palette())
        self._scene.setBackgroundBrush(QBrush(_CANVAS_BG[key]))
        # 아이콘 재생성: 액션(파일/보기 26종 전부 — SVG 11종·QPainter 8종 모두 이제 중립색이라
        # 테마 전환마다 실제로 재칠됨) + 팔레트/심볼(중립색) + 상단 그리기 도구 7종(2026-08-02
        # 4차 피드백으로 코랄 고정 → 중립색 전환, 이제 테마 전환 시 재생성 필요 — 2026-08-10
        # TRIM 추가로 6→7종) + 화살표 종류별 아이콘(별도 헬퍼가 종류를 함께 챙김).
        for act, name in getattr(self, "_icon_actions", ()):
            act.setIcon(_act_icon(name))
        for k, b in getattr(self, "_shape_tool_buttons", {}).items():
            b.setIcon(self._shape_icon(k))
        for k, b in getattr(self, "_sym_buttons", {}).items():
            b.setIcon(self._shape_icon(k))
        for k, b in getattr(self, "_tool_buttons", {}).items():
            b.setIcon(_tool_icon(k, _current_icon_color()))
        self._refresh_arrow_tool_button()
        # [캔버스-퍼스트] 플로팅 패널 제목줄 = accent 밑줄 + 틴트 배경(옛 dock 제목표시줄과 같은
        # '잡아 눈에 띄는 카드' 언어 유지, 자유 드래그는 없지만 접기 버튼이 있는 자리라 여전히
        # 상호작용 영역으로 보여야 함).
        # [디자인 베이크오프 2026-08-02] accent는 코랄(Claude 브랜드톤) 고정, 다크/라이트 공통 —
        # 아이콘이 이미 양쪽 다 코랄로 확정돼(2라운드) 라이트만 블루로 남겨두면 아이콘·강조선
        # 색이 어긋난다(예전엔 "라이트는 스코프 밖"으로 블루 유지했던 결정을 여기서 통일).
        accent = "#da7756"
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
        # [디자인 베이크오프 2026-08-02] 버튼 상태(hover/checked/pressed) 코랄 강조 — 다크/라이트
        # 공통(예전엔 다크 전용이었는데, 라이트 팔레트 버그 수정과 함께 라이트도 켬 — 아이콘이
        # 이미 양쪽 다 코랄이라 강조도 맞춰야 자연스럽다). Qt QSS는 box-shadow가 없어 Material
        # 참고시안의 그림자는 배경 틴트 강도로 근사한다(호버<pressed 순으로 진하게).
        # [2026-08-02 사용자 재피드백] "테두리만" 버전(직전 커밋)도 여전히 과했다 — 스냅·격자·
        # 좌측 「도형」 탭처럼 **기본값이 ON이라 상시 켜져 있는 토글**이 코랄 테두리 박스로
        # 계속 떠 있어 "항상 튀어 보인다"는 지적. 순간적으로 켜지는 것(그리기 도구 무장·핀)엔
        # 테두리가 적절하지만, 상시 상태엔 옅은 배경 틴트가 덜 튀면서도 "켜짐"을 계속 알린다 —
        # 사용자 선택(대안 1): checked는 테두리 없이 옅은 배경 틴트만(alpha 35).
        # [2026-08-02 3차 피드백] checked가 무테두리가 되니 이번엔 hover만 테두리가 남아 오히려
        # 더 튀었다 — hover도 테두리 없이 옅은 틴트로 낮춤(완전히 없애지 않은 이유: 아이콘 전용
        # 툴바라 hover가 유일한 즉각 피드백, 툴팁은 딜레이가 있음).
        # [2026-08-02 4차 피드백] hover까지 코랄이면 이미 아이콘·checked·구분선이 전부 코랄인
        # 화면에서 코랄이 흔해져 "진짜 선택됨"(checked)의 신호력이 떨어진다는 지적 — hover는
        # 의미 없는 발견용 신호(커서가 지나갈 뿐)라 **중립 회색 틴트**로 바꾸고, checked는 실제
        # "지금 활성 상태"라는 의미가 있으니 코랄을 그대로 유지(사용자 확인). 다크는 배경을
        # 밝히는 흰색 계열(rgba(255,255,255,22)), 라이트는 반대로 어둡히는 검정 계열
        # (rgba(0,0,0,18))— 밝은 배경 위에 흰 틴트를 얹으면 안 보이므로 방향을 테마별로 뒤집는다.
        # pressed는 여전히 코랄 진하게(클릭 확정 피드백은 또렷해야 하므로 건드리지 않음).
        hover_bg = "rgba(255,255,255,22)" if dark else "rgba(0,0,0,18)"
        # [2026-08-02 5차 피드백] "상시 켜짐"(스냅·격자, 기본값 ON)은 옅은 틴트(35)를 유지하되,
        # "순간적으로 켜지는" 것(그리기 도구 무장·핀·직교)은 클릭 순간(pressed)의 진한 코랄을
        # 뗀 뒤에도 고정색으로 유지해 달라는 요청 — objectName 선택자로 두 그룹을 나눈다.
        # `QToolButton#toolStrongCheck:checked`는 CSS 명시도(objectName 선택자 > 타입 선택자)로
        # 일반 `QToolButton:checked` 규칙을 이긴다 — 같은 스타일시트 문자열 안에서 셀렉터
        # 명시도로 가르는 방식이라(각 버튼에 별도 stylesheet를 걸어 조상↔자손 캐스케이드에
        # 기대는 방식보다) 결과가 항상 결정적이다. 이 objectName은 아래에서 대상 위젯에만 부여.
        strong_checked_bg = "rgba(218,119,86,150)"
        btn_qss = (
            "QToolButton { border:1px solid transparent; border-radius:6px; padding:3px; }"
            "QToolButton:checked { background:rgba(218,119,86,35); }"
            f"QToolButton#toolStrongCheck:checked {{ background:{strong_checked_bg};"
            " border-color:#da7756; }"
            f"QToolButton:hover {{ background:{hover_bg}; }}"
            f"QToolButton:pressed {{ background:{strong_checked_bg}; border-color:#da7756; }}"
        )
        toolbar = getattr(self, "_toolbar", None)
        if toolbar is not None:
            sep_color = "#3d4b5c" if dark else "#c9d3dc"
            toolbar.setStyleSheet(
                f"QToolBar::separator {{ background:{sep_color}; width:1px; margin:6px 9px; }}"
                + btn_qss)
            # 순간적 활성 그룹: 그리기 도구 6종(선택/화살표/텍스트/선/펜/번호) + 핀 + 직교.
            # 스냅·격자는 objectName을 안 줘서 위 일반 규칙(옅은 35)에 그대로 남는다.
            _strong_check_widgets = list(getattr(self, "_tool_buttons", {}).values())
            for act_name in ("_act_pin", "_act_ortho"):
                act = getattr(self, act_name, None)
                w = toolbar.widgetForAction(act) if act is not None else None
                if w is not None:
                    _strong_check_widgets.append(w)
            for w in _strong_check_widgets:
                w.setObjectName("toolStrongCheck")
        _accent_btns = (
            list(getattr(self, "_shape_tool_buttons", {}).values())
            + list(getattr(self, "_sym_buttons", {}).values())
            + list(getattr(self, "_left_tab_buttons", {}).values())
        )
        for name in ("_pf_color", "_pf_fill", "_pf_swap_btn", "_pf_routing_btn", "_pf_dir_btn"):
            b = getattr(self, name, None)
            if b is not None:
                _accent_btns.append(b)
        for b in _accent_btns:
            b.setStyleSheet(btn_qss)
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

    # ---- 도형 팔레트 (좌측 dock) — 기본(네모·원) + 내 심볼(SVG 가져오기) --------------
    @staticmethod

    @staticmethod
    def _shape_icon(kind: str, px: int = 30) -> QIcon:
        """팔레트 아이콘 — 캔버스 도형과 같은 모양으로 그린다. 심볼은 경로 팩토리,
        기본 도형(rect/ellipse)은 직접."""
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(_current_icon_color()); pen.setWidthF(1.6)   # 테마색(다크/라이트 적응)
        p.setPen(pen); p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        m = 4
        r = QRectF(m, m, px - 2 * m, px - 2 * m)
        if kind == "rect":
            p.drawRect(r)
        elif kind == "ellipse":
            p.drawEllipse(r)
        elif kind in ("port_rect", "port_circle"):
            # [신규기능 §8-12] 포트 — 기본 도형보다 작게 그려 "장비에 붙는 부속"임을 암시.
            small = r.adjusted(r.width() * 0.28, r.height() * 0.28,
                                -r.width() * 0.28, -r.height() * 0.28)
            p.drawRect(small) if kind == "port_rect" else p.drawEllipse(small)
        elif kind == "terminal":
            # [2026-08-03 버그 수정] 스타디움(양끝 둥근 알약형)이 정사각형 캔버스에 그려지면
            # 반지름이 min(w,h)/2 = w/2가 되어 완전한 원이 되고, "원"(ellipse) 아이콘과 똑같이
            # 보였다(사용자 발견). 실제 캔버스 도형은 이미 가로가 긴 비율로 생성되므로(host_ui.py
            # _PALETTE_SYM_WH = 120x72) 아이콘도 세로를 눌러 같은 비율로 맞춘다.
            oblong = QRectF(r.left(), r.center().y() - r.height() * 0.3,
                             r.width(), r.height() * 0.6)
            p.drawPath(_SYMBOL_KINDS[kind][1](oblong))
        elif kind == "dtv":
            # [§8-13] DTV는 세로로 매우 좁은 패널(0~100 좌표계 32:84)이라 정사각 아이콘 박스에
            # 그대로 그리면 옆으로 퍼져 보인다 — terminal과 반대 방향으로 폭만 좁혀 비율을 살린다.
            tall = QRectF(r.center().x() - r.width() * 0.22, r.top(),
                          r.width() * 0.44, r.height())
            p.drawPath(_SYMBOL_KINDS[kind][1](tall))
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
            w, h = _PALETTE_TRIANGLE_WH if kind == "triangle" else _PALETTE_SYM_WH
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
        elif kind == "port_rect":
            p.drawRect(r)
        elif kind == "port_circle":
            p.drawEllipse(r)
        else:
            p.drawPath(path_fn(r))
        p.end()
        return pm


    def _palette_button(self, label: str, icon_kind, tooltip: str, tool_key: str) -> QToolButton:
        """icon_kind는 보통 _SYMBOL_KINDS 키 문자열이지만, 커스텀 심볼(§8-8)처럼 미리 만든
        QIcon(썸네일)을 직접 넘길 수도 있다."""
        btn = _PaletteButton(tool_key, preview_fn=self._render_drag_preview)   # [M3 #17] 클릭=무장 / 드래그=캔버스 드롭 생성
        btn.setText(label)
        btn.setIcon(icon_kind if isinstance(icon_kind, QIcon) else self._shape_icon(icon_kind))
        btn.setIconSize(QSize(30, 30))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(QSize(64, 56))   # 고정 크기 — dock이 넓어도 버튼이 커지거나 벌어지지 않게
        btn.clicked.connect(
            lambda _c=False, k=tool_key: self.set_tool(None if self.current_tool == k else k))
        return btn

    @staticmethod

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


    def _refresh_custom_symbol_section(self):
        """[신규기능 §8-8] '내 심볼' 섹션을 라이브러리 파일 기준으로 다시 그린다 —
        등록/삭제 직후 호출. 빈 슬롯이 나오지 않도록 라이브러리가 비면 섹션 자체를 숨긴다."""
        grid, old_btns = self._shape_sections[self._custom_sym_idx]
        for b in old_btns:
            grid.removeWidget(b)
            b.deleteLater()
        entries = symbol_library.load_library()
        self._custom_sym_buttons = {}
        btns = []
        for entry in entries:
            icon = QIcon(_b64_to_pixmap(entry["thumb"]))
            sid = entry["id"]
            key = f"customsym:{sid}"
            btn = self._palette_button(entry["name"][:6], icon, entry["name"], key)
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, sid=sid: self._delete_custom_symbol_prompt(sid))
            self._custom_sym_buttons[sid] = btn
            btns.append(btn)
        self._shape_sections[self._custom_sym_idx] = (grid, btns)
        self._custom_sym_section.setVisible(bool(entries))
        self._relayout_sections(horiz=False)


    def _delete_custom_symbol_prompt(self, sym_id: str):
        """[신규기능 §8-8] 팔레트 버튼 우클릭 → 확인 후 라이브러리에서 삭제(캔버스에 이미
        놓인 사본은 독립 아이템이라 영향 없음 — 라이브러리는 '찍어내는 틀'일 뿐)."""
        entry = next((e for e in symbol_library.load_library() if e.get("id") == sym_id), None)
        name = entry["name"] if entry else sym_id
        ret = QMessageBox.question(
            self, "팔레트에서 삭제", f"'{name}' 심볼을 팔레트에서 삭제할까요?")
        if ret == QMessageBox.StandardButton.Yes:
            symbol_library.delete_symbol(sym_id)
            self._refresh_custom_symbol_section()


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
        self._shape_sections: list = []   # (grid, buttons)
        # [§8 항목17 7단계, 2026-08-10] 포트□/포트○ 팔레트 버튼 제거 — TRIM 도구가 일반
        # 사각형/원을 겹쳐 놓고 자르는 워크플로로 대체(계획서 확정, 2026-08-04 순서도 섹션
        # 제거와 같은 패턴: 백엔드(`_create_port_at`/`_ports`/직렬화/DXF)는 그대로 둬 기존
        # `.ecad`(포트 포함)가 그대로 열리고 렌더·회귀 안전).
        basic = self._make_shape_section("기본", [
            ("네모", "rect", "네모 — 클릭 후 캔버스에 드래그", "rect"),
            ("원", "ellipse", "원 — 클릭 후 캔버스에 드래그", "ellipse"),
            ("삼각형", "triangle", "삼각형 — 클릭 후 캔버스에 드래그", "sym:triangle"),
        ], self._shape_tool_buttons)
        self._custom_sym_buttons: dict[str, QToolButton] = {}   # [신규기능 §8-8] set_tool 체크상태 동기화용
        custom = self._make_shape_section("내 심볼", [], self._custom_sym_buttons)   # 버튼은 refresh가 채움
        self._custom_sym_idx = len(self._shape_sections) - 1
        self._custom_sym_section = custom
        box.addWidget(basic); box.addWidget(custom)
        self._relayout_sections(horiz=False)   # 항상 세로(2열) — 반응형 전환 없음
        self._refresh_custom_symbol_section()
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
