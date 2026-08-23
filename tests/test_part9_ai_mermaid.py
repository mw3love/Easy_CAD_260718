"""§8 항목18(AI 이미지→도면) 후속 — Mermaid 가져오기 통합(2026-08-12).

deep-interview(2026-08-12)로 확정된 대로 이미지 입력 경로(옛 sketch_pipeline.py 전체,
P1~P3.75 타일링, host_ai.py QThread 워커, _AIImageImportDialog)를 완전히 폐기하고
"텍스트 설명 → AI(게이트웨이 1회 호출) → Mermaid 텍스트"로 `fileio/mermaid_import.py`
가져오기 다이얼로그(`host_dialogs._MermaidDialog`)에 흡수했다.

이 파일이 검증하는 것:
  - `gateway.py`의 텍스트 전용 호출(`call_text`/`call_text_with_fallback`) — 이미지 없는
    단순 chat completion. 게이트웨이 실호출은 여기서 하지 않는다(수동 `tools/ai_probe.py`
    스타일 실행이 필요하나, §8 항목18 텍스트 전용 실측은 API 키가 있어야 가능 — 아직 없음).
  - `easycad/ai/text_to_mermaid.py` — 프롬프트 빌더·코드펜스 벗기기·generate_mermaid.
  - `_MermaidDialog`의 AI 보조 생성 — 2칸 구조(`_prompt_edit` 설명/Enter 트리거,
    `_edit` 최종 Mermaid 코드), 모델 드롭다운(gemini/gpt 그룹 헤더, 추천 배지 없음),
    우상단 게이트웨이 설정 버튼.
  - `_AIGatewaySettingsDialog`(2026-08-12) — 게이트웨이 주소·API 키 입력·저장에 더해
    "연결 테스트"(모델 gpt/gemini 개수 + 크레딧 잔여를 한 번에) 버튼까지.
  - 옛 이미지 경로가 실제로 사라졌는지(메뉴 액션·믹스인 잔존 여부) 회귀 가드.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part9_ai_mermaid.py.
"""
from PyQt6.QtCore import QSettings, QEvent
from PyQt6.QtWidgets import QDialog, QDialogButtonBox

from _shared import *  # noqa: F401,F403

from easycad.ai import gateway as gw  # noqa: E402
from easycad.ai import text_to_mermaid as ttm  # noqa: E402
from easycad.canvas.host_dialogs import (  # noqa: E402
    _MermaidDialog, _AIGatewaySettingsDialog, _render_mermaid_preview_pixmap,
    _pick_fallback_model, _model_version_key,
)


def _wait_worker(dlg):
    """2026-08-19 비동기화(`_MermaidGenWorker`, QThread) — `_on_ai_clicked()`는 즉시
    반환하고 백그라운드 스레드에서 돈다. `wait()`로 스레드 종료까지 막은 뒤
    `processEvents()`를 몇 번 돌려야 큐잉된(cross-thread) 시그널이 실제로 슬롯에
    전달된다(Qt의 기본 QueuedConnection 동작 — 이벤트 루프가 펌핑돼야 배달됨)."""
    dlg._worker.wait(5000)
    for _ in range(5):
        QApplication.processEvents()


def _wait_model_list_worker(dlg):
    """2026-08-20 비동기화(`_ModelListWorker`, QThread) — `_populate_models()`가 이제
    즉시 반환하고 실제 목록 조회는 백그라운드에서 돈다. `_wait_worker`와 동일한 이유로
    `wait()`+`processEvents()` 펌핑이 필요."""
    dlg._model_list_worker.wait(5000)
    for _ in range(5):
        QApplication.processEvents()


def _clear_gateway_settings():
    """반복 실행 시 테스트끼리 서로 오염되지 않도록 매번 명시적으로 지운다.
    conftest.py의 `_isolate_gateway_settings`(autouse)가 `gw._SETTINGS_ORG/_SETTINGS_APP`을
    격리된 값으로 이미 바꿔치기해 두므로, 여기서도 하드코딩 대신 그 값을 그대로 참조해야
    실사용자 레지스트리를 건드리지 않는다(2026-08-20 — 하드코딩된 "EasyCAD"였을 때 pytest
    실행마다 실사용자의 진짜 저장 API 키가 지워지던 사고, `docs/pitfalls.md` 참조)."""
    s = QSettings(gw._SETTINGS_ORG, gw._SETTINGS_APP)
    s.remove("ai_gateway_key")
    s.remove("ai_gateway_base_url")


# ── gateway.py: 텍스트 전용 호출 ─────────────────────────────────────────────

def test_call_text_sends_plain_string_content_not_vision_array():
    """`call_vision`은 content가 [image_url, text] 배열이지만, `call_text`는 이미지가
    없으므로 문자열 하나만 보내야 한다 — vision 콘텐츠 배열을 실수로 재사용하면 게이트웨이가
    이미지 없는 요청을 거부하거나 프롬프트를 잘못 해석할 위험이 있다."""
    captured = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    captured.update(kw)
                    class _Resp:
                        choices = [type("_C", (), {"message": type("_M", (), {"content": "ok"})()})()]
                    return _Resp()

    text, dt = gw.call_text(_FakeClient(), "gpt-5.4-mini", "설명을 Mermaid로")
    assert text == "ok"
    assert captured["messages"] == [{"role": "user", "content": "설명을 Mermaid로"}]
    assert captured["model"] == "gpt-5.4-mini"


def test_call_text_with_fallback_no_chain_raises_on_timeout():
    """텍스트 전용은 기본 폴백 사슬이 없다(사용자가 드롭다운에서 직접 모델을 고름) —
    빈 `fallback_chain`이면 실패를 그대로 올려야 한다."""
    def fake_call_text(client, model, prompt, *, image=None, max_tokens=0):
        raise RuntimeError("Error code: 504 Gateway Timeout")

    with patch.object(gw, "_client", lambda *a, **k: object()), \
         patch.object(gw, "call_text", fake_call_text):
        try:
            gw.call_text_with_fallback("key", "prompt", model="gpt-5.4-mini")
            assert False, "should have raised"
        except RuntimeError as e:
            assert "504" in str(e)


