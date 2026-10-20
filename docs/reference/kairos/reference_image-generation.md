# 이미지 생성

> 이미지 생성 엔드포인트

텍스트 프롬프트에서 이미지를 생성하는 API입니다.

Google, OpenAI, Black Forest Labs, ByteDance, Ideogram, Recraft, Stability AI, xAI, Alibaba 등 다양한 제공업체의 이미지 모델을 지원합니다. 대부분 결과를 바로 돌려주고, Fal 모델은 생성이 오래 걸릴 때만 `operation_id`로 폴링합니다.

  동기 이미지 생성은 모델에 따라 응답 시간이 다릅니다. Google Gemini 모델은 약 5~10초, OpenAI 모델은 약 15~30초가 소요됩니다. HTTP 클라이언트의 타임아웃을 최소 60초 이상으로 설정해주세요 (httpx 기본값은 5초입니다).

---

### 이미지 생성

POST

텍스트 프롬프트에서 하나 이상의 이미지를 생성합니다.

### 상태 폴링 (지연된 작업만)

GET

생성 응답에 `operation_id`가 왔을 때만 씁니다. Fal 모델은 보통 결과를 바로 돌려주고, 생성이 오래 걸리거나 제공업체 쪽 일시 오류가 나면 `processing` 상태와 `operation_id`를 돌려줍니다.

---

### 파라미터

model
이미지 모델 이름.

prompt
생성할 이미지에 대한 텍스트 설명.

number_of_images
생성할 이미지 수 (기본값: `1`).

aspect_ratio
예: `"1:1"`, `"16:9"`, `"9:16"`, `"4:3"`.

quality
`"standard"` 또는 `"hd"` (제공업체별 상이).

image_size
예: `"1024x1024"` (제공업체별 상이).

input_images
편집·합성·인페인팅에 사용할 입력 이미지 목록. 값을 넣으면 같은 엔드포인트가 편집 모드로 동작합니다.

---

### 이미지 편집 · 합성

편집 전용 엔드포인트는 따로 없습니다. 생성과 같은 `POST /v1/gateway/images/generate/`에 `input_images`를 넣으면 편집 모드로 전환됩니다.

- 배열의 각 항목은 `http(s)` URL 또는 `data:image/...;base64,...` 형태의 데이터 URL입니다. 이미지 호스팅이 없는 로컬 애플리케이션이라면 데이터 URL이 가장 간단한 방법입니다. 접두사 없는 raw base64 문자열은 `400`으로 거절됩니다.
- 이미지를 여러 장 넣으면 합성됩니다. 티셔츠 사진과 패턴 원단 사진을 함께 넣고 "Apply the pattern from the second image onto the garment in the first image"라고 지시하면 첫 번째 이미지의 옷에 두 번째 이미지의 패턴이 입혀집니다. 프롬프트에서는 넣은 순서대로 "첫 번째 이미지", "두 번째 이미지"처럼 지칭하세요.
- 모델 한도(아래 표)보다 이미지를 많이 넣어도 게이트웨이는 요청을 거절하지 않습니다. 이미지를 한 장만 받는 모델은 첫 번째 이미지만 쓰고, 나머지 모델은 목록 전체를 제공사에 넘기므로 제공사가 거절할 수 있습니다. 한도 안에서 보내세요.
- 편집 전용 모델(`bytedance/seedream/v5/pro/layerize`)을 `input_images` 없이 호출하면 `400`이 반환됩니다: `Model 'X' edits an existing image only. Pass 'input_images' with at least one image URL.`

  요청 본문은 25MB를 넘을 수 없습니다(초과 시 `413`). base64 데이터 URL은 원본보다 약 33% 커지므로, 데이터 URL로 이미지를 넣는다면 원본 파일 합계 18MB 안팎이 실질 상한입니다. 큰 이미지는 데이터 URL 대신 `http(s)` URL로 넘기거나 업로드 전에 리사이즈하세요.

#### 모델별 최대 입력 이미지 수

