# Easy CAD — 최종 검수 계획서

> 목표: **프로그램 완성도 및 안정성 향상**(오류 찾기·코드 최적화·릴리스 준비).
> 작성일 2026-08-25. 이 문서는 살아있는 계획서 — 각 Phase를 닫을 때마다 결과를 여기 기록한다.
> **세션이 끊겨도 이어갈 수 있게** Phase 단위로 독립 실행 가능하도록 나눴다.

---

## 0. 이 계획의 근거 (2026-08-25 실측)

계획을 세우기 전에 리포 상태를 실제로 측정했다. 아래는 전부 이 날짜 실측값이다.

| 항목 | 실측 |
|---|---|
| `easycad/` 코드 | 27,874줄 / 33파일 |
| 최대 2파일 | `core_shapes.py` 8,288줄 · `core_view.py` 4,520줄 (전체의 46%) |
| `tests/` | 20,905줄 / 15파일 / **1,001개 수집** |
| 커밋 | 461개 (2026-07-18 ~ 2026-08-25) |
| `TODO`/`FIXME`/`HACK` | **0건** (코드 규율 좋음 — 일반 리뷰 수확은 낮을 것) |
| bare `except:` | 0건 |
| `except Exception` | 47건 (그중 **조용히 삼키는 `pass` 12건**) |
| 커밋 본문 `Not-tested:` 줄 | **342건** |
| git 태그 | **없음** (`__version__ = "0.1.0"`인데 기준점 태그 부재) |
| PyInstaller 스펙 | **없음** (원 계획서 Phase 0 항목인데 미실행) |

### ⚠ 최중요 발견 — 회귀 안전망이 지금 작동하지 않는다

```
python -m pytest tests/          → EXIT 127, 1001개 중 ~215개(21%)만 실행하고 네이티브 크래시
python tests/test_easycad.py     → EXIT 127, 출력 한 줄도 없이 죽음  (CLAUDE.md가 추천하는 명령)
python -m pytest tests/test_part1_ui_arrows.py → "101 passed" 출력 후 종료 시점에 EXIT 127
```

- **100% 재현**(3회 연속 동일). 플레이크가 아니다.
- `faulthandler`를 켜도 트레이스백이 안 나온다 — `docs/perf_group_drag_200.md`에 기록된
  "비결정적 네이티브 크래시(exit 127)"와 같은 서명.
- **파일별로 하나씩 돌리면 전부 통과한다**(아래 표). 즉 축적/상호작용 효과다.
- 범인은 **`tests/test_part1_ui_arrows.py`** 하나로 특정됐다 — *필요충분*이 실측으로 확인됨:
  - 단독 실행 → 101개 전부 통과 후 **종료 시점** 크래시(exit 127)
  - 뒤에 다른 파일이 대기 중이면 → part1 **실행 도중 ~96번째**에서 크래시
  - **part1만 제외하면 나머지 900개가 완주한다** — `3 failed, 897 passed in 47.61s`,
    exit 1(정상적인 테스트 실패 코드지 크래시가 아님)
  - `part13_group + part13_mindmap`만 따로 → 정상(exit 0)

### ✓ 그래서 지금 당장 쓸 수 있는 임시 안전망이 있다

```
python -m pytest tests/ --ignore=tests/test_part1_ui_arrows.py
   → 900개 실행 · 897 passed · 3 failed(아래 AI 게이트웨이 건) · 크래시 없음
```

**이게 계획의 교착을 막는다.** 이 프로젝트는 과거에 같은 서명의 네이티브 크래시를 근본원인
미상으로 포기하고 되돌린 이력이 있다(`docs/perf_group_drag_200.md` "⚠ 후속 시도"). 그러니
Phase 1이 오래 걸릴 가능성을 계획에 미리 반영한다 — **Phase 2 이후는 이 900개 안전망 위에서
진행할 수 있으므로 Phase 1에 발이 묶이지 않는다.**

| 테스트 파일 | 단독 실행 결과 |
|---|---|
| test_part1_ui_arrows | 101 passed → **종료 시 crash** |
| test_part2_labels_routing | 84 passed |
| test_part3_transform_snap | 107 passed |
| test_part4_ports_fileio | 111 passed |
| test_part5_precision_edit | 87 passed |
| test_part6_grid_minimap_layers | 78 passed |
| test_part7_symbol_library | 65 passed |
| test_part8_trim_kernel | 69 passed |
| test_part9_ai_mermaid | **3 failed**, 78 passed |
| test_part9_ai_svg_asset | 84 passed |
| test_part10_multi_doc | 25 passed |
| test_part11_polygon | 18 passed |
| test_part12_shortcuts | 20 passed |
| test_part13_group_frame | 19 passed |
| test_part13_mindmap | 52 passed |

