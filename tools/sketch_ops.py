"""사진→도면 실험용: 모델이 낸 "ops" JSON 명세를 .ecad로 만들고, 원본 사진과 같은 틀로 렌더한다.

2026-10-01 실험(`docs/history/2026-10.md` "사진→도면 재실험")에서 쓴 도구를 리포로 옮긴 것.
변환 본체와 ops 어휘 설명은 앱 모듈 `easycad/fileio/photo_ops.py`로 옮겼다(§8 항목28 1단계) —
여기는 .ecad 저장·렌더 래퍼만 남는다. 개발용.

사용법:
    python tools/sketch_ops.py spec.json out.ecad [out.png 1252x733]   # .ecad 생성(+원본 크기로 렌더)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycad.fileio.photo_ops import SCALE, ops_to_sketch


def build(spec: dict, out: str, *, dark: bool = False, scale: float = SCALE) -> tuple[int, int]:
    """ops 명세 → .ecad 저장. 반환 (아이템 수, 건너뛴 op 수). 잘못된 op는 건너뛰고 셈만 한다."""
    s, skipped = ops_to_sketch(spec, dark=dark, scale=scale)
    return s.save(out), skipped


def render(ecad: str, out: str, size: tuple[int, int], *, scale: float = SCALE) -> None:
    """원본 사진 프레임(0,0)~size를 흰 배경으로 렌더 — 원본과 1:1로 겹쳐 비교하기 위함.
    실제 CanvasWindow에 불러와 그리므로(오프스크린이 아니면) 한글 글꼴까지 실화면과 같다."""
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QImage, QPainter, QColor
    from PyQt6.QtCore import QRectF
    from easycad.canvas.host import CanvasWindow
    from easycad.fileio.document import load_document

    app = QApplication.instance() or QApplication([])
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    load_document(w._scene, ecad)
    for _ in range(5):
        app.processEvents()
    sc = w._scene
    sc.clearSelection()
    sc.setBackgroundBrush(QColor("#ffffff"))
    img = QImage(size[0], size[1], QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    sc.render(p, QRectF(0, 0, size[0], size[1]), QRectF(0, 0, size[0] * scale, size[1] * scale))
    p.end()
    img.save(out)
    w.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    n, sk = build(spec, sys.argv[2])
    print(f"items={n} skipped={sk}")
    if len(sys.argv) > 4:
        wh = tuple(int(v) for v in sys.argv[4].lower().split("x"))
        render(sys.argv[2], sys.argv[3], wh)
        print("rendered", sys.argv[3])
