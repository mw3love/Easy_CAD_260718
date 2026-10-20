# Decisions — 판정 모델

> 글 하나에 여러 질문을 던져 확률로 판정받는 엔드포인트 (Jev · OpenAI)

판정할 내용(`state`) 하나와 질문 여러 개를 보내면, 질문마다 **확률로 된 답**을 돌려줍니다. 자유로운 문장을 쓰는 채팅 모델이 아니라 분류·채점 전용 모델입니다. TypeSafe Jev와 OpenAI 판정 모델 두 가지를 같은 엔드포인트로 제공합니다.

"이 문의가 환불 요청인가?", "어느 부서로 보낼까?", "얼마나 급한가?" 같은 판단을 한 번의 호출로, 파싱할 필요 없는 구조로 받습니다.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/v1/gateway/decisions/` | `state` 에 대한 질문들을 판정 |

---

### 모델

| 모델 | 비고 |
| --- | --- |
| `jev-latest` | 현재 제공되는 판정 모델. `jev-1.13` 도 같은 모델로 연결됩니다 |
| `gpt-6-luna-decisions` | OpenAI 판정 모델(GPT-6 Luna 기반). 텍스트와 이미지를 함께 판정할 수 있습니다. 요청 형식이 Jev와 다릅니다 — [아래](#openai-판정-모델--gpt-6-luna-decisions) |

조직에서 켠 경우에만 쓸 수 있습니다. `GET /v1/gateway/models/?type=decisions` 에 나오면 쓸 수 있습니다.

  **두 모델은 요청·응답 형식이 다릅니다.** 바로 아래의 파라미터·요청·응답은 `jev-latest` 기준입니다. `gpt-6-luna-decisions`는 [OpenAI 판정 모델](#openai-판정-모델--gpt-6-luna-decisions) 절을 보세요. 한 모델의 형식을 다른 모델에 보내면 `400`입니다.

---

### 파라미터

model
`jev-latest`.

state
판정할 내용. 문장, JSON 객체, 배열 모두 됩니다.

questions
`{ 질문 이름: 질문 }` 형태. 질문은 최대 **32개**, 이름은 128자까지입니다. 이름은 응답의 `answers` 키로 그대로 돌아옵니다.

각 질문은 다음 필드를 가집니다.

| 필드 | 설명 |
| --- | --- |
| `type` | `noul`, `choice`, `score` 중 하나 |
| `instructions` | 무엇을 판단할지 (문자열·객체·배열, 8,000자까지) |
| `criteria` | 유형별 기준 (아래 표) |

| `type` | 묻는 것 | `criteria` |
| --- | --- | --- |
| `noul` | 예/아니오 | 생략 가능. 주려면 `{"true": "…", "false": "…"}` |
| `choice` | 여러 선택지 중 하나 | `{ 선택지: 설명 }` 객체, 2~255개 |
| `score` | 순서가 있는 단계 | 낮은 단계부터 적은 배열, 2~10개 |

이 세 필드 말고 다른 필드를 보내면 `400`입니다.

---

### 요청

```bash
curl -X POST https://api.baze.co/v1/gateway/decisions/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "jev-latest",
    "state": "고객 문의: 지난주에 주문한 노트북이 아직 안 왔어요. 환불해 주세요. 정말 화가 납니다.",
    "questions": {
      "is_refund_request": { "type": "noul", "instructions": "고객이 환불을 요청하고 있는가?" },
      "category": {
        "type": "choice",
        "instructions": "문의 유형",
        "criteria": { "shipping": "배송 지연·분실", "billing": "결제·환불", "product": "제품 불량·사용법" }
      },
      "urgency": {
        "type": "score",
        "instructions": "얼마나 급하게 응대해야 하는가?",
        "criteria": ["낮음", "보통", "높음"]
      }
    }
  }'
