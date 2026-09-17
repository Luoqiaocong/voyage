<script setup lang="ts">
/**
 * ProfileView · 个人主页
 *
 * 布局：信息头部（头像 + 昵称 + 旅行足迹）→ 两列卡片（基本资料 / 账号安全）
 *       → 通栏长期记忆
 *
 * 视觉：与首页、对话页统一为清爽浅色系 + 旅行蓝主色。
 * 「旅行足迹」的数据全部来自真实接口（行程数、会话数、记忆数），
 * 不使用编造的统计数字——个人主页上出现假数据最伤信任。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import MemoryPanel from '@/components/MemoryPanel.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import { AVATAR_BASE_URL } from '@/constants'
import { changePassword, deleteAccount, getAvatars, logout, updateProfile } from '@/api/user'
import { listItineraries } from '@/api/itinerary'
import { listConversations } from '@/api/conversation'
import { listMemories } from '@/api/memory'
import { useUiStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const ui = useUiStore()
const user = useUserStore()

const avatars = ref<string[]>([])
const username = ref('')
const avatar = ref('')
const savingProfile = ref(false)
/** 资料是否存在未保存的改动，用于按钮状态与离开提醒 */
const dirty = ref(false)

const pwdForm = reactive({ current: '', next: '', confirm: '' })
const savingPwd = ref(false)
const showPwd = ref(false)

/** 旅行足迹：各计数独立失败，不因某一个接口出错就让整块消失 */
const footprint = reactive({ itineraries: 0, conversations: 0, memories: 0 })
const loadingFootprint = ref(true)

onMounted(async () => {
  const info = await user.fetchUserInfo(true)
  if (info) {
    username.value = info.username ?? ''
    avatar.value = info.avatar ?? ''
  }
  dirty.value = false

  try {
    const lib = await getAvatars()
    avatars.value = lib.avatars
  } catch (e: any) {
    ui.toast(e?.message ?? '头像库加载失败', 'error')
  }

  // 三个计数并行拉取；各自 catch，避免一个失败拖垮整块
  const [its, convs, mems] = await Promise.allSettled([
    listItineraries(),
    listConversations(),
    listMemories(false)
  ])
  if (its.status === 'fulfilled') footprint.itineraries = its.value.length
  if (convs.status === 'fulfilled') footprint.conversations = convs.value.length
  if (mems.status === 'fulfilled') footprint.memories = mems.value.memories.length
  loadingFootprint.value = false
})

const avatarUrl = computed(() => (avatar.value ? AVATAR_BASE_URL + avatar.value : ''))
const displayName = computed(
  () => user.userInfo?.username || user.userInfo?.email?.split('@')[0] || '旅行者'
)
const initial = computed(() => displayName.value.slice(0, 1).toUpperCase())

/**
 * 密码强度评分（0–4）。
 *
 * 前端只做提示，真正校验在后端；这里不引入 zxcvbn 之类的库——
 * 一个几十行的启发式规则足以覆盖「太短 / 太单一 / 常见词」这三类主要问题。
 */
const pwdStrength = computed(() => {
  const v = pwdForm.next
  if (!v) return { score: 0, label: '', hint: '' }

  let score = 0
  if (v.length >= 8) score++
  if (v.length >= 12) score++
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(v)).length
  if (kinds >= 2) score++
  if (kinds >= 3) score++

  // 明显弱的模式直接压到最低档，避免「Aa123456」被评为很强
  if (/^(.)\1+$/.test(v) || /^(?:0123|1234|abcd|qwer|password|admin)/i.test(v)) {
    score = Math.min(score, 1)
  }

  const labels = ['太弱', '偏弱', '一般', '较强', '很强']
  const hints = [
    '至少 8 位，建议混合字母与数字',
    '再加长一些会更安全',
    '可以再加大小写或符号',
    '强度不错',
    '强度很好'
  ]
  const s = Math.min(score, 4)
  return { score: s, label: labels[s], hint: hints[s] }
})

/** 两次输入是否一致（只在确认框有内容时才提示，避免边打字边报错） */
const pwdMismatch = computed(
  () => pwdForm.confirm.length > 0 && pwdForm.next !== pwdForm.confirm
)
const canSubmitPwd = computed(
  () =>
    !savingPwd.value &&
    pwdForm.current.length > 0 &&
    pwdForm.next.length >= 8 &&
    pwdForm.next === pwdForm.confirm
)

