"""웹 칠판 「정리해 줘」 ① — 칠판 자료 → 아티팩트 같은 정리 문서 한 장(HTML, Qt 비의존, `web/server.py`가 부름, §8 항목61 2026-10-19).

데스크톱 「만들기」가 늘 비슷했던 까닭 = AI는 내용 JSON만, 앱이 정해 둔 틀에 끼움. 여기선 AI가 HTML을 직접 써 모양까지 자료에 맞게 고른다
(2026-10-19 실측: 회의록 → 브리핑, 점검 기록 → 지표 카드·그래프 인포그래픽 — 같은 지시문으로 모양이 달라짐).
결과는 칠판의 「문서 카드」(`doc` — 칸 안에 스크립트 없는 iframe)로 붙고, 크게 열어 바로 인쇄·PDF. 「더 짧게」처럼 말하면 앞 문서를 바탕으로 고쳐 씀.
"""
from __future__ import annotations

import html as _html
import json
import re
import time

from easycad.ai import gateway as gw, see

REPORT_MODEL = "claude-opus-5-5"   # 실측 40~55초·약 $0.10~0.15 — sonnet-5-5는 22초·$0.04지만 조금 단순(계획서 §8 항목61)
MAX_MATERIAL = 40_000              # 칠판 자료 상한(자)
MAX_TOKENS = 16_000

SYSTEM = """너는 칠판에 흩어진 메모·검색 결과·회의록·표를 읽고, 그 내용에 가장 알맞은 형식으로 정리한 문서 한 장을 만드는 편집 디자이너다.
출력은 완결된 HTML 문서 하나뿐이다(설명·코드펜스 없이 <!doctype html>로 시작). <title>에 문서 제목을 쓴다.
- 내용을 먼저 이해하고 형식을 고른다: 결정·할 일이 핵심이면 브리핑 보고서, 숫자·비교가 핵심이면 인포그래픽(막대·도넛은 인라인 SVG), 시간 흐름이면 타임라인,
  개념·관계면 구조도 등. 매번 같은 틀을 쓰지 않는다. 큰 숫자·카드·표·그래프로 한눈에 읽히게.
- A4 세로로 인쇄해도 손색없게: @page { size: A4; margin: 14mm }, 화면에서도 A4 폭(210mm) 가운데 정렬, 흰 바탕. 1~2쪽 안에.
- 스크립트·외부 파일·외부 글꼴·외부 그림을 쓰지 않는다(인터넷 없이 열려야 함). 글꼴은 'Pretendard','Malgun Gothic',sans-serif.
- 한국어. 칠판에 없는 사실은 지어내지 않는다. 계산한 값(합계·비율)은 자료에서 계산했다고 작게 밝힌다.
- 칠판에 없는 연결·담당·계산 표를 그림이나 표에도 지어 넣지 않는다(흐름도의 담당 칸, 자료에 없는 값으로 만든 표 등 — 비어 있으면 비어 있다고 쓴다).
- 마지막에 짧은 「핵심 의견」 한 칸은 넣어도 되지만 작성자 의견임을 밝힌다. 출처 주소가 있으면 각주처럼 작게 남긴다."""

