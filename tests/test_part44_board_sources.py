"""§8 항목53 4단계(나) 여러 자료(2026-10-16) — 가운데 칸에 파일을 여럿 넣으면 A·B·C 이름표, 한 장 보드로.
PDF는 글([A p.N]), 그림은 그림(여러 장 한 번에), 근거는 「A p.3」, 보드 머리에 자료 목록, 그림 칸은 고른 자료에서.
"""
import json
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

import fitz
import pytest
from PyQt6.QtGui import QColor, QImage

from easycad.ai import gateway as gw
from easycad.ai import pdf_to_board as pb
from easycad.ai.gateway import GatewayResult
from easycad.canvas.annotator_core import _BoardItem, _ImageItem


def _pdf(path, text):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()
    return str(path)


def _png(path, color="#3366cc"):
    img = QImage(120, 80, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    img.save(str(path))
    return str(path)


@pytest.fixture
def files(tmp_path):
    return _pdf(tmp_path / "a.pdf", "Paper A text"), _pdf(tmp_path / "b.pdf", "Paper B text"), _png(tmp_path / "c.png")


SPEC = {"kind": "paper-board", "title": "두 논문", "one_line": "A와 B 비교.",
        "three_lines": [{"text": "A는 빠르다", "pages": "A p.1"}, {"text": "B는 크다", "pages": "B p.1"}],
        "figure": {"caption": "그림", "source": "C", "page": 1}}


def test_start_prompt_collects_sources(files):
    w = CanvasWindow()
    sp = w._start_prompt
    a, b, c = files
    sp.attach_path(a)
    assert sp.kind() == "explain" and sp._sources == []          # 하나면 예전대로
    sp.attach_path(b)
    sp.attach_path(c)
    assert [(s["label"], s["kind"]) for s in sp._sources] == [("A", "pdf"), ("B", "pdf"), ("C", "image")]
    assert sp._sources[2]["path"] == c and sp._image_name_label.text() == "자료 3개 A·B·C"
    seen = []
    sp.submitted.connect(lambda *a: seen.append(a))
    with _patch("easycad.ai.gateway.resolve_api_key", return_value=""):   # 키 없음 — 생성은 안 함
        assert sp.submit() == "explain"
    kind, _text, srcs, name = seen[0]
    assert kind == "explain" and len(srcs) == 3 and name == "자료 3개" and sp._sources == []
    sp._clear_image()


def test_photo_then_photo_also_becomes_sources(tmp_path):
    w = CanvasWindow()
    sp = w._start_prompt
    sp.attach_path(_png(tmp_path / "1.png"))
    assert sp.kind() != "explain"
    sp.attach_path(_png(tmp_path / "2.png", "#cc3333"))
    assert sp.kind() == "explain" and [s["label"] for s in sp._sources] == ["A", "B"]
    sp._clear_image()
    assert sp._sources == [] and not sp._image_chip.isVisibleTo(sp)


def test_sources_limit(tmp_path):
    w = CanvasWindow()
    sp = w._start_prompt
    for i in range(pb.MAX_SOURCES + 2):
        sp.attach_path(_png(tmp_path / f"{i}.png"))
    assert len(sp._sources) == pb.MAX_SOURCES


def test_generate_board_sources_sends_labels_and_images(files):
    a, b, c = files
    from PIL import Image
    srcs = [{"label": "A", "kind": "pdf", "name": "a.pdf", "path": a},
            {"label": "B", "kind": "pdf", "name": "b.pdf", "path": b},
            {"label": "C", "kind": "image", "name": "c.png", "path": c, "image": Image.open(c)}]
    seen = []

    def fake(_k, prompt, **kw):
        seen.append((prompt, kw))
        return GatewayResult(json.dumps(SPEC, ensure_ascii=False), "m", None, 0.1)
    with _patch("easycad.ai.gateway.call_text_with_fallback", side_effect=fake):
        text, _used = pb.generate_board_sources("k", srcs, "비교", model="m")
    prompt, kw = seen[0]
    assert "[A p.1] Paper A text" in prompt and "[B p.1] Paper B text" in prompt
    assert "C = c.png(그림으로 첨부)" in prompt and '"A p.3"' in prompt
    assert [lbl for lbl, _img in kw["images"]] == ["C"]
    spec = pb.parse_board(text)
    assert spec["_sources"]["A"]["path"] == a and spec["figure"]["source"] == "C"
    assert a not in pb.build_refine_prompt("더 쉽게", text)   # 파일 경로는 AI에 안 보냄


def test_gateway_sends_several_images():
    from PIL import Image
    calls = []

    class _C:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    calls.append(kw)

                    class R:
                        choices = [type("x", (), {"message": type("m", (), {"content": "ok"})()})()]
                    return R()
    imgs = [("A", Image.new("RGB", (4, 4))), ("B", Image.new("RGB", (4, 4)))]
    gw.call_text(_C, "m", "질문", images=imgs)
    content = calls[0]["messages"][0]["content"]
    assert [p["type"] for p in content] == ["text", "image_url", "text", "image_url", "text"]
    assert content[0]["text"].startswith("자료 A") and content[-1]["text"] == "질문"


def test_board_shows_sources_and_figure_from_source(files):
    a, b, c = files
    spec = dict(SPEC, _sources={"A": {"name": "a.pdf", "kind": "pdf", "path": a},
                                "B": {"name": "b.pdf", "kind": "pdf", "path": b},
                                "C": {"name": "c.png", "kind": "image", "path": c}})
    w = CanvasWindow()
    w.resize(1600, 950)
    w.show()
    _n, _a, _k, added = w._build_flow_items(json.dumps(spec, ensure_ascii=False))
    texts = [it.toPlainText() for it in added if hasattr(it, "toPlainText")]
    assert any("자료 A a.pdf · B b.pdf · C c.png" in t for t in texts)
    assert any(t == "C p.1" for t in texts)
    imgs = [it for it in added if isinstance(it, _ImageItem)]
    assert len(imgs) == 1 and imgs[0]._pixmap.width() == 120     # C 그림 파일을 그대로
    for d in w._docs:
        d.dirty = False


def _wait_until(cond, ms=5000):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        _app.processEvents()
        if cond():
            return True
    return False


def test_sources_request_stages_board(files):
    a, b, c = files
    w = CanvasWindow()
    w.resize(1600, 950)
    w.show()
    srcs = [{"label": "A", "kind": "pdf", "name": "a.pdf", "path": a},
            {"label": "B", "kind": "pdf", "name": "b.pdf", "path": b}]
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.pdf_to_board.generate_board_sources",
                   return_value=(json.dumps(SPEC, ensure_ascii=False), "m")) as gen:
        req = w._ai_ctrl.request_make("비교", kind="explain", sources=srcs)
        assert req.kind == "explain" and req.sources == srcs
        assert _wait_until(lambda: w._board_selected() is not None)
    assert gen.call_args.args[1] == srcs and isinstance(w._board_selected(), _BoardItem)
    again = w._ai_ctrl.resubmit(req)
    assert again.sources == srcs
    w._ai_detach_jobs()
    for d in w._docs:
        d.dirty = False