function onProfileChange() {
  dirty.value = true
}

async function saveProfile() {
  if (!username.value.trim()) {
    ui.toast('昵称不能为空', 'error')
    return
  }
  savingProfile.value = true
  try {
    const patch: { username?: string; avatar?: string } = { username: username.value.trim() }
    if (avatar.value) patch.avatar = avatar.value
    const updated = await updateProfile(patch)
    user.$patch({ userInfo: updated })
    dirty.value = false
    ui.toast('资料已更新', 'success')
  } catch (e: any) {
    ui.toast(e?.message ?? '保存失败', 'error')
  } finally {
    savingProfile.value = false
  }
}

function resetProfile() {
  username.value = user.userInfo?.username ?? ''
  avatar.value = user.userInfo?.avatar ?? ''
  dirty.value = false
}

async function savePassword() {
  if (pwdForm.next.length < 8) {
    ui.toast('新密码至少 8 位', 'error')
    return
  }
  if (pwdForm.next !== pwdForm.confirm) {
    ui.toast('两次输入的新密码不一致', 'error')
    return
  }
  savingPwd.value = true
  try {
    await changePassword(pwdForm.current, pwdForm.next)
    ui.toast('密码已修改，请重新登录', 'success', 4500)
    user.clearAuth()
    router.replace('/login')
  } catch (e: any) {
    ui.toast(e?.message ?? '修改失败', 'error')
  } finally {
    savingPwd.value = false
  }
}

async function handleLogout() {
  const sure = await ui.confirm('确定退出登录吗？下次需要重新输入密码。')
  if (!sure) return
  try {
    if (user.refreshToken) await logout(user.refreshToken)
  } catch {
    /* 即使后端撤销失败也继续本地登出 */
  }
  user.clearAuth()
  ui.toast('已退出登录', 'success')
  router.replace('/login')
}

async function handleDeleteAccount() {
  const sure = await ui.confirm('确定永久注销账号吗？所有会话和行程将被删除，且无法恢复！')
  if (!sure) return
  try {
    await deleteAccount()
    user.clearAuth()
    ui.toast('账号已注销', 'success')
    router.replace('/')
  } catch (e: any) {
    ui.toast(e?.message ?? '注销失败', 'error')
  }
}

/** 快捷入口：都用真实路由，不做点了没反应的占位 */
const shortcuts = [
  { to: '/itineraries', icon: 'map', label: '我的行程', desc: '查看与编辑已保存的行程' },
  { to: '/chat', icon: 'chat', label: '继续对话', desc: '和旅行顾问接着聊' }
]
</script>

