# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 스펙 — 최종 검수 Phase 7(릴리스 준비), 2026-08-26.

빌드: `pyinstaller EasyCAD.spec` (repo 루트에서). 결과는 `dist/EasyCAD/EasyCAD.exe`
(onedir — PyQt6은 리소스가 많아 onefile은 시작이 느려짐, 배포는 폴더째 zip).

⚠ 알려진 한계(코드는 안 고침, 이 스펙만으로는 못 푸는 문제):
- `easycad/fileio/symbol_library.py._library_path()`가 `__file__` 기준 3단계 상위
  (리포 루트)를 심볼 라이브러리 저장 위치로 계산한다 — 이 계산은 PyInstaller가 만드는
  `dist/EasyCAD/` 폴더 구조에서는 리포 루트가 아닌 엉뚱한 경로를 가리킨다("내 심볼"
  기능이 frozen 빌드에서 깨짐, 개발 중 `python run.py` 실행에는 영향 없음). 고치려면
  "frozen 빌드에서 심볼 라이브러리를 어디에 저장할지"(exe 옆? AppData?) 설계 결정이
  필요해 별도 deep-interview로 넘긴다 — 이 스펙은 패키징만 담당.
- 앱 아이콘(.ico)이 아직 없어 PyInstaller 기본 아이콘으로 빌드된다. `icon=` 파라미터에
  준비되면 경로를 채워 넣을 것.
"""
import os

block_cipher = None

a = Analysis(
    ['run.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        ('easycad/resources/icons', 'easycad/resources/icons'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # PySide6이 이 개발 환경에 별도로 설치돼 있어(어떤 의존성이 끌어왔는지는 확인 안 함) PyInstaller가
    # "Qt 바인딩 두 개 동시 수집 불가"로 빌드를 거부한다 — 앱은 PyQt6만 쓰므로 명시 제외.
    excludes=['PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EasyCAD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # run.pyw과 동일 — 콘솔 창 없이 뜬다
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EasyCAD',
)
