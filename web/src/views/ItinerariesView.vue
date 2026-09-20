<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import BackToTop from '@/components/BackToTop.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import { listItineraries, type ItineraryDetail } from '@/api/itinerary'
import { useUiStore } from '@/stores/ui'
import { formatDateTime } from '@/utils/datetime'
import { PAGE_COPY } from '@/constants/copy'
import { preferenceTone } from '@/utils/preferenceTone'
import { parseTransport } from '@/utils/transportParse'

const router = useRouter()
const ui = useUiStore()
const items = ref<ItineraryDetail[]>([])
const loading = ref(true)

/**
 * 每张卡片的解析结果。
 *
 * 在卡片渲染前一次性算好，而不是把 parseTransport 写进模板里调用 ——
 * 模板每次重渲染都会重新解析，而列表可能有几十条。
 */
const cards = computed(() =>
  items.value.map((it) => ({
    it,
    transport: parseTransport(it.plan.transport),
    // 只展示前 4 个标签：再多会挤成两行，反而看不清重点
    prefs: (it.plan.preferences ?? []).slice(0, 4),
    extraPrefs: Math.max((it.plan.preferences ?? []).length - 4, 0)
  }))
)

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
  <div>
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
            v-for="c in cards"
            :key="c.it.id"
            class="card it-card"
            tabindex="0"
            @click="go(c.it.id)"
            @keydown.enter="go(c.it.id)"
          >
            <!-- ── 头部：目的地为视觉主体，天数与预算退居右侧 ── -->
            <header class="it-card__head">
              <div class="it-card__where">
                <h3 class="it-card__dest">{{ c.it.plan.destination }}</h3>
                <p class="it-card__sub">
                  <span class="it-card__days">{{ c.it.plan.days }} 天</span>
                  <template v-if="c.it.plan.budget != null">
                    <span class="it-card__dot" aria-hidden="true">·</span>
                    <span class="it-card__budget">预算 ¥{{ c.it.plan.budget }}</span>
                  </template>
                </p>
              </div>
              <span class="it-card__stamp" aria-hidden="true">
                <TravelIcon name="compass" :size="18" />
              </span>
            </header>

            <!--
              ── 车票信息块 ──
              只渲染解析出来的字段；解析不到就整块不出现，
              不留空占位（transport 是自由文本，字段完整度无法保证）。
            -->
            <section
              v-if="c.transport.primary"
              class="ticket"
              :aria-label="`交通：${c.transport.raw}`"
            >
              <div class="ticket__route">
                <span v-if="c.transport.primary.from" class="ticket__station">
                  {{ c.transport.primary.from }}
                </span>
                <TravelIcon name="arrow-right" :size="13" class="ticket__arrow" />
                <span v-if="c.transport.primary.to" class="ticket__station">
                  {{ c.transport.primary.to }}
                </span>
                <!-- 车次是这块的「编号」，用等宽字突出 -->
                <span v-if="c.transport.primary.trainNo" class="ticket__no">
                  {{ c.transport.primary.trainNo }}
                </span>
                <span
                  v-if="c.transport.primary.recommended"
                  class="ticket__rec"
                >推荐</span>
              </div>

              <div class="ticket__facts">
                <span
                  v-if="c.transport.primary.depart"
                  class="ticket__time"
                >{{ c.transport.primary.depart }} – {{ c.transport.primary.arrive }}</span>
                <span v-if="c.transport.primary.seat" class="ticket__seat">
                  {{ c.transport.primary.seat }}
                </span>
                <span v-if="c.transport.primary.price" class="ticket__price">
                  {{ c.transport.primary.price }}
                </span>
              </div>

              <!-- 备选车次：整体弱化（更小、更淡），只保留车次与时刻 -->
              <ul v-if="c.transport.alternatives.length" class="ticket__alts">
                <li
                  v-for="(alt, ai) in c.transport.alternatives"
                  :key="ai"
                  class="ticket__alt"
                >
                  <span class="ticket__alt-label">备选</span>
                  <span v-if="alt.trainNo" class="ticket__alt-no">{{ alt.trainNo }}</span>
                  <span v-if="alt.depart" class="ticket__alt-time">
                    {{ alt.depart }}–{{ alt.arrive }}
                  </span>
                  <span v-if="alt.to" class="ticket__alt-to">{{ alt.to }}</span>
                  <span v-if="alt.price" class="ticket__alt-price">{{ alt.price }}</span>
                </li>
              </ul>
            </section>

            <!-- 认不出结构时的兜底：原样展示文本，不丢信息 -->
            <p v-else-if="c.transport.raw" class="ticket ticket--plain">
              <TravelIcon name="train" :size="14" />
              {{ c.transport.raw }}
            </p>

            <!-- ── 主题标签：按语义着色 ── -->
            <div v-if="c.prefs.length" class="it-card__prefs">
              <span
                v-for="p in c.prefs"
                :key="p"
                class="ptag"
                :class="`ptag--${preferenceTone(p)}`"
              >{{ p }}</span>
              <span v-if="c.extraPrefs" class="ptag ptag--plain">+{{ c.extraPrefs }}</span>
            </div>

            <footer class="it-card__foot">
              <span class="it-card__date">
                <TravelIcon name="clock" :size="13" />
                {{ formatDateTime(c.it.updated_at) }}
              </span>
              <span class="it-card__go">
                查看行程
                <TravelIcon name="arrow-right" :size="15" />
              </span>
            </footer>
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

