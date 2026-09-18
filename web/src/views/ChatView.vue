<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import MessageBody from '@/components/MessageBody.vue'
import ToolTimeline from '@/components/ToolTimeline.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import type { ToolStep } from '@/types/tool'
import {
  createConversation,
  deleteConversations,
  getMessagesPage,
  listConversations,
  renameConversation,
  streamChat,
  toolLabel,
  type ChatMessage,
  type Conversation,
  type MessagesPage
} from '@/api/conversation'
import { extractItinerary } from '@/api/itinerary'
import { useUiStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'
import { PAGE_COPY } from '@/constants/copy'

/** 会话消息：assistant 消息可携带本轮的工具调用与思考过程 */
interface RdMsg extends ChatMessage {
  tools?: ToolStep[]
  reasoning?: string
}

/** 打开会话时默认加载的历史轮次（一轮 = 一条用户消息及其后的回复） */
const HISTORY_ROUNDS = 30

const router = useRouter()
const route = useRoute()
const ui = useUiStore()
const user = useUserStore()

const conversations = ref<Conversation[]>([])
const activeId = ref<string | null>(null)
const messages = ref<RdMsg[]>([])
/** 更早的历史是否被截断（后端按轮次分页），用于给出提示 */
const historyTruncated = ref(false)
const input = ref('')
const loadingList = ref(false)
const streaming = ref(false)

const activeConversation = computed(
  () => conversations.value.find((c) => c.id === activeId.value) ?? null
)

const scrollEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)

/* ---------------- 流式临时状态 ---------------- */
const streamText = ref('')
const streamReasoning = ref('')
const streamTools = ref<ToolStep[]>([])
const streamError = ref('')
const showReasoning = ref(false)

/** 工具调用序号，保证 v-for key 稳定 */
let toolSeq = 0

/** 助手正在工作但还没有任何可见输出 */
const thinking = computed(
  () => streaming.value && !streamText.value && !streamTools.value.length && !streamError.value
)

/** 当前流式阶段，用于顶部状态条 */
const streamPhase = computed(() => {
  if (!streaming.value) return ''
  const running = streamTools.value.find((t) => t.status === 'running')
  if (running) return `正在调用 ${running.label}`
  if (streamTools.value.length) return '正在整合工具结果'
  if (streamText.value) return '正在生成回答'
  if (streamReasoning.value) return '正在思考'
  return '正在理解你的需求'
})

function scrollToBottom(smooth = false) {
  nextTick(() => {
    const el = scrollEl.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  })
}

/* ---------------- 数据加载 ---------------- */
async function loadConversations() {
  loadingList.value = true
  try {
    conversations.value = await listConversations()
  } catch (e: any) {
    ui.toast(e?.message ?? '会话列表加载失败', 'error')
  } finally {
    loadingList.value = false
  }
}

/**
 * 把后端返回的历史消息规整成可渲染的消息列表。
 *
 * 兼容两种响应形状：
 * - 分页对象 `{ messages, total_rounds, returned_rounds, truncated }`（当前后端）
 * - 裸数组 `[...]`（更早的后端版本）
 *
 * 后端在「历史消息分页」这次改动中把返回从数组改成了分页对象，
 * 而调用方当时仍按数组遍历，导致 `for...of` 抛 "raw is not iterable"，
 * 整条历史记录都渲染不出来。这里做形状归一，避免后端再次调整时同类问题复发。
 */
function normalizeMessages(payload: unknown): RdMsg[] {
  const list: unknown[] = Array.isArray(payload)
    ? payload
    : Array.isArray((payload as { messages?: unknown })?.messages)
      ? ((payload as { messages: unknown[] }).messages)
      : []

  const out: RdMsg[] = []
  for (const item of list) {
    const m = (item ?? {}) as { role?: string; content?: unknown }
    let content = m.content ?? ''
    // content 可能是多模态数组（[{type:'text', text:'...'}]），拼成纯文本
    if (Array.isArray(content)) {
      content = content
        .map((p) => (typeof p === 'string' ? p : ((p as { text?: string })?.text ?? '')))
        .join('')
    }
    const text = String(content).trim()
    // 跳过空内容：工具调用产生的中间态 assistant 消息没有文本，
    // 保留会渲染成空气泡
    if (!text) continue
    out.push({
      role: m.role === 'user' ? 'user' : 'assistant',
      content: text
    })
  }
  return out
}

async function openConversation(id: string) {
  if (streaming.value) return
  activeId.value = id
  messages.value = []
  resetStream()
  try {
    // 用带 limit 的分页版本：长会话不必一次拉全量，减少首屏等待
    const page = (await getMessagesPage(id, HISTORY_ROUNDS)) as MessagesPage
    messages.value = normalizeMessages(page)
    historyTruncated.value = page.truncated

    // 顺手缓存摘要：这次已取到消息，可直接用首条用户消息，
    // 不必再为同一个会话多发一次请求
    const firstUser = messages.value.find((m) => m.role === 'user' && m.content.trim())
    if (firstUser && !convSummary.value[id]) {
      convSummary.value = { ...convSummary.value, [id]: summarize(firstUser.content) }
    }
  } catch (e: any) {
    ui.toast(e?.message ?? '历史消息加载失败', 'error')
    // 历史没取到，摘要也补一次（独立请求，失败静默）
    void cacheSummary(id)
  }
  scrollToBottom()
}

function resetStream() {
  streamText.value = ''
  streamReasoning.value = ''
  streamTools.value = []
  streamError.value = ''
  showReasoning.value = false
}

async function newConversation() {
  if (streaming.value) return
  try {
    const conv = await createConversation()
    if (!conversations.value.some((c) => c.id === conv.id)) {
      conversations.value.unshift(conv)
    }
    await openConversation(conv.id)
    inputEl.value?.focus()
  } catch (e: any) {
    ui.toast(e?.message ?? '创建会话失败', 'error')
  }
}

/**
 * 内联重命名状态：正在编辑哪个会话、草稿标题。
 *
 * 为什么不用 window.prompt：那是浏览器原生弹窗，无法套用站点样式，
 * 移动端尤其突兀（会顶掉整个页面），且与页面的视觉体系完全脱节。
 * 标题本来就短，直接就地改最自然——点铅笔，标题原地变成输入框。
 */
const editingId = ref<string | null>(null)
const editingTitle = ref('')
const renameInputEl = ref<HTMLInputElement | null>(null)

/** 进入编辑态并聚焦（等 DOM 更新后再选，否则元素还不存在） */
function startRename(conv: Conversation) {
  editingId.value = conv.id
  editingTitle.value = conv.title ?? ''
  nextTick(() => {
    renameInputEl.value?.focus()
    renameInputEl.value?.select()
  })
}

function cancelRename() {
  editingId.value = null
  editingTitle.value = ''
}

/** 提交重命名。失败时保留编辑态，让用户能直接改而不是重来一遍 */
async function commitRename(conv: Conversation) {
  if (editingId.value !== conv.id) return
  const trimmed = editingTitle.value.trim()
  const original = conv.title ?? ''

  if (!trimmed || trimmed === original) {
    cancelRename()
    return
  }
  if (trimmed.length > 64) {
    ui.toast('标题不能超过 64 个字符', 'error')
    return
  }
  try {
    await renameConversation(conv.id, trimmed)
    conv.title = trimmed
    cancelRename()
  } catch (e: any) {
    ui.toast(e?.message ?? '修改标题失败', 'error')
  }
}

/** 编辑框的键盘处理：回车保存、Esc 取消 */
function onRenameKey(e: KeyboardEvent, conv: Conversation) {
  if (e.key === 'Enter') {
    e.preventDefault()
    void commitRename(conv)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    cancelRename()
  }
}

