# 다중선택 그룹드래그 200개+ 성능 조사·구현 (§8 항목0 후속)

> **2026-08-13 구현·검증 완료.** 아래 "제안하는 대안 메커니즘"을 그대로
> `_HandleResizeMixin.boundingRect()`(core_shapes.py:472)에 반영, 스모크 543종 전원
> 통과 + 실제 창에서 재실측까지 마쳤다. 결과·최종 수치는 문서 맨 끝 "구현 결과" 참조.
> 아래 본문(배경~검증 계획)은 계획 수립 당시 그대로 보존.

## 배경 · 목표

사용자 보고: 200개 이상 객체를 한 번에 이동시키면 심하게 버벅인다. 가장 최근 커밋
(`43b2a3c`, 2026-08-13 13:53 — 바인딩된 화살표 강체-평행이동 최적화)으로 나아졌다고는
하나, **화살표가 0개인 순수 도형 200개 문서에서도 여전히 60fps 예산의 7.3배**를 초과한다
(아래 실측). 즉 오늘 커밋이 푼 것과는 다른 병목이 남아 있다.

목표(잠정 — 실측 후 조정): `drag_all`(전체 선택 그룹 드래그) 시나리오가 200개에서
60fps 예산(16.67ms/frame) 근접까지 개선.

## 재현 고정

- **실제 재현 문서**: `C:\Users\aros\Desktop\200.ecad` — 사용자가 직접 만듦(사각형 1개를
  Ctrl+D로 배수 복제 후 저장). 사각형 200개, 화살표 0개, 씬 전체=선택 전체(변수 분리를
  위해 의도적으로 단순화된 형태 — 아래 "범위 밖" 참조).
- **신규 벤치마크**: `tools/perf_bench.py`에 `drag_all` 시나리오 추가(기존 `drag_multi`는
  20개 고정이라 200+ 규모를 못 잡음, 회귀 게이트 안정성을 위해 그대로 두고 새로 추가).
  ```
  python tools/perf_bench.py --doc "C:\Users\aros\Desktop\200.ecad" --only drag,drag_multi,drag_all --no-minimap
  ```
- **신규 프로파일러**: `tools/profile_group_drag.py`(cProfile, `profile_reroute.py`와 같은
  관례). `--no-minimap`으로 미니맵 리페인트 기여도 분리 가능.
  ```
  python tools/profile_group_drag.py --doc "C:\Users\aros\Desktop\200.ecad" --frames 10 --no-minimap
  ```

## 실측 결과 (2026-08-13, 실제 창 — 오프스크린 아님)

| 시나리오 | ms/frame | 60fps 배수 |
|---|---|---|
| 도형 1개 드래그 | 5.45 | OK |
| 20개 그룹 드래그 | 18.61 | x1.1 초과 |
| **200개(전체) 그룹 드래그** | **121.81** | **x7.3 초과** |

20→200(10배)에 시간은 약 6.5배로 늘어 대략 선택 개수에 비례 — "씬 전체를 매번 훑는"
이차적 폭증이 아니라 "선택된 도형 1개당 고정 비용이 과함"에 가깝다(정확한 구분은
아래 "범위 밖" 참조).

## 프로파일 분석 — 병목은 A* 라우팅이 아니라 도형 자신의 `boundingRect()`

화살표가 0개인데도 7.3배 초과라는 것 자체가, 오늘 커밋이 최적화한 "바인딩된 화살표
재라우팅" 경로와 이번 병목이 **무관**함을 말해준다. cProfile 실측(미니맵 격리, 10프레임,
`4934697 function calls in 3.546 seconds`):

```
누적시간(cumtime)     함수
3.063s (86%)          boundingRect()                core_shapes.py:472
2.336s                 └ _qc_dot_rects()              core_shapes.py:630
1.901s                    └ _shape_ports()             core_shapes.py:5956
1.675s (55536회)             └ _nearest_border()         core_shapes.py:5164
0.706s (55536회)                └ _axis_forced_local_normal()  core_shapes.py:5109
```

프레임당 boundingRect() 호출 ≈ 1388회(도형 200개 대비 ~7회/개) — 코드 472행 자체 주석이
"Qt가 인덱싱·히트테스트·페인트 판정마다 매우 자주 호출한다"고 명시하는 그대로다. 선택된
도형은(501행 `if not self.isSelected()` 분기로) 매 호출마다 `_qc_dot_rects()`를 처음부터
다시 계산한다 — 캐시가 전혀 없다.

