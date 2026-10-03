"""2026-10-03 작은 개선 2건 — ① 미니맵 자기 재생성 반복 끊기 ② A0 용지틀."""
from _shared import *  # noqa: F401,F403


def _settle(app, ms=400):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()


def test_minimap_rebuild_does_not_retrigger_itself():
    # [실측 2026-10-03] 재생성 때 얇은 펜을 setPen으로 잠깐 굵게 했다 되돌리면 scene.changed가
    # 뒤늦게 와서 디바운스가 다시 걸리고 → 또 재생성 → … 끝없이 돌았다(9,488개 PDF에서 3.5초마다).
    w = CanvasWindow(); w.resize(1200, 800); w.show()
    app = QApplication.instance()
    _mk_pen_rect(w, width=1.0)            # 최소 두께(3.0)보다 얇은 펜 — setPen이 일어나는 경우
    _settle(app)
    w._minimap._rebuild_pixmap()
    assert not w._minimap._rebuild_timer.isActive()
    _settle(app)                          # 예전엔 여기서 scene.changed가 와 타이머가 다시 걸렸다
    assert not w._minimap._rebuild_timer.isActive()
    assert not w._minimap._bounds_dirty
    w._active_doc.dirty = False
    w.close()


def test_minimap_still_rebuilds_after_real_change():
    # 자기 변경만 무시하고, 그 뒤의 진짜 편집은 그대로 미니맵 재생성을 예약해야 한다.
    w = CanvasWindow(); w.resize(1200, 800); w.show()
    app = QApplication.instance()
    _mk_pen_rect(w, width=1.0)
    _settle(app)
    w._minimap._rebuild_pixmap()
    _settle(app)
    _mk_pen_rect(w, x=3000, y=3000, width=1.0)
    _settle(app, 50)                      # scene.changed 도착(디바운스 150ms 전)
    assert w._minimap._rebuild_timer.isActive()
    _settle(app)
    assert w._minimap._bounds_cache.right() > 3000   # 새 도형까지 범위에 들어옴
    w._active_doc.dirty = False
    w.close()


def test_minimap_rebuild_keeps_pending_real_change():
    # 진짜 변경이 아직 scene.changed로 안 나온 상태에서 재생성되면(예: 열기 중 paintEvent),
    # 그 변경은 먼저 평소대로 처리돼 범위에 반영돼야 한다(자기 변경과 섞여 버려지면 안 됨).
    w = CanvasWindow(); w.resize(1200, 800); w.show()
    app = QApplication.instance()
    _mk_pen_rect(w, width=1.0)
    _settle(app)
    w._minimap._rebuild_pixmap()
    _settle(app)
    _mk_pen_rect(w, x=5000, y=5000, width=1.0)   # 이벤트 루프 안 돌림 — 아직 대기 중
    w._minimap._rebuild_pixmap()
    assert w._minimap._bounds_cache.right() > 5000
    w._active_doc.dirty = False
    w.close()


# ---- ② A0 용지틀 — 예전엔 A4~A1만이라 A0 PDF를 열면 용지틀 없이 놓였다 ----------------

def test_a0_pdf_opens_with_frame_and_exports_back_as_a0():
    import os, uuid
    import pytest
    fitz = pytest.importorskip("fitz")
    from PyQt6.QtWidgets import QGraphicsScene
    from easycad.fileio import pdf_import
    from easycad.fileio.pdf_export import export_pdf_pages
    d = os.path.join(_TMP, f"a0_{uuid.uuid4().hex}"); os.makedirs(d)
    src, out = os.path.join(d, "a0.pdf"), os.path.join(d, "out.pdf")
    doc = fitz.open()
    p = doc.new_page(width=3370.39, height=2383.94)   # A0 가로(pt)
    p.draw_line((100, 100), (3000, 2000), color=(0, 0, 0), width=1)
    doc.save(src); doc.close()

    sc = QGraphicsScene()
    st = {}
    pdf_import.import_pdf(sc, src, stats=st)
    frames = [it for it in sc.items() if isinstance(it, _TitleBlockItem)]
    assert st["no_frame"] == 0
    assert [(f._size, f._orient) for f in frames] == [("A0", "landscape")]

    assert export_pdf_pages(sc, out, frames)
    with fitz.open(out) as res:
        r = res[0].rect
    assert abs(r.width - 3370.39) < 2 and abs(r.height - 2383.94) < 2   # 다시 A0 가로


def test_paper_combo_lists_a0():
    from easycad.canvas.host_dialogs import _PaperSizeDialog
    w = CanvasWindow()
    dlg = _PaperSizeDialog(w)
    sizes = [dlg._size_cb.itemData(i) for i in range(dlg._size_cb.count())]
    assert sizes == ["A4", "A3", "A2", "A1", "A0"]
