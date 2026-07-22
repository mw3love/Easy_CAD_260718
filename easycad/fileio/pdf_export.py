"""PDF 출력 — 씬(또는 선택영역)을 A4~A1 용지에 맞춰 벡터 PDF로 렌더.

전체 출력: 그려진 모든 객체의 경계(itemsBoundingRect)를 용지에 fit.
선택영역 출력: 선택된 객체들의 경계를 용지에 fit.
용지 방향은 원본 종횡비로 자동(가로가 길면 Landscape).
"""
from PyQt6.QtCore import Qt, QRectF, QMarginsF
from PyQt6.QtGui import QPainter, QPageSize, QPageLayout, QBrush, QColor
from PyQt6.QtPrintSupport import QPrinter

# 라벨 → QPageSize id
PAGE_SIZES = {
    "A4": QPageSize.PageSizeId.A4,
    "A3": QPageSize.PageSizeId.A3,
    "A2": QPageSize.PageSizeId.A2,
    "A1": QPageSize.PageSizeId.A1,
}


def _selection_rect(scene) -> QRectF:
    sel = scene.selectedItems()
    if not sel:
        return QRectF()
    r = QRectF()
    for it in sel:
        r = r.united(it.sceneBoundingRect())
    return r


def _find_title_frame(scene):
    """[Phase 4] 씬에 표제란/용지틀이 있으면 그 아이템(없으면 None). 순환 임포트 방지 위해 지연 임포트."""
    from easycad.canvas.annotator_core import _TitleBlockItem
    for it in scene.items():
        if isinstance(it, _TitleBlockItem):
            return it
    return None


def export_pdf(scene, path: str, page: str = "A4",
               selection_only: bool = False, margin_mm: float = 10.0) -> bool:
    """scene을 path에 PDF로 저장. selection_only면 선택영역만. 성공 True.

    [Phase 4] 전체 출력이고 씬에 표제란/용지틀이 있으면 그 '용지 경계'를 출력 대상으로
    자동 전환한다(용지 크기·방향도 프레임을 따름). 프레임이 없으면 기존 itemsBoundingRect fit.
    렌더 전 선택을 잠시 해제해 파란 핸들/점선이 PDF에 찍히지 않게 하고, 끝나면 복원한다.
    """
    frame = None if selection_only else _find_title_frame(scene)
    if frame is not None:
        # 용지 프레임 기준: 정확한 용지 경계를 페이지 전체에 맞춤(패드·여백 없음, 종횡비 일치).
        source = frame.mapRectToScene(frame.rect())
        page = frame._size
        landscape = frame._orient == "landscape"
        margin_mm = 0.0
    else:
        if selection_only:
            source = _selection_rect(scene)
        else:
            source = scene.itemsBoundingRect()
        if source.isEmpty():
            return False
        # 여백(획 두께·화살촉이 경계 밖으로 삐져나오는 것 보정)
        pad = max(source.width(), source.height()) * 0.02
        source = source.adjusted(-pad, -pad, pad, pad)
        landscape = source.width() >= source.height()
    if source.isEmpty():
        return False

    page_id = PAGE_SIZES.get(page, QPageSize.PageSizeId.A4)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    layout = QPageLayout(
        QPageSize(page_id),
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait,
        QMarginsF(margin_mm, margin_mm, margin_mm, margin_mm),
        QPageLayout.Unit.Millimeter,
    )
    printer.setPageLayout(layout)

    # 선택 상태 저장 후 해제(핸들 렌더 방지)
    saved = list(scene.selectedItems())
    scene.clearSelection()
    # [Phase 6 M1] 다크 테마여도 인쇄물은 흰 종이 — 렌더 동안 배경을 흰색으로 강제 후 복원.
    saved_bg = scene.backgroundBrush()
    scene.setBackgroundBrush(QBrush(QColor("#ffffff")))

    painter = QPainter()
    if not painter.begin(printer):
        scene.setBackgroundBrush(saved_bg)
        for it in saved:
            it.setSelected(True)
        return False
    try:
        paint_rect = printer.pageLayout().paintRectPixels(printer.resolution())
        target = QRectF(0, 0, paint_rect.width(), paint_rect.height())
        scene.render(painter, target, source, Qt.AspectRatioMode.KeepAspectRatio)
    finally:
        painter.end()
        scene.setBackgroundBrush(saved_bg)
        for it in saved:
            it.setSelected(True)
    return True
