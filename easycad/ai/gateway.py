"""AI 게이트웨이 클라이언트 — 텍스트/이미지 설명→Mermaid 생성(§8 항목18 후속).

형제 프로젝트 `Paste_flow/pasteflow/ocr_engine.py`의 모델 폴백(`_call_with_fallback`)·
오류 분류(fail/retry/weak) 패턴을 이식했다. 설계 근거는 `docs/ai_image_import.md`(옛
이미지→JSON 경로, 2026-08-12 폐기), 함정은 `docs/pitfalls.md`의 "AI 게이트웨이 호출" 절.

2026-08-12: 이미지→**좌표 보존 JSON** 경로(vision 호출·P1~P3.75 타일링 파이프라인)는
완전히 폐기했다(`parse_json`도 함께 삭제) — 그 복잡성은 전부 "원본 배치를 정밀하게
지켜야 한다"는 요구에서 왔는데, Mermaid는 애초에 좌표가 없는 관계형 DSL이라 그 요구
자체가 없다. 같은 날 후속으로 이미지→**Mermaid 텍스트** 입력을 다시 받았다(`call_text`/
`call_text_with_fallback`이 이제 선택적 `image` 인자를 받는다) — 단일 호출, 타일링
없음, 좌표 없음이라 옛 파이프라인과는 다른 훨씬 가벼운 경로다.

**PyQt 비의존.** `resolve_api_key()`만 QSettings를 쓰는데, 그마저도 함수 안에서 지연
임포트해 이 모듈의 나머지(모델 조회·크레딧·텍스트/이미지 호출)는 순수 파이썬에서 Qt
애플리케이션 없이도 그대로 쓸 수 있다.

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
"""
from __future__ import annotations

import base64
import io
import os
import time
from pathlib import Path
from typing import Literal, NamedTuple, Optional

BASE_URL = "https://factchat.mindlogic-kr-api.com/v1/gateway"
KEY_ENV = "EASYCAD_GW_KEY"
SECRETS_FILE = Path.home() / ".claude" / ".secrets" / "easycad-gateway.key"

# QSettings 조직/앱 이름 — 상수로 빼서 테스트가 `monkeypatch`로 격리된 값으로 바꿔치기할 수
# 있게 한다(2026-08-20, `_isolated_symbol_library` 관례를 그대로 따름). 이전엔 4개 함수가
# 전부 `QSettings("EasyCAD", "EasyCAD")`를 하드코딩해 테스트가 격리할 방법이 없었고, 그
# 결과 실사용자의 진짜 저장된 API 키가 pytest 실행마다(`tests/test_part9_ai_mermaid.py`의
# `_clear_gateway_settings()`) 조용히 지워지는 사고로 이어졌다 — "저장한 키가 앱을 껐다
# 켜면 사라진다"는 재현 안 되던 버그의 실제 원인이 앱 코드가 아니라 이거였다.
_SETTINGS_ORG = "EasyCAD"
_SETTINGS_APP = "EasyCAD"

# 게이트웨이가 reasoning(thinking) 토큰을 같은 max_tokens 예산에서 차감한다(ocr_engine.py와
# 동일 실측 근거) — 작게 잡으면 thinking 모델에서 본문이 잘린다.
DEFAULT_MAX_TOKENS = 16384

# 텍스트 전용 기본값(§8 항목18 후속, 2026-08-12 — Mermaid 가져오기 통합, 이미지 경로 폐기).
# gpt/gemini 두 계열만 노출(사용자 확정 — claude 제외), 계열별 가성비 최선 1곳씩 추천.
# SVG 에셋 생성창(`_SvgAssetDialog`)의 슬롯 A/B 기본값으로 쓰인다 — GPT/Gemini
# 두 계열을 나란히 비교하는 게 그 창의 설계 의도라 계열별로 하나씩 유지한다.
# [2026-08-21 실사용 버그] `gpt-5.4-mini`가 게이트웨이에서 은퇴돼(`Model not found` 404)
# 재실측 — 실제 Mermaid 생성 호출(`text_to_mermaid.generate_mermaid`)로 크레딧 잔액
# 전후차를 실측한 결과 gpt-5.6-luna가 압도적으로 저렴·최속이었다(같은 설명 기준
# gpt-5.6-luna 0.09 크레딧/0.99초, gpt-5.6-sol 2.12/1.67, gpt-5.6-terra 0.77/1.14,
# gpt-5.5 3.23/4.57).
# ⚠ 같은 날 후속 재실측(더 상세한 요청 프롬프트로) — gpt-5.6 계열(luna/sol/terra)
# 전부 "상세하게" 같은 확장 요청에 노드 1개만 돌려주고 마는 경우가 잦았다(luna 3/3,
# terra 1/4 — 나머지는 정상이었지만 비용도 0.77~3.71 크레딧으로 요동쳐 신뢰하기
# 어려움). 확장 요청엔 상위 모델 gpt-5.5(26노드, 3.23 크레딧)만 안정적이었으나
# "가성비 최선"이라는 이 상수의 취지에 안 맞아 SVG 창 몫으로만 남겨두고(그쪽은
# 이번에 검증 안 함), **Mermaid 창은 아래 `TEXT_RECOMMEND_MERMAID`로 완전히 분리**했다.
TEXT_RECOMMEND_1 = "gpt-5.6-luna"       # gpt 계열 — SVG 슬롯 A 전용(Mermaid는 미사용)
TEXT_RECOMMEND_2 = "gemini-3.6-flash"   # gemini 계열 — SVG 슬롯 B 전용(Mermaid는 미사용)

