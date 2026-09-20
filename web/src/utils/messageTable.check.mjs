/**
 * markdown 表格解析验证。
 *
 * 运行：node web/src/utils/messageTable.check.mjs
 *
 * 用真实场景的样本：模型给车次、票价、天气时会写成 markdown 表格，
 * 解析器必须认出分隔行，否则表格行会被渲染成原始竖线文本。
 */
import { parseMessage, splitTableRow, looksLikeTableRow, TABLE_SEP_RE } from './messageParse.ts'

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

/** 取第一个 table 块 */
function firstTable(text) {
  const blocks = parseMessage(text)
  return blocks.find((b) => b.kind === 'table')
}

console.log('=== 1. 车次表格（真实模型输出形态） ===')
const train = `这是为您查到的车次：

| 车次 | 出发 | 到达 | 历时 | 二等座 |
|---|---|---|---|---|
| G79 | 08:00 | 16:05 | 8小时05分 | ¥862 |
| G65 | 10:11 | 18:12 | 8小时01分 | ¥862 |

祝您旅途愉快！`

const t1 = firstTable(train)
console.log('  表头:', t1?.table?.headers)
console.log('  行数:', t1?.table?.rows?.length)
check('识别为表格', !!t1)
check('表头 5 列', t1?.table?.headers.length === 5, String(t1?.table?.headers.length))
check('表头内容正确', t1?.table?.headers.join(',') === '车次,出发,到达,历时,二等座',
  t1?.table?.headers.join(','))
check('收集到 2 行数据', t1?.table?.rows.length === 2, String(t1?.table?.rows.length))
check('首行首格为车次号', t1?.table?.rows[0][0] === 'G79', t1?.table?.rows[0][0])
check('价格保留 ¥ 符号', t1?.table?.rows[0][4] === '¥862', t1?.table?.rows[0][4])

console.log('\n=== 2. 表格前后的文字仍是独立段落 ===')
const blocks = parseMessage(train)
console.log('  块序列:', blocks.map((b) => b.kind).join(' → '))
check('表格前有段落', blocks[0].kind === 'para', blocks[0].kind)
check('表格后有段落', blocks[blocks.length - 1].kind === 'para', blocks[blocks.length - 1].kind)
check('表格只有一个', blocks.filter((b) => b.kind === 'table').length === 1)

console.log('\n=== 3. 无外层竖线的写法也要认 ===')
const noOuter = `车次 | 出发 | 二等座
--- | --- | ---
G79 | 08:00 | ¥862`
const t2 = firstTable(noOuter)
check('无外层竖线可解析', !!t2, JSON.stringify(t2?.table))
check('表头 3 列', t2?.table?.headers.length === 3, String(t2?.table?.headers.length))

console.log('\n=== 4. 对齐标记（:---:）不影响解析 ===')
const aligned = `| 项目 | 价格 |
|:---|---:|
| 门票 | ¥60 |`
const t3 = firstTable(aligned)
check('带对齐标记可解析', !!t3)
check('数据正确', t3?.table?.rows[0][1] === '¥60', t3?.table?.rows[0][1])

console.log('\n=== 5. 没有分隔行的竖线文本**不能**被当成表格 ===')
// 这是最要紧的一条：仅凭含竖线就判定会把正文变成表格
const prose = `可选方案是 A | B，看您偏好。
另一行也有竖线 | 但不是表格。`
const pb = parseMessage(prose)
console.log('  块序列:', pb.map((b) => b.kind).join(' → '))
check('未误判为表格', !pb.some((b) => b.kind === 'table'),
  pb.map((b) => b.kind).join(','))
check('内容保留为段落', pb.every((b) => b.kind === 'para'), pb.map((b) => b.kind).join(','))

console.log('\n=== 6. 列数与表头不一致时补齐（模型偶尔多写/少写竖线） ===')
const ragged = `| a | b | c |
|---|---|---|
| 1 | 2 |
| 3 | 4 | 5 | 6 |`
const t4 = firstTable(ragged)
console.log('  行:', JSON.stringify(t4?.table?.rows))
check('少列的行补齐到 3 列', t4?.table?.rows[0].length === 3,
  String(t4?.table?.rows[0].length))
check('多列的行截断到 3 列', t4?.table?.rows[1].length === 3,
  String(t4?.table?.rows[1].length))

console.log('\n=== 7. 单元格里的 **粗体** 原样保留（渲染层再切 spans） ===')
const bold = `| 车次 | 说明 |
|---|---|
| **G79** | 最快 |`
const t5 = firstTable(bold)
check('粗体标记未被剥掉', t5?.table?.rows[0][0] === '**G79**', t5?.table?.rows[0][0])

console.log('\n=== 8. 表格与列表混排 ===')
const mixed = `- 先看车次
| 车次 | 价格 |
|---|---|
| G79 | ¥862 |
- 再定酒店`
const mb = parseMessage(mixed)
console.log('  块序列:', mb.map((b) => b.kind).join(' → '))
check('列表与表格都识别', mb.filter((b) => b.kind === 'list').length >= 1
  && mb.filter((b) => b.kind === 'table').length === 1,
  mb.map((b) => b.kind).join(','))

console.log('\n=== 9. 工具函数 ===')
check('splitTableRow 去首尾竖线',
  JSON.stringify(splitTableRow('| a | b |')) === '["a","b"]',
  JSON.stringify(splitTableRow('| a | b |')))
check('looksLikeTableRow 拒绝无竖线行', !looksLikeTableRow('普通文本'))
check('looksLikeTableRow 接受带竖线行', looksLikeTableRow('| a | b |'))
check('TABLE_SEP_RE 接受 |---|---|', TABLE_SEP_RE.test('|---|---|'))
check('TABLE_SEP_RE 接受 --- | ---', TABLE_SEP_RE.test('--- | ---'))
check('TABLE_SEP_RE 拒绝普通行', !TABLE_SEP_RE.test('| 车次 | 价格 |'))

console.log('\n=== 10. 流式场景：表格未写完时不崩 ===')
const partial = `| 车次 | 出发 |
|---|`
const pp = parseMessage(partial)
console.log('  块序列:', pp.map((b) => b.kind).join(' → ') || '（空）')
check('不抛异常且产出块', pp.length > 0, String(pp.length))
// 只有表头 + 分隔行、还没数据行：可接受为「0 行表格」或退化为段落
const hasTable = pp.some((b) => b.kind === 'table')
const table = pp.find((b) => b.kind === 'table')
check('要么是 0 行表格、要么未识别', !hasTable || table.table.rows.length === 0,
  hasTable ? `rows=${table.table.rows.length}` : '未识别为表格')

console.log(`\n${'='.repeat(52)}\n表格解析验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)
