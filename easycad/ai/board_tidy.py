"""웹 칠판 「정리해 줘」 ② 레고형 정리정돈 — 고른 것(없으면 화면에 보이는 것)을 뜻이 맞는 것끼리 묶음 목록으로(Qt 비의존, `web/server.py`가 부름, §8 항목61 2026-10-19).

AI는 도형마다 uid·종류·글 앞부분·크기만 받아 **어떤 것끼리 묶을지**만 답한다 — 좌표는 맡기지 않는다(데스크톱 흐름도 원칙: 좌표를 맡기면 겹치고 들쭉날쭉).
자리 잡기(묶음마다 프레임, 바둑판, 안에서 줄 맞춤)는 칠판(`web/src/next/Editor.jsx` `applyTidy`)이 한다. 지우거나 새로 쓰지 않는다 — 옮기고 제목만 단다.
"""
from __future__ import annotations

import json
import re
import time

TIDY_MODEL = "gpt-6-luna"   # 2026-10-20 7종 비교(정답 묶음 있는 칠판 2개, history): 옛 claude-sonnet-5-5는 4번 중 1번 JSON 깨짐·$0.005,
#   gpt-6-luna는 둘 다 완벽·4~6초·$0.0003(1/18). 사용자 선택
MAX_ITEMS = 300        # 한 번에 정돈할 도형 상한
MAX_TEXT = 160         # 도형마다 보내는 글 앞부분(자)
MAX_SECTIONS = 9
OTHER = "기타"

SYSTEM = """너는 칠판에 흩어진 메모·카드·도형을 주제별로 묶어 정돈하는 도우미다. 한국어로 쓴다.
입력은 칠판 조각 목록이다(uid · 종류 · 크기 · 글 앞부분). 내용을 이해하고 뜻이 맞는 것끼리 2~7개의 묶음으로 나눈다.
- 조각을 지우거나 새로 쓰지 않는다. 모든 uid를 정확히 한 묶음에 한 번씩 넣는다. 목록에 없는 uid를 만들지 않는다.
- 묶음 차례 = 읽는(발표할) 차례. 묶음 안 차례도 읽기 좋은 차례로(시간·원인→결과·중요한 것 먼저).
- 묶음 제목은 짧게(15자 안), note는 그 묶음을 설명하는 한 줄(40자 안). 글이 없는 조각은 가까운 뜻의 묶음이나 「기타」에.
- opinion은 전체를 보고 드는 핵심 의견 한 줄(작성자 의견).
출력은 JSON 하나뿐이다(설명·코드펜스 없이):
{"title": "전체 제목", "sections": [{"title": "묶음 제목", "items": ["uid", ...], "note": "한 줄 설명"}], "opinion": "핵심 의견 한 줄"}"""


def item_lines(items: list) -> str:
    """칠판 조각 → AI에 보낼 목록 글(한 줄에 하나)."""
    out = []
    for it in items[:MAX_ITEMS]:
        t = re.sub(r"\s+", " ", str(it.get("text") or "")).strip()[:MAX_TEXT]
        out.append(f"- {it.get('uid')} · {it.get('type') or '?'} · {int(it.get('w') or 0)}x{int(it.get('h') or 0)} · {t or '(글 없음)'}")
    return "\n".join(out)


def parse_json(text: str) -> dict:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < i:
        raise ValueError("묶음 목록(JSON)이 아닌 답")
    return json.loads(t[i:j + 1])


def normalize(plan: dict, uids: list) -> dict:
    """AI 답 → 믿을 수 있는 묶음 목록: 없는 uid·겹친 uid는 빼고, 빠진 uid는 「기타」로, 빈 묶음은 버림, 묶음 수 상한(넘치면 끝을 「기타」로 합침)."""
    known, seen, secs = set(uids), set(), []
    for s in plan.get("sections") or []:
        if not isinstance(s, dict):
            continue
        ids = []
        for u in s.get("items") or []:
            if isinstance(u, str) and u in known and u not in seen:
                seen.add(u)
                ids.append(u)
        if ids:
            secs.append({"title": str(s.get("title") or "묶음").strip()[:30] or "묶음", "items": ids, "note": str(s.get("note") or "").strip()[:80]})
    if len(secs) > MAX_SECTIONS:   # 넘친 끝 묶음들은 하나로
        rest = [u for s in secs[MAX_SECTIONS - 1:] for u in s["items"]]
        secs = secs[:MAX_SECTIONS - 1] + [{"title": OTHER, "items": rest, "note": ""}]
    left = [u for u in uids if u not in seen]
    if left:
        other = next((s for s in secs if s["title"] == OTHER), None)
        if other:
            other["items"] += left
        else:
            secs.append({"title": OTHER, "items": left, "note": ""})
    return {"title": str(plan.get("title") or "정리정돈").strip()[:40] or "정리정돈", "sections": secs, "opinion": str(plan.get("opinion") or "").strip()[:200]}


def summary(plan: dict) -> str:
    """대화창에 보일 답 글."""
    n = sum(len(s["items"]) for s in plan["sections"])
    lines = [f"**{plan['title']}** — 조각 {n}개를 {len(plan['sections'])}묶음으로 정돈했어요(되돌리기 Ctrl+Z 한 번)."]
    lines += [f"- **{s['title']}** ({len(s['items'])}개){' — ' + s['note'] if s['note'] else ''}" for s in plan["sections"]]
    if plan.get("opinion"):
        lines += ["", f"핵심 의견: {plan['opinion']}"]
    return "\n".join(lines)


def make(client, items: list, ask: str = "", *, model: str = TIDY_MODEL) -> dict:
    """칠판 조각 [{uid, type, text, w, h}](+요청) → {"plan", "content", "model", "elapsed"}."""
    items = [it for it in items if isinstance(it, dict) and isinstance(it.get("uid"), str) and it["uid"]][:MAX_ITEMS]
    if len(items) < 2:
        raise ValueError("정돈할 조각이 2개 이상 있어야 해요 — 칠판에서 고르거나 화면에 보이게 해 주세요")
    user = "[칠판 조각]\n" + item_lines(items) + ("\n\n[요청]\n" + ask if ask else "") + "\n\n위 조각들을 주제별 묶음으로 나눠 JSON으로 답해 줘."
    t0 = time.time()
    r = client.chat.completions.create(model=model, max_tokens=4000, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    plan = normalize(parse_json(r.choices[0].message.content or ""), [it["uid"] for it in items])
    return {"plan": plan, "content": summary(plan), "model": model, "elapsed": round(time.time() - t0, 1)}
