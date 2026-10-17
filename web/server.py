"""Magic Board 웹 칠판 서버(§8 항목61 ⓑ, 2026-10-17) — 감시 PC에서 켜 두고 회사 안 다른 PC 크롬으로 접속한다.

하는 일 두 가지(파이썬 기본 라이브러리만 — 새 설치 없음):
- 칠판 화면: `web/dist/`(먼저 `cd web && npm run build`)를 그대로 내준다.
- 칠판 저장: GET/PUT `/api/board/<이름>` — tldraw 문서(JSON)를 데이터 폴더의 `<이름>.json`에.
  쓰기는 안전 저장(임시 파일 → 바꿔치기, `easycad/fileio/safe_write.py`)이라 도중에 꺼져도 직전 완성본이 남는다.
  바로 앞 저장본은 `<이름>.prev.json`으로 하나 남긴다(실수로 지웠을 때 손으로 되살리기용).

지금은 "마지막에 저장한 쪽이 이김" — 두 PC에서 동시에 고치면 나중 저장이 앞 저장을 덮는다(실시간 공동작업은 §8 항목61 ⓕ).
접근 제한 없음: 같은 네트워크의 누구나 열 수 있다 — 회사 보안 정책 확인 전엔 내 PC에서만(`--host 127.0.0.1`).

실행: python web/server.py [--host 0.0.0.0] [--port 5191] [--data 폴더]
데이터 폴더 기본값: %APPDATA%/EasyCAD/web_boards (데스크톱 앱 설정·자동 저장과 같은 곳 — git에 안 들어감)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from easycad.fileio.safe_write import write_via_temp  # noqa: E402  (Qt 안 씀)

NAME_RE = re.compile(r"^[\w\-가-힣]{1,64}$")
MAX_BYTES = 200 * 1024 * 1024   # 그림이 든 칠판도 넉넉히, 하지만 끝없이는 아니게


def default_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "EasyCAD", "web_boards")


class Handler(SimpleHTTPRequestHandler):
    data_dir = default_data_dir()

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=os.path.join(HERE, "dist"), **kw)

    # ── API ──
    def _board_path(self):
        m = re.match(r"^/api/board/([^/?#]+)$", self.path)
        if not m:
            return None
        from urllib.parse import unquote
        name = unquote(m.group(1))
        return os.path.join(self.data_dir, name + ".json") if NAME_RE.match(name) else ""

    def _send(self, code: int, body: bytes = b"", ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
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

    def do_PUT(self):
        p = self._board_path()
        if not p:
            return self._send(400, b'{"error":"bad name"}')
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._send(413, b'{"error":"size"}')
        raw = self.rfile.read(n)
        try:
            json.loads(raw)   # 깨진 내용으로 좋은 저장본을 덮지 않게
        except ValueError:
            return self._send(400, b'{"error":"json"}')
        os.makedirs(self.data_dir, exist_ok=True)
        if os.path.exists(p):
            prev = p[:-5] + ".prev.json"
            write_via_temp(prev, lambda tmp: _copy(p, tmp))
        write_via_temp(p, lambda tmp: _write(tmp, raw))
        self._send(200, b'{"ok":true}')

    def log_message(self, fmt, *args):   # 저장 요청만 짧게
        if self.command == "PUT":
            sys.stderr.write("[저장] %s %s\n" % (self.path, args[1] if len(args) > 1 else ""))


def _write(path: str, raw: bytes):
    with open(path, "wb") as f:
        f.write(raw)


def _copy(src: str, dst: str):
    with open(src, "rb") as a, open(dst, "wb") as b:
        b.write(a.read())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Magic Board 웹 칠판 서버")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5191)
    ap.add_argument("--data", default=default_data_dir())
    a = ap.parse_args(argv)
    Handler.data_dir = a.data
    if not os.path.isdir(os.path.join(HERE, "dist")):
        print("web/dist가 없습니다 — 먼저 `cd web && npm run build` (API만 씁니다)")
    print(f"Magic Board 칠판: http://{'localhost' if a.host in ('0.0.0.0', '127.0.0.1') else a.host}:{a.port}  · 저장 폴더: {a.data}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
