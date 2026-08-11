"""§8 항목18(AI 이미지→도면, 앱 내장) A+B+C단계.

A단계 — `easycad/ai/gateway.py`: 오류 분류(model_not_found/timeout/quota/server_busy)·
폴백 선택·JSON 파싱 등 순수 로직만 검증한다(실제 게이트웨이 호출은 여기서 하지 않음 —
그건 `tools/ai_probe.py` 수동 실행 몫, `docs/ai_image_import.md` 실측 참조).

B단계 — `easycad/ai/sketch_pipeline.py`(2026-08-11 `tools/ai_sketch.py`에서 이동 — C단계
앱 통합이 같은 파이프라인을 가져다 쓰려면 `tools/`가 아니라 `easycad/`에 있어야 했다):
P1(개괄)~P3(병합·정규화) 파이프라인. 게이트웨이 호출은 전부 mock — 실호출 검증은 별도
(수동 `tools/ai_sketch.py` 실행). 좌표 복원(P2 크롭 좌표계 → 원본 좌표계,
`restore_item_coords`)이 가장 틀리기 쉬운 지점이라 전용 테스트를 둔다(순서: zoom으로
나눈 뒤 크롭 오프셋을 더한다 — 반대로 하면 오프셋 자체가 zoom배 되어 크게 어긋난다).

C단계 — `easycad/canvas/host_ai.py`(2026-08-11, 이 코드베이스 첫 `QThread` 사용): 입력
다이얼로그(`host_dialogs._AIImageImportDialog`)·백그라운드 워커(`_AISketchWorker`)·
결과 삽입(`document.insert_items`, `load_document`처럼 씬을 지우지 않는 버전)·undo 통합
(`push_undo_add_many`, Mermaid 가져오기와 동일 관례). 워커는 `start()`을 동기 호출로
치환해 실제 스레드 없이 신호 배선만 검증(타이밍 불확실성 회피) — 진짜 스레드 동시성
자체는 Qt가 보장하는 부분이라 이 테스트의 관심사가 아니다.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part9_ai_image_import.py.
"""
import json
import os

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QDialog, QDialogButtonBox

from _shared import *  # noqa: F401,F403

from easycad.ai import gateway as gw  # noqa: E402
from easycad.ai import sketch_pipeline as ais  # noqa: E402
from easycad.canvas import host_ai as hai  # noqa: E402
from easycad.canvas.host_dialogs import _AIImageImportDialog, _AISketchProgressDialog  # noqa: E402
from easycad.fileio.document import load_document, insert_items  # noqa: E402


# ── A단계: gateway.py 오류 분류·폴백·파싱 ────────────────────────────────────

def test_gateway_classify_error_timeout_and_model_not_found():
    assert gw.classify_error(Exception("Error code: 504 Gateway Timeout")) == "timeout"
    assert gw.classify_error(Exception("Request timed out.")) == "timeout"
    assert gw.classify_error(Exception("Error code: 404 - model 'x' not found")) == "model_not_found"
    assert gw.classify_error(Exception("Error code: 429 RESOURCE_EXHAUSTED")) == "quota"
    assert gw.classify_error(Exception("Error code: 503 Service Unavailable")) == "server_busy"
    assert gw.classify_error(Exception("some other weird error")) == "other"


def test_gateway_select_fallback_model_skips_failed_and_returns_none_when_exhausted():
    assert gw.select_fallback_model("gemini-3.6-flash") == "gemini-2.0-flash"
    assert gw.select_fallback_model("gemini-2.0-flash", chain=("gemini-2.0-flash",)) is None


def test_gateway_call_with_fallback_falls_back_on_timeout():
    """claude-* 계열이 밀집 도면 전체 이미지에서 504를 내는 실측 함정(docs/pitfalls.md) —
    call_with_fallback이 model_not_found뿐 아니라 timeout에도 폴백해야 한다."""
    calls = []

    def fake_call_vision(client, model, img, prompt, *, schema=None, schema_name="drawing", max_tokens=0):
        calls.append(model)
        if model == "claude-sonnet-5":
            raise RuntimeError("Error code: 504 Gateway Timeout")
        return '{"shapes":[],"edges":[],"unknown":[]}', 1.23

    with patch.object(gw, "_client", lambda *a, **k: object()), \
         patch.object(gw, "call_vision", fake_call_vision):
        result = gw.call_with_fallback("key", object(), "prompt", model="claude-sonnet-5",
                                        fallback_chain=("claude-sonnet-5", "gemini-3.6-flash"))
    assert calls == ["claude-sonnet-5", "gemini-3.6-flash"]
    assert result.model_used == "gemini-3.6-flash"
    assert result.fallback_from == "claude-sonnet-5"


def test_gateway_call_with_fallback_does_not_swallow_quota_error():
    """429/503은 폴백 대상이 아니다 — 조용히 갈아타면 실패를 성공으로 오인하게 된다
    (ocr_engine 프로브 분리 원칙, docs/pitfalls.md 참조)."""
    def fake_call_vision(*a, **k):
        raise RuntimeError("Error code: 429 RESOURCE_EXHAUSTED")

    raised = None
    with patch.object(gw, "_client", lambda *a, **k: object()), \
         patch.object(gw, "call_vision", fake_call_vision):
        try:
            gw.call_with_fallback("key", object(), "prompt", model="gemini-3.6-flash")
        except RuntimeError as e:
            raised = e
    assert raised is not None and "429" in str(raised)


def test_gateway_parse_json_strips_code_fence():
    assert gw.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert gw.parse_json('{"a": 1}') == {"a": 1}


def test_gateway_resolve_api_key_prefers_explicit():
    assert gw.resolve_api_key("explicit-key") == "explicit-key"


def test_gateway_resolve_api_key_reads_secrets_file_before_env():
    """`jbnu-gateway` 스킬과 동일한 secrets 파일 관례(2026-08-11 도입) — 첫 줄을 읽고,
    파일이 없으면 조용히 다음 소스(QSettings→환경변수)로 넘어간다."""
    secrets_path = os.path.join(_TMP, f"secrets_{uuid.uuid4().hex}.key")
    with open(secrets_path, "w", encoding="utf-8") as f:
        f.write("\nfile-key-value\n")  # 첫 줄이 빈 줄이어도 첫 "비어있지 않은" 줄을 읽음
    with patch.object(gw, "SECRETS_FILE", __import__("pathlib").Path(secrets_path)):
        assert gw.resolve_api_key() == "file-key-value"


def test_gateway_resolve_api_key_falls_back_when_secrets_file_missing():
    missing = os.path.join(_TMP, f"missing_{uuid.uuid4().hex}.key")
    with patch.object(gw, "SECRETS_FILE", __import__("pathlib").Path(missing)), \
         patch.dict(os.environ, {gw.KEY_ENV: "env-key-value"}):
        assert gw.resolve_api_key() == "env-key-value"


# ── B단계: 좌표 복원(P2→P3) ──────────────────────────────────────────────────

