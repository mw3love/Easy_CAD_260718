"""§8 항목42(2026-10-16) — 「그림으로 복사(한글·PPT)」: 내용 크기 흰 바탕 그림을 클립보드에.

선택이 있으면 선택만, 없으면 전체. 3배 해상도(긴 변 상한), 다크 테마여도 흰 바탕·검은 잉크.
"""
from _shared import *  # noqa: F401,F403

from PyQt6.QtGui import QColor, QPen

from easycad.fileio.pdf_export import render_content_image


def _rect(scene, x, y, w, h, color="#1b222b"):
    it = _RectItem(QRectF(x, y, w, h))
    p = QPen(QColor(color))
    p.setWidthF(3.0)
    it.setPen(p)
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    scene.addItem(it)
    return it


def _dark_pixels(img) -> int:
    n = 0
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            if img.pixelColor(x, y).lightness() < 100:
                n += 1
    return n


def test_empty_scene_gives_null_image():
    w = CanvasWindow()
    assert render_content_image(w._scene).isNull()


def test_content_fit_white_background_and_scale():
    w = CanvasWindow()
    _rect(w._scene, 0, 0, 100, 50)
    img = render_content_image(w._scene, scale=3.0, pad=16.0)
    br = w._scene.itemsBoundingRect()
    assert abs(img.width() - round((br.width() + 32) * 3)) <= 1
    assert abs(img.height() - round((br.height() + 32) * 3)) <= 1
    assert img.pixelColor(2, 2).name() == "#ffffff"           # 흰 바탕(한글·PPT에 붙였을 때)
    assert _dark_pixels(img) > 0                              # 선이 실제로 그려짐


def test_selection_only_crops_and_hides_others():
    w = CanvasWindow()
    a = _rect(w._scene, 0, 0, 100, 50)
    _rect(w._scene, 400, 0, 100, 50)
    full = render_content_image(w._scene)
    a.setSelected(True)
    part = render_content_image(w._scene, selection_only=True)
    assert part.width() < full.width() / 2
    assert a.isSelected(), "그린 뒤 선택은 원래대로"


def test_long_side_capped():
    w = CanvasWindow()
    _rect(w._scene, 0, 0, 5000, 100)
    img = render_content_image(w._scene, max_side=2000)
    assert max(img.width(), img.height()) <= 2000


def test_dark_theme_white_ink_prints_black():
    w = CanvasWindow()
    _rect(w._scene, 0, 0, 100, 50, color="#ffffff")   # 다크 테마 흰 선
    img = render_content_image(w._scene)
    assert _dark_pixels(img) > 0, "흰 잉크는 인쇄 규칙대로 검정"


def test_action_copies_to_clipboard_with_toast():
    w = CanvasWindow()
    w._copy_as_image()
    assert "없어요" in w._toast.currentMessage()
    _rect(w._scene, 0, 0, 100, 50)
    w._copy_as_image()
    img = QApplication.clipboard().image()
    assert not img.isNull() and img.width() > 300
    assert "전체" in w._toast.currentMessage()


def test_menu_toolbar_shortcut():
    w = CanvasWindow()
    a = w._act_copy_img
    assert a.text() == "그림으로 복사(한글·PPT)"
    assert a.shortcut().toString() == "Ctrl+Shift+C"
    assert a in w._toolbar.actions() and a.iconText() == "그림 복사"
    from easycad.canvas.host_widgets import _SVG_ACT_ICON_NAMES
    assert "copy_image" in _SVG_ACT_ICON_NAMES, "SVG 목록에 없으면 상단바에 빈 아이콘(실제 창에서 발견)"
