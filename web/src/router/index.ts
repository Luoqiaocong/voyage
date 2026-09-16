import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { guestOnly: true } },
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
    if (!user.userInfo) {
      await user.fetchUserInfo()
    }
    if (user.userInfo?.role !== 'admin') {
      return { name: 'home' }
    }
  }
})

export default router
