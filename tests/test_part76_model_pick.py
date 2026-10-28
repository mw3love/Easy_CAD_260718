"""2026-10-26 사용자 — 「회사로 넘기면 모델 관리를 할 수 없다, 관리 없이 오류가 안 나는 모델 선택」: 모델 대체(`easycad/ai/model_pick.py`).
정해 둔 모델이 은퇴하면 KAIROS가 적은 대체로, 불렀다가 「모델 없음」이면 같은 종류에서 대신할 것으로 한 번 다시(값 상한 안). KAIROS는 가짜.
진짜 KAIROS 확인(없는 이름 → 대화·임베딩·그림·받아쓰기 모두 404 not found, 목록 125개 · 그림 견적)은 `docs/history/2026-10.md` 끝.
"""
import json
import os
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from easycad.ai import board_find, board_image, gateway as gw, meeting, model_pick as mp  # noqa: E402


def _llm(mid, out, created, owner="openai", life="current", rep=None):
    return {"id": mid, "type": "llm", "owned_by": owner, "created": created, "lifecycle": life, "replacement": rep,
            "endpoints": ["/v1/gateway/chat/completions/"], "pricing": {"input": out / 5, "output": out}}


ROWS = [   # 2026-10-26 실제 목록에서 추린 것(값·대체는 실제와 같음, 「claude-opus-4-7 → fable」만 값 상한 시험용 가상)
    _llm("gpt-6.1-sol", 10, 90), _llm("gpt-6-sol", 10, 80), _llm("gpt-6-luna", 0.5, 85), _llm("gpt-6-astra", 50, 88),
    _llm("gpt-5.6-luna", 1.2, 50), _llm("gpt-5.4-mini", 4.5, 10, life="legacy", rep="gpt-5.6-luna"),
    _llm("claude-opus-5-5", 20, 70, owner="claude"), _llm("claude-sonnet-5-5", 10, 72, owner="claude"),
    _llm("claude-fable-5-1", 50, 75, owner="claude"), _llm("claude-opus-4-7", 25, 20, owner="claude", life="legacy", rep="claude-fable-5-1"),
    {"id": "gpt-image-2.5-flare", "type": "image", "owned_by": "openai", "created": 1},
    {"id": "gpt-image-2.5-sunburst", "type": "image", "owned_by": "openai", "created": 1},
    {"id": "gpt-image-2", "type": "image", "owned_by": "openai", "created": 1},
    {"id": "fal-ai/fast-sdxl", "type": "image", "owned_by": "stability-ai", "created": 1},
    {"id": "qwen3.7-text-embedding", "type": "embedding", "owned_by": "alibaba-cloud", "created": 3, "lifecycle": "current", "pricing": {"input": 0.07}},
    {"id": "text-embedding-v4", "type": "embedding", "owned_by": "alibaba-cloud", "created": 2, "lifecycle": "current", "pricing": {"input": 0.1}},
    {"id": "text-embedding-3-small", "type": "embedding", "owned_by": "openai", "created": 1, "lifecycle": "current", "pricing": {"input": 0.02}},
    {"id": "stt-async-v5", "type": "audio", "owned_by": "soniox", "audio_client": "soniox", "created": 1},
    {"id": "gemini-3.8-flash-tts", "type": "audio", "owned_by": "gemini", "audio_client": "google", "created": 2},
    {"id": "jev-1.14.0", "type": "decisions", "owned_by": "typesafe", "created": 9, "lifecycle": "current", "pricing": {"input": 0.042}},
]


@pytest.fixture(autouse=True)
def fresh():
    mp.reset()
    mp.remember(ROWS)
    yield
    mp.reset()


class NotFound(Exception):
    pass


def _gone(*names):
    """가짜 OpenAI create — `names`면 KAIROS처럼 404, 아니면 부른 모델을 답."""
    calls = []

    def create(**kw):
        calls.append(kw["model"])
        if kw["model"] in names:
            raise NotFound(f"Error code: 404 - {{'detail': {{'code': 404, 'message': \"invalid_request_error - Model '{kw['model']}' not found\"}}}}")
        return SimpleNamespace(model=kw["model"])
    return create, calls


def _client(create, embed=None):
    inner = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create, extra="속 그대로")),
                            embeddings=SimpleNamespace(create=embed or create), models="모델 목록")
    return mp.guarded(inner, "k", "https://g")


