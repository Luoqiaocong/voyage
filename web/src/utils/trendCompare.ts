/**
 * 趋势图的涨跌幅度计算（纯函数，无 Vue 依赖，便于单测）。
 *
 * ## 口径必须写清楚
 *
 * 用 **(后 − 前) / 前 × 100%**，即标准增幅：
 *   前 100 → 后 200  显示 ⬆ 100%
 *   前 100 → 后 300  显示 ⬆ 200%
 * 若改用「后 / 前」口径，同样的数据会显示 200% / 300% —— 恰好差 100 个百分点。
 * 两种口径都有人用，所以实现与文档都必须明确，否则同一组数据会有两种读法。
 *
 * ## 为什么是「窗口内前后半段」而不是与上一周期比
 *
 * trend 接口只返回当前窗口，前端拿不到更早的数据。这不是严格的环比，
 * 只能给出方向性判断 —— 因此界面上保留一行基准说明，
 * 避免读者误读成「比上一周期增长」。
 */

export interface Compare {
  /** 显示文案，如 `⬆ 100%` / `⬇ 50%` / `— 持平` */
  text: string
  tone: 'up' | 'down' | 'flat'
}

/**
 * 计算后半段相对前半段的变化幅度。
 *
 * @param values 按时间升序的日值序列
 * @returns 无法比较时返回 null（调用方不渲染标记）
 */
export function halfCompare(values: number[]): Compare | null {
  // 少于 4 个点时分不出有意义的前后两段（每段至少 2 个点）
  if (values.length < 4) return null

  const mid = Math.floor(values.length / 2)
  const first = values.slice(0, mid).reduce((a, b) => a + b, 0)
  const last = values.slice(mid).reduce((a, b) => a + b, 0)

  // 两段都是 0：没有可比信息。显示 ⬆ 0% 会让人以为「有增长」
  if (first === 0 && last === 0) return null

  // 前半段为 0 而后半段有值：增幅在数学上是无穷大。
  // 显示 ⬆ ∞% 既吓人也没信息量，改用「新增」表达同一件事
  if (first === 0) return { text: `⬆ 新增 ${last}`, tone: 'up' }

  const pct = ((last - first) / first) * 100

  // 不足 1% 视为持平：日粒度数据本就有波动，标 ⬆0% 只是噪音
  if (Math.abs(pct) < 1) return { text: '— 持平', tone: 'flat' }

  return {
    text: `${pct > 0 ? '⬆' : '⬇'} ${Math.abs(pct).toFixed(0)}%`,
    tone: pct > 0 ? 'up' : 'down'
  }
}
