"""칠판 자동 정리(2026-11-04 사용자 — 「모두가 무제한으로 서버에 저장할 수는 없다」).

로그인이 없어(칠판 주소 = 열쇠) 사람마다 칠판 개수를 셀 수 없으므로 개수 대신 기간으로 정리한다:
- 예시 칠판 사본을 받기만 하고 한 번도 안 고침(문서 `example_rev` == `rev`) + 7일 동안 안 열림 → 휴지통
- 그 밖의 칠판: 90일 동안 아무도 안 열고 안 고침 → 휴지통(`server._delete_board` — 지운 이름은 `deleted.json`에 남아 그 주소는 「지워짐」)
- 휴지통(`trash/<이름>-<때>/`)은 30일 뒤 완전히 지움

「열림」 = 서버 `Usage.seen`(칠판 문서를 받아 간 날, 지문만), 「고침」 = 칠판 파일들의 수정 시각. 계산만 — 옮기기는 서버가.
"""
from __future__ import annotations

import json
import os
import shutil
import time

EXAMPLE_DAYS, IDLE_DAYS, TRASH_DAYS = 7, 90, 30
DAY = 86400


def _last_used(data_dir: str, name: str, files: list, seen_day: str) -> float:
    t = 0.0
    for fn in files:
        if fn == name or fn.startswith(name + "."):
            try:
                t = max(t, os.path.getmtime(os.path.join(data_dir, fn)))
            except OSError:
                pass
    if seen_day:
        try:
            t = max(t, time.mktime(time.strptime(seen_day, "%Y-%m-%d")) + DAY - 1)   # 그날 끝까지 열린 것으로
        except ValueError:
            pass
    return t


def stale(data_dir: str, seen: dict, mark, now: float | None = None, idle_days: int = IDLE_DAYS, example_days: int = EXAMPLE_DAYS) -> list:
    """지울 칠판 [(이름, "example" | "idle")] — seen = {지문: "YYYY-MM-DD"}, mark = 이름 → 지문."""
    now = time.time() if now is None else now
    try:
        files = os.listdir(data_dir)
    except OSError:
        return []
    out = []
    for fn in files:
        if not fn.endswith(".ecad") or fn.endswith(".prev.ecad"):
            continue
        name = fn[:-5]
        used = _last_used(data_dir, name, files, seen.get(mark(name), ""))
        idle = (now - used) / DAY
        try:
            with open(os.path.join(data_dir, fn), "rb") as f:
                doc = json.loads(f.read())
        except (OSError, ValueError):
            continue
        untouched = isinstance(doc, dict) and doc.get("example") and doc.get("example_rev") is not None and doc.get("example_rev") == doc.get("rev")
        if untouched and idle >= example_days:
            out.append((name, "example"))
        elif idle >= idle_days:
            out.append((name, "idle"))
    return out


def old_trash(data_dir: str, now: float | None = None, days: int = TRASH_DAYS) -> list:
    """휴지통에서 `days`일 지난 폴더 경로들(이름 끝 `-YYYYmmdd-HHMMSS`)."""
    now = time.time() if now is None else now
    trash = os.path.join(data_dir, "trash")
    out = []
    try:
        names = os.listdir(trash)
    except OSError:
        return []
    for fn in names:
        p = os.path.join(trash, fn)
        if not os.path.isdir(p) or len(fn) < 16:
            continue
        try:
            t = time.mktime(time.strptime(fn[-15:], "%Y%m%d-%H%M%S"))
        except ValueError:
            continue
        if (now - t) / DAY >= days:
            out.append(p)
    return out


def purge(paths: list) -> int:
    n = 0
    for p in paths:
        try:
            shutil.rmtree(p)
            n += 1
        except OSError:
            pass
    return n
