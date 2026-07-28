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
  같은 이유로 **작업 산출물도 리포에 안 들어간다** — 루트 `*.ecad`와 작업 사진 폴더는 `.gitignore`
  (리포는 코드·문서만). 의도적 테스트 픽스처는 `tests/` 아래면 커밋 가능(루트 한정 패턴).

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
  - **FigJam 라벨 갭 + 드래그** 완료(`391b65f`, 실조건검증 ✓ 2026-07-21): 화살표 라벨을 선/곡선 위
    **완전중앙**에 앉히고 paint에서 라벨 사각형과 겹치는 선을 끊어(=[C] 겹침 해결) 그 gap에 텍스트를
    놓는다(FigJam). 라벨 드래그=경로 따라 슬라이드(정규화 `t`)+옆으로 수직 오프셋(Lucid), `.ecad`에
    `t·off` 직렬화(하위호환). sarrow(`_PolyArrowItem`)=선분 Liang-Barsky 클리핑(`_seg_rect_interval`),
    곡선/직선 arrow(`_ArrowItem`)=QPainter 클립(3차 베지어 곡률 유지·선분근사 아님). 라벨은
    `_ConnectorLabel`(itemChange가 자유이동→경로 재투영, `ItemSendsGeometryChanges` 플래그 필수).
    히트테스트·직렬화·DXF는 전체 선 그대로(시각 갭만). ⚠ 함정: `itemChange(ItemPositionChange)`는
    `ItemSendsGeometryChanges` 없으면 발화 안 함.
  - **직교 자동라우팅** 완료(`ddd4ca3`·`75d8abc`·`d454227`): 직선화살(sarrow)의 Lucid식 직교 라우팅
    + 장애물 회피 → A* 승격(Hanan 그리드)으로 밀집 배치에서도 관통 0.
  - **직교 자동라우팅 경유지 힌트** 완료: 자동라우팅(A*) 중 중간 정점을 드래그하면 freeze 대신
    '경유 힌트'로 커밋 — 자동라우팅을 유지한 채 그 지점을 지나가도록 재계산. 화살표당 힌트
    최대 1개(여러 개 허용했더니 드래그할수록 계단식으로 지저분해짐 — GUI 실측 후 단일 제한).
    힌트 제거 스냅 반경은 화면 px 고정(테두리 스냅과 동일 관례, 줌과 무관하게 일정). sync-repos
    병합 시 Stage3(화살표 회피)·Stage4(근접정렬 흡수)와 함께 동작하도록 `build_elbow`/
    `_route_with_hints`에 avoid_segs·cross_penalty·정렬흡수 호출을 통합(2026-07-22).
  - **화살표-화살표 교차 회피(soft 벌점)** 완료(`dde043b`, Stage3): 코어 라우터가 다른 화살표를
    A* 비용의 **soft 벌점**으로 회피(장애물 아님 — hard는 경로실패→폴백 절벽·순서의존이라 배제).
    preferred 엘보가 도형은 안전하나 화살표를 가로지르면 두 A* 시도를 평가해 **교차를 가장 줄이는
    도형-안전 후보만** 채택(개선 없으면 preferred 유지). `_seg_cross_seg`·`_count_seg_crossings` 신설,
    `_astar_ortho(avoid_segs,cross_penalty)`, `_obstacle_arrow_segs`(self 제외), `_ARROW_CROSS_PENALTY=200`.
    되먹임 없음(재라우팅 트리거 불변 + `host._rerouting` 재진입 가드 + `build_elbow` 멱등). 인터랙티브는
    scene-change당 단일패스라 회피 1회 적용(순서의존)→다음 조작에서 자기교정. **실조건검증 ✓**(2026-07-21:
    run.py 로그인 순서도 — 긴 루프백들이 다른 화살표 관통 없이 우회 확인). ⚠ 함정(메모리
    `core-arrow-avoidance-deferred`): 화살표 좌표를 Hanan 격자선에 넣으면 A* 노드가 교차점에 얹혀
    벌점이 눈멂(해법: 안 넣음, 우회 레인은 도형 팽창 모서리만으로 충분).
  - **근접정렬 흡수(Stage4)** 완료(프록시+자체렌더 ✓, 실조건 재확인 대기): `[A]`백엣지·`[B]`수렴부의
    작은 계단은 **연결 도형 축이 몇 px 어긋나면 직교 경로가 그 차이만큼 짧은 점프를 반드시 넣는**
    기하적 필연으로 진단(라우터 버그 아님 — 정렬 시 계단 0, 실측). 해법 `_PolyArrowItem.
    _absorb_near_alignment`(build_elbow 라우팅 직전): 교차축(두 끝점의 **지배적 분리축의 수직** —
    가로연결 `|dx|≥|dy|`→Y, 세로연결→X) 어긋남 ≤ `_ALIGN_TOL`(8px)이면 부착점을 공통 축으로 스냅해
    계단을 직선으로 붕괴. 정렬 목표는 후보(상대끝점→자기→중점) 중 **두 부착점이 모두 도형 테두리 위**에
    남는 첫 값 → 마름모 꼭짓점은 축 밖으로 못 나가 자연히 '움직일 수 있는 박스 변'만 옮긴다. `_pts`+
    bind_pt 함께 갱신(reroute가 안 되돌림), 멱등(스냅 후 어긋남 0), 큰(의도적) 오프셋 미변경.
    ⚠ **v1 함정(실조건서 발견):** 방향판정을 법선으로 하면 마름모 E꼭짓점의 **대각 법선**에 속아
    decision 연결 6px 계단을 못 잡았다 → 법선 대신 **분리축**으로 교체(v2). 폭 다른 E-E 루프는 양쪽
    다 테두리 밖이라 코어로 못 잡음 → **build에서 열별 폭 통일**로 처리(코어+빌드 병행). 스모크
    `test_sarrow_absorbs_near_alignment`·`test_sarrow_absorbs_decision_alignment`. **[C] 라벨-선 겹침
    해결**(`391b65f`) — 위 'FigJam 라벨 갭 + 드래그' 항목으로 근본 해결(선을 라벨 자리에서 끊음).
  - **image→ecad 빌드 지침(밀집 순서도):** 실조건서 확인 — 열별 **박스 폭 통일**(E/W·N/S 포트 정렬),
    피드백 루프는 `channel_x`(열 변 밖 U-bump), 여러 화살표 합류는 `channel_y` 공통 레일(병합 버스),
    루프백은 `channel_x`를 서로 다르게(겹침 방지). 계단은 코어(Stage4)가, 겹침은 이 빌드 힌트가 잡는다.
  - **단일객체 Lucid식 박스 핸들**(`3eec670`): 꼭짓점 2D·변 1축·좌상단 회전.
  - **스마트 정렬 가이드**(`ee0346a`): 이동 중 모서리·중심 정렬 스냅 + 가상선.
  - **빠른 생성 도트 + 고스트 미리보기**(`65b5958`).
  - **심볼/스텐실 라이브러리** 완료: 좌측 「심볼」 dock 팔레트(판단·시작끝·입출력·준비·문서·저장소
    6종) → 무장 후 캔버스 드래그로 그리기. `_SymbolItem`(rect 기반 → 리사이즈·회전·stretch·undo
    전부 재사용) + kind별 경로 팩토리(`_SYMBOL_KINDS`). 화살표가 심볼 **실제 외곽선**에 스냅·지속
    연결(`_symbol_nearest`, 외접 박스 아님 — GUI 실조건 확인). `.ecad`에 kind 직렬화.
  - **닫힌 도형 중앙 라벨** 완료: 네모·원·심볼을 더블클릭하면 도형 **정중앙**에 텍스트 부착,
    리사이즈 시 추종. `_CenterLabelMixin`(`_LabelMixin`의 '중점 위쪽' 대신 '정중앙')을 셋이 공유.
    화살표는 FigJam 갭(위 항목), 플레인 선(`_LineItem`)만 기존 '중점 위쪽' 유지. `.ecad`에 직렬화.
    긴 라벨이 도형 내접폭 초과 시 **폰트 축소**(단일 줄, `_fit_label_to_shape`, 마름모 0.6·원 0.72·
    심볼 0.78·rect 0.85 내접비율)로 세로 spill 방지 — 실조건검증 ✓(2026-07-21, 마름모 shrink+수동
    엔터 다줄). ⚠ 함정: wrap(줄바꿈)은 마름모서 줄 수 폭발→세로 spill이라 배제(실측); 폭 측정은
    `_content_rect`가 contentsChanged 콜백서 stale이라 `QFontMetricsF` 직접측정.
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
4. (계획서 §5 권장 흡수) — **전부 완료**(직교 커넥터+자동라우팅(A*·경유지 힌트)·심볼 라이브러리·포트/접속점):
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
헤드리스 tofu). **실조건검증 ✓**(2026-07-21: run.py에서 한글/영문 라벨·편집성·지속연결·직교라우팅
확인). ⚠ 실조건에서 발견: 연결 도형의 **중심축이 몇 px만 어긋나도** 직교 라우터가 화살표에 작은
계단(꺾임)을 넣는다 → 해법은 노드를 격자 정렬(Mermaid BFS가 반듯한 이유와 동일). 이미지 읽을 때
연결 도형의 중심 x(세로연결)·중심 y(가로연결)를 맞추도록 워크플로 문서에 지침 추가(마름모·원은
극점이 중심축에만 있어 특히 중요). **Phase 5 이미지→도면 빌더 완료.**
Phase 3(DXF)은 위 진행 상태 참조 — 내보내기·가져오기·펜 두께 왕복 완료. **외부 CAD 두께 렌더용
`lineweight` 병행 저장 완료**(M2 #3 실조건 D서 AutoCAD가 XDATA 두께를 못 읽어 전부 얇게 렌더 →
`_wx`가 XDATA(1040, 무손실 왕복)에 더해 표준 `lineweight`(px×10→유효 enum 스냅, 표시 전용)를
병행 부착 + `$LWDISPLAY=1` 헤더로 선가중치 표시 ON. import는 XDATA 우선 유지=무손실. 실조건검증 ✓
2026-07-22 AutoCAD 2022서 두께 구분 확인). 후속: 구식 POLYLINE·ARC 등 외부 DXF 엔티티 흡수 확대,
외부 DXF의 lineweight→px 역폴백(현재 미지원).

