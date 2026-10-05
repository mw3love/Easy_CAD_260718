"""사진→도면(§8 항목28) — Qt 쪽: ops 렌더·백그라운드 워커(2단계), 입력 창(3단계).

AI 루프 본체는 `easycad/ai/photo_to_ops.generate_ops`(Qt 비의존), ops→아이템 변환은
`easycad/fileio/photo_ops.ops_to_sketch`. 여기는 그 둘을 앱에 잇는다.
2026-08의 "관계만 남기고 재배치" 경로(`host_ai`·`sketch_pipeline`, 폐기·회귀 가드 있음)와는 별개다.
"""
import io

from PyQt6.QtCore import (
    QBuffer, QByteArray, QIODevice, QPointF, QRectF, QSize, QThread, Qt, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QGraphicsScene, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QVBoxLayout,
)

from easycad.ai import gateway as gw
from easycad.canvas.host_dialogs import _GenProgressRow, _ImageAttachMixin, _detach_worker
from easycad.canvas.host_widgets import _ACCENT_CORAL
from easycad.fileio.document import insert_items
from easycad.fileio.photo_ops import SCALE, ops_to_sketch


def render_spec_qimage(spec: dict, size: tuple[int, int], *, scale: float = SCALE) -> QImage:
    """ops 명세를 원본 사진 프레임(0,0)~size로 흰 배경에 그린다 — 원본과 1:1 대조용.
    앱 창 없이 임시 씬에 넣어 그린다. **메인(GUI) 스레드에서만 부를 것**(Qt 글자 아이템)."""
    s, _ = ops_to_sketch(spec, dark=False, scale=scale)
    scene = QGraphicsScene()
    insert_items(scene, s._items)
    img = QImage(size[0], size[1], QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    scene.render(p, QRectF(0, 0, size[0], size[1]), QRectF(0, 0, size[0] * scale, size[1] * scale))
    p.end()
    scene.clear()
    return img


def qimage_to_pil(img: QImage):
    from PIL import Image
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(ba.data()))).convert("RGB")


def render_spec_pil(spec: dict, size: tuple[int, int], *, scale: float = SCALE):
    """`render_spec_qimage`의 PIL 판 — `generate_ops(render=...)`에 넘기는 모양."""
    return qimage_to_pil(render_spec_qimage(spec, size, scale=scale))


