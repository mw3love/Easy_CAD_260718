"""§8 항목20 AI SVG 에셋 생성 — B단계(앱 UI 통합, 2026-08-14) + Stage 1/2/3(2026-08-19).

deep-interview(2026-08-14)로 확정된 대로: 진입점 2곳(삽입 메뉴로 새로 삽입 + 우클릭으로
기존 도형 대체)이 `_SvgAssetDialog` 하나를 공유, 대체 시 새 SVG 크기는 대체 도형
바운딩박스 긴 변 기준(SVG 자체 종횡비 유지), 화살표는 재연결하지 않음(`delete_selection()`
이 이미 제공하는 "제자리에 얼어붙는다" 동작과 같은 결과).

2026-08-19 deep-interview로 세 차례 더 확정: **Stage 1** — 동기 호출+WaitCursor(원래
2026-08-14 결정, 당시 옛 QThread 워커는 §8 항목18에서 이미 폐기된 상태였음)가 프리징을
일으켜 `_SvgGenWorker`(QThread)+진행바로 교체. **Stage 2** — 모델별 후보 개수를 gpt/gemini
체크박스(모델당 1개 고정) 대신 독립 드롭다운(0~5개)으로 확장, 요청한 후보 전부를 완전
병렬 호출(워커 하나=호출 하나, 전부 동시 `start()`), 끝난 순서대로 카드 채움. **Stage 3** —
이미지 입력(찾아보기·드래그드롭·Ctrl+V)을 `_ImageAttachMixin`으로 `_MermaidDialog`와
공유해 추가, 이미지가 첨부되면 대상 설명은 선택 사항이 된다.

이 파일이 검증하는 것:
  - `easycad/ai/text_to_svg.py` — 프롬프트 빌더(텍스트·이미지)·코드펜스 벗기기·generate_svg.
  - `easycad/fileio/svg_import.py` — `parse_svg_string`(문자열 입력, `parse_svg_items`와
    동일 동작).
  - `_SvgAssetDialog` — 모델별 개수 드롭다운→완전 병렬 호출, 부분 실패 시 성공한 후보만
    표시, 후보 카드 클릭 선택, 빈 프롬프트/개수 0/키 없음 가드, 생성 중 진행 표시·컨트롤
    비활성화·닫기는 즉시(생성 중이어도 워커를 분리해 백그라운드에서 마저 끝남), 이미지
    첨부(찾아보기·드롭·Ctrl+V).
  - `host_fileio._insert_ai_svg_asset` — 삽입 경로(undo 1스텝).
  - `host_context._generate_svg_replace` — 대체 경로(remove+create 단일 undo, 화살표
    미재연결, 대체 도형 bbox 긴 변 기준 리스케일).
  - 메뉴/툴바/컨텍스트메뉴 배선.

실행: python tests/test_easycad.py (전체) 또는 pytest test_part9_ai_svg_asset.py.
"""
from PyQt6.QtCore import QRectF, QPointF, QEvent
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QWidget

from _shared import *  # noqa: F401,F403

from easycad.ai import gateway as gw  # noqa: E402
from easycad.ai import text_to_svg as tts  # noqa: E402
from easycad.fileio.svg_import import parse_svg_items, parse_svg_string  # noqa: E402
from easycad.fileio import symbol_library  # noqa: E402
from easycad.canvas.host_dialogs import (  # noqa: E402
    _SvgAssetDialog, _SvgCandidateCard, _SaveToSymbolsFolderDialog, _QuickLookDialog,
)
from easycad.canvas.host_selection import _group_scene_rect  # noqa: E402

_SAMPLE_SVG = ('<svg viewBox="0 0 100 100">'
              '<line x1="10" y1="10" x2="90" y2="90"/>'
              '<rect x="20" y="20" width="30" height="30"/>'
              '</svg>')


def _wait_workers(dlg):
    """2026-08-19 비동기화(`_SvgGenWorker`, QThread) — `_on_generate_clicked()`는 즉시
    반환하고 요청한 후보 개수만큼의 백그라운드 스레드가 동시에 돈다(Stage 2, 완전 병렬).
    각 워커를 `wait()`로 종료까지 막은 뒤 `processEvents()`를 몇 번 돌려야 큐잉된
    (cross-thread) 시그널이 실제로 슬롯에 전달된다(Qt의 기본 QueuedConnection 동작 —
    이벤트 루프가 펌핑돼야 배달됨). 마지막 워커의 `finished`가 `dlg._workers`를 비우므로
    반드시 먼저 리스트를 복사해 둔다."""
    for w in list(dlg._workers):
        w.wait(5000)
    for _ in range(5):
        QApplication.processEvents()


# ── text_to_svg.py ───────────────────────────────────────────────────────────

def test_build_prompt_includes_subject_and_parser_rules():
    text = tts.build_prompt("BNC 커넥터 아이콘")
    assert "BNC 커넥터 아이콘" in text
    assert "viewBox" in text
    assert "<g>" in text   # 미지원 요소 금지 규칙


def test_extract_svg_strips_language_tagged_code_fence():
    raw = "```svg\n<svg viewBox=\"0 0 10 10\"></svg>\n```"
    assert tts.extract_svg(raw) == '<svg viewBox="0 0 10 10"></svg>'


def test_extract_svg_strips_bare_code_fence():
    raw = "```\n<svg viewBox=\"0 0 10 10\"></svg>\n```"
    assert tts.extract_svg(raw) == '<svg viewBox="0 0 10 10"></svg>'


def test_extract_svg_passthrough_when_no_fence():
    raw = '<svg viewBox="0 0 10 10"></svg>'
    assert tts.extract_svg(raw) == raw


def test_generate_svg_returns_text_and_model_used():
    def fake_call(api_key, prompt, *, model, **kw):
        assert "안테나" in prompt
        return gw.GatewayResult("```svg\n<svg viewBox=\"0 0 10 10\"></svg>\n```",
                                model, None, 1.2)

    with patch.object(tts.gw, "call_text_with_fallback", fake_call):
        text, used = tts.generate_svg("key", "안테나 아이콘", model="gpt-5.4-mini")
    assert text == '<svg viewBox="0 0 10 10"></svg>'
    assert used == "gpt-5.4-mini"


# ── text_to_svg.py: 이미지 입력(Stage 3, 2026-08-19) ──────────────────────────

def test_build_image_prompt_includes_subject_and_no_hallucination_note():
    text = tts.build_image_prompt("BNC 커넥터 아이콘")
    assert "BNC 커넥터 아이콘" in text
    assert "실제로 있는 형태만" in text   # 2026-07-21 환각 함정 재확인 규칙 계승


