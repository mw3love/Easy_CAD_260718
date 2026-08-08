"""[성능 최적화 2026-08-08, 0단계 안전망] 성능 수정이 **그림을 바꾸지 않았음**을 기계로 증명한다.

`tools/perf_bench.py`가 "빨라졌나"를 재는 짝이라면, 이 스크립트는 "결과가 그대로인가"를 잰다.
성능 최적화는 캐싱·건너뛰기가 본질이라 **조용히 틀린 그림을 그리는 것**이 최대 위험이고, 이
레포는 라우팅(A*/직교 엘보)에서 스턱루프가 반복된 이력이 있어(`docs/pitfalls.md`) 눈으로
훑는 확인은 신뢰할 수 없다. 그래서 두 축을 각각 기계로 고정한다:

  1. 기하 지문 — 모든 아이템의 위치·경계, 특히 **화살표 라우팅 결과 정점 좌표 전부**.
     A* 회피 결과가 1픽셀이라도 달라지면 여기서 잡힌다.
  2. 시각 지문 — 대표 3개 뷰 상태(전체축소 / 100% / 밀집 클러스터 확대)의 렌더 PNG를
     픽셀 단위 비교. 캐시 무효화 누락으로 생기는 잔상·미갱신이 여기서 잡힌다.

사용법:
    python tools/perf_baseline_check.py save     # 수정 '전'에 기준 지문 저장
    python tools/perf_baseline_check.py check    # 수정 '후' 대조 (차이 있으면 exit 1)
    python tools/perf_baseline_check.py check --doc other.ecad

기준 지문은 `tools/_perf_ref/`에 저장된다(빌드 산출물이라 커밋 대상 아님).
차이가 나면 같은 폴더에 `diff_*.png`(달라진 픽셀만 빨강)를 남겨 눈으로도 확인할 수 있게 한다.
"""
import argparse
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import _ArrowItem, _PolyArrowItem
from easycad.fileio.document import load_document

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(ROOT, "tools", "_perf_ref")
DEFAULT_DOC = os.path.join(ROOT, "heavy_perf_test.ecad")
VIEW_W, VIEW_H = 1400, 900
ROUND = 4      # 부동소수 잡음 흡수용 자릿수. A*는 결정론적이라 실제로는 완전일치해야 정상.


def _r(v: float) -> float:
    return round(float(v), ROUND)


def _rect_sig(r: QRectF):
    return [_r(r.x()), _r(r.y()), _r(r.width()), _r(r.height())]


def _item_sig(it) -> dict:
    """아이템 하나의 기하 지문. 화살표는 라우팅 결과(_pts)를 통째로 싣는다 — 이게 핵심."""
    sig = {
        "type": type(it).__name__,
        "pos": [_r(it.pos().x()), _r(it.pos().y())],
        "sbr": _rect_sig(it.sceneBoundingRect()),
    }
    cr = getattr(it, "_content_rect", None)
    if callable(cr):
        sig["cr"] = _rect_sig(cr())
    if isinstance(it, (_ArrowItem, _PolyArrowItem)):
        pts = getattr(it, "_pts", None)
        if pts is not None:
            # 라우팅 정점 전부 — 성능 수정이 경로를 바꿨는지 판정하는 유일한 근거.
            sig["pts"] = [[_r(p.x()), _r(p.y())] for p in pts]
        sig["bound"] = bool(it.has_binding())
    return sig


def geometry_fingerprint(scene) -> list:
    """씬 전체의 기하 지문. 순서는 Qt의 스태킹 순서를 그대로 쓴다 — 같은 파일을 같은 순서로
    로드하면 결정론적이라 before/after가 일대일 대응된다(개수가 다르면 그 자체로 회귀)."""
    return [_item_sig(it) for it in scene.items(Qt.SortOrder.AscendingOrder)]


