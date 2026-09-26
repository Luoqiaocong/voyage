<script setup lang="ts">
import MessageBody from '@/components/MessageBody.vue'
import ToolTimeline from '@/components/ToolTimeline.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import type { RdMsg } from '@/types/message'
import { PAGE_COPY } from '@/constants/copy'

defineProps<{
  messages: RdMsg[]
  streaming: boolean
  streamError: string
  thinking: boolean
  streamPhase: string
  isDraft: boolean
  historyTruncated: boolean
  historyRounds: number
}>()

const emit = defineEmits<{
  (e: 'copy', msg: RdMsg): void
  (e: 'regenerate', index: number): void
  (e: 'extract'): void
}>()
</script>

<template>
  <div class="chat-stream">
    <!--
      草稿态的问候。
      点「新会话」后消息区是空的，只有一个输入框会显得冷清、
      也让人不确定「这里是不是坏了、能不能说话」。
      一句问候把这件事说清楚，语气与欢迎屏一致（不说教、不堆字）。

      位置刻意放在**消息区**而不是输入框里：
      与欢迎屏同处一栏，视觉上前后连贯；输入区保持轻，
      不被一行文字压得拥挤。
    -->
    <div v-if="isDraft" class="draft-hello">
      <h2 class="draft-hello__title">{{ PAGE_COPY.chatDraftGreeting }}</h2>
      <p class="draft-hello__hint">{{ PAGE_COPY.chatDraftHint }}</p>
    </div>

    <!-- 历史被截断时的提示：后端按轮次分页，更早的内容不在此次响应里 -->
    <p v-if="historyTruncated" class="chat-truncated">
      仅显示最近 {{ historyRounds }} 轮对话
    </p>
    <div
      v-for="(msg, i) in messages"
      :key="i"
      class="msg"
      :class="`msg--${msg.role}`"
    >
      <!-- 助手头像：voyage-icon-2.png（128x128，带透明底）。
           30px 显示、3 倍屏需 90px，128 足够；
           用透明版是因为头像落在消息区背景上，
           透明底在浅色与深色主题下都能自然贴合。 -->
      <span v-if="msg.role === 'assistant'" class="msg__avatar" aria-hidden="true">
        <img src="/voyage-icon-2.png" alt="" />
      </span>

      <div class="msg__col">
        <!-- 思考过程：默认折叠，不抢视线 -->
        <details v-if="msg.reasoning" class="reason">
          <summary>
            <span class="reason__dot"></span>
            思考过程
            <span class="reason__len">{{ msg.reasoning.length }} 字</span>
          </summary>
          <p>{{ msg.reasoning }}</p>
        </details>

        <!-- 工具调用：鲜明的时间线 -->
        <ToolTimeline v-if="msg.tools && msg.tools.length" :steps="msg.tools" />

        <!--
          正文：助手走结构化渲染，用户走纯文本。
          助手不再用气泡装 markdown —— 那会让用户看到满屏 ** 与 -，
          像在读源码。MessageBody 把它解析成小节标题、条目列表、
          行程片段与提示块，读起来像顾问给的方案。
        -->
        <MessageBody
          v-if="msg.content && msg.role === 'assistant'"
          class="msg__card"
          :class="{ 'msg__card--err': !!streamError && i === messages.length - 1 && streaming }"
          :text="msg.content"
          :streaming="streaming && i === messages.length - 1"
          @extract="emit('extract')"
        />
        <div v-else-if="msg.content" class="msg__bubble">{{ msg.content }}</div>

        <!--
          流式光标已由 MessageBody 内部处理（末块不结构化），
          这里不再单独渲染，避免出现两个光标。
        -->

        <!-- 消息操作条：悬停浮现，避免常驻占用视线 -->
        <div v-if="msg.content && !streaming" class="msg__ops">
          <button class="op-btn" title="复制内容" @click="emit('copy', msg)">
            <TravelIcon name="check" :size="13" />
            复制
          </button>
          <button
            v-if="msg.role === 'assistant'"
            class="op-btn"
            title="用同一个问题再问一次"
            @click="emit('regenerate', i)"
          >
            <TravelIcon name="compass" :size="13" />
            重新生成
          </button>
        </div>
      </div>
    </div>

    <!-- 首字等待：三点 + 当前阶段
         只说「正在生成」等于没说；告诉用户此刻在做什么
         （解析需求 / 核对天气 / 查车次），等待才不焦躁 -->
    <div v-if="thinking" class="msg msg--assistant">
      <span class="msg__avatar" aria-hidden="true">
        <img src="/voyage-icon-2.png" alt="" />
      </span>
      <div class="msg__col">
        <div class="waiting" role="status" aria-live="polite">
          <span class="waiting__dots" aria-hidden="true">
            <i></i><i></i><i></i>
          </span>
          <span class="waiting__text">{{ streamPhase }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/*
 * min-height: 100% 是草稿态问候能垂直居中所需：
 * .draft-hello 用上下 auto 外边距居中，前提是父容器有富余高度。
 * 没有这一条时它只按内容高度撑开，问候会贴在顶部。
 */
.chat-stream { max-width: 820px; margin-inline: auto; min-height: 100%; display: flex; flex-direction: column; gap: 22px; }

/* ============================================================
   草稿态的问候
   ------------------------------------------------------------
   点「新会话」后消息区是空的，只给一个输入框会显得冷清，
   用户也不确定「这里能不能说话」。一句问候把这件事讲清楚。

   与欢迎屏（.chat-empty）的分工：欢迎屏是介绍页（logo + 引导卡），
   这里是「我已经在了，你说」—— 所以只用两行字，不加图形与卡片。
   ============================================================ */
.draft-hello {
  /*
   * 垂直居中：草稿态下它是消息区里唯一的元素，贴顶会像一条被遗忘的提示。
   * 靠上下 auto 外边距居中，一旦有消息进来（v-if 变假）它就消失，
   * 不影响正常排版。
   */
  margin: auto 0;
  text-align: center;
  padding: 40px 16px;
}
.draft-hello__title {
  margin: 0 0 8px;
  font-family: var(--font-display);
  font-size: 1.32rem;
  font-weight: 700;
  color: var(--text);
}
.draft-hello__hint {
  margin: 0;
  font-size: 0.86rem;
  line-height: 1.7;
  color: var(--text3);
}

/* 历史截断提示：居中细字，不抢消息的视觉重心 */
.chat-truncated {
  text-align: center;
  font-size: 0.76rem;
  color: var(--text3);
  padding: 2px 0 6px;
  position: relative;
}
.chat-truncated::before,
.chat-truncated::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 42px;
  height: 1px;
  background: var(--hairline);
}
.chat-truncated::before { left: calc(50% - 110px); }
.chat-truncated::after { right: calc(50% - 110px); }

.msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  /* 消息进入时轻微上移淡入。新消息硬出现会让人猝不及防，
     尤其实时对话里用户的注意力正在输入框上 */
  animation: msgIn 0.32s cubic-bezier(0.2, 0.7, 0.2, 1) both;
}

/*
 * 历史消息的虚拟化：让浏览器跳过**屏幕外**消息的渲染。
 *
 * 为什么不用固定高度的虚拟滚动：聊天消息高度完全不定（一段话可能两三行，
 * 也可能是一张表格 + 十几条行程条目），固定高度会算错位置导致滚动跳动；
 * 动态测量又要引入依赖与一套高度缓存。content-visibility 把「哪些元素需要
 * 渲染」交给浏览器，它自己知道视口在哪，比在 JS 里重算更准也更省。
 *
 * 为什么排除 :last-child：末条是**正在流式输出**的消息，它的高度每来一个字
 * 都在变。若也按估算值占位，估算与实测会交替生效，滚动位置就会抖。
 * 一条消息不参与虚拟化对性能没有影响。
 *
 * contain-intrinsic-size 用 `auto 200px` 而非单纯 `200px`：
 *   · 不写这一项，未渲染元素高度会被当成 0，滚动条长度随滚动不断跳变
 *     ——这是启用 content-visibility 最常见的副作用
 *   · `auto` 让浏览器**记住元素上次渲染的真实高度**，此后按真实值占位；
 *     只写 200px 则每次都重新估算，长消息多的会话往回滚会位置跳动
 *   · 200px 仅作为「尚未渲染过」时的初始估算
 *
 * 浏览器不支持时（如较老的 Safari）该规则被忽略，退化为全部渲染，
 * 也就是当前行为 —— 没有兼容性风险。
 */
.msg:not(:last-child) {
  content-visibility: auto;
  contain-intrinsic-size: auto 200px;
}
@keyframes msgIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .msg { animation: none; }
}
.msg--user { flex-direction: row-reverse; }
.msg--assistant { flex-direction: row; }

.msg__avatar {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  /* 同 chat-empty__logo：图标自带完整方形底，故容器不再叠渐变 */
  background: var(--panel);
  border: 1px solid var(--border);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  margin-top: 2px;
  overflow: hidden;
}
.msg__avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }

.msg__col { display: flex; flex-direction: column; gap: 8px; min-width: 0; max-width: min(680px, 88%); }
.msg--user .msg__col { align-items: flex-end; max-width: min(600px, 84%); }

