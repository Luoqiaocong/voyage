<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
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
import { suggestFromContext } from '@/utils/quickSuggest'
import { formatRelative } from '@/utils/datetime'
import { groupByTime } from '@/utils/conversationGroup'
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

/**
 * 当前生成的中断控制器。
 *
 * 放在组件作用域而非 send() 局部：停止按钮在模板里，需要够得着它。
 * 生成结束（无论正常还是中断）都会置回 null，避免误用已失效的控制器。
 */
let abortCtl: AbortController | null = null

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

/**
 * 用户是否**主动**滚离了底部。
 *
 * 它同时决定两件事：「要不要自动跟随流式输出」与「是否显示回到底部按钮」。
 *
 * ## 为什么必须是「用户意图」而不是「容器位置」
 *
 * 原实现是在容器的 scroll 事件里按间距判断（gap > 80px 即视为离开底部），
 * 看起来合理，但**在流式输出下必然失效**：
 *
 *   AI 每吐一段字，内容就变长 → 容器位置被动改变 → 触发 scroll 事件
 *   → 重新计算 gap → 一旦落回 80px 内就把本标志置回 false
 *   → 自动跟随恢复 → 用户刚拉上去又被拽回底部
 *
 * 也就是说，用户想往上读时，只要 AI 还在输出，就永远「甩不掉」底部。
 *
 * 现在改为：**只有用户的滚动动作才能把它置为 true**（滚轮向上、触摸下拉、
 * 键盘上翻）。程序性的内容增长不再影响它。
 * 复位只发生在两个明确的时刻：用户点「回到底部」、或用户发送新消息。
 */
const awayFromBottom = ref(false)

/** 距底部多少像素内仍视为「在底部」（仅用于判断按钮显隐，不再用于自动复位） */
const NEAR_BOTTOM_PX = 80

/**
 * 容器滚动时只维护一个事实：**用户如果已经滚回最底，就恢复自动跟随**。
 *
 * 注意方向是单向的 —— 这里只可能把 true 变 false，绝不由位置把 false 变 true。
 * 置 true 只由下面的用户意图处理函数负责。
 */
function onStreamScroll() {
  const el = scrollEl.value
  if (!el) return
  const gap = el.scrollHeight - el.scrollTop - el.clientHeight
  // 已到底（容差内）→ 视为用户回到了跟随状态
  if (awayFromBottom.value && gap <= NEAR_BOTTOM_PX) {
    awayFromBottom.value = false
  }
}

/** 用户往上滚 → 停止自动跟随 */
function markUserScrolledUp() {
  awayFromBottom.value = true
}

/** 滚轮：只认向上的滚动（往下滚交给 onStreamScroll 的到底复位） */
function onWheelIntent(e: WheelEvent) {
  if (e.deltaY < 0) markUserScrolledUp()
}

let touchStartY: number | null = null
function onTouchStartIntent(e: TouchEvent) {
  touchStartY = e.touches[0]?.clientY ?? null
}
/** 触摸：手指下拉（y 变大）表示在看上面的内容 */
function onTouchMoveIntent(e: TouchEvent) {
  if (touchStartY === null) return
  const y = e.touches[0]?.clientY
  if (y === undefined) return
  if (y - touchStartY > 12) markUserScrolledUp()
}

/** 键盘：PageUp / 方向键上 / Home 都是「往上读」的明确意图 */
function onKeyIntent(e: KeyboardEvent) {
  if (['PageUp', 'ArrowUp', 'Home'].includes(e.key)) markUserScrolledUp()
}

/**
 * 滚动到底部。
 *
 * @param smooth 是否平滑滚动
 * @param force  是否无视「用户已滚上去」强制拉到底
 *
 * 默认**只在用户本来就在底部时才自动跟随**。
 * 原先是无条件跟随：用户往回翻看历史时，新生成的内容会不断把他拽回底部，
 * 根本读不了上面的内容 —— 这是流式输出场景的经典体验问题。
 * 用户主动触发的操作（发送、点箭头、切换会话）则用 force 强制到底。
 */
function scrollToBottom(smooth = false, force = false) {
  nextTick(() => {
    const el = scrollEl.value
    if (!el) return
    if (!force && awayFromBottom.value) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
    awayFromBottom.value = false
  })
}

/** 点箭头：回到底部并恢复自动跟随 */
function jumpToBottom() {
  scrollToBottom(true, true)
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
  return mergeAssistantRuns(out)
}

/**
 * 把连续的助手消息合并成一条，只保留最后一段文本。
 *
 * 为什么需要：工具调用型 Agent 一次回答会产生**多条** assistant 消息
 * （「我先查一下车次」→ 工具调用 → 「查到了，结果如下…」）。
 * 逐条渲染就会出现好几个人工头像，看起来像 AI 回了好几次，
 * 实际上用户只问了一次。这是真实反馈的问题。
 *
 * 合并规则：连续的 assistant 消息视为同一次回答，只取最后一条的正文，
 * 中间的过程性话语直接丢弃——它们是 Agent 的内部步骤，
 * 不是给用户看的内容。工具调用与思考过程本就不该出现在对话流里。
 *
 * 用户消息是天然的分隔符，遇到即结束当前合并。
 */
function mergeAssistantRuns(list: RdMsg[]): RdMsg[] {
  const out: RdMsg[] = []
  let pending: RdMsg | null = null

  for (const m of list) {
    if (m.role === 'assistant') {
      // 同一轮里的后续消息覆盖前一条，最终留下最后那段正文
      pending = m
      continue
    }
    if (pending) {
      out.push(pending)
      pending = null
    }
    out.push(m)
  }
  if (pending) out.push(pending)
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
  // 切换会话是用户主动操作，强制到底（不受「此前是否在翻历史」影响）
  scrollToBottom(false, true)
}

function resetStream() {
  streamText.value = ''
  streamReasoning.value = ''
  streamTools.value = []
  streamError.value = ''
  showReasoning.value = false
}

/**
 * 开一个新会话。
 *
 * ## 这里刻意**不调用 createConversation**
 *
 * 原先点一下就在后端建一条会话、并立刻插进列表 —— 结果是：
 * 用户点开看看、什么都没聊就去做别的，列表里就永久留下一条「新会话」。
 * 建了又没内容，既占位置，也让人以为自己说过什么。
 *
 * 现在的做法与主流对话产品一致（用户点名要求）：
 *   点「新会话」→ 只是把界面切到空白对话窗**草稿态**（activeId = null），
 *   后端不动、列表不动；等用户真的发出第一条消息时（见 runTurn），
 *   才创建会话、生成标题、出现在列表里。
 *
 * 于是「空会话」在数据和界面上都不存在，不需要额外去删。
 * 副作用是草稿态与「首次进入、还没选会话」是同一个状态 ——
 * 这没问题：两者要显示的都是那个空白对话框。因此这里再点一次
 * 也不会有变化，只需把焦点放回输入框。
 */
