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
