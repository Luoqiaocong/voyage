/**
 * 时间展示工具。
 *
 * ## 与后端的约定（重要）
 *
 * 后端 `to_local_display()` 已把 UTC 时间转成 **Asia/Shanghai 的本地时间字符串**
 * 再下发，格式为 `YYYY-MM-DD HH:MM:SS`（**不带时区标记**）。
 *
 * 因此前端**绝不能再做时区换算** —— 那个字符串已经是本地时间，
 * 交给 `new Date()` 解析会被当成本机时区，在非东八区的机器上又偏一次。
 * 这里所有函数都按「无时区的本地时间字符串」处理。
 *
 * ## 为什么要有这个模块
 *
 * 格式与语义需要统一：各处自行处理会各自假设不同的后端格式
 * （直接渲染原串、按 ISO 截断、自行做相对时间），显示不一致。
 */

/** 后端下发的本地时间字符串形如 `2026-09-19 17:30:00` */
const LOCAL_RE = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/

interface Parts {
  y: number
  mo: number
  d: number
  h: number
  mi: number
  s: number
}

/** 解析后端时间字符串；无法识别时返回 null（调用方降级为原样显示） */
export function parseLocalTime(raw?: string | null): Parts | null {
  if (!raw) return null
  const m = LOCAL_RE.exec(raw)
  if (!m) return null
  return {
    y: Number(m[1]),
    mo: Number(m[2]),
    d: Number(m[3]),
    h: Number(m[4]),
    mi: Number(m[5]),
    s: Number(m[6] ?? 0)
  }
}

const pad = (n: number) => String(n).padStart(2, '0')

/** `2026-09-19 17:30` —— 用于表格与详情，最常用的形式 */
export function formatDateTime(raw?: string | null): string {
  const p = parseLocalTime(raw)
  if (!p) return raw ?? ''
  return `${p.y}-${pad(p.mo)}-${pad(p.d)} ${pad(p.h)}:${pad(p.mi)}`
}

/** `2026-09-19` —— 只到日，用于列表里空间紧张的场景 */
export function formatDate(raw?: string | null): string {
  const p = parseLocalTime(raw)
  if (!p) return raw ?? ''
  return `${p.y}-${pad(p.mo)}-${pad(p.d)}`
}

/** `09-19 17:30` —— 同年时省略年份，用于紧凑列表 */
export function formatShort(raw?: string | null): string {
  const p = parseLocalTime(raw)
  if (!p) return raw ?? ''
  return `${pad(p.mo)}-${pad(p.d)} ${pad(p.h)}:${pad(p.mi)}`
}

/**
 * 相对时间：今天只显示时刻，昨天显示「昨天 HH:MM」，更早显示 `M/D`。
 *
 * 用于会话列表这类「判断新旧」比「知道确切时刻」更重要的位置。
 * 超过一年则带上年份，否则用户无法判断是哪一年的记录。
 */
export function formatRelative(raw?: string | null): string {
  const p = parseLocalTime(raw)
  if (!p) return raw ?? ''

  const now = new Date()
  const sameDay =
    p.y === now.getFullYear() && p.mo === now.getMonth() + 1 && p.d === now.getDate()
  if (sameDay) return `${pad(p.h)}:${pad(p.mi)}`

  // 用本地构造的 Date 做日期差，避免时区问题（两端都是本地时间）
  const then = new Date(p.y, p.mo - 1, p.d)
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diffDays = Math.round((today.getTime() - then.getTime()) / 86_400_000)

  if (diffDays === 1) return `昨天 ${pad(p.h)}:${pad(p.mi)}`
  if (diffDays < 7 && diffDays > 0) return `${diffDays} 天前`
  if (p.y !== now.getFullYear()) return `${p.y}-${pad(p.mo)}-${pad(p.d)}`
  return `${p.mo}/${p.d}`
}
