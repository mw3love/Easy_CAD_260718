"""PDF → 「한 장 보드」 설계서 JSON(§8 항목53 2단계 → 57 블록 조립식, 2026-10-16 Magic Board) — 옛 「풀어 그리기」(흐름도 하나, §8 항목45)를 대체.

§8 항목57부터 새 보드는 **블록 설계서**(`block-board`, `_BLOCK_FORMAT`): AI가 문서에 맞는 블록(카드·흐름·막대·숫자·그림·표·용어·일정·인용…)과
줄·칸 수(12칸 격자)·크기를 고르고, 앱(`host_board._build_block_board`)이 글 크기를 재서 겹치지 않게 놓는다. 아래 옛 논문 틀(`paper-board`)은
다시 연 옛 보드를 읽고 고치는 데만 쓴다.

AI는 **내용만** 쓴다: 제목·한 줄 요약·세 줄 요약·핵심 개념 카드·작동 흐름도(§8 항목52 설계서 형식)·결과 막대·숫자 카드·논문 속
그림(쪽 번호만 — 그림은 앱이 PDF에서 잘라 붙인다)·용어 풀이·의의와 한계. 칸마다 원문 쪽 번호, 논문에 없는 말은 「논문 밖 맥락」.
배치·색·크기는 앱이 정한다(`host_board._build_paper_board`) — 좌표를 AI에 맡기면 겹친다(계획서 §8 항목51~53 공통 원칙).
시안: Artifact 81avA5GPjgcGjdaLsbcbQR 「④ 논문 보드」(`project/Board.dc.html`).

PDF 글 뽑기·긴 문서 나눠 요약은 옛 `pdf_to_mermaid`의 것을 그대로 쓴다(쪽 번호 [p.N] 유지).

**PyQt 비의존.**
"""
from __future__ import annotations

import json
import re

from easycad.ai import gateway as gw
from easycad.ai.pdf_to_mermaid import (
    SINGLE_PASS_CHARS, extract_pdf_pages,
)
from easycad.fileio.flow_spec import FlowSpecError, parse_spec

BOARD_KIND = "paper-board"   # 옛(§8 항목53) 논문 틀 설계서 표식 — 흐름도 설계서와 가르는 열쇠(`is_board_spec`). 다시 연 옛 보드용으로 남김
BLOCK_KIND = "block-board"   # §8 항목57 블록 조립식 — 새로 만드는 보드는 모두 이것
BLOCK_TYPES = ("text", "list", "cards", "flow", "bars", "numbers", "figure", "table", "terms", "timeline", "quote", "verdict")
BLOCK_SIZES = ("small", "normal", "big")
MAX_BLOCKS = 12
HERO_TYPES = ("text", "list", "cards", "numbers", "quote")   # 주인공(진한 면)이 될 수 있는 블록 — §8 항목58 ②

