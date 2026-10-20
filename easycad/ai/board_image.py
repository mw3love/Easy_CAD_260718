"""웹 칠판 그림 만들기(§8 항목61 ③-4, 2026-10-19) — 「○○ 그려줘」 → KAIROS 그림 후보 몇 장(Qt 비의존, `web/server.py`가 부름).

KAIROS POST `/images/generate/` {"model", "prompt", "number_of_images", "aspect_ratio"} → {"data": [{"url": "data:image/jpeg;base64,…"} 또는 {"b64_json"}], "credits_charged"}.
2026-10-19 실측(후보 2장, 4:3): gemini-3.1-flash-lite-image 4.1~5.2초·68크레딧(장당 약 34) / gemini-3.1-flash-image-preview 11.5초·138크레딧 — 평면 일러스트 품질은
lite도 충분해 기본은 lite → 2026-10-20 그림 모델 6개를 한글 인포그래픽(점검 메모 한 장)으로 비교: `gpt-image-2.5-flare`가 한글·숫자 모두 정확하고
16초·장당 약 10크레딧(lite의 1/3)이라 기본을 바꿈(사용자 선택). sunburst·gemini-3-pro는 숫자·날짜를 지어냈고 ideogram v4는 한글이 깨짐(docs/history 2026-10-20). 후보는 대화창에만 보이고 고른 한 장만 칠판에(같이 쓰는 칠판에 고르기 전 후보가 남들 화면에 안 보이게).
"""
from __future__ import annotations

import base64
import re

from easycad.ai import gateway as gw

IMAGE_MODEL = "gpt-image-2.5-flare"
CANDIDATES = 2
ASPECT = "4:3"


def infographic_prompt(material: str) -> str:
    """정리 문서와 같은 자료 → 인포그래픽 그림 지시(「🎨 그림으로도」). 2026-10-20 비교에 쓴 문구 — 없는 숫자·날짜를 넣지 말라고 못 박음."""
    return ("다음 내용을 한국어 인포그래픽 한 장으로 만들어 줘. 제목·숫자 카드·막대·할 일 체크리스트가 보이게, 한글 글자는 정확하게, 깔끔한 업무용 디자인. "
            "자료에 없는 숫자·날짜·문구는 넣지 마.\n\n" + (material or "").strip()[:4000])


IMAGE_MARK = "그림 후보"   # 서버 그림 답 글에 늘 들어가는 말(`web/server.py` `_image`) — 앞 답이 그림이었나 알아보는 표시
FACTS_HEAD = "웹에서 찾은 정보로 그렸어요"
FACTS_HEADS = (FACTS_HEAD, "공공 데이터로 그렸어요", "기상청·천문연 자료로 그렸어요")   # 둘째 = `kr_tools.TOOL_HEAD`(공공 데이터로 그린 그림도 이어 고치기가 그 자료를 다시 씀), 셋째 = 10-20 낮까지의 옛 머리
# 그림 바로 뒤 「날짜도 넣어 줘」 같은 고칠 말 — 이 말이 있으면 길 고르기 없이 그림을 이어서(판단 모델은 앞 대화를 안 봄)
FOLLOW_WORDS = re.compile(r"그림|이미지|사진|넣어|넣으|반영|바꿔|바꾸|추가|빼|지워|크게|작게|색|날짜|글씨|글자|제목|분위기|느낌|다시")


def followup(msgs: list) -> dict | None:
    """바로 앞 답이 그림이면 그 그림 줄기 → {"asks": [처음 요청, 고칠 점, …], "facts": 처음에 찾은 정보}. 아니면 None.
    2026-10-20 사용자: 첫 그림이 좋아 「내일 날짜도 넣어 줘」 했더니 마지막 말만 지시로 가서 전혀 다른 그림이 나왔음.
    (KAIROS 그림 API는 기존 그림을 받아 고치지 못함 — image·images·reference_images 셋 다 무시, 실측 — 그래서 요청·정보를 이어 다시 그림)"""
    ms = [m for m in msgs if isinstance(m, dict)]
    if len(ms) < 3 or ms[-1].get("role") != "user":
        return None
    i, asks, facts = len(ms) - 2, [], ""
    while i >= 1 and ms[i].get("role") == "assistant" and IMAGE_MARK in str(ms[i].get("content", "")) and ms[i - 1].get("role") == "user":
        c = str(ms[i]["content"])
        if c.startswith(FACTS_HEADS) and "\n" in c:
            facts = re.sub(r"\[\d+\]", "", c.split("\n", 1)[1].rsplit("\n\n" + IMAGE_MARK, 1)[0]).strip()
        asks.insert(0, str(ms[i - 1].get("content", "")).strip())
        i -= 2
    return {"asks": asks, "facts": facts} if asks else None


def followup_prompt(fu: dict, new: str) -> str:
    """앞 그림 줄기 + 새 고칠 말 → 한 덩어리 그림 지시(같은 내용·화풍 유지, 고칠 점만)."""
    out = "[처음 요청]\n" + fu["asks"][0]
    later = fu["asks"][1:] + [new.strip()]
    out += "\n\n[이어서 고칠 점 — 앞 그림과 같은 내용·구도·화풍은 그대로 두고 이것만 반영]\n" + "\n".join(f"{n}. {a}" for n, a in enumerate(later, 1))
    if fu.get("facts"):
        out += "\n\n[그림에 반영할 최신 정보 — 여기와 다른 숫자·날짜는 넣지 마]\n" + fu["facts"][:1500]
    return out


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


def edit_prompt(ask: str, count: int = 1) -> str:
    """고른 그림 고치기 지시 — 한 장이면 그 그림(input_images 첫 번째)을 그대로 두고 말한 것만, 여러 장이면 넣은 차례로 불러 말한 대로(합치기 등)."""
    if count > 1:
        return f"넣은 이미지 {count}장(차례대로 첫 번째·두 번째…)을 바탕으로, 말하지 않은 부분은 원래대로 두고 다음대로 해 줘: {ask.strip()}"
    return f"첫 번째 이미지를 그대로 유지하고(구도·화풍·글자·색 모두), 다음만 고쳐 줘: {ask.strip()}"


def generate(api_key: str, prompt: str, *, n: int = CANDIDATES, model: str = IMAGE_MODEL, aspect: str = ASPECT,
             base_url: str = gw.BASE_URL, http=None, input_images: list | None = None) -> dict:
    """프롬프트 → {"images": [(바이트, 확장자), …], "model", "credits"}. `http`는 시험용(httpx 흉내).
    `input_images` = 고칠 그림 data: 주소 목록 — 있으면 편집 모드(KAIROS 문서 `input_images`, 2026-10-20 실측: flare가 원본 그대로 + 날짜만 추가.
    처음엔 image·images·reference_images로 보냈다가 게이트웨이가 모르는 필드라 조용히 버려 새 그림이 나왔음)."""
    import httpx
    http = http or httpx
    body = {"model": model, "prompt": prompt, "number_of_images": n, "aspect_ratio": aspect}
    if input_images:
        body["input_images"] = list(input_images)
    r = http.post(base_url + "/images/generate/", headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"그림 만들기 실패 HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    items = d.get("data") or d.get("images") or []
    if not items:
        raise RuntimeError(f"그림 응답이 비었어요: {str(d)[:200]}")
    return {"images": [_bytes_of(it if isinstance(it, dict) else {"url": it}, http) for it in items], "model": model,
            "credits": d.get("credits_charged")}
