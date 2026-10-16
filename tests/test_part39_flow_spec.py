"""§8 항목52 새 흐름도 엔진(2026-10-16) — AI는 「내용 설계서」(JSON), 배치·색은 앱.

- `easycad/fileio/flow_spec.py` — 설계서 읽기(너그럽게)·칸 계산(되돌아가는 고리 빼기)·띠 배치.
- `easycad/ai/text_to_flow.py` — 지시문(새로 만들기·그림·이어 고치기), Mermaid 바탕이면 옛 경로.
- `host_fileio._build_flowspec_items` — 띠·이름표·상자·강조 하나·아이콘·화살표, 「도면 검사」 0개.
- 결과 막대 한 줄 — 「세로로」(AI 없이 방향), 이어 고치기(바탕 = 설계서), 비교 표시(달라진 상자·화살표만).
"""
import json
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

from PyQt6.QtGui import QColor

from easycad.canvas.annotator_core import _PathItem, _RectItem, _SymbolItem, _PolyArrowItem
from easycad.canvas.drawing_check import check_drawing
from easycad.canvas.host_widgets import _ACCENT_CORAL
from easycad.fileio import flow_spec as fs

SPEC = {
    "title": "송신소 장애 대응", "direction": "LR", "lanes": ["감시실", "송신소", "본사"],
    "steps": [
        {"id": "s1", "text": "경보 발생", "lane": "감시실", "kind": "start"},
        {"id": "s2", "text": "원격 상태 확인", "lane": "감시실"},
        {"id": "s3", "text": "자동 절체 성공?", "lane": "감시실", "kind": "decision"},
        {"id": "s4", "text": "현장 출동", "lane": "송신소"},
        {"id": "s5", "text": "송신기 점검", "lane": "송신소", "icon": "DTV"},
        {"id": "s6", "text": "장애 보고서", "lane": "본사", "kind": "document"},
        {"id": "s7", "text": "정상 송출", "lane": "감시실", "kind": "end"},
    ],
    "links": [
        {"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}, {"from": "s3", "to": "s7", "text": "예"},
        {"from": "s3", "to": "s4", "text": "아니오"}, {"from": "s4", "to": "s5"}, {"from": "s5", "to": "s6"},
        {"from": "s5", "to": "s2", "text": "재확인"},
    ],
    "focus": "s3",
}
SPEC_TEXT = json.dumps(SPEC, ensure_ascii=False)


# ── 설계서 읽기 ─────────────────────────────────────────────────────────────────────

def test_parse_spec_is_lenient():
    raw = "설명입니다\n```json\n" + json.dumps({
        "direction": "tb", "lanes": [{"name": "갑"}, "을"],
        "steps": [{"id": "a", "label": "시작", "type": "begin", "lane": "갑"}, {"id": "b", "text": "판단?", "kind": "if"},
                  {"id": "c", "text": "모르는 종류", "kind": "zzz", "lane": "병"}, {"id": "a", "text": "같은 id는 버림"},
                  {"text": ""}],
        "links": [{"from": "a", "to": "b"}, {"from": "b", "to": "없음"}, {"from": "c", "to": "c"}, {"src": "b", "dst": "c", "label": "예"}],
        "focus": "없는 id"}, ensure_ascii=False) + "\n```\n끝"
    spec = fs.parse_spec(raw)
    assert spec.direction == "TD"
    assert [(s.id, s.kind, s.lane) for s in spec.steps] == [("a", "start", "갑"), ("b", "decision", "갑"), ("c", "step", "병")]
    assert spec.lanes == ["갑", "을", "병"]                               # 단계에만 나온 담당은 뒤에 붙음
    assert [(k.src, k.dst, k.text) for k in spec.links] == [("a", "b", ""), ("b", "c", "예")]
    assert spec.focus == ""


def test_parse_spec_single_lane_means_no_bands_and_errors():
    spec = fs.parse_spec('{"lanes": ["하나"], "steps": [{"id": "a", "text": "A", "lane": "하나"}]}')
    assert spec.lanes == [] and spec.steps[0].lane == ""
    for bad in ("flowchart LR\n A-->B", "{ 깨진", '{"steps": []}', "[1, 2]"):
        try:
            fs.parse_spec(bad)
        except fs.FlowSpecError:
            continue
        raise AssertionError(bad)
    assert fs.looks_like_spec("```json\n{}\n```") and not fs.looks_like_spec("flowchart LR\n A-->B")


def test_to_json_roundtrips_and_direction_change():
    spec = fs.parse_spec(SPEC_TEXT)
    again = fs.parse_spec(spec.to_json())
    assert fs.all_keys(again) == fs.all_keys(spec) and again.focus == "s3" and again.lanes == spec.lanes
    assert fs.parse_spec(fs.with_direction(SPEC_TEXT, "TD")).direction == "TD"


def test_ranks_skip_back_links():
    spec = fs.parse_spec(SPEC_TEXT)
    r = fs.ranks_of(spec)
    assert r == {"s1": 0, "s2": 1, "s3": 2, "s7": 3, "s4": 3, "s5": 4, "s6": 5}   # s5 → s2(재확인)는 칸 계산에서 빠짐


def test_layout_lanes_contain_boxes_without_overlap():
    for direction in ("LR", "TD", "RL", "BT"):
        spec = fs.parse_spec(fs.with_direction(SPEC_TEXT, direction))
        lay = fs.layout(spec, lambda s: (120.0, 56.0), head=60.0, icon_h=30.0)
        boxes = list(lay.boxes.items())
        for i, (a, ra) in enumerate(boxes):
            for b, rb in boxes[i + 1:]:
                sep = (ra[0] + ra[2] <= rb[0] or rb[0] + rb[2] <= ra[0] or ra[1] + ra[3] <= rb[1] or rb[1] + rb[3] <= ra[1])
                assert sep, (direction, a, b)
        lane_of = {s.id: s.lane for s in spec.steps}
        for lb in lay.lanes:
            x, y, w, h = lb.rect
            for sid, (bx, by, bw, bh) in lay.boxes.items():
                inside = x <= bx and bx + bw <= x + w and y <= by and by + bh <= y + h
                assert inside == (lane_of[sid] == lb.name), (direction, sid, lb.name)
        # 흐름 방향대로: 앞 칸이 앞에
        ax = lay.boxes["s1"][0 if direction in ("LR", "RL") else 1]
        bx = lay.boxes["s6"][0 if direction in ("LR", "RL") else 1]
        assert (ax < bx) == (direction in ("LR", "TD")), direction


# ── 지시문 ────────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, content):
        self.content, self.model_used = content, "m"


def test_generate_flow_prompts_and_returns_clean_spec():
    from easycad.ai import text_to_flow as ttf
    seen = []

    def call(_key, prompt, **kw):
        seen.append((prompt, kw))
        return _Res("```json\n" + SPEC_TEXT + "\n```")
    with _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=call):
        text, used = ttf.generate_flow("k", "장애 대응 흐름", model="x", icons=["DTV", "안테나"])
        assert fs.parse_spec(text).focus == "s3" and used == "m"
        assert "장애 대응 흐름" in seen[0][0] and "DTV, 안테나" in seen[0][0] and seen[0][1]["timeout"] == 60.0
        ttf.generate_flow("k", "감시실을 아래로", model="x", base_code=text)
        assert "아래 흐름도 「내용 설계서」를 지시대로" in seen[1][0] and '"s3"' in seen[1][0]
        ttf.generate_flow("k", "", model="x", image=object())
        assert "이미지" in seen[2][0] and seen[2][1]["timeout"] == 120.0 and "쓰지 말 것" in seen[2][0]
    with _patch("easycad.ai.text_to_mermaid.generate_mermaid", return_value=("flowchart LR\n A-->B", "m2")) as gm:
        assert ttf.generate_flow("k", "더 쉽게", model="x", base_code="flowchart LR\n A-->B") == ("flowchart LR\n A-->B", "m2")
        assert gm.call_args.kwargs["base_code"].startswith("flowchart")   # 「풀어 그리기」 결과는 옛 Mermaid로 이어 고침


