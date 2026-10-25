"""웹 칠판 딥모드(§8 항목66 3-3, 2026-10-25) — 한 주제로 칠판 한 판: 편집장 계획 → 재료 모으기 → 기자 본문. Qt 비의존, 서버 `/api/chat` `kind: 'deep'`이 부른다.

- 계획 = 편집장(claude-opus-5-5 — 0단계 실측: gpt-6.1-sol은 1/3 값이지만 더 추상적·검색 문장이 너무 김). 숫자는 쓰지 않고 꼭지(모양·재료 출처·검색 문장)만.
  말로 고치기 = 앞 계획 + 고칠 말로 다시. 장 수는 계획에서 뺌(opus가 늘 2라고 함 — 칠판이 잼).
- 재료 = 꼭지마다 동시에: web = Exa(`board_chat.exa_answer`), kr = 공공 데이터(`kr_tools.gather` — 못 찾으면 웹 검색으로 갈아탐). 출처 번호는 판 전체에서 하나로.
- 본문 = 기자(claude-sonnet-5-5 한 번에 — 3-0 실측: opus와 품질 검사 같고 약 40% 쌈). 꼭지 모양마다 칠판이 읽는 칸만(`web/src/next/deepboard.js` `deepSection`).
실측 도구: `tools/deepmode_probe.py`(계획·재료)·`tools/deepbody_probe.py`(본문) — 지시문을 여기와 맞춰 둘 것.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import board_chat, kr_tools, live_card
from . import gateway as gw

EDITOR_MODEL = "claude-opus-5-5"
WRITER_MODEL = "claude-sonnet-5-5"
# 칠판이 그릴 줄 아는 모양(`deepboard.js`). 「움직이는 카드」 = 스크립트 켠 HTML(`live_card`, 4단계 — 한 판에 하나), 그림·아이콘 꼭지는 아직
SHAPES = ("주인공 글", "숫자 타일", "단계 카드", "그래프", "표", "움직이는 카드", "용어 풀이", "접힌 메모", "확인 문제", "출처 카드")
SOURCES = ("ai", "web", "kr", "board")
CHARTS = ("세로 막대", "가로 막대", "꺾은선", "원")
NUMERIC = ("숫자 타일", "그래프", "표")
SIZES = ("주인공", "보통", "작게")
MAX_SECTIONS = 9

EDITOR = """너는 「웹 칠판」의 편집장이다. 사용자의 주제 하나로 칠판 한 판을 신문 지면처럼 채울 **지면 계획**만 세운다(본문은 아직 쓰지 않는다).
목표: 독자가 한 판을 보고 빠르게 이해한다. 꾸미려고 넣는 꼭지는 없다. 오늘은 {today}.

출력은 JSON 하나뿐(설명·코드펜스 없이):
{{"title": "지면 제목", "headline": "큰 제목 한 줄",
  "sections": [{{"title": "꼭지 제목", "question": "이 꼭지가 답하는 독자의 질문", "shape": 모양, "chart": 그래프 종류 또는 null,
                 "source": 재료 출처, "query": 검색·조회 문장 또는 null, "size": "주인공" | "보통" | "작게"}}]}}

- sections는 5~9개, 읽는 순서대로. "주인공"은 하나만. 마지막은 보통 「출처 카드」(숫자·사실 꼭지가 있으면 꼭).
- shape는 다음 중 하나: {shapes}. 꼭지마다 모양 하나 — 숫자 비교 = 그래프, 순서 = 단계 카드, 핵심 숫자 몇 개 = 숫자 타일, 낯선 낱말 = 용어 풀이,
  직접 만져 보면 이해되는 원리(값을 바꾸면 결과가 바뀌는 것) = 움직이는 카드(한 판에 하나까지, source ai — 숫자는 다른 꼭지 재료에서 가져다 씀).
- chart는 shape가 그래프일 때만: {charts}. 자료에 맞는 종류(비교 = 막대, 시간 흐름 = 꺾은선, 전체 중 몫 = 원).
- source는 다음 중 하나: ai(일반 지식으로 AI가 씀 — 설명·용어·문제·원리 단계), web(웹 검색), kr(한국 공공 데이터 — 통계청·한국은행·법령·날씨), board(이 칠판에 있는 자료).
- **숫자·날짜·최신 사실이 들어가는 꼭지는 source가 web 또는 kr**(ai 금지). query는 앞 대화 없이 혼자 통하는 한국어 검색 문장(최신이면 연도·달 포함).
  kr이면 query에 「통계」「법령」 같은 낱말을 넣는다.
