<script setup lang="ts">
/**
 * 「我的记忆」管理面板。
 *
 * 记忆是系统从对话中提炼的画像。这里给用户完整的控制权：
 * 查看、修正取值、停用（不再注入对话但保留）、删除、一键清空。
 *
 * 设计上刻意展示 confidence / hit_count / evidence：
 * 让用户能判断某条记忆是「自己明确说过的」还是「系统猜的」，
 * 从而决定要不要纠正——不透明的画像会让人不安。
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  clearMemories,
  deleteMemory,
  listMemories,
  MEMORY_VALUE_OPTIONS,
  removeMemoryValue,
  toggleMemory,
  updateMemoryValue,
  type MemoryItem,
  type MemoryStats
} from '@/api/memory'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(true)
const items = ref<MemoryItem[]>([])
const stats = ref<MemoryStats | null>(null)
const showInactive = ref(false)
const busyId = ref<number | null>(null)

/** 正在编辑取值的记忆 ID */
const editingId = ref<number | null>(null)
const draftValue = ref('')
const savingValue = ref(false)

const activeItems = computed(() => items.value.filter((m) => m.is_active))
const inactiveItems = computed(() => items.value.filter((m) => !m.is_active))

/* ==================== 气泡展示 ==================== */

/**
 * 气泡配色：一组柔和的浅色，按序号循环。
 *
 * 用**序号取模**而不是按键或取值取色：气泡颜色只是让一堆同质小卡片彼此
 * 分开、不那么单调，**不承载语义**。若按 key 上色，用户会以为「蓝色代表
 * 偏好、绿色代表城市」而去解读它 —— 那是误导。按序号循环时相邻气泡必然
 * 不同色，观感上就够用了。
 *
 * 色板取自设计系统已有的浅色族，取值都在 50 级别附近，饱和度低、不刺眼。
 */
const BUBBLE_TONES = ['blue', 'cyan', 'green', 'gold', 'violet', 'amber'] as const

function bubbleTone(index: number): string {
  return `bubble--${BUBBLE_TONES[index % BUBBLE_TONES.length]}`
}

/* ==================== 气泡分列（瀑布流） ==================== */

/**
 * 气泡分两列。
 *
 * ## 为什么不用 CSS 多列（columns）
 *
 * 需求是「多列 + 限高 + 区域内竖向滚动」。实测过三种多列写法
 * （max-height / 固定 height / 加 contain），结果一致：
 * **内容不会竖向滚动，而是继续向右生成第 3、4 列**——
 * 容器高度被限住后，多列布局把放不下的内容排到右侧的可滚动溢出区，
 * 而不是往下排。于是出现「右半部分看不见、纵向又没得滚」。
 * 这是多列布局在受限高度下的固有行为，不是写法问题。
 *
 * CSS 也做不出横向的多列瀑布流（fixed 高度会破坏等高列的外观）。
 * 所以改为**受控分列**：自己把条目分到两个列容器里，列内是普通文档流，
 * 外层限高滚动 —— 这时竖向滚动才是真的竖向滚动。
 *
 * ## 分配算法
 *
 * 贪心：按顺序把每个条目放进当前**较矮**的那一列。
 * 先用文字长度估高排序一次（拿不到真实高度时的近似），
 * 挂载后再按**实测高度**重排一次 —— 一次就足够接近最优，
 * 反复迭代的收益很小，还会引入抖动。
 */
const colA = ref<MemoryItem[]>([])
const colB = ref<MemoryItem[]>([])
const colARef = ref<HTMLElement | null>(null)
const colBRef = ref<HTMLElement | null>(null)

/** 无实测高度时的估值：标题一行 + 正文按字数折行 + 间距 */
function estimateH(m: MemoryItem): number {
  const lines = Math.max(1, Math.ceil(m.fact_value.length / 14))
  return 62 + lines * 21 + (m.hit_count > 1 ? 14 : 0)
}

