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
# 칠판에서 찾아 답하기(§8 항목61 ③-2 뜻으로 찾기) — 「지난번 송신소 점검 뭐였지?」 → 칠판 글(`board_find`)만 근거, [칠판 n]으로 출처
BOARD_SYSTEM = """너는 사용자의 「웹 칠판」에 쌓인 메모·글을 찾아 답하는 도우미다. 한국어로 답한다.
- 아래 [칠판 n] 글만 근거로 답한다. 칠판에 없는 내용은 지어내지 말고 「칠판에서 못 찾았어요」라고 말한다.
- 결론을 첫 문장에 쓰고 짧게 정리한다. 근거가 된 문장 끝에 [칠판 1]처럼 번호를 붙인다. 강조는 **굵게**만."""
_BOARD_WORDS = re.compile(r"지난번|저번|예전에|아까|칠판에(서)?\s*(찾|있|적)|우리가\s*(정리|적|메모)|(정리|메모|기록|적어)\s*(해\s*)?(둔|놨|뒀|했던|한\s*거)")
# 그림(§8 항목61 ③-4) — 「그려줘·일러스트·이미지 만들어」. 흐름도·도면·표처럼 칠판 도형으로 그릴 것은 그림 모델이 아니라 대화로(그림 모델은 글자·선이 엉킴)
_IMAGE_WORDS = re.compile(r"그려\s*(줘|주세요|봐)|그림\s*(을|으로|좀)?\s*(그려|만들|생성)|이미지\s*(를|로)?\s*(만들|생성|그려)|일러스트|삽화|캐릭터\s*(만들|그려)")
_DIAGRAM_WORDS = re.compile(r"흐름도|순서도|플로우|도면|계통도|다이어그램|표로|마인드맵|조직도")
# 정리 문서(「정리해 줘」 ①) — 칠판 자료를 아티팩트 같은 보고서·인포그래픽 한 장으로(`board_report`)
_REPORT_WORDS = re.compile(r"정리해\s*(줘|주세요|봐)|정리\s*(문서|보고서)|보고서|인포그래픽|브리핑\s*(자료|문서|으로)|한\s*장(으로|짜리)|요약\s*(문서|자료|보고)|인쇄용")
# 정리정돈(「정리해 줘」 ②) — 고른 것을 지우지 않고 주제별로 묶어 옮김(`board_tidy`). 「정리해 줘」만은 ①(문서) — 묶기·정돈 말이 있고 문서 말이 없을 때만
TIDY_WORDS = r"정돈|분류해|묶어\s*(줘|주세요|봐|서|놓)|모아\s*(줘|주세요|놓|서)|주제별|종류별|그룹(으로|별|지어)|끼리\s*(묶|모아)|레고"
_TIDY_WORDS = re.compile(TIDY_WORDS)
_DOC_WORDS = re.compile(r"문서|보고서|인포그래픽|브리핑|한\s*장|인쇄")
_NO_SEARCH = re.compile(r"칠판에서 고른|이 (메모|글|카드)|위 (내용|글)|요약해|정리해|번역|고쳐|다듬")


def guess_kind(text: str, has_context: bool = False) -> str:
    """질문 → "tidy"(정리정돈) | "report"(정리 문서) | "board"(칠판에서 찾아 답) | "image"(그림 후보) | "search"(웹 검색) | "chat"(대화).
    낱말 규칙(데스크톱 `guess_kind`처럼) — 칠판에서 고른 글을 다루는 말이면 대화."""
    t = text or ""
    if _TIDY_WORDS.search(t) and not _DOC_WORDS.search(t):
        return "tidy"
    if _REPORT_WORDS.search(t):
        return "report"
    if _BOARD_WORDS.search(t):
        return "board"
    if _IMAGE_WORDS.search(t) and not _DIAGRAM_WORDS.search(t):
        return "image"
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


def board_context(refs: list) -> str:
    """칠판에서 찾은 글 → 질문 앞에 붙일 글([칠판 n] (종류) 글)."""
    return "\n\n".join(f"[칠판 {i + 1}] ({r.get('kind') or r.get('type', '')}) {r.get('text', '')}" for i, r in enumerate(refs))


def cited_board(content: str, refs: list) -> list:
    """답에 쓰인 [칠판 n]의 글만 → [{"n", "uid", "kind", "text"}]."""
    used = sorted({int(n) for n in re.findall(r"\[칠판\s*(\d{1,2})\]", content or "") if 1 <= int(n) <= len(refs)})
    return [{"n": n, "uid": refs[n - 1]["uid"], "kind": refs[n - 1].get("kind", ""), "text": refs[n - 1].get("text", "")[:200]} for n in used]


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


def chat(api_key: str, history: list, *, model: str, context: str = "", kind: str = "", board_refs=None, base_url: str = gw.BASE_URL,
         timeout: float = 180.0, client=None) -> dict:
    """한 차례 답 → {"content", "model", "elapsed", "kind", "sources"?, "refs"?}. `client`는 시험용(가짜 클라이언트).
    `kind` = "search"·"chat"·"board"(대화창에서 바꿔 다시 물을 때), 비면 마지막 질문으로 짐작. 검색은 모델을 `SEARCH_MODEL`로 바꾼다.
    "board"는 서버가 칠판에서 찾은 글(`board_refs` — `board_find.find` 결과)을 근거로 붙여 묻고, 답에 쓰인 [칠판 n]을 `refs`로 돌려준다."""
    last = next((m for m in reversed(history) if m.get("role") == "user"), {})
    kind = kind if kind in ("search", "chat", "board") else guess_kind(str(last.get("content", "")), bool(context or last.get("context")))
    search, board = kind == "search", kind == "board"
    refs = list(board_refs or [])
    if board:
        context = ((context + "\n\n") if context else "") + (board_context(refs) or "(칠판에서 관련 글을 못 찾음)")
    messages = build_messages(history, context, SEARCH_SYSTEM if search else BOARD_SYSTEM if board else SYSTEM)
    client = client or gw._client(api_key, base_url, timeout=timeout)
    use = SEARCH_MODEL if search else model
    t0 = time.time()
    resp = client.chat.completions.create(model=use, max_tokens=gw.DEFAULT_MAX_TOKENS, messages=messages)
    content = resp.choices[0].message.content or ""
    out = {"content": content, "model": use, "elapsed": round(time.time() - t0, 1), "kind": kind}
    if search:
        raw = resp.model_dump() if hasattr(resp, "model_dump") else dict(getattr(resp, "__dict__", {}))
        out["sources"] = cited_sources(content, raw)
    if board:
        out["refs"] = cited_board(content, refs)
    return out


def models(api_key: str, base_url: str = gw.BASE_URL) -> dict:
    """모델 고르기 목록 — {"default", "featured": {"gpt": [{"id", "price"}], ...}}(데스크톱 `model_picker`와 같은 규칙)."""
    info = gw.list_text_models_info(api_key, base_url)
    feat = gw.featured_models(info)
    return {"default": gw.default_model_id(info),
            "featured": {v: [{"id": m["id"], "price": gw.price_text(m)} for m in rows] for v, rows in feat.items()}}
