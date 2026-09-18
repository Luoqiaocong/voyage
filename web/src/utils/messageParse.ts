/**
 * 助手消息的 markdown 解析（纯函数，无 Vue 依赖，便于单测）。
 *
 * 设计出发点：普通 AI 聊天界面把回复原样当纯文本渲染，用户看到满屏
 * `**` 与 `-`，像在读 markdown 源码。旅行顾问不会那样给方案——他会分小节、
 * 列条目、把关键信息（名称、价格、时段）挑出来。
 *
 * 解析规则照**真实回复样本**定，不是照 markdown 规范猜的。
 * 实测 3 条真实回复的共同特征：
 *   - 无序列表 3/3
 *   - 「**粗体**」独占一行作小节标题 3/3
 *   - emoji 图标 3/3
 *   - 列表项普遍是「**名称**：描述」的推荐卡形态
 * 故「整行粗体 = 小节标题」这条规则是重点，它不是标准 markdown 写法，
 * 但在这套提示词下是模型的主要小标题形态。
 */

export type BlockKind = 'heading' | 'list' | 'itinerary' | 'para' | 'tip' | 'divider'

export interface ListItem {
  /** 条目标题（来自 **粗体** 前缀或「名称：」的前半段） */
  title: string
  /** 条目说明 */
  desc: string
  /** 条目自带的 emoji 图标 */
  icon: string
}

export interface ItineraryDay {
  no: string
  theme: string
  slots: string[]
}

export interface Block {
  kind: BlockKind
  text: string
  level?: number
  items?: ListItem[]
  days?: ItineraryDay[]
}

/** 行首 emoji / 装饰符号 */
const LEAD_ICON = /^[\p{Extended_Pictographic}\uFE0F\u200D]+\s*/u

/** 提示类段落的开头词 */
export const TIP_LEAD =
  /^(?:提醒|注意|温馨提示|小贴士|建议|贴士|划重点|说明|注：|⚠️|💡)/

/** 行程特征：Day N / 第 N 天 / D1 */
export const DAY_RE = /(?:day\s*(\d+)|第\s*([一二三四五六七八九十\d]+)\s*天|d(\d+))/i

/** 时段词 */
export const SLOT_RE = /(上午|下午|晚上|傍晚|清晨|中午|早上)/

/** 去掉行内 markdown 标记，留下纯文本 */
export function stripInline(s: string): string {
  return s
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1$2')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .trim()
}

/**
 * 把一条列表项拆成「标题 + 说明」。
 *
 * 真实形态：
 *   **全季酒店（湖滨店）**：位置核心，出门就是湖滨步行街
 *   **杭州君悦、杭州四季**：多备有儿童备品
 *   🏨 中端之选（约 500–800 元/晚）——亲子性价比首选
 */
export function splitItem(raw: string): ListItem {
  let s = raw.trim()
  let icon = ''
  const im = s.match(LEAD_ICON)
  if (im) {
    icon = im[0].trim()
    s = s.slice(im[0].length)
  }

  const bold = s.match(/^\*\*(.+?)\*\*\s*[:：]\s*(.+)$/s)
  if (bold) return { title: stripInline(bold[1]), desc: stripInline(bold[2]), icon }

  const onlyBold = s.match(/^\*\*(.+?)\*\*\s*$/)
  if (onlyBold) return { title: stripInline(onlyBold[1]), desc: '', icon }

  const colon = s.match(/^([^：:]{2,24})\s*[:：]\s*(.+)$/s)
  if (colon) return { title: stripInline(colon[1]), desc: stripInline(colon[2]), icon }

  return { title: '', desc: stripInline(s), icon }
}

/** 一批列表项是否构成行程（含天数或时段，且条目不少于 2 条） */
export function looksLikeItinerary(items: string[], whole: string): boolean {
  if (items.length < 2) return false
  const hasDay = DAY_RE.test(whole)
  const slotCount = (whole.match(new RegExp(SLOT_RE.source, 'g')) || []).length
  // 需要「有明确天数」或「时段出现 2 次以上」才算行程，
  // 否则任何提到「下午」的普通建议都会被误判
  return hasDay || slotCount >= 2
}

/** 把行程条目按天分组 */
export function groupByDay(items: string[]): ItineraryDay[] {
  const groups: ItineraryDay[] = []
  let cur: ItineraryDay | null = null
  let seq = 1

  for (const raw of items) {
    const line = stripInline(raw)
    /*
     * 匹配「Day 1 市区文化」「第 2 天：都江堰」「D3 返程」等开头。
     * 天数可能是阿拉伯数字或中文数字，主题可能没有。
     * 用非捕获组拼装，保证分组编号与下面取值一一对应。
     */
    const m = line.match(
      /^(?:day\s*(\d+)|第\s*([一二三四五六七八九十\d]+)\s*天|d(\d+))\s*[:：、\-—]*\s*(.*)$/i
    )
    if (m) {
      const no = m[1] || m[2] || m[3] || String(seq)
      cur = { no: `Day ${no}`, theme: (m[4] || '').trim(), slots: [] }
      groups.push(cur)
      seq += 1
      continue
    }
    if (!cur) {
      cur = { no: `Day ${seq}`, theme: '', slots: [] }
      groups.push(cur)
      seq += 1
    }
    if (line) cur.slots.push(line)
  }
  return groups.filter((g) => g.slots.length || g.theme)
}

