"""웹 칠판 대화·그림의 공공 데이터 도구(2026-10-20, KAIROS 문서 검토) — 기상청 날씨·천문연 달력을 KAIROS MCP 도구 묶음으로(Qt 비의존).

KAIROS `/mcp/{suite}/`(MCP JSON-RPC, 상태 없는 streamable HTTP — `Accept`에 json과 event-stream 둘 다 넣어야 함, 안 넣으면 406).
`tools/list`는 무료, `tools/call` 한 번 = 1건(지금 0크레딧, 키당 하루 200건).
날씨·공휴일 말이 있는 질문만 — 빠른 모델(`TOOL_MODEL`)에 도구 정의를 주고 고르게 한 뒤 실제로 불러, 나온 숫자를 답·그림의 재료로 넘긴다.

⚠ 날씨 도구 셋은 10개 도시(`CITIES`)만 안다 — 모르는 도시(전주 등)는 알리지 않고 서울 날씨를 돌려준다(2026-10-20 실측).
그래서 목록 밖 도시면 부르지 않고, 돌아온 도시가 물은 도시와 다르면 버린다 — 그때는 지금처럼 웹 검색으로.
"""
from __future__ import annotations

import json
import os
import re
import time

from easycad.ai import gateway as gw

SUITES = ("kr-weather", "kr-calendar")
TOOL_MODEL = "gpt-6-luna"   # 도구 고르기만 — 정리정돈과 같은 빠른 모델
CITIES = ("서울", "부산", "인천", "대구", "대전", "광주", "수원", "제주", "춘천", "강릉")
WORDS = re.compile(r"날씨|기온|기상|예보|강수|비\s*(가|와|오|올|소식)|눈\s*(이|와|오|올)|우산|공휴일|휴일|연휴|빨간\s*날|쉬는\s*날|대체\s*공휴|"
                   r"일출|일몰|해\s*(뜨|지)는|해돋이|해넘이|음력|양력|절기|월출|월몰|보름")
SOURCES = {"kr-weather": ("기상청 날씨누리", "https://www.weather.go.kr"),
           "kr-calendar": ("한국천문연구원 천문우주정보", "https://astro.kasi.re.kr")}
TOOL_HEAD = "기상청·천문연 자료로 그렸어요"   # 그림 답 글 머리(웹 검색이면 board_image.FACTS_HEAD) — 이어 고치기가 이 자료를 다시 씀
SYSTEM = """너는 질문에 답하는 데 필요한 한국 공공 데이터 도구만 부른다. 오늘은 {today}.
- 도구가 필요 없으면 아무것도 부르지 않는다.
- 날씨 도구는 이 도시만 정확하다: {cities}. 다른 지역의 날씨면 날씨 도구를 부르지 않는다.
- 날짜는 오늘을 기준으로 계산해 넣는다.
- 「올해·남은·다음」 공휴일은 month 없이 한 해 전체로 받는다(연말이면 다음 해도).
- 일출·일몰은 지역을 말하지 않았으면 서울로."""
_ACCEPT = "application/json, text/event-stream"
_defs: dict = {}   # base_url → (시각, 도구 정의) — tools/list는 무료지만 매번 부를 필요는 없음


