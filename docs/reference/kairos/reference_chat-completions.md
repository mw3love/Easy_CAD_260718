# Chat Completions API

> OpenAI 호환 채팅 완성 엔드포인트

가장 범용적인 텍스트 생성 엔드포인트입니다.

OpenAI, Anthropic, Google Gemini, xAI 등 대부분의 모델을 이 하나의 엔드포인트로 사용할 수 있으며, OpenAI SDK와 100% 호환됩니다. 기존 OpenAI 코드의 Base URL만 변경하면 바로 시작할 수 있습니다.

- 공식 레퍼런스: [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat)

  이 엔드포인트는 텍스트 모델 전용입니다. 이미지 모델을 `model`로 지정하면 `404 invalid_request_error - Model '<name>' not found`가 반환됩니다 — 이미지는 [`/images/generate`](/docs/gateway/api-reference/image-generation)를 사용하세요.

---

### Chat Completions

POST

채팅 완성을 생성합니다. 게이트웨이는 OpenAI Chat API와 동일한 요청/응답 스키마를 구현합니다.

---

### 요청 헤더

```http
POST https://api.baze.co/v1/gateway/chat/completions/
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

---

### 파라미터

#### 핵심

model
`GET /v1/gateway/models/`에서 확인 가능한 모델 이름.

messages
대화 기록 (role + content).

System / Developer message
모델이 따라야 하는 지침.

  role
  `"system"` 또는 `"developer"`

  content
  지침 내용

User message
사용자 입력.

  role
  `"user"`

  content
  사용자 입력 내용

Assistant message
모델이 생성한 응답.

  role
  `"assistant"`

  content
  생성된 응답

stream
SSE 스트리밍 활성화 (기본값: `false`).

stream_options
`{"include_usage": true}` — 마지막 스트림 청크에 사용량 포함.

---

#### 샘플링

temperature
무작위성 0–2. 낮을수록 더 결정적. 기본값: `1.0`.

  일부 OpenAI 모델(`gpt-5`, `gpt-5-mini`, `gpt-5.1-chat-latest`, `gpt-5.2-chat-latest`)은 `temperature: 1`만 지원합니다. 다른 값을 설정하면 400 에러가 반환됩니다.

top_p
핵 샘플링 임계값. 기본값: `1.0`.

top_k
Top-k 샘플링 (Anthropic OpenAI 호환 전용).

---

#### 출력 제한

max_tokens
최대 출력 토큰. 최신 모델에서는 `max_completion_tokens`로 자동 변환됩니다.

  추론 모델(GPT-5 시리즈, Gemini 3.1 Pro)은 내부 추론 토큰이 `max_tokens` 예산에 포함됩니다. 너무 낮게 설정하면(예: 4096 미만) 빈 응답이 반환될 수 있습니다. 추론이 필요한 작업에는 최소 `16000` 이상 사용하세요.

max_completion_tokens
직접 별칭; o-시리즈 / gpt-5+ 모델에 사용.

stop
최대 4개의 중단 시퀀스.

---

#### 도구 호출

tools
도구 정의 목록 (`type: "function"`).

tool_choice
`"auto"`, `"none"`, `"required"`, 또는 `{"type":"function","function":{"name":"..."}}`.

---

#### 구조화된 출력

response_format
`{"type": "json_schema", "json_schema": {"name": "...", "strict": true, "schema": {...}}}`. `strict: true`와 `additionalProperties: false`가 포함된 유효한 JSON Schema가 필요합니다.

---

#### 추론 / 사고

reasoning_effort
`"low"` / `"medium"` / `"high"` — OpenAI o-시리즈·gpt-5+ 및 Gemini 계열. Gemini에서는 Google이 내부적으로 사고 토큰으로 환산합니다 (low ≈ 1,024 / medium ≈ 8,192 / high ≈ 24,576 토큰).

thinking_budget
사고 토큰 예산. Gemini 계열에서만 사용합니다. 게이트웨이가 값을 `reasoning_effort`로 환산해 전달합니다 — `1`–`2048`은 low, `2049`–`16384`는 medium, `16385` 이상은 high. `0` 또는 `-1`(자동)은 별도 지정 없이 모델 기본값으로 동작합니다.

thinking_level
`"minimal"` / `"low"` / `"medium"` / `"high"` — Gemini 계열. `minimal`은 `low`로 처리됩니다.

  `thinking_budget`·`thinking_level`은 Gemini 계열 전용입니다. 다른 제공업체 모델에 보내면 변환 없이 그대로 전달되므로 사용하지 마세요. 두 파라미터를 함께 보내면 에러가 나지는 않고 `thinking_level`이 우선하며 `thinking_budget`은 무시됩니다.

  일부 모델에서 `reasoning_effort`와 `tools`를 동시에 사용하면 400 에러가 발생할 수 있습니다 (GPT-5.6 시리즈, chat 모델, Grok 4.6 등). 게이트웨이는 이 경우 자동으로 `reasoning_effort`를 제거하고 재시도하므로, 별도 처리 없이 안정적으로 사용할 수 있습니다.

---

### 챗봇 호출

POST

특정 챗봇을 API 키로 호출합니다. 일반 `/chat/completions/`가 모델에 그대로 중계하는 것과 달리, 이 엔드포인트는 챗봇의 파이프라인(지식 검색, 도구 호출 등)을 전부 태웁니다.

- `model`은 받아도 무시합니다. 챗봇에 설정된 모델이 사용됩니다.
- 상태를 서버에 저장하지 않습니다. 대화 맥락이 필요하면 매 호출마다 `messages`에 전체 기록을 담아 보내세요.
- 챗봇의 `allow_api_access`가 켜져 있어야 합니다. 꺼져 있으면 호출이 거절됩니다.
- 이 경로에는 분당 30건의 별도 속도 제한이 걸립니다 (게이트웨이 공통 제한은 60초에 120건).
- 응답은 OpenAI `chat.completion` 형식이며, `usage`는 항상 `null`입니다. 대신 이번 호출에 청구된 크레딧이 `credits`로, 이번 턴이 만든 파일이 `files`로 함께 옵니다.
- 전체 파라미터·응답·에러는 [챗봇 호출 API](/docs/api-gateway/reference/chatbot-chat) 문서를 참고하세요.

```bash
curl -X POST https://api.baze.co/v1/gateway/chatbots/1234/chat/completions/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "환불 규정 알려줘"}]
  }'
