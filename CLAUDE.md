# Easy CAD — 프로젝트 지침 (Claude Code용)

빠르고 쉬운 **순서도/간단도면 작성기**. 최종 목표는 **PDF 인쇄**, 기존 CAD 자산과 **DXF 상호운용**.
"가벼운 CAD 대체 + 쓰면서 나에게 맞추는 맞춤 프로그램". pasteflow 주석 편집기를 독립 무한캔버스
앱으로 승격한 프로젝트.

> 이 파일은 세션 연속성용이다. Claude의 프로젝트 *기억*은 세션 시작 폴더(cwd)로 키가 걸려,
> 초기 세션들(Drive 경로 `G:\내 드라이브\A1. 개인 자료\A1. AI 연습\260718 Easy CAD`)에서 쌓은
> 기억은 이 Dev 경로 세션엔 자동으로 안 딸려온다. 그래서 핵심 맥락을 여기 적어둔다.

## 확정 결정 (심층 인터뷰, 2026-07-18)
- 플랫폼: **PyQt6 데스크톱**. pasteflow(`C:\Users\7make\Dev\Paste_flow`) 편집기를 verbatim 이식해 승격.
- CAD 상호운용: **DXF 파일 왜복**(`ezdxf`, 베지어→SPLINE). 클립보드 직행은 AutoCAD 독자포맷이라 보류.
- 빌드 vs 바이: **직접 제작**(draw.io 인터페이스 불편·QCAD 과함, 사랑하는 스냅+베지어 UX를 이미 보유).
- 전체 계획서: `docs/EasyCAD_계획.md` (리포 내). 참고 이미지·PDF는 `docs/reference/`
  (구글드라이브 원본에서 이관 — 대용량 PDF는 `.gitignore`로 로컬만 유지).

## 구조
```
easycad/
├── canvas/
│   ├── annotator_core.py   pasteflow 편집기 verbatim 이식 + 우리 확장(지속연결 등). 크게 편집 가능(우리 fork).
│   └── host.py             무한캔버스 호스트(얇은 owner + 최소 툴바/메뉴)
├── fileio/
│   ├── pdf_export.py       PDF 출력(A4~A1, 전체/선택영역)
│   └── document.py         .ecad(JSON) 저장/열기 — 문서모델 씨앗(DXF 매핑 기반)
└── main.py · run.py        진입점
tests/test_easycad.py       offscreen 회귀 스위트 (python tests/test_easycad.py)
```
실행: `python run.py` · 테스트: `python tests/test_easycad.py` · PyQt6 전역설치(Python 3.14).