function distribute(getH: (m: MemoryItem) => number) {
  const a: MemoryItem[] = []
  const b: MemoryItem[] = []
  let ha = 0
  let hb = 0
  for (const m of activeItems.value) {
    if (ha <= hb) {
      a.push(m)
      ha += getH(m)
    } else {
      b.push(m)
      hb += getH(m)
    }
  }
  colA.value = a
  colB.value = b
}

/** 按实测高度再平衡：把较高列末尾的项搬给较低列，直到搬不动为止 */
async function rebalance() {
  await nextTick()
  const ha = colARef.value?.offsetHeight ?? 0
  const hb = colBRef.value?.offsetHeight ?? 0
  if (Math.abs(ha - hb) < 40) return   // 已经很接近，别为几像素打乱顺序

  const taller = ha > hb ? colA : colB
  const shorter = ha > hb ? colB : colA
  // 搬运量用估高近似 —— 只求「搬到接近」，不值得为精确高度反复量 DOM
  let diff = Math.abs(ha - hb)

  /*
   * 逐个搬末尾项，直到「再搬一项反而更不均衡」为止。
   * 只搬一项是不够的：两列差 250px 时搬一项只补上约 60~100px，
   * 差值仍然明显（实测 A=659 / B=403 就是这么来的）。
   */
  while (taller.value.length > 1) {
    const last = taller.value[taller.value.length - 1]
    const h = estimateH(last)
    if (Math.abs(diff - h) >= diff) break   // 搬过去不会更接近，停
    taller.value.pop()
    shorter.value.push(last)
    diff = Math.abs(diff - h)
  }
}

watch(activeItems, () => {
  distribute(estimateH)
  void rebalance()
})

/**
 * 已展开元素操作的气泡 id。
 *
 * 交互分工（两种删除各司其职）：
 *   · 右上角「×」  → 删除**整条**记忆，不需要展开，任何时候都在
 *   · 点击气泡本体 → 展开每个元素的「−」，用于**逐项**删除
 *
 * 用「点击展开」而不是「悬停展开」：悬停态在触屏上不存在，
 * 而且容易误触（鼠标划过就闪出一排 −）。点击是明确的意图表达，
 * 两种设备行为一致。
 */
const openedId = ref<number | null>(null)

function toggleOpen(m: MemoryItem) {
  openedId.value = openedId.value === m.id ? null : m.id
}

/** 收起已展开的气泡（点空白处或按 Esc） */
function closeOpened() {
  openedId.value = null
}

/** 该键是否受枚举约束：受约束的用下拉，否则用输入框 */
function optionsFor(key: string): string[] | null {
  return MEMORY_VALUE_OPTIONS[key] ?? null
}

function confidenceText(c: number): string {
  if (c >= 0.85) return '你说过的'
  if (c >= 0.6) return '较可信'
  return '系统推测'
}

function confidenceTone(c: number): string {
  if (c >= 0.85) return 'high'
  if (c >= 0.6) return 'mid'
  return 'low'
}