.it-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

/* 左侧信息列：min-width:0 是必须的。
   flex 子项默认 min-width:auto，长目的地名（如「两江四湖·象鼻山」）
   会把右侧印章挤出卡片，而不是正常换行。 */
.it-card__where {
  min-width: 0;
  flex: 1;
}

.it-card__dest {
  font-family: var(--font-display);
  font-size: 1.55rem;
  font-weight: 750;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: var(--text);
}

/* 天数与预算合成一行次级信息：比原来「大字 + 徽标」的主次更清楚 */
.it-card__sub {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 7px;
  font-size: 0.82rem;
  color: var(--text2);
}
.it-card__days {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--blue-50);
  color: var(--blue-700);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.01em;
}
:root[data-theme='dark'] .it-card__days {
  background: rgba(37, 99, 235, 0.18);
  color: var(--blue-300);
}
.it-card__dot { color: var(--text3); }
.it-card__budget { font-weight: 550; }

/* 右上角的罗盘印章：给卡片一个视觉锚点，避免右侧空荡 */
.it-card__stamp {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 12px;
  background: var(--blue-50);
  color: var(--blue-600);
  transition: transform 0.3s cubic-bezier(0.2, 0.7, 0.2, 1), background-color 0.25s;
}
:root[data-theme='dark'] .it-card__stamp {
  background: rgba(37, 99, 235, 0.16);
  color: var(--blue-400);
}
/* 悬停时印章轻微转向，作为「这张卡活着」的反馈 */
.it-card:hover .it-card__stamp,
.it-card:focus-visible .it-card__stamp {
  transform: rotate(-12deg) scale(1.06);
  background: var(--blue-100);
}

/* ============================================================
   车票信息块
   ------------------------------------------------------------
   设计思路：把它做成一张**票据**而不是一排 chip。
   · 左侧竖线（color bar）区分「这是另一种信息」，与正文拉开
   · 主车次占一行：站名 → 站名 + 车次（等宽字）+ 「推荐」小标签
   · 时刻 / 座别 / 价格 作为次级事实排在第二行，字号更小、颜色更淡
   · 备选车次另起一组，整体降一级（更小、更灰），不抢主车次
   ============================================================ */
.ticket {
  position: relative;
  margin-top: 16px;
  padding: 12px 14px 12px 16px;
  border-radius: 12px;
  background: var(--panel2);
  border: 1px solid var(--border);
}
/* 左侧色条：票据的「边」 */
.ticket::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 3px;
  background: var(--grad);
  opacity: 0.85;
}