/**
 * 工具条的「重命名」：重命名是就地编辑，输入框在侧栏里。
 * 所以这里要先把侧栏备好——桌面端若已折叠就展开，
 * 窄屏则唤出抽屉，否则用户点了按钮却看不到任何反应。
 */
function renameFromToolbar() {
  const conv = activeConversation.value
  if (!conv) return
  if (window.matchMedia('(max-width: 860px)').matches) sideOpen.value = true
  else sideFolded.value = false
  startRename(conv)
}

async function handleDelete(conv: Conversation) {
  const sure = await ui.confirm(`确定删除会话「${conv.title ?? conv.id}」吗？历史与 AI 记忆将一并清除。`)
  if (!sure) return
  try {
    await deleteConversations([conv.id])
    conversations.value = conversations.value.filter((c) => c.id !== conv.id)
    if (activeId.value === conv.id) {
      activeId.value = null
      messages.value = []
    }
    ui.toast('会话已删除', 'success')
  } catch (e: any) {
    ui.toast(e?.message ?? '删除失败', 'error')
  }
}

/**
 * 取当前会话里「会被后端提取的那条消息」——即最后一条有文本的 AI 回复。
 *
 * 后端 /itineraries/extract/{id} 的 id 是**会话 ID**，提取范围由服务端定为
 * 「最后一条 AI 文本」（见 app/modules/itinerary/service.py 的 get_last_ai_text），
 * 前端无法指定某条消息。所以界面上必须按这个口径来说明与判断，
 * 否则用户会以为能从任意一条历史回答里提取。
 */
function lastAiMessage(): RdMsg | null {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i]
    if (m.role === 'assistant' && typeof m.content === 'string' && m.content.trim()) {
      return m
    }
  }
  return null
}

/**
 * 对话轮数（一问一答算一轮）。
 *
 * 用助手回复条数而非用户消息条数：用户可能连发几条才得到一次回答，
 * 按用户消息数会高估进度。
 */
const rounds = computed(
  () =>
    messages.value.filter(
      (m) => m.role === 'assistant' && typeof m.content === 'string' && m.content.trim()
    ).length
)

/**
 * 是否具备提取条件（存在 AI 回复）。
 *
 * 只判断「有没有可提取的文本」，不判断「像不像行程」——
 * 内容预判已被证明两个方向都会出错（见 handleExtract 里的说明），
 * 真正的判定器在后端。这里仅用于把按钮置灰并给出提示，
 * 让用户在点之前就知道为什么不能点。
 */
const canExtract = computed(() => lastAiMessage() !== null)

async function handleExtract() {
  if (!activeId.value || streaming.value) return

  const target = lastAiMessage()
  if (!target) {
    ui.toast('这个会话里还没有 AI 回复，无法提取', 'error')
    return
  }

  // 这里刻意**不做内容预判**。
  //
  // 曾经加过一个 looksLikeItinerary() 启发式（要求出现 Day N 且时段/要素达标），
  // 想拦住「最后一条是收尾语、提取会编造」的情况。实测证明它两向都错：
  //   - 误拦真行程：一份含「路线/高铁/酒店/预算/行程」6 个要素的攻略，
  //     因没写「Day 1」而被拦（真实数据里 8 个会话只放行 1 个）
  //   - 放行非行程：纯车次表因车次号里的 "D7" 被误判成天数标记而通过
  // 根源是「这段文本能否被 LLM 抽成行程」本质上猜不准。
  // 真正的判定器在后端：extract_itinerary_plan 失败返回 None，
  // service 抛 ITINERARY_GEN_FAILED，**不会编造**。所以交给它判断即可。
  const sure = await ui.confirm(
    '将从本会话「最后一条 AI 回复」提取行程。\n\n' +
      `后端只取最后一条 AI 回复（不是整个对话），当前这条约 ${target.content.length} 字。\n` +
      '若它不是行程安排，提取会失败且不会生成任何行程。继续？'
  )
  if (!sure) return

  ui.toast('AI 正在提取行程，请稍候…', 'info')
  try {
    const it = await extractItinerary(activeId.value)
    ui.toast(`行程已提取：${it.plan.destination}（${it.plan.days} 天）`, 'success', 4200)
    router.push(`/itineraries/${it.id}`)
  } catch (e: any) {
    ui.toast(e?.message ?? '行程提取失败，请确认最后一条 AI 回复中包含完整行程', 'error')
  }
}

/* ---------------- 发送 ---------------- */
async function send() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  input.value = ''
  await runTurn(text, true)
}

/**
 * 执行一轮对话。
 *
 * @param text      要发送的内容
 * @param echoUser  是否把这条用户消息追加到界面。
 *                  「重新生成」复用同一段逻辑但传 false——那条用户消息已经在列表里了，
 *                  再插一次会出现两条一样的提问。
 */
async function runTurn(text: string, echoUser: boolean) {
  if (!text || streaming.value) return

  if (!activeId.value) {
    try {
      const conv = await createConversation()
      if (!conversations.value.some((c) => c.id === conv.id)) {
        conversations.value.unshift(conv)
      }
      activeId.value = conv.id
    } catch (e: any) {
      ui.toast(e?.message ?? '创建会话失败', 'error')
      return
    }
  }

  const cid = activeId.value!
  if (echoUser) messages.value.push({ role: 'user', content: text })
  streaming.value = true
  resetStream()
  scrollToBottom()

  let finished = false

  try {
    for await (const chunk of streamChat(cid, text)) {
      if (chunk.type === 'text') {
        streamText.value += chunk.content
        scrollToBottom()
      } else if (chunk.type === 'tool') {
        applyToolChunk(chunk.name, chunk.label, chunk.phase, chunk.content)
        scrollToBottom()
      } else if (chunk.type === 'reasoning') {
        streamReasoning.value += chunk.content
      } else if (chunk.type === 'title') {
        const conv = conversations.value.find((c) => c.id === cid)
        if (conv) conv.title = chunk.content
      } else if (chunk.type === 'error') {
        streamError.value = chunk.content
        scrollToBottom()
      } else if (chunk.type === 'done') {
        finished = true
        commitAssistant()
      }
    }
  } catch (e: any) {
    streamError.value = e?.message ?? '对话请求失败'
  } finally {
    if (!finished) {
      if (!streamText.value.trim() && !streamTools.value.length) {
        streamError.value = streamError.value || 'AI 响应中断，请重试'
      } else {
        commitAssistant()
      }
    }
    streaming.value = false
    resetStream()
    scrollToBottom(true)
    inputEl.value?.focus()
  }
}

/* ---------------- 消息操作 ---------------- */
/** 复制某条消息的纯文本（Markdown 原文，便于粘到别处保留结构） */
async function copyMessage(msg: RdMsg) {
  try {
    await navigator.clipboard.writeText(msg.content)
    ui.toast('已复制到剪贴板', 'success')
  } catch {
    // 非 HTTPS 或未授权时 clipboard 不可用，退回手动选择
    ui.toast('复制失败，请手动选择文本', 'error')
  }
}

/**
 * 重新生成：把上一条用户提问重发一遍。
 *
 * 不做「删除旧回答」——保留历史能让用户对比两次结果，
 * 而删掉再生成会让人怀疑是不是真的重跑了。
 */
async function regenerate(index: number) {
  if (streaming.value) return
  // 往前找到最近的一条用户消息
  let prev = ''
  for (let i = index - 1; i >= 0; i--) {
    if (renderedMessages.value[i]?.role === 'user') {
      prev = renderedMessages.value[i].content
      break
    }
  }
  if (!prev) {
    ui.toast('找不到对应的提问，无法重新生成', 'error')
    return
  }
  await runTurn(prev, false)
}