async function load() {
  loading.value = true
  try {
    const res = await listMemories(true) // 一次取回含停用项，前端自行分组
    items.value = res.memories
    stats.value = res.stats
  } catch (e: any) {
    ui.toast(e?.message ?? '记忆加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function startEdit(m: MemoryItem) {
  editingId.value = m.id
  draftValue.value = m.fact_value
}

function cancelEdit() {
  editingId.value = null
  draftValue.value = ''
}

async function saveValue(m: MemoryItem) {
  const next = draftValue.value.trim()
  if (!next || next === m.fact_value) {
    cancelEdit()
    return
  }
  savingValue.value = true
  try {
    await updateMemoryValue(m.id, next)
    ui.toast('已更新', 'success')
    cancelEdit()
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '更新失败', 'error')
  } finally {
    savingValue.value = false
  }
}

async function toggle(m: MemoryItem) {
  busyId.value = m.id
  try {
    await toggleMemory(m.id, !m.is_active)
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '操作失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function removeOne(m: MemoryItem) {
  const ok = await ui.confirm(`删除这条记忆「${m.fact_key_label}：${m.fact_value}」？`)
  if (!ok) return
  busyId.value = m.id
  try {
    await deleteMemory(m.id)
    ui.toast('已删除', 'success')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '删除失败', 'error')
  } finally {
    busyId.value = null
  }
}

/**
 * 只删多值记忆里的一项（如「去过的城市」里去掉一座城）。
 *
 * 不弹确认框：这个动作影响范围小（只少一项，不是整条消失），
 * 且删错了再聊一次就会重新记住。给每项都套一层确认会让面板变得很吵。
 * 整条删除（removeOne）仍然确认 —— 那个动作会丢失整类信息。
 */
async function removeValue(m: MemoryItem, value: string) {
  busyId.value = m.id
  try {
    await removeMemoryValue(m.id, value)
    ui.toast(`不再记住「${value}」`, 'success')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '删除失败', 'error')
  } finally {
    busyId.value = null
  }
}

async function removeAll() {
  const ok = await ui.confirm(
    '清空全部记忆后，助手将不再记得你的偏好（不影响已有对话与行程）。确认清空？'
  )
  if (!ok) return
  try {
    const res = await clearMemories()
    ui.toast(`已清空 ${res.deleted} 条记忆`, 'success')
    await load()
  } catch (e: any) {
    ui.toast(e?.message ?? '清空失败', 'error')
  }
}

onMounted(load)
</script>

