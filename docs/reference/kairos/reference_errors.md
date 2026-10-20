# 에러

> API Gateway 에러 코드 및 트러블슈팅

에러가 발생했을 때 당황하지 마세요! 🙌

이 페이지에서는 KAIROS Chat API Gateway에서 발생할 수 있는 에러 코드와 응답 형식을 정리하고, 증상별 해결 방법을 안내합니다. 대부분의 에러는 간단한 설정 변경으로 해결할 수 있습니다.

## HTTP 상태 코드

| 상태 | 의미 |
| --- | --- |
| `200` | 성공 |
| `400` | 잘못된 요청 — 유효하지 않은 파라미터 또는 엔드포인트에 맞지 않는 모델 타입 |
| `401` | 인증 실패 — API 키 누락 또는 유효하지 않음 |
| `402` | 결제 필요 — 크레딧 잔액 소진 |
| `403` | 접근 거부 — 모델이 조직에 활성화되지 않았거나, 게이트웨이 API로 제공되지 않는 무료·제외 모델이거나, Cloudflare가 요청을 차단 (아래 `error code: 1010` 참고) |
| `404` | 찾을 수 없음 — 모델을 찾을 수 없거나 엔드포인트 경로 오류 |
| `413` | 요청 본문 초과 — 요청 본문이 25MB를 넘음 |
| `429` | 요청 과다 — 게이트웨이 속도 제한(회원당 60초에 120건) 초과. 응답의 `Retry-After` 헤더가 다시 시도할 때까지 기다릴 초를 알려 줍니다 |
| `500` | 내부 서버 오류 — 업스트림 제공업체 오류 |
| `503` | 서비스 이용 불가 — 점검으로 서비스가 일시 중지됨 |

스트리밍 요청(`"stream": true`)도 제공업체가 **시작 전에** 거절하면 `200` 이 아니라 위와 같은 HTTP 오류(보통 `400`, 일시 장애면 `502`)로 오며 과금되지 않습니다. 스트림이 시작된 뒤에 난 오류만 스트림 안의 오류 이벤트로 옵니다.

WebSocket(실시간 음성)은 HTTP 상태 대신 닫힘 코드로 알려 줍니다. [Realtime 의 닫힘 코드](/docs/api-gateway/reference/realtime)를 참고하세요.

---

## 에러 응답 형식

```json
{
  "detail": {
    "code": 401,
    "message": "Authentication Error - Bearer token is not supplied"
  }
}
```

---

## 호출 제한

| 제한 | 값 | 초과 시 |
| --- | --- | --- |
| 게이트웨이 공통 속도 제한 | 회원당 60초에 120건 | `429` |
| 챗봇 채팅 라우트 (`/chatbots/{chatbot_id}/chat/completions/`) | 분당 30건 | `429` |
| 작업 상태 폴링 (비디오·이미지·전사의 `GET …/{operation_id}/`) | 회원당 60초에 300건 (공통 한도와 별도로 셈) | `429` |
| 크레딧 예약 공용 한도 | 회원당 60초에 크레딧 예약 300건 — 크레딧을 예약하는 호출은 임베딩·리랭크·가드와 앱 사용까지 모두 합산 | `429` (`detail.code` `6005`, `Retry-After` 없음) |
| 요청 본문 크기 | 25MB | `413` |
| TTS `input` 길이 | 4,000자 | `400` |
| 비디오 참조 이미지 픽셀 수 (ByteDance/ModelArk) | 36,000,000 (가로 × 세로) | `400` |

속도 제한은 API 키가 아니라 회원 기준으로 셉니다. 같은 회원이 키를 여러 개 써도 한도는 하나입니다.

작업 상태 폴링은 따로 셉니다. 여러 작업을 동시에 기다려도 폴링 때문에 새 생성 요청이 막히지 않습니다. 다운로드(`…/download/`)는 폴링이 아니라 공통 한도에 포함됩니다.

게이트웨이 속도 제한으로 `429`를 받으면 `Retry-After` 헤더(초)만큼 기다린 뒤 다시 보내세요.

25MB 한도는 `Content-Length` 헤더와 실제 본문 양쪽에서 검사합니다. base64로 인코딩한 이미지는 원본보다 약 33% 커지므로, `input_images`에 데이터 URL을 넣는다면 원본 파일 기준 18MB 안팎이 실질 상한입니다. 이미지가 크다면 데이터 URL 대신 `http(s)` URL을 넘기는 편이 안전합니다.

