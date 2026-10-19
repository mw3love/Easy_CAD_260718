"""웹 칠판 회의록(§8 항목61 ③-3, 2026-10-19) — 녹음 파일 → KAIROS 받아쓰기(STT) → 요약 JSON(Qt 비의존, `web/server.py`가 부름).

받아쓰기(2026-10-19 실측): POST `/audio/transcriptions`(multipart `file`, `model=stt-async-v5`) → {"operation_id", "status": "processing",
"duration_seconds", "credits_charged"} → GET `/audio/transcriptions/{operation_id}` → {"status": "completed", "segments": [{"speaker", "text",
"start_ms", "end_ms"}], "text"}. 24.7초 녹음 = 올리기 3.2초 + 끝까지 7.6초, 2.47크레딧(1초 0.1크레딧 — 1시간 ≈ 360크레딧).
요약은 「AI는 내용만」(§8 항목52 원칙) — 제목·요약·결정·할 일·다음 회의를 JSON으로만 받고, 칠판 배치는 브라우저(Editor `insertMeeting`)가 한다.
"""
from __future__ import annotations

import json
import re
import time

from easycad.ai import gateway as gw

STT_MODEL = "stt-async-v5"
POLL_S = 2.0
STT_TIMEOUT_S = 40 * 60        # 긴 회의도(받아쓰기는 녹음 길이보다 훨씬 빠름 — 24초 녹음이 7.6초)
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".webm", ".ogg", ".aac", ".flac", ".mp4")

SUMMARY_SYSTEM = """너는 회의 녹취를 정리하는 도우미다. 한국어로 쓴다. 아래 모양의 JSON 하나만 출력한다(다른 글·코드펜스 없이):
{"title": "회의 제목(짧게)", "summary": "무엇을 논의했는지 2~3문장", "decisions": ["정한 것", ...],
 "todos": [{"who": "맡은 사람(모르면 빈 글)", "what": "할 일", "due": "기한(모르면 빈 글)"}], "next": "다음 회의 일정(없으면 빈 글)"}
- 녹취에 없는 내용은 지어내지 않는다. 결정·할 일이 없으면 빈 목록."""


def transcribe(api_key: str, data: bytes, filename: str, *, base_url: str = gw.BASE_URL, http=None, sleep=time.sleep,
               on_status=None) -> dict:
    """녹음 → {"segments", "text", "duration", "credits"}. `http`는 시험용(httpx 흉내), `on_status(글)`은 진행 알림."""
    import httpx
    http = http or httpx
    h = {"Authorization": f"Bearer {api_key}"}
    r = http.post(base_url + "/audio/transcriptions", headers=h, files={"file": (filename, data)}, data={"model": STT_MODEL}, timeout=300)
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
        on_status("받아쓰기 올리는 중…")
    stt = transcribe(api_key, data, filename, base_url=base_url, http=http, sleep=sleep, on_status=on_status)
    tns = turns(stt["segments"])
    if not tns:
        raise RuntimeError("녹음에서 말소리를 못 찾았어요")
    if on_status:
        on_status("요약하는 중…")
    client = client or gw._client(api_key, base_url, timeout=300)
    out = summarize(client, tns, model=model)
    return {**out, "turns": tns, "duration": round(float(stt["duration"] or 0), 1), "credits": round(float(stt["credits"] or 0), 2), "model": model}