def test_restore_item_coords_divides_by_zoom_then_adds_offset():
    # 순서 검증: 오프셋을 먼저 더하면 100(x)이 그대로 커져 결과가 크게 어긋난다.
    item = {"x": 90.0, "y": 60.0, "w": 30.0, "h": 12.0}
    out = ais.restore_item_coords(item, crop_left=55.0, crop_top=50.0, zoom=3)
    assert out["x"] == 90.0 / 3 + 55.0 == 85.0
    assert out["y"] == 60.0 / 3 + 50.0 == 70.0
    assert out["w"] == 30.0 / 3 == 10.0
    assert out["h"] == 12.0 / 3 == 4.0


def test_restore_item_coords_zoom_1_is_pure_offset():
    item = {"x": 5.0, "y": 5.0, "w": 20.0, "h": 20.0}
    out = ais.restore_item_coords(item, crop_left=100.0, crop_top=200.0, zoom=1)
    assert out == {"x": 105.0, "y": 205.0, "w": 20.0, "h": 20.0}


def test_crop_and_zoom_uses_rounded_int_offset_and_downscales_over_max_dim():
    from PIL import Image
    img = Image.new("RGB", (1000, 1000), "white")
    crop, z, left, top = ais.crop_and_zoom(img, (10.4, 20.6, 100.0, 100.0), zoom=3, max_dim=250)
    assert left == 10 and top == 21  # round(10.4)=10, round(20.6)=21
    assert max(crop.width, crop.height) <= 250
    assert z * 100 == crop.width  # 정사각 크롭이라 폭==zoom*원본폭


# ── B단계: 타일 격자 ─────────────────────────────────────────────────────────

def test_compute_tiles_only_covers_occupied_cells():
    # 왼쪽에 몰린 8개 항목 → 오른쪽 절반은 빈 칸이라 타일 목록에서 제외돼야 함.
    items = [{"x": i * 10, "y": 0, "w": 8, "h": 8} for i in range(8)]
    tiles = ais.compute_tiles(items, img_w=1000, img_h=200, max_shapes_per_tile=4)
    assert tiles  # 최소 1개
    for left, top, w, h in tiles:
        assert 0 <= left < 1000 and 0 <= top < 200
        assert left + w <= 1000 + 1e-6 and top + h <= 200 + 1e-6
        assert left < 200  # 항목이 전부 x<80에 있으므로 점유 셀은 왼쪽에만


def test_compute_tiles_empty_items_returns_empty():
    assert ais.compute_tiles([], 100, 100) == []


# ── B단계: 타일 결과 네임스페이스 ────────────────────────────────────────────

def test_namespace_tile_result_prefixes_ids_and_drops_cross_tile_edges():
    data = {
        "shapes": [{"id": "s1", "kind": "box", "x": 0, "y": 0, "w": 10, "h": 10, "label": "a"}],
        "edges": [{"from": "s1", "to": "ghost", "label": ""}],  # ghost는 이 타일 shapes에 없음
        "unknown": [{"x": 1, "y": 1, "w": 2, "h": 2, "desc": "?"}],
    }
    out = ais.namespace_tile_result(3, data)
    assert out["shapes"][0]["id"] == "t3_s1"
    assert out["edges"] == []  # to가 이 타일 안에 없으므로 드롭
    assert out["unknown"] == data["unknown"]


# ── B단계: 병합·중복제거·정규화 ──────────────────────────────────────────────

def test_dedupe_shapes_merges_overlapping_boxes_from_tile_overlap():
    shapes = [
        {"id": "t0_a", "kind": "box", "x": 100.0, "y": 100.0, "w": 80.0, "h": 40.0, "label": "펌프"},
        {"id": "t1_a", "kind": "box", "x": 103.0, "y": 98.0, "w": 78.0, "h": 42.0, "label": "펌프"},
    ]
    edges = [{"from": "t1_a", "to": "t0_a", "label": ""}]  # 병합되면 자기순환이 되어 사라져야 함
    kept, ne = ais.dedupe_shapes(shapes, edges)
    assert len(kept) == 1
    assert kept[0]["id"] == "t0_a"
    assert ne == []