**왜 이게 계획의 1순위인가** — 코드리뷰가 만들어 낼 모든 수정은 "회귀가 없다"를 이 스위트로
증명해야 한다. 기본 명령이 21%만 돌면 **나머지 79%는 수정해도 검증이 안 된다.** 이 프로젝트는
2026-08-15 성능 작업에서 이미 같은 교훈을 얻었다 — 「측정 기반 고정이 선행 필수였고, 실제로
하네스 자체에서 결함 5종이 나와 그 전 절대 ms는 전부 무효가 됐다」. 이번엔 성능이 아니라
**정확성**에 대해 같은 일이 벌어져 있다. 다만 위 임시 안전망 덕에 "1순위"이지 "차단 조건"은
아니다 — part1이 덮던 101개(도구·화살표 UI)만 검증 사각지대로 남는다.

⚠ 부수 함의: 최근 히스토리의 "전체 pytest N종 통과" 기록들은 **재확인이 필요하다**(당시엔
통과했더라도 지금 이 상태에선 같은 방식으로 재현되지 않는다).

### 기타 사전 정리 대상

- **문서 미반영 커밋 6건** — `39e1b84`·`cf60f9d`·`54f41dd`·`b70d805`·`8e40a54`·`4fc30df`가
  `docs/history/2026-08.md` 마지막 항목("그룹 프레임 4차") 이후에 있는데 기록이 없다.
- ~~**`symbol_library/symbol_library.json` uncommitted 변경**~~ — **정체 확인 완료(Phase 0)**:
  구조적 diff 결과 폴더 "gg" 신설 + 심볼 2→9개(7개 추가) = **진짜 사용자 데이터**, 오염 아님.
  그대로 커밋. memory의 known issue(`bug_symbol_library_test_leak.md`, "pytest 실행 후 변조")는
  **별개 버그로 여전히 미해결** — Phase 1에서 pytest 실행 전후 diff로 별도 재현·규명한다.
- **`test_part9_ai_mermaid` 3건 실패** — 전부 `_AIGatewaySettingsDialog` 관련
  (`prefills_default_url` / `test_requires_key` / `accept_persists_url_and_key`).
  CLAUDE.md는 "로컬 secrets발 무관 실패"로 기록해 왔으나, 최종 검수에서는 **면제 대상이 아니라
  닫아야 할 항목**이다(테스트가 로컬 환경에 의존하면 다른 PC에서 결과가 달라진다).
- **진단용 임시 로그가 프로덕션 코드에 상주** — `core_view.py._dbg`(`easycad_debug.log`)와
  `core_shapes.py._dbg2`, 호출 16곳. CLAUDE.md에 "사용자 요청으로 유지 중, 삭제는 승인 후"로
  기록돼 있다. 릴리스 관점에선 실행할 때마다 파일을 쓰므로 정리 여부 결정 필요.

---

## 1. 도구 결정 — `code-review` 스킬 vs 자체 진행

**결론: 하이브리드.** 기계적 정확성·중복 탐지는 스킬에, 이 프로젝트 고유의 재발 함정은 자체 감사에.

`code-review`는 Claude Code **내장** 스킬이다(`~/.claude/skills/`에 없음 — 파일로 찾으면 안 나온다).
superpowers 플러그인의 `requesting-code-review`와는 별개이며, superpowers는 2026-08-25에
비활성화됐다(memory `feedback_no_superpowers`).

| | `code-review` 스킬 | 자체 진행 |
|---|---|---|
| 강점 | 정확성 버그·중복/단순화·효율에 특화. **`path` 타겟 지원** → PR 없이 모듈 단위 실행 가능. effort 조절(low~max) | `docs/pitfalls.md` 12계열 재발 패턴·히스토리 맥락을 아는 유일한 경로 |
| 약점 | 이 프로젝트의 재발 함정을 모른다(일반 리뷰어라 pitfalls.md를 안 읽음) | 정확성 버그 탐지를 사람 눈으로 재발명 — 느리고 누락 위험 |
| 배치 | **Phase 2~4**(모듈별 1차 스캔) | **Phase 5~6**(함정 재발 감사 + Not-tested 트리아지) |

**`path` 타겟이 핵심이다** — 이 리포는 PR 없이 master에 직접 커밋하는 워크플로라 "현재 diff"가
비어 있다. `/code-review high <파일경로>` 형태로 모듈을 지정해야 동작한다.

**`--fix`는 쓰지 않는다** — 리뷰 결과를 먼저 읽고 채택 여부를 판단한 뒤, 회귀 테스트를 동반해
수동 반영한다. 이 프로젝트의 surgical-change 규율(전역 규칙 8)과 자동 일괄수정은 충돌한다.

