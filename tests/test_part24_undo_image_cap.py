"""§8 항목35(2026-10-03) — 되돌리기 기록 상한. 사용자 결정: 그림 메모리만 제한(기록이 붙잡은 지운 그림이
`_UNDO_IMAGE_BUDGET`을 넘으면 가장 오래된 기록부터 버림). 도형 작업은 횟수 제한 없음."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPixmap

from _shared import *  # noqa: F401,F403
from easycad.canvas.annotator_core import _ImageItem, _RectItem

_IMG_BYTES = 100 * 100 * 4


def _add_and_delete_image(w):
    pm = QPixmap(100, 100)
    pm.fill(Qt.GlobalColor.gray)
    img = _ImageItem(pm, QRectF(0, 0, 100, 100))
    img.setFlags(img.GraphicsItemFlag.ItemIsSelectable | img.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(img)
    w.push_undo_add(img)
    w._scene.clearSelection()
    img.setSelected(True)
    w.delete_selection()
    return img


def test_deleted_images_over_budget_drop_oldest_history():
    w = CanvasWindow()
    w._UNDO_IMAGE_BUDGET = 3 * _IMG_BYTES
    imgs = [_add_and_delete_image(w) for _ in range(6)]
    assert w._history_image_bytes() <= 3 * _IMG_BYTES
    assert len(w._undo) < 12                              # 오래된 기록이 버려짐
    assert "정리했습니다" in w.statusBar().currentMessage()
    w.undo()                                               # 가장 최근 지우기는 그대로 되돌릴 수 있다
    assert imgs[-1].scene() is w._scene


def test_shape_history_is_not_limited():
    w = CanvasWindow()
    w._UNDO_IMAGE_BUDGET = 0
    for i in range(300):
        r = _RectItem(QRectF(0, 0, 10, 10))
        w._scene.addItem(r)
        w.push_undo_add(r)
    assert len(w._undo) == 300                             # 도형만이면 아무것도 안 버림


def test_images_still_in_scene_do_not_count():
    w = CanvasWindow()
    pm = QPixmap(100, 100)
    pm.fill(Qt.GlobalColor.gray)
    img = _ImageItem(pm, QRectF(0, 0, 100, 100))
    w._scene.addItem(img)
    w.push_undo_add(img)
    assert w._history_image_bytes() == 0                   # 씬에 있는 그림은 기록 탓이 아님
