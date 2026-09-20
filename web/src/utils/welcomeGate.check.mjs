/**
 * 欢迎屏显示条件的判定验证。
 *
 * 运行：node web/src/utils/welcomeGate.check.mjs
 *
 * 为什么把这段逻辑从组件里抽出来单测：
 *   它出过一次真实故障 —— 判据写成「列表为空就直接显示欢迎屏」，
 *   导致无会话时 markWelcomeShown() 完全无效，用户点「开始新的旅程」
 *   看到的界面纹丝不动（欢迎屏那一分支里根本没有输入框）。
 *   而它同时还要满足「当天首次才显示」与「刷新不重复弹」，
 *   三个条件互相牵制，靠手点是测不全的。
 */
import { shouldShowWelcome, WELCOME_SUPPRESS_REASONS } from './welcomeGate.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

/** 今天的 ISO 串（判定只看「是否今天」，不必造任意时刻） */
const TODAY = new Date().toISOString()
/** 明显不是今天：用于「跨天」场景 */
const LONG_AGO = '2020-01-01T00:00:00.000Z'

console.log('\n=== 1. 无会话（新用户 / 列表被清空）===')

check(
  '从未显示过 → 显示欢迎屏',
  shouldShowWelcome({
    dismissed: false, listLoaded: true, conversationCount: 0, lastWelcomeAt: '',
  }) === true
)

check(
  '今天已显示过 → 不再显示（否则每次刷新都会重弹）',
  shouldShowWelcome({
    dismissed: false, listLoaded: true, conversationCount: 0, lastWelcomeAt: TODAY,
  }) === false
)

check(
  '列表中已有会话但今天没见过 → 显示',
  shouldShowWelcome({
    dismissed: false, listLoaded: true, conversationCount: 3, lastWelcomeAt: LONG_AGO,
  }) === true
)

check(
  '有会话且今天见过 → 不显示',
  shouldShowWelcome({
    dismissed: false, listLoaded: true, conversationCount: 3, lastWelcomeAt: TODAY,
  }) === false
)

console.log('\n=== 2. 用户已主动关闭（本次进入内）===')

check(
  '**无会话 + 已关闭 → 不显示**（这正是「点了没反应」的根因场景）',
  shouldShowWelcome({
    dismissed: true, listLoaded: true, conversationCount: 0, lastWelcomeAt: '',
  }) === false
)

check(
  '已关闭优先于「今天没见过」',
  shouldShowWelcome({
    dismissed: true, listLoaded: true, conversationCount: 5, lastWelcomeAt: LONG_AGO,
  }) === false
)

check(
  '已关闭优先于「列表为空」',
  shouldShowWelcome({
    dismissed: true, listLoaded: true, conversationCount: 0, lastWelcomeAt: TODAY,
  }) === false
)

console.log('\n=== 3. 列表尚未加载完（防闪烁）===')

check(
  '未加载完且无会话 → 不显示（否则会先闪一下欢迎屏）',
  shouldShowWelcome({
    dismissed: false, listLoaded: false, conversationCount: 0, lastWelcomeAt: '',
  }) === false
)

check(
  '未加载完但已关闭 → 依然不显示',
  shouldShowWelcome({
    dismissed: true, listLoaded: false, conversationCount: 0, lastWelcomeAt: '',
  }) === false
)

console.log('\n=== 4. 异常输入不应抛错 ===')

let threw = false
try {
  shouldShowWelcome({
    dismissed: false, listLoaded: true, conversationCount: 0, lastWelcomeAt: 'not-a-date',
  })
} catch {
  threw = true
}
check('无法解析的时间不抛异常', !threw)
check(
  '无法解析的时间按「没见过」处理（宁可多显示一次，也不要永远不显示）',
  shouldShowWelcome({
    dismissed: false, listLoaded: true, conversationCount: 0, lastWelcomeAt: 'not-a-date',
  }) === true
)

console.log('\n=== 5. 关闭原因枚举完备（供组件侧判断用）===')
check(
  'SUPPRESS 原因含 dismissed / notLoaded / seenToday',
  ['dismissed', 'notLoaded', 'seenToday'].every((k) =>
    WELCOME_SUPPRESS_REASONS.includes(k)
  ),
  WELCOME_SUPPRESS_REASONS.join(', ')
)

console.log(`\n${'='.repeat(56)}`)
console.log(`欢迎屏显示条件验证: ${pass} 通过 / ${fail} 失败`)
console.log('='.repeat(56))
process.exit(fail ? 1 : 0)
