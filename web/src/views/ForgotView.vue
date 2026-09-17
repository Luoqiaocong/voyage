<script setup lang="ts">
/**
 * ForgotView · 找回通行证（重置密码）
 *
 * 单一职责：本页只做重置密码，不含登录/注册的任何字段或文案。
 * 之所以独立成页而不是继续挂在 LoginView 的 mode 里——
 * 三者共用一个组件会导致字段与文案互相渗透（例如注册的「旅行昵称」
 * 出现在重置流程中），也让每个页面的可维护性随分支增长而下降。
 *
 * 流程严格两步，不混排：
 *   步骤 1 · 验证邮箱   → 邮箱 + 6 位验证码 + 获取验证码（60s 倒计时）
 *   步骤 2 · 设置新密码 → 新密码 + 确认新密码
 *
 * 后端接口：
 *   POST /auth/code          { email }              发验证码
 *   POST /auth/reset-token   { email, code } → token 校验验证码并换取重置令牌
 *   POST /users/reset        { password, token }     用令牌设置新密码
 */
import { computed, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { resetPassword, resetToken, sendCode } from '@/api/user'
import { useUiStore } from '@/stores/ui'
import TravelIcon from '@/components/TravelIcon.vue'
import MapTexture from '@/components/MapTexture.vue'
import { AUTH_COPY } from '@/constants/copy'

const router = useRouter()
const ui = useUiStore()

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** 当前步骤：1 验证邮箱 / 2 设置新密码 */
const step = ref<1 | 2>(1)
const loading = ref(false)
const showPwd = ref(false)

const form = reactive({
  email: '',
  code: '',
  /** 步骤 1 成功后由后端返回的重置令牌，步骤 2 提交时使用 */
  token: '',
  password: '',
  confirm: ''
})

/** 字段级错误：统一显示在对应输入框下方 */
const errors = reactive<Record<string, string>>({})

function clearError(key: string) {
  delete errors[key]
}

/* ---------------- 验证码倒计时 ---------------- */
const countdown = ref(0)
let timer: number | null = null

function stopTimer() {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

function startCountdown() {
  countdown.value = 60
  stopTimer()
  timer = window.setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) stopTimer()
  }, 1000)
}

onUnmounted(stopTimer)

const codeButtonText = computed(() =>
  countdown.value > 0 ? `${countdown.value} 秒后重发` : '获取验证码'
)

/* ---------------- 步骤 1：发送与校验验证码 ---------------- */
async function handleSendCode() {
  const email = form.email.trim()
  if (!EMAIL_RE.test(email)) {
    errors.email = AUTH_COPY.emailInvalid
    return
  }
  clearError('email')
  try {
    await sendCode(email)
    ui.toast(AUTH_COPY.codeSent, 'success')
    startCountdown()
  } catch (e: any) {
    errors.email = e?.message ?? '验证码发送失败，稍后重试'
  }
}

async function handleVerify() {
  Object.keys(errors).forEach((k) => delete errors[k])

  const email = form.email.trim()
  if (!email) {
    errors.email = AUTH_COPY.emailRequired
    return
  }
  if (!EMAIL_RE.test(email)) {
    errors.email = AUTH_COPY.emailInvalid
    return
  }
  if (!form.code.trim()) {
    errors.code = AUTH_COPY.codeRequired
    return
  }

  loading.value = true
  try {
    const res = await resetToken(email, form.code.trim())
    form.token = res.token
    step.value = 2
  } catch (e: any) {
    errors.code = e?.message ?? '验证码校验失败，请检查后重试'
  } finally {
    loading.value = false
  }
}

/* ---------------- 步骤 2：设置新密码 ---------------- */
async function handleReset() {
  Object.keys(errors).forEach((k) => delete errors[k])

  if (form.password.length < 8) {
    errors.password = AUTH_COPY.passwordShort
    return
  }
  if (form.password !== form.confirm) {
    errors.confirm = AUTH_COPY.passwordMismatch
    return
  }

  loading.value = true
  try {
    await resetPassword(form.password, form.token)
    ui.toast(AUTH_COPY.resetSuccess, 'success')
    router.replace('/login')
  } catch (e: any) {
    errors.form = e?.message ?? '重置失败，稍后重试'
  } finally {
    loading.value = false
  }
}

/**
 * 返回步骤 1 修改邮箱。
 * 重置令牌与邮箱强绑定，改了邮箱就必须重新验证，故清空令牌与验证码。
 */
