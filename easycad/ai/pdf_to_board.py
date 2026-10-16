"""논문 PDF → 「한 장 보드」 설계서 JSON(§8 항목53 2단계, 2026-10-16 Magic Board) — 옛 「풀어 그리기」(흐름도 하나, §8 항목45)를 대체.

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
    SINGLE_PASS_CHARS, build_summary_prompt, chunk_pages, extract_pdf_pages, pages_to_text,
)
from easycad.fileio.flow_spec import FlowSpecError, parse_spec

BOARD_KIND = "paper-board"   # 설계서 표식 — 흐름도 설계서와 가르는 열쇠(`is_board_spec`)

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

_BOARD_TEMPLATE = """다음은 논문 PDF의 내용이다({kind_note}, 각 줄 앞 [p.N]은 원문 쪽 번호).
이 논문을 처음 보는 사람이 한 장으로 이해하도록 「한 장 보드」의 내용을 정리하라. 배치·색은 앱이 정하니 너는 내용만 정한다.
{request_line}
{format}

문서:
{body}
"""

_REFINE_TEMPLATE = """아래는 논문 「한 장 보드」의 내용 설계서다. 지시대로 고쳐라.

```json
{code}
```

지시: {instruction}

규칙:
- 지시와 관계없는 칸은 그대로 둘 것. 원문을 다시 볼 수 없으니 새 숫자·사실을 지어내지 말 것(필요하면 "논문 밖 맥락"으로 표시).
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
    return t.lstrip().startswith("{") and f'"{BOARD_KIND}"' in t[:400]


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
            page = int(re.sub(r"[^0-9]", "", str(fig.get("page"))) or "x")
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
    if s(d.get("_pdf")):
        out["_pdf"] = s(d.get("_pdf"))
    if d.get("_pages") in ("one", "auto"):   # 결과 막대 「한 장으로」(앱이 붙임, §8 항목53 4단계)
        out["_pages"] = d["_pages"]
    if isinstance(d.get("_sources"), dict):   # 여러 자료 목록(앱이 붙임)
        out["_sources"] = d["_sources"]
    return out


def dump_board(spec: dict) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=1)


def build_board_prompt(body: str, note: str = "", summarized: bool = False) -> str:
    request_line = f"사용자 요청(이 관점으로 정리할 것): {note.strip()}\n" if note.strip() else ""
    kind_note = "쪽 묶음별 요약" if summarized else "원문에서 뽑은 글"
    return _BOARD_TEMPLATE.format(body=body, request_line=request_line, kind_note=kind_note, format=_FORMAT.format())


def build_refine_prompt(instruction: str, code: str) -> str:
    spec = parse_board(code)
    spec.pop("_pdf", None)
    spec.pop("_pages", None)
    spec.pop("_sources", None)   # 파일 경로가 든 목록 — AI에 안 보냄   # 이 PC의 파일 경로는 AI에 보내지 않는다
    return _REFINE_TEMPLATE.format(code=dump_board(spec), instruction=instruction.strip(), format=_FORMAT.format())


def generate_board(api_key: str, pdf_path: str, note: str = "", *, model: str, base_url: str = gw.BASE_URL,
                   progress=None) -> tuple[str, str]:
    """PDF → (보드 설계서 JSON 글, 실제 쓴 모델). 긴 문서는 쪽 묶음별 요약 뒤(옛 「풀어 그리기」와 같은 길). 글자 없는 PDF는
    `PdfTextError`, 응답을 못 읽으면 `BoardSpecError`. 설계서에 PDF 경로(`_pdf`)를 넣어 앱이 논문 그림을 잘라 오게 한다."""
    pages = extract_pdf_pages(pdf_path)
    total = sum(len(t) for _n, t in pages)
    used = model
    if total <= SINGLE_PASS_CHARS:
        body, summarized = pages_to_text(pages), False
    else:
        parts = []
        chunks = chunk_pages(pages)
        for i, ch in enumerate(chunks, start=1):
            if progress:
                progress(f"긴 문서라 나눠 읽는 중 {i}/{len(chunks)}")
            res = gw.call_text_with_fallback(api_key, build_summary_prompt(ch), model=model, base_url=base_url,
                                             timeout=120.0)
            parts.append(res.content.strip())
            used = res.model_used
        body, summarized = "\n".join(parts), True
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
    for k in ("_pdf", "_pages", "_sources"):   # 앱이 붙인 칸은 이어 붙인다
        if old.get(k):
            spec[k] = old[k]
    return dump_board(spec), res.model_used
