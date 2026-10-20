# 요금과 크레딧 차감

> API Gateway 호출이 크레딧으로 차감되는 방식과 응답의 billing 블록

API Gateway 는 **모델 제공사의 정가(USD)를 기준으로** 원화로 환산해 크레딧을 차감합니다. 환율은 하루 한 번 갱신되며, 카드로 결제한 크레딧에는 결제 수수료가 반영됩니다.

호출 한 건의 원가는 모델 카드(`GET /v1/gateway/models/`)의 `pricing` 단가로 계산하며, 캐시 할인과 검색·도구 사용량이 모두 반영됩니다.

---

### 소수점

차감 크레딧은 **소수 넷째 자리까지 정확히** 차감합니다. 최소 과금은 없고, 무료 모델은 0 입니다. 콘솔의 잔액·사용 내역은 보기 좋게 반올림해 표시하지만, 실제 잔액은 차감값을 그대로 누적합니다.

---

### 응답의 `billing` 블록

크레딧 단가가 등록된 계정의 응답에는 `billing` 블록이 실려, 호출 한 건의 원가와 차감 크레딧을 응답에서 바로 확인할 수 있습니다.

cost_usd
제공사 정가(USD).

exchange_rate
적용 환율(원/USD).

exchange_rate_date
적용 환율의 기준일(`YYYY-MM-DD`).

cost_krw
원화 환산 금액.

vat_included
`cost_krw` 와 `credit_conversion_rate` 에 부가세가 포함돼 있는지.

credit_conversion_rate
귀사의 크레딧 단가(원/cr).

payment_fee_rate
카드 결제 수수료율. 카드로 결제한 크레딧이 아니면 0 입니다.

deducted_credit
이 호출로 차감된 크레딧(소수 넷째 자리).

크레딧 단가가 등록되지 않은 계정에는 `billing` 블록이 오지 않습니다. 잔액은 응답에 싣지 않습니다 — [`/credits`](/docs/api-gateway/reference/credits) 로 조회하세요.

---

### 어디에 실리는가

| 엔드포인트 | 위치 |
|---|---|
| Chat Completions, Messages, Responses, Gemini native (비스트리밍) | 응답 JSON 최상위 `billing` |
| Chat Completions 스트리밍 | `usage` 가 실린 마지막 청크의 `billing` |
| Messages 스트리밍 | `message_delta` 이벤트의 `billing` |
| Responses 스트리밍 | `response.completed` 이벤트의 `response.billing` |
| Gemini native 스트리밍 | `usageMetadata` 가 실린 마지막 청크의 `billing` |
| Embeddings, Rerank, Guard, Decisions, Image, Video, STT | 응답 JSON 최상위 `billing` |
| TTS, Music (바이너리 응답), MCP | `X-Billing` 헤더 (같은 필드의 JSON) |

새 이벤트 타입은 추가되지 않습니다 — 기존 SDK 는 모르는 필드를 무시하므로 그대로 동작합니다.

---

### 오늘 적용되는 값 확인

크레딧 단가가 등록된 계정은 `GET /v1/gateway/models/` 응답 최상위에 오늘 적용되는 `exchange_rate`·`exchange_rate_date`·`credit_conversion_rate`·`vat_included` 가 함께 옵니다.

---

### 다음 단계

- [모델 목록과 단가](/docs/api-gateway/getting-started/models)
- [크레딧 잔액 조회](/docs/api-gateway/reference/credits)
