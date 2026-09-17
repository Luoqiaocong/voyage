<script setup lang="ts">
/**
 * LoginView · 沉浸式旅行登录体验
 *
 * 布局：左侧大幅旅行场景（按场景轮换 + 鼠标视差），右侧船票式表单卡片。
 * 交互：登录/注册滑动切换、忘记密码分步、第三方登录入口、记住我。
 * 移动端：场景退化为顶部画面，表单上滑成「底部抽屉」。
 */
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, register, sendCode } from '@/api/user'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { useTheme } from '@/composables/useTheme'
import TravelScene from '@/components/TravelScene.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import { AUTH_COPY, AUTH_SCENES } from '@/constants/copy'

/**
 * 本页只负责「登录」与「注册」两件事。
 *
 * 重置密码已拆到独立页面 /forgot（ForgotView.vue）——三者共用一个组件时
 * 字段与文案会互相渗透，例如注册的「旅行昵称」曾出现在重置流程里。
 * 想改重置密码请去 ForgotView，不要在这里加回 forgot 分支。
 */
type Mode = 'login' | 'register'

const router = useRouter()
const route = useRoute()
const user = useUserStore()
const ui = useUiStore()
const { isDark, toggleTheme } = useTheme()

/* ---------------- 模式 ---------------- */
const initial = route.query.tab
const mode = ref<Mode>(initial === 'register' ? 'register' : 'login')
/** 1 = 登录，2 = 注册，用于滑轨位移 */
const slideIndex = computed(() => (mode.value === 'login' ? 0 : 1))
const loading = ref(false)

/* ---------------- 场景轮换 ---------------- */
const sceneIdx = ref(0)
let sceneTimer: number | null = null
const scene = computed(() => AUTH_SCENES[sceneIdx.value])

function startSceneRotation() {
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
  sceneTimer = window.setInterval(() => {
    sceneIdx.value = (sceneIdx.value + 1) % AUTH_SCENES.length
  }, 6500)
}
function stopSceneRotation() {
  if (sceneTimer !== null) {
    window.clearInterval(sceneTimer)
    sceneTimer = null
  }
}
function pickScene(i: number) {
  sceneIdx.value = i
  stopSceneRotation()
  startSceneRotation()
}

/* ---------------- 鼠标视差 ---------------- */
const parallax = ref(0)
function onMove(e: MouseEvent) {
  const r = { w: window.innerWidth, h: window.innerHeight }
  const x = e.clientX / r.w - 0.5
  const y = e.clientY / r.h - 0.5
  parallax.value = Math.max(-1, Math.min(1, x * 1.2 + y * 0.4))
}

/* ---------------- 表单 ---------------- */
const loginForm = reactive({ email: '', password: '' })
const remember = ref(true)

const regForm = reactive({ email: '', username: '', password: '', code: '' })
const countdown = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

const showLoginPwd = ref(false)
const showRegPwd = ref(false)
const errors = reactive<Record<string, string>>({})

function clearError(k: string) {
  if (errors[k]) delete errors[k]
}
watch(mode, () => {
  Object.keys(errors).forEach((k) => delete errors[k])
})

/** 恢复上次登录的邮箱 */
const REMEMBER_KEY = 'voyage-remember-email'
onMounted(() => {
  try {
    const saved = localStorage.getItem(REMEMBER_KEY)
    if (saved) {
      loginForm.email = saved
      remember.value = true
    }
  } catch {
    /* 忽略 */
  }
  startSceneRotation()
  window.addEventListener('mousemove', onMove)
})
onUnmounted(() => {
  stopSceneRotation()
  stopTimer()
  window.removeEventListener('mousemove', onMove)
})

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function startCountdown() {
  countdown.value = 60
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) stopTimer()
  }, 1000)
}

function switchMode(m: Mode) {
  mode.value = m
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

async function handleSendCode() {
  const email = regForm.email.trim()
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
    ui.toast(e?.message ?? '验证码发送失败', 'error')
  }
}

