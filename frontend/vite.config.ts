import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // 백엔드 API 네임스페이스는 /v1 (tasks/PHASE-3: POST /v1/intent/infer)
    proxy: {
      '/v1': 'http://127.0.0.1:8000',
    },
  },
})
