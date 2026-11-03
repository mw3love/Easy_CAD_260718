"""웹 칠판 🔷 도형 그리기(2026-11-03) — 말 → 설계서(`text_to_flow`) → 서버가 데스크톱 배치 규칙으로 자리(`board_diagram.place`) → 칠판이 지음.

AI는 가짜(설계서 글 고정). 칠판 짓기는 `web/e2e/flow58`·`web/test/flowboard.test.mjs`.
"""
import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from easycad.ai import board_diagram, board_image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web"))   # 서버(web/server.py)

SPEC = {"title": "송신소 계통도", "direction": "LR", "lanes": ["방송국", "송신소"],
        "steps": [{"id": "s1", "text": "주조정실", "lane": "방송국"}, {"id": "s2", "text": "STL 송신 (마이크로웨이브 링크)", "lane": "방송국"},
                  {"id": "s3", "text": "신호 정상?", "lane": "송신소", "kind": "decision"}, {"id": "s4", "text": "송신기", "lane": "송신소"},
                  {"id": "s5", "text": "예비 송신기", "lane": "송신소"}, {"id": "s6", "text": "안테나", "lane": "송신소"}],
        "links": [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}, {"from": "s3", "to": "s4", "text": "예"},
                  {"from": "s3", "to": "s5", "text": "아니오"}, {"from": "s4", "to": "s6"}, {"from": "s5", "to": "s6"}],
        "focus": "s4"}


def _overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def test_place_boxes_fit_and_do_not_overlap():
    pl = board_diagram.place(json.dumps(SPEC, ensure_ascii=False))
    boxes = [s["box"] for s in pl["steps"]]
    assert len(boxes) == 6 and len(pl["links"]) == 6 and pl["title"] == "송신소 계통도" and pl["focus"] == "s4"
    assert all(not _overlap(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:])
    assert all(x >= 0 and y >= 0 and x + w <= pl["width"] + 0.5 and y + h <= pl["height"] + 0.5 for x, y, w, h in boxes)
    assert [l["key"] for l in pl["lanes"]] == ["방송국", "송신소"]
    by = {s["id"]: s for s in pl["steps"]}
    assert "\n" in by["s2"]["text"]                                   # 긴 글은 두 줄로(데스크톱 `_mermaid_wrap`)
    assert by["s3"]["box"][3] > by["s1"]["box"][3]                    # 마름모는 키가 크게(가운데 줄에서만 넓음)
    assert pl["ranks"]["s4"] == pl["ranks"]["s5"] == pl["ranks"]["s3"] + 1


def test_label_arrow_gets_room():
    """옆 칸으로 곧게 가는 라벨 화살표는 칸 간격이 라벨 + 양옆 선만큼(2026-11-03 사용자 — 「예비 전원」 라벨이 72 간격을 다 덮어 화살촉만 보였음)."""
    spec = {"title": "전원", "direction": "LR", "lanes": ["송신기실"],
            "steps": [{"id": "a", "text": "발전기 예비 전원", "lane": "송신기실"}, {"id": "b", "text": "수배전·UPS 전원", "lane": "송신기실"},
                      {"id": "c", "text": "송신기", "lane": "송신기실"}],
            "links": [{"from": "a", "to": "b", "text": "예비 전원"}, {"from": "b", "to": "c"}]}
    pl = board_diagram.place(json.dumps(spec, ensure_ascii=False))
    box = {s["id"]: s["box"] for s in pl["steps"]}
    gap_ab = box["b"][0] - (box["a"][0] + box["a"][2])
    gap_bc = box["c"][0] - (box["b"][0] + box["b"][2])
    assert gap_ab >= board_diagram.text_w("예비 전원", board_diagram.LABEL_PT) + board_diagram.LABEL_ROOM - 0.5
    assert abs(gap_bc - board_diagram.GAP_MAJOR) < 0.5                # 라벨 없는 칸은 그대로
    spec["direction"] = "TD"                                         # 세로 흐름은 라벨 높이가 간격 안에 들어가 그대로
    assert board_diagram.label_gaps(board_diagram.parse_spec(json.dumps(spec, ensure_ascii=False))) != {}   # 계산은 하지만
    pl2 = board_diagram.place(json.dumps(spec, ensure_ascii=False))
    b2 = {s["id"]: s["box"] for s in pl2["steps"]}
    assert abs(b2["b"][1] - (b2["a"][1] + b2["a"][3]) - board_diagram.GAP_MAJOR) < 0.5   # 배치엔 안 씀


def test_hierarchy_prompt_forbids_start_end():
    from easycad.ai.text_to_flow import build_prompt
    assert "조직도·마인드맵" in build_prompt("KBS 조직도 그려 줘")   # 0단계 실측: 모든 모델이 조직도 잎에 「끝」 모양을 씀


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    monkeypatch.setattr(srv.gw, "get_credit_balance", lambda *a, **k: (100.0, 1000.0))
    calls = []

    def fake_flow(key, ask, *, model, base_url="", base_code="", **_):
        calls.append((ask, base_code, model))
        spec = dict(SPEC)
        if base_code:
            spec = {**SPEC, "steps": SPEC["steps"] + [{"id": "s7", "text": "전원 장치", "lane": "송신소"}], "links": SPEC["links"] + [{"from": "s7", "to": "s4"}]}
        return json.dumps(spec, ensure_ascii=False), model
    monkeypatch.setattr(board_diagram, "generate_flow", fake_flow)
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", calls
    httpd.shutdown()


def _post(base, **body):
    req = urllib.request.Request(base + "/api/chat", data=json.dumps({"board": "도형", **body}).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_server_draws_without_asking_then_fixes(server):
    base, calls = server
    out = _post(base, messages=[{"role": "user", "content": "송신소 계통도 그려 줘"}])
    assert out["kind"] == "diagram" and out["fixed"] is False and out["model"] == board_diagram.DIAGRAM_MODEL
    assert len(out["place"]["steps"]) == 6 and json.loads(out["spec"])["title"] == "송신소 계통도"
    assert calls[-1] == ("송신소 계통도 그려 줘", "", board_diagram.DIAGRAM_MODEL)
    # 앞 도형을 두고 고치는 말 = 그 설계서 고치기(이름표 없이도)
    fix = _post(base, base_flow=out["spec"], messages=[{"role": "user", "content": "전원 장치 추가해 줘"}])
    assert fix["kind"] == "diagram" and fix["fixed"] is True and len(fix["place"]["steps"]) == 7 and calls[-1][1] == out["spec"]
    # 새 도형을 그리라는 말이면 앞 도형이 있어도 새로
    new = _post(base, base_flow=out["spec"], messages=[{"role": "user", "content": "KBS 조직도 그려 줘"}])
    assert new["fixed"] is False and calls[-1][1] == ""
    # 바로 앞 답이 그림이어도 「계통도 그려 줘」 = 도형(실검증 — 그림 이어 고치기로 잡혀 이미지가 나왔음)
    after_pic = _post(base, messages=[{"role": "user", "content": "송신탑 그려 줘"}, {"role": "assistant", "content": "송신탑 " + board_image.IMAGE_MARK + " 2장"},
                                      {"role": "user", "content": "송신소 계통도 그려 줘"}])
    assert after_pic["kind"] == "diagram"
    # 「+ › 🔷 도형 그리기」 이름표 + 모델 설정(terra 등)
    pick = _post(base, kind="diagram", models={"diagram": "gpt-6.1-terra"}, messages=[{"role": "user", "content": "출근 준비"}])
    assert pick["kind"] == "diagram" and calls[-1][2] == "gpt-6.1-terra"
