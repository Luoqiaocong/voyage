<script setup lang="ts">
/**
 * 行程分享管理面板。
 *
 * 展示某个行程已有的全部分享链接，并支持新建、改设置、撤销。
 * 密码明文由后端一并返回，便于分享者再次查看自己设的密码；
 * 界面上默认打码，点「显示」才展开，避免旁人一眼看到。
 */
import { onMounted, ref } from 'vue'
import {
  createShare,
  listShares,
  revokeShare,
  shareStatusLabel,
  updateShare,
  type ShareItem
} from '@/api/share'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ itineraryId: number }>()

const ui = useUiStore()

const loading = ref(true)
const shares = ref<ShareItem[]>([])
const creating = ref(false)
const busyId = ref<number | null>(null)

/** 新建表单 */
const form = ref({
  allow_copy: true,
  allow_edit: false,
  password: '',
  expires_in_days: 7 as number | null
})

/** 哪些分享的密码处于「显示」状态 */
const revealed = ref<Set<number>>(new Set())

const EXPIRY_OPTIONS = [
  { value: 1, label: '1 天' },
  { value: 7, label: '7 天' },
  { value: 30, label: '30 天' },
  { value: null, label: '永不过期' }
]

async function load() {
  loading.value = true
  try {
    shares.value = await listShares(props.itineraryId)
  } catch (e: any) {
    ui.toast(e?.message ?? '分享列表加载失败', 'error')
  } finally {
    loading.value = false
  }
}

async function create() {
  creating.value = true
  try {
    await createShare(props.itineraryId, {
      allow_copy: form.value.allow_copy,
      allow_edit: form.value.allow_edit,
      password: form.value.password.trim() || null,
      expires_in_days: form.value.expires_in_days
    })
    // 重置密码输入：链接已生成，留着明文输入框没有意义
    form.value.password = ''
    ui.toast('分享链接已创建', 'success')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '创建分享失败', 'error')
  } finally {
    creating.value = false
  }
}

async function copyLink(item: ShareItem) {
  try {
    await navigator.clipboard.writeText(item.url)
    ui.toast('链接已复制', 'success')
  } catch {
    // 非 HTTPS 或未授权时 clipboard 不可用，退回手动选择
    ui.toast('复制失败，请手动选择链接文本', 'error')
  }
}

