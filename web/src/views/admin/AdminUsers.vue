<script setup lang="ts">
/**
 * 用户管理：分页 + 关键词搜索 + 角色/状态筛选 + 改角色 + 启用禁用。
 *
 * 权限分两级（与后端一致）：
 *   super_admin  可改角色、可启停用
 *   admin        只读，页面上不渲染任何操作按钮
 * 后端仍会独立校验（写接口走 get_current_super_admin），前端隐藏只是
 * 避免「点了才被拒」的差体验，不是安全边界。
 *
 * 关于自我保护：后端会拒绝「停用自己」「操作同级或更高级」「降级最后一个
 * 超管」，前端把这些提示原样透出即可，不重复实现规则。
 */
import { computed, onMounted, ref, watch } from 'vue'
import {
  getAdminMe,
  getUserDetail,
  listUsers,
  updateUserRole,
  updateUserStatus,
  type AdminMe,
  type AdminRole,
  type AdminUserDetail,
  type AdminUserItem
} from '@/api/admin'
import { useUiStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'
import { roleLabel } from '@/utils/role'

const ui = useUiStore()
const me = useUserStore()

const loading = ref(false)
const items = ref<AdminUserItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const roleFilter = ref<'' | 'user' | 'admin' | 'super_admin'>('')
const activeFilter = ref<'all' | 'active' | 'inactive'>('all')

const detail = ref<AdminUserDetail | null>(null)
const detailLoading = ref(false)
const busyId = ref<number | null>(null)

/** 当前管理员的身份与写权限，由 /admin/me 返回（以后端为准，不在前端推断） */
const adminMe = ref<AdminMe | null>(null)
const canWrite = computed(() => adminMe.value?.can_write === true)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

/** 当前登录者是否就是这一行（用于禁用「停用自己」按钮并给出原因） */
function isSelf(u: AdminUserItem): boolean {
  return me.userInfo?.email === u.email
}

/**
 * 角色 → 样式类。文案取 utils/role.ts 的共享定义，不在这里再维护一份 ——
 * 角色名称写两处，新增角色时必然漏改其中一处。
 */
const ROLE_CLS: Record<string, string> = {
  super_admin: 'tag--super',
  admin: 'tag--admin',
  user: 'tag--user'
}
function roleMeta(role: string) {
  return { label: roleLabel(role), cls: ROLE_CLS[role] ?? 'tag--user' }
}

async function load() {
  loading.value = true
  try {
    const res = await listUsers({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value.trim() || undefined,
      role: roleFilter.value || undefined,
      is_active:
        activeFilter.value === 'all' ? undefined : activeFilter.value === 'active'
    })
    items.value = res.items
    total.value = res.total
  } catch (e: any) {
    ui.toast(e?.message ?? '用户列表加载失败', 'error')
  } finally {
    loading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(keyword, () => {
  // 输入防抖：每敲一个字就请求一次会给后端带来无谓压力
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    load()
  }, 320)
})

watch([roleFilter, activeFilter], () => {
  page.value = 1
  load()
})

watch(page, load)

function goto(next: number) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
}

/**
 * 改角色。三档循环：user -> admin -> super_admin -> user。
 *
 * 为什么不是「一键切换管理员/用户」：现在有三种角色，二值切换无法表达
 * 「普通管理员」这一档，必须给用户明确的选择。
 */
async function setRole(u: AdminUserItem, next: AdminRole) {
  const NAME: Record<string, string> = {
    user: '普通用户',
    admin: '普通管理员（只能查看数据，不能做任何操作）',
    super_admin: '超级管理员（可管理用户与其它管理员）'
  }
  const ok = await ui.confirm(`将「${u.email}」设为${NAME[next] ?? next}？`)
  if (!ok) return
  busyId.value = u.id
  try {
    const res = await updateUserRole(u.id, next)
    // changed=false 表示后端认为无需变更（例如已是该角色），据实提示而不是谎报成功
    ui.toast(res.changed ? '角色已更新' : '角色未变化', res.changed ? 'success' : 'info')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '修改角色失败', 'error')
  } finally {
    busyId.value = null
  }
}

