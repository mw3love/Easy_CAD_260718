"""웹 칠판 대화·그림의 공공 데이터 도구(2026-10-20, KAIROS 문서 검토) — KAIROS MCP 도구 묶음(Qt 비의존).

KAIROS `/mcp/{suite}/`(MCP JSON-RPC, 상태 없는 streamable HTTP — `Accept`에 json과 event-stream 둘 다 넣어야 함, 안 넣으면 406).
`tools/list`는 무료, `tools/call` 한 번 = 1건(지금 0크레딧, 키당 하루 200건). 우리 키로 쓸 수 있는 묶음은 34개(`GET /mcp/`, 2026-10-20) —
날씨·달력에 더해 법령·통계·특보·대기질·국어 규범을 쓴다(같은 날 사용자 선택 「공공 데이터 도구 확대」).
질문 낱말(`SUITE_WORDS`)에 맞는 묶음의 도구만 빠른 모델(`TOOL_MODEL`)에 주고, 최대 `MAX_ROUNDS`번 주고받으며 부르게 한다
(법령은 찾기 → 조문, 통계는 표 찾기 → 구조 → 숫자처럼 여러 번 이어 불러야 함). 나온 결과를 답·그림의 재료로 넘긴다.

⚠ 날씨 도구 셋은 10개 도시(`CITIES`)만 안다 — 모르는 도시(전주 등)는 알리지 않고 서울 날씨를 돌려준다(2026-10-20 실측).
그래서 목록 밖 도시면 부르지 않고, 돌아온 도시가 물은 도시와 다르면 버린다 — 그때는 지금처럼 웹 검색으로.
⚠ 도구 고르는 모델이 「전주 날씨」를 서울로 바꿔 부를 때가 있다(2026-10-25 실측, 두 번 중 한 번) — 그래서 날씨는 질문 글에
목록 도시 이름이 있을 때만 쓴다(도시 없는 「내일 날씨」도 서울로 정하지 않고 웹 검색으로 — 사용자는 전주).
"""
from __future__ import annotations

import json
import os
import re
import time

from easycad.ai import gateway as gw

TOOL_MODEL = "gpt-6-luna"   # 도구 고르기만 — 정리정돈과 같은 빠른 모델
MAX_ROUNDS = 6              # 도구 주고받기 횟수(법령 찾기 → 조문, 통계 찾기 → 구조 → 숫자 — 4번이면 통계가 표만 찾다 끝남, 2026-10-20 실측)
MAX_CALLS = 8               # 한 질문에 부르는 도구 수 상한(키당 하루 200건)
CITIES = ("서울", "부산", "인천", "대구", "대전", "광주", "수원", "제주", "춘천", "강릉")
# 묶음마다 부르는 낱말 — 낱말이 없으면 도구 정의도 안 보냄(관계없는 질문은 느려지지 않게)
SUITE_WORDS = {
    "kr-weather": r"날씨|기온|기상|예보|강수|비\s*(가|와|오|올|소식)|눈\s*(이|와|오|올)|우산",
    "kr-calendar": r"공휴일|휴일|연휴|빨간\s*날|쉬는\s*날|대체\s*공휴|일출|일몰|해\s*(뜨|지)는|해돋이|해넘이|음력|양력|절기|월출|월몰|보름",
    "korean-law": r"법령|법률|법적|법상|조문|조항|제\s*\d+\s*조|시행령|시행규칙|판례|판결|대법원|헌법|헌재|조례|훈령|예규|과태료|처벌|위반|불법|합법|"
                  r"규정상|해석례|질의회신|(근로기준|개인정보\s*보호|저작권|방송|전파|전기통신사업|정보통신망|산업안전보건|중대재해\s*처벌|노동조합|민|형|상)법",
    "kr-macro": r"통계|인구|출산율|고용률|실업률|물가|GDP|성장률|금리|가구\s*수|세대\s*수|KOSIS|코시스|한국은행|고령화|경제\s*지표",
    "kr-safety": r"특보|경보|주의보|태풍|호우|대설|폭염|한파|강풍|지진|쓰나미|재난",
    "airkorea": r"미세\s*먼지|초미세|대기\s*질|공기\s*질|황사|오존|PM\s*2\.?5|PM\s*10",
    "kr-language": r"표준어|맞춤법|띄어쓰기|외래어|표기법|로마자|표기\s*(가|는|이)?\s*맞|어느\s*(게|것이)\s*맞|뜻이\s*뭐|국어사전|['‘\"“][^'’\"”]{1,20}['’\"”]\s*(가|이)\s*맞",
}
SUITES = tuple(SUITE_WORDS)
WORDS = re.compile("|".join(f"(?:{w})" for w in SUITE_WORDS.values()), re.I)   # 서버가 먼저 보는 낱말(하나라도 있으면 `gather`)
SOURCES = {"kr-weather": ("기상청 날씨누리", "https://www.weather.go.kr"),
           "kr-calendar": ("한국천문연구원 천문우주정보", "https://astro.kasi.re.kr"),
           "korean-law": ("국가법령정보센터", "https://www.law.go.kr"),
           "kr-macro": ("통계청 KOSIS", "https://kosis.kr"),
           "kr-safety": ("기상청 날씨누리", "https://www.weather.go.kr"),
           "airkorea": ("에어코리아", "https://www.airkorea.or.kr"),
           "kr-language": ("국립국어원", "https://korean.go.kr")}
