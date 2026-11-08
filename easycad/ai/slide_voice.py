"""웹 칠판 발표 「읽어 주기」(계획 ⑥, 2026-11-08, Qt 비의존) — 장의 발표자 메모 → KAIROS 음성(gemini-3.8-flash-tts) → WAV.

KAIROS `/audio/speech/`(docs/reference/kairos/reference_audio-tts.md): 답 = 원시 PCM(24kHz 모노 16비트 LE) — 브라우저가 틀 수 있게 WAV 머리를 붙임.
`input`은 적힌 그대로 읽어서 말투는 `instructions`에(한국어 가능), 한 번에 4,000자까지 — 넘으면 문장 끝에서 나눠 이어 붙임.
서버는 같은 글·목소리·말투면 만든 파일을 다시 씀(`cache_name`) — 같은 발표를 다시 해도 크레딧이 안 듦.
"""
from __future__ import annotations

import hashlib
import re
import struct
import time

from easycad.ai import gateway as gw

TTS_MODEL = "gemini-3.8-flash-tts"
VOICE = "Kore"   # 목소리 하나로 시작(인계 ⑥) — 바꾸면 만든 파일 이름도 바뀜
STYLE = "발표자가 청중에게 설명하듯 차분하고 또렷하게, 자연스러운 한국어 말투로. 너무 빠르지 않게."
RATE = 24000
MAX_INPUT = 3800   # KAIROS 상한 4,000자 — 조금 남김
MAX_TEXT = 12000   # 장 하나 메모 상한(그 이상은 자름 — 발표자 메모가 이렇게 길 일은 없음)


def wav(pcm: bytes, rate: int = RATE) -> bytes:
    """16비트 모노 PCM → WAV 파일 바이트."""
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def clean(text: str) -> str:
    """읽을 글 — 마크다운 꾸밈·출처 번호·「발표자 메모」 머리는 소리 내어 읽지 않게 뺌."""
    t = re.sub(r"^\s*발표자\s*메모\s*[:：]?\s*", "", str(text or ""))
    t = re.sub(r"\s*\[\d+\]|[*_#`>]+", "", t)
    return re.sub(r"[ \t]+", " ", t).strip()[:MAX_TEXT]


def chunks(text: str, size: int = MAX_INPUT) -> list:
    """긴 글 → 문장 끝에서 나눈 조각들(각 `size`자 이하)."""
    out, cur = [], ""
    for s in re.split(r"(?<=[.!?。…다요])\s+", text):
        while len(s) > size:   # 마침표 없는 아주 긴 문장
            out.append(s[:size]); s = s[size:]
        if len(cur) + len(s) + 1 > size and cur:
            out.append(cur); cur = ""
        cur = (cur + " " + s).strip()
    return out + ([cur] if cur else [])


def cache_name(text: str, voice: str = VOICE, style: str = STYLE, model: str = TTS_MODEL) -> str:
    return hashlib.sha1("\n".join((model, voice, style, clean(text))).encode("utf-8")).hexdigest()[:16]


def speak(key: str, text: str, *, base_url: str = gw.BASE_URL, voice: str = VOICE, style: str = STYLE, model: str = TTS_MODEL, http=None) -> dict:
    """메모 → {"wav": WAV 바이트, "seconds": 길이, "tokens": [입력, 출력], "model", "elapsed"}. 읽을 글이 없으면 ValueError."""
    import httpx
    http = http or httpx
    t = clean(text)
    if not t:
        raise ValueError("읽을 발표자 메모가 없어요")
    t0, pcm, tok = time.time(), b"", [0, 0]
    for part in chunks(t):
        r = http.post(base_url + "/audio/speech/", headers={"Authorization": f"Bearer {key}"}, timeout=180,
                      json={"model": model, "input": part, "voice": voice, "instructions": style})
        if r.status_code >= 400:
            raise RuntimeError(f"읽어 주기 실패 HTTP {r.status_code}: {str(getattr(r, 'text', ''))[:200]}")
        pcm += r.content
        tok = [tok[0] + int(r.headers.get("X-Input-Tokens") or 0), tok[1] + int(r.headers.get("X-Output-Tokens") or 0)]
    return {"wav": wav(pcm), "seconds": round(len(pcm) / (RATE * 2), 1), "tokens": tok, "model": model, "elapsed": round(time.time() - t0, 1)}