<template>
  <section class="card memory">
    <header class="memory__head">
      <div>
        <h2>我的记忆</h2>
        <p class="memory__hint">
          助手会从对话中记住你的偏好，并在之后的对话里参考它们
        </p>
      </div>
      <!--
        「清空全部」固定在右上角（header 用 space-between，且它不参与换行），
        与下方气泡区之间另有分隔线，避免误触。
      -->
      <button
        v-if="activeItems.length"
        class="btn btn-ghost btn--sm memory__clear"
        @click="removeAll"
      >
        清空全部
      </button>
    </header>

    <p v-if="loading" class="memory__empty">加载中…</p>

    <p v-else-if="!items.length" class="memory__empty">
      还没有记忆。多聊几次旅行偏好（预算、节奏、饮食、去过的城市），助手就会慢慢记住。
    </p>

    <template v-else>
      <!-- 分隔线：把「清空全部」与气泡区分开，减少误触 -->
      <div class="memory__rule"></div>

      <p v-if="stats" class="memory__stats">
        共 {{ stats.total }} 条 · 生效 {{ stats.active }} 条<template v-if="stats.inactive"> · 已停用 {{ stats.inactive }} 条</template>
      </p>

      <!--
        气泡区：**局部滚动**。
        max-height + overflow-y 让记忆多时只在这里滚，页面本身不动 ——
        否则在个人主页往下滚会被这一块吸住，长列表还会把下方的
        密码/账号卡片一路推到底。
        点空白处或按 Esc 收起已展开的操作。
      -->
            <!--
        气泡区：两列瀑布流 + **局部滚动**。
        分列与限高滚动的理由见 script 里 distribute() 的注释
        （简言之：CSS 多列在受限高度下会向右溢出而不会竖向滚动）。
      -->
      <div
        class="bubbles"
        @click.self="closeOpened"
        @keydown.esc="closeOpened"
      >
        <div ref="colARef" class="bubbles__col" role="list" aria-label="记忆列表">
            <div
              v-for="m in colA"
              :key="m.id"
              class="bubble"
              :class="[bubbleTone(m.id), { 'bubble--open': openedId === m.id }]"
            >
              <!--
                点击气泡本体展开/收起元素操作。
                用 button 而不是 div + @click：键盘用户能 Tab 到、回车触发，
                aria-expanded 也能如实播报当前状态。
              -->
              <button
                class="bubble__body"
                type="button"
                :aria-expanded="openedId === m.id"
                :aria-label="`${m.fact_key_label}：${m.fact_value}，点击${openedId === m.id ? '收起' : '展开'}元素操作`"
                @click="toggleOpen(m)"
              >
                <span class="bubble__key">{{ m.fact_key_label }}</span>
                <span class="bubble__value">{{ m.fact_value }}</span>
                <span
                  v-if="m.hit_count > 1"
                  class="bubble__hit"
                  :title="`被重复提到 ${m.hit_count} 次`"
                >×{{ m.hit_count }}</span>
              </button>

              <!--
                「×」删除整条记忆，**常驻**在右上角。
                与点击气泡弹开的「−」分工明确：× 删整条、− 删单个元素。
                整条删除不可逆，故仍走一次确认。
              -->
              <button
                class="bubble__del"
                type="button"
                :disabled="busyId === m.id"
                :aria-label="`删除整条记忆「${m.fact_key_label}：${m.fact_value}」`"
                title="删除整条记忆"
                @click.stop="removeOne(m)"
              >×</button>

              <!--
                展开后的元素级操作：每个元素一行，行内右侧是「−」。
                只在**多值且不止一个元素**时出现 —— 只有一个元素时
                删掉它等于删整条，那条路径已经由右上角的 × 提供。
              -->
              <Transition name="bubble-act">
                <div
                  v-if="openedId === m.id && m.is_multi && m.values.length > 1"
                  class="bubble__items"
                >
                  <div v-for="v in m.values" :key="v" class="bubble__item">
                    <span class="bubble__item-text">{{ v }}</span>
                    <button
                      class="bubble__minus"
                      type="button"
                      :disabled="busyId === m.id"
                      :aria-label="`不再记住「${v}」`"
                      :title="`不再记住「${v}」（删完后整条会自动消失）`"
                      @click.stop="removeValue(m, v)"
                    >−</button>
                  </div>
                </div>
              </Transition>

              <!-- 次级信息与修正项：展开时才出现，平时让气泡保持干净 -->
              <Transition name="bubble-act">
                <div v-if="openedId === m.id" class="bubble__meta">
                  <span class="bubble__conf" :class="`bubble__conf--${confidenceTone(m.confidence)}`">
                    {{ confidenceText(m.confidence) }}
                  </span>
                  <span v-if="m.evidence" class="bubble__evi" :title="m.evidence">「{{ m.evidence }}」</span>
                </div>
              </Transition>

              <Transition name="bubble-act">
                <div v-if="openedId === m.id && editingId !== m.id" class="bubble__ops">
                  <button class="bubble__op" type="button" @click.stop="startEdit(m)">修正</button>
                  <button class="bubble__op" type="button" :disabled="busyId === m.id" @click.stop="toggle(m)">
                    停用
                  </button>
                </div>
              </Transition>

              <!-- 修正态：原地变成输入框，不弹窗 -->
              <div v-if="editingId === m.id" class="bubble__edit" @click.stop>
                <select
                  v-if="optionsFor(m.fact_key)"
                  v-model="draftValue"
                  class="select bubble__input"
                  :aria-label="`修改「${m.fact_key_label}」的取值`"
                >
                  <option v-for="o in optionsFor(m.fact_key)!" :key="o" :value="o">{{ o }}</option>
                </select>
                <input
                  v-else
                  v-model="draftValue"
                  class="input bubble__input"
                  maxlength="40"
                  :aria-label="`修改「${m.fact_key_label}」的取值`"
                />
                <button class="btn btn-primary btn--xs" :disabled="savingValue" @click="saveValue(m)">
                  保存
                </button>
                <button class="btn btn-ghost btn--xs" @click="cancelEdit">取消</button>
              </div>
            </div>
