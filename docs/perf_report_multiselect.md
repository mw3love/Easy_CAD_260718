# 다중선택 성능 전수조사 최종 보고서 (2026-08-15)

> **목적**: Claude Code 세션에서 이 보고서를 읽고, 각 병목을 재검증한 뒤 우선순위대로 수정한다.
> **작성 맥락**: Antigravity에서 코드 전수조사(3개 병렬 서브에이전트) + cProfile 실측.
>
> **2026-08-15 이관·검증 메모(Claude Code)**: 원래 `perf_lab/` 하위에 있던 것을 `docs/`로
> 옮겼다(나머지 실험 산출물 3개는 폐기 — 아래 §6 참조). 병목 A~F의 *메커니즘*은 코드 확인·
> 실측으로 전부 재현됐으나, **우선순위는 규모에 따라 달라진다**: 병목 A(`_selection_is_solo`
> O(N²))는 200개에선 오차 범위(50.78→50.06ms)이고 500개에서야 값을 한다(142.88→119.88ms).
> 보고서가 A를 "가장 넓은 영향"으로 1순위에 둔 것은 큰 문서에서만 맞다. 병목 B/C는 두 규모
> 모두에서 확실히 이득이었다(200개 50.06→40.06ms, 500개 119.88→97.22ms).
> A는 커밋 `c87626f`, B/C는 `de71498`로 반영 완료. 후속 계획은
> `docs/perf_plan_500_1000.md`.

---

## 0. 사용자 보고 증상

"객체를 100개 이상 한번에 드래그해서 선택하면 엄청나게 부하가 발생해서
이동하기도 어렵고 프로그램도 느려지고 그럼."

버벅임 발생 시점 2가지:
1. **러버밴드 드래그 중** (마우스 드래그로 영역 선택하는 동안)
2. **선택 후 그룹 이동** (선택된 객체를 드래그해서 이동할 때)

---

## 1. 발견한 병목 — 심각도순 정리

### 병목 A: `_selection_is_solo()` → paint마다 O(N²)

**파일**: `core_shapes.py:1412-1419`
**호출 경로**: 선택된 각 아이템의 `paint()` → `_paint_selection_outline()` →
`_paint_selection_highlight()` → `_selection_is_solo(it)`

```python
def _selection_is_solo(it) -> bool:
    sc = it.scene()
    if sc is None:
        return True
    return len(sc.selectedItems()) <= 1   # ← 매번 C++에서 새 리스트 생성, O(N)
```

- `scene().selectedItems()`는 Qt C++에서 **매 호출마다 선택된 아이템 전체 리스트를
  새로 생성**해서 반환한다. 선택된 아이템이 N개면 이 호출 1회가 O(N).
- 이것이 **선택된 N개 각각의 `paint()` 안에서 호출**되므로, 프레임당 총 비용은 **O(N²)**.
- 100개 선택 시 프레임당 10,000번, 200개 선택 시 40,000번의 리스트 생성+순회.
- `len()`만 쓰는데 전체 리스트를 만드는 것이 낭비.

**개선안**: 씬 레벨에서 선택 개수를 캐시하거나(예: `selectionChanged` 시그널에서
`self._sel_count = len(self.selectedItems())`를 1회 갱신), `_selection_is_solo`가
그 캐시를 읽게 한다. paint() 안에서 selectedItems()를 호출하지 않는다.


### 병목 B: `_highlight_band()` 캐시 없이 매 paint()마다 재계산

**파일**: `core_shapes.py:1076-1077`, `core_shapes.py:1446-1464`, `core_shapes.py:1369-1409`
**호출 경로**: 선택된 각 아이템의 `paint()` → `_paint_selection_outline(painter, scale)` →
`_paint_selection_highlight(painter, self, scale)` → `_highlight_band(it)`

```python
# core_shapes.py:1076 — band 파라미터를 넘기지 않음
def _paint_selection_outline(self, painter, scale):
    _paint_selection_highlight(painter, self, scale)     # band=None → 매번 재계산

# core_shapes.py:1458 — band=None이면 매번 호출
if band is None:
    band = _highlight_band(it)                          # ← QPainterPath 불리언 연산

# core_shapes.py:1408 — 비싼 불리언 연산
band = stroker.createStroke(centerline).simplified()    # QPainterPath 다각형 단순화
return band.subtracted(centerline)                      # QPainterPath 차집합
```

- `simplified()`와 `subtracted()`는 **QPainterPath 불리언(교차/차집합) 연산**으로,
  내부적으로 2D 다각형 교차 계산을 수행한다. 단일 호출도 수 ms 수준.
- 다중선택 상태에서 paint()가 발화할 때마다(드래그 중 매 프레임) 선택된 아이템
  N개 각각에 대해 이 연산이 반복 → 프레임당 N회.
- **기존 캐시 시도 기록**: `docs/perf_group_drag_200.md` "후속 시도" 절 참조 —
  `QPainterPath` 인스턴스를 인스턴스 속성에 캐시했더니 전체 pytest에서 비결정적
  네이티브 크래시(exit 127) 발생, 되돌림. 근본 원인 미상.

