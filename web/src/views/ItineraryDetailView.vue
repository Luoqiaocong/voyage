<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
import BackToTop from '@/components/BackToTop.vue'
import NavButton from '@/components/NavButton.vue'
import SharePanel from '@/components/SharePanel.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import {
  deleteItinerary,
  exportItineraryCalendar,
  exportItineraryMarkdown,
  getItinerary,
  openItineraryPrintView,
  patchItinerary,
  type ItineraryActivity,
  type ItineraryDetail
} from '@/api/itinerary'
import { useUiStore } from '@/stores/ui'
import { groupBySlot, sortGroupsBySlot } from '@/utils/messageParse'
import { preferenceTone } from '@/utils/preferenceTone'
import { parseTransport } from '@/utils/transportParse'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()

const id = Number(route.params.id)
const detail = ref<ItineraryDetail | null>(null)
const loading = ref(true)

/**
 * 往返交通的结构化解析。
 *
 * 与行程列表页卡片共用同一个解析器与同一套票据样式，
 * 两处展示必须一致 —— 用户在列表看到的车次信息，
 * 点进来不该换一种写法。
 */
const detailTransport = computed(() => parseTransport(detail.value?.plan.transport))
const saving = ref(false)

/** 分享面板默认收起：它不是高频操作，展开会挤掉行程正文 */
const showShare = ref(false)
/** 导出进行中标记：同一个时刻只允许一个导出任务 */
const exporting = ref<'ics' | 'md' | 'print' | null>(null)

const editing = ref(false)
const edit = reactive({
  budget: null as number | null,
  preferences: [] as string[],
  transport: '',
  tips: [] as string[],
  accommodationName: '',
  accommodationDuration: 2,
  accommodationCost: 0,
  accommodationNote: ''
})

const kindLabel: Record<string, string> = {
  attraction: '景点',
  restaurant: '美食',
  hotel: '住宿',
  transport: '交通',
  rest: '休整'
}

// 时段标签由 groupBySlot 统一从 messageParse 的 SLOT_TEXT 生成，
// 本文件不再自己维护一份映射，避免两处不一致。

/**
 * 导出下拉的选项。
 *
 * 图标从 TravelIcon 里挑语义最近的：站内只有固定一套 SVG，没有日历/打印/
 * 文档这类通用图标。用「时钟」表示日历（同为时间维度）、「地图」表示 PDF
 * （输出的是版面），比继续用 emoji 统一得多 —— emoji 跨平台字形差异大，
 * 且与站内图标风格脱节。
 *
 * 每项带一句说明：下拉展开后有一段空间，写清「导出成什么、能拿来做什么」
 * 比只放一个词更有用。
 */
const exportTools = [
  { key: 'ics' as const, label: '日历文件', hint: '可导入手机日历，带时间提醒', icon: 'clock' },
  { key: 'md' as const, label: 'Markdown', hint: '纯文本，方便复制到别处编辑', icon: 'edit' },
  { key: 'print' as const, label: 'PDF / 打印', hint: '打开打印视图，可另存为 PDF', icon: 'map' }
]

/** 导出下拉的开合状态 */
const exportOpen = ref(false)
const exportWrap = ref<HTMLElement | null>(null)

/** 选中一项后关闭下拉再执行，避免导出期间菜单还挂在界面上 */
async function pickExport(kind: 'ics' | 'md' | 'print') {
  exportOpen.value = false
  await doExport(kind)
}

/**
 * 点击组件外部时收起下拉。
 *
 * 只在展开时挂监听：常驻监听会让每次页面点击都走一遍判断，
 * 而下拉大部分时间是关闭的。用 pointerdown 而非 click —— 后者要等
 * 鼠标抬起，期间用户可能已经点到别处，收起会显得迟钝。
 */
function onDocPointerDown(e: PointerEvent) {
  if (!exportOpen.value) return
  const el = exportWrap.value
  if (el && !el.contains(e.target as Node)) exportOpen.value = false
}

/** Esc 关闭下拉：键盘用户需要一条退路，不能只靠点空白 */
function onDocKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && exportOpen.value) exportOpen.value = false
}

onMounted(async () => {
  // 下拉的「点击外部收起 / Esc 收起」监听
  document.addEventListener('pointerdown', onDocPointerDown)
  document.addEventListener('keydown', onDocKeydown)

  try {
    detail.value = await getItinerary(id)
    syncEdit()
  } catch (e: any) {
    ui.toast(e?.message ?? '行程加载失败', 'error')
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocPointerDown)
  document.removeEventListener('keydown', onDocKeydown)
})

