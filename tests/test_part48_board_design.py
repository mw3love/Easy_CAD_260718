"""§8 항목60 보드 디자인 2차(2026-10-17) — 아티팩트 시안과 나란히 본 실사용 피드백.

① 글 안 부분 강조 「**구절**」 — 문장 전체가 아니라 그 구절만 코랄·굵게, .ecad 저장·다시 열기·복제에도 남는다.
"""
import json

from _shared import *  # noqa: F401,F403

from easycad.ai import pdf_to_board as pb
from easycad.canvas.host_board import _ACCENT, INK_ON_LIGHT, _map_spans, _wrap, split_emph
from easycad.fileio.document import dict_to_item, item_to_dict
from test_part41_paper_board import _close, _window  # noqa: F401
from test_part46_block_board import PAPER


def test_split_emph_strips_markers_and_stray_stars():
    assert split_emph("앞 **모든 단어를 한 번에** 보자") == ("앞 모든 단어를 한 번에 보자", [(2, 13)])
    assert split_emph("**a** b **c**") == ("a b c", [(0, 1), (4, 5)])
    assert split_emph("짝 없는 ** 별표") == ("짝 없는  별표", [])
    assert split_emph("") == ("", [])


def test_map_spans_follows_wrap_breaks():
    """줄바꿈이 띄어쓰기를 바꾸든 긴 낱말을 쪼개든 구간이 같은 글자를 가리킨다."""
    from PyQt6.QtGui import QFont, QFontMetricsF
    fm = QFontMetricsF(QFont())
    plain = "가나다라마바사아자차카타파하 " * 3 + "핵심구절"
    spans = [(len(plain) - 4, len(plain))]
    wrapped = _wrap(plain, fm, fm.horizontalAdvance("가나다라마") + 1)
    assert "\n" in wrapped
    (a, b), = _map_spans(plain, wrapped, spans)
    assert wrapped[a:b].replace("\n", "") == "핵심구절"


def _texts(added):
    return [it for it in added if hasattr(it, "toPlainText")]


def test_headline_emphasis_only_phrase_is_accent_and_survives_save():
    w = _window()
    blocks = [dict(b) for b in PAPER["blocks"]]
    blocks[0]["hero"] = True
    blocks[0]["items"] = [dict(blocks[0]["items"][0], body="단어마다 **관련 깊은 단어**에 점수를 준다."), blocks[0]["items"][1]]
    spec = pb.parse_board(json.dumps(dict(PAPER, blocks=blocks, headline="앞 단어를 기다리지 말고, **모든 단어를 한 번에** 보자"),
                                     ensure_ascii=False))
    _n, _a, _d, added = w._build_paper_board(pb.dump_board(spec))
    head = next(it for it in _texts(added) if it.toPlainText().replace("\n", " ").startswith("앞 단어를"))
    assert "**" not in head.toPlainText()
    assert head.defaultTextColor().name() != QColor(_ACCENT).name()   # 문장 전체는 코랄이 아니다(주인공 면 위라 크림)
    runs = head.text_runs()
    assert runs and all(r[2] == QColor(_ACCENT).name() and r[3] for r in runs)   # 줄이 바뀌면 줄마다 한 조각
    assert " ".join(head.toPlainText()[r[0]:r[0] + r[1]] for r in runs) == "모든 단어를 한 번에"
    card = next(it for it in _texts(added) if it.toPlainText().startswith("단어마다"))
    assert [card.toPlainText()[r[0]:r[0] + r[1]] for r in card.text_runs()] == ["관련 깊은 단어"]
    # .ecad 저장 → 다시 열기, 복제
    d = item_to_dict(head)
    assert d["runs"] == runs
    again = dict_to_item(json.loads(json.dumps(d)))
    assert again.text_runs() == runs and again.toPlainText() == head.toPlainText()
    assert head.clone().text_runs() == runs
    _close(w)


