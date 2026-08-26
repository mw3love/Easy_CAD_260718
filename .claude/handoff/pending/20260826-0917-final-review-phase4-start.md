# 최종 검수 Phase 4 착수 — fileio·ai 경계 코드리뷰

생성: 2026-08-26 09:17

## 배경

Easy CAD 최종 검수(완성도·안정성 향상) 계획서는 `docs/final_review_plan.md`에 있다.
Phase 0~3은 완료됐고(각 완료 기준·수치는 그 문서 §5 진행 기록 참조), 이번 세션에서
**Phase 4부터의 방법론을 바꿨다** — 반드시 이 변경사항을 알고 시작할 것:

- Phase 2~3을 실제로 `code-review` 스킬(`/code-review high <경로>`, 일부는 백그라운드
  fork)로 돌려본 결과, 서브에이전트 호출량이 사용자의 Claude Code 요금제로 감당이 안
  된다는 게 확인됐다(같은 이유로 `superpowers` 플러그인도 이 세션에서 완전
  삭제했다 — `claude plugin uninstall superpowers@claude-plugins-official`).
- 전역 `~/.claude/settings.json`에 `skillOverrides: {"code-review":
  "user-invocable-only"}`를 걸었다 — Claude가 스스로 판단해 자동 호출하는 것만
  막고, 필요하면 `/code-review`로 직접 부르는 것 자체는 열려 있다(완전 `"off"`는
  아님, 나중에 저부담 effort로 국소 사용할 옵션은 남겨둠).
- **Phase 4부터는 `code-review` 스킬을 쓰지 않고 자체 진행한다**(Read/Grep으로
  직접 정독). 계획서 §1 표, Phase 4 체크리스트, Phase 7 체크리스트를 이 방침대로
  갱신하고 커밋까지 완료함(커밋 `c18b24c` "docs: 최종 검수 방침 변경 — Phase 4부터
  code-review 스킬 미사용").

## 지금 시작할 것 — Phase 4

`docs/final_review_plan.md`의 "Phase 4 — fileio·ai 경계 코드리뷰 (데이터 손실 리스크
최상)" 절을 그대로 열어서 시작한다. 요약:

**대상**: `fileio/`(document 489줄 · dxf_import 711 · dxf_export 365 · pdf_export 395 ·
svg_import 309 · mermaid_import 292 · sketch_build 212 · symbol_library 173) ·
`ai/`(gateway 379 · text_to_mermaid 87 · text_to_svg 85)

**체크리스트(자체 진행, 갱신된 항목 포함)**:
1. **자체 정독** — Read/Grep으로 파일별 직접 훑기.
2. **일반 정확성·중복/단순화·효율 스캔**(신규 항목) — code-review 스킬이 자동으로
   하던 역할의 수동 대체. Phase 2~3에서 스킬이 실제로 찾아낸 findings 유형(캐시
   무효화 누락, identity 비교 오판, scene 전체 중복 스캔 등, `docs/final_review_
   plan.md` Phase 2·3 절 참조)을 참고 기준으로 삼아 비슷한 패턴을 찾는다.
3. **중점 축**(도메인 특화):
   - 왕복 무손실성 — `.ecad` 저장→열기, DXF 내보내기→가져오기에서 잃는 필드
     (알려진 미검증: 화살촉 개수 `head_start` 보존 여부)
   - 하위호환 — 옛 `.ecad`가 지금 코드로 열리는지(스키마 확장 이력: `cuts`·
     `favorite`·`head_scale`·`_group_id`·다중 라벨)
   - 조용한 실패 12곳 — `except Exception: pass`가 데이터 손실을 숨기는지 개별
     판정(특히 `dxf_export.py:76,80` · `dxf_import.py:125,519` ·
     `host_fileio.py:1141`)
   - API 키 취급 — `gateway.py`의 secrets 경로·QSettings, 로그·예외 메시지 노출 여부

**완료 기준**: findings 분류표 + 왕복 무손실성 판정표(문서 Phase 4 절 그대로).

## 판단 기준

- 발견한 버그는 규모가 작고 즉시 검증 가능하면 Phase 2·3 때처럼 **즉시 반영**(회귀
  테스트 동반), 설계 변경급이거나 파급 범위가 넓으면 Phase 7로 미루고 여기선 기록만.
- Phase 4가 끝나면 계획서 §5 진행 기록에 결과를 추가하고, 다음은 Phase 5(프로젝트
  고유 함정 재발 감사 — `docs/pitfalls.md` 계열별 대조, 이건 원래부터 자체 진행
  설계라 방법론 변경과 무관)로 넘어가면 된다.

## 참고 — 대기 중인 다른 인계 항목

`.claude/handoff/pending/`에 이 파일보다 먼저 생성된 항목이 하나 더 있다
(`20260825-1159-palette-svg-feedback-2-3.md`, SVG 다중조각 심볼 큐닷 관련 설계
논의). `/handoff`는 가장 오래된 것부터 처리하므로 그게 먼저 뜬다 — Phase 4를
바로 시작하고 싶으면 그 항목은 잠깐 미루겠다고 말하면 된다.