function backToStep1() {
  form.token = ''
  form.code = ''
  Object.keys(errors).forEach((k) => delete errors[k])
  step.value = 1
}

/** 密码强度：与个人中心保持同一套判定，避免两处标准不一致 */
const pwdStrength = computed(() => {
  const v = form.password
  if (!v) return { score: 0, label: '' }
  let score = 0
  if (v.length >= 8) score++
  if (v.length >= 12) score++
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(v)).length
  if (kinds >= 2) score++
  if (kinds >= 3) score++
  if (/^(.)\1+$/.test(v) || /^(?:0123|1234|abcd|qwer|password|admin)/i.test(v)) {
    score = Math.min(score, 1)
  }
  return { score: Math.min(score, 4), label: ['太弱', '偏弱', '一般', '较强', '很强'][Math.min(score, 4)] }
})

const pwdMismatch = computed(
  () => form.confirm.length > 0 && form.password !== form.confirm
)
</script>

<template>
  <div class="fg-page">
    <div class="fg-bg" aria-hidden="true">
      <span class="fg-glow fg-glow--a"></span>
      <span class="fg-glow fg-glow--b"></span>
      <MapTexture class="fg-map" routes />
    </div>

    <main class="fg-main">
      <div class="fg-card">
        <!-- 品牌 -->
        <RouterLink to="/" class="fg-brand">
          <span class="fg-brand__mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2.4" />
              <path
                d="M16 4.5 L18.8 13.2 L27.5 16 L18.8 18.8 L16 27.5 L13.2 18.8 L4.5 16 L13.2 13.2 Z"
                fill="currentColor"
              />
              <circle cx="16" cy="16" r="2.2" fill="#fff" />
            </svg>
          </span>
          <span class="fg-brand__text">Voyage <em>AI</em></span>
        </RouterLink>

        <!-- 步骤指示：当前高亮，已完成打勾，未完成灰色 -->
        <ol class="steps" aria-label="重置密码步骤">
          <li
            class="steps__item"
            :class="{ 'steps__item--on': step === 1, 'steps__item--done': step === 2 }"
          >
            <span class="steps__no">
              <TravelIcon v-if="step === 2" name="check" :size="12" />
              <template v-else>1</template>
            </span>
            <span class="steps__label">验证邮箱</span>
          </li>
          <li class="steps__line" :class="{ 'steps__line--done': step === 2 }" aria-hidden="true"></li>
          <li class="steps__item" :class="{ 'steps__item--on': step === 2 }">
            <span class="steps__no">2</span>
            <span class="steps__label">设置新密码</span>
          </li>
        </ol>

        <!-- ==================== 步骤 1 ==================== -->
        <template v-if="step === 1">
          <header class="fg-head">
            <h1>找回通行证</h1>
            <p>验证邮箱后即可设置新密码</p>
          </header>

          <form class="fg-form" novalidate @submit.prevent="handleVerify">
            <div class="field">
              <label for="fg-email">邮箱</label>
              <input
                id="fg-email"
                v-model="form.email"
                class="input"
                :class="{ 'input--bad': errors.email }"
                type="email"
                autocomplete="email"
                placeholder="用于接收验证码"
                @input="clearError('email')"
              />
              <p v-if="errors.email" class="fg-err">{{ errors.email }}</p>
            </div>

            <div class="field">
              <label for="fg-code">邮箱验证码</label>
              <div class="fg-code">
                <input
                  id="fg-code"
                  v-model="form.code"
                  class="input"
                  :class="{ 'input--bad': errors.code }"
                  maxlength="6"
                  inputmode="numeric"
                  autocomplete="one-time-code"
                  placeholder="6 位数字"
                  @input="clearError('code')"
                />
                <button
                  type="button"
                  class="btn btn-ghost fg-code__btn"
                  :disabled="countdown > 0"
                  @click="handleSendCode"
                >
                  {{ codeButtonText }}
                </button>
              </div>
              <p v-if="errors.code" class="fg-err">{{ errors.code }}</p>
            </div>

            <p v-if="errors.form" class="fg-err fg-err--form">{{ errors.form }}</p>

            <button class="btn btn-primary btn--block btn--lg" type="submit" :disabled="loading">
              {{ loading ? '验证中…' : '下一步' }}
            </button>
          </form>

          <RouterLink to="/login" class="fg-back">
            <TravelIcon name="arrow-left" :size="14" />
            返回登录
          </RouterLink>
        </template>

        <!-- ==================== 步骤 2 ==================== -->
        <template v-else>
          <header class="fg-head">
            <h1>设置新密码</h1>
            <p>请为你的账号设置一个新密码</p>
          </header>

          <form class="fg-form" novalidate @submit.prevent="handleReset">
            <div class="field">
              <label for="fg-pwd">新密码</label>
              <div class="fg-pwd">
                <input
                  id="fg-pwd"
                  v-model="form.password"
                  class="input"
                  :class="{ 'input--bad': errors.password }"
                  :type="showPwd ? 'text' : 'password'"
                  autocomplete="new-password"
                  placeholder="至少 8 位，建议数字 + 字母"
                  @input="clearError('password')"
                />
                <button
                  class="fg-pwd__eye"
                  type="button"
                  :aria-label="showPwd ? '隐藏密码' : '显示密码'"
                  @click="showPwd = !showPwd"
                >
                  <TravelIcon :name="showPwd ? 'eye-off' : 'eye'" :size="15" />
                </button>
              </div>
              <div v-if="form.password" class="fg-strength">
                <span class="fg-strength__bars">
                  <i
                    v-for="n in 4"
                    :key="n"
                    :class="[`lv-${pwdStrength.score}`, { on: n <= pwdStrength.score }]"
                  ></i>
                </span>
                <span class="fg-strength__text">{{ pwdStrength.label }}</span>
              </div>
              <p v-if="errors.password" class="fg-err">{{ errors.password }}</p>
            </div>

            <div class="field">
              <label for="fg-confirm">确认新密码</label>
              <input
                id="fg-confirm"
                v-model="form.confirm"
                class="input"
                :class="{ 'input--bad': errors.confirm || pwdMismatch }"
                :type="showPwd ? 'text' : 'password'"
                autocomplete="new-password"
                placeholder="再输入一次"
                @input="clearError('confirm')"
              />
              <p v-if="errors.confirm || pwdMismatch" class="fg-err">
                {{ errors.confirm || AUTH_COPY.passwordMismatch }}
              </p>
            </div>

            <p v-if="errors.form" class="fg-err fg-err--form">{{ errors.form }}</p>

            <button class="btn btn-primary btn--block btn--lg" type="submit" :disabled="loading">
              {{ loading ? '提交中…' : '完成并登录' }}
            </button>
          </form>

          <div class="fg-foot">
            <button class="link-btn" type="button" @click="backToStep1">换个邮箱</button>
            <span class="fg-foot__dot" aria-hidden="true">·</span>
            <RouterLink to="/login" class="link-btn">返回登录</RouterLink>
          </div>
        </template>
      </div>
    </main>
  </div>