def test_headline_without_markers_stays_all_accent():
    """옛 설계서(표시 없음)는 전처럼 헤드라인 전체 코랄 — 강조가 사라지지 않게."""
    w = _window()
    spec = pb.parse_board(json.dumps(dict(PAPER, headline="모든 단어를 한 번에 보자"), ensure_ascii=False))
    _n, _a, _d, added = w._build_paper_board(pb.dump_board(spec))
    head = next(it for it in _texts(added) if it.toPlainText() == "모든 단어를 한 번에 보자")
    assert head.defaultTextColor().name() == QColor(_ACCENT).name() and head.text_runs() == []
    plain = next(it for it in _texts(added) if it.toPlainText().startswith("단어마다"))
    assert plain.text_runs() == [] and "runs" not in item_to_dict(plain)
    assert plain.defaultTextColor().name() == QColor(INK_ON_LIGHT).name()
    _close(w)


def test_board_font_pretendard_weights_survive_save():
    """② 보드 글꼴 — 앱에 실은 Pretendard, 제목 아주 굵게(800)·부제 약간 굵게(600)·본문 보통. 저장·다시 열기에도 같은 글꼴·굵기."""
    from easycad.fonts import BOARD_FONT, ensure_fonts
    assert ensure_fonts()
    w = _window()
    spec = pb.parse_board(json.dumps(PAPER, ensure_ascii=False))
    _n, _a, _d, added = w._build_paper_board(pb.dump_board(spec))
    texts = _texts(added)
    title = next(it for it in texts if it.toPlainText() == "Attention Is All You Need")
    sub = next(it for it in texts if it.toPlainText().replace("\n", " ").startswith("문장 안 모든"))
    body = next(it for it in texts if it.toPlainText().startswith("단어마다"))
    assert {it.font().family() for it in (title, sub, body)} == {BOARD_FONT}
    assert (title.font().weight(), sub.font().weight(), body.font().weight()) == (800, 600, 400)
    for it in (title, sub, body):
        again = dict_to_item(json.loads(json.dumps(item_to_dict(it))))
        assert (again.font().family(), again.font().weight()) == (BOARD_FONT, it.font().weight())
    _close(w)


def _fake_figure(w_px, h_px):
    from PyQt6.QtGui import QPixmap
    pm = QPixmap(w_px, h_px)
    pm.fill(QColor("#88aacc"))
    return pm


def test_tall_figure_goes_to_side_column_full_height():
    """③ 세로로 긴 그림은 오른쪽 옆 칸에 여러 줄에 걸쳐 크게 — 옆 칸과 나란한 블록은 그림 왼쪽에, 설명은 그림 아래."""
    from unittest.mock import patch
    from easycad.canvas.annotator_core import _BoardItem, _ImageItem
    w = _window()
    spec = pb.parse_board(json.dumps(PAPER, ensure_ascii=False))
    with patch.object(type(w), "_pb_figure_source", lambda self, s, f: _fake_figure(300, 500)):
        _n, _a, _d, added = w._build_paper_board(pb.dump_board(spec))
    board = next(it for it in added if isinstance(it, _BoardItem))
    img = next(it for it in added if isinstance(it, _ImageItem))
    ir, br = img.sceneBoundingRect(), board.sceneBoundingRect()
    assert ir.height() > br.height() * 0.5                     # 보드 높이의 절반 넘게
    assert ir.right() > br.left() + br.width() * 0.7           # 오른쪽 옆 칸
    beside = [it for it in added if getattr(it, "_pb_part", None) not in (None, "title", "blocks[3]") and not isinstance(it, _BoardItem)
              and it.sceneBoundingRect().top() < ir.bottom() and it.sceneBoundingRect().bottom() > ir.top()]
    assert beside and all(it.sceneBoundingRect().right() <= ir.left() + 1 for it in beside)
    cap = next(it for it in added if hasattr(it, "toPlainText") and it.toPlainText() == "그림 1")
    assert cap.sceneBoundingRect().top() >= ir.bottom() - 1
    _close(w)


