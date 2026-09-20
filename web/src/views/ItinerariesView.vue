<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import BackToTop from '@/components/BackToTop.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import { listItineraries, type ItineraryDetail } from '@/api/itinerary'
import { useUiStore } from '@/stores/ui'
import { formatDateTime } from '@/utils/datetime'
import { PAGE_COPY } from '@/constants/copy'

const router = useRouter()
const ui = useUiStore()
const items = ref<ItineraryDetail[]>([])
const loading = ref(true)

function go(id: number) {
  router.push(`/itineraries/${id}`)
}

onMounted(async () => {
  try {
    items.value = await listItineraries()
  } catch (e: any) {
    ui.toast(e?.message ?? '行程列表加载失败', 'error')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="it-page">
    <AppNavbar />
    <main id="main" tabindex="-1">
      <div class="container page">
        <div class="page-head">
          <div>
            <p class="eyebrow">My Routes</p>
            <h1 class="page-title">我的行程</h1>
            <p class="section-sub">AI 从对话里替你整理出的结构化出行方案</p>
          </div>
          <RouterLink to="/chat" class="btn btn-primary">
            <TravelIcon name="plane" :size="17" />
            去规划新的旅程
          </RouterLink>
        </div>

        <!-- 加载态：旅行语气 -->
        <div v-if="loading" class="empty">
          <span class="loader-route" aria-hidden="true">
            <svg viewBox="0 0 120 24" fill="none">
              <path id="loadPath" d="M2 20 C 30 4, 60 4, 118 20" stroke="currentColor" stroke-width="1.6" stroke-dasharray="3 6" stroke-linecap="round" />
              <circle r="4" fill="currentColor">
                <animateMotion dur="1.5s" repeatCount="indefinite">
                  <mpath href="#loadPath" />
                </animateMotion>
              </circle>
            </svg>
          </span>
          <p>{{ PAGE_COPY.itinerariesLoading }}</p>
        </div>

        <!-- 空状态：邀请再次出发 -->
        <div v-else-if="items.length === 0" class="card empty empty--rich">
          <span class="empty__art" aria-hidden="true">
            <svg viewBox="0 0 120 96" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10 78 L 40 34 L 60 62 L 78 38 L 110 78 Z" />
              <circle cx="92" cy="22" r="9" />
              <path d="M14 88 h 92" stroke-dasharray="4 7" />
              <path d="M30 88 C 50 70, 70 70, 96 84" stroke-dasharray="2 7" opacity="0.6" />
            </svg>
          </span>
          <h3>{{ PAGE_COPY.itinerariesEmptyTitle }}</h3>
          <p>{{ PAGE_COPY.itinerariesEmptyDesc }}</p>
          <RouterLink to="/chat" class="btn btn-primary btn-gap">
            <TravelIcon name="compass" :size="17" />
            {{ PAGE_COPY.itinerariesEmptyCta }}
          </RouterLink>
        </div>

        <div v-else class="it-grid">
          <article
            v-for="it in items"
            :key="it.id"
            class="card it-card"
            tabindex="0"
            @click="go(it.id)"
            @keydown.enter="go(it.id)"
          >
            <!-- 票根顶部：目的地大字 + 天数徽标 -->
            <div class="it-card__top">
              <span class="it-card__dest">{{ it.plan.destination }}</span>
              <span class="badge-kind badge-tag">{{ it.plan.days }} 天</span>
            </div>

            <div class="it-card__meta">
              <span v-if="it.plan.budget != null" class="chip">
                <TravelIcon name="passport" :size="13" />预算 ¥{{ it.plan.budget }}
              </span>
              <span v-if="it.plan.transport" class="chip">
                <TravelIcon name="train" :size="13" />{{ it.plan.transport }}
              </span>
              <span v-for="p in it.plan.preferences.slice(0, 3)" :key="p" class="chip">{{ p }}</span>
            </div>

            <div class="it-card__foot">
              <span class="it-card__date">
                <TravelIcon name="clock" :size="13" />
                更新于 {{ formatDateTime(it.updated_at) }}
              </span>
              <span class="it-card__go">
                查看行程
                <TravelIcon name="arrow-right" :size="15" />
              </span>
            </div>
          </article>
        </div>
      </div>
    </main>

    <!-- 返回顶部：行程多时列表很长，符合「已滚过一屏」才出现的自身判断 -->
    <BackToTop />
  </div>
</template>

<style scoped>
.it-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

.it-card {
  position: relative;
  padding: 22px 22px 18px;
  cursor: pointer;
  transition: transform 0.22s cubic-bezier(0.2, 0.7, 0.2, 1), box-shadow 0.22s, border-color 0.22s;
  overflow: hidden;
}

/* 顶部渐变纸条：像行程票据的抬头 */
.it-card::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--grad);
  opacity: 0;
  transition: opacity 0.25s;
}
.it-card:hover::before, .it-card:focus-visible::before { opacity: 1; }

.it-card:hover, .it-card:focus-visible {
  transform: translateY(-5px);
  box-shadow: var(--shadow-lift);
  border-color: transparent;
}

.btn-gap { margin-top: 18px; }

.it-card__top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }

.it-card__dest {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.it-card__meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.it-card__meta .chip { gap: 5px; }

.it-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--border);
}

.it-card__date {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text3);
  font-size: 0.76rem;
}

.it-card__go {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.8rem;
  font-weight: 650;
  color: var(--text3);
  transition: color 0.2s, gap 0.2s;
}
.it-card:hover .it-card__go { color: var(--blue-700); gap: 8px; }
:root[data-theme='dark'] .it-card:hover .it-card__go { color: var(--blue-400); }

/* ---- 加载态：航线上的光点 ---- */
.loader-route {
  display: block;
  width: 120px;
  height: 24px;
  margin: 0 auto 14px;
  color: var(--blue-600);
}

/* ---- 空状态插画 ---- */
.empty--rich { padding: 56px 24px; }

.empty__art {
  display: block;
  width: 128px;
  height: 102px;
  margin: 0 auto 20px;
  color: var(--blue-600);
  opacity: 0.85;
}
.empty__art svg { width: 100%; height: 100%; }

.empty--rich h3 { font-family: var(--font-display); font-size: 1.3rem; }
.empty--rich p { max-width: 32em; margin: 8px auto 0; line-height: 1.75; }
</style>

