import http, { downloadFile, openTextExport } from './http'

export interface ItineraryActivity {
  time_slot: 'morning' | 'afternoon' | 'evening'
  kind: 'attraction' | 'restaurant' | 'hotel' | 'transport' | 'rest'
  name: string
  description: string
  duration_hours: number
  cost: number
  note?: string | null
}

export interface ItineraryDay {
  day_no: number
  date?: string | null
  theme: string
  activities: ItineraryActivity[]
  summary: string
}

export interface ItineraryPlan {
  destination: string
  days: number
  budget?: number | null
  preferences: string[]
  transport?: string | null
  accommodation?: ItineraryActivity | null
  daily_plans: ItineraryDay[]
  tips: string[]
}

export interface ItineraryDetail {
  id: number
  conversation_id: string | null
  plan: ItineraryPlan
  created_at: string
  updated_at: string
}

export interface ItineraryPatch {
  budget?: number | null
  preferences?: string[]
  transport?: string | null
  tips?: string[]
  accommodation?: ItineraryActivity | null
}

export async function listItineraries(): Promise<ItineraryDetail[]> {
  const data = (await http.get('/itineraries/')) as unknown as { itineraries?: ItineraryDetail[] }
  return data.itineraries ?? []
}

export async function getItinerary(id: number): Promise<ItineraryDetail> {
  return (await http.get(`/itineraries/${id}`)) as unknown as ItineraryDetail
}

export async function extractItinerary(conversationId: string): Promise<ItineraryDetail> {
  // 提取是一次同步 LLM 调用，耗时可达数十秒；http 实例默认 20s 会误判超时。
  return (await http.post(`/itineraries/extract/${conversationId}`, undefined, {
    timeout: 120000
  })) as unknown as ItineraryDetail
}

export async function updateItinerary(id: number, plan: ItineraryPlan): Promise<ItineraryDetail> {
  return http.put(`/itineraries/${id}`, plan)
}

export async function patchItinerary(id: number, patch: ItineraryPatch): Promise<ItineraryDetail> {
  return http.patch(`/itineraries/${id}`, patch)
}

export async function deleteItinerary(id: number): Promise<void> {
  await http.delete(`/itineraries/${id}`)
}

// ==================== 导出 ====================
// 三种导出都走独立的原始请求（见 http.ts 的 downloadFile/openTextExport）：
// 它们返回的是文件流/HTML 而非 JSON 信封，不能经过 http 实例的响应拦截器。

/** 导出为日历文件（.ics，可导入手机日历） */
export async function exportItineraryCalendar(id: number): Promise<void> {
  await downloadFile(`/itineraries/${id}/export/calendar.ics`, `itinerary-${id}.ics`)
}

/** 导出为 Markdown（浏览器无法优雅预览，直接下载） */
export async function exportItineraryMarkdown(id: number): Promise<void> {
  await openTextExport(`/itineraries/${id}/export/markdown`)
}

/** 打开打印友好页面（在新标签打开后可用 Ctrl+P 另存为 PDF） */
export async function openItineraryPrintView(id: number): Promise<void> {
  await openTextExport(`/itineraries/${id}/export/print`)
}