- 계획에는 숫자·사실을 쓰지 않는다(제목은 「기억할 숫자 3개」처럼). 숫자는 재료에서 온다.
- 질문지 답(누구에게·무엇에·깊이·꼭 넣을 것·재료)을 따른다. 「알아서」는 네가 정한다."""

SCHEMA = {
    "주인공 글": '{"text": ["문단", "문단"]} — 2~3문단, 핵심은 **굵게**',
    "용어 풀이": '{"terms": [["낱말", "풀이 한 줄"], …]} — 3~5개',
    "단계 카드": '{"steps": [["단계 이름(짧게)", "한 줄 설명"], …]} — 3~6단계',
    "그래프": '{"rows": [["항목 이름", "계열 이름(단위)"], ["항목", "숫자 [n]"], …], "header": true, "kind": "line"|"col"|"row"|"pie", "caption": "한 줄"} — 칸 숫자마다 [n]',
    "표": '{"rows": [["", "열 이름", …], ["행 이름", "칸", …], …], "header": true} — 숫자 칸엔 [n]',
    "숫자 타일": '{"tiles": [["값+단위", "한 줄 설명", n], …]} — 2~4개, n = 출처 번호(숫자)',
    "확인 문제": '{"items": ["…을 말할 수 있다", …]} — 3개',
    "출처 카드": '{"links": [n, …]} — 판에서 쓴 출처 번호',
    "접힌 메모": '{"md": "- 줄\\n- 줄"} — 5~8줄, 숫자엔 [n]',
    "움직이는 카드": '{"note": "무엇을 움직이면 무엇이 보이는지 한 줄"} — 카드 HTML은 따로 만듦(칠판엔 카드 밑 설명)',
}

WRITER = """너는 「웹 칠판」 딥모드의 기자다. 편집장이 세운 지면 계획의 꼭지마다 **본문**을 쓴다. 칠판이 그대로 물건으로 짓는다(메모·표·그래프·숫자 타일).
독자: {audience}. 목표: 한 판을 보고 빠르게 이해. 쉬운 우리말, 짧은 문장, 「~요」체. 오늘은 {today}.

규칙:
- 숫자·날짜·최신 사실은 **재료에 있는 것만**, 쓴 자리마다 출처 번호 [n](재료 머리의 번호 그대로). 재료에 없는 숫자는 지어내지 않는다 — 모자라면 항목을 줄인다.
- source가 ai인 꼭지(설명·용어·문제·단계)는 숫자 없이 일반 지식으로.
- 꼭지 모양마다 정해진 칸만(아래). 설명·코드펜스 없이 JSON 하나:
{{"sections": [{{"title": "꼭지 제목 그대로", "body": {{…}}}}, …]}}

