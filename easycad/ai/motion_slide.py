"""웹 칠판 「이 장 움직이게」(계획 ⑤, 2026-11-08, Qt 비의존) — 발표 자료 장 하나 → 모션그래픽 HTML 한 장(→ 로 단계).

칠판은 이 HTML을 그 장 프레임을 꼭 덮는 움직이는 카드(`doc` + `live` + `motion`, 틀은 `web/src/next/livecard.js`)로 둔다.
발표 중 → = 먼저 장 안 단계(`window.mbNext()`), 마지막 단계면 다음 프레임. PDF·그림 내보내기엔 카드를 안 그려 원래 장이 찍힘.

2026-11-07 실측(장 하나 「송신소는 무슨 일을 하나」, 다섯 단계): Opus 5.5 255초·약 510크레딧(압도적 — 사용자) ·
**Opus + 그 장 GPT 그림을 참고 그림으로 180초·약 366크레딧**(그림 구성 그대로) · Sonnet 124초·163(배치 어색) · Sol 40초·42(단순·글자 잘림).
답 한도 16,000이면 끝이 잘림 → 32,000.
"""
from __future__ import annotations

import json
import re
import time

from easycad.ai import gateway as gw

MOTION_MODEL = "claude-opus-5-5"
MAX_TOKENS = 32000
SYSTEM = """너는 방송국 발표 화면을 만드는 모션그래픽 디자이너다. 발표 장 하나를 HTML 한 파일로 만든다.
- 화면 {W}×{H} 고정, 바깥 라이브러리·글꼴·그림 주소 없이 HTML·CSS·SVG·자바스크립트만(인터넷이 막힌 틀에서 돈다). 글꼴은 'Pretendard','Malgun Gothic',sans-serif.
  html·body 여백 0, 바탕 흰색, 창 크기에 맞춰 {W}×{H} 판 전체를 비율 그대로 줄이고 늘려 가운데에.
- 색: 흰 바탕, 남색 #1e3a5f · 코랄 #da7756 + 회색. 평면 벡터 일러스트를 SVG로 직접 그린다.
- 장이 열리면 제목과 첫 단계가 부드럽게 움직이며 나타난다(0.6~1.2초, 과하지 않게).
- 발표자가 넘긴다: 단계(build)를 나눠 window.mbNext()를 부를 때마다 다음 단계가 움직이며 나타나고 true를 돌려준다. 마지막 단계에서는 아무것도 안 하고 false를 돌려준다(그때 발표가 다음 장으로).
  window.mbPrev()는 한 단계 되돌리고 true, 첫 단계에서는 false. window.mbSteps = 전체 단계 수, window.mbStep = 지금 단계(0부터). → 키·스페이스·클릭 = mbNext, ← = mbPrev.
- 각 단계엔 신호의 흐름(점이 선을 따라 이동, 전파 고리가 퍼짐 등) 같은 뜻 있는 움직임을 하나씩. 계속 도는 장식 움직임은 은은하게만.
- 글은 [장 글]에 있는 것만, 크게(본문 28px 이상) 적게. HTML만 답한다(설명·코드펜스 없이)."""
REF_NOTE = ("\n\n[참고 그림] 함께 보낸 그림은 이 장을 미리 그려 본 설명 그림이다. 구성(무엇이 어디에·어떤 순서로)·사물 모양·색감을 이 그림에 가깝게 SVG로 다시 그리고, "
            "단계마다 움직임을 더한다. 그림 속 글은 [장 글]을 따른다.")


def steps_of(slide: dict) -> int:
    """단계 수 = 글머리(없으면 단계 줄·숫자 칸) 수, 2~6."""
    n = len(slide.get("bullets") or slide.get("steps") or slide.get("numbers") or [])
    return max(2, min(6, n or 3))


def prompt(slide: dict, ref: bool) -> str:
    keep = {k: slide[k] for k in ("title", "bullets", "steps", "numbers", "message", "notes") if slide.get(k)}
    n = steps_of(slide)
    return ("[장 글]\n" + json.dumps(keep, ensure_ascii=False) + (REF_NOTE if ref else "")
            + f"\n\n단계는 {n}개(첫 단계는 열릴 때 같이) — 글머리 하나 = 단계 하나.")


def clean(html: str) -> str:
    """답 → HTML. 끝이 잘렸거나 단계 함수가 없으면 ValueError(크레딧은 이미 씀 — 대화창이 까닭을 보임)."""
    h = gw.strip_code_fence(html or "").strip()
    if "<html" not in h.lower() and "<svg" not in h.lower():
        raise ValueError("움직이는 장을 못 만들었어요(HTML이 아님)")
    if not re.search(r"</html>\s*$", h, re.I):
        raise ValueError("움직이는 장이 중간에 끊겼어요 — 다시 해 보세요")
    if "mbNext" not in h:
        raise ValueError("움직이는 장에 단계 넘기기(mbNext)가 없어요")
    return h


def make(client, slide: dict, *, w: int = 1600, h: int = 900, ref_image: str = "", model: str = MOTION_MODEL) -> dict:
    """장(제목·글머리·발표자 메모) + 참고 그림(data: 주소, 그림 장이면) → {"html", "title", "steps", "model", "elapsed"}."""
    if not str(slide.get("title") or "").strip():
        raise ValueError("장 제목이 없어요")
    w, h = int(max(800, min(2400, w))), int(max(450, min(2400, h)))
    text = prompt(slide, bool(ref_image))
    user = [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": ref_image}}] if ref_image else text
    t0 = time.time()
    r = client.chat.completions.create(model=model, max_tokens=MAX_TOKENS, messages=[
        {"role": "system", "content": SYSTEM.replace("{W}", str(w)).replace("{H}", str(h))}, {"role": "user", "content": user}])
    return {"html": clean(r.choices[0].message.content or ""), "title": str(slide["title"])[:80], "steps": steps_of(slide),
            "model": getattr(r, "model", None) or model, "elapsed": round(time.time() - t0, 1)}
