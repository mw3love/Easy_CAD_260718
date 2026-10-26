"""모델 대체(2026-10-26, Qt 비의존) — 정해 둔 모델이 KAIROS에서 은퇴하거나 없어져도 기능이 멈추지 않게, 사람이 관리하지 않아도.

사용자(2026-10-26): 「개발에서 손을 놓고 회사로 넘기면 모델 관리를 할 수 없다 — 관리 없이 오류가 안 나는 모델 선택」.
기능마다 재 보고 고른 이름(`board_image.IMAGE_MODEL` 등)은 코드에 그대로 두고, 부를 때마다 KAIROS 목록(`/models` — 대화창 목록을 받을 때
같이 기억, `remember`)을 보고 「지금 부를 이름」을 계산한다(`pick`). 새 이름을 어디 적어 두지 않으니 대신한 것이 또 은퇴해도 고칠 것이 없고,
원래 모델이 돌아오면 저절로 돌아간다.
① 부르기 전: 은퇴(`lifecycle: legacy`)면 KAIROS가 적은 대체(`replacement`)로 — 값이 원래의 1.5배를 넘으면 원래 것 그대로(은퇴해도 한동안 답함)
② 불렀다가 「모델 없음」(404 — 대화·임베딩·그림·받아쓰기 모두 같은 말, 2026-10-26 실측)이면 그 이름을 1시간 「없음」으로 기억하고
   같은 종류에서 대신할 것으로 한 번 다시(`fallback`) — 그 1시간은 처음부터 대신할 것으로
③ 목록에 없는 이름은 막지 않는다 — `jev-latest`·`stt-rt-v5`는 목록에 없어도 됨(2026-10-26 실측). 불러서 없을 때만 ②
「모델 없음」 밖의 오류(크레딧·바쁨·시간 초과)는 갈아타지 않는다 — 조용히 갈아타면 실패를 성공으로 오인(`gw.call_text_with_fallback`과 같은 원칙).
갈아탄 것은 `mark`로 답에 남긴다 — 서버가 답의 모델 이름을 실제로 부른 것으로 바꾸고 대화창이 「대신」을 보인다.
"""
from __future__ import annotations

import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from easycad.ai import gateway as gw

AUTO_MAX = 25.0        # 앱이 저절로 고르는 대화 모델 출력 값 상한(100만 토큰당 $) — fable·astra($50)는 사람만 고름
PRICE_FACTOR = 1.5     # 대신할 것의 값 상한(원래의 몇 배)
IMAGE_MAX = 15.0       # 원래 그림 값을 모를 때 장당 크레딧 상한 — gpt-image-2.5-flare 장당 10의 1.5배(2026-10-26 견적: 그림 모델은 장당 5~140으로 28배 차이)
DEAD_TTL = 3600        # 「없음」 기억(초) — 지나면 원래 이름으로 한 번 다시 부름(돌아왔을 수도)
LIST_TTL = 600         # 대신할 것을 찾을 때 목록이 이보다 오래면 새로 받음(서버 `/api/models`와 같은 10분)
CHAT_PATH = "/chat/completions/"
MAKER_ORDER = {"openai": 0, "claude": 1, "gemini": 2, "google": 2}   # 「모델 설정」 목록 차례(나머지 회사는 그 뒤 이름순)

_lock = threading.Lock()
_seen: dict = {}       # id → 목록 한 줄(한 번이라도 본 것 — 목록에서 사라져도 회사·값을 기억)
_now: set = set()      # 마지막으로 받은 목록에 있는 id
_loaded = [0.0]        # 마지막으로 목록을 받은 시각
_dead: dict = {}       # id → 없다고 안 시각
_alt: dict = {}        # 없어진 id → 대신 부를 id(②)
_swaps: dict = {}      # 원래 id → {"to", "why"} — 마지막 `pick`·`fallback` 결과(답에 남길 것)
_cost: dict = {}       # 그림 id → 장당 크레딧(견적·실제 차감)


def reset():
    """시험용 — 기억을 모두 지움."""
    with _lock:
        for d in (_seen, _dead, _alt, _swaps, _cost):
            d.clear()
        _now.clear()
        _loaded[0] = 0.0


