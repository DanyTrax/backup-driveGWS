import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** Inyectado por `npm run build` (`npm_package_version`). */
const ver = process.env.npm_package_version ?? '0.1.0'
const uiBuildId = `${ver} · ${new Date().toISOString().slice(0, 19)}Z`

export default defineConfig({
  define: {
    'import.meta.env.VITE_UI_BUILD_ID': JSON.stringify(uiBuildId),
  },
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
    chunkSizeWarningLimit: 1000,
  },
})
