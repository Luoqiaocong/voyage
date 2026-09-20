import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { canAccessAdmin } from '@/utils/role'
import { routeLoading, routeLoadingText } from './state'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { guestOnly: true } },
    // 找回通行证独立成页：重置密码与登录/注册是不同任务，
    // 挂在同一组件里会让字段与文案互相渗透
    { path: '/forgot', name: 'forgot', component: () => import('@/views/ForgotView.vue'), meta: { guestOnly: true } },
    { path: '/chat', name: 'chat', component: () => import('@/views/ChatView.vue'), meta: { requiresAuth: true } },
    { path: '/itineraries', name: 'itineraries', component: () => import('@/views/ItinerariesView.vue'), meta: { requiresAuth: true } },
    { path: '/itineraries/:id(\\d+)', name: 'itinerary-detail', component: () => import('@/views/ItineraryDetailView.vue'), meta: { requiresAuth: true } },
    { path: '/profile', name: 'profile', component: () => import('@/views/ProfileView.vue'), meta: { requiresAuth: true } },

    // 公开分享页：无需登录——这正是分享的意义。
    // 安全性由令牌 + 可选密码保证，而不是登录态。
    { path: '/share/:token', name: 'share', component: () => import('@/views/ShareView.vue') },

    // 管理台：requiresAdmin 只是界面层拦截，真正的边界在后端
    // （/admin 路由统一挂了 get_current_admin）。
    {
      path: '/admin',
      component: () => import('@/views/admin/AdminLayout.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
      children: [
        { path: '', name: 'admin-dashboard', component: () => import('@/views/admin/AdminDashboard.vue') },
        { path: 'metrics', name: 'admin-metrics', component: () => import('@/views/admin/AdminMetrics.vue') },
        { path: 'users', name: 'admin-users', component: () => import('@/views/admin/AdminUsers.vue') },
        { path: 'conversations', name: 'admin-conversations', component: () => import('@/views/admin/AdminConversations.vue') },
        { path: 'audit', name: 'admin-audit', component: () => import('@/views/admin/AdminAudit.vue') }
      ]
    },

    { path: '/:pathMatch(.*)*', redirect: '/' }
  ],
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  }
})

router.beforeEach(async (to) => {
  const user = useUserStore()

  // 顶部进度条：懒加载页面在 chunk 下载期间需要有即时反馈
  routeLoading.value = true
  routeLoadingText.value = loadingTextFor(to.path)

  // 整个守卫包在 try/catch 里：守卫一旦抛错，导航会被中止、页面渲染成空白。
  // 任何意外都退化为「按未登录处理」——宁可多跳一次登录页，也不要白屏。
  try {
    /*
     * access token 过期时**先尝试续期**，而不是直接登出 ——
     * refresh token 有 7 天有效期，access token 只有 30 分钟，
     * 直接登出会让用户每 30 分钟就要重新输一次密码。
     *
     * ensureValidToken 内部会：令牌仍有效 → 直接用；过期 → 用 refresh
     * token 换新的；换不到才清登录态。它自己吞掉异常，不会中断导航。
     */
    if (user.isLoggedIn && !user.hasUsableToken) {
      await user.ensureValidToken()
    }

    if (to.meta.requiresAuth && !user.isLoggedIn) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (to.meta.guestOnly && user.isLoggedIn) {
      /*
       * 已登录用户访问登录页时弹到对话页。
       *
       * 必须**保留 example**：首页填了需求点「开始规划」→ 去登录页
       * （?example=...）→ 此时若已是登录态（例如令牌刚恢复、或从历史
       * 记录进来），丢掉 example 会让用户回到对话页后发现刚写的内容没了。
       *
       * redirect 参数也要一并保留：/login?redirect=/itineraries/3 这类
       * 深链在已登录时同样应落到原目标，而不是一律去 /chat。
       */
      const raw = to.query.example
      const example = Array.isArray(raw) ? raw[0] : raw
      const rawRedirect = to.query.redirect
      const redirect = Array.isArray(rawRedirect) ? rawRedirect[0] : rawRedirect

      // 只接受站内绝对路径，防开放重定向（与 LoginView.safeRedirect 同规则）
      const target =
        typeof redirect === 'string' &&
        redirect.startsWith('/') &&
        !redirect.startsWith('//')
          ? redirect
          : '/chat'

      return {
        path: target,
        query: typeof example === 'string' && example ? { example } : undefined
      }
    }

    if (to.meta.requiresAdmin) {
      // role 来自 /users/info：整页刷新时 store 里还是空的（userInfo 只存在内存），
      // 必须先拉一次，否则会被当成非管理员弹回首页。
      // fetchUserInfo 内部已吞掉异常并返回 null，正常不会抛。
      if (!user.userInfo) {
        await user.fetchUserInfo()
      }
      // 两种管理员都能进：普通管理员只是没有写权限，不该被挡在门外。
      // 判断走 utils/role.ts，admin 与 super_admin 都放行（与后端一致）。
      if (!canAccessAdmin(user.userInfo?.role)) {
        return { name: 'home' }
      }
    }
  } catch {
    // 兜底：清掉可能已损坏的登录态，放行到登录页
    try {
      user.clearAuth()
    } catch {
      /* 忽略 */
    }
    return { name: 'login' }
  }

  return true
})

/**
 * 切换结束时收起进度条。
 *
 * 必须同时挂 afterEach 与 onError：导航失败（守卫抛错、chunk 下载失败）
 * 时不会走 afterEach，只挂它会让进度条永远停在那里。
 */
router.afterEach(() => {
  routeLoading.value = false
})
router.onError(() => {
  routeLoading.value = false
})

/** 按目标路径给一句贴切的加载提示 */
function loadingTextFor(path: string): string {
  if (path.startsWith('/chat')) return '正在打开旅行顾问…'
  if (path.startsWith('/itineraries')) return '正在取出你的行程…'
  if (path.startsWith('/admin')) return '正在加载管理台…'
  if (path.startsWith('/profile')) return '正在打开个人主页…'
  if (path.startsWith('/share')) return '正在打开分享的行程…'
  return '正在加载…'
}

export default router
