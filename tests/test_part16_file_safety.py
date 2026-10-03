"""점검 1단계 — 파일 안전(2026-10-03): 안전 저장(.ecad·DXF·DWG)·새 버전 파일 경고·자동 저장/복구.

자동 저장 복구 폴더는 conftest/_shared가 `EASYCAD_RECOVERY_DIR`로 임시 폴더를 가리키게 한다
(실사용자 앱 데이터 오염 방지). 각 테스트는 자기가 만든 복구 파일만 확인·정리한다."""
import json
import os
import subprocess
import sys
import uuid
from unittest.mock import patch

from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QGraphicsScene, QMessageBox

from _shared import *  # noqa: F401,F403

from easycad.fileio import autosave, document as document_mod, dxf_export


def _tmp(name):
    d = os.path.join(_TMP, f"safety_{uuid.uuid4().hex}")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _scene_with_rect():
    sc = QGraphicsScene()
    _mk_rect(sc, QPen(QColor("red")), 0, 0, 100, 60)
    return sc


def _dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


# ---- A. .ecad 안전 저장 ---------------------------------------------------
def test_ecad_save_failure_keeps_original():
    path = _tmp("a.ecad")
    save_document(_scene_with_rect(), path)
    before = open(path, encoding="utf-8").read()

    def _boom(obj, f, **kw):
        f.write('{"format": "easycad-doc", "items": [')   # 반쯤 쓰다가
        raise RuntimeError("디스크 오류 흉내")

    sc2 = _scene_with_rect()
    _mk_rect(sc2, QPen(QColor("blue")), 200, 0, 50, 50)
    with patch.object(document_mod.json, "dump", side_effect=_boom):
        try:
            save_document(sc2, path)
            assert False, "예외가 전파돼야 함"
        except RuntimeError:
            pass
    assert open(path, encoding="utf-8").read() == before   # 원본 그대로
    assert not os.path.exists(path + ".tmp")                # 임시 파일 정리
    assert load_document(QGraphicsScene(), path) == 1


def test_ecad_save_success_replaces_and_leaves_no_tmp():
    path = _tmp("b.ecad")
    save_document(_scene_with_rect(), path)
    sc2 = _scene_with_rect()
    _mk_rect(sc2, QPen(QColor("blue")), 200, 0, 50, 50)
    save_document(sc2, path)
    assert load_document(QGraphicsScene(), path) == 2
    assert not os.path.exists(path + ".tmp")


# ---- B. DXF·DWG 안전 저장 -------------------------------------------------
def test_dxf_save_failure_keeps_original():
    path = _tmp("c.dxf")
    export_dxf(_scene_with_rect(), path)
    before = open(path, "rb").read()

    class _BadDoc:
        def saveas(self, p):
            with open(p, "w") as f:
                f.write("0\nSECTION\n")
            raise RuntimeError("쓰기 실패 흉내")

    with patch.object(dxf_export, "_build_dxf_doc", return_value=_BadDoc()):
        try:
            export_dxf(_scene_with_rect(), path)
            assert False
        except RuntimeError:
            pass
    assert open(path, "rb").read() == before
    assert not os.path.exists(path + ".tmp")


def test_dwg_overwrite_keeps_original_when_converter_fails():
    """ezdxf `odafc.export_dwg(replace=True)`는 변환 전에 대상부터 지운다 — 우리 래퍼는
    임시 폴더로 변환하므로 변환기가 없거나 실패해도 원본 .dwg가 남아야 한다."""
    from ezdxf.addons import odafc
    path = _tmp("d.dwg")
    with open(path, "wb") as f:
        f.write(b"ORIGINAL-DWG")

    def _fail(doc, filename, **kw):
        # 진짜 ezdxf처럼 replace=True면 "대상"을 먼저 지운 뒤 실패 — 대상이 임시 폴더 안이어야 원본 무사
        if os.path.exists(filename):
            os.remove(filename)
        raise odafc.ODAFCNotInstalledError("ODA File Converter not installed")

    with patch.object(odafc, "export_dwg", side_effect=_fail):
        try:
            dxf_export.export_dwg(_scene_with_rect(), path)
            assert False
        except odafc.ODAFCNotInstalledError:
            pass
    assert open(path, "rb").read() == b"ORIGINAL-DWG"
    leftovers = [n for n in os.listdir(os.path.dirname(path)) if n.startswith(".ecad_dwg_")]
    assert leftovers == []


