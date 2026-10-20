# Gemini API

> Gemini 네이티브 API 패스스루

Google Gemini의 네이티브 요청 형식을 그대로 받는 엔드포인트입니다. OpenAI 호환 형식으로 바꾸지 않고, Google SDK나 Gemini CLI가 보내는 본문을 그대로 보냅니다.

OpenAI 호환 경로(`/chat/completions/`)로도 Gemini 모델을 쓸 수 있지만, **네이티브 경로에서만 되는 것**이 있습니다. 검색 기반 응답(`google_search`), 안전 설정, 그리고 **`thoughtSignature` 보존**입니다. 마지막 항목은 도구를 연달아 호출하는 에이전트에서 특히 중요합니다 — 이 값이 유실되면 두 번째 도구 호출부터 실패합니다.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/v1/gateway/gemini/v1beta/models` | 사용 가능한 Gemini 모델 목록 |
| POST | `/v1/gateway/gemini/v1beta/models/{model}:generateContent` | 응답 생성 |
| POST | `/v1/gateway/gemini/v1beta/models/{model}:streamGenerateContent` | 스트리밍 응답 생성 |
| POST | `/v1/gateway/gemini/v1beta/models/{model}:countTokens` | 토큰 수 계산 (무료) |

---

### 인증

Gemini SDK와 CLI가 쓰는 헤더를 그대로 받습니다. 둘 다 동작합니다.

```bash
-H "x-goog-api-key: $YOUR_API_KEY"
# 또는
-H "Authorization: Bearer $YOUR_API_KEY"
```

  키는 KAIROS Chat API 키입니다. Google AI Studio 키가 아닙니다.

---

### 요청

```bash
curl -X POST https://api.baze.co/v1/gateway/gemini/v1beta/models/gemini-3.5-flash:generateContent \
  -H "x-goog-api-key: $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      { "role": "user", "parts": [{ "text": "게이트웨이를 한 문장으로 설명해 줘" }] }
    ]
  }'
```

### 응답

```json
{
  "candidates": [
    {
      "content": {
        "parts": [{ "text": "하나의 API 키로 여러 제공사의 모델을 호출하도록 중계하는 서비스입니다." }],
        "role": "model"
      },
      "index": 0
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 7,
    "candidatesTokenCount": 7,
    "totalTokenCount": 202,
    "thoughtsTokenCount": 188
  }
}
```

`thoughtsTokenCount`는 모델이 내부적으로 생각하는 데 쓴 토큰입니다. **출력 토큰 단가로 과금됩니다.** 위 예시에서 실제 답변은 7토큰이지만 전체는 202토큰입니다 — 사고 과정이 비용의 대부분을 차지할 수 있다는 뜻입니다.

---

### 웹 검색 (google_search)

`tools`에 `google_search`를 넣으면 모델이 검색해서 답합니다.

```bash
curl -X POST https://api.baze.co/v1/gateway/gemini/v1beta/models/gemini-3.5-flash:generateContent \
  -H "x-goog-api-key: $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      { "role": "user", "parts": [{ "text": "현재 코스피 지수 알려줘" }] }
    ],
    "tools": [{ "google_search": {} }]
  }'
```

응답에 `groundingMetadata`가 함께 오며, 여기에 실제로 사용한 검색어(`webSearchQueries`)와 출처(`groundingChunks`)가 담깁니다. 검색은 별도로 과금됩니다.

---

### 스트리밍

`:streamGenerateContent`에 `?alt=sse`를 붙이면 SSE로 받습니다.

```bash
curl -X POST "https://api.baze.co/v1/gateway/gemini/v1beta/models/gemini-3.5-flash:streamGenerateContent?alt=sse" \
  -H "x-goog-api-key: $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"role":"user","parts":[{"text":"1부터 3까지 세어 줘"}]}]}'
```

---

### 토큰 계산은 무료입니다

`:countTokens`는 모델을 호출하지 않으므로 크레딧이 차감되지 않습니다. 긴 프롬프트를 보내기 전에 비용을 가늠할 때 쓰세요.

```json
{ "totalTokens": 7, "promptTokensDetails": [{ "modality": "TEXT", "tokenCount": 7 }] }
```

---

### Gemini CLI 연동

이 경로는 Gemini CLI가 기대하는 형식과 같으므로, 베이스 URL만 바꾸면 그대로 붙습니다.

```bash
export GEMINI_API_KEY=YOUR_API_KEY
export GOOGLE_GEMINI_BASE_URL=https://api.baze.co/v1/gateway/gemini

gemini -m gemini-3.5-flash -p "이 저장소에서 TODO를 찾아 줘"
```

  `GOOGLE_GEMINI_BASE_URL`에 `/v1beta`까지 넣지 마세요. CLI가 뒤에 경로를 스스로 붙이므로 `.../v1beta/v1beta/...`가 되어 404가 납니다.

자세한 설정은 [Gemini CLI 연동 가이드](/docs/gateway/integrations/gemini-cli)를 참고하세요.

---

### 알아 두면 좋은 것

- 목록에 나오는 모델만 호출할 수 있습니다. 조직에서 허용하지 않은 모델은 `403`입니다.
- 이 경로는 Gemini 모델 전용입니다. 다른 제공사 모델은 `/chat/completions/`를 쓰세요.
- 과금은 OpenAI 호환 경로와 동일합니다 — 입력·출력 토큰 기준이며, 사고 토큰은 출력 단가로 계산합니다.
