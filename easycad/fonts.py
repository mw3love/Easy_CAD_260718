"""앱에 같이 싣는 글꼴(§8 항목60 ②, 2026-10-17) — 보드 글을 어느 PC에서나 같은 모양·굵기로.

Pretendard(SIL OFL 1.1, `resources/fonts/Pretendard-OFL.txt`) 네 굵기만 싣는다: 보통·약간 굵게·굵게·아주 굵게.
윈도우 기본 맑은 고딕은 굵기가 보통·굵게 둘뿐이라 제목을 더 굵게 할 수 없었고, 사내 PC엔 Noto Sans KR이 없을 수 있다.
QApplication이 있어야 등록되므로 처음 쓸 때 등록한다(`board_family`). 못 읽으면 None — 그때는 앱 기본 글꼴 그대로.
"""
from __future__ import annotations

import sys
from pathlib import Path

BOARD_FONT = "Pretendard"
_FILES = ("Pretendard-Regular.otf", "Pretendard-SemiBold.otf", "Pretendard-Bold.otf", "Pretendard-ExtraBold.otf")
_loaded: bool | None = None


def fonts_dir() -> Path:
    base = Path(sys._MEIPASS) / "easycad" if hasattr(sys, "_MEIPASS") else Path(__file__).resolve().parent
    return base / "resources" / "fonts"


def ensure_fonts() -> bool:
    """실린 글꼴을 Qt에 한 번 등록 — 하나라도 들어가면 True."""
    global _loaded
    if _loaded is None:
        from PyQt6.QtGui import QFontDatabase
        ok = False
        for name in _FILES:
            p = fonts_dir() / name
            if p.is_file() and QFontDatabase.addApplicationFont(str(p)) >= 0:
                ok = True
        _loaded = ok
    return _loaded


def board_family() -> str | None:
    """보드 글꼴 이름 — 쓸 수 있으면 "Pretendard", 아니면 None."""
    return BOARD_FONT if ensure_fonts() else None


def apply_ui_font(app) -> bool:
    """앱 화면 글꼴(메뉴·버튼·패널)도 Pretendard로(2026-10-22 사용자 선택 — 웹 칠판과 같은 글꼴).
    까닭: 윈도우 맑은 고딕은 어두운 화면 메뉴에서 「제」 글자만 주황으로 그려짐(맑은 고딕 글자 다듬기 탓 — 팔레트와 무관, 실측).
    크기는 시스템 그대로, 못 읽으면 바꾸지 않음. 메뉴·도움말 풍선은 시스템이 따로 주는 글꼴이라 함께 바꿈.
    ⚠ Fusion 스타일을 켜면(`_apply_theme` 첫 호출) 메뉴 글꼴이 시스템 기본으로 되돌아감 — 창을 만든 뒤에 부를 것."""
    if not board_family():
        return False
    from PyQt6.QtGui import QFont
    for cls in (None, "QMenu", "QMenuBar", "QToolTip"):
        base = QFont(app.font(cls) if cls else app.font())
        base.setFamilies([BOARD_FONT, *[f for f in base.families() if f != BOARD_FONT]])
        if cls:
            app.setFont(base, cls)
        else:
            app.setFont(base)
    return True
