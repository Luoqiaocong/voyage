/**
 * 「相对昨日」涨跌标注验证。
 *
 * 运行：node web/src/utils/trendCompare.check.mjs
 *
 * 重点：
 *   1. 口径是 (后−前)/前（标准增幅），不是「后/前」—— 两者差 100 个百分点
 *   2. 同时给出**具体数目**与**百分比**
 *   3. 边界不出现 NaN / Infinity / 误导性的 +0
 */
import { dayOverDay, formatDayOverDay } from './trendCompare.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

const fmt = (n) => String(n)

console.log('=== 1. 口径：(后−前)/前 ===')
// 昨日 100 → 今日 200：数目 +100，百分比 +100%
const g = dayOverDay([100, 200])
console.log('  [100, 200] ->', g)
check('数目为 100', g?.delta === 100, String(g?.delta))
check('百分比为 +100%', g?.pct === 100, String(g?.pct))
check('方向为 up', g?.tone === 'up')
// 若口径被改成「后/前」，pct 会是 200
check('口径不是「后/前」（否则 pct=200）', g?.pct !== 200, String(g?.pct))

console.log('\n=== 2. 下降 ===')
const d = dayOverDay([200, 100])
console.log('  [200, 100] ->', d)
check('数目为 100（绝对值）', d?.delta === 100, String(d?.delta))
check('百分比为 -50%', d?.pct === -50, String(d?.pct))
check('方向为 down', d?.tone === 'down')

console.log('\n=== 3. 只取最后两天（多天序列） ===')
// 7 天：前面的值不应影响结果
const many = dayOverDay([1, 2, 3, 4, 5, 100, 250])
console.log('  [1,2,3,4,5,100,250] ->', many)
check('用最后两天 100→250', many?.prev === 100 && many?.curr === 250,
  `prev=${many?.prev} curr=${many?.curr}`)
check('数目 150', many?.delta === 150, String(many?.delta))
check('百分比 +150%', many?.pct === 150, String(many?.pct))

console.log('\n=== 4. 边界：数据不足 ===')
check('0 个点返回 null', dayOverDay([]) === null)
check('1 个点返回 null', dayOverDay([5]) === null)
check('2 个点可用', dayOverDay([1, 2]) !== null)

console.log('\n=== 5. 边界：昨日为 0 ===')
const fromZero = dayOverDay([0, 7])
console.log('  [0, 7] ->', fromZero)
check('方向为 up', fromZero?.tone === 'up')
check('数目为 7', fromZero?.delta === 7, String(fromZero?.delta))
check('百分比为 null（无穷大不给）', fromZero?.pct === null, String(fromZero?.pct))
const fz = formatDayOverDay(fromZero, fmt)
console.log('  格式化 ->', fz)
check('展示里不含 Infinity', !/Infinity|NaN/.test(JSON.stringify(fz)), JSON.stringify(fz))
check('只给数目片子', fz.amount !== '' && fz.percent === '',
  JSON.stringify({ amount: fz.amount, percent: fz.percent }))
check('数目片带箭头', fz.amount.startsWith('⬆'), fz.amount)

console.log('\n=== 6. 边界：两天都是 0 ===')
check('[0,0] 返回 null', dayOverDay([0, 0]) === null,
  JSON.stringify(dayOverDay([0, 0])))

console.log('\n=== 7. 持平 ===')
const flat = dayOverDay([50, 50])
console.log('  [50, 50] ->', flat)
check('方向为 flat', flat?.tone === 'flat')
check('数目为 0', flat?.delta === 0, String(flat?.delta))
const ff = formatDayOverDay(flat, fmt)
check('文案为「持平」', ff.amount === '持平', ff.amount)
check('持平不给百分比', ff.percent === '', JSON.stringify(ff.percent))

console.log('\n=== 8. 格式化：两个各自带箭头的量 ===')
// 用户指定形态：⬆ 1.0M   ⬆ 100%   —— 两个箭头各指自己的方向
const f = formatDayOverDay(dayOverDay([100, 350]), fmt)
console.log('  [100, 350] ->', f)
check('数目片为「⬆ 250」', f.amount === '⬆ 250', f.amount)
check('幅度片为「⬆ 250%」', f.percent === '⬆ 250%', f.percent)
check('两个片子都带箭头',
  f.amount.startsWith('⬆') && f.percent.startsWith('⬆'),
  `${f.amount} / ${f.percent}`)

