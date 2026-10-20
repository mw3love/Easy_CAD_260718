# Realtime — 실시간 음성

> 실시간 음성 대화와 실시간 받아쓰기 (WebSocket)

WebSocket 으로 여는 실시간 세션입니다. 세 가지를 같은 API 키로 씁니다.

| 용도 | 프로토콜 | 모델 | 주소 |
| --- | --- | --- | --- |
| 음성 대화 | OpenAI Realtime | `gpt-realtime-2.1`, `gpt-realtime-2.1-mini` | `wss://…/v1/gateway/realtime?model=<모델>` |
| 음성 대화 | Gemini Live | `gemini-3.8-live`, `gemini-3.8-live-extended-thinking` | `wss://…/v1/gateway/gemini/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent` |
| 실시간 받아쓰기 | Soniox | `stt-rt-v5` | `wss://…/v1/gateway/soniox/transcribe-websocket` |

각 제공업체의 **원래 프로토콜을 그대로** 씁니다. 공식 SDK 나 예제 코드에서 주소와 키만 바꾸면 됩니다. 게이트웨이는 연결마다 인증·과금을 끼워 넣고, OpenAI Realtime·Gemini Live 소켓에는 조직이 개인정보 필터를 켠 경우에만 필터를 겁니다. Soniox 소켓에는 필터가 걸리지 않습니다.

음성 대화 모델은 조직에서 켠 경우에만 쓸 수 있습니다. `GET /v1/gateway/models/?type=realtime` 에 나오면 쓸 수 있습니다. 실시간 받아쓰기는 파일 받아쓰기([`/audio/transcriptions`](/docs/api-gateway/reference/audio-stt))가 켜진 조직이면 됩니다.

---

### 인증

**서버에서 연결할 때**는 WebSocket 핸드셰이크에 키를 헤더로 넣습니다. `Authorization: Bearer`, `x-api-key`, `x-goog-api-key` 중 무엇이든 됩니다.

**브라우저에서 연결할 때**는 키를 브라우저에 넣지 말고, 서버에서 일회용 토큰을 받아 넘기세요.

POST

```bash
curl -X POST https://api.baze.co/v1/gateway/realtime/sessions/ \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-realtime-2.1-mini"}'
```

```json
{
  "object": "gateway.live_session",
  "token": "Y_vbRsz7ZyDcN2wNzQ5l8GpgwmHeRmjEJZYiSL7juFs",
  "expires_at": "2026-09-29T04:08:22.200781+00:00",
  "model": "gpt-realtime-2.1-mini",
  "url": "/v1/gateway/realtime?model=gpt-realtime-2.1-mini"
}
```

브라우저는 `url` 에 `token` 을 쿼리로 붙여 연결합니다 (`…?model=gpt-realtime-2.1-mini&token=…`, 쿼리가 없는 주소는 `?token=…`).

- 토큰은 **60초** 동안, **한 번만** 쓸 수 있습니다. 다시 쓰면 `1008 invalid or already used session token` 으로 닫힙니다.
- 토큰은 발급할 때 정한 모델에만 쓸 수 있습니다.
- `model` 이 채팅 모델이면 `400` 과 함께 맞는 엔드포인트를 안내합니다.

---

### OpenAI Realtime

OpenAI Realtime API 와 같은 이벤트를 주고받습니다. 첫 이벤트로 `session.update` 를 보내세요.

```python
import asyncio, json, websockets

GATEWAY = "https://api.baze.co/v1/gateway".replace("https://", "wss://", 1)
URL = f"{GATEWAY}/realtime?model=gpt-realtime-2.1-mini"

async def main():
    async with websockets.connect(URL, additional_headers={"Authorization": "Bearer YOUR_API_KEY"}) as ws:
        await ws.send(json.dumps({"type": "session.update", "session": {
            "type": "realtime", "output_modalities": ["text"],
            "instructions": "한 문장으로 답하세요."}}))
        await ws.send(json.dumps({"type": "conversation.item.create", "item": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "대한민국의 수도는?"}]}}))
        await ws.send(json.dumps({"type": "response.create"}))
        async for raw in ws:
            event = json.loads(raw)
            if event["type"] == "response.output_text.delta":
                print(event["delta"], end="")
            if event["type"] == "response.done":
                break

asyncio.run(main())
```

음성으로 주고받으려면 `output_modalities` 에 `audio` 를 넣고 `input_audio_buffer.append` 로 오디오를 보냅니다. 이벤트 전체는 OpenAI Realtime 문서와 같습니다.

---

### Gemini Live

