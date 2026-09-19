<script setup lang="ts">
/**
 * 管理台概览：核心指标卡 + 增长/消耗趋势 + 模型分布 + 系统健康 + CSV 导出。
 */
import { computed, onMounted, ref } from 'vue'
import {
  exportTokenUsageCsv,
  exportUsersCsv,
  getDashboardHealth,
  getDashboardModels,
  getDashboardSummary,
  getDashboardTrend,
  type DashboardSummary,
  type DashboardTrend,
  type HealthReport,
  type ModelBreakdown
} from '@/api/admin'
import LineChart from '@/components/charts/LineChart.vue'
import BarChart from '@/components/charts/BarChart.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import { dayOverDay, formatDayOverDay } from '@/utils/trendCompare'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(true)
const summary = ref<DashboardSummary | null>(null)
const trend = ref<DashboardTrend | null>(null)
const models = ref<ModelBreakdown | null>(null)
const health = ref<HealthReport | null>(null)
const days = ref(7)
const exporting = ref<'users' | 'tokens' | null>(null)

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return n.toLocaleString()
}

const cards = computed(() => {
  const s = summary.value
  if (!s) return []
  return [
    { label: '今日 Token 消耗', value: compact(s.today_tokens), sub: `${s.today_calls} 次调用`, tone: 'primary' },
    { label: '今日新增用户', value: compact(s.new_users_today), sub: `累计 ${s.total_users}` },
    { label: '今日活跃用户', value: compact(s.active_users_today), sub: '当日产生过会话' },
    { label: '累计会话', value: compact(s.total_conversations), sub: `行程 ${s.total_itineraries}` }
  ]
})

const costText = computed(() => {
  const c = summary.value?.today_cost
  if (!c) return '—'
  const unpriced = c.unpriced_models.length ? `（${c.unpriced_models.length} 个模型未配单价）` : ''
  return `$${c.estimated_usd.toFixed(4)}${unpriced}`
})

const tokenPoints = computed(
  () => trend.value?.tokens.map((t) => ({ label: t.date, value: t.total_tokens })) ?? []
)
const userPoints = computed(
  () => trend.value?.users.map((t) => ({ label: t.date, value: t.new_users })) ?? []
)

/**
 * 相对昨日的涨跌标注。
 *
 * 计算逻辑抽到 utils/trendCompare（纯函数，可单测）：
 * 取趋势序列最后两天比较，给出「涨跌数目 + 百分比」两段。
 * 口径为 (后−前)/前，即标准增幅 —— 详见该模块的说明。
 *
 * 这里只负责把结果接到图上。格式化成两段而不是一整句，
 * 是因为两段要用不同样式渲染（数目等宽、百分比带底色）。
 */
const tokenCompare = computed(() => {
  const c = dayOverDay(tokenPoints.value.map((p) => p.value))
  return c ? formatDayOverDay(c, compact) : null
})
const userCompare = computed(() => {
  const c = dayOverDay(userPoints.value.map((p) => p.value))
  return c ? formatDayOverDay(c, (n) => String(n)) : null
})

const modelBars = computed(() =>
  (models.value?.breakdown ?? []).map((m) => ({
    label: m.model,
    value: m.total_tokens,
    hint: m.share !== undefined ? `${(m.share * 100).toFixed(1)}%` : undefined
  }))
)

const healthItems = computed(() => {
  const h = health.value
  if (!h) return []
  return [
    { label: 'Redis', ok: h.redis_ok, detail: h.redis_detail },
    { label: '数据库', ok: h.database_ok, detail: h.database_detail },
    { label: '模型通道', ok: h.llm_channel_configured, detail: `${h.llm_model} · ${h.llm_detail}` }
  ]
})

/** 是否有检测未通过 */
const hasHealthIssue = computed(() => healthItems.value.some((h) => !h.ok))
/** 未通过项数，用于文案 */
const healthIssueCount = computed(() => healthItems.value.filter((h) => !h.ok).length)

const rechecking = ref(false)
const showLogHelp = ref(false)

