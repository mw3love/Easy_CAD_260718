"""pytest가 tests/ 아래 무엇을 수집하든 가장 먼저 임포트하는 파일.

QT_QPA_PLATFORM/프로젝트 루트 sys.path는 _shared.py도 방어적으로 다시 설정하지만
(직접 `python tests/test_easycad.py` 실행 경로용), pytest 경로에서는 이 파일이
더 먼저 보장되므로 여기서도 동일하게 설정해 둔다.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def _isolate_gateway_settings(monkeypatch):
    """모든 테스트에 자동 적용 — AI 게이트웨이 QSettings 조직/앱 이름을 실사용자 값
    ("EasyCAD")에서 격리된 값으로 바꿔치기한다.

    2026-08-20 사고: `tests/test_part9_ai_mermaid.py`의 `_clear_gateway_settings()`가
    실사용자 레지스트리(`HKCU\\Software\\EasyCAD\\EasyCAD`)의 `ai_gateway_key`를 직접
    지우고 있었고, 복원 로직이 없어 pytest를 돌릴 때마다 사용자가 실제로 저장한 API 키가
    조용히 사라졌다("저장한 키가 앱을 껐다 켜면 사라진다"던 재현 안 되던 버그의 실제
    원인). `_isolated_symbol_library()`(_shared.py)와 동일한 관례로, 앱 코드를 건드리지
    않고 QSettings의 진입점(`easycad.ai.gateway._SETTINGS_ORG/_SETTINGS_APP`)만 세션
    전체에서 격리해 원천 차단한다."""
    monkeypatch.setattr("easycad.ai.gateway._SETTINGS_ORG", "EasyCAD-pytest")
    monkeypatch.setattr("easycad.ai.gateway._SETTINGS_APP", "EasyCAD-pytest")
