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
import { formatDateTime } from '@/utils/datetime'
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

/**
 * 活跃用户排行的口径。
 *
 * 用户要求「这都可以归为用户活跃排行，不必两个卡片，下拉框按不同规则排序
 * 就可以了」。原先「活跃用户排行」与「会话规模分布」是两张卡片，
 * 但前者按会话数、后者按消息数，本质是同一份数据的两种排法。
 *
 * 两种口径都只依赖已返回的 top_active_users 字段（conversations /
 * today_messages），切换时**不需要重新请求** —— 数据一次取回、本地重排，
 * 切换是瞬时的。后端的 ACTIVE_USER_POOL 已多取候选，保证两种排法
 * 各自的前 10 名都落在池子里。
 */
/** 折叠时保留可见的条数（用户要求「显示前十，折叠后面七位」） */
const RANK_VISIBLE = 3
const rankExpanded = ref(false)

const rankMetric = ref<'conversations' | 'today_messages'>('conversations')

/** 按选定口径重排；同值时用 user_id 保证顺序稳定 */
const rankedUsers = computed(() => {
  const list = [...(stats.value?.top_active_users ?? [])]
  const key = rankMetric.value
  list.sort((a, b) => {
    const diff = (b[key] ?? 0) - (a[key] ?? 0)
    return diff !== 0 ? diff : a.user_id - b.user_id
  })
  return list.slice(0, 10)
})

/** 折叠状态下只显示前三条 */
const visibleRank = computed(() =>
  rankExpanded.value ? rankedUsers.value : rankedUsers.value.slice(0, RANK_VISIBLE)
)

/** 被折叠起来的条数，用于按钮文案 */
const hiddenRank = computed(() => Math.max(0, rankedUsers.value.length - RANK_VISIBLE))

/**
 * 前三名的奖牌色识别。
 * 返回 gold / silver / bronze，其余为空。用**背景色**而不是 emoji 奖牌，
 * 免得与站内图标风格不一致（此前已统一去掉 emoji 图标）。
 */
function medalOf(index: number): string {
  return ['gold', 'silver', 'bronze'][index] ?? ''
}

function metricText(u: { conversations: number; today_messages: number }): string {
  return rankMetric.value === 'conversations'
    ? `${u.conversations} 个会话`
    : `今日 ${u.today_messages} 条消息`
}

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
        <!-- 后端已做向下取整（用户要求），此处不再格式化，
             避免前端再做一次 round 造成两处口径不一致 -->
        <p class="ccard__value">{{ stats?.avg_messages_per_conversation ?? '—' }}</p>
      </div>
      <!-- 原先这里还有一张「已生成标题」卡片。
           该指标只服务于「查看会话标题」，而标题已按隐私要求不再暴露，
           指标本身也一并从后端移除，故这里删掉这张卡片。 -->
    </div>

    <!--
      活跃用户排行：一个卡片 + 下拉切换口径。
      原先「活跃用户排行」（按会话数）与「会话规模分布」（按消息数）
      是两张卡片，本质是同一份数据的两种排法，合并后更省空间也更清楚。
      切换口径在本地重排，不重新请求 —— 数据已在前端。
    -->
    <section v-if="stats?.top_active_users.length" class="card conv__panel">
      <header class="conv__head">
        <h2>用户活跃排行</h2>
        <div class="conv__head-ops">
          <select
            v-model="rankMetric"
            class="select conv__sort"
            aria-label="排行口径"
          >
            <option value="conversations">按会话数</option>
            <option value="today_messages">按今日消息数</option>
          </select>
          <span class="conv__hint">仅统计规模，不含内容</span>
        </div>
      </header>

      <ul class="rank">
        <li v-for="(u, i) in visibleRank" :key="u.user_id">
          <!-- 前三名用金银铜底色；名次本身仍是数字，不比奖牌图标更难认 -->
          <span class="rank__no" :class="medalOf(i) ? `rank__no--${medalOf(i)}` : ''">
            {{ i + 1 }}
          </span>
          <span class="rank__email">{{ u.email }}</span>
          <span class="rank__count">{{ metricText(u) }}</span>
        </li>
      </ul>

      <!-- 折叠：默认只露前 3，其余收起。条数不多时不显示这个按钮 -->
      <button
        v-if="hiddenRank > 0"
        class="rank__toggle"
        type="button"
        @click="rankExpanded = !rankExpanded"
      >
        {{ rankExpanded ? '收起' : `展开其余 ${hiddenRank} 位` }}
      </button>
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
              <td class="table__mono table__date">{{ formatDateTime(c.created_at) }}</td>
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
  font-weight: 700;
  font-family: var(--mono);
  background: var(--surface-soft);
  color: var(--text2);
}
/*
 * 前三名金银铜。
 * 用底色区分而不是奖牌 emoji：站内图标已统一为 SVG，混入 emoji
 * 会在不同平台呈现成不同字形（此前已因这个原因清理过一批）。
 * 名次本身仍是数字，比图标更精确。
 */
.rank__no--gold { background: linear-gradient(135deg, #f0b429, #d69e2e); color: #fff; }
.rank__no--silver { background: linear-gradient(135deg, #cbd5e0, #a0aec0); color: #fff; }
.rank__no--bronze { background: linear-gradient(135deg, #d69e7a, #b7791f); color: #fff; }

.rank__email { font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank__count { font-size: 0.8rem; color: var(--text3); font-family: var(--mono); }

.rank__toggle {
  margin-top: 12px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: var(--r-s);
  background: var(--panel);
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--prim);
  transition: background-color 0.18s, border-color 0.18s;
}
.rank__toggle:hover { background: var(--blue-50); border-color: var(--blue-200); }
.rank__toggle:focus-visible { outline: 2px solid var(--prim); outline-offset: 2px; }

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
