# API Gateway

> API Gateway 개요 및 빠른 시작

KAIROS Chat API Gateway에 오신 것을 환영합니다! 🙌

API Gateway는 OpenAI, Anthropic, Google Gemini, xAI, Perplexity 등 주요 AI 제공업체의 모델을 **하나의 API 키와 하나의 Base URL**로 통합 제공하는 LLM 게이트웨이입니다.

기존에 사용하시던 OpenAI SDK나 Anthropic SDK를 그대로 사용하면서, Base URL만 변경하면 바로 시작할 수 있습니다.

  API Gateway란 무엇인가요?
  
    API Gateway는 여러 AI 제공업체의 API를 하나의 통합 엔드포인트로 제공하는 프록시 서비스입니다.
    기존에는 OpenAI, Anthropic, Google 등 각 제공업체별로 별도의 API 키와 엔드포인트를 관리해야 했지만,
    Gateway를 사용하면 하나의 키로 모든 모델에 접근할 수 있습니다.
  

## Base URL

| API 형식 | Base URL |
| --- | --- |
| OpenAI 호환 (Chat Completions) | `https://api.baze.co/v1/gateway` |
| Anthropic 네이티브 (Messages API) | `https://api.baze.co/v1/gateway/claude` |
| OpenAI Responses API | `https://api.baze.co/v1/gateway` |
| Google Gemini 네이티브 | `https://api.baze.co/v1/gateway/gemini` |

## 전체 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/v1/gateway/models/` | [모델 목록 (`?type=` 으로 종류별)](/docs/api-gateway/getting-started/models) |
| GET | `/v1/gateway/models/{model}/` | [모델 하나 상세](/docs/api-gateway/getting-started/models) |
| POST | `/v1/gateway/chat/completions/` | [OpenAI 호환 채팅](/docs/api-gateway/reference/chat-completions) |
| POST | `/v1/gateway/responses/` | [OpenAI Responses API](/docs/api-gateway/reference/responses-api) |
| POST | `/v1/gateway/claude/v1/messages/` | [Anthropic Messages API](/docs/api-gateway/reference/messages-api) |
| POST | `/v1/gateway/claude/v1/messages/count_tokens/` | [Anthropic 토큰 수 계산](/docs/api-gateway/reference/messages-api) |
| GET | `/v1/gateway/claude/v1/models/` | [Anthropic 형식 모델 목록](/docs/api-gateway/reference/messages-api) |
| GET · POST | `/v1/gateway/gemini/v1beta/models/…` | [Gemini 네이티브 (목록 · generateContent · 스트리밍)](/docs/api-gateway/reference/gemini-native) |
| POST | `/v1/gateway/embeddings/` | [임베딩](/docs/api-gateway/reference/embeddings) |
| POST | `/v1/gateway/rerank/` | [검색 결과 재정렬](/docs/api-gateway/reference/rerank) |
| POST | `/v1/gateway/exa/search/` · `…/contents/` · `…/answer/` | [웹 검색 (Exa)](/docs/api-gateway/reference/web-search) |
| POST | `/v1/gateway/guard/` | [개인정보 탐지·마스킹](/docs/api-gateway/reference/guard) |
| POST | `/v1/gateway/decisions/` | [판정 모델 (Jev · OpenAI)](/docs/api-gateway/reference/decisions) |
| GET · POST | `/v1/gateway/mcp/` (GET) · `/v1/gateway/mcp/{suite}/` (POST) | [MCP 도구 묶음](/docs/api-gateway/reference/mcp) |
| POST | `/v1/gateway/audio/speech/` | [음성 합성 (TTS)](/docs/api-gateway/reference/audio-tts) |
| POST · GET | `/v1/gateway/audio/transcriptions/` · `…/{operation_id}/` | [받아쓰기 (STT) 시작 · 상태](/docs/api-gateway/reference/audio-stt) |
| POST | `/v1/gateway/audio/music/` | [음악·효과음 생성](/docs/api-gateway/reference/audio-music) |
| POST · GET | `/v1/gateway/images/generate/` · `…/{operation_id}/` | [이미지 생성 · 지연된 작업 상태](/docs/api-gateway/reference/image-generation) |
| POST · GET | `/v1/gateway/video/generation/` · `…/{operation_id}/` · `…/download/` | [비디오 생성 · 상태 · 다운로드](/docs/api-gateway/reference/video-generation) |
| POST · WS | `/v1/gateway/realtime/sessions/` · 실시간 소켓 | [실시간 음성 대화·받아쓰기](/docs/api-gateway/reference/realtime) |
| POST | `/v1/gateway/chatbots/{chatbot_id}/chat/completions/` | [스튜디오 챗봇 호출](/docs/api-gateway/reference/chatbot-chat) |
| POST | `/v1/gateway/estimate/` | [호출 전 크레딧 견적](/docs/api-gateway/reference/estimate) |
| GET | `/v1/gateway/credits/` | [크레딧 잔액](/docs/api-gateway/reference/credits) |
| GET | `/v1/gateway/usage/` | [사용량 요약](/docs/api-gateway/reference/usage) |
| POST | `/v1/gateway/keys/revoke/` | [지금 쓰는 키 해지](/docs/api-gateway/reference/keys-revoke) |

