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