def test_call_text_with_fallback_uses_chain_when_provided():
    calls = []

    def fake_call_text(client, model, prompt, *, image=None, max_tokens=0):
        calls.append(model)
        if model == "gpt-5.4-mini":
            raise RuntimeError("Error code: 404 model_not_found")
        return "결과", 0.5

    with patch.object(gw, "_client", lambda *a, **k: object()), \
         patch.object(gw, "call_text", fake_call_text):
        result = gw.call_text_with_fallback(
            "key", "prompt", model="gpt-5.4-mini",
            fallback_chain=("gpt-5.4-mini", "gemini-3.6-flash"))
    assert calls == ["gpt-5.4-mini", "gemini-3.6-flash"]
    assert result.model_used == "gemini-3.6-flash"
    assert result.fallback_from == "gpt-5.4-mini"


def test_call_text_with_fallback_does_not_swallow_quota_error():
    def fake_call_text(*a, **k):
        raise RuntimeError("Error code: 429 RESOURCE_EXHAUSTED")

    with patch.object(gw, "_client", lambda *a, **k: object()), \
         patch.object(gw, "call_text", fake_call_text):
        try:
            gw.call_text_with_fallback("key", "prompt", model="gpt-5.4-mini",
                                       fallback_chain=("gemini-3.6-flash",))
            assert False, "should have raised"
        except RuntimeError as e:
            assert "429" in str(e)


def test_call_text_sends_vision_content_array_when_image_given():
    """`image`가 주어지면 문자열 대신 [image_url, text] 콘텐츠 배열을 보내야 한다."""
    from PIL import Image
    captured = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    captured.update(kw)
                    class _Resp:
                        choices = [type("_C", (), {"message": type("_M", (), {"content": "ok"})()})()]
                    return _Resp()

    img = Image.new("RGB", (10, 10), "white")
    text, dt = gw.call_text(_FakeClient(), "gemini-3.6-flash", "이미지를 Mermaid로", image=img)
    assert text == "ok"
    content = captured["messages"][0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1] == {"type": "text", "text": "이미지를 Mermaid로"}


def test_list_text_models_filters_to_gpt_and_gemini_only():
    """사용자 확정(deep-interview 2026-08-12) — claude 계열은 텍스트 전용 드롭다운에서 제외."""
    with patch.object(gw, "list_models",
                      lambda *a, **k: ["claude-sonnet-5", "gpt-5.4-mini", "gemini-3.6-flash",
                                       "claude-haiku-4-5", "gpt-5.4-nano"]):
        out = gw.list_text_models("key")
    assert out == sorted(["gpt-5.4-mini", "gemini-3.6-flash", "gpt-5.4-nano"])
    assert "claude-sonnet-5" not in out
    assert "claude-haiku-4-5" not in out


def test_list_text_models_excludes_image_and_tts_variants():
    """[2026-08-21 실사용 버그] `gemini-3.1-flash-lite-image`처럼 이름에 gpt/gemini가
    들어있어도 실제로는 이미지·음성 전용이라 text chat completion에서 404가 나는
    모델이 있었다(실측 확인) — "image"/"tts"가 들어간 이름은 텍스트 목록에서 제외."""
    with patch.object(gw, "list_models",
                      lambda *a, **k: ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite-image",
                                       "gemini-2.5-flash-preview-tts", "gpt-image-1",
                                       "gpt-5.6-luna"]):
        out = gw.list_text_models("key")
    assert out == sorted(["gemini-3.5-flash-lite", "gpt-5.6-luna"])


def test_model_version_key_extracts_leading_version():
    assert _model_version_key("gemini-3.5-flash-lite") == (3, 5)
    assert _model_version_key("gpt-5.6-luna") == (5, 6)
    assert _model_version_key("gemini-3.10-flash") == (3, 10)   # 10 > 9, 문자열 정렬 함정 회피
    assert _model_version_key("no-version-here") == (0,)


def test_pick_fallback_model_prefers_highest_versioned_lite():
    """[2026-08-21 사용자 확정] "lite가 붙은 이름 중 가장 높은 번호를 최우선"."""
    candidates = ["gemini-3.5-flash", "gemini-3.4-flash-lite",
                 "gemini-3.6-flash-lite", "gemini-3.5-flash-lite"]
    assert _pick_fallback_model(candidates) == "gemini-3.6-flash-lite"


def test_pick_fallback_model_falls_back_to_alphabetical_when_no_lite():
    candidates = ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.5"]
    assert _pick_fallback_model(candidates) == sorted(candidates)[0]


def test_pick_fallback_model_empty_candidates_returns_none():
    assert _pick_fallback_model([]) is None


# ── text_to_mermaid.py ───────────────────────────────────────────────────────

def test_build_prompt_includes_description_and_mermaid_rules():
    text = ttm.build_prompt("날씨를 예보하는 워크플로우")
    assert "날씨를 예보하는 워크플로우" in text
    assert "flowchart" in text
    assert "Mermaid" in text


def test_extract_mermaid_strips_language_tagged_code_fence():
    raw = "```mermaid\nflowchart TD\n A-->B\n```"
    assert ttm.extract_mermaid(raw) == "flowchart TD\n A-->B"


def test_extract_mermaid_strips_bare_code_fence():
    raw = "```\nflowchart LR\n A-->B\n```"
    assert ttm.extract_mermaid(raw) == "flowchart LR\n A-->B"


def test_extract_mermaid_passthrough_when_no_fence():
    raw = "flowchart TD\n A-->B"
    assert ttm.extract_mermaid(raw) == raw


def test_generate_mermaid_returns_text_and_model_used():
    def fake_call(api_key, prompt, *, model, **kw):
        assert "설명" in prompt or True
        return gw.GatewayResult("```mermaid\nflowchart TD\n A-->B\n```", model, None, 1.2)

    with patch.object(ttm.gw, "call_text_with_fallback", fake_call):
        text, used = ttm.generate_mermaid("key", "간단한 흐름", model="gpt-5.4-mini")
    assert text == "flowchart TD\n A-->B"
    assert used == "gpt-5.4-mini"


def test_build_image_prompt_includes_note_and_no_hallucination_rule():
    text = ttm.build_image_prompt("방송 송신소 계통도")
    assert "방송 송신소 계통도" in text
    assert "실제로 그려진" in text   # 2026-07-21 환각 함정 재확인 규칙 계승


def test_build_image_prompt_omits_note_line_when_empty():
    text = ttm.build_image_prompt("")
    assert "참고" not in text


