<script setup lang="ts">
/**
 * 审计日志：管理端写操作的留痕（谁、何时、对谁、改前改后）。
 *
 * detail 字段后端存的是 JSON 字符串，这里解析出来渲染成易读的「改前 → 改后」，
 * 解析失败则退回原文展示，避免因格式意外变化而丢信息。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { AUDIT_ACTION_LABEL, listAuditLogs, type AuditLogItem } from '@/api/admin'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(false)
const items = ref<AuditLogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const actionFilter = ref('')
const targetFilter = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const actionOptions = computed(() => Object.entries(AUDIT_ACTION_LABEL))

function actionText(action: string): string {
  return AUDIT_ACTION_LABEL[action] ?? action
}

/** 把 detail 的 JSON 解析成「改前 → 改后」；解析不了就原样返回 */
function detailText(raw: string | null): string {
  if (!raw) return '—'
  try {
    const obj = JSON.parse(raw) as Record<string, unknown>
    const before = obj.before
    const after = obj.after
    if (before === undefined && after === undefined) return raw
    return `${fmt(before)} → ${fmt(after)}`
  } catch {
    return raw
  }
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? '启用/是' : '禁用/否'
  return String(v)
}

async function load() {
  loading.value = true
  try {
    const res = await listAuditLogs({
      page: page.value,
      page_size: pageSize.value,
      action: actionFilter.value || undefined,
      target_id: targetFilter.value.trim() || undefined
    })
    items.value = res.items
    total.value = res.total
  } catch (e: any) {
    ui.toast(e?.message ?? '审计日志加载失败', 'error')
  } finally {
    loading.value = false
  }
}

watch(actionFilter, () => {
  page.value = 1
  load()
})

let targetTimer: ReturnType<typeof setTimeout> | null = null
watch(targetFilter, () => {
  if (targetTimer) clearTimeout(targetTimer)
  targetTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 320)
})

watch(page, load)

function goto(next: number) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
}

onMounted(load)
</script>

<template>
  <div class="audit">
    <div class="toolbar">
      <select v-model="actionFilter" class="select toolbar__select" aria-label="按操作类型筛选">
        <option value="">全部动作</option>
        <option v-for="[key, label] in actionOptions" :key="key" :value="key">{{ label }}</option>
      </select>
      <input
        v-model="targetFilter"
        class="input toolbar__search"
        type="search"
        placeholder="按目标用户 ID 筛选…"
        aria-label="按目标用户 ID 筛选审计日志"
      />
      <span class="toolbar__count">共 {{ total }} 条</span>
    </div>

    <div class="card audit__panel">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>时间</th>
              <th>操作者</th>
              <th>动作</th>
              <th>目标</th>
              <th>变更</th>
              <th>来源 IP</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in items" :key="log.id">
              <td class="table__mono table__date">{{ log.created_at }}</td>
              <td class="table__email">{{ log.operator_email }}</td>
              <td>
                <span class="tag">{{ actionText(log.action) }}</span>
              </td>
              <td class="table__mono">{{ log.target_type }}#{{ log.target_id }}</td>
              <td class="table__mono table__change">{{ detailText(log.detail) }}</td>
              <td class="table__mono table__date">{{ log.ip ?? '—' }}</td>
            </tr>
            <tr v-if="!loading && !items.length">
              <td colspan="6" class="table__empty">暂无审计记录</td>
            </tr>
            <tr v-if="loading">
              <td colspan="6" class="table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pager">
        <button class="btn btn-ghost btn--sm" :disabled="page <= 1" @click="goto(page - 1)">上一页</button>
        <span class="pager__info">{{ page }} / {{ totalPages }}</span>
        <button class="btn btn-ghost btn--sm" :disabled="page >= totalPages" @click="goto(page + 1)">
          下一页
        </button>
      </div>
    </div>

    <p class="audit__note">
      审计记录与业务变更写在同一事务中——「改了」与「留痕」要么都生效、要么都不生效，
      不会出现操作成功却没有记录的缺口。
    </p>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar__search { flex: 1 1 200px; min-width: 160px; }
.toolbar__select { flex: 0 0 160px; }
.toolbar__count { font-size: 0.8rem; color: var(--text3); margin-left: auto; }

.audit__panel { padding: 0; overflow: hidden; }

.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.table th {
  text-align: left;
  font-weight: 600;
  color: var(--text3);
  font-size: 0.75rem;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  background: var(--panel2);
}
.table td { padding: 12px 14px; border-bottom: 1px solid var(--hairline); }
.table__mono { font-family: var(--mono); font-size: 0.78rem; }
.table__date { color: var(--text3); white-space: nowrap; }
.table__email { color: var(--text2); }
.table__change { color: var(--prim); }
.table__empty { text-align: center; color: var(--text3); padding: 32px 0; }

.tag {
  display: inline-block;
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
  background: var(--surface-soft);
  color: var(--text2);
  white-space: nowrap;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 14px;
  border-top: 1px solid var(--hairline);
}
.pager__info { font-size: 0.82rem; color: var(--text2); font-family: var(--mono); }

.audit__note { margin-top: 14px; font-size: 0.75rem; color: var(--text3); line-height: 1.6; }
</style>
