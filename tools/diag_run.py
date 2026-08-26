"""진단용 런처 — "예외 메시지도 없이 조용히 죽는" 네이티브 크래시의 원인을 잡는다.

목적: PyQt6 앱이 특정 조작 몇 번 만에 프로세스째 사라질 때, 크래시 **직전**의 Qt/Python
메시지를 파일에 즉시 flush해 남긴다. 평범한 실행(`python run.py`)은 stderr가 블록
버퍼링돼 `abort()` 시 통째로 유실되고, `run.pyw`(pythonw.exe)는 콘솔 자체가 없다.

배경(2026-08-26, 실제로 이걸로 잡은 버그): Mermaid/SVG 생성창을 2~6번 열고 X로 닫으면
앱이 죽던 크래시. minidump를 보니 exception `0xC0000409` + `ExceptionInformation[0] == 7`
(`FAST_FAIL_FATAL_APP_EXIT`)였다 — **메모리 손상이 아니라 누군가 `abort()`를 명시적으로
불렀다**는 뜻이고, PyQt6에서 이건 대부분 **Qt 가상함수/슬롯 안에서 처리 안 된 파이썬
예외**다(PyQt6가 traceback을 stderr에 찍고 `qFatal()`→`abort()`). 이 런처로 그
traceback을 그대로 받아 원인(죽은 QThread 래퍼 참조)을 한 번에 특정했다.

⚠ **이 런처로는 크래시가 재현되지 않는다** — 커스텀 `sys.excepthook`을 설치하면 PyQt6가
abort를 하지 않기 때문이다. 그 자체가 "파이썬 예외가 원인"이라는 강력한 증거지만,
**수정 검증은 반드시 평범한 `python run.py`로** 따로 해야 한다(그래야 실제 abort 경로가
살아 있다). 이 런처는 "원인 포착"용이지 "수정 확인"용이 아니다.

사용법:
    python tools/diag_run.py                       # 로그: tools/_diag.log
    EASYCAD_DIAG_LOG=C:/tmp/x.log python tools/diag_run.py

읽는 법:
    grep -v "^\\[INFO\\]" tools/_diag.log      # 실제 문제만
    grep -c "EXCEPTHOOK" tools/_diag.log       # 예외 발생 횟수(수정 전/후 비교용)

관련: minidump 파싱은 `pip install minidump` 후
`%LOCALAPPDATA%\\CrashDumps\\*.dmp`를 열어 `mf.exception.exception_records[0]`의
`ExceptionRecord.ExceptionInformation`(fastfail 코드)까지 볼 것.
"""
import faulthandler
import os
import sys
import threading
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # 리포 루트 — tools/에서 실행해도 easycad 임포트

LOG = os.environ.get("EASYCAD_DIAG_LOG", os.path.join(_HERE, "_diag.log"))

_log_lock = threading.Lock()


def _write(tag, text):
    """즉시 flush + fsync — 다음 줄에서 프로세스가 죽어도 남아야 하므로 버퍼링 금지."""
    with _log_lock:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"[{tag}] {text}\n")
            f.flush()
            os.fsync(f.fileno())


with open(LOG, "w", encoding="utf-8") as _f:
    _f.write("=== diag start ===\n")

# ⓐ faulthandler — 진짜 네이티브 크래시(세그폴트 등)면 파이썬 스택이라도 남긴다.
_fh = open(LOG + ".faulthandler", "w", encoding="utf-8")
faulthandler.enable(file=_fh, all_threads=True)


class _TeeStderr:
    """ⓑ stderr 미러링 — PyQt6가 abort() 직전 찍는 traceback을 붙잡는 핵심 경로."""

    def __init__(self, orig):
        self._orig = orig

    def write(self, s):
        try:
            if self._orig is not None:
                self._orig.write(s)
                self._orig.flush()
        except Exception:
            pass
        if s.strip():
            _write("STDERR", s.rstrip("\n"))
        return len(s)

    def flush(self):
        try:
            if self._orig is not None:
                self._orig.flush()
        except Exception:
            pass


sys.stderr = _TeeStderr(sys.stderr)


def _hook(exc_type, exc, tb):   # ⓒ 처리 안 된 파이썬 예외
    _write("EXCEPTHOOK", "".join(traceback.format_exception(exc_type, exc, tb)))


sys.excepthook = _hook


def _thook(args):
    _write("THREAD-EXCEPTHOOK",
           "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


threading.excepthook = _thook

from PyQt6.QtCore import qInstallMessageHandler, QtMsgType  # noqa: E402

_MSG_NAMES = {
    QtMsgType.QtDebugMsg: "QtDebug",
    QtMsgType.QtInfoMsg: "QtInfo",
    QtMsgType.QtWarningMsg: "QtWarning",
    QtMsgType.QtCriticalMsg: "QtCritical",
    QtMsgType.QtFatalMsg: "QtFATAL",
}


def _qt_handler(mode, context, message):   # ⓓ Qt 자신의 메시지(qWarning/qFatal 등)
    name = _MSG_NAMES.get(mode, str(mode))
    where = ""
    try:
        if context.file:
            where = f" ({context.file}:{context.line}, {context.function})"
    except Exception:
        pass
    _write(name, f"{message}{where}")
    if mode == QtMsgType.QtFatalMsg:
        _write("QtFATAL-PYSTACK", "".join(traceback.format_stack()))


qInstallMessageHandler(_qt_handler)

_write("INFO", f"python={sys.version}")
_write("INFO", f"log={LOG}")

from easycad.main import main  # noqa: E402

if __name__ == "__main__":
    try:
        main()
    except BaseException:
        _write("MAIN-EXC", traceback.format_exc())
        raise
    finally:
        _write("INFO", "main() returned normally")
