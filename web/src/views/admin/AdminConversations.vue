<script setup lang="ts">
/**
 * 会话洞察：统计概览 + 活跃用户排行 + 会话列表检索。
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  getConversationStats,
  listConversations,
  type AdminConversationItem,
  type ConversationStats
} from '@/api/admin'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(false)
const stats = ref<ConversationStats | null>(null)
const items = ref<AdminConversationItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

async function loadStats() {
  try {
    stats.value = await getConversationStats()
  } catch (e: any) {
    ui.toast(e?.message ?? '会话统计加载失败', 'error')
  }
}

async function load() {
  loading.value = true
  try {
    const res = await listConversations({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value.trim() || undefined
    })
    items.value = res.items
    total.value = res.total
  } catch (e: any) {
    ui.toast(e?.message ?? '会话列表加载失败', 'error')
  } finally {
    loading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(keyword, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 320)
})

watch(page, load)

function goto(next: number) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
}

onMounted(() => {
  loadStats()
  load()
})
</script>

<template>
  <div class="conv">
    <!-- 统计卡 -->
    <div class="conv__cards">
      <div class="ccard">
        <p class="ccard__label">会话总数</p>
        <p class="ccard__value">{{ stats?.total_conversations ?? '—' }}</p>
      </div>
      <div class="ccard">
        <p class="ccard__label">消息总数</p>
        <p class="ccard__value">{{ stats?.total_messages ?? '—' }}</p>
      </div>
      <div class="ccard">
        <p class="ccard__label">平均每会话消息</p>
        <p class="ccard__value">{{ stats?.avg_messages_per_conversation ?? '—' }}</p>
      </div>
      <div class="ccard">
        <p class="ccard__label">已生成标题</p>
        <p class="ccard__value">{{ stats?.conversations_with_title ?? '—' }}</p>
      </div>
    </div>

    <!-- 活跃用户 -->
    <section v-if="stats?.top_active_users.length" class="card conv__panel">
      <header class="conv__head">
        <h2>活跃用户排行</h2>
        <span class="conv__hint">按会话数</span>
      </header>
      <ul class="rank">
        <li v-for="(u, i) in stats.top_active_users" :key="u.user_id">
          <span class="rank__no" :class="{ 'is-top': i === 0 }">{{ i + 1 }}</span>
          <span class="rank__email">{{ u.email }}</span>
          <span class="rank__count">{{ u.conversations }} 个会话</span>
        </li>
      </ul>
    </section>

    <!-- 会话列表 -->
    <section class="card conv__panel">
      <header class="conv__head">
        <h2>会话记录</h2>
        <input v-model="keyword" class="input conv__search" type="search" placeholder="按标题搜索…" />
      </header>

      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>会话 ID</th>
              <th>标题</th>
              <th>所属用户</th>
              <th>消息数</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in items" :key="c.id">
              <td class="table__mono">{{ c.id }}</td>
              <td>{{ c.title || '（无标题）' }}</td>
              <td class="table__email">{{ c.user_email }}</td>
              <td>{{ c.message_count }}</td>
              <td class="table__mono table__date">{{ c.created_at }}</td>
            </tr>
            <tr v-if="!loading && !items.length">
              <td colspan="5" class="table__empty">没有符合条件的会话</td>
            </tr>
            <tr v-if="loading">
              <td colspan="5" class="table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pager">
        <button class="btn btn-ghost btn--sm" :disabled="page <= 1" @click="goto(page - 1)">上一页</button>
        <span class="pager__info">{{ page }} / {{ totalPages }}　共 {{ total }} 条</span>
        <button class="btn btn-ghost btn--sm" :disabled="page >= totalPages" @click="goto(page + 1)">
          下一页
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.conv__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.ccard {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  padding: 16px 18px;
  box-shadow: var(--shadow-sm);
}
.ccard__label { font-size: 0.78rem; color: var(--text2); margin-bottom: 6px; }
.ccard__value { font-family: var(--font-display); font-size: 1.45rem; font-weight: 800; }

.conv__panel { padding: 20px 22px; margin-bottom: 20px; }
.conv__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.conv__head h2 { font-size: 0.98rem; font-weight: 700; }
.conv__hint { font-size: 0.75rem; color: var(--text3); }
.conv__search { flex: 0 1 240px; }

.rank { display: flex; flex-direction: column; gap: 10px; }
.rank li { display: grid; grid-template-columns: 26px 1fr auto; align-items: center; gap: 12px; }
.rank__no {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 0.72rem;
  font-family: var(--mono);
  background: var(--surface-soft);
  color: var(--text2);
}
.rank__no.is-top { background: var(--grad-gold); color: #fff; }
.rank__email { font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank__count { font-size: 0.8rem; color: var(--text3); font-family: var(--mono); }

.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.table th {
  text-align: left;
  font-weight: 600;
  color: var(--text3);
  font-size: 0.75rem;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.table td { padding: 11px 12px; border-bottom: 1px solid var(--hairline); }
.table__mono { font-family: var(--mono); font-size: 0.78rem; }
.table__date { color: var(--text3); white-space: nowrap; }
.table__email { color: var(--text2); }
.table__empty { text-align: center; color: var(--text3); padding: 30px 0; }

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding-top: 16px;
}
.pager__info { font-size: 0.82rem; color: var(--text2); font-family: var(--mono); }
</style>
