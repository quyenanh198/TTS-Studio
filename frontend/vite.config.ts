import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev: Vite on :5173 proxies /api and /ws to backend on :8765 (python launcher.py --dev)
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true, ws: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
