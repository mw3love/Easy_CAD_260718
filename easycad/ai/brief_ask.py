"""딥모드·발표 자료 맞춤 질문(2026-11-06 사용자 「질문이 정해진 것만 나옴 — 프롬프트에 대상을 썼는데 또 물음」).

주제 글을 읽고 ① 이미 말한 것(`known` — 대상·쓰임·꼭 넣을 것…) ② 그 주제에 맞춘 질문 2~4개(`questions`)를 돌려준다.
코드가 직접 쓰는 설정(장 수·그림 장·재료·내용·깊이)은 화면이 따로 묻으니 여기선 묻지 않는다.
대상(독자)은 딥모드 본문이 `brief["누구에게"]`로 읽어서 — 알아들었으면 `audience`, 모르면 첫 질문 이름을 「누구에게」로.
Qt 비의존. 서버 `/api/chat` `kind: deep|slides` `step: 'ask'`가 부름.
"""
from __future__ import annotations

import time

from easycad.ai.deep_mode import parse_json

ASK_MODEL = "claude-sonnet-5-5"   # 짧은 JSON — 몇 초(사용자 「충분한 시간을 가지고 질문을 정리」 → 싼 haiku 대신)
AUDIENCE = "누구에게"
SETTINGS = ("장 수", "그림 장", "재료", "내용", "깊이")   # 화면이 따로 묻는 것(코드가 값으로 씀)
MAX_Q, MAX_OPT, MAX_KNOWN = 4, 4, 6

SYSTEM = """너는 자료를 만들기 전에 사용자에게 짧게 되묻는 편집자다. 아래 [주제 글]을 꼼꼼히 읽는다.
1) known = 주제 글에 **이미 나온 것**(대상·쓰임·상황·꼭 넣을 것·빼 줄 것·말투 등). label은 2~6자, value는 주제 글 표현 그대로 짧게. 없으면 [].
2) audience = 주제 글에서 알 수 있는 대상(독자·듣는 사람). 모르면 null.
3) questions = 이 주제로 좋은 자료를 만들려면 꼭 알아야 하는데 주제 글에 **없는 것만** 2~4개.
   - known에 있는 것은 절대 다시 묻지 않는다(대상을 말했으면 대상을 묻지 않는다).
   - 「누구에게?」 같은 두루뭉술한 질문보다 이 주제에 맞춘 구체적인 질문(예: 「견학 전에 볼 자료인가요, 다녀온 뒤 정리인가요?」).
   - audience가 null이면 첫 질문은 q = "누구에게"로, 이 주제에 맞는 대상 보기를 준다.
   - q는 짧게(20자 안팎), h는 탭에 쓸 이름(2~5자 — 예: 용도·수준·넣을 것), options는 2~4개(각 14자 안팎, 서로 겹치지 않게), 여럿 고를 만하면 multi = true.
   - 다음은 화면이 따로 묻는 설정이라 묻지 않는다: {settings}.
JSON 하나만: {{"known": [{{"label": "", "value": ""}}], "audience": null, "questions": [{{"q": "", "h": "", "options": [""], "multi": false}}]}}"""


def _s(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def clean(raw) -> dict:
    """AI 답 다듬기 — 설정 이름·빈 질문·보기 하나짜리는 뺌, 개수 상한. 질문이 하나도 없으면 ValueError(화면이 고정 질문으로)."""
    if not isinstance(raw, dict):
        raise ValueError("질문 답이 JSON이 아니에요")
    known = [{"label": _s(k.get("label"), 12), "value": _s(k.get("value"), 60)} for k in raw.get("known") or [] if isinstance(k, dict)]
    known = [k for k in known if k["label"] and k["value"] and k["label"] != "주제"][:MAX_KNOWN]   # 주제 = 질문지 머리에 이미 보임
    aud = _s(raw.get("audience"), 60) or None
    qs, seen = [], set()
    for q in raw.get("questions") or []:
        if not isinstance(q, dict):
            continue
        name = _s(q.get("q"), 40).rstrip("?？ ")
        opts = list(dict.fromkeys(o for o in (_s(x, 24) for x in q.get("options") or []) if o and o != "알아서"))[:MAX_OPT]
        if not name or name in SETTINGS or name in seen or len(opts) < 2 or (aud and name == AUDIENCE):
            continue
        seen.add(name)
        qs.append({"q": name, "h": _s(q.get("h"), 8) or name[:6], "options": opts, "multi": bool(q.get("multi"))})   # h = 질문 탭 이름(2026-11-07)
    if not qs:
        raise ValueError("맞춤 질문이 없어요")
    return {"known": known, "audience": aud, "questions": qs[:MAX_Q]}


def ask(client, topic: str, *, material: str = "", model: str = ASK_MODEL) -> dict:
    """주제(+ 칠판에서 고른 자료 앞부분) → {"known", "audience", "questions", "model", "elapsed"}."""
    t0 = time.time()
    user = f"[주제 글]\n{topic.strip()[:2000]}" + (f"\n\n[칠판에서 고른 자료 — 앞부분]\n{material.strip()[:1500]}" if material.strip() else "")
    r = client.chat.completions.create(model=model, max_tokens=1500, messages=[
        {"role": "system", "content": SYSTEM.format(settings="·".join(SETTINGS))}, {"role": "user", "content": user}])
    out = clean(parse_json(r.choices[0].message.content or ""))
    return {**out, "model": getattr(r, "model", None) or model, "elapsed": round(time.time() - t0, 1)}