async function newConversation() {
  if (streaming.value) return
  // 已经在草稿态：无需重来，把焦点交回输入框即可
  if (!activeId.value) {
    inputEl.value?.focus()
    return
  }
  activeId.value = null
  messages.value = []
  resetStream()
  historyTruncated.value = false
  // 切到草稿态是用户主动操作，滚回顶部（空白窗没有「底部」可言）
  await nextTick()
  inputEl.value?.focus()
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
 * 注意：原先此处有 renameFromToolbar()，供工具条的「重命名」按钮调用——
 * 它会先展开侧栏再把焦点移到标题输入框。该按钮已移除（侧栏点标题即可就地
 * 编辑，工具条是重复入口，且焦点跳走会让用户困惑），故此函数一并删除。
 */

async function handleDelete(conv: Conversation) {
  /*
   * 不再把会话 id 显示给用户。原先标题为空时回退到 conv.id，
   * 弹出一串随机字符（如「确定删除会话「483f5aa725c1」吗？」）——
   * 用户既看不懂，也不需要知道内部标识。
   * 没有标题就是「新会话」，与列表里的显示保持一致。
   */
  const label = conv.title?.trim() || '新会话'
  const sure = await ui.confirm(`确定删除「${label}」吗？历史记录与 AI 记忆将一并清除。`)
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

  /*
   * 会话的**唯一创建入口**。
   *
   * 「新会话」按钮只把界面切到草稿态（activeId = null），不建后端会话；
   * 直到这里 —— 用户真的发出第一条消息 —— 才创建。
   * 这样列表里不会出现「建了却没聊过」的空会话，也就不需要清理逻辑。
   *
   * 插入列表放在创建之后、流式开始之前：此时列表里已有这一条，
   * 后续流式返回的 title 事件才能按 id 找到它并回填标题
   * （见下方 chunk.type === 'title' 分支）。
   */
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
  /** 本次生成的中断控制器；用户点「停止生成」时用它断开连接 */
  const myCtl = new AbortController()
  abortCtl = myCtl
  resetStream()
  // 用户刚发送，强制到底（即便他此前在翻历史）
  scrollToBottom(false, true)

  let finished = false
  let aborted = false

  try {
    for await (const chunk of streamChat(cid, text, myCtl.signal)) {
      /*
       * 事件名以 api/conversation.ts 的 SSE 解析层为准：那一层已把后端的
       * tool_call / tool_result 归一成前端的 'tool'，并带上 label / phase /
       * content。这里只消费归一后的类型，不要改成后端的事件名。
       *
       * （曾误判此处与后端事件名不匹配并改动过，实为误判：
       *   抓原始 SSE 帧确认后端正常发出、前端解析层也正常映射。）
       */
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
    /*
     * 用户主动停止时会抛 AbortError。这**不是错误**，不该弹提示吓人 ——
     * 只需把已生成的内容保留下来即可。
     * 其余异常才是真的失败。
     */
    if (e?.name === 'AbortError') {
      aborted = true
    } else {
      streamError.value = e?.message ?? '对话请求失败'
    }
  } finally {
    /*
     * 竞态防护：只有当 abortCtl 仍是**本次**的控制器时才做收尾。
     *
     * 场景：用户点停止后立刻又发了一条（或快速连发两次）。此时旧请求的
     * finally 会晚于新请求的初始化执行，若不加判断就会把新请求的
     * streaming / abortCtl / 流式缓冲全部重置 —— 表现为「刚发出的消息
     * 界面毫无反应」，且新请求再也无法被停止（控制器被置空）。
     * 这是经典的 async 收尾竞态，只在快速操作时偶发，极易漏测。
     */
    const isCurrent = abortCtl === myCtl
    if (isCurrent) {
      if (!finished) {
        if (!streamText.value.trim() && !streamTools.value.length) {
          // 主动停止且一个字都没有：安静处理，不报错
          if (!aborted) streamError.value = streamError.value || 'AI 响应中断，请重试'
        } else {
          // 已生成的部分照样落进消息列表，用户不会白等
          if (aborted) ui.toast('已停止生成，保留已生成的内容', 'info')
          commitAssistant()
        }
      }
      streaming.value = false
      abortCtl = null
      resetStream()
      scrollToBottom(true)
      inputEl.value?.focus()
    }
  }
}

/**
 * 停止生成。
 *
 * 中断的连锁反应：abort() → 浏览器断开连接 → 服务端 SSE 生成器被取消 →
 * LangGraph 停止执行、不再继续调用模型与工具，因此不会继续消耗 token。
 */
function stopStreaming() {
  abortCtl?.abort()
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
 * 从折叠图标列点「搜索」：先展开侧栏，再打开搜索弹窗。
 *
 * 展开侧栏不是必须的（弹窗是浮层），但用户点的是「侧栏里的搜索」，
 * 收起状态下展开一下更符合预期，也能让结果列表与侧栏上下文对齐。
 * 注意这里**不再依赖 convKeyword / 内联搜索框** —— 搜索已改为弹窗，
 * 且支持内容搜索（见 searchOpen / searchResults）。
 */
async function focusSearch() {
  sideFolded.value = false
  await nextTick()
  openSearch()
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

/**
 * 按标题或已缓存摘要过滤会话；空关键词返回全部。
 * 侧栏列表用这一份（只匹配标题与首条消息摘要，不额外打接口）。
 */
const filteredConversations = computed(() => {
  const kw = convKeyword.value.trim().toLowerCase()
  if (!kw) return conversations.value
  return conversations.value.filter((c) => {
    const title = (c.title ?? '').toLowerCase()
    const sum = (convSummary.value[c.id] ?? '').toLowerCase()
    return title.includes(kw) || sum.includes(kw)
  })
})

/* ==================== 搜索弹窗 ==================== */

/**
 * 搜索弹窗是否打开。
 *
 * 与侧栏内联搜索不同：弹窗支持**搜索对话内容**（用户要求），
 * 而内容不在列表接口里 —— 必须按会话逐条拉取消息。
 * 弹窗形态给了这件事空间：有标题栏、有结果区、有加载提示，
 * 内联在侧栏里做这些会把列表挤得没法看。
 */
const searchOpen = ref(false)
const searchEl = ref<HTMLInputElement | null>(null)
/** 弹窗里的关键词。与侧栏内联搜索用的 convKeyword 分开 ——
 *  两者生命周期不同：弹窗关闭即清空，侧栏那份是列表过滤态 */
const searchKeyword = ref('')

/**
 * 会话内容缓存：{ 会话 id -> 全部消息文本（小写，便于匹配） }。
 * 首次打开弹窗时按需拉取，之后复用；切换会话不影响它。
 */
const convContent = ref<Record<string, string>>({})
/** 内容是否已拉过（避免重复请求；空内容也要记，否则会反复重试） */
const contentLoaded = ref<Set<string>>(new Set())
const contentLoading = ref(false)

/**
 * 并行拉取所有会话的消息内容。
 *
 * 为什么不做后端搜索：消息存在 langgraph 的 checkpointer 表里
 * （会话表只有 id/title/created_at），要后端搜就得查它的内部结构，
 * 与第三方实现细节耦合。而会话量级是「几十条」，
 * 并发拉取 + 前端过滤足够快，改动面也小得多。
 *
 * 并发上限 6：一次性打几十个请求会把浏览器与服务端都压住，
 * 而这个量级下 6 并发已经能在 1~2 秒内跑完。
 */
const CONTENT_CONCURRENCY = 6

async function loadContents() {
  const todo = conversations.value.filter((c) => !contentLoaded.value.has(c.id))
  if (!todo.length) return
  contentLoading.value = true
  let cursor = 0
  const worker = async () => {
    while (cursor < todo.length) {
      const conv = todo[cursor++]
      try {
        const page = (await getMessagesPage(conv.id)) as MessagesPage
        // 只保留纯文本消息：多模态消息的 content 是数组，没有可搜的文本
        const text = (page.messages ?? [])
          .map((m) => (typeof m.content === 'string' ? m.content : ''))
          .join('\n')
          .toLowerCase()
        convContent.value = { ...convContent.value, [conv.id]: text }
      } catch {
        // 单条失败不该影响整体搜索：记为「已拉过、内容为空」
        convContent.value = { ...convContent.value, [conv.id]: '' }
      } finally {
        contentLoaded.value = new Set(contentLoaded.value).add(conv.id)
      }
    }
  }
  try {
    await Promise.all(Array.from({ length: Math.min(CONTENT_CONCURRENCY, todo.length) }, worker))
  } finally {
    contentLoading.value = false
  }
}

/** 弹窗搜索结果：标题或**内容**命中 */
const searchResults = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return conversations.value
  return conversations.value.filter((c) => {
    const title = (c.title ?? '').toLowerCase()
    if (title.includes(kw)) return true
    return (convContent.value[c.id] ?? '').includes(kw)
  })
})

/** 命中片段：把内容里关键词周围的一小段截出来做预览 */
function hitSnippet(id: string, kw: string): string {
  const text = convContent.value[id] ?? ''
  const k = kw.trim().toLowerCase()
  if (!k) return ''
  const i = text.indexOf(k)
  if (i < 0) return ''
  const start = Math.max(0, i - 24)
  const raw = text.slice(start, i + k.length + 40).replace(/\s+/g, ' ').trim()
  return (start > 0 ? '…' : '') + raw + '…'
}

function openSearch() {
  searchOpen.value = true
  void loadContents()
  void nextTick(() => searchEl.value?.focus())
}

function closeSearchModal() {
  searchOpen.value = false
  searchKeyword.value = ''
}

/** 点搜索结果：打开该会话并关掉弹窗 */
function pickResult(id: string) {
  closeSearchModal()
  void openConversation(id)
}

/* ==================== 时间分组 ==================== */

/** 侧栏列表按时间分组（今天/昨天/7 天内/30 天内/更早） */
const groupedConversations = computed(() => groupByTime(filteredConversations.value))

/** 弹窗结果同样分组，便于在长列表里定位 */
const groupedResults = computed(() => groupByTime(searchResults.value))


/** 会话项显示的时间：今天显示时刻，更早显示日期，避免一长串相同日期 */
/**
 * 会话列表的时间显示。
 *
 * 原先这里自己实现了一套（用 new Date() 解析并判断是否同一天）。
 * 现在委托给 utils/datetime 的 formatRelative：
 *   · 统一了时间处理（原先三处各写一套，假设的后端格式还不一样）
 *   · 修掉一个隐患：new Date('2026-09-19 17:30:00') 会被当成本机时区解析，
 *     而后端下发的**已经是东八区本地时间**，在非东八区的机器上会再偏一次
 *   · formatRelative 用正则提取日期分量后本地构造 Date，不做时区换算
 */
function convTime(createdAt?: string): string {
  return formatRelative(createdAt)
}

/** 默认快捷示例：无上下文可依据时使用 */
const QUICK_PROMPTS = [
  '帮我规划广州到北京的 3 天行程',
  '这周末去成都穿什么？',
  '查一下明天广州南到北京西的高铁'
]

/**
 * 空状态的引导卡片：把最常用的三类场景摆出来。
 *
 * 原先空态只有一行文字提示，用户不知道该从哪问起。
 * 卡片带图标与说明，比一串示例胶囊更能说明「这个助手能做什么」。
 */
const EMPTY_GUIDES = [
  {
    icon: 'map',
    title: '规划一次出游',
    desc: '给出出发地、天数与预算，生成按天排布的行程',
    prompt: '帮我规划广州到北京的 3 天行程，预算 3000'
  },
  {
    icon: 'train',
    title: '查火车票',
    desc: '查指定日期的车次、票价与耗时',
    prompt: '查一下明天广州南到北京西的高铁'
  },
  {
    icon: 'spark',
    title: '算预算',
    desc: '估算一趟旅行的交通、住宿与餐饮开销',
    prompt: '去成都玩 4 天大概要花多少钱？'
  }
]

/**
 * 快捷提问：优先用**当前对话的上下文**推荐，没有上下文时回退默认示例。
 *
 * 例如刚聊过三亚，就推「三亚这几天适合穿什么」「三亚有哪些必吃的本地菜」，
 * 而不是永远那三条通用示例。判断逻辑全在本地（utils/quickSuggest），
 * 不额外请求模型 —— 建议必须与对话同时出现，等一次请求会闪一下才出。
 */
const quickPrompts = computed(() => {
  // 只用当前会话的消息做判断：别的会话聊过什么与本轮无关
  const text = messages.value.map((m) => m.content).join('\n')
  const contextual = suggestFromContext(text)
  return contextual.length ? contextual : QUICK_PROMPTS
})

/**
 * 快捷芯片的配色。
 *
 * ## 为什么可以按关键词上色（而不是纯按序号）
 *
 * 这层颜色是**纯装饰**：它不承载语义，用户也不需要通过颜色去理解建议。
 * 所以可以大方地用「关键词命中」这种近似 —— 猜错了只是颜色不那么贴切，
 * 不会误导（对比：状态色猜错会让人误判系统状态）。
 *
 * ## 为什么要按关键词而不是按序号循环
 *
 * 按序号循环（i % 5）虽然简单，但同一句话在不同会话里会换颜色，
 * 换一批建议时颜色也跟着洗牌，看起来像随机噪声。
 * 按内容决定则同一句建议始终是同一个颜色，视觉上「稳定」得多。
 *
 * 顺序即优先级：越靠前的主题越具辨识度（吃 > 爬山 > 预算 …）。
 * 一个都命中不了时按序号回退，保证**同屏三张卡颜色一定不同**。
 */
const CHIP_TONES: { keys: string[]; tone: string }[] = [
  { keys: ['吃', '美食', '小吃', '火锅', '餐厅'], tone: 'food' },
  { keys: ['预算', '多少钱', '花费', '省钱', '便宜'], tone: 'budget' },
  { keys: ['天气', '下雨', '气温'], tone: 'weather' },
  { keys: ['爬山', '徒步', '自然', '风景', '海岛', '看海'], tone: 'nature' },
  { keys: ['古迹', '历史', '博物馆', '文化', '古镇'], tone: 'history' },
  { keys: ['拍照', '摄影', '夜景'], tone: 'photo' },
  { keys: ['亲子', '带娃', '老人', '带父母'], tone: 'family' },
  { keys: ['几天', '日程', '安排', '路线', '行程'], tone: 'plan' }
]
const FALLBACK_TONES = ['plan', 'food', 'nature', 'budget', 'history']

function chipTone(text: string, index: number): string {
  for (const group of CHIP_TONES) {
    if (group.keys.some((k) => text.includes(k))) return group.tone
  }
  return FALLBACK_TONES[index % FALLBACK_TONES.length]
}

/**
 * 是否展示快捷示例。
 * 只在「没在生成」且「输入框为空」时出现：用户一开始打字，
 * 建议就从帮助变成了干扰，而且那一行会把输入框顶上去。
 */
const showQuickChips = computed(() => !streaming.value && !input.value.trim())

/**
 * 底部提示行的显示时机。
 *
 * 原先提示行**常驻**，但它平时只是重复表头已经写过的 placeholder，
 * 真正有信息量的时刻是「光标已在输入框里、却还没想好写什么」。
 * 所以改为：聚焦时显示，或已经在输入内容时显示（此时提示的是换行方式）。
 * 好处是静息状态下输入区更干净，底部也不再多占一行。
 */
const showInputHint = computed(() => inputFocused.value || !!input.value.trim())

/** 输入框是否获得焦点：用于提示行显隐，以及键盘/触屏下的聚焦态表现 */
const inputFocused = ref(false)

/**
 * 是否可以发送。
 *
 * 抽成 computed 而不是在模板里写两遍 `input.trim()` ——
 * 按钮的 disabled 与 send-btn--ready（高亮态）必须用**同一个判断**，
 * 否则会出现「看起来可点但点了没反应」这类不一致。
 */
const canSend = computed(() => input.value.trim().length > 0)

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
  // Esc 停止生成：长回答时用户的手通常还在键盘上，
  // 强制去够鼠标点停止按钮是多余的
  if (e.key === 'Escape' && streaming.value) {
    e.preventDefault()
    stopStreaming()
    return
  }
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

/**
 * 全局 Esc：关闭窄屏抽屉。
 *
 * 原先抽屉只能靠点遮罩关闭 —— 遮罩是鼠标操作，键盘用户打开抽屉后
 * 就出不去了（Tab 会一路走到抽屉里的会话项，却找不到关闭入口）。
 * 遮罩上补 tabindex 也只是权宜之计：遮罩不是内容，让它可聚焦本身就是
 * 语义错误。用 Esc 才是这个交互的键盘等价操作。
 *
 * 挂在 window 而非某个元素：抽屉打开时焦点可能在抽屉内任意位置，
 * 只有全局监听才能稳定捕获。
 */
function onGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && sideOpen.value) {
    sideOpen.value = false
  }
  // 键盘翻页同样算「用户主动往上读」，用于停止自动跟随（见 onKeyIntent）
  onKeyIntent(e)
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
  // 全局 Esc：关闭窄屏抽屉（见 onGlobalKeydown 的说明）
  window.addEventListener('keydown', onGlobalKeydown)

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

onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
})

