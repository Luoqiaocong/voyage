<script setup lang="ts">
/**
 * MessageBody · 助手消息的结构化渲染
 *
 * 只负责「怎么画」，解析规则全部在 @/utils/messageParse（纯函数，可单测）。
 * 拆开的原因：解析是这里的主要复杂度，留在 SFC 里就无法独立验证。
 */
import { computed } from 'vue'
import { parseMessage, toSpans, SLOT_RE, type Block } from '@/utils/messageParse'

interface Props {
  /** markdown 原文 */
  text: string
  /** 是否处于流式输出中 */
  streaming?: boolean
}
const props = withDefaults(defineProps<Props>(), { streaming: false })

const emit = defineEmits<{ (e: 'extract'): void }>()

/**
 * 流式输出时不结构化：末块可能只写了一半，中途解析会让内容在
 * 「段落 ↔ 列表」之间反复跳变，比不做还乱。
 */
const blocks = computed<Block[]>(() =>
  props.streaming ? [{ kind: 'para', text: props.text }] : parseMessage(props.text)
)
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
              <span v-for="(s, si) in d.slots" :key="si" class="mb__slot">
                <em>{{ s.match(SLOT_RE)?.[0] ?? '安排' }}</em>
                {{ s.replace(SLOT_RE, '').replace(/^[：:、\s]+/, '') }}
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
        <!--
          流式光标：ChatView 里原先单独渲染一个，集成到本组件后由这里接管。
          只在最后一块后面画，否则中间每个段落都会挂一个光标。
        -->
        <span
          v-if="streaming && i === blocks.length - 1"
          class="mb__caret"
          aria-hidden="true"
        ></span>
      </p>
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
/* 左侧一道短竖线，像文档的小节，比加粗整行更轻盈 */
.mb__h {
  position: relative;
  margin: 4px 0 0;
  padding-left: 11px;
  font-size: 0.95rem;
  font-weight: 700;
  line-height: 1.6;
}
.mb__h::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.42em;
  bottom: 0.42em;
  width: 3px;
  border-radius: 2px;
  background: var(--grad);
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
.mb__p {
  margin: 0;
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
  gap: 3px;
  min-width: 0;
}
.mb__day-body b {
  font-size: 0.87rem;
  font-weight: 650;
}
.mb__slot {
  font-size: 0.85rem;
  color: var(--text2);
  line-height: 1.65;
}
.mb__slot em {
  font-style: normal;
  font-weight: 600;
  color: var(--blue-700);
  margin-right: 5px;
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
