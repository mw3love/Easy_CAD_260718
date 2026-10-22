"""칠판에서 찾기(Ctrl+F) — 웹 find.jsx를 옮김(§8 항목61 ③-2, 데스크톱 2026-10-22 — 사용자: 뜻으로 찾기까지).

치면 바로 낱말로 찾고(앱 안, 인터넷 없이도), 0.4초 쉬면 KAIROS 임베딩으로 뜻이 가까운 것을 찾아 순서를 다시 맞춘다(`ai/board_find.find` — 웹 서버와 같은 계산).
찾은 것은 칠판 위 노란 점선, ↑↓로 고르고 Enter·누르기 = 그 도형으로 가기(고르고 가운데로), Esc 닫기.
뜻 숫자는 앱 데이터 폴더 `find/<문서 지문>.emb.json`에 모아 둠 — 도면 폴더에 파일을 만들지 않게(웹은 칠판 옆).
"""
from __future__ import annotations

import hashlib
import os

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from easycad.ai import board_find

MARK_COLOR = "#f59e0b"   # 노란 점선(웹 찾기 표시와 같은 뜻)


def item_texts(scene) -> list:
    """칠판 맨 위 도형마다 (도형, 웹 칸 dict, 글) — 글 없는 것은 뺌. 글 뽑기는 웹 서버와 같은 `board_find.item_text`."""
    from easycad.fileio.document import item_to_dict
    out = []
    for it in scene.items():
        if it.parentItem() is not None or not hasattr(it, "capture_state"):
            continue
        try:
            d = item_to_dict(it)
        except Exception:   # 저장 형식이 없는 보조 도형(미리보기 등)은 건너뜀
            continue
        t = board_find.item_text(d)
        if t:
            out.append((it, d, t))
    return out


def word_hits(rows, q: str) -> list:
    """낱말 찾기 — 띄어 쓴 낱말이 모두 들어 있는 것(웹 wordHits)."""
    words = [w for w in q.lower().split() if w]
    if not words:
        return []
    return [r for r in rows if all(w in r[2].lower() for w in words)]


class _SemWorker(QThread):
    """뜻으로 찾기(KAIROS) — 화면이 안 멈추게 뒤에서. 끝나면 done(번호, 결과 | None, 오류 글)."""
    done = pyqtSignal(int, object, str)

    def __init__(self, seq, doc, query, cache_path):
        super().__init__()
        self._a = (seq, doc, query, cache_path)

    def run(self):
        seq, doc, query, cache_path = self._a
        try:
            from easycad.ai import gateway as gw
            key = gw.resolve_api_key()
            if not key:
                self.done.emit(seq, None, "KAIROS 키가 없어요 — 낱말 찾기만")
                return
            client = gw._client(key, gw.resolve_base_url(), timeout=60)
            self.done.emit(seq, board_find.find(client, doc, query, k=8, cache_path=cache_path), "")
        except Exception as e:   # 인터넷·키 문제 — 낱말 찾기는 그대로
            self.done.emit(seq, None, f"뜻으로 찾기 안 됨 — 낱말 찾기만 ({type(e).__name__})")


class _FindEdit(QLineEdit):
    def __init__(self, bar):
        super().__init__(bar)
        self._bar = bar

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self._bar.close_bar()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._bar.go(self._bar.at)
        elif k == Qt.Key.Key_Down:
            self._bar.go(min(len(self._bar.rows) - 1, self._bar.at + 1))
        elif k == Qt.Key.Key_Up:
            self._bar.go(max(0, self._bar.at - 1))
        else:
            super().keyPressEvent(e)


