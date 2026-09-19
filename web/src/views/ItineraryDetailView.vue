<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppNavbar from '@/components/AppNavbar.vue'
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

const route = useRoute()
const router = useRouter()
const ui = useUiStore()

const id = Number(route.params.id)
const detail = ref<ItineraryDetail | null>(null)
const loading = ref(true)
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

// 原先此处有一份 timeLabel（morning→上午…）用于每条活动前的时段标签。
// 改为按时段归组后，标签由 groupBySlot 统一从 messageParse 的 SLOT_TEXT 生成，
// 本文件不再需要自己维护一份映射，故删除以免两处不一致。

/**
 * 导出/分享工具项。
 *
 * 图标从 TravelIcon 里挑语义最近的：站内只有固定一套 SVG 图标，
 * 没有日历/打印/文档这类通用图标。用「时钟」表示日历（两者都是时间维度）、
 * 「地图」表示打印（输出的是版面），比继续用 emoji 更统一 ——
 * emoji 跨平台字形差异大，且与站内图标风格完全脱节。
 */
const exportTools = [
  { key: 'ics' as const, label: '日历', icon: 'clock', title: '导出为 .ics，可导入手机日历' },
  { key: 'md' as const, label: 'Markdown', icon: 'edit', title: '导出为 Markdown 文本' },
  { key: 'print' as const, label: '打印', icon: 'map', title: '打开打印视图，可另存为 PDF' }
]

