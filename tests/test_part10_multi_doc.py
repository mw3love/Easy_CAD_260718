"""§8 항목10(다중 도면 지원 — 탭 + 새 창) Stage A~D 회귀.

deep-interview(2026-08-18)로 확정된 설계: `CanvasDocument`(document.py)가 씬·undo/redo·
레이어·저장경로·dirty·라우팅 캐시를 갖고, `CanvasWindow`는 `self._active_doc`으로 포워딩하는
프로퍼티만 둔다(host.py `_PER_DOC_ATTRS`). 탭은 한 창 안의 여러 `CanvasDocument`, 클립보드는
`self._clipboard`(창 인스턴스별 — 독립 생성된 창은 격리, "새 창"만 부모 것을 공유, Stage D).

이 파일이 검증하는 것:
  - Stage A: 포워딩 프로퍼티가 활성 문서를 정확히 가리킴(순수 리팩터, 단일 문서 기준 무회귀는
    기존 스모크 전체가 이미 담당 — 여기서는 다중 문서 상황에서의 격리만 추가로 본다).
  - Stage B: 탭 추가/전환/닫기, "새로 만들기"·"열기"의 새 탭 의미 변화, 탭 제목, 클립보드가
    같은 창의 다른 탭 사이엔 공유되지만 다른 창 인스턴스와는 격리됨.
  - Stage C: dirty 추적(undo 저널에 뭔가 쌓이면 True, 저장하면 False), Ctrl+S 빠른저장
    (경로 있으면 다이얼로그 없음), "다른 이름으로 저장"은 항상 다이얼로그, 탭/창 닫기confirm
    (저장/버리기/취소). `QMessageBox.warning`을 직접 몽키패치해 실제 모달 없이 확인 —
    ⚠ 기존 test_part1/test_part6의 `w.close()` 8곳은 이 기능 도입으로 dirty 상태면 실제
    확인창이 뜨게 됐는데, 그 테스트들은 닫기확인이 검증 대상이 아니라서 `close()` 직전에
    `w._active_doc.dirty = False`를 추가해 무관하게 유지했다(오프스크린에서도 진짜 모달
    `.exec()`은 블로킹된다는 걸 이 참에 실측 확인 — 이전엔 dirty 트래킹 자체가 버그로
    무효였어서 몰랐던 위험).
  - Stage D: "새 창"(`_open_new_window`) — 같은 프로세스 안의 독립 최상위 창. sticky 설정은
    생성 시점 스냅샷만 복사(그 뒤론 독립), 도형 클립보드는 인스턴스를 그대로 공유(진짜
    실시간). `_live_windows`로 가비지컬렉트 방지 + `closeEvent`에서 해제.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part10_multi_doc.py.
"""
from contextlib import contextmanager

from PyQt6.QtWidgets import QMessageBox, QFileDialog

from _shared import *


@contextmanager
def _mock_message_box(answer):
    """[§8 항목10 Stage C] `QMessageBox.warning`(정적 편의 메서드)을 실제 모달 없이
    `answer`(StandardButton)를 곧바로 반환하도록 교체 — 클릭한 척 대체."""
    orig = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **kw: answer)
    try:
        yield
    finally:
        QMessageBox.warning = orig


def test_new_doc_opens_new_tab_preserves_previous():
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    first_doc = w._active_doc
    assert len(w._docs) == 1

    w._new_doc()   # ["새로 만들기" §8 항목10 Stage B] 이제 현재 씬을 비우지 않고 새 탭을 연다
    assert len(w._docs) == 2
    assert w._active_doc is not first_doc
    assert w._scene.items() == []                      # 새 탭은 빈 문서
    assert len(first_doc.scene.items()) == 1            # 이전 탭의 도형은 그대로 남음


