"""텍스트/이미지 설명 → AI → SVG 에셋(선-아트 아이콘) 생성 — §8 항목20 AI SVG 에셋 생성의
B단계(텍스트) + Stage 3(이미지, 2026-08-19).

A단계(`tools/svg_asset_probe.py`, 2026-08-14 게이트웨이 실측)에서 검증한 프롬프트
템플릿·코드펜스 벗기기 로직을 그대로 승격했다(그 스크립트는 이제 이 모듈을 재사용).
게이트웨이 호출은 새로 안 만들고 `easycad/ai/gateway.py`(Mermaid AI 보조가 이미 검증해
쓰는 것)를 그대로 재사용 — `text_to_mermaid.py`와 동일 패턴.

프롬프트 규칙은 `easycad/fileio/svg_import.py`가 실제로 지원/미지원하는 요소를 그대로
반영한다("모델이 예쁘게 그릴 수 있는가"가 아니라 "우리 파서가 받을 수 있는 형태로 낼
수 있는가") — 그 모듈의 docstring 참조.

2026-08-19 deep-interview로 이미지 입력을 추가(Stage 3) — `image`(PIL Image)가 주어지면
`subject`는 보충 설명 취급되고, 프롬프트는 "이미지를 보고 그려라"로 전환된다. 이미지
입력·타임아웃 처리는 `text_to_mermaid.generate_mermaid`와 동일 패턴(호출부인
`host_dialogs.py`가 Mermaid 다이얼로그의 첨부 UI(찾아보기·드래그드롭·Ctrl+V)를 그대로
재사용).

PyQt 비의존 — `gateway.py`와 같은 이유로 헤드리스 테스트에서도 그대로 쓸 수 있다
(`image`는 PIL Image 객체로 받는다)."""
from __future__ import annotations

from easycad.ai import gateway as gw

_RULES = """규칙(반드시 지킬 것 — 이 SVG는 전용 파서로 다시 읽어들여 편집 가능한 도형으로 변환된다):
- 루트 <svg>에 viewBox="0 0 W H" 속성을 반드시 넣을 것(W·H는 100 내외 정수 권장).
- 오직 이 요소만 쓸 것: <line> <rect> <circle> <ellipse> <polyline> <polygon> <path> <text>.
  <g>, transform 속성, <use>, <defs>, 그라디언트, 클립패스, 이미지 임베드는 절대 쓰지 말 것
  (전부 이동/회전 없이 절대좌표로, 최상위 요소로만 평평하게 나열).
- <path>의 d 속성은 M/L/H/V/Q/C/S/T/A/Z 명령만 쓰고, A(호) 명령의 large-arc-flag·
  sweep-flag는 반드시 공백이나 쉼표로 다른 숫자와 구분할 것(예: "0 1" — "01"처럼 붙여 쓰지 말 것).
- 채움(fill)·선(stroke) 색은 지정하지 않아도 된다(가져온 뒤 앱이 다시 칠한다).
- 다른 설명 없이 SVG 코드만 출력하라(```svg 코드블록으로 감싸도 되고 안 감싸도 됨)."""

_PROMPT_TEMPLATE = """다음 대상을 나타내는 간단한 선(line-art) 아이콘을 SVG로 그려라.

대상: {subject}

""" + _RULES + "\n"

# ⚠ "이미지에 실제로 있는 형태만"은 text_to_mermaid.py의 환각 방지 규칙과 같은 이유
# (`docs/image_to_ecad.md`, 2026-07-21에 처음 겪은 함정) — 모델이 참고 이미지에 없는
# 디테일(예: 상표·질감·배경 요소)까지 "그럴듯하다"며 지어내는 것을 막는다.
_IMAGE_PROMPT_TEMPLATE = """이 이미지(사진·스케치·아이콘 등)를 보고, 그 대상을
나타내는 간단한 선(line-art) 아이콘을 SVG로 그려라.
{subject_line}
이미지에 실제로 있는 형태만 단순화해 그려라 — 이미지에 없는 디테일을 임의로 추가하지 말 것.

""" + _RULES + "\n"


def build_prompt(subject: str) -> str:
    return _PROMPT_TEMPLATE.format(subject=subject.strip())


def build_image_prompt(subject: str = "") -> str:
    subject_line = f"참고(보충 설명): {subject.strip()}\n" if subject.strip() else ""
    return _IMAGE_PROMPT_TEMPLATE.format(subject_line=subject_line)


def extract_svg(raw: str) -> str:
    """모델 응답에서 SVG 텍스트만 꺼낸다 — text_to_mermaid.extract_mermaid와 동일 패턴
    (```svg 코드펜스가 섞여 나오면 벗긴다)."""
    txt = raw.strip()
    if txt.startswith("```"):
        lines = txt.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        txt = "\n".join(lines).strip()
    return txt


def generate_svg(api_key: str, subject: str, *, model: str, image=None,
                  base_url: str = gw.BASE_URL) -> tuple[str, str]:
    """대상 설명(및/또는 이미지) → (SVG 텍스트, 실제 사용된 모델). `image`(PIL Image)가
    주어지면 이미지 프롬프트로 전환되고 `subject`는 보충 설명 취급된다(비어 있어도 됨 —
    `generate_mermaid`와 동일 관례). 이미지 호출은 timeout을 넉넉히(120s) 잡는다(텍스트
    기본값 60s보다 여유, `generate_mermaid`와 동일 판단). 실패 시 예외를 그대로 올린다
    (호출자가 후보 카드에 실패로 표시)."""
    prompt = build_image_prompt(subject) if image is not None else build_prompt(subject)
    timeout = 120.0 if image is not None else 60.0
    res = gw.call_text_with_fallback(api_key, prompt, model=model, base_url=base_url,
                                     image=image, timeout=timeout)
    return extract_svg(res.content), res.model_used
