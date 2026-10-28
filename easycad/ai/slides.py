"""웹 칠판 「📽 발표 자료」(§8 항목69, 2026-10-28 사용자 — NotebookLM 슬라이드처럼: 칠판 자료나 주제로 프레임 여러 장, 바로 발표).

딥모드(한 판 = 읽는 신문)와 결과 성질이 달라 입구는 따로, 속은 딥모드 것을 같이 씀 — 질문지 카드·계획 카드(대화창)·재료 모으기(`deep_mode.gather` — 웹)·
「이 칠판」 재료(여기선 칠판에서 고른 것의 글). 순서: 장 계획(제목·요점·재료 출처) → 사람이 빼고 고침 → 장마다 본문(제목·세 줄 안팎·발표자 메모).
장은 칠판이 16:9 프레임으로 짓는다(`Editor.slidesBoard`). Qt 없음 — `web/server.py`가 부른다.
"""
from __future__ import annotations

import json
import time

from easycad.ai import deep_mode, gateway as gw, see

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


def make_plan(client, topic: str, brief: dict, *, material: str = "", prev: dict | None = None, fix: str = "", model: str = PLAN_MODEL, images=None) -> dict:
    """images = 고른 것 속 그림(`see`) — 그림만 골라도 [고른 자료]로 짬."""
    t0 = time.time()
    images = list(images or [])
    user = f"[주제]\n{topic}\n\n[질문지 답]\n{brief_text(brief)}"
    if material or images:
        user += f"\n\n[고른 자료]\n{material[:MAX_MATERIAL]}{see.note(len(images))}"
    if prev:
        user += f"\n\n[앞 계획]\n" + "\n".join(f"{i + 1}. {s.get('title')} — {s.get('point')}" for i, s in enumerate(prev.get("slides") or [])) + f"\n\n[고칠 점]\n{fix}\n앞 계획에서 고칠 점만 반영해 다시."
    r = client.chat.completions.create(model=model, max_tokens=3000, messages=see.attach([
        {"role": "system", "content": PLANNER.format(n=count_of(brief))}, {"role": "user", "content": user}], images))
    plan = clean_plan(deep_mode.parse_json(r.choices[0].message.content or ""))
    return {"plan": plan, "estimate": estimate(plan), "model": model, "elapsed": round(time.time() - t0, 1)}


def material_text(plan: dict, mat: dict, board: str = "", n_images: int = 0) -> str:
    lines = [f"[발표] {plan.get('title')}", "", "[장]"]
    for i, s in enumerate(plan["slides"]):
        lines.append(f"{i + 1}. {s['title']} — {s.get('point') or ''} · 출처 {s['source']}")
        m = mat["materials"][i] if i < len(mat["materials"]) else None
        if m and m.get("text"):
            lines.append("   [재료]\n" + "\n".join("   " + x for x in m["text"][:4000].splitlines()))
        elif s["source"] == "web":
            lines.append("   [재료 없음 — 숫자 없이]")
    if board or n_images:
        lines.append("\n[고른 자료]\n" + board[:MAX_MATERIAL] + see.note(n_images))
    lines.append("\n[출처 번호]\n" + ("\n".join(f"[{x['n']}] {x['title']} — {x['url']}" for x in mat["sources"]) or "(없음)"))
    return "\n".join(lines)


COVER = ("발표 자료 표지 오른쪽 위에 놓일 그림 한 장. 주제: {title}. 다룰 내용: {points}. "
         "글자·숫자·로고 없이, 깔끔한 플랫 일러스트, 흰 바탕, 차분한 색에 주황 포인트 하나, 가로 4:3.")


def cover_prompt(plan: dict) -> str:
    return COVER.format(title=plan["title"], points=" · ".join(s["title"] for s in plan["slides"][1:5]))


