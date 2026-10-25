"""딥모드(§8 항목66) 4-0 실측 — 「움직이는 카드」(스크립트를 켠 HTML 한 장)의 시간·크레딧·품질(앱 코드는 안 고침).

3-0(`deepbody_probe.py`)이 모아 둔 계획·재료(`tools/_deepbody_probe/<주제>_materials.json`)를 그대로 쓰고, 계획 속 「움직이는 카드」 꼭지 하나만:
  1. 모델 셋(claude-opus-5-5 · claude-sonnet-5-5 · gpt-6.1-sol)이 카드 HTML을 씀 — 주제 셋은 동시, 모델은 차례로(잔액 차이를 모델별로)
  2. 잴 것: 시간·크레딧(잔액 차이)·토큰·$·크기, 글로 보는 검사(스크립트·조작 부품·외부 주소·금지 API·출처 번호)
  3. 화면 검사는 `tools/livecard_shot.mjs`(Playwright — 앱과 같은 sandbox + CSP로 띄워 조작 전후 그림·오류·넘침)
결과는 `tools/_livecard_probe/<주제>_<모델>.html`(카드 원본)·`results.json`.

사용:
    python tools/livecard_probe.py                          # 주제 셋 · 모델 셋
    python tools/livecard_probe.py --topics news --models claude-sonnet-5-5
    node tools/livecard_shot.mjs                            # 화면 검사(위 결과 폴더)
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
from deepmode_probe import balance, price_of, usd, TODAY   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "gpt-6.1-sol")
MAX_MAT = 2500       # 꼭지 하나의 재료 글 상한(자) — 공공 데이터 원문은 1만 자가 넘음
MAX_BYTES = 40_000   # 카드 크기 상한(앱이 받을 한도 후보)

LIVE = """너는 「웹 칠판」 딥모드의 「움직이는 카드」를 만든다 — 개념이 원리대로 움직이는 작은 장치 한 장(HTML 한 파일, 스크립트 됨).
독자: 처음 보는 사람. 목표: 직접 만져 보고 원리를 빠르게 이해. 쉬운 우리말, 짧은 문장. 오늘은 {today}.

출력은 완결된 HTML 문서 하나뿐(설명·코드펜스 없이 <!doctype html>로 시작). <title>에 카드 제목.

틀:
- 칠판 위 카드 칸 하나를 꽉 채운다 — 기준 가로 720 × 세로 480 CSS px, 칸 크기가 바뀌면 따라 늘고 줄음(100vw × 100vh). **스크롤·넘침 없음.** 흰 바탕, 글꼴 'Pretendard','Malgun Gothic',sans-serif.
- 네 구석: 왼쪽 위 = 「그림 1」 + 카드 제목, 오른쪽 위 = 실시간 값(조작하면 바뀌는 숫자 1~3개), 왼쪽 아래 = 조작 안내 한 줄(「막대를 끌어 보세요」처럼), 맨 아래 = 지금 보이는 것이 무슨 뜻인지 설명 한 줄(조작에 따라 바뀜).
- 가운데 = **알아보는 물건** — 상자·화살표 도식이 아니라 그 개념이 실제로 생긴 모양(인라인 SVG 또는 canvas).
- 조작은 1~2개(슬라이더·버튼·끌기). 처음 열면 이미 뜻 있는 상태가 보인다(빈 화면 금지). 저절로 도는 움직임은 없어도 되고, 있으면 조작하는 순간 멈춘다.

숫자:
- 화면의 모든 숫자는 스크립트 안 한 곳(상태 하나 + 계산 함수 하나)에서 나와 그림과 값 칸이 늘 같다.
- 사실 숫자(규격·통계·날짜)는 아래 재료에 있는 것만, 쓴 자리 옆에 출처 번호 [n](재료 머리 번호 그대로). 재료에 없는 값으로 보여 줄 땐 「예시 값」이라고 밝힌다. 숫자를 지어내지 않는다.