# [§8 항목57, 2026-10-16] 블록 조립식 — AI가 문서에 맞는 블록 종류·차례·자리(12칸 격자의 줄·칸 수)·크기를 고르고, 앱이 글 크기를 재서
# 겹치지 않게 놓는다(좌표는 앱 — "좌표를 맡기면 겹친다" 원칙 유지). 논문이면 개념·흐름·결과·그림, 회의 자료면 결정·할 일 표·일정처럼.
_BLOCK_FORMAT = """출력 형식 — 아래 JSON 하나만 출력하라(다른 설명 없이, 코드펜스는 있어도 됨).
{{"kind": "block-board",
 "title": "문서 제목(원문 그대로)", "meta": "저자·부서·날짜 등 한 줄(없으면 \\"\\")",
 "subtitle": "처음 보는 사람용 한 문장 요약(60자 안팎)", "highlight": "subtitle 안에서 가장 중요한 짧은 구절(그대로 복사, 없으면 \\"\\")",
 "headline": "이 문서의 핵심을 말하듯 던지는 짧은 문장(25자 안팎, 포스터 문구처럼 — 예: \\"사고 없이, 11월 안에 송신기를 바꾼다\\")",
 "blocks": [ 블록 5~7개, 아래 종류 중 이 문서에 맞는 것만 골라 ] }}

블록 공통 칸: "type", "title"(칸 제목), "pages"(근거 쪽 — "p.3"·"p.2–5"·"p.8 · 표 2", 없으면 ""),
 "row"(몇째 줄, 1부터), "span"(12칸 격자에서 차지할 칸 수 1~12 — 한 줄의 span 합은 12 이하), "size"("small"|"normal"|"big"),
 "hero"(이 보드의 주인공 블록 하나에만 true — text·list·cards·numbers·quote 중 첫 줄에 두는 것. 앱이 진한 면으로 돋보이게 하고 headline을 그 위에 크게 쓴다).
블록 종류별 칸:
- text: "body"(2~4문장)
- list: "items": ["한 줄", ...] 3~6개 (근거가 있으면 줄 끝에 (p.N))
- cards: "items": [{{"name": "이름", "body": "쉬운 설명 1~2문장", "pages": "p.3"}}, ...] 2~6개 — 핵심 개념·주요 항목
- flow: "flow": {{"direction": "TD", "lanes": [], "steps": [{{"id": "s1", "text": "단계(12자 안팎)", "kind": "step"}}, ... 3~9개],
         "links": [{{"from": "s1", "to": "s2", "text": ""}}, ...], "focus": "가장 중요한 단계 id"}} — 일이 진행되는 순서·작동 원리
- bars: "bars": [{{"label": "비교 대상", "value": 27.3, "mine": true}}, ... 3~6개], "note": "막대 읽는 법 한 줄" — 숫자 비교 하나
- numbers: "items": [{{"label": "숫자 이름", "value": "41.8", "note": "한 줄 설명", "pages": "p.1"}}, ... 1~4개] — 꼭 기억할 숫자
- figure: "caption": "무엇을 보여 주는 그림", "page": 3 — 문서 속 대표 그림이 있는 쪽(정수). 앱이 그 쪽에서 그림을 잘라 붙인다
- table: "columns": ["열", ...] 2~5개, "rows": [["칸", ...], ...] 2~8줄 — 할 일·담당·기한, 항목 비교 등
- terms: "items": [{{"term": "용어", "meaning": "쉬운 풀이 한 줄"}}, ...] 3~6개
- timeline: "items": [{{"when": "날짜·단계", "text": "무엇을"}}, ...] 2~6개 — 일정·연혁
- quote: "text": "꼭 남길 한 문장(원문 그대로)", "by": "누가·어디서"
- verdict: "items": [{{"type": "의의"|"한계", "text": "한 문장", "pages": "p.6", "outside": false}}, ...] — 의의와 한계(논문·보고서)

한 장 분량(16:9 한 장에 다 들어가야 한다 — 넘치면 앱이 2장으로 나누는데, 사람들은 한 장을 원한다):
- 블록은 5~7개. 글은 짧게 — text body 120자 이내, list 항목 4개 이내·각 45자 이내, cards 4개 이내·body 50자 이내, table 5줄 이내,
  terms 4개 이내, verdict 4개 이내·각 50자 이내, numbers note 30자 이내. 포스터처럼 핵심만, 긴 설명은 빼고 쪽 번호로 원문을 가리킨다.
- figure는 하나만, flow 단계는 6개 이내.

고르는 규칙:
- 문서 종류에 맞는 블록을 고른다. 논문: cards(핵심 개념)·flow(작동 순서)·bars/numbers(결과)·figure·terms·verdict. 회의록·보고: list(결정한 것)·
  table(할 일·담당·기한)·timeline(일정)·numbers. 매뉴얼·절차: flow·list·table·figure. 맞지 않는 블록은 넣지 말 것.
- 자리: 첫 줄엔 이 문서의 요점(요약 list·cards 등), 가장 중요한 블록은 크게("big" 또는 span 6 이상). flow는 span 4 이상, table은 span 6 이상.
  한 줄에 블록 2~3개(span 합 12)가 보통이다. 가운데에 두고 싶은 것은 그 줄에 혼자 두고 span을 12보다 작게(앱이 가운데로 놓는다).
- 쉬운 한국어로, 전문 용어는 cards·terms에서 풀어 쓴다. 숫자·이름·결과는 문서에 있는 그대로 — 지어내지 말 것.
- 문서에 없는 내용(일반 상식·이후 평가 등)을 쓸 땐 그 항목에 "outside": true(verdict) 또는 pages를 "문서 밖 맥락"으로.
- 사용자 요청이 있으면 그 관점에 맞춰 고르되 형식은 그대로."""

