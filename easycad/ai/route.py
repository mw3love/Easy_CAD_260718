"""웹 칠판 대화창 길 고르기(2026-10-20, Qt 비의존, `web/server.py`가 부름) — 질문 → 대화·웹 검색·칠판에서·그림·정리 문서·정리정돈.

판단은 KAIROS 판단 모델 `jev-latest`(POST /decisions/, choice + 확신도)에 맡기고, 낱말 규칙(`board_chat.guess_kind`)을 바닥으로 깐다:
바깥 모델이 없어지거나·오류·`TIMEOUT`을 넘기거나·주간 자가 시험에서 규칙보다 못하면 규칙으로(앱은 안 멈춤).
2026-10-20 실측(아래 `CASES` 24문항 × 2번, docs/history): 규칙 16/24 · jev 22/24(오류 0·두 번 같은 답·1.4초) · gemini-3.5-flash-lite 21~22(오류 4) ·
gpt-6-luna-decisions 21(오류 4). jev가 틀린 둘은 아래 두 손질로 잡음 — 흐름도·도면은 그림이 아님(규칙과 같은 말), 확신이 낮고 검색이 후보면 검색(출처가 붙어 안전).
"""
from __future__ import annotations

import os
import time

from easycad.ai import board_chat, gateway as gw

ROUTE_MODEL = "jev-latest"
TIMEOUT = 2.0          # 넘기면 규칙 — 판단 때문에 답이 늦어지지 않게
LOW_CONF = 0.6         # 이보다 낮고 검색이 1·2등이면 검색
INSTRUCTIONS = "사용자가 '웹 칠판' 앱 대화창에 쓴 글을 보고 어떤 길로 답할지 하나 고른다."
CRITERIA = {
    "search": "인터넷의 최신·실시간 정보가 필요(뉴스·날씨·시세·최근 상황·맛집 등)",
    "board": "사용자가 이 칠판에 전에 적어 둔 자기 메모·기록을 찾아야 함(우리·내가 적은·지난번·정했었지 등)",
    "chat": "AI가 아는 일반 지식·방법·설명, 또는 고른 글을 번역·요약·다듬기",
    "image": "그림·일러스트를 새로 그리기(흐름도·도면·표는 chat)",
    "report": "칠판 자료를 문서·보고서 한 장으로 정리",
    "tidy": "칠판 조각을 주제별로 묶어 옮기기",
}
# 정답 있는 시험 문제(질문, 칠판에서 고른 것 있음, 정답) — 주간 자가 시험·모델 시험장(§8 항목62)이 같이 씀. 늘릴 땐 사람이 정답을 단다.
CASES = [
    ("내일 전주 날씨 어때?", 0, "search"), ("오늘 회의 내용 정리해 줘", 0, "report"), ("송신소 발전기 점검 주기는 보통 얼마야?", 0, "chat"),
    ("지난번에 적어 둔 VSWR 값 뭐였지?", 0, "board"), ("요즘 AI 반도체 동향 알려줘", 0, "search"), ("이 메모 영어로 번역해 줘", 1, "chat"),
    ("KBS 수신료 지금 어떻게 걷어?", 0, "search"), ("엑셀에서 VLOOKUP 쓰는 법", 0, "chat"), ("우리 송신소 점검 결과 어땠지?", 0, "board"),
    ("송신탑 있는 산 풍경 그려 줘", 0, "image"), ("방송 송출 흐름도 그려 줘", 0, "chat"), ("이것들 주제별로 묶어 줘", 1, "tidy"),
    ("칠판 내용 보고서 한 장으로", 0, "report"), ("삼성전자 주가 얼마야", 0, "search"), ("파이썬 리스트 정렬 방법", 0, "chat"),
    ("발표 리허설 언제로 정했었지?", 0, "board"), ("ATSC 3.0이 뭐야?", 0, "chat"), ("ATSC 3.0 국내 도입 최근 상황", 0, "search"),
    ("이 글 더 짧게 다듬어 줘", 1, "chat"), ("전주 맛집 추천해 줘", 0, "search"), ("내가 정리한 할 일 중에 안 끝난 거 있어?", 0, "board"),
    ("광컨버터 고장나면 뭐부터 확인해?", 0, "chat"), ("오늘 날짜 기준 환율", 0, "search"), ("우리가 얘기한 예산 얼마였지", 0, "board"),
    ("내일의 전주 날씨를 고흐 느낌으로 그려줘.", 0, "image"),   # 2026-10-20 사용자 실사용 — 검색으로 잘못 감
    ("파라볼라 안테나를 SVG로 그려 줘", 0, "icon"), ("송신기를 선 그림으로 만들어 줘", 0, "icon"), ("아이콘 만드는 법 알려줘", 0, "chat"),   # §8 항목63
    ("펭귄 아이콘 그려줘", 0, "image"),   # 「아이콘」은 뜻이 둘 — 안 물었으면 그림, 대화창은 되물음(`decide`, §8 항목64)
    ("송신소 구성도 만들어 줘", 0, "chat"),   # 2026-10-23 측정 — 구성도가 그림으로 갔음
]
# 주간 자가 시험 결과 — False면 규칙만(서버가 `self_check`로 바꿈). 환경 변수 EASYCAD_ROUTE=rules면 늘 규칙(시험·네트워크 없는 곳)
state = {"ai": True}


