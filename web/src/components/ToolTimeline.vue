<script setup lang="ts">
/**
 * 工具调用时间线：把一轮回答中的多次工具调用渲染成带状态的可视化步骤。
 * 状态：running（正在调用）/ done（已返回）/ error（失败）
 *
 * 只展示面向用户的中文名（label），不展示内部函数名——
 * get_today / weather_forecast_cached 这类标识是给开发看的，
 * 对用户没有任何意义，还会让界面像调试面板。
 */
import { computed } from 'vue'
import ToolIcon from './ToolIcon.vue'
import type { ToolStep } from '@/types/tool'

const props = defineProps<{ steps: ToolStep[]; collapsed?: boolean }>()

function fmtDuration(ms?: number): string {
  if (ms == null) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/**
 * 给重复出现的同一工具标注序号。
 *
 * 去掉内部函数名后，同一个工具被调用两次就会出现两个一模一样的
 * 「查询天气」条目，用户无法分辨，看起来像重复渲染的 bug。
 * 因此只在**确实重复**时补「· 第 N 次」，单次调用保持干净。
 */
const seqLabel = computed(() => {
  const total = new Map<string, number>()
  for (const s of props.steps) {
    total.set(s.name, (total.get(s.name) ?? 0) + 1)
  }
  const seen = new Map<string, number>()
  return props.steps.map((s) => {
    const n = (seen.get(s.name) ?? 0) + 1
    seen.set(s.name, n)
    return (total.get(s.name) ?? 0) > 1 ? `第 ${n} 次` : ''
  })
})
</script>

<template>
  <div v-if="steps.length" class="tools" :class="{ 'tools--collapsed': collapsed }">
    <div class="tools__head">
      <span class="tools__pulse" :class="{ 'is-idle': !steps.some((s) => s.status === 'running') }"></span>
      <span class="tools__label">
        {{ steps.some((s) => s.status === 'running') ? '正在调用工具' : '工具调用' }}
      </span>
      <span class="tools__count">{{ steps.length }}</span>
    </div>

    <ol class="tools__list">
      <li v-for="(s, i) in steps" :key="s.id" class="tstep" :class="`tstep--${s.status}`">
        <span class="tstep__rail" aria-hidden="true">
          <span class="tstep__dot"></span>
          <span v-if="i < steps.length - 1" class="tstep__line"></span>
        </span>

        <span class="tstep__icon"><ToolIcon :kind="s.icon" /></span>

        <span class="tstep__body">
          <span class="tstep__title">
            {{ s.label }}
            <span v-if="seqLabel[i]" class="tstep__seq">{{ seqLabel[i] }}</span>
          </span>
          <span v-if="s.result" class="tstep__result">{{ s.result }}</span>
          <span v-else-if="s.status === 'running'" class="tstep__shimmer" aria-label="调用中">
            <i></i><i></i><i></i>
          </span>
        </span>

        <span class="tstep__state">
          <span v-if="s.status === 'running'" class="tstep__spinner" aria-label="进行中"></span>
          <span v-else-if="s.status === 'error'" class="tstep__badge tstep__badge--err">失败</span>
          <template v-else>
            <svg class="tstep__ok" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
            <span v-if="s.duration != null" class="tstep__time">{{ fmtDuration(s.duration) }}</span>
          </template>
        </span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.tools {
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  background: var(--panel2);
  padding: 12px 14px 6px;
  max-width: min(660px, 94%);
  position: relative;
  overflow: hidden;
}

/* 左侧渐变竖条：一眼区分“这是工具调用” */
.tools::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--grad);
}

.tools__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--prim);
  margin-bottom: 10px;
}

.tools__pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--prim);
  box-shadow: 0 0 0 0 var(--glow);
  animation: tpulse 1.6s ease-out infinite;
}
.tools__pulse.is-idle { animation: none; }

@keyframes tpulse {
  0% { box-shadow: 0 0 0 0 var(--glow); }
  70% { box-shadow: 0 0 0 8px rgba(79, 130, 245, 0); }
  100% { box-shadow: 0 0 0 0 rgba(79, 130, 245, 0); }
}

.tools__count {
  margin-left: auto;
  font-size: 0.72rem;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--panel);
  border: 1px solid var(--border);
  color: var(--text3);
  letter-spacing: 0;
}

.tools__list { list-style: none; margin: 0; padding: 0; }

.tstep {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 7px 0;
  font-size: 0.85rem;
}

/* ---- 轨道 ---- */
.tstep__rail {
  position: relative;
  width: 10px;
  flex-shrink: 0;
  align-self: stretch;
  display: flex;
  justify-content: center;
  padding-top: 5px;
}
.tstep__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text3);
  opacity: 0.4;
  transition: 0.25s;
  z-index: 1;
}
.tstep__line {
  position: absolute;
  top: 15px;
  bottom: -7px;
  width: 1.5px;
  background: var(--border);
}
.tstep--running .tstep__dot { background: var(--prim); opacity: 1; animation: blink 1s ease-in-out infinite; }
.tstep--done .tstep__dot { background: var(--success); opacity: 1; }
.tstep--error .tstep__dot { background: var(--danger); opacity: 1; }

@keyframes blink { 50% { opacity: 0.3; } }

/* ---- 图标 ---- */
.tstep__icon {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  color: var(--text2);
  transition: 0.25s;
}
.tstep--running .tstep__icon {
  color: #fff;
  background: var(--grad);
  border-color: transparent;
  box-shadow: 0 4px 12px var(--glow);
}
.tstep--done .tstep__icon { color: var(--success); border-color: rgba(16, 185, 129, 0.3); }
.tstep--error .tstep__icon { color: var(--danger); border-color: rgba(229, 72, 77, 0.3); }

/* ---- 正文 ---- */
.tstep__body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }

.tstep__title {
  display: flex;
  align-items: baseline;
  gap: 7px;
  flex-wrap: wrap;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
}
.tstep--running .tstep__title { color: var(--prim); }

/* 重复调用时的序号标记：弱化处理，只是为了让两条同名步骤可区分 */
.tstep__seq {
  font-size: 0.68rem;
  color: var(--text3);
  background: var(--panel);
  border: 1px solid var(--border);
  padding: 0 6px;
  border-radius: 5px;
  font-weight: 400;
  margin-left: 2px;
}

.tstep__result {
  font-size: 0.78rem;
  color: var(--text2);
  line-height: 1.5;
  overflow-wrap: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tstep__shimmer { display: inline-flex; gap: 4px; padding: 2px 0; }
.tstep__shimmer i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--prim);
  opacity: 0.4;
  animation: bounce 1.1s ease-in-out infinite;
}
.tstep__shimmer i:nth-child(2) { animation-delay: 0.15s; }
.tstep__shimmer i:nth-child(3) { animation-delay: 0.3s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.35; }
  40% { transform: translateY(-4px); opacity: 1; }
}

/* ---- 状态 ---- */
.tstep__state {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  padding-top: 5px;
  min-height: 24px;
}

.tstep__spinner {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid var(--primary-soft);
  border-top-color: var(--prim);
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.tstep__ok { width: 14px; height: 14px; color: var(--success); }

.tstep__badge {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 999px;
}
.tstep__badge--err { background: rgba(229, 72, 77, 0.12); color: var(--danger); }

.tstep__time {
  font-family: var(--mono);
  font-size: 0.68rem;
  color: var(--text3);
}

.tools--collapsed .tools__list { display: none; }
</style>
