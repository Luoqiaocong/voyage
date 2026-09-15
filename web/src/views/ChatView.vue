<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import ToolTimeline from '@/components/ToolTimeline.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import type { ToolStep } from '@/types/tool'
import {
  createConversation,
  deleteConversations,
  getMessages,
  listConversations,
  renameConversation,
  streamChat,
  toolLabel,
  type ChatMessage,
  type Conversation
} from '@/api/conversation'
import { extractItinerary } from '@/api/itinerary'
import { useUiStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'
import { renderMarkdown } from '@/utils/md'
import { PAGE_COPY } from '@/constants/copy'

/** 会话消息：assistant 消息可携带本轮的工具调用与思考过程 */
interface RdMsg extends ChatMessage {
  tools?: ToolStep[]
  reasoning?: string
}

const router = useRouter()
const ui = useUiStore()
const user = useUserStore()

const conversations = ref<Conversation[]>([])
const activeId = ref<string | null>(null)
const messages = ref<RdMsg[]>([])
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

function normalizeMessages(raw: unknown[]): RdMsg[] {
  const out: RdMsg[] = []
  for (const m of raw as Array<{ role?: string; content?: unknown }>) {
    let content = m.content ?? ''
    if (Array.isArray(content)) {
      content = content
        .map((p) => (typeof p === 'string' ? p : ((p as { text?: string })?.text ?? '')))
        .join('')
    }
    const text = String(content).trim()
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
    const raw = await getMessages(id)
    messages.value = normalizeMessages(raw as unknown[])
  } catch (e: any) {
    ui.toast(e?.message ?? '历史消息加载失败', 'error')
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

async function handleRename(conv: Conversation) {
  const title = window.prompt('请输入新标题（1-64 个字符）', conv.title ?? '')
  if (title === null || !title.trim()) return
  const trimmed = title.trim()
  if (trimmed === conv.title) return
  if (trimmed.length > 64) {
    ui.toast('标题不能超过 64 个字符', 'error')
    return
  }
  try {
    await renameConversation(conv.id, trimmed)
    conv.title = trimmed
    ui.toast('标题已更新', 'success')
  } catch (e: any) {
    ui.toast(e?.message ?? '修改标题失败', 'error')
  }
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

async function handleExtract() {
  if (!activeId.value || streaming.value) return
  const sure = await ui.confirm('根据本次对话的完整内容提取并保存旅行行程？（可能耗时较长）')
  if (!sure) return
  ui.toast('AI 正在提取行程，请稍候…', 'info')
  try {
    const it = await extractItinerary(activeId.value)
    ui.toast(`行程已提取：${it.plan.destination}（${it.plan.days} 天）`, 'success', 4200)
    router.push(`/itineraries/${it.id}`)
  } catch (e: any) {
    ui.toast(e?.message ?? '行程提取失败，请确认对话中已包含可用攻略信息', 'error')
  }
}

/* ---------------- 发送 ---------------- */
async function send() {
  const text = input.value.trim()
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
  messages.value.push({ role: 'user', content: text })
  input.value = ''
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
      <aside class="chat-side" aria-label="会话列表">
        <div class="chat-side__head">
          <span class="chat-side__title">会话</span>
          <button class="btn btn-primary btn--sm" :disabled="streaming" @click="newConversation">
            ＋ 新建
          </button>
        </div>

        <div v-if="loadingList" class="chat-side__hint">加载中…</div>
        <div v-else-if="conversations.length === 0" class="chat-side__hint">
          还没有会话，点击「新建」开始
        </div>

        <ul class="chat-side__list">
          <li
            v-for="conv in conversations"
            :key="conv.id"
            class="conv-item"
            :class="{ 'conv-item--active': conv.id === activeId }"
            @click="openConversation(conv.id)"
          >
            <span class="conv-item__main">
              <span class="conv-item__title">{{ conv.title || '新会话' }}</span>
              <span class="conv-item__time">{{ conv.created_at?.slice(0, 10) }}</span>
            </span>
            <span class="conv-item__ops" @click.stop>
              <button class="icon-btn" title="重命名" aria-label="重命名会话" @click="handleRename(conv)">✎</button>
              <button class="icon-btn icon-btn--danger" title="删除" aria-label="删除会话" @click="handleDelete(conv)">✕</button>
            </span>
          </li>
        </ul>
      </aside>

      <!-- ==================== 主区域 ==================== -->
      <section class="chat-body">
        <!-- 空状态 -->
        <div v-if="!activeId" class="chat-empty">
          <div class="chat-empty__logo" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2.4" />
              <path d="M16 4.5 L18.8 13.2 L27.5 16 L18.8 18.8 L16 27.5 L13.2 18.8 L4.5 16 L13.2 13.2 Z" fill="currentColor" />
              <circle cx="16" cy="16" r="2.2" fill="var(--panel)" />
            </svg>
          </div>
          <h2>{{ PAGE_COPY.chatEmptyTitle }}</h2>
          <p>{{ PAGE_COPY.chatEmptyDesc }}</p>
          <div class="chat-empty__quick">
            <button
              v-for="q in ['帮我规划广州到北京的 3 天行程', '这周末去成都穿什么？', '查一下明天广州南到北京西的高铁']"
              :key="q"
              class="quick-chip"
              @click="input = q; inputEl?.focus()"
            >
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
            <span class="chat-toolbar__title">{{ activeConversation?.title || '新会话' }}</span>
            <div class="chat-toolbar__ops">
              <button class="btn btn-ghost btn--sm" :disabled="streaming" @click="handleExtract">
                🧳 提取行程
              </button>
              <button class="btn btn-ghost btn--sm" :disabled="streaming" @click="handleRename(activeConversation!)">
                ✎ 重命名
              </button>
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
              <div
                v-for="(msg, i) in renderedMessages"
                :key="i"
                class="msg"
                :class="`msg--${msg.role}`"
              >
                <!-- 助手头像 -->
                <span v-if="msg.role === 'assistant'" class="msg__avatar" aria-hidden="true">
                  <svg viewBox="0 0 32 32" fill="none">
                    <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2.6" />
                    <path d="M16 4.5 L18.8 13.2 L27.5 16 L18.8 18.8 L16 27.5 L13.2 18.8 L4.5 16 L13.2 13.2 Z" fill="currentColor" />
                  </svg>
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

                  <!-- 正文：助手走 Markdown，用户走纯文本 -->
                  <div
                    v-if="msg.content && msg.role === 'assistant'"
                    class="msg__bubble md-body"
                    :class="{ 'msg__bubble--err': !!streamError && i === renderedMessages.length - 1 && streaming }"
                    v-html="renderMarkdown(msg.content)"
                  ></div>
                  <div v-else-if="msg.content" class="msg__bubble">{{ msg.content }}</div>

                  <!-- 流式光标 -->
                  <span
                    v-if="streaming && i === renderedMessages.length - 1 && msg.content"
                    class="stream-caret"
                    aria-hidden="true"
                  ></span>
                </div>
              </div>

              <!-- 首字等待：三点 -->
              <div v-if="thinking" class="msg msg--assistant">
                <span class="msg__avatar" aria-hidden="true">
                  <svg viewBox="0 0 32 32" fill="none">
                    <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2.6" />
                    <path d="M16 4.5 L18.8 13.2 L27.5 16 L18.8 18.8 L16 27.5 L13.2 18.8 L4.5 16 L13.2 13.2 Z" fill="currentColor" />
                  </svg>
                </span>
                <div class="msg__col">
                  <div class="typing" aria-label="AI 正在生成">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 输入区 -->
          <div class="chat-inputbar">
            <div class="chat-inputbar__field">
              <textarea
                ref="inputEl"
                v-model="input"
                class="textarea chat-inputbar__box"
                rows="1"
                :placeholder="streaming ? 'AI 正在回答中…' : '例如：帮我规划 8/17-8/19 广州到北京的行程，预算 500 元以内'"
                :disabled="streaming"
                @keydown="onKeydown"
              ></textarea>
              <span class="chat-inputbar__hint">Enter 发送 · Shift + Enter 换行</span>
            </div>
            <button
              class="btn btn-primary chat-inputbar__send"
              :disabled="streaming || !input.trim()"
              @click="send"
            >
              <template v-if="streaming">生成中…</template>
              <template v-else>
                发送
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M5 12h14M13 6l6 6-6 6" />
                </svg>
              </template>
            </button>
          </div>
        </template>
      </section>
    </main>
  </div>
</template>

<style scoped>
.chat-page { height: 100vh; display: flex; flex-direction: column; position: relative; z-index: 1; }

.chat-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 272px 1fr;
  margin: 0 16px 16px;
  gap: 16px;
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

.chat-side__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--hairline);
}

.chat-side__title { font-family: var(--font-display); font-size: 1rem; font-weight: 700; }

.chat-side__hint { padding: 18px 16px; color: var(--text3); font-size: 0.82rem; line-height: 1.6; }

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
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 11px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}
.conv-item:hover { background: var(--panel2); }
.conv-item--active {
  background: var(--grad-soft);
  border-color: var(--border);
  box-shadow: inset 2px 0 0 var(--prim);
}

.conv-item__main { flex: 1; min-width: 0; }

.conv-item__title {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-item__time { font-size: 0.68rem; color: var(--text3); }

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
  color: #fff;
  display: grid;
  place-items: center;
  border-radius: 18px;
  background: var(--grad);
  box-shadow: 0 12px 30px var(--glow);
}
.chat-empty__logo svg { width: 38px; height: 38px; }
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
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel2);
  color: var(--text2);
  font-size: 0.81rem;
  transition: 0.18s;
}
.quick-chip:hover {
  color: var(--prim);
  border-color: var(--prim);
  background: var(--primary-soft);
  transform: translateY(-1px);
}