def test_wide_figure_stays_in_row():
    """가로 그림은 옛 배치 그대로(그 줄 안)."""
    from unittest.mock import patch
    from easycad.canvas.annotator_core import _BoardItem, _ImageItem
    w = _window()
    spec = pb.parse_board(json.dumps(PAPER, ensure_ascii=False))
    with patch.object(type(w), "_pb_figure_source", lambda self, s, f: _fake_figure(600, 300)):
        _n, _a, _d, added = w._build_paper_board(pb.dump_board(spec))
    board = next(it for it in added if isinstance(it, _BoardItem))
    img = next(it for it in added if isinstance(it, _ImageItem))
    assert img.sceneBoundingRect().height() < board.sceneBoundingRect().height() * 0.5
    _close(w)


STEPS = {"type": "steps", "title": "어텐션은 어떻게 정보를 고르나", "pages": "p.3", "row": 2, "span": 8,
         "items": [{"text": "질의·키·값 준비", "sym": "Q K V"}, {"text": "질의와 키를 곱함", "sym": "QKᵀ"},
                   {"text": "softmax로 비중 결정", "sym": "softmax"}, {"text": "값을 가중합", "sym": "× V"}],
         "focus": 3, "note": "관련 깊은 단어에 더 큰 비중."}


def test_steps_block_parses():
    spec = pb.parse_board(json.dumps(dict(PAPER, blocks=PAPER["blocks"] + [STEPS]), ensure_ascii=False))
    blk = next(b for b in spec["blocks"] if b["type"] == "steps")
    assert [i["sym"] for i in blk["items"]] == ["Q K V", "QKᵀ", "softmax", "× V"] and blk["focus"] == 3 and blk["note"]
    bad = pb.parse_board(json.dumps(dict(PAPER, blocks=PAPER["blocks"] + [dict(STEPS, focus=9, items=STEPS["items"][:1])]), ensure_ascii=False))
    assert not any(b["type"] == "steps" for b in bad["blocks"])   # 한 단계뿐이면 버린다
    assert "steps" in pb._BLOCK_FORMAT


def test_steps_block_one_row_left_to_right_focus_accent():
    """④ 가로 단계 — 꺾이지 않고 한 줄(왼쪽→오른쪽), 핵심 단계 하나만 코랄 면. 「도면 검사」 문제 0."""
    from easycad.canvas.annotator_core import _BoardItem, _RectItem
    from easycad.canvas.drawing_check import check_drawing
    w = _window()
    blocks = [b for b in PAPER["blocks"] if b["type"] != "flow"] + [STEPS]
    spec = pb.parse_board(json.dumps(dict(PAPER, blocks=blocks), ensure_ascii=False))
    _n, _a, _d, added = w._build_paper_board(pb.dump_board(spec))
    part = f"blocks[{next(i for i, b in enumerate(spec['blocks']) if b['type'] == 'steps')}]"
    texts = [next(it for it in added if hasattr(it, "toPlainText") and it.toPlainText().replace("\n", " ") == s["text"])
             for s in STEPS["items"]]
    ys = {round(t.sceneBoundingRect().top()) for t in texts}
    xs = [t.sceneBoundingRect().left() for t in texts]
    assert len(ys) == 1 and xs == sorted(xs)
    cards = [it for it in added if isinstance(it, _RectItem) and getattr(it, "_pb_part", None) == part and it.rect().height() > 20]
    accent = [c for c in cards if c.brush().color().name() == QColor(_ACCENT).name()]
    assert len(cards) == 4 and len(accent) == 1
    assert accent[0].sceneBoundingRect().contains(texts[2].sceneBoundingRect().center())
    board = next(it for it in added if isinstance(it, _BoardItem))
    assert check_drawing(w._scene, items=[it for it in w._board_scope(board) if it is not board]) == []
    _close(w)