</div>
        </div>
        <div ref="colBRef" class="bubbles__col" role="list">
            <div
              v-for="m in colB"
              :key="m.id"
              class="bubble"
              :class="[bubbleTone(m.id), { 'bubble--open': openedId === m.id }]"
            >
              <!--
                点击气泡本体展开/收起元素操作。
                用 button 而不是 div + @click：键盘用户能 Tab 到、回车触发，
                aria-expanded 也能如实播报当前状态。
              -->
              <button
                class="bubble__body"
                type="button"
                :aria-expanded="openedId === m.id"
                :aria-label="`${m.fact_key_label}：${m.fact_value}，点击${openedId === m.id ? '收起' : '展开'}元素操作`"
                @click="toggleOpen(m)"
              >
                <span class="bubble__key">{{ m.fact_key_label }}</span>
                <span class="bubble__value">{{ m.fact_value }}</span>
                <span
                  v-if="m.hit_count > 1"
                  class="bubble__hit"
                  :title="`被重复提到 ${m.hit_count} 次`"
                >×{{ m.hit_count }}</span>
              </button>

              <!--
                「×」删除整条记忆，**常驻**在右上角。
                与点击气泡弹开的「−」分工明确：× 删整条、− 删单个元素。
                整条删除不可逆，故仍走一次确认。
              -->
              <button
                class="bubble__del"
                type="button"
                :disabled="busyId === m.id"
                :aria-label="`删除整条记忆「${m.fact_key_label}：${m.fact_value}」`"
                title="删除整条记忆"
                @click.stop="removeOne(m)"
              >×</button>

              <!--
                展开后的元素级操作：每个元素一行，行内右侧是「−」。
                只在**多值且不止一个元素**时出现 —— 只有一个元素时
                删掉它等于删整条，那条路径已经由右上角的 × 提供。
              -->
              <Transition name="bubble-act">
                <div
                  v-if="openedId === m.id && m.is_multi && m.values.length > 1"
                  class="bubble__items"
                >
                  <div v-for="v in m.values" :key="v" class="bubble__item">
                    <span class="bubble__item-text">{{ v }}</span>
                    <button
                      class="bubble__minus"
                      type="button"
                      :disabled="busyId === m.id"
                      :aria-label="`不再记住「${v}」`"
                      :title="`不再记住「${v}」（删完后整条会自动消失）`"
                      @click.stop="removeValue(m, v)"
                    >−</button>
                  </div>
                </div>
              </Transition>

              <!-- 次级信息与修正项：展开时才出现，平时让气泡保持干净 -->
              <Transition name="bubble-act">
                <div v-if="openedId === m.id" class="bubble__meta">
                  <span class="bubble__conf" :class="`bubble__conf--${confidenceTone(m.confidence)}`">
                    {{ confidenceText(m.confidence) }}
                  </span>
                  <span v-if="m.evidence" class="bubble__evi" :title="m.evidence">「{{ m.evidence }}」</span>
                </div>
              </Transition>

              <Transition name="bubble-act">
                <div v-if="openedId === m.id && editingId !== m.id" class="bubble__ops">
                  <button class="bubble__op" type="button" @click.stop="startEdit(m)">修正</button>
                  <button class="bubble__op" type="button" :disabled="busyId === m.id" @click.stop="toggle(m)">
                    停用
                  </button>
                </div>
              </Transition>

              <!-- 修正态：原地变成输入框，不弹窗 -->
              <div v-if="editingId === m.id" class="bubble__edit" @click.stop>
                <select
                  v-if="optionsFor(m.fact_key)"
                  v-model="draftValue"
                  class="select bubble__input"
                  :aria-label="`修改「${m.fact_key_label}」的取值`"
                >
                  <option v-for="o in optionsFor(m.fact_key)!" :key="o" :value="o">{{ o }}</option>
                </select>
                <input
                  v-else
                  v-model="draftValue"
                  class="input bubble__input"
                  maxlength="40"
                  :aria-label="`修改「${m.fact_key_label}」的取值`"
                />
                <button class="btn btn-primary btn--xs" :disabled="savingValue" @click="saveValue(m)">
                  保存
                </button>
                <button class="btn btn-ghost btn--xs" @click="cancelEdit">取消</button>
              </div>
            </div>