def test_build_image_prompt_omits_subject_line_when_empty():
    text = tts.build_image_prompt("")
    assert "참고" not in text


def test_generate_svg_uses_image_prompt_and_longer_timeout_when_image_given():
    from PIL import Image
    captured = {}

    def fake_call(api_key, prompt, *, model, image=None, base_url=None, timeout=None):
        captured["prompt"] = prompt
        captured["image"] = image
        captured["timeout"] = timeout
        return gw.GatewayResult('<svg viewBox="0 0 10 10"></svg>', model, None, 1.0)

    img = Image.new("RGB", (10, 10), "white")
    with patch.object(tts.gw, "call_text_with_fallback", fake_call):
        text, used = tts.generate_svg("key", "보충설명", model="gpt-5.4-mini", image=img)
    assert text == '<svg viewBox="0 0 10 10"></svg>'
    assert captured["image"] is img
    assert "보충설명" in captured["prompt"]
    assert "실제로 있는 형태만" in captured["prompt"]
    assert captured["timeout"] == 120.0   # 텍스트 전용 기본(60s)보다 넉넉하게


def test_generate_svg_uses_text_prompt_when_no_image():
    captured = {}

    def fake_call(api_key, prompt, *, model, image=None, base_url=None, timeout=None):
        captured["prompt"] = prompt
        captured["timeout"] = timeout
        return gw.GatewayResult('<svg viewBox="0 0 10 10"></svg>', model, None, 1.0)

    with patch.object(tts.gw, "call_text_with_fallback", fake_call):
        tts.generate_svg("key", "안테나 아이콘", model="gpt-5.4-mini")
    assert "viewBox" in captured["prompt"]
    assert captured["timeout"] == 60.0


# ── svg_import.py: parse_svg_string ──────────────────────────────────────────