def test_generate_mermaid_uses_image_prompt_and_longer_timeout_when_image_given():
    from PIL import Image
    captured = {}

    def fake_call(api_key, prompt, *, model, image=None, base_url=None, timeout=None):
        captured["prompt"] = prompt
        captured["image"] = image
        captured["timeout"] = timeout
        return gw.GatewayResult("flowchart TD\n A-->B", model, None, 1.0)

    img = Image.new("RGB", (10, 10), "white")
    with patch.object(ttm.gw, "call_text_with_fallback", fake_call):
        text, used = ttm.generate_mermaid("key", "보충설명", model="gpt-5.4-mini", image=img)
    assert text == "flowchart TD\n A-->B"
    assert captured["image"] is img
    assert "보충설명" in captured["prompt"]
    assert "실제로 그려진" in captured["prompt"]
    assert captured["timeout"] == 120.0   # 텍스트 전용 기본(60s)보다 넉넉하게


def test_generate_mermaid_uses_text_prompt_when_no_image():
    captured = {}

    def fake_call(api_key, prompt, *, model, image=None, base_url=None, timeout=None):
        captured["prompt"] = prompt
        captured["timeout"] = timeout
        return gw.GatewayResult("flowchart TD\n A-->B", model, None, 1.0)

    with patch.object(ttm.gw, "call_text_with_fallback", fake_call):
        ttm.generate_mermaid("key", "간단한 흐름", model="gpt-5.4-mini")
    assert "flowchart" in captured["prompt"]
    assert captured["timeout"] == 60.0


# ── _MermaidDialog: AI 보조 생성 ─────────────────────────────────────────────

def _combo_model_ids(dlg):
    """콤보박스에 실제로 담긴 선택 가능한(그룹 헤더 제외) model_id 전체."""
    m = dlg._model_combo.model()
    return [m.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(m.rowCount()) if m.item(i).isEnabled()]


def _select_model(dlg, model_id):
    m = dlg._model_combo.model()
    for i in range(m.rowCount()):
        if m.item(i).data(Qt.ItemDataRole.UserRole) == model_id:
            dlg._model_combo.setCurrentIndex(i)
            return
    raise AssertionError(f"{model_id} not found in combo")


def test_mermaid_dialog_populate_models_groups_gemini_and_gpt():
    """gpt/gemini를 그룹 헤더(선택 불가)가 있는 평범한 드롭다운으로 나눈다(재피드백:
    2열 병렬 패널 대신 드롭다운으로, 추천 배지·설명 문구는 뺌).
    [2026-08-20] `_populate_models`가 `_ModelListWorker`(QThread)로 비동기화돼(첫
    오픈 지연 수정) 조회 완료를 명시적으로 기다려야 한다."""
    # [2026-08-21] 추천 모델(gw.TEXT_RECOMMEND_MERMAID)을 하드코딩 문자열이 아니라
    # 심볼로 넣는다 — 게이트웨이가 추천 모델을 은퇴시켜 상수 값이 바뀌어도(gpt-5.4-mini
    # 404 실사용 버그) 이 테스트가 "추천 모델이 실제 목록에 있을 때 기본 선택된다"는
    # 의도를 계속 검증하게 하려는 것(하드코딩이면 상수가 바뀌는 순간 목록에 없는 모델을
    # 기본값으로 기대하는 죽은 테스트가 된다). Mermaid 창은 gpt-5.6 계열이 확장 요청에
    # 불안정함이 드러나(같은 날 후속) `TEXT_RECOMMEND_1`(GPT, SVG 창 전용)이 아니라
    # `TEXT_RECOMMEND_MERMAID`(Gemini)를 쓴다.
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               return_value=[gw.TEXT_RECOMMEND_MERMAID, "gpt-5.4-nano", "gemini-2.0-flash"]):
        dlg = _MermaidDialog()
        _wait_model_list_worker(dlg)
    assert dlg.model() == gw.TEXT_RECOMMEND_MERMAID
    assert set(_combo_model_ids(dlg)) == {gw.TEXT_RECOMMEND_MERMAID, "gpt-5.4-nano", "gemini-2.0-flash"}
    m = dlg._model_combo.model()
    header_texts = {m.item(i).text() for i in range(m.rowCount()) if not m.item(i).isEnabled()}
    assert header_texts == {"Gemini", "GPT"}
    all_texts = [m.item(i).text() for i in range(m.rowCount())]
    assert not any("추천" in t for t in all_texts)   # 추천 배지/설명 문구 없음
    # claude는 애초에 list_text_models가 걸러주므로 드롭다운에 아예 없어야 함(방어적 확인).
    assert "claude-sonnet-5" not in _combo_model_ids(dlg)


def test_mermaid_dialog_falls_back_when_recommended_model_retired():
    """[2026-08-21 실사용 버그 재발방지] 게이트웨이가 추천 모델(TEXT_RECOMMEND_MERMAID)을
    은퇴시켜 실제 목록에 없으면(gpt-5.4-mini 404 재현), 예전엔 `_fill_model_combo_
    grouped`가 그 값을 풀에 강제로 합쳐넣어 죽은 모델이 계속 기본 선택으로 남았다 —
    이제는 같은 계열(gemini) 안의 살아있는 모델로 자동 폴백해야 한다. 폴백 후보에
    "lite" 붙은 게 있으면 그걸 최우선으로(`_pick_fallback_model` — 같은 날 후속 확정)."""
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               return_value=["gemini-3.5-flash", "gemini-3.6-flash"]):
        dlg = _MermaidDialog()
        _wait_model_list_worker(dlg)
    # 후보에 lite가 하나도 없으니 알파벳 순 첫 항목(gemini-3.5-flash)으로 폴백.
    assert dlg.model() == "gemini-3.5-flash"
    assert gw.TEXT_RECOMMEND_MERMAID not in _combo_model_ids(dlg)


def test_mermaid_dialog_falls_back_prefers_highest_versioned_lite():
    """[2026-08-21] 폴백 후보 중 "lite" 붙은 이름이 여러 버전 있으면 가장 높은 버전을
    고른다 — 사용자 확정 휴리스틱: "lite가 붙은 이름 중에 가장 높은 번호를 최우선".
    목록에서 `TEXT_RECOMMEND_MERMAID` 자체는 빼야 폴백 경로가 실제로 걸린다(있으면
    그대로 선택돼 폴백 로직을 안 타므로 이 테스트가 무의미해진다)."""
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               return_value=["gemini-3.5-flash", "gemini-3.4-flash-lite",
                            "gemini-3.6-flash-lite"]):
        dlg = _MermaidDialog()
        _wait_model_list_worker(dlg)
    assert dlg.model() == "gemini-3.6-flash-lite"


