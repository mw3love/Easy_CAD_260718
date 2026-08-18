"""사용자 정의 심볼 팔레트 — 임의 선택(주로 DXF에서 가져온 심볼)을 앱 전역에 등록해
다른 도면에서도 재사용한다. 계획서 §8 항목8. 문서(.ecad)와 무관하게 QStandardPaths
AppData에 JSON으로 영구 저장(다크모드 등 QSettings 관례와 달리, 항목 수가 늘고
썸네일 PNG를 품는 구조라 레지스트리보다 파일이 적합).

deep-interview 2026-08-03 확정 스코프: 등록 대상=현재 선택 전부(1개 이상, 가져온 심볼
한정 아님) · 썸네일=실제 렌더 캡처 · 관리 기능=등록+삭제(이름변경은 스코프 밖 — 2026-08-18
실사용 피드백으로 심볼 한정 번복, `rename_symbol` 참조. 폴더 이름변경은 여전히 스코프 밖).
화살표의 지속연결 바인딩은 저장하지 않는다 — DXF 가져오기 산출물은 애초에 좌표만
있는 라인·경로라 바인딩이 없고, 위치 자체는 그대로 보존되므로 시각적 손실이 없다.

[신규기능, 2026-08-12 좌측 패널 아코디언 개편] 폴더 지원 추가 — 심볼 항목에 "folder" 필드
(없거나 None=미분류), 폴더 자체는 별도 목록(빈 폴더도 드롭 대상으로 남아야 하므로 심볼
필드만으론 존재를 못 담음). 관리 기능은 심볼과 같은 관례로 생성+삭제만(이름변경 스코프 밖).
폴더 삭제 시 소속 심볼은 미분류로 소급(심볼 자체는 보존).
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


def _load_raw() -> dict:
    path = _library_path()
    if not os.path.exists(path):
        return {"folders": [], "symbols": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"folders": [], "symbols": []}
    if not isinstance(data, dict):
        return {"folders": [], "symbols": []}
    return {"folders": data.get("folders", []), "symbols": data.get("symbols", [])}


def _save_raw(data: dict):
    with open(_library_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def load_library() -> list[dict]:
    return _load_raw()["symbols"]


def load_folders() -> list[str]:
    return _load_raw()["folders"]


def create_folder(name: str):
    name = name.strip()
    if not name:
        return
    data = _load_raw()
    if name not in data["folders"]:
        data["folders"].append(name)
        _save_raw(data)


def delete_folder(name: str):
    """폴더를 지우고, 소속 심볼은 미분류(folder=None)로 되돌린다(심볼 자체는 삭제하지 않음)."""
    data = _load_raw()
    if name not in data["folders"]:
        return
    data["folders"].remove(name)
    for e in data["symbols"]:
        if e.get("folder") == name:
            e["folder"] = None
    _save_raw(data)


def add_symbol(name: str, item_dicts: list[dict], thumb_b64: str, folder: str | None = None) -> dict:
    """새 항목을 등록하고 그 항목(id 포함)을 반환. folder 생략 시 미분류."""
    data = _load_raw()
    entry = {"id": uuid.uuid4().hex[:8], "name": name, "thumb": thumb_b64, "items": item_dicts,
              "folder": folder}
    data["symbols"].append(entry)
    _save_raw(data)
    return entry


def rename_symbol(symbol_id: str, new_name: str):
    """[실사용 피드백 2026-08-18] 심볼 이름을 바꾼다 — 등록 관례("이름변경 스코프 밖")를
    실사용 요청으로 뒤집음. 빈 이름은 무시(호출부가 우클릭 메뉴에서 확인)."""
    new_name = new_name.strip()
    if not new_name:
        return
    data = _load_raw()
    for e in data["symbols"]:
        if e.get("id") == symbol_id:
            e["name"] = new_name
            break
    else:
        return
    _save_raw(data)


def delete_symbol(symbol_id: str):
    data = _load_raw()
    data["symbols"] = [e for e in data["symbols"] if e.get("id") != symbol_id]
    _save_raw(data)


def move_symbol(symbol_id: str, folder: str | None):
    """심볼을 다른 폴더(또는 미분류=None)로 옮긴다 — 좌측 패널 드래그앤드롭이 호출."""
    data = _load_raw()
    for e in data["symbols"]:
        if e.get("id") == symbol_id:
            e["folder"] = folder
            break
    else:
        return
    _save_raw(data)
