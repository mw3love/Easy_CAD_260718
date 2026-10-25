"""딥모드(§8 항목66) 0단계 실측 — 편집장 계획·재료 모으기의 시간·크레딧(앱 코드는 안 고침).

주제 셋(논문·송신 장비·시사)마다:
  1. 편집장: 질문 + 질문지 답(시안 ①의 기본값) → 꼭지 5~9개 계획 JSON — 모델 둘(claude-opus-5-5 · 비교 gpt-6.1-sol)
  2. 재료: 첫 모델 계획의 꼭지마다 기존 길을 동시에 — 웹 검색 `board_chat.exa_answer`, 공공 데이터 `kr_tools.gather`, 그림은 견적만(`/estimate/`)
  3. 잴 것: 단계별 시간·크레딧(이 계정은 응답에 `billing`이 안 옴 — 2026-10-25 확인, 그래서 `/credits/` 잔액 차이 + 토큰 × 단가),
     계획 품질(꼭지 수·모양·숫자 꼭지의 출처, 계획 안에 지어낸 숫자), 재료의 숫자 문장에 [n] 출처가 붙었나

사용:
    python tools/deepmode_probe.py                  # 주제 셋 다
    python tools/deepmode_probe.py --topics paper   # 하나만(paper·tx·news)
    python tools/deepmode_probe.py --out <폴더>      # 원본 결과 JSON 저장 자리(기본 tools/_deepmode_probe/)

키는 `easycad-gateway.key`(`gateway.resolve_api_key`). 잔액 차이는 같은 계정을 동시에 쓰는 다른 일(5191 서버 등)이 있으면 섞인다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from easycad.ai import gateway as gw          # noqa: E402
from easycad.ai import board_chat, kr_tools   # noqa: E402

MODELS = ("claude-opus-5-5", "gpt-6.1-sol")
IMAGE_MODEL = "gpt-image-2.5-flare"
TODAY = time.strftime("%Y년 %m월 %d일")

# 시안 ①(질문지)의 기본값 — 처음 보는 사람 · 공부·교육 · 알아서(분량 보고) · 숫자·그래프, 원리 단계, 직접 눌러 보기 · 둘 다
ANSWERS = {"누구에게": "처음 보는 사람", "무엇에": "공부·교육", "깊이": "알아서 (분량 보고)",
           "꼭 넣을 것": ["숫자·그래프", "원리 단계", "직접 눌러 보기"], "재료": "둘 다(웹 검색 + 이 칠판 — 이번 칠판은 비어 있음)"}

TOPICS = {
    "paper": "어텐션이 뭐야? 신입 교육용으로 칠판에 정리해 줘",
    "tx": "ATSC 3.0 송신기가 어떻게 동작하는지 송신소 신입에게 칠판 한 판으로 알려 줘",
    "news": "요즘 한국 반도체 수출 동향을 칠판 한 판으로 정리해 줘",
}

SHAPES = ("헤드라인", "주인공 글", "숫자 타일", "단계 카드", "그래프", "표", "움직이는 카드", "용어 풀이", "접힌 메모", "확인 문제", "그림", "아이콘", "출처 카드")
SOURCES = ("ai", "web", "kr", "image", "board")
CHARTS = ("세로 막대", "가로 막대", "꺾은선", "원", "표")

EDITOR = """너는 「웹 칠판」의 편집장이다. 사용자의 질문 하나로 칠판 한 판을 신문 지면처럼 채울 **지면 계획**만 세운다(본문은 아직 쓰지 않는다).
목표: 처음 보는 사람이 한 판을 보고 빠르게 이해한다. 꾸미려고 넣는 꼭지는 없다.
오늘은 {today}.

출력은 JSON 하나뿐(설명·코드펜스 없이):
{{"title": "지면 제목", "headline": "큰 제목 한 줄", "pages": 1 또는 2(분량 판단 — 꼭지가 많고 깊으면 2),
  "sections": [{{"title": "꼭지 제목", "question": "이 꼭지가 답하는 독자의 질문", "shape": 모양, "chart": 그래프 종류 또는 null,
                 "source": 재료 출처, "query": 검색·조회 문장 또는 null, "size": "주인공" | "보통" | "작게"}}]}}

- sections는 5~9개, 읽는 순서대로. "주인공"은 하나만.
- shape는 다음 중 하나: {shapes}. 꼭지마다 모양 하나 — 숫자 비교 = 그래프, 순서 = 단계 카드, 원리 = 움직이는 카드(한 판에 하나까지), 핵심 숫자 몇 개 = 숫자 타일.
- chart는 shape가 그래프일 때만: {charts}. 자료에 맞는 종류(비교 = 막대, 시간 흐름 = 꺾은선, 전체 중 몫 = 원).
- source는 다음 중 하나: ai(일반 지식으로 AI가 씀 — 설명·용어·문제), web(웹 검색), kr(한국 공공 데이터 — 통계청·한국은행·법령·날씨),
  image(그림 생성 — 한 판에 하나까지, 사진이 아니면 이해가 안 될 때만), board(이 칠판에 있는 자료).