async function handleLogin() {
  const ok = validateLogin()
  if (!ok) return
  loading.value = true
  try {
    const res = await login(loginForm.email.trim(), loginForm.password)
    user.setAuth(res)
    await user.fetchUserInfo(true)

    try {
      if (remember.value) localStorage.setItem(REMEMBER_KEY, loginForm.email.trim())
      else localStorage.removeItem(REMEMBER_KEY)
    } catch {
      /* 忽略 */
    }
    ui.toast(AUTH_COPY.loginSuccess, 'success')
    router.replace(withExample(safeRedirect()))
  } catch (e: any) {
    // 关键：走到这里说明本次登录流程没有完整成功（例如令牌写入后
    // fetchUserInfo 抛错）。若不清理，localStorage 里会留下一个「已登录但不可用」
    // 的状态——此时 /login 的 guestOnly 守卫会把用户弹走，而目标页又因令牌无效
    // 无法加载数据，用户看到的就是一个空白界面。
    user.clearAuth()
    errors.form = e?.message ?? '登录失败，稍后重试'
  } finally {
    loading.value = false
  }
}

/**
 * 首页示例胶囊带来的预填问题（?example=...）。
 *
 * 从首页点「试试这样说」过来时，这句话要一路带到对话页并填进输入框，
 * 否则用户点了一下却什么都没发生。用 query 传递以免刷新后丢失。
 */
const pendingExample = computed(() => {
  const raw = route.query.example
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' ? value : ''
})

/** 把待发送的问题附加到跳转目标上 */
function withExample(path: string): string {
  if (!pendingExample.value) return path
  const sep = path.includes('?') ? '&' : '?'
  return `${path}${sep}example=${encodeURIComponent(pendingExample.value)}`
}

/**
 * 取安全的登录后跳转目标。
 *
 * 只接受站内绝对路径（以 / 开头且不是 //host 形式）。
 * 直接把 query 参数交给 router.replace 有两个问题：
 * - 形如 "http://evil.com" 的外部地址会被当作路径处理并抛错，中断渲染；
 * - 形如 "//evil.com" 的值可能被当成协议相对 URL 造成开放重定向。
 */
function safeRedirect(): string {
  const raw = route.query.redirect
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value === 'string' && value.startsWith('/') && !value.startsWith('//')) {
    return value
  }
  return '/chat'
}

function validateLogin(): boolean {
  Object.keys(errors).forEach((k) => delete errors[k])
  if (!loginForm.email.trim()) {
    errors.email = AUTH_COPY.emailRequired
    return false
  }
  if (!EMAIL_RE.test(loginForm.email.trim())) {
    errors.email = AUTH_COPY.emailInvalid
    return false
  }
  if (!loginForm.password) {
    errors.password = AUTH_COPY.passwordRequired
    return false
  }
  return true
}

function validateRegister(): boolean {
  Object.keys(errors).forEach((k) => delete errors[k])
  let ok = true
  if (!regForm.email.trim() || !EMAIL_RE.test(regForm.email.trim())) {
    errors.email = regForm.email.trim() ? AUTH_COPY.emailInvalid : AUTH_COPY.emailRequired
    ok = false
  }
  if (!regForm.code.trim()) {
    errors.code = AUTH_COPY.codeRequired
    ok = false
  }
  const name = regForm.username.trim()
  if (!name) {
    errors.username = AUTH_COPY.usernameRequired
    ok = false
  } else if (name.length < 2 || name.length > 10) {
    errors.username = AUTH_COPY.usernameLength
    ok = false
  }
  if (regForm.password.length < 8) {
    errors.password = AUTH_COPY.passwordShort
    ok = false
  }
  return ok
}

async function handleRegister() {
  if (!validateRegister()) return
  loading.value = true
  try {
    const email = regForm.email.trim()
    await register({
      email,
      password: regForm.password,
      username: regForm.username.trim(),
      code: regForm.code.trim()
    })
    ui.toast(AUTH_COPY.registerSuccess, 'success')
    const res = await login(email, regForm.password)
    user.setAuth(res)
    await user.fetchUserInfo(true)
    router.replace(withExample('/chat'))
  } catch (e: any) {
    errors.form = e?.message ?? '注册失败，稍后重试'
  } finally {
    loading.value = false
  }
}