**`ultra`(멀티에이전트 클라우드)** — Phase 7에서 **선택적으로만** 고려한다. ⓐ 사용자가 직접
트리거해야 하고 과금되며 Claude가 대신 실행할 수 없다. ⓑ 브랜치 diff 기준이 기본이라 이
워크플로와 잘 안 맞는다. Phase 2~6을 다 닫은 뒤에도 불안이 남으면 그때 판단.

---

## 2. 왜 "코드리뷰"가 아니라 "최종 검수"인가 (프레임 조정)

사용자의 목표는 "완성도·안정성"이고 코드리뷰는 그 **수단**이다. 그런데 이 프로젝트의 실제
버그 이력을 보면 정적 리뷰의 기대 수확이 생각보다 낮다:

- `docs/pitfalls.md` 항목 대부분이 "**실사용에서 발견**", "사용자가 스크린샷으로 제보",
  "실사용 재현으로"로 시작한다. 오프스크린 테스트는 통과하는데 실제 창에서만 깨진 사례가 반복됐다.
- `TODO`/`FIXME` 0건, bare except 0건 — 정적 스캐너가 주울 저수확 과일이 이미 없다.

따라서 이 계획은 **코드리뷰(Phase 2~4)를 한 갈래로 포함하되**, 이 프로젝트에서 역사적으로
수확이 높았던 두 갈래 — **함정 재발 감사(Phase 5)** 와 **실사용 검증 백로그 정리(Phase 6)** —
를 동급으로 둔다. 그리고 그 모든 것의 전제인 **검증 기반 복구(Phase 1)** 를 맨 앞에 놓는다.

**스코프 밖**: `web_prototype/`(2026-08-06 중단, 재개 미정) · 신규 기능 개발 · 성능 목표 재도전
(`docs/perf_plan_500_1000.md`는 미달로 닫힌 상태이며 남은 축은 LOD 설계로 별도 건).

---

## 3. Phase 목록

각 Phase는 **독립 세션으로 실행 가능**하다. 앞 Phase의 산출물만 있으면 뒤 Phase를 시작할 수 있다.
단 **Phase 1은 Phase 2~7 전체의 전제**다(회귀 검증 수단이 없으면 나머지가 무의미).

---

### Phase 0 — 사전 정리 (작업공간·문서 위생) — **완료 (2026-08-25)**

**왜 먼저**: 리뷰 중 나올 변경을 깨끗한 기준선 위에 올리기 위해. 짧다.

- [x] 미반영 커밋 6건을 `docs/history/2026-08.md` + `CLAUDE.md` 요약에 기록 (`doc-sync` 절차 수동 적용)
- [x] `symbol_library.json` uncommitted 변경의 정체 확인 — **진짜 사용자 데이터**로 확인됨
      (폴더 "gg" 신설 + 심볼 2→9개, 구조적 diff로 검증). 오염 아님, 그대로 커밋 대상.
      known issue(`bug_symbol_library_test_leak.md`, "pytest 실행 후 변조")는 **별개로 여전히
      미해결** — Phase 1로 이관.
- [x] `이미지 모음/`(untracked, JPEG 7장, 23MB) — 기존 `.gitignore`의 "작업 도면·입력 사진"
      패턴(`/송출 도면/`·`/실제 도면/`)과 동일 성격이라 같은 방식으로 `/이미지 모음/` 추가.
- [x] **기준점 태그** `v0.1.0` 생성(로컬, 커밋 `d382fb1`) — annotated tag, 아직 push 안 함
- [x] `tools/` 산출물 점검 — 대부분(`_perf_*.json`·`_shot_*.png`)은 이미 `.gitignore` 대상이라
      깨끗함. 단 **`tools/_kbs_hit_crop.png`·`tools/_route_bug.png` 2개는 tracked인데 ignore
      패턴에 안 걸림**(과거 버그 재현용 스크린샷, 지금은 스코프 밖) — 삭제하지 않고 보고만
      (전역 규칙 8: dead code는 보고, 삭제는 승인 후). Phase 7 정리 대상 후보로 남김.

**완료 기준**: `git status`가 깨끗하고, 마지막 커밋까지 문서에 반영돼 있으며, 태그가 있다.
**완료** — 커밋 `d382fb1`, 태그 `v0.1.0`(로컬).

---

### Phase 1 — 검증 기반 복구 ⭐ — **완료 (2026-08-25)**

**결과: 근본원인 규명 성공, 타임박스 안에 완전 종결.** exit 127 크래시는 미상으로 남기지
않고 특정·수정했다.

