# Keys — 키 해지

> 지금 쓰는 API 키를 스스로 해지하는 엔드포인트

요청에 쓴 API 키를 바로 해지합니다. CI에 넣어 둔 키가 새었거나 노트북을 잃어버렸을 때, 콘솔에 들어가지 않고도 그 키로 그 키를 끌 수 있습니다.

키는 **자기 자신만** 해지할 수 있습니다. 다른 키는 건드릴 수 없으므로 이 엔드포인트가 새로운 권한을 주지는 않습니다.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/v1/gateway/keys/revoke/` | 이 요청에 쓴 키 해지 |

요청 본문은 없습니다.

---

### 요청

```bash
curl -X POST https://api.baze.co/v1/gateway/keys/revoke/ \
  -H "Authorization: Bearer $YOUR_API_KEY"
```

### 응답

```json
{ "object": "api_key.revoked", "id": 108 }
```

해지는 즉시 적용됩니다. 같은 키로 보내는 다음 요청부터는 `401`입니다.

```json
{
  "detail": {
    "code": 401,
    "message": "authentication_error - This API key has been revoked. Create a new key in the console."
  }
}
```

되돌릴 수 없습니다. 계속 쓰려면 콘솔에서 새 키를 만드세요. 해지한 키로 쓴 사용량은 [`/usage`](/docs/api-gateway/reference/usage)의 `scope=member`에 그대로 남습니다.