class FindBar(QWidget):
    """칠판 위 가운데 찾기 칸(웹 FindBar) — 뷰 화면 위 위젯."""

    def __init__(self, host):
        vp = host._view.viewport()
        super().__init__(vp)
        self._host = host
        self.setObjectName("findBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("#findBar { background: palette(window); border: 1px solid palette(mid); border-radius: 10px; }"
                           "QLineEdit { border: 0; background: transparent; font-size: 13.5px; padding: 2px; }"
                           "QListWidget { border: 0; background: transparent; }"
                           "QListWidget::item { padding: 4px 6px; border-radius: 6px; }"
                           "QListWidget::item:selected { background: rgba(245,158,11,.22); color: palette(text); }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        top = QHBoxLayout()
        icon = QLabel("🔍", self)
        self.edit = _FindEdit(self)
        self.edit.setPlaceholderText("칠판에서 찾기 — 낱말이 달라도 뜻으로 (↑↓ · Enter · Esc)")
        self.status = QLabel("", self)
        self.status.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        top.addWidget(icon)
        top.addWidget(self.edit, 1)
        top.addWidget(self.status)
        lay.addLayout(top)
        self.err = QLabel("", self)
        self.err.setStyleSheet("color: #d97706; font-size: 11px;")
        self.err.hide()
        lay.addWidget(self.err)
        self.list = QListWidget(self)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(lambda li: self.go(self.list.row(li)))
        self.list.hide()
        lay.addWidget(self.list)
        self.rows, self.at, self._sem, self._seq, self._workers = [], 0, None, 0, []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._ask_sem)
        self.edit.textChanged.connect(self._changed)
        self._place()
        self.show()
        self.raise_()
        self.edit.setFocus()

    def _place(self):
        vp = self.parentWidget()
        w = min(440, vp.width() - 32)
        self.setFixedWidth(max(200, w))
        self.adjustSize()
        self.move((vp.width() - self.width()) // 2, 12)

    # ---- 찾기 ----
    def _changed(self, _t=""):
        self._seq += 1
        self._sem = None
        self.err.hide()
        self.at = 0
        self._refresh()
        if self.edit.text().strip():
            self._timer.start()
            self.status.setText("뜻으로 찾는 중…")

    def _ask_sem(self):
        q = self.edit.text().strip()
        if not q:
            return
        rows = item_texts(self._host._scene)
        self._uids = {f"f{i}": r[0] for i, r in enumerate(rows)}
        doc = {"items": [{**r[1], "uid": f"f{i}"} for i, r in enumerate(rows)]}
        wk = _SemWorker(self._seq, doc, q, self._host._find_cache_path())
        wk.done.connect(self._sem_done)
        wk.finished.connect(lambda wk=wk: self._workers.remove(wk) if wk in self._workers else None)
        self._workers.append(wk)
        wk.start()

    def _sem_done(self, seq, res, err):
        if seq != self._seq:   # 그 사이 더 쳤음 — 옛 답은 버림
            return
        if res is None:
            self.err.setText(err)
            self.err.show()
        else:
            self._sem = [(self._uids[r["uid"]], r) for r in res if r["uid"] in self._uids]
        self._refresh()

    def _refresh(self):
        q = self.edit.text().strip()
        rows = item_texts(self._host._scene) if q else []
        words = word_hits(rows, q) if q else []
        word_items = {r[0] for r in words}
        live = {r[0] for r in rows}
        kind = lambda d: board_find.KIND_NAME.get(d.get("type", ""), d.get("type", ""))   # noqa: E731
        if self._sem is not None:   # 뜻 차례(낱말이 다 든 것은 점수를 더 받음) + 뜻 결과에 없는 낱말 결과는 뒤에
            out = [(it, r["kind"], r["text"], it in word_items) for it, r in self._sem if it in live]
            seen = {o[0] for o in out}
            out += [(it, kind(d), t, True) for it, d, t in words if it not in seen]
        else:
            out = [(it, kind(d), t, True) for it, d, t in words]
        self.rows = out
        self.list.clear()
        for it, k, t, w in out:
            li = QListWidgetItem(f"{k}    {t.splitlines()[0][:60]}    {'낱말' if w else '뜻'}")
            li.setToolTip("친 낱말이 들어 있음" if w else "낱말은 달라도 뜻이 가까움")
            self.list.addItem(li)
        self.list.setVisible(bool(out))
        self.list.setFixedHeight(min(300, 26 * len(out) + 8))
        busy = self._timer.isActive() or (self._sem is None and bool(q) and not self.err.isVisible() and self._workers)
        self.status.setText("뜻으로 찾는 중…" if busy else (f"{len(out)}개" if q else ""))
        if q and not out and not busy:
            self.status.setText("못 찾았어요")
        if out:
            self.list.setCurrentRow(min(self.at, len(out) - 1))
        self._host._set_find_marks([o[0] for o in out])
        self._place()

    def go(self, i):
        if not (0 <= i < len(self.rows)):
            return
        self.at = i
        self.list.setCurrentRow(i)
        self._host._show_item(self.rows[i][0])

    def close_bar(self):
        self._seq += 1
        self._host._set_find_marks([])
        self._host._find_bar = None
        self._host._view.setFocus()
        self.deleteLater()


class _FindMixin:
    """CanvasWindow 믹스인 — Ctrl+F 찾기 칸·노란 점선·그 도형으로 가기."""
    _find_bar = None
    _find_marks: list = []

    def open_find(self):
        if self._find_bar is not None:
            self._find_bar.edit.setFocus()
            self._find_bar.edit.selectAll()
            return
        self._find_bar = FindBar(self)

    def _find_cache_path(self) -> str:
        from easycad.fileio.autosave import recovery_dir
        d = os.path.join(os.path.dirname(recovery_dir()), "find")
        os.makedirs(d, exist_ok=True)
        doc = self._docs[self._tabs.currentIndex()] if hasattr(self, "_docs") and hasattr(self, "_tabs") else None
        key = (getattr(doc, "doc_path", None) or getattr(doc, "external_path", None) or f"untitled-{id(doc)}") if doc is not None else "untitled"
        return os.path.join(d, hashlib.sha1(str(key).encode("utf-8")).hexdigest()[:16] + ".emb.json")

    def _set_find_marks(self, items):
        self._find_marks = list(items)
        self._view.viewport().update()

    def _show_item(self, it):
        """그 도형으로 가기 — 고르고 가운데로, 화면에서 너무 작으면 키움(웹 showItem)."""
        if it.scene() is not self._scene:
            return
        self._scene.clearSelection()
        it.setSelected(True)
        v = self._view
        r = it.sceneBoundingRect()
        z = abs(v.transform().m11()) or 1.0
        if r.width() * z < 120:
            nz = min(1.0, v.viewport().width() * 0.4 / max(r.width(), 1.0))
            if nz > z:
                v.scale(nz / z, nz / z)
        v.centerOn(r.center())
        self._update_zoom_label()
        self._refresh_minimap()

    def draw_find_marks(self, painter):
        if not self._find_marks:
            return
        from PyQt6.QtGui import QColor, QPen
        z = abs(self._view.transform().m11()) or 1.0
        pen = QPen(QColor(MARK_COLOR), 2 / z, Qt.PenStyle.DashLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for it in self._find_marks:
            if it.scene() is self._scene:
                painter.drawRoundedRect(it.sceneBoundingRect().adjusted(-4 / z, -4 / z, 4 / z, 4 / z), 4 / z, 4 / z)
        painter.restore()
