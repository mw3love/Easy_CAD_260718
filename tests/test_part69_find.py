"""데스크톱 칠판 찾기(Ctrl+F) = 웹 find.jsx(2026-10-22 사용자: 뜻으로 찾기까지).

치면 바로 낱말로, 0.4초 쉬면 KAIROS 임베딩으로 뜻이 가까운 것(`ai/board_find.find` — 웹 서버와 같은 계산). 노란 점선 · ↑↓ Enter = 그 도형으로 · Esc 닫기.
여기선 KAIROS 대신 가짜 임베딩(낱말 → 정해 둔 방향) — 진짜 호출은 손으로 한 번 확인.
"""
import copy
import os
from types import SimpleNamespace

from _shared import _app  # noqa: F401  (QApplication)
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from test_part66_desktop_web_kinds import DOCS, _win_with
from test_part68_type_to_write import RECT

# 뜻 방향: 밥·점심 = 축 0, 프린터·인쇄 = 축 1, 그 밖 = 축 2
_AXES = (("밥", "점심", "식당"), ("인쇄", "프린터", "토너"))


def _vec(text):
    for i, words in enumerate(_AXES):
        if any(w in text for w in words):
            return [1.0 if j == i else 0.0 for j in range(3)]
    return [0.0, 0.0, 1.0]


class _FakeClient:
    def __init__(self):
        self.calls = 0
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model, input):
        self.calls += 1
        return SimpleNamespace(data=[SimpleNamespace(embedding=_vec(t)) for t in input])


def _board():
    memo = {**copy.deepcopy(DOCS["memo"]), "lines": [{"k": "h2", "t": "점심 후보"}, {"k": "ul", "t": "김치찌개"}]}
    box, box2 = {**RECT, "pos": [600, 0]}, {**RECT, "pos": [600, 400]}
    w, (m, b, b2) = _win_with(memo, box, box2)
    for it, t in ((b, "프린터 토너 교체"), (b2, "회의실 예약")):   # 상자 라벨은 문서 열기가 붙임(dict_to_item 하나로는 안 붙음) — 직접
        it.ensure_label().setPlainText(t)
    return w, (m, b, b2)


def _wait_sem(bar):
    bar._timer.stop()
    bar._ask_sem()
    for wk in list(bar._workers):
        wk.wait(5000)
    QApplication.processEvents()


def _patch_gateway(monkeypatch, client, key="k"):
    from easycad.ai import gateway as gw
    monkeypatch.setattr(gw, "resolve_api_key", lambda *a, **k: key)
    monkeypatch.setattr(gw, "_client", lambda *a, **k: client)


def test_word_find_marks_and_enter_goes_to_item(monkeypatch):
    _patch_gateway(monkeypatch, _FakeClient())
    w, (memo, box, box2) = _board()
    try:
        w.open_find()
        bar = w._find_bar
        bar.edit.setText("토너")                                                         # 치면 바로 낱말로
        assert [r[0] for r in bar.rows] == [box] and w._find_marks == [box] and bar.rows[0][3] is True
        QApplication.sendEvent(bar.edit, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, ""))
        v = w._view
        assert box.isSelected() and (v.mapToScene(v.viewport().rect().center()) - box.sceneBoundingRect().center()).manhattanLength() < 3   # 그 도형으로(고르고 가운데)
        QApplication.sendEvent(bar.edit, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier, ""))
        QApplication.processEvents()
        assert w._find_bar is None and w._find_marks == []                              # Esc = 닫고 점선도 지움
    finally:
        w.close()


def test_semantic_find_finds_different_words_and_caches(monkeypatch):
    client = _FakeClient()
    _patch_gateway(monkeypatch, client)
    w, (memo, box, box2) = _board()
    try:
        w.open_find()
        bar = w._find_bar
        bar.edit.setText("밥 뭐 먹지")
        assert bar.rows == []                                                            # 낱말로는 없음
        _wait_sem(bar)
        assert [r[0] for r in bar.rows][:1] == [memo] and bar.rows[0][3] is False          # 뜻으로 = 「점심 후보」 메모(표시 「뜻」)
        assert box2 not in [r[0] for r in bar.rows]                                      # 관련 없는 건 안 나옴
        n = client.calls
        bar.edit.setText("인쇄기")
        _wait_sem(bar)
        assert [r[0] for r in bar.rows][:1] == [box] and client.calls == n + 1              # 칠판 글 뜻 숫자는 모아 둠 — 질문만 새로
        assert os.path.exists(w._find_cache_path())
        bar.close_bar()
    finally:
        w.close()


def test_no_key_falls_back_to_word_find_with_notice(monkeypatch):
    _patch_gateway(monkeypatch, _FakeClient(), key="")
    w, (memo, box, box2) = _board()
    try:
        w.open_find()
        bar = w._find_bar
        bar.edit.setText("회의실")
        _wait_sem(bar)
        assert [r[0] for r in bar.rows] == [box2] and "낱말 찾기만" in bar.err.text()
        bar.close_bar()
    finally:
        w.close()