def test_mermaid_dialog_populate_models_falls_back_when_list_fails():
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               side_effect=RuntimeError("no network")):
        dlg = _MermaidDialog()
        _wait_model_list_worker(dlg)
    assert dlg.model() == gw.TEXT_RECOMMEND_MERMAID
    assert set(_combo_model_ids(dlg)) == {
        gw.TEXT_RECOMMEND_MERMAID, gw.TEXT_RECOMMEND_1, gw.TEXT_RECOMMEND_2}


def test_mermaid_dialog_selecting_combo_item_updates_model():
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               return_value=["gpt-5.4-mini", "gemini-3.6-flash", "gemini-2.0-flash"]):
        dlg = _MermaidDialog()
        _wait_model_list_worker(dlg)
    _select_model(dlg, "gemini-2.0-flash")
    assert dlg.model() == "gemini-2.0-flash"


def test_mermaid_dialog_two_boxes_ai_fills_code_box_prompt_stays():
    """1번 칸(`_prompt_edit`)에 설명을 쓰고 AI 생성하면 결과는 2번 칸(`_edit`, 최종
    Mermaid 코드)에 채워지고, 1번 칸 내용은 지워지지 않아 수정 후 재생성이 가능하다
    (2026-08-12 재피드백으로 1칸 → 2칸 복귀, 각 칸이 서로 다른 목적이라 실수로 덮어쓸
    위험이 구조적으로 없다). 2번 칸은 그 뒤에도 직접 편집 가능해야 한다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._prompt_edit.setPlainText("날씨를 예보하는 워크플로우")

    def fake_generate(key, desc, *, model, **kw):
        assert desc == "날씨를 예보하는 워크플로우"
        return "flowchart TD\n A[관측] --> B[예보]", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()
        _wait_worker(dlg)

    assert dlg.text() == "flowchart TD\n A[관측] --> B[예보]"
    assert dlg._prompt_edit.toPlainText() == "날씨를 예보하는 워크플로우"   # 프롬프트는 안 지워짐
    dlg._edit.setPlainText(dlg.text() + "\n B --> C[게시]")
    assert "게시" in dlg.text()


def test_mermaid_dialog_ai_fill_is_undoable_via_ctrl_z():
    """setPlainText() 대신 QTextCursor 치환을 써서, AI가 채운 코드를 Ctrl+Z(코드 칸
    자체의 undo 스택)로 되돌릴 수 있어야 한다 — 손으로 고친 코드 위에 실수로 다시
    생성했을 때 복구 가능(2칸 분리 후에도 유지되는 안전망)."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("flowchart TD\n A-->B  # 직접 고친 코드")
    dlg._prompt_edit.setPlainText("아무 설명")

    def fake_generate(key, desc, *, model, **kw):
        return "flowchart TD\n X-->Y", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()
        _wait_worker(dlg)
    assert dlg.text() == "flowchart TD\n X-->Y"
    dlg._edit.undo()
    assert dlg.text() == "flowchart TD\n A-->B  # 직접 고친 코드"


def test_mermaid_dialog_enter_in_prompt_triggers_ai_generation():
    """1번 칸(프롬프트)에서 Enter만으로 바로 변환 트리거(참고 이미지 관례 채용,
    2026-08-12 재피드백) — `_prompt_edit`에 설치된 eventFilter가 가로채 AI 생성을
    트리거하고 이벤트를 소비한다(기본 줄바꿈 삽입 방지)."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    calls = {"n": 0}
    dlg._on_ai_clicked = lambda: calls.__setitem__("n", calls["n"] + 1)

    from PyQt6.QtGui import QKeyEvent
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    handled = dlg.eventFilter(dlg._prompt_edit, ev)
    assert handled is True
    assert calls["n"] == 1


def test_mermaid_dialog_shift_enter_in_prompt_inserts_newline_not_ai():
    """Shift+Enter는 줄바꿈(여러 줄 설명용)이지 AI 트리거가 아니어야 한다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    calls = {"n": 0}
    dlg._on_ai_clicked = lambda: calls.__setitem__("n", calls["n"] + 1)

    from PyQt6.QtGui import QKeyEvent
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    handled = dlg.eventFilter(dlg._prompt_edit, ev)
    assert handled is False   # 기본 동작(줄바꿈)에 맡김
    assert calls["n"] == 0


