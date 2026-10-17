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