```

### 응답

```json
{
  "id": "decisions-328039628b0e4179968cd269e47c2be5",
  "object": "decisions",
  "model": "jev-latest",
  "answers": {
    "is_refund_request": { "type": "noul", "noul": 0.98 },
    "category": {
      "type": "choice",
      "choice": "shipping",
      "confidence": 0.92,
      "probabilities": { "shipping": 0.95, "product": 0.0, "billing": 0.05 }
    },
    "urgency": {
      "type": "score",
      "score": 1.97,
      "confidence": 0.95,
      "legend": { "0": "낮음", "1": "보통", "2": "높음" },
      "probabilities": { "0": 0.0, "1": 0.03, "2": 0.97 }
    }
  },
  "usage": { "input_tokens": 434, "output_tokens": 72 }
}
```

| `type` | 읽는 법 |
| --- | --- |
| `noul` | `noul` 이 "예"일 확률 (0~1) |
| `choice` | `choice` 가 가장 확률 높은 선택지, `probabilities` 가 선택지별 확률 |
| `score` | `score` 는 단계 번호의 기댓값(0부터), `legend` 가 번호와 단계 이름, `probabilities` 가 단계별 확률 |

`confidence` 는 모델이 돌려주는 확신도입니다. 자동으로 처리할지 사람에게 넘길지를 가르는 기준으로 쓰세요.

---

### OpenAI 판정 모델 — `gpt-6-luna-decisions`

OpenAI Decisions API를 그대로 씁니다. 질문 세 가지 유형(예/아니오·선택·점수)은 Jev와 같지만, 필드 이름과 모양이 다릅니다.

| | `jev-latest` | `gpt-6-luna-decisions` |
| --- | --- | --- |
| 판정할 내용 | `state` (문자열·객체·배열) | `input` (문자열 또는 메시지 배열, 이미지 가능) |
| 질문 | 객체 `{ 이름: 질문 }` | 배열 `[{ "name": …, … }]` |
| 예/아니오 | `noul` | `predicate` |
| 선택지 / 단계 | `criteria` | `choices` / `levels` |
| 응답 `answers` | 질문 이름이 키인 객체 | 질문 순서대로의 배열 (`name` 포함) |

#### 파라미터

model
`gpt-6-luna-decisions`.

input
판정할 내용. 문자열 하나, 또는 `role: "user"` 메시지 배열입니다. 메시지의 `content`는 문자열이거나 `input_text`·`input_image` 블록 배열입니다.

이미지는 **base64 `data:` URL로만** 받습니다(요청당 최대 8장). `https://…` 같은 외부 이미지 URL은 `400`입니다.

```json
"input": [
  {
    "role": "user",
    "content": [
      { "type": "input_text", "text": "이 사진 속 제품이 파손되었는가?" },
      { "type": "input_image", "image_url": "data:image/jpeg;base64,/9j/4AAQ..." }
    ]
  }
]
```

questions
질문 배열. 최대 **32개**, `name`은 질문마다 달라야 하고 128자까지입니다.

| 필드 | 설명 |
| --- | --- |
| `name` | 질문 이름. 응답의 `answers[].name`으로 돌아옵니다 |
| `type` | `predicate`(예/아니오), `choice`, `score` 중 하나 |
| `instructions` | 무엇을 판단할지 (8,000자까지) |
| `choices` | `choice`일 때: `[{ "value": …, "description": … }]`, 2~255개. `value`는 서로 달라야 합니다 |
| `levels` | `score`일 때: 낮은 단계부터 `[{ "label": …, "description": … }]`, 2~10개 |

`description`은 생략할 수 있습니다. 위에 없는 필드는 요청 최상위든 질문 안이든 `400`입니다.

#### 요청

```bash
curl -X POST https://api.baze.co/v1/gateway/decisions/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-6-luna-decisions",
    "input": "고객 문의: 지난주에 주문한 노트북이 아직 안 왔어요. 환불해 주세요. 정말 화가 납니다.",
    "questions": [
      { "name": "is_refund_request", "type": "predicate", "instructions": "고객이 환불을 요청하고 있는가?" },
      {
        "name": "category",
        "type": "choice",
        "instructions": "문의 유형",
        "choices": [
          { "value": "shipping", "description": "배송 지연·분실" },
          { "value": "billing", "description": "결제·환불" },
          { "value": "product", "description": "제품 불량·사용법" }
        ]
      },
      {
        "name": "urgency",
        "type": "score",
        "instructions": "얼마나 급하게 응대해야 하는가?",
        "levels": [{ "label": "낮음" }, { "label": "보통" }, { "label": "높음" }]
      }
    ]
  }'
```

#### 응답

