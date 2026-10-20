# MCP — 도구 묶음

> MCP 도구 묶음을 API 키로 호출하는 엔드포인트

공휴일·법령·공시·논문 검색처럼 KAIROS Chat 가 운영하는 MCP 도구 묶음(suite)을 API 키 하나로 씁니다. 어떤 MCP 클라이언트든 묶음 주소와 키만 넣으면 연결됩니다.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/v1/gateway/mcp/` | 이 키로 쓸 수 있는 묶음 목록 |
| POST | `/v1/gateway/mcp/{suite}/` | 묶음 하나에 MCP JSON-RPC 요청 |

---

### 묶음 목록

```bash
curl https://api.baze.co/v1/gateway/mcp/ \
  -H "Authorization: Bearer $YOUR_API_KEY"
```

```json
{
  "object": "list",
  "data": [
    {
      "slug": "kr-calendar",
      "display_name": "Korea Calendar & Almanac",
      "description": "Korean public holidays, lunar/solar date conversion, and sunrise/sunset and moon times from 한국천문연구원 (KASI).",
      "url": "/v1/gateway/mcp/kr-calendar/",
      "transport": "streamable-http"
    }
  ]
}
```

커넥터 설정에서 조직 단위나 내 그룹 단위로 막은 묶음은 목록에 나오지 않습니다.

---

### MCP 클라이언트에서 연결

`url`에 호스트를 붙인 주소가 MCP 서버 주소입니다. 인증은 다른 Gateway 엔드포인트와 같은 `Authorization: Bearer` 헤더입니다. Claude Code 의 `.mcp.json` 예:

```json
{
  "mcpServers": {
    "kr-calendar": {
      "type": "http",
      "url": "https://api.baze.co/v1/gateway/mcp/kr-calendar/",
      "headers": { "Authorization": "Bearer ${FACTCHAT_API_KEY}" }
    }
  }
}
```

전송 방식은 **상태 없는 streamable HTTP** 입니다. `POST`만 받고, `GET`·`DELETE` 는 `405`입니다. 세션 ID 도 쓰지 않습니다.

---

### 직접 호출

요청은 MCP JSON-RPC 그대로입니다. `Accept` 헤더를 보낸다면 `application/json` 과 `text/event-stream` 을 **둘 다** 넣어야 하며, 하나라도 빠지면 `406`입니다. 헤더를 보내지 않으면 게이트웨이가 두 가지를 대신 채워 보냅니다. 응답은 SSE(`event: message`) 한 건으로 옵니다.

```bash
curl -X POST https://api.baze.co/v1/gateway/mcp/kr-calendar/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
       "params": {"name": "get_holidays", "arguments": {"year": 2026, "month": 10}}}'
```

```text
event: message
data: {"result":{"content":[{"type":"text","text":"{\n  \"year\": 2026,\n  \"month\": 10,\n  \"count\": 3,\n  \"items\": [ … ] }"}]},"jsonrpc":"2.0","id":1}
```

도구 목록과 각 도구의 인자는 `tools/list` 로 먼저 확인하세요. `initialize`·`tools/list`·`ping` 은 과금되지 않습니다.

---

### 과금과 한도

- **`tools/call` 한 번이 1건**입니다. 도구가 실행되면(`2xx`) 결과가 JSON-RPC 에러여도 1건으로 셉니다. 묶음이 요청을 거절하면(`4xx`) 과금되지 않습니다. 현재 단가는 0 크레딧이며, 사용량은 [`/usage`](/docs/api-gateway/reference/usage)에 `mcp:<묶음>` 으로 남습니다.
- `tools/call` 에는 게이트웨이 공통 속도 제한과 별도로 한도가 있습니다.

| 기준 | 한도 |
| --- | --- |
| API 키 | 분당 30건, 하루 200건 |
| 조직 | 하루 1,000건 |
| 묶음 | 분당 60건, 하루 300건 기본 (공공 데이터 쿼터에 따라 묶음마다 다름) |

한도를 넘으면 `429`와 `Retry-After` 헤더가 옵니다.

---

### 에러

| 상태 | 메시지 | 원인 |
| --- | --- | --- |
| `400` | `Invalid JSON-RPC request: …` | JSON-RPC 형식이 아님 |
| `403` | `MCP suite 'X' is disabled by your organization's connector settings` | 조직이나 내 그룹에서 이 묶음을 막음 |
| `404` | `Unknown MCP suite 'X'. See GET /v1/gateway/mcp/` | 없는 묶음 |
| `404` | `MCP suite 'X' is not available through the API. See GET /v1/gateway/mcp/` | 앱에서만 쓸 수 있는 묶음 |
| `405` | `Use POST; this endpoint is stateless streamable-HTTP` | `GET`·`DELETE` 요청 |
| `406` | `Not Acceptable: Client must accept both application/json and text/event-stream` | `Accept` 헤더에 두 형식 중 하나만 있음 |
| `429` | `Rate limit exceeded: …` | 위 한도 초과 |
| `502` | `MCP suite 'X' did not respond. Try again shortly` | 묶음이 응답하지 않았거나 실패함. 잠시 후 다시 시도 |
| `503` | `MCP suite 'X' is paused after repeated upstream failures. Retry in N seconds` | 묶음이 연달아 실패해 잠시 멈춤 (`Retry-After` 참고) |