def test_pick_follows_retirement_but_keeps_current_and_unlisted_names():
    assert mp.pick("gpt-6.1-sol") == "gpt-6.1-sol"
    assert mp.mark({"model": "gpt-6.1-sol", "content": "답"}) == {"model": "gpt-6.1-sol", "content": "답"}
    assert mp.pick("gpt-5.4-mini") == "gpt-5.6-luna"   # 은퇴 → KAIROS가 적은 대체(더 쌈)
    out = mp.mark({"model": "gpt-5.4-mini", "content": "답"})
    assert out["model"] == "gpt-5.6-luna" and out["swap"] == {"from": "gpt-5.4-mini", "to": "gpt-5.6-luna", "why": "은퇴"}
    assert mp.pick("claude-opus-4-7") == "claude-opus-4-7"   # 대체가 원래 값의 1.5배를 넘으면 원래 것 그대로(은퇴해도 아직 답함)
    assert mp.pick("jev-latest") == "jev-latest" and mp.pick("stt-rt-v5") == "stt-rt-v5"   # 목록에 없는 별명은 막지 않음(실측: 됨)


def test_not_found_switches_once_and_remembers_for_an_hour(monkeypatch):
    create, calls = _gone("claude-opus-5-5")
    c = _client(create)
    assert c.chat.completions.create(model="claude-opus-5-5", messages=[]).model == "claude-sonnet-5-5"   # 같은 회사, 값이 가장 비슷(fable $50은 상한 밖)
    assert calls == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert mp.mark({"model": "claude-opus-5-5"})["swap"]["why"] == "없어짐"
    c.chat.completions.create(model="claude-opus-5-5", messages=[])
    assert calls[2:] == ["claude-sonnet-5-5"]   # 기억하는 동안은 처음부터 대신할 것으로(다시 실패하지 않음)
    assert c.chat.completions.extra == "속 그대로" and c.models == "모델 목록"   # 나머지는 OpenAI 클라이언트 그대로
    mp._dead["claude-opus-5-5"] = time.time() - mp.DEAD_TTL - 1   # 1시간 지남 → 원래 이름으로 다시(돌아왔을 수도)
    assert mp.pick("claude-opus-5-5") == "claude-opus-5-5" and "swap" not in mp.mark({"model": "claude-opus-5-5"})


def test_other_errors_do_not_switch():
    def create(**kw):
        raise RuntimeError("Error code: 429 - quota exceeded")
    with pytest.raises(RuntimeError, match="429"):
        _client(create).chat.completions.create(model="gpt-6.1-sol", messages=[])
    assert not mp._dead and "swap" not in mp.mark({"model": "gpt-6.1-sol"})   # 크레딧·바쁨은 갈아타지 않음(실패를 성공으로 오인)


def test_llm_fallback_never_auto_picks_top_price_models():
    assert mp.fallback("gpt-6-astra", "llm", "k") == "gpt-6.1-sol"     # $50이 없어져도 $25 상한 안에서(fable·astra는 사람만 고름)
    assert mp.fallback("gpt-7-nova", "llm", "k") == "gpt-6.1-sol"      # 본 적 없는 이름(목록에서 사라진 뒤 켬) — 이름 첫 마디로 같은 회사, 기본 모델 값 근처
    assert mp.fallback("gpt-6-luna", "llm", "k") == "gpt-6.1-sol"      # 같은 계열·회사에 상한 안 모델이 없으면 대화 기본 모델(마지막 바닥)


def test_retired_then_gone_chain_points_to_the_last_name():
    create, calls = _gone("gpt-5.6-luna")
    c = _client(create)
    c.chat.completions.create(model="gpt-5.4-mini", messages=[])   # 은퇴 → 5.6-luna → 그것도 없음 → 같은 계열 6-luna
    assert calls == ["gpt-5.6-luna", "gpt-6-luna"]
    assert mp.mark({"model": "gpt-5.4-mini"})["model"] == "gpt-6-luna" and mp.pick("gpt-5.4-mini") == "gpt-6-luna"


