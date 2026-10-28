"""웹 칠판 「💬 AI 말풍선」(2026-10-28 사용자 — 물건마다 작은 대화창: 큰 대화창에 여러 물건 작업이 섞이지 않게, §8 항목68 「메모에 AI가 직접 쓰기」를 품음).

말풍선 하나 = 칠판 물건 하나. 그 물건의 글(메모는 줄 전체)·그림만 보고, 그 말풍선의 앞 대화만 이어 보낸다.
메모·표·글 상자는 고쳐 달라는 말이면 고친 전체를 돌려주고(3단계 — 표·글은 2026-10-28 같은 날)(칠판이 그 자리에서 바꿈 — Ctrl+Z 한 번), 묻는 말이면 답만.
답 글은 Claude Docs 댓글처럼 짧게 — 고친 결과는 칠판에 보이니 「무엇을 바꿨는지」만. Qt 없음 — `web/server.py`가 부른다.
"""
from __future__ import annotations

import json
import time

from easycad.ai import gateway as gw

MAX_TURNS = 12     # 말풍선 앞 대화(물건 하나라 짧게)
MAX_TEXT = 20000   # 물건 글 상한

SYSTEM = """너는 사용자의 「웹 칠판」 위 물건 하나에 붙은 작은 AI 말풍선이다. 한국어로, 아래 [이 물건]만 다룬다.
- 답은 JSON 하나만: {"reply": "말풍선에 보일 짧은 답", "edit": "고친 물건 전체" 또는 null}
- [이 물건] 머리에 「고칠 수 있음」이 있고 사용자가 고쳐·바꿔·더해·줄여·정리해·이어 써 달라고 하면 edit에 **고친 물건 전체**를 쓴다. 말하지 않은 곳은 그대로 둔다.
  모양: 메모 = 마크다운(# 제목 · - 목록 · 1. 번호 · - [ ] 할 일(끝난 것 - [x]) · > 인용 · | 표 | · **굵게**) · 표 = 마크다운 표 하나(첫 줄 = 머리, 칸 수는 바꿔도 됨) · 글 = 글만(마크다운 기호 없이).
  물건에 없던 사실·숫자는 지어내지 않는다.
- 그때 reply는 무엇을 바꿨는지 한두 문장(내용을 다시 옮겨 쓰지 않는다 — 고친 것은 칠판에 바로 보인다).
- 묻는 말이면 edit는 null, reply에 답(결론 먼저, 짧게, 강조는 **굵게**만). 「고칠 수 있음」이 없는 물건은 늘 edit null.
- 그림이 함께 오면 그 그림을 보고 답한다."""
EDIT_NAME = {"memo": "메모", "table": "표", "text": "글"}   # 말풍선이 그 자리에서 고쳐 쓰는 물건(칠판이 `item.edit`으로 알려 줌)


def _item_block(item: dict) -> str:
    kind = str(item.get("type") or "물건")
    text = str(item.get("text") or "")[:MAX_TEXT]
    edit = EDIT_NAME.get(str(item.get("edit") or ""))
    return f"[이 물건 — {kind}{f' · 고칠 수 있음({edit})' if edit else ''}]\n{text if text.strip() else '(글 없음)'}"


def build_messages(item: dict, history: list, image: str = "") -> list:
    """말풍선 기록 [{"role", "content"}] + 물건 → 게이트웨이 messages. 물건(지금 모습)은 마지막 질문 앞에 붙인다(고친 뒤 다시 물어도 새 글로)."""
    turns = [{"role": m["role"], "content": str(m.get("content", ""))} for m in history
             if isinstance(m, dict) and m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()][-MAX_TURNS:]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    if not turns or turns[-1]["role"] != "user":
        raise ValueError("마지막 말이 질문이 아닙니다")
    last = f"{_item_block(item)}\n\n[사용자]\n{turns[-1]['content']}"
    turns[-1] = {"role": "user", "content": [{"type": "text", "text": last}, {"type": "image_url", "image_url": {"url": image}}] if image else last}
    return [{"role": "system", "content": SYSTEM}] + turns


def parse(text: str, editable: bool) -> dict:
    """모델 답 → {"reply", "edit"?}. JSON이 아니면 글 전체를 답으로(고치지 않음)."""
    t = gw.strip_code_fence(text or "")
    i, j = t.find("{"), t.rfind("}")
    try:
        d = json.loads(t[i:j + 1]) if i >= 0 else None
    except ValueError:
        d = None
    if not isinstance(d, dict):
        return {"reply": (text or "").strip()}
    out = {"reply": str(d.get("reply") or "").strip()}
    edit = d.get("edit") if d.get("edit") is not None else d.get("memo")   # 옛 이름(memo)도 받음
    if editable and isinstance(edit, str) and edit.strip():
        out["edit"] = edit.strip()
        out["reply"] = out["reply"] or "고쳤어요."
    return out


def reply(api_key: str, item: dict, history: list, *, model: str = gw.FALLBACK_DEFAULT_MODEL, image: str = "",
          base_url: str = gw.BASE_URL, client=None, timeout: float = 180.0) -> dict:
    """한 차례 → {"content", "edit"?(고친 물건 전체 — 메모·표는 마크다운, 글은 글), "model", "elapsed"}. `client` = 시험용 가짜."""
    messages = build_messages(item, history, image)
    t0 = time.time()
    client = client or gw._client(api_key, base_url, timeout=timeout)
    resp = client.chat.completions.create(model=model, max_tokens=gw.DEFAULT_MAX_TOKENS, messages=messages)
    got = parse(resp.choices[0].message.content or "", str(item.get("edit") or "") in EDIT_NAME)
    out = {"content": got["reply"], "model": model, "elapsed": round(time.time() - t0, 1)}
    if "edit" in got:
        out["edit"] = got["edit"]
    return out
