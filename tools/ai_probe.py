"""AI 게이트웨이 vision 프로브 — 이미지→도면(§8 항목18) 착수 전 실측 도구.

설계·측정 결과 전문은 `docs/ai_image_import.md`. 이 스크립트는 그 문서의 실측값을 만든
코드이고, A단계(`easycad/ai/gateway.py`)의 출발점으로 그대로 재사용할 수 있다.

확인하는 것 3가지:
  1. `json_schema`(structured output)가 이 게이트웨이에서 통하는가
  2. 밀집 실도면 1장에서 블록/연결을 몇 개나 잡는가 (모델별 비교)
  3. 구획 크롭(줌인)이 실제로 인식률을 올리는가 — "작은 요소 누락은 입력 해상도 탓" 가설

사용:
    set EASYCAD_GW_KEY=...            (PowerShell: $env:EASYCAD_GW_KEY="...")
    python tools/ai_probe.py                          # 기본 모델로 크롭+전체
    python tools/ai_probe.py --model gemini-3.6-flash
    python tools/ai_probe.py --image "some/drawing.png" --full-only

⚠ 실측으로 확인된 함정(`docs/pitfalls.md` "AI 게이트웨이 호출" 참조):
  - `urllib`로 치면 SSL 검증 실패(self-signed in chain) — openai SDK/httpx만 쓸 것.
  - `claude-*` 계열은 밀집 도면 전체 이미지에서 504(축소해도 동일). gemini 계열이 기본.
"""
import argparse
import base64
import io
import json
import os
import sys
import time

BASE_URL = "https://factchat.mindlogic-kr-api.com/v1/gateway"
KEY_ENV = "EASYCAD_GW_KEY"
DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_IMAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "docs", "reference", "image (1).png")

# 중간 JSON 스키마 — `easycad/fileio/sketch_build.py`의 Sketch 빌더 API를 미러링한다.
# 필드를 늘리기 전에 빌더가 그걸 지원하는지 먼저 확인할 것(스키마가 빌더보다 앞서면
# 변환기에서 조용히 버려진다).
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["shapes", "edges", "unknown"],
    "properties": {
        "shapes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "kind", "x", "y", "w", "h", "label"],
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["box", "ellipse", "decision", "terminal"]},
                    "x": {"type": "number"}, "y": {"type": "number"},
                    "w": {"type": "number"}, "h": {"type": "number"},
                    "label": {"type": "string"},
                },
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["from", "to", "label"],
                "properties": {
                    "from": {"type": "string"}, "to": {"type": "string"},
                    "label": {"type": "string"},
                },
            },
        },
        "unknown": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["x", "y", "w", "h", "desc"],
                "properties": {
                    "x": {"type": "number"}, "y": {"type": "number"},
                    "w": {"type": "number"}, "h": {"type": "number"},
                    "desc": {"type": "string"},
                },
            },
        },
    },
}

# ⚠ "실제로 그려진 연결선만"은 반드시 유지할 것 — 2026-07-21 실조건 함정(`image_to_ecad.md`):
# 모델이 "이 흐름이면 여기로 돌아가야 논리적"이라며 원본에 없는 화살표를 만들어낸다.
PROMPT = """이 이미지는 방송 송신소 계통도(블록 다이어그램)다. 편집 가능한 CAD 도형으로 복원하려 한다.

규칙:
- 좌표는 이 이미지의 픽셀 좌표 그대로. 원점은 좌상단. 이미지 크기: {w}x{h}
- shapes: 사각형 블록 하나당 항목 하나. label은 박스 안 텍스트 그대로(한글 포함).
- edges: **실제로 그려진 연결선만**. 논리적으로 있어야 할 것 같다고 없는 선을 추가하지 말 것.
- unknown: 사각형·타원으로 표현 못 하는 도형(안테나 픽토그램 등)만.
- 점선 그룹 테두리(구획 박스)는 shapes에 포함하지 말 것.
"""


def _client(timeout=600.0):
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("openai 패키지 미설치: pip install openai")
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        sys.exit(f"환경변수 {KEY_ENV}에 게이트웨이 API 키를 넣어 주세요.")
    return OpenAI(api_key=key, base_url=BASE_URL, timeout=timeout, max_retries=0)


def _b64_png(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def call(client, model, img, *, use_schema=True, max_tokens=16384):
    """단일 vision 호출. 반환 (본문 문자열, 소요초).

    max_tokens를 크게 잡는 이유는 pasteflow ocr_engine과 같다 — 게이트웨이가 reasoning
    토큰을 같은 예산에서 차감해, 작게 잡으면 thinking 모델에서 본문이 잘린다."""
    kw = {}
    if use_schema:
        kw["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "drawing", "schema": SCHEMA, "strict": True},
        }
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64_png(img)}"}},
            {"type": "text", "text": PROMPT.format(w=img.width, h=img.height)},
        ]}],
        **kw,
    )
    return (resp.choices[0].message.content or ""), time.time() - t0


def parse(raw: str):
    """모델 응답에서 JSON을 꺼낸다. 스키마를 안 쓴 폴백 경로는 ```json 펜스가 섞여 나온다."""
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1]
        if txt[:4].lower().startswith("json"):
            txt = txt[txt.find("\n"):]
    return json.loads(txt)


def summarize(tag, raw, dt):
    print(f"\n===== {tag} ({dt:.1f}s, {len(raw)} chars) =====")
    try:
        d = parse(raw)
    except Exception as e:
        print("JSON PARSE FAIL:", e)
        print(raw[:600])
        return None
    print(f"shapes={len(d.get('shapes', []))} edges={len(d.get('edges', []))} "
          f"unknown={len(d.get('unknown', []))}")
    for s in d.get("shapes", [])[:8]:
        print(f"  {s['id']:>10} ({s['x']:>5.0f},{s['y']:>5.0f}) "
              f"{s['w']:>4.0f}x{s['h']:<4.0f} {s['label']!r}")
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    ap.add_argument("--crop", nargs=4, type=int, metavar=("L", "T", "R", "B"),
                    default=[55, 50, 415, 210],
                    help="구획 크롭 영역(기본값은 기준 이미지의 1UHD 구획)")
    ap.add_argument("--zoom", type=int, default=3, help="크롭 확대 배율")
    ap.add_argument("--full-only", action="store_true")
    ap.add_argument("--crop-only", action="store_true")
    ap.add_argument("--out", default="", help="결과 JSON을 쓸 경로(생략 시 저장 안 함)")
    args = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow 미설치: pip install pillow")

    client = _client()
    full = Image.open(args.image).convert("RGB")
    result = None

    if not args.full_only:
        crop = full.crop(tuple(args.crop))
        if args.zoom != 1:
            crop = crop.resize((crop.width * args.zoom, crop.height * args.zoom), Image.LANCZOS)
        try:
            raw, dt = call(client, args.model, crop)
            result = summarize(f"{args.model} / 크롭 {args.zoom}x / json_schema", raw, dt)
        except Exception as e:
            print("CROP+SCHEMA FAIL:", type(e).__name__, str(e)[:400])
            raw, dt = call(client, args.model, crop, use_schema=False)
            result = summarize(f"{args.model} / 크롭 {args.zoom}x / 스키마 없음(폴백)", raw, dt)

    if not args.crop_only:
        try:
            raw, dt = call(client, args.model, full)
            result = summarize(f"{args.model} / 전체 {full.width}x{full.height} / json_schema",
                               raw, dt) or result
        except Exception as e:
            print("FULL FAIL:", type(e).__name__, str(e)[:400])

    if args.out and result is not None:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(f"\n→ {args.out}")


if __name__ == "__main__":
    main()