def _state_text(text: str, has_context: bool) -> str:
    return ("(칠판에서 고른 글 있음) " if has_context else "") + (text or "")[:2000]


def ask_model(api_key: str, text: str, has_context: bool, *, base_url: str = gw.BASE_URL, http=None, timeout: float = TIMEOUT) -> tuple:
    """판단 모델 한 번 → (고른 길, 확신도, {길: 확률}). 실패하면 예외."""
    import httpx
    http = http or httpx
    r = http.post(base_url + "/decisions/", headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout,
                  json={"model": ROUTE_MODEL, "state": _state_text(text, has_context),
                        "questions": {"q": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA}}})
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}")
    a = r.json()["answers"]["q"]
    if a.get("choice") not in CRITERIA:
        raise RuntimeError(f"모르는 길 {a.get('choice')!r}")
    return a["choice"], float(a.get("confidence") or 0), dict(a.get("probabilities") or {})


def adjust(text: str, choice: str, conf: float, probs: dict) -> str:
    """판단 모델 답 손질 — 아이콘 말이면 아이콘(판단 모델엔 이 길이 없음 — 낱말로 분명, §8 항목63), 흐름도·도면은 그림이 아님,
    「그려 줘」가 분명하면 그림(최신 정보가 필요하면 서버가 검색 → 그리기로 이음), 확신이 낮고 검색이 1·2등이면 검색."""
    if board_chat.is_icon(text):
        return "icon"
    if choice == "image" and board_chat._DIAGRAM_WORDS.search(text or ""):
        return "chat"
    if board_chat._IMAGE_WORDS.search(text or "") and not board_chat._DIAGRAM_WORDS.search(text or ""):
        return "image"   # 2026-10-20 사용자: 「내일의 전주 날씨를 고흐 느낌으로 그려줘」가 검색(0.56)으로 감 — 그림 0.35~0.41로 헷갈림
    top2 = sorted(probs, key=lambda k: -float(probs[k] or 0))[:2]
    if conf < LOW_CONF and "search" in top2 and choice in ("chat", "search"):
        return "search"
    return choice


def route(api_key: str, text: str, has_context: bool = False, *, has_items: bool = True, base_url: str = gw.BASE_URL, http=None) -> tuple:
    """질문 → (길, 어떻게 골랐나 "ai"|"rules"). 정리정돈인데 칠판이 조각 목록을 안 보냈으면 규칙(조각 없이는 정돈 못 함)."""
    kind, how, _ = decide(api_key, text, has_context, has_items=has_items, base_url=base_url, http=http)
    return kind, how


# 되묻기(§8 항목64, 2026-10-23 사용자 승인) — 애매하고 비싼 갈림길에서 한 번, 버튼으로. 대화·검색은 틀려도 몇 초면 다시라 안 물음.
# 0단계 실측(41문항 × 3번): 「발표 자료 만들어 줘」 1·2등 차 0.03~0.11에 chat 2·report 1로 흔들림, 분명한 문항 중 차 < 0.3이고 비싼 길이 낀 것은 1개
ASK_GAP = 0.3
COSTLY = {"image", "report", "tidy"}


