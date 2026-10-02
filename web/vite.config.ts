import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  build: {
    rollupOptions: {
      output: {
        // 把体积稳定、更新频率低的依赖拆成独立 chunk。
        // 业务代码每次发版都变，框架依赖基本不动；不拆的话用户每次
        // 都要重新下载整个 ~220KB 的 index 包。拆开后改业务只失效业务包。
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          http: ['axios']
        }
      }
    }
  },
  server: {
    port: 5173,
    host: true,
    watch: {
      // 忽略编辑器/工具的中转临时目录（*.tmpdir），否则写入瞬间会触发 watcher EBUSY 崩溃
      ignored: ['**/.preview/**', '**/.shots/**', '**/*.tmpdir/**', '**/.*.tmpdir/**']
    }
  }
})
