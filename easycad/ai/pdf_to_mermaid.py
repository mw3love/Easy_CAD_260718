"""논문·보고서 PDF → 핵심을 풀어 그린 Mermaid flowchart(§8 항목45, 2026-10-16) — AI 패널 「풀어 그리기」.

처음 보는 사람이 문서의 핵심을 한눈에 보게 하는 "설명 그림". 상자마다 원문 쪽 번호(`· p.N`)를 붙여 AI 요약을 원문과
대조할 수 있게 한다(AI 요약은 틀릴 수 있음 — 다잡기 2026-10-16). 결과는 흐름도와 같은 Mermaid라 캔버스 임시 결과·이어
고치기·방향 바꾸기를 그대로 쓴다(`mermaid_import`는 flowchart만 읽음 — 그래서 형식은 flowchart 하나).

anatomy 스킬(wheresryan22/anatomy)에서 가져온 "그리기 전에 목록부터": 지시문이 먼저 핵심 개념을 고르고 그 관계를
그리게 한다(한 번 호출 안에서 — 사용자 확인 단계는 두지 않음). 긴 문서는 쪽 묶음별로 먼저 요약(쪽 번호 유지)한 뒤 그린다.

**PyQt 비의존**(text_to_mermaid와 같은 이유). PDF 읽기는 PyMuPDF(`pdf_import`와 같은 의존성, 지연 임포트).
"""
from __future__ import annotations

import re

from easycad.ai import gateway as gw
from easycad.ai.text_to_mermaid import extract_mermaid

# 한 번에 보낼 본문 상한(글자). 넘으면 쪽 묶음별 요약 후 그린다. 160쪽 세미나 자료가 5.6만 자(2026-10-16 실측) — 한 번에 가는 크기.
SINGLE_PASS_CHARS = 90_000
CHUNK_CHARS = 40_000


class PdfTextError(RuntimeError):
    """글자를 뽑을 수 없는 PDF(스캔 등)."""


def extract_pdf_pages(path: str) -> list[tuple[int, str]]:
    """(쪽 번호 1부터, 그 쪽 글) — 빈 쪽은 뺀다. 줄바꿈·공백은 한 칸으로(토큰 절약)."""
    try:
        import fitz   # PyMuPDF
    except ImportError as e:   # pragma: no cover — requirements.txt에 있음
        raise PdfTextError("PDF를 읽는 부품(PyMuPDF)이 없어요") from e
    pages = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = re.sub(r"\s+", " ", page.get_text()).strip()
            if text:
                pages.append((i, text))
    if not pages:
        raise PdfTextError("이 PDF에서 글자를 찾지 못했어요(스캔한 PDF일 수 있어요). 쪽을 그림으로 바꿔 「베끼기」를 써 보세요.")
    return pages


def pages_to_text(pages) -> str:
    return "\n".join(f"[p.{n}] {t}" for n, t in pages)


def chunk_pages(pages, limit: int | None = None) -> list[list[tuple[int, str]]]:
    """쪽을 순서대로 묶어 묶음마다 글자 수가 `limit`(기본 `CHUNK_CHARS` — 부를 때 읽음) 근처가 되게
    (한 쪽이 혼자 넘으면 그 쪽만 한 묶음)."""
    limit = CHUNK_CHARS if limit is None else limit
    chunks, cur, size = [], [], 0
    for n, t in pages:
        if cur and size + len(t) > limit:
            chunks.append(cur)
            cur, size = [], 0
        cur.append((n, t))
        size += len(t)
    if cur:
        chunks.append(cur)
    return chunks


_SUMMARY_TEMPLATE = """다음은 PDF 문서의 일부다(각 줄 앞 [p.N]은 원문 쪽 번호).
이 부분의 핵심 내용을 글머리표 15줄 이내로 요약하라. 줄마다 끝에 근거 쪽을 (p.N) 형식으로 붙일 것.
문서에 없는 내용은 쓰지 말 것. 요약만 출력하라.

{body}
"""