</template>

<style scoped>
.fg-page {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 40px 20px;
  overflow: hidden;
}

/* ---------- 背景：浅色旅行感 ---------- */
.fg-bg { position: absolute; inset: 0; pointer-events: none; }
.fg-glow { position: absolute; border-radius: 50%; filter: blur(80px); }
.fg-glow--a {
  width: 560px;
  height: 420px;
  top: -160px;
  left: -120px;
  background: radial-gradient(circle, rgba(37, 99, 235, 0.14), transparent 68%);
}
.fg-glow--b {
  width: 520px;
  height: 400px;
  bottom: -160px;
  right: -110px;
  background: radial-gradient(circle, rgba(14, 165, 233, 0.12), transparent 68%);
}
.fg-map {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  color: var(--blue-600);
  opacity: 0.55;
  mask-image: radial-gradient(ellipse 72% 70% at 50% 45%, #000 12%, transparent 74%);
  -webkit-mask-image: radial-gradient(ellipse 72% 70% at 50% 45%, #000 12%, transparent 74%);
}

/* ---------- 卡片：居中、宽度适中 ---------- */
.fg-main { position: relative; z-index: 1; width: 100%; display: grid; place-items: center; }
.fg-card {
  width: 100%;
  max-width: 440px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  box-shadow: 0 24px 60px rgba(37, 99, 235, 0.12);
  padding: 32px 34px 28px;
}

/* ---------- 品牌 ---------- */
.fg-brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 22px;
}
.fg-brand__mark {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: var(--grad);
  color: #fff;
  display: grid;
  place-items: center;
  box-shadow: 0 6px 16px var(--glow);
}
.fg-brand__mark svg { width: 20px; height: 20px; }
.fg-brand__text {
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.fg-brand__text em { font-style: normal; color: var(--prim); }

/* ---------- 步骤指示 ---------- */
.steps {
  display: flex;
  align-items: center;
  gap: 10px;
  list-style: none;
  margin: 0 0 24px;
  padding: 0;
}
.steps__item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.79rem;
  color: var(--text3);
  transition: color 0.24s;
}
.steps__no {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--mono);
  font-size: 0.68rem;
  font-weight: 700;
  background: var(--surface-soft);
  color: var(--text3);
  flex-shrink: 0;
  transition: background-color 0.24s, color 0.24s, box-shadow 0.24s;
}
.steps__line {
  flex: 1;
  height: 1px;
  min-width: 22px;
  background: var(--line);
  transition: background-color 0.24s;
}
.steps__line--done { background: var(--prim); }