def test_tab_switch_restores_per_doc_state():
    w = CanvasWindow()
    r1 = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r1)
    doc0 = w._active_doc
    assert w._undo and not w._redo

    w._open_new_tab()
    _mk_rect(w._scene, w.make_pen(), 100, 100, 20, 20)
    doc1 = w._active_doc
    assert doc1 is not doc0
    assert w._scene is doc1.scene
    assert len(w._scene.items()) == 1

    w._tabs.setCurrentIndex(w._docs.index(doc0))
    assert w._active_doc is doc0
    assert w._scene is doc0.scene
    assert len(w._scene.items()) == 1   # doc0 도형(r1)만, doc1 도형은 안 섞임
    assert w._undo and not w._redo      # doc0의 undo 저널이 되돌아옴
    assert w._act_undo.isEnabled()      # [§8 항목10 Stage B] 탭 전환 시 undo/redo 액션도 갱신


def test_close_tab_removes_only_that_doc():
    w = CanvasWindow()
    doc0 = w._active_doc
    _mk_rect(w._scene, w.make_pen(), 0, 0, 10, 10)
    doc1 = w._open_new_tab()
    _mk_rect(w._scene, w.make_pen(), 20, 20, 10, 10)
    doc2 = w._open_new_tab()
    _mk_rect(w._scene, w.make_pen(), 40, 40, 10, 10)
    assert len(w._docs) == 3

    w._close_tab_at(w._docs.index(doc1))
    assert len(w._docs) == 2
    assert doc1 not in w._docs
    assert len(doc0.scene.items()) == 1   # 안 건드린 문서들은 그대로
    assert len(doc2.scene.items()) == 1


def test_closing_last_tab_closes_window():
    w = CanvasWindow()
    closed = []
    w.close = lambda: closed.append(True)   # [§8 항목10 Stage B] close() 위임만 확인
    assert len(w._docs) == 1
    w._close_tab_at(0)
    assert closed == [True]
    assert len(w._docs) == 1   # 실제로 안 지워짐 — close()가 처리할 몫(Stage C closeEvent)


def test_tab_title_untitled_then_filename():
    w = CanvasWindow()
    assert w._tab_title_for(w._active_doc) == "제목 없음1"
    doc2 = w._open_new_tab()
    assert w._tab_title_for(doc2) == "제목 없음2"   # 생성 순번 — 안 겹침

    w._active_doc.doc_path = r"C:\drawings\panel.ecad"
    w._update_tab_title()
    idx = w._docs.index(w._active_doc)
    assert w._tabs.tabText(idx) == "panel.ecad"


def test_clipboard_shared_across_tabs_same_window():
    w = CanvasWindow()
    r1 = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    r1.setSelected(True)
    w.copy_selection()
    assert w._clip

    w._open_new_tab()
    assert w._scene.items() == []
    w.paste_selection()
    assert len(w._scene.items()) == 1   # 다른 탭에서 복사한 도형이 새 탭에도 붙여넣기됨


def test_clipboard_isolated_across_independent_windows():
    w1 = CanvasWindow()
    r1 = _mk_rect(w1._scene, w1.make_pen(), 0, 0, 40, 30)
    r1.setSelected(True)
    w1.copy_selection()
    assert w1._clip

    w2 = CanvasWindow()   # [§8 항목10] 독립 생성 — 부모 없이 만든 창은 클립보드도 새 인스턴스
    assert not w2._clip
    assert w1._clipboard is not w2._clipboard


def test_open_new_tab_registers_and_activates_doc():
    w = CanvasWindow()
    doc = w._open_new_tab()
    assert doc in w._docs
    assert w._active_doc is doc
    assert w._tabs.currentWidget() is doc.view


