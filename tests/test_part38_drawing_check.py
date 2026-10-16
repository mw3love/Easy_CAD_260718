"""§8 항목48(2026-10-16) — 「도면 검사」: 연결 안 된 화살표 끝·넘친 글자·겹친 상자·상자를 지나가는 선.

잡아야 할 것과, 잡으면 안 되는 것(테두리에 닿은 끝·쏙 들어간 상자·자기 끝 상자)을 같이 본다 — 헷갈리면 안 잡는 게 원칙.
"""
from _shared import *  # noqa: F401,F403

from PyQt6.QtGui import QColor, QPen

from easycad.canvas.annotator_core import _PolyArrowItem
from easycad.canvas.drawing_check import check_drawing, summary


def _kinds(issues):
    return [s.kind for s in issues]


def _rect(scene, x, y, w=100, h=50):
    it = _RectItem(QRectF(x, y, w, h))
    it.setPen(QPen(QColor("#1b222b"), 2))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    scene.addItem(it)
    return it


def _flow(w, code="flowchart LR\n A[휴가 신청] --> B[팀장 결재]"):
    w._build_mermaid(code)
    arrows = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    return arrows


def test_clean_flow_has_no_issues():
    w = CanvasWindow()
    _flow(w)
    assert check_drawing(w._scene) == []


def test_loose_arrow_end_found_but_end_on_border_is_ok():
    w = CanvasWindow()
    arrow = _flow(w)[0]
    end = arrow._bind_end
    arrow._bind_end = None           # 끝이 상자 테두리 위에 그대로 — 사람 눈엔 이어져 보임
    assert "loose_end" not in _kinds(check_drawing(w._scene))
    arrow._pts[-1] = arrow.mapFromScene(QPointF(5000, 5000))   # 허공으로
    issues = check_drawing(w._scene)
    assert _kinds(issues) == ["loose_end"] and issues[0].item is arrow
    assert end is not None


def test_text_overflow():
    w = CanvasWindow()
    w._build_mermaid("flowchart LR\n A[짧음]")
    box = next(it for it in w._scene.items() if isinstance(it, _RectItem))
    assert "text_overflow" not in _kinds(check_drawing(w._scene))
    r = box.rect()
    box.setRect(QRectF(r.x(), r.y(), 12, r.height()))   # 상자를 아주 좁게 — 글자가 밖으로
    assert "text_overflow" in _kinds(check_drawing(w._scene))


def test_partial_overlap_found_containment_ignored():
    w = CanvasWindow()
    _rect(w._scene, 0, 0, 100, 60)
    _rect(w._scene, 20, 10, 40, 20)        # 쏙 들어감 — 묶음 표시로 봄
    assert "box_overlap" not in _kinds(check_drawing(w._scene))
    _rect(w._scene, 70, 30, 100, 60)       # 일부만 겹침
    assert _kinds(check_drawing(w._scene)).count("box_overlap") == 1


def test_line_through_other_box_but_not_its_own_ends():
    w = CanvasWindow()
    arrow = _flow(w)[0]
    assert "line_through" not in _kinds(check_drawing(w._scene)), "자기 양 끝 상자는 지나가도 됨"
    pts = [arrow.mapToScene(p) for p in arrow._pts]
    mid = QPointF((pts[0].x() + pts[-1].x()) / 2, (pts[0].y() + pts[-1].y()) / 2)
    _rect(w._scene, mid.x() - 20, mid.y() - 20, 40, 40)   # 화살표 한가운데에 상자
    issues = check_drawing(w._scene)
    assert "line_through" in _kinds(issues)


def test_check_only_given_items_for_ai_results():
    w = CanvasWindow()
    _rect(w._scene, 0, 0, 100, 60)
    other = _rect(w._scene, 70, 30, 100, 60)
    assert check_drawing(w._scene, items=[other]) == [], "AI 결과만 볼 땐 결과 밖 상자와의 겹침은 안 봄"


def test_card_walks_issues_and_selects():
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    _app.processEvents()
    a = _rect(w._scene, 0, 0, 100, 60)
    b = _rect(w._scene, 70, 30, 100, 60)
    _rect(w._scene, 400, 0, 100, 60)
    _rect(w._scene, 470, 30, 100, 60)
    issues = w._run_drawing_check()
    assert len(issues) == 2 and w._check_card.isVisible()
    assert "겹친 상자 2" in w._check_card._summary.text()
    assert issues[0].item.isSelected()
    w._check_step(1)
    assert w._check[2] == 1 and issues[1].item.isSelected()
    w._check_step(1)
    assert w._check[2] == 0, "끝에서 다시 처음으로"
    w._close_drawing_check()
    assert not w._check_card.isVisible() and w._check is None
    for it in (a, b):
        w._scene.removeItem(it)
    w._scene.clear()
    assert w._run_drawing_check() == [] and "없어요" in w._toast.currentMessage()


def test_marks_draw_only_on_their_tab():
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    _rect(w._scene, 0, 0, 100, 60)
    _rect(w._scene, 70, 30, 100, 60)
    w._run_drawing_check()
    first = w._active_doc
    w._open_new_tab()
    _app.processEvents()
    assert not w._check_card.isVisible()
    assert w._check[0] is first


def test_summary_and_menu():
    w = CanvasWindow()
    assert summary([]) == ""
    assert w._act_check.text() == "도면 검사" and w._act_check.shortcut().toString() == "Ctrl+Shift+K"