```

---

### 지원 제공업체

| 제공업체 | 예시 모델 |
| --- | --- |
| OpenAI | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5` |
| Anthropic | `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5`, `claude-haiku-4-5-20251001` |
| Google Gemini | `gemini-3.1-pro-preview`, `gemini-3.7-flash`, `gemini-3.5-flash` |
| xAI | `grok-4.7`, `grok-4.6`, `grok-4.5` |
| Perplexity | `sonar-pro`, `sonar-reasoning-pro` |
| 오픈소스 | `google/gemma-4-31B-it` |

  Anthropic 네이티브 기능(확장 사고, 프롬프트 캐싱, 비전)이 필요하신가요? [Messages API](/docs/gateway/api-reference/messages-api)를 사용하시면 모든 Anthropic 전용 기능을 그대로 사용할 수 있습니다.

 Codex 모델(`gpt-5.2-codex`, `gpt-5.1-codex-max`)은 이 엔드포인트에서 지원되지 않습니다. [Responses API](/docs/gateway/api-reference/responses-api)를 사용하세요.

---

### 코드 예제

#### 기본 채팅 (Python)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.baze.co/v1/gateway",
)

response = client.chat.completions.create(
    model="claude-sonnet-5",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

#### 스트리밍 (JavaScript)

```javascript
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "YOUR_API_KEY",
  baseURL: "https://api.baze.co/v1/gateway",
});

const stream = await client.chat.completions.create({
  model: "gemini-3.7-flash",
  messages: [{ role: "user", content: "Tell me a joke." }],
  stream: true,
});

for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}
```

---

### 다음 단계

- [OpenAI SDK 연동](/docs/gateway/integrations/openai-sdk) — Python/JavaScript에서 바로 사용해보세요
- [curl 예제](/docs/gateway/integrations/curl) — 터미널에서 빠르게 테스트
- [에러 가이드](/docs/gateway/reference/errors) — 문제 발생 시 참고