def remember(rows: list):
    """KAIROS `/models` 목록(`data`)을 기억 — 받을 때마다(`gw.models_raw`)."""
    with _lock:
        _now.clear()
        for r in rows or []:
            if isinstance(r, dict) and r.get("id"):
                _seen[r["id"]] = r
                _now.add(r["id"])
        _loaded[0] = time.time()


def load(api_key: str, base_url: str = gw.BASE_URL):
    """목록을 새로 받아 기억(서버를 켤 때·대신할 것을 찾을 때). 못 받으면 그냥 둠 — 부르는 것은 그대로 된다."""
    try:
        gw.models_raw(api_key, base_url)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write("[모델 목록 못 받음] %s\n" % e)


def note_cost(mid: str, per: float):
    """그림 한 장에 실제로 든 크레딧 — 그 모델이 없어졌을 때 대신할 것의 값 상한으로."""
    if mid and isinstance(per, (int, float)) and per > 0:
        _cost[mid] = float(per)


def _dead_now(mid: str) -> bool:
    t = _dead.get(mid)
    if t and time.time() - t < DEAD_TTL:
        return True
    if t:   # 1시간 지남 — 원래 이름으로 다시
        _dead.pop(mid, None)
        _alt.pop(mid, None)
    return False


def _price(row) -> float | None:
    p = (row or {}).get("pricing") or {}
    v = p.get("output", p.get("input"))
    return float(v) if isinstance(v, (int, float)) else None


def _step(mid: str) -> tuple:
    """한 걸음 → (다음 id, 까닭) 또는 (None, "")."""
    if _dead_now(mid):
        return _alt.get(mid), "없어짐"
    row = _seen.get(mid)
    rep = (row or {}).get("replacement")
    if row and row.get("lifecycle") == "legacy" and rep and rep in _now:   # 대체도 없어졌으면 다음 걸음이 그것의 대신으로
        a, b = _price(row), _price(_seen.get(rep))
        if a is None or b is None or b <= a * PRICE_FACTOR:
            return rep, "은퇴"
    return None, ""


def pick(mid: str) -> str:
    """정해 둔 이름 → 지금 부를 이름(은퇴·없어짐을 따라감, 고리는 막음). 목록을 아직 안 받았으면 그대로."""
    if not mid:
        return mid
    cur, why, seen = mid, "", {mid}
    with _lock:
        while True:
            nxt, w = _step(cur)
            if not nxt or nxt in seen:
                break
            cur, why = nxt, why or w
            seen.add(cur)
        if cur != mid:
            _swaps[mid] = {"to": cur, "why": why}
        else:
            _swaps.pop(mid, None)
    return cur


def mark(out):
    """답 dict의 "model"을 갈아탔으면 실제로 부른 이름으로 + "swap": {"from", "to", "why"}(대화창 「대신」). 아니면 그대로."""
    m = out.get("model") if isinstance(out, dict) else None
    s = _swaps.get(m) if isinstance(m, str) else None
    if not s or s["to"] == m:
        return out
    return {**out, "model": s["to"], "swap": {"from": m, **s}}


def _rows(kind: str) -> list:
    return [r for i, r in list(_seen.items()) if i in _now and r.get("type") == kind and r.get("lifecycle") != "legacy" and not _dead_now(i)]


def _same_maker(mid: str, row: dict) -> bool:
    """같은 회사 — 본 적 있으면 `owned_by`, 없으면(목록에서 사라진 뒤 서버를 켬) 이름 첫 마디."""
    seen = _seen.get(mid)
    if seen and seen.get("owned_by"):
        return seen.get("owned_by") == row.get("owned_by")
    return row["id"].split("/")[0].split("-")[0] == mid.split("/")[0].split("-")[0]


def _newest(rows: list) -> str | None:
    return max(rows, key=lambda r: (r.get("created", 0), r["id"]))["id"] if rows else None


