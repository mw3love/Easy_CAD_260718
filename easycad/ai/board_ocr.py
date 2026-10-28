"""웹 칠판 「그림 속 글 읽기」(§8 항목61, 2026-10-21 사용자: 그림을 글로 바꾸는 OCR) — 그림 한 장 → KAIROS 그림 읽는 모델 → 글.

모델은 2026-10-21 실측(흐릿하게 줄인 한글 점검 보고 6줄 캡처, 글자 일치율·시간):
claude-haiku-5-5 1.000·1.6초 · gemini-3.5-flash-lite 1.000·2.6초 · gpt-6.1-sol 1.000·7.5초 · gpt-6-luna 0.997·5.3초 · gemini-3.8-flash 0.994·10.8초
→ 가장 싸고 빠르고 틀림없는 haiku. Qt 없음 — `web/server.py`가 부른다.
"""
from __future__ import annotations

import io
import time

from easycad.ai import gateway as gw, see

OCR_MODEL = "claude-haiku-5-5"
PROMPT = ("그림 속 글자를 그대로 옮겨 적어 줘. 줄은 그림의 줄대로, 표는 칸을 탭으로 나눠서. "
          "설명·머리말·마크다운 없이 글만. 글자가 없으면 아무것도 쓰지 마.")


DESCRIBE = ("이 그림을 칠판에서 나중에 찾을 수 있게 한두 문장(100자 안쪽)으로 설명해 줘. 무엇인지·종류(사진·도면·표·화면 캡처 등)·그림 속 핵심 글자나 숫자. "
            "설명만 쓰고 머리말·마크다운은 빼.")


def describe(key: str, url: str, *, base_url: str = gw.BASE_URL, model: str = OCR_MODEL, client=None) -> dict:
    """그림 설명 한두 줄(2026-10-28) — 칠판에 넣은 그림의 보이지 않는 설명 `alt`로(뜻으로 찾기·글만 받는 길·데스크톱이 「무슨 그림」을 앎).
    실측 haiku 한 장 0.1크레딧 · 1.5~2.5초. {text, model, elapsed}, `client` = 시험용."""
    t0 = time.time()
    client = client or gw._client(key, base_url, timeout=60)
    r = client.chat.completions.create(model=model, max_tokens=200, messages=see.attach([{"role": "user", "content": DESCRIBE}], [see.shrink(url, 768)]))
    return {"text": gw.strip_code_fence(r.choices[0].message.content or "").strip()[:300], "model": model, "elapsed": round(time.time() - t0, 1)}


def read(key: str, png: bytes, *, base_url: str = gw.BASE_URL, model: str = OCR_MODEL) -> dict:
    """{text, model, elapsed} — 글이 없으면 text = ""."""
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    r = gw.call_text_with_fallback(key, PROMPT, model=model, image=img, base_url=base_url, timeout=120)
    return {"text": gw.strip_code_fence(r.content).strip(), "model": r.model_used, "elapsed": round(r.elapsed, 1)}
