<script setup lang="ts">
/**
 * 横向条形图（纯 SVG，不引图表库）。
 *
 * 用途：展示各模型的用量占比。选横向条而非饼图，是因为模型名较长，
 * 横向排列能直接放下完整名称，也不需要处理饼图的标签避让。
 */
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    items: { label: string; value: number; hint?: string }[]
    /** 数值单位后缀 */
    unit?: string
  }>(),
  { unit: '' }
)

const maxValue = computed(() => Math.max(...props.items.map((i) => i.value), 0) || 1)

const rows = computed(() =>
  props.items.map((item) => ({
    ...item,
    /** 相对最大值算宽度，而不是相对总和：占比很小的项也能看见 */
    percent: Math.max((item.value / maxValue.value) * 100, item.value > 0 ? 2 : 0)
  }))
)

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}
</script>

<template>
  <div class="bars">
    <div v-for="row in rows" :key="row.label" class="bars__row">
      <div class="bars__head">
        <span class="bars__label" :title="row.label">{{ row.label }}</span>
        <span class="bars__value">
          {{ compact(row.value) }}<em v-if="unit"> {{ unit }}</em>
          <span v-if="row.hint" class="bars__hint">{{ row.hint }}</span>
        </span>
      </div>
      <div class="bars__track">
        <div class="bars__fill" :style="{ width: `${row.percent}%` }"></div>
      </div>
    </div>
    <p v-if="!items.length" class="bars__empty">暂无数据</p>
  </div>
</template>

<style scoped>
.bars { display: flex; flex-direction: column; gap: 14px; }

.bars__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 6px;
}
.bars__label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bars__value {
  font-family: var(--mono);
  font-size: 0.82rem;
  color: var(--text2);
  flex-shrink: 0;
}
.bars__value em { font-style: normal; color: var(--text3); font-size: 0.75rem; }
.bars__hint { color: var(--text3); margin-left: 8px; font-size: 0.75rem; }

.bars__track {
  height: 8px;
  border-radius: 999px;
  background: var(--surface-soft);
  overflow: hidden;
}
.bars__fill {
  height: 100%;
  border-radius: 999px;
  background: var(--grad);
  transition: width 0.5s cubic-bezier(0.2, 0.8, 0.3, 1);
}

.bars__empty {
  color: var(--text3);
  font-size: 0.85rem;
  text-align: center;
  padding: 24px 0;
}
</style>