</div>
        </div>
      </div>

      <!-- 已停用（折叠） -->
      <template v-if="inactiveItems.length">
        <button class="memory__toggle" @click="showInactive = !showInactive">
          {{ showInactive ? '▾' : '▸' }} 已停用的记忆（{{ inactiveItems.length }}）
        </button>
        <ul v-if="showInactive" class="off-list">
          <li v-for="m in inactiveItems" :key="m.id" class="off-item">
            <span class="off-item__key">{{ m.fact_key_label }}</span>
            <span class="off-item__value">{{ m.fact_value }}</span>
            <span class="off-item__ops">
              <button class="bubble__op" type="button" :disabled="busyId === m.id" @click="toggle(m)">
                重新启用
              </button>
              <button
                class="bubble__op bubble__op--danger"
                type="button"
                :disabled="busyId === m.id"
                @click="removeOne(m)"
              >
                删除
              </button>
            </span>
          </li>
        </ul>
        <p class="memory__note">停用的记忆不会再影响对话，但仍保留在这里，随时可以重新启用。</p>
      </template>
    </template>
  </section>
</template>

<style scoped>
.memory { padding: 20px 22px; }

.memory__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;   /* 「清空全部」固定在右上角 */
  gap: 14px;
}
.memory__head h2 { font-size: 1.05rem; }
.memory__hint { margin-top: 4px; font-size: 0.8rem; color: var(--text3); }
/* 不参与换行：窗口变窄时它也不该掉到标题下面 */
.memory__clear { flex-shrink: 0; }

/*
 * 分隔线：把「清空全部」与气泡区分开。
 * 清空是不可逆操作，需要一条明确边界把它与「点气泡删单条」区分开，避免误触。
 */
.memory__rule {
  height: 1px;
  margin: 14px 0 12px;
  background: var(--hairline);
}

.memory__empty { padding: 22px 0; font-size: 0.85rem; color: var(--text3); }
.memory__stats { margin-bottom: 10px; font-size: 0.74rem; color: var(--text3); }

/* ============================================================
   气泡区：两列瀑布流 + 局部滚动
   ------------------------------------------------------------
   列由 JS 分配（见 script 的 distribute），这里只负责排布与滚动。
   不用 CSS 多列的原因见 script 注释：受限高度下多列会向右溢出、
   不会竖向滚动，实测三种写法都不行。
   ============================================================ */
.bubbles {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  max-height: 340px;
  overflow-y: auto;
  /* 滚到边界时不把滚动传给页面，否则用户想继续看下面的卡片却被这里吸住 */
  overscroll-behavior: contain;
  padding: 2px 8px 2px 2px;   /* 右侧给滚动条留位置，别贴着气泡 */

  /* 轻量滚动条：细、半透明 */
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}
.bubbles::-webkit-scrollbar { width: 6px; }
.bubbles::-webkit-scrollbar-track { background: transparent; }
.bubbles::-webkit-scrollbar-thumb { background: var(--border); border-radius: 999px; }
.bubbles::-webkit-scrollbar-thumb:hover { background: var(--blue-300); }

/* flex:1 + min-width:0：两列等宽，且长内容不会把列撑宽 */
.bubbles__col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* 窄屏单列：两列时气泡会被压得很窄，长值只能断成好几行 */
@media (max-width: 620px) {
  .bubbles { flex-direction: column; max-height: 300px; }
  .bubbles__col { width: 100%; }
}

/* ============================================================
   气泡
   ============================================================ */