/* 当前步骤高亮 */
.steps__item--on { color: var(--text); font-weight: 650; }
.steps__item--on .steps__no {
  background: var(--grad);
  color: #fff;
  box-shadow: 0 4px 12px var(--glow);
}
/* 已完成：打勾 */
.steps__item--done { color: var(--prim); }
.steps__item--done .steps__no { background: var(--primary-soft); color: var(--prim); }

/* ---------- 标题 ---------- */
.fg-head { margin-bottom: 22px; }
.fg-head h1 {
  font-size: 1.42rem;
  font-weight: 800;
  letter-spacing: -0.022em;
}
.fg-head p {
  margin-top: 7px;
  font-size: 0.87rem;
  color: var(--text2);
  line-height: 1.6;
}

/* ---------- 表单 ---------- */
.fg-form { display: flex; flex-direction: column; gap: 16px; }

.fg-code { display: flex; gap: 9px; }
.fg-code .input { flex: 1; min-width: 0; }
.fg-code__btn {
  flex-shrink: 0;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  /* 固定最小宽度：倒计时数字变化时按钮不跳动 */
  min-width: 110px;
  justify-content: center;
}
.fg-code__btn:disabled { opacity: 0.6; cursor: not-allowed; }

.fg-pwd { position: relative; display: flex; align-items: center; }
.fg-pwd .input { padding-right: 42px; }
.fg-pwd__eye {
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
.fg-pwd__eye:hover { color: var(--text); background: var(--surface-soft); }

.input--bad { border-color: var(--danger); }

/* 字段级错误：紧贴输入框下方 */
.fg-err {
  margin-top: 1px;
  font-size: 0.76rem;
  color: var(--danger);
  line-height: 1.5;
}
.fg-err--form {
  padding: 9px 12px;
  border-radius: var(--r-s);
  background: rgba(224, 82, 82, 0.07);
  border: 1px solid rgba(224, 82, 82, 0.18);
  margin-top: 0;
}

.fg-strength { display: flex; align-items: center; gap: 9px; margin-top: 2px; }
.fg-strength__bars { display: flex; gap: 4px; }
.fg-strength__bars i {
  width: 24px;
  height: 4px;
  border-radius: 999px;
  background: var(--surface-soft);
  transition: background-color 0.24s;
}
.fg-strength__bars i.on.lv-1 { background: var(--danger); }
.fg-strength__bars i.on.lv-2 { background: var(--gold-500); }
.fg-strength__bars i.on.lv-3 { background: var(--cyan-500); }
.fg-strength__bars i.on.lv-4 { background: var(--success); }
.fg-strength__text { font-size: 0.73rem; color: var(--text3); }

/* ---------- 底部 ---------- */
.fg-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 20px;
  font-size: 0.82rem;
  color: var(--text3);
  transition: color 0.18s;
}
.fg-back:hover { color: var(--prim); }

.fg-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 20px;
  font-size: 0.82rem;
}
.fg-foot__dot { color: var(--text3); }
.link-btn {
  background: none;
  border: none;
  padding: 0;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--prim);
  cursor: pointer;
}
.link-btn:hover { text-decoration: underline; }

/* ---------- 响应式 ---------- */
@media (max-width: 480px) {
  .fg-page { padding: 24px 14px; place-items: start center; }
  .fg-card { padding: 26px 22px 22px; border-radius: var(--r-m); }
  .fg-head h1 { font-size: 1.28rem; }
  /* 验证码按钮移到输入框下方，避免窄屏挤压 */
  .fg-code { flex-direction: column; }
  .fg-code__btn { width: 100%; min-width: 0; }
}
</style>