# 「읽기용」(2026-11-05 사용자 — /pic A/B의 「C」): 모양은 모델이 고르고 지시문엔 놓이는 자리 규칙만 + 결론 맨 위·용어 풀이·구조는 그림으로.
# 위 SYSTEM = 「발표용」(화려·전문적 — 발표하기 좋음), 이쪽 = 정돈·차분(혼자 읽기 좋음). 당분간 둘 다 만들어 써 보고 하나로 합칠지 정한다(남긴 쪽 세기 `python web/usage.py`).
# ⚠ 좋은 디자인의 모양을 여기 베껴 적지 말 것 — 그날 모양으로 굳는다(/pic 교훈). A/B 경위: docs/history/2026-11.md
SYSTEM_READ = """너는 칠판에 흩어진 메모·검색 결과·회의록·표를 읽고, 읽는 사람이 바로 이해하도록 정리한 문서 한 장을 만든다.
출력은 완결된 HTML 문서 하나뿐이다(설명·코드펜스 없이 <!doctype html>로 시작). <title>에 문서 제목을 쓴다.
디자인(배치·색·글꼴 크기·형식)은 이 자료에 가장 알맞게 네가 정한다. 아래는 이 문서가 놓이는 자리 때문에 꼭 지킬 것뿐이다.

[놓이는 자리]
- 칠판 위 카드(스크립트가 돌지 않는 틀)로 보이고, 크게 열어 A4 세로로 인쇄·PDF로 저장한다. @page { size: A4; margin: 14mm }, 화면에서도 A4 폭 안에. 1~2쪽 안에.
- 스크립트·외부 파일·외부 글꼴·외부 그림을 쓰지 않는다(인터넷 없이 열려야 함). 글꼴은 한글이 있는 것만 — 목록 끝에 'Malgun Gothic','Apple SD Gothic Neo',sans-serif.
- 정지된 문서다: 버튼·탭·접기·마우스 올리기처럼 누르거나 움직이는 것을 쓰지 않고, 누르는 것처럼 보이는 모양도 그리지 않는다. 숨길 내용은 펼쳐서 보인다.
- 인쇄하는 문서라 넓은 면을 진한 색으로 채우지 않는다.
- body에 word-break: keep-all(한글이 낱말 중간에서 줄바꿈되지 않게). 칸 높이를 고정하지 않는다(글이 넘쳐 겹치지 않게 내용만큼 늘게).

[내용]
- 이 문서의 결론(가장 중요한 한 문장)을 맨 위에, 문서에서 가장 눈에 띄게 둔다.
- 처음 보는 사람이 모를 용어는 그 자리에서 한 줄로 풀어 쓴다.
- 흐름·단계·시간 순서·추이·갈래·비교처럼 구조가 있는 내용은 글이나 표 대신 그 구조를 그대로 그린다(흐름도·타임라인·그래프·나란한 칸 — 인라인 SVG나 HTML로). 읽는 사람이 글을 따라가지 않고 한눈에 보게. 몇 개 안 되는 숫자는 숫자 그대로 쓰고, 꾸미려고 넣는 그림은 쓰지 않는다. 칠판에 없는 연결·담당은 그림에도 지어 넣지 않는다.
- 한국어. 칠판에 없는 사실은 지어내지 않는다. 계산한 값(합계·비율)은 자료에서 계산했다고 작게 밝힌다. 값을 옮기거나 계산할 때 그 값의 뜻(무엇의 평균인지 등)이 결론과 맞는지 확인한다.
- 마지막에 짧은 「핵심 의견」 한 칸은 넣어도 되지만 작성자 의견임을 밝힌다. 출처 주소가 있으면 각주처럼 작게 남긴다."""

STYLES = {"present": "발표용", "read": "읽기용"}   # 차례 = 칠판에 놓는 차례(왼쪽부터)
_STYLE_WORDS = {"present": r"발표용|발표\s*(?:자료\s*)?(?:느낌|스타일)", "read": r"읽기용|읽기\s*(?:좋|느낌|스타일)|차분하게"}


def style_of(ask: str) -> str:
    """요청 속 「발표용」·「읽기용」 → 그 하나만(없거나 둘 다면 "" = 둘 다 만듦)."""
    hits = [k for k, rx in _STYLE_WORDS.items() if re.search(rx, ask or "")]
    return hits[0] if len(hits) == 1 else ""


