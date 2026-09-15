import http from './http'

export interface Conversation {
  id: string
  title: string | null
  created_at: string
}

export interface ChatMessage {
  role: string
  content: string
}

export async function createConversation(): Promise<Conversation> {
  return http.post('/conversations/')
}

export async function listConversations(): Promise<Conversation[]> {
  const data = (await http.get('/conversations/')) as unknown as { conversations?: Conversation[] }
  return data.conversations ?? []
}

export async function getMessages(conversationId: string): Promise<unknown[]> {
  return http.get(`/conversations/${conversationId}/messages`)
}

export async function renameConversation(conversationId: string, title: string): Promise<void> {
  await http.patch(`/conversations/${conversationId}`, { title })
}

export async function deleteConversations(ids: string[]): Promise<void> {
  await http.post('/conversations/delete', { ids })
}

export type ChatChunk =
  | { type: 'text'; content: string }
  | { type: 'tool'; name: string; label: string; phase: 'call' | 'result'; content?: string }
  | { type: 'reasoning'; content: string }
  | { type: 'error'; content: string }
  | { type: 'title'; content: string }
  | { type: 'done' }

/** 内置工具的技术名 → 中文展示信息 */
const TOOL_META: Record<string, { label: string; icon: string }> = {
  get_weather: { label: '查询天气', icon: 'weather' },
  query_weather: { label: '查询天气', icon: 'weather' },
  get_train_tickets: { label: '查询车次票价', icon: 'train' },
  query_train_tickets: { label: '查询车次票价', icon: 'train' },
  search_train: { label: '查询车次票价', icon: 'train' },
  recommend_itinerary: { label: '生成行程推荐', icon: 'itinerary' },
  get_current_date: { label: '获取当前日期', icon: 'date' },
  get_date: { label: '获取当前日期', icon: 'date' }
}

export function toolLabel(name: string): { label: string; icon: string } {
  const meta = TOOL_META[name]
  if (meta) return meta
  // 未知工具：把 snake_case 还原成可读短语
  const pretty = name
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim()
  return { label: pretty || '工具调用', icon: 'generic' }
}

/** 工具结果压缩成一行摘要，避免把整段 JSON 铺在气泡里 */
export function summarizeToolResult(raw: string): string {
  const text = (raw ?? '').trim()
  if (!text) return ''
  // 结构化工具常返回 JSON：优先抽取可读字段
  if (text.startsWith('{') || text.startsWith('[')) {
    try {
      const obj = JSON.parse(text) as unknown
      const pick = extractReadable(obj)
      if (pick) return pick
    } catch {
      /* 不是合法 JSON，按纯文本处理 */
    }
  }
  return text.replace(/\s+/g, ' ').slice(0, 220)
}

function extractReadable(node: unknown, depth = 0): string {
  if (depth > 3 || node == null) return ''
  if (typeof node === 'string') return node.trim().slice(0, 200)
  if (typeof node === 'number' || typeof node === 'boolean') return String(node)
  if (Array.isArray(node)) {
    const parts = node
      .slice(0, 3)
      .map((v) => extractReadable(v, depth + 1))
      .filter(Boolean)
    const more = node.length > 3 ? ` 等 ${node.length} 项` : ''
    return parts.join('；') + more
  }
  const obj = node as Record<string, unknown>
  // 常见的结果字段优先
  for (const key of ['summary', 'message', 'text', 'content', 'result', 'data', 'answer']) {
    if (key in obj) {
      const v = extractReadable(obj[key], depth + 1)
      if (v) return v
    }
  }
  const entries = Object.entries(obj).slice(0, 4)
  return entries
    .map(([k, v]) => {
      const val = extractReadable(v, depth + 1)
      return val ? `${k}: ${val}` : ''
    })
    .filter(Boolean)
    .join(' · ')
    .slice(0, 220)
}


/**
 * POST SSE 流式对话（fetch 实现，POST 无法用 EventSource）
 * 事件格式：event: message + data: {type, ...}；结束 event: done + data: [DONE]
 */
export async function* streamChat(conversationId: string, message: string): AsyncGenerator<ChatChunk> {
  const { API_BASE_URL, getAccessToken, refreshAccessToken, clearAuthStorage } = await import('./http')
  let token = getAccessToken()

  const doFetch = () =>
    fetch(`${API_BASE_URL}/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({ message })
    })

  let res = await doFetch()
  if (res.status === 401) {
    const ok = await refreshAccessToken()
    if (!ok) {
      clearAuthStorage()
      yield { type: 'error', content: '登录已过期，请重新登录' }
      return
    }
    token = getAccessToken()
    res = await doFetch()
  }

  if (!res.ok) {
    let msg = `请求失败（HTTP ${res.status}）`
    try {
      const body = await res.json()
      msg = body?.message ?? body?.detail ?? msg
    } catch {
      /* 忽略非 JSON 错误体 */
    }
    yield { type: 'error', content: msg }
    return
  }

  const reader = res.body?.getReader()
  if (!reader) {
    yield { type: 'error', content: '浏览器不支持流式读取' }
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let event = 'message'

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let nl: number
      while ((nl = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, nl).replace(/\r$/, '')
        buffer = buffer.slice(nl + 1)

        if (!line || line.startsWith(':')) continue
        if (line.startsWith('event:')) {
          event = line.slice(6).trim()
          continue
        }
        if (line.startsWith('data:')) {
          const data = line.slice(5).trim()
          if (event === 'done' || data === '[DONE]') {
            yield { type: 'done' }
            return
          }
          try {
            const obj = JSON.parse(data) as Record<string, unknown>
            const t = String(obj.type ?? '')
            if (t === 'text') yield { type: 'text', content: String(obj.content ?? '') }
            else if (t === 'tool_call' || t === 'tool_result') {
              const name = String(obj.name ?? obj.tool_name ?? '工具')
              const { label } = toolLabel(name)
              yield {
                type: 'tool',
                name,
                label,
                phase: t === 'tool_call' ? 'call' : 'result',
                content: t === 'tool_result' ? summarizeToolResult(String(obj.content ?? '')) : undefined
              }
            } else if (t === 'reasoning') yield { type: 'reasoning', content: String(obj.content ?? '') }
            else if (t === 'title') yield { type: 'title', content: String(obj.content ?? '') }
            else if (t === 'error') yield { type: 'error', content: String(obj.content ?? 'AI 服务暂时不可用') }
          } catch {
            /* 非 JSON 帧忽略 */
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
