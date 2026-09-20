/**
 * 会话时间分组的边界验证。
 *
 * 运行：node web/src/utils/conversationGroup.check.mjs
 *
 * 重点验边界，而不是「大概能分对」：
 *   · 日界：今天 00:00 与昨天 23:59 必须分属不同组
 *   · 「7 天内」不含今天昨天（否则一个会话会出现两次归属的错觉）
 *   · 未来时间归入今天（时钟偏差不该造出一个空组）
 *   · 无法解析的时间不丢项，沉到「更早」
 */
import { bucketOf, dayDiff, groupByTime } from './conversationGroup.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

// 固定「现在」= 2026-09-20 15:00 本地时间，避免用真实时钟导致结果随时段漂移
const NOW = new Date(2026, 8, 20, 15, 0, 0) // 月份从 0 起，8 = 9 月
const at = (y, m, d, hh = 12, mm = 0) => new Date(y, m - 1, d, hh, mm).toISOString()

console.log('=== 1. 日界（最容易出错的地方）===')
check('今天 00:00 → 今天', bucketOf(at(2026, 9, 20, 0, 0), NOW) === 'today')
check('今天 23:59 → 今天', bucketOf(at(2026, 9, 20, 23, 59), NOW) === 'today')
check('昨天 23:59 → 昨天', bucketOf(at(2026, 9, 19, 23, 59), NOW) === 'yesterday')
check('昨天 00:00 → 昨天', bucketOf(at(2026, 9, 19, 0, 0), NOW) === 'yesterday')
// 这两条正是「按小时差算」会算错的例子
check('今天凌晨 1 点仍属今天（按自然日，不看小时差）',
  bucketOf(at(2026, 9, 20, 1, 0), NOW) === 'today')
check('前一天 23:30 属昨天（不因不足 24 小时就并入今天）',
  bucketOf(at(2026, 9, 19, 23, 30), NOW) === 'yesterday')

console.log('\n=== 2. 「7 天内」不含今天与昨天 ===')
check('2 天前 → 7 天内', bucketOf(at(2026, 9, 18), NOW) === 'week')
check('6 天前 → 7 天内', bucketOf(at(2026, 9, 14), NOW) === 'week')
check('7 天前 → 30 天内（边界外移一档）',
  bucketOf(at(2026, 9, 13), NOW) === 'month')
check('昨天不落入 7 天内（避免重复归属）',
  bucketOf(at(2026, 9, 19), NOW) !== 'week')

console.log('\n=== 3. 30 天内 ===')
check('7 天前 → 30 天内', bucketOf(at(2026, 9, 13), NOW) === 'month')
check('29 天前 → 30 天内', bucketOf(at(2026, 8, 22), NOW) === 'month')
check('30 天前 → 更早', bucketOf(at(2026, 8, 21), NOW) === 'earlier')
check('一年前 → 更早', bucketOf(at(2025, 9, 20), NOW) === 'earlier')

console.log('\n=== 4. 跨月/跨年不因「同一个月」而误判 ===')
check('上月同日（31 天差）→ 更早', bucketOf(at(2026, 8, 20), NOW) === 'earlier')
check('去年 12 月 31 日 → 更早', bucketOf(at(2025, 12, 31), NOW) === 'earlier')

console.log('\n=== 5. 异常输入不丢项 ===')
check('空字符串 → 更早（不抛错）', bucketOf('', NOW) === 'earlier')
check('乱码 → 更早', bucketOf('not-a-date', NOW) === 'earlier')
check('未来时间 → 今天（时钟偏差不该造出空组）',
  bucketOf(at(2026, 9, 21), NOW) === 'today')
check('未来 1 小时 → 今天', bucketOf(at(2026, 9, 20, 16, 0), NOW) === 'today')

console.log('\n=== 6. dayDiff 口径 ===')
check('今天 diff=0', dayDiff(new Date(2026, 8, 20, 9, 0), NOW) === 0)
check('昨天 diff=1', dayDiff(new Date(2026, 8, 19, 9, 0), NOW) === 1)
check('明天 diff=-1', dayDiff(new Date(2026, 8, 21, 9, 0), NOW) === -1)

console.log('\n=== 7. groupByTime 组合行为 ===')
const list = [
  { id: 'a', created_at: at(2026, 9, 20) }, // 今天
  { id: 'b', created_at: at(2026, 9, 20, 9) }, // 今天（顺序应保持）
  { id: 'c', created_at: at(2026, 9, 19) }, // 昨天
  { id: 'd', created_at: at(2026, 9, 16) }, // 7 天内
  { id: 'e', created_at: at(2026, 9, 1) }, // 30 天内
  { id: 'f', created_at: at(2026, 7, 1) }, // 更早
]
const groups = groupByTime(list, NOW)
console.log('  分组结果:', groups.map((g) => `${g.label}(${g.items.length})`).join(' / '))
check('分 5 组', groups.length === 5, String(groups.length))
check('顺序为 今天→昨天→7天内→30天内→更早',
  groups.map((g) => g.key).join(',') === 'today,yesterday,week,month,earlier',
  groups.map((g) => g.key).join(','))
check('今天组含 2 条且保持传入顺序',
  groups[0].items.map((x) => x.id).join('') === 'ab',
  groups[0].items.map((x) => x.id).join(''))
check('总数不丢不重',
  groups.reduce((n, g) => n + g.items.length, 0) === list.length)

console.log('\n=== 8. 空组被剔除 ===')
const onlyToday = groupByTime([{ id: 'x', created_at: at(2026, 9, 20) }], NOW)
check('只有今天有数据时只出 1 组', onlyToday.length === 1, String(onlyToday.length))
check('不出现空的「昨天」段落', !onlyToday.some((g) => g.key === 'yesterday'))
check('空列表返回空数组', groupByTime([], NOW).length === 0)

console.log(
  `\n${'=' * 56}\n会话分组验证: ${pass} 通过 / ${fail} 失败\n${'=' * 56}`
)
process.exit(fail ? 1 : 0)
