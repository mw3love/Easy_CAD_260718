"""CanvasWindow 믹스인 — §8 항목18 C단계: AI 이미지→도면 앱 통합.

이 코드베이스 첫 `QThread` 사용(2026-08-11) — `easycad/ai/sketch_pipeline.build_from_image`
호출이 게이트웨이 왕복(밀집 도면 기준 실측 약 3~4분, `docs/ai_image_import.md`)이라
GUI 스레드에서 그대로 부르면 그동안 창이 멈춘다. 파이프라인은 파일만 만들고(`.ecad`
임시파일), 씬 조작(`QGraphicsScene.addItem` 등)은 전부 메인 스레드의 완료 콜백에서
한다 — Qt 규칙(그래픽스 씬은 소유 스레드에서만 건드릴 것)을 지키기 위해서다.

결과 삽입은 `document.insert_items()`(§8 항목18 C단계에서 신설 — `load_document`처럼
씬을 지우지 않고 기존 문서에 추가)로 현재 씬에 얹고, `push_undo_add_many`로 undo
1스텝 등록(Mermaid 가져오기 `host_fileio._insert_mermaid`와 동일 관례).

⚠ 스코프: 진행 취소·원본 이미지 반투명 언더레이 대조는 이번 라운드에 빠졌다(설계
문서 C단계 전체 스펙 중 "빠른 테스트"에 필요한 부분만 먼저 구현 — 사용자 확인 후 축소).
"""
import os
import tempfile

from PyQt6.QtCore import Qt, QPointF, QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QMessageBox

from easycad.canvas.annotator_core import _PolyArrowItem
from easycad.canvas.host_dialogs import _AIImageImportDialog, _AISketchProgressDialog
from easycad.fileio.document import load_document_items, insert_items


class _AISketchWorker(QThread):
    """`build_from_image`를 백그라운드 스레드에서 실행. 진행 로그(`progress`)와 완료
    (`finished_ok`/`finished_err`) 시그널만 GUI 스레드로 넘긴다 — 씬 조작은 안 함."""
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(dict)
    finished_err = pyqtSignal(str)

    def __init__(self, image_path: str, out_path: str, note: str, parent=None):
        super().__init__(parent)
        self._image_path = image_path
        self._out_path = out_path
        self._note = note

    def run(self):
        from easycad.ai.sketch_pipeline import build_from_image
        try:
            summary = build_from_image(
                self._image_path, self._out_path, note=self._note,
                verbose=False, on_progress=self.progress.emit,
            )
            self.finished_ok.emit(summary)
        except Exception as e:
            self.finished_err.emit(str(e))


class _AIImportMixin:
    """CanvasWindow에 섞이는 "AI 이미지→도면" 진입점(`_import_ai_image`)."""

    def _import_ai_image(self):
        dlg = _AIImageImportDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        image_path = dlg.image_path()
        note = dlg.note()
        if not image_path:
            return

        out_fd, out_path = tempfile.mkstemp(suffix=".ecad", prefix="ai_sketch_")
        os.close(out_fd)

        progress = _AISketchProgressDialog(self)
        worker = _AISketchWorker(image_path, out_path, note, self)
        # progress/worker를 self에 붙여 GC가 실행 도중 회수하지 않게 한다(Qt 부모 없는
        # QThread는 파이썬 참조가 사라지면 실행 중이라도 소멸자가 불릴 위험이 있다).
        self._ai_worker = worker

        def _cleanup_file():
            try:
                os.remove(out_path)
            except OSError:
                pass

        def _on_ok(summary):
            progress.accept()
            try:
                items = load_document_items(out_path)
                added = insert_items(self._scene, items)
            finally:
                _cleanup_file()
            if not added:
                QMessageBox.information(self, "AI 이미지→도면", "인식된 도형이 없습니다.")
                return
            self._offset_ai_items_to_view_center(added)
            self.push_undo_add_many(added)
            self._scene.clearSelection()
            for it in added:
                it.setSelected(True)
            self.statusBar().showMessage(
                f"AI 이미지→도면: 도형 {summary['shapes']} · 연결선 {summary['edges']} · "
                f"미확인 {summary['unknown']}건(타일 {summary['tiles']}개) — "
                "미확인 항목은 텍스트만 있는 상자로 표시됩니다", 10000)
            self._ai_worker = None

        def _on_err(msg):
            progress.reject()
            _cleanup_file()
            QMessageBox.warning(self, "AI 이미지→도면", f"실패: {msg}")
            self._ai_worker = None

        worker.progress.connect(progress.append)
        worker.finished_ok.connect(_on_ok)
        worker.finished_err.connect(_on_err)
        worker.start()
        progress.exec()

    def _offset_ai_items_to_view_center(self, items):
        """삽입된 항목들의 결합 bbox 중심을 현재 뷰 중심으로 옮긴다(Mermaid 가져오기
        `_build_mermaid`와 동일 관례) — AI 결과 좌표는 원본 이미지 픽셀 좌표라 현재
        캔버스 어디에 놓일지 보장이 없다. 화살표는 위치 이동 후 `build_elbow()`를
        명시 호출해 경로를 재계산(부착된 도형 위치가 바뀌었으므로) — Mermaid 가져오기가
        `itemChange` 자동 재라우팅에 기대지 않고 직접 부르는 것과 같은 이유."""
        if not items:
            return
        bbox = None
        for it in items:
            r = it.sceneBoundingRect()
            bbox = r if bbox is None else bbox.united(r)
        if bbox is None:
            return
        center = self._view.mapToScene(self._view.viewport().rect().center())
        delta = QPointF(center.x() - bbox.center().x(), center.y() - bbox.center().y())
        if delta.x() == 0 and delta.y() == 0:
            return
        for it in items:
            it.setPos(it.pos() + delta)
        for it in items:
            if isinstance(it, _PolyArrowItem):
                try:
                    it.build_elbow()
                except Exception:
                    pass
                it._sync_label()