/* ---- 气泡（仅用户消息）----
   助手消息不再用气泡包裹：结构化内容自己就是排版，
   再套一层圆角底色只会让小节标题、列表、提示块挤在一个框里，
   既不像文档也不像对话。改成无底色直接铺开，
   靠 MessageBody 内部的标题竖线与列表缩进建立层次。 */
.msg__bubble {
  padding: 12px 16px;
  border-radius: 14px;
  font-size: 0.92rem;
  line-height: 1.7;
  overflow-wrap: break-word;
  position: relative;
}

.msg--user .msg__bubble {
  background: var(--grad);
  color: #fff;
  border-radius: 16px 16px 5px 16px;
  box-shadow: 0 6px 18px var(--glow);
}

/* ---- 助手消息卡片 ----
   原先这里有一条左侧竖边（悬停时浮出蓝色），实测很干扰：
   鼠标划过内容就冒出一道蓝线，像是选中状态，且与文内的小节标题
   竖线叠在一起更显杂乱。现改为完全无装饰，让内容自己成立。 */
.msg__card {
  padding: 2px 0;
}

/* 出错时整块转为错误色——这个保留：它表达的是真实状态而非装饰 */
.msg__card--err {
  background: rgba(229, 72, 77, 0.06);
  border-radius: 10px;
  padding: 10px 13px;
  color: var(--danger);
}

/* ---- 消息操作条 ----
   默认隐藏、悬停浮现，并轻微下移淡入——常驻会持续占用视线，
   而这类操作的使用频率远低于阅读正文。 */
.msg__ops {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
  opacity: 0;
  transform: translateY(-4px);
  transition: opacity 0.22s, transform 0.22s;
}
.msg:hover .msg__ops,
.msg:focus-within .msg__ops {
  opacity: 1;
  transform: none;
}
@media (hover: none) {
  /* 触屏没有悬停，操作条直接常驻，否则永远点不到 */
  .msg__ops { opacity: 1; transform: none; }
}

.op-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text3);
  font-size: 0.75rem;
  transition: background-color 0.18s, color 0.18s, border-color 0.18s;
}
.op-btn:hover {
  background: var(--panel2);
  border-color: var(--border);
  color: var(--text);
}
.op-btn--accent:hover {
  background: var(--primary-soft);
  border-color: var(--blue-200);
  color: var(--prim);
}

/* ---- 思考过程 ---- */
.reason {
  border-left: 3px solid rgba(245, 158, 11, 0.7);
  background: rgba(245, 158, 11, 0.06);
  border-radius: 5px 12px 12px 5px;
  padding: 9px 13px;
  font-size: 0.82rem;
  color: var(--text2);
  max-width: min(640px, 100%);
}
.reason summary {
  cursor: pointer;
  font-weight: 650;
  display: flex;
  align-items: center;
  gap: 7px;
  list-style: none;
}
.reason summary::-webkit-details-marker { display: none; }
.reason__dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); flex-shrink: 0; }
.reason__len { margin-left: auto; font-size: 0.7rem; color: var(--text3); font-weight: 400; }
.reason p { margin-top: 8px; white-space: pre-wrap; line-height: 1.7; }

/*
 * Markdown 相关样式已随 v-html 渲染一并移除。
 * 助手消息改由 MessageBody 组件渲染，其样式封装在该组件内（scoped），
 * 这里再留一份 .md-body 规则只会成为永远不会命中的死代码。
 */

/* ---- 等待状态：三点 + 当前阶段 ---- */
.waiting {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  padding: 13px 17px;
  background: var(--bubble-ai);
  border: 1px solid var(--border);
  border-radius: 5px 16px 16px 16px;
  width: fit-content;
}
.waiting__dots {
  display: inline-flex;
  gap: 5px;
  flex-shrink: 0;
}
.waiting__dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--prim);
  animation: bounce 1.2s ease-in-out infinite;
}
.waiting__dots i:nth-child(2) { animation-delay: 0.15s; }
.waiting__dots i:nth-child(3) { animation-delay: 0.3s; }
/* 阶段文字用主题色并与点同步呼吸，整体像「正在处理」而非静止 */
.waiting__text {
  font-size: 0.85rem;
  color: var(--prim);
  font-weight: 550;
  animation: waitFade 1.6s ease-in-out infinite;
}
@keyframes waitFade {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.62; }
}
@media (prefers-reduced-motion: reduce) {
  .waiting__dots i,
  .waiting__text { animation: none; }
}
/* bounce 关键帧由 .waiting__dots 使用；旧的 .typing span 规则已随
   等待组件改造移除（改为 .waiting__dots i） */
@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40% { transform: translateY(-7px); opacity: 1; }
}

@media (max-width: 860px) {
  .msg__col { max-width: 92%; }
  .msg--user .msg__col { max-width: 88%; }
}
</style>