- [x] **exit 127 네이티브 크래시 진단·수정** — 이등분 탐색으로 `test_part1_ui_arrows.py`의
      단일 테스트(`test_left_panel_scrolls_instead_of_growing_unbounded_with_many_folders`)로
      확정. **원인은 앞서 세운 3개 가설(창 미종료·QApplication 파괴 순서·QThread) 전부 아니었다** —
      실제로는 ⓐ 이 테스트가 40회 반복으로 UI 위젯을 실제로 짓고 부수며(등록+폴더생성+이동,
      매회 `_refresh_custom_symbol_section()`가 좌측 패널 전체 재구축, 최대 120회) ⓑ
      `.show()`된 실제 창 위에서 ⓒ `host_ui.py`(당일 앞선 커밋 `39e1b84`가 추가한 코드)가
      `QApplication.processEvents()`를 동기 재진입시켜, clear-loop가 예약한 `deleteLater()`가
      같은 재진입 안에서 처리되며 힙 손상 abort를 유발한 것(`os.abort()`가 이 환경에서
      정확히 exit 127을 냄을 별도 확인해 서명 일치를 검증). 수정 2건:
      1. **프로덕션**(`easycad/canvas/host_ui.py`) — 문제의 `processEvents()` 동기호출을
         `QTimer.singleShot(0, self._relayout_left_panel)`로 교체(재진입 없이 다음 이벤트루프
         틱으로 지연). 진짜 `QApplication.exec()` 이벤트루프(오프스크린 아님, 실제 앱과
         동일 조건)로 별도 재현해본 결과 **원래 코드도 실사용자에게는 크래시가 없었다**
         (pytest의 합성 `processEvents()` 호출 특유의 문제) — 그래도 안전한 패턴으로
         교체해 향후 유사 재진입 위험을 원천 차단.
      2. **테스트**(`tests/test_part1_ui_arrows.py`) — 40회 실제 UI 액션 대신 라이브러리
         데이터를 직접 채우고 위젯 재구축은 1회만 실행하도록 재설계(같은 최종 상태를
         검증하되 위젯 처치량을 대폭 축소, "많은 폴더 → 스크롤"이라는 원래 검증 목적은 유지).
      3자 검증: 원인 파일 단독 3회 연속 재현 성공 → 수정 후 3회 연속 무크래시, 전체 파일
      101종 3회 연속 통과, 전체 스위트(1001종) exit 0, 자체러너(`test_easycad.py`, 865종)
      정상 종료 — 전부 확인 완료.
