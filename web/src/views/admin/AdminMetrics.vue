<script setup lang="ts">
/**
 * 运行指标（可观测性）。
 *
 * 这一页回答的是「优化到底有没有效」：调了提示词后结构校验通过率是否上升、
 * 接入缓存后命中率与工具延迟分位是否下降。没有这些数字，改动只能靠感觉。
 */
import { computed, onMounted, ref } from 'vue'
import { getMetrics, getMetricsTrend, type MetricsSnapshot, type MetricsTrendPoint } from '@/api/admin'
import LineChart from '@/components/charts/LineChart.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(true)
const snap = ref<MetricsSnapshot | null>(null)
const trend = ref<MetricsTrendPoint[]>([])
const days = ref(7)

function pct(v: number | undefined): string {
  if (v === undefined || v === null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

/** 分位标签 le_500 → ≤500ms；gt_10000 → >10000ms */
function latencyLabel(label: string | null | undefined): string {
  if (!label) return '—'
  if (label.startsWith('le_')) return `≤ ${label.slice(3)}ms`
  if (label.startsWith('gt_')) return `> ${label.slice(3)}ms`
  return label
}

const toolRows = computed(() => {
  const tools = snap.value?.tools ?? {}
  return Object.entries(tools).map(([name, m]) => ({
    name,
    calls: m.calls ?? 0,
    hitRate: m.cache_hit_rate ?? 0,
    errRate: m.error_rate ?? 0,
    p50: latencyLabel(m.p50),
    p95: latencyLabel(m.p95),
    avg: m.avg_ms !== undefined ? `${m.avg_ms} ms` : '—'
  }))
})

const ex = computed(() => snap.value?.extraction)
const chat = computed(() => snap.value?.chat)
const cache = computed(() => snap.value?.cache)

const trendPoints = computed(() => ({
  calls: trend.value.map((t) => ({ label: t.date, value: t.tool_calls })),
  cache: trend.value.map((t) => ({ label: t.date, value: Math.round(t.cache_hit_rate * 100) })),
  pass: trend.value.map((t) => ({ label: t.date, value: Math.round(t.extract_pass_rate * 100) }))
}))

async function load() {
  loading.value = true
  try {
    const [s, t] = await Promise.all([getMetrics(), getMetricsTrend(days.value)])
    snap.value = s
    trend.value = t.trend
  } catch (e: any) {
    ui.toast(e?.message ?? '指标加载失败', 'error')
  } finally {
    loading.value = false
  }
}

async function switchDays(next: number) {
  days.value = next
  try {
    trend.value = (await getMetricsTrend(next)).trend
  } catch (e: any) {
    ui.toast(e?.message ?? '趋势加载失败', 'error')
  }
}

onMounted(load)
</script>

<template>
  <div class="metrics">
    <p v-if="loading" class="metrics__loading">加载中…</p>

    <template v-else-if="snap && !snap.available">
      <p class="empty">指标暂不可用（Redis 读取失败）。</p>
    </template>

    <template v-else-if="snap">
      <!-- 概览 -->
      <div class="metrics__cards">
        <div class="mcard">
          <p class="mcard__label">工具调用</p>
          <!--
            用后端的精确总计 tool.total.calls，而不是前端把明细行加起来。
            原先的写法有两个问题：
              · tool.total.calls 曾被解析成一个名叫 total 的「工具」混进明细，
                相加时把它也算了一次，于是「总计 = 工具之和 + 总计」；
                数字看着对只是巧合（total 恰好等于工具之和），
                换一天数据就会虚高
              · 即便解析修好了，两套求和逻辑并存也容易再次漂移
          -->
          <p class="mcard__value">{{ snap.counters?.['tool.total.calls'] ?? 0 }}</p>
          <p class="mcard__sub">今日累计 · 含各层子 Agent 与 MCP 工具</p>
        </div>
        <div class="mcard">
          <p class="mcard__label">缓存命中率</p>
          <p class="mcard__value">{{ pct(cache?.hit_rate) }}</p>
          <p class="mcard__sub">{{ cache?.hit ?? 0 }} / {{ cache?.total ?? 0 }} 次</p>
        </div>
        <div class="mcard">
          <p class="mcard__label">结构校验通过率</p>
          <p class="mcard__value">{{ pct(ex?.pass_rate) }}</p>
          <p class="mcard__sub">{{ ex?.ok ?? 0 }} / {{ ex?.total ?? 0 }} 次提取</p>
        </div>
        <div class="mcard">
          <p class="mcard__label">对话错误率</p>
          <p class="mcard__value">{{ pct(chat?.error_rate) }}</p>
          <p class="mcard__sub">{{ chat?.errors ?? 0 }} / {{ chat?.total ?? 0 }} 次对话</p>
        </div>
      </div>

      <!-- 提取路径 -->
      <section class="card metrics__panel">
        <header class="metrics__head">
          <h2>结构化提取路径</h2>
          <span class="metrics__hint">反映模型通道对强制工具调用的支持情况</span>
        </header>
        <div class="paths">
          <div class="paths__item">
            <span class="paths__dot paths__dot--ok"></span>
            <span>工具调用路径</span>
            <strong>{{ ex?.via_tool_call ?? 0 }}</strong>
          </div>
          <div class="paths__item">
            <span class="paths__dot paths__dot--warn"></span>
            <span>提示词回退路径</span>
            <strong>{{ ex?.via_fallback ?? 0 }}</strong>
          </div>
          <div class="paths__item">
            <span class="paths__dot"></span>
            <span>工具路径占比</span>
            <strong>{{ pct(ex?.tool_call_ratio) }}</strong>
          </div>
        </div>
      </section>

      <!-- 工具明细 -->
      <section class="card metrics__panel">
        <header class="metrics__head">
          <h2>工具调用明细</h2>
        </header>
        <div class="table-wrap">
          <table class="table">
            <thead>
              <tr>
                <th>工具</th>
                <th>调用</th>
                <th>缓存命中率</th>
                <th>错误率</th>
                <th>P50</th>
                <th>P95</th>
                <th>均值</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in toolRows" :key="row.name">
                <td class="table__mono">{{ row.name }}</td>
                <td>{{ row.calls }}</td>
                <td>{{ pct(row.hitRate) }}</td>
                <td>{{ pct(row.errRate) }}</td>
                <td class="table__mono">{{ row.p50 }}</td>
                <td class="table__mono">{{ row.p95 }}</td>
                <td class="table__mono">{{ row.avg }}</td>
              </tr>
              <tr v-if="!toolRows.length">
                <td colspan="7" class="table__empty">今日暂无工具调用</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="metrics__note">
          延迟为近似分位：后端按固定桶计数（≤100ms / ≤500ms / ≤1s / ≤3s / ≤10s / &gt;10s），
          因此这里显示的是「落在哪个桶以内」，而非毫秒级精确值。
        </p>
      </section>

      <!-- 趋势 -->
      <section class="card metrics__panel">
        <header class="metrics__head">
          <h2>指标趋势</h2>
          <div class="metrics__segments">
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
        <div class="metrics__charts">
          <div>
            <p class="metrics__chart-title">工具调用次数</p>
            <LineChart :points="trendPoints.calls" unit="次" :dots="false" />
          </div>
          <div>
            <p class="metrics__chart-title">缓存命中率（%）</p>
            <LineChart :points="trendPoints.cache" unit="%" :dots="false" />
          </div>
          <div>
            <p class="metrics__chart-title">结构校验通过率（%）</p>
            <LineChart :points="trendPoints.pass" unit="%" :dots="false" />
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.metrics__loading { color: var(--text2); padding: 40px 0; text-align: center; }

.metrics__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.mcard {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  padding: 16px 18px;
  box-shadow: var(--shadow-sm);
}
.mcard__label { font-size: 0.78rem; color: var(--text2); margin-bottom: 6px; }
.mcard__value {
  font-family: var(--font-display);
  font-size: 1.45rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.mcard__sub { margin-top: 4px; font-size: 0.74rem; color: var(--text3); }

.metrics__panel { padding: 20px 22px; margin-bottom: 20px; }
.metrics__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.metrics__head h2 { font-size: 0.98rem; font-weight: 700; }
.metrics__hint { font-size: 0.75rem; color: var(--text3); }

.paths { display: flex; flex-wrap: wrap; gap: 24px; }
.paths__item { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; color: var(--text2); }
.paths__item strong { color: var(--text); font-family: var(--mono); }
.paths__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text3); }
.paths__dot--ok { background: var(--success); }
.paths__dot--warn { background: var(--warn); }

.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.84rem; }
.table th {
  text-align: left;
  font-weight: 600;
  color: var(--text3);
  font-size: 0.76rem;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.table td { padding: 10px; border-bottom: 1px solid var(--hairline); }
.table__mono { font-family: var(--mono); font-size: 0.8rem; }
.table__empty { text-align: center; color: var(--text3); padding: 28px 0; }

.metrics__note { margin-top: 12px; font-size: 0.74rem; color: var(--text3); line-height: 1.6; }

.metrics__segments { display: flex; gap: 4px; }
.seg {
  padding: 5px 11px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--panel);
  font-size: 0.78rem;
  color: var(--text2);
}
.seg--on { background: var(--primary-soft); color: var(--prim); border-color: transparent; font-weight: 650; }

.metrics__charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 22px;
}
.metrics__chart-title { font-size: 0.8rem; color: var(--text2); margin-bottom: 6px; }
</style>