<template>
  <div class="pf-page">
    <AppNavbar />
    <main id="main" tabindex="-1">
      <div class="container page">
        <!-- ==================== 信息头部 ==================== -->
        <section class="pf-hero">
          <div class="pf-hero__avatar">
            <img v-if="avatarUrl" :src="avatarUrl" alt="当前头像" />
            <span v-else class="pf-hero__initial">{{ initial }}</span>
          </div>

          <div class="pf-hero__info">
            <h1 class="pf-hero__name">
              {{ displayName }}
              <span v-if="user.userInfo?.role === 'admin'" class="pf-hero__role">管理员</span>
            </h1>
            <p class="pf-hero__email">{{ user.userInfo?.email ?? '—' }}</p>

            <!-- 旅行足迹：全部来自真实接口 -->
            <div class="pf-fp" :class="{ 'is-loading': loadingFootprint }">
              <div class="pf-fp__item">
                <TravelIcon name="map" :size="15" />
                <b>{{ loadingFootprint ? '—' : footprint.itineraries }}</b>
                <span>份行程</span>
              </div>
              <div class="pf-fp__item">
                <TravelIcon name="chat" :size="15" />
                <b>{{ loadingFootprint ? '—' : footprint.conversations }}</b>
                <span>次对话</span>
              </div>
              <div class="pf-fp__item">
                <TravelIcon name="spark" :size="15" />
                <b>{{ loadingFootprint ? '—' : footprint.memories }}</b>
                <span>条偏好记忆</span>
              </div>
            </div>
          </div>

          <div class="pf-hero__nav">
            <RouterLink v-for="s in shortcuts" :key="s.to" :to="s.to" class="pf-shortcut">
              <TravelIcon :name="s.icon" :size="17" />
              <span class="pf-shortcut__body">
                <b>{{ s.label }}</b>
                <i>{{ s.desc }}</i>
              </span>
              <TravelIcon name="arrow-right" :size="14" />
            </RouterLink>
          </div>
        </section>

        <!-- ==================== 两列卡片 ==================== -->
        <div class="pf-grid">
          <!-- ---------- 基本资料 ---------- -->
          <section class="card pf-card">
            <header class="pf-card__head">
              <h2 class="pf-title">基本资料</h2>
              <span v-if="dirty" class="pf-dirty">未保存</span>
            </header>

            <div class="field">
              <label for="pf-username">昵称</label>
              <input
                id="pf-username"
                v-model="username"
                class="input"
                maxlength="10"
                placeholder="2-10 个字符"
                @input="onProfileChange"
              />
              <p class="pf-counter">{{ username.length }} / 10</p>
            </div>

            <div class="field">
              <label for="pf-email">邮箱</label>
              <input id="pf-email" class="input" :value="user.userInfo?.email ?? ''" disabled />
              <p class="pf-tip">邮箱作为账号标识，暂不支持修改</p>
            </div>

            <div v-if="avatars.length" class="field">
              <label>选择头像</label>
              <div class="pf-avatar-grid">
                <button
                  v-for="a in avatars"
                  :key="a"
                  class="pf-avatar-opt"
                  :class="{ 'pf-avatar-opt--active': a === avatar }"
                  :aria-label="'选择头像 ' + a"
                  type="button"
                  @click="avatar = a; onProfileChange()"
                >
                  <img :src="AVATAR_BASE_URL + a" :alt="a" loading="lazy" />
                  <span v-if="a === avatar" class="pf-avatar-opt__check" aria-hidden="true">
                    <TravelIcon name="check" :size="12" />
                  </span>
                </button>
              </div>
            </div>

            <div class="pf-actions">
              <button v-if="dirty" class="btn btn-ghost btn--sm" @click="resetProfile">撤销</button>
              <button
                class="btn btn-primary btn--block"
                :disabled="savingProfile || !dirty"
                @click="saveProfile"
              >
                {{ savingProfile ? '保存中…' : dirty ? '保存资料' : '已是最新' }}
              </button>
            </div>
          </section>

          <!-- ---------- 账号安全 ---------- -->
          <section class="card pf-card">
            <header class="pf-card__head">
              <h2 class="pf-title">账号安全</h2>
            </header>

            <div class="field">
              <label for="pwd-current">当前密码</label>
              <div class="pf-pwd">
                <input
                  id="pwd-current"
                  v-model="pwdForm.current"
                  class="input"
                  :type="showPwd ? 'text' : 'password'"
                  autocomplete="current-password"
                />
              </div>
            </div>

            <div class="field">
              <label for="pwd-next">新密码</label>
              <div class="pf-pwd">
                <input
                  id="pwd-next"
                  v-model="pwdForm.next"
                  class="input"
                  :type="showPwd ? 'text' : 'password'"
                  minlength="8"
                  autocomplete="new-password"
                  placeholder="至少 8 位"
                />
                <button
                  class="pf-pwd__eye"
                  type="button"
                  :aria-label="showPwd ? '隐藏密码' : '显示密码'"
                  @click="showPwd = !showPwd"
                >
                  <TravelIcon :name="showPwd ? 'eye-off' : 'eye'" :size="15" />
                </button>
              </div>

              <!-- 强度提示：只在开始输入后出现，避免空表单就被警告 -->
              <div v-if="pwdForm.next" class="pf-strength">
                <span class="pf-strength__bars">
                  <i
                    v-for="n in 4"
                    :key="n"
                    :class="[`lv-${pwdStrength.score}`, { on: n <= pwdStrength.score }]"
                  ></i>
                </span>
                <span class="pf-strength__text">{{ pwdStrength.label }} · {{ pwdStrength.hint }}</span>
              </div>
            </div>

            <div class="field">
              <label for="pwd-confirm">确认新密码</label>
              <input
                id="pwd-confirm"
                v-model="pwdForm.confirm"
                class="input"
                :class="{ 'input--bad': pwdMismatch }"
                :type="showPwd ? 'text' : 'password'"
                minlength="8"
                autocomplete="new-password"
              />
              <p v-if="pwdMismatch" class="pf-error">两次输入的新密码不一致</p>
            </div>

            <!-- 提示做得显眼但不吓人：用信息色而非警告色 -->
            <p class="pf-notice">
              <TravelIcon name="shield" :size="15" />
              修改密码后，所有设备都会退出登录，需要用新密码重新登录。
            </p>

            <button class="btn btn-ink btn--block" :disabled="!canSubmitPwd" @click="savePassword">
              {{ savingPwd ? '提交中…' : '修改密码' }}
            </button>

            <hr class="pf-hr" />

            <h3 class="pf-subtitle">会话与账号</h3>
            <button class="btn btn-ghost btn--block" @click="handleLogout">
              <TravelIcon name="key" :size="15" />
              退出登录
            </button>
            <p class="pf-tip pf-tip--center">退出后本地会清除登录凭证</p>
            <button class="btn btn-danger btn--block pf-danger" @click="handleDeleteAccount">
              注销账号
            </button>
            <p class="pf-tip pf-tip--center">注销将永久删除全部会话与行程，无法恢复</p>
          </section>
        </div>

        <!-- ==================== 长期记忆（通栏）==================== -->
        <div class="pf-memory">
          <MemoryPanel />
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* ==================== 信息头部 ==================== */
.pf-hero {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 26px;
  padding: 26px 28px;
  margin-bottom: 22px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  box-shadow: var(--shadow-sm);
  position: relative;
  overflow: hidden;
}
/* 右上角一层极淡的蓝晕，让头部区块不至于太平 */
.pf-hero::after {
  content: '';
  position: absolute;
  top: -80px;
  right: -60px;
  width: 260px;
  height: 200px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(37, 99, 235, 0.1), transparent 70%);
  pointer-events: none;
}

