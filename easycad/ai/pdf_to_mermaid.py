"""논문·보고서 PDF 읽기 — 쪽 글 뽑기·긴 문서 나눠 요약(§8 항목45, 2026-10-16).

[§8 항목53, 2026-10-16] 이 파일의 흐름도 그리기(옛 「풀어 그리기」 — PDF → Mermaid 하나)는 「한 장 보드」(`pdf_to_board.py`)로
바뀌어 지웠다. 아래 옛 설명 중 그리기 부분은 경위 기록으로만 남는다.

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

def build_summary_prompt(chunk) -> str:
    return _SUMMARY_TEMPLATE.format(body=pages_to_text(chunk))


def pdf_body(api_key: str, pdf_path: str, *, model: str, base_url: str = gw.BASE_URL, progress=None) -> tuple[str, bool, str]:
    """PDF → (AI에 보낼 본문 — 줄마다 [p.N], 요약했나, 실제 쓴 모델). 짧으면 원문 그대로, 길면 쪽 묶음별 요약.
    한 장 보드와 「PDF로 흐름도」(2026-10-16 — 가운데 칸 말에 따라)가 같이 쓴다."""
    pages = extract_pdf_pages(pdf_path)
    if sum(len(t) for _n, t in pages) <= SINGLE_PASS_CHARS:
        return pages_to_text(pages), False, model
    parts, used = [], model
    chunks = chunk_pages(pages)
    for i, ch in enumerate(chunks, start=1):
        if progress:
            progress(f"긴 문서라 나눠 읽는 중 {i}/{len(chunks)}")
        res = gw.call_text_with_fallback(api_key, build_summary_prompt(ch), model=model, base_url=base_url, timeout=120.0)
        parts.append(res.content.strip())
        used = res.model_used
    return "\n".join(parts), True, used