모양별 body 칸:
{schema}"""

AUTO = "알아서"


def today() -> str:
    t = time.localtime()
    return "%d년 %d월 %d일" % (t.tm_year, t.tm_mon, t.tm_mday)


def brief_text(brief: dict) -> str:
    """질문지 답 → 지시문 줄(대화창 `deepchat.jsx` `briefOf` 꼴 — 안 고른 것은 「알아서」, 「더」 = 입력 칸 글)."""
    b = brief if isinstance(brief, dict) else {}
    keys = ("누구에게", "무엇에", "깊이", "꼭 넣을 것", "재료")
    out = [f"- {k}: {', '.join(map(str, b[k])) if isinstance(b.get(k), list) else b.get(k) or AUTO}" for k in keys]
    if str(b.get("더") or "").strip():
        out.append(f"- 더(사용자가 직접 쓴 말 — 꼭 따름): {str(b['더']).strip()[:500]}")
    return "\n".join(out)


def parse_json(text: str):
    t = gw.strip_code_fence(text or "")
    i, j = t.find("{"), t.rfind("}")
    try:
        return json.loads(t[i:j + 1]) if i >= 0 else None
    except ValueError:
        return None


def clean_plan(plan) -> dict:
    """AI 계획 다듬기 — 모르는 모양·출처·크기는 고치고, 숫자 꼭지를 ai로 두면 web으로, 주인공은 하나, 꼭지 9개까지. 꼭지가 없으면 ValueError."""
    if not isinstance(plan, dict):
        raise ValueError("편집장 답이 JSON이 아니에요 — 다시 짜 주세요")
    secs, hero = [], False
    for s in plan.get("sections") or []:
        if not isinstance(s, dict) or not str(s.get("title") or "").strip():
            continue
        shape = s.get("shape") if s.get("shape") in SHAPES else "접힌 메모"
        src = s.get("source") if s.get("source") in SOURCES else "ai"
        if shape in NUMERIC and src == "ai":   # 숫자는 재료에서만(0단계 원칙) — 계획이 어겨도 검색으로
            src = "web"
        if shape == "움직이는 카드":   # 한 판에 하나(비싸고 화면을 크게 먹음 — 4단계 계획), 재료는 다른 꼭지 것을 씀
            if any(x["shape"] == "움직이는 카드" for x in secs):
                shape = "단계 카드"
            else:
                src = "ai"
        if shape == "출처 카드":   # 판에서 모은 출처를 보일 뿐 — 재료를 따로 안 모음(편집장이 web·board로 적어 검색 한 번이 헛돌았음, 3-3 실측)
            src = "ai"
        size = s.get("size") if s.get("size") in SIZES else "보통"
        if size == "주인공":
            size, hero = ("보통", hero) if hero else ("주인공", True)
        chart = s.get("chart") if shape == "그래프" and s.get("chart") in CHARTS else None
        q = str(s.get("query") or "").strip() or None
        secs.append({"title": str(s["title"]).strip()[:60], "question": str(s.get("question") or "").strip()[:200], "shape": shape, "chart": chart,
                     "source": src, "query": (q or str(s["title"]))[:300] if src in ("web", "kr") else None, "size": size})
    if not secs:
        raise ValueError("편집장이 꼭지를 하나도 못 짰어요 — 주제를 조금 더 구체적으로 적어 주세요")
    return {"title": str(plan.get("title") or "").strip()[:60] or secs[0]["title"], "headline": str(plan.get("headline") or "").strip()[:120], "sections": secs[:MAX_SECTIONS]}


def estimate(plan: dict) -> dict:
    """「이대로 만들기」 값 어림(재료 + 본문) — 3-0 실측(웹 꼭지 3초·5cr, 공공 22~26초, 본문 sonnet 38~80cr·23~37초)에서. 추정."""
    secs = plan.get("sections") or []
    web, kr = sum(s["source"] == "web" for s in secs), sum(s["source"] == "kr" for s in secs)
    live = any(s["shape"] == "움직이는 카드" for s in secs)   # 카드 한 장 약 45cr·55~75초(4-0 실측 sol) — 본문과 동시. 4-2 실조건 한 판 = 만들기 113초·117cr
    lo = 5 * web + 8 * kr + 25 + 3 * len(secs) + (40 if live else 0)
    hi = round(lo * 1.6)
    sec = [(25 if kr else 4) + 23, (35 if kr else 8) + 40]
    return {"credits": [lo, hi], "seconds": [max(sec[0], 60), max(sec[1], 120)] if live else sec}


def plan_prompt(topic: str, brief: dict, prev: dict | None = None, fix: str = "") -> str:
    head = f"[주제]\n{topic.strip()[:1000]}\n\n[질문지 답]\n{brief_text(brief)}\n\n"
    if prev and fix:
        return head + f"[앞 계획 — 사용자가 이미 본 것(빼 달라던 꼭지는 이미 빠져 있음)]\n{json.dumps(clean_plan(prev), ensure_ascii=False)}\n\n[고칠 점]\n{fix.strip()[:500]}\n\n앞 계획을 고칠 점대로 고친 지면 계획 JSON을 써 줘(말하지 않은 꼭지는 그대로)."
    return head + "지면 계획 JSON을 써 줘."


def make_plan(client, topic: str, brief: dict, *, prev: dict | None = None, fix: str = "", model: str = EDITOR_MODEL, day: str = "") -> dict:
    """주제 + 질문지 답(+ 앞 계획·고칠 말) → {"plan", "estimate", "model", "elapsed"}."""
    if not str(topic or "").strip():
        raise ValueError("주제가 비어 있어요")
    t0 = time.time()
    r = client.chat.completions.create(model=model, max_tokens=6000, messages=[
        {"role": "system", "content": EDITOR.format(today=day or today(), shapes="·".join(SHAPES), charts="·".join(CHARTS))},
        {"role": "user", "content": plan_prompt(topic, brief, prev, fix)}])
    plan = clean_plan(parse_json(r.choices[0].message.content or ""))
    return {"plan": plan, "estimate": estimate(plan), "model": model, "elapsed": round(time.time() - t0, 1)}


def gather(key: str, plan: dict, *, base_url: str = gw.BASE_URL, day: str = "", exa=None, kr=None) -> dict:
    """꼭지마다 재료 글 + 판 전체 출처 목록 {"sources": [{n, title, url}], "materials": [{"text"} | None]}.
    재료 글 속 [k](도구마다 따로 매긴 번호)는 판 번호 [n]으로 바꿈. 공공 데이터가 비면 웹 검색으로 갈아탐. exa·kr = 시험용 바꿔 끼우기."""
    exa = exa or (lambda q: board_chat.exa_answer(key, q, board_chat.SEARCH_SYSTEM, base_url=base_url))
    kr = kr or (lambda q: kr_tools.gather(key, q, base_url=base_url, today=day or today()))

    def web(q):
        ans, raw = exa(q[:4000])
        return {"text": ans, "sources": [{"title": x.get("title") or x["url"], "url": x["url"]} for x in raw.get("search_results") or []]}

    def one(sec):
        src, q = sec.get("source"), (sec.get("query") or sec.get("title") or "")
        try:
            if src == "kr":
                found = kr(q)
                if found:
                    return {"text": kr_tools.context_text(found), "sources": [{"title": s["title"], "url": s["url"]} for s in kr_tools.sources(found)]}
                return web(q)   # 공공 데이터가 못 찾으면 웹 검색(0단계: 셋 중 하나만 성공)
            if src == "web":
                return web(q)
        except Exception as e:   # 한 꼭지가 틀어져도 나머지는 — 기자에게 「재료 없음」으로
            return {"text": "", "sources": [], "error": f"{type(e).__name__}: {e}"[:200]}
        return None

    secs = plan.get("sections") or []
    with ThreadPoolExecutor(max_workers=max(1, len(secs))) as ex:
        got = list(ex.map(one, secs))
    allsrc, mats = [], []
    for g in got:
        if not g:
            mats.append(None)
            continue
        local = {}
        for k, s in enumerate(g["sources"], 1):
            hit = next((x for x in allsrc if s["url"] and x["url"] == s["url"]), None) or next((x for x in allsrc if not s["url"] and x["title"] == s["title"]), None)
            if not hit:
                hit = {"n": len(allsrc) + 1, **s}
                allsrc.append(hit)
            local[k] = hit["n"]
        text = re.sub(r"\[(\d+)\]", lambda m: f"[{local[int(m.group(1))]}]" if int(m.group(1)) in local else "", g["text"])
        mats.append({"text": text, **({"error": g["error"]} if g.get("error") else {})})
    return {"sources": allsrc, "materials": mats}


def material_text(plan: dict, mat: dict, board: str = "") -> str:
    lines = [f"[지면] {plan.get('title')} — {plan.get('headline')}", "", "[꼭지]"]
    for i, s in enumerate(plan.get("sections") or []):
        lines.append(f"{i + 1}. {s.get('title')} · 모양 {s.get('shape')}{' · ' + s['chart'] if s.get('chart') else ''} · 출처 {s.get('source')} · 크기 {s.get('size')}\n   독자의 질문: {s.get('question')}")
        m = mat["materials"][i]
        if m and m.get("text"):
            lines.append("   [재료]\n" + "\n".join("   " + x for x in m["text"][:5000].splitlines()))
        elif s.get("source") in ("web", "kr"):
            lines.append("   [재료 없음 — 숫자 없이 쓰거나 항목을 줄임]")
        elif s.get("source") == "board":
            lines.append("   [재료 = 아래 「이 칠판」]" if board else "   [이 칠판이 비어 있음 — 일반 지식으로, 숫자 없이]")
    if board:
        lines.append("\n[이 칠판에 있는 자료]\n" + board[:8000])
    lines.append("\n[출처 번호]\n" + ("\n".join(f"[{s['n']}] {s['title']} — {s['url']}" for s in mat["sources"]) or "(없음)"))
    return "\n".join(lines)


def write(client, plan: dict, mat: dict, brief: dict, *, model: str = WRITER_MODEL, board: str = "", day: str = "") -> list:
    """꼭지마다 body → 계획 꼭지에 body를 단 목록(못 쓴 꼭지는 빈 body — 칠판이 머리만 그림)."""
    secs = plan.get("sections") or []
    who = (brief or {}).get("누구에게")
    shapes = sorted({s["shape"] for s in secs if s["shape"] in SCHEMA})
    system = WRITER.format(audience=who if who and who != AUTO else "처음 보는 사람", today=day or today(), schema="\n".join(f"- {sh}: {SCHEMA[sh]}" for sh in shapes))
    r = client.chat.completions.create(model=model, max_tokens=8000, messages=[
        {"role": "system", "content": system}, {"role": "user", "content": material_text(plan, mat, board) + "\n\n꼭지마다 body를 써서 JSON 하나로."}])
    got = (parse_json(r.choices[0].message.content or "") or {}).get("sections") or []
    by_title = {str(s.get("title")): s.get("body") for s in got if isinstance(s, dict)}
    by_order = [s.get("body") if isinstance(s, dict) else None for s in got]
    out = []
    for i, s in enumerate(secs):   # 제목이 조금 바뀌어 와도 차례로 맞춤
        body = by_title.get(s["title"]) or (by_order[i] if i < len(by_order) else None)
        out.append({**s, "body": body if isinstance(body, dict) else {}})
    return out


def build(key: str, client, topic: str, brief: dict, plan: dict, *, base_url: str = gw.BASE_URL, board: str = "", model: str = WRITER_MODEL, exa=None, kr=None) -> dict:
    """계획(사용자가 고친 것) → 재료 → 본문 → {"plan": {title, headline, sources, sections[body]}, "model", "elapsed"}."""
    t0, day = time.time(), today()
    plan = clean_plan(plan)
    mat = gather(key, plan, base_url=base_url, day=day, exa=exa, kr=kr)
    li = next((i for i, s in enumerate(plan["sections"]) if s["shape"] == "움직이는 카드"), None)
    with ThreadPoolExecutor(max_workers=2) as ex:   # 원리 꼭지 카드 = 본문과 동시에(4단계 — 재료는 판 전체)
        fw = ex.submit(write, client, plan, mat, brief, model=model, board=board, day=day)
        fl = ex.submit(_live, client, plan, mat, li, brief) if li is not None else None
        secs, card = fw.result(), fl.result() if fl else None
    if card and card.get("html"):
        secs[li]["body"] = {**(secs[li]["body"] or {}), "html": card["html"], "card_model": card["model"]}
    if mat["sources"]:   # 출처 카드 = 판에서 쓴 번호(기자가 비워도)
        for s in secs:
            if s["shape"] == "출처 카드" and not (s["body"] or {}).get("links"):
                s["body"] = {"links": [x["n"] for x in mat["sources"]]}
    return {"plan": {**plan, "sources": mat["sources"], "sections": secs}, "model": model, "elapsed": round(time.time() - t0, 1),
            "missing": [s["title"] for s, m in zip(plan["sections"], mat["materials"]) if m is not None and not m.get("text")]
            + ([plan["sections"][li]["title"] + "(움직이는 카드: " + card["error"] + ")"] if card and card.get("error") else [])}


def _live(client, plan: dict, mat: dict, idx: int, brief: dict) -> dict:
    """원리 꼭지 하나의 카드 HTML — 못 만들면 {"error"}(판은 그대로 짓고 그 꼭지만 설명 메모)."""
    who = (brief or {}).get("누구에게")
    try:
        return live_card.make(client, "", user=live_card.section_prompt(plan, mat, idx), audience=who if who and who != AUTO else "처음 보는 사람")
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:200]}
