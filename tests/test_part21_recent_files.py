"""§8 항목32(2026-10-03) — 최근 연 파일. 사용자 결정: 10개 · DXF/DWG 포함 · 파일 메뉴 하위 목록.
설정은 conftest가 EASYCAD_SETTINGS_ORG=EasyCAD-pytest로 격리 — 실사용자 목록을 건드리지 않는다."""
import os
import uuid
from unittest.mock import patch

from PyQt6.QtWidgets import QMessageBox

from _shared import *  # noqa: F401,F403


def _tmp(name):
    d = os.path.join(_TMP, f"recent_{uuid.uuid4().hex}")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _fresh_window():
    w = CanvasWindow()
    w._set_recent_files([])
    return w


def test_settings_are_isolated_from_real_user():
    assert os.environ.get("EASYCAD_SETTINGS_ORG") == "EasyCAD-pytest"
    assert CanvasWindow._recent_settings().organizationName() == "EasyCAD-pytest"


def test_save_and_open_put_file_on_top_without_duplicates():
    w = _fresh_window()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    a, b = _tmp("a.ecad"), _tmp("b.ecad")
    w._do_save_ecad(a)
    w._do_save_ecad(b)
    assert w._recent_files() == [os.path.abspath(b), os.path.abspath(a)]
    w2 = CanvasWindow()
    w2._open_path(a)                         # 다시 열면 맨 위로, 중복 없음
    assert w2._recent_files() == [os.path.abspath(a), os.path.abspath(b)]


def test_dxf_open_is_remembered_but_dxf_export_is_not():
    w = _fresh_window()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    dxf = _tmp("c.dxf")
    w._do_export_dxf(dxf)
    assert w._recent_files() == []           # 내보내기는 기억 안 함
    w2 = CanvasWindow()
    with patch.object(w2, "_confirm_dxf_open_once", return_value=True):
        w2._open_path(dxf)
    assert w2._recent_files() == [os.path.abspath(dxf)]


def test_list_is_capped_at_ten():
    w = _fresh_window()
    for i in range(12):
        w._remember_recent(_tmp(f"{i}.ecad"))
    files = w._recent_files()
    assert len(files) == 10 and os.path.basename(files[0]) == "11.ecad"


def test_missing_file_is_reported_and_removed():
    w = _fresh_window()
    gone = _tmp("gone.ecad")
    w._remember_recent(gone)
    titles = []
    with patch.object(QMessageBox, "warning", side_effect=lambda *a, **k: titles.append(a[1])):
        w._open_recent(os.path.abspath(gone))
    assert titles == ["최근 파일"] and w._recent_files() == []


def test_menu_lists_recent_files_and_clear():
    w = _fresh_window()
    w._fill_recent_menu()
    acts = w._recent_menu.actions()
    assert len(acts) == 1 and not acts[0].isEnabled()       # (없음)
    p = _tmp("m.ecad")
    _mk_rect(w._scene, w.make_pen(), 0, 0, 40, 30)
    w._do_save_ecad(p)
    w._fill_recent_menu()
    texts = [a.text() for a in w._recent_menu.actions() if not a.isSeparator()]
    assert texts[0].startswith("1  m.ecad") and texts[-1] == "목록 비우기"
    w._recent_menu.actions()[-1].trigger()
    assert w._recent_files() == []
