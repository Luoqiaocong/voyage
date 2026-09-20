import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from '@/constants'
import { emitSessionExpired } from '@/utils/session'

/** 后端统一响应信封 */
export interface ApiEnvelope {
  code: number
  message: string
  data: any
}

const SUCCESS_CODES = new Set([20000, 20100, 20200, 20400])

/**
 * 「需要重新登录」的业务码。
 *
 * ## 为什么必须有这组常量
 *
 * 后端把鉴权失败表达成 **HTTP 200 + 业务码**，而不是 HTTP 401 ——
 * 见 app/core/business/util.py：`BaseBusinessException` 的处理器一律
 * 返回 `status_code=200`。所以令牌过期时前端拿到的是一个**成功响应**，
 * 只有在信封里才看得出失败：
 *
 *   { code: 10102, message: "登录已过期，请重新登录" }   ← 用户看到的就是这句
 *
 * 而原先的拦截器只在 `error.response.status === 401` 时才刷新令牌，
 * 那条分支永远命中不了 —— 于是 refresh token（7 天有效）从未被使用过，
 * 用户每 30 分钟就被弹一次「请重新登录」。
 *
 * 对应 app/core/business/code.py：
 *   10101 UNAUTHORIZED  未授权，请先登录
 *   10102 TOKEN_EXPIRED 登录已过期，请重新登录
 *   10103 TOKEN_INVALID 无效的令牌
 */
const AUTH_FAILED_CODES = new Set([10101, 10102, 10103])

export class ApiError extends Error {
  readonly code: number
  /** HTTP 状态码。信封式失败（HTTP 200 + 业务码）时为 200 —— 用来区分
   *  「会话失效」与「网络/服务不可达」：后者不该把用户登出。 */
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
 * 这里用原生 fetch，并复用与拦截器同一套会话处理。
 */
async function fetchRaw(path: string): Promise<Response> {
  const doFetch = (token: string) =>
    fetch(`${API_BASE_URL}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })

  let res = await doFetch(getAccessToken())

  /*
   * 鉴权失败要先刷新令牌再重放。
   *
   * 除了 HTTP 401，还要看**业务码** —— 导出接口同样可能返回
   * HTTP 200 + 10102「登录已过期」。只判 401 会漏掉主路径。
   * 通过 clone() 读一份响应体做判断，不影响后面取 Blob。
   */
  let authFailed = res.status === 401
  if (!authFailed && res.ok) {
    try {
      const body = (await res.clone().json()) as ApiEnvelope
      if (body && typeof body.code === 'number' && AUTH_FAILED_CODES.has(body.code)) {
        authFailed = true
      }
    } catch {
      /* 非 JSON（例如直接返回文件流）——正常情况，忽略 */
    }
  }

  if (authFailed) {
    try {
      res = await retryAfterRefresh(() => doFetch(getAccessToken()))
    } catch (e) {
      // retryAfterRefresh 已在刷新失败时清理并跳登录页，这里只需把错误传出去
      throw e instanceof ApiError ? e : new ApiError(-1, '登录已过期，请重新登录', 200)
    }
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

/** 会话已失效：清掉本地令牌并通知应用跳登录页（带回跳地址） */
function handleSessionExpired(message?: string): void {
  clearAuthStorage()
  emitSessionExpired(message)
}

/**
 * 遇到鉴权失败时的统一处理：先尝试用 refresh token 换新令牌并重放请求；
 * 换不到才算真正失效（清令牌 + 跳登录页）。
 *
 * 抽出来是因为**有两条入口**都要用它：
 *   1. HTTP 401（网关/中间件层拒绝）
 *   2. HTTP 200 + 业务码 10101/10102/10103（业务异常层的拒绝，本项目的主路径）
 * 原先只处理了第 1 条，而实际发生的是第 2 条。
 */
async function retryAfterRefresh<T>(
  request: () => Promise<T>,
  message?: string
): Promise<T> {
  const ok = await refreshAccessToken()
  if (!ok) {
    handleSessionExpired(message)
    throw new ApiError(10102, message || '登录已过期，请重新登录', 200)
  }
  return request()
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
  async (response) => {
    const body = response.data as ApiEnvelope | unknown
    if (body && typeof body === 'object' && 'code' in body) {
      const envelope = body as ApiEnvelope
      if (SUCCESS_CODES.has(envelope.code)) return envelope.data

      /*
       * 鉴权类业务码：HTTP 是 200，但语义上等价于 401。
       * 这里先刷新令牌重放一次；成功则用户完全无感，失败才跳登录页。
       *
       * 用 _retry 标记防死循环：刷新后仍失败说明 refresh token 也无效了，
       * 此时不该再重试。
       */
      const cfg = response.config as InternalAxiosRequestConfig & { _retry?: boolean }
      if (AUTH_FAILED_CODES.has(envelope.code) && !cfg._retry) {
        cfg._retry = true
        return retryAfterRefresh(
          () => http(cfg) as Promise<unknown>,
          envelope.message
        )
      }

      return Promise.reject(
        new ApiError(envelope.code, envelope.message || '请求失败', response.status)
      )
    }
    return response.data
  },
  async (error: AxiosError<ApiEnvelope>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined

    // HTTP 401：同样先刷新再重放一次
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true
      original.headers.Authorization = `Bearer ${getAccessToken()}`
      try {
        return await retryAfterRefresh(() => http(original) as Promise<unknown>)
      } catch (retryErr) {
        return Promise.reject(retryErr)
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
