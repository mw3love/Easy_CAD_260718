"""말(또는 그림) → 흐름도 「내용 설계서」 JSON(§8 항목52, 2026-10-16 Magic Board 개편).

옛 경로(`text_to_mermaid.py`)는 AI가 Mermaid를 쓰고 가져오기가 관계만 읽어 색·묶음·강조가 없는 "네모 나열"이 됐다.
이제 AI는 **내용만**(담당 묶음·단계·갈림길·중요한 단계 하나·아이콘 이름) 쓰고, 배치·색·글꼴은 앱이 규칙으로 정한다
(`fileio/flow_spec.py` 배치, `host_fileio._build_flowspec_items` 그리기). 말을 다루는 규칙(나열한 단계는 그대로, "구조를
알려줘"는 펼쳐 그리기)은 옛 지시문에서 실측으로 다듬은 것을 그대로 옮겼다.

Mermaid 결과(「풀어 그리기」 PDF 흐름도·Mermaid 가져오기)를 이어 고칠 땐 옛 Mermaid 지시문으로 보낸다 — 바탕 글의 형식을 따른다.

**PyQt 비의존**(`gateway.py`와 같은 이유).
"""
from __future__ import annotations

from easycad.ai import gateway as gw
from easycad.fileio.flow_spec import looks_like_spec, parse_spec

_FORMAT = """출력 형식 — 아래 JSON 하나만 출력하라(다른 설명 없이, 코드펜스는 있어도 됨):
{{"title": "흐름도 제목(짧게)",
 "direction": "LR",
 "lanes": ["담당 이름", ...],
 "steps": [{{"id": "s1", "text": "단계 이름", "lane": "담당 이름", "kind": "start", "icon": "아이콘 이름"}}, ...],
 "links": [{{"from": "s1", "to": "s2", "text": "연결 글(없으면 빼기)"}}, ...],
 "focus": "가장 중요한 단계의 id"}}

칸 설명:
- lanes: 단계를 맡는 사람·부서·장비·장소가 둘 이상으로 뚜렷이 나뉘면 그 묶음 이름(2~5개, 흐름에 처음 나오는 순서로).
  나눌 게 없으면 [] — 억지로 만들지 말 것. lanes가 있으면 모든 단계의 lane은 그 이름 중 하나.
- kind: 처음은 "start", 끝은 "end", 예/아니오처럼 갈리는 판단은 "decision"(나가는 links의 text에 "예"·"아니오" 같은 갈림 글),
  입력·출력은 "data", 문서·보고서는 "document", 저장소·DB는 "database", 나머지는 "step"(기본이라 빼도 됨).
- focus: 이 흐름에서 가장 중요한 단계 딱 하나의 id(앱이 그 하나만 강조한다). 고르기 어려우면 "".
- icon: {icon_rule}
- direction: 기본 "LR"(가로). 위→아래 계층·단계가 아래로 깊어지는 흐름이 뚜렷할 때만 "TD".
- text: 한글로 짧게(15자 안팎, 필요하면 영문 약어 병기). 좌표·색·크기는 쓰지 말 것(앱이 정한다).
- 모든 단계는 links로 어딘가에 이어질 것. 되돌아가는 고리(다시 시도 등)도 links로 쓰면 된다."""


def _icon_rule(icons) -> str:
    names = [n for n in (icons or []) if n]
    if not names:
        return "쓰지 말 것(쓸 수 있는 아이콘이 없음)."
    return ("아래 목록에 그 단계와 꼭 맞는 것이 있을 때만 그 이름 그대로, 아니면 빼라(대부분은 없음). 목록: "
            + ", ".join(names[:60]))