watch(streaming, (v) => {
  // 生成结束时强制把最终内容带到视野：用户可能刚发完就往下翻，
  // 但结果出来时应当能看到（这是他等待的东西）。
  // 若此时他正停在底部附近，这个调用本身也不会有副作用。
  if (!v) scrollToBottom(false, true)
})
</script>

<template>
  <div class="chat-page">
    <AppNavbar />

    <main
      id="main"
      tabindex="-1"
      class="chat-main"
      :class="{ 'chat-main--folded': sideFolded }"
    >
      <!-- ==================== 侧边栏 ==================== -->
      <!-- 窄屏为抽屉，遮罩点击关闭 -->
      <!--
        窄屏抽屉遮罩：点击关闭。
        遮罩本身不是内容，标 aria-hidden 免得读屏器把它读成一个元素。
      -->
      <div
        v-if="sideOpen"
        class="side-backdrop"
        aria-hidden="true"
        @click="sideOpen = false"
      ></div>
      <aside
        class="chat-side"
        :class="{ 'chat-side--open': sideOpen, 'chat-side--folded': sideFolded }"
        aria-label="会话列表"
      >

        <div class="chat-side__head">
          <!--
            顶部操作区：三个图标按钮，从左到右依次是
              ① 折叠/展开侧栏   ② 搜索会话   ③ 新建会话
            顺序按使用频率与「从整体到具体」排：先控制这块区域本身，
            再在其中查找，最后是创建新内容。

            只用图标不配文字（每个都有 title 与 aria-label）：
            三个按钮横排已经很紧凑，加文字会把标题行挤掉。
          -->
          <div class="side-acts">
            <button
              class="side-act"
              type="button"
              :aria-label="sideFolded ? '展开会话列表' : '折叠会话列表'"
              :aria-expanded="!sideFolded"
              :title="sideFolded ? '展开会话列表' : '折叠会话列表'"
              @click="toggleFold"
            >
              <!-- 面板图标（矩形 + 左竖线），不是箭头：箭头会被读成「返回」 -->
              <TravelIcon name="panel" :size="17" />
            </button>

            <button
              class="side-act"
              type="button"
              :disabled="!conversations.length"
              aria-label="搜索会话"
              title="搜索会话（可按对话内容搜索）"
              @click="openSearch"
            >
              <TravelIcon name="search" :size="17" />
            </button>

            <span class="side-acts__spacer"></span>
            <span v-if="conversations.length" class="chat-side__count">
              {{ conversations.length }}
            </span>
          </div>
        </div>

        <!--
          新建会话：展开态的主操作，占满整行、实心主色。
          刻意**不用「+」图标** —— 用户明确要求它与折叠态的那个 + 区分开：
          展开时有足够横向空间，一句话说清动作比一个符号好认；
          折叠成窄竖列时才退回 + 图标（见 .side-rail 里的第三个按钮）。
        -->
        <button
          class="side-new"
          type="button"
          :disabled="streaming"
          @click="newConversation"
        >
          <TravelIcon name="plane" :size="16" />
          开始新会话
        </button>

        <!--
          原侧栏内联搜索框已移除：搜索改为屏幕中央的弹窗（见页面末尾的
          .search-modal），因为要支持**按对话内容搜索** —— 那需要拉取
          各会话的消息并展示命中片段，侧栏这点宽度放不下。
        -->

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

        <!--
          会话列表：按时间分组（今天 / 昨天 / 7 天内 / 30 天内 / 更早）。
          每组一个小标题，空组由 groupByTime 剔除（不显示只有标题的空段落）。

          语义：外层用 div，**每组各一个 ul 并带 aria-label**。
          若把组标题塞进同一个 ul 里，读屏器会把它当成一个列表项播报，
          与「这是个分组」的事实不符。
        -->
        <div v-else class="conv-groups">
          <section
            v-for="g in groupedConversations"
            :key="g.key"
            class="conv-group"
          >
            <h3 class="conv-group__label">{{ g.label }}</h3>
            <ul class="chat-side__list" :aria-label="g.label">
              <li v-for="conv in g.items" :key="conv.id">
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
          </section>
        </div>
      </aside>

      <!--
        折叠图标列（仅侧栏折叠时可见，见 .chat-main--folded）。

        ⚠️ 它是 .chat-main 的**直接子元素**，不是 .chat-side 的子元素。
        这一点是必需的：折叠时侧栏那一列宽度为 0，而侧栏自身又有
        overflow: hidden —— 图标列若放在侧栏内部，会被夹在零宽区域里
        裁掉／压在零宽盒子里，表现就是「三个按钮都看不见、也点不到」
        （实测：几何上按钮尺寸正常，但 elementFromPoint 命中的是主区）。

        放在这里则落在网格第 1 列（侧栏那一列），由容器 align-self: start
        定位；非折叠时侧栏占满该列 → 它被侧栏盖住；折叠时侧栏宽 0 →
        它显示出来。不需要额外的显示/隐藏规则。

        三个动作与展开态顶部操作栏一一对应，顺序也一致。
      -->
      <div class="side-rail">
        <button
          class="rail-btn"
          type="button"
          aria-label="展开会话列表"
          aria-expanded="false"
          title="展开会话列表"
          @click="toggleFold"
        >
          <!-- 与展开态顶部同一个面板图标，保证是同一个动作的同一种表示 -->
          <TravelIcon name="panel" :size="17" />
        </button>
        <button
          class="rail-btn"
          type="button"
          :disabled="!conversations.length"
          aria-label="搜索会话"
          title="搜索会话"
          @click="focusSearch"
        >
          <TravelIcon name="search" :size="17" />
        </button>
        <button
          class="rail-btn"
          type="button"
          :disabled="streaming"
          aria-label="创建新会话"
          title="创建新会话"
          @click="newConversation"
        >
          <TravelIcon name="plus" :size="17" />
        </button>
      </div>

      <!--
        极细分割线。只占 1px 的独立网格列，折叠时该列归零自动消失。
        背景色差本身已能区分左右，这条线是给「浅色主题下两者差异较小」
        兜底，让边界更明确。
      -->
      <div class="chat-divider" aria-hidden="true"></div>

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

          <!--
            引导卡片：把最常用的三类场景摆出来。
            原先空态只有一串示例胶囊，用户不知道「这个助手到底能做什么」；
            卡片带标题与一句说明，既回答能力范围，也给出可直接点的起点。
          -->
          <div class="chat-empty__guides">
            <button
              v-for="g in EMPTY_GUIDES"
              :key="g.title"
              type="button"
              class="guide-card"
              @click="input = g.prompt; inputEl?.focus()"
            >
              <span class="guide-card__icon" aria-hidden="true">
                <TravelIcon :name="g.icon" :size="18" />
              </span>
              <span class="guide-card__title">{{ g.title }}</span>
              <span class="guide-card__desc">{{ g.desc }}</span>
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
                <!--
                  生成中只显示一个简短状态，不重复消息区的阶段文字。
                  工具条常驻可见、消息区会随滚动离开视野，所以两边都需要
                  一个「还在进行」的信号；但把同一句「正在理解你的需求」
                  渲染两遍是冗余的——细节留给用户正在看的那一处。
                -->
                <span v-if="streaming" class="tstatus tstatus--busy">
                  <i class="tstatus__dot"></i>生成中
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
              <!--
                工具条只保留「提取行程」这一个动作。
                原先还有两个按钮，均已移除：
                  · 重命名 —— 侧栏会话项点标题即可就地编辑，这里是重复入口，
                    而且它只是把焦点移到侧栏，用户看到光标跳走反而困惑
                  · 分享 / 导出 —— 它并不分享对话内容，只是跳到「行程」页，
                    属于「看起来有用但点进去还要再来一遍」的伪入口
              -->
              <button
                class="tool-btn tool-btn--accent"
                :disabled="streaming || !canExtract"
                :title="canExtract ? '把最后一条回答整理成行程' : '先让 AI 给出一份行程安排'"
                @click="handleExtract"
              >
                <TravelIcon name="luggage" :size="15" />
                提取行程
              </button>
            </div>
          </div>

          <!--
            这里原先还有一条全宽的「流式状态条」（波浪动画 + streamPhase）。
            已移除，因为同一句话被渲染了两遍：
              - 消息区的等待块（首字未到时的三点 + 阶段文字）
              - 这条状态条
            两者都表达「AI 正在做什么」，且同时出现。此外它是一条通栏的
            强调色横条，出现与消失会推挤整个消息区，视觉重量远大于信息量。
            工具条上保留了一个安静的「生成中」，让滚走消息区时仍有信号。
          -->

          <!-- 消息区 -->
          <div
            ref="scrollEl"
            class="chat-scroll"
            @scroll.passive="onStreamScroll"
            @wheel.passive="onWheelIntent"
            @touchstart.passive="onTouchStartIntent"
            @touchmove.passive="onTouchMoveIntent"
          >
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

          <!--
            「回到底部」箭头：只在用户滚离底部时出现。

            为什么需要：修正自动跟随逻辑后（用户翻历史时不再被拽走），
            用户就不知道下面还有新内容在生成。这个箭头补上那个信号，
            点一下就回到底部并恢复自动跟随。
          -->
          <Transition name="jump">
            <button
              v-if="awayFromBottom"
              type="button"
              class="jump-bottom"
              :class="{ 'jump-bottom--live': streaming }"
              :aria-label="streaming ? '正在生成，点击回到底部' : '回到底部'"
              :title="streaming ? '正在生成，点击回到底部' : '回到底部'"
              @click="jumpToBottom"
            >
              <TravelIcon name="arrow-right" :size="16" />
              <span class="jump-bottom__text">
                {{ streaming ? '正在生成' : '新消息' }}
              </span>
            </button>
          </Transition>

          <!--
            输入区：快捷提示与输入框**收在同一个容器里**，共享一层边框与聚焦环。
            原先两者是上下相邻的两个独立块（快捷条在外、输入框自己带边框），
            视觉上只是「挨着」；合起来之后它们是一组，聚焦时整组一起高亮，
            「这些芯片是用来填这个框的」这层关系就不用靠猜。
          -->
          <div class="composer">
            <!--
              快捷示例：只在输入框为空且没在生成时出现。
              用户一旦开始打字就收起 —— 那时的建议会变成干扰。
              横向滚动（不换行）：窄屏下不会挤成多行把输入框顶上去。
            -->
            <Transition name="chips">
              <div v-if="showQuickChips" class="composer__chips">
                <span class="composer__chips-label">试试</span>
                <div class="composer__chips-scroll">
                  <button
                    v-for="(q, qi) in quickPrompts"
                    :key="q"
                    type="button"
                    class="quick-chip"
                    :class="`quick-chip--${chipTone(q, qi)}`"
                    @click="input = q; inputEl?.focus()"
                  >
                    {{ q }}
                  </button>
                </div>
              </div>
            </Transition>

            <div class="composer__row">
              <textarea
                ref="inputEl"
                v-model="input"
                class="composer__box"
                rows="1"
                :placeholder="
                  streaming
                    ? '正在回答，稍候可以继续追问…'
                    : '说说你想去哪、几天、预算多少…'
                "
                :disabled="streaming"
                @keydown="onKeydown"
                @focus="inputFocused = true"
                @blur="inputFocused = false"
                aria-label="输入你的旅行需求"
              ></textarea>

              <!--
                底部条：左侧是快捷键与字数，右侧是发送按钮。
                按钮**收在框内**（而不是框外另起一列）——
                放在外面会把输入框挤短、整块拉得很长；收进来之后
                输入框能用满整行宽度，视觉上也更像常见的对话输入框。

                键帽提示按需淡出（不是 v-if 移除）：位置始终占着，
                否则按钮会随提示显隐左右跳动。
              -->
              <div class="composer__foot">
                <span class="kbd-hint" :class="{ 'kbd-hint--hidden': !showInputHint }">
                  <template v-if="!streaming">
                    <kbd>Enter</kbd> 发送
                    <span class="kbd-hint__sep">·</span>
                    <kbd>Shift</kbd><kbd>Enter</kbd> 换行
                  </template>
                  <!-- 生成中改提示「可中断」，否则用户不知道有这条快捷方式 -->
                  <template v-else>
                    <kbd>Esc</kbd> 停止生成
                  </template>
                </span>

                <span class="composer__foot-right">
                  <span v-if="input.trim()" class="charcount">{{ input.length }}</span>
                  <!--
                    流式期间同一个按钮变为「停止生成」。
                    用同一个位置而不是新增按钮：这里本就是「提交/取消本次生成」的位置，
                    语义随状态切换比并排两个按钮更符合直觉。
                  -->
                  <button
                    v-if="streaming"
                    class="send-btn send-btn--stop"
                    type="button"
                    aria-label="停止生成"
                    title="停止生成（已生成的内容会保留）"
                    @click="stopStreaming"
                  >
                    <span class="send-btn__stop" aria-hidden="true"></span>
                  </button>
                  <button
                    v-else
                    class="send-btn"
                    :class="{ 'send-btn--ready': canSend }"
                    :disabled="!canSend"
                    aria-label="发送消息"
                    title="发送（Enter）"
                    @click="send"
                  >
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M5 12h14M13 6l6 6-6 6" />
                    </svg>
                  </button>
                </span>
              </div>
            </div>
          </div>
        </template>
      </section>
    </main>

    <!--
      搜索弹窗（屏幕中央 + 背景遮罩）。

      为什么做成弹窗而不是侧栏内联：
        · 用户要求「点击搜索后在屏幕中央弹出」
        · 更重要的是它要**搜索对话内容** —— 那需要展示命中片段，
          侧栏那点宽度放不下；弹窗有完整的宽度与结果区。
      遮罩同时承担两件事：视觉上把背后的对话区淡化（聚焦搜索本身），
      以及点击空白处关闭。
    -->
    <Transition name="modal">
      <div
        v-if="searchOpen"
        class="search-mask"
        role="dialog"
        aria-modal="true"
        aria-label="搜索会话"
        @click.self="closeSearchModal"
      >
        <div class="search-box">
          <div class="search-box__head">
            <TravelIcon name="search" :size="17" />
            <input
              ref="searchEl"
              v-model="searchKeyword"
              class="search-box__input"
              type="search"
              placeholder="搜索会话标题或对话内容…"
              aria-label="搜索会话标题或对话内容"
              @keydown.esc.prevent="closeSearchModal"
            />
            <button
              v-if="searchKeyword"
              class="search-box__clear"
              type="button"
              aria-label="清除关键词"
              @click="searchKeyword = ''"
            >
              ✕
            </button>
            <kbd class="search-box__esc">Esc</kbd>
          </div>

          <div class="search-box__body">
            <!-- 内容仍在拉取时给提示：否则用户以为「内容搜不到」 -->
            <p v-if="contentLoading" class="search-box__hint">
              正在读取对话内容…
            </p>
            <p v-else-if="!searchKeyword.trim()" class="search-box__hint">
              输入关键词，可搜索会话标题与对话内容
            </p>

            <p
              v-if="searchKeyword.trim() && !groupedResults.length && !contentLoading"
              class="search-box__empty"
            >
              没有匹配的会话
            </p>

            <div class="search-box__results">
              <section
                v-for="g in groupedResults"
                :key="g.key"
                class="search-group"
              >
                <h3 class="search-group__label">{{ g.label }}</h3>
                <ul class="search-group__list" :aria-label="g.label">
                  <li v-for="conv in g.items" :key="conv.id">
                    <button
                      type="button"
                      class="search-hit"
                      @click="pickResult(conv.id)"
                    >
                      <span class="search-hit__title">{{ conv.title || '新会话' }}</span>
                      <span class="search-hit__meta">
                        {{ convTime(conv.created_at) }}
                      </span>
                      <!-- 命中内容时给出片段；只命中标题时没有片段 -->
                      <span
                        v-if="hitSnippet(conv.id, searchKeyword)"
                        class="search-hit__snippet"
                      >{{ hitSnippet(conv.id, searchKeyword) }}</span>
                    </button>
                  </li>
                </ul>
              </section>
            </div>
          </div>
        </div>
      </div>
    </Transition>
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

