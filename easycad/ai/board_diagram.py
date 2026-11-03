"""웹 칠판 「🔷 도형 그리기」(2026-11-03 사용자 — 「계통도 그려 줘」가 고칠 수 있는 상자 + 붙은 화살표로). Qt 비의존.

데스크톱 흐름도와 같은 길(§8 항목52): AI는 「내용 설계서」 JSON만(`text_to_flow`), 자리는 앱 규칙(`flow_spec.layout`·`best_wrap`).
데스크톱은 글 폭을 Qt로 재지만 서버엔 Qt가 없어 글자 수로 짐작한다(한글 한 자 = 글자 크기 — 웹 `chart.js textW`와 같은 셈).
칠판(`web/src/next/flowboard.js`)이 받은 자리로 띠·상자·붙은 화살표를 짓는다 — 규칙이 서버 한 곳에 있어 두 앱이 같은 모양.

검토한 대안: 배치를 웹 JS로 옮기기 — 웹도 글 폭은 짐작이라 나을 게 없고, 이어 고치기는 어차피 AI(서버)를 거쳐서 버림.
0단계 실측(2026-11-03, 네 문장): sonnet 6~13초·11~20cr 가장 알참(송신소 STL·감시·전원) · terra 8~11초·3~5cr 얕음 · sol 비쌈 · gemini-lite 모양 틀림.
"""
from __future__ import annotations

import json
import re
import time

from easycad.ai import gateway as gw
from easycad.ai.text_to_flow import generate_flow
from easycad.fileio.flow_spec import best_wrap, layout, parse_spec, ranks_of

DIAGRAM_MODEL = "claude-sonnet-5-5"   # 사용자 선택(2026-11-03) — 「모델 설정」에서 terra 등으로 바꿀 수 있음

# 앞 도형 답(또는 고른 도형 판)을 두고 한 말이 고치는 말인가 — 아니면 새로 그림
FOLLOW_WORDS = re.compile(r"추가|더\s*(넣|그려|붙)|빼|지워|없애|바꿔|바꾸|고쳐|넣어|이어|연결|세로로|가로로|나눠|합쳐|줄여|늘려|이름|하나\s*더|대신|옮겨|순서")

LABEL_PT, HEAD_PT, TITLE_PT = 12, 11, 15   # 데스크톱 `_FLOW_LABEL_PT`·`_FLOW_HEAD_PT`·`_FLOW_TITLE_PT`
PX = 4.0 / 3.0                            # pt → 칠판 단위
NODE_W, NODE_H, NODE_W_MAX = 120.0, 56.0, 280.0   # 데스크톱 `_MMD_NODE_*`
WRAP_BOX, WRAP_DECISION = 190.0, 250.0    # 한 줄이면 이 폭을 넘을 때만 두 줄(`_FLOW_WRAP_*`)
ICON_H = 0.0                              # 웹은 아이콘 칸 없음(내 심볼은 브라우저마다 달라 서버가 모름)
MARGIN = 8.0                              # 글 상자 안쪽 여백 두 배(데스크톱 documentMargin × 2)
LINE = 1.3                                # 줄 높이 = 글자 크기 × 1.3
# 도형 안 글이 들어가는 폭 비율(데스크톱 `_label_inset_ratio` — 마름모 가장 좁게)
RATIO = {"decision": 0.55, "start": 0.8, "end": 0.8, "data": 0.75, "document": 0.8, "database": 0.8, "step": 0.85}


def text_w(s: str, pt: float) -> float:
    """한 줄 글 폭(칠판 단위) — 한글·한자 = 글자 크기, 그 밖 0.56배(웹 `textW`)."""
    fs = pt * PX
    return sum(fs if ord(ch) >= 0x2E80 else fs * 0.56 for ch in s)


def wrap_two(text: str, pt: float) -> str:
    """가장 긴 줄이 가장 짧아지는 띄어쓰기 한 곳에서 두 줄로(데스크톱 `_mermaid_wrap`). 띄어쓰기가 없으면 그대로."""
    best = None
    for i, ch in enumerate(text):
        if ch == " ":
            a, b = text[:i].rstrip(), text[i + 1:].lstrip()
            if a and b:
                w = max(text_w(a, pt), text_w(b, pt))
                if best is None or w < best[0]:
                    best = (w, a + "\n" + b)
    return best[1] if best else text


def box_sizes(spec) -> dict:
    """단계마다 (w, h) — 보통 상자끼리 같게(가장 긴 글에 맞춤), 마름모끼리 같게. 긴 글은 두 줄로 단계 글을 고친다(데스크톱 `_flow_box_sizes`)."""
    line_h = LABEL_PT * PX * LINE
    groups = {"box": [], "decision": []}
    for s in spec.steps:
        ratio = RATIO.get(s.kind, 0.85)
        limit = WRAP_DECISION if s.kind == "decision" else WRAP_BOX
        if "\n" not in s.text and (text_w(s.text, LABEL_PT) + MARGIN) / ratio > limit:
            s.text = wrap_two(s.text, LABEL_PT)
        parts = s.text.split("\n")
        need = (max(text_w(t, LABEL_PT) for t in parts) + MARGIN) / ratio + 2.0
        groups["decision" if s.kind == "decision" else "box"].append((s.id, need, len(parts)))
    out = {}
    for name, rows in groups.items():
        if not rows:
            continue
        lines = max(n for _i, _w, n in rows)
        if name == "decision":
            w = min(NODE_W_MAX * 1.25, max(NODE_W * 1.2, max(w for _i, w, _n in rows)))
            h = max(NODE_H * 1.35, lines * line_h * 2 + MARGIN)
        else:
            w = min(NODE_W_MAX, max(NODE_W, max(w for _i, w, _n in rows)))
            h = max(NODE_H, lines * line_h + MARGIN + 8)
            if lines >= 2 and any(s.kind in ("database", "document") for s in spec.steps):
                h += line_h * 0.6
        for sid, _w, _n in rows:
            out[sid] = (w, h)
    return out


