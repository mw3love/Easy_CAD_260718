"""§8 항목61(2026-10-17) — 웹 칠판이 내보낸 .ecad를 데스크톱이 그대로 연다.

`fixtures/web_export_board.ecad` = 보드 샘플(`web/public/samples/paper_board.ecad`)을 웹 칠판에서 열고 「.ecad 저장」한 것
(web/src/ecadExport.js). 웹 쪽 형식이 바뀌어 데스크톱이 못 읽게 되면 여기서 잡는다.
"""
import json
import os

from _shared import *  # noqa: F401,F403

from easycad.fileio.document import load_document
from test_part41_paper_board import _close, _window

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "fixtures", "web_export_board.ecad")
ORIG = os.path.join(os.path.dirname(HERE), "web", "public", "samples", "paper_board.ecad")


def test_web_export_opens_with_same_items_and_board_marks():
    w = _window()
    sc = w._scene if hasattr(w, "_scene") else w.scene
    n_orig = load_document(sc, ORIG)
    n_web = load_document(sc, WEB)
    assert n_web == n_orig == 60
    tops = [it for it in sc.items() if it.parentItem() is None]
    # 보드 칸 표시(데스크톱 보드 막대의 「선택 N개」·칸 안으로 들어가기가 쓰는 것)가 웹을 거쳐도 남는다
    assert sum(1 for it in tops if getattr(it, "_pb_part", None)) == 59
    assert sum(1 for it in tops if getattr(it, "_pb_card", False)) == 17
    # 흐름도 화살표 두 개가 양 끝 상자에 붙어 있다
    arrows = [it for it in tops if type(it).__name__ == "_PolyArrowItem"]
    assert len(arrows) == 2 and all(a._bound(0) is not None and a._bound(len(a._pts) - 1) is not None for a in arrows)
    # 부분 강조(runs)와 보드 글꼴이 남는다
    texts = {it.toPlainText(): it for it in tops if hasattr(it, "text_runs")}
    head = next(t for k, t in texts.items() if k.startswith("앞 단어를"))
    assert head.text_runs() and head.font().family() == "Pretendard" and head.font().weight() == 800
    _close(w)


def test_web_export_is_plain_ecad_json():
    with open(WEB, encoding="utf-8") as f:
        doc = json.load(f)
    assert doc["format"] == "easycad-doc" and doc["version"] == 1
    assert {i["type"] for i in doc["items"]} <= {"board", "text", "rect", "ellipse", "symbol", "polygon", "path", "line", "sarrow", "arrow", "image"}
