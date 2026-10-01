"""1TV 계통도 사진(photo.png) → .ecad — 2026-10-01 Claude Code 세션이 사진을 직접 보고 좌표를 적은 기준본.

게이트웨이 모델 결과(같은 폴더 *.json, tools/sketch_ops.py로 변환)와 비교하는 기준이다.
실행: python docs/reference/sketch_ops_1tv/session_baseline.py out.ecad
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from easycad.fileio.sketch_build import Sketch, _argb

S = 2.0
W = 2.0          # 선 두께
F = 18           # 기본 글자
FS = 15          # 작은 글자(케이블 번호·포트명)
s = Sketch()
INK = s._default_color


def P(x, y):
    return [x * S, y * S]


def box(x1, y1, x2, y2, label=None, font=F):
    n = s.box(x1 * S, y1 * S, (x2 - x1) * S, (y2 - y1) * S, label, width=W)
    if label:
        s._items[-1]["label"]["font"] = font
    return n


def text(x, y, t, font=FS):
    s.text(x * S, y * S, t, font=font)


def line(pts, head=False, src=None, dst=None, style=None):
    """직교 연결선(sarrow, 경로 고정). src/dst Node면 해당 끝을 그 도형에 지속연결."""
    q = [P(*p) for p in pts]
    d = s._common()
    d.update(type="sarrow", pts=q, color=_argb(INK), width=W, head=head,
             auto_route=False, routing="straight", curve_r=0.0)
    if src is not None:
        d.update(bind1=src.idx, bind1_pt=q[0])
    if dst is not None:
        d.update(bind2=dst.idx, bind2_pt=q[-1])
    if style is not None:
        d["style"] = style
    s._items.append(d)


def poly(pts, closed=False, style=None):
    """장식용 자유 꺾은선(_PolygonItem) — 안테나·스위치 내부 등."""
    q = [P(*p) for p in pts]
    xs = [p[0] for p in q]; ys = [p[1] for p in q]
    d = s._common()
    d.update(type="polygon", closed=closed,
             rect=[min(xs), min(ys), max(max(xs) - min(xs), 1), max(max(ys) - min(ys), 1)],
             pts=q, pen=_argb(INK), width=W, fill=None)
    if style is not None:
        d["style"] = style
    s._items.append(d)


def circle(cx, cy, r):
    return s.ellipse((cx - r) * S, (cy - r) * S, 2 * r * S, 2 * r * S, width=W)


def tag(x, y, t):
    """케이블 번호 〈1DJ1-1〉 — 선 바로 위에."""
    text(x, y - 15, f"<{t}>")


def dish(x, y, label, two_line=False):
    """접시 안테나 + 수신 표시. (x,y)=접시 오른쪽 뒤 급전점."""
    if two_line:
        text(x - 105, y - 18, label, font=F)
    else:
        text(x - 105, y - 10, label, font=F)
    poly([(x - 40, y - 2), (x - 32, y - 6), (x - 26, y + 2), (x - 18, y - 2)])   # 수신 지그재그
    poly([(x - 12, y - 16), (x - 2, y - 8), (x + 2, y), (x - 2, y + 8), (x - 12, y + 16)])  # 접시


# ── 왼쪽 열: 수신원 ─────────────────────────────────────────────
dish(118, 155, "연주소")
ekmfr = box(138, 157, 217, 190, "EK-MFR/2\n(Eurotek)", font=15)
line([(118, 163), (118, 178), (138, 178)], dst=ekmfr)

dish(118, 255, "연주소")
mspp = box(138, 253, 217, 300, "광대역 자영망\n(MSPP)", font=15)
line([(118, 263), (118, 278), (138, 278)], dst=mspp)

dish(118, 318, "무궁화\n위성", two_line=True)
stb = box(138, 312, 217, 355, "무궁화 위성\nSET TOP BOX", font=15)
line([(118, 326), (118, 333), (138, 333)], dst=stb)

dish(118, 437, "노고단")
box(141, 446, 220, 486)                                  # 2중 상자(뒤 장)
ekmrf = box(138, 450, 217, 490, "EK-MRF/2\n(Eurotek link-1,2)", font=14)
line([(118, 445), (118, 470), (138, 470)], dst=ekmrf)

text(30, 538, "식장산", font=F)
poly([(70, 548), (128, 548)])                            # 야기 안테나
for i in range(5):
    poly([(78 + i * 10, 556), (90 + i * 10, 540)])
hdrx = box(138, 543, 217, 585, "HDTV\nRECEIVER\nSKD1000A", font=14)
line([(98, 548), (98, 565), (138, 565)], dst=hdrx)

# ── 가운데: 분배·디코더·인코더 ─────────────────────────────────
tsd = box(290, 148, 398, 213)
text(300, 160, "TS DIVIDER\nDWD 200-1", font=15)
text(293, 170, "IN", font=12)
for nm, y in (("THRU1", 152), ("THRU2", 167), ("OUT1", 183), ("OUT2", 198)):
    text(366, y, nm, font=12)
line([(217, 177), (290, 177)], src=ekmfr, dst=tsd)
text(228, 152, "SMPTE-310M", font=13)
tag(228, 177, "1DJ1-1")

dec = box(425, 215, 512, 253, "DTV MPEG\nDECODER\nSKD2000A", font=14)
line([(398, 203), (412, 203), (412, 230), (425, 230)], src=tsd, dst=dec)

enc = box(355, 310, 440, 352, "MPEG ENCODER\nWi-vision\nHDV-1000EN", font=14)
line([(217, 340), (355, 340)], src=stb, dst=enc)
text(220, 342, "HDMI OUT", font=12)

# 출력 화살표 → 텍스트 목적지
line([(398, 188), (500, 188)], head=True, src=tsd)
tag(430, 188, "2DJ2-1")
text(515, 170, "DTV TS\nSwitcher ①\n16*1", font=13)
line([(512, 248), (555, 248)], head=True, src=dec)
text(516, 233, "NTSC", font=12)
text(560, 228, "조정실 모니터\n(M/W OUT)", font=13)
line([(175, 355), (175, 395)], head=True, src=stb)
text(180, 360, "NTSC OUT", font=12)
text(135, 398, "조정실 모니터\n(무궁화위성 On-Air)", font=13)
line([(175, 585), (175, 615)], head=True, src=hdrx)
text(180, 590, "NTSC OUT", font=12)
text(150, 617, "조정실 모니터\n(대전 On-Air)", font=13)
line([(217, 573), (340, 573), (340, 625)], head=True, src=hdrx)
tag(275, 573, "2DJ2-2")
text(290, 628, "DTV TS\nSwitcher ②\n16*1", font=13)
line([(217, 551), (270, 551)], src=hdrx)
tag(275, 551, "1DJ1-9")
text(207, 543, "1", font=12); text(207, 565, "3", font=12)

# ── DTV PIC ────────────────────────────────────────────────────
pic = box(657, 158, 740, 265)
text(678, 158, "DTV PIC", font=16)
for nm, y in (("CH1(MW)", 179), ("CH2(광대역주)", 196), ("CH3(광대역예비)", 213), ("CH4(스카이라이프)", 230)):
    text(660, y, nm, font=11)
line([(398, 157), (608, 157), (608, 185), (657, 185)], src=tsd, dst=pic)          # THRU1→CH1
tag(430, 157, "1DJ1-2")
line([(217, 265), (607, 265), (607, 202), (657, 202)], src=mspp, dst=pic)         # 주→CH2
text(220, 252, "(주)", font=12); tag(268, 265, "1DJ1-3")
line([(217, 285), (627, 285), (627, 219), (657, 219)], src=mspp, dst=pic)         # 예비→CH3
text(220, 272, "(예비)", font=12); tag(268, 285, "1DJ1-4")
line([(440, 328), (645, 328), (645, 237), (657, 237)], src=enc, dst=pic)          # 인코더→CH4
tag(500, 328, "1DJ1-5")
# 노고단 2회선
line([(217, 477), (597, 477), (597, 172), (398, 172)], src=ekmrf, dst=tsd)        # 노고 예비 ↔ THRU2
text(230, 465, "노고 예비", font=12)
line([(217, 459), (835, 459), (835, 210), (740, 210)], src=ekmrf, dst=pic)        # 노고 주 ↔ OUT 1
text(230, 447, "노고 주", font=12)

text(670, 330, "1TV", font=110)

# ── 오른쪽: 송신기·U-LINK ──────────────────────────────────────
txa = box(890, 125, 1035, 197, "1TV TX-A", font=22)
fila = box(1037, 125, 1075, 197, "FIL\nTER", font=20)
txb = box(897, 648, 1040, 720, "1TV TX-B", font=22)
filb = box(1043, 648, 1078, 720, "FIL\nTER", font=20)
text(745, 160, "Bypass 1", font=12); text(745, 180, "Bypass 2", font=12); text(745, 197, "OUT 1", font=12)
line([(740, 170), (890, 170)], src=pic, dst=txa)
tag(800, 170, "1DJ1-6")
line([(740, 190), (848, 190), (848, 683), (897, 683)], src=pic, dst=txb)
tag(800, 190, "1DJ1-7")

# U-LINK 1점쇄선 테두리(Qt DashDotLine=4)
s._items.append(dict(s._common(), type="rect", rect=P(900, 295) + [318 * S, 285 * S],
                     pen=_argb(INK), width=W, fill=None, style=4))
text(925, 545, "U-LINK", font=24)
text(1240, 300, "1", font=16)

# 동축 스위치(근사): 다이아몬드 + 4 포트 원
sw_c = (985, 412)
poly([(963, 412), (985, 394), (1007, 412), (985, 430)], closed=True)
poly([(963, 412), (1007, 412)]); poly([(985, 394), (985, 430)])
ant = circle(985, 390, 5); swa = circle(960, 412, 5); swb = circle(1010, 412, 5); swd = circle(985, 434, 5)
text(1000, 377, "ANT", font=11); text(930, 400, "TX-A", font=11)
text(1013, 400, "TX-B", font=11); text(1017, 416, "D/L", font=11)
poly([(945, 418), (945, 465), (1025, 465), (1025, 418)])        # 아래 루프
circle(985, 465, 8)

# FILTER A → 스위치 TX-A
line([(1075, 160), (1112, 160), (1112, 290), (926, 290), (926, 412), (955, 412)], src=fila, dst=swa)
# ANT → 상단 출력(외부로)
line([(985, 385), (985, 328), (1250, 328)], src=ant)
poly([(912, 470), (912, 328), (981, 328), (981, 340)])          # 왼쪽 보조 루프
circle(1183, 328, 10)
poly([(1183, 338), (1183, 378), (1250, 378)])
meter1 = box(1083, 345, 1140, 393, "METER\n(1식)", font=15)
poly([(1111, 345), (1111, 330)]); poly([(1103, 330), (1119, 330)])
# TX-B ← FILTER B
line([(1078, 690), (1103, 690), (1103, 412), (1015, 412)], src=filb, dst=swb)
# D/L → D/L 부하
dl = box(1045, 605, 1093, 632, "D/L", font=18)
line([(985, 439), (985, 422), (1072, 422), (1072, 605)], src=swd, dst=dl)
meter2 = box(1010, 497, 1050, 530, "METER\n(1식)", font=12)
poly([(1050, 513), (1068, 513)]); poly([(1068, 507), (1068, 519)])

n = s.save(sys.argv[1] if len(sys.argv) > 1 else "1tv.ecad")
print("items", n)
