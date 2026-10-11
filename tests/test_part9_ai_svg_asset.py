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

(2026-10-11 §8 항목36 6단계) `_SvgAssetDialog`와 그 삽입·대체 경로는 지웠다 — 아래 목록 중
창·삽입·대체 항목의 테스트도 함께 지웠고, 생성은 「AI로 만들기」 패널(`test_part29_ai_panel.py`)이 맡는다.

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
from PyQt6.QtCore import QRectF, QPointF

from _shared import *  # noqa: F401,F403

from easycad.ai import gateway as gw  # noqa: E402
from easycad.ai import text_to_svg as tts  # noqa: E402
from easycad.fileio.svg_import import parse_svg_items, parse_svg_string  # noqa: E402
from easycad.fileio import symbol_library  # noqa: E402
from easycad.canvas.host_dialogs import (  # noqa: E402
    _SaveToSymbolsFolderDialog,
)
from easycad.canvas.host_selection import _group_scene_rect  # noqa: E402

_SAMPLE_SVG = ('<svg viewBox="0 0 100 100">'
              '<line x1="10" y1="10" x2="90" y2="90"/>'
              '<rect x="20" y="20" width="30" height="30"/>'
              '</svg>')


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


# ── 2026-08-20 재피드백 5건 ──────────────────────────────────────────────────


def test_save_to_symbols_folder_dialog_lists_existing_folders_and_new_folder_field():
    with _isolated_symbol_library():
        symbol_library.create_folder("기존폴더")
        d = _SaveToSymbolsFolderDialog()
        texts = [d._folder_combo.itemText(i) for i in range(d._folder_combo.count())]
        assert texts == ["기존폴더", "새 폴더…"]   # [2026-10-11] 「(미분류)」 없음
        assert d._folder_combo.currentText() == "기존폴더"   # 처음 값 = 마지막에 쓴(없으면 첫) 폴더
        assert d._new_folder_edit.isHidden()

        d._folder_combo.setCurrentIndex(texts.index("기존폴더"))
        assert d.chosen_folder() == "기존폴더"
        assert d._new_folder_edit.isHidden()

        d._folder_combo.setCurrentIndex(texts.index("새 폴더…"))
        assert not d._new_folder_edit.isHidden()
        d._new_folder_edit.setText("만드는 중인 폴더")
        assert d.chosen_folder() == "만드는 중인 폴더"

        d.deleteLater()


def test_save_to_symbols_folder_dialog_without_folders_offers_default_name():
    """[2026-10-11] 폴더가 하나도 없으면 「새 폴더…」가 골라진 채 기본 이름 「내 심볼」이 채워져 있다."""
    with _isolated_symbol_library():
        d = _SaveToSymbolsFolderDialog()
        assert d._folder_combo.currentData() == "__new__"
        assert not d._new_folder_edit.isHidden() and d.chosen_folder() == "내 심볼"
        d.deleteLater()


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
        assert entries[0]["folder"] == "내 심볼"   # [2026-10-11] 폴더 없이 저장하면 기본 폴더
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


# ── 메뉴/툴바/컨텍스트메뉴 배선 ─────────────────────────────────────────────────

def test_ai_svg_menu_action_exists_with_shortcut():
    w = CanvasWindow()
    assert hasattr(w, "_act_ai_svg")
    assert w._act_ai_svg.shortcut().toString() == "Ctrl+Shift+A"
    w.deleteLater()


def test_ai_svg_action_is_on_toolbar():
    """2026-08-13 재개편(모든 삽입 메뉴 항목을 상단 툴바에도) 관례 — [§8 항목36, 2026-10-05] AI 생성
    아이콘 셋(Mermaid·SVG·사진)은 상단바에서 「AI로 만들기」 하나로 합쳤다(사용자 결정). 삽입 메뉴 항목은
    6단계부터 패널을 심볼로 연다."""
    w = CanvasWindow()
    assert w._act_ai_make in w._toolbar.actions()
    assert w._act_ai_svg not in w._toolbar.actions()
    menu_acts = [a for m in w.menuBar().actions() if m.menu() for a in m.menu().actions()]
    assert w._act_ai_svg in menu_acts
    w.deleteLater()


def test_context_menu_offers_svg_generate_for_single_rect_selection():
    w = CanvasWindow()
    rect = _mk_pen_rect(w, x=0, y=0, ww=100, hh=100)
    rect.setSelected(True)
    menu = w._build_context_menu()
    texts = [a.text() for a in menu.actions()]
    assert any("AI로 바꾸기" in t for t in texts)
    w.deleteLater()


def test_context_menu_omits_svg_generate_for_multi_selection():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0, ww=100, hh=100)
    b = _mk_pen_rect(w, x=200, y=0, ww=100, hh=100)
    a.setSelected(True)
    b.setSelected(True)
    menu = w._build_context_menu()
    texts = [act.text() for act in menu.actions()]
    assert not any("AI로 바꾸기" in t for t in texts)
    w.deleteLater()


def test_context_menu_omits_svg_generate_for_arrow_selection():
    w = CanvasWindow()
    ar = _mk_arrow(w, 0, 0, 100, 100)
    ar.setSelected(True)
    menu = w._build_context_menu()
    texts = [act.text() for act in menu.actions()]
    assert not any("AI로 바꾸기" in t for t in texts)
    w.deleteLater()


# ── §8 항목23 Stage 6(2026-08-19) — 레이아웃 최종 통일(목업 시각 언어 차용) ────────