/* ============================================================
   对话页主容器
   ------------------------------------------------------------
   原先左侧会话列表与右侧对话区是**两个独立的圆角卡片**并排：
   各自带 border / border-radius / background，中间隔着 16px 的 gap
   —— 视觉上是「两块拼在一起」，切换视线时会有明显的断裂感。

   现在改为**一个整体面板**：
     · 容器自身承担边框与圆角，内部两块不再各画边框
     · 去掉 gap，两块紧邻，靠**背景色差**区分左右
       侧栏 --bg2（比页面底色略深一档）/ 主区 --panel（白）
       这两个变量在设计系统里本就是这个层级关系，直接拿来用
     · 两者之间只留 1px 极细分割线（--hairline 太淡、--border 更清楚）
     · 分割线宽度用变量 --divider-w 控制：折叠侧栏时归零，
       既不用改 border-width（那会跳变），也不用条件类
   ============================================================ */
.chat-main {
  flex: 1;
  min-height: 0;
  display: grid;
  /* 侧栏宽度用变量控制：折叠时只改变量，主区自动铺满，
     不必让 JS 参与布局计算 */
  --side-w: 272px;
  --divider-w: 1px;
  grid-template-columns: var(--side-w) var(--divider-w) 1fr;
  margin: 0 16px 16px;
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  background: var(--panel);
  position: relative;
  z-index: 1;
  transition: grid-template-columns 0.26s cubic-bezier(0.2, 0.7, 0.2, 1);
}
/* 折叠态：侧栏让位，分割线一并归零，否则会留一条孤立的竖线。
   用容器自身的修饰类而不是 :has(.chat-side--folded)：
   折叠会连带影响工具栏内边距，把状态放在容器上、由一处决定全部后果，
   比让多条规则各自去 :has() 里猜更清楚，也少一层嵌套选择器。 */