_FORMAT = """출력 형식 — 아래 JSON 하나만 출력하라(다른 설명 없이, 코드펜스는 있어도 됨). 쪽 번호 칸 "pages"는 "p.3"·"p.2–5"·"p.8 · 표 2"처럼.
{{"kind": "paper-board",
 "title": "논문 제목(원문 그대로)", "meta": "저자 외, 연도",
 "one_line": "처음 보는 사람용 한 문장 요약(60자 안팎)", "highlight": "one_line 안에서 가장 중요한 짧은 구절(그대로 복사, 없으면 \\"\\")",
 "three_lines": [{{"text": "요약 한 줄", "pages": "p.1–2"}}, ... 정확히 3개],
 "concepts": [{{"name": "개념 이름", "body": "쉬운 설명 1~2문장", "pages": "p.3"}}, ... 3~4개],
 "flow": {{"title": "어떻게 작동하나", "pages": "p.2–5", "direction": "TD", "lanes": ["묶음 이름", ...],
          "steps": [{{"id": "s1", "text": "단계(12자 안팎)", "lane": "묶음 이름", "kind": "step"}}, ... 4~9개],
          "links": [{{"from": "s1", "to": "s2", "text": ""}}, ...], "focus": "가장 중요한 단계 id"}},
 "results": {{"title": "무엇을 비교했나(단위·높을수록 좋음 등)", "pages": "p.8 · 표 2",
             "bars": [{{"label": "비교 대상", "value": 27.3, "mine": true}}, ...], "note": "막대 읽는 법 한 줄"}},
 "numbers": [{{"label": "숫자 이름", "value": "41.8", "note": "한 줄 설명", "pages": "p.1"}}, ... 0~2개],
 "figure": {{"caption": "그림 1 · 무엇을 보여 주는 그림", "page": 3}},
 "terms": [{{"term": "용어", "meaning": "쉬운 풀이 한 줄"}}, ... 3~5개],
 "verdict": [{{"type": "의의", "text": "한 문장", "pages": "p.6–7", "outside": false}},
             {{"type": "한계", "text": "한 문장", "pages": "p.6"}}, ... 의의 2개·한계 2개 안팎]}}

칸 규칙:
- 쉬운 한국어로, 전문 용어는 concepts·terms에서 풀어 쓴다. 숫자·이름·결과는 논문에 있는 그대로 — 지어내지 말 것.
- 논문에 없는 내용(일반 상식·이후 평가 등)을 쓸 땐 그 항목에 "outside": true(verdict) 또는 pages를 "논문 밖 맥락"으로.
- flow: 논문이 제안한 방법이 작동하는 순서. §흐름도 설계서와 같은 형식 — lanes는 뚜렷한 묶음(예: 인코더·디코더)이 둘 이상일 때만, 아니면 [].
  direction은 4~9단계가 보드 가운데 칸(정사각형에 가까움)에 들어가게 — 보통 "TD".
- results: 논문의 표·그래프에서 가장 중요한 비교 하나(막대 3~6개). 제안한 방법의 막대에 "mine": true. 비교할 숫자가 없으면 "bars": [].
- figure: 논문 전체 구조를 보여 주는 대표 그림이 있는 쪽 번호(정수). 없으면 null.
- 사용자 요청이 있으면 그 관점에 맞춰 고르되 형식은 그대로."""

