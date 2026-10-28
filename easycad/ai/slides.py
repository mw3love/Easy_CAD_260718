"""웹 칠판 「📽 발표 자료」(§8 항목69, 2026-10-28 사용자 — NotebookLM 슬라이드처럼: 칠판 자료나 주제로 프레임 여러 장, 바로 발표).

딥모드(한 판 = 읽는 신문)와 결과 성질이 달라 입구는 따로, 속은 딥모드 것을 같이 씀 — 질문지 카드·계획 카드(대화창)·재료 모으기(`deep_mode.gather` — 웹)·
「이 칠판」 재료(여기선 칠판에서 고른 것의 글). 순서: 장 계획(제목·요점·재료 출처) → 사람이 빼고 고침 → 장마다 본문(제목·세 줄 안팎·발표자 메모).
장은 칠판이 16:9 프레임으로 짓는다(`Editor.slidesBoard`). Qt 없음 — `web/server.py`가 부른다.
"""
from __future__ import annotations

import time

from easycad.ai import deep_mode, gateway as gw

PLAN_MODEL = "claude-sonnet-5-5"     # 장 계획 — 딥모드 편집장(opus)보다 싸고 빠르게(장 제목·요점만이라) — 추정, 실측 2026-10-28
WRITER_MODEL = "claude-sonnet-5-5"   # 장마다 본문
SOURCES = ("ai", "web", "board")
MAX_SLIDES = 15
MAX_MATERIAL = 40000
LAYOUTS = ("표지", "글머리", "숫자", "단계", "한마디", "마무리")   # 장 모양 — 칠판 `slidesBoard`가 그릴 줄 아는 것(2단계)

PLANNER = """너는 발표 자료를 짜는 기획자다. 사용자의 주제(와 칠판에서 고른 자료)로 **장 계획**만 세운다(본문은 아직 쓰지 않는다).
- JSON 하나만: {{"title": "발표 제목", "slides": [{{"title": "장 제목(짧게)", "point": "이 장에서 말할 한 줄", "source": "ai|web|board", "query": "웹 검색 문장 또는 null"}}]}}
- 장 수는 {n}장 안팎(첫 장 = 표지, 끝 장 = 정리·다음 할 일). 한 장에 생각 하나.
- source: ai = 일반 지식으로 설명, web = 최신 사실·숫자가 필요(query에 혼자 통하는 검색 문장), board = 아래 [고른 자료]에서.
  [고른 자료]가 있으면 그것을 중심으로 짠다. 숫자·사실은 web이나 board에서만 — 계획에는 숫자를 쓰지 않는다.
- 듣는 사람·발표 시간·바라는 점(질문지 답)을 따른다. 「알아서」는 네가 정한다."""

WRITER = """너는 발표 자료를 쓰는 사람이다. 장 계획의 장마다 **화면에 띄울 글**과 **발표자 메모**를 쓴다. 듣는 사람: {audience}. 오늘: {today}.
- JSON 하나만: {{"slides": [{{"title": "장 제목", "layout": "표지|글머리|숫자|단계|한마디|마무리", "bullets": ["화면 글 한 줄", …], "numbers": [{{"value": "70%", "label": "발전기 연료 [1]"}}], "steps": ["단계 한 줄", …], "message": "핵심 한 문장", "notes": "발표자가 말할 내용 2~4문장"}}]}}
- layout(장 모양) 고르기 — 장마다 내용에 맞게, 같은 모양만 이어지지 않게(2026-10-28 2단계):
  표지 = 첫 장(bullets = 부제·발표자 자리 한 줄) · 숫자 = 기억할 숫자가 2~3개(numbers, value는 8자 안팎 — 「70%」「8시간」) · 단계 = 순서·절차(steps 3~5개, 한 줄 30자 안팎) ·
  한마디 = 꼭 남길 한 문장을 크게(message 25자 안팎) · 마무리 = 끝 장(bullets = 할 일·다음 걸음) · 그 밖엔 글머리.
- 어떤 모양이든 bullets도 써 둔다(칠판이 그 모양을 못 그리면 글머리로).
- bullets는 장마다 2~4줄, 한 줄 25자 안팎(읽는 글이 아니라 보는 글).
- 숫자·날짜·최신 사실은 **재료에 있는 것만**, 쓴 줄 끝에 출처 번호 [n](재료 머리의 번호 그대로). 재료에 없는 숫자는 지어내지 않는다.
- notes는 그 장을 말로 풀어 주는 문장(화면 글을 되풀이하지 않는다). 쉬운 말, 강조는 **굵게**만."""


