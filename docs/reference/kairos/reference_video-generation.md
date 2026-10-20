# 비디오 생성

> 비동기 비디오 생성 엔드포인트

텍스트 프롬프트에서 비디오를 생성하는 비동기 API입니다.

Seedance, Kling, Gemini Omni Flash 등 최신 비디오 생성 모델을 사용하여 고품질 영상을 만들 수 있습니다. 비디오 생성은 작업 제출 → 상태 폴링 → 다운로드의 3단계로 진행됩니다.

---

### 참고

  생성 시간은 모델에 따라 다릅니다. `minimax/h3-max-turbo`는 몇 초에서 10초 안쪽, 대부분의 모델은 30~120초, `bytedance/seedance-2.5`는 길이와 참조 수에 따라 2~6분까지 걸릴 수 있습니다. 폴링 간격은 10초를 권장합니다.

- `operation_id`에 슬래시가 포함될 수 있습니다 — 전체 문자열을 그대로 전달하세요
- `operation_id`는 작업을 만든 회원에게만 유효합니다. 같은 조직의 다른 회원이 조회하거나 다운로드하면 `404`입니다
- 폴링 및 다운로드 URL에 `?model=<모델명>`을 반드시 추가하세요 (예: `?model=google/gemini-omni-flash/v1.1`). 없으면 400 에러가 반환됩니다.

---

### 엔드포인트

| Method | Path | 설명 |
| --- | --- | --- |
| POST | `/v1/gateway/video/generation/` | 비디오 생성 작업 시작 |
| GET | `/v1/gateway/video/generation/{operation_id}/` | 작업 상태 폴링 |
| GET | `/v1/gateway/video/generation/{operation_id}/download/` | 완성된 비디오 다운로드 |

---

### 1. 비디오 생성 시작

POST

비동기 비디오 생성 작업을 시작합니다.

#### 파라미터

model
비디오 모델 이름 (예: `google/gemini-omni-flash/v1.1`, `fal-ai/kling-video/v3`).

prompt
생성할 비디오에 대한 텍스트 설명.

parameters
모델별 파라미터 (종횡비, 길이 등).

input_urls
입력 이미지/비디오 URL (이미지-투-비디오 모델용).

#### 응답

```json
{
  "operation_id": "gw.dcf14f430a2cef8e.openrouter:gen-vid-1790652775-0oa5SoIayNOMl8YAkol7",
  "status": "processing",
  "video_model_id": 12,
  "credits_charged": 435.57
}
```

`credits_charged` 는 접수 시 차감된 크레딧입니다(모든 계정). 결과 없이 실패한 작업의 크레딧은 접수 후 7일 안의 상태 조회에서 `failed` 가 확인될 때 환불됩니다. 그러니 작업마다 `completed` 나 `failed` 가 나올 때까지 폴링하세요. 폴링을 멈춘 작업은 자동으로 환불되지 않습니다. 호출 전에 금액을 알고 싶다면 [`/estimate`](/docs/api-gateway/reference/estimate) 를 쓰세요.

`video_model_id`는 요청이 실제로 배정된 비디오 모델의 내부 ID입니다. 크레딧 정산과 문의 시 어떤 모델로 처리됐는지 확인하는 용도로 씁니다.

요청 본문은 25MB를 넘을 수 없습니다(초과 시 `413`). `input_urls`에 base64 데이터 URL을 넣으면 원본보다 약 33% 커지므로, 입력 이미지는 `http(s)` URL로 넘기는 편이 안전합니다.

ByteDance(ModelArk) 계열 모델(`bytedance/…`)에 참조 이미지를 넣을 때는 이미지의 전체 픽셀 수(가로 × 세로)가 36,000,000을 넘을 수 없습니다. 초과한 이미지는 크레딧이 차감되기 전에 `400`으로 거절되니, 이미지를 줄여서 다시 요청해 주세요.

---

### 2. 상태 폴링

GET

#### Query Parameter

model
비디오 생성 시 사용한 모델 이름 (예: `google/gemini-omni-flash/v1.1`). 이 파라미터가 없으면 `400` 에러가 반환됩니다.

**결과 파일을 바로 넘기지 않는 제공업체** — `video_uri`가 상대 경로(다운로드 엔드포인트)로 반환됩니다:

```json
{
  "operation_id": "gw.dcf14f430a2cef8e.openrouter:gen-vid-1790652775-0oa5SoIayNOMl8YAkol7",
  "status": "completed",
  "video_uri": "/v1/gateway/video/generation/gw.dcf14f430a2cef8e.openrouter:gen-vid-1790652775-0oa5SoIayNOMl8YAkol7/download/?model=<모델명>",
  "duration_seconds": null
}
```

