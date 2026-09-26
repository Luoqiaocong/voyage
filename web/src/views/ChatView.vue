<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import SearchModal from '@/components/SearchModal.vue'
import ChatComposer from '@/components/ChatComposer.vue'
import MessageStream from '@/components/MessageStream.vue'
import type { ToolStep } from '@/types/tool'
import type { RdMsg } from '@/types/message'
import {
  createConversation,
  deleteConversations,
  getMessagesPage,
  listConversations,
  renameConversation,
  streamChat,
  toolLabel,
  type Conversation,
  type MessagesPage
} from '@/api/conversation'
import { useUiStore } from '@/stores/ui'
import { useChatAutoScroll } from '@/composables/useChatAutoScroll'
import { useItineraryExtract } from '@/composables/useItineraryExtract'
import { suggestFromContext } from '@/utils/quickSuggest'
import { formatRelative } from '@/utils/datetime'
import { groupByTime, isToday } from '@/utils/conversationGroup'
import { shouldShowWelcome as shouldShowWelcomePure } from '@/utils/welcomeGate'
import { useUserStore } from '@/stores/user'
import { PAGE_COPY } from '@/constants/copy'

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

/**
 * 输入区组件实例。焦点管理需要跨组件：欢迎屏关闭、切会话、生成结束
 * 这些时机都要把光标交回输入框，而输入框已收进 ChatComposer。
 */
const composerRef = ref<InstanceType<typeof ChatComposer> | null>(null)

/* ---------------- 流式临时状态 ---------------- */
const streamText = ref('')
const streamReasoning = ref('')
const streamTools = ref<ToolStep[]>([])
const streamError = ref('')

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
 * 自动跟随滚动（滚轮/触摸/键盘意图识别、是否跟随流式输出、回到底部）。
 * 实现与设计说明见 composables/useChatAutoScroll.ts。
 */
const {
  awayFromBottom,
  onStreamScroll,
  onWheelIntent,
  onTouchStartIntent,
  onTouchMoveIntent,
  onKeyIntent,
  scrollToBottom,
  jumpToBottom
} = useChatAutoScroll(scrollEl)

