"""웹 칠판 회의록(§8 항목61 ③-3, 2026-10-19) — 녹음 파일 → KAIROS 받아쓰기(STT) → 요약 JSON(Qt 비의존, `web/server.py`가 부름).

받아쓰기(2026-10-19 실측): POST `/audio/transcriptions`(multipart `file`, `model=stt-async-v5`) → {"operation_id", "status": "processing",
"duration_seconds", "credits_charged"} → GET `/audio/transcriptions/{operation_id}` → {"status": "completed", "segments": [{"speaker", "text",
"start_ms", "end_ms"}], "text"}. 24.7초 녹음 = 올리기 3.2초 + 끝까지 7.6초, 2.47크레딧(1초 0.1크레딧 — 1시간 ≈ 360크레딧).
요약은 「AI는 내용만」(§8 항목52 원칙) — 제목·요약·결정·할 일·다음 회의를 JSON으로만 받고, 칠판 배치는 브라우저(Editor `insertMeeting`)가 한다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from easycad.ai import gateway as gw, model_pick

STT_MODEL = "stt-async-v5"
POLL_S = 2.0
STT_TIMEOUT_S = 40 * 60        # 긴 회의도(받아쓰기는 녹음 길이보다 훨씬 빠름 — 24초 녹음이 7.6초)
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".webm", ".ogg", ".aac", ".flac", ".mp4")   # 칠판이 받는 것 — KAIROS가 안 받는 것은 아래에서 바꿈
# [2026-10-20 KAIROS 문서] 받아쓰기는 본문 25MB·120분까지, 길이를 못 읽는 webm·amr은 거절(aac는 목록에 없음).
# 그래서 넘거나 안 맞으면 ffmpeg로 말소리용 작은 mp3(모노 16kHz 24kbps — 1시간 ≈ 11MB)로 바꾸고, 120분이 넘으면 110분씩 나눠 받아쓴다.
KAIROS_EXT = (".mp3", ".m4a", ".mp4", ".wav", ".flac", ".ogg", ".opus", ".aiff")
MAX_UPLOAD = 24 * 1024 * 1024  # 25MB에서 multipart 머리말 몫을 뺌
MAX_SECONDS = 120 * 60
CHUNK_SECONDS = 110 * 60
LANGUAGE_HINT = "ko"           # 문서: 언어가 정해져 있으면 하나만 넘기는 편이 정확

SUMMARY_SYSTEM = """너는 회의 녹취를 정리하는 도우미다. 한국어로 쓴다. 아래 모양의 JSON 하나만 출력한다(다른 글·코드펜스 없이):
{"title": "회의 제목(짧게)", "summary": "무엇을 논의했는지 2~3문장", "decisions": ["정한 것", ...],
 "todos": [{"who": "맡은 사람(모르면 빈 글)", "what": "할 일", "due": "기한(모르면 빈 글)"}], "next": "다음 회의 일정(없으면 빈 글)"}
