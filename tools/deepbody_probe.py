"""딥모드(§8 항목66) 3-0 실측 — 꼭지 본문 쓰기의 시간·크레딧·품질(앱 코드는 안 고침).

0단계(`deepmode_probe.py`)는 계획·재료까지만 쟀다. 여기서는 그 계획(opus, `tools/_deepmode_probe/<주제>.json`)을 그대로 쓰고:
  1. 재료를 출처 주소까지 다시 모음(0단계 저장본엔 주소가 없음) — 웹 = Exa, 공공 = kr_tools. 출처 번호는 판 전체에서 하나로([n])
  2. 본문 쓰기 세 방식: A opus 한 번에 · B sonnet 한 번에 · C sonnet 꼭지마다 동시
  3. 잴 것: 시간·크레딧(잔액 차이)·토큰·$, 모양별 칸이 맞나, 숫자 꼭지의 숫자에 [n]이 붙었나·없는 번호를 썼나, ai 꼭지에 숫자가 섞였나
결과는 칠판 고정 계획과 같은 꼴(`web/test/fixtures/deep_*.json`) — `tools/_deepbody_probe/<주제>_<방식>.json`을 `ed.deepBoard`로 바로 지어 볼 수 있다.

사용:
    python tools/deepbody_probe.py                       # 주제 셋 · 방식 셋
    python tools/deepbody_probe.py --topics paper --modes A
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from easycad.ai import gateway as gw          # noqa: E402
from easycad.ai import board_chat, kr_tools   # noqa: E402
from deepmode_probe import ClientRec, balance, parse_plan, price_of, usd, TODAY   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODES = {"A": ("claude-opus-5-5", "one"), "B": ("claude-sonnet-5-5", "one"), "C": ("claude-sonnet-5-5", "each")}

# 칠판 물건이 읽는 칸(web/src/next/deepboard.js `deepSection`) — 이 꼴로만 받는다
SCHEMA = {
    "주인공 글": '{"text": ["문단", "문단"]} — 2~3문단, 핵심은 **굵게**',
    "용어 풀이": '{"terms": [["낱말", "풀이 한 줄"], …]} — 3~5개',
    "단계 카드": '{"steps": [["단계 이름(짧게)", "한 줄 설명"], …]} — 3~6단계',
    "움직이는 카드": '{"note": "무엇을 움직이면 무엇이 보이는지 한 줄"}',
    "그래프": '{"rows": [["항목 이름", "계열 이름(단위)"], ["항목", "숫자 [n]"], …], "header": true, "kind": "line"|"col"|"row"|"pie", "caption": "한 줄"} — 칸 숫자마다 [n]',
    "표": '{"rows": [["", "열 이름", …], ["행 이름", "칸", …], …], "header": true} — 숫자 칸엔 [n]',
    "숫자 타일": '{"tiles": [["값+단위", "한 줄 설명", n], …]} — 2~4개, n = 출처 번호(숫자)',
    "확인 문제": '{"items": ["…을 말할 수 있다", …]} — 3개',
    "출처 카드": '{"links": [n, …]} — 판에서 쓴 출처 번호',
    "접힌 메모": '{"md": "- 줄\\n- 줄"} — 5~8줄, 숫자엔 [n]',
}
NUMERIC = ("그래프", "표", "숫자 타일", "접힌 메모")

WRITER = """너는 「웹 칠판」 딥모드의 기자다. 편집장이 세운 지면 계획의 꼭지마다 **본문**을 쓴다. 칠판이 그대로 물건으로 짓는다(메모·표·그래프·숫자 타일).
독자: {audience}. 목표: 한 판을 보고 빠르게 이해. 쉬운 우리말, 짧은 문장. 오늘은 {today}.

규칙:
- 숫자·날짜·최신 사실은 **재료에 있는 것만**, 쓴 자리마다 출처 번호 [n](재료 머리의 번호 그대로). 재료에 없는 숫자는 지어내지 않는다 — 모자라면 항목을 줄인다.
- source가 ai인 꼭지(설명·용어·문제·단계)는 숫자 없이 일반 지식으로.
- 꼭지 모양마다 정해진 칸만(아래). 설명·코드펜스 없이 JSON 하나:
{{"sections": [{{"title": "꼭지 제목 그대로", "body": {{…}}}}, …]}}