**Fal 등 URL을 바로 주는 제공업체** — `video_uri`가 직접 다운로드 가능한 CDN URL로 반환됩니다:

```json
{
  "operation_id": "gw.8b1e53c07fa24d69.xai/grok-imagine-video::5e94b562-ee6c-47be-973c-6546e70b7175",
  "status": "completed",
  "video_uri": "https://v3b.fal.media/files/.../video.mp4",
  "duration_seconds": null
}
```

| Status | 의미 |
| --- | --- |
| `processing` | 작업 진행 중 |
| `completed` | 비디오 준비 완료 |
| `failed` | 생성 실패 |

---

### 3. 비디오 다운로드

GET

#### Query Parameter

model
비디오 생성 시 사용한 모델 이름 (예: `google/gemini-omni-flash/v1.1`). 이 파라미터가 없으면 `400` 에러가 반환됩니다.

`video/mp4` 바이트를 직접 스트리밍합니다.

---

### 전체 흐름 (Python)

```python
import time
import httpx

API_KEY = "YOUR_API_KEY"
BASE = "https://api.baze.co/v1/gateway"
client = httpx.Client(headers={"Authorization": f"Bearer {API_KEY}"}, timeout=120.0)

# 1. 시작
resp = client.post(f"{BASE}/video/generation/", json={
    "model": "google/gemini-omni-flash/v1.1",
    "prompt": "A serene mountain lake at sunrise",
})
operation_id = resp.json()["operation_id"]

# 2. 폴링
while True:
    status = client.get(f"{BASE}/video/generation/{operation_id}/", params={"model": "google/gemini-omni-flash/v1.1"}).json()
    if status["status"] in ("completed", "failed"):
        break
    time.sleep(10)

# 3. 다운로드
resp = client.get(f"{BASE}/video/generation/{operation_id}/download/", params={"model": "google/gemini-omni-flash/v1.1"})
with open("output.mp4", "wb") as f:
    f.write(resp.content)
```

---

### 사용 가능한 모델

크레딧은 모델 기본값이며, 조직 설정에 따라 달라질 수 있습니다.

| 모델 | 제공업체 | 크레딧/비디오 | 주요 파라미터 |
| --- | --- | --- | --- |
| `bytedance/seedance-2.5` | ByteDance (ModelArk) | 1,165 | `duration` (5/10/15/30초), `resolution` (480p/720p/1080p), `aspect_ratio` |
| `fal-ai/vidu/q3` | Vidu (Fal) | 770 | `duration` (2–16초), `resolution` (360p/540p/720p/1080p), `aspect_ratio`, `audio` |
| `bytedance/seedance-2.0` | ByteDance (ModelArk) | 500 | `duration` (5/10), `resolution` (720p/1080p), `aspect_ratio` |
| `lightricks/ltx-2.5/pro` | Lightricks (Fal) | 720 | `duration` (6/8/10), `resolution` (720p/1080p), `aspect_ratio`, `generate_audio` |
| `bytedance/seedance-2.0/fast` | ByteDance (ModelArk) | 250 | `duration` (5/10), `resolution` (720p), `aspect_ratio` |
| `lightricks/ltx-2.5/fast` | Lightricks (Fal) | 540 | `duration` (6/8/10), `resolution` (720p/1080p), `aspect_ratio`, `generate_audio` |
| `fal-ai/luma-dream-machine/ray-2` | Luma (Fal) | 500 | `duration` (5초/9초), `resolution` (540p/720p/1080p), `aspect_ratio`, `loop` |
| `fal-ai/kling-video/o3` | Kling (Fal) | 420 | `duration` (3–15초), `aspect_ratio`, `mode` (standard/pro), `generate_audio` |
| `fal-ai/kling-video/v3` | Kling (Fal) | 420 | `duration` (3–15초), `aspect_ratio`, `mode` (standard/pro), `generate_audio` |
| `fal-ai/kling-video/v2.5-turbo/pro` | Kling (Fal) | 350 | `duration` (5/10), `aspect_ratio` |
| `fal-ai/pixverse/v5` | PixVerse (Fal) | 150 | `duration` (5/8), `quality` (360p–1080p), `aspect_ratio` |
| `xai/grok-imagine-video` | xAI (Fal) | 300 | `duration` (1–15초), `resolution` (480p/720p), `aspect_ratio` |
| `fal-ai/minimax/hailuo-02` | MiniMax (Fal) | 270 | `duration` (6초 고정), `resolution` (768p/1080p) |
| `minimax/h3-max` | MiniMax (Fal) | 400 | `duration` (5/10), `resolution` (`480P`/`768P`/`1080P`, 대문자 P), `aspect_ratio` (21:9, 16:9, 4:3, 1:1, 3:4, 9:16) |
| `minimax/h3-max-turbo` | MiniMax (Fal) | 200 | `duration` (5/10), `resolution` (`480P`/`768P`/`1080P`, 대문자 P), `aspect_ratio` (21:9, 16:9, 4:3, 1:1, 3:4, 9:16) |
| `bytedance/seedance-1-pro` | ByteDance (ModelArk) | 60 | `duration` (2–12초), `resolution` (480p/720p/1080p), `aspect_ratio` |
| `bytedance/seedance-1.5-pro` | ByteDance (ModelArk) | 130 | `duration` (5/10), `resolution` (480p/720p/1080p), `aspect_ratio` |
| `bytedance/seedance-1.0-pro/fast` | ByteDance (ModelArk) | 97 | `duration` (5/10), `resolution` (480p/720p/1080p), `aspect_ratio` |
| `wan3.0-video-prime` | Alibaba (Model Studio) | 1,400 | `duration` (5초 고정) |
| `happyhorse-1.1-t2v` | Alibaba (Model Studio) | 900 | `duration` (5초 고정) |
| `google/gemini-omni-flash/v1.1` | Google (Fal) | 240 | `duration` (3–10초, 기본 8초), `resolution` (360p/720p/1080p/4K), `aspect_ratio` |