function syncEdit() {
  if (!detail.value) return
  const p = detail.value.plan
  edit.budget = p.budget ?? null
  edit.preferences = [...(p.preferences ?? [])]
  edit.transport = p.transport ?? ''
  edit.tips = [...(p.tips ?? [])]
  edit.accommodationName = p.accommodation?.name ?? ''
  edit.accommodationDuration = p.accommodation?.duration_hours ?? 2
  edit.accommodationCost = p.accommodation?.cost ?? 0
  edit.accommodationNote = p.accommodation?.note ?? ''
}

function addChip(target: 'preferences' | 'tips') {
  const inputId = target === 'preferences' ? 'pref-input' : 'tip-input'
  const el = document.getElementById(inputId) as HTMLInputElement | HTMLTextAreaElement | null
  const v = el?.value.trim()
  if (!v) return
  if (target === 'preferences') edit.preferences.push(v)
  else edit.tips.push(v)
  if (el) el.value = ''
}

function removeChip(target: 'preferences' | 'tips', i: number) {
  if (target === 'preferences') edit.preferences.splice(i, 1)
  else edit.tips.splice(i, 1)
}

async function saveEdits() {
  if (!detail.value) return
  saving.value = true
  try {
    const accommodation: ItineraryActivity | null = edit.accommodationName.trim()
      ? {
          time_slot: 'evening',
          kind: 'hotel',
          name: edit.accommodationName.trim(),
          description: '住宿安排',
          duration_hours: Number(edit.accommodationDuration) || 2,
          cost: Number(edit.accommodationCost) || 0,
          note: edit.accommodationNote.trim() || null
        }
      : null
    const patch = {
      budget: edit.budget === null || Number.isNaN(Number(edit.budget)) ? null : Number(edit.budget),
      preferences: edit.preferences,
      transport: edit.transport.trim() || null,
      tips: edit.tips,
      accommodation
    }
    const updated = await patchItinerary(id, patch)
    detail.value = updated
    editing.value = false
    syncEdit()
    ui.toast('行程已保存', 'success')
  } catch (e: any) {
    ui.toast(e?.message ?? '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!detail.value) return
  const sure = await ui.confirm('确定删除「' + detail.value.plan.destination + '」的行程吗？')
  if (!sure) return
  try {
    await deleteItinerary(id)
    ui.toast('行程已删除', 'success')
    router.replace('/itineraries')
  } catch (e: any) {
    ui.toast(e?.message ?? '删除失败', 'error')
  }
}

/**
 * 导出行程。
 *
 * 三种格式的落点不同：
 * - .ics 直接下载，可导入手机日历（每天活动变成日程）
 * - Markdown 直接下载（浏览器无法优雅预览 md）
 * - 打印页在新标签打开，用户用 Ctrl+P 即可存为 PDF
 */
async function doExport(kind: 'ics' | 'md' | 'print') {
  exporting.value = kind
  try {
    if (kind === 'ics') await exportItineraryCalendar(id)
    else if (kind === 'md') await exportItineraryMarkdown(id)
    else await openItineraryPrintView(id)
    if (kind !== 'print') ui.toast('导出已开始下载', 'success')
  } catch (e: any) {
    ui.toast(e?.message ?? '导出失败', 'error')
  } finally {
    exporting.value = null
  }
}

const budgetDraft = computed({
  get: () => (edit.budget == null ? '' : String(edit.budget)),
  set: (v: string) => {
    edit.budget = v.trim() === '' ? null : Number(v)
  }
})

function openEditor() {
  syncEdit()
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  syncEdit()
}
</script>

<template>
  <div>
    <AppNavbar />
    <main id="main" tabindex="-1">
      <div class="container page">
        <template v-if="loading">
          <div class="empty"><p>加载中…</p></div>
        </template>

        <template v-else-if="detail">
          <div class="page-head">
            <div class="it-head">
              <!-- 用统一的 NavButton（次要按钮形态）：纯文字链接看起来不像可点的控件 -->
              <NavButton to="/itineraries" label="全部行程" />
              <h1 class="page-title">{{ detail.plan.destination }}</h1>
              <div class="it-head__chips">
                <span class="badge-kind badge-tag">{{ detail.plan.days }} 天</span>
                <span v-if="detail.plan.budget != null" class="badge-kind badge-country">预算 ¥{{ detail.plan.budget }}</span>
                <span class="badge-kind badge-tag">#{{ detail.id }}</span>
              </div>
            </div>
            <!--
              操作区。配色按「功能语义」分配，而不是一片灰：
                编辑行程  实心蓝 —— 主操作
                分享      绿     —— 传播类
                导出 ▾    金     —— 输出类，合并为下拉
                删除      灰→红  —— 破坏性操作，不常亮
              三色并存但不刺眼：都用淡色底 + 饱和文字，只有主操作是实心。
            -->
            <div class="it-actions">
              <template v-if="!editing">
                <div class="it-actions__group">
                  <!-- 分享：独立按钮而非塞进下拉 —— 它是这页最常用的动作之一 -->
                  <button
                    class="btn btn-tint btn-tint-green btn--sm"
                    type="button"
                    :class="{ 'is-open': showShare }"
                    :title="showShare ? '收起分享面板' : '生成分享链接'"
                    @click="showShare = !showShare"
                  >
                    <TravelIcon name="spark" :size="15" />
                    {{ showShare ? '收起分享' : '分享' }}
                  </button>

                  <!--
                    导出：三个格式（日历 / Markdown / PDF）收进一个下拉。
                    导出是低频动作，不配占操作区一半宽度；收进下拉后主次更清楚。
                  -->
                  <div ref="exportWrap" class="exp">
                    <button
                      class="btn btn-tint btn-tint-gold btn--sm"
                      type="button"
                      :disabled="exporting !== null"
                      :aria-expanded="exportOpen"
                      aria-haspopup="menu"
                      @click="exportOpen = !exportOpen"
                    >
                      <TravelIcon name="arrow-right" :size="15" class="exp__icon" />
                      {{ exporting !== null ? '导出中…' : '导出' }}
                      <span class="exp__caret" :class="{ 'is-open': exportOpen }" aria-hidden="true"></span>
                    </button>

                    <Transition name="exp">
                      <div v-if="exportOpen" class="exp__menu" role="menu">
                        <button
                          v-for="t in exportTools"
                          :key="t.key"
                          class="exp__item"
                          type="button"
                          role="menuitem"
                          :disabled="exporting !== null"
                          @click="pickExport(t.key)"
                        >
                          <TravelIcon :name="t.icon" :size="15" />
                          <span class="exp__item-main">
                            <b>{{ t.label }}</b>
                            <i>{{ t.hint }}</i>
                          </span>
                        </button>
                      </div>
                    </Transition>
                  </div>
                </div>

                <div class="it-actions__group it-actions__group--main">
                  <button class="btn btn-primary btn--sm" type="button" @click="openEditor">
                    <TravelIcon name="edit" :size="15" />
                    编辑行程
                  </button>
                  <!-- 删除：默认灰字（不常亮红色），悬停才转红 -->
                  <button class="delbtn" type="button" title="删除这份行程" @click="remove">
                    删除
                  </button>
                </div>
              </template>

              <template v-else>
                <button class="btn btn-ghost btn--sm" :disabled="saving" @click="cancelEdit">
                  取消
                </button>
                <button class="btn btn-primary btn--sm" :disabled="saving" @click="saveEdits">
                  {{ saving ? '保存中…' : '保存修改' }}
                </button>
              </template>
            </div>
          </div>

          <!-- 分享面板：默认收起，展开时置于概览之上 -->
          <SharePanel v-if="showShare" :itinerary-id="id" />

          <!--
            概览卡片组。四块共用一套「小标题 + 内容」的语言，
            视觉上与列表页的卡片保持一致（同样的标签配色、同样的票据块）。
            目的地块承载天数与预算 —— 它们是对目的地的定量描述，
            与列表页头部「城市名 + N 天 · 预算」的层级完全一致。
          -->
          <section class="ov">
            <!-- 目的地 -->
            <div class="ov__card ov__card--dest ov__card--center">
              <p class="ov__label">
                <TravelIcon name="compass" :size="14" />目的地
              </p>
              <p class="ov__dest">{{ detail.plan.destination }}</p>
              <p class="ov__meta">
                <span class="ov__days">{{ detail.plan.days }} 天</span>
                <template v-if="detail.plan.budget != null">
                  <span class="ov__dot" aria-hidden="true">·</span>
                  <span>预算 ¥{{ detail.plan.budget }}</span>
                </template>
              </p>
            </div>

            <!--
              往返交通：与列表页卡片同一套票据结构。
              解析不出车次时退回纯文本 —— transport 是自由文本，
              字段完整度无法保证，不能因为解析失败就什么都不显示。
            -->
            <div class="ov__card">
              <p class="ov__label">
                <TravelIcon name="train" :size="14" />往返交通
              </p>

              <template v-if="detailTransport.primary">
                <div class="ticket">
                  <div class="ticket__route">
                    <span v-if="detailTransport.primary.from" class="ticket__station">
                      {{ detailTransport.primary.from }}
                    </span>
                    <TravelIcon name="arrow-right" :size="13" class="ticket__arrow" />
                    <span v-if="detailTransport.primary.to" class="ticket__station">
                      {{ detailTransport.primary.to }}
                    </span>
                    <span v-if="detailTransport.primary.trainNo" class="ticket__no">
                      {{ detailTransport.primary.trainNo }}
                    </span>
                    <span
                      v-if="detailTransport.primary.recommended"
                      class="ticket__rec"
                    >推荐</span>
                  </div>
                  <div class="ticket__facts">
                    <span
                      v-if="detailTransport.primary.depart"
                      class="ticket__time"
                    >{{ detailTransport.primary.depart }} – {{ detailTransport.primary.arrive }}</span>
                    <span v-if="detailTransport.primary.seat" class="ticket__seat">
                      {{ detailTransport.primary.seat }}
                    </span>
                    <span v-if="detailTransport.primary.price" class="ticket__price">
                      {{ detailTransport.primary.price }}
                    </span>
                  </div>

                  <ul v-if="detailTransport.alternatives.length" class="ticket__alts">
                    <li
                      v-for="(alt, ai) in detailTransport.alternatives"
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
                </div>
              </template>
              <p v-else class="ov__plain">
                {{ detail.plan.transport || '未指定' }}
              </p>
            </div>

            <!-- 住宿 -->
            <div v-if="detail.plan.accommodation" class="ov__card">
              <p class="ov__label">
                <TravelIcon name="bed" :size="14" />住宿
              </p>
              <p class="ov__stay-name">{{ detail.plan.accommodation.name }}</p>
              <p v-if="detail.plan.accommodation.description" class="ov__stay-desc">
                {{ detail.plan.accommodation.description }}
              </p>
              <p class="ov__stay-facts">
                <span
                  v-if="detail.plan.accommodation.cost"
                  class="ov__cost"
                >¥{{ detail.plan.accommodation.cost }} / 晚</span>
                <span v-if="detail.plan.accommodation.note" class="ov__stay-note">
                  {{ detail.plan.accommodation.note }}
                </span>
              </p>
            </div>

            <!-- 偏好：与列表页同一套语义配色 -->
            <div v-if="detail.plan.preferences?.length" class="ov__card">
              <p class="ov__label">
                <TravelIcon name="star" :size="14" />偏好
              </p>
              <div class="ov__tags">
                <span
                  v-for="p in detail.plan.preferences"
                  :key="p"
                  class="ptag"
                  :class="`ptag--${preferenceTone(p)}`"
                >{{ p }}</span>
              </div>
            </div>
          </section>

          <section v-if="editing" class="card edit-panel">
            <h2 class="edit-panel__title">编辑行程信息（仅修改独立字段；每日安排请在对话中重新生成）</h2>

            <div class="edit-grid">
              <div class="field">
                <label for="budget">总预算（元）</label>
                <input id="budget" v-model="budgetDraft" class="input" type="number" min="0" placeholder="留空表示未知" />
              </div>
              <div class="field">
                <label for="transport">往返交通建议</label>
                <input id="transport" v-model="edit.transport" class="input" placeholder="如：广州→北京 高铁 G77 08:30-16:05" />
              </div>
            </div>

            <div class="field edit-field-gap">
              <label for="pref-input">旅行偏好（回车添加）</label>
              <div class="chip-input-row">
                <input id="pref-input" class="input" placeholder="如：美食 / 亲子 / 穷游" @keydown.enter.prevent="addChip('preferences')" />
              </div>
              <div class="chip-list">
                <span v-for="(p, i) in edit.preferences" :key="p" class="chip chip--removable">
                  {{ p }} <button class="chip-x" aria-label="移除偏好" @click="removeChip('preferences', i)">✕</button>
                </span>
              </div>
            </div>

            <div class="field edit-field-gap">
              <label for="tip-input">出行提醒（一行一条）</label>
              <div class="chip-input-row">
                <textarea id="tip-input" class="input" rows="2" placeholder="例如：故宫门票需提前 7 天预约"></textarea>
                <button class="btn btn-ghost btn--sm" @click="addChip('tips')">添加</button>
              </div>
              <ul class="tip-list">
                <li v-for="(t, i) in edit.tips" :key="i">
                  {{ t }} <button class="chip-x" aria-label="移除提醒" @click="removeChip('tips', i)">✕</button>
                </li>
              </ul>
            </div>

            <div class="field edit-field-gap">
              <label for="accommodation-name">住宿安排（名称留空则移除）</label>
              <div class="edit-grid">
                <input id="accommodation-name" v-model="edit.accommodationName" class="input" placeholder="酒店 / 民宿名称" />
                <div class="edit-grid edit-grid--2col">
                  <input
                    v-model.number="edit.accommodationDuration"
                    class="input"
                    type="number"
                    min="1"
                    step="0.5"
                    placeholder="停留小时"
                    aria-label="住宿停留小时"
                  />
                  <input
                    v-model.number="edit.accommodationCost"
                    class="input"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="单人花费 / 晚"
                    aria-label="住宿单人花费（元/晚）"
                  />
                </div>
              </div>
              <textarea
                v-model="edit.accommodationNote"
                class="input"
                rows="2"
                style="margin-top:10px"
                placeholder="入住 / 退房日期等备注"
                aria-label="住宿备注（入住与退房日期等）"
              ></textarea>
            </div>
          </section>

          <section v-for="day in detail.plan.daily_plans" :key="day.day_no" class="day card">
            <header class="day__head">
              <span class="day__no">Day {{ day.day_no }}</span>
              <div>
                <h2 class="day__theme">{{ day.theme }}</h2>
                <p class="day__date">{{ day.date || '第 ' + day.day_no + ' 天' }}</p>
              </div>
            </header>

            <!--
              按时段归组渲染，而不是每条活动前面都挂「上午/下午/晚上」。
              一天内常有多条属于同一时段，逐条挂标签会让同一个词重复出现，
              真正的内容反而被淹没。归组后时段只作分组标题出现一次。
              这里用 sortGroupsBySlot 按时间排序（数据是结构化的，
              按「上午→下午→晚上」阅读更自然）。
            -->
            <div class="day__slots">
              <section
                v-for="(grp, gi) in sortGroupsBySlot(
                  groupBySlot(day.activities, (a: ItineraryActivity) => a.time_slot)
                )"
                :key="gi"
                class="slotgrp"
              >
                <h4 v-if="grp.label" class="slotgrp__label">{{ grp.label }}</h4>
                <ul class="day__acts">
                  <li v-for="(act, i) in grp.items" :key="i" class="act">
                    <span class="badge-kind badge-tag">{{ kindLabel[act.kind] }}</span>
                    <div class="act__body">
                      <h3>{{ act.name }}</h3>
                      <p>{{ act.description }}</p>
                      <div class="act__meta">
                        <span v-if="act.duration_hours">约 {{ act.duration_hours }} 小时</span>
                        <!--
                          cost 是整数、单位元，0 表示免费。
                          必须始终渲染这一位：写成 v-if="act.cost" 时 0 是假值，
                          免费活动的费用位会整个消失，看起来像数据缺失。
                        -->
                        <span :class="{ 'act__free': !act.cost }">
                          {{ act.cost ? `¥${act.cost}` : '免费' }}
                        </span>
                        <span v-if="act.note" class="act__note">{{ act.note }}</span>
                      </div>
                    </div>
                  </li>
                </ul>
              </section>
            </div>

            <p class="day__summary">{{ day.summary }}</p>
          </section>

          <section v-if="detail.plan.tips?.length" class="card tips">
            <h2>出行提醒</h2>
            <ul>
              <li v-for="(t, i) in detail.plan.tips" :key="i">{{ t }}</li>
            </ul>
          </section>
        </template>
      </div>
    </main>

    <!-- 返回顶部：行程详情按天铺开、还有清单与提醒，页面通常很长 -->
    <BackToTop />
  </div>
</template>

<style scoped>
/* 返回入口的样式已抽到 components/NavButton.vue，
   本文件不再自行定义纯文字链接，避免各处写法不一致 */
.it-head { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }

.it-head__chips { display: flex; gap: 8px; margin-top: 4px; }

/* ---- 操作区 ----
   两组：工具（次要，浅底）与主操作（编辑/删除）。
   组间用一道细竖线分隔，让「导出」与「改动」在视觉上分开。 */
.it-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.it-actions__group {
  display: flex;
  align-items: center;
  gap: 8px;
}
/* 两组之间的细竖线：比留白更能说明「这是两类操作」 */
.it-actions__group--main {
  padding-left: 14px;
  border-left: 1px solid var(--line);
}

/* ---- 导出下拉 ----
   把三个格式收进一个菜单：导出是低频动作，不该与「编辑行程」抢位置。 */
.exp { position: relative; }

/* 按钮里的箭头转一下当作下拉指示，避免再加一个图标 */
.exp__icon { transform: rotate(90deg); opacity: 0.8; }

.exp__caret {
  width: 0;
  height: 0;
  margin-left: 1px;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid currentColor;
  opacity: 0.7;
  transition: transform 0.2s ease;
}
.exp__caret.is-open { transform: rotate(180deg); }

.exp__menu {
  position: absolute;
  z-index: 20;
  top: calc(100% + 8px);
  right: 0;
  min-width: 232px;
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: var(--r-m);
  /* 菜单需要明显浮于内容之上，故这里用较强的阴影（按钮上刻意不用） */
  box-shadow: 0 12px 32px rgba(16, 24, 40, 0.14), 0 2px 6px rgba(16, 24, 40, 0.06);
  background: var(--surface);
}

.exp__item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: var(--r-s);
  background: transparent;
  text-align: left;
  transition: background-color 0.16s ease;
}
.exp__item :deep(svg) {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--gold-600);
  transition: color 0.16s ease;
}
.exp__item:hover:not(:disabled) { background: var(--gold-soft); }
.exp__item:disabled { opacity: 0.5; cursor: not-allowed; }
.exp__item:focus-visible {
  outline: 2px solid var(--gold-600);
  outline-offset: -2px;
}