_TOOL_SOURCES = {"search_bok_statistics": ("한국은행 ECOS", "https://ecos.bok.or.kr"), "get_bok_statistic": ("한국은행 ECOS", "https://ecos.bok.or.kr"),
                 "get_bok_key_indicators": ("한국은행 ECOS", "https://ecos.bok.or.kr"), "get_global_disaster": ("미국 지질조사국 USGS", "https://earthquake.usgs.gov")}
TOOL_HEAD = "공공 데이터로 그렸어요"   # 그림 답 글 머리(웹 검색이면 board_image.FACTS_HEAD) — 이어 고치기가 이 자료를 다시 씀
SYSTEM = """너는 질문에 답하는 데 필요한 한국 공공 데이터 도구만 부른다. 오늘은 {today}.
- 도구가 필요 없으면 아무것도 부르지 않는다. 필요한 자료를 다 받았으면 도구를 더 부르지 말고 「끝」이라고만 답한다.
- 날씨 도구는 이 도시만 정확하다: {cities}. 다른 지역의 날씨면 날씨 도구를 부르지 않는다.
- 날짜는 오늘을 기준으로 계산해 넣는다.
- 「올해·남은·다음」 공휴일은 month 없이 한 해 전체로 받는다(연말이면 다음 해도).
- 일출·일몰은 지역을 말하지 않았으면 서울로.
- 법령: search_law로 찾고 get_law에는 물은 조문(article)만. 실무 해석은 search_interpretation, 다툼은 search_precedent.
- 통계: search_statistics로 표를 찾고 get_statistics_meta로 항목·분류를 본 뒤 get_statistics_data는 필요한 칸만 최근 몇 해(recentN 5 안팎).
  objL에 "ALL"을 쓰지 말고 물은 지역 코드를 넣는다(분류 목록이 잘려 안 보여도) — 전국 00 서울 11 부산 21 대구 22 인천 23 광주 24 대전 25 울산 26 세종 29
  경기 41 충북 43 충남 44 전남 46 경북 47 경남 48 제주 50 강원 51 전북 52.
  「몇 년 추이」는 연(Y) 주기로 그 햇수만큼. 금리·환율·물가 같은 경제 지표는 get_bok_key_indicators 먼저,
  「요즘·지금」 한 값은 월(M) 주기로 최근 몇 달 범위를(일(D)·한 날만 물으면 빈 답이 옴).
- 대기질: 동네를 말하면 get_air_quality_by_station, 시도 전체(「서울 미세먼지」)면 get_air_forecast로 예보 등급을 함께.
- 결과는 작게 받는다(limit·page_size 5 안팎)."""
_ACCEPT = "application/json, text/event-stream"
_defs: dict = {}   # (base_url, 묶음) → (시각, 도구 정의) — tools/list는 무료지만 매번 부를 필요는 없음


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


