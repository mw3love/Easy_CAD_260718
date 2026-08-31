"""크래시 리포터(easycad/crash_report.py) — 예외 로깅·debounce·excepthook 설치/복원 검증.

⚠ 이 스위트는 `_shared.py`가 강제하는 오프스크린 플랫폼에서 돈다. "PyQt6 슬롯 예외가
`abort()` 대신 살아남는다"는 실조건 확인(exit 127 → exit 0)은 실제 창(오프스크린 아님)
으로 별도 실행해 확인했다(2026-08-31 세션 기록 참조) — 여기서는 모듈 자체 로직(로그
기록·debounce·훅 설치/복원)만 검증한다.

⚠ `sys.excepthook`/`threading.excepthook`은 전역 상태라 프로세스 전체(전체 스위트 실행)에
영향을 준다 — 모든 테스트가 `_reset()`으로 원래 값을 저장해뒀다가 반드시 복원한다(2026-08-15
QTimer 지연생성 스턱루프 사례와 같은 계열: 전역 상태를 건드리는 테스트는 순서 무관하게
스위트 전체를 오염시킬 수 있다)."""
import os
import sys
import threading
import uuid
from unittest.mock import patch

from _shared import *  # noqa: F401,F403

from easycad import crash_report


def _reset():
    """이전 테스트가 뭘 남겼든 모듈 전역을 깨끗한 상태로."""
    crash_report._log_path = ""
    crash_report._sentry_ready = False
    crash_report._last_dialog_at.clear()


def test_init_crash_reporting_installs_and_restores_hooks():
    orig_exc, orig_thread_exc = sys.excepthook, threading.excepthook
    _reset()
    log_dir = os.path.join(_TMP, f"crashlog_{uuid.uuid4().hex}")
    os.makedirs(log_dir, exist_ok=True)
    try:
        with patch.object(crash_report, "_log_dir", return_value=log_dir):
            path = crash_report.init_crash_reporting()
        assert os.path.exists(path)
        assert sys.excepthook is crash_report._handle_exception
        assert threading.excepthook is crash_report._handle_thread_exception
        # 이중호출 방지 — 같은 경로를 그대로 반환하고 재초기화하지 않음.
        with patch.object(crash_report, "_log_dir", return_value=log_dir + "_other"):
            assert crash_report.init_crash_reporting() == path
    finally:
        sys.excepthook = orig_exc
        threading.excepthook = orig_thread_exc
        _reset()


def test_report_writes_traceback_to_log_file():
    _reset()
    log_dir = os.path.join(_TMP, f"crashlog_{uuid.uuid4().hex}")
    os.makedirs(log_dir, exist_ok=True)
    try:
        with patch.object(crash_report, "_log_dir", return_value=log_dir):
            path = crash_report._init_local_log()
        try:
            raise ValueError("한글 메시지 포함 예외")
        except ValueError:
            crash_report._report(*sys.exc_info())
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "ValueError" in content
        assert "한글 메시지 포함 예외" in content
    finally:
        crash_report._logger.handlers.clear()
        _reset()


def test_dialog_debounce_suppresses_rapid_repeats():
    _reset()
    key = (ValueError, "동일 예외")
    assert crash_report._should_show_dialog(key) is True
    assert crash_report._should_show_dialog(key) is False  # 쿨다운 안 지남
    assert crash_report._should_show_dialog((KeyError, "다른 예외")) is True  # 다른 키는 무관
    _reset()


def test_handle_exception_logs_and_shows_dialog_once_per_cooldown():
    """excepthook 경로 전체(_report → debounce → _show_dialog) — 실제 QMessageBox는
    막아 오프스크린에서도 안전하게(모달 exec() 없이) 검증한다."""
    _reset()
    log_dir = os.path.join(_TMP, f"crashlog_{uuid.uuid4().hex}")
    os.makedirs(log_dir, exist_ok=True)
    calls = []
    try:
        with patch.object(crash_report, "_log_dir", return_value=log_dir):
            path = crash_report._init_local_log()
        with patch.object(crash_report, "_show_dialog", side_effect=lambda *a: calls.append(a)):
            try:
                raise RuntimeError("dialog test")
            except RuntimeError:
                crash_report._handle_exception(*sys.exc_info())
            try:
                raise RuntimeError("dialog test")
            except RuntimeError:
                crash_report._handle_exception(*sys.exc_info())  # 쿨다운 내 반복 → 창 안 뜸
        assert len(calls) == 1
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert content.count("RuntimeError: dialog test") == 2  # 로그는 매번 남음
    finally:
        crash_report._logger.handlers.clear()
        _reset()


def test_handle_thread_exception_never_touches_gui():
    """백그라운드 스레드 예외는 다이얼로그를 띄우지 않는다(Qt에서 위험) — 로그만."""
    _reset()
    log_dir = os.path.join(_TMP, f"crashlog_{uuid.uuid4().hex}")
    os.makedirs(log_dir, exist_ok=True)
    try:
        with patch.object(crash_report, "_log_dir", return_value=log_dir):
            path = crash_report._init_local_log()
        with patch.object(crash_report, "_show_dialog") as mock_dialog:
            class _Args:
                exc_type = ValueError
                exc_value = ValueError("thread boom")
                exc_traceback = None

            crash_report._handle_thread_exception(_Args())
        mock_dialog.assert_not_called()
        with open(path, encoding="utf-8") as f:
            assert "thread boom" in f.read()
    finally:
        crash_report._logger.handlers.clear()
        _reset()


def test_log_dir_pins_app_name_regardless_of_prior_qcoreapplication_state():
    """dev(`python run.py`)와 빌드된 exe가 같은 로그 경로를 쓰도록 org/app 이름을 고정한다
    (2026-08-31 실측: 안 고정하면 QStandardPaths가 실행 파일명을 그대로 폴더명으로 써서
    dev/배포 경로가 갈렸다)."""
    from PyQt6.QtCore import QCoreApplication
    d = crash_report._log_dir()
    assert os.path.isdir(d)
    assert QCoreApplication.organizationName() == "EasyCAD"
    assert QCoreApplication.applicationName() == "EasyCAD"