def test_dedupe_shapes_keeps_distinct_adjacent_boxes():
    # 살짝 겹치는 정도(IoU 낮음)의 이웃 도형은 서로 다른 도형으로 남아야 한다.
    shapes = [
        {"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 100.0, "h": 50.0, "label": "A"},
        {"id": "b", "kind": "box", "x": 98.0, "y": 2.0, "w": 100.0, "h": 48.0, "label": "B"},
    ]
    kept, _ = ais.dedupe_shapes(shapes, [])
    assert len(kept) == 2


def test_dedupe_shapes_remaps_edge_endpoints_to_canonical_id():
    shapes = [
        {"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 50.0, "h": 50.0, "label": "A"},
        {"id": "a_dup", "kind": "box", "x": 1.0, "y": 1.0, "w": 49.0, "h": 49.0, "label": "A"},
        {"id": "b", "kind": "box", "x": 500.0, "y": 0.0, "w": 50.0, "h": 50.0, "label": "B"},
    ]
    edges = [{"from": "a_dup", "to": "b", "label": "간다"}]
    kept, ne = ais.dedupe_shapes(shapes, edges)
    ids = {s["id"] for s in kept}
    assert ids == {"a", "b"}
    assert ne == [{"from": "a", "to": "b", "label": "간다"}]


def test_dedupe_shapes_merges_same_label_low_overlap_from_real_diagram():
    """실사용 KBS 도면(ee.ecad) 재현 — 'STL-TX MT PLATINUM 1.701.75GHz'가 서로 다른
    타일에서 다른 정밀도로 두 번 감지돼 IoU가 겨우 0.12까지 떨어진 실제 사례. 순수
    IoU 임계값(0.4)만으로는 못 잡고, 라벨이 같을 때만 적용되는 낮은 바닥값(0.05)이
    잡아야 한다."""
    a = {"id": "a", "kind": "box", "x": 2830.0, "y": 598.0, "w": 285.5, "h": 325.0,
         "label": "STL-TX MT PLATINUM 1.701.75GHz"}
    b = {"id": "b", "kind": "box", "x": 2842.0, "y": 868.0, "w": 255.5, "h": 168.0,
         "label": "STL-TX MT PLATINUM 1.701.75GHz"}
    kept, _ = ais.dedupe_shapes([a, b], [])
    assert len(kept) == 1


def test_dedupe_shapes_merges_whitespace_differing_label_via_iou():
    """실사용 사례 — 같은 실물을 두 타일이 각각 다른 쉼표 뒤 공백으로 OCR한 경우
    ('6950,6990MHz' vs '6950, 6990MHz'). IoU 0.48(순수 기하 임계값 0.4 이상)로 잡힘."""
    a = {"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 100.0, "h": 50.0,
         "label": "노고향 M/W EK-MFR/2 6950,6990MHz"}
    b = {"id": "b", "kind": "box", "x": 5.0, "y": 5.0, "w": 100.0, "h": 50.0,
         "label": "노고향 M/W EK-MFR/2 6950, 6990MHz"}
    kept, _ = ais.dedupe_shapes([a, b], [])
    assert len(kept) == 1


def test_dedupe_shapes_does_not_merge_legitimate_nested_different_labels():
    """"PIC-FM"이 그 안의 "Audio(A)"를 감싸는 것처럼 라벨이 다른 진짜 별개 구성요소는
    겹쳐도(실측 IoU 0.11~0.35) 합치면 안 된다 — 라벨 신호는 라벨이 같을 때만 쓴다."""
    outer = {"id": "outer", "kind": "box", "x": 0.0, "y": 0.0, "w": 200.0, "h": 200.0, "label": "PIC-FM"}
    inner = {"id": "inner", "kind": "box", "x": 50.0, "y": 50.0, "w": 100.0, "h": 100.0, "label": "Audio(A)"}
    kept, _ = ais.dedupe_shapes([outer, inner], [])
    assert len(kept) == 2


def test_dedupe_shapes_does_not_merge_same_label_when_spatially_separate():
    """같은 라벨이라도 공간적으로 멀리 떨어져 있으면(IoU≈0, 예: TX-A/TX-B 양쪽의
    "SYT-5K") 별개 실물로 보존해야 한다 — label_iou_floor가 이 경우를 걸러낸다."""
    a = {"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 50.0, "h": 30.0, "label": "SYT-5K"}
    b = {"id": "b", "kind": "box", "x": 1000.0, "y": 1000.0, "w": 50.0, "h": 30.0, "label": "SYT-5K"}
    kept, _ = ais.dedupe_shapes([a, b], [])
    assert len(kept) == 2


# ── P4: 관계 기반 배치(2026-08-11) ───────────────────────────────────────────

def _rects_overlap(a, b):
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    return not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0)


def test_layout_graph_eliminates_overlap_from_pathologically_bad_raw_coords():
    """실사용 KBS 도면 재현 — vision 모델의 좌표 추정 오차로 원래 좌표가 서로 크게
    겹쳐 있어도(A*의 재시도 폭주로 916ms/frame까지 느려진 근본 원인), layout_graph 이후엔
    겹침이 원리적으로 0이어야 한다(격자 셀 크기를 최대 도형 크기로 잡으므로)."""
    shapes = [
        {"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 100.0, "h": 50.0, "label": "A"},
        {"id": "b", "kind": "box", "x": 50.0, "y": 50.0, "w": 100.0, "h": 50.0, "label": "B"},
        {"id": "c", "kind": "box", "x": 50.0, "y": 50.0, "w": 100.0, "h": 50.0, "label": "C"},
    ]
    edges = [{"from": "a", "to": "b", "label": ""}, {"from": "a", "to": "c", "label": ""}]
    unknown = [{"x": 1000.0, "y": 1000.0, "w": 40.0, "h": 40.0, "desc": "미확인"}]

    new_shapes, new_edges, new_unknown = ais.layout_graph(shapes, edges, unknown)
    all_items = new_shapes + new_unknown
    for i in range(len(all_items)):
        for j in range(i + 1, len(all_items)):
            assert not _rects_overlap(all_items[i], all_items[j]), \
                (all_items[i]["label"], all_items[j].get("label") or all_items[j].get("desc"))
    assert new_edges == edges   # 두 끝 다 유효한 id라 그대로 채택


def test_layout_graph_preserves_original_shape_sizes():
    shapes = [{"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 77.0, "h": 33.0, "label": "A"},
              {"id": "b", "kind": "ellipse", "x": 0.0, "y": 0.0, "w": 55.0, "h": 90.0, "label": "B"}]
    new_shapes, _, _ = ais.layout_graph(shapes, [{"from": "a", "to": "b", "label": ""}])
    sizes = {s["id"]: (s["w"], s["h"]) for s in new_shapes}
    assert sizes["a"] == (77.0, 33.0)
    assert sizes["b"] == (55.0, 90.0)
    kinds = {s["id"]: s["kind"] for s in new_shapes}
    assert kinds == {"a": "box", "b": "ellipse"}   # kind는 layout_graph가 안 건드림


def test_layout_graph_drops_edges_referencing_deduped_or_unknown_ids():
    shapes = [{"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0, "label": "A"}]
    edges = [{"from": "a", "to": "ghost", "label": ""}, {"from": "a", "to": "a", "label": ""}]
    _, new_edges, _ = ais.layout_graph(shapes, edges)
    assert new_edges == []   # 존재하지 않는 id, 자기순환 둘 다 제거


def test_layout_graph_places_isolated_shapes_and_unknown_without_crash():
    """관계(edge)가 하나도 없어도(전부 고립) 죽지 않고 배치돼야 한다 — PIC-FM처럼 P3.5
    보완 전에는 화살표가 0개인 경우가 실제로 있었다."""
    shapes = [{"id": f"s{i}", "kind": "box", "x": float(i * 5), "y": 0.0, "w": 20.0, "h": 20.0,
              "label": f"L{i}"} for i in range(6)]
    new_shapes, new_edges, _ = ais.layout_graph(shapes, [])
    assert len(new_shapes) == 6
    assert new_edges == []
    for i in range(len(new_shapes)):
        for j in range(i + 1, len(new_shapes)):
            assert not _rects_overlap(new_shapes[i], new_shapes[j])


def test_layout_graph_empty_input_returns_empty():
    assert ais.layout_graph([], []) == ([], [], [])


def test_infer_direction_uses_bbox_aspect_ratio():
    wide = [{"x": 0.0, "y": 0.0}, {"x": 1000.0, "y": 10.0}]   # 가로로 넓게 퍼짐
    tall = [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 1000.0}]   # 세로로 넓게 퍼짐
    assert ais._infer_direction(wide) == "LR"
    assert ais._infer_direction(tall) == "TD"
    assert ais._infer_direction([]) == "TD"   # 빈 입력 폴백


def test_build_from_manual_json_output_has_no_overlap_even_with_bad_coords():
    """수동 모드도 같은 layout_graph를 타므로, 사람이 붙여넣은 JSON의 좌표가 겹쳐도
    최종 결과는 겹치지 않아야 한다."""
    payload = json.dumps({
        "shapes": [
            {"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 100.0, "h": 50.0, "label": "A"},
            {"id": "b", "kind": "box", "x": 10.0, "y": 10.0, "w": 100.0, "h": 50.0, "label": "B"},
        ],
        "edges": [{"from": "a", "to": "b", "label": ""}],
        "unknown": [],
    })
    out = os.path.join(_TMP, f"manual_overlap_{uuid.uuid4().hex}.ecad")
    ais.build_from_manual_json(payload, out)
    with open(out, encoding="utf-8") as f:
        doc = json.load(f)
    rects = [it["rect"] for it in doc["items"] if it["type"] == "rect"]
    assert len(rects) == 2
    a, b = ({"x": r[0], "y": r[1], "w": r[2], "h": r[3]} for r in rects)
    assert not _rects_overlap(a, b)


def test_clean_label_collapses_whitespace_and_strips():
    assert ais.clean_label("  a   b\n\nc  ") == "a b c"
    assert ais.clean_label(None) == ""


# ── B단계: Sketch 변환 ───────────────────────────────────────────────────────

def test_build_sketch_maps_kinds_and_unknown_becomes_placeholder():
    shapes = [
        {"id": "s1", "kind": "box", "x": 0.0, "y": 0.0, "w": 100.0, "h": 60.0, "label": "박스"},
        {"id": "s2", "kind": "ellipse", "x": 200.0, "y": 0.0, "w": 80.0, "h": 80.0, "label": "타원"},
        {"id": "s3", "kind": "decision", "x": 400.0, "y": 0.0, "w": 100.0, "h": 60.0, "label": "판단"},
    ]
    edges = [{"from": "s1", "to": "s2", "label": "예"}, {"from": "s2", "to": "s3", "label": ""}]
    unknown = [{"x": 600.0, "y": 0.0, "w": 40.0, "h": 40.0, "desc": "안테나 픽토그램"}]

    sk = ais.build_sketch(shapes, edges, unknown)
    d = sk.to_dict()
    types = [it["type"] for it in d["items"]]
    assert types.count("rect") == 2   # box + unknown 플레이스홀더
    assert types.count("ellipse") == 1
    assert types.count("symbol") == 1
    assert types.count("sarrow") == 2

    unknown_item = next(it for it in d["items"] if it["type"] == "rect" and it["rect"][0] == 600.0)
    assert unknown_item["label"]["text"] == "[미확인] 안테나 픽토그램"


def test_build_sketch_skips_edge_with_unresolved_endpoint():
    shapes = [{"id": "s1", "kind": "box", "x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0, "label": ""}]
    edges = [{"from": "s1", "to": "ghost", "label": ""}]
    sk = ais.build_sketch(shapes, edges, [])
    assert all(it["type"] != "sarrow" for it in sk.to_dict()["items"])


# ── B단계: 전체 파이프라인(mock 게이트웨이) ──────────────────────────────────

def test_build_from_image_skips_tiling_when_under_threshold():
    from PIL import Image
    img_path = os.path.join(_TMP, f"ai_small_{uuid.uuid4().hex}.png")
    Image.new("RGB", (200, 100), "white").save(img_path)

    p1_json = json.dumps({
        "shapes": [{"id": "a", "kind": "box", "x": 10.0, "y": 10.0, "w": 50.0, "h": 30.0, "label": "A"},
                   {"id": "b", "kind": "box", "x": 120.0, "y": 10.0, "w": 50.0, "h": 30.0, "label": "B"}],
        "edges": [{"from": "a", "to": "b", "label": ""}],
        "unknown": [],
    })
    calls = {"n": 0}

    def fake_call(api_key, image, prompt, *, model, schema=None, **kw):
        calls["n"] += 1
        return gw.VisionResult(p1_json, model, None, 0.5)

    out = os.path.join(_TMP, f"ai_small_out_{uuid.uuid4().hex}.ecad")
    with patch.object(ais.gw, "call_with_fallback", fake_call):
        summary = ais.build_from_image(img_path, out, tile_threshold=15, verbose=False)

    assert calls["n"] == 1  # P1만 호출 — 타일링 없음
    assert summary["tiles"] == 0
    assert summary["shapes"] == 2
    assert summary["edges"] == 1
    assert os.path.exists(out)


def test_build_from_image_tiles_and_restores_coords_when_over_threshold():
    from PIL import Image
    img_path = os.path.join(_TMP, f"ai_dense_{uuid.uuid4().hex}.png")
    Image.new("RGB", (400, 200), "white").save(img_path)

    p1_shapes = [{"id": f"s{i}", "kind": "box", "x": float(i), "y": float(i), "w": 10.0, "h": 10.0,
                  "label": f"L{i}"} for i in range(20)]
    p1_json = json.dumps({"shapes": p1_shapes, "edges": [], "unknown": []})

    fixed_tiles = [(0.0, 0.0, 200.0, 200.0), (200.0, 0.0, 200.0, 200.0)]

    tile_json = [
        json.dumps({"shapes": [{"id": "a", "kind": "box", "x": 30.0, "y": 60.0, "w": 90.0, "h": 30.0,
                                "label": "왼쪽"}], "edges": [], "unknown": []}),
        json.dumps({"shapes": [{"id": "a", "kind": "ellipse", "x": 60.0, "y": 90.0, "w": 60.0, "h": 60.0,
                                "label": "오른쪽"}], "edges": [],
                    "unknown": [{"x": 300.0, "y": 300.0, "w": 30.0, "h": 30.0, "desc": "미확인기호"}]}),
    ]
    calls = {"n": 0}

    def fake_call(api_key, image, prompt, *, model, schema=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return gw.VisionResult(p1_json, model, None, 0.5)
        return gw.VisionResult(tile_json[calls["n"] - 2], model, None, 0.5)

    out = os.path.join(_TMP, f"ai_dense_out_{uuid.uuid4().hex}.ecad")
    with patch.object(ais, "compute_tiles", lambda *a, **k: fixed_tiles), \
         patch.object(ais.gw, "call_with_fallback", fake_call):
        # complete_missing_edges=False — 이 테스트는 좌표 복원을 검증하는 게 목적이라
        # P3.5 연결선 보완(별도 테스트 참조)까지 mock하면 관심사가 흐려진다.
        summary = ais.build_from_image(img_path, out, tile_threshold=5, zoom=3, verbose=False,
                                       complete_missing_edges=False)

    assert calls["n"] == 3  # P1 + 타일 2개
    assert summary["tiles"] == 2
    assert summary["shapes"] == 2
    assert summary["unknown"] == 1

    with open(out, encoding="utf-8") as f:
        doc = json.load(f)
    rects = [it for it in doc["items"] if it["type"] == "rect"]
    ellipses = [it for it in doc["items"] if it["type"] == "ellipse"]
    assert len(ellipses) == 1
    # 최종 좌표는 이제 layout_graph()가 관계 기반으로 재배치하므로 restore_item_coords의
    # 정확한 산출값(크롭 오프셋+zoom 복원)은 여기서 검증 안 함 — 그건
    # test_restore_item_coords_divides_by_zoom_then_adds_offset의 몫. 여기서는 크기가
    # 원래 감지된 값 그대로 보존됐는지만 확인(w/h는 layout_graph가 안 건드림,
    # x/30(왼쪽 타일 zoom 3)=30/3=10, 오른쪽 ellipse w=60/3=20 h=60/3=20).
    left_shape = next(it for it in rects if it["rect"][2] == 30.0)  # w=30
    assert left_shape["rect"][3] == 10.0  # h=10
    assert ellipses[0]["rect"][2:] == [20.0, 20.0]
    unk = next(it for it in rects if it["label"]["text"].startswith("[미확인]"))
    assert unk["rect"][2:] == [10.0, 10.0]

    # 실제 앱 문서 로더로도 정상 로드되는지 확인(회귀 방지 — 스키마 드리프트는 즉시 실패).
    w = CanvasWindow()
    n_loaded = load_document(w._scene, str(out))
    assert n_loaded == len(doc["items"])
    w.deleteLater()


# ── P3.5: 연결선 보완(2026-08-11) ────────────────────────────────────────────

def test_edge_completion_prompt_lists_shape_ids_and_labels():
    shapes = [{"id": "a", "label": "PIC-FM", "x": 10.0, "y": 20.0},
              {"id": "b", "label": "SYT-5K", "x": 300.0, "y": 20.0}]
    text = ais._edge_completion_prompt(shapes, 500, 300, "테스트")
    assert "id=a" in text and "PIC-FM" in text
    assert "id=b" in text and "SYT-5K" in text
    assert "테스트" in text
    assert "실제로 그려진" in text


def test_complete_edges_filters_unknown_ids_and_self_loops():
    shapes = [{"id": "a", "label": "A", "x": 0.0, "y": 0.0},
              {"id": "b", "label": "B", "x": 100.0, "y": 0.0}]
    payload = json.dumps({"edges": [
        {"from": "a", "to": "b", "label": ""},          # 유효
        {"from": "a", "to": "ghost", "label": ""},       # 존재하지 않는 id — 버려야 함
        {"from": "b", "to": "b", "label": ""},           # 자기순환 — 버려야 함
    ]})

    def fake_call(api_key, image, prompt, *, model, schema=None, **kw):
        return gw.VisionResult(payload, model, None, 0.5)

    from PIL import Image
    fake_img = Image.new("RGB", (500, 300), "white")
    with patch.object(ais.gw, "call_with_fallback", fake_call):
        out = ais.complete_edges("key", fake_img, shapes)
    assert out == [{"from": "a", "to": "b", "label": ""}]


def test_complete_edges_empty_shapes_skips_call():
    from PIL import Image
    fake_img = Image.new("RGB", (500, 300), "white")
    calls = {"n": 0}

    def fake_call(*a, **k):
        calls["n"] += 1
        return gw.VisionResult('{"edges":[]}', "m", None, 0.1)

    with patch.object(ais.gw, "call_with_fallback", fake_call):
        out = ais.complete_edges("key", fake_img, [])
    assert out == []
    assert calls["n"] == 0


def test_merge_completed_edges_dedupes_regardless_of_direction():
    edges = [{"from": "a", "to": "b", "label": "기존"}]
    candidates = [
        {"from": "b", "to": "a", "label": "역방향 중복"},   # 같은 물리적 연결(방향만 반대) — 버려야 함
        {"from": "b", "to": "c", "label": "새 연결"},       # 진짜 신규
    ]
    added = ais._merge_completed_edges(edges, candidates)
    assert added == [{"from": "b", "to": "c", "label": "새 연결"}]
    assert len(edges) == 2
    assert edges[0]["label"] == "기존"   # 기존 edge는 그대로 유지(덮어쓰지 않음)


def test_build_from_image_tiled_path_runs_edge_completion_and_adds_edges():
    """§8 항목18 실사용 피드백(2026-08-11) — 실도면에서 타일 경계 때문에 도형은 맞게
    인식됐지만 그 사이 선이 통째로 누락되는 문제(KBS 실측: 실제 도형 27개 중 11개가
    화살표 0개, 특히 중앙 핵심 블록 "PIC-FM")를 재현·검증. 타일링된 경로에서 P3.5가
    실제로 호출되어 edges를 보강하는지 종단 확인."""
    from PIL import Image
    img_path = os.path.join(_TMP, f"ai_edgefix_{uuid.uuid4().hex}.png")
    Image.new("RGB", (400, 200), "white").save(img_path)

    p1_shapes = [{"id": f"s{i}", "kind": "box", "x": float(i), "y": float(i), "w": 10.0, "h": 10.0,
                  "label": f"L{i}"} for i in range(20)]
    p1_json = json.dumps({"shapes": p1_shapes, "edges": [], "unknown": []})
    fixed_tiles = [(0.0, 0.0, 200.0, 200.0), (200.0, 0.0, 200.0, 200.0)]
    # 두 타일이 서로 다른 도형만 인식 — 이 둘을 잇는 edge는 애초에 어느 타일에서도
    # 안 나온다(실제 KBS 사례와 동일 패턴, PIC-FM처럼 타일 경계에 걸친 도형 사이 연결).
    tile_json = [
        json.dumps({"shapes": [{"id": "left", "kind": "box", "x": 30.0, "y": 60.0, "w": 90.0, "h": 30.0,
                                "label": "PIC-FM"}], "edges": [], "unknown": []}),
        json.dumps({"shapes": [{"id": "right", "kind": "box", "x": 30.0, "y": 60.0, "w": 90.0, "h": 30.0,
                                "label": "SYT-5K"}], "edges": [], "unknown": []}),
    ]
    edge_completion_json = json.dumps({"edges": [
        {"from": "t0_left", "to": "t1_right", "label": ""}]})   # namespace_tile_result 접두어 반영

    calls = {"n": 0}

    def fake_call(api_key, image, prompt, *, model, schema=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return gw.VisionResult(p1_json, model, None, 0.5)
        if calls["n"] <= 3:
            return gw.VisionResult(tile_json[calls["n"] - 2], model, None, 0.5)
        return gw.VisionResult(edge_completion_json, model, None, 0.5)   # P3.5 호출

    out = os.path.join(_TMP, f"ai_edgefix_out_{uuid.uuid4().hex}.ecad")
    with patch.object(ais, "compute_tiles", lambda *a, **k: fixed_tiles), \
         patch.object(ais.gw, "call_with_fallback", fake_call):
        summary = ais.build_from_image(img_path, out, tile_threshold=5, zoom=3, verbose=False)

    assert calls["n"] == 4   # P1 + 타일 2개 + P3.5 연결선 보완 1회
    assert summary["shapes"] == 2
    assert summary["edges"] == 1   # 타일 단독으로는 0개였을 edge가 P3.5로 보강됨

    with open(out, encoding="utf-8") as f:
        doc = json.load(f)
    arrows = [it for it in doc["items"] if it["type"] == "sarrow"]
    assert len(arrows) == 1


def test_build_from_image_edge_completion_failure_does_not_break_pipeline():
    """P3.5 호출이 실패해도(네트워크 오류 등) 파이프라인 전체가 죽지 않고 P3까지의
    결과로 계속 진행해야 한다(설계 문서의 "P4 실패해도 P3까지는 쓸 수 있다"와 같은
    폴백 철학을 P3.5에도 적용)."""
    from PIL import Image
    img_path = os.path.join(_TMP, f"ai_edgefail_{uuid.uuid4().hex}.png")
    Image.new("RGB", (400, 200), "white").save(img_path)

    p1_shapes = [{"id": f"s{i}", "kind": "box", "x": float(i), "y": float(i), "w": 10.0, "h": 10.0,
                  "label": f"L{i}"} for i in range(20)]
    p1_json = json.dumps({"shapes": p1_shapes, "edges": [], "unknown": []})
    fixed_tiles = [(0.0, 0.0, 200.0, 200.0)]
    tile_json = json.dumps({"shapes": [{"id": "a", "kind": "box", "x": 0.0, "y": 0.0, "w": 10.0, "h": 10.0,
                                        "label": "A"}], "edges": [], "unknown": []})

    calls = {"n": 0}

    def fake_call(api_key, image, prompt, *, model, schema=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return gw.VisionResult(p1_json, model, None, 0.5)
        if calls["n"] == 2:
            return gw.VisionResult(tile_json, model, None, 0.5)
        raise RuntimeError("네트워크 오류(P3.5 실패 시뮬레이션)")

    out = os.path.join(_TMP, f"ai_edgefail_out_{uuid.uuid4().hex}.ecad")
    with patch.object(ais, "compute_tiles", lambda *a, **k: fixed_tiles), \
         patch.object(ais.gw, "call_with_fallback", fake_call):
        summary = ais.build_from_image(img_path, out, tile_threshold=5, zoom=3, verbose=False)

    assert summary["shapes"] == 1   # P3.5가 실패해도 P3 결과는 그대로 저장됨
    assert os.path.exists(out)


# ── C단계: document.insert_items — 씬을 지우지 않는 삽입 ────────────────────

def test_insert_items_preserves_existing_scene_content():
    w = CanvasWindow()
    existing = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 40)

    sk = Sketch(dark=True)
    a = sk.box(100, 100, 80, 40, "A")
    b = sk.box(300, 100, 80, 40, "B")
    sk.arrow(a, b, label="e")
    doc = sk.to_dict()

    added = insert_items(w._scene, doc["items"])
    assert len(added) == 3   # box·box·arrow(라벨은 자식이라 최상위 목록에 안 잡힘)
    assert existing.scene() is w._scene   # 기존 아이템이 지워지지 않았다
    top_level = [it for it in w._scene.items() if it.parentItem() is None]
    assert existing in top_level
    for it in added:
        assert it in top_level
    w.deleteLater()


def test_insert_items_resolves_bindings_within_new_island():
    """새로 삽입되는 아이템끼리의 bind1/bind2 인덱스가 기존 씬 아이템과 충돌하지 않고
    올바르게 자기들끼리만 재연결되는지 — 기존 씬에 이미 아이템이 있는 상태에서 검증."""
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 40)   # 인덱스 오프셋 교란용 기존 아이템

    sk = Sketch(dark=True)
    a = sk.box(100, 100, 80, 40, "A")
    b = sk.box(300, 100, 80, 40, "B")
    sk.arrow(a, b)
    added = insert_items(w._scene, sk.to_dict()["items"])

    arrow = next(it for it in added if isinstance(it, _PolyArrowItem))
    boxes = [it for it in added if it is not arrow]
    assert arrow._bound(0) in boxes
    assert arrow._bound(len(arrow._pts) - 1) in boxes
    w.deleteLater()


# ── C단계: host_ai — 백그라운드 워커·삽입·undo 통합 ──────────────────────────

def test_ai_worker_run_emits_finished_ok_on_success():
    recorded = {}
    worker = hai._AISketchWorker("img.png", os.path.join(_TMP, f"w_{uuid.uuid4().hex}.ecad"), "")
    worker.finished_ok.connect(lambda summary: recorded.setdefault("ok", summary))
    worker.finished_err.connect(lambda msg: recorded.setdefault("err", msg))

    fake_summary = {"shapes": 1, "edges": 0, "unknown": 0, "tiles": 0,
                    "overview_model": "mock", "path": worker._out_path}
    # 크레딧 조회는 실호출이라(gw.get_credit_balance) 테스트에서 반드시 차단 — 실패해도
    # finished_ok 자체는 그대로 나가야 한다(본 결과에 영향 없는 부가정보라는 설계 확인).
    with patch("easycad.ai.sketch_pipeline.build_from_image", return_value=fake_summary), \
         patch("easycad.ai.gateway.get_credit_balance", side_effect=RuntimeError("네트워크 없음")):
        worker.run()

    assert recorded.get("ok") == fake_summary
    assert "credit_remaining" not in recorded["ok"]
    assert "err" not in recorded


def test_ai_worker_run_attaches_credit_balance_when_available():
    worker = hai._AISketchWorker("img.png", os.path.join(_TMP, f"w_{uuid.uuid4().hex}.ecad"), "")
    recorded = {}
    worker.finished_ok.connect(lambda summary: recorded.setdefault("ok", summary))

    fake_summary = {"shapes": 1, "edges": 0, "unknown": 0, "tiles": 0,
                    "overview_model": "mock", "path": worker._out_path}
    with patch("easycad.ai.sketch_pipeline.build_from_image", return_value=fake_summary), \
         patch("easycad.ai.gateway.resolve_api_key", return_value="key"), \
         patch("easycad.ai.gateway.get_credit_balance", return_value=(4085.66, 5000.0)):
        worker.run()

    assert recorded["ok"]["credit_remaining"] == 4085.66
    assert recorded["ok"]["credit_quota"] == 5000.0


def test_ai_worker_run_emits_finished_err_on_exception():
    recorded = {}
    worker = hai._AISketchWorker("img.png", os.path.join(_TMP, f"w_{uuid.uuid4().hex}.ecad"), "")
    worker.finished_ok.connect(lambda summary: recorded.setdefault("ok", summary))
    worker.finished_err.connect(lambda msg: recorded.setdefault("err", msg))

    with patch("easycad.ai.sketch_pipeline.build_from_image",
              side_effect=RuntimeError("게이트웨이 실패")):
        worker.run()

    assert "ok" not in recorded
    assert "게이트웨이 실패" in recorded.get("err", "")


def test_offset_ai_items_to_view_center_moves_bbox_and_keeps_arrow_attached():
    w = CanvasWindow()
    sk = Sketch(dark=True)
    a = sk.box(1000, 1000, 80, 40, "A")
    b = sk.box(1300, 1000, 80, 40, "B")
    sk.arrow(a, b)
    added = insert_items(w._scene, sk.to_dict()["items"])

    w._offset_ai_items_to_view_center(added)

    bbox = None
    for it in added:
        r = it.sceneBoundingRect()
        bbox = r if bbox is None else bbox.united(r)
    center = w._view.mapToScene(w._view.viewport().rect().center())
    assert _close(bbox.center(), center, eps=2.0)

    arrow = next(it for it in added if isinstance(it, _PolyArrowItem))
    boxes = [it for it in added if it is not arrow]
    start_box, end_box = arrow._bound(0), arrow._bound(len(arrow._pts) - 1)
    assert start_box in boxes and end_box in boxes
    # build_elbow 후에도 화살표 양끝이 부착된 도형의 경계 근처에 남아 있는지(재라우팅 확인).
    pts = [arrow.mapToScene(p) for p in arrow._pts]
    start_rect = start_box.mapRectToScene(start_box.rect())
    end_rect = end_box.mapRectToScene(end_box.rect())
    assert start_rect.adjusted(-2, -2, 2, 2).contains(pts[0])
    assert end_rect.adjusted(-2, -2, 2, 2).contains(pts[-1])
    w.deleteLater()


def test_import_ai_image_inserts_result_and_registers_one_undo_step():
    """다이얼로그·진행창·워커 스레드를 전부 동기 mock으로 대체해 `_import_ai_image()`의
    배선(입력→백그라운드 실행→결과 삽입→undo 등록) 전체를 종단 검증한다."""
    w = CanvasWindow()
    existing = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 40)

    def fake_run(self):
        sk = Sketch(dark=True)
        a = sk.box(100, 100, 80, 40, "A")
        b = sk.box(300, 100, 80, 40, "B")
        sk.arrow(a, b, label="e")
        sk.save(self._out_path)
        self.finished_ok.emit({"shapes": 2, "edges": 1, "unknown": 0, "tiles": 0,
                               "overview_model": "mock", "path": self._out_path})

    dlg_instance = type("_D", (), {
        "exec": lambda self: QDialog.DialogCode.Accepted,
        "image_path": lambda self: "dummy.png",
        "note": lambda self: "",
        "overview_model": lambda self: "gemini-3.6-flash",
        "tile_model": lambda self: "gpt-5.4-mini",
        "cleanup_temp_image": lambda self: None,
        "is_manual_mode": lambda self: False,
    })()
    prog_instance = type("_P", (), {
        "exec": lambda self: None,
        "accept": lambda self: None,
        "reject": lambda self: None,
        "append": lambda self, msg: None,
    })()

    with patch.object(hai._AISketchWorker, "run", fake_run), \
         patch.object(hai._AISketchWorker, "start", lambda self: self.run()), \
         patch.object(hai, "_AIImageImportDialog", return_value=dlg_instance), \
         patch.object(hai, "_AISketchProgressDialog", return_value=prog_instance):
        w._import_ai_image()

    top_level = [it for it in w._scene.items() if it.parentItem() is None]
    assert existing in top_level
    assert len(top_level) == 4   # 기존 1 + 박스2 + 화살표1

    w.undo()
    top_level_after_undo = [it for it in w._scene.items() if it.parentItem() is None]
    assert top_level_after_undo == [existing]   # 삽입 전체가 undo 1스텝
    w.deleteLater()


def test_ai_image_import_dialog_ok_enabled_after_browse():
    # _populate_models()는 게이트웨이를 실호출한다 — 테스트는 네트워크 무의존이어야 하므로
    # 여기선 항상 mock(모델 목록 관련 별도 테스트는 아래 참조).
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    ok_btn = dlg._btns.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok_btn.isEnabled()
    with patch("easycad.canvas.host_dialogs.QFileDialog.getOpenFileName",
              return_value=("picked.png", "")):
        dlg._browse()
    assert ok_btn.isEnabled()
    assert dlg.image_path() == "picked.png"


def test_ai_image_import_dialog_populate_models_uses_live_list_and_marks_default():
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_models",
               return_value=["gemini-3.6-flash", "gpt-5.4-mini", "claude-sonnet-5"]):
        dlg = _AIImageImportDialog()
    assert dlg.overview_model() == "gemini-3.6-flash"
    assert dlg.tile_model() == "gpt-5.4-mini"
    idx = dlg._overview_combo.findData("gemini-3.6-flash")
    assert "추천" in dlg._overview_combo.itemText(idx)
    assert dlg._overview_combo.findData("claude-sonnet-5") >= 0   # 전체 목록이 그대로 노출됨


def test_ai_image_import_dialog_populate_models_falls_back_when_list_fails():
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_models", side_effect=RuntimeError("no network")):
        dlg = _AIImageImportDialog()
    assert dlg.overview_model() == "gemini-3.6-flash"
    assert dlg.tile_model() == "gpt-5.4-mini"


def test_ai_image_import_dialog_paste_from_clipboard_sets_path():
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    pm = _mk_pixmap(40, 20)
    fake_md = type("_MD", (), {"hasUrls": lambda self: False})()
    with patch.object(QApplication.clipboard(), "mimeData", return_value=fake_md), \
         patch("easycad.canvas.host_dialogs._clipboard_pixmap", return_value=pm):
        dlg._paste_from_clipboard()
    assert dlg.image_path()
    saved_path = dlg._temp_image_path
    assert saved_path is not None
    assert os.path.exists(saved_path)
    dlg.cleanup_temp_image()
    assert not os.path.exists(saved_path)


def test_ai_image_import_dialog_ctrl_v_works_when_path_edit_focused():
    """실사용 버그(2026-08-11): 드래그드롭은 되는데 Ctrl+V는 안 됨 — 포커스가 있는
    QLineEdit이 표준 붙여넣기 키를 자기 keyPressEvent에서 먼저 처리·accept()해버려
    다이얼로그 레벨 keyPressEvent가 이벤트를 못 받던 게 원인. eventFilter로 고침
    (path_edit·note_edit에 직접 설치 — 포커스 위젯 자신에게 걸어야 먼저 가로챈다)."""
    from PyQt6.QtGui import QKeyEvent
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    pm = _mk_pixmap(40, 20)
    fake_md = type("_MD", (), {"hasUrls": lambda self: False, "hasImage": lambda self: True})()
    with patch.object(QApplication.clipboard(), "mimeData", return_value=fake_md), \
         patch("easycad.canvas.host_dialogs._clipboard_pixmap", return_value=pm):
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        handled = dlg.eventFilter(dlg._path_edit, ev)
    assert handled is True
    assert dlg.image_path()


def test_ai_image_import_dialog_note_edit_ctrl_v_falls_through_for_plain_text():
    """note_edit는 진짜 텍스트 입력창이라, 클립보드에 이미지가 없으면(보통의 텍스트
    붙여넣기) 가로채지 않고 위젯 기본 동작에 맡겨야 한다."""
    from PyQt6.QtGui import QKeyEvent
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    fake_md = type("_MD", (), {"hasUrls": lambda self: False, "hasImage": lambda self: False})()
    with patch.object(QApplication.clipboard(), "mimeData", return_value=fake_md):
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        handled = dlg.eventFilter(dlg._note_edit, ev)
    assert handled is False
    assert dlg.image_path() == ""


def test_ai_image_import_dialog_sets_thumbnail_on_image_selected():
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    assert dlg._thumb_label.pixmap() is None or dlg._thumb_label.pixmap().isNull()
    real_path = os.path.join(_TMP, f"thumb_{uuid.uuid4().hex}.png")
    _mk_pixmap(80, 40).save(real_path)
    dlg._set_image_path(real_path)
    assert dlg._thumb_label.pixmap() is not None
    assert not dlg._thumb_label.pixmap().isNull()


def test_ai_image_import_dialog_drop_file_sets_path():
    from PyQt6.QtCore import QUrl
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    fake_url = QUrl.fromLocalFile(os.path.join(_TMP, "dropped.png"))
    fake_md = type("_MD", (), {
        "hasUrls": lambda self: True,
        "urls": lambda self: [fake_url],
        "hasImage": lambda self: False,
    })()
    fake_event = type("_E", (), {
        "mimeData": lambda self: fake_md,
        "acceptProposedAction": lambda self: None,
    })()
    dlg.dropEvent(fake_event)
    assert dlg.image_path().lower().endswith("dropped.png")


def test_progress_dialog_parses_tile_progress_and_updates_status():
    dlg = _AISketchProgressDialog()
    dlg.append("[P1 개괄] gemini-3.6-flash (10.0s) shapes=20 edges=10 unknown=2")
    assert dlg._progress.minimum() == 0 and dlg._progress.maximum() == 0   # 여전히 무한로딩
    dlg.append("[P2 타일 0/3] claude-sonnet-5 (5.0s) shapes=5 edges=3")
    assert dlg._progress.maximum() == 3
    assert dlg._progress.value() == 1
    dlg.append("[P2 타일 2/3] claude-sonnet-5 (5.0s) shapes=5 edges=3")
    assert dlg._progress.value() == 3
    assert "타일 2/3" in dlg._status_label.text()


# ── 수동 붙여넣기 모드(2026-08-11) ───────────────────────────────────────────

def test_manual_prompt_includes_json_format_instructions():
    text = ais.manual_prompt(360, 160, "테스트 도면")
    assert "360x160" in text
    assert "테스트 도면" in text
    assert '"shapes"' in text and '"edges"' in text and '"unknown"' in text


def test_build_from_manual_json_skips_gateway_and_builds_sketch():
    payload = json.dumps({
        "shapes": [{"id": "s1", "kind": "box", "x": 0.0, "y": 0.0, "w": 50.0, "h": 30.0, "label": "A"},
                   {"id": "s2", "kind": "decision", "x": 200.0, "y": 0.0, "w": 60.0, "h": 60.0, "label": "B"}],
        "edges": [{"from": "s1", "to": "s2", "label": "예"}],
        "unknown": [{"x": 400.0, "y": 0.0, "w": 30.0, "h": 30.0, "desc": "모름"}],
    })
    out = os.path.join(_TMP, f"manual_{uuid.uuid4().hex}.ecad")
    summary = ais.build_from_manual_json(payload, out)
    assert summary == {"shapes": 2, "edges": 1, "unknown": 1, "tiles": 0,
                       "overview_model": "manual", "path": out}
    with open(out, encoding="utf-8") as f:
        doc = json.load(f)
    assert len(doc["items"]) == 4   # box + symbol + sarrow + unknown placeholder box


def test_build_from_manual_json_raises_on_invalid_json():
    out = os.path.join(_TMP, f"manual_bad_{uuid.uuid4().hex}.ecad")
    try:
        ais.build_from_manual_json("이건 JSON이 아님", out)
        assert False, "should have raised"
    except Exception:
        pass
    assert not os.path.exists(out)


def test_ai_image_import_dialog_manual_toggle_swaps_visible_groups():
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    assert not dlg._auto_group.isHidden()
    assert dlg._manual_group.isHidden()
    dlg._manual_check.setChecked(True)
    assert dlg._auto_group.isHidden()
    assert not dlg._manual_group.isHidden()
    assert dlg.is_manual_mode()


def test_ai_image_import_dialog_manual_accept_rejects_empty_and_invalid_json():
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    dlg._manual_check.setChecked(True)
    dlg._set_image_path("dummy.png")

    with patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn:
        dlg._on_accept_clicked()   # 빈 JSON
    assert warn.called
    assert dlg.result() != QDialog.DialogCode.Accepted

    dlg._manual_json_edit.setPlainText("이건 JSON이 아님")
    with patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn:
        dlg._on_accept_clicked()   # 깨진 JSON
    assert warn.called
    assert dlg.result() != QDialog.DialogCode.Accepted

    dlg._manual_json_edit.setPlainText('{"shapes":[],"edges":[],"unknown":[]}')
    dlg._on_accept_clicked()
    assert dlg.result() == QDialog.DialogCode.Accepted


def test_ai_image_import_dialog_copy_manual_prompt_sets_clipboard():
    with patch.object(_AIImageImportDialog, "_populate_models", lambda self: None):
        dlg = _AIImageImportDialog()
    real_path = os.path.join(_TMP, f"copy_{uuid.uuid4().hex}.png")
    _mk_pixmap(120, 80).save(real_path)
    dlg._set_image_path(real_path)
    with patch("easycad.canvas.host_dialogs.QMessageBox.information"):
        dlg._copy_manual_prompt()
    clip_text = QApplication.clipboard().text()
    assert "120x80" in clip_text
    assert '"shapes"' in clip_text


def test_import_ai_manual_mode_inserts_without_worker_thread():
    """수동모드는 QThread를 아예 안 띄운다 — _AISketchWorker.start가 호출되지 않는지까지
    확인(호출됐다면 게이트웨이를 실제로 부르려 시도했다는 뜻이라 이 테스트의 핵심)."""
    w = CanvasWindow()
    existing = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 40)

    payload = json.dumps({
        "shapes": [{"id": "s1", "kind": "box", "x": 100.0, "y": 100.0, "w": 80.0, "h": 40.0, "label": "A"},
                   {"id": "s2", "kind": "box", "x": 300.0, "y": 100.0, "w": 80.0, "h": 40.0, "label": "B"}],
        "edges": [{"from": "s1", "to": "s2", "label": ""}],
        "unknown": [],
    })
    dlg_instance = type("_D", (), {
        "exec": lambda self: QDialog.DialogCode.Accepted,
        "image_path": lambda self: "dummy.png",
        "note": lambda self: "",
        "cleanup_temp_image": lambda self: None,
        "is_manual_mode": lambda self: True,
        "manual_json": lambda self: payload,
    })()

    with patch.object(hai._AISketchWorker, "start") as worker_start, \
         patch.object(hai, "_AIImageImportDialog", return_value=dlg_instance):
        w._import_ai_image()

    assert not worker_start.called
    top_level = [it for it in w._scene.items() if it.parentItem() is None]
    assert existing in top_level
    assert len(top_level) == 4   # 기존 1 + 박스2 + 화살표1

    w.undo()
    assert [it for it in w._scene.items() if it.parentItem() is None] == [existing]
    w.deleteLater()
