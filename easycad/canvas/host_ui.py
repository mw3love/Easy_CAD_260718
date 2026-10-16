"""CanvasWindow 믹스인 — 창 구성 — 메뉴/툴바/좌측 도형·심볼 패널/속성패널 골격/미니맵 패널/줌·테마·단축키 도움말/리사이즈·패널 재배치.

2026-08-02 host.py(3635줄) 분할분. `class CanvasWindow(...)`이 이 믹스인들을 다중상속해
메서드를 합친다 — 동작·이름 전부 원본과 동일(이동만), annotator_core.py가 이미 쓰는 믹스인
패턴을 host.py에도 적용한 것.
"""
from __future__ import annotations


from PyQt6.QtCore import Qt, QPoint, QRect, QRectF, QSize, QTimer
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter, QFont, QPalette,
)
from PyQt6.QtWidgets import (
    QApplication, QGraphicsScene, QWidget, QVBoxLayout, QToolButton, QLabel, QFileDialog,
    QInputDialog, QMessageBox, QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QSizePolicy, QHBoxLayout, QMenu, QPushButton,
    QFrame, QListWidget, QStackedWidget, QScrollArea, QToolBar,
)

from easycad.app_settings import app_settings
from easycad.canvas.annotator_core import (
    _PolyArrowItem, _tool_icon, _TOOLS, _DEFAULT_INK_DARK, _DEFAULT_INK_LIGHT, _MIN_FONT, _MAX_FONT,
    _SYMBOL_KINDS, _pen_style_icon, _arrow_kind_icon, _flip_icon, _arrow_head_icon, _icons_dir,
    _svg_icon, _svg_icon_pixmap,
)
from easycad.fileio.pdf_export import export_svg_symbol
from easycad.fileio.document import (
    _b64_to_pixmap, insert_items,
)
from easycad.fileio import symbol_library
from easycad.canvas import shortcuts
from easycad.canvas.host_widgets import (
    _PropPopup, _swatch_icon,
    _CANVAS_BG, _set_icon_color, _current_icon_color,
    _act_icon, _dark_palette, _light_palette, _FloatingPanel, _PaletteButton, _MinimapView,
    _StaticSection, _SymbolFolderDropZone, _apply_native_titlebar_scheme,
    _DragGrip, _SymbolFolderBrowser, _menu_icon, _ACCENT_CORAL, _SECTION_COLOR_SWATCHES,
    _ARROW_KIND_LABELS, _ARROW_HEAD_LABELS, _set_menu_sep_color, _style_menu_separators,
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

# [2026-08-12, 사용자 스크린샷 피드백 — Lucid 대비 버튼이 크고 2열 고정이라 패널 폭의 절반이
# 빈 공간] 아이콘+라벨은 유지하되(사용자 선택) 버튼·아이콘을 줄이고 3열로 늘려 밀도를 높인다.
# [같은 날 후속] 3열로도 아이콘 사이 여백이 넓다는 재피드백 — 버튼 폭을 더 줄이고(74→58)
# 4열로 늘려 같은 폭 안에서 더 촘촘하게(간격은 버튼 내부 여백이 대부분이라 버튼 자체를
# 줄이는 쪽이 grid spacing을 줄이는 것보다 효과적).
# [같은 날 3차 후속] 패널 자체를 속성/미니맵 패널(218px)과 비슷한 폭으로 줄이자는 요청 —
# 버튼·아이콘·폰트를 한 번 더 줄이고(58→48, 22→18, 폰트 -2pt), 4열은 유지.
# [첫 화면 재디자인 2026-10-07, 시안 3라운드 S3 "아이콘이 커서 좋음"] 18→24, 칸 폭 48→56 — 카드 폭이
# 시안(256px)에 가까워지고 오른쪽 카드(속성 P2)도 같은 폭대로 맞춘다.
_PALETTE_ICON_PX = 24
# [실사용 피드백 2026-08-19] 기본도형은 단일 글리프라 18px에서도 또렷하지만, "내 심볼"은
# 사용자가 등록한 임의 조합(예: 사각형 2개+화살표 2개인 작은 흐름도)이라 같은 18px에서는
# 형태 자체가 안 보인다는 보고 — 기본도형과 "최소한 같은 크기"를 요청받아 그보다 큰 전용
# 상수를 신설(기본도형 자체는 이미 충분히 커서 함께 키우지 않음). 그래도 가로로 아주 긴
# 조합은 이 크기에서도 한계가 있어(2:1 이상이면 세로가 다시 눌린다) 호버 확대 미리보기
# (`host_selection._symbol_preview_html`)로 보완한다.
_PALETTE_SYM_ICON_PX = 28
_PALETTE_LIST_ICON_PX = 18   # 「목록」 보기(기본) 줄 아이콘
_PALETTE_LIST_TEXT_W = 118   # 「목록」 보기 이름 칸 — 넘치면 …로 줄인다(카드 폭을 밀지 않게)
# [패널 통일 2라운드 2026-10-11] 왼쪽 카드 폭 — 예전 240px에서 20% 줄임("작업영역이 쾌적하게", 사용자 요청).
_LEFT_PANEL_W = 192

# [§8 항목34, 2026-10-03] '내 심볼' 검색 — 이름 일부(대소문자 무시) 또는 한글 초성("ㅇㅌ" → "안테나").
# 초성과 글자를 섞어 써도 된다("안ㅌ"). 사용자 결정: 이름만(폴더 이름은 검색 대상 아님).
_CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def _symbol_name_matches(name: str, query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    n = name.lower()
    if q in n:
        return True

    def same(qc, nc):
        if qc == nc:
            return True
        if qc in _CHOSEONG and "가" <= nc <= "힣":
            return _CHOSEONG[(ord(nc) - 0xAC00) // 588] == qc
        return False

    return any(all(same(qc, n[i + k]) for k, qc in enumerate(q))
               for i in range(len(n) - len(q) + 1))

# [실사용 피드백 2026-10-11] 폴더마다 처음 보이는 심볼 수 — 폴더 칸 아래 손잡이로 폴더마다 바꿀 수 있고
# (`symfolder_rows_<폴더>` 설정), 넘치는 것은 「더 보기 (+N)」 → 크게 보기 패널.
_FOLDER_ROWS_DEFAULT = 6


_PALETTE_FONT_SHRINK = 1   # pt만큼 기본 폰트에서 뺀다 — [2026-08-12 5차] 2→1, 너무 작다는 피드백
# [2026-08-12 6차] 폰트를 키운 뒤 버튼 높이(40)가 실제 sizeHint(48)보다 작아 라벨 아래가
# 잘렸다 — 고정 크기가 자연 sizeHint 밑으로 내려가면 항상 이 클래스 버그가 재발하므로,
# 폭만 고정하고 높이는 버튼이 실제로 요구하는 sizeHint를 그대로 쓴다(아래 _palette_button).




class _UIBuildMixin:
    def _make_action(self, text, icon, slot, shortcut=None, checkable=False,
                      shortcut_id=None, display_only=False):
        """[Phase 6 M1] 메뉴·상단 툴바가 공유할 QAction 하나를 만든다(아이콘 포함).
        상단 QToolBar는 이 액션을 setDefaultAction으로 재사용 → 상태(체크 등) 자동 동기화.

        [단축키 설정, 2026-08-21] `shortcut_id`를 주면 `shortcuts.py` 레지스트리가 단축키의
        유일한 출처가 된다(`shortcut` 인자 무시) — 초기값은 QSettings 저장값(설정 창에서
        재할당했으면 그 값, 없으면 기본값)이고, `self._shortcut_actions[shortcut_id] = a`로
        등록해 설정 창이 나중에 라이브 갱신할 수 있게 한다. 툴팁에도 현재 단축키를 붙여
        (호버 요청) 재할당 후에도 항상 최신값을 보여준다.

        `display_only=True`면 실제 `QAction.setShortcut()`은 절대 안 건다 — 되돌리기/
        다시 실행처럼 진짜 키 처리는 뷰의 `keyPressEvent`가 하는 항목(위 편집(&E) 메뉴
        생성부 주석 참조: QAction에 같은 단축키를 걸면 Qt 전역 단축키가 뷰보다 먼저
        가로채 이중 실행 위험이 생긴다). 툴팁만 레지스트리 값을 따라간다."""
        a = QAction(text, self)
        if icon:
            a.setIcon(_act_icon(icon))
            self._icon_actions.append((a, icon))   # 테마 전환 시 아이콘 재생성용 등록
        if shortcut_id is not None:
            self._shortcut_actions[shortcut_id] = a
            if display_only:
                self._shortcut_display_only.add(shortcut_id)
            self._apply_action_shortcut(shortcut_id)
        elif shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if checkable:
            a.setCheckable(True)
        a.triggered.connect(slot)
        return a


    def refresh_shortcut_ui(self):
        """[단축키 설정, 2026-08-21] 설정 창이 저장한 뒤 호출 — 메뉴/툴바 QAction 전부
        (`_apply_action_shortcut`) + 상단 툴바 도구 버튼 툴팁 + 도구(&T) 메뉴 표시 텍스트를
        전부 레지스트리 현재값으로 다시 그린다. 대상이 넓어 보이지만 다 가벼운 텍스트/
        QKeySequence 갱신뿐이라 매번 다시 계산해도 무해(설정 저장은 드문 이벤트)."""
        for sid in self._shortcut_actions:
            self._apply_action_shortcut(sid)
        for key, name, sc in _TOOLS:
            if key in ("rect", "ellipse", "sarrow"):
                continue
            sid = shortcuts.SHORTCUT_ID_BY_TOOL.get(key)
            live_sc = shortcuts.current_sequence(sid) if sid else sc
            btn = self._tool_buttons.get(key)
            if btn is not None:
                tip = f"화살표 ({live_sc} — 그린 뒤 속성 패널에서 종류 변경)" \
                    if key == "arrow" else f"{name} ({live_sc})"
                btn.setToolTip(tip)
            act = self._tool_menu_actions.get(key)
            if act is not None:
                act.setText(f"{name}\t{live_sc}" if live_sc else name)


    def _apply_action_shortcut(self, shortcut_id: str):
        """[단축키 설정, 2026-08-21] `shortcut_id`의 현재 QSettings 값(또는 기본값)을
        해당 QAction에 반영(`display_only` 등록이면 툴팁만) + 툴팁을 "{텍스트} ({단축키})"
        로 갱신(호버 요청). 설정 창이 저장할 때마다 바뀐 id들에 대해 이걸 다시 부른다."""
        a = self._shortcut_actions.get(shortcut_id)
        if a is None:
            return
        seq_str = shortcuts.current_sequence(shortcut_id)
        seq = QKeySequence(seq_str)
        if shortcut_id not in self._shortcut_display_only:
            a.setShortcut(seq)
        base_text = a.text().split("\t")[0]
        if seq.isEmpty():
            a.setToolTip(base_text)
        else:
            a.setToolTip(f"{base_text} ({seq.toString(QKeySequence.SequenceFormat.NativeText)})")


    def _build_menu(self):
        self._doc_path = None
        self._icon_actions: list[tuple[QAction, str]] = []   # (액션, 아이콘이름) — 테마 재생성용
        self._shortcut_actions: dict[str, QAction] = {}   # [단축키 설정] id → QAction
        self._shortcut_display_only: set = set()   # [단축키 설정] setShortcut() 안 거는 id들
        m = self.menuBar().addMenu("파일(&F)")

        # [실사용 피드백 2026-08-26] 탭 도입 이후 실제 동작이 "새 탭 열기"라 이름도 그에
        # 맞춤(예전 "새로 만들기"는 탭 이전 시절 명칭이 남아있던 것).
        self._act_new = self._make_action("새 탭", "new", self._new_doc,
                                          shortcut_id="new_doc")
        self._act_open = self._make_action("열기…", "open", self._open_doc,
                                           shortcut_id="open_doc")
        self._act_save = self._make_action("저장…", "save", self._save_doc,
                                           shortcut_id="save_doc")
        # [§8 항목10 Stage C] 빠른저장(Ctrl+S, 위 _act_save)과 별개로 항상 다이얼로그를
        # 띄우는 경로 — 저장 경로를 바꾸고 싶을 때.
        self._act_save_as = self._make_action(
            "다른 이름으로 저장…", "save", self._save_doc_as,
            shortcut_id="save_doc_as")
        # [§8 항목10 Stage D] 새 탭(위 "새 탭", Ctrl+N)과 별개 — 여긴 완전히 독립된 새 최상위 창.
        self._act_new_window = self._make_action(
            "새 창", "new", self._new_window, shortcut_id="new_window")
        # [2026-08-20 피드백] "새 창"은 "새 탭"과 같은 성격(새 시작)이라 저장 계열
        # (열기·저장·다른 이름으로 저장) 앞, 바로 아래에 둔다.
        for a in (self._act_new, self._act_new_window, self._act_open, self._act_save,
                  self._act_save_as):
            m.addAction(a)
        # [§8 항목32, 2026-10-03] 최근 연 파일 — 열 때마다 다시 채움(host_fileio._fill_recent_menu)
        self._recent_menu = m.addMenu("최근 파일")
        self._recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()

        # [§8 항목14, 2026-08-07] 옛 "전체"/"선택영역" 별도 메뉴 2개를 1개로 통합 —
        # 전체/선택 선택지는 _PdfExportDialog 안의 라디오로 이동(옵션+라이브 미리보기).
        # [신규기능] DXF 가져오기/내보내기 통합 — 옛 전용 메뉴·단축키(Ctrl+Shift+D/I)는
        # 폐지하고 열기(Ctrl+O)/저장(Ctrl+S)이 확장자로 분기(아래 _open_doc/_save_doc).
        # [내보내기 단일화, 2026-08-24 실사용 피드백] "내보내기" 하위메뉴로 PDF/PNG/SVG
        # 3개를 나란히 뒀던 것을 다시 걷어냄 — 다이얼로그 안 「형식」 콤보
        # (host_dialogs.py `_FORMAT_OPTIONS`)가 이미 같은 4종을 고르게 하므로 진입점에서
        # 형식을 미리 고르는 하위메뉴는 순수 중복 UI였다. 항목 하나(_export_pdf, 기본
        # pdf·전체 도면)가 다이얼로그를 열고, 형식·범위는 그 안에서 바꾼다. Ctrl+P·툴바
        # 버튼도 이 액션 하나를 그대로 공유.
        self._act_pdf = self._make_action("내보내기…", "pdf", self._export_pdf,
                                          shortcut_id="export_pdf")
        m.addAction(self._act_pdf)
        # [§8 항목42, 2026-10-16] 엔지니어가 아닌 직원의 출구 — 도면(또는 선택)을 그림으로 클립보드에, 한글·PPT에 Ctrl+V.
        self._act_copy_img = self._make_action("그림으로 복사(한글·PPT)", "copy_image", self._copy_as_image,
                                               shortcut_id="copy_image")
        m.addAction(self._act_copy_img)
        # [§8 항목46, 2026-10-16] 받는 사람은 앱이 없어도 되는 공유 — 브라우저로 여는 HTML 한 파일.
        self._act_share_html = self._make_action("HTML로 공유…", "menu_export", self._share_html)
        m.addAction(self._act_share_html)
        # [§8 항목47, 2026-10-16] 같은 페이지 + KAIROS가 쓴 단계별 설명(단계마다 그 상자 강조) — 교육·발표·대회 시연용.
        self._act_explain_page = self._make_action("설명 페이지 만들기(KAIROS)…", "generate", self._make_explain_page)
        m.addAction(self._act_explain_page)

        # 편집(상단 툴바와 액션 공유. Ctrl+Z/Ctrl+Y 키는 여전히 뷰가 직접 처리하므로 QAction엔
        # 단축키를 안 건다 — 여기에 같은 단축키를 걸면 Qt 전역 단축키가 뷰의 keyPressEvent보다
        # 먼저 가로챌 수 있어 이중 실행 위험이 생긴다(무해해 보여도 검증 안 된 변경, 규칙 8).
        # [2026-08-13 재피드백] 예전엔 이 셋이 툴바 전용으로 의도돼 있었으나("메뉴엔 없던
        # undo/redo"), 표준 메뉴 관례(File→Edit→Insert→View)를 따라 "편집(&E)" 메뉴로도
        # 노출하기로 재확정.
        self._act_undo = self._make_action("되돌리기", "undo", self.undo,
                                           shortcut_id="undo", display_only=True)
        self._act_redo = self._make_action("다시 실행", "redo", self.redo,
                                           shortcut_id="redo", display_only=True)
        # [M2] 도구 고정 — 켜면 도형을 그려도 도구가 유지(연속 그리기), 끄면 one-shot(그리면 선택모드).
        self._act_pin = self._make_action("도구 고정", "pin", self._toggle_pin, checkable=True)
        self._act_pin.setToolTip("도구 고정 — 켜면 연속으로 그리기(끄면 하나 그린 뒤 선택모드)")
        e = self.menuBar().addMenu("편집(&E)")
        for a in (self._act_undo, self._act_redo, self._act_pin):
            e.addAction(a)
        e.addSeparator()
        # [단축키 설정, 2026-08-21] 단축키 재할당 창 진입점.
        self._act_shortcut_settings = self._make_action(
            "단축키 설정…", None, self._show_shortcut_settings)
        e.addAction(self._act_shortcut_settings)

        # [2026-08-12 재피드백] "파일" 메뉴가 파일 I/O(새로만들기·열기·저장·내보내기)와
        # 문서에 콘텐츠를 끼워넣는 "삽입" 계열(표제란·표·Mermaid)이 섞여 있어 분리 —
        # 새 "삽입(&I)" 메뉴로 옮긴다. AI 게이트웨이 설정은 이 메뉴 맨 아래 항목과 「AI로 만들기」
        # 패널 안에서 연다(옛 Mermaid 창 안 버튼은 §8 항목36 6단계에서 창과 함께 사라짐).
        i = self.menuBar().addMenu("삽입(&I)")
        self._act_tb = self._make_action("표제란 / 용지틀 삽입…", "titleblock",
            self._insert_titleblock, shortcut_id="insert_titleblock")
        self._act_tbl = self._make_action("표 삽입…", "table",
            self._insert_table, shortcut_id="insert_table")
        for a in (self._act_tb, self._act_tbl):
            i.addAction(a)
        i.addSeparator()   # [2026-08-13] 위 2개(문서 내장 요소) vs 아래 2개(외부 소스 가져오기) 구분
        # [2026-08-13 재피드백] "파일" 메뉴에 있던 이미지/SVG 삽입을 여기로 이동 — 열기와
        # 같은 "파일선택창" 성격이라기보다, Mermaid처럼 "외부 소스를 도면으로 가져온다"는
        # 성격이 더 가깝다는 재검토로 Mermaid와 같은 그룹에 둔다(§8-8용 벡터 vs 참고용
        # 래스터는 내부에서 확장자로 갈라 각자의 기존 경로로 보낸다 — 로직 무변경, 메뉴
        # 위치만 이동).
        self._act_img = self._make_action("이미지/SVG 삽입…", "image",
            self._insert_image_or_svg, shortcut_id="insert_image")
        # [§8 항목36 6단계, 2026-10-11] 옛 Mermaid·AI SVG·사진→도면 창은 지웠다 — 세 항목과 그 단축키
        # (id는 재사용 금지 규칙대로 그대로)는 이제 「AI로 만들기」 패널을 그 종류로 연다.
        self._act_mmd = self._make_action("AI 흐름도…", "mermaid",
            self._open_ai_flow, shortcut_id="insert_mermaid")
        self._act_ai_svg = self._make_action("AI 심볼…", "generate",
            self._open_ai_symbol, shortcut_id="insert_ai_svg")
        self._act_photo = self._make_action("AI 베끼기(사진→도면)…", "photo",
            self._open_ai_trace, shortcut_id="insert_photo")
        # [§8 항목36, 2026-10-05] 오른쪽 「AI로 만들기」 패널(켜기/끄기). 상단바엔 이것 하나만.
        self._act_ai_make = self._make_action("KAIROS로 만들기", "generate",   # §8 항목40(2026-10-16)
            self._toggle_ai_panel, checkable=True)
        i.addAction(self._act_img)
        i.addAction(self._act_ai_make)
        for a in (self._act_mmd, self._act_ai_svg, self._act_photo):
            i.addAction(a)
        i.addSeparator()   # [2026-08-20 피드백] 위(가져오기·AI) vs 아래(AI 연결 설정) 구분
        # Mermaid/SVG 창 안의 설정 버튼과 같은 다이얼로그를 독립적으로 여는 진입점 — 그
        # 안에서 열면 해당 창을 그대로 같이 쓴다(호출부는 무변경).
        self._act_ai_settings = self._make_action("KAIROS 연결 설정…", "settings",
            self._open_ai_gateway_settings)
        i.addAction(self._act_ai_settings)

        # ---- 도구(&T) 메뉴 — 상단 그리기 도구 버튼과 같은 목록(메뉴 접근성 부재
        # 실사용 피드백 2026-08-20). 단축키는 표시만 — 실제 처리는 뷰의 키 이벤트가 하므로
        # (`core_view.py`) QAction에 단축키를 걸면 편집(&E)의 undo/redo와 같은 이유로
        # 이중 실행 위험이 생긴다(위 주석 참조). 네모·원·직선화살은 상단 툴바와 동일하게
        # 제외(팔레트가 담당 / 화살표 하나로 통합).
        t = self.menuBar().addMenu("도구(&T)")
        self._tool_menu_actions: dict[str, QAction] = {}
        for key, name, sc in _TOOLS:
            if key in ("rect", "ellipse", "sarrow"):
                continue
            # [단축키 설정, 2026-08-21] 표시 텍스트의 단축키 부분을 레지스트리 현재값으로
            # (재할당 반영) — `_TOOLS`의 `sc`는 매핑 없는 도구용 폴백일 뿐.
            sid = shortcuts.SHORTCUT_ID_BY_TOOL.get(key)
            live_sc = shortcuts.current_sequence(sid) if sid else sc
            act = QAction(f"{name}\t{live_sc}" if live_sc else name, self)
            act.setIcon(_tool_icon(key, _current_icon_color()))
            act.setCheckable(True)
            if key == "arrow":
                act.triggered.connect(lambda _c=False: self.arm_arrow_tool())
            else:
                act.triggered.connect(
                    lambda _c=False, k=key: self.set_tool(None if self.current_tool == k else k))
            t.addAction(act)
            self._tool_menu_actions[key] = act

        # ---- 보기 메뉴 (기준 zoom / 스냅 토글) ----
        v = self.menuBar().addMenu("보기(&V)")
        self._act_zoom100 = self._make_action("100% (1:1)", "zoom_100",
            self._zoom_reset, shortcut_id="zoom_100")
        self._act_fit = self._make_action("전체 맞춤", "zoom_fit",
            self._zoom_fit, shortcut_id="zoom_fit")
        v.addAction(self._act_zoom100)
        v.addAction(self._act_fit)
        v.addSeparator()
        self._act_snap = self._make_action("스냅 (o-snap)", "snap",
            self._toggle_snap, shortcut_id="toggle_snap", checkable=True)
        self._act_snap.setChecked(True)
        self._act_ortho = self._make_action("직교 제약 (Ortho)", "ortho",
            self._toggle_ortho, shortcut_id="toggle_ortho", checkable=True)
        self._act_grid = self._make_action("격자 (Grid Snap)", "grid",
            self._toggle_grid, shortcut_id="toggle_grid", checkable=True)
        self._act_grid.setChecked(False)
        self._act_align = self._make_action("정렬 가이드선", "align",
            self._toggle_align_guides, shortcut_id="toggle_align", checkable=True)
        self._act_align.setChecked(True)
        v.addAction(self._act_snap)
        v.addAction(self._act_ortho)
        v.addAction(self._act_grid)
        v.addAction(self._act_align)
        v.addSeparator()
        self._act_theme = self._make_action("다크/라이트 전환", "theme",
            self._toggle_theme, shortcut_id="toggle_theme")
        v.addAction(self._act_theme)
        # [패널 관련 수정, 2026-08-19] 「패널」 하위메뉴(도형·레이어·속성·미니맵 표시/숨김)는
        # 패널 객체가 아직 없는 이 시점엔 못 만든다(전부 이 메서드보다 나중에 생성됨,
        # __init__ 순서 참조) — 참조만 저장해두고 `_build_panel_menu()`가 모든 패널 생성 후
        # 채운다.
        self._view_menu = v

        # ---- 도움말(&H) — [실사용 요청 2026-08-21] 옛 "단축키 도움말"이 보기(&V) 메뉴에
        # 파묻혀 있던 것을 독립 메뉴로 승격 + 프로그램 정보(버전·문의처) 추가.
        h = self.menuBar().addMenu("도움말(&H)")
        self._act_help = self._make_action("단축키 도움말…", "help",
            self._show_shortcuts, shortcut_id="show_help")
        h.addAction(self._act_help)
        self._act_about = self._make_action("프로그램 정보…", None, self._show_about)
        h.addAction(self._act_about)

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
            # [2026-10-11] 배율은 제목 옆 % 버튼이 보여 준다 — 제목은 「미니맵」만.
            panel._title_lbl.setText("미니맵")
            pct_lbl = getattr(self, "_zoom_pct_lbl", None)
            if pct_lbl is not None:
                pct_lbl.setText(f"{pct}%")
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
    _DOC_FILTER = "Easy CAD 문서 (*.ecad);;DXF 파일 (*.dxf);;DWG 파일 (*.dwg)"
    _OPEN_FILTER = ("지원 파일 (*.ecad *.dxf *.dwg *.pdf);;Easy CAD 문서 (*.ecad);;"
                    "DXF 파일 (*.dxf);;DWG 파일 (*.dwg);;PDF 도면 (*.pdf)")


    def resizeEvent(self, e):
        # [미니맵] 창 크기가 바뀌면 메인 뷰의 보이는 씬 영역도 바뀐다(스크롤·줌 변화가 없어도) —
        # scene.changed를 안 타므로 명시적으로 미니맵 사각형을 갱신.
        super().resizeEvent(e)
        self._refresh_minimap()
        if hasattr(self, "_left_container"):
            self._relayout_left_panel()   # [2026-10-11] 도형·심볼 카드 기본 높이가 창 높이를 따른다
        self._reposition_panels()
        self._fit_view_toggles()


    def showEvent(self, e):
        # [2026-08-12] `_layers_list`(QListWidget)의 `sizeHintForRow()`/geometry는 위젯이
        # 실제로 show() 되기 전까지는 `.height()`를 직접 읽어도 settle 안 되는 Qt 내부 지연
        # 계산이라(오프스크린·실제 창 둘 다 재현), `_build_left_panel()` 생성 시점(창이 아직
        # 안 뜬 상태) 계산은 `setMaximumWidth(200)` 같은 제약을 반영 못 하고 더 넓은 값으로
        # 남는다 — 처음 뜬 직후 한 번 더 읽어 재계산해야 좌측 패널이 처음부터 목표 폭으로
        # 뜬다(안 하면 사용자가 뭔가 다른 상호작용을 해 우연히 relayout이 다시 불릴 때까지
        # 창이 잘못된(더 넓은) 크기로 보임).
        super().showEvent(e)
        _ = self._layers_list.height()
        self._relayout_left_panel()
        self._sync_layers_panel_width()

    # ---- [패널 관련 수정, 2026-08-19] 패널 표시/숨김 메뉴 --------------------

    def _build_panel_menu(self):
        """보기(&V)→「패널」 하위메뉴 — 패널별 체크형 표시/숨김. 우클릭 헤더의 「닫기」
        (`_FloatingPanel._close_panel`)와 짝을 이루는 재오픈 경로. 모든 `_build_*_panel`이
        끝난 뒤(=패널 객체가 다 있는 시점) `CanvasWindow.__init__`이 호출한다.
        ⚠ [실측, 2026-08-19] `act.toggled.connect(lambda checked, p=panel: ...)`처럼 QAction의
        시그널을 "다른 QObject(panel)를 캡처한 람다"에 연결하면, 창을 반복 생성만 하고 닫지
        않는(`w.close()`를 안 부르는 기존 테스트 다수의) pytest 스모크에서 재현되는 비결정적
        네이티브 크래시를 유발했다(faulthandler로도 잡히지 않는 액세스 위반, 5회 실측 재현 후
        이 연결 하나만 지우면 사라짐을 이분 제거로 확인). 원인 후보는 QAction·panel이 둘 다
        같은 창의 C++ 자식인데 그 사이를 파이썬 람다 클로저가 또 참조해 파이썬 GC 사이클
        수집과 Qt의 C++ 자식 파괴 순서가 서로 다른 시점에 얽히는 것 — 이 코드베이스가 이미
        수백 곳에서 쓰는 "바운드 메서드를 직접 connect"(`_make_action`의 `a.triggered.
        connect(slot)` 관례, 클로저 없음)로 바꿔 회피한다: `sender()`로 발신 액션/패널을
        역조회해 QObject를 클로저에 담지 않는다."""
        menu = self._view_menu.addMenu("패널")
        self._panel_visibility_actions = {}
        self._panel_action_targets: dict[QAction, _FloatingPanel] = {}
        specs = (
            ("shapes", "도형 패널", self._left_panel),
            ("layers", "레이어 패널", self._layers_panel),
            ("props", "속성 패널", self._props_panel),
            ("minimap", "미니맵 패널", self._minimap_panel),
        )
        for key, label, panel in specs:
            act = QAction(label, self)
            act.setCheckable(True)
            # ⚠ `panel.isVisible()`가 아니라 `isHidden()`의 부정 — 이 시점(`__init__` 도중,
            # 최상위 창이 아직 `.show()`되기 전)엔 조상 체인이 안 보여 `isVisible()`이 항상
            # False라 초기 체크상태가 전부 꺼진 것처럼 잘못 뜬다. `isHidden()`은 "이 위젯이
            # 명시적으로 hide()됐는가"만 보므로 창 표시 여부와 무관하게 정확하다.
            act.setChecked(not panel.isHidden())
            self._panel_action_targets[act] = panel
            act.toggled.connect(self._on_panel_action_toggled)
            panel.visibility_changed.connect(self._on_panel_visibility_changed)
            menu.addAction(act)
            self._panel_visibility_actions[key] = act

    def _on_panel_action_toggled(self, checked: bool):
        act = self.sender()
        panel = self._panel_action_targets.get(act)
        if panel is not None:
            panel.set_panel_visible(checked)

    def _on_panel_visibility_changed(self, visible: bool):
        # 우클릭 「닫기」가 만든 상태변화를 메뉴 체크상태로 반영. `panel.set_panel_visible`이
        # 이미 `visible`을 결정해 보내므로 여기선 그 값을 그대로 반영만 한다(재질의 없음).
        panel = self.sender()
        for act, p in self._panel_action_targets.items():
            if p is panel:
                self._sync_panel_action(act, visible)
                break

    def _sync_panel_action(self, act: QAction, visible: bool):
        # 「닫기」가 만든 상태변화를 메뉴 체크상태로 반영 — act.toggled가 이미
        # `set_panel_visible`을 부른 경우(메뉴 클릭 자체)엔 이미 일치하므로 무한루프 없음.
        if act.isChecked() != visible:
            act.blockSignals(True)
            act.setChecked(visible)
            act.blockSignals(False)

    # ---- [캔버스-퍼스트] 플로팅 패널·토스트 위치 계산 -------------------------

    def _reposition_panels(self):
        """좌상단=도형, 좌하단=레이어, 우상단=속성(편집 클러스터). 우하단=미니맵(탐색 클러스터
        — 지도 + 제목에 표기된 줌%, 한 카드 — 줌 배지는 독립 위젯이 아니라 미니맵 패널 제목
        자체다, `_build_minimap_panel`/`_update_zoom_label` 참조). [2026-08-01 폭 통일] 미니맵
        폭을 속성 패널 폭에, [2026-08-19] 레이어 패널 폭을 도형 패널 폭에 맞춰 매 호출마다
        동기화 — 나란한 패널 폭이 어긋나 튀어 보이던 문제(사용자 지적)를 "따라간다"로 해소.
        선택 상태에 따라 속성 패널 폭이 미세하게 바뀌어도 계속 맞음. 전부 `self._view`가
        차지하는 실제 캔버스 영역(메뉴·상단툴바 아래) 기준 — `self._view.mapTo(self, ...)`
        좌표 관례. 닫힌(숨김) 패널도 그대로 위치·크기 계산은 하되 화면엔 안 그려진다(재오픈 시
        곧바로 제자리) — `isVisible()` 분기를 넣지 않는 편이 훨씬 단순하고 숨김 상태에서
        move()/adjustSize()는 부작용이 없다."""
        panels = (getattr(self, "_left_panel", None), getattr(self, "_layers_panel", None),
                  getattr(self, "_props_panel", None), getattr(self, "_minimap_panel", None))
        if any(p is None for p in panels):
            return   # 초기화 중 조기 호출 가드
        left_panel, layers_panel, props_panel, minimap_panel = panels
        m = self._PANEL_MARGIN
        vx, vy = self._view.mapTo(self, QPoint(0, 0)).x(), self._view.mapTo(self, QPoint(0, 0)).y()
        vw, vh = self._view.width(), self._view.height()

        left_panel.adjustSize()
        left_panel.move(vx + m, vy + m)
        left_panel.raise_()

        layers_panel.adjustSize()
        layers_panel.move(vx + m, vy + vh - m - layers_panel.height())
        layers_panel.raise_()

        props_panel.adjustSize()
        props_panel.move(vx + vw - m - props_panel.width(), vy + m)
        props_panel.raise_()

        if getattr(self, "_start_prompt", None) is not None:
            self._place_start_prompt()   # §8 항목39 가운데 입구 — 뷰 가운데

        # [2026-10-11] 폴더 크게 보기 — 도형·심볼 카드 오른쪽, 왼쪽 세로 공간(카드 위 ~ 레이어 카드 아래) 전체 높이
        browser = getattr(self, "_symbol_browser", None)
        if browser is not None:
            bx = left_panel.x() + left_panel.width() + m
            bw = max(browser.MIN_W, min(browser.panel_w, vx + vw - m - bx))
            browser.setFixedSize(bw, max(200, vh - 2 * m))
            browser.move(bx, vy + m)
            browser.raise_()

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

    # [첫 화면 재디자인 2026-10-07, 시안 2라운드 T3] 상단바 버튼 밑에 붙는 짧은 이름 — 메뉴 글자
    # (`text()`)는 그대로 두고 `iconText`만 바꾼다. 그리기 도구(액션 없는 QToolButton)도 여기서.
    _TOOLBAR_LABELS = {
        "new": "새로", "open": "열기", "save": "저장", "pdf": "PDF", "copy_image": "그림 복사",
        "undo": "되돌리기", "redo": "다시", "titleblock": "표제란", "table": "표", "image": "이미지",
        "select": "선택", "arrow": "화살표", "text": "글자", "line": "선", "polygon": "다각형",
        "pen": "펜", "badge": "번호", "trim": "Trim", "pin": "고정",
    }
    # [실사용 피드백 2026-10-11 후속] 「자르기」 → 「Trim」(사용자 선택) — 늘이기(Extend)도 하는 도구라 "자르기"로는 다 설명이 안 되고
    # AutoCAD 명령 이름이라 익숙하다. 상단바 이름만 바꾸고 메뉴·툴팁(`_TOOLS`)은 「자르기」 그대로(뜻 풀이 역할).

    def _build_toolbar(self):
        # 파이썬에서 만든다 — `addToolBar("이름")`이 C++에서 만든 툴바는 아래 paintEvent 덮어쓰기가 안 먹는다(묶음 바탕용)
        tb = QToolBar("주 도구모음", self)
        self.addToolBar(tb)
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        # [첫 화면 재디자인 2026-10-07, 시안 2라운드 T3 채택] 아이콘만(T1)은 "알아보기 힘듦",
        # 한 줄 전부 옆 글자(T2)는 "마우스 이동이 너무 넓음"으로 탈락 — 아이콘 밑에 짧은 이름.
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        lbl = self._TOOLBAR_LABELS
        for a, key in ((self._act_new, "new"), (self._act_open, "open"), (self._act_save, "save"),
                       (self._act_pdf, "pdf"), (self._act_copy_img, "copy_image"),
                       (self._act_undo, "undo"), (self._act_redo, "redo"),
                       (self._act_tb, "titleblock"), (self._act_tbl, "table"),
                       (self._act_img, "image"), (self._act_pin, "pin")):
            a.setIconText(lbl[key])

        # [2026-08-13 재개편, 사용자 요청 "모든 메뉴 항목을 상단바에도"] 옛 결정(내보내기·삽입
        # 계열은 아이콘만으론 구분 어려워 상단바에서 제거)을 뒤집는다 — 각 액션 생성 시 이미
        # 붙은 툴팁으로 구분을 보완하고, 메뉴별 그룹을 구분선으로 나눠 정리한다. 순서는
        # File→Edit→Insert→(그리기 도구)→View — 편집(&E) 메뉴를 메뉴관례로 재확정한
        # 2026-08-13 결정과 동일한 순서. 그리기 도구는 메뉴가 없는 캔버스 전용 묶음이라
        # Insert 다음, View 앞에 그대로 둔다.

        # 파일(&F)
        for a in (self._act_new, self._act_open, self._act_save, self._act_pdf, self._act_copy_img):
            tb.addAction(a)
        tb.addSeparator()

        # 편집(&E)
        for a in (self._act_undo, self._act_redo):
            tb.addAction(a)
        self._refresh_history_actions()   # undo/redo 버튼 초기 활성 상태(둘 다 비어 disabled)
        tb.addSeparator()

        # 삽입(&I)
        # [§8 항목36] AI 생성 아이콘 세 개(Mermaid·SVG·사진→도면) → 「AI로 만들기」 하나(패널 켜기/끄기).
        # [첫 화면 재디자인 2026-10-07] 그 「AI로 만들기」는 강조 버튼으로 보기 토글 뒤에 따로 둔다.
        for a in (self._act_tb, self._act_tbl, self._act_img):
            tb.addAction(a)
        tb.addSeparator()

        # 그리기 도구(체크형, 메뉴 없음 — 캔버스 전용) — 네모·원은 왼쪽 「도형」 팔레트로
        # 이관(단축키 2·5는 유지). [화살표 통합] 직선화살(sarrow) 버튼 제거 — 화살표 버튼
        # 하나가 종류(직선·곡선·직각)를 대표한다. [미니패널 통합, 2026-07-31] 상단바 클릭 시
        # 종류를 고르는 메뉴(InstantPopup)는 폐지 — 클릭은 항상 현재 sticky 종류(기본 직각)로
        # 바로 무장/해제하고, 종류 변경은 그린 뒤 속성 dock의 「화살표」 행에서 한다(사용자
        # 피드백: 그리기 전 선택지가 하나 더 있는 게 번거로움, 이미 dock에 같은 메뉴가 있어 중복).
        self._tool_buttons: dict[str, QToolButton] = {}
        for key, name, sc in _TOOLS:
            if key in ("rect", "ellipse", "sarrow"):
                continue
            btn = QToolButton()
            btn.setIcon(_tool_icon(key, _current_icon_color()))
            btn.setIconSize(QSize(20, 20))
            btn.setText(lbl[key])
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            # [단축키 설정, 2026-08-21] 레지스트리 현재값으로(재할당 반영) — `_TOOLS`의
            # `sc`는 매핑 없는 도구용 폴백일 뿐.
            sid = shortcuts.SHORTCUT_ID_BY_TOOL.get(key)
            live_sc = shortcuts.current_sequence(sid) if sid else sc
            tip = f"화살표 ({live_sc} — 그린 뒤 속성 패널에서 종류 변경)" \
                if key == "arrow" else f"{name} ({live_sc})"
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
        # [실사용 요청 2026-08-25] "도구 고정"은 undo/redo(히스토리 조작)와 무관한, 그리기
        # 도구 자체의 동작 모드(연속 그리기 on/off) 토글이라 도구 묶음 옆이 의미상 맞다 —
        # 옛 위치(편집 그룹, undo/redo 옆)에서 이리 옮긴다. 메뉴(편집(&E)) 쪽 위치는 그대로
        # (기능별 분류라 문제 없음, 툴바만 시각적 근접성이 문제였다).
        tb.addAction(self._act_pin)
        tb.addSeparator()

        # 보기(&V) — [첫 화면 재디자인 2026-10-07] 「100%」「전체 보기」는 상단바에서 빼고 미니맵
        # 카드의 확대 줄로 옮긴다(사용자 결정, 보기 메뉴·단축키는 그대로). 스냅·직교·격자·정렬선은
        # 「체크박스+글자」 2×2 묶음 — 2026-09-25에 아이콘 전용으로 되돌렸던 것을 시안 2라운드 T3
        # 채택으로 다시 뒤집음(상단바 전체에 글자가 붙으니 아이콘만 남은 묶음이 오히려 안 읽힘).
        # 액션은 보기 메뉴가 계속 쓰므로 별도 버튼을 잇고 상태는 항상 액션이 원본(`_sync_view_toggle`).
        # [실사용 피드백 2026-10-11] 체크박스 대신 뜻 아이콘 + 코랄 바탕으로 바꿨다가
        # [2026-10-12] "선택됐다는 느낌이 애매함" — 체크박스로 되돌리고 꺼진 것은 글자·체크를 흐리게(시안 A).
        # 창이 좁으면 아이콘만(`_fit_view_toggles`).
        # ⚠ 툴바 직속이 아니라 묶음 위젯의 자식이라 `QToolBar`가 iconSize를 20으로 덮어쓰는
        # 함정(pitfalls 「setIconSize 무시」)을 밟지 않는다.
        toggles = QWidget()
        grid = QGridLayout(toggles)
        grid.setContentsMargins(2, 0, 2, 0); grid.setHorizontalSpacing(2); grid.setVerticalSpacing(0)
        self._view_toggle_buttons: dict[QAction, QToolButton] = {}
        for i, (a, label, icon) in enumerate(((self._act_snap, "스냅", "snap"), (self._act_ortho, "직교", "ortho"),
                                              (self._act_grid, "격자", "grid"), (self._act_align, "정렬선", "align"))):
            btn = QToolButton()
            btn.setText(label)
            btn._icon_name = icon
            btn.setIconSize(QSize(16, 16))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setProperty("viewToggle", True)   # 툴바 QSS의 여백·글자 규칙용(_apply_theme)
            btn.clicked.connect(lambda _c=False, a=a: a.trigger())
            a.changed.connect(lambda a=a, b=btn: self._sync_view_toggle(a, b))   # 체크·툴팁(단축키 재할당)
            grid.addWidget(btn, i // 2, i % 2)   # 윗줄 스냅·직교, 아랫줄 격자·정렬선(시안 T3 순서)
            self._view_toggle_buttons[a] = btn
            self._sync_view_toggle(a, btn)
        tb.addWidget(toggles)
        tb.addSeparator()
        # 「AI로 만들기」는 강조 버튼(시안 1라운드 D·2라운드 T3에서 호평) — 아이콘 옆 글자.
        tb.addAction(self._act_ai_make)
        ai_btn = tb.widgetForAction(self._act_ai_make)
        ai_btn.setObjectName("aiMakeBtn")
        ai_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # [실사용 피드백 2026-10-11, 시안 A2] 혼자 너무 커서 글자만 「AI」로 줄인다(강조 모양은 그대로).
        # 메뉴·툴팁은 「KAIROS로 만들기」라 무엇인지는 알 수 있다(§8 항목40 — 상단바 글자는 10-11 결정대로 짧게 유지).
        self._act_ai_make.setIconText("AI")

        # 우측 정렬 스페이서 → 테마 → 도움말 (여백이 있을 때만 밀어냄 — 좁은 창에서는 그냥 이어짐).
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self._act_theme)
        tb.addAction(self._act_help)
        for a in (self._act_theme, self._act_help):   # 오른쪽 끝 둘은 아이콘만(시안 그대로)
            tb.widgetForAction(a).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._toolbar = tb
        # [실사용 피드백 2026-10-11, 시안 T3 채택] 세로 구분선 대신 묶음(파일·편집·삽입·그리기·보기)마다 옅은 바탕.
        # QToolBar엔 "버튼 묶음 바탕"이 없어 툴바를 그린 뒤 구분선 사이 버튼들의 범위를 둥근 사각으로 칠한다.
        # ⚠ 반드시 None을 돌려주는 함수로 — 람다로 튜플을 돌려주면 PyQt6가 가상 함수 결과 오류로 앱을 강제 종료한다(실측 exit 127).
        def _tb_paint(e, tb=tb):
            QToolBar.paintEvent(tb, e)
            try:
                self._paint_toolbar_groups(tb)
            except RuntimeError:   # 창이 닫히는 중(지워진 위젯) — 가상 함수 예외는 앱 강제 종료라 삼킨다
                pass
        tb.paintEvent = _tb_paint

    def _toolbar_group_rects(self, tb) -> list:
        """구분선으로 나뉜 묶음마다 보이는 버튼들을 감싸는 사각(툴바 좌표). 마지막 구분선 뒤(AI·테마·도움말)는 제외."""
        groups, cur = [], []
        for a in tb.actions():
            if a.isSeparator():
                groups.append(cur); cur = []
                continue
            w = tb.widgetForAction(a)
            if w is not None and w.isVisible():
                cur.append(w.geometry())
        rects = []
        for g in groups:
            if g:
                r = g[0]
                for q in g[1:]:
                    r = r.united(q)
                r = r.adjusted(-3, 0, 3, 0)
                rects.append(QRect(r.left(), max(r.top(), 3), r.width(), min(r.bottom(), tb.height() - 4) - max(r.top(), 3) + 1))
        return rects

    def _paint_toolbar_groups(self, tb):
        p = QPainter(tb)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 13) if getattr(self, "_dark", True) else QColor(0, 0, 0, 11))
        for r in self._toolbar_group_rects(tb):
            p.drawRoundedRect(QRectF(r), 8, 8)
        p.end()

    def _sync_view_toggle(self, act: QAction, btn: QToolButton):
        """보기 토글 버튼을 액션 상태에 맞춘다 — 체크박스 아이콘·툴팁, 꺼지면 체크·글자를 흐리게(`viewOff`)."""
        on = act.isChecked()
        btn.setToolTip(f"{btn.text()} — {act.toolTip()}")
        color = (_current_icon_color() if on
                 else QApplication.palette().color(QPalette.ColorRole.PlaceholderText))
        btn.setIcon(_svg_icon("check_on" if on else "check_off", 16, color))
        if btn.property("viewOff") != (not on):
            btn.setProperty("viewOff", not on)
            btn.style().unpolish(btn); btn.style().polish(btn)   # 동적 속성 QSS는 다시 칠해야 반영

    def _fit_view_toggles(self):
        """[실사용 피드백 2026-10-11] 창이 좁아 상단바가 다 안 들어가면 보기 토글 넷은 아이콘만(이름은 툴팁에)."""
        btns = list(getattr(self, "_view_toggle_buttons", {}).values())
        tb = getattr(self, "_toolbar", None)
        if not btns or tb is None:
            return
        beside = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        if getattr(self, "_toolbar_full_w", None) is None and btns[0].toolButtonStyle() == beside:
            self._toolbar_full_w = tb.sizeHint().width()
        style = (Qt.ToolButtonStyle.ToolButtonIconOnly
                 if self.width() < (self._toolbar_full_w or 0) else beside)
        for b in btns:
            if b.toolButtonStyle() != style:
                b.setToolButtonStyle(style)

    # ---- 테마 (다크 기본 + 라이트 토글) -------------------------------------

    @staticmethod
    def _palette_accent_qss(dark: bool) -> str:
        """[실사용 버그 수정 2026-08-19] 팔레트 버튼 스타일(미선택=투명 테두리만·선택=코랄
        틴트)을 `_apply_theme`의 `btn_qss`에서 뽑아낸 것 — 커스텀 심볼 버튼(§8-8)이 이
        스타일을 못 받아 Qt 기본 테마의 raised 배경 박스로 남던 버그를 고치려면
        `_refresh_custom_symbol_section`(버튼을 매번 새로 만드는 곳)에서도 같은 문자열이
        필요해서다. `_apply_theme`가 항상 갖고 있는 `dark`만 받으면 되므로 static으로 뺐다."""
        hover_bg = "rgba(255,255,255,22)" if dark else "rgba(0,0,0,18)"
        strong_checked_bg = "rgba(218,119,86,150)"
        return (
            "QToolButton { border:1px solid transparent; border-radius:6px; padding:3px; }"
            "QToolButton:checked { background:rgba(218,119,86,35); }"
            f"QToolButton#toolStrongCheck:checked {{ background:{strong_checked_bg};"
            " border-color:#da7756; }"
            f"QToolButton:hover {{ background:{hover_bg}; }}"
            f"QToolButton:pressed {{ background:{strong_checked_bg}; border-color:#da7756; }}"
        )

    def _apply_theme(self, dark: bool, persist: bool = False):
        """[Phase 6 M1] 다크/라이트 일괄 적용 — 팔레트(Fusion)·캔버스 배경·아이콘 색.
        아이콘은 baked QPixmap이라 테마색이 바뀌면 액션·팔레트 아이콘을 재생성한다.
        persist=True일 때만 QSettings에 저장(테스트가 사용자 설정을 덮지 않도록 분리)."""
        was_dark = getattr(self, "_dark", dark)   # [실사용 피드백 2026-08-26] 아래 도형 반전용
        self._dark = dark
        key = "dark" if dark else "light"
        # [실사용 피드백 2026-08-18] 기본 도형 색이 아직 사용자가 안 건드린 상태(sticky
        # 미변경)면 새 테마의 잉크색으로 따라간다 — 직접 고른 색은 `_color_is_default`가
        # False라 여기 안 걸리고 그대로 유지(host_style._set_current_color 참조).
        if getattr(self, "_color_is_default", False):
            self.current_color = QColor(_DEFAULT_INK_DARK if dark else _DEFAULT_INK_LIGHT)
        _set_icon_color(dark)   # host_widgets._ICON_COLOR 갱신(host_widgets._act_icon()이 읽는 실제 전역)
        _set_menu_sep_color(dark)   # host_widgets._MENU_SEP_COLOR 갱신 — 각 QMenu 생성 시점에 읽음
        app = QApplication.instance()
        if app is not None:
            # [2026-08-12] 이미 Fusion이면 재적용하지 않는다 — `setStyle()`은 그 순간 살아있는
            # 위젯 전부를 새 스타일로 재polish하는 무거운 전역 연산이고, 매 `CanvasWindow()`
            # 생성마다(테마 무관하게) 무조건 호출되고 있었다. 평소엔 안 보이다가, 왼쪽 패널
            # 아코디언 개편으로 창당 위젯 수가 늘고 나서 스모크 스위트(수백 개 창을 닫지 않고
            # 누적 생성)의 후반부에서 Windows access violation으로 재현됨 — `faulthandler`로
            # 잡은 크래시 지점이 정확히 이 줄이었다(중복 호출 자체가 원인, 아코디언 코드는
            # 무관 — 그저 위젯 수를 늘려 기존에 잠재해 있던 재현 조건을 앞당겼을 뿐).
            if app.style().objectName().lower() != "fusion":
                app.setStyle("Fusion")   # 두 테마 모두 Fusion — 팔레트가 전 위젯에 안정 반영
            # [2026-08-02 버그 수정] 예전엔 라이트에 `app.style().standardPalette()`를 썼는데,
            # 이 Qt6/Windows 조합은 OS 다크모드를 따라 Fusion "표준" 팔레트 자체가 다크로
            # 나온다(`styleHints().colorScheme()`가 Dark) — 라이트 토글이 캔버스만 하얘지고
            # 패널·버튼·제목/토스트 텍스트는 다크 색 그대로 남아 안 보이던 원인. `_dark_palette()`처럼
            # 고정 색 팔레트(`_light_palette()`)로 OS 설정과 무관하게 만들어 해결.
            app.setPalette(_dark_palette() if dark else _light_palette())
        for pop in self.findChildren(_PropPopup):   # [2026-10-11] 별도 창이라 앱 팔레트가 안 내려온다(실측)
            pop._follow_app_palette()
        # [§8 항목10 실사용 버그 수정, 2026-08-18] self._scene(활성 탭만)이 아니라 열려 있는
        # 모든 탭의 씬을 칠한다 — 안 그러면 배경 탭들은 테마를 토글해도 여전히 예전 색으로
        # 남는다(활성 탭에서 토글해도 다른 탭까지 정상화되어야 함). _apply_theme가 처음 불릴
        # 때(__init__ 끝)는 이미 self._docs가 채워진 뒤라 폴백 없이 안전.
        for _doc in self._docs:
            _doc.scene.setBackgroundBrush(QBrush(_CANVAS_BG[key]))
        # [실사용 피드백 2026-08-26] 다크→라이트(또는 반대)로 실제 전환될 때, 이미 그려둔
        # 도형 중 "그 순간 테마의 기본 잉크색 그대로"인 것만 새 테마 기본색으로 반전한다 —
        # 그리는 순간 색이 박제되는 기존 설계(위 731~732줄) 탓에 다크에서 그린 흰 도형이
        # 라이트 배경에서 안 보이던 문제(미니맵도 같은 씬을 그리므로 동시에 해결). 사용자가
        # 직접 고른 색(기본값과 다른 값)은 조건에 안 걸려 그대로 유지된다. 기본색 "값" 자체는
        # 안 바꾸므로 PDF 내보내기의 "흰색→검정" 임계값 매칭과도 안 부딪힌다(2026-08-18에
        # 기본색 자체를 회색빛으로 바꿨다가 그 매칭이 깨졌던 것과는 다른 접근).
        if was_dark != dark:
            old_ink = QColor(_DEFAULT_INK_DARK if was_dark else _DEFAULT_INK_LIGHT).name()
            new_ink = QColor(_DEFAULT_INK_DARK if dark else _DEFAULT_INK_LIGHT).name()
            for _doc in self._docs:
                for _it in _doc.scene.items():
                    if not hasattr(_it, "apply_color"):
                        continue
                    _cur = self._read_props(_it).get("color")
                    if _cur is not None and _cur.name().lower() == old_ink.lower():
                        _it.apply_color(QColor(new_ink))
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
        for k, b in getattr(self, "_fav_palette_buttons", {}).items():   # 「즐겨찾기」의 기본 도형 칸
            hit = getattr(self, "_basic_palette_entries", {}).get(k)
            if hit is not None:
                b.setIcon(self._shape_icon(hit[1]))
        for k, b in getattr(self, "_tool_buttons", {}).items():
            b.setIcon(_tool_icon(k, _current_icon_color()))
        for k, a in getattr(self, "_tool_menu_actions", {}).items():
            a.setIcon(_tool_icon(k, _current_icon_color()))
        # [2026-08-13 피드백] 패널 접기 화살표(코랄→중립색 전환)도 아이콘과 같은 전역색을
        # 쓰므로 테마 전환마다 재도색 — `_apply_theme`가 호출되는 시점(위 386~388줄)엔
        # `_build_left_panel`/`_build_properties_panel`/`_build_minimap_panel`이 이미 끝나
        # 있어(host.py __init__ 순서) 항상 존재함이 보장된다.
        # [UI 검토 2026-09-25] 레이어 패널(2026-08-19 분리)이 이 목록에서 빠져 있어 그 접기
        # 화살표만 테마 전환 후에도 옛 색으로 남았다(다크에서 흐려 비활성처럼 보임).
        for panel in (getattr(self, "_left_panel", None), getattr(self, "_props_panel", None),
                      getattr(self, "_minimap_panel", None), getattr(self, "_layers_panel", None)):
            if panel is not None:
                panel._refresh_collapse_color()
        self._refresh_layer_icons()
        # [2026-10-11] 섹션·폴더 접기 ▾ 버튼은 없앴다(제목을 눌러 접음) — 남은 건 폴더 ⋯ 버튼.
        self._restyle_palette_boxes()
        for btn in getattr(self, "_symfolder_collapse_btns", []) + getattr(self, "_section_more_btns", []):
            btn.setStyleSheet(
                f"QToolButton {{ color: {_current_icon_color().name()}; font-size: 13px; }}")
        # [2026-10-11] 패널 버튼 아이콘(새 폴더·더 보기·레이어 버튼)도 테마 아이콘 색으로 다시
        for btn in [getattr(self, "_add_folder_btn", None), getattr(self, "_layer_add_btn", None),
                    getattr(self, "_layer_move_btn", None)] + getattr(self, "_folder_more_btns", []):
            if btn is not None and getattr(btn, "_icon_name", None):
                btn.setIcon(_menu_icon(btn._icon_name, faint=getattr(btn, "_faint", False)))
        browser = getattr(self, "_symbol_browser", None)
        if browser is not None:
            browser.restyle()
            if browser.isVisible():
                browser.refresh()   # 열려 있을 때만 칸 다시(심볼 그림이 테마 잉크색)
        # [실사용 피드백 2026-08-26] '내 심볼' 팔레트 아이콘은 등록 당시 테마 잉크색으로
        # 박제된 정지 이미지라(캔버스 도형과 달리 QGraphicsItem이 아니라 반영 안 됨) —
        # 저장된 레시피(items)로 재렌더하는 기존 자동치유 경로(`_ensure_symbol_thumb_
        # current`)를 재사용해 아이콘만 바꿔치기한다. `_refresh_custom_symbol_section()`
        # 전체 재구성(위젯 삭제·재생성)은 여기서 매번 부르면 안 된다 — 스모크 스위트처럼
        # 창을 안 닫고 대량 생성하는 환경에서 위젯 재구축을 반복하면 과거(2026-08-12)
        # 겪었던 것과 같은 계열의 네이티브 크래시를 재현시킨다(실측 확인, 이 커밋에서
        # 처음엔 전체 재구성을 불렀다가 스모크 스위트가 중간에 죽어 발견).
        custom_sym_buttons = getattr(self, "_custom_sym_buttons", None)
        if custom_sym_buttons:
            entries_by_id = {e["id"]: e for e in symbol_library.load_library()}
            for sid, blist in custom_sym_buttons.items():
                entry = entries_by_id.get(sid)
                if entry is None:
                    continue
                fresh = self._ensure_symbol_thumb_current(entry)
                icon = QIcon(_b64_to_pixmap(fresh["thumb"]))
                for btn in blist:
                    btn.setIcon(icon)
        self._refresh_arrow_tool_button()
        # [실사용 피드백 2026-08-20, 아이콘화] 속성패널 '선'·'화살표'·'방향' 아이콘도 중립색
        # baked QPixmap이라 테마 전환마다 재생성해야 한다(위 액션 아이콘들과 같은 이유).
        pf_style = getattr(self, "_pf_style", None)
        if pf_style is not None:
            for i, (st, _name) in enumerate(self._PEN_STYLE_ITEMS):
                pf_style.setItemIcon(i, _pen_style_icon(
                    st, _current_icon_color(), self._PROPS_ICON_W, self._PROPS_ICON_H))
            for b, (st, _name) in zip(getattr(self, "_pf_style_btns", []), self._PEN_STYLE_ITEMS):
                b.setIcon(_pen_style_icon(st, _current_icon_color(), 26, 10))
        pf_routing = getattr(self, "_pf_routing_btn", None)
        if pf_routing is not None:
            for i, (kind, _label) in enumerate(_ARROW_KIND_LABELS):
                pf_routing.setItemIcon(i, _arrow_kind_icon(
                    kind, _current_icon_color(), self._PROPS_ICON_W, self._PROPS_ARROW_ICON_H))
        # [첫 화면 재디자인 2026-10-07, 시안 P2] 선 모양·굵기 버튼 — 켜진 것만 옅은 면+테두리. 스핀박스와
        # 같은 폼 안이라 패널 전체가 아니라 버튼마다 따로 건다(속성 패널 스핀박스 sizeHint 함정, 위 주석).
        seg_line, seg_on, seg_ring = (("#3a4450", "#3d4856", "#cdd8e3") if dark
                                      else ("#c9d3dc", "#dfe5eb", "#39434f"))
        seg_qss = (f"QToolButton {{ border:1px solid {seg_line}; border-radius:4px; background:transparent; }}"
                   f"QToolButton:checked {{ background:{seg_on}; border-color:{seg_ring}; }}")
        for b in (list(getattr(self, "_pf_style_btns", []))
                  + list(getattr(self, "_pf_width_presets", {}).values())
                  + [getattr(self, n) for n in ("_pf_color_btn", "_pf_style_btn", "_pf_width_btn", "_pf_fill_btn")
                     if hasattr(self, n)]):
            b.setStyleSheet(seg_qss)
        if hasattr(self, "_zoom_fit_btn"):   # [2026-10-11] 미니맵 제목 줄의 확대 버튼은 테두리 없이, 아이콘만 다시 칠함
            self._zoom_fit_btn.setIcon(_svg_icon("zoom_fit", 14, _current_icon_color()))
        # 견본 첫 칸(기본 잉크색)과 고리 색이 테마를 따르므로 선택 중이면 속성 카드를 다시 채운다.
        if getattr(self, "_pf_color_presets", None) and getattr(self, "_props_form", None) is not None:
            self._refresh_properties()
        pf_dir = getattr(self, "_pf_dir_btn", None)
        if pf_dir is not None:
            pf_dir.setIcon(_flip_icon(_current_icon_color()))
        # [실사용 피드백 2026-08-26] '화살촉' 콤보만 위 재도색 목록에서 빠져 있어 테마 전환
        # 시 만들 때 색 그대로 흐리게 남던 버그 — 같은 관례로 추가.
        pf_head = getattr(self, "_pf_head_btn", None)
        if pf_head is not None:
            for i, (kind, _label) in enumerate(_ARROW_HEAD_LABELS):
                pf_head.setItemIcon(i, _arrow_head_icon(
                    kind, _current_icon_color(), self._PROPS_ICON_W, self._PROPS_ARROW_ICON_H))
        # [캔버스-퍼스트] 플로팅 패널 제목줄 = accent 밑줄 + 틴트 배경(옛 dock 제목표시줄과 같은
        # '잡아 눈에 띄는 카드' 언어 유지, 자유 드래그는 없지만 접기 버튼이 있는 자리라 여전히
        # 상호작용 영역으로 보여야 함).
        # [디자인 베이크오프 2026-08-02] accent는 코랄(Claude 브랜드톤) 고정, 다크/라이트 공통 —
        # 아이콘이 이미 양쪽 다 코랄로 확정돼(2라운드) 라이트만 블루로 남겨두면 아이콘·강조선
        # 색이 어긋난다(예전엔 "라이트는 스코프 밖"으로 블루 유지했던 결정을 여기서 통일).
        accent = "#da7756"
        title_bg = "#232f3d" if dark else "#e8eef5"   # 토스트 바탕(카드 제목 줄은 2026-10-11부터 띠 없음)
        # [첫 화면 재디자인 2026-10-07] 카드 제목 줄 밑줄은 코랄 대신 옅은 중립선(강조색은 의미 있는 상태에만)
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
            # [실사용 피드백 2026-10-11, 시안 H3] 제목 띠 배경·밑줄 없이 큰 제목 글자(`_FloatingPanel`)로 위계
            "#floatPanelHead { background:transparent; font-weight:600; }"
)
        for panel in (getattr(self, "_left_panel", None), getattr(self, "_props_panel", None),
                      getattr(self, "_minimap_panel", None), getattr(self, "_layers_panel", None),
                      getattr(self, "_ai_panel", None), getattr(self, "_symbol_browser", None)):
            if panel is not None:
                panel._head.setStyleSheet(head_qss)
                panel.update()
        self._panel_head_qss = head_qss   # 나중에 만들어지는 카드(폴더 크게 보기)도 같은 제목 줄
        ai_panel = getattr(self, "_ai_panel", None)
        if ai_panel is not None:
            ai_panel.refresh_theme(dark)
            self._ai_refresh_theme()   # 떠 있는 결과·준비 막대도(host_aimake)
        if getattr(self, "_start_prompt", None) is not None:
            self._start_prompt.refresh_theme(dark)   # §8 항목39 가운데 입구
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
        # [2026-08-02 5차 피드백] "상시 켜짐"(스냅·격자, 기본값 ON)은 옅은 틴트(35)를 유지하되,
        # "순간적으로 켜지는" 것(그리기 도구 무장·핀·직교)은 클릭 순간(pressed)의 진한 코랄을
        # 뗀 뒤에도 고정색으로 유지해 달라는 요청 — objectName 선택자로 두 그룹을 나눈다.
        # `QToolButton#toolStrongCheck:checked`는 CSS 명시도(objectName 선택자 > 타입 선택자)로
        # 일반 `QToolButton:checked` 규칙을 이긴다 — 같은 스타일시트 문자열 안에서 셀렉터
        # 명시도로 가르는 방식이라(각 버튼에 별도 stylesheet를 걸어 조상↔자손 캐스케이드에
        # 기대는 방식보다) 결과가 항상 결정적이다. 이 objectName은 아래에서 대상 위젯에만 부여.
        btn_qss = self._palette_accent_qss(dark)
        toolbar = getattr(self, "_toolbar", None)
        if toolbar is not None:
            # [2026-08-13 피드백] 패널 헤더의 코랄 하단선(위 head_qss)과 같은 언어를 상단
            # 툴바에도 — "이 아래부터 캔버스"를 앱 전체 크롬에 통일.
            # [첫 화면 재디자인 2026-10-07] 코랄 하단선은 뺀다 — 강조색은 "의미 있는 상태"에만
            # (디자인 취향 확정 원칙), 시안 1라운드 A·2라운드 T3 모두 선 없이 채택.
            # 버튼 밑 글자는 11px(시안 T3), 보기 토글 글자는 12.5px·좌우 여백을 글자에 맞춤.
            # 「AI로 만들기」(#aiMakeBtn)만 따뜻한 테두리의 강조 버튼 — checked(패널 켜짐)는 코랄 틴트.
            ai_bg, ai_bd, ai_fg = (("#2a2f36", "#4a3e38", "#f0d9cf") if dark
                                   else ("#fbefe9", "#e3b9a6", "#7a3a22"))
            toolbar.setStyleSheet(
                "QToolBar { border:none; spacing:1px; }"
                # [2026-10-11 시안 T3] 구분선 대신 묶음마다 옅은 바탕(`_paint_toolbar_groups`) — 구분선은 투명한 틈
                "QToolBar::separator { background:transparent; width:12px; }"
                + btn_qss
                + "QToolBar QToolButton { font-size:11px; padding:2px 3px; }"
                + 'QToolButton[viewToggle="true"] { font-size:12.5px; padding:1px 6px 1px 3px; }'
                + f'QToolButton[viewToggle="true"][viewOff="true"] {{ color:{"#6f7883" if dark else "#9aa2ab"}; }}'
                + f"QToolButton#aiMakeBtn {{ font-size:13px; background:{ai_bg};"
                  f" border:1px solid {ai_bd}; border-radius:8px; color:{ai_fg}; padding:6px 12px; }}"
                + "QToolButton#aiMakeBtn:checked { background:rgba(218,119,86,90); }")
            # 순간적 활성 그룹: 그리기 도구 6종(선택/화살표/텍스트/선/펜/번호) + 핀.
            # [2026-10-07] 직교는 이제 체크박스 묶음이라(켜짐을 체크박스가 말함) 강조 대상에서 빠짐.
            _strong_check_widgets = list(getattr(self, "_tool_buttons", {}).values())
            act = getattr(self, "_act_pin", None)
            w = toolbar.widgetForAction(act) if act is not None else None
            if w is not None:
                _strong_check_widgets.append(w)
            for w in _strong_check_widgets:
                w.setObjectName("toolStrongCheck")
        # 보기 토글 체크박스 아이콘도 중립색이라 테마 전환마다 재칠.
        for act, btn in getattr(self, "_view_toggle_buttons", {}).items():
            self._sync_view_toggle(act, btn)
        _accent_btns = (
            list(getattr(self, "_shape_tool_buttons", {}).values())
            + list(getattr(self, "_sym_buttons", {}).values())
            # [실사용 버그 수정 2026-08-19] 커스텀 심볼(§8-8) 버튼이 이 목록에서 빠져 있어
            # 위 btn_qss(미선택=투명 테두리만·선택=코랄 틴트)를 못 받고 Qt 기본 스타일의
            # raised 배경 박스로 남아 있었다 — 일반 도형/심볼 버튼과 시각적으로 달라 보이던
            # 원인. [2026-08-20] 즐겨찾기 이중표시로 sid당 버튼이 여러 개일 수 있어 리스트를
            # 평탄화(flatten)한다.
            + [b for blist in getattr(self, "_custom_sym_buttons", {}).values() for b in blist]
            + list(getattr(self, "_fav_palette_buttons", {}).values())
        )
        # [2026-08-20] _pf_routing_btn은 QToolButton→QComboBox로 바뀌어(아이콘화 통일) 이
        # QToolButton 전용 QSS가 안 먹는다 — _pf_style(원래도 QComboBox)과 같은 취급으로
        # 목록에서 뺐다(적용해도 무해하지만 아무 효과 없는 스타일 적용은 남기지 않음).
        # [UI 검토 2026-09-25] `_pf_color`·`_pf_fill`은 뺐다 — [2026-10-07] 이제 둘은 「…」 버튼이고 견본은
        # `_pf_color_presets`·`_pf_fill_presets`(스타일은 `_sync_props_presets`가 칠함, 아래 테마 끝에서 다시).
        for name in ("_pf_swap_btn", "_pf_dir_btn"):
            b = getattr(self, name, None)
            if b is not None:
                _accent_btns.append(b)
        for b in _accent_btns:
            b.setStyleSheet(btn_qss)
        # [UI 검토 2026-09-25] 탭 닫기 버튼 — Fusion 기본값은 빨간 네모 ✗라 "강조색은 의미
        # 있는 상태에만"(checked·pressed만 코랄) 원칙과 어긋났다. 평소엔 중립 회색 ✗(두 테마
        # 배경 모두 3:1 이상인 #7d8794, SVG에 고정), 호버 때만 도구 버튼과 같은 중립 틴트.
        # 스타일시트는 탭바에만 건다 — 탭 위젯에 걸면 문서 뷰 아래 위젯까지 QStyleSheetStyle로
        # 바뀐다(스핀박스 sizeHint 함정, 위 head_qss 주석 참조).
        close_svg = (_icons_dir() / "tab_close.svg").as_posix()
        close_hover = "rgba(255,255,255,22)" if dark else "rgba(0,0,0,18)"
        self._tabs.tabBar().setStyleSheet(
            f"QTabBar::close-button {{ image: url({close_svg}); subcontrol-position: right;"
            " border-radius:3px; }"
            f"QTabBar::close-button:hover {{ background:{close_hover}; }}")
        toast = getattr(self, "_toast", None)
        if toast is not None:
            toast.setStyleSheet(
                f"#toastLabel {{ background:{title_bg}; border:1px solid {accent};"
                " border-radius:6px; padding:4px 12px; }")
        minimap = getattr(self, "_minimap", None)
        if minimap is not None:
            minimap.viewport().update()   # 씬 배경색(다크/라이트)이 바뀌므로 재도색
        # [2026-08-13 피드백] 프로그램 최상단(OS) 타이틀바가 흰색으로 튄다 — QPalette로는
        # 못 닿는 네이티브 창 프레임이라 Qt 앱 전역 색상 스킴으로 반영(메인 창은 물론, 이후
        # 열리는 모든 다이얼로그의 OS 타이틀바까지 자동 적용 — `_apply_native_titlebar_scheme` 참조).
        _apply_native_titlebar_scheme(dark)
        if persist:
            app_settings().setValue("dark", dark)


    def _toggle_theme(self):
        self._apply_theme(not self._dark, persist=True)
        self.statusBar().showMessage("다크 모드" if self._dark else "라이트 모드", 2500)


    def _show_shortcuts(self):
        """[Phase 6 M1] 상단바에서 뺀 단축키 안내를 도움말 다이얼로그로.
        [단축키 설정, 2026-08-21] 마우스 제스처(휠·팬)만 고정 안내로 남기고, 키보드
        단축키는 `shortcuts.SHORTCUT_DEFS`에서 카테고리별로 동적 생성 — 설정 창에서
        재할당하면 이 목록도 항상 최신값을 보여준다(하드코딩 목록이 따로 안 썩는다)."""
        mouse_rows = [
            ("휠", "확대·축소 (커서 기준)"),
            ("Shift + 휠", "선 두께·도형 크기 조절"),
            ("가운데버튼 드래그", "화면 이동(팬)"),
        ]
        lines = [f"{k:<18}{d}" for k, d in mouse_rows]
        last_cat = None
        for sid, cat, label, _default in shortcuts.SHORTCUT_DEFS:
            if cat != last_cat:
                lines.append("")
                lines.append(f"[{cat}]")
                last_cat = cat
            seq = shortcuts.current_sequence(sid) or "(없음)"
            lines.append(f"{seq:<18}{label}")
        lines.append("")
        lines.append("단축키는 편집(&E) → 단축키 설정…에서 바꿀 수 있습니다.")
        body = "\n".join(lines)
        # [실사용 버그 수정 2026-08-21] 예전엔 QMessageBox.setInformativeText였는데, 이 목록이
        # 카테고리 추가마다 계속 늘어나(현재 6개) 작은 화면에서 스크롤 없이 화면 아래로
        # 잘렸다(QMessageBox는 화면 높이를 넘는 내용을 스크롤 지원 안 함). 스크롤 가능한
        # QPlainTextEdit로 교체 — 화면 크기와 무관하게 전체 목록을 볼 수 있다.
        dlg = QDialog(self)
        dlg.setWindowTitle("단축키 도움말")
        lay = QVBoxLayout(dlg)
        title = QLabel("Easy CAD 단축키")
        title.setStyleSheet("font-weight:bold;")
        lay.addWidget(title)
        text = QPlainTextEdit(dlg)
        text.setPlainText(body)
        text.setReadOnly(True)
        text.setFont(QFont("Consolas"))
        lay.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.resize(560, 700)
        dlg.exec()


    def _show_shortcut_settings(self):
        """[단축키 설정, 2026-08-21] 편집(&E) → 단축키 설정… — 재할당 다이얼로그를 열고,
        저장됐으면(Accepted) 메뉴/툴바/도구메뉴 표시를 전부 최신값으로 다시 그린다."""
        from easycad.canvas.host_dialogs import _ShortcutSettingsDialog
        dlg = _ShortcutSettingsDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.refresh_shortcut_ui()


    def _show_about(self):
        """[실사용 요청 2026-08-21] 도움말(&H) → 프로그램 정보 — 버전(`easycad.__version__`)·
        문의처·런타임(Qt/Python) 정도만. 별도 문서·라이선스 화면은 아직 없어 범위 밖."""
        import sys
        from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        from easycad import __version__ as easycad_version
        box = QMessageBox(self)
        box.setWindowTitle("Easy CAD 정보")
        box.setText(f"Easy CAD v{easycad_version}")
        box.setInformativeText(
            "빠르고 쉬운 순서도/간단도면 작성기\n\n"
            f"문의: jjrftech@gmail.com\n\n"
            f"Python {sys.version.split()[0]} · Qt {QT_VERSION_STR} · PyQt {PYQT_VERSION_STR}")
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


    def _palette_button(self, label: str, icon_kind, tooltip: str, tool_key: str,
                         icon_px: int = _PALETTE_ICON_PX, tooltip_html_fn=None) -> QToolButton:
        """icon_kind는 보통 _SYMBOL_KINDS 키 문자열이지만, 커스텀 심볼(§8-8)처럼 미리 만든
        QIcon(썸네일)을 직접 넘길 수도 있다. icon_px는 [실사용 피드백 2026-08-19]로 신설 —
        커스텀 심볼은 `_PALETTE_SYM_ICON_PX`(기본도형보다 큼)를 받는다. tooltip_html_fn은
        같은 피드백의 호버 확대 미리보기 — 매 팔레트 새로고침마다 전 심볼을 미리 렌더하면
        심볼이 많아질수록 비용이 커지므로(사용자가 우려한 바로 그 확장성 문제), 실제 호버가
        일어날 때만 지연 계산한다(`_PaletteButton.event`가 QEvent.ToolTip에서 호출)."""
        # [M3 #17] 클릭=무장 / 드래그=캔버스 드롭 생성. [2026-08-19] drag_*_fn 3개는 씬에
        # 진짜 임시 도형을 만들어 실시간 정렬 스냅을 태우는 경로(host_fileio.py 참조) —
        # False를 돌려주는 tool_key(포트·커스텀심볼)는 preview_fn 기반 네이티브 QDrag로 폴백.
        btn = _PaletteButton(tool_key, preview_fn=self._render_drag_preview,
                              drag_begin_fn=self._palette_drag_begin,
                              drag_move_fn=self._palette_drag_move,
                              drag_end_fn=self._palette_drag_end,
                              tooltip_html_fn=tooltip_html_fn)
        btn._full_name = label
        btn.setAccessibleName(label)
        btn.setIcon(icon_kind if isinstance(icon_kind, QIcon) else self._shape_icon(icon_kind, px=icon_px))
        btn._icon_px = icon_px
        if tooltip_html_fn is None:
            btn.setToolTip(tooltip)
        btn.setCheckable(True)
        # [2026-08-12 3차 피드백] 라벨 폰트도 축소 — QFont로(추후 _apply_theme가 setStyleSheet로
        # checked/hover 배경색을 다시 씌워도 폰트는 별도 채널이라 안 덮임, 스타일시트로 넣으면
        # 그 재적용에 지워질 것).
        f = btn.font(); f.setPointSize(max(1, f.pointSize() - _PALETTE_FONT_SHRINK)); btn.setFont(f)
        self._style_palette_button(btn)
        btn.clicked.connect(
            lambda _c=False, k=tool_key: self._on_palette_click(k))
        # [실사용 피드백 2026-10-11] 기본 도형·즐겨찾기·검색 결과·폴더 어느 칸이든 우클릭 메뉴(즐겨찾기 넣기/빼기,
        # 내 심볼은 이름변경 등도) — `_show_palette_item_menu`가 종류별로 나눈다.
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(
            lambda pos, b=btn, k=tool_key: self._show_palette_item_menu(b, pos, k))
        return btn

    @staticmethod
    def _style_palette_button(btn):
        """[패널 통일 2라운드 2026-10-11, 시안 2-2] 작은 아이콘 옆에 이름 한 줄(넘치면 …). 이름 전체는
        `_full_name`(툴팁·접근성 이름에도). [실사용 피드백 2026-10-11] 이름 없는 「아이콘」 보기는 없앴다
        ("글자가 같이 있는 게 가독성이 좋음") — 큰 그림은 폴더 「크게 보기」 창이 맡는다."""
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setIconSize(QSize(_PALETTE_LIST_ICON_PX, _PALETTE_LIST_ICON_PX))
        btn.setText(btn.fontMetrics().elidedText(btn._full_name, Qt.TextElideMode.ElideRight, _PALETTE_LIST_TEXT_W))
        btn.setMinimumWidth(0); btn.setMaximumWidth(16777215)
        btn.setFixedHeight(26)

    def _on_palette_click(self, key: str):
        self.set_tool(key if self.current_tool != key else None)

    # ---- 「즐겨찾기」(2026-10-11 — 옛 「자주 쓰는 것」 최근 8개 자동을 사용자가 넣고 빼는 목록으로) ----
    def _palette_entry_for(self, key: str):
        """tool_key → (이름, 아이콘 종류 또는 QIcon, 아이콘 px, 툴팁 HTML 함수) — 사라진 심볼이면 None."""
        if key.startswith("customsym:"):
            sid = key[len("customsym:"):]
            entry = next((e for e in symbol_library.load_library() if e.get("id") == sid), None)
            if entry is None:
                return None
            entry = self._ensure_symbol_thumb_current(entry)
            return (entry["name"], QIcon(_b64_to_pixmap(entry["thumb"])), _PALETTE_SYM_ICON_PX,
                    lambda e=entry: self._symbol_preview_html(e))
        hit = self._basic_palette_entries.get(key)
        # 기본 도형 칸과 같은 그림(`_shape_icon` 기본 30px 원본을 칸 크기로 줄임 — 테마 전환 때도 같은 방식)
        return None if hit is None else (hit[0], self._shape_icon(hit[1]), _PALETTE_ICON_PX, None)

    def _refresh_fav_section(self):
        """[실사용 피드백 2026-10-11] 「즐겨찾기」 칸 — `symbol_library.load_favorites()` 순서대로(기본 도형·내 심볼 함께).
        넣기/빼기는 어느 칸이든 우클릭(`_show_palette_item_menu`)."""
        section = getattr(self, "_fav_section", None)
        if section is None:
            return
        keep = self._left_scroll_value()
        lay = section.body_layout
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide(); w.deleteLater()   # 숨김 먼저 — 지연 삭제 전까지 새 칸과 겹쳐 보이지 않게
            elif item.layout() is not None:
                old = item.layout()
                while old.count():
                    wi = old.takeAt(0).widget()
                    if wi is not None:
                        wi.hide(); wi.deleteLater()
        grid = QGridLayout(); grid.setSpacing(0); grid.setContentsMargins(0, 0, 0, 0)
        self._fav_palette_buttons: dict[str, QToolButton] = {}
        n = 0
        for key in symbol_library.load_favorites():
            info = self._palette_entry_for(key)
            if info is None:
                continue
            name, icon, px, tip_fn = info
            btn = self._palette_button(name, icon, name, key, icon_px=px, tooltip_html_fn=tip_fn)
            btn.setStyleSheet(self._palette_accent_qss(self._dark))
            btn.setChecked(self.current_tool == key)
            self._fav_palette_buttons[key] = btn
            grid.addWidget(btn, n, 0)
            n += 1
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        if n == 0:
            hint = self._section_label("도형을 우클릭 → 「즐겨찾기에 넣기」")
            hint.setWordWrap(True)
            lay.addWidget(hint)
        section.set_count(str(n))
        section.updateGeometry()
        if hasattr(self, "_left_container"):
            self._relayout_left_panel_keep_scroll(keep)

    def _show_palette_item_menu(self, btn, pos, key: str):
        """팔레트 칸 우클릭 — 내 심볼은 심볼 메뉴(즐겨찾기·이름변경·SVG·삭제), 기본 도형은 즐겨찾기 넣기/빼기."""
        if key.startswith("customsym:"):
            self._show_custom_symbol_context_menu(btn, pos, key[len("customsym:"):])
            return
        menu = QMenu(self)
        _style_menu_separators(menu)
        self._add_favorite_toggle_action(menu, key)
        menu.exec(btn.mapToGlobal(pos))

    def _add_favorite_toggle_action(self, menu: QMenu, key: str):
        fav = symbol_library.is_favorite(key)
        menu.addAction(_menu_icon("menu_star_off" if fav else "menu_star"),
                       "즐겨찾기에서 빼기" if fav else "즐겨찾기에 넣기",
                       lambda: self._toggle_palette_favorite(key))

    def _toggle_palette_favorite(self, key: str):
        symbol_library.toggle_favorite_key(key)
        self._refresh_fav_section()

    # ---- 스크롤 위치 지키기 ----
    def _left_scroll_value(self) -> int | None:
        sc = getattr(self, "_left_scroll", None)
        return sc.verticalScrollBar().value() if sc is not None else None

    def _relayout_left_panel_keep_scroll(self, value):
        """[실사용 버그 수정 2026-10-11] 목록을 다시 그려도(이름변경·즐겨찾기·이동·색·접기) 스크롤 위치를 그대로 —
        예전엔 다시 그릴 때마다 맨 위로 튀었다. 스크롤 범위는 다음 틱에 정해지는 경우가 있어 그때 한 번 더 맞춘다."""
        self._relayout_left_panel()
        if value is None:
            return
        sb = self._left_scroll.verticalScrollBar()
        # 새로 지은 칸들의 크기가 몇 틱에 걸쳐 자리 잡는 동안 스크롤 범위가 잠깐 짧아져 위치가 깎였다(전체 스위트에서
        # 966 → 882 실측) — 잠깐(0.4초) 동안은 범위가 바뀔 때마다 원래 위치로 다시 맞춘다.
        if getattr(self, "_keep_scroll_timer", None) is None:
            self._keep_scroll_timer = QTimer(self)
            self._keep_scroll_timer.setSingleShot(True)
            self._keep_scroll_timer.timeout.connect(self._end_keep_left_scroll)
            sb.rangeChanged.connect(self._on_left_scroll_range_changed)
        self._pending_left_scroll = value
        self._keep_scroll_timer.start(400)
        sb.setValue(value)
        QTimer.singleShot(0, self._apply_pending_left_scroll)

    def _apply_pending_left_scroll(self):
        value = getattr(self, "_pending_left_scroll", None)
        if value is not None and hasattr(self, "_left_scroll"):
            self._relayout_left_panel()
            self._left_scroll.verticalScrollBar().setValue(value)

    def _on_left_scroll_range_changed(self, _lo, _hi):
        value = getattr(self, "_pending_left_scroll", None)
        if value is not None:
            self._left_scroll.verticalScrollBar().setValue(value)

    def _end_keep_left_scroll(self):
        self._pending_left_scroll = None

    @staticmethod

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        # [UI 검토 2026-09-25] 고정 #888·11px는 라이트 배경에서 대비 3.15:1(작은 글씨 권장
        # 4.5:1 미달)이었다 — 색은 팔레트의 PlaceholderText(테마별 값, 전환 시 자동 반영)로.
        # ⚠ 크기·여백을 스타일시트로 주면 안 된다 — 스타일시트가 걸린 라벨은 앱 팔레트 대신
        # Qt 기본 PlaceholderText(흰색 α128)를 받아 라이트에서 거의 안 보였다(실측).
        f = lbl.font(); f.setPixelSize(12); lbl.setFont(f)
        lbl.setContentsMargins(2, 3, 2, 1)
        lbl.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        return lbl


    def _make_shape_grid(self, entries) -> QGridLayout:
        """[캔버스-퍼스트] 팔레트 버튼 grid 하나 — 아코디언 섹션 바디에 직접 얹는다(제목은
        섹션 헤더가 이미 표시하므로 옛 `_make_shape_section`처럼 내부 라벨을 또 넣지 않음).
        [2026-08-13 피드백] entries마다 저장할 dict를 함께 받는다(기본도형·순서도가 예전엔
        별개 그리드라 3+5로 줄이 안 맞았음 — 8개를 한 그리드에 넣어야 4열×2줄로 고르게
        줄바꿈되면서, "판단"이 자연스레 4번째(첫 줄)로 온다. dict 분리 자체는 `set_tool`
        체크상태 동기화가 참조하므로 유지)."""
        grid = QGridLayout(); grid.setSpacing(2)   # [2026-08-12 3차] 4→2, 패널 폭 축소에 맞춤
        btns = []
        for label, icon_kind, tooltip, tool_key, store in entries:
            btn = self._palette_button(label, icon_kind, tooltip, tool_key)
            store[icon_kind] = btn   # 기본=rect/ellipse, 심볼=kind(=icon_kind)로 키
            btns.append(btn)
        self._shape_sections.append((grid, btns))
        return grid


    def _relayout_sections(self, horiz: bool = False):
        """[캔버스-퍼스트] 각 섹션 그리드를 한 줄에 하나로 배치(2026-10-11 아이콘 보기 폐지 — 그 전엔 여러 열,
        패널 폭의 절반이 빈 공간으로 남던 문제 수정). `horiz` 인자는 옛 dock 상/하 재도킹 시
        한 줄로 눕히던 반응형 레이아웃의 흔적(플로팅 패널은 위치 고정이라 대상 없음) — 항상
        False로만 호출되지만, 초기 빌드 호출부(`_build_left_panel`)와의 계약을 그대로 둔다."""
        for grid, btns in self._shape_sections:
            for b in btns:
                grid.removeWidget(b)
            cols = len(btns) if horiz else 1
            grid.setSpacing(0 if cols == 1 else 1)
            for i, b in enumerate(btns):
                grid.addWidget(b, i // cols, i % cols)
            # 스트레치 초기화 후 실제 열 다음 빈 열에만 1 → 넓어져도 버튼은 좌측 정렬 유지.
            for ci in range(len(btns) + 2):
                grid.setColumnStretch(ci, 0)
            grid.setColumnStretch(cols, 1)


    def _refresh_custom_symbol_section(self):
        """[신규기능 §8-8, 폴더 지원 2026-08-12 → 2026-08-19 폴더별 접기 재개편] '내 심볼'
        섹션을 라이브러리 파일(심볼+폴더) 기준으로 다시 그린다 — 등록/삭제/폴더 생성·삭제·
        이동 직후 호출. 폴더마다 독립 `_SymbolFolderDropZone`(드롭하면 그 폴더로 이동) + 그
        안에 한 줄에 하나씩 버튼. 빈 폴더도 드롭 대상으로 남아야 하므로 숨기지 않는다.
        [실사용 피드백 2026-10-11] 미분류 칸 없음(심볼은 늘 폴더에 — `symbol_library._default_folder`),
        즐겨찾기는 카드 위쪽 「즐겨찾기」 칸 하나로(폴더 안 이중표시 없음), 폴더마다 처음 몇 개만 보이고
        나머지는 「더 보기」, 「＋ 새 폴더」는 마지막 폴더 아래, 다시 그려도 스크롤 위치 유지."""
        keep = self._left_scroll_value()
        body = self._custom_sym_body
        while body.layout().count():
            item = body.layout().takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide(); w.deleteLater()

        entries = symbol_library.load_library()
        folders = symbol_library.load_folders()
        search = getattr(self, "_custom_sym_search", None)
        query = search.text().strip() if search is not None else ""
        self._custom_sym_buttons: dict[str, list[QToolButton]] = {}
        self._symfolder_collapse_btns: list[QToolButton] = []   # `_apply_theme` 재도색용
        self._palette_folder_boxes: list = []                   # (상자, 색) — `_restyle_palette_boxes`
        self._folder_more_btns: list[QToolButton] = []          # 「더 보기」 — `_apply_theme` 아이콘
        self._add_folder_btn = None
        colors = self._symbol_folder_colors(folders)

        def make_symbol_button(entry):
            # [실사용 버그 수정 2026-08-19] 2026-08-19 이전에 등록된 심볼의 옛 흐린
            # 썸네일을 재등록 없이 자동 치유(host_selection._ensure_symbol_thumb_current).
            entry = self._ensure_symbol_thumb_current(entry)
            sid = entry["id"]
            # [실사용 피드백 2026-08-19] 정적 tooltip 대신 호버 시에만 계산되는 확대 미리보기.
            btn = self._palette_button(
                entry["name"], QIcon(_b64_to_pixmap(entry["thumb"])), entry["name"], f"customsym:{sid}",
                icon_px=_PALETTE_SYM_ICON_PX,
                tooltip_html_fn=lambda e=entry: self._symbol_preview_html(e))
            # [실사용 버그 수정 2026-08-19] 버튼을 매번 새로 만드므로 만든 즉시 같은 스타일을 건다.
            btn.setStyleSheet(self._palette_accent_qss(self._dark))
            btn.setChecked(self.current_tool == f"customsym:{sid}")
            self._custom_sym_buttons.setdefault(sid, []).append(btn)
            return btn

        def fill_grid(sec, btns):
            grid = QGridLayout(); grid.setSpacing(0)
            # [실사용 버그 수정 2026-08-19] 그리드 여백 0 — 기본 여백이 패널 폭을 흔들었다.
            grid.setContentsMargins(0, 0, 0, 0)
            for i, bt in enumerate(btns):
                grid.addWidget(bt, i, 0)
            grid.setColumnStretch(1, 1)
            sec.body_layout.addLayout(grid)

        if query:
            # [패널 통일 2라운드 2026-10-11, 시안 2-3] 검색 결과는 폴더로 나누지 않고 한 줄 목록 — 기본 도형과
            # 심볼을 함께, 줄 오른쪽에 어느 폴더인지 흐린 글자(이름으로 찾는 중이라 이름이 보여야 한다).
            # 2026-10-03 "검색 중에도 폴더 유지"를 사용자 결정으로 바꿈.
            hits = [(v[0], k) for k, v in self._basic_palette_entries.items()
                    if _symbol_name_matches(v[0], query)]
            sym_hits = [e for e in entries if _symbol_name_matches(e["name"], query)]
            if not hits and not sym_hits:
                none_lbl = self._section_label("일치하는 도형·심볼 없음")
                body.layout().addWidget(none_lbl)
                zones = [none_lbl]
            else:
                sec = _StaticSection("검색 결과")
                sec.set_count(str(len(hits) + len(sym_hits)))
                sec.body_layout.setSpacing(0)
                self._palette_folder_boxes.append((sec, None))
                self._search_result_buttons: dict[str, QToolButton] = {}
                rows = []
                for name, key in hits:
                    kind = self._basic_palette_entries[key][1]
                    bt = self._palette_button(name, kind, name, key)
                    bt.setStyleSheet(self._palette_accent_qss(self._dark))
                    bt.setChecked(self.current_tool == key)
                    self._search_result_buttons[key] = bt
                    rows.append((bt, "기본 도형"))
                for e in sym_hits:
                    rows.append((make_symbol_button(e), e.get("folder") or ""))
                for bt, where in rows:
                    # 오른쪽 폴더 이름 자리만큼 이름을 더 짧게 줄인다 — 안 그러면 줄이 카드 밖으로 밀렸다(실측)
                    bt.setText(bt.fontMetrics().elidedText(bt._full_name, Qt.TextElideMode.ElideRight, 92))
                    row = QHBoxLayout(); row.setContentsMargins(0, 0, 2, 0); row.setSpacing(4)
                    row.addWidget(bt)
                    row.addStretch(1)
                    tag = QLabel()
                    tf = tag.font(); tf.setPixelSize(10); tag.setFont(tf)
                    tag.setText(tag.fontMetrics().elidedText(where, Qt.TextElideMode.ElideRight, 48))
                    tag.setForegroundRole(QPalette.ColorRole.PlaceholderText)
                    tag.setMaximumWidth(56)
                    tag.setToolTip(where)
                    row.addWidget(tag)
                    sec.body_layout.addLayout(row)
                body.layout().addWidget(sec)
                zones = [sec]
        else:
            self._search_result_buttons = {}

            def add_group(folder_name):
                group_entries = [e for e in entries if e.get("folder") == folder_name]
                zone = _SymbolFolderDropZone(folder_name, self._move_custom_symbol)
                zv = QVBoxLayout(zone)
                zv.setContentsMargins(0, 0, 0, 0); zv.setSpacing(0)
                # [패널 통일 2라운드 2026-10-11, 시안 C] 폴더 = 색 점 + 그 색으로 옅게 물든 테두리 칸 + 개수,
                # ⋯(색·이름변경·삭제)는 마우스를 올렸을 때만, 「크게 보기」 ⤢는 늘(옛 접기 ▾ 자리 — 2026-10-11).
                sec = _StaticSection(folder_name)
                sec.set_count(str(len(group_entries)))
                sec._is_folder = True   # 제목 앞 폴더 그림 대상(같은 목록의 「검색 결과」 칸은 제외)
                self._palette_folder_boxes.append((sec, colors.get(folder_name)))
                # [실사용 피드백 2026-08-19 재개편] 폴더 이름 우클릭 메뉴(탐색기 관례)는 그대로.
                sec._title_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                sec._title_lbl.customContextMenuRequested.connect(
                    lambda pos, n=folder_name, w=sec._title_lbl:
                        self._show_symbol_folder_context_menu(w, pos, n))
                collapse_key = f"symfolder_collapsed_{folder_name}"

                def on_toggle(collapsed, key=collapse_key, zone=zone):
                    app_settings().setValue(key, collapsed)
                    # [실사용 버그 수정 2026-08-19] 위젯 경계마다 updateGeometry — 하나라도 빠지면
                    # 두 번째 접기부터 패널이 줄지 않고 부풀어 보였다(실측).
                    zone.updateGeometry()
                    self._custom_sym_body.updateGeometry()
                    self._custom_sym_section.updateGeometry()
                    self._relayout_left_panel()
                sec.make_collapsible(app_settings().value(collapse_key, False, type=bool), on_toggle)
                if group_entries:
                    # [실사용 피드백 2026-10-11] 「크게 보기」는 ⋯ 메뉴 밖, 제목 줄 오른쪽 끝에 늘 흐리게(유일한 진입로라
                    # 찾기 쉽게). 같은 버튼을 다시 누르면 닫힌다. 빈 폴더엔 없음.
                    big = QToolButton()
                    big._icon_name, big._faint = "menu_expand", True
                    big.setIcon(_menu_icon(big._icon_name, faint=True))
                    big.setIconSize(QSize(13, 13))
                    big.setAutoRaise(True)
                    big.setFixedSize(QSize(18, 16))
                    big.setToolTip(f"「{folder_name}」 크게 보기")
                    big.clicked.connect(lambda _c=False, f=folder_name: self._open_symbol_browser(f, toggle=True))
                    sec.add_tail_button(big)
                    self._folder_more_btns.append(big)
                more = QToolButton()
                more.setText("⋯"); more.setAutoRaise(True)
                more.setFixedSize(QSize(18, 16))
                more.setToolTip("폴더 메뉴 — 색·이름변경·삭제")
                more.setStyleSheet(
                    f"QToolButton {{ color: {_current_icon_color().name()}; font-size: 13px; }}")
                more.clicked.connect(lambda _c=False, n=folder_name, w=more:
                                     self._show_symbol_folder_context_menu(w, QPoint(0, w.height()), n))
                sec.add_hover_button(more)
                self._symfolder_collapse_btns.append(more)
                btns = [make_symbol_button(e) for e in group_entries]
                fill_grid(sec, btns)
                if len(btns) > 1:
                    self._add_folder_rows_control(sec, zone, folder_name, btns)
                zv.addWidget(sec)
                body.layout().addWidget(zone)
                return zone

            # [실사용 버그 수정 2026-08-25] 빈 폴더에 첫 심볼을 등록하면 라벨이 잘리던 버그 — 새로 지은
            # zone + body + section 세 겹 모두 updateGeometry를 걸어야 한다(아래).
            zones = [add_group(name) for name in folders]
            # [실사용 피드백 2026-10-11] 「＋ 새 폴더」는 마지막 폴더 아래(레이어 카드의 「새로」와 같은 자리 규칙) —
            # 예전 카드 제목 줄의 ＋는 "너무 위에 있음".
            add_btn = QPushButton()   # [2026-10-12] QToolButton은 아이콘 옆 글자를 늘 왼쪽에 붙여 가운데 정렬이 안 된다
            add_btn._icon_name = "menu_plus"
            add_btn.setIcon(_menu_icon(add_btn._icon_name))
            add_btn.setText("새 폴더")
            # [실사용 피드백 2026-10-11 후속] 테두리 없는 납작 버튼(autoRaise)은 목록 한 줄처럼 보여 "버튼처럼 안 보임" —
            # 레이어 카드의 「Layer」·「선택 옮기기」와 같은 테두리 버튼, 같은 아이콘 크기.
            # [2026-10-12] 카드 폭 가득 + 점선 테두리 + 가운데 「＋ 새 폴더」(점선 = "여기에 새로 추가", 폴더 칸 실선과 구분).
            # 글자는 남긴다 — ＋만이면 이 카드에선 폴더 추가인지 심볼 추가인지 헷갈린다.
            add_btn.setIconSize(QSize(14, 14))
            add_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            add_btn.setObjectName("addFolderBtn")
            add_btn.setToolTip("새 폴더 만들기")
            add_btn.clicked.connect(self._prompt_create_symbol_folder)
            self._add_folder_btn = add_btn
            body.layout().addWidget(add_btn)
            zones.append(add_btn)
        self._restyle_palette_boxes()
        for z in zones:
            if z is not None:
                z.updateGeometry()
        self._custom_sym_body.layout().invalidate()
        self._custom_sym_body.layout().activate()
        self._custom_sym_body.updateGeometry()
        self._custom_sym_section.layout().invalidate()
        self._custom_sym_section.layout().activate()
        self._custom_sym_section.updateGeometry()
        # 실측: 위 invalidate()들만으론 부족하다 — `_relayout_left_panel()`을 한 번 부르면
        # `_left_container`가 custom_sym_section의 새 sizeHint까지는 읽어내지만, 그 커진 값이
        # `_left_panel` 자신의 크기(adjustSize())까지 반영되려면 그 사이에 `updateGeometry()`가
        # 예약해 둔(비동기) `LayoutRequest`가 실제로 한 번 처리돼야 한다(네 겹 중첩 — 이 파일의
        # `_toggle_folder`가 겪은 세 겹 캐싱 함정과 같은 종류인데 한 단 더 깊다). 그래서 두 번째
        # 호출 전에 이벤트루프를 한 틱 돌려야 한다 — 단순 반복 호출만으론 안 됨을 실측으로 확인.
        # [2026-08-25 Phase 1 재수정] 이 틱을 `QApplication.processEvents()`로 동기 재진입시키면
        # 함수 맨 위 clear 루프가 예약한 `deleteLater()`까지 같은 재진입 안에서 처리되며 힙
        # 손상 abort(pytest exit 127, 실측 재현·격리 확인)를 유발한다 — 재진입 없이 다음
        # 이벤트루프 틱으로 미루는 `QTimer.singleShot(0, ...)`로 교체(동일 효과, 재진입 없음).
        # [2026-10-11] 그 다음 틱 재계산은 `_relayout_left_panel_keep_scroll`이 스크롤 위치 복원과 함께 한다.
        if hasattr(self, "_fav_palette_buttons"):   # 심볼 이름변경·삭제를 「즐겨찾기」에도
            self._refresh_fav_section()
        self._relayout_left_panel_keep_scroll(keep if keep is not None else 0)
        browser = getattr(self, "_symbol_browser", None)
        if browser is not None and browser.isVisible():
            browser.refresh()

    def _add_folder_rows_control(self, sec, zone, folder: str, btns: list):
        """[실사용 피드백 2026-10-11] 폴더 칸 — 처음 n개만(기본 `_FOLDER_ROWS_DEFAULT`), 나머지는 「더 보기 (+N)」
        (→ 크게 보기 패널). 칸 맨 아래 손잡이를 위아래로 끌면 n이 한 줄씩 바뀌고 폴더마다 기억, 더블클릭하면 기본값.
        끝까지 끌면 전부 보이고 「더 보기」는 사라진다. 손잡이와 카드 높이 손잡이는 자리가 다르다(이건 칸 안쪽)."""
        key = f"symfolder_rows_{folder}"
        more = QToolButton()
        more._icon_name = "menu_expand"
        more.setIcon(_menu_icon(more._icon_name))
        more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        more.setAutoRaise(True)
        more.setIconSize(QSize(14, 14))
        more.setToolTip(f"「{folder}」 폴더를 크게 보기")
        more.clicked.connect(lambda _c=False, f=folder: self._open_symbol_browser(f))
        self._folder_more_btns.append(more)
        sec.body_layout.addWidget(more)
        state = {"n": app_settings().value(key, _FOLDER_ROWS_DEFAULT, type=int), "n0": 0}
        step = max(1, btns[0].height())   # 줄 높이(목록 칸은 고정 높이)

        def apply(n, relayout=True):
            n = max(1, min(len(btns), n))
            state["n"] = n
            for i, b in enumerate(btns):
                b.setVisible(i < n)
            hidden = len(btns) - n
            more.setText(f"더 보기 (+{hidden})")
            more.setVisible(hidden > 0)
            if relayout:
                for w in (sec, zone, self._custom_sym_body, self._custom_sym_section):
                    w.updateGeometry()
                self._relayout_left_panel()

        def on_press():
            state["n0"] = state["n"]

        def on_move(dy):
            n = max(1, min(len(btns), state["n0"] + round(dy / step)))
            if n != state["n"]:
                apply(n)

        def on_release():
            app_settings().setValue(key, state["n"])

        def on_reset():
            app_settings().remove(key)
            apply(_FOLDER_ROWS_DEFAULT)

        grip = _DragGrip(f"끌어서 처음 보이는 개수 조절 · 더블클릭하면 {_FOLDER_ROWS_DEFAULT}개로",
                         on_press, on_move, on_release, on_reset, height=7)
        sec.body_layout.addWidget(grip)
        apply(state["n"], relayout=False)

    def _open_symbol_browser(self, folder: str, toggle: bool = False):
        """폴더 「크게 보기」 패널(도형·심볼 카드 오른쪽) — 하나만 두고 다른 폴더면 그 폴더로 바꾼다.
        toggle=True(폴더 제목 줄 ⤢)면 같은 폴더가 이미 열려 있을 때 닫는다."""
        browser = getattr(self, "_symbol_browser", None)
        if browser is not None and toggle and browser.isVisible() and browser.folder == folder:
            browser.hide()
            return
        if browser is None:
            browser = _SymbolFolderBrowser(
                self, folder, lambda f: [e for e in symbol_library.load_library() if e.get("folder") == f],
                self._make_browser_button, default_w=_LEFT_PANEL_W)   # 너비 = 도형·심볼 카드와 같게
            self._symbol_browser = browser
            browser._head.setStyleSheet(getattr(self, "_panel_head_qss", ""))
        else:
            browser.set_folder(folder)
        browser.show()
        self._reposition_panels()

    def _make_browser_button(self, entry, w: int, h: int):
        entry = self._ensure_symbol_thumb_current(entry)
        key = f"customsym:{entry['id']}"
        btn = self._palette_button(entry["name"], QIcon(_b64_to_pixmap(self._symbol_big_thumb_b64(entry, w, h))),
                                   entry["name"], key, icon_px=_PALETTE_SYM_ICON_PX,
                                   tooltip_html_fn=lambda e=entry: self._symbol_preview_html(e))
        btn.setStyleSheet(self._palette_accent_qss(self._dark))
        btn.setChecked(self.current_tool == key)
        return btn


    # [패널 통일 2라운드 2026-10-11, 시안 C] 폴더 색 — 사용자가 ⋯ 메뉴로 고른 색. 처음엔 안 고른 폴더에 기본색 7개를 돌려
    # 칠했고(뜻 없는 무지개), 2026-10-12 오전엔 중립(띠 없음), 같은 날 오후 아래 기본색(회색)으로.
    # [실사용 피드백 2026-10-12] 안 고른 칸의 기본 — 폴더는 회색 띠, 「기본 도형」은 연한 파랑(둘 다 제목 줄 색 목록에 있는 색).
    # 파일엔 저장하지 않고 그릴 때만 쓴다(기본을 바꾸면 안 고른 칸이 모두 따라오게).
    _FOLDER_BASE_COLOR = _SECTION_COLOR_SWATCHES[0]
    _BASIC_BASE_COLOR = _SECTION_COLOR_SWATCHES[5]

    @staticmethod
    def _section_icon_color(color: QColor, dark: bool) -> QColor:
        """제목 앞 그림 색 — 띠는 연한색 그대로, 그림은 라이트 테마에서 한 단계 진하게(연한 파랑·회색 그림이 묻혔다, 실측)."""
        return QColor(color) if dark else QColor(color).darker(150)

    def _symbol_folder_colors(self, folders=None) -> dict:
        folders = symbol_library.load_folders() if folders is None else folders
        chosen = symbol_library.load_folder_colors()
        out = {}
        for name in folders:   # 고른 색, 없으면 기본 회색(2026-10-12 — 그 전엔 None=띠 없음)
            c = QColor(chosen[name]) if chosen.get(name) else None
            out[name] = c if c is not None and c.isValid() else QColor(self._FOLDER_BASE_COLOR)
        return out

    def _restyle_palette_boxes(self):
        """도형·심볼 카드의 테두리 칸들을 지금 테마로 다시 칠한다(만들 때·테마 바꿀 때)."""
        dark = getattr(self, "_dark", True)
        chosen = symbol_library.load_section_colors()   # [2026-10-11] 즐겨찾기·기본 도형도 ⋯로 색을 고른다
        fav = getattr(self, "_fav_section", None)
        if fav is not None:   # [2026-10-11] 즐겨찾기 칸은 옅은 코랄(★가 점 자리를 맡음) — 고른 색이 있으면 그 색(★도)
            c = QColor(chosen.get("favorites") or _ACCENT_CORAL)
            fav.set_box(c, dark)
            fav.set_title_html(f"<span style='color:{c.name()}'>★</span> 즐겨찾기")
        for sec in (getattr(self, "_basic_section", None),):
            if sec is not None:   # 안 고르면 중립 칸(점 없음), 고르면 폴더처럼 색 점 + 옅은 칸
                # [2026-10-12] 안 고르면 연한 파랑(그 전엔 중립). 제목 앞 □○△ 그림도 그 색(★처럼)
                c = QColor(chosen.get("basic") or self._BASIC_BASE_COLOR)
                sec.set_box(c, dark)
                sec.set_lead_pixmap(_svg_icon_pixmap("shapes", 15, self._section_icon_color(c, dark)))
        for sec, color in getattr(self, "_palette_folder_boxes", []):
            sec.set_box(color, dark)
            # [2026-10-12] 폴더 제목 앞 폴더 그림 — ★·□○△와 줄을 맞추고, 고른 색이 있으면 그 색
            if getattr(sec, "_is_folder", False):
                sec.set_lead_pixmap(_svg_icon_pixmap("folder", 15, self._section_icon_color(color, dark)))
        add_btn = getattr(self, "_add_folder_btn", None)
        if add_btn is not None:   # [2026-10-12] 새 폴더 = 점선 테두리 칸(폴더 칸과 같은 모서리, 중립색)
            bd, hover = (("rgba(255,255,255,55)", "rgba(255,255,255,18)") if dark
                         else ("rgba(0,0,0,70)", "rgba(0,0,0,12)"))
            add_btn.setStyleSheet(
                f"#addFolderBtn {{ border:1px dashed {bd}; border-radius:8px; padding:4px; background:transparent; }}"
                f"#addFolderBtn:hover {{ background:{hover}; }}")

    def _pick_symbol_folder_color(self, anchor: QWidget, folder_name: str):
        current = self._symbol_folder_colors().get(folder_name)

        def on_pick(col):
            if col is None:
                return
            symbol_library.set_folder_color(folder_name, QColor(col).name())
            self._refresh_custom_symbol_section()

        self._show_color_grid_popup(anchor, current, False, False, "폴더 색", on_pick, swatches=_SECTION_COLOR_SWATCHES)

    def _add_section_color_menu(self, sec, key: str):
        """[실사용 피드백 2026-10-11] 「즐겨찾기」·「기본 도형」에도 폴더처럼 마우스를 올리면 ⋯ — 칸 색 바꾸기·기본 색으로.
        이름변경·삭제는 없다(고정 칸). 제목 우클릭도 같은 메뉴."""
        more = QToolButton()
        more.setText("⋯"); more.setAutoRaise(True)
        more.setFixedSize(QSize(18, 16))
        more.setToolTip("칸 메뉴 — 색")
        more.setStyleSheet(f"QToolButton {{ color: {_current_icon_color().name()}; font-size: 13px; }}")
        more.clicked.connect(lambda _c=False, w=more: self._show_section_color_menu(w, QPoint(0, w.height()), key))
        sec.add_hover_button(more)
        self._section_more_btns.append(more)
        sec._title_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        sec._title_lbl.customContextMenuRequested.connect(
            lambda pos, w=sec._title_lbl: self._show_section_color_menu(w, pos, key))

    def _show_section_color_menu(self, widget: QWidget, pos, key: str):
        menu = QMenu(self)
        _style_menu_separators(menu)
        menu.addAction(_menu_icon("menu_color"), "칸 색 바꾸기…", lambda: self._pick_section_color(widget, key))
        reset = menu.addAction("기본 색으로", lambda: self._set_section_color(key, None))
        reset.setEnabled(key in symbol_library.load_section_colors())
        menu.exec(widget.mapToGlobal(pos))

    def _pick_section_color(self, anchor: QWidget, key: str):
        chosen = symbol_library.load_section_colors().get(key)
        current = QColor(chosen or (_ACCENT_CORAL if key == "favorites" else self._BASIC_BASE_COLOR))
        self._show_color_grid_popup(anchor, current, False, False, "칸 색",
                                    lambda col: col is not None and self._set_section_color(key, QColor(col).name()),
                                    swatches=_SECTION_COLOR_SWATCHES)

    def _set_section_color(self, key: str, color):
        symbol_library.set_section_color(key, color)
        self._restyle_palette_boxes()

    def _show_symbol_folder_context_menu(self, label_widget: QLabel, pos, folder_name: str):
        """[실사용 피드백 2026-08-19 재개편] 폴더 이름 우클릭 → 이름변경/삭제 메뉴 — 옛
        헤더의 "✎"/"×" 버튼 2개를 대체한다(심볼 버튼 우클릭 메뉴, 아래
        `_show_custom_symbol_context_menu`와 같은 관례)."""
        menu = QMenu(self)
        _style_menu_separators(menu)
        menu.addAction(_menu_icon("menu_color"), "폴더 색 바꾸기…",
                       lambda: self._pick_symbol_folder_color(label_widget, folder_name))
        # [2026-10-12] 기본이 중립이 되면서 고른 색을 되돌릴 길 — 「기본 도형」·「즐겨찾기」 메뉴와 같은 이름
        reset = menu.addAction("기본 색으로", lambda: self._reset_symbol_folder_color(folder_name))
        reset.setEnabled(folder_name in symbol_library.load_folder_colors())
        menu.addAction(_menu_icon("menu_rename"), "이름변경…", lambda: self._rename_symbol_folder_prompt(folder_name))
        menu.addAction(_menu_icon("ai_trash"), "삭제…", lambda: self._delete_symbol_folder_prompt(folder_name))
        menu.exec(label_widget.mapToGlobal(pos))

    def _reset_symbol_folder_color(self, folder_name: str):
        symbol_library.set_folder_color(folder_name, None)
        self._refresh_custom_symbol_section()


    def _show_custom_symbol_context_menu(self, btn: QToolButton, pos, sym_id: str):
        """[실사용 피드백 2026-08-18] 우클릭 = 곧바로 삭제 확인창이던 것을 메뉴(이름변경/삭제)
        로 교체 — 탐색기 관례. 폴더 이름변경/삭제는 폴더 이름 우클릭이 별도로 담당(위
        `_show_symbol_folder_context_menu`, 2026-08-19 재개편).
        [신규기능 2026-08-20] 즐겨찾기 토글도 여기 추가 — deep-interview로 "추가/해제 액션
        2개"가 아니라 "토글 1개"로 확정, 현재 상태에 따라 라벨이 바뀐다."""
        menu = QMenu(self)
        _style_menu_separators(menu)
        self._add_favorite_toggle_action(menu, f"customsym:{sym_id}")
        menu.addAction(_menu_icon("menu_rename"), "이름변경…", lambda: self._rename_custom_symbol_prompt(sym_id))
        menu.addSeparator()
        menu.addAction(_menu_icon("menu_export"), "SVG로 내보내기…", lambda: self._export_custom_symbol_svg(sym_id))
        menu.addAction(_menu_icon("ai_trash"), "삭제…", lambda: self._delete_custom_symbol_prompt(sym_id))
        menu.exec(btn.mapToGlobal(pos))


    def _export_custom_symbol_svg(self, sym_id: str):
        """[실사용 요청 2026-08-21] 심볼 우클릭 → SVG로 내보내기 — 심볼 저장 형식이 이미
        도형 dict 목록(`symbol_library.add_symbol`)이라 새 의존성 없이 `insert_items`(임시
        씬 재구성, AI 이미지→도면 삽입과 같은 헬퍼)+`export_svg_symbol`(콘텐츠 크기에 꽉
        맞춘 SVG, `export_svg`의 A4 캔버스는 심볼 하나엔 과함)만으로 구현 가능."""
        entry = next((e for e in symbol_library.load_library() if e.get("id") == sym_id), None)
        if entry is None:
            return
        tmp_scene = QGraphicsScene()
        insert_items(tmp_scene, entry.get("items", []))
        if not tmp_scene.items():
            QMessageBox.warning(self, "SVG로 내보내기", "내보낼 도형이 없습니다.")
            return
        default_name = f"{entry.get('name', 'symbol')}.svg"
        path, _f = QFileDialog.getSaveFileName(self, "SVG로 내보내기", default_name, "SVG 파일 (*.svg)")
        if not path:
            return
        if export_svg_symbol(tmp_scene, path):
            self.statusBar().showMessage(f"'{entry.get('name')}' SVG로 내보냄", 3000)
        else:
            QMessageBox.warning(self, "SVG로 내보내기", "내보내기 실패 — 도형 크기를 확인하세요.")


    def _toggle_custom_symbol_favorite(self, sym_id: str):
        """[신규기능 2026-08-20, deep-interview] 심볼 우클릭 → 즐겨찾기 추가/해제 토글."""
        self._toggle_palette_favorite(f"customsym:{sym_id}")


    def _rename_custom_symbol_prompt(self, sym_id: str):
        """[실사용 피드백 2026-08-18] 팔레트 버튼 우클릭 → 이름변경 — 새 이름 입력 후
        `symbol_library.rename_symbol`로 저장, 패널을 다시 그려 버튼 라벨/툴팁에 반영."""
        entry = next((e for e in symbol_library.load_library() if e.get("id") == sym_id), None)
        if entry is None:
            return
        name, ok = QInputDialog.getText(self, "심볼 이름변경", "새 이름:", text=entry["name"])
        name = name.strip()
        if not ok or not name:
            return
        symbol_library.rename_symbol(sym_id, name)
        self._refresh_custom_symbol_section()


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


    def _move_custom_symbol(self, sym_id: str, folder: str | None):
        """[신규기능, 2026-08-12] `_SymbolFolderDropZone.dropEvent` 콜백 — 심볼을 드롭된 폴더로 옮기고 다시 그린다."""
        symbol_library.move_symbol(sym_id, folder)
        self._refresh_custom_symbol_section()


    def _rename_symbol_folder_prompt(self, name: str):
        """[실사용 피드백 2026-08-19 → 같은 날 우클릭 메뉴로 재개편] 폴더 이름 우클릭 메뉴
        → 새 이름 입력 후 `symbol_library.rename_folder`로 저장 — 도입 당시 "폴더 이름변경은
        스코프 밖"이던 것을 심볼 이름변경(2026-08-18)과 같은 이유로 뒤집음. 이름 중복은
        폴더 목록에서 직접 확인(라이브러리 쪽은 조용히 무시하므로 사용자에게 이유를 알려줘야
        함)."""
        new_name, ok = QInputDialog.getText(self, "폴더 이름변경", "새 이름:", text=name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == name:
            return
        if new_name in symbol_library.load_folders():
            QMessageBox.warning(self, "폴더 이름변경", f"'{new_name}' 폴더가 이미 있습니다.")
            return
        symbol_library.rename_folder(name, new_name)
        st = app_settings()   # 폴더별 화면 설정(접힘·보이는 개수)도 새 이름으로
        for pre in ("symfolder_collapsed_", "symfolder_rows_"):
            if st.contains(pre + name):
                st.setValue(pre + new_name, st.value(pre + name))
                st.remove(pre + name)
        self._refresh_custom_symbol_section()


    def _prompt_create_symbol_folder(self):
        """[신규기능, 2026-08-12] 「＋ 새 폴더」(2026-10-11부터 마지막 폴더 아래) — 새 폴더 생성. 이름변경은
        `_rename_symbol_folder_prompt`(2026-08-19 신설, 폴더 이름 우클릭 메뉴)가 담당."""
        name, ok = QInputDialog.getText(self, "새 폴더", "폴더 이름:")
        name = name.strip()
        if not ok or not name:
            return
        symbol_library.create_folder(name)
        self._refresh_custom_symbol_section()


    def _delete_symbol_folder_prompt(self, name: str):
        """[신규기능, 2026-08-12 → 2026-08-19 우클릭 메뉴로 재개편 → 같은 날 정책 전환] 폴더
        이름 우클릭 메뉴 → 확인 후 폴더와 소속 심볼을 전부 삭제(`symbol_library.delete_folder`
        참조) — 미분류로 옮겨 보존하던 옛 동작을 실사용 피드백으로 뒤집음(남기고 싶은 심볼은
        지우기 전에 다른 폴더로 옮겨두는 게 루틴이라는 전제). 개수를 셈해 경고에 반영 —
        "몇 개가 사라지는지" 없이 "삭제됩니다"만 뜨면 되돌릴 수 없는 조작 앞에서 정보가 너무
        적다."""
        count = sum(1 for e in symbol_library.load_library() if e.get("folder") == name)
        if count:
            msg = f"'{name}' 폴더를 삭제할까요? 안의 심볼 {count}개도 함께 완전히 삭제됩니다."
        else:
            msg = f"'{name}' 폴더를 삭제할까요?"
        ret = QMessageBox.question(self, "폴더 삭제", msg)
        if ret == QMessageBox.StandardButton.Yes:
            symbol_library.delete_folder(name)
            app_settings().remove(f"symfolder_rows_{name}")
            self._refresh_custom_symbol_section()


    # [실사용 피드백 2026-10-11] 도형·심볼 카드 높이 — 기본은 도면 칸 높이의 절반(옛 고정 상한 640px은 거의
    # 화면 끝까지 내려왔다), 카드 아래 손잡이로 끌어 바꾸면 그 값(`left_panel_height`), 제목 더블클릭하면 기본으로.
    # 레이어 카드와 겹치지 않는 데까지만 늘어난다.
    _LEFT_PANEL_MIN_H = 160

    def _left_panel_max_h(self) -> int:
        view_h = self._view.height() if self._view.isVisible() else self.height()
        layers = getattr(self, "_layers_panel", None)
        layers_h = layers.height() if layers is not None and not layers.isHidden() else 0
        extra = self._left_panel._head.sizeHint().height() + self._left_grip.height()
        limit = view_h - layers_h - 3 * self._PANEL_MARGIN - extra
        want = getattr(self, "_left_h_drag", None)
        if want is None:
            want = app_settings().value("left_panel_height", 0, type=int) or view_h // 2
        return max(self._LEFT_PANEL_MIN_H, min(want, limit))

    def _on_left_grip_press(self):
        self._left_h0 = self._left_scroll.height()

    def _on_left_grip_move(self, dy):
        self._left_h_drag = max(self._LEFT_PANEL_MIN_H, int(self._left_h0 + dy))
        self._relayout_left_panel()

    def _on_left_grip_release(self):
        if getattr(self, "_left_h_drag", None) is not None:
            app_settings().setValue("left_panel_height", self._left_scroll.height())
        self._left_h_drag = None

    def _reset_left_panel_height(self):
        self._left_h_drag = None
        app_settings().remove("left_panel_height")
        self._relayout_left_panel()

    def _build_left_panel(self):
        """[캔버스-퍼스트][좌측 패널 아코디언 개편, 2026-08-12 → 2026-08-13 3섹션으로 병합
        → 2026-08-19 레이어를 좌하단 독립 패널로 재분리, `_build_layers_panel` 참조 →
        2026-08-19 재실사용 피드백으로 기본도형/내 심볼 최상단 접기 제거]
        기본도형(순서도 5종 포함)/내 심볼 2섹션을 `_StaticSection`으로 쌓은 좌상단 플로팅
        카드(deep-interview 확정 스코프 — 옛 도형/레이어 탭 2개를 대체). 최상단 두 섹션은
        더 이상 접지 않는다 — 실사용 중 이 아코디언을 접었다 펼 때 패널이 원래 크기로
        정확히 복원되지 않고 부풀어 보이는 레이아웃 버그(`QWidgetItem`이 부모 레이아웃에
        캐시한 옛 sizeHint가 `updateGeometry()` 없이는 갱신되지 않는 Qt 함정, 아래
        `_refresh_custom_symbol_section.add_group._toggle_folder` 참조)가 있었고, "내 심볼"은
        폴더 단위로 접는 게 더 유용하다는 판단(사용자 확인). 탭 전환 특유의 "숨긴 페이지가
        sizeHint에서 안 빠지는" 문제(2026-07-29, `_switch_left_tab`이 겪던 QTabWidget 함정)는
        애초에 탭이 아니라 섹션마다 독립 `setVisible()`이라 같은 함정을 밟지 않는다."""
        # [2026-08-13 피드백] 빈 제목이라 패널 최상단바에 아무 표시가 없던 것 — 속성/미니맵
        # 패널처럼 짧은 명사 하나로("도형", 내부엔 도형 팔레트+레이어가 함께 있지만 팔레트가
        # 주 콘텐츠).
        # [첫 화면 재디자인 2026-10-07, 시안 3라운드 S3+S4] 제목 「도형 · 심볼」. 안은 위에서부터 큰 검색칸
        # (도형도 찾음) → 즐겨찾기 → 기본 도형 → 폴더 → 「＋ 새 폴더」. [2026-10-11] 제목 줄의 「아이콘|목록」·＋는 없앰.
        panel = _FloatingPanel(self, "도형 · 심볼", "left")
        self._left_panel = panel
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(3, 3, 3, 3); outer.setSpacing(2)   # [2026-08-12 3차] 4→3
        self._left_container = container   # _refresh_custom_symbol_section이 아래에서 바로 씀
        # [실사용 피드백 2026-08-25] "내 심볼" 폴더가 계속 늘어나면 이 패널은 그냥 화면
        # 아래로 잘려나갈 뿐 스크롤이 없었다 — 콘텐츠를 QScrollArea로 감싸고 높이를
        # 상한으로 클램프한다(실제 높이 계산은 `_relayout_
        # left_panel`이 콘텐츠가 바뀔 때마다 담당 — 그 메서드 주석 참조). 뷰 높이 기준으로
        # 매번 다시 재는 방식은 시도했다가 되돌렸다 — 오프스크린 테스트 플랫폼의 가상
        # 화면이 작아 평소 콘텐츠(폴더 1~2개)조차 항상 클램프에 걸려버려 "폴더를 접으면
        # 패널이 줄어든다"는 기존 동작 자체가 검증 불가능해졌다(회귀 테스트 실패로 확인).
        # 고정 상한은 실사용 창 크기(기본 1200×800, `host.py` 참조)에서 폴더 몇 개
        # 수준까진 전혀 안 걸리고, 정말 폴더가 쌓였을 때만("어딘가서부터는 스크롤" —
        # 실사용 질문) 개입한다.
        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # [실사용 피드백 2026-10-12] 스크롤 영역이 카드 끝까지 붙어 불투명 배경으로 카드 왼쪽 테두리(카드가
        # 직접 그리는 1px)를 덮었다 — 배경을 칠하지 않게 해 카드 바탕·테두리가 그대로 보이게.
        # (setWidget이 내용 위젯의 autoFillBackground를 켜므로 그 뒤에 끈다.)
        scroll.viewport().setAutoFillBackground(False)
        container.setAutoFillBackground(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._left_scroll = scroll
        # [패널 통일 2라운드 2026-10-11] 스크롤바는 얇게(6px), 마우스를 카드에 올렸을 때만 손잡이가 보인다
        # (자리는 늘 같아 나타날 때 내용이 밀리지 않음 — `_set_left_scroll_hover`).
        scroll.installEventFilter(self)
        self._set_left_scroll_hover(False)
        panel.set_content(scroll)
        # [실사용 피드백 2026-10-11] 카드 아래 끝 손잡이 — 끌어서 높이, 더블클릭(또는 제목 더블클릭)하면 기본(창 절반).
        self._left_grip = _DragGrip("끌어서 카드 높이 조절 · 더블클릭하면 원래대로",
                                    self._on_left_grip_press, self._on_left_grip_move,
                                    self._on_left_grip_release, self._reset_left_panel_height, height=9)
        panel._body_layout.addWidget(self._left_grip)
        panel.set_title_double_click(self._reset_left_panel_height)

        self._shape_tool_buttons: dict[str, QToolButton] = {}
        self._sym_buttons: dict[str, QToolButton] = {}
        self._shape_sections: list = []   # (grid, buttons) — 기본도형·순서도
        # ---- 검색칸(맨 위, 도형·심볼 함께) ----
        # [§8 항목34, 2026-10-03] 항상 보이게. 목록을 새로 그려도(등록·삭제·입력마다) 입력 중인
        # 글자·포커스가 남도록 다시 그리는 영역 밖에 둔다. [2026-10-07] 「내 심볼」 아래에서 카드 맨 위로
        # 올리고 크게(시안 S3 "검색이 위에 있어 좋음"), 기본 도형도 이름·초성으로 거른다.
        search = QLineEdit()
        search.setPlaceholderText("도형·심볼 검색 (이름·초성)")
        search.setClearButtonEnabled(True)
        search.setMinimumHeight(32)
        # 입력칸 기본 폭(sizeHint)이 패널을 202→220px로 밀어냈다 — 폭은 패널을 따르게만
        search.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        search.setToolTip("이름 일부나 초성(예: ㅇㅌ)으로 찾기 — Esc로 지우기")
        search.textChanged.connect(lambda _t: self._on_palette_search())
        # ⚠ 등록을 먼저 — eventFilter가 이 칸을 알아보기 전에 이벤트가 오면 아직 없는 뷰를 찾다 죽는다
        self._custom_sym_search = search
        search.installEventFilter(self)   # Esc → 지우기(host_fileio.eventFilter)
        search_row = QWidget()
        sl = QHBoxLayout(search_row)
        sl.setContentsMargins(2, 2, 2, 4)
        sl.addWidget(search)
        outer.addWidget(search_row)

        # ---- 즐겨찾기(사용자가 넣고 빼는 목록 — `symbol_library.load_favorites`) ----
        # [실사용 피드백 2026-10-11] 옛 「자주 쓰는 것」(최근 8개 자동)을 대신한다. 제목에 코랄 ★ + 옅은 코랄 칸
        # ("말 그대로 즐겨찾기니까 돋보이게" — 사용자 요청이라 코랄=의미 있는 상태 원칙에 맞음).
        fav_section = _StaticSection("즐겨찾기")
        fav_section.set_title_html(f"<span style='color:{_ACCENT_CORAL}'>★</span> 즐겨찾기")
        self._fav_section = fav_section
        outer.addWidget(fav_section)

        # ---- 기본도형 (항상 펼침, 접기 없음 — 2026-08-19) ----
        # [2026-08-13 피드백] 옛 "기본도형"(네모·원·삼각형)과 "순서도"(판단·시작/끝·입출력·
        # 준비·저장소) 두 아코디언 섹션을 하나로 병합 — 순서도 5종도 mermaid 기준으로는
        # 각자 고유 shape 이름(decision/terminal 등)일 뿐 "기본"과 상위 카테고리로 묶이진
        # 않지만, 접힌 별도 헤더로 나눌 만큼 이질적이지도 않다는 판단(사용자 확인).
        # [2026-08-13 재피드백] 두 그리드를 따로 만들면 3개+5개로 줄이 안 맞아(3/4/1) 어색
        # 하다는 지적 — 하나의 그리드에 8개를 다 넣어 4열×2줄로 고르게 줄바꿈하고, 사용
        # 빈도가 높은 "판단"을 순서상 4번째(첫 줄 마지막 칸)로 옮겨 올렸다.
        # [§8 항목17 7단계, 2026-08-10] 포트□/포트○ 팔레트 버튼 제거 — TRIM 도구가 일반
        # 사각형/원을 겹쳐 놓고 자르는 워크플로로 대체(백엔드는 그대로 둬 기존 `.ecad` 안전).
        # `_shape_tool_buttons`/`_sym_buttons` 딕셔너리 분리(기본 도구 vs 심볼)는 `set_tool`
        # 체크상태 동기화가 참조하므로 그대로 유지(host_canvas.py `set_tool` 참조) — 한 그리드
        # 안에서도 항목별로 다른 dict에 저장 가능하도록 `_make_shape_grid`를 확장했다.
        basic_section = _StaticSection("기본 도형")
        basic_entries = [
            ("사각형", "rect", "사각형 — 클릭 후 캔버스에 드래그", "rect", self._shape_tool_buttons),
            ("원", "ellipse", "원 — 클릭 후 캔버스에 드래그", "ellipse", self._shape_tool_buttons),
            ("삼각형", "triangle", "삼각형 — 클릭 후 캔버스에 드래그", "sym:triangle", self._shape_tool_buttons),
            ("판단", "decision", "판단 — 클릭 후 캔버스에 드래그", "sym:decision", self._sym_buttons),
            ("시작/끝", "terminal", "시작/끝 — 클릭 후 캔버스에 드래그", "sym:terminal", self._sym_buttons),
            ("입출력", "data", "입출력 — 클릭 후 캔버스에 드래그", "sym:data", self._sym_buttons),
            ("준비", "prep", "준비 — 클릭 후 캔버스에 드래그", "sym:prep", self._sym_buttons),
            ("저장소", "database", "저장소 — 클릭 후 캔버스에 드래그", "sym:database", self._sym_buttons),
        ]
        # 「즐겨찾기」가 기본 도형 칸을 다시 만들 때 쓰는 표(tool_key → 이름·아이콘 종류).
        self._basic_palette_entries = {e[3]: (e[0], e[1]) for e in basic_entries}
        basic_grid = self._make_shape_grid(basic_entries)
        basic_section.set_count(str(len(basic_entries)))
        self._basic_section = basic_section
        basic_section.body_layout.addLayout(basic_grid)
        outer.addWidget(basic_section)

        self._relayout_sections(horiz=False)   # 항상 세로(2열) — 반응형 전환 없음

        # ---- 내 심볼 (폴더 지원, 최상단은 항상 펼침 — 폴더별 접기는 add_group 참조) ----
        custom_section = _StaticSection("내 심볼")
        # [2026-10-07] 「내 심볼」 제목 줄은 숨긴다 — ＋는 카드 제목 줄로, 검색칸은 카드 맨 위로 옮겼고
        # (시안 S3), 폴더 이름이 바로 이어져 제목이 따로 필요 없다.
        custom_section.layout().itemAt(0).widget().hide()
        custom_section.body_layout.setSpacing(8)
        self._custom_sym_section = custom_section
        self._custom_sym_body = custom_section.body
        self._custom_sym_buttons: dict[str, list[QToolButton]] = {}   # set_tool 체크상태 동기화용
        outer.addWidget(custom_section)
        self._refresh_custom_symbol_section()

        # [2026-08-19] 이제 어느 쪽도 최상단에서 접히지 않지만, "내 심볼"은 폴더 추가/삭제·
        # 심볼 등록마다 내용이 바뀌므로 `_relayout_left_panel()`이 계속 invalidate() 대상으로
        # 참조한다(이름은 옛 아코디언 시절 그대로 — `_relayout_left_panel` 주석 참조).
        self._left_accordion_sections = {
            "fav": fav_section,
            "basic": basic_section,
            "customsym": custom_section,
        }
        # [실사용 피드백 2026-10-11] 「즐겨찾기」·「기본 도형」도 폴더처럼 제목 줄에서 접는다(접힘 저장).
        # 2026-08-19에 이 두 섹션 접기를 뺀 이유(접었다 펴면 패널이 부풀던 것)는 폴더 접기가 쓰는
        # 겹마다 updateGeometry + `_relayout_left_panel` 방식으로 막는다.
        for key, sec in (("fav", fav_section), ("basic", basic_section)):
            setting = f"palette_section_collapsed_{key}"
            sec.make_collapsible(app_settings().value(setting, False, type=bool),
                                 lambda c, s=setting: self._on_palette_section_toggled(s, c))
        self._section_more_btns: list[QToolButton] = []   # `_apply_theme` 재도색용
        self._add_section_color_menu(fav_section, "favorites")
        self._add_section_color_menu(basic_section, "basic")
        self._restyle_palette_boxes()
        self._refresh_fav_section()
        self._relayout_left_panel()

    def _on_palette_section_toggled(self, setting: str, collapsed: bool):
        app_settings().setValue(setting, collapsed)
        self._relayout_left_panel()

    def _set_left_scroll_hover(self, hover: bool):
        handle = ("rgba(255,255,255,70)" if getattr(self, "_dark", True) else "rgba(0,0,0,70)") if hover else "transparent"
        self._left_scroll.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { width:6px; background:transparent; margin:0; }"
            f"QScrollBar::handle:vertical {{ background:{handle}; border-radius:3px; min-height:24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }")

    def _on_palette_search(self):
        """[패널 통일 2라운드 2026-10-11, 시안 2-3] 검색 중엔 「즐겨찾기」·「기본 도형」을 숨기고, 기본 도형까지
        함께 한 줄 목록으로 보인다(`_refresh_custom_symbol_section`의 검색 결과 칸)."""
        query = self._custom_sym_search.text().strip()
        self._basic_section.setVisible(not query)
        self._fav_section.setVisible(not query)
        for sec in (self._basic_section, self._fav_section):
            sec.updateGeometry()
        self._refresh_custom_symbol_section()


    def _build_layers_panel(self):
        """[패널 관련 수정, 2026-08-19, 사용자 요청] 레이어를 도형 팔레트 아코디언에서
        분리해 좌하단 독립 `_FloatingPanel`로 — "도구 선택"(도형 팔레트)과 "레이어 가시성/
        순서 관리"는 성격이 달라 나눠도 자연스럽고, 좌하단이 그동안 비어 있던 사분면이라
        늘어난 패널 하나만큼 화면을 더 차지하는 대신 공간 낭비는 없다. `_build_left_panel()`
        *뒤에* 호출돼야 한다(폭을 그 결과인 `_left_panel.width()`에 맞춤, 아래
        `_sync_layers_panel_width` 참조)."""
        panel = _FloatingPanel(self, "레이어", "layers")
        self._layers_panel = panel
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(3, 3, 3, 3); v.setSpacing(4)
        self._layers_list = QListWidget()
        self._layers_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        # [2026-08-13 시도했다 되돌림] `border-radius`를 걸어봤으나 `QAbstractScrollArea`
        # 계열은 뷰포트가 별도 자식 위젯이라 배경이 프레임 모서리에 클리핑되지 않음 —
        # 실측 결과 위쪽만 둥글고 아래쪽은 그대로 각진 채(뷰포트 배경이 그 밑을 사각으로
        # 채움) 일관성 없이 보여 원상복구. 제대로 하려면 커스텀 paintEvent로 클립 리전을
        # 그려야 해 이번 저위험 범위 밖으로 미룸.
        v.addWidget(self._layers_list)
        # [첫 화면 재디자인 2026-10-07, 시안 4라운드 L2] 아래 글자 버튼 두 개 — 새 레이어 / 선택한 도형을
        # 「그리는 중」 레이어로 옮기기(예전엔 우클릭 메뉴에만 있던 기능).
        # 버튼 줄은 크기 계산에서 뺀다(Ignored) — 폭은 도형·심볼 카드를 따라야 하는데(`_sync_layers_panel_width`),
        # 글꼴이 넓게 잡히는 환경에서 이 줄이 레이어 카드를 272px까지 밀어 넓혔다(실측, 오프스크린).
        btn_wrap = QWidget()
        btn_wrap.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        btn_row = QHBoxLayout(btn_wrap)
        btn_row.setContentsMargins(2, 2, 2, 2); btn_row.setSpacing(6)
        # [실사용 피드백 2026-10-11] 버튼은 아이콘+글자(자리가 모자라면 아이콘만 — `_sync_layers_panel_width`).
        add_layer_btn = QToolButton()
        # [2026-10-11] 192px 카드에 두 버튼이 다 들어가게(「＋ 새 레이어」에서 줄임) → [같은 날 후속] 「새로」만으론 무엇을
        # 만드는지 모호해 「Layer」로(사용자 선택 — 영어도 괜찮음).
        add_layer_btn.setText("Layer")
        add_layer_btn._icon_name = "menu_plus"
        add_layer_btn.setToolTip("레이어를 하나 더 만들어요")
        add_layer_btn.clicked.connect(lambda: self.add_layer())
        move_btn = QToolButton()
        # [2026-10-11] 아이콘이 붙어도 192px 카드에 둘 다 글자째 들어가게 → [같은 날 후속] 「선택 옮기기」는 어디로 옮기는지
        # 안 보여 「Move to layer」(사용자 선택). 자리가 모자라면 `_sync_layers_panel_width`가 아이콘만 남긴다.
        move_btn.setText("Move to layer")
        move_btn._icon_name = "menu_move_layer"
        move_btn.setToolTip("선택한 도형을 「그리는 중」 레이어로 옮겨요")
        move_btn.clicked.connect(self._move_selection_to_active_layer)
        self._layer_add_btn, self._layer_move_btn = add_layer_btn, move_btn
        for b in (add_layer_btn, move_btn):
            b.setIcon(_menu_icon(b._icon_name))
            b.setIconSize(QSize(14, 14))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn_row.addWidget(add_layer_btn)
        btn_row.addWidget(move_btn)
        btn_row.addStretch(1)
        v.addWidget(btn_wrap)
        panel.set_content(container)
        self._sync_layers_panel_width()
        self._refresh_layers_panel()


    def _sync_layers_panel_width(self):
        """레이어 패널 폭을 도형 패널(`_left_panel`) 폭에 맞춘다(2026-08-19, 사용자 요청) —
        미니맵이 속성 패널 폭을 따라가는 기존 패턴(`_reposition_panels` 주석 참조)과 동일
        관례. `_build_left_panel()`이 끝나기 전(레이어 패널 자체가 아직 없는 시점)엔 조용히
        건너뛴다.
        ⚠ [실측] `_left_panel.width()`는 그 안 컨테이너(`_left_container`, 좌우 여백 3+3)의
        폭과 정확히 같다(패널 자신의 프레임은 레이아웃 공간을 안 먹는 오버레이 그리기라
        오버헤드 0) — 레이어 패널의 콘텐츠 컨테이너도 같은 3+3 여백이므로, 안쪽
        `_layers_list`에는 그 여백만큼 뺀 폭을 줘야 바깥 패널 폭이 정확히 일치한다(그대로
        주면 여백만큼 6px 더 넓어짐 — 실측으로 확인한 값, 매직넘버 아님)."""
        layers_panel = getattr(self, "_layers_panel", None)
        if layers_panel is None:
            return
        container_margin = 6   # 레이어 패널 콘텐츠 컨테이너의 좌+우 여백(3+3) — 위 주석 참조
        target_w = self._left_panel.width() - container_margin
        if self._layers_list.width() != target_w:
            self._layers_list.setFixedWidth(target_w)
        # 버튼 둘이 글자째로 안 들어가면 아이콘만(이름은 툴팁) — 글자 모양 폭으로 재서 정한다.
        btns = (self._layer_add_btn, self._layer_move_btn)
        beside = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        for b in btns:
            b.setToolButtonStyle(beside)
        if sum(b.sizeHint().width() for b in btns) + 6 + 4 > target_w:
            for b in btns:
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        # [2026-10-07] 목록 높이가 바뀐 직후엔 세 겹 레이아웃(목록 담은 칸 → 패널 본문 → 패널)이 옛 크기를
        # 기억해 adjustSize가 예전 높이에 멈췄다(아래 버튼 줄 아래로 마지막 레이어가 가려짐, 실측 126 vs 159px)
        # — `_relayout_left_panel`과 같은 함정이라 같은 방식으로 겹마다 비운 뒤 잰다.
        for lay in (self._layers_list.parentWidget().layout(), layers_panel._body_layout,
                    layers_panel.layout()):
            lay.invalidate()
            lay.activate()
        layers_panel.adjustSize()


    def _relayout_left_panel(self):
        """왼쪽 패널 아코디언 섹션 접기/펴기·내용 변경 후 즉시 크기 재계산. 옛 `_switch_left_tab`은
        `container.layout().activate()` 한 번으로 충분했다 — 숨긴 페이지가 `container`의 직접
        자식이라 hide 시 Qt가 그 레이아웃만 동기적으로 무효화해준다. 아코디언은 숨는 위젯
        (`section.body`)이 `container`의 손자(`section`의 자식)라 한 단계 더 중첩됐는데, Qt의
        `QLayout::invalidate()`는 "레이아웃의 부모가 레이아웃인 동안만" 상위로 전파하고
        (`addLayout()`으로 중첩된 경우), 위젯 경계(`section` → `container`)를 넘는 전파는
        비동기 `LayoutRequest` 이벤트로만 일어난다 — 그래서 이 동기 호출 시점엔 아직 `outer`·
        `panel._body_layout`·`panel.layout()` 세 겹 모두 옛 sizeHint를 캐시한 채다. 각 위젯
        경계마다 명시적으로 `invalidate()`를 걸어 캐시를 비워야 그다음 `activate()`가 섹션들의
        *지금* sizeHint를 다시 읽는다(실측: 이걸 생략하면 접었다 펴도 패널이 펼친 크기에 고정됨)."""
        for section in getattr(self, "_left_accordion_sections", {}).values():
            section.layout().invalidate()
        self._left_container.layout().invalidate()
        self._left_container.layout().activate()
        # [실사용 피드백 2026-08-25, 스크롤 지원 신설] `_left_container`가 이제 패널 body에
        # 직접 얹히지 않고 `_left_scroll`(QScrollArea)을 한 겹 더 거친다 — `updateGeometry()`
        # 만으로는 부족했다(실측: `QScrollArea.sizeHint()`가 `setWidget()` 이후 내용이
        # 바뀌어도 최초 값에 멈춰 있어, 폴더를 접어도 패널 높이가 안 줄었다 — 이 함정은
        # `docs/pitfalls.md`에 별도 기록 예정). 대신 콘텐츠의 진짜 sizeHint(`_left_container`,
        # 이건 실측으로 정상 갱신됨을 확인)를 직접 읽어 `setFixedHeight`로 강제한다 — 고정
        # 높이는 레이아웃이 `sizeHint()`를 다시 묻지 않고 이 값을 그대로 쓰므로 캐시 여부와
        # 무관하게 항상 정확하다. 상한(`_left_panel_max_h` — 기본 창 절반·손잡이로 바꾼 값)을 넘으면
        # 그 값에서 멈추고 내부 스크롤바가 뜬다.
        content_h = self._left_container.sizeHint().height()
        self._left_scroll.setFixedHeight(min(content_h, self._left_panel_max_h()))
        # [패널 통일 2라운드 2026-10-11] 카드 폭은 고정 192px(내용이 정하지 않음) — 긴 이름은 …로 줄인다.
        self._left_scroll.setFixedWidth(_LEFT_PANEL_W)
        # [첫 화면 재디자인 2026-10-07] 스크롤바가 생기면 그 폭만큼 카드를 넓힌다 — 안 그러면 스크롤바가
        # 안쪽 폭을 먹어 오른쪽 글자(「최근 8개」·4열 끝 칸)가 잘렸다(「목록」 보기에서 실측).
        self._left_panel._body_layout.invalidate()
        self._left_panel._body_layout.activate()
        self._left_panel.layout().invalidate()
        self._left_panel.layout().activate()
        self._left_panel.adjustSize()
        self._sync_layers_panel_width()
        self._reposition_panels()

    # ---- 속성 패널 (M2 #2: 편집 — 색·두께·선스타일·폰트를 push_undo_state 경로로) ----
    _PEN_STYLE_ITEMS = [
        (Qt.PenStyle.SolidLine, "실선"), (Qt.PenStyle.DashLine, "점선"),
        (Qt.PenStyle.DotLine, "점선(도트)"), (Qt.PenStyle.DashDotLine, "일점쇄선"),
        (Qt.PenStyle.DashDotDotLine, "이점쇄선"),
    ]
    # [실사용 피드백 2026-08-20] '선'/'화살표' 아이콘 콤보가 텍스트 없이 아이콘만 보여주므로
    # (아래 _build_properties_panel) 생성 시점과 테마 재도색(_apply_theme) 양쪽이 같은
    # 크기를 써야 한다 — 클래스 상수로 한 곳에.
    _PROPS_ICON_W, _PROPS_ICON_H = 72, 18
    # [실사용 피드백 2026-08-20] 화살표 콤보만 '선' 콤보보다 위아래로 커 보인다는 지적 —
    # 곡선 아이콘을 수직 이등분선 방향 bulge로 재설계(위 `_arrow_kind_icon`)해 18px
    # 높이에서도 직선과 뚜렷이 구분되므로, 더 큰 높이가 필요 없어져 통일한다.
    _PROPS_ARROW_ICON_H = _PROPS_ICON_H


    def _build_properties_panel(self):
        panel = _FloatingPanel(self, "속성", "props")
        self._props_panel = panel
        self._pf_updating = False   # 프로그램적 값 세팅 중엔 편집 시그널 무시(피드백 차단)
        # [실사용 피드백 2026-08-20] 값·컨트롤이 안 잘리는 바닥폭. 원래 170이었으나, 아래
        # 힌트 라벨에 최대폭을 걸어 패널 폭 요동(170↔190)을 없애는 김에 그 요동의 "넓은 쪽"
        # 값(190)을 새 바닥으로 채택했다 — 단순히 좁은 쪽(170)으로 고정하면 `_update_zoom_
        # label()`의 "미니맵 (100%)" 제목이 그 폭 기준으로 여유공간(avail_w = 패널폭-57)을
        # 계산하는데, 오프스크린 테스트 폰트(한글 대체글리프가 원본보다 넓게 잡힘, 헤드리스
        # 폰트 한계 — screenshot.py 문서 참조)에서 딱 그 문턱에 걸려 "%)"가 말줄임되는 게
        # 재현됐다(실측: 폭170→avail_w 113px vs 필요 120px). 190이면 여유(avail_w 133px)가
        # 넉넉해 오프스크린·네이티브 폰트 모두 안전. 힌트 라벨의 최대폭도 이 값과 맞춰야
        # 한다(다음 줄 주석 참조), 그래서 매직넘버를 한 곳에만 둔다.
        # [패널 통일 2라운드 2026-10-11] 왼쪽 카드와 같은 192px — 자주 안 바꾸는 속성을 「현재 값 버튼」으로 접어 들어간다.
        _PROPS_MIN_W = _LEFT_PANEL_W - 3   # 카드 테두리·여백 3px를 빼야 바깥 폭이 왼쪽 카드와 같은 192(실측)
        content = QWidget()
        content.setMinimumWidth(_PROPS_MIN_W)
        form = QFormLayout(content)
        form.setContentsMargins(8, 8, 8, 8); form.setSpacing(7)

        # [실사용 피드백 2026-08-20] '종류'(읽기전용 라벨)와 '도형 바꾸기' 버튼을 한 행으로
        # 통합 — 바꿀 수 있는 도형(사각형/원/심볼)이 단일선택되면 이 행 자체가 현재 종류를
        # 보여주는 클릭형 버튼(=기존 _pf_swap_btn, 메뉴 그대로)으로 바뀌고, 그 외(화살표·텍스트·
        # 다중선택 등)는 기존처럼 읽기전용 라벨을 보여준다. 두 위젯을 QStackedWidget에 넣어
        # "안 보이는 페이지의 위젯은 isHidden()==True" Qt 기본 동작을 그대로 이용 — 옛 회귀
        # 테스트(선택 없으면 _pf_swap_btn.isHidden())가 별도 수정 없이 계속 성립한다.
        self._pf_type = QLabel("—")
        self._pf_swap_btn = QToolButton()
        self._pf_swap_btn.setToolTip("클릭: 다른 도형으로 바꾸기(크기·연결 유지)")
        self._pf_swap_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._pf_swap_btn.setMenu(self._build_swap_menu())
        # [실사용 피드백 2026-10-11 후속] 지금 종류도 펼침 메뉴와 같은 그림을 글자 옆에(`_refresh_properties`가 채움).
        self._pf_swap_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._pf_swap_btn.setIconSize(QSize(16, 16))
        # [실사용 피드백 2026-08-21] 화살표는 '종류'(경로 형태: 직선·곡선·직각)를 이 자리
        # 대신 별도 '화살표' 행에서 골라야 해 도형(사각형 등)의 바꾸기 버튼과 비일관이었다 —
        # 같은 스택에 화살표 종류 콤보(`_pf_routing_btn`, 아래에서 생성)를 3번째 페이지로
        # 추가해 도형·화살표 둘 다 '종류' 자리에서 바로 바꾸도록 통일한다.
        self._pf_type_stack = QStackedWidget()
        self._pf_type_stack.addWidget(self._pf_type)
        self._pf_type_stack.addWidget(self._pf_swap_btn)

        # 색 — [첫 화면 재디자인 2026-10-07, 시안 4라운드 P2] 견본 8개를 펼쳐 두고(한 번 클릭으로 바로 적용)
        # 끝의 「⋯」가 예전 스와치 버튼 자리(그리드 팝업·다른 색). 지금 색과 같은 견본에 테두리 고리.
        # hex 글자(`_pf_color_val`)는 시안에 없어 숨기되 값은 계속 채운다(테스트·접근성 텍스트).
        self._pf_color = QToolButton()
        self._pf_color.setText("…")
        self._pf_color.setFixedSize(QSize(22, 20))
        self._pf_color.setToolTip("다른 색 고르기 — 견본 칸은 우클릭으로 내 색으로 바꿀 수 있어요")
        self._pf_color.clicked.connect(lambda: (self._pf_color_pop.hide(), self._edit_color()))
        self._pf_color_val = QLabel("—")
        self._pf_color_val.setForegroundRole(QPalette.ColorRole.PlaceholderText)   # [UI 검토 2026-09-25] #888 대비 미달
        self._pf_color_val.hide()
        color_row = QWidget(); ch = QHBoxLayout(color_row)
        ch.setContentsMargins(0, 0, 0, 0); ch.setSpacing(3)
        self._pf_color_presets: list[QToolButton] = []
        for i in range(8):
            b = QToolButton(); b.setFixedSize(QSize(18, 18))
            b.clicked.connect(lambda _c=False, i=i: self._apply_line_preset(i))
            if i:   # [2026-10-11 후속] 2~8번째 칸은 우클릭으로 사용자가 색을 정한다(첫 칸 = 테마 잉크색 고정)
                b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(lambda _p, i=i: self._customize_preset("line", i))
            ch.addWidget(b); self._pf_color_presets.append(b)
        ch.addWidget(self._pf_color); ch.addWidget(self._pf_color_val); ch.addStretch(1)

        # [신규기능] 채움 — 스와치 하나(클릭=그리드 팝업, "없음"도 팝업 안 항목). rect/ellipse/
        # symbol 전용, 대상 없으면 행 자체를 비활성화(has_fill로 판정, _refresh_properties).
        # [2026-10-07, 시안 P2] 색과 같은 모양 — 견본 8개(첫 칸 = 없음, 나머지는 반투명이라 다크·라이트 캔버스와
        # 흰 종이 PDF 모두에서 글자가 읽힌다) + 「⋯」(예전 스와치 = 그리드 팝업·다른 색·투명도).
        self._pf_fill = QToolButton()
        self._pf_fill.setText("…")
        self._pf_fill.setFixedSize(QSize(22, 20))
        self._pf_fill.setToolTip("다른 채움색 고르기 — 견본 칸은 우클릭으로 내 색으로 바꿀 수 있어요")
        self._pf_fill.clicked.connect(lambda: (self._pf_fill_pop.hide(), self._edit_fill()))
        self._pf_fill_val = QLabel("—")
        self._pf_fill_val.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self._pf_fill_val.hide()
        fill_presets = QWidget(); fh = QHBoxLayout(fill_presets)
        fh.setContentsMargins(0, 0, 0, 0); fh.setSpacing(3)
        self._pf_fill_presets: list[QToolButton] = []
        for i in range(8):
            b = QToolButton(); b.setFixedSize(QSize(18, 18))
            b.clicked.connect(lambda _c=False, i=i: self._apply_fill_preset(i))
            if i:   # 첫 칸 = 없음 고정
                b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(lambda _p, i=i: self._customize_preset("fill", i))
            fh.addWidget(b); self._pf_fill_presets.append(b)
        fh.addWidget(self._pf_fill); fh.addWidget(self._pf_fill_val); fh.addStretch(1)

        # 두께 — 스핀박스(px).
        self._pf_width = QDoubleSpinBox()
        self._pf_width.setRange(0.5, 50.0); self._pf_width.setSingleStep(0.5)
        self._pf_width.setDecimals(1); self._pf_width.setSuffix(" px")
        self._pf_width.valueChanged.connect(self._edit_width)
        # [2026-10-07, 시안 P2] 자주 쓰는 굵기 버튼 1·2·3·5 — 한 번 클릭. 다른 값은 옆 숫자칸(예전 그대로).
        width_row = QWidget(); wh = QHBoxLayout(width_row)
        wh.setContentsMargins(0, 0, 0, 0); wh.setSpacing(2)
        self._pf_width_presets: dict[float, QToolButton] = {}
        for v in (1.0, 2.0, 3.0, 5.0):
            b = QToolButton(); b.setText(f"{v:g}"); b.setCheckable(True)
            b.setFixedSize(QSize(24, 22)); b.setToolTip(f"{v:g} px")
            b.setProperty("propSeg", True)
            b.clicked.connect(lambda _c=False, v=v: self._pf_width.setValue(v))
            wh.addWidget(b); self._pf_width_presets[v] = b
        self._pf_width.setFixedWidth(70)
        wh.addSpacing(4); wh.addWidget(self._pf_width); wh.addStretch(1)

        # 선스타일 — 콤보(pen 기반 도형 전용; 화살표·DXF는 #3). [실사용 피드백 2026-08-20]
        # 텍스트 목록 대신 각 스타일을 실제로 그린 아이콘. 1차(아이콘+텍스트)는 QComboBox
        # 기본 iconSize(16×16)에 짜부라져 잘 안 보인다는 재피드백으로 텍스트를 없애고
        # 그만큼 아이콘 자체를 키움(_PROPS_ICON_W/H) — 이름은 툴팁(ToolTipRole)으로 유지해
        # 드롭다운에서 항목에 마우스를 올리면 확인 가능. "이상하면 다시 텍스트 넣기"로
        # 사용자가 시험 승인.
        self._pf_style = QComboBox()
        self._pf_style.setToolTip("선 스타일")
        self._pf_style.setIconSize(QSize(self._PROPS_ICON_W, self._PROPS_ICON_H))
        for i, (st, name) in enumerate(self._PEN_STYLE_ITEMS):
            self._pf_style.addItem(_pen_style_icon(st, _current_icon_color(),
                                                    self._PROPS_ICON_W, self._PROPS_ICON_H), "", st)
            self._pf_style.setItemData(i, name, Qt.ItemDataRole.ToolTipRole)
        self._pf_style.currentIndexChanged.connect(self._edit_style)
        # [2026-10-07, 시안 P2] 선 모양 5종을 펼친 버튼으로 — 누르면 위 콤보의 현재 항목을 바꿔(편집 신호는
        # 콤보가 그대로 낸다) 펼침 목록을 여는 단계를 없앤다. 콤보 자체는 숨겨 두고 값의 원본으로만 쓴다.
        style_row = QWidget(); sh = QHBoxLayout(style_row)
        sh.setContentsMargins(0, 0, 0, 0); sh.setSpacing(2)
        self._pf_style_btns: list[QToolButton] = []
        for i, (st, name) in enumerate(self._PEN_STYLE_ITEMS):
            b = QToolButton(); b.setCheckable(True); b.setAutoExclusive(True)
            b.setIcon(_pen_style_icon(st, _current_icon_color(), 26, 10)); b.setIconSize(QSize(26, 10))
            b.setFixedSize(QSize(34, 22)); b.setToolTip(name)
            b.setProperty("propSeg", True)
            b.clicked.connect(lambda _c=False, i=i: self._pf_style.setCurrentIndex(i))
            sh.addWidget(b); self._pf_style_btns.append(b)
        sh.addStretch(1)
        self._pf_style.hide()
        sh.addWidget(self._pf_style)

        # 폰트 — 스핀박스(pt; 텍스트/라벨 전용).
        self._pf_font = QSpinBox()
        self._pf_font.setRange(_MIN_FONT, _MAX_FONT); self._pf_font.setSuffix(" pt")
        # [2026-10-07, 시안 P2 「− 12 pt ＋」] 위아래 화살표 대신 −/＋ 기호.
        self._pf_font.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        self._pf_font.valueChanged.connect(self._edit_font)

        # [실사용 피드백 2026-08-21] 항목 순서 — 종류(무엇인지) → 채움·색(같은 '색' 계열,
        # 면적이 넓은 채움을 먼저) → 선(선의 형태부터 정한 뒤) → 두께(그 선을 얼마나 굵게,
        # 연속값 다듬기라 선 바로 다음) → 폰트(텍스트 전용, 도형 축과 무관해 맨 뒤).
        # [패널 통일 2라운드 2026-10-11, 시안 2-4] 색·채움·선 모양·두께는 자주 바꾸지 않아(사용자) 카드엔 지금 값만 보이는
        # 버튼으로 두고, 누르면 예전에 펼쳐 두던 견본·버튼 줄이 작은 목록(`_PropPopup`)으로 열린다. 견본 하나를 고르면
        # 바로 적용된다. 「선」 한 줄에 색 | 선 모양 | 두께.
        # [실사용 피드백 2026-10-11 후속] 골라도 목록은 열린 채 — 하나씩 바꿔 보며 비교하려면 닫히면 불편.
        # 닫기는 바깥 클릭·Esc·연 버튼 다시 누르기(`_PropPopup.mousePressEvent`).
        # [2026-10-11, 시안 S1+Lucid] 목록에서 고른 뒤 목록이 닫힐 때까지 선택 강조선을 숨겨 바꾼 선 색이 그대로 보이게
        # (같은 날 후속 — 열기만 했을 땐 그대로 둔다, `host_style._on_prop_popup_visible`).
        self._pf_color_pop = _PropPopup(self, color_row, self._on_prop_popup_visible)
        self._pf_fill_pop = _PropPopup(self, fill_presets, self._on_prop_popup_visible)
        self._pf_style_pop = _PropPopup(self, style_row, self._on_prop_popup_visible)
        self._pf_width_pop = _PropPopup(self, width_row, self._on_prop_popup_visible)

        def value_btn(tip, pop):
            b = QToolButton()
            b.setToolTip(tip)
            b.setFixedHeight(24)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setProperty("propSeg", True)
            b.clicked.connect(lambda _c=False, b=b, pop=pop: pop.open_below(b))
            return b
        self._pf_color_btn = value_btn("선 색", self._pf_color_pop)
        self._pf_color_btn.setIconSize(QSize(16, 16)); self._pf_color_btn.setText("▾")
        self._pf_style_btn = value_btn("선 모양", self._pf_style_pop)
        self._pf_style_btn.setIconSize(QSize(26, 10)); self._pf_style_btn.setText("▾")
        self._pf_width_btn = value_btn("두께", self._pf_width_pop)
        self._pf_width_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._pf_fill_btn = value_btn("채움", self._pf_fill_pop)
        self._pf_fill_btn.setIconSize(QSize(16, 16)); self._pf_fill_btn.setText("▾")
        # 폭 고정 — 글꼴이 넓게 잡히는 환경에서 버튼이 카드를 밀어 넓히지 않게(오프스크린 실측 227px 줄)
        for b, bw in ((self._pf_color_btn, 38), (self._pf_style_btn, 52), (self._pf_width_btn, 50),
                      (self._pf_fill_btn, 38)):
            b.setFixedWidth(bw)
        line_row = QWidget(); lh = QHBoxLayout(line_row)
        lh.setContentsMargins(0, 0, 0, 0); lh.setSpacing(3)
        lh.addWidget(self._pf_color_btn); lh.addWidget(self._pf_style_btn); lh.addWidget(self._pf_width_btn)
        lh.addStretch(1)
        self._pf_fill_row = QWidget(); frh = QHBoxLayout(self._pf_fill_row)
        frh.setContentsMargins(0, 0, 0, 0)
        frh.addWidget(self._pf_fill_btn); frh.addStretch(1)
        form.addRow("종류", self._pf_type_stack)
        form.addRow("선", line_row)
        form.addRow("채움", self._pf_fill_row)
        self._pf_line_row = line_row

        # [미니패널 통합, 2026-07-31] 선택 위를 따라다니던 플로팅 컨텍스트 툴바(M3 #15)를
        # 폐지하고 그 안의 타입 전용 액션을 여기로 이관 — 사용자 피드백: 우측 속성 dock과
        # 겹치는 부분(색·선스타일)이 많아 따라다니는 패널이 방해로 느껴짐. 핸들러
        # (_floating_set_arrow_kind·_floating_set_radius·_floating_flip_arrows)는 플로팅
        # 툴바가 쓰던 것을 그대로 재사용(로직 변경 없음), 행 노출만 옛
        # _reposition_floating_toolbar의 show_routing/curved/show_dir 판정을 그대로 옮겨
        # _refresh_properties가 담당.
        # [실사용 피드백 2026-08-20] ① 화살표 종류와 방향 뒤집기가 성격이 비슷하니 인접
        # 배치(화살표→방향→반경, 반경은 곡선일 때만 조건부 노출이라 맨 뒤) ② 화살표 종류를
        # '선'과 같은 아이콘 콤보로 통일(예전엔 QToolButton+QMenu라 위젯 자체가 달라 보였음).
        # 속성 이름은 하위호환을 위해 그대로 _pf_routing_btn(이제 QComboBox)을 유지.
        # [실사용 피드백 2026-08-20] '선'과 같은 이유로 텍스트 없이 아이콘만(더 큼) + 툴팁.
        self._pf_routing_btn = QComboBox()
        self._pf_routing_btn.setToolTip("화살표 종류(직선·곡선·직각)")
        self._pf_routing_btn.setIconSize(QSize(self._PROPS_ICON_W, self._PROPS_ARROW_ICON_H))
        for i, (kind, label) in enumerate(_ARROW_KIND_LABELS):
            self._pf_routing_btn.addItem(
                _arrow_kind_icon(kind, _current_icon_color(),
                                 self._PROPS_ICON_W, self._PROPS_ARROW_ICON_H),
                "", kind)
            self._pf_routing_btn.setItemData(i, label, Qt.ItemDataRole.ToolTipRole)
        self._pf_routing_btn.currentIndexChanged.connect(self._edit_arrow_kind_combo)
        # [실사용 피드백 2026-08-21] 별도 '화살표' 행 대신 위 '종류' 스택의 3번째 페이지로 —
        # 화살표 선택 시 `_refresh_properties`가 이 위젯을 currentWidget으로 올린다.
        self._pf_type_stack.addWidget(self._pf_routing_btn)

        # [양방향 화살표, 2026-08-21] 화살촉 위치(없음/끝만/양쪽/시작만) — 화살표 전용 행.
        self._pf_head_btn = QComboBox()
        self._pf_head_btn.setToolTip("화살촉 위치(없음·끝만·양쪽·시작만)")
        self._pf_head_btn.setIconSize(QSize(self._PROPS_ICON_W, self._PROPS_ARROW_ICON_H))
        for i, (kind, label) in enumerate(_ARROW_HEAD_LABELS):
            self._pf_head_btn.addItem(
                _arrow_head_icon(kind, _current_icon_color(),
                                 self._PROPS_ICON_W, self._PROPS_ARROW_ICON_H),
                "", kind)
            self._pf_head_btn.setItemData(i, label, Qt.ItemDataRole.ToolTipRole)
        self._pf_head_btn.currentIndexChanged.connect(self._edit_arrow_head_combo)
        form.addRow("화살촉", self._pf_head_btn)

        # [실사용 피드백 2026-08-21] 화살촉 크기 배율 — Lucid 대비 화살촉이 작다는 지적으로
        # 신설(기본 공식도 같이 상향, `core_shapes._head_size` 참조). 화살촉이 아예 없으면
        # (화살촉='없음') 배율이 무의미하므로 그때만 숨긴다(_refresh_properties가 판정).
        self._pf_head_scale = QDoubleSpinBox()
        self._pf_head_scale.setRange(0.5, 3.0); self._pf_head_scale.setSingleStep(0.1)
        self._pf_head_scale.setDecimals(1); self._pf_head_scale.setSuffix("×")
        self._pf_head_scale.setKeyboardTracking(False)
        self._pf_head_scale.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._pf_head_scale.setToolTip("화살촉 크기 배율")
        self._pf_head_scale.valueChanged.connect(self._edit_head_scale)
        form.addRow("머리크기", self._pf_head_scale)

        self._pf_dir_btn = QToolButton()
        self._pf_dir_btn.setText("뒤집기")
        self._pf_dir_btn.setIcon(_flip_icon(_current_icon_color()))
        self._pf_dir_btn.setIconSize(QSize(28, 20))
        self._pf_dir_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._pf_dir_btn.setToolTip("화살표 방향 뒤집기")
        self._pf_dir_btn.clicked.connect(self._floating_flip_arrows)
        form.addRow("방향", self._pf_dir_btn)

        self._pf_radius = QSpinBox()
        self._pf_radius.setRange(0, int(_PolyArrowItem._CURVE_R_MAX))
        self._pf_radius.setSingleStep(2)
        self._pf_radius.setSuffix(" px")
        self._pf_radius.setKeyboardTracking(False)   # 타이핑 중 매 글자 커밋 방지
        # [실사용 버그 2026-08-21] 예전엔 NoFocus였다 — Del·Ctrl+D·도구 숫자키를 뷰
        # keyPressEvent가 처리하는데, 스핀박스가 포커스를 가져가면(휠로 값만 만져도 기본
        # 포커스정책이 그걸 흡수) 그 단축키들이 캔버스로 안 갔기 때문. 그런데 NoFocus는
        # 키보드 포커스 자체를 영구 차단해 클릭해서 숫자를 '타이핑'하는 것도 함께 막아버렸다
        # (커서 깜빡임조차 없음, 사용자가 회전 필드에서 직접 재현). 실측(offscreen)으로 확인한
        # `ClickFocus`가 둘 다 만족한다 — 명시적으로 클릭해야만 포커스를 얻고(타이핑 가능),
        # 포커스 없이 휠만 굴리면 값은 바뀌어도 포커스는 안 옮겨간다(캔버스 단축키 안전).
        self._pf_radius.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._pf_radius.setToolTip("곡선 반경(0=직각)")
        self._pf_radius.valueChanged.connect(self._floating_set_radius)
        form.addRow("반경", self._pf_radius)

        # [신규기능 2026-08-21] 회전 각도 숫자입력 — 핸들 드래그만 있던 회전에 정밀 입력을
        # 더한다. 끝점으로 모양을 정하는 도형(화살표·선·펜 등, `_uses_endpoints()`)은 회전
        # 핸들 자체가 없어 대상에서 뺀다(_refresh_properties가 행 노출을 그 조건으로 판정).
        self._pf_rotation = QDoubleSpinBox()
        self._pf_rotation.setRange(0.0, 359.9); self._pf_rotation.setDecimals(1)
        self._pf_rotation.setSuffix("°"); self._pf_rotation.setWrapping(True)
        self._pf_rotation.setKeyboardTracking(False)
        self._pf_rotation.setFocusPolicy(Qt.FocusPolicy.ClickFocus)   # 위 반경 스핀박스 주석 참조
        self._pf_rotation.setToolTip("회전 각도")
        self._pf_rotation.valueChanged.connect(self._edit_rotation)
        form.addRow("회전", self._pf_rotation)

        # [실사용 피드백 2026-10-11, 시안 T1] 「글자」 구역 — 도형·선 안 글자(라벨)와 독립 글자의 크기·색. 예전 「폰트」 줄은
        # 독립 글자를 고를 때만 켜져, 도형 안 글자 크기는 바꿀 길이 없었다. 글자가 하나도 없으면 구역째 숨김(`_refresh_properties`).
        self._pf_text_sep = QFrame()
        self._pf_text_sep.setFrameShape(QFrame.Shape.HLine)
        self._pf_text_sep.setFrameShadow(QFrame.Shadow.Plain)
        self._pf_text_sep.setForegroundRole(QPalette.ColorRole.Mid)
        form.addRow(self._pf_text_sep)
        self._pf_text_head = QWidget()
        th = QHBoxLayout(self._pf_text_head)
        th.setContentsMargins(0, 0, 0, 0); th.setSpacing(6)
        head_lbl = QLabel("글자")
        _thf = head_lbl.font(); _thf.setWeight(QFont.Weight.DemiBold); head_lbl.setFont(_thf)   # 스타일시트 금지 — 팔레트 색 유지
        self._pf_text_preview = QLabel()
        _tpf = self._pf_text_preview.font(); _tpf.setPixelSize(11); self._pf_text_preview.setFont(_tpf)
        self._pf_text_preview.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        th.addWidget(head_lbl); th.addWidget(self._pf_text_preview, 1)
        form.addRow(self._pf_text_head)
        form.addRow("크기", self._pf_font)
        # 글자 색 — 선 색과 같은 견본(같은 사용자 지정 칸) + 「⋯」 다른 색.
        text_color_row = QWidget(); tch = QHBoxLayout(text_color_row)
        tch.setContentsMargins(0, 0, 0, 0); tch.setSpacing(3)
        self._pf_text_color_presets: list[QToolButton] = []
        for i in range(8):
            b = QToolButton(); b.setFixedSize(QSize(18, 18))
            b.clicked.connect(lambda _c=False, i=i: self._apply_text_color_preset(i))
            tch.addWidget(b); self._pf_text_color_presets.append(b)
        more = QToolButton(); more.setText("…"); more.setFixedSize(QSize(22, 20))
        more.setToolTip("다른 글자 색 고르기")
        more.clicked.connect(lambda: (self._pf_text_color_pop.hide(), self._edit_text_color()))
        tch.addWidget(more); tch.addStretch(1)
        self._pf_text_color_pop = _PropPopup(self, text_color_row, self._on_prop_popup_visible)
        self._pf_text_color_btn = value_btn("글자 색", self._pf_text_color_pop)
        self._pf_text_color_btn.setIconSize(QSize(16, 16)); self._pf_text_color_btn.setText("▾")
        self._pf_text_color_btn.setFixedWidth(38)
        self._pf_text_color_row = QWidget(); tcr = QHBoxLayout(self._pf_text_color_row)
        tcr.setContentsMargins(0, 0, 0, 0)
        tcr.addWidget(self._pf_text_color_btn); tcr.addStretch(1)
        form.addRow("색", self._pf_text_color_row)

        self._pf_hint = QLabel("객체를 선택하면 속성을 편집할 수 있습니다.")
        _hf = self._pf_hint.font(); _hf.setPixelSize(12); self._pf_hint.setFont(_hf)   # 스타일시트 금지 — _section_label 주석
        self._pf_hint.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        self._pf_hint.setWordWrap(True)   # 줄바꿈 허용 → 안내문이 패널 최소폭을 붙잡지 않게
        # [실사용 피드백 2026-08-20] 위 wordWrap만으론 부족했다 — 줄바꿈 QLabel의 sizeHint()는
        # 폭 상한이 없으면 Qt가 자체적으로 "적당히 넓은" 값(약 190px)을 계산해 반환하고,
        # `adjustSize()`는 그 sizeHint를 그대로 쓴다(위 _PROPS_MIN_W 바닥폭 170px보다 큼) —
        # 그래서 선택 없음(이 안내문이 보임)↔선택 있음(안내문이 "" 로 비워짐) 사이에서 패널
        # 폭이 170↔190으로 실제로 흔들렸고, 미니맵이 속성패널 폭을 그대로 따라가는 설계라
        # (_reposition_panels) 그 요동이 미니맵 크기 요동(사용자가 지적한 "이상한 여백")으로
        # 번졌다. 명시적 최대폭을 걸어 sizeHint 자체가 바닥폭을 못 넘게 고정.
        self._pf_hint.setMaximumWidth(_PROPS_MIN_W)
        form.addRow(self._pf_hint)
        panel.set_content(content)
        self._props_form = form
        # [§8 항목10] selectionChanged→_refresh_properties 연결은 host._wire_document_signals가
        # 문서(탭)마다 맡는다(여기서 하면 최초 문서 하나만 연결되고 새 탭은 못 받음).
        self._refresh_properties()

    # ---- 미니맵 패널 (신규기능 — deep-interview 2026-07-28) ------------------

    def _build_minimap_panel(self):
        """메인과 같은 scene을 공유하는 축소 뷰. 내용 갱신은 Qt가 자동(멀티뷰) — 여기선 메인
        뷰의 줌/팬/리사이즈(scene.changed를 안 타는 순수 뷰 변환) 시점에만 명시적으로 미니맵을
        다시 그리도록 훅을 건다."""
        panel = _FloatingPanel(self, "미니맵", "minimap")
        self._minimap_panel = panel
        # [줌 배지 통합 2026-08-01, 사용자 요청 2차] 처음엔 독립 배지 → 미니맵 하단 푸터 행으로
        # 옮겼다가, "숫자를 '미니맵(50%)'처럼 제목에 표기하고 그 %를 클릭하면 100%+정중앙
        # 이동"이라는 후속 요청으로 한 번 더 바뀌었다 — 별도 배지 위젯 없이 제목 자체가 표기와
        # 클릭을 겸한다(`set_title_click`). 지도 위 오버레이로 그리지 않는 이유는 그대로다:
        # 2026-07-28 미니맵 인디케이터 이중변환 사고 같은 좌표계 버그를 또 만들 여지를 피한다.
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

        # [패널 통일 2라운드 2026-10-11, 시안 2-5] 다른 카드처럼 제목 줄을 두고 그 옆에 확대 버튼 「− % ＋ ⤢ 1:1」
        # (4라운드 M2의 "제목 없이 지도 위·확대 줄 아래"를 사용자 요청으로 바꿈 — 한 줄이 줄어 지도 칸이 그대로).
        # 192px에 들어가게 「전체 보기」·「100%」 글자는 아이콘·「1:1」로, 접기 버튼은 뺀다(M2부터 없던 것).
        panel._collapse_btn.hide()
        if panel._collapsed:
            panel._set_collapsed(False, persist=False)   # 접기 버튼이 없으니 예전에 접어 둔 상태는 펼쳐 둔다
        head_l = panel._head.layout()
        head_l.setSpacing(0)   # [2026-10-11 시안 H3] 카드 제목이 15px로 커져 192px 안에 넣으려고 버튼 사이 틈을 없앰(버튼 자체 여백이 있음)

        def _zbtn(text, tip, slot, w=20):
            b = QToolButton(); b.setText(text); b.setToolTip(tip)
            b.setAutoRaise(True); b.setFixedSize(QSize(w, 20))
            b.clicked.connect(slot)
            return b
        self._zoom_out_btn = _zbtn("−", "축소", lambda: self._on_wheel_zoom(-1))
        self._zoom_pct_lbl = QToolButton()
        self._zoom_pct_lbl.setAutoRaise(True)
        self._zoom_pct_lbl.setToolTip("누르면 100% + 내용 가운데로")
        self._zoom_pct_lbl.setFixedSize(QSize(38, 20))
        _f = self._zoom_pct_lbl.font(); _f.setBold(True); _f.setPixelSize(11); self._zoom_pct_lbl.setFont(_f)
        self._zoom_pct_lbl.clicked.connect(self._zoom_reset)
        self._zoom_pct_lbl.setText(f"{round(self._view.transform().m11() * 100)}%")   # 첫 표시(이후는 _update_zoom_label)
        self._zoom_in_btn = _zbtn("＋", "확대", lambda: self._on_wheel_zoom(1))
        self._zoom_fit_btn = _zbtn("", "전체 보기 — 도면 전체가 보이게(Ctrl+9)", self._act_fit.trigger, 22)
        self._zoom_fit_btn.setIcon(_svg_icon("zoom_fit", 14, _current_icon_color()))
        self._zoom_fit_btn.setIconSize(QSize(14, 14))
        self._zoom_100_btn = _zbtn("1:1", "실제 크기(100%)", self._act_zoom100.trigger, 24)
        _f2 = self._zoom_100_btn.font(); _f2.setPixelSize(10); _f2.setBold(True); self._zoom_100_btn.setFont(_f2)
        for i, b in enumerate((self._zoom_out_btn, self._zoom_pct_lbl, self._zoom_in_btn,
                               self._zoom_fit_btn, self._zoom_100_btn)):
            head_l.insertWidget(1 + i, b)
        self._zoom_row = panel._head   # 확대 버튼 줄 = 제목 줄(우클릭 「닫기」도 제목 줄 메뉴 그대로)

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
        self._minimap_wired_view = self._view   # [§8 항목10 Stage B] _rebuild_minimap 대조용


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
