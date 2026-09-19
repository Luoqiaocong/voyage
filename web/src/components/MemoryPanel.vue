<script setup lang="ts">
/**
 * 「我的记忆」管理面板。
 *
 * 记忆是系统从对话中提炼的画像。这里给用户完整的控制权：
 * 查看、修正取值、停用（不再注入对话但保留）、删除、一键清空。
 *
 * 设计上刻意展示 confidence / hit_count / evidence：
 * 让用户能判断某条记忆是「自己明确说过的」还是「系统猜的」，
 * 从而决定要不要纠正——不透明的画像会让人不安。
 */
import { computed, onMounted, ref } from 'vue'
import {
  clearMemories,
  deleteMemory,
  listMemories,
  MEMORY_VALUE_OPTIONS,
  toggleMemory,
  updateMemoryValue,
  type MemoryItem,
  type MemoryStats
} from '@/api/memory'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(true)
const items = ref<MemoryItem[]>([])
const stats = ref<MemoryStats | null>(null)
const showInactive = ref(false)
const busyId = ref<number | null>(null)

/** 正在编辑取值的记忆 ID */
const editingId = ref<number | null>(null)
const draftValue = ref('')
const savingValue = ref(false)

const activeItems = computed(() => items.value.filter((m) => m.is_active))
const inactiveItems = computed(() => items.value.filter((m) => !m.is_active))

/** 该键是否受枚举约束：受约束的用下拉，否则用输入框 */
function optionsFor(key: string): string[] | null {
  return MEMORY_VALUE_OPTIONS[key] ?? null
}

function confidenceText(c: number): string {
  if (c >= 0.85) return '你说过的'
  if (c >= 0.6) return '较可信'
  return '系统推测'
}

function confidenceTone(c: number): string {
  if (c >= 0.85) return 'high'
  if (c >= 0.6) return 'mid'
  return 'low'
}

