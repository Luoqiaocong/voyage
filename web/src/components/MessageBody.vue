<script setup lang="ts">
/**
 * MessageBody · 助手消息的结构化渲染
 *
 * 只负责「怎么画」，解析规则全部在 @/utils/messageParse（纯函数，可单测）。
 * 拆开的原因：解析是这里的主要复杂度，留在 SFC 里就无法独立验证。
 */
import { computed } from 'vue'
import {
  parseMessage,
  toSpans,
  groupBySlot,
  detectSlot,
  stripSlotPrefix,
  type Block
} from '@/utils/messageParse'

interface Props {
  /** markdown 原文 */
  text: string
  /** 是否处于流式输出中 */
  streaming?: boolean
}
const props = withDefaults(defineProps<Props>(), { streaming: false })

const emit = defineEmits<{ (e: 'extract'): void }>()

/**
 * 流式期间**同样做结构化解析**，不要退化成纯文本。
 *
 * 曾经的做法是流式时整段当纯文本渲染，理由是「末块可能只写了一半，
 * 中途解析会让内容在段落与列表间跳变」。实测这个取舍是错的，代价远大于收益：
 *
 *   1. 生成过程可能持续 20~100 秒，这段时间用户看到的是一整团糊在一起的
 *      原始 markdown —— 既没有小标题层次，也没有列表缩进，因为纯文本
 *      容器不保留换行（见 .mb__p 的 white-space 说明）。
 *   2. `**粗体**` 在流式期被当作行内粗体渲染成蓝色，而流结束后同一段文字
 *      变成小节标题（黑色）——用户看到「蓝字闪一下又没了」。
 *   3. 结构化本身就是「正在生成」的最好提示，比一个光标更有信息量。
 *
 * 跳变问题实际很轻微：解析器把未写完的行当作普通段落，等换行符到达再
 * 归入列表。真正会变的只有最后一行，用户注意力本就在新增内容上。
 */
const blocks = computed<Block[]>(() => parseMessage(props.text))
</script>

