"""CanvasWindow 믹스인 — 파일 입출력 — 새문서/열기/저장/PDF·DXF 내보내기·가져오기/이미지·표제란·표·Mermaid 삽입/드래그앤드롭.

2026-08-02 host.py(3635줄) 분할분. `class CanvasWindow(...)`이 이 믹스인들을 다중상속해
메서드를 합친다 — 동작·이름 전부 원본과 동일(이동만), annotator_core.py가 이미 쓰는 믹스인
패턴을 host.py에도 적용한 것.
"""
from __future__ import annotations

import math
import os
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
    _attach_port_to_host, _find_port_host_near, _is_closed_trim_shape,
    _DEFAULT_COLOR, _DEFAULT_WIDTH, _DEFAULT_FONT, _DEFAULT_BADGE, _TOOLS,
    _MIN_FONT, _MAX_FONT, _COLOR_PRESETS,
    _SYMBOL_KINDS, PAPER_SIZES_MM, TB_FIELD_KEYS, TB_FIELD_LABELS,
    remap_grouped_bindings, regroup_duplicated_items, _pixmap_from_data,
)
from easycad.fileio.pdf_export import export_pdf, export_image, export_svg
from easycad.fileio.dxf_export import export_dxf, export_dwg
from easycad.fileio.dxf_import import import_dxf
from easycad.fileio.svg_import import parse_svg_items, parse_svg_string
from easycad.fileio.document import (
    save_document, load_document, load_document_layers, dict_to_item, item_to_dict,
)
from easycad.fileio import symbol_library
from easycad.fileio.mermaid_import import (
    parse_mermaid, layout_positions, MermaidError,
)
from easycad.canvas.host_widgets import _border_attach
from easycad.canvas.host_selection import _group_scene_rect, _render_symbol_thumbnail
from easycad.canvas.host_dialogs import (
    _PaperSizeDialog, _TitleBlockDialog, _TableSizeDialog, _MermaidDialog, _PdfExportDialog,
    _SvgAssetDialog, _AIGatewaySettingsDialog,
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
        """[§8 항목10 Stage B] "새로 만들기"(Ctrl+N) — 빈 문서를 새 탭으로 연다. 예전엔 현재
        씬을 통째로 비웠지만, 탭이 생긴 뒤로는 다른 탭의 작업을 그대로 둔 채 새 탭을 여는
        쪽이 자연스럽다(탭 도입에 따른 의도된 의미 변화). 클립보드(`_clip`)는 더는 문서별이
        아니라 창이 공유하는 상태(§8 항목10)라 여기서 비우지 않는다."""
        self._open_new_tab()


    def _focus_existing_tab_for(self, path: str) -> bool:
        """[실사용 피드백 2026-08-26] 이미 열려 있는 파일을 또 열면 새 탭을 만드는 대신 그
        탭으로 포커스만 옮긴다(VSCode 등 일반적인 편집기 관례) — 새 탭에 대해서만
        deep-interview로 확정했던 §8 항목10 Stage B 결정과 별개, "같은 파일 두 번 열기"는
        그때 고려 대상이 아니었다. `.ecad`는 `doc_path`, DXF/DWG는 `external_path`(위
        탭 제목 표시용 경로)와 비교 — 대소문자·상대경로 차이를 없애려 정규화한다."""
        target = os.path.normcase(os.path.abspath(path))
        for doc in self._docs:
            shown = doc.doc_path or doc.external_path
            if shown and os.path.normcase(os.path.abspath(shown)) == target:
                self._tabs.setCurrentIndex(self._docs.index(doc))
                return True
        return False

    def _open_doc(self):
        """[통합] 확장자로 분기 — .dxf/.dwg는 DXF 가져오기(DWG는 ODA File Converter로 먼저
        변환, §8 2026-08-14), 그 외는 .ecad 네이티브 열기. [§8 항목10 Stage B] 항상 새 탭에
        연다 — 예전엔 현재 씬을 통째로 교체했지만, 탭이 생긴 뒤로는 다른 탭의 작업을 보존해야
        하므로 자연스럽게 바뀐 의미다(기존 도면 '안에' 추가 삽입하는 기능은 여전히 스코프 밖,
        deep-interview 2026-07-29 확정). 로드가 실패하면 방금 연 빈 탭이 남는다(사용자가
        직접 닫으면 됨) — 실패가 드물고 되돌리기 쉬워 자동 정리까지는 하지 않는다.
        [실사용 피드백 2026-08-26] 단, 이미 열려 있는 파일이면 새 탭 없이 그 탭으로 이동."""
        path, _ = QFileDialog.getOpenFileName(self, "열기", "", self._OPEN_FILTER)
        if not path:
            return
        if self._focus_existing_tab_for(path):
            return
        if path.lower().endswith((".dxf", ".dwg")):
            if not self._confirm_dxf_open_once():
                return
            self._open_new_tab()
            self._do_open_dxf(path)
        else:
            self._open_new_tab()
            self._do_open_ecad(path)


    def _migrate_legacy_closed_cuts(self):
        """[TRIM 파괴적 재설계 1~4단계 완료, 2026-08-30] `.ecad` 하위호환 — 재설계 이전에
        저장된 파일은 닫힌 도형(`_is_closed_trim_shape` — 사각·원·심볼·닫힌다각형)에
        비파괴 `_cuts`(옛 방식)가 그대로 남아 있을 수 있다. 로드 직후(undo 히스토리가
        리셋되기 전) `finalize_closed_trim`을 재사용해 그 자리에서 바로 새 파괴적 표현
        (`_PolygonItem`/완전삭제)으로 확정한다 — 뒤이어 호출되는 `_reset_history()`가 이
        변환이 만든 임시 undo 엔트리를 곧바로 지우므로 사용자에게는 "그냥 열렸다"로만
        보인다(재저장하면 새 형식으로 굳는다 — 재설계 전 앱이 그 새 파일을 열어도
        `_PolygonItem`은 이미 정식 지원 타입이라 평범한 다각형으로 안전하게 뜬다)."""
        legacy = {it: [] for it in list(self._scene.items())
                  if _is_closed_trim_shape(it) and getattr(it, "_cuts", None)}
        if legacy:
            self.finalize_closed_trim(legacy)


    def _do_open_ecad(self, path: str):
        try:
            n = load_document(self._scene, path)
        except Exception as e:  # noqa: BLE001 — 사용자에게 오류만 전달
            QMessageBox.warning(self, "열기 실패", str(e))
            return
        self._migrate_legacy_closed_cuts()   # [TRIM 파괴적 재설계 1단계, 2026-08-30]
        # [code-review 2026-08-26] `load_document_layers`가 같은 파일을 별도로 다시
        # 여는데(레이어 목록만 뽑으려고), 그 사이 파일이 사라지거나 바뀌면(네트워크
        # 드라이브·동시 외부수정 등) 위 `load_document`는 이미 성공해 씬을 채웠는데도
        # 여기서 예외가 나 전체를 "열기 실패"로 되돌리던 게 있었다 — `_doc_path`가 끝내
        # 안 잡혀 방금 채운 씬이 "제목 없는 미완성 문서"로 남는 상태였다(docstring이
        # 문서화한 "실패 시 빈 탭"과 실제로 달랐음). 이미 유효함이 확인된 문서이므로
        # 레이어 읽기만 별도로 격리 — 실패해도 기본 레이어로 계속 진행한다.
        try:
            layers = load_document_layers(path)
        except Exception:
            layers = None
        self._reset_history()
        self._doc_path = path
        self._update_tab_title()   # [§8 항목10 Stage B] 탭 제목을 파일명으로
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
        # [실사용 피드백 2026-08-26] `doc_path`는 손실 변환이라 계속 비워두지만(Ctrl+S가
        # 조용히 DXF/DWG를 덮어쓰지 않도록), 탭 제목에는 파일명을 보여준다.
        self._external_path = path
        self._update_tab_title()
        # [2026-07-29] 외부 DXF는 우리 앱과 원점·스케일이 무관해 가져온 직후 화면 밖이거나
        # 100% 줌에서 너무 작게/크게 보일 수 있다 — 열기 직후 항상 전체 맞춤(Ctrl+9와 동일).
        self._zoom_fit()
        self.statusBar().showMessage(f"가져오기 완료: {n}개 객체 — {path}", 5000)


    def _confirm_dxf_open_once(self) -> bool:
        """[통합] DXF/DWG 열기 안내 — 앱 생애 처음 1회만(사용자 요청, QSettings 플래그).
        [§8 항목10 Stage B] 새 탭에 연다는 점(예전엔 "현재 도면을 통째로 교체") + 외부 CAD
        도형은 근사 변환될 수 있음을 고지. [§8 DWG 자동변환, 2026-08-14] DWG는 내부적으로
        DXF로 변환된 뒤 같은 경로를 타므로 같은 안내·같은 1회성 플래그를 공유한다(별개
        문구로 나눌 만큼 의미가 다르지 않음)."""
        settings = QSettings("EasyCAD", "EasyCAD")
        if settings.value("dxf_open_notified", False, type=bool):
            return True
        settings.setValue("dxf_open_notified", True)
        resp = QMessageBox.information(
            self, "DXF/DWG 열기",
            "DXF·DWG는 새 탭으로 엽니다(기존 도면 안에 추가 삽입 아님).\n"
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
            "직접 지정할 수 있습니다.\n\n"
            "다른 CAD 프로그램이 있다면 그 프로그램에서 DXF로 저장한 뒤 그 파일을 "
            "여는 것도 방법입니다(DXF는 별도 프로그램 없이 바로 열립니다).")
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
        """[통합] Ctrl+S — [§8 항목10 Stage C] 이미 저장 경로(.ecad)가 있으면 다이얼로그
        없이 그 경로로 바로 저장(빠른저장). 없으면(처음 저장하는 문서, 또는 DXF/DWG로 열어
        `_doc_path`가 비어 있는 문서 — "저장"의 기본 포맷은 언제나 .ecad라는 기존 결정 때문에
        DXF 출처를 되돌아 덮어쓰지 않는다) "다른 이름으로 저장"과 동일하게 다이얼로그를 띄운다."""
        if self._doc_path:
            self._do_save_ecad(self._doc_path)
        else:
            self._save_doc_as()


    def _save_doc_as(self):
        """[§8 항목10 Stage C] "다른 이름으로 저장"(Ctrl+Shift+S) — 항상 다이얼로그에서 고른
        확장자로 분기. 기본 필터는 항상 .ecad(DXF/DWG를 방금 열었어도 마찬가지,
        deep-interview 2026-07-29 결정). [§8 DWG 자동변환 후속, 2026-08-14] .dwg도 .dxf와
        같은 손실 경고를 거쳐 내보낸다."""
        path, _ = QFileDialog.getSaveFileName(
            self, "다른 이름으로 저장", self._doc_path or "", self._DOC_FILTER)
        if not path:
            return
        if path.lower().endswith((".dxf", ".dwg")):
            if not self._confirm_dxf_save_once():
                return
            if path.lower().endswith(".dwg"):
                self._do_export_dwg(path)
            else:
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
        self._active_doc.dirty = False   # [§8 항목10 Stage C] DXF/DWG 내보내기는 안 건드림(손실 변환)
        self._update_tab_title()
        self.statusBar().showMessage(f"저장 완료: {path}", 5000)


    def _confirm_dxf_save_once(self) -> bool:
        """[통합] DXF/DWG 저장 손실 경고 — 앱 생애 처음 1회만(QSettings 플래그), 이후는
        조용히 진행. [§8 DWG 자동변환 후속, 2026-08-14] DWG도 내부적으로 DXF를 거쳐
        나가므로(dxf_export.export_dwg) 손실 범위가 동일 — 같은 안내·같은 플래그 공유."""
        settings = QSettings("EasyCAD", "EasyCAD")
        if settings.value("dxf_save_warned", False, type=bool):
            return True
        settings.setValue("dxf_save_warned", True)
        resp = QMessageBox.warning(
            self, "DXF/DWG로 저장",
            "DXF·DWG는 다른 CAD 프로그램과 호환되는 교환 포맷입니다.\n"
            "화살표 지속연결·라벨 위치·심볼 종류·레이어 소속·포트 부착 관계 등 Easy CAD "
            "전용 정보는 저장되지 않습니다(도형·텍스트·색상·두께·좌표는 보존 — 포트가 "
            "만든 테두리 끊김도 실제 선분으로는 보존되지만, 다시 열면 개별 선·도형일 뿐 "
            "포트로 인식되지 않습니다).\n\n계속 저장할까요?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        return resp == QMessageBox.StandardButton.Ok


    # [내보내기 통합, 2026-08-20 실사용 피드백] PDF/PNG/SVG 공통 진입점 — File 메뉴
    # "내보내기" 하위메뉴·우클릭 메뉴가 형식별 기본값(default_format)·범위별 기본값
    # (default_selection_only)만 다르게 이 메서드 하나를 공유한다. 다이얼로그 안에서
    # 형식·범위를 서로 반대쪽으로 바꿀 수도 있어(라디오·콤보 그대로 노출) 별도 경로를
    # 두 벌 만들 필요가 없다.
    _EXPORT_FILTERS = {
        "pdf": ("PDF로 저장", "PDF 파일 (*.pdf)", ".pdf"),
        "png": ("PNG로 저장", "PNG 파일 (*.png)", ".png"),
        "svg": ("SVG로 저장", "SVG 파일 (*.svg)", ".svg"),
    }

    def _export_document(self, default_format: str = "pdf", default_selection_only: bool = False):
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "내보내기", "출력할 객체가 없습니다.")
            return
        dlg = _PdfExportDialog(self, self._scene, bool(self._scene.selectedItems()),
                               default_format=default_format,
                               default_selection_only=default_selection_only)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.result_options()
        fmt = opts["format"]
        title, filt, ext = self._EXPORT_FILTERS[fmt]
        path, _ = QFileDialog.getSaveFileName(self, title, "", filt)
        if not path:
            return
        if not path.lower().endswith(ext):
            path += ext
        common = dict(page=opts["page"], selection_only=opts["selection_only"],
                     orientation=opts["orientation"], frame=opts.get("frame"),
                     margins_mm=opts["margins_mm"])
        if fmt == "pdf":
            ok = export_pdf(self._scene, path, **common)
        elif fmt == "png":
            ok = export_image(self._scene, path, transparent=opts["transparent"], **common)
        else:
            ok = export_svg(self._scene, path, transparent=opts["transparent"], **common)
        if ok:
            QMessageBox.information(self, "내보내기", f"저장 완료:\n{path}")
        else:
            QMessageBox.warning(self, "내보내기", "저장에 실패했습니다.")

    def _export_pdf(self):
        """File 메뉴 「PDF 내보내기…」(Ctrl+P·툴바 버튼) — 항상 PDF·전체 도면 기본."""
        self._export_document("pdf", False)


    def _do_export_dxf(self, path: str):
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "DXF로 저장", "저장할 객체가 없습니다.")
            return
        try:
            export_dxf(self._scene, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "DXF로 저장", f"저장에 실패했습니다:\n{e}")
            return
        # [실사용 피드백 2026-08-26] doc_path는 그대로 비워두되(손실 변환이라 Ctrl+S가
        # 이 파일을 조용히 덮어쓰면 안 됨) 탭 제목에는 파일명을 보여준다.
        self._external_path = path
        self._update_tab_title()
        QMessageBox.information(self, "DXF로 저장", f"저장 완료:\n{path}")


    def _do_export_dwg(self, path: str):
        """[§8 DWG 자동변환 후속, 2026-08-14] DWG로 저장 — `_do_open_dxf`의 ODAFC 미설치
        처리(안내+경로지정 후 1회 재시도)와 같은 구조. 코드 공유 대신 이미 검증된
        `_do_open_dxf`를 안 건드리는 쪽을 택했다(§8 항목9 구현 관례 그대로)."""
        if self._scene.itemsBoundingRect().isEmpty():
            QMessageBox.information(self, "DWG로 저장", "저장할 객체가 없습니다.")
            return
        try:
            self._export_dwg_waited(path)
        except Exception as e:  # noqa: BLE001
            if self._is_odafc_missing(e):
                if not self._prompt_odafc_missing():
                    return
                try:
                    self._export_dwg_waited(path)
                except Exception as e2:  # noqa: BLE001
                    QMessageBox.warning(self, "DWG로 저장", f"저장에 실패했습니다:\n{e2}")
                    return
            else:
                QMessageBox.warning(self, "DWG로 저장", f"저장에 실패했습니다:\n{e}")
                return
        # [실사용 피드백 2026-08-26] DXF 저장과 동일 — doc_path는 비워두고 탭 제목만 갱신.
        self._external_path = path
        self._update_tab_title()
        QMessageBox.information(self, "DWG로 저장", f"저장 완료:\n{path}")


    def _export_dwg_waited(self, path: str):
        """[§8 DWG 자동변환 후속] export_dwg 얇은 래퍼 — 대기 커서+상태바(외부 프로세스
        호출이라 몇 초 걸릴 수 있음, `_import_dxf_waited`와 동일 관례)."""
        self.statusBar().showMessage("DWG 변환 중… (ODA File Converter)")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            export_dwg(self._scene, path)
        finally:
            QApplication.restoreOverrideCursor()

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
            # [code-review 2026-08-26] 전부 실패(all_items도 비어 있음)면 여기서 끝 —
            # return이 없어 아래 상태바에 "파일 0개, 도형 0개"를 또 찍어 방금 뜬 경고와
            # 같은 실패를 중복 보고하고 있었다. 일부만 성공했으면(all_items 있음) 계속
            # 진행해 상태바에 몇 개가 실제로 들어왔는지 알려준다.
            if not all_items:
                return
        elif not all_items:
            QMessageBox.information(self, "SVG 가져오기", "가져올 도형이 없습니다.")
            return
        self.statusBar().showMessage(msg, 4000)

    # ---- AI SVG 에셋 생성 (§8 항목20 B단계, 2026-08-14) ----------------------
    # 위 SVG 가져오기(파일)와 소스만 다르다 — AI 게이트웨이 응답 문자열을 파일 없이
    # 바로 파싱(`parse_svg_string`)해 같은 펜 관례(텍스트 제외 현재 그리기색, NoBrush)로
    # 아이템을 만든다. 씬 추가·undo는 호출부(삽입 vs 대체)가 각자 처리 — 대체 경로
    # (`host_context._generate_svg_replace`)는 remove+create를 한 undo 엔트리로 묶어야
    # 해서 이 헬퍼는 아이템만 만들고 씬에는 안 넣는다.

    def _svg_text_to_items(self, svg_text: str, long_side: float, center: QPointF):
        """AI가 생성한 SVG 문자열 → 우리 네이티브 아이템 리스트(펜·플래그 적용, 씬 미추가)."""
        items, _vb = parse_svg_string(svg_text, long_side, center)
        pen = self.make_pen()
        for it in items:
            if not isinstance(it, _TextItem):
                it.setPen(QPen(pen))
                if hasattr(it, "setBrush"):
                    it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable)
        return items

    def _open_ai_gateway_settings(self):
        """삽입(&I) 메뉴 「AI 게이트웨이 설정…」 진입점(2026-08-20 피드백) — Mermaid/SVG
        창 안의 설정 버튼과 같은 `_AIGatewaySettingsDialog`를 독립적으로 연다."""
        _AIGatewaySettingsDialog(self).exec()

    def _get_svg_asset_dialog(self) -> "_SvgAssetDialog":
        """[실사용 피드백 2026-08-25] "닫았다 다시 열어도 이전 결과가 살아있으면 좋겠다"
        — 매번 새로 `_SvgAssetDialog(self)`를 만들면 후보·코드·첨부이미지·프롬프트가
        닫는 순간 통째로 버려졌다. 이제 창당 인스턴스 하나만 지연 생성해 재사용한다(
        `dlg.exec()`만 다시 호출 — QDialog는 재실행 가능). "다시 AI로 생성할 때만
        기존 걸 날린다"는 요구는 이미 `_on_generate_clicked`→`_clear_candidates()`
        흐름이 그 정책이라(생성 버튼을 눌러야만 후보 초기화) 별도 로직이 필요 없다.
        deep-interview로 확정: 삽입(새 도형)과 대체(`host_context._generate_svg_
        replace`, 기존 도형 1개 대체) 두 진입점이 **하나의 서랍을 공유**한다(사용자
        선택 — 분리안도 검토했으나 "방금 만든 후보를 다른 자리에도 써보고 싶다"는
        재사용 의도를 우선). 부수 이득: 모델 목록 재조회(`_populate_models`, 최초
        오픈만 느렸던 비동기 호출)도 두 번째부턴 아예 안 일어나 재오픈이 더 빠르다."""
        dlg = getattr(self, "_svg_asset_dialog", None)
        if dlg is None:
            dlg = _SvgAssetDialog(self)
            self._svg_asset_dialog = dlg
        return dlg

    def _insert_ai_svg_asset(self):
        """메뉴 진입점(삽입(&I) 메뉴 「AI SVG 에셋 생성…」) — 뷰 중심에 새로 삽입.
        우클릭 「SVG로 생성」(기존 도형 대체)은 `host_context._generate_svg_replace`가
        `_get_svg_asset_dialog()`로 같은 인스턴스를 공유하되 별도 undo 경로를 쓴다.
        [실사용 피드백 2026-08-25] "체크한 후보 여러 개를 다 넣어달라" — 예전엔 체크박스로
        몇 개를 골라도 코드칸(`selected_svg()`, 클릭 단일선택 1개)만 삽입됐다.
        `svgs_for_insert()`(체크됨 있으면 체크된 전부, 없으면 기존처럼 코드칸 1개)로
        바꾸고, 2개 이상이면 `_place_svg_groups_no_overlap`으로 서로 안 겹치게 격자
        배치한다. "도형 대체"(위 `_generate_svg_replace`, 대상이 기존 도형 1개)는 다중
        삽입 개념 자체가 안 맞아 그대로 `selected_svg()` 단일 경로를 유지한다."""
        dlg = self._get_svg_asset_dialog()
        dlg.set_confirm_label("확인 (도형 삽입)")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        svg_texts = dlg.svgs_for_insert()
        if not svg_texts:
            return
        center = self._view.mapToScene(self._view.viewport().rect().center())
        groups = []
        for svg_text in svg_texts:
            try:
                items = self._svg_text_to_items(svg_text, self._SVG_LONG, QPointF(0.0, 0.0))
            except Exception:  # noqa: BLE001 — 후보 하나 실패해도 나머지는 계속 삽입
                continue
            if items:
                groups.append(items)
        if not groups:
            QMessageBox.warning(self, "AI SVG 에셋 생성", "가져올 도형이 없습니다.")
            return
        all_items = self._place_svg_groups_no_overlap(groups, center)
        self._scene.clearSelection()
        for it in all_items:
            self._scene.addItem(it)
            it.setSelected(True)
        self.push_undo_add_many(all_items)
        self.set_tool("select")
        msg = (f"AI SVG 에셋 삽입: 도형 {len(all_items)}개" if len(groups) <= 1 else
               f"AI SVG 에셋 삽입: 후보 {len(groups)}개, 도형 {len(all_items)}개")
        self.statusBar().showMessage(msg, 4000)

    def _place_svg_groups_no_overlap(self, groups: list, center: QPointF) -> list:
        """[2026-08-25] 체크한 SVG 후보 여러 개를 한 번에 삽입할 때 서로 안 겹치도록
        정사각형에 가까운 격자로 나눠 놓는다 — 칸 크기는 후보 중 가장 큰 bbox+여백에
        맞춰 전부 통일(후보마다 크기가 달라도 겹칠 일이 없다), 격자 전체를 뷰 중심에
        맞춘다. 단일 후보(len==1)도 같은 경로를 타되 격자가 1칸이라 기존 "뷰 중심에
        바로 삽입" 동작과 결과가 같다."""
        boxes = [_group_scene_rect(items) for items in groups]
        gap = 24.0
        cell_w = max(b.width() for b in boxes) + gap
        cell_h = max(b.height() for b in boxes) + gap
        cols = max(1, math.ceil(math.sqrt(len(groups))))
        rows = math.ceil(len(groups) / cols)
        origin_x = center.x() - (cols * cell_w) / 2.0
        origin_y = center.y() - (rows * cell_h) / 2.0
        all_items = []
        for i, (items, box) in enumerate(zip(groups, boxes)):
            r, c = divmod(i, cols)
            cell_cx = origin_x + c * cell_w + cell_w / 2.0
            cell_cy = origin_y + r * cell_h + cell_h / 2.0
            dx, dy = cell_cx - box.center().x(), cell_cy - box.center().y()
            for it in items:
                it.moveBy(dx, dy)
            all_items.extend(items)
        return all_items

    def _save_svg_candidates_to_symbols(self, entries: list[tuple[str, str]],
                                        subject: str, folder: str | None) -> int:
        """SVG 후보(체크된 카드) 여러 개를 한 번에 내 심볼 팔레트에 등록 — §8 항목20 후속
        Stage 4(2026-08-19). `_SvgAssetDialog`가 `getattr(self, ...)`로 이름만 보고
        호출한다(그 다이얼로그는 순환 임포트를 피하는 잎 모듈이라 이 파일을 직접 import
        못 함, `host_dialogs._on_save_to_symbols_clicked` 참조). `register_selection_
        as_symbol`(host_selection.py)과 같은 관례(위치를 bbox 좌상단 기준으로 정규화,
        실제 렌더 캡처 썸네일)를 따르되, 소스가 캔버스 선택이 아니라 아직 씬에 없는 SVG
        파싱 결과라는 점만 다르다 — `_svg_text_to_items`로 만든 임시 아이템을 그대로
        재사용(씬에는 추가하지 않음, 등록만 하고 버림)."""
        saved = 0
        for svg_text, model_used in entries:
            try:
                items = self._svg_text_to_items(svg_text, self._SVG_LONG, QPointF(0.0, 0.0))
            except Exception:  # noqa: BLE001 — 후보 하나 실패해도 나머지는 계속 저장
                continue
            if not items:
                continue
            dicts = [d for d in (item_to_dict(it) for it in items) if d is not None]
            if not dicts:
                continue
            box = _group_scene_rect(items)
            for d in dicts:
                d["pos"][0] -= box.left()
                d["pos"][1] -= box.top()
            thumb = _render_symbol_thumbnail(items, box)
            name = f"{subject} — {model_used}" if subject else model_used
            symbol_library.add_symbol(name, dicts, thumb, folder)
            saved += 1
        if saved:
            self._refresh_custom_symbol_section()
        return saved


    def _build_shape_item(self, tool_key: str):
        """[리팩터 2026-08-19] `_create_shape_at`의 '아이템 생성+스타일링'만 분리 —
        씬 추가·선택·undo push는 호출부(`_create_shape_at`/팔레트 실시간 드래그
        `_palette_drag_begin`) 각자 몫이다. 포트·커스텀심볼은 각각 호스트 부착·그룹
        재구성이라는 별도 배치 로직이 있어 여기 포함하지 않는다(호출부가 먼저 걸러낸다).
        반환: (아이템, w, h) 또는 미지원 tool_key면 None."""
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
        it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable)
        return it, w, h


    def _create_shape_at(self, tool_key: str, scene_pos: QPointF):
        """[Phase 6 M3 #17] 팔레트에서 드롭한 도구를 scene_pos 중심에 기본 크기로 생성.
        무장 후 드래그로 그리는 경로(_AnnotatorView.mousePressEvent)와 같은 아이템·펜·플래그를
        써 이후 편집(리사이즈·회전·undo·저장)이 전부 동일하게 동작한다."""
        if tool_key.startswith("customsym:"):
            return self._create_custom_symbol_at(tool_key[len("customsym:"):], scene_pos)
        if tool_key in ("port_rect", "port_circle"):
            return self._create_port_at(tool_key, scene_pos)
        built = self._build_shape_item(tool_key)
        if built is None:
            return None
        it, w, h = built
        it.setPos(scene_pos.x() - w / 2.0, scene_pos.y() - h / 2.0)
        self._scene.addItem(it)
        self._scene.clearSelection()
        it.setSelected(True)
        self.push_undo_add(it)
        return it


    def _palette_drag_begin(self, tool_key: str) -> bool:
        """[신규기능 2026-08-19, 실사용 피드백] 팔레트 버튼 드래그 임계 넘김(`_PaletteButton`)
        — 진짜 임시 도형을 씬에 만들어 커서를 따라다니게 한다. 이러면 이동 중에도 기존
        도형 이동과 완전히 같은 `_view._apply_smart_snap()`을 그대로 태울 수 있어(호출부
        `_palette_drag_move`), 정렬 스냅이 드롭 순간이 아니라 드래그 도중에도 실시간으로
        걸린다 — 네이티브 QDrag는 OS가 고스트 이미지를 직접 그려 앱이 위치를 되돌릴 수
        없어(플랫폼 공통 제약) 이 체감을 낼 수 없었다(기존 도형 이동과 다르다는 실사용
        지적으로 확인). 반환 False면 `_PaletteButton`이 기존 네이티브 QDrag로 폴백한다
        — 포트(호스트 테두리 부착이라는 별도 배치 로직, `_create_port_at`)가 그 경우.
        [실사용 피드백 2026-08-25] 커스텀 심볼("customsym:")도 예전엔 이 False 폴백
        대상이라 OS 고스트가 팔레트 아이콘 크기(28px)로만 보였다 — "기본도형은 실제
        캔버스 크기로 보이는데 내 심볼만 다르다"는 지적으로 여기 그룹 경로를 신설,
        `_palette_drag_group`(리스트)로 단일 아이템 경로와 상태를 분리해 이후
        `_palette_drag_move`/`_palette_drag_end`가 둘 중 있는 쪽만 따른다."""
        if tool_key in ("port_rect", "port_circle"):
            return False
        if tool_key.startswith("customsym:"):
            built = self._build_custom_symbol_items(tool_key[len("customsym:"):])
            if built is None:
                return False
            items, box = built
            dx, dy = -box.left(), -box.top()
            for it in items:
                it.moveBy(dx, dy)
                it.setOpacity(0.6)
                self._scene.addItem(it)
            self._scene.clearSelection()
            for it in items:
                it.setSelected(True)
            self._palette_drag_group = items
            # [drift 방지] 매 이동 프레임마다 커서 기준 절대좌표로 다시 배치하므로(단일
            # 아이템의 setPos와 동일한 관례), 각 아이템의 "그룹 박스 좌상단 기준 상대
            # 오프셋"을 한 번만 기록해둔다 — moveBy 델타를 누적하면 이전 프레임의 스냅
            # 보정까지 매번 다시 얹혀 그룹 형태가 서서히 어긋날 수 있다.
            self._palette_drag_offsets = [it.pos() for it in items]
            self._palette_drag_size = (box.width(), box.height())
            return True
        built = self._build_shape_item(tool_key)
        if built is None:
            return False
        it, w, h = built
        it.setOpacity(0.6)   # [UX] 아직 확정 전임을 반투명으로 표시(드롭하면 1.0으로 복원)
        self._scene.addItem(it)
        self._scene.clearSelection()
        it.setSelected(True)
        self._palette_drag_item = it
        self._palette_drag_size = (w, h)
        return True


    def _palette_drag_move(self, tool_key: str, global_pos: QPoint):
        """[신규기능 2026-08-19] 팔레트 드래그 중 매 이동 호출 — 커서 아래 씬 좌표로 임시
        도형을 옮기고, 기존 도형 이동과 동일한 스냅 체인(`_apply_smart_snap` → 정렬
        가이드 축은 건너뛰고 나머지만 `_apply_grid_snap_move`)을 그대로 태운다. 캔버스
        뷰포트 밖이면(다른 패널 위 등) 숨겨서 엉뚱한 자리에 스냅되지 않게 한다.
        [2026-08-25] 커스텀 심볼(그룹, `_palette_drag_group`)은 여러 아이템을 한 번에
        옮겨야 해 단일 아이템 분기와 나눴다 — 스냅 호출부(`_apply_smart_snap` 등)는
        선택된 아이템 전부(다중선택 그룹 bbox 지원, 2026-08-25)를 그대로 다루므로 공유."""
        it = getattr(self, "_palette_drag_item", None)
        group = getattr(self, "_palette_drag_group", None)
        if it is None and not group:
            return
        items = group if group else [it]
        vp = self._view.viewport()
        local = vp.mapFromGlobal(global_pos)
        inside = vp.rect().contains(local)
        if not inside:
            if items[0].isVisible():
                for x in items:
                    x.setVisible(False)
            if self._view._align_guides:
                self._view._align_guides = []
                self._view.viewport().update()
            return
        if not items[0].isVisible():
            for x in items:
                x.setVisible(True)
        w, h = self._palette_drag_size
        scene_pos = self._view.mapToScene(local)
        tx, ty = scene_pos.x() - w / 2.0, scene_pos.y() - h / 2.0
        if group:
            offsets = self._palette_drag_offsets
            for x, off in zip(group, offsets):
                x.setPos(tx + off.x(), ty + off.y())
        else:
            it.setPos(tx, ty)
        self._view._apply_smart_snap()
        skip_x = any(g[0] == "v" for g in self._view._align_guides)
        skip_y = any(g[0] == "h" for g in self._view._align_guides)
        self._view._apply_grid_snap_move(skip_x, skip_y)
        self._view.viewport().update()


    def _palette_drag_end(self, tool_key: str, global_pos: QPoint):
        """[신규기능 2026-08-19] 팔레트 드래그 release — 캔버스 위면 확정(undo 등록·불투명
        복원), 밖이면 임시 도형을 그냥 지운다(=취소, 드롭 안 함과 동일한 관례).
        [2026-08-25] 그룹(`_palette_drag_group`)은 `_finish_custom_symbol_placement`
        (그룹ID 부여+선택+undo 1건)로 마무리 — `_create_custom_symbol_at`(단발 배치)과
        같은 경로라 undo·그룹ID 관례가 자연히 일치한다."""
        it = getattr(self, "_palette_drag_item", None)
        group = getattr(self, "_palette_drag_group", None)
        self._palette_drag_item = None
        self._palette_drag_group = None
        self._palette_drag_offsets = None
        self._view._align_guides = []
        if it is None and not group:
            return
        items = group if group else [it]
        vp = self._view.viewport()
        inside = vp.rect().contains(vp.mapFromGlobal(global_pos))
        if not inside:
            for x in items:
                self._scene.removeItem(x)
            self._view.viewport().update()
            return
        for x in items:
            x.setOpacity(1.0)
        if group:
            self._finish_custom_symbol_placement(items)
        else:
            it.setSelected(True)
            self.push_undo_add(it)
        # [실사용 피드백 2026-08-25] 팔레트 버튼이 드래그 내내 grabMouse()로 키보드 포커스를
        # 안 가진 위젯이었으므로, 드롭 후 캔버스 뷰가 키보드 포커스를 도로 안 받으면(도형은
        # 선택됐어도) Ctrl+Enter/Tab/Enter 같은 단축키가 뷰에 아예 도착하지 못한다.
        self._view.setFocus(Qt.FocusReason.MouseFocusReason)
        self._view.viewport().update()


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


    def _build_custom_symbol_items(self, sym_id: str):
        """[클릭-드래그 배치 2026-08-19] 등록된 커스텀 심볼(그룹) 항목들을 원본 배치 그대로
        재구성만 하고 씬엔 아직 안 넣는다 — `_create_custom_symbol_at`(단발 배치)과 캔버스
        드래그-리사이즈 배치(`core_view.py`의 `_csym_drag`) 둘 다 이 조립 단계를 공유한다.
        반환: (items, box) 또는 항목이 없으면 None. `box`는 아이템들이 씬에 없어도
        `mapToScene`이 자기 좌표계 기준으로 동작하므로 `_group_scene_rect`로 바로 잴 수 있다."""
        entry = next((e for e in symbol_library.load_library() if e.get("id") == sym_id), None)
        if entry is None:
            return None
        items = [it for it in (dict_to_item(d) for d in entry.get("items", [])) if it is not None]
        if not items:
            return None
        box = _group_scene_rect(items)
        return items, box

    def _finish_custom_symbol_placement(self, items):
        """씬에 이미 놓인(위치 확정된) 커스텀 심볼 그룹의 마무리 — 그룹ID 부여+선택+undo 등록.
        단발 배치·드래그 리사이즈 배치 둘 다 마지막에 이걸 부른다."""
        if len(items) >= 2:
            gid = uuid.uuid4().hex[:8]
            for it in items:
                it._group_id = gid
        self._scene.clearSelection()
        self._bulk_select(items)
        self.push_undo_add_many(items)

    def _create_custom_symbol_at(self, sym_id: str, scene_pos: QPointF):
        """[신규기능 §8-8] 팔레트에 등록해 둔 커스텀 심볼(그룹)을 scene_pos에 기본 크기로
        재구성(드래그 없는 단발 배치 — 캔버스에서 클릭-드래그로 크기를 조절하는 경로는
        `core_view.py`의 `_csym_drag` 참조). 단일 아이템이 아니라 그룹이라 위 분기와 별도
        경로 — bbox 좌상단을 scene_pos에 맞춘다."""
        built = self._build_custom_symbol_items(sym_id)
        if built is None:
            return None
        items, box = built
        dx, dy = scene_pos.x() - box.left(), scene_pos.y() - box.top()
        for it in items:
            it.moveBy(dx, dy)
            self._scene.addItem(it)
        self._finish_custom_symbol_placement(items)
        return items[0]


    # [드래그앤드롭 확장, 2026-08-23] 이미지 외에 .ecad(새 탭 열기)/.dxf·.dwg(새 탭
    # 가져오기)/.svg(도형 삽입)도 캔버스에 직접 끌어놓을 수 있게 — 각각 이미 있던 열기/
    # 가져오기/삽입 함수(_do_open_ecad/_do_open_dxf/_insert_svgs_at)를 그대로 재사용한다.
    _DOC_EXTS = (".ecad",)
    _DXF_EXTS = (".dxf", ".dwg")
    _DROP_EXTS = _IMG_EXTS + _DOC_EXTS + _DXF_EXTS + (".svg",)

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(_PALETTE_MIME) or (
                md.hasUrls() and any(u.toLocalFile().lower().endswith(self._DROP_EXTS)
                                     for u in md.urls())):
            e.acceptProposedAction()


    def dragMoveEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(_PALETTE_MIME) or (
                md.hasUrls() and any(u.toLocalFile().lower().endswith(self._DROP_EXTS)
                                     for u in md.urls())):
            e.acceptProposedAction()


    def _handle_url_drop(self, md, scene_pos: QPointF) -> int:
        """[드래그앤드롭 확장, 2026-08-23] URL 목록(md.hasUrls())을 확장자별로 분류해
        연다/가져온다/삽입한다 — `dropEvent`(창 레벨)와 `eventFilter`(뷰포트 레벨, 아래
        참조)가 공유하는 실제 처리 본문. 반환값은 처리한 개수(0이면 아무 URL도 못 알아봄)."""
        paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        doc_paths = [p for p in paths if p.lower().endswith(self._DOC_EXTS)]
        dxf_paths = [p for p in paths if p.lower().endswith(self._DXF_EXTS)]
        svg_paths = [p for p in paths if p.lower().endswith(".svg")]
        img_paths = [p for p in paths if p.lower().endswith(self._IMG_EXTS)]
        n = 0
        # .ecad/.dxf·.dwg는 기존 "열기(Ctrl+O)"와 동일하게 새 탭에 연다(현재 도면 보존).
        # [실사용 피드백 2026-08-26] 단, 이미 열려 있는 파일이면 새 탭 대신 그 탭으로 이동
        # (`_open_doc`과 동일 관례 — `_focus_existing_tab_for`).
        for p in doc_paths:
            if self._focus_existing_tab_for(p):
                n += 1
                continue
            self._open_new_tab()
            self._do_open_ecad(p)
            n += 1
        for p in dxf_paths:
            if self._focus_existing_tab_for(p):
                n += 1
                continue
            if not self._confirm_dxf_open_once():
                continue
            self._open_new_tab()
            self._do_open_dxf(p)
            n += 1
        # SVG·이미지는 현재 도면(마지막에 열린 탭이 있으면 그 탭) 위 드롭 위치에 바로 삽입.
        if svg_paths:
            self._insert_svgs_at(svg_paths, scene_pos)
            n += len(svg_paths)
        for p in img_paths:
            self._insert_image_at(p, scene_pos)
            scene_pos = QPointF(scene_pos.x() + 20.0, scene_pos.y() + 20.0)
            n += 1
        return n


    def eventFilter(self, obj, event):
        # [M3 #17] 캔버스 뷰포트 위의 팔레트 드래그를 여기서 직접 처리(뷰가 가로채기 전에).
        # 뷰포트 좌표 → mapToScene 로 놓은 자리에 도형 생성. 팔레트 mime가 아니면 통과.
        # [드래그앤드롭 확장, 2026-08-23] 실사용 재현으로 발견 — `viewport().setAcceptDrops
        # (True)`가 걸려 있으면 팔레트 mime이 아닌 드래그(파일 URL 등)도 Qt가 CanvasWindow가
        # 아니라 뷰포트로 직접 보낸다. `QGraphicsView`(우리 뷰) 자신의 기본 드래그 처리는
        # dragEnter는 낙관적으로 받아주지만 dragMove는 "그 위치에 드롭을 받는 씬 아이템이
        # 없으면" 거부한다(우리 도형·화살표는 애초에 드롭 수용 아이템이 아님) — 그래서
        # 캔버스 중앙에서 실제로 마우스를 움직이면 항상 금지 커서가 뜨고 CanvasWindow.
        # dropEvent(아래)까지 이벤트가 아예 안 왔다(실측: `event.isAccepted()`가 dragEnter는
        # True, dragMove는 False로 갈림 — 커서는 dragMove 기준이라 이게 실제로 보인 증상).
        # 팔레트와 동일하게 여기서 파일 URL도 직접 가로채 처리해야 한다.
        if obj is self._view.viewport():
            et = event.type()
            if et == QEvent.Type.Resize:
                # [미니맵 실조건 버그] dock 스플리터 드래그로 메인 뷰포트 크기가 바뀌면
                # CanvasWindow.resizeEvent(창 자체 리사이즈)는 안 불려 미니맵 인디케이터가
                # 갱신 안 됐다(사용자 GUI 확인 — 창 크기는 그대로인데 dock 배치만 바뀐 경우).
                # 뷰포트 자체의 resize를 잡아야 원인 불문 항상 정확하다.
                self._refresh_minimap()
            if et in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                md = event.mimeData()
                if md.hasFormat(_PALETTE_MIME):
                    event.acceptProposedAction()
                    return True
                if md.hasUrls() and any(u.toLocalFile().lower().endswith(self._DROP_EXTS)
                                        for u in md.urls()):
                    event.acceptProposedAction()
                    return True
            elif et == QEvent.Type.Drop:
                md = event.mimeData()
                if md.hasFormat(_PALETTE_MIME):
                    # [2026-08-19] 이 네이티브 QDrag 경로는 이제 포트·커스텀심볼(`_palette_
                    # drag_begin`이 False를 돌려주는 tool_key)에서만 쓰인다 — 일반 도형·심볼은
                    # `_PaletteButton`이 씬 안 실물 임시 도형으로 직접 끌어(정렬 스냅이 드래그
                    # 도중에도 실시간으로 걸리도록, `_palette_drag_begin/_move/_end` 참조).
                    tool_key = bytes(md.data(_PALETTE_MIME)).decode("utf-8")
                    scene_pos = self._view.mapToScene(event.position().toPoint())
                    if self._create_shape_at(tool_key, scene_pos) is not None:
                        event.acceptProposedAction()
                    return True
                if md.hasUrls():
                    scene_pos = self._view.mapToScene(event.position().toPoint())
                    if self._handle_url_drop(md, scene_pos):
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
        # [드래그앤드롭 확장, 2026-08-23] 실사용에선 캔버스(뷰포트)가 이 이벤트를 가로채
        # 위 eventFilter의 Drop 분기가 처리하므로, 이 메서드는 뷰포트 밖(툴바 여백 등)에
        # 떨어졌을 때만 남는 폴백 경로 — 좌표만 창 기준으로 변환해 같은 본문을 재사용한다.
        view_pt = self._view.mapFrom(self, e.position().toPoint())
        scene_pos = self._view.mapToScene(view_pt)
        if self._handle_url_drop(md, scene_pos):
            e.acceptProposedAction()

    # ---- 표제란 / 용지틀 (Phase 4) ------------------------------------------

    def _insert_titleblock(self):
        """용지 크기·방향을 고르고 표제란 프레임을 삽입. 프레임은 뷰 중앙 근처에 좌상단 배치.
        [다중 페이지 지원, 2026-08-14] 예전엔 씬에 이미 하나 있으면 거부했으나(단일 프레임
        전제), 여러 용지틀을 두고 PDF 내보내기에서 고르는 워크플로를 지원하며 그 가드를
        제거했다(deep-interview 확정 — 메뉴로도 자유롭게 추가 삽입, Alt+드래그 복제와 동등)."""
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


    def _get_mermaid_dialog(self) -> "_MermaidDialog":
        """[실사용 피드백 2026-08-25] SVG와 같은 이유로 인스턴스 하나를 재사용 —
        `_get_svg_asset_dialog()` 참조. Mermaid는 진입점이 이거 하나뿐이라 공유 범위
        고민 없이 창당 싱글턴 1개면 된다."""
        dlg = getattr(self, "_mermaid_dialog", None)
        if dlg is None:
            dlg = _MermaidDialog(self)
            self._mermaid_dialog = dlg
        return dlg

    def _insert_mermaid(self):
        """Mermaid flowchart 코드를 붙여넣어 편집가능 도형+화살표로 자동배치(뷰 중앙 기준).
        노드는 _RectItem/_EllipseItem/_SymbolItem, 엣지는 _PolyArrowItem 직교 라우팅으로 연결."""
        dlg = self._get_mermaid_dialog()
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
