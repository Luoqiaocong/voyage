/**
 * 首页首屏展开闸门 + 入场滚动揭示。
 *
 * ## 首屏展开闸门
 *
 * 首页初始**只呈现 Hero**：一句话输入框。下方的示例行程、场景、三步流程、
 * 收尾 CTA 默认不渲染，由用户点击引导按钮或向下滚动/上滑后展开。
 *
 * 为什么默认收起：Hero 已经完整表达了「说一句话 → 得到行程」这件事，
 * 首屏直接铺开四屏内容反而稀释了唯一的行动点（输入框）。
 * 收起后首屏只有一个焦点，用户要么输入、要么展开看细节。
 *
 * 触发方式同时支持三种，覆盖桌面与移动端：
 *   · 点击/回车引导按钮（主要入口，键盘可达）
 *   · 桌面：鼠标滚轮向下
 *   · 移动端：触摸上滑
 * 后两者是「用户已经在尝试往下看」的强信号，此时立刻展开，
 * 避免出现「滚不动」的困惑。
 *
 * ## 入场揭示
 *
 * 为所有 .rv 元素注册 IntersectionObserver，滚到视口内时加 .in。
 * 必须在**展开之后重新调用一次**：收起状态下内容容器是 display:none，
 * 被它包裹的元素没有布局盒，观察器永远判定不相交，展开后会一直停在
 * opacity:0（表现为「下面一片空白」）。
 */
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

