"""단축키 레지스트리 — [실사용 요청 2026-08-21] 설정 창에서 재할당 가능한 단축키 목록.

두 갈래를 하나로 묶는다:
  - "메뉴/툴바 액션"(QAction 기반, `host_ui.py._make_action`이 만드는 ~20종) — Qt가 이미
    `QAction.setShortcut()`으로 재할당을 지원한다.
  - "뷰 단축키"(도구 전환·복사/붙여넣기·undo 등, `core_view.py`가 raw key 비교로 처리하던
    것) — `_make_action`에 단축키를 안 건 이유(host_ui.py `_build_menu` 주석 참조)가
    "Qt 전역 단축키가 뷰의 keyPressEvent보다 먼저 가로챌 수 있어 이중 실행 위험"이었으므로,
    이 갈래는 QAction 경로에 태우지 않고 `core_view.py`가 이 레지스트리를 직접 조회해
    이벤트의 key+modifiers를 비교한다(같은 물리적 단축키가 두 경로에서 동시에 반응할
    위험이 구조적으로 없다).

값은 `QSettings("EasyCAD", "EasyCAD")`의 "shortcuts/<id>" 키에 저장 — 없으면 기본값.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

# (id, category, label, default_sequence). id는 안정적인 키 — 절대 재사용 금지(과거 id가
# 남아 있으면 그 사용자의 커스터마이즈가 조용히 유실된다).
SHORTCUT_DEFS: list[tuple[str, str, str, str]] = [
    # ---- 도구 전환 (view) ----
    # [2026-08-21 도형 단축키 폐지] "tool_rect"/"tool_ellipse"는 여기서 완전히 삭제됐다
    # (사각형·원이 좌측 팔레트 전용 클릭/드래그로 통일 — 나머지 6종 도형과 동일 취급).
    # 이 두 id는 위 규칙(id 재사용 금지)에 따라 앞으로도 재사용하지 않는다. 빈 2·5를
    # 포함해 나머지 도구는 상단 툴바 시각 순서 그대로 1~7로 재번호.
    ("tool_select",  "도구", "선택 도구",     "1"),
    ("tool_arrow",   "도구", "화살표 도구",   "2"),
    ("tool_text",    "도구", "텍스트 도구",   "3"),
    ("tool_line",    "도구", "선 도구",       "4"),
    ("tool_polygon", "도구", "다각형 도구",   "5"),
    ("tool_pen",     "도구", "펜 도구",       "6"),
    ("tool_badge",   "도구", "번호(배지) 도구", "7"),
    ("tool_trim",    "도구", "자르기(TRIM) 도구", "T"),
    ("stretch_arm",  "도구", "스트레치 무장(러버밴드 선택 후)", "S"),
    # ---- 편집 (view) ----
    ("select_all",  "편집", "전체 선택",       "Ctrl+A"),
    ("copy",        "편집", "복사",           "Ctrl+C"),
    ("paste",       "편집", "붙여넣기",        "Ctrl+V"),
    ("style_copy",  "편집", "스타일 복사",      "Ctrl+Alt+C"),
    ("style_paste", "편집", "스타일 붙여넣기",   "Ctrl+Alt+V"),
    ("duplicate",   "편집", "제자리 복제",      "Ctrl+D"),
    ("group",       "편집", "그룹",           "Ctrl+G"),
    ("ungroup",     "편집", "그룹 해제",       "Ctrl+Shift+G"),
    ("lock_toggle", "편집", "잠금 전환",       "Ctrl+L"),
    ("bring_front", "편집", "맨 앞으로",       "Ctrl+]"),
    ("send_back",   "편집", "맨 뒤로",         "Ctrl+["),
    ("delete",      "편집", "삭제",           "Del"),
    ("undo",        "편집", "되돌리기",        "Ctrl+Z"),
    ("redo",        "편집", "다시 실행",        "Ctrl+Y"),
    ("mirror_x",    "편집", "좌우 반전",       "Shift+H"),
    ("mirror_y",    "편집", "상하 반전",       "Shift+V"),
    # ---- 파일 (QAction) ----
    ("new_doc",     "파일", "새 탭",  "Ctrl+N"),
    ("new_window",  "파일", "새 창",       "Ctrl+Shift+N"),
    ("open_doc",    "파일", "열기",        "Ctrl+O"),
    ("save_doc",    "파일", "저장",        "Ctrl+S"),
    ("save_doc_as", "파일", "다른 이름으로 저장", "Ctrl+Shift+S"),
    ("export_pdf",  "파일", "내보내기", "Ctrl+P"),
    # ---- 삽입 (QAction) ----
    ("insert_titleblock", "삽입", "표제란/용지틀 삽입", "Ctrl+Shift+T"),
    ("insert_table",      "삽입", "표 삽입",            "Ctrl+Shift+B"),
    ("insert_image",      "삽입", "이미지/SVG 삽입",      "Ctrl+Shift+M"),
    ("insert_mermaid",    "삽입", "Mermaid 가져오기",     "Ctrl+Shift+F"),
    ("insert_ai_svg",     "삽입", "AI SVG 에셋 생성",     "Ctrl+Shift+A"),
    # ---- 보기 (QAction) ----
    ("zoom_100",     "보기", "100%(1:1)",     "Ctrl+0"),
    ("zoom_fit",     "보기", "전체 맞춤",      "Ctrl+9"),
    ("toggle_snap",  "보기", "스냅 토글",      "F3"),
    ("toggle_ortho", "보기", "직교 제약 토글",  "F8"),
    ("toggle_grid",  "보기", "격자 토글",      "Shift+G"),
    ("toggle_align", "보기", "정렬 가이드선 토글", "Shift+A"),
    ("toggle_theme", "보기", "다크/라이트 전환", "Ctrl+Shift+L"),
    # ---- 도움말 (QAction) ----
    ("show_help", "도움말", "단축키 도움말", "F1"),
]

_LABEL_BY_ID = {d[0]: d[2] for d in SHORTCUT_DEFS}
_DEFAULT_BY_ID = {d[0]: d[3] for d in SHORTCUT_DEFS}

# id → 도구 키(`current_tool`이 쓰는 문자열). `core_view.py`(뷰 단축키 매칭)와
# `host_ui.py`(도구(&T) 메뉴·상단 툴바 버튼 툴팁 표시)가 같은 매핑을 공유한다 —
# 두 파일이 각자 사본을 들면 하나만 고치고 잊는 드리프트가 생기기 쉽다.
TOOL_SHORTCUT_IDS: dict[str, str] = {
    "tool_select": "select", "tool_arrow": "arrow",
    "tool_text": "text", "tool_line": "line",
    "tool_pen": "pen", "tool_badge": "badge",
    "tool_polygon": "polygon", "tool_trim": "trim",
}
SHORTCUT_ID_BY_TOOL: dict[str, str] = {v: k for k, v in TOOL_SHORTCUT_IDS.items()}

_SETTINGS_ORG = "EasyCAD"
_SETTINGS_APP = "EasyCAD"


def default_sequence(shortcut_id: str) -> str:
    return _DEFAULT_BY_ID.get(shortcut_id, "")


def label_of(shortcut_id: str) -> str:
    return _LABEL_BY_ID.get(shortcut_id, shortcut_id)


def current_sequence(shortcut_id: str) -> str:
    """QSettings 저장값(있으면) 아니면 기본값. 매 호출 QSettings를 읽는다 — 단축키
    처리는 키 입력마다 한 번뿐이라 캐시 없이도 비용이 무시할 만함(측정 없이도 자명)."""
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    val = settings.value(f"shortcuts/{shortcut_id}")
    if val:
        return str(val)
    return default_sequence(shortcut_id)


def set_sequence(shortcut_id: str, sequence: str) -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(f"shortcuts/{shortcut_id}", sequence)


def reset_sequence(shortcut_id: str) -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.remove(f"shortcuts/{shortcut_id}")


def reset_all() -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.beginGroup("shortcuts")
    settings.remove("")
    settings.endGroup()


def all_sequences() -> dict[str, str]:
    return {d[0]: current_sequence(d[0]) for d in SHORTCUT_DEFS}