| 모델 | 최대 입력 이미지 |
| --- | --- |
| Nano Banana 2.1 (`gemini-nano-banana-2.1`) | 14 |
| Nano Banana 2 (`gemini-3.1-flash-image-preview`) | 14 |
| Nano Banana 2 Lite (`gemini-3.1-flash-lite-image`) | 14 |
| Nano Banana Pro, Nano Banana, GPT Image 2.5 Sunburst / 2.5 Flare, GPT Image 2 / 1.5 / 1 / 1 Mini, Seedream 5.0 Pro / 5.0 Lite / 4.5 / 4.0 | 10 |
| FLUX 2 [pro] (`fal-ai/flux-2-pro`) | 8 |
| SDXL, Ideogram V3 | 1 |
| Seedream 5.0 Pro Layerize (`bytedance/seedream/v5/pro/layerize`) | 1 (편집 전용 — `input_images` 필수) |
| Recraft V4, FLUX 1.1 [pro], Grok Imagine 2.0, Ideogram V4 [fast], Qwen Image 3 (`qwen-image-3.0`), Z-Image Turbo (`z-image-turbo`) | 0 (생성 전용 — `input_images` 미지원) |

  이미지 모델은 `/chat/completions`로 호출할 수 없습니다. 시도하면 `404 invalid_request_error - Model '<name>' not found`가 반환됩니다. 이미지는 반드시 `/v1/gateway/images/generate/`를 사용하세요.

#### curl

```bash
curl -X POST https://api.baze.co/v1/gateway/images/generate/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.1-flash-lite-image",
    "prompt": "Apply the pattern from the second image onto the garment in the first image",
    "input_images": [
      "https://example.com/tshirt.jpg",
      "https://example.com/pattern.png"
    ]
  }'
```

#### Python

```python
import base64, mimetypes, requests

API_KEY = "YOUR_API_KEY"
URL = "https://api.baze.co/v1/gateway/images/generate/"

def to_data_url(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()

resp = requests.post(
    URL,
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "my-app/1.0",  # User-Agent가 비어 있으면 403 (error code: 1010)
    },
    json={
        "model": "gemini-3.1-flash-lite-image",
        "prompt": "Apply the pattern from the second image onto the garment in the first image",
        "input_images": [to_data_url("tshirt.jpg"), to_data_url("pattern.png")],
    },
    timeout=120,
)
resp.raise_for_status()

# 응답의 base64 데이터 URL을 파일로 저장
url = resp.json()["data"][0]["url"]
with open("edited.png", "wb") as f:
    f.write(base64.b64decode(url.split(",", 1)[1]))
print("Saved edited.png")
```

---

### 응답 — 동기 제공업체 (Google)

```json
{
  "id": "img-a1b2c3d4e5f6g7h8",
  "created": 1738000000,
  "model": "gemini-2.5-flash-image",
  "data": [
    { "url": "data:image/png;base64,iVBORw0KGgo..." }
  ],
  "usage": {
    "prompt_tokens": 42,
    "completion_tokens": 1290,
    "total_tokens": 1332
  },
  "credits_charged": 28.3121
}
```

  Fal 모델은 생성이 오래 걸리면 결과 대신 `operation_id`를 돌려줍니다. 이때는 아래처럼 상태를 폴링하세요. 응답에 `data`가 있으면 폴링할 필요가 없습니다.

### 응답 — 결과가 아직 준비되지 않았을 때 (Fal)

```json
{
  "operation_id": "gw.3f9c1a7e52b04d18.fal-ai/flux-2-pro::0b6e4f2a-9c1d-4e8b-a5f3-7d2c9e1b4a60",
  "status": "processing",
  "credits_charged": 29.038
}
```

`credits_charged` 는 이 호출로 차감된 크레딧입니다(모든 계정). 이 경우에는 접수 시점(`processing` 응답)에 차감됩니다. 호출 전에 금액을 알고 싶다면 [`/estimate`](/docs/api-gateway/reference/estimate) 를 쓰세요.

`GET /v1/gateway/images/generate/{operation_id}/?model=<model_name>`으로 `status`가 `"completed"`가 될 때까지 폴링하세요. `operation_id`는 받은 문자열을 그대로 넘기세요. 요청한 회원에게만 유효해서, 같은 조직의 다른 회원이 조회하면 `404`입니다.

---

### 예제

#### curl

```bash
curl -X POST https://api.baze.co/v1/gateway/images/generate/ \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash-image",
    "prompt": "A mountain landscape at sunset with dramatic clouds",
    "aspect_ratio": "16:9"
  }'
```

