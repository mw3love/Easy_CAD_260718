"""사진→도면(§8 항목28) — Qt 쪽: ops 렌더·백그라운드 워커(2단계), 입력 창(3단계).

AI 루프 본체는 `easycad/ai/photo_to_ops.generate_ops`(Qt 비의존), ops→아이템 변환은
`easycad/fileio/photo_ops.ops_to_sketch`. 여기는 그 둘을 앱에 잇는다.
2026-08의 "관계만 남기고 재배치" 경로(`host_ai`·`sketch_pipeline`, 폐기·회귀 가드 있음)와는 별개다.
"""
import io

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsScene

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
        from easycad.ai import gateway as gw
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
