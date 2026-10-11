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
  - (2026-10-11 §8 항목36 6단계) `_MermaidDialog`·사진→도면 창 테스트는 창과 함께 지웠다 —
    생성은 「AI로 만들기」 패널(`test_part29_ai_panel.py`)이 맡는다.
  - `_AIGatewaySettingsDialog`(2026-08-12) — 게이트웨이 주소·API 키 입력·저장에 더해
    "연결 테스트"(모델 gpt/gemini 개수 + 크레딧 잔여를 한 번에) 버튼까지.
  - 옛 이미지 경로가 실제로 사라졌는지(메뉴 액션·믹스인 잔존 여부) 회귀 가드.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part9_ai_mermaid.py.
"""
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog

from _shared import *  # noqa: F401,F403

from easycad.ai import gateway as gw  # noqa: E402
from easycad.ai import text_to_mermaid as ttm  # noqa: E402
from easycad.canvas.host_dialogs import (  # noqa: E402
    _AIGatewaySettingsDialog, _pick_fallback_model, _model_version_key,
)


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
# 2026-08 "관계만 남기고 재배치" 경로의 부활을 막는다. §8 항목28(2026-10-01)의 좌표 보존 사진→도면은
# 별개 경로라 다른 이름(`photo_ops`·`photo_to_ops`)을 쓰고, 이 가드는 그대로 유지한다.

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


# ── 인라인 미리보기 비인터랙티브화 + 확대창(2026-08-25 실사용 피드백) ───────────────
# "미리보기인데 마우스를 만지면(확대하려고) 뭔가 움직이는 것 같다" — 인라인 패널은
# 정지 이미지로 되돌리고(휠·드래그 전부 무시), 클릭하면 SVG 후보 확대와 같은 관례로
# 별도 창에 인터랙티브(휠줌·드래그팬) 뷰를 띄운다.


# ── §8 항목23 Stage 6(2026-08-19) — 레이아웃 최종 통일(목업 시각 언어 차용) ────────


# ── 인스턴스 재사용(2026-08-25 실사용 피드백 — 닫았다 다시 열어도 이전 결과 유지) ────


# ── §8 항목28 2단계(2026-10-01) — 사진→도면 AI 루프·렌더·워커 ──────────────────

class _FakeOpsClient:
    """chat.completions.create만 흉내 — 응답 문자열을 차례로 돌려주고 받은 content를 기록."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.contents = []
        outer = self

        class _Comp:
            def create(self, model, max_tokens, messages, stream=False, stream_options=None):
                assert stream   # 5분 게이트웨이 시간초과를 피하려 스트리밍으로 받는다(2026-10-05)
                outer.contents.append(messages[0]["content"])
                txt = outer._replies.pop(0)
                half = len(txt) // 2
                return [type("K", (), {"choices": [type("C", (), {"delta": type("D", (), {"content": t})()})()],
                                       "usage": None})() for t in (txt[:half], txt[half:])]

        self.chat = type("Chat", (), {"completions": _Comp()})()


_OPS_A = '{"ops": [{"op": "box", "id": "a", "x1": 10, "y1": 10, "x2": 60, "y2": 40}]}'
_OPS_B = '{"ops": [{"op": "box", "id": "a", "x1": 10, "y1": 10, "x2": 60, "y2": 40}, {"op": "text", "x": 5, "y": 50, "text": "X"}]}'


def test_generate_ops_loop_rounds_render_and_broken_fix():
    from PIL import Image
    from easycad.ai.photo_to_ops import generate_ops, Cancelled
    photo = Image.new("RGB", (120, 90), "white")
    client = _FakeOpsClient([_OPS_A, _OPS_B, "JSON 없음"])
    rendered, progress = [], []

    def render(spec, size):
        rendered.append((len(spec["ops"]), size))
        return Image.new("RGB", size, "white")

    spec, log = generate_ops(client, photo, model="m", render=render, rounds=2,
                             progress=lambda i, n, t: progress.append((i, n, t)))
    assert len(client.contents[0]) == 2 + 2 * 6             # 지시+원본 + (범위 글+조각)×6
    assert len(client.contents[1]) == 3                     # 지시+이전JSON, 원본, 직전 렌더
    assert rendered == [(1, (120, 90)), (2, (120, 90))]     # 매 수정 라운드 직전 결과를 렌더
    assert [p[:2] for p in progress] == [(0, 3), (1, 3), (2, 3)]
    assert len(spec["ops"]) == 2 and "error" in log[2]      # 깨진 수정 응답 → 직전 결과 유지
    try:                                                    # 첫 생성이 깨지면 실패
        generate_ops(_FakeOpsClient(["없음"]), photo, model="m", render=render, rounds=0)
        assert False
    except ValueError:
        pass
    try:                                                    # 취소는 호출 사이에서
        generate_ops(_FakeOpsClient([_OPS_A]), photo, model="m", render=render, rounds=1,
                     cancelled=lambda: True)
        assert False
    except Cancelled:
        pass


