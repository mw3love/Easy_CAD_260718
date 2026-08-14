"""CanvasWindow 믹스인 — 파일 입출력 — 새문서/열기/저장/PDF·DXF 내보내기·가져오기/이미지·표제란·표·Mermaid 삽입/드래그앤드롭.

2026-08-02 host.py(3635줄) 분할분. `class CanvasWindow(...)`이 이 믹스인들을 다중상속해
메서드를 합친다 — 동작·이름 전부 원본과 동일(이동만), annotator_core.py가 이미 쓰는 믹스인
패턴을 host.py에도 적용한 것.
"""
from __future__ import annotations

import re
import uuid

from PyQt6.QtCore import (
    Qt, QPoint, QPointF, QRectF, QSize, QSettings, QTimer, QMimeData, QEvent,
)
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QAction, QKeySequence, QIcon, QPixmap, QPainter,
    QFont, QPolygonF, QPainterPath, QPalette, QDrag,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView, QWidget, QVBoxLayout,
    QToolButton, QLabel, QFileDialog, QMessageBox,
    QGridLayout, QDialog, QFormLayout, QLineEdit, QComboBox,
    QDialogButtonBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPlainTextEdit,
    QSizePolicy, QColorDialog, QHBoxLayout, QMenu, QFrame,
    QListWidget, QListWidgetItem,
)

from easycad.canvas.annotator_core import (
    _AnnotatorView, _ArrowItem, _PolyArrowItem, _ImageItem, _TitleBlockItem,
    _TableItem, _RectItem, _EllipseItem, _SymbolItem, _TextItem, _tool_icon,
    _attach_port_to_host, _find_port_host_near,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
)
from easycad.fileio.pdf_export import export_pdf
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.svg_import import parse_svg_items
from easycad.fileio.document import save_document, load_document, load_document_layers, dict_to_item
from easycad.fileio import symbol_library
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)
from easycad.canvas.host_widgets import _border_attach
from easycad.canvas.host_selection import _group_scene_rect
from easycad.canvas.host_dialogs import (
    _PaperSizeDialog, _TitleBlockDialog, _TableSizeDialog, _MermaidDialog, _PdfExportDialog,
)

# Mermaid 중립 shape → 우리 아이템. ('rect'|'ellipse'|'symbol', symbol kind|None).
# deep-interview 2026-07-21 확정 매핑. 둥근사각형은 사각형으로(라운딩 손실), 미인식은 사각형 폴백.
_MERMAID_SHAPE_ITEM = {
    "rect":          ("rect", None),
    "rounded":       ("rect", None),
    "stadium":       ("symbol", "terminal"),
    "rhombus":       ("symbol", "decision"),
    "hexagon":       ("symbol", "prep"),
    "parallelogram": ("symbol", "data"),
    "cylinder":      ("symbol", "database"),
    "circle":        ("ellipse", None),
}


# [Phase 6 M3 #17] 팔레트 드래그앤드롭 — 좌측 「도형·심볼」 버튼을 캔버스로 끌어 드롭.
_PALETTE_MIME = "application/x-easycad-tool"      # QDrag가 실어 나르는 tool_key 포맷
_PALETTE_DROP_WH = {
    # 사각형 기본 120×120(정사각) — 2026-08-09 deep-interview: "포트가 붙는 한 변 기준으로
    # 포트 10개 폭"이라는 사용자 어림값(포트 변 12 × 10)을 그대로 채택, 가로세로 비대칭일
    # 이유가 없어 정사각으로(구 120×72).
    "rect": (120.0, 120.0), "ellipse": (100.0, 100.0),
    "port_rect": (12.0, 12.0), "port_circle": (12.0, 12.0),   # 포트 기본 크기 — 2026-08-09
    # deep-interview: 실도면 대조로 텍스트 라벨보다 작은 절대 고정 크기(구 18→12)로 축소.
}
_PALETTE_SYM_WH = (120.0, 72.0)                   # 심볼(sym:*) 공통 기본 크기 (삼각형은 예외 — 아래 참조)
# [신규기능, 2026-08-09 deep-interview → 2026-08-10 후속] 삼각형은 정삼각형 기본을 원한다.
# [2026-08-10 후속] _sym_triangle()이 이제 bbox를 그대로 채운다(Lucid 대조 — 정삼각형 내접은
# 리사이즈 핸들이 실제 꼭짓점과 어긋나는 근본 원인이었다) — 그래서 "정삼각형처럼 보이는" 몫은
# 여기 기본 박스 비율(높이 대비 폭 = sqrt(3)/2)이 담당한다. 리사이즈하면 다른 도형처럼 그
# 비율이 깨지는 게 정상(원을 늘이면 타원 되는 것과 같음) — 기본 생성 시점만 정삼각형 보장.
_PALETTE_TRIANGLE_WH = (77.94, 90.0)




