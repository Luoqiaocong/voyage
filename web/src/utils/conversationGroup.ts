/**
 * 会话按时间分组：今天 / 昨天 / 7 天内 / 30 天内 / 更早。
 *
 * ## 为什么按「自然日」而不是「距今多少小时」
 *
 * 用户说「昨天」时指的是**日历上的昨天**，不是「24~48 小时前」。
 * 一个今天凌晨 1 点建的会话，在今天下午看应该是「今天」；
 * 若按小时差算，它可能被算成「7 天内」—— 与直觉不符。
 * 所以先各自归到本地自然日，再按日差分组。
 *
 * ## 边界口径
 *
 * 以本地日历日为单位，用日差（今天=0）判定：
 *   diff = 0        → 今天
 *   diff = 1        → 昨天
 *   2 <= diff <= 6  → 7 天内   （不含今天与昨天，避免重复归类）
 *   7 <= diff <= 29 → 30 天内
 *   diff >= 30      → 更早
 * 未来时间（diff < 0）也归入「今天」—— 客户端时钟偏差或服务端时区差
 * 都可能造出一点点未来时间，单独开一组没有意义。
 */

export type ConversationBucket =
  | 'today'
  | 'yesterday'
  | 'week'
  | 'month'
  | 'earlier'

export interface BucketMeta {
  key: ConversationBucket
  label: string
}

/** 分组顺序即展示顺序 */
export const BUCKETS: BucketMeta[] = [
  { key: 'today', label: '今天' },
  { key: 'yesterday', label: '昨天' },
  { key: 'week', label: '7 天内' },
  { key: 'month', label: '30 天内' },
  { key: 'earlier', label: '更早' }
]

/** 取本地自然日的零点，用于按日比较 */
function startOfLocalDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** 计算本地日历日差：今天=0、昨天=1… */
export function dayDiff(date: Date, now: Date = new Date()): number {
  const a = startOfLocalDay(date)
  const b = startOfLocalDay(now)
  return Math.round((b - a) / 86400000)
}

/** 单个时间戳属于哪一组 */
export function bucketOf(iso: string, now: Date = new Date()): ConversationBucket {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'earlier' // 解析不了就沉到最后一组，不丢项
  const diff = dayDiff(d, now)
  if (diff <= 0) return 'today' // 含未来时间，见文件头说明
  if (diff === 1) return 'yesterday'
  if (diff <= 6) return 'week'
  if (diff <= 29) return 'month'
  return 'earlier'
}

export interface GroupedItem<T> {
  key: ConversationBucket
  label: string
  items: T[]
}

/**
 * 分组。空组会被剔除（不显示一个只有标题的空段落）；
 * 组内保持传入顺序（调用方已按时间倒序排好）。
 */
export function groupByTime<T extends { created_at: string }>(
  list: T[],
  now: Date = new Date()
): { key: ConversationBucket; label: string; items: T[] }[] {
  const map = new Map<ConversationBucket, T[]>()
  for (const item of list) {
    const b = bucketOf(item.created_at, now)
    const arr = map.get(b)
    if (arr) arr.push(item)
    else map.set(b, [item])
  }
  return BUCKETS.filter((b) => map.has(b.key)).map((b) => ({
    key: b.key,
    label: b.label,
    items: map.get(b.key)!
  }))
}
