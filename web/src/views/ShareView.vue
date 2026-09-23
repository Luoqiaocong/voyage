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
import BackToTop from '@/components/BackToTop.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { groupBySlot, sortGroupsBySlot } from '@/utils/messageParse'
import { preferenceTone } from '@/utils/preferenceTone'
import { parseTransport } from '@/utils/transportParse'

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
const shareTransport = computed(() => parseTransport(plan.value?.transport))

const kindLabel: Record<string, string> = {
  attraction: '景点',
  restaurant: '美食',
  hotel: '住宿',
  transport: '交通',
  rest: '休整'
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

function activityCost(a: ItineraryActivity): string {
  return a.cost ? `¥${a.cost}` : '免费'
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
            aria-label="访问密码"
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
              <li>{{ plan.days }} 天</li>
              <li v-if="plan.budget != null">预算 ¥{{ plan.budget }}</li>
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

        <section class="ov">
          <div class="ov__card">
            <p class="ov__label"><TravelIcon name="train" :size="14" />往返交通</p>
            <template v-if="shareTransport.primary">
              <div class="ticket">
                <div class="ticket__route">
                  <span v-if="shareTransport.primary.from" class="ticket__station">{{ shareTransport.primary.from }}</span>
                  <TravelIcon name="arrow-right" :size="13" class="ticket__arrow" />
                  <span v-if="shareTransport.primary.to" class="ticket__station">{{ shareTransport.primary.to }}</span>
                  <span v-if="shareTransport.primary.trainNo" class="ticket__no">{{ shareTransport.primary.trainNo }}</span>
                  <span v-if="shareTransport.primary.recommended" class="ticket__rec">推荐</span>
                </div>
                <div class="ticket__facts">
                  <span v-if="shareTransport.primary.depart" class="ticket__time">{{ shareTransport.primary.depart }} – {{ shareTransport.primary.arrive }}</span>
                  <span v-if="shareTransport.primary.seat" class="ticket__seat">{{ shareTransport.primary.seat }}</span>
                  <span v-if="shareTransport.primary.price" class="ticket__price">{{ shareTransport.primary.price }}</span>
                </div>
                <ul v-if="shareTransport.alternatives.length" class="ticket__alts">
                  <li v-for="(alt, ai) in shareTransport.alternatives" :key="ai" class="ticket__alt">
                    <span class="ticket__alt-label">备选</span>
                    <span v-if="alt.trainNo" class="ticket__alt-no">{{ alt.trainNo }}</span>
                    <span v-if="alt.depart" class="ticket__alt-time">{{ alt.depart }}–{{ alt.arrive }}</span>
                    <span v-if="alt.to" class="ticket__alt-to">{{ alt.to }}</span>
                    <span v-if="alt.price" class="ticket__alt-price">{{ alt.price }}</span>
                  </li>
                </ul>
              </div>
            </template>
            <p v-else class="ov__plain">{{ plan.transport || '未指定' }}</p>
          </div>

          <div v-if="plan.accommodation" class="ov__card">
            <p class="ov__label"><TravelIcon name="bed" :size="14" />住宿</p>
            <p class="ov__stay-name">{{ plan.accommodation.name }}</p>
            <p v-if="plan.accommodation.description" class="ov__stay-desc">{{ plan.accommodation.description }}</p>
            <p class="ov__stay-facts">
              <span v-if="plan.accommodation.cost" class="ov__cost">¥{{ plan.accommodation.cost }} / 晚</span>
              <span v-if="plan.accommodation.note" class="ov__stay-note">{{ plan.accommodation.note }}</span>
            </p>
          </div>

          <div v-if="plan.preferences?.length" class="ov__card">
            <p class="ov__label"><TravelIcon name="star" :size="14" />偏好</p>
            <div class="ov__tags">
              <span
                v-for="p in plan.preferences"
                :key="p"
                class="ptag"
                :class="`ptag--${preferenceTone(p)}`"
              >{{ p }}</span>
            </div>
          </div>
        </section>

        <section v-for="day in plan.daily_plans" :key="day.day_no" class="card share__day">
          <header class="share__day-head">
            <span class="day__no">Day {{ day.day_no }}</span>
            <div>
              <h2>{{ day.theme }}</h2>
              <span class="share__day-date">{{ day.date || '第 ' + day.day_no + ' 天' }}</span>
            </div>
          </header>

          <div class="day__slots">
            <section
              v-for="(grp, gi) in sortGroupsBySlot(groupBySlot(day.activities, (a: ItineraryActivity) => a.time_slot))"
              :key="gi"
              class="slotgrp"
            >
              <h4 v-if="grp.label" class="slotgrp__label">{{ grp.label }}</h4>
              <ul class="acts">
                <li v-for="(a, i) in grp.items" :key="i" class="acts__item">
                  <span class="badge-kind badge-tag">{{ kindLabel[a.kind] ?? a.kind }}</span>
                  <div class="acts__body">
                    <p class="acts__name">{{ a.name }}</p>
                    <p class="acts__desc">{{ a.description }}</p>
                    <p class="acts__meta">
                      <span v-if="a.duration_hours">约 {{ a.duration_hours }} 小时</span>
                      <span :class="{ 'acts__free': !a.cost }">{{ activityCost(a) }}</span>
                      <span v-if="a.note" class="acts__note">{{ a.note }}</span>
                    </p>
                  </div>
                </li>
              </ul>
            </section>
          </div>
          <p v-if="day.summary" class="share__summary">{{ day.summary }}</p>
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

    <!--
      返回顶部：多天行程的分享页会很长，浏览者常需要回到顶部看概要。
      这里是**公开页面**，没有导航栏 —— 组件用 fixed 定位，不依赖任何上层结构。
    -->
    <BackToTop />
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

.share__day, .share__tips { padding: 20px 22px; margin-bottom: 16px; }
.share__panel-title { font-size: 0.95rem; font-weight: 700; margin-bottom: 10px; }

.ov {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.ov__card {
  padding: 16px 18px;
  border-radius: 14px;
  background: var(--panel);
  border: 1px solid var(--border);
}
.ov__label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 650;
  color: var(--text3);
  margin-bottom: 8px;
}
.ov__stay-name { font-size: 1rem; font-weight: 700; }
.ov__stay-desc { font-size: 0.84rem; color: var(--text2); margin-top: 4px; }
.ov__stay-facts { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; font-size: 0.82rem; color: var(--text2); }
.ov__cost { font-weight: 650; color: var(--text); }
.ov__plain { font-size: 0.88rem; color: var(--text2); line-height: 1.6; }
.ov__tags { display: flex; flex-wrap: wrap; gap: 6px; }

.ticket { display: flex; flex-direction: column; gap: 6px; }
.ticket__route { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.ticket__station { font-weight: 700; }
.ticket__arrow { opacity: 0.7; }
.ticket__no { font-family: var(--mono); font-weight: 650; }
.ticket__rec {
  font-size: 0.68rem;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--gold-soft);
  color: var(--gold-600);
}
.ticket__facts { display: flex; flex-wrap: wrap; gap: 8px; font-size: 0.79rem; color: var(--text2); }
.ticket__time { font-family: var(--mono); }
.ticket__price { margin-left: auto; font-weight: 750; color: var(--text); }
.ticket__alts {
  list-style: none;
  margin: 8px 0 0;
  padding: 8px 0 0;
  border-top: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ticket__alt { display: flex; flex-wrap: wrap; gap: 8px; font-size: 0.76rem; color: var(--text3); }
.ticket__alt-label {
  font-size: 0.68rem;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--panel);
  border: 1px solid var(--border);
}
.ticket__alt-no, .ticket__alt-time { font-family: var(--mono); }

.day__no {
  font-family: var(--display);
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--primary);
  padding: 2px 10px;
  border: 1.5px solid var(--primary);
  border-radius: 10px;
}
.share__day-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--hairline);
  margin-bottom: 14px;
}
.share__day-head h2 { font-size: 1.1rem; font-weight: 700; }
.share__day-date { font-size: 0.78rem; color: var(--text3); font-family: var(--mono); }
.share__summary {
  margin-top: 12px;
  font-size: 0.84rem;
  color: var(--text2);
  line-height: 1.6;
  border-top: 1px dashed var(--line);
  padding-top: 10px;
}

.day__slots { display: flex; flex-direction: column; gap: 16px; }
.slotgrp { display: flex; flex-direction: column; gap: 8px; }
.slotgrp__label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--blue-700);
}
.slotgrp__label::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, var(--blue-200), transparent);
}

.acts { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.acts__item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
}
.acts__name { font-weight: 600; font-size: 0.95rem; }
.acts__desc { font-size: 0.83rem; color: var(--text2); margin-top: 3px; line-height: 1.6; }
.acts__meta { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 6px; font-size: 0.8rem; color: var(--text3); }
.acts__free { color: var(--success); }
.acts__note { font-style: italic; }

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

@media (max-width: 720px) {
  .share { padding: 24px 0 56px; }
  .share__head { flex-direction: column; align-items: stretch; }
  .share__actions { flex-wrap: wrap; }
  .ov { grid-template-columns: 1fr; }
  .share__form { flex-direction: column; }
  .acts__item { grid-template-columns: 1fr; gap: 6px; }
  .share__day-head { align-items: flex-start; }
}
</style>
