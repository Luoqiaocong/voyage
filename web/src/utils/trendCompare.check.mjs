/**
 * 涨跌幅度标记验证。
 *
 * 运行：node web/src/utils/trendCompare.check.mjs
 *
 * 重点验证口径：(后−前)/前，即标准增幅。
 * 这组用例是**防止口径被改成「后/前」而无人察觉** —— 两者恰好差 100 个百分点，
 * 很容易在重构时被无意改掉，而界面上看不出异常。
 */
import { halfCompare } from './trendCompare.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

console.log('=== 1. 口径：标准增幅 (后−前)/前 ===')
// 前半段 [100,100] 合计 200，后半段 [200,200] 合计 400 → 增幅 100%
check('翻倍 = ⬆100%', halfCompare([100, 100, 200, 200])?.text === '⬆ 100%',
  halfCompare([100, 100, 200, 200])?.text)
// 前半 200，后半 600 → 增幅 200%
check('三倍 = ⬆200%', halfCompare([100, 100, 300, 300])?.text === '⬆ 200%',
  halfCompare([100, 100, 300, 300])?.text)
// 前半 200，后半 100 → 降幅 50%
check('腰斩 = ⬇50%', halfCompare([100, 100, 50, 50])?.text === '⬇ 50%',
  halfCompare([100, 100, 50, 50])?.text)
// 若口径被误改为「后/前」，翻倍会变成 200%，此用例会失败
const doubled = halfCompare([100, 100, 200, 200])?.text
check('口径不是「后/前」（否则会显示 200%）', !String(doubled).includes('200'), doubled)

console.log('\n=== 2. 方向与颜色 tone ===')
check('增长为 up', halfCompare([1, 1, 2, 2])?.tone === 'up')
check('下降为 down', halfCompare([4, 4, 2, 2])?.tone === 'down')
check('持平为 flat', halfCompare([100, 100, 100, 100])?.tone === 'flat')

console.log('\n=== 3. 边界：数据不足 ===')
check('3 个点返回 null', halfCompare([1, 2, 3]) === null)
check('2 个点返回 null', halfCompare([1, 2]) === null)
check('0 个点返回 null', halfCompare([]) === null)
check('4 个点可用', halfCompare([1, 1, 2, 2]) !== null)

console.log('\n=== 4. 边界：全 0 不显示标记 ===')
// 显示 ⬆0% 会让人以为「有增长」，实际什么都没发生
check('全 0 返回 null', halfCompare([0, 0, 0, 0]) === null,
  JSON.stringify(halfCompare([0, 0, 0, 0])))

console.log('\n=== 5. 边界：前半段为 0 无法算百分比 ===')
const fromZero = halfCompare([0, 0, 5, 5])
console.log('  ', fromZero)
check('不显示 ∞%', !String(fromZero?.text).includes('∞'), fromZero?.text)
check('改用「新增」表达', String(fromZero?.text).includes('新增'), fromZero?.text)
check('方向为 up', fromZero?.tone === 'up')
check('新增量正确（5+5=10）', String(fromZero?.text).includes('10'), fromZero?.text)

console.log('\n=== 6. 边界：不足 1% 视为持平 ===')
const tiny = halfCompare([100, 100, 100, 100.5])
console.log('  ', tiny)
check('0.25% 显示持平', tiny?.tone === 'flat', tiny?.text)

console.log('\n=== 7. 奇数长度：中位点归入后半段 ===')
// 5 个点 → mid=2，前半 [0,1)，即前 2 个；后半为后 3 个
const odd = halfCompare([0, 0, 10, 10, 10])
console.log('  [0,0,10,10,10] ->', odd?.text)
check('前半为 0 时走「新增」分支', String(odd?.text).includes('新增'), odd?.text)
check('新增量为 30', String(odd?.text).includes('30'), odd?.text)

console.log('\n=== 8. 小数值不出现 NaN / Infinity ===')
for (const v of [[0, 0, 1, 1], [1, 1, 0, 0], [0.1, 0.1, 0.2, 0.2], [1e6, 1e6, 1, 1]]) {
  const r = halfCompare(v)
  const bad = /NaN|Infinity|undefined/.test(String(r?.text))
  check(`[${v}] 输出正常`, !bad, r?.text)
}

console.log(`\n${'='.repeat(52)}\n涨跌标记验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)