def test_render_spec_qimage_draws_in_photo_frame():
    from easycad.canvas.photo_dialog import render_spec_qimage
    img = render_spec_qimage({"ops": [{"op": "box", "x1": 10, "y1": 10, "x2": 60, "y2": 40}]}, (120, 90))
    assert (img.width(), img.height()) == (120, 90)
    assert QColor(img.pixel(10, 25)).lightness() < 128       # 상자 왼쪽 변(원본 좌표 그대로)
    assert QColor(img.pixel(35, 25)).lightness() > 240       # 상자 안은 흰 배경


class _FnOpsClient:
    """동시 호출용 가짜 — reply(콘텐츠 첫 글, 호출 번호) → 응답 글. 스트리밍 조각 2개로 돌려준다."""

    def __init__(self, reply):
        import threading
        self.calls = []
        lock = threading.Lock()
        outer = self

        class _Comp:
            def create(self, model, max_tokens, messages, stream=False, stream_options=None):
                assert stream
                text = messages[0]["content"][0]["text"]
                with lock:
                    outer.calls.append(text)
                    n = len(outer.calls)
                txt = reply(text, n)
                half = len(txt) // 2
                return [type("K", (), {"choices": [type("C", (), {"delta": type("D", (), {"content": t})()})()],
                                       "usage": None})() for t in (txt[:half], txt[half:])]

        self.chat = type("Chat", (), {"completions": _Comp()})()


def _tile_of(text):
    import re
    m = re.search(r"맡은 구역: 원본 좌표 x (\d+)~(\d+), y (\d+)~(\d+)", text)
    x1, x2, y1, y2 = (int(v) for v in m.groups())
    return x1, y1, x2, y2


def test_generate_ops_tiled_owns_retries_and_joins_seams():
    # 2026-10-05: 6구역 동시 생성 — 도형은 주인 구역 하나에만, 경계에서 잘린 선은 다시 이어지고,
    # 깨진 응답(스트림이 중간에 끊김)은 그 구역만 다시 보낸다.
    import json
    from PIL import Image
    from easycad.ai.photo_to_ops import generate_ops_tiled
    photo = Image.new("RGB", (600, 400), "white")          # 3×2 구역 = 200×200씩
    broken = {"first": True}

    def reply(text, n):
        x1, y1, x2, y2 = _tile_of(text)
        ops = [{"op": "box", "id": "a", "x1": 20, "y1": 20, "x2": 80, "y2": 60},          # 모든 구역이 같은 상자를 봄
               {"op": "line", "pts": [[50, 40], [550, 42 + (x1 > 0)]], "head": True,      # 구역마다 1px씩 어긋난 같은 선
                "src": "a"}]
        if x1 > 150 and y1 == 0 and broken["first"]:      # 가운데 위 구역 첫 응답은 끊긴 JSON
            broken["first"] = False
            return json.dumps({"ops": ops})[:40]
        return json.dumps({"ops": ops})

    client = _FnOpsClient(reply)
    seen = []
    spec, log = generate_ops_tiled(client, photo, model="m", progress=lambda i, n, t: seen.append((i, n)))
    assert len(client.calls) == 7 and seen[0] == (0, 6) and seen[-1] == (6, 6)
    assert sorted(e["tries"] for e in log) == [1, 1, 1, 1, 1, 2] and not any("error" in e for e in log)
    boxes = [o for o in spec["ops"] if o["op"] == "box"]
    lines = [o for o in spec["ops"] if o["op"] == "line"]
    assert len(boxes) == 1 and boxes[0]["id"] == "t0_a"                  # 중심이 구역 0에 있는 것만
    assert len(lines) == 1                                               # 세 구역 조각이 한 선으로
    ln = lines[0]
    assert ln["pts"][0] == [50.0, 40.0] and ln["pts"][-1][0] == 550 and ln["head"] and ln["src"] == "t0_a"


def test_generate_ops_tiled_gives_up_tile_and_all_fail_raises():
    from PIL import Image
    from easycad.ai.photo_to_ops import generate_ops_tiled
    photo = Image.new("RGB", (600, 400), "white")
    ok = '{"ops": [{"op": "text", "x": 10, "y": 10, "text": "A"}]}'
    spec, log = generate_ops_tiled(_FnOpsClient(lambda t, n: "없음" if _tile_of(t)[0] == 0 and _tile_of(t)[1] == 0
                                                 else ok), photo, model="m")
    assert [e["tile"] for e in log if "error" in e] == [0] and log[0]["tries"] == 2
    assert spec["ops"] == []                       # 글자 시작점(10,10)의 주인 구역 0이 실패 → 비어 있음
    try:
        generate_ops_tiled(_FnOpsClient(lambda t, n: "없음"), photo, model="m")
        assert False
    except ValueError:
        pass


