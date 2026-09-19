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
check('展示里说明昨日为 0', String(fz.amount).includes('昨日 0'), fz.amount)

console.log('\n=== 6. 边界：两天都是 0 ===')
check('[0,0] 返回 null', dayOverDay([0, 0]) === null,
  JSON.stringify(dayOverDay([0, 0])))

console.log('\n=== 7. 持平 ===')
const flat = dayOverDay([50, 50])
console.log('  [50, 50] ->', flat)
check('方向为 flat', flat?.tone === 'flat')
check('数目为 0', flat?.delta === 0, String(flat?.delta))
const ff = formatDayOverDay(flat, fmt)
check('文案为「与昨日持平」', ff.amount === '与昨日持平', ff.amount)
check('持平不给百分比', ff.percent === '', JSON.stringify(ff.percent))

console.log('\n=== 8. 格式化：数目与百分比分成两段 ===')
const f = formatDayOverDay(dayOverDay([100, 350]), fmt)
console.log('  [100, 350] ->', f)
check('箭头为 ⬆', f.arrow === '⬆', f.arrow)
check('数目段含 250', f.amount.includes('250'), f.amount)
check('百分比段为 +250%', f.percent === '+250%', f.percent)

const fdown = formatDayOverDay(dayOverDay([400, 100]), fmt)
console.log('  [400, 100] ->', fdown)
check('下降箭头为 ⬇', fdown.arrow === '⬇', fdown.arrow)
check('百分比段为 −75%', fdown.percent === '−75%', fdown.percent)

console.log('\n=== 9. 自定义格式化函数生效（Token 用紧凑格式） ===')
const compactFmt = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n))
const big = formatDayOverDay(dayOverDay([1000, 2500]), compactFmt)
console.log('  [1000, 2500] with compact ->', big)
check('数目用紧凑格式 1.5k', big.amount.includes('1.5k'), big.amount)

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
