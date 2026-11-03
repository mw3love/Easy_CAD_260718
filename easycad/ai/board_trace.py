"""웹 칠판 「도면으로 베끼기」(2026-10-25 사용자 — 웹에서도 못 쓰는 것보다 단순하게라도). Qt 비의존.

칠판 그림 → 데스크톱 베끼기와 같은 엔진(`photo_to_ops.generate_ops_tiled` — 구역 6곳 동시, 이어 붙이기)
→ `photo_ops.ops_to_sketch` → `.ecad` 아이템. 키는 서버에만 있어 AI 호출은 서버가 하고, 서버가 파이썬이라
데스크톱 코드를 그대로 부른다(결과는 같은 `.ecad` 아이템이라 웹이 이미 그림).

데스크톱과 다른 점(사용자 선택 — 웹은 단순하게): 모서리 맞추기(`rectify`)·흐린 바탕·부분 다시 베끼기 없음.
결과는 그림 옆에 같은 크기로 놓고, 마무리는 사람이 그림을 보며 손으로 한다.
"""
import io

from easycad.ai import gateway as gw
from easycad.ai.photo_to_ops import fit_for_ai, generate_ops_tiled
from easycad.fileio.photo_ops import SCALE, ops_to_sketch

TRACE_MODEL = "gpt-6.1-sol"   # 데스크톱 베끼기 추천 1(`photo_dialog.PHOTO_MODELS` — 가성비)


def _scale_fonts(spec: dict, k: float) -> dict:
    """ops의 글자 크기는 SCALE(2배)에 맞춘 값 — 다른 배율로 그리면 글자도 같은 비율로(회전 축 계산도 이 값을 씀)."""
    out = []
    for op in spec.get("ops", []):
        if isinstance(op, dict) and op.get("op") in ("text", "box"):   # 글자 크기를 안 적은 것도 기본값(`ops_to_sketch` 글 13·상자 15)에 배율을
            f = op.get("font")
            f = f if isinstance(f, (int, float)) else (13 if op["op"] == "text" else 15)
            op = {**op, "font": max(2, round(f * k))}   # 바닥 2 — 그림이 작게 놓이면 글자도 작게(6이면 상자 밖으로 넘쳐 겹쳤음, 10-25 실조건)
        out.append(op)
    return {**spec, "ops": out}


def _units(s: str) -> float:
    """한 줄 글 폭(글자 크기 1 = 한글 한 자) — 한글·한자 1, 그 밖 0.6."""
    return sum(1.0 if ord(ch) >= 0x2E80 else 0.6 for ch in s)


def _texts_into_boxes(spec: dict) -> dict:
    """이름 없는 상자 안에 놓인 자유 글자 = 그 상자의 이름(2026-11-02 실검증 — AI가 상자 이름을 따로 글자로 적으면 상자 가운데에 안 오고
    크기 고르기에서도 빠져 「마이크로웨이브」·「광 수신기」가 아주 작았음). 돌린 글자·상자 밖으로 반 넘게 나간 글자는 그대로. 위에서 아래 순서로 줄을 이음."""
    ops = [op for op in spec.get("ops", [])]
    taken, label_of = set(), {}
    for bi, b in enumerate(ops):
        if not (isinstance(b, dict) and b.get("op") == "box" and not b.get("label")):
            continue
        try:
            x1, y1, x2, y2 = (float(b[k]) for k in ("x1", "y1", "x2", "y2"))
        except (KeyError, TypeError, ValueError):
            continue
        inside = []
        for ti, t in enumerate(ops):
            if ti in taken or not (isinstance(t, dict) and t.get("op") == "text" and str(t.get("text") or "").strip()) or float(t.get("rot") or 0) % 360:
                continue
            try:
                tx, ty = float(t["x"]), float(t["y"])
            except (KeyError, TypeError, ValueError):
                continue
            f = float(t.get("font", 13)) if isinstance(t.get("font", 13), (int, float)) else 13.0
            tw = _units(str(t["text"]).split("\n")[0]) * f * 4 / 3 / SCALE   # 글 폭(그림 픽셀) — 반 넘게 상자 안이면
            if x1 - 2 <= tx and tx + tw / 2 <= x2 + 2 and y1 - 2 <= ty <= y2:
                inside.append((ty, tx, ti, f))
        if inside and len(inside) <= 3 and all(_units(str(ops[ti]["text"])) <= 14 for _, _, ti, _ in inside):   # 범례·설명 상자(줄 많음·긴 글)는 그대로 — 합치면 선 견본과 어긋났음(같은 날)
            inside.sort()
            cols = {ops[ti].get("color") for _, _, ti, _ in inside}
            label_of[bi] = ("\n".join(str(ops[ti]["text"]).strip() for _, _, ti, _ in inside), max(f for *_, f in inside),
                            cols.pop() if len(cols) == 1 else None)   # 글 색이 하나면 상자 이름 색으로(2026-11-03 꾸밈)
            taken.update(ti for _, _, ti, _ in inside)
    if not label_of:
        return spec
    out = []
    for i, op in enumerate(ops):
        if i in taken:
            continue
        if i in label_of:
            op = {**op, "label": label_of[i][0], "font": label_of[i][1]}
            if label_of[i][2]:
                op["tcolor"] = label_of[i][2]
        out.append(op)
    return {**spec, "ops": out}