모양별 body 칸:
{schema}"""


def schema_text(secs) -> str:
    shapes = sorted({s.get("shape") for s in secs if s.get("shape") in SCHEMA})
    return "\n".join(f"- {sh}: {SCHEMA[sh]}" for sh in shapes)


# ── 재료(출처 주소까지) ──
def gather(key: str, plan: dict) -> dict:
    """꼭지마다 재료 글 + 판 전체 출처 목록. 재료 글 속 [k](도구마다 따로 매긴 번호)를 판 번호 [n]으로 바꿈."""
    secs = plan.get("sections") or []

    def one(sec):
        src, q = sec.get("source"), (sec.get("query") or sec.get("title") or "")
        try:
            if src == "web":
                ans, raw = board_chat.exa_answer(key, q[:4000], board_chat.SEARCH_SYSTEM)
                return {"text": ans, "sources": [{"title": r["title"] or r["url"], "url": r["url"]} for r in raw["search_results"]]}
            if src == "kr":
                found = kr_tools.gather(key, q, client=ClientRec(gw._client(key, gw.BASE_URL, timeout=60)), today=TODAY)
                return {"text": kr_tools.context_text(found), "sources": [{"title": s["title"], "url": s["url"]} for s in kr_tools.sources(found)]} if found else {"text": "", "sources": [], "empty": True}
        except Exception as e:
            return {"text": "", "sources": [], "error": f"{type(e).__name__}: {e}"[:200]}
        return None

    t0, b0 = time.time(), balance(key)
    with ThreadPoolExecutor(max_workers=max(1, len(secs))) as ex:
        got = list(ex.map(one, secs))
    sec, credits = time.time() - t0, b0 - (time.sleep(2) or balance(key))
    allsrc, mats = [], []
    for g in got:
        if not g:
            mats.append(None)
            continue
        local = {}
        for k, s in enumerate(g["sources"], 1):
            hit = next((x for x in allsrc if x["url"] == s["url"] and s["url"]), None) or next((x for x in allsrc if not s["url"] and x["title"] == s["title"]), None)
            if not hit:
                hit = {"n": len(allsrc) + 1, **s}
                allsrc.append(hit)
            local[k] = hit["n"]
        text = re.sub(r"\[(\d+)\]", lambda m: f"[{local.get(int(m.group(1)), '?')}]", g["text"])
        mats.append({"text": text, **({"error": g["error"]} if g.get("error") else {}), **({"empty": True} if g.get("empty") else {})})
    return {"sec": round(sec, 1), "credits": round(credits, 2), "sources": allsrc, "materials": mats}


def mat_block(plan, mat, sources, only=None) -> str:
    secs = plan.get("sections") or []
    lines = [f"[지면] {plan.get('title')} — {plan.get('headline')}", "", "[꼭지]"]
    for i, s in enumerate(secs):
        if only is not None and i != only:
            continue
        lines.append(f"{i + 1}. {s.get('title')} · 모양 {s.get('shape')}{' · ' + s['chart'] if s.get('chart') else ''} · 출처 {s.get('source')} · 크기 {s.get('size')}\n   독자의 질문: {s.get('question')}")
        m = mat["materials"][i]
        if m and m.get("text"):
            lines.append("   [재료]\n" + "\n".join("   " + x for x in m["text"][:5000].splitlines()))
        elif s.get("source") in ("web", "kr"):
            lines.append("   [재료 없음 — 숫자 없이 쓰거나 항목을 줄임]")
    if only is not None:
        lines.append("\n[다른 꼭지 제목 — 겹치지 않게] " + " · ".join(s.get("title", "") for j, s in enumerate(secs) if j != only))
    lines.append("\n[출처 번호]\n" + "\n".join(f"[{s['n']}] {s['title']} — {s['url']}" for s in sources))
    return "\n".join(lines)


def call(client, model, system, user, max_tokens=8000):
    t0 = time.time()
    r = client.chat.completions.create(model=model, max_tokens=max_tokens, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return r.choices[0].message.content or "", r.usage, time.time() - t0


def write(key: str, plan: dict, mat: dict, mode: str, prices: dict) -> dict:
    model, how = MODES[mode]
    secs = plan.get("sections") or []
    client = gw._client(key, gw.BASE_URL, timeout=600)
    sys_ = WRITER.format(audience="처음 보는 사람", today=TODAY, schema=schema_text(secs))
    b0, t0 = balance(key), time.time()
    if how == "one":
        text, u, _ = call(client, model, sys_, mat_block(plan, mat, mat["sources"]) + "\n\n꼭지마다 body를 써서 JSON 하나로.")
        got = (parse_plan(text) or {}).get("sections") or []
        tin, tout = u.prompt_tokens, u.completion_tokens
        bodies = {s.get("title"): s.get("body") for s in got if isinstance(s, dict)}
        per = None
    else:
        def one(i):
            text, u, sec = call(client, model, WRITER.format(audience="처음 보는 사람", today=TODAY, schema=schema_text([secs[i]])),
                                mat_block(plan, mat, mat["sources"], only=i) + f"\n\n{i + 1}번 꼭지 하나만 body를 써서 JSON 하나로.", 3000)
            got = (parse_plan(text) or {}).get("sections") or []
            return (got[0].get("body") if got and isinstance(got[0], dict) else None), u.prompt_tokens, u.completion_tokens, round(sec, 1)
        with ThreadPoolExecutor(max_workers=len(secs)) as ex:
            res = list(ex.map(one, range(len(secs))))
        bodies = {secs[i].get("title"): r[0] for i, r in enumerate(res)}
        tin, tout = sum(r[1] for r in res), sum(r[2] for r in res)
        per = [r[3] for r in res]
    sec = time.time() - t0
    time.sleep(2)
    credits = b0 - balance(key)
    out_secs = [{**{k: s.get(k) for k in ("title", "question", "shape", "chart", "source", "size")}, "body": bodies.get(s.get("title")) or {}} for s in secs]
    return {"mode": mode, "model": model, "how": how, "sec": round(sec, 1), "per_section_sec": per, "credits": round(credits, 2), "in": tin, "out": tout,
            "usd": round(usd(prices, model, tin, tout), 4), "sections": out_secs, "check": check(out_secs, mat["sources"])}


# ── 품질 ──
_REF = re.compile(r"\[(\d+)\]")
_HASNUM = re.compile(r"\d")


def check(secs, sources) -> dict:
    ns = {s["n"] for s in sources}
    need = {"주인공 글": "text", "용어 풀이": "terms", "단계 카드": "steps", "움직이는 카드": "note", "그래프": "rows", "표": "rows", "숫자 타일": "tiles", "확인 문제": "items", "출처 카드": "links", "접힌 메모": "md"}
    bad_shape, uncited, bad_ref, ai_nums, empty = [], [], [], [], []
    for s in secs:
        b, sh = s.get("body") or {}, s.get("shape")
        if not b:
            empty.append(s["title"])
            continue
        if sh in need and need[sh] not in b:
            bad_shape.append(s["title"])
        strs = []
        if sh in ("그래프", "표"):
            strs = [c for r in (b.get("rows") or [])[1:] for c in r[1:]]
        elif sh == "숫자 타일":
            for t in b.get("tiles") or []:
                if len(t) < 3 or not isinstance(t[2], int):
                    uncited.append(f"{s['title']}: {t[:1]}")
                elif t[2] not in ns:
                    bad_ref.append(f"{s['title']}: {t[2]}")
        elif sh == "접힌 메모":
            strs = (b.get("md") or "").splitlines()
        for x in strs:
            x = str(x)
            refs = [int(m) for m in _REF.findall(x)]
            if _HASNUM.search(_REF.sub("", x)) and not refs:
                uncited.append(f"{s['title']}: {x[:40]}")
            bad_ref += [f"{s['title']}: {n}" for n in refs if n not in ns]
        if s.get("source") == "ai" and sh not in NUMERIC:
            flat = json.dumps(b, ensure_ascii=False)
            if re.search(r"\d{2,}", _REF.sub("", flat)):
                ai_nums.append(s["title"])
    return {"empty": empty, "bad_shape": bad_shape, "uncited": uncited[:8], "n_uncited": len(uncited), "bad_ref": bad_ref, "ai_nums": ai_nums}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", default="paper,tx,news")
    ap.add_argument("--modes", default="A,B,C")
    ap.add_argument("--src", default=os.path.join(HERE, "_deepmode_probe"))
    ap.add_argument("--out", default=os.path.join(HERE, "_deepbody_probe"))
    a = ap.parse_args()
    key = gw.resolve_api_key()
    if not key:
        sys.exit("키 없음 — ~/.claude/.secrets/easycad-gateway.key")
    os.makedirs(a.out, exist_ok=True)
    prices, start = price_of(key), balance(key)
    print(f"시작 잔액 {start:.2f}")
    for name in a.topics.split(","):
        plan = json.load(open(os.path.join(a.src, f"{name}.json"), encoding="utf-8"))["plans"][0]["plan"]
        mat = gather(key, plan)
        print(f"[{name}] 재료 {mat['sec']}초 · {mat['credits']}cr · 출처 {len(mat['sources'])} · 빈 꼭지 {[plan['sections'][i]['title'] for i, m in enumerate(mat['materials']) if m and (m.get('empty') or m.get('error'))]}")
        json.dump({"plan": plan, **mat}, open(os.path.join(a.out, f"{name}_materials.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        for mode in a.modes.split(","):
            r = write(key, plan, mat, mode, prices)
            c = r["check"]
            print(f"[{name}] {mode} {r['model']} {r['how']}: {r['sec']}초 · {r['credits']}cr · ${r['usd']} · in {r['in']} out {r['out']}"
                  f"{' · 꼭지별 ' + str(r['per_section_sec']) if r['per_section_sec'] else ''}\n      빈 {c['empty']} · 칸 틀림 {c['bad_shape']} · 출처 없는 숫자 {c['n_uncited']} {c['uncited']} · 없는 번호 {c['bad_ref']} · ai 꼭지 숫자 {c['ai_nums']}")
            fixture = {"_note": f"딥모드 3-0 실측 — 계획 0단계 opus, 재료 다시 모음, 본문 {mode} {r['model']} {r['how']}", "title": plan.get("title"), "headline": plan.get("headline"),
                       "sources": mat["sources"], "sections": r["sections"], "_measure": {k: r[k] for k in ("sec", "credits", "in", "out", "usd", "per_section_sec", "check")}}
            json.dump(fixture, open(os.path.join(a.out, f"{name}_{mode}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"끝 잔액 {balance(key):.2f} (전체 {start - balance(key):.2f}cr)")


if __name__ == "__main__":
    main()