_BOARD_TEMPLATE = """다음은 문서(PDF)의 내용이다({kind_note}, 각 줄 앞 [p.N]은 원문 쪽 번호).
이 문서를 처음 보는 사람이 한 장으로 이해하도록 「한 장 보드」를 블록으로 짜라. 좌표·색은 앱이 정하니 너는 블록 종류·내용·줄·칸 수·크기만 정한다.
{request_line}
{format}

문서:
{body}
"""

_BLOCK_REFINE_TEMPLATE = """아래는 「한 장 보드」의 블록 설계서다. 지시대로 고쳐라.

```json
{code}
```

지시: {instruction}

규칙:
- 지시와 관계없는 블록·칸은 그대로 둘 것. 원문을 다시 볼 수 없으니 새 숫자·사실을 지어내지 말 것(필요하면 "문서 밖 맥락"으로 표시).
- 배치 지시(「가운데로」·「크게」·「옆으로」·「위로」 등)는 그 블록의 "row"·"span"·"size"를 바꿔서 따를 것 — 가운데에 두려면 그 줄에 혼자 두고
  span을 12보다 작게, 크게 하려면 span을 늘리고 "size": "big". 그 때문에 다른 블록의 row·span이 바뀌는 것은 괜찮다(글은 그대로).
- 블록을 빼거나 더하라는 지시면 blocks에서 빼거나 같은 형식으로 더할 것.
- 독자·말투를 바꾸라는 지시(예: 중학생용으로)면 모든 글 칸을 그 독자에 맞게 다시 쓸 것.
- 고친 전체 설계서를 같은 형식으로 출력하라.

{format}
"""

_REFINE_TEMPLATE = """아래는 논문 「한 장 보드」의 내용 설계서다. 지시대로 고쳐라.

```json
{code}
```

지시: {instruction}

규칙:
- 지시와 관계없는 칸은 그대로 둘 것. 원문을 다시 볼 수 없으니 새 숫자·사실을 지어내지 말 것(필요하면 "논문 밖 맥락"으로 표시).
- 배치·위치·크기(「그림을 가운데」 등)는 앱이 맡으니 무시하고, 글 내용에 대한 지시만 따를 것.
- 독자·말투를 바꾸라는 지시(예: 중학생용으로)면 모든 글 칸(요약·개념·단계·결과 설명·용어·의의와 한계)을 그 독자에 맞게 다시 쓸 것.
- 고친 전체 설계서를 같은 형식으로 출력하라.

{format}
"""


class BoardSpecError(ValueError):
    pass


_SOURCES_NOTE = """
여러 자료(§ 자료마다 이름표): {listing}
- 근거 칸 "pages"는 자료 이름표를 붙여 "A p.3"·"B p.2–4"·"C 사진"처럼 쓴다(이름표 없이 쪽 번호만 쓰지 말 것).
- figure는 {{"caption": ..., "source": "A", "page": 3}}처럼 어느 자료의 몇 쪽인지(그림 자료면 "page": 1).
- 자료끼리 말이 다르면 의의와 한계(verdict)에 그 차이를 적어라."""

MAX_SOURCES = 10   # 한 번에 넣을 자료 수 상한(계획서 §8 항목53 "예: 파일 10개" — 크레딧은 실측 전)


def sources_body(sources) -> tuple[str, list, str]:
    """여러 자료 → (글 본문 — 줄마다 [A p.N], 그림 목록 [(이름표, PIL)], 자료 목록 한 줄). PDF는 글로, 그림은 그림으로.
    `sources` = [{"label", "kind": "pdf"|"image", "name", "path"?, "image"?}]."""
    lines, images, listing = [], [], []
    for s in sources:
        if s["kind"] == "pdf":
            for n, t in extract_pdf_pages(s["path"]):
                lines.append(f"[{s['label']} p.{n}] {t}")
            listing.append(f"{s['label']} = {s['name']}(글)")
        else:
            images.append((s["label"], s["image"]))
            listing.append(f"{s['label']} = {s['name']}(그림으로 첨부)")
    return "\n".join(lines), images, ", ".join(listing)