/* ---- 工具栏 ---- */
.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--hairline);
  flex-shrink: 0;
}

.chat-toolbar__title {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 0.98rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-toolbar__ops { display: flex; gap: 8px; flex-shrink: 0; }

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

.msg { display: flex; gap: 10px; align-items: flex-start; }
.msg--user { flex-direction: row-reverse; }
.msg--assistant { flex-direction: row; }

.msg__avatar {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--grad);
  color: #fff;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  margin-top: 2px;
  box-shadow: 0 4px 12px var(--glow);
}
.msg__avatar svg { width: 18px; height: 18px; }

.msg__col { display: flex; flex-direction: column; gap: 8px; min-width: 0; max-width: min(680px, 88%); }
.msg--user .msg__col { align-items: flex-end; max-width: min(600px, 84%); }

/* ---- 气泡 ---- */
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

.msg--assistant .msg__bubble {
  background: var(--bubble-ai);
  border: 1px solid var(--border);
  border-radius: 5px 16px 16px 16px;
  color: var(--text);
}

.msg__bubble--err {
  background: rgba(229, 72, 77, 0.08) !important;
  border-color: rgba(229, 72, 77, 0.3) !important;
  color: var(--danger) !important;
}

/* ---- 流式光标 ---- */
.stream-caret {
  display: inline-block;
  width: 7px;
  height: 15px;
  border-radius: 2px;
  background: var(--prim);
  animation: caret 1.05s steps(2) infinite;
  vertical-align: -2px;
}
@keyframes caret { 50% { opacity: 0; } }

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

