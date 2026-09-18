<script setup lang="ts">
/**
 * 公开分享页（/share/:token）——无需登录。
 *
 * 流程：先调预检接口判断链接状态与是否需要密码，再据此展示密码输入或行程内容。
 * 后端刻意让预检返回轻量预览（目的地/天数），这样即使需要密码，
 * 用户也能先看到「这是哪份行程」再决定是否输入密码。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  copySharedItinerary,
  inspectShare,
  openSharedItinerary,
  shareReasonLabel,
  type ShareCheck,
  type SharedItinerary
} from '@/api/share'
import type { ItineraryActivity } from '@/api/itinerary'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const ui = useUiStore()

const token = String(route.params.token ?? '')

const loading = ref(true)
const check = ref<ShareCheck | null>(null)
const data = ref<SharedItinerary | null>(null)
const password = ref('')
const submitting = ref(false)
const copying = ref(false)
const errorText = ref('')

const plan = computed(() => data.value?.plan ?? null)

const slotLabel: Record<string, string> = { morning: '上午', afternoon: '下午', evening: '晚上' }
const kindLabel: Record<string, string> = {
  attraction: '景点',
  restaurant: '餐饮',
  hotel: '住宿',
  transport: '交通',
  rest: '休息'
}

async function bootstrap() {
  loading.value = true
  errorText.value = ''
  try {
    check.value = await inspectShare(token)
    if (!check.value.available) {
      errorText.value = shareReasonLabel(check.value.reason)
      return
    }
    // 无需密码则直接取内容
    if (!check.value.requires_password) {
      await fetchItinerary()
    }
  } catch (e: any) {
    errorText.value = e?.message ?? '分享链接加载失败'
  } finally {
    loading.value = false
  }
}

async function fetchItinerary() {
  data.value = await openSharedItinerary(token, password.value || null)
}

async function submitPassword() {
  if (!password.value.trim()) return
  submitting.value = true
  errorText.value = ''
  try {
    await fetchItinerary()
  } catch (e: any) {
    // 密码错误时保留输入框让用户重试，而不是整页报错
    errorText.value = e?.message ?? '密码校验失败'
  } finally {
    submitting.value = false
  }
}

async function copyToMine() {
  if (!user.isLoggedIn) {
    // 复制需要登录：带上回跳地址，登录后回到本页
    router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  copying.value = true
  try {
    const res = await copySharedItinerary(token, password.value || null)
    ui.toast('已复制到你的行程', 'success')
    router.push(`/itineraries/${res.id}`)
  } catch (e: any) {
    ui.toast(e?.message ?? '复制失败', 'error')
  } finally {
    copying.value = false
  }
}

/**
 * 活动的费用文案。
 *
 * cost 是整数、单位元，**0 表示免费**（后端与 ItineraryDetailView 都按此约定）。
 * 原先写 `a.cost ? ... : ''`，0 是假值 → 免费活动返回空串，
 * 模板里的 v-if 便整个不渲染，看起来像费用数据缺失。
 * 现改为明确返回「免费」。
 */
function activityCost(a: ItineraryActivity): string {
  return a.cost ? `约 ${a.cost} 元` : '免费'
}

onMounted(bootstrap)
</script>

<template>
  <div class="share page">
    <div class="container">
      <!-- 加载中 -->
      <p v-if="loading" class="share__loading">正在打开分享…</p>

      <!-- 链接不可用 -->
      <div v-else-if="!data && !check?.available" class="card share__gate">
        <h1 class="share__gate-title">链接不可用</h1>
        <p class="share__gate-text">{{ errorText || '该分享链接不存在或已失效' }}</p>
        <RouterLink to="/" class="btn btn-ghost btn--sm">返回首页</RouterLink>
      </div>

      <!-- 需要密码 -->
      <div v-else-if="!data && check?.requires_password" class="card share__gate">
        <span class="share__lock" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <rect x="4" y="10" width="16" height="10" rx="2" />
            <path d="M8 10V7a4 4 0 0 1 8 0v3" />
          </svg>
        </span>
        <h1 class="share__gate-title">该分享需要访问密码</h1>
        <p v-if="check?.destination" class="share__gate-text">
          「{{ check.destination }}」{{ check.days }} 天行程 —— 输入密码后查看完整安排
        </p>

        <form class="share__form" @submit.prevent="submitPassword">
          <input
            v-model="password"
            class="input"
            type="password"
            placeholder="请输入访问密码"
            autocomplete="off"
          />
          <button class="btn btn-primary" type="submit" :disabled="submitting || !password.trim()">
            {{ submitting ? '校验中…' : '查看行程' }}
          </button>
        </form>
        <p v-if="errorText" class="share__error">{{ errorText }}</p>
      </div>

      <!-- 行程内容 -->
      <template v-else-if="plan && data">
        <header class="share__head">
          <div>
            <p class="share__eyebrow">
              来自 {{ data.owner_name || '一位旅行者' }} 的分享
              <span class="share__views">· 已被查看 {{ data.view_count }} 次</span>
            </p>
            <h1 class="share__title">{{ plan.destination }} · {{ plan.days }} 天行程</h1>
            <ul class="share__meta">
              <!-- 用 != null 而非真值判断：预算为 0 时也应展示，与列表页口径一致 -->
              <li v-if="plan.budget != null">预算 {{ plan.budget }} 元</li>
              <li v-if="plan.transport">交通：{{ plan.transport }}</li>
              <li v-if="plan.preferences?.length">偏好：{{ plan.preferences.join('、') }}</li>
            </ul>
          </div>
          <div class="share__actions">
            <button
              v-if="data.allow_copy"
              class="btn btn-primary btn--sm"
              :disabled="copying"
              @click="copyToMine"
            >
              {{ copying ? '复制中…' : user.isLoggedIn ? '复制到我的行程' : '登录后复制' }}
            </button>
            <span v-if="!data.allow_copy" class="share__badge">分享者未开放复制</span>
            <span v-if="data.allow_edit" class="share__badge share__badge--edit">可编辑</span>
          </div>
        </header>

        <div v-if="plan.accommodation" class="card share__panel">
          <h2 class="share__panel-title">住宿</h2>
          <p class="share__acc">
            <strong>{{ plan.accommodation.name }}</strong>
            <span v-if="plan.accommodation.description"> — {{ plan.accommodation.description }}</span>
          </p>
          <p v-if="plan.accommodation.note" class="share__note">⚠️ {{ plan.accommodation.note }}</p>
        </div>

        <section v-for="day in plan.daily_plans" :key="day.day_no" class="card share__day">
          <header class="share__day-head">
            <h2>第 {{ day.day_no }} 天 · {{ day.theme }}</h2>
            <span v-if="day.date" class="share__day-date">{{ day.date }}</span>
          </header>
          <p class="share__summary">{{ day.summary }}</p>

          <ul class="acts">
            <li v-for="(a, i) in day.activities" :key="i" class="acts__item">
              <span class="acts__slot">{{ slotLabel[a.time_slot] ?? a.time_slot }}</span>
              <div class="acts__body">
                <p class="acts__name">
                  {{ a.name }}
                  <span class="acts__kind">{{ kindLabel[a.kind] ?? a.kind }}</span>
                  <span v-if="a.duration_hours" class="acts__dur">{{ a.duration_hours }} 小时</span>
                  <span v-if="activityCost(a)" class="acts__cost">{{ activityCost(a) }}</span>
                </p>
                <p class="acts__desc">{{ a.description }}</p>
                <p v-if="a.note" class="share__note">⚠️ {{ a.note }}</p>
              </div>
            </li>
          </ul>
        </section>

        <section v-if="plan.tips?.length" class="card share__tips">
          <h2 class="share__panel-title">出行提醒</h2>
          <ul>
            <li v-for="(t, i) in plan.tips" :key="i">{{ t }}</li>
          </ul>
        </section>

        <p class="share__foot">由 Voyage 生成 · 内容以分享者保存的版本为准</p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.share { padding: 40px 0 72px; }
