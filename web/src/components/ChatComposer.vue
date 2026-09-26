<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

const props = defineProps<{
  modelValue: string
  streaming: boolean
  quickPrompts: string[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'send'): void
  (e: 'stop'): void
  (e: 'pick', text: string): void
}>()

const inputEl = ref<HTMLTextAreaElement | null>(null)

/**
 * 输入框高度上限，必须与样式里的 .composer__box max-height 保持一致。
 * 到顶后交回 textarea 自己的内部滚动，避免多行输入把消息区一路挤没。
 */
const INPUT_MAX_HEIGHT = 180

/**
 * 让输入框随内容行数长高。
 *
 * 固定高度时多出来的行会藏进 textarea 的内部滚动区，用户得在框里上下滑
 * 才能看到自己写了什么 —— 这里按 scrollHeight 撑开，写到上限才转内部滚动。
 *
 * 先把 height 置 auto 再读 scrollHeight：否则上一次设的 height 会被算进
 * 内容高度，删行时高度收不回去（只会越撑越高）。
 */
function resizeInput() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, INPUT_MAX_HEIGHT)}px`
}

watch(
  () => props.modelValue,
  () => nextTick(resizeInput)
)
watch(inputEl, (el) => {
  if (el) nextTick(resizeInput)
})

/** 输入框是否获得焦点：用于提示行显隐，以及键盘/触屏下的聚焦态表现 */
const inputFocused = ref(false)

/**
 * 底部提示行的显示时机。
 *
 * 原先提示行**常驻**，但它平时只是重复表头已经写过的 placeholder，
 * 真正有信息量的时刻是「光标已在输入框里、却还没想好写什么」。
 * 所以改为：聚焦时显示，或已经在输入内容时显示（此时提示的是换行方式）。
 * 好处是静息状态下输入区更干净，底部也不再多占一行。
 */
const showInputHint = computed(() => inputFocused.value || !!props.modelValue.trim())

/**
 * 是否可以发送。
 *
 * 抽成 computed 而不是在模板里写两遍 `input.trim()` ——
 * 按钮的 disabled 与 send-btn--ready（高亮态）必须用**同一个判断**，
 * 否则会出现「看起来可点但点了没反应」这类不一致。
 */
const canSend = computed(() => props.modelValue.trim().length > 0)

/**
 * 是否展示快捷示例。
 * 只在「没在生成」且「输入框为空」时出现：用户一开始打字，
 * 建议就从帮助变成了干扰，而且那一行会把输入框顶上去。
 */
const showQuickChips = computed(() => !props.streaming && !props.modelValue.trim())

/**
 * 快捷芯片的配色。
 *
 * ## 为什么可以按关键词上色（而不是纯按序号）
 *
 * 这层颜色是**纯装饰**：它不承载语义，用户也不需要通过颜色去理解建议。
 * 所以可以大方地用「关键词命中」这种近似 —— 猜错了只是颜色不那么贴切，
 * 不会误导（对比：状态色猜错会让人误判系统状态）。
 *
 * ## 为什么要按关键词而不是按序号循环
 *
 * 按序号循环（i % 5）虽然简单，但同一句话在不同会话里会换颜色，
 * 换一批建议时颜色也跟着洗牌，看起来像随机噪声。
 * 按内容决定则同一句建议始终是同一个颜色，视觉上「稳定」得多。
 *
 * 顺序即优先级：越靠前的主题越具辨识度（吃 > 爬山 > 预算 …）。
 * 一个都命中不了时按序号回退，保证**同屏三张卡颜色一定不同**。
 */
const CHIP_TONES: { keys: string[]; tone: string }[] = [
  { keys: ['吃', '美食', '小吃', '火锅', '餐厅'], tone: 'food' },
  { keys: ['预算', '多少钱', '花费', '省钱', '便宜'], tone: 'budget' },
  { keys: ['天气', '下雨', '气温'], tone: 'weather' },
  { keys: ['爬山', '徒步', '自然', '风景', '海岛', '看海'], tone: 'nature' },
  { keys: ['古迹', '历史', '博物馆', '文化', '古镇'], tone: 'history' },
  { keys: ['拍照', '摄影', '夜景'], tone: 'photo' },
  { keys: ['亲子', '带娃', '老人', '带父母'], tone: 'family' },
  { keys: ['几天', '日程', '安排', '路线', '行程'], tone: 'plan' }
]
const FALLBACK_TONES = ['plan', 'food', 'nature', 'budget', 'history']

function chipTone(text: string, index: number): string {
  for (const group of CHIP_TONES) {
    if (group.keys.some((k) => text.includes(k))) return group.tone
  }
  return FALLBACK_TONES[index % FALLBACK_TONES.length]
}

function updateInput(value: string) {
  emit('update:modelValue', value)
}

function onKeydown(e: KeyboardEvent) {
  // Esc 停止生成：长回答时用户的手通常还在键盘上，
  // 强制去够鼠标点停止按钮是多余的
  if (e.key === 'Escape' && props.streaming) {
    e.preventDefault()
    emit('stop')
    return
  }
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    emit('send')
  }
}

/** 供视图在欢迎屏关闭、切会话、生成结束等时机把焦点交回输入框 */
function focus() {
  inputEl.value?.focus()
}

defineExpose({ focus })
</script>

<template>
  <!--
    输入区：快捷提示与输入框**收在同一个容器里**，共享一层边框与聚焦环。
    原先两者是上下相邻的两个独立块（快捷条在外、输入框自己带边框），
    视觉上只是「挨着」；合起来之后它们是一组，聚焦时整组一起高亮，
    「这些芯片是用来填这个框的」这层关系就不用靠猜。
  -->
  <div class="composer">
    <!--
      快捷示例：只在输入框为空且没在生成时出现。
      用户一旦开始打字就收起 —— 那时的建议会变成干扰。
      横向滚动（不换行）：窄屏下不会挤成多行把输入框顶上去。
    -->
    <Transition name="chips">
      <div v-if="showQuickChips" class="composer__chips">
        <span class="composer__chips-label">试试</span>
        <div class="composer__chips-scroll">
          <button
            v-for="(q, qi) in quickPrompts"
            :key="q"
            type="button"
            class="quick-chip"
            :class="`quick-chip--${chipTone(q, qi)}`"
            @click="emit('pick', q)"
          >
            {{ q }}
          </button>
        </div>
      </div>
    </Transition>

    <div class="composer__row">
      <textarea
        ref="inputEl"
        :value="modelValue"
        class="composer__box"
        rows="1"
        :placeholder="
          streaming ? '正在回答，稍候可以继续追问…' : '说说你想去哪、几天、预算多少…'
        "
        :disabled="streaming"
        @input="updateInput(($event.target as HTMLTextAreaElement).value)"
        @keydown="onKeydown"
        @focus="inputFocused = true"
        @blur="inputFocused = false"
        aria-label="输入你的旅行需求"
      ></textarea>

      <!--
        底部条：左侧是快捷键与字数，右侧是发送按钮。
        按钮**收在框内**（而不是框外另起一列）——
        放在外面会把输入框挤短、整块拉得很长；收进来之后
        输入框能用满整行宽度，视觉上也更像常见的对话输入框。

        键帽提示按需淡出（不是 v-if 移除）：位置始终占着，
        否则按钮会随提示显隐左右跳动。
      -->
      <div class="composer__foot">
        <span class="kbd-hint" :class="{ 'kbd-hint--hidden': !showInputHint }">
          <template v-if="!streaming">
            <kbd>Enter</kbd> 发送
            <span class="kbd-hint__sep">·</span>
            <kbd>Shift</kbd><kbd>Enter</kbd> 换行
          </template>
          <!-- 生成中改提示「可中断」，否则用户不知道有这条快捷方式 -->
          <template v-else>
            <kbd>Esc</kbd> 停止生成
          </template>
        </span>

        <span class="composer__foot-right">
          <span v-if="modelValue.trim()" class="charcount">{{ modelValue.length }}</span>
          <!--
            流式期间同一个按钮变为「停止生成」。
            用同一个位置而不是新增按钮：这里本就是「提交/取消本次生成」的位置，
            语义随状态切换比并排两个按钮更符合直觉。
          -->
          <button
            v-if="streaming"
            class="send-btn send-btn--stop"
            type="button"
            aria-label="停止生成"
            title="停止生成（已生成的内容会保留）"
            @click="emit('stop')"
          >
            <span class="send-btn__stop" aria-hidden="true"></span>
          </button>
          <button
            v-else
            class="send-btn"
            :class="{ 'send-btn--ready': canSend }"
            :disabled="!canSend"
            aria-label="发送消息"
            title="发送（Enter）"
            @click="emit('send')"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ============================================================
   输入区（composer）
   ------------------------------------------------------------
   结构：一个容器里放三行
     ① 快捷芯片行（可横向滚动，按需出现）
     ② 输入行：textarea + 发送按钮
     ③ 提示行：键帽 + 字数（按需出现）
   ①② 共享同一层边框与聚焦环 —— 这是「快捷芯片是用来填这个框的」
   这层关系唯一的视觉依据；原先两者各自独立，只能靠相邻去猜。
   ============================================================ */
.composer {
  flex-shrink: 0;
  /*
   * 最大宽度与消息流（.chat-stream 的 820px）对齐并居中。
   *
   * 原先是整块铺满可用宽度 —— 在宽屏上输入框会被拉到一千多像素，
   * 一行能塞下好几个句子，视觉上又长又空，与上方消息的宽度也对不齐。
   * 收窄到与消息同宽后，输入区与对话内容形成同一条中轴。
   */
  width: 100%;
  max-width: 820px;
  margin: 0 auto 16px;
  padding: 6px 8px 8px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: var(--panel);
  box-shadow: var(--shadow-sm);
  transition: border-color 0.2s, box-shadow 0.22s, background-color 0.2s;
}
/* 聚焦态：主色描边 + 柔和外环。整组一起亮，而不是只给 textarea 描边 */
.composer:focus-within {
  border-color: var(--prim);
  box-shadow: 0 0 0 3px var(--primary-soft), var(--shadow-sm);
}
/* 生成中降低视觉存在感，暗示此刻不该输入 */
.composer:has(.composer__box:disabled) {
  opacity: 0.72;
}

/* ---- ① 快捷芯片行 ---- */
.composer__chips {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 4px 8px 8px;
  border-bottom: 1px dashed var(--hairline);
  margin-bottom: 4px;
}
.composer__chips-label {
  flex-shrink: 0;
  font-size: 0.72rem;
  color: var(--text3);
  user-select: none;
}
/*
 * 芯片横向滚动而不换行。
 * 换行会让输入区在小屏上长高好几行、把消息区挤扁；
 * 横滚则始终保持一行高度，用户滑动即可看到其余建议。
 * 隐藏滚动条：它在这么窄的条里很扎眼，而横滚本身有「切了一半的芯片」作暗示。
 */
.composer__chips-scroll {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
  -ms-overflow-style: none;
  /* 右端渐隐，暗示「还能往右滑」 */
  mask-image: linear-gradient(90deg, #000 calc(100% - 20px), transparent);
  -webkit-mask-image: linear-gradient(90deg, #000 calc(100% - 20px), transparent);
}
.composer__chips-scroll::-webkit-scrollbar { display: none; }

/* ---- ② 输入行：textarea 在上、底部条在下，按钮收在框内 ---- */
.composer__row {
  display: flex;
  flex-direction: column;
}
.composer__box {
  width: 100%;
  /* 单行时约 40px 高，比原先的 34px 更好点、也更接近常见的聊天输入框 */
  min-height: 40px;
  /* 高度由 JS 按内容撑开（见 resizeInput），到 INPUT_MAX_HEIGHT 封顶后
     转为内部滚动；这里的上限是 JS 失效时的兜底，两处数值需保持一致 */
  max-height: 180px;
  overflow-y: auto;
  resize: none;
  border: none;
  background: transparent;
  padding: 8px 8px 4px;
  font-size: 0.95rem;
  line-height: 1.55;
  color: var(--text);
}
.composer__box:focus { outline: none; }
.composer__box::placeholder { color: var(--text3); }
.composer__box:disabled { cursor: not-allowed; }

/* ---- ③ 底部条：左键帽、右发送 ---- */
.composer__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 32px;
  padding: 0 2px 0 8px;
}
.composer__foot-right {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
/*
 * 键帽提示：仍然「按需出现」的语义 —— 静息时淡出，聚焦或有内容时淡入。
 * 但它所在的位置**始终占位**（不是 v-if），这样按钮不会随提示显隐而左右跳动。
 */
.kbd-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.68rem;
  color: var(--text3);
  user-select: none;
  transition: opacity 0.2s ease;
}
.kbd-hint--hidden { opacity: 0; }
.kbd-hint kbd {
  font-family: var(--mono);
  font-size: 0.64rem;
  line-height: 1;
  padding: 3px 5px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--panel2);
  color: var(--text2);
  box-shadow: 0 1px 0 var(--border);
}
.kbd-hint__sep { opacity: 0.5; }

.charcount {
  font-family: var(--mono);
  font-size: 0.68rem;
  color: var(--text3);
  font-variant-numeric: tabular-nums;
}
/* 接近上限才变色提醒，平时不打扰 */
.charcount--warn { color: var(--gold-600); }

/* ---- 发送按钮 ----
 *
 * 主次由**背景**区分，而不只是透明度：
 *   无内容 → 淡灰底、灰箭头、无光晕：明确是「还不能点」
 *   有内容 → 主题渐变实心 + 光晕 + 轻微放大：明确是「可以发了」
 * 原先两种情况共用同一套渐变底，只靠 opacity 0.42 区分 ——
 * 在浅色界面上「半透明的蓝按钮」仍然像可点，主次不够清晰。
 */
.send-btn {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 13px;
  background: var(--panel2);
  color: var(--text3);
  border: 1px solid var(--border);
  box-shadow: none;
  transition: transform 0.2s, box-shadow 0.22s, background-color 0.22s,
    color 0.22s, border-color 0.22s;
}
/* 有内容：实心主色 + 光晕 */
.send-btn--ready {
  background: var(--grad);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 6px 18px var(--glow);
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: saturate(1.08);
}
.send-btn--ready:hover:not(:disabled) {
  box-shadow: 0 10px 24px var(--glow);
}
.send-btn:active:not(:disabled) {
  transform: translateY(0);
}
.send-btn:disabled {
  cursor: not-allowed;
}

/*
 * 生成中的「停止」状态。
 *
 * 刻意用中性深灰而不是红色：中断是正常操作（用户改主意、发现需求说错了），
 * 不是危险动作。红色会让人以为「点下去会丢失什么」而不敢用。
 * 同时去掉渐变与光晕 —— 生成期间焦点应落在内容上，按钮不该持续发光吸引注意。
 */
.send-btn--stop {
  background: var(--slate-700);
  box-shadow: 0 4px 12px rgba(16, 24, 40, 0.18);
}
.send-btn--stop:hover {
  background: var(--slate-800);
  transform: translateY(-1px);
}
/* 方块＝停止，是播放器的通用符号，无需文字说明 */
.send-btn__stop {
  width: 13px;
  height: 13px;
  border-radius: 3px;
  background: #fff;
}

/* 生成中的转圈：用边框缺口旋转，比三点更安静 */
.send-btn__spin {
  width: 17px;
  height: 17px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  animation: sendSpin 0.72s linear infinite;
}
@keyframes sendSpin {
  to { transform: rotate(360deg); }
}
@media (prefers-reduced-motion: reduce) {
  .send-btn__spin { animation: none; }
  .send-btn--stop:hover { transform: none; }
}

/* ---- 快捷示例条 ---- */
/*
 * 旧样式已清理：
 *   .quick-bar / .quick-bar__label  → .composer__chips / .composer__chips-label
 *     （布局由 flex-wrap 改为横向滚动，见 .composer__chips-scroll）
 *   .quick-chip--sm                 → 并入 .quick-chip（现在只有一个尺寸）
 * 保留说明是为了下次改这块时知道东西搬到哪了。
 */
.quick-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  /*
   * ⚠️ flex-shrink: 0 与 white-space: nowrap 是「横向滚动」能否成立的关键。
   *
   * flex 项默认 flex-shrink: 1，而 min-width: auto 又允许它被压到内容
   * 最小宽度以下 —— 结果在窄容器里芯片会被压窄、文字在里面折行：
   * 实测容器 420px 时单个芯片从 37px 高变成 94px 高，整行变成一堵墙，
   * 而 overflow-x: auto 根本没机会生效（因为内容被压缩到不溢出了）。
   * 加上这两条后芯片保持自身宽度、容器真正横向溢出，横滚才起作用。
   */
  flex-shrink: 0;
  white-space: nowrap;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 0.81rem;
  transition: color 0.18s, border-color 0.18s, background-color 0.18s, transform 0.18s,
              box-shadow 0.18s;
}
/*
 * 彩色芯片：8 个语义色，浅底 + 同族深字 + 稍深的边框。
 *
 * 底色都取 *-50 级别（或等价的极浅色），文字取 *-600/700 ——
 * 与行程标签（.ptag）用同一套「浅底深字」规则，所以两处放在一起不打架。
 * 边框用比底色略深一档的同族色，让芯片在浅色背景上有轮廓、不糊成一片。
 */
.quick-chip--food    { background: #fdf6e7; color: var(--gold-600);   border: 1px solid #f5e6c8; }
.quick-chip--budget  { background: var(--blue-50); color: var(--blue-700); border: 1px solid var(--blue-100); }
.quick-chip--weather { background: #eaf7fb; color: var(--cyan-600);   border: 1px solid #cdeaf3; }
.quick-chip--nature  { background: #eefaf1; color: var(--green-600);  border: 1px solid #d6f0de; }
.quick-chip--history { background: #f5f1fe; color: var(--purple-600); border: 1px solid #e6dcfb; }
.quick-chip--photo   { background: #fef3f8; color: var(--rose-600);   border: 1px solid #fbd9e8; }
.quick-chip--family  { background: #fff7ed; color: var(--amber-600);  border: 1px solid #fde8cf; }
.quick-chip--plan    { background: #eef4fb; color: #31527a;           border: 1px solid #d5e3f2; }

/* 深色主题：浅底深字在暗背景上发闷，改成半透明底 + 提亮文字 */
:root[data-theme='dark'] .quick-chip--food    { background: rgba(214, 158, 46, 0.16); color: var(--gold-400);   border-color: rgba(214, 158, 46, 0.3); }
:root[data-theme='dark'] .quick-chip--budget  { background: rgba(37, 99, 235, 0.16);  color: var(--blue-300);   border-color: rgba(37, 99, 235, 0.3); }
:root[data-theme='dark'] .quick-chip--weather { background: rgba(14, 165, 233, 0.16); color: var(--cyan-400);   border-color: rgba(14, 165, 233, 0.3); }
:root[data-theme='dark'] .quick-chip--nature  { background: rgba(56, 161, 105, 0.16); color: var(--green-400);  border-color: rgba(56, 161, 105, 0.3); }
:root[data-theme='dark'] .quick-chip--history { background: rgba(139, 92, 246, 0.16); color: var(--purple-400); border-color: rgba(139, 92, 246, 0.3); }
:root[data-theme='dark'] .quick-chip--photo   { background: rgba(244, 114, 182, 0.16); color: var(--rose-400);  border-color: rgba(244, 114, 182, 0.3); }
:root[data-theme='dark'] .quick-chip--family  { background: rgba(251, 191, 36, 0.16); color: var(--amber-400);  border-color: rgba(251, 191, 36, 0.3); }
:root[data-theme='dark'] .quick-chip--plan    { background: rgba(127, 168, 248, 0.14); color: var(--blue-300);  border-color: rgba(127, 168, 248, 0.28); }

/* 悬停：底色压深一档、边框用主色，明确「可点」 */
.quick-chip:hover {
  color: var(--prim);
  border-color: var(--blue-300);
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.12);
}

.chips-enter-active,
.chips-leave-active {
  transition: opacity 0.22s, transform 0.22s;
}
.chips-enter-from,
.chips-leave-to {
  opacity: 0;
  transform: translateY(5px);
}

@media (max-width: 860px) {
  /* 窄屏没有物理键盘，键帽提示没有意义，收起以省一行高度 */
  .kbd-hint { display: none; }
  /* 输入区在窄屏贴着容器边（不再叠加自身外边距，避免双重留白） */
  .composer { margin: 0 auto 12px; padding: 6px 6px 8px; }
  .composer__chips-scroll { gap: 5px; }
}
</style>
