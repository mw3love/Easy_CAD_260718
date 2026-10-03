"""자동 저장·복구 파일 관리 — 점검 1단계(파일 안전), 2026-10-03.

문서마다 고유 id를 하나 주고, 복구 폴더에 `<id>.ecad`(도면 자체)와 `<id>.json`(원래 경로·
제목·저장 시각·프로세스 번호)을 둔다. 원본 파일은 절대 건드리지 않는다(사용자 결정 —
별도 복구 폴더). 정상적으로 저장하거나 탭/창을 닫으면 지우고, 프로그램이 비정상
종료되면 남아 다음 실행 때 복구 후보가 된다.

복구 폴더는 크래시 로그(`crash_report._log_dir`)와 같은 앱 데이터 폴더 아래 `recovery` —
구글 드라이브·리포 밖이라 PC 사이 동기화로 섞이지 않는다. 테스트는 환경변수
`EASYCAD_RECOVERY_DIR`로 임시 폴더를 쓴다(실사용자 폴더 오염 방지, tests/conftest.py).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

from easycad.fileio.document import save_document
from easycad.fileio.safe_write import write_via_temp


def recovery_dir() -> str:
    env = os.environ.get("EASYCAD_RECOVERY_DIR")
    if env:
        base = env
    else:
        from PyQt6.QtCore import QCoreApplication, QStandardPaths
        # crash_report._log_dir와 같은 이유로 조직/앱 이름을 고정(dev·배포 경로 통일).
        QCoreApplication.setOrganizationName("EasyCAD")
        QCoreApplication.setApplicationName("EasyCAD")
        root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not root:
            root = os.path.join(os.path.expanduser("~"), ".easycad")
        base = os.path.join(root, "recovery")
    os.makedirs(base, exist_ok=True)
    return base


def new_id() -> str:
    return uuid.uuid4().hex


def _paths(doc_id: str) -> tuple[str, str]:
    d = recovery_dir()
    return os.path.join(d, doc_id + ".ecad"), os.path.join(d, doc_id + ".json")


def _write_meta(meta_path: str, meta: dict) -> None:
    def _w(tmp):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
    write_via_temp(meta_path, _w)


def write(doc_id: str, scene, layers, *, doc_path=None, external_path=None, title="") -> None:
    """문서를 복구 폴더에 저장한다(도면 먼저, 메타는 그 뒤 — 메타가 있으면 도면도 완성본)."""
    ecad, meta = _paths(doc_id)
    save_document(scene, ecad, layers=layers)
    _write_meta(meta, {"doc_path": doc_path, "external_path": external_path, "title": title,
                       "saved_at": time.time(), "pid": os.getpid()})


def claim(doc_id: str) -> None:
    """복구한 파일을 이 프로세스 소유로 표시(다른 실행 중인 Easy CAD가 또 복구 제안하지 않게)."""
    ecad, meta_path = _paths(doc_id)
    meta = _read_meta(meta_path)
    meta["pid"] = os.getpid()
    _write_meta(meta_path, meta)


def remove(doc_id: str | None) -> None:
    if not doc_id:
        return
    for p in _paths(doc_id):
        try:
            os.remove(p)
        except OSError:
            pass


def _read_meta(meta_path: str) -> dict:
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else {}
    except (OSError, ValueError):
        return {}


def _pid_alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        # os.kill(pid, 0)은 Windows에서 신호 0을 TerminateProcess로 처리해 **남의 프로세스를
        # 죽인다**(파이썬 문서) — 반드시 OpenProcess로 조회만 한다.
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == 259   # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def find_orphans() -> list[tuple[str, str, dict]]:
    """주인이 없는(=비정상 종료로 남은) 자동 저장 목록 [(id, .ecad 경로, meta)] — 오래된 순.
    지금 실행 중인 다른 Easy CAD가 쓰고 있는 파일(pid 살아 있음)은 뺀다."""
    out = []
    d = recovery_dir()
    for name in os.listdir(d):
        if not name.endswith(".ecad"):
            continue
        doc_id = name[:-5]
        ecad, meta_path = _paths(doc_id)
        meta = _read_meta(meta_path)
        if _pid_alive(meta.get("pid")):
            continue
        out.append((doc_id, ecad, meta))
    out.sort(key=lambda t: t[2].get("saved_at") or 0)
    return out