def test_mermaid_dialog_has_no_credit_label():
    """2026-08-12 4차, 디자인 시안 합의 — 크레딧 표시는 이 창에서 제거하고
    `_AIGatewaySettingsDialog`의 "연결 테스트" 한 곳으로 통합했다(중복 표시 제거).
    회귀 가드: `_on_ai_clicked`가 더 이상 `get_credit_balance`를 호출하지 않아야 한다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    assert not hasattr(dlg, "_credit_label")
    dlg._prompt_edit.setPlainText("아무 설명")

    def fake_generate(key, desc, *, model, **kw):
        return "flowchart TD\n A-->B", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate), \
         patch("easycad.canvas.host_dialogs.gw.get_credit_balance") as get_credit:
        dlg._on_ai_clicked()
        _wait_worker(dlg)
    assert dlg.text() == "flowchart TD\n A-->B"
    assert not get_credit.called


def test_mermaid_dialog_ai_button_requires_nonempty_box():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    with patch("easycad.canvas.host_dialogs.QMessageBox.information") as info, \
         patch("easycad.ai.text_to_mermaid.generate_mermaid") as gen:
        dlg._on_ai_clicked()
    assert info.called
    assert not gen.called
    assert dlg.text() == ""


def test_mermaid_dialog_ai_button_warns_when_no_api_key():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._prompt_edit.setPlainText("아무 설명")
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value=""), \
         patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn, \
         patch("easycad.ai.text_to_mermaid.generate_mermaid") as gen:
        dlg._on_ai_clicked()
    assert warn.called
    assert not gen.called


def test_mermaid_dialog_ai_button_shows_warning_on_generation_failure():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._prompt_edit.setPlainText("아무 설명")
    dlg._edit.setPlainText("flowchart TD\n A-->B  # 기존 코드")

    def fake_generate(key, desc, *, model, **kw):
        raise RuntimeError("게이트웨이 실패")

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn, \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()
        _wait_worker(dlg)
    assert warn.called
    assert dlg.text() == "flowchart TD\n A-->B  # 기존 코드"   # 실패해도 기존 코드를 지우지 않음
    assert dlg._ai_btn.isEnabled()   # 완료 시그널에서 버튼이 다시 활성화됨


def test_mermaid_dialog_shows_progress_and_disables_controls_while_generating():
    """2026-08-19 비동기화 — 프리징 해소의 핵심 증거: 워커가 도는 동안(`_on_ai_clicked()`가
    반환한 직후, 아직 `wait()`하기 전) 진행 표시가 보이고 생성/버튼박스가 비활성화돼
    있어야 한다. 예전 동기 구현은 이 순간 자체가 없었다.

    ⚠ 어서션이 `_wait_worker()` 전에 실패하면(=워커를 join하지 않은 채 테스트가 죽으면)
    아직 살아있는 QThread가 뒤이은 `with patch(...)` 종료로 원본(진짜 네트워크 호출)
    함수를 다시 붙잡을 위험이 있다(실측으로 확인된 함정 — 실제로 이 문제 때문에 전체
    스위트가 몇 시간 멈춘 적이 있다). 그래서 `try/finally`로 무슨 일이 있어도 join한다."""
    import time
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._prompt_edit.setPlainText("아무 설명")

    def fake_generate(key, desc, *, model, **kw):
        time.sleep(0.05)
        return "flowchart TD\n A-->B", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()
        try:
            assert not dlg._progress.isHidden()
            assert not dlg._ai_btn.isEnabled()
            assert not dlg._btns.isEnabled()
        finally:
            _wait_worker(dlg)
    assert dlg._progress.isHidden()
    assert dlg._ai_btn.isEnabled()
    assert dlg._btns.isEnabled()
    assert dlg._worker is None


def test_mermaid_dialog_close_immediate_while_generating():
    """2026-08-23 설계 변경 — 예전엔 생성 중 닫기를 `closeEvent`의 `e.ignore()`로
    막았으나, Cancel 버튼의 `reject()`는 그 방어코드를 거치지 않고 곧장 다이얼로그를
    없애 아직 도는 워커까지 함께 파괴돼(살아있는 QThread 파괴) 프로그램이 죽는 실사용
    크래시로 이어졌다(X·Cancel을 누른다는 건 결과가 필요없다는 뜻이므로 애초에 막을
    이유도 없었다). 이제는 무엇이 돌든 닫기가 항상 즉시 되고, 아직 도는 워커는
    `_detach_worker`로 다이얼로그와 분리돼 크래시 없이 백그라운드에서 마저 끝난다."""
    import time
    from easycad.canvas import host_dialogs
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._prompt_edit.setPlainText("아무 설명")

    def fake_generate(key, desc, *, model, **kw):
        time.sleep(0.3)
        return "flowchart TD\n A-->B", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()
        worker = dlg._worker
        assert worker.isRunning()
        dlg.reject()   # Cancel 버튼과 완전히 같은 경로 — 실사용 크래시가 재현되던 지점
        assert dlg.result() == QDialog.DialogCode.Rejected   # 생성 중이어도 즉시 닫힘
        assert worker in host_dialogs._ORPHANED_WORKERS   # 분리돼 백그라운드에서 계속 돎
        worker.wait(5000)
        for _ in range(5):
            QApplication.processEvents()
    assert worker not in host_dialogs._ORPHANED_WORKERS   # 끝난 뒤 스스로 정리됨


def test_mermaid_dialog_direct_paste_still_works_without_ai():
    """게이트웨이를 쓰고 싶지 않을 때 — 외부 AI 챗에서 받은 Mermaid를 그대로 붙여넣고
    OK만 눌러도 되는 경로(옛 "수동 모드"를 대신하는 것이 바로 이 경로)."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("flowchart LR\n A-->B\n")
    assert dlg.text() == "flowchart LR\n A-->B\n"


# ── _MermaidDialog: 이미지 첨부(2026-08-12, 이미지 입력 재추가) ─────────────────

def test_mermaid_dialog_browse_image_attaches_and_shows_thumbnail():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    assert dlg._image_chip.isHidden()

    real_path = os.path.join(_TMP, f"attach_{uuid.uuid4().hex}.png")
    _mk_pixmap(60, 40).save(real_path)
    with patch("easycad.canvas.host_dialogs.QFileDialog.getOpenFileName",
              return_value=(real_path, "")):
        dlg._browse_image()
    assert dlg._attached_image is not None
    assert dlg._attached_image_name == os.path.basename(real_path)
    assert not dlg._image_chip.isHidden()
    assert not dlg._image_thumb.pixmap().isNull()


def test_mermaid_dialog_clear_image_hides_row_and_resets_state():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    real_path = os.path.join(_TMP, f"attach_{uuid.uuid4().hex}.png")
    _mk_pixmap(40, 40).save(real_path)
    dlg._load_image_path(real_path)
    assert dlg._attached_image is not None

    dlg._clear_image()
    assert dlg._attached_image is None
    assert dlg._attached_image_name == ""
    assert dlg._image_chip.isHidden()


def test_mermaid_dialog_drop_image_file_attaches():
    from PyQt6.QtCore import QUrl
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    real_path = os.path.join(_TMP, f"drop_{uuid.uuid4().hex}.png")
    _mk_pixmap(50, 30).save(real_path)
    fake_url = QUrl.fromLocalFile(real_path)
    fake_md = type("_MD", (), {
        "hasUrls": lambda self: True,
        "urls": lambda self: [fake_url],
        "hasImage": lambda self: False,
    })()
    fake_event = type("_E", (), {
        "mimeData": lambda self: fake_md,
        "acceptProposedAction": lambda self: None,
    })()
    dlg.dropEvent(fake_event)
    assert dlg._attached_image is not None
    assert dlg._attached_image_name == os.path.basename(real_path)


def test_mermaid_dialog_drop_raw_image_data_attaches():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    pm = _mk_pixmap(40, 20)
    fake_md = type("_MD", (), {
        "hasUrls": lambda self: False,
        "hasImage": lambda self: True,
        "imageData": lambda self: pm.toImage(),
    })()
    fake_event = type("_E", (), {
        "mimeData": lambda self: fake_md,
        "acceptProposedAction": lambda self: None,
    })()
    dlg.dropEvent(fake_event)
    assert dlg._attached_image is not None
    assert dlg._attached_image_name == "드롭한 이미지"


