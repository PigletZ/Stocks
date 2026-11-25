import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    // 拆分大依赖到独立 chunk：避免把所有代码压进一个巨型 chunk，
    // 降低构建时压缩单文件的瞬时内存峰值，同时改善前端按需加载
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/echarts/') || id.includes('/node_modules/zrender/')) return 'charts'
          if (id.includes('/node_modules/lightweight-charts/')) return 'lightweight-charts'
          if (/\/node_modules\/(vue|@vue|vue-router|pinia)\//.test(id)) return 'vue'
        },
      },
    },
  },
  server: {
    port: 5173,
    host: true, // 允许通过公网 IP 访问开发服务器
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
