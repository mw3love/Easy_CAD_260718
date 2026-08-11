"""이미지→도면 파이프라인 — §8 항목18 B단계.

이미지 한 장(+보충설명 텍스트)을 받아 `.ecad`를 만든다. 설계·실측 근거 전문은
`docs/ai_image_import.md`, 함정은 `docs/pitfalls.md`의 "AI 게이트웨이 호출(이미지→도면)"
절. `easycad/ai/gateway.py`의 vision 호출 위에 P1~P3를 얹는다(P4 에셋 패스는 스코프 밖).

**PyQt 비의존** — `gateway.py`와 같은 이유로, C단계(앱 통합, `easycad/canvas/host_ai.py`)와
헤드리스 CLI(`tools/ai_sketch.py`) 양쪽이 이 모듈을 그대로 가져다 쓴다(2026-08-11: 원래
`tools/ai_sketch.py`에 있던 로직을 앱이 재사용해야 해서 이곳으로 이동 — `tools/`는 독립
스크립트 전용이라 앱 코드가 거기 의존하면 방향이 꼬인다).

파이프라인:
  P1 개괄  전체 이미지 1회(기본 gemini) → 대략 shapes/edges/unknown.
           항목 수가 `tile_threshold` 이하면 여기서 끝(밀집도 낮은 도면).
  P2 타일  P1 shapes 밀도로 격자 타일을 만들어(`compute_tiles`) 구획별 크롭 ×N을
           확대(zoom)해 재전송(기본 gpt-5.4-mini — 2026-08-11 동일 크롭 4모델 실측
           비교로 확정, 아래 "모델 선택" 참조). 좌표는 크롭 좌표계로 나오므로
           `restore_item_coords`로 원본 좌표계 복원.
  P3 병합  타일 간 겹침으로 중복된 shape를 IoU로 합치고(`dedupe_shapes`) 그 과정에서
           edges의 참조도 같이 재매핑 — 이게 "타일 경계를 넘는 연결 잇기"의 실제 구현이다
           (겹치는 오버랩 구간에 걸친 도형이 최소 한 타일엔 온전히 잡힌다는 전제, 문서화된
           한계: 두 타일 모두에 걸치지 않는 아주 긴 연결선은 못 잇는다). 라벨 공백을
           정리한다(`clean_label`).

unknown 항목은 P4(에셋 패스, 스코프 밖)가 아직 없으므로 전부 "[미확인] 설명" 라벨의
플레이스홀더 박스로 남는다(설계 문서의 "실패하면 통짜 상자로 남기고 목록에 표시" 폴백을
지금 단계 전체에 적용한 것).

**P3.5 연결선 보완(2026-08-11, 실사용 피드백으로 신설)** — 타일링 자체의 구조적 한계로
"두 도형이 서로 다른 타일에서 각각 인식돼 그 사이 실제 연결선이 통째로 누락"되는 문제가
실측으로 확인됐다(KBS 실도면에서 실제 도형 27개 중 11개가 화살표를 하나도 못 얻음, 특히
도면 중앙의 핵심 블록 "PIC-FM"). 타일 오버랩 패딩만으로는 도면 전체를 가로지르는 긴
연결선을 못 잡는다(설계 문서에 이미 문서화된 한계) — 타일이 클수록 세부 인식이 나빠지고
(다른 함정, `docs/pitfalls.md` 참조), 작을수록 긴 선을 놓친다는 트레이드오프라 타일 크기
조정만으론 근본 해결이 안 된다.

그래서 P3(병합) 직후 **전체 원본 이미지 + 이미 병합된 shapes 목록(id·라벨·좌표)**을 다시
모델에 보내 "이 도형들 사이에 실제로 그려진 선만 찾아라"고 묻는 새 패스를 추가했다
(`complete_edges`). 스키마를 `edges`만 있는 좁은 형태로 만들어(`EDGE_SCHEMA`,
`additionalProperties: False`) 모델이 새 도형을 만들 구조적 여지 자체를 없앴고, 프롬프트에
"실제로 그려진 선만"(2026-07-21부터 이어진 환각방지 원칙)을 그대로 유지, 반환된 edges는
`from`/`to`가 실제 존재하는 shape id일 때만 채택한다(방어적 검증). 타일링이 트리거된
경우에만 실행(단일 P1 패스는 이미 전체 이미지를 봐서 이 문제 자체가 없음).

**모델 선택(2026-08-11, 실사용 비용 피드백 후 재측정)** — 애초 `claude-sonnet-5`를
P2 기본으로 뒀던 건 인식 세부도만 보고 정한 결정이라 비용을 안 봤다. 실사용 중
크레딧 소모가 과하다는 지적을 받고 같은 크롭(360×160) 1장으로 4모델을 직접 비교:

| 모델 | 크레딧 | 소요 | shapes | edges |
|---|---|---|---|---|
| gemini-3.6-flash | 9.53 | 11.8s | 9 | 10 |
| claude-sonnet-5 | 56.92 | 32.3s | 13 | 12 |
| claude-haiku-4-5 | 5.97 | 14.1s | 15 | 9 |
| **gpt-5.4-mini** | **3.08** | **4.9s** | **13** | **12** |

`gpt-5.4-mini`가 `claude-sonnet-5`와 shapes·edges가 완전히 같으면서 비용은 1/18,
속도는 1/6이라 P2 기본을 이걸로 교체했다. `claude-haiku-4-5`도 유력한 대안(shapes
최다)이라 드롭다운엔 그대로 남아 있다 — 사용자가 직접 골라 쓸 수 있다.
⚠ 표본 1개짜리 비교라 밀집 도면·다른 도면 스타일에서 순위가 바뀔 수 있다.

**P3.75 관계 기반 배치(2026-08-11, 좌표 신뢰 배치를 완전히 대체)** — P4(에셋 패스)와
이름이 겹치지 않도록 P3(병합)·P3.5(연결선 보완) 다음 자리로 번호를 매겼다. 중복박스·연결선 보완
(P3.5)까지 고쳐도 실사용 결과가 여전히 "지저분해서 못 쓴다"는 재보고를 받고 재진단한
결과, 근본 원인은 두 수정과 별개로 "vision 모델의 절대 픽셀 좌표 추정 자체가 부정확
하다"는 것이었다(실측: 같은 실물을 두 번 인식해도 좌표가 몇~수십 px씩 어긋남) — 그
부정확한 좌표를 그대로 믿고 배치하면 도형이 겹치고, 겹친 더미 사이로 자동 배선(A*)이
못 지나가 성능까지 파국적으로 나빠진다(실측: 20개 그룹 드래그 916ms — 도형 수는 1600개
짜리 문서보다 훨씬 적은데도 60fps 예산의 55배, 원인은 순전히 밀집·중첩된 장애물 사이
경로를 못 찾아 재시도 캐스케이드가 반복 발동했기 때문). 두 증상(지저분함·버벅임)이 같은
뿌리였던 것.

그래서 좌표를 정밀 배치 근거로 쓰는 걸 완전히 그만두고(사용자 확정, 2026-08-11 — 좌표
기반 경로를 옵션으로 남기지 않고 전면 교체), P1~P3.5가 여전히 그대로 뽑아주는 관계
정보(shapes+edges)만으로 `layout_graph()`가 새로 배치한다 — Mermaid 가져오기가 이미
검증해 쓰는 `layout_positions()`(그래프 BFS 레벨 기반, 같은 레벨은 자동으로 안 겹치게
나란히)를 그대로 재사용한다(규칙 2 손안의 카드: 새 레이아웃 알고리즘을 새로 만들지
않음). 원본의 대략적인 흐름 방향(좌→우 vs 위→아래)은 "약하게"만 남긴다(사용자 확정) —
rough 좌표의 bbox 가로세로 비율로 전체 방향을 추정하고, 같은 레벨 안에서의 순서도 rough
좌표로 정렬해 원본과 비슷한 느낌은 유지하되 정밀 위치는 신뢰하지 않는다. 좌표 스냅
(`axis_snap`, 이제 폐기)이 하던 일도 이 새 배치가 원리적으로 대체한다 — 격자 배치라
애초에 스냅할 미세 오차가 안 생긴다."""
import math
import re