.ticket__route {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  font-size: 0.9rem;
  font-weight: 650;
  color: var(--text);
}
.ticket__station { letter-spacing: -0.01em; }
.ticket__arrow {
  color: var(--text3);
  flex-shrink: 0;
}
/* 车次用等宽字：它是编号而非词语，等宽能一眼扫出并便于逐个比对 */
.ticket__no {
  font-family: var(--mono);
  font-size: 0.82rem;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 6px;
  background: var(--panel);
  border: 1px solid var(--border);
  color: var(--blue-700);
  letter-spacing: 0.02em;
}
:root[data-theme='dark'] .ticket__no { color: var(--blue-300); }

/* 「推荐」：金色小标签。金是本站既有的点缀色，且与「备选」的灰形成明确对比 */
.ticket__rec {
  padding: 1px 7px;
  border-radius: 6px;
  background: var(--gold-soft);
  color: var(--gold-600);
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.03em;
}
:root[data-theme='dark'] .ticket__rec {
  background: rgba(214, 158, 46, 0.18);
  color: var(--gold-400);
}

.ticket__facts {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 7px;
  font-size: 0.79rem;
  color: var(--text2);
}
/* 时刻用等宽字，数字对齐后更好读 */
.ticket__time {
  font-family: var(--mono);
  font-size: 0.78rem;
  letter-spacing: 0.01em;
}
.ticket__seat {
  padding: 1px 7px;
  border-radius: 5px;
  background: var(--panel);
  border: 1px solid var(--border);
  font-size: 0.72rem;
}
/* 价格是决策信息，稍作强调 */
.ticket__price {
  margin-left: auto;
  font-weight: 750;
  font-size: 0.86rem;
  color: var(--text);
}

/* ---- 备选车次：整体降一级 ---- */
.ticket__alts {
  list-style: none;
  margin: 9px 0 0;
  padding: 9px 0 0;
  border-top: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.ticket__alt {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 0.76rem;
  /* 弱化：文字用 text3，不参与「一眼扫过」的竞争 */
  color: var(--text3);
}
.ticket__alt-label {
  font-size: 0.68rem;
  letter-spacing: 0.04em;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--panel);
  border: 1px solid var(--border);
}
.ticket__alt-no {
  font-family: var(--mono);
  font-weight: 650;
}
.ticket__alt-time { font-family: var(--mono); font-size: 0.74rem; }
/* 备选的目的地站：比同行的「备选」标签更实一点，
   因为它是「这趟车去哪里」这一决策信息，不该和标签一样淡 */
.ticket__alt-to {
  color: var(--text2);
  font-weight: 550;
}
.ticket__alt-price { margin-left: auto; }

/* 兜底：认不出结构时按纯文本展示 */
.ticket--plain {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--text2);
}

/* ============================================================
   主题标签
   ------------------------------------------------------------
   .ptag 与各语义色（--history/--nature/--food/--shopping/--leisure/--plain）
   定义在全局 main.css —— 行程**详情页**也要用同一套，
   写两处必然漂移（同一标签在两个页面变两个颜色）。
   这里只负责本页的排布。
   ============================================================ */
.it-card__prefs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 14px;
}

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

/* 「查看行程」：从弱化的灰色文字改为有底色的按钮态，加强存在感。
   卡片整体可点，这里是**视觉承诺**而非独立交互元素，故不做成真按钮。 */
.it-card__go {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 9px;
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--blue-700);
  background: var(--blue-50);
  transition: color 0.2s, background-color 0.2s, gap 0.2s;
}
:root[data-theme='dark'] .it-card__go {
  color: var(--blue-300);
  background: rgba(37, 99, 235, 0.16);
}
.it-card:hover .it-card__go,
.it-card:focus-visible .it-card__go {
  gap: 8px;
  color: #fff;
  background: var(--prim);
}

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

