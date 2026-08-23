"""PDF/PNG/SVG 내보내기 — 씬(또는 선택영역)을 A4~A1 용지에 맞춰 렌더.

전체 출력: 그려진 모든 객체의 경계(itemsBoundingRect)를 용지에 fit.
선택영역 출력: 선택된 객체들의 경계를 용지에 fit.
용지 방향은 기본 원본 종횡비 자동(가로가 길면 Landscape)이나 `orientation`으로 수동 지정 가능
(표제란/용지틀이 적용될 때는 그 프레임 방향이 항상 우선 — 아래 `_resolve_geometry` 참조).

[§8 항목14, 2026-08-07] `export_pdf`(파일 저장)와 `render_preview`(다이얼로그 라이브 미리보기)가
`_resolve_geometry`/`_paint_scene`을 공유해 미리보기와 실제 출력이 항상 같은 결과를 낸다.
[2026-08-20 실사용 피드백] `export_image`(PNG)·`export_svg`가 같은 두 헬퍼를 재사용해
합류 — 세 포맷 모두 같은 크롭/용지/방향/선택영역 규칙을 공유한다."""
from PyQt6.QtCore import Qt, QRectF, QMarginsF, QSize
from PyQt6.QtGui import QPainter, QPageSize, QPageLayout, QBrush, QColor, QPixmap
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtSvg import QSvgGenerator

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
    """[Phase 4] 씬에 표제란/용지틀이 있으면 그 아이템(없으면 None). 순환 임포트 방지 위해 지연 임포트.
    [다중 페이지 지원, 2026-08-14] 프레임이 여러 개면 `scene.items()` 순서상 맨 앞의 것 —
    호출부가 특정 프레임을 명시하지 않은 기존 호출(`export_pdf`/`render_preview`를 `frame`
    인자 없이 부르는 테스트·스크립트 등)의 하위호환용. 새 다중 프레임 UI(`_PdfExportDialog`)는
    `_list_title_frames`로 고른 프레임을 `frame=` 인자로 명시해 이 폴백을 안 탄다."""
    from easycad.canvas.annotator_core import _TitleBlockItem
    for it in scene.items():
        if isinstance(it, _TitleBlockItem):
            return it
    return None


def _list_title_frames(scene):
    """[다중 페이지 지원, 2026-08-14] 씬의 모든 표제란/용지틀을 도면번호순으로 반환
    (도면번호가 비어있으면 뒤로 — deep-interview 확정, 알파벳순이라 대소문자·숫자 혼용
    표기는 사용자가 일관된 번호 규칙을 쓴다는 전제). 동률(둘 다 빈 번호 등)은 `scene.items()`
    순서를 그대로 유지(안정 정렬). PDF 다이얼로그의 프레임 선택 드롭다운이 쓴다."""
    from easycad.canvas.annotator_core import _TitleBlockItem
    frames = [it for it in scene.items() if isinstance(it, _TitleBlockItem)]
    frames.sort(key=lambda fr: (fr._fields.get("number", "").strip() == "",
                                fr._fields.get("number", "").strip()))
    return frames


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


_DEFAULT_MARGINS_MM = (10.0, 10.0, 10.0, 10.0)   # (위, 오른쪽, 아래, 왼쪽) — CSS 순서


def _resolve_geometry(scene, page: str, selection_only: bool,
                      margins_mm: tuple[float, float, float, float],
                      orientation: str | None, frame=None):
    """(source, page, landscape, margins_mm) 계산. 출력 대상이 없으면 None.

    표제란/용지틀이 있고 전체 출력이면 그 프레임 경계·크기·방향이 항상 우선(`orientation`
    무시 — 프레임이 이미 '이 용지로 낸다'는 결정을 대신하므로, §8 항목14 deep-interview
    2026-08-07 확정). 그 외에는 `orientation`이 주어지면 그대로, 없으면 원본 종횡비로 자동.

    [다중 페이지 지원, 2026-08-14] `frame`을 명시하면 그 프레임을 그대로 쓴다(씬에 프레임이
    여러 개일 때 `_PdfExportDialog`가 사용자가 고른 걸 넘긴다). 생략(None)하면 기존처럼
    `_find_title_frame`(첫 번째 프레임) 자동탐지로 폴백 — 기존 호출부(테스트 등) 무변경.

    [여백 상하좌우 개별 지정, 2026-08-23] `margins_mm`은 (위, 오른쪽, 아래, 왼쪽) mm 4개.
    표제란/용지틀이 적용되면 그 프레임이 이미 정확한 용지 경계라 여백은 항상 0으로 강제한다
    (기존 크기/방향 잠금과 같은 이유)."""
    if not selection_only:
        frame = frame if frame is not None else _find_title_frame(scene)
    else:
        frame = None
    if frame is not None:
        # 용지 프레임 기준: 정확한 용지 경계를 페이지 전체에 맞춤(패드·여백 없음, 종횡비 일치).
        source = frame.mapRectToScene(frame.rect())
        page = frame._size
        landscape = frame._orient == "landscape"
        margins_mm = (0.0, 0.0, 0.0, 0.0)
    else:
        if selection_only:
            source = _selection_rect(scene)
        else:
            source = scene.itemsBoundingRect()
        if source.isEmpty():
            return None
        # 여백(획 두께·화살촉이 경계 밖으로 삐져나오는 것 보정) — 사용자 지정 여백과는 별개.
        pad = max(source.width(), source.height()) * 0.02
        source = source.adjusted(-pad, -pad, pad, pad)
        landscape = (orientation == "landscape") if orientation else source.width() >= source.height()
    if source.isEmpty():
        return None
    return source, page, landscape, margins_mm