.chat-main--folded {
  --side-w: 0px;
  --divider-w: 0px;
}
@media (prefers-reduced-motion: reduce) {
  .chat-main { transition: none; }
}

/* ==================== 侧边栏 ==================== */
.chat-side {
  /*
   * 不再是独立卡片：边框与圆角交给外层容器，这里只负责背景。
   * 用 --bg2 而不是 --panel —— 比主区的白底深一档，
   * 于是左右两侧靠**背景色差**自然分开，而不需要两条边框。
   * 左侧圆角仍需自己画：容器没有 overflow:hidden（见 .chat-main 注释）。
   */
  background: var(--bg2);
  border-radius: var(--r-m) 0 0 var(--r-m);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  /* ::after / 折叠按钮的绝对定位以它为参照 */
  position: relative;
  /* min-width:0 是折叠所必需：否则内容的最小宽度会把网格列撑住，
     即使轨道被设为 0 也收不回去（flex/grid 的经典坑） */
  min-width: 0;
}

/*
 * 折叠态。
 *
 * ## 为什么不能只把宽度收成 0
 *
 * 折叠/展开的按钮**就在侧栏内部**。把整块收成 0 之后按钮也跟着消失 ——
 * 结果是「收得起来、展不开」，用户被锁在折叠状态里。
 * （实测：toggleFold 原本全项目只有一个调用点，且在该按钮上。）
 *
 * ## 做法
 *
 *   1. 侧栏内容整体淡出（`:not(.side-rail)` —— **必须排除图标列**，
 *      否则连展开按钮一起淡掉，等于没修）
 *   2. 图标列改为绝对定位，脱离「宽度归零」的影响，钉在面板左侧
 */
.chat-side--folded > *:not(.side-rail) {
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease;
}

/* ============================================================
   折叠图标列
   ------------------------------------------------------------
   它是 .chat-main 的直接子元素，占据网格第 1 列（侧栏那一列）。
   靠**层叠顺序**自动显隐，不需要 display 切换：
     · 展开态：.chat-side 占满该列，且是后绘制顺序更早但宽度完整
       —— 图标列被它盖住（同时我们用 .chat-main--folded 精确控制）
     · 折叠态：该列宽度为 0，侧栏不可见，图标列显示出来
   用 position: absolute + align-self: start：不参与撑高，
   只占顶部一小块，右边留给主区。
   ============================================================ */
