# 모델 목록

> 사용 가능한 LLM · 오디오 · 이미지 · 비디오 모델 조회

KAIROS Chat Gateway에서 사용 가능한 AI 모델을 조회하는 방법을 안내합니다.

조직에 활성화된 모든 모델을 API로 확인할 수 있으며, 반환된 모델 `id`를 API 요청의 `model` 파라미터로 사용하시면 됩니다.

어떤 모델을 사용할 수 있는지 먼저 확인해보세요. 조직의 구독 플랜에 따라 사용 가능한 모델이 다를 수 있습니다.

### 모델 조회

GET

조직에서 사용 가능한 모델 목록을 반환합니다. 채팅/LLM 모델뿐 아니라 오디오, 이미지, 비디오 모델도 함께 내려옵니다.

---

### 요청 헤더

```http
GET https://api.baze.co/v1/gateway/models/
Authorization: Bearer YOUR_API_KEY
```

---

### 쿼리 파라미터

type
모델 종류로 목록을 거릅니다. `llm`, `embedding`, `rerank`, `decisions`, `realtime`, `audio`, `image`, `video` 중 하나를 넣거나 쉼표로 여러 개를 나열합니다. 생략하면 모든 종류가 반환됩니다.

```http
GET /v1/gateway/models/?type=audio
GET /v1/gateway/models/?type=image,video
```

---

### 모델 종류

각 항목에는 어느 엔드포인트에 속하는 모델인지 알려주는 `type` 필드가 붙습니다.

| `type` | 모델 | 엔드포인트 |
| --- | --- | --- |
| `llm` | 채팅 · 추론 모델 | `/v1/gateway/chat/completions/` |
| `audio` | TTS·음악/효과음·음성 텍스트 변환(STT) 모델 | `/v1/gateway/audio/speech/` · `/v1/gateway/audio/music/` · `/v1/gateway/audio/transcriptions/` |
| `image` | 이미지 생성 모델 | `/v1/gateway/images/generate/` |
| `video` | 비디오 생성 모델 | `/v1/gateway/video/generation/` |
| `embedding` | 임베딩 모델 | [`/v1/gateway/embeddings/`](/docs/api-gateway/reference/embeddings) |
| `rerank` | 재정렬 모델 | [`/v1/gateway/rerank/`](/docs/api-gateway/reference/rerank) |
| `decisions` | 판정 모델 (Jev · OpenAI) | [`/v1/gateway/decisions/`](/docs/api-gateway/reference/decisions) |
| `realtime` | 실시간 음성 대화 모델 (WebSocket) | [`/v1/gateway/realtime`](/docs/api-gateway/reference/realtime) |

```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-opus-5",
      "object": "model",
      "created": 1776614400,
      "owned_by": "claude",
      "type": "llm"
    },
    {
      "id": "gemini-3.8-flash-tts",
      "object": "model",
      "created": 1777075200,
      "owned_by": "gemini",
      "audio_client": "google",
      "type": "audio"
    }
  ]
}
```

---

### 응답

```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-5.6-terra",
      "object": "model",
      "created": 1783694656,
      "owned_by": "openai",
      "profile_image_url": "https://factchat-public.s3.ap-northeast-2.amazonaws.com/public/svg/openai-icon-logo.svg",
      "type": "llm"
    },
    {
      "id": "claude-opus-5",
      "object": "model",
      "created": 1785151540,
      "owned_by": "claude",
      "profile_image_url": "https://factchat-public.s3.ap-northeast-2.amazonaws.com/public/png/claude_logo.png",
      "type": "llm"
    },
    {
      "id": "gemini-3.6-flash",
      "object": "model",
      "created": 1784730547,
      "owned_by": "gemini",
      "profile_image_url": "https://factchat-public.s3.ap-northeast-2.amazonaws.com/public/png/gemini_logo.png",
      "type": "llm"
    },
    {
      "id": "kimi-k3",
      "object": "model",
      "created": 1785325593,
      "owned_by": "moonshot-ai",
      "profile_image_url": "https://factchat-public.s3.ap-northeast-2.amazonaws.com/public/svg/kimi-logo.svg",
      "type": "llm"
    }
  ]
}
```