def test_parse_svg_string_matches_parse_svg_items_for_same_content():
    """문자열 입력이 파일 입력과 동일한 결과를 내야 한다(공통 `_parse_svg_root` 재사용)."""
    path = os.path.join(_TMP, f"probe_{uuid.uuid4().hex}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_SAMPLE_SVG)
    items_file, vb_file = parse_svg_items(path)
    items_str, vb_str = parse_svg_string(_SAMPLE_SVG)
    assert len(items_file) == len(items_str) == 2
    assert vb_file == vb_str


def test_parse_svg_string_applies_long_side_and_center():
    center = QPointF(500.0, 300.0)
    items, vb = parse_svg_string(_SAMPLE_SVG, 40.0, center)
    line = items[0]
    scene_len = max(abs(line.line().dx()), abs(line.line().dy()))
    assert scene_len <= 40.0 + 1e-6


def test_parse_svg_string_raises_on_malformed_xml():
    try:
        parse_svg_string("<svg><line x1='0'></svg-broken")
        assert False, "should have raised"
    except Exception:
        pass


def test_parse_svg_polygon_and_polyline_map_to_polygon_item():
    # [실사용 요청 2026-08-19] §8 항목21로 `_PolygonItem`이 생기기 전엔 <polygon>/<polyline>도
    # 임의 QPainterPath 컨테이너인 `_PathItem`(펜 도구와 같은 타입)으로만 들어왔다 — 이제
    # box 리사이즈·이산 포트·TRIM을 그대로 얻도록 `_PolygonItem`으로 옮겼다. 닫힘 여부(closed)
    # 는 태그 종류(polygon=닫힘/polyline=열림) 그대로 반영돼야 한다.
    svg = ('<svg viewBox="0 0 100 100">'
           '<polygon points="10,10 90,10 50,90"/>'
           '<polyline points="10,50 40,20 70,50 90,30"/>'
           '</svg>')
    items, _vb = parse_svg_string(svg)
    assert len(items) == 2
    poly, line = items
    assert isinstance(poly, _PolygonItem) and poly._closed
    assert isinstance(line, _PolygonItem) and not line._closed
    assert len(poly.local_pts()) == 3
    assert len(line.local_pts()) == 4
    assert not isinstance(poly, _PathItem) and not isinstance(line, _PathItem)


def test_parse_svg_path_still_maps_to_path_item():
    # <path>(베지어·호)는 임의 곡선이라 정점 목록이 아니다 — `_PolygonItem`으로 옮길 대상이
    # 아니고, 지금도 정확히 `_PathItem`이 맞는 선택임을 회귀로 고정.
    svg = '<svg viewBox="0 0 100 100"><path d="M10,10 C20,20 40,20 50,10"/></svg>'
    items, _vb = parse_svg_string(svg)
    assert len(items) == 1
    assert isinstance(items[0], _PathItem)


# ── _SvgAssetDialog ───────────────────────────────────────────────────────────

def test_svg_asset_dialog_defaults_to_one_candidate_per_model():
    """2026-08-19 Stage 2 — 체크박스(모델당 1개 고정) 대신 모델별 개수 드롭다운(0~5)으로
    확장됐지만, 기본값은 Stage 1과 같은 체감(각 1개)을 유지한다."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    assert dlg._count_a.currentText() == "1"
    assert dlg._count_b.currentText() == "1"
    assert dlg._count_a.count() == 6        # 0~5
    assert dlg._count_b.count() == 6
    assert dlg._requested_jobs() == [gw.TEXT_RECOMMEND_1, gw.TEXT_RECOMMEND_2]
    dlg.deleteLater()


def test_svg_asset_dialog_requested_jobs_repeats_model_per_count():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._count_a.setCurrentText("3")
    dlg._count_b.setCurrentText("2")
    assert dlg._requested_jobs() == [gw.TEXT_RECOMMEND_1] * 3 + [gw.TEXT_RECOMMEND_2] * 2
    dlg.deleteLater()


def test_svg_asset_dialog_requires_nonempty_subject():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    with patch("easycad.canvas.host_dialogs.QMessageBox.information") as info, \
         patch("easycad.canvas.host_dialogs.generate_svg") as gen:
        dlg._on_generate_clicked()
    assert info.called
    assert not gen.called
    dlg.deleteLater()


def test_svg_asset_dialog_requires_api_key():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("안테나 아이콘")
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value=""), \
         patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn, \
         patch("easycad.canvas.host_dialogs.generate_svg") as gen:
        dlg._on_generate_clicked()
    assert warn.called
    assert not gen.called
    dlg.deleteLater()


def test_svg_asset_dialog_requires_at_least_one_model_checked():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("안테나 아이콘")
    dlg._count_a.setCurrentText("0")
    dlg._count_b.setCurrentText("0")
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.QMessageBox.information") as info, \
         patch("easycad.canvas.host_dialogs.generate_svg") as gen:
        dlg._on_generate_clicked()
    assert info.called
    assert not gen.called
    dlg.deleteLater()


def test_svg_asset_dialog_generates_one_candidate_per_default_job():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    calls = []

    def fake_generate(key, subject, *, model, **kw):
        calls.append(model)
        return _SAMPLE_SVG, model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate):
        dlg._on_generate_clicked()
        _wait_workers(dlg)
    # 2026-08-19 Stage 2 — 완전 병렬(워커별 실행 순서는 OS 스케줄링에 달림)이라 도착
    # 순서는 보장 안 됨, 호출된 모델 집합만 확인한다.
    assert sorted(calls) == sorted([gw.TEXT_RECOMMEND_1, gw.TEXT_RECOMMEND_2])
    assert len(dlg._candidates) == 2
    assert dlg._selected_card is not None   # 첫 성공 후보 기본 선택
    assert dlg._ok_btn.isEnabled()
    dlg.deleteLater()


def test_svg_asset_dialog_all_requested_workers_start_together():
    """2026-08-19 Stage 2 핵심 증거 — 개수를 늘리면(GPT 3·Gemini 2=5개) 워커가 순차가
    아니라 전부 동시에 만들어져 시작된다. `_on_generate_clicked()`가 반환한 직후(아직
    `wait()`하기 전) 워커 5개가 모두 존재+실행 중이어야 한다(하나씩 만들고 끝나길
    기다렸다가 다음을 만드는 방식이면 이 순간 워커가 1개뿐일 것)."""
    import time
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    dlg._count_a.setCurrentText("3")
    dlg._count_b.setCurrentText("2")

    def fake_generate(key, subject, *, model, **kw):
        time.sleep(0.05)
        return _SAMPLE_SVG, model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate):
        dlg._on_generate_clicked()
        try:
            assert len(dlg._workers) == 5
            assert dlg._pending == 5
            time.sleep(0.01)   # 스레드들이 실제로 뜰 시간
            assert sum(1 for w in dlg._workers if w.isRunning()) >= 2   # 순차라면 1개뿐일 것
        finally:
            _wait_workers(dlg)
    assert len(dlg._candidates) == 5
    dlg.deleteLater()


def test_svg_asset_dialog_shows_progress_and_disables_controls_while_generating():
    """2026-08-19 비동기화 — 프리징 해소의 핵심 증거: 워커가 도는 동안(=`_on_generate_
    clicked()`가 반환한 직후, 아직 `wait()`하기 전) 진행 표시가 보이고 생성/버튼박스가
    비활성화돼 있어야 한다. 예전 동기 구현은 이 순간 자체가 없었다(호출이 끝나야
    `_on_generate_clicked()`가 반환했으므로).

    ⚠ 어서션이 `_wait_workers()` 전에 실패하면(=워커를 join하지 않은 채 테스트가 죽으면)
    아직 살아있는 QThread가 뒤이은 `with patch(...)` 종료로 원본(진짜 네트워크 호출)
    함수를 다시 붙잡을 위험이 있다(실측으로 확인된 함정 — 실제로 이 문제 때문에 전체
    스위트가 몇 시간 멈춘 적이 있다). 그래서 `try/finally`로 무슨 일이 있어도 join한다."""
    import time
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")

    def fake_generate(key, subject, *, model, **kw):
        time.sleep(0.05)   # 스레드가 실제로 도는 동안 메인 스레드가 상태를 관찰할 여지
        return _SAMPLE_SVG, model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate):
        dlg._on_generate_clicked()
        try:
            assert not dlg._progress.isHidden()
            assert not dlg._gen_btn.isEnabled()
            assert not dlg._btns.isEnabled()
            assert not dlg._count_a.isEnabled()
            assert not dlg._count_b.isEnabled()
        finally:
            _wait_workers(dlg)
    assert dlg._progress.isHidden()
    assert dlg._gen_btn.isEnabled()
    assert dlg._btns.isEnabled()
    assert dlg._count_a.isEnabled()
    assert dlg._count_b.isEnabled()
    assert dlg._workers == []
    dlg.deleteLater()


def test_svg_asset_dialog_close_immediate_while_generating():
    """2026-08-23 설계 변경(`_MermaidDialog`와 동일 이유) — 예전엔 생성 중 닫기를
    `closeEvent`의 `e.ignore()`로 막았으나, Cancel 버튼의 `reject()`는 그 방어코드를
    거치지 않고 곧장 다이얼로그를 없애 아직 도는 워커까지 함께 파괴돼 프로그램이 죽는
    실사용 크래시로 이어졌다. 이제는 무엇이 돌든 닫기가 항상 즉시 되고, 아직 도는
    워커는 `_detach_worker`로 분리돼 크래시 없이 백그라운드에서 마저 끝난다."""
    import time
    from easycad.canvas import host_dialogs
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")

    def fake_generate(key, subject, *, model, **kw):
        time.sleep(0.3)
        return _SAMPLE_SVG, model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate):
        dlg._on_generate_clicked()
        workers = list(dlg._workers)
        assert workers and all(w.isRunning() for w in workers)
        dlg.reject()   # Cancel 버튼과 완전히 같은 경로 — 실사용 크래시가 재현되던 지점
        assert dlg.result() == QDialog.DialogCode.Rejected   # 생성 중이어도 즉시 닫힘
        assert all(w in host_dialogs._ORPHANED_WORKERS for w in workers)   # 전부 분리됨
        for w in workers:
            w.wait(5000)
        for _ in range(5):
            QApplication.processEvents()
    assert not any(w in host_dialogs._ORPHANED_WORKERS for w in workers)   # 끝난 뒤 정리됨
    dlg.deleteLater()


def test_svg_asset_dialog_partial_failure_keeps_successful_candidates():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")

    def fake_generate(key, subject, *, model, **kw):
        if model == gw.TEXT_RECOMMEND_1:
            raise RuntimeError("504 timeout")
        return _SAMPLE_SVG, model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate), \
         patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn:
        dlg._on_generate_clicked()
        _wait_workers(dlg)
    assert warn.called   # 실패 사실은 알림
    assert len(dlg._candidates) == 1
    assert dlg._candidates[0][2] == gw.TEXT_RECOMMEND_2
    dlg.deleteLater()


def test_svg_asset_dialog_all_models_fail_shows_no_candidates():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")

    def fake_generate(key, subject, *, model, **kw):
        raise RuntimeError("network down")

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate), \
         patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn:
        dlg._on_generate_clicked()
        _wait_workers(dlg)
    assert warn.called
    assert dlg._candidates == []
    assert not dlg._ok_btn.isEnabled()
    dlg.deleteLater()


def test_svg_asset_dialog_clicking_card_switches_selection():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")

    def fake_generate(key, subject, *, model, **kw):
        return _SAMPLE_SVG, model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate):
        dlg._on_generate_clicked()
        _wait_workers(dlg)
    first_card, _svg, first_model = dlg._candidates[0]
    second_card, _svg2, second_model = dlg._candidates[1]
    assert dlg._selected_card is first_card
    dlg._pick_card(second_card)
    assert dlg._selected_card is second_card
    assert dlg.selected_svg() == _SAMPLE_SVG
    assert not first_card._selected
    assert second_card._selected
    dlg.deleteLater()


def test_svg_asset_dialog_enter_in_prompt_triggers_generate():
    """[2026-08-20 재피드백 — `_prompt_edit`을 `QLineEdit`→`QPlainTextEdit`(3줄)으로 전환
    하며 `returnPressed` 시그널이 사라졌다] Mermaid `_prompt_edit`과 동일하게 `eventFilter`
    가 Enter를 가로채 `_on_generate_clicked`를 호출한다 — 실제 Qt 시그널 연결이 아니라
    이 다이얼로그가 직접 처리하므로 인스턴스 속성 monkeypatch로도 검증 가능(Mermaid의
    동일 테스트와 같은 방식)."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    calls = {"n": 0}
    dlg._on_generate_clicked = lambda: calls.__setitem__("n", calls["n"] + 1)

    from PyQt6.QtGui import QKeyEvent
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    handled = dlg.eventFilter(dlg._prompt_edit, ev)
    assert handled is True
    assert calls["n"] == 1
    dlg.deleteLater()


def test_svg_asset_dialog_shift_enter_in_prompt_inserts_newline_not_generate():
    """Shift+Enter는 줄바꿈(여러 줄 대상 설명용)이지 생성 트리거가 아니어야 한다
    (Mermaid `_prompt_edit`과 동일 관례)."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    calls = {"n": 0}
    dlg._on_generate_clicked = lambda: calls.__setitem__("n", calls["n"] + 1)

    from PyQt6.QtGui import QKeyEvent
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    handled = dlg.eventFilter(dlg._prompt_edit, ev)
    assert handled is False   # 기본 동작(줄바꿈)에 맡김
    assert calls["n"] == 0
    dlg.deleteLater()


# ── 2026-08-20 재피드백 5건 ──────────────────────────────────────────────────

def test_svg_asset_dialog_dark_theme_preview_uses_brighter_pen():
    """[2026-08-20 피드백] "후보 미리보기 선이 배경과 비슷해 흐리다" — 다크 테마 부모
    창일 때만 미리보기 전용 밝은 펜 색을 준비해야 한다(실삽입 색과는 무관)."""
    parent = QWidget()
    parent._dark = True
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog(parent)
    assert dlg._preview_pen_color is not None
    assert dlg._preview_pen_color.name() == "#f2f2f2"
    dlg.deleteLater()
    parent.deleteLater()


def test_svg_asset_dialog_light_theme_preview_uses_default_pen():
    """라이트 테마는 흰 배경에 흰 선이 안 보이므로 오버라이드 없이(`None`) 기본 잉크색
    (`_render_svg_candidate_pixmap`의 `_ICON_COLOR` 폴백)에 맡긴다."""
    parent = QWidget()
    parent._dark = False
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog(parent)
    assert dlg._preview_pen_color is None
    dlg.deleteLater()
    parent.deleteLater()


def test_svg_asset_dialog_candidate_columns_respond_to_width():
    """[2026-08-20 피드백] "창 크기에 따라 후보 크기도" — 카드 픽셀 크기는 고정하고
    열 개수만 가용 폭에 반응해야 한다. 실제 창(레이아웃이 살아있는)에서 다이얼로그
    자체를 리사이즈해 `resizeEvent`가 `_update_candidate_columns`를 발화시키는지까지
    확인한다(스크롤 영역만 직접 `resize()`하면 부모 레이아웃이 되돌려버려 무의미함)."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg.show()
    QApplication.processEvents()

    dlg.resize(1600, 700)
    QApplication.processEvents()
    wide_cols = dlg._candidate_cols
    assert wide_cols > dlg._CANDIDATE_COLS   # 1600px 폭이면 기본 3열보다 넓게 잡혀야 함

    dlg.resize(500, 700)
    QApplication.processEvents()
    narrow_cols = dlg._candidate_cols
    assert 1 <= narrow_cols < wide_cols
    dlg.close()
    dlg.deleteLater()


def test_svg_asset_dialog_add_candidate_uses_current_column_count():
    """열 수가 바뀐 뒤 추가되는 후보는 새 열 수를 기준으로 배치돼야 한다. `_add_candidate`
    가 배치 직전 `_update_candidate_columns()`(실사용 경로 보정용, 위 테스트 참조)를 항상
    부르므로, 이 테스트에서 수동으로 정한 `_candidate_cols`가 실제(레이아웃 안 된) 폭
    기준 값으로 덮어써지지 않도록 그 갱신만 무력화한다 — 여기서 검증하려는 건 "배치가
    `_candidate_cols`를 따르는가"이지 "폭에서 열 수를 어떻게 계산하는가"가 아니다."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._candidate_cols = 2
    with patch.object(dlg, "_update_candidate_columns"):
        for i in range(3):
            dlg._add_candidate(f"model{i}", _SAMPLE_SVG)
    item = dlg._candidates_grid.itemAtPosition(1, 0)   # idx=2, cols=2 → row1,col0
    assert item is not None
    assert item.widget() is dlg._candidates[2][0]
    dlg.deleteLater()


def _gen_n_candidates_direct(dlg, n):
    """AI 호출 없이 `_add_candidate`만 n번 불러 후보를 채운다(갤러리 탐색·확대창 테스트가
    반복 재사용)."""
    for i in range(n):
        dlg._add_candidate(f"model{i}", _SAMPLE_SVG)


def test_svg_asset_dialog_enlarge_candidate_is_non_modal_without_close_button():
    """[2026-08-20 재피드백] 확대 보기는 하단 Close 버튼 없이 비모달로 뜬다(우상단 X는
    창 자체가 원래 제공, 빠르게 여러 후보를 훑어보기 위함)."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    _gen_n_candidates_direct(dlg, 2)
    dlg._show_enlarged_candidate(0)
    quicklook = dlg._quicklook
    assert quicklook is not None
    assert not quicklook.isModal()
    assert not quicklook.findChildren(QDialogButtonBox)
    quicklook.close()
    dlg.deleteLater()


def test_svg_asset_dialog_enlarge_candidate_reuses_single_instance():
    """[2026-08-20 3차 피드백] 매번 새 창을 만들지 않고 인스턴스 하나를 재사용해야 한다
    (화살표 탐색·카드 클릭 동기화가 "같은 창"이어야 자연스러우므로)."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    _gen_n_candidates_direct(dlg, 3)
    dlg._show_enlarged_candidate(0)
    first = dlg._quicklook
    dlg._show_enlarged_candidate(2)
    assert dlg._quicklook is first
    assert first._index == 2
    first.close()
    dlg.deleteLater()


def test_svg_asset_dialog_quicklook_shows_position_counter_and_model():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    _gen_n_candidates_direct(dlg, 4)
    dlg._show_enlarged_candidate(1)
    assert dlg._quicklook._counter_label.text() == "2 / 4  ·  model1"
    dlg._quicklook.close()
    dlg.deleteLater()


def test_svg_asset_dialog_quicklook_arrow_keys_navigate_and_sync_selection():
    """[2026-08-20 3차 피드백] 확대창 안 ←/→로 후보를 넘기면 메인 그리드의 단일선택
    (`_pick_card`)도 함께 이동해야 한다."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    _gen_n_candidates_direct(dlg, 3)
    dlg._show_enlarged_candidate(0)
    ql = dlg._quicklook

    from PyQt6.QtGui import QKeyEvent
    ql.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier))
    assert ql._index == 1
    assert dlg._selected_card is dlg._candidates[1][0]

    ql.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier))
    assert ql._index == 0
    assert dlg._selected_card is dlg._candidates[0][0]

    # 맨 앞에서 ←는 아무 일도 안 함(범위 밖)
    ql.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier))
    assert ql._index == 0
    ql.close()
    dlg.deleteLater()