class ImageHttp:
    """가짜 그림 창구 — 생성(`gone`이면 404)·무료 견적(`price`, 장당)."""

    def __init__(self, gone, price):
        self.gone, self.price, self.made = gone, price, []

    def post(self, url, headers, json, timeout):
        m = json["model"]
        if url.endswith("/estimate/"):
            ok = m in self.price
            return SimpleNamespace(status_code=200 if ok else 404, json=lambda: {"credits": self.price[m]} if ok else {})
        self.made.append(m)
        if m in self.gone:
            return SimpleNamespace(status_code=404, text=f'{{"detail": {{"message": "Image model \'{m}\' not found"}}}}', json=lambda: {})
        return SimpleNamespace(status_code=200, text="", json=lambda: {"data": [{"b64_json": "UE5H"}], "credits_charged": self.price[m] * json["number_of_images"]})


def test_image_falls_back_within_price_by_free_estimate():
    http = ImageHttp({"gpt-image-2.5-flare"}, {"gpt-image-2.5-sunburst": 10, "gpt-image-2": 41, "fal-ai/fast-sdxl": 5})
    out = board_image.generate("k", "송신탑", n=1, base_url="https://g", http=http)
    assert http.made == ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]   # 같은 회사 먼저, 장당 15 상한 안(gpt-image-2 41은 밖)
    assert out["model"] == "gpt-image-2.5-flare" and mp.mark(out)["model"] == "gpt-image-2.5-sunburst"   # 갈아탄 이름은 서버가 답에


def test_image_other_maker_when_same_maker_too_pricey():
    mp.note_cost("gpt-image-2.5-flare", 10)   # 전에 실제로 든 값(장당 10) → 상한 15
    http = ImageHttp({"gpt-image-2.5-flare"}, {"gpt-image-2.5-sunburst": 30, "gpt-image-2": 41, "fal-ai/fast-sdxl": 5})
    board_image.generate("k", "송신탑", n=1, base_url="https://g", http=http)
    assert http.made[-1] == "fal-ai/fast-sdxl"


def test_stt_falls_back_in_same_lane_only():
    mp.remember(ROWS + [{"id": "stt-async-v6", "type": "audio", "owned_by": "soniox", "audio_client": "soniox", "created": 1}])
    sent = []

    class Http:
        def post(self, url, headers, files, data, timeout):
            sent.append(data["model"])
            if data["model"] == "stt-async-v5":
                return SimpleNamespace(status_code=404, text="Audio model 'stt-async-v5' not found", json=lambda: {})
            return SimpleNamespace(status_code=200, text="", json=lambda: {})   # operation_id 없음 → 여기서 멈춤(보낸 모델만 봄)
    with pytest.raises(RuntimeError, match="operation_id"):
        meeting.transcribe("k", b"RIFF", "a.wav", base_url="https://g", http=Http(), sleep=lambda s: None)
    assert sent == ["stt-async-v5", "stt-async-v6"]   # 음성 합성(google)이 아니라 같은 받아쓰기 창구


def test_find_cache_is_per_model_and_redone_when_switched_mid_call(tmp_path):
    doc = {"items": [{"type": "memo", "uid": "m1", "lines": [{"k": "p", "t": "송신소 점검"}]},
                     {"type": "memo", "uid": "m2", "lines": [{"k": "p", "t": "점심 후보"}]}]}
    path = str(tmp_path / "b.emb.json")
    json.dump({"model": board_find.EMBED_MODEL, "vecs": {"x": [1.0]}}, open(path, "w", encoding="utf-8"))
    seen = []

    def embed(**kw):
        seen.append((kw["model"], len(kw["input"])))
        if kw["model"] == board_find.EMBED_MODEL:
            raise NotFound(f"Error code: 404 - Model '{kw['model']}' not found")
        return SimpleNamespace(data=[SimpleNamespace(embedding=[1.0, float(i)]) for i in range(len(kw["input"]))])
    board_find.find(_client(_gone()[0], embed), doc, "점검")
    board_find.find(_client(_gone()[0], embed), doc, "점검", cache_path=path)
    assert seen[:2] == [(board_find.EMBED_MODEL, 3), ("text-embedding-v4", 3)]   # 같은 회사로 갈아타 글 둘 + 질문
    saved = json.load(open(path, encoding="utf-8"))
    assert saved["model"] == "text-embedding-v4" and "x" not in saved["vecs"]   # 옛 모델 숫자와 섞지 않음