/* ---------------- 会话搜索 ---------------- */
const convKeyword = ref('')

/** 窄屏抽屉开关：侧栏在手机上收起，需要能主动唤出 */
const sideOpen = ref(false)

/**
 * 桌面端侧栏折叠。
 *
 * 与 sideOpen 分开的原因：两者语义不同——
 *   sideOpen   窄屏抽屉是否唤出（移动端）
 *   sideFolded 桌面端是否收起侧栏（宽屏，给对话区让宽度）
 * 合成一个状态会导致宽屏抽屉化、窄屏收不起来。
 */
const sideFolded = ref(false)

/** 侧栏宽度由 CSS 变量控制，折叠时主区自动铺满，无需 JS 参与布局 */
function toggleFold() {
  sideFolded.value = !sideFolded.value
}

/**
 * 会话摘要缓存：{ 会话 id -> 首条用户消息的截断 }。
 *
 * Conversation 类型只有 id/title/created_at，后端不返回摘要，
 * 所以只能按需补取。这里取「首条用户消息」而不是标题：
 * 标题是模型概括的，首条消息才看得出用户当时想干什么。
 *
 * 只对**当前打开的会话**补取（见 openConversation），
 * 不在列表加载时批量拉取——那会随会话数线性增长地打接口。
 */
const convSummary = ref<Record<string, string>>({})

/** 最多缓存的摘要条数，防止长会话列表把内存堆满 */
const SUMMARY_CACHE_MAX = 60

function summarize(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, 34)
}

async function cacheSummary(id: string) {
  if (convSummary.value[id]) return
  try {
    const page = (await getMessagesPage(id, 1)) as MessagesPage
    /*
     * content 的类型是 string | unknown[]（多模态消息的内容是数组）。
     * 摘要只对纯文本有意义，所以这里显式判类型，
     * 不能直接 .trim()——类型检查会挡，运行时数组也没有 trim。
     */
    const first = (page.messages ?? []).find(
      (m) => m.role === 'user' && typeof m.content === 'string' && m.content.trim()
    )
    if (!first || typeof first.content !== 'string') return
    const next = { ...convSummary.value, [id]: summarize(first.content) }
    // 超限时丢掉最早的一批，避免无限增长
    const keys = Object.keys(next)
    if (keys.length > SUMMARY_CACHE_MAX) {
      for (const k of keys.slice(0, keys.length - SUMMARY_CACHE_MAX)) delete next[k]
    }
    convSummary.value = next
  } catch {
    // 摘要属于增强信息，取不到就不显示，不打扰用户
  }
}

/** 按标题或已缓存摘要过滤会话；空关键词返回全部 */
const filteredConversations = computed(() => {
  const kw = convKeyword.value.trim().toLowerCase()
  if (!kw) return conversations.value
  return conversations.value.filter((c) => {
    const title = (c.title ?? '').toLowerCase()
    const sum = (convSummary.value[c.id] ?? '').toLowerCase()
    return title.includes(kw) || sum.includes(kw)
  })
})

/** 会话项显示的时间：今天显示时刻，更早显示日期，避免一长串相同日期 */
function convTime(createdAt?: string): string {
  if (!createdAt) return ''
  const d = new Date(createdAt)
  if (Number.isNaN(d.getTime())) return createdAt.slice(0, 10)
  const now = new Date()
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  if (sameDay) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return `${d.getMonth() + 1}/${d.getDate()}`
}

/** 快捷示例：空态与输入框上方共用，改一处即可 */
const QUICK_PROMPTS = [
  '帮我规划广州到北京的 3 天行程',
  '这周末去成都穿什么？',
  '查一下明天广州南到北京西的高铁'
]

/**
 * 是否展示快捷示例。
 * 只在「没在生成」且「输入框为空」时出现：用户一开始打字，
 * 建议就从帮助变成了干扰，而且那一行会把输入框顶上去。
 */
const showQuickChips = computed(() => !streaming.value && !input.value.trim())

/** 把工具事件合并进当前时间线：result 会回填到同名且仍在运行的步骤 */
function applyToolChunk(name: string, label: string, phase: 'call' | 'result', content?: string) {
  if (phase === 'call') {
    // 同名工具可能被连续调用多次，只有最后一个仍在运行的才复用
    const pending = [...streamTools.value].reverse().find((t) => t.name === name && t.status === 'running')
    if (!pending) {
      streamTools.value.push({
        id: `t${++toolSeq}`,
        name,
        label: label || toolLabel(name).label,
        icon: toolLabel(name).icon,
        status: 'running'
      })
    }
    return
  }

  const pending = [...streamTools.value].reverse().find((t) => t.name === name && t.status === 'running')
  if (pending) {
    pending.status = 'done'
    pending.result = content
  } else {
    // 只收到 result（例如历史回放）：补一条已完成记录
    streamTools.value.push({
      id: `t${++toolSeq}`,
      name,
      label: label || toolLabel(name).label,
      icon: toolLabel(name).icon,
      status: 'done',
      result: content
    })
  }
}