# Mermaid 가져오기 창 전용 기본값(2026-08-21) — 위 GPT/Gemini 비교쌍과 별개로,
# "이 작업 하나에 제일 나은 모델 하나"만 필요해서 분리했다. 실측: 같은 "재건축
# 시나리오 상세하게" 프롬프트로 4회 반복한 결과 노드 12~13개·엣지 11~12개를 매번
# 안정적으로 냈고(gpt-5.6 계열의 들쭉날쭉함과 대조적), 비용도 0.43~0.46 크레딧으로
# 좁게 수렴 — gpt-5.6-luna보다 조금 비싸지만(약 4~5배) gpt-5.5(3.23)의 1/7 수준이면서
# 품질은 gpt-5.5와 대등했다.
TEXT_RECOMMEND_MERMAID = "gemini-3.5-flash-lite"


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
        stored = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value("ai_gateway_key", "", type=str)
        if stored:
            return stored.strip()
    except Exception:
        pass
    return os.environ.get(KEY_ENV, "").strip()


def store_api_key(key: str) -> None:
    """설정창(C단계)에서 키를 저장할 때 쓸 대칭 함수 — QSettings에 영구 저장.
    `sync()`로 즉시 디스크/레지스트리에 flush — Qt의 암묵적 지연 flush(보통 이벤트루프
    유휴 시나 객체 소멸 시)에만 맡기면, 저장 직후 비정상 종료(강제 종료·크래시)가 겹칠 때
    쓰기가 유실될 여지가 이론상 있다(2026-08-20, 저장이 안 되는 것처럼 보인다는 재현
    안 되는 사용자 보고에 대한 방어적 조치 — 실측으로는 유실을 재현하지 못했다)."""
    from PyQt6.QtCore import QSettings
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue("ai_gateway_key", key.strip())
    settings.sync()


def resolve_base_url(explicit: str = "") -> str:
    """게이트웨이 주소 해석: 명시 인자 > QSettings["ai_gateway_base_url"] > 기본값(BASE_URL).
    `resolve_api_key`와 달리 secrets 파일 단계가 없다 — 주소는 비밀이 아니라 파일로
    분리할 이유가 없고, `_AIGatewaySettingsDialog`에서 직접 입력·저장하는 용도다."""
    if explicit:
        return explicit.strip()
    try:
        from PyQt6.QtCore import QSettings
        stored = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value("ai_gateway_base_url", "", type=str)
        if stored:
            return stored.strip()
    except Exception:
        pass
    return BASE_URL


def store_base_url(url: str) -> None:
    """설정창에서 게이트웨이 주소를 저장할 때 쓸 대칭 함수 — QSettings에 영구 저장.
    `store_api_key`와 동일 이유로 `sync()` 즉시 flush."""
    from PyQt6.QtCore import QSettings
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue("ai_gateway_base_url", url.strip())
    settings.sync()


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


def list_models(api_key: str, base_url: str = BASE_URL, timeout: float = 600.0) -> list[str]:
    """게이트웨이의 `/models`에서 사용 가능한 모델 ID 목록. 필터 없이 전부 반환
    (ocr_engine.list_gemini_models과 동일 관례 — 어떤 모델이 실제로 되는지는 실호출로 안다).

    `timeout`은 기본값(600s)과 별개로 짧게 줄 수 있다 — `list_text_models`가 이걸
    호출부(`host_dialogs._MermaidDialog._populate_models`)의 동기 호출 제약에 맞춰
    짧은 timeout(8s)으로 넘긴다. 네트워크가 죽어 있으면 기본 600초를 그대로 물려받아
    다이얼로그 자체가 못 뜨는 걸 막기 위함."""
    try:
        resp = _client(api_key, base_url, timeout=timeout).models.list()
    except Exception as e:
        raise RuntimeError(f"게이트웨이 모델 조회 실패: {e}") from e
    return sorted({m.id for m in resp.data})