---

### 응답 필드

id
모델 이름. API 요청의 `model` 파라미터에 그대로 넣습니다.

object
항상 `"model"`.

created
모델 등록 시각 (Unix epoch 초).

owned_by
제공업체 식별자 (예: `openai`, `claude`, `gemini`).

profile_image_url
모델 로고 이미지 URL.

type
`llm` · `audio` · `image` · `video` 중 하나.

audio_client
오디오 모델에만 붙습니다. 오디오 레인 세 가지를 이 값으로 구분합니다.

| `audio_client` | 모델 종류 | 엔드포인트 |
| --- | --- | --- |
| `google_lyria3`, `elevenlabs` | 음악·효과음 | `/v1/gateway/audio/music/` |
| `soniox` | 음성 텍스트 변환(STT) | `/v1/gateway/audio/transcriptions/` |
| 그 밖의 값 (`google` 등) | TTS | `/v1/gateway/audio/speech/` |

다른 레인으로 보내면 `400`이 돌아오고, 응답 메시지가 올바른 엔드포인트를 알려줍니다.

---

### 모델 하나 조회

GET

모델 하나의 상세를 OpenAI 형식으로 반환합니다. LLM에서 찾지 못하면 조직에 활성화된 오디오·이미지·비디오 카탈로그에서 이어서 찾습니다.

```json
{
  "id": "claude-opus-5",
  "object": "model",
  "created": 1785151540,
  "owned_by": "claude",
  "profile_image_url": "https://factchat-public.s3.ap-northeast-2.amazonaws.com/public/png/claude_logo.png",
  "type": "llm"
}
```

---

### 사용 가능 모델 (2026-10-14 기준)

사용 가능한 모델은 조직 설정과 사용자가 속한 그룹의 권한에 따라 달라집니다. 아래 표는 2026년 10월 14일 기준 게이트웨이가 제공하는 주요 LLM 목록입니다. 모델은 수시로 추가되므로, 내 계정에서 실제로 쓸 수 있는 목록은 위 `/models` API로 확인하세요.

#### Anthropic
| 모델 ID | 표시 이름 | 사고 | 웹 검색 |
| --- | --- | --- | --- |
| `claude-fable-5` | Claude Fable 5 | ✓ | ✓ |
| `claude-fable-5-1` | Claude Fable 5.1 | ✓ | ✓ |
| `claude-haiku-4-5-20251001` | Claude 4.5 Haiku | ✓ | ✓ |
| `claude-haiku-5-5` | Claude Haiku 5.5 | ✓ | ✓ |
| `claude-opus-4-8` | Claude 4.8 Opus | ✓ | ✓ |
| `claude-opus-5` | Claude Opus 5 | ✓ | ✓ |
| `claude-opus-5-5` | Claude Opus 5.5 | ✓ | ✓ |
| `claude-sonnet-5` | Claude Sonnet 5 | ✓ | ✓ |
| `claude-sonnet-5-5` | Claude Sonnet 5.5 | ✓ | ✓ |
| `claude-opus-4-6` | Claude 4.6 Opus | ✓ | ✓ |
| `claude-opus-4-7` | Claude 4.7 Opus | ✓ | ✓ |
| `claude-sonnet-4-6` | Claude 4.6 Sonnet | ✓ | ✓ |

