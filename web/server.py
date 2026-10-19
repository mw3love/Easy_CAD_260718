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
⚠ 사내망 `http`라 비밀번호·열쇠가 암호화 없이 오간다 — 회사 보안 확인 전엔 내 PC에서만(`--host 127.0.0.1`).

실행: python web/server.py [--host 0.0.0.0] [--port 5191] [--data 폴더]
데이터 폴더 기본값: %APPDATA%/EasyCAD/web_boards (데스크톱 앱 설정·자동 저장과 같은 곳 — git에 안 들어감)
"""
from __future__ import annotations

import argparse
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
from easycad.ai import board_chat, gateway as gw  # noqa: E402  (Qt 안 씀 — 키 찾기만 QSettings를 늦게 부른다)
sys.path.insert(0, HERE)
import collab  # noqa: E402  (공동작업 계산 — web/collab.py)

NAME_RE = re.compile(r"^[\w\-가-힣]{1,64}$")
MAX_BYTES = 200 * 1024 * 1024   # 그림이 든 칠판도 넉넉히, 하지만 끝없이는 아니게
_MODELS = None                  # (받은 시각, 모델 목록) — `/api/models`


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
        """칠판 문서(`/api/doc/<이름>` → `<이름>.ecad`)·대화 기록(`/api/chatlog/<이름>` → `<이름>.chat.json`) 파일 자리.
        API 경로가 아니면 None, 이름이 나쁘면 ""."""
        m = re.match(r"^/api/(chatlog|doc)/([^/?#]+)$", self.path)
        if not m:
            return None
        from urllib.parse import unquote
        name = unquote(m.group(2))
        ext = {"chatlog": ".chat.json", "doc": ".ecad"}[m.group(1)]
        return os.path.join(self.data_dir, name + ext) if NAME_RE.match(name) else ""

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _models(self):
        key = gw.resolve_api_key()
        if not key:
            return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다(~/.claude/.secrets/easycad-gateway.key)"})
        global _MODELS
        if _MODELS is None or time.time() - _MODELS[0] > 600:   # 10분마다 새로(새 모델이 올라와도 서버를 안 껐다 켜게)
            try:
                _MODELS = (time.time(), board_chat.models(key, gw.resolve_base_url()))
            except Exception as e:   # 목록을 못 받아도 대화는 기본 모델로 된다
                return self._json(200, {"default": gw.FALLBACK_DEFAULT_MODEL, "featured": {}, "error": str(e)})
        return self._json(200, _MODELS[1])

    def _chat(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 4 * 1024 * 1024:
            return self._json(413, {"error": "질문이 너무 큽니다"})
        try:
            req = json.loads(self.rfile.read(n))
        except ValueError:
            return self._json(400, {"error": "json"})
        key = gw.resolve_api_key()
        if not key:
            return self._json(503, {"error": "이 서버 PC에 KAIROS 키가 없습니다(~/.claude/.secrets/easycad-gateway.key)"})
        try:
            out = board_chat.chat(key, req.get("messages") or [], model=req.get("model") or gw.FALLBACK_DEFAULT_MODEL,
                                  context=req.get("context") or "", base_url=gw.resolve_base_url())
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:   # 게이트웨이 오류는 대화창에 그대로 보여 준다(조용히 다른 모델로 갈아타지 않음)
            return self._json(502, {"error": f"KAIROS 호출 실패: {e}"})
        sys.stderr.write("[대화] %s %.1f초\n" % (out["model"], out["elapsed"]))
        return self._json(200, out)

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
        """편집 열쇠(쿠키)가 맞나 — 비밀번호를 안 정했으면(내 PC 개발) 누구나."""
        return not self.password or collab.cookie_value(self.headers.get("Cookie")) == collab.edit_key(self.password)

    def _body(self, limit: int = MAX_BYTES):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > limit:
            return None
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return None

    def _name(self, raw: str) -> str:
        from urllib.parse import unquote
        name = unquote(raw)
        return name if NAME_RE.match(name) else ""

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
        if path == "/api/session":   # 비밀번호가 필요한가·이미 들어왔나
            return self._json(200, {"auth": bool(self.password), "ok": self._authed()})
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
        if path.startswith("/api/") and not self._authed():
            return self._send(401, b'{"error":"login"}')
        if path == "/api/models":
            return self._models()
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
                return self._json(200, {"token": self._publish_map(m.group(1)).get(name), "password": bool(self.password)})
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
            return self._send(404, b'{"error":"none"}')
        with open(p, "rb") as f:
            self._send(200, f.read())

    def do_POST(self):
        path, _ = self._route()
        if path == "/api/login":
            req = self._body(64 * 1024) or {}
            if not self.password:
                return self._json(200, {"ok": True})
            if req.get("password") != self.password:
                time.sleep(0.5)   # 마구 넣어 보기 늦추기
                return self._send(403, b'{"error":"password"}')
            key = collab.edit_key(self.password)
            return self._send(200, b'{"ok":true}', headers={"Set-Cookie": f"mb_key={key}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"})
        if path == "/api/join":   # 편집 초대 링크로 들어옴 — 맞으면 편집 열쇠 쿠키(비밀번호 없이)
            req = self._body(64 * 1024) or {}
            board = self._name(str(req.get("board") or ""))
            tok = self._publish_map("invite").get(board) if board else None
            if not tok or not secrets.compare_digest(str(req.get("token") or ""), tok):
                time.sleep(0.5)
                return self._send(403, b'{"error":"invite"}')
            if not self.password:
                return self._json(200, {"ok": True})
            key = collab.edit_key(self.password)
            return self._send(200, b'{"ok":true}', headers={"Set-Cookie": f"mb_key={key}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"})
        if not self._authed():
            return self._send(401, b'{"error":"login"}')
        if path == "/api/chat":
            return self._chat()
        m = re.match(r"^/api/(patch|presence|publish|invite)/([^/]+)$", path)
        if not m:
            return self._send(404, b'{"error":"none"}')
        name = self._name(m.group(2))
        req = self._body()
        if not name or not isinstance(req, dict):
            return self._send(400, b'{"error":"bad request"}')
        if m.group(1) == "presence":
            cid = str(req.get("id") or "")
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
        if os.path.exists(p):
            root, ext = os.path.splitext(p)
            prev = root + ".prev" + ext
            write_via_temp(prev, lambda tmp: _copy(p, tmp))
        write_via_temp(p, lambda tmp: _write(tmp, raw))
        self._send(200, b'{"ok":true}')

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
    _Server((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