def test_svg_asset_dialog_picking_card_updates_open_quicklook():
    """카드를 클릭(단일선택)하면 이미 열려 있는 확대창도 그 후보로 갱신돼야 한다."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    _gen_n_candidates_direct(dlg, 3)
    dlg._show_enlarged_candidate(0)
    ql = dlg._quicklook
    assert ql._index == 0

    dlg._pick_card(dlg._candidates[2][0])
    assert ql._index == 2
    ql.close()
    dlg.deleteLater()


def test_svg_asset_dialog_quicklook_space_toggles_save_checkbox():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    _gen_n_candidates_direct(dlg, 2)
    dlg._show_enlarged_candidate(0)
    ql = dlg._quicklook
    card = dlg._candidates[0][0]
    assert not card.is_checked_for_save()

    from PyQt6.QtGui import QKeyEvent
    ql.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
    assert card.is_checked_for_save()
    assert "☑" in ql._check_hint.text()

    ql.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier))
    assert not card.is_checked_for_save()
    assert "☐" in ql._check_hint.text()
    ql.close()
    dlg.deleteLater()


def test_svg_asset_dialog_clear_candidates_closes_open_quicklook():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    _gen_n_candidates_direct(dlg, 2)
    dlg._show_enlarged_candidate(0)
    assert dlg._quicklook.isVisible()
    dlg._clear_candidates()
    assert not dlg._quicklook.isVisible()
    dlg.deleteLater()


def test_svg_asset_dialog_enlarge_candidate_closes_on_real_window_deactivate():
    """[2026-08-20 4차 재확인] 바깥 클릭으로 실제로 닫히는지 — 이전 검증은
    `changeEvent()`를 직접 호출해 "통과"했지만, 실측(진짜 top-level 창 두 개를 띄우고
    하나를 활성화)해보니 Qt는 `WindowDeactivate`를 `changeEvent()`가 아니라 `event()`로
    보낸다는 게 드러났다(실사용에서 안 닫히던 원인) — `_QuickLookDialog.event()`로 옮긴
    수정이 실제로 이 실측 경로에서도 닫히는지 이번엔 진짜 창 활성화 전환으로 확인한다."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    _gen_n_candidates_direct(dlg, 1)
    dlg.show()
    QApplication.processEvents()
    dlg._show_enlarged_candidate(0)
    quicklook = dlg._quicklook
    quicklook.show()
    quicklook.activateWindow()
    for _ in range(10):
        QApplication.processEvents()

    other = QWidget()
    other.setWindowTitle("other top-level window")
    other.move(50, 50)
    other.resize(200, 150)
    other.show()
    other.activateWindow()
    other.raise_()
    for _ in range(20):
        QApplication.processEvents()

    assert not quicklook.isVisible()
    other.close()
    dlg.close()
    dlg.deleteLater()