- [x] **`test_part9_ai_mermaid` 3건 실패 해소** — `gw.resolve_api_key()`가 QSettings보다
      **먼저** `gw.SECRETS_FILE`(`~/.claude/.secrets/easycad-gateway.key`)을 확인하는데,
      기존 `conftest.py`/`_shared.py` 격리는 QSettings 조직명만 바꿔치기하고 이 파일 경로는
      그대로 둬 실제 키가 있는 이 PC에서만 3건이 실패했다(다른 PC에서 "무관한 실패"로
      반복 관찰된 것의 실제 원인). `conftest.py`의 autouse fixture + `_shared.py` 양쪽에
      `SECRETS_FILE`을 존재하지 않는 임시 경로로 재바인딩(2026-08-20 "게이트웨이 키 소실
      재발 — 두 번째 진입점"과 같은 패턴: 격리 진입점이 여러 개면 하나씩 빠짐). 수정 후
      81/81 통과.
- [x] **`symbol_library.json` 테스트 오염 재조사** — 정식 스위트(`pytest tests/`·
      `test_easycad.py`) 각 2회 연속 실행 후 `git diff`가 매번 공백 — **오염 없음, 정식
      스위트는 무죄로 재확인**. 실제 오염은 이번 진단 과정에서 만든 임시 스크립트(격리
      컨텍스트 없이 `register_selection_as_symbol()` 직접 호출)가 만든 것으로 재현·확정.
      memory(`bug_symbol_library_test_leak.md`) 갱신 완료 — "정식 스위트 무죄, 위험은
      애드혹 진단 스크립트"로 결론 정정.
- [ ] CLAUDE.md의 테스트 명령 안내 갱신 — **보류, 불필요로 재확인**: 이미 exit 0으로
      정상 작동하므로 기존 안내(`python tests/test_easycad.py`)를 고칠 이유가 없어졌다.
- [x] **성능 베이스라인 재측정** — `tools/perf_bench.py --save
      tools/_perf_baseline_phase1_2026-08-25.json`(`.gitignore` 대상, 로컬 전용) 1회 실행,
      `heavy_perf_test.ecad`(1599아이템) 기준. ⚠ **관찰(조사 안 함, Phase 7로 이관)**:
      `전체 선택 그룹 드래그` 448.24ms가 `docs/perf_plan_500_1000.md`가 기록한 1000개
      문서 최종치(123.8ms)보다 크게 나쁘다 — 단 서로 다른 문서(1599 vs 1000아이템)라
      직접 비교는 아니고, 회귀인지 문서 규모 차이인지는 미판정. Phase 7에서 같은 문서로
      재측정해 판정할 것.

**완료 기준(실조건) 충족**: `python -m pytest tests/` exit 0(1,001종), `python
tests/test_easycad.py` 정상 종료(865종). 3회 이상 반복 재현으로 안정성 확인.

---

### Phase 2 — 코어 기하·이벤트 2대 파일 코드리뷰 — **완료 (2026-08-25)**

**대상**: `easycad/canvas/core_shapes.py`(8,288줄) · `easycad/canvas/core_view.py`(4,520줄)
— 전체 코드의 46%이자 버그 이력이 가장 짙은 영역.

⚠ **계획 대비 실제 진행 방식 변경**: 원안은 "findings를 분류표로만 정리하고 Phase 7에서
일괄 반영"이었으나, 두 파일 모두 findings가 소규모·저위험·즉시 검증 가능해 **발견
즉시 반영**했다. review finding이 이 정도 규모(수정 몇 줄, 회귀 테스트로 즉시 검증
가능)면 즉시 반영, 설계 변경급이거나 넓은 파급 범위면 Phase 7로 미루는 원칙으로
Phase 2 전체를 마쳤다.

- [x] `code-review high easycad/canvas/core_shapes.py` — **완료**. 2건 발견, 둘 다
      즉시 반영(커밋 `bb248b4`):
      1. `_GroupTransform.whole_group_id()`가 호출될 때마다 `_group_members()`(scene
         전체 선형스캔)를 재실행 — `_qc_dot_at` 호버 히트테스트 1회에 2번 중복 스캔되던
         것을 `qc_dot_rects(gid=...)` 옵션 인자로 재사용하게 수정.
      2. `_GroupTransform._HANDLE_PX`와 `_HandleResizeMixin._HANDLE_PX`가 값만 우연히
         같은 별개 상수(10.0) — 전자가 후자를 직접 참조하도록 통일.
      신규 pytest 1종.
- [x] `code-review high easycad/canvas/core_view.py` — **완료**(백그라운드 fork,
      약 12분 소요, 4건 발견 — 이 중 3건 즉시 반영, 1건 보류):
      1. **[채택]** `_qc_route_context(src, target)`가 `it is src/target`으로 라우팅
         장애물을 제외하는데, 그룹 큐닷 연결에서 `src`/`target`이 `_GroupBindProxy`면
         실제 그룹 멤버는 그 프록시와 절대 `is` 매칭이 안 돼 그룹 자신의 조각이 자기
         화살표의 장애물로 잘못 포함되던 버그(우회 경로 렌더). proxy의 `group_id`로
         멤버도 같이 제외하도록 수정.
      2. **[채택]** `_align_candidates`의 `_bound_to_excluded`가 `e in o.bound_shapes()`
         (e=드래그 중인 실제 도형)로 자기-정렬 오탐을 막는데, 그룹에 바인딩된 화살표의
         `bound_shapes()`는 `_GroupBindProxy`를 돌려줘 그룹 드래그 시 이 제외가 항상
         무효였다(2026-08-19에 개별 도형용으로 고쳤던 것과 같은 버그의 그룹 버전) —
         `excl` 멤버들의 `_group_id`로도 매칭하도록 확장.
      3. **[채택]** `_group_bbox_scene(_group_members(...))`(scene 전체 선형스캔)가
         `_qc_snap_target`·`_border_snap_at`·`_port_dot_target`·`_hover_port_at` 4개
         호출부에서 같은 마우스무브 프레임 안에 그룹당 각자 재계산되고 있었음 —
         `_GroupTransform._cache_key()`와 동일한 `(sel_version, geom_version)` 무효화
         시맨틱을 쓰는 뷰 레벨 캐시(`_group_bbox_cached()`)를 신설해 3개 호출부에 적용.
      4. **[보류]** `_group_proxy_cache`가 생성된 group_id마다 항목을 영구 보유(프루닝
         없음) — 리뷰어도 "low impact"로 평가했고, 섣불리 프루닝하면 "같은 group_id는
         항상 같은 인스턴스" identity 계약(`_GroupBindProxy` 클래스 docstring이 명시한
         설계 전제)이 깨질 위험이 커서 유보. 정상 사용 범위(장시간 세션이라도 그룹
         수백 개)에서 메모리 영향은 무시할 수준.
      신규 pytest 3종(라우팅 장애물 제외·정렬 후보 제외·캐시 히트 각각 직접 검증).