from easycad.ai import gateway as gw

# `sketch_build.Sketch` 빌더 API를 미러링(`docs/ai_image_import.md` "중간 JSON 스키마").
# 필드를 늘리기 전에 빌더가 그걸 지원하는지 먼저 확인할 것 — 스키마가 빌더보다 앞서면
# `build_sketch`에서 조용히 버려진다.
SKETCH_SCHEMA = {
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

# P3.5 연결선 보완 전용 스키마 — edges만 있다(additionalProperties: False로 새 shapes/
# unknown을 만들 구조적 여지 자체를 없앤다, "P3.5 연결선 보완" 절 참조).
EDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["edges"],
    "properties": {
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
    },
}

# ⚠ "실제로 그려진 연결선만"은 반드시 유지 — 2026-07-21 실조건 함정(`image_to_ecad.md`):
# 모델이 "이 흐름이면 여기로 돌아가야 논리적"이라며 원본에 없는 화살표를 만들어낸다.
_BASE_RULES = """규칙:
- shapes: 사각형/타원/순서도 기호(decision=마름모 판단·terminal=타원형 시작/끝) 블록
  하나당 항목 하나. label은 도형 안 텍스트 그대로(한글 포함).
- edges: **실제로 그려진 연결선만**. 논리적으로 있어야 할 것 같다고 없는 선을 추가하지 말 것.
- unknown: 사각형·타원·순서도 기호로 표현 못 하는 도형(안테나 픽토그램 등)만.
- 점선 그룹 테두리(구획 박스)는 shapes에 포함하지 말 것.
"""