def _has_kept_ancestor(it, keep: set) -> bool:
    """`it` 자신 또는 그 조상 중 하나가 `keep`에 있으면 True — 선택된 도형의 라벨 등
    자식 아이템은 자신이 직접 선택되지 않아도 부모가 선택됐으면 함께 남겨야 한다."""
    p = it
    while p is not None:
        if p in keep:
            return True
        p = p.parentItem()
    return False


def _centered_target_rect(target: QRectF, source: QRectF) -> QRectF:
    """[2026-08-20 실사용 버그 수정] `QGraphicsScene.render(painter, target, source,
    KeepAspectRatio)`는 종횡비가 안 맞을 때 남는 여백을 target 왼쪽/위로 몰아붙인다
    (Qt 기본 동작 — 가운데 정렬이 아님, 실측으로 확인). "여백이 이상하다"는 실사용
    피드백의 원인 — target을 source와 같은 비율의 중앙 부분 사각형으로 미리 좁혀 넘기면
    남는 여백이 사방에 고르게 분배된다."""
    if source.isEmpty() or target.isEmpty():
        return target
    scale = min(target.width() / source.width(), target.height() / source.height())
    w, h = source.width() * scale, source.height() * scale
    x = target.x() + (target.width() - w) / 2
    y = target.y() + (target.height() - h) / 2
    return QRectF(x, y, w, h)


def _paint_scene(scene, painter: QPainter, target: QRectF, source: QRectF,
                 isolate_selection: bool = False, white_bg: bool = True):
    """선택 해제(핸들 미출력) + (기본) 흰 배경 강제·흰 잉크→검정 치환 후 렌더, 끝나면 전부 원복.

    [2026-08-20 실사용 버그 수정] `isolate_selection=True`면 렌더 동안 선택되지 않은
    아이템(과 그 자식)을 잠시 숨긴다 — `scene.render(painter, target, source)`는 `source`
    사각형과 겹치는 아이템을 전부 그리기 때문에, 이게 없으면 "선택 영역 내보내기"가
    선택한 항목의 bounding box 안에 있는 다른(비선택) 도형까지 함께 내보내고 있었다.

    [내보내기 통합, 2026-08-20] `white_bg=False`면 배경을 강제하지 않는다(투명 배경
    PNG/SVG 전용) — 흰 종이 인쇄 관례(흰 배경 강제 + 흰 잉크→검정 치환)는 투명 배경일
    땐 의미가 없으므로 함께 건너뛴다."""
    saved = list(scene.selectedItems())
    scene.clearSelection()
    hidden = []
    if isolate_selection:
        keep = set(saved)
        for it in scene.items():
            if it.isVisible() and not _has_kept_ancestor(it, keep):
                it.setVisible(False)
                hidden.append(it)
    saved_bg = scene.backgroundBrush()
    swapped_colors = []
    if white_bg:
        # [Phase 6 M1] 다크 테마여도 인쇄물은 흰 종이 — 렌더 동안 배경을 흰색으로 강제 후 복원.
        scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        # [2026-07-29] 흰 잉크색(예: DXF ACI 7)은 흰 종이에 안 보이므로 인쇄 관례대로 검정 치환.
        swapped_colors = _swap_white_to_black_for_print(scene)
    else:
        scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
    try:
        scene.render(painter, _centered_target_rect(target, source), source,
                     Qt.AspectRatioMode.KeepAspectRatio)
    finally:
        scene.setBackgroundBrush(saved_bg)
        _restore_swapped_colors(swapped_colors)
        for it in hidden:
            it.setVisible(True)
        for it in saved:
            it.setSelected(True)


