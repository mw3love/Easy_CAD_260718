# Chatbot Chat Completions

> 스튜디오에서 만든 챗봇을 API 키로 호출하는 OpenAI 호환 엔드포인트

스튜디오에서 만든 챗봇을 그대로 호출하는 엔드포인트입니다.

일반 [`/chat/completions`](/docs/api-gateway/reference/chat-completions)가 모델에 요청을 중계하는 것과 달리, 이 엔드포인트는 챗봇에 설정된 시스템 프롬프트 · 지식 문서 · 도구 · 페르소나를 모두 태워 실행합니다. 요청과 응답은 OpenAI `chat.completion` 형식이라 OpenAI SDK의 `base_url`만 바꾸면 됩니다.

- 발급과 콘솔 설정 절차: [API로 챗봇 호출](/docs/baze/product/api-access)

---

### 챗봇 호출

POST

지정한 챗봇으로 대화 완성을 생성합니다. 끝의 슬래시가 없는 `/chat/completions` 경로도 같은 핸들러로 연결되므로, `base_url`을 챗봇 경로까지 지정하는 OpenAI SDK를 그대로 쓸 수 있습니다.

```http
POST https://api.baze.co/v1/gateway/chatbots/{chatbot_id}/chat/completions/
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

챗봇 id는 스튜디오 챗봇 상세 화면의 주소(`/dashboard/studio/[chatbot_id]`)에서 확인합니다.

---

### 호출 전 확인

호출이 성공하려면 세 가지가 모두 필요합니다.

1. 조직에 Gateway API가 켜져 있어야 합니다. 꺼져 있으면 `403`입니다.
2. 해당 챗봇의 API 접근 스위치가 켜져 있어야 합니다. 챗봇마다 따로 켜는 값이고 기본값은 꺼짐이며, 꺼진 챗봇을 호출하면 `403`입니다.
3. 게이트웨이 공통 API 키가 필요합니다. 인증 방식은 다른 게이트웨이 엔드포인트와 같습니다 — [인증 가이드](/docs/api-gateway/getting-started/authentication)를 참고하세요.

---

### 파라미터

messages
대화 기록입니다. 최소 한 건이 필요하며, 각 항목은 `role`(`system` · `user` · `assistant`)과 문자열 `content`로 구성됩니다. 서버가 대화를 저장하지 않으므로 멀티턴을 이어가려면 매 호출마다 이전 턴을 모두 함께 보내야 합니다.

stream
SSE 스트리밍 활성화 (기본값: `false`).

  요청 본문에 있는 값은 이 둘뿐입니다. `model` 파라미터는 없으며 챗봇에 설정된 모델이 사용됩니다. `messages`의 `system` 메시지는 대화 기록으로 옮길 때 제외됩니다 — 시스템 프롬프트는 챗봇이 가지고 있습니다.

---

### 응답

비스트리밍 응답은 OpenAI `chat.completion` 형식입니다. 아래 값은 형식을 보여주기 위한 예시입니다.

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1780321180,
  "model": "<챗봇에 설정된 모델>",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "..." },
      "finish_reason": "stop"
    }
  ],
  "usage": null,
  "credits": 12.5,
  "files": [
    {
      "file_id": 4821,
      "filename": "report.docx",
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "url": "https://api.baze.co/v1/public/f/4821/<signature>/?e=...",
      "expires_in": 86400
    }
  ]
}
```

usage
이 엔드포인트에서는 항상 `null`입니다. 챗봇의 파이프라인은 여러 단계로 나뉘어 실행되기 때문에 호출당 prompt/completion 토큰 분할이 하나의 값으로 의미를 갖지 않습니다. 토큰 내역은 `GET /v1/gateway/chatbots/{chatbot_id}/api-usage/`에서 확인합니다.

credits
이번 호출에 청구된 KAIROS Chat 크레딧입니다. 표준 OpenAI 필드가 아니며, 파이프라인 전체의 과금액을 하나의 값으로 돌려주기 위해 추가한 항목입니다. 확인된 과금 정보가 없으면 `0.0`입니다.

files
이번 턴이 생성한 파일 목록입니다. 항상 배열이며, 파일이 없으면 빈 배열입니다. `url`은 로그인이 필요 없는 서명 주소(`/v1/public/f/{file_id}/{signature}/?e=`)이고 유효 기간은 24시간(`expires_in`은 `86400`)입니다. 서명 자체가 자격 증명이므로, 주소를 가진 사람은 만료 전까지 누구나 파일을 내려받을 수 있습니다. 같은 링크가 `choices[0].message.content` 끝에 markdown으로도 덧붙습니다.

---

### 스트리밍

`stream: true`이면 `chat.completion.chunk` 델타를 SSE로 보냅니다. 델타를 이어 붙인 결과는 비스트리밍 응답의 `content`와 같습니다.

- 정상 종료: 파일이 생성됐다면 markdown 링크가 마지막 `content` 델타로 추가됨 → `finish_reason: "stop"` 청크 → 트레일러 청크 → `data: [DONE]`
- 오류 종료: 트레일러 청크가 **먼저** 전송된 뒤 (오류 직전에 이미 과금됐을 수 있습니다) → `data: {"error": {"message": "...", "type": "upstream_error"}}` → `data: [DONE]`

