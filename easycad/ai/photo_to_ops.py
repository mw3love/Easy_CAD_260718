"""사진→도면 프롬프트·조각·응답 파싱 (§8 항목28). Qt 비의존.

게이트웨이 모델에게 사진을 주고 "ops" JSON(`easycad/fileio/photo_ops.py`)을 받는다.
처음 실측 프롬프트(`tools/sketch_ops_probe.py`의 `TASK_V1`, 비교용으로 그대로 보존)는 방송 송신소
계통도 전용이었다. 지금은 분야 문구·예시를 뺀 범용판(2026-10-01) — 출력 형식(ops 어휘·원본 픽셀 좌표)과
분야 무관 규칙만 남겼다. 형식은 앱이 결과를 읽는 약속이라 뺄 수 없다(8월 실패의 원인이 형식이었다).
글자 회전(`rot`)은 DMB 폰 사진에서 세로 케이블 번호가 눕혀져 겹친 것을 고치려 넣었다.
"""
import base64
import io
import json
import re
import time

TASK = """이 사진 속 도면을 CAD 앱에서 편집할 수 있는 도형으로 다시 그린다.
원본 사진 크기는 {w}x{h} 픽셀이고, 모든 좌표는 이 원본 픽셀 좌표계(x 오른쪽, y 아래)로 쓴다.

출력은 JSON 객체 하나만: {{"ops": [ ... ]}}. 코드펜스·설명 금지. 사용 가능한 op:
- {{"op":"box","id":"b1","x1":..,"y1":..,"x2":..,"y2":..,"label":"상자 안 중앙 글자(\\n 줄바꿈 가능, 없으면 생략)","font":15}}
- {{"op":"text","x":..,"y":..,"text":"글자(\\n 가능)","font":13}}   ← (x,y)=글자 왼쪽 위. font는 원본 글자 높이(px)의 약 2배.
- {{"op":"text","x":..,"y":..,"text":"세로 글자","font":13,"rot":90}}   ← 세로로 쓴 글자. rot=90은 위에서 아래로, rot=-90은 아래에서 위로 읽힘. 이때 (x,y)=읽기 시작하는 끝의 글줄 가운데 점.
- {{"op":"line","pts":[[x,y],[x,y],...],"head":false,"src":"상자id","dst":"상자id"}}  ← 원본 경로대로 꺾이는 선. head=true면 끝에 화살촉. src/dst는 선 끝이 닿는 상자(없으면 생략).
- {{"op":"poly","pts":[[x,y],...],"closed":false}}  ← 그 밖의 선·기호. 곡선·호는 점을 촘촘히 찍어 근사한다.
- {{"op":"circle","id":"..","cx":..,"cy":..,"r":..}}
- {{"op":"dashrect","x1":..,"y1":..,"x2":..,"y2":..}}  ← 점선 테두리 영역.

규칙:
- 원본의 위치·크기를 그대로 따른다(재배치 금지).
- 원본에 실제로 그려진 것만 그린다. 있을 법한 선이나 글자를 지어내지 않는다.
- 글자는 작은 것까지 빠짐없이, 원본 그대로(한글 포함) 옮긴다. 세로 글자는 rot로 세운다."""

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


# ---- AI 루프(§8 항목28 2단계) -------------------------------------------------
# 도구(`tools/sketch_ops_probe.py`)와 앱이 같은 루프를 쓴다. 수정 라운드에 쓰는 "직전 결과 렌더"는
# Qt가 필요해 밖에서 `render(spec, (W, H)) -> PIL.Image`로 받는다(이 모듈은 Qt 비의존 유지).

class Cancelled(Exception):
    """사용자가 취소함 — 호출 사이에서만 확인한다(진행 중인 HTTP 호출은 못 끊는다)."""