async function load() {
  loading.value = true
  try {
    const res = await listMemories(true) // 一次取回含停用项，前端自行分组
    items.value = res.memories
    stats.value = res.stats
  } catch (e: any) {
    ui.toast(e?.message ?? '记忆加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function startEdit(m: MemoryItem) {
  editingId.value = m.id
  draftValue.value = m.fact_value
}

function cancelEdit() {
  editingId.value = null
  draftValue.value = ''
}

async function saveValue(m: MemoryItem) {
  const next = draftValue.value.trim()
  if (!next || next === m.fact_value) {
    cancelEdit()
    return
  }
  savingValue.value = true
  try {
    await updateMemoryValue(m.id, next)
    ui.toast('已更新', 'success')
    cancelEdit()
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '更新失败', 'error')
  } finally {
    savingValue.value = false
  }
}

async function toggle(m: MemoryItem) {
  busyId.value = m.id
  try {
    await toggleMemory(m.id, !m.is_active)
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '操作失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function removeOne(m: MemoryItem) {
  const ok = await ui.confirm(`删除这条记忆「${m.fact_key_label}：${m.fact_value}」？`)
  if (!ok) return
  busyId.value = m.id
  try {
    await deleteMemory(m.id)
    ui.toast('已删除', 'success')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '删除失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function removeAll() {
  const ok = await ui.confirm(
    '清空全部记忆后，助手将不再记得你的偏好（不影响已有对话与行程）。确认清空？'
  )
  if (!ok) return
  try {
    const res = await clearMemories()
    ui.toast(`已清空 ${res.deleted} 条记忆`, 'success')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '清空失败', 'error')
  }
}

onMounted(load)
</script>

<template>
  <section class="card memory">
    <header class="memory__head">
      <div>
        <h2>我的记忆</h2>
        <p class="memory__hint">
          助手会从对话中记住你的偏好，并在之后的对话里参考它们
        </p>
      </div>
      <button v-if="activeItems.length" class="btn btn-ghost btn--sm" @click="removeAll">
        清空全部
      </button>
    </header>

    <p v-if="loading" class="memory__empty">加载中…</p>

    <template v-else-if="!items.length">
      <p class="memory__empty">
        还没有记忆。多聊几次旅行偏好（预算、节奏、饮食、去过的城市），助手就会慢慢记住。
      </p>
    </template>

    <template v-else>
      <p v-if="stats" class="memory__stats">
        共 {{ stats.total }} 条 · 生效 {{ stats.active }} 条<template v-if="stats.inactive"> · 已停用 {{ stats.inactive }} 条</template>
      </p>

      <!-- 生效中 -->
      <ul class="mems">
        <li v-for="m in activeItems" :key="m.id" class="mem">
          <div class="mem__main">
            <span class="mem__key">{{ m.fact_key_label }}</span>

            <!-- 编辑态 -->
            <template v-if="editingId === m.id">
              <select
                v-if="optionsFor(m.fact_key)"
                v-model="draftValue"
                class="select mem__input"
                :aria-label="`修改「${m.fact_key_label}」的取值`"
              >
                <option v-for="o in optionsFor(m.fact_key)!" :key="o" :value="o">{{ o }}</option>
              </select>
              <input
                v-else
                v-model="draftValue"
                class="input mem__input"
                maxlength="40"
                :aria-label="`修改「${m.fact_key_label}」的取值`"
              />
              <button class="btn btn-primary btn--xs" :disabled="savingValue" @click="saveValue(m)">
                保存
              </button>
              <button class="btn btn-ghost btn--xs" @click="cancelEdit">取消</button>
            </template>

            <!-- 展示态 -->
            <template v-else>
              <span class="mem__value">
                {{ m.fact_value }}
                <span v-if="m.previous_value" class="mem__prev" :title="`原为「${m.previous_value}」`">
                  ← {{ m.previous_value }}
                </span>
              </span>
            </template>
          </div>

          <div class="mem__meta">
            <span class="mem__conf" :class="`mem__conf--${confidenceTone(m.confidence)}`">
              {{ confidenceText(m.confidence) }}
            </span>
            <span v-if="m.hit_count > 1" class="mem__hit">提到过 {{ m.hit_count }} 次</span>
            <span v-if="m.evidence" class="mem__evi" :title="m.evidence">「{{ m.evidence }}」</span>
          </div>

          <div v-if="editingId !== m.id" class="mem__ops">
            <button class="btn btn-link btn--xs" @click="startEdit(m)">修正</button>
            <button class="btn btn-link btn--xs" :disabled="busyId === m.id" @click="toggle(m)">
              停用
            </button>
            <button
              class="btn btn-link btn--xs is-danger"
              :disabled="busyId === m.id"
              @click="removeOne(m)"
            >
              删除
            </button>
          </div>
        </li>
      </ul>

      <!-- 已停用（折叠） -->
      <template v-if="inactiveItems.length">
        <button class="memory__toggle" @click="showInactive = !showInactive">
          {{ showInactive ? '▾' : '▸' }} 已停用的记忆（{{ inactiveItems.length }}）
        </button>
        <ul v-if="showInactive" class="mems mems--off">
          <li v-for="m in inactiveItems" :key="m.id" class="mem">
            <div class="mem__main">
              <span class="mem__key">{{ m.fact_key_label }}</span>
              <span class="mem__value">{{ m.fact_value }}</span>
            </div>
            <div class="mem__ops">
              <button class="btn btn-link btn--xs" :disabled="busyId === m.id" @click="toggle(m)">
                重新启用
              </button>
              <button
                class="btn btn-link btn--xs is-danger"
                :disabled="busyId === m.id"
                @click="removeOne(m)"
              >
                删除
              </button>
            </div>
          </li>
        </ul>
        <p class="memory__note">停用的记忆不会再影响对话，但仍保留在这里，随时可以重新启用。</p>
      </template>
    </template>
  </section>
</template>

<style scoped>
.memory { padding: 20px 22px; }
.memory__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}
.memory__head h2 { font-size: 0.98rem; font-weight: 700; }
.memory__hint { font-size: 0.76rem; color: var(--text3); margin-top: 4px; line-height: 1.5; }

.memory__empty { font-size: 0.85rem; color: var(--text3); line-height: 1.7; padding: 10px 0; }
.memory__stats { font-size: 0.76rem; color: var(--text3); margin-bottom: 12px; }

.mems { display: flex; flex-direction: column; }
.mems--off { opacity: 0.75; }

.mem {
  padding: 12px 0;
  border-bottom: 1px dashed var(--hairline);
}
.mem:last-child { border-bottom: none; }

.mem__main { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; }
.mem__key {
  font-size: 0.76rem;
  font-weight: 650;
  padding: 2px 8px;
  border-radius: 5px;
  background: var(--primary-soft);
  color: var(--prim);
  white-space: nowrap;
}
.mem__value { font-size: 0.9rem; font-weight: 600; display: inline-flex; align-items: baseline; gap: 8px; }
.mem__prev {
  font-size: 0.76rem;
  font-weight: 400;
  color: var(--text3);
  text-decoration: line-through;
}
.mem__input { max-width: 180px; padding: 5px 9px; font-size: 0.82rem; }

.mem__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 6px;
  font-size: 0.73rem;
  color: var(--text3);
}
.mem__conf { font-weight: 600; }
.mem__conf--high { color: var(--success); }
.mem__conf--mid { color: var(--text2); }
.mem__conf--low { color: var(--warn); }
.mem__evi {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.mem__ops { display: flex; gap: 4px; margin-top: 6px; }
.btn--xs { font-size: 0.76rem; padding: 2px 6px; }
.btn--xs.is-danger { color: var(--danger); }

.memory__toggle {
  margin-top: 12px;
  border: none;
  background: transparent;
  font-size: 0.8rem;
  color: var(--text2);
  padding: 4px 0;
}
.memory__toggle:hover { color: var(--prim); }
.memory__note { margin-top: 8px; font-size: 0.74rem; color: var(--text3); line-height: 1.6; }
</style>