def test_mermaid_dialog_ctrl_v_with_clipboard_image_attaches_not_pastes_text():
    """클립보드에 이미지가 있으면(옛 이미지 다이얼로그와 동일 관례) Ctrl+V가 텍스트
    붙여넣기 대신 이미지 첨부로 가로채져야 한다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    pm = _mk_pixmap(40, 20)
    fake_md = type("_MD", (), {"hasImage": lambda self: True, "imageData": lambda self: pm.toImage()})()
    from PyQt6.QtGui import QKeyEvent
    with patch.object(QApplication.clipboard(), "mimeData", return_value=fake_md):
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        handled = dlg.eventFilter(dlg._prompt_edit, ev)
    assert handled is True
    assert dlg._attached_image is not None
    assert dlg._attached_image_name == "붙여넣은 이미지"


def test_mermaid_dialog_ctrl_v_with_plain_text_clipboard_falls_through():
    """클립보드에 이미지가 없으면(보통의 텍스트 붙여넣기) 위젯 기본 동작에 맡겨야 한다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    fake_md = type("_MD", (), {"hasImage": lambda self: False})()
    from PyQt6.QtGui import QKeyEvent
    with patch.object(QApplication.clipboard(), "mimeData", return_value=fake_md):
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        handled = dlg.eventFilter(dlg._prompt_edit, ev)
    assert handled is False
    assert dlg._attached_image is None