def decide(api_key: str, text: str, has_context: bool = False, *, has_items: bool = True, prefs: dict | None = None,
           base_url: str = gw.BASE_URL, http=None) -> tuple:
    """질문 → (길, "ai"|"rules", 물어볼 길 목록 — 안 물으면 []). 물을 때 길 = 안 물었으면 갔을 길.
    `prefs` = {갈림길 이름: 길} — 사용자가 같은 갈림길에서 같은 답을 고른 적이 있으면 묻지 않고 그 길(대화창이 보냄)."""
    if board_chat.maybe_icon(text):   # 「아이콘·로고·심볼」 — 판단 모델엔 아이콘 길이 없어 점수로는 못 봄(0단계: 「펭귄 아이콘」 image 1.0) → 낱말로
        pick = (prefs or {}).get("icon|image")
        return (pick, "rules", []) if pick in ("image", "icon") else ("image", "rules", ["image", "icon"])
    rules = board_chat.guess_kind(text, has_context)
    if os.environ.get("EASYCAD_ROUTE") == "rules" or not state["ai"] or not api_key:
        return rules, "rules", []
    try:
        choice, conf, probs = ask_model(api_key, text, has_context, base_url=base_url, http=http)
    except Exception:
        return rules, "rules", []
    kind = adjust(text, choice, conf, probs)
    if kind == "tidy" and not has_items:
        return rules, "rules", []
    return kind, "ai", ask_choices(choice, kind, probs, has_items)


# 되묻기 버튼 대신 입력 칸에 친 말(「선으로 해 줘」·「그림인데 수채화로」) → 버튼 중 하나. 앞이 먼저(「선 그림」은 그림보다 아이콘)
CHOICE_WORDS = [("icon", r"선\s*(으로|그림|도형)|도형|svg|벡터|고칠\s*수|아이콘으로"), ("image", r"그림|이미지|사진|일러스트|수채화|유화|그려"),
                ("report", r"문서|보고서|한\s*장|인쇄"), ("tidy", r"정돈|묶어|옮겨"), ("search", r"검색|찾아\s*(줘|봐)|최신"),
                ("board", r"칠판에서|적어\s*둔"), ("chat", r"그냥|글로|대화로|설명")]


def pick_from(text: str, choices: list) -> str:
    """되묻기에 글로 답함 → 그 말이 가리키는 버튼 길, 못 알아들으면 ""(서버는 다시 묻지 않고 원래 1등 길 — 한 요청에 한 번만 묻기)."""
    import re
    for k, words in CHOICE_WORDS:
        if k in choices and re.search(words, text or "", re.I):
            return k
    return ""


def ask_choices(choice: str, kind: str, probs: dict, has_items: bool = True) -> list:
    """판단 모델 1·2등이 가깝고(차 < `ASK_GAP`) 비싼 길이 끼면 [1등, 2등] — 낱말 손질이 길을 바꿨으면(말이 분명) 안 물음."""
    if kind != choice:
        return []
    top = [k for k in sorted(probs, key=lambda k: -float(probs[k] or 0)) if k in CRITERIA and (k != "tidy" or has_items)][:2]
    # 고른 길과 점수 1등이 다를 때도 있음(실측 chat 고름 · chat 0.49 / report 0.49) — 가장 애매한 경우라 1·2등 안에만 있으면 됨
    if len(top) < 2 or kind not in top or float(probs[top[0]] or 0) - float(probs[top[1]] or 0) >= ASK_GAP or not COSTLY & set(top):
        return []
    return [kind] + [k for k in top if k != kind]


def self_check(api_key: str, *, base_url: str = gw.BASE_URL, http=None) -> dict:
    """정답 있는 시험(`CASES`)으로 판단 모델 vs 규칙 — 판단 모델이 규칙보다 못하면 `state["ai"] = False`(규칙만).
    `jev-latest`처럼 이름은 그대로인데 속이 바뀌는 모델을 잡으려고 매주(서버, 2026-10-20 사용자 선택 — 비용 1센트 미만)."""
    ok_ai = ok_rules = err = 0
    t0 = time.time()
    for q, c, want in CASES:
        ok_rules += board_chat.guess_kind(q, bool(c)) == want
        try:
            choice, conf, probs = ask_model(api_key, q, bool(c), base_url=base_url, http=http, timeout=10.0)
            ok_ai += adjust(q, choice, conf, probs) == want
        except Exception:
            err += 1
    state["ai"] = ok_ai >= ok_rules
    return {"model": ROUTE_MODEL, "ai": ok_ai, "rules": ok_rules, "errors": err, "of": len(CASES), "use_ai": state["ai"],
            "at": int(time.time()), "sec": round(time.time() - t0, 1)}