def test_new_tab_inherits_current_theme_background():
    """[§8 항목10 실사용 버그 수정, 2026-08-18] 사용자 실사용 발견 — 새 탭이 다크모드에서도
    흰 배경으로 뜨고, 다크모드를 껐다 켜야만 정상화됐다. `CanvasDocument`는 항상 흰색으로
    시작(테마를 모르는 잎 클래스)하는데, 원래 단일 문서 시절엔 `__init__` 끝의 `_apply_theme`
    한 번이 그 유일한 씬을 다시 칠해 문제가 없었지만, "새 탭"으로 만든 문서는 그 호출을 못
    받았다."""
    w = CanvasWindow()   # 다크 기본
    dark_hex = w._docs[0].scene.backgroundBrush().color().name()
    assert dark_hex != "#ffffff"

    doc2 = w._open_new_tab()
    assert doc2.scene.backgroundBrush().color().name() == dark_hex   # 새 탭도 즉시 다크


def test_theme_toggle_repaints_background_tabs_too():
    """`_apply_theme`가 활성 탭(`self._scene`)만 칠하면 다른 탭은 테마를 토글해도 예전
    색으로 남는다 — 열려 있는 모든 문서를 칠해야 한다."""
    w = CanvasWindow()
    doc2 = w._open_new_tab()
    w._tabs.setCurrentIndex(0)   # doc2는 이제 비활성(백그라운드) 탭

    w._apply_theme(False)   # 라이트로 토글 — 활성 탭에서 눌렀다고 가정
    assert w._docs[0].scene.backgroundBrush().color().name() == "#ffffff"
    assert doc2.scene.backgroundBrush().color().name() == "#ffffff"   # 백그라운드 탭도 갱신


# ---- Stage C: dirty 추적 + 빠른저장 + 닫기확인 ------------------------------

def test_dirty_set_on_edit_cleared_on_save():
    w = CanvasWindow()
    assert not w._active_doc.dirty
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r)
    assert w._active_doc.dirty
    assert w._tab_title_for(w._active_doc).startswith("*")

    path = os.path.join(_TMP, f"a_{uuid.uuid4().hex}.ecad")
    w._do_save_ecad(path)
    assert not w._active_doc.dirty
    assert w._active_doc.doc_path == path
    assert not w._tab_title_for(w._active_doc).startswith("*")


def test_dirty_set_on_undo_and_redo():
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r)
    w._do_save_ecad(os.path.join(_TMP, f"a_{uuid.uuid4().hex}.ecad"))
    assert not w._active_doc.dirty

    w.undo()
    assert w._active_doc.dirty   # 저장 후 되돌리기도 다시 dirty


def test_new_tab_and_loaded_tab_start_clean():
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r)
    assert w._active_doc.dirty

    doc2 = w._open_new_tab()
    assert not doc2.dirty   # 새 탭은 항상 깨끗하게 시작


def test_quick_save_reuses_path_without_dialog():
    w = CanvasWindow()
    path = os.path.join(_TMP, f"a_{uuid.uuid4().hex}.ecad")
    w._active_doc.doc_path = path

    def _boom(*a, **kw):
        raise AssertionError("경로가 이미 있는데 저장 다이얼로그가 떴다(빠른저장 실패)")

    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r)
    with patch.object(QFileDialog, "getSaveFileName", staticmethod(_boom)):
        w._save_doc()
    assert not w._active_doc.dirty
    assert w._active_doc.doc_path == path


def test_save_as_always_shows_dialog():
    w = CanvasWindow()
    path = os.path.join(_TMP, f"existing_{uuid.uuid4().hex}.ecad")
    w._active_doc.doc_path = path
    renamed = os.path.join(_TMP, f"renamed_{uuid.uuid4().hex}.ecad")
    calls = []

    def _fake(*a, **kw):
        calls.append(1)
        return (renamed, "")

    with patch.object(QFileDialog, "getSaveFileName", staticmethod(_fake)):
        w._save_doc_as()
    assert calls == [1]
    assert w._active_doc.doc_path == renamed


def test_close_tab_cancel_keeps_tab_open():
    w = CanvasWindow()
    w._open_new_tab()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r)
    n = len(w._docs)
    with _mock_message_box(QMessageBox.StandardButton.Cancel):
        w._close_tab_at(1)
    assert len(w._docs) == n   # 취소 — 아무 것도 안 지워짐


