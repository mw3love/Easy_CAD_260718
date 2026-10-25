"""웹 칠판 「움직이는 카드」(§8 항목66 4단계, 2026-10-25) — 원리 하나를 직접 만져 보는 HTML 한 장(스크립트 됨). Qt 비의존, 서버 `/api/chat`이 부른다.

- 쓰는 곳 둘: 딥모드 원리 꼭지(`deep_mode.build`가 기자 본문과 동시에) · 대화창 「+ › 움직이는 카드」(하나만 따로).
- 모델 = gpt-6.1-sol(4-0 실측 — 한 장 약 45cr·56초, 셋 중 가장 깔끔·「알아보는 물건」이 좋음. opus는 실제 숫자를 더 잘 쓰지만 약 190cr·겹침,
  sonnet은 글 한도를 생각에 다 써 끊긴 적 있음). sol이 재료 숫자를 안 쓰던 것은 지시문 「기준 값은 재료 숫자로」로 보탬.
- 칠판은 이 HTML을 믿지 않는 글로 다룬다 — 스크립트만 켠 칸(sandbox + CSP, `web/src/next/livecard.js`)에서만 돎. 여기선 모양만 다듬고 크기만 막음.
실측 도구: `tools/livecard_probe.py`(지시문을 여기와 맞춰 둘 것).
"""
from __future__ import annotations

import re
import time

from . import gateway as gw

LIVE_MODEL = "gpt-6.1-sol"
LIVE_MAX = 200_000   # 칠판 `livecard.js` `LIVE_MAX`와 같게(넘으면 칠판이 안 띄움)
MAX_TOKENS = 16_000
MAX_MAT = 2500       # 재료 글 꼭지 하나 상한(자) — 공공 데이터 원문은 1만 자가 넘음
# 「움직이는 카드」 이름표를 단 채 바로 앞 카드 뒤에 이런 말 = 새 카드가 아니라 그 카드 고치기(아이콘 `board_icon.FOLLOW_WORDS`와 같은 생각)
FOLLOW_WORDS = re.compile(r"바꿔|바꾸|고쳐|고치|크게|작게|넣어|추가|빼|지워|없애|느리|빠르|천천|색|글자|글씨|단순|간단|자세|대신|다시|더\s|덜\s")

SYSTEM = """너는 「웹 칠판」의 「움직이는 카드」를 만든다 — 개념이 원리대로 움직이는 작은 장치 한 장(HTML 한 파일, 스크립트 됨).
독자: {audience}. 목표: 직접 만져 보고 원리를 빠르게 이해. 쉬운 우리말, 짧은 문장. 오늘은 {today}.

출력은 완결된 HTML 문서 하나뿐(설명·코드펜스 없이 <!doctype html>로 시작). <title>에 카드 제목.

틀:
- 칠판 위 카드 칸 하나를 꽉 채운다 — 기준 가로 720 × 세로 480 CSS px, 칸 크기가 바뀌면 따라 늘고 줄음(100vw × 100vh). **스크롤·넘침 없음, 글·단추가 서로 겹치지 않게.** 흰 바탕, 글꼴 'Pretendard','Malgun Gothic',sans-serif.
- 네 구석: 왼쪽 위 = 「그림 1」 + 카드 제목, 오른쪽 위 = 실시간 값(조작하면 바뀌는 숫자 1~3개), 왼쪽 아래 = 조작 안내 한 줄(「막대를 끌어 보세요」처럼), 맨 아래 = 지금 보이는 것이 무슨 뜻인지 설명 한 줄(조작에 따라 바뀜).
- 가운데 = **알아보는 물건** — 상자·화살표 도식이 아니라 그 개념이 실제로 생긴 모양(인라인 SVG 또는 canvas).
- 조작은 1~2개(슬라이더·버튼·끌기). 처음 열면 이미 뜻 있는 상태가 보인다(빈 화면 금지). 저절로 도는 움직임은 없어도 되고, 있으면 조작하는 순간 멈춘다.

숫자:
- 화면의 모든 숫자는 스크립트 안 한 곳(상태 하나 + 계산 함수 하나)에서 나와 그림과 값 칸이 늘 같다.
- **재료에 이 원리에 맞는 실제 숫자(규격·통계)가 있으면 그것을 처음 상태(기준 값)로 쓰고**, 그 옆에 출처 번호 [n](재료 머리 번호 그대로). 조작해서 바꾼 값은 「예시 값」이라고 밝힌다.
- 재료에 없는 사실 숫자는 지어내지 않는다 — 그럴 땐 처음부터 「예시 값」.

금지(칠판이 막는다 — 쓰면 카드가 깨짐): 외부 주소(스크립트·글꼴·그림·fetch·링크), localStorage·sessionStorage·cookie, alert·confirm·prompt, window.parent·window.top, form 전송, 새 창.
크기: 40KB 안."""

