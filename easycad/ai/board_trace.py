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
    sk, skipped = ops_to_sketch(_scale_fonts(spec, scale / SCALE), dark=False, scale=scale)
    return {"items": sk._items, "w": W * scale, "h": H * scale, "skipped": skipped, "tiles": log, "model": model}
