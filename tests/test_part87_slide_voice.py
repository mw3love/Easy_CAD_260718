"""발표 「읽어 주기」(계획 ⑥, 2026-11-08) — 발표자 메모 → KAIROS 음성(가짜) → WAV, 같은 글이면 서버가 만든 파일을 다시 씀."""
import json
import os
import struct
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web"))   # server.py

from easycad.ai import slide_voice  # noqa: E402


class _Resp:
    def __init__(self, content, status=200):
        self.content, self.status_code, self.text = content, status, ""
        self.headers = {"X-Input-Tokens": "10", "X-Output-Tokens": "100"}


class _Http:
    def __init__(self):
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, json))
        return _Resp(b"\x01\x00" * 24000)   # 1초


def test_wav_header_and_speak():
    h = _Http()
    out = slide_voice.speak("k", "발표자 메모: 송신소는 **마지막 관문**입니다 [1].", base_url="https://g", http=h)
    w = out["wav"]
    assert w[:4] == b"RIFF" and w[8:16] == b"WAVEfmt " and struct.unpack("<I", w[24:28])[0] == 24000 and len(w) == 44 + 48000
    assert out["seconds"] == 1.0 and out["tokens"] == [10, 100]
    url, body = h.calls[0]
    assert url == "https://g/audio/speech/" and body["model"] == "gemini-3.8-flash-tts" and body["voice"] == "Kore"
    assert body["input"] == "송신소는 마지막 관문입니다." and "차분" in body["instructions"]   # 머리·꾸밈·출처 번호는 안 읽음, 말투는 instructions에(input은 그대로 읽힘)


def test_long_notes_split_at_sentences_and_empty_is_error():
    text = "가나다라마바사입니다. " * 600   # 약 6,600자 — 두 조각
    parts = slide_voice.chunks(slide_voice.clean(text))
    assert len(parts) == 2 and all(len(p) <= slide_voice.MAX_INPUT for p in parts) and all(p.endswith("다.") for p in parts)
    h = _Http()
    assert slide_voice.speak("k", text, http=h)["seconds"] == float(len(parts)) and len(h.calls) == len(parts)
    with pytest.raises(ValueError):
        slide_voice.speak("k", "발표자 메모: ", http=h)
    assert slide_voice.cache_name("가") == slide_voice.cache_name("**가**") != slide_voice.cache_name("나")


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    calls = []
    monkeypatch.setattr(srv.slide_voice, "speak", lambda key, text, **kw: calls.append(text) or {"wav": slide_voice.wav(b"\x00\x00" * 2400), "seconds": 0.1, "tokens": [1, 2], "model": "tts", "elapsed": 0.5})
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", calls
    httpd.shutdown()


def _post(base, body):
    req = urllib.request.Request(base + "/api/tts", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_server_tts_makes_once_then_reuses(server):
    base, calls = server
    a = _post(base, {"board": "발표", "text": "송신소는 마지막 관문입니다."})
    b = _post(base, {"board": "발표", "text": "송신소는 마지막 관문입니다."})
    assert a["cached"] is False and b["cached"] is True and a["url"] == b["url"] and calls == ["송신소는 마지막 관문입니다."]   # 두 번째는 크레딧 0
    with urllib.request.urlopen(base + a["url"]) as r:
        assert r.headers["Content-Type"] == "audio/wav" and r.read()[:4] == b"RIFF"
    with pytest.raises(urllib.error.HTTPError):
        _post(base, {"board": "발표", "text": "  "})
