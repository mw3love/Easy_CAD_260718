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
