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
- 저장 폴더: `%APPDATA%\EasyCAD\web_boards\<이름>.json` (바로 앞 저장본은 `<이름>.prev.json`). 바꾸려면 `--data 폴더`.
- ⚠ 접근 제한이 없다 — 같은 네트워크의 누구나 열 수 있다. 회사 보안 확인 전엔 `--host 127.0.0.1`(이 PC에서만).
- 두 PC에서 동시에 고치면 나중에 저장한 쪽이 이긴다(실시간 공동작업은 아직).
- 코드를 고친 뒤엔 `npm run build`를 다시 하고 서버를 다시 켠다.

## 개발

```
cd web
npm run dev          # http://localhost:5190 — 저장은 python web/server.py(5191)로 넘김, 서버가 없으면 이 브라우저에만
npm test             # 순수 함수 시험
```

tldraw는 5.5.2로 고정. `http://` 주소에선 라이선스 키 없이 개발 모드로 돌지만, 실제로 쓰려면 약관상 키가 필요(취미 라이선스는 표시가 남음).
