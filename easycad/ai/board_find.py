"""웹 칠판 「뜻으로 찾기」(§8 항목61 ③-2, 2026-10-19) — 칠판(.ecad)의 글을 KAIROS 임베딩으로 찾는다(Qt 비의존, `web/server.py`가 부름).

처음 의도 「질문·답이 흘러가 버리지 않고 쌓여서 다시 찾아진다」의 「다시 찾아진다」 몫. 낱말이 하나도 안 겹쳐도 뜻이 가까우면 찾고
(「밥 뭐 먹지」 → 「점심 후보」, 「인쇄기」 → 「프린터 토너 교체」), 친 낱말이 그대로 들어 있으면 점수를 더 준다.
모델(2026-10-19 KAIROS 임베딩 5개를 한국어 질문 9개로 비교): text-embedding-3-small 6/9(「인쇄기」 못 찾음) · 3-large 9/9(3072차원) ·
text-embedding-v4 9/9 · qwen3.7-text-embedding 9/9 + 정답과 2등 차이 가장 큼(1024차원, 100만 토큰 $0.07) → qwen. gemini-embedding-2는 그때 429.
도형마다 글은 `uid`(공동작업 이름표)로 돌려준다 — 브라우저가 그 도형으로 바로 간다.
글의 뜻 숫자(벡터)는 칠판 옆 `<이름>.emb.json`에 글 지문(sha1)별로 두고, 바뀐 글만 다시 만든다(1536개 숫자, 한 번에 100개씩).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re

EMBED_MODEL = "qwen3.7-text-embedding"   # KAIROS 임베딩(위 비교, 1.0초·1024차원) — 바꾸면 모아 둔 뜻 숫자는 버리고 다시 만든다(_load_cache)
MAX_TEXT = 2000        # 도형 하나 글 상한(자) — 긴 메모도 앞부분이면 뜻은 충분
MIN_SCORE = 0.42       # 이보다 낮은 뜻 점수는 「관련 없음」(qwen 실측: 정답 최저 0.43, 오답은 대부분 0.40 아래)
NEAR_TOP = 0.18        # 1등보다 이만큼 넘게 낮으면 뺌(오답이 0.43~0.48까지 올 때가 있어 — 「방송사 경영진」 1등 0.67 · 엉뚱한 2등 0.43)
WORD_BONUS = 0.25      # 친 낱말이 모두 들어 있으면 더함
KIND_NAME = {"doc": "정리 문서", "memo": "메모", "text": "글", "table": "표", "web": "웹 카드", "frame": "프레임", "sarrow": "화살표", "arrow": "화살표",
             "rect": "상자", "ellipse": "원", "symbol": "심볼", "line": "선", "polygon": "다각형", "titleblock": "표제란"}


def item_text(it: dict) -> str:
    """도형 하나의 글(없으면 "") — 메모 줄·이름표·글 상자·표 칸·웹 카드 제목과 주소·화살표 라벨·프레임 이름·그림 설명·표제란 칸."""
    t = it.get("type")
    out = []
    if t == "memo":
        out += [str(ln.get("t", "")) for ln in it.get("lines") or [] if ln.get("k") != "hr"]
    if t == "text":
        out.append(str(it.get("text", "")))
    if isinstance(it.get("label"), dict):
        out.append(str(it["label"].get("text", "")))
    out += [str(L.get("text", "")) for L in it.get("labels") or [] if isinstance(L, dict)]
    if t == "table":
        out += [" | ".join(str(c) for c in row if c) for row in it.get("cells") or []]
    if t == "web":
        out += [str(it.get("title", "")), str(it.get("desc", "")), str(it.get("url", ""))]
    if t == "frame":
        out.append(str(it.get("name", "")))
    if t == "image":   # 대화창 그림 = 만든 요청(보이지 않는 설명 `alt`, 2026-10-20)
        out.append(str(it.get("alt", "")))
    if t == "doc":   # 정리 문서 카드(「정리해 줘」 ①) — 제목 + 문서 글
        from easycad.ai.board_report import plain_text
        out += [str(it.get("title", "")), plain_text(str(it.get("html", "")), MAX_TEXT)]
    if t == "titleblock" and isinstance(it.get("fields"), dict):
        out += [str(v) for v in it["fields"].values()]
    return "\n".join(s.strip() for s in out if s and s.strip())[:MAX_TEXT]


def board_items(doc: dict) -> list:
    """글이 있는 도형 → [{"uid", "type", "text"}](이름표 없는 도형은 뺀다 — 브라우저가 찾아갈 수 없음)."""
    out = []
    for it in doc.get("items") or []:
        uid = it.get("uid")
        text = item_text(it)
        if isinstance(uid, str) and uid and text:
            out.append({"uid": uid, "type": it.get("type", ""), "text": text})
    return out


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _cos(a, b) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _load_cache(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("vecs", {}) if d.get("model") == EMBED_MODEL else {}
    except (OSError, ValueError):
        return {}


def _save_cache(path: str, vecs: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"model": EMBED_MODEL, "vecs": vecs}, f, separators=(",", ":"))
    os.replace(tmp, path)


def embed(client, texts: list) -> list:
    """글들 → 뜻 숫자들(차례 그대로). 한 번에 100개씩."""
    out = []
    for i in range(0, len(texts), 100):
        r = client.embeddings.create(model=EMBED_MODEL, input=texts[i:i + 100])
        out += [[round(x, 5) for x in d.embedding] for d in r.data]
    return out


def _words(q: str) -> list:
    return [w for w in re.split(r"\s+", q.strip().lower()) if len(w) >= 2]


def find(client, doc: dict, query: str, *, k: int = 8, cache_path: str = "") -> list:
    """칠판에서 질문과 뜻이 가까운 글 → [{"uid", "type", "kind", "text", "score"}] 점수 높은 차례, 최대 k개.
    뜻 점수가 MIN_SCORE 이상이고 1등에서 NEAR_TOP 안이어야 넣는다 — 친 낱말이 다 들어 있으면 그래도 넣는다. `cache_path`가 있으면 뜻 숫자를 거기 모아 둔다."""
    query = (query or "").strip()
    items = board_items(doc)
    if not query or not items:
        return []
    cache = _load_cache(cache_path) if cache_path else {}
    keys = [_sha(it["text"]) for it in items]
    missing = sorted({h for h in keys if h not in cache})
    by_sha = {h: it["text"] for h, it in zip(keys, items)}
    vecs = embed(client, [by_sha[h] for h in missing] + [query])
    qv = vecs[-1]
    for h, v in zip(missing, vecs[:-1]):
        cache[h] = v
    if cache_path and missing:
        live = set(keys)   # 지워진 글의 숫자는 버림(파일이 끝없이 커지지 않게)
        _save_cache(cache_path, {h: v for h, v in cache.items() if h in live})
    words = _words(query)
    sems = [_cos(qv, cache[h]) for h in keys]
    floor = max(MIN_SCORE, (max(sems) if sems else 0.0) - NEAR_TOP)
    scored = []
    for it, sem in zip(items, sems):
        low = it["text"].lower()
        hit = bool(words) and all(w in low for w in words)
        if sem < floor and not hit:
            continue
        scored.append({**it, "kind": KIND_NAME.get(it["type"], it["type"]), "score": round(sem + (WORD_BONUS if hit else 0.0), 3)})
    scored.sort(key=lambda r: -r["score"])
    return scored[:k]