_EXPLAIN_TEMPLATE = """다음은 PDF 문서의 내용이다({kind_note}, 각 줄 앞 [p.N]은 원문 쪽 번호).
이 문서를 처음 보는 사람이 핵심을 한눈에 이해하도록 Mermaid flowchart로 풀어 그려라.
{request_line}
그리는 순서:
1. 먼저 문서의 핵심 주제와 중요한 개념·단계를 8~15개 고른다(머릿속으로만 — 출력하지 말 것).
2. 그것들 사이의 관계(순서, 원인→결과, 구성·포함, 비교)를 화살표로 잇고, 관계가 분명하지 않으면 화살표에 짧은 라벨(2~6자)을 단다.
   단, 한 노드에서 화살표가 2개 이상 갈라져 나가면 그 화살표들에는 라벨을 달지 말 것(갈래 라벨은 한 줄에 겹쳐 보임).

규칙:
- 반드시 `flowchart TD` 또는 `flowchart LR`로 시작할 것 — 단계가 차례로 이어지는 절차면 LR, 주제에서 하위 개념으로 갈라지는 구조면 TD.
- 노드는 반드시 `ID[라벨]` 형식(ID는 영문·숫자 A, B, C…) — 라벨을 ID 자리에 바로 쓰지 말 것.
- 노드 라벨은 짧은 한글(필요하면 영문 약어 병기) 뒤에 ` · p.N` 형식으로 근거 쪽을 붙일 것(예: `A[IP 전환 이유 · p.2]`).
  괄호 ( ) 는 라벨 안에 쓰지 말 것.
- 문서에 없는 내용을 지어내지 말 것.
- subgraph·style·classDef는 쓰지 말고 노드와 화살표만 평평하게. 모든 노드는 화살표로 어딘가에 이어질 것.
- 다른 설명 없이 Mermaid 코드만 출력하라(```mermaid 코드블록으로 감싸도 되고 안 감싸도 됨).

문서:
{body}
"""


def build_summary_prompt(chunk) -> str:
    return _SUMMARY_TEMPLATE.format(body=pages_to_text(chunk))


def build_explain_prompt(body: str, note: str = "", summarized: bool = False) -> str:
    request_line = f"사용자 요청(이 관점으로 그릴 것): {note.strip()}\n" if note.strip() else ""
    kind_note = "쪽 묶음별 요약" if summarized else "원문에서 뽑은 글"
    return _EXPLAIN_TEMPLATE.format(body=body, request_line=request_line, kind_note=kind_note)


def generate_explain(api_key: str, pdf_path: str, note: str = "", *, model: str,
                     base_url: str = gw.BASE_URL, progress=None) -> tuple[str, str]:
    """PDF → (Mermaid 텍스트, 실제 사용된 모델). `progress(text)`가 있으면 단계마다 한 줄 알린다(긴 문서 요약 중 등).
    실패는 예외 그대로(호출부가 기록 칸에 보여 줌). 글자가 없으면 `PdfTextError`."""
    pages = extract_pdf_pages(pdf_path)
    total = sum(len(t) for _n, t in pages)
    used = model
    if total <= SINGLE_PASS_CHARS:
        body, summarized = pages_to_text(pages), False
    else:
        chunks = chunk_pages(pages)
        parts = []
        for i, ch in enumerate(chunks, start=1):
            if progress:
                progress(f"긴 문서라 나눠 읽는 중 {i}/{len(chunks)}")
            res = gw.call_text_with_fallback(api_key, build_summary_prompt(ch), model=model, base_url=base_url,
                                             timeout=120.0)
            parts.append(res.content.strip())
            used = res.model_used
        body, summarized = "\n".join(parts), True
    if progress:
        progress("그리는 중")
    res = gw.call_text_with_fallback(api_key, build_explain_prompt(body, note, summarized), model=model,
                                     base_url=base_url, timeout=180.0)
    return extract_mermaid(res.content), res.model_used or used
