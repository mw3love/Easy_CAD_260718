"""텍스트 설명 → Mermaid flowchart 생성 — Mermaid 가져오기의 AI 보조 기능.

§8 항목18(AI 이미지→도면) 후속(2026-08-12, deep-interview로 확정): 실사용 결과 이미지
입력 경로는 못 쓰겠다는 판단이 나와 완전히 폐기하고, "텍스트 설명 → AI → Mermaid" 로
`fileio/mermaid_import.py` 가져오기에 흡수했다. 옛 `sketch_pipeline.py`(P1~P3.75 이미지
타일링)와 달리 게이트웨이 호출이 1번뿐이고 좌표·타일링이 전혀 없다 — Mermaid 자체가
좌표 없는 관계형 DSL이라 배치는 항상 `mermaid_import.layout_positions()`(그래프 BFS
레벨 배치)가 맡는다.

**PyQt 비의존** — `gateway.py`와 같은 이유로 헤드리스 테스트·잠재적 CLI에서도 그대로
쓸 수 있다.
"""
from __future__ import annotations

from easycad.ai import gateway as gw

_PROMPT_TEMPLATE = """다음 설명을 Mermaid flowchart 문법으로 변환하라.

설명: {description}

규칙:
- 반드시 `flowchart TD` 또는 `flowchart LR`로 시작할 것(설명의 흐름에 맞게 방향을 고를 것).
- 노드 라벨은 한글로 간결하게, 설명에 없는 단계를 임의로 추가하지 말 것.
- 다른 설명 없이 Mermaid 코드만 출력하라(```mermaid 코드블록으로 감싸도 되고 안 감싸도 됨).
"""


def build_prompt(description: str) -> str:
    return _PROMPT_TEMPLATE.format(description=description.strip())


def extract_mermaid(raw: str) -> str:
    """모델 응답에서 Mermaid 텍스트만 꺼낸다 — ```mermaid 코드펜스가 섞여 나오면 벗긴다
    (`gateway.parse_json`의 코드펜스 처리와 같은 관례)."""
    txt = raw.strip()
    if txt.startswith("```"):
        lines = txt.split("\n")
        lines = lines[1:]                 # 여는 펜스(```mermaid 또는 ```) 제거
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]            # 닫는 펜스 제거
        txt = "\n".join(lines).strip()
    return txt


def generate_mermaid(api_key: str, description: str, *, model: str) -> tuple[str, str]:
    """설명 텍스트 → (Mermaid 텍스트, 실제 사용된 모델). 실패 시 예외를 그대로 올린다
    (호출자가 다이얼로그에서 메시지로 보여준다)."""
    prompt = build_prompt(description)
    res = gw.call_text_with_fallback(api_key, prompt, model=model)
    return extract_mermaid(res.content), res.model_used
