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
   * 为什么需要：路由守卫此前只看「localStorage 里有没有令牌」。若残留一个
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

  /** 确保有可用 access token；过期则尝试 refresh */
  async function ensureValidToken(): Promise<boolean> {
    if (accessToken.value) return true
    if (!refreshToken.value) return false
    const ok = await refreshAccessToken()
    if (ok) {
      accessToken.value = localStorage.getItem(ACCESS_TOKEN_KEY) ?? ''
      return true
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