def test_svg_asset_dialog_regenerate_clears_old_candidates():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")

    def fake_generate(key, subject, *, model, **kw):
        return _SAMPLE_SVG, model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate):
        dlg._on_generate_clicked()
        _wait_workers(dlg)
        first_batch = list(dlg._candidates)
        dlg._on_generate_clicked()
        _wait_workers(dlg)
    assert len(dlg._candidates) == 2   # 누적되지 않고 새로 교체
    for card, *_r in first_batch:
        assert card not in [c for c, *_r2 in dlg._candidates]
    dlg.deleteLater()


# ── _SvgAssetDialog: 이미지 첨부(Stage 3, 2026-08-19 — `_MermaidDialog`와 동일 UI 재사용) ──

def test_svg_asset_dialog_browse_image_attaches_and_shows_thumbnail():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
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
    dlg.deleteLater()


def test_svg_asset_dialog_clear_image_hides_chip_and_resets_state():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    real_path = os.path.join(_TMP, f"attach_{uuid.uuid4().hex}.png")
    _mk_pixmap(40, 40).save(real_path)
    dlg._load_image_path(real_path)
    assert dlg._attached_image is not None

    dlg._clear_image()
    assert dlg._attached_image is None
    assert dlg._attached_image_name == ""
    assert dlg._image_chip.isHidden()
    dlg.deleteLater()


def test_svg_asset_dialog_drop_image_file_attaches():
    from PyQt6.QtCore import QUrl
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
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
    dlg.deleteLater()


def test_svg_asset_dialog_ctrl_v_with_clipboard_image_attaches_not_pastes_text():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    pm = _mk_pixmap(40, 20)
    fake_md = type("_MD", (), {"hasImage": lambda self: True, "imageData": lambda self: pm.toImage()})()
    from PyQt6.QtGui import QKeyEvent
    with patch.object(QApplication.clipboard(), "mimeData", return_value=fake_md):
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        handled = dlg.eventFilter(dlg._prompt_edit, ev)
    assert handled is True
    assert dlg._attached_image is not None
    assert dlg._attached_image_name == "붙여넣은 이미지"
    dlg.deleteLater()


