"""칠판 그림을 AI에게 보이기 — 고른 것·프레임 안·칠판의 그림을 글 재료와 함께 실어 보내는 한 곳(2026-10-28).

쓰는 곳: 대화창 질문(`board_chat`)·정리 문서(`board_report`)·인터랙티브 HTML(`live_card`)·발표 자료(`slides`)·
딥모드 「이 칠판」(`deep_mode`)·말풍선(`board_bubble`). 웹 검색(Exa)은 글만 받아 안 붙인다.
실측(2026-10-28, 1024×640 JPEG 한 장 ≈ 850토큰, 짧은 글 포함): claude-opus-5-5 5.9 · claude-sonnet-5-5 2.4 · gpt-6.1-sol 2.0크레딧 — 셋 다 그림 속 글까지 읽음.
그림 고치기(`board_image` `input_images`)는 원본이 필요해 여기를 안 거친다(대화창이 긴 변 1536으로 보냄).
"""
from __future__ import annotations

import base64
import io

MAX_IMAGES = 6   # 한 번에 보이는 그림 — 넘는 그림은 글(`alt`)로만
SIDE = 1024      # 보내는 긴 변(대화창 첨부는 1536 — 보기만 할 땐 이 정도면 글자도 읽음, 위 실측)


def shrink(url: str, side: int = SIDE) -> str:
    """data: 그림 주소 → 긴 변 `side` JPEG data 주소. 못 읽으면 원래 주소(이미 작은 것일 수 있음)."""
    try:
        from PIL import Image
        raw = base64.b64decode(url.split(",", 1)[1])
        im = Image.open(io.BytesIO(raw))
        if max(im.size) <= side and url.startswith("data:image/jpeg"):
            return url
        im.thumbnail((side, side))
        if im.mode != "RGB":   # 투명 PNG는 흰 바탕에(검은 바탕이 되면 글이 안 보임)
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.convert("RGBA").split()[-1])
            im = bg
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001 — PIL 없음·깨진 그림 모두 그대로
        return url


def clean(images, limit: int = MAX_IMAGES) -> list:
    """요청에서 받은 그림 목록 → data:image만, `limit`장, 줄인 것."""
    return [shrink(s) for s in [s for s in images or [] if isinstance(s, str) and s.startswith("data:image/")][:limit]]


def from_doc(doc: dict, uids=None, limit: int = MAX_IMAGES) -> list:
    """저장된 칠판(.ecad) → 그림 도형의 그림(`uids`가 있으면 그것만, 칠판 순서). 그림 칸 `data` = base64 PNG(또는 data: 주소)."""
    want = set(uids) if uids is not None else None
    out = []
    for it in (doc or {}).get("items") or []:
        if it.get("type") != "image" or not isinstance(it.get("data"), str) or not it["data"]:
            continue
        if want is not None and it.get("uid") not in want:
            continue
        d = it["data"]
        out.append(d if d.startswith("data:") else "data:image/png;base64," + d)
        if len(out) >= limit:
            break
    return clean(out, limit)


def attach(messages: list, images) -> list:
    """게이트웨이 messages의 마지막 user 말에 그림 조각을 붙인 새 목록(그림이 없으면 그대로)."""
    images = [u for u in images or [] if isinstance(u, str) and u]
    if not images or not messages or messages[-1].get("role") != "user":
        return messages
    c = messages[-1]["content"]
    parts = list(c) if isinstance(c, list) else [{"type": "text", "text": str(c)}]
    parts += [{"type": "image_url", "image_url": {"url": u}} for u in images]
    return messages[:-1] + [{**messages[-1], "content": parts}]


def note(n: int) -> str:
    """글 재료 끝에 붙이는 한 줄 — 그림이 있다는 걸 모델이 알게."""
    return f"\n\n[같이 보낸 그림 {n}장 — 칠판에 있는 그림이에요. 그림 속 글·숫자·모양도 재료로 쓰세요]" if n else ""
