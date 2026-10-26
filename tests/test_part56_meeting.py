"""§8 항목61 ③-3(2026-10-19) — 웹 칠판 회의록: 받아쓰기 올리기·기다리기(`easycad/ai/meeting.py`)·같은 사람 구간 합치기·요약 JSON,
서버 뒤 일감(`/api/meeting/<이름>` POST → GET 확인).

KAIROS는 부르지 않는다 — 가짜 http·가짜 클라이언트. 실제 호출은 따로 확인(24.7초 녹음 = 2.47크레딧).
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

from easycad.ai import meeting  # noqa: E402

SEGS = [{"speaker": "Speaker 1", "text": "회의 시작합니다.", "start_ms": 90, "end_ms": 2000},
        {"speaker": "Speaker 1", "text": "첫 안건은 송신기 교체.", "start_ms": 2100, "end_ms": 5000},
        {"speaker": "Speaker 2", "text": "견적은 금요일까지 받을게요.", "start_ms": 65000, "end_ms": 68000},
        {"speaker": "Speaker 1", "text": "  ", "start_ms": 69000, "end_ms": 69500}]


class FakeHttp:
    def __init__(self, polls=2):
        self.calls, self.polls = [], polls

    def post(self, url, headers, files, data, timeout):
        self.calls.append(("post", url, data["model"], files["file"][0]))
        return SimpleNamespace(status_code=200, text="", json=lambda: {"operation_id": "op1", "status": "processing", "duration_seconds": 68.4, "credits_charged": 6.84})

    def get(self, url, headers, timeout):
        self.calls.append(("get", url))
        self.polls -= 1
        body = {"status": "processing"} if self.polls > 0 else {"status": "completed", "segments": SEGS, "text": "…"}
        return SimpleNamespace(status_code=200, text="", json=lambda: body)


def test_transcribe_uploads_then_polls_until_completed():
    http, said = FakeHttp(polls=3), []
    out = meeting.transcribe("k", b"RIFF", "회의.wav", base_url="https://g", http=http, sleep=lambda s: None, on_status=said.append)
    assert http.calls[0] == ("post", "https://g/audio/transcriptions", meeting.STT_MODEL, "회의.wav")
    assert [c[1] for c in http.calls[1:]] == ["https://g/audio/transcriptions/op1"] * 3
    assert out["segments"] == SEGS and out["duration"] == 68.4 and out["credits"] == 6.84 and said


def test_turns_merge_same_speaker_and_clock():
    tns = meeting.turns(SEGS)
    assert tns == [{"speaker": "화자 1", "start_ms": 90, "text": "회의 시작합니다. 첫 안건은 송신기 교체."},
                   {"speaker": "화자 2", "start_ms": 65000, "text": "견적은 금요일까지 받을게요."}]
    assert meeting.clock(65000) == "01:05" and meeting.clock(3_725_000) == "1:02:05"
    assert meeting.transcript_text(tns).splitlines()[1] == "[01:05] 화자 2: 견적은 금요일까지 받을게요."


def _fake_client(content):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), seen


def test_summarize_reads_json_even_in_code_fence_and_fills_gaps():
    client, seen = _fake_client('```json\n{"title": "송신기 교체", "summary": "교체 논의", "decisions": ["교체한다", ""], "todos": [{"who": "화자 2", "what": "견적", "due": "금요일"}, "보고서"]}\n```')
    out = meeting.summarize(client, meeting.turns(SEGS), model="m-1")
    assert seen["model"] == "m-1" and "[01:05] 화자 2" in seen["messages"][1]["content"]
    assert out == {"title": "송신기 교체", "summary": "교체 논의", "decisions": ["교체한다"],
                   "todos": [{"who": "화자 2", "what": "견적", "due": "금요일"}, {"who": "", "what": "보고서", "due": ""}], "next": ""}
    client, _ = _fake_client("JSON이 아닌 답")
    assert meeting.summarize(client, meeting.turns(SEGS), model="m")["summary"] == "JSON이 아닌 답"   # 깨져도 요약 글로는 남김


@pytest.fixture
def server(tmp_path, monkeypatch):
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    got = {}

    def fake_minutes(key, data, fname, *, model, base_url="", on_status=None, **kw):
        got.update(key=key, data=data, fname=fname, model=model)
        on_status("요약하는 중…")
        time.sleep(0.2)
        return {"title": "회의", "summary": "", "decisions": [], "todos": [], "next": "", "turns": [], "duration": 3.0, "credits": 0.3, "model": model}
    monkeypatch.setattr(srv.meeting, "make_minutes", fake_minutes)
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", got
    httpd.shutdown()


def test_server_meeting_job_start_poll_done(server):
    base, got = server
    req = urllib.request.Request(base + "/api/meeting/" + urllib.parse.quote("공부") + "?model=m-9", data=b"RIFFxx", method="POST",
                                 headers={"Content-Type": "audio/wav", "X-File-Name": urllib.parse.quote("회의 녹음.wav")})
    with urllib.request.urlopen(req) as r:
        job = json.loads(r.read())["job"]
    url = base + "/api/meeting/" + urllib.parse.quote("공부") + "/" + job
    for _ in range(50):
        with urllib.request.urlopen(url) as r:
            st = json.loads(r.read())
        if st["status"] != "run":
            break
        time.sleep(0.05)
    assert st["status"] == "done" and st["result"]["model"] == "m-9"
    assert got == {"key": "test-key", "data": b"RIFFxx", "fname": "회의 녹음.wav", "model": "m-9"}
    with pytest.raises(urllib.error.HTTPError):   # 한 번 돌려주면 끝
        urllib.request.urlopen(url)
    bad = urllib.request.Request(base + "/api/meeting/x", data=b"abc", method="POST", headers={"X-File-Name": "a.txt"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(bad)
    assert e.value.code == 400


# ── [2026-10-20 KAIROS 문서] 받아쓰기는 25MB·120분까지, webm 거절 → 올리기 전에 바꾸거나 쉬운 말로 알림 ──

def test_transcribe_sends_korean_hint():
    seen = {}

    class H(FakeHttp):
        def post(self, url, headers, files, data, timeout):
            seen.update(data)
            return super().post(url, headers, files, data, timeout)
    meeting.transcribe("k", b"RIFF", "a.wav", base_url="https://g", http=H(polls=1), sleep=lambda s: None)
    assert seen["language_hints"] == "ko"


def test_prepare_without_ffmpeg_passes_ok_and_explains_bad():
    assert meeting.prepare(b"x" * 10, "a.m4a", ffmpeg="", ffprobe="") == [(b"x" * 10, "a.m4a", 0)]
    with pytest.raises(RuntimeError, match="webm"):
        meeting.prepare(b"x", "녹음.webm", ffmpeg="", ffprobe="")
    with pytest.raises(RuntimeError, match="25MB"):
        meeting.prepare(b"x" * (meeting.MAX_UPLOAD + 1), "a.mp3", ffmpeg="", ffprobe="")


FFMPEG = __import__("shutil").which("ffmpeg")


def _tone(seconds: int, ext: str) -> bytes:
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t" + ext)
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", p], check=True)
        return open(p, "rb").read()


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg 없음")
def test_prepare_converts_webm_and_splits_long(monkeypatch):
    parts = meeting.prepare(_tone(2, ".webm"), "회의.webm")
    assert len(parts) == 1 and parts[0][1] == "회의.mp3" and parts[0][0][:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    ok = _tone(1, ".wav")
    assert meeting.prepare(ok, "a.wav") == [(ok, "a.wav", 0)]                      # 되는 것은 그대로
    monkeypatch.setattr(meeting, "MAX_SECONDS", 2)
    monkeypatch.setattr(meeting, "CHUNK_SECONDS", 2)
    parts = meeting.prepare(_tone(5, ".wav"), "긴.wav")
    assert [p[2] for p in parts] == [0, 2000, 4000] and [p[1] for p in parts] == ["긴_1.mp3", "긴_2.mp3", "긴_3.mp3"]


def test_make_minutes_joins_parts_with_offsets(monkeypatch):
    monkeypatch.setattr(meeting, "prepare", lambda data, name: [(b"a", "a_1.mp3", 0), (b"b", "a_2.mp3", 6_600_000)])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"title": "t"}'))]))))
    out = meeting.make_minutes("k", b"x", "a.mp3", model="m", base_url="https://g", http=FakeHttp(polls=1), client=client, sleep=lambda s: None)
    assert [t["start_ms"] for t in out["turns"]] == [90, 65000, 6_600_090, 6_665_000]
    assert out["duration"] == 136.8 and out["credits"] == 13.68


def test_live_token_builds_wss_url_with_token():
    seen = {}

    class H:
        def post(self, url, headers, json, timeout):
            seen.update(url=url, json=json)
            return SimpleNamespace(status_code=200, text="", json=lambda: {"token": "T0k", "expires_at": "x", "url": "/v1/gateway/soniox/transcribe-websocket"})
    out = meeting.live_token("k", base_url="https://api.baze.co/v1/gateway", http=H())
    assert seen == {"url": "https://api.baze.co/v1/gateway/realtime/sessions/", "json": {"model": "stt-rt-v5"}}
    assert out["url"] == "wss://api.baze.co/v1/gateway/soniox/transcribe-websocket?token=T0k"


# ── 「🎙 회의」 실시간 받아쓰기(2026-10-23) — 브라우저가 모은 구간 → 요약만, 파일 회의록과 같은 모양 ──
def test_minutes_from_live_merges_and_summarizes_without_stt():
    client, seen = _fake_client('{"title": "점검 일정", "decisions": ["수요일 10시"]}')
    out = meeting.minutes_from_live("k", SEGS, model="m-2", duration=68.4, client=client)
    assert [t["speaker"] for t in out["turns"]] == ["화자 1", "화자 2"] and out["turns"][0]["text"] == "회의 시작합니다. 첫 안건은 송신기 교체."
    assert out["title"] == "점검 일정" and out["decisions"] == ["수요일 10시"] and out["duration"] == 68.4 and out["credits"] is None and out["model"] == "m-2"
    assert "[01:05] 화자 2" in seen["messages"][1]["content"]
    with pytest.raises(RuntimeError):
        meeting.minutes_from_live("k", [{"speaker": "Speaker 1", "text": " "}], model="m", client=client)


def test_server_meeting_live_job(server, monkeypatch):
    import server as srv
    base, got = server

    def fake_live(key, segs, *, model, duration=0, base_url="", **kw):
        got.update(key=key, segs=segs, model=model, duration=duration)
        return {"title": "실시간", "summary": "", "decisions": [], "todos": [], "next": "", "turns": meeting.turns(segs), "duration": duration, "credits": None, "model": model}
    monkeypatch.setattr(srv.meeting, "minutes_from_live", fake_live)
    body = json.dumps({"segments": SEGS[:3], "duration": 68.4}).encode()
    req = urllib.request.Request(base + "/api/meeting/" + urllib.parse.quote("공부") + "/live?model=m-7", data=body, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        job = json.loads(r.read())["job"]
    url = base + "/api/meeting/" + urllib.parse.quote("공부") + "/" + job
    for _ in range(50):
        with urllib.request.urlopen(url) as r:
            st = json.loads(r.read())
        if st["status"] != "run":
            break
        time.sleep(0.05)
    assert st["status"] == "done" and st["result"]["title"] == "실시간" and len(st["result"]["turns"]) == 2
    assert got == {"key": "test-key", "segs": SEGS[:3], "model": "m-7", "duration": 68.4}
    empty = urllib.request.Request(base + "/api/meeting/x/live", data=b'{"segments": []}', method="POST", headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(empty)
    assert e.value.code == 400


def test_summary_prompt_fixes_kairos_misheard():
    # 2026-10-26 시연 캡처: 받아쓰기가 「KAIROS」를 「KIYOS」로 — 받아쓰기엔 단어 힌트 칸이 없어 요약 지시문이 바로잡음(진짜 KAIROS로 한 번 확인: 할 일에 KAIROS)
    client, seen = _fake_client('{"title": "t"}')
    meeting.summarize(client, meeting.turns(SEGS), model="m")
    assert "KIYOS" in seen["messages"][0]["content"] and "KAIROS로 바로잡는다" in seen["messages"][0]["content"]