# ── 그리기 ────────────────────────────────────────────────────────────────────────

def _window():
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    _app.processEvents()
    return w


def _close(w):
    for d in w._docs:
        d.dirty = False
    w.close()


def test_build_flowspec_items_lanes_focus_icon_and_clean_check():
    w = _window()
    n, a, direction, added = w._build_flow_items(SPEC_TEXT)
    assert (n, a, direction) == (7, 7, "LR")
    bands = [it for it in added if isinstance(it, _PathItem)]
    assert len(bands) == 3 and all(b.brush().color().alpha() < 255 for b in bands)
    keyed = [it for it in added if getattr(it, "_flow_key", None) is not None]
    assert len(keyed) == 14                                       # 상자 7 + 화살표 7
    boxes = {it._flow_key[0]: it for it in keyed if not isinstance(it, _PolyArrowItem)}
    focus = boxes["자동 절체 성공?"]
    assert isinstance(focus, _SymbolItem) and focus._kind == "decision"
    assert focus.pen().color().name() == QColor(_ACCENT_CORAL).name()
    assert sum(1 for it in boxes.values() if it.pen().color().name() == QColor(_ACCENT_CORAL).name()) == 1   # 강조는 하나
    assert boxes["경보 발생"]._kind == "terminal" and boxes["장애 보고서"]._kind == "document"
    assert isinstance(boxes["현장 출동"], _RectItem)
    assert boxes["경보 발생"].pen().color() != boxes["현장 출동"].pen().color()   # 띠마다 다른 색
    pts = {it._label.font().pointSize() for it in boxes.values()}
    assert len(pts) == 1                                          # 상자 글자 크기는 모두 같게
    icons = [it for it in added if isinstance(it, _SymbolItem) and it._kind == "dtv"]
    body = boxes["송신기 점검"]
    assert len(icons) == 1 and icons[0].mapRectToScene(icons[0].rect()).bottom() <= body.mapRectToScene(body.rect()).top()
    assert check_drawing(w._scene, items=added) == []
    texts = [it.toPlainText() for it in added if hasattr(it, "toPlainText")]
    assert "송신소 장애 대응" in texts and "본사" in texts
    _close(w)


