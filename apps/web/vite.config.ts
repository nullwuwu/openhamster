import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('vue-echarts')) {
            return 'vendor-vue-echarts'
          }
          if (id.includes('echarts')) {
            return 'vendor-echarts-core'
          }
          if (id.includes('zrender')) {
            return 'vendor-zrender'
          }
          if (id.includes('@tanstack/vue-query')) {
            return 'vendor-query'
          }
          if (id.includes('vue-router') || id.includes('vue-i18n') || id.includes('/vue/')) {
            return 'vendor-vue'
          }
          return 'vendor'
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
  },
})
