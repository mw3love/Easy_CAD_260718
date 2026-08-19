완료: 2026-08-19 20:15 (Stage 5 완료, 커밋 5ea83a6 — 같은 세션에서 Stage 6로 계속 진행)

# Mermaid·SVG AI 다이얼로그 재정리 — Stage 5·6 이어서

생성: 2026-08-19 19:34

## 배경

사용자가 SVG 생성 버튼을 누르면 창이 멈추는 문제를 보고했고(참고 이미지: AI가 만든
"Mermaid 가져오기 Studio v2.0" 목업), deep-interview로 6단계 계획을 확정했다:

1. 비동기화(QThread, 프리징 해소) + 진행표시(marquee+경과시간)
2. SVG 다중후보(모델별 0~5개 드롭다운) + 완전 병렬 호출
3. SVG 이미지 입력(Mermaid와 동일 첨부 UI 재사용)
4. 카드 다중선택(체크박스) + 내 심볼 일괄저장
5. Mermaid 실시간 렌더 미리보기
6. 레이아웃 최종 통일(시안 이미지 기준)

이 세션에서 **Stage 1~4를 전부 구현·검증·커밋 완료**했다. 아직 **push 안 함**(사용자가
이번엔 push도 다음으로 미루기로 선택).

## 커밋 내역 (로컬에만 있음, 아직 push 안 됨)

```
22b0441 feat(ai-svg): SVG 후보 다중선택 + 내 심볼 팔레트 일괄저장          (Stage 4)
b469e80 feat(ai-svg): SVG 에셋 생성 이미지 입력 추가 — Mermaid 첨부 UI 재사용  (Stage 3)
79c3a3b feat(ai-svg): SVG 에셋 생성 다중후보(모델별 0~5개) + 완전 병렬 호출   (Stage 2)
6185ced perf(ai-dialogs): Mermaid·SVG AI 생성 프리징 해소 — QThread 비동기화 + 진행표시 (Stage 1)
```

각 커밋은 실제 창(오프스크린 아님) + 실제 게이트웨이 호출로 종단 검증까지 마쳤다(스크린샷
확인, 커밋 트레일러에 Confidence: high로 기록됨). 전체 pytest 762종 통과(사전에 이미
알려진 이 PC 로컬 secrets 파일발 무관 실패 3건은 제외 — `_clear_gateway_settings()`가
QSettings만 지우고 secrets 파일 우선순위는 못 지우는 기존 결함, 이번 세션과 무관).

## 다음 세션에서 할 일

**1. push 확인부터** — 4개 커밋이 로컬에만 있다. `git push` 실행 전 `doc-sync` 스킬로
사전 검토(전역 CLAUDE.md 규칙 10). 이미 CLAUDE.md·docs/EasyCAD_계획.md·docs/history/
2026-08.md·docs/pitfalls.md는 매 스테이지마다 갱신해 커밋에 포함시켰으므로, doc-sync가
추가로 찾을 게 많지 않을 가능성이 높다(그래도 절차는 생략하지 말 것).

**2. Stage 5(Mermaid 실시간 렌더 미리보기) 착수** — deep-interview로 이미 설계 확정됨:
- 신규 mermaid.js 렌더러(QWebEngineView 등) **도입 안 함** — 새 의존성 없이 기존 파서
  (`easycad/fileio/mermaid_import.py`의 `parse_mermaid`/`layout_positions`)로 도형을
  만들고 임시 `QGraphicsScene`에 렌더하는 방식(SVG 쪽 `_render_svg_candidate_pixmap`,
  `host_dialogs.py`에 있음이 정확히 같은 패턴 — 그대로 참고해서 만들면 됨).
- 코드 편집 중 **디바운스 재렌더**(타이핑마다 매번 다시 그리면 무거우므로 QTimer
  디바운스, 몇백ms 정도 — 정확한 수치는 이번에 착수하며 판단).
- 참고 이미지(사용자가 원래 보여준 목업)에 우측 미리보기 패널 컨셉이 있었음 — 그
  이미지 자체는 이 세션 대화에만 있고 파일로 저장 안 해뒀으니, 필요하면 사용자에게
  다시 보여달라고 요청하거나 이미 반영된 레이아웃 감각(카드+커넥터 화살표+모델 드롭다운)
  으로 충분히 진행 가능.
- 배치는 `_MermaidDialog`(`host_dialogs.py`)의 Mermaid 코드칸(`_edit`) 옆/아래에 미리보기
  영역을 추가하는 형태가 될 것 — 정확한 레이아웃은 착수 시 판단(필요하면 짧은
  deep-interview로 확정).

**3. Stage 6(레이아웃 최종 통일)** — Stage 5까지 끝난 뒤, 시안 이미지 기준으로 두
다이얼로그의 최종 비주얼을 정리. Stage 5 결과에 따라 세부가 달라지므로 지금 미리
설계하지 않는다.

## 참고할 문서 (요약 말고 원문을 읽을 것 — 전역 CLAUDE.md 규칙 1)

- `docs/EasyCAD_계획.md` §8 항목23 — 전체 6단계 계획과 Stage 1~4 완료 요약.
- `docs/history/2026-08.md`의 "§8 항목20 후속 — Mermaid·SVG AI 다이얼로그 재정리
  Stage 1"·"Stage 2"·"Stage 3"·"Stage 4" — 각 단계 판단 근거·시행착오 전문(예:
  `host_dialogs.py`가 순환임포트 회피용 잎 모듈이라 `host_selection.py`를 직접
  import 못 하는 제약을 어떻게 `getattr(parent, ...)` 위임으로 우회했는지, `_SvgGenWorker`
  를 "워커 하나=모델 리스트 순차"에서 "워커 하나=호출 하나"로 왜 재설계했는지 등).
- `docs/pitfalls.md` "검증 방법론" 절 끝부분 — QThread 테스트가 join 전에 실패하면
  살아있는 스레드가 patch 해제 후 진짜 네트워크 함수를 다시 잡아 스위트가 몇 시간
  멈추는 함정(이번 세션에 실제로 걸렸다 풀었음, Stage 5/6에서 QThread 테스트를 또
  건드릴 일이 있으면 같은 함정을 피할 것).

## 판단 기준

이 프롬프트의 커밋 해시·문서 항목 제목을 그대로 믿지 말고, 착수 전에 `git log --oneline
-10`과 해당 문서 섹션이 실제로 그 내용대로 있는지 먼저 확인한다(전역 CLAUDE.md 규칙 1 —
기억이 아니라 도구로 확인).
