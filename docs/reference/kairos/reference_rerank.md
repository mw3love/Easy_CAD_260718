# Rerank — 검색 결과 재정렬

> 검색 결과 재정렬 엔드포인트

질문 하나와 후보 문서 여러 개를 주면, 질문에 실제로 답이 되는 순서대로 다시 줄을 세워 주는 엔드포인트입니다.

벡터 검색은 빠른 대신 "비슷해 보이는 것"을 가져옵니다. 재정렬은 느린 대신 "정말 맞는 것"을 가려냅니다. 그래서 보통 **임베딩으로 50개쯤 추린 뒤 그중 상위 5개를 재정렬로 고르는** 2단계로 씁니다. RAG 답변 품질이 눈에 띄게 올라가는 지점입니다.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/v1/gateway/rerank/` | 후보 문서 재정렬 |

---

### 모델

| 모델 | 비고 |
| --- | --- |
| `qwen3-rerank` | 현재 제공되는 유일한 재정렬 모델입니다 |

---

### 파라미터

model
`qwen3-rerank`.

query
기준이 되는 질문이나 검색어.

documents
재정렬할 문서 문자열 배열. 최대 **500개**, 문서당 최대 **32,000자**입니다.

top_n
상위 몇 개만 돌려받을지. 생략하면 전부 돌려줍니다.

return_documents
`true`면 결과에 원문(`document.text`)을 같이 실어 줍니다. 기본값은 `false`이며, 이때는 `index`와 점수만 옵니다.

---

### 요청

```bash
curl -X POST https://api.baze.co/v1/gateway/rerank/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-rerank",
    "query": "환불 정책",
    "documents": [
      "환불은 7일 이내 가능합니다.",
      "오늘 날씨는 맑습니다."
    ],
    "top_n": 2
  }'
```

### 응답

```json
{
  "id": "rerank-ca32305c704142a098c24c536a4d9be0",
  "object": "rerank",
  "model": "qwen3-rerank",
  "results": [
    { "index": 0, "relevance_score": 0.6648205475452849 },
    { "index": 1, "relevance_score": 0.20617433908620775 }
  ],
  "usage": { "total_tokens": 59 }
}
```

`index`는 **요청에 넣은 `documents` 배열의 위치**입니다. 결과는 점수 내림차순이므로, 원문을 되찾으려면 이 `index`로 원래 배열을 참조하거나 `return_documents: true`를 쓰세요.

`relevance_score`는 0에 가까울수록 무관, 1에 가까울수록 관련이 높다는 뜻입니다. 절대적인 기준값은 없으므로, 실제 데이터로 잘라낼 지점을 정하는 편이 좋습니다.

---

### 임베딩과 함께 쓰는 예

```python
from openai import OpenAI
import httpx

BASE = "https://api.baze.co/v1/gateway"
KEY = "YOUR_API_KEY"

# 1단계: 임베딩으로 후보를 넓게 추린다 (내 벡터 DB에서)
candidates = my_vector_search(query, top_k=50)

# 2단계: 재정렬로 상위 5개만 고른다
res = httpx.post(
    f"{BASE}/rerank/",
    headers={"Authorization": f"Bearer {KEY}"},
    json={
        "model": "qwen3-rerank",
        "query": query,
        "documents": [c.text for c in candidates],
        "top_n": 5,
    },
    timeout=60,
).json()

best = [candidates[r["index"]] for r in res["results"]]
```

---

### 알아 두면 좋은 것

- **과금은 토큰 기준**입니다. `query`와 모든 `documents`를 합쳐서 셉니다. 후보를 500개 넣으면 500개어치를 냅니다 — `top_n`을 줄여도 비용은 줄지 않습니다. 비용을 줄이려면 1단계에서 후보 수를 줄이세요.
- **조직에서 개인정보 필터를 켠 경우** `query`와 모든 문서가 검사 대상이며, 검사에도 요금이 붙습니다. 후보가 많을수록 느려지고 비싸집니다.
- 재정렬 모델을 `/v1/gateway/chat/completions/`에 보내면 `400`과 함께 올바른 경로를 안내합니다.