def test_decision_branches_leave_from_different_corners():
    w = _window()
    nolane = {"direction": "LR", "steps": [{"id": "d", "text": "정상?", "kind": "decision"}, {"id": "e", "text": "송신"},
                                           {"id": "f", "text": "예비 절체"}],
              "links": [{"from": "d", "to": "e", "text": "예"}, {"from": "d", "to": "f", "text": "아니오"},
                        {"from": "f", "to": "e"}]}
    _n, _a, _d, added = w._build_flow_items(json.dumps(nolane, ensure_ascii=False))
    arrows = [it for it in added if isinstance(it, _PolyArrowItem) and isinstance(it._bind_start, _SymbolItem)
              and it._bind_start._kind == "decision"]
    starts = {(round(it.mapToScene(it._pts[0]).x()), round(it.mapToScene(it._pts[0]).y())) for it in arrows}
    assert len(arrows) == 2 and len(starts) == 2                  # 「예」「아니오」가 한 점에서 겹치지 않음
    assert check_drawing(w._scene, items=added) == []
    _close(w)


def test_mermaid_text_still_uses_old_builder():
    w = _window()
    n, a, direction, added = w._build_flow_items("flowchart TD\n A[가] --> B[나]")
    assert (n, a, direction) == (2, 1, "TD") and not [it for it in added if isinstance(it, _PathItem)]
    _close(w)


def test_flowspec_result_survives_save_and_load(tmp_path):
    from easycad.fileio.document import save_document, load_document
    w = _window()
    _n, _a, _d, added = w._build_flow_items(SPEC_TEXT)
    path = str(tmp_path / "flow.ecad")
    save_document(w._scene, path)
    w2 = _window()
    load_document(w2._scene, path)
    bands = [it for it in w2._scene.items() if isinstance(it, _PathItem)]
    assert len(bands) == 3 and all(b.brush().color().alpha() < 255 for b in bands)
    _close(w)
    _close(w2)


# ── 결과 막대(임시 결과 · 한 줄) ─────────────────────────────────────────────────────

def _wait_until(cond, ms=5000):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        _app.processEvents()
        if cond():
            return True
    return False


def _say(w, text):
    line = w._ai_staged.bar.line
    line.setText(text)
    line.returnPressed.emit()
    _app.processEvents()


def _staged_spec(w, result=SPEC_TEXT):
    seen = []

    def gen(*_a, **kw):
        seen.append(kw)
        return result, "fake"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
        w._ai_ctrl.request_make("송신소 장애 대응 흐름", kind="flow")
        assert _wait_until(lambda: w._ai_staged is not None)
    return w._ai_staged, seen