## 진행 상태
- **Phase 0** 완료: 코어 승격 + 무한캔버스(팬/줌) + 8도구 + 스냅 + 베지어 화살표 + undo + 연속복붙.
- **Phase 1** 완료: PDF 출력(Ctrl+P/Ctrl+Shift+P) · .ecad 저장/열기(Ctrl+N/O/S).
- **Phase 2** 진행:
  - 화살표 **지속 연결** 완료(고정 부착점 방식). 도형에 붙은 화살표 끝이 이동해도 붙은 채 유지,
    둘 다 선택 시 강체·한쪽만이면 늘어남, 멀리 끌면 unbind, 곡선 보존. `.ecad`에 직렬화.
  - 휠=줌 / **Shift+휠=두께·크기** 조절(무한캔버스 휠-줌 충돌 해소).
  - 기준 zoom: **Ctrl+0=100%(1:1)**, **Ctrl+9=전체 맞춤**.
  - **o-snap 토글**(F3 / 보기 메뉴) — 스냅 켜고 끄기.
  - **다중선택 그룹 변형** 완료: 회전·균일/비균일 스케일·미러(Shift+H/V) + **stretch**(crossing
    박스 걸친 정점만 이동, 명시적 `S` 모드). 상세 이력은 메모리 `connector-roadmap`.
  - **좌/우 드래그 선택** 완료(`d4be731`): 왼→오=window(완전포함, 파란 실선) / 오→왼=crossing(걸침,
    초록 점선). AutoCAD 시그니처. Qt 기본 RubberBandDrag를 방향 감지 커스텀 밴드로 대체.
  - **선/화살표 더블클릭 라벨** 완료(`260f73c`): 더블클릭으로 텍스트 부착, 본체 이동·변형 시 라벨이
    중점을 따라옴(`_LabelMixin`). 선·베지어화살·직선화살 모두 지원. `.ecad`에 직렬화.
  - **직교 자동라우팅** 완료(`ddd4ca3`·`75d8abc`·`d454227`): 직선화살(sarrow)의 Lucid식 직교 라우팅
    + 장애물 회피 → A* 승격(Hanan 그리드)으로 밀집 배치에서도 관통 0.
  - **단일객체 Lucid식 박스 핸들**(`3eec670`): 꼭짓점 2D·변 1축·좌상단 회전.
  - **스마트 정렬 가이드**(`ee0346a`): 이동 중 모서리·중심 정렬 스냅 + 가상선.
  - **빠른 생성 도트 + 고스트 미리보기**(`65b5958`).
  - **심볼/스텐실 라이브러리** 완료: 좌측 「심볼」 dock 팔레트(판단·시작끝·입출력·준비·문서·저장소
    6종) → 무장 후 캔버스 드래그로 그리기. `_SymbolItem`(rect 기반 → 리사이즈·회전·stretch·undo
    전부 재사용) + kind별 경로 팩토리(`_SYMBOL_KINDS`). 화살표가 심볼 **실제 외곽선**에 스냅·지속
    연결(`_symbol_nearest`, 외접 박스 아님 — GUI 실조건 확인). `.ecad`에 kind 직렬화.
  - **닫힌 도형 중앙 라벨** 완료: 네모·원·심볼을 더블클릭하면 도형 **정중앙**에 텍스트 부착,
    리사이즈 시 추종. `_CenterLabelMixin`(`_LabelMixin`의 '중점 위쪽' 대신 '정중앙')을 셋이 공유.
    선·화살표는 기존 `_LabelMixin`(중점 위쪽) 유지. `.ecad`에 직렬화.
  - **포트/접속점** 완료(`1b06976`): 도형의 변 중점 4개(N·E·S·W)를 이산 접속점으로. `_shape_ports`가
    변 중점을 실제 외곽선에 투영(마름모=꼭짓점). 스냅은 **포트 우선(18px) + 연속 폴백(14px)**
    2패스(`_border_snap_at`) — 기존 자유 스냅 유지. 화살표 도구로 도형 근처면 포트 점 예고, 바인딩은
    `set_bound` 재사용(이동 추종).
- **Phase 3** 진행: DXF 상호운용(`ezdxf`).
  - **DXF 내보내기** 완료(`3f4afde`): `fileio/dxf_export.py`. .ecad 각 아이템 → 개별 DXF 엔티티
    (rect→LWPOLYLINE·ellipse→CIRCLE/ELLIPSE·arrow→SPLINE·sarrow→LWPOLYLINE·text→MTEXT·
    badge→CIRCLE+MTEXT·symbol→외곽선 폴리라인). 타입별 레이어(EC_*)·true_color·Y축 뒤집기(CAD Y-up).
  - **DXF 가져오기** 완료(`dd31967`): `fileio/dxf_import.py`. export의 역매핑 — 레이어 힌트로 타입
    판정, Y-flip 역변환(involution), 4꼭짓점/타원 장축으로 회전 흡수. 화살촉 삼각형=무시+tip으로 head
    방향복원, 심볼 kind=외곽선 `_PathItem`으로만 복원(소실), 외부 DXF는 dxftype 폴백. 왕복 스모크 2종
    (핵심 월드 기하 일치). 손실 범위(승인됨): 바인딩·라벨(→독립 텍스트)·심볼 kind·변환 필드값.
  - **펜 두께 왕복** 완료(`262a904`): 두께를 XDATA(AppID `EASYCAD`, 코드 1040 float)로 실어 복원.
    DXF 표준 `lineweight`는 enum 스냅(6→9)으로 무손실 불가라 배제(실측). 실조건 확인.
  - 파일 메뉴: **DXF 내보내기 `Ctrl+Shift+D`** / **가져오기 `Ctrl+Shift+I`**(열기 시맨틱, 씬 대체).
  - **실조건검증 완료 ✓**(2026-07-20): 우리 DXF를 **AutoCAD 2022**에서 열어 도형·텍스트·화살표가 개별
    엔티티로 인식됨 확인 → 계획서의 Phase 3 완료 게이트 충족(Phase 3 종료). 왕복도 정상.

## 다음 할 일 (우선순위)
> 1·2·3번은 완료됨(2026-07-20 코드 대조로 문서 갱신). 남은 것은 4번 일부와 Phase 3 이후.
1. ~~좌/우 드래그 선택~~ — **완료**(`d4be731`, window/crossing).
2. ~~선/화살표 더블클릭 라벨~~ — **완료**(`260f73c`, 부착·이동추종).
3. ~~회전/미러/스케일/stretch(다중 선택)~~ — **완료**(그룹 변형 Stage 1·2a·2b).
4. (계획서 §5 권장 흡수) — **전부 완료**(직교 커넥터+자동라우팅·심볼 라이브러리·포트/접속점):
   - ~~심볼/스텐실 라이브러리~~ — **완료**(6종 dock 팔레트 + 외곽선 스냅 + 중앙 라벨). 후속:
     진짜 드래그앤드롭, 심볼 종류 추가.
   - ~~포트/접속점~~ — **완료**(`1b06976`, 변 중점 4포트 우선 스냅 + 연속 폴백). 후속: 8포트(꼭짓점 추가).
