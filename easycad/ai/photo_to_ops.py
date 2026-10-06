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


MAX_SIDE = 1600   # 2026-10-01 실측 조건(폰 사진 5712×4284를 1600×1200으로 줄여 통과)


def fit_for_ai(photo, max_side: int = MAX_SIDE):
    """긴 변이 max_side를 넘으면 비율 유지로 줄인다. 폰 원본(5712×4284) 그대로면 첫 호출 요청이
    약 69MB로 게이트웨이 한도(25MB)를 넘어 413 오류가 났다(2026-10-05). 1600이면 약 9MB."""
    if max(photo.size) <= max_side:
        return photo
    from PIL import Image
    out = photo.copy()
    out.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return out


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
    """한 번 호출. 반환 (본문, usage dict, 소요초).

    스트리밍으로 받는다 — 게이트웨이는 응답 전체가 5분(실측 303초) 안에 안 끝나면 504로 끊는데,
    벽 전체 도면 사진(ops 709개)은 한 호출이 353초 걸렸다. 조금씩 흘려받으면 끊기지 않았다(2026-10-05)."""
    t0 = time.time()
    stream = client.chat.completions.create(model=model, max_tokens=max_tokens, stream=True,
                                            stream_options={"include_usage": True},
                                            messages=[{"role": "user", "content": content}])
    parts, usage = [], {}
    for ch in stream:
        if ch.choices and ch.choices[0].delta and ch.choices[0].delta.content:
            parts.append(ch.choices[0].delta.content)
        if getattr(ch, "usage", None):
            usage = ch.usage.model_dump()
    return "".join(parts), usage, time.time() - t0


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


# ---- 구역별 동시 생성(2026-10-05) ----------------------------------------------
# 시간 대부분은 AI가 답을 쓰는 시간이라, 사진을 구역으로 나눠 동시에 쓰게 한다. 벽 전체 도면 실측:
# 한 번에 전체 331초 → 3×2 구역 161초(4×3도 143초라 더 잘게는 이득 없음). 수정 라운드는 없다(전체를
# 다시 쓰느라 18분이 걸렸다). 경위: docs/history/2026-10.md "구역별 동시 호출".

TILE_NOTE = ("\n\n이번에는 도면의 한 구역만 맡는다. 첫 이미지=원본 전체(위치 참고용), 둘째 이미지=맡은 구역을 "
             "2배 확대한 것. 맡은 구역: 원본 좌표 x {x1}~{x2}, y {y1}~{y2} (확대 이미지 픽셀÷2 + ({x1},{y1}) = "
             "원본 좌표). 이 구역 안에 보이는 것만 그린다. 구역 밖으로 이어지는 선은 구역 경계까지만 그린다. "
             "단 글자는 시작점(x,y)이 구역 안이면 구역 밖으로 넘어가도 끝까지 전부 쓰고(원본 전체 이미지에서 "
             "읽어라), 시작점이 구역 밖인 글자는 쓰지 않는다. 상자도 중심이 구역 안이면 전체를 그린다. "
             "좌표는 원본 좌표계로.")

SEAM_TOL = 8   # 경계에서 양쪽 구역의 선 끝이 이 거리(원본 px) 안이면 같은 선으로 잇는다


def core_rects(w, h, cols=3, rows=2):
    """겹침 없는 구역 범위 — 도형마다 주인 구역을 하나로 정하는 데 쓴다(조각은 `grid_crops`로 겹쳐 보낸다)."""
    cw, ch = w / cols, h / rows
    return [(c * cw, r * ch, (c + 1) * cw, (r + 1) * ch) for r in range(rows) for c in range(cols)]