def generate_board_sources(api_key: str, sources, note: str = "", *, model: str, base_url: str = gw.BASE_URL,
                           progress=None) -> tuple[str, str]:
    """여러 자료(A·B·C — PDF 글 + 그림) → 보드 설계서 하나. 근거는 「A p.3」·「B 사진」. 긴 글은 한 자료 때처럼 묶음별 요약
    (줄 앞 [A p.N] 표시가 남는다). 설계서에 자료 목록(`_sources` — 이름표 → 파일 경로·이름)을 넣어 앱이 그림을 잘라 온다."""
    from easycad.ai.pdf_to_mermaid import CHUNK_CHARS
    sources = list(sources)[:MAX_SOURCES]
    body, images, listing = sources_body(sources)
    used = model
    summarized = False
    if len(body) > SINGLE_PASS_CHARS:
        chunks, cur = [], []
        size = 0
        for ln in body.split("\n"):
            if cur and size + len(ln) > CHUNK_CHARS:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(ln)
            size += len(ln)
        if cur:
            chunks.append(cur)
        parts = []
        for i, ch in enumerate(chunks, start=1):
            if progress:
                progress(f"긴 자료라 나눠 읽는 중 {i}/{len(chunks)}")
            res = gw.call_text_with_fallback(api_key, _SUMMARY_MULTI.format(body="\n".join(ch)), model=model,
                                             base_url=base_url, timeout=120.0)
            parts.append(res.content.strip())
            used = res.model_used
        body, summarized = "\n".join(parts), True
    if progress:
        progress("보드 정리하는 중")
    prompt = build_board_prompt(body or "(글 자료 없음 — 첨부한 그림만 보고 정리)", note, summarized)
    prompt += _SOURCES_NOTE.format(listing=listing)
    res = gw.call_text_with_fallback(api_key, prompt, model=model, base_url=base_url, images=images or None,
                                     timeout=240.0)
    spec = parse_board(res.content)
    spec["_sources"] = {s["label"]: {"name": s["name"], "kind": s["kind"], "path": s.get("path", "")} for s in sources}
    return dump_board(spec), res.model_used or used


_SUMMARY_MULTI = """다음은 여러 자료의 일부다(각 줄 앞 [A p.N]은 자료 이름표와 원문 쪽 번호).
핵심 내용을 글머리표 15줄 이내로 요약하라. 줄마다 끝에 근거를 (A p.N) 형식으로 붙일 것. 자료에 없는 내용은 쓰지 말 것. 요약만 출력하라.

{body}
"""


def is_board_spec(text: str) -> bool:
    t = (text or "").lstrip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
    head = t[:400]
    return t.lstrip().startswith("{") and (f'"{BOARD_KIND}"' in head or f'"{BLOCK_KIND}"' in head)


def is_block_spec(spec: dict) -> bool:
    return spec.get("kind") == BLOCK_KIND


def _pages(v) -> str:
    return str(v or "").strip()


