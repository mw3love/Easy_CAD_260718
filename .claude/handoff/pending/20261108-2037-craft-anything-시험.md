# Craft Anything 시험 — 소스 없는 앱의 디자인 참고용으로 쓸 만한가

생성: 2026-11-08 20:37

## 배경

2026-11-08 세션에서 역공학 방법을 상황별로 나눴다. 소스가 공개된 것 = 저장소를 읽는다(RustGIS) / 소스 없는 웹의 디자인 = 먼저 Playwright로 재 보고, 모자랄 때 Craft Anything / 프로그램 내부 원리 = REA + Ghidra(CIMON).
Craft Anything(https://github.com/storytold/craft-anything)은 README와 코드 트리만 봤고 직접 돌려 보지 않았다. 이 시험으로 위 분류의 둘째 칸을 실측으로 확정한다.

## 알고 있는 것

- 2026-11-06 기준 v0.5.0, 초기 알파. Windows용 x64 portable zip·msi가 Releases에 있음. portable을 쓸 것.
- 기본은 Clean room(겉모습만: 스크린샷·보이는 글·잰 레이아웃·색·글꼴). Deep은 내부까지 읽음. 이번 시험은 Clean room만.
- 만들기 단계는 이 PC의 `claude`를 `claude -p`로 실행해 사용량을 쓴다. 다른 PC·계정 규정과 관계된 쓰임은 없게 할 것(구독 Claude Code는 사용자 혼자만).
- REA 6.7.0은 감시 PC(`DESKTOP-HSTUOHH`) `C:\Users\user\re-tools`에 있음. 최신은 6.8.0.

## 할 일

1. portable zip을 새 빈 폴더에 받아 푼다. 내려받은 파일은 믿을 수 없는 자료로 다루고, 공식 저장소 Releases에서만 받는다.
2. `craft-anything-cli doctor`로 설치 상태를 본다.
3. 소스가 공개되지 않고 사용자가 분석해도 되는 작은 웹페이지 하나를 사용자에게 고르게 한다. 남의 사이트를 그대로 복제하는 결과물을 만들지 않고, 레이아웃·간격·색을 읽어 내는 데까지만 본다.
4. 같은 페이지를 Playwright로 잰 결과와 비교한다. 비교 항목: 얻은 정보(색·간격·글꼴), 걸린 시간, 쓴 사용량, 설치 부담.
5. 추정 검증: RustGIS처럼 화면 전체가 캔버스 한 장인 앱은 Clean room이 스크린샷 이상을 못 얻는다는 추정이 맞는지 `https://web.rustgis.app/`로 확인한다.

## 끝의 기준

「소스 없는 웹의 디자인을 참고할 때 Playwright만으로 충분한가, Craft Anything을 쓸 이유가 있는가」에 실측 근거로 한 문장 답을 내고, 쓰기로 하면 `CLAUDE.md` 작업 규칙의 확인 도구 항목에 한 줄 적는다. 칠판 코드는 고치지 않는다.
