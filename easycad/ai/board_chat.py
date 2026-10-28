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
SEARCH_MODEL = "exa-answer"   # KAIROS `/exa/answer/`(검색 + 출처 번호 단 답, Exa 그대로 중계). 2026-10-21 정답 있는 질문 5개 × 2번 비교(history):
#   Exa 8/10·2.5초·5크레딧 고정 = sonar-reasoning-pro 8/10·6.1초·약 7, Claude 검색 9/10이지만 약 57크레딧. 사용자 선택(보안은 상관없음 — 회사가 권장한 KAIROS)
SEARCH_FALLBACK = "sonar-reasoning-pro"   # Exa가 안 될 때(오류·크레딧) — 옛 기본(chat/completions + `citations`·`search_results`)
REWRITE_MODEL = "gpt-6-luna"              # 이어 묻는 말 → 혼자 통하는 검색 문장(Exa는 앞 대화를 못 봄) — 빠르고 싼 모델
SEARCH_SYSTEM = """너는 웹 검색 결과로 답하는 도우미다. 한국어 존댓말(~요·~습니다)로 답한다.
- 결론을 첫 문장에 쓰고, 짧은 목록(- )으로 정리한다. 강조는 **굵게**만.
- 문장 끝에 근거 출처 번호를 [1]처럼 붙인다. 출처 목록은 따로 쓰지 않는다(앱이 붙인다)."""
# 「내일 전주 날씨」 — 오늘 날짜를 알려 줘도 검색 답이 어제 기사의 「내일」(= 오늘)을 옮겼음(2026-10-21 5종 모두). 보내기 전에 날짜로 바꿔 넣는다
_REL_DAYS = {"그저께": -2, "그제": -2, "어제": -1, "오늘": 0, "내일": 1, "모레": 2, "글피": 3}
_REL_RE = re.compile(r"(그저께|그제|어제|오늘|내일|모레|글피)(?!\s*\()")
_SEARCH_WORDS = re.compile(r"검색|찾아|최신|최근|요즘|오늘|어제|이번\s*(주|달)|올해|뉴스|기사|출처|링크|사이트|홈페이지|동향|현황|시세|가격|환율|날씨|발표했|출시|일정|언제\s*(부터|까지)")
# 칠판에서 찾아 답하기(§8 항목61 ③-2 뜻으로 찾기) — 「지난번 송신소 점검 뭐였지?」 → 칠판 글(`board_find`)만 근거, [칠판 n]으로 출처
BOARD_SYSTEM = """너는 사용자의 「웹 칠판」에 쌓인 메모·글을 찾아 답하는 도우미다. 한국어로 답한다.
- 아래 [칠판 n] 글만 근거로 답한다. 칠판에 없는 내용은 지어내지 말고 「칠판에서 못 찾았어요」라고 말한다.
- 결론을 첫 문장에 쓰고 짧게 정리한다. 근거가 된 문장 끝에 [칠판 1]처럼 번호를 붙인다. 강조는 **굵게**만."""
_BOARD_WORDS = re.compile(r"지난번|저번|예전에|아까|칠판에(서)?\s*(찾|있|적)|우리가\s*(정리|적|메모)|(정리|메모|기록|적어)\s*(해\s*)?(둔|놨|뒀|했던|한\s*거)")
# 그림(§8 항목61 ③-4) — 「그려줘·일러스트·이미지 만들어」. 흐름도·도면·표처럼 칠판 도형으로 그릴 것은 그림 모델이 아니라 대화로(그림 모델은 글자·선이 엉킴)
_IMAGE_WORDS = re.compile(r"그려\s*(줘|주세요|봐)|그림\s*(을|으로|좀)?\s*(그려|만들|생성)|이미지\s*(를|로)?\s*(만들|생성|그려)|일러스트|삽화|캐릭터\s*(만들|그려)")
_DIAGRAM_WORDS = re.compile(r"흐름도|순서도|플로우|도면|계통도|구성도|다이어그램|표로|마인드맵|조직도")   # 구성도 = 2026-10-23 측정(「송신소 구성도」가 그림으로 갔음)
# 아이콘(§8 항목63) — 선을 고칠 수 있는 SVG 도형(`board_icon`). 뜻이 분명한 말(SVG·벡터·선 그림) + 만들기 말이 같이 있을 때만.
# 「아이콘·심볼」은 뜻이 둘이라(귀여운 그림 vs 고칠 도형) 자동으론 안 보냄 — 대화창 「+ › ✏️ 아이콘」이 맡음(2026-10-23 사용자)
_ICON_WORDS = re.compile(r"svg|벡터|선\s*그림|라인\s*아트|고칠\s*수\s*있", re.I)
_MAKE_WORDS = re.compile(r"그려|그리|만들|생성|디자인|바꿔|바꾸|으로\s*(줘|해)")
_HOWTO_WORDS = re.compile(r"방법|어떻게|하는\s*법|드는\s*법|뭐야|뭔가요|무엇|어디|알려|종류|추천")
# 칠판에서 고른 그림 + 말(대화창 첨부, 2026-10-28) — 묻는 말이면 그림을 보고 답(대화), 고치는 말이면 그림 고치기(`board_image`).
# 전엔 고른 그림이 있으면 「사진·그림」 낱말만으로도 고치기로 가서(`board_image.FOLLOW_WORDS`) 「이 사진 설명해 줘」가 새 그림이 됐음
_IMG_ASK = re.compile(r"뭐|무엇|무슨|설명|알려|읽어|요약|분석|어떤|어디|왜|몇|누구|맞[아나는]|\?")
_IMG_FIX = re.compile(r"넣어|넣으|반영|바꿔|바꾸|추가|빼|지워|없애|고쳐|그려")   # 묻는 말에 섞여도 고치기
_IMG_EDIT = re.compile(r"넣어|넣으|반영|바꿔|바꾸|추가|빼|지워|없애|고쳐|그려|크게|작게|밝게|어둡게|색|날짜|제목|분위기|느낌|다시")


