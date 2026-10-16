"""AI 흐름도 「내용 설계서」(§8 항목52, 2026-10-16 Magic Board 개편) — 형식 읽기·검사와 배치 규칙.

AI는 Mermaid 대신 내용만 JSON으로 쓴다(담당 묶음 `lanes`·단계 `steps`·연결 `links`·중요한 단계 하나 `focus`·아이콘 이름).
배치·색·크기는 앱이 규칙으로 정한다 — 좌표를 AI에 맡기면 겹치고, Mermaid는 관계만 담아 가져오기가 색·묶음을 버렸다
(`mermaid_import.py`가 classDef·subgraph를 건너뜀 → "네모 나열"). 그림으로 만드는 건 `host_fileio._build_flowspec_items`.

배치 규칙(`layout`): 흐름 방향으로 단계마다 칸(rank — 앞 단계에서 가장 긴 길이), 담당마다 띠(가로 흐름이면 가로 띠,
세로 흐름이면 세로 띠). 한 띠의 같은 칸에 단계가 여럿이면 줄(track)을 늘린다. 되돌아가는 연결(다시 시도 같은 고리)은
칸 계산에서 뺀다. 띠가 없으면(묶음이 하나뿐) 띠·이름표 없이 같은 규칙.

**PyQt 비의존** — 글자 크기 재기는 호출부가 `size_of`로 넘긴다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

KINDS = ("start", "end", "step", "decision", "data", "document", "database")
DIRECTIONS = ("LR", "TD", "RL", "BT")
_KIND_ALIAS = {"process": "step", "task": "step", "terminal": "start", "begin": "start", "stop": "end",
               "finish": "end", "judge": "decision", "condition": "decision", "if": "decision", "io": "data",
               "input": "data", "output": "data", "doc": "document", "db": "database", "storage": "database"}


class FlowSpecError(ValueError):
    pass


@dataclass
class Step:
    id: str
    text: str
    lane: str = ""
    kind: str = "step"
    icon: str = ""


@dataclass
class Link:
    src: str
    dst: str
    text: str = ""


@dataclass
class FlowSpec:
    title: str = ""
    direction: str = "LR"
    lanes: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    focus: str = ""

    def to_json(self) -> str:
        """결과 글(`req.result_text`) — 이어 고치기 때 AI에 그대로 다시 보낸다. 빈 칸(아이콘 없음 등)은 줄여 짧게."""
        steps = []
        for s in self.steps:
            d = {"id": s.id, "text": s.text}
            if s.lane:
                d["lane"] = s.lane
            if s.kind != "step":
                d["kind"] = s.kind
            if s.icon:
                d["icon"] = s.icon
            steps.append(d)
        links = [{"from": k.src, "to": k.dst, **({"text": k.text} if k.text else {})} for k in self.links]
        data = {"title": self.title, "direction": self.direction, "lanes": self.lanes, "steps": steps,
                "links": links, "focus": self.focus}
        lines = ["{"]
        for key in ("title", "direction", "lanes", "focus"):
            lines.append(f' "{key}": {json.dumps(data[key], ensure_ascii=False)},')
        for key in ("steps", "links"):   # 한 줄에 하나씩 — 사람이 읽고 비교하기 쉽게
            rows = ",\n  ".join(json.dumps(v, ensure_ascii=False) for v in data[key])
            lines.append(f' "{key}": [\n  {rows}\n ]' + ("," if key == "steps" else ""))
        lines.append("}")
        return "\n".join(lines)


def _strip_fence(raw: str) -> str:
    t = (raw or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def looks_like_spec(text: str) -> bool:
    """결과 글이 설계서(JSON)인가 — 아니면 Mermaid(가져오기·「풀어 그리기」)."""
    return _strip_fence(text).startswith("{")


def parse_spec(raw: str) -> FlowSpec:
    """모델 응답 → FlowSpec. 너그럽게 읽는다: 코드펜스·앞뒤 말은 걷고 첫 `{`~마지막 `}`만, 모르는 종류는 step, 없는 단계로
    가는 연결은 버림, 이름 없는 담당은 앞 단계 담당으로. 단계가 하나도 없으면 FlowSpecError."""
    txt = _strip_fence(raw)
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b <= a:
        raise FlowSpecError("설계서(JSON)를 찾지 못했어요")
    try:
        data = json.loads(txt[a:b + 1])
    except json.JSONDecodeError as ex:
        raise FlowSpecError(f"설계서(JSON)를 읽지 못했어요: {ex.msg}") from None
    if not isinstance(data, dict):
        raise FlowSpecError("설계서(JSON)가 객체가 아니에요")

    direction = str(data.get("direction") or "LR").strip().upper()
    direction = "TD" if direction == "TB" else direction
    if direction not in DIRECTIONS:
        direction = "LR"
    lanes: list[str] = []
    raw_lanes = data.get("lanes")
    for v in raw_lanes if isinstance(raw_lanes, list) else []:   # 글 한 줄이면 글자마다 띠가 됐다
        name = str((v.get("name") or v.get("id") or "") if isinstance(v, dict) else v).strip()
        if name and name not in lanes:
            lanes.append(name)

    steps: list[Step] = []
    seen: set[str] = set()
    prev_lane = ""
    for i, v in enumerate(data.get("steps") or data.get("nodes") or []):
        if not isinstance(v, dict):
            continue
        text = str(v.get("text") or v.get("label") or v.get("name") or "").strip()
        sid = str(v.get("id") or "").strip() or f"s{i + 1}"
        if not text or sid in seen:
            continue
        seen.add(sid)
        kind = str(v.get("kind") or v.get("type") or "step").strip().lower()
        kind = _KIND_ALIAS.get(kind, kind)
        if kind not in KINDS:
            kind = "step"
        lane = str(v.get("lane") or "").strip()
        if lanes and not lane:
            lane = prev_lane or lanes[0]
        if lane and lane not in lanes:
            lanes.append(lane)
        prev_lane = lane or prev_lane
        steps.append(Step(sid, text, lane, kind, str(v.get("icon") or "").strip()))
    if not steps:
        raise FlowSpecError("단계가 하나도 없어요")
    if len(lanes) < 2:   # 묶음이 하나뿐이면 띠는 뜻이 없다
        lanes = []
        for s in steps:
            s.lane = ""

    links: list[Link] = []
    for v in data.get("links") or data.get("edges") or []:
        if not isinstance(v, dict):
            continue
        src = str(v.get("from") or v.get("src") or "").strip()
        dst = str(v.get("to") or v.get("dst") or "").strip()
        if src in seen and dst in seen and src != dst:
            links.append(Link(src, dst, str(v.get("text") or v.get("label") or "").strip()))
    focus = str(data.get("focus") or "").strip()
    return FlowSpec(title=str(data.get("title") or "").strip(), direction=direction, lanes=lanes, steps=steps,
                    links=links, focus=focus if focus in seen else "")


def with_direction(raw: str, direction: str) -> str:
    """방향만 바꾼 설계서 글(결과 막대 「세로로」 — AI 호출 없음)."""
    spec = parse_spec(raw)
    spec.direction = direction
    return spec.to_json()


def step_keys(spec: FlowSpec) -> dict[str, tuple]:
    """단계 id → 비교 열쇠(글, 종류) — 이어 고친 결과와 원본에서 달라진 곳 표시용(AI가 id만 바꿔도 글이 같으면 같은 것)."""
    return {s.id: (s.text, s.kind) for s in spec.steps}


def link_key(spec: FlowSpec, link: Link) -> tuple:
    by = {s.id: s.text for s in spec.steps}
    return (by.get(link.src, link.src), by.get(link.dst, link.dst), link.text)


def all_keys(spec: FlowSpec) -> list[tuple]:
    sk = step_keys(spec)
    return [sk[s.id] for s in spec.steps] + [link_key(spec, k) for k in spec.links]


# ---- 배치 ---------------------------------------------------------------------------------

@dataclass
class LaneBox:
    name: str
    rect: tuple[float, float, float, float]      # 띠 전체(x, y, w, h)
    head: tuple[float, float, float, float]      # 이름표 자리


@dataclass
class FlowLayout:
    boxes: dict[str, tuple[float, float, float, float]]   # 단계 id → (x, y, w, h)
    lanes: list[LaneBox]
    ranks: dict[str, int]
    width: float
    height: float
    segments: dict[str, int] = field(default_factory=dict)   # 단계 id → 꺾은 덩어리 번호(0부터)


def _back_links(spec: FlowSpec) -> set[int]:
    """되돌아가는 연결(고리)의 번호 — 들어오는 연결이 없는 단계부터 목록 순서로 깊이 우선으로 걸으며, 걷는 중인 단계로
    돌아가는 연결을 고른다(목록 순서가 곧 AI가 쓴 흐름 순서라 "다시 시도"가 거꾸로 잡힌다)."""
    out: dict[str, list[tuple[int, str]]] = {s.id: [] for s in spec.steps}
    indeg = {s.id: 0 for s in spec.steps}
    for i, k in enumerate(spec.links):
        out[k.src].append((i, k.dst))
        indeg[k.dst] += 1
    state: dict[str, int] = {}   # 1=걷는 중, 2=끝
    back: set[int] = set()
    order = [s.id for s in spec.steps if indeg[s.id] == 0] + [s.id for s in spec.steps]
    for root in order:
        if root in state:
            continue
        stack = [(root, iter(out[root]))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                continue
            i, dst = nxt
            st = state.get(dst)
            if st == 1:
                back.add(i)
            elif st is None:
                state[dst] = 1
                stack.append((dst, iter(out[dst])))
    return back


def ranks_of(spec: FlowSpec) -> dict[str, int]:
    """단계마다 칸 번호 = 시작에서 오는 가장 긴 길(되돌아가는 연결은 뺌)."""
    back = _back_links(spec)
    preds: dict[str, list[str]] = {s.id: [] for s in spec.steps}
    for i, k in enumerate(spec.links):
        if i not in back:
            preds[k.dst].append(k.src)
    rank: dict[str, int] = {}

    def visit(sid, guard):
        if sid in rank:
            return rank[sid]
        if sid in guard:   # 남은 고리(이론상 없음) — 0으로
            return 0
        guard.add(sid)
        r = max((visit(p, guard) + 1 for p in preds[sid]), default=0)
        guard.discard(sid)
        rank[sid] = r
        return r

    for s in spec.steps:
        visit(s.id, set())
    return rank


def layout(spec: FlowSpec, size_of, *, gap_major: float = 72.0, gap_minor: float = 34.0,
           lane_pad: float = 22.0, lane_gap: float = 10.0, head: float = 0.0, icon_h: float = 0.0,
           wrap: int | None = None) -> FlowLayout:
    """단계 자리 계산. `size_of(step) → (w, h)` 상자 크기. `head` = 띠 이름표 자리 두께(가로 흐름이면 띠 왼쪽 폭, 세로
    흐름이면 띠 위 높이). `icon_h` = 아이콘이 있는 단계 위에 비워 둘 높이(있는 단계가 하나라도 있으면 모든 줄에).
    `wrap`(칸 수)을 주면 그만큼씩 꺾어 내린다(`best_wrap`이 고른다). 좌표는 왼쪽 위가 (0, 0)."""
    horizontal = spec.direction in ("LR", "RL")
    rank = ranks_of(spec)
    n_ranks = max(rank.values(), default=0) + 1
    lane_names = spec.lanes or [""]
    lane_ix = {name: i for i, name in enumerate(lane_names)}
    sizes = {s.id: size_of(s) for s in spec.steps}
    has_icon = any(s.icon for s in spec.steps) and icon_h > 0
    extra = icon_h if has_icon else 0.0

    # 흐름축(칸) 두께는 칸마다, 교차축(줄) 두께는 모두 같게 — 같은 줄의 상자가 한 줄로 서게.
    def flow_len(s):
        w, h = sizes[s.id]
        return w if horizontal else h + extra

    def cross_len(s):
        w, h = sizes[s.id]
        return h + extra if horizontal else w

    col = [0.0] * n_ranks
    for s in spec.steps:
        col[rank[s.id]] = max(col[rank[s.id]], flow_len(s))
    cell = max(cross_len(s) for s in spec.steps)

    # 띠·칸마다 단계 묶기 → 줄 순서: 앞 칸 이웃들의 줄 평균(없으면 목록 순서)
    order = {s.id: i for i, s in enumerate(spec.steps)}
    preds: dict[str, list[str]] = {s.id: [] for s in spec.steps}
    for k in spec.links:
        if rank[k.src] < rank[k.dst]:
            preds[k.dst].append(k.src)
    cells: dict[tuple[int, int], list[str]] = {}
    for s in spec.steps:
        cells.setdefault((lane_ix[s.lane if s.lane in lane_ix else lane_names[0]], rank[s.id]), []).append(s.id)
    # 꺾어 내리기(2026-10-16) — 칸을 `wrap`개씩 덩어리로 나눠 다음 덩어리는 교차축으로(가로 흐름이면 아래 줄, 세로 흐름이면
    # 오른쪽 열) 처음부터 다시 — 책 읽는 순서. 덩어리마다 띠·이름표를 다시 그린다.
    per = max(1, int(wrap)) if wrap else n_ranks
    seg_of = [r // per for r in range(n_ranks)]
    n_seg = (n_ranks + per - 1) // per
    tracks = [[1] * len(lane_names) for _ in range(n_seg)]
    for (li, r), ids in cells.items():
        tracks[seg_of[r]][li] = max(tracks[seg_of[r]][li], len(ids))
    pos_cross: dict[str, float] = {}   # 줄 위치(띠 안 0..tracks-1, 가운데 맞춤 반영) — 정렬 기준
    for r in range(n_ranks):
        for li in range(len(lane_names)):
            ids = cells.get((li, r))
            if not ids:
                continue

            def key(sid):
                ps = [pos_cross[p] + 1000 * lane_ix.get(_lane_of(spec, p), 0) for p in preds[sid] if p in pos_cross]
                return (sum(ps) / len(ps) - 1000 * li if ps else 1e9, order[sid])
            ids.sort(key=key)
            off = (tracks[seg_of[r]][li] - len(ids)) / 2.0
            for t, sid in enumerate(ids):
                pos_cross[sid] = off + t

    # 띠 두께와 시작 자리(덩어리마다)
    lanes_on = bool(spec.lanes)
    pad = lane_pad if lanes_on else 0.0
    hd = head if lanes_on else 0.0
    seg_gap = gap_major * 1.3
    lane_len, lane_at, seg_at = [], [], []
    acc = 0.0
    present = []   # 덩어리마다 단계가 있는 띠만(꺾으면 계단 모양 흐름에서 빈 띠가 줄줄이 남았다 — 실제 창)
    for sg in range(n_seg):
        rs = range(sg * per, min(n_ranks, (sg + 1) * per))
        here = [i for i in range(len(lane_names)) if any(cells.get((i, r)) for r in rs)] if n_seg > 1 else []
        present.append(here or list(range(len(lane_names))))
    for sg in range(n_seg):
        seg_at.append(acc)
        ll = {i: pad * 2 + tracks[sg][i] * cell + (tracks[sg][i] - 1) * gap_minor for i in present[sg]}
        la, a2 = {}, acc
        for i in present[sg]:
            la[i] = a2
            a2 += ll[i] + (lane_gap if lanes_on else 0.0)
        lane_len.append(ll)
        lane_at.append(la)
        acc = a2 - (lane_gap if lanes_on else 0.0) + seg_gap
    cross_total = acc - seg_gap
    col_at = [0.0] * n_ranks
    flow_total = 0.0
    for sg in range(n_seg):
        a2 = hd + pad
        for r in range(sg * per, min(n_ranks, (sg + 1) * per)):
            col_at[r] = a2
            a2 += col[r] + gap_major
        flow_total = max(flow_total, a2 - gap_major + pad)
    flip = spec.direction in ("RL", "BT")

    boxes: dict[str, tuple[float, float, float, float]] = {}
    for s in spec.steps:
        w, h = sizes[s.id]
        li = lane_ix[s.lane if s.lane in lane_ix else lane_names[0]]
        r = rank[s.id]
        sg = seg_of[r]
        f0 = col_at[r]
        flen = col[r]
        if flip:   # 흐름축 뒤집기(이름표 자리는 그대로 앞쪽)
            f0 = hd + (flow_total - hd) - (f0 - hd) - flen
        c0 = lane_at[sg][li] + pad + pos_cross[s.id] * (cell + gap_minor)
        if horizontal:
            x = f0 + (flen - w) / 2.0
            y = c0 + extra + (cell - extra - h) / 2.0
        else:
            x = c0 + (cell - w) / 2.0
            y = f0 + extra + (flen - extra - h) / 2.0
        boxes[s.id] = (x, y, w, h)

    lanes: list[LaneBox] = []
    if lanes_on:
        for sg in range(n_seg):
            for i in present[sg]:
                name = lane_names[i]
                at, ln = lane_at[sg][i], lane_len[sg][i]
                if horizontal:
                    rect = (0.0, at, flow_total, ln)
                    hrect = (0.0, at, hd, ln)
                else:
                    rect = (at, 0.0, ln, flow_total)
                    hrect = (at, 0.0, ln, hd)
                lanes.append(LaneBox(name, rect, hrect))
    width, height = (flow_total, cross_total) if horizontal else (cross_total, flow_total)
    return FlowLayout(boxes, lanes, rank, width, height, {sid: seg_of[r] for sid, r in rank.items()})


def best_wrap(spec: FlowSpec, size_of, *, target: float = 16.0 / 9.0, min_len: float = 1600.0, **kw):
    """꺾어 내릴 덩어리 크기(칸 수) — 안 꺾으면 None. 흐름 방향 길이가 `min_len`을 넘고 모양이 `target`(폭/높이)보다
    훨씬 길 때만, 덩어리 1~6개를 다 배치해 보고 모양이 `target`에 가장 가까운 것을 고른다(같으면 덜 꺾는 쪽)."""
    import math
    base = layout(spec, size_of, **kw)
    n = max(base.ranks.values(), default=0) + 1
    horizontal = spec.direction in ("LR", "RL")
    long_side = base.width if horizontal else base.height
    if n < 4 or long_side <= min_len:
        return None

    def score(lay):
        return abs(math.log(max(lay.width, 1.0) / max(lay.height, 1.0) / target))
    best, best_s = None, score(base)
    for segs in range(2, min(6, n // 2) + 1):
        per = (n + segs - 1) // segs
        sc = score(layout(spec, size_of, wrap=per, **kw))
        if sc < best_s - 0.05:
            best, best_s = per, sc
    return best


def _lane_of(spec: FlowSpec, sid: str) -> str:
    for s in spec.steps:
        if s.id == sid:
            return s.lane
    return ""
