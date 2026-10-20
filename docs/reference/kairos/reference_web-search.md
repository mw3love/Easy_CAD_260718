# Web Search — Exa 웹 검색

> Exa 웹 검색 · 페이지 본문 · 출처가 달린 답변

API 키 하나로 웹을 검색하고, 페이지 본문을 읽고, 출처가 달린 답변을 받는 엔드포인트입니다.

게이트웨이는 [Exa](https://exa.ai/docs) API를 **그대로** 중계합니다. 요청 본문은 Exa로 그대로 전달되고 Exa의 JSON 응답도 그대로 돌아오므로, Exa 공식 문서와 SDK를 기본 URL만 바꿔서 쓸 수 있습니다. Exa 계정이나 Exa API 키는 필요 없습니다 — 게이트웨이 API 키로 호출하고 크레딧으로 과금됩니다.

---

### 엔드포인트

기본 URL: `https://api.baze.co/v1/gateway/exa`

| Method | Path                        | 설명                                                               | Exa 레퍼런스                                           |
| ------ | --------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------ |
| POST   | `/v1/gateway/exa/search/`   | 웹 검색. `contents`로 본문·하이라이트·요약을 함께 받을 수 있습니다 | [Search](https://exa.ai/docs/reference/search)         |
| POST   | `/v1/gateway/exa/contents/` | 알고 있는 URL의 본문·하이라이트·요약                               | [Contents](https://exa.ai/docs/reference/get-contents) |
| POST   | `/v1/gateway/exa/answer/`   | 검색 결과를 근거로 한 답변과 출처                                  | [Answer](https://exa.ai/docs/reference/answer)         |

끝에 `/`가 없는 경로(`…/exa/search`)도 같은 엔드포인트로 받습니다. Exa SDK가 그렇게 호출하기 때문입니다.

  **인증 헤더는 둘 다 됩니다.** `Authorization: Bearer $YOUR_API_KEY` 또는 Exa
  SDK가 쓰는 `x-api-key: $YOUR_API_KEY`. 어느 쪽이든 값은 게이트웨이 API
  키입니다.

---

### 요청

```bash
curl -X POST https://api.baze.co/v1/gateway/exa/search/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "FastAPI release notes",
    "numResults": 2,
    "contents": { "highlights": { "maxCharacters": 200 } }
  }'
```

### 응답

```json
{
  "requestId": "8a736e09c18f16770e36308b0f593581",
  "results": [
    {
      "id": "https://fastapi.tiangolo.com/release-notes/",
      "title": "Release Notes - FastAPI",
      "url": "https://fastapi.tiangolo.com/release-notes/",
      "highlights": ["Release Notes - FastAPI ... ## 0.142.2 (2026-09-30) ..."]
    },
    {
      "id": "https://github.com/fastapi/fastapi/releases",
      "title": "Releases · fastapi/fastapi",
      "url": "https://github.com/fastapi/fastapi/releases",
      "highlights": ["## 0.142.2 ... 30 Sep ... ### Fixes ..."]
    }
  ],
  "searchTime": 727.3,
  "costDollars": { "total": 0.007, "search": { "neural": 0.007 } }
}
```

응답 본문은 Exa가 보낸 그대로입니다. 차감된 크레딧은 본문이 아니라 응답 헤더로 알려 드립니다([과금](#과금) 참고).

---

### Exa SDK로 호출하기

`base_url`만 게이트웨이로 바꾸면 Exa SDK가 그대로 동작합니다.

```python
from exa_py import Exa

exa = Exa(
    api_key=YOUR_API_KEY,  # Exa 키가 아니라 게이트웨이 API 키
    base_url="https://api.baze.co/v1/gateway/exa",
)

# exa-py는 snake_case 인자를 camelCase로 바꿔 보냅니다 (num_results → numResults, max_characters → maxCharacters)
results = exa.search("FastAPI release notes", num_results=5, contents={"highlights": True})
page = exa.get_contents(["https://fastapi.tiangolo.com/release-notes/"], text={"max_characters": 2000})
answer = exa.answer("호주의 수도는 어디인가요?")
```

```ts
import Exa from 'exa-js';

const exa = new Exa(
  YOUR_API_KEY,
  'https://api.baze.co/v1/gateway/exa',
);
const results = await exa.search('FastAPI release notes', { numResults: 5 });
```

---

### 파라미터

Exa가 문서화한 필드는 모두 받습니다. 아래는 자주 쓰는 것과 게이트웨이가 직접 확인하는 것입니다. 전체 목록은 각 Exa 레퍼런스를 보세요.

#### `/search`

query
검색어. 빈 문자열이면 `400`입니다.

type
`auto`(기본값), `fast`, `instant`, `deep-lite`, `deep`, `deep-reasoning`.
종류마다 가격과 속도가 다릅니다([과금](#과금)).

numResults
결과 수. **1–100**, 기본값 10. 10개를 넘는 결과는 추가 과금됩니다.

category
`company`, `publication`, `news`, `personal site`, `financial report`, `people`
중 하나로 결과를 좁힙니다.

includeDomains · excludeDomains
포함하거나 뺄 도메인 목록.

startPublishedDate · endPublishedDate
게시일 범위(ISO 8601). 예: `"2026-09-01"`.

contents
결과마다 함께 받을 내용. `text`(본문), `highlights`(관련 구절), `summary`(요약),
`subpages`(하위 페이지 수), `extras` 등. `text`와 `highlights`는 검색 가격에
포함되고, `summary`는 페이지당 추가 과금됩니다.

#### `/contents`

urls
본문을 가져올 URL. 최대 **100개**. 검색 결과의 `id`를 `ids`로 보내도 됩니다.

text · highlights · summary
가져올 내용의 종류. 종류마다 페이지당 과금됩니다.

#### `/answer`

query
질문.

systemPrompt
답변 방식에 대한 추가 지시.

outputSchema
답변을 JSON 구조로 받고 싶을 때 쓰는 JSON Schema.

  **스트리밍은 지원하지 않습니다.** `/search`·`/answer`에 `"stream": true`를
  보내면 `400`입니다. JSON 응답을 한 번에 받아 주세요.

---

### 과금

호출마다 **Exa가 응답에 적어 보내는 실제 비용**(`costDollars.total`)을 기준으로, 다른 게이트웨이 호출과 같은 방식으로 크레딧으로 바꿔 차감합니다. 참고용 Exa 공시 가격(2026-10 기준, [Exa Pricing](https://exa.ai/pricing)):

| 호출                                      | Exa 공시 가격                 |
| ----------------------------------------- | ----------------------------- |
| `/search` `instant` (결과 10개까지)       | $4 / 1천 건                   |
| `/search` `fast` · `auto` (결과 10개까지) | $7 / 1천 건                   |
| `/search` `deep-lite` · `deep`            | $12 / 1천 건                  |
| `/search` `deep-reasoning`                | $15 / 1천 건                  |
| 10개를 넘는 결과                          | $1 / 1천 결과                 |
| 요약(`summary`)                           | $1 / 1천 페이지               |
| `/contents`                               | 내용 종류마다 $1 / 1천 페이지 |
| `/answer`                                 | $5 / 1천 건                   |

차감 내역은 **응답 헤더**에 있습니다. 응답 본문은 Exa가 보낸 그대로 두기 위해서입니다.

| 헤더                | 내용                                                                                           |
| ------------------- | ---------------------------------------------------------------------------------------------- |
| `X-Credits-Charged` | 이번 호출에서 차감된 크레딧                                                                    |
| `X-Billing`         | 원화 과금 조직에서만: 환산 내역(`cost_usd`, `exchange_rate`, `cost_krw`, `deducted_credit` 등) |

- Exa가 요청 자체를 거절한 경우(`400`)는 과금하지 않습니다.
- `/contents`에서 URL을 하나도 가져오지 못한 경우에도 Exa가 보고한 비용(`costDollars.total`)만 차감됩니다.
- 호출 전에 예상 최대 비용만큼 크레딧을 잠시 잡아 두었다가, 실제 비용으로 정산한 뒤 나머지를 돌려 놓습니다. 크레딧이 부족하면 Exa를 호출하지 않고 `402`를 돌려줍니다.
- 사용 내역에는 **Mindlogic Websearch**로 기록됩니다.

---

### 한도

- 웹 검색 용량은 KAIROS Chat 앱 안의 웹 검색과 함께 씁니다. 그래서 **조직당 초당 5건**(그리고 전체 API 고객 합산 상한)으로 제한합니다. 넘으면 `429`와 `Retry-After: 1`이 옵니다.
- 게이트웨이 공통 한도(멤버당 분당 120건)도 함께 적용됩니다.
- `numResults` 1–100, `/contents` URL 최대 100개 (Exa 한도).

---

### 데이터 처리

- 검색어와 요청 본문은 Exa(미국)로 전송됩니다. Exa의 데이터 처리 방침은 [Exa 보안 문서](https://exa.ai/docs/reference/security)를 참고하세요.
- 조직에 콘텐츠 필터가 켜져 있으면 Exa로 보내기 전에 자유 텍스트 필드(`query`, `additionalQueries`, `systemPrompt`, `objective`, `highlights.query`, `summary.query`, `subpageTarget`)에 같은 필터를 적용합니다.
- 게이트웨이는 요청·응답 본문을 저장하지 않습니다. 사용 내역에는 호출 사실, 엔드포인트, Exa 요청 ID, 비용만 남습니다.

---

### 지원하지 않는 것

- `stream: true` (`/search`, `/answer`)
- `/findSimilar` — Exa에서 지원을 중단했습니다. 대신 그 페이지를 설명하는 검색어로 `/search`를 쓰세요.
- Exa의 Agent, Websets, Monitors, Research, OpenAI 호환 `/chat/completions`

---

### 에러

| 상태  | 언제                                                                                                                      |
| ----- | ------------------------------------------------------------------------------------------------------------------------- |
| `400` | 게이트웨이 검사 실패: 잘못된 JSON, `query` 없음, `numResults` 범위 밖, `urls` 없음, `stream: true` — 게이트웨이 에러 형식 |
| `400` | Exa가 필드를 거절함 — **Exa 에러 본문 그대로**(`requestId`, `error`, `tag`). 과금하지 않습니다                            |
| `401` | API 키가 없거나 잘못됨                                                                                                    |
| `402` | 남은 크레딧이 없음                                                                                                        |
| `429` | 조직의 초당 한도 초과, 또는 Exa 쪽 속도 제한 (`Retry-After` 참고)                                                         |
| `502` | Exa에 연결할 수 없거나 Exa 쪽 오류 — 잠시 뒤 다시 시도하세요                                                              |
| `503` | 이 환경에 웹 검색이 설정되어 있지 않음                                                                                    |

Exa가 돌려준 `400`의 예:

```json
{
  "requestId": "fab94f81a40c01772ab716e8a1b8585e",
  "error": "Invalid request body | Validation error: Invalid option: expected one of ... at \"type\"",
  "tag": "INVALID_REQUEST_BODY"
}
```

게이트웨이 에러 형식은 [에러 코드](/docs/api-gateway/reference/errors)를 보세요.

---

### 참고 링크

- [Exa 문서](https://exa.ai/docs) · [Search](https://exa.ai/docs/reference/search) · [Contents](https://exa.ai/docs/reference/get-contents) · [Answer](https://exa.ai/docs/reference/answer)
- [Exa Python SDK (`exa-py`)](https://github.com/exa-labs/exa-py) · [Exa JS SDK (`exa-js`)](https://github.com/exa-labs/exa-js)
- [Exa 가격](https://exa.ai/pricing) · [Exa 속도 제한](https://exa.ai/docs/reference/rate-limits)
- [웹 검색과 코드 실행](/docs/api-gateway/reference/server-tools) — 채팅 호출 안에서 모델이 직접 검색하는 제공사 웹 검색입니다. 이 페이지는 검색·본문·답변을 따로 호출하는 독립 API입니다.