/* ---------------- 第三方登录（占位，待后端接入） ---------------- */
const thirdParty = [
  { name: 'wechat' as const, label: '微信' },
  { name: 'apple' as const, label: 'Apple' },
  { name: 'google' as const, label: 'Google' }
]

function handleThirdParty() {
  ui.toast(AUTH_COPY.thirdPartySoon, 'info')
}
</script>

<template>
  <main id="main" tabindex="-1" class="auth">
    <!-- ==================== 左侧：旅行场景 ==================== -->
    <section class="auth__scene" aria-hidden="true">
      <TravelScene :scene="scene.key" :depth="1 + parallax * 0.35" />

      <!-- 场景文案 -->
      <div class="auth__scene-copy">
        <Transition name="copy" mode="out-in">
          <div :key="scene.key" class="scene-copy">
            <p class="scene-copy__eyebrow">{{ scene.eyebrow }}</p>
            <h2 class="scene-copy__title">{{ scene.title }}</h2>
            <p class="scene-copy__desc">{{ scene.desc }}</p>
          </div>
        </Transition>

        <!-- 场景切换点 -->
        <div class="scene-dots" role="tablist" aria-label="切换场景">
          <button
            v-for="(s, i) in AUTH_SCENES"
            :key="s.key"
            type="button"
            class="scene-dot"
            :class="{ 'scene-dot--on': i === sceneIdx }"
            :aria-label="s.title"
            :aria-selected="i === sceneIdx"
            role="tab"
            @click="pickScene(i)"
          ></button>
        </div>
      </div>

      <!-- 品牌落款 -->
      <RouterLink to="/" class="auth__brand" @click.stop>
        <span class="auth__brand-mark">
          <svg viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2.4" />
            <path d="M16 4.5 L18.8 13.2 L27.5 16 L18.8 18.8 L16 27.5 L13.2 18.8 L4.5 16 L13.2 13.2 Z" fill="currentColor" />
          </svg>
        </span>
        <span class="auth__brand-text">Voyage <em>AI</em></span>
      </RouterLink>
    </section>

    <!-- ==================== 右侧：表单 ==================== -->
    <section class="auth__panel">
      <div class="auth__panel-inner">
        <!-- 顶部工具条 -->
        <div class="auth__bar">
          <RouterLink to="/" class="auth__back">
            <TravelIcon name="arrow-left" :size="16" />
            回到首页
          </RouterLink>
          <button
            class="auth__theme"
            type="button"
            :title="isDark ? '切换到浅色' : '切换到深色'"
            :aria-label="isDark ? '切换到浅色' : '切换到深色'"
            @click="toggleTheme"
          >
            <TravelIcon :name="isDark ? 'sun' : 'moon'" :size="17" />
          </button>
        </div>

        <!-- 标题 -->
        <header class="auth__head">
          <Transition name="copy" mode="out-in">
            <div :key="mode">
              <h1 class="auth__title">
                {{ mode === 'login' ? '欢迎回来，旅人' : mode === 'register' ? '开启你的旅程' : '找回通行证' }}
              </h1>
              <p class="auth__sub">
                {{
                  mode === 'login'
                    ? '登录后继续你的行程规划'
                    : mode === 'register'
                      ? '注册一个账号，第一份行程马上就好'
                      : '验证邮箱后即可设置新密码'
                }}
              </p>
            </div>
          </Transition>
        </header>

        <!-- 滑动切换：登录 / 注册 -->
        <div class="auth__tabs" role="tablist" aria-label="登录或注册">
          <span class="auth__tabs-thumb" :style="{ transform: `translateX(${slideIndex * 100}%)` }"></span>
          <button
            class="auth__tab"
            :class="{ 'auth__tab--on': mode === 'login' }"
            role="tab"
            :aria-selected="mode === 'login'"
            @click="switchMode('login')"
          >
            登录
          </button>
          <button
            class="auth__tab"
            :class="{ 'auth__tab--on': mode === 'register' }"
            role="tab"
            :aria-selected="mode === 'register'"
            @click="switchMode('register')"
          >
            注册
          </button>
        </div>

        <!-- 表单区（滑轨）：两屏常驻以保证滑动过渡，非当前屏用 inert 移出焦点与无障碍树 -->
        <div class="auth__track-wrap">
          <div class="auth__track" :style="{ transform: `translateX(-${slideIndex * 50}%)` }">
            <!-- ======== 登录 ======== -->
            <div class="auth__pane" :inert="mode !== 'login' ? true : undefined" :aria-hidden="mode !== 'login'">
              <form class="form" @submit.prevent="handleLogin">
                <div class="field">
                  <label for="login-email">邮箱</label>
                  <div class="input-icon">
                    <TravelIcon name="mail" />
                    <input
                      id="login-email"
                      v-model="loginForm.email"
                      class="input"
                      type="email"
                      autocomplete="email"
                      placeholder="you@example.com"
                      :disabled="mode !== 'login'"
                      @input="clearError('email')"
                    />
                  </div>
                  <p v-if="errors.email" class="form-err">
                    <TravelIcon name="alert" :size="14" />{{ errors.email }}
                  </p>
                </div>

                <div class="field">
                  <label for="login-pwd">密码</label>
                  <div class="input-icon">
                    <TravelIcon name="lock" />
                    <input
                      id="login-pwd"
                      v-model="loginForm.password"
                      class="input input--pwd"
                      :type="showLoginPwd ? 'text' : 'password'"
                      autocomplete="current-password"
                      placeholder="至少 8 位"
                      :disabled="mode !== 'login'"
                      @input="clearError('password')"
                    />
                    <button
                      type="button"
                      class="pwd-toggle"
                      :aria-label="showLoginPwd ? '隐藏密码' : '显示密码'"
                      @click="showLoginPwd = !showLoginPwd"
                    >
                      <TravelIcon :name="showLoginPwd ? 'eye-off' : 'eye'" :size="16" />
                    </button>
                  </div>
                  <p v-if="errors.password" class="form-err">
                    <TravelIcon name="alert" :size="14" />{{ errors.password }}
                  </p>
                </div>

                <div class="form-row">
                  <label class="checkbox">
                    <input v-model="remember" type="checkbox" />
                    <span class="checkbox__box"><TravelIcon name="check" :size="12" /></span>
                    <span>{{ AUTH_COPY.rememberMe }}</span>
                  </label>
                  <RouterLink to="/forgot" class="link-btn">忘记密码？</RouterLink>
                </div>

                <p v-if="errors.form" class="form-err form-err--block">
                  <TravelIcon name="alert" :size="14" />{{ errors.form }}
                </p>

                <button class="btn btn-primary btn--block btn--lg" type="submit" :disabled="loading || mode !== 'login'">
                  <template v-if="loading">正在登机…</template>
                  <template v-else>
                    继续我的旅程
                    <TravelIcon name="arrow-right" :size="17" />
                  </template>
                </button>
              </form>
            </div>

            <!-- ======== 注册 ======== -->
            <div class="auth__pane" :inert="mode !== 'register' ? true : undefined" :aria-hidden="mode !== 'register'">
              <form class="form" @submit.prevent="handleRegister">
                <div class="field">
                  <label for="reg-email">邮箱</label>
                  <div class="input-icon">
                    <TravelIcon name="mail" />
                    <input
                      id="reg-email"
                      v-model="regForm.email"
                      class="input"
                      type="email"
                      autocomplete="email"
                      placeholder="用于接收验证码"
                      :disabled="mode !== 'register'"
                      @input="clearError('email')"
                    />
                  </div>
                  <p v-if="errors.email" class="form-err">
                    <TravelIcon name="alert" :size="14" />{{ errors.email }}
                  </p>
                </div>

                <div class="field">
                  <label for="reg-code">邮箱验证码</label>
                  <div class="code-row">
                    <div class="input-icon">
                      <TravelIcon name="shield" />
                      <input
                        id="reg-code"
                        v-model="regForm.code"
                        class="input"
                        maxlength="6"
                        inputmode="numeric"
                        placeholder="6 位数字"
                        :disabled="mode !== 'register'"
                        @input="clearError('code')"
                      />
                    </div>
                    <button
                      type="button"
                      class="btn btn-ghost btn--sm code-btn"
                      :disabled="countdown > 0 || mode !== 'register'"
                      @click="handleSendCode"
                    >
                      {{ countdown > 0 ? countdown + 's 后重发' : '获取验证码' }}
                    </button>
                  </div>
                  <p v-if="errors.code" class="form-err">
                    <TravelIcon name="alert" :size="14" />{{ errors.code }}
                  </p>
                </div>

                <div class="field">
                  <label for="reg-name">旅行昵称</label>
                  <div class="input-icon">
                    <TravelIcon name="user" />
                    <input
                      id="reg-name"
                      v-model="regForm.username"
                      class="input"
                      maxlength="10"
                      placeholder="2-10 个字符"
                      :disabled="mode !== 'register'"
                      @input="clearError('username')"
                    />
                  </div>
                  <p v-if="errors.username" class="form-err">
                    <TravelIcon name="alert" :size="14" />{{ errors.username }}
                  </p>
                </div>

                <div class="field">
                  <label for="reg-pwd">密码</label>
                  <div class="input-icon">
                    <TravelIcon name="lock" />
                    <input
                      id="reg-pwd"
                      v-model="regForm.password"
                      class="input input--pwd"
                      :type="showRegPwd ? 'text' : 'password'"
                      autocomplete="new-password"
                      placeholder="至少 8 位，建议数字 + 字母"
                      :disabled="mode !== 'register'"
                      @input="clearError('password')"
                    />
                    <button
                      type="button"
                      class="pwd-toggle"
                      :aria-label="showRegPwd ? '隐藏密码' : '显示密码'"
                      @click="showRegPwd = !showRegPwd"
                    >
                      <TravelIcon :name="showRegPwd ? 'eye-off' : 'eye'" :size="16" />
                    </button>
                  </div>
                  <p v-if="errors.password" class="form-err">
                    <TravelIcon name="alert" :size="14" />{{ errors.password }}
                  </p>
                </div>

                <p v-if="errors.form" class="form-err form-err--block">
                  <TravelIcon name="alert" :size="14" />{{ errors.form }}
                </p>

                <button class="btn btn-primary btn--block btn--lg" type="submit" :disabled="loading || mode !== 'register'">
                  <template v-if="loading">正在准备行囊…</template>
                  <template v-else>
                    注册并出发
                    <TravelIcon name="plane" :size="17" />
                  </template>
                </button>
              </form>
            </div>
          </div>
        </div>

        <!-- 第三方登录 -->
        <div class="divider"><span>或从别处登机</span></div>

        <div class="oauth">
          <button
            v-for="p in thirdParty"
            :key="p.name"
            type="button"
            class="oauth__btn"
            :aria-label="`使用 ${p.label} 登录`"
            @click="handleThirdParty"
          >
            <TravelIcon :name="p.name" :size="19" />
            <span>{{ p.label }}</span>
          </button>
        </div>

        <p class="auth__foot">
          {{ mode === 'login' ? '还没有账号？' : '已经有账号了？' }}
          <button type="button" class="link-btn" @click="switchMode(mode === 'login' ? 'register' : 'login')">
            {{ mode === 'login' ? '注册一个' : '直接登录' }}
          </button>
        </p>

        <p class="auth__legal">
          继续即表示同意
          <a href="#" @click.prevent>服务条款</a>
          与
          <a href="#" @click.prevent>隐私政策</a>
        </p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.auth {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1.06fr 0.94fr;
  position: relative;
  z-index: 1;
}