/** 把当前流式内容固化为一条历史消息 */
function commitAssistant() {
  const hasBody = !!streamText.value.trim()
  const hasTools = streamTools.value.length > 0
  if (!hasBody && !hasTools && !streamError.value) return
  messages.value.push({
    role: 'assistant',
    content: streamError.value || streamText.value,
    tools: hasTools ? streamTools.value.map((t) => ({ ...t, status: t.status === 'running' ? 'done' : t.status })) : undefined,
    reasoning: streamReasoning.value || undefined
  })
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

/** 送入渲染的列表：历史消息 + 正在流式的这一条 */
const renderedMessages = computed<RdMsg[]>(() => {
  const list = [...messages.value]
  if (!streaming.value) return list
  const live: RdMsg = {
    role: 'assistant',
    content: streamError.value || streamText.value,
    tools: streamTools.value.length ? streamTools.value : undefined,
    reasoning: streamReasoning.value || undefined
  }
  if (live.content || live.tools || live.reasoning) list.push(live)
  return list
})

onMounted(async () => {
  user.fetchUserInfo().catch(() => {})
  await loadConversations()
  if (conversations.value.length > 0) {
    await openConversation(conversations.value[0].id)
  }

  // 首页示例胶囊带来的问题：填进输入框并聚焦，用户确认后直接回车发送。
  // 这里刻意不自动发送——自动发出去会让用户失去修改措辞的机会，
  // 而示例文案本就是给人改的起点。
  const raw = route.query.example
  const example = Array.isArray(raw) ? raw[0] : raw
  if (typeof example === 'string' && example.trim()) {
    input.value = example.trim()
    await nextTick()
    // 进入时清掉 query，避免刷新或返回时重复填充
    router.replace({ path: route.path })
  }
})

watch(streaming, (v) => {
  if (!v) scrollToBottom()
})
</script>

<template>
  <div class="chat-page">
    <AppNavbar />

    <main id="main" tabindex="-1" class="chat-main">
      <!-- ==================== 侧边栏 ==================== -->
      <!-- 窄屏为抽屉，遮罩点击关闭 -->
      <div v-if="sideOpen" class="side-backdrop" @click="sideOpen = false"></div>
      <aside
        class="chat-side"
        :class="{ 'chat-side--open': sideOpen, 'chat-side--folded': sideFolded }"
        aria-label="会话列表"
      >
        <div class="chat-side__head">
          <span class="chat-side__title">我的会话</span>
          <span v-if="conversations.length" class="chat-side__count">{{ conversations.length }}</span>
          <!-- 折叠：会话多时把侧栏收起，给对话区让出宽度 -->
          <button
            class="side-fold"
            type="button"
            :aria-label="sideFolded ? '展开会话列表' : '收起会话列表'"
            :title="sideFolded ? '展开' : '收起'"
            @click="toggleFold"
          >
            <TravelIcon :name="sideFolded ? 'arrow-right' : 'arrow-left'" :size="15" />
          </button>
        </div>

        <!-- 新建：主操作，占满整行比挤在标题旁更好点 -->
        <button class="side-new" type="button" :disabled="streaming" @click="newConversation">
          <span class="side-new__icon" aria-hidden="true">
            <TravelIcon name="plane" :size="15" />
          </span>
          开始新会话
        </button>

        <!-- 会话搜索：会话一多就必须能找回来 -->
        <div v-if="conversations.length" class="chat-side__search">
          <TravelIcon name="compass" :size="14" />
          <input
            v-model="convKeyword"
            type="search"
            placeholder="搜索标题或内容…"
            aria-label="搜索会话"
          />
          <button v-if="convKeyword" class="chat-side__clear" aria-label="清除搜索" @click="convKeyword = ''">
            ✕
          </button>
        </div>

        <div v-if="loadingList" class="chat-side__loading">
          <span class="skel skel--line"></span>
          <span class="skel skel--line"></span>
          <span class="skel skel--line"></span>
        </div>

        <!-- 空状态：没有任何会话 -->
        <div v-else-if="!conversations.length" class="chat-side__empty">
          <span class="chat-side__empty-icon" aria-hidden="true">
            <TravelIcon name="luggage" :size="26" />
          </span>
          <p>还没有出行计划</p>
          <span>点上方「开始新会话」，说说你想去哪</span>
        </div>

        <!-- 空状态：搜索无结果 -->
        <div v-else-if="!filteredConversations.length" class="chat-side__empty">
          <span class="chat-side__empty-icon" aria-hidden="true">
            <TravelIcon name="map" :size="26" />
          </span>
          <p>没有匹配的会话</p>
          <span>换个关键词，或清空搜索</span>
        </div>

        <ul v-else class="chat-side__list">
          <li v-for="conv in filteredConversations" :key="conv.id">
            <!--
              用 button 而非可点击的 li：原生支持 Tab 聚焦与回车/空格触发，
              读屏器也能正确播报为可操作项。li 保留在外层维持列表语义。
            -->
            <button
              type="button"
              class="conv-item"
              :class="{ 'conv-item--active': conv.id === activeId }"
              :aria-current="conv.id === activeId ? 'true' : undefined"
              @click="openConversation(conv.id); sideOpen = false"
            >
              <span class="conv-item__pin" aria-hidden="true"></span>
              <span class="conv-item__main">
                <!-- 编辑态：标题原地变成输入框，不弹窗 -->
                <input
                  v-if="editingId === conv.id"
                  ref="renameInputEl"
                  v-model="editingTitle"
                  class="conv-item__edit"
                  type="text"
                  maxlength="64"
                  aria-label="会话标题"
                  @click.stop
                  @keydown="onRenameKey($event, conv)"
                  @blur="commitRename(conv)"
                />
                <span v-else class="conv-item__title">{{ conv.title || '新会话' }}</span>

                <!-- 摘要取该会话首条用户消息，比标题更能说明聊了什么 -->
                <span v-if="convSummary[conv.id] && editingId !== conv.id" class="conv-item__sum">
                  {{ convSummary[conv.id] }}
                </span>
                <span class="conv-item__meta">
                  <span class="conv-item__time">{{ convTime(conv.created_at) }}</span>
                  <span v-if="!conv.title" class="conv-item__wip">待命名</span>
                </span>
              </span>
              <span class="conv-item__ops" @click.stop>
                <span
                  class="icon-btn"
                  role="button"
                  tabindex="0"
                  title="重命名"
                  aria-label="重命名会话"
                  @click="startRename(conv)"
                  @keydown.enter.prevent="startRename(conv)"
                  @keydown.space.prevent="startRename(conv)"
                >✎</span>
                <span
                  class="icon-btn icon-btn--danger"
                  role="button"
                  tabindex="0"
                  title="删除"
                  aria-label="删除会话"
                  @click="handleDelete(conv)"
                  @keydown.enter.prevent="handleDelete(conv)"
                  @keydown.space.prevent="handleDelete(conv)"
                >✕</span>
              </span>
            </button>
          </li>
        </ul>
      </aside>

      <!-- ==================== 主区域 ==================== -->
      <section class="chat-body">
        <!-- 空状态 -->
        <div v-if="!activeId" class="chat-empty">
          <button
            class="side-toggle chat-empty__toggle"
            type="button"
            aria-label="展开会话列表"
            @click="sideOpen = !sideOpen"
          >
            <TravelIcon name="map" :size="16" />
            我的会话
          </button>
          <div class="chat-empty__logo" aria-hidden="true">
            <!-- 这里显示 64px（3 倍屏需 192px），故用 512 的版本。
                 缩小到 128 在这个尺寸会发虚，与导航栏的取舍不同。 -->
            <img src="/voyage-mark-2.png" alt="" />
          </div>
          <h2>{{ PAGE_COPY.chatEmptyTitle }}</h2>
          <p>{{ PAGE_COPY.chatEmptyDesc }}</p>
          <div class="chat-empty__quick">
            <button
              v-for="q in QUICK_PROMPTS"
              :key="q"
              class="quick-chip"
              @click="input = q; inputEl?.focus()"
            >
              <TravelIcon name="route" :size="14" />
              {{ q }}
            </button>
          </div>
          <button class="btn btn-primary" @click="newConversation">
            <TravelIcon name="plane" :size="17" />
            开始新的旅程
          </button>
        </div>

        <template v-else>
          <!-- 工具栏 -->
          <div class="chat-toolbar">
            <!-- 窄屏唤出侧栏；宽屏用侧栏自身的折叠按钮，此处隐藏 -->
            <button
              class="side-toggle"
              type="button"
              aria-label="展开会话列表"
              @click="sideOpen = !sideOpen"
            >
              <TravelIcon name="map" :size="17" />
            </button>

            <div class="chat-toolbar__id">
              <span class="chat-toolbar__title">{{ activeConversation?.title || '新会话' }}</span>
              <!-- 会话状态提示：让用户知道这段对话进行到哪、能不能提取 -->
              <span class="chat-toolbar__status">
                <span v-if="streaming" class="tstatus tstatus--busy">
                  <i class="tstatus__dot"></i>{{ streamPhase }}
                </span>
                <span v-else-if="canExtract" class="tstatus tstatus--ready">
                  <i class="tstatus__dot"></i>{{ rounds }} 轮对话 · 可提取行程
                </span>
                <span v-else class="tstatus">{{
                  rounds ? `${rounds} 轮对话` : '还没有对话，说说你的计划'
                }}</span>
              </span>
            </div>

            <div class="chat-toolbar__ops">
              <button
                class="tool-btn tool-btn--accent"
                :disabled="streaming || !canExtract"
                :title="canExtract ? '把最后一条回答整理成行程' : '先让 AI 给出一份行程安排'"
                @click="handleExtract"
              >
                <TravelIcon name="luggage" :size="15" />
                提取行程
              </button>
              <button
                class="tool-btn"
                :disabled="streaming"
                title="在左侧会话列表中就地修改标题"
                @click="renameFromToolbar"
              >
                <TravelIcon name="edit" :size="15" />
                重命名
              </button>
              <!-- 分享与导出统一在「行程详情」里操作（那边有完整的权限与格式选择），
                   这里只做入口，避免两处各实现一套 -->
              <RouterLink
                to="/itineraries"
                class="tool-btn"
                title="分享与导出请到「行程」页打开对应行程"
              >
                <TravelIcon name="route" :size="15" />
                分享 / 导出
              </RouterLink>
            </div>
          </div>

          <!-- 流式状态条：始终告诉用户 AI 在做什么 -->
          <Transition name="phase">
            <div v-if="streaming" class="phase" role="status" aria-live="polite">
              <span class="phase__wave" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
              <span class="phase__text">{{ streamPhase }}</span>
            </div>
          </Transition>

          <!-- 消息区 -->
          <div ref="scrollEl" class="chat-scroll">
            <div class="chat-stream">
              <!-- 历史被截断时的提示：后端按轮次分页，更早的内容不在此次响应里 -->
              <p v-if="historyTruncated" class="chat-truncated">
                仅显示最近 {{ HISTORY_ROUNDS }} 轮对话
              </p>
              <div
                v-for="(msg, i) in renderedMessages"
                :key="i"
                class="msg"
                :class="`msg--${msg.role}`"
              >
                <!-- 助手头像：用站点图标组的 voyage-mark-128
                     （30px 显示，3 倍屏需 90px；内边距仅 1.5%/边，
                      在 30px 方块里不会被空白缩掉一圈） -->
                <span v-if="msg.role === 'assistant'" class="msg__avatar" aria-hidden="true">
                  <img src="/voyage-mark-128.png" alt="" />
                </span>

                <div class="msg__col">
                  <!-- 思考过程：默认折叠，不抢视线 -->
                  <details v-if="msg.reasoning" class="reason">
                    <summary>
                      <span class="reason__dot"></span>
                      思考过程
                      <span class="reason__len">{{ msg.reasoning.length }} 字</span>
                    </summary>
                    <p>{{ msg.reasoning }}</p>
                  </details>

                  <!-- 工具调用：鲜明的时间线 -->
                  <ToolTimeline v-if="msg.tools && msg.tools.length" :steps="msg.tools" />

                  <!--
                    正文：助手走结构化渲染，用户走纯文本。
                    助手不再用气泡装 markdown —— 那会让用户看到满屏 ** 与 -，
                    像在读源码。MessageBody 把它解析成小节标题、条目列表、
                    行程片段与提示块，读起来像顾问给的方案。
                  -->
                  <MessageBody
                    v-if="msg.content && msg.role === 'assistant'"
                    class="msg__card"
                    :class="{ 'msg__card--err': !!streamError && i === renderedMessages.length - 1 && streaming }"
                    :text="msg.content"
                    :streaming="streaming && i === renderedMessages.length - 1"
                    @extract="handleExtract"
                  />
                  <div v-else-if="msg.content" class="msg__bubble">{{ msg.content }}</div>

                  <!--
                    流式光标已由 MessageBody 内部处理（末块不结构化），
                    这里不再单独渲染，避免出现两个光标。
                  -->

                  <!-- 消息操作条：悬停浮现，避免常驻占用视线 -->
                  <div v-if="msg.content && !streaming" class="msg__ops">
                    <button class="op-btn" title="复制内容" @click="copyMessage(msg)">
                      <TravelIcon name="check" :size="13" />
                      复制
                    </button>
                    <button
                      v-if="msg.role === 'assistant'"
                      class="op-btn"
                      title="用同一个问题再问一次"
                      @click="regenerate(i)"
                    >
                      <TravelIcon name="compass" :size="13" />
                      重新生成
                    </button>
                  </div>
                </div>
              </div>

              <!-- 首字等待：三点 + 当前阶段
                   只说「正在生成」等于没说；告诉用户此刻在做什么
                   （解析需求 / 核对天气 / 查车次），等待才不焦躁 -->
              <div v-if="thinking" class="msg msg--assistant">
                <span class="msg__avatar" aria-hidden="true">
                  <img src="/voyage-mark-128.png" alt="" />
                </span>
                <div class="msg__col">
                  <div class="waiting" role="status" aria-live="polite">
                    <span class="waiting__dots" aria-hidden="true">
                      <i></i><i></i><i></i>
                    </span>
                    <span class="waiting__text">{{ streamPhase }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 输入区 -->
          <div class="chat-inputbar">
            <!--
              快捷示例：只在输入框为空且没在生成时出现。
              用户一旦开始打字就收起——那时的建议会变成干扰，
              而且占一行高度会把输入框往上顶。
            -->
            <Transition name="chips">
              <div v-if="showQuickChips" class="quick-bar">
                <span class="quick-bar__label">试试</span>
                <button
                  v-for="q in QUICK_PROMPTS"
                  :key="q"
                  type="button"
                  class="quick-chip quick-chip--sm"
                  @click="input = q; inputEl?.focus()"
                >
                  {{ q }}
                </button>
              </div>
            </Transition>

            <div class="chat-inputbar__row">
              <div class="chat-inputbar__field" :class="{ 'is-busy': streaming }">
                <textarea
                  ref="inputEl"
                  v-model="input"
                  class="textarea chat-inputbar__box"
                  rows="1"
                  :placeholder="
                    streaming
                      ? '正在回答，稍候可以继续追问…'
                      : '说说你想去哪、几天、预算多少…'
                  "
                  :disabled="streaming"
                  @keydown="onKeydown"
                ></textarea>

                <!-- 回车提示做成一枚键帽，比一行小字更易读 -->
                <div class="chat-inputbar__foot">
                  <span class="kbd-hint">
                    <kbd>Enter</kbd> 发送
                    <span class="kbd-hint__sep">·</span>
                    <kbd>Shift</kbd><kbd>Enter</kbd> 换行
                  </span>
                  <span v-if="input.trim()" class="charcount">{{ input.length }}</span>
                </div>
              </div>

              <button
                class="send-btn"
                :disabled="streaming || !input.trim()"
                :aria-label="streaming ? '正在生成' : '发送消息'"
                @click="send"
              >
                <template v-if="streaming">
                  <span class="send-btn__spin" aria-hidden="true"></span>
                </template>
                <template v-else>
                  <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M5 12h14M13 6l6 6-6 6" />
                  </svg>
                </template>
              </button>
            </div>
          </div>
        </template>
      </section>
    </main>
  </div>
</template>

<style scoped>
.chat-page { height: 100vh; display: flex; flex-direction: column; position: relative; z-index: 1; }

/* 消息区的底纹：一层几乎看不见的地图纹理。
   目的不是「看到地图」，而是让大片留白不至于像一张死白的纸。
   用 fixed 定位避免随滚动移动产生眩晕感。 */
.chat-page::before {
  content: '';
  position: fixed;
  inset: var(--nav-h) 0 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.5;
  background-image:
    radial-gradient(circle at 12% 22%, rgba(37, 99, 235, 0.05), transparent 42%),
    radial-gradient(circle at 88% 72%, rgba(14, 165, 233, 0.045), transparent 45%);
}

.chat-main {
  flex: 1;
  min-height: 0;
  display: grid;
  /* 侧栏宽度用变量控制：折叠时只改变量，主区自动铺满，
     不必让 JS 参与布局计算 */
  --side-w: 272px;
  grid-template-columns: var(--side-w) 1fr;
  margin: 0 16px 16px;
  gap: 16px;
  position: relative;
  z-index: 1;
  transition: grid-template-columns 0.26s cubic-bezier(0.2, 0.7, 0.2, 1);
}
/* 折叠态：侧栏让位，间隔也收掉，否则会留一条空缝 */
.chat-main:has(.chat-side--folded) {
  grid-template-columns: 0 1fr;
  gap: 0;
}
@media (prefers-reduced-motion: reduce) {
  .chat-main { transition: none; }
}

/* ==================== 侧边栏 ==================== */
.chat-side {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
/* 折叠时整栏淡出并收窄；不给 width 是因为宽度已由网格控制 */
.chat-side--folded {
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}
.chat-side--folded * {
  pointer-events: none;
}

.chat-side__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 14px 12px;
}

.chat-side__title { font-family: var(--font-display); font-size: 1rem; font-weight: 700; }

/* 会话条数：让用户对「攒了多少」有概念 */
.chat-side__count {
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--text3);
  background: var(--panel2);
  border-radius: 20px;
  padding: 1px 7px;
}

/* 折叠按钮：靠右，悬停才明显，避免与标题抢注意力 */
.side-fold {
  margin-left: auto;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text3);
  transition: background-color 0.18s, color 0.18s, border-color 0.18s;
}
.side-fold:hover {
  background: var(--panel2);
  border-color: var(--border);
  color: var(--prim);
}