5. **상단바 정리** — 네모·원 버튼을 왼쪽 「도형」 팔레트로 이관 **완료**(기본+순서도 섹션, 원은 곡선
   기하 유지·배치만 통일, 단축키 2·5 유지). 상단은 그리기 도구 7종만. 추가 정리 아이디어는 메모리 `toolbar-cleanup-plan`.
**Phase 4(문서 완성도) 진행 중** — **이미지 삽입 완료**(`_ImageItem` rect 기반 재사용, `Ctrl+Shift+M`
+드래그앤드롭, `.ecad` base64 embed, PDF 렌더·DXF 제외, 종횡비 고정 리사이즈, 실조건검증 2026-07-20).
**표제란/용지틀 완료(실조건검증 2026-07-20)** — `_TitleBlockItem`(모델공간 위 A-size 용지경계
프레임 객체, 진짜 paper space 아님·뷰포트 없음). 우하단 3행 표제란 표(발주처/프로젝트·도면번호·도면명·
축척·작성/검토/날짜) + 도면 테두리. 삽입 `Ctrl+Shift+T`(용지 크기·방향 선택), 더블클릭→필드 편집 폼
(용지 재선택 포함). 프레임 있으면 **PDF가 용지경계·크기·방향으로 자동 전환**. `.ecad` 직렬화(size·
orient·fields). 단일 프레임(다중 페이지 스코프 밖), 축척=텍스트 필드(자동계산 없음), DXF 제외(조용히
skip), 용지 내부 클릭통과(위에 그리기 가능). 설계 근거: deep-interview 2026-07-20. 실조건검증 ✓(한글
필드·더블클릭 폼·A2 PDF 사용자 확인).
**표 삽입 완료(실조건검증 2026-07-20 ✓)** — `_TableItem`(rect 기반 → `_ImageItem`처럼
`_HandleResizeMixin`·회전·undo·그룹변형·복제·PDF 재사용). NxM **균등 비례** 격자(전체 리사이즈 시 열·행
동일 비율, 개별 열폭은 후속), 첫 행 헤더(굵게+음영 옵션). 셀 더블클릭→**인라인 편집**(`_CellEditor`
QLineEdit, Enter=아래·Tab=오른쪽 줄넘김·Shift+Tab=왼쪽·Esc=취소·포커스상실=커밋, undo 스코프 밖).
삽입 `Ctrl+Shift+B`(행·열·헤더 다이얼로그). `.ecad` 직렬화(rows·cols·header·rect·cells), DXF 제외
(조용히 skip). 설계 근거: deep-interview 2026-07-20(표 vs Mermaid 중 표 선택, 균등만·인라인편집으로
스코프 확정). 스코프 밖: 개별 열폭 드래그·셀 병합·텍스트 붙여넣기 파싱·셀편집 undo. 실조건검증 ✓(삽입·인라인
편집 엔터/탭·리사이즈·저장/재열기·PDF 사용자 확인).
**Mermaid import 완료(실조건검증 2026-07-21 ✓)** — `fileio/mermaid_import.py`(순수 Python, Qt 비의존):
flowchart 파서 + **자체 BFS 계층 배치**(외부 의존성 0 — 규칙 2 손안의 카드: 엣지 라우팅은 기존
`_PolyArrowItem` 직교 자동라우팅이 담당, 노드 배치만 자체 구현). 붙여넣기 다이얼로그 `Ctrl+Shift+G`.
지원(핵심 부분집합): 방향 5종(TD/TB/LR/RL/BT)·노드 8모양→우리 도형 매핑(마름모=decision·스타디움=
terminal·평행사변형=data·육각형=prep·원기둥=database·원=ellipse·나머지=rect)·화살표 4종(--> --- -.->
==>)+파이프/인라인 라벨·한 줄 체인. 노드→`_RectItem`/`_EllipseItem`/`_SymbolItem`(중앙 라벨), 엣지→
`_PolyArrowItem`(지속연결 바인딩+직교 엘보). `.ecad`·PDF는 기존 아이템 직렬화 재사용(코드 변경 0),
DXF는 대상 아님. 스코프 밖(승인): subgraph·classDef/스타일·click·`&`·점선/굵은선 스타일(실선 흡수).
설계 근거: deep-interview 2026-07-21. **Phase 4 완료.**
  ⚠ 이때 라벨 중앙정렬 순서 버그 발견·수정: 삽입 헬퍼가 `addItem` **전**에 라벨을 붙이면
  `_sync_label`이 씬 멤버십 가드로 no-op해 라벨이 좌상단(0,0)에 박힘 → addItem **후** `_sync_label()`
  재호출로 해결. 라벨 세로는 글리프 잉크 중심 보정(`_ink_center_dy`, 실렌더 픽셀측정)·원기둥 광학중심
  오프셋 추가. (검증 함정: 헤드리스는 한글 tofu라 정렬 못 봄 → 비-헤드리스 `QGraphicsView.grab()`으로 실폰트 재현.)