/* ==================== 左侧场景 ==================== */
.auth__scene {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 44px;
  min-height: 100vh;
}

.auth__scene-copy {
  position: relative;
  z-index: 2;
  max-width: 30em;
}

.scene-copy__eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--blue-700);
  margin-bottom: 14px;
}

.scene-copy__title {
  font-family: var(--font-display);
  font-size: clamp(1.7rem, 2.6vw, 2.4rem);
  font-weight: 700;
  line-height: 1.26;
  letter-spacing: -0.025em;
  color: var(--slate-800);
}

.scene-copy__desc {
  margin-top: 14px;
  font-size: 0.95rem;
  line-height: 1.75;
  color: var(--slate-600);
}

/* 文案切换 */
.copy-enter-active, .copy-leave-active { transition: opacity 0.45s ease, transform 0.45s cubic-bezier(0.2, 0.7, 0.2, 1); }
.copy-enter-from { opacity: 0; transform: translateY(12px); }
.copy-leave-to { opacity: 0; transform: translateY(-8px); }

/* 场景切换点 */
.scene-dots { display: flex; gap: 9px; margin-top: 28px; }

.scene-dot {
  width: 9px;
  height: 9px;
  padding: 0;
  border-radius: 999px;
  background: rgba(43, 108, 176, 0.24);
  transition: 0.3s;
}
.scene-dot:hover { background: rgba(43, 108, 176, 0.45); }
.scene-dot--on { width: 30px; background: var(--blue-600); }

