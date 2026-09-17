/**
 * 行程分享接口。
 *
 * 分两组：
 * - 分享者侧（需登录 + 行程归属）：create/list/update/revoke
 * - 访问者侧（公开，无需登录）：inspect/openShared；copy 需要登录，extend 可选登录
 *
 * 注意访问者侧的令牌校验失败会返回业务码而不是 HTTP 401——
 * 后端业务异常统一是 HTTP 200 + 业务码（见 core/business/util.py）。
 */
import http from './http'
import type { ItineraryPlan } from './itinerary'

export type ShareStatus = 'active' | 'expired' | 'revoked'

export interface ShareItem {
  id: number
  itinerary_id: number
  token: string
  /** 后端拼好的完整链接，前端直接复制即可 */
  url: string
  allow_copy: boolean
  allow_edit: boolean
  has_password: boolean
  /** 明文密码：便于分享者再次查看自己设的密码 */
  password: string | null
  expires_at: string | null
  revoked_at: string | null
  view_count: number
  created_at: string
  status: ShareStatus
}

export interface CreateSharePayload {
  allow_copy?: boolean
  allow_edit?: boolean
  password?: string | null
  expires_in_days?: number | null
}

export interface ShareCheck {
  available: boolean
  requires_password: boolean
  reason: string | null
  destination: string | null
  days: number | null
}

export interface SharedItinerary {
  itinerary_id: number
  plan: ItineraryPlan
  allow_copy: boolean
  allow_edit: boolean
  view_count: number
  owner_name: string | null
  created_at: string
  updated_at: string
}

export interface ExtendResult {
  /** 改动是否已写入原行程：仅行程所有者本人通过分享链接编辑才为 true */
  is_applied: boolean
  plan: ItineraryPlan
}

// ==================== 分享者侧 ====================
export async function createShare(
  itineraryId: number,
  payload: CreateSharePayload
): Promise<ShareItem> {
  return (await http.post(`/itineraries/${itineraryId}/shares`, payload)) as unknown as ShareItem
}

export async function listShares(itineraryId: number): Promise<ShareItem[]> {
  const data = (await http.get(`/itineraries/${itineraryId}/shares`)) as unknown as {
    shares?: ShareItem[]
  }
  return data.shares ?? []
}

export async function updateShare(
  shareId: number,
  payload: CreateSharePayload,
  options: { clearPassword?: boolean; clearExpiry?: boolean } = {}
): Promise<ShareItem> {
  return (await http.patch(`/itineraries/shares/${shareId}`, payload, {
    params: {
      clear_password: options.clearPassword ?? false,
      clear_expiry: options.clearExpiry ?? false
    }
  })) as unknown as ShareItem
}

/**
 * 删除分享链接（物理删除，记录不再出现在列表里）。
 *
 * 后端返回 {id, deleted} 而不是被删对象——记录已不存在，
 * 序列化一个已删除的实体没有意义。
 */
export async function revokeShare(shareId: number): Promise<{ id: number; deleted: boolean }> {
  return (await http.delete(`/itineraries/shares/${shareId}`)) as unknown as {
    id: number
    deleted: boolean
  }
}

// ==================== 访问者侧（公开）====================
export async function inspectShare(token: string): Promise<ShareCheck> {
  return (await http.get(`/share/${token}`)) as unknown as ShareCheck
}

export async function openSharedItinerary(
  token: string,
  password?: string | null
): Promise<SharedItinerary> {
  return (await http.get(`/share/${token}/itinerary`, {
    params: password ? { pwd: password } : {}
  })) as unknown as SharedItinerary
}

export async function copySharedItinerary(
  token: string,
  password?: string | null
): Promise<{ id: number; plan: ItineraryPlan }> {
  return (await http.post(
    `/share/${token}/copy`,
    {},
    { params: password ? { pwd: password } : {} }
  )) as unknown as { id: number; plan: ItineraryPlan }
}

export async function extendSharedItinerary(
  token: string,
  changes: {
    budget?: number | null
    preferences?: string[] | null
    transport?: string | null
    tips?: string[] | null
  },
  password?: string | null
): Promise<ExtendResult> {
  return (await http.patch(`/share/${token}/itinerary`, changes, {
    params: password ? { pwd: password } : {}
  })) as unknown as ExtendResult
}

/** 分享失效原因 → 中文说明 */
export function shareReasonLabel(reason: string | null): string {
  switch (reason) {
    case 'expired':
      return '该分享链接已过期'
    case 'unavailable':
      return '该分享链接不存在或已被撤销'
    default:
      return '该分享链接当前不可用'
  }
}

/** 分享状态 → 展示文案与色值类别 */
export function shareStatusLabel(status: ShareStatus): { text: string; tone: string } {
  switch (status) {
    case 'active':
      return { text: '生效中', tone: 'ok' }
    case 'expired':
      return { text: '已过期', tone: 'warn' }
    default:
      return { text: '已撤销', tone: 'muted' }
  }
}