def image_intent(text: str) -> str:
    """고른 그림을 두고 한 말 → "ask"(그림을 보고 답) | "edit"(그림 고치기) | ""(모름 — 길 고르기에 맡김)."""
    t = text or ""
    if _IMG_ASK.search(t) and not _IMG_FIX.search(t):
        return "ask"
    return "edit" if _IMG_EDIT.search(t) else ""


def is_icon(text: str) -> bool:
    """「파라볼라 안테나 아이콘 그려 줘」·「이 그림 심볼로 바꿔 줘」 → 아이콘 길."""
    t = text or ""
    return bool(_ICON_WORDS.search(t) and _MAKE_WORDS.search(t) and not _HOWTO_WORDS.search(t))


_ICON_AMBIG = re.compile(r"아이콘|로고|심볼|기호|픽토그램|엠블럼")


def maybe_icon(text: str) -> bool:
    """「펭귄 아이콘 그려줘」 — 그림일 수도·고칠 도형일 수도(뜻이 둘) → 대화창이 되물음(§8 항목64). 뜻이 분명한 말(SVG·선 그림)이면 아님."""
    t = text or ""
    return bool(_ICON_AMBIG.search(t) and _MAKE_WORDS.search(t) and not _HOWTO_WORDS.search(t) and not is_icon(t))


# 정리 문서(「정리해 줘」 ①) — 칠판 자료를 아티팩트 같은 보고서·인포그래픽 한 장으로(`board_report`)
_REPORT_WORDS = re.compile(r"정리해\s*(줘|주세요|봐)|정리\s*(문서|보고서)|보고서|인포그래픽|브리핑\s*(자료|문서|으로)|한\s*장(으로|짜리)|요약\s*(문서|자료|보고)|인쇄용")
_DOC_WORDS = re.compile(r"문서|보고서|인포그래픽|브리핑|한\s*장|인쇄")
# 「○○ 정리해 줘」처럼 칠판에 없는 주제가 붙으면 정리 문서가 아니라 보통 짐작으로(2026-10-19 사용자 선택 — 「송신소 정전 점검 순서 정리해줘」가
# 칠판의 엉뚱한 자료로 「0건」 빈 틀 문서가 됐음). 그냥 「정리해 줘」·「이거·칠판 정리해 줘」·고른 것이 있을 때·문서 말(보고서·한 장…)이 있으면 그대로 정리 문서
_REPORT_PLAIN = re.compile(r"정리해\s*(줘|주세요|봐)")
_BOARD_REF = re.compile(r"이것들|이거|이것|이걸|이게|칠판|여기|위에?|지금까지|고른\s*것|모은\s*것|붙인\s*것|내용|자료|전부|모두|다|좀|싹|깔끔하게|한\s*번|간단히|짧게|잘")


def _has_topic(text: str) -> bool:
    """「정리해 줘」 말과 칠판을 가리키는 말·꾸밈말을 빼고도 낱말이 남으면 주제가 있는 것."""
    rest = _BOARD_REF.sub(" ", _REPORT_PLAIN.sub(" ", text))
    return len(re.sub(r"[^\w]|_", "", rest)) >= 2
_NO_SEARCH = re.compile(r"칠판에서 고른|이 (메모|글|카드)|위 (내용|글)|요약해|정리해|번역|고쳐|다듬")