.share__loading { text-align: center; color: var(--text2); padding: 60px 0; }

/* 门槛页（不可用 / 需要密码） */
.share__gate {
  max-width: 420px;
  margin: 40px auto;
  padding: 36px 30px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.share__lock { width: 40px; height: 40px; color: var(--prim); }
.share__lock svg { width: 100%; height: 100%; }
.share__gate-title { font-size: 1.2rem; font-family: var(--font-display); }
.share__gate-text { font-size: 0.88rem; color: var(--text2); line-height: 1.6; }
.share__form { display: flex; gap: 10px; width: 100%; margin-top: 8px; }
.share__form .input { flex: 1; }
.share__error { color: var(--danger); font-size: 0.82rem; }

/* 内容页 */
.share__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 24px;
}
.share__eyebrow { font-size: 0.8rem; color: var(--text3); margin-bottom: 6px; }
.share__views { color: var(--text3); }
.share__title { font-size: clamp(1.5rem, 2.6vw, 2rem); font-family: var(--font-display); }
.share__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin-top: 8px;
  font-size: 0.84rem;
  color: var(--text2);
}
.share__actions { display: flex; align-items: center; gap: 10px; }
.share__badge {
  font-size: 0.74rem;
  padding: 3px 9px;
  border-radius: 6px;
  background: var(--surface-soft);
  color: var(--text2);
}
.share__badge--edit { background: var(--primary-soft); color: var(--prim); }

.share__panel, .share__day, .share__tips { padding: 20px 22px; margin-bottom: 16px; }
.share__panel-title { font-size: 0.95rem; font-weight: 700; margin-bottom: 10px; }
.share__acc { font-size: 0.9rem; }
.share__note { font-size: 0.8rem; color: var(--danger); margin-top: 4px; }

.share__day-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--hairline);
  margin-bottom: 10px;
}
.share__day-head h2 { font-size: 1rem; font-weight: 700; }
.share__day-date { font-size: 0.78rem; color: var(--text3); font-family: var(--mono); }
.share__summary { font-size: 0.84rem; color: var(--text2); margin-bottom: 14px; line-height: 1.6; }

.acts { display: flex; flex-direction: column; }
.acts__item {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px dashed var(--hairline);
}
.acts__item:last-child { border-bottom: none; }
.acts__slot {
  font-size: 0.78rem;
  color: var(--prim);
  font-weight: 650;
}
.acts__name { font-weight: 600; font-size: 0.9rem; display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }
.acts__kind {
  font-size: 0.7rem;
  font-weight: 500;
  padding: 1px 7px;
  border-radius: 5px;
  background: var(--surface-soft);
  color: var(--text2);
}
.acts__dur, .acts__cost { font-size: 0.75rem; color: var(--text3); font-weight: 500; }
.acts__cost { color: var(--gold-600); }
.acts__desc { font-size: 0.83rem; color: var(--text2); margin-top: 3px; line-height: 1.6; }

.share__tips ul { display: flex; flex-direction: column; gap: 8px; }
.share__tips li {
  font-size: 0.85rem;
  color: var(--text2);
  padding-left: 16px;
  position: relative;
  line-height: 1.6;
}
.share__tips li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--prim);
}

.share__foot { text-align: center; font-size: 0.78rem; color: var(--text3); margin-top: 24px; }

@media (max-width: 620px) {
  .share__form { flex-direction: column; }
  .acts__item { grid-template-columns: 1fr; gap: 4px; }
}
</style>