class _FileIOMixin:
    def _new_doc(self):
        self._scene.clear()
        self._reset_history()
        self._clip.clear()
        self._badge_n = 0
        self._doc_path = None
        self._reset_layers()


    def _open_doc(self):
        """[통합] 확장자로 분기 — .dxf/.dwg는 DXF 가져오기(DWG는 ODA File Converter로 먼저
        변환, §8 2026-08-14), 그 외는 .ecad 네이티브 열기. 셋 다 현재 씬을 통째로 교체(열기
        시맨틱) — 기존 도면 위에 추가 삽입하는 기능은 스코프 밖(deep-interview 2026-07-29 확정)."""
        path, _ = QFileDialog.getOpenFileName(self, "열기", "", self._OPEN_FILTER)
        if not path:
            return
        if path.lower().endswith((".dxf", ".dwg")):
            if not self._confirm_dxf_open_once():
                return
            self._do_open_dxf(path)
        else:
            self._do_open_ecad(path)


    def _do_open_ecad(self, path: str):
        try:
            n = load_document(self._scene, path)
            layers = load_document_layers(path)
        except Exception as e:  # noqa: BLE001 — 사용자에게 오류만 전달
            QMessageBox.warning(self, "열기 실패", str(e))
            return
        self._reset_history()
        self._doc_path = path
        self._apply_loaded_layers(layers)
        # 번호 마커 카운터를 로드된 최대값 뒤로 재설정
        nums = [it._number for it in self._scene.items() if hasattr(it, "_number")]
        self._badge_n = max(nums) if nums else 0
        self.statusBar().showMessage(f"열기 완료: {n}개 객체 — {path}", 5000)


    def _do_open_dxf(self, path: str):
        """.dxf/.dwg 공통 진입점. .dwg는 ODA File Converter 미설치 시 안내+경로지정 후
        1회 재시도(§8 DWG 자동변환, 2026-08-14). DWG 변환은 외부 프로세스 호출이라 몇 초
        걸릴 수 있어 대기 커서를 띄운다."""
        is_dwg = path.lower().endswith(".dwg")
        try:
            n = self._import_dxf_waited(path, is_dwg)
        except Exception as e:  # noqa: BLE001
            if is_dwg and self._is_odafc_missing(e):
                if not self._prompt_odafc_missing():
                    return
                try:
                    n = self._import_dxf_waited(path, is_dwg)
                except Exception as e2:  # noqa: BLE001
                    QMessageBox.warning(self, "DWG 열기", f"가져오기에 실패했습니다:\n{e2}")
                    return
            else:
                title = "DWG 열기" if is_dwg else "DXF 열기"
                QMessageBox.warning(self, title, f"가져오기에 실패했습니다:\n{e}")
                return
        self._reset_history()
        nums = [it._number for it in self._scene.items() if hasattr(it, "_number")]
        self._badge_n = max(nums) if nums else 0
        # [2026-07-29] 외부 DXF는 우리 앱과 원점·스케일이 무관해 가져온 직후 화면 밖이거나
        # 100% 줌에서 너무 작게/크게 보일 수 있다 — 열기 직후 항상 전체 맞춤(Ctrl+9와 동일).
        self._zoom_fit()
        self.statusBar().showMessage(f"가져오기 완료: {n}개 객체 — {path}", 5000)


    def _confirm_dxf_open_once(self) -> bool:
        """[통합] DXF/DWG 열기 안내 — 앱 생애 처음 1회만(사용자 요청, QSettings 플래그).
        현재 도면을 통째로 교체한다는 점 + 외부 CAD 도형은 근사 변환될 수 있음을 고지.
        [§8 DWG 자동변환, 2026-08-14] DWG는 내부적으로 DXF로 변환된 뒤 같은 경로를 타므로
        같은 안내·같은 1회성 플래그를 공유한다(별개 문구로 나눌 만큼 의미가 다르지 않음)."""
        settings = QSettings("EasyCAD", "EasyCAD")
        if settings.value("dxf_open_notified", False, type=bool):
            return True
        settings.setValue("dxf_open_notified", True)
        resp = QMessageBox.information(
            self, "DXF/DWG 열기",
            "DXF·DWG를 열면 현재 도면을 통째로 교체합니다(추가 삽입 아님).\n"
            "외부 CAD에서 만든 도형 중 일부(INSERT 배열·클리핑 등)는 근사 변환될 수 있습니다.\n\n"
            "계속 열까요?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        return resp == QMessageBox.StandardButton.Ok


    def _import_dxf_waited(self, path: str, is_dwg: bool) -> int:
        """[§8 DWG 자동변환] import_dxf 얇은 래퍼 — .dwg일 때만 대기 커서+상태바 문구를
        띄운다(ODA File Converter가 외부 프로세스라 큰 파일은 수 초 걸릴 수 있음, .dxf는
        기존과 동일하게 즉시 진행)."""
        if not is_dwg:
            return import_dxf(self._scene, path)
        self.statusBar().showMessage("DWG 변환 중… (ODA File Converter)")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            return import_dxf(self._scene, path)
        finally:
            QApplication.restoreOverrideCursor()


    @staticmethod
    def _is_odafc_missing(e: Exception) -> bool:
        """DWG→DXF 변환에 필요한 ODA File Converter가 안 깔려 있어서 난 예외인지 판별.
        [§8 DWG 자동변환] 지연 임포트 — odafc 모듈은 .dwg를 열 때만 필요하다(규칙 8, 무관한
        경로에 새 임포트를 얹지 않음)."""
        from ezdxf.addons.odafc import ODAFCNotInstalledError
        return isinstance(e, ODAFCNotInstalledError)


    def _prompt_odafc_missing(self) -> bool:
        """[§8 DWG 자동변환, 2026-08-14] ODA File Converter 미설치 안내 — 다운로드 링크 +
        「찾아보기」로 실행 파일 직접 지정. 지정한 경로는 QSettings에 영구 저장해 다음
        실행부터도 자동 반영(매 .dwg 열기 전 `dxf_import._apply_stored_odafc_path`가 읽음).
        반환 True면 호출부가 변환을 1회 재시도한다."""
        box = QMessageBox(self)
        box.setWindowTitle("DWG 열기")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("ODA File Converter를 찾을 수 없습니다.")
        box.setInformativeText(
            "DWG를 열려면 무료 프로그램 'ODA File Converter'가 필요합니다.\n"
            "다운로드: https://www.opendesign.com/guestfiles/oda_file_converter\n\n"
            "이미 설치했다면 '찾아보기'로 실행 파일(ODAFileConverter.exe) 위치를 "
            "직접 지정할 수 있습니다.")
        browse_btn = box.addButton("찾아보기...", QMessageBox.ButtonRole.ActionRole)
        box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not browse_btn:
            return False
        exe, _ = QFileDialog.getOpenFileName(
            self, "ODAFileConverter 실행 파일 위치 지정", "",
            "실행 파일 (*.exe);;모든 파일 (*)")
        if not exe:
            return False
        QSettings("EasyCAD", "EasyCAD").setValue("odafc_exe_path", exe)
        return True


    def _save_doc(self):
        """[통합] 저장 다이얼로그에서 고른 확장자로 분기 — 기본 필터는 항상 .ecad
        (DXF를 방금 열었어도 마찬가지, deep-interview 2026-07-29 결정)."""
        path, _ = QFileDialog.getSaveFileName(
            self, "저장", self._doc_path or "", self._DOC_FILTER)
        if not path:
            return
        if path.lower().endswith(".dxf"):
            if not self._confirm_dxf_save_once():
                return
            self._do_export_dxf(path)
        else:
            if not path.lower().endswith(".ecad"):
                path += ".ecad"
            self._do_save_ecad(path)


    def _do_save_ecad(self, path: str):
        try:
            save_document(self._scene, path, layers=self._layers)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "저장 실패", str(e))
            return
        self._doc_path = path
        self.statusBar().showMessage(f"저장 완료: {path}", 5000)


    def _confirm_dxf_save_once(self) -> bool:
        """[통합] DXF 저장 손실 경고 — 앱 생애 처음 1회만(QSettings 플래그), 이후는 조용히 진행."""
        settings = QSettings("EasyCAD", "EasyCAD")
        if settings.value("dxf_save_warned", False, type=bool):
            return True
        settings.setValue("dxf_save_warned", True)
        resp = QMessageBox.warning(
            self, "DXF로 저장",
            "DXF는 다른 CAD 프로그램과 호환되는 교환 포맷입니다.\n"
            "화살표 지속연결·라벨 위치·심볼 종류·레이어 소속·포트 부착 관계 등 Easy CAD "
            "전용 정보는 저장되지 않습니다(도형·텍스트·색상·두께·좌표는 보존 — 포트가 "
            "만든 테두리 끊김도 실제 선분으로는 보존되지만, 다시 열면 개별 선·도형일 뿐 "
            "포트로 인식되지 않습니다).\n\n계속 저장할까요?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        return resp == QMessageBox.StandardButton.Ok


    def _export_pdf(self):
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "PDF 내보내기", "출력할 객체가 없습니다.")
            return
        dlg = _PdfExportDialog(self, self._scene, bool(self._scene.selectedItems()))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.result_options()
        path, _ = QFileDialog.getSaveFileName(self, "PDF로 저장", "", "PDF 파일 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if export_pdf(self._scene, path, page=opts["page"], selection_only=opts["selection_only"],
                      orientation=opts["orientation"]):
            QMessageBox.information(self, "PDF 내보내기", f"저장 완료:\n{path}")
        else:
            QMessageBox.warning(self, "PDF 내보내기", "저장에 실패했습니다.")


    def _do_export_dxf(self, path: str):
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "DXF로 저장", "저장할 객체가 없습니다.")
            return
        try:
            export_dxf(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DXF로 저장", f"저장에 실패했습니다:\n{e}")
            return
        QMessageBox.information(self, "DXF로 저장", f"저장 완료:\n{path}")

    # ---- 이미지 삽입 (Phase 4) ---------------------------------------------
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
    _IMG_LONG = 400.0   # 삽입 시 긴 변 기본 크기(씬 단위) — 대형 사진이 캔버스를 뒤덮지 않게


    def _insert_image_or_svg(self):
        """[2026-08-12 재피드백] "이미지 삽입"과 "SVG 가져오기"의 파일선택창을 하나로 통합 —
        결과물(래스터 참고이미지 vs 실제 벡터 도형)은 서로 다르지만, 열기(Ctrl+O)가
        .ecad/.dxf를 확장자로 갈라 처리하는 것과 같은 패턴으로 확장자만 보고 기존 경로
        (`_insert_image_at`/`_insert_svgs_at`, 둘 다 무변경)로 나눠 보낸다."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "이미지/SVG 삽입", "",
            "이미지·SVG (*.png *.jpg *.jpeg *.bmp *.gif *.svg);;"
            "이미지 (*.png *.jpg *.jpeg *.bmp *.gif);;SVG (*.svg)")
        if not paths:
            return
        center = self._view.mapToScene(self._view.viewport().rect().center())
        svg_paths = [p for p in paths if p.lower().endswith(".svg")]
        img_paths = [p for p in paths if not p.lower().endswith(".svg")]
        if svg_paths:
            self._insert_svgs_at(svg_paths, center)
        for i, p in enumerate(img_paths):
            # 여러 장이면 살짝 어긋나게 배치(겹침 방지) — SVG처럼 가로 일렬은 사진엔
            # 과함(세로로 긴 사진도 흔함), 대각선 계단식이면 전부 조금씩은 드러난다.
            self._insert_image_at(p, center + QPointF(i * 40.0, i * 40.0))


    def _insert_image_at(self, path: str, scene_pos: QPointF):
        """path의 이미지를 scene_pos를 중심으로 삽입(긴 변 _IMG_LONG로 축소, 종횡비 유지)."""
        pm = QPixmap(path)
        if pm.isNull():
            QMessageBox.warning(self, "이미지 삽입", f"이미지를 열 수 없습니다:\n{path}")
            return
        self._insert_pixmap_at(pm, scene_pos, f"이미지 삽입: {pm.width()}×{pm.height()}px — {path}")


    def _insert_pixmap_at(self, pm: QPixmap, scene_pos: QPointF, status_msg: str):
        """QPixmap을 scene_pos 중심에 삽입(긴 변 _IMG_LONG로 축소, 종횡비 유지) — 파일 경로
        유무와 무관한 공통 경로(파일 삽입·드래그앤드롭·클립보드 붙여넣기가 공유)."""
        w, h = pm.width(), pm.height()
        s = min(1.0, self._IMG_LONG / max(w, h)) if max(w, h) > 0 else 1.0
        W, H = w * s, h * s
        item = _ImageItem(pm, QRectF(0.0, 0.0, W, H))
        item.setPos(scene_pos.x() - W / 2.0, scene_pos.y() - H / 2.0)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(status_msg, 4000)

    # ---- SVG 가져오기 (2026-08-04, §8 항목8 확장) ---------------------------
    # 실사용 동기: 순서도 도형 대신 직접 그리거나 AI로 만든 SVG 아이콘을 "팔레트에 등록"
    # 흐름에 태워 왼쪽 커스텀 심볼 팔레트에 쌓아가는 방식으로 전환(내장 파라메트릭 심볼
    # 대신 — 안테나 심볼 실사용 피드백 참조). 래스터(이미지 삽입)와 달리 실제 지오메트리로
    # 들여오므로 다른 손그림 도형과 동일하게 리사이즈·펜 두께·색이 편집된다.
    _SVG_LONG = 160.0   # 삽입 시 긴 변 기본 크기(씬 단위) — 기본 네모(150×90)와 비슷한 눈대중

    def _insert_svgs_at(self, paths: list[str], scene_pos: QPointF):
        """여러 SVG를 scene_pos부터 가로로 나란히 삽입(파일당 _SVG_LONG 간격) — 한 번의
        undo로 묶는다. 실패한 파일은 경고만 띄우고 나머지는 계속 가져온다(부분 성공)."""
        all_items = []
        failed = []
        step = self._SVG_LONG + 20.0
        start_x = scene_pos.x() - step * (len(paths) - 1) / 2.0
        self._scene.clearSelection()
        pen = self.make_pen()
        for i, path in enumerate(paths):
            pos = QPointF(start_x + step * i, scene_pos.y())
            try:
                items, _vb = parse_svg_items(path, self._SVG_LONG, pos)
            except Exception as e:  # noqa: BLE001 — 외부 파일 파싱, 원인 다양(구조 손상 등)
                failed.append((path, e))
                continue
            # [실사용 요청 2026-08-04] 도형끼리 자동 그룹 안 함 — 종전엔 DXF INSERT 흡수와
            # 같은 방식으로 `_group_id`를 묶어 하나처럼 선택되게 했는데, SVG 아이콘은 DXF
            # 블록과 달리 "손실 없이 이미 쪼개진 낱개 도형"이라 처음부터 개별 선택·이동이
            # 가능해야 한다는 지적("일부만 선택해도 전체가 선택되네") — 나중에 묶고 싶으면
            # 기존 Ctrl+G로 하면 된다.
            for it in items:
                if not isinstance(it, _TextItem):
                    it.setPen(QPen(pen))
                    if hasattr(it, "setBrush"):
                        it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable)
                self._scene.addItem(it)
                it.setSelected(True)
            all_items.extend(items)
        if all_items:
            self.push_undo_add_many(all_items)
            self.set_tool("select")
        msg = f"SVG 가져오기: 파일 {len(paths) - len(failed)}개, 도형 {len(all_items)}개"
        if failed:
            names = "\n".join(f"{p} — {e}" for p, e in failed)
            QMessageBox.warning(self, "SVG 가져오기",
                                f"{len(failed)}개 파일을 읽지 못했습니다:\n{names}")
        elif not all_items:
            QMessageBox.information(self, "SVG 가져오기", "가져올 도형이 없습니다.")
            return
        self.statusBar().showMessage(msg, 4000)


    def _create_shape_at(self, tool_key: str, scene_pos: QPointF):
        """[Phase 6 M3 #17] 팔레트에서 드롭한 도구를 scene_pos 중심에 기본 크기로 생성.
        무장 후 드래그로 그리는 경로(_AnnotatorView.mousePressEvent)와 같은 아이템·펜·플래그를
        써 이후 편집(리사이즈·회전·undo·저장)이 전부 동일하게 동작한다."""
        if tool_key.startswith("customsym:"):
            return self._create_custom_symbol_at(tool_key[len("customsym:"):], scene_pos)
        if tool_key in ("port_rect", "port_circle"):
            return self._create_port_at(tool_key, scene_pos)
        if tool_key.startswith("sym:"):
            kind = tool_key[4:]
            w, h = _PALETTE_TRIANGLE_WH if kind == "triangle" else _PALETTE_SYM_WH
            it = _SymbolItem(kind, QRectF(0.0, 0.0, w, h))
        elif tool_key in _PALETTE_DROP_WH:
            w, h = _PALETTE_DROP_WH[tool_key]
            it = (_EllipseItem if tool_key == "ellipse" else _RectItem)(QRectF(0.0, 0.0, w, h))
        else:
            return None
        it.setPen(self.make_pen())
        it.setBrush(self.make_brush())   # [신규기능] sticky 채움색
        it.setPos(scene_pos.x() - w / 2.0, scene_pos.y() - h / 2.0)
        it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(it)
        self._scene.clearSelection()
        it.setSelected(True)
        self.push_undo_add(it)
        return it


    def _create_port_at(self, tool_key: str, scene_pos: QPointF):
        """[신규기능 §8-12] 포트(작은 사각/원)를 scene_pos 근처 장비(사각형/삼각형) 테두리에
        부착 — 드래그앤드롭·클릭배치 두 경로가 공유. 근처에 유효한 장비가 없으면 자유 도형으로
        배치(나중에 손으로 옮겨 붙일 수 있음)."""
        w, h = _PALETTE_DROP_WH[tool_key]
        it = (_EllipseItem if tool_key == "port_circle" else _RectItem)(QRectF(0.0, 0.0, w, h))
        it.setPen(self.make_pen())
        it.setBrush(self.make_brush())
        # ItemSendsGeometryChanges: 포트를 드래그로 옮기면 itemChange(ItemPositionHasChanged)가
        # 발화해 (fx,fy) 갱신 + 호스트 재그리기(trim 자리 갱신)를 트리거한다.
        it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable
                    | it.GraphicsItemFlag.ItemSendsGeometryChanges)

        # [2026-08-09] 호스트 탐색 로직을 `_find_port_host_near`로 통합 — Alt+드래그 복제
        # 재부착(core_view.py `_maybe_alt_drag_copy`)과 공유해 판정이 두 곳에서 어긋나지 않게.
        host = _find_port_host_near(self._view, scene_pos)

        self._scene.addItem(it)
        if host is not None:
            _attach_port_to_host(it, host, scene_pos)
        else:
            it.setPos(scene_pos.x() - w / 2.0, scene_pos.y() - h / 2.0)
        self._scene.clearSelection()
        it.setSelected(True)
        self.push_undo_add(it)
        return it


    def _create_custom_symbol_at(self, sym_id: str, scene_pos: QPointF):
        """[신규기능 §8-8] 팔레트에 등록해 둔 커스텀 심볼(그룹)을 scene_pos에 재구성.
        단일 아이템이 아니라 그룹이라 위 분기와 별도 경로 — bbox 좌상단을 scene_pos에 맞춘다."""
        entry = next((e for e in symbol_library.load_library() if e.get("id") == sym_id), None)
        if entry is None:
            return None
        items = [it for it in (dict_to_item(d) for d in entry.get("items", [])) if it is not None]
        if not items:
            return None
        box = _group_scene_rect(items)
        dx, dy = scene_pos.x() - box.left(), scene_pos.y() - box.top()
        for it in items:
            it.moveBy(dx, dy)
            self._scene.addItem(it)
        if len(items) >= 2:
            gid = uuid.uuid4().hex[:8]
            for it in items:
                it._group_id = gid
        self._scene.clearSelection()
        self._bulk_select(items)
        self.push_undo_add_many(items)
        return items[0]


    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(_PALETTE_MIME) or (
                md.hasUrls() and any(u.toLocalFile().lower().endswith(self._IMG_EXTS)
                                     for u in md.urls())):
            e.acceptProposedAction()


    def dragMoveEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(_PALETTE_MIME) or md.hasUrls():
            e.acceptProposedAction()


    def eventFilter(self, obj, event):
        # [M3 #17] 캔버스 뷰포트 위의 팔레트 드래그를 여기서 직접 처리(뷰가 가로채기 전에).
        # 뷰포트 좌표 → mapToScene 로 놓은 자리에 도형 생성. 팔레트 mime가 아니면 통과.
        if obj is self._view.viewport():
            et = event.type()
            if et == QEvent.Type.Resize:
                # [미니맵 실조건 버그] dock 스플리터 드래그로 메인 뷰포트 크기가 바뀌면
                # CanvasWindow.resizeEvent(창 자체 리사이즈)는 안 불려 미니맵 인디케이터가
                # 갱신 안 됐다(사용자 GUI 확인 — 창 크기는 그대로인데 dock 배치만 바뀐 경우).
                # 뷰포트 자체의 resize를 잡아야 원인 불문 항상 정확하다.
                self._refresh_minimap()
            if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if event.mimeData().hasFormat(_PALETTE_MIME):
                    event.acceptProposedAction()
                    return True
            elif et == QEvent.Type.Drop and event.mimeData().hasFormat(_PALETTE_MIME):
                tool_key = bytes(event.mimeData().data(_PALETTE_MIME)).decode("utf-8")
                scene_pos = self._view.mapToScene(event.position().toPoint())
                if self._create_shape_at(tool_key, scene_pos) is not None:
                    event.acceptProposedAction()
                return True
        return super().eventFilter(obj, event)


    def dropEvent(self, e):
        md = e.mimeData()
        # [M3 #17] 팔레트 도형 드롭 — 놓은 위치에 기본 크기로 생성.
        if md.hasFormat(_PALETTE_MIME):
            tool_key = bytes(md.data(_PALETTE_MIME)).decode("utf-8")
            view_pt = self._view.mapFrom(self, e.position().toPoint())
            scene_pos = self._view.mapToScene(view_pt)
            if self._create_shape_at(tool_key, scene_pos) is not None:
                e.acceptProposedAction()
            return
        if not md.hasUrls():
            return
        view_pt = self._view.mapFrom(self, e.position().toPoint())
        scene_pos = self._view.mapToScene(view_pt)
        n = 0
        for u in md.urls():
            p = u.toLocalFile()
            if p.lower().endswith(self._IMG_EXTS):
                self._insert_image_at(p, scene_pos)
                scene_pos = QPointF(scene_pos.x() + 20.0, scene_pos.y() + 20.0)
                n += 1
        if n:
            e.acceptProposedAction()

    # ---- 표제란 / 용지틀 (Phase 4) ------------------------------------------

    def _insert_titleblock(self):
        """용지 크기·방향을 고르고 표제란 프레임을 삽입. 프레임은 뷰 중앙 근처에 좌상단 배치."""
        existing = self._find_titleblock()
        if existing is not None:
            QMessageBox.information(
                self, "표제란", "이미 표제란/용지틀이 있습니다.\n"
                "더블클릭해 내용을 편집하거나, 지운 뒤 다시 삽입하세요.")
            self._scene.clearSelection()
            existing.setSelected(True)
            return
        dlg = _PaperSizeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        size, orient = dlg.result_size_orient()
        item = _TitleBlockItem(size, orient)
        w, h = item.paper_wh()
        center = self._view.mapToScene(self._view.viewport().rect().center())
        item.setPos(center.x() - w / 2.0, center.y() - h / 2.0)
        item.setZValue(-1000.0)   # 용지는 그린 도형들 뒤에(시트처럼)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(
            f"표제란/용지틀 삽입: {size} {orient} — 더블클릭해 필드 입력", 5000)


    def _edit_titleblock(self, item):
        """표제란 더블클릭 → 필드 편집 폼(용지 크기·방향 포함)."""
        dlg = _TitleBlockDialog(self, item)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        size, orient = dlg.result_size_orient()
        item.set_paper(size, orient)
        item.set_fields(dlg.result_fields())
        self.statusBar().showMessage("표제란 갱신됨", 3000)


    def _find_titleblock(self):
        for it in self._scene.items():
            if isinstance(it, _TitleBlockItem):
                return it
        return None

    # ---- 표(table) 삽입 (Phase 4) -------------------------------------------
    _CELL_W, _CELL_H = 40.0, 14.0   # 삽입 시 셀 기본 치수(mm 월드좌표)


    def _insert_table(self):
        """행·열 개수를 고르고 균등 격자 표를 삽입(뷰 중앙에 배치). 셀은 더블클릭해 인라인 편집."""
        dlg = _TableSizeDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rows, cols, header = dlg.result()
        W, H = cols * self._CELL_W, rows * self._CELL_H
        item = _TableItem(rows, cols, QRectF(0.0, 0.0, W, H), header=header)
        center = self._view.mapToScene(self._view.viewport().rect().center())
        item.setPos(center.x() - W / 2.0, center.y() - H / 2.0)
        item.setFlags(item.GraphicsItemFlag.ItemIsMovable
                      | item.GraphicsItemFlag.ItemIsSelectable)
        self._scene.addItem(item)
        self._scene.clearSelection()
        item.setSelected(True)
        self.push_undo_add(item)
        self.set_tool("select")
        self.statusBar().showMessage(
            f"표 삽입: {rows}×{cols} — 셀 더블클릭해 편집(Enter/Tab 이동)", 5000)

    # ---- Mermaid 가져오기 (Phase 4) -----------------------------------------
    _MMD_NODE_W, _MMD_NODE_H = 120.0, 56.0   # 노드 기본 치수(mermaid_import 레이아웃 상수와 동일)


    def _insert_mermaid(self):
        """Mermaid flowchart 코드를 붙여넣어 편집가능 도형+화살표로 자동배치(뷰 중앙 기준).
        노드는 _RectItem/_EllipseItem/_SymbolItem, 엣지는 _PolyArrowItem 직교 라우팅으로 연결."""
        dlg = _MermaidDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            n_nodes, n_arrows, direction = self._build_mermaid(dlg.text())
        except MermaidError as ex:
            QMessageBox.warning(self, "Mermaid 가져오기", str(ex))
            return
        self.set_tool("select")
        self.statusBar().showMessage(
            f"Mermaid 가져오기: 노드 {n_nodes} · 화살표 {n_arrows} "
            f"(방향 {direction}) — 도형을 개별 이동·편집 가능", 6000)


    def _build_mermaid(self, text):
        """텍스트 → 도형·화살표를 씬에 배치(한 번의 undo). (노드수, 화살표수, 방향) 반환.
        파싱 실패 시 MermaidError를 올린다(UI 없음 — 스모크에서 그대로 호출 가능)."""
        graph = parse_mermaid(text)   # 실패 시 MermaidError

        W, H = self._MMD_NODE_W, self._MMD_NODE_H
        pos = layout_positions(graph, node_w=W, node_h=H)
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        min_x, min_y = (min(xs), min(ys)) if xs else (0.0, 0.0)
        span_x = (max(xs) - min_x + W) if xs else 0.0
        span_y = (max(ys) - min_y + H) if ys else 0.0
        center = self._view.mapToScene(self._view.viewport().rect().center())
        ox = center.x() - span_x / 2.0 - min_x
        oy = center.y() - span_y / 2.0 - min_y

        pen = self.make_pen()
        items_by_id: dict[str, object] = {}
        added: list = []
        for nid, node in graph.nodes.items():
            x, y = pos[nid]
            it = self._make_mermaid_node(node, ox + x, oy + y, W, H, pen)
            self._scene.addItem(it)
            it._sync_label()   # 라벨 중앙 정렬은 씬에 든 뒤라야 동작(_label_alive가 씬 멤버십을 봄)
            items_by_id[nid] = it
            added.append(it)

        arrows: list = []
        for e in graph.edges:
            s = items_by_id.get(e.src)
            d = items_by_id.get(e.dst)
            if s is None or d is None or s is d:   # self-loop은 스킵(직교 엘보 무의미)
                continue
            arr = self._make_mermaid_edge(e, s, d)
            self._scene.addItem(arr)
            arrows.append(arr)
            added.append(arr)

        # 노드·화살표를 모두 씬에 올린 뒤 직교 엘보를 계산(장애물·부착 법선이 씬 존재를 전제).
        for arr in arrows:
            try:
                arr.build_elbow()
            except Exception:
                pass
            arr._sync_label()   # 엣지 라벨도 씬에 든 뒤 재동기(build_elbow가 무변경이면 sync 생략되므로)

        self.push_undo_add_many(added)
        self._scene.clearSelection()
        return len(items_by_id), len(arrows), graph.direction


    def _make_mermaid_node(self, node, x, y, w, h, pen):
        shape, kind = _MERMAID_SHAPE_ITEM.get(node.shape, ("rect", None))
        rect = QRectF(0.0, 0.0, w, h)
        if shape == "ellipse":
            it = _EllipseItem(rect)
        elif shape == "symbol":
            it = _SymbolItem(kind, rect)
        else:
            it = _RectItem(rect)
        it.setPen(QPen(pen))
        it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setPos(x, y)
        it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable)
        if node.label:
            it.ensure_label().setPlainText(node.label)
        return it


    def _make_mermaid_edge(self, edge, src_it, dst_it):
        rs = src_it.mapRectToScene(src_it.rect())
        rd = dst_it.mapRectToScene(dst_it.rect())
        a_src = _border_attach(rs, rd.center())
        a_dst = _border_attach(rd, rs.center())
        arr = _PolyArrowItem(self.current_color, self.current_width, edge.arrow)
        arr.set_points(a_src, a_dst)   # arrow pos=(0,0) → local==scene 좌표
        # 지속 연결 — 도형 이동 시 화살표가 따라오도록 양끝을 부착점에 바인딩(부착점=변 중점 로컬좌표).
        arr.set_bound(0, src_it, src_it.mapFromScene(a_src))
        arr.set_bound(len(arr._pts) - 1, dst_it, dst_it.mapFromScene(a_dst))
        arr._auto_route = True   # 직교 자동 엘보(양끝 바인딩 → build_elbow가 경로 생성)
        if edge.label:
            arr.ensure_label().setPlainText(edge.label)
        return arr

    # ---- 상단 툴바 (QToolBar) -----------------------------------------------
    # [Phase 6 M1] 텍스트 버튼 → 아이콘, 파일·보기 액션을 상단으로 이관, 긴 단축키 라벨은
    # `?` 도움말로 분리. QToolBar를 쓰는 이유: 창을 좁히면 넘치는 버튼이 ≫ 오버플로우로
    # 접혀 창 최소폭이 작아진다(사용자 요청 "축소 유연성"). 그리기 도구는 체크형 커스텀
    # 버튼(set_tool 토글 동기화 유지 → `_tool_buttons`), 나머지는 공유 QAction.