/* ---- Markdown ---- */
.md-body :deep(p) { margin: 0 0 9px; }
.md-body :deep(p:last-child) { margin-bottom: 0; }
.md-body :deep(.md-inline) {
  background: var(--panel2);
  border: 1px solid var(--border);
  padding: 1px 6px;
  border-radius: 5px;
  font-family: var(--mono);
  font-size: 0.85em;
}
.md-body :deep(.md-code) {
  background: var(--ink-deep);
  color: #d8e6ee;
  padding: 12px 14px;
  border-radius: 10px;
  font-size: 0.85em;
  overflow-x: auto;
  margin: 9px 0;
}
:root[data-theme='dark'] .md-body :deep(.md-code) { background: #060a14; }
.md-body :deep(.md-h) { margin: 14px 0 7px; font-size: 1.02em; font-weight: 700; }
.md-body :deep(.md-h:first-child) { margin-top: 0; }
.md-body :deep(.md-list) { margin: 6px 0; padding-left: 1.25em; }
.md-body :deep(.md-list li) { margin: 3px 0; }
.md-body :deep(.md-quote) {
  margin: 9px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--primary);
  background: var(--primary-soft);
  border-radius: 0 8px 8px 0;
  color: var(--text2);
}
.md-body :deep(.md-hr) { border: none; border-top: 1px solid var(--hairline); margin: 14px 0; }
.md-body :deep(.md-a) { color: var(--prim); text-decoration: underline; }
.md-body :deep(.md-table-wrap) { overflow-x: auto; margin: 10px 0; }
.md-body :deep(.md-table) { border-collapse: collapse; width: 100%; font-size: 0.86em; }
.md-body :deep(.md-table th),
.md-body :deep(.md-table td) {
  border: 1px solid var(--border);
  padding: 7px 11px;
  text-align: left;
}
.md-body :deep(.md-table th) { background: var(--panel2); font-weight: 680; }

/* ---- 打字点 ---- */
.typing { display: flex; gap: 6px; padding: 14px 16px; background: var(--bubble-ai); border: 1px solid var(--border); border-radius: 5px 16px 16px 16px; width: fit-content; }
.typing span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--prim);
  animation: bounce 1.2s ease-in-out infinite;
}
.typing span:nth-child(2) { animation-delay: 0.15s; }
.typing span:nth-child(3) { animation-delay: 0.3s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40% { transform: translateY(-7px); opacity: 1; }
}

/* ---- 输入区 ---- */
.chat-inputbar {
  display: flex;
  gap: 10px;
  padding: 14px 18px 16px;
  border-top: 1px solid var(--hairline);
  align-items: flex-end;
  flex-shrink: 0;
  background: var(--panel);
}

.chat-inputbar__field { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }

.chat-inputbar__box {
  min-height: 46px;
  max-height: 160px;
  resize: none;
  background: var(--panel2);
}

.chat-inputbar__hint { font-size: 0.68rem; color: var(--text3); padding-left: 2px; }

.chat-inputbar__send { flex-shrink: 0; height: 46px; }

/* ==================== 响应式 ==================== */
@media (max-width: 860px) {
  .chat-main { grid-template-columns: 1fr; margin: 0 10px 10px; gap: 10px; }
  .chat-side { display: none; }
  .chat-toolbar__ops .btn { padding: 8px 10px; font-size: 0.78rem; }
  .msg__col { max-width: 92%; }
  .msg--user .msg__col { max-width: 88%; }
  .chat-inputbar__hint { display: none; }
}
</style>