def _clip_seg(p, q, r):
    """선분 p→q를 사각형 r로 자른다(Liang-Barsky). 반환 (p', q') 또는 None."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if pp == 0:
            if qq < 0:
                return None
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    if t0 > t1:
        return None
    return [x0 + t0 * dx, y0 + t0 * dy], [x0 + t1 * dx, y0 + t1 * dy]


def _clip_polyline(pts, r):
    """꺾은선을 사각형으로 잘라 안에 남는 조각들. 각 조각 = (점들, 시작이 잘렸나, 끝이 잘렸나)."""
    out, cur = [], []

    def flush():
        if len(cur) > 1:
            out.append((cur[:], cur[0] != pts_f[0], cur[-1] != pts_f[-1]))

    pts_f = [[float(x), float(y)] for x, y in pts]
    for a, b in zip(pts_f, pts_f[1:]):
        s = _clip_seg(a, b, r)
        if s is None:
            flush()
            cur = []
            continue
        if cur and cur[-1] == s[0]:
            cur.append(s[1])
        else:
            flush()
            cur = [s[0], s[1]]
    flush()
    return out


def _inside(x, y, r):
    return r[0] <= x < r[2] and r[1] <= y < r[3]


def _own(op, core):
    """구역 결과의 op 하나를 주인 구역 기준으로 거른다. 상자·원·글자는 중심(글자는 시작점)이 구역 안일
    때만, 선은 구역 안 부분만 남긴다. 선 조각은 끝 정보(잘림·연결·화살촉)를 함께 돌려 나중에 잇는다."""
    k = op.get("op")
    try:
        if k in ("box", "dashrect"):
            return [op] if _inside((op["x1"] + op["x2"]) / 2, (op["y1"] + op["y2"]) / 2, core) else []
        if k == "circle":
            return [op] if _inside(op["cx"], op["cy"], core) else []
        if k == "text":
            return [op] if _inside(op["x"], op["y"], core) else []
        if k in ("line", "poly"):
            pts = list(op.get("pts") or [])
            if op.get("closed") and pts:
                pts.append(pts[0])
            res = []
            for piece, cut0, cut1 in _clip_polyline(pts, core):
                base = {key: v for key, v in op.items()
                        if key not in ("pts", "closed", "head", "src", "dst")}
                res.append({"_piece": True, "base": base, "pts": piece,
                            "ends": [{"cut": cut0, "node": None if cut0 else op.get("src"), "head": False},
                                     {"cut": cut1, "node": None if cut1 else op.get("dst"),
                                      "head": bool(op.get("head")) and not cut1}],
                            "closed": bool(op.get("closed")) and not (cut0 or cut1)})
            return res
    except (KeyError, TypeError, ValueError):
        return []
    return []


def _seam_join(pieces):
    """구역 경계에서 잘린 선 조각끼리 잇는다 — 잘린 끝이 같은 경계 위에서 SEAM_TOL 안이면 한 선으로."""
    def rev(p):
        p["pts"].reverse()
        p["ends"].reverse()

    alive = list(pieces)
    merged = True
    while merged:
        merged = False
        for a in alive:
            if not a["ends"][1]["cut"]:
                if a["ends"][0]["cut"]:
                    rev(a)
                else:
                    continue
            ax, ay = a["pts"][-1]
            best, best_d = None, SEAM_TOL
            for b in alive:
                if b is a or b["base"].get("op") != a["base"].get("op") or b["tile"] == a["tile"]:
                    continue
                for end in (0, 1):
                    if not b["ends"][end]["cut"]:
                        continue
                    bx, by = b["pts"][-1 if end else 0]
                    d = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
                    if d < best_d:
                        best, best_d, best_end = b, d, end
            if best is None:
                a["ends"][1]["cut"] = False     # 짝 없음 — 잘린 끝으로 남는다
                merged = True
                break
            if best_end == 1:
                rev(best)
            bx, by = best["pts"][0]
            mid = [(ax + bx) / 2, (ay + by) / 2]
            a["pts"] = a["pts"][:-1] + [mid] + best["pts"][1:]
            a["ends"][1] = best["ends"][1]
            alive.remove(best)
            merged = True
            break
    ops = []
    for p in alive:
        if p["ends"][0]["head"] and not p["ends"][1]["head"]:
            rev(p)
        op = dict(p["base"], pts=p["pts"])
        if op.get("op") == "line":
            op["head"] = p["ends"][1]["head"]
            for key, end in (("src", 0), ("dst", 1)):
                if p["ends"][end]["node"] is not None:
                    op[key] = p["ends"][end]["node"]
        elif p["closed"]:
            op["pts"] = p["pts"][:-1]
            op["closed"] = True
        ops.append(op)
    return ops


def tile_content(photo, task: str, crop) -> list:
    """구역 하나의 콘텐츠: [지시+구역 안내, 원본, 구역 2배 조각]."""
    x1, y1, x2, y2 = crop
    c = photo.crop(crop)
    return [{"type": "text", "text": task + TILE_NOTE.format(x1=x1, y1=y1, x2=x2, y2=y2)},
            image_part(photo), image_part(c.resize((c.width * 2, c.height * 2)))]


def generate_ops_tiled(client, photo, *, model: str, cols: int = 3, rows: int = 2, task: str = TASK,
                       max_tokens: int = 32000, tries: int = 2, progress=None,
                       cancelled=None) -> tuple[dict, list]:
    """사진(PIL RGB) → ops 명세. 구역 cols×rows를 동시에 생성해 합친다. 반환 (spec, 구역별 로그).

    - 구역 응답이 깨지면(스트림이 오류 없이 중간에 끊긴 사례 실측) 그 구역만 `tries`번까지 다시 보낸다.
      끝내 실패한 구역은 비워 두고 로그에 error를 남긴다. 전부 실패면 ValueError.
    - progress(끝난 수, 전체, 글): 시작과 구역이 끝날 때마다. cancelled() -> bool: 다시 보내기 전과
      다 끝난 뒤 확인(진행 중인 호출은 못 끊는다), 참이면 Cancelled."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    W, H = photo.size
    text = task.format(w=W, h=H)
    crops, cores = grid_crops(W, H, cols, rows), core_rects(W, H, cols, rows)
    n = len(crops)

    def one(i):
        entry = {"tile": i}
        for t in range(tries):
            if cancelled is not None and cancelled():
                entry["error"] = "취소"
                return entry, []
            try:
                txt, usage, dt = call(client, model, tile_content(photo, text, crops[i]), max_tokens)
                spec = parse_ops(txt)
            except Exception as e:  # noqa: BLE001 — 깨진 응답·HTTP 오류 모두 그 구역만 다시
                entry["error"] = str(e)[:200]
                continue
            entry.pop("error", None)
            entry.update(tries=t + 1, sec=round(dt, 1), usage=usage, ops=len(spec["ops"]))
            return entry, spec["ops"]
        entry["tries"] = tries
        return entry, []

    if progress is not None:
        progress(0, n, f"구역 {n}곳 동시 생성 중")
    results = [None] * n
    with ThreadPoolExecutor(n) as ex:
        futs = {ex.submit(one, i): i for i in range(n)}
        for done, f in enumerate(as_completed(futs), 1):
            results[futs[f]] = f.result()
            if progress is not None:
                progress(done, n, f"구역 {done}/{n}곳 끝")
    if cancelled is not None and cancelled():
        raise Cancelled()
    log = [e for e, _ in results]
    if all("error" in e for e in log):
        raise ValueError("모든 구역 생성 실패: " + log[0]["error"])
    ops, pieces = [], []
    for i, (_, tile_ops) in enumerate(results):
        for op in tile_ops:
            if not isinstance(op, dict):
                continue
            op = dict(op)
            for key in ("id", "src", "dst"):          # 구역마다 id를 따로 매기므로 겹치지 않게
                if key in op:
                    op[key] = f"t{i}_{op[key]}"
            for o in _own(op, cores[i]):
                if o.get("_piece"):
                    o["tile"] = i
                    pieces.append(o)
                else:
                    ops.append(o)
    return {"ops": ops + _seam_join(pieces)}, log