# 렌더 지문을 뜰 뷰 상태 3종 — 이름, 설정 함수.
# 서로 다른 줌 배율을 섞는 이유: `_view_zoom_factor`가 boundingRect에 들어가 있어 줌마다
# 다른 코드 경로를 타므로, 한 배율만 보면 캐시 무효화 버그를 놓친다.
def _view_states(win):
    scene_rect = win._scene.itemsBoundingRect()

    def fit_all():
        win._view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def actual_size():
        win._view.resetTransform()
        win._view.centerOn(scene_rect.center())

    def dense_zoom():
        # 밀집 클러스터 확대 — 씬 좌상단 1/6 영역(도형·화살표가 겹쳐 라우팅이 복잡한 구간).
        w, h = scene_rect.width() / 6.0, scene_rect.height() / 6.0
        win._view.fitInView(QRectF(scene_rect.x(), scene_rect.y(), w, h),
                            Qt.AspectRatioMode.KeepAspectRatio)

    return [("fit_all", fit_all), ("actual", actual_size), ("dense", dense_zoom)]


def render_view(win, app) -> QImage:
    img = QImage(VIEW_W, VIEW_H, QImage.Format.Format_ARGB32)
    img.fill(0)
    app.processEvents()
    p = QPainter(img)
    win._view.render(p)
    p.end()
    return img


def compare_images(a: QImage, b: QImage, diff_path: str):
    """픽셀 비교. 반환: (다른 픽셀 수, 최대 채널 차이, 차이 bbox). 다르면 diff PNG를 남긴다."""
    if a.size() != b.size():
        return (-1, -1, None)
    # 빠른 경로: 원시 버퍼가 같으면 픽셀 루프(126만회 x 3뷰)를 통째로 건너뛴다.
    # 대다수 실행은 '동일'이 정답이라 이 경로만 타고 끝난다.
    # ⚠ 변환 결과를 반드시 지역변수에 붙들어 둘 것 — `a.convertToFormat(...).bits()`처럼
    #   임시 QImage에서 바로 포인터를 꺼내면 그 임시가 즉시 회수돼 dangling 포인터가 되고
    #   해석 시 액세스 위반(0xC0000005)으로 프로세스가 죽는다(2026-08-08 실제로 겪음).
    ca = a.convertToFormat(QImage.Format.Format_ARGB32)
    cb = b.convertToFormat(QImage.Format.Format_ARGB32)
    if bytes(ca.constBits().asstring(ca.sizeInBytes())) == \
            bytes(cb.constBits().asstring(cb.sizeInBytes())):
        return (0, 0, None)
    diff = QImage(a.size(), QImage.Format.Format_ARGB32)
    diff.fill(QColor(0, 0, 0).rgb())
    n = 0
    max_ch = 0
    minx = miny = 10 ** 9
    maxx = maxy = -1
    for y in range(a.height()):
        for x in range(a.width()):
            pa, pb = a.pixel(x, y), b.pixel(x, y)
            if pa != pb:
                n += 1
                d = max(abs(((pa >> s) & 0xFF) - ((pb >> s) & 0xFF)) for s in (0, 8, 16, 24))
                max_ch = max(max_ch, d)
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
                diff.setPixel(x, y, QColor(255, 0, 0).rgb())
    if n:
        diff.save(diff_path)
        return (n, max_ch, (minx, miny, maxx, maxy))
    return (0, 0, None)


def build(doc_path: str):
    app = QApplication.instance() or QApplication(sys.argv)
    win = CanvasWindow()
    win.resize(VIEW_W, VIEW_H)
    win.show()
    app.processEvents()
    load_document(win._scene, doc_path)
    app.processEvents()
    app.processEvents()          # 로드 직후 지연 reroute까지 정착시킨 뒤에 지문을 뜬다
    win._scene.clearSelection()  # 선택 강조가 지문에 섞이지 않게
    app.processEvents()
    return app, win


def cmd_save(args):
    os.makedirs(REF_DIR, exist_ok=True)
    app, win = build(args.doc)
    geo = geometry_fingerprint(win._scene)
    with open(os.path.join(REF_DIR, "geometry.json"), "w", encoding="utf-8") as f:
        json.dump({"doc": os.path.basename(args.doc), "items": geo}, f, ensure_ascii=False)
    print(f"기하 지문 저장: 아이템 {len(geo)}개")
    for name, setup in _view_states(win):
        setup()
        img = render_view(win, app)
        img.save(os.path.join(REF_DIR, f"ref_{name}.png"))
        print(f"시각 지문 저장: ref_{name}.png")
    print(f"\n기준 지문을 {REF_DIR} 에 저장했습니다. 수정 후 `check`로 대조하세요.")


