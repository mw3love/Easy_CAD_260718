import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// 개발 중엔 저장 API를 Python 서버(web/server.py, 5191)로 넘긴다
// 페이지 둘: index.html(지금 tldraw 칠판) · next.html(직접 만드는 칠판, §8 항목61 「바뀐 결정」 — 5단계에서 index로 갈아탐)
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:5191' } },
  build: { rollupOptions: { input: { main: 'index.html', next: 'next.html' } } },
})