.exp__item-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.exp__item-main b { font-size: 0.86rem; font-weight: 650; color: var(--text); }
.exp__item-main i {
  font-style: normal;
  font-size: 0.75rem;
  line-height: 1.45;
  color: var(--text3);
}

/* 展开/收起：轻微下移淡入，不做缩放（缩放会让菜单像弹出来） */
.exp-enter-active,
.exp-leave-active { transition: opacity 0.16s ease, transform 0.16s ease; }
.exp-enter-from,
.exp-leave-to { opacity: 0; transform: translateY(-4px); }

/* 「分享」按钮在面板展开时保持按下感 */
.btn-tint-green.is-open {
  background: rgba(56, 161, 105, 0.2);
  border-color: rgba(56, 161, 105, 0.32);
}

@media (prefers-reduced-motion: reduce) {
  .exp__caret,
  .exp__item,
  .exp__item :deep(svg) { transition: none; }
  .exp-enter-active,
  .exp-leave-active { transition: none; }
}

/* ---- 删除：弱化为文字按钮 ----
   删除是最不该被误点的操作，故默认只有灰字，悬停才转为红色；
   实心红底在浅色页面里过于刺眼。
   仍然放在最右——位置固定，需要时一眼能找到。 */
.delbtn {
  padding: 7px 10px;
  border: none;
  border-radius: var(--r-s);
  background: transparent;
  font-size: 0.82rem;
  font-weight: 550;
  color: var(--ink-soft);
  transition: color 0.18s, background-color 0.18s;
}
.delbtn:hover {
  color: var(--danger);
  background: rgba(224, 82, 82, 0.08);
}
.delbtn:focus-visible {
  outline: 2px solid var(--danger);
  outline-offset: 2px;
}

