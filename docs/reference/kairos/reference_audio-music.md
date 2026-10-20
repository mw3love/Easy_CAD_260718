# Audio — 음악·효과음 생성

> Lyria 3와 ElevenLabs를 사용한 음악·효과음 생성 엔드포인트

텍스트 프롬프트로 음악 트랙이나 효과음을 생성합니다.

동기 방식이라 폴링 없이 MP3 바이트가 바로 돌아옵니다. Google Lyria 3와 ElevenLabs Music을 사용하며, 배경음악·징글·게임 및 영상 사운드 디자인에 활용할 수 있습니다.

- 공식 레퍼런스: [Google Lyria](https://ai.google.dev/gemini-api/docs/music-generation) · [ElevenLabs Music](https://elevenlabs.io/docs/api-reference/music)

---

### 음악 생성

POST

프롬프트로 오디오를 생성합니다. 응답은 원시 MP3 바이트입니다.

---

### 파라미터

model
음악 모델 이름(예: `lyria-3-clip-preview`). 아래 모델 표를 참고하세요.

prompt
무엇을 만들지 — 분위기, 장르, 악기, 템포. 최대 4,000자입니다.

lyrics
부를 가사. `lyria-3-pro-preview`와 `elevenlabs-music`에서만 지원합니다. 최대 4,000자입니다.

duration_seconds
출력 길이. **ElevenLabs 모델 전용**입니다 — Lyria는 호출당 정액이며 길이를 엔진이 정합니다.

instrumental
`true`면 보컬 없는 오디오를 생성합니다. **`elevenlabs-music` 전용**이며 `lyrics`와 함께 보낼 수 없습니다.

---

  위 목록에 없는 필드는 `400`으로 거절됩니다. 조용히 무시하지 않습니다 — 지원하지 않는 파라미터는 에러이지, 그 파라미터를 무시한 결과물에 대한 청구서가 아닙니다.

### 모델

| 모델 | 엔진 | 길이 | 가사 | 가격 |
| --- | --- | --- | --- | --- |
| `lyria-3-pro-preview` | Google Lyria 3 Pro | 최대 약 3분, 엔진이 결정 | ✓ 자동 또는 직접 | 호출당 $0.08 |
| `lyria-3-clip-preview` | Google Lyria 3 Clip | 약 30초 고정, 연주곡 | — | 호출당 $0.04 |
| `elevenlabs-music` | ElevenLabs Music | `duration_seconds`, 기본 30초, 최대 180초 | ✓ 자동 또는 직접 | 초당 $0.0025 |
| `elevenlabs-sfx` | ElevenLabs Sound Effects | `duration_seconds` 또는 엔진 결정, 최대 30초 | — | 초당 $0.006 |

조직에 활성화된 모델만 호출할 수 있고, 그렇지 않으면 `403`이 반환됩니다. `GET /v1/gateway/models/?type=audio`로 사용 가능한 모델을 확인할 수 있습니다 — 오디오 항목에는 `audio_client` 필드가 있고, 값이 `google_lyria3` 또는 `elevenlabs`면 음악, 그 외는 TTS입니다.

---

### 길이와 과금

- **Lyria**는 길이를 스스로 정하며 `duration_seconds`를 받지 않습니다(보내면 `400`). 길이는 프롬프트로 유도하세요 — Lyria Pro는 "90초짜리 트랙" 같은 힌트를 약 3분까지 반영합니다.
- **ElevenLabs**는 `duration_seconds`를 반영하며, 음악은 **180초**, 효과음은 **30초**가 상한입니다.
- **`duration_seconds`를 생략했을 때**의 동작은 모델마다 다릅니다.

| 모델 | `duration_seconds` 생략 시 | 청구 |
| --- | --- | --- |
| `elevenlabs-music` | 30초 | 30초 |
| `elevenlabs-sfx` | 엔진이 길이를 결정 | 실제로 돌아온 길이 |

  짧은 효과음은 30초 최대 요금이 아니라 실제 길이만큼만 청구됩니다. 생성 중에는 상한만큼의 크레딧이 예약되고 실제 길이가 확정되면 해제되므로, 짧은 효과음이라도 잔액은 상한을 감당할 수 있어야 합니다. 청구된 길이는 `X-Audio-Duration-Seconds` 헤더로 확인하세요.

---

### 보컬

`lyria-3-pro-preview`와 `elevenlabs-music`은 노래할 수 있습니다. 어느 쪽으로 갈지는 요청이 정합니다.

| 보내는 것 | 받는 것 |
| --- | --- |
| `prompt`만 | 엔진이 가사를 직접 지어 부릅니다 |
| `prompt` + `lyrics` | 보낸 가사를 부릅니다 |
| `prompt` + `instrumental: true` | 보컬 없음(`elevenlabs-music` 전용) |

`instrumental`은 해당 스위치가 없는 Lyria와 효과음 모델에서는 `400`이고, `lyrics`와 동시에 보낼 수 없습니다.

---

### 응답

원시 MP3 오디오 바이트(`audio/mpeg`)입니다.

| 헤더 | 설명 |
| --- | --- |
| `X-Model` | 오디오를 생성한 모델 — 항상 요청한 그 모델입니다 |
| `X-Credits-Charged` | 이번 호출에서 차감된 크레딧 |
| `X-Audio-Duration-Seconds` | ElevenLabs 전용 — 청구된 길이 |
| `X-Music-Structure` | Lyria 전용 — 엔진의 구조 마커(예: `<instrumental>`, `[[A0]] [[B1]] [16.0:] …`) |
| `Content-Type` | `audio/mpeg` |

호출 전에 금액을 알고 싶다면 [`/estimate`](/docs/api-gateway/reference/estimate) 를 쓰세요.

  `X-Music-Structure`는 참고용 힌트이지 가사 전문이 아닙니다. Lyria Pro는 생성한 가사를 여기에 담는데, 값은 한 줄로 정규화되고 Latin-1로 표현할 수 없는 문자(한글·일본어)는 제거되며 200자에서 잘립니다.

---

### 예제

#### curl

```bash
curl -X POST https://api.baze.co/v1/gateway/audio/music/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "lyria-3-clip-preview",
    "prompt": "a calm lofi hip hop beat with soft piano and vinyl crackle"
  }' \
  --output track.mp3
```

#### Python

```python
import httpx

response = httpx.post(
    "https://api.baze.co/v1/gateway/audio/music/",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={
        "model": "elevenlabs-music",
        "prompt": "upbeat city pop with bright synths",
        "duration_seconds": 60,
    },
    timeout=300,  # 동기 생성이라 수 분이 걸릴 수 있습니다
)
response.raise_for_status()

with open("track.mp3", "wb") as f:
    f.write(response.content)

print(response.headers["X-Credits-Charged"])          # "150.0"
print(response.headers.get("X-Audio-Duration-Seconds"))
```

#### 효과음 — 길이를 엔진에 맡기기

```bash
curl -X POST https://api.baze.co/v1/gateway/audio/music/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "elevenlabs-sfx",
    "prompt": "a heavy wooden door closing"
  }' \
  --output door.mp3
```

  클라이언트 타임아웃을 넉넉히 잡으세요. Lyria Clip은 약 10~15초, Lyria Pro는 약 35초가 걸리고, 3분짜리 ElevenLabs 트랙은 더 오래 걸립니다.

---

### 가격

음악은 위 표의 프로바이더 가격을 기준으로 크레딧이 차감됩니다.

프로바이더 호출 **전에** 최악값을 예약하고 성공 시 정확한 금액을 청구합니다. 프로바이더가 실패하면 예약이 해제되고 사용 기록도 남지 않습니다 — **실패한 생성에는 비용이 들지 않습니다.**

---

### 에러

| 상태 | 원인 |
| --- | --- |
| `400` | `model`/`prompt` 누락, 지원하지 않는 파라미터, `prompt` 또는 `lyrics`가 4,000자 초과(Lyria는 둘의 합이 4,000자 초과), 미지원 모델에 `lyrics`·`instrumental` 지정, `instrumental: true`와 `lyrics` 동시 지정, Lyria에 `duration_seconds` 지정 또는 상한 초과, 이 엔드포인트에 TTS 모델 사용, 프로바이더 콘텐츠 정책 차단 |
| `402` | 크레딧 부족 |
| `403` | 조직에 활성화되지 않은 모델 — 관리자에게 문의하세요 |
| `404` | 모델을 찾을 수 없음 |
| `429` | 요청 한도 초과(멤버당 분당 60회) |
| `500` | 모델에 가격이 설정되지 않음 — 무료로 생성하지 않습니다. 지원팀에 문의하세요 |
| `502` | 음악 엔진 실패(장애, 쿼터, 빈 응답 또는 읽을 수 없는 응답) — 재시도하세요 |
| `503` | 점검으로 서비스가 일시 중지됨 |

  **엔진 간 폴백은 없습니다.** Lyria가 프롬프트를 차단하면 차단 사유를 담은 `400`을 받습니다 — 다른 엔진으로 조용히 다시 돌리지 않습니다. 돈을 낸 그 엔진의 결과이거나 에러이지, 대체품은 없습니다.

---

### 참고

- 가사는 프롬프트에 인라인으로 붙어 엔진에 전달됩니다. 두 엔진 모두 별도의 가사 파라미터가 없습니다. Lyria는 둘을 하나의 텍스트(4,000자 제한)로 받기 때문에, `prompt` + `lyrics`의 합이 그 한도를 넘으면 조용히 자르지 않고 거절합니다.
- 음악 생성은 감사 로그에 `event_type="audio"`, `endpoint="/v1/gateway/audio/music/"`로 남고 사용량에는 `audio_credit`으로 집계됩니다 — [TTS](./audio-tts)와 같은 경로입니다.
- 레퍼런스 오디오 기반 커버(Mureka 계열 `reference_audio`)는 게이트웨이에서 의도적으로 제공하지 않습니다.
