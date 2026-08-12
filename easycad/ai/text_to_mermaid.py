"""텍스트/이미지 설명 → Mermaid flowchart 생성 — Mermaid 가져오기의 AI 보조 기능.

§8 항목18(AI 이미지→도면) 후속(2026-08-12, deep-interview로 확정): 실사용 결과 이미지→
**좌표 보존 JSON** 경로는 못 쓰겠다는 판단이 나와 완전히 폐기하고, "텍스트 설명 → AI →
Mermaid" 로 `fileio/mermaid_import.py` 가져오기에 흡수했다. 옛 `sketch_pipeline.py`
(P1~P3.75 이미지 타일링)와 달리 게이트웨이 호출이 1번뿐이고 좌표·타일링이 전혀 없다 —
Mermaid 자체가 좌표 없는 관계형 DSL이라 배치는 항상 `mermaid_import.layout_positions()`
(그래프 BFS 레벨 배치)가 맡는다.

같은 날 후속(2026-08-12) — 이미지 입력을 다시 받되 이번엔 **이미지→Mermaid 텍스트**
단일 호출뿐이다(좌표 없음, 타일링 없음) — 이미지 경로를 죽였던 "원본 배치를 정밀하게
지켜야 한다"는 요구 자체가 Mermaid 출력엔 없기 때문에 옛 파이프라인의 복잡성 없이도
성립한다. `image`가 주어지면 텍스트 칸의 내용은 "보충 설명(선택)"으로 격하된다(옛
`_AIImageImportDialog`의 "이미지+보충설명" 관례 계승).

**PyQt 비의존** — `gateway.py`와 같은 이유로 헤드리스 테스트·잠재적 CLI에서도 그대로
쓸 수 있다(`image`는 PIL Image 객체로 받는다 — PyQt 타입에 의존하지 않음, 호출부인
`host_dialogs.py`가 QPixmap↔PIL 변환을 담당).
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

# ⚠ "실제로 그려진 연결선만"은 옛 이미지 파이프라인이 2026-07-21에 처음 겪은 환각 함정
# (`docs/image_to_ecad.md`)과 같다 — 모델이 "이 흐름이면 여기로 돌아가야 논리적"이라며
# 원본에 없는 화살표를 만들어낸다. 텍스트 경로는 애초에 참조할 원본이 없어 이 문제가
# 성립하지 않지만, 이미지 경로는 원본이 있으니 같은 규칙을 다시 명시해야 한다.
_IMAGE_PROMPT_TEMPLATE = """이 이미지(손그림·사진·스크린샷 등)를 보고 Mermaid flowchart
문법으로 변환하라.
{note_line}
규칙:
- 반드시 `flowchart TD` 또는 `flowchart LR`로 시작할 것(이미지의 흐름에 맞게 방향을 고를 것).
- 노드 라벨은 이미지에 적힌 텍스트 그대로(한글 포함) — 이미지에 없는 단계를 임의로
  추가하지 말 것.
- 화살표/선은 **이미지에 실제로 그려진 것만** 반영하라. 논리적으로 있어야 할 것 같다고
  없는 연결선을 추가하지 말 것.
- 다른 설명 없이 Mermaid 코드만 출력하라(```mermaid 코드블록으로 감싸도 되고 안 감싸도 됨).
"""


def build_prompt(description: str) -> str:
    return _PROMPT_TEMPLATE.format(description=description.strip())


def build_image_prompt(note: str = "") -> str:
    note_line = f"참고(보충 설명): {note.strip()}\n" if note.strip() else ""
    return _IMAGE_PROMPT_TEMPLATE.format(note_line=note_line)


def extract_mermaid(raw: str) -> str:
    """모델 응답에서 Mermaid 텍스트만 꺼낸다 — ```mermaid 코드펜스가 섞여 나오면 벗긴다."""
    txt = raw.strip()
    if txt.startswith("```"):
        lines = txt.split("\n")
        lines = lines[1:]                 # 여는 펜스(```mermaid 또는 ```) 제거
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]            # 닫는 펜스 제거
        txt = "\n".join(lines).strip()
    return txt


def generate_mermaid(api_key: str, description: str, *, model: str,
                      base_url: str = gw.BASE_URL, image=None) -> tuple[str, str]:
    """설명(및/또는 이미지) → (Mermaid 텍스트, 실제 사용된 모델). `image`(PIL Image)가
    주어지면 이미지 프롬프트로 전환되고 `description`은 보충 설명 취급된다(비어 있어도
    됨 — 텍스트 전용 경로와 달리 이미지 경로는 설명이 필수가 아니다). 이미지 호출은
    단일 이미지 인코딩·전송이 텍스트보다 오래 걸릴 수 있어 timeout을 넉넉히(120s) 잡는다
    (옛 밀집 타일링 파이프라인의 504 위험만큼은 아니다 — 이미지 1장뿐이라 그 정도는
    아니지만 텍스트 기본값 60s보다는 여유가 필요하다는 판단, 실측 없음). 실패 시 예외를
    그대로 올린다(호출자가 다이얼로그에서 메시지로 보여준다)."""
    prompt = build_image_prompt(description) if image is not None else build_prompt(description)
    timeout = 120.0 if image is not None else 60.0
    res = gw.call_text_with_fallback(api_key, prompt, model=model, base_url=base_url,
                                     image=image, timeout=timeout)
    return extract_mermaid(res.content), res.model_used
