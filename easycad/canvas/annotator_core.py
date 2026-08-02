"""Easy CAD 캔버스 코어 — pasteflow 주석 편집기를 verbatim 이식 + 우리 확장(지속연결·
직교 라우팅·포트·정렬 등)한 무한캔버스 아이템·뷰(`_AnnotatorView`) 모듈. 실제 호스트
윈도우는 `easycad/canvas/host.py`의 `CanvasWindow`.

도구 단축키: 1 선택 · 2 네모 · 3 화살표 · 4 텍스트 · 5 원 · 6 선 · 7 펜 · 8 번호.
Shift: 정사각형/정원/45° 스냅. 선택 후 우하단 핸들 드래그로 크기조절(균일 스케일).

2026-08-02 문서/코드 분할 — 원래 이 파일 하나(8169줄)에 전부 있던 것을 세 파일로 나눴다:
`core_constants.py`(상수·아이콘, ~420줄) · `core_shapes.py`(핸들믹스인+아이템+기하/라우팅
엔진, ~5300줄 — 셋이 실제로 서로를 호출하는 순환 의존이라 안전하게 더 못 쪼갬) ·
`core_view.py`(`_AnnotatorView`, ~2470줄). 이 파일은 셋을 전부 재수출하는 얇은 shim —
`from easycad.canvas.annotator_core import X` 형태의 기존 호출부(host*.py·fileio/*·
tests·tools 전부)를 한 줄도 안 고치기 위해서다. 실제로 코드를 고칠 땐 위 세 파일 중
해당 내용이 실제로 있는 파일을 연다(이 파일엔 정의가 없다).
"""
from easycad.canvas.core_constants import *  # noqa: F401,F403
from easycad.canvas.core_shapes import *  # noqa: F401,F403
from easycad.canvas.core_view import *  # noqa: F401,F403