def test_number_with_other_unit_gets_other_color():
    """⑤ 숫자 — 모두 같은 무리 색인데 단위가 다른 숫자(「3.5일」)는 다른 색. 무리를 AI가 나눴으면 그대로."""
    w = _window()
    same = [{"label": "BLEU", "value": "28.4"}, {"label": "BLEU", "value": "41.8"}, {"label": "학습", "value": "3.5일"}]
    cols = w._bb_number_colors({}, same)
    assert cols[0] == cols[1] == _ACCENT and cols[2] == w._BB_BLUE
    spec = {"groups": ["성능", "비용"]}
    grouped = [dict(same[0], group="비용"), dict(same[1], group="비용"), dict(same[2], group="성능")]
    assert w._bb_number_colors(spec, grouped) == [w._BB_GROUP_COLORS[1], w._BB_GROUP_COLORS[1], w._BB_GROUP_COLORS[0]]
    assert w._bb_number_colors({}, same[:2]) == [_ACCENT, _ACCENT]
    times = [{"label": "기본", "value": "12시간"}, {"label": "대형", "value": "3.5일"}]   # 시간 단위끼리는 한 무리(실제 KAIROS)
    assert w._bb_number_colors({}, times) == [_ACCENT, _ACCENT]
    _close(w)


def test_verdict_tags_are_chips():
    """⑤ 의의·한계 — 색 글자만이 아니라 옅은 색 딱지(칩) 위에."""
    from easycad.canvas.annotator_core import _RectItem
    w = _window()
    spec = pb.parse_board(json.dumps(PAPER, ensure_ascii=False))
    _n, _a, _d, added = w._build_paper_board(pb.dump_board(spec))
    for tag in ("한계", "문서 밖 맥락"):
        t = next(it for it in added if hasattr(it, "toPlainText") and it.toPlainText() == tag)
        chips = [r for r in added if isinstance(r, _RectItem) and r.brush().color().alpha() == 40
                 and r.sceneBoundingRect().contains(t.sceneBoundingRect().center())]
        assert chips and chips[0].brush().color().rgb() == t.defaultTextColor().rgb()
    _close(w)


def test_numbers_narrow_stack_lying_tiles_without_breaking_words():
    """좁은 칸의 숫자 — 세운 타일을 두 줄로 꺾지 않고(줄이 높아져 옆 진한 면이 텅 빔) 누운 타일을 세로로, 이름 낱말이 안 끊긴다."""
    w = _window()
    items = [{"label": "영어→독일어", "value": "28.4", "note": "BLEU"}, {"label": "영어→프랑스어", "value": "41.8", "note": "BLEU"},
             {"label": "big 모델 학습", "value": "3.5일", "note": "GPU 8장"}]
    added = []
    w._bb_numbers(added, items, 0.0, 0.0, 360.0, 1.0)
    labels = [next(it for it in added if hasattr(it, "toPlainText") and it.toPlainText() == i["label"]) for i in items]
    ys = [t.sceneBoundingRect().top() for t in labels]
    assert ys == sorted(ys) and len(set(round(y) for y in ys)) == 3          # 세로로 하나씩
    wide = []
    w._bb_numbers(wide, items, 0.0, 0.0, 900.0, 1.0)                           # 넓으면 옛처럼 한 줄
    assert len({round(it.sceneBoundingRect().top()) for it in wide if hasattr(it, "toPlainText") and it.toPlainText() in
                {i["label"] for i in items}}) == 1
    w._pb_discard(added + wide)
    _close(w)


def test_piece_frame_stays_under_inner_card_faces():
    """조각 틀(종이색)은 안쪽 카드 면 아래 — 같은 높이면 나중에 놓인 틀이 단계 카드·칩을 덮어 크림 글이 종이 위에 떴다(실제 창)."""
    from easycad.canvas.annotator_core import _RectItem
    w = _window()
    items, _h = w._piece_make({}, dict(STEPS), 0.0, 0.0)
    frame = next(it for it in items if getattr(it, "_pb_piece", None))
    faces = [it for it in items if isinstance(it, _RectItem) and it is not frame and it.rect().height() > 20]
    assert faces and all(f.zValue() > frame.zValue() for f in faces)
    w._pb_discard(items)
    _close(w)