.side-rail {
  display: none;   /* 展开态不显示，避免与顶部操作栏重复 */
}
.chat-main--folded .side-rail {
  display: flex;
  flex-direction: column;
  gap: 6px;
  /*
   * 定位在网格第 1 列内、贴左上角。
   * 用 absolute 是必要的：容器那条 1px 分割线列会让「侧栏列」的
   * 实际可用宽度只有 0px，普通流里的元素会被挤成 0 宽。
   */
  position: absolute;
  top: 9px;
  left: 9px;
  z-index: 3;
}
/* 与 .side-act 同一套外观，让「同一个动作」在两种形态下长得一样 */
.rail-btn {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text2);
  transition: background-color 0.18s, border-color 0.18s, color 0.18s,
    transform 0.18s;
}
.rail-btn:hover:not(:disabled) {
  background: var(--panel);
  border-color: var(--border);
  color: var(--prim);
}
.rail-btn:active:not(:disabled) { transform: translateY(0); }
.rail-btn:disabled { opacity: 0.38; cursor: not-allowed; }
.rail-btn:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}

/*
 * 分割线：占据 .chat-main 的中间那一列（见 grid-template-columns）。
 * 独立成元素而不是给侧栏画 border-right，原因：
 *   · 侧栏需要保留自己的 overflow:hidden（内部列表要滚动裁剪），
 *     边框画在它身上会在折叠时随宽度变化而跳变
 *   · 折叠时该列宽度归零，线条自然消失，不会留下孤立竖线
 */
.chat-divider {
  width: 100%;
  height: 100%;
  background: var(--border);
}
/*
 * ⚠️ 这里原有两条规则已删除：
 *
 *     .chat-side--folded      { opacity: 0; pointer-events: none }
 *     .chat-side--folded *    { pointer-events: none }
 *
 * 它们把**整栏连同图标列**一起禁用点击，而图标列正是折叠后唯一的
 * 「展开」入口 —— 结果就是「折叠后再也点不开」。
 * 我新增 .side-rail 时没删掉它们，它们在样式表里更靠后，
 * 把我给图标列设的 pointer-events: auto 又覆盖回 none（实测确认）。
 *
 * 淡出改由上面那条 `.chat-side--folded > *:not(.side-rail)` 负责，
 * 它排除了图标列，语义也更准确：要淡出的是**内容**，不是整个侧栏。
 */

/* ============================================================
   新建会话（展开态）
   ------------------------------------------------------------
   用户明确要求它与折叠态的「+」图标区分开：
   展开时有整行宽度，用**实心主色 + 文字**说清动作，比一个符号好认；
   折叠成窄竖列时空间只够放「+」图标（见 .side-rail 的第三个按钮）。
   所以这里是「实心大按钮」，不是图标按钮 —— 它也是侧栏里唯一的主操作。
   ============================================================ */
.side-new {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  /* 左右与顶部操作栏对齐；下方留出与列表的间隔 */
  margin: 0 12px 10px;
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
@media (prefers-reduced-motion: reduce) {
  .side-new { transition: none; }
  .side-new:hover:not(:disabled) { transform: none; }
}

/* ============================================================
   会话列表：按时间分组
   ============================================================ */
.conv-groups {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: 10px;
}
.conv-group + .conv-group {
  /* 组间留白比组内项距更大，读起来才是「一组一组」而不是一长条 */
  margin-top: 14px;
}
/*
 * 组标题：小、灰、不抢视线，但要在滚动时能当锚点用。
 * 用 sticky 吸在滚动容器顶部 —— 会话多时用户滚到一半仍知道当前在哪一组。
 * 背景必须与侧栏底色一致，否则吸顶时会透出下面的列表项。
 */
.conv-group__label {
  position: sticky;
  top: 0;
  z-index: 1;
  margin: 0;
  padding: 6px 14px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--text3);
  background: var(--bg2);
}

/* ============================================================
   搜索弹窗
   ------------------------------------------------------------
   居中浮层 + 半透明遮罩：遮罩把背后的对话区淡化（用户要求的
   「背后淡化/遮罩处理」），同时点击空白可关闭。
   ============================================================ */
.search-mask {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  /* 顶部对齐而非正中：键盘弹出时（移动端）居中会让输入框被顶出视野 */
  align-items: flex-start;
  justify-content: center;
  padding: 12vh 20px 20px;
  background: rgba(15, 23, 42, 0.36);
  -webkit-backdrop-filter: blur(2px);
  backdrop-filter: blur(2px);
}
.search-box {
  width: min(620px, 100%);
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  background: var(--panel);
  border: 1px solid var(--border);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.24);
  overflow: hidden;
}
.search-box__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--hairline);
  color: var(--text3);
}
.search-box__input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 0.98rem;
  color: var(--text);
  outline: none;
}
.search-box__input::placeholder { color: var(--text3); }
.search-box__clear {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: none;
  background: var(--panel2);
  color: var(--text3);
  font-size: 0.72rem;
  cursor: pointer;
}
.search-box__clear:hover { color: var(--prim); }
/* Esc 键帽：告诉用户还有这条退出路径 */
.search-box__esc {
  font-family: var(--mono);
  font-size: 0.64rem;
  padding: 3px 6px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--panel2);
  color: var(--text3);
}

.search-box__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 0 12px;
}
.search-box__hint,
.search-box__empty {
  padding: 18px 18px;
  font-size: 0.84rem;
  color: var(--text3);
  text-align: center;
}
.search-group + .search-group { margin-top: 10px; }
.search-group__label {
  margin: 0;
  padding: 6px 18px;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--text3);
}
.search-group__list { list-style: none; margin: 0; padding: 0; }

.search-hit {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  padding: 9px 18px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.16s;
}
.search-hit:hover,
.search-hit:focus-visible {
  background: var(--primary-soft);
  outline: none;
}
.search-hit__title {
  font-size: 0.9rem;
  font-weight: 650;
  color: var(--text);
}
.search-hit__meta {
  font-size: 0.72rem;
  color: var(--text3);
}
/* 命中片段：让用户看到「为什么这条匹配」，而不是只给一个标题 */
.search-hit__snippet {
  margin-top: 2px;
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--text2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 弹窗进出：淡入 + 轻微上浮 */
.modal-enter-active,
.modal-leave-active { transition: opacity 0.18s ease; }
.modal-enter-active .search-box,
.modal-leave-active .search-box {
  transition: transform 0.2s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.modal-enter-from,
.modal-leave-to { opacity: 0; }
.modal-enter-from .search-box,
.modal-leave-to .search-box { transform: translateY(-8px) scale(0.99); }

@media (prefers-reduced-motion: reduce) {
  .modal-enter-active,
  .modal-leave-active,
  .modal-enter-active .search-box,
  .modal-leave-active .search-box { transition: none; }
  .modal-enter-from .search-box,
  .modal-leave-to .search-box { transform: none; }
}

/* ============================================================
   侧栏顶部操作区
   ------------------------------------------------------------
   结构：一行三图标（折叠 / 搜索 / 新建）+ 会话计数，下面一行标题。
   图标按钮统一 30px 方形、圆角 9px、透明底，悬停才浮出底色 ——
   三个按钮视觉上等权，不靠颜色抢注意力。
   「新建」默认带一点主色：它是这一行里唯一会「产生内容」的动作。
   ============================================================ */
.chat-side__head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 12px 10px;
}
.side-acts {
  display: flex;
  align-items: center;
  gap: 4px;
}
/* 把计数推到最右，三个按钮自然靠左成为一组 */
.side-acts__spacer { flex: 1; }

.side-act {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text2);
  transition: background-color 0.18s, border-color 0.18s, color 0.18s,
    transform 0.18s;
}
.side-act:hover:not(:disabled) {
  background: var(--panel);
  border-color: var(--border);
  color: var(--prim);
  transform: translateY(-1px);
}
.side-act:active:not(:disabled) { transform: translateY(0); }
.side-act:disabled { opacity: 0.38; cursor: not-allowed; }
.side-act:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}
/* 搜索展开时按钮保持「按下」态，让用户知道它对应下面那个输入框 */
.side-act[aria-expanded='true'] {
  background: var(--primary-soft);
  border-color: var(--blue-300);
  color: var(--prim);
}
.side-act--new { color: var(--prim); }



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

/*
 * 旧样式已清理：
 *   .side-fold         → 并入 .side-act（三个图标按钮共用一套外观）
 *   .side-new          → 并入 .side-act--new
 *     「新建」原本是一个占满整行、实心渐变的按钮，现在收进顶部操作栏
 *     变成图标按钮。代价是少了一句文字标签，收益是顶部只占一行、
 *     且与「折叠/搜索」处在同一视觉层级（它俩也不该被一个实心大按钮压住）。
 *     可发现性由 title + aria-label 兜底。
 * 保留说明是为了下次改这块时知道东西搬到哪了。
 */

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
/* 搜索框展开 / 收起：淡入 + 轻微下移，避免相邻的会话列表瞬移 */
.search-enter-active,
.search-leave-active {
  transition: opacity 0.2s ease, transform 0.2s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.search-enter-from,
.search-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
@media (prefers-reduced-motion: reduce) {
  .search-enter-active,
  .search-leave-active { transition: none; }
}
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
  /* 让「回到底部」箭头能相对消息区绝对定位 */
  position: relative;
  /*
   * 不再是独立卡片：不再画自己的边框与圆角，那些由外层 .chat-main 统一承担。
   * 背景保持 --panel（白）—— 与侧栏的 --bg2 形成色差，左右自然分开。
   * 右侧圆角仍需自己画：容器没有 overflow:hidden。
   */
  background: var(--panel);
  border-radius: 0 var(--r-m) var(--r-m) 0;
  overflow: hidden;
}