.pf-hero__avatar {
  position: relative;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  flex-shrink: 0;
  padding: 3px;
  background: var(--grad);
  box-shadow: 0 10px 26px var(--glow);
}
.pf-hero__avatar img,
.pf-hero__initial {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  display: grid;
  place-items: center;
  background: var(--panel);
  font-family: var(--font-display);
  font-size: 2.3rem;
  font-weight: 800;
  color: var(--prim);
}

.pf-hero__info { min-width: 0; }
.pf-hero__name {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.45rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.pf-hero__role {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 3px 9px;
  border-radius: 6px;
  background: var(--grad);
  color: #fff;
}
.pf-hero__email {
  margin-top: 5px;
  font-size: 0.86rem;
  color: var(--text3);
  font-family: var(--mono);
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 旅行足迹 */
.pf-fp { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
.pf-fp__item {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  background: var(--panel2);
  border: 1px solid var(--hairline);
  font-size: 0.78rem;
  color: var(--text3);
}
.pf-fp__item :deep(svg) { color: var(--prim); align-self: center; }
.pf-fp__item b {
  font-family: var(--font-display);
  font-size: 0.98rem;
  font-weight: 800;
  color: var(--text);
}
.pf-fp.is-loading .pf-fp__item b { color: var(--text3); }

/* 快捷入口 */
.pf-hero__nav { display: flex; flex-direction: column; gap: 8px; position: relative; z-index: 1; }
.pf-shortcut {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 208px;
  padding: 11px 14px;
  border-radius: var(--r-s);
  border: 1px solid var(--border);
  background: var(--panel);
  transition: transform 0.22s, border-color 0.22s, box-shadow 0.22s;
}
.pf-shortcut > :deep(svg:first-child) { color: var(--prim); flex-shrink: 0; }
.pf-shortcut > :deep(svg:last-child) { color: var(--text3); margin-left: auto; flex-shrink: 0; }
.pf-shortcut__body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.pf-shortcut__body b { font-size: 0.85rem; font-weight: 650; }
.pf-shortcut__body i {
  font-style: normal;
  font-size: 0.72rem;
  color: var(--text3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pf-shortcut:hover {
  transform: translateY(-2px);
  border-color: var(--blue-300);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.12);
}

/* ==================== 两列卡片 ==================== */
.pf-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
  align-items: start;
}

.pf-card { padding: 26px 28px; display: flex; flex-direction: column; gap: 16px; }

.pf-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.pf-title { font-size: 1.12rem; font-weight: 700; }
.pf-subtitle { font-size: 0.98rem; font-weight: 700; }
.pf-dirty {
  font-size: 0.7rem;
  font-weight: 650;
  color: var(--gold-600);
  background: var(--gold-soft);
  padding: 3px 9px;
  border-radius: 6px;
}

.pf-counter { font-size: 0.72rem; color: var(--text3); text-align: right; font-family: var(--mono); }
.pf-tip { font-size: 0.74rem; color: var(--text3); line-height: 1.6; }
.pf-tip--center { text-align: center; }
.pf-error { font-size: 0.75rem; color: var(--danger); }
.pf-danger { margin-top: 12px; }

/* ---- 头像选择 ---- */
.pf-avatar-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(58px, 1fr));
  gap: 10px;
  max-height: 210px;
  overflow-y: auto;
  padding: 2px;
}
.pf-avatar-opt {
  position: relative;
  border: 2px solid transparent;
  border-radius: 12px;
  padding: 0;
  overflow: hidden;
  background: var(--surface-soft);
  transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
}
.pf-avatar-opt img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }
.pf-avatar-opt:hover { transform: translateY(-2px); box-shadow: var(--shadow-sm); }
.pf-avatar-opt--active {
  border-color: var(--prim);
  box-shadow: 0 0 0 3px var(--primary-soft);
}
/* 选中角标：光靠描边在缩略图上不够醒目 */
.pf-avatar-opt__check {
  position: absolute;
  right: 4px;
  bottom: 4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--grad);
  color: #fff;
  display: grid;
  place-items: center;
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.28);
}

