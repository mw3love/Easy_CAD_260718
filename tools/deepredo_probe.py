"""딥모드(§8 항목66) 5-0 실측 — 꼭지 다시 쓰기(`deep_mode.redo`)의 시간·크레딧·품질. 앱 함수를 그대로 부른다(지시문이 갈라지지 않게).

재료 = 4-2 실조건 판(`web/test/fixtures/deep_real_live.json` — ATSC 3.0, 꼭지 9개·출처 23개). 경우마다 따로 돌려 잔액 차이를 잰다:
  hero  = 주인공 글(ai) 「더 자세히」(고칠 말 없음)
  graph = 그래프(web) 「더 자세히」 — 재료 다시 + 새 출처 번호가 판 번호 뒤에 붙나
  more  = 그래프(web) 「중간 조합 숫자도 더 넣어 줘」 — 재료에 없는 걸 달라 할 때 못 한 까닭(change)을 쓰나(5-4 실조건 질문)
  shape = 그래프(web) 「표로 바꿔 줘」 — 모양 바꾸기
  card  = 움직이는 카드 「더 자세히」 — 앞 HTML 고치기
결과 = `tools/_deepredo_probe/<경우>.json`(판 전체 — 고친 꼭지를 끼운 것, 칠판 `ed.deepBoard`로 바로 지어 볼 수 있음) + results.json.

사용:
    python tools/deepredo_probe.py                    # 넷 다(상한 --cap 300cr — 넘으면 거기서 멈춤)
    python tools/deepredo_probe.py --cases hero,card
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from easycad.ai import deep_mode            # noqa: E402
from easycad.ai import gateway as gw        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN = os.path.join(os.path.dirname(HERE), "web", "test", "fixtures", "deep_real_live.json")
CASES = {"hero": ([0], ""), "graph": ([3], ""), "more": ([3], "중간 조합 숫자도 더 넣어 줘"), "shape": ([3], "표로 바꿔 줘"), "card": ([5], "")}
BRIEF = {"누구에게": "송신소 신입"}
_REF = re.compile(r"\[(\d+)\]")


def check(old: dict, new: dict, plan: dict, sources: list) -> dict:
    ns = {s["n"] for s in sources}
    flat = json.dumps({k: v for k, v in (new.get("body") or {}).items() if k != "html"}, ensure_ascii=False)   # 카드 HTML 속 [0]은 스크립트(배열) — 출처 번호 아님
    blank = sum(1 for r in ((new.get("body") or {}).get("rows") or [])[1:] for c in r[1:] if not str(c).strip()) if new["shape"] == "그래프" else 0
    refs = sorted({int(x) for x in _REF.findall(flat)} | {t[2] for t in (new.get("body") or {}).get("tiles") or [] if len(t) > 2 and isinstance(t[2], int)})
    o, n = json.dumps(old.get("body") or {}, ensure_ascii=False), flat
    return {"shape": f"{old['shape']} → {new['shape']}" if old["shape"] != new["shape"] else new["shape"], "len": [len(o), len(n)],
            "refs": refs, "bad_refs": [r for r in refs if r not in ns], "blank_cells": blank, "new_sources": len(sources) - len(plan.get("sources") or []),
            "html": [len((old.get("body") or {}).get("html") or ""), len((new.get("body") or {}).get("html") or "")]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--cap", type=float, default=300)
    ap.add_argument("--out", default=os.path.join(HERE, "_deepredo_probe"))
    a = ap.parse_args()
    key = gw.resolve_api_key()
    if not key:
        sys.exit("키 없음 — ~/.claude/.secrets/easycad-gateway.key")
    os.makedirs(a.out, exist_ok=True)
    plan = json.load(open(PLAN, encoding="utf-8"))
    path = os.path.join(a.out, "results.json")
    results = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    start = gw.get_credit_balance(key)[0]
    print(f"시작 잔액 {start:.2f} · 상한 {a.cap}cr")
    for name in a.cases.split(","):
        spent = start - gw.get_credit_balance(key)[0]
        if spent >= a.cap:
            print(f"상한 도달({spent:.1f}cr) — {name}부터 안 함")
            break
        idx, ask = CASES[name]
        b0, t0 = gw.get_credit_balance(key)[0], time.time()
        try:
            out = deep_mode.redo(key, gw._client(key, gw.BASE_URL, timeout=600), plan, idx, BRIEF, ask)
        except Exception as e:
            results[name] = {"error": f"{type(e).__name__}: {e}"[:300]}
            print(f"[{name}] 오류 {results[name]['error']}")
            continue
        sec = time.time() - t0
        time.sleep(2)
        credits = b0 - gw.get_credit_balance(key)[0]
        secs = [dict(s) for s in plan["sections"]]
        rep = {"sec": round(sec, 1), "credits": round(credits, 2), "model": out["model"], "missing": out["missing"], "changes": [c["text"] for c in out.get("changes") or []], "checks": []}
        for s in out["sections"]:
            i = s.pop("i")
            rep["checks"].append({"i": i, "title": s["title"], **check(plan["sections"][i], s, plan, out["sources"])})
            secs[i] = s
        json.dump({**plan, "_note": f"5-0 실측 {name} — {idx} {ask or deep_mode.MORE}", "sources": out["sources"], "sections": secs},
                  open(os.path.join(a.out, name + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        results[name] = rep
        print(f"[{name}] {rep['sec']}초 · {rep['credits']}cr · {rep['model']} · 못 씀 {rep['missing']} · " + " / ".join(
            f"{c['title']}: {c['shape']} 길이 {c['len'][0]}→{c['len'][1]} 출처 {c['refs']} 틀린 {c['bad_refs']} 빈 칸 {c['blank_cells']} 새 출처 {c['new_sources']}"
            + (f" html {c['html'][0]}→{c['html'][1]}" if c['html'][0] or c['html'][1] else "") for c in rep["checks"]) + f" · 고친 것 {rep['changes']}")
        json.dump(results, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"끝 잔액 {gw.get_credit_balance(key)[0]:.2f} (전체 {start - gw.get_credit_balance(key)[0]:.2f}cr)")


if __name__ == "__main__":
    main()
