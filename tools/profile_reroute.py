"""[성능 버그 재현 2026-08-07] 선택(클릭)만으로 A* 재라우팅이 폭주하는 문제 재현·프로파일링.

배경: §8 항목15(밀집 실도면 변환) 검증 중 사용자가 실제 창에서 발견 — 화살표가 캔버스
전역에 넓게 뻗은 밀집 도면(장애물 18개짜리 KBS 1TV 구간)에서 도형 하나를 **선택만 해도**
(이동 없음) 수 초씩 멈춘다. 원인 가설은 `docs/history/2026-08.md`"§8 항목15 실사용 피드백"·
`docs/pitfalls.md`"라우팅(A*/직교 엘보)" 참조 — `_on_scene_changed`(host_canvas.py)의
"changed region이 화살표 bbox와 겹치면 reroute" 필터가 선택강조 리페인트도 겹침으로
오판하는 것으로 추정.

사용법:
    python tools/profile_reroute.py            # 클릭 5회 프로파일링, 상위 20줄 출력
    python tools/profile_reroute.py --clicks 10

⚠ 라우팅(A*/직교 엘보) 코드는 과거 여러 차례 스턱루프가 난 민감 영역(전역 규칙 11-b) —
수정 전후로 반드시 이 스크립트를 다시 돌려 실제 개선(초 단위 → ms 단위)을 직접 확인할 것.
"""
import argparse
import cProfile
import io
import os
import pstats
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 재현 자체엔 실제 창 불필요

from PyQt6.QtWidgets import QApplication

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import _RectItem
from easycad.fileio.sketch_build import Sketch


def build_kbs_1tv_doc(path: str) -> int:
    """§8 항목15 검증에 쓴 KBS 모악산 1TV 구간 근사 재현(박스 18·화살표 19·텍스트 1=38개).
    좌표는 `실제 도면/IMG_7072.jpeg` 육안판독 그대로(2026-08-07 최초 작성)."""
    s = Sketch(dark=True)
    ekmfr = s.box(225, 345, 145, 75, "EK-MFR/2\n(Eurotek)")
    mspp = s.box(225, 500, 145, 65, "광대역 자영망\n(MSPP)")
    settop = s.box(225, 605, 145, 70, "무궁화위성\nSET TOP BOX")
    ekmrf2 = s.box(225, 815, 145, 70, "EK-MRF/2\n(Eurotek link-1,2)\n[노고단]")
    hdtv_recv = s.box(225, 985, 145, 65, "HDTV RECEIVER\nSKD1000A\n[식장산]")
    tsdiv = s.box(480, 320, 190, 120, "TS DIVIDER\nDWD 200-1")
    tsswitch1 = s.box(790, 395, 170, 35, "DTV TS Switcher①\n16*1")
    mpegdec = s.box(695, 450, 160, 65, "DTV MPEG DECODER\nSKD2000A")
    mpegenc = s.box(580, 610, 135, 55, "MPEG ENCODER\nWi-vision HDV-1000EN")
    dtvpic = s.box(1065, 355, 145, 185, "DTV PIC\nCH1(MW) CH2(광대역주)\nCH3(광대역예비) CH4(스카이라이프)")
    tx_a = s.box(1435, 310, 230, 100, "1TV TX-A")
    filter_a = s.box(1665, 310, 70, 100, "FILTER")
    tx_b = s.box(1445, 1160, 220, 100, "1TV TX-B")
    filter_b = s.box(1665, 1160, 70, 100, "FILTER")
    ulink = s.box(1480, 590, 490, 440, "U-LINK\n[내부 안테나절체 스위치\n회로 근사 생략]")
    meter_top = s.box(1720, 660, 100, 80, "METER\n(1식)")
    meter_bot = s.box(1600, 900, 100, 65, "METER\n(1식)")
    dl = s.box(1690, 1090, 65, 50, "D/L")

    s.arrow(ekmfr, tsdiv, label="1DJ1-1")
    s.arrow(tsdiv, dtvpic, label="1DJ1-2", from_side="E", to_side="W")
    s.arrow(tsdiv, tsswitch1, label="2DJ2-1", from_side="E", to_side="W")
    s.arrow(tsdiv, mpegdec, from_side="S", to_side="N")
    s.arrow(mspp, dtvpic, label="1DJ1-3/4", from_side="E", to_side="W")
    s.arrow(settop, mpegenc, label="HDMI OUT", from_side="S", to_side="W")
    s.arrow(mpegenc, dtvpic, label="1DJ1-5", from_side="E", to_side="W")
    s.arrow(ekmrf2, dtvpic, label="노고 주/예비", from_side="E", to_side="W")
    s.arrow(hdtv_recv, dtvpic, label="1DJ1-9", from_side="E", to_side="S")
    s.arrow(hdtv_recv, tsswitch1, label="2DJ2-2", from_side="N", to_side="W")
    s.arrow(dtvpic, tx_a, label="Bypass1/2 1DJ1-6/7", from_side="N", to_side="W")
    s.arrow(dtvpic, ulink, label="OUT1", from_side="E", to_side="W")
    s.arrow(tx_a, filter_a)
    s.arrow(tx_b, filter_b)
    s.arrow(ulink, meter_top, from_side="E", to_side="W")
    s.arrow(ulink, meter_bot, from_side="S", to_side="N")
    s.arrow(ulink, dl, from_side="S", to_side="N")
    s.arrow(dl, tx_b, from_side="W", to_side="E")
    s.arrow(filter_a, ulink, from_side="S", to_side="N")
    s.text(80, 250, "모악산(송) TV,DMB 송출계통도 - 1TV 구간 (성능 재현용)")
    return s.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clicks", type=int, default=5)
    ap.add_argument("--lines", type=int, default=20)
    args = ap.parse_args()

    app = QApplication(sys.argv)
    w = CanvasWindow()

    doc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_profile_reroute_doc.ecad")
    from easycad.fileio.document import load_document
    n = build_kbs_1tv_doc(doc_path)
    load_document(w._scene, doc_path)
    w.show()
    app.processEvents()

    rects = [it for it in w._scene.items() if isinstance(it, _RectItem)]
    print(f"items={n} rects={len(rects)}")

    pr = cProfile.Profile()
    pr.enable()
    for r in rects[: args.clicks]:
        w._scene.clearSelection()
        r.setSelected(True)
        app.processEvents()
    pr.disable()

    st = pstats.Stats(pr)
    st.sort_stats("cumulative")
    buf = io.StringIO()
    st.stream = buf
    st.print_stats(args.lines)
    print(buf.getvalue())


if __name__ == "__main__":
    main()