def test_flow_request_sends_icon_names_and_stages_spec():
    w = _window()
    st, seen = _staged_spec(w)
    assert "DTV" in seen[0]["icons"] and st.request.result_text == SPEC_TEXT
    assert len([it for it in st.items if isinstance(it, _PathItem)]) == 3
    _close(w)


def test_direction_word_redraws_spec_without_ai():
    w = _window()
    st, _seen = _staged_spec(w)
    n_undo = len(w._undo)
    with _patch("easycad.ai.text_to_flow.generate_flow", side_effect=AssertionError("AI 부르면 안 됨")):
        _say(w, "세로로")
    cur = w._ai_staged
    assert cur is not st and fs.parse_spec(cur.request.result_text).direction == "TD"
    assert len(w._undo) == n_undo and all(it.scene() is None for it in st.items)
    _close(w)


def test_followup_sends_spec_and_marks_only_changed():
    w = _window()
    st, _seen = _staged_spec(w)
    changed = json.loads(SPEC_TEXT)
    changed["steps"].append({"id": "s8", "text": "경보 기록", "lane": "본사"})
    changed["links"].append({"from": "s6", "to": "s8"})
    new_text = json.dumps(changed, ensure_ascii=False)
    seen = []

    def gen(*_a, base_code="", **_k):
        seen.append(base_code)
        return new_text, "m"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
        _say(w, "본사에 경보 기록 추가")
        assert _wait_until(lambda: w._ai_staged is not None and w._ai_staged is not st)
    assert seen == [SPEC_TEXT]
    new = w._ai_staged
    assert new.alt is st
    marked = sorted(getattr(it, "_flow_key", ("?",))[0] for it in new.marks)
    assert marked == ["경보 기록", "장애 보고서"]                    # 새 상자 + 새 화살표(앞 상자 글)
    assert new.alt_marks == []
    _close(w)


# ── 꺾어 내리기(2026-10-16) ─────────────────────────────────────────────────────────

def _chain(n, lanes=()):
    steps = [{"id": f"s{i}", "text": f"단계 {i}", **({"lane": lanes[(i - 1) * len(lanes) // n]} if lanes else {})}
             for i in range(1, n + 1)]
    return fs.parse_spec(json.dumps({"direction": "LR", "lanes": list(lanes), "steps": steps,
                                     "links": [{"from": f"s{i}", "to": f"s{i + 1}"} for i in range(1, n)]},
                                    ensure_ascii=False))


def test_best_wrap_only_for_long_flows():
    size = lambda s: (150.0, 56.0)   # noqa: E731
    assert fs.best_wrap(_chain(5), size) is None
    per = fs.best_wrap(_chain(18), size)
    assert per is not None and 3 <= per < 18
    flat, folded = fs.layout(_chain(18), size), fs.layout(_chain(18), size, wrap=per)
    assert abs(folded.width / folded.height - 16 / 9) < abs(flat.width / flat.height - 16 / 9)
    assert max(folded.segments.values()) == (17 // per)
    boxes = list(folded.boxes.values())
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]


def test_fold_draws_only_lanes_used_in_each_segment():
    spec = _chain(15, lanes=("가", "나", "다", "라", "마"))
    lay = fs.layout(spec, lambda s: (150.0, 56.0), head=60.0, wrap=8)
    per_seg = {}
    for lb in lay.lanes:
        per_seg.setdefault(round(lb.rect[1]), []).append(lb.name)
    assert len(lay.lanes) < 2 * 5                                    # 덩어리마다 다섯 띠를 다 그리지 않음
    assert {s.lane for s in spec.steps} <= {lb.name for lb in lay.lanes}


def test_long_flow_builds_folded_with_clean_check():
    w = _window()
    spec = {"direction": "LR", "steps": [{"id": f"s{i}", "text": f"처리 단계 {i}"} for i in range(1, 19)],
            "links": [{"from": f"s{i}", "to": f"s{i + 1}"} for i in range(1, 18)]}
    _n, _a, _d, added = w._build_flow_items(json.dumps(spec, ensure_ascii=False))
    r = w._ai_items_rect(added)
    assert r.width() / r.height() < 4                                # 한 줄(18칸)이면 10배 넘게 길다
    assert check_drawing(w._scene, items=added) == []
    _close(w)
