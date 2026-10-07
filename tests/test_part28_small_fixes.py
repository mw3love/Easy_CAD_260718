"""2026-10-03 작은 문제 묶음 — ① 앱 설정 격리(테스트가 실사용자 설정을 못 건드리게)
② 파일을 연 직후 레이어 패널 개수."""
import os
import re

from _shared import *  # noqa: F401,F403

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_app_settings_uses_isolated_store_under_tests():
    from easycad.app_settings import app_settings, settings_org
    assert settings_org() == "EasyCAD-pytest"
    assert app_settings().organizationName() == "EasyCAD-pytest"


def test_no_hardcoded_real_settings_store():
    # 실사용자 저장소("EasyCAD")를 직접 여는 코드가 다시 생기면 테스트가 실제 설정을 바꾼다
    # (최근 색 삭제·"DXF 안내 봤음" 표시 — 2026-10-03 발견, 2026-08-20 AI 키 소실과 같은 종류).
    pat = re.compile(r'QSettings\(\s*"EasyCAD"')
    bad = []
    for base in ("easycad", "tests"):
        for dirpath, _dirs, files in os.walk(os.path.join(_ROOT, base)):
            for f in files:
                if f.endswith(".py"):
                    p = os.path.join(dirpath, f)
                    with open(p, encoding="utf-8") as fh:
                        for i, line in enumerate(fh, 1):
                            code = line.split("#", 1)[0]
                            if pat.search(code) and "`" not in line and p != __file__:
                                bad.append(f"{os.path.relpath(p, _ROOT)}:{i}")
    assert bad == [], bad


def _layer_labels(w):
    lst = w._layers_list
    # [2026-10-07] 개수는 이름과 따로(시안 L2) — 예전 「이름 (개수)」 모양으로 합쳐 비교한다.
    return [f"{r._layer_name_lbl.text()} ({r._layer_count_lbl.text()})"
            for r in (lst.itemWidget(lst.item(i)) for i in range(lst.count()))]


def _wait(ms=400):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        _app.processEvents()


def test_layer_count_right_after_opening_dxf():
    # 고치기 전: DXF·PDF를 연 직후 「기본 (0)」(개수는 기록이 쌓일 때만 다시 셌다).
    import uuid
    from unittest.mock import patch
    from PyQt6.QtWidgets import QMessageBox
    src = CanvasWindow()   # 다른 창에서 만든 DXF — 같은 창이면 「이미 연 문서」로 보고 탭만 옮긴다
    for i in range(3):
        _mk_pen_rect(src, x=i * 150)
    d = os.path.join(_TMP, f"lc_{uuid.uuid4().hex}"); os.makedirs(d)
    dx = os.path.join(d, "three.dxf")
    src._do_export_dxf(dx)
    src._active_doc.dirty = False
    w = CanvasWindow()
    with patch.object(QMessageBox, "information", return_value=QMessageBox.StandardButton.Ok):
        w._open_path(dx)
    _wait()
    assert _layer_labels(w) == ["기본 (3)"]
    for doc in getattr(w, "_docs", []):
        doc.dirty = False
    w.close()


def _brute_fill_match(rect, candidates, used):
    """고치기 전 `_match_fill_target` 그대로(후보 전체를 매번 훑음) — 결과 동일성 기준."""
    from easycad.canvas.annotator_core import _TextItem
    best, best_score = None, None
    base_tol = max(3.0, 0.05 * max(rect.width(), rect.height()))
    for c in candidates:
        if id(c) in used:
            continue
        pen_w = c.pen().widthF() if hasattr(c, "pen") else 0.0
        tol = base_tol + 4.0 * pen_w
        cr = getattr(c, "_content_rect", None)
        r = c.mapRectToScene(cr()) if cr is not None else c.sceneBoundingRect()
        if isinstance(c, _TextItem):
            r = r.adjusted(1, 1, -1, -1)
        score = ((r.center() - rect.center()).manhattanLength()
                 + abs(r.width() - rect.width()) + abs(r.height() - rect.height()))
        if score <= tol and (best_score is None or score < best_score):
            best, best_score = c, score
    return best


def test_fill_matcher_same_result_as_brute_force():
    # 2026-10-03 DXF 채우기 짝짓기를 격자 색인으로 바꿈(9천 개 DXF 343초) — 고르는 결과는 예전과 같아야.
    import random
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPen, QColor
    from easycad.fileio.dxf_import import _FillMatcher
    rnd = random.Random(7)
    w = CanvasWindow()
    cands = []
    for i in range(400):
        x, y = rnd.uniform(0, 3000), rnd.uniform(0, 3000)
        it = _RectItem(QRectF(0, 0, rnd.choice([20, 40, 41, 200]), rnd.choice([10, 30, 31, 150])))
        it.setPen(QPen(QColor("#000"), rnd.choice([0.0, 1.0, 3.0, 8.0])))
        it.setPos(round(x / 50) * 50, round(y / 50) * 50)   # 겹치는 자리·크기 섞어 동점 상황도 만듦
        w._scene.addItem(it)
        cands.append(it)
    matcher = _FillMatcher(cands)
    used_a, used_b = set(), set()
    hits = 0
    for _ in range(600):
        c = rnd.choice(cands)
        r = c.mapRectToScene(c._content_rect())
        q = r.adjusted(rnd.uniform(-6, 6), rnd.uniform(-6, 6), rnd.uniform(-6, 6), rnd.uniform(-6, 6))
        if rnd.random() < 0.2:
            q = QRectF(rnd.uniform(0, 3000), rnd.uniform(0, 3000), 50, 50)   # 짝 없는 해치
        a = _brute_fill_match(q, cands, used_a)
        b = matcher.match(q, used_b)
        assert a is b
        if a is not None:
            used_a.add(id(a)); used_b.add(id(b)); hits += 1
    assert hits > 100