def build(key: str, client, topic: str, brief: dict, plan: dict, *, base_url: str = gw.BASE_URL, material: str = "", model: str = WRITER_MODEL, exa=None, image=None, images=None) -> dict:
    """장 계획 → {"deck": {"title", "slides": [{title, layout, bullets, notes, …}], "sources", "cover"?}, "model", "elapsed", "missing"}. exa = 시험용.
    image = 표지 그림 그리기(서버 `_deep_image` — 지시문 → {"img", "w", "h", "model"}), 장 본문을 쓰는 동안 같이(3단계 — 그림 약 12초·12크레딧이 기다림에 안 더해지게)."""
    if image is not None:   # 표지 그림은 장 계획만으로 그림 — 본문과 동시에
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(image, cover_prompt(clean_plan(plan)))
            out = build(key, client, topic, brief, plan, base_url=base_url, material=material, model=model, exa=exa, images=images)
            try:
                got = fut.result()
                out["deck"]["cover"] = {k: got[k] for k in ("img", "w", "h", "model") if k in got}
            except Exception as e:   # 그림이 틀어져도 장은 그대로
                out["cover_error"] = f"{type(e).__name__}: {e}"[:200]
        return out
    plan = clean_plan(plan)
    t0 = time.time()
    secs = [{"title": s["title"], "shape": "주인공 글", "source": s["source"] if s["source"] == "web" else "ai", "query": s["query"]} for s in plan["slides"]]
    mat = deep_mode.gather(key, {"sections": secs}, base_url=base_url, exa=exa) if any(s["source"] == "web" for s in secs) else {"sources": [], "materials": [None] * len(secs)}
    who = (brief or {}).get("듣는 사람")
    system = WRITER.format(audience=who if who and who != deep_mode.AUTO else "처음 보는 동료", today=deep_mode.today())
    images = list(images or [])
    r = client.chat.completions.create(model=model, max_tokens=8000, messages=see.attach([
        {"role": "system", "content": system}, {"role": "user", "content": f"[주제] {topic}\n[질문지 답]\n{brief_text(brief)}\n\n" + material_text(plan, mat, material, len(images)) + "\n\n장마다 써서 JSON 하나로."}], images))
    got = (deep_mode.parse_json(r.choices[0].message.content or "") or {}).get("slides") or []
    slides, missing = [], []
    for i, s in enumerate(plan["slides"]):   # 제목이 조금 바뀌어 와도 차례로 맞춤
        g = got[i] if i < len(got) and isinstance(got[i], dict) else {}
        one = clean_slide(g, s["title"], s.get("point") or "", first=i == 0, last=i == len(plan["slides"]) - 1)
        if one.pop("_empty", False):
            missing.append(s["title"])
        slides.append(one)
    return {"deck": {"title": plan["title"], "slides": slides, "sources": mat["sources"]}, "model": model, "elapsed": round(time.time() - t0, 1), "missing": missing}


def clean_slide(g: dict, title: str = "", point: str = "", *, first: bool = False, last: bool = False) -> dict:
    """모델이 쓴 장 하나 → 칠판이 그리는 장(`Editor.slidePieces`). 모양에 쓸 것이 없으면 글머리로, 첫 장 = 표지. `_empty` = 화면 글이 없었음."""
    g = g if isinstance(g, dict) else {}
    bullets = [str(b).strip() for b in g.get("bullets") or [] if str(b).strip()][:5]
    one = {"title": str(g.get("title") or title).strip()[:60], "bullets": bullets or [point], "notes": str(g.get("notes") or "").strip(), **({"_empty": True} if not bullets else {})}
    layout = str(g.get("layout") or "")
    nums = [{"value": str(x.get("value") or "").strip()[:14], "label": str(x.get("label") or "").strip()[:60]} for x in g.get("numbers") or [] if isinstance(x, dict) and str(x.get("value") or "").strip()][:3]
    steps = [str(x).strip()[:60] for x in g.get("steps") or [] if str(x).strip()][:5]
    msg = str(g.get("message") or "").strip()[:80]
    if first:
        layout = "표지"
    elif layout == "숫자" and len(nums) < 2 or layout == "단계" and len(steps) < 2 or layout == "한마디" and not msg or layout not in LAYOUTS:
        layout = "마무리" if last else "글머리"   # 그 모양에 쓸 것이 없으면 글머리로
    one["layout"] = layout
    one.update({"numbers": nums} if layout == "숫자" else {"steps": steps} if layout == "단계" else {"message": msg} if layout == "한마디" else {})
    return one


