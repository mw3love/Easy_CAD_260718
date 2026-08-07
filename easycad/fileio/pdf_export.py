"""PDF 출력 — 씬(또는 선택영역)을 A4~A1 용지에 맞춰 벡터 PDF로 렌더.

전체 출력: 그려진 모든 객체의 경계(itemsBoundingRect)를 용지에 fit.
선택영역 출력: 선택된 객체들의 경계를 용지에 fit.
용지 방향은 기본 원본 종횡비 자동(가로가 길면 Landscape)이나 `orientation`으로 수동 지정 가능
(표제란/용지틀이 적용될 때는 그 프레임 방향이 항상 우선 — 아래 `_resolve_geometry` 참조).

[§8 항목14, 2026-08-07] `export_pdf`(파일 저장)와 `render_preview`(다이얼로그 라이브 미리보기)가
`_resolve_geometry`/`_paint_scene`을 공유해 미리보기와 실제 출력이 항상 같은 결과를 낸다.
"""
from PyQt6.QtCore import Qt, QRectF, QMarginsF
from PyQt6.QtGui import QPainter, QPageSize, QPageLayout, QBrush, QColor, QPixmap
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


def _current_ink_color(it):
    """[2026-07-29] apply_color가 있는 아이템의 현재 잉크색을 duck-typing으로 읽는다.
    화살표/배지=`_color` 필드, 텍스트=defaultTextColor(), 나머지(도형·선)=pen().color()."""
    col = getattr(it, "_color", None)
    if col is not None:
        return QColor(col)
    if hasattr(it, "defaultTextColor"):
        return it.defaultTextColor()
    if hasattr(it, "pen"):
        return it.pen().color()
    return None


def _is_near_white(c) -> bool:
    return c is not None and c.red() >= 250 and c.green() >= 250 and c.blue() >= 250


def _swap_white_to_black_for_print(scene):
    """[2026-07-29 — 사용자 확정: 화면은 흰색, 종이는 검정] AutoCAD의 ACI 7(흰색) 인쇄 관례를
    따른다. 다크 캔버스에선 흰 선·글자가 잘 보이지만, PDF는 항상 흰 종이라 그대로 두면 안 보이는
    유령 선이 된다. 렌더 직전 흰색 계열 잉크색만 검정으로 바꾸고, (item, 원래색) 목록을 반환해
    렌더 후 원복할 수 있게 한다. 대상은 `apply_color`가 있는 아이템(도형·선·화살표·배지·텍스트)
    전부 — 타입 무관하게 흰색이면 바꾼다(화면-표시용 색과 인쇄용 색을 분리 관리하지 않으므로
    되돌리기 전제로만 임시 변경)."""
    swapped = []
    for it in scene.items():
        if not hasattr(it, "apply_color"):
            continue
        col = _current_ink_color(it)
        if _is_near_white(col):
            swapped.append((it, col))
            it.apply_color(QColor("black"))
    return swapped


def _restore_swapped_colors(swapped):
    for it, col in swapped:
        it.apply_color(col)


