"""앱 설정(QSettings)을 여는 한 곳.

2026-10-03 — 앱·테스트 곳곳이 `QSettings("EasyCAD", "EasyCAD")`를 직접 열어, pytest와 시험
스크립트가 실사용자 설정을 바꾸고 있었다(최근 색 목록 삭제, "DXF 안내 봤음" 표시 등 — 2026-08-20
AI 키 소실 사고와 같은 종류). 환경변수 `EASYCAD_SETTINGS_ORG`가 있으면 그 이름의 별도 저장소를
쓴다(tests/conftest.py·_shared.py가 "EasyCAD-pytest"로 설정). 실사용(환경변수 없음)은 예전과 같은
"EasyCAD" 저장소 그대로라 동작 변화가 없다.
"""
import os

from PyQt6.QtCore import QSettings

ORG_ENV = "EASYCAD_SETTINGS_ORG"
APP_NAME = "EasyCAD"


def settings_org() -> str:
    return os.environ.get(ORG_ENV, "EasyCAD")


def app_settings() -> QSettings:
    return QSettings(settings_org(), APP_NAME)
