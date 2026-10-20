# Estimate API

> 이미지·비디오·음악 생성 요청이 몇 크레딧인지 호출 전에 확인하는 엔드포인트

이미지·비디오·음악 생성 요청을 **보내기 전에** 몇 크레딧이 차감될지 알려 줍니다.

견적은 실제 차감과 같은 계산으로 나옵니다 — 같은 모델 단가, 같은 조직 단가, 같은 환산식을 씁니다. 견적 호출 자체는 무료이며, 크레딧을 예약하거나 무언가를 생성·저장하지 않습니다.

---

### 견적 요청

POST

생성 엔드포인트에 보낼 본문에 `kind` 하나만 더해 보내면 됩니다. `prompt` 는 필요 없습니다.

---

### 요청 헤더

```http
POST https://api.baze.co/v1/gateway/estimate/
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

---

### 파라미터

kind
어떤 생성 요청의 견적인지. `image`, `video`, `music` 중 하나.

model
생성에 쓸 모델 ID. 생성 엔드포인트와 같은 값입니다.

`kind` 별로 생성 엔드포인트의 파라미터를 그대로 받습니다.

| `kind` | 생성 엔드포인트 | 견적에 반영되는 파라미터 |
|---|---|---|
| `image` | [`POST /images/generate/`](/docs/api-gateway/reference/image-generation) | `number_of_images`, 크기·품질 등 모델 파라미터 |
| `video` | [`POST /video/generation/`](/docs/api-gateway/reference/video-generation) | `parameters` (`duration`, `resolution` 등) |
| `music` | [`POST /audio/music/`](/docs/api-gateway/reference/audio-music) | `duration_seconds` |

생략한 파라미터는 생성 요청과 똑같이 모델 기본값으로 계산합니다.

---

### 응답

object
항상 `"estimate"`.

kind
요청한 `kind`.

model
견적을 낸 모델 ID.

credits
예상 차감 크레딧(`lines` 합계, 소수 넷째 자리).

exact
`bound` 가 `"exact"` 이면 `true`.

bound
실제 차감액이 견적과 어떤 관계인지.

| 값 | 뜻 | 언제 |
|---|---|---|
| `exact` | 견적 그대로 차감 | 대부분의 모델 |
| `minimum` | 견적 이상 | 생성 토큰으로 과금되는 이미지 모델(`gpt-image-*`, `gemini-*-image*`) — 제공사 원가가 건당 단가를 넘으면 그만큼 더 차감 |
| `maximum` | 견적 이하 | 길이를 엔진이 정하는 효과음 — `duration_seconds` 를 주면 `exact` |
| `approximate` | 위아래 모두 가능 | `note` 에 적힌 이유로 실제 차감액이 견적과 달라질 수 있을 때 |

lines
견적 항목. 보통 생성 한 줄이고, 조직이 프롬프트 검사(마스킹)를 켜 두었다면 그 요금이 한 줄 더 붙습니다.

item
`image`, `video`, `music`, `content_filter` 중 하나.

credits
이 항목의 크레딧.

exact
이 항목이 정확한 값인지.

bound
위 표와 같은 값.

basis
단가 방식. 예: `fixed`(건당), `price_schema`(해상도·길이별), `per_second`, `per_generation`, `per_request`. 이 밖에 두 가지가 더 있습니다.

- `actual_cost` — 이 설정의 제공사 원가가 모델의 장당 단가보다 높아서, 원가 기준으로 매긴 이미지.
- `fixed_fallback` — 해상도·길이로 가격을 계산할 수 없는 비디오 모델. 길이·해상도와 상관없이 편당 고정 단가로 견적하고 차감합니다.

note
견적과 실제 차감액이 달라질 수 있는 이유, 또는 그 항목의 설명. `exact` 항목에는 보통 없지만 붙을 때도 있습니다 — `content_filter` 항목에는 항상 있습니다.

---

### 응답 예시

비디오 — 정확한 견적:

```json
{
  "object": "estimate",
  "kind": "video",
  "model": "bytedance/seedance-1.0-pro/fast",
  "credits": 31.6442,
  "exact": true,
  "bound": "exact",
  "lines": [
    { "item": "video", "credits": 31.6442, "exact": true, "bound": "exact", "basis": "price_schema" }
  ]
}
```

토큰으로 과금되는 이미지 모델 — 최소값:

```json
{
  "object": "estimate",
  "kind": "image",
  "model": "gemini-3.1-flash-image-preview",
  "credits": 50.0906,
  "exact": false,
  "bound": "minimum",
  "lines": [
    {
      "item": "image",
      "credits": 50.0906,
      "exact": false,
      "bound": "minimum",
      "basis": "fixed",
      "note": "Minimum: this model is priced by the tokens it generates, and the charge rises above this when the provider's cost does."
    }
  ]
}
```

길이를 정하지 않은 효과음 — 최대값:

```json
{
  "object": "estimate",
  "kind": "music",
  "model": "elevenlabs-sfx",
  "credits": 130.671,
  "exact": false,
  "bound": "maximum",
  "lines": [
    {
      "item": "music",
      "credits": 130.671,
      "exact": false,
      "bound": "maximum",
      "basis": "per_second",
      "note": "Maximum: the engine picks the length (up to 30s) and the charge is for the length it returns. Set duration_seconds for an exact price."
    }
  ]
}
```

위 숫자는 예시입니다. 실제 금액은 계정과 모델 단가에 따라 다릅니다.

---

### 에러

| 상태 | 원인 |
|---|---|
| `400` | `kind` 가 `image`·`video`·`music` 이 아님, `model` 누락, 음악 모델이 아닌 오디오 모델, 잘못된 파라미터 |
| `400` | `Model 'X' has no price to quote.` — 가격이 설정되지 않은 음악 모델 |
| `400` | `Model 'X' edits an existing image only. Pass 'input_images' with at least one image URL.` — 편집 전용 이미지 모델을 `input_images` 없이 견적 |
| `403` | 조직에서 활성화되지 않은 모델 |
| `403` | `Model 'X' is not available to you (blocked for your group or organization). Contact your administrator.` — 내 그룹에서 막힌 모델 |
| `404` | 없는 모델 ID — 메시지에 사용 가능한 모델 목록이 옵니다 |

이미지는 견적도 생성 요청과 같은 모델 검사를 거칩니다(`number_of_images` 최대값 포함). 비디오 견적은 모델 기본 파라미터만 채울 뿐 `input_urls`나 참조 이미지는 검사하지 않으므로, 견적이 통과한 요청도 생성 단계에서 거절될 수 있습니다.

---

### 코드 예제

#### curl

```bash
curl https://api.baze.co/v1/gateway/estimate/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "kind": "video",
    "model": "bytedance/seedance-1.0-pro/fast",
    "parameters": { "resolution": "480p", "duration": 5 }
  }'