대부분의 모델은 텍스트-투-비디오와 이미지-투-비디오(1개 입력 이미지, `input_urls` 사용)를 모두 지원합니다. `wan3.0-video-prime`, `happyhorse-1.1-t2v`는 텍스트-투-비디오 전용이라 입력 이미지를 받지 않습니다. `google/gemini-omni-flash/v1.1`은 입력 이미지를 최대 3개까지 받습니다(1개는 첫 프레임, 2–3개는 참조 이미지).

`minimax/h3-max`와 `minimax/h3-max-turbo`는 참조 영상·오디오를 받지 않습니다(이미지 1개만). `resolution` 값은 다른 모델과 달리 대문자 `P`(`768P`)로 보내야 하고, 이미지-투-비디오에서는 비율을 입력 이미지에서 가져오므로 `aspect_ratio`는 텍스트-투-비디오에서만 지정합니다.

  조직에 따라 일부 모델이 활성화되지 않을 수 있습니다. 활성화되지 않은 모델을 사용하면 `403` 에러가 반환됩니다 — 관리자에게 문의하세요.

---

### 크레딧 산정 방식

표의 크레딧은 각 모델의 **기본 파라미터(기본 길이·해상도) 기준값**입니다. 실제 차감액은 요청한 `duration`·`resolution`(모델에 따라 `mode`·`generate_audio`)에 따라 달라지며, 길이를 늘리거나 해상도를 올리면 그만큼 커집니다.

예를 들어 `bytedance/seedance-2.5`는 출력 해상도와 길이에 비례해 산정되고, 표의 1,165는 **720p·5초** 기준값입니다.

| 해상도 \ 길이 | 5초 | 10초 | 15초 | 30초 |
| --- | --- | --- | --- | --- |
| 480p | 518 | 1,032 | 1,546 | 3,088 |
| 720p | 1,165 | 2,321 | 3,476 | 6,943 |
| 1080p | 2,622 | 5,222 | 7,822 | 15,622 |

`minimax/h3-max`와 `minimax/h3-max-turbo`는 해상도별 **초당 크레딧**으로 산정됩니다. 표의 400과 200은 **768P·5초** 기준값이고, 10초는 두 배입니다.

| 모델 | 480P | 768P | 1080P |
| --- | --- | --- | --- |
| `minimax/h3-max` | 50 크레딧/초 | 80 크레딧/초 | 160 크레딧/초 |
| `minimax/h3-max-turbo` | 25 크레딧/초 | 40 크레딧/초 | 80 크레딧/초 |

`input_urls`로 참조 **영상**을 넣으면 그 길이도 함께 산정됩니다. 참조 이미지는 추가 과금이 없습니다.

### 실패 건 과금

크레딧은 생성 요청이 접수되는 시점에 차감되고, 작업이 `failed`로 끝나 결과물이 제공되지 않으면 차감분이 자동으로 환불됩니다. 콘텐츠 정책·저작권 검사로 출력이 거부된 경우도 같습니다. 환불이 확인되지 않으면 `operation_id`와 함께 문의해 주세요.
