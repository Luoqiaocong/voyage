/**
 * 会话失效的统一处理。
 *
 * ## 为什么需要这个模块
 *
 * 后端把「登录已过期」表达成 **HTTP 200 + 业务码 10102**，而不是 HTTP 401
 * （见 app/core/business/util.py：BaseBusinessException 一律返 200）。
 * 本模块在收到该业务码时负责：
 *
 *   1. 清理登录态（localStorage + Pinia store）
 *   2. **带上回跳地址**跳到登录页，登录后能回到原处
 *
 * ## 为什么用自定义事件而不是直接 import store
 *
 * `stores/user.ts` 已经 import 了 `api/http.ts`。若 http 再 import store
 * 就形成循环依赖（模块初始化顺序会变得不可预测）。
 * 事件把依赖方向掰成单向：
 *
 *   http.ts ──dispatch──▶ SESSION_EXPIRED_EVENT ──listen──▶ main.ts ──▶ store + router
 */

/** 会话失效事件名（http 层派发，应用入口监听） */
export const SESSION_EXPIRED_EVENT = 'voyage:session-expired'

/** 事件携带的信息 */
export interface SessionExpiredDetail {
  /** 展示给用户的原因；缺省用一句通用文案 */
  message?: string
}

/** 派发「会话已失效」。登录页自身不派发，避免在登录页反复弹提示。 */
export function emitSessionExpired(message?: string): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(
    new CustomEvent<SessionExpiredDetail>(SESSION_EXPIRED_EVENT, {
      detail: { message }
    })
  )
}
