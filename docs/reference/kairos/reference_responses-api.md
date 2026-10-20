# OpenAI Responses API

> OpenAI Responses API 엔드포인트

OpenAI의 최신 Responses API를 지원하는 엔드포인트입니다.

o-시리즈 추론 모델, Codex 코드 생성 모델(`gpt-5.3-codex`, `gpt-5.2-codex`, `gpt-5.1-codex-max`) 등 Responses API 전용 모델을 사용하려면 이 엔드포인트를 이용해주세요. `reasoning_effort`와 `tools`를 동시에 사용해야 하는 경우에도 이 엔드포인트가 권장됩니다. 백그라운드 실행과 폴링을 통한 장시간 작업도 지원합니다.

- 공식 레퍼런스: [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)

  Responses API는 `messages` 대신 `input`을, `max_tokens` 대신 `max_output_tokens`를 사용합니다. OpenAI 모델만 지원됩니다.

---

### 응답 생성

POST

OpenAI Responses API 형식으로 응답을 생성합니다.

---

### 추가 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/v1/gateway/responses/{id}/` | 백그라운드 응답 폴링 |
| POST | `/v1/gateway/responses/{id}/cancel/` | 백그라운드 응답 취소 |

---

### 파라미터

model
OpenAI 모델 이름.

input
입력 메시지. 문자열 하나를 넣으면 사용자 메시지 한 건으로 해석하고, 배열이면 `role` + `content` 항목(또는 `input_text` 블록)으로 읽습니다. 필수는 아니며, 생략하면 빈 입력으로 전달됩니다 — 실제로 쓸 때는 `input`이나 `instructions` 중 최소 하나는 넣으세요.

instructions
시스템 프롬프트 대체. `input` 전에 적용됩니다.

max_output_tokens
최대 출력 토큰 (기본값: 4096).

stream
SSE 스트리밍 활성화.

reasoning
추론 설정: `{"effort": "low" | "medium" | "high", "summary": "auto" | "none"}`.

text
구조화된 출력을 위한 출력 형식 설정.

background
백그라운드 작업으로 실행 — 즉시 반환 후 폴링.

previous_response_id
다중 턴 대화를 위한 응답 체이닝.

---

### 응답 형식

```json
{
  "id": "resp_abc123",
  "object": "response",
  "created_at": 1720000000,
  "status": "completed",
  "model": "gpt-5.2",
  "output": [
    {
      "type": "message",
      "id": "msg_abc",
      "role": "assistant",
      "content": [
        {"type": "output_text", "text": "The answer is 42."}
      ]
    }
  ],
  "usage": {
    "input_tokens": 25,
    "output_tokens": 30,
    "output_tokens_details": {
      "reasoning_tokens": 512
    }
  }
}
```

---

### 사용 예제

```python
import httpx

BASE = "https://api.baze.co/v1/gateway"
HEADERS = {"Authorization": "Bearer YOUR_API_KEY", "Content-Type": "application/json"}

# 응답 생성
r = httpx.post(f"{BASE}/responses/", json={
    "model": "gpt-5.2-codex",
    "input": [{"role": "user", "content": "Analyze this dataset..."}],
}, headers=HEADERS, timeout=120.0)
data = r.json()

if data["status"] == "completed":
    print(data["output"][-1]["content"][0]["text"])
```

---

### 지원 모델

| 패밀리 | 예시 | 비고 |
| --- | --- | --- |
| Codex 시리즈 | `gpt-5.3-codex`, `gpt-5.2-codex`, `gpt-5.1-codex-max` | Responses API 전용 — Chat Completions에서 사용 시 404 반환 |
| GPT-5.6 시리즈 | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | Chat Completions로도 사용 가능. `reasoning_effort` + `tools` 동시 사용 시 이 엔드포인트 권장 |
| Standard | `gpt-5.2`, `gpt-5.1`, `gpt-5` | Chat Completions로도 사용 가능 |

---

### 제한 사항

- OpenAI 모델만 지원됩니다
- Anthropic 모델은 [Messages API](/docs/gateway/api-reference/messages-api)를 사용하세요
- Codex 모델(`gpt-5.2-codex`, `gpt-5.1-codex-max`)은 이 엔드포인트에서만 지원됩니다 — `/chat/completions/`에서 사용하면 404가 반환됩니다