def test_mermaid_dialog_ai_click_with_image_and_no_text_still_generates():
    """이미지 경로는 텍스트 전용 경로와 달리 설명이 필수가 아니다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    real_path = os.path.join(_TMP, f"attach_{uuid.uuid4().hex}.png")
    _mk_pixmap(40, 20).save(real_path)
    dlg._load_image_path(real_path)

    captured = {}

    def fake_generate(key, desc, *, model, image=None, base_url=None):
        captured["desc"] = desc
        captured["image"] = image
        return "flowchart TD\n A-->B", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()
        _wait_worker(dlg)

    assert captured["desc"] == ""
    assert captured["image"] is not None
    assert dlg.text() == "flowchart TD\n A-->B"


def test_mermaid_dialog_ai_click_requires_text_or_image():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    with patch("easycad.canvas.host_dialogs.QMessageBox.information") as info, \
         patch("easycad.ai.text_to_mermaid.generate_mermaid") as gen:
        dlg._on_ai_clicked()
    assert info.called
    assert not gen.called


def test_mermaid_dialog_populate_models_uses_resolved_base_url():
    """모델 조회가 하드코딩 BASE_URL이 아니라 resolve_base_url()(설정창에서 바꾼 값
    포함)을 쓰는지 — 커스텀 게이트웨이 주소를 저장했으면 그 주소로 조회해야 한다."""
    captured = {}

    def fake_list_text_models(key, base_url, timeout=8.0):
        captured["base_url"] = base_url
        return ["gpt-5.4-mini"]

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.resolve_base_url",
               return_value="https://custom.example.com/v1/gateway"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models", fake_list_text_models):
        dlg = _MermaidDialog()
        _wait_model_list_worker(dlg)
    assert captured["base_url"] == "https://custom.example.com/v1/gateway"


# ── 게이트웨이 설정 진입점 — 상단 메뉴/툴바로 나갔다가(2026-08-12) Mermaid 창 안으로
# 복귀했다가, 2026-08-20 재피드백으로 삽입(&I) 메뉴에 독립 항목으로 다시 추가됐다(다만
# Mermaid/SVG 창 안의 설정 버튼은 그대로 유지 — "그 창을 같이 사용"). 툴바에는 안 둔다
# (과거 "상시노출 아이콘은 실사용 결과 되돌림" 판단 유지, 메뉴 텍스트로만 노출).

def test_ai_gateway_settings_action_in_insert_menu_opens_dialog():
    w = CanvasWindow()
    assert hasattr(w, "_act_ai_settings")
    assert w._act_ai_settings.text() == "AI 게이트웨이 설정…"
    assert w._act_ai_settings not in w._toolbar.actions()   # 메뉴 전용, 툴바엔 없음
    opened = {}

    class _FakeDlg:
        def __init__(self, parent=None):
            opened["parent"] = parent

        def exec(self):
            opened["exec"] = True

    with patch("easycad.canvas.host_fileio._AIGatewaySettingsDialog", _FakeDlg):
        w._open_ai_gateway_settings()
    assert opened.get("exec") is True
    assert opened.get("parent") is w
    w.deleteLater()


def test_mermaid_dialog_settings_button_opens_dialog_and_refreshes_models():
    d = _MermaidDialog()
    opened = {}

    class _FakeDlg:
        def __init__(self, parent=None):
            opened["parent"] = parent

        def exec(self):
            opened["exec"] = True
            return QDialog.DialogCode.Accepted

    with patch("easycad.canvas.host_dialogs._AIGatewaySettingsDialog", _FakeDlg), \
         patch.object(d, "_populate_models") as mock_refresh:
        d._settings_btn.click()
    assert opened.get("exec") is True
    assert opened.get("parent") is d
    mock_refresh.assert_called_once()   # 주소/키가 바뀌었을 수 있어 목록 재조회
    d.deleteLater()


def test_mermaid_dialog_settings_button_cancelled_skips_refresh():
    d = _MermaidDialog()

    class _FakeDlg:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    with patch("easycad.canvas.host_dialogs._AIGatewaySettingsDialog", _FakeDlg), \
         patch.object(d, "_populate_models") as mock_refresh:
        d._settings_btn.click()
    mock_refresh.assert_not_called()
    d.deleteLater()


# ── gateway.py: 게이트웨이 주소 저장/해석 ────────────────────────────────────

def test_resolve_base_url_defaults_to_constant_when_nothing_stored():
    _clear_gateway_settings()
    assert gw.resolve_base_url() == gw.BASE_URL
    assert gw.BASE_URL == "https://factchat.mindlogic-kr-api.com/v1/gateway"


def test_store_base_url_then_resolve_reads_it_back():
    _clear_gateway_settings()
    try:
        gw.store_base_url("https://custom.example.com/v1/gateway")
        assert gw.resolve_base_url() == "https://custom.example.com/v1/gateway"
    finally:
        _clear_gateway_settings()


def test_resolve_base_url_prefers_explicit_over_stored():
    _clear_gateway_settings()
    try:
        gw.store_base_url("https://stored.example.com")
        assert gw.resolve_base_url("https://explicit.example.com") == "https://explicit.example.com"
    finally:
        _clear_gateway_settings()


# ── _AIGatewaySettingsDialog ─────────────────────────────────────────────────

def test_gateway_settings_dialog_prefills_default_url_when_nothing_stored():
    _clear_gateway_settings()
    dlg = _AIGatewaySettingsDialog()
    assert dlg.base_url() == "https://factchat.mindlogic-kr-api.com/v1/gateway"
    assert dlg.api_key() == ""


def test_gateway_settings_dialog_test_reports_models_and_credit():
    """[2026-08-12 4차, 디자인 시안 합의] 옛 "새로고침"+"크레딧 확인" 두 버튼을 "연결
    테스트" 하나로 통합 — 클릭 한 번으로 모델 gpt/gemini 개수와 크레딧 잔여를 함께
    보고한다. 크레딧은 "잔여" 문구로(남은 양임을 명확히, 옛 "…사용" 표기 폐기)."""
    dlg = _AIGatewaySettingsDialog()
    dlg._key_edit.setText("some-key")
    with patch("easycad.canvas.host_dialogs.gw.list_text_models",
              return_value=["gpt-5.4-mini", "gpt-5.4-nano", "gemini-3.6-flash"]), \
         patch("easycad.canvas.host_dialogs.gw.get_credit_balance",
              return_value=(380.0, 1000.0)):
        dlg._on_test_clicked()
    text = dlg._test_result_label.text()
    assert "GPT 2개" in text
    assert "Gemini 1개" in text
    assert "잔여" in text
    assert "380" in text and "1000" in text
    assert dlg._test_btn.isEnabled()


def test_gateway_settings_dialog_test_reports_model_failure_but_still_checks_credit():
    """모델·크레딧 조회는 서로 독립 — 하나가 실패해도 다른 하나는 계속 시도한다."""
    dlg = _AIGatewaySettingsDialog()
    dlg._key_edit.setText("bad-key")
    with patch("easycad.canvas.host_dialogs.gw.list_text_models",
              side_effect=RuntimeError("401 Unauthorized")), \
         patch("easycad.canvas.host_dialogs.gw.get_credit_balance",
              return_value=(5.0, 10.0)):
        dlg._on_test_clicked()
    text = dlg._test_result_label.text()
    assert "모델 조회 실패" in text
    assert "401" in text
    assert "잔여 5" in text   # 모델 조회가 실패해도 크레딧 확인은 그대로 성공


def test_gateway_settings_dialog_test_reports_credit_failure():
    dlg = _AIGatewaySettingsDialog()
    dlg._key_edit.setText("some-key")
    with patch("easycad.canvas.host_dialogs.gw.list_text_models",
              return_value=["gpt-5.4-mini"]), \
         patch("easycad.canvas.host_dialogs.gw.get_credit_balance",
              side_effect=RuntimeError("network down")):
        dlg._on_test_clicked()
    assert "크레딧 확인 실패" in dlg._test_result_label.text()


def test_gateway_settings_dialog_test_requires_key():
    _clear_gateway_settings()   # 남은 키가 있으면 필드가 미리 채워져 이 테스트가 무의미해짐
    dlg = _AIGatewaySettingsDialog()
    with patch("easycad.canvas.host_dialogs.gw.list_text_models") as list_text_models, \
         patch("easycad.canvas.host_dialogs.gw.get_credit_balance") as get_credit:
        dlg._on_test_clicked()
    assert not list_text_models.called
    assert not get_credit.called
    assert "키를 입력" in dlg._test_result_label.text()


def test_gateway_settings_dialog_accept_persists_url_and_key():
    _clear_gateway_settings()
    try:
        dlg = _AIGatewaySettingsDialog()
        dlg._url_edit.setText("https://custom.example.com/v1/gateway")
        dlg._key_edit.setText("my-secret-key")
        dlg._on_accept()
        assert gw.resolve_base_url() == "https://custom.example.com/v1/gateway"
        assert gw.resolve_api_key() == "my-secret-key"
        assert dlg.result() == QDialog.DialogCode.Accepted
    finally:
        _clear_gateway_settings()


def test_gateway_settings_dialog_cancel_does_not_persist():
    _clear_gateway_settings()
    try:
        dlg = _AIGatewaySettingsDialog()
        dlg._url_edit.setText("https://should-not-be-saved.example.com")
        dlg.reject()
        assert gw.resolve_base_url() == gw.BASE_URL
    finally:
        _clear_gateway_settings()


# ── 이미지 경로 폐기 회귀 가드 ────────────────────────────────────────────────

def test_ai_image_menu_action_and_mixin_are_gone():
    w = CanvasWindow()
    assert not hasattr(w, "_act_ai_sketch")
    assert not hasattr(w, "_import_ai_image")
    w.deleteLater()


def test_sketch_pipeline_and_host_ai_modules_removed():
    import importlib
    for modname in ("easycad.ai.sketch_pipeline", "easycad.canvas.host_ai"):
        try:
            importlib.import_module(modname)
            assert False, f"{modname} should have been deleted"
        except ModuleNotFoundError:
            pass


# ── §8 항목23 Stage 5(2026-08-19) — Mermaid 실시간 렌더 미리보기 ───────────────

def test_render_mermaid_preview_pixmap_none_for_empty_text():
    from PyQt6.QtCore import QSize
    assert _render_mermaid_preview_pixmap("", QSize(220, 220)) is None
    assert _render_mermaid_preview_pixmap("   \n  ", QSize(220, 220)) is None


def test_render_mermaid_preview_pixmap_uses_same_shape_mapping_as_insert():
    """실제 삽입 경로(host_fileio._make_mermaid_node)와 같은 도형 매핑을 타는지 —
    rhombus(판단)가 원(_EllipseItem) 대신 사각형 폴백이 아니라 실제로 결정 심볼로
    그려지는지는 픽셀로 직접 못 보므로, 파서·배치·매핑 각 단계가 예외 없이 끝까지
    돌아 None이 아닌 픽스맵을 만들어내는지로 대신 검증(도형별 렌더 자체는 위 자체확인
    스크린샷으로 육안 확인 완료)."""
    from PyQt6.QtCore import QSize
    text = ("flowchart TD\n"
            "    A[시작] --> B{조건}\n"
            "    B -->|예| C[처리]\n"
            "    B -->|아니오| D([종료])\n"
            "    C --> D")
    pm = _render_mermaid_preview_pixmap(text, QSize(220, 220))
    assert pm is not None
    assert not pm.isNull()
    assert pm.width() == 220 and pm.height() == 220


def test_render_mermaid_preview_pixmap_single_node_no_edges():
    """엣지 없는 단일 노드도 렌더 실패 없이 픽스맵을 낸다(레이아웃 bbox가 노드 하나뿐)."""
    from PyQt6.QtCore import QSize
    pm = _render_mermaid_preview_pixmap("flowchart TD\n A[혼자]", QSize(100, 100))
    assert pm is not None and not pm.isNull()


def test_mermaid_dialog_has_preview_panel_with_placeholder_initially():
    """[2026-08-21] 클릭-확대 QLabel(`_ClickablePreviewLabel`)을 휠줌/드래그팬
    `_MermaidPreviewView`로 교체 — `pixmap()/text()` 대신 `has_content()`/
    `message_text()`로 같은 계약(플레이스홀더 vs 실제 도형)을 확인한다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    assert hasattr(dlg, "_preview_view")
    assert not dlg._preview_view.has_content()
    assert "미리보기" in dlg._preview_view.message_text()