.bubble {
  position: relative;
  margin-bottom: 10px;
  border-radius: 13px;
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}
.bubble:hover { transform: translateY(-1px); }
/* 展开时抬起来，与其它气泡区分 */
.bubble--open { box-shadow: var(--shadow-lift); }

.bubble__body {
  display: block;
  width: 100%;
  text-align: left;
  /* 右侧留出常驻 × 的位置，正文不会被它压住 */
  padding: 9px 30px 10px 12px;
  border: none;
  border-radius: 13px;
  background: transparent;
  cursor: pointer;
  font: inherit;
  color: var(--text);
}
.bubble__key {
  display: block;
  margin-bottom: 2px;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  opacity: 0.62;   /* 用不透明度而不是固定灰：跟随气泡色走，更协调 */
}
.bubble__value {
  display: block;
  font-size: 0.84rem;
  font-weight: 600;
  line-height: 1.5;
  /* 长值换行而不是撑破气泡 */
  overflow-wrap: anywhere;
}
/* 命中次数：小角标 */
.bubble__hit {
  display: inline-block;
  margin-top: 3px;
  font-family: var(--mono);
  font-size: 0.64rem;
  opacity: 0.5;
}
.bubble__body:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
  border-radius: 13px;
}

/* ---------- 配色：6 组浅色循环 ---------- */
.bubble--blue   { background: var(--blue-50);  box-shadow: 0 1px 2px rgba(37, 99, 235, 0.06); }
.bubble--cyan   { background: #eaf7fb;         box-shadow: 0 1px 2px rgba(14, 165, 233, 0.07); }
.bubble--green  { background: #eefaf1;         box-shadow: 0 1px 2px rgba(56, 161, 105, 0.07); }
.bubble--gold   { background: #fdf7e9;         box-shadow: 0 1px 2px rgba(214, 158, 46, 0.08); }
.bubble--violet { background: #f5f1fe;         box-shadow: 0 1px 2px rgba(139, 92, 246, 0.07); }
.bubble--amber  { background: #fff6ec;         box-shadow: 0 1px 2px rgba(217, 119, 6, 0.07); }

/* 悬停加深一档：用同色系阴影而不是加边框，避免整体发灰 */
.bubble--blue:hover   { box-shadow: 0 4px 12px rgba(37, 99, 235, 0.14); }
.bubble--cyan:hover   { box-shadow: 0 4px 12px rgba(14, 165, 233, 0.14); }
.bubble--green:hover  { box-shadow: 0 4px 12px rgba(56, 161, 105, 0.14); }
.bubble--gold:hover   { box-shadow: 0 4px 12px rgba(214, 158, 46, 0.16); }
.bubble--violet:hover { box-shadow: 0 4px 12px rgba(139, 92, 246, 0.14); }
.bubble--amber:hover  { box-shadow: 0 4px 12px rgba(217, 119, 6, 0.14); }

/* 深色主题：浅底在暗背景上发闷，改半透明底 */
:root[data-theme='dark'] .bubble--blue   { background: rgba(37, 99, 235, 0.16); }
:root[data-theme='dark'] .bubble--cyan   { background: rgba(14, 165, 233, 0.16); }
:root[data-theme='dark'] .bubble--green  { background: rgba(56, 161, 105, 0.16); }
:root[data-theme='dark'] .bubble--gold   { background: rgba(214, 158, 46, 0.16); }
:root[data-theme='dark'] .bubble--violet { background: rgba(139, 92, 246, 0.16); }
:root[data-theme='dark'] .bubble--amber  { background: rgba(217, 119, 6, 0.16); }

/* ---------- 右上角「×」：删整条，常驻 ---------- */
.bubble__del {
  position: absolute;
  top: 5px;
  right: 5px;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text3);
  font-size: 0.86rem;
  line-height: 1;
  cursor: pointer;
  /*
   * 常驻但很轻：默认透明度偏低，悬停/聚焦时才完全显形。
   * 完全隐藏会让人找不到这条路径；完全不透明又会让整片气泡显得全是按钮。
   */
  opacity: 0.55;
  transition: opacity 0.15s, color 0.15s, border-color 0.15s, background-color 0.15s;
}
.bubble:hover .bubble__del,
.bubble--open .bubble__del,
.bubble__del:focus-visible { opacity: 1; }
.bubble__del:hover:not(:disabled) {
  color: var(--danger);
  border-color: var(--danger);
  background: var(--panel);
}
.bubble__del:disabled { cursor: not-allowed; }

/* ---------- 元素级「−」：展开后每个元素一行 ---------- */
.bubble__items {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 10px 8px 12px;
}
/*
 * 每个元素一行、行内右侧放「−」。
 * 不做成「元素上方浮一个小按钮」：绝对定位会盖住相邻元素，
 * 元素一多就互相压。行内右侧既不遮挡，点击目标也更明确。
 */
.bubble__item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px 3px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.62);
}
:root[data-theme='dark'] .bubble__item { background: rgba(255, 255, 255, 0.06); }
.bubble__item-text {
  flex: 1;
  min-width: 0;
  font-size: 0.78rem;
  color: var(--text2);
  overflow-wrap: anywhere;
}
.bubble__minus {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 19px;
  height: 19px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text2);
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background-color 0.15s;
}
.bubble__minus:hover:not(:disabled) {
  color: var(--danger);
  border-color: var(--danger);
}
.bubble__minus:disabled { opacity: 0.5; cursor: not-allowed; }

/* ---------- 展开后的次级信息 ---------- */
.bubble__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  padding: 0 12px 6px;
  font-size: 0.68rem;
  color: var(--text3);
}
.bubble__conf--high { color: var(--green-600); }
.bubble__conf--mid { color: var(--text2); }
.bubble__conf--low { color: var(--gold-600); }
.bubble__evi {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.85;
}

