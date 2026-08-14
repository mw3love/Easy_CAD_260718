"""AI SVG 에셋 생성 게이트웨이 실측 — A단계(신규 §8 항목, 2026-08-14 deep-interview).

gpt/gemini 텍스트 모델이 이 앱의 SVG 임포터(fileio/svg_import.py)가 실제로 파싱 가능한
형태의 SVG 코드를 만들어내는지 확인한다. "모델이 뭘 낼 수 있는가"가 아니라 "우리 파서가
받을 수 있는 형태로 낼 수 있는가"가 질문이라, 임포터가 지원하는 요소·미지원 사항(<g
transform> 등)을 프롬프트에 그대로 반영했다(svg_import.py 모듈 docstring 참조).

게이트웨이 호출은 새로 안 만들고 `easycad/ai/gateway.py`(Mermaid AI 보조가 이미 검증해
쓰는 것)를 그대로 재사용한다 — 프롬프트 빌더·코드펜스 벗기기는 `text_to_mermaid.py`와
동일 패턴.

사용법:
    python tools/svg_asset_probe.py
    python tools/svg_asset_probe.py --models gpt-5.4-mini,gemini-3.6-flash
    python tools/svg_asset_probe.py --prompts "안테나 아이콘,BNC 커넥터 아이콘"
    python tools/svg_asset_probe.py --out-dir tools/_svg_probe_out
"""
import argparse
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from easycad.ai import gateway as gw

# KBS 방송 송신소 계통도에서 실제로 쓰일 법한 아이콘들 — 이 프로젝트의 심볼 팔레트
# 도메인(안테나·증폭기·랙 등, docs/history/2026-08.md "심볼 종류 추가" 참조)과 맞춤.
DEFAULT_PROMPTS = [
    "동축케이블 커넥터(BNC) 아이콘",
    "안테나(야기) 아이콘",
    "압력/전력 게이지(미터) 아이콘",
    "송신기 랙 장비 아이콘",
]

# svg_import.py가 실제로 지원/미지원하는 것을 그대로 프롬프트 규칙으로 옮김(모듈 docstring
# 13~22줄 참조) — "모델이 예쁘게 그릴 수 있는가"가 아니라 "우리 파서가 받을 수 있는가".
_SVG_PROMPT_TEMPLATE = """다음 대상을 나타내는 간단한 선(line-art) 아이콘을 SVG로 그려라.

대상: {subject}

규칙(반드시 지킬 것 — 이 SVG는 전용 파서로 다시 읽어들여 편집 가능한 도형으로 변환된다):
- 루트 <svg>에 viewBox="0 0 W H" 속성을 반드시 넣을 것(W·H는 100 내외 정수 권장).
- 오직 이 요소만 쓸 것: <line> <rect> <circle> <ellipse> <polyline> <polygon> <path> <text>.
  <g>, transform 속성, <use>, <defs>, 그라디언트, 클립패스, 이미지 임베드는 절대 쓰지 말 것
  (전부 이동/회전 없이 절대좌표로, 최상위 요소로만 평평하게 나열).
- <path>의 d 속성은 M/L/H/V/Q/C/S/T/A/Z 명령만 쓰고, A(호) 명령의 large-arc-flag·
  sweep-flag는 반드시 공백이나 쉼표로 다른 숫자와 구분할 것(예: "0 1" — "01"처럼 붙여 쓰지 말 것).
- 채움(fill)·선(stroke) 색은 지정하지 않아도 된다(가져온 뒤 앱이 다시 칠한다).
- 다른 설명 없이 SVG 코드만 출력하라(```svg 코드블록으로 감싸도 되고 안 감싸도 됨).
"""


def build_prompt(subject: str) -> str:
    return _SVG_PROMPT_TEMPLATE.format(subject=subject)


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


def try_parse(svg_text: str):
    """well-formed XML인지 + 실제 파서(parse_svg_items)가 아이템을 뽑아내는지 확인.
    반환 (성공여부, (아이템수, 종류별개수, viewBox) 또는 에러메시지 문자열)."""
    try:
        ET.fromstring(svg_text)
    except ET.ParseError as e:
        return False, f"XML parse error: {e}"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False,
                                     encoding="utf-8") as f:
        f.write(svg_text)
        tmp_path = f.name
    try:
        from easycad.fileio.svg_import import parse_svg_items
        items, vb = parse_svg_items(tmp_path)
    except Exception as e:  # noqa: BLE001 — 파서 실패 원인을 그대로 보고
        return False, f"parse_svg_items 실패: {type(e).__name__}: {e}"
    finally:
        os.remove(tmp_path)
    if not items:
        return False, "파싱은 됐으나 아이템 0개(전부 미지원 요소였을 가능성)"
    kinds = {}
    for it in items:
        k = type(it).__name__
        kinds[k] = kinds.get(k, 0) + 1
    return True, (len(items), kinds, vb)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", default=f"{gw.TEXT_RECOMMEND_1},{gw.TEXT_RECOMMEND_2}")
    ap.add_argument("--prompts", default="", help="쉼표구분, 생략 시 기본 4종")
    ap.add_argument("--out-dir", default="", help="생성된 SVG 원문을 저장할 폴더(생략 시 저장 안 함)")
    args = ap.parse_args()

    api_key = gw.resolve_api_key()
    if not api_key:
        sys.exit(f"API 키를 찾을 수 없습니다 — {gw.SECRETS_FILE} 또는 "
                 f"환경변수 {gw.KEY_ENV}를 확인하세요.")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    subjects = [p.strip() for p in args.prompts.split(",") if p.strip()] or DEFAULT_PROMPTS

    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)

    results = []
    for subject in subjects:
        prompt = build_prompt(subject)
        for model in models:
            try:
                res = gw.call_text_with_fallback(api_key, prompt, model=model, timeout=60.0)
            except Exception as e:  # noqa: BLE001
                print(f"[FAIL:call] {model} / {subject!r}: {type(e).__name__}: {e}")
                results.append((subject, model, False))
                continue
            svg = extract_svg(res.content)
            ok, info = try_parse(svg)
            tag = "OK" if ok else "PARSE-FAIL"
            print(f"[{tag}] {model} / {subject!r} ({res.elapsed:.1f}s, {len(svg)} chars)")
            if ok:
                n, kinds, vb = info
                print(f"       items={n} kinds={kinds} viewBox={vb}")
            else:
                print(f"       {info}")
                print("       " + svg[:300].replace("\n", " "))
            if args.out_dir:
                safe = re.sub(r"[^\w가-힣]+", "_", f"{model}_{subject}")[:60]
                with open(os.path.join(args.out_dir, f"{safe}.svg"), "w",
                         encoding="utf-8") as f:
                    f.write(svg)
            results.append((subject, model, ok))

    n_ok = sum(1 for r in results if r[2])
    print(f"\n합계: {n_ok}/{len(results)} 성공")


if __name__ == "__main__":
    main()