- **숫자·날짜·최신 사실이 들어가는 꼭지는 source가 web 또는 kr**(ai 금지). query는 앞 대화 없이 혼자 통하는 한국어 검색 문장(최신이면 연도·달 포함).
  kr이면 query에 「통계」「법령」 같은 낱말을 넣는다. image면 query = 그림 설명.
- 계획에는 숫자·사실을 쓰지 않는다(제목은 「기억할 숫자 3개」처럼). 숫자는 재료에서 온다."""


def user_prompt(question: str) -> str:
    a = ANSWERS
    return (f"[사용자 질문]\n{question}\n\n[질문지 답]\n- 누구에게: {a['누구에게']}\n- 무엇에: {a['무엇에']}\n- 깊이: {a['깊이']}\n"
            f"- 꼭 넣을 것: {', '.join(a['꼭 넣을 것'])}\n- 재료: {a['재료']}\n\n지면 계획 JSON을 써 줘.")


class Rec:
    """httpx 흉내 — 부른 주소·시간·X-Billing 머리말을 적어 둠(MCP는 머리말에 `billing`이 온다고 문서에 있음)."""

    def __init__(self):
        import httpx
        self._h, self.calls = httpx, []

    def post(self, url, **kw):
        t0 = time.time()
        r = self._h.post(url, **kw)
        b = r.headers.get("X-Billing")
        self.calls.append({"url": url.split("/gateway", 1)[-1], "sec": round(time.time() - t0, 2), "status": r.status_code, "x_billing": b})
        return r


class ClientRec:
    """openai 클라이언트 감싸기 — 대화 호출마다 모델·토큰·시간을 적어 둠(kr_tools의 gpt-6-luna 주고받기)."""

    def __init__(self, client):
        self._c, self.calls = client, []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        t0 = time.time()
        r = self._c.chat.completions.create(**kw)
        u = r.usage
        self.calls.append({"model": kw.get("model"), "sec": round(time.time() - t0, 2),
                           "in": getattr(u, "prompt_tokens", 0), "out": getattr(u, "completion_tokens", 0)})
        return r


def balance(key: str) -> float:
    return gw.get_credit_balance(key)[0]


def price_of(key: str) -> dict:
    return {m["id"]: m for m in gw.list_text_models_info(key)}


def usd(prices: dict, model: str, tin: int, tout: int) -> float:
    p = prices.get(model) or {}
    return ((p.get("input") or 0) * tin + (p.get("output") or 0) * tout) / 1e6


def parse_plan(text: str):
    t = gw.strip_code_fence(text or "")
    i, j = t.find("{"), t.rfind("}")
    try:
        return json.loads(t[i:j + 1]) if i >= 0 else None
    except ValueError:
        return None


_NUM = re.compile(r"\d")


def check_plan(plan) -> dict:
    """계획 품질 — 꼭지 수, 모르는 모양·출처, 숫자 꼭지가 ai 출처인지, 계획 글 안의 숫자(지어낸 숫자 후보)."""
    if not isinstance(plan, dict):
        return {"ok": False, "why": "JSON 아님"}
    secs = plan.get("sections") or []
    bad_shape = [s.get("shape") for s in secs if s.get("shape") not in SHAPES]
    bad_src = [s.get("source") for s in secs if s.get("source") not in SOURCES]
    numeric_ai = [s.get("title") for s in secs if s.get("shape") in ("숫자 타일", "그래프", "표") and s.get("source") == "ai"]
    heroes = sum(1 for s in secs if s.get("size") == "주인공")
    texts = [plan.get("title") or "", plan.get("headline") or ""] + [f"{s.get('title', '')} {s.get('question', '')}" for s in secs]
    nums = sorted({m for t in texts for m in re.findall(r"[^\s]*\d[^\s]*", t)})
    return {"ok": True, "n": len(secs), "pages": plan.get("pages"), "bad_shape": bad_shape, "bad_src": bad_src,
            "numeric_ai": numeric_ai, "heroes": heroes, "nums_in_plan": nums,
            "by_src": {k: sum(1 for s in secs if s.get("source") == k) for k in SOURCES}}


def run_plan(key: str, model: str, question: str, prices: dict) -> dict:
    client = gw._client(key, gw.BASE_URL, timeout=300)
    b0, t0 = balance(key), time.time()
    r = client.chat.completions.create(model=model, max_tokens=6000, messages=[
        {"role": "system", "content": EDITOR.format(today=TODAY, shapes="·".join(SHAPES), charts="·".join(CHARTS))},
        {"role": "user", "content": user_prompt(question)}])
    sec = time.time() - t0
    time.sleep(2)   # 잔액이 늦게 줄 수도 있어 잠깐
    b1 = balance(key)
    u = r.usage
    text = r.choices[0].message.content or ""
    plan = parse_plan(text)
    return {"model": model, "sec": round(sec, 1), "credits": round(b0 - b1, 2), "in": u.prompt_tokens, "out": u.completion_tokens,
            "usd": round(usd(prices, model, u.prompt_tokens, u.completion_tokens), 4), "plan": plan, "raw": None if plan else text,
            "check": check_plan(plan)}


def _number_claims(answer: str) -> dict:
    """숫자가 든 문장 중 [n] 출처가 붙은 몫."""
    sents = [s for s in re.split(r"(?<=[.!?])\s+|\n+", answer or "") if _NUM.search(re.sub(r"\[\d+\]", "", s))]
    cited = [s for s in sents if re.search(r"\[\d+\]", s)]
    return {"num_sents": len(sents), "cited": len(cited), "uncited": [s.strip()[:120] for s in sents if s not in cited][:5]}


def gather_one(key: str, sec: dict, prices: dict) -> dict:
    src, q = sec.get("source"), (sec.get("query") or sec.get("title") or "")
    out = {"title": sec.get("title"), "source": src, "query": q}
    t0 = time.time()
    try:
        if src == "web":
            rec = Rec()
            ans, raw = board_chat.exa_answer(key, q[:4000], board_chat.SEARCH_SYSTEM, http=rec)
            out.update(answer=ans, sources=len(raw["citations"]), http=rec.calls, quality=_number_claims(ans))
        elif src == "kr":
            rec, crec = Rec(), ClientRec(gw._client(key, gw.BASE_URL, timeout=60))
            found = kr_tools.gather(key, q, client=crec, http=rec, today=TODAY)
            usd_ = sum(usd(prices, c["model"], c["in"], c["out"]) for c in crec.calls)
            out.update(found=[{"suite": f["suite"], "tool": f["tool"], "args": f["args"], "text": f["text"][:600]} for f in found],
                       suites=kr_tools.pick_suites(q), tool_calls=len([c for c in rec.calls if "/mcp/" in c["url"]]),
                       llm=crec.calls, usd=round(usd_, 4), http=rec.calls)
        elif src == "image":
            import httpx
            r = httpx.post(gw.BASE_URL + "/estimate/", headers={"Authorization": f"Bearer {key}"},
                           json={"kind": "image", "model": IMAGE_MODEL, "number_of_images": 2, "aspect_ratio": "4:3"}, timeout=30)
            out.update(estimate=r.json() if r.status_code < 400 else r.text[:200])
        else:
            out.update(skipped="ai·board 꼭지는 재료 단계에서 부를 것 없음(본문 쓰기 단계 몫)")
    except Exception as e:   # 한 꼭지가 틀어져도 나머지는 — 실패도 결과
        out.update(error=f"{type(e).__name__}: {e}"[:300])
    out["sec"] = round(time.time() - t0, 1)
    return out


def run_materials(key: str, plan: dict, prices: dict) -> dict:
    secs = [s for s in (plan or {}).get("sections") or []]
    b0, t0 = balance(key), time.time()
    with ThreadPoolExecutor(max_workers=max(1, len(secs))) as ex:
        items = list(ex.map(lambda s: gather_one(key, s, prices), secs))
    sec = time.time() - t0
    time.sleep(2)
    b1 = balance(key)
    return {"sec": round(sec, 1), "credits": round(b0 - b1, 2), "items": items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", default="paper,tx,news")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "_deepmode_probe"))
    a = ap.parse_args()
    key = gw.resolve_api_key()
    if not key:
        sys.exit("키 없음 — ~/.claude/.secrets/easycad-gateway.key")
    os.makedirs(a.out, exist_ok=True)
    prices = price_of(key)
    start = balance(key)
    print(f"시작 잔액 {start:.2f}")
    for name in a.topics.split(","):
        q = TOPICS[name]
        res = {"topic": name, "question": q, "answers": ANSWERS, "plans": []}
        for m in MODELS:
            p = run_plan(key, m, q, prices)
            res["plans"].append(p)
            c = p["check"]
            print(f"[{name}] 계획 {m}: {p['sec']}초 · {p['credits']}cr · ${p['usd']} · 꼭지 {c.get('n')} · 출처 {c.get('by_src')} · "
                  f"숫자꼭지 ai {c.get('numeric_ai')} · 계획 속 숫자 {c.get('nums_in_plan')}")
        base = next((p["plan"] for p in res["plans"] if p["plan"]), None)
        res["materials"] = run_materials(key, base, prices) if base else None
        mt = res["materials"] or {}
        print(f"[{name}] 재료(첫 계획 기준): {mt.get('sec')}초 · {mt.get('credits')}cr")
        for it in mt.get("items", []):
            extra = it.get("quality") or ({"suites": it.get("suites"), "tool_calls": it.get("tool_calls"), "found": len(it.get("found", []))} if it["source"] == "kr" else "")
            if it["source"] == "image":
                extra = (it.get("estimate") or {}).get("credits") if isinstance(it.get("estimate"), dict) else it.get("estimate")
            print(f"    - {it['source']:5} {it['sec']:5}초 {it['title']} {it.get('error') or ''} {extra}")
        with open(os.path.join(a.out, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"끝 잔액 {balance(key):.2f} (전체 {start - balance(key):.2f}cr)")


if __name__ == "__main__":
    main()