def _even_box_fonts(spec: dict) -> dict:
    """상자 글자 크기 고르기(2026-11-02 실검증 — AI가 상자마다 따로 정해 「마이크로웨이브」는 아주 작고 「송신기」는 상자를 넘쳤음).
    SCALE 기준 글자 크기에서: 상자 글자들의 가운데 값 ±15% 안으로 모으고, 상자 폭·높이를 넘으면 줄임(가운데 값의 65% 밑으로는 안 줄임 — 그보다 길면 칠판이 줄을 꺾음).
    글자 폭 = 크기 × 4/3(pt → 칠판 단위) × 한 줄 글자 수."""
    spec = _texts_into_boxes(spec)
    boxes = [op for op in spec.get("ops", []) if isinstance(op, dict) and op.get("op") == "box" and op.get("label")]
    fonts = sorted(float(op.get("font", 15)) for op in boxes if isinstance(op.get("font", 15), (int, float)))
    if len(fonts) < 2:
        return spec
    m = fonts[(len(fonts) - 1) // 2]   # 짝수 개면 아래 가운데 값(위로 치우치면 큰 글이 기준이 됐음)
    out = []
    for op in spec.get("ops", []):
        if isinstance(op, dict) and op.get("op") == "box" and op.get("label"):
            try:
                w, h = (float(op["x2"]) - float(op["x1"])) * SCALE, (float(op["y2"]) - float(op["y1"])) * SCALE
            except (KeyError, TypeError, ValueError):
                out.append(op)
                continue
            f = float(op.get("font", 15)) if isinstance(op.get("font", 15), (int, float)) else 15.0
            f = min(max(f, 0.85 * m), 1.15 * m)
            lines = str(op["label"]).split("\n")
            u = max(_units(s) for s in lines) or 1.0
            fit = min(w * 0.88 / (u * 4 / 3), h * 0.85 / (len(lines) * 1.3 * 4 / 3))
            if f > fit:
                f = max(fit, 0.65 * m)
            op = {**op, "font": max(2, round(f))}
        out.append(op)
    return {**spec, "ops": out}


def _text_box(op: dict, f: float | None = None) -> tuple[float, float, float, float]:
    """자유 글이 차지하는 자리(그림 픽셀) — 폭 = 글자 수 × 크기, 높이 = 줄 수 × 크기 × 1.2."""
    f = float(op.get("font", 13)) if f is None else f
    lines = str(op["text"]).split("\n")
    w = max(_units(s) for s in lines) * f * 4 / 3 / SCALE
    h = len(lines) * f * 4 / 3 * 1.2 / SCALE
    return float(op["x"]), float(op["y"]), float(op["x"]) + w, float(op["y"]) + h


def _untangle_texts(spec: dict) -> dict:
    """자유 글끼리 겹침 줄이기(2026-11-03 사용자 — 「10kW」·「VSWR 1.1」, 「- 스튜디오 신호」·「- 1Gbps」가 겹쳤음).
    AI가 설명 글 크기를 원본보다 크게 적는다(실측 약 1.5배 — 자리는 맞음). 그래서 ① 겹친 짝마다 「앞 글이 뒤 글 앞에서 끝나는」 크기를 구해
    그 가운데 값을 설명 글(가운데 크기 1.25배 이하)의 상한으로(한 그림의 설명 글은 크기가 같음 — 더 작은 글은 그대로), 범례처럼 틀 안 글이 오른쪽 변을 넘으면 맞게,
    ② 그래도 겹치는 글만 15%까지 더 줄이고
    ③ 남은 겹침은 뒤 글을 오른쪽·아래로 비켜 놓는다(글 높이·폭의 60%까지). 돌린 글·상자 이름은 안 건드림."""
    ops = [dict(op) if isinstance(op, dict) else op for op in spec.get("ops", [])]
    ts = []
    for op in ops:
        if not (isinstance(op, dict) and op.get("op") == "text" and str(op.get("text") or "").strip()) or float(op.get("rot") or 0) % 360:
            continue
        try:
            float(op["x"]), float(op["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(op.get("font", 13), (int, float)):
            op["font"] = 13
        ts.append(op)
    if len(ts) < 2:
        return {**spec, "ops": ops}
    f0 = {id(t): float(t.get("font", 13)) for t in ts}

    def need(a, b):
        """a·b가 겹치면 (줄여야 할 글, 그 글에 필요한 배율, 같은 줄인가) — 안 겹치면 None. 같은 줄 = 왼쪽 글이 오른쪽 글 앞에서 끝나게, 위아래 = 위 글이 아래 글 위에서 끝나게."""
        A, B = _text_box(a), _text_box(b)
        ox, oy = min(A[2], B[2]) - max(A[0], B[0]), min(A[3], B[3]) - max(A[1], B[1])
        if ox <= 0 or oy <= 0:
            return None
        if oy >= 0.5 * min(A[3] - A[1], B[3] - B[1]) and abs(A[1] - B[1]) < 0.6 * min(A[3] - A[1], B[3] - B[1]):   # 같은 줄
            (l, L), (r, R) = sorted(((a, A), (b, B)), key=lambda p: p[1][0])
            gap = 0.3 * float(l["font"]) * 4 / 3 / SCALE
            return l, (R[0] - L[0] - gap) / (L[2] - L[0]), True
        (u, U), (d, D) = sorted(((a, A), (b, B)), key=lambda p: p[1][1])
        return u, (D[1] - U[1]) / (U[3] - U[1]), False

    def pairs():
        return [n for i, a in enumerate(ts) for b in ts[i + 1:] if (n := need(a, b))]

    want = sorted(float(t["font"]) * max(0.65, k) for t, k, _ in pairs() if 0.55 <= k < 1)
    if want:   # ① 설명 글 크기 상한 = 겹친 글이 맞는 크기의 가운데 값 — 그보다 큰 설명 글만 내림(작은 글까지 같은 배율로 줄이면 「N+1」·「- 30m」이 아주 작아졌음)
        m = sorted(f0.values())[(len(f0) - 1) // 2]
        cap = want[(len(want) - 1) // 2]
        for t in ts:
            if cap < f0[id(t)] <= 1.25 * m:
                t["font"] = cap
        for t in ts:   # AI가 아주 작게 적은 설명 글(「- 자동 절체」·「- 30m」)은 상한 쪽으로 키움 — 다른 글과 안 겹치는 만큼만
            f = float(t["font"])
            if f >= 0.8 * cap:
                continue
            for c in (cap, cap * 0.9, cap * 0.8):
                if c <= f:
                    break
                t["font"] = c
                A = _text_box(t)
                if not any(u is not t and min(A[2], B[2]) > max(A[0], B[0]) and min(A[3], B[3]) > max(A[1], B[1])
                           for u in ts for B in (_text_box(u),)):
                    break
                t["font"] = f
    boxes = []   # 이름 없는 상자(범례·설명 틀) 안에서 시작한 글이 오른쪽 변을 넘으면 맞게(처음 크기의 60%까지)
    for op in ops:
        if isinstance(op, dict) and op.get("op") == "box" and not op.get("label"):
            try:
                boxes.append(tuple(float(op[k]) for k in ("x1", "y1", "x2", "y2")))
            except (KeyError, TypeError, ValueError):
                pass
    for t in ts:
        x0, y0, x1, _ = _text_box(t)
        for bx1, by1, bx2, by2 in boxes:
            if bx1 <= x0 < bx2 and by1 <= y0 < by2 and x1 > bx2:
                t["font"] = max(0.6 * f0[id(t)], float(t["font"]) * (bx2 - 4 - x0) / (x1 - x0))
    for t, k, _ in pairs():   # ② 겹친 글만 조금 더 — 한 번에 15%까지(더 줄이면 옆 글과 크기가 달라 보였음), 처음 크기의 60% 밑으로는 안 줄임
        t["font"] = max(0.6 * f0[id(t)], float(t["font"]) * max(0.85, min(1.0, k)))
    for a, b in [(a, b) for i, a in enumerate(ts) for b in ts[i + 1:]]:   # ③ 남은 겹침 = 뒤 글 비켜 놓기
        n = need(a, b)
        if not n:
            continue
        first, _, row = n
        second = b if first is a else a
        F, S = _text_box(first), _text_box(second)
        if row:
            dx = F[2] + 0.3 * float(first["font"]) * 4 / 3 / SCALE - S[0]
            if 0 < dx <= 0.6 * (S[2] - S[0]):
                second["x"] = float(second["x"]) + dx
        else:
            dy = F[3] - S[1]
            if 0 < dy <= 0.6 * (S[3] - S[1]):
                second["y"] = float(second["y"]) + dy
    for t in ts:
        t["font"] = max(2, round(float(t["font"])))
    return {**spec, "ops": ops}


def trace(key: str, png: bytes, *, width: float = 0, model: str = TRACE_MODEL, base_url: str | None = None,
          progress=None) -> dict:
    """그림 바이트 → {"items": .ecad 아이템들(왼쪽 위 = 0,0), "w", "h", "skipped", "tiles": 구역 로그}.

    width = 칠판에 놓일 폭(그림 카드 폭과 같게) — 없으면 데스크톱과 같은 SCALE. progress(끝난 구역, 전체, 글)."""
    from PIL import Image
    photo = Image.open(io.BytesIO(png)).convert("RGB")
    sent = fit_for_ai(photo)
    W, H = sent.size
    client = gw._client(key, base_url or gw.resolve_base_url(), timeout=600.0)
    spec, log = generate_ops_tiled(client, sent, model=model, progress=progress)
    scale = float(width) / W if width and width > 0 else SCALE
    sk, skipped = ops_to_sketch(_scale_fonts(_untangle_texts(_even_box_fonts(spec)), scale / SCALE), dark=False, scale=scale)
    return {"items": sk._items, "w": W * scale, "h": H * scale, "skipped": skipped, "tiles": log, "model": model}