트레일러 청크는 `choices`가 빈 배열이고 `usage`는 `null`이며 `credits`와 `files`를 담습니다.

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion.chunk",
  "created": 1780321180,
  "model": "<챗봇에 설정된 모델>",
  "choices": [],
  "usage": null,
  "credits": 12.5,
  "files": []
}
```

비스트리밍 경로에서는 텍스트나 파일이 조금이라도 만들어졌으면 잘린 응답을 `200`으로 반환합니다. 텍스트와 파일이 모두 비어 있고 업스트림이 실패한 경우에만 `502`입니다.

---

### 실행되는 파이프라인

콘솔에서 같은 챗봇과 대화할 때와 같은 경로로 실행됩니다. 지식 문서 검색, 세션 파일 읽기, 이미지 · 음성 · 영상 생성, 코드 실행 샌드박스, 웹 검색, 커넥터 도구가 챗봇 제작자가 켜둔 설정 그대로 등록됩니다. 워크플로우가 게시되고 실행 모드가 워크플로우인 챗봇은 워크플로우 런타임이 턴을 담당합니다.

  API 호출 1건은 API 키를 소유한 멤버가 그 챗봇과 대화하는 것과 같습니다. 접근 권한 · 모델 유효성 · 크레딧을 인터랙티브 채팅과 동일하게 검증하고 차감합니다. 다른 점은 세션과 대화 기록을 남기지 않는다는 것입니다.

Super Agent 챗봇은 실행 환경이 달라 이 엔드포인트에서 `400`으로 거부됩니다. 다만 Super Agent 모델을 쓰더라도 워크플로우가 활성화된 챗봇은 워크플로우 런타임이 처리하므로 호출할 수 있습니다.

---

### 저장되는 것과 저장되지 않는 것

| 항목 | 동작 |
| --- | --- |
| 세션 · 대화 기록 | 저장하지 않음. 대화 맥락은 요청의 `messages`가 전부입니다 |
| 사용량 · 과금 | `usage` 기록 (`usage_type=apikey` + `api_key_id` + 챗봇 id) |
| 대화 내용 | `audit_log`에 기록 (`event_type="chat"`, `api_source="chatbot_api"`, 대상은 해당 챗봇). 스튜디오 챗봇 상세(`/dashboard/studio/[chatbot_id]`)의 호출 이력이 이 기록을 씁니다 |
| 대화 내용 열람 제한 | 조직에 대화 관리 권한이 꺼져 있으면 읽는 시점에 내용이 가려집니다 |
| 콘텐츠 안전 필터 | 조직에 필터가 켜져 있고 Gateway API 적용이 활성화된 경우, 파이프라인 실행 전에 요청 메시지를 마스킹하거나 `400`으로 거부 |

---

### 제한

| 항목 | 한도 | 초과 시 |
| --- | --- | --- |
| 게이트웨이 공통 | 회원당 60초에 120건 | `429` |
| 이 경로 추가 한도 | 회원당 분당 30건 | `429` |
| 요청 본문 크기 | 25MB | `413` |

두 속도 제한은 함께 적용되므로 둘 다 만족해야 합니다. 이 경로만 더 좁은 이유는 호출 한 건이 지식 검색 · 도구 반복 · 샌드박스까지 실행하는 무거운 작업이기 때문입니다.

---

### 에러

| 상태 코드 | 원인 |
| --- | --- |
| `400` | 지원하지 않는 챗봇 유형(Super Agent), 게시되지 않은 워크플로우, 콘텐츠 안전 필터에 의한 거부 |
| `401` | API 키 누락 또는 유효하지 않음 |
| `403` | 조직의 Gateway API 비활성화, 또는 이 챗봇의 API 접근 스위치가 꺼짐 |
| `404` | 챗봇을 찾을 수 없음(다른 조직 소속 포함), 또는 챗봇에 연결된 모델이 없음 |
| `413` | 요청 본문이 25MB 초과 |
| `429` | 속도 제한 초과 |
| `502` | 업스트림 실패로 응답을 만들지 못함 |
| `503` | 점검으로 서비스 중지 |

게이트웨이 공통 에러 형식과 대처는 [에러 가이드](/docs/api-gateway/reference/errors)를 참고하세요.

---

### 예제

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.baze.co/v1/gateway/chatbots/1234",
)

response = client.chat.completions.create(
    model="ignored",  # 챗봇에 설정된 모델이 사용됩니다
    messages=[{"role": "user", "content": "환불 정책 알려줘"}],
)
print(response.choices[0].message.content)
```

#### curl

```bash
curl -X POST \
  https://api.baze.co/v1/gateway/chatbots/1234/chat/completions/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"환불 정책 알려줘"}]}'
```

#### 스트리밍 (curl)

```bash
curl -N -X POST \
  https://api.baze.co/v1/gateway/chatbots/1234/chat/completions/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"환불 정책 알려줘"}],"stream":true}'
```

---

### 다음 단계

- [API로 챗봇 호출](/docs/baze/product/api-access) — 콘솔에서 API 접근을 켜는 방법
- [Chat Completions API](/docs/api-gateway/reference/chat-completions) — 챗봇 없이 모델을 직접 호출
- [에러 가이드](/docs/api-gateway/reference/errors) — 게이트웨이 공통 에러
