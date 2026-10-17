import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
// 개발 중엔 저장 API를 Python 서버(web/server.py, 5191)로 넘긴다
export default defineConfig({ plugins: [react()], server: { proxy: { '/api': 'http://localhost:5191' } } })
