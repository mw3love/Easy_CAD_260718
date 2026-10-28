"""공동작업 1단계(§8 항목61 ⓕ, 2026-10-18 사용자 결정 — 방송 준비용 소규모) — 서버(`web/server.py`)가 부르는 순수 계산.

- 도형 이름표 `uid`: 여러 브라우저가 같은 도형을 같은 이름으로 알아보게 .ecad에 저장(없으면 서버가 처음 열 때 붙임).
- 화살표 연결 `bind1`/`bind2`는 .ecad에선 「목록 순번」, 합치는 동안엔 상대 uid — 순번은 사람마다 달라서 그대로 합치면 엉뚱한 도형에 붙는다.
- 부분 저장(patch) = { base, upsert: [uid 꼴 도형], delete: [uid], meta: {layers 등 items 밖 칸} } → 도형 단위로 덮어씀(나중 것이 이김),
  서로 다른 도형을 고치면 둘 다 남는다. 고칠 때마다 판 번호 `rev` +1 — 브라우저는 「rev 다음 것 있나」로 받아 온다.
- 공용 비밀번호(사람별 계정 아님) → 편집 열쇠(쿠키), 게시 링크(로그인 없이 보기·발표만), 접속자 이름.
- 팀별 칠판(§8 항목67, 2026-10-27): `teams.json` — 팀마다 비밀번호·KAIROS 키·칠판(`Teams`).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import threading
import time

BIND_KEYS = ("bind1", "bind2")


def ensure_uids(doc: dict) -> bool:
    """uid 없는(또는 겹친) 도형에 새 uid — 바뀌었으면 True(그때 저장)."""
    seen, changed = set(), False
    for it in doc.get("items") or []:
        u = it.get("uid")
        if not isinstance(u, str) or not u or u in seen:
            u = "s" + secrets.token_hex(6)
            it["uid"] = u
            changed = True
        seen.add(u)
    return changed


def to_uid_form(items: list) -> list:
    """.ecad 도형(연결 = 순번) → 합치기용(연결 = 상대 uid)."""
    uids = [it.get("uid") for it in items]
    out = []
    for it in items:
        o = dict(it)
        for k in BIND_KEYS:
            j = o.get(k)
            if isinstance(j, int) and 0 <= j < len(uids):
                o[k] = uids[j]
        out.append(o)
    return out


def to_index_form(items: list) -> list:
    """합치기용(연결 = uid) → .ecad(연결 = 순번). 상대가 없어졌으면 끊긴 끝(웹 `toEcad`·데스크톱과 같은 규칙)."""
    index = {it.get("uid"): i for i, it in enumerate(items)}
    out = []
    for it in items:
        o = dict(it)
        for k in BIND_KEYS:
            ref = o.get(k)
            if isinstance(ref, str):
                j = index.get(ref)
                if j is None:
                    if not (o.get(k + "_group") and o.get(k + "_pt")):
                        o[k + "_pt"] = None
                        o[k + "_group"] = None
                    o[k] = None
                else:
                    o[k] = j
        out.append(o)
    return out


def apply_patch(doc: dict, patch: dict) -> dict:
    """문서(.ecad 꼴)에 부분 저장을 얹은 새 문서 — 도형 단위 덮어쓰기, rev +1."""
    items = to_uid_form(doc.get("items") or [])
    pos = {it.get("uid"): i for i, it in enumerate(items)}
    for up in patch.get("upsert") or []:
        u = up.get("uid")
        if not u:
            continue
        if u in pos:
            items[pos[u]] = up
        else:
            pos[u] = len(items)
            items.append(up)
    dels = set(patch.get("delete") or [])
    if dels:
        items = [it for it in items if it.get("uid") not in dels]
    out = {k: v for k, v in doc.items() if k != "items"}
    for k, v in (patch.get("meta") or {}).items():
        if k not in ("items", "rev", "format"):
            out[k] = v
    out["items"] = to_index_form(items)
    out["rev"] = int(doc.get("rev") or 0) + 1
    return out


# ── 공용 비밀번호 → 편집 열쇠(쿠키) ──
def edit_key(password: str) -> str:
    """비밀번호에서 나온 열쇠 — 비밀번호를 바꾸면 열쇠도 바뀌어 모두 다시 들어와야 함(사람별로 빼는 건 안 됨 — 사용자가 고른 단순함)."""
    return hashlib.sha256(("magic-board|" + password).encode("utf-8")).hexdigest()[:40]


def cookie_value(header: str | None, name: str = "mb_key") -> str:
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


# ── 접속자(이름만, 5초 안에 신호 보낸 사람) ──
class Presence:
    # 5초(2026-10-27 — 15 → 5): 화면은 1초마다 신호. 「나감」 신호가 안 오는 경우(시크릿 창 닫기 실측·휴대폰 다른 앱·노트북 덮기)에 이름이 15초 남았음
    def __init__(self, ttl: float = 5.0):
        self.ttl, self.boards = ttl, {}

    def ping(self, board: str, client: str, name: str, now: float | None = None, sel=None, edit: str = "") -> list:
        """접속 신호 → 지금 접속한 이름들. sel·edit = 이 사람이 고른 도형·고치는 도형 uid(2026-10-19 — 「누가 어디를 고치는지」, `others`로 읽음)."""
        now = time.time() if now is None else now
        b = self.boards.setdefault(board, {})
        if client:
            b[client] = ((name or "이름 없음")[:30], now, [str(x)[:64] for x in (sel or [])][:200], str(edit or "")[:64])
        for c in [c for c, v in b.items() if now - v[1] > self.ttl]:
            del b[c]
        return sorted({v[0] for v in b.values()})

    def people(self, board: str, now: float | None = None) -> list:
        """지금 접속자 [{ id, name }] — 칠판 판 줄마다 동그라미(2026-10-28, 신호를 보내지 않고 읽기만)"""
        now = time.time() if now is None else now
        return [{"id": c, "name": v[0]} for c, v in sorted(self.boards.get(board, {}).items()) if now - v[1] <= self.ttl]

    def leave(self, board: str, client: str) -> None:
        """창을 닫음 = 바로 뺌(2026-10-26 실검증 — ttl만 기다리면 이름이 20초쯤 남았음)"""
        self.boards.get(board, {}).pop(client, None)

    def others(self, board: str, client: str) -> list:
        """나를 뺀 접속자 [{ id, name, sel, edit }] — 화면에 그 사람 색 테두리·이름표"""
        return [{"id": c, "name": v[0], "sel": v[2], "edit": v[3]} for c, v in sorted(self.boards.get(board, {}).items()) if c != client]


# ── 대화 기록 합치기(2026-10-26 점검 — 두 창이 같은 칠판에 각자 물으면 나중 저장이 앞 창 대화를 통째로 덮었음) ──
# 기록 `<칠판>.chat.json` = { rev, messages: 지금 대화, past: [{ at, title, messages }] }. 브라우저는 읽은 판 번호를 `base`로 보내고,
# 서버 판이 그사이 바뀌었으면(다른 창이 저장했거나·못 읽은 채 저장) 새 기록 어디에도 없는 앞 메시지를 「지난 대화」로 옮겨 둔다(지우지 않음).
# 같은 메시지 = 역할 + 시각(`at`, 밀리초) — 고른 표시·붙임 같은 칸은 바뀌어도 같은 메시지.

def _msg_key(m) -> tuple | None:
    return (m.get("role"), m.get("at")) if isinstance(m, dict) and m.get("at") is not None else None


def _convs(log: dict) -> list:
    """지금 대화 + 지난 대화들 — [(제목 또는 None, 메시지 목록)]"""
    out = [(None, [m for m in log.get("messages") or [] if isinstance(m, dict)])]
    for p in log.get("past") or []:
        if isinstance(p, dict):
            out.append((p.get("title"), [m for m in p.get("messages") or [] if isinstance(m, dict)]))
    return out


def merge_chatlog(old: dict | None, new: dict) -> tuple[dict, int]:
    """저장할 기록 + 옮겨 둔 메시지 수. 판이 맞으면(아무도 그사이 안 씀) 받은 그대로 — 고쳐 묻기·다시 만들기로 지운 것은 지운 대로."""
    base = new.get("base")
    new = {k: v for k, v in new.items() if k != "base"}
    rev = int((old or {}).get("rev") or 0)
    new["rev"] = rev + 1
    if not old or base == rev:
        return new, 0
    have = {_msg_key(m) for _, ms in _convs(new) for m in ms} - {None}
    past, moved = list(new.get("past") or []), 0
    for title, ms in _convs(old):
        lost = [m for m in ms if _msg_key(m) not in have and _msg_key(m) is not None]
        if not lost:
            continue
        moved += len(lost)
        keys = {_msg_key(m) for m in ms}
        hit = next((p for p in past if isinstance(p, dict) and keys & {_msg_key(m) for m in p.get("messages") or []}), None)
        if hit is not None:   # 이미 옮겨 둔 같은 대화 — 늘어난 만큼 이어 붙임(조각조각 안 늘게)
            extra = [m for m in hit.get("messages") or [] if _msg_key(m) not in keys]
            hit["messages"] = sorted(ms + extra, key=lambda m: m.get("at") or 0)
            continue
        first = next((m for m in ms if m.get("role") == "user"), None) or ms[0]
        head = str(first.get("content") or "").split("\n")[0][:40]
        past.insert(0, {"at": ms[0].get("at") or 0, "title": title or ("다른 창 · " + head), "messages": ms})
        have |= keys
    new["past"] = past
    return new, moved


# ── 팀별 칠판(§8 항목67, 2026-10-27) — 데이터 폴더 `teams.json` 한 파일. 없으면 지금과 똑같이(공용 비밀번호 하나) ──
# 파일 = [{"name": "A팀", "password": "…", "key": "KAIROS 키(없으면 서버 키)", "base": "그 키의 게이트웨이 주소(다른 계정일 때만)", "boards": ["칠판", …]}]. 팀 = 비밀번호 하나 + 키 하나 + 칠판 여러 개.
# 팀 열쇠로는 그 팀 `boards`와 「아직 아무도 안 쓴 이름」만 — 처음 저장하면 그 팀 `boards`에 더함. 팀 없는 옛 칠판은 관리자(`edit_password.txt`)만.
# 칠판 이름은 서버 전체에서 하나(게시·초대·접속자 표가 이름으로 찾음). ⚠ 윈도 파일 이름은 대소문자를 안 가려 이름 비교는 casefold
# (「Main」을 새 이름으로 받으면 관리자 칠판 main.ecad를 덮어씀).
TEAM_NAME_MAX = 30


def team_key(team: dict) -> str:
    """팀 열쇠(쿠키) — 이름 + 비밀번호에서. 관리자 열쇠(`edit_key(비밀번호)`)와 섞이지 않게 앞말을 붙임."""
    return edit_key("team|%s|%s" % (team["name"], team["password"]))


def _same(a: str, b: str) -> bool:
    """같은 글인가(걸린 시간으로 안 새게) — 한글 비밀번호도(`compare_digest`는 글이면 ASCII만 받음)"""
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def board_files_exist(data_dir: str, name: str) -> bool:
    """이 이름의 칠판 파일(`<이름>.ecad`·`.chat.json`·`.img/`·`.pdf/` …)이 하나라도 있나 — 있으면 「아직 아무도 안 쓴 이름」이 아님."""
    head = name.casefold() + "."
    try:
        return any(fn.casefold().startswith(head) for fn in os.listdir(data_dir))
    except OSError:
        return False


class Teams:
    """`teams.json` — 고칠 때마다 다시 읽음(서버를 안 꺼도 팀을 더하게). 깨진 파일이면 팀 로그인은 막고(`broken`) 잠금은 유지 —
    파일이 깨졌다고 「비밀번호 없음 = 누구나」로 열리면 안 됨(Funnel = 인터넷 전체)."""
    _cache: dict = {}
    _cache_lock = threading.Lock()

    @classmethod
    def at(cls, data_dir: str) -> "Teams":
        path = os.path.join(data_dir, "teams.json")
        with cls._cache_lock:
            t = cls._cache.get(path)
            if t is None:
                t = cls._cache[path] = cls(path)
        t._reload()
        return t

    def __init__(self, path: str):
        self.path, self.lock = path, threading.Lock()
        self._sig, self.teams, self.exists, self.broken = None, [], False, False

    def _reload(self):
        try:
            st = os.stat(self.path)
        except OSError:
            self._sig, self.teams, self.exists, self.broken = None, [], False, False
            return
        sig = (st.st_mtime_ns, st.st_size)
        if sig == self._sig:
            return
        with self.lock:
            self._sig, self.exists = sig, True
            try:
                with open(self.path, encoding="utf-8-sig") as f:
                    raw = json.load(f)
            except (OSError, ValueError) as e:
                sys.stderr.write("[팀] teams.json을 못 읽어요 — 팀 로그인 막힘(관리자만): %s\n" % e)
                self.teams, self.broken = [], True
                return
            self.teams, self.broken = self._clean(raw), False

    @staticmethod
    def _clean(raw) -> list:
        """맞는 칸만 — 이름(1~30자, `|` 없음)·비밀번호 필수, 같은 이름·같은 비밀번호·남의 칠판은 앞 팀이 가짐(알림)"""
        out, names, pws, owned = [], set(), set(), set()
        for i, t in enumerate(raw if isinstance(raw, list) else []):
            name = str(t.get("name") or "").strip() if isinstance(t, dict) else ""
            pw = str(t.get("password") or "") if isinstance(t, dict) else ""
            if not name or len(name) > TEAM_NAME_MAX or "|" in name or not pw:
                sys.stderr.write("[팀] %d번째 팀은 이름·비밀번호가 없어 뺐어요\n" % (i + 1))
                continue
            if name.casefold() in names or pw in pws:
                sys.stderr.write("[팀] 「%s」 — 이름이나 비밀번호가 앞 팀과 같아 뺐어요\n" % name)
                continue
            key = str(t.get("key") or "").strip()
            base = str(t.get("base") or "").strip().rstrip("/")   # 키가 다른 계정이면 그 계정 게이트웨이 주소(없으면 서버 주소)
            if base and not base.startswith(("https://", "http://")):
                sys.stderr.write("[팀] 「%s」 base는 http(s) 주소만 — 뺐어요\n" % name)
                base = ""
            boards = []
            for b in t.get("boards") or []:
                if isinstance(b, str) and b and b.casefold() not in owned:
                    owned.add(b.casefold())
                    boards.append(b)
                elif isinstance(b, str) and b:
                    sys.stderr.write("[팀] 칠판 「%s」은 앞 팀 것이라 「%s」에서 뺐어요\n" % (b, name))
            names.add(name.casefold())
            pws.add(pw)
            out.append({"name": name, "password": pw, "key": key, "base": base, "boards": boards})
        return out

    def by_password(self, pw: str) -> dict | None:
        return next((t for t in self.teams if _same(t["password"], pw)), None) if pw else None

    def by_cookie(self, cookie: str) -> dict | None:
        return next((t for t in self.teams if _same(team_key(t), cookie)), None) if cookie else None

    def owner(self, board: str) -> dict | None:
        b = board.casefold()
        return next((t for t in self.teams if any(x.casefold() == b for x in t["boards"])), None)

    def allows(self, team: dict, board: str, data_dir: str, claim: bool = False) -> bool:
        """팀이 이 칠판을 써도 되나 — 그 팀 것이면 예, 남의 팀 것·팀 없는 옛 칠판(파일 있음)이면 아니오, 새 이름이면 예(claim이면 그 팀에 등록)."""
        o = self.owner(board)
        if o is not None:
            return o["name"] == team["name"]
        if board_files_exist(data_dir, board):
            return False
        return self.claim(team, board) if claim else True

    def claim(self, team: dict, board: str) -> bool:
        """새 칠판을 그 팀 `boards`에 더해 파일에 씀(사람이 적어 둔 다른 칸은 그대로). 그사이 다른 팀이 가졌으면 False."""
        with self.lock:
            try:
                with open(self.path, encoding="utf-8-sig") as f:
                    raw = json.load(f)
            except (OSError, ValueError):
                return False
            for t in raw if isinstance(raw, list) else []:
                if isinstance(t, dict) and any(isinstance(x, str) and x.casefold() == board.casefold() for x in t.get("boards") or []):
                    return str(t.get("name") or "").strip() == team["name"]
            hit = next((t for t in raw if isinstance(t, dict) and str(t.get("name") or "").strip() == team["name"]), None)
            if hit is None:
                return False
            hit["boards"] = [*(hit.get("boards") or []), board]
            body = json.dumps(raw, ensure_ascii=False, indent=2).encode("utf-8")
            tmp = self.path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(body)
            os.replace(tmp, self.path)
            self._sig = None   # 다음에 다시 읽음
        self._reload()
        sys.stderr.write("[팀] 새 칠판 「%s」 → %s\n" % (board, team["name"]))
        return True