def _rpc(api_key: str, base_url: str, suite: str, method: str, params: dict | None = None, http=None) -> dict:
    import httpx
    http = http or httpx
    r = http.post(f"{base_url}/mcp/{suite}/", headers={"Authorization": f"Bearer {api_key}", "Accept": _ACCEPT},
                  json={"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params else {})}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"MCP {suite} {method} HTTP {r.status_code}: {r.text[:160]}")
    t = r.text
    body = json.loads(t.split("data:", 1)[1].strip().split("\n")[0]) if "data:" in t else json.loads(t)   # 답은 SSE 한 건
    if "error" in body:
        raise RuntimeError(f"MCP {suite} {method}: {body['error']}")
    return body.get("result") or {}


def tool_defs(api_key: str, base_url: str = gw.BASE_URL, http=None) -> list:
    """두 묶음의 도구 → OpenAI 함수 도구 정의(이름 = 「묶음__도구」). 하루 한 번만 새로 받는다."""
    hit = _defs.get(base_url)
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    out = []
    for suite in SUITES:
        for t in _rpc(api_key, base_url, suite, "tools/list", http=http).get("tools", []):
            params = {k: v for k, v in (t.get("inputSchema") or {"type": "object"}).items() if k != "$schema"}
            out.append({"type": "function", "function": {"name": f"{suite}__{t['name']}", "description": (t.get("description") or "")[:1000], "parameters": params}})
    _defs[base_url] = (time.time(), out)
    return out


def gather(api_key: str, question: str, *, base_url: str = gw.BASE_URL, client=None, http=None, today: str = "") -> list:
    """질문 → 실제로 부른 도구 결과 [{"suite", "tool", "args", "text"}](없으면 빈 목록). 날씨는 10개 도시일 때만."""
    if not WORDS.search(question or "") or (os.environ.get("EASYCAD_ROUTE") == "rules" and client is None):   # 시험(길 고르기와 같은 스위치) — 가짜 client를 주면 돎
        return []
    if not today:
        t = time.localtime()
        today = "%d년 %d월 %d일(%s)" % (t.tm_year, t.tm_mon, t.tm_mday, "월화수목금토일"[t.tm_wday])
    client = client or gw._client(api_key, base_url, timeout=60)
    resp = client.chat.completions.create(model=TOOL_MODEL, max_tokens=2000, tools=tool_defs(api_key, base_url, http), tool_choice="auto",
                                          messages=[{"role": "system", "content": SYSTEM.format(today=today, cities="·".join(CITIES))},
                                                    {"role": "user", "content": question}])
    calls = getattr(resp.choices[0].message, "tool_calls", None) or []
    out = []
    for c in calls[:4]:
        suite, _, name = (c.function.name or "").partition("__")
        if suite not in SUITES:
            continue
        try:
            args = json.loads(c.function.arguments or "{}")
        except ValueError:
            continue
        if suite == "kr-weather" and str(args.get("city", "서울")) not in CITIES:
            continue   # 모르는 도시 = 서울 날씨가 옴
        res = _rpc(api_key, base_url, suite, "tools/call", {"name": name, "arguments": args}, http=http)
        text = "\n".join(str(b.get("text", "")) for b in res.get("content") or [] if isinstance(b, dict))
        if res.get("isError") or not text.strip():
            continue
        if suite == "kr-weather":
            try:
                if json.loads(text).get("city") not in (None, args.get("city", "서울")):
                    continue
            except ValueError:
                pass
            if name == "get_forecast":   # 모델이 limit를 작게 주면 내일 새벽만 옴(실측 8칸) — 사흘 치 다 받아 날마다 줄임
                full = _rpc(api_key, base_url, suite, "tools/call", {"name": name, "arguments": {**args, "limit": 200}}, http=http)
                text = daily(" ".join(str(b.get("text", "")) for b in full.get("content") or [] if isinstance(b, dict))) or text
        out.append({"suite": suite, "tool": name, "args": args, "text": text[:6000]})
    return out


def daily(text: str) -> str:
    """단기예보(시간별 칸) → 날마다 한 줄 JSON: 최저·최고 기온, 비 올 확률 최대, 오전·오후 하늘, 비·눈 형태."""
    try:
        d = json.loads(text)
    except ValueError:
        return ""
    days: dict = {}
    for sl in d.get("slots") or []:
        days.setdefault(sl.get("date"), []).append(sl)
    rows = []
    for date, sl in days.items():
        temps = [x["tempC"] for x in sl if isinstance(x.get("tempC"), (int, float))]
        def sky(lo, hi):
            v = [x.get("sky") for x in sl if lo <= int(str(x.get("time", "0"))[:2] or 0) < hi and x.get("sky")]
            return max(set(v), key=v.count) if v else ""
        rain = sorted({x.get("precipType") for x in sl if x.get("precipType") not in (None, "", "없음")})
        rows.append({"date": date, "minC": min(temps) if temps else None, "maxC": max(temps) if temps else None,
                     "rainProbMaxPct": max((x.get("precipProbPct") or 0) for x in sl), "skyAM": sky(6, 12), "skyPM": sky(12, 18),
                     "precipType": "·".join(rain) or "없음", "hours": f"{sl[0].get('time')}~{sl[-1].get('time')}"})
    return json.dumps({"city": d.get("city"), "base": d.get("base"), "days": rows}, ensure_ascii=False)


def context_text(found: list) -> str:
    """도구 결과 → 답·그림에 넣을 재료 글. 머리의 [n] = `sources`의 번호(답이 그 번호로 출처를 단다)."""
    num = {s["title"]: s["n"] for s in sources(found)}
    return "\n\n".join(f"[{num[SOURCES[f['suite']][0]]}] {SOURCES[f['suite']][0]} · {f['tool']} {json.dumps(f['args'], ensure_ascii=False)}\n{f['text']}" for f in found)


def sources(found: list) -> list:
    """답 아래 출처 — 묶음마다 하나([1] 기상청 날씨누리 …)."""
    seen = []
    for f in found:
        if f["suite"] not in seen:
            seen.append(f["suite"])
    return [{"n": i + 1, "title": SOURCES[s][0], "url": SOURCES[s][1]} for i, s in enumerate(seen)]
