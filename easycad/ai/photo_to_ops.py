"""사진→도면 프롬프트·조각·응답 파싱 (§8 항목28). Qt 비의존.

게이트웨이 모델에게 사진을 주고 "ops" JSON(`easycad/fileio/photo_ops.py`)을 받는다.
2026-10-01 실측 프롬프트(`tools/sketch_ops_probe.py`의 `TASK`, 비교용으로 그대로 보존)에
글자 회전(`rot`)만 더했다 — DMB 폰 사진에서 세로 케이블 번호가 눕혀져 겹친 게 유일한 구조적 약점이었다.
"""
import json
import re

TASK = """이 사진은 방송 송신소 계통도(블록 다이어그램)다. 이걸 CAD 앱에서 편집 가능한 도면으로 다시 그리려 한다.
원본 사진 크기는 {w}x{h} 픽셀이고, 모든 좌표는 이 원본 픽셀 좌표계(x 오른쪽, y 아래)로 쓴다.

출력은 JSON 객체 하나만: {{"ops": [ ... ]}}. 코드펜스·설명 금지. 사용 가능한 op:
- {{"op":"box","id":"tsd","x1":..,"y1":..,"x2":..,"y2":..,"label":"상자 안 중앙 글자(\\n 줄바꿈 가능, 없으면 생략)","font":15}}
- {{"op":"text","x":..,"y":..,"text":"자유 글자(\\n 가능)","font":13}}   ← (x,y)=글자 왼쪽 위. font는 원본 글자 높이(px)의 약 2배.
- {{"op":"text","x":..,"y":..,"text":"<1DJ1-9>","font":13,"rot":90}}   ← 세로로 쓴 글자. rot=90은 위에서 아래로 읽힘, rot=-90은 아래에서 위로 읽힘. 이때 (x,y)=읽기 시작하는 끝의 글줄 가운데 점(세로선 위 글자면 그 선의 x).
- {{"op":"line","pts":[[x,y],[x,y],...],"head":false,"src":"상자id","dst":"상자id"}}  ← 원본처럼 직각으로 꺾이는 연결선. head=true면 끝에 화살촉. src/dst는 선 끝이 닿는 상자(없으면 생략).
- {{"op":"poly","pts":[[x,y],...],"closed":false}}  ← 안테나 기호·스위치 내부 같은 장식선.
- {{"op":"circle","id":"..","cx":..,"cy":..,"r":..}}
- {{"op":"dashrect","x1":..,"y1":..,"x2":..,"y2":..}}  ← 점선/1점쇄선 테두리 영역.

규칙:
- 원본의 위치·크기를 최대한 그대로 따른다(재배치 금지).
- 원본에 실제로 그려진 선만 그린다. 논리적으로 있을 법한 선을 지어내지 않는다.
- 상자 안 포트 이름(예: THRU1, CH1(MW))과 선 옆 글자(케이블 번호 <1DJ1-1> 등)도 text로 빠짐없이 옮긴다.
- 글자는 원본 그대로(한글 포함) 정확히 읽는다.
- 원본에서 세로로 쓴 글자는 가로로 눕히지 말고 rot로 세운다.
- 상자 내부 글자가 포트 이름과 겹치면 상자 label 대신 text로 제목 위치를 직접 지정한다."""

CROP_NOTE = ("\n\n첫 이미지는 원본 전체다. 이어서 같은 사진을 구획별로 잘라 2배 확대한 조각들을 준다. "
             "각 조각 앞에 원본 좌표계에서의 범위를 적었다(조각 픽셀÷2 + 왼쪽위 오프셋 = 원본 좌표). "
             "작은 글자·기호는 조각에서 읽되, 출력 좌표는 원본 좌표계로.")

FIX_NOTE = ("\n\n지금은 수정 라운드다. 첫 이미지=원본, 둘째 이미지=네 이전 JSON을 실제 앱으로 렌더한 결과"
            "(같은 좌표 프레임). 둘을 비교해 위치 어긋남·빠진 상자/선/글자·겹친 글자·지어낸 선을 고친 "
            "**전체** JSON을 다시 출력하라.\n\n이전 JSON:\n")


def grid_crops(w, h, cols=3, rows=2, overlap=0.1):
    """원본을 cols×rows 격자로 나눈 조각 범위(각 변 overlap 비율만큼 겹침)."""
    cw, ch = w / cols, h / rows
    ox, oy = cw * overlap, ch * overlap
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append((int(max(0, c * cw - ox)), int(max(0, r * ch - oy)),
                        int(min(w, (c + 1) * cw + ox)), int(min(h, (r + 1) * ch + oy))))
    return out


def parse_ops(txt: str) -> dict:
    """응답 텍스트에서 첫 `{`~마지막 `}`를 JSON으로 읽는다(코드펜스·앞뒤 설명이 붙어도 됨)."""
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        raise ValueError("응답에 JSON 객체가 없음: " + (txt or "")[:200])
    spec = json.loads(m.group(0))
    if not isinstance(spec, dict) or not isinstance(spec.get("ops"), list):
        raise ValueError("응답 JSON에 ops 목록이 없음")
    return spec
