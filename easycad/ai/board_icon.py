"""웹 칠판 아이콘 — 「안테나 아이콘 그려 줘」 → KAIROS SVG 후보 → 칠판이 고칠 수 있는 선 도형으로(§8 항목63 2단계, 2026-10-23, Qt 비의존).

지시문·코드펜스 벗기기는 데스크톱 「심볼」과 같은 `text_to_svg`(그 규칙 = 우리 파서가 받는 모양). 도형으로 바꾸기는 칠판(`web/src/next/svgin.js`).
모델 = 0단계 실측(같은 부품 5개 × 모델 4개, docs/history/2026-10.md): claude-sonnet-5-5 — sol과 같은 품질·값에 3~4배 빠름(3~4초).
후보는 같은 모델을 두 번 동시에(답이 매번 달라 고를 거리가 됨). 이어 고치기(고른 아이콘 + 「선을 더 굵게」)는 한 개 — 거의 같은 결과라(그림 고치기와 같은 판단).
"""
from __future__ import annotations

import base64
import io
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from easycad.ai import gateway as gw
from easycad.ai.text_to_svg import generate_svg

ICON_MODEL = "claude-sonnet-5-5"
_SHAPES = {"line", "rect", "circle", "ellipse", "polyline", "polygon", "path", "text"}   # 칠판이 도형으로 받는 요소(데스크톱 `svg_import`)
# 아이콘 다음 말 — 고른 아이콘을 바탕으로 고치기(그 밖의 말은 보통 길 고르기)
FOLLOW_WORDS = re.compile(r"굵|가늘|얇|선|단순|간단|복잡|자세|크게|작게|빼|지워|추가|넣어|바꿔|바꾸|다시|둥글|각지|비슷|대신|없애|섞어")


def usable(svg: str) -> bool:
    """칠판이 도형으로 받을 수 있는 SVG인가 — XML로 읽히고 우리 요소가 하나라도 있음."""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return False
    return root.tag.rsplit("}", 1)[-1] == "svg" and any(el.tag.rsplit("}", 1)[-1] in _SHAPES for el in root.iter())


def _image(data_url: str):
    """칠판에서 고른 그림(data: 주소) → PIL 그림 — 「이 그림을 아이콘으로」."""
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1]))).convert("RGB")


def make(api_key: str, ask: str, *, base_svg: str = "", image_url: str = "", n: int = 2, base_url: str = gw.BASE_URL, model: str = ICON_MODEL) -> dict:
    """→ {"svgs": [SVG 글, …], "model", "elapsed"}. 못 읽는 답은 빼고, 하나도 없으면 예외(대화창에 실패로)."""
    t0 = time.time()
    refs = [base_svg] if base_svg else None
    image = _image(image_url) if image_url and not refs else None
    n = 1 if refs else n

    def one(_):   # 하나가 실패해도 다른 하나는 살림
        try:
            return generate_svg(api_key, ask, model=model, image=image, refs=refs, base_url=base_url)
        except Exception as e:  # noqa: BLE001 — 게이트웨이 오류는 모두 실패 하나로 셈
            return "", e
    with ThreadPoolExecutor(n) as ex:
        outs = list(ex.map(one, range(n)))
    svgs = [s for s, _m in outs if s and usable(s)]
    if not svgs:
        err = next((m for s, m in outs if isinstance(m, Exception)), None)
        raise RuntimeError(f"아이콘을 못 만들었어요 — {err}" if err else "아이콘을 못 만들었어요(SVG가 아닌 답) — 다시 물어 주세요")
    return {"svgs": svgs, "model": next(m for s, m in outs if s and usable(s)), "elapsed": round(time.time() - t0, 1)}