def image_part(img) -> dict:
    """PIL 이미지 → chat 콘텐츠 image_url 조각."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {"type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}}


def first_content(photo, task: str, crops=None) -> list:
    """첫 호출 콘텐츠: [지시+조각 안내, 원본, (조각 범위 글, 2배 조각)×N]."""
    W, H = photo.size
    crops = grid_crops(W, H) if crops is None else crops
    content = [{"type": "text", "text": task + CROP_NOTE}, image_part(photo)]
    for i, (x1, y1, x2, y2) in enumerate(crops):
        c = photo.crop((x1, y1, x2, y2))
        content += [{"type": "text", "text": f"조각 {i + 1}: 원본 범위 x {x1}~{x2}, y {y1}~{y2}"},
                    image_part(c.resize((c.width * 2, c.height * 2)))]
    return content


def fix_content(photo, prev_render, task: str, spec: dict) -> list:
    """수정 라운드 콘텐츠: [지시+이전 JSON, 원본, 직전 렌더]."""
    return [{"type": "text", "text": task + FIX_NOTE + json.dumps(spec, ensure_ascii=False)},
            image_part(photo), image_part(prev_render)]


def call(client, model: str, content: list, max_tokens: int) -> tuple[str, dict, float]:
    """한 번 호출. 반환 (본문, usage dict, 소요초)."""
    t0 = time.time()
    resp = client.chat.completions.create(model=model, max_tokens=max_tokens,
                                          messages=[{"role": "user", "content": content}])
    txt = resp.choices[0].message.content or ""
    usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
    return txt, usage, time.time() - t0


def generate_ops(client, photo, *, model: str, render, rounds: int = 2, task: str = TASK,
                 crops=None, max_tokens: int = 32000, progress=None, cancelled=None,
                 on_round=None) -> tuple[dict, list]:
    """사진(PIL RGB) → ops 명세. 첫 생성 1회 + 수정 `rounds`회. 반환 (최종 spec, 라운드별 로그).

    - render(spec, (W, H)) -> PIL 이미지: 수정 라운드에 넘길 직전 결과 그림.
    - progress(i, total, 글): 각 호출 직전에 알림. cancelled() -> bool: 호출 사이에 확인, 참이면 Cancelled.
    - on_round(r, spec, log_entry): 라운드마다 결과를 받는다(도구가 파일로 남길 때).
    - 수정 라운드의 응답이 깨졌으면(JSON 없음 등) 직전 spec을 그대로 쓰고 로그에 사유를 남긴다 —
      이미 쓸 만한 결과를 버리지 않는다. 첫 생성이 깨지면 ValueError."""
    W, H = photo.size
    text = task.format(w=W, h=H)
    total = rounds + 1
    spec, log = None, []
    for r in range(total):
        if cancelled is not None and cancelled():
            raise Cancelled()
        if progress is not None:
            progress(r, total, "첫 생성" if r == 0 else f"수정 {r}/{rounds}")
        content = (first_content(photo, text, crops) if r == 0
                   else fix_content(photo, render(spec, (W, H)), text, spec))
        txt, usage, dt = call(client, model, content, max_tokens)
        entry = {"round": r, "sec": round(dt, 1), "usage": usage}
        try:
            spec = parse_ops(txt)
        except (ValueError, json.JSONDecodeError) as e:
            if r == 0:
                raise ValueError(f"응답을 읽지 못함: {e}") from e
            entry["error"] = str(e)[:200]
        entry["ops"] = len(spec["ops"])
        log.append(entry)
        if on_round is not None:
            on_round(r, spec, entry)
    return spec, log


# ---- 원근 보정(2026-10-01) -----------------------------------------------------
# 비스듬히 찍은 사진은 결과 도면도 같은 사다리꼴이 된다("원본 위치 그대로" 규칙이 왜곡까지 따름 —
# 평면도 시험에서 발견). 사용자가 창에서 맞춘 네 모서리를 반듯한 직사각형으로 펴서 AI에 보낸다.
# Pillow 내장 PERSPECTIVE만 쓴다(OpenCV·numpy는 배포판 의존성에 없다).

def _solve(a, b):
    """가우스 소거(부분 피벗) — 8×8 하나라 순수 파이썬으로 충분."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            raise ValueError("네 점이 한 줄 위에 있어 펼 수 없음")
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def is_full_frame(quad, size, tol=0.5) -> bool:
    """네 점이 사진 네 귀퉁이 그대로인가(=보정 안 함)."""
    w, h = size
    full = ((0, 0), (w, 0), (w, h), (0, h))
    return all(abs(px - fx) <= tol and abs(py - fy) <= tol for (px, py), (fx, fy) in zip(quad, full))


def rectify(photo, quad):
    """quad=(왼쪽위, 오른쪽위, 오른쪽아래, 왼쪽아래) 사진 좌표 → 그 사각형을 편 직사각형 사진.
    결과 크기는 마주보는 변 길이 중 긴 쪽. 네 점이 사진 귀퉁이 그대로면 원본을 그대로 돌려준다."""
    if is_full_frame(quad, photo.size):
        return photo
    from PIL import Image
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = quad

    def d(ax, ay, bx, by):
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
    W = max(1, round(max(d(x0, y0, x1, y1), d(x3, y3, x2, y2))))
    H = max(1, round(max(d(x0, y0, x3, y3), d(x1, y1, x2, y2))))
    # 출력 (u,v) → 입력 (x,y): x=(a u+b v+c)/(g u+h v+1), y=(d u+e v+f)/(g u+h v+1)
    rows, rhs = [], []
    for (u, v), (x, y) in zip(((0, 0), (W, 0), (W, H), (0, H)), quad):
        rows.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); rhs.append(x)
        rows.append([0, 0, 0, u, v, 1, -u * y, -v * y]); rhs.append(y)
    coeffs = _solve(rows, rhs)
    return photo.transform((W, H), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC,
                           fillcolor="white")