def test_number_unit_never_wraps_in_lying_tile():
    """누운 숫자 타일의 단위는 한 줄(「2.04 BLEU」가 「BLE / U」로 꺾였다)."""
    w = _window()
    added = []
    items = [{"label": "번역 향상", "value": "2.04BLEU"}, {"label": "base 학습", "value": "12시간"}, {"label": "big 학습", "value": "3.5일"}]
    w._bb_numbers(added, items, 0.0, 0.0, 300.0, 1.0)
    unit = next(it for it in added if hasattr(it, "toPlainText") and it.toPlainText().replace("\n", "") == "BLEU")
    assert "\n" not in unit.toPlainText()
    w._pb_discard(added)
    _close(w)


def test_three_cards_never_leave_a_hole():
    """카드 셋은 2×2(한 칸 빔) 대신 한 줄에 셋 또는 세로로."""
    w = _window()
    cards = [{"name": f"카드{i}", "body": "짧은 설명.", "pages": "", "group": ""} for i in range(3)]
    for width in (560.0, 360.0):
        added = []
        w._bb_cards(added, cards, 0.0, 0.0, width, 1.0)
        names = [next(it for it in added if hasattr(it, "toPlainText") and it.toPlainText() == f"카드{i}") for i in range(3)]
        tops = {round(t.sceneBoundingRect().top()) for t in names}
        lefts = {round(t.sceneBoundingRect().left()) for t in names}
        assert len(tops) == 1 or len(lefts) == 1, (width, tops, lefts)
        w._pb_discard(added)
    _close(w)


def test_bars_commas_and_blue_when_no_mine():
    """막대 — 천 단위 쉼표, 「우리 것」이 없으면 모두 파랑(전부 회색이면 꺼진 화면 같았다 — 회의록 예산)."""
    from easycad.canvas.annotator_core import _RectItem
    w = _window()
    added = []
    blk = {"bars": [{"label": "서버", "value": 11800, "mine": False}, {"label": "전원", "value": 1800, "mine": False}], "note": ""}
    w._bb_bars(added, blk, 0.0, 0.0, 500.0, 1.0)
    assert any(hasattr(it, "toPlainText") and it.toPlainText() == "11,800" for it in added)
    bars = [it for it in added if isinstance(it, _RectItem)]
    assert bars and all(b.brush().color().name() == QColor(w._BB_BLUE).name() for b in bars)
    w._pb_discard(added)
    _close(w)


def test_compound_korean_amount_drawn_whole():
    """「1억 4,200만 원」은 「1」 + 작은 단위가 아니라 통째로 한 크기."""
    w = _window()
    added = []
    w._bb_number_value(added, "1억 4,200만 원", 0.0, 0.0, 300.0, 26, "#3d7fb8")
    texts = [it for it in added if hasattr(it, "toPlainText")]
    assert len(texts) == 1 and texts[0].toPlainText().replace("\n", " ") == "1억 4,200만 원"
    w._pb_discard(added)
    _close(w)


def test_wide_flow_cell_shrinks_and_neighbor_takes_columns():
    """흐름도보다 많이 넓은 칸은 흐름도 크기로(최소 4칸) 줄이고, 남는 칸은 같은 줄 다른 블록이 받는다. 상자 글은 보드 글꼴."""
    from easycad.fonts import BOARD_FONT
    w = _window()
    flow = {"direction": "TD", "lanes": [], "steps": [{"id": "a", "text": "시작"}, {"id": "b", "text": "끝"}],
            "links": [{"from": "a", "to": "b"}], "focus": "b"}
    blocks = [{"type": "flow", "title": "흐름", "row": 1, "span": 8, "flow": flow},
              {"type": "list", "title": "목록", "row": 1, "span": 4, "items": ["하나", "둘"]}]
    spec = pb.parse_board(json.dumps({"kind": "block-board", "title": "T", "blocks": blocks}, ensure_ascii=False))
    rows = w._bb_rows(dict(spec, blocks=[dict(b, _i=i) for i, b in enumerate(spec["blocks"])]), 112.0)
    spans = {b["type"]: sp for _i, b, sp in rows[0]}
    assert spans["flow"] < 8 and spans["flow"] + spans["list"] == 12
    _n, _a, _d, added = w._build_paper_board(pb.dump_board(spec))
    labels = [it._label for it in added if getattr(it, "_flow_key", None) and hasattr(it, "_label_alive") and it._label_alive()]
    assert labels and all(lb.font().family() == BOARD_FONT for lb in labels)
    _close(w)


