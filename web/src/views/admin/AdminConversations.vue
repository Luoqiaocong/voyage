<script setup lang="ts">
/**
 * 会话洞察：统计概览 + 活跃用户排行 + 会话规模分布。
 *
 * 隐私边界（重要）：本页**只展示聚合数据与会话元数据**
 * （用户、消息数、时间），不展示会话标题或任何消息内容。
 * 原先有「按标题搜索」的检索框，那等于允许对全站用户的对话标题做
 * 关键词检索——标题是 LLM 从用户消息生成的，属于用户内容，已移除。
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  getConversationStats,
  listConversations,
  type AdminConversationItem,
  type ConversationStats
} from '@/api/admin'
import { useUiStore } from '@/stores/ui'
import TravelIcon from '@/components/TravelIcon.vue'

const ui = useUiStore()

const loading = ref(false)
const stats = ref<ConversationStats | null>(null)
const items = ref<AdminConversationItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
/** 排序维度：规模统计页默认按消息数看更直观，也可切回看最新动态 */
const sort = ref<'created_desc' | 'messages_desc'>('messages_desc')

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
    // 不再传 keyword：后端已移除按标题检索的能力
    const res = await listConversations({
      page: page.value,
      page_size: pageSize.value,
      sort: sort.value
    })
    items.value = res.items
    total.value = res.total
  } catch (e: any) {
    ui.toast(e?.message ?? '会话列表加载失败', 'error')
  } finally {
    loading.value = false
  }
}

// 切换排序后回到第 1 页，否则会停在一个可能已不存在的页码上
watch(sort, () => {
  page.value = 1
  load()
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
      <!-- 原先这里还有一张「已生成标题」卡片。
           该指标只服务于「查看会话标题」，而标题已按隐私要求不再暴露，
           指标本身也一并从后端移除，故这里删掉这张卡片。 -->
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

    <!-- 会话元数据（不展示任何会话内容） -->
    <section class="card conv__panel">
      <header class="conv__head">
        <h2>会话规模分布</h2>
        <div class="conv__head-ops">
          <select v-model="sort" class="select conv__sort" aria-label="排序方式">
            <option value="messages_desc">按消息数（多 → 少）</option>
            <option value="created_desc">按创建时间（新 → 旧）</option>
          </select>
          <span class="conv__privacy">
            <TravelIcon name="shield" :size="14" />
            仅展示规模与归属，不展示会话内容
          </span>
        </div>
      </header>

      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>会话 ID</th>
              <th>所属用户</th>
              <th>消息数</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in items" :key="c.id">
              <td class="table__mono">{{ c.id }}</td>
              <td class="table__email">{{ c.user_email }}</td>
              <td>{{ c.message_count }}</td>
              <td class="table__mono table__date">{{ c.created_at }}</td>
            </tr>
            <tr v-if="!loading && !items.length">
              <td colspan="4" class="table__empty">暂无会话</td>
            </tr>
            <tr v-if="loading">
              <td colspan="4" class="table__empty">加载中…</td>
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
/* 隐私提示：说明本页只展示元数据，消除「为什么看不到对话内容」的疑惑 */
.conv__head-ops { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.conv__sort { flex: 0 0 190px; font-size: 0.82rem; }
.conv__privacy {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text3);
}
.conv__privacy :deep(svg) { color: var(--success); flex-shrink: 0; }

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