금지(앱이 막는다 — 쓰면 카드가 깨짐): 외부 주소(스크립트·글꼴·그림·fetch·링크), localStorage·sessionStorage·cookie, alert·confirm·prompt, window.parent·window.top, form 전송, 새 창.
크기: 40KB 안."""


def mat_block(plan: dict, mat: dict, idx: int) -> str:
    secs = plan.get("sections") or []
    s = secs[idx]
    lines = [f"[지면] {plan.get('title')} — {plan.get('headline')}", "",
             f"[이 카드 꼭지] {s.get('title')}\n   독자의 질문: {s.get('question')}", "",
             "[판의 다른 꼭지 — 겹치지 않게] " + " · ".join(x.get("title", "") for j, x in enumerate(secs) if j != idx), "", "[재료]"]
    for i, x in enumerate(secs):
        m = mat["materials"][i]
        if m and m.get("text"):
            lines.append(f"({x.get('title')})\n" + m["text"][:MAX_MAT])
    lines.append("\n[출처 번호]\n" + "\n".join(f"[{x['n']}] {x['title']} — {x['url']}" for x in mat["sources"]))
    return "\n".join(lines) + "\n\n이 꼭지의 움직이는 카드 HTML 하나를 써 줘."


def clean(text: str) -> str:
    t = gw.strip_code_fence(text or "").strip()
    i = t.lower().find("<!doctype")
    return t[i:] if i > 0 else t


_EXT = re.compile(r"""(?:src|href|url\()\s*=?\s*["']?\s*(?:https?:)?//""", re.I)
_BANNED = {"localStorage": r"\blocalStorage\b", "sessionStorage": r"\bsessionStorage\b", "cookie": r"document\.cookie",
           "alert": r"\b(?:alert|confirm|prompt)\s*\(", "parent/top": r"\bwindow\.(?:parent|top)\b|\bparent\.postMessage",
           "fetch": r"\bfetch\s*\(|XMLHttpRequest|WebSocket", "open": r"\bwindow\.open\s*\(", "form": r"<form\b"}


def check(html: str, n_sources: int) -> dict:
    refs = sorted({int(x) for x in re.findall(r"\[(\d+)\]", re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I))})
    return {"bytes": len(html.encode("utf-8")), "over": len(html.encode("utf-8")) > MAX_BYTES,
            "script": bool(re.search(r"<script\b", html, re.I)),
            "controls": len(re.findall(r"<input\b|<button\b", html, re.I)) + len(re.findall(r"createElement\(\s*['\"](?:input|button)", html)),
            "external": _EXT.findall(html)[:3], "banned": [k for k, rx in _BANNED.items() if re.search(rx, html)],
            "refs": refs, "bad_refs": [r for r in refs if not 1 <= r <= n_sources], "title": (re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I) or [None, ""])[1].strip()}


def one(key: str, name: str, model: str) -> dict:
    d = json.load(open(os.path.join(HERE, "_deepbody_probe", f"{name}_materials.json"), encoding="utf-8"))
    plan = d["plan"]
    idx = next(i for i, s in enumerate(plan["sections"]) if s.get("shape") == "움직이는 카드")
    client = gw._client(key, gw.BASE_URL, timeout=600)
    t0 = time.time()
    try:
        r = client.chat.completions.create(model=model, max_tokens=16000, messages=[
            {"role": "system", "content": LIVE.format(today=TODAY)}, {"role": "user", "content": mat_block(plan, d, idx)}])
    except Exception as e:
        return {"topic": name, "model": model, "error": f"{type(e).__name__}: {e}"[:300], "sec": round(time.time() - t0, 1)}
    html = clean(r.choices[0].message.content or "")
    u = r.usage
    return {"topic": name, "model": model, "section": plan["sections"][idx]["title"], "sec": round(time.time() - t0, 1),
            "in": u.prompt_tokens, "out": u.completion_tokens, "html": html, "check": check(html, len(d["sources"])),
            "sources": d["sources"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", default="paper,tx,news")
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--out", default=os.path.join(HERE, "_livecard_probe"))
    a = ap.parse_args()
    key = gw.resolve_api_key()
    if not key:
        sys.exit("키 없음 — ~/.claude/.secrets/easycad-gateway.key")
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "results.json")
    results = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    prices, start = price_of(key), balance(key)
    print(f"시작 잔액 {start:.2f}")
    topics = a.topics.split(",")
    for model in a.models.split(","):
        b0 = balance(key)
        with ThreadPoolExecutor(max_workers=len(topics)) as ex:
            got = list(ex.map(lambda n: one(key, n, model), topics))
        time.sleep(2)
        spent = b0 - balance(key)
        for r in got:
            tag = f"{r['topic']}_{model}"
            if "error" in r:
                print(f"[{tag}] 오류 {r['error']}")
                results[tag] = {k: v for k, v in r.items()}
                continue
            open(os.path.join(a.out, tag + ".html"), "w", encoding="utf-8").write(r.pop("html"))
            r.pop("sources")
            r["usd"] = round(usd(prices, model, r["in"], r["out"]), 4)
            r["model_credits_all_topics"] = round(spent, 2)
            results[tag] = r
            c = r["check"]
            print(f"[{tag}] {r['sec']}초 · in {r['in']} out {r['out']} · ${r['usd']} · {c['bytes']}B{' 넘침' if c['over'] else ''} · 조작 {c['controls']}"
                  f" · 외부 {c['external']} · 금지 {c['banned']} · 출처 {c['refs']} 틀린 번호 {c['bad_refs']} · 「{c['title']}」")
        print(f"  {model}: 주제 {len(topics)}개 합 {spent:.2f}cr")
        json.dump(results, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"끝 잔액 {balance(key):.2f} (전체 {start - balance(key):.2f}cr)")


if __name__ == "__main__":
    main()