# ---- 부분 다시 베끼기(2026-10-06) ------------------------------------------------
# 결과에서 틀린 곳만 상자로 골라 그 부분만 다시 그린다 — 전체(6구역 2~3분)를 다시 쓰지 않는다. 한 번 호출.

REGION_NOTE = ("\n\n이번에는 도면의 한 부분만 다시 그린다. 첫 이미지=원본 전체(위치 참고용), 둘째 이미지=다시 그릴 부분을 "
               "{z}배 확대한 것. 부분: 원본 좌표 x {x1}~{x2}, y {y1}~{y2} (확대 이미지 픽셀÷{z} + ({x1},{y1}) = 원본 좌표). "
               "이 부분 안에 보이는 것만 빠짐없이 그린다. 부분 밖으로 이어지는 선은 경계까지만 그린다. 좌표는 원본 좌표계로.")
REGION_PREV = "\n\n이 부분의 이전 결과(틀리거나 빠진 것이 있어 다시 그린다 — 맞는 것은 그대로 살려도 된다):\n"
REGION_ASK = "\n\n사용자가 짚은 문제: "
REGION_MAX_ZOOM_SIDE = 1600   # 확대 조각의 긴 변 상한(요청 크기 — fit_for_ai와 같은 이유)


def op_center(op):
    """op 하나의 대표점(원본 px) — 부분 안에 드는지 가를 때 쓴다. 못 읽으면 None."""
    try:
        k = op.get("op")
        if k in ("box", "dashrect"):
            return (op["x1"] + op["x2"]) / 2, (op["y1"] + op["y2"]) / 2
        if k == "circle":
            return op["cx"], op["cy"]
        if k == "text":
            return op["x"], op["y"]
        if k in ("line", "poly"):
            xs = [p[0] for p in op["pts"]]
            ys = [p[1] for p in op["pts"]]
            return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return None