/* 品牌 */
.auth__brand {
  position: absolute;
  top: 40px;
  left: 44px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 11px;
  color: var(--slate-800);
}

.auth__brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 11px;
  display: grid;
  place-items: center;
  background: var(--panel);
  border: 1px solid var(--border);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  color: var(--blue-700);
  box-shadow: var(--shadow-sm);
}
.auth__brand-mark svg { width: 22px; height: 22px; }

.auth__brand-text {
  font-family: var(--font-display);
  font-size: 1.08rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.auth__brand-text em { font-style: normal; color: var(--blue-500); }

/* ==================== 右侧表单 ==================== */
.auth__panel {
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 32px;
  overflow-y: auto;
}

.auth__panel-inner { width: min(408px, 100%); }

.auth__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 34px;
}

.auth__back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.86rem;
  color: var(--text2);
  transition: 0.18s;
}
.auth__back:hover { color: var(--blue-700); }

.auth__theme {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  display: grid;
  place-items: center;
  color: var(--text3);
  border: 1px solid transparent;
  transition: 0.18s;
}
.auth__theme:hover { background: var(--panel2); border-color: var(--border); color: var(--text); }

.auth__head { min-height: 84px; }

.auth__title { font-size: clamp(1.5rem, 2.4vw, 1.85rem); }

