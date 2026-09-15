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
    setAuth,
    clearAuth,
    fetchUserInfo,
    ensureValidToken
  }
})
