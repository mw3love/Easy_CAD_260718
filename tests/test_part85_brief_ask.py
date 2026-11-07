"""딥모드·발표 자료 맞춤 질문(2026-11-06): `easycad/ai/brief_ask.py` 다듬기와 딥모드 `brief_text`가 맞춤 답을 버리지 않는지.

KAIROS는 부르지 않는다 — 가짜 클라이언트. 실제 호출은 따로 확인(2026-11-06, claude-sonnet-5-5: 3.5~5.1초 — 주제 셋에서 대상을 알아들으면 안 물음).
"""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from easycad.ai import brief_ask, deep_mode  # noqa: E402


def fake_client(answer, sent):
    def create(**kw):
        sent.append(kw)
        return SimpleNamespace(model="m", choices=[SimpleNamespace(message=SimpleNamespace(content=answer), finish_reason="stop")])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_clean_drops_settings_audience_dupes_and_topic():
    raw = {"known": [{"label": "주제", "value": "송신소"}, {"label": "대상", "value": "신입"}], "audience": "신입",
           "questions": [{"q": "누구에게?", "options": ["a", "b"]},            # 대상을 알아들었으니 뺌
                         {"q": "장 수", "options": ["5장", "8장"]},           # 설정은 화면이 따로
                         {"q": "언제 쓰나요?", "options": ["견학 전", "알아서", "견학 전", "뒤"], "multi": 1},
                         {"q": "보기 하나", "options": ["x"]},                 # 보기 하나 = 질문 아님
                         {"q": "언제 쓰나요", "options": ["c", "d"]}]}         # 같은 질문 두 번
    out = brief_ask.clean(raw)
    assert out["known"] == [{"label": "대상", "value": "신입"}]
    assert out["questions"] == [{"q": "언제 쓰나요", "options": ["견학 전", "뒤"], "multi": True}]


def test_clean_no_questions_is_error():
    with pytest.raises(ValueError):
        brief_ask.clean({"known": [], "questions": [{"q": "장 수", "options": ["a", "b"]}]})
    with pytest.raises(ValueError):
        brief_ask.clean("아님")


def test_ask_sends_topic_and_material():
    sent = []
    ans = json.dumps({"known": [], "audience": None, "questions": [{"q": "누구에게", "options": ["아이", "어른"]}, {"q": "쓰임", "options": ["수업", "전시"]}]}, ensure_ascii=False)
    out = brief_ask.ask(fake_client(ans, sent), "전파가 집까지", material="고른 메모 글")
    assert [q["q"] for q in out["questions"]] == ["누구에게", "쓰임"]          # 대상을 모르면 「누구에게」를 물어도 됨
    user = sent[0]["messages"][1]["content"]
    assert "전파가 집까지" in user and "고른 메모 글" in user
    assert "장 수" in sent[0]["messages"][0]["content"]                       # 설정은 묻지 말라고


def test_deep_brief_text_keeps_tailored_answers():
    old = deep_mode.brief_text({"누구에게": "신입"})                             # 옛 질문지 = 고정 이름 + 「알아서」
    assert "- 깊이: 알아서" in old and "- 누구에게: 신입" in old
    new = deep_mode.brief_text({"주제에서 알아들은 것": "대상: 신입", "누구에게": "신입", "언제 쓰나요": "견학 전", "깊이": "보통", "더": "숫자 많이"})
    assert "- 언제 쓰나요: 견학 전" in new and "- 주제에서 알아들은 것: 대상: 신입" in new
    assert "무엇에" not in new                                                 # 안 물은 고정 이름은 안 채움
    assert new.strip().endswith("숫자 많이")