/* ---- 新建会话：主操作占满整行 ---- */
.side-new {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0 10px 10px;
  padding: 10px 14px;
  border-radius: 11px;
  background: var(--grad);
  color: #fff;
  font-size: 0.88rem;
  font-weight: 650;
  box-shadow: 0 6px 16px var(--glow);
  transition: transform 0.2s, filter 0.2s, box-shadow 0.2s;
}
.side-new:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: saturate(1.08);
  box-shadow: 0 10px 22px var(--glow);
}
.side-new:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.side-new__icon {
  display: grid;
  place-items: center;
}

/* ---- 会话摘要 ----
   两行截断：一行放不下多少信息，三行又会让每项太高、列表变长 */
.conv-item__sum {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 0.76rem;
  line-height: 1.5;
  color: var(--text3);
  margin-top: 1px;
}

/* ---- 内联重命名输入框 ----
   外观与标题文字接近，只是多一圈边框，避免「突然换了个控件」的割裂感 */
.conv-item__edit {
  width: 100%;
  padding: 2px 6px;
  margin: -1px 0 0 -7px;
  border: 1px solid var(--prim);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  font-size: 0.88rem;
  font-weight: 650;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
  box-shadow: 0 0 0 3px var(--primary-soft);
}

.chat-side__hint { padding: 18px 16px; color: var(--text3); font-size: 0.82rem; line-height: 1.6; }

