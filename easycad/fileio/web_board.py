"""데스크톱 ↔ 웹 칠판 서버(`web/server.py`) — 칠판 목록·받기·올리기(§8 항목61 ④-2, 2026-10-19, Qt 비의존).

두 앱의 다리는 `.ecad` 그대로다 — 서버가 칠판을 `<이름>.ecad`로 두므로 데스크톱 문서를 통째로 PUT하면 웹 칠판이 되고,
GET하면 데스크톱이 여는 파일과 같은 JSON이 온다. 팀 비밀번호가 있는 서버면 먼저 `/api/login`으로 편집 열쇠 쿠키를 받는다(쿠키는 이 객체에만).
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request

NAME_RE = re.compile(r"^[\w\-가-힣]{1,64}$")   # 서버 `NAME_RE`와 같음
DEFAULT_URL = "http://localhost:5191"


class WebBoardError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 한국어 오류."""


def board_from_text(text: str) -> str:
    """칠판 주소(…?board=이름) 또는 이름 그대로 → 이름(웹 「주소 복사」를 그대로 붙여 넣어도 되게)."""
    t = (text or "").strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(t).query).get("board") if "board=" in t else None
    return clean_name(q[0] if q else t)


def clean_name(name: str) -> str:
    """칠판 이름 — 서버가 받는 글자(영문·숫자·_·-·한글)만 남기고 64자까지."""
    return re.sub(r"[^\w\-가-힣]", "", (name or "").strip().replace(" ", "_"))[:64]


class WebBoardClient:
    def __init__(self, base_url: str = DEFAULT_URL, password: str = "", timeout: float = 20.0):
        self.base = (base_url or DEFAULT_URL).rstrip("/")
        self.password = password or ""
        self.timeout = timeout
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self._logged = False

    def board_url(self, name: str) -> str:
        """브라우저로 그 칠판을 여는 주소."""
        return f"{self.base}/?board={urllib.parse.quote(name)}"

    def _req(self, method: str, path: str, body=None, raw: bool = False):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        r = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(r, timeout=self.timeout) as resp:
                b = resp.read()
                return resp.status, (b if raw else (json.loads(b) if b else None))
        except urllib.error.HTTPError as e:
            return e.code, None
        except (urllib.error.URLError, OSError) as e:
            raise WebBoardError(f"웹 칠판 서버({self.base})에 연결하지 못했어요 — 서버가 켜져 있는지, 주소가 맞는지 확인해 주세요.\n({e})") from e

    def _ensure_login(self):
        if self._logged:
            return
        st, ss = self._req("GET", "/api/session")
        if st != 200:
            raise WebBoardError(f"웹 칠판 서버가 아닌 것 같아요(응답 {st}) — 주소를 확인해 주세요.")
        if ss.get("auth") and not ss.get("ok"):
            if not self.password:
                raise WebBoardError("이 서버는 팀 비밀번호가 필요해요 — 「웹 칠판 설정」에서 적어 주세요.")
            st, _ = self._req("POST", "/api/login", {"password": self.password})
            if st != 200:
                raise WebBoardError("팀 비밀번호가 맞지 않아요 — 「웹 칠판 설정」에서 확인해 주세요.")
        self._logged = True

    def list_boards(self) -> list:
        """[{"name", "mtime"(초), "items"}] — 최근에 고친 것부터."""
        self._ensure_login()
        st, d = self._req("GET", "/api/boards")
        if st != 200:
            raise WebBoardError(f"칠판 목록을 받지 못했어요(응답 {st}).")
        self.hidden = bool(d.get("hidden"))   # 비밀번호 없는 서버 = 칠판 주소가 곧 열쇠라 전체 목록을 숨김(2026-10-27) — 화면은 이름·주소를 물음
        return d.get("boards") or []

    def board_exists(self, name: str) -> bool:
        """서버에 그 이름의 칠판이 있나 — 목록을 숨기는 서버에서도 아는 이름은 물어볼 수 있음(`?names=`)."""
        self._ensure_login()
        st, d = self._req("GET", "/api/boards?names=" + urllib.parse.quote(name))
        return st == 200 and any(b.get("name") == name for b in (d or {}).get("boards") or [])

    def get_doc(self, name: str) -> dict:
        self._ensure_login()
        st, d = self._req("GET", "/api/doc/" + urllib.parse.quote(name))
        if st == 404:
            raise WebBoardError(f"「{name}」 칠판이 서버에 없어요.")
        if st == 400 and NAME_RE.match(name or ""):   # 이름은 맞는데 거절 = 다른 팀 칠판(§8 항목67 팀별 칠판)
            raise WebBoardError(f"「{name}」은 다른 팀 칠판이라 이 비밀번호로는 열 수 없어요.")
        if st != 200 or not isinstance(d, dict):
            raise WebBoardError(f"「{name}」 칠판을 받지 못했어요(응답 {st}).")
        return d

    def put_doc(self, name: str, doc: dict) -> int:
        """칠판을 통째로 올림 → 새 판 번호. 같은 이름이 있으면 덮어씀(묻는 건 화면 쪽)."""
        if not NAME_RE.match(name or ""):
            raise WebBoardError("칠판 이름은 한글·영문·숫자·_·-로 64자까지예요.")
        self._ensure_login()
        st, d = self._req("PUT", "/api/doc/" + urllib.parse.quote(name), doc)
        if st == 401:
            raise WebBoardError("편집 권한이 없어요 — 팀 비밀번호를 확인해 주세요.")
        if st == 400:   # 이름은 위에서 확인 — 다른 팀이 쓰는 이름(§8 항목67)
            raise WebBoardError(f"「{name}」은 다른 팀이 쓰는 이름이에요 — 다른 이름으로 올려 주세요.")
        if st != 200:
            raise WebBoardError(f"올리지 못했어요(응답 {st}).")
        return int((d or {}).get("rev") or 0)
