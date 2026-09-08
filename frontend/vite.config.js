import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// 127.0.0.1, not localhost: on Windows `localhost` resolves to ::1 first, and a
// backend bound to IPv4 only is then unreachable through the proxy (it 404s or
// hits whatever else holds the port). Override with VITE_PROXY_TARGET when the
// backend runs elsewhere or on another port.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { '/api': { target, changeOrigin: true } },
    },
    optimizeDeps: { include: ['microsoft-cognitiveservices-speech-sdk'] },
    build: {
      commonjsOptions: {
        include: [/microsoft-cognitiveservices-speech-sdk/, /node_modules/],
      },
    },
    define: { global: 'globalThis' },
  }
})
