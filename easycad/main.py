"""Easy CAD 진입점 — 무한 캔버스 편집기를 띄운다."""
import sys

from PyQt6.QtWidgets import QApplication

from easycad.canvas.host import CanvasWindow
from easycad.crash_report import init_crash_reporting


def main():
    app = QApplication(sys.argv)
    init_crash_reporting()
    win = CanvasWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
