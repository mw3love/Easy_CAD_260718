// 화면 자동 시험(§8 항목61 「다잡기」, 2026-10-19) — 매일 쓰는 흐름을 실제 크롬으로 돌린다. 실행 `npm run e2e`(빌드 → 시험).
// 시험용 저장 서버는 다른 문(5291)·임시 데이터 폴더(`web/.e2e-data`)로 띄워 진짜 칠판(5191·%APPDATA%)과 섞이지 않는다.
// 브라우저는 깔린 크롬(channel 'chrome') — 따로 내려받지 않음.
import { defineConfig } from '@playwright/test'

export const PORT = 5291
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,   // 서버 하나를 같이 씀 — 칠판 이름은 시험마다 따로
  workers: 1,
  reporter: [['list']],
  globalSetup: './e2e/global-setup.js',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: 'chrome',
    viewport: { width: 1600, height: 900 },
    locale: 'ko-KR',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `python server.py --host 127.0.0.1 --port ${PORT} --data .e2e-data`,
    url: `http://127.0.0.1:${PORT}/api/session`,
    reuseExistingServer: false,
    env: { PYTHONIOENCODING: 'utf-8', MB_PASSWORD: '', EASYCAD_ROUTE: 'rules', EASYCAD_DESCRIBE: 'off' },   // 길 고르기는 낱말 규칙(판단 모델·주간 자가 시험 안 부름), 그림 설명 끔(그림 넣을 때마다 크레딧)
    timeout: 30_000,
  },
})
