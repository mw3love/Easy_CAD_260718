"""§8 항목47(2026-10-16) — 「설명 페이지 만들기(KAIROS)」: 도면 상자·연결 → 단계별 설명 → HTML 공유 페이지 오른쪽 설명 칸.

브라우저에서 단계 넘기기·상자 강조는 실제 Chrome으로 확인(history) — 여기선 지시문·답 읽기·상자/연결 모으기·페이지에 들어가는지.
"""
import json
import re
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

import pytest

from easycad.ai import drawing_explain as de
from easycad.ai.gateway import GatewayResult


def test_prompt_lists_boxes_and_links():
    p = de.build_steps_prompt("송출", [(0, "카메라"), (1, "스위처")], [(0, 1, "SDI")], note="신입용")
    assert "0: 카메라" in p and "0 → 1 : SDI" in p and "신입용" in p and '"boxes"' in p
    assert "글에는 쓰지 말 것" in p, "실측: 설명 글에 '인코더(3)'처럼 내부 번호가 샜다"


def test_parse_steps_cleans_numbers_bad_ids_and_fences():
    raw = """설명입니다
```json
{"title": "안내", "summary": "요약", "steps": [
  {"title": "1. 1. 수집", "body": "카메라가 찍어요", "boxes": [0, 7, "1", 1]},
  {"title": "2단계: 제어", "body": "", "boxes": []},
  {"title": "", "body": "", "boxes": [0]}
]}
```"""
    g = de.parse_steps(raw, n_boxes=2)
    assert g["title"] == "안내" and len(g["steps"]) == 2, "빈 단계는 버림"
    assert g["steps"][0] == {"title": "수집", "body": "카메라가 찍어요", "boxes": [0, 1]}, "없는 번호·중복은 버림"
    assert g["steps"][1]["title"] == "제어"


def test_parse_steps_rejects_non_json():
    with pytest.raises(ValueError):
        de.parse_steps("죄송해요, 못 하겠어요", 3)


def _window_with_flow():
    w = CanvasWindow()
    w._build_mermaid("flowchart LR\n A[카메라] --> B[스위처]\n B -->|SDI| C[주조정실]")
    return w


def test_boxes_in_reading_order_and_links_by_index():
    w = _window_with_flow()
    boxes = w._share_boxes()
    assert [t for _it, t in boxes] == ["카메라", "스위처", "주조정실"]
    assert sorted(w._share_links(boxes)) == [(0, 1, ""), (1, 2, "SDI")]


def test_explain_page_end_to_end_with_fake_kairos(tmp_path):
    w = _window_with_flow()
    reply = json.dumps({"title": "송출 안내", "summary": "카메라에서 주조정실까지",
                        "steps": [{"title": "찍기", "body": "카메라", "boxes": [0]},
                                  {"title": "보내기", "body": "SDI로", "boxes": [1, 2]}]}, ensure_ascii=False)
    path = str(tmp_path / "guide.html")
    with _patch("easycad.ai.gateway.call_text_with_fallback", return_value=GatewayResult(reply, "m", None, 0.1)):
        worker = w._start_explain_page("k", path, "송출 흐름", w._share_boxes(), open_after=False)
        assert worker.wait(5000)
        _app.processEvents()
    text = open(path, encoding="utf-8").read()
    assert "<title>송출 흐름</title>" in text, "만들 때 정한 제목(탭 이름 아님)"
    guide = json.loads(re.search(r"var GUIDE = (\{.*?\});\n", text, re.S).group(1))
    assert [s["boxes"] for s in guide["steps"]] == [[0], [1, 2]]
    shapes = json.loads(re.search(r"var SHAPES = (\[.*?\]);", text, re.S).group(1))
    assert [s["text"] for s in shapes] == ["카메라", "스위처", "주조정실"], "설명의 상자 번호와 같은 순서"


def test_no_text_boxes_or_no_key():
    w = CanvasWindow()
    assert w._make_explain_page() is None and "상자가 없어요" in w._toast.currentMessage()
    w = _window_with_flow()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value=""):
        assert w._make_explain_page() is None   # 키 창(모달 아님)만 띄움


def test_failure_message_and_menu():
    w = _window_with_flow()
    with _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=RuntimeError("503 busy")):
        worker = w._start_explain_page("k", "unused.html", "t", w._share_boxes(), open_after=False)
        assert worker.wait(5000)
        _app.processEvents()
    assert "만들지 못했어요" in w._toast.currentMessage() and "503" in w._toast.currentMessage()
    assert w._act_explain_page.text() == "설명 페이지 만들기(KAIROS)…"


def test_guide_json_cannot_break_script():
    from easycad.fileio.html_share import build_html
    doc = build_html("t", 10, 10, [("기본", "<g/>", True)], [{"x": 0, "y": 0, "w": 1, "h": 1, "text": "</script><b>"}],
                     guide={"title": "</script>", "summary": "", "steps": []})
    assert doc.count("</script>") == 1, "글자 속 </script>는 <\\/script>로"