/**
 * 只重新检测健康状态，不重拉整个看板。
 *
 * 为什么单独一个动作：健康检查是三项轻量探测，而整个看板要拉
 * 四项聚合统计（含 Token 汇总），重试成本高得多。管理员此时只想确认
 * 「服务是不是好了」，不该为此付出一整屏数据的加载时间。
 */
async function recheckHealth() {
  rechecking.value = true
  try {
    health.value = await getDashboardHealth()
    // 刷新后如果全好了，自动收起日志提示（问题已解决，留着是噪音）
    if (!hasHealthIssue.value) {
      showLogHelp.value = false
      ui.toast('各项检测均已通过', 'success')
    } else {
      ui.toast(`仍有 ${healthIssueCount.value} 项未通过`, 'error')
    }
  } catch (e: any) {
    ui.toast(e?.message ?? '健康检查失败', 'error')
  } finally {
    rechecking.value = false
  }
}

async function load() {
  loading.value = true
  try {
    // 并行拉取：四项之间无依赖，串行会让首屏明显更慢
    const [s, t, m, h] = await Promise.all([
      getDashboardSummary(),
      getDashboardTrend(days.value),
      getDashboardModels(),
      getDashboardHealth()
    ])
    summary.value = s
    trend.value = t
    models.value = m
    health.value = h
  } catch (e: any) {
    ui.toast(e?.message ?? '看板数据加载失败', 'error')
  } finally {
    loading.value = false
  }
}

async function switchDays(next: number) {
  days.value = next
  try {
    trend.value = await getDashboardTrend(next)
  } catch (e: any) {
    ui.toast(e?.message ?? '趋势加载失败', 'error')
  }
}

