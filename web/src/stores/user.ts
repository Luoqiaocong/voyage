import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type { UserInfo } from '@/api/user'
import { getInfo as apiGetInfo } from '@/api/user'
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '@/constants'
import { clearAuthStorage, refreshAccessToken } from '@/api/http'

export const useUserStore = defineStore('user', () => {
  const accessToken = ref<string>(localStorage.getItem(ACCESS_TOKEN_KEY) ?? '')
  const refreshToken = ref<string>(localStorage.getItem(REFRESH_TOKEN_KEY) ?? '')
  const userInfo = ref<UserInfo | null>(null)

  const isLoggedIn = computed(() => accessToken.value !== '')

  function setAuth(res: { access_token: string; refresh_token: string }) {
    accessToken.value = res.access_token
    refreshToken.value = res.refresh_token
    localStorage.setItem(ACCESS_TOKEN_KEY, res.access_token)
    localStorage.setItem(REFRESH_TOKEN_KEY, res.refresh_token)
  }

  /**
   * 本地判断 access token 是否已过期（不请求后端）。
   *
   * 为什么需要：路由守卫只看「localStorage 里有没有令牌」并不够。若残留一个
   * 已过期的令牌（access token 默认仅 30 分钟），访问 /login 会被 guestOnly
   * 静默弹到 /chat，而 /chat 又因令牌失效取不到数据——用户看到的就是一个
   * 空白界面，主观上就是「登录页打不开」。
   *
   * 解析失败（非 JWT 结构）视为不可用，同样触发清理。
   */
  function isTokenExpired(token: string): boolean {
    const parts = token.split('.')
    if (parts.length < 2) return true
    try {
      // JWT payload 是 base64url，需补齐 padding 并替换 URL 安全字符
      const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
      const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
      const payload = JSON.parse(atob(padded)) as { exp?: number }
      if (typeof payload.exp !== 'number') return false
      // 留 30 秒余量，避免边界上刚好过期导致请求被拒
      return payload.exp * 1000 <= Date.now() + 30_000
    } catch {
      return true
    }
  }

  /** 当前是否持有一个看起来仍有效的 access token */
  const hasUsableToken = computed(
    () => accessToken.value !== '' && !isTokenExpired(accessToken.value)
  )

  function clearAuth() {
    accessToken.value = ''
    refreshToken.value = ''
    userInfo.value = null
    clearAuthStorage()
  }

  async function fetchUserInfo(force = false): Promise<UserInfo | null> {
    if (!accessToken.value) return null
    if (userInfo.value && !force) return userInfo.value
    try {
      userInfo.value = await apiGetInfo()
      return userInfo.value
    } catch {
      return null
    }
  }

  /**
   * 确保有**可用**的 access token；过期则用 refresh token 换新的。
   *
   * 判断依据必须是**是否过期**，不能只看「localStorage 里有没有字符串」：
   * access token 仅 30 分钟有效，refresh token 有 7 天，只看存在与否会让
   * 刷新机制形同虚设 —— 请求全部拿到 10102「登录已过期」，而用户既进不去
   * 页面、也没被引导去登录。
   */
  async function ensureValidToken(): Promise<boolean> {
    // 令牌存在且看起来仍有效 → 直接用
    if (accessToken.value && !isTokenExpired(accessToken.value)) return true
    // 没有 refresh token 就没得续，只能按未登录处理
    if (!refreshToken.value) {
      if (accessToken.value) clearAuth()
      return false
    }
    try {
      if (await refreshAccessToken()) {
        // refreshAccessToken 内部已写入 localStorage，这里同步内存中的值
        accessToken.value = localStorage.getItem(ACCESS_TOKEN_KEY) ?? ''
        if (accessToken.value) return true
      }
    } catch {
      /* 刷新过程中的任何异常都按失败处理，由下面统一清理 */
    }
    clearAuth()
    return false
  }

  return {
    accessToken,
    refreshToken,
    userInfo,
    isLoggedIn,
    hasUsableToken,
    setAuth,
    clearAuth,
    fetchUserInfo,
    ensureValidToken
  }
})
