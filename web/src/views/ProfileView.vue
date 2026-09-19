<script setup lang="ts">
/**
 * ProfileView · 我的 / 个人中心
 *
 * 布局（方案1：上沉浸 + 下分栏）
 *   1. 顶部沉浸区：旅行感渐变 + 地图纹理，大头像（可点击更换）、
 *      昵称与关键数据、两个主操作
 *   2. 下方左右分栏：左「基本资料」，右「账号安全 + 会话与账号」
 *   3. 通栏「我的记忆」
 *
 * 数据真实性：顶部的行程/对话/记忆数全部来自真实接口，
 * 三个请求并行且各自 catch——某一个失败只影响对应数字，不让整块消失。
 * 个人主页上出现写死的假数字最伤信任，所以宁可显示 0 也不编。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import MemoryPanel from '@/components/MemoryPanel.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import MapTexture from '@/components/MapTexture.vue'
import { AVATAR_BASE_URL } from '@/constants'
import { changePassword, deleteAccount, getAvatars, logout, updateProfile } from '@/api/user'
import { listItineraries } from '@/api/itinerary'
import { listConversations } from '@/api/conversation'
import { listMemories } from '@/api/memory'
import { useUiStore } from '@/stores/ui'
import { canAccessAdmin, roleLabel } from '@/utils/role'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const ui = useUiStore()
const user = useUserStore()

const avatars = ref<string[]>([])
const username = ref('')
const avatar = ref('')
const savingProfile = ref(false)
/** 是否存在未保存改动：决定保存按钮的可用态与文案 */
const dirty = ref(false)
/** 头像选择弹窗 */
const pickerOpen = ref(false)
const loadingAvatars = ref(true)

const pwdForm = reactive({ current: '', next: '', confirm: '' })
const savingPwd = ref(false)
const showPwd = ref(false)

const footprint = reactive({ itineraries: 0, conversations: 0, memories: 0 })
const loadingFootprint = ref(true)

