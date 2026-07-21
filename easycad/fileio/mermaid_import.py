"""Mermaid flowchart import — 순서도 텍스트를 편집가능 도형+화살표로.

Phase 4 마지막 조각. 이 모듈은 **순수 Python(Qt 비의존)** 으로 파싱과 계층 배치만
담당한다 — 실제 도형 생성(Qt 아이템)과 지속연결 바인딩은 host._insert_mermaid가 이 결과를
받아서 한다. 그래야 스모크가 씬 없이도 파싱·배치를 검증할 수 있고, 규칙 2(손안의 카드)대로
외부 레이아웃 의존성 없이 자체 BFS 계층 배치로 초안을 만든다(엣지 라우팅은 _PolyArrowItem의
기존 직교 자동라우팅이 담당).

지원 범위(deep-interview 2026-07-21로 확정한 '핵심 부분집합'):
  - 헤더: `flowchart|graph` + 방향 TD/TB/LR/RL/BT (기본 TD)
  - 노드 모양 8종 → 중립 shape 문자열(host가 우리 도형에 매핑)
  - 엣지 4종(--> --- -.-> ==>) + 파이프 라벨 `-->|txt|` + 인라인 라벨 `-- txt -->`
  - 한 줄 체인(A --> B --> C)
스코프 밖(조용히 무시/폴백): subgraph·classDef/스타일·click·`&` 다중노드.
점선(-.->)·굵은선(==>)은 스타일 손실(실선 화살표로 흡수) — host에서 처리.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


class MermaidError(ValueError):
    """파싱 실패(빈 입력·노드 없음 등). host가 잡아 사용자에게 메시지로 보여준다."""


# ── 노드 모양 매핑용 중립 어휘 ──────────────────────────────────────────────
# (opener, closer, shape) — startswith/endswith 로 판정하므로 가장 구체적인(긴)
# 구분자부터 둔다. 여는 문자가 같아도 닫는 문자로 갈린다(예: [/../] vs [/..\]).
_SHAPE_DELIMS = [
    ("([", "])", "stadium"),        # 시작/끝
    ("[(", ")]", "cylinder"),       # 저장소
    ("[[", "]]", "rect"),           # subroutine → 사각형 폴백
    ("{{", "}}", "hexagon"),        # 준비
    ("((", "))", "circle"),         # 원
    ("[/", "/]", "parallelogram"),  # 입출력
    ("[\\", "\\]", "parallelogram"),
    ("[/", "\\]", "rect"),          # 사다리꼴 → 사각형 폴백
    ("[\\", "/]", "rect"),
    ("[", "]", "rect"),
    ("(", ")", "rounded"),          # 둥근 사각형 → host에서 사각형(라운딩 손실)
    ("{", "}", "rhombus"),          # 판단
]

_ID_RE = re.compile(r"[A-Za-z0-9_]+")
_HEADER_RE = re.compile(r"^\s*(?:flowchart|graph)\s+(TD|TB|LR|RL|BT)\b", re.IGNORECASE)

# 연결자: 점선/굵은/보통 × (화살표/선), 뒤에 선택적 파이프 라벨. 긴 것부터 매칭.
_CONN_RE = re.compile(
    r"\s*(?P<op>-\.->|-\.-|==+>|==+|--+>|--+)\s*(?:\|(?P<label>[^|]*)\|\s*)?"
)
# 인라인 라벨(`-- yes -->`) → 파이프 형태(`-->|yes|`)로 정규화하는 전처리.
# 오른쪽 연산자가 화살촉(>)으로 끝나는 경우만 잡아 `A --- B --- C` 같은 체인을 오염시키지 않는다.
_INLINE_RE = re.compile(r"(--+|==+|-\.-)\s+([^|>][^>|]*?)\s+(--+>|==+>|-\.->)")

_OPEN, _CLOSE = set("[({"), set("])}")


@dataclass
class MNode:
    id: str
    shape: str = "rect"
    label: str = ""


@dataclass
class MEdge:
    src: str
    dst: str
    label: str = ""
    style: str = "solid"   # solid | dotted | thick
    arrow: bool = True      # 화살촉 유무(--- 는 False)


@dataclass
class MGraph:
    direction: str = "TD"
    nodes: dict[str, MNode] = field(default_factory=dict)
    edges: list[MEdge] = field(default_factory=list)


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _parse_node_token(token: str) -> MNode | None:
    """`A[Start]` · `B{{Prep}}` · `C` → MNode. 빈 토큰이면 None.
    모양 구분자가 없으면 bare 참조(shape/label 미정 → 사각형·id 라벨)."""
    token = token.strip()
    if not token:
        return None
    m = _ID_RE.match(token)
    if not m:
        return None
    nid = m.group(0)
    rest = token[m.end():].strip()
    if not rest:
        return MNode(nid, "rect", "")   # bare 참조 — 라벨은 나중에 host가 id로 채움
    for opn, cls, shape in _SHAPE_DELIMS:
        if rest.startswith(opn) and rest.endswith(cls) and len(rest) >= len(opn) + len(cls):
            label = _strip_quotes(rest[len(opn): len(rest) - len(cls)])
            return MNode(nid, shape, label)
    # 미인식 구분자 → 사각형 폴백(라벨은 rest 통째로 정리해 사용)
    return MNode(nid, "rect", _strip_quotes(rest.strip("[](){}")))


def _classify_conn(m: re.Match) -> tuple[str, bool, str]:
    op = m.group("op")
    style = "dotted" if "." in op else ("thick" if "=" in op else "solid")
    arrow = op.endswith(">")
    label = (m.group("label") or "").strip()
    return style, arrow, label


def _tokenize_line(line: str) -> list:
    """한 줄을 [('node', str), ('conn', (style, arrow, label)), ('node', str), ...] 로.
    대괄호/괄호 깊이를 세어 라벨 안의 `-->` 같은 텍스트는 연결자로 오인하지 않는다."""
    tokens: list = []
    buf = ""
    depth = 0
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in _OPEN:
            depth += 1
            buf += ch
            i += 1
            continue
        if ch in _CLOSE:
            depth = max(0, depth - 1)
            buf += ch
            i += 1
            continue
        if depth == 0:
            cm = _CONN_RE.match(line, i)
            if cm and cm.group("op"):
                tokens.append(("node", buf.strip()))
                buf = ""
                tokens.append(("conn", _classify_conn(cm)))
                i = cm.end()
                continue
        buf += ch
        i += 1
    tokens.append(("node", buf.strip()))
    return tokens


def _register(graph: MGraph, node: MNode) -> str:
    """노드를 그래프에 등록(또는 기존 정의 보강)하고 id 반환. 모양·라벨이 있는 정의가
    bare 참조를 덮어쓴다(첫 실질 정의 우선)."""
    exist = graph.nodes.get(node.id)
    if exist is None:
        graph.nodes[node.id] = node
    else:
        # bare 참조 뒤에 실질 정의가 오면 채운다(모양/라벨).
        if node.label and not exist.label:
            exist.label = node.label
        if node.shape != "rect" and exist.shape == "rect":
            exist.shape = node.shape
    return node.id


def parse_mermaid(text: str) -> MGraph:
    """Mermaid flowchart 텍스트 → MGraph. 실패 시 MermaidError."""
    if not text or not text.strip():
        raise MermaidError("빈 입력입니다. Mermaid flowchart 코드를 붙여넣어 주세요.")

    graph = MGraph()
    header_seen = False
    for raw in text.splitlines():
        line = raw.split("%%", 1)[0].strip()   # %% 주석 제거
        if not line:
            continue
        if not header_seen:
            hm = _HEADER_RE.match(line)
            if hm:
                graph.direction = hm.group(1).upper()
                header_seen = True
                rest = line[hm.end():].strip()
                if not rest:
                    continue
                line = rest   # 헤더 뒤에 문장이 붙은 경우 계속 처리
        # subgraph/end/스타일/클릭 등 스코프 밖 구문은 조용히 건너뛴다.
        low = line.lower()
        if low.startswith(("subgraph", "end", "classdef", "class ", "style ",
                           "click ", "linkstyle", "direction ")):
            continue

        line = _INLINE_RE.sub(r"\3|\2|", line)   # 인라인 라벨 → 파이프 형태
        tokens = _tokenize_line(line)

        # 노드/연결자 교차 시퀀스에서 엣지를 뽑는다.
        prev_id = None
        pending_conn = None
        for kind, val in tokens:
            if kind == "node":
                node = _parse_node_token(val)
                if node is None:
                    prev_id = None if pending_conn is None else prev_id
                    continue
                cur_id = _register(graph, node)
                if pending_conn is not None and prev_id is not None:
                    style, arrow, elabel = pending_conn
                    graph.edges.append(MEdge(prev_id, cur_id, elabel, style, arrow))
                prev_id = cur_id
                pending_conn = None
            else:  # conn
                pending_conn = val

    # bare 참조 노드의 라벨을 id로 채운다(정의된 라벨이 없을 때만).
    for node in graph.nodes.values():
        if not node.label:
            node.label = node.id

    if not graph.nodes:
        raise MermaidError(
            "노드를 찾지 못했습니다. 예: `flowchart TD` 다음 줄에 `A[시작] --> B{판단}`.")
    return graph


# ── 자체 계층 레이아웃(BFS 최장경로 레벨) ───────────────────────────────────
DEFAULT_NODE_W = 120.0
DEFAULT_NODE_H = 56.0
DEFAULT_GAP_MAJOR = 64.0   # 레벨 사이(흐름 축) 간격
DEFAULT_GAP_MINOR = 40.0   # 같은 레벨 안 간격


def _levels(graph: MGraph) -> dict[str, int]:
    """각 노드의 레벨(=루트로부터의 BFS 거리). BFS라 재시도 루프(`D-->B`) 같은 사이클의
    역방향 간선은 방문표시로 자연히 무시된다 — 최장경로 완화는 사이클에서 레벨이 발산하므로 쓰지 않는다."""
    from collections import deque
    ids = list(graph.nodes.keys())
    indeg = {i: 0 for i in ids}
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for e in graph.edges:
        if e.src in adj and e.dst in indeg and e.src != e.dst:
            adj[e.src].append(e.dst)
            indeg[e.dst] += 1
    # 루트 = 들어오는 간선 없는 노드. 전부 사이클이라 루트가 없으면 첫 노드를 루트로.
    roots = [i for i in ids if indeg[i] == 0] or (ids[:1])
    level = {i: 0 for i in ids}
    seen = set(roots)
    q = deque((r, 0) for r in roots)
    while q:
        nid, lv = q.popleft()
        level[nid] = lv
        for nb in adj[nid]:
            if nb not in seen:
                seen.add(nb)
                q.append((nb, lv + 1))
    # 루트에서 못 닿은 노드(분리된 사이클 등)는 레벨 0으로 둔다.
    return level


def layout_positions(graph: MGraph,
                     node_w: float = DEFAULT_NODE_W,
                     node_h: float = DEFAULT_NODE_H,
                     gap_major: float = DEFAULT_GAP_MAJOR,
                     gap_minor: float = DEFAULT_GAP_MINOR) -> dict[str, tuple[float, float]]:
    """노드 id → (좌상단 x, y). 방향에 따라 레벨을 행(TD/TB) 또는 열(LR/RL)로 펼치고,
    같은 레벨은 첫 등장 순서로 나란히 배치(중앙 정렬). BT/RL은 축을 뒤집는다."""
    level = _levels(graph)
    order = list(graph.nodes.keys())        # 첫 등장 순서(dict 삽입 순) = 레벨 내 정렬
    by_level: dict[int, list[str]] = {}
    for nid in order:
        by_level.setdefault(level[nid], []).append(nid)
    max_level = max(level.values()) if level else 0
    max_count = max((len(v) for v in by_level.values()), default=1)

    horizontal = graph.direction in ("LR", "RL")
    major = node_w + gap_major if horizontal else node_h + gap_major   # 흐름축 스텝
    minor = node_h + gap_minor if horizontal else node_w + gap_minor   # 교차축 스텝

    pos: dict[str, tuple[float, float]] = {}
    for lv, members in by_level.items():
        count = len(members)
        # 교차축에서 중앙 정렬: 전체 폭(max_count) 대비 이 레벨을 가운데로.
        offset = (max_count - count) / 2.0
        # 흐름축 좌표(레벨). BT/RL은 뒤집는다.
        flv = (max_level - lv) if graph.direction in ("BT", "RL") else lv
        for k, nid in enumerate(members):
            cross = (offset + k) * minor
            flow = flv * major
            if horizontal:
                x, y = flow, cross
            else:
                x, y = cross, flow
            pos[nid] = (x, y)
    return pos