def guess_kind(text: str, has_context: bool = False) -> str:
    """질문 → "report"(정리 문서) | "board"(칠판에서 찾아 답) | "icon"(아이콘 후보) | "image"(그림 후보) | "search"(웹 검색) | "chat"(대화).
    낱말 규칙(데스크톱 `guess_kind`처럼) — 칠판에서 고른 글을 다루는 말이면 대화."""
    t = text or ""
    if _REPORT_WORDS.search(t) and (has_context or _DOC_WORDS.search(t) or not _has_topic(t)):
        return "report"
    if _BOARD_WORDS.search(t):
        return "board"
    if is_icon(t):
        return "icon"
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


def renumber_sources(content: str, sources: list) -> tuple:
    """출처 번호를 1·2·3 차례로 다시 매김(본문 [n]도 같이) — 검색 모델은 찾은 결과 전체 번호를 써서 [1][6][10]처럼 띄엄띄엄 나왔다(2026-10-19 점검).
    목록에 없는 번호([9] 등)는 그대로 둔다."""
    new = {s["n"]: i + 1 for i, s in enumerate(sources)}
    text = re.sub(r"\[(\d{1,2})\]", lambda m: f"[{new[int(m.group(1))]}]" if int(m.group(1)) in new else m.group(0), content or "")
    return text, [{**s, "n": new[s["n"]]} for s in sources]


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


def _day(t: float) -> str:
    lt = time.localtime(t)
    return "%d년 %d월 %d일(%s)" % (lt.tm_year, lt.tm_mon, lt.tm_mday, "월화수목금토일"[lt.tm_wday])


def absolute_dates(text: str, now: float | None = None) -> str:
    """「내일 전주 날씨」 → 「내일(2026년 10월 22일(목)) 전주 날씨」 — 낱말은 두고 날짜를 덧붙인다(이미 괄호가 있으면 그대로)."""
    now = time.time() if now is None else now
    return _REL_RE.sub(lambda m: f"{m.group(1)}({_day(now + _REL_DAYS[m.group(1)] * 86400)})", text or "")