.auth__sub { color: var(--text2); font-size: 0.9rem; margin-top: 7px; }

/* ---- 滑动 tabs ---- */
.auth__tabs {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  padding: 4px;
  margin: 26px 0 24px;
  border-radius: 13px;
  background: var(--panel2);
  border: 1px solid var(--border);
}

.auth__tabs-thumb {
  position: absolute;
  top: 4px;
  left: 4px;
  width: calc(50% - 4px);
  height: calc(100% - 8px);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border);
  transition: transform 0.36s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.auth__tab {
  position: relative;
  z-index: 1;
  padding: 10px 6px;
  border-radius: 10px;
  font-size: 0.9rem;
  font-weight: 650;
  color: var(--text2);
  transition: color 0.24s;
}
.auth__tab--on { color: var(--text); }

/* ---- 滑轨 ---- */
.auth__track-wrap { overflow: hidden; }

.auth__track {
  display: flex;
  width: 200%;
  transition: transform 0.44s cubic-bezier(0.22, 0.8, 0.2, 1);
}

.auth__pane { width: 50%; flex-shrink: 0; padding-right: 2px; }
.auth__pane:last-child { padding-left: 2px; padding-right: 0; }

.form { display: flex; flex-direction: column; gap: 15px; }

/* 密码可见性切换 */
.input--pwd { padding-right: 42px; }

.pwd-toggle {
  position: absolute;
  right: 10px;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  color: var(--text3);
  transition: 0.18s;
}
.pwd-toggle:hover { color: var(--text); background: var(--panel2); }

.code-row { display: flex; gap: 10px; }
.code-row .input-icon { flex: 1; min-width: 0; }
.code-btn { flex-shrink: 0; white-space: nowrap; }

/* 记住我 / 忘记密码 */
.form-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.checkbox {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text2);
  cursor: pointer;
  user-select: none;
}
.checkbox input { position: absolute; opacity: 0; width: 0; height: 0; }

