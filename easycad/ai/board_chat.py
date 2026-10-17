"""웹 칠판 KAIROS 대화(§8 항목61 ⓒ, 2026-10-17) — 칠판 옆 대화창이 서버(`web/server.py`)를 거쳐 부른다(Qt 비의존).

`gateway.call_text`는 말 한 번만 보낸다. 대화창은 앞 대화를 이어 물어야 해서 여러 차례(messages)를 그대로 보낸다.
칠판에서 고른 것의 글은 그 질문 앞에 붙인다 — AI가 "이 카드"가 무엇인지 알게(앞 차례에 고른 글도 차례마다 `context`로 남아
이어 묻기에서 다시 보낸다).
답은 칠판 카드로 붙을 수 있으니 짧고 구조 있게 쓰라고 지시한다(카드가 길면 칠판이 금방 넘친다).
"""
from __future__ import annotations

import time

from easycad.ai import gateway as gw

SYSTEM = """너는 사용자가 하루 종일 옆에 띄워 두는 「웹 칠판」의 대화 도우미다. 한국어로 답한다.
- 답은 칠판에 카드로 붙을 수 있다. 결론을 첫 문장에 쓰고, 짧은 문단이나 짧은 목록(- )으로 쓴다. 꼭 필요할 때만 길게.
- 강조는 **굵게**만 쓴다. 표·코드는 꼭 필요할 때만.
- 사용자가 칠판에서 고른 내용을 함께 보내면 그 내용을 바탕으로 답한다."""

MAX_TURNS = 40           # 보내는 앞 대화 상한(차례 수) — 오래된 것부터 버린다
MAX_CONTEXT = 20_000     # 칠판에서 고른 글 상한(자)


def _with_context(content: str, ctx: str) -> str:
    ctx = (ctx or "").strip()[:MAX_CONTEXT]
    return f"[칠판에서 고른 내용]\n{ctx}\n\n[질문]\n{content}" if ctx else content


def build_messages(history: list, context: str = "") -> list:
    """대화창 기록 [{"role": "user"|"assistant", "content", "context"?}] → 게이트웨이에 보낼 messages.
    사용자 말에 딸린 `context`(그때 칠판에서 고른 글)는 그 말 앞에 붙인다. `context` 인자는 마지막 말에 더 붙일 글."""
    turns = [{"role": m["role"], "content": _with_context(str(m.get("content", "")), m.get("context", "") if m["role"] == "user" else "")}
             for m in history if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()]
    turns = turns[-MAX_TURNS:]
    while turns and turns[0]["role"] != "user":   # 잘라낸 뒤 답으로 시작하면 안 된다
        turns.pop(0)
    if not turns or turns[-1]["role"] != "user":
        raise ValueError("마지막 말이 질문이 아닙니다")
    if (context or "").strip():
        turns[-1] = {"role": "user", "content": _with_context(turns[-1]["content"], context)}
    return [{"role": "system", "content": SYSTEM}] + turns


def chat(api_key: str, history: list, *, model: str, context: str = "", base_url: str = gw.BASE_URL,
         timeout: float = 180.0, client=None) -> dict:
    """한 차례 답 → {"content", "model", "elapsed"}. `client`는 시험용(가짜 클라이언트)."""
    messages = build_messages(history, context)
    client = client or gw._client(api_key, base_url, timeout=timeout)
    t0 = time.time()
    resp = client.chat.completions.create(model=model, max_tokens=gw.DEFAULT_MAX_TOKENS, messages=messages)
    return {"content": resp.choices[0].message.content or "", "model": model, "elapsed": round(time.time() - t0, 1)}


def models(api_key: str, base_url: str = gw.BASE_URL) -> dict:
    """모델 고르기 목록 — {"default", "featured": {"gpt": [{"id", "price"}], ...}}(데스크톱 `model_picker`와 같은 규칙)."""
    info = gw.list_text_models_info(api_key, base_url)
    feat = gw.featured_models(info)
    return {"default": gw.default_model_id(info),
            "featured": {v: [{"id": m["id"], "price": gw.price_text(m)} for m in rows] for v, rows in feat.items()}}