---

## 자주 발생하는 에러

| 에러 | 상태 | 원인 | 해결 방법 |
| --- | --- | --- | --- |
| `Authorization header is not supplied` | 401 | 요청에 API 키 없음 | `Authorization: Bearer KEY` 또는 `x-api-key: KEY` 헤더 추가 |
| `Bearer token is not supplied` | 401 | `Authorization` 헤더 형식 오류 | `Authorization: Bearer YOUR_KEY` 형식 사용 |
| `Invalid API key` | 401 | 키가 존재하지 않음 (오타, 다른 환경의 키 등) | 개발자 설정에서 키 확인 |
| `This API key has been revoked. Create a new key in the console.` | 401 | 해지된 키 | 콘솔에서 새 키를 만드세요 |
| `This API key is disabled. Turn it back on in the console, or use another key.` | 401 | 비활성화된 키 | 콘솔에서 키를 다시 켜거나 다른 키를 쓰세요 |
| `Model 'X' not found` | 404 | 모델 이름 오류 또는 비활성화 | 채팅 모델: `/v1/gateway/models/` 확인. 이미지/오디오/비디오: 에러 응답에 사용 가능한 모델이 나열됩니다. |
| `Model 'X' is not an Anthropic model` | 400 | 비Anthropic 모델로 `/claude/v1/messages/` 사용 | 비Anthropic 모델은 `/chat/completions/` 사용 |
| `Model 'X' is not an OpenAI model` | 400 | 비OpenAI 모델로 `/responses/` 사용 | `/chat/completions/` 또는 `/claude/v1/messages/` 사용 |
| `Credit balance exhausted` | 402 | 크레딧 잔액 없음 | 개발자 설정에서 크레딧 충전 |
| `Rate limit exceeded` | 429 | 60초 창에서 회원당 120건(챗봇 채팅 라우트는 분당 30건, 작업 상태 폴링은 별도로 300건)을 넘김 | `Retry-After` 헤더만큼 기다렸다가 다시 보내고, 동시 요청 수를 줄이세요 |
| `Too many reservation requests. Please try again later.` | 429 | 크레딧 예약 공용 한도 초과: 회원당 60초에 크레딧 예약 300건. `detail.code`는 `6005`. 채팅·오디오·이미지·비디오·임베딩·리랭크·가드, 그리고 같은 회원의 앱 사용까지 크레딧을 예약하는 호출은 모두 합산 | `Retry-After` 헤더가 없습니다. 1분 안쪽으로 기다렸다가 동시 요청 수를 줄여 다시 보내세요 |
| `Request body too large. Maximum size is 25MB.` | 413 | 요청 본문이 25MB 초과 — base64 `input_images`가 가장 흔한 원인 | 이미지를 URL로 전달하거나 업로드 전에 리사이즈·압축하세요 |
| `content_policy_violation - The provider's safety system rejected this prompt. Nothing was charged. Rephrase the prompt and try again.` | 400 | 이미지·비디오 프롬프트가 제공업체의 안전 정책에 걸림 | 프롬프트를 바꿔 다시 요청하세요. 크레딧은 차감되지 않습니다 |
| 상태 조회·다운로드가 `404` | 404 | 다른 회원이 만든 작업의 `operation_id`를 사용 | 작업은 만든 회원만 조회할 수 있습니다. 작업을 만든 회원의 키로 조회하세요 |
| `Model 'X' is not enabled for your tenant.` | 403 | 이미지·비디오·오디오 모델이 조직에 활성화되지 않음 | 관리자에게 해당 모델 활성화를 요청하세요 |
| `Model 'X' is not available through the Gateway API.` | 403 | 무료 모델 또는 앱 전용 모델을 API로 호출 | `gpt-5.6-luna`, `claude-sonnet-5` 등 일반 모델을 사용하세요 |
| `Input text too long (N chars). Maximum is 4000 characters.` | 400 | TTS `input`이 4,000자 초과 | 텍스트를 4,000자 이하로 나눠 여러 번 호출하세요 |
| `input_urls[N] is WxH = P pixels, over this model's limit of 36000000 total pixels.` | 400 | ByteDance(ModelArk) 비디오 모델에 넘긴 참조 이미지의 전체 픽셀 수가 36,000,000 초과 | 이미지를 줄여서 다시 요청하세요. 크레딧은 차감되지 않습니다 |
| `Service is temporarily stopped for maintenance` | 503 | 점검으로 서비스 중지 | 점검이 끝난 뒤 재시도하세요 |
| `Model 'gpt-5.x-codex' not found` | 400 | Codex 모델로 `/chat/completions/` 사용 | Codex 모델은 `/v1/gateway/responses/`에서만 사용 가능 |
| `reasoning_effort` + `tools` 동시 사용 시 400 | 400 | 일부 모델이 `reasoning_effort`와 도구 호출을 동시에 지원하지 않음 | 게이트웨이가 자동으로 `reasoning_effort`를 제거하고 재시도합니다. 직접 처리가 필요한 경우 `reasoning_effort`를 제거하거나 [Responses API](/docs/gateway/api-reference/responses-api)를 사용하세요 |
| 추론 모델이 빈 응답 반환 | 200 | 낮은 `max_tokens` — 추론 토큰이 전체 예산을 소비 | 추론 모델(GPT-5 시리즈, Gemini 3.1 Pro)은 `max_tokens: 16000+` 사용. 일부 모델(`gpt-5`, `gpt-5-mini`, `gpt-5.1-chat-latest`, `gpt-5.2-chat-latest`)은 `temperature: 1`도 필요 |
| `error code: 1010` (JSON 아님) | 403 | `User-Agent` 헤더가 비어 있어 게이트웨이 도달 전에 Cloudflare가 차단 | 비어 있지 않은 `User-Agent`를 보내세요. Python `urllib`은 기본적으로 `User-Agent`를 보내지 않아 여기에 걸립니다. `requests`, `httpx`, OpenAI SDK는 자동으로 설정합니다 |
| 이미지 모델로 `/chat/completions` 호출 시 `Model 'X' not found` | 404 | 이미지 모델은 채팅 엔드포인트에서 사용할 수 없음 | `/v1/gateway/images/generate/`를 사용하세요 |