export function useHomeReveal() {
  const revealed = ref(false)
  /** 用于 aria-controls 指向的容器 id */
  const REVEAL_ID = 'home-more'

  /*
   * 展开后把「引导件」滚到导航栏正下方。
   *
   * ## 目标位置怎么定
   *
   * 不依赖任何元素引用，而是先算出引导件在文档里的绝对纵坐标，再减去
   * 导航栏高度与一点呼吸空间。这样得到的滚动目标在滚动过程中**不会变**，
   * 不会出现「滚到一半目标跑了」的情况。
   *
   * ## 为什么不用 scrollIntoView
   *
   * 试过 `block: 'start'` 与 `'nearest'`，问题在于它对齐的是**容器顶端**，
   * 而容器（可展开区）顶部有一段内边距，紧贴其上的引导件因此被推到
   * 视口顶边之外 —— 这正是「一份可执行的行程被遮挡了，箭头也没完全显现」
   * 的成因。手动算位置能精确控制落点，让它停在导航栏下方。
   *
   * ## 关于滚动动画
   *
   * 不传 `behavior`，由全局 `html { scroll-behavior: smooth }` 决定
   * （用户在系统里开启「减弱动效」时，全局会切换为 auto，浏览器自动
   * 改为瞬时跳转，无需在此判断）。
   */
  function scrollGuideIntoView() {
    if (typeof document === 'undefined') return
    const guide = document.querySelector<HTMLElement>('.join-arrow')
    if (!guide) return

    const nav = document.querySelector<HTMLElement>('.nav')
    const navH = nav?.getBoundingClientRect().height ?? 64
    const BREATH = 24 // 引导件与导航栏之间的呼吸空间

    const docTop = guide.getBoundingClientRect().top + window.scrollY
    const targetY = Math.max(docTop - navH - BREATH, 0)
    window.scrollTo(0, targetY)
  }

  /**
   * 展开后的滚动入口。
   *
   * **必须等布局稳定再滚**：内容刚由 display:none 变为可见时，`.rv` 元素
   * 还停在 opacity:0 并带 20px 位移，各区块高度尚未定型 —— 此时算出的
   * 目标位置是错的（实测那样滚几乎不生效）。
   * 故等两帧（一帧移除 display、一帧完成布局）再加一小段延时，
   * 让入场过渡走过大部分位移后再计算并滚动。
   */
  function scrollToContent() {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.setTimeout(scrollGuideIntoView, 120)
      })
    })
  }

  function reveal(andScroll = false) {
    if (revealed.value) return
    revealed.value = true
    if (andScroll) {
      // 等 v-show 把内容渲染出来再滚，否则目标元素高度还是 0
      void nextTick(() => scrollToContent())
    }
  }

  function collapse() {
    revealed.value = false
    /*
     * 回顶部。同样不传 behavior —— 由全局 scroll-behavior 决定。
     * 收起后页面总高骤降、浏览器会自行纠正滚动位置，回顶部最可预期：
     * 收起后的首屏就是 Hero，本来就该在顶部。
     */
    window.scrollTo(0, 0)
  }

  function toggleReveal() {
    if (revealed.value) collapse()
    else reveal(true)
  }

  /* ---------------- 滚动 / 触摸意图 ---------------- */
  let wheelAcc = 0
  let touchStartY: number | null = null

  function onWheelIntent(e: WheelEvent) {
    if (revealed.value) return
    // 只认「向下滚」。阈值避免触控板轻微误触就展开
    if (e.deltaY <= 0) {
      wheelAcc = 0
      return
    }
    wheelAcc += e.deltaY
    if (wheelAcc >= 24) {
      // 收起状态下没有可滚动内容，阻止默认行为避免用户以为页面卡住
      e.preventDefault()
      reveal(true)
    }
  }

  function onTouchStartIntent(e: TouchEvent) {
    if (revealed.value) return
    touchStartY = e.touches[0]?.clientY ?? null
  }

  function onTouchMoveIntent(e: TouchEvent) {
    if (revealed.value || touchStartY === null) return
    const y = e.touches[0]?.clientY
    if (y === undefined) return
    // 手指上滑（y 变小）表示想看下面的内容
    if (touchStartY - y >= 28) {
      e.preventDefault()
      touchStartY = null
      reveal(true)
    }
  }

  let io: IntersectionObserver | null = null

  /*
   * 入场揭示：为所有 .rv 元素注册 IntersectionObserver。
   *
   * ⚠️ 必须在**展开之后重新调用一次**，不能在 onMounted 里只做一次：
   * 收起状态下内容容器是 display:none，被它包裹的元素**没有布局盒**，
   * IntersectionObserver 永远不会判定它们相交，`.in` 类加不上，
   * 展开后它们会一直停在 opacity:0 —— 表现为「下面一片空白」。
   *
   * 幂等：已加过 .in 的元素再次 observe 也无副作用（回调里会 unobserve）。
   */
  let rvBound = false

  function bindRevealObserver() {
    // 滚动揭示只在展开后才需要：收起时下方内容不可见，注册了也不会触发
    if (!revealed.value) return
    if (rvBound) return
    rvBound = true

    if (typeof IntersectionObserver === 'undefined') {
      // 环境不支持时直接显示，绝不因为动画而让内容不可见
      document.querySelectorAll('.rv').forEach((el) => el.classList.add('in'))
      return
    }
    io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('in')
            io?.unobserve(e.target)
          }
        }
      },
      { threshold: 0.12 }
    )
    document.querySelectorAll('.rv').forEach((el) => io?.observe(el))
  }

  onMounted(() => {
    // 展开闸门的触发器。passive:false 是必须的：收起状态下本来就没有可滚动
    // 内容，会在处理函数里 preventDefault 以免用户以为页面卡住。
    window.addEventListener('wheel', onWheelIntent, { passive: false })
    window.addEventListener('touchstart', onTouchStartIntent, { passive: true })
    window.addEventListener('touchmove', onTouchMoveIntent, { passive: false })
  })

  /*
   * 展开后注册揭示观察器。
   *
   * 用 watch 而不是写在点击处理函数里：滚轮/触摸也能触发展开，
   * 若只在点击里做，另外两条路径展开后内容同样会隐形。
   * 统一在这里处理，三条路径行为一致。
   */
  watch(revealed, async (open) => {
    if (!open) return
    // 等两帧：一帧让 v-show 移除 display:none，再一帧让浏览器完成布局，
    // 这样 IntersectionObserver 才能基于真实位置判定
    await nextTick()
    requestAnimationFrame(() => {
      bindRevealObserver()
    })
  })

  onUnmounted(() => {
    io?.disconnect()
    io = null
    window.removeEventListener('wheel', onWheelIntent)
    window.removeEventListener('touchstart', onTouchStartIntent)
    window.removeEventListener('touchmove', onTouchMoveIntent)
  })

  return {
    revealed,
    REVEAL_ID,
    reveal,
    collapse,
    toggleReveal,
    onWheelIntent,
    onTouchStartIntent,
    onTouchMoveIntent
  }
}
