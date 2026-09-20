/**
 * 趋势图的「相对昨日」涨跌标注。
 *
 * ## 口径
 *
 * 取趋势序列的**最后两天**比较：后一天相对前一天
 *   · 涨跌数目 = 后 − 前
 *   · 涨跌百分比 = (后 − 前) / 前 × 100%
 *
 * 用 (后−前)/前 而非「后/前」：前者是标准增幅（前 100 → 后 200 显示 +100%），
 * 后者会显示 200%，两者恰好差 100 个百分点。实现与文案都按增幅口径。
 *
 * ## 为什么是最后两天，而不是窗口内前后半段
 *
 * 比较前后半段之和时「昨日」这个词用不了 —— 后半段是好几天的合计，
 * 标成「较昨日」是错的。而用户要的正是**相对昨日**的百分比，
 * 故直接取最后两天。数据本身就是逐日的，无需新增接口。
 *
 * ## 边界
 *
 * · 不足 2 天 → 无法比较，返回 null（不显示）
 * · 昨天为 0、今天有值 → 增幅在数学上是无穷大，改为只显示数目（无百分比）
 * · 两天都为 0 → 返回 null（显示「+0」会被误读为有增长）
 * · 变化为 0 → 显示「持平」
 * · 出现负值 → 返回 null（见下方守卫，负数会让百分比方向翻转）
 */

export interface DayOverDay {
  /** 涨跌方向：up 增长 / down 下降 / flat 持平 */
  tone: 'up' | 'down' | 'flat'
  /** 涨跌的绝对数目（恒为非负，方向由 tone 表示） */
  delta: number
  /** 百分比；无法计算（昨天为 0）时为 null */
  pct: number | null
  /** 前一天的原始值，用于展示对比基数 */
  prev: number
  /** 后一天（即最新一天）的原始值 */
  curr: number
}

export function dayOverDay(values: number[]): DayOverDay | null {
  if (values.length < 2) return null

  const prev = values[values.length - 2]
  const curr = values[values.length - 1]

  /*
   * 负值一律不比较。
   *
   * 这个指标（token 数、用户数）不可能为负，但一旦真出现负值，
   * 除法会**翻转符号**：[-1, -2] 明明是下降，pct 算出来却是 +100%，
   * 于是标注显示「⬇ 1  +100%」——方向自相矛盾，比不显示更糟。
   * 宁可返回 null（界面不显示标注），也不给出会误导人的数字。
   */
  if (prev < 0 || curr < 0) return null

  const delta = curr - prev

  // 两天都是 0：没有可比信息。显示「+0」会让人以为「有增长」
  if (prev === 0 && curr === 0) return null

  // 昨天为 0、今天有值：增幅是无穷大，百分比无意义。
  // 只给数目，界面据此隐藏百分比部分。
  if (prev === 0) {
    return { tone: 'up', delta: curr, pct: null, prev, curr }
  }

  const pct = (delta / prev) * 100
  const tone: DayOverDay['tone'] = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'
  return { tone, delta: Math.abs(delta), pct, prev, curr }
}

/**
 * 把比较结果格式化成**两个各自带箭头的量**。
 *
 * 展示形态（用户指定）：
 *
 *     Token 消耗   ⬆ 1.0M   ⬆ 100%
 *                  └ 数目   └ 增减幅
 *
 * 两个箭头各自指示自己的方向，不是「一个箭头管两个数」——
 * 截图里的写法就是两个 ⬆ 并列，故这里返回两个完整字段，
 * 由界面各自渲染成独立的标签片。
 *
 * 方向一致（涨则都涨、跌则都跌），所以两个箭头符号相同；
 * 但仍然分别生成，因为数目为 0 或无法算百分比时只渲染其中一个。
 */
export interface DayOverDayDisplay {
  /** 具体数目，含箭头，如「⬆ 1.0M」；持平或无法计算时为空串 */
  amount: string
  /** 增减幅度，含箭头，如「⬆ 100%」；无法计算时为空串 */
  percent: string
  tone: DayOverDay['tone']
}

export function formatDayOverDay(
  c: DayOverDay,
  fmt: (n: number) => string
): DayOverDayDisplay {
  if (c.tone === 'flat') {
    return { amount: '持平', percent: '', tone: c.tone }
  }

  const arrow = c.tone === 'up' ? '⬆' : '⬇'
  const amount = `${arrow} ${fmt(c.delta)}`

  // 昨日为 0：增幅是无穷大，百分比无意义 —— 只显示数目那一片
  if (c.pct === null) {
    return { amount, percent: '', tone: c.tone }
  }

  return {
    amount,
    percent: `${arrow} ${Math.abs(c.pct).toFixed(0)}%`,
    tone: c.tone
  }
}
