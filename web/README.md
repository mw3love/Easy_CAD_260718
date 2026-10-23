# Magic Board 웹 칠판

데스크톱 Magic Board(`.ecad`)를 브라우저에서 여는 칠판. 계획: `docs/EasyCAD_계획.md` §8 항목61.

## 감시 PC에서 켜기 (회사 안 다른 PC는 크롬으로 접속)

처음 한 번(Node 24·Python 3 필요):

```
git pull
cd web
npm install
npm run build
```

켜기(리포 맨 위 폴더에서):

```
python web/server.py
```

- 다른 PC 크롬에서 `http://<감시 PC 주소>:5191` — 같은 칠판이 보인다. 주소 끝 `?board=이름`으로 칠판을 여러 개.
- 저장 폴더: `%APPDATA%\EasyCAD\web_boards\<이름>.ecad` (데스크톱과 같은 형식, 바로 앞 저장본은 `<이름>.prev.ecad`). 바꾸려면 `--data 폴더`.
- 같이 쓰기(공동작업 1단계): 팀 비밀번호를 정하면 들어올 때 비밀번호 + 이름을 묻는다 — `python web/server.py --password 팀비번`
  (또는 환경 변수 `MB_PASSWORD`, 또는 저장 폴더의 `edit_password.txt`). 비밀번호를 바꾸면 모두 다시 들어와야 한다. 정하지 않으면 누구나 편집(내 PC 개발용).
- 게시: 칠판 상단 「🔗 공유」 → 「게시하기」 = 로그인 없이 보기·발표만 되는 링크(`/?view=…`). 「새 링크로 바꾸기」 = 옛 링크 막힘, 「게시 끄기」 = 막힘.
- 여럿이 동시에 고쳐도 서로 다른 도형이면 둘 다 남는다(같은 도형은 나중 것이 이김). 다른 사람 변경은 2초쯤 뒤에 보인다.
- ⚠ 사내망 `http`라 비밀번호가 암호화 없이 오간다 — 회사 보안 확인 전엔 `--host 127.0.0.1`(이 PC에서만).
- 코드를 고친 뒤엔 `npm run build`를 다시 하고 서버를 다시 켠다.
- 오른쪽 KAIROS 대화창은 이 서버가 게이트웨이를 대신 부른다 — 서버 PC에 `openai`·`httpx`(데스크톱 앱과 같은 것)와 키 파일
  `~/.claude/.secrets/easycad-gateway.key`가 있어야 한다(키는 브라우저로 안 간다). 대화 기록은 저장 폴더의 `<이름>.chat.json`.
  ⚠ 팀 비밀번호를 안 정하면 같은 네트워크의 누구나 내 크레딧으로 물을 수 있다(정하면 들어온 사람만, 게시 링크로는 못 씀).

## 개발

```
cd web
npm run dev          # http://localhost:5190 — 저장은 python web/server.py(5191)로 넘김, 서버가 없으면 이 브라우저에만
npm test             # 순수 함수 시험
npm run e2e          # 화면 자동 시험 — 빌드 후 깔린 크롬으로 매일 쓰는 흐름(e2e/flow1~26, 82개)을 돌림, 약 3분
```

화면 시험(2026-10-19 다잡기)은 시험용 서버를 따로 띄운다 — 문 5291·데이터 `web/.e2e-data`(시험 전에 비움, git 밖). 켜 둔 진짜 서버(5191)·칠판과 섞이지 않는다.
KAIROS는 가짜 답으로 바꿔 끼워 크레딧을 안 쓴다. 글쇠를 바꾸면 `src/next/keys.js`(도움말 F1이 보여 주는 표)와 `e2e/flow9-keys.spec.js`를 같이 고친다.
실패하면 `web/test-results/`의 trace를 `npx playwright show-trace <경로>`로 본다.

칠판은 직접 만든 것(`src/next/`) — 2026-10-18 tldraw에서 갈아탐(§8 항목61 5단계). 문서는 `.ecad` 그대로, 서버 저장은 `/api/doc/<이름>`.
옛 주소 `next.html?board=…`는 `/`로 넘어간다(즐겨찾기용). 글 편집은 TipTap 3.32.0(MIT), 부품은 `package.json`에 모두 버전 고정.