#### Python

```python
import httpx, base64

API_KEY = "YOUR_API_KEY"
BASE = "https://api.baze.co/v1/gateway"
client = httpx.Client(headers={"Authorization": f"Bearer {API_KEY}"}, timeout=60.0)

# 동기 제공업체 (Google Gemini) — 즉시 반환
resp = client.post(f"{BASE}/images/generate/", json={
    "model": "gemini-2.5-flash-image",
    "prompt": "A mountain landscape at sunset with dramatic clouds",
    "aspect_ratio": "16:9",
    "number_of_images": 1,
})
data = resp.json()

# base64 이미지 저장
for i, img in enumerate(data["data"]):
    b64 = img["url"].split(",", 1)[1]
    with open(f"image_{i}.png", "wb") as f:
        f.write(base64.b64decode(b64))
    print(f"Saved image_{i}.png")

print(f"사용된 토큰: {data['usage']['total_tokens']}")
```

#### Python — Fal 모델 (지연 시 폴링)

```python
import time

MODEL = "fal-ai/flux-2-pro"
data = client.post(f"{BASE}/images/generate/", json={
    "model": MODEL,
    "prompt": "A futuristic city skyline",
    "image_size": "landscape_16_9",
}).json()

# 대부분 바로 결과가 옵니다. processing이 왔을 때만 폴링하세요.
while data.get("status") == "processing":
    time.sleep(5)
    data = client.get(
        f"{BASE}/images/generate/{data['operation_id']}/",
        params={"model": MODEL},
    ).json()

print("이미지 URL:", data["data"][0]["url"])
```

#### JavaScript

```javascript
const response = await fetch(
  "https://api.baze.co/v1/gateway/images/generate/",
  {
    method: "POST",
    headers: {
      Authorization: "Bearer YOUR_API_KEY",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-image-1",
      prompt: "A mountain landscape at sunset",
      quality: "high",
      number_of_images: 1,
    }),
  }
);
const data = await response.json();
console.log(`생성된 이미지: ${data.data.length}개`);
```

---

### 제공업체 참고

| 제공업체 | 동기/비동기 | URL 유형 | 비고 |
| --- | --- | --- | --- |
| Google (Gemini) | 동기 | Base64 인라인 | 기본 제공업체. 모델: `gemini-2.5-flash-image` |
| OpenAI (GPT Image) | 동기 | HTTPS URL 또는 base64 | 임시 URL, 즉시 다운로드 권장 |
| ByteDance (Seedream) | 동기 | HTTPS URL | |
| Fal | 동기 (지연 시 폴링) | HTTPS CDN URL | 생성이 오래 걸리면 `operation_id`로 폴링 |
| Alibaba (Model Studio) | 동기 | HTTPS URL | |

---

### 사용 가능한 모델

조직에서 사용 가능한 모델의 라이브 목록을 확인하려면 잘못된 `model` 값으로 `POST /v1/gateway/images/generate/`를 호출하세요 — 404 응답의 `detail` 필드에 `Available models: [...]` 가 포함되어 반환됩니다.

#### OpenAI (동기)
| 모델 | 크레딧/이미지 | 주요 파라미터 |
| --- | --- | --- |
| `gpt-image-2` | 41 | `size`, `quality` (low/medium/high), `background` (auto/opaque) |
| `gpt-image-2.5-sunburst` | 10 | `size`, `quality`, `background` |
| `gpt-image-2.5-flare` | 10 | `size`, `quality`, `background` |
| `gpt-image-1.5` | 39 | `size`, `quality` (low/medium/high), `background` (auto/transparent/opaque) |
| `gpt-image-1` | 42 | `size`, `quality` (low/medium/high), `background` |
| `gpt-image-1-mini` | 8 | `size`, `quality` (low/medium/high), `background` |

