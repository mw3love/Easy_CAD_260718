"""사용자 정의 심볼 팔레트 — 임의 선택(주로 DXF에서 가져온 심볼)을 앱 전역에 등록해
다른 도면에서도 재사용한다. 계획서 §8 항목8. 문서(.ecad)와 무관하게 QStandardPaths
AppData에 JSON으로 영구 저장(다크모드 등 QSettings 관례와 달리, 항목 수가 늘고
썸네일 PNG를 품는 구조라 레지스트리보다 파일이 적합).

deep-interview 2026-08-03 확정 스코프: 등록 대상=현재 선택 전부(1개 이상, 가져온 심볼
한정 아님) · 썸네일=실제 렌더 캡처 · 관리 기능=등록+삭제(이름변경은 스코프 밖).
화살표의 지속연결 바인딩은 저장하지 않는다 — DXF 가져오기 산출물은 애초에 좌표만
있는 라인·경로라 바인딩이 없고, 위치 자체는 그대로 보존되므로 시각적 손실이 없다.
"""
import json
import os
import uuid

from PyQt6.QtCore import QStandardPaths

_FILE_NAME = "symbol_library.json"


def _library_path() -> str:
    d = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, _FILE_NAME)


def load_library() -> list[dict]:
    path = _library_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return data.get("symbols", []) if isinstance(data, dict) else []


def _save(entries: list[dict]):
    with open(_library_path(), "w", encoding="utf-8") as f:
        json.dump({"symbols": entries}, f, ensure_ascii=False)


def add_symbol(name: str, item_dicts: list[dict], thumb_b64: str) -> dict:
    """새 항목을 등록하고 그 항목(id 포함)을 반환."""
    entries = load_library()
    entry = {"id": uuid.uuid4().hex[:8], "name": name, "thumb": thumb_b64, "items": item_dicts}
    entries.append(entry)
    _save(entries)
    return entry


def delete_symbol(symbol_id: str):
    _save([e for e in load_library() if e.get("id") != symbol_id])