def cmd_check(args):
    geo_path = os.path.join(REF_DIR, "geometry.json")
    if not os.path.exists(geo_path):
        raise SystemExit("기준 지문이 없습니다 — 먼저 `python tools/perf_baseline_check.py save`")
    with open(geo_path, encoding="utf-8") as f:
        ref = json.load(f)

    app, win = build(args.doc)
    cur = geometry_fingerprint(win._scene)
    ref_items = ref["items"]

    failures = []

    # ---- 1) 기하 대조 ----
    if len(cur) != len(ref_items):
        failures.append(f"아이템 개수 불일치: 기준 {len(ref_items)} → 현재 {len(cur)}")
    else:
        diffs = []
        for i, (a, b) in enumerate(zip(ref_items, cur)):
            if a != b:
                keys = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
                diffs.append((i, b.get("type"), keys))
        if diffs:
            route_diffs = [d for d in diffs if "pts" in d[2]]
            failures.append(f"기하 불일치 {len(diffs)}건 (그중 라우팅 경로 변경 {len(route_diffs)}건)")
            for i, tp, keys in diffs[:10]:
                print(f"   [{i}] {tp}: {', '.join(sorted(keys))}")
            if len(diffs) > 10:
                print(f"   ... 외 {len(diffs) - 10}건")
        else:
            print(f"기하 지문 일치 (아이템 {len(cur)}개, 화살표 경로 좌표 포함)")

    # ---- 2) 시각 대조 ----
    for name, setup in _view_states(win):
        ref_png = os.path.join(REF_DIR, f"ref_{name}.png")
        if not os.path.exists(ref_png):
            failures.append(f"기준 이미지 없음: ref_{name}.png")
            continue
        setup()
        img = render_view(win, app)
        before = QImage(ref_png)
        n, max_ch, bbox = compare_images(before, img, os.path.join(REF_DIR, f"diff_{name}.png"))
        total = VIEW_W * VIEW_H
        if n < 0:
            failures.append(f"[{name}] 이미지 크기 불일치")
        elif n:
            img.save(os.path.join(REF_DIR, f"cur_{name}.png"))
            failures.append(f"[{name}] 픽셀 {n}개 ({n / total * 100:.4f}%) 다름, "
                            f"최대 채널차 {max_ch}, 영역 {bbox} → diff_{name}.png")
        else:
            print(f"시각 지문 일치: {name}")

    # [2026-08-08] 미니맵(`win._minimap.grab()`)도 지문에 넣어봤으나, 같은 문서·같은 코드로
    # 저장→대조해도 같은 프로세스 안에서 두 번 grab하면 항상 0diff인데, `save`/`check`를
    # 별도 프로세스로 실행하면 매번 정확히 같은 크기(64.02%, 채널차 193)로 어긋났다 — 원인은
    # 못 찾음(itemsBoundingRect가 `_view_zoom_factor`에 의존하는 자기참조적 계산이라 부동소수
    # 반올림이 프로세스마다 미세하게 갈릴 가능성 의심, 미확정). 신뢰 못 할 게이트를 넣느니
    # 없는 게 낫다고 판단해 자동 지문에선 뺐다 — 미니맵 시각 회귀는 `python tools/screenshot.py`
    # 또는 실제 창에서 직접 확인할 것(이번 레터박스 버그도 실제 창 재현으로 잡고 고쳤다).

    print()
    if failures:
        print("회귀 감지 — 성능 수정이 결과를 바꿨습니다:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("기하·시각 지문 모두 일치 — 성능 수정이 결과를 바꾸지 않았습니다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["save", "check"])
    ap.add_argument("--doc", default=DEFAULT_DOC)
    args = ap.parse_args()
    if not os.path.exists(args.doc):
        raise SystemExit(f"문서를 찾을 수 없습니다: {args.doc}")
    (cmd_save if args.mode == "save" else cmd_check)(args)


if __name__ == "__main__":
    main()
