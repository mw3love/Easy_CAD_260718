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

    def ping(self, board: str, client: str, name: str, now: float | None = None) -> list:
        now = time.time() if now is None else now
        b = self.boards.setdefault(board, {})
        if client:
            b[client] = ((name or "이름 없음")[:30], now)
        for c in [c for c, (_, t) in b.items() if now - t > self.ttl]:
            del b[c]
        return sorted({n for n, _ in b.values()})