/**
 * 主解析：markdown 文本 → 块数组。
 *
 * 用索引扫描而非逐行 for-of，是因为处理空行时需要**向前看一行**：
 * 模型常在「天数标题 + 条目」之间夹空行，
 *
 *     **Day 1 市区文化**
 *
 *     - 上午：宽窄巷子
 *
 *     **Day 2 都江堰**
 *
 * 若见到空行就结算列表，每个 Day 都会成为独立块。
 * 但空行也可能真的表示分段（例如「中端之选」与「高端之选」之间），
 * 所以不能一律忽略——必须看空行之后的那一行是否延续同一列表。
 */
export function parseMessage(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let para: string[] = []
  let listBuf: string[] = []

  const flushPara = () => {
    const t = para.join(' ').trim()
    para = []
    if (!t) return
    if (TIP_LEAD.test(t)) {
      const lead = t.match(TIP_LEAD)?.[0] ?? ''
      blocks.push({ kind: 'tip', text: stripInline(t.slice(lead.length)) })
    } else {
      blocks.push({ kind: 'para', text: stripInline(t) })
    }
  }

  const flushList = () => {
    if (!listBuf.length) return
    const whole = listBuf.join('\n')
    if (looksLikeItinerary(listBuf, whole)) {
      blocks.push({ kind: 'itinerary', text: '', days: groupByDay(listBuf) })
    } else {
      blocks.push({ kind: 'list', text: '', items: listBuf.map(splitItem) })
    }
    listBuf = []
  }

  /** 整行被粗体包裹时的内部文本 */
  const boldInner = (line: string): string | null => {
    const m = line.match(/^\s*\*\*(.+?)\*\*\s*[:：]?\s*$/)
    return m ? stripInline(m[1]) : null
  }

  /** 该行是否延续列表语义（列表项，或天数小标题） */
  const continuesList = (line: string): boolean => {
    if (/^\s*(?:[-*+]|\d+[.、])\s+/.test(line)) return true
    const inner = boldInner(line)
    return inner !== null && DAY_RE.test(inner)
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd()

    // ---- 空行：看下一行决定是分段还是列表内的间隔 ----
    if (!line.trim()) {
      flushPara()
      if (listBuf.length) {
        // 找到下一个非空行
        let j = i + 1
        while (j < lines.length && !lines[j].trim()) j++
        const next = j < lines.length ? lines[j] : ''
        // 下一行仍属同一列表（含天数标题）→ 不结算，保留缓冲
        if (next && continuesList(next)) continue
      }
      flushList()
      continue
    }

    // ---- 天数小标题：并入列表，不结算 ----
    const inner = boldInner(line)
    if (inner !== null && DAY_RE.test(inner)) {
      flushPara()
      listBuf.push(line.trim())
      continue
    }

    // ---- 分隔线 ----
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushList()
      flushPara()
      blocks.push({ kind: 'divider', text: '' })
      continue
    }

    // ---- # 标题 ----
    const h = line.match(/^\s*(#{1,4})\s+(.*)$/)
    if (h) {
      flushList()
      flushPara()
      blocks.push({ kind: 'heading', text: stripInline(h[2]), level: h[1].length })
      continue
    }

    // ---- 列表项 ----
    const li = line.match(/^\s*(?:[-*+]|\d+[.、])\s+(.*)$/)
    if (li) {
      flushPara()
      listBuf.push(li[1])
      continue
    }

    // ---- 其它整行粗体 → 小节标题 ----
    if (inner !== null) {
      flushList()
      flushPara()
      blocks.push({ kind: 'heading', text: inner, level: 3 })
      continue
    }

    // ---- 普通文本 ----
    flushList()
    para.push(line.trim())
  }
  flushList()
  flushPara()
  return blocks
}

/** 行内粗体切片，用于渲染富文本 */
export interface Span {
  bold: boolean
  text: string
}

export function toSpans(s: string): Span[] {
  const out: Span[] = []
  const re = /\*\*(.+?)\*\*/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(s))) {
    if (m.index > last) out.push({ bold: false, text: s.slice(last, m.index) })
    out.push({ bold: true, text: m[1] })
    last = m.index + m[0].length
  }
  if (last < s.length) out.push({ bold: false, text: s.slice(last) })
  return out.length ? out : [{ bold: false, text: s }]
}
