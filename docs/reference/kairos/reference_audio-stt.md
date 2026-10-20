# Audio — 음성 텍스트 변환

> 비동기 음성 텍스트 변환(STT) 엔드포인트

녹음 파일을 텍스트로 옮기는 STT(Speech-to-Text) 엔드포인트입니다.

화자 분리와 구간별 타임스탬프를 함께 돌려주므로 회의·인터뷰·상담 녹음처럼 여러 사람이 말하는 오디오도 그대로 넘기면 됩니다. 변환은 작업 시작 → 상태 폴링 두 단계로 진행됩니다.

---

### 참고

  변환은 오디오 길이에 비례해 시간이 걸립니다. 폴링 간격은 10초를 권장합니다.

- 인증은 다른 게이트웨이 엔드포인트와 동일합니다 — `Authorization: Bearer <API_KEY>`. 조직(테넌트)은 키로 식별하므로 별도 파라미터가 없습니다.
- 요청은 JSON이 아니라 `multipart/form-data`입니다.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/v1/gateway/audio/transcriptions/` | 변환 작업 시작 |
| GET | `/v1/gateway/audio/transcriptions/{operation_id}/` | 작업 상태 폴링 |

---

### 1. 변환 시작

POST

오디오 파일을 올려 비동기 변환 작업을 시작합니다. 본문은 `multipart/form-data`입니다.

#### 파라미터

file
변환할 오디오 파일. `mp3`, `m4a`/`mp4`, `wav`, `flac`, `ogg`/`opus`, `aiff`를 지원합니다. 파일에서 길이를 읽어 과금하므로, 길이 정보가 없는 컨테이너(`webm`, `amr`)는 `400`으로 거절합니다.

model
STT 모델 이름. 현재 `stt-async-v5` 하나입니다. TTS·음악 모델을 넘기면 `400`이며, 응답이 올바른 엔드포인트를 안내합니다.

language_hints
언어 힌트 (기본값: `["en", "ko"]`, 최대 5개). 필드를 여러 번 반복해 전달합니다 (`-F "language_hints=ko" -F "language_hints=en"`). 폼 인코더에 따라 `-F "language_hints=ko,en"` 형태도 받습니다. 오디오의 언어가 정해져 있다면 하나만 넘기는 편이 정확합니다.

enable_speaker_diarization
화자 분리 사용 여부 (기본값: `true`). 끄면 화자별로 나뉘지 않아 `segments`가 하나로 합쳐지고, `speaker`에는 `Speaker Unknown`이 들어갑니다.

#### 응답

```json
{
  "operation_id": "soniox:9e2b5fe1-f54c-43e6-aa9a-61ba765292d7:555f54095a15874b",
  "status": "processing",
  "model": "stt-async-v5",
  "duration_seconds": 1832.4,
  "credits_charged": 183.24
}
```

| 필드 | 설명 |
| --- | --- |
| `operation_id` | 폴링에 그대로 넘길 불투명한 문자열. 형식을 파싱하지 마세요 |
| `duration_seconds` | 업로드 파일에서 측정한 오디오 길이 — **과금 기준** |
| `credits_charged` | 이 요청으로 차감된 크레딧. 응답 헤더 `X-Credits-Charged`에도 같은 값이 실립니다 |

크레딧은 이 시점에 한 번 차감됩니다 — 아래 [과금](#과금)을 참고하세요.

---

### 2. 상태 폴링

GET

`status`가 종료 상태(`completed` 또는 `failed`)가 될 때까지 폴링합니다. 완료되면 같은 응답에 전문(`text`)과 구간(`segments`)이 함께 들어옵니다.

```json
{
  "operation_id": "soniox:9e2b5fe1-f54c-43e6-aa9a-61ba765292d7:555f54095a15874b",
  "status": "completed",
  "duration_seconds": 1832.4,
  "text": "안녕하세요, 오늘 회의 시작하겠습니다. ...",
  "segments": [
    {
      "speaker": "Speaker 1",
      "text": "안녕하세요, 오늘 회의 시작하겠습니다.",
      "start_ms": 0,
      "end_ms": 4120
    }
  ]
}
```

| Status | 의미 |
| --- | --- |
| `processing` | 변환 진행 중 |
| `completed` | 변환 완료 — `text`·`segments` 사용 가능 |
| `failed` | 변환 실패 — `text`·`segments` 대신 `error` 메시지가 들어옵니다. 시작 시 차감한 크레딧은 그대로 유지됩니다 |

```json
{
  "operation_id": "soniox:9e2b5fe1-f54c-43e6-aa9a-61ba765292d7:555f54095a15874b",
  "status": "failed",
  "error": "Audio file could not be decoded"
}
```

| 필드 | 설명 |
| --- | --- |
| `text` | 전체 전사 텍스트 |
| `segments[].speaker` | 화자 라벨 (`Speaker 1`, `Speaker 2` …. 화자 분리를 껐다면 `Speaker Unknown`) |
| `segments[].text` | 해당 구간의 텍스트 |
| `segments[].start_ms` / `end_ms` | 오디오 시작점 기준 밀리초 |
| `duration_seconds` | 변환 엔진이 측정한 오디오 길이. 과금 기준은 시작 응답의 `duration_seconds`이며, 소수점 아래에서 다를 수 있습니다 |

---

### 예제

#### curl — 1. 변환 시작

```bash
curl -X POST https://api.baze.co/v1/gateway/audio/transcriptions/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@meeting.mp3" \
  -F "model=stt-async-v5" \
  -F "language_hints=ko" \
  -F "language_hints=en" \
  -F "enable_speaker_diarization=true"