def _llm_alt(mid: str) -> str | None:
    """대화 모델: 같은 계열(버전만 다름) 가장 새 것 → 같은 회사에서 값이 가장 비슷한 것 → 대화 기본 모델. 값은 원래의 1.5배·`AUTO_MAX` 안."""
    o = _price(_seen.get(mid))
    cap = min(AUTO_MAX, o * PRICE_FACTOR) if o else AUTO_MAX
    rows = [r for r in _rows("llm") if r["id"] != mid and _price(r) is not None and _price(r) <= cap
            and any(str(e).endswith(CHAT_PATH) for e in r.get("endpoints") or [CHAT_PATH])
            and not any(w in r["id"].lower() for w in ("image", "tts", "audio"))]
    line = gw.model_line(mid)
    alt = _newest([r for r in rows if gw.model_line(r["id"]) == line])
    if alt:
        return alt
    default = gw.default_model_id(gw.text_models_from([_seen[i] for i in list(_now) if i in _seen]))
    target = max(o or _price(_seen.get(default)) or 10.0, 1e-3)
    maker = [r for r in rows if _same_maker(mid, r)]
    if maker:
        return min(maker, key=lambda r: (abs(math.log(max(_price(r), 1e-3)) - math.log(target)), -r.get("created", 0)))["id"]
    return default if default != mid and not _dead_now(default) else None


def _embed_alt(mid: str) -> str | None:
    """임베딩: 같은 계열 → 같은 회사 → 아무것, 뒤 둘은 싼 것부터(모아 둔 뜻 숫자는 `board_find`가 이름별로 따로 둠)."""
    rows = [r for r in _rows("embedding") if r["id"] != mid]
    alt = _newest([r for r in rows if gw.model_line(r["id"]) == gw.model_line(mid)])
    if alt:
        return alt
    for group in ([r for r in rows if _same_maker(mid, r)], rows):
        if group:
            return min(group, key=lambda r: (_price(r) if _price(r) is not None else 1e9, r["id"]))["id"]
    return None


def _estimate(api_key: str, base_url: str, mid: str, http) -> float | None:
    """그림 한 장 무료 견적(KAIROS `/estimate/` — 크레딧을 안 씀)."""
    if mid in _cost:
        return _cost[mid]
    try:
        r = http.post(base_url + "/estimate/", headers={"Authorization": f"Bearer {api_key}"},
                      json={"kind": "image", "model": mid, "number_of_images": 1}, timeout=20)
        v = r.json().get("credits") if r.status_code < 400 else None
    except Exception:  # noqa: BLE001
        v = None
    if isinstance(v, (int, float)):
        _cost[mid] = float(v)
        return float(v)
    return None


def _image_alt(mid: str, api_key: str, base_url: str, http) -> str | None:
    """그림: 같은 회사 → 다른 회사, 장당 견적이 상한 안에서 싼 것부터. 그림 모델은 목록에 값·등록 순서가 없어(2026-10-26 — 모두 같은 `created`) 견적으로 잰다."""
    if http is None:
        import httpx
        http = httpx
    known = _estimate(api_key, base_url, mid, http)
    cap = known * PRICE_FACTOR if known else IMAGE_MAX
    rows = [r for r in _rows("image") if r["id"] != mid]
    for group in ([r for r in rows if _same_maker(mid, r)], [r for r in rows if not _same_maker(mid, r)]):
        with ThreadPoolExecutor(8) as ex:
            costs = list(ex.map(lambda r: _estimate(api_key, base_url, r["id"], http), group))
        ok = sorted((c, r["id"]) for c, r in zip(costs, group) if c is not None and c <= cap)
        if ok:
            return ok[0][1]
    return None


def _stt_alt(mid: str) -> str | None:
    """받아쓰기: 같은 창구(`audio_client` — soniox)의 다른 모델."""
    lane = (_seen.get(mid) or {}).get("audio_client") or "soniox"
    return _newest([r for r in _rows("audio") if r["id"] != mid and r.get("audio_client") == lane])