def _resolve_geometry(scene, page: str, selection_only: bool, margin_mm: float,
                      orientation: str | None):
    """(source, page, landscape, margin_mm) 계산. 출력 대상이 없으면 None.

    표제란/용지틀이 있고 전체 출력이면 그 프레임 경계·크기·방향이 항상 우선(`orientation`
    무시 — 프레임이 이미 '이 용지로 낸다'는 결정을 대신하므로, §8 항목14 deep-interview
    2026-08-07 확정). 그 외에는 `orientation`이 주어지면 그대로, 없으면 원본 종횡비로 자동.
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
            return None
        # 여백(획 두께·화살촉이 경계 밖으로 삐져나오는 것 보정)
        pad = max(source.width(), source.height()) * 0.02
        source = source.adjusted(-pad, -pad, pad, pad)
        landscape = (orientation == "landscape") if orientation else source.width() >= source.height()
    if source.isEmpty():
        return None
    return source, page, landscape, margin_mm


def _paint_scene(scene, painter: QPainter, target: QRectF, source: QRectF):
    """선택 해제(핸들 미출력) + 흰 배경 강제 + 흰 잉크→검정 치환 후 렌더, 끝나면 전부 원복."""
    saved = list(scene.selectedItems())
    scene.clearSelection()
    # [Phase 6 M1] 다크 테마여도 인쇄물은 흰 종이 — 렌더 동안 배경을 흰색으로 강제 후 복원.
    saved_bg = scene.backgroundBrush()
    scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
    # [2026-07-29] 흰 잉크색(예: DXF ACI 7)은 흰 종이에 안 보이므로 인쇄 관례대로 검정 치환.
    swapped_colors = _swap_white_to_black_for_print(scene)
    try:
        scene.render(painter, target, source, Qt.AspectRatioMode.KeepAspectRatio)
    finally:
        scene.setBackgroundBrush(saved_bg)
        _restore_swapped_colors(swapped_colors)
        for it in saved:
            it.setSelected(True)


def export_pdf(scene, path: str, page: str = "A4", selection_only: bool = False,
               margin_mm: float = 10.0, orientation: str | None = None) -> bool:
    """scene을 path에 PDF로 저장. selection_only면 선택영역만. 성공 True.

    [Phase 4] 전체 출력이고 씬에 표제란/용지틀이 있으면 그 '용지 경계'를 출력 대상으로
    자동 전환한다(용지 크기·방향도 프레임을 따름). 프레임이 없으면 기존 itemsBoundingRect fit.
    `orientation`("landscape"/"portrait"/None)으로 방향을 수동 지정할 수 있다(프레임 적용 시 무시).
    렌더 전 선택을 잠시 해제해 파란 핸들/점선이 PDF에 찍히지 않게 하고, 끝나면 복원한다.
    """
    geo = _resolve_geometry(scene, page, selection_only, margin_mm, orientation)
    if geo is None:
        return False
    source, page, landscape, margin_mm = geo

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

    painter = QPainter()
    if not painter.begin(printer):
        return False
    try:
        paint_rect = printer.pageLayout().paintRectPixels(printer.resolution())
        target = QRectF(0, 0, paint_rect.width(), paint_rect.height())
        _paint_scene(scene, painter, target, source)
    finally:
        painter.end()
    return True


def render_preview(scene, page: str = "A4", selection_only: bool = False,
                   margin_mm: float = 10.0, orientation: str | None = None,
                   max_px: int = 420) -> QPixmap | None:
    """[§8 항목14] `export_pdf`와 같은 geometry(`_resolve_geometry`)로 미리보기 QPixmap을 렌더.
    출력 대상이 없으면 None(호출부가 안내 문구로 대체 표시)."""
    geo = _resolve_geometry(scene, page, selection_only, margin_mm, orientation)
    if geo is None:
        return None
    source, page, landscape, margin_mm = geo

    page_id = PAGE_SIZES.get(page, QPageSize.PageSizeId.A4)
    paper_mm = QPageSize(page_id).size(QPageSize.Unit.Millimeter)
    pw_mm, ph_mm = paper_mm.width(), paper_mm.height()
    if landscape:
        pw_mm, ph_mm = ph_mm, pw_mm
    aspect = pw_mm / ph_mm if ph_mm else 1.0
    px_w, px_h = (max_px, max(1, round(max_px / aspect))) if aspect >= 1 \
        else (max(1, round(max_px * aspect)), max_px)

    pixmap = QPixmap(px_w, px_h)
    pixmap.fill(QColor("white"))
    margin_px = round((margin_mm / pw_mm) * px_w) if pw_mm else 0
    target = QRectF(margin_px, margin_px, max(1, px_w - 2 * margin_px), max(1, px_h - 2 * margin_px))

    painter = QPainter(pixmap)
    try:
        _paint_scene(scene, painter, target, source)
    finally:
        painter.end()
    return pixmap
