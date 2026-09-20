<script setup lang="ts">
/**
 * 返回顶部按钮（右下角蓝色圆形 + 白色上箭头）。
 *
 * ## 设计取舍
 *
 * · **只在滚动一段距离后出现**（默认 400px）。一进页面就顶着按钮没有意义，
 *   而且会与首屏内容抢注意力。400px 约等于「已经看过一屏」，
 *   这时用户想要回到顶部的可能性才真实存在。
 * · 放在**右下角**：主流习惯位置，且左手拇指在移动端也不容易误触。
 * · 用 `position: fixed` 而非 sticky：不参与文档流，不会挤动任何内容。
 * · 进入/退出都有过渡，避免在阈值附近抖动时反复闪现（用 v-show 保持占位
 *   反而会留一个透明热区，所以用 v-if + Transition）。
 *
 * ## 无障碍
 *
 * · 真实 `<button>`，键盘可达；带 aria-label
 * · 尊重 prefers-reduced-motion：直接跳到顶部，不做平滑滚动
 */
import { onMounted, onUnmounted, ref } from 'vue'
import TravelIcon from '@/components/TravelIcon.vue'

interface Props {
  /** 滚动超过多少像素后出现 */
  threshold?: number
}

const props = withDefaults(defineProps<Props>(), { threshold: 400 })

const visible = ref(false)

function onScroll() {
  visible.value = window.scrollY > props.threshold
}

function toTop() {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
}

onMounted(() => {
  // passive：滚动监听绝不阻塞滚动
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll() // 处理「刷新后停在中间位置」的情况
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <Transition name="totop">
    <button
      v-if="visible"
      type="button"
      class="totop"
      aria-label="返回顶部"
      title="返回顶部"
      @click="toTop"
    >
      <TravelIcon name="arrow-up" :size="20" />
    </button>
  </Transition>
</template>

<style scoped>
.totop {
  position: fixed;
  /* 右下角。用 --nav-h 无关，给它固定的安全边距 */
  right: 28px;
  bottom: 32px;
  z-index: 50; /* 低于导航栏(60)，高于内容 */

  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;

  border: none;
  border-radius: 50%;
  /* 主题蓝：与「开始规划」等主按钮同色，一眼认得出是可点的动作 */
  background: var(--prim);
  color: #fff; /* 白色箭头 */
  box-shadow: 0 6px 20px var(--glow);
  cursor: pointer;
  transition: transform 0.2s cubic-bezier(0.2, 0.7, 0.2, 1),
    box-shadow 0.2s, filter 0.2s;
}

.totop:hover {
  transform: translateY(-2px);
  filter: saturate(1.08);
  box-shadow: 0 10px 26px var(--glow);
}
.totop:active {
  transform: translateY(0);
}
.totop:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 3px;
}

/* 进入 / 退出：淡入 + 轻微上移，避免突兀闪现 */
.totop-enter-active,
.totop-leave-active {
  transition: opacity 0.22s ease, transform 0.22s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.totop-enter-from,
.totop-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.92);
}

/* 窄屏收小一点，避免遮挡内容（尤其行程页的长列表） */
@media (max-width: 860px) {
  .totop {
    right: 16px;
    bottom: 20px;
    width: 42px;
    height: 42px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .totop,
  .totop-enter-active,
  .totop-leave-active {
    transition: none;
  }
  .totop:hover {
    transform: none;
  }
}
</style>
