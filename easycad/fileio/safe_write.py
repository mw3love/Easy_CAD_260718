"""안전 저장 — 임시 파일에 먼저 다 쓰고, 성공했을 때만 대상 파일과 바꿔치기한다.

[점검 1단계 — 파일 안전, 2026-10-03] 예전 `.ecad`/DXF 저장은 대상 파일을 직접 열어 썼다 —
쓰는 도중 크래시·전원 차단·직렬화 예외가 나면 원래 파일까지 반쯤 쓰인 채 깨졌다.
`symbol_library._save_raw`(2026-08 왕복 점검 때 같은 이유로 먼저 고침)와 같은 원리:
`os.replace`는 같은 볼륨 안에서 Windows·POSIX 둘 다 원자적이라(표준 라이브러리 보증)
쓰기가 어디서 끊기든 대상 파일은 항상 "이전 완성본" 아니면 "새 완성본" 둘 중 하나다.

[§8 항목61 2026-10-19] 웹 칠판 서버는 여러 요청을 동시에 처리한다 — 같은 파일(대화 기록)을 두 요청이 거의 동시에 저장하면
같은 임시 파일을 두고 부딪혀 Windows에서 `PermissionError`(액세스 거부)가 났다(화면 시험 flow16). 같은 대상은 잠금으로 한 줄로 세우고,
다른 프로그램(백신·탐색기 미리보기)이 대상을 잠깐 잡고 있으면 짧게 다시 시도한다.
"""
from __future__ import annotations

import os
import threading
import time

_LOCKS: dict = {}
_LOCKS_GUARD = threading.Lock()
_RETRIES = 20          # 바꿔치기 다시 시도(Windows가 대상·임시 파일을 잠깐 잡고 있을 때)
_RETRY_SLEEP = 0.05


def _lock_for(path: str) -> threading.Lock:
    key = os.path.normcase(os.path.abspath(path))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def _replace(tmp: str, path: str) -> None:
    for i in range(_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == _RETRIES - 1:
                raise
            time.sleep(_RETRY_SLEEP)


def write_via_temp(path: str, writer) -> None:
    """`writer(tmp_path)`로 같은 폴더의 임시 파일에 쓰게 한 뒤 `path`로 바꿔치기한다.

    writer가 예외를 던지면 임시 파일만 지우고 그 예외를 그대로 다시 던진다(대상 `path`는
    한 번도 안 건드림). 임시 파일은 대상과 같은 폴더에 둔다 — 다른 드라이브면
    `os.replace`가 원자적이지 않거나 아예 실패하기 때문. 같은 대상을 동시에 쓰면 차례로(잠금)."""
    tmp = path + ".tmp"
    with _lock_for(path):
        try:
            writer(tmp)
            _replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