class _PhotoOpsWorker(QThread):
    """`generate_ops`(첫 생성 + 수정 라운드)를 메인 스레드 밖에서 돈다. 1회 수 분이 걸린다.

    수정 라운드에 필요한 "직전 결과 렌더"는 Qt 글자 아이템을 쓰므로 메인 스레드에서 그린다 —
    워커가 `_render_req`를 BlockingQueuedConnection으로 쏘면 메인 스레드의 `_do_render`가 그려
    `_rendered`에 담고, 워커는 그동안 기다린다.

    취소는 호출 사이에서만 먹는다(진행 중인 HTTP 호출은 못 끊음). 창이 먼저 닫히면 호출부가
    `host_dialogs._detach_worker`로 떼어내 결과를 버린다."""

    progressed = pyqtSignal(int, int, str)     # (라운드 i, 전체, 글)
    succeeded = pyqtSignal(dict, list)         # (최종 spec, 라운드 로그)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    _render_req = pyqtSignal(dict, int, int)

    def __init__(self, api_key, base_url, photo, model, rounds=2, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url
        self._photo = photo
        self._model = model
        self._rounds = rounds
        self._cancel = False
        self._rendered = None
        # 수신 객체(self)는 메인 스레드 소속이라 슬롯이 메인 스레드에서 돈다.
        self._render_req.connect(self._do_render, Qt.ConnectionType.BlockingQueuedConnection)

    def request_cancel(self):
        self._cancel = True

    @pyqtSlot(dict, int, int)
    def _do_render(self, spec, w, h):
        self._rendered = render_spec_pil(spec, (w, h))

    def _render(self, spec, size):
        self._rendered = None
        self._render_req.emit(spec, size[0], size[1])
        return self._rendered

    def run(self):
        from easycad.ai.photo_to_ops import Cancelled, generate_ops
        try:
            client = gw._client(self._api_key, self._base_url, timeout=600.0)
            spec, log = generate_ops(
                client, self._photo, model=self._model, render=self._render, rounds=self._rounds,
                progress=lambda i, n, t: self.progressed.emit(i, n, t),
                cancelled=lambda: self._cancel)
        except Cancelled:
            self.cancelled.emit()
            return
        except Exception as e:  # noqa: BLE001 — 실패 사유를 그대로 창에 전달
            self.failed.emit(str(e))
            return
        self.succeeded.emit(spec, log)


# ---- 입력 창(3단계) ------------------------------------------------------------
# UI 원칙(CLAUDE.md "AI 보조 생성 UI"): 모델은 추천 2개만. 결과 포맷(ops JSON)은 사람이 직접 쓰기
# 어려워 글 칸 대신 원본|결과 나란히 미리보기를 "결과 칸"으로 둔다(수동 모드 UI 없음).

PHOTO_MODELS = (("gpt-6.1-sol", "gpt-6.1-sol (추천1 — 가성비)"),
                ("gpt-6-astra", "gpt-6-astra (추천2 — 약 5배 비쌈)"))
PHOTO_ROUNDS = 2   # 첫 생성 뒤 수정 라운드 — 2026-10-01 실측 조건(조각 3×2 + 수정 2회)


def _pil_to_pixmap(img) -> QPixmap:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    pm = QPixmap()
    pm.loadFromData(buf.getvalue())
    return pm


class _CornerPreview(QLabel):
    """원본 미리보기 + 모서리 점 4개(원근 보정, 2026-10-01). 점을 끌어 도면 종이의 네 귀퉁이에 맞추면
    AI에 보내기 전에 그 사각형을 반듯하게 편다(`photo_to_ops.rectify`). 처음 위치는 사진 네 귀퉁이 —
    건드리지 않으면 보정 없음. 좌표는 원본 사진 픽셀로 보관한다."""

    quad_changed = pyqtSignal()
    _HIT = 18   # 점 잡기 거리(px, 맨해튼)

    def __init__(self, size: QSize, parent=None):
        super().__init__(parent)
        self.setFixedSize(size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#ffffff; color:#999999; border:1px solid rgba(128,128,128,90);")
        self.setText("원본")
        self._img_size = None
        self._pm = None
        self._quad = []
        self._drag = None

    def set_image(self, pil_img):
        self._drag = None
        if pil_img is None:
            self._img_size, self._pm, self._quad = None, None, []
            self.setText("원본")
        else:
            self._img_size = pil_img.size
            self._pm = _pil_to_pixmap(pil_img).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation)
            self.setText("")
            self.reset_quad(emit=False)
        self.update()

    def reset_quad(self, emit=True):
        if self._img_size is None:
            return
        w, h = self._img_size
        self._quad = [(0.0, 0.0), (float(w), 0.0), (float(w), float(h)), (0.0, float(h))]
        self.update()
        if emit:
            self.quad_changed.emit()

    def quad(self):
        return list(self._quad)

    def set_quad(self, quad):
        self._quad = [(float(x), float(y)) for x, y in quad]
        self.update()
        self.quad_changed.emit()

    # 원본 픽셀 <-> 위젯 좌표
    def _frame(self):
        pw, ph = self._pm.width(), self._pm.height()
        return (self.width() - pw) / 2.0, (self.height() - ph) / 2.0, pw / self._img_size[0]

    def _to_widget(self, x, y):
        ox, oy, k = self._frame()
        return QPointF(ox + x * k, oy + y * k)

    def _to_image(self, pt):
        ox, oy, k = self._frame()
        w, h = self._img_size
        return (min(max((pt.x() - ox) / k, 0.0), float(w)), min(max((pt.y() - oy) / k, 0.0), float(h)))

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._pm is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ox, oy, _ = self._frame()
        p.drawPixmap(int(round(ox)), int(round(oy)), self._pm)
        pts = [self._to_widget(x, y) for x, y in self._quad]
        p.setPen(QPen(QColor(_ACCENT_CORAL), 1.5))
        p.drawPolygon(QPolygonF(pts))
        p.setBrush(QColor(_ACCENT_CORAL))
        for q in pts:
            p.drawEllipse(q, 5.0, 5.0)
        p.end()

    def mousePressEvent(self, e):
        if self._pm is None or not self.isEnabled():
            return
        pos = e.position()
        best = min(range(4), key=lambda i: (self._to_widget(*self._quad[i]) - pos).manhattanLength())
        if (self._to_widget(*self._quad[best]) - pos).manhattanLength() <= self._HIT:
            self._drag = best

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self._quad[self._drag] = self._to_image(e.position())
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.quad_changed.emit()


class _PhotoToDrawingDialog(_ImageAttachMixin, QDialog):
    """사진 첨부 → AI(첫 생성 + 수정 2회) → 원본|결과 미리보기 → 캔버스에 넣기."""

    _PREVIEW = QSize(380, 285)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("사진→도면")
        self.setAcceptDrops(True)
        self._init_image_attach_state()
        self._worker = None
        self._spec = None
        self._sent_photo = None   # 마지막으로 AI에 보낸(원근 보정된) 사진 — 결과·밑깔기의 기준
        lay = QVBoxLayout(self)

        # 사진 카드: 첨부 버튼 + 칩 + 안내
        card = QFrame(self)
        card.setObjectName("photoCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        normal = "QFrame#photoCard { border:1px solid rgba(128,128,128,90); border-radius:8px; }"
        active = f"QFrame#photoCard {{ border:2px dashed {_ACCENT_CORAL}; border-radius:8px; }}"
        card.setStyleSheet(normal)
        self._set_image_drop_frame(card, normal, active)
        cl = QHBoxLayout(card)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.addWidget(self._build_attach_button(card))
        cl.addWidget(self._build_image_chip(card))
        self._hint = QLabel("도면 사진을 첨부하세요 — 끌어다 놓기 · Ctrl+V 붙여넣기", card)
        self._hint.setStyleSheet("color:#8a8a8a;")
        cl.addWidget(self._hint, 1)
        lay.addWidget(card)

        # 모델 + 만들기/취소
        row = QHBoxLayout()
        row.addWidget(QLabel("모델", self))
        self._model = QComboBox(self)
        for mid, label in PHOTO_MODELS:
            self._model.addItem(label, mid)
        row.addWidget(self._model, 1)
        self._go = QPushButton("도면 만들기", self)
        self._go.clicked.connect(self._on_go)
        row.addWidget(self._go)
        self._cancel = QPushButton("취소", self)
        self._cancel.setVisible(False)
        self._cancel.clicked.connect(self._on_cancel)
        row.addWidget(self._cancel)
        lay.addLayout(row)
        note = QLabel(f"한 번에 첫 생성 + 수정 {PHOTO_ROUNDS}회(약 5~7분). 그동안 창을 옮기거나 닫을 수 있어요.", self)
        note.setStyleSheet("color:#8a8a8a; font-size:11px;")
        lay.addWidget(note)
        self._progress = _GenProgressRow(self)
        lay.addWidget(self._progress)

        # 원본 | 결과 미리보기
        prev = QHBoxLayout()
        self._orig_view = _CornerPreview(self._PREVIEW, self)
        self._orig_view.quad_changed.connect(self._on_quad_changed)
        self._result_view = self._preview_label("결과")
        self._reset_corners = QPushButton("모서리 초기화", self)
        self._reset_corners.setFlat(True)
        self._reset_corners.setStyleSheet("color:#8a8a8a; font-size:11px; padding:0 4px;")
        self._reset_corners.clicked.connect(self._orig_view.reset_quad)
        for title, v in (("원본 — 비스듬히 찍었으면 주황 점을 종이 네 귀퉁이로", self._orig_view),
                         ("결과", self._result_view)):
            col = QVBoxLayout()
            t = QLabel(title, self)
            t.setStyleSheet("color:#8a8a8a; font-size:11px;")
            col.addWidget(t)
            col.addWidget(v)
            if v is self._orig_view:
                # 제목 줄에 두면 옆 칸 「결과」 제목과 붙어 한 덩어리로 읽혀 미리보기 아래로.
                col.addWidget(self._reset_corners, 0, Qt.AlignmentFlag.AlignRight)
            else:
                col.addStretch(1)
            prev.addLayout(col)
        lay.addLayout(prev)

        # 넣기 옵션 + 버튼
        self._underlay = QCheckBox("원본 사진을 밑에 깔기(흐리게·잠금 — 대조하며 고친 뒤 지우면 됨)", self)
        self._underlay.setChecked(True)
        lay.addWidget(self._underlay)
        btns = QHBoxLayout()
        btns.addStretch(1)
        self._insert = QPushButton("캔버스에 넣기", self)
        self._insert.setEnabled(False)
        self._insert.setDefault(True)
        self._insert.clicked.connect(self.accept)
        close = QPushButton("닫기", self)
        close.clicked.connect(self.reject)
        btns.addWidget(self._insert)
        btns.addWidget(close)
        lay.addLayout(btns)

    def _preview_label(self, text):
        v = QLabel(text, self)
        v.setFixedSize(self._PREVIEW)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setStyleSheet("background:#ffffff; color:#999999; border:1px solid rgba(128,128,128,90);")
        return v

    def _show(self, label, pm):
        label.setPixmap(pm.scaled(self._PREVIEW, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation))

    # ---- 첨부 칩 연동: 사진이 바뀌면 원본 미리보기 갱신·이전 결과 폐기 ----
    def _set_attached_image(self, pil_img, name: str):
        super()._set_attached_image(pil_img, name)
        self._hint.setVisible(False)
        self._orig_view.set_image(pil_img)
        self._sent_photo = None
        self._set_result(None)

    def _clear_image(self):
        super()._clear_image()
        self._hint.setVisible(True)
        self._orig_view.set_image(None)
        self._sent_photo = None
        self._set_result(None)

    def _on_quad_changed(self):
        # 모서리를 바꾸면 보낼 사진이 달라지므로 이전 결과는 버린다.
        self._sent_photo = None
        self._set_result(None)

    def _ai_photo(self):
        """결과·밑깔기의 기준 사진 — AI에 보낸 보정본, 없으면 첨부 원본."""
        return self._sent_photo if self._sent_photo is not None else self._attached_image

    def keyPressEvent(self, e):
        if self._maybe_intercept_paste_image(e):
            return
        super().keyPressEvent(e)

    def _set_result(self, spec):
        self._spec = spec
        self._insert.setEnabled(spec is not None)
        if spec is None:
            self._result_view.clear()
            self._result_view.setText("결과")
        else:
            w, h = self._ai_photo().size
            self._show(self._result_view, QPixmap.fromImage(render_spec_qimage(spec, (w, h))))

    # ---- 생성 ----
    def _on_go(self):
        if self._attached_image is None:
            QMessageBox.information(self, "사진→도면", "먼저 도면 사진을 첨부하세요.")
            return
        key = gw.resolve_api_key()
        if not key:
            QMessageBox.warning(self, "사진→도면", "게이트웨이 API 키가 없습니다. "
                                "삽입 메뉴의 「AI 게이트웨이 설정…」에서 입력해 주세요.")
            return
        from easycad.ai.photo_to_ops import fit_for_ai, rectify
        try:
            sent = fit_for_ai(rectify(self._attached_image, self._orig_view.quad()))
        except ValueError as e:
            QMessageBox.warning(self, "사진→도면", f"모서리로 사진을 펼 수 없습니다: {e}")
            return
        self._set_result(None)
        self._sent_photo = sent
        self._set_running(True)
        self._worker = _PhotoOpsWorker(key, gw.resolve_base_url(), sent,
                                       self.model(), PHOTO_ROUNDS, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, i, n, text):
        self._progress.start(f"{text} ({i + 1}/{n})")

    def _on_succeeded(self, spec, _log):
        self._set_result(spec)

    def _on_failed(self, err):
        QMessageBox.warning(self, "사진→도면", f"생성 실패: {err}")

    def _on_cancel(self):
        if self._worker is not None:
            self._worker.request_cancel()
            self._progress.start("취소하는 중 — 지금 호출이 끝나면 멈춰요")
            self._cancel.setEnabled(False)

    def _on_finished(self):
        self._worker = None
        self._set_running(False)

    def _set_running(self, on: bool):
        self._go.setVisible(not on)
        self._cancel.setVisible(on)
        self._cancel.setEnabled(on)
        self._model.setEnabled(not on)
        self._orig_view.setEnabled(not on)        # 진행 중엔 모서리 고정(보낸 사진과 어긋나지 않게)
        self._reset_corners.setEnabled(not on)
        if not on:
            self._progress.stop()

    def done(self, r):
        # `_MermaidDialog.done`과 같은 이유 — 닫기는 항상 즉시 허용하고 도는 워커는 분리한다.
        # 분리 전에 취소를 걸어 다음 호출(크레딧)을 막는다.
        if self._worker is not None:
            try:
                self._worker.request_cancel()
            except RuntimeError:
                pass
        _detach_worker(self._worker)
        self._worker = None
        super().done(r)

    # ---- 호출부(host_fileio)용 ----
    def model(self) -> str:
        return self._model.currentData()

    def result_spec(self):
        return self._spec

    def photo(self):
        return self._ai_photo()

    def underlay(self) -> bool:
        return self._underlay.isChecked()