/* ---------------- 数据加载 ---------------- */
async function loadConversations() {
  loadingList.value = true
  try {
    conversations.value = await listConversations()
  } catch (e: any) {
    ui.toast(e?.message ?? '会话列表加载失败', 'error')
  } finally {
    loadingList.value = false
    // 无论成功失败都标记「已加载」：失败时不该永远停在空白等待态
    listLoaded.value = true
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
  /*
   * 点「新会话」就等于告诉系统：欢迎屏的使命结束了。
   *
   * 必须同时做两件事，缺一不可：
   *   1. welcomeDismissed = true —— 立刻把欢迎屏关掉。
   *      只有在「一条会话都没有」的场景下这一步才是决定性的：
   *      那时 shouldShowWelcome 由 conversations.length === 0 直接判真，
   *      **不看 lastWelcomeAt**，所以只写记录根本关不掉它 ——
   *      用户看到的就是「点了没反应」（这是实测复现过的 bug）。
   *   2. markWelcomeShown() —— 落一条「今天已经见过」的持久记录，
   *      让刷新后（welcomeDismissed 随内存重置）不再重新弹出来。
   */
  dismissWelcome()

  /*
   * 已经在草稿态：无需重来，把焦点交回输入框即可。
   *
   * 判据用 isDraft 而不是 `!activeId` —— 后者在**欢迎屏**上也为真，
   * 那时若不进入草稿态，输入框根本不在 DOM 里（欢迎屏分支没有 composer），
   * 后面那句 focus() 会静默失败。
   */
  if (isDraft.value) {
    await nextTick()
    composerRef.value?.focus()
    return
  }
  activeId.value = null
  messages.value = []
  resetStream()
  historyTruncated.value = false
  await nextTick()
  composerRef.value?.focus()
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
 * 行程提取：把当前会话的历史总结成行程。
 *
 * 判断条件、二次确认、调用提取、结果引导都在
 * composables/useItineraryExtract.ts；视图只消费它的返回值。
 */
const { extracting, rounds, canExtract, handleExtract } = useItineraryExtract({
  messages,
  activeId,
  streaming,
  router
})

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
      composerRef.value?.focus()
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
 * 折叠图标列里的「搜索」。
 *
 * ⚠️ 这里**不能**展开侧栏。搜索是屏幕中央的弹窗，与侧栏宽度无关；
 * 原先写了 sideFolded = false，于是折叠状态下点搜索会把侧栏又推开 ——
 * 用户明确报告过这个 bug：他折叠侧栏就是为了腾出宽度，结果一点搜索就弹回来。
 */
function focusSearch() {
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
 * 弹窗的展示、内容检索、命中片段等逻辑都在 components/SearchModal.vue，
 * 这里只保留开关状态，供侧栏/工具栏按钮触发。
 * 与侧栏内联搜索不同：弹窗支持**搜索对话内容**（用户要求），
 * 而内容不在列表接口里 —— 必须按会话逐条拉取消息。
 */
const searchOpen = ref(false)

function openSearch() {
  searchOpen.value = true
}

/* ==================== 欢迎屏 / 草稿态 ==================== */

/**
 * 欢迎屏的记录键：存上一次露面的**时刻**（ISO 字符串）。
 * 按用户区分，避免多账号在同一浏览器里互相影响。
 */
const WELCOME_KEY = 'voyage:chat-welcome-at'

/** 上一次欢迎屏露面的时刻；读不到返回空串。
 *  存时刻而不是日期：判定交给 isToday（与列表分组同一套自然日口径），
 *  自己再拼一次日期字符串容易在两者之间产生不一致。 */
const lastWelcomeAt = ref('')

/**
 * 这次进入是否该显示欢迎屏。
 *
 * 用户要求：欢迎屏只在**没有会话历史**、或**当天首次打开对话页**时出现。
 * 点「新会话」时不该再看到它（那是要开始打字，不是要看介绍）。
 *
 * 为什么不只用「有没有会话」判断：
 *   老用户每天第一次进来，给他一个空白输入框会显得空落落的；
 *   欢迎屏兼作「今天想去哪儿」的起手式。但同一天内反复点「新会话」
 *   就不该反复看到 —— 那才是打扰。
 */
/**
 * 会话列表是否已经加载过一次。
 *
 * ⚠️ 没有它就会**闪一遍欢迎屏**：挂载那一刻 conversations 还是空数组
 * （loadConversations 尚未返回），shouldShowWelcome 会先判为 true 并把
 * logo + 引导卡整屏渲染出来，等列表回来才切走 —— 用户看到的就是一闪。
 * 所以在「还没加载完」期间一律不显示欢迎屏与草稿态，宁可短暂空着。
 */
const listLoaded = ref(false)

/**
 * 本次进入对话页期间，用户是否已经主动关掉过欢迎屏。
 *
 * ⚠️ 没有这个标记就会出现「点了没反应」（实测复现过）：
 * 下面 shouldShowWelcome 在「一条会话都没有」时是**直接判真**的，
 * 因为它要先满足「新用户必须看到欢迎屏」。于是 markWelcomeShown()
 * 虽然写了 lastWelcomeAt，那个值却根本不参与判断 —— 欢迎屏卸不掉，
 * 欢迎屏那一分支里又没有 composer，用户点「开始新的旅程」看到的
 * 就是界面纹丝不动。
 *
 * 这两个状态回答的是不同的问题，不能合并：
 *   lastWelcomeAt    跨会话/跨天：今天是否已经见过欢迎屏（持久化）
 *   welcomeDismissed 本次进入：用户是否已经明确表示「我要开始打字了」
 *
 * 后者只活在内存里 —— 它代表一次点击，刷新后本就该重新按当天记录判断。
 */
const welcomeDismissed = ref(false)

/**
 * 这次进入是否该显示欢迎屏。
 *
 * 用户要求：只在**没有会话历史**、或**当天首次打开对话页**时出现。
 * 点「新会话」或引导卡时不该再看到它（那是要开始打字，不是要看介绍）。
 *
 * 注意这里的「不显示」有三个来源，别混：
 *   welcomeDismissed   用户刚点了「开始新的旅程」/「新会话」/引导卡
 *   listLoaded=false   数据还没到，先不判断（防闪烁）
 *   有会话且今天已显示过  用户今天已经见过，不必再看
 */
const shouldShowWelcome = computed(() =>
  shouldShowWelcomePure({
    dismissed: welcomeDismissed.value,
    listLoaded: listLoaded.value,
    conversationCount: conversations.value.length,
    lastWelcomeAt: lastWelcomeAt.value,
    // 沿用列表分组那套「本地自然日」口径，避免两处对「今天」的理解不一致
    isToday,
  })
)

/**
 * 草稿态：点过「新会话」、还没发出第一条消息。
 *
 * 与「欢迎屏」是**两个不同的界面**（这是上一版做错的地方）：
 *   欢迎屏：logo + 标题 + 三张引导卡 + 「开始新的旅程」按钮
 *   草稿态：只给输入框，让用户直接打字
 * 两者都满足 activeId 为空，所以必须用额外的状态区分，
 * 否则点「新会话」会看到欢迎屏、而按钮又无事可做。
 */
const isDraft = computed(() => !activeId.value && !shouldShowWelcome.value)


/** 侧栏列表按时间分组（今天/昨天/7 天内/30 天内/更早） */
const groupedConversations = computed(() => groupByTime(filteredConversations.value))

/**
 * 把一段文案填进输入框并聚焦。
 *
 * 欢迎屏上的引导卡会用到它 —— 而欢迎屏那一分支**没有输入框**
 * （composer 在另一个分支里），直接 focus 会静默失败。
 * 所以先离开欢迎屏（它已经完成使命：用户选好了起点），
 * 等输入框渲染出来再聚焦。
 */
async function fillInput(text: string) {
  input.value = text
  // 引导卡与快捷芯片都在欢迎屏上：点它等于「我要开始打字了」，
  // 于是关掉欢迎屏（同时落一条当天记录），让 composer 分支渲染出来
  if (shouldShowWelcome.value) dismissWelcome()
  await nextTick()
  composerRef.value?.focus()
}

/**
 * 关闭欢迎屏并记下「今天已经见过」。
 *
 * 抽成一个函数，是因为有两个入口都要做同样两件事
 * （「新会话」按钮与欢迎屏上的引导卡），漏做其中一件就会复现
 * 「点了没反应」—— 这个 bug 已经因为两处逻辑不一致出现过一次。
 */
function dismissWelcome() {
  welcomeDismissed.value = true
  markWelcomeShown()
}

/** 记录「欢迎屏刚刚露过面」，供 shouldShowWelcome 判断 */
function markWelcomeShown() {
  const now = new Date().toISOString()
  lastWelcomeAt.value = now
  try {
    localStorage.setItem(WELCOME_KEY, now)
  } catch {
    // 隐私模式等场景下 localStorage 不可用：退化为「本次会话内记住」，
    // 不影响功能，只是同一天重进可能再看到一次欢迎屏
  }
}


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

  // 读「上次欢迎屏露面时刻」，决定这次进来是给欢迎屏还是直接给输入框
  try {
    lastWelcomeAt.value = localStorage.getItem(WELCOME_KEY) ?? ''
  } catch {
    lastWelcomeAt.value = ''
  }

  user.fetchUserInfo().catch(() => {})
  await loadConversations()

  const raw = route.query.example
  const example = Array.isArray(raw) ? raw[0] : raw
  const autoText = typeof example === 'string' ? example.trim() : ''

  if (autoText) {
    await nextTick()
    router.replace({ path: route.path })
    await newConversation()
    await runTurn(autoText, true)
    return
  }

  if (conversations.value.length > 0) {
    await openConversation(conversations.value[0].id)
  }
})

/**
 * 欢迎屏一旦真的显示出来就记下时刻。
 *
 * ⚠️ 刻意**不加 immediate**：挂载那一刻 conversations 还是空数组
 * （loadConversations 尚未返回），会误判成「该显示欢迎屏」并把记录写掉 ——
 * 老用户当天就再也看不到欢迎屏了。只在它真正**变为**显示时记录。
 */
watch(shouldShowWelcome, (show) => {
  if (show) markWelcomeShown()
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
        <!--
          空状态 = 欢迎屏。
          显示条件不是「没有 activeId」而是 shouldShowWelcome：
          点「新会话」时 activeId 同样为空，但那时用户是要开始打字，
          不该再看到 logo 与引导卡（否则就像点了没反应）。
        -->
        <div v-if="shouldShowWelcome" class="chat-empty">
          <button
            class="side-toggle chat-empty__toggle"
            type="button"
            aria-label="展开会话列表"
            @click="sideOpen = !sideOpen"
          >
            <TravelIcon name="map" :size="16" />
            我的会话
          </button>
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
              @click="fillInput(g.prompt)"
            >
              <span class="guide-card__icon" aria-hidden="true">
                <TravelIcon :name="g.icon" :size="18" />
              </span>
              <span class="guide-card__title">{{ g.title }}</span>
              <span class="guide-card__desc">{{ g.desc }}</span>
            </button>
          </div>

          <!--
            「开始新的旅程」只在**一条会话都没有**时出现。
            此时它是唯一的起手式，点它把焦点交给下面的输入框。
            已有会话时不该出现：那时用户已经在对话页里了，
            「开始新的旅程」既啰嗦又容易与「新会话」混淆。
          -->
          <button
            v-if="!conversations.length"
            class="btn btn-primary"
            @click="newConversation"
          >
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
                :disabled="streaming || extracting || !canExtract"
                :title="extracting ? '正在生成行程' : canExtract ? '总结对话历史，整理成行程' : '先让 AI 给出一份行程安排'"
                @click="handleExtract"
              >
                <TravelIcon name="luggage" :size="15" />
                <span>{{ extracting ? '生成中…' : '提取行程' }}</span>
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
            <MessageStream
              :messages="renderedMessages"
              :streaming="streaming"
              :stream-error="streamError"
              :thinking="thinking"
              :stream-phase="streamPhase"
              :is-draft="isDraft"
              :history-truncated="historyTruncated"
              :history-rounds="HISTORY_ROUNDS"
              @copy="copyMessage"
              @regenerate="regenerate"
              @extract="handleExtract"
            />
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
            输入区已拆到 ChatComposer：快捷芯片、自适应高度、按键处理
            都封装在组件内，视图只负责把输入内容与生成状态接进来。
          -->
          <ChatComposer
            ref="composerRef"
            v-model="input"
            :streaming="streaming"
            :quick-prompts="quickPrompts"
            @send="send"
            @stop="stopStreaming"
            @pick="fillInput"
          />
        </template>
      </section>
    </main>

    <!--
      搜索弹窗（屏幕中央 + 背景遮罩）。

      做成弹窗的原因：用户要求「点击搜索后在屏幕中央弹出」，
      而且它要**搜索对话内容**，需要展示命中片段，侧栏宽度放不下。
      具体实现见 components/SearchModal.vue。
    -->
    <SearchModal
      v-model:open="searchOpen"
      :conversations="conversations"
      @select="openConversation"
    />
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

/*
 * 原 .chat-empty__logo（64px 圆角方块 + logo）已移除 —— 用户要求欢迎屏不要 logo。
 * 去掉后标题成为第一眼内容，视觉重心也从「品牌」回到了「开始对话」。
 */
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

.chat-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 22px 20px;
  scroll-behavior: smooth;
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
}

@media (max-width: 560px) {
  .chat-toolbar { padding: 10px 12px; gap: 8px; }
  .chat-toolbar__title { font-size: 0.9rem; }
  .chat-toolbar__status { display: none; }
  .chat-scroll { padding: 18px 14px; }
  .tool-btn { flex-shrink: 0; }
}
</style>
