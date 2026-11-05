"""칠판 그림 따로 보내기(2026-11-05 사용자 — 노트북에서 큰 칠판이 다 뜨기까지 5초).

`.ecad`는 그림을 base64로 안에 품는다(데스크톱과 같은 꼴 — 그대로 둠). 그런데 웹이 칠판을 열 때마다 그 글을 통째로 받아
검증 본부는 4.2MB 중 75%가 그림이었다(같은 그림 5장 포함). 그래서 웹 화면에 보낼 때만(`?lite=1`) 그림 데이터를 빼고
주소(`_ref` = `/api/blob/<지문>.<확장자>`)를 단다 — 그림 파일은 내용 지문 이름이라 바뀔 일이 없어 브라우저가 오래 기억한다(같은 그림은 한 번만).
브라우저는 도형을 먼저 그리고, 그림을 받아 원래 데이터로 채워 넣는다(`web/src/next/blobs.js`). 디스크·데스크톱·AI가 읽는 파일은 그대로.

`_`로 시작하는 칸은 브라우저가 저장할 때 빼므로(`sync.toWire`·`model.toEcad`) 채우기 전에 그림을 옮겨도 `data: ''`로 온다
→ `keep_image_data`가 서버에 있던 데이터를 지킨다.
"""
import base64
import binascii
import hashlib
import os
import re

MIN_LEN = 4096          # 이보다 작은 그림은 그대로 둠(주소 한 번 더 묻는 값이 더 큼)
REF_RE = re.compile(r"^([0-9a-f]{32})\.(jpg|png|webp|gif)$")
CTYPE = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}
_known: dict = {}       # 지문 → 확장자(None = 따로 못 뺌 — 다시 풀어 보지 않게)


def _ext(raw: bytes):
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def split_data(s: str):
    """그림 데이터 → (앞머리, base64). 앞머리 = `data:image/...;base64,` 또는 ''."""
    if s.startswith("data:"):
        head, sep, body = s.partition(",")
        return (head + sep, body) if sep and head.endswith(";base64") else ("", "")
    return "", s


def ref_for(blob_dir: str, data: str):
    """그림 데이터 → (주소, 앞머리) — 파일이 없으면 이때 씀. 따로 못 빼면(작음·base64가 아님·되살린 글이 달라짐) None."""
    if not isinstance(data, str) or len(data) < MIN_LEN:
        return None
    pre, b64 = split_data(data)
    if not b64:
        return None
    h = hashlib.sha256(b64.encode("ascii", "replace")).hexdigest()[:32]
    ext = _known.get(h, "")
    if ext == "":
        ext = None
        try:
            raw = base64.b64decode(b64, validate=True)
            if base64.b64encode(raw).decode("ascii") == b64:   # 브라우저가 다시 base64로 만든 글이 한 글자도 안 달라야 함(다르면 저장할 때 바뀐 것으로 보임)
                ext = _ext(raw)
        except (binascii.Error, ValueError):
            raw = b""
        if ext:
            path = os.path.join(blob_dir, f"{h}.{ext}")
            if not os.path.exists(path):
                os.makedirs(blob_dir, exist_ok=True)
                tmp = f"{path}.{os.getpid()}.tmp"
                with open(tmp, "wb") as f:
                    f.write(raw)
                os.replace(tmp, path)
        _known[h] = ext
    return (f"/api/blob/{h}.{ext}", pre) if ext else None


def lite(doc: dict, blob_dir: str) -> dict:
    """웹 화면에 보낼 칠판 — 큰 그림 데이터를 주소로 바꾼 사본(원본은 그대로)."""
    items, changed = [], False
    for it in doc.get("items") or []:
        r = ref_for(blob_dir, it.get("data")) if isinstance(it, dict) and it.get("type") == "image" else None
        if r:
            it = dict(it, data="", _ref=r[0], _pre=r[1])
            changed = True
        items.append(it)
    return dict(doc, items=items) if changed else doc


def keep_image_data(items: list, old_items: list) -> list:
    """들어온 도형 중 데이터가 빈 그림(브라우저가 채우기 전에 옮김) = 서버에 있던 같은 도형(uid)의 데이터를 그대로."""
    old = {it.get("uid"): it.get("data") for it in old_items or [] if isinstance(it, dict) and it.get("type") == "image" and it.get("uid") and it.get("data")}
    if not old:
        return items
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("type") == "image" and not it.get("data") and old.get(it.get("uid")):
            it = dict(it, data=old[it["uid"]])
        if isinstance(it, dict) and ("_ref" in it or "_pre" in it):
            it = {k: v for k, v in it.items() if k not in ("_ref", "_pre")}
        out.append(it)
    return out


def blob_path(blob_dir: str, fn: str):
    """`/api/blob/<파일>`의 파일 → (경로, 종류) 또는 None."""
    m = REF_RE.match(fn or "")
    if not m:
        return None
    p = os.path.join(blob_dir, fn)
    return (p, CTYPE[m.group(2)]) if os.path.exists(p) else None
