"""Easy CAD 진입점 — 무한 캔버스 편집기를 띄운다."""
import sys

from PyQt6.QtWidgets import QApplication

from easycad.canvas.host import CanvasWindow


def main():
    app = QApplication(sys.argv)
    win = CanvasWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