**핵심 관찰(캐싱이 안전한 이유)**: `_shape_ports(item)`(5956행)은 `item.rect()`(로컬
좌표)만 입력받고, `_qc_dot_rects()`는 그 결과를 `mapToScene`(함수 내부)→`mapFromScene`
(632행)으로 왕복해 다시 로컬 좌표로 되돌린다. **순수 위치이동(그룹 드래그 = `setPos`만
바뀜, 크기·회전 불변)에서는 이 체인의 결과가 프레임마다 수학적으로 완전히 동일**한데,
그 사실을 이용하지 않고 매번 `_nearest_border`(경계투영)·`_axis_forced_local_normal`
(법선보정) 기하 계산을 처음부터 다시 돈다.

## ⚠ 이미 실패한 접근 — 재시도 금지

같은 날(2026-08-13) 이 세션 이전에 이미 정확히 이 지점을 건드린 시도가 있었다(커밋
`43b2a3c` 트레일러, `docs/pitfalls.md` "Qt 시그널·이벤트 발화 조건" 51~62행):

- **시도한 것**: `_PolyArrowItem`이 쓰던 `_geom_version`+`prepareGeometryChange()`
  버전키 캐시를 `_HandleResizeMixin.boundingRect()`(도형 공용, 바로 이 함수)에도 확장.
- **실패 원인**: `prepareGeometryChange()`는 Qt C++에서 **non-virtual**이다.
  `QGraphicsRectItem.setRect()`/`QGraphicsTextItem.setFont()` 같은 **Qt 네이티브
  메서드가 내부적으로 부르는 prepareGeometryChange는 이 Python 오버라이드를 안 탄다**
  — 버전 번호가 안 올라가 캐시가 조용히 stale해진다.
- **어떻게 걸렸나**: `test_sketch_build_roundtrip`(라벨 `_fit_label_to_shape`의
  `setFont()` 폰트 축소) 실행 후에도 옛 boundingRect가 캐시에 남아 라벨이 중앙에서
  11~32유닛 어긋남 — 회귀 테스트가 바로 잡아냄.
- **교훈**: `_HandleResizeMixin`은 `_TextItem.setFont()` 같은 native 경로가 있어
  `_PolyArrowItem`(기하 변경이 전부 이 코드베이스 자체 파이썬 메서드를 거침)과 전제가
  다르다 — **이벤트/시그널 기반 무효화는 이 클래스에 구조적으로 안 맞는다.** 다음
  시도는 이 실패를 피할 수 있는 다른 메커니즘이어야 한다(아래).

## 제안하는 대안 메커니즘 — 값 비교 캐시(이벤트 무효화가 필요 없음)

- **핵심 아이디어**: `boundingRect()`가 이미 매 호출 초반에 계산하는
  `content_rect()`·`scale`(`s = self._scale_or_1(vz)`)·`handle_px()`(둘 다 저비용,
  기하 검색 없음)를 그대로 캐시 키로 쓴다. 이 값들이 직전 호출과 같으면
  `_qc_dot_rects()`/`_box_corner_rects()` 결과를 재사용하고, 다르면(리사이즈·회전·줌
  변경 등) 그때만 재계산한다.
- **왜 이전 실패를 피하는가**: `prepareGeometryChange()`가 호출되어야 무효화되는
  구조가 아니다 — 매 `boundingRect()` 호출마다 "이미 계산해야만 하는 저비용 값"을
  직접 비교하므로, native `setFont()`/`setRect()` 경로가 캐시를 우회할 여지 자체가
  없다(비교 자체가 그 호출들이 만든 새 `content_rect()`/`scale`을 보고 이뤄짐).
- **트레이드오프**: `content_rect()`/`scale`/`handle_px` 세 값은 캐시 히트 시에도
  매번 다시 계산해야 하니 "완전 스킵"은 아니다 — 다만 프로파일상 비싼 부분
  (`_shape_ports`→`_nearest_border`→`_axis_forced_local_normal` 체인, 전체의 86%
  중 대부분)만 스킵해도 이득이 크다.
- **검증해야 할 것(구현 전 스파이크로 먼저 확인 권장)**:
  - 리사이즈 드래그 중(매 프레임 `content_rect()` 변함) 무회귀
  - 회전 드래그 중 무회귀
  - 라벨 폰트 변경(`_fit_label_to_shape`의 `setFont()`) 후 무회귀 —
    **이전 시도가 정확히 여기서 걸렸다**, `test_sketch_build_roundtrip` 재확인 필수

## 이번 조사에서 분리해 둔 것 (범위 밖)

- **`_sync_geom_snapshot()`(host_canvas.py:65)의 씬 전체 순회** — 이번 재현 문서는
  씬 전체(200)=선택 전체(200)라 "선택 개수 비례"와 "씬 전체 개수 비례"를 구분할 수
  없다. 씬은 크고(예: 1000+) 선택은 작은(200) 별도 합성 문서로 재실측해야 이게 독립
  병목인지 확정된다 — boundingRect 캐시 적용 후 재실측해 여전히 예산 초과면 다음
  후보로.
