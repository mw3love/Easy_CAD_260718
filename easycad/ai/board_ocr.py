"""웹 칠판 「그림 속 글 읽기」(§8 항목61, 2026-10-21 사용자: 그림을 글로 바꾸는 OCR) — 그림 한 장 → KAIROS 그림 읽는 모델 → 글.

모델은 2026-10-21 실측(흐릿하게 줄인 한글 점검 보고 6줄 캡처, 글자 일치율·시간):
claude-haiku-5-5 1.000·1.6초 · gemini-3.5-flash-lite 1.000·2.6초 · gpt-6.1-sol 1.000·7.5초 · gpt-6-luna 0.997·5.3초 · gemini-3.8-flash 0.994·10.8초
→ 가장 싸고 빠르고 틀림없는 haiku. Qt 없음 — `web/server.py`가 부른다.
"""
from __future__ import annotations

import io

from easycad.ai import gateway as gw

OCR_MODEL = "claude-haiku-5-5"
PROMPT = ("그림 속 글자를 그대로 옮겨 적어 줘. 줄은 그림의 줄대로, 표는 칸을 탭으로 나눠서. "
          "설명·머리말·마크다운 없이 글만. 글자가 없으면 아무것도 쓰지 마.")


def read(key: str, png: bytes, *, base_url: str = gw.BASE_URL, model: str = OCR_MODEL) -> dict:
    """{text, model, elapsed} — 글이 없으면 text = ""."""
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    r = gw.call_text_with_fallback(key, PROMPT, model=model, image=img, base_url=base_url, timeout=120)
    return {"text": gw.strip_code_fence(r.content).strip(), "model": r.model_used, "elapsed": round(r.elapsed, 1)}