def parse_board(raw: str) -> dict:
    """모델 응답 → 다듬은 설계서 dict. 너그럽게: 코드펜스·앞뒤 말 걷기, 칸이 없으면 빈 칸, 흐름도는 `parse_spec`으로 검사(못 읽으면
    흐름도만 뺌), 막대 값은 숫자만. 제목·한 줄 요약이 둘 다 없으면 BoardSpecError."""
    txt = gw.strip_code_fence(raw)
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b <= a:
        raise BoardSpecError("보드 설계서(JSON)를 찾지 못했어요")
    try:
        d = json.loads(txt[a:b + 1])
    except json.JSONDecodeError as ex:
        raise BoardSpecError(f"보드 설계서(JSON)를 읽지 못했어요: {ex.msg}") from None
    if not isinstance(d, dict):
        raise BoardSpecError("보드 설계서(JSON)가 객체가 아니에요")
    if d.get("kind") == BLOCK_KIND or isinstance(d.get("blocks"), list):
        return _parse_blocks(d)

    def s(v):
        return str(v or "").strip()

    def rows(key, keys, limit):
        out = []
        for v in d.get(key) or []:
            if isinstance(v, dict):
                row = {k: s(v.get(k)) for k in keys}
                if any(row.values()):
                    out.append(row)
        return out[:limit]

    out = {"kind": BOARD_KIND, "title": s(d.get("title")), "meta": s(d.get("meta")), "one_line": s(d.get("one_line")),
           "highlight": s(d.get("highlight"))}
    if not (out["title"] or out["one_line"]):
        raise BoardSpecError("보드 제목·요약이 비어 있어요")
    if out["highlight"] and out["highlight"] not in out["one_line"]:
        out["highlight"] = ""
    out["three_lines"] = rows("three_lines", ("text", "pages"), 3)
    out["concepts"] = rows("concepts", ("name", "body", "pages"), 4)
    flow = d.get("flow")
    out["flow"] = None
    if isinstance(flow, dict) and flow.get("steps"):
        try:
            f = json.loads(parse_spec(json.dumps(flow, ensure_ascii=False)).to_json())
            f["title"] = s(flow.get("title")) or "어떻게 작동하나"
            f["pages"] = _pages(flow.get("pages"))
            out["flow"] = f
        except FlowSpecError:
            out["flow"] = None
    res = d.get("results") if isinstance(d.get("results"), dict) else {}
    bars = []
    for v in res.get("bars") or []:
        if not isinstance(v, dict):
            continue
        try:
            val = float(re.sub(r"[^0-9.\-]", "", str(v.get("value"))) or "x")
        except ValueError:
            continue
        if s(v.get("label")):
            bars.append({"label": s(v.get("label")), "value": val, "mine": bool(v.get("mine"))})
    out["results"] = {"title": s(res.get("title")), "pages": _pages(res.get("pages")), "bars": bars[:6],
                      "note": s(res.get("note"))}
    out["numbers"] = rows("numbers", ("label", "value", "note", "pages"), 2)
    fig = d.get("figure") if isinstance(d.get("figure"), dict) else None
    page = None
    if fig is not None:
        try:
            m = re.search(r"\d+", str(fig.get("page")))   # 첫 숫자 — "p.3–5"를 35쪽으로 읽지 않게
            page = int(m.group()) if m else None
        except ValueError:
            page = None
    out["figure"] = {"caption": s(fig.get("caption")), "page": page} if fig is not None and page else None
    if out["figure"] and s(fig.get("source")):
        out["figure"]["source"] = s(fig.get("source"))
    out["terms"] = rows("terms", ("term", "meaning"), 5)
    verdict = []
    for v in d.get("verdict") or []:
        if isinstance(v, dict) and s(v.get("text")):
            t = s(v.get("type"))
            verdict.append({"type": "한계" if "한계" in t else "의의", "text": s(v.get("text")),
                            "pages": _pages(v.get("pages")),
                            "outside": bool(v.get("outside")) or "논문 밖" in _pages(v.get("pages"))})
    out["verdict"] = verdict[:5]
    _copy_app_keys(d, out)
    return out


_APP_KEYS = ("_pdf", "_pages", "_figure", "_sources")   # 앱이 붙이는 칸(AI에는 안 보냄, 이어 고친 결과에 이어 붙임)


def _copy_app_keys(d: dict, out: dict):
    if str(d.get("_pdf") or "").strip():
        out["_pdf"] = str(d["_pdf"]).strip()
    if d.get("_pages") in ("one", "auto"):   # 결과 막대 「한 장으로」(앱이 붙임, §8 항목53 4단계)
        out["_pages"] = d["_pages"]
    if d.get("_figure") in ("big", "small"):   # 결과 막대 「그림 크게」(앱이 붙임, 2026-10-16)
        out["_figure"] = d["_figure"]
    if isinstance(d.get("_sources"), dict):   # 여러 자료 목록(앱이 붙임)
        out["_sources"] = d["_sources"]


def _num(v):
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v)) or "x")
    except ValueError:
        return None


def _page_no(v):
    m = re.search(r"\d+", str(v if v is not None else ""))   # 첫 숫자 — "p.3–5"를 35쪽으로 읽지 않게
    return int(m.group()) if m else None