def _overview_prompt(w: int, h: int, note: str = "") -> str:
    extra = f"\n참고: {note}\n" if note else ""
    return (f"이 이미지는 도면(계통도/블록 다이어그램)이다. 편집 가능한 CAD 도형으로 복원하려 한다.\n"
            f"좌표는 이 이미지의 픽셀 좌표 그대로. 원점은 좌상단. 이미지 크기: {w}x{h}\n{extra}\n{_BASE_RULES}")


def _tile_prompt(w: int, h: int, note: str = "") -> str:
    extra = f"\n참고: {note}\n" if note else ""
    return (f"이 이미지는 어떤 도면의 한 구획을 확대한 크롭이다. 편집 가능한 CAD 도형으로 복원하려 한다.\n"
            f"좌표는 **이 크롭 이미지 자체의 픽셀 좌표**(원본 전체 이미지 좌표 아님). "
            f"원점은 좌상단. 이 크롭 이미지 크기: {w}x{h}\n{extra}\n{_BASE_RULES}")


def _edge_completion_prompt(shapes: list[dict], w: int, h: int, note: str = "") -> str:
    """P3.5 연결선 보완 프롬프트 — 이미 인식된 도형 목록을 id·라벨·좌표로 나열해 모델이
    "이 도형들 사이 실제 선"만 찾도록 좁힌다. 새 도형을 만들 여지는 스키마(`EDGE_SCHEMA`,
    edges만 존재)로 구조적으로 차단하고, 프롬프트로도 명시(이중 안전장치)."""
    extra = f"\n참고: {note}\n" if note else ""
    listing = "\n".join(
        f"- id={s['id']}: {s.get('label', '') or '(라벨없음)'} (대략 위치 x={s['x']:.0f}, y={s['y']:.0f})"
        for s in shapes)
    return (f"이 이미지는 도면(계통도/블록 다이어그램)이다. 이미지 크기: {w}x{h}\n{extra}\n"
            f"아래는 이미 인식된 도형 목록이다(id·라벨·대략 위치로 이미지 안에서 실제 위치를 찾아라):\n"
            f"{listing}\n\n"
            f"규칙:\n"
            f"- 위 도형들 **사이에 실제로 그려진 연결선(선/화살표)만** 찾아 edges로 출력하라.\n"
            f"- 논리적으로 있어야 할 것 같다고 없는 선을 추가하지 말 것.\n"
            f"- from/to는 반드시 위 목록의 id를 그대로 사용하라(새 id·새 도형을 만들지 말 것).\n"
            f"- 위 목록에 없는 도형·요소는 무시하라 — 오직 나열된 도형 사이의 연결선만 찾는다.")


# ── 수동 붙여넣기 모드(2026-08-11, §8 항목18 C단계 후속) ─────────────────────
# 게이트웨이 API 대신 사용자가 원하는 AI 챗(Claude Code·claude.ai·chatgpt.com 등,
# 별도 정액제/구독 — 이 프로젝트가 쓰는 kairos 계정 크레딧과 무관)에 이미지+프롬프트를
# 직접 붙여넣고 받은 JSON 응답을 그대로 붙여넣는 경로. `json_schema` 구조화 출력은
# API 전용 기능이라 이 경로엔 없으므로, 프롬프트 텍스트 자체에 정확한 JSON 형식을
# 예시까지 박아 둔다 — 그래야 임의의 챗 UI에서도 같은 스키마로 답이 온다. P1(전체
# 1패스) 결과로만 취급하고 P2(타일)·P3(병합)는 거치지 않는다 — 붙여넣기 자체가 반복
# 수작업이라 자동 타일링까지 손으로 반복하긴 비현실적이라는 사용자 확인(2026-08-11).
_MANUAL_JSON_FORMAT = """
**출력 형식**: 다른 설명 없이 아래와 똑같은 구조의 JSON 하나만 출력하라(```json 코드블록으로
감싸도 되고 안 감싸도 됨):

{
 "shapes": [{"id": "s1", "kind": "box", "x": 120, "y": 80, "w": 200, "h": 90, "label": "1TV 송신기"}],
 "edges":  [{"from": "s1", "to": "s2", "label": ""}],
 "unknown": [{"x": 400, "y": 300, "w": 60, "h": 60, "desc": "원형 스위치"}]
}

- kind는 "box"·"ellipse"·"decision"(마름모 판단)·"terminal"(타원 시작/끝) 중 하나만.
- id는 shapes 배열 안에서만 서로 다르면 된다(문자열, 형식 자유).
- edges의 from/to는 반드시 shapes의 id를 그대로 참조.
- 이미지에 shapes/edges/unknown이 없으면 그 배열은 빈 배열([])로.
"""


def manual_prompt(w: int, h: int, note: str = "") -> str:
    """수동 모드용 프롬프트 — `_overview_prompt`와 같은 지시문에 JSON 출력 형식을
    명시적으로 덧붙인다(API 모드는 `response_format=json_schema`로 형식을 강제하지만,
    수동 모드는 임의의 채팅 UI를 거치므로 프롬프트 텍스트가 유일한 강제 수단)."""
    return _overview_prompt(w, h, note) + _MANUAL_JSON_FORMAT


