/**
 * 快捷提问的上下文推荐验证。
 *
 * 运行：node web/src/utils/quickSuggest.check.mjs
 */
import { detectCities, suggestFromContext } from './quickSuggest.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

console.log('=== 1. detectCities：从文本里认目的地 ===')
const cityCases = [
  ['帮我规划广州到北京的 3 天行程', ['广州', '北京']],
  ['三亚有什么好玩的', ['三亚']],
  ['我想去成都和重庆', ['成都', '重庆']],
  ['随便聊聊', []],
  ['今天天气怎么样', []],
  // 「南京」不应被「京」等单字规则误伤（我们只做整词匹配）
  ['北京南京都想去', ['北京', '南京']],
]
for (const [text, want] of cityCases) {
  const got = detectCities(text)
  check(`${text.slice(0, 20)} -> [${want}]`, JSON.stringify(got) === JSON.stringify(want),
    `得到 [${got}]`)
}

console.log('\n=== 2. 有目的地 + 正在规划行程 -> 推进到落地问题 ===')
const s1 = suggestFromContext('帮我规划广州到北京的 3 天行程，预算 3000')
console.log('  ', s1)
check('推荐非空', s1.length > 0)
check('提到北京', s1.some((s) => s.includes('北京')), JSON.stringify(s1))
check('不超过 3 条', s1.length <= 3, String(s1.length))
check('与行程话题相关（吃/紧凑/小众）',
  s1.some((s) => /吃|紧凑|小众|必吃/.test(s)), JSON.stringify(s1))

console.log('\n=== 3. 问过天气 -> 推荐穿衣/天气类追问 ===')
const s2 = suggestFromContext('三亚这几天天气怎么样')
console.log('  ', s2)
check('提到三亚', s2.some((s) => s.includes('三亚')), JSON.stringify(s2))
check('与天气/穿衣相关', s2.some((s) => /穿|天气/.test(s)), JSON.stringify(s2))

console.log('\n=== 4. 查过车次 -> 推荐基于车次排行程 ===')
const s3 = suggestFromContext('查一下明天广州南到北京西的高铁')
console.log('  ', s3)
check('提到北京', s3.some((s) => s.includes('北京')), JSON.stringify(s3))
check('含「基于车次排行程」类建议',
  s3.some((s) => /基于|行程|住哪个/.test(s)), JSON.stringify(s3))

console.log('\n=== 5. 用户刚聊三亚（用户举的例子）===')
const s4 = suggestFromContext('用户：三亚好玩吗\n助手：三亚很适合潜水，蜈支洲岛水质最好')
console.log('  ', s4)
check('能识别出三亚', s4.some((s) => s.includes('三亚')), JSON.stringify(s4))

console.log('\n=== 6. 认不出目的地时仍给贴合当前话题的追问 ===')
// 覆盖天气/交通/行程之外的话题（如预算），
// 不能回退到与当前对话无关的固定三条示例。
const s5 = suggestFromContext('这个大概要多少钱')
console.log('  ', s5)
check('预算类追问有建议（不再回退到无关示例）', s5.length > 0, JSON.stringify(s5))
check('建议与预算相关', s5.every((s) => /预算|省钱|交通/.test(s)), JSON.stringify(s5))

const s5b = suggestFromContext('会不会下雨')
console.log('   天气类:', s5b)
check('天气类追问有建议', s5b.length > 0, JSON.stringify(s5b))

const s5c = suggestFromContext('你好呀')
console.log('   纯闲聊:', s5c)
check('纯闲聊无上下文时返回空（由调用方回退默认示例）',
  s5c.length === 0, JSON.stringify(s5c))

console.log('\n=== 7. 空文本 / 无上下文 -> 返回空数组（由调用方回退默认）===')
check('空字符串返回 []', suggestFromContext('').length === 0)
check('仅空白返回 []', suggestFromContext('   \n  ').length === 0)

console.log('\n=== 8. 只看最近内容（早期话题不应干扰）===')
const long = '成都好玩'.repeat(300) + ' 现在说说三亚的天气'
const s6 = suggestFromContext(long)
console.log('  ', s6)
check('以最近提到的三亚为准', s6.some((s) => s.includes('三亚')), JSON.stringify(s6))

console.log('\n=== 9. 去重 ===')
const s7 = suggestFromContext('北京北京北京 天气')
check('推荐项无重复', new Set(s7).size === s7.length, JSON.stringify(s7))

console.log(`\n${'='.repeat(52)}\n快捷推荐验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)