```json
{
  "id": "decisions-5d2f0c1e9a8b4c7d8e6f1a2b3c4d5e6f",
  "object": "decisions",
  "model": "gpt-6-luna-decisions",
  "answers": [
    { "type": "predicate", "name": "is_refund_request", "probability": 1.0 },
    {
      "type": "choice",
      "name": "category",
      "choice": "shipping",
      "probabilities": [
        { "value": "shipping", "probability": 0.92 },
        { "value": "billing", "probability": 0.08 },
        { "value": "product", "probability": 0.0 }
      ],
      "confidence": 0.88
    },
    {
      "type": "score",
      "name": "urgency",
      "score": 1.98,
      "probabilities": [
        { "value": 0, "label": "낮음", "probability": 0.0 },
        { "value": 1, "label": "보통", "probability": 0.02 },
        { "value": 2, "label": "높음", "probability": 0.98 }
      ],
      "confidence": 0.97
    }
  ],
  "usage": { "input_tokens": 428, "output_tokens": 0 }
}
```

| `type` | 읽는 법 |
| --- | --- |
| `predicate` | `probability`가 "예"일 확률 (0~1) |
| `choice` | `choice`가 가장 확률 높은 선택지, `probabilities`가 선택지별 확률 |
| `score` | `score`는 단계 번호의 기댓값(0부터), `probabilities`가 단계별 번호·이름·확률 |

`confidence`의 쓰임새는 Jev와 같습니다.

#### 한도

- `input`의 텍스트와 `questions`를 합쳐 약 **64,000 토큰**까지입니다. 이미지는 이 한도 계산에 들어가지 않습니다.
- 입력 토큰에만 과금되며, OpenAI가 보고한 입력 토큰 수가 기준입니다.
- 조직에서 개인정보 필터를 켠 경우 `input`의 텍스트가 검사 대상입니다. `questions`는 검사하지 않습니다.

---

### 한도와 과금 — `jev-latest`

- `state` 와 가장 긴 질문을 합쳐 약 **32,000 토큰**, 요청 전체는 약 **64,000 토큰**까지입니다. 넘으면 `400`과 함께 줄이라는 안내가 옵니다. 한글은 글자당 약 1토큰이라 영어보다 빨리 찹니다.
- **입력 토큰에만** 과금됩니다. 출력 토큰은 무료입니다.
- 조직에서 개인정보 필터를 켠 경우 `state` 도 검사 대상이며, 검사에도 요금이 붙습니다. `questions` 는 호출자가 정한 판단 기준이라 검사하지 않습니다.
- 스트리밍·도구 호출은 없습니다. 한 번의 요청에 한 번의 응답입니다.

---

### 에러

| 상태 | 모델 | 메시지 | 원인 |
| --- | --- | --- | --- |
| `400` | `jev-latest` | `Unsupported parameter(s): …` | `model`·`state`·`questions` 외의 필드. OpenAI 형식(`input`)을 보내면 `Unsupported parameter(s): input` |
| `400` | `gpt-6-luna-decisions` | `Unsupported parameter(s): …` | `model`·`input`·`questions` 외의 필드. Jev 형식(`state`)을 보내면 `Unsupported parameter(s): state` |
| `400` | `jev-latest` | `'questions' must be a non-empty object` | 질문이 없음 |
| `400` | `gpt-6-luna-decisions` | `'questions' must be a non-empty array` | 질문이 없음 |
| `400` | 공통 | `Too many questions (N). Maximum is 32` | 질문이 32개 초과 |
| `400` | `jev-latest` | `questions['X'].criteria …` | 유형에 맞지 않는 `criteria` |
| `400` | `jev-latest` | `The request is over the model's 64000-token budget` 등 | 너무 긴 요청 |
| `400` | `gpt-6-luna-decisions` | `The request is over the 64000-token budget` | 너무 긴 요청 |
| `400` | `gpt-6-luna-decisions` | `… image_url must be a base64 'data:' URL …` | 외부 이미지 URL |
| `400` | `gpt-6-luna-decisions` | `… role must be 'user'` | `user`가 아닌 메시지 |
| `400` | `gpt-6-luna-decisions` | `Question names must be unique` / `Choice values must be unique …` | 이름·선택지 값이 겹침 |