# ---- 작은 것 셋 + 슬라이드 그림(§8 항목60 5라운드) ---------------------------------------------------------------------

def _slide_pdf(path):
    """가로 슬라이드 한 쪽 — 제목 줄 옆 아이콘(본문에 살짝 걸침), 작은 사진 셋을 잇는 선, 짧은 이름표, 강조 상자가 든 긴 문단."""
    import fitz
    from PyQt6.QtGui import QImage
    img = QImage(40, 30, QImage.Format.Format_RGB32); img.fill(QColor("#336699"))
    png = str(path) + ".png"; img.save(png)
    doc = fitz.open(); p = doc.new_page(width=720, height=540)
    font = r"C:\Windows\Fonts\malgun.ttf"
    p.insert_text((40, 30), "SLIDE TITLE", fontsize=20)
    p.insert_image(fitz.Rect(400, 15, 520, 105), filename=png)            # 제목 줄 장식(가운데가 제목 줄)
    for x, y in ((60, 300), (300, 330), (600, 300)):
        p.insert_image(fitz.Rect(x, y, x + 60, y + 40), filename=png)
    p.draw_line((120, 320), (300, 350), color=(0.2, 0.5, 0.8), width=3)
    p.draw_line((360, 350), (600, 320), color=(0.2, 0.5, 0.8), width=3)
    p.insert_text((60, 290), "메인 장비", fontsize=10, fontname="malgun", fontfile=font)
    p.insert_text((300, 395), "체인지오버", fontsize=10, fontname="malgun", fontfile=font)
    p.draw_rect(fitz.Rect(60, 131, 200, 146), color=None, fill=(1, 0.6, 0.2))   # 문단 안 강조 상자(글 줄 위)
    p.insert_textbox(fitz.Rect(40, 130, 680, 200), "이 장비는 외부 기준 신호에 맞춰 안정적인 동기 신호를 만들고, 이상이 생기면 예비로 절체하는 기능을 갖추고 있습니다.",
                     fontsize=11, fontname="malgun", fontfile=font)
    doc.save(str(path))
    return str(path)


def test_slide_figure_rect_wraps_photos_lines_labels_only(tmp_path):
    """슬라이드 그림 자리 = 본문의 사진·선·이름표만 — 제목 줄 장식·문단(과 그 안 강조 상자)은 빼고, 이름표는 반쯤 자르지 않는다."""
    import fitz
    from easycad.fileio.pdf_figure import figure_labels, figure_rect
    pdf = _slide_pdf(tmp_path / "slide.pdf")
    with fitz.open(pdf) as doc:
        r = figure_rect(doc[0])
        assert r is not None
        assert r.y0 > 200                      # 제목 줄 아이콘·문단(130~200)·강조 상자는 안 들어감
        assert r.x0 <= 60 and r.x1 >= 660      # 왼쪽 사진 ~ 오른쪽 사진
        assert r.y1 >= 395                     # 아래 이름표까지 통째로
        labels = figure_labels(doc[0], r)
        assert "메인 장비" in labels and "체인지오버" in labels and "기준 신호" not in labels


def test_figure_hint_lists_figure_pages(tmp_path):
    hint = pb.figure_hint([(None, _slide_pdf(tmp_path / "s.pdf"))])
    assert "p.1:" in hint and "체인지오버" in hint and "대표 그림" in hint
    assert pb.figure_hint([(None, str(tmp_path / "없는.pdf"))]) == ""