**개선안 (기존 크래시를 피하는 방향)**:
- 방안 1: `_selection_is_solo` 수정(병목 A)이 먼저 적용되면, 다중선택 시에도
  `_highlight_band` 대신 `_paint_selection_centerline`(단순 drawPath 1회)으로
  통일하는 것이 가능 — Lucid 스타일 밴드 대신 얇은 외곽선으로 시각적 차이는 있으나
  성능은 O(1).
- 방안 2: QPainterPath 자체를 캐시하는 대신, 밴드의 "입력 파라미터"(content_rect,
  pen width, rotation)가 변하지 않았으면 이전 결과를 재사용하는 값비교 캐시 —
  단, 이전 크래시가 QPainterPath 장기 보관 자체의 문제였다면 같은 위험.
- 방안 3: 단순 도형(사각형, 원)은 `_highlight_band`의 불리언 연산 없이 `adjusted()`로
  바깥 사각/타원을 바로 그리는 경량 경로 신설.


### 병목 C: 러버밴드 드래그 중 drawForeground에서 `_highlight_band` 반복

**파일**: `core_view.py:1759-1760`
**호출 경로**: 러버밴드 드래그 중 매 마우스 무브 → `viewport().update()` →
`drawForeground()` 발화

```python
# core_view.py:1759-1760
for it in self._rb_preview:                              # 미리보기 후보 K개 순회
    painter.drawPath(it.mapToScene(_highlight_band(it)))  # ← 매 프레임, K개 각각
```

- 러버밴드를 끌면서 100개 객체 위를 지날 때, **매 마우스 무브 이벤트마다**
  100개 각각에 `_highlight_band()` 호출.
- 이 경로는 `paint()` 경로(병목 B)와 별개 — `drawForeground`는 뷰 레벨 렌더링이라
  아이템의 `paint()`와 독립적으로 발화함.
- 마우스가 1초에 60번 움직이면, 100개 × 60 = 6,000회의 불리언 연산.

**개선안**: `_rb_preview` 아이템에 대해 `_highlight_band` 대신 경량 하이라이트
(예: `_item_center_path`를 약간 두껍게 drawPath, 또는 단순 `sceneBoundingRect`를
살짝 부풀려 drawRect)를 사용. 미리보기는 정밀할 필요 없으므로 근사로 충분.


### 병목 D: 화살표 reroute 캐스케이드 (드래그 이동 시)

**파일**: `host_canvas.py:101-179`
**호출 경로**: 선택된 도형 이동 → `scene.changed` 시그널 → `_on_scene_changed()` →
`_sync_geom_snapshot()` (O(N) 씬 순회) → 화살표마다 `reroute()` 호출

프로파일 실측 (`heavy_perf_test.ecad`, 도형 800 + 화살표 799):

```
프레임당 비용 분해:
- Arrow boundingRect(4658):  75.1ms (32,688회/10프레임)
- _on_scene_changed:         69.7ms
- reroute:                   40.8ms (7,990회/10프레임 = 799/프레임)
- Shape boundingRect(477):   36.9ms
- Arrow _content_rect:       34.3ms
- _sync_geom_snapshot:       10.9ms (씬 전체 순회)
총: ~191ms/프레임 (x11.5 초과)
```

- 도형만 있으면(화살표 0) 200개에서 17ms — 거의 OK.
- **화살표가 추가되면 reroute 캐스케이드로 비용이 폭발**.
- `fast=True`(미관 폴리시 스킵)가 이미 적용돼 있지만, reroute **호출 횟수** 자체
  (프레임당 799)가 문제.

**개선안**: 드래그 중(mousePress~mouseRelease 사이) reroute를 완전히 스킵하고,
mouseRelease 시 1회만 전체 reroute. 드래그 중에는 바인딩된 화살표의 끝점만
도형 위치에 추종시키는 경량 업데이트로 대체. (이미 "선택된 화살표+도형이
같은 그룹으로 함께 이동"하는 경우는 평행이동 최적화가 있음 — 그 외 케이스가
reroute를 트리거함.)


### 병목 E: `_view_zoom_factor()` 대량 호출

**파일**: `core_constants.py:347-380`
**프로파일**: 10프레임에 58,223회 호출, 누적 0.250s

- `boundingRect()` 체인을 통해 간접 호출됨. Qt가 아이템마다 여러 번 재조회.
- 뷰 캐시가 이미 적용돼 있어(`_interactive_view_cache`) 1회 호출 비용은 낮지만,
  **호출 횟수 자체가 58K**라 누적됨.
- `transform().m11()` 호출은 매번 최신 줌값을 읽으므로 캐시 불가(staleness 위험).

**개선안**: `boundingRect()` 내에서 `_view_zoom_factor`를 1회만 호출하고 지역변수로
재사용(현재도 그렇게 하고 있을 수 있음 — 확인 필요). 또는 프레임 단위로 줌값을
캐시하는 방안(줌이 프레임 중간에 바뀌지 않으므로 안전).


