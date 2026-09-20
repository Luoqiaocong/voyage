/**
 * 用户长期记忆接口。
 *
 * 记忆来自对话提炼，用户可查看/修正/停用/删除；停用后不再注入对话，
 * 但仍保留在库中（用 include_inactive=true 才能看到）。
 */
import http from './http'

export interface MemoryItem {
  id: number
  fact_key: string
  /** 后端给的中文标签，直接用即可，无需前端再维护一份映射 */
  fact_key_label: string
  fact_value: string
  /**
   * 拆开后的取值列表。
   *
   * 多值键（旅行偏好 / 饮食禁忌 / 去过的城市 / 同行人）在后端是
   * **一行一个键、多项用「、」连接**（详见后端 schemas 的说明），
   * 这里由后端拆好给前端 —— 前端不自己解析分隔符，
   * 否则拆分口径会有两份实现，容易与后端不一致。
   */
  values: string[]
  /** 是否多值键（决定能否逐项删除） */
  is_multi: boolean
  /** 被本次覆盖的旧值：能看出偏好是怎么变的 */
  previous_value: string | null
  confidence: number
  evidence: string | null
  hit_count: number
  is_active: boolean
  updated_at: string | null
}

export interface MemoryStats {
  total: number
  active: number
  inactive: number
  by_key: Record<string, number>
}

export interface MemoryListResult {
  memories: MemoryItem[]
  stats: MemoryStats
}

export async function listMemories(includeInactive = false): Promise<MemoryListResult> {
  return (await http.get('/memories/', {
    params: { include_inactive: includeInactive }
  })) as unknown as MemoryListResult
}

export async function updateMemoryValue(memoryId: number, factValue: string): Promise<MemoryItem> {
  return (await http.patch(`/memories/${memoryId}`, {
    fact_value: factValue
  })) as unknown as MemoryItem
}

export async function toggleMemory(memoryId: number, isActive: boolean): Promise<MemoryItem> {
  return (await http.patch(`/memories/${memoryId}/active`, {
    is_active: isActive
  })) as unknown as MemoryItem
}

export async function deleteMemory(memoryId: number): Promise<void> {
  await http.delete(`/memories/${memoryId}`)
}

/**
 * 从多值记忆里删掉**其中一项**（如「去过的城市」里去掉一座城）。
 *
 * 返回剩余的记录；若这是最后一项，后端会整行删除并返回 `{ deleted: true }`，
 * 调用方据此把整张卡片移除，而不是留一个空卡片。
 */
export async function removeMemoryValue(
  memoryId: number,
  factValue: string
): Promise<MemoryItem | { deleted: true }> {
  // 取值放路径：后端 Path 参数会自动 URL 解码，中文城市名需先编码
  return (await http.delete(
    `/memories/${memoryId}/values/${encodeURIComponent(factValue)}`
  )) as unknown as MemoryItem | { deleted: true }
}

export async function clearMemories(): Promise<{ deleted: number }> {
  return (await http.delete('/memories/')) as unknown as { deleted: number }
}

/**
 * 各键的取值约束（与后端 schemas.VALUE_ENUMS 保持一致）。
 *
 * 后端对手动修正也做枚举校验，前端提前用下拉框限制可避免无谓的失败请求。
 * 未列出的键是自由文本，用输入框即可。
 */
export const MEMORY_VALUE_OPTIONS: Record<string, string[]> = {
  budget_level: ['穷游', '经济', '舒适', '奢华'],
  travel_pace: ['紧凑', '适中', '悠闲']
}
