"""§8 항목66 4-1 움직이는 카드 그릇(2026-10-25) — 데스크톱 쪽: 웹 `web/src/next/livecard.js`와 같은 틀 글(CSP·크기 상한),
두 번 누르기로 브라우저에 여는 페이지(움직이는 카드 = sandbox 틀 안에서만 스크립트, 보통 문서 = 스크립트 끔), 저장하면 `live` 칸 그대로.
웹 화면(한 번 = 고르기·두 번 = 조작·인터넷/칠판 못 닿음)은 `web/e2e/flow34-live-card.spec.js`.
"""
import os
import re
import sys

from _shared import _app  # noqa: F401  (QApplication)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from easycad.canvas import core_web as W  # noqa: E402
from easycad.fileio.document import dict_to_item, item_to_dict  # noqa: E402

JS = open(os.path.join(ROOT, "web", "src", "next", "livecard.js"), encoding="utf-8").read()
CARD = '<!doctype html><html><head><title>카드</title><script>x()</script></head><body><input type="range"></body></html>'
DOC = {"type": "doc", "pos": [0, 0], "rect": [0, 0, 480, 360], "scale": 1, "rotation": 0, "z": 1, "origin": [0, 0], "locked": False,
       "group_id": None, "layer_id": None, "title": "가격 × 물량", "html": CARD, "model": "gpt-6.1-sol", "live": True}


def _js_const(name):
    return re.search(rf'export const {name} = "([^"]+)"', JS).group(1)


def test_same_frame_as_web():
    assert W.LIVE_CSP == _js_const("LIVE_CSP")
    assert W.STATIC_CSP == _js_const("STATIC_CSP")
    assert f"LIVE_MAX = {W.LIVE_MAX:_}" in JS
    assert W._KICK in JS


def test_big_page_live_runs_only_inside_sandbox():
    p = W.big_page(DOC)
    assert p.startswith(f'<!doctype html><meta http-equiv="Content-Security-Policy" content="{W.LIVE_CSP}">')
    m = re.search(r'<iframe sandbox="allow-scripts" csp="[^"]+" srcdoc="([^"]*)"></iframe>', p)
    assert m and "allow-same-origin" not in p
    assert "<script" not in p.replace(m.group(0), "")          # 틀 밖 페이지엔 스크립트 없음
    assert "&lt;script&gt;x()" in m.group(1)                  # 카드 글은 틀 안(이스케이프)
    assert m.group(1).count("&lt;!doctype") == 1              # 우리 doctype 하나


def test_big_page_static_and_too_big():
    plain = W.big_page({**DOC, "live": False})
    assert plain.startswith(f'<!doctype html><meta http-equiv="Content-Security-Policy" content="{W.STATIC_CSP}">')
    assert "script-src" not in W.STATIC_CSP                   # 끌어 놓은 HTML 파일 속 스크립트도 꺼짐
    big = {**DOC, "html": "a" * (W.LIVE_MAX + 1)}
    assert not W.live_fits(big) and W.big_page(big).startswith(f'<!doctype html><meta http-equiv="Content-Security-Policy" content="{W.STATIC_CSP}">')


def test_live_kept_on_save():
    it = dict_to_item(dict(DOC))
    assert isinstance(it, W._DocItem)
    assert item_to_dict(it).get("live") is True
