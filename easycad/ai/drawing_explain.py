"""도면 → 단계별 설명(§8 항목47, 2026-10-16) — 「설명 페이지 만들기」. 결과는 「HTML로 공유」 페이지 오른쪽 설명 칸이 된다.

도면의 상자(번호·글자)와 화살표 연결(어느 상자 → 어느 상자, 라벨)을 글로 정리해 KAIROS에 보내고, 처음 보는 사람이 따라갈
단계(제목·설명·관련 상자 번호)를 JSON으로 받는다. 페이지는 단계를 넘길 때마다 그 상자들을 강조하고 화면을 옮긴다.
교육·발표·대회 시연용(다잡기 2026-10-16 — anatomy 스킬에서 받은 "어려운 개념을 시각적으로 풀어 보여 주기"의 우리 식 답).

**PyQt 비의존.** 상자 번호는 HTML `SHAPES` 순서와 같다(호출부가 같은 목록으로 둘 다 만든다).
"""
from __future__ import annotations

import json
import re

from easycad.ai import gateway as gw

# 단계 제목 앞 번호("1." "2)" "3단계:" "1. 1.") — 페이지 목록이 번호를 붙여 "1. 1. …"이 됐다(실측). 숫자로 시작하는 진짜 제목("2110 표준")은 그대로.
_STEP_NUM_RE = re.compile(r"^\s*(?:\d+\s*(?:단계\s*[:.)]?|[.):])\s*)+")

_TEMPLATE = """다음은 도면 「{title}」의 내용이다. 이 도면을 처음 보는 사람에게 차례로 설명하는 안내를 만들어라.
{note_line}
상자 목록(번호: 글자):
{boxes}

연결(화살표, 번호 → 번호 : 라벨):
{links}

출력 형식 — 아래 JSON 하나만 출력하라(다른 설명·코드펜스 없이):
{{"title": "안내 제목", "summary": "도면 전체를 2~3문장으로", "steps": [{{"title": "단계 제목", "body": "2~4문장 설명", "boxes": [상자 번호, ...]}}]}}

규칙:
- 단계는 4~8개. 흐름이 있으면 흐름 순서대로, 없으면 큰 덩어리에서 세부로.
- 단계마다 "boxes"에 그 단계가 다루는 상자 번호(1~5개)를 넣을 것 — 위 목록에 있는 번호만.
- 상자 번호는 "boxes"에만 쓰고 제목·설명 글에는 쓰지 말 것(예: "인코더(3)" 금지 — 읽는 사람에겐 번호가 안 보임).
- 설명은 쉬운 한국어로, 전문 용어는 처음 나올 때 짧게 풀어 쓸 것. 도면에 없는 사실을 단정하지 말 것(일반 상식 수준의 보충은 괜찮음).
"""


def build_steps_prompt(title: str, boxes, links, note: str = "") -> str:
    """`boxes` = [(번호, 글자)], `links` = [(번호, 번호, 라벨)]."""
    box_lines = "\n".join(f"{i}: {t}" for i, t in boxes) or "(없음)"
    link_lines = "\n".join(f"{a} → {b}" + (f" : {lbl}" if lbl else "") for a, b, lbl in links) or "(없음)"
    note_line = f"설명할 관점(사용자 요청): {note.strip()}\n" if note.strip() else ""
    return _TEMPLATE.format(title=title, boxes=box_lines, links=link_lines, note_line=note_line)


def parse_steps(raw: str, n_boxes: int) -> dict:
    """모델 응답 → {"title","summary","steps":[{"title","body","boxes"}]}. 코드펜스·앞뒤 말은 걷고 첫 `{`~마지막 `}`만 읽는다.
    없는 상자 번호는 버리고, 글자가 빈 단계도 버린다. 단계가 하나도 없으면 ValueError."""
    txt = gw.strip_code_fence(raw)
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("설명 형식(JSON)을 찾지 못했어요")
    data = json.loads(txt[a:b + 1])
    steps = []
    for st in data.get("steps") or []:
        if not isinstance(st, dict):
            continue
        title, body = str(st.get("title") or "").strip(), str(st.get("body") or "").strip()
        title = _STEP_NUM_RE.sub("", title)   # 목록이 번호를 붙이므로 제목 앞 "1." 류는 뗀다(실측: "1. 1. …")
        if not (title or body):
            continue
        ids = []
        for v in st.get("boxes") or []:
            try:
                k = int(v)
            except (TypeError, ValueError):
                continue
            if 0 <= k < n_boxes and k not in ids:
                ids.append(k)
        steps.append({"title": title, "body": body, "boxes": ids})
    if not steps:
        raise ValueError("설명 단계가 비어 있어요")
    return {"title": str(data.get("title") or "").strip(), "summary": str(data.get("summary") or "").strip(),
            "steps": steps}


def generate_steps(api_key: str, title: str, boxes, links, note: str = "", *, model: str,
                   base_url: str = gw.BASE_URL) -> tuple[dict, str]:
    res = gw.call_text_with_fallback(api_key, build_steps_prompt(title, boxes, links, note), model=model,
                                     base_url=base_url, timeout=120.0)
    return parse_steps(res.content, len(boxes)), res.model_used