def list_text_models(api_key: str, base_url: str = BASE_URL, timeout: float = 8.0) -> list[str]:
    """`list_models`를 gpt·gemini 계열로만 걸러 반환 — 텍스트 전용 드롭다운용(사용자 확정,
    claude 계열은 제외). 짧은 기본 timeout은 `_MermaidDialog._populate_models`와 같은
    이유(다이얼로그 생성이 동기 호출이라 네트워크가 죽어 있으면 다이얼로그 자체가 못 뜬다).

    [2026-08-21 실사용 버그] "gpt"/"gemini" 이름 포함만 걸러서 `gemini-3.1-flash-
    lite-image` 같은 이미지 전용 모델까지 "텍스트 모델"로 새고 있었다 — 실제로
    text chat completion을 호출해보면 404("Model not found")를 낸다(실측 확인).
    이름에 "image"·"tts"가 들어간 것(이미지 생성·음성합성 전용)을 추가로 제외한다."""
    models = list_models(api_key, base_url, timeout=timeout)
    return sorted(m for m in models
                 if ("gpt" in m.lower() or "gemini" in m.lower())
                 and "image" not in m.lower() and "tts" not in m.lower())


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


def select_fallback_model(failed_model: str, chain: tuple = ()) -> Optional[str]:
    """실패 모델이 아닌 사슬의 첫 항목. 남은 후보가 없으면 None."""
    for candidate in chain:
        if candidate != failed_model:
            return candidate
    return None


class GatewayResult(NamedTuple):
    """`call_text_with_fallback`의 반환값.

    - content         : 모델 응답 본문 문자열.
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


def call_text(client, model: str, prompt: str, *, image=None,
              max_tokens: int = DEFAULT_MAX_TOKENS) -> tuple[str, float]:
    """텍스트 전용 또는 이미지+텍스트 호출(단일, 폴백 없음). `image`(PIL Image)를 주면
    vision 콘텐츠 배열로, 안 주면 문자열 하나만 보낸다(이름은 `call_text`로 남겨둔다 —
    text_to_mermaid.py 등 기존 호출부가 이 이름을 그대로 쓴다). 반환 (본문 문자열, 소요초)."""
    if image is not None:
        content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_b64_png(image)}"}},
            {"type": "text", "text": prompt},
        ]
    else:
        content = prompt
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
    )
    return (resp.choices[0].message.content or ""), time.time() - t0


def call_text_with_fallback(api_key: str, prompt: str, *, model: str, image=None,
                             fallback_chain: tuple = (), base_url: str = BASE_URL,
                             max_tokens: int = DEFAULT_MAX_TOKENS,
                             timeout: float = 60.0) -> GatewayResult:
    """`call_text`를 실행하고, `model_not_found`/`timeout`이면 `fallback_chain`의 다음
    모델로 1회 재시도한다(`quota`/`server_busy`/`other`는 그대로 던짐 — 조용히 갈아타면
    실패를 성공으로 오인하게 된다, ocr_engine의 프로브 분리 원칙과 동일). 기본 timeout은
    짧게(60s) 잡는다 — `image`가 있으면 호출부(`text_to_mermaid.generate_mermaid`)가 더
    넉넉한 값을 넘긴다(단일 이미지 1장이라 옛 밀집 타일링 파이프라인만큼 오래 걸리진
    않지만, 순수 텍스트보다는 여유가 필요). `fallback_chain`이 비어 있으면(기본값) 실패
    시 그대로 예외를 올린다 — 모델은 사용자가 드롭다운에서 직접 골라 쓰므로 정해진
    폴백 사슬을 강제할 이유가 없다."""
    client = _client(api_key, base_url, timeout=timeout)

    def _try(m: str) -> tuple[str, float]:
        return call_text(client, m, prompt, image=image, max_tokens=max_tokens)

    try:
        content, dt = _try(model)
        return GatewayResult(content, model, None, dt)
    except Exception as exc:
        cls = classify_error(exc)
        if cls not in ("model_not_found", "timeout") or not fallback_chain:
            raise
        fallback = select_fallback_model(model, fallback_chain)
        if not fallback:
            raise
        content, dt = _try(fallback)
        return GatewayResult(content, fallback, model, dt)