- [x] findings 분류 완료: **채택 5건**(core_shapes 2 + core_view 3, 전부 즉시 반영) /
      **보류 1건**(core_view finding 4, 근거 위 기록) / **기각 0건**.

⚠ 파일이 커서 한 번에 안 들어갈 걸 대비해 관심사별 분할 계획을 세워뒀으나, 두 파일
모두 한 번에 리뷰가 완주해(각각 2건·4건만 반환) 쪼갤 필요가 없었다 — 다만 이게
12,808줄 전체를 빠짐없이 훑었다는 보증은 아니므로(리뷰어 자체 판단으로 findings를
추릴 수 있음), 정말 철저한 커버리지가 필요하면 재검토 시 관심사별 분할도 고려.

**완료 기준 충족**: 두 파일의 findings 6건 전부 분류·처리(커밋 `bb248b4`, 그리고 이번
core_view.py 3건 반영 커밋). 전체 스위트 1005종(신규 4종 포함) 통과.

---

### Phase 3 — host_* UI 레이어 코드리뷰 — **진행 중 (2026-08-25/26 착수)**

**대상**: `host_dialogs.py`(2,872) · `host_ui.py`(1,956) · `host_widgets.py`(1,181) ·
`host_fileio.py`(1,187) · `host_context.py`(783) · `host_style.py`(602) ·
`host_selection.py`(490) · `host_canvas.py`(462) · `host.py`(422) · `host_undo.py`(305) ·
`host_layers.py`(257) · `host_mindmap.py`(234) · `shortcuts.py`(132)

⚠ **세션 한도로 1차 실행 일부 실패** — `host_dialogs`/`host_ui`/`host_widgets`는 완료됐으나
`host_fileio`와 9개 묶음은 API 세션 한도로 실패해 재실행함(2026-08-26). 재실행 중.

- [x] `host_dialogs.py`(2,872줄) — **완료**. 4건 발견, 2건 반영(커밋 `61b5cca`): 확대창이
      타이핑 중 350ms마다 키보드 포커스를 뺏던 버그, `event()` 중복코드 2곳 통합. 2건
      보류(저수확 커서 UX·씬 중복빌드는 설계변경 규모).
- [x] `host_ui.py`(1,959줄) — **완료**. **0건**(방금 반영한 Phase 1 수정을 리뷰어가
      직접 검증 — 재진입 위험·정리 경로 전부 안전하다고 확인, 별도 채택 없음).
- [x] `host_widgets.py`(1,181줄) — **완료**. 2건 발견, 1건 반영(커밋 `afdc7f3`): 팔레트
      버튼 드래그 중 오른쪽 버튼 release가 왼쪽 드래그를 잘못 끝내던 버그. 1건 스킵
      (캐시된 rect 산술 중복 호출, 실질 비용 0에 가까움).
- [ ] `host_fileio.py`(1,187줄) — **재실행 중**(2026-08-26).
- [ ] 나머지 9개 묶음(3,687줄) — **재실행 중**(2026-08-26, 8각도 서브에이전트 병렬).
      1차 실행에서 여러 각도(D·E·F·G·H·B·C)가 findings를 이미 반환했으나 메인 취합·
      검증 에이전트가 세션 한도로 죽어 **미검증 상태로 폐기** — 재실행 결과만 신뢰한다.
      (참고로만: 반복 발견된 패턴은 host.py 분할(2026-08-02) 잔재인 `_MERMAID_SHAPE_ITEM`
      /`_PALETTE_MIME` 등 상수가 9개 파일에 죽은 사본으로 복제된 것, 그룹 프레임 관련
      추가 성능·정확성 이슈, 고아 `@staticmethod` 중복 데코레이터 3곳 — 재검증 시 이
      단서들을 우선 확인)
- [ ] **중점 축**: QThread 수명(이 프로젝트가 반복해서 크래시를 낸 지점) · 다이얼로그
      `done()`/`reject()` 경로 · 시그널 연결 해제 · 위젯 부모 관계

**완료 기준**: findings 분류표.

---

### Phase 4 — fileio·ai 경계 코드리뷰 (데이터 손실 리스크 최상)

**대상**: `fileio/`(document 489 · dxf_import 711 · dxf_export 365 · pdf_export 395 ·
svg_import 309 · mermaid_import 292 · sketch_build 212 · symbol_library 173) ·
`ai/`(gateway 379 · text_to_mermaid 87 · text_to_svg 85)