/* ---- 会话搜索 ---- */
.chat-side__search {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 10px 8px;
  padding: 0 12px;
  height: 36px;
  border-radius: 10px;
  background: var(--panel2);
  border: 1px solid transparent;
  transition: border-color 0.2s, background-color 0.2s;
}
.chat-side__search:focus-within {
  background: var(--panel);
  border-color: var(--blue-300);
}
.chat-side__search :deep(svg) { color: var(--text3); flex-shrink: 0; }
.chat-side__search input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 0.82rem;
  color: var(--text);
  outline: none;
}
.chat-side__search input::placeholder { color: var(--text3); }
.chat-side__clear {
  color: var(--text3);
  font-size: 0.75rem;
  padding: 2px 4px;
  border-radius: 4px;
}
.chat-side__clear:hover { color: var(--text); background: var(--surface-soft); }

/* ---- 加载骨架：比「加载中…」更能表达结构 ---- */
.chat-side__loading { padding: 12px 18px; display: flex; flex-direction: column; gap: 10px; }
.skel {
  display: block;
  height: 10px;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--surface-soft) 25%, var(--panel2) 37%, var(--surface-soft) 63%);
  background-size: 400% 100%;
  animation: skelShine 1.4s ease infinite;
}
.skel--line:nth-child(2) { width: 78%; }
.skel--line:nth-child(3) { width: 60%; }
@keyframes skelShine {
  0% { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}
@media (prefers-reduced-motion: reduce) {
  .skel { animation: none; }
}

/* ---- 侧栏空状态 ---- */
.chat-side__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 32px 22px;
  text-align: center;
}
.chat-side__empty-icon {
  display: grid;
  place-items: center;
  width: 54px;
  height: 54px;
  border-radius: 16px;
  background: var(--grad-soft);
  color: var(--prim);
  margin-bottom: 6px;
}
.chat-side__empty p { font-size: 0.88rem; font-weight: 650; color: var(--text); }
.chat-side__empty > span:last-child { font-size: 0.78rem; color: var(--text3); line-height: 1.6; }

.chat-side__list {
  list-style: none;
  margin: 0;
  padding: 10px;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.conv-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 11px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background-color 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
  /* 按钮元素的重置：抹掉浏览器默认外观，与原先的 li 视觉保持一致 */
  width: 100%;
  background: transparent;
  font: inherit;
  color: inherit;
  text-align: left;
}
.conv-item:hover { background: var(--panel2); transform: translateX(2px); }
/* 键盘聚焦要有可见指示，否则 Tab 过去看不出焦点在哪 */
.conv-item:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: -2px;
}
.conv-item--active {
  background: var(--grad-soft);
  border-color: var(--blue-200);
  box-shadow: inset 2px 0 0 var(--prim);
}

/* 当前会话左侧的地图钉，比纯色条更有旅行意味 */
.conv-item__pin {
  position: absolute;
  left: -3px;
  top: 50%;
  width: 6px;
  height: 6px;
  margin-top: -3px;
  border-radius: 50%;
  background: var(--prim);
  opacity: 0;
  transform: scale(0.4);
  transition: opacity 0.2s, transform 0.2s;
}
.conv-item--active .conv-item__pin { opacity: 1; transform: scale(1); }

.conv-item__main { flex: 1; min-width: 0; }

.conv-item__title {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-item__meta {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 3px;
}
.conv-item__time { font-size: 0.68rem; color: var(--text3); font-family: var(--mono); }
.conv-item__wip {
  font-size: 0.64rem;
  color: var(--gold-600);
  background: var(--gold-soft);
  padding: 1px 6px;
  border-radius: 4px;
}

.conv-item__ops { display: none; gap: 2px; flex-shrink: 0; }
.conv-item:hover .conv-item__ops { display: flex; }

.icon-btn {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  color: var(--text3);
  font-size: 0.78rem;
  display: grid;
  place-items: center;
  transition: background-color 0.15s ease, color 0.15s ease;
}
.icon-btn:hover { background: var(--panel); color: var(--text); }
.icon-btn--danger:hover { color: var(--danger); background: rgba(229, 72, 77, 0.1); }

/* ==================== 主体 ==================== */
.chat-body {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  overflow: hidden;
}

/* ---- 空状态 ---- */
.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  text-align: center;
  padding: 24px;
}

.chat-empty__logo {
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  border-radius: 18px;
  /* 去掉渐变底：新图标本身是完整方形图，再套一层渐变会变成「渐变框套方块」 */
  background: var(--panel);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.chat-empty__logo img { width: 100%; height: 100%; object-fit: cover; display: block; }
.chat-empty h2 { font-size: 1.45rem; }
.chat-empty p { color: var(--text2); max-width: 30em; font-size: 0.9rem; }

.chat-empty__quick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 44em;
  margin: 6px 0 4px;
}

.quick-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel2);
  color: var(--text2);
  font-size: 0.81rem;
  transition: color 0.18s, border-color 0.18s, background-color 0.18s, transform 0.18s,
              box-shadow 0.18s;
}
.quick-chip :deep(svg) { color: var(--text3); transition: color 0.18s; }
.quick-chip:hover {
  color: var(--prim);
  border-color: var(--blue-300);
  background: var(--primary-soft);
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.1);
}
.quick-chip:hover :deep(svg) { color: var(--prim); }

