# Easy CAD — 프로젝트 지침 (Claude Code용)

빠르고 쉬운 **순서도/간단도면 작성기**. 최종 목표는 **PDF 인쇄**, 기존 CAD 자산과 **DXF 상호운용**.
"가벼운 CAD 대체 + 쓰면서 나에게 맞추는 맞춤 프로그램". pasteflow 주석 편집기를 독립 무한캔버스
앱으로 승격한 프로젝트.

> 이 파일은 세션 연속성용이다. Claude의 프로젝트 *기억*은 세션 시작 폴더(cwd)로 키가 걸려,
> 초기 세션들(Drive 경로 `G:\내 드라이브\A1. 개인 자료\A1. AI 연습\260718 Easy CAD`)에서 쌓은
> 기억은 이 Dev 경로 세션엔 자동으로 안 딸려온다. 그래서 핵심 맥락을 여기 적어둔다.
>
> **2026-08-02 문서 분할**: 이 파일은 원래 1229줄(진행 로그 전체)이었다. 지침만 남기고
> 상세 진행 기록은 `docs/history/2026-07.md`·`docs/history/2026-08.md`로, 함정(⚠)만
> 추린 요약은 `docs/pitfalls.md`로 이관했다(코드·의미 변경 없음, git log가 나머지를 보존).
> **"무엇을 왜 했는지" 세부 경위가 필요하면 history를, "이거 전에 겪은 함정 있나"는
> pitfalls를, "다음에 뭐 할지"는 `docs/EasyCAD_계획.md` §8을 본다.**

## 확정 결정 (심층 인터뷰, 2026-07-18)
- 플랫폼: **PyQt6 데스크톱**. pasteflow(`C:\Users\7make\Dev\Paste_flow`) 편집기를 verbatim 이식해 승격.
- CAD 상호운용: **DXF 파일 왕복**(`ezdxf`, 베지어→SPLINE). 클립보드 직행은 AutoCAD 독자포맷이라 보류.
- 빌드 vs 바이: **직접 제작**(draw.io 인터페이스 불편·QCAD 과함, 사랑하는 스냅+베지어 UX를 이미 보유).
- 전체 계획서: `docs/EasyCAD_계획.md` (리포 내). 참고 이미지·PDF는 `docs/reference/`
  (구글드라이브 원본에서 이관 — 대용량 PDF는 `.gitignore`로 로컬만 유지).
  같은 이유로 **작업 산출물도 리포에 안 들어간다** — 루트 `*.ecad`와 작업 사진 폴더는 `.gitignore`
  (리포는 코드·문서만). 의도적 테스트 픽스처는 `tests/` 아래면 커밋 가능(루트 한정 패턴).

## 구조
```
easycad/
├── canvas/
│   ├── annotator_core.py   2026-08-02 분할 — 이제 아래 3개 재수출하는 얇은 shim(18줄).
│   │                       실제 코드 수정은 core_constants/core_shapes/core_view에서.
│   ├── core_constants.py   상수·아이콘·커서 팩토리(잎 모듈)
│   ├── core_shapes.py      `_HandleResizeMixin`+전체 아이템 클래스+최근접점/포트/A* 라우팅/
│   │                       그룹변형 — pasteflow verbatim 이식 + 우리 확장(지속연결 등),
│   │                       크게 편집 가능(우리 fork). 셋이 실제 순환의존이라 한 파일 유지(주석 참조).
│   ├── core_view.py        `_AnnotatorView` — 마우스/키 이벤트, 드래그선택, 스냅, 팬/줌
│   ├── host.py             CanvasWindow(창) — __init__만, 나머지는 아래 믹스인 다중상속
│   ├── host_ui.py / host_fileio.py / host_layers.py / host_style.py / host_undo.py /
│   │   host_selection.py / host_context.py / host_canvas.py   CanvasWindow 믹스인(역할별)
│   ├── host_widgets.py     독립 위젯(팔레트버튼·미니맵뷰·플로팅패널·토스트·색상팝업) + 공유 상수
│   └── host_dialogs.py     입력 다이얼로그(용지·표제란·표·케이블채번·Mermaid)
├── fileio/
│   ├── pdf_export.py       PDF 출력(A4~A1, 전체/선택영역)
│   ├── document.py         .ecad(JSON) 저장/열기 — 문서모델 씨앗(DXF 매핑 기반)
│   ├── dxf_export.py / dxf_import.py   DXF 왕복
│   ├── mermaid_import.py   Mermaid flowchart → .ecad
│   └── sketch_build.py     이미지→도면 빌더(Qt 비의존)
└── main.py · run.py        진입점
tests/
├── test_easycad.py         전체 실행 진입점(하위호환 shim) — python tests/test_easycad.py
├── _shared.py              공용 임포트·헬퍼(QApplication 등)
├── conftest.py             pytest용 env·sys.path 부트스트랩
└── test_part1~6_*.py       테마별 회귀 스모크 345종(개별 pytest 실행 가능)
docs/
├── EasyCAD_계획.md          로드맵·§8 다음 순서·큰 설계 필요 항목
├── history/2026-07.md 등    월별 상세 진행 기록(완료 사항의 경위·근거)
├── pitfalls.md              ⚠ 함정 요약(재발 방지 체크용)
└── reference/                참고 이미지
```
실행: `python run.py` · 테스트: `python tests/test_easycad.py` · PyQt6 전역설치(Python 3.14).

