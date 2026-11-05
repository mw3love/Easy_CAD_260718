"""2026-11-04 — 사용 기록(`web/usage.py`)·칠판 자동 정리(`web/cleanup.py`).
사용자: 대회 기획서에 쓸 숫자가 필요 + 「모두가 무제한으로 서버에 저장할 수는 없다」(로그인이 없어 개수 대신 기간으로 정리).
진짜 Handler를 시험 안에서 띄움(크레딧 안 씀 — KAIROS 키 없는 길만).
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))

DAY = 86400


@pytest.fixture
def server(tmp_path):
    import server as srv
    import usage
    srv.Handler.data_dir = str(tmp_path)
    srv.Handler.password = ""
    srv.Handler.server_key = False   # 키 없음 = KAIROS를 부르지 않고 바로 「키 없음」 답(크레딧 0)
    srv.Handler.usage = usage.Usage(str(tmp_path))
    srv.Handler.keep_days = 90
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", srv, tmp_path
    srv.Handler.server_key = True
    srv.Handler.usage = None
    srv.Handler.keep_days = 0
    httpd.shutdown()


def _req(url, method="GET", body=None):
    r = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as res:
            return res.status, json.loads(res.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_usage_counts_ai_calls_boards_and_visits_without_names(server):
    base, srv, tmp = server
    q = urllib.request.quote
    _req(base + "/api/chat", "POST", {"messages": [{"role": "user", "content": "안녕"}], "board": "비밀칠판-abcd1234"})
    _req(base + "/api/stt-token", "POST", {})
    assert _req(base + "/api/example/" + q("새칠판-zzzz9999"), "POST", {})[0] == 200
    _req(base + "/api/patch/" + q("비밀칠판-abcd1234"), "POST", {"upsert": [], "delete": []})
    _req(base + "/api/patch/" + q("비밀칠판-abcd1234"), "POST", {"upsert": [], "delete": []})   # 같은 칠판 = 한 번만
    _req(base + "/api/session")                                                        # AI 아닌 GET은 안 셈
    srv.Handler.usage.flush()
    raw = open(os.path.join(tmp, "usage.json"), encoding="utf-8").read()
    assert "비밀칠판" not in raw and "안녕" not in raw                                   # 이름·물은 글은 안 남김
    day = json.loads(raw)["days"][time.strftime("%Y-%m-%d")]
    assert day["kinds"]["chat"] == [1, 0.0, 1] and day["kinds"]["stt"] == [1, 0.0, 1]   # 키 없음 = 실패로 셈
    assert len(day["kinds"]) == 2 and day["new"] == 1 and len(day["boards"]) == 1
    import usage
    text = usage.summary(json.loads(raw))
    assert "AI 2번" in text and "처음 온 사람 1" in text and "chat" in text


def test_usage_adds_credits_from_answers():
    import usage
    u = usage.Usage(os.devnull + "_없음")
    u.add("deep", 12.34)
    u.add("deep", None)
    u.add("image", 5)
    d = u.data["days"][time.strftime("%Y-%m-%d")]["kinds"]
    assert d["deep"] == [2, 12.3, 0] and d["image"] == [1, 5.0, 0]


def _board(tmp, name, age_days, doc=None):
    p = os.path.join(tmp, name + ".ecad")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc or {"format": "easycad-doc", "version": 1, "items": [], "rev": 3}, f)
    t = time.time() - age_days * DAY
    os.utime(p, (t, t))


def test_cleanup_picks_untouched_example_after_7_days_and_idle_after_90(tmp_path):
    import cleanup
    import usage
    ex = {"items": [], "rev": 2, "example": "intro", "example_rev": 2}
    _board(tmp_path, "예시-안고침", 8, ex)
    _board(tmp_path, "예시-막받음", 3, ex)                                   # 아직 7일 안 됨
    _board(tmp_path, "예시-고침", 8, dict(ex, rev=5))                        # 고친 예시 = 보통 칠판(90일)
    _board(tmp_path, "옛예시", 8, {"items": [], "rev": 2, "example": "intro"})   # 이 기능 전 사본(example_rev 없음) = 보통 칠판
    _board(tmp_path, "오래됨", 91)
    _board(tmp_path, "오래됐지만-어제-엶", 200)
    _board(tmp_path, "요즘", 10)
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - DAY))
    seen = {usage.board_mark("오래됐지만-어제-엶"): yesterday}
    got = dict(cleanup.stale(str(tmp_path), seen, usage.board_mark))
    assert got == {"예시-안고침": "example", "오래됨": "idle"}


def test_cleanup_counts_chat_and_other_board_files_as_use(tmp_path):
    import cleanup
    import usage
    _board(tmp_path, "대화만", 120)
    open(os.path.join(tmp_path, "대화만.chat.json"), "w").write("{}")      # 오늘 대화 = 쓰는 칠판
    assert cleanup.stale(str(tmp_path), {}, usage.board_mark) == []


def test_sweep_moves_to_trash_marks_gone_and_purges_old_trash(server):
    base, srv, tmp = server
    _board(tmp, "오래됨-k7p2qx9m", 95)
    img = os.path.join(tmp, "오래됨-k7p2qx9m.img")
    os.makedirs(img)
    os.utime(img, (time.time() - 95 * DAY,) * 2)                             # 그림 폴더도 옛날(새 그림이 들면 쓰는 칠판)
    os.makedirs(os.path.join(tmp, "trash", "옛것-20200101-000000"))
    os.makedirs(os.path.join(tmp, "trash", "최근-" + time.strftime("%Y%m%d-%H%M%S")))
    moved, gone = srv.sweep_once()
    assert (moved, gone) == (1, 1)
    assert not os.path.exists(os.path.join(tmp, "오래됨-k7p2qx9m.ecad"))
    trash = sorted(os.listdir(os.path.join(tmp, "trash")))
    assert any(t.startswith("오래됨-k7p2qx9m-") for t in trash) and not any(t.startswith("옛것") for t in trash)
    assert _req(base + "/api/doc/" + urllib.request.quote("오래됨-k7p2qx9m"))[0] == 410   # 지운 주소 = 「지워짐」(빈 칠판으로 안 되살아남)
    assert _req(base + "/api/session")[1]["keep_days"] == 90


def test_opening_a_board_records_seen_and_example_copy_sets_example_rev(server):
    base, srv, tmp = server
    assert _req(base + "/api/example/" + urllib.request.quote("예시-abcd1234"), "POST", {})[0] == 200
    st, doc = _req(base + "/api/doc/" + urllib.request.quote("예시-abcd1234"))
    assert st == 200 and doc["example_rev"] == doc["rev"]
    import usage
    assert srv.Handler.usage.data["seen"][usage.board_mark("예시-abcd1234")] == time.strftime("%Y-%m-%d")
    _req(base + "/api/patch/" + urllib.request.quote("예시-abcd1234"), "POST", {"upsert": [], "delete": []})
    doc2 = _req(base + "/api/doc/" + urllib.request.quote("예시-abcd1234"))[1]
    assert doc2["rev"] > doc2["example_rev"]                                  # 고치면 더는 「안 고친 사본」이 아님


# ── 정리 문서 → 한글 파일(.hwpx, `web/hwpxout.py`) ──
REPORT = '''<!doctype html><html><head><title>송신소 점검 정리</title><style>.k{color:red}</style></head><body><main>
<header><h1>송신소 점검 정리</h1><p>2026-11-04 · 전주</p></header>
<section><h2>핵심 숫자</h2><div class=kpis><div class=kpi><div class=num>42%</div><div>줄어든 대기 시간</div></div></div>
<ol><li>송신기 <b>교체</b></li><li>안테나 점검<ul><li>급전선</li></ul></li></ol>
<table><tr><th>항목</th><th>상태</th></tr><tr><td>송신기</td><td>교체 필요</td></tr><tr><td>전원</td></tr></table>
<svg viewBox="0 0 9 9"><title>월별 장애</title><text>1월</text></svg><script>alert(1)</script>
<p>끝 문단<br>둘째 줄</p></section></main></body></html>'''


def test_hwpx_blocks_keep_reading_order_and_drop_style_script():
    import hwpxout
    got = hwpxout.blocks(REPORT)
    assert got == [("h", 1, "송신소 점검 정리"), ("p", "2026-11-04 · 전주"), ("h", 2, "핵심 숫자"), ("p", "42% · 줄어든 대기 시간"),
                   ("li", "1. 송신기 교체"), ("li", "2. 안테나 점검"), ("li", "  • 급전선"),
                   ("table", [["항목", "상태"], ["송신기", "교체 필요"], ["전원", ""]]),          # 모자란 칸은 빈칸
                   ("fig", "[그림] 월별 장애 · 1월"), ("p", "끝 문단"), ("p", "둘째 줄")]


def test_hwpx_server_returns_a_valid_hangul_file(server):
    pytest.importorskip("hwpx")
    import io
    from hwpx import HwpxDocument
    base, _, _ = server
    r = urllib.request.Request(base + "/api/hwpx", method="POST", data=json.dumps({"html": REPORT, "title": "송신소 점검 정리"}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as res:
        assert res.headers["Content-Type"] == "application/hwp+zip"
        data = res.read()
    assert data[:2] == b"PK"                                                   # hwpx = zip
    doc = HwpxDocument.open(io.BytesIO(data))
    assert not doc.validate().issues
    text = doc.text.plain() if callable(getattr(doc.text, "plain", None)) else doc.export_text()
    assert "송신소 점검 정리" in text and "교체 필요" in text and "alert" not in text
    assert _req(base + "/api/hwpx", "POST", {"html": ""})[0] == 400


def test_hwpx_spaces_side_by_side_cells_but_keeps_particles():
    """진짜 정리 문서(2026-11-04)에서 「11/8진공관 견적박 주임」·「회의11월」로 붙었던 칸 — 띄우되 조사(「송신기를」)는 붙임."""
    import hwpxout
    h = ('<div><b>회의</b>11월 정기 점검</div><ul><li><span>11/8</span><span>진공관 견적</span><span>박 주임</span></li></ul>'
         '<p><b>송신기</b>를 교체하고 <b>안테나</b> 점검</p><div>핵심 의견<span>작성자 의견</span></div>')
    assert [b[1] for b in hwpxout.blocks(h)] == ["회의 11월 정기 점검", "• 11/8 진공관 견적 박 주임", "송신기를 교체하고 안테나 점검", "핵심 의견 작성자 의견"]


def test_report_styles_counts_which_style_was_kept(tmp_path):
    """2026-11-05 — 정리 문서 발표용·읽기용 두 장 중 칠판에 남긴 쪽(같은 답 `chat_at`끼리): 둘 다 / 발표용만 / 읽기용만. 옛 한 장(style 없음)·.prev는 안 셈."""
    import usage
    doc = lambda at, st: {"type": "doc", "chat_at": at, **({"style": st} if st else {})}
    (tmp_path / "a.ecad").write_text(json.dumps({"items": [doc(1, "present"), doc(1, "read"), doc(2, "present"), doc(3, "read"), doc(4, None)]}), encoding="utf-8")
    (tmp_path / "b.ecad").write_text(json.dumps({"items": [doc(1, "read")]}), encoding="utf-8")
    (tmp_path / "b.prev.ecad").write_text(json.dumps({"items": [doc(9, "present")]}), encoding="utf-8")
    assert usage.report_styles(str(tmp_path)) == {"both": 1, "present": 1, "read": 2}
