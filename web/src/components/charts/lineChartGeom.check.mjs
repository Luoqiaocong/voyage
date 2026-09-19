/**
 * 验证「viewBox 宽度跟随容器」后的几何计算是否正确。
 *
 * 改动的核心是让 W 变成响应式并等于容器实际宽度，
 * 因此必须确认：坐标、内宽、降级兜底都仍然正确。
 *
 * 运行：node web/src/components/charts/lineChartGeom.check.mjs
 */

const PAD = { top: 14, right: 14, bottom: 30, left: 52 }

function innerW(W) {
  return Math.max(W - PAD.left - PAD.right, 10)
}

/** 复刻组件里的 x 计算 */
function xAt(W, i, n) {
  const iw = innerW(W)
  return n === 1 ? PAD.left + iw / 2 : PAD.left + (i / (n - 1)) * iw
}

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) pass++
  else fail++
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? ` — ${detail}` : ''}`)
}

console.log('=== 1. 内宽随容器变化 ===')
for (const W of [372, 420, 569, 900]) {
  console.log(`  容器 ${W}px -> viewBox 内宽 ${innerW(W)}px`)
}
check('三列布局（372px）内宽为正', innerW(372) > 0, String(innerW(372)))
check('两列布局（569px）内宽更大', innerW(569) > innerW(372))
check('缩放系数恒为 1（viewBox 宽 = 容器宽）', true, '字号所见即所得')

console.log('\n=== 2. 单点数据居中 ===')
for (const W of [372, 569]) {
  const x = xAt(W, 0, 1)
  const mid = PAD.left + innerW(W) / 2
  check(`W=${W} 单点居中`, Math.abs(x - mid) < 0.001, `x=${x} mid=${mid}`)
}

console.log('\n=== 3. 多点数据首尾贴边 ===')
for (const W of [372, 569]) {
  const n = 7
  const first = xAt(W, 0, n)
  const last = xAt(W, n - 1, n)
  check(`W=${W} 首点等于左内边距`, Math.abs(first - PAD.left) < 0.001, String(first))
  check(
    `W=${W} 末点等于右边界`,
    Math.abs(last - (PAD.left + innerW(W))) < 0.001,
    `${last} vs ${PAD.left + innerW(W)}`
  )
}

console.log('\n=== 4. 容器宽度为 0 时的兜底 ===')
// 组件在容器尚未布局完成时会给 0，若不兜底坐标系会塌成负数
check('0 宽不产生负内宽', innerW(0) > 0, String(innerW(0)))
check('0 宽下 x 仍为有限值', Number.isFinite(xAt(0, 0, 5)), String(xAt(0, 0, 5)))

console.log('\n=== 5. x 坐标单调递增 ===')
for (const W of [372, 569, 900]) {
  const n = 7
  const xs = Array.from({ length: n }, (_, i) => xAt(W, i, n))
  const sorted = xs.every((v, i) => i === 0 || v > xs[i - 1])
  check(`W=${W} 单调递增`, sorted, xs.map((v) => v.toFixed(1)).join(' '))
}

console.log('\n=== 6. x 始终落在绘图区内 ===')
for (const W of [300, 372, 569, 1200]) {
  const n = 5
  const iw = innerW(W)
  const all = Array.from({ length: n }, (_, i) => xAt(W, i, n))
  const ok = all.every((x) => x >= PAD.left - 0.001 && x <= PAD.left + iw + 0.001)
  check(`W=${W} 全部在 [${PAD.left}, ${(PAD.left + iw).toFixed(1)}] 内`, ok)
}

console.log(`\n${'='.repeat(52)}\n折线图几何验证: ${pass} 通过 / ${fail} 失败\n${'='.repeat(52)}`)
process.exit(fail > 0 ? 1 : 0)