def ops_in_region(ops, region):
    """대표점이 부분(x1,y1,x2,y2) 안인 op만."""
    out = []
    for op in ops:
        c = op_center(op) if isinstance(op, dict) else None
        if c is not None and region[0] <= c[0] <= region[2] and region[1] <= c[1] <= region[3]:
            out.append(op)
    return out


def region_content(photo, task: str, region, prev_ops=(), note: str = "") -> list:
    """부분 하나의 콘텐츠: [지시+부분 안내(+이전 결과·사용자 지적), 원본, 부분 확대 조각]."""
    x1, y1, x2, y2 = (int(round(v)) for v in region)
    c = photo.crop((x1, y1, x2, y2))
    z = max(1.0, min(2.0, REGION_MAX_ZOOM_SIDE / max(c.width, c.height, 1)))
    z = round(z, 2)
    text = task + REGION_NOTE.format(z=z, x1=x1, y1=y1, x2=x2, y2=y2)
    if prev_ops:
        text += REGION_PREV + json.dumps({"ops": list(prev_ops)}, ensure_ascii=False)
    if note:
        text += REGION_ASK + note
    return [{"type": "text", "text": text}, image_part(photo),
            image_part(c.resize((max(1, int(c.width * z)), max(1, int(c.height * z)))))]


def generate_ops_region(client, photo, region, *, model: str, note: str = "", prev_ops=(), task: str = TASK,
                        max_tokens: int = 32000, tries: int = 2) -> tuple[dict, dict]:
    """사진의 한 부분(원본 px 사각형)만 다시 그린다. 반환 (spec — 대표점이 부분 안인 op만, 로그).
    응답이 깨지면 `tries`번까지 다시 보내고, 끝내 실패하면 마지막 오류를 그대로 올린다."""
    W, H = photo.size
    text = task.format(w=W, h=H)
    err = None
    for t in range(tries):
        try:
            txt, usage, dt = call(client, model, region_content(photo, text, region, prev_ops, note), max_tokens)
            spec = parse_ops(txt)
        except Exception as e:  # noqa: BLE001 — 깨진 응답·HTTP 오류 모두 다시
            err = e
            continue
        kept = ops_in_region(spec["ops"], region)
        return {"ops": kept}, {"tries": t + 1, "sec": round(dt, 1), "usage": usage, "ops": len(spec["ops"]),
                               "kept": len(kept)}
    raise err


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