/**
 * 该行是否可被当前管理员操作。
 *
 * 与后端 can_manage_role 同一套规则：**只能操作层级严格低于自己的账号**，
 * 且不能操作自己。在前端复刻一份是为了让按钮置灰并给出原因，
 * 而不是让用户点了才收到「权限不足」。
 */
const RANK: Record<string, number> = { user: 0, admin: 1, super_admin: 2 }

/** 当前管理员的层级；未加载时为 0（视为无权限，默认拒绝） */
const myRank = computed(() => RANK[adminMe.value?.role ?? ''] ?? 0)

function canOperate(u: AdminUserItem): boolean {
  if (!canWrite.value) return false
  if (isSelf(u)) return false
  const targetRank = RANK[u.role]
  if (targetRank === undefined) return false
  return myRank.value > targetRank
}

/** 不可操作的原因，作为按钮的 title 与 disabled 提示 */
function whyCannot(u: AdminUserItem): string {
  if (!canWrite.value) return '当前账号只有查看权限'
  if (isSelf(u)) return '不能操作自己的账号'
  const targetRank = RANK[u.role] ?? -1
  if (targetRank >= myRank.value) return '不能操作与自己同级或级别更高的账号'
  return ''
}

async function toggleStatus(u: AdminUserItem) {
  const next = !u.is_active
  const ok = await ui.confirm(
    next ? `启用「${u.email}」？` : `禁用「${u.email}」？该用户将无法登录，但数据保留。`
  )
  if (!ok) return
  busyId.value = u.id
  try {
    const res = await updateUserStatus(u.id, next)
    ui.toast(res.changed ? (next ? '已启用' : '已禁用') : '状态未变化', res.changed ? 'success' : 'info')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '修改状态失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function openDetail(u: AdminUserItem) {
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getUserDetail(u.id)
  } catch (e: any) {
    ui.toast(e?.message ?? '详情加载失败', 'error')
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  detail.value = null
}

onMounted(async () => {
  // 管理台入口依赖 role，进入本页前先确保用户信息已加载，否则「自己」判断会失效
  await me.fetchUserInfo(true)
  // 写权限以后端 /admin/me 为准，不在前端按角色名推断 ——
  // 这样将来后端调整权限规则，前端无需同步改动
  try {
    adminMe.value = await getAdminMe()
  } catch {
    adminMe.value = null // 拿不到就按只读处理（默认拒绝）
  }
  load()
})
</script>

<template>
  <div class="users">
    <!-- 工具栏 -->
    <div class="toolbar">
      <input v-model="keyword" class="input toolbar__search" type="search" placeholder="搜索邮箱或昵称…" />
      <select v-model="roleFilter" class="select toolbar__select">
        <option value="">全部角色</option>
        <option value="user">普通用户</option>
        <option value="admin">普通管理员</option>
        <option value="super_admin">超级管理员</option>
      </select>
      <select v-model="activeFilter" class="select toolbar__select">
        <option value="all">全部状态</option>
        <option value="active">已启用</option>
        <option value="inactive">已禁用</option>
      </select>
      <span class="toolbar__count">共 {{ total }} 人</span>
    </div>

    <!-- 列表 -->
    <div class="card users__panel">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <!-- 已去掉独立的 ID 列：它只占宽度、日常几乎不用。
                   需要 ID 时「详情」抽屉里仍有完整展示。 -->
              <th>邮箱</th>
              <th>昵称</th>
              <th>角色</th>
              <th>状态</th>
              <th>注册</th>
              <th class="table__ops">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in items" :key="u.id">
              <td class="table__email">
                <!-- 邮箱长度差异极大（实测最长 266px），故截断并保留完整值在 title 里，
                     避免个别长邮箱把整列撑开导致表格横向滚动。 -->
                <span class="email" :title="u.email">{{ u.email }}</span>
                <span v-if="isSelf(u)" class="tag tag--me">我</span>
              </td>
              <td>{{ u.username ?? '—' }}</td>
              <td>
                <span class="tag" :class="roleMeta(u.role).cls">
                  {{ roleMeta(u.role).label }}
                </span>
              </td>
              <td>
                <span class="tag" :class="u.is_active ? 'tag--ok' : 'tag--off'">
                  {{ u.is_active ? '启用' : '禁用' }}
                </span>
              </td>
              <td class="table__mono table__date" :title="u.created_at">
                {{ u.created_at?.slice(0, 10) }}
              </td>
              <td class="table__ops">
                <!-- 详情对所有管理员开放：它只展示统计数字，不含操作 -->
                <button class="btn btn-link btn--xs" @click="openDetail(u)">详情</button>

                <!--
                  写操作仅超管可见。普通管理员（只读）连按钮都不渲染，
                  而不是渲染后置灰 —— 后者会让人反复尝试。
                  即便前端漏了，后端写接口也有 get_current_super_admin 兜底。
                -->
                <template v-if="canWrite">
                  <button
                    v-if="canOperate(u)"
                    class="btn btn-link btn--xs"
                    :disabled="busyId === u.id"
                    @click="setRole(u, u.role === 'super_admin' ? 'user' : u.role === 'admin' ? 'super_admin' : 'admin')"
                  >
                    {{ u.role === 'user' ? '设为管理员' : u.role === 'admin' ? '升为超管' : '降为用户' }}
                  </button>
                  <!-- 同级或更高级：保留按钮但置灰，并说明原因 ——
                       直接隐藏会让管理员以为「功能没了」 -->
                  <button
                    v-else
                    class="btn btn-link btn--xs"
                    disabled
                    :title="whyCannot(u)"
                  >
                    改角色
                  </button>

                  <button
                    v-if="canOperate(u)"
                    class="btn btn-link btn--xs"
                    :class="{ 'is-danger': u.is_active }"
                    :disabled="busyId === u.id"
                    @click="toggleStatus(u)"
                  >
                    {{ u.is_active ? '禁用' : '启用' }}
                  </button>
                  <button
                    v-else
                    class="btn btn-link btn--xs"
                    disabled
                    :title="whyCannot(u)"
                  >
                    {{ u.is_active ? '禁用' : '启用' }}
                  </button>
                </template>
              </td>
            </tr>
            <tr v-if="!loading && !items.length">
              <td colspan="7" class="table__empty">没有符合条件的用户</td>
            </tr>
            <tr v-if="loading">
              <td colspan="7" class="table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页 -->
      <div class="pager">
        <button class="btn btn-ghost btn--sm" :disabled="page <= 1" @click="goto(page - 1)">上一页</button>
        <span class="pager__info">{{ page }} / {{ totalPages }}</span>
        <button class="btn btn-ghost btn--sm" :disabled="page >= totalPages" @click="goto(page + 1)">
          下一页
        </button>
      </div>
    </div>

    <!-- 详情抽屉 -->
    <div v-if="detailLoading || detail" class="drawer" @click.self="closeDetail">
      <div class="drawer__panel">
        <header class="drawer__head">
          <h3>用户详情</h3>
          <button class="drawer__close" aria-label="关闭" @click="closeDetail">×</button>
        </header>
        <p v-if="detailLoading" class="drawer__loading">加载中…</p>
        <dl v-else-if="detail" class="kv">
          <div><dt>ID</dt><dd class="table__mono">{{ detail.id }}</dd></div>
          <div><dt>邮箱</dt><dd>{{ detail.email }}</dd></div>
          <div><dt>昵称</dt><dd>{{ detail.username ?? '—' }}</dd></div>
          <div>
            <dt>角色</dt>
            <dd>{{ roleLabel(detail.role) }}</dd>
          </div>
          <div><dt>状态</dt><dd>{{ detail.is_active ? '已启用' : '已禁用' }}</dd></div>
          <div><dt>注册时间</dt><dd class="table__mono">{{ detail.created_at }}</dd></div>
          <div><dt>会话数</dt><dd>{{ detail.conversation_count }}</dd></div>
          <div><dt>行程数</dt><dd>{{ detail.itinerary_count }}</dd></div>
        </dl>
      </div>
    </div>
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
.toolbar__search { flex: 1 1 220px; min-width: 180px; }
.toolbar__select { flex: 0 0 130px; }
.toolbar__count { font-size: 0.8rem; color: var(--text3); margin-left: auto; }

.users__panel { padding: 0; overflow: hidden; }

/* 横向滚动仅作为兜底（例如窗口被拖得极窄），不再依赖它来显示完整表格。
   实测修复前表格最小宽 916px > 容器可用 888px，必然出滚动条。 */
.table-wrap { overflow-x: auto; }
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  /* fixed 让列宽由表格算法分配而不是由内容撑开，
     配合下面的列宽声明，长邮箱就不会把整列顶宽。 */
  table-layout: fixed;
}
.table th {
  text-align: left;
  font-weight: 600;
  color: var(--text3);
  font-size: 0.75rem;
  /* 内边距由 14px 收到 11px：6 列共省约 36px */
  padding: 12px 11px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  background: var(--panel2);
}
.table td { padding: 12px 11px; border-bottom: 1px solid var(--hairline); }

