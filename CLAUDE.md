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
  - **직교 자동라우팅 경유지 힌트** 완료: 자동라우팅(A*) 중 중간 정점을 드래그하면 freeze 대신
    '경유 힌트'로 커밋 — 자동라우팅을 유지한 채 그 지점을 지나가도록 재계산. 화살표당 힌트
    최대 1개(여러 개 허용했더니 드래그할수록 계단식으로 지저분해짐 — GUI 실측 후 단일 제한).
    힌트 제거 스냅 반경은 화면 px 고정(테두리 스냅과 동일 관례, 줌과 무관하게 일정).

## 다음 할 일 (우선순위)
1. **좌/우 드래그 선택**(window: 왼→오 완전포함 / crossing: 오→왼 걸침) — AutoCAD 시그니처. (다음 세션 지정)
2. **선/화살표 더블클릭 라벨** — 선 움직이면 라벨도 따라오게(부착) 설계 포함.
3. ~~회전/미러/스케일/stretch(다중 선택)~~ — **완료**(그룹 변형 Stage 1·2a·2b).
4. (계획서 §5 권장 흡수) 심볼/스텐실 라이브러리 · 포트/접속점.
   ~~직교 커넥터+자동라우팅(A*·경유지 힌트)~~ — **완료**.
그 후 Phase 3(DXF, ezdxf) · Phase 4(표·이미지·표제란·Mermaid import) · Phase 5(AI 이미지→도면).

## 작업 규칙
- GUI라 **offscreen 스모크로 프록시검증** 후 **실조건은 사용자에게 `python run.py` 요청**.
  ⚠ 전례: 지속연결 초안이 offscreen을 통과했으나 GUI에서 버그 발견(플로팅→고정 부착점으로 수정).
  즉 **offscreen 통과 ≠ 해결**. GUI 확인 전 "해결" 단정 금지.
- 각 기능은 검증가능 목표로 닫고, 새 스모크는 `tests/test_easycad.py`에 추가(임시폴더 금지).
- 비자명 커밋엔 트레일러(Rejected/Constraint/Confidence/Not-tested) + `Co-Authored-By: Claude Opus 4.8`.
- 계획/검토 요청이면 코드 손대지 말 것(승인 게이트). "고쳐줘/만들어줘"면 실행.
- 코어는 pasteflow에서 복사해 분기한 것 — annotator_core.py 편집 허용(단 surgical하게, 주석으로 우리 확장 표시).