REVISE = """아래는 앞서 만든 움직이는 카드다. 사용자의 요청대로 고친 완결된 HTML 문서 하나만 다시 출력한다(같은 규칙 — 기준 720×480·넘침 없음·외부 주소 없음).

[앞 카드]
{prev}

[고칠 점]
{ask}"""


def today() -> str:
    t = time.localtime()
    return "%d년 %d월 %d일" % (t.tm_year, t.tm_mon, t.tm_mday)


def clean(text: str) -> str:
    """AI 답 → 카드 HTML: 코드펜스 벗기고 doctype(없으면 <html>)부터. 스크립트는 그대로(그게 카드) — 막기는 칠판 틀이 함."""
    t = gw.strip_code_fence(text or "").strip()
    low = t.lower()
    i = low.find("<!doctype")
    if i < 0:
        i = low.find("<html")
    if i > 0:
        t = t[i:]
    j = t.lower().rfind("</html>")
    if j >= 0:
        t = t[:j + 7]
    return t


def title_of(doc: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", doc or "", re.I | re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()[:80] if m else ""


def section_prompt(plan: dict, mat: dict, idx: int) -> str:
    """딥모드 판의 원리 꼭지 하나 — 판 전체 재료(숫자 기준 값을 찾도록)와 출처 번호를 같이."""
    secs = plan.get("sections") or []
    s = secs[idx]
    lines = [f"[지면] {plan.get('title')} — {plan.get('headline')}", "",
             f"[이 카드 꼭지] {s.get('title')}\n   독자의 질문: {s.get('question')}", "",
             "[판의 다른 꼭지 — 겹치지 않게] " + " · ".join(x.get("title", "") for j, x in enumerate(secs) if j != idx), "", "[재료]"]
    for i, x in enumerate(secs):
        m = (mat.get("materials") or [None] * len(secs))[i]
        if m and m.get("text"):
            lines.append(f"({x.get('title')})\n" + m["text"][:MAX_MAT])
    lines.append("\n[출처 번호]\n" + ("\n".join(f"[{x['n']}] {x['title']} — {x['url']}" for x in mat.get("sources") or []) or "(없음)"))
    return "\n".join(lines) + "\n\n이 꼭지의 움직이는 카드 HTML 하나를 써 줘."


def make(client, ask: str, material: str = "", *, prev_html: str = "", audience: str = "처음 보는 사람", model: str = LIVE_MODEL, user: str = "") -> dict:
    """요청(+ 칠판 재료 글) → {"html", "title", "model", "elapsed"}. `prev_html`이 있으면 그 카드를 `ask`대로 고쳐 씀, `user` = 다 짜 둔 요청 글(딥모드)."""
    if prev_html:
        content = REVISE.format(prev=prev_html[:60_000], ask=(ask or "더 알아보기 쉽게").strip()[:1000])
    elif user:
        content = user
    else:
        if not str(ask or "").strip():
            raise ValueError("무엇을 움직여 볼지 적어 주세요")
        content = (f"[칠판 재료]\n{material.strip()[:20_000]}\n\n" if material and material.strip() else "") + f"[요청]\n{ask.strip()[:1000]}\n\n이 원리의 움직이는 카드 HTML 하나를 써 줘."
    t0 = time.time()
    r = client.chat.completions.create(model=model, max_tokens=MAX_TOKENS, messages=[
        {"role": "system", "content": SYSTEM.format(audience=audience or "처음 보는 사람", today=today())}, {"role": "user", "content": content}])
    doc = clean(r.choices[0].message.content or "")
    if "<" not in doc or "</html>" not in doc.lower():
        raise RuntimeError("움직이는 카드를 끝까지 만들지 못했어요(HTML이 끊김) — 다시 해 주세요")
    if len(doc) > LIVE_MAX:
        raise RuntimeError("움직이는 카드가 너무 커요 — 더 단순하게 다시 해 주세요")
    return {"html": doc, "title": title_of(doc) or "움직이는 카드", "model": model, "elapsed": round(time.time() - t0, 1)}
