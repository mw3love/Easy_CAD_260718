"""전역 크래시 리포터 — 처리 안 된 예외를 로컬 로그+Sentry로 남기고 오류창을 띄운다.

배경: PyQt6은 Qt 슬롯/가상함수 안에서 처리 안 된 파이썬 예외가 있으면 기본적으로
`qFatal()`→`abort()`로 프로세스를 통째로 죽인다 — 이 프로젝트가 겪은 실사용 크래시
(2026-08-23 Mermaid/SVG 생성창 X닫기, 2026-08-26 그룹 큐닷 등, `docs/history/2026-08.md`
참조)가 전부 이 경로였다. `sys.excepthook`을 직접 설치하면 이 abort 자체가 일어나지
않고 이벤트루프가 계속 살아있는다 — 그래서 이 모듈은 "리포트 전송" 이전에 그 자체로
이 클래스의 크래시를 예방하는 효과가 있다. 단, 진짜 네이티브 크래시(메모리 손상 등
파이썬 예외가 아닌 것)는 이 방식으로 못 잡는다 — 그건 별도 영역(OS 크래시덤프).

Sentry DSN은 쓰기전용 공개키라 소스에 그대로 박아도 안전하다(Sentry 공식 설계 — 읽기
권한이 없어 계정 탈취로 못 이어짐). 도입 절차: sentry.io 무료 가입 → 새 Python 프로젝트
생성 → 발급된 DSN을 아래 `_SENTRY_DSN`에 붙여넣기만 하면 된다. 비어 있는 동안은 원격
전송 없이 로컬 로그(`%APPDATA%/EasyCAD/logs/crash.log`)만 남는다.

⚠ 개인정보 참고: Sentry 기본 설정은 각 스택 프레임의 지역변수 값까지 함께 캡처한다
(디버깅에 유용 — 예: 어떤 파일 경로를 열다 실패했는지). 그 값에 Windows 사용자명이 섞인
파일 경로 정도는 포함될 수 있으니, 이 앱을 본인 외 다른 사람에게 배포한다면 그 점을
안내하는 편이 좋다.
"""
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback

from PyQt6.QtCore import QCoreApplication, QStandardPaths
from PyQt6.QtWidgets import QApplication, QMessageBox

from easycad import __version__ as _APP_VERSION

_SENTRY_DSN = ""  # sentry.io 프로젝트 생성 후 여기 붙여넣기 (쓰기전용 키, 노출돼도 안전)

_logger = logging.getLogger("easycad.crash")
_sentry_ready = False
_log_path = ""
_last_dialog_at: dict[tuple, float] = {}
_DIALOG_COOLDOWN_SEC = 3.0  # 같은 예외가 짧은 시간에 반복(예: paint() 루프)돼도 창은 1번만


def _log_dir() -> str:
    # QCoreApplication은 조직/앱 이름을 명시 안 하면 실행 파일명(dev: "python", 배포:
    # "EasyCAD")으로 자동 채워 QStandardPaths 경로가 dev/배포 간 갈린다(실측 확인) —
    # gateway.py/shortcuts.py의 QSettings 관례("EasyCAD")와 맞춰 무조건 덮어쓴다(다른
    # 곳의 QSettings(org, app) 직접 호출엔 영향 없음, 이 프로퍼티를 읽는 코드도 없음).
    QCoreApplication.setOrganizationName("EasyCAD")
    QCoreApplication.setApplicationName("EasyCAD")
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".easycad")
    path = os.path.join(base, "logs")
    os.makedirs(path, exist_ok=True)
    return path


def _init_local_log() -> str:
    path = os.path.join(_log_dir(), "crash.log")
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.ERROR)
    return path


def init_crash_reporting() -> str:
    """main()에서 QApplication 생성 직후 1회 호출. 로컬 로그 경로를 반환한다."""
    global _sentry_ready, _log_path
    if _log_path:
        return _log_path  # 이중호출 방지
    _log_path = _init_local_log()
    if _SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=_SENTRY_DSN,
                release=f"easycad@{_APP_VERSION}",
                traces_sample_rate=0.0,
            )
            _sentry_ready = True
        except Exception:
            _logger.exception("Sentry 초기화 실패 — 로컬 로그만 사용")
    sys.excepthook = _handle_exception
    threading.excepthook = _handle_thread_exception
    return _log_path


def _report(exc_type, exc, tb) -> str:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    _logger.error(text)
    if _sentry_ready:
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except Exception:
            _logger.exception("Sentry 전송 실패")
    return text


def _should_show_dialog(key) -> bool:
    now = time.monotonic()
    last = _last_dialog_at.get(key, 0.0)
    if now - last < _DIALOG_COOLDOWN_SEC:
        return False
    _last_dialog_at[key] = now
    return True


def _handle_exception(exc_type, exc, tb):
    text = _report(exc_type, exc, tb)
    if not _should_show_dialog((exc_type, str(exc))):
        return
    try:
        _show_dialog(exc_type, exc, text)
    except Exception:
        _logger.exception("오류창 표시 자체가 실패")


def _handle_thread_exception(args):
    # 백그라운드 스레드에서 다이얼로그를 직접 띄우는 건 Qt에서 안전하지 않아 로그+전송만.
    _report(args.exc_type, args.exc_value, args.exc_traceback)


def _show_dialog(exc_type, exc, full_text: str):
    app = QApplication.instance()
    if app is None:
        return
    sent_note = (
        "개발자에게 자동으로 오류 리포트가 전송되었습니다."
        if _sentry_ready
        else "(원격 리포트 기능이 아직 꺼져 있어 로컬 로그에만 남았습니다.)"
    )
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("예상치 못한 오류")
    box.setText(f"작업 중 예상치 못한 오류가 발생했습니다.\n{sent_note}")
    box.setInformativeText(f"{exc_type.__name__}: {exc}")
    box.setDetailedText(full_text)
    box.setStandardButtons(QMessageBox.StandardButton.Ignore | QMessageBox.StandardButton.Close)
    box.button(QMessageBox.StandardButton.Ignore).setText("계속 사용")
    box.button(QMessageBox.StandardButton.Close).setText("지금 종료")
    box.setDefaultButton(QMessageBox.StandardButton.Ignore)
    ret = box.exec()
    if ret == QMessageBox.StandardButton.Close:
        app.quit()