/*
 * 折叠时给图标列让位。
 *
 * 图标列被绝对定位钉在侧栏左上角（此时侧栏宽度为 0），
 * 会压在工具栏左端（会话标题）上面。这里把工具栏标题推开
 * —— 34px 按钮 + 左右各 6px 余量。
 */
.chat-main--folded .chat-toolbar {
  padding-left: 52px;
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

/* ---- 空状态的引导卡片 ----
   比一串示例胶囊更能说明「这个助手能做什么」：
   卡片有标题与一句说明，用户不必从示例文本里反推能力范围。 */
.chat-empty__guides {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  width: 100%;
  max-width: 640px;
  margin: 8px 0 6px;
}

.guide-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 16px 16px 15px;
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  background: var(--panel);
  text-align: left;
  transition: border-color 0.18s, background-color 0.18s, transform 0.18s,
    box-shadow 0.18s;
}
.guide-card:hover {
  border-color: var(--blue-200);
  background: var(--blue-50);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}
.guide-card:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}

.guide-card__icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--primary-soft);
  color: var(--prim);
  margin-bottom: 2px;
}
.guide-card__title { font-size: 0.92rem; font-weight: 650; color: var(--text); }
.guide-card__desc { font-size: 0.78rem; line-height: 1.6; color: var(--text3); }

@media (prefers-reduced-motion: reduce) {
  .guide-card:hover { transform: none; }
}

/* ---- 回到底部箭头 ----
   悬在消息区右下角。生成中把文案换成「正在生成」——
   此时下面的内容是流动的，说「新消息」不够准确。 */
.jump-bottom {
  position: absolute;
  right: 18px;
  bottom: 84px;        /* 让开输入区高度 */
  z-index: 5;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px 8px 12px;
  border-radius: 999px;
  border: 1px solid var(--blue-200);
  background: var(--panel);
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--prim);
  box-shadow: 0 6px 18px rgba(37, 99, 235, 0.16);
  transition: background-color 0.18s, transform 0.18s, box-shadow 0.18s;
}
.jump-bottom:hover {
  background: var(--blue-50);
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.2);
}
.jump-bottom:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}
/* 图标朝下：箭头本身是右向，转 90° 即向下，省一个图标 */
.jump-bottom :deep(svg) { transform: rotate(90deg); }

/* 生成中加一个呼吸点，表达「内容还在往下长」 */
.jump-bottom--live::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--prim);
  animation: jumpDot 1.2s ease-in-out infinite;
}
@keyframes jumpDot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}
@media (prefers-reduced-motion: reduce) {
  .jump-bottom:hover { transform: none; }
  .jump-bottom--live::before { animation: none; }
}

/* 箭头出入：从下方轻移淡入 */
.jump-enter-active,
.jump-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.jump-enter-from,
.jump-leave-to { opacity: 0; transform: translateY(8px); }

/* 窄屏隐藏文案，只留图标，避免遮挡内容 */
@media (max-width: 640px) {
  .jump-bottom { padding: 9px; right: 12px; bottom: 78px; }
  .jump-bottom__text { display: none; }
}

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
  /*
   * ⚠️ flex-shrink: 0 与 white-space: nowrap 是「横向滚动」能否成立的关键。
   *
   * flex 项默认 flex-shrink: 1，而 min-width: auto 又允许它被压到内容
   * 最小宽度以下 —— 结果在窄容器里芯片会被压窄、文字在里面折行：
   * 实测容器 420px 时单个芯片从 37px 高变成 94px 高，整行变成一堵墙，
   * 而 overflow-x: auto 根本没机会生效（因为内容被压缩到不溢出了）。
   * 加上这两条后芯片保持自身宽度、容器真正横向溢出，横滚才起作用。
   */
  flex-shrink: 0;
  white-space: nowrap;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 0.81rem;
  transition: color 0.18s, border-color 0.18s, background-color 0.18s, transform 0.18s,
              box-shadow 0.18s;
}
/*
 * 彩色芯片：8 个语义色，浅底 + 同族深字 + 稍深的边框。
 *
 * 底色都取 *-50 级别（或等价的极浅色），文字取 *-600/700 ——
 * 与行程标签（.ptag）用同一套「浅底深字」规则，所以两处放在一起不打架。
 * 边框用比底色略深一档的同族色，让芯片在浅色背景上有轮廓、不糊成一片。
 */