def export_pdf(scene, path: str, page: str = "A4", selection_only: bool = False,
               margins_mm: tuple[float, float, float, float] = _DEFAULT_MARGINS_MM,
               orientation: str | None = None, frame=None) -> bool:
    """scene을 path에 PDF로 저장. selection_only면 선택영역만. 성공 True.

    [Phase 4] 전체 출력이고 씬에 표제란/용지틀이 있으면 그 '용지 경계'를 출력 대상으로
    자동 전환한다(용지 크기·방향도 프레임을 따름). 프레임이 없으면 기존 itemsBoundingRect fit.
    `orientation`("landscape"/"portrait"/None)으로 방향을 수동 지정할 수 있다(프레임 적용 시 무시).
    렌더 전 선택을 잠시 해제해 파란 핸들/점선이 PDF에 찍히지 않게 하고, 끝나면 복원한다.
    [다중 페이지 지원, 2026-08-14] `frame`으로 여러 프레임 중 하나를 명시할 수 있다(생략 시
    씬의 첫 프레임 자동탐지, 기존 동작 무변경).
    [여백 상하좌우 개별 지정, 2026-08-23] `margins_mm`은 (위, 오른쪽, 아래, 왼쪽) mm 4개
    (기존 `margin_mm` 단일값을 대체 — 외부 호출부가 없어 하위호환 유지 불필요).
    """
    geo = _resolve_geometry(scene, page, selection_only, margins_mm, orientation, frame)
    if geo is None:
        return False
    source, page, landscape, margins_mm = geo
    top, right, bottom, left = margins_mm

    page_id = PAGE_SIZES.get(page, QPageSize.PageSizeId.A4)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    layout = QPageLayout(
        QPageSize(page_id),
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait,
        QMarginsF(left, top, right, bottom),
        QPageLayout.Unit.Millimeter,
    )
    printer.setPageLayout(layout)

    painter = QPainter()
    if not painter.begin(printer):
        return False
    try:
        paint_rect = printer.pageLayout().paintRectPixels(printer.resolution())
        target = QRectF(0, 0, paint_rect.width(), paint_rect.height())
        _paint_scene(scene, painter, target, source, isolate_selection=selection_only)
    finally:
        painter.end()
    return True


def _page_pixel_geometry(page_id, landscape: bool,
                         margins_mm: tuple[float, float, float, float], dpi: int):
    """(px_w, px_h, target) — mm 단위 용지를 `dpi` 해상도의 픽셀 사각형으로 환산.
    `export_image`/`export_svg`가 공유(둘 다 같은 픽셀 좌표계에 그려 화질·여백이 일치).
    `margins_mm`은 (위, 오른쪽, 아래, 왼쪽) — 상하좌우 개별 지정(2026-08-23)."""
    paper_mm = QPageSize(page_id).size(QPageSize.Unit.Millimeter)
    pw_mm, ph_mm = paper_mm.width(), paper_mm.height()
    if landscape:
        pw_mm, ph_mm = ph_mm, pw_mm
    mm_to_px = dpi / 25.4
    px_w = max(1, round(pw_mm * mm_to_px))
    px_h = max(1, round(ph_mm * mm_to_px))
    top, right, bottom, left = (round(m * mm_to_px) for m in margins_mm)
    target = QRectF(left, top,
                    max(1, px_w - left - right), max(1, px_h - top - bottom))
    return px_w, px_h, target


def export_image(scene, path: str, page: str = "A4", selection_only: bool = False,
                 margins_mm: tuple[float, float, float, float] = _DEFAULT_MARGINS_MM,
                 orientation: str | None = None, frame=None,
                 transparent: bool = False, dpi: int = 200) -> bool:
    """scene을 path에 PNG로 저장 — `export_pdf`와 같은 크롭/용지/방향/선택영역/여백 규칙.
    [내보내기 통합, 2026-08-20] `transparent=True`면 흰 배경 강제·흰 잉크→검정 치환을
    건너뛰고 알파 배경으로 저장한다(로고·다른 문서에 얹어 쓰는 용도)."""
    geo = _resolve_geometry(scene, page, selection_only, margins_mm, orientation, frame)
    if geo is None:
        return False
    source, page, landscape, margins_mm = geo
    page_id = PAGE_SIZES.get(page, QPageSize.PageSizeId.A4)
    px_w, px_h, target = _page_pixel_geometry(page_id, landscape, margins_mm, dpi)

    pixmap = QPixmap(px_w, px_h)
    pixmap.fill(Qt.GlobalColor.transparent if transparent else QColor("white"))
    painter = QPainter(pixmap)
    try:
        _paint_scene(scene, painter, target, source, isolate_selection=selection_only,
                     white_bg=not transparent)
    finally:
        painter.end()
    return pixmap.save(path, "PNG")