**Phase 5(AI 이미지→도면) 진행 중** — **이미지→도면 빌더 완료(프록시검증, 실조건 대기)**:
`fileio/sketch_build.py`의 `Sketch` 빌더(순수 파이썬, **Qt 비의존** — `document.py`의 `.ecad` JSON
스키마를 직접 생성). 프레임 확정(deep-interview 2026-07-21): **앞단(이미지 이해)=Claude 네이티브
vision**(외부 API·게이트웨이 불필요 → 지속성, mindlogic 쿼터 무관), **뒷단(도형 생성)=이 빌더**,
좌표=이미지 픽셀 그대로. 규칙 2 손안의 카드: 이미지 *생성*이 아니라 *이해*가 필요한 Phase라 Claude
vision이 이미 손안에 있었음(게이트웨이 이미지생성과 결이 다름). 뒷단 포맷은 **`.ecad` 직접**(Mermaid
경유는 BFS 재배치가 원본 위치를 버려 배제 — 완성도 우선). 빌더 API: `box`/`ellipse`/`symbol`(6종)/
`arrow`(변 중점 포트 지속연결+`auto_route` 직교 엘보)/`text`, 중앙·중점 라벨. **앱 UI 없음**(최소
스코프 — Claude Code 안에서 저작, 산출물 `.ecad`를 사용자가 `Ctrl+O`로 엶). 워크플로: `docs/image_to_ecad.md`.
스모크 3종(`test_sketch_*`: 왕복·바인딩·색정규화). 스코프 밖(승인): 앱 내장 버튼(후속 A 승격 여지)·
Mermaid 경유·DXF 대상 아님·손글씨 OCR 정확도 보장. 자체렌더 확인(도형·직교라우팅·부착 ✓, 텍스트는
헤드리스 tofu). 실조건 대기: 사용자가 `python run.py`로 열어 라벨 내용·편집성 확인.
Phase 3(DXF)은 위 진행 상태 참조 — 내보내기·가져오기·펜 두께 왕복 완료. 후속: 외부 CAD 두께 렌더용
`lineweight` 병행 저장, 구식 POLYLINE·ARC 등 외부 DXF 엔티티 흡수 확대.

## 작업 규칙
- GUI라 **offscreen 스모크로 프록시검증** 후 **실조건은 사용자에게 `python run.py` 요청**.
  ⚠ 전례: 지속연결 초안이 offscreen을 통과했으나 GUI에서 버그 발견(플로팅→고정 부착점으로 수정).
  즉 **offscreen 통과 ≠ 해결**. GUI 확인 전 "해결" 단정 금지.
- **레이아웃·렌더링 시각 변경은 `python tools/screenshot.py`로 자체 검증**(PNG 렌더 → 직접 확인).
  툴바·팔레트 배치·도형·아이콘·색·위치는 이걸로 잡는다. 단 ⓐ 한글 텍스트는 헤드리스 폰트 없어 □로
  뜨고 ⓑ 상호작용 '느낌'(hover·드래그·스냅)은 못 잡으므로, 그 둘은 여전히 실조건(사용자 화면) 몫.
- 각 기능은 검증가능 목표로 닫고, 새 스모크는 `tests/test_easycad.py`에 추가(임시폴더 금지).
- 비자명 커밋엔 트레일러(Rejected/Constraint/Confidence/Not-tested) + `Co-Authored-By: Claude Opus 4.8`.
- 계획/검토 요청이면 코드 손대지 말 것(승인 게이트). "고쳐줘/만들어줘"면 실행.
- 코어는 pasteflow에서 복사해 분기한 것 — annotator_core.py 편집 허용(단 surgical하게, 주석으로 우리 확장 표시).