```

#### curl — 2. 상태 폴링

```bash
curl https://api.baze.co/v1/gateway/audio/transcriptions/OPERATION_ID/ \
  -H "Authorization: Bearer YOUR_API_KEY"
```

#### 전체 흐름 (Python)

```python
import time
import httpx

API_KEY = "YOUR_API_KEY"
BASE = "https://api.baze.co/v1/gateway"
client = httpx.Client(headers={"Authorization": f"Bearer {API_KEY}"}, timeout=120.0)

# 1. 시작
with open("meeting.mp3", "rb") as f:
    resp = client.post(
        f"{BASE}/audio/transcriptions/",
        files={"file": ("meeting.mp3", f, "audio/mpeg")},
        data={
            "model": "stt-async-v5",
            # 반복 폼 필드 — httpx가 리스트 항목마다 파트를 하나씩 만든다
            "language_hints": ["ko", "en"],
            "enable_speaker_diarization": "true",
        },
    )
operation_id = resp.json()["operation_id"]

# 2. 폴링
while True:
    result = client.get(f"{BASE}/audio/transcriptions/{operation_id}/").json()
    if result["status"] == "completed":
        break
    if result["status"] == "failed":
        raise RuntimeError(f"전사에 실패했습니다: {result}")
    time.sleep(10)

print(result["text"])
for seg in result["segments"]:
    print(f"[{seg['start_ms']}ms] {seg['speaker']}: {seg['text']}")
```

---

### 제한

| 제한 | 값 |
| --- | --- |
| 오디오 길이 | 요청당 최대 120분 |
| 요청 본문 크기 | 25MB |
| 요청 속도 | 사용자당 분당 120회 (게이트웨이 공통) |

120분을 넘는 오디오는 잘라서 변환하지 않고 `400`으로 거절합니다. 긴 녹음은 미리 120분 이하로 나눠 여러 번 호출하세요. 25MB를 넘는 본문은 `413`입니다 — 저비트레이트 mp3라면 25MB로도 2시간이 넘을 수 있으므로 두 제한은 별개입니다.

---

### 과금

오디오 **1분당 6 크레딧**입니다.

- 파일에서 측정한 실제 길이를 기준으로 **작업 시작 시 한 번만** 차감합니다.
- 폴링은 무료이며, 몇 번을 하든 추가 과금이 없습니다.
- 작업이 `failed`로 끝나도 **시작 시 차감한 크레딧은 환불되지 않습니다** (추가 차감도 없습니다). 변환 엔진 장애로 실패한 경우에는 문의해 주세요.
- 시작 요청 자체가 실패하면(`4xx`·`5xx` 응답) 차감이 일어나지 않습니다.
- 오디오 크레딧으로 집계됩니다.

---

### 에러

| 상태 코드 | 원인 | 단계 |
| --- | --- | --- |
| `400` | 빈 파일 · 길이를 읽을 수 없는 오디오(`webm`·`amr` 포함) · 120분 초과 · `language_hints` 형식 오류나 5개 초과 · STT가 아닌 모델 | 시작 |
| `401` | API 키 누락 또는 유효하지 않음 | 둘 다 |
| `402` | 크레딧 잔액 부족 | 시작 |
| `403` | 조직의 Gateway API 비활성화, 또는 해당 모델이 조직에 활성화되지 않음 | 시작 |
| `404` | 존재하지 않는 모델 이름 | 시작 |
| `404` | `operation_id`가 이 조직의 것이 아니거나 위조·존재하지 않음 | 폴링 |
| `413` | 요청 본문 25MB 초과 | 시작 |
| `429` | 사용자당 분당 120회 초과. 채팅·미디어·오디오가 함께 쓰는 크레딧 예약 한도(분당 300회)에 걸려도 같은 코드입니다 | 둘 다 |
| `500` | 모델 단가 설정 누락 (문의해 주세요) | 시작 |
| `502` | 변환 엔진 오류 — 이 경우 크레딧은 차감되지 않습니다 | 둘 다 |
| `503` | 조직이 점검(서비스 중지) 상태 | 시작 |

게이트웨이 공통 에러 형식과 대처는 [에러 가이드](/docs/api-gateway/reference/errors)를 참고하세요.

---

### 요약까지 필요하다면

이 엔드포인트는 전사까지만 합니다. 회의록처럼 요약이 필요하다면 받은 `text`를 그대로 [`POST /v1/gateway/chat/completions/`](/docs/api-gateway/reference/chat-completions)에 넣고 원하는 요약 프롬프트를 직접 쓰세요. 요약 형식·항목·언어를 전부 통제할 수 있고, 채팅 호출분만 별도로 과금됩니다.

```python
summary = client.post(f"{BASE}/chat/completions/", json={
    "model": "gpt-5.6-luna",
    "messages": [
        {"role": "system", "content": "다음 회의 전사를 안건·결정·액션아이템으로 정리해줘."},
        {"role": "user", "content": result["text"]},
    ],
}).json()
```

---

### 관련 문서

- [`/audio/speech`](/docs/api-gateway/reference/audio-tts) — 텍스트 음성 변환(TTS)
- [`/chat/completions`](/docs/api-gateway/reference/chat-completions) — 전사 요약용 채팅 호출
- [에러 가이드](/docs/api-gateway/reference/errors) — 게이트웨이 공통 에러
