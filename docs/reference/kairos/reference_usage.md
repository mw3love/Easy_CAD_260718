# Usage — 사용량 요약

> API 키 사용량 요약 엔드포인트

API 키로 호출한 Gateway 사용량을 모델별·키별·날짜별로 합산해 돌려줍니다. 앱에서 채팅으로 쓴 크레딧은 들어가지 않습니다.

남은 크레딧은 [`/credits`](/docs/api-gateway/reference/credits), 호출 전에 금액을 알고 싶다면 [`/estimate`](/docs/api-gateway/reference/estimate)를 쓰세요.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/v1/gateway/usage/` | 기간 안의 Gateway 사용량 합계 |

---

### 쿼리 파라미터

from
시작일 (`YYYY-MM-DD`, 한국 시간, 그날 포함). 생략하면 이번 달 1일입니다.

to
종료일 (`YYYY-MM-DD`, 한국 시간, 그날 포함). 생략하면 오늘입니다.

by
묶는 기준. `model`(기본값), `key`, `day` 중 하나입니다.

scope
`key`(기본값)는 이 요청에 쓴 키의 사용량만, `member`는 같은 회원의 모든 키를 합칩니다. 삭제한 키의 사용량도 `member`에 포함됩니다.

`to` 는 `from` 으로부터 최대 **92일** 뒤까지 지정할 수 있습니다(양 끝 날짜 포함이므로 달력상 최대 93일).

---

### 요청

```bash
curl "https://api.baze.co/v1/gateway/usage/?from=2026-09-01&to=2026-09-29&by=model" \
  -H "Authorization: Bearer $YOUR_API_KEY"
```

### 응답

```json
{
  "object": "usage_summary",
  "start_date": "2026-09-01",
  "end_date": "2026-09-29",
  "timezone": "Asia/Seoul",
  "group_by": "model",
  "scope": "key",
  "total": { "call_count": 209, "credits": 1512.96 },
  "rows": [
    { "key": "claude-sonnet-5", "call_count": 20, "credits": 414.07 },
    { "key": "google/gemini-omni-flash/v1.1", "call_count": 1, "credits": 150 },
    { "key": "gemini-3.5-flash", "call_count": 5, "credits": 131.67 }
  ]
}
```

`rows[].key`는 `by`에 따라 달라집니다.

| `by` | `key` 값 |
| --- | --- |
| `model` | 모델 이름. MCP 도구는 `mcp:<묶음>` (예: `mcp:kr-calendar`) |
| `key` | 키 이름과 끝 4자리 (예: `260928-QA (...JQM4)`) |
| `day` | 날짜 (`2026-09-28`) |

`rows`는 크레딧이 많은 순서입니다(`day`는 날짜 순).

---

### 에러

| 상태 | 메시지 | 원인 |
| --- | --- | --- |
| `400` | `The window may not exceed 92 days.` | 기간이 92일을 넘음 |
| `400` | `'from' is after 'to'.` | 시작일이 종료일보다 늦음 |
| `400` | `'from' must be YYYY-MM-DD, …` | 날짜 형식 오류 |
| `400` | `'by' must be one of model, key, day.` | 지원하지 않는 `by` |
| `400` | `'scope' must be 'key' or 'member'.` | 지원하지 않는 `scope` |