---

## 증상별 트러블슈팅

### 403 과 `error code: 1010` 이 반환되나요?

응답 본문이 JSON이 아니라 `error code: 1010` 텍스트라면, 게이트웨이에 닿기 전에 Cloudflare가 요청을 차단한 것입니다. 원인은 대부분 비어 있는 `User-Agent` 헤더입니다.

```python
# 잘못됨 — urllib은 User-Agent를 보내지 않아 403 + "error code: 1010"
import urllib.request
req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {API_KEY}"})

# 올바름 — 비어 있지 않은 User-Agent를 넣으면 통과
req.add_header("User-Agent", "my-app/1.0")
```

`requests`, `httpx`, OpenAI SDK는 기본 `User-Agent`를 설정하므로 이 문제가 없습니다.

### Claude Code에서 401 오류가 발생하나요?

Claude Code는 기본적으로 `x-api-key` 헤더를 전송합니다. `ANTHROPIC_API_KEY`가 아닌 `ANTHROPIC_AUTH_TOKEN`을 설정했는지 확인하세요:

```bash
export ANTHROPIC_AUTH_TOKEN=YOUR_API_KEY  # 올바름
export ANTHROPIC_API_KEY=YOUR_API_KEY     # 커스텀 Base URL에서 잘못됨
```

### Anthropic SDK에서 404 오류가 발생하나요?

Anthropic SDK는 Base URL에 `/v1/messages`를 자동 추가합니다. Base URL이 `/claude`로 끝나도록 설정하세요:

```bash
# 올바름
export ANTHROPIC_BASE_URL=https://api.baze.co/v1/gateway/claude

# 잘못됨 — SDK가 /v1/gateway/v1/messages/로 POST
export ANTHROPIC_BASE_URL=https://api.baze.co/v1/gateway
```

### 모델 이름이 맞는데도 찾을 수 없나요?

1. `GET /v1/gateway/models/`로 정확한 모델 이름 확인
2. 개발자 설정에서 해당 모델이 조직에 활성화되어 있는지 확인
3. API 키가 올바른 조직에 속하는지 확인

### 스트리밍이 예상치 않게 중단되나요?

일부 프록시 및 로드 밸런서가 SSE 응답을 버퍼링합니다. 스트리밍이 끊기면:
- `Connection: keep-alive` 헤더 설정
- 클라이언트 측 타임아웃 설정 줄이기
- 네트워크 관리자에게 프록시 버퍼링 설정 확인 요청

---

  위 방법으로도 문제가 해결되지 않으면, 담당자에게 문의해주세요. 에러 메시지와 요청 정보를 함께 전달해주시면 더 빠르게 도움을 드릴 수 있습니다.
