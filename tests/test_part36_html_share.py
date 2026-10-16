"""§8 항목46(2026-10-16) — 「HTML로 공유」: 브라우저로 여는 파일 하나(레이어별 SVG + 확대·이동 + 상자 정보).

브라우저 조작(확대·상자 누르기·레이어 끄기)은 실제 Chrome에서 시험 스크립트로 확인(history) — 여기선 파일 내용과
그리는 동안 바꾼 씬 상태가 전부 되돌아오는지.
"""
import json
import re

from _shared import *  # noqa: F401,F403

from PyQt6.QtGui import QColor, QPen

from easycad.fileio.html_share import build_html, export_html


def _rect(scene, x, y, color="#1b222b", label=None):
    it = _RectItem(QRectF(x, y, 100, 50))
    p = QPen(QColor(color))
    p.setWidthF(2.0)
    it.setPen(p)
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    scene.addItem(it)
    return it


def _read(path):
    return open(path, encoding="utf-8").read()


def _json_after(text, name):
    m = re.search(r"var " + name + r" = (\[.*?\]);", text, re.S)
    return json.loads(m.group(1))


def test_empty_scene_is_false(tmp_path):
    w = CanvasWindow()
    assert export_html(w._scene, str(tmp_path / "a.html"), "t", [], []) is False


def test_layers_and_shapes_go_into_one_file(tmp_path):
    w = CanvasWindow()
    a = _rect(w._scene, 0, 0)
    b = _rect(w._scene, 300, 0)
    path = str(tmp_path / "share.html")
    assert export_html(w._scene, path, "결재 흐름", [("기본", [a], True), ("메모", [b], False)], [(a, "휴가 신청")])
    text = _read(path)
    assert "<title>결재 흐름</title>" in text
    assert 'data-layer="0"' in text and 'data-layer="1" style="display:none"' in text
    assert [ly["name"] for ly in _json_after(text, "LAYERS")] == ["기본", "메모"]
    shapes = _json_after(text, "SHAPES")
    assert len(shapes) == 1 and shapes[0]["text"] == "휴가 신청" and shapes[0]["x"] > 0
    assert "<path" in text or "<polyline" in text or "<rect" in text   # 실제 그림이 들어감
    assert "http://" not in text.replace("http://www.w3.org", ""), "외부 자원 없음(사내망·오프라인)"


def test_scene_state_restored_after_render(tmp_path):
    w = CanvasWindow()
    a = _rect(w._scene, 0, 0, color="#ffffff")   # 다크 테마 흰 선 — 인쇄 규칙으로 잠깐 검정
    b = _rect(w._scene, 300, 0)
    b.setVisible(False)
    a.setSelected(True)
    bg = w._scene.backgroundBrush().color().name()
    export_html(w._scene, str(tmp_path / "s.html"), "t", [("기본", [a, b], True)], [])
    assert a.isSelected() and not b.isVisible()
    assert a.pen().color().name() == "#ffffff"
    assert w._scene.backgroundBrush().color().name() == bg


def test_build_html_escapes_title():
    doc = build_html("<b>x</b>", 10, 10, [("기본", "<g/>", True)], [])
    assert "<title>&lt;b&gt;x&lt;/b&gt;</title>" in doc


def test_host_share_uses_layers_and_box_labels(tmp_path):
    w = CanvasWindow()
    assert w._share_html(path=str(tmp_path / "none.html"), open_after=False) is None
    assert "없어요" in w._toast.currentMessage()
    w._build_mermaid("flowchart LR\n A[휴가 신청] --> B[팀장 결재]")
    w.add_layer("메모")
    path = w._share_html(path=str(tmp_path / "flow"), open_after=False)
    assert path.endswith(".html")
    text = _read(path)
    assert [ly["name"] for ly in _json_after(text, "LAYERS")][:2] == ["기본", "메모"]
    labels = [s["text"] for s in _json_after(text, "SHAPES")]
    assert "휴가 신청" in labels and "팀장 결재" in labels, "화살표는 상자 정보에서 빠짐"
    assert len(labels) == 2


def test_menu_action():
    w = CanvasWindow()
    assert w._act_share_html.text() == "HTML로 공유…"
    from easycad.canvas.host_widgets import _SVG_ACT_ICON_NAMES
    assert "menu_export" in _SVG_ACT_ICON_NAMES