GAP_MAJOR = 72.0                          # `flow_spec.layout` 기본 칸 간격
# 라벨 양옆에 남길 선 = (화살촉 11 + 보이는 선 10) × 2 + 라벨 자리 비움 4(웹 render.jsx `arrowLabels` gap) — 2026-11-03 사용자:
# 「예비 전원」 라벨이 72 간격을 다 덮어 화살촉만 살짝 보였음(라벨 폭 73)
LABEL_ROOM = 46.0


def label_gaps(spec) -> dict:
    """가로 흐름에서 옆 칸 상자로 곧게 가는 라벨 화살표(같은 띠·바로 다음 칸)가 있으면 그 칸 뒤 간격을 라벨이 들어가게 넓힘 → {칸: 간격}."""
    rank, lane = ranks_of(spec), {s.id: s.lane for s in spec.steps}
    out: dict = {}
    for k in spec.links:
        if not k.text or rank.get(k.dst) != rank.get(k.src, -9) + 1 or lane.get(k.src) != lane.get(k.dst):
            continue
        need = max(text_w(t, LABEL_PT) for t in k.text.split("\n")) + LABEL_ROOM
        if need > GAP_MAJOR:
            out[rank[k.src]] = max(out.get(rank[k.src], 0.0), round(need, 1))
    return out


def place(spec_json: str) -> dict:
    """설계서 글 → 칠판이 지을 자리 {"steps": [{id, text(줄바꿈 반영), kind, lane, box: [x, y, w, h], seg}], "links": [{from, to, text}],
    "lanes": [{name, rect, head}], "title", "direction", "focus", "width", "height", "ranks": {id: 칸}}. 좌표는 왼쪽 위 = (0, 0)."""
    spec = parse_spec(spec_json)
    sizes = box_sizes(spec)
    size_fn = lambda s: sizes[s.id]   # noqa: E731
    horizontal = spec.direction in ("LR", "RL")
    if horizontal:   # 이름표 = 띠 왼쪽 칸(긴 이름은 두 줄)
        names = [wrap_two(n, HEAD_PT) if text_w(n, HEAD_PT) > 110 else n for n in spec.lanes]
        head = max((max(text_w(t, HEAD_PT) for t in n.split("\n")) for n in names), default=0.0) + 28.0
    else:
        names = list(spec.lanes)
        head = HEAD_PT * PX * LINE + 26.0
    gaps = label_gaps(spec) if horizontal else {}
    wrap = best_wrap(spec, size_fn, head=head, icon_h=ICON_H, gaps=gaps)
    lay = layout(spec, size_fn, head=head, icon_h=ICON_H, wrap=wrap, gaps=gaps)
    shown = dict(zip(spec.lanes, names))
    r = lambda t: [round(v, 1) for v in t]   # noqa: E731
    return {
        "title": spec.title, "direction": spec.direction, "focus": spec.focus,
        "width": round(lay.width, 1), "height": round(lay.height, 1), "ranks": lay.ranks,
        "steps": [{"id": s.id, "text": s.text, "kind": s.kind, "lane": s.lane, "box": r(lay.boxes[s.id]),
                   "seg": lay.segments.get(s.id, 0)} for s in spec.steps],
        "links": [{"from": k.src, "to": k.dst, **({"text": k.text} if k.text else {})} for k in spec.links],
        "lanes": [{"name": shown.get(lb.name, lb.name), "key": lb.name, "rect": r(lb.rect), "head": r(lb.head)} for lb in lay.lanes],
    }


def make(key: str, ask: str, *, base_spec: str = "", model: str = DIAGRAM_MODEL, base_url: str | None = None) -> dict:
    """말 → {"spec": 설계서 글(이어 고치기 때 그대로 다시 보냄), "place": 칠판 자리(`place`), "model", "elapsed"}.
    `base_spec` = 앞 설계서 글 — 있으면 그 설계서를 말대로 고침(바뀐 곳만)."""
    t0 = time.time()
    txt, used = generate_flow(key, ask, model=model, base_url=base_url or gw.resolve_base_url(), base_code=base_spec)
    json.loads(txt)   # generate_flow가 parse_spec으로 다듬은 글 — 혹시 Mermaid로 빠졌으면(앞 글이 Mermaid) 여기서 오류
    return {"spec": txt, "place": place(txt), "model": used, "elapsed": round(time.time() - t0, 1)}
