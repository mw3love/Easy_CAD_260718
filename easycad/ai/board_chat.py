"""웹 칠판 KAIROS 대화(§8 항목61 ⓒ, 2026-10-17) — 칠판 옆 대화창이 서버(`web/server.py`)를 거쳐 부른다(Qt 비의존).

`gateway.call_text`는 말 한 번만 보낸다. 대화창은 앞 대화를 이어 물어야 해서 여러 차례(messages)를 그대로 보낸다.
칠판에서 고른 것의 글은 그 질문 앞에 붙인다 — AI가 "이 카드"가 무엇인지 알게(앞 차례에 고른 글도 차례마다 `context`로 남아
이어 묻기에서 다시 보낸다).
답은 칠판 카드로 붙을 수 있으니 짧고 구조 있게 쓰라고 지시한다(카드가 길면 칠판이 금방 넘친다).
"""
from __future__ import annotations

import re
import time

from easycad.ai import gateway as gw

SYSTEM = """너는 사용자가 하루 종일 옆에 띄워 두는 「웹 칠판」의 대화 도우미다. 한국어로 답한다.
- 답은 칠판에 카드로 붙을 수 있다. 결론을 첫 문장에 쓰고, 짧은 문단이나 짧은 목록(- )으로 쓴다. 꼭 필요할 때만 길게.
- 강조는 **굵게**만 쓴다. 표·코드는 꼭 필요할 때만.
- 사용자가 칠판에서 고른 내용을 함께 보내면 그 내용을 바탕으로 답한다."""

# 웹 검색(§8 항목61 ② 담는 법, 2026-10-19) — 입구는 대화창 하나, 종류는 앱이 짐작(`guess_kind`)하고 답 위에 보여 한 번에 바꾸게.
# 검색 답 = 요약 메모 + 본문에 실제로 쓰인 번호([1]…)의 출처만 → 칠판에서 웹 카드·번호 화살표로 이어 놓는다(web Editor `pinCard`).
SEARCH_MODEL = "sonar-pro"   # KAIROS 웹 검색(답 + `search_results` 제목·주소·날짜, 2026-10-19 실호출 3.4초·$0.004)
SEARCH_SYSTEM = """너는 웹 검색 결과로 답하는 도우미다. 한국어로 답한다.
- 결론을 첫 문장에 쓰고, 짧은 목록(- )으로 정리한다. 강조는 **굵게**만.
- 문장 끝에 근거 출처 번호를 [1]처럼 붙인다. 출처 목록은 따로 쓰지 않는다(앱이 붙인다)."""
_SEARCH_WORDS = re.compile(r"검색|찾아|최신|최근|요즘|오늘|어제|이번\s*(주|달)|올해|뉴스|기사|출처|링크|사이트|홈페이지|동향|현황|시세|가격|환율|날씨|발표했|출시|일정|언제\s*(부터|까지)")
_NO_SEARCH = re.compile(r"칠판에서 고른|이 (메모|글|카드)|위 (내용|글)|요약해|정리해|번역|고쳐|다듬")


def guess_kind(text: str, has_context: bool = False) -> str:
    """질문 → "search"(웹 검색) | "chat"(대화). 낱말 규칙(데스크톱 `guess_kind`처럼) — 칠판에서 고른 글을 다루는 말이면 대화."""
    t = text or ""
    if has_context and _NO_SEARCH.search(t):
        return "chat"
    return "search" if _SEARCH_WORDS.search(t) else "chat"


def cited_sources(content: str, raw: dict, keep_if_none: int = 3) -> list:
    """답 본문에 쓰인 번호([n])의 출처만 [{"n", "url", "title", "date"}] — 번호는 `citations` 차례(1부터).
    제목·날짜는 `search_results`에서 주소로 찾는다. 번호가 하나도 없으면 앞 `keep_if_none`개."""
    urls = list(raw.get("citations") or []) or [r.get("url") for r in raw.get("search_results") or []]
    info = {r.get("url"): r for r in raw.get("search_results") or []}
    used = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", content or "") if 1 <= int(n) <= len(urls)})
    out = []
    for n in used or list(range(1, min(keep_if_none, len(urls)) + 1)):
        u = urls[n - 1]
        if not u:
            continue
        r = info.get(u, {})
        out.append({"n": n, "url": u, "title": (r.get("title") or "").strip(), "date": r.get("date") or ""})
    return out


MAX_TURNS = 40           # 보내는 앞 대화 상한(차례 수) — 오래된 것부터 버린다
MAX_CONTEXT = 20_000     # 칠판에서 고른 글 상한(자)


def _with_context(content: str, ctx: str) -> str:
    ctx = (ctx or "").strip()[:MAX_CONTEXT]
    return f"[칠판에서 고른 내용]\n{ctx}\n\n[질문]\n{content}" if ctx else content


def build_messages(history: list, context: str = "", system: str = SYSTEM) -> list:
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
    return [{"role": "system", "content": system}] + turns


def chat(api_key: str, history: list, *, model: str, context: str = "", kind: str = "", base_url: str = gw.BASE_URL,
         timeout: float = 180.0, client=None) -> dict:
    """한 차례 답 → {"content", "model", "elapsed", "kind", "sources"?}. `client`는 시험용(가짜 클라이언트).
    `kind` = "search"·"chat"(대화창에서 바꿔 다시 물을 때), 비면 마지막 질문으로 짐작. 검색은 모델을 `SEARCH_MODEL`로 바꾼다."""
    last = next((m for m in reversed(history) if m.get("role") == "user"), {})
    kind = kind if kind in ("search", "chat") else guess_kind(str(last.get("content", "")), bool(context or last.get("context")))
    search = kind == "search"
    messages = build_messages(history, context, SEARCH_SYSTEM if search else SYSTEM)
    client = client or gw._client(api_key, base_url, timeout=timeout)
    use = SEARCH_MODEL if search else model
    t0 = time.time()
    resp = client.chat.completions.create(model=use, max_tokens=gw.DEFAULT_MAX_TOKENS, messages=messages)
    content = resp.choices[0].message.content or ""
    out = {"content": content, "model": use, "elapsed": round(time.time() - t0, 1), "kind": kind}
    if search:
        raw = resp.model_dump() if hasattr(resp, "model_dump") else dict(getattr(resp, "__dict__", {}))
        out["sources"] = cited_sources(content, raw)
    return out


def models(api_key: str, base_url: str = gw.BASE_URL) -> dict:
    """모델 고르기 목록 — {"default", "featured": {"gpt": [{"id", "price"}], ...}}(데스크톱 `model_picker`와 같은 규칙)."""
    info = gw.list_text_models_info(api_key, base_url)
    feat = gw.featured_models(info)
    return {"default": gw.default_model_id(info),
            "featured": {v: [{"id": m["id"], "price": gw.price_text(m)} for m in rows] for v, rows in feat.items()}}