- **미니맵 `_rebuild_pixmap`** — 격리 실측(`--no-minimap`)에서 이번 병목과 무관함을
  확인(이미 2026-08-08 3단계에서 150ms 디바운스 처리됨).
- **LOD(레벨오브디테일)** — 기존에 "별도 deep-interview 필요"로 보류된 큰 설계 항목,
  이번 스코프 밖(`docs/EasyCAD_계획.md` §8 "큰 설계 필요" 참조).

## 검증 계획

1. `tools/perf_bench.py --doc 200.ecad --only drag,drag_multi,drag_all --no-minimap`
   수정 전/후 대조 — `drag_all`이 60fps 예산에 근접하는지.
2. `tools/profile_group_drag.py`로 boundingRect 누적시간 비중이 실제로 줄었는지
   함수별 재확인.
3. 리사이즈/회전/라벨폰트변경 회귀 테스트(`test_sketch_build_roundtrip` 포함) 통과 —
   이전 시도가 걸렸던 바로 그 케이스.
4. 전체 스모크 재통과.
5. 실제 창(오프스크린 아님)에서 사용자의 `200.ecad`로 체감 확인, 가능하면 실사용
   문서(화살표 포함)로도 확인.

## 다음 세션 시작점

- 이 문서 + `tools/perf_bench.py --only drag_all` + `tools/profile_group_drag.py` 그대로
  재사용(둘 다 이번에 신설, 회귀 없이 그대로 커밋됨).
- 착수 전 "제안하는 대안 메커니즘"의 검증해야 할 항목(리사이즈/회전/setFont)부터
  구현 없이 손으로 먼저 확인 — 이 영역은 오늘 이미 한 번 되돌림이 있었던 자리다
  (전역 규칙 11-b: 같은 함수에 세 번째 패치를 그냥 얹지 않는다).

## 구현 결과 (2026-08-13, 같은 날 후속)

위 "제안하는 대안 메커니즘"(값 비교 캐시)을 `_HandleResizeMixin.boundingRect()`
(core_shapes.py:472)에 그대로 반영. 인스턴스 속성 `_bbox_cache_key`/`_bbox_cache_rect`
(클래스 기본값 `None` — 콜드스타트 안전) + `key = (cr.x(), cr.y(), cr.width(),
cr.height(), s, h)` 비교 후 미스일 때만 `_qc_dot_rects()`/`_box_corner_rects()` 재계산.
`prepareGeometryChange()`/시그널을 전혀 안 쓰므로 이전 시도가 걸렸던 "네이티브 호출이
무효화 훅을 안 탄다" 함정이 구조적으로 발생할 수 없다(매 호출 `cr`을 직접 다시 읽어
비교하기 때문).

**검증**:
- `test_sketch_build_roundtrip`(이전 시도가 걸렸던 바로 그 테스트) 개별 통과.
- 전체 스모크 **543종 전원 통과**(리사이즈·회전 관련 회귀 테스트 포함, 신규 테스트
  추가 없이 기존 커버리지로 충분히 검증됨 — 별도 함정 발견 없음).
- `perf_bench.py --doc 200.ecad --only drag,drag_multi,drag_all --no-minimap`(실제 창):

  | 시나리오 | 수정 전 | 수정 후 | 배수 |
  |---|---|---|---|
  | 도형 1개 드래그 | 5.45ms | 4.90ms | — |
  | 20개 그룹 드래그 | 18.61ms (x1.1 초과) | **9.97ms (OK)** | 1.9배 |
  | 전체 200개 그룹 드래그 | 121.81ms (x7.3 초과) | **34.84ms (x2.1 초과)** | **3.5배** |

- `profile_group_drag.py`(cProfile, 10프레임, 미니맵 격리): boundingRect 누적시간
  3.063s→0.092s(33배), 프로파일 총 시간 3.546s→0.436s(8배) — 남은 비용은 이제
  `_qc_dot_rects` 체인이 아니라 실제 `paint()`/`drawPath()`(정당한 렌더링 비용)가
  대부분을 차지.

**남은 것**: `drag_all`(200개)은 여전히 60fps 예산 x2.1 초과 — 위 "이번 조사에서
분리해 둔 것"의 `_sync_geom_snapshot()` 씬 전체 순회 후보(씬≠선택 규모의 별도 문서로
재실측 필요)와 이제는 `paint()` 자체 비용이 다음 라운드 후보. LOD는 여전히 스코프 밖.