#### Google (동기)
| 모델 | 크레딧/이미지 | 주요 파라미터 |
| --- | --- | --- |
| `gemini-nano-banana-2.1` (Nano Banana 2.1) | 37 | `aspect_ratio`, `image_size` (1K/2K/4K), `number_of_images` (최대 4) |
| `gemini-3.1-flash-image-preview` (Nano Banana 2) | 69 | `aspect_ratio`, `image_size` (1K/2K/4K), `number_of_images` (최대 4) |
| `gemini-3-pro-image-preview` (Nano Banana Pro) | 140 | `aspect_ratio`, `image_size` (1K/2K/4K), `number_of_images` (최대 4) |
| `gemini-3.1-flash-lite-image` (Nano Banana 2 Lite) | 34 | `aspect_ratio`, `image_size`, `input_images` (최대 14) |
| `gemini-2.5-flash-image` (Nano Banana) | 39 | `aspect_ratio`, `number_of_images` (최대 4) |

#### ByteDance (동기)
| 모델 | 크레딧/이미지 | 주요 파라미터 |
| --- | --- | --- |
| `bytedance/seedream-5-pro` (Seedream 5.0 Pro) | 90 | `image_size` (square/square_hd/landscape_4_3/landscape_16_9/portrait_4_3/portrait_16_9), `input_images` (최대 10) |
| `fal-ai/bytedance/seedream/v5/lite` (Seedream 5.0 Lite) | 35 | `image_size` (위 6가지 + auto_2K/auto_3K/auto_4K) |
| `fal-ai/bytedance/seedream/v4.5` (Seedream 4.5) | 40 | `image_size` (square/landscape/portrait/2K/4K) |
| `bytedance/seedream-4` | 30 | `aspect_ratio`, `size` (1K/2K/4K) |

#### Fal (동기 — 생성이 오래 걸리면 폴링)
| 모델 | 크레딧/이미지 | 주요 파라미터 |
| --- | --- | --- |
| `fal-ai/flux-2-pro` (FLUX 2 [pro]) | 30 | `image_size` (square_hd/square/portrait_4_3/portrait_16_9/landscape_4_3/landscape_16_9), `input_images` (최대 8) |
| `fal-ai/flux-pro/v1.1` (FLUX 1.1 [pro]) | 40 | `image_size` (위와 같은 6가지), 생성 전용 |
| `fal-ai/fast-sdxl` (SDXL) | 5 | `image_size` (위와 같은 6가지) |
| `fal-ai/ideogram/v3` (Ideogram V3) | 60 | `image_size` (위와 같은 6가지), `rendering_speed` (TURBO/BALANCED/QUALITY), `style` (AUTO/GENERAL/REALISTIC/DESIGN) |
| `ideogram/v4/fast` (Ideogram V4 [fast]) | 10 | `image_size` (위와 같은 6가지), `rendering_speed` (TURBO/BALANCED), 생성 전용 |
| `fal-ai/recraft/v4/text-to-image` (Recraft V4) | 40 | `image_size` (위와 같은 6가지), 생성 전용 |
| `bytedance/seedream/v5/pro/layerize` (Seedream 5.0 Pro Layerize) | 34 | 편집 전용 — `input_images` 필수(최대 1). `image_size` (auto/auto_1K/auto_1.5K/auto_2K), `enhance_prompt_mode` (standard/fast) |
| `xai/grok-imagine-image/v2.0/text-to-image` (Grok Imagine 2.0) | 60 | `aspect_ratio` (1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 2:1, 1:2 등), `resolution` (1k/2k), `quality` (low/medium), 생성 전용 |

#### Alibaba (동기)
| 모델 | 크레딧/이미지 | 주요 파라미터 |
| --- | --- | --- |
| `qwen-image-3.0` | 40 | 크기 파라미터 없음 — 출력은 1024×1024 고정. 생성 전용 |
| `z-image-turbo` | 5 | 크기 파라미터 없음 — 출력은 1024×1024 고정. 생성 전용 |

  예전 모델 이름도 계속 받습니다. `black-forest-labs/flux-2-pro` → `fal-ai/flux-2-pro`, `black-forest-labs/flux-1.1-pro` → `fal-ai/flux-pro/v1.1`, `stability-ai/sdxl:7762fd07…` → `fal-ai/fast-sdxl`, `xai/grok-imagine-image` → `xai/grok-imagine-image/v2.0/text-to-image`로 연결됩니다. 새 코드에는 새 이름을 쓰세요.

  조직에 따라 일부 모델이 활성화되지 않을 수 있습니다. 활성화되지 않은 모델을 사용하면 `403` 에러가 반환됩니다 — 관리자에게 문의하세요.
