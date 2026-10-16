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
import sys
import uuid

_FILE_NAME = "symbol_library.json"

# easycad/fileio/symbol_library.py → 두 단계 위가 리포 루트.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _library_dir() -> str:
    """개발 실행은 리포의 `symbol_library/`(git으로 PC 간 동기화 — 사용자 요청 2026-08-20). [§8 항목43, 2026-10-16]
    exe(PyInstaller)는 그 PC의 앱 데이터(`%APPDATA%/EasyCAD/EasyCAD`, 자동 저장·크래시 로그와 같은 곳) — 리포 기준
    3단계 위는 exe 설치 폴더 안쪽이라 새 버전을 깔면 사라진다. exe는 빈 「내 심볼」로 시작한다(리포 파일엔 시험용
    폴더가 섞여 있어 나눠 줄 기본 세트로 싣지 않음)."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "EasyCAD", "EasyCAD")
    return os.path.join(_REPO_ROOT, "symbol_library")


def _library_path() -> str:
    d = _library_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, _FILE_NAME)


# [실사용 피드백 2026-10-11] 미분류 폐지 — 심볼은 늘 어느 폴더엔가 들어간다. 폴더를 안 정하고 등록하면
# 마지막에 쓴 폴더 → 첫 폴더 → (폴더가 하나도 없으면) 이 이름으로 새로 만든 폴더 순으로 들어간다.
DEFAULT_FOLDER = "내 심볼"

# [실사용 피드백 2026-10-11] 즐겨찾기 = 사용자가 직접 넣고 빼는 tool_key 목록(순서 그대로, 기본 도형
# "rect"/"sym:decision"과 내 심볼 "customsym:<id>"를 함께). 옛 「자주 쓰는 것」(최근 8개 자동)과 심볼마다
# 붙던 "favorite" 표식을 이 목록 하나로 합쳤다. 목록이 없는 파일은 이 기본 4개 + 옛 표식 심볼로 시작.
DEFAULT_FAVORITES = ["rect", "ellipse", "sym:decision", "sym:terminal"]


def _default_folder(data: dict) -> str:
    """폴더를 안 정한 등록·옛 미분류 심볼이 들어갈 폴더 — 없으면 `DEFAULT_FOLDER`를 만들어서."""
    last = data.get("last_folder")
    if last in data["folders"]:
        return last
    if data["folders"]:
        return data["folders"][0]
    data["folders"].append(DEFAULT_FOLDER)
    return DEFAULT_FOLDER


def _migrate(data: dict) -> bool:
    """옛 파일을 지금 규칙으로 — 미분류(folder 없음) 심볼은 기본 폴더로, "favorite" 표식은 즐겨찾기 목록으로.
    바뀐 게 있으면 True(부르는 쪽이 한 번 저장해 다음부터는 그냥 읽히게)."""
    changed = False
    if "favorites" not in data:
        data["favorites"] = list(DEFAULT_FAVORITES) + [
            f"customsym:{e['id']}" for e in data["symbols"] if e.get("favorite") and e.get("id")]
        changed = True
    for e in data["symbols"]:
        if "favorite" in e:
            del e["favorite"]
            changed = True
        if not e.get("folder"):
            # 옛 미분류는 남의 폴더에 섞지 않고 「내 심볼」 폴더로 모은다(없으면 만든다)
            if DEFAULT_FOLDER not in data["folders"]:
                data["folders"].append(DEFAULT_FOLDER)
            e["folder"] = DEFAULT_FOLDER
            changed = True
    return changed


def _load_raw() -> dict:
    path = _library_path()
    if not os.path.exists(path):
        return {"folders": [], "symbols": [], "favorites": list(DEFAULT_FAVORITES)}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"folders": [], "symbols": [], "favorites": list(DEFAULT_FAVORITES)}
    if not isinstance(data, dict):
        return {"folders": [], "symbols": [], "favorites": list(DEFAULT_FAVORITES)}
    raw = {"folders": data.get("folders", []), "symbols": data.get("symbols", [])}
    if isinstance(data.get("folder_colors"), dict):   # [2026-10-11] 폴더 색 칩 — 없던 파일엔 키가 없다
        raw["folder_colors"] = data["folder_colors"]
    if isinstance(data.get("section_colors"), dict):   # 즐겨찾기·기본 도형 칸 색(폴더가 아니라 따로)
        raw["section_colors"] = data["section_colors"]
    if isinstance(data.get("favorites"), list):
        raw["favorites"] = data["favorites"]
    if isinstance(data.get("last_folder"), str):
        raw["last_folder"] = data["last_folder"]
    if _migrate(raw):
        try:
            _save_raw(raw)
        except OSError:
            pass   # 읽기 전용이어도 화면엔 옮긴 결과로 보인다 — 다음 저장 때 같이 써진다
    return raw


def _save_raw(data: dict):
    """[최종 검수 Phase 4, 2026-08-26] 임시파일에 쓴 뒤 `os.replace`로 원자적 교체 —
    예전엔 대상 파일을 직접 열어 썼는데, 그 도중 크래시(이 프로젝트가 exit 127 네이티브
    크래시를 반복 겪은 이력 — `docs/perf_group_drag_200.md`·최종 검수 Phase 1 참조)가
    나면 JSON이 반쯤 쓰인 채 깨지고, 다음 `_load_raw`가 파싱 실패를 조용히 "빈 라이브러리"로
    삼켜(아래 `except (OSError, ValueError)`) 그 직후 심볼을 하나만 추가해도 기존 전체가
    영구 소실될 수 있었다(재현은 안 했지만 원리적으로 가능한 조용한 데이터 손실 — 왕복
    무손실성 점검 중 발견). `os.replace`는 같은 볼륨 안에서 POSIX·Windows 둘 다 원자적이라
    (표준 라이브러리 보증) 쓰기 도중 죽어도 원본 파일은 항상 이전 완성본 그대로 남는다."""
    path = _library_path()
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        # 실패한 임시파일을 남기지 않는다 — 대상 `path`는 이 지점에서 건드리지 않았으므로
        # 항상 이전 완성본 그대로다(프로세스 자체가 죽는 경우는 이 except가 안 돌지만,
        # 그때도 대상 path는 여전히 무사하다 — 유실 위험은 오직 tmp가 지저분해지는 것뿐).
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def load_library() -> list[dict]:
    return _load_raw()["symbols"]


def load_folders() -> list[str]:
    return _load_raw()["folders"]


def load_favorites() -> list[str]:
    """즐겨찾기 tool_key 목록(넣은 순서)."""
    return list(_load_raw().get("favorites", []))


def is_favorite(key: str) -> bool:
    return key in _load_raw().get("favorites", [])


def toggle_favorite_key(key: str):
    """즐겨찾기에 넣기/빼기 — 넣을 때는 맨 뒤에."""
    data = _load_raw()
    favs = data.setdefault("favorites", [])
    if key in favs:
        favs.remove(key)
    else:
        favs.append(key)
    _save_raw(data)


def preferred_folder() -> str | None:
    """폴더를 고르는 창의 처음 값 — 마지막에 쓴 폴더, 없으면 첫 폴더, 폴더가 없으면 None."""
    data = _load_raw()
    last = data.get("last_folder")
    if last in data["folders"]:
        return last
    return data["folders"][0] if data["folders"] else None


def load_folder_colors() -> dict[str, str]:
    """[패널 통일 2라운드 2026-10-11] 폴더 이름 → 색(#rrggbb). 사용자가 ⋯ 메뉴로 고른 것만 들어 있다
    (안 고른 폴더는 화면 쪽이 순서대로 기본 색을 준다). 이름이 곧 폴더 식별자라 이름변경·삭제가 함께 고친다."""
    return dict(_load_raw().get("folder_colors", {}))


def set_folder_color(name: str, color: str | None):
    data = _load_raw()
    if name not in data["folders"]:
        return
    colors = data.setdefault("folder_colors", {})
    if color:
        colors[name] = color
    else:
        colors.pop(name, None)
    _save_raw(data)


SECTION_KEYS = ("favorites", "basic")   # 「즐겨찾기」·「기본 도형」 칸


def load_section_colors() -> dict[str, str]:
    """[실사용 피드백 2026-10-11] 「즐겨찾기」·「기본 도형」 칸 색 — 폴더 색과 같은 ⋯ 메뉴로 고른 것만 들어 있다.
    폴더 색(`folder_colors`)과 저장소를 나눈 건 같은 이름의 사용자 폴더(예: 「즐겨찾기」 폴더)와 안 섞이게."""
    return {k: v for k, v in _load_raw().get("section_colors", {}).items() if k in SECTION_KEYS}


def set_section_color(key: str, color: str | None):
    if key not in SECTION_KEYS:
        return
    data = _load_raw()
    colors = data.setdefault("section_colors", {})
    if color:
        colors[key] = color
    else:
        colors.pop(key, None)
    _save_raw(data)


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
    data.get("folder_colors", {}).pop(name, None)
    gone = {f"customsym:{e.get('id')}" for e in data["symbols"] if e.get("folder") == name}
    data["symbols"] = [e for e in data["symbols"] if e.get("folder") != name]
    data["favorites"] = [k for k in data.get("favorites", []) if k not in gone]
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
    colors = data.get("folder_colors", {})
    if old_name in colors:
        colors[new_name] = colors.pop(old_name)
    for e in data["symbols"]:
        if e.get("folder") == old_name:
            e["folder"] = new_name
    if data.get("last_folder") == old_name:
        data["last_folder"] = new_name
    _save_raw(data)


def add_symbol(name: str, item_dicts: list[dict], thumb_b64: str, folder: str | None = None) -> dict:
    """새 항목을 등록하고 그 항목(id 포함)을 반환. folder 생략 시 `_default_folder`(미분류는 없다)."""
    data = _load_raw()
    if folder and folder not in data["folders"]:
        data["folders"].append(folder)
    folder = folder or _default_folder(data)
    data["last_folder"] = folder
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


def toggle_favorite(symbol_id: str):
    """[신규기능, 2026-08-20 → 2026-10-11 즐겨찾기 목록으로 통합] 내 심볼 하나의 즐겨찾기 넣기/빼기."""
    if any(e.get("id") == symbol_id for e in load_library()):
        toggle_favorite_key(f"customsym:{symbol_id}")


def delete_symbol(symbol_id: str):
    data = _load_raw()
    data["symbols"] = [e for e in data["symbols"] if e.get("id") != symbol_id]
    data["favorites"] = [k for k in data.get("favorites", []) if k != f"customsym:{symbol_id}"]
    _save_raw(data)


def move_symbol(symbol_id: str, folder: str | None):
    """심볼을 다른 폴더로 옮긴다 — 좌측 패널 드래그앤드롭이 호출. [2026-10-11] 미분류가 없어져
    없는 폴더(None 포함)로는 안 옮긴다."""
    data = _load_raw()
    if folder not in data["folders"]:
        return
    for e in data["symbols"]:
        if e.get("id") == symbol_id:
            e["folder"] = folder
            break
    else:
        return
    _save_raw(data)
