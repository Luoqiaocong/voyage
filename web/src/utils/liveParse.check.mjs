/**
 * 验证流式期间逐字解析的效果：块结构应平滑演化，不应剧烈跳变。
 *
 * 模拟真实的 SSE 逐块到达（一次几个字），每次都对当前累积文本跑一遍解析，
 * 观察块序列如何变化。这是「流式期间也结构化」这个改动的核心风险点。
 *
 * 运行：node web/src/utils/liveParse.check.mjs
 */
import { parseMessage } from './messageParse.ts'

// 一份真实形态的回答（含小标题、列表、提示）
const FULL = `成都这周末天气不错，适合出行：

**🌤️ 天气概览**
- 9月19日（周六）：阴，18~26°C
- 9月20日（周日）：多云，17~25°C

**🎯 景点推荐**
- **青城山**：适合周日去，前山门票 90 元
- **宽窄巷子**：市区内，免费

提醒：青城山山路湿滑，建议穿防滑鞋。`

let pass = 0
let fail = 0

function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

console.log('=== 模拟逐块到达（每块 4 字）===')
const kindsHistory = []
let maxKindsJump = 0
let prevKinds = []

for (let i = 1; i <= FULL.length; i += 4) {
  const partial = FULL.slice(0, i)
  const blocks = parseMessage(partial)
  const kinds = blocks.map((b) => b.kind).join(',')

  if (kinds !== prevKinds.join(',')) {
    kindsHistory.push({ at: i, kinds })
    // 统计块序列的变化幅度（新增/减少多少项）
    const jump = Math.abs(blocks.length - prevKinds.length)
    maxKindsJump = Math.max(maxKindsJump, jump)
    prevKinds = blocks.map((b) => b.kind)
  }
}

console.log(`  文本共 ${FULL.length} 字，块序列变化 ${kindsHistory.length} 次`)
console.log('  关键节点:')
for (const h of kindsHistory.slice(0, 14)) {
  console.log(`    第 ${String(h.at).padStart(3)} 字  ->  ${h.kinds}`)
}

console.log('\n=== 断言 ===')
check('块序列变化次数在合理范围（<=12）', kindsHistory.length <= 12,
  `${kindsHistory.length} 次`)
check('单次变化不剧烈（块数增减 <=1）', maxKindsJump <= 1, `最大跳变 ${maxKindsJump}`)

// 最终结果必须与整段解析一致
const finalBlocks = parseMessage(FULL)
const finalKinds = finalBlocks.map((b) => b.kind).join(',')
console.log(`\n  最终块序列: ${finalKinds}`)
check('最终结构与一次性解析一致', kindsHistory[kindsHistory.length - 1].kinds === finalKinds)

// 逐字到达时不应抛错、也不应产生空块序列之外的东西
let errorCount = 0
for (let i = 0; i <= FULL.length; i++) {
  try {
    const b = parseMessage(FULL.slice(0, i))
    if (!Array.isArray(b)) errorCount++
  } catch {
    errorCount++
  }
}
check('任意长度前缀都能正常解析（无异常）', errorCount === 0, `${errorCount} 次异常`)

// 未闭合的粗体不应吞掉后续文字
const half = '**天气概览'
const hb = parseMessage(half)
check('未闭合的 ** 不吞字', hb.length === 1 && hb[0].text.includes('天气概览'),
  JSON.stringify(hb[0]))

console.log(`\n${'='.repeat(52)}\n流式解析验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)
