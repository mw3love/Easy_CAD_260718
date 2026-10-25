"""§8 항목61 「정리해 줘」 ① 정리 문서 말 짐작(`easycad/ai/board_chat.guess_kind`) — 「정리해 줘」·보고서 = report, 주제가 붙으면 보통 짐작.
옛 ② 레고형 정리정돈(`board_tidy`)은 2026-10-25 사용자 판단으로 뺐다(완성도가 낮고 딥모드·정리 문서와 겹침 — 이 파일의 옛 이름 test_part62_tidy).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from easycad.ai import board_chat  # noqa: E402


def test_guess_kind_report():
    for q in ("정리해 줘", "주제별로 묶어서 보고서로", "한 장으로 정리해 줘"):
        assert board_chat.guess_kind(q) == "report", q
    assert board_chat.guess_kind("송신기 출력 몇이야") == "chat"


def test_guess_kind_report_needs_board_material():
    """「○○ 정리해 줘」 — 주제가 붙고 고른 게 없으면 정리 문서가 아니라 보통 짐작(2026-10-19 사용자 선택)."""
    for q in ("이거 정리해 줘", "칠판 내용 다 정리해 줘", "지금까지 모은 것 깔끔하게 정리해 주세요", "송신소 점검 결과 보고서로 정리해 줘"):
        assert board_chat.guess_kind(q) == "report", q
    assert board_chat.guess_kind("송신소 정전 대비 점검 순서 정리해줘 목록으로") == "chat"
    assert board_chat.guess_kind("지난번 송신기 회의 정리해 줘") == "board"
    assert board_chat.guess_kind("오늘 KBS 뉴스 정리해 줘") == "search"
    assert board_chat.guess_kind("송신소 점검 순서 정리해 줘", has_context=True) == "report"   # 고른 것이 있으면 그것으로 문서
