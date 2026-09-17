import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
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
    // 过期的令牌先清掉再判断。否则会进入一种坏状态：守卫认为「已登录」
    // （localStorage 里有令牌），而任何请求都拿到 401——访问 /login 会被
    // guestOnly 弹到 /chat，/chat 又取不到数据，用户看到的就是一片空白。
    if (user.isLoggedIn && !user.hasUsableToken) {
      user.clearAuth()
    }

    if (to.meta.requiresAuth && !user.isLoggedIn) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (to.meta.guestOnly && user.isLoggedIn) {
      return { name: 'chat' }
    }

    if (to.meta.requiresAdmin) {
      // role 来自 /users/info：整页刷新时 store 里还是空的（userInfo 只存在内存），
      // 必须先拉一次，否则会把自己误判成非管理员并弹回首页。
      // fetchUserInfo 内部已吞掉异常并返回 null，正常不会抛。
      if (!user.userInfo) {
        await user.fetchUserInfo()
      }
      if (user.userInfo?.role !== 'admin') {
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