/* 列宽分配：把富余留给邮箱，其余按内容固定 */
.table th:nth-child(1), .table td:nth-child(1) { width: auto; }        /* 邮箱：占剩余 */
.table th:nth-child(2), .table td:nth-child(2) { width: 92px; }        /* 昵称 */
.table th:nth-child(3), .table td:nth-child(3) { width: 88px; }        /* 角色 */
.table th:nth-child(4), .table td:nth-child(4) { width: 76px; }        /* 状态 */
.table th:nth-child(5), .table td:nth-child(5) { width: 104px; }       /* 注册 */
.table th:nth-child(6), .table td:nth-child(6) { width: 186px; }       /* 操作 */

.table__mono { font-family: var(--mono); font-size: 0.8rem; }
.table__date { color: var(--text3); white-space: nowrap; }
.table__email { font-weight: 500; }
.table__ops { white-space: nowrap; text-align: right; }

/* 邮箱截断：否则单个超长邮箱（实测 266px）就能把表格撑出滚动条。
   完整值在 title 属性里，鼠标悬停可见。 */
.email {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
.table__empty { text-align: center; color: var(--text3); padding: 32px 0; }

.tag {
  display: inline-block;
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
  white-space: nowrap;
}
.tag--admin { background: rgba(56, 161, 105, 0.13); color: var(--green-600); }
.tag--user { background: var(--surface-soft); color: var(--text2); }
/* 超级管理员用主题蓝突出：它是唯一能改动数据的角色，
   与绿色的只读管理员在扫视时应能立刻区分 */
.tag--super { background: var(--primary-soft); color: var(--prim); font-weight: 700; }
.tag--ok { background: rgba(72, 187, 120, 0.14); color: var(--success); }
.tag--off { background: rgba(224, 82, 82, 0.13); color: var(--danger); }
.tag--me { background: var(--gold-soft); color: var(--gold-600); margin-left: 6px; }

.btn--xs { font-size: 0.78rem; padding: 2px 6px; }
.btn--xs.is-danger { color: var(--danger); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; text-decoration: none; }

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 14px;
  border-top: 1px solid var(--hairline);
}
.pager__info { font-size: 0.82rem; color: var(--text2); font-family: var(--mono); }

.drawer {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: rgba(15, 23, 42, 0.42);
  display: flex;
  justify-content: flex-end;
}
.drawer__panel {
  width: min(380px, 92vw);
  background: var(--panel);
  height: 100%;
  padding: 22px;
  overflow-y: auto;
  box-shadow: var(--shadow-lift);
}
.drawer__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.drawer__head h3 { font-size: 1rem; font-weight: 700; }
.drawer__close {
  border: none;
  background: transparent;
  font-size: 1.5rem;
  line-height: 1;
  color: var(--text3);
  padding: 0 4px;
}
.drawer__close:hover { color: var(--text); }
.drawer__loading { color: var(--text3); font-size: 0.85rem; }

.kv { display: flex; flex-direction: column; gap: 14px; }
.kv > div { display: flex; justify-content: space-between; gap: 16px; align-items: baseline; }
.kv dt { font-size: 0.8rem; color: var(--text3); flex-shrink: 0; }
.kv dd { font-size: 0.86rem; text-align: right; word-break: break-all; }
</style>
