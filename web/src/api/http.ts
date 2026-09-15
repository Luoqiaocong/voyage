import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '@/constants'

/** 后端统一响应信封 */
export interface ApiEnvelope {
  code: number
  message: string
  data: any
}

const SUCCESS_CODES = new Set([20000, 20100, 20200, 20400])

export class ApiError extends Error {
  readonly code: number
  readonly httpStatus?: number

  constructor(code: number, message: string, httpStatus?: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.httpStatus = httpStatus
  }
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export function getAccessToken(): string {
  return localStorage.getItem(ACCESS_TOKEN_KEY) ?? ''
}

export function getRefreshToken(): string {
  return localStorage.getItem(REFRESH_TOKEN_KEY) ?? ''
}

export function clearAuthStorage(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

/** 用 refresh token 换新 access token（独立于拦截器，避免递归） */
let refreshing: Promise<boolean> | null = null
export function refreshAccessToken(): Promise<boolean> {
  const rt = getRefreshToken()
  if (!rt) return Promise.resolve(false)
  if (refreshing) return refreshing
  refreshing = (async () => {
    try {
      const res = await axios.post<ApiEnvelope>(API_BASE_URL + '/auth/refresh', {
        refresh_token: rt
      })
      const body = res.data
      if (body && body.code === 20000 && body.data?.access_token) {
        localStorage.setItem(ACCESS_TOKEN_KEY, body.data.access_token)
        return true
      }
      return false
    } catch {
      return false
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000
})

http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiEnvelope | unknown
    if (body && typeof body === 'object' && 'code' in body) {
      const envelope = body as ApiEnvelope
      if (SUCCESS_CODES.has(envelope.code)) return envelope.data
      return Promise.reject(new ApiError(envelope.code, envelope.message || '请求失败', response.status))
    }
    return response.data
  },
  async (error: AxiosError<ApiEnvelope>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined

    // 401：用 refresh token 换新 token 后重试一次
    if (error.response?.status === 401 && original && !original._retry) {
      const ok = await refreshAccessToken()
      if (ok) {
        original._retry = true
        original.headers.Authorization = `Bearer ${getAccessToken()}`
        try {
          return await http(original)
        } catch (retryErr) {
          return Promise.reject(retryErr)
        }
      }
    }

    if (error.response?.status === 401) {
      clearAuthStorage()
      if (!window.location.pathname.startsWith('/login')) {
        window.location.assign('/login')
      }
    }

    const data = error.response?.data
    let code = -1
    let message = error.message || '网络异常，请稍后重试'
    if (data && typeof data === 'object') {
      const rec = data as unknown as Record<string, unknown>
      if (typeof rec.code !== 'undefined') code = Number(rec.code) || -1
      if (typeof rec.message === 'string') message = rec.message
      else if (typeof rec.detail === 'string') message = rec.detail
    }
    return Promise.reject(new ApiError(code, message, error.response?.status))
  }
)

export default http