- 녹취에 없는 내용은 지어내지 않는다. 결정·할 일이 없으면 빈 목록.
- 녹취는 소리를 글로 옮긴 것이라 이름이 틀릴 수 있다. 사내 AI 「KAIROS」(카이로스)로 들리는 말(예: KIYOS·카이로·카이오스)은 KAIROS로 바로잡는다. 그 밖의 이름은 녹취 그대로."""   # 2026-10-26 시연 캡처: 「KAIROS 활용 사례」 → 「KIYOS」(받아쓰기엔 단어 힌트 칸이 없음 — 문서 reference_audio-stt)


def transcribe(api_key: str, data: bytes, filename: str, *, base_url: str = gw.BASE_URL, http=None, sleep=time.sleep,
               on_status=None) -> dict:
    """녹음 → {"segments", "text", "duration", "credits"}. `http`는 시험용(httpx 흉내), `on_status(글)`은 진행 알림."""
    import httpx
    http = http or httpx
    h = {"Authorization": f"Bearer {api_key}"}
    use = model_pick.pick(STT_MODEL)   # 은퇴·없어진 받아쓰기 모델은 대신할 것으로(2026-10-26)
    r = http.post(base_url + "/audio/transcriptions", headers=h, files={"file": (filename, data)}, data={"model": use, "language_hints": LANGUAGE_HINT}, timeout=300)
    if r.status_code == 404 and "not found" in str(r.text).lower():   # 같은 창구(soniox)의 다른 모델로 한 번 다시
        alt = model_pick.fallback(use, "stt", api_key, base_url, http=http)
        if alt:
            r = http.post(base_url + "/audio/transcriptions", headers=h, files={"file": (filename, data)}, data={"model": alt, "language_hints": LANGUAGE_HINT}, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"받아쓰기 올리기 실패 HTTP {r.status_code}: {r.text[:200]}")
    first = r.json()
    op = first.get("operation_id")
    if not op:
        raise RuntimeError(f"받아쓰기 답에 operation_id가 없음: {str(first)[:200]}")
    t0 = time.time()
    while True:
        g = http.get(f"{base_url}/audio/transcriptions/{op}", headers=h, timeout=60)
        if g.status_code >= 400:
            raise RuntimeError(f"받아쓰기 확인 실패 HTTP {g.status_code}: {g.text[:200]}")
        d = g.json()
        st = d.get("status")
        if st == "completed":
            return {"segments": d.get("segments") or [], "text": d.get("text") or "",
                    "duration": d.get("duration_seconds") or first.get("duration_seconds") or 0, "credits": first.get("credits_charged") or 0}
        if st in ("failed", "error", "cancelled"):
            raise RuntimeError(f"받아쓰기 실패: {str(d)[:200]}")
        if time.time() - t0 > STT_TIMEOUT_S:
            raise RuntimeError("받아쓰기가 너무 오래 걸려요(40분)")
        if on_status:
            on_status(f"받아쓰는 중… {int(time.time() - t0)}초")
        sleep(POLL_S)


def _seconds(path: str, ffprobe: str) -> float:
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def prepare(data: bytes, filename: str, *, ffmpeg: str | None = None, ffprobe: str | None = None) -> list:
    """녹음 → KAIROS에 올릴 조각 [(bytes, 이름, 시작 ms)] — 그대로 되면 한 조각. ffmpeg가 없으면 안 되는 경우를 쉬운 말로 알림."""
    ext = os.path.splitext(filename.lower())[1]
    ok_ext, small = ext in KAIROS_EXT, len(data) <= MAX_UPLOAD
    ffmpeg = ffmpeg if ffmpeg is not None else shutil.which("ffmpeg")
    ffprobe = ffprobe if ffprobe is not None else shutil.which("ffprobe")
    if not ffmpeg:
        if not ok_ext:
            raise RuntimeError(f"이 녹음 형식({ext or '알 수 없음'})은 KAIROS가 받지 않아요 — mp3·m4a·wav로 바꿔서 올려 주세요(서버 PC에 ffmpeg가 있으면 저절로 바꿔요)")
        if not small:
            raise RuntimeError(f"녹음이 너무 커요({len(data) / 1048576:.0f}MB — KAIROS는 25MB까지). 나눠서 올리거나 서버 PC에 ffmpeg를 깔아 주세요")
        return [(data, filename, 0)]
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in" + (ext or ".bin"))
        with open(src, "wb") as f:
            f.write(data)
        secs = _seconds(src, ffprobe) if ffprobe else 0.0
        if ok_ext and small and secs <= MAX_SECONDS:
            return [(data, filename, 0)]
        r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "24k",
                            "-f", "segment", "-segment_time", str(CHUNK_SECONDS), "-reset_timestamps", "1", os.path.join(tmp, "part%03d.mp3")],
                           capture_output=True, text=True, timeout=1800)
        parts = sorted(n for n in os.listdir(tmp) if n.startswith("part") and n.endswith(".mp3"))
        if r.returncode != 0 or not parts:
            raise RuntimeError(f"녹음을 읽지 못했어요: {(r.stderr or '').strip()[:160] or '알 수 없는 형식'}")
        out = []
        for i, n in enumerate(parts):
            with open(os.path.join(tmp, n), "rb") as f:
                b = f.read()
            if len(b) > MAX_UPLOAD:
                raise RuntimeError("녹음을 줄여도 25MB를 넘어요 — 나눠서 올려 주세요")
            out.append((b, os.path.splitext(filename)[0] + (f"_{i + 1}" if len(parts) > 1 else "") + ".mp3", i * CHUNK_SECONDS * 1000))
        return out


def turns(segments: list) -> list:
    """같은 사람이 이어 말한 구간을 합침 → [{"speaker", "start_ms", "text"}]. 말한 사람 이름은 「화자 1」처럼."""
    out = []
    for s in segments:
        sp = re.sub(r"^Speaker\s*", "화자 ", str(s.get("speaker") or "화자")).strip()
        t = str(s.get("text") or "").strip()
        if not t:
            continue
        if out and out[-1]["speaker"] == sp:
            out[-1]["text"] += " " + t
        else:
            out.append({"speaker": sp, "start_ms": int(s.get("start_ms") or 0), "text": t})
    return out


def clock(ms: int) -> str:
    s = max(0, int(ms) // 1000)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def transcript_text(tns: list) -> str:
    return "\n".join(f"[{clock(t['start_ms'])}] {t['speaker']}: {t['text']}" for t in tns)


def _json_block(text: str) -> dict:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    m = re.search(r"\{.*\}", t, re.S)
    return json.loads(m.group(0) if m else t)


def summarize(client, tns: list, *, model: str) -> dict:
    """합친 구간 → {"title", "summary", "decisions", "todos", "next"}(빈 칸은 빈 글·빈 목록으로 채움)."""
    resp = client.chat.completions.create(model=model, max_tokens=gw.DEFAULT_MAX_TOKENS, messages=[
        {"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": "[회의 녹취]\n" + transcript_text(tns)[:120_000]}])
    try:
        d = _json_block(resp.choices[0].message.content or "")
    except ValueError:
        d = {"summary": (resp.choices[0].message.content or "").strip()}
    todos = [t if isinstance(t, dict) else {"what": str(t)} for t in d.get("todos") or []]
    return {"title": str(d.get("title") or "회의"), "summary": str(d.get("summary") or ""),
            "decisions": [str(x) for x in d.get("decisions") or [] if str(x).strip()],
            "todos": [{"who": str(t.get("who") or ""), "what": str(t.get("what") or ""), "due": str(t.get("due") or "")} for t in todos if str(t.get("what") or "").strip()],
            "next": str(d.get("next") or "")}


def make_minutes(api_key: str, data: bytes, filename: str, *, model: str, base_url: str = gw.BASE_URL, on_status=None,
                 http=None, client=None, sleep=time.sleep) -> dict:
    """녹음 → {"title", "summary", "decisions", "todos", "next", "turns", "duration", "credits", "model"} — 서버 뒤 일감이 부른다."""
    if on_status:
        on_status("녹음 살피는 중…")
    parts = prepare(data, filename)
    segs, duration, credits = [], 0.0, 0.0
    for i, (b, name, offset) in enumerate(parts):   # 120분 넘으면 110분씩 — 조각마다 「화자 1」은 따로 매겨져 이어지지 않을 수 있음
        tag = f" ({i + 1}/{len(parts)})" if len(parts) > 1 else ""
        if on_status:
            on_status(f"받아쓰기 올리는 중{tag}…")
        stt = transcribe(api_key, b, name, base_url=base_url, http=http, sleep=sleep, on_status=(lambda m, t=tag: on_status(m + t)) if on_status else None)
        segs += [{**s, "start_ms": int(s.get("start_ms") or 0) + offset, "end_ms": int(s.get("end_ms") or 0) + offset} for s in stt["segments"]]
        duration += float(stt["duration"] or 0)
        credits += float(stt["credits"] or 0)
    stt = {"duration": duration, "credits": credits}
    tns = turns(segs)
    if not tns:
        raise RuntimeError("녹음에서 말소리를 못 찾았어요")
    if on_status:
        on_status("요약하는 중…")
    client = client or gw._client(api_key, base_url, timeout=300)
    out = summarize(client, tns, model=model)
    return {**out, "turns": tns, "duration": round(float(stt["duration"] or 0), 1), "credits": round(float(stt["credits"] or 0), 2), "model": model}


def minutes_from_live(api_key: str, segments: list, *, model: str, duration: float = 0, base_url: str = gw.BASE_URL, client=None) -> dict:
    """「🎙 회의」 실시간 받아쓰기(2026-10-23) — 브라우저가 모은 구간 → 파일 회의록과 같은 모양. 받아쓰기는 이미 끝났으니 요약만.
    화자는 실시간 답의 "1"·"2"를 브라우저가 "Speaker 1"처럼 보냄(파일 받아쓰기와 같은 이름 → `turns`가 「화자 1」로). 크레딧은 받아쓰기 쪽을 모름(None)."""
    tns = turns(segments)
    if not tns:
        raise RuntimeError("받아 적은 말이 없어요")
    client = client or gw._client(api_key, base_url, timeout=300)
    out = summarize(client, tns, model=model)
    return {**out, "turns": tns, "duration": round(float(duration or 0), 1), "credits": None, "model": model}


# ── 실시간 받아쓰기(대화창 🎤, 2026-10-20 KAIROS 문서 검토) — 브라우저가 KAIROS 소켓에 바로 붙되 키는 서버에만 ──
# POST `/realtime/sessions/` {"model": "stt-rt-v5"} → 60초 동안 한 번만 쓰는 표. 브라우저는 `wss://<호스트><url>?token=…`로 붙고(Soniox 실시간 형식 그대로),
# 첫 프레임 JSON 설정 → 0.1초씩 PCM 16비트 → 끝은 빈 글("" — 빈 바이너리면 408). 실측: 말 뒤 0.1~0.3초에 임시 글, 문장 끝에 확정. 과금 = 처리한 오디오 초.
LIVE_MODEL = "stt-rt-v5"


def live_token(api_key: str, *, base_url: str = gw.BASE_URL, http=None) -> dict:
    """→ {"url": 붙을 wss 주소(표 포함), "expires_at"}."""
    import httpx
    http = http or httpx
    r = http.post(base_url + "/realtime/sessions/", headers={"Authorization": f"Bearer {api_key}"}, json={"model": LIVE_MODEL}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"실시간 받아쓰기 표 받기 실패 HTTP {r.status_code}: {r.text[:200]}")
    d = r.json()
    host = re.sub(r"^https://", "wss://", base_url.split("/v1/gateway")[0])
    path = d.get("url") or "/v1/gateway/soniox/transcribe-websocket"
    return {"url": f"{host}{path}{'&' if '?' in path else '?'}token={d['token']}", "expires_at": d.get("expires_at", ""), "model": LIVE_MODEL}
