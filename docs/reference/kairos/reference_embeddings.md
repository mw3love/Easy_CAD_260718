# Embeddings

> 텍스트·이미지 임베딩 엔드포인트

텍스트나 이미지를 벡터로 바꾸는 엔드포인트입니다. 검색, 추천, 분류, 중복 판정처럼 의미가 얼마나 가까운지를 다루는 기능의 재료가 됩니다.

요청·응답 형식은 OpenAI Embeddings API와 같아서, 기존 코드의 `base_url`만 바꾸면 그대로 동작합니다.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/v1/gateway/embeddings/` | 임베딩 생성 |

---

### 모델

| 모델 | 차원 | 이미지 | 비고 |
| --- | --- | --- | --- |
| `text-embedding-3-small` | 1536 | — | 가장 저렴합니다 |
| `text-embedding-3-large` | 3072 | — | |
| `gemini-embedding-2` | 3072 | 지원 | 이미지 1장을 크기와 무관하게 258토큰으로 셉니다 |
| `text-embedding-v4` | 1024 | — | |
| `qwen3.7-text-embedding` | 1024 | — | |
| `tongyi-embedding-vision-plus` | 1152 | 지원 | 이미지 토큰을 실제 크기대로 셉니다 |

`dimensions`로 줄일 수 있는 모델이 있으므로, 표의 차원은 기본값입니다.

  임베딩 모델을 `/v1/gateway/chat/completions/`에 보내면 400과 함께 올바른 경로를 안내합니다. 반대로 대화 모델을 이 엔드포인트에 보내도 마찬가지입니다.

---

### 파라미터

model
위 표의 모델 이름.

input
임베딩할 대상. 문자열 하나, 문자열 배열, 또는 이미지 객체 배열을 받습니다. 배열 순서는 응답의 `index`로 그대로 보존됩니다.

이미지는 `image_url` 객체로 넘깁니다. `url`은 **base64 데이터 URL**이어야 하며, 외부 링크는 받지 않습니다.

```json
{ "type": "image_url", "image_url": { "url": "data:image/png;base64,iVBORw0KG..." } }
```

dimensions
반환할 벡터 차원. 모델이 지원하는 경우에만 유효합니다. 예를 들어 `text-embedding-3-small`에 `256`을 주면 256차원이 돌아옵니다.

encoding_format
`float`(기본값) 또는 `base64`. `base64`를 주면 `embedding`이 숫자 배열이 아니라 문자열로 돌아옵니다. 전송량이 줄어 대량 처리에 유리합니다.

task_type
Gemini 임베딩 모델 전용. `RETRIEVAL_DOCUMENT`, `RETRIEVAL_QUERY` 등 용도를 알려 주면 그에 맞게 벡터를 만듭니다.

---

### 요청

#### 텍스트

```bash
curl -X POST https://api.baze.co/v1/gateway/embeddings/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "text-embedding-3-small",
    "input": ["게이트웨이 임베딩 점검", "second item"]
  }'
```

#### 이미지

```bash
curl -X POST https://api.baze.co/v1/gateway/embeddings/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tongyi-embedding-vision-plus",
    "input": [
      { "type": "image_url", "image_url": { "url": "data:image/png;base64,iVBORw0KG..." } }
    ]
  }'
```

### 응답

```json
{
  "object": "list",
  "data": [
    { "object": "embedding", "index": 0, "embedding": [-0.01203918, 0.02644348, "..."] },
    { "object": "embedding", "index": 1, "embedding": [0.00780105, 0.00629425, "..."] }
  ],
  "model": "text-embedding-3-small",
  "usage": { "prompt_tokens": 18, "total_tokens": 18 }
}
```

이미지를 넣으면 `usage`에 `image_tokens`가 함께 옵니다.

```json
"usage": { "prompt_tokens": 66, "total_tokens": 66, "image_tokens": 66 }
```

---

### OpenAI SDK로 호출하기

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY",
    base_url="https://api.baze.co/v1/gateway",
)

result = client.embeddings.create(
    model="text-embedding-3-small",
    input=["첫 번째 문장", "두 번째 문장"],
)
print(len(result.data[0].embedding))  # 1536
```

---

### 알아 두면 좋은 것

- **배열 크기 제한은 신경 쓰지 않아도 됩니다.** 일부 제공자는 한 번에 받는 개수가 10~20개로 제한되지만, 게이트웨이가 알아서 나눠 호출하고 순서를 맞춰 돌려줍니다.
- **과금은 입력 토큰 기준**입니다. 이미지 토큰도 같은 사용 내역에 합산됩니다.
- **조직에서 개인정보 필터를 켠 경우** `input`의 모든 문자열이 검사 대상입니다. 검사 자체에도 요금이 붙으므로, 대량 색인 작업 전에 관리자와 설정을 확인해 보세요.
- 이 엔드포인트는 문서 변환(OCR)을 하지 않습니다. 이미지는 그대로 제공자 모델에 전달됩니다.
