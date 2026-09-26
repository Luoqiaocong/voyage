<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import TravelIcon from '@/components/TravelIcon.vue'
import {
  getMessagesPage,
  type Conversation,
  type MessagesPage
} from '@/api/conversation'
import { groupByTime } from '@/utils/conversationGroup'
import { formatRelative } from '@/utils/datetime'

const props = defineProps<{
  open: boolean
  conversations: Conversation[]
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'select', id: string): void
}>()

const searchEl = ref<HTMLInputElement | null>(null)
const keyword = ref('')

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
  const todo = props.conversations.filter((c) => !contentLoaded.value.has(c.id))
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
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return props.conversations
  return props.conversations.filter((c) => {
    const title = (c.title ?? '').toLowerCase()
    if (title.includes(kw)) return true
    return (convContent.value[c.id] ?? '').includes(kw)
  })
})

const groupedResults = computed(() => groupByTime(searchResults.value))

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

/** 会话项显示的时间：今天显示时刻，更早显示日期 */
function convTime(createdAt?: string): string {
  return formatRelative(createdAt)
}

function close() {
  keyword.value = ''
  emit('update:open', false)
}

/** 点搜索结果：打开该会话并关掉弹窗 */
function pick(id: string) {
  close()
  emit('select', id)
}

watch(
  () => props.open,
  (open) => {
    if (!open) return
    void loadContents()
    void nextTick(() => searchEl.value?.focus())
  }
)
</script>

<template>
  <Transition name="modal">
    <div
      v-if="open"
      class="search-mask"
      role="dialog"
      aria-modal="true"
      aria-label="搜索会话"
      @click.self="close"
    >
      <div class="search-box">
        <div class="search-box__head">
          <TravelIcon name="search" :size="17" />
          <input
            ref="searchEl"
            v-model="keyword"
            class="search-box__input"
            type="search"
            placeholder="搜索会话标题或对话内容…"
            aria-label="搜索会话标题或对话内容"
            @keydown.esc.prevent="close"
          />
          <button
            v-if="keyword"
            class="search-box__clear"
            type="button"
            aria-label="清除关键词"
            @click="keyword = ''"
          >
            ✕
          </button>
          <kbd class="search-box__esc">Esc</kbd>
        </div>

        <div class="search-box__body">
          <p v-if="contentLoading" class="search-box__hint">
            正在读取对话内容…
          </p>
          <p v-else-if="!keyword.trim()" class="search-box__hint">
            输入关键词，可搜索会话标题与对话内容
          </p>

          <p
            v-if="keyword.trim() && !groupedResults.length && !contentLoading"
            class="search-box__empty"
          >
            没有匹配的会话
          </p>

          <div class="search-box__results">
            <section v-for="g in groupedResults" :key="g.key" class="search-group">
              <h3 class="search-group__label">{{ g.label }}</h3>
              <ul class="search-group__list" :aria-label="g.label">
                <li v-for="conv in g.items" :key="conv.id">
                  <button type="button" class="search-hit" @click="pick(conv.id)">
                    <span class="search-hit__title">{{ conv.title || '新会话' }}</span>
                    <span class="search-hit__meta">{{ convTime(conv.created_at) }}</span>
                    <!-- 命中内容时给出片段；只命中标题时没有片段 -->
                    <span
                      v-if="hitSnippet(conv.id, keyword)"
                      class="search-hit__snippet"
                    >{{ hitSnippet(conv.id, keyword) }}</span>
                  </button>
                </li>
              </ul>
            </section>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
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
</style>
