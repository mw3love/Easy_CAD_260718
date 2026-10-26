"""공동작업 1단계(§8 항목61 ⓕ, 2026-10-18 사용자 결정 — 방송 준비용 소규모) — 서버(`web/server.py`)가 부르는 순수 계산.

- 도형 이름표 `uid`: 여러 브라우저가 같은 도형을 같은 이름으로 알아보게 .ecad에 저장(없으면 서버가 처음 열 때 붙임).
- 화살표 연결 `bind1`/`bind2`는 .ecad에선 「목록 순번」, 합치는 동안엔 상대 uid — 순번은 사람마다 달라서 그대로 합치면 엉뚱한 도형에 붙는다.
- 부분 저장(patch) = { base, upsert: [uid 꼴 도형], delete: [uid], meta: {layers 등 items 밖 칸} } → 도형 단위로 덮어씀(나중 것이 이김),
  서로 다른 도형을 고치면 둘 다 남는다. 고칠 때마다 판 번호 `rev` +1 — 브라우저는 「rev 다음 것 있나」로 받아 온다.
- 공용 비밀번호(사람별 계정 아님) → 편집 열쇠(쿠키), 게시 링크(로그인 없이 보기·발표만), 접속자 이름.
"""
from __future__ import annotations

import hashlib
import secrets
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


# ── 접속자(이름만, 15초 안에 신호 보낸 사람) ──
class Presence:
    def __init__(self, ttl: float = 15.0):
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