<template>
  <div class="mb">
    <template v-for="(b, i) in blocks" :key="i">
      <!-- 小节标题 -->
      <h4 v-if="b.kind === 'heading'" class="mb__h" :class="`mb__h--${b.level}`">
        {{ b.text }}
      </h4>

      <!-- 分隔线 -->
      <hr v-else-if="b.kind === 'divider'" class="mb__hr" />

      <!-- 提示块 -->
      <aside v-else-if="b.kind === 'tip'" class="mb__tip">
        <span class="mb__tip-icon" aria-hidden="true">💡</span>
        <p>{{ b.text }}</p>
      </aside>

      <!--
        表格：车次、票价、天气这类多列信息的正确形态。
        解析器原先不认 markdown 表格，那些行落进普通段落被渲染成
        一堆竖线与短横线的原始文本，看起来「很乱」。
        首列用等宽字体并加粗：车次号、日期这类标识符最需要纵向对齐比对。
      -->
      <div v-else-if="b.kind === 'table' && b.table" class="mb__table-wrap">
        <table class="mb__table">
          <thead>
            <tr>
              <th v-for="(h, hi) in b.table.headers" :key="hi">
                <span
                  v-for="(sp, si) in toSpans(h)"
                  :key="si"
                  :class="{ 'mb__b': sp.bold }"
                >{{ sp.text }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in b.table.rows" :key="ri">
              <td
                v-for="(cell, ci) in row"
                :key="ci"
                :class="{ 'mb__table-first': ci === 0 }"
              >
                <span
                  v-for="(sp, si) in toSpans(cell)"
                  :key="si"
                  :class="{ 'mb__b': sp.bold }"
                >{{ sp.text }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 行程片段：可直接提取 -->
      <section v-else-if="b.kind === 'itinerary'" class="mb__trip">
        <header class="mb__trip-head">
          <span class="mb__trip-tag">行程片段</span>
          <button type="button" class="mb__trip-btn" @click="emit('extract')">
            提取为行程
          </button>
        </header>
        <ol class="mb__days">
          <li v-for="(d, di) in b.days" :key="di" class="mb__day">
            <span class="mb__day-no">{{ d.no }}</span>
            <span class="mb__day-body">
              <b v-if="d.theme">{{ d.theme }}</b>
              <!--
                按时段归组，而不是每条前面都挂「上午/下午/晚上」。
                同一天内常有连续几条属于同一时段，重复标签会淹没真正的内容。
                组内条目保持原有顺序（那通常就是模型给的合理安排）。
              -->
              <span
                v-for="(g, gi) in groupBySlot(d.slots, detectSlot)"
                :key="gi"
                class="mb__slot-group"
              >
                <em v-if="g.label" class="mb__slot-label">{{ g.label }}</em>
                <span v-for="(s, si) in g.items" :key="si" class="mb__slot-item">
                  {{ stripSlotPrefix(s) }}
                </span>
              </span>
            </span>
          </li>
        </ol>
      </section>

      <!-- 条目列表（推荐卡的轻量形态） -->
      <ul v-else-if="b.kind === 'list'" class="mb__list">
        <li v-for="(it, ii) in b.items" :key="ii" class="mb__item">
          <span v-if="it.icon" class="mb__item-icon" aria-hidden="true">{{ it.icon }}</span>
          <span v-else class="mb__item-dot" aria-hidden="true"></span>
          <span class="mb__item-body">
            <b v-if="it.title">{{ it.title }}</b>
            <span v-if="it.desc" class="mb__item-desc">
              <template v-if="it.title">：</template>{{ it.desc }}
            </span>
          </span>
        </li>
      </ul>

      <!-- 普通段落（支持行内粗体） -->
      <p v-else class="mb__p">
        <template v-for="(s, si) in toSpans(b.text)" :key="si">
          <b v-if="s.bold">{{ s.text }}</b>
          <template v-else>{{ s.text }}</template>
        </template>
      </p>

      <!--
        流式光标只在末块是**段落**时显示。
        末块是列表/行程/标题时不画——那些块无法自然地容纳一个行内光标，
        硬塞进去会让布局变形；而「正在生成」的信号并不依赖它：
        工具条有状态文字、首字等待区有三点动画，光标只是锦上添花。
      -->
      <span
        v-if="streaming && i === blocks.length - 1 && b.kind === 'para'"
        class="mb__caret"
        aria-hidden="true"
      ></span>
    </template>
  </div>
</template>

<style scoped>
.mb {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 0.94rem;
  line-height: 1.78;
  color: var(--text);
}

/* ---------- 小节标题 ---------- */
/* 纯文字加粗即可。
   原设计在标题左侧画了一道渐变竖线，实测显得杂乱——一段回答里
   往往有三四个小标题，每条都挂一道竖线，视觉噪音盖过了层次本身。 */
.mb__h {
  margin: 6px 0 0;
  font-size: 0.95rem;
  font-weight: 700;
  line-height: 1.6;
}
.mb__h--1,
.mb__h--2 {
  font-size: 1.02rem;
}

.mb__hr {
  border: none;
  border-top: 1px solid var(--hairline);
  margin: 4px 0;
}

/* ---------- 段落 ---------- */
/*
 * pre-wrap 是必需的：解析器把同一段落内的多行用空格拼接，
 * 但模型偶尔会在段内换行（例如「交通：…\n住宿：…」这种不成列表的写法）。
 * 不留住换行，这些内容会被挤成一整行，看起来就是「乱」。
 */
.mb__p {
  margin: 0;
  white-space: pre-wrap;
}
.mb__p b {
  font-weight: 700;
  color: var(--blue-700);
}

/* 流式光标：贴着最后一个字，随文字增长自然右移 */
.mb__caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -0.14em;
  border-radius: 1px;
  background: var(--prim);
  animation: mbCaret 1.05s steps(2) infinite;
}
@keyframes mbCaret {
  50% { opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .mb__caret { animation: none; }
}

/* ---------- 提示块 ---------- */
.mb__tip {
  display: flex;
  gap: 9px;
  padding: 11px 14px;
  border-radius: 10px;
  background: var(--gold-soft);
  border: 1px solid rgba(214, 158, 46, 0.22);
}
.mb__tip p {
  margin: 0;
  font-size: 0.89rem;
  line-height: 1.7;
  color: var(--gold-600);
}
.mb__tip-icon {
  flex-shrink: 0;
  line-height: 1.7;
}

/* ---------- 条目列表 ---------- */
.mb__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.mb__item {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 7px 10px;
  border-radius: 8px;
  line-height: 1.7;
  transition: background-color 0.18s;
}
.mb__item:hover {
  background: var(--panel2);
}
.mb__item-icon {
  flex-shrink: 0;
  font-size: 0.95rem;
  line-height: 1.75;
}
/* 无 emoji 的条目用一个小圆点，保持左缘对齐 */
.mb__item-dot {
  flex-shrink: 0;
  width: 5px;
  height: 5px;
  margin-top: 0.72em;
  border-radius: 50%;
  background: var(--blue-300);
}
.mb__item-body {
  min-width: 0;
}
.mb__item-body b {
  font-weight: 700;
  color: var(--blue-700);
}
.mb__item-desc {
  color: var(--text2);
}

/* ---------- 行程片段 ---------- */
.mb__trip {
  border: 1px solid var(--blue-200);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.035), transparent 60%);
  overflow: hidden;
}
.mb__trip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 13px;
  border-bottom: 1px solid var(--blue-100, var(--hairline));
}
.mb__trip-tag {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--prim);
}
.mb__trip-btn {
  padding: 5px 12px;
  border-radius: 7px;
  background: var(--panel);
  border: 1px solid var(--blue-200);
  color: var(--prim);
  font-size: 0.77rem;
  font-weight: 650;
  transition: background-color 0.18s, border-color 0.18s, transform 0.18s;
}
.mb__trip-btn:hover {
  background: var(--primary-soft);
  border-color: var(--prim);
  transform: translateY(-1px);
}

