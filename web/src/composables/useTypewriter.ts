/**
 * Hero 区的打字机动效。
 *
 * 三个用途，共用一套节流与降级逻辑：
 *   1. 主标题逐字出现
 *   2. 副标题逐字出现（在主标题之后开始）
 *   3. 输入框占位文案：像有人在打字一样轮换不同的示例需求
 *
 * ## 关键取舍
 *
 * **布局稳定性**：逐字显示会让元素高度/宽度不断变化，进而把下方内容一路推挤。
 * 这里的做法是让模板始终渲染**完整文本**，只把超出已输入长度的部分设为
 * `visibility: hidden` —— 它仍然占据宽度与高度，因此从第一帧起布局就是最终的。
 * 若改用「只渲染已输入的前缀」，整页会在两秒内持续向下抖动，非常廉价。
 *
 * **降级**：`prefers-reduced-motion: reduce` 时**直接显示全文**，不逐字播放。
 * 动效是锦上添花，不能成为阅读内容的门槛。
 *
 * **为什么用 setTimeout 而不是 requestAnimationFrame**：
 * rAF 在两种情况下会**卡住不动**：
 *   · 无头/离屏渲染环境（rAF 不推进）
 *   · 页面切到后台标签页（浏览器冻结 rAF）
 * 后者对真实用户一样可见 —— 切走再回来，文字停在半句上，比不动效更糟。
 * setTimeout 在后台会被节流到约 1 次/秒，但仍在推进，回到前台即恢复正常速度。
 * 打字机对帧率精度没有要求，定时器足够，且行为更可预期。
 *
 * **不要用 CSS animation-delay 逐字**：需要为每个字符生成延迟规则，
 * 且与「循环 / 变长文本」不兼容。
 */
import { onUnmounted, ref, type Ref } from 'vue'

/** 是否应跳过动效（用户偏好减弱动效 / 无 window 环境） */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return true
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

export interface TypewriterOptions {
  /** 每个字符的间隔（毫秒） */
  charMs?: number
  /** 开始前的等待（毫秒），用于让多个打字机错开 */
  startDelayMs?: number
}

/**
 * 逐字显示一段**静态文本**（标题、副标题用）。
 *
 * 返回已输入的字符数 `count`，模板据此把文本切成「可见 + 隐藏」两段。
 */
export function useTypewriter(
  fullText: string,
  options: TypewriterOptions = {}
): { count: Ref<number>; done: Ref<boolean> } {
  const { charMs = 55, startDelayMs = 0 } = options
  const count = ref(0)
  const done = ref(false)

  if (prefersReducedMotion()) {
    count.value = fullText.length
    done.value = true
    return { count, done }
  }

  let delayTimer: ReturnType<typeof setTimeout> | null = null
  let stepTimer: ReturnType<typeof setTimeout> | null = null

  const step = () => {
    count.value = Math.min(count.value + 1, fullText.length)
    if (count.value >= fullText.length) {
      done.value = true
      return
    }
    stepTimer = setTimeout(step, charMs)
  }

  delayTimer = setTimeout(step, startDelayMs)

  onUnmounted(() => {
    if (delayTimer !== null) clearTimeout(delayTimer)
    if (stepTimer !== null) clearTimeout(stepTimer)
  })

  return { count, done }
}

/**
 * 输入框占位文案：像有人在打字一样，在若干示例之间轮换。
 *
 * 每一轮的节奏是「逐字打出 → 停留 → 逐字删掉 → 换下一条」。
 * 逐字删除而不是整段消失，是因为「有人在打字」这个错觉靠的就是
 * 打字与删除两个动作都可见；直接切换会很跳。
 *
 * 返回当前应显示的片段 `text`。
 */
export function useRotatingPlaceholder(
  samples: string[],
  options: { charMs?: number; holdMs?: number; eraseMs?: number } = {}
): { text: Ref<string>; caretVisible: Ref<boolean> } {
  const { charMs = 85, holdMs = 1800, eraseMs = 34 } = options

  const text = ref('')
  const caretVisible = ref(true)

  if (prefersReducedMotion() || samples.length === 0) {
    // 降级：直接显示第一条，不做轮换（也不显示光标，避免暗示「正在打字」）
    text.value = samples[0] ?? ''
    caretVisible.value = false
    return { text, caretVisible }
  }

  let timer: ReturnType<typeof setTimeout> | null = null
  let phase: 'typing' | 'holding' | 'erasing' = 'typing'
  let index = 0

  const step = () => {
    const target = samples[index % samples.length]

    if (phase === 'typing') {
      text.value = target.slice(0, text.value.length + 1)
      if (text.value.length >= target.length) {
        phase = 'holding'
        timer = setTimeout(step, holdMs)
        return
      }
      timer = setTimeout(step, charMs)
      return
    }

    if (phase === 'holding') {
      phase = 'erasing'
      timer = setTimeout(step, eraseMs)
      return
    }

    // erasing
    text.value = text.value.slice(0, -1)
    if (text.value.length === 0) {
      index += 1
      phase = 'typing'
    }
    timer = setTimeout(step, eraseMs)
  }

  timer = setTimeout(step, charMs)
  onUnmounted(() => {
    if (timer !== null) clearTimeout(timer)
  })

  return { text, caretVisible }
}
