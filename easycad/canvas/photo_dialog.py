"""사진→도면(§8 항목28) — Qt 쪽: ops 렌더·백그라운드 워커(2단계). 입력은 「AI로 만들기」 패널의
「그대로 베끼기」(§8 항목36 — 옛 입력 창 `_PhotoToDrawingDialog`는 6단계에서 지움).

AI 호출 본체는 `easycad/ai/photo_to_ops.generate_ops_tiled`(Qt 비의존), ops→아이템 변환은
`easycad/fileio/photo_ops.ops_to_sketch`. 여기는 그 둘을 앱에 잇는다.
2026-08의 "관계만 남기고 재배치" 경로(`host_ai`·`sketch_pipeline`, 폐기·회귀 가드 있음)와는 별개다.
"""
import io

from PyQt6.QtCore import (
    QBuffer, QByteArray, QIODevice, QRectF, QThread, pyqtSignal,
)
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QGraphicsScene

from easycad.ai import gateway as gw
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
    """`render_spec_qimage`의 PIL 판 — `generate_ops(render=...)`(도구 `tools/sketch_ops_probe.py`)에 넘기는 모양."""
    return qimage_to_pil(render_spec_qimage(spec, size, scale=scale))


class _PhotoOpsWorker(QThread):
    """`generate_ops_tiled`(구역별 동시 생성, 2026-10-05)를 메인 스레드 밖에서 돈다. 2~3분 걸린다.

    2026-10-01판은 첫 생성 + 수정 2라운드(`generate_ops`)라 수정마다 직전 결과를 메인 스레드에서
    렌더해 넘겼는데, 벽 전체 도면에서 18분이 걸려 수정 라운드를 뺐다(렌더 장치도 함께 걷어 냄).

    취소는 호출 사이에서만 먹는다(진행 중인 HTTP 호출은 못 끊음). 창이 먼저 닫히면 호출부가
    `host_dialogs._detach_worker`로 떼어내 결과를 버린다."""

    progressed = pyqtSignal(int, int, str)     # (끝난 구역 수, 전체, 글)
    succeeded = pyqtSignal(dict, list)         # (최종 spec, 구역별 로그)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, api_key, base_url, photo, model, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url
        self._photo = photo
        self._model = model
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def run(self):
        from easycad.ai.photo_to_ops import Cancelled, generate_ops_tiled
        try:
            client = gw._client(self._api_key, self._base_url, timeout=600.0)
            spec, log = generate_ops_tiled(
                client, self._photo, model=self._model,
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


def _pil_to_pixmap(img) -> QPixmap:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    pm = QPixmap()
    pm.loadFromData(buf.getvalue())
    return pm
