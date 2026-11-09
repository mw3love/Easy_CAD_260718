"""웹 칠판 재료 찾기(옛 딥모드 §8 항목66에서 남긴 것) — 꼭지마다 웹(Exa)·공공 데이터(KAIROS MCP)로 재료를 모아 출처 번호를 매김.
문서 「찾아 보태기」(`board_report`)·슬라이드(`slides`)·인포그래픽(서버 `_infographic`)이 `gather`를 쓴다. Qt 비의존.
- 공공 데이터는 숫자가 없거나(`has_data`) 꼭지와 다른 것을 재면(`fits`) 웹 검색으로 갈아탐.
⚠ 2026-11-09 문서 통합 3단계: 지면 「한 판」(편집장 계획·기자 본문·꼭지 다시 쓰기·요약 그림)은 뺐다 — 옛 코드는 git에 있음.
"""
from __future__ import annotations
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from . import board_chat, kr_tools
from . import gateway as gw

AUTO = "알아서"


def today() -> str:
    t = time.localtime()
    return "%d년 %d월 %d일" % (t.tm_year, t.tm_mon, t.tm_mday)


def brief_text(brief: dict) -> str:
    """질문지 답 → 지시문 줄(대화창 `deepchat.jsx` `briefOf` 꼴 — 안 고른 것은 「알아서」, 「더」 = 입력 칸 글)."""
    b = brief if isinstance(brief, dict) else {}
    keys = ("누구에게", "무엇에", "깊이", "꼭 넣을 것", "재료")
    extra = [k for k in b if k not in keys and k != "더"]   # 맞춤 질문(2026-11-06 `brief_ask`) = 질문 이름이 그때그때 — 있으면 온 것 그대로(없는 고정 이름은 「알아서」로 채우지 않음)
    if extra:
        keys = tuple(k for k in b if k != "더")
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


FIT_MODEL = kr_tools.TOOL_MODEL   # 공공 재료 검사(빠른 모델 — 한 꼭지 1~2초)
FIT = """너는 통계 재료 검사관이다. 꼭지가 묻는 숫자와 재료 속 표가 **같은 것을 재는지**만 본다(품목·대상·지역·단위).
JSON 하나만: {"ok": true 또는 false, "why": "한 줄"}.
- 품목·대상이 다르면 false(예: 반도체를 물었는데 다른 품목 표, 전국을 물었는데 다른 지역 표).
- 같은 것을 재면 기간이 조금 달라도·질문의 일부만 답해도 true."""


def has_data(found: list) -> bool:
    """공공 도구 결과에 받은 숫자·조문이 있나 — 찾기·구조 보기뿐이거나 데이터 줄이 0개면 False(0단계: 표 구조만 보고 끝남)."""
    for f in found or []:
        if kr_tools._finding(f.get("tool") or ""):
            continue
        try:
            d = json.loads(f.get("text") or "")
        except ValueError:
            return True
        if isinstance(d, dict) and "rows" in d and not d["rows"]:
            continue
        return True
    return False


def fits(client, sec: dict, text: str, model: str = FIT_MODEL) -> tuple:
    """공공 재료가 꼭지 질문과 같은 것을 재나 → (ok, 까닭). 검사가 틀어지면 (True, "") — 재료를 막지 않음."""
    try:
        r = client.chat.completions.create(model=model, max_tokens=300, messages=[{"role": "system", "content": FIT}, {"role": "user", "content":
            f"[꼭지] {sec.get('title')}\n[독자의 질문] {sec.get('question') or ''}\n[찾은 문장] {sec.get('query') or ''}\n\n[재료]\n{text[:6000]}"}])
        d = parse_json(r.choices[0].message.content or "") or {}
        return (d.get("ok") is not False, str(d.get("why") or "")[:200])
    except Exception:
        return True, ""


def gather(key: str, plan: dict, *, base_url: str = gw.BASE_URL, day: str = "", exa=None, kr=None, known=None, fit=None) -> dict:
    """꼭지마다 재료 글 + 판 전체 출처 목록 {"sources": [{n, title, url}], "materials": [{"text"(, "switched")} | None]}.
    재료 글 속 [k](도구마다 따로 매긴 번호)는 판 번호 [n]으로 바꿈. exa·kr·fit = 시험용 바꿔 끼우기.
    공공 데이터는 숫자가 없거나(`has_data`) 꼭지와 다른 것을 재면(`fits` — 0단계 「반도체」에 다른 품목 표) 웹 검색으로 갈아탐(switched = 까닭).
    known = 판에 이미 있는 출처(꼭지 다시 쓰기 — 같은 주소는 같은 번호, 새 출처는 그 뒤 번호)."""
    exa = exa or (lambda q: board_chat.exa_answer(key, q, board_chat.SEARCH_SYSTEM, base_url=base_url))
    kr = kr or (lambda q: kr_tools.gather(key, q, base_url=base_url, today=day or today()))
    fit = fit or (lambda sec, text: fits(gw._client(key, base_url, timeout=60), sec, text))

    def web(q):
        ans, raw = exa(q[:4000])
        return {"text": ans, "sources": [{"title": x.get("title") or x["url"], "url": x["url"]} for x in raw.get("search_results") or []]}

    def one(sec):
        src, q = sec.get("source"), (sec.get("query") or sec.get("title") or "")
        try:
            if src == "kr":
                found = kr(q)
                why = "" if found else "공공 데이터에서 못 찾음"
                if found and not has_data(found):
                    why = "공공 데이터가 표만 찾고 숫자를 못 받음"
                elif found:
                    text = kr_tools.context_text(found)
                    ok, w = fit(sec, text)
                    if ok:
                        return {"text": text, "sources": [{"title": s["title"], "url": s["url"]} for s in kr_tools.sources(found)]}
                    why = "공공 데이터 표가 꼭지와 다름" + (f" — {w}" if w else "")
                return {**web(q), "switched": why}   # 웹 검색으로(0단계: 셋 중 하나만 맞았음)
            if src == "web":
                return web(q)
        except Exception as e:   # 한 꼭지가 틀어져도 나머지는 — 기자에게 「재료 없음」으로
            return {"text": "", "sources": [], "error": f"{type(e).__name__}: {e}"[:200]}
        return None

    secs = plan.get("sections") or []
    with ThreadPoolExecutor(max_workers=max(1, len(secs))) as ex:
        got = list(ex.map(one, secs))
    allsrc, mats = [dict(x) for x in known or []], []
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
        mats.append({"text": text, **({"error": g["error"]} if g.get("error") else {}), **({"switched": g["switched"]} if g.get("switched") else {})})
    return {"sources": allsrc, "materials": mats}
