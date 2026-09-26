import { nextTick, ref, type Ref } from 'vue'

/**
 * 对话流的「自动跟随」行为。
 *
 * 从 ChatView 抽出：这段逻辑自成一体（只依赖滚动容器本身），
 * 且夹杂了大段「为什么这么写」的说明，继续留在 3700 行的视图里
 * 会淹没在其它状态中。视图只需把容器的 ref 传进来，再拿去绑定事件。
 *
 * @param scrollEl 消息区滚动容器的 ref
 */
export function useChatAutoScroll(scrollEl: Ref<HTMLElement | null>) {
  /**
   * 用户是否**主动**滚离了底部。
   *
   * 它同时决定两件事：「要不要自动跟随流式输出」与「是否显示回到底部按钮」。
   *
   * ## 为什么必须是「用户意图」而不是「容器位置」
   *
   * 原实现是在容器的 scroll 事件里按间距判断（gap > 80px 即视为离开底部），
   * 看起来合理，但**在流式输出下必然失效**：
   *
   *   AI 每吐一段字，内容就变长 → 容器位置被动改变 → 触发 scroll 事件
   *   → 重新计算 gap → 一旦落回 80px 内就把本标志置回 false
   *   → 自动跟随恢复 → 用户刚拉上去又被拽回底部
   *
   * 也就是说，用户想往上读时，只要 AI 还在输出，就永远「甩不掉」底部。
   *
   * 现在改为：**只有用户的滚动动作才能把它置为 true**（滚轮向上、触摸下拉、
   * 键盘上翻）。程序性的内容增长不再影响它。
   * 复位只发生在两个明确的时刻：用户点「回到底部」、或用户发送新消息。
   */
  const awayFromBottom = ref(false)

  /** 距底部多少像素内仍视为「在底部」（仅用于判断按钮显隐，不再用于自动复位） */
  const NEAR_BOTTOM_PX = 80

  /**
   * 容器滚动时只维护一个事实：**用户如果已经滚回最底，就恢复自动跟随**。
   *
   * 注意方向是单向的 —— 这里只可能把 true 变 false，绝不由位置把 false 变 true。
   * 置 true 只由下面的用户意图处理函数负责。
   */
  function onStreamScroll() {
    const el = scrollEl.value
    if (!el) return
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight
    // 已到底（容差内）→ 视为用户回到了跟随状态
    if (awayFromBottom.value && gap <= NEAR_BOTTOM_PX) {
      awayFromBottom.value = false
    }
  }

  /** 用户往上滚 → 停止自动跟随 */
  function markUserScrolledUp() {
    awayFromBottom.value = true
  }

  /** 滚轮：只认向上的滚动（往下滚交给 onStreamScroll 的到底复位） */
  function onWheelIntent(e: WheelEvent) {
    if (e.deltaY < 0) markUserScrolledUp()
  }

  let touchStartY: number | null = null
  function onTouchStartIntent(e: TouchEvent) {
    touchStartY = e.touches[0]?.clientY ?? null
  }
  /** 触摸：手指下拉（y 变大）表示在看上面的内容 */
  function onTouchMoveIntent(e: TouchEvent) {
    if (touchStartY === null) return
    const y = e.touches[0]?.clientY
    if (y === undefined) return
    if (y - touchStartY > 12) markUserScrolledUp()
  }

  /** 键盘：PageUp / 方向键上 / Home 都是「往上读」的明确意图 */
  function onKeyIntent(e: KeyboardEvent) {
    if (['PageUp', 'ArrowUp', 'Home'].includes(e.key)) markUserScrolledUp()
  }

  /**
   * 滚动到底部。
   *
   * @param smooth 是否平滑滚动
   * @param force  是否无视「用户已滚上去」强制拉到底
   *
   * 默认**只在用户本来就在底部时才自动跟随**。
   * 原先是无条件跟随：用户往回翻看历史时，新生成的内容会不断把他拽回底部，
   * 根本读不了上面的内容 —— 这是流式输出场景的经典体验问题。
   * 用户主动触发的操作（发送、点箭头、切换会话）则用 force 强制到底。
   */
  function scrollToBottom(smooth = false, force = false) {
    nextTick(() => {
      const el = scrollEl.value
      if (!el) return
      if (!force && awayFromBottom.value) return
      el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
      awayFromBottom.value = false

      /*
       * 瞬时滚动后再校正一次。
       *
       * 原因：调用这一刻的 scrollHeight 可能还不是最终值——
       *   · 发送时输入框清空，自适应高度会把它从多行收回单行，
       *     消息区随之变高（否则会停在离底部约「收缩量」的位置）；
       *   · content-visibility 让未进入过视口的历史消息按估算高度占位，
       *     真正渲染后高度会变大，底部随之外移。
       * 这些布局变化都发生在本次布局之后，等一帧再按新的 scrollHeight 落一次，
       * 才能停在真正的底部。期间若用户主动上翻（away=false→true）则放弃校正。
       */
      if (!smooth) {
        requestAnimationFrame(() => {
          const e2 = scrollEl.value
          if (e2 && !awayFromBottom.value) {
            e2.scrollTo({ top: e2.scrollHeight, behavior: 'auto' })
          }
        })
      }
    })
  }

  /** 点箭头：回到底部并恢复自动跟随 */
  function jumpToBottom() {
    scrollToBottom(true, true)
  }

  return {
    awayFromBottom,
    onStreamScroll,
    onWheelIntent,
    onTouchStartIntent,
    onTouchMoveIntent,
    onKeyIntent,
    scrollToBottom,
    jumpToBottom
  }
}