def fallback(mid: str, kind: str, api_key: str, base_url: str = gw.BASE_URL, *, http=None) -> str | None:
    """`mid`를 불렀더니 「모델 없음」 → 1시간 「없음」으로 기억하고 대신 부를 이름. 못 찾으면 None(원래 오류 그대로).
    `kind` = "llm" | "embedding" | "image" | "stt"."""
    if time.time() - _loaded[0] > LIST_TTL:
        load(api_key, base_url)   # 대신할 것은 새 목록에서
    with _lock:
        _dead[mid] = time.time()
    alt = {"llm": _llm_alt, "embedding": _embed_alt, "stt": _stt_alt}[kind](mid) if kind != "image" else _image_alt(mid, api_key, base_url, http)
    with _lock:
        if alt:
            _alt[mid] = alt
            for v in _swaps.values():   # 앞에서 이 이름으로 갈아탔던 것도 새 이름으로
                if v["to"] == mid:
                    v.update(to=alt, why="없어짐")
            _swaps[mid] = {"to": alt, "why": "없어짐"}
    sys.stderr.write("[모델 없음] %s → %s\n" % (mid, alt or "대신할 것 없음"))
    return alt


def choices() -> dict:
    """대화창 「모델 설정」 목록(2026-10-26) — 종류(`type`)로 나눈 지금 모델 전부, 회사별·비싼 것부터.
    {"llm": [{"id", "maker", "price"}], "image": [{"id", "maker", "price"(장당 견적 — 아직 모르면 "")}]}. 판단(jev)·음성·임베딩은 고르는 칸이 없어 안 넣음."""
    llm = [r for r in _rows("llm") if _price(r) is not None and any(str(e).endswith(CHAT_PATH) for e in r.get("endpoints") or [CHAT_PATH])
           and not any(w in r["id"].lower() for w in ("image", "tts", "audio"))]
    first = lambda r: (MAKER_ORDER.get(str(r.get("owned_by")), 9), str(r.get("owned_by")))   # noqa: E731 — 대화창 목록과 같은 차례(GPT·Claude·Gemini 먼저)
    llm.sort(key=lambda r: (first(r), -_price(r), r["id"]))
    img = sorted(_rows("image"), key=lambda r: (first(r), _cost.get(r["id"], 1e9), r["id"]))
    p = lambda r: gw.price_text({"input": (r.get("pricing") or {}).get("input"), "output": _price(r)})   # noqa: E731
    return {"llm": [{"id": r["id"], "maker": r.get("owned_by") or "", "price": p(r)} for r in llm],
            "image": [{"id": r["id"], "maker": r.get("owned_by") or "",
                       "price": f"장당 약 {_cost[r['id']]:g}크레딧" if r["id"] in _cost else ""} for r in img]}


def price_images(api_key: str, base_url: str = gw.BASE_URL, http=None):
    """그림 모델마다 한 장 견적(무료)을 받아 둠 — 「모델 설정」 목록에 값을 보이려고(서버를 켤 때 뒤에서)."""
    if http is None:
        import httpx
        http = httpx
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda r: _estimate(api_key, base_url, r["id"], http), _rows("image")))


class _Over:
    """겉 — 몇 이름만 바꾸고 나머지는 속 물건 그대로."""

    def __init__(self, inner, **over):
        self.__dict__.update(_inner=inner, _over=over)

    def __getattr__(self, name):
        over = self.__dict__["_over"]
        return over[name] if name in over else getattr(self.__dict__["_inner"], name)


def _guard(create, kind: str, api_key: str, base_url: str):
    def call(*a, **kw):
        want = kw.get("model")
        if not isinstance(want, str) or not want:
            return create(*a, **kw)
        use = pick(want)
        try:
            return create(*a, **{**kw, "model": use})
        except Exception as e:
            alt = fallback(use, kind, api_key, base_url) if gw.classify_error(e) == "model_not_found" else None
            if not alt:
                raise
            return create(*a, **{**kw, "model": alt})
    return call


def guarded(client, api_key: str, base_url: str):
    """OpenAI 클라이언트 → 대화(`chat.completions.create`)·임베딩(`embeddings.create`)이 ①②를 거치는 겉(`gw._client`가 씀). 나머지는 그대로."""
    comp = client.chat.completions
    return _Over(client,
                 chat=_Over(client.chat, completions=_Over(comp, create=_guard(comp.create, "llm", api_key, base_url))),
                 embeddings=_Over(client.embeddings, create=_guard(client.embeddings.create, "embedding", api_key, base_url)))