def test_pieces_do_not_land_on_other_pieces():
    """두 보드의 조각이 같은 자리로 펼쳐져도 겹치지 않는다(세 모델 보드: 조각 40개 중 17쌍이 겹쳤다)."""
    from PyQt6.QtCore import QRectF
    w = _window()
    spec = pb.parse_board(json.dumps(dict(PAPER, more=[{"type": "quote", "text": "인용 하나", "row": 1, "span": 6},
                                                       {"type": "list", "items": ["하나", "둘"], "row": 1, "span": 6}]),
                                     ensure_ascii=False))
    near = QRectF(0, 0, 1000, 600)
    a = w._pieces_place(spec, near)
    b = w._pieces_place(spec, near)
    ra = w._ai_items_rect(a); rb = w._ai_items_rect(b)
    assert not ra.intersects(rb)
    _close(w)


def test_fill_hex_input_applies_and_shows_current():
    w = _window()
    from easycad.canvas.annotator_core import _RectItem
    from PyQt6.QtCore import QRectF
    r = _RectItem(QRectF(0, 0, 100, 60)); w._scene.addItem(r)
    r.setFlag(r.GraphicsItemFlag.ItemIsSelectable); r.setSelected(True)
    w._refresh_properties()
    w._pf_fill_hex.setText("d9703f"); w._apply_fill_hex()
    assert r.brush().color().name() == "#d9703f"
    w._refresh_properties()
    assert w._pf_fill_hex.text().lower().startswith("#") and "d9703f" in w._pf_fill_hex.text().lower()
    w._pf_fill_hex.setText("이상한값"); w._apply_fill_hex()   # 틀린 값은 무시하고 지금 값으로
    assert r.brush().color().name() == "#d9703f"
    w.undo()
    assert r.brush().color().name() != "#d9703f"
    _close(w)


def test_highlighter_selection_toggle_save_undo():
    """형광펜 — 글 고치는 중 드래그한 구절만, 다시 누르면 지움, .ecad·되돌리기 유지. 도형 안 글(라벨)도 저장된다."""
    from PyQt6.QtGui import QTextCursor
    from easycad.canvas.annotator_core import _RectItem, _TextItem
    from PyQt6.QtCore import QRectF
    w = _window()
    t = _TextItem(QColor("#202020")); t.setPlainText("어텐션으로 단어 관계를 연결"); w._scene.addItem(t)
    t.setTextInteractionFlags(t.textInteractionFlags().__class__.TextEditorInteraction); t.setFocus()
    w._scene.setFocusItem(t)
    c = t.textCursor(); c.setPosition(0); c.setPosition(5, QTextCursor.MoveMode.KeepAnchor); t.setTextCursor(c)
    w._text_highlight()
    runs = t.text_runs()
    assert len(runs) == 1 and runs[0][:2] == [0, 5] and runs[0][4].lower() == w._HIGHLIGHT
    again = dict_to_item(json.loads(json.dumps(item_to_dict(t))))
    assert again.text_runs() == runs
    w._text_highlight()                       # 같은 구절 다시 → 지움
    assert t.text_runs() == []
    w.undo()                                   # 지운 것 되돌리기 → 다시 칠해짐
    assert t.text_runs() == runs
    # 도형 안 글(라벨)
    box = _RectItem(QRectF(0, 0, 160, 60)); w._scene.addItem(box)
    lbl = box.ensure_label(); lbl.setPlainText("라벨 글"); lbl.set_highlight(0, 2, w._HIGHLIGHT)
    d = json.loads(json.dumps(item_to_dict(box)))
    box2 = dict_to_item(d)
    if box2._label_alive():
        assert box2._label.text_runs() == lbl.text_runs()
    else:   # 라벨 복원은 씬에 넣은 뒤(insert_items) — 저장 dict에 서식이 있는지만
        assert d["label"]["runs"] == lbl.text_runs()
    _close(w)
