<script setup lang="ts">
/**
 * 会话洞察：统计概览 + 用户活跃排行 + Token 用量排行。
 *
 * 隐私边界（重要）：本页**只展示聚合数据**
 * （用户、消息数、Token 数），不展示会话标题或任何消息内容。
 * 原先有「按标题搜索」的检索框，那等于允许对全站用户的对话标题做
 * 关键词检索——标题是 LLM 从用户消息生成的，属于用户内容，已移除。
 *
 * 原先下方还有一张「会话规模分布」明细表（逐行列出会话 ID + 用户 +
 * 消息数 + 时间），已替换为 Token 用量排行。原因是会话 ID 是哈希串
 * （如 76a3160f3a83），而标题因隐私要求不返回 —— 用户既认不出是哪次对话，
 * 也无法据此做任何对比，作为排行它不成立。
 * 随之删除的还有一整套分页状态与请求（见下方注释）。
 */
import { computed, onMounted, ref } from 'vue'
import { getConversationStats, type ConversationStats } from '@/api/admin'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const stats = ref<ConversationStats | null>(null)

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

async function loadStats() {
  try {
    stats.value = await getConversationStats()
  } catch (e: any) {
    ui.toast(e?.message ?? '会话统计加载失败', 'error')
  }
}

/*
 * 原先此处有 load() / goto() / watch(sort) / watch(page) / totalPages
 * 与 items / total / page / pageSize / sort / loading 等一整套分页状态，
 * 服务于已被替换掉的「会话规模分布」明细表。
 * 明细表移除后它们全部失去引用，故一并删除 ——
 * 保留会让后来者以为「还有列表在拉数据」，也会白跑一次接口。
 */

/* ---------------- Token 用量排行 ---------------- */

const tokenExpanded = ref(false)

/** 按用量降序；同值时用 user_id 保证顺序稳定（否则每次都可能换位置） */
const rankedTokens = computed(() => {
  const list = [...(stats.value?.top_token_users ?? [])]
  return list
    .sort((a, b) => (b.tokens - a.tokens) || (a.user_id - b.user_id))
    .slice(0, 10)
})

const visibleTokens = computed(() =>
  tokenExpanded.value ? rankedTokens.value : rankedTokens.value.slice(0, RANK_VISIBLE)
)

const hiddenTokens = computed(() =>
  Math.max(0, rankedTokens.value.length - RANK_VISIBLE)
)

/**
 * Token 数压缩显示。
 * 六位数以上的原始值（如 923985）在小字号下既难读也容易数错位数，
 * 换成 924.0k 更直观；万以下保留原值，免得 2301 变成 2.3k 反而丢失精度。
 */
function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

onMounted(() => {
  // 只拉统计：两个排行（活跃 / Token）都在 getConversationStats 的响应里，
  // 不再有第二张需要分页请求的表
  loadStats()
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

    <!--
      Token 用量排行：替换原先的「会话规模分布」明细表。
      原先那张表逐行列出「会话 ID + 用户 + 消息数 + 时间」，但会话 ID 是
      哈希串（如 76a3160f3a83），而标题因隐私要求不返回 —— 用户既认不出
      是哪次对话，也无法据此做任何对比。作为排行它不成立。
      Token 排行同样是「用户维度」，但数值有明确含义、可横向比较。
    -->
    <section class="card conv__panel">
      <header class="conv__head">
        <h2>Token 用量排行</h2>
        <span class="conv__hint">
          仅统计引入该指标之后的用量，更早的数据没有用户维度
        </span>
      </header>

      <ul v-if="rankedTokens.length" class="rank">
        <li v-for="(u, i) in visibleTokens" :key="u.user_id">
          <span class="rank__no" :class="medalOf(i) ? `rank__no--${medalOf(i)}` : ''">
            {{ i + 1 }}
          </span>
          <span class="rank__email">{{ u.email }}</span>
          <span class="rank__count">
            {{ formatTokens(u.tokens) }} tokens · {{ u.calls }} 次调用
          </span>
        </li>
      </ul>
      <p v-else class="table__empty">
        暂无数据。Token 用量从本次上线后开始累积，发一条对话即可看到。
      </p>

      <button
        v-if="hiddenTokens > 0"
        class="rank__toggle"
        type="button"
        @click="tokenExpanded = !tokenExpanded"
      >
        {{ tokenExpanded ? '收起' : `展开其余 ${hiddenTokens} 位` }}
      </button>
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
/* 卡片头右侧的操作区（当前只有活跃排行的口径下拉） */
.conv__head-ops { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.conv__sort { flex: 0 0 190px; font-size: 0.82rem; }
/*
 * 原先此处有 .conv__privacy（带盾牌图标的「不展示会话内容」提示）。
 * 明细表移除后该提示也不再渲染 —— 现在页面上已没有任何会话级信息，
 * 无需再解释「为什么看不到内容」。相关样式一并删除。
 */

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

/*
 * 保留 table__empty：Token 排行的空态仍在用它（一条居中的提示文字）。
 * 其余 .table / .table-wrap / .table__mono / .table__date / .table__email
 * 与 .pager / .pager__info 都是「会话规模分布」明细表的样式，
 * 那张表已被 Token 排行替换，这些规则失去引用，故删除。
 */
.table__empty { text-align: center; color: var(--text3); padding: 30px 0; }
</style>
