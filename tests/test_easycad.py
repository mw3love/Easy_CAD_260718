"""Easy CAD 회귀 스모크 — 전체 스위트 진입점(하위호환 shim).

실행: python tests/test_easycad.py   (또는 pytest tests/)
GUI 없이 QT_QPA_PLATFORM=offscreen으로 구성·렌더·직렬화·지속연결을 확인한다.
실조건(실제 창 조작)은 python run.py로 별도 확인.

2026-08-02: 원본 7181줄 단일 파일을 `tests/_shared.py`(공용 헬퍼) +
`tests/test_part1_ui_arrows.py` ~ `test_part6_grid_minimap_layers.py`(테마별 테스트)로
분할했다. 이 파일은 예전과 동일한 진입점(`python tests/test_easycad.py`)을 유지하기
위한 얇은 집계 shim — 실제 테스트 345종은 전부 test_part*.py에 있고, `pytest tests/`로도
개별 파일 단위로 실행할 수 있다.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_part1_ui_arrows as _p1
import test_part2_labels_routing as _p2
import test_part3_transform_snap as _p3
import test_part4_ports_fileio as _p4
import test_part5_precision_edit as _p5
import test_part6_grid_minimap_layers as _p6
import test_part7_symbol_library as _p7

_PARTS = [_p1, _p2, _p3, _p4, _p5, _p6, _p7]


def _run_all():
    tests = []
    for mod in _PARTS:
        tests += [v for k, v in sorted(vars(mod).items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"ALL {len(tests)} TESTS PASSED")


if __name__ == "__main__":
    _run_all()
