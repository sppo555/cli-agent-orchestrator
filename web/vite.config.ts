/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../src/cli_agent_orchestrator/web_ui',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: fileURLToPath(new URL('./index.html', import.meta.url)),
        token: fileURLToPath(new URL('./token.html', import.meta.url)),
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
  server: {
    host: 'localhost',
    port: 5173,
    proxy: {
      '/sessions': { target: 'http://localhost:9889', changeOrigin: true },
      '/terminals': { target: 'http://localhost:9889', changeOrigin: true, ws: true },
      '/health': { target: 'http://localhost:9889', changeOrigin: true },
      '/agents': { target: 'http://localhost:9889', changeOrigin: true },
      '/settings': { target: 'http://localhost:9889', changeOrigin: true },
      '/flows': { target: 'http://localhost:9889', changeOrigin: true },
      '/memory': { target: 'http://localhost:9889', changeOrigin: true },
      '/token-usage': { target: 'http://localhost:9889', changeOrigin: true },
      '/graph': { target: 'http://localhost:9889', changeOrigin: true },
    },
  },
})
