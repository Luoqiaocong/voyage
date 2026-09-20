/**
 * 解析器验证：用真实 AI 回复样本跑 parseMessage，检查分块是否符合预期。
 *
 * 为什么要用真实样本：解析规则是照实际回复的形态定的
 * （整行粗体作小标题、列表项是「**名称**：描述」）。
 * 用我编造的样例测只能证明代码自洽，证明不了对真实内容有效。
 *
 * 运行：node web/src/utils/messageParse.check.mjs
 */
import { parseMessage, splitItem, toSpans } from './messageParse.ts'

let pass = 0
let fail = 0

function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

function kinds(blocks) {
  return blocks.map((b) => b.kind).join(',')
}

/* ============ 样本 1：酒店推荐回复（真实输出格式）============ */
const SAMPLE_HOTEL = `西湖边适合亲子的酒店，给你按位置和价位理一下（都在步行 5–10 分钟能到湖边的区域）：

**🏨 中端之选（约 500–800 元/晚）——亲子性价比首选**
- **全季酒店（湖滨店）**：位置核心，出门就是湖滨步行街，逛吃方便
- **柳莺里一带的酒店**：靠近柳浪闻莺，环境安静、绿地多，适合推娃散步

**🏨 高端之选（1200 元+/晚）——设施更适合带娃**
- **杭州君悦、杭州四季**：多备有**儿童备品**，部分带**泳池**，带小孩住起来更省心

**挑房小贴士**
- 优先选「**湖景房 + 可加婴儿床**」的房型
- 尽量避开**临街低楼层**，夜间车流噪音会影响孩子睡觉

顺便提一句，这一带带孩子玩很方便：**花港观鱼**可以喂鱼，**断桥→白堤→孤山**是平地好推车，**浙江省博物馆、中国茶叶博物馆**雨天也能玩，都在西湖周边。

如果你告诉我**预算范围和入住日期**，我可以帮你再精准挑几家、并看看当天的房价和天气～`

console.log('=== 样本 1：真实酒店推荐回复 ===')
const b1 = parseMessage(SAMPLE_HOTEL)
console.log('        块序列:', kinds(b1))
check('首块是段落（导语）', b1[0]?.kind === 'para')
check('识别出小节标题', b1.filter((b) => b.kind === 'heading').length === 3,
  `${b1.filter((b) => b.kind === 'heading').length} 个`)
check('识别出列表块', b1.filter((b) => b.kind === 'list').length === 3,
  `${b1.filter((b) => b.kind === 'list').length} 个`)
check('未被误判为行程', !b1.some((b) => b.kind === 'itinerary'))

const h1 = b1.find((b) => b.kind === 'heading')
check('小节标题去掉了 emoji 与粗体', !h1.text.includes('*') && h1.text.includes('中端之选'),
  h1.text)

const l1 = b1.find((b) => b.kind === 'list')
check('列表项拆出了标题', l1.items[0].title === '全季酒店（湖滨店）', l1.items[0].title)
check('列表项拆出了说明', l1.items[0].desc.includes('湖滨步行街'))
check('列表项标题里的粗体已剥离', !l1.items[0].title.includes('*'))

console.log('\n  --- 列表项拆分细节 ---')
for (const it of l1.items) {
  console.log(`      标题=[${it.title}]  说明=[${it.desc.slice(0, 26)}…]`)
}

/* ============ 样本 2：行程形态 ============ */
const SAMPLE_TRIP = `帮你把成都 3 天安排好了：

**Day 1 市区文化**
- 上午：宽窄巷子，免费
- 下午：人民公园鹤鸣茶社，约 80 元
- 晚上：蜀大侠火锅，人均 150 元

**Day 2 都江堰**
- 上午：都江堰景区，门票 80 元
- 下午：青城山前山，门票 90 元`

console.log('\n=== 样本 2：行程形态 ===')
const b2 = parseMessage(SAMPLE_TRIP)
console.log('        块序列:', kinds(b2))
check('识别出行程块', b2.some((b) => b.kind === 'itinerary'))
const trip = b2.find((b) => b.kind === 'itinerary')
if (trip) {
  check('行程按天分组为 2 天', trip.days.length === 2, `${trip.days.length} 天`)
  check('Day 1 含 3 个时段', trip.days[0].slots.length === 3, `${trip.days[0].slots.length}`)
  console.log('        Day 1:', trip.days[0].no, '|', trip.days[0].theme,
    '|', trip.days[0].slots.length, '项')
}

/* ============ 样本 3：提示类段落 ============ */
const SAMPLE_TIP = `行程排好了。

提醒：故宫周一闭馆，请避开当天安排。`

console.log('\n=== 样本 3：提示段落 ===')
const b3 = parseMessage(SAMPLE_TIP)
console.log('        块序列:', kinds(b3))
check('识别出提示块', b3.some((b) => b.kind === 'tip'))
const tip = b3.find((b) => b.kind === 'tip')
check('提示块去掉了「提醒：」前缀', tip && !tip.text.startsWith('提醒'), tip?.text)

/* ============ 边界：不应误判的情况 ============ */
console.log('\n=== 边界 ===')
const b4 = parseMessage('建议下午去西湖，晚上看音乐喷泉。')
check('单句含时段不误判为行程', !b4.some((b) => b.kind === 'itinerary'), kinds(b4))

const b5 = parseMessage('## 标题\n\n普通段落一。\n\n- 条目 A\n- 条目 B')
check('标准 # 标题被识别', b5[0]?.kind === 'heading' && b5[0].level === 2)
check('列表被识别', b5.some((b) => b.kind === 'list'))

const b6 = parseMessage('')
check('空文本不报错', Array.isArray(b6))

const b7 = parseMessage('只有一行普通文字')
check('单段落正常', b7.length === 1 && b7[0].kind === 'para')

console.log('\n=== splitItem 边界 ===')
check('纯说明无标题', splitItem('免费，适合散步').title === '')
const withIcon = splitItem('🍜 龙抄手：人均 40 元')
check('剥离 emoji 作图标', withIcon.icon === '🍜' && withIcon.title === '龙抄手',
  `icon=${withIcon.icon} title=${withIcon.title}`)

console.log('\n=== toSpans ===')
const sp = toSpans('前**中**后')
check('粗体切片正确', sp.length === 3 && sp[1].bold && sp[1].text === '中')

console.log(`\n${'='.repeat(52)}\n解析器验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)