.pf-actions { display: flex; gap: 10px; align-items: center; margin-top: auto; }

/* ---- 密码 ---- */
.pf-pwd { position: relative; display: flex; align-items: center; }
.pf-pwd .input { padding-right: 42px; }
.pf-pwd__eye {
  position: absolute;
  right: 6px;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  color: var(--text3);
  transition: color 0.18s, background-color 0.18s;
}
.pf-pwd__eye:hover { color: var(--text); background: var(--surface-soft); }

.input--bad { border-color: var(--danger); }

.pf-strength { display: flex; align-items: center; gap: 10px; margin-top: 2px; }
.pf-strength__bars { display: flex; gap: 4px; flex-shrink: 0; }
.pf-strength__bars i {
  width: 26px;
  height: 4px;
  border-radius: 999px;
  background: var(--surface-soft);
  transition: background-color 0.24s;
}
.pf-strength__bars i.on.lv-1 { background: var(--danger); }
.pf-strength__bars i.on.lv-2 { background: var(--gold-500); }
.pf-strength__bars i.on.lv-3 { background: var(--cyan-500); }
.pf-strength__bars i.on.lv-4 { background: var(--success); }
.pf-strength__text { font-size: 0.73rem; color: var(--text3); }

/* 提示条：信息色而非警告色——这件事是正常的，不该让用户紧张 */
.pf-notice {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 11px 13px;
  border-radius: var(--r-s);
  background: var(--primary-soft);
  border: 1px solid var(--blue-100);
  font-size: 0.79rem;
  color: var(--blue-700);
  line-height: 1.6;
}
.pf-notice :deep(svg) { flex-shrink: 0; margin-top: 1px; }

.pf-hr { border: none; border-top: 1px dashed var(--line); margin: 8px 0 4px; }

.pf-memory { margin-top: 22px; }

/* ==================== 响应式 ==================== */
@media (max-width: 900px) {
  /* 头部改为上下堆叠：头像与信息一行，快捷入口铺满 */
  .pf-hero { grid-template-columns: auto minmax(0, 1fr); gap: 18px; }
  .pf-hero__nav { grid-column: 1 / -1; flex-direction: row; }
  .pf-shortcut { flex: 1; min-width: 0; }
}

@media (max-width: 760px) {
  .pf-grid { grid-template-columns: 1fr; gap: 18px; }
  .pf-card { padding: 22px 20px; }
}

@media (max-width: 560px) {
  .pf-hero { grid-template-columns: 1fr; justify-items: center; text-align: center; padding: 22px 18px; }
  .pf-hero__name { justify-content: center; }
  .pf-fp { justify-content: center; }
  .pf-hero__nav { flex-direction: column; width: 100%; }
  .pf-shortcut { min-width: 0; }
}
</style>