async function download(kind: 'users' | 'tokens') {
  exporting.value = kind
  try {
    if (kind === 'users') await exportUsersCsv()
    else await exportTokenUsageCsv()
    ui.toast('导出已开始下载', 'success')
  } catch (e: any) {
    ui.toast(e?.message ?? '导出失败', 'error')
  } finally {
    exporting.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="dash">
    <p v-if="loading" class="dash__loading">加载中…</p>

    <template v-else>
      <!-- 指标卡 -->
      <div class="dash__cards">
        <div v-for="c in cards" :key="c.label" class="statcard" :class="`statcard--${c.tone ?? 'plain'}`">
          <p class="statcard__label">{{ c.label }}</p>
          <p class="statcard__value">{{ c.value }}</p>
          <p class="statcard__sub">{{ c.sub }}</p>
        </div>
        <div class="statcard">
          <p class="statcard__label">今日成本估算</p>
          <p class="statcard__value statcard__value--sm">{{ costText }}</p>
          <p class="statcard__sub">按模型单价 × 用量估算</p>
        </div>
      </div>

      <!-- 趋势 -->
      <section class="card dash__panel">
        <header class="dash__panel-head">
          <h2>增长与消耗趋势</h2>
          <div class="dash__segments">
            <button
              v-for="d in [7, 14, 30]"
              :key="d"
              class="seg"
              :class="{ 'seg--on': days === d }"
              @click="switchDays(d)"
            >
              {{ d }} 天
            </button>
          </div>
        </header>
        <div class="dash__charts">
          <div>
            <p class="dash__chart-title">
              Token 消耗
              <!--
                相对昨日的涨跌：**两个各自带箭头的量** —— 前面是具体数目，
                后面是增减幅度。两个箭头各指自己的方向，不是「一个箭头管两个数」。
              -->
              <template v-if="tokenCompare">
                <span
                  v-if="tokenCompare.amount"
                  class="dash__cmp"
                  :class="`dash__cmp--${tokenCompare.tone}`"
                >{{ tokenCompare.amount }}</span>
                <span
                  v-if="tokenCompare.percent"
                  class="dash__cmp"
                  :class="`dash__cmp--${tokenCompare.tone}`"
                >{{ tokenCompare.percent }}</span>
              </template>
              <span class="dash__cmp-base">较昨日</span>
            </p>
            <LineChart :points="tokenPoints" unit="token" />
          </div>
          <div>
            <p class="dash__chart-title">
              新增用户
              <template v-if="userCompare">
                <span
                  v-if="userCompare.amount"
                  class="dash__cmp"
                  :class="`dash__cmp--${userCompare.tone}`"
                >{{ userCompare.amount }}</span>
                <span
                  v-if="userCompare.percent"
                  class="dash__cmp"
                  :class="`dash__cmp--${userCompare.tone}`"
                >{{ userCompare.percent }}</span>
              </template>
              <span class="dash__cmp-base">较昨日</span>
            </p>
            <LineChart :points="userPoints" unit="人" />
          </div>
        </div>
      </section>

      <div class="dash__two">
        <!-- 模型分布 -->
        <section class="card dash__panel">
          <header class="dash__panel-head">
            <h2>模型用量分布</h2>
            <span class="dash__scope">{{ models?.scope === 'all' ? '全部历史' : models?.scope }}</span>
          </header>
          <BarChart :items="modelBars" unit="token" />
          <p v-if="models?.cost.unpriced_models.length" class="dash__warn">
            以下模型未配置单价，未计入成本估算：{{ models.cost.unpriced_models.join('、') }}
          </p>
        </section>

        <!-- 系统健康 -->
        <section class="card dash__panel">
          <header class="dash__panel-head">
            <h2>系统健康</h2>
          </header>
          <ul class="health">
            <li v-for="h in healthItems" :key="h.label">
              <span class="health__dot" :class="h.ok ? 'is-ok' : 'is-bad'"></span>
              <span class="health__label">{{ h.label }}</span>
              <span class="health__detail">{{ h.detail }}</span>
            </li>
          </ul>

          <!--
            异常时的自助排查入口。
            原先只有一行说明文字，检测到 Redis/数据库/模型通道有问题时，
            管理员不知道下一步该做什么 —— 只能刷新页面碰运气，
            或者登服务器翻日志。这里给两个明确动作：
              · 重新检测：多数「瞬时故障」（连接抖动、容器刚重启）重试即恢复
              · 查看日志：真故障时给出可直接执行的命令，省掉查文档
          -->
          <div v-if="hasHealthIssue" class="health__actions">
            <p class="health__warn">
              有 {{ healthIssueCount }} 项检测未通过。多数瞬时故障重新检测即可恢复。
            </p>
            <div class="health__btns">
              <button
                class="btn btn-tint btn-tint-blue btn--sm"
                type="button"
                :disabled="rechecking"
                @click="recheckHealth"
              >
                <TravelIcon name="spark" :size="14" />
                {{ rechecking ? '检测中…' : '重新检测' }}
              </button>
              <button
                class="btn btn-ghost btn--sm"
                type="button"
                @click="showLogHelp = !showLogHelp"
              >
                {{ showLogHelp ? '收起' : '查看日志' }}
              </button>
            </div>

            <div v-if="showLogHelp" class="health__logs">
              <p>在服务器上执行对应命令查看详细原因：</p>
              <code>docker compose logs --tail=100 backend</code>
              <code>docker compose exec redis redis-cli ping</code>
              <code>docker compose exec postgres pg_isready -U voyage</code>
              <p class="health__logs-hint">
                Redis 不通时先看容器是否在跑；数据库不通多半是连接数或凭据问题；
                模型通道只是配置检查，报错说明 .env 里缺少对应的 Key。
              </p>
            </div>
          </div>

          <p class="dash__note">
            模型通道只校验配置完整性，不实际发起调用——避免看板本身消耗额度。
          </p>
        </section>
      </div>

      <!-- 导出 -->
      <section class="card dash__panel">
        <header class="dash__panel-head">
          <h2>数据导出</h2>
        </header>
        <div class="dash__actions">
          <button class="btn btn-ghost btn--sm" :disabled="exporting !== null" @click="download('users')">
            {{ exporting === 'users' ? '导出中…' : '导出用户列表 CSV' }}
          </button>
          <button class="btn btn-ghost btn--sm" :disabled="exporting !== null" @click="download('tokens')">
            {{ exporting === 'tokens' ? '导出中…' : '导出 Token 用量 CSV' }}
          </button>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.dash__loading { color: var(--text2); padding: 40px 0; text-align: center; }

.dash__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.statcard {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  padding: 16px 18px;
  box-shadow: var(--shadow-sm);
}
.statcard--primary { background: var(--grad-soft); border-color: transparent; }
.statcard__label { font-size: 0.78rem; color: var(--text2); margin-bottom: 6px; }
.statcard__value {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.statcard__value--sm { font-size: 1.05rem; }
.statcard__sub { margin-top: 4px; font-size: 0.74rem; color: var(--text3); }

.dash__panel { padding: 20px 22px; margin-bottom: 20px; }
.dash__panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.dash__panel-head h2 { font-size: 0.98rem; font-weight: 700; }
.dash__scope { font-size: 0.75rem; color: var(--text3); font-family: var(--mono); }

.dash__segments { display: flex; gap: 4px; }
.seg {
  padding: 5px 11px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel);
  font-size: 0.78rem;
  color: var(--text2);
}
.seg--on { background: var(--primary-soft); color: var(--prim); border-color: transparent; font-weight: 650; }

.dash__charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 22px;
}
.dash__chart-title { font-size: 0.8rem; color: var(--text2); margin-bottom: 6px; }

.dash__two {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}

.dash__warn {
  margin-top: 14px;
  font-size: 0.76rem;
  color: var(--warn);
  line-height: 1.5;
}
.dash__note { margin-top: 14px; font-size: 0.75rem; color: var(--text3); line-height: 1.5; }

.health { display: flex; flex-direction: column; gap: 12px; }
.health li { display: grid; grid-template-columns: 10px 68px 1fr; align-items: baseline; gap: 10px; }
.health__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text3); }
.health__dot.is-ok { background: var(--success); box-shadow: 0 0 0 3px rgba(72, 187, 120, 0.16); }
.health__dot.is-bad { background: var(--danger); box-shadow: 0 0 0 3px rgba(224, 82, 82, 0.16); }
.health__label { font-size: 0.84rem; font-weight: 600; }
.health__detail { font-size: 0.76rem; color: var(--text3); font-family: var(--mono); word-break: break-all; }