async function toggleCopy(item: ShareItem) {
  busyId.value = item.id
  try {
    await updateShare(item.id, {
      allow_copy: !item.allow_copy,
      allow_edit: item.allow_edit
    })
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '修改失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function toggleEdit(item: ShareItem) {
  if (!item.allow_edit) {
    const ok = await ui.confirm(
      '开启「可编辑」后，拿到链接的人可以直接修改这份行程。确认开启？'
    )
    if (!ok) return
  }
  busyId.value = item.id
  try {
    await updateShare(item.id, {
      allow_copy: item.allow_copy,
      allow_edit: !item.allow_edit
    })
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '修改失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function revoke(item: ShareItem) {
  const ok = await ui.confirm('撤销后该链接立即失效，且无法恢复。确认撤销？')
  if (!ok) return
  busyId.value = item.id
  try {
    await revokeShare(item.id)
    ui.toast('已撤销', 'success')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '撤销失败', 'error')
  } finally {
    busyId.value = null
  }
}

function toggleReveal(id: number) {
  const next = new Set(revealed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  revealed.value = next
}

onMounted(load)
defineExpose({ reload: load })
</script>

<template>
  <section class="card sharepanel">
    <header class="sharepanel__head">
      <h2>分享这份行程</h2>
      <span class="sharepanel__hint">把链接发给同行的人，可设权限、密码与有效期</span>
    </header>

    <!-- 新建 -->
    <div class="creator">
      <label class="creator__opt">
        <input v-model="form.allow_copy" type="checkbox" />
        <span>允许复制到对方账号</span>
      </label>
      <label class="creator__opt">
        <input v-model="form.allow_edit" type="checkbox" />
        <span>允许直接编辑（谨慎开启）</span>
      </label>
      <label class="creator__opt creator__opt--field">
        <span>密码</span>
        <input
          v-model="form.password"
          class="input input--sm"
          type="text"
          placeholder="留空则无需密码"
          maxlength="32"
        />
      </label>
      <label class="creator__opt creator__opt--field">
        <span>有效期</span>
        <select v-model="form.expires_in_days" class="select input--sm">
          <option v-for="o in EXPIRY_OPTIONS" :key="String(o.value)" :value="o.value">
            {{ o.label }}
          </option>
        </select>
      </label>
      <button class="btn btn-primary btn--sm" :disabled="creating" @click="create">
        {{ creating ? '创建中…' : '创建分享链接' }}
      </button>
    </div>

    <!-- 列表 -->
    <p v-if="loading" class="sharepanel__empty">加载中…</p>
    <p v-else-if="!shares.length" class="sharepanel__empty">还没有分享链接</p>
    <ul v-else class="shares">
      <li v-for="s in shares" :key="s.id" class="shares__item" :class="{ 'is-dead': s.status !== 'active' }">
        <div class="shares__row">
          <span class="shares__status" :class="`shares__status--${shareStatusLabel(s.status).tone}`">
            {{ shareStatusLabel(s.status).text }}
          </span>
          <input class="shares__url" :value="s.url" readonly @focus="($event.target as HTMLInputElement).select()" />
          <button class="btn btn-ghost btn--sm" @click="copyLink(s)">复制</button>
        </div>

        <div class="shares__meta">
          <span>访问 {{ s.view_count }} 次</span>
          <span v-if="s.expires_at">有效期至 {{ s.expires_at }}</span>
          <span v-else>永不过期</span>
          <span v-if="s.has_password" class="shares__pwd">
            密码：{{ revealed.has(s.id) ? s.password : '••••••' }}
            <button class="btn btn-link btn--xs" @click="toggleReveal(s.id)">
              {{ revealed.has(s.id) ? '隐藏' : '显示' }}
            </button>
          </span>
          <span v-else>无密码</span>
        </div>

        <div class="shares__ops">
          <button class="btn btn-link btn--xs" :disabled="busyId === s.id" @click="toggleCopy(s)">
            {{ s.allow_copy ? '禁止复制' : '允许复制' }}
          </button>
          <button class="btn btn-link btn--xs" :disabled="busyId === s.id" @click="toggleEdit(s)">
            {{ s.allow_edit ? '关闭编辑' : '允许编辑' }}
          </button>
          <button
            v-if="s.status === 'active'"
            class="btn btn-link btn--xs is-danger"
            :disabled="busyId === s.id"
            @click="revoke(s)"
          >
            撤销
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.sharepanel { padding: 20px 22px; margin-bottom: 20px; }
.sharepanel__head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin-bottom: 16px; }
.sharepanel__head h2 { font-size: 0.98rem; font-weight: 700; }
.sharepanel__hint { font-size: 0.75rem; color: var(--text3); }

.creator {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 18px;
  padding: 14px 16px;
  border-radius: var(--r-s);
  background: var(--surface-soft);
  margin-bottom: 16px;
}
.creator__opt { display: inline-flex; align-items: center; gap: 7px; font-size: 0.82rem; color: var(--text2); }
.creator__opt input[type='checkbox'] { width: 15px; height: 15px; accent-color: var(--prim); }
.creator__opt--field { gap: 8px; }
.creator__opt--field .input--sm { width: 130px; padding: 5px 9px; font-size: 0.8rem; }

.sharepanel__empty { font-size: 0.84rem; color: var(--text3); padding: 12px 0; }

.shares { display: flex; flex-direction: column; gap: 10px; }
.shares__item {
  border: 1px solid var(--border);
  border-radius: var(--r-s);
  padding: 12px 14px;
}
.shares__item.is-dead { opacity: 0.62; }

.shares__row { display: flex; align-items: center; gap: 10px; }
.shares__status {
  font-size: 0.72rem;
  font-weight: 650;
  padding: 2px 8px;
  border-radius: 5px;
  white-space: nowrap;
}
.shares__status--ok { background: rgba(72, 187, 120, 0.14); color: var(--success); }
.shares__status--warn { background: var(--gold-soft); color: var(--gold-600); }
.shares__status--muted { background: var(--surface-soft); color: var(--text3); }

.shares__url {
  flex: 1;
  min-width: 0;
  font-family: var(--mono);
  font-size: 0.76rem;
  padding: 6px 9px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: var(--panel2);
  color: var(--text2);
  text-overflow: ellipsis;
}

.shares__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-top: 9px;
  font-size: 0.75rem;
  color: var(--text3);
}
.shares__pwd { color: var(--text2); font-family: var(--mono); }

.shares__ops { display: flex; gap: 4px; margin-top: 8px; }
.btn--xs { font-size: 0.76rem; padding: 2px 6px; }
.btn--xs.is-danger { color: var(--danger); }

@media (max-width: 640px) {
  .shares__row { flex-wrap: wrap; }
  .shares__url { flex: 1 1 100%; order: 3; }
}
</style>
