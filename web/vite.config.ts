import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
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