# ── P2: 타일 격자 계산 ───────────────────────────────────────────────────────

def compute_tiles(items: list[dict], img_w: int, img_h: int, *,
                   max_shapes_per_tile: int = 8, overlap_frac: float = 0.15) -> list[tuple[float, float, float, float]]:
    """P1 결과(shapes+unknown)의 밀도로 격자 타일 목록을 만든다. 반환은 원본 이미지
    좌표계의 (left, top, w, h) 튜플 목록, 오버랩 패딩 포함(경계에 걸친 도형이 최소
    한 타일엔 온전히 들어오게 하기 위함 — P3 dedupe로 접합).

    빈 칸(그 격자 셀에 P1 항목이 하나도 없는 곳)은 목록에서 제외해 불필요한 호출을 줄인다.
    """
    if not items or img_w <= 0 or img_h <= 0:
        return []
    n = len(items)
    total_tiles = max(1, math.ceil(n / max_shapes_per_tile))
    aspect = img_w / img_h if img_h else 1.0
    cols = max(1, round(math.sqrt(total_tiles * aspect)))
    rows = max(1, math.ceil(total_tiles / cols))
    cell_w = img_w / cols
    cell_h = img_h / rows

    occupied: set[tuple[int, int]] = set()
    for it in items:
        cx = it["x"] + it["w"] / 2.0
        cy = it["y"] + it["h"] / 2.0
        ci = min(cols - 1, max(0, int(cx // cell_w)))
        ri = min(rows - 1, max(0, int(cy // cell_h)))
        occupied.add((ci, ri))

    pad_x, pad_y = cell_w * overlap_frac, cell_h * overlap_frac
    tiles = []
    for ci, ri in sorted(occupied):
        left = max(0.0, ci * cell_w - pad_x)
        top = max(0.0, ri * cell_h - pad_y)
        right = min(float(img_w), (ci + 1) * cell_w + pad_x)
        bottom = min(float(img_h), (ri + 1) * cell_h + pad_y)
        tiles.append((left, top, right - left, bottom - top))
    return tiles


def crop_and_zoom(img, box: tuple[float, float, float, float], *, zoom: int = 3, max_dim: int = 2000):
    """`box`(원본 좌표계 left,top,w,h)를 잘라 `zoom`배 확대. 결과 이미지가 `max_dim`을
    넘으면 확대율을 낮춘다(과대 payload 방지). 반환 (crop_img, 실제zoom, 실제left(int),
    실제top(int)) — 실제left/top은 PIL 크롭에 쓴 반올림 정수값으로, 좌표 복원의 진짜
    기준점이다(부동소수 box를 그대로 쓰면 반올림 오차가 누적된다)."""
    from PIL import Image

    left, top, w, h = box
    l, t = int(round(left)), int(round(top))
    r, b = int(round(left + w)), int(round(top + h))
    crop = img.crop((l, t, r, b))
    z = zoom
    while max(crop.width * z, crop.height * z) > max_dim and z > 1:
        z -= 1
    if z != 1:
        crop = crop.resize((max(1, crop.width * z), max(1, crop.height * z)), Image.LANCZOS)
    return crop, z, l, t


def restore_item_coords(item: dict, crop_left: float, crop_top: float, zoom: int) -> dict:
    """P2 타일 좌표(크롭 이미지 자체 픽셀, zoom배 확대된 좌표계) → 원본 전체 이미지
    좌표계로 복원. 순서가 중요: **먼저 zoom으로 나누고, 그다음 크롭 오프셋을 더한다**
    (확대된 크롭 안에서의 위치를 원래 크기로 되돌린 뒤에야 원본 좌표계의 오프셋을 더하는
    게 맞다 — 반대 순서로 하면 오프셋 자체가 zoom배 되어 크게 어긋난다)."""
    out = dict(item)
    out["x"] = item["x"] / zoom + crop_left
    out["y"] = item["y"] / zoom + crop_top
    out["w"] = item["w"] / zoom
    out["h"] = item["h"] / zoom
    return out


def namespace_tile_result(tile_idx: int, data: dict) -> dict:
    """타일별로 독립 발급된 id가 다른 타일과 충돌하지 않도록 `t{tile_idx}_` 접두어를 붙인다.
    edges는 from/to가 **같은 타일 안에서 만든 id를 참조할 때만** 유지한다 — 모델은 자기가
    본 크롭 안의 도형만 알 수 있으므로 다른 타일 id를 참조하는 edge는 애초에 나올 수 없지만,
    방어적으로 매핑 실패 시 그 edge는 버린다."""
    prefix = f"t{tile_idx}_"
    id_map = {}
    shapes = []
    for s in data.get("shapes", []):
        new_id = prefix + s["id"]
        id_map[s["id"]] = new_id
        s2 = dict(s)
        s2["id"] = new_id
        shapes.append(s2)
    edges = []
    for e in data.get("edges", []):
        f, t = e.get("from"), e.get("to")
        if f in id_map and t in id_map:
            e2 = dict(e)
            e2["from"], e2["to"] = id_map[f], id_map[t]
            edges.append(e2)
    unknown = [dict(u) for u in data.get("unknown", [])]
    return {"shapes": shapes, "edges": edges, "unknown": unknown}


# ── P3: 병합·정규화 ──────────────────────────────────────────────────────────

def _iou(a: dict, b: dict) -> float:
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _label_key(s: dict) -> str:
    """라벨 비교용 정규화 키 — 공백을 전부 제거하고 소문자화. 같은 실물을 서로 다른
    타일에서 두 번 읽었을 때 OCR이 쉼표 뒤 공백 유무처럼 사소하게 다르게 뽑는 경우
    (실측: '6950,6990MHz' vs '6950, 6990MHz')를 같은 라벨로 취급하기 위함."""
    return re.sub(r"\s+", "", s.get("label", "") or "").lower()


def dedupe_shapes(shapes: list[dict], edges: list[dict], *,
                   iou_thresh: float = 0.4, label_iou_floor: float = 0.05) -> tuple[list[dict], list[dict]]:
    """겹치는 타일에서 같은 도형이 중복 인식된 것을 합친다(같은 kind가 전제).
    두 가지 병합 신호를 OR로 판정한다:
      ⓐ 순수 겹침(IoU) ≥ `iou_thresh` — 라벨이 달라도 기하가 거의 같으면 병합.
      ⓑ 라벨이 사실상 같은 텍스트(`_label_key` 일치) AND IoU ≥ `label_iou_floor` — 같은
         실물을 서로 다른 타일이 서로 다른 정밀도로 감지해 겹침이 낮게 나온 경우(실측:
         'STL-TX MT PLATINUM 1.701.75GHz' 두 번 감지, IoU 0.12)를 라벨 신호로 보강.
    ⓑ만으로는 위험하다 — "PIC-FM"이 그 안의 "Audio(A)"를 감싸는 것처럼 **라벨이 다른
    진짜 별개 구성요소**가 겹칠 수 있어(실측 IoU 0.11~0.35), 라벨이 같을 때만 낮은
    바닥값을 적용한다. 같은 실측 도면에서 라벨이 같은 서로 다른 실물(예: TX-A/TX-B
    양쪽의 "SYT-5K")은 공간적으로 떨어져 있어 IoU가 0에 가까우므로 `label_iou_floor`
    (기본 0.05)에 못 미쳐 안전하게 병합되지 않는다.

    먼저 나온 쪽을 canonical로 남기고, edges의 from/to를 canonical id로 재매핑 — 이게
    "타일 경계를 넘는 연결 잇기"의 실제 구현이다: 경계에 걸친 도형이 오버랩 패딩 덕에
    최소 한 타일엔 온전히 잡히고, 그 도형을 참조하는 edge는 원래 자기 타일 id로 남아
    있다가 여기서 같은 도형의 canonical id로 합쳐진다."""
    kept: list[dict] = []
    id_remap: dict[str, str] = {}
    for s in shapes:
        s_label = _label_key(s)
        match = None
        for k in kept:
            if s.get("kind") != k.get("kind"):
                continue
            v = _iou(s, k)
            same_label = s_label and s_label == _label_key(k)
            if v >= iou_thresh or (same_label and v >= label_iou_floor):
                match = k
                break
        if match is not None:
            id_remap[s["id"]] = match["id"]
        else:
            kept.append(s)
            id_remap[s["id"]] = s["id"]

    new_edges = []
    seen = set()
    for e in edges:
        f = id_remap.get(e["from"], e["from"])
        t = id_remap.get(e["to"], e["to"])
        if f == t:
            continue  # 병합으로 자기순환이 된 edge는 제거
        key = (f, t, e.get("label", ""))
        if key in seen:
            continue
        seen.add(key)
        e2 = dict(e)
        e2["from"], e2["to"] = f, t
        new_edges.append(e2)
    return kept, new_edges



def clean_label(label: str) -> str:
    """라벨 정리 — 연속 공백/줄바꿈을 한 칸으로, 앞뒤 공백 제거."""
    return re.sub(r"\s+", " ", (label or "")).strip()


# ── 관계 기반 배치(2026-08-11, 실사용 피드백으로 좌표 신뢰 배치를 완전히 대체) ─────
#
# 배경: vision 모델의 절대 픽셀 좌표 추정은 본질적으로 부정확하다(실측: 같은 실물을
# 두 번 인식해도 좌표가 몇~수십 px씩 어긋남). 그 부정확한 좌표를 그대로 믿고 배치하면
# 도형이 겹치고(중복 제거로도 근본 해결 안 됨), 그 겹친 도형 더미 사이로 자동 배선
# (A*)이 못 지나가 성능까지 파국적으로 나빠진다(실측: 20개 그룹 드래그가 916ms —
# 겹친 장애물 사이 경로를 못 찾아 8~10회 재시도 캐스케이드가 반복 발동).
#
# 해법: 좌표를 "정밀 배치 근거"로 쓰는 걸 완전히 그만두고, "무엇이 무엇과 연결되는가"
# (shapes+edges, P1~P3.5가 여전히 그대로 뽑아주는 값)만 가지고 Mermaid 가져오기가 이미
# 검증해 쓰는 `layout_positions()`(그래프 BFS 레벨 기반, 같은 레벨은 겹치지 않게 나란히)
# 로 새로 배치한다(규칙 2 손안의 카드 — 새 레이아웃 알고리즘을 새로 안 만들고 기존
# 검증된 걸 그대로 재사용). 좌표는 완전히 안 버리는 게 아니라 "약하게" 남는다(사용자
# 확정, 2026-08-11) — 전체 흐름 방향(왼→오 vs 위→아래)을 rough 좌표의 가로세로 퍼짐으로
# 추정하고, 같은 레벨 안에서의 순서도 rough 좌표로 정렬해 원본과 비슷한 느낌을 남긴다.
def _infer_direction(shapes: list[dict]) -> str:
    """rough 좌표(dedup 후, 아직 안 버린 상태)의 bbox 가로세로 비율로 전체 흐름 방향을
    약하게 추정한다 — 가로로 넓게 퍼져 있으면 좌→우(LR), 세로로 넓으면 위→아래(TD)."""
    if not shapes:
        return "TD"
    xs = [s["x"] for s in shapes]
    ys = [s["y"] for s in shapes]
    w = max(xs) - min(xs) if xs else 0.0
    h = max(ys) - min(ys) if ys else 0.0
    return "LR" if w >= h else "TD"


def _layout_order_key(direction: str):
    """같은 레벨 안 순서를 rough 좌표로 결정 — LR/RL이면 x 우선(가로 흐름), 아니면 y 우선."""
    if direction in ("LR", "RL"):
        return lambda s: (s["x"], s["y"])
    return lambda s: (s["y"], s["x"])


def layout_graph(shapes: list[dict], edges: list[dict], unknown: list[dict] | None = None, *,
                  direction: str | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """좌표를 버리고 관계(shapes+edges)만으로 겹침 없는 새 배치를 계산한다.
    `unknown` 항목도 (관계가 없으니) 고립 노드로 같은 그래프에 포함해 함께 배치한다
    (`_levels`가 진입 간선 없는 노드를 자동으로 루트 레벨에 놓아 처리해 준다).

    셀 크기(`node_w`/`node_h`)는 모든 도형 중 가장 큰 크기 + 여백으로 잡아, 어떤 도형도
    자기 셀을 벗어나지 않게 한다(그래서 겹침이 원리적으로 불가능) — 각 도형은 자기 셀
    중앙에 원래 감지된 크기 그대로 배치한다(크기 자체는 신뢰 — 부정확한 건 절대 위치뿐).

    edges는 두 끝이 실제 존재하는 id를 참조할 때만 채택(`complete_edges`와 같은 방어적
    검증 관례)."""
    unknown = unknown or []
    _UNK_PREFIX = "__ai_unknown_"
    unk_nodes = [{"id": f"{_UNK_PREFIX}{i}", "label": u.get("desc", ""),
                 "x": float(u.get("x", 0.0)), "y": float(u.get("y", 0.0)),
                 "w": max(1.0, float(u.get("w", 40.0))), "h": max(1.0, float(u.get("h", 40.0)))}
                for i, u in enumerate(unknown)]
    all_nodes = list(shapes) + unk_nodes
    if not all_nodes:
        return shapes, edges, unknown

    from easycad.fileio.mermaid_import import MGraph, MNode, MEdge, layout_positions

    direction = direction or _infer_direction(all_nodes)
    ordered = sorted(all_nodes, key=_layout_order_key(direction))
    graph = MGraph(direction=direction)
    for s in ordered:
        graph.nodes[s["id"]] = MNode(s["id"], "rect", s.get("label", ""))
    valid_edges = []
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f in graph.nodes and t in graph.nodes and f != t:
            graph.edges.append(MEdge(f, t, e.get("label", "")))
            valid_edges.append(e)

    cell_w = max((s["w"] for s in all_nodes), default=120.0) + 40.0
    cell_h = max((s["h"] for s in all_nodes), default=60.0) + 40.0
    pos = layout_positions(graph, node_w=cell_w, node_h=cell_h)

    def _place(items, size_key_w, size_key_h):
        out = []
        for it in items:
            if it["id"] not in pos:
                out.append(it)
                continue
            cx, cy = pos[it["id"]]
            it2 = dict(it)
            it2["x"] = cx + (cell_w - it[size_key_w]) / 2.0
            it2["y"] = cy + (cell_h - it[size_key_h]) / 2.0
            out.append(it2)
        return out

    new_shapes = _place(shapes, "w", "h")
    new_unknown = []
    for i, u in enumerate(unknown):
        nid = f"{_UNK_PREFIX}{i}"
        uw, uh = max(1.0, float(u.get("w", 40.0))), max(1.0, float(u.get("h", 40.0)))
        if nid not in pos:
            new_unknown.append(u)
            continue
        cx, cy = pos[nid]
        u2 = dict(u)
        u2["x"] = cx + (cell_w - uw) / 2.0
        u2["y"] = cy + (cell_h - uh) / 2.0
        new_unknown.append(u2)
    return new_shapes, valid_edges, new_unknown


# ── Sketch 변환 ──────────────────────────────────────────────────────────────

def build_sketch(shapes: list[dict], edges: list[dict], unknown: list[dict], *, dark: bool = True):
    """정규화된 shapes/edges/unknown을 `sketch_build.Sketch`로 조립.

    unknown 항목은 P4(에셋 패스, 스코프 밖)가 없어 지금은 전부 "[미확인] 설명"
    플레이스홀더 박스로 남는다(설계 문서의 P4 실패 폴백을 이 단계 전체에 적용)."""
    from easycad.fileio.sketch_build import Sketch

    s = Sketch(dark=dark)
    nodes = {}
    for sh in shapes:
        kind = sh.get("kind", "box")
        label = clean_label(sh.get("label", "")) or None
        x, y = sh["x"], sh["y"]
        w, h = max(1.0, sh["w"]), max(1.0, sh["h"])
        if kind == "ellipse":
            node = s.ellipse(x, y, w, h, label)
        elif kind in ("decision", "terminal"):
            node = s.symbol(kind, x, y, w, h, label)
        else:
            node = s.box(x, y, w, h, label)
        nodes[sh["id"]] = node

    for e in edges:
        src, dst = nodes.get(e.get("from")), nodes.get(e.get("to"))
        if src is None or dst is None:
            continue
        s.arrow(src, dst, label=clean_label(e.get("label", "")) or None)

    for u in unknown:
        desc = clean_label(u.get("desc", ""))
        label = f"[미확인] {desc}" if desc else "[미확인]"
        s.box(u["x"], u["y"], max(1.0, u["w"]), max(1.0, u["h"]), label)

    return s


# ── P3.5: 연결선 보완 ─────────────────────────────────────────────────────────

def complete_edges(api_key: str, img, shapes: list[dict], *, note: str = "",
                    model: str = gw.DEFAULT_MODEL) -> list[dict]:
    """전체 이미지 + 병합된 shapes 목록을 다시 모델에 보내 "이 도형들 사이 실제 연결선"만
    찾는다("P3.5 연결선 보완" 절 참조). 반환은 후보 edges — `from`/`to`가 `shapes`에 실제
    존재하는 id일 때만 채택하고(모델이 지시를 어기고 새 id를 만들 가능성에 대한 방어),
    자기순환(`from==to`)은 제거한다. 호출자가 기존 edges와의 중복 제거를 담당한다."""
    if not shapes:
        return []
    prompt = _edge_completion_prompt(shapes, img.width, img.height, note)
    res = gw.call_with_fallback(api_key, img, prompt, model=model, schema=EDGE_SCHEMA)
    data = gw.parse_json(res.content)
    valid_ids = {s["id"] for s in shapes}
    out = []
    for e in data.get("edges", []):
        f, t = e.get("from"), e.get("to")
        if f in valid_ids and t in valid_ids and f != t:
            out.append({"from": f, "to": t, "label": e.get("label", "")})
    return out


def _merge_completed_edges(edges: list[dict], candidates: list[dict]) -> list[dict]:
    """`edges`에 `candidates`를 중복 없이 추가. 같은 두 도형 사이 선은 방향과 무관하게
    같은 물리적 연결로 본다(from,to)==(to,from) — 보완 패스가 같은 선을 반대 방향으로
    다시 읽어올 가능성이 실제 신호 역방향 존재 가능성보다 흔하다는 판단."""
    seen = {frozenset((e["from"], e["to"])) for e in edges}
    added = []
    for e in candidates:
        key = frozenset((e["from"], e["to"]))
        if key in seen:
            continue
        seen.add(key)
        edges.append(e)
        added.append(e)
    return added


# ── 파이프라인 오케스트레이션 ─────────────────────────────────────────────────

def build_from_image(image_path: str, out_path: str, *, api_key: str = "", note: str = "",
                      overview_model: str = gw.DEFAULT_MODEL, tile_model: str = "gpt-5.4-mini",
                      tile_threshold: int = 15, max_shapes_per_tile: int = 8, zoom: int = 3,
                      complete_missing_edges: bool = True, edge_model: str = "",
                      dark: bool = True, verbose: bool = True, on_progress=None) -> dict:
    """P1~P3 전체 파이프라인. `.ecad`를 `out_path`에 저장하고 요약 dict를 반환한다.

    `on_progress`(선택, `str`을 받는 콜백)를 주면 각 단계 로그를 `print` 대신/추가로
    그 콜백에도 넘긴다 — C단계(앱 통합)가 이걸로 백그라운드 스레드의 진행 상황을
    Qt 시그널로 UI에 전달한다(`easycad/canvas/host_ai.py`)."""
    from PIL import Image

    def _log(msg: str) -> None:
        if verbose:
            print(msg)
        if on_progress is not None:
            on_progress(msg)

    api_key = gw.resolve_api_key(api_key)
    img = Image.open(image_path).convert("RGB")
    W, H = img.width, img.height

    ov_prompt = _overview_prompt(W, H, note)
    ov = gw.call_with_fallback(api_key, img, ov_prompt, model=overview_model, schema=SKETCH_SCHEMA)
    data = gw.parse_json(ov.content)
    _log(f"[P1 개괄] {ov.model_used} ({ov.elapsed:.1f}s) "
         f"shapes={len(data.get('shapes', []))} edges={len(data.get('edges', []))} "
         f"unknown={len(data.get('unknown', []))}")

    p1_shapes = data.get("shapes", [])
    p1_unknown = data.get("unknown", [])
    total_items = len(p1_shapes) + len(p1_unknown)

    if total_items <= tile_threshold:
        shapes, edges, unknown = p1_shapes, data.get("edges", []), p1_unknown
        tiles_used = 0
    else:
        tiles = compute_tiles(p1_shapes + p1_unknown, W, H, max_shapes_per_tile=max_shapes_per_tile)
        all_shapes: list[dict] = []
        all_edges: list[dict] = []
        all_unknown: list[dict] = []
        for i, box in enumerate(tiles):
            crop, z, left, top = crop_and_zoom(img, box, zoom=zoom)
            prompt = _tile_prompt(crop.width, crop.height, note)
            try:
                res = gw.call_with_fallback(api_key, crop, prompt, model=tile_model, schema=SKETCH_SCHEMA)
            except Exception as e:
                _log(f"[P2 타일 {i}] 실패: {e}")
                continue
            tdata = gw.parse_json(res.content)
            _log(f"[P2 타일 {i}/{len(tiles)}] {res.model_used} ({res.elapsed:.1f}s) "
                 f"shapes={len(tdata.get('shapes', []))} edges={len(tdata.get('edges', []))}")
            ns = namespace_tile_result(i, tdata)
            all_shapes.extend(restore_item_coords(sh, left, top, z) for sh in ns["shapes"])
            all_unknown.extend(restore_item_coords(u, left, top, z) for u in ns["unknown"])
            all_edges.extend(ns["edges"])
        shapes, edges = dedupe_shapes(all_shapes, all_edges)
        unknown = all_unknown
        tiles_used = len(tiles)

        if complete_missing_edges:
            try:
                em = edge_model or overview_model
                candidates = complete_edges(api_key, img, shapes, note=note, model=em)
                added = _merge_completed_edges(edges, candidates)
                _log(f"[P3.5 연결선 보완] {em} 신규 edges={len(added)}")
            except Exception as e:
                _log(f"[P3.5 연결선 보완] 실패(건너뜀): {e}")

    shapes, edges, unknown = layout_graph(shapes, edges, unknown)

    sk = build_sketch(shapes, edges, unknown, dark=dark)
    sk.save(out_path)
    summary = {"shapes": len(shapes), "edges": len(edges), "unknown": len(unknown),
               "tiles": tiles_used, "overview_model": ov.model_used, "path": out_path}
    _log(f"[P3 완료] shapes={len(shapes)} edges={len(edges)} unknown={len(unknown)} "
         f"tiles={tiles_used} → {out_path}")
    return summary


def build_from_manual_json(text: str, out_path: str, *, dark: bool = True) -> dict:
    """수동 붙여넣기 모드 — 사용자가 `manual_prompt()`를 다른 AI 챗에 붙여넣어 받은 JSON
    응답(`text`)을 그대로 `.ecad`로 변환한다. 게이트웨이 호출이 전혀 없다(API 크레딧
    무사용). P1 단일 패스 결과로만 취급 — `dedupe_shapes`는 여러 타일을 잇는 용도라
    여기선 의미가 없어 건너뛴다(단일 응답이라 타일 경계 자체가 없음). 좌표는 다른 경로와
    동일하게 `layout_graph`로 관계 기반 재배치한다 — 수동 모드도 결국 AI가 찍은 좌표를
    받는 거라 같은 부정확성 위험을 그대로 안고 있다.

    `text`가 유효한 JSON이 아니면 `json.JSONDecodeError`가 그대로 올라간다 — 호출자
    (`host_ai.py`)가 잡아 사용자에게 보여준다."""
    data = gw.parse_json(text)
    shapes = data.get("shapes", [])
    edges = data.get("edges", [])
    unknown = data.get("unknown", [])
    shapes, edges, unknown = layout_graph(shapes, edges, unknown)
    sk = build_sketch(shapes, edges, unknown, dark=dark)
    sk.save(out_path)
    return {"shapes": len(shapes), "edges": len(edges), "unknown": len(unknown),
            "tiles": 0, "overview_model": "manual", "path": out_path}
