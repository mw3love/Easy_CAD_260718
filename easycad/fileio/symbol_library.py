"""사용자 정의 심볼 팔레트 — 임의 선택(주로 DXF에서 가져온 심볼)을 앱 전역에 등록해
다른 도면에서도 재사용한다. 계획서 §8 항목8. 문서(.ecad)와 무관하게 JSON으로 영구
저장(다크모드 등 QSettings 관례와 달리, 항목 수가 늘고 썸네일 PNG를 품는 구조라
레지스트리보다 파일이 적합).

[2026-08-20 실사용 피드백] 저장 위치를 OS `QStandardPaths.AppDataLocation`에서
리포 루트 하위 `symbol_library/symbol_library.json`으로 변경 — 사용자가 여러 PC를
git으로 상시 동기화하는 습관이 있어(`.claude/handoff/`와 같은 이유, 2026-08-18 결정),
심볼 라이브러리도 git으로 PC 간 따라가길 원함. 프로젝트의 기존 "작업 산출물은 리포에
안 들어간다" 원칙(루트 `.ecad`·작업 사진 등)과는 반대 방향인데, 저 원칙은 "커밋할
가치가 없는 대용량/개인 자료"가 대상이고 심볼 라이브러리는 사용자가 직접 쌓아 재사용
하려는 구조화된 데이터라 예외로 판단(사용자 명시 요청).

deep-interview 2026-08-03 확정 스코프: 등록 대상=현재 선택 전부(1개 이상, 가져온 심볼
한정 아님) · 썸네일=실제 렌더 캡처 · 관리 기능=등록+삭제(이름변경은 스코프 밖 — 2026-08-18
실사용 피드백으로 심볼 한정 번복, `rename_symbol` 참조. 폴더 이름변경은 여전히 스코프 밖).
화살표의 지속연결 바인딩은 저장하지 않는다 — DXF 가져오기 산출물은 애초에 좌표만
있는 라인·경로라 바인딩이 없고, 위치 자체는 그대로 보존되므로 시각적 손실이 없다.

[신규기능, 2026-08-12 좌측 패널 아코디언 개편] 폴더 지원 추가 — 심볼 항목에 "folder" 필드
(없거나 None=미분류), 폴더 자체는 별도 목록(빈 폴더도 드롭 대상으로 남아야 하므로 심볼
필드만으론 존재를 못 담음). [2026-08-19 정책 전환] 폴더 삭제 시 소속 심볼도 함께 삭제
(도입 당시엔 미분류로 소급 보존했으나, 실사용 피드백으로 "지우기 전에 옮겨두는" 루틴으로
확정 — `delete_folder` 참조). 폴더 이름변경은 도입 당시 스코프 밖이었으나, 심볼 이름변경과
마찬가지로 실사용 피드백(2026-08-19)으로 뒤집어 `rename_folder` 추가 — 이름 자체가 심볼의
"folder" 필드 값과 같은 식별자라 이름을 바꾸면 소속 심볼 전체의 참조도 함께 갱신해야 한다
(심볼 이름변경은 id로 식별해 이런 캐스케이드가 불필요했던 것과 다른 점).

[신규기능, 2026-08-20, deep-interview] 즐겨찾기 추가 — 심볼 항목에 "favorite" 불리언 필드
(folder와 같은 패턴). 이중표시(원래 폴더+즐겨찾기 섹션 둘 다에 노출) 확정이라 별도 참조
목록이 없고, 폴더 필드처럼 원본 삭제·폴더 완전삭제 시 자동으로 함께 정리된다.
"""
import json
import os
import uuid

_FILE_NAME = "symbol_library.json"

# easycad/fileio/symbol_library.py → 두 단계 위가 리포 루트.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _library_path() -> str:
    d = os.path.join(_REPO_ROOT, "symbol_library")
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
    """[2026-08-19 실사용 피드백으로 정책 전환] 폴더와 그 안의 심볼을 전부 지운다 — 도입
    당시엔 소속 심볼을 미분류로 옮겨 보존했으나(id 기반 이력은 `docs/history/2026-08.md`
    2026-08-12 항목), 미분류의 역할이 애매해지며(동시 실사용 피드백) "폴더 삭제 = 안의
    것도 함께 삭제, 남기고 싶으면 지우기 전에 직접 다른 폴더로 옮겨두는" 루틴으로 확정.
    보존이 필요 없으면 `move_symbol`로 먼저 옮겨두는 게 호출부 쪽 책임이다."""
    data = _load_raw()
    if name not in data["folders"]:
        return
    data["folders"].remove(name)
    data["symbols"] = [e for e in data["symbols"] if e.get("folder") != name]
    _save_raw(data)


def rename_folder(old_name: str, new_name: str):
    """[실사용 피드백 2026-08-19] 폴더 이름을 바꾼다 — 폴더 목록의 이름 자체와, 그 이름을
    "folder" 값으로 참조 중인 모든 심볼을 함께 갱신(캐스케이드, 심볼 이름변경엔 없던 단계 —
    심볼은 id로 식별되지만 폴더는 이름이 곧 식별자라서). 빈 새 이름·변화 없음·존재하지 않는
    old_name·이미 있는 new_name은 무시(호출부가 확인)."""
    new_name = new_name.strip()
    if not new_name or new_name == old_name:
        return
    data = _load_raw()
    if old_name not in data["folders"] or new_name in data["folders"]:
        return
    data["folders"][data["folders"].index(old_name)] = new_name
    for e in data["symbols"]:
        if e.get("folder") == old_name:
            e["folder"] = new_name
    _save_raw(data)


def add_symbol(name: str, item_dicts: list[dict], thumb_b64: str, folder: str | None = None) -> dict:
    """새 항목을 등록하고 그 항목(id 포함)을 반환. folder 생략 시 미분류."""
    data = _load_raw()
    entry = {"id": uuid.uuid4().hex[:8], "name": name, "thumb": thumb_b64, "items": item_dicts,
              "folder": folder, "favorite": False}
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


def toggle_favorite(symbol_id: str):
    """[신규기능, 2026-08-20, deep-interview] 즐겨찾기 on/off를 뒤집는다 — `folder`와 같이
    심볼 엔트리 자체의 필드라 원본 삭제·폴더 완전삭제 시 자동으로 함께 사라진다(별도 정리
    코드 불필요). 이중표시(원래 폴더+즐겨찾기 섹션 둘 다에 노출)라 별도 목록 동기화도 없다."""
    data = _load_raw()
    for e in data["symbols"]:
        if e.get("id") == symbol_id:
            e["favorite"] = not e.get("favorite", False)
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