# 찾아 보태기(2026-11-09 사용자 — AI 칩 「문서」): 칠판 자료만으론 빈약한 사실(숫자·통계·날짜·정의·최근 동향)이 있을 때만 찾을 질문을 뽑음.
# 회의록·할 일처럼 칠판 내용 자체가 주제면 빈 목록 — 늘 검색하면 일반론이 끼어 문서를 망침(비교 1회차: 취재 한 판이 회의록에 일반론을 채움).
# 찾기는 서버가 취재 한 판 재료 모으기(`deep_mode.gather`)로 — 여기선 질문만(deep_mode가 이 모듈을 불러 순환을 피함).
GAP_MODEL = "claude-sonnet-5-5"
MAX_GAPS = 3
GAPS = """너는 문서 편집자다. 아래 [칠판 자료]로 [요청]의 문서 한 장을 쓰려 한다. 오늘: {today}.
자료에 없어서 문서가 빈약해지는 사실(숫자·통계·날짜·정의·최근 동향)이 있으면, 밖에서 찾아볼 질문을 최대 3개 고른다.
- 자료만으로 충분하면 빈 목록: 회의록·할 일·내 생각 정리처럼 칠판 내용 자체가 주제일 때, 자료에 이미 숫자·근거가 있을 때.
- 자료 속 사람·회의·우리 조직 일정처럼 밖에서 찾을 수 없는 것은 고르지 않는다.
- 질문은 그것만 읽어도 통하는 한국어 한 문장(대상·기간·단위를 넣음).
- source: 한국 공공 통계·법령·날씨처럼 공공 데이터로 답할 것은 "kr", 나머지는 "web".
JSON만: {{"queries": [{{"q": "…", "source": "web"}}]}}"""


def find_gaps(client, material: str, ask: str = "", *, model: str = GAP_MODEL, today: str = "") -> list:
    """칠판 자료로 문서를 쓸 때 밖에서 찾을 질문 [{"q", "source"}](최대 3개) — 충분하면 []. 틀어지면 [](문서는 칠판 자료만으로)."""
    if client is None or not str(material or "").strip():
        return []
    try:
        r = client.chat.completions.create(model=model, max_tokens=600, messages=[
            {"role": "system", "content": GAPS.format(today=today or time.strftime("%Y-%m-%d"))},
            {"role": "user", "content": f"[요청]\n{ask or '정리한 문서 한 장'}\n\n[칠판 자료]\n{material.strip()[:MAX_MATERIAL]}"}])
        m = re.search(r"\{.*\}", r.choices[0].message.content or "", re.S)
        qs = (json.loads(m.group(0)) if m else {}).get("queries") or []
    except Exception:
        return []
    out = [{"q": str(q["q"]).strip()[:300], "source": "kr" if q.get("source") == "kr" else "web"} for q in qs if isinstance(q, dict) and str(q.get("q") or "").strip()]
    return out[:MAX_GAPS]


def found_text(found: dict | None) -> str:
    """찾아 보탠 자료 → 문서 지시에 붙일 글(없으면 "")."""
    if not found or not str(found.get("text") or "").strip():
        return ""
    src = "\n".join(f"[{s['n']}] {s.get('title') or s.get('url')} — {s.get('url') or ''}" for s in found.get("sources") or [])
    return ("[찾아 보탠 자료 — 칠판 밖에서 찾음. 여기서 가져온 사실엔 그 [n] 번호를 달고, 문서 끝에 출처(번호·제목·주소)를 작게 남긴다]\n"
            + found["text"].strip()[:20_000] + ("\n\n[출처 번호]\n" + src if src else ""))


REVISE = """아래는 앞서 만든 정리 문서다. 사용자의 요청대로 고친 완결된 HTML 문서 하나만 다시 출력한다(같은 규칙 — 스크립트·외부 파일 없음, A4 인쇄).

[앞 문서]
{prev}

[고칠 점]
{ask}"""

_BAD = [re.compile(p, re.I | re.S) for p in (
    r"<script\b.*?</script\s*>", r"<script\b[^>]*/?>", r"<iframe\b.*?</iframe\s*>", r"<(object|embed)\b.*?>",
    r"<link\b[^>]*>", r"<meta\b[^>]*http-equiv[^>]*>")]