/* 窄屏：两组各自换行，竖线在换行后意义会变弱，故去掉 */
@media (max-width: 720px) {
  .it-actions { gap: 10px; }
  .it-actions__group--main {
    padding-left: 0;
    border-left: none;
  }
}

/* ============================================================
   概览卡片组：两列，四块排成 2×2
   ------------------------------------------------------------
   两列（每张约 540px）让四块形成规整的 2×2，卡片内不再有大片空白，
   也不显拥挤。不能用固定四列 —— 那样每张只剩约 250px，
   车次 + 时刻 + 座别 + 价格会挤在一起；auto-fit minmax(240px)
   在常见视口下会排出 3 列 + 1 块换行，也不齐。

   响应式只递减列数，不改变「同级并列」的语义：
     宽屏 ≥760   两列（2×2）
     窄屏 <760   单列堆叠
   ------------------------------------------------------------ */
.ov {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  /*
   * 两行等高。默认每行各自按内容撑高，两行会差几个像素，
   * 看起来像没对齐；两行等高后四块才形成规整的 2×2。
   */
  grid-auto-rows: 1fr;
  gap: 14px;
  margin-bottom: 24px;
}
@media (max-width: 760px) {
  .ov { grid-template-columns: minmax(0, 1fr); }
}
.ov__card {
  padding: 16px 18px;
  border-radius: 14px;
  background: var(--panel);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  /*
   * 同行的卡片会被 grid 拉到等高（这是好事，四块才看起来齐），
   * 但内容少的块（目的地只有一行城市名、偏好只有几个标签）
   * 就会在底部留出一片空白。用纵向 flex + 居中把内容在卡片内
   * 垂直居中，空白被均分到上下 —— 读起来是「留白」而非「没写完」。
   *
   * ⚠️ 这里必须显式声明 display: flex。块级容器上写 align-content
   * 对普通流子元素**不生效**（它只作用于 flex/grid 容器）。
   */
  display: flex;
  flex-direction: column;
  justify-content: center;
}
/* 目的地是整组里唯一的「标题级」信息：加左侧强调条与淡蓝底，
   让它在四块里第一眼被看到 */
