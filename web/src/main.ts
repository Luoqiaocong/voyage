import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'
import { useUiStore } from './stores/ui'
import { SESSION_EXPIRED_EVENT, type SessionExpiredDetail } from './utils/session'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

/*
 * 会话失效的统一处理。
 *
 * 为什么在这里监听而不是写在 api/http.ts 里：
 * http 层直接 import store 会与 stores/user.ts（它 import 了 http）
 * 形成循环依赖。事件把方向掰成单向：
 *
 *   http.ts ──dispatch──▶ 这里 ──▶ store.clearAuth() + router
 *
 * 处理三件事：
 *   1. 清登录态 —— 必须做。http 层只清了 localStorage，
 *      而 Pinia 内存里的 accessToken 还在，界面会继续显示「已登录」
 *      （头像、导航项都在），点任何功能才报错，观感是「登录了但用不了」。
 *   2. 弹一句提示 —— 告诉用户为什么被请去登录页，否则跳转很突兀。
 *   3. 带 redirect 跳登录页 —— 登录后能回到原处，而不是一律落到 /chat。
 */
window.addEventListener(SESSION_EXPIRED_EVENT, ((e: CustomEvent<SessionExpiredDetail>) => {
  const user = useUserStore()
  const ui = useUiStore()

  // 已经在登录页就不要再跳，否则会打断用户正在进行的登录
  const onLoginPage = window.location.pathname.startsWith('/login')
  if (onLoginPage) {
    user.clearAuth()
    return
  }

  user.clearAuth()
  ui.toast(e.detail?.message || '登录已过期，请重新登录', 'error')

  const redirect = window.location.pathname + window.location.search
  // 只回跳站内路径，防开放重定向（与 LoginView.safeRedirect 同规则）
  const safe =
    redirect.startsWith('/') && !redirect.startsWith('//') && !redirect.startsWith('/login')
      ? { redirect }
      : undefined

  router.replace({ name: 'login', query: safe }).catch(() => {
    // 路由已在别处跳转时忽略，避免未捕获的导航失败
  })
}) as EventListener)

app.mount('#app')
