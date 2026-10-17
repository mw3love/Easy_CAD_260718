import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
export default defineConfig({ plugins: [react()], build: { rollupOptions: { input: {
  tldraw: resolve(__dirname, 'tldraw.html'), excalidraw: resolve(__dirname, 'excalidraw.html'), direct: resolve(__dirname, 'direct.html') } } } })
