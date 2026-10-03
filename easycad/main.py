"""Easy CAD 진입점 — 무한 캔버스 편집기를 띄운다."""
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from easycad.canvas.host import CanvasWindow
from easycad.crash_report import init_crash_reporting


def main():
    app = QApplication(sys.argv)
    init_crash_reporting()
    win = CanvasWindow()
    win.show()
    # [점검 1단계 2026-10-03] 지난번 비정상 종료로 남은 자동 저장이 있으면 복구를 묻는다.
    QTimer.singleShot(0, win._offer_recovery)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