def pick_suites(question: str) -> list:
    """질문 낱말에 맞는 묶음들(없으면 빈 목록)."""
    return [s for s, w in SUITE_WORDS.items() if re.search(w, question or "", re.I)]


def tool_defs(api_key: str, base_url: str = gw.BASE_URL, http=None, suites=SUITES) -> list:
    """고른 묶음의 도구 → OpenAI 함수 도구 정의(이름 = 「묶음__도구」). 묶음마다 하루 한 번만 새로 받는다."""
    out = []
    for suite in suites:
        hit = _defs.get((base_url, suite))
        if not hit or time.time() - hit[0] >= 86400:
            defs = []
            for t in _rpc(api_key, base_url, suite, "tools/list", http=http).get("tools", []):
                params = {k: v for k, v in (t.get("inputSchema") or {"type": "object"}).items() if k != "$schema"}
                defs.append({"type": "function", "function": {"name": f"{suite}__{t['name']}", "description": (t.get("description") or "")[:1000], "parameters": params}})
            hit = _defs[(base_url, suite)] = (time.time(), defs)
        out += hit[1]
    return out


def _call(api_key: str, base_url: str, suite: str, name: str, args: dict, http=None) -> str:
    """도구 하나 부르기 → 결과 글(못 쓰면 빈 글). 날씨는 모르는 도시·서울로 떨어진 답을 버리고, 예보는 사흘 치를 날마다 줄인다."""
    if suite == "kr-weather" and str(args.get("city", "서울")) not in CITIES:
        return ""   # 모르는 도시 = 서울 날씨가 옴
    res = _rpc(api_key, base_url, suite, "tools/call", {"name": name, "arguments": args}, http=http)
    if res.get("isError"):   # 공공 API가 가끔 시간 초과(「This operation was aborted」 — 에어코리아 3번 중 1번, 2026-10-21 실측) — 한 번만 다시
        res = _rpc(api_key, base_url, suite, "tools/call", {"name": name, "arguments": args}, http=http)
    text = "\n".join(str(b.get("text", "")) for b in res.get("content") or [] if isinstance(b, dict))
    if res.get("isError") or not text.strip():
        return ""
    if suite == "kr-weather":
        try:
            if json.loads(text).get("city") not in (None, args.get("city", "서울")):
                return ""
        except ValueError:
            pass
        if name == "get_forecast":   # 모델이 limit를 작게 주면 내일 새벽만 옴(실측 8칸) — 사흘 치 다 받아 날마다 줄임
            full = _rpc(api_key, base_url, suite, "tools/call", {"name": name, "arguments": {**args, "limit": 200}}, http=http)
            text = daily(" ".join(str(b.get("text", "")) for b in full.get("content") or [] if isinstance(b, dict))) or text
    try:   # 도구는 들여쓴 JSON을 줌 — 빽빽하게(같은 6000자에 2~3배 담김)
        text = json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))
    except ValueError:
        pass
    return text


def _finding(tool: str) -> bool:
    """찾기·구조 보기 도구(그것만으론 답할 숫자·조문이 없음)."""
    return tool.startswith(("search_", "browse_")) or tool in ("get_statistics_meta",)


