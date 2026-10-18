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
- ⚠ 접근 제한이 없다 — 같은 네트워크의 누구나 열 수 있다. 회사 보안 확인 전엔 `--host 127.0.0.1`(이 PC에서만).
- 두 PC에서 동시에 고치면 나중에 저장한 쪽이 이긴다(실시간 공동작업은 아직).
- 코드를 고친 뒤엔 `npm run build`를 다시 하고 서버를 다시 켠다.
- 오른쪽 KAIROS 대화창은 이 서버가 게이트웨이를 대신 부른다 — 서버 PC에 `openai`·`httpx`(데스크톱 앱과 같은 것)와 키 파일
  `~/.claude/.secrets/easycad-gateway.key`가 있어야 한다(키는 브라우저로 안 간다). 대화 기록은 저장 폴더의 `<이름>.chat.json`.
  ⚠ 접근 제한이 없으니 같은 네트워크의 누구나 내 크레딧으로 물을 수 있다 — 보안 확인 전엔 `--host 127.0.0.1`.

## 개발

```
cd web
npm run dev          # http://localhost:5190 — 저장은 python web/server.py(5191)로 넘김, 서버가 없으면 이 브라우저에만
npm test             # 순수 함수 시험
```

칠판은 직접 만든 것(`src/next/`) — 2026-10-18 tldraw에서 갈아탐(§8 항목61 5단계). 문서는 `.ecad` 그대로, 서버 저장은 `/api/doc/<이름>`.
옛 주소 `next.html?board=…`는 `/`로 넘어간다(즐겨찾기용). 글 편집은 TipTap 3.32.0(MIT), 부품은 `package.json`에 모두 버전 고정.
