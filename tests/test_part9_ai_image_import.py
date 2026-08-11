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

from PyQt6.QtWidgets import QDialog, QDialogButtonBox

from _shared import *  # noqa: F401,F403

from easycad.ai import gateway as gw  # noqa: E402
from easycad.ai import sketch_pipeline as ais  # noqa: E402
from easycad.canvas import host_ai as hai  # noqa: E402
from easycad.canvas.host_dialogs import _AIImageImportDialog  # noqa: E402
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


def test_axis_snap_aligns_close_edges_but_not_far_ones():
    shapes = [
        {"x": 0.0, "y": 0.0, "w": 100.0, "h": 50.0},
        {"x": 3.0, "y": 200.0, "w": 100.0, "h": 50.0},   # x=3, 왼쪽 0과 tol(6) 이내 → 스냅
        {"x": 500.0, "y": 400.0, "w": 100.0, "h": 50.0},  # 멀리 있어 스냅 안 됨
    ]
    out = ais.axis_snap(shapes, tol=6.0)
    assert out[0]["x"] == out[1]["x"]  # 가까운 왼쪽 변끼리 합쳐짐
    assert out[2]["x"] == 500.0        # 먼 도형은 그대로


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
        summary = ais.build_from_image(img_path, out, tile_threshold=5, zoom=3, verbose=False)

    assert calls["n"] == 3  # P1 + 타일 2개
    assert summary["tiles"] == 2
    assert summary["shapes"] == 2
    assert summary["unknown"] == 1

    with open(out, encoding="utf-8") as f:
        doc = json.load(f)
    rects = [it for it in doc["items"] if it["type"] == "rect"]
    ellipses = [it for it in doc["items"] if it["type"] == "ellipse"]
    assert len(ellipses) == 1
    # 왼쪽 타일 shape: x=30/3+0=10, y=60/3+0=20, w=30, h=10
    left_shape = next(it for it in rects if abs(it["rect"][0] - 10.0) < 1e-6)
    assert left_shape["rect"] == [10.0, 20.0, 30.0, 10.0]
    # 오른쪽 타일 ellipse: x=60/3+200=220, y=90/3+0=30, w=20, h=20
    assert ellipses[0]["rect"] == [220.0, 30.0, 20.0, 20.0]
    # unknown(오른쪽 타일): x=300/3+200=300, y=300/3+0=100, w=10, h=10
    unk = next(it for it in rects if it["label"]["text"].startswith("[미확인]"))
    assert unk["rect"] == [300.0, 100.0, 10.0, 10.0]

    # 실제 앱 문서 로더로도 정상 로드되는지 확인(회귀 방지 — 스키마 드리프트는 즉시 실패).
    w = CanvasWindow()
    n_loaded = load_document(w._scene, str(out))
    assert n_loaded == len(doc["items"])
    w.deleteLater()


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
    with patch("easycad.ai.sketch_pipeline.build_from_image", return_value=fake_summary):
        worker.run()

    assert recorded.get("ok") == fake_summary
    assert "err" not in recorded


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
    dlg = _AIImageImportDialog()
    ok_btn = dlg._btns.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok_btn.isEnabled()
    with patch("easycad.canvas.host_dialogs.QFileDialog.getOpenFileName",
              return_value=("picked.png", "")):
        dlg._browse()
    assert ok_btn.isEnabled()
    assert dlg.image_path() == "picked.png"