.ov__card--dest {
  position: relative;
  padding-left: 22px;
  background: linear-gradient(180deg, var(--blue-50), var(--panel) 70%);
}
/*
 * 内容居中的变体：给「目的地」这种内容很短（一行城市名 + 一行元信息）
 * 的卡片用。小标题已经居中，若内容仍左对齐会显得上下不搭；
 * 而且短内容左对齐时右侧空一大片，比居中更空。
 * 长文本块（交通票据、住宿描述）不适用，故不做成默认。
 */
.ov__card--center {
  text-align: center;
}
.ov__card--center .ov__label,
.ov__card--center .ov__meta {
  justify-content: center;
}
.ov__card--dest::before {
  content: '';
  position: absolute;
  left: 0;
  top: 14px;
  bottom: 14px;
  width: 3px;
  border-radius: 3px;
  background: var(--grad);
}
:root[data-theme='dark'] .ov__card--dest {
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.12), var(--panel) 70%);
}

.ov__label {
  display: flex;
  align-items: center;
  justify-content: center;   /* 居中 */
  gap: 7px;
  font-size: 0.92rem;        /* 由 0.76rem 加大 */
  font-weight: 750;          /* 由 700 加粗 */
  letter-spacing: 0.02em;
  color: var(--text2);       /* 由 text3 提亮一档，与加粗后的字重匹配 */
}
.ov__label :deep(svg) { color: var(--blue-600); }
:root[data-theme='dark'] .ov__label :deep(svg) { color: var(--blue-400); }

