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

/**
 * 带认证的原始请求（不经过 http 实例的响应拦截器）。
 *
 * 为什么不走 http 实例：它的拦截器会把信封剥成 `data`，
 * 而文件导出需要拿到原始 Blob 与 Content-Disposition 里的文件名。
 * 这里用原生 fetch：对 Blob 的处理更直接，并复刻了 http 实例
 * 「401 后用 refresh token 换新令牌再重试一次」的行为。
 */
async function fetchRaw(path: string): Promise<Response> {
  const doFetch = (token: string) =>
    fetch(`${API_BASE_URL}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })

  let res = await doFetch(getAccessToken())
  if (res.status === 401) {
    const ok = await refreshAccessToken()
    if (ok) res = await doFetch(getAccessToken())
  }
  if (!res.ok) {
    // 尽量把后端业务错误透出来，而不是抛一个笼统的失败
    let message = `请求失败（HTTP ${res.status}）`
    try {
      const body = (await res.json()) as ApiEnvelope
      if (body?.message) message = body.message
    } catch {
      /* 非 JSON 响应，保留默认提示 */
    }
    throw new ApiError(-1, message, res.status)
  }
  return res
}

/** 从 Content-Disposition 解析文件名，取不到则用兜底名 */
function filenameFrom(res: Response, fallback: string): string {
  const disposition = res.headers.get('Content-Disposition') ?? ''
  return /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? fallback
}

/** 触发浏览器下载一个 Blob */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** 下载需要认证的文件（CSV 导出、.ics 日历等） */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await fetchRaw(path)
  saveBlob(await res.blob(), filenameFrom(res, fallbackName))
}

/**
 * 打开文本类导出：
 * - 打印 HTML 在新标签页打开，用户可直接 Ctrl+P 存为 PDF；
 * - Markdown 浏览器无法优雅预览，走下载。
 */
export async function openTextExport(path: string): Promise<void> {
  const res = await fetchRaw(path)
  const contentType = res.headers.get('Content-Type') ?? ''

  if (contentType.includes('text/html')) {
    const html = await res.text()
    const win = window.open('', '_blank')
    if (win) {
      win.document.write(html)
      win.document.close()
    }
    return
  }
  saveBlob(await res.blob(), filenameFrom(res, 'export.md'))
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
