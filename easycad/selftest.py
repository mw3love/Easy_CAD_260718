"""설치 점검 `EasyCAD.exe --selftest`(§8 항목43, 2026-10-16) — exe 안에서 아이콘·라이브러리 묶음·KAIROS 연결을 확인한다.

exe는 콘솔이 없고(`console=False`) 내부 파이썬을 따로 부를 수 없어서, 다른 PC(동료·심사위원)에서 "AI가 안 돼요"가 나오면
이걸로 원인을 가른다. 결과는 `%TEMP%/easycad_selftest.txt`에 쓰고, `--quiet`가 없으면 창으로도 보여 준다.
KAIROS 호출은 아주 짧은 흐름도 한 번(크레딧 아주 조금) — 키가 없으면 건너뛴다.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback


def _check(lines: list, name: str, fn):
    t0 = time.monotonic()
    try:
        detail = fn()
        lines.append(f"[OK]   {name} — {detail} ({time.monotonic() - t0:.1f}s)")
        return True
    except Exception as e:  # noqa: BLE001 — 점검은 실패를 모아 보여 주는 게 목적
        lines.append(f"[FAIL] {name} — {type(e).__name__}: {e}")
        lines.append("       " + traceback.format_exc().strip().splitlines()[-1])
        return False


def run(quiet: bool = False) -> int:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)

    lines = [f"Easy CAD 설치 점검 — {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"exe: {getattr(sys, 'frozen', False)}  python: {sys.version.split()[0]}  위치: {sys.executable}", ""]

    def icons():
        from easycad.canvas.core_constants import _icons_dir, _svg_icon_pixmap
        d = _icons_dir()
        n = len([f for f in os.listdir(d) if f.endswith(".svg")])
        pm = _svg_icon_pixmap("save", 24)
        if pm.isNull():
            raise RuntimeError("save.svg를 그리지 못함")
        return f"{n}개, {d}"

    def symbols():
        from easycad.fileio import symbol_library as sl
        return sl._library_path()

    def dxf():
        import ezdxf
        import ezdxf.math  # C 확장(DLL) — 회사 PC 보안 정책이 막는지
        return f"ezdxf {ezdxf.__version__}"

    def pdf():
        import fitz
        return f"PyMuPDF {fitz.VersionBind}"

    def ai_libs():
        import httpx
        import openai
        return f"openai {openai.__version__}, httpx {httpx.__version__}"

    ok = all([_check(lines, "아이콘", icons), _check(lines, "내 심볼 저장 위치", symbols),
              _check(lines, "DXF(ezdxf)", dxf), _check(lines, "PDF 열기(PyMuPDF)", pdf),
              _check(lines, "AI 연결 라이브러리", ai_libs)])

    from easycad.ai import gateway as gw
    key = gw.resolve_api_key()
    if not key:
        lines.append("[SKIP] KAIROS — 키가 없어요(앱에서 「KAIROS 연결 설정…」으로 넣은 뒤 다시 점검)")
    else:
        url = gw.resolve_base_url()

        def credit():
            remaining, quota = gw.get_credit_balance(key, url)
            return f"남은 크레딧 {remaining:,.0f} / {quota:,.0f}"

        def models():
            return f"글 모델 {len(gw.list_text_models(key, url, timeout=15.0))}개"

        def generate():
            from easycad.ai.text_to_mermaid import generate_mermaid
            code, used = generate_mermaid(key, "신청에서 승인까지 두 단계 흐름도", model=gw.TEXT_RECOMMEND_MERMAID,
                                          base_url=url)
            if "flowchart" not in code and "graph" not in code:
                raise RuntimeError(f"흐름도 코드가 아님: {code[:60]!r}")
            return f"흐름도 생성({used})"

        ok = all([_check(lines, "KAIROS 크레딧", credit), _check(lines, "KAIROS 모델 목록", models),
                  _check(lines, "KAIROS 흐름도 생성", generate)]) and ok

    lines += ["", "결과: 모두 정상" if ok else "결과: 실패한 항목이 있어요 — 이 파일을 개발자에게 보내 주세요"]
    out = os.path.join(tempfile.gettempdir(), "easycad_selftest.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    if not quiet:
        QMessageBox.information(None, "Easy CAD 설치 점검", "\n".join(lines) + f"\n\n저장: {out}")
    del app
    return 0 if ok else 1
