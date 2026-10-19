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
