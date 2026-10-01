"""사진→도면 게이트웨이 실측 — 같은 사진을 모델에 보내 ops JSON을 받고, .ecad·렌더까지 만든다.

2026-10-01 실험(`docs/history/2026-10.md` "사진→도면 재실험")을 재현·확장하는 도구. 개발용.

    python tools/sketch_ops_probe.py photo.png --model gpt-6.1-sol --mode oneshot
    python tools/sketch_ops_probe.py photo.png --model gpt-6.1-sol --mode loop --rounds 2 --out-dir tools/_sketch_ops

mode
    oneshot  원본 1장 → ops JSON 1회.
    loop     원본 + 2배 확대 조각(기본 3×2 격자, 10% 겹침) → JSON, 이후 라운드마다
             [원본 + 직전 결과 렌더 + 직전 JSON] → 수정된 전체 JSON.
키: 기본은 앱과 같은 `gateway.resolve_api_key()`. `--key-file`로 다른 키 파일(첫 줄)을 줄 수 있다.
산출물: <out-dir>/<model>_<mode>_r{N}.json/.ecad/.png + _log.json(토큰·소요초).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

from easycad.ai import gateway
from sketch_ops import build, render
from easycad.ai.photo_to_ops import TASK as TASK_APP, call, generate_ops, image_part, parse_ops as _parse

# 2026-10-01 실측에 쓴 프롬프트 원문 — 결과 비교를 위해 바꾸지 말 것(`--task v1`). 기본(`--task app`)은
# 앱 모듈 `easycad/ai/photo_to_ops.py`의 TASK(이것 + 글자 회전 rot).
TASK_V1 = """이 사진은 방송 송신소 계통도(블록 다이어그램)다. 이걸 CAD 앱에서 편집 가능한 도면으로 다시 그리려 한다.
원본 사진 크기는 {w}x{h} 픽셀이고, 모든 좌표는 이 원본 픽셀 좌표계(x 오른쪽, y 아래)로 쓴다.

출력은 JSON 객체 하나만: {{"ops": [ ... ]}}. 코드펜스·설명 금지. 사용 가능한 op:
- {{"op":"box","id":"tsd","x1":..,"y1":..,"x2":..,"y2":..,"label":"상자 안 중앙 글자(\\n 줄바꿈 가능, 없으면 생략)","font":15}}
- {{"op":"text","x":..,"y":..,"text":"자유 글자(\\n 가능)","font":13}}   ← (x,y)=글자 왼쪽 위. font는 원본 글자 높이(px)의 약 2배.
- {{"op":"line","pts":[[x,y],[x,y],...],"head":false,"src":"상자id","dst":"상자id"}}  ← 원본처럼 직각으로 꺾이는 연결선. head=true면 끝에 화살촉. src/dst는 선 끝이 닿는 상자(없으면 생략).
- {{"op":"poly","pts":[[x,y],...],"closed":false}}  ← 안테나 기호·스위치 내부 같은 장식선.
- {{"op":"circle","id":"..","cx":..,"cy":..,"r":..}}
- {{"op":"dashrect","x1":..,"y1":..,"x2":..,"y2":..}}  ← 점선/1점쇄선 테두리 영역.

규칙:
- 원본의 위치·크기를 최대한 그대로 따른다(재배치 금지).
- 원본에 실제로 그려진 선만 그린다. 논리적으로 있을 법한 선을 지어내지 않는다.
- 상자 안 포트 이름(예: THRU1, CH1(MW))과 선 옆 글자(케이블 번호 <1DJ1-1> 등)도 text로 빠짐없이 옮긴다.
- 글자는 원본 그대로(한글 포함) 정확히 읽는다.
- 상자 내부 글자가 포트 이름과 겹치면 상자 label 대신 text로 제목 위치를 직접 지정한다."""

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("--model", required=True)
    ap.add_argument("--mode", choices=["oneshot", "loop"], required=True)
    ap.add_argument("--task", choices=["app", "v1"], default="app",
                    help="app=앱 프롬프트(글자 회전 rot 포함), v1=2026-10-01 실측 원문")
    ap.add_argument("--rounds", type=int, default=2, help="loop: 첫 생성 뒤 수정 라운드 수")
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--crops-json", help='loop 조각 범위 직접 지정: [[x1,y1,x2,y2],...] (기본 3×2 격자)')
    ap.add_argument("--key-file", help="키 파일(첫 줄). 생략 시 앱과 같은 resolve_api_key()")
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "_sketch_ops"))
    a = ap.parse_args(argv)

    key = open(a.key_file, encoding="utf-8").readline().strip() if a.key_file else gateway.resolve_api_key()
    client = gateway._client(key, gateway.resolve_base_url(), timeout=600.0)
    os.makedirs(a.out_dir, exist_ok=True)
    orig = Image.open(a.photo).convert("RGB")
    W, H = orig.size
    task = (TASK_APP if a.task == "app" else TASK_V1).format(w=W, h=H)   # oneshot용
    stem = os.path.join(a.out_dir, f"{a.model}_{a.mode}")

    def save_round(r, spec, entry):
        json.dump(spec, open(f"{stem}_r{r}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        n, skipped = build(spec, f"{stem}_r{r}.ecad")
        render(f"{stem}_r{r}.ecad", f"{stem}_r{r}.png", (W, H))
        entry["skipped"] = skipped
        u = entry.get("usage") or {}
        print(f"r{r}: ops={entry['ops']} skipped={skipped} {entry['sec']:.0f}s "
              f"in={u.get('prompt_tokens')} out={u.get('completion_tokens')}"
              + (f" (수정 응답 깨짐 — 직전 결과 유지: {entry['error']})" if entry.get("error") else ""),
              flush=True)

    if a.mode == "oneshot":
        txt, usage, dt = call(client, a.model, [{"type": "text", "text": task}, image_part(orig)], a.max_tokens)
        spec = _parse(txt)
        log = [{"round": 0, "sec": round(dt, 1), "usage": usage, "ops": len(spec["ops"])}]
        save_round(0, spec, log[0])
    else:
        # 앱과 같은 루프(`photo_to_ops.generate_ops`)·같은 렌더(`photo_dialog.render_spec_pil`).
        from PyQt6.QtWidgets import QApplication
        from easycad.canvas.photo_dialog import render_spec_pil
        _app = QApplication.instance() or QApplication([])  # noqa: F841 — 렌더에 필요
        crops = json.loads(a.crops_json) if a.crops_json else None
        _, log = generate_ops(client, orig, model=a.model, render=render_spec_pil, rounds=a.rounds,
                              task=TASK_APP if a.task == "app" else TASK_V1, crops=crops,
                              max_tokens=a.max_tokens, on_round=save_round)
    json.dump(log, open(f"{stem}_log.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
