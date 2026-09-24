import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: '/v2/',
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8010' },
  },
  test: {
    environment: 'happy-dom',
  },
})