/* ---- 工具栏 ---- */
.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 18px;
  border-bottom: 1px solid var(--hairline);
  flex-shrink: 0;
}

/* 标题与状态竖排：标题是「在哪」，状态是「到哪一步了」 */
.chat-toolbar__id {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.chat-toolbar__title {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 0.98rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ---- 会话状态提示 ---- */
.tstatus {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.73rem;
  color: var(--text3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tstatus__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
/* 可提取：成功色，暗示「现在可以操作了」 */
.tstatus--ready {
  color: var(--success);
}
/* 生成中：主题色 + 呼吸，与消息区的流式提示呼应 */
.tstatus--busy {
  color: var(--prim);
}
.tstatus--busy .tstatus__dot {
  animation: tstatusPulse 1.4s ease-in-out infinite;
}
/* 本文件自带关键帧：HomeView 里的 pulse 是 scoped 的，
   这边引用不到，靠全局同名定义会形成隐式依赖 */
@keyframes tstatusPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.7); }
}
@media (prefers-reduced-motion: reduce) {
  .tstatus--busy .tstatus__dot { animation: none; }
}

.chat-toolbar__ops { display: flex; gap: 8px; flex-shrink: 0; }

/* 工具栏按钮：与全局 .btn 区分开——这里是轻量操作，视觉重量要更低 */
.tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 13px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text2);
  font-size: 0.82rem;
  font-weight: 500;
  white-space: nowrap;
  transition: transform 0.2s, border-color 0.2s, color 0.2s, box-shadow 0.2s;
}
.tool-btn :deep(svg) { color: var(--text3); transition: color 0.2s; }
.tool-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: var(--blue-300);
  color: var(--text);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.1);
}
.tool-btn:hover:not(:disabled) :deep(svg) { color: var(--prim); }
.tool-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 主操作（提取行程）用主色描边强调，但不抢发送按钮的实心高对比 */
.tool-btn--accent {
  border-color: var(--blue-200);
  background: var(--primary-soft);
  color: var(--prim);
  font-weight: 600;
}
.tool-btn--accent :deep(svg) { color: var(--prim); }
.tool-btn--accent:hover:not(:disabled) { background: var(--blue-100); }

/* ---- 流式阶段条 ---- */
.phase {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 18px;
  background: var(--grad-soft);
  border-bottom: 1px solid var(--hairline);
  font-size: 0.82rem;
  color: var(--prim);
  font-weight: 600;
  flex-shrink: 0;
}

.phase__wave { display: inline-flex; align-items: flex-end; gap: 3px; height: 14px; }
.phase__wave i {
  width: 3px;
  border-radius: 2px;
  background: var(--prim);
  animation: wave 1s ease-in-out infinite;
}
.phase__wave i:nth-child(1) { height: 6px; animation-delay: 0s; }
.phase__wave i:nth-child(2) { height: 13px; animation-delay: 0.12s; }
.phase__wave i:nth-child(3) { height: 9px; animation-delay: 0.24s; }
.phase__wave i:nth-child(4) { height: 12px; animation-delay: 0.36s; }

@keyframes wave {
  0%, 100% { transform: scaleY(0.45); opacity: 0.55; }
  50% { transform: scaleY(1); opacity: 1; }
}

.phase-enter-active, .phase-leave-active { transition: opacity 0.25s, transform 0.25s; }
.phase-enter-from, .phase-leave-to { opacity: 0; transform: translateY(-6px); }

/* ---- 消息区 ---- */
.chat-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 22px 20px;
  scroll-behavior: smooth;
}

.chat-stream { max-width: 820px; margin-inline: auto; display: flex; flex-direction: column; gap: 22px; }

/* 历史截断提示：居中细字，不抢消息的视觉重心 */
.chat-truncated {
  text-align: center;
  font-size: 0.76rem;
  color: var(--text3);
  padding: 2px 0 6px;
  position: relative;
}
.chat-truncated::before,
.chat-truncated::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 42px;
  height: 1px;
  background: var(--hairline);
}
.chat-truncated::before { left: calc(50% - 110px); }
.chat-truncated::after { right: calc(50% - 110px); }

.msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  /* 消息进入时轻微上移淡入。新消息硬出现会让人猝不及防，
     尤其实时对话里用户的注意力正在输入框上 */
  animation: msgIn 0.32s cubic-bezier(0.2, 0.7, 0.2, 1) both;
}
@keyframes msgIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .msg { animation: none; }
}
.msg--user { flex-direction: row-reverse; }
.msg--assistant { flex-direction: row; }

.msg__avatar {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  /* 同 chat-empty__logo：图标自带完整方形底，故容器不再叠渐变 */
  background: var(--panel);
  border: 1px solid var(--border);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  margin-top: 2px;
  overflow: hidden;
}
.msg__avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }

.msg__col { display: flex; flex-direction: column; gap: 8px; min-width: 0; max-width: min(680px, 88%); }
.msg--user .msg__col { align-items: flex-end; max-width: min(600px, 84%); }

/* ---- 气泡（仅用户消息）----
   助手消息不再用气泡包裹：结构化内容自己就是排版，
   再套一层圆角底色只会让小节标题、列表、提示块挤在一个框里，
   既不像文档也不像对话。改成无底色直接铺开，
   靠 MessageBody 内部的标题竖线与列表缩进建立层次。 */
.msg__bubble {
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 0.92rem;
  line-height: 1.7;
  overflow-wrap: break-word;
  position: relative;
}

.msg--user .msg__bubble {
  background: var(--grad);
  color: #fff;
  border-radius: 16px 16px 5px 16px;
  box-shadow: 0 6px 18px var(--glow);
}

/* ---- 助手消息卡片 ----
   原先这里有一条左侧竖边（悬停时浮出蓝色），实测很干扰：
   鼠标划过内容就冒出一道蓝线，像是选中状态，且与文内的小节标题
   竖线叠在一起更显杂乱。现改为完全无装饰，让内容自己成立。 */
.msg__card {
  padding: 2px 0;
}

/* 出错时整块转为错误色——这个保留：它表达的是真实状态而非装饰 */
.msg__card--err {
  background: rgba(229, 72, 77, 0.06);
  border-radius: 10px;
  padding: 10px 13px;
  color: var(--danger);
}

/* ---- 消息操作条 ----
   默认隐藏、悬停浮现，并轻微下移淡入——常驻会持续占用视线，
   而这类操作的使用频率远低于阅读正文。 */
.msg__ops {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
  opacity: 0;
  transform: translateY(-4px);
  transition: opacity 0.22s, transform 0.22s;
}
.msg:hover .msg__ops,
.msg:focus-within .msg__ops {
  opacity: 1;
  transform: none;
}
@media (hover: none) {
  /* 触屏没有悬停，操作条直接常驻，否则永远点不到 */
  .msg__ops { opacity: 1; transform: none; }
}

.op-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text3);
  font-size: 0.75rem;
  transition: background-color 0.18s, color 0.18s, border-color 0.18s;
}
.op-btn:hover {
  background: var(--panel2);
  border-color: var(--border);
  color: var(--text);
}
.op-btn--accent:hover {
  background: var(--primary-soft);
  border-color: var(--blue-200);
  color: var(--prim);
}