.ov__dest {
  margin-top: 8px;
  font-family: var(--font-display);
  font-size: 1.6rem;
  font-weight: 750;
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1.2;
}
.ov__meta {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 8px;
  font-size: 0.84rem;
  color: var(--text2);
}
/* 与列表页的天数徽标同款，两处保持一致 */
.ov__days {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--blue-50);
  color: var(--blue-700);
  font-size: 0.76rem;
  font-weight: 700;
}
:root[data-theme='dark'] .ov__days {
  background: rgba(37, 99, 235, 0.18);
  color: var(--blue-300);
}
.ov__dot { color: var(--text3); }

/* 住宿 */
.ov__stay-name {
  margin-top: 8px;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text);
}
.ov__stay-desc {
  margin-top: 5px;
  font-size: 0.85rem;
  line-height: 1.65;
  color: var(--text2);
}
.ov__stay-facts {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 9px;
  font-size: 0.78rem;
  color: var(--text3);
}
.ov__cost {
  font-weight: 750;
  font-size: 0.9rem;
  color: var(--text);
}
.ov__stay-note { line-height: 1.6; }

.ov__plain {
  margin-top: 8px;
  font-size: 0.86rem;
  line-height: 1.7;
  color: var(--text2);
}
.ov__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
  /* 与居中的小标题对齐；标签数量少时也不会靠左显得空 */
  justify-content: center;
}

