"""사용 기록(2026-11-04 사용자 — 대회 기획서에 쓸 숫자: 몇 번·어떤 기능·크레딧 얼마).

데이터 폴더 `usage.json` 한 파일에 날짜별로 모은다 — 무엇을 물었는지(글)·누가(키·이름)는 남기지 않는다.
칠판은 이름 대신 짧은 지문(해시)만 남겨 「그날 쓰인 칠판 수」만 센다.

    {"days": {"2026-11-04": {"kinds": {"chat": [횟수, 크레딧 합, 실패], ...},
                             "boards": ["a1b2c3d4", ...],   # 그날 고치거나 AI를 쓴 칠판(지문)
                             "new": 3}},                     # 처음 온 사람(예시 칠판 사본 수)
     "seen": {"a1b2c3d4": "2026-11-04"}}                       # 칠판(지문)을 마지막으로 연 날 — 자동 정리용

크레딧은 서버가 답에 붙인 것(`credits` — 잔액 차이)만 더한다. 보통 대화 답은 크레딧을 안 재서 0으로 남는다(횟수만).
쓰기는 모아 두었다가 60초마다(또는 `flush`) — 부분 저장이 0.3초마다 와도 파일을 매번 쓰지 않게.

보기: python web/usage.py [데이터 폴더]   → 날짜별·기능별 표 + 정리 문서 발표용·읽기용 중 남긴 쪽(`report_styles`)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time

FILE = "usage.json"


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def board_mark(name: str) -> str:
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]


class Usage:
    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, FILE)
        self.lock = threading.Lock()
        self.dirty = False
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
            if not isinstance(self.data.get("days"), dict):
                raise ValueError
        except (OSError, ValueError, AttributeError):
            self.data = {"days": {}}

    def _day(self) -> dict:
        d = self.data["days"].setdefault(_today(), {})
        d.setdefault("kinds", {})
        d.setdefault("boards", [])
        d.setdefault("new", 0)
        return d

    def add(self, kind: str, credits=None, ok: bool = True, board: str = ""):
        """AI 일 하나 — kind = 대화 길(chat·search·image·…)이나 길목 이름(ocr·meeting·trace·stt)."""
        kind = (kind or "etc")[:24]
        with self.lock:
            d = self._day()
            row = d["kinds"].setdefault(kind, [0, 0.0, 0])
            row[0] += 1
            if isinstance(credits, (int, float)) and credits > 0:
                row[1] = round(row[1] + float(credits), 1)
            if not ok:
                row[2] += 1
            if board:
                self._touch(d, board)
            self.dirty = True

    def touch(self, board: str):
        """칠판을 고침(부분 저장·통째 저장) — 그날 쓰인 칠판 수만."""
        if not board:
            return
        with self.lock:
            if self._touch(self._day(), board):
                self.dirty = True

    @staticmethod
    def _touch(d: dict, board: str) -> bool:
        m = board_mark(board)
        if m in d["boards"]:
            return False
        d["boards"].append(m)
        return True

    def seen(self, board: str):
        """칠판을 연 날(지문 → 날짜) — 자동 정리(`cleanup.stale`)가 「오래 안 연 칠판」을 고를 때."""
        if not board:
            return
        m, day = board_mark(board), _today()
        with self.lock:
            seen = self.data.setdefault("seen", {})
            if seen.get(m) != day:
                seen[m] = day
                self.dirty = True

    def new_visit(self):
        with self.lock:
            self._day()["new"] += 1
            self.dirty = True

    def flush(self):
        with self.lock:
            if not self.dirty:
                return
            raw = json.dumps(self.data, ensure_ascii=False).encode("utf-8")
            self.dirty = False
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, self.path)

    def keep_flushing(self, every: float = 60.0):
        def loop():
            while True:
                time.sleep(every)
                try:
                    self.flush()
                except OSError as e:
                    sys.stderr.write("[사용 기록 저장 실패] %s\n" % e)
        threading.Thread(target=loop, daemon=True).start()


def summary(data: dict) -> str:
    """날짜별 한 줄 + 기능별 합계 — 기획서 숫자용."""
    days = data.get("days") or {}
    lines, total = [], {}
    for day in sorted(days):
        d = days[day]
        kinds = d.get("kinds") or {}
        n = sum(r[0] for r in kinds.values())
        cr = round(sum(r[1] for r in kinds.values()), 1)
        lines.append(f"{day}  AI {n}번 · 크레딧 {cr} · 칠판 {len(d.get('boards') or [])}개 · 처음 온 사람 {d.get('new', 0)}")
        for k, r in kinds.items():
            t = total.setdefault(k, [0, 0.0, 0])
            t[0] += r[0]
            t[1] = round(t[1] + r[1], 1)
            t[2] += r[2]
    if total:
        lines.append("")
        lines.append("기능별 합계(횟수 · 잰 크레딧 · 실패)")
        for k, r in sorted(total.items(), key=lambda kv: -kv[1][0]):
            lines.append(f"  {k:<10} {r[0]:>5}번 · {r[1]:>8} · 실패 {r[2]}")
    return "\n".join(lines) or "기록 없음"


def report_styles(folder: str) -> dict:
    """정리 문서 발표용·읽기용 중 칠판에 남긴 쪽 세기(2026-11-05 — 당분간 둘 다 만들어 써 보고 하나로 합칠지 정함).
    칠판 파일들의 문서 카드(`style`)를 같은 답(`chat_at`)끼리 묶어: 둘 다 남김 / 발표용만 / 읽기용만. 둘 다 지운 답은 안 보임(셀 수 없음)."""
    out = {"both": 0, "present": 0, "read": 0}
    try:
        names = [n for n in os.listdir(folder) if n.endswith(".ecad") and not n.endswith(".prev.ecad")]
    except OSError:
        return out
    for n in names:
        try:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                items = json.load(f).get("items") or []
        except (OSError, ValueError, AttributeError):
            continue
        by = {}
        for it in items:
            if isinstance(it, dict) and it.get("type") == "doc" and it.get("style") in ("present", "read"):
                by.setdefault(it.get("chat_at") or id(it), set()).add(it["style"])
        for st in by.values():
            out["both" if len(st) > 1 else next(iter(st))] += 1
    return out


if __name__ == "__main__":
    for s in (sys.stdout,):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    if len(sys.argv) > 1:
        folder = sys.argv[1]
    else:
        from server import default_data_dir
        folder = default_data_dir()
    try:
        with open(os.path.join(folder, FILE), encoding="utf-8") as f:
            print(summary(json.load(f)))
    except OSError:
        print("기록 없음 —", os.path.join(folder, FILE))
    r = report_styles(folder)
    print()
    print(f"정리 문서 칠판에 남긴 쪽(답 하나 기준): 둘 다 {r['both']} · 발표용만 {r['present']} · 읽기용만 {r['read']}")