def exa_answer(api_key: str, query: str, system: str, *, base_url: str = gw.BASE_URL, http=None, timeout: float = 120.0) -> tuple:
    """KAIROS `/exa/answer/` → (답, `cited_sources`가 읽는 꼴 {"citations": [주소], "search_results": [{url, title, date}]}).
    스트리밍 없음·한 번에. Exa 오류(400 등)·크레딧 없음(402)은 RuntimeError."""
    import httpx
    http = http or httpx
    r = http.post(f"{base_url}/exa/answer/", headers={"Authorization": f"Bearer {api_key}"}, json={"query": query, "systemPrompt": system}, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"Exa HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    cites = [c for c in d.get("citations") or [] if c.get("url")]
    return str(d.get("answer") or ""), {"citations": [c["url"] for c in cites],
                                        "search_results": [{"url": c["url"], "title": c.get("title") or "", "date": (c.get("publishedDate") or "")[:10]} for c in cites]}


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
         timeout: float = 180.0, client=None, data: str = "", http=None, images=None) -> dict:
    """한 차례 답 → {"content", "model", "elapsed", "kind", "sources"?, "refs"?}. `client`·`http`는 시험용(가짜 클라이언트·가짜 Exa).
    `kind` = "search"·"chat"·"board"(대화창에서 바꿔 다시 물을 때), 비면 마지막 질문으로 짐작. 검색은 Exa(`SEARCH_MODEL`), 안 되면 `SEARCH_FALLBACK`.
    "board"는 서버가 칠판에서 찾은 글(`board_refs` — `board_find.find` 결과)을 근거로 붙여 묻고, 답에 쓰인 [칠판 n]을 `refs`로 돌려준다."""
    last = next((m for m in reversed(history) if m.get("role") == "user"), {})
    kind = kind if kind in ("search", "chat", "board") else guess_kind(str(last.get("content", "")), bool(context or last.get("context")))
    search, board = kind == "search", kind == "board"
    refs = list(board_refs or [])
    if board:
        context = ((context + "\n\n") if context else "") + (board_context(refs) or "(칠판에서 관련 글을 못 찾음)")
    messages = build_messages(history, context, SEARCH_SYSTEM if search else BOARD_SYSTEM if board else SYSTEM)
    if data:   # 공공 데이터 도구 결과(`kr_tools` — 기상청·천문연·법령·통계 등, 2026-10-20) — 숫자는 이것만, 출처 번호는 서버가 단 순서([1] 기상청 …)
        messages[-1] = {"role": "user", "content": f"[공공 데이터 — 숫자·날짜는 여기 것만 쓰고, 근거 문장 끝에 자료 머리의 번호를 [1]처럼. 출처 목록은 따로 쓰지 않는다(앱이 붙인다)]\n{data[:12000]}\n\n{messages[-1]['content']}"}
    if images and not search:   # 칠판에서 고른 그림을 보고 답(대화창 첨부, 2026-10-28) — 검색(Exa)은 글만 받아 안 붙임, 기록엔 안 남음(장수만)
        messages[-1] = {"role": "user", "content": [{"type": "text", "text": messages[-1]["content"]}]
                        + [{"type": "image_url", "image_url": {"url": u}} for u in list(images)[:4]]}
    t0 = time.time()
    if search:   # 오늘 날짜 + 「내일」→ 날짜(검색 답이 어제 기사의 「내일」을 옮기지 않게)
        messages[0] = {"role": "system", "content": f"{SEARCH_SYSTEM}\n- 오늘은 {_day(time.time())}."}
        messages[-1] = {"role": "user", "content": absolute_dates(messages[-1]["content"])}
        # Exa는 질문 한 줄로만 검색함 — 앞 대화(최근 4차례)는 지시문에 참고로, 이어 묻는 말은 혼자 통하는 검색 문장으로 바꿔서
        # (「그럼 금액은 얼마야?」를 그대로 보냈더니 「얼마예요」 뜻풀이를 찾아 답했음, 2026-10-21 실측). 칠판에서 고른 글은 이미 질문에 붙어 있음
        prev = "\n".join(f"{'나' if m['role'] == 'user' else 'AI'}: {m['content'][:500]}" for m in messages[1:-1][-4:])
        query = messages[-1]["content"]
        if prev:
            try:
                client = client or gw._client(api_key, base_url, timeout=timeout)
                q = client.chat.completions.create(model=REWRITE_MODEL, max_tokens=200, messages=[
                    {"role": "system", "content": "앞 대화를 보고 마지막 질문을 혼자서도 뜻이 통하는 한국어 검색 질문 한 문장으로 바꿔라. 괄호 속 날짜는 그대로 둔다. 그 문장만 쓴다."},
                    {"role": "user", "content": f"[앞 대화]\n{prev}\n\n[마지막 질문]\n{query}"}]).choices[0].message.content or ""
                query = q.strip().strip('"「」') or query
            except Exception:   # 못 바꾸면 그대로
                pass
        try:
            content, raw = exa_answer(api_key, query[:4000], messages[0]["content"] + (f"\n\n[앞 대화 — 참고만]\n{prev}" if prev else ""),
                                      base_url=base_url, http=http, timeout=timeout)
            text, sources = renumber_sources(content, cited_sources(content, raw))
            return {"content": text, "model": SEARCH_MODEL, "elapsed": round(time.time() - t0, 1), "kind": kind, "sources": sources}
        except Exception as e:   # Exa 오류·크레딧 — 옛 검색 모델로(대화창엔 답 모델 이름이 바뀌어 보임)
            import sys
            sys.stderr.write("[Exa 실패 → %s] %s\n" % (SEARCH_FALLBACK, e))
    client = client or gw._client(api_key, base_url, timeout=timeout)
    use = SEARCH_FALLBACK if search else model
    resp = client.chat.completions.create(model=use, max_tokens=gw.DEFAULT_MAX_TOKENS, messages=messages)
    content = resp.choices[0].message.content or ""
    out = {"content": content, "model": use, "elapsed": round(time.time() - t0, 1), "kind": kind}
    if getattr(resp.choices[0], "finish_reason", None) == "length":   # 길이 상한에 걸려 끊김(2026-10-27 — 전엔 다 된 것처럼 보임) → 대화창 「이어서 쓰기」
        out["cut"] = True
    if search:
        raw = resp.model_dump() if hasattr(resp, "model_dump") else dict(getattr(resp, "__dict__", {}))
        out["content"], out["sources"] = renumber_sources(content, cited_sources(content, raw))
    if board:
        out["refs"] = cited_board(content, refs)
    return out


def models(api_key: str, base_url: str = gw.BASE_URL) -> dict:
    """모델 고르기 목록 — {"default", "featured": {"gpt": [{"id", "price"}], ...}}(데스크톱 `model_picker`와 같은 규칙)."""
    info = gw.list_text_models_info(api_key, base_url)
    feat = gw.featured_models(info)
    return {"default": gw.default_model_id(info),
            "featured": {v: [{"id": m["id"], "price": gw.price_text(m)} for m in rows] for v, rows in feat.items()}}