.bubble__ops { display: flex; gap: 10px; padding: 0 12px 10px; }
.bubble__op {
  border: none;
  background: transparent;
  padding: 0;
  color: var(--prim);
  font-size: 0.74rem;
  cursor: pointer;
}
.bubble__op:hover:not(:disabled) { text-decoration: underline; }
.bubble__op:disabled { opacity: 0.5; cursor: not-allowed; }
.bubble__op--danger { color: var(--danger); }

.bubble__edit {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 0 12px 10px;
}
.bubble__input { max-width: 150px; padding: 4px 8px; font-size: 0.78rem; }

/* 展开内容的进出：轻微上移淡入 */
.bubble-act-enter-active,
.bubble-act-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.bubble-act-enter-from,
.bubble-act-leave-to { opacity: 0; transform: translateY(-3px); }

/* ---------- 已停用（沿用简洁列表：次要信息，不做气泡） ---------- */
.memory__toggle {
  margin-top: 12px;
  border: none;
  background: transparent;
  padding: 0;
  color: var(--text3);
  font-size: 0.78rem;
  cursor: pointer;
}
.memory__toggle:hover { color: var(--prim); }
.memory__note { margin-top: 8px; font-size: 0.72rem; color: var(--text3); line-height: 1.7; }

.off-list { list-style: none; margin: 8px 0 0; padding: 0; }
.off-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  font-size: 0.78rem;
  border-bottom: 1px solid var(--hairline);
}
.off-item:last-child { border-bottom: none; }
.off-item__key { flex-shrink: 0; color: var(--text3); }
.off-item__value { flex: 1; min-width: 0; color: var(--text2); }
.off-item__ops { display: flex; gap: 10px; flex-shrink: 0; }

@media (prefers-reduced-motion: reduce) {
  .bubble,
  .bubble-act-enter-active,
  .bubble-act-leave-active { transition: none; }
  .bubble:hover { transform: none; }
}
</style>
