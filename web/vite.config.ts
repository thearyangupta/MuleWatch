import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const reviewApiKey = process.env.MULEWATCH_REVIEW_API_KEY

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            if (reviewApiKey) {
              proxyReq.setHeader('X-Review-API-Key', reviewApiKey)
            }
          })
        },
      },
    },
  },
})
