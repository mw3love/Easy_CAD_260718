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
    # [첫 화면 재디자인 2026-10-07, 사용자 결정] 새 상단바(아이콘+글자)는 약 1,300px라 기본 창
    # 1200×800엔 다 안 들어간다 — 처음엔 최대화로 켠다(창을 줄이면 넘친 버튼은 » 목록으로).
    win.showMaximized()
    # [점검 1단계 2026-10-03] 지난번 비정상 종료로 남은 자동 저장이 있으면 복구를 묻는다.
    QTimer.singleShot(0, win._offer_recovery)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