Gemini Live API 와 같은 메시지를 주고받습니다. 연결 후 **10초 안에** 첫 메시지로 `setup` 을 보내야 합니다. `setup.model` 이 쓸 모델입니다. 경로의 버전은 `v1beta` 와 `v1alpha` 를 받습니다.

```python
GATEWAY = "https://api.baze.co/v1/gateway".replace("https://", "wss://", 1)
URL = f"{GATEWAY}/gemini/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"

async with websockets.connect(URL, additional_headers={"x-goog-api-key": "YOUR_API_KEY"}) as ws:
    await ws.send(json.dumps({"setup": {
        "model": "models/gemini-3.8-live",
        "generationConfig": {"responseModalities": ["AUDIO"]},
        "outputAudioTranscription": {}}}))
    await ws.send(json.dumps({"realtimeInput": {"text": "대한민국의 수도는?"}}))
    async for raw in ws:
        message = json.loads(raw)
        text = message.get("serverContent", {}).get("outputTranscription", {}).get("text")
        if text:
            print(text, end="")
        if message.get("serverContent", {}).get("turnComplete"):
            break
```

---

### 실시간 받아쓰기 (Soniox)

Soniox 실시간 API 와 같습니다. 첫 프레임은 JSON 설정, 그다음은 바이너리 오디오, 끝낼 때는 **빈 텍스트 프레임**(`""`)을 보냅니다. 설정의 `api_key` 는 넣지 않아도 되고, `model` 은 `stt-rt-v5` 로 고정됩니다.

```python
GATEWAY = "https://api.baze.co/v1/gateway".replace("https://", "wss://", 1)
URL = f"{GATEWAY}/soniox/transcribe-websocket"

async with websockets.connect(URL, additional_headers={"Authorization": "Bearer YOUR_API_KEY"}) as ws:
    await ws.send(json.dumps({"model": "stt-rt-v5", "audio_format": "pcm_s16le",
                              "sample_rate": 24000, "num_channels": 1, "language_hints": ["ko"]}))
    for chunk in pcm_chunks:          # 0.1초 분량씩
        await ws.send(chunk)
    await ws.send("")                 # 끝 — 빈 바이너리 프레임이 아니라 빈 문자열
    async for raw in ws:
        message = json.loads(raw)
        print("".join(t["text"] for t in message.get("tokens", []) if t.get("is_final")), end="")
        if message.get("finished"):
            break
```

끝 프레임을 바이너리(`b""`)로 보내면 Soniox 가 끝을 알아채지 못해 잠시 뒤 `408 request_timeout` 으로 끝납니다.

---

### 과금

- 음성 대화는 **토큰 단위**입니다. 텍스트·오디오 입력과 출력 토큰을 모델 단가로 셉니다(Gemini 는 thinking 토큰 포함).
- 실시간 받아쓰기는 **처리한 오디오 초 단위**입니다.
- 세션을 여는 순간 1분어치를 먼저 잡아 두고, 쓰는 만큼 이어서 잡습니다. 세션이 끝나면 실제로 쓴 만큼만 한 번에 청구됩니다.
- 사용량은 [`/usage`](/docs/api-gateway/reference/usage) 에 모델 이름으로 남습니다.

---

### 연결이 닫힐 때

거절은 모두 연결을 연 뒤 **닫힘 코드**로 알려 줍니다. 닫힘 사유(reason)에 원인이 적혀 있습니다.

| 코드 | 뜻 | 대표 사유 |
| --- | --- | --- |
| `1000` | 정상 종료 — 세션당 60분 상한에 닿은 경우 포함 | `session cap`, `upstream closed`, `client closed` |
| `1008` | 정책 위반 — 인증 실패, 모델 없음·꺼짐, 잘못된 첫 메시지 | `missing ?model= on the URL`, `setup message not received in time`, `invalid or already used session token` |
| `1011` | 서버·제공업체 오류 — 제공업체 쪽이 비정상적으로 연결을 닫은 경우 포함 | `Gemini Live unavailable`, `upstream closed <code>: <제공업체 사유>` |
| `1013` | 잠시 후 다시 — 실시간 받아쓰기 동시 세션이 꽉 찼거나, 연결 시 검사가 `429`/`503`(속도 제한, 일시적 사용 불가)으로 응답함 | `all realtime slots are busy, retry shortly`, 또는 해당 `429`/`503` 메시지 |
| `4402` | 크레딧 부족 | 세션을 열 때나 도중에 잔액이 모자라면 이 코드로 닫힙니다 (`insufficient credits`) |