def test_svg_asset_dialog_ctrl_v_with_plain_text_clipboard_falls_through():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    fake_md = type("_MD", (), {"hasImage": lambda self: False})()
    from PyQt6.QtGui import QKeyEvent
    with patch.object(QApplication.clipboard(), "mimeData", return_value=fake_md):
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        handled = dlg.eventFilter(dlg._prompt_edit, ev)
    assert handled is False
    assert dlg._attached_image is None
    dlg.deleteLater()


def test_svg_asset_dialog_generate_with_image_and_no_subject_still_generates():
    """이미지 경로는 텍스트 전용 경로와 달리 대상 설명이 필수가 아니다(Mermaid와 동일
    관례) — 이미지가 각 워커에 그대로 전달되는지도 함께 확인."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    real_path = os.path.join(_TMP, f"attach_{uuid.uuid4().hex}.png")
    _mk_pixmap(40, 20).save(real_path)
    dlg._load_image_path(real_path)
    dlg._count_b.setCurrentText("0")   # gpt 1개만 — 검증 단순화

    captured = {}

    def fake_generate(key, subject, *, model, image=None, base_url=None):
        captured["subject"] = subject
        captured["image"] = image
        return _SAMPLE_SVG, model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate):
        dlg._on_generate_clicked()
        _wait_workers(dlg)

    assert captured["subject"] == ""
    assert captured["image"] is not None
    assert len(dlg._candidates) == 1
    dlg.deleteLater()


# ── _SvgAssetDialog: 다중선택+내 심볼 저장(Stage 4, 2026-08-19) ─────────────────

def _gen_two_candidates(dlg):
    def fake_generate(key, subject, *, model, **kw):
        return _SAMPLE_SVG, model
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.generate_svg", fake_generate):
        dlg._on_generate_clicked()
        _wait_workers(dlg)


def test_svg_candidate_checkbox_independent_of_click_selection():
    """체크박스(다중선택, 심볼저장용)와 카드 클릭(단일선택, OK로 삽입용)은 서로 무관해야
    한다 — 하나를 체크해도 다른 카드의 클릭 선택 상태는 안 바뀐다."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    _gen_two_candidates(dlg)
    first_card, _s1, _m1 = dlg._candidates[0]
    second_card, _s2, _m2 = dlg._candidates[1]

    first_card._save_check.setChecked(True)
    assert dlg._checked_for_save_candidates() == [(first_card.svg_text(), _m1)]
    assert dlg._selected_card is first_card   # 클릭 선택은 첫 성공 후보 기본값 그대로

    dlg._pick_card(second_card)
    assert dlg._selected_card is second_card
    assert first_card._save_check.isChecked()   # 클릭 선택 전환이 체크박스를 안 건드림
    dlg.deleteLater()


def test_svg_asset_dialog_save_button_enabled_only_when_something_checked():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    _gen_two_candidates(dlg)
    assert not dlg._save_symbols_btn.isEnabled()

    card, _svg, _model = dlg._candidates[0]
    card._save_check.setChecked(True)
    assert dlg._save_symbols_btn.isEnabled()

    card._save_check.setChecked(False)
    assert not dlg._save_symbols_btn.isEnabled()
    dlg.deleteLater()


def test_svg_asset_dialog_regenerate_resets_save_button():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    _gen_two_candidates(dlg)
    dlg._candidates[0][0]._save_check.setChecked(True)
    assert dlg._save_symbols_btn.isEnabled()

    _gen_two_candidates(dlg)   # 재생성 — 새 카드로 교체되며 체크 상태도 초기화
    assert not dlg._save_symbols_btn.isEnabled()
    dlg.deleteLater()


def test_save_to_symbols_folder_dialog_lists_existing_folders_and_new_folder_field():
    with _isolated_symbol_library():
        symbol_library.create_folder("기존폴더")
        d = _SaveToSymbolsFolderDialog()
        texts = [d._folder_combo.itemText(i) for i in range(d._folder_combo.count())]
        assert texts == ["(미분류)", "기존폴더", "새 폴더…"]
        assert d._new_folder_edit.isHidden()

        d._folder_combo.setCurrentIndex(texts.index("기존폴더"))
        assert d.chosen_folder() == "기존폴더"
        assert d._new_folder_edit.isHidden()

        d._folder_combo.setCurrentIndex(texts.index("새 폴더…"))
        assert not d._new_folder_edit.isHidden()
        d._new_folder_edit.setText("만드는 중인 폴더")
        assert d.chosen_folder() == "만드는 중인 폴더"

        d._folder_combo.setCurrentIndex(texts.index("(미분류)"))
        assert d.chosen_folder() is None
        d.deleteLater()


def test_svg_asset_dialog_save_to_symbols_calls_parent_method_with_checked_entries():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    _gen_two_candidates(dlg)
    card, svg_text, model = dlg._candidates[0]
    card._save_check.setChecked(True)

    class _FakeParent:
        def __init__(self):
            self.calls = []

        def _save_svg_candidates_to_symbols(self, entries, subject, folder):
            self.calls.append((entries, subject, folder))
            return len(entries)

    fake_parent = _FakeParent()

    class _FakeFolderDlg:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def chosen_folder(self):
            return "새폴더"

    with patch.object(dlg, "parent", return_value=fake_parent), \
         patch("easycad.canvas.host_dialogs._SaveToSymbolsFolderDialog", _FakeFolderDlg), \
         patch("easycad.canvas.host_dialogs.symbol_library.load_folders", return_value=[]), \
         patch("easycad.canvas.host_dialogs.symbol_library.create_folder") as create_folder, \
         patch("easycad.canvas.host_dialogs.QMessageBox.information") as info:
        dlg._on_save_to_symbols_clicked()

    create_folder.assert_called_once_with("새폴더")
    assert fake_parent.calls == [([(svg_text, model)], "BNC 커넥터 아이콘", "새폴더")]
    assert info.called
    dlg.deleteLater()


def test_svg_asset_dialog_save_to_symbols_noop_when_nothing_checked():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    _gen_two_candidates(dlg)
    with patch("easycad.canvas.host_dialogs._SaveToSymbolsFolderDialog") as folder_dlg:
        dlg._on_save_to_symbols_clicked()
    assert not folder_dlg.called
    dlg.deleteLater()