onMounted(async () => {
  try {
    detail.value = await getItinerary(id)
    syncEdit()
  } catch (e: any) {
    ui.toast(e?.message ?? '行程加载失败', 'error')
  } finally {
    loading.value = false
  }
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
  <div class="it-page">
    <AppNavbar />
    <main id="main" tabindex="-1">
      <div class="container page">
        <template v-if="loading">
          <div class="empty"><p>加载中…</p></div>
        </template>

        <template v-else-if="detail">
          <div class="page-head">
            <div class="it-head">
              <!--
                原先是一行纯文字「← 全部行程」，看起来不像可点的控件。
                改用统一的 NavButton（次要按钮形态）。
              -->
              <NavButton to="/itineraries" label="全部行程" />
              <h1 class="page-title">{{ detail.plan.destination }}</h1>
              <div class="it-head__chips">
                <span class="badge-kind badge-tag">{{ detail.plan.days }} 天</span>
                <span v-if="detail.plan.budget != null" class="badge-kind badge-country">预算 ¥{{ detail.plan.budget }}</span>
                <span class="badge-kind badge-tag">#{{ detail.id }}</span>
              </div>
            </div>
            <!--
              操作区分三组，按「用到它的频率」从右往左排：
                主操作  编辑行程（实心）—— 进入这份行程后最常做的事
                次要    分享 / 导出（日历、Markdown、打印）
                弱化    删除 —— 破坏性操作，不做实心红底
              原先六个按钮平铺、全用 emoji 当图标：
                · emoji 跨平台渲染差异大（Windows 是彩色、macOS 是另一套字形），
                  且与站内统一的 SVG 图标体系脱节，看起来像临时拼的
                · 主次不分：编辑与导出同为幽灵按钮，而删除是实心红，最刺眼
                · 无分组，六个按钮连成一排，扫视时找不到重点
            -->
            <div class="it-actions">
              <template v-if="!editing">
                <div class="it-actions__group it-actions__group--tools">
                  <button
                    v-for="t in exportTools"
                    :key="t.key"
                    class="toolbtn"
                    type="button"
                    :disabled="exporting !== null"
                    :title="t.title"
                    @click="doExport(t.key)"
                  >
                    <TravelIcon :name="t.icon" :size="15" />
                    <span>{{ exporting === t.key ? '导出中…' : t.label }}</span>
                  </button>
                  <button
                    class="toolbtn"
                    type="button"
                    :class="{ 'is-on': showShare }"
                    :title="showShare ? '收起分享面板' : '生成分享链接'"
                    @click="showShare = !showShare"
                  >
                    <TravelIcon name="spark" :size="15" />
                    <span>{{ showShare ? '收起分享' : '分享' }}</span>
                  </button>
                </div>

                <div class="it-actions__group it-actions__group--main">
                  <button class="btn btn-primary btn--sm" type="button" @click="openEditor">
                    <TravelIcon name="edit" :size="15" />
                    编辑行程
                  </button>
                  <!-- 删除做成文字按钮：它不该与常用操作抢视觉重量，
                       但仍要能一眼找到（放最右，位置固定） -->
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

          <section class="card it-overview">
            <div class="it-overview__item">
              <span class="it-overview__label">目的地</span>
              <strong>{{ detail.plan.destination }}</strong>
            </div>
            <div class="it-overview__item">
              <span class="it-overview__label">往返交通</span>
              <strong>{{ detail.plan.transport || '未指定' }}</strong>
            </div>
            <div v-if="detail.plan.accommodation" class="it-overview__item">
              <span class="it-overview__label">住宿</span>
              <strong>{{ detail.plan.accommodation.name }}</strong>
            </div>
            <div v-if="detail.plan.preferences?.length" class="it-overview__item it-overview__item--wide">
              <span class="it-overview__label">偏好</span>
              <span class="it-overview__chips">
                <span v-for="p in detail.plan.preferences" :key="p" class="chip">{{ p }}</span>
              </span>
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
                  <input v-model.number="edit.accommodationDuration" class="input" type="number" min="1" step="0.5" placeholder="停留小时" />
                  <input v-model.number="edit.accommodationCost" class="input" type="number" min="0" step="1" placeholder="单人花费 / 晚" />
                </div>
              </div>
              <textarea v-model="edit.accommodationNote" class="input" rows="2" style="margin-top:10px" placeholder="入住 / 退房日期等备注"></textarea>
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
                          原先写 v-if="act.cost"，而 0 是假值，导致免费活动
                          整个费用位不渲染 —— 看起来像数据缺失，实际是免费的。
                          故改为始终渲染，0 显示「免费」。
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

/* ---- 工具按钮（导出/分享）----
   比全局 .btn 更轻：字号更小、内边距更紧，避免与「编辑行程」抢视觉。 */
.toolbtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid var(--line);
  border-radius: var(--r-s);
  background: var(--surface);
  font-size: 0.82rem;
  font-weight: 550;
  color: var(--ink-soft);
  transition: background-color 0.18s, border-color 0.18s, color 0.18s, transform 0.18s;
}
.toolbtn :deep(svg) { opacity: 0.75; transition: opacity 0.18s; }
.toolbtn:hover:not(:disabled) {
  background: var(--surface-soft);
  border-color: var(--blue-200);
  color: var(--primary);
  transform: translateY(-1px);
}
.toolbtn:hover:not(:disabled) :deep(svg) { opacity: 1; }
.toolbtn:active:not(:disabled) { transform: translateY(0); }
.toolbtn:disabled { opacity: 0.5; cursor: not-allowed; }
/* 分享面板已展开时保持激活态，让「再点一次收起」这件事可预期 */
.toolbtn.is-on {
  background: var(--primary-soft);
  border-color: var(--blue-200);
  color: var(--primary);
}
.toolbtn.is-on :deep(svg) { opacity: 1; }
.toolbtn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* ---- 删除：弱化为文字按钮 ----
   原先用 .btn-danger（实心红底），在浅色页面里是最刺眼的一个，
   而它恰恰是最不该被误点的操作。改为默认只有灰字，悬停才转为红色。
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

.it-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 20px;
  padding: 20px 24px;
  margin-bottom: 24px;
}

.it-overview__item { display: flex; flex-direction: column; gap: 4px; }
.it-overview__item--wide { grid-column: 1 / -1; }
.it-overview__label { font-size: 0.8rem; color: var(--ink-soft); }
.it-overview__chips { display: flex; flex-wrap: wrap; gap: 6px; }

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

/* 归组后时段标签已移出条目，故列数由 3 列改为 2 列（类型徽标 + 正文） */
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