#### OpenAI
| 모델 ID | 표시 이름 | 사고 | 웹 검색 |
| --- | --- | --- | --- |
| `gpt-5.5` | GPT-5.5 | ✓ | ✓ |
| `gpt-5.6-luna` | GPT-5.6 Luna | ✓ | ✓ |
| `gpt-5.6-sol` | GPT-5.6 Sol | ✓ | ✓ |
| `gpt-5.6-terra` | GPT-5.6 Terra | ✓ | ✓ |
| `gpt-6.1-sol` | GPT-6.1 Sol | ✓ | ✓ |
| `gpt-6-astra` | GPT-6 Astra | ✓ | ✓ |
| `gpt-6-sol` | GPT-6 Sol | ✓ | ✓ |
| `gpt-6-luna` | GPT-6 Luna | ✓ | ✓ |
| `gpt-audio-1.5` | GPT Audio 1.5 | — | — |
| `gpt-5.1` | GPT-5.1 | ✓ | ✓ |
| `gpt-5.2` | GPT-5.2 | ✓ | ✓ |
| `gpt-5.2-pro` | GPT-5.2 Pro | ✓ | ✓ |
| `gpt-5.4` | GPT-5.4 | ✓ | ✓ |
| `gpt-5.4-mini` | GPT-5.4 mini | ✓ | ✓ |
| `gpt-5.4-nano` | GPT-5.4 nano | ✓ | ✓ |
| `gpt-5.4-pro` | GPT-5.4 Pro | ✓ | ✓ |

#### Google Gemini
| 모델 ID | 표시 이름 | 사고 | 웹 검색 |
| --- | --- | --- | --- |
| `gemini-4-argon` | Gemini 4 Argon | ✓ | ✓ |
| `gemini-3.1-pro-preview` | Gemini 3.1 Pro | ✓ | ✓ |
| `gemini-3.5-flash` | Gemini 3.5 Flash | ✓ | ✓ |
| `gemini-3.5-flash-lite` | Gemini 3.5 Flash-Lite | ✓ | ✓ |
| `gemini-3.6-flash` | Gemini 3.6 Flash | ✓ | ✓ |
| `gemini-3.7-flash` | Gemini 3.7 Flash | ✓ | ✓ |
| `gemini-3.8-flash` | Gemini 3.8 Flash | ✓ | ✓ |
| `gemini-3.1-flash-lite` | Gemini 3.1 Flash-Lite | ✓ | ✓ |

#### xAI
| 모델 ID | 표시 이름 | 사고 | 웹 검색 |
| --- | --- | --- | --- |
| `grok-4.7` | Grok 4.7 | — | — |
| `grok-4-1-fast` | Grok 4.1 Fast | ✓ | — |
| `grok-4.5` | Grok 4.5 | ✓ | — |
| `grok-4.6` | Grok 4.6 | ✓ | — |

#### 국내 모델
| 모델 ID | 표시 이름 | 사고 | 웹 검색 |
| --- | --- | --- | --- |
| `solar-pro4` | Solar Pro 4 | ✓ | — |
| `solar-mini4` | Solar Mini 4 | ✓ | — |
| `solar-pro3` | Solar Pro 3 | ✓ | — |

#### 기타 제공업체
| 모델 ID | 표시 이름 | 사고 | 웹 검색 |
| --- | --- | --- | --- |
| `deepseek-v4.1-flash` | DeepSeek V4.1 Flash | ✓ | — |
| `deepseek-v4-pro` | DeepSeek V4 Pro | ✓ | — |
| `glm-5.2` | GLM-5.2 | ✓ | — |
| `glm-5.3` | GLM-5.3 | ✓ | — |
| `glm-5.3-flash` | GLM-5.3-Flash | ✓ | — |
| `google/gemma-4-31B-it` | Gemma 4 | — | — |
| `kimi-k3` | Kimi K3 | ✓ | — |
| `muse-spark-1.3` | Muse Spark 1.3 | ✓ | — |
| `qwen3.7-max` | Qwen 3.7 Max | ✓ | — |
| `qwen3.7-plus` | Qwen 3.7 Plus | ✓ | — |
| `qwen3.8-max` | Qwen 3.8 Max | ✓ | — |
| `qwen3.8-flash` | Qwen 3.8 Flash | ✓ | — |
| `seed-2-0-lite-260428` | Seed 2.0 Lite | ✓ | — |
| `seed-2-0-pro-260328` | Seed 2.0 Pro | ✓ | — |
| `sonar-pro` | Sonar Pro | — | ✓ |
| `sonar-reasoning-pro` | Sonar Reasoning Pro | — | ✓ |
| `google/gemma-3-27b-it` | Gemma 3 | — | — |