def test_gateway_client_is_guarded_and_list_is_remembered(monkeypatch):
    c = gw._client("k-test-only", "https://g.example", timeout=1)
    try:
        assert c.chat.completions.create.__name__ == "call" and hasattr(c, "models")
    finally:
        gw._client_cache.pop(("k-test-only", "https://g.example", 1), None)

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [_llm("gpt-9-sol", 10, 99), _llm("gpt-6.1-sol", 10, 90, life="legacy", rep="gpt-9-sol")]}
    from unittest.mock import patch
    with patch("httpx.get", return_value=Resp()):
        gw.list_text_models_info("k")
    assert mp.pick("gpt-6.1-sol") == "gpt-9-sol"   # 대화창 목록을 받을 때 같이 기억 → 은퇴를 바로 따라감


@pytest.fixture
def server(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer
    sys.path.insert(0, os.path.join(ROOT, "web"))
    import server as srv
    monkeypatch.setattr(srv.gw, "resolve_api_key", lambda explicit="": "test-key")
    monkeypatch.setattr(srv.board_chat, "models", lambda key, base="": {"default": "gpt-6.1-sol", "featured": {}})
    srv._MODELS.clear()
    srv.Handler.data_dir, srv.Handler.password = str(tmp_path), ""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", srv
    httpd.shutdown()


def _post(base, body):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(base + "/api/chat", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_server_picked_model_first_then_default_when_it_cannot(server, monkeypatch):
    """「모델 설정」(2026-10-26) — 고른 모델로 먼저, 그 모델이 이 일을 못 하면 앱 기본으로 한 번 다시 + 답에 「(대신)」. 크레딧 오류는 다시 안 함."""
    base, srv = server
    used = []

    def make(client, material, ask, prev_html="", model="", images=None):
        used.append(model)
        if model == "bad-model":
            raise RuntimeError("정리 문서 HTML이 아닌 답")
        if model == "broke-model":
            raise RuntimeError("Error code: 429 - quota exceeded")
        return {"title": "점검", "html": "<p>x</p>", "model": model, "elapsed": 1.0}
    monkeypatch.setattr(srv.board_report, "make", make)
    ask = lambda picks: _post(base, {"board": "b", "kind": "report", "models": picks, "messages": [{"role": "user", "content": "정리해 줘", "context": "VSWR 1.12"}]})   # noqa: E731
    code, out = ask({"report": "claude-sonnet-5-5"})
    assert code == 200 and out["model"] == "claude-sonnet-5-5" and "swap" not in out and used == ["claude-sonnet-5-5"]
    code, out = ask({"report": "bad-model"})
    assert code == 200 and out["model"] == srv.board_report.REPORT_MODEL and out["swap"] == {"from": "bad-model", "to": srv.board_report.REPORT_MODEL, "why": "못 함"}
    code, out = ask({"report": "broke-model"})
    assert code == 502 and used[-1] == "broke-model"   # 크레딧은 다른 모델로도 안 됨 — 다시 안 함
    code, out = ask({"report": "x; rm -rf"})   # 이상한 이름은 버리고 자동
    assert code == 200 and used[-1] == srv.board_report.REPORT_MODEL


def test_server_models_lists_by_kind_and_jobs_follow_retirement(server):
    import urllib.request
    base, srv = server
    mp.remember(ROWS + [_llm("claude-opus-5-5", 20, 70, owner="claude", life="legacy", rep="claude-sonnet-5-5")])
    mp.note_cost("gpt-image-2.5-flare", 10.41)
    with urllib.request.urlopen(base + "/api/models") as r:
        out = json.loads(r.read())
    llm, img = [m["id"] for m in out["choices"]["llm"]], [m["id"] for m in out["choices"]["image"]]
    assert "gpt-6.1-sol" in llm and "jev-1.14.0" not in llm and "gpt-image-2.5-flare" not in llm and "gpt-5.4-mini" not in llm   # 판단·그림·은퇴는 대화 칸에 없음
    assert img[0] == "gpt-image-2.5-flare" and next(m for m in out["choices"]["image"] if m["id"] == "gpt-image-2.5-flare")["price"] == "장당 약 10.41크레딧"
    assert out["jobs"]["report"] == "claude-sonnet-5-5" and out["jobs"]["deep_write"] == srv.deep_mode.WRITER_MODEL   # 은퇴한 정리 문서 모델 = 지금 부르는 이름으로
