# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 빌드 스펙 — 최종 검수 Phase 7(릴리스 준비), 2026-08-26.

빌드: `pyinstaller EasyCAD.spec` (repo 루트에서). 결과는 `dist/EasyCAD/EasyCAD.exe`
(onedir — PyQt6은 리소스가 많아 onefile은 시작이 느려짐, 배포는 폴더째 zip).

⚠ 알려진 한계(코드는 안 고침, 이 스펙만으로는 못 푸는 문제):
- (해결 2026-10-16, §8 항목43) "내 심볼"은 exe에서 `%APPDATA%/EasyCAD/EasyCAD/symbol_library.json`
  (`symbol_library._library_dir`), 아이콘 경로도 `_MEIPASS/easycad/resources/icons`로 바로잡음.
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