- [ ] `/code-review high easycad/fileio/`
- [ ] `/code-review high easycad/ai/`
- [ ] **중점 축**:
      - **왕복 무손실성** — `.ecad` 저장→열기, DXF 내보내기→가져오기에서 잃는 필드
        (알려진 미검증: 화살촉 개수 `head_start` 보존 여부)
      - **하위호환** — 옛 `.ecad`가 지금 코드로 열리는지(스키마가 여러 번 확장됨:
        `cuts`·`favorite`·`head_scale`·`_group_id`·다중 라벨)
      - **조용한 실패 12곳** — `except Exception: pass`가 데이터 손실을 숨기는지 개별 판정
        (특히 `dxf_export.py:76,80` · `dxf_import.py:125,519` · `host_fileio.py:1141`)
      - **API 키 취급** — `gateway.py`의 secrets 경로·QSettings, 로그·예외 메시지 노출 여부

**완료 기준**: findings 분류표 + 왕복 무손실성 판정표.

---

### Phase 5 — 프로젝트 고유 함정 재발 감사 (자체 · 스킬이 못 하는 부분)

`docs/pitfalls.md`의 각 계열이 **지금 코드에 재발해 있지 않은지** 기계적으로 확인한다.
이 프로젝트에서 같은 함정이 2~4회씩 재발한 이력이 있어(예: `_scale_or_1` 나눗셈 누락 4회)
"한 번 고쳤다"가 보증이 안 된다.

- [ ] **좌표계·변환** — `_scale_or_1()` 나눗셈 누락 grep (4회 재발 이력) ·
      `_content_rect()`를 "보이는 외형"으로 오용한 곳 · `drawForeground` 이중 변환
- [ ] **히트테스트·후보목록 누락** — `isinstance(it, (_RectItem, ...))` 병렬 목록 전수 대조
      (새 타입 `_PolygonItem`·`_TextItem`·`_GroupBindProxy`가 빠진 목록이 있는지)
- [ ] **이벤트 우선순위** — `mousePressEvent`/`mouseMoveEvent`/`mouseDoubleClickEvent`에서
      `current_tool`을 확인 안 하는 early-return 분기 전수 나열
- [ ] **`try/finally` 뒷정리 보장** — 조기 return이 많은 핸들러의 상태 플래그 해제 경로
- [ ] **버전키 메모이즈** — `prepareGeometryChange()` 순서(super 먼저) · 네이티브 Qt 호출이
      우회하는 캐시
- [ ] **Qt 레이아웃 `updateGeometry()`** — 위젯 경계마다 걸렸는지
- [ ] 발견분은 회귀 테스트와 함께 Phase 7에서 반영

**완료 기준**: pitfalls.md 계열별 "재발 없음 / 재발 발견(위치)" 판정표.

---

### Phase 6 — Not-tested 백로그 트리아지 + 실사용 검증 시나리오표

커밋 본문에 `Not-tested:` 줄이 **342건** 쌓여 있다. 이건 "미검증 부채 장부"이며,
최종 검수에서 한 번은 훑어야 한다.

- [ ] 342건을 4분류:
      1. **손맛 전용**(마우스 드래그 감각 등) — 대리 불가, 사용자 확인 시나리오표로 이관
      2. **자동화 가능한데 안 한 것** — 지금 테스트를 써서 닫는다
      3. **이미 무효**(그 코드가 이후 바뀜) — 장부에서 지운다
      4. **진짜 미해결 버그** — 즉시 수정 대상
- [ ] 알려진 미해결 항목 명시적 재확인:
      - PDF 용지크기/방향 "안 먹힘"(표제란 락 가설, 사용자 재확인 대기)
      - "내 심볼" 개별 썸네일이 옅게 보이는 문제
      - 마인드맵 빈 노드 취소 시 남는 고아 화살표
      - DXF 왕복 화살촉 개수 보존
- [ ] **실사용 검증 시나리오표 작성** — 사용자가 `python run.py`로 한 번에 훑을 수 있는
      체크리스트(기능별 최소 경로). 이 프로젝트에서 버그가 가장 많이 나온 경로다.

**완료 기준**: 4분류표 + 사용자용 시나리오 체크리스트 문서.

---

### Phase 7 — 수정 반영 · 릴리스 준비 · 마감

- [ ] Phase 2~6의 **채택 findings 반영** — 건마다 회귀 테스트 동반 (전역 규칙 8: surgical)
- [ ] 반영 후 **전체 스위트 재실행**(Phase 1에서 복구된 상태로) + `perf_baseline_check.py`로
      시각·기하 지문 무회귀 확인 + `perf_bench.py`로 Phase 1 베이스라인 대비 성능 무회귀