def test_close_tab_discard_clears_dirty_and_closes():
    w = CanvasWindow()
    doc1 = w._open_new_tab()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r)
    assert doc1.dirty
    with _mock_message_box(QMessageBox.StandardButton.Discard):
        w._close_tab_at(w._docs.index(doc1))
    assert doc1 not in w._docs


def test_close_tab_not_dirty_skips_dialog():
    w = CanvasWindow()
    w._open_new_tab()   # 깨끗한 탭
    with _mock_message_box(QMessageBox.StandardButton.Cancel):
        w._close_tab_at(1)   # Cancel을 리턴하는 몽키패치인데도 지워지면 다이얼로그가 안 뜬 것
    assert len(w._docs) == 1


def test_close_event_cancel_blocks_window_close():
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r)
    from PyQt6.QtGui import QCloseEvent
    ev = QCloseEvent()
    with _mock_message_box(QMessageBox.StandardButton.Cancel):
        w.closeEvent(ev)
    assert not ev.isAccepted()


def test_close_event_discard_accepts_and_clears_dirty():
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w.push_undo_add(r)
    from PyQt6.QtGui import QCloseEvent
    ev = QCloseEvent()
    with _mock_message_box(QMessageBox.StandardButton.Discard):
        w.closeEvent(ev)
    assert ev.isAccepted()
    assert not w._active_doc.dirty


# ---- Stage D: 새 창 --------------------------------------------------------

def test_new_window_creates_independent_registered_instance():
    from easycad.canvas.host import _open_new_window
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w2 = _open_new_window(source=w)
    try:
        assert w2 is not w
        assert w2 in CanvasWindow._live_windows
        assert w2._active_doc is not w._active_doc
        assert w2._scene.items() == []          # 도형은 안 옮겨감 — 정말 빈 새 창
        assert len(w._scene.items()) == 1        # 원래 창은 그대로
    finally:
        w2._active_doc.dirty = False
        w2.close()


def test_new_window_snapshots_sticky_settings_then_diverges():
    from easycad.canvas.host import _open_new_window
    w = CanvasWindow()
    w.current_color = QColor("#ff00ff")
    w.snap_enabled = False
    w2 = _open_new_window(source=w)
    try:
        assert w2.current_color.name() == "#ff00ff"   # 생성 시점 값을 그대로 복사
        assert w2.snap_enabled is False

        w.current_color = QColor("#00ff00")   # 부모 창을 나중에 바꿔도
        assert w2.current_color.name() == "#ff00ff"   # 이미 연 창엔 안 옴(독립)
    finally:
        w2._active_doc.dirty = False
        w2.close()


def test_new_window_shares_clipboard_live_with_parent():
    from easycad.canvas.host import _open_new_window
    w = CanvasWindow()
    w2 = _open_new_window(source=w)
    try:
        assert w2._clipboard is w._clipboard   # 같은 인스턴스 — 스냅샷이 아니라 진짜 공유

        r = _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
        r.setSelected(True)
        w.copy_selection()   # 새 창을 연 "뒤에" 복사해도
        assert w2._clip and w2._clip is w._clip   # w2에도 실시간으로 보임(스냅샷이 아님)
    finally:
        w2._active_doc.dirty = False
        w2.close()


def test_new_window_removed_from_live_list_on_close():
    from easycad.canvas.host import _open_new_window
    w = CanvasWindow()
    w2 = _open_new_window(source=w)
    assert w2 in CanvasWindow._live_windows
    w2.close()
    assert w2 not in CanvasWindow._live_windows


def test_new_window_without_source_uses_defaults():
    from easycad.canvas.host import _open_new_window
    w2 = _open_new_window(source=None)
    try:
        assert w2.current_tool == "select"
        assert w2.snap_enabled is True
    finally:
        w2.close()
