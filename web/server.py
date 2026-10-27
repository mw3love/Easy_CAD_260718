"""Magic Board 웹 칠판 서버(§8 항목61 ⓑ, 2026-10-17) — 감시 PC에서 켜 두고 회사 안 다른 PC 크롬으로 접속한다.

하는 일 세 가지(화면·저장은 파이썬 기본 라이브러리만, 대화는 데스크톱 앱과 같은 openai·httpx):
- 칠판 화면: `web/dist/`(먼저 `cd web && npm run build`)를 그대로 내준다.
- 칠판 저장: GET/PUT `/api/doc/<이름>` — 칠판 문서(.ecad, 데스크톱과 같은 형식)를 데이터 폴더의 `<이름>.ecad`에.
  (옛 tldraw 칠판 `/api/board/<이름>`·`<이름>.json`은 2026-10-18 갈아타며 지움 — 쌓인 칠판 없음, 사용자 확인.)
  쓰기는 안전 저장(임시 파일 → 바꿔치기, `easycad/fileio/safe_write.py`)이라 도중에 꺼져도 직전 완성본이 남는다.
  바로 앞 저장본은 `<이름>.prev.ecad`로 하나 남긴다(실수로 지웠을 때 손으로 되살리기용).
- KAIROS 대화(§8 항목61 ⓒ): POST `/api/chat`(앞 대화 + 칠판에서 고른 글 → 답, `easycad/ai/board_chat.py`), GET `/api/models`,
  GET/PUT `/api/chatlog/<이름>` — 칠판마다 대화 기록(`<이름>.chat.json`). 게이트웨이 키는 이 서버 PC에만 있다(브라우저로 안 감 —
  키 찾는 순서는 데스크톱과 같다, `gateway.resolve_api_key`).
- 웹 카드: GET `/api/link?url=…&embed=…` — 주소를 대신 열어 제목·대표 그림·「칸 안에 넣어도 되나」(`link_info`). http(s)만.

- 공동작업 1단계(§8 항목61 ⓕ, 2026-10-18): 공용 비밀번호(`--password`·`MB_PASSWORD`·데이터 폴더 `edit_password.txt`) → POST `/api/login` = 편집 열쇠 쿠키.
  열쇠가 없으면 편집·대화·웹 카드 길목은 401(비밀번호를 안 정하면 누구나 — 내 PC 개발). 부분 저장 POST `/api/patch/<이름>`(도형 단위, 판 번호 rev),
  받아 오기 GET `/api/since/<이름>?rev=N`(바뀐 게 없으면 204), 접속자 POST `/api/presence/<이름>`, 게시 POST `/api/publish/<이름>` {on, renew} →
  로그인 없이 보기만 GET `/api/pub/<토큰>`(데이터 폴더 `publish.json`). 계산은 `web/collab.py`.
- 팀별 칠판(§8 항목67, 2026-10-27): 데이터 폴더 `teams.json`이 있으면 팀 비밀번호 → 그 팀 열쇠 = 그 팀 칠판만·그 팀 KAIROS 키
  (공용 비밀번호는 관리자 = 모든 칠판). 막는 곳 = 칠판 이름을 읽는 한 길 `_name()`, 없으면 지금과 똑같음.
⚠ 사내망 `http`라 비밀번호·열쇠가 암호화 없이 오간다 — 회사 보안 확인 전엔 내 PC에서만(`--host 127.0.0.1`).

실행: python web/server.py [--host 0.0.0.0] [--port 5191] [--data 폴더]
데이터 폴더 기본값: %APPDATA%/EasyCAD/web_boards (데스크톱 앱 설정·자동 저장과 같은 곳 — git에 안 들어감)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from easycad.fileio.safe_write import write_via_temp  # noqa: E402  (Qt 안 씀)
from easycad.ai import board_chat, board_find, board_icon, board_trace, deep_mode, board_image, board_ocr, board_report, kr_tools, live_card, meeting, model_pick, route, gateway as gw  # noqa: E402  (Qt 안 씀 — 키 찾기만 QSettings를 늦게 부른다)
sys.path.insert(0, HERE)
import collab  # noqa: E402  (공동작업 계산 — web/collab.py)
import pdfview  # noqa: E402  (PDF 보기 카드 — web/pdfview.py)

NAME_RE = re.compile(r"^[\w\-가-힣]{1,64}$")
MAX_BYTES = 200 * 1024 * 1024   # 그림이 든 칠판도 넉넉히, 하지만 끝없이는 아니게
_MODELS = {}                    # 키 지문 → (받은 시각, 모델 목록) — `/api/models`
PICK_JOBS = ("image", "icon", "report", "live", "deep_plan", "deep_write")   # 「모델 설정」으로 고를 수 있는 일(대화·회의 요약은 원래 `model`) — 2026-10-26 사용자: 고를 의미 있는 일만
# 그림 요청에 날짜 말이 있을 때만 오늘 날짜를 알려 줌(없는데 알려 주면 그림에 오늘 날짜를 써 넣음 — 2026-10-20 실측)
DATE_WORDS = re.compile(r"오늘|내일|모레|어제|그제|날짜|요일|주말|이번\s*주|다음\s*주|지난\s*주|이번\s*달|다음\s*달|\d+\s*월\s*\d+\s*일")


def default_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "EasyCAD", "web_boards")


class Handler(SimpleHTTPRequestHandler):
    data_dir = default_data_dir()
    password = ""                 # 공용 편집 비밀번호(없으면 누구나 — 내 PC 개발)
    presence = collab.Presence()
    lock = threading.Lock()       # 부분 저장·게시 표를 한 번에 하나씩
    changed = threading.Condition()   # 저장되면 깨움 — 받아 오기를 기다리던 요청(롱 폴링, 2026-10-19 사용자: 거의 실시간)
    revs = {}                     # 칠판 이름 → 마지막 판 번호(기다리는 동안 파일을 다시 읽지 않게)

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=os.path.join(HERE, "dist"), **kw)

    # ── API ──
    def _board_path(self):
        """칠판 문서(`/api/doc/<이름>` → `<이름>.ecad`)·대화 기록(`/api/chatlog/<이름>` → `<이름>.chat.json`)·
        「🎙 회의」 받아 적는 글 사본(`/api/meetdraft/<이름>` → `<이름>.meet.json`, 2026-10-23 — 브라우저가 죽어도 남게) 파일 자리.
        API 경로가 아니면 None, 이름이 나쁘면 ""."""
        m = re.match(r"^/api/(chatlog|doc|meetdraft)/([^/?#]+)$", self.path)
        if not m:
            return None
        name = self._name(m.group(2))   # 팀 검사도 여기서(§8 항목67)
        ext = {"chatlog": ".chat.json", "doc": ".ecad", "meetdraft": ".meet.json"}[m.group(1)]
        return os.path.join(self.data_dir, name + ext) if name else ""

    def _json(self, code: int, obj):
        obj = model_pick.mark(obj)   # 답의 "model"이 은퇴·없어져 갈아탄 이름이면 실제로 부른 이름 + "swap"(대화창 「대신」, 2026-10-26)
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _key(self) -> str:
        """KAIROS 키 — 브라우저가 「🔑 내 키」로 보낸 머리말 `X-Kairos-Key`가 있으면 그것(2026-10-20 사용자 — 사람마다 자기 크레딧),
        없으면 팀 키(`teams.json`, §8 항목67 — 팀마다 크레딧), 그것도 없으면 이 서버 PC 키. 받은 키는 이 요청에만 쓰고 파일·로그에 남기지 않는다."""
        mine = (self.headers.get("X-Kairos-Key") or "").strip()
        if re.fullmatch(r"[!-~]{8,300}", mine):
            return mine
        team = (self._team() or {}).get("key") or ""
        return team if re.fullmatch(r"[!-~]{8,300}", team) else gw.resolve_api_key()

    def _models(self):
        key = self._key()
        if not key:
            return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다(~/.claude/.secrets/easycad-gateway.key)"})
        import hashlib
        kid = hashlib.sha256(key.encode()).hexdigest()[:16]   # 키마다 따로(계정마다 모델이 다를 수 있음) — 키 자체는 안 들고 있음
        hit = _MODELS.get(kid)
        if hit is None or time.time() - hit[0] > 600:   # 10분마다 새로(새 모델이 올라와도 서버를 안 껐다 켜게)
            try:
                hit = _MODELS[kid] = (time.time(), board_chat.models(key, gw.resolve_base_url()))
            except Exception as e:   # 목록을 못 받아도 대화는 기본 모델로 된다
                return self._json(200, {"default": gw.FALLBACK_DEFAULT_MODEL, "featured": {}, "error": str(e)})
        # 일마다 정해 둔 모델 — 대화창 「생각 중」 줄이 고른 모델이 아니라 실제로 일하는 모델을 보이게(2026-10-20 사용자: 정돈인데 gpt로 보였음)
        jobs = {"report": board_report.REPORT_MODEL, "search": board_chat.SEARCH_MODEL, "image": board_image.IMAGE_MODEL, "icon": board_icon.ICON_MODEL, "deep": deep_mode.EDITOR_MODEL, "live": live_card.LIVE_MODEL, "trace": board_trace.TRACE_MODEL}   # deep = 대화창 「+ › 딥모드」를 보임(§8 항목66 3-3), live = 「+ › 움직이는 카드」(4단계)
        jobs.update(deep_plan=deep_mode.EDITOR_MODEL, deep_write=deep_mode.WRITER_MODEL)   # 「모델 설정」 칸(2026-10-26)
        jobs = {k: model_pick.pick(v) for k, v in jobs.items()}   # 은퇴·없어져 갈아탄 것은 지금 부르는 이름으로
        return self._json(200, {**hit[1], "jobs": jobs, "choices": model_pick.choices()})

    def _with(self, job: str, default: str, fn):
        """대화창 「모델 설정」에서 사람이 고른 모델(`models`)로 먼저 — 그 모델이 이 일을 못 하면(형식이 깨짐·창구가 안 받음 등) 앱 기본으로 한 번 다시,
        답에 「(대신)」(2026-10-26). 크레딧·바쁨·시간 초과는 다시 안 함(그대로 오류 — 시간 초과를 다시 하면 두 배로 기다림)."""
        mine = (getattr(self, "_picked", None) or {}).get(job)
        if not mine or mine == default:
            return fn(default)
        try:
            return fn(mine)
        except Exception as e:
            if gw.classify_error(e) in ("quota", "server_busy", "timeout"):
                raise
            sys.stderr.write("[고른 모델 못 함] %s %s → %s: %s\n" % (job, mine, default, str(e)[:200]))
            out = fn(default)
            return {**out, "swap": {"from": mine, "to": out.get("model") or default, "why": "못 함"}} if isinstance(out, dict) else out

    def _chat(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 24 * 1024 * 1024:   # 칠판에서 고른 그림(최대 4장, 긴 변 1536 JPEG)을 실을 수 있게 — KAIROS 본문 상한 25MB
            return self._json(413, {"error": "질문이 너무 큽니다"})
        try:
            req = json.loads(self.rfile.read(n))
        except ValueError:
            return self._json(400, {"error": "json"})
        self._extra = {}   # 아이콘·그림 답에 덧붙일 칸(되묻기 기억 — 연결을 다시 쓸 수 있어 요청마다 비움)
        picked = req.get("models") if isinstance(req.get("models"), dict) else {}   # 대화창 「모델 설정」 — 일마다 사람이 고른 모델(없으면 앱 기본, `_with`)
        self._picked = {k: v for k, v in picked.items() if k in PICK_JOBS and isinstance(v, str) and re.fullmatch(r"[\w.:/\-]{1,120}", v)}
        key = self._key()
        if not key:
            return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다(~/.claude/.secrets/easycad-gateway.key)"})
        try:
            msgs, ctx = req.get("messages") or [], req.get("context") or ""
            last = next((m for m in reversed(msgs) if isinstance(m, dict) and m.get("role") == "user"), {})
            kind = req.get("kind") or ""
            if kind == "deep":   # 딥모드(§8 항목66) — 대화창 질문지·계획 카드가 단계(`deep.step`)를 정해 보냄, 길 고르기 없음
                return self._deep(req, key)
            if kind == "live":   # 「+ › 움직이는 카드」(§8 항목66 4단계) — 하나만 따로, 재료 = 고른 것의 글. 앞 답이 카드이고 고칠 말이면 그 카드 고치기
                t = str(last.get("content", ""))
                fix = str(req.get("prev_html") or "") if req.get("prev_kind") == "live" and live_card.FOLLOW_WORDS.search(t) else ""
                return self._live(t, ctx or str(last.get("context") or ""), key, fix)
            reply = req.get("ask_reply") if isinstance(req.get("ask_reply"), dict) else None
            if not kind and reply:   # 되묻기 버튼 대신 입력 칸에 친 말(§8 항목64) — 그 말이 가리키는 버튼, 못 알아들으면 원래 1등 길(다시 안 물음)
                kind = route.pick_from(str(req.get("ask_add") or ""), [str(c) for c in reply.get("choices") or []]) or str(reply.get("default") or "") or "chat"
                sys.stderr.write("[되묻기 답] %s\n" % kind)
            fu = board_image.followup(msgs)   # 바로 앞 답이 그림이면 그 줄기(요청·찾은 정보)
            # 칠판에서 고른 그림(대화 기록엔 안 남음, 2026-10-20 사용자 — 칠판에서 고르고 말하기) — data:image만, 4장까지
            bimgs = [s for s in req.get("board_images") or [] if isinstance(s, str) and s.startswith("data:image/")][:4]
            text, base_svg = str(last.get("content", "")), str(req.get("base_svg") or "")[:60000]
            follow_svg = bool(base_svg and board_icon.FOLLOW_WORDS.search(text))   # 아이콘 답 뒤 「선을 더 굵게」 = 고른 아이콘 고치기
            if not kind and (board_chat.is_icon(text) or follow_svg):
                kind = "icon"   # 그림 고치기보다 먼저 — 「이 그림 아이콘으로 바꿔 줘」는 그림을 보고 아이콘(§8 항목63)
            if kind == "icon":
                return self._icon(text, key, base_svg if follow_svg else "", "" if follow_svg else (bimgs[0] if bimgs else ""))
            if not kind and (fu or bimgs) and (board_image.FOLLOW_WORDS.search(str(last.get("content", ""))) or board_chat._IMAGE_WORDS.search(str(last.get("content", "")))):
                kind = "image"   # 그림 뒤·그림을 고른 채 「날짜도 넣어 줘」 = 그 그림 고치기(판단 모델은 앞 대화·고른 그림을 안 봄)
            if not kind:   # 길 고르기 = 판단 모델 jev + 낱말 규칙 바닥(`easycad/ai/route.py`, 2026-10-20 사용자 선택)
                prefs = req.get("ask_pref") if isinstance(req.get("ask_pref"), dict) else {}
                kind, how, choices = route.decide(key, str(last.get("content", "")), bool(ctx or last.get("context")), prefs=prefs, base_url=gw.resolve_base_url())
                sys.stderr.write("[길] %s (%s)%s\n" % (kind, how, " — 되묻기 " + "|".join(choices) if choices else ""))
                if choices:   # 애매하고 비싼 갈림길 — 만들기 전에 버튼으로 물음(§8 항목64). 누르면 대화창이 그 길 이름표로 다시 보냄
                    return self._json(200, {"kind": "ask", "choices": choices, "default": kind, "key": "|".join(sorted(choices)),
                                            "content": "어느 쪽으로 만들까요?", "model": route.ROUTE_MODEL if how == "ai" else "낱말 규칙", "elapsed": 0})
                if board_chat.maybe_icon(text) and prefs.get("icon|image") == kind:   # 기억으로 고른 길 — 대화창이 답에 「다른 쪽으로」 버튼을 붙임
                    self._extra = {"remembered": {"key": "icon|image", "choices": ["image", "icon"]}}
                if kind == "icon":   # 되묻기에서 두 번 고른 길(`ask_pref`)
                    return self._icon(text, key, "", bimgs[0] if bimgs else "")
            refs = None
            # 날씨·공휴일·법령·통계·특보·대기질·국어 규범 = 공공 데이터 도구(KAIROS MCP, `kr_tools` — 2026-10-20). 못 쓰면(도시 밖·도구 실패) 지금처럼 웹 검색
            found = []
            if kind in ("chat", "search", "image") and not bimgs and not fu and not req.get("infographic") and kr_tools.WORDS.search(str(last.get("content", ""))):
                try:
                    found = kr_tools.gather(key, str(last.get("content", "")), base_url=gw.resolve_base_url())
                    sys.stderr.write("[도구] %s\n" % (", ".join(f"{f['tool']} {f['args']}" for f in found) or "안 씀"))
                except Exception as e:
                    sys.stderr.write("[도구 실패] %s\n" % e)
            prev_html = str(req.get("prev_html") or "")
            if kind == "chat" and prev_html and not req.get("kind"):   # 정리 문서 바로 뒤 「더 짧게」 같은 말 = 그 문서 고치기(움직이는 카드 뒤면 그 카드 — §8 항목66 4-3)
                kind = "live" if req.get("prev_kind") == "live" else "report"
            if kind == "live":
                return self._live(str(last.get("content", "")), ctx or str(last.get("context") or ""), key, prev_html if req.get("prev_kind") == "live" else "")
            if kind == "report":   # 「정리해 줘」 ① — 고른 것(없으면 칠판 전체)을 정리 문서 한 장으로(§8 항목61)
                return self._report(self._name(str(req.get("board") or "")), str(last.get("content", "")), ctx or str(last.get("context") or ""), prev_html, key)
            if kind == "image":   # 「○○ 그려줘」 — 그림 후보(§8 항목61 ③-4): 칠판 옆 폴더에 두고 주소만 대화 기록에(기록이 그림으로 불지 않게)
                name, prompt = self._name(str(req.get("board") or "")), str(last.get("content", ""))
                if req.get("infographic"):   # 정리 문서의 「🎨 그림으로도」 — 같은 자료(고른 것, 없으면 칠판 전체)로 인포그래픽
                    prompt = board_image.infographic_prompt(ctx or str(last.get("context") or "") or self._board_material(name))
                facts, note, edit = None, "", None
                base = self._img_file(name, str(req.get("base_image") or "")) if fu and not req.get("infographic") else ""
                if bimgs and not req.get("infographic"):   # 칠판에서 고른 그림이 먼저 — 그 그림을 그대로 두고 말한 것만
                    edit, prompt, note = bimgs, board_image.edit_prompt(prompt, len(bimgs)), f"칠판에서 고른 그림 {len(bimgs)}장을 그대로 두고 말한 점만 고쳤어요.\n\n"
                elif base:   # 앞 그림 고치기 — 칠판이 고른 그림(붙인 것, 없으면 첫 후보)을 그대로 두고 말한 것만(input_images, 2026-10-20)
                    with open(base, "rb") as f:
                        edit = ["data:image/%s;base64,%s" % ("jpeg" if base.endswith(".jpg") else base.rsplit(".", 1)[1], base64.b64encode(f.read()).decode())]
                    prompt, note = board_image.edit_prompt(prompt), "고른 그림을 그대로 두고 말한 점만 고쳤어요.\n\n"
                elif fu and not req.get("infographic"):   # 고칠 그림 파일이 없으면 — 처음 요청·찾은 정보 + 고칠 점으로 새로(다시 검색 안 함)
                    prompt, note = board_image.followup_prompt(fu, prompt), "앞 그림의 요청·정보를 이어서 고친 점만 반영해 새로 그렸어요(조금 달라질 수 있어요).\n\n"
                elif found:   # 날씨·공휴일·통계 그림 = 공공 데이터로(웹 검색보다 숫자가 정확, 0크레딧)
                    facts = board_chat.chat(key, [{"role": "user", "content": prompt + "\n(이 그림에 넣을 사실만 세 줄로)"}], model=gw.FALLBACK_DEFAULT_MODEL, kind="chat",
                                            data=kr_tools.context_text(found), base_url=gw.resolve_base_url())
                    facts.update(model=", ".join(s["title"] for s in kr_tools.sources(found)), sources=kr_tools.sources(found), head=kr_tools.TOOL_HEAD)
                    prompt += "\n\n[그림에 반영할 최신 정보 — 여기와 다른 숫자·날짜는 넣지 마]\n" + re.sub(r"\[\d+\]", "", facts["content"])[:1500]
                elif not req.get("infographic") and board_chat._SEARCH_WORDS.search(prompt):   # 「내일 날씨를 고흐 느낌으로 그려줘」 = 웹 검색 → 그리기(2026-10-20 사용자 — 대화창 all in one)
                    try:
                        facts = board_chat.chat(key, [{"role": "user", "content": prompt + "\n(이 그림에 넣을 사실만 세 줄로)"}], model=gw.FALLBACK_DEFAULT_MODEL, kind="search", base_url=gw.resolve_base_url())
                        prompt += "\n\n[그림에 반영할 최신 정보 — 여기와 다른 숫자·날짜는 넣지 마]\n" + re.sub(r"\[\d+\]", "", facts["content"])[:1500]
                    except Exception as e:   # 못 찾아도 그림은 그린다
                        sys.stderr.write("[그림 앞 검색 실패] %s\n" % e)
                # 그림 모델은 오늘을 모름 — 「내일 날짜도」가 11월 9일(일)로 나왔음(2026-10-20 실측)
                # 「오늘·내일은 이 기준」이라고만 쓰면 요청에 없는 「오늘」 칸을 지어냈음(같은 날 실측) — 날짜 계산에만 쓰라고.
                # 날짜 말이 없는 그림(「송신탑을 수채화로」)에도 붙이면 오늘 날짜를 그림에 써 넣었음(같은 날 실측) — 날짜 말이 있을 때만
                if DATE_WORDS.search(" ".join((fu or {}).get("asks", [])) + " " + str(last.get("content", ""))):
                    # 오늘만 주면 「내일 날씨」 그림에 오늘 날짜를 써 넣었음(2026-10-20 실측) — 내일·모레도 계산해 줌
                    day = lambda k: time.localtime(time.time() + k * 86400)
                    fmt = lambda t: "%d년 %d월 %d일(%s)" % (t.tm_year, t.tm_mon, t.tm_mday, "월화수목금토일"[t.tm_wday])
                    prompt += "\n\n[날짜 — 오늘 %s · 내일 %s · 모레 %s. 그림에 적는 날짜는 요청한 그날로. 요청에 없는 날의 내용은 넣지 마]" % (fmt(day(0)), fmt(day(1)), fmt(day(2)))
                return self._image(name, prompt, key, facts, note, fu["asks"][0] if fu and not req.get("infographic") else "", edit)   # 붙인 그림 밑 글 = 처음 요청
            if kind == "board":   # 「지난번 ○○ 뭐였지?」 — 이 칠판의 저장된 글에서 찾아 근거로(§8 항목61 ③-2)
                refs = self._find(self._name(str(req.get("board") or "")), str(last.get("content", "")), key)
            if found and kind in ("chat", "search"):   # 공공 데이터 답 = 고른 대화 모델 + 그 자료, 출처는 그 기관
                out = board_chat.chat(key, msgs, model=req.get("model") or gw.FALLBACK_DEFAULT_MODEL, context=ctx, kind="chat",
                                      data=kr_tools.context_text(found), base_url=gw.resolve_base_url())
                out["sources"] = kr_tools.sources(found)
            else:
                out = board_chat.chat(key, msgs, model=req.get("model") or gw.FALLBACK_DEFAULT_MODEL,
                                      context=ctx, kind=kind, board_refs=refs, base_url=gw.resolve_base_url())
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:   # 게이트웨이 오류는 대화창에 그대로 보여 준다(갈아타는 건 「모델 없음」일 때만, 답에 「대신」으로 — `model_pick`)
            return self._json(502, {"error": gw.friendly_error(e)})
        sys.stderr.write("[대화] %s %.1f초\n" % (out["model"], out["elapsed"]))
        return self._json(200, out)

    def _deep(self, req: dict, key: str):
        """딥모드 → step plan: {"kind": "deep", "plan"(본문 없이), "estimate", "model", "elapsed"} · step build: {"kind": "deep", "plan"(꼭지마다 body + sources), "model", "elapsed", "missing"}
        · step section(5단계): {"kind": "deep", "step": "section", "sections": [{"i", …새 꼭지}], "sources"(판 전체), "model", "elapsed", "missing"}.
        판은 칠판이 짓는다(`ed.deepBoard`). 재료 꼭지 board = 이 칠판의 저장된 글."""
        d = req.get("deep") if isinstance(req.get("deep"), dict) else {}
        step, topic = d.get("step"), str(d.get("topic") or "")
        brief = d.get("brief") if isinstance(d.get("brief"), dict) else {}
        base = gw.resolve_base_url()
        b0 = self._balance(key, base)   # 쓴 크레딧 = 잔액 차이(대화 모델 답엔 credits_charged가 없음) — 같은 키를 동시에 쓰면 섞임(대화창이 「약」)
        try:
            if step == "plan":
                prev = d.get("prev") if isinstance(d.get("prev"), dict) else None
                out = self._with("deep_plan", deep_mode.EDITOR_MODEL, lambda m: deep_mode.make_plan(gw._client(key, base, timeout=300), topic, brief, prev=prev, fix=str(d.get("fix") or "") if prev else "", model=m))
                sys.stderr.write("[딥모드 계획] %s %.1f초 꼭지 %d%s\n" % (out["model"], out["elapsed"], len(out["plan"]["sections"]), " (고치기)" if prev else ""))
                return self._json(200, {"kind": "deep", **out, "credits": self._spent(key, base, b0)})
            if step == "build":
                plan = d.get("plan") if isinstance(d.get("plan"), dict) else {}
                uses_board = any(isinstance(s, dict) and s.get("source") == "board" for s in plan.get("sections") or [])
                material = self._board_material(self._name(str(req.get("board") or ""))) if uses_board else ""
                out = self._with("deep_write", deep_mode.WRITER_MODEL, lambda m: deep_mode.build(key, gw._client(key, base, timeout=600), topic, brief, plan, base_url=base, board=material, image=self._deep_image(str(req.get("board") or ""), key, base), model=m))
                sys.stderr.write("[딥모드 만들기] %s %.1f초 출처 %d%s\n" % (out["model"], out["elapsed"], len(out["plan"]["sources"]), " 재료 없음: " + ", ".join(out["missing"]) if out["missing"] else ""))
                for w in out.get("switched") or []:   # 공공 데이터 → 웹 검색으로 갈아탄 꼭지(숫자 없음·다른 품목 — 실사용에서 얼마나 걸리나 보려고)
                    sys.stderr.write("[딥모드 웹으로] %s\n" % w)
                return self._json(200, {"kind": "deep", **out, "credits": self._spent(key, base, b0)})
            if step == "section":   # 판에서 고른 꼭지만 다시(5단계) — plan = 칠판 `deep_plan.plan`(꼭지마다 body + sources), 판은 칠판이 다시 지음
                plan = d.get("plan") if isinstance(d.get("plan"), dict) else {}
                idx = d.get("idx") if isinstance(d.get("idx"), list) else []
                uses_board = any(isinstance(s, dict) and s.get("source") == "board" for j, s in enumerate(plan.get("sections") or []) if j in idx)
                material = self._board_material(self._name(str(req.get("board") or ""))) if uses_board else ""
                out = self._with("deep_write", deep_mode.WRITER_MODEL, lambda m: deep_mode.redo(key, gw._client(key, base, timeout=600), plan, idx, brief, str(d.get("ask") or ""), base_url=base, board=material, image=self._deep_image(str(req.get("board") or ""), key, base), model=m))
                sys.stderr.write("[딥모드 꼭지 다시] %s %.1f초 꼭지 %s%s\n" % (out["model"], out["elapsed"], [s["i"] for s in out["sections"]], " 못 씀: " + ", ".join(out["missing"]) if out["missing"] else ""))
                return self._json(200, {"kind": "deep", "step": "section", **out, "credits": self._spent(key, base, b0)})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            return self._json(502, {"error": f"딥모드 실패: {gw.friendly_error(e)}"})
        return self._json(400, {"error": "딥모드 단계(plan·build·section)를 몰라요"})

    def _deep_image(self, board: str, key: str, base: str):
        """딥모드 요약 그림 그리기 — 지시문 → 그림 한 장을 칠판 옆 `<이름>.img/`에 두고 {"img": 주소, "w", "h", "model"}(칠판이 받아 그림 칸으로). 칠판 이름이 없으면 None."""
        name = self._name(board)
        if not name:
            return None

        def draw(prompt: str) -> dict:
            out = self._with("image", board_image.IMAGE_MODEL, lambda m: board_image.generate(key, prompt, n=1, base_url=base, model=m))
            data, ext = out["images"][0]
            url = self._save_img(name, data, ext)
            from io import BytesIO
            try:
                from PIL import Image
                w, h = Image.open(BytesIO(data)).size
            except Exception:   # 크기를 못 읽으면 요청한 비율(4:3)로 — 칠판이 그림을 받으면 실제 크기로 고침
                w, h = 1536, 1152
            sys.stderr.write("[딥모드 요약 그림] %s %dx%d · %s크레딧\n" % (out["model"], w, h, out.get("credits")))
            return {"img": url, "w": w, "h": h, "model": out["model"]}
        return draw

    @staticmethod
    def _balance(key: str, base: str):
        try:
            return gw.get_credit_balance(key, base)[0]
        except Exception:   # 잔액을 못 읽어도 일은 함 — 답에 크레딧만 안 붙음
            return None

    def _spent(self, key: str, base: str, b0):
        """일 앞 잔액 → 쓴 크레딧(정산이 늦게 잡혀 1.5초 뒤에 읽음 — 실측 도구는 2초). 못 읽으면 None"""
        if b0 is None:
            return None
        time.sleep(1.5)
        b1 = self._balance(key, base)
        return round(b0 - b1, 1) if b1 is not None else None

    def _live(self, ask: str, material: str, key: str, prev_html: str = ""):
        """움직이는 카드 하나 → {"kind": "live", "content", "title", "html", "model", "elapsed"} — 칠판에 붙이면 문서 카드 `live`(스크립트만 켠 칸).
        prev_html = 바로 앞 답이 움직이는 카드면 그 카드를 말대로 고침(정리 문서 `prev_html`과 같은 길)."""
        try:
            out = self._with("live", live_card.LIVE_MODEL, lambda m: live_card.make(gw._client(key, gw.resolve_base_url(), timeout=600), ask, material, prev_html=prev_html, model=m))
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            return self._json(502, {"error": f"움직이는 카드 실패: {gw.friendly_error(e)}"})
        sys.stderr.write("[움직이는 카드] %s %.1f초 %d자%s\n" % (out["model"], out["elapsed"], len(out["html"]), " (고치기)" if prev_html else ""))
        head = "말한 대로 고친 움직이는 카드" if prev_html else "움직이는 카드"
        return self._json(200, {"kind": "live", "content": f"{head} 「{out['title']}」 — 칠판에 붙이고 두 번 누르면 움직여 볼 수 있어요", **out})

    def _icon(self, ask: str, key: str, base_svg: str = "", image_url: str = ""):
        """아이콘 → {"kind": "icon", "content", "svgs": [SVG 글…], "model", "elapsed"} — 도형으로 바꾸기는 칠판(`svgin.js`), 대화 기록에 SVG 글 그대로(작음)."""
        try:
            out = self._with("icon", board_icon.ICON_MODEL, lambda m: board_icon.make(key, ask, base_svg=base_svg, image_url=image_url, base_url=gw.resolve_base_url(), model=m))
        except Exception as e:
            return self._json(502, {"error": f"아이콘 만들기 실패: {gw.friendly_error(e)}"})
        sys.stderr.write("[아이콘] %s %d개 %.1f초%s\n" % (out["model"], len(out["svgs"]), out["elapsed"], " (고치기)" if base_svg else " (그림 보고)" if image_url else ""))
        head = "고른 아이콘을 바탕으로 고쳤어요" if base_svg else "고른 그림을 보고 그렸어요" if image_url else f"아이콘 후보 {len(out['svgs'])}개"
        # 선 굵기·색은 칠판 펜이 정함(SVG 원본 값은 안 읽음 — 데스크톱과 같게) — 「굵게」라고 했는데 그대로면 헷갈림(2026-10-23 실측)
        tip = "\n\n선 굵기·색은 붙인 뒤 오른쪽 위 속성 카드 「선」에서 바로 바꿀 수 있어요." if re.search(r"굵|가늘|얇|색", ask) else ""
        return self._json(200, {"kind": "icon", "content": head + " — 누르면 칠판에 붙어요(선 하나하나 고칠 수 있어요)" + tip, **out, **getattr(self, "_extra", {})})

    def _report(self, name: str, ask: str, material: str, prev_html: str, key: str):
        """정리 문서 → {"kind": "report", "content", "title", "html", "model", "elapsed"} — 자료 = 고른 것의 글, 없으면 이 칠판 전체 글."""
        if not material.strip() and not prev_html:
            material = self._board_material(name)
        if not material.strip() and not prev_html:
            return self._json(400, {"error": "정리할 것이 없어요 — 칠판에서 메모·글을 고르고 다시 물어 주세요"})
        try:
            out = self._with("report", board_report.REPORT_MODEL, lambda m: board_report.make(gw._client(key, gw.resolve_base_url(), timeout=600), material, ask, prev_html=prev_html, model=m))
        except Exception as e:
            return self._json(502, {"error": f"정리 문서 실패: {gw.friendly_error(e)}"})
        sys.stderr.write("[정리 문서] %s %.1f초 %d자%s\n" % (out["model"], out["elapsed"], len(out["html"]), " 확인할 숫자 %d" % len(out["unchecked"]) if out.get("unchecked") else ""))
        tone = board_report.TONES.get(out.get("tone") or "", {}).get("name")
        note = f"\n\n칠판 자료에서 그대로 찾지 못한 숫자: {', '.join(out['unchecked'])} — 계산한 값일 수 있어요. 문서에서 한 번 확인해 주세요" if out.get("unchecked") else ""
        return self._json(200, {"kind": "report", "content": f"정리 문서 「{out['title']}」{f' · {tone} 톤' if tone else ''} — 칠판에 붙이면 인쇄용 문서 카드가 돼요{note}", **out})

    def _board_material(self, name: str) -> str:
        """이 칠판의 저장된 글 전부(「(메모) …」 줄들) — 고른 게 없을 때 정리 문서·인포그래픽의 자료."""
        if not name or not os.path.exists(self._doc_path(name)):
            return ""
        with open(self._doc_path(name), encoding="utf-8") as f:
            items = board_find.board_items(json.load(f))
        return "\n\n".join(f"({board_find.KIND_NAME.get(it['type'], it['type'])}) {it['text']}" for it in items)

    def _save_img(self, name: str, data: bytes, ext: str) -> str:
        """그림 바이트 → 칠판 옆 `<이름>.img/<시각>_<무작위>.<확장자>`(새 이름이라 덮어쓸 일 없음), 주소 `/api/img/<이름>/<파일>`."""
        from urllib.parse import quote
        os.makedirs(self._img_dir(name), exist_ok=True)
        fn = f"{int(time.time() * 1000)}_{secrets.token_hex(3)}.{ext}"
        with open(os.path.join(self._img_dir(name), fn), "wb") as f:
            f.write(data)
        return f"/api/img/{quote(name)}/{fn}"

    def _img_dir(self, name: str) -> str:
        return os.path.join(self.data_dir, name + ".img")

    def _img_file(self, name: str, url: str) -> str:
        """대화창이 보낸 그림 주소(`/api/img/<이 칠판>/<파일>`) → 서버의 그 파일 경로, 이 칠판 그림이 아니거나 없으면 ""."""
        from urllib.parse import unquote
        m = re.match(r"^/api/img/([^/]+)/(\d+_[0-9a-f]{6}\.(png|jpg|webp))$", url or "")
        if not name or not m or self._name(unquote(m.group(1))) != name:
            return ""
        p = os.path.join(self._img_dir(name), m.group(2))
        return p if os.path.exists(p) else ""

    def _image(self, name: str, prompt: str, key: str, facts: dict | None = None, note: str = "", caption: str = "", edit: list | None = None):
        """그림 후보 → {"kind": "image", "content", "images": [{"url"}], "model", "elapsed", "credits"(, "sources")} — 그림은 `<이름>.img/`에.
        `facts` = 그리기 전에 찾은 웹 검색 답(`board_chat.chat` 결과) — 답 글 앞에 그 내용·출처를 같이 보임."""
        if not name:
            return self._json(400, {"error": "칠판 이름이 없어요"})
        t0 = time.time()
        try:
            out = self._with("image", board_image.IMAGE_MODEL, lambda m: board_image.generate(key, prompt, base_url=gw.resolve_base_url(), model=m, **({"input_images": edit, "n": 1} if edit else {})))   # 고치기는 거의 같은 결과라 1장(크레딧)
        except Exception as e:
            return self._json(502, {"error": f"그림 만들기 실패: {gw.friendly_error(e)}"})
        urls = [{"url": self._save_img(name, data, ext)} for data, ext in out["images"]]
        el = round(time.time() - t0, 1)
        sys.stderr.write("[그림] %s %d장 %.1f초 · %s크레딧\n" % (out["model"], len(urls), el, out.get("credits")))
        head = f"{facts.get('head') or board_image.FACTS_HEAD}({facts['model']}).\n{facts['content']}\n\n" if facts else note
        return self._json(200, {"kind": "image", "content": head + f"그림 후보 {len(urls)}장 — 마음에 드는 것을 눌러 칠판에 붙여요", "images": urls, **getattr(self, "_extra", {}),
                                "model": out["model"], "elapsed": el, "credits": out.get("credits"), **({"sources": facts["sources"]} if facts and facts.get("sources") else {}),
                                **({"caption": caption} if caption else {})})

    def _find(self, name: str, query: str, key: str, k: int = 8) -> list:
        """칠판 `name`의 저장된 글에서 뜻으로 찾기(`board_find`) — 뜻 숫자는 칠판 옆 `<이름>.emb.json`에 모아 둔다."""
        if not name or not os.path.exists(self._doc_path(name)):
            return []
        with open(self._doc_path(name), encoding="utf-8") as f:
            doc = json.load(f)
        client = gw._client(key, gw.resolve_base_url(), timeout=60)
        return board_find.find(client, doc, query, k=k, cache_path=os.path.join(self.data_dir, name + ".emb.json"))

    # ── 회의록(§8 항목61 ③-3) — 녹음은 길어서 뒤 일감으로: POST가 일감 번호를 바로 주고, 브라우저가 GET으로 2초마다 확인 ──
    MAX_AUDIO = 300 * 1024 * 1024
    jobs = {}                     # 일감 번호 → {"board", "status": "run"|"done"|"error", "msg", "result"?, "error"?}

    def _meeting_start(self, name: str, q: dict):
        n = int(self.headers.get("Content-Length") or 0)
        if not name or n <= 0 or n > self.MAX_AUDIO:
            return self._json(413 if n > self.MAX_AUDIO else 400, {"error": "녹음 파일이 없거나 너무 커요(300MB까지)"})
        from urllib.parse import unquote
        fname = unquote(self.headers.get("X-File-Name") or "meeting.wav")
        if not fname.lower().endswith(meeting.AUDIO_EXT):
            return self._json(400, {"error": "녹음 파일(mp3·m4a·wav·webm·ogg·aac·flac·mp4)만 돼요"})
        data = self.rfile.read(n)
        key = self._key()
        if not key:
            return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다(~/.claude/.secrets/easycad-gateway.key)"})
        job = secrets.token_hex(6)
        model = (q.get("model") or [""])[0] or gw.FALLBACK_DEFAULT_MODEL
        Handler.jobs[job] = {"board": name, "status": "run", "msg": "받아쓰기 올리는 중…"}

        def run():
            def say(msg):
                Handler.jobs[job]["msg"] = msg
            try:
                res = meeting.make_minutes(key, data, fname, model=model, base_url=gw.resolve_base_url(), on_status=say)
                Handler.jobs[job].update(status="done", msg="끝", result=res)
                sys.stderr.write("[회의록] %s %.0f초 녹음 · %.1f크레딧\n" % (name, res["duration"], res["credits"]))
            except Exception as e:   # 브라우저에 그대로 보여 준다
                Handler.jobs[job].update(status="error", error=gw.friendly_error(e))
        threading.Thread(target=run, daemon=True).start()
        return self._json(200, {"job": job})

    def _meeting_live(self, name: str, q: dict):
        """POST /api/meeting/<이름>/live {"segments", "duration"} — 「🎙 회의」 실시간 받아 적은 구간 → 요약만(같은 일감 방식, 2026-10-23)"""
        req = self._body()
        segs = req.get("segments") if isinstance(req, dict) else None
        if not name or not isinstance(segs, list) or not segs:
            return self._json(400, {"error": "받아 적은 말이 없어요"})
        key = self._key()
        if not key:
            return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다(~/.claude/.secrets/easycad-gateway.key)"})
        job = secrets.token_hex(6)
        model = (q.get("model") or [""])[0] or gw.FALLBACK_DEFAULT_MODEL
        duration = float(req.get("duration") or 0)
        Handler.jobs[job] = {"board": name, "status": "run", "msg": "요약하는 중…"}

        def run():
            try:
                res = meeting.minutes_from_live(key, segs, model=model, duration=duration, base_url=gw.resolve_base_url())
                Handler.jobs[job].update(status="done", msg="끝", result=res)
                sys.stderr.write("[회의록 실시간] %s %.0f초 · %d구간\n" % (name, res["duration"], len(res["turns"])))
            except Exception as e:
                Handler.jobs[job].update(status="error", error=gw.friendly_error(e))
        threading.Thread(target=run, daemon=True).start()
        return self._json(200, {"job": job})

    def _trace_start(self, name: str):
        """POST /api/trace/<이름> {"data": 그림(data 주소·base64), "width": 칠판 폭} — 「도면으로 베끼기」(2026-10-25). 2~3분 → 회의록과 같은 일감 방식"""
        req = self._body(30 * 1024 * 1024) or {}
        raw = str(req.get("data") or "")
        if not name or not raw:
            return self._json(400, {"error": "베낄 그림이 없어요"})
        key = self._key()
        if not key:
            return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다(~/.claude/.secrets/easycad-gateway.key)"})
        try:
            png = base64.b64decode(raw.split(",", 1)[1] if raw.startswith("data:") else raw)
        except ValueError:
            return self._json(400, {"error": "그림을 못 읽었어요"})
        job, base = secrets.token_hex(6), gw.resolve_base_url()
        Handler.jobs[job] = {"board": name, "status": "run", "msg": "구역 6곳으로 나눠 그리는 중…", "done": 0, "total": 0}

        def run():
            b0, t0 = self._balance(key, base), time.time()
            try:
                res = board_trace.trace(key, png, width=float(req.get("width") or 0), base_url=base,
                                        progress=lambda i, n, t: Handler.jobs[job].update(done=i, total=n, msg=t))
                res.update(elapsed=round(time.time() - t0, 1), credits=self._spent(key, base, b0))
                Handler.jobs[job].update(status="done", msg="끝", result=res)
                sys.stderr.write("[베끼기] %s 도형 %d개 · %.0f초 · %s크레딧\n" % (name, len(res["items"]), res["elapsed"], res["credits"]))
            except Exception as e:
                Handler.jobs[job].update(status="error", error=gw.friendly_error(e))
        threading.Thread(target=run, daemon=True).start()
        return self._json(200, {"job": job})

    def _meeting_status(self, name: str, job: str):
        j = Handler.jobs.get(job)
        if not j or j["board"] != name:
            return self._send(404, b'{"error":"none"}')
        if j["status"] != "run":
            Handler.jobs.pop(job, None)   # 한 번 돌려주면 끝(서버 메모리에 안 쌓이게)
        return self._json(200, {k: v for k, v in j.items() if k != "board"})

    # ── PDF 보기 카드(2026-10-21) — 원본은 `<이름>.pdf/<번호>.pdf`, 칠판엔 주소만 ──
    MAX_PDF = 100 * 1024 * 1024

    def _pdf_put(self, name: str):
        """POST /api/pdf/<이름> (본문 = PDF, 머리말 X-File-Name) → {url, name, pages, sizes, thumb, text}"""
        n = int(self.headers.get("Content-Length") or 0)
        if not name or n <= 0 or n > self.MAX_PDF:
            return self._json(413 if n > self.MAX_PDF else 400, {"error": "PDF가 없거나 너무 커요(100MB까지)"})
        from urllib.parse import quote, unquote
        data = self.rfile.read(n)
        if not data.startswith(b"%PDF"):
            return self._json(400, {"error": "PDF 파일이 아니에요"})
        folder = os.path.join(self.data_dir, name + ".pdf")
        os.makedirs(folder, exist_ok=True)
        pid = f"{int(time.time() * 1000)}_{secrets.token_hex(3)}"
        path = os.path.join(folder, pid + ".pdf")
        write_via_temp(path, lambda tmp: _write(tmp, data))
        try:
            out = pdfview.info(path)
        except Exception as e:   # 깨진 PDF·암호 걸린 PDF
            os.remove(path)
            return self._json(400, {"error": f"PDF를 읽지 못했어요: {e}"})
        fname = os.path.basename(unquote(self.headers.get("X-File-Name") or "문서.pdf"))[:120]
        sys.stderr.write("[PDF] %s %s %d쪽\n" % (name, fname, out["pages"]))
        return self._json(200, {"url": f"/api/pdf/{quote(name)}/{pid}", "name": fname, **out})

    def _pdf_get(self, name: str, pid: str, what: str | None, page: int, q: dict):
        path = os.path.join(self.data_dir, name + ".pdf", pid + ".pdf") if name else ""
        if not path or not os.path.exists(path):
            return self._send(404, b'{"error":"none"}')
        if not what:   # 원본 — 브라우저 PDF 보기 화면(↗)
            with open(path, "rb") as f:
                return self._send(200, f.read(), ctype="application/pdf")
        try:
            r = [float(v) for v in ((q.get("r") or [""])[0]).split(",")] if what in ("clip", "text") else None
            if r is not None and len(r) != 4:
                return self._json(400, {"error": "r=x0,y0,x1,y1"})
            if what == "page":
                return self._send(200, pdfview.page_jpeg(path, page, int((q.get("w") or ["1200"])[0])), ctype="image/jpeg")
            if what == "clip":
                return self._send(200, pdfview.clip_png(path, page, r), ctype="image/png")
            if what == "lines":   # 보이지 않는 글 층(끌어 고르기)
                return self._json(200, {"lines": pdfview.lines(path, page)})
            return self._json(200, {"text": pdfview.clip_text(path, page, r)})
        except (IndexError, ValueError) as e:
            return self._json(400, {"error": str(e)})

    def _find_api(self, name: str):
        """POST /api/find/<이름> {q, k?} → {"results": [{uid, type, kind, text, score}]} — 칠판 Ctrl+F 「뜻으로 찾기」."""
        if not name:   # 나쁜 이름·다른 팀 칠판(§8 항목67)
            return self._send(400, b'{"error":"bad name"}')
        req = self._body(64 * 1024) or {}
        q = str(req.get("q") or "").strip()[:500]
        if not q:
            return self._json(200, {"results": []})
        key = self._key()
        if not key:
            return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다 — 낱말 찾기만 돼요"})
        try:
            res = self._find(name, q, key, k=max(1, min(20, int(req.get("k") or 8))))
        except Exception as e:
            return self._json(502, {"error": gw.friendly_error(e)})
        return self._json(200, {"results": [{**r, "text": r["text"][:300]} for r in res]})

    def _link(self):
        _, q = self._route()
        url, embed = (q.get("url") or [""])[0], (q.get("embed") or [""])[0]
        if not re.match(r"^https?://", url):
            return self._json(400, {"error": "http(s) 주소만"})
        return self._json(200, link_info(url, embed if re.match(r"^https?://", embed) else ""))

    def _send(self, code: int, body: bytes = b"", ctype: str = "application/json; charset=utf-8", headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    # ── 공동작업 1단계(§8 항목61 ⓕ, 2026-10-18) — 공용 비밀번호·부분 저장·게시·접속자(계산은 `collab.py`) ──
    def _authed(self) -> bool:
        """편집 열쇠(쿠키)가 맞나 — 관리자(공용 비밀번호) 또는 팀(§8 항목67). 비밀번호도 팀도 없으면(내 PC 개발) 누구나."""
        if not self._locked():
            return True
        c = collab.cookie_value(self.headers.get("Cookie"))
        return bool(self.password and c == collab.edit_key(self.password)) or self._team() is not None

    def _teams(self) -> collab.Teams:
        return collab.Teams.at(self.data_dir)

    def _locked(self) -> bool:
        """들어올 때 비밀번호가 필요한 서버인가 — 공용 비밀번호가 있거나 `teams.json`이 있으면(깨졌어도 — 열리면 안 됨)"""
        return bool(self.password) or self._teams().exists

    def _team(self) -> dict | None:
        """이 요청의 팀(쿠키가 팀 열쇠면) — 관리자·로그인 전·팀 없는 서버는 None(= 칠판 이름을 가리지 않음)"""
        t = self._teams()
        return t.by_cookie(collab.cookie_value(self.headers.get("Cookie"))) if t.teams else None

    def _set_key(self, key: str):
        return self._send(200, b'{"ok":true}', headers={"Set-Cookie": f"mb_key={key}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"})

    def _body(self, limit: int = MAX_BYTES):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > limit:
            return None
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return None

    def _name(self, raw: str, team: bool = True) -> str:
        """주소·본문의 칠판 이름 → 쓸 이름, 나쁘면 "". 팀 열쇠면 그 팀이 못 쓰는 칠판도 ""(§8 항목67 — 뒤는 모두 「나쁜 이름」으로 거절).
        고치는 요청(POST·PUT — 접속 신호·찾기 빼고)이 새 이름을 쓰면 그 팀 칠판으로 등록. team=False = 로그인 전 길(초대 링크)."""
        from urllib.parse import unquote
        name = unquote(raw)
        if not NAME_RE.match(name):
            return ""
        t = self._team() if team else None
        if t is None:
            return name
        claim = self.command in ("POST", "PUT") and not self.path.startswith(("/api/presence/", "/api/find/"))
        return name if self._teams().allows(t, name, self.data_dir, claim=claim) else ""

    def _doc_path(self, name: str) -> str:
        return os.path.join(self.data_dir, name + ".ecad")

    def _doc_load(self, name: str):
        """칠판 문서 — uid가 없으면 붙여 저장(모든 브라우저가 같은 이름표를 받게). 없으면 None."""
        path = self._doc_path(name)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            doc = json.loads(f.read())
        if collab.ensure_uids(doc):
            self._doc_save(name, doc)
        return doc

    def _doc_save(self, name: str, doc: dict):
        os.makedirs(self.data_dir, exist_ok=True)
        path = self._doc_path(name)
        if os.path.exists(path):
            root, ext = os.path.splitext(path)
            write_via_temp(root + ".prev" + ext, lambda tmp: _copy(path, tmp))
        raw = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        write_via_temp(path, lambda tmp: _write(tmp, raw))
        with Handler.changed:
            Handler.revs[name] = int(doc.get("rev") or 0)
            Handler.changed.notify_all()

    def _wait_rev(self, name: str, rev: int, q) -> None:
        """`wait=N`(초, 최대 25)이면 판 번호가 rev보다 커질 때까지 기다림 — 바뀌는 즉시 돌려줘서 0.x초 안에 보임"""
        try:
            secs = min(25.0, float((q.get("wait") or ["0"])[0]))
        except ValueError:
            secs = 0
        if secs <= 0 or rev < 0:
            return
        if name not in Handler.revs:   # 서버를 켠 뒤 처음 — 파일에서 한 번
            d = self._doc_load(name)
            Handler.revs[name] = int((d or {}).get("rev") or 0)
        end = time.time() + secs
        with Handler.changed:
            while Handler.revs.get(name, 0) <= rev and time.time() < end:
                Handler.changed.wait(end - time.time())

    def _publish_map(self, kind: str = "publish") -> dict:
        """칠판 → 토큰 표. publish = 게시(보기) 링크, invite = 편집 초대 링크(2026-10-19 — 노션 「공유」, 비밀번호 대신 링크로 편집)"""
        path = os.path.join(self.data_dir, f"{kind}.json")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _publish_save(self, mp: dict, kind: str = "publish"):
        os.makedirs(self.data_dir, exist_ok=True)
        raw = json.dumps(mp, ensure_ascii=False).encode("utf-8")
        write_via_temp(os.path.join(self.data_dir, f"{kind}.json"), lambda tmp: _write(tmp, raw))

    def _route(self):
        from urllib.parse import parse_qs, urlparse
        u = urlparse(self.path)
        return u.path, parse_qs(u.query)

    def do_GET(self):
        path, q = self._route()
        if path == "/api/session":   # 비밀번호가 필요한가·이미 들어왔나 (+ 팀 서버면 내 팀·이 칠판을 써도 되나·우리 팀 첫 칠판 — §8 항목67)
            out = {"auth": self._locked(), "ok": self._authed()}
            if out["ok"] and self._teams().exists:
                t = self._team()
                out["team"] = t["name"] if t else None
                if q.get("board"):
                    out["board_ok"] = bool(self._name(q["board"][0]))
                if t:
                    out["home"] = next(iter(t["boards"]), "") or (t["name"] if self._name(t["name"]) else "")
            return self._json(200, out)
        m = re.match(r"^/api/pub/([\w\-]{8,64})$", path)
        if m:   # 게시 링크 — 로그인 없이 보기만
            board = next((b for b, t in self._publish_map().items() if t == m.group(1)), None)
            if board:
                self._wait_rev(board, int((q.get("rev") or ["-1"])[0]), q)
            doc = board and self._doc_load(board)
            if not doc:
                return self._send(404, b'{"error":"none"}')
            rev = int((q.get("rev") or ["-1"])[0])
            if rev >= int(doc.get("rev") or 0) and rev >= 0:
                return self._send(204)
            return self._json(200, dict(doc, board=board))
        m = re.match(r"^/api/pdf/([^/]+)/(\d+_[0-9a-f]{6})(?:/(page|clip|text|lines)/(\d+))?$", path)
        if m and not self._authed() and self._name(m.group(1), team=False) in self._publish_map():   # 게시한 칠판의 PDF = 로그인 없이 보기(게시 링크에서 쪽 그림이 401이었음, 2026-10-22)
            return self._pdf_get(self._name(m.group(1), team=False), m.group(2), m.group(3), int(m.group(4) or 0), q)
        if path.startswith("/api/") and not self._authed():
            return self._send(401, b'{"error":"login"}')
        if path == "/api/models":
            return self._models()
        if path == "/api/credits":   # 대화창 머리줄 「남은 크레딧」(2026-10-21 사용자 — baze CLI 검토) — 이 요청의 키(「🔑 내 키」면 그 사람 것)
            key = self._key()
            if not key:
                return self._json(503, {"error": "키 없음"})
            try:
                remaining, quota = gw.get_credit_balance(key, gw.resolve_base_url())
            except Exception as e:   # 못 받아도 대화는 됨 — 화면은 숫자를 안 보임
                return self._json(502, {"error": str(e)})
            return self._json(200, {"remaining": remaining, "quota": quota})
        if path == "/api/boards":   # 칠판 목록(데스크톱 「웹 칠판 열기」, §8 항목61 ④-2) — 최근에 고친 것부터
            out = []
            for fn in os.listdir(self.data_dir) if os.path.isdir(self.data_dir) else []:
                name = fn[:-5] if fn.endswith(".ecad") else ""
                if not NAME_RE.match(name) or not self._name(name):   # `<이름>.prev.ecad`(되돌림용 앞 판) 등은 뺌, 팀이면 그 팀 칠판만(§8 항목67)
                    continue
                p = os.path.join(self.data_dir, fn)
                try:
                    with open(p, encoding="utf-8") as f:
                        n = len(json.load(f).get("items") or [])
                except (OSError, ValueError):
                    continue
                out.append({"name": name, "mtime": int(os.path.getmtime(p)), "items": n})
            return self._json(200, {"boards": sorted(out, key=lambda b: -b["mtime"])})
        m = re.match(r"^/api/(?:meeting|trace)/([^/]+)/([0-9a-f]{12})$", path)   # 일감 확인(회의록·베끼기 같은 방식)
        if m:
            return self._meeting_status(self._name(m.group(1)), m.group(2))
        m = re.match(r"^/api/img/([^/]+)/(\d+_[0-9a-f]{6}\.(png|jpg|webp))$", path)
        if m:   # 그림 후보(대화창 미리보기·칠판에 붙일 때 가져감)
            name = self._name(m.group(1))
            p = os.path.join(self._img_dir(name), m.group(2)) if name else ""
            if not p or not os.path.exists(p):
                return self._send(404, b'{"error":"none"}')
            with open(p, "rb") as f:
                return self._send(200, f.read(), ctype={"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[m.group(3)])
        m = re.match(r"^/api/pdf/([^/]+)/(\d+_[0-9a-f]{6})(?:/(page|clip|text|lines)/(\d+))?$", path)
        if m:   # PDF 보기 카드 — 원본(↗ 새 탭)·쪽 그림·오려 오기·그 부분 글(`pdfview.py`)
            return self._pdf_get(self._name(m.group(1)), m.group(2), m.group(3), int(m.group(4) or 0), q)
        if path == "/api/link":
            return self._link()
        if path == "/api/symbols":   # 「내 심볼」 — 데스크톱과 같은 파일(git으로 PC 간 동기화), 웹은 읽기만
            lib = os.path.join(os.path.dirname(HERE), "symbol_library", "symbol_library.json")
            if not os.path.exists(lib):
                return self._send(404, b'{"error":"none"}')
            with open(lib, "rb") as f:
                return self._send(200, f.read())
        m = re.match(r"^/api/(doc|since|publish|invite)/([^/]+)$", path)
        if m:
            name = self._name(m.group(2))
            if not name:
                return self._send(400, b'{"error":"bad name"}')
            if m.group(1) in ("publish", "invite"):
                return self._json(200, {"token": self._publish_map(m.group(1)).get(name), "password": self._locked()})
            if m.group(1) == "since":
                self._wait_rev(name, int((q.get("rev") or ["0"])[0]), q)
            doc = self._doc_load(name)
            if doc is None:
                if m.group(1) == "since":
                    return self._send(204)   # 아직 저장 안 한 새 칠판 = 바뀐 것 없음(404면 브라우저 콘솔에 오류가 쌓임)
                return self._send(404, b'{"error":"none"}')
            if m.group(1) == "since" and int((q.get("rev") or ["0"])[0]) >= int(doc.get("rev") or 0):
                return self._send(204)   # 그 뒤로 바뀐 것 없음
            return self._json(200, doc)
        p = self._board_path()
        if p is None:
            # 화면: 없는 경로는 index.html(한 페이지 앱)
            if not os.path.exists(os.path.join(self.directory, self.path.lstrip("/").split("?")[0])):
                self.path = "/index.html"
            return super().do_GET()
        if p == "":
            return self._send(400, b'{"error":"bad name"}')
        if not os.path.exists(p):
            if p.endswith(".meet.json"):
                return self._send(204)   # 받아 적던 회의 없음 = 보통(칠판 열 때마다 물어봄 — 404면 콘솔에 오류가 쌓임)
            return self._send(404, b'{"error":"none"}')
        with open(p, "rb") as f:
            self._send(200, f.read())

    def do_POST(self):
        path, _ = self._route()
        if path == "/api/login":
            req = self._body(64 * 1024) or {}
            if not self._locked():
                return self._json(200, {"ok": True})
            pw = str(req.get("password") or "")
            if self.password and secrets.compare_digest(pw.encode("utf-8"), self.password.encode("utf-8")):   # 관리자 = 모든 칠판
                return self._set_key(collab.edit_key(self.password))
            team = self._teams().by_password(pw)   # 팀 비밀번호 = 그 팀 열쇠(§8 항목67)
            if team:
                return self._set_key(collab.team_key(team))
            time.sleep(0.5)   # 마구 넣어 보기 늦추기
            return self._send(403, b'{"error":"password"}')
        if path == "/api/join":   # 편집 초대 링크로 들어옴 — 맞으면 편집 열쇠 쿠키(비밀번호 없이)
            req = self._body(64 * 1024) or {}
            board = self._name(str(req.get("board") or ""), team=False)   # 다른 팀 열쇠를 든 채 눌러도 그 칠판으로(팀 검사 없이)
            tok = self._publish_map("invite").get(board) if board else None
            if not tok or not collab._same(str(req.get("token") or ""), tok):
                time.sleep(0.5)
                return self._send(403, b'{"error":"invite"}')
            if not self._locked():
                return self._json(200, {"ok": True})
            owner = self._teams().owner(board)
            if owner:   # 팀 칠판 초대 = 그 팀 열쇠(그 팀 다른 칠판도 열림 — 노션 초대와 같게 받아들임, §8 항목67)
                return self._set_key(collab.team_key(owner))
            if not self.password:   # 팀 없는 칠판인데 관리자 비밀번호도 없음 — 줄 열쇠가 없음
                return self._send(403, b'{"error":"invite"}')
            return self._set_key(collab.edit_key(self.password))
        if not self._authed():
            return self._send(401, b'{"error":"login"}')
        if path == "/api/chat":
            return self._chat()
        if path == "/api/ocr":   # 「그림 속 글 읽기」 — 본문 = {data: PNG base64}(칠판 그림 그대로)
            req = self._body(30 * 1024 * 1024) or {}
            key = self._key()
            if not key:
                return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다"})
            try:
                out = board_ocr.read(key, base64.b64decode(req.get("data") or ""), base_url=gw.resolve_base_url())
            except Exception as e:
                return self._json(502, {"error": f"글 읽기 실패: {gw.friendly_error(e)}"})
            sys.stderr.write("[글 읽기] %s %.1f초 %d자\n" % (out["model"], out["elapsed"], len(out["text"])))
            return self._json(200, out)
        if path == "/api/stt-token":   # 대화창 🎤 — 실시간 받아쓰기 일회용 표(키는 서버에만, 2026-10-20)
            key = self._key()
            if not key:
                return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다"})
            try:
                return self._json(200, meeting.live_token(key, base_url=gw.resolve_base_url()))
            except Exception as e:
                return self._json(502, {"error": str(e)})
        m = re.match(r"^/api/find/([^/]+)$", path)
        if m:
            return self._find_api(self._name(m.group(1)))
        m = re.match(r"^/api/meeting/([^/]+)/live$", path)
        if m:
            return self._meeting_live(self._name(m.group(1)), self._route()[1])
        m = re.match(r"^/api/meeting/([^/]+)$", path)
        if m:
            return self._meeting_start(self._name(m.group(1)), self._route()[1])
        m = re.match(r"^/api/pdf/([^/]+)$", path)
        if m:
            return self._pdf_put(self._name(m.group(1)))
        m = re.match(r"^/api/trace/([^/]+)$", path)
        if m:
            return self._trace_start(self._name(m.group(1)))
        m = re.match(r"^/api/(patch|presence|publish|invite)/([^/]+)$", path)
        if not m:
            return self._send(404, b'{"error":"none"}')
        name = self._name(m.group(2))
        req = self._body()
        if not name or not isinstance(req, dict):
            return self._send(400, b'{"error":"bad request"}')
        if m.group(1) == "presence":
            cid = str(req.get("id") or "")
            if req.get("leave"):   # 창 닫힘(브라우저 pagehide) = 바로 뺌
                self.presence.leave(name, cid)
                return self._json(200, {"ok": True})
            people = self.presence.ping(name, cid, str(req.get("name") or ""), sel=req.get("sel") if isinstance(req.get("sel"), list) else None, edit=str(req.get("edit") or ""))
            return self._json(200, {"people": people, "others": self.presence.others(name, cid)})
        if m.group(1) in ("publish", "invite"):   # 켜기·끄기·새 링크(옛 링크 막힘) — 게시와 초대가 같은 방식
            kind = m.group(1)
            with self.lock:
                mp = self._publish_map(kind)
                if not req.get("on"):
                    mp.pop(name, None)
                elif req.get("renew") or name not in mp:
                    mp[name] = secrets.token_urlsafe(12)
                self._publish_save(mp, kind)
            return self._json(200, {"token": mp.get(name)})
        with self.lock:   # 부분 저장 — 도형 단위로 덮어씀(서로 다른 도형이면 둘 다 남음)
            doc = self._doc_load(name) or {"format": "easycad-doc", "version": 1, "items": []}
            out = collab.apply_patch(doc, req)
            self._doc_save(name, out)
        return self._json(200, {"rev": out["rev"]})

    def do_PUT(self):
        if not self._authed():
            return self._send(401, b'{"error":"login"}')
        p = self._board_path()
        if not p:
            return self._send(400, b'{"error":"bad name"}')
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._send(413, b'{"error":"size"}')
        raw = self.rfile.read(n)
        try:
            doc = json.loads(raw)   # 깨진 내용으로 좋은 저장본을 덮지 않게
        except ValueError:
            return self._send(400, b'{"error":"json"}')
        if p.endswith(".ecad"):   # 통째 저장(파일 열기 등) — 판 번호를 올려 다른 브라우저가 받아 가게
            name = os.path.basename(p)[:-5]
            with self.lock:
                old = self._doc_load(name) or {}
                collab.ensure_uids(doc)
                doc["rev"] = int(old.get("rev") or 0) + 1
                self._doc_save(name, doc)
            return self._json(200, {"ok": True, "rev": doc["rev"]})
        os.makedirs(self.data_dir, exist_ok=True)
        with self.lock:
            moved, rev = 0, None
            if p.endswith(".chat.json") and isinstance(doc, dict):   # 대화 기록 = 판 번호로 합치기(두 창이 덮어쓰던 것, 2026-10-26 점검)
                try:
                    with open(p, encoding="utf-8") as f:
                        old = json.load(f)
                except (OSError, ValueError):
                    old = None
                doc, moved = collab.merge_chatlog(old if isinstance(old, dict) else None, doc)
                raw, rev = json.dumps(doc, ensure_ascii=False).encode("utf-8"), doc["rev"]
            if os.path.exists(p):
                root, ext = os.path.splitext(p)
                prev = root + ".prev" + ext
                write_via_temp(prev, lambda tmp: _copy(p, tmp))
            write_via_temp(p, lambda tmp: _write(tmp, raw))
        if rev is None:
            return self._send(200, b'{"ok":true}')
        self._json(200, {"ok": True, "rev": rev, "moved": moved})

    def log_message(self, fmt, *args):   # 저장 요청만 짧게(대화는 `_chat`이 따로 남김)
        if self.command == "PUT":
            sys.stderr.write("[저장] %s %s\n" % (self.path, args[1] if len(args) > 1 else ""))


# ── 웹 카드(§8 항목61 4-b ①', 2026-10-18) — 주소를 서버가 대신 열어 「칸 안에 넣어도 되나·제목·대표 그림」을 알려 준다.
# 브라우저는 남의 사이트가 넣기를 막았는지 알 수 없다(막힌 페이지도 「다 불러옴」 신호가 똑같이 옴) → 응답 머리말로 판단.
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
_THUMB_MAX = 400 * 1024   # 대표 그림은 문서에 data 주소로 들어가니(서버 없이도·내보내기에도 보이게) 크기 상한
_ICON_MAX = 64 * 1024   # 사이트 아이콘(대표 그림 없는 막힌 사이트 카드 — 2026-10-19 사용자: ChatGPT 카드가 제목 띠만)


def frame_blocked(headers) -> bool:
    """X-Frame-Options(DENY·SAMEORIGIN) 또는 CSP frame-ancestors(별표 없음)면 남의 페이지 안에 못 넣는다."""
    xfo = " ".join(headers.get_all("X-Frame-Options") or []).lower()
    if "deny" in xfo or "sameorigin" in xfo:
        return True
    for csp in headers.get_all("Content-Security-Policy") or []:
        for part in csp.split(";"):
            p = part.strip().lower()
            if p.startswith("frame-ancestors") and "*" not in p.split()[1:]:
                return True
    return False


def _meta(html: str, *names) -> str:
    import html as _h
    for n in names:   # <meta property="og:title" content="…"> — 속성 차례는 사이트마다 다름
        for pat in (rf'<meta[^>]+(?:property|name)=["\']{re.escape(n)}["\'][^>]*content=["\']([^"\']*)',
                    rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']{re.escape(n)}["\']'):
            m = re.search(pat, html, re.I)
            if m and m.group(1).strip():
                return _h.unescape(m.group(1).strip())
    return ""


def _decode(raw: bytes, headers) -> str:
    cs = headers.get_content_charset()
    if not cs:
        m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:4096], re.I)
        cs = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    try:
        return raw.decode(cs, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _open(url: str, limit: int):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "ko,en;q=0.8"})
    r = urllib.request.urlopen(req, timeout=6)
    return r, r.read(limit + 1)


def link_info(url: str, embed: str = "") -> dict:
    """주소 → { url, title, desc, icon(data 주소|""), thumb(data 주소|""), frameable, embed }. 못 열어도 오류 대신 「모름」(칸 안에 넣지 않고 새 탭으로)."""
    import base64
    import html as _h
    from urllib.parse import urljoin
    out = {"url": url, "embed": embed, "title": "", "desc": "", "icon": "", "thumb": "", "frameable": False}

    def data_url(src, limit):   # 그림 주소 → data 주소(그림이 아니거나 크면 "")
        try:
            ri, data = _open(src, limit)
            ct = ri.headers.get_content_type() or ""
            if (ct.startswith("image/") or src.lower().endswith(".ico")) and len(data) <= limit:
                return "data:%s;base64,%s" % (ct if ct.startswith("image/") else "image/x-icon", base64.b64encode(data).decode("ascii"))
        except Exception:
            pass
        return ""
    page, img = "", ""
    try:
        r, raw = _open(url, 1024 * 1024)
        page = _decode(raw, r.headers)
        out["title"] = _meta(page, "og:title", "twitter:title") or _h.unescape(
            (re.search(r"<title[^>]*>([^<]*)", page, re.I) or [None, ""])[1].strip())
        out["desc"] = _meta(page, "og:description", "description", "twitter:description")[:200]
        img = _meta(page, "og:image", "twitter:image")
        out["frameable"] = not frame_blocked(r.headers)
    except Exception as e:   # 사내망·로그인 필요·없는 주소 — 카드는 주소(+ 잡히면 아이콘)만으로
        sys.stderr.write("[웹 카드] %s 열기 실패: %s\n" % (url, e))
    # 아이콘 — <link rel="icon"> 먼저, 없으면 사이트 뿌리의 /favicon.ico(페이지가 막혀도 이건 열리는 곳이 있음)
    m = re.search(r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]*href=["\']([^"\']+)', page, re.I) or \
        re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\'][^"\']*icon', page, re.I)
    for src in ([urljoin(url, _h.unescape(m.group(1)))] if m else []) + [urljoin(url, "/favicon.ico")]:
        if src.startswith("http") and not src.lower().split("?")[0].endswith(".svg"):
            out["icon"] = data_url(src, _ICON_MAX)
            if out["icon"]:
                break
    # 유튜브 — 서버가 열면 진짜 페이지 대신 다른 화면이 와서 제목이 「- YouTube」·그림 없음(2026-10-19 확인) → 공식 oEmbed로 제목·썸네일
    if embed.startswith("https://www.youtube.com/embed/"):
        try:
            from urllib.parse import quote
            _, oe = _open("https://www.youtube.com/oembed?format=json&url=" + quote(url, safe=""), 64 * 1024)
            j = json.loads(oe.decode("utf-8"))
            out["title"] = j.get("title") or out["title"]
            if j.get("author_name"):
                out["desc"] = j["author_name"]
            img = j.get("thumbnail_url") or img
        except Exception:
            pass
    if not page and not img:
        return out
    if embed:   # 재생용 주소(유튜브 embed 등)는 그 주소의 머리말로 다시 판단
        try:
            out["frameable"] = not frame_blocked(_open(embed, 0)[0].headers)
        except Exception:
            out["frameable"] = False
    if img:
        out["thumb"] = data_url(urljoin(url, img), _THUMB_MAX)
    return out


def _write(path: str, raw: bytes):
    with open(path, "wb") as f:
        f.write(raw)


def _copy(src: str, dst: str):
    with open(src, "rb") as a, open(dst, "wb") as b:
        b.write(a.read())


class _Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        """브라우저가 기다리던 요청을 끊고 떠남(탭 닫기·새로고침 — 롱 폴링이면 늘 생김)은 조용히. 나머지 오류는 그대로 찍는다(2026-10-19 다잡기)."""
        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):   # 출력을 파일로 돌리면(cp949) 「—」 등에서 바로 꺼졌음(2026-10-19) — 못 쓰는 글자는 ?로
        try: s.reconfigure(errors="replace")
        except (AttributeError, ValueError): pass
    ap = argparse.ArgumentParser(description="Magic Board 웹 칠판 서버")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5191)
    ap.add_argument("--data", default=default_data_dir())
    ap.add_argument("--password", default=os.environ.get("MB_PASSWORD", ""), help="공용 편집 비밀번호(없으면 데이터 폴더의 edit_password.txt, 그것도 없으면 누구나 편집)")
    a = ap.parse_args(argv)
    Handler.data_dir = a.data
    pw_file = os.path.join(a.data, "edit_password.txt")
    Handler.password = a.password or (open(pw_file, encoding="utf-8").read().strip() if os.path.exists(pw_file) else "")
    gw.preload_network()   # 통신 부품을 먼저 — 두 요청이 동시에 처음 부르면 모듈 잠금 교착(gateway.preload_network 참조)
    if not os.path.isdir(os.path.join(HERE, "dist")):
        print("web/dist가 없습니다 — 먼저 `cd web && npm run build` (API만 씁니다)")
    print(f"Magic Board 칠판: http://{'localhost' if a.host in ('0.0.0.0', '127.0.0.1') else a.host}:{a.port}  · 저장 폴더: {a.data}")
    print("편집: " + ("공용 비밀번호 필요" if Handler.password else "누구나(비밀번호 없음 — --password 또는 edit_password.txt로 정함)"))
    teams = collab.Teams.at(a.data)
    if teams.exists:   # 팀별 칠판(§8 항목67)
        print("팀: " + (", ".join(f"{t['name']}(칠판 {len(t['boards'])}개{', 키 따로' if t['key'] else ''})" for t in teams.teams) or "없음 — teams.json을 확인해 주세요")
              + (" · 관리자 = 공용 비밀번호" if Handler.password else " · 관리자 없음"))
    threading.Thread(target=_route_check_weekly, args=(a.data,), daemon=True).start()
    if gw.resolve_api_key():   # 모델 목록을 먼저 받아 둠 — 은퇴한 모델을 첫 요청부터 대신할 것으로(`model_pick` ①) + 「모델 설정」 그림 값(무료 견적), 2026-10-26
        def warm(key=gw.resolve_api_key(), base=gw.resolve_base_url()):
            model_pick.load(key, base)
            model_pick.price_images(key, gw._normalize_base_url(base))
        threading.Thread(target=warm, daemon=True).start()
    _Server((a.host, a.port), Handler).serve_forever()


def _route_check_weekly(data_dir: str):
    """길 고르기 주간 자가 시험(2026-10-20 사용자 선택 — 판단 과목만 매주) — 판단 모델이 규칙보다 못하면 규칙만 쓰게, 결과는 `route_check.json`."""
    if os.environ.get("EASYCAD_ROUTE") == "rules":
        return
    path = os.path.join(data_dir, "route_check.json")
    while True:
        try:
            last = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        except (OSError, ValueError):
            last = {}
        wait = int(last.get("at") or 0) + 7 * 86400 - time.time()
        if wait > 0:   # 지난 결과가 아직 1주 안 — 그 결과를 따름
            route.state["ai"] = bool(last.get("use_ai", True))
            time.sleep(min(wait, 86400))
            continue
        key = gw.resolve_api_key()
        if key:
            res = route.self_check(key, base_url=gw.resolve_base_url())
            raw = json.dumps(res, ensure_ascii=False).encode("utf-8")
            os.makedirs(data_dir, exist_ok=True)
            write_via_temp(path, lambda tmp: _write(tmp, raw))
            sys.stderr.write("[길 시험] %s %d/%d · 규칙 %d · 오류 %d → %s\n" % (res["model"], res["ai"], res["of"], res["rules"], res["errors"], "판단 모델" if res["use_ai"] else "규칙만"))
        time.sleep(86400)


if __name__ == "__main__":
    main()