/* ---- 票据块（与 ItinerariesView 的样式保持一致）----
   行程列表与详情两处展示同一份车票信息，样式必须一致；
   scoped 样式无法跨组件共享，故在此重复一份并保持同步。
   若将来要改，两处都要改（已在两边注释中互相标注）。 */
.ticket {
  position: relative;
  margin-top: 10px;
  padding: 12px 14px 12px 16px;
  border-radius: 12px;
  background: var(--panel2);
  border: 1px solid var(--border);
}
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
  font-size: 0.92rem;
  font-weight: 650;
  color: var(--text);
}
.ticket__station { letter-spacing: -0.01em; }
.ticket__arrow { color: var(--text3); flex-shrink: 0; }
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
.ticket__time { font-family: var(--mono); font-size: 0.78rem; letter-spacing: 0.01em; }
.ticket__seat {
  padding: 1px 7px;
  border-radius: 5px;
  background: var(--panel);
  border: 1px solid var(--border);
  font-size: 0.72rem;
}
.ticket__price {
  margin-left: auto;
  font-weight: 750;
  font-size: 0.86rem;
  color: var(--text);
}
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
.ticket__alt-no { font-family: var(--mono); font-weight: 650; }
.ticket__alt-time { font-family: var(--mono); font-size: 0.74rem; }
.ticket__alt-to { color: var(--text2); font-weight: 550; }
.ticket__alt-price { margin-left: auto; }