def test_svg_asset_dialog_save_to_symbols_warns_when_parent_lacks_method():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    _gen_two_candidates(dlg)
    dlg._candidates[0][0]._save_check.setChecked(True)

    class _FakeFolderDlg:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def chosen_folder(self):
            return None

    with patch.object(dlg, "parent", return_value=object()), \
         patch("easycad.canvas.host_dialogs._SaveToSymbolsFolderDialog", _FakeFolderDlg), \
         patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn:
        dlg._on_save_to_symbols_clicked()
    assert warn.called
    dlg.deleteLater()


def test_svg_asset_dialog_save_to_symbols_cancel_does_nothing():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    dlg._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    _gen_two_candidates(dlg)
    dlg._candidates[0][0]._save_check.setChecked(True)

    class _FakeFolderDlg:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    fake_parent = type("_P", (), {"_save_svg_candidates_to_symbols":
                                   lambda self, *a: 99})()
    with patch.object(dlg, "parent", return_value=fake_parent), \
         patch("easycad.canvas.host_dialogs._SaveToSymbolsFolderDialog", _FakeFolderDlg), \
         patch("easycad.canvas.host_dialogs.QMessageBox.information") as info:
        dlg._on_save_to_symbols_clicked()
    assert not info.called
    dlg.deleteLater()


# ── host_fileio._save_svg_candidates_to_symbols (Stage 4 실제 등록) ────────────

def test_save_svg_candidates_to_symbols_creates_normalized_entries():
    """`_LineItem`/`_RectItem`는 종류에 따라 절대좌표를 `pos`에 담기도, 로컬 도형(rect/
    line)에 담기도 해(전자는 드래그로 옮겨진 도형, 후자는 방금 파싱된 SVG 도형) `pos`
    필드 자체를 직접 비교할 수 없다 — dict를 실제 아이템으로 복원해 합친 bbox의 좌상단이
    원점 근처인지로 정규화 여부를 확인한다(`register_selection_as_symbol`과 동일한
    `_group_scene_rect` 기준)."""
    from easycad.fileio.document import dict_to_item
    with _isolated_symbol_library():
        w = CanvasWindow()
        saved = w._save_svg_candidates_to_symbols(
            [(_SAMPLE_SVG, "gpt-5.4-mini")], "BNC 커넥터", None)
        assert saved == 1
        entries = symbol_library.load_library()
        assert len(entries) == 1
        assert entries[0]["name"] == "BNC 커넥터 — gpt-5.4-mini"
        assert entries[0]["folder"] is None
        restored = [it for it in (dict_to_item(d) for d in entries[0]["items"]) if it is not None]
        box = _group_scene_rect(restored)
        assert abs(box.left()) < 2.0 and abs(box.top()) < 2.0
        w.deleteLater()


def test_save_svg_candidates_to_symbols_uses_model_only_when_subject_empty():
    with _isolated_symbol_library():
        w = CanvasWindow()
        w._save_svg_candidates_to_symbols([(_SAMPLE_SVG, "gemini-3.6-flash")], "", None)
        entries = symbol_library.load_library()
        assert entries[0]["name"] == "gemini-3.6-flash"
        w.deleteLater()


def test_save_svg_candidates_to_symbols_assigns_folder():
    with _isolated_symbol_library():
        w = CanvasWindow()
        w._save_svg_candidates_to_symbols([(_SAMPLE_SVG, "gpt-5.4-mini")], "안테나", "내폴더")
        entries = symbol_library.load_library()
        assert entries[0]["folder"] == "내폴더"
        w.deleteLater()


def test_save_svg_candidates_to_symbols_saves_multiple_and_refreshes_palette():
    with _isolated_symbol_library():
        w = CanvasWindow()
        saved = w._save_svg_candidates_to_symbols(
            [(_SAMPLE_SVG, "gpt-5.4-mini"), (_SAMPLE_SVG, "gemini-3.6-flash")], "안테나", None)
        assert saved == 2
        assert len(symbol_library.load_library()) == 2
        w.deleteLater()


def test_save_svg_candidates_to_symbols_skips_unparseable_entry():
    with _isolated_symbol_library():
        w = CanvasWindow()
        saved = w._save_svg_candidates_to_symbols(
            [("<not valid svg", "gpt-5.4-mini"), (_SAMPLE_SVG, "gemini-3.6-flash")],
            "안테나", None)
        assert saved == 1   # 깨진 것 하나는 건너뛰고 나머지는 저장
        assert len(symbol_library.load_library()) == 1
        w.deleteLater()


# ── host_fileio._insert_ai_svg_asset (삽입 경로) ──────────────────────────────

def test_insert_ai_svg_asset_adds_items_as_single_undo_step():
    w = CanvasWindow()
    before = len(w._scene.items())

    class _FakeDlg:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_svg(self):
            return _SAMPLE_SVG

    with patch("easycad.canvas.host_fileio._SvgAssetDialog", _FakeDlg):
        w._insert_ai_svg_asset()
    after = len(w._scene.items())
    assert after == before + 2   # line + rect
    w.undo()
    assert len(w._scene.items()) == before
    w.redo()
    assert len(w._scene.items()) == before + 2
    w.deleteLater()


def test_insert_ai_svg_asset_cancel_does_nothing():
    w = CanvasWindow()
    before = len(w._scene.items())

    class _FakeDlg:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

        def selected_svg(self):
            return ""

    with patch("easycad.canvas.host_fileio._SvgAssetDialog", _FakeDlg):
        w._insert_ai_svg_asset()
    assert len(w._scene.items()) == before
    w.deleteLater()


# ── host_context._generate_svg_replace (대체 경로) ────────────────────────────

