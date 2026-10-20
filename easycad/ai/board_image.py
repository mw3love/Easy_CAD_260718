"""웹 칠판 그림 만들기(§8 항목61 ③-4, 2026-10-19) — 「○○ 그려줘」 → KAIROS 그림 후보 몇 장(Qt 비의존, `web/server.py`가 부름).

KAIROS POST `/images/generate/` {"model", "prompt", "number_of_images", "aspect_ratio"} → {"data": [{"url": "data:image/jpeg;base64,…"} 또는 {"b64_json"}], "credits_charged"}.
2026-10-19 실측(후보 2장, 4:3): gemini-3.1-flash-lite-image 4.1~5.2초·68크레딧(장당 약 34) / gemini-3.1-flash-image-preview 11.5초·138크레딧 — 평면 일러스트 품질은
lite도 충분해 기본은 lite → 2026-10-20 그림 모델 6개를 한글 인포그래픽(점검 메모 한 장)으로 비교: `gpt-image-2.5-flare`가 한글·숫자 모두 정확하고
16초·장당 약 10크레딧(lite의 1/3)이라 기본을 바꿈(사용자 선택). sunburst·gemini-3-pro는 숫자·날짜를 지어냈고 ideogram v4는 한글이 깨짐(docs/history 2026-10-20). 후보는 대화창에만 보이고 고른 한 장만 칠판에(같이 쓰는 칠판에 고르기 전 후보가 남들 화면에 안 보이게).
"""
from __future__ import annotations

import base64

from easycad.ai import gateway as gw

IMAGE_MODEL = "gpt-image-2.5-flare"
CANDIDATES = 2
ASPECT = "4:3"


def infographic_prompt(material: str) -> str:
    """정리 문서와 같은 자료 → 인포그래픽 그림 지시(「🎨 그림으로도」). 2026-10-20 비교에 쓴 문구 — 없는 숫자·날짜를 넣지 말라고 못 박음."""
    return ("다음 내용을 한국어 인포그래픽 한 장으로 만들어 줘. 제목·숫자 카드·막대·할 일 체크리스트가 보이게, 한글 글자는 정확하게, 깔끔한 업무용 디자인. "
            "자료에 없는 숫자·날짜·문구는 넣지 마.\n\n" + (material or "").strip()[:4000])


def _bytes_of(item: dict, http) -> tuple:
    """응답 한 칸 → (바이트, 확장자). data: 주소·b64_json·http 주소 셋 다."""
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"]), "png"
    u = str(item.get("url") or item.get("image") or "")
    if u.startswith("data:"):
        head, b64 = u.split(",", 1)
        return base64.b64decode(b64), ("jpg" if "jpeg" in head or "jpg" in head else "png" if "png" in head else "webp" if "webp" in head else "png")
    if u.startswith("http"):
        r = http.get(u, timeout=120)
        ct = r.headers.get("content-type", "")
        return r.content, ("jpg" if "jpeg" in ct else "webp" if "webp" in ct else "png")
    raise RuntimeError("그림 응답에서 그림을 못 찾음")


def generate(api_key: str, prompt: str, *, n: int = CANDIDATES, model: str = IMAGE_MODEL, aspect: str = ASPECT,
             base_url: str = gw.BASE_URL, http=None) -> dict:
    """프롬프트 → {"images": [(바이트, 확장자), …], "model", "credits"}. `http`는 시험용(httpx 흉내)."""
    import httpx
    http = http or httpx
    r = http.post(base_url + "/images/generate/", headers={"Authorization": f"Bearer {api_key}"},
                  json={"model": model, "prompt": prompt, "number_of_images": n, "aspect_ratio": aspect}, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"그림 만들기 실패 HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    items = d.get("data") or d.get("images") or []
    if not items:
        raise RuntimeError(f"그림 응답이 비었어요: {str(d)[:200]}")
    return {"images": [_bytes_of(it if isinstance(it, dict) else {"url": it}, http) for it in items], "model": model,
            "credits": d.get("credits_charged")}
