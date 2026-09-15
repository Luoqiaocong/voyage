import { ref } from 'vue'

/**
 * 全局主题（浅色 / 深色）。
 * 在 <html data-theme> 上切换，CSS 令牌随之生效；选择持久化到 localStorage。
 * index.html 中的内联脚本会在首屏渲染前写入 data-theme，避免主题闪烁。
 */
const STORAGE_KEY = 'voyage-theme'

const isDark = ref(false)
let initialized = false

function apply(dark: boolean) {
  isDark.value = dark
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}

export function useTheme() {
  if (!initialized && typeof document !== 'undefined') {
    initialized = true
    const current = document.documentElement.getAttribute('data-theme')
    if (current) {
      isDark.value = current === 'dark'
    } else {
      let stored: string | null = null
      try {
        stored = localStorage.getItem(STORAGE_KEY)
      } catch {
        /* 隐私模式：忽略 */
      }
      const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
      apply(stored ? stored === 'dark' : prefersDark)
    }
  }

  function toggleTheme() {
    const next = !isDark.value
    apply(next)
    try {
      localStorage.setItem(STORAGE_KEY, next ? 'dark' : 'light')
    } catch {
      /* 隐私模式：忽略 */
    }
  }

  return { isDark, toggleTheme }
}