#### 레거시

아래 모델은 API로는 계속 응답하지만 앱에서는 더 이상 제공하지 않습니다. 종료일이 정해지면 모델 카드에 `shutdown_at`으로 표시됩니다.

| 레거시 모델 | 대체 |
| --- | --- |
| `claude-opus-4-6` | `claude-opus-4-8` |
| `claude-opus-4-7` | `claude-opus-5` |
| `claude-sonnet-4-6` | `claude-sonnet-5` |
| `gpt-5.1` | `gpt-5.6-luna` |
| `gpt-5.2` | `gpt-5.6-terra` |
| `gpt-5.2-pro` | 대체 없음 |
| `gpt-5.4` | `gpt-5.6-terra` |
| `gpt-5.4-mini` | `gpt-5.6-luna` |
| `gpt-5.4-nano` | `gpt-5.6-luna` |
| `gpt-5.4-pro` | 대체 없음 |
| `gemini-3.1-flash-lite` | `gemini-3.5-flash-lite` |
| `solar-pro3` | `solar-pro4` |
| `google/gemma-3-27b-it` | `google/gemma-4-31B-it` |

---

  **게이트웨이 API로 호출할 수 없는 모델이 있습니다.** 아래 모델은 앱 화면에서만 제공되며, 정책상 API로는 제공되지 않습니다. `model` 파라미터로 호출하면 사용할 수 없다는 오류(403)가 반환됩니다.

  - **Super Agent** (`mindlogic-super-agent`): 앱 전용 기능입니다. 영상·음악·음성 등 내장 도구는 게이트웨이 API로 호출할 수 없습니다.
  - **무료 모델** (`gpt-5-nano`, SAIT 등): 무료 모델은 게이트웨이 API 대상에서 제외됩니다. API에서는 `gpt-5.6-luna`, `gpt-5.6-terra`, `claude-sonnet-5` 등 일반 모델을 사용하세요.

  위 표는 채팅/LLM 모델 목록입니다. 오디오, 이미지, 비디오 모델도 같은 엔드포인트에서 내려오며 `?type=audio`, `?type=image`, `?type=video`로 걸러낼 수 있습니다. 파라미터와 과금은 각 API 레퍼런스 페이지를 참조하세요. 오디오 항목에는 `audio_client` 필드도 있습니다: `google_lyria3` 또는 `elevenlabs`면 `/audio/music/`용 음악·효과음 모델, `soniox`면 `/audio/transcriptions/`용 STT 모델이고, 그 외는 `/audio/speech/`용 TTS 모델입니다.

### 코드 예제

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.baze.co/v1/gateway",
)

models = client.models.list()
for model in models.data:
    print(model.id)
```

---

### 모델별 권장 엔드포인트

| 모델 제공업체 | 권장 엔드포인트 |
| --- | --- |
| Anthropic | `/v1/gateway/chat/completions/` 또는 `/v1/gateway/claude/v1/messages/` |
| OpenAI (채팅) | `/v1/gateway/chat/completions/` |
| OpenAI (o-시리즈 추론) | `/v1/gateway/responses/` |
| Google Gemini | `/v1/gateway/chat/completions/` |
| OpenAI (Codex) | `/v1/gateway/responses/` |
| 기타 제공업체 | `/v1/gateway/chat/completions/` |

---

### 참고

- 조직에 활성화된 모델만 이 목록에 표시됩니다
- 모델 가용성은 구독 플랜에 따라 다릅니다
- API 요청에서 `id` 필드를 `model` 파라미터로 사용하세요
- `type` 필드로 해당 모델의 엔드포인트를 확인하거나, 조회 단계에서 `?type=`으로 미리 걸러내세요

  어떤 엔드포인트를 사용해야 할지 모르겠다면, `/v1/gateway/chat/completions/`를 사용해보세요. 대부분의 모델이 이 엔드포인트를 통해 사용 가능합니다.