def export_svg(scene, path: str, page: str = "A4", selection_only: bool = False,
               margins_mm: tuple[float, float, float, float] = _DEFAULT_MARGINS_MM,
               orientation: str | None = None, frame=None,
               transparent: bool = False, dpi: int = 200) -> bool:
    """scene을 path에 SVG로 저장 — `export_pdf`와 같은 크롭/용지/방향/선택영역/여백 규칙.
    QtSvg의 `QSvgGenerator`가 이미 프로젝트 의존성(SVG 가져오기/미리보기에서 사용 중)이라
    새 외부 패키지 없이 구현 가능."""
    geo = _resolve_geometry(scene, page, selection_only, margins_mm, orientation, frame)
    if geo is None:
        return False
    source, page, landscape, margins_mm = geo
    page_id = PAGE_SIZES.get(page, QPageSize.PageSizeId.A4)
    px_w, px_h, target = _page_pixel_geometry(page_id, landscape, margins_mm, dpi)

    generator = QSvgGenerator()
    generator.setFileName(path)
    generator.setSize(QSize(px_w, px_h))
    generator.setViewBox(QRectF(0, 0, px_w, px_h))
    # `setResolution` 없이는 Qt가 72dpi로 가정해 SVG의 물리 크기(width/height mm) 속성이
    # `dpi`(기본 200)만큼 실제보다 커진다 — 뷰어 화면에선 안 보여도 "실척 인쇄" 시 어긋난다.
    generator.setResolution(dpi)
    generator.setTitle("Easy CAD")

    painter = QPainter(generator)
    try:
        _paint_scene(scene, painter, target, source, isolate_selection=selection_only,
                     white_bg=not transparent)
    finally:
        painter.end()
    return True


def export_svg_symbol(scene, path: str, pad: float = 6.0) -> bool:
    """scene 전체 콘텐츠를 여백만 두고 꽉 채운 SVG로 저장 — 페이지 개념이 없는 아이콘/심볼
    전용 내보내기. [실사용 요청, 2026-08-21] '내 심볼' 우클릭 「SVG로 내보내기」가 사용.
    `export_svg`는 A4~A1 용지 캔버스에 콘텐츠를 fit하는 인쇄용이라 심볼 하나를 내보내면
    거대한 빈 여백의 SVG가 나온다(과함) — 그래서 페이지/프레임 로직을 건너뛰고
    `itemsBoundingRect()` 기준으로 캔버스 크기 자체를 콘텐츠에 맞춘다."""
    source = scene.itemsBoundingRect()
    if source.isEmpty():
        return False
    source = source.adjusted(-pad, -pad, pad, pad)
    px_w = max(1, round(source.width()))
    px_h = max(1, round(source.height()))
    target = QRectF(0, 0, px_w, px_h)

    generator = QSvgGenerator()
    generator.setFileName(path)
    generator.setSize(QSize(px_w, px_h))
    generator.setViewBox(target)
    generator.setTitle("Easy CAD Symbol")

    painter = QPainter(generator)
    try:
        _paint_scene(scene, painter, target, source, isolate_selection=False, white_bg=False)
    finally:
        painter.end()
    return True


def render_preview(scene, page: str = "A4", selection_only: bool = False,
                   margins_mm: tuple[float, float, float, float] = _DEFAULT_MARGINS_MM,
                   orientation: str | None = None,
                   max_px: int = 420, frame=None) -> QPixmap | None:
    """[§8 항목14] `export_pdf`와 같은 geometry(`_resolve_geometry`)로 미리보기 QPixmap을 렌더.
    출력 대상이 없으면 None(호출부가 안내 문구로 대체 표시).
    [다중 페이지 지원, 2026-08-14] `frame` — `export_pdf`와 동일(생략 시 자동탐지).
    [여백 상하좌우 개별 지정, 2026-08-23] `margins_mm` — (위, 오른쪽, 아래, 왼쪽) mm."""
    geo = _resolve_geometry(scene, page, selection_only, margins_mm, orientation, frame)
    if geo is None:
        return None
    source, page, landscape, margins_mm = geo

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
    scale = px_w / pw_mm if pw_mm else 0
    top, right, bottom, left = (round(m * scale) for m in margins_mm)
    target = QRectF(left, top, max(1, px_w - left - right), max(1, px_h - top - bottom))

    painter = QPainter(pixmap)
    try:
        _paint_scene(scene, painter, target, source, isolate_selection=selection_only)
    finally:
        painter.end()
    return pixmap