_ON_ATTR = re.compile(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_JS_URL = re.compile(r"(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2", re.I)


def clean_html(text: str) -> str:
    """AI가 쓴 HTML → 칠판에 둘 수 있는 것: 코드펜스 벗기고 스크립트·iframe·외부 연결·이벤트 속성 지움(카드도 스크립트 없는 iframe이지만 한 번 더)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:html)?\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    i = t.lower().find("<!doctype")
    if i < 0:
        i = t.lower().find("<html")
    if i > 0:
        t = t[i:]
    for rx in _BAD:
        t = rx.sub("", t)
    t = _ON_ATTR.sub("", t)
    return _JS_URL.sub(r'\1=\2#\2', t)


def title_of(doc: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", doc or "", re.I | re.S) or re.search(r"<h1[^>]*>(.*?)</h1>", doc or "", re.I | re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()[:80] if m else "정리 문서"


def plain_text(doc: str, limit: int = 4000) -> str:
    """문서 HTML → 쉬운 글(찾기·대화 근거용)."""
    t = re.sub(r"<(style|script|head)\b.*?</\1\s*>", " ", doc or "", flags=re.I | re.S)   # 머리(제목)는 카드 제목과 겹쳐 뺌
    t = re.sub(r"<br\s*/?>|</(p|div|li|h[1-6]|tr|td|th)>", "\n", t, flags=re.I)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
    lines = (re.sub(r"[ \t]+", " ", ln).strip() for ln in t.split("\n"))
    return "\n".join(ln for ln in lines if ln)[:limit]


# 톤 — 웹 칠판 딥모드 판과 같은 색 넷(`web/src/next/deepstyle.js` — 2026-10-25 사용자 「정리 문서와 딥모드는 장점을 서로 바꿔 쓰기」: 한 칠판에서 두 결과가 어울리게).
# 기본 = 차분, 요청에 톤 이름(신문·남색·파랑·차분)이 있으면 그 톤. 시험 `test_part61_report`가 deepstyle.js와 맞춰 봄
TONES = {
    "calm": {"name": "차분", "main": "#27272a", "accent": "#b4532f", "muted": "#71717a", "line": "#da7756"},
    "news": {"name": "신문", "main": "#18181b", "accent": "#9b1c1c", "muted": "#57534e", "line": "#3f3f46"},
    "magazine": {"name": "남색", "main": "#1f3a4d", "accent": "#1f5f7a", "muted": "#6b7280", "line": "#1f5f7a"},
    "info": {"name": "파랑", "main": "#2a78d6", "accent": "#2a78d6", "muted": "#64748b", "line": "#2a78d6"},
}


def tone_of(ask: str) -> str:
    """요청 속 톤 이름 → 톤 키(없으면 "")."""
    for k, t in TONES.items():
        if re.search(t["name"] + r"\s*(톤|색|으로|로)", ask or ""):
            return k
    return ""


def tone_line(key: str) -> str:
    t = TONES.get(key) or TONES["calm"]
    return (f"[색 — 칠판 「{t['name']}」 톤(딥모드 판과 같은 색)] 주색 {t['main']} · 강조 {t['accent']} · 흐린 글 {t['muted']} · 선·테두리 {t['line']}. "
            "제목 띠·숫자 카드·그래프를 이 색들(과 그 옅은 색)로만, 흰 바탕.")


# 숫자 검사(딥모드의 「숫자마다 출처」를 정리 문서에도 — 같은 날): 문서에 쓴 숫자 중 칠판 자료에 그대로 없는 것. 계산한 값(합계·비율)일 수 있어 막지 않고 답에 알림
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _nums(text: str) -> set:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(text or "") if len(n.replace(",", "")) >= 2}


# 시각·날짜는 모양만 바꿔 쓰는 일이 많아(14:00 ↔ 오후 2시, 2026-07-31 ↔ 2026.7.31 ↔ 7월 31일) 지어낸 숫자 검사에서 뺌(2026-10-26 점검 — 회의록 「오후 2시」·기사 날짜가 다 걸렸음)
_TIME = re.compile(r"\d{1,2}:\d{2}")
_YMD = re.compile(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})(?:\s*[.\-/월]\s*(\d{1,2}))?")
_MD = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:[./]|월\s*)\s*(\d{1,2})(?![\d.])")


def _dates(text: str) -> tuple:
    """자료 속 날짜 — (년, 월) 모음과 (월, 일) 모음."""
    ym, md = set(), set()
    for y, m, d in _YMD.findall(text or ""):
        ym.add((int(y), int(m)))
        if d:
            md.add((int(m), int(d)))
    md |= {(int(m), int(d)) for m, d in _MD.findall(text or "")}
    return {(y, m) for y, m in ym if 1 <= m <= 12}, {(m, d) for m, d in md if 1 <= m <= 12 and 1 <= d <= 31}


def _drop_dates(text: str, material: str) -> str:
    """문서 글에서 시각, 그리고 자료에 있는 날짜를 지움(남은 숫자만 검사)."""
    ym, md = _dates(material)
    text = _TIME.sub(" ", text)
    text = _YMD.sub(lambda m: " " if (int(m[1]), int(m[2])) in ym and (not m[3] or (int(m[2]), int(m[3])) in md) else m[0], text)
    return _MD.sub(lambda m: " " if (int(m[1]), int(m[2])) in md else m[0], text)


def unchecked_numbers(doc: str, material: str, limit: int = 8) -> list:
    """정리 문서 글의 두 자리 이상 숫자 중 자료에 없는 것(나온 차례, 겹침 없이) — 자료가 비면 [](견줄 게 없음). 시각·자료에 있는 날짜는 안 셈."""
    if not str(material or "").strip():
        return []
    have, out = _nums(material), []
    for n in _NUM.findall(_drop_dates(plain_text(doc, 60_000), material)):
        k = n.replace(",", "").rstrip(".")
        if len(k) >= 2 and k not in have and n not in out:
            out.append(n)
    return out[:limit]


def make(client, material: str, ask: str = "", *, prev_html: str = "", model: str = REPORT_MODEL, images=None, style: str = "present", found: dict | None = None) -> dict:
    """칠판 자료(+요청) → {"html", "title", "model", "elapsed", "tone", "unchecked", "style"}. `prev_html`이 있으면 그 문서를 `ask`대로 고쳐 씀(톤은 말했을 때만 바꿈).
    unchecked = 자료에서 그대로 못 찾은 숫자(`unchecked_numbers` — 서버가 답 글에 알림). images = 칠판 그림(`see` — 새로 쓸 때만, 고쳐 쓰기는 앞 문서가 재료).
    style = "present"(발표용 — 기본 톤 차분) / "read"(읽기용 — 색은 모델이 고르고 톤은 말했을 때만).
    found = 서버가 찾아 보탠 자료 {"text", "sources": [{n, title, url}]}(새로 쓸 때만 — `find_gaps` → `deep_mode.gather`)."""
    style = style if style in STYLES else "present"
    tone = tone_of(ask)
    images = [] if prev_html else list(images or [])
    if prev_html:
        user = REVISE.format(prev=prev_html[:60_000], ask=ask or "더 보기 좋게") + ("\n\n" + tone_line(tone) if tone else "")
    else:
        tone = tone or ("calm" if style == "present" else "")
        extra = found_text(found)
        user = ("[칠판 자료]\n" + (material or "").strip()[:MAX_MATERIAL] + see.note(len(images)) + "\n\n" + (extra + "\n\n" if extra else "") + (f"[요청]\n{ask}\n\n" if ask else "") + (tone_line(tone) + "\n\n" if tone else "")
                + "위 자료를 정리한 문서 한 장을 만들어 줘.")
    t0 = time.time()
    r = client.chat.completions.create(model=model, max_tokens=MAX_TOKENS, messages=see.attach([{"role": "system", "content": SYSTEM_READ if style == "read" else SYSTEM}, {"role": "user", "content": user}], images))
    doc = clean_html(r.choices[0].message.content or "")
    if "<" not in doc:
        raise RuntimeError("정리 문서를 만들지 못했어요(HTML이 아닌 답)")
    return {"html": doc, "title": title_of(doc), "model": model, "elapsed": round(time.time() - t0, 1), "tone": tone, "unchecked": unchecked_numbers(doc, material + ("\n" + found["text"] if not prev_html and found and found.get("text") else "")), "style": style}
