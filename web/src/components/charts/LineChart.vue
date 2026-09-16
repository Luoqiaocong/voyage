<script setup lang="ts">
/**
 * 轻量折线图（纯 SVG，不引图表库）。
 *
 * 为什么手写：本项目只用到一种图（时间序列折线），为此引入 ECharts
 * 会增加约 1MB 依赖与一套额外的配置心智；而折线的几何计算本身很简单。
 * 样式全部走 CSS 变量，自动跟随明暗主题。
 */
import { computed } from 'vue'

let uid = 0

const props = withDefaults(
  defineProps<{
    /** 数据点；value 为纵轴值 */
    points: { label: string; value: number }[]
    /** 纵轴单位后缀，如「token」 */
    unit?: string
    /** 是否显示数据点圆点（点多时关掉更清爽） */
    dots?: boolean
    height?: number
  }>(),
  { unit: '', dots: true, height: 180 }
)

/** 渐变 id 必须全局唯一：同页多个图表若共用 id，会互相引用错误的渐变 */
const gradientId = `line-area-${++uid}`

const W = 640
const PAD = { top: 16, right: 12, bottom: 26, left: 44 }

const innerW = W - PAD.left - PAD.right
const innerH = computed(() => props.height - PAD.top - PAD.bottom)

const maxValue = computed(() => {
  const m = Math.max(...props.points.map((p) => p.value), 0)
  // 全 0 时给一个虚拟上界，避免除零与图形塌陷
  return m > 0 ? m : 1
})

/** 纵轴刻度：0 / 中值 / 最大值，用紧凑格式（1.2k / 3.4M） */
const yTicks = computed(() => {
  const m = maxValue.value
  return [0, m / 2, m].map((v) => ({ value: v, text: compact(v) }))
})

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(Math.round(n))
}

const coords = computed(() =>
  props.points.map((p, i) => {
    const x =
      props.points.length === 1
        ? PAD.left + innerW / 2
        : PAD.left + (i / (props.points.length - 1)) * innerW
    const y = PAD.top + innerH.value - (p.value / maxValue.value) * innerH.value
    return { x, y, ...p }
  })
)

const linePath = computed(() =>
  coords.value.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ')
)

/** 面积填充路径：折线闭合到基线，给折线一点体量感 */
const areaPath = computed(() => {
  if (!coords.value.length) return ''
  const baseY = PAD.top + innerH.value
  const first = coords.value[0]
  const last = coords.value[coords.value.length - 1]
  return `${linePath.value} L${last.x.toFixed(1)},${baseY} L${first.x.toFixed(1)},${baseY} Z`
})

/** 横轴标签抽稀：点太多时只保留首、中、尾，避免文字重叠 */
const xLabels = computed(() => {
  const n = coords.value.length
  if (n === 0) return []
  if (n <= 7) return coords.value.map((c) => ({ x: c.x, text: shortLabel(c.label) }))
  const idx = [0, Math.floor((n - 1) / 2), n - 1]
  return idx.map((i) => ({ x: coords.value[i].x, text: shortLabel(coords.value[i].label) }))
})

/** 日期 yyyy-MM-dd → MM-DD；非日期原样返回 */
function shortLabel(label: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})$/.exec(label)
  return m ? `${m[1]}-${m[2]}` : label
}

const hasData = computed(() => props.points.some((p) => p.value > 0))
</script>

<template>
  <div class="chart">
    <svg :viewBox="`0 0 ${W} ${height}`" role="img" :aria-label="`趋势图，单位 ${unit}`">
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--blue-500)" stop-opacity="0.28" />
          <stop offset="100%" stop-color="var(--blue-500)" stop-opacity="0.02" />
        </linearGradient>
      </defs>

      <!-- 横向网格与纵轴刻度 -->
      <g class="chart__grid">
        <template v-for="t in yTicks" :key="t.value">
          <line
            :x1="PAD.left"
            :x2="W - PAD.right"
            :y1="PAD.top + innerH - (t.value / maxValue) * innerH"
            :y2="PAD.top + innerH - (t.value / maxValue) * innerH"
          />
          <text
            :x="PAD.left - 8"
            :y="PAD.top + innerH - (t.value / maxValue) * innerH + 4"
            text-anchor="end"
          >
            {{ t.text }}
          </text>
        </template>
      </g>

      <template v-if="hasData">
        <path :d="areaPath" :fill="`url(#${gradientId})`" stroke="none" />
        <path class="chart__line" :d="linePath" fill="none" />
        <template v-if="dots">
          <circle v-for="(c, i) in coords" :key="i" class="chart__dot" :cx="c.x" :cy="c.y" r="3">
            <title>{{ c.label }}：{{ c.value.toLocaleString() }} {{ unit }}</title>
          </circle>
        </template>
      </template>

      <!-- 横轴标签 -->
      <g class="chart__x">
        <text v-for="(l, i) in xLabels" :key="i" :x="l.x" :y="height - 8" text-anchor="middle">
          {{ l.text }}
        </text>
      </g>
    </svg>

    <p v-if="!hasData" class="chart__empty">暂无数据</p>
  </div>
</template>

<style scoped>
.chart { position: relative; width: 100%; }
.chart svg { width: 100%; height: auto; display: block; overflow: visible; }

.chart__grid line { stroke: var(--hairline); stroke-width: 1; }
.chart__grid text { fill: var(--text3); font-size: 11px; font-family: var(--mono); }

.chart__line {
  stroke: var(--blue-500);
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.chart__dot { fill: var(--panel); stroke: var(--blue-500); stroke-width: 2; }

.chart__x text { fill: var(--text3); font-size: 11px; font-family: var(--mono); }

.chart__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--text3);
  font-size: 0.85rem;
  pointer-events: none;
}
</style>