### 병목 F: `_sync_geom_snapshot()` 씬 전체 순회

**파일**: `host_canvas.py:65-99`
**프로파일**: 프레임당 10.9ms (10프레임 합산 0.109s)

- 매 `scene.changed` 발화 시 **씬의 모든 아이템을 순회**(화살표 제외).
- 아이템마다 `_content_rect()` 호출 + 스냅샷 비교.
- 800개 도형이면 프레임당 800회 순회.

**개선안**: 전체 비용에서 6% 수준이라 우선순위는 낮음. 병목 A~D를 먼저 해결한 뒤
재측정해서 여전히 유의미하면 공간 쿼리 대체를 재검토.

---

## 2. 이미 잘 최적화된 부분 (건드릴 필요 없음)

| 항목 | 이유 |
|---|---|
| `_bulk_select()` | selectionChanged 시그널 disconnect/reconnect로 O(N²)→O(N) |
| `_rb_preview_hits()` | BSP 트리 공간 쿼리로 O(log N + K), setSelected 미호출 |
| `_apply_rubber_selection()` | Release 시 1회만 호출, _bulk_select 경유 |
| 도형 `boundingRect` 캐시 | 값비교 캐시 적용 완료 (2026-08-13) |
| 화살표 `boundingRect` 캐시 | `_geom_version` 기반 캐시 적용 완료 |
| 화살표 `_content_rect` 캐시 | `_geom_version` 기반 캐시 적용 완료 |
| reroute 평행이동 최적화 | 같은 선택 그룹이면 A* 생략, 위치만 이동 |

---

## 3. 이전 보고서(Gemini 분석 기반)와의 차이점

| 항목 | 이전 보고서 | 이번 전수조사 |
|---|---|---|
| `_highlight_band` | **핵심 원인으로 지목** | 병목 중 하나이나 최대 병목 아님. O(N²)인 `_selection_is_solo`가 더 큼 |
| `_selection_is_solo` | **미발견** | **새로 발견된 O(N²) 병목** — 매 paint()에서 selectedItems() 전체 리스트 생성 |
| 화살표 reroute | 핵심 원인으로 지목 | 동일 — 화살표 있는 파일에서 최대 병목 |
| 러버밴드 중 _highlight_band | **미분석** | 별도 경로(drawForeground)에서 K개×매프레임 호출 |
| 순수 도형 성능 | 미확인 | 200개까지 거의 OK (17ms/프레임) |

---

## 4. 추천 수정 우선순위

1. **병목 A** (`_selection_is_solo` O(N²) 제거) — 가장 넓은 영향, 구현 단순
2. **병목 C** (러버밴드 중 `_highlight_band` 경량화) — 선택 **중** 버벅임 직접 해결
3. **병목 B** (paint 내 `_highlight_band` 캐시 또는 경량화) — 선택 **후** 매 프레임 비용
4. **병목 D** (reroute 지연) — 화살표 있는 파일 전용, 가장 큰 절대 비용

---

## 5. 검증 방법

⚠ **이 절의 첫 스크립트는 폐기됐다(2026-08-15).** `perf_lab/test_selection_perf.py`는
`_RectItem`을 생성자로 직접 만들고 `_bulk_select()`를 불렀는데, `ItemIsSelectable` 플래그는
그 생성자가 아니라 캔버스 도구·파일로드 경로에서만 붙는다 — 실제로 `selectedItems()`가 0개라
**병목 A/B 경로가 한 번도 실행되지 않았다.** 대체 하네스는 `docs/perf_plan_500_1000.md`
1-0에서 신설한다(워밍업+best-of-5 내장).

```bash
# 화살표 포함 프로파일 — 병목 D 효과 확인
python tools/profile_group_drag.py --doc heavy_perf_test.ecad --frames 10 --no-minimap

# 벤치마크 (프레임당 ms)
python tools/perf_bench.py --doc heavy_perf_test.ecad --only drag_all --no-minimap

# 전체 테스트 스위트 (회귀 확인)
python -m pytest tests/ -x -q
```

수정 전 기준선:
- 순수 도형 200개: 17.26ms/프레임
- heavy_perf_test.ecad (800+799): 191ms/프레임

---

## 6. 참고 파일 목록

- `docs/perf_group_drag_200.md` — 기존 성능 조사 문서 (2026-08-13)
- ~~`perf_lab/test_selection_perf.py`~~ — 폐기(위 §5 참조: 선택이 실제로 안 걸리는 버그)
- ~~`perf_lab/canvas_sandbox/`·`perf_lab/svg_profile/`~~ — 폐기(브라우저 성능 샌드박스.
  얻은 결론은 `docs/perf_plan_500_1000.md` 2-D에 반영)
- `tools/profile_group_drag.py` — 기존 프로파일 스크립트
- `tools/perf_bench.py` — 기존 벤치마크 스크립트
- `heavy_perf_test.ecad` — 대규모 테스트 문서 (도형 800 + 화살표 799)