def brief_text(brief: dict) -> str:
    return "\n".join(f"- {k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in (brief or {}).items()) or "- (없음)"


def count_of(brief: dict) -> int:
    """질문지 「장 수」 → 숫자(알아서 = 8)."""
    v = str((brief or {}).get("장 수") or "")
    digits = "".join(c for c in v if c.isdigit())
    return max(3, min(MAX_SLIDES, int(digits))) if digits else 8


def clean_plan(plan) -> dict:
    if not isinstance(plan, dict) or not isinstance(plan.get("slides"), list):
        raise ValueError("장 계획이 JSON이 아니에요 — 다시 짜 주세요")
    out = []
    for s in plan["slides"][:MAX_SLIDES]:
        if not isinstance(s, dict) or not str(s.get("title") or "").strip():
            continue
        src = s.get("source") if s.get("source") in SOURCES else "ai"
        q = str(s.get("query") or "").strip() or None
        out.append({"title": str(s["title"]).strip()[:60], "point": str(s.get("point") or "").strip()[:200], "source": "web" if src == "web" or (src == "ai" and q) else src,
                    "query": q if src != "board" else None})
    if len(out) < 2:
        raise ValueError("장이 너무 적어요 — 다시 짜 주세요")
    return {"title": str(plan.get("title") or out[0]["title"]).strip()[:80], "slides": out}


def estimate(plan: dict) -> dict:
    """「이대로 만들기」 어림 — 웹 장 하나 약 3초·5크레딧(딥모드 3-0 실측), 본문 sonnet 장 수만큼. 추정."""
    n, web = len(plan["slides"]), sum(1 for s in plan["slides"] if s["source"] == "web")
    return {"credits": [10 + 3 * n + 5 * web, 20 + 5 * n + 6 * web], "seconds": [15 + 2 * n, 30 + 4 * n]}


def make_plan(client, topic: str, brief: dict, *, material: str = "", prev: dict | None = None, fix: str = "", model: str = PLAN_MODEL) -> dict:
    t0 = time.time()
    user = f"[주제]\n{topic}\n\n[질문지 답]\n{brief_text(brief)}"
    if material:
        user += f"\n\n[고른 자료]\n{material[:MAX_MATERIAL]}"
    if prev:
        user += f"\n\n[앞 계획]\n" + "\n".join(f"{i + 1}. {s.get('title')} — {s.get('point')}" for i, s in enumerate(prev.get("slides") or [])) + f"\n\n[고칠 점]\n{fix}\n앞 계획에서 고칠 점만 반영해 다시."
    r = client.chat.completions.create(model=model, max_tokens=3000, messages=[
        {"role": "system", "content": PLANNER.format(n=count_of(brief))}, {"role": "user", "content": user}])
    plan = clean_plan(deep_mode.parse_json(r.choices[0].message.content or ""))
    return {"plan": plan, "estimate": estimate(plan), "model": model, "elapsed": round(time.time() - t0, 1)}


def material_text(plan: dict, mat: dict, board: str = "") -> str:
    lines = [f"[발표] {plan.get('title')}", "", "[장]"]
    for i, s in enumerate(plan["slides"]):
        lines.append(f"{i + 1}. {s['title']} — {s.get('point') or ''} · 출처 {s['source']}")
        m = mat["materials"][i] if i < len(mat["materials"]) else None
        if m and m.get("text"):
            lines.append("   [재료]\n" + "\n".join("   " + x for x in m["text"][:4000].splitlines()))
        elif s["source"] == "web":
            lines.append("   [재료 없음 — 숫자 없이]")
    if board:
        lines.append("\n[고른 자료]\n" + board[:MAX_MATERIAL])
    lines.append("\n[출처 번호]\n" + ("\n".join(f"[{x['n']}] {x['title']} — {x['url']}" for x in mat["sources"]) or "(없음)"))
    return "\n".join(lines)


def build(key: str, client, topic: str, brief: dict, plan: dict, *, base_url: str = gw.BASE_URL, material: str = "", model: str = WRITER_MODEL, exa=None) -> dict:
    """장 계획 → {"deck": {"title", "slides": [{title, bullets, notes}], "sources"}, "model", "elapsed", "missing"}. exa = 시험용."""
    plan = clean_plan(plan)
    t0 = time.time()
    secs = [{"title": s["title"], "shape": "주인공 글", "source": s["source"] if s["source"] == "web" else "ai", "query": s["query"]} for s in plan["slides"]]
    mat = deep_mode.gather(key, {"sections": secs}, base_url=base_url, exa=exa) if any(s["source"] == "web" for s in secs) else {"sources": [], "materials": [None] * len(secs)}
    who = (brief or {}).get("듣는 사람")
    system = WRITER.format(audience=who if who and who != deep_mode.AUTO else "처음 보는 동료", today=deep_mode.today())
    r = client.chat.completions.create(model=model, max_tokens=8000, messages=[
        {"role": "system", "content": system}, {"role": "user", "content": f"[주제] {topic}\n[질문지 답]\n{brief_text(brief)}\n\n" + material_text(plan, mat, material) + "\n\n장마다 써서 JSON 하나로."}])
    got = (deep_mode.parse_json(r.choices[0].message.content or "") or {}).get("slides") or []
    slides, missing = [], []
    for i, s in enumerate(plan["slides"]):   # 제목이 조금 바뀌어 와도 차례로 맞춤
        g = got[i] if i < len(got) and isinstance(got[i], dict) else {}
        bullets = [str(b).strip() for b in g.get("bullets") or [] if str(b).strip()][:5]
        if not bullets:
            missing.append(s["title"])
        one = {"title": str(g.get("title") or s["title"]).strip()[:60], "bullets": bullets or [s.get("point") or ""], "notes": str(g.get("notes") or "").strip()}
        layout = str(g.get("layout") or "")
        nums = [{"value": str(x.get("value") or "").strip()[:14], "label": str(x.get("label") or "").strip()[:60]} for x in g.get("numbers") or [] if isinstance(x, dict) and str(x.get("value") or "").strip()][:3]
        steps = [str(x).strip()[:60] for x in g.get("steps") or [] if str(x).strip()][:5]
        msg = str(g.get("message") or "").strip()[:80]
        if i == 0:
            layout = "표지"
        elif layout == "숫자" and len(nums) < 2 or layout == "단계" and len(steps) < 2 or layout == "한마디" and not msg or layout not in LAYOUTS:
            layout = "마무리" if i == len(plan["slides"]) - 1 else "글머리"   # 그 모양에 쓸 것이 없으면 글머리로
        one["layout"] = layout
        one.update({"numbers": nums} if layout == "숫자" else {"steps": steps} if layout == "단계" else {"message": msg} if layout == "한마디" else {})
        slides.append(one)
    return {"deck": {"title": plan["title"], "slides": slides, "sources": mat["sources"]}, "model": model, "elapsed": round(time.time() - t0, 1), "missing": missing}