def test_generate_svg_replace_swaps_shape_bbox_long_side_and_center():
    """새 SVG의 긴 변이 대체 도형 bbox 긴 변과 같아야 하고, 중심 위치도 유지돼야 한다."""
    w = CanvasWindow()
    rect = _mk_pen_rect(w, x=100, y=100, ww=200, hh=80)   # bbox 200×80, 긴변 200, 중심(200,140)

    class _FakeDlg:
        def __init__(self, parent=None, confirm_label=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_svg(self):
            return _SAMPLE_SVG   # 원본 viewBox 100×100(정사각) — 긴 변 기준으로만 스케일

    with patch("easycad.canvas.host_context._SvgAssetDialog", _FakeDlg):
        w._generate_svg_replace(rect)

    assert rect.scene() is None   # 옛 도형은 씬에서 빠짐
    new_items = [it for it in w._scene.items()
                if isinstance(it, _LineItem) or isinstance(it, _RectItem)]
    assert len(new_items) >= 1
    combined = QRectF()
    for it in new_items:
        combined = combined.united(it.mapToScene(it.boundingRect()).boundingRect()) \
            if not combined.isNull() else it.mapToScene(it.boundingRect()).boundingRect()
    assert abs(max(combined.width(), combined.height()) - 200.0) < 5.0
    assert abs(combined.center().x() - 200.0) < 5.0
    assert abs(combined.center().y() - 140.0) < 5.0
    w.deleteLater()


def test_generate_svg_replace_is_single_undo_step():
    w = CanvasWindow()
    rect = _mk_pen_rect(w, x=0, y=0, ww=100, hh=100)
    before = len(w._scene.items())

    class _FakeDlg:
        def __init__(self, parent=None, confirm_label=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_svg(self):
            return _SAMPLE_SVG

    with patch("easycad.canvas.host_context._SvgAssetDialog", _FakeDlg):
        w._generate_svg_replace(rect)
    assert len(w._scene.items()) == before + 2 - 1   # -1(제거된 rect) +2(신규)

    w.undo()
    assert rect.scene() is w._scene
    assert len(w._scene.items()) == before

    w.redo()
    assert rect.scene() is None
    assert len(w._scene.items()) == before + 1
    w.deleteLater()


def test_generate_svg_replace_leaves_bound_arrow_frozen_not_rebound():
    """계획서 확정 스코프 — 화살표는 자동 재연결하지 않는다. `delete_selection()`이 이미
    제공하는 "도형만 지우면 화살표가 sh.scene() is not None 가드에 걸려 제자리에
    얼어붙는다"는 동작과 같은 결과가 나야 한다(별도 언바인드 구현이 없어도)."""
    w = CanvasWindow()
    rect = _mk_pen_rect(w, x=0, y=0, ww=100, hh=100)
    other = _mk_pen_rect(w, x=300, y=0, ww=100, hh=100)
    arrow = _mk_bound_sarrow(w, rect, other, 1, 3)   # rect의 E포트 → other의 W포트
    before_pts = [arrow.mapToScene(p) for p in arrow._pts]

    class _FakeDlg:
        def __init__(self, parent=None, confirm_label=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def selected_svg(self):
            return _SAMPLE_SVG

    with patch("easycad.canvas.host_context._SvgAssetDialog", _FakeDlg):
        w._generate_svg_replace(rect)

    assert arrow._bind_start is rect   # 재바인딩 안 됨(옛 도형을 계속 가리킴)
    after_pts = [arrow.mapToScene(p) for p in arrow._pts]
    assert [(p.x(), p.y()) for p in before_pts] == [(p.x(), p.y()) for p in after_pts]
    w.deleteLater()


def test_generate_svg_replace_cancel_keeps_original_shape():
    w = CanvasWindow()
    rect = _mk_pen_rect(w, x=0, y=0, ww=100, hh=100)

    class _FakeDlg:
        def __init__(self, parent=None, confirm_label=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

        def selected_svg(self):
            return ""

    with patch("easycad.canvas.host_context._SvgAssetDialog", _FakeDlg):
        w._generate_svg_replace(rect)
    assert rect.scene() is w._scene
    w.deleteLater()


# ── 메뉴/툴바/컨텍스트메뉴 배선 ─────────────────────────────────────────────────

def test_ai_svg_menu_action_exists_with_shortcut():
    w = CanvasWindow()
    assert hasattr(w, "_act_ai_svg")
    assert w._act_ai_svg.shortcut().toString() == "Ctrl+Shift+A"
    w.deleteLater()


def test_ai_svg_action_is_on_toolbar():
    """2026-08-13 재개편(모든 삽입 메뉴 항목을 상단 툴바에도) 관례를 그대로 따른다."""
    w = CanvasWindow()
    assert w._act_ai_svg in w._toolbar.actions()
    w.deleteLater()


def test_context_menu_offers_svg_generate_for_single_rect_selection():
    w = CanvasWindow()
    rect = _mk_pen_rect(w, x=0, y=0, ww=100, hh=100)
    rect.setSelected(True)
    menu = w._build_context_menu()
    texts = [a.text() for a in menu.actions()]
    assert any("SVG로 생성" in t for t in texts)
    w.deleteLater()


def test_context_menu_omits_svg_generate_for_multi_selection():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=100, hh=100)
    b = _mk_pen_rect(w, x=200, y=0, ww=100, hh=100)
    a.setSelected(True)
    b.setSelected(True)
    menu = w._build_context_menu()
    texts = [act.text() for act in menu.actions()]
    assert not any("SVG로 생성" in t for t in texts)
    w.deleteLater()


def test_context_menu_omits_svg_generate_for_arrow_selection():
    w = CanvasWindow()
    ar = _mk_arrow(w, 0, 0, 100, 100)
    ar.setSelected(True)
    menu = w._build_context_menu()
    texts = [act.text() for act in menu.actions()]
    assert not any("SVG로 생성" in t for t in texts)
    w.deleteLater()


# ── §8 항목23 Stage 6(2026-08-19) — 레이아웃 최종 통일(목업 시각 언어 차용) ────────

def test_svg_asset_dialog_default_confirm_label_is_insert():
    """호출부가 안 넘기면(host_fileio._insert_ai_svg_asset 경로) 기본값 "도형 삽입"."""
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog()
    ok_btn = dlg._btns.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_btn.text() == "확인 (도형 삽입)"


def test_svg_asset_dialog_custom_confirm_label_used_for_replace():
    with patch.object(_SvgAssetDialog, "_populate_models", lambda self: None):
        dlg = _SvgAssetDialog(confirm_label="확인 (도형 대체)")
    ok_btn = dlg._btns.button(QDialogButtonBox.StandardButton.Ok)
    assert ok_btn.text() == "확인 (도형 대체)"


def test_generate_svg_replace_passes_replace_confirm_label():
    """host_context._generate_svg_replace가 실제로 "도형 대체" 라벨을 넘기는지 —
    대체 진입점은 새로 삽입이 아니라 기존 도형을 바꾸는 것이므로 라벨이 달라야 한다."""
    w = CanvasWindow()
    rect = _mk_pen_rect(w, x=0, y=0, ww=100, hh=100)
    captured = {}

    class _FakeDlg:
        def __init__(self, parent=None, confirm_label=None):
            captured["confirm_label"] = confirm_label

        def exec(self):
            return QDialog.DialogCode.Rejected

        def selected_svg(self):
            return ""

    with patch("easycad.canvas.host_context._SvgAssetDialog", _FakeDlg):
        w._generate_svg_replace(rect)
    assert captured["confirm_label"] == "확인 (도형 대체)"
    w.deleteLater()
