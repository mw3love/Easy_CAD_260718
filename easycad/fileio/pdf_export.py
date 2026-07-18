"""PDF 출력 — 씬(또는 선택영역)을 A4~A1 용지에 맞춰 벡터 PDF로 렌더.

전체 출력: 그려진 모든 객체의 경계(itemsBoundingRect)를 용지에 fit.
선택영역 출력: 선택된 객체들의 경계를 용지에 fit.
용지 방향은 원본 종횡비로 자동(가로가 길면 Landscape).
"""
from PyQt6.QtCore import Qt, QRectF, QMarginsF
from PyQt6.QtGui import QPainter, QPageSize, QPageLayout
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


def export_pdf(scene, path: str, page: str = "A4",
               selection_only: bool = False, margin_mm: float = 10.0) -> bool:
    """scene을 path에 PDF로 저장. selection_only면 선택영역만. 성공 True.

    렌더 전 선택을 잠시 해제해 파란 핸들/점선이 PDF에 찍히지 않게 하고, 끝나면 복원한다.
    """
    if selection_only:
        source = _selection_rect(scene)
    else:
        source = scene.itemsBoundingRect()
    if source.isEmpty():
        return False
    # 여백(획 두께·화살촉이 경계 밖으로 삐져나오는 것 보정)
    pad = max(source.width(), source.height()) * 0.02
    source = source.adjusted(-pad, -pad, pad, pad)

    page_id = PAGE_SIZES.get(page, QPageSize.PageSizeId.A4)
    landscape = source.width() >= source.height()

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

    painter = QPainter()
    if not painter.begin(printer):
        for it in saved:
            it.setSelected(True)
        return False
    try:
        paint_rect = printer.pageLayout().paintRectPixels(printer.resolution())
        target = QRectF(0, 0, paint_rect.width(), paint_rect.height())
        scene.render(painter, target, source, Qt.AspectRatioMode.KeepAspectRatio)
    finally:
        painter.end()
        for it in saved:
            it.setSelected(True)
    return True
