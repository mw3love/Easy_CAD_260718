"""웹 칠판 「정리해 줘」 ① — 칠판 자료 → 아티팩트 같은 정리 문서 한 장(HTML, Qt 비의존, `web/server.py`가 부름, §8 항목61 2026-10-19).

데스크톱 「만들기」가 늘 비슷했던 까닭 = AI는 내용 JSON만, 앱이 정해 둔 틀에 끼움. 여기선 AI가 HTML을 직접 써 모양까지 자료에 맞게 고른다
(2026-10-19 실측: 회의록 → 브리핑, 점검 기록 → 지표 카드·그래프 인포그래픽 — 같은 지시문으로 모양이 달라짐).
결과는 칠판의 「문서 카드」(`doc` — 칸 안에 스크립트 없는 iframe)로 붙고, 크게 열어 바로 인쇄·PDF. 「더 짧게」처럼 말하면 앞 문서를 바탕으로 고쳐 씀.
"""
from __future__ import annotations

import html as _html
import re
import time

from easycad.ai import gateway as gw

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
- 마지막에 짧은 「핵심 의견」 한 칸은 넣어도 되지만 작성자 의견임을 밝힌다. 출처 주소가 있으면 각주처럼 작게 남긴다."""

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


def make(client, material: str, ask: str = "", *, prev_html: str = "", model: str = REPORT_MODEL) -> dict:
    """칠판 자료(+요청) → {"html", "title", "model", "elapsed", "tone", "unchecked"}. `prev_html`이 있으면 그 문서를 `ask`대로 고쳐 씀(톤은 말했을 때만 바꿈).
    unchecked = 자료에서 그대로 못 찾은 숫자(`unchecked_numbers` — 서버가 답 글에 알림)."""
    tone = tone_of(ask)
    if prev_html:
        user = REVISE.format(prev=prev_html[:60_000], ask=ask or "더 보기 좋게") + ("\n\n" + tone_line(tone) if tone else "")
    else:
        tone = tone or "calm"
        user = ("[칠판 자료]\n" + (material or "").strip()[:MAX_MATERIAL] + "\n\n" + (f"[요청]\n{ask}\n\n" if ask else "") + tone_line(tone) + "\n\n"
                + "위 자료를 정리한 문서 한 장을 만들어 줘.")
    t0 = time.time()
    r = client.chat.completions.create(model=model, max_tokens=MAX_TOKENS, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    doc = clean_html(r.choices[0].message.content or "")
    if "<" not in doc:
        raise RuntimeError("정리 문서를 만들지 못했어요(HTML이 아닌 답)")
    return {"html": doc, "title": title_of(doc), "model": model, "elapsed": round(time.time() - t0, 1), "tone": tone, "unchecked": unchecked_numbers(doc, material)}