def test_dwg_overwrite_success_replaces_original():
    from ezdxf.addons import odafc
    path = _tmp("e.dwg")
    with open(path, "wb") as f:
        f.write(b"ORIGINAL-DWG")
    seen = {}

    def _ok(doc, filename, **kw):
        seen["target"] = filename
        with open(filename, "wb") as f:
            f.write(b"NEW-DWG")

    with patch.object(odafc, "export_dwg", side_effect=_ok):
        assert dxf_export.export_dwg(_scene_with_rect(), path)
    assert os.path.normcase(os.path.dirname(os.path.dirname(seen["target"]))) == \
        os.path.normcase(os.path.dirname(os.path.abspath(path)))   # 같은 폴더의 임시 폴더로 변환
    assert open(path, "rb").read() == b"NEW-DWG"
    assert [n for n in os.listdir(os.path.dirname(path)) if n.startswith(".ecad_dwg_")] == []


# ---- C. 새 버전 파일 경고 ---------------------------------------------------
def test_load_document_reports_newer_version():
    path = _tmp("f.ecad")
    save_document(_scene_with_rect(), path)
    info = {}
    load_document(QGraphicsScene(), path, info=info)
    assert info == {"version": 1, "newer": False}

    data = json.load(open(path, encoding="utf-8"))
    data["version"] = 99
    json.dump(data, open(path, "w", encoding="utf-8"))
    info = {}
    assert load_document(QGraphicsScene(), path, info=info) == 1   # 거부하지 않고 읽는다
    assert info["newer"] is True and info["version"] == 99


def test_open_newer_version_shows_warning():
    path = _tmp("g.ecad")
    save_document(_scene_with_rect(), path)
    data = json.load(open(path, encoding="utf-8"))
    data["version"] = 2
    json.dump(data, open(path, "w", encoding="utf-8"))
    w = CanvasWindow()
    calls = []
    with patch.object(QMessageBox, "warning", side_effect=lambda *a, **k: calls.append(a[1])):
        w._do_open_ecad(path)
    assert calls == ["새 버전 파일"]
    assert len(w._scene.items()) == 1

    calls.clear()
    path2 = _tmp("h.ecad")
    save_document(_scene_with_rect(), path2)
    w2 = CanvasWindow()
    with patch.object(QMessageBox, "warning", side_effect=lambda *a, **k: calls.append(a[1])):
        w2._do_open_ecad(path2)
    assert calls == []   # 같은 버전이면 조용히


# ---- D. 자동 저장·복구 -----------------------------------------------------
import pytest
from PyQt6.QtCore import Qt as _Qt
from PyQt6.QtWidgets import QApplication as _QApp


def _buttons(state):
    return patch.object(_QApp, "mouseButtons", staticmethod(lambda: state))


@pytest.fixture(autouse=True)
def _mouse_released():
    """오프스크린 스위트에서는 앞선 테스트의 합성 마우스 누름이 풀리지 않고 남는 경우가 있다
    (전체 실행에서 `mouseButtons()==LeftButton` 실측) — 자동 저장은 드래그 중이면 미루므로,
    이 파일의 테스트는 "버튼 안 누름"으로 고정한다(누름 상태는 아래 전용 테스트가 검증)."""
    with _buttons(_Qt.MouseButton.NoButton):
        yield


def test_autosave_defers_while_mouse_pressed_then_retries_once():
    w = _dirty_window()
    with _buttons(_Qt.MouseButton.LeftButton):
        w._autosave_tick()
        w._autosave_tick()   # 두 번 불려도 재시도 예약은 한 겹
    assert w._active_doc.autosave_id is None and w._autosave_retry_pending
    w._autosave_retry()      # 3초 뒤 재시도(마우스는 이제 놓임 — fixture 상태)
    assert w._active_doc.autosave_id and not w._autosave_retry_pending
    autosave.remove(w._active_doc.autosave_id)


def _dirty_window():
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w._mark_dirty()
    return w