REDO_SLIDE = """너는 발표 자료의 **장 하나**를 고치는 사람이다. 아래 [지금 장](JSON)과 사용자 말을 보고 답한다. 오늘: {today}.
- JSON 하나만: {{"reply": "말풍선에 보일 짧은 답", "slide": 고친 장 전체 또는 null}}
- 고쳐·바꿔·줄여·늘려·더해·쉽게·모양 바꿔 달라는 말이면 slide에 **고친 장 전체**(모양은 지금 장과 같은 칸: title, layout, bullets, numbers?, steps?, message?, notes). 말하지 않은 곳은 그대로.
  layout = 표지|글머리|숫자|단계|한마디|마무리 — 숫자 = numbers 2~3개({{"value": "8자 안팎", "label"}}) · 단계 = steps 3~5줄 · 한마디 = message 25자 안팎 · 어느 모양이든 bullets도(2~4줄, 25자 안팎).
  지금 장·[장 안 글]에 없는 숫자·사실은 지어내지 않는다(출처 번호 [n]은 그대로 둠). 그때 reply는 무엇을 바꿨는지 한 문장.
- 묻는 말이면 slide는 null, reply에 답(짧게, 결론 먼저).
- 그림이 함께 오면 그 그림도 장 안의 재료다."""


def redo_slide(client, slide: dict, ask: str, *, text: str = "", deck: str = "", history=None, model: str = WRITER_MODEL, images=None) -> dict:
    """장 하나 고치기(발표 자료 말풍선, 2026-10-28) — 지금 장(`slide`, 칠판 프레임에 적어 둔 것) + 말 → {"content", "edit"?(고친 장 — `clean_slide`), "model", "elapsed"}.
    text = 그 프레임 안의 글(손으로 고친 것까지), history = 그 말풍선 앞 대화."""
    t0 = time.time()
    first, last = slide.get("layout") == "표지", slide.get("layout") == "마무리"
    turns = [{"role": m["role"], "content": str(m.get("content", ""))} for m in history or [] if isinstance(m, dict) and m.get("role") in ("user", "assistant")][-8:-1]
    user = (f"[발표] {deck}\n" if deck else "") + "[지금 장]\n" + json.dumps({k: v for k, v in slide.items() if k != "small"}, ensure_ascii=False)[:6000] + (
        f"\n\n[장 안 글 — 손으로 고친 것 포함]\n{text[:6000]}" if text.strip() else "") + see.note(len(images or [])) + f"\n\n[사용자]\n{ask[:1000]}"
    r = client.chat.completions.create(model=model, max_tokens=3000, messages=see.attach(
        [{"role": "system", "content": REDO_SLIDE.format(today=deep_mode.today())}] + turns + [{"role": "user", "content": user}], images))
    d = deep_mode.parse_json(r.choices[0].message.content or "")
    if not isinstance(d, dict):
        return {"content": (r.choices[0].message.content or "").strip(), "model": model, "elapsed": round(time.time() - t0, 1)}
    out = {"content": str(d.get("reply") or "").strip(), "model": model, "elapsed": round(time.time() - t0, 1)}
    if isinstance(d.get("slide"), dict):
        new = clean_slide(d["slide"], slide.get("title") or "", (slide.get("bullets") or [""])[0], first=first, last=last)
        new.pop("_empty", None)
        if slide.get("small"):
            new["small"] = True
        out["edit"], out["content"] = new, out["content"] or "이 장을 고쳤어요."
    return out