## 호출 제한

| 제한 | 값 | 초과 시 |
| --- | --- | --- |
| 속도 제한 | 회원당 60초에 120건 | `429` |
| 챗봇 채팅 라우트 | 분당 30건 | `429` |
| 작업 상태 폴링 (비디오·이미지·받아쓰기) | 회원당 60초에 300건 (속도 제한과 별도) | `429` |
| 크레딧 예약 공용 한도 | 회원당 60초에 크레딧 예약 300건 (크레딧을 예약하는 모든 호출 합산 — 임베딩·리랭크·가드·앱 사용 포함) | `429`, `Retry-After` 없음 |
| 요청 본문 크기 | 25MB | `413` |
| TTS `input` 길이 | 4,000자 | `400` |

자세한 내용과 대처법은 [에러 가이드](/docs/gateway/reference/errors)를 참고하세요.

## 인증

모든 엔드포인트는 KAIROS Chat API 키가 필요합니다. 두 가지 헤더 방식을 지원합니다:

```bash
# 방법 1: Authorization 헤더 (OpenAI 스타일)
Authorization: Bearer YOUR_API_KEY

# 방법 2: x-api-key 헤더 (Anthropic SDK 스타일)
x-api-key: YOUR_API_KEY
```

자세한 내용은 [인증](/docs/gateway/getting-started/authentication)을 참조하세요.

## 빠른 시작

  시작하기 전에 KAIROS Chat API 키가 필요합니다. 아직 발급받지 않으셨다면 [인증 가이드](/docs/gateway/getting-started/authentication)를 참고해주세요.

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

터미널에서 바로 쓰거나 Claude Code·Codex·OpenCode·Hermes Agent 를 이 키로 돌리려면 [Baze CLI](/docs/api-gateway/integrations/baze-cli)를 쓰세요. 코딩 에이전트에게 설치를 맡길 수도 있습니다.

## 공식 제공업체 문서

| API | 공식 문서 |
| --- | --- |
| OpenAI Chat Completions | [platform.openai.com/docs/api-reference/chat](https://platform.openai.com/docs/api-reference/chat) |
| OpenAI Responses API | [platform.openai.com/docs/api-reference/responses](https://platform.openai.com/docs/api-reference/responses) |
| Anthropic Messages API | [docs.anthropic.com/en/api/messages](https://docs.anthropic.com/en/api/messages) |
| Google Gemini | [ai.google.dev/api/generate-content](https://ai.google.dev/api/generate-content) |

  위 링크들은 각 제공업체의 **모델 호출 요청/응답 형식을 참고**하기 위한 문서입니다. API Gateway는 위
  [전체 엔드포인트](#전체-엔드포인트)에 나열된 경로만 지원하며, 제공업체의 네이티브 리소스 API(예: Google Gemini의
  File Search / `fileSearchStores`, 파일 스토어, 벡터 검색 등)는 Gateway를 통해 호출되지 않습니다. 해당 네이티브 기능이
  필요하신 경우 제공업체 API 키로 직접 호출하셔야 합니다.
