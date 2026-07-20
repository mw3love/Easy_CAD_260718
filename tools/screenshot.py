"""오프스크린 스크린샷 — 앱 창(상단 툴바 + 왼쪽 「도형」 팔레트 + 캔버스)을 PNG로 렌더한다.

목적: GUI를 띄우지 않고도 **레이아웃·렌더링을 눈으로 검증**한다(Claude 자체검증 / CI 시각 회귀).
GUI 상호작용 '느낌'(hover·라이브 드래그·스냅 타이밍)은 이 도구로 못 잡는다 — 그건 실제 창이 필요.

⚠ 헤드리스 폰트 한계: 오프스크린 환경에 한글 폰트가 없으면 텍스트 글리프가 □(두부박스)로 뜬다.
   레이아웃·도형·아이콘·색·위치는 정확하지만 **한글 텍스트 내용은 이 렌더로 확인 불가**(실화면은 정상).

사용법:
    python tools/screenshot.py                 # 대표 데모 장면 → tools/_shot.png
    python tools/screenshot.py out.png         # 출력 경로 지정
    python tools/screenshot.py out.png --doc a.ecad   # 실제 .ecad 문서를 렌더
    python tools/screenshot.py --empty         # 빈 캔버스(툴바·팔레트만 확인)
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QBrush, QColor, QPen

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import _SymbolItem, _RectItem, _EllipseItem, _ArrowItem
from easycad.fileio.document import load_document


def _demo_scene(w):
    """대표 장면 — 기본 도형·심볼·중앙 라벨·포트 부착 화살표를 한 화면에."""
    sc = w._scene

    def pen():
        p = QPen(QColor("#e02424")); p.setWidthF(3.0)
        p.setCapStyle(Qt.PenCapStyle.RoundCap); return p

    def add(it, x, y, label=None):
        it.setPen(pen()); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
        it.setPos(QPointF(x, y)); sc.addItem(it)
        if label is not None:
            it.ensure_label().setPlainText(label); it._sync_label()
        return it

    add(_RectItem(QRectF(0, 0, 150, 90)), -300, -200, "처리 A")
    add(_SymbolItem("decision", QRectF(0, 0, 160, 100)), 100, -220, "판단?")
    add(_EllipseItem(QRectF(0, 0, 140, 90)), -280, 40, "시작")
    add(_SymbolItem("database", QRectF(0, 0, 120, 100)), 150, 60, "저장")
    ar = _ArrowItem(QColor("#1f6feb"), 4, True)
    ar.set_points(QPointF(-150, -155), QPointF(180, -170)); sc.addItem(ar)


def main(argv):
    out = "tools/_shot.png"
    doc = None
    empty = False
    args = list(argv)
    if "--empty" in args:
        empty = True; args.remove("--empty")
    if "--doc" in args:
        i = args.index("--doc"); doc = args[i + 1]; del args[i:i + 2]
    if args:
        out = args[0]

    app = QApplication.instance() or QApplication([])
    w = CanvasWindow()
    w.resize(1200, 760)
    w.show()

    if doc:
        load_document(w._scene, doc)
        w._zoom_fit()
    elif not empty:
        _demo_scene(w)
        w._zoom_fit()

    app.processEvents(); app.processEvents()
    out_abs = os.path.abspath(out)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    if not w.grab().save(out_abs):
        print("FAILED to save", out_abs); return 1
    print("SAVED", out_abs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
