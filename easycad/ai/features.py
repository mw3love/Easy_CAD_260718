"""웹 칠판 「KAIROS 기능 표」(2026-11-08, Qt 비의존) — 한 줄 = 대화창 말 한마디로 갈 수 있는 KAIROS 기능 하나.

2026-11-07 대화창 bakeoff 3라운드에서 「+」 도구 창을 없애기로 함(사용자 — 「모두 채팅창으로 녹여 버리자, 대부분의 AI 서비스가 그렇게」).
그래서 길마다 「무엇을 하는 길인지」를 한 곳에 적고, 길 고르기 선택지(`route.JUDGE_KINDS`)·대화창 비용 안내(`/api/models` `features`)가 여기서 나온다.
새 기능을 더하면 이 표에 한 줄 + `route.CASES`에 정답 문항을 더하고 판정을 다시 잰다.

칸:
- kind: 서버·대화창이 쓰는 길 이름(`/api/chat` `kind`)
- judge: 판정 모델에게 보이는 설명(한 줄 — 비슷한 길과 갈리는 말을 넣는다)
- ask: 만들기 전에 맞춤 질문(질문지 카드)을 먼저 하나
- api: KAIROS 창구 · type: 모델 종류(KAIROS `type`) · model: 지금 기본 모델(모듈 상수)
- board: 칠판에 무엇으로 남나
- credits: 한 번에 드는 어림 크레딧 (낮음, 높음) — 실측에서 옴, 모르면 None(「확인 필요」)
"""
from __future__ import annotations

from easycad.ai import board_chat, board_diagram, board_icon, board_image, board_report, live_card, slides

FEATURES = [
    {"kind": "chat", "judge": "AI가 아는 일반 지식·방법·설명, 또는 고른 글을 번역·요약·다듬기",
     "ask": False, "api": "/chat/completions/", "type": "chat", "model": "", "board": "답 글(메모로 붙이기)", "credits": (0.1, 2)},
    {"kind": "search", "judge": "인터넷의 최신·실시간 정보가 필요(뉴스·날씨·시세·최근 상황·맛집 등)",
     "ask": False, "api": "/exa/answer/", "type": "search", "model": board_chat.SEARCH_MODEL, "board": "답 글 + 출처", "credits": (1, 3)},
    {"kind": "board", "judge": "사용자가 이 칠판에 전에 적어 둔 자기 메모·기록을 찾아야 함(우리·내가 적은·지난번·정했었지 등)",
     "ask": False, "api": "/embeddings/", "type": "embedding", "model": "", "board": "답 글 + 칠판 자리", "credits": (0.1, 2)},
    {"kind": "image", "judge": "그림·일러스트를 새로 그리기(흐름도·도면·표는 chat)",
     "ask": False, "api": "/images/generations/", "type": "image", "model": board_image.IMAGE_MODEL, "board": "그림 후보 둘 중 고른 것", "credits": (20, 26)},
    {"kind": "infographic", "judge": "어떤 주제를 조사해서 숫자·핵심이 한눈에 보이는 인포그래픽 그림 한 장으로 만들기",
     "ask": True, "api": "/images/generations/", "type": "image", "model": board_image.IMAGE_MODEL, "board": "인포그래픽 그림 후보 둘", "credits": (22, 32)},
    {"kind": "icon", "judge": "선으로 된 아이콘·심볼을 SVG(고칠 수 있는 선)로 만들기",
     "ask": False, "api": "/chat/completions/", "type": "chat", "model": board_icon.ICON_MODEL, "board": "고칠 수 있는 선 도형", "credits": (2, 6)},
    {"kind": "diagram", "judge": "상자와 화살표로 된 흐름도·계통도·구성도를 칠판에서 고칠 수 있는 도형으로 그리기",
     "ask": False, "api": "/chat/completions/", "type": "chat", "model": board_diagram.DIAGRAM_MODEL, "board": "프레임 안 상자·화살표", "credits": (10, 20)},
    {"kind": "report", "judge": "칠판 자료를 문서·보고서 한 장으로 정리",
     "ask": False, "api": "/chat/completions/", "type": "chat", "model": board_report.REPORT_MODEL, "board": "정리 문서 카드", "credits": None},
    {"kind": "slides", "judge": "발표 자료·슬라이드·PPT·여러 장짜리 작은 책이나 그림책·동화책 만들기",
     "ask": True, "api": "/chat/completions/ + /images/generations/", "type": "chat", "model": slides.WRITER_MODEL, "board": "16:9 프레임 여러 장(바로 발표)", "credits": (40, 160)},
    {"kind": "live", "judge": "원리를 직접 눌러 보고 값을 바꿔 보는 인터랙티브 HTML·시뮬레이션 카드 만들기",
     "ask": False, "api": "/chat/completions/", "type": "chat", "model": live_card.LIVE_MODEL, "board": "움직이는 카드(HTML)", "credits": (30, 60)},
]
BY_KIND = {f["kind"]: f for f in FEATURES}
ASK_FIRST = {f["kind"] for f in FEATURES if f["ask"]}   # 서버는 만들지 않고 대화창에 질문지부터 띄우라고 답함(`/api/chat` `kind: 'go'`)


def judge_kinds() -> dict:
    """판정 모델 선택지 {길: 설명} — 표 차례 그대로."""
    return {f["kind"]: f["judge"] for f in FEATURES}


def public() -> list:
    """대화창에 줄 것(`/api/models` `features`) — 비용 안내용, 모델 이름은 `jobs`가 따로 줌."""
    return [{"kind": f["kind"], "ask": f["ask"], "board": f["board"], "credits": list(f["credits"]) if f["credits"] else None} for f in FEATURES]


def credit_text(kind: str) -> str:
    """「약 22~32크레딧」 — 모르면 ""."""
    c = (BY_KIND.get(kind) or {}).get("credits")
    if not c:
        return ""
    lo, hi = c
    return f"약 {lo:g}크레딧" if lo == hi else f"약 {lo:g}~{hi:g}크레딧"
