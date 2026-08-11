"""이미지→도면 CLI — §8 항목18 B단계. 실제 로직은 `easycad/ai/sketch_pipeline.py`
(2026-08-11 이동 — C단계 앱 통합이 같은 파이프라인을 가져다 쓰면서 `tools/`가 아니라
`easycad/`에 있어야 했다). 이 파일은 argparse 얇은 wrapper + 콘솔 전용 관심사만 남는다.

사용:
    set EASYCAD_GW_KEY=...          (또는 ~/.claude/.secrets/easycad-gateway.key)
    python tools/ai_sketch.py docs/reference/image (1).png out.ecad
    python tools/ai_sketch.py a.png --note "이건 방송 송신소 전원 계통도"
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from easycad.ai import gateway as gw
from easycad.ai.sketch_pipeline import build_from_image


def _fix_console_encoding():
    """Windows 한국어 로캘(cp949)에서 stdout이 UTF-8이 아니면 한글 진행 로그가 콘솔에서
    깨진다(2026-08-11 실도면 검증 중 실측 — 파일 저장은 `sketch_build.save()`가 항상
    `encoding="utf-8"`을 명시해 영향 없음, 콘솔 표시만의 문제)."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _fix_console_encoding()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image")
    ap.add_argument("out", nargs="?", default="", help="생략 시 이미지와 같은 이름의 .ecad")
    ap.add_argument("--note", default="", help="보충 설명(도면 종류 등)")
    ap.add_argument("--overview-model", default=gw.DEFAULT_MODEL)
    ap.add_argument("--tile-model", default="gpt-5.4-mini")
    ap.add_argument("--tile-threshold", type=int, default=15,
                    help="P1 항목 수가 이 값 이하면 타일링 생략")
    ap.add_argument("--max-shapes-per-tile", type=int, default=8)
    ap.add_argument("--zoom", type=int, default=3)
    ap.add_argument("--no-edge-completion", action="store_true",
                    help="P3.5 연결선 보완 패스 생략(타일 경계를 넘는 연결선 손실을 감수하고 호출 1회 절약)")
    ap.add_argument("--edge-model", default="", help="P3.5 연결선 보완에 쓸 모델(생략 시 --overview-model과 동일)")
    ap.add_argument("--light", action="store_true", help="라이트 테마 잉크색(기본은 다크)")
    args = ap.parse_args()

    out = args.out or os.path.splitext(args.image)[0] + ".ecad"
    build_from_image(args.image, out, note=args.note, overview_model=args.overview_model,
                     tile_model=args.tile_model, tile_threshold=args.tile_threshold,
                     max_shapes_per_tile=args.max_shapes_per_tile, zoom=args.zoom,
                     complete_missing_edges=not args.no_edge_completion, edge_model=args.edge_model,
                     dark=not args.light)


if __name__ == "__main__":
    main()