/* ---- 健康异常时的自助排查 ---- */
.health__actions {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--hairline);
}
.health__warn { font-size: 0.78rem; color: var(--danger); line-height: 1.6; }
.health__btns { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }

.health__logs {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--r-s);
  background: var(--surface-soft);
  font-size: 0.76rem;
  color: var(--text2);
  line-height: 1.7;
}
.health__logs code {
  display: block;
  margin-top: 6px;
  padding: 7px 10px;
  border-radius: 7px;
  background: var(--panel);
  border: 1px solid var(--border);
  font-family: var(--mono);
  font-size: 0.74rem;
  color: var(--text);
  /* 命令在窄屏可能超宽，允许横向滚动而不是撑破卡片 */
  overflow-x: auto;
  white-space: nowrap;
}
.health__logs-hint { margin-top: 10px; color: var(--text3); font-size: 0.74rem; }

/* ---- 趋势图的「较昨日」涨跌标记 ----
   两个**各自带箭头**的独立标签片：前面是具体数目，后面是增减幅度。
   每个片子自己带底色与箭头，方向由内容自明 —— 不用「一个箭头管两个数」，
   那样在数目与百分比方向需要区分时会含糊。
   数目用等宽数字：两个图上下并排时便于对齐比较。 */
.dash__cmp {
  display: inline-flex;
  align-items: baseline;
  margin-left: 6px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 0.74rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.dash__cmp--up { background: rgba(72, 187, 120, 0.14); color: var(--success); }
.dash__cmp--down { background: rgba(224, 82, 82, 0.12); color: var(--danger); }
.dash__cmp--flat { background: var(--surface-soft); color: var(--text3); font-weight: 600; }

/* 「较昨日」：说明对比基准，比标记更弱一档 */
.dash__cmp-base {
  margin-left: 8px;
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text3);
}

.dash__actions { display: flex; flex-wrap: wrap; gap: 10px; }
</style>