## 현재 상태 (요약 — 상세는 `docs/history/`)
- **Phase 0~5 완료**: 무한캔버스 코어, PDF/.ecad, 지속연결 커넥터(A* 직교 라우팅+경유힌트),
  심볼 라이브러리(14종), 포트/접속점, DXF 왕복(내보내기·가져오기·INSERT/BLOCK·펜두께),
  Mermaid import, 이미지→도면 빌더(`sketch_build.py`).
- **Phase 6(편집 경험 현대화 UI/UX) 진행 중** — M1~M5 완료(툴바→QToolBar, 다크모드, 플로팅
  패널, undo 저널, 정렬/분배 등). 이후 신규기능 다수 완료: 클립보드 이미지 붙여넣기·그리드/
  스냅투그리드·미니맵·스타일 복사(format painter)·케이블 자동채번·레이어 패널·캔버스-퍼스트
  레이아웃(도킹→플로팅)·DXF/.ecad 통합·8포트+라우팅 안정성 대수술·도형 채우기·색 선택 팝업.
  **M6(디자인 베이크오프) 진행 중** — 버튼 색·상태(코랄 accent, 완료·코드반영) → 아이콘
  판별성(시안 확정, 코드반영 미착수), 새 스킬 `design-bakeoff`(전역) + 취향 문서
  `~/.claude/design-system/` 도입(2026-08-02, `docs/history/2026-08.md` 참조).
- **다음 순서**: `docs/EasyCAD_계획.md` §8("다음 순서"·"큰 설계 필요") 및 Phase 6 M6 참조 —
  아이콘 SVG 코드 반영, 화살표 boundingRect 체인 후속 최적화, 실도면 대규모 성능 등.

## 작업 규칙
- GUI라 **offscreen 스모크로 프록시검증** 후, **실조건은 먼저 직접 재현 시도**(전역 CLAUDE.md
  규칙 11-d, 2026-07-31 개정) — 이 환경은 Bash가 사용자와 같은 대화형 데스크톱 세션이라
  `QT_QPA_PLATFORM=offscreen` 없이 같은 재현 스크립트를 그대로 돌리면 실제 창·콘솔 로그를
  직접 확인할 수 있다(마우스 클릭 자체가 아니라 결과 상태가 필요하면 API 호출로 대체 가능).
  정말 대리 불가능한 것(마우스 드래그의 손맛·실제 물리 기기·다중 모니터 조합)만 사용자에게
  `python run.py` 확인을 요청한다.
  ⚠ 전례: 지속연결 초안이 offscreen을 통과했으나 GUI에서 버그 발견(플로팅→고정 부착점으로 수정).
  즉 **offscreen 통과 ≠ 해결**. GUI 확인(자체 실행 또는 사용자 확인) 전 "해결" 단정 금지.
  같은 부류 함정을 다시 만나면 먼저 `docs/pitfalls.md`를 훑는다.
- **레이아웃·렌더링 시각 변경은 `python tools/screenshot.py`로 자체 검증**(PNG 렌더 → 직접 확인).
  툴바·팔레트 배치·도형·아이콘·색·위치는 이걸로 잡는다. 단 ⓐ 한글 텍스트는 헤드리스 폰트 없어 □로
  뜨고 ⓑ 상호작용 '느낌'(hover·드래그·스냅)은 못 잡으므로, 그 둘은 여전히 실조건(사용자 화면) 몫.
- 각 기능은 검증가능 목표로 닫고, 새 스모크는 `tests/`에 추가(임시폴더 금지).
- 비자명 커밋엔 트레일러(Rejected/Constraint/Confidence/Not-tested) + `Co-Authored-By: Claude Opus 4.8`.
- 계획/검토 요청이면 코드 손대지 말 것(승인 게이트). "고쳐줘/만들어줘"면 실행.
- 코어는 pasteflow에서 복사해 분기한 것 — `core_shapes.py`/`core_view.py` 편집 허용(단
  surgical하게, 주석으로 우리 확장 표시). `annotator_core.py`는 재수출 shim이라 정의가 없다.
- **완료한 비자명 작업의 경위·근거는 `docs/history/<년-월>.md`에 그 달 파일 맨 끝에 이어 쓴다**
  (CLAUDE.md 본문에 다시 쌓지 않음 — 2026-08-02 분할의 취지 유지). 새로 겪은 함정은
  `docs/pitfalls.md`에도 한 줄 추가.