.quick-chip--food    { background: #fdf6e7; color: var(--gold-600);   border: 1px solid #f5e6c8; }
.quick-chip--budget  { background: var(--blue-50); color: var(--blue-700); border: 1px solid var(--blue-100); }
.quick-chip--weather { background: #eaf7fb; color: var(--cyan-600);   border: 1px solid #cdeaf3; }
.quick-chip--nature  { background: #eefaf1; color: var(--green-600);  border: 1px solid #d6f0de; }
.quick-chip--history { background: #f5f1fe; color: var(--purple-600); border: 1px solid #e6dcfb; }
.quick-chip--photo   { background: #fef3f8; color: var(--rose-600);   border: 1px solid #fbd9e8; }
.quick-chip--family  { background: #fff7ed; color: var(--amber-600);  border: 1px solid #fde8cf; }
.quick-chip--plan    { background: #eef4fb; color: #31527a;           border: 1px solid #d5e3f2; }

/* 深色主题：浅底深字在暗背景上发闷，改成半透明底 + 提亮文字 */
:root[data-theme='dark'] .quick-chip--food    { background: rgba(214, 158, 46, 0.16); color: var(--gold-400);   border-color: rgba(214, 158, 46, 0.3); }
:root[data-theme='dark'] .quick-chip--budget  { background: rgba(37, 99, 235, 0.16);  color: var(--blue-300);   border-color: rgba(37, 99, 235, 0.3); }
:root[data-theme='dark'] .quick-chip--weather { background: rgba(14, 165, 233, 0.16); color: var(--cyan-400);   border-color: rgba(14, 165, 233, 0.3); }
:root[data-theme='dark'] .quick-chip--nature  { background: rgba(56, 161, 105, 0.16); color: var(--green-400);  border-color: rgba(56, 161, 105, 0.3); }
:root[data-theme='dark'] .quick-chip--history { background: rgba(139, 92, 246, 0.16); color: var(--purple-400); border-color: rgba(139, 92, 246, 0.3); }
:root[data-theme='dark'] .quick-chip--photo   { background: rgba(244, 114, 182, 0.16); color: var(--rose-400);  border-color: rgba(244, 114, 182, 0.3); }
:root[data-theme='dark'] .quick-chip--family  { background: rgba(251, 191, 36, 0.16); color: var(--amber-400);  border-color: rgba(251, 191, 36, 0.3); }
:root[data-theme='dark'] .quick-chip--plan    { background: rgba(127, 168, 248, 0.14); color: var(--blue-300);  border-color: rgba(127, 168, 248, 0.28); }

/* 悬停：底色压深一档、边框用主色，明确「可点」 */
.quick-chip:hover {
  color: var(--prim);
  border-color: var(--blue-300);
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.12);
}

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

/* 流式阶段条的样式已随该组件一并移除。
   它曾是夹在工具条与消息区之间的一条通栏强调色横条，与消息区的等待块
   重复表达同一件事，且出现/消失会推挤消息区。相关规则
   （.phase / .phase__wave / keyframes wave / phase-enter|leave）全部删除，
   避免留下永不命中的死样式。 */

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

/*
 * 历史消息的虚拟化：让浏览器跳过**屏幕外**消息的渲染。
 *
 * 为什么不用固定高度的虚拟滚动：聊天消息高度完全不定（一段话可能两三行，
 * 也可能是一张表格 + 十几条行程条目），固定高度会算错位置导致滚动跳动；
 * 动态测量又要引入依赖与一套高度缓存。content-visibility 把「哪些元素需要
 * 渲染」交给浏览器，它自己知道视口在哪，比在 JS 里重算更准也更省。
 *
 * 为什么排除 :last-child：末条是**正在流式输出**的消息，它的高度每来一个字
 * 都在变。若也按估算值占位，估算与实测会交替生效，滚动位置就会抖。
 * 一条消息不参与虚拟化对性能没有影响。
 *
 * contain-intrinsic-size 用 `auto 200px` 而非单纯 `200px`：
 *   · 不写这一项，未渲染元素高度会被当成 0，滚动条长度随滚动不断跳变
 *     ——这是启用 content-visibility 最常见的副作用
 *   · `auto` 让浏览器**记住元素上次渲染的真实高度**，此后按真实值占位；
 *     只写 200px 则每次都重新估算，长消息多的会话往回滚会位置跳动
 *   · 200px 仅作为「尚未渲染过」时的初始估算
 *
 * 浏览器不支持时（如较老的 Safari）该规则被忽略，退化为全部渲染，
 * 也就是当前行为 —— 没有兼容性风险。
 */
.msg:not(:last-child) {
  content-visibility: auto;
  contain-intrinsic-size: auto 200px;
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

/* ============================================================
   输入区（composer）
   ------------------------------------------------------------
   结构：一个容器里放三行
     ① 快捷芯片行（可横向滚动，按需出现）
     ② 输入行：textarea + 发送按钮
     ③ 提示行：键帽 + 字数（按需出现）
   ①② 共享同一层边框与聚焦环 —— 这是「快捷芯片是用来填这个框的」
   这层关系唯一的视觉依据；原先两者各自独立，只能靠相邻去猜。
   ============================================================ */
.composer {
  flex-shrink: 0;
  /*
   * 最大宽度与消息流（.chat-stream 的 820px）对齐并居中。
   *
   * 原先是整块铺满可用宽度 —— 在宽屏上输入框会被拉到一千多像素，
   * 一行能塞下好几个句子，视觉上又长又空，与上方消息的宽度也对不齐。
   * 收窄到与消息同宽后，输入区与对话内容形成同一条中轴。
   */
  width: 100%;
  max-width: 820px;
  margin: 0 auto 16px;
  padding: 6px 8px 8px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: var(--panel);
  box-shadow: var(--shadow-sm);
  transition: border-color 0.2s, box-shadow 0.22s, background-color 0.2s;
}
/* 聚焦态：主色描边 + 柔和外环。整组一起亮，而不是只给 textarea 描边 */
.composer:focus-within {
  border-color: var(--prim);
  box-shadow: 0 0 0 3px var(--primary-soft), var(--shadow-sm);
}
/* 生成中降低视觉存在感，暗示此刻不该输入 */
.composer:has(.composer__box:disabled) {
  opacity: 0.72;
}

/* ---- ① 快捷芯片行 ---- */
.composer__chips {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 4px 8px 8px;
  border-bottom: 1px dashed var(--hairline);
  margin-bottom: 4px;
}
.composer__chips-label {
  flex-shrink: 0;
  font-size: 0.72rem;
  color: var(--text3);
  user-select: none;
}
/*
 * 芯片横向滚动而不换行。
 * 换行会让输入区在小屏上长高好几行、把消息区挤扁；
 * 横滚则始终保持一行高度，用户滑动即可看到其余建议。
 * 隐藏滚动条：它在这么窄的条里很扎眼，而横滚本身有「切了一半的芯片」作暗示。
 */
.composer__chips-scroll {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
  -ms-overflow-style: none;
  /* 右端渐隐，暗示「还能往右滑」 */
  mask-image: linear-gradient(90deg, #000 calc(100% - 20px), transparent);
  -webkit-mask-image: linear-gradient(90deg, #000 calc(100% - 20px), transparent);
}
.composer__chips-scroll::-webkit-scrollbar { display: none; }

/* ---- ② 输入行：textarea 在上、底部条在下，按钮收在框内 ---- */
.composer__row {
  display: flex;
  flex-direction: column;
}
.composer__box {
  width: 100%;
  /* 单行时约 40px 高，比原先的 34px 更好点、也更接近常见的聊天输入框 */
  min-height: 40px;
  max-height: 180px;
  resize: none;
  border: none;
  background: transparent;
  padding: 8px 8px 4px;
  font-size: 0.95rem;
  line-height: 1.55;
  color: var(--text);
}
.composer__box:focus { outline: none; }
.composer__box::placeholder { color: var(--text3); }
.composer__box:disabled { cursor: not-allowed; }

/* ---- ③ 底部条：左键帽、右发送 ---- */
.composer__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 32px;
  padding: 0 2px 0 8px;
}
.composer__foot-right {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
/*
 * 键帽提示：仍然「按需出现」的语义 —— 静息时淡出，聚焦或有内容时淡入。
 * 但它所在的位置**始终占位**（不是 v-if），这样按钮不会随提示显隐而左右跳动。
 */
.kbd-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.68rem;
  color: var(--text3);
  user-select: none;
  transition: opacity 0.2s ease;
}
.kbd-hint--hidden { opacity: 0; }
.kbd-hint kbd {
  font-family: var(--mono);
  font-size: 0.64rem;
  line-height: 1;
  padding: 3px 5px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--panel2);
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

/* ---- 发送按钮 ----
 *
 * 主次由**背景**区分，而不只是透明度：
 *   无内容 → 淡灰底、灰箭头、无光晕：明确是「还不能点」
 *   有内容 → 主题渐变实心 + 光晕 + 轻微放大：明确是「可以发了」
 * 原先两种情况共用同一套渐变底，只靠 opacity 0.42 区分 ——
 * 在浅色界面上「半透明的蓝按钮」仍然像可点，主次不够清晰。
 */
.send-btn {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 13px;
  background: var(--panel2);
  color: var(--text3);
  border: 1px solid var(--border);
  box-shadow: none;
  transition: transform 0.2s, box-shadow 0.22s, background-color 0.22s,
    color 0.22s, border-color 0.22s;
}
/* 有内容：实心主色 + 光晕 */
.send-btn--ready {
  background: var(--grad);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 6px 18px var(--glow);
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: saturate(1.08);
}
.send-btn--ready:hover:not(:disabled) {
  box-shadow: 0 10px 24px var(--glow);
}
.send-btn:active:not(:disabled) {
  transform: translateY(0);
}
.send-btn:disabled {
  cursor: not-allowed;
}

/*
 * 生成中的「停止」状态。
 *
 * 刻意用中性深灰而不是红色：中断是正常操作（用户改主意、发现需求说错了），
 * 不是危险动作。红色会让人以为「点下去会丢失什么」而不敢用。
 * 同时去掉渐变与光晕 —— 生成期间焦点应落在内容上，按钮不该持续发光吸引注意。
 */
.send-btn--stop {
  background: var(--slate-700);
  box-shadow: 0 4px 12px rgba(16, 24, 40, 0.18);
}
.send-btn--stop:hover {
  background: var(--slate-800);
  transform: translateY(-1px);
}
/* 方块＝停止，是播放器的通用符号，无需文字说明 */
.send-btn__stop {
  width: 13px;
  height: 13px;
  border-radius: 3px;
  background: #fff;
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
  .send-btn--stop:hover { transform: none; }
}

/* ---- 快捷示例条 ---- */
/*
 * 旧样式已清理：
 *   .quick-bar / .quick-bar__label  → .composer__chips / .composer__chips-label
 *     （布局由 flex-wrap 改为横向滚动，见 .composer__chips-scroll）
 *   .quick-chip--sm                 → 并入 .quick-chip（现在只有一个尺寸）
 * 保留说明是为了下次改这块时知道东西搬到哪了。
 */
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
  /* 窄屏只有一列：侧栏变成浮层抽屉，不再占据网格轨道，
     所以分割线那一列也要去掉（否则会多出一条 1px 的空列） */
  .chat-main {
    grid-template-columns: 1fr;
    margin: 0 10px 10px;
  }
  .chat-divider { display: none; }
  /*
   * 抽屉态下侧栏是固定定位的浮层，圆角与「左圆右直」的贴边样式都不适用，
   * 改成右侧圆角（从左边滑出）；背景仍用 --bg2，与浮层的身份一致。
   */
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
  /*
   * 窄屏不用「折叠」这套：侧栏本就是抽屉（用 sideOpen 控制），
   * 折叠态若也生效会让抽屉内容整体透明、无法使用。故全部还原。
   */
  .chat-side--folded > *:not(.side-rail) {
    opacity: 1;
    pointer-events: auto;
  }
  /*
   * ⚠️ 这里**不能**再写 `.chat-side--folded .side-rail { display: none }`。
   *
   * 我原先写的是：
   *     .chat-side--folded .side-rail,
   *     .side-rail { display: none; }
   * 其中 `.chat-side--folded .side-rail` 与基础规则
   * `.chat-side--folded .side-rail { display: flex }` **特异性完全相同**
   * （都是 0,2,0），而它位置更靠后 —— 于是媒体查询一旦命中，
   * 折叠态就被打成 display:none，**三个按钮全看不见**。
   * 这也是「折叠后根本看不到按钮」的真正原因。
   *
   * 而且这个重置本来就是多余的：`.side-rail` 基类已经是 display:none，
   * 窄屏不需要折叠这套（侧栏本就是抽屉），根本不会进入折叠态。
   */
  /* 「给浮出按钮让位」只针对宽屏折叠，窄屏下不适用 */
  .chat-main--folded .chat-toolbar {
    padding-left: 0;
  }

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
  /* 输入区在窄屏贴着容器边（不再叠加自身外边距，避免双重留白） */
  .composer { margin: 0 auto 12px; padding: 6px 6px 8px; }
  .composer__chips-scroll { gap: 5px; }
}

@media (max-width: 560px) {
  .chat-toolbar { padding: 10px 12px; }
  .chat-toolbar__title { font-size: 0.9rem; }
  .chat-scroll { padding: 18px 14px; }
}
</style>