/* ---- 表格 ----
   模型给车次/票价/天气这类多列信息时会写 markdown 表格。
   外层 wrap 负责横向滚动：列多时（车次表常有 5~6 列）窄屏必然放不下，
   让表格自己滚而不是撑破消息区。 */
.mb__table-wrap {
  overflow-x: auto;
  margin: 4px 0;
  border: 1px solid var(--line);
  border-radius: var(--r-s);
}

.mb__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.mb__table th,
.mb__table td {
  padding: 8px 12px;
  text-align: left;
  white-space: nowrap;   /* 单元格不折行，避免「G1234」被拆成两行 */
  border-bottom: 1px solid var(--hairline);
}

/* 表头：淡底 + 深字，与数据行拉开层次 */
.mb__table th {
  background: var(--surface-soft);
  font-weight: 650;
  color: var(--text);
  font-size: 0.8rem;
}

.mb__table tbody tr:last-child td { border-bottom: none; }
/* 悬停整行高亮：横向比对车次时不容易看错行 */
.mb__table tbody tr:hover { background: var(--blue-50); }

/* 首列用等宽并加粗：车次号、日期这类标识符最需要纵向对齐 */
.mb__table-first {
  font-family: var(--mono);
  font-weight: 650;
  color: var(--text);
}

/* 行内 **粗体** */
.mb__b { font-weight: 650; }

.mb__days {
  list-style: none;
  margin: 0;
  padding: 8px 13px 11px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mb__day {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 11px;
  align-items: start;
}
.mb__day-no {
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--prim);
  background: var(--primary-soft);
  border-radius: 6px;
  padding: 3px 0;
  text-align: center;
}
.mb__day-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.mb__day-body b {
  font-size: 0.87rem;
  font-weight: 650;
}

/* ---- 时段分组 ----
   组标题（上午/下午/晚上）以左侧一道细线+小字呈现，
   与「条目正文」形成层次；条目本身不再带时段词。 */
.mb__slot-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-left: 10px;
  border-left: 2px solid var(--blue-100, var(--hairline));
}
.mb__slot-label {
  font-style: normal;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--blue-700);
  letter-spacing: 0.02em;
}
.mb__slot-item {
  font-size: 0.86rem;
  color: var(--text2);
  line-height: 1.65;
}

/* ---------- 移动端 ---------- */
@media (max-width: 620px) {
  .mb {
    font-size: 0.92rem;
    gap: 9px;
  }
  .mb__item {
    padding: 6px 4px;
  }
  .mb__day {
    grid-template-columns: 46px 1fr;
    gap: 9px;
  }
}
</style>
