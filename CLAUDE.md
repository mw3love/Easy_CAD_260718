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
