"""§8 항목61 ④-1(2026-10-19) — 웹 ↔ 데스크톱 왕복: 웹이 실제로 만든 문서(`tests/fixtures/web_made.ecad` — 화면 시험이 남긴 칠판을
`tools/collect_web_fixture.py`로 모음)를 데스크톱으로 열었다 저장해도 칸 하나 안 잃는다. 반대쪽(데스크톱 문서 → 웹)은 `web/test/roundtrip.test.mjs`.

전엔 데스크톱이 웹 종류마다 지킬 칸을 하나하나 적어 둬서 웹에 새 칸이 생길 때마다 잃었다(메모 `fold`, 2026-10-19 실측) → 웹 종류는 원래 칸 통째(`_web_raw`).
"""
import base64
import json
import os
import sys

from _shared import _app  # noqa: F401  (QApplication)
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QGraphicsScene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from easycad.fileio import document as D  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "web_made.ecad")
LEGEND = {"type": "legend", "uid": "lg1", "pos": [0, 900], "rect": [0, 0, 220, 80], "rows": [{"key": "ff2563eb|1|2", "color": "#ff2563eb", "style": 1, "width": 2}],
          "names": {"ff2563eb|1|2": "광케이블"}, "title": "범례", "scale": 1, "rotation": 0, "z": 3, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None}

DOC = {"type": "doc", "uid": "dc1", "pos": [500, 900], "rect": [0, 0, 397, 601], "title": "회의 브리핑", "html": "<!doctype html><html><head><title>회의 브리핑</title></head><body><h1>송신기</h1></body></html>",
       "model": "claude-opus-5-5", "chat_at": 1792390000000, "scale": 1, "rotation": 0, "z": 4, "origin": [0, 0], "locked": False, "group_id": None, "layer_id": None}   # 정리 문서 카드(「정리해 줘」 ①)
PDF = {"type": "pdf", "uid": "pf1", "pos": [1000, 900], "rect": [0, 0, 420, 600], "url": "/api/pdf/main/1792390000000_abcdef", "name": "보고서.pdf", "pages": 2,
       "sizes": [[595, 842], [842, 595]], "thumb": "data:image/jpeg;base64,AAAA", "text": "[1쪽] 송신기", "scale": 0.5, "rotation": 0, "z": 5, "origin": [0, 0], "locked": False,
       "group_id": None, "layer_id": None}   # PDF 보기 카드(2026-10-21 — 원본은 웹 서버, 칠판엔 주소)


def _close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-6
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    return a == b


def _pixels(b64):
    im = QImage.fromData(base64.b64decode(b64)).convertToFormat(QImage.Format.Format_ARGB32)
    return im.width(), im.height(), bytes(im.constBits().asstring(im.sizeInBytes()))


def _by_uid(items):
    uids = [it.get("uid") for it in items]
    out = {}
    for it in items:
        it = dict(it)
        for k in ("bind1", "bind2"):   # 순번 → 붙은 도형 이름표(저장 차례가 바뀌어도 비교되게)
            if isinstance(it.get(k), int):
                it[k] = "uid:" + str(uids[it[k]])
        out[it.get("uid")] = it
    return out


def test_web_made_document_survives_desktop_open_save(tmp_path):
    with open(FIX, encoding="utf-8") as f:
        doc = json.load(f)
    doc["items"] += [LEGEND, DOC, PDF]
    kinds = {it["type"] for it in doc["items"]}
    assert {"memo", "web", "frame", "legend", "doc", "pdf", "sarrow", "image", "text", "table", "rect"} <= kinds   # 재료가 모든 웹 종류를 덮는지
    assert any(it.get("fold") is True for it in doc["items"])                                      # 회의록 전문(접기)
    src, out = tmp_path / "a.ecad", tmp_path / "b.ecad"
    src.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    sc = QGraphicsScene()
    D.load_document(sc, str(src))
    D.save_document(sc, str(out), doc.get("layers"))
    back = json.loads(out.read_text(encoding="utf-8"))
    A, B = _by_uid(doc["items"]), _by_uid(back["items"])
    assert set(A) == set(B)
    bad = []
    for u, a in A.items():
        b = B[u]
        for k, v in a.items():
            if k == "data" and a["type"] == "image":   # 데스크톱은 PNG를 다시 만듦 — 픽셀이 같으면 됨
                if _pixels(v) != _pixels(b["data"]):
                    bad.append((a["type"], u, k, "픽셀 다름"))
            elif not _close(v, b.get(k, "<없음>")):
                bad.append((a["type"], u, k, v, b.get(k, "<없음>")))
        if a["type"] in D._WEB_TYPES:
            bad += [(a["type"], u, "+" + k, b[k]) for k in b if k not in a]   # 데스크톱 대리 그림용 칸(테두리 등)이 웹 종류에 붙지 않음
    assert bad == []