def _parse_blocks(d: dict) -> dict:
    """[§8 항목57] 블록 설계서 다듬기 — 모르는 종류·빈 블록은 빼고, 줄·칸 수·크기는 범위 안으로. 블록·제목·요약이 다 없으면
    BoardSpecError."""
    def s(v):
        return str(v or "").strip()

    def items(v, keys, limit):
        out = []
        for x in v or []:
            if isinstance(x, dict):
                row = {k: s(x.get(k)) for k in keys}
                if any(row.values()):
                    out.append(row)
            elif isinstance(x, str) and s(x) and len(keys) == 1:
                out.append({keys[0]: s(x)})
        return out[:limit]

    out = {"kind": BLOCK_KIND, "title": s(d.get("title")), "meta": s(d.get("meta")),
           "subtitle": s(d.get("subtitle") or d.get("one_line")), "highlight": s(d.get("highlight")),
           "headline": s(d.get("headline"))[:60]}
    if out["highlight"] and out["highlight"] not in out["subtitle"]:
        out["highlight"] = ""
    blocks = []
    for i, b in enumerate(d.get("blocks") or []):
        if not isinstance(b, dict) or s(b.get("type")) not in BLOCK_TYPES:
            continue
        t = s(b.get("type"))
        row = _num(b.get("row"))
        row = max(1, int(row)) if row is not None else i + 1
        span = _num(b.get("span"))
        span = int(min(12, max(1, span))) if span is not None else 6
        size = s(b.get("size")) if s(b.get("size")) in BLOCK_SIZES else "normal"
        blk = {"type": t, "title": s(b.get("title")), "pages": _pages(b.get("pages")), "row": row, "span": span, "size": size}
        if t == "text":
            blk["body"] = s(b.get("body"))
            ok = bool(blk["body"])
        elif t == "list":
            blk["items"] = [x["text"] for x in items(b.get("items"), ("text",), 8)]
            ok = bool(blk["items"])
        elif t == "cards":
            blk["items"] = items(b.get("items"), ("name", "body", "pages"), 6)
            ok = bool(blk["items"])
        elif t == "flow":
            flow = b.get("flow") if isinstance(b.get("flow"), dict) else b
            ok = False
            if isinstance(flow, dict) and flow.get("steps"):
                try:
                    keep = {k: flow.get(k) for k in ("direction", "lanes", "steps", "links", "focus") if k in flow}
                    blk["flow"] = json.loads(parse_spec(json.dumps(keep, ensure_ascii=False)).to_json())
                    blk["flow"]["title"] = ""
                    ok = True
                except FlowSpecError:
                    ok = False
        elif t == "bars":
            bars = []
            for v in b.get("bars") or b.get("items") or []:
                if isinstance(v, dict) and s(v.get("label")) and _num(v.get("value")) is not None:
                    bars.append({"label": s(v.get("label")), "value": _num(v.get("value")), "mine": bool(v.get("mine"))})
            blk["bars"], blk["note"] = bars[:6], s(b.get("note"))
            ok = bool(bars)
        elif t == "numbers":
            blk["items"] = items(b.get("items"), ("label", "value", "note", "pages"), 4)
            ok = bool(blk["items"])
        elif t == "figure":
            page = _page_no(b.get("page"))
            blk.update(caption=s(b.get("caption")), page=page)
            if s(b.get("source")):
                blk["source"] = s(b.get("source"))
            ok = bool(page)
        elif t == "table":
            cols = [s(c) for c in (b.get("columns") or []) if s(c)][:5]
            rows = []
            for r in b.get("rows") or []:
                if isinstance(r, list) and any(s(c) for c in r):
                    cells = [s(c) for c in r][:len(cols) or 5]
                    rows.append(cells + [""] * (len(cols) - len(cells)))
            blk["columns"], blk["rows"] = cols, rows[:8]
            ok = bool(cols and rows)
        elif t == "terms":
            blk["items"] = items(b.get("items"), ("term", "meaning"), 6)
            ok = bool(blk["items"])
        elif t == "timeline":
            blk["items"] = items(b.get("items"), ("when", "text"), 6)
            ok = bool(blk["items"])
        elif t == "quote":
            blk.update(text=s(b.get("text")), by=s(b.get("by")))
            ok = bool(blk["text"])
        else:   # verdict
            ver = []
            for v in b.get("items") or []:
                if isinstance(v, dict) and s(v.get("text")):
                    ver.append({"type": "한계" if "한계" in s(v.get("type")) else "의의", "text": s(v.get("text")),
                                "pages": _pages(v.get("pages")),
                                "outside": bool(v.get("outside")) or "밖" in _pages(v.get("pages"))})
            blk["items"] = ver[:6]
            ok = bool(ver)
        if ok:
            if b.get("hero") is True and t in HERO_TYPES and not any(x.get("hero") for x in blocks):
                blk["hero"] = True   # 주인공은 하나만(§8 항목58 ②)
            blocks.append(blk)
    out["blocks"] = blocks[:MAX_BLOCKS]
    if not (out["title"] or out["subtitle"] or out["blocks"]):
        raise BoardSpecError("보드 제목·요약·블록이 비어 있어요")
    _copy_app_keys(d, out)
    return out