```

#### Python

```python
import requests

API = "https://api.baze.co/v1/gateway"
HEADERS = {"Authorization": "Bearer YOUR_API_KEY"}

body = {"model": "fal-ai/flux-pro/v1.1", "number_of_images": 2}

quote = requests.post(f"{API}/estimate/", headers=HEADERS, json={"kind": "image", **body}).json()
print(quote["credits"], quote["bound"])

if quote["credits"] <= 100:
    requests.post(f"{API}/images/generate/", headers=HEADERS, json={"prompt": "a lighthouse at dawn", **body})
```

---

### 실제 차감액 확인

생성 응답에도 실제로 차감된 크레딧이 실립니다 — 이미지·비디오는 응답의 `credits_charged`, 음악은 `X-Credits-Charged` 헤더입니다. 생성 항목이 `exact` 였다면 이 값과 같습니다. `content_filter` 항목(조직이 프롬프트를 검사할 때)은 별도 사용 내역으로 차감되므로 `credits_charged`·`X-Credits-Charged`에는 포함되지 않습니다.

---

### 다음 단계

- [크레딧 잔액 조회](/docs/api-gateway/reference/credits)
- [이미지 생성](/docs/api-gateway/reference/image-generation) · [비디오 생성](/docs/api-gateway/reference/video-generation) · [음악 생성](/docs/api-gateway/reference/audio-music)
