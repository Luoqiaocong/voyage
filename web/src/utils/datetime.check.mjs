/**
 * 时间展示工具验证。
 *
 * 运行：node web/src/utils/datetime.check.mjs
 *
 * 重点验证「不做二次时区换算」——后端下发的已经是东八区本地时间字符串，
 * 若前端再交给 new Date() 解析，在非东八区机器上会再偏一次。
 */
import {
  formatDate,
  formatDateTime,
  formatRelative,
  formatShort,
  parseLocalTime,
} from './datetime.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

console.log('=== 1. 解析后端格式（YYYY-MM-DD HH:MM:SS） ===')
const p = parseLocalTime('2026-09-19 17:30:45')
console.log('  ', p)
check('年份', p?.y === 2026)
check('月份', p?.mo === 9)
check('日', p?.d === 19)
check('时', p?.h === 17)
check('分', p?.mi === 30)
check('秒', p?.s === 45)

console.log('\n=== 2. 兼容仍然带 T 的 ISO 形式 ===')
const p2 = parseLocalTime('2026-09-19T17:30:00')
check('T 分隔也能解析', p2?.h === 17 && p2?.d === 19, JSON.stringify(p2))

console.log('\n=== 3. 格式化输出 ===')
check('formatDateTime', formatDateTime('2026-09-19 17:30:45') === '2026-09-19 17:30',
  formatDateTime('2026-09-19 17:30:45'))
check('formatDate', formatDate('2026-09-19 17:30:45') === '2026-09-19',
  formatDate('2026-09-19 17:30:45'))
check('formatShort', formatShort('2026-09-19 17:30:45') === '09-19 17:30',
  formatShort('2026-09-19 17:30:45'))

console.log('\n=== 4. 只接受两位补零的约定格式；不合规的**原样返回**而非猜测 ===')
// 后端用 strftime 生成，一定补零，故解析器只认两位。
// 对不合规输入的处理是「原样返回」——不猜、不改写。
// 这比强行解析更安全：猜错会把 9:05 显示成别的时间，而原样返回
// 至少能让人看出「这里格式不对」。
check('两位补零可解析', formatDateTime('2026-09-19 09:05:00') === '2026-09-19 09:05',
  formatDateTime('2026-09-19 09:05:00'))
check('个位数小时不解析、原样返回',
  formatDateTime('2026-09-19 9:05:00') === '2026-09-19 9:05:00',
  formatDateTime('2026-09-19 9:05:00'))
check('parseLocalTime 对不合规输入返回 null',
  parseLocalTime('2026-09-19 9:05:00') === null,
  JSON.stringify(parseLocalTime('2026-09-19 9:05:00')))

console.log('\n=== 5. 相对时间：今天只显示时刻 ===')
const now = new Date()
const pad = (n) => String(n).padStart(2, '0')
const todayStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} 08:05:00`
const rel = formatRelative(todayStr)
console.log(`  今天 ${todayStr} -> ${rel}`)
check('今天显示为 HH:MM', /^\d{2}:\d{2}$/.test(rel), rel)
check('时刻正确', rel === '08:05', rel)

console.log('\n=== 6. 相对时间：昨天 ===')
const y = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
const yStr = `${y.getFullYear()}-${pad(y.getMonth() + 1)}-${pad(y.getDate())} 22:10:00`
const relY = formatRelative(yStr)
console.log(`  昨天 ${yStr} -> ${relY}`)
check('显示「昨天 HH:MM」', relY === '昨天 22:10', relY)

console.log('\n=== 7. 相对时间：更早（同年）显示 M/D ===')
const older = `${now.getFullYear()}-01-05 12:00:00`
const relO = formatRelative(older)
console.log(`  ${older} -> ${relO}`)
check('显示 M/D', /^\d+\/\d+$/.test(relO), relO)

console.log('\n=== 8. 跨年时带年份（否则无法判断是哪一年） ===')
const lastYear = `${now.getFullYear() - 1}-06-15 12:00:00`
const relLY = formatRelative(lastYear)
console.log(`  ${lastYear} -> ${relLY}`)
check('含年份', relLY.includes(String(now.getFullYear() - 1)), relLY)

console.log('\n=== 9. 空值 / 非法值降级 ===')
check('空字符串返回空', formatDateTime('') === '')
check('null 返回空', formatDateTime(null) === '')
check('非法值原样返回', formatDateTime('不是时间') === '不是时间')
check('undefined 相对时间为空', formatRelative(undefined) === '')

console.log('\n=== 10. 关键：不做时区换算 ===')
// 后端给的是东八区本地时间 17:30，无论本机在哪个时区，展示都应是 17:30。
// 若实现里用了 new Date('...') + getHours()，在 UTC 机器上会变成 09:30。
check('17:30 原样展示（不因本机时区改变）',
  formatDateTime('2026-09-19 17:30:00') === '2026-09-19 17:30',
  formatDateTime('2026-09-19 17:30:00'))
check('本机时区偏移不影响输出',
  new Date('2026-09-19 17:30:00').getHours() === 17
    ? true
    : formatDateTime('2026-09-19 17:30:00') === '2026-09-19 17:30',
  `本机 getHours=${new Date('2026-09-19 17:30:00').getHours()}`)

console.log(`\n${'='.repeat(52)}\n时间工具验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)
