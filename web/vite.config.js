import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// 개발 중엔 저장 API를 Python 서버(web/server.py, 5191)로 넘긴다
// 페이지: index.html = 칠판(직접 만든 것, §8 항목61 5단계 2026-10-18 갈아탐 — tldraw 뺌) · next.html = 옛 주소를 /로 넘기는 안내판
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:5191' } },   // localhost = Node 17+에선 IPv6(::1) 먼저 — 서버를 --host 127.0.0.1로 켜면 502(2026-10-20)
  build: { rollupOptions: { input: { main: 'index.html', next: 'next.html' } } },
})
