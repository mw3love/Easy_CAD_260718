"""AI 게이트웨이 클라이언트 — 이미지→도면(§8 항목18) A단계.

`tools/ai_probe.py`(2026-08-11 실측)의 실호출 코드가 출발점이고, 형제 프로젝트
`Paste_flow/pasteflow/ocr_engine.py`의 모델 폴백(`_call_with_fallback`)·오류 분류(fail/
retry/weak) 패턴을 이식했다. 설계·실측 근거는 `docs/ai_image_import.md`, 함정은
`docs/pitfalls.md`의 "AI 게이트웨이 호출(이미지→도면)" 절 참조.

**PyQt 비의존.** `resolve_api_key()`만 QSettings를 쓰는데, 그마저도 함수 안에서 지연
임포트해 이 모듈의 나머지(모델 조회·크레딧·vision 호출)는 순수 파이썬 헤드리스 도구
(`tools/ai_sketch.py`)에서 Qt 애플리케이션 없이도 그대로 쓸 수 있다.

키 해석 순서(`resolve_api_key`): 명시 인자 > `~/.claude/.secrets/easycad-gateway.key`(첫 줄)
> QSettings("EasyCAD","EasyCAD")["ai_gateway_key"] > 환경변수 `EASYCAD_GW_KEY`.

**secrets 파일 관례는 `jbnu-gateway` 스킬(`~/.claude/skills/jbnu-gateway/scripts/_gw.py`)과
동일하게 맞췄다** — 단 계정이 다르다(jbnu-gateway.key=학교 계정, easycad-gateway.key=이
프로젝트가 쓰는 회사(kairos) 계정, 2026-08-11 확인). 파일은 `.gitignore`되는
`~/.claude/.secrets/` 아래라 대화·git 어디에도 키가 남지 않는다 — 이 규칙을 2026-08-11에
도입한 이유는 그 전에 `!` 프리픽스로 사용자가 직접 타이핑하다 셸 문법 실수로 키가 대화
로그에 그대로 노출된 사고 때문(`docs/pitfalls.md` 참조 없음, 재발 방지 목적으로 파일
경로 자체를 1순위로 승격).

⚠ 함정(`docs/pitfalls.md` 참조, 재확인 없이 우회하지 말 것):
- `urllib`로 이 게이트웨이를 호출하면 SSL 인증서 검증 실패(self-signed in chain).
  `openai` SDK·`httpx`(둘 다 certifi 기본 신뢰)만 쓴다 — 이 모듈은 표준 urllib을 쓰지 않는다.
- `claude-*` 계열은 밀집 도면 **전체 이미지**에서 504 Gateway Timeout(축소해도 동일).
  구획 크롭(줌인)에서는 정상 — `call_with_fallback`이 504도 모델없음과 같은 폴백 트리거로
  다룬다(ocr_engine 원본은 model_not_found만 다뤘으나, 이 게이트웨이의 실제 실패 모드가
  타임아웃이라 그 트리거를 넓혔다).
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
from pathlib import Path
from typing import Literal, NamedTuple, Optional

BASE_URL = "https://factchat.mindlogic-kr-api.com/v1/gateway"
KEY_ENV = "EASYCAD_GW_KEY"
SECRETS_FILE = Path.home() / ".claude" / ".secrets" / "easycad-gateway.key"

# 게이트웨이가 reasoning(thinking) 토큰을 같은 max_tokens 예산에서 차감한다(ocr_engine.py와
# 동일 실측 근거) — 작게 잡으면 thinking 모델에서 본문이 잘린다.
DEFAULT_MAX_TOKENS = 16384

# 실측(`docs/ai_image_import.md` "실측" 표, 2026-08-11) 기반 기본 모델.
# gemini 계열만 밀집 도면 전체 이미지를 완주한다 — 범용 기본값.
DEFAULT_MODEL = "gemini-3.6-flash"
FALLBACK_CHAIN = (DEFAULT_MODEL, "gemini-2.0-flash")


def _normalize_base_url(base_url: str) -> str:
    """OpenAI 호환 게이트웨이 base_url 정규화(ocr_engine._normalize_base_url과 동일 관례).

    사용자가 실수로 endpoint 전체 경로를 붙여넣어도 SDK 표준 형식으로 보정.
    예: '.../v1/gateway/chat/completions' → '.../v1/gateway'
    """
    if not base_url:
        return base_url
    url = base_url.strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions", "/models", "/embeddings", "/credits", "/credits/"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url


def _read_secrets_file() -> str:
    """`SECRETS_FILE` 첫(비어있지 않은) 줄에서 키를 읽는다 — `jbnu-gateway` 스킬의
    `_gw.py`와 동일한 파일 관례(경로만 이 프로젝트 전용)."""
    try:
        for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                return line.strip()
    except OSError:
        pass
    return ""


def resolve_api_key(explicit: str = "") -> str:
    """키 해석: 명시 인자 > `SECRETS_FILE` 첫 줄 > QSettings["ai_gateway_key"] > 환경변수.

    QSettings 접근은 여기서만 지연 임포트한다 — Qt 애플리케이션 인스턴스 없이도
    QSettings 값 읽기는 가능하지만(플랫폼 레지스트리/INI 직접 접근), 이 모듈의 나머지
    함수는 PyQt6를 아예 안 건드려야 헤드리스 도구에서 순수 파이썬으로 쓸 수 있다.
    """
    if explicit:
        return explicit.strip()
    from_file = _read_secrets_file()
    if from_file:
        return from_file
    try:
        from PyQt6.QtCore import QSettings
        stored = QSettings("EasyCAD", "EasyCAD").value("ai_gateway_key", "", type=str)
        if stored:
            return stored.strip()
    except Exception:
        pass
    return os.environ.get(KEY_ENV, "").strip()


def store_api_key(key: str) -> None:
    """설정창(C단계)에서 키를 저장할 때 쓸 대칭 함수 — QSettings에 영구 저장."""
    from PyQt6.QtCore import QSettings
    QSettings("EasyCAD", "EasyCAD").setValue("ai_gateway_key", key.strip())


# ── OpenAI 호환 클라이언트 캐시(ocr_engine._get_client와 동일 관례: 커넥션 풀 재사용) ──
_client_cache: dict[tuple[str, str, float], object] = {}


def _client(api_key: str, base_url: str = BASE_URL, timeout: float = 600.0):
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("openai 패키지 미설치: pip install openai") from e
    if not api_key:
        raise RuntimeError(f"API 키가 없습니다. 설정에서 입력하거나 환경변수 {KEY_ENV}를 설정하세요.")
    norm_url = _normalize_base_url(base_url)
    cache_key = (api_key, norm_url, timeout)
    client = _client_cache.get(cache_key)
    if client is None:
        client = OpenAI(api_key=api_key, base_url=norm_url, timeout=timeout, max_retries=0)
        _client_cache[cache_key] = client
    return client


def list_models(api_key: str, base_url: str = BASE_URL) -> list[str]:
    """게이트웨이의 `/models`에서 사용 가능한 모델 ID 목록. 필터 없이 전부 반환
    (ocr_engine.list_gemini_models과 동일 관례 — 어떤 모델이 실제로 되는지는 실호출로 안다)."""
    try:
        resp = _client(api_key, base_url).models.list()
    except Exception as e:
        raise RuntimeError(f"게이트웨이 모델 조회 실패: {e}") from e
    return sorted({m.id for m in resp.data})


def get_credit_balance(api_key: str, base_url: str = BASE_URL) -> tuple[float, float]:
    """크레딧 잔액 조회 — GET {base_url}/credits/ (Mindlogic 게이트웨이 전용 raw REST).

    `httpx`로 호출한다(certifi 기본 신뢰 — urllib과 달리 SSL 검증 함정이 없다,
    `docs/pitfalls.md` "AI 게이트웨이 호출" 참조). 응답 스키마
    `{"total": {"remaining": ..., "quota": ...}}`.
    """
    import httpx

    url = _normalize_base_url(base_url) + "/credits/"
    try:
        resp = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}") from e
    except httpx.HTTPError as e:
        raise RuntimeError(str(e)) from e
    total = data.get("total", {})
    return (float(total.get("remaining", 0)), float(total.get("quota", 0)))


# ── 오류 분류(ocr_engine.py 이식 + 이 게이트웨이 실측으로 확장) ───────────────────

def _is_model_not_found(exc: Exception) -> bool:
    msg = str(exc).lower()
    if "not found" in msg or "model_not_found" in msg:
        return True
    return "404" in msg and "model" in msg


def _is_gateway_timeout(exc: Exception) -> bool:
    """`claude-*` 계열이 밀집 도면 전체 이미지에서 겪는 504(`docs/ai_image_import.md` 실측).
    폴백 트리거에 반드시 포함해야 한다 — ocr_engine 원본은 model_not_found만 다뤘지만
    이 게이트웨이의 실제 실패 모드는 모델 부재가 아니라 타임아웃이다."""
    msg = str(exc).lower()
    return "504" in msg or "gateway timeout" in msg or (
        "timeout" in msg and "read" not in msg  # httpx의 클라이언트측 ReadTimeout과 구분 안 함(둘 다 재시도 대상)
    ) or "timed out" in msg


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg


def _is_server_busy(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "503" in msg or "unavailable" in msg or "overloaded" in msg


ErrorClass = Literal["model_not_found", "timeout", "quota", "server_busy", "other"]


def classify_error(exc: Exception) -> ErrorClass:
    """폴백·재시도 판단에 쓰는 굵은 분류. `quota`/`server_busy`는 일시적(재시도 여지),
    `model_not_found`/`timeout`은 이 모델로는 이 입력을 못 처리한다는 뜻(폴백 대상)."""
    if _is_model_not_found(exc):
        return "model_not_found"
    if _is_gateway_timeout(exc):
        return "timeout"
    if _is_quota_error(exc):
        return "quota"
    if _is_server_busy(exc):
        return "server_busy"
    return "other"


def select_fallback_model(failed_model: str, chain: tuple = FALLBACK_CHAIN) -> Optional[str]:
    """실패 모델이 아닌 사슬의 첫 항목. 남은 후보가 없으면 None."""
    for candidate in chain:
        if candidate != failed_model:
            return candidate
    return None


class VisionResult(NamedTuple):
    """`call_with_fallback`의 반환값.

    - content         : 모델 응답 본문 문자열(파싱은 호출자가 `parse_json` 등으로).
    - model_used       : 실제로 응답을 만든 모델(폴백 발생 시 폴백 모델).
    - fallback_from    : 원래 시도했다가 실패한 모델(폴백 없으면 None).
    - elapsed          : 성공한 호출의 소요 초.
    """
    content: str
    model_used: str
    fallback_from: Optional[str]
    elapsed: float


def _b64_png(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def call_vision(client, model: str, img, prompt: str, *,
                 schema: Optional[dict] = None, schema_name: str = "drawing",
                 max_tokens: int = DEFAULT_MAX_TOKENS) -> tuple[str, float]:
    """단일 vision 호출(폴백 없음). 반환 (본문 문자열, 소요초).

    `schema`를 주면 `json_schema` structured output(strict)을 쓴다 — 2026-08-11 실측으로
    이 게이트웨이에서 통함을 확인(`docs/ai_image_import.md`).
    """
    kw = {}
    if schema is not None:
        kw["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        }
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64_png(img)}"}},
            {"type": "text", "text": prompt},
        ]}],
        **kw,
    )
    return (resp.choices[0].message.content or ""), time.time() - t0


def call_with_fallback(api_key: str, img, prompt: str, *,
                        model: str = DEFAULT_MODEL, fallback_chain: tuple = FALLBACK_CHAIN,
                        base_url: str = BASE_URL, schema: Optional[dict] = None,
                        schema_name: str = "drawing", max_tokens: int = DEFAULT_MAX_TOKENS,
                        timeout: float = 600.0) -> VisionResult:
    """`call_vision`을 실행하고, `model_not_found`/`timeout`이면 `fallback_chain`의 다음
    모델로 1회 재시도한다(`quota`/`server_busy`/`other`는 그대로 던짐 — 조용히 갈아타면
    실패를 성공으로 오인하게 된다, ocr_engine의 프로브 분리 원칙과 동일)."""
    client = _client(api_key, base_url, timeout=timeout)

    def _try(m: str) -> tuple[str, float]:
        return call_vision(client, m, img, prompt, schema=schema, schema_name=schema_name,
                           max_tokens=max_tokens)

    try:
        content, dt = _try(model)
        return VisionResult(content, model, None, dt)
    except Exception as exc:
        cls = classify_error(exc)
        if cls not in ("model_not_found", "timeout"):
            raise
        fallback = select_fallback_model(model, fallback_chain)
        if not fallback:
            raise
        content, dt = _try(fallback)
        return VisionResult(content, fallback, model, dt)


def parse_json(raw: str) -> dict:
    """모델 응답에서 JSON을 꺼낸다. 스키마를 안 쓴 폴백 경로는 ```json 펜스가 섞여 나온다."""
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1]
        if txt[:4].lower().startswith("json"):
            txt = txt[txt.find("\n"):]
    return json.loads(txt)