const fdown = formatDayOverDay(dayOverDay([400, 100]), fmt)
console.log('  [400, 100] ->', fdown)
check('数目片为「⬇ 300」', fdown.amount === '⬇ 300', fdown.amount)
check('幅度片为「⬇ 75%」', fdown.percent === '⬇ 75%', fdown.percent)
check('下降时两个箭头都是 ⬇',
  fdown.amount.startsWith('⬇') && fdown.percent.startsWith('⬇'),
  `${fdown.amount} / ${fdown.percent}`)
check('幅度片不再用 +/- 号（改由箭头表意）',
  !f.percent.includes('+') && !fdown.percent.includes('−'),
  `${f.percent} / ${fdown.percent}`)

console.log('\n=== 9. 自定义格式化函数生效（Token 用紧凑格式） ===')
const compactFmt = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n))
const big = formatDayOverDay(dayOverDay([1000, 2500]), compactFmt)
console.log('  [1000, 2500] with compact ->', big)
check('数目片用紧凑格式「⬆ 1.5k」', big.amount === '⬆ 1.5k', big.amount)
check('幅度片为「⬆ 150%」', big.percent === '⬆ 150%', big.percent)
// 用户给的例子形态是「⬆ 1.0M  ⬆ 100%」。
// 反推输入：增量 1.0M 且增幅 100% → 基数 = 增量 / 增幅 = 1.0M。
// 即 prev = 1.0M、curr = 2.0M。
// （我先后两次心算成 500k→1.0M 与 500k→1.5M，实际都不是这个组合 ——
//   这也是为什么这条用例值得留着：数目与增幅是**两个独立量**，
//   不能凭直觉从其中一个推出另一个。）
const mFmt = (n) => `${(n / 1e6).toFixed(1)}M`
const mega = formatDayOverDay(dayOverDay([1000000, 2000000]), mFmt)
console.log('  [1.0M, 2.0M] ->', mega)
check('形态匹配用户示例「⬆ 1.0M ⬆ 100%」',
  mega.amount === '⬆ 1.0M' && mega.percent === '⬆ 100%',
  `${mega.amount} / ${mega.percent}`)
// 对照：同样数目的增量（1.0M），基数不同则增幅不同 —— 500k→1.5M 是 200%。
// 这一条正是「两个数各自独立」的证据。
const mega2 = formatDayOverDay(dayOverDay([500000, 1500000]), mFmt)
console.log('  [500k, 1.5M] ->', mega2)
check('增量同为 1.0M 但增幅为 200%（两个数独立计算）',
  mega2.amount === '⬆ 1.0M' && mega2.percent === '⬆ 200%',
  `${mega2.amount} / ${mega2.percent}`)

console.log('\n=== 10. 不出现 NaN / Infinity ===')
for (const v of [[0, 0], [0, 1], [1, 0], [1e9, 1], [1, 1e9], [0.1, 0.2]]) {
  const r = dayOverDay(v)
  const s = JSON.stringify(r) + JSON.stringify(r ? formatDayOverDay(r, fmt) : null)
  check(`[${v}] 输出正常`, !/NaN|Infinity|undefined/.test(s), s.slice(0, 90))
}

console.log('\n=== 11. 负值不比较（否则百分比方向会翻转） ===')
// 这个指标不可能为负，但一旦出现负值，除法会翻转符号：
// [-1,-2] 是下降，pct 却算成 +100%，标注会显示「⬇ 1  +100%」自相矛盾。
// 故守卫为直接返回 null —— 不显示好过显示错的。
check('[-1,-2] 返回 null（不显示矛盾标注）', dayOverDay([-1, -2]) === null,
  JSON.stringify(dayOverDay([-1, -2])))
check('[1,-2] 返回 null', dayOverDay([1, -2]) === null)
check('[-1,2] 返回 null', dayOverDay([-1, 2]) === null)
check('[0,0] 仍返回 null', dayOverDay([0, 0]) === null)
// 正常非负输入不受影响
check('[0,5] 仍可用', dayOverDay([0, 5]) !== null)
check('[5,0] 仍可用', dayOverDay([5, 0]) !== null)

console.log(`\n${'='.repeat(52)}\n相对昨日涨跌验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)