def dump_board(spec: dict) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=1)


def build_board_prompt(body: str, note: str = "", summarized: bool = False) -> str:
    request_line = f"사용자 요청(이 관점으로 정리할 것): {note.strip()}\n" if note.strip() else ""
    kind_note = "쪽 묶음별 요약" if summarized else "원문에서 뽑은 글"
    return _BOARD_TEMPLATE.format(body=body, request_line=request_line, kind_note=kind_note, format=_BLOCK_FORMAT.format())


def build_refine_prompt(instruction: str, code: str) -> str:
    spec = parse_board(code)
    for k in _APP_KEYS:   # 이 PC의 파일 경로·앱 표시는 AI에 보내지 않는다
        spec.pop(k, None)
    if is_block_spec(spec):
        return _BLOCK_REFINE_TEMPLATE.format(code=dump_board(spec), instruction=instruction.strip(),
                                             format=_BLOCK_FORMAT.format())
    return _REFINE_TEMPLATE.format(code=dump_board(spec), instruction=instruction.strip(), format=_FORMAT.format())


def generate_board(api_key: str, pdf_path: str, note: str = "", *, model: str, base_url: str = gw.BASE_URL,
                   progress=None) -> tuple[str, str]:
    """PDF → (보드 설계서 JSON 글, 실제 쓴 모델). 긴 문서는 쪽 묶음별 요약 뒤(옛 「풀어 그리기」와 같은 길). 글자 없는 PDF는
    `PdfTextError`, 응답을 못 읽으면 `BoardSpecError`. 설계서에 PDF 경로(`_pdf`)를 넣어 앱이 논문 그림을 잘라 오게 한다."""
    from easycad.ai.pdf_to_mermaid import pdf_body
    body, summarized, used = pdf_body(api_key, pdf_path, model=model, base_url=base_url, progress=progress)
    if progress:
        progress("보드 정리하는 중")
    res = gw.call_text_with_fallback(api_key, build_board_prompt(body, note, summarized), model=model,
                                     base_url=base_url, timeout=180.0)
    spec = parse_board(res.content)
    spec["_pdf"] = pdf_path
    return dump_board(spec), res.model_used or used


def refine_board(api_key: str, instruction: str, code: str, *, model: str, base_url: str = gw.BASE_URL) -> tuple[str, str]:
    """결과 막대 한 줄로 보드 이어 고치기 — 지금 설계서 + 지시 → 고친 설계서(원문은 다시 안 읽음). PDF 경로는 이어 붙인다."""
    old = parse_board(code)
    res = gw.call_text_with_fallback(api_key, build_refine_prompt(instruction, code), model=model, base_url=base_url,
                                     timeout=120.0)
    spec = parse_board(res.content)
    for k in _APP_KEYS:   # 앱이 붙인 칸은 이어 붙인다
        if old.get(k):
            spec[k] = old[k]
    return dump_board(spec), res.model_used
