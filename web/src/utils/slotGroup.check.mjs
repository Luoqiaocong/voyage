/**
 * 时段归组与文字处理验证。
 *
 * 运行：node web/src/utils/slotGroup.check.mjs
 */
import {
  groupBySlot,
  sortGroupsBySlot,
  normalizeSlot,
  detectSlot,
  stripSlotPrefix,
} from './messageParse.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

const shape = (gs) => gs.map((g) => `${g.label || '—'}:${g.items.length}`).join(' ')

console.log('=== 1. 连续同时段合并 ===')
// 这是改动的核心场景：上午连着 3 条，原先每条都挂「上午」
const g1 = groupBySlot(
  ['上午：宽窄巷子', '上午：人民公园', '上午：青羊宫', '下午：武侯祠', '晚上：火锅'],
  (s) => detectSlot(s),
)
console.log('  ', shape(g1))
check('上午 3 条合成一组', g1[0].label === '上午' && g1[0].items.length === 3, shape(g1))
check('下午单独一组', g1[1].label === '下午' && g1[1].items.length === 1)
check('晚上单独一组', g1[2].label === '晚上')
check('总组数 3', g1.length === 3, String(g1.length))

console.log('\n=== 2. 不重排：时段跳变时各自成组 ===')
// 上午→下午→上午 的顺序本身有信息量，不应被重排合并
const g2 = groupBySlot(
  ['上午：A', '下午：B', '上午：C'],
  (s) => detectSlot(s),
)
console.log('  ', shape(g2))
check('三个组（不跨组合并）', g2.length === 3, shape(g2))
check('第一组上午、第二组下午、第三组上午',
  g2[0].label === '上午' && g2[1].label === '下午' && g2[2].label === '上午', shape(g2))

console.log('\n=== 3. 认不出时段的条目不硬塞 ===')
const g3 = groupBySlot(
  ['上午：A', '集合出发', '下午：B'],
  (s) => detectSlot(s),
)
console.log('  ', shape(g3))
check('无时段条目单独成组', g3.length === 3 && g3[1].label === '', shape(g3))
check('未并入相邻的上午组', g3[0].items.length === 1, String(g3[0].items.length))

console.log('\n=== 4. sortGroupsBySlot 按上午→下午→晚上排序 ===')
const g4 = sortGroupsBySlot(
  groupBySlot(['晚上：C', '上午：A', '下午：B'], (s) => detectSlot(s)),
)
console.log('  ', shape(g4))
check('排序后为 上午/下午/晚上',
  g4.map((g) => g.label).join(',') === '上午,下午,晚上',
  g4.map((g) => g.label).join(','))

console.log('\n=== 5. 无时段组排在最后 ===')
const g5 = sortGroupsBySlot(
  groupBySlot(['自由活动', '晚上：C', '上午：A'], (s) => detectSlot(s)),
)
console.log('  ', shape(g5))
check('无时段组在末尾', g5[g5.length - 1].label === '', shape(g5))

console.log('\n=== 6. normalizeSlot 归一各种写法 ===')
const cases = [
  ['morning', 'morning'], ['afternoon', 'afternoon'], ['evening', 'evening'],
  ['上午', 'morning'], ['早上', 'morning'], ['清晨', 'morning'],
  ['下午', 'afternoon'], ['中午', 'afternoon'],
  ['晚上', 'evening'], ['傍晚', 'evening'], ['夜间', 'evening'],
  ['MORNING', 'morning'], [' 上午 ', 'morning'],
  ['', undefined], [null, undefined], ['随便什么', undefined],
]
for (const [input, want] of cases) {
  const got = normalizeSlot(input)
  check(`normalizeSlot(${JSON.stringify(input)}) = ${want}`, got === want, String(got))
}

console.log('\n=== 7. stripSlotPrefix 去掉条目开头的时段词 ===')
const stripCases = [
  ['上午：宽窄巷子，免费', '宽窄巷子，免费'],
  ['下午:人民公园', '人民公园'],
  ['晚上、火锅', '火锅'],
  ['上午 故宫', '故宫'],
  ['清晨—看日出', '看日出'],
  ['宽窄巷子，免费', '宽窄巷子，免费'],
  // 句中出现的时段词不能被误删
  ['去喝下午茶', '去喝下午茶'],
  ['安排一次晚间散步', '安排一次晚间散步'],
]
for (const [input, want] of stripCases) {
  const got = stripSlotPrefix(input)
  check(`strip(${JSON.stringify(input)})`, got === want, `got=${JSON.stringify(got)}`)
}

console.log('\n=== 8. 结构化数据（行程详情页用法）===')
const acts = [
  { name: 'A', time_slot: 'evening' },
  { name: 'B', time_slot: 'morning' },
  { name: 'C', time_slot: 'morning' },
]
const g8 = sortGroupsBySlot(groupBySlot(acts, (a) => a.time_slot))
console.log('  ', g8.map((g) => `${g.label}[${g.items.map((i) => i.name).join('')}]`).join(' '))
check('按时间排序且组内保持原序',
  g8[0].label === '上午' && g8[0].items.map((i) => i.name).join('') === 'BC' &&
  g8[1].label === '晚上' && g8[1].items[0].name === 'A',
  JSON.stringify(g8.map((g) => [g.label, g.items.map((i) => i.name)])))

console.log('\n=== 9. 边界 ===')
check('空数组返回空', groupBySlot([], (x) => x).length === 0)
check('全部无时段时只有一组', groupBySlot(['a', 'b'], () => undefined).length === 1)
check('排序不修改原数组', (() => {
  const src = groupBySlot(['晚上：C', '上午：A'], (s) => detectSlot(s))
  const before = src.map((g) => g.label).join(',')
  sortGroupsBySlot(src)
  return src.map((g) => g.label).join(',') === before
})())

console.log(`\n${'='.repeat(52)}\n时段归组验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)