def test_autosave_writes_only_dirty_docs_then_save_removes():
    w = _dirty_window()
    w._open_new_tab()          # 두 번째 탭은 깨끗 — 자동 저장 대상 아님
    clean = w._active_doc
    w._autosave_tick()
    dirty = w._docs[0]
    assert dirty.autosave_id and clean.autosave_id is None
    ecad = os.path.join(autosave.recovery_dir(), dirty.autosave_id + ".ecad")
    meta = json.load(open(ecad[:-5] + ".json", encoding="utf-8"))
    assert meta["pid"] == os.getpid()
    assert load_document(QGraphicsScene(), ecad) == 1
    assert dirty.autosave_pending is False

    # 바뀐 게 없으면 다시 쓰지 않는다
    mtime = os.path.getmtime(ecad)
    w._autosave_tick()
    assert os.path.getmtime(ecad) == mtime

    # 진짜 저장하면 복구 파일이 사라진다
    w._tabs.setCurrentIndex(0)
    w._do_save_ecad(_tmp("saved.ecad"))
    assert not os.path.exists(ecad) and dirty.autosave_id is None


def test_autosave_removed_on_tab_close_after_discard():
    w = _dirty_window()
    w._open_new_tab()
    w._tabs.setCurrentIndex(0)
    w._autosave_tick()
    doc = w._docs[0]
    ecad = os.path.join(autosave.recovery_dir(), doc.autosave_id + ".ecad")
    assert os.path.exists(ecad)
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Discard):
        w._close_tab_at(0)
    assert not os.path.exists(ecad)


def test_find_orphans_skips_live_process_files():
    live, dead = autosave.new_id(), autosave.new_id()
    sc = _scene_with_rect()
    try:
        autosave.write(live, sc, None, title="살아있음")            # 이 프로세스 소유
        autosave.write(dead, sc, None, title="죽은 프로세스")
        meta_path = os.path.join(autosave.recovery_dir(), dead + ".json")
        meta = json.load(open(meta_path, encoding="utf-8"))
        meta["pid"] = _dead_pid()
        json.dump(meta, open(meta_path, "w", encoding="utf-8"))
        ids = [i for i, _p, _m in autosave.find_orphans()]
        assert dead in ids and live not in ids
    finally:
        autosave.remove(live)
        autosave.remove(dead)


def test_restore_autosave_reopens_with_original_path_and_dirty():
    orig = _tmp("원본.ecad")
    doc_id = autosave.new_id()
    sc = _scene_with_rect()
    _mk_rect(sc, QPen(QColor("blue")), 200, 0, 50, 50)
    autosave.write(doc_id, sc, None, doc_path=orig, title="원본.ecad")
    try:
        w = CanvasWindow()
        ecad = os.path.join(autosave.recovery_dir(), doc_id + ".ecad")
        meta = json.load(open(ecad[:-5] + ".json", encoding="utf-8"))
        w._restore_autosave(doc_id, ecad, meta)
        assert len(w._docs) == 1                     # 빈 첫 탭에 채움
        assert len(w._scene.items()) == 2
        assert w._doc_path == orig
        assert w._active_doc.dirty and w._tabs.tabText(0) == "*원본.ecad"
        assert w._active_doc.autosave_id == doc_id   # 저장 전까진 복구 파일 유지
        assert os.path.exists(ecad)
        w._do_save_ecad(orig)
        assert not os.path.exists(ecad)
        assert load_document(QGraphicsScene(), orig) == 2
    finally:
        autosave.remove(doc_id)


def test_offer_recovery_delete_button_removes_orphans():
    doc_id = autosave.new_id()
    autosave.write(doc_id, _scene_with_rect(), None, title="지울 것")
    meta_path = os.path.join(autosave.recovery_dir(), doc_id + ".json")
    meta = json.load(open(meta_path, encoding="utf-8"))
    meta["pid"] = _dead_pid()
    json.dump(meta, open(meta_path, "w", encoding="utf-8"))
    w = CanvasWindow()

    def _exec(box):
        for b in box.buttons():
            if b.text() == "지우기":
                box._clicked = b
        return 0

    with patch.object(QMessageBox, "exec", _exec), \
         patch.object(QMessageBox, "clickedButton", lambda box: box._clicked):
        w._offer_recovery()
    assert not os.path.exists(meta_path)
    assert not os.path.exists(meta_path[:-5] + ".ecad")