onMounted(async () => {
  const info = await user.fetchUserInfo(true)
  if (info) {
    username.value = info.username ?? ''
    avatar.value = info.avatar ?? ''
  }
  dirty.value = false

  // 头像库与足迹数据互不依赖，并行拉取
  const [lib, its, convs, mems] = await Promise.allSettled([
    getAvatars(),
    listItineraries(),
    listConversations(),
    listMemories(false)
  ])

  if (lib.status === 'fulfilled') avatars.value = lib.value.avatars
  else ui.toast('头像库加载失败，可稍后重试', 'error')
  loadingAvatars.value = false

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
 * 是否展示「管理员」标识。
 * 两种管理员都展示 —— 原先只认 'admin'，引入 super_admin 后超管反而没有标识。
 * 文案区分档次，让用户一眼看出自己能不能改动数据。
 */
const isAdmin = computed(() => canAccessAdmin(user.userInfo?.role))
const adminRoleLabel = computed(() => roleLabel(user.userInfo?.role))

/* ---------------- 顶部数据与主操作 ---------------- */
const heroStats = computed(() => [
  { value: footprint.itineraries, label: '行程', to: '/itineraries' },
  { value: footprint.conversations, label: '对话', to: '/chat' },
  { value: footprint.memories, label: '偏好记忆', to: '' }
])

/** 新建行程：对话是唯一的生成入口，故带着一句起始语过去 */
function newTrip() {
  router.push({ path: '/chat', query: { example: '帮我规划一次新的旅行' } })
}

function continueChat() {
  router.push('/chat')
}

/**
 * 密码强度（0–4）。
 * 前端只做提示，真正校验在后端；不引第三方库，
 * 一个启发式规则足以覆盖「太短 / 太单一 / 常见弱口令」三类主要问题。
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

/* ---------------- 资料 ---------------- */
function openPicker() {
  if (loadingAvatars.value) {
    ui.toast('头像库还在加载…', 'info')
    return
  }
  if (!avatars.value.length) {
    ui.toast('头像库暂时不可用', 'error')
    return
  }
  pickerOpen.value = true
}

function chooseAvatar(name: string) {
  avatar.value = name
  dirty.value = true
  pickerOpen.value = false
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
    /* 即使后端撤销失败也继续本地登出，否则用户被困在当前会话里 */
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
</script>

<template>
  <div class="pf-page">
    <AppNavbar />
    <main id="main" tabindex="-1">
      <div class="container page">
        <!-- ==================== 1. 顶部沉浸区 ==================== -->
        <section class="hero-card">
          <MapTexture class="hero-card__map" routes />

          <div class="hero-card__inner">
            <!-- 大头像：点击更换 -->
            <button
              class="hero-avatar"
              type="button"
              :aria-label="avatarUrl ? '更换头像' : '选择头像'"
              @click="openPicker"
            >
              <img v-if="avatarUrl" :src="avatarUrl" alt="当前头像" />
              <span v-else class="hero-avatar__initial">{{ initial }}</span>
              <span class="hero-avatar__edit" aria-hidden="true">
                <TravelIcon name="camera" :size="15" />
              </span>
            </button>

            <div class="hero-body">
              <h1 class="hero-name">
                {{ displayName }}
                <!-- 标出具体档次：超管可读写、普通管理员只读。
                     只写「管理员」会让人误以为自己能改数据。 -->
                <span v-if="isAdmin" class="hero-role">{{ adminRoleLabel }}</span>
              </h1>
              <p class="hero-email">{{ user.userInfo?.email ?? '—' }}</p>

              <!-- 关键数据：可点进对应页面 -->
              <ul class="hero-stats" :class="{ 'is-loading': loadingFootprint }">
                <li v-for="s in heroStats" :key="s.label">
                  <component
                    :is="s.to ? 'RouterLink' : 'div'"
                    :to="s.to || undefined"
                    class="hero-stat"
                  >
                    <b>{{ loadingFootprint ? '—' : s.value }}</b>
                    <span>{{ s.label }}</span>
                  </component>
                </li>
              </ul>
            </div>

            <div class="hero-cta">
              <button class="btn btn-primary" @click="continueChat">
                <TravelIcon name="chat" :size="16" />
                继续对话
              </button>
              <button class="btn btn-ghost" @click="newTrip">
                <TravelIcon name="plane" :size="16" />
                新建行程
              </button>
            </div>
          </div>
        </section>

        <!-- ==================== 2. 下方左右分栏 ==================== -->
        <div class="pf-grid">
          <!-- ---------- 左：基本资料 ---------- -->
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
                @input="dirty = true"
              />
              <p class="pf-counter">{{ username.length }} / 10</p>
            </div>

            <div class="field">
              <label for="pf-email">邮箱</label>
              <input id="pf-email" class="input" :value="user.userInfo?.email ?? ''" disabled />
              <p class="pf-tip">邮箱是账号标识，暂不支持修改</p>
            </div>

            <!-- 头像选择：顶部可点，这里也留一个入口，不必非得回到顶部 -->
            <div class="field">
              <label>头像</label>
              <button class="avatar-trigger" type="button" @click="openPicker">
                <img v-if="avatarUrl" :src="avatarUrl" alt="" class="avatar-trigger__img" />
                <span v-else class="avatar-trigger__img avatar-trigger__img--empty">
                  {{ initial }}
                </span>
                <span class="avatar-trigger__text">
                  <b>更换头像</b>
                  <i>{{ loadingAvatars ? '正在加载头像库…' : `共 ${avatars.length} 款可选` }}</i>
                </span>
                <TravelIcon name="arrow-right" :size="15" />
              </button>
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

          <!-- ---------- 右：账号安全 + 会话与账号 ---------- -->
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
                <span class="pf-strength__text">
                  {{ pwdStrength.label }} · {{ pwdStrength.hint }}
                </span>
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

            <!-- 提示显眼但不吓人：用信息色而非警告色 -->
            <p class="pf-notice">
              <TravelIcon name="shield" :size="15" />
              修改密码后，所有设备都会退出登录，需要用新密码重新登录。
            </p>

            <div class="pf-actions">
              <button class="btn btn-ink btn--block" :disabled="!canSubmitPwd" @click="savePassword">
                {{ savingPwd ? '提交中…' : '修改密码' }}
              </button>
            </div>
          </section>
        </div>

        <!-- ==================== 2.5 通栏：会话与账号 ====================
             从「账号安全」里拆出来单独成块：
             退出与注销是账号级操作，和改密不是同一件事，
             挤在一张卡片里会让危险按钮紧挨着日常操作，既不好看也容易误点。 -->
        <section class="card session-card">
          <header class="session-card__head">
            <h2 class="pf-title">会话与账号</h2>
            <span class="session-card__hint">这些操作会影响你的登录状态</span>
          </header>

          <div class="session-grid">
            <!-- 退出登录：次要操作，描边样式 -->
            <div class="session-item">
              <div class="session-item__body">
                <h3>退出登录</h3>
                <p>退出后本地会清除登录凭证，下次需要重新输入密码。</p>
              </div>
              <button class="btn btn-ghost" @click="handleLogout">
                <TravelIcon name="key" :size="15" />
                退出登录
              </button>
            </div>

            <!-- 注销账号：危险操作，红色并明确后果 -->
            <div class="session-item session-item--danger">
              <div class="session-item__body">
                <h3>注销账号</h3>
                <p>注销将永久删除全部会话与行程，无法恢复。</p>
              </div>
              <button class="btn btn-danger" @click="handleDeleteAccount">
                <TravelIcon name="alert" :size="15" />
                注销账号
              </button>
            </div>
          </div>
        </section>

        <!-- ==================== 3. 通栏：我的记忆 ==================== -->
        <div class="pf-memory">
          <MemoryPanel />
        </div>
      </div>
    </main>

    <!-- ==================== 头像选择弹窗 ==================== -->
    <div v-if="pickerOpen" class="picker" @click.self="pickerOpen = false">
      <div class="picker__panel" role="dialog" aria-label="选择头像">
        <header class="picker__head">
          <h3>选择头像</h3>
          <button class="picker__close" aria-label="关闭" @click="pickerOpen = false">×</button>
        </header>
        <p class="picker__hint">选好后记得点「保存资料」，否则不会生效</p>

        <div class="picker__grid">
          <button
            v-for="a in avatars"
            :key="a"
            class="picker__opt"
            :class="{ 'picker__opt--active': a === avatar }"
            :aria-label="`选择头像 ${a}`"
            type="button"
            @click="chooseAvatar(a)"
          >
            <img :src="AVATAR_BASE_URL + a" :alt="a" loading="lazy" />
            <span v-if="a === avatar" class="picker__check" aria-hidden="true">
              <TravelIcon name="check" :size="12" />
            </span>
          </button>
        </div>

        <footer class="picker__foot">
          <button class="btn btn-ghost btn--sm" @click="pickerOpen = false">取消</button>
          <button class="btn btn-primary btn--sm" @click="pickerOpen = false">完成</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ==================== 1. 顶部沉浸区 ==================== */
.hero-card {
  position: relative;
  overflow: hidden;
  border-radius: var(--r-l);
  padding: 30px 32px;
  margin-bottom: 22px;
  /* 浅色旅行感渐变：冷雾蓝到白，不走高饱和 */
  background: linear-gradient(135deg, #eef4ff 0%, #f7f9fc 46%, #f0f9ff 100%);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}
.hero-card__map {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  color: var(--blue-600);
  opacity: 0.85;
  mask-image: radial-gradient(ellipse 70% 120% at 88% 10%, #000 6%, transparent 68%);
  -webkit-mask-image: radial-gradient(ellipse 70% 120% at 88% 10%, #000 6%, transparent 68%);
}

.hero-card__inner {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 24px;
}

/* ---- 大头像（可点击更换）---- */
.hero-avatar {
  position: relative;
  width: 104px;
  height: 104px;
  border-radius: 50%;
  padding: 3px;
  background: var(--grad);
  box-shadow: 0 12px 30px var(--glow);
  flex-shrink: 0;
  transition: transform 0.24s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.hero-avatar:hover { transform: translateY(-2px) scale(1.02); }
.hero-avatar:active { transform: scale(0.99); }

.hero-avatar img,
.hero-avatar__initial {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
  display: grid;
  place-items: center;
  background: var(--panel);
  font-family: var(--font-display);
  font-size: 2.5rem;
  font-weight: 800;
  color: var(--prim);
}

/* 相机角标：暗示头像可点 */
.hero-avatar__edit {
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--panel);
  color: var(--prim);
  border: 2px solid var(--panel);
  box-shadow: var(--shadow-sm);
}

.hero-body { min-width: 0; }
.hero-name {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.022em;
}
.hero-role {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 3px 9px;
  border-radius: 6px;
  background: var(--grad);
  color: #fff;
}
.hero-email {
  margin-top: 5px;
  font-size: 0.85rem;
  color: var(--text3);
  font-family: var(--mono);
  overflow: hidden;
  text-overflow: ellipsis;
}

.hero-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  list-style: none;
  padding: 0;
}
.hero-stat {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid var(--hairline);
  backdrop-filter: blur(6px);
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}
a.hero-stat:hover {
  transform: translateY(-1px);
  border-color: var(--blue-300);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.12);
}
.hero-stat b {
  font-family: var(--font-display);
  font-size: 1.05rem;
  font-weight: 800;
  color: var(--text);
}
.hero-stat span { font-size: 0.76rem; color: var(--text2); }
.hero-stats.is-loading .hero-stat b { color: var(--text3); }

.hero-cta { display: flex; flex-direction: column; gap: 9px; flex-shrink: 0; }
.hero-cta .btn { justify-content: center; white-space: nowrap; }

/* ==================== 2. 左右分栏 ==================== */
.pf-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
  /* 不设 align-items: start —— 那会让每张卡片只按自身内容高度渲染，
     两栏高度必然不等，视觉上就是「左右不均衡」。
     默认的 stretch 让两张卡片撑满同一行高，高度自动对齐。 */
}
.pf-card {
  padding: 26px 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 卡片内的操作区固定在底部：配合 .pf-card 的 column 布局，
   左右两栏的主按钮会落在同一水平线上，视线更整齐。 */
.pf-actions { margin-top: auto; }

.pf-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.pf-title { font-size: 1.12rem; font-weight: 700; }
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
.pf-error { font-size: 0.75rem; color: var(--danger); }

/* ---- 头像触发条 ---- */
.avatar-trigger {
  display: flex;
  align-items: center;
  gap: 13px;
  width: 100%;
  padding: 11px 14px;
  border-radius: var(--r-s);
  border: 1px solid var(--border);
  background: var(--panel);
  text-align: left;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}
.avatar-trigger:hover {
  border-color: var(--blue-300);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.1);
  transform: translateY(-1px);
}
.avatar-trigger__img {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  border: 2px solid var(--blue-100);
}
.avatar-trigger__img--empty {
  display: grid;
  place-items: center;
  background: var(--primary-soft);
  color: var(--prim);
  font-weight: 700;
}
.avatar-trigger__text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.avatar-trigger__text b { font-size: 0.87rem; font-weight: 650; }
.avatar-trigger__text i {
  font-style: normal;
  font-size: 0.74rem;
  color: var(--text3);
}
.avatar-trigger > :deep(svg) { margin-left: auto; color: var(--text3); flex-shrink: 0; }

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

.pf-memory { margin-top: 22px; }

/* ==================== 2.5 通栏：会话与账号 ==================== */
.session-card { padding: 24px 28px; margin-top: 22px; }
.session-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 18px;
}
.session-card__hint { font-size: 0.76rem; color: var(--text3); }

/* 两项并排：退出为常规项，注销为危险项并带淡红底以示区分 */
.session-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 18px;
  border-radius: var(--r-s);
  border: 1px solid var(--border);
  background: var(--panel2);
  transition: border-color 0.22s, box-shadow 0.22s;
}
.session-item:hover { border-color: var(--blue-200); box-shadow: var(--shadow-sm); }
.session-item--danger {
  border-color: rgba(224, 82, 82, 0.22);
  background: rgba(224, 82, 82, 0.04);
}
.session-item--danger:hover {
  border-color: rgba(224, 82, 82, 0.4);
  box-shadow: 0 8px 20px rgba(224, 82, 82, 0.1);
}

.session-item__body { min-width: 0; }
.session-item__body h3 { font-size: 0.92rem; font-weight: 700; margin-bottom: 4px; }
.session-item__body p { font-size: 0.78rem; color: var(--text3); line-height: 1.55; }
.session-item .btn { flex-shrink: 0; white-space: nowrap; }

/* ==================== 头像弹窗 ==================== */
.picker {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.42);
  backdrop-filter: blur(2px);
}
.picker__panel {
  width: min(520px, 100%);
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border-radius: var(--r-l);
  padding: 22px 24px;
  box-shadow: var(--shadow-lift);
  animation: pickerIn 0.26s cubic-bezier(0.2, 0.7, 0.2, 1);
}
@keyframes pickerIn {
  from { opacity: 0; transform: translateY(12px) scale(0.98); }
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .picker__panel { animation: none; }
}

.picker__head { display: flex; align-items: center; justify-content: space-between; }
.picker__head h3 { font-size: 1.05rem; font-weight: 700; }
.picker__close {
  border: none;
  background: transparent;
  font-size: 1.5rem;
  line-height: 1;
  color: var(--text3);
  padding: 0 4px;
}
.picker__close:hover { color: var(--text); }
.picker__hint { margin-top: 6px; font-size: 0.76rem; color: var(--text3); }

.picker__grid {
  margin: 16px 0;
  padding: 2px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(64px, 1fr));
  gap: 10px;
  overflow-y: auto;
  flex: 1;
}
.picker__opt {
  position: relative;
  border: 2px solid transparent;
  border-radius: 12px;
  padding: 0;
  overflow: hidden;
  background: var(--surface-soft);
  transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
}
.picker__opt img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }
.picker__opt:hover { transform: translateY(-2px); box-shadow: var(--shadow-sm); }
.picker__opt--active {
  border-color: var(--prim);
  box-shadow: 0 0 0 3px var(--primary-soft);
}
.picker__check {
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
.picker__foot { display: flex; justify-content: flex-end; gap: 10px; }

/* ==================== 响应式 ==================== */
@media (max-width: 900px) {
  /* 顶部改为：头像与信息一行，按钮组占满一行 */
  .hero-card__inner { grid-template-columns: auto minmax(0, 1fr); gap: 20px; }
  .hero-cta { grid-column: 1 / -1; flex-direction: row; }
  .hero-cta .btn { flex: 1; }
}

@media (max-width: 760px) {
  .pf-grid { grid-template-columns: 1fr; gap: 18px; }
  .pf-card { padding: 22px 20px; }
  .hero-card { padding: 24px 20px; }
  /* 单列后不必再撑高，避免卡片底部出现大片空白 */
  .pf-actions { margin-top: 4px; }
  .session-grid { grid-template-columns: 1fr; }
  .session-card { padding: 20px; }
}

@media (max-width: 560px) {
  .hero-card__inner { grid-template-columns: 1fr; justify-items: center; text-align: center; }
  .hero-name { justify-content: center; }
  .hero-stats { justify-content: center; }
  .hero-cta { width: 100%; }
  .picker__grid { grid-template-columns: repeat(auto-fill, minmax(58px, 1fr)); }
  /* 窄屏把说明与按钮改为上下排列，避免按钮被文字挤到换行 */
  .session-item { flex-direction: column; align-items: stretch; gap: 14px; }
  .session-item .btn { width: 100%; justify-content: center; }
}
</style>