def gather(api_key: str, question: str, *, base_url: str = gw.BASE_URL, client=None, http=None, today: str = "") -> list:
    """질문 → 실제로 부른 도구 결과 [{"suite", "tool", "args", "text"}](없으면 빈 목록).
    모델이 도구를 부르면 결과를 돌려주고 다시 묻기를 `MAX_ROUNDS`번까지(찾기 → 받기). 날씨는 10개 도시일 때만."""
    suites = pick_suites(question)
    if "kr-weather" in suites and not any(c in question for c in CITIES):   # 도시 없음·목록 밖 도시 = 날씨 도구 안 씀(웹 검색으로)
        suites.remove("kr-weather")
    if not suites or (os.environ.get("EASYCAD_ROUTE") == "rules" and client is None):   # 시험(길 고르기와 같은 스위치) — 가짜 client를 주면 돎
        return []
    if not today:
        t = time.localtime()
        today = "%d년 %d월 %d일(%s)" % (t.tm_year, t.tm_mon, t.tm_mday, "월화수목금토일"[t.tm_wday])
    client = client or gw._client(api_key, base_url, timeout=60)
    tools = tool_defs(api_key, base_url, http, suites)
    messages = [{"role": "system", "content": SYSTEM.format(today=today, cities="·".join(CITIES))}, {"role": "user", "content": question}]
    out, n, nudged = [], 0, False
    for _ in range(MAX_ROUNDS):
        msg = client.chat.completions.create(model=TOOL_MODEL, max_tokens=2000, tools=tools, tool_choice="auto", messages=messages).choices[0].message
        calls = [c for c in (getattr(msg, "tool_calls", None) or []) if (c.function.name or "").partition("__")[0] in suites][:MAX_CALLS - n]
        if not calls:
            # 찾기·구조만 받고 멈추면 한 번 재촉 — 통계표만 찾고 숫자 없이 끝나는 일이 있었음(같은 질문 셋 중 하나, 2026-10-21 실측)
            if out and not nudged and n < MAX_CALLS and all(_finding(f["tool"]) for f in out):
                nudged = True
                messages += [{"role": "assistant", "content": getattr(msg, "content", None) or "끝"},
                             {"role": "user", "content": "아직 찾기 결과뿐이야. 위에서 찾은 표·법령으로 실제 숫자나 조문을 받는 도구(get_statistics_data·get_law 등)를 불러."}]
                continue
            break
        ids = [getattr(c, "id", None) or f"c{n + i}" for i, c in enumerate(calls)]
        messages.append({"role": "assistant", "content": getattr(msg, "content", None) or "",
                         "tool_calls": [{"id": ids[i], "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                                        for i, c in enumerate(calls)]})
        for i, c in enumerate(calls):
            suite, _, name = c.function.name.partition("__")
            try:
                args = json.loads(c.function.arguments or "{}")
                # 질문에 없는 도시로 부른 날씨 = 버림(「전주와 서울」의 서울은 씀)
                text = "" if suite == "kr-weather" and str(args.get("city", "서울")) not in question else _call(api_key, base_url, suite, name, args, http)
            except (ValueError, RuntimeError) as e:   # 도구 하나가 틀어져도 나머지는 — 모델에겐 실패를 알려 다른 길로
                messages.append({"role": "tool", "tool_call_id": ids[i], "content": f"실패: {e}"[:300]})
                continue
            messages.append({"role": "tool", "tool_call_id": ids[i], "content": (text or "결과 없음")[:6000]})
            if text:
                out.append({"suite": suite, "tool": name, "args": args, "text": text[:6000]})
        n += len(calls)
        if n >= MAX_CALLS:
            break
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


def source_of(f: dict) -> tuple:
    """도구 결과 하나의 출처 (이름, 주소) — 묶음 기준, 한국은행·USGS 도구는 따로."""
    return _TOOL_SOURCES.get(f["tool"]) or SOURCES[f["suite"]]


def context_text(found: list) -> str:
    """도구 결과 → 답·그림에 넣을 재료 글. 머리의 [n] = `sources`의 번호(답이 그 번호로 출처를 단다).
    받은 숫자·조문이 앞, 찾기 결과(search_·browse_)는 뒤 — 답 재료는 12000자에서 잘리니 찾기 목록에 밀려 숫자가 빠지지 않게."""
    num = {s["title"]: s["n"] for s in sources(found)}
    found = sorted(found, key=lambda f: _finding(f["tool"]))
    return "\n\n".join(f"[{num[source_of(f)[0]]}] {source_of(f)[0]} · {f['tool']} {json.dumps(f['args'], ensure_ascii=False)}\n{f['text']}" for f in found)


def sources(found: list) -> list:
    """답 아래 출처 — 기관마다 하나([1] 기상청 날씨누리 …)."""
    seen = []
    for f in found:
        if source_of(f) not in seen:
            seen.append(source_of(f))
    return [{"n": i + 1, "title": t, "url": u} for i, (t, u) in enumerate(seen)]