_PROMPT_TEMPLATE = """다음 요청을 흐름도의 「내용 설계서」로 써라. 그림의 배치·색은 앱이 정하니 너는 내용만 정한다.

요청: {description}

내용 규칙:
- 요청이 단계·관계를 직접 나열하면(예: "A → B → C") 그 단계만 그대로 쓰고 임의로 단계를 더하지 말 것.
- 요청이 어떤 대상의 구조·원리·흐름을 설명해 달라는 말이면(예: "~ 구조를 알려줘", "~를 그려줘") 일반적인 기술 지식으로
  주요 구성 요소와 신호·처리 흐름을 펼쳐 써라. "상세하게·자세히"가 있으면 하위 구성까지 한 단계 더 깊게(대략 10~20단계).

{format}
"""

# ⚠ "실제로 그려진 연결선만"은 옛 이미지 파이프라인이 2026-07-21에 처음 겪은 환각 함정(`text_to_mermaid.py` 같은 자리 주석).
_IMAGE_PROMPT_TEMPLATE = """이 이미지(손그림·사진·스크린샷 등)의 흐름도를 「내용 설계서」로 옮겨라. 배치·색은 앱이 정하니 너는 내용만.
{note_line}
내용 규칙:
- 단계 글은 이미지에 적힌 텍스트 그대로(한글 포함) — 이미지에 없는 단계를 임의로 추가하지 말 것.
- 연결은 **이미지에 실제로 그려진 것만**. 논리적으로 있어야 할 것 같다고 없는 연결을 추가하지 말 것.
- 이미지에 구역·담당 칸(스윔레인)이 그려져 있으면 그것을 lanes로.

{format}
"""

_REFINE_TEMPLATE = """아래 흐름도 「내용 설계서」를 지시대로 고쳐라.

```json
{code}
```

지시: {instruction}

규칙:
- 지시와 관계없는 단계·연결·글·id는 그대로 둘 것(바뀐 곳만 달라야 사람이 비교할 수 있다).
- direction은 지시가 바꾸라고 하지 않으면 그대로. 강조(focus)·담당(lanes)도 지시가 없으면 그대로.
- 고친 전체 설계서를 같은 형식으로 출력하라.

{format}
"""


def build_prompt(description: str, icons=()) -> str:
    return _PROMPT_TEMPLATE.format(description=description.strip(),
                                   format=_FORMAT.format(icon_rule=_icon_rule(icons)))


def build_image_prompt(note: str = "", icons=()) -> str:
    note_line = f"참고(보충 설명): {note.strip()}\n" if note.strip() else ""
    return _IMAGE_PROMPT_TEMPLATE.format(note_line=note_line, format=_FORMAT.format(icon_rule=_icon_rule(icons)))


def build_refine_prompt(instruction: str, code: str, icons=()) -> str:
    return _REFINE_TEMPLATE.format(code=code.strip(), instruction=instruction.strip(),
                                   format=_FORMAT.format(icon_rule=_icon_rule(icons)))


def generate_flow(api_key: str, description: str, *, model: str, base_url: str = gw.BASE_URL, image=None,
                  base_code: str = "", icons=()) -> tuple[str, str]:
    """설명(및/또는 그림) → (설계서 JSON 글, 실제 쓴 모델). 응답은 `parse_spec`으로 한 번 읽어 다듬은 글로 돌려준다
    (못 읽으면 FlowSpecError — 호출부가 실패로 보여 준다). `base_code`가 Mermaid면(「풀어 그리기」 결과 이어 고치기) 옛 Mermaid
    지시문으로 보내고 Mermaid 글을 그대로 돌려준다."""
    if base_code.strip() and not looks_like_spec(base_code):
        from easycad.ai.text_to_mermaid import generate_mermaid
        return generate_mermaid(api_key, description, model=model, base_url=base_url, image=image, base_code=base_code)
    if base_code.strip():
        prompt = build_refine_prompt(description, base_code, icons)
    else:
        prompt = build_image_prompt(description, icons) if image is not None else build_prompt(description, icons)
    timeout = 120.0 if image is not None else 60.0
    res = gw.call_text_with_fallback(api_key, prompt, model=model, base_url=base_url, image=image, timeout=timeout)
    return parse_spec(res.content).to_json(), res.model_used
