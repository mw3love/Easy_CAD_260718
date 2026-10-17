"""모든 .ecad 아이템 종류가 든 시험 문서를 데스크톱 엔진으로 만든다(웹 칠판 직접 만들기 1단계, §8 항목61, 2026-10-17).

손으로 쓴 dict를 데스크톱이 열고(`load_document`) 다시 저장(`save_document`)해, 형식이 데스크톱이 만드는 그대로가 되게 한다.
같이 데스크톱 그림(`render_content_image`, 밝은 화면)도 PNG로 남겨 웹 그림과 나란히 비교한다.

실행: python tools/make_all_types_ecad.py  →  tests/fixtures/all_types.ecad, tests/fixtures/all_types_desktop.png
"""
import base64
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PyQt6.QtGui import QColor, QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _png_b64(w=60, h=40):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ff9ec5fe"))
    for x in range(w):
        img.setPixelColor(x, h // 2, QColor("#ff1e2b45"))
    ba = QByteArray(); buf = QBuffer(ba); buf.open(QIODevice.OpenModeFlag.WriteOnly); img.save(buf, "PNG"); buf.close()
    return base64.b64encode(bytes(ba)).decode("ascii")


def C(**kw):
    d = {"pos": [0, 0], "scale": 1.0, "rotation": 0.0, "z": 0, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None}
    d.update(kw)
    return d


def lbl(text, color="#ff1e2b45", font=12, **kw):
    d = {"text": text, "color": color, "font": font, "bg": None}
    d.update(kw)
    return d


ITEMS = [
    # 0 상자(라벨) · 1 원(라벨·점선) · 2 마름모 심볼 · 3 시작/끝 심볼 · 4 채운 상자
    C(type="rect", pos=[40, 40], rect=[0, 0, 160, 80], pen="#ff1e2b45", width=2.0, fill=None, style=1, label=lbl("상자 라벨")),
    C(type="ellipse", pos=[260, 40], rect=[0, 0, 140, 80], pen="#ffda7756", width=2.0, fill="#ffffeedd", style=2, label=lbl("원", color="#ffda7756")),
    C(type="symbol", kind="decision", pos=[460, 30], rect=[0, 0, 140, 100], pen="#ff1e2b45", width=2.0, fill=None, style=1, label=lbl("판단?")),
    C(type="symbol", kind="terminal", pos=[660, 50], rect=[0, 0, 150, 60], pen="#ff2563eb", width=2.0, fill="#ffdbeafe", style=1, label=lbl("시작")),
    C(type="rect", pos=[860, 40], rect=[0, 0, 120, 80], pen="#00000000", width=0.0, fill="#ff1f2f4d", style=0,
      label=lbl("채운 면", color="#ffffffff", font=14, family="Pretendard")),
    # 5 직선 화살표(양쪽 머리) · 6 곡선 화살표(라벨 2개) · 7 직각 화살표(라벨, 둥근 모서리) · 8 직각 각진
    C(type="arrow", p1=[40, 200], p2=[240, 200], ctrl1=None, ctrl2=None, color="#ff1e2b45", width=2, head=True, head_start=True, head_scale=1.0, style=1,
      labels=[lbl("양쪽", t=0.5, off=0.0)]),
    C(type="arrow", p1=[280, 240], p2=[520, 200], ctrl1=[340, 140], ctrl2=[460, 300], color="#ffda7756", width=3, head=True, head_start=False, head_scale=1.4, style=1,
      labels=[lbl("곡선 앞", t=0.25, off=0.0), lbl("뒤", t=0.8, off=-14.0)]),
    C(type="sarrow", pts=[[560, 200], [640, 200], [640, 260], [760, 260]], color="#ff1e2b45", width=2, head=True, head_start=False, head_scale=1.0, style=1,
      auto_route=False, routing="ortho", curve_r=10.0, route_hints=[], labels=[lbl("직각", t=0.5, off=0.0)]),
    C(type="sarrow", pts=[[800, 200], [900, 200], [900, 280]], color="#ff2563eb", width=3, head=False, head_start=True, head_scale=1.0, style=2,
      auto_route=False, routing="ortho", curve_r=0.0, route_hints=[]),
    # 9 선(라벨) · 10 다각형(닫힘·채움) · 11 폴리라인(열림) · 12 펜 경로(곡선) · 13 채운 경로(구멍)
    C(type="line", line=[40, 330, 240, 380], pen="#ff16a34a", width=2.0, style=1, label=lbl("선 라벨", color="#ff16a34a")),
    C(type="polygon", pos=[280, 320], closed=True, rect=[0, 0, 120, 80], pts=[[0, 80], [60, 0], [120, 80]], pen="#ff1e2b45", width=2.0, fill="#ffe0e7ff", style=1),
    C(type="polygon", pos=[440, 320], closed=False, rect=[0, 0, 120, 80], pts=[[0, 0], [40, 80], [80, 0], [120, 80]], pen="#ffda7756", width=2.0, fill=None, style=1),
    C(type="path", elements=[["M", 600, 330], ["C", 640, 280, 700, 420, 760, 340], ["L", 800, 380]], pen="#ff7c3aed", width=3.0, style=1, freehand=True),
    C(type="path", elements=[["M", 840, 320], ["L", 960, 320], ["L", 960, 420], ["L", 840, 420], ["L", 840, 320], ["M", 870, 350], ["L", 930, 350], ["L", 930, 390], ["L", 870, 390], ["L", 870, 350]],
      pen="#00000000", width=0.0, fill="#ff94a3b8", style=1),
    # 14 글(여러 줄·굵기·부분 강조·형광펜) · 15 큰 보드 글꼴 글
    C(type="text", pos=[40, 450], text="첫 줄 보통\n둘째 줄 강조와 형광펜", color="#ff1f1f1f", font=12, bg=None,
      runs=[[6, 2, "#ffda7756", True], [10, 3, None, False, "#80ffeb3b"]]),
    C(type="text", pos=[300, 450], text="보드 글꼴 26pt", color="#ff1f2f4d", font=26, bg=None, weight=800, family="Pretendard"),
    # 16 이미지 · 17 표 · 18 번호표 · 19 회전한 상자
    C(type="image", pos=[620, 450], rect=[0, 0, 120, 80], data=_png_b64()),
    C(type="table", pos=[40, 560], rows=3, cols=3, header=True, rect=[0, 0, 300, 90],
      cells=[["항목", "값", "비고"], ["전력", "220V", ""], ["대역", "6MHz", "UHD"]], col_widths=[0.4, 0.3, 0.3]),
    C(type="badge", pos=[420, 600], number=7, color="#ffda7756"),
    C(type="rect", pos=[520, 560], rect=[0, 0, 120, 60], pen="#ff1e2b45", width=2.0, fill="#ffffffff", style=1, rotation=20.0, origin=[60, 30],
      label=lbl("회전 20°")),
    # 20 TRIM 자국(cuts) 있는 상자 · 21 포트 달린 상자
    C(type="rect", pos=[720, 560], rect=[0, 0, 120, 80], pen="#ff1e2b45", width=2.0, fill=None, style=1, cuts=[[0, 0.3, 0.7]]),
    C(type="rect", pos=[900, 560], rect=[0, 0, 100, 80], pen="#ff1e2b45", width=2.0, fill=None, style=1,
      ports=[{"shape": "rect", "size": [14, 14], "pen": "#ff1e2b45", "width": 1.5, "fill": "#ffffffff", "frac": [1.0, 0.5]},
             {"shape": "circle", "size": [14, 14], "pen": "#ffda7756", "width": 1.5, "fill": None, "frac": [0.5, 1.0]}]),
    # 22 표제란(용지틀) — 작게 A4 가로, 멀리
    C(type="titleblock", pos=[1100, 40], size="A4", orient="landscape",
      fields={"client": "KBS 전주", "number": "EC-001", "title": "모든 종류 시험", "scale": "1:1", "author": "mw", "reviewer": "", "date": "2026-10-17"}),
    # 23 보드(어두운 바탕) + 24 그 안 글
    C(type="board", pos=[1100, 300], rect=[0, 0, 400, 225], bg="#ff1f2f4d", z=-1),
    C(type="text", pos=[1130, 330], text="보드 안 흰 글", color="#ffffffff", font=18, bg=None, family="Pretendard", weight=600),
]
# 직각 화살표 7을 상자 0·원 1에 붙인 연결 하나 더(바인딩 왕복 확인용)
ITEMS.append(C(type="sarrow", pts=[[200, 80], [230, 80], [230, 80], [260, 80]], color="#ff1e2b45", width=2, head=True, head_start=False, head_scale=1.0,
               style=1, auto_route=True, routing="ortho", curve_r=10.0, route_hints=[], bind1=0, bind1_pt=[160, 40], bind1_group=None,
               bind2=1, bind2_pt=[0, 40], bind2_group=None))


def main():
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    from easycad.canvas.host import CanvasWindow
    from easycad.fileio.document import load_document, save_document
    from easycad.fileio.pdf_export import render_content_image
    w = CanvasWindow()
    sc = w._scene if hasattr(w, "_scene") else w.scene
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.ecad")
        with open(src, "w", encoding="utf-8") as f:
            json.dump({"format": "easycad-doc", "version": 1, "items": ITEMS}, f, ensure_ascii=False)
        n = load_document(sc, src)
    # 데스크톱은 열면 「자동 길」 화살표를 이벤트 고리에서 다시 꺾는다 — 여기선 고리가 안 도니 직접 부른다(웹 시험이 이 길과 맞춰 봄)
    from easycad.canvas.annotator_core import _PolyArrowItem
    for it in sc.items():
        if isinstance(it, _PolyArrowItem) and it._auto_route:
            it.reroute()
    out = os.path.join(ROOT, "tests", "fixtures", "all_types.ecad")
    save_document(sc, out)
    img = render_content_image(sc, scale=1.0, pad=16.0)
    png = os.path.join(ROOT, "tests", "fixtures", "all_types_desktop.png")
    img.save(png)
    print(f"{n}개 → {out}\n그림 → {png} ({img.width()}x{img.height()})")


if __name__ == "__main__":
    main()
