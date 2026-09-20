/**
 * 行程交通解析验证。
 *
 * 运行：node web/src/utils/transportParse.check.mjs
 *
 * 断言基准全部来自**数据库里的真实 transport 文本**（不是编的样例）——
 * 这三条覆盖了模型实际写出的三种变体：
 *   1. 去程 + 返程（两段独立行程）
 *   2. 主车次（带「推荐」）+ 备选（带车站）
 *   3. 主车次 + 两个备选（只有车次与时刻）
 *
 * 解析器最怕的是「看起来能跑、遇到真实写法就漏字段」，所以基准必须是真实数据。
 */
import { parseTransport } from './transportParse.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

console.log('=== 1. 真实数据：去程 + 返程（成都 id=3）===')
const s1 =
  '去程：北京丰台→成都东 D997 20:41-次日08:46（动卧¥900）；返程：成都西→北京西 K118 21:12-次日05:26（硬卧¥426）'
const t1 = parseTransport(s1)
console.log(`  legs=${t1.legs.length} primary=${t1.primary?.trainNo} alts=${t1.alternatives.length}`)
check('解析出 2 段', t1.legs.length === 2, String(t1.legs.length))
check('主车次 D997', t1.primary?.trainNo === 'D997', t1.primary?.trainNo)
check('主车次角色为去程', t1.primary?.role === '去程', t1.primary?.role)
check('出发站 北京丰台', t1.primary?.from === '北京丰台', t1.primary?.from)
check('到达站 成都东', t1.primary?.to === '成都东', t1.primary?.to)
check('发车 20:41', t1.primary?.depart === '20:41', t1.primary?.depart)
check('到达 08:46（次日）', t1.primary?.arrive === '08:46', t1.primary?.arrive)
check('座别 动卧', t1.primary?.seat === '动卧', t1.primary?.seat)
check('价格 ¥900', t1.primary?.price === '¥900', t1.primary?.price)
check('返程车次 K118', t1.legs[1]?.trainNo === 'K118', t1.legs[1]?.trainNo)
check('返程角色为返程', t1.legs[1]?.role === '返程', t1.legs[1]?.role)
check('返程座别 硬卧', t1.legs[1]?.seat === '硬卧', t1.legs[1]?.seat)
check('返程价格 ¥426', t1.legs[1]?.price === '¥426', t1.legs[1]?.price)
check('去返程都不算「备选」', t1.legs.every((l) => l.role !== '备选'))

console.log('\n=== 2. 真实数据：推荐 + 备选带车站（桂林 id=4）===')
const s2 =
  '北京西→桂林北 G309 09:00-16:58（二等座 ¥949，推荐）；备选 G311 北京西→桂林站 11:05-19:03（¥951.5）'
const t2 = parseTransport(s2)
console.log(`  legs=${t2.legs.length} primary=${t2.primary?.trainNo} alts=${t2.alternatives.length}`)
check('主车次 G309', t2.primary?.trainNo === 'G309', t2.primary?.trainNo)
check('标记为推荐', t2.primary?.recommended === true)
check('座别 二等座', t2.primary?.seat === '二等座', t2.primary?.seat)
check('价格 ¥949', t2.primary?.price === '¥949', t2.primary?.price)
check('出发站 北京西', t2.primary?.from === '北京西', t2.primary?.from)
check('到达站 桂林北', t2.primary?.to === '桂林北', t2.primary?.to)
check('识别出 1 条备选', t2.alternatives.length === 1, String(t2.alternatives.length))
check('备选车次 G311', t2.alternatives[0]?.trainNo === 'G311', t2.alternatives[0]?.trainNo)
/*
 * 注意这里断言的是「它在备选列表里」，而不是 role 字段等于「备选」。
 * role 表达的是**行程段**（去程/返程），主/备由它在 legs 中的位置决定；
 * 混为一谈会让「返程」也被标成备选（实测踩过这个坑，见 parseTransport 注释）。
 */
check('备选被归入 alternatives（位置而非 role 决定主/备）',
  t2.alternatives[0] === t2.legs[1])
check('备选带自己的车站 桂林站', t2.alternatives[0]?.to === '桂林站', t2.alternatives[0]?.to)
check('备选价格含小数 ¥951.5', t2.alternatives[0]?.price === '¥951.5', t2.alternatives[0]?.price)
check('备选不算推荐', t2.alternatives[0]?.recommended === false)

console.log('\n=== 3. 真实数据：两个备选、只有车次与时刻（成都 id=2）===')
const s3 =
  '广州南→成都东 G3712 14:45-22:13（二等座 ¥644，全程最快）；备选 G2276 12:25-20:31 或 G3708 14:00-21:32'
const t3 = parseTransport(s3)
console.log(`  legs=${t3.legs.length} alts=${t3.alternatives.length} -> ${t3.legs.map((l) => l.trainNo).join(', ')}`)
check('主车次 G3712', t3.primary?.trainNo === 'G3712', t3.primary?.trainNo)
check('识别出 2 条备选', t3.alternatives.length === 2, String(t3.alternatives.length))
check('备选依次为 G2276 / G3708',
  t3.alternatives[0]?.trainNo === 'G2276' && t3.alternatives[1]?.trainNo === 'G3708',
  t3.alternatives.map((l) => l.trainNo).join(','))
check('备选时刻解析正确 12:25', t3.alternatives[0]?.depart === '12:25', t3.alternatives[0]?.depart)
check('备选无座别时留空（不编造）', t3.alternatives[0]?.seat === '', JSON.stringify(t3.alternatives[0]?.seat))
check('备选无价格时留空', t3.alternatives[0]?.price === '', JSON.stringify(t3.alternatives[0]?.price))
check('主车次价格 ¥644', t3.primary?.price === '¥644', t3.primary?.price)

console.log('\n=== 4. 边界：不该崩、也不该编造 ===')
const empty = parseTransport('')
check('空字符串 → legs 为空', empty.legs.length === 0)
check('空字符串 → primary 为 null', empty.primary === null)
check('空字符串 → 保留 raw（空串）', empty.raw === '')

const plain = parseTransport('建议自驾前往，沿途风景不错')
check('无车次无时刻的纯描述 → 不产出 legs', plain.legs.length === 0, String(plain.legs.length))
check('纯描述 → 保留 raw 供兜底展示', plain.raw === '建议自驾前往，沿途风景不错')

const nullish = parseTransport(null)
check('null 输入不报错', nullish.legs.length === 0 && nullish.raw === '')
const undef = parseTransport(undefined)
check('undefined 输入不报错', undef.legs.length === 0 && undef.raw === '')

console.log('\n=== 5. 价格区间与无座别 ===')
const ranged = parseTransport('广州南→成都东 G3712 14:45-22:13（¥644-688）')
check('价格区间保留为 ¥644-688', ranged.primary?.price === '¥644-688', ranged.primary?.price)
check('无座别时 seat 留空', ranged.primary?.seat === '', JSON.stringify(ranged.primary?.seat))

console.log('\n=== 6. 有「推荐」字样才标推荐 ===')
const notRec = parseTransport('广州南→成都东 G3712 14:45-22:13（二等座 ¥644）')
check('无「推荐」字样 → recommended=false', notRec.primary?.recommended === false)

console.log(
  `\n${'=' * 56}\n交通解析验证: ${pass} 通过 / ${fail} 失败\n${'=' * 56}`
)
process.exit(fail ? 1 : 0)