.checkbox__box {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  border: 1.5px solid var(--border);
  background: var(--panel);
  display: grid;
  place-items: center;
  color: #fff;
  transition: 0.18s;
  flex-shrink: 0;
}
.checkbox__box :deep(svg) { opacity: 0; transition: opacity 0.15s; }
.checkbox input:checked + .checkbox__box { background: var(--grad); border-color: transparent; }
.checkbox input:checked + .checkbox__box :deep(svg) { opacity: 1; }
.checkbox input:focus-visible + .checkbox__box { outline: 2px solid var(--primary); outline-offset: 2px; }

.link-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--blue-700);
  transition: 0.18s;
}
:root[data-theme='dark'] .link-btn { color: var(--blue-400); }
.link-btn:hover { text-decoration: underline; }
.link-btn--center { justify-content: center; margin-top: 2px; }

.form-err--block {
  padding: 9px 12px;
  border-radius: 10px;
  background: rgba(196, 69, 61, 0.08);
  border: 1px solid rgba(196, 69, 61, 0.22);
}

/* ---- 忘记密码步骤 ---- */
.steps {
  list-style: none;
  display: flex;
  gap: 10px;
  margin: 0 0 4px;
  padding: 0;
}

.steps__item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 11px;
  background: var(--panel2);
  border: 1px solid var(--border);
  font-size: 0.8rem;
  color: var(--text3);
  transition: 0.25s;
}
.steps__item--on { border-color: var(--blue-400); background: var(--grad-soft); color: var(--text); }
.steps__item--done { color: var(--green-600); }

.steps__no {
  width: 19px;
  height: 19px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 0.7rem;
  font-weight: 700;
  background: var(--panel);
  border: 1px solid var(--border);
  flex-shrink: 0;
}
.steps__item--on .steps__no { background: var(--grad); color: #fff; border-color: transparent; }
.steps__item--done .steps__no { background: var(--green-600); color: #fff; border-color: transparent; }

/* ---- 第三方 ---- */
.divider {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: 26px 0 18px;
  color: var(--text3);
  font-size: 0.78rem;
}
.divider::before, .divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

.oauth { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }

.oauth__btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 13px 6px 11px;
  border-radius: 13px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text2);
  font-size: 0.76rem;
  font-weight: 600;
  transition: 0.2s;
}
.oauth__btn:hover {
  transform: translateY(-2px);
  border-color: var(--blue-400);
  color: var(--blue-800);
  box-shadow: var(--shadow-sm);
  background: var(--blue-50);
}
:root[data-theme='dark'] .oauth__btn:hover { color: var(--blue-300); background: var(--blue-900); border-color: var(--blue-700); }

.auth__foot {
  margin-top: 22px;
  text-align: center;
  font-size: 0.85rem;
  color: var(--text2);
}

.auth__legal {
  margin-top: 20px;
  text-align: center;
  font-size: 0.72rem;
  color: var(--text3);
}
.auth__legal a { color: var(--text2); text-decoration: underline; text-underline-offset: 2px; }
.auth__legal a:hover { color: var(--blue-700); }

/* ==================== 响应式 ==================== */
@media (max-width: 1024px) {
  .auth { grid-template-columns: 1fr; }
  .auth__scene { display: none; }
  .auth__panel { padding: 32px 24px; }
}

/* 移动端：顶部旅行画面 + 底部抽屉式表单 */
@media (max-width: 720px) {
  .auth {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }

  .auth__scene {
    display: flex;
    position: relative;
    min-height: 246px;
    flex: 0 0 auto;
    padding: 26px 22px 30px;
    border-radius: 0 0 26px 26px;
  }

  .auth__brand { position: static; margin-bottom: auto; }
  .scene-copy__title { font-size: 1.45rem; }
  .scene-copy__desc { font-size: 0.85rem; margin-top: 8px; }
  .scene-dots { margin-top: 18px; }

  .auth__panel {
    flex: 1;
    align-items: flex-start;
    margin-top: -22px;
    padding: 26px 20px 40px;
    background: var(--bg);
    border-radius: 24px 24px 0 0;
    position: relative;
    z-index: 2;
    box-shadow: 0 -12px 34px rgba(7, 27, 51, 0.16);
  }

  .auth__bar { margin-bottom: 20px; }
  .auth__head { min-height: 0; }
  .auth__title { font-size: 1.35rem; }
}
</style>