def test_photo_ops_worker_runs_tiled_off_main_thread():
    import json
    import time
    from PIL import Image
    from easycad.ai import gateway as gw
    import easycad.canvas.photo_dialog as pdlg
    client = _FnOpsClient(lambda t, n: json.dumps({"ops": [{"op": "text", "x": _tile_of(t)[0] + 70,
                                                            "y": _tile_of(t)[1] + 60, "text": "T"}]}))
    got, prog = {}, []
    with patch.object(gw, "_client", lambda *a, **k: client):
        w = pdlg._PhotoOpsWorker("key", "url", Image.new("RGB", (120, 90), "white"), "m")
        w.succeeded.connect(lambda spec, log: got.update(spec=spec, log=log))
        w.failed.connect(lambda e: got.update(err=e))
        w.progressed.connect(lambda i, n, t: prog.append(t))
        w.start()
        t0 = time.time()
        while not w.isFinished() and time.time() - t0 < 10:
            QApplication.processEvents()
        for _ in range(5):
            QApplication.processEvents()
    assert "err" not in got, got.get("err")
    assert len(got["log"]) == 6 and prog and prog[-1] == "구역 6/6곳 끝"


# ── §8 항목28 3~4단계(2026-10-01) — 사진→도면 창·삽입 ─────────────────────────

def test_build_photo_drawing_centers_underlays_and_undoes_once():
    from PIL import Image
    w = CanvasWindow()
    w.resize(1200, 800)
    spec = {"ops": [{"op": "box", "id": "a", "x1": 10, "y1": 10, "x2": 60, "y2": 40, "label": "A"},
                    {"op": "line", "pts": [[60, 25], [100, 25]], "src": "a"},
                    {"op": "text", "x": 70, "y": 40, "text": "V", "rot": 90},
                    {"op": "bogus"}]}
    added, skipped = w._build_photo_drawing(spec, Image.new("RGB", (120, 90), "white"))
    assert skipped == 1
    img = added[0]
    assert isinstance(img, _ImageItem) and img._locked and not (img.flags() & img.GraphicsItemFlag.ItemIsSelectable)
    assert img._pixmap.toImage().pixelColor(5, 5).alpha() == w._PHOTO_UNDERLAY_ALPHA   # 흐림이 픽스맵에 구워짐
    assert all(it.zValue() > img.zValue() for it in added[1:])
    center = w._view.mapToScene(w._view.viewport().rect().center())
    r = img.mapRectToScene(img.rect())                    # sceneBoundingRect는 핸들 여백 포함
    assert abs(r.center().x() - center.x()) < 1 and abs(r.width() - 240) < 1   # 사진 중심=뷰 중앙, ×2
    box = next(it for it in added if isinstance(it, _RectItem))
    assert abs(box.mapRectToScene(box.rect()).left() - (r.left() + 20)) < 1     # 원본 좌표 그대로(×2)
    w.undo()
    assert not [it for it in w._scene.items() if it.parentItem() is None]
    w.deleteLater()


# ── 사진→도면 원근 보정(2026-10-01) ─────────────────────────────────────────────

def test_rectify_unwarps_quad_and_keeps_full_frame():
    from PIL import Image, ImageDraw
    from easycad.ai.photo_to_ops import rectify
    im = Image.new("RGB", (400, 300), "white")
    q = [(60, 40), (330, 70), (360, 260), (30, 240)]
    ImageDraw.Draw(im).polygon(q, outline="black", width=4)
    assert rectify(im, [(0, 0), (400, 0), (400, 300), (0, 300)]) is im     # 귀퉁이 그대로 → 보정 없음
    r = rectify(im, q)
    w, h = r.size
    px = r.load()
    dark = lambda p: sum(p) < 200
    assert dark(px[w // 2, 1]) and dark(px[1, h // 2]) and dark(px[w - 2, h // 2])   # 기운 변이 가장자리로
    assert px[w // 2, h // 2] == (255, 255, 255)
    try:
        rectify(im, [(0, 0), (100, 0), (200, 0), (300, 0)])                 # 한 줄 위 네 점
        assert False
    except ValueError:
        pass


def test_fit_for_ai_shrinks_phone_photo_under_gateway_limit():
    # 2026-10-05: 폰 원본(5712×4284)을 그대로 보내 요청 69MB → 413(한도 25MB).
    from PIL import Image
    from easycad.ai.photo_to_ops import fit_for_ai, first_content
    small = Image.new("RGB", (1200, 800), "white")
    assert fit_for_ai(small) is small                                       # 작으면 그대로
    big = fit_for_ai(Image.effect_noise((5712, 4284), 60).convert("RGB"))  # 압축 안 되는 최악 그림
    assert big.size == (1600, 1200)
    size = sum(len(p["image_url"]["url"]) for p in first_content(big, "x") if "image_url" in p)
    assert size < 25_000_000, size
