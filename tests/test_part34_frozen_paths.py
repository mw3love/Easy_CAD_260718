"""§8 항목43(2026-10-16) — exe(PyInstaller) 안에서의 경로: 아이콘 폴더·「내 심볼」 저장 위치.

처음 실제로 빌드해 보니 SVG 아이콘이 전부 빠졌고(아이콘 폴더 경로 어긋남), 내 심볼은 설치 폴더 안쪽을 가리켰다.
빌드 없이 `sys._MEIPASS`·`sys.frozen`을 흉내 내 같은 계산을 확인한다.
"""
import os
import sys

from _shared import *  # noqa: F401,F403


def test_icons_dir_in_frozen_build_matches_spec_datas(monkeypatch, tmp_path):
    from easycad.canvas import core_constants as cc
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    # EasyCAD.spec: datas=[('easycad/resources/icons', 'easycad/resources/icons')]
    assert cc._icons_dir() == tmp_path / "easycad" / "resources" / "icons"
    spec = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "EasyCAD.spec"), encoding="utf-8").read()
    assert "('easycad/resources/icons', 'easycad/resources/icons')" in spec


def test_icons_dir_in_dev_run_has_svgs():
    from easycad.canvas import core_constants as cc
    d = cc._icons_dir()
    assert (d / "copy_image.svg").exists() and (d / "save.svg").exists()


def test_symbol_library_goes_to_appdata_when_frozen(monkeypatch, tmp_path):
    from easycad.fileio import symbol_library as sl
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert sl._library_dir() == os.path.join(str(tmp_path), "EasyCAD", "EasyCAD")


def test_symbol_library_stays_in_repo_in_dev_run(monkeypatch):
    from easycad.fileio import symbol_library as sl
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert sl._library_dir() == os.path.join(sl._REPO_ROOT, "symbol_library")


def test_selftest_without_key_skips_kairos_and_writes_report(monkeypatch, tmp_path):
    """`EasyCAD.exe --selftest` — 키가 없으면 KAIROS 점검은 건너뛰고(실패 아님) 결과 파일을 남긴다."""
    import tempfile
    from unittest.mock import patch
    from easycad import selftest
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    with patch("easycad.ai.gateway.resolve_api_key", return_value=""):
        assert selftest.run(quiet=True) == 0
    text = (tmp_path / "easycad_selftest.txt").read_text(encoding="utf-8")
    assert "[OK]   아이콘" in text and "[SKIP] KAIROS" in text and "결과: 모두 정상" in text


def test_selftest_reports_kairos_failure(monkeypatch, tmp_path):
    import tempfile
    from unittest.mock import patch
    from easycad import selftest
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    def boom(*_a, **_k):
        raise RuntimeError("SSL: CERTIFICATE_VERIFY_FAILED")
    with patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            patch("easycad.ai.gateway.get_credit_balance", side_effect=boom), \
            patch("easycad.ai.gateway.list_text_models", return_value=["gpt-x"]), \
            patch("easycad.ai.text_to_flow.generate_flow", return_value=("{}", "m")):
        assert selftest.run(quiet=True) == 1
    text = (tmp_path / "easycad_selftest.txt").read_text(encoding="utf-8")
    assert "[FAIL] KAIROS 크레딧" in text and "CERTIFICATE" in text and "개발자에게" in text


def test_outer_name_is_magic_board_inner_stays_easycad():
    """§8 항목50(2026-10-16) — 겉 이름(창 제목·exe·아이콘)만 Magic Board, 설정 조직·.ecad는 EasyCAD 그대로."""
    import os
    from easycad.app_settings import APP_NAME, APP_TITLE
    from easycad.canvas.core_constants import _icons_dir
    w = CanvasWindow()
    assert w.windowTitle() == APP_TITLE == "Magic Board" and APP_NAME == "EasyCAD"
    for ext in (".svg", ".ico"):
        assert (_icons_dir() / f"app_magic_board{ext}").exists()
    spec = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "EasyCAD.spec"),
                encoding="utf-8").read()
    assert "name='MagicBoard'" in spec and "app_magic_board.ico" in spec
    assert "Magic Board 문서 (*.ecad)" in w._DOC_FILTER
