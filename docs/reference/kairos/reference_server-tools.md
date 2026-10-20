# 웹 검색과 코드 실행

> 제공사가 서버에서 실행하는 도구 — 웹 검색, 샌드박스 코드 실행

모델 제공사가 **자기 서버에서 직접 실행하는 도구**를 쓰는 방법입니다. 우리 쪽에서 따로 구현하거나 준비할 것이 없고, 요청에 도구를 선언하면 모델이 알아서 검색하거나 코드를 돌린 뒤 결과를 반영해 답합니다.

일반 함수 호출(function calling)과 다른 점은 **실행 주체**입니다. 함수 호출은 모델이 "이 함수를 불러 달라"고 요청하고 여러분의 코드가 실행합니다. 서버 도구는 제공사가 실행하고 결과까지 채워서 돌려줍니다. 왕복이 한 번으로 끝납니다.

---

### 무엇을 쓸 수 있나

| 도구 | 경로 | 하는 일 |
| --- | --- | --- |
| Claude 웹 검색 | `/v1/gateway/claude/v1/messages/` | 웹에서 찾아 출처와 함께 답합니다 |
| Gemini 검색 | `/v1/gateway/gemini/v1beta/...` | 검색 기반으로 답합니다 ([Gemini API](/docs/gateway/reference/gemini-native)) |
| OpenAI 웹 검색 | `/v1/gateway/responses/` | 웹에서 찾아 인용과 함께 답합니다 |
| Claude 코드 실행 | `/v1/gateway/claude/v1/messages/` | 샌드박스에서 코드를 실행합니다 |
| OpenAI 코드 인터프리터 | `/v1/gateway/responses/` | 컨테이너에서 파이썬을 실행합니다 |

---

## 웹 검색

### Claude

```bash
curl -X POST https://api.baze.co/v1/gateway/claude/v1/messages \
  -H "x-api-key: $YOUR_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-5",
    "max_tokens": 400,
    "messages": [
      { "role": "user", "content": "2026년 기준 대한민국 최저임금은 얼마인가요? 웹에서 확인해 주세요." }
    ],
    "tools": [
      { "type": "web_search_20250305", "name": "web_search", "max_uses": 2 }
    ]
  }'
```

응답의 `content` 배열에 단계가 그대로 들어옵니다.

| 블록 | 내용 |
| --- | --- |
| `server_tool_use` | 모델이 실제로 검색한 질의 |
| `web_search_tool_result` | 검색 결과 목록 |
| `text` | 출처가 붙은 최종 답변 |

`usage.server_tool_use.web_search_requests`에 검색 횟수가 들어옵니다. `max_uses`로 상한을 두면 예산을 통제할 수 있습니다.

### OpenAI

```bash
curl -X POST https://api.baze.co/v1/gateway/responses/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4",
    "input": "What is the current population of Seoul? Search the web.",
    "tools": [{ "type": "web_search" }]
  }'
```

`output`에 `web_search_call`이 먼저 오고, 이어지는 `message`의 `content[].annotations`에 인용 출처가 담깁니다.

---

## 코드 실행 (샌드박스)

계산, 데이터 처리, 검증처럼 **모델이 지어내면 안 되는 것**에 씁니다. 모델이 파이썬을 짜서 실제로 돌리고, 그 출력을 근거로 답합니다.

### Claude

베타 헤더가 필요합니다.

```bash
curl -X POST https://api.baze.co/v1/gateway/claude/v1/messages \
  -H "x-api-key: $YOUR_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: code-execution-2025-08-25" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-5",
    "max_tokens": 600,
    "messages": [
      { "role": "user", "content": "Use the code execution tool to compute the 30th Fibonacci number and print it." }
    ],
    "tools": [
      { "type": "code_execution_20250825", "name": "code_execution" }
    ]
  }'
```

실행 결과가 그대로 돌아옵니다.

```json
{
  "type": "bash_code_execution_result",
  "stdout": "832040\n",
  "stderr": "",
  "return_code": 0
}
```

  `anthropic-beta` 헤더는 **헤더로** 보내야 합니다. 본문에 `"betas": [...]`를 넣으면 `400 betas: Extra inputs are not permitted`가 납니다.

### OpenAI

```bash
curl -X POST https://api.baze.co/v1/gateway/responses/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5.4",
    "input": "Compute the standard deviation of [2,4,4,4,5,5,7,9] using python and print it.",
    "tools": [{ "type": "code_interpreter", "container": { "type": "auto" } }]
  }'
```

`output`에 `code_interpreter_call`이 들어오며, 모델이 작성한 코드와 실행 상태를 볼 수 있습니다.

---

### 과금

서버 도구는 **토큰과 별개로** 과금되며, 사용 내역에서 토큰 비용과 구분되어 기록됩니다.

| 도구 | 기준 | 주의 |
| --- | --- | --- |
| 웹 검색 | 검색 1회당 | `max_uses`로 상한을 두세요 |
| Claude 코드 실행 | 컨테이너 사용 시간 | **최소 5분**부터 계산합니다 |
| OpenAI 코드 인터프리터 | 컨테이너 사용 시간 | **최소 15분**부터 계산합니다 |

  코드 실행의 최소 과금 시간이 실제 실행 시간보다 훨씬 깁니다. 1초짜리 계산도 최소 시간만큼 냅니다. 짧은 호출을 여러 번 하는 것보다 한 요청에 모아서 처리하는 편이 훨씬 저렴합니다.

---

### 알아 두면 좋은 것

- 모델마다 지원 여부가 다릅니다. `GET /v1/gateway/models/{model}/`의 `pricing.web_search_per_1k`가 `null`이면 그 모델은 웹 검색을 지원하지 않습니다.
- 샌드박스는 제공사가 운영합니다. 실행 환경, 설치된 라이브러리, 네트워크 접근 여부는 제공사 정책을 따릅니다.
- 검색 결과와 실행 출력은 다음 턴의 입력 토큰이 됩니다. 대화를 이어 가면 그만큼 입력 비용이 늘어납니다.