**Phase 6(편집 경험 현대화 UI/UX) 진행 — M1 완료(2026-07-22, 실조건검증 ✓)** — 상단바를 커스텀
QWidget→**QToolBar**로 승격: 그리기 도구 아이콘화(코어 `_tool_icon` 재사용) + 파일·삽입·보기 QAction
이관(메뉴 유지·액션 공유) + 긴 단축키 라벨 제거→`?`/F1 도움말 다이얼로그(창 최소폭 축소·오버플로우 ≫).
**다크모드**(다크 기본+라이트 토글 `Ctrl+Shift+L`, Fusion 팔레트+캔버스 배경+아이콘 테마색, QSettings
저장; ⚠ `scene.render`가 배경까지 그려 **PDF는 흰배경 강제**). **도형 dock 4방향**(그립 `⋮⋮`+accent
밑줄 제목, 상/하 dock이면 `_relayout_sections`로 버튼 한 줄로 눕힘) + **줌% 상태바**(클릭=100%) + 창
제목 'Easy CAD'. **속성 dock(읽기전용)** — 선택 객체 종류·색(스와치)·두께·선스타일·폰트 값 표시(편집은
M2). 패널은 콤팩트 기본폭(도형 144·속성 170px)으로 **진짜 최소 클램프**(슬랙 0)+버튼 고정크기 좌측뭉침.
아이콘/UI 방향=icon_proposal 아티팩트. 커밋 `80f22fa`~`e8f3d45`. **M3 완료(2026-07-22, 실조건검증 ✓)**
— 상세 로드맵 `docs/EasyCAD_계획.md` §Phase 6.
  - **M2 #1** Undo 단일 스냅샷 저널(3-op)+Redo, **#2** 속성 dock 편집화(색·두께·선스타일·폰트) 완료(`77f9b58`~`9dbe9bb`).
  - **M2 #3 화살표 점선 + DXF linetype + Ctrl+D 복제 + 외부 CAD 두께 표시** 완료(실조건검증 ✓ 2026-07-22):
    화살표(`_ArrowItem`/`_PolyArrowItem`)에 `_style` 신설(`_color`/`_width`와 대칭) → paint·`capture_state`/
    `apply_state`·`.ecad`(하위호환 `_apply_arrow_style`)·속성 dock(`_edit_style`을 `apply_style`로 확장)·
    clone까지 연결. **몸통만 점선, 화살촉은 항상 solid**(육안 확인 ✓). DXF는 Qt스타일↔linetype 매핑
    (`DASHED`/`DOT`/`DASHDOT`/`DIVIDE`, export가 없으면 픽셀스케일 패턴으로 등록 → 버전 무관·외부 CAD 가시성).
    **Ctrl+D**=제자리 복제(`duplicate_selection`, clone+오프셋+`push_undo_add_many`, 클립보드 미오염).
    ⚠ 실조건(2026-07-22)서 2건 발견·수정: ⓐ 화살표 sticky 선스타일이 새 화살표에 미적용(화살표는
    `make_pen` 밖) → `_begin_draw` 초크포인트에서 `current_style` 스탬프. ⓑ DXF linetype이 화살표만
    실려 **pen 기반 도형(네모·선·원·심볼·펜) 점선이 왕복서 실선화** → export 5함수 `_with_linetype`,
    import `_pen`에 `_style_of` 일괄 적용. ⓒ AutoCAD가 XDATA 두께를 못 읽어 얇게 렌더 → `_wx`가
    표준 `lineweight`(px×10→enum) 병행 + `$LWDISPLAY=1`(아래 Phase 3 항목). **실조건 D ✓**(AutoCAD
    2022서 점선·모양·두께 모두 정상). ⚠ 남은 한계: 바인딩된 화살표 복제 시 사본이 원본 도형 참조(paste와 동일). **M2 #4 화살표 2종(곡선/직선) 통합=보류 결정**(deep-interview: 데이터 모델
    이질성 `_ctrl`좌표 vs 정점리스트+A*라우팅으로 1클래스 통합 시 분기지옥 → M3 이후 도구 진입점만 병합 검토).
  - **M3 빠른 편집 UX** 완료(실조건검증 ✓ 2026-07-22, 커밋 `ca71d21`~`568065d`):
    **#17 팔레트 드래그앤드롭** — 좌측 「도형·심볼」 버튼을 캔버스로 끌어 놓은 자리에 기본 크기 생성
    (`_PaletteButton` QDrag + host `_create_shape_at`, 클릭=무장/드래그=드롭 분리). ⚠ 실조건서 뷰
    (QGraphicsView)가 내부 드래그를 먼저 가로채 금지커서·드롭무시 → `_view.viewport()`에 `eventFilter`로
    직접 수신해 해결(`568065d`). **#16 우클릭 재정의** — 상태 분기: BUSY(무장·그리기중)=취소(M2 탈출구
    보존)/유휴=드래그 임계(6px) 팬·제자리 탭=컨텍스트 메뉴(복사·잘라내기·복제·삭제·붙여넣기·전체선택,
    전부 기존 편집 경로→undo 일관). `_rmb_is_busy`가 M2 취소 대상과 정확히 일치해 검증된 탈출구 보존.
    **#15 플로팅 컨텍스트 툴바** — 선택 위 미니 툴바(색 스와치·선스타일 순환·복제·삭제·화살표 방향 토글),
    속성 dock 편집 경로(#9) 재사용, 상단 침범 시 아래 반전·창 클램프, 따라다니기=selectionChanged+
    스크롤바+scene.changed(코어 무수정). 방향 토글용 `_PolyArrowItem.flip_head` 신설 + `capture_state`에
    `head` 추가(undo 가능). **화살표 곡선↔직선 통합(#4)은 계속 보류**(방향 토글만 — 데이터모델 이질성).
    **Phase 6 M3 완료.**
  - **M4 편집 정밀화 & 커넥터 고도화** 진행 — **M4-1/2/3 완료(실조건검증 ✓ 2026-07-22)**
    (커밋 `68b9c8f`·`04e11e2`·`bdb670b` + 실조건서 버그 3건 발견·수정):
    Lucid/FigJam 캡처(`C:\Users\minwoo\OneDrive\Desktop\PasteFlow`) + 사용자 요청 반영, deep-interview로
    4가지 확정(2026-07-22). **M4-1 라벨 정밀화** — 라벨-선 갭 5→2px, 수직 오프셋 3위치(선 위 0/±D)로
    스냅(공용 `_snap_label_off`), along-line 슬라이드는 자유 유지. **M4-2 빠른연결·스냅 확대** — 네방향점
    드래그=화살표만 생성(`_qc_create_arrow_only`, 클릭은 도형복제+화살표 유지) + 화살표 스냅 대상에 선·
    화살표(끝점 우선+몸통 폴백) 추가(`_border_snap_at`에 `_conn_lines` 병행, shape=None=기하 스냅만·바인딩은
    도형만, self=`_temp`·`_place` 제외). **M4-3 도형 바로 바꾸기** — 플로팅 툴바 `⬗` 드롭다운(네모·원·심볼
    6종, 단일 도형 선택 시만)으로 즉석 변환, rect·pos·회전·펜·라벨 유지 + 연결 화살표 new로 재바인딩,
    remove+create+화살표 geom을 단일 undo 엔트리로 묶음(`_swap_shape`).
    ⚠ **실조건서 발견·수정한 버그 3건(2026-07-22, 실조건검증 ✓):** ⓐ **크래시** — M4-2가 선·화살표를
    스냅 대상으로 넣으며 `_border_snap_at`이 `shape=None`을 반환하는데 바인딩 호출부 5곳(`_ArrowItem`·
    `_PolyArrowItem`의 `_move_endpoint_with_snap`·`_update_arrow_draw`·arrow/sarrow press 시작)이
    None 가드 없이 `snap[2].mapFromScene`를 호출 → 화살표 만든 뒤 근처 드래그 시 크래시. 해법: 5곳에
    `shape=None`이면 기하 스냅만·바인딩 skip(원래 의도 "바인딩은 도형만"과 일치). ⓑ **QC 스냅 안됨** —
    `_qc_create_arrow_only`이 릴리스 순간에만 스냅하고 고스트에 마커가 없어 조준 불가 → `_qc_snap_target`
    신설(테두리·포트 스냅 우선 + 커서가 도형 **내부**면 `rect().contains`로 최근접 포트 흡수, 채움 없는
    도형은 `shape()`가 외곽선만이라 `rect()`로 판정) + 고스트에 `_draw_snap_marker` 예고. ⓒ **비대칭 이탈**
    — `_rebind_arrow`(host)가 옛 도형 테두리 좌표를 그대로 new에 바인딩 → 원·평행사변형처럼 외곽선이
    안으로 든 도형에선 끝점이 떠 보임. 해법: `_nearest_border`로 new 실제 외곽선에 투영 후 `reroute`.
    스모크 3종(`test_arrow_endpoint_drag_onto_line_no_crash`·`test_qc_drag_absorbs_onto_shape`·
    `test_swap_to_asymmetric_keeps_arrow_on_outline`).
  - **M4-4 직교 커넥터 고도화 + #4 라우팅 드롭다운** 완료(실조건검증 ✓ 2026-07-22, 커밋 `2a50103`):
    `_PolyArrowItem`에 **`_routing`**(straight/ortho/ortho_curved) + 통합 경로 생성기 `_apply_routing()`
    (바인딩=A* 회피 `build_elbow`, 자유=단순 `_ortho_elbow`) 도입. **기본=곡선 엘보**(ortho_curved),
    모서리 반경 `_corner_radius()`(0=직각, `_curve_r` 조절 가능 — Lucid식 곡선값 통합 준비). `.ecad`
    직렬화 + 하위호환(옛 파일: `auto_route`→ortho / 아니면 straight, `_pts` 무손실). **세그먼트 드래그**
    — 변 중점 파란 알약 핸들(`_paint_segment_handles`, `_SEG_HANDLE_PX`)을 잡아 변 전체 수직 이동
    (`_begin_segment_drag`→끝점 보호 정점 삽입→`_drag_segment_to`→`_end_segment_drag` dedup). 뷰 경로
    (`_segment_add_at`이 ortho만 반환→press가 `_seg_drag` 시작→mouseMove/Release). 드래그가 끝점·이웃 축에
    가까우면 **일직선 스냅**(①b). 드래그 후 `_auto_route=False`(완전 수동 직교). **중간정점 사각 핸들 제거**
    (`_handle_indices`=끝점만) — 세그먼트 드래그가 중간 관리, 자유드래그로 직교 깨짐 방지. **#4 드롭다운**
    (플로팅 툴바 `⌐▾`, 단일 sarrow 선택 시 — 직선/직각/곡선, `_floating_set_routing`+geom undo). ⚠
    **실조건서 잡은 핵심 버그(⑦):** 세그먼트 편집(수동 직교, `_auto_route` off)한 커넥터가 도형 이동 시
    대각화 → `reroute`가 수동 직교 폴리라인의 **끝-이웃 변(스텁)을 직교로 리플로우**하게 수정(옛 "완전
    동결"이 원인). `reroute`는 한쪽만 바인딩돼도(`has_binding`) `_apply_routing` 재적용→straight가 엘보로
    튀던 버그도 차단. 스모크: `test_sarrow_routing_*`·`test_sarrow_segment_drag*`·`test_sarrow_*_ortho_on_move`·
    `test_floating_toolbar_routing_dropdown` 등 8종.
  - **M4-4 잔여 ⓓ·ⓑ 완료**(실조건검증 ✓ 2026-07-24):
    ⓓ **도형 내부 빈공간 이동** — 선택된 속 빈 도형(네모·원·심볼)은 내부도 클릭 영역에 포함해 가는
    테두리 조준 없이 이동(Lucid/FigJam). 믹스인에 `_interior_path()`(기본 None) + `_interior_hit_active()`
    훅을 두고 `shape()`가 합집합, 세 도형만 override(외접 박스 아니라 실제 외곽선 — 원=곡선, 마름모=마름모).
    ⚠ **그리기 도구 무장 중엔 끈다**(`_INTERIOR_HIT_TOOLS=(None,"select")`) — 뷰의 `_is_empty_area`가
    `shape()`로 판정해, 켜 두면 '도형 안에서 새 화살표·네모 그리기'가 막힌다. 러버밴드 판정은
    `_base_shape` 기준이라 무영향. ⓑ **곡선 반경 스테퍼** — 플로팅 툴바에 `0~40px` 스핀박스(곡선 엘보
    단일 선택 시만 노출, **0=직각**). `set_corner_radius`·`_CURVE_R_MAX`, `.ecad`(`curve_r`, 하위호환)·
    clone·geom undo(연속 조작은 `coalesce_key`로 1스텝) 연결. 반경 0이 직각이 안 되던 폴백
    (`or self._CORNER_R`)도 제거. ⚠ 스핀박스는 **`FocusPolicy.NoFocus` 필수** — Del·Ctrl+D·도구 숫자키는
    윈도 QAction이 아니라 뷰 `keyPressEvent`가 처리해서, 포커스를 뺏기면 그 단축키가 캔버스로 안 간다.
    스모크 8종 추가(총 177). ⚠ 검증 함정: 합성 QMouseEvent가 우리 창에선 씬으로 배달되지 않아
    (바닐라 QGraphicsView에선 정상) 아이템 grab·이동은 오프스크린서 재현 불가 → 뷰의 분기 선택까지만 검증.
    ⚠ 클릭배치(멀티정점 자유 폴리라인)는 **보수적으로 유지**(완전 제거는 옛 드로잉 테스트 6개 파손·가치
    낮음). 드래그로 그린 2정점만 직교화, 클릭배치는 수동 경로. 완전 제거 여부는 후속 판단.
  - **라우팅 모드 통합 완료**(실조건검증 ✓ 2026-07-24): `_routing`을 straight/ortho **2값**으로 축소
    (옛 ortho_curved 제거). 각짐/둥긂은 모드가 아니라 **모서리 반경(`_curve_r`, 0=직각)** 이 소유 —
    「직각 엘보」=반경0 프리셋, 「곡선 엘보」=반경>0. paint 분기도 `_corner_radius()>0`으로 바꿔 반경0이면
    옛 「직각」과 완전히 같은 폴리라인 코드로 그린다(같은 그림 두 코드 중복 해소). ⚠ 하위호환: 옛 `.ecad`의
    `routing:"ortho"`(옛 직각)는 반경 0으로 읽어야 안 둥글어진다 → `curve_r` 키 없으면 옛 "ortho"=0,
    "ortho_curved"=기본반경. `set_routing("ortho_curved")`는 ortho 별칭. 반경 스테퍼는 직교 커넥터면 항상 노출.
  - **화살표 도구 통합 완료**(실조건검증 ✓ 2026-07-24) — 사용자 UI 원칙(memory `ui-simplicity-principle`:
    상단 툴바에 종류를 두지 말고 선택 후 컨텍스트 하위목록에서). **상단 툴바 화살표 버튼 1개**(sarrow 버튼
    제거), 종류(직선·곡선·직각)는 선택 후 **미니툴바 `⌐▾`**에서 고른다. **각짐 조절(반경 스테퍼)은 직각일
    때만** 노출. 내부 구조는 클래스 통합 아님 — 직선·곡선은 `_ArrowItem` 두 상태(제어점 없음/있음,
    `apply_straight`/`apply_curved`), 직각은 `_PolyArrowItem`. 종류 전환: 직선↔곡선=같은 객체 상태변경
    (곡률 기억), ↔직각=M4-3식 클래스 교체 `_swap_arrow`(색·두께·선스타일·머리·라벨·연결 이전 + 단일 undo,
    곡률·경유힌트 초기화·Ctrl+Z 복구). 종류 **sticky**(`current_arrow_kind`, 최초=곡선), 반경도 sticky
    (`current_curve_r`) — `_begin_draw` 초크포인트서 스탬프. 그리기 진입점 `arm_arrow_tool`(종류→내부 도구:
    곡선·직선=arrow, 직각=sarrow); `set_tool`은 리터럴 유지(테스트·내부 호출 무영향). 직선 종류로 그리면
    도형 스냅 자동 S자도 `_apply_arrow_kind_on_create`로 곧게 폄. 단축키 **3만** 화살표(9 해제 — 도구 하나면
    키 하나). reroute·`.ecad`·DXF는 타입 불변이라 영향 0(스캔 방식). 스모크 총 182.
    ⚠ **핀 버그(실조건서 발견·수정):** 도구 핀 켠 채 종류를 바꾸면 `current_arrow_kind`만 갱신되고 무장된
    `current_tool`은 그대로라 다음 화살표가 옛 종류로 그려졌다 → `_floating_set_arrow_kind`가 화살표 도구
    무장 중이면 새 종류로 재무장. 스모크 `test_arrow_kind_change_rearms_pinned_tool`.
    **남은 것:** ⓐ 관통·재진입은 아래 항목서 완료 — 경로가 도형 변을 **'타는'(관통 아닌 나란히) 미세
    케이스만** 남음(우선순위 낮음). ⓒ 곡선 화살표
    베지어의 **진짜 클래스 통합**은 하지 않기로 확정(사용자 화면 차이 0인데 분기지옥·회귀 위험만 큼 — UI
    통합으로 목적 달성). 미니패널 색 스와치 5개→버튼 1개 등 추가 통합은 같은 UI 원칙으로 후속.
  - **연결도형 재진입 회피 + 라이브 직각 그리기 완료**(실조건검증 ✓ 2026-07-24, 커밋 `1bf9f4e`) — M4-4
    잔여 ⓐ의 관통/재진입 부분. 직교 커넥터(`_PolyArrowItem`)가 연결된 도형으로 **재진입**하던 문제를
    보수적으로 회피: `_route_ortho(conn_rects=)` — 연결 도형은 끝점이 테두리 위라 통짜 팽창 장애물로 못
    넣는 deferred 함정을, **'재진입만 원본 rect로 판정'**(부착부 바깥 스텁 접촉은 통과) + **stub↔stub A*엔
    팽창본을 장애물로** 넣어 우회. 재진입 없으면 conn 무시 = 기존 경로 완전 불변(무회귀). 변 붙음은
    `_CONN_CLEAR_MULT=3`(36px)로 우회 여유+스텁 거리 확대(제3도형 12px·무재진입 경로 불변). **라이브 직각
    그리기:** 직각 화살표 드래그 중에도 릴리스와 동일한 회피 경로로 미리보기 — `set_ortho_preview`가
    릴리스가 쓰는 `_apply_routing`에 위임 + **tip이 도형에 스냅되면 라이브 바인딩**(끝점이 테두리 위라 conn
    처리돼야 A* 도착노드 유효 — 미바인딩이면 팽창 안에 도착점이 들어가 A* 실패→단순엘보 폴백=옛 관통버그).
    `_apply_routing` 자유분기도 한쪽만 바인딩되면 `_route_ortho`로 회피(일관). 릴리스·클릭배치 진입 시
    미리보기 정점을 **2점으로 되돌려** `_bind_poly_ends`의 `len==2` 자동라우팅 경로 보존(3점↑=수동 폴리라인
    오인 방지). 스모크 3종(`test_sarrow_avoids_reenter_connected_shape`·`test_sarrow_live_ortho_preview`·
    `test_sarrow_live_preview_avoids_reenter`, 총 185). ⚠ 한계: 원·심볼은 bbox 근사라 외곽선이 안으로 든
    경우 재진입은 preferred 폴백(회귀 아님).
  - **M5 정렬 / 분배 완료**(실조건검증 ✓ 2026-07-26) — 계획서 §5 #4 미흡수분. 정렬 6종(왼쪽·가로
    가운데·오른쪽·위·세로 가운데·아래) + 균등 분배 2종(가로·세로). 기준은 **선택 bbox**(Qt가 선택
    *순서*를 보장하지 않아 '먼저 고른 객체 기준'은 불가), 분배는 중심 간격이 아니라 **여백**을 균등화
    (크기가 달라도 보이는 틈이 같게), 3개 미만 no-op. 진입점은 UI 원칙대로 상단이 아닌 선택 후 컨텍스트
    2곳 — 미니툴바 `≡▾` 드롭다운 + 우클릭 「정렬 / 분배」 서브메뉴(대상 2개 이상일 때만 노출).
    이동만이라 `push_undo_move` 한 엔트리로 복원. **대상 규칙**: 연결된 화살표 제외(도형이 움직이면
    reroute가 따라오므로 화살표까지 옮기면 그 이동이 덮어써지고 기준 bbox만 흐트러진다)·용지틀 제외·
    자식 아이템(라벨) 제외. 동기 검증: 축 40px 어긋난 두 도형의 직교 커넥터 계단이 「세로 가운데」 한 번에
    0이 됨(`test_align_removes_connector_stair`) — 코어 Stage4가 8px까지만 흡수하던 그 문제.
    ⚠ 함정 3건: ⓐ **`sceneBoundingRect()`는 정렬 기준으로 못 쓴다** — 코어 boundingRect가 선택·회전
    핸들과 빠른생성 도트 자리를 상시 예약해 도형마다 여백이 다르다(26px vs 19.75px 실측) → `_content_rect`
    기반 `_align_rect`(회전은 `mapToScene`로 흡수). ⓑ 라벨(`_ConnectorLabel`)도 selectable·movable이라
    러버밴드에 딸려 오는데 위치를 부모가 소유(재투영)하고 moveBy 델타 좌표계도 다르다 → 자식 제외.
    ⓒ **그룹 선택 박스는 뷰 `drawForeground`가 그린다** — Qt는 움직인 아이템 bbox만 무효화하므로
    프로그램 이동(정렬·분배·undo) 뒤 옛 점선이 남는다 → `_repaint_overlays()` 연결. **이 잔상은
    오프스크린 렌더로 재현 불가**(`render()`가 전면 재도색) — 실조건서만 드러났다. 스모크 8종(총 193).
  - **M4-4 ⓐ 최종 잔여(변타기/관통) 완료(실조건검증 ✓ 2026-07-27, 커밋 `75c60c6`)** — 계획서가
    "우선순위 낮음"으로 뒀던 도형 변 타기(관통 아닌 포개짐)를 실측하니 관통 56/768(7.3%)·타기
    48/768(6.2%)로 무시할 수준이 아니었다. `_route_ortho`를 단조 개선 구조로 재설계(base를 엄격히
    이기는 후보만 채택 + 연결도형 clearance 사다리 36→12→1→0px) → 합성 768케이스·실도면 재진입·
    타기 모두 0. 실조건서 사용자가 추가로 잡은 버그 2건도 같은 라운드에서 해결: ⓐ 스냅 동점(포트=
    화살표 끝점 거리 0)에서 화살표가 도형 포트를 이겨 바인딩을 잃던 것(`<=`→`<`) ⓑ Stage3(화살표-
    화살표 soft 회피) 철회 — 경로가 '다른 화살표 집합'에 의존해 화살표를 지우면 무관한 화살표
    경로가 재계산됐다(대가: 실도면 교차 3→7, 수동 정렬/분배로 회수).
    **이어서 실조건서 부착점 이탈·흔들림 2건 추가 발견 → Stage4(`_absorb_near_alignment`) 철회** —
    8px 이하 축 어긋남을 없애려 **부착점(사용자 데이터) 자체**를 테두리 따라 미끄러뜨리던 게
    원인(그림 문제를 데이터를 고쳐 풀면 안 된다는 계층 오류). 대가: 어긋남 ≤8px가 계단으로 재출현
    (M5 정렬/분배로 회수). 스모크 193→203종.
    **재부착 추종 실패 버그 완료(실조건검증 ✓ 2026-07-27)** — 화살표를 뗐다가 도형 변의 중심점이
    아닌 곳에 재부착하면 도형을 옮겨도 안 따라오던 문제. 앞선 2회 시도(F8/Shift `set_bound` 누락
    수정, `_rebind_at_fixed_point`)는 실제 원인이 아니었음(그 수정 자체는 별개로 정당해 유지) —
    규칙 11-b 스턱루프 트립와이어 발동 후 임시 디버그 로깅(`_dbg_rebind`, 파일 flush)으로 실제
    마우스 이벤트를 그대로 캡처해 확정. **근본원인**: `_endpoint_border_snap`이 `_border_snap_at`
    (선·화살표 몸통 스냅 지원, M4-2b)에 `exclude`를 안 넘겨, 재부착 드래그 중 화살표가 **도형이
    아니라 자기 자신의 다른 구간**에 스냅될 수 있었다 — 그 경로는 바인딩을 만들지 않는 "기하만"
    스냅이라, 릴리스 지점이 도형 바로 옆이라 시각적으로 붙어 보여도 실제 바인딩은 None으로 남았다.
    로그의 릴리스 좌표가 도형과 무관한 부동소수 계산값인 것으로 확정(예: raw 드래그 좌표가 아닌
    자기 몸 위 투영점). 수정은 `exclude=self` 전달 한 줄(`_endpoint_border_snap`). 스냅·바인딩·
    직교라우팅 회귀 78종 + 전체 스모크 203종 통과, 사용자 GUI 재확인 완료. 디버그 로깅은 원인
    확정 후 전량 제거.
  - **기본 펜 두께 6px→1px 완료**(`ce17ac8`) — CAD 관행에 맞춰 새 도형·선·화살표 기본 두께를
    최소값으로. 클릭 판정(`_EDGE_HIT_MIN` 8px)은 두께와 무관해 선택성 불변. 실화면 시인성은 미검증
    (오프스크린은 픽셀 시각확인 불가).
  - **팔레트 드래그 실물 미리보기 + 무한캔버스 스크롤바 숨김 완료**(`4bd2b5a`) — 팔레트 도형을
    캔버스로 끌 때 고정 아이콘 대신 현재 색·두께·줌 배율을 반영한 실제 렌더를 드래그 픽스맵으로
    사용(`_render_drag_preview`). 무한캔버스 스크롤바는 씬이 사실상 무한이라 `ScrollBarAsNeeded`도
    상시 표시돼 시각 잡음만 되던 것을 `AlwaysOff`로 전환(팬은 손모드 드래그로 이미 구현돼 있어
    스크롤바 정책과 무관). Rejected: 캔버스 위 실시간 고스트 프리뷰 | 뷰 페인트 이벤트 개입 필요해
    드래그 픽스맵 교체보다 손이 훨씬 많이 감.
  - **화살표 상단바 클릭 → 종류 메뉴 즉시 선택 완료(실조건검증 ✓ 2026-07-27, 커밋 `6bab273`·
    `968c920`)** — 사용자가 상단바에 화살표 종류(직선·곡선·직각) 선택 진입점이 없다고 지적해
    진행(2026-07-24 화살표 통합 원칙 유지: 세부 편집은 여전히 미니툴바). 처음엔 split-button
    (▾ 드롭다운)으로 구현했으나 "아이콘도 작은데 ▾ 조준이 힘들다"는 GUI 피드백으로
    `QToolButton.InstantPopup`(버튼 전체 클릭=메뉴)으로 교체 — 클릭 한 번의 즉시무장 단축경로는
    사라지는 대신 키보드 **3**(`arm_arrow_tool` 직결)이 그대로 대신한다. ⚠ 실조건서 버그 발견·수정:
    직선 종류를 고르고 드래그해 그리면 릴리스 전까지는 도형 스냅 자동 S자로 보이다 뗄 때만 곧게
    펴져 미리보기≠결과였다 — `_update_arrow_draw`(라이브 드래그)가 sticky 종류를 안 보고 항상
    자동 S자 곡률을 계산한 게 원인(`_apply_arrow_kind_on_create`는 릴리스에만 관여). 드래그 중에도
    sticky 종류가 '직선'이면 즉시 곧게 그리도록 통일. 스모크 203→204종.
  - **편의기능 5종 완료(실조건검증 ✓ 2026-07-27, 커밋 `0b980b7`)** — deep-interview로 확정
    (Z-order/Group/Lock 3개는 AskUserQuestion 추가 승인). **Alt+드래그 복사** — press 시 선택
    항목을 제자리 clone해 Qt 기본 히트테스트가 clone을 잡게 하는 방식(grabber 직접 조작보다
    견고 — offscreen에서 clone이 top+selected임을 실측 확인). **Shift+드래그 축 고정** — 첫
    유의미한 편차 방향으로 축을 고정(스마트 정렬 스냅보다 우선). **Z-order**(`Ctrl+]`/`Ctrl+[`
    맨앞/맨뒤) · **Group/Ungroup**(`Ctrl+G`/`Ctrl+Shift+G`, 평면 비중첩 — selectionChanged로
    멤버 동반선택) · **잠금**(`Ctrl+L`, `ItemIsMovable`/`ItemIsSelectable` 플래그를 직접 꺼서
    이벤트 핸들러 개별 체크 불필요)은 undo 저널의 기존 "mut" 메커니즘에 z/group/lock sub 타입
    추가로 재사용. `.ecad`에 `locked`/`group_id` 직렬화. Rejected: Z-order 한 단계씩 이동
    (범위 밖, 맨앞/맨뒤로 충분) · 중첩 그룹(데이터모델 복잡도 대비 가치 낮음). 스모크 204→217종.
    ⚠ 이 커밋의 Ctrl+Shift+G(그룹 해제)가 Mermaid 가져오기와 충돌해 죽은 코드였던 것은 바로
    아래 "중간점검" 항목에서 발견·수정.

**중간점검(기존 기능 점검) 2026-07-27 — 버그 6건 발견·수정, 실조건검증 대부분 ✓, 스모크 217→229종.**
사용자 요청으로 "4대 영역(기존기능/코드정리/디자인/신규기능) 중 기존 기능 점검부터" 진행.
정적 스캔 + 사용자 GUI 실사용 피드백 병행으로 발견:
  - **복제/붙여넣기 계열 바인딩 유실 3건**(`89a855b`·`0253182`·`d507ca0`) — Ctrl+D·복사/붙여넣기·
    Alt+드래그 세 진입점 전부에서 clone()이 `_bind1`/`_bind2`(화살표)·`_group_id`(그룹)를 원본
    참조/값 그대로 복사해, 도형+화살표를 함께 복제하면 사본 화살표가 원본 도형에 남고, 그룹을
    복제하면 사본이 그룹 해제됐다. `remap_grouped_bindings`·`regroup_duplicated_items`(둘 다
    annotator_core.py, 세 진입점 공유)로 해결. 실조건검증 ✓.
  - **Ctrl+Shift+G 단축키 충돌**(`399416e`) — Mermaid 가져오기 QAction과 뷰 raw keyPressEvent의
    그룹 해제가 같은 단축키라 QAction(WindowShortcut)이 항상 이겨 그룹 해제가 죽은 코드였음
    (오프스크린 테스트는 view.keyPressEvent 직접호출이라 이 우선순위를 우회해 못 잡았음). Mermaid를
    Ctrl+Shift+F로 재배정 + `test_no_duplicate_window_action_shortcuts`(전역 QAction 단축키 중복
    정적 검사)로 재발방지. 실조건검증 ✓.
  - **다중선택 빈틈 드래그 이동 + 그룹 상태메시지**(`e15ff08`) — 사용자 피드백: 여러 도형 선택 시
    바운딩박스 안이라도 실제 도형이 없는 빈틈은 이동 안 됨(Qt 히트테스트가 개별 도형 위만 잡음).
    `_group_body_area_at`/`_group_body_drag`로 그룹 바운딩박스 전체를 이동 영역으로 확장(Shift+
    드래그는 기존 러버밴드 그대로). 그룹/해제 시 상태바 메시지 추가(조용히 바뀌어 인지 어렵다는
    피드백). 실조건검증 ✓.
  - **빠른연결(네방향점 드래그) 화살표 직각 기본화 + sticky 반경**(`08796e5`·`86be836`) — 도형
    변점을 다른 도형으로 드래그해 화살표를 만들 때 도착점이 정확히 안 붙으면(자유 끝) 2점 직선으로
    영구히 남던 버그. `_qc_create_arrow_only`가 `_apply_routing()`에 위임하도록 수정(`_auto_route`
    항상 True) + 미니툴바 곡선 반경 sticky 값(`current_curve_r`)도 `_begin_draw`와 동일하게 스탬프.
    실조건검증 ✓(반경 유지 확인).
  - **A* 라우터 불필요한 우회('혹') + QC 미리보기≠확정**(`12f807f`, 별도 세션에서 진행) — 사용자가
    실사용 중 GUI 스크린샷으로 제보(도형 변 포트 연결 시 화살표가 위로 갔다 다시 내려오는 혹 발견).
    두 가지 근본원인: ⓐ `_route_ortho`가 재진입회피 A*의 가장 넉넉한 clearance(conn_clear) 첫
    결과를 결함없다는 이유만으로 조기채택해, 더 짧은 경로를 찾는 clearance 사다리(36→12→1→0px)가
    실행될 기회를 못 얻었다 → 조기 반환 제거(사다리는 단조개선이라 무회귀). ⓑ QC 고스트 미리보기
    (`_qc_paint_ghost`)가 장애물·재진입 회피 없는 `_ortho_elbow`만 써서 릴리스 시 실제 경로와
    달랐다 → `_qc_route_context` 헬퍼로 고스트도 `_route_ortho` 사용(sarrow의 `set_ortho_preview`와
    동일 패턴). Rejected: `set_ortho_preview`에 start_shape 바인딩 추가(다른 코드경로가 이미
    처리 중이라 불필요 + 회귀 유발, QTest 재현으로 확인 후 폐기). Confidence high, Not-tested:
    실제 물리 마우스(합성 이벤트로 대체), 사다리 상시화의 대규모 도면 성능.
  - **재현 파일**: `C:\Users\7make\Desktop\123.ecad` 사용자 실도면 — 재현·회귀 스모크 근거.

**디자인 개선 1차(상단바·플로팅 툴바 정리) 완료(2026-07-28, 커밋 `b9fa323`)** — 사용자
인터뷰(아티팩트 시안 검토) 결과 반영. 상단바에서 PDF/DXF 내보내기·가져오기·이미지·표·표제란·
Mermaid 7개 버튼 제거(이미 파일 메뉴에 있어 중복, 단축키 불변). 플로팅 컨텍스트 툴바는
정렬/분배·복제·삭제를 빼고 겉모습 계열(색·스타일·도형바꾸기·화살표종류·반경·방향뒤집기)만
남김 — Figma/Lucid/Excalidraw 관례대로 "스타일은 상시 패널, 액션은 우클릭"으로 역할 분담
(세 액션은 우클릭 메뉴·Ctrl+D·Del로 계속 접근 가능, 기능 손실 없음). 실조건은 마우스 조작
느낌만 미검증(배치는 오프스크린 확인).

**코드정리 진행(2026-07-28)** — 정적 스캔 사전진단 기반 순수 리팩터링(시각·동작 변경 없음,
스모크로만 검증, `python run.py` 실조건은 생략).
  - **1순위** Stage3 잔재 dead code 정리(`cce126f`) — 화살표-화살표 soft 회피(Stage3,
    2026-07-26 철회)의 얇은 집계 래퍼 `_count_seg_crossings`가 호출부 3곳(`_route_score`·
    `_route_ortho` 2곳)을 감싸기만 할 뿐 다른 곳에 안 쓰여 각 호출부에 인라인. `avoid_segs`/
    `cross_penalty` 재도입 훅은 보존(삭제 시 재도입 경로 소실).
  - **2순위** rect 기반 도형 5클래스 기하 리베이크 중복 → 믹스인 추출(`c3a96b1`) —
    `_RectItem`·`_EllipseItem`·`_SymbolItem`·`_ImageItem`·`_TableItem`이
    `_capture_geom_local`·`_apply_geom_local`·`rebake_scene`·`_stretch_grips` 4메서드를
    byte-for-byte 동일하게 중복 정의하던 것을 `_RectGeometryMixin`(`_HandleResizeMixin`과
    도형 클래스 사이 MRO)으로 흡수. `rect()` 존재 전제라 비rect 기하(`_LineItem`·`_PathItem`·
    `_ArrowItem`·`_PolyArrowItem`)는 대상 아님. 스모크 229종 전 구간 통과.
  - **3순위** `apply_color`/`apply_width`·`paint()`·`_font_px` 중복 흡수(`02ffc73`) —
    `_ArrowItem`·`_PolyArrowItem`·`_BadgeItem`의 `_color`/`_width` 분기를
    `_HandleResizeMixin`의 기존 pen 분기 옆에 hasattr 분기로 추가(`_stroke_width`가 이미
    쓰던 패턴과 동일). `_LineItem`·`_PathItem`의 동일한 paint() 오케스트레이션을 믹스인
    기본 `paint()`로 승격. `_TitleBlockItem`·`_TableItem`의 `_font_px` 정적 헬퍼를 모듈
    레벨 함수로 추출. `apply_style`은 의도적으로 제외 — host.py가
    `hasattr(it,"apply_style")`로 "화살표냐 pen 기반 도형이냐"를 가르는 분기 신호로 써서,
    믹스인에 기본 구현을 얹으면 pen 기반 도형의 점선 적용이 조용히 깨진다. `_pixmap_from_data`/
    `_to_png_full`(dead code로 보임)도 삭제하지 않음 — docstring이 "clipboard_monitor와
    동일 로직"을 언급해 계획서 후속 항목 "클립보드 이미지 붙여넣기"(미구현)용 스캐폴딩일
    가능성이 높음. 스모크 229종 전 구간 통과.
  - **4순위** 미사용 `_EditorMixin` 잔재 ~700줄 삭제(`794aeab`) — annotator_core.py 최하단
    "편집기 다이얼로그" 섹션(`_DragBar`·`_ColorPalettePopup`·`flatten_scene_to_png`·
    `_EditorMixin`)이 pasteflow 원본 독립 스크린샷 편집기의 호스트 계약 구현으로, 이 프로젝트
    어디서도 상속·호출되지 않음을 확인(`_AnnotatorView`가 `self._owner`에 기대하는 계약을
    host.py의 `CanvasWindow`가 이미 독립적으로 전부 구현 — host.py 자체 주석이 "무거운
    `_EditorMixin` 대신 무한캔버스에 맞는 CanvasWindow를 새로 만들었다"고 명시). 삭제가 만든
    고아(`QBuffer`/`QIODevice`/`time` import, 모듈 최상단 stale docstring)도 함께 정리.
    스모크 231종 전 구간 통과 + `CanvasWindow` 생성/표시 확인.

**신규기능 — 클립보드 이미지 붙여넣기 완료(2026-07-28, 커밋 `7baf69b`, 실조건검증 ✓)** — 위
코드정리 3순위에서 찾은 `_pixmap_from_data`/`_to_png_full`을 실사용 경로에 연결. host.py에
`_clipboard_pixmap()`(Qt `pixmap()`/`image()` 우선, raw 포맷만 `_pixmap_from_data` 폴백)
신설 + `_insert_image_at`에서 `_insert_pixmap_at(pm, scene_pos, msg)`를 추출해 파일삽입·
드래그드롭·클립보드 붙여넣기가 공유. `paste_selection()`은 내부 붙여넣기 버퍼가 비어 있을
때만 시스템 클립보드 이미지로 폴백(Ctrl+V 하나 공유, 기존 Ctrl+C/Ctrl+D 동작 불변). 스모크
231종(신규 2종 포함) 통과 + 자체렌더 스크린샷으로 배치·선택·종횡비 확인. **실조건검증 ✓**
(2026-07-28, 사용자가 외부 스크린샷 도구로 캡처한 이미지를 `Ctrl+V`로 정상 붙여넣기 확인).
⚠ 실조건에서 파생 버그 2건 발견·수정(연쇄, 둘 다 실조건검증 ✓) — ⓐ(`a1146ab`) 붙여넣은
이미지가 자동 선택되며 플로팅 툴바가 뜨는데, 색상 스와치·선스타일 버튼이 `_ImageItem`/
`_TableItem`(둘 다 NoPen + 자체 고정 색)에도 노출돼 눌러도 시각 효과가 없었다 →
`_reposition_floating_toolbar`에 다른 버튼들과 동일한 isinstance 기반 가시성 규칙 추가
(선택 전부가 이미지/표일 때만 숨김). ⓑ(`4783a4a`) ⓐ 수정 후에도 그 자리에 빈 프레임
(배경+테두리)의 작은 사각 흔적이 남는 것을 사용자가 재발견 — 버튼별 가시성만 계산하고
`bar.setVisible(True)`는 무조건 실행되던 게 원인. 색상계열·방향·도형교체·라우팅·반경
5개 플래그가 전부 False면 위치 계산 없이 바 전체를 숨기도록 조기 반환 추가(맨 위
"선택 없음" 분기와 동일 패턴). ⚠ 이 흔적은 오프스크린 렌더로 재현 안 됨(네이티브 위젯
최소크기 차이로 추정) — 실조건서만 드러난 케이스.

**신규기능 — 그리드/스냅투그리드 완료(2026-07-28, 커밋 `16c7551`, 실조건검증 ✓)** —
`docs/EasyCAD_계획.md` "후속(Phase 6 이후/낮은 우선)" 백로그 항목. deep-interview(2026-07-28)로
확정: 씬 단위 고정 간격(20유닛, 줌에 비례해 화면 밀도 변화 — CAD/Figma 관행) + 점 격자(이 프로젝트가
이미 '점'을 UI 언어로 씀 — 빠른생성 도트·포트 점·스냅 마커) + 표시·스냅 통합 토글(`Shift+G`, F3/F8과
같은 관례, 기본 켜짐) + 드래그 중 **항상 양자화**(임계값 없음 — 스마트정렬의 '임계 내만 당김'과 다른
성격). 우선순위 **축고정(Shift) > 스마트정렬 > 격자스냅**: 스마트정렬이 맞춘 축(`_align_guides`에
"v"/"h" 존재)·축고정이 고정한 축은 skip_x/skip_y로 건드리지 않는다. **화살표류는 스코프 밖** —
테두리/포트 스냅이 항상 우선이어야 하는 커넥터라 격자가 끼어들면 지속연결이 어긋난다.
적용 범위: 도형 이동(`_apply_grid_snap_move`, 단일선택만 — 스마트정렬과 동일 관례로 다중선택 제외)·
박스 리사이즈(`_HandleResizeMixin._grid_snap_local`, `mapToScene`/`mapFromScene`로 아이템 회전·
스케일 변환을 통과시켜 회전된 도형도 코너가 정확히 격자에 맞음)·새 도형 생성 드래그(`_grid_snap_scene`,
`_cur_point` + 시작점(mousePressEvent) 양쪽 다 스냅해야 시작 모서리가 격자 밖에 남는 어긋남을 피함).
표시는 `_AnnotatorView.drawBackground`(점 격자, 화면 밀도가 `_GRID_MIN_PX`(4px) 미만이면 자동 숨김
+ 점 개수 상한 `_GRID_MAX_DOTS`(6000) 세이프가드로 극단적 줌·창크기 조합에서도 프레임 랙 방지).
프레임 챌린지(deep-interview 막판): "이 프로젝트가 최근 계속 시각 잡음을 줄여왔는데 점 격자 상시
표시가 역행 아닌가" — 검토 결과 지금까지의 잡음 줄이기는 **UI 크롬**(버튼·패널) 대상이었지 캔버스
내용 자체(용지틀·표처럼 작업 기준선 역할)는 아니었다고 판단, 원래 결정(점 격자 상시 표시) 유지.
스모크 15종 추가(총 247) + 자체 스크린샷(`tools/screenshot.py`)으로 다크·라이트 둘 다 격자 시인성
확인. ⚠ 기존 스모크 3건(`test_box_corner_resize` 계열·`test_hybrid_two_click_shapes`·
`test_symbol_draw_via_tool`)이 grid 기본 켜짐과 충돌 — 격자 밖 좌표(예: 90은 20 격자에서
`round(90/20)`이 banker's rounding으로 80이 됨)를 쓰던 순수 로직 테스트라 `grid_enabled = False`로
격자와 분리해 격자 자체 검증(신규 테스트)과 역할을 나눴다. Rejected/Not-tested는 커밋 `16c7551`
트레일러 참조. **실조건검증 ✓**(2026-07-28, 아래 이동 스냅 버그 수정 후 사용자가 `python run.py`로
격자 표시·스냅 감각 확인).
⚠ **함정(self-review로 발견·수정, 커밋 `9b3515e`):** 이동 스냅 초안은 `item.pos()`를 직접 격자로
당겼는데, 마우스로 그린 도형은 로컬 rect가 클릭 시점 씬 좌표를 그대로 품고(`QRectF(sp, sp)`)
`pos()`는 (0,0)에 남는 게 보통이라(실측: `rect(300,50,100,60)`인데 `pos()=(0,0)`) `pos()`만
맞춰도 실제 화면 위치는 격자 밖일 수 있었다. 1차 재수정(아이템 로컬 원점 `(0,0)`을 `mapToScene`)도
같은 함정(그 점은 `pos()`와 동치일 뿐 실제 그려진 도형과 무관) — 실측으로 확정한 뒤
`_apply_smart_snap`과 동일하게 `_content_rect()` 좌상단의 `mapToScene` 값을 기준점으로 삼고
`moveBy`로 적용해야 한다.

**신규기능 — 미니맵 완료(2026-07-28, 커밋 `bd9637d`, 실조건검증 ✓)** — 무한캔버스
큰 도면 탐색용. deep-interview(2026-07-28)로 확정: 독립 dock 패널(도형·속성 dock과 같은 UI
언어) + **클릭/드래그로 메인 뷰 이동**(읽기전용 아님 — 이게 미니맵의 핵심 가치). 프레임 챌린지
통과: `Ctrl+9`(전체맞춤)와 달리 **줌 레벨을 유지한 채** 다른 영역으로 점프하는 가치가 실제로
필요하다고 확인. 구현(`_MinimapView`, `host.py`): 메인과 **같은 `QGraphicsScene`을 공유**하는
두 번째 `QGraphicsView`(규칙 2 손안의 카드 — Qt 멀티뷰가 내용 변경 자동반영을 이미 제공, 별도
캐시·갱신 로직 불필요) + `setInteractive(False)`로 자체 선택/드래그 차단(클릭=내비게이션 전용) +
페인트마다 `itemsBoundingRect`로 재-fit(도면이 자라도 항상 전체가 보임) + `drawForeground`로
메인 뷰포트 사각형 오버레이(다크/라이트 accent색). 메인 뷰의 줌·팬·리사이즈는 `scene.changed`를
안 타는 순수 뷰 변환이라 미니맵이 자동으로 못 알아채 — `CanvasWindow`가 5개 지점(휠줌·`Ctrl+0`·
`Ctrl+9`·스크롤바 x2·창 리사이즈)에서 명시적으로 `viewport().update()`. ⚠ 함정(자체 스크린샷으로
발견·수정): 처음엔 하단(Bottom, 창 전체 폭)에 얇게 뒀더니 뷰포트 종횡비가 극단(≈9:1)이라
`fitInView(KeepAspectRatio)`가 가로로 크게 레터박스돼 인디케이터 사각형이 실제보다 훨씬 작아
보였다 → 속성 dock 아래(우측 열, `splitDockWidget`)로 옮겨 폭을 좁고 세로로 긴 문서 비율에
가깝게 만들어 해결. Rejected: 캔버스 모서리 고정 오버레이 | 메인 뷰의 복잡한 마우스 이벤트
파이프라인(우클릭 재정의·러버밴드·빠른생성)과 충돌 위험. 스모크 5종 추가(총 253). Not-tested:
대형 도면(수백 아이템)에서 드래그 중 매 페인트 재-fit 성능, 실조건(`python run.py`) 미확인.
⚠ **함정(실조건 스크린샷 2차례로 발견 — 1차 수정은 틀렸음, 최종 근본원인 커밋 `48b9160`):**
사용자가 `python run.py`로 인디케이터가 실제 보이는 영역과 다른 자리에 그려지는 것을 스크린샷으로
제보. **1차 진단(커밋 `2bd6827`, 틀림):** `_refresh_minimap()` 훅이 창 리사이즈·줌·스크롤바뿐이라
dock 스플리터 드래그로 뷰포트만 바뀌는 경우 안 걸린다고 보고 `eventFilter`에 `QEvent.Type.Resize`
분기를 추가했으나 — 사용자가 **같은 증상을 다시 보고**(규칙 11-b 스턱루프 트리거). **진짜 근본원인:**
`drawForeground`의 painter는 Qt가 이미 **씬 좌표계**로 매핑해 넘긴다(`QGraphicsItem.paint()`의
로컬 좌표계와 같은 설계 — offscreen 프로브로 실측 확인: `drawForeground`의 `rect` 인자가 뷰 픽셀이
아니라 `fitInView`된 씬 범위 그대로였음). 인디케이터 코드는 메인의 가시 영역(씬 좌표)을
`self.mapFromScene()`으로 미니맵 **픽셀** 좌표로 또 변환한 뒤, 이미 씬 좌표계인 painter에 그 픽셀값을
그렸다 — **이중 변환.** 데모 씬은 좌표값이 우연히 뷰 픽셀 크기와 비슷한 자릿수라 자체 스크린샷
검증(오프스크린)을 통과했지만, 원점에서 먼 좌표에 그린 실사용에서는 완전히 어긋났다 — **폴링으로는
못 고치는 종류의 버그**(매번 같은 잘못된 값을 다시 그릴 뿐이라 1차 수정 방향이 원천적으로 틀렸음).
**교훈:** 같은 증상이 재발하면 트리거(언제 다시 그리는지)를 의심하기 전에 **핵심 계산 자체**부터
다시 검증한다 — 트리거만 좁혀가는 건 계산이 이미 맞다는 전제가 틀렸을 때 헛수고다. 해법: 씬 좌표를
그대로 그린다(`mapFromScene` 제거). dock 리사이즈 이벤트 훅(1차 수정)은 근본원인은 아니었지만
부작용 없어 유지, 폴링(200ms 타이머)도 안전망으로 유지. Confidence: high(프로브로 좌표계 실측 +
원점에서 먼 좌표 재현 테스트로 버그·수정 모두 검증). **실조건검증 ✓**(2026-07-28, 좌표 수정 후
사용자가 `python run.py`로 인디케이터 위치 정상 확인).
**UX 후속(2026-07-28, 커밋 `983dd94`)** — 인디케이터 반투명 파란 채움이 미니맵 속 도형을 뿌옇게
가려 시인성이 나쁘고, 테두리색이 dock 제목줄 밑 accent 선(`#54a9ff`/`#1f7ae0`)과 같아 서로 다른
UI 요소인데 헷갈린다는 사용자 피드백 → 채움 제거(테두리만) + 테마·accent와 무관한 고정 시안
(`#22d3ee`)으로 교체.

**신규기능 — 스타일 복사(format painter) 완료(2026-07-28, 커밋 `7b135bf`, 실조건검증 ✓)** —
백로그 §5 항목 5의 마지막 절반(그리드·미니맵은 앞서 완료). deep-interview(2026-07-28)로
확정: **복사/붙여넣기 방식**(우클릭 메뉴 + `Ctrl+Alt+C`/`Ctrl+Alt+V`) — Office의 페인터모드 커서
(다음 클릭을 가로채는 새 도구 모드) 대신 기존 선택·우클릭메뉴·undo 인프라를 그대로 재사용해
구현비용을 낮췄고, 다중선택 붙여넣기로 "여러 도형에 연속 클릭 적용"이라는 페인터모드의 핵심
가치도 사실상 커버됨(deep-interview에서 트레이드오프로 확인). 범위: 색·두께·선스타일·폰트크기·
텍스트색·텍스트배경·화살표방향 — **텍스트 내용은 제외**(일반적 서식복사 관례, 실수로 글자가
덮어써지는 사고 방지). **타입이 달라도(네모↔화살표 등) 항상 적용** — 도면이 도형+화살표가 섞여
있어 이게 실용적이라는 사용자 판단. 프레임 챌린지 통과: 속성 dock 다중편집(이미 존재)과 달리
"정확한 값을 몰라도 그대로 옮긴다"는 가치가 실제로 필요하다고 확인. 구현: 색·두께·선스타일·폰트는
속성 dock이 이미 쓰는 `_read_props`(pen 기반↔화살표 duck-typing 정규화)를 그대로 재사용(규칙 2
손안의 카드) + tcolor·bg·head(화살표 방향)만 `_capture_paint_style`/`_apply_paint_style`에 추가.
붙여넣기는 `capture_state`/`apply_state` 스냅샷으로 다중 대상을 **단일 `push_undo_state` 엔트리**에
묶는다. ⚠ 함정: 단축키를 `view.keyPressEvent`에 배선하며 보니 기존 `Ctrl+C`/`Ctrl+V` 체크가
`AltModifier` 유무를 안 걸러 `Ctrl+Alt+C`/`V`가 항상 일반 복사/붙여넣기로 먼저 먹혔다 — 새 체크를
먼저 검사하는 것만으로는 안전하지 않아(우연히 그 owner가 스타일 복사를 지원 안 하면 조용히
일반복사로 새는 경로가 남음), 기존 두 체크에도 `not (mods & AltModifier)`를 명시적으로 추가(Ctrl+L이
Shift를 배제하던 기존 관례와 동일). 스모크 8종 추가(총 263). Rejected/Not-tested는 커밋 `7b135bf`
트레일러 참조.

**신규기능 — 케이블/넷 번호 자동채번 완료(2026-07-28, 커밋 `7e3e9fb`, 실조건검증 ✓)** —
계획서 §5-6(advanced 후보) 항목. deep-interview로 확정: **선택한 화살표에만 실행하는 우클릭
명령**(전체 화살표 자동 적용 아님 — 순서도 사용자에게 원치 않는 라벨이 안 붙게). 번호 순서는
**화면 위치 자동 정렬**(좌상단→우하단, y우선·x보조) — Qt가 `selectedItems()` 순서를 보장하지
않아(M5에서 이미 확인한 제약) 클릭 순서 방식은 애초에 불가능. 접두사·시작번호는 실행 시
다이얼로그 입력(표·표제란 삽입과 같은 관례). 기존 라벨에 텍스트가 있으면 번호를 앞에 붙이고
원문 보존(`CABLE-01: 메인전원`), 재실행 시 같은 접두사의 옛 번호는 정규식으로 인식해 교체(콜론
유무 모두 매칭 — 최초 채번은 빈 텍스트라 콜론 없이 찍히는데 재실행 인식 정규식이 콜론을 필수로
요구해 자기가 찍은 텍스트를 못 알아보던 self-review 발견 버그 수정). 프레임 챌린지: 삭제·이동
시 자동 갱신되는 '라이브' 채번 대신 **사용자가 필요할 때 재실행하는 수동 명령**으로 확정 — 넷
단위 지속 그룹ID·매 편집마다 동기화가 필요해 복잡도가 크게 뛰는데, 결선도 채번은 실사용상
"문서화 시점 1회+필요시 재정리" 패턴이라 수동 명령으로 충분. 구현: 새 필드 없음 — 화살표
(`_ArrowItem`/`_PolyArrowItem` 둘 다, 직선·곡선·직각 무관) 기존 라벨(`_ConnectorLabel`) 텍스트를
재사용해 `.ecad` 스키마 변경 불필요(규칙 2 손안의 카드). 신규 라벨 생성(create op)과 기존 라벨
수정(mut/state op)을 한 undo 엔트리로 묶어 되돌리기 1번에 전부 복원. 스모크 8종 추가(총 271).

**신규기능 — 레이어 패널 UI 완료(2026-07-28, 커밋 `e1661a0`, 실조건검증 ✓)** — 계획서 §5
후속 항목. deep-interview로 확정: **사용자 정의 이름 레이어**(AutoCAD식, 타입 무관하게 아무
객체나 배정) — DXF 내보내기의 타입별 고정 레이어(`EC_RECT`·`EC_ARROW`…)와는 별개 개념. 스코프
축소: 새로 그리는 도형을 "활성 레이어"에 자동 배정하는 동작은 그리기 도구·붙여넣기·복제·심볼
드롭·Mermaid/이미지 가져오기 등 생성 경로 수십 곳을 전부 건드려야 해서, 1차 버전은 **명시적
이동만**(우클릭 "레이어로 이동" — `Ctrl+G`가 명시적 그룹 지정으로만 붙는 것과 동일한 패턴).
레이어 표시/잠금은 다크모드·그리드 토글과 같은 문서 설정으로 취급해 **undo 비대상**, 아이템→
레이어 배정만 undo 대상(`mut`/`layer`). 그룹(`Ctrl+G`)과는 별개 축 유지 — 그룹은 "함께 움직임",
레이어는 "함께 보이거나 잠김". DXF 왕복은 스코프 밖(1차는 앱 내부 전용). 구현: 아이템 `_layer_id`
(그룹 `_group_id`와 동일 패턴) + 문서 레벨 `self._layers`(이름·표시·잠금 목록, 최소 1개 "기본"
유지). 좌측 "레이어" dock(도형 dock과 탭 공유) — 레이어별 표시/잠금 토글, 우클릭 이름변경·삭제,
+ 로 추가. `.ecad`는 `save_document`/`load_document`에 `layers` 하위호환 추가(옛 파일은 기본
레이어로 안전 리셋) — `load_document`의 기존 반환 계약(`int`, 25곳 이상에서 `== n` 비교)은
그대로 두고 레이어 목록은 별도 `load_document_layers()`로 분리(반환 타입을 튜플로 바꾸면 기존
호출부 25곳이 전부 깨져 회귀 폭이 큼). ⚠ self-review로 발견·수정: 레이어로 이동해도 표시/잠금이
안 물려받는 버그 — `move_selection_to_layer`가 `_layer_id`만 바꾸고 `setVisible`/잠금 플래그는
안 건드려, 숨김·잠금 레이어로 옮겨도 화면엔 그대로 보이고 움직여지는 상태였다. undo도 마찬가지로
`_layer_id`만 복원해 표시/잠금이 어긋났다. `_sync_item_to_layer_state()`로 통일해 이동(forward)·
undo/redo·삭제(기본 소급)·문서 열기 네 경로 전부 "현재 `_layer_id`가 가리키는 레이어 상태로 항상
다시 계산"하게 고쳤다(별도 snapshot 없이 single source of truth). 알려진 한계(승인됨): 레이어
잠금 해제 시 그 안의 개별 `Ctrl+L` 잠금도 함께 풀림(별도 필드 없이 `_locked` 플래그 재사용).
스모크 9종 추가(총 280). Rejected/Not-tested는 커밋 `e1661a0` 트레일러 참조.

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