/* ---- 思考过程 ---- */
.reason {
  border-left: 3px solid rgba(245, 158, 11, 0.7);
  background: rgba(245, 158, 11, 0.06);
  border-radius: 5px 12px 12px 5px;
  padding: 9px 13px;
  font-size: 0.82rem;
  color: var(--text2);
  max-width: min(640px, 100%);
}
.reason summary {
  cursor: pointer;
  font-weight: 650;
  display: flex;
  align-items: center;
  gap: 7px;
  list-style: none;
}
.reason summary::-webkit-details-marker { display: none; }
.reason__dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); flex-shrink: 0; }
.reason__len { margin-left: auto; font-size: 0.7rem; color: var(--text3); font-weight: 400; }
.reason p { margin-top: 8px; white-space: pre-wrap; line-height: 1.7; }

/*
 * Markdown 相关样式已随 v-html 渲染一并移除。
 * 助手消息改由 MessageBody 组件渲染，其样式封装在该组件内（scoped），
 * 这里再留一份 .md-body 规则只会成为永远不会命中的死代码。
 */

/* ---- 等待状态：三点 + 当前阶段 ---- */
.waiting {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  padding: 13px 17px;
  background: var(--bubble-ai);
  border: 1px solid var(--border);
  border-radius: 5px 16px 16px 16px;
  width: fit-content;
}
.waiting__dots {
  display: inline-flex;
  gap: 5px;
  flex-shrink: 0;
}
.waiting__dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--prim);
  animation: bounce 1.2s ease-in-out infinite;
}
.waiting__dots i:nth-child(2) { animation-delay: 0.15s; }
.waiting__dots i:nth-child(3) { animation-delay: 0.3s; }
/* 阶段文字用主题色并与点同步呼吸，整体像「正在处理」而非静止 */
.waiting__text {
  font-size: 0.85rem;
  color: var(--prim);
  font-weight: 550;
  animation: waitFade 1.6s ease-in-out infinite;
}
@keyframes waitFade {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.62; }
}
@media (prefers-reduced-motion: reduce) {
  .waiting__dots i,
  .waiting__text { animation: none; }
}
/* bounce 关键帧由 .waiting__dots 使用；旧的 .typing span 规则已随
   等待组件改造移除（改为 .waiting__dots i） */
@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40% { transform: translateY(-7px); opacity: 1; }
}

/* ---- 输入区 ---- */
.chat-inputbar {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 12px 18px 16px;
  border-top: 1px solid var(--hairline);
  flex-shrink: 0;
  background: var(--panel);
}

.chat-inputbar__row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

/* 输入框容器：整体做聚焦态，而不是只给 textarea 描边——
   这样键帽提示也在同一个视觉容器里 */
.chat-inputbar__field {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 6px 6px 12px;
  border: 1px solid var(--border);
  border-radius: 15px;
  background: var(--panel2);
  transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
}
.chat-inputbar__field:focus-within {
  background: var(--panel);
  border-color: var(--blue-300);
  box-shadow: 0 0 0 3px var(--primary-soft);
}
/* 生成中降低视觉存在感，暗示此刻不该输入 */
.chat-inputbar__field.is-busy {
  opacity: 0.72;
}

.chat-inputbar__box {
  min-height: 34px;
  max-height: 160px;
  resize: none;
  background: transparent;
  border: none;
  padding: 8px 0 0;
  font-size: 0.94rem;
}
.chat-inputbar__box:focus {
  outline: none;
}

.chat-inputbar__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 18px;
}

/* 键帽：比一行灰字更容易一眼扫到 */
.kbd-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.68rem;
  color: var(--text3);
  user-select: none;
}
.kbd-hint kbd {
  font-family: var(--mono);
  font-size: 0.64rem;
  line-height: 1;
  padding: 3px 5px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text2);
  box-shadow: 0 1px 0 var(--border);
}
.kbd-hint__sep { opacity: 0.5; }

.charcount {
  font-family: var(--mono);
  font-size: 0.68rem;
  color: var(--text3);
  font-variant-numeric: tabular-nums;
}
/* 接近上限才变色提醒，平时不打扰 */
.charcount--warn { color: var(--gold-600); }

/* ---- 发送按钮：高对比圆形主按钮 ---- */
.send-btn {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: var(--grad);
  color: #fff;
  box-shadow: 0 8px 20px var(--glow);
  transition: transform 0.2s, box-shadow 0.2s, opacity 0.2s, filter 0.2s;
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: saturate(1.08);
  box-shadow: 0 12px 26px var(--glow);
}
.send-btn:active:not(:disabled) {
  transform: translateY(0);
}
.send-btn:disabled {
  opacity: 0.42;
  box-shadow: none;
  cursor: not-allowed;
}
/* 生成中的转圈：用边框缺口旋转，比三点更安静 */
.send-btn__spin {
  width: 17px;
  height: 17px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  animation: sendSpin 0.72s linear infinite;
}
@keyframes sendSpin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .send-btn__spin { animation: none; }
}

/* ---- 快捷示例条 ---- */
.quick-bar {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.quick-bar__label {
  font-size: 0.72rem;
  color: var(--text3);
  flex-shrink: 0;
}
.quick-chip--sm {
  padding: 5px 11px;
  font-size: 0.78rem;
}
/* 展开/收起：轻微上移淡入，不推动布局 */
.chips-enter-active,
.chips-leave-active {
  transition: opacity 0.22s, transform 0.22s;
}
.chips-enter-from,
.chips-leave-to {
  opacity: 0;
  transform: translateY(5px);
}

/* ==================== 响应式 ==================== */
/* 窄屏把侧栏收进抽屉。
   关键：不能直接 display:none —— 那样手机上就没法切换会话、也没法新建了。
   改为绝对定位的抽屉 + 工具栏按钮开关。 */
.side-toggle { display: none; }
.side-backdrop { display: none; }
/* 空状态里的「我的会话」按钮自带文字，宽度不受上面的定尺限制 */
.chat-empty__toggle { width: auto; gap: 7px; padding: 0 13px; font-size: 0.82rem; }

@media (max-width: 860px) {
  .chat-main { grid-template-columns: 1fr; margin: 0 10px 10px; gap: 10px; }

  .side-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border-radius: 9px;
    border: 1px solid var(--border);
    background: var(--panel);
    color: var(--text2);
    flex-shrink: 0;
    margin-right: 4px;
  }
  .chat-empty__toggle { width: auto; padding: 0 13px; margin: 0 0 4px; }
  .side-toggle:active { transform: scale(0.96); }

  .chat-side {
    position: fixed;
    z-index: 70;
    top: var(--nav-h);
    bottom: 0;
    left: 0;
    width: min(300px, 84vw);
    border-radius: 0 var(--r-m) var(--r-m) 0;
    transform: translateX(-102%);
    transition: transform 0.28s cubic-bezier(0.2, 0.7, 0.2, 1);
    box-shadow: var(--shadow-lift);
  }
  .chat-side--open { transform: none; }

  /* 抽屉打开时的遮罩，点击关闭 */
  .side-backdrop {
    display: block;
    position: fixed;
    inset: var(--nav-h) 0 0;
    z-index: 65;
    background: rgba(15, 23, 42, 0.36);
  }

  .tool-btn { padding: 8px 10px; font-size: 0.78rem; }
  .tool-btn span { display: none; }   /* 窄屏只留图标，靠 title 提示 */
  .msg__col { max-width: 92%; }
  .msg--user .msg__col { max-width: 88%; }
  /* 窄屏没有物理键盘，键帽提示没有意义，收起以省一行高度 */
  .kbd-hint { display: none; }
  .quick-bar { gap: 6px; }
}

@media (max-width: 560px) {
  .chat-toolbar { padding: 10px 12px; }
  .chat-toolbar__title { font-size: 0.9rem; }
  .chat-scroll { padding: 18px 14px; }
}
</style>