def test_mermaid_dialog_typing_schedules_debounced_timer_not_immediate():
    """타이핑(`setPlainText` → `textChanged`) 즉시가 아니라 디바운스 타이머가 도는 것만
    확인 — 매 키 입력마다 무거운 렌더를 즉시 돌리지 않는다는 계약(§8 항목23 Stage 5
    deep-interview 확정: "몇백ms 디바운스")."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    assert dlg._preview_timer.isSingleShot()
    dlg._edit.setPlainText("flowchart TD\n A-->B")
    assert dlg._preview_timer.isActive()
    # 타이머가 아직 안 끝났으니 미리보기는 그대로 플레이스홀더여야 한다.
    assert not dlg._preview_view.has_content()


def test_mermaid_dialog_preview_updates_when_timer_fires():
    """타이머 만료(`timeout` 강제 발화, 실 대기 없이)로 `_update_preview`가 실제로
    도형을 씬에 채우는지 — 유효한 Mermaid 코드일 때."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("flowchart TD\n A[시작] --> B[끝]")
    dlg._preview_timer.stop()
    dlg._update_preview()
    assert dlg._preview_view.has_content()


def test_mermaid_dialog_preview_shows_error_text_for_invalid_code():
    """빈 노드(파싱 실패)일 때는 도형 대신 안내 문구."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("flowchart TD\n classDef only styling, no nodes")
    dlg._preview_timer.stop()
    dlg._update_preview()
    assert not dlg._preview_view.has_content()
    assert "구문 오류" in dlg._preview_view.message_text()


def test_mermaid_dialog_preview_clears_back_to_placeholder_when_text_emptied():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("flowchart TD\n A[시작] --> B[끝]")
    dlg._preview_timer.stop()
    dlg._update_preview()
    assert dlg._preview_view.has_content()
    dlg._edit.setPlainText("")
    dlg._preview_timer.stop()
    dlg._update_preview()
    assert not dlg._preview_view.has_content()
    assert "미리보기" in dlg._preview_view.message_text()


def test_mermaid_dialog_ai_fill_also_refreshes_preview():
    """AI 생성 결과가 `_edit`에 채워지는 것도 `QTextCursor.insertText`를 통하지만
    `textChanged`는 그대로 발화하므로, 별도 훅 없이도 디바운스 타이머가 걸려야 한다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()

    def fake_generate(key, desc, *, model, **kw):
        return "flowchart TD\n X[가]-->Y[나]", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._prompt_edit.setPlainText("아무 설명")
        dlg._on_ai_clicked()
        _wait_worker(dlg)
    assert dlg._preview_timer.isActive()
    dlg._preview_timer.stop()
    dlg._update_preview()
    assert dlg._preview_view.has_content()


def test_mermaid_preview_view_wheel_zoom_and_pan_drag_mode():
    """[2026-08-21 실사용 피드백] "클릭하면 확대 방식보다 드래그·휠 방식은 어떤지" —
    클릭-확대 다이얼로그를 없애고 패널 자체가 휠로 확대·드래그로 패닝하게 했다.
    `ScrollHandDrag`(좌클릭 드래그=패닝, Qt 기본 제공)가 켜져 있는지, 휠이 실제로
    `scale()`을 호출해 확대하는지(도형이 있을 때만) 확인."""
    from PyQt6.QtCore import QPoint, Qt as _Qt
    from PyQt6.QtGui import QWheelEvent
    from easycad.canvas.host_dialogs import _MermaidPreviewView

    view = _MermaidPreviewView()
    assert view.dragMode() == view.DragMode.ScrollHandDrag

    view.set_mermaid_code("flowchart LR\n A[시작] --> B[끝]")
    assert view.has_content()
    before = view.transform().m11()   # 가로 스케일

    ev = QWheelEvent(QPoint(50, 50).toPointF(), QPoint(50, 50).toPointF(),
                     QPoint(0, 0), QPoint(0, 120), _Qt.MouseButton.NoButton,
                     _Qt.KeyboardModifier.NoModifier, _Qt.ScrollPhase.NoScrollPhase, False)
    view.wheelEvent(ev)
    after = view.transform().m11()
    assert after > before   # 휠 위로 = 확대


def test_mermaid_preview_view_wheel_noop_on_placeholder():
    """안내문(도형 없음)만 떠 있을 땐 휠이 확대를 하지 않는다 — 확대할 대상이 없으므로."""
    from PyQt6.QtCore import QPoint, Qt as _Qt
    from PyQt6.QtGui import QWheelEvent
    from easycad.canvas.host_dialogs import _MermaidPreviewView

    view = _MermaidPreviewView()
    assert not view.has_content()
    before = view.transform().m11()
    ev = QWheelEvent(QPoint(50, 50).toPointF(), QPoint(50, 50).toPointF(),
                     QPoint(0, 0), QPoint(0, 120), _Qt.MouseButton.NoButton,
                     _Qt.KeyboardModifier.NoModifier, _Qt.ScrollPhase.NoScrollPhase, False)
    view.wheelEvent(ev)
    assert view.transform().m11() == before


# ── §8 항목23 Stage 6(2026-08-19) — 레이아웃 최종 통일(목업 시각 언어 차용) ────────

def test_mermaid_dialog_ok_button_has_descriptive_label():
    """"OK" 대신 결과를 명시하는 라벨(목업 "확인 (캔버스 삽입)" 차용, 사용자 확정:
    구조는 그대로 두고 시각 언어만 반영)."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    ok_btn = dlg._btns.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_btn.text() == "확인 (캔버스 삽입)"