- [ ] **진단 로그(`_dbg`/`_dbg2`) 처리 결정** — 유지 / 환경변수 게이트 / 제거 (사용자 승인 필요)
- [ ] **죽은 코드 보고**(제거는 별건 — 전역 규칙 8: 기존 dead code는 보고만)
- [ ] **릴리스 준비**: PyInstaller 스펙(원 계획서 Phase 0 미실행분) · README 최신화 ·
      `requirements.txt` 버전 고정 여부 · `__version__` 상향 + git 태그
- [ ] `doc-sync`로 CLAUDE.md·계획서 최종 동기화
- [ ] (선택) `/code-review ultra` 최종 1회 — 사용자 트리거·과금 · Phase 2~6 종료 후 판단

**완료 기준(실조건)**: 전체 스위트 exit 0 · 실사용 시나리오표 사용자 통과 · 태그된 릴리스.

---

## 4. 실행 순서와 세션 배분 (권장)

| 세션 | Phase | 비고 |
|---|---|---|
| 1 | Phase 0 + Phase 1 착수 | 정리는 짧다. 크래시 진단에 시간을 쓴다 |
| 2 | Phase 1 완료 | 완료 기준이 명확(exit 0). 여기가 안 끝나면 다음으로 안 감 |
| 3~4 | Phase 2 | 파일이 커서 2세션 예상 |
| 5 | Phase 3 | |
| 6 | Phase 4 | |
| 7 | Phase 5 | |
| 8 | Phase 6 | |
| 9~10 | Phase 7 | 발견량에 따라 유동 |

⚠ **Phase 2~6은 서로 순서를 바꿔도 된다**(독립적). **Phase 7은 반드시 마지막**이다.
Phase 1은 우선순위가 가장 높지만 **차단 조건은 아니다** — 타임박스(2세션)를 넘기면 임시
안전망(`--ignore` 러너, 900개)을 공식화하고 Phase 2로 진행한다.

---

## 5. 진행 기록

> 각 Phase를 닫을 때 여기에 결과·수치·판단을 추가한다.

- **2026-08-25** — 계획 수립. §0 실측 완료. 회귀 안전망 붕괴(exit 127) 발견 →
  범인을 `test_part1_ui_arrows.py` 하나로 특정(제외 시 900개 완주 = 필요충분 실측),
  임시 안전망 확보로 계획 교착 위험 제거.
- **2026-08-25 (후속)** — **Phase 0 완료**. 문서 6건 동기화, `symbol_library.json`을
  진짜 사용자 데이터로 확인(오염 아님), `이미지 모음/` gitignore 편입, 커밋 `d382fb1`,
  태그 `v0.1.0`(로컬) 생성. `tools/_kbs_hit_crop.png`·`tools/_route_bug.png`(tracked인데
  ignore 미적용)를 Phase 7 정리 후보로 기록. 다음: Phase 1(exit 127 진단, 타임박스 2세션).
- **2026-08-25 (후속 2)** — **Phase 1 완료(타임박스 안, 근본원인 규명 성공)**. exit 127
  크래시를 `test_left_panel_scrolls_...` 단일 테스트로 확정(가설 3개는 전부 기각 —
  실제 원인은 `processEvents()` 재진입 중 `deleteLater()` 처리로 인한 힙 손상), 프로덕션
  코드(`host_ui.py`)와 테스트(`test_part1_ui_arrows.py`) 양쪽 수정. AI 게이트웨이 테스트
  3건은 `SECRETS_FILE` 격리 누락으로 확인·수정. `symbol_library.json` known issue는
  정식 스위트 무죄로 재확인(memory 갱신). 전체 스위트(1001종)+자체러너(865종) exit 0
  안정 재현(각 2~3회). 성능 베이스라인 1회 저장(관찰 1건 Phase 7로 이관). 다음: 커밋 →
  `docs/history/2026-08.md`+`docs/pitfalls.md` 기록 → Phase 2(코어 2대 파일 코드리뷰).
- **2026-08-25 (후속 3)** — **Phase 2 완료**. `core_shapes.py`(2건)·`core_view.py`(4건,
  백그라운드 fork로 병렬 실행) 리뷰 완료, findings 6건 중 5건 즉시 반영(전부 그룹
  프레임 기능의 `_GroupBindProxy` 관련 성능·정확성 버그 — 중복 scene 전체스캔 3곳,
  라우팅 장애물 오판, 정렬 자기매칭 오판), 1건은 low-impact로 근거와 함께 보류. 신규
  pytest 4종, 전체 스위트 1005종 통과. 다음: 커밋 → Phase 3(host_* UI 레이어 코드리뷰).
