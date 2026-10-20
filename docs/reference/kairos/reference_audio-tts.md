# Audio — 텍스트 음성 변환

> Google Gemini TTS를 사용한 텍스트 음성 변환 엔드포인트

텍스트를 자연스러운 음성으로 변환하는 TTS(Text-to-Speech) 엔드포인트입니다.

Google Gemini TTS 모델을 활용하여 단일 화자 및 다중 화자 합성을 지원합니다. 팟캐스트, 오디오북, 안내 음성 등 다양한 용도로 활용해보세요.

- 공식 레퍼런스: [Google Gemini TTS](https://ai.google.dev/gemini-api/docs/speech-generation)

---

### 텍스트 음성 변환

POST

텍스트를 오디오로 변환합니다. 응답은 원시 PCM 바이트입니다.

---

### 파라미터

model
TTS 모델 이름 (예: `gemini-3.8-flash-tts`).

input
합성할 텍스트. 다중 화자의 경우 대화 형식을 사용합니다. 최대 4,000자이며, 넘기면 `400 Invalid Request Error - Input text too long (N chars). Maximum is 4000 characters.` 가 반환됩니다. 긴 원고는 4,000자 이하로 나눠 여러 번 호출한 뒤 PCM을 이어 붙이세요.

`gemini-3.8-flash-tts`는 `input`을 적힌 그대로 읽습니다. `Say cheerfully:` 같은 지시문이나 `[whispers]` 같은 대괄호 지시는 소리 내어 읽힐 수 있으니 넣지 마세요. 말투는 `instructions`에 적고, 웃음·한숨·쉼 같은 순간적인 소리는 아래 [소리 태그](#소리-태그)처럼 꺾쇠 괄호로 넣습니다.

voice
음성 이름 (기본값: `"Aoede"`). 옵션: `Aoede`, `Charon`, `Fenrir`, `Kore`, `Puck` 등.

speakers
다중 화자 매핑 `{speaker_name: voice_name}`.

instructions
말투 지시. 감정·속도·톤을 자연어로 적습니다(한국어 가능, 예: `"9시 뉴스 앵커처럼 또박또박하게"`). OpenAI `/audio/speech`와 같은 필드 이름이며, 요청 전체에 적용됩니다. 다중 화자 요청이면 두 화자의 모든 대사에 같이 적용됩니다. 최대 4,000자이고 `gemini-3.8-flash-tts`에서만 받습니다. 문자열이 아니거나 4,000자를 넘거나 다른 모델에 보내면 `400`이 반환됩니다. 조직의 콘텐츠 필터가 켜져 있으면 `input`과 같이 검사합니다. 자세한 내용은 [말투 지정](#말투-지정)을 참고하세요.

---

  응답은 원시 PCM 오디오(24kHz 모노, 16비트 LE)로 반환됩니다. MP3나 WAV로 변환하려면 아래 ffmpeg 예제를 참고해주세요.

### 응답

원시 PCM 오디오 바이트 (`audio/pcm`), 24kHz 모노, 16비트 리틀 엔디안.

| 헤더 | 설명 |
| --- | --- |
| `X-Input-Tokens` | 입력 텍스트에 소비된 토큰 |
| `X-Output-Tokens` | 오디오 출력에 소비된 토큰 |
| `Content-Type` | `audio/pcm` |

---

### 예제

#### curl

```bash
curl -X POST https://api.baze.co/v1/gateway/audio/speech/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.8-flash-tts",
    "input": "Hello! This is a test of the TTS gateway.",
    "voice": "Aoede"
  }' \
  --output speech.pcm
```

#### Python

```python
import httpx

response = httpx.post(
    "https://api.baze.co/v1/gateway/audio/speech/",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={
        "model": "gemini-3.8-flash-tts",
        "input": "Hello! This is a test of the TTS gateway.",
        "voice": "Aoede",
    },
)
response.raise_for_status()

with open("speech.pcm", "wb") as f:
    f.write(response.content)

print(f"Input tokens:  {response.headers.get('X-Input-Tokens')}")
print(f"Output tokens: {response.headers.get('X-Output-Tokens')}")
```

#### PCM을 MP3로 변환

```bash
ffmpeg -f s16le -ar 24000 -ac 1 -i speech.pcm speech.mp3
```

---

### 다중 화자 TTS

```json
{
  "model": "gemini-3.8-flash-tts",
  "input": "Alice: Hello Bob, how are you?\nBob: I'm doing great, thanks! <laugh>",
  "speakers": {
    "Alice": "Aoede",
    "Bob": "Puck"
  },
  "instructions": "Warm, relaxed podcast banter"
}
```

- `input`에는 한 줄에 한 대사씩 `화자: 대사` 형식으로 적습니다.
- `input`에 나오는 화자는 모두 `speakers`에 정의돼 있어야 합니다.
- `gemini-3.8-flash-tts`의 다중 화자는 정확히 2명입니다. `speakers`에 화자를 3명 이상 넣으면 `400`이 반환됩니다.
- `gemini-3.8-flash-tts`는 줄마다 해당 화자의 목소리로 합성합니다. 화자 이름 없이 이어지는 줄은 직전 대사에 붙고, 첫 대사보다 앞에 있는 줄(예: `TTS the following:`)은 읽지 않습니다.
- 대사 중간에 `speakers`에 없는 화자 이름으로 시작하는 줄(예: `Carol: ...`)이 있으면 `400`이 반환됩니다. `speakers`에 있는 이름으로 시작하는 줄이 하나도 없어도 `400`입니다.
- `instructions`를 함께 보내면 두 화자의 모든 대사에 같은 말투가 적용됩니다.

---

### 말투 지정

`gemini-3.8-flash-tts`는 `instructions`로 요청 전체의 말투를 정합니다. 읽을 문장은 `input`에, 어떻게 읽을지는 `instructions`에 나눠 적습니다. 순간적인 소리는 `input` 안의 [소리 태그](#소리-태그)로 넣습니다.

#### curl

```bash
curl -X POST https://api.baze.co/v1/gateway/audio/speech/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.8-flash-tts",
    "input": "오늘의 주요 소식을 전해 드립니다.",
    "voice": "Charon",
    "instructions": "9시 뉴스 앵커처럼 또박또박하게"
  }' \
  --output news.pcm
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.baze.co/v1/gateway",
)

response = client.audio.speech.create(
    model="gemini-3.8-flash-tts",
    voice="Charon",
    input="오늘의 주요 소식을 전해 드립니다.",
    instructions="9시 뉴스 앵커처럼 또박또박하게",
)
# 응답 본문은 원시 PCM입니다 (24kHz 모노, 16비트 LE).
with open("news.pcm", "wb") as f:
    f.write(response.content)
```

---

### 소리 태그

`gemini-3.8-flash-tts`는 `input` 안의 꺾쇠 괄호 태그를 읽지 않고 그 소리로 표현합니다. 태그는 소리가 나야 하는 위치에 넣습니다.

| 태그 | 표현 |
| --- | --- |
| `<laugh>` · `<giggle>` · `<chuckle>` | 웃음 |
| `<sigh>` | 한숨 |
| `<breath>` · `<gasp>` | 숨소리 · 놀라 숨 들이켜기 |
| `<cough>` · `<yawn>` | 기침 · 하품 |
| `<whispers>` | 속삭임 |
| `<short pause>` · `<long pause>` | 짧은 쉼 · 긴 쉼 |

```json
{
  "model": "gemini-3.8-flash-tts",
  "input": "정말요? <laugh> 그럴 줄 알았어요. <short pause> 그럼 다시 해 볼까요?",
  "voice": "Kore"
}
```

---

### 오디오 형식

| 속성 | 값 |
| --- | --- |
| 형식 | Raw PCM (WAV/MP3 헤더 없음) |
| 샘플 레이트 | 24,000 Hz |
| 채널 | 모노 (1 ch) |
| 비트 깊이 | 16비트 부호 있음, 리틀 엔디안 |

---

### 사용 가능한 모델

| 모델 | 표시 이름 | 10k 입력 토큰당 크레딧 | 10k 출력 토큰당 크레딧 |
| --- | --- | --- | --- |
| `gemini-3.8-flash-tts` | Gemini 3.8 Flash TTS | 10 | 180 |
| `gemini-3.1-flash-tts-preview` | Gemini 3.1 Flash TTS | 10 | 200 |
| `gemini-2.5-flash-preview-tts` | Gemini 2.5 Flash TTS | 5 | 100 |
| `gemini-2.5-pro-preview-tts` | Gemini 2.5 Pro TTS | 10 | 200 |

`gemini-3.8-flash-tts`는 요청마다 모델 내부 처리용 오디오 토큰 약 200개가 입력 토큰에 더해져 과금됩니다. 이 토큰은 `X-Input-Tokens` 헤더 값에 포함됩니다.

`gemini-3.8-flash-tts`가 최신 모델이며, 새로 연동한다면 이 모델을 권장합니다. `gemini-3.1-flash-tts-preview`와 Gemini 2.5 모델도 계속 지원합니다. 아래 음성 30종은 `gemini-3.8-flash-tts`에서도 그대로 쓸 수 있습니다.

---

### 사용 가능한 음성

**여성:**
`Aoede` (산뜻함), `Achernar` (부드러움), `Autonoe` (밝음), `Callirrhoe` (편안함), `Despina` (매끄러움), `Erinome` (선명함), `Gacrux` (성숙함), `Kore` (단단함), `Laomedeia` (경쾌함), `Leda` (젊음), `Pulcherrima` (적극적), `Sulafat` (따뜻함), `Vindemiatrix` (온화함), `Zephyr` (밝음)

**남성:**
`Achird` (친근함), `Algenib` (거친), `Algieba` (매끄러움), `Alnilam` (단단함), `Charon` (정보적), `Enceladus` (숨결), `Fenrir` (활기찬), `Iapetus` (선명함), `Orus` (단단함), `Puck` (경쾌함), `Rasalgethi` (정보적), `Sadachbia` (활발함), `Sadaltager` (박식함), `Schedar` (차분함), `Umbriel` (편안함), `Zubenelgenubi` (캐주얼)

---

### 참고

- 게이트웨이 공통 속도 제한(회원당 60초에 120건) 외에, 크레딧을 예약하는 호출에 회원당 분당 300건 공용 한도가 함께 적용됩니다. 이 한도는 채팅·이미지·비디오 호출과 나눠 씁니다. 초과하면 `429`가 반환됩니다.
- 점검으로 서비스가 중지된 동안에는 `503`이 반환됩니다.
- 조직에 따라 일부 모델이 활성화되지 않을 수 있습니다. 활성화되지 않은 모델을 사용하면 `403` 에러가 반환됩니다 — 관리자에게 문의하세요.