.edit-panel { padding: 22px 24px; margin-bottom: 24px; }
.edit-panel__title { font-size: 1.1rem; margin-bottom: 16px; }

.edit-grid { display: grid; grid-template-columns: 1fr 1.6fr; gap: 14px; }
.edit-grid--2col { grid-template-columns: 1fr 1fr; }
.edit-field-gap { margin-top: 16px; }

.chip-input-row { display: flex; gap: 10px; }
.chip-input-row .input { flex: 1; }

.chip-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.chip--removable { gap: 8px; }

.chip-x {
  border: none;
  background: transparent;
  color: inherit;
  font-size: 0.74rem;
  padding: 0;
  display: grid;
  place-items: center;
}
.chip-x:hover { color: var(--danger); }

.tip-list { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.tip-list li {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  background: var(--surface-soft);
  border-radius: 8px;
  font-size: 0.9rem;
}

.day { padding: 22px 24px; margin-bottom: 18px; }

.day__head { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }

.day__no {
  font-family: var(--display);
  font-size: 1.7rem;
  font-weight: 700;
  color: var(--primary);
  padding: 2px 10px;
  border: 1.5px solid var(--primary);
  border-radius: 10px;
}

.day__theme { font-size: 1.25rem; }
.day__date { color: var(--ink-soft); font-size: 0.85rem; }

/* ---- 时段分组 ----
   一天内的活动按时段归组，时段只作分组标题出现一次。
   组与组之间有间距，组内条目紧凑一些——这样「上午做了三件事」
   在视觉上是一个整体，而不是三条并列的独立卡片。 */
.day__slots { display: flex; flex-direction: column; gap: 18px; }

.slotgrp { display: flex; flex-direction: column; gap: 8px; }

.slotgrp__label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--blue-700);
  letter-spacing: 0.02em;
}
/* 标题右侧一道渐隐横线，把「上午」与后面的条目在视觉上连成一组 */
.slotgrp__label::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, var(--blue-200), transparent);
}

.day__acts { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }

/* 两列：类型徽标 + 正文（时段标签已移到分组标题上，不占条目列） */
.act {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px;
  align-items: flex-start;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
}

.act__body h3 { font-size: 1rem; }
.act__body p { color: var(--ink-soft); font-size: 0.88rem; margin-top: 2px; }

.act__meta { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 6px; font-size: 0.8rem; color: var(--ink-soft); }
.act__note { font-style: italic; }
/* 免费活动用成功色区分，让「0 元」看起来是有意为之而非缺数据 */
.act__free { color: var(--success); }

.day__summary { margin-top: 12px; color: var(--ink-soft); font-size: 0.9rem; border-top: 1px dashed var(--line); padding-top: 10px; }

.tips { padding: 20px 24px; }
.tips h2 { font-size: 1.1rem; margin-bottom: 10px; }
.tips ul { margin: 0; padding-left: 1.2em; display: flex; flex-direction: column; gap: 6px; color: var(--ink-soft); }

@media (max-width: 700px) {
  .act { grid-template-columns: 1fr; gap: 6px; }
  .edit-grid, .edit-grid--2col { grid-template-columns: 1fr; }
  .page-head { align-items: flex-start; }
}
</style>
