/**
 * 行程交通文本解析。
 *
 * ## 为什么是「解析文本」而不是「加结构化字段」
 *
 * 数据库里 `plan.transport` 是一段自由文本，但**模型已经写进了结构化信息**：
 *
 *   去程：北京丰台→成都东 D997 20:41-次日08:46（动卧¥900）；
 *   返程：成都西→北京西 K118 21:12-次日05:26（硬卧¥426）
 *
 *   北京西→桂林北 G309 09:00-16:58（二等座 ¥949，推荐）；
 *   备选 G311 北京西→桂林站 11:05-19:03（¥951.5）
 *
 *   广州南→成都东 G3712 14:45-22:13（二等座 ¥644，全程最快）；
 *   备选 G2276 12:25-20:31 或 G3708 14:00-21:32
 *
 * 三种变体（去返程 / 推荐+备选 / 仅备选车次）都覆盖到了。
 * 因此在**前端解析**即可拿到车次、时间、座别、价格、是否推荐、备选，
 * 不必改后端提取提示词与 schema、也不必迁移已存数据 —— 代价小得多。
 *
 * ## 已知的脆弱点（如实记录）
 *
 * 解析依赖模型当前的书写习惯。若将来攻略写法变化（例如把座别写在车次前、
 * 用「～」代替「-」连接时刻），这里会解析不到对应字段。
 * 因此：
 *   · 每个字段都是**可选**的，解析不到就不渲染那一块，不会出现空占位
 *   · 兜底保留原始文本 `raw`，实在认不出来时按纯文本展示
 *   · 有 tests 覆盖上面三种真实变体（见 .dsh 校验脚本 / tests）
 */

export interface TicketLeg {
  /** '去程' | '返程' | '推荐' | '备选' | '' */
  role: string
  /** 车次，如 G309 / D997 */
  trainNo: string
  /** 出发站（取不到为空） */
  from: string
  /** 到达站（取不到为空） */
  to: string
  /** 发车时刻，如 09:00（可能带「次日」） */
  depart: string
  /** 到达时刻 */
  arrive: string
  /** 座别，如 二等座 / 硬卧 */
  seat: string
  /** 价格原文，如 ¥949（可能是区间 ¥300-500） */
  price: string
  /** 是否被标为推荐 */
  recommended: boolean
}

export interface TransportInfo {
  legs: TicketLeg[]
  /** 主车次（第一条），无则 null */
  primary: TicketLeg | null
  /** 备选车次 */
  alternatives: TicketLeg[]
  /** 原文。认不出结构时用它兜底展示 */
  raw: string
}

const TRAIN_NO_RE = /\b([GDCKZT]\d{1,4})\b/
/** 时刻对：09:00-16:58 / 20:41-次日08:46 */
const TIME_RANGE_RE = /(\d{1,2}:\d{2})\s*[-–~至]\s*(次日)?\s*(\d{1,2}:\d{2})/
/** 座别：二等座 / 一等座 / 硬卧 / 软卧 / 动卧 / 硬座 / 无座 / 商务座 */
const SEAT_RE = /(商务座|一等座|二等座|动卧|软卧|硬卧|硬座|软座|无座)/
/** 价格：¥949 / ¥951.5 / ¥300-500 */
const PRICE_RE = /¥\s*(\d+(?:\.\d+)?(?:\s*[-~]\s*\d+(?:\.\d+)?)?)/

/** 从一段文本里抽一条车票信息 */
function parseLeg(segment: string, role: string): TicketLeg | null {
  const train = TRAIN_NO_RE.exec(segment)
  const time = TIME_RANGE_RE.exec(segment)
  if (!train && !time) return null

  const seat = SEAT_RE.exec(segment)
  const price = PRICE_RE.exec(segment)

  /*
   * 车站对：形如「北京西→桂林北」。
   *
   * 搜**整段**而不是只搜车次之前 —— 语序有两种：
   *   「北京西→桂林北 G309 09:00-…」 车站**在**车次前
   *   「G311 北京西→桂林站 11:05-…」 车站**在**车次后
   * 只搜前半段会漏掉后者（实测踩过：备选丢了「桂林站」）。
   *
   * 顺序很关键：**先剥角色前缀，再判断是不是站名**。
   * 反过来（先过滤后剥）会把正确的匹配一起丢掉 ——
   * 「去程：北京丰台→成都东」的 from 带着「去程：」，
   * 纯中文校验失败，于是唯一正确的候选也被过滤掉，最终取不到车站。
   */
  const ROLE_WORDS = ['去程', '返程', '回程', '前往', '返回', '备选']
  const stripRole = (s: string) => {
    let out = s.trim()
    for (const w of ROLE_WORDS) {
      if (out.startsWith(w)) out = out.slice(w.length).replace(/^[:：]\s*/, '')
    }
    return out
  }
  /** 站名只由中文、·、字母组成（如「两江四湖·象鼻山」「T3航站楼」） */
  const isStationName = (s: string) => /^[\u4e00-\u9fa5·A-Za-z]{2,}$/.test(s)

  const stations = [
    ...segment.matchAll(/([^\s→\-—>]{2,10}?)\s*[→\-—>]\s*([^\s→\-—>（(]{2,10}?)(?=[\s（(]|$)/g)
  ]
    .map((m) => ({ from: stripRole(m[1]), to: stripRole(m[2]) }))
    // 过滤掉时刻对（「20:41-次日08:46」形状相同但不是站名）
    .filter((p) => isStationName(p.from) && isStationName(p.to))

  let from = ''
  let to = ''
  if (stations.length) {
    // 取最后一处：语序上车站紧邻车次，靠后的更可能是站名而非正文里的地名
    const last = stations[stations.length - 1]
    from = last.from
    to = last.to
  }

  return {
    role,
    trainNo: train ? train[1] : '',
    from,
    to,
    depart: time ? time[1] : '',
    arrive: time ? time[3] : '',
    seat: seat ? seat[1] : '',
    price: price ? `¥${price[1].replace(/\s/g, '')}` : '',
    recommended: /推荐/.test(segment)
  }
}

/**
 * 解析 plan.transport。
 *
 * ## 分两层切分，顺序不能颠倒
 *
 * 第一层按 `；` 切成「行程段」——这一层的语义是**独立行程**（去程 / 返程）。
 * 第二层在**段内**找「备选」，切出主车次与备选车次。
 *
 * 最初把两层混在一起切，结果「去程…；返程…」被当成两条备选，
 * 而「备选 G311 北京西→桂林站」又因为顿号切分把车站名切碎了。
 * 分层之后两个问题同时消失。
 *
 * 返回的 legs 已按「主车次在前、备选在后」排好；解析不出任何车次时
 * legs 为空数组，调用方应退回展示 raw 文本。
 */
export function parseTransport(text?: string | null): TransportInfo {
  const raw = (text ?? '').trim()
  if (!raw) return { legs: [], primary: null, alternatives: [], raw }

  const legs: TicketLeg[] = []

  // 第一层：按分号切成独立行程段
  for (const part of raw.split(/[；;]/).map((s) => s.trim()).filter(Boolean)) {
    const roleMatch = /^(去程|返程|回程|前往|返回)\s*[:：]?/.exec(part)
    const role = roleMatch ? roleMatch[1] : ''

    /*
     * 第二层：段内找「备选」。
     *
     * ⚠️ 判断是 `>= 0` 而不是 `> 0`。写成 `> 0` 时，
     * 整段以「备选」开头（index 恰为 0）的写法会走进 else 分支，
     * 只解析出第一辆备选车次、后续的整条丢失。
     * 实测：「备选 G2276 12:25-20:31 或 G3708 14:00-21:32」只出 G2276。
     * 前两条真实数据能通过纯属侥幸（它们的备选段以站名开头）。
     */
    const altIdx = part.search(/备选/)
    if (altIdx >= 0) {
      const main = altIdx > 0 ? parseLeg(part.slice(0, altIdx), role) : null
      if (main) legs.push(main)
      pushAlternatives(legs, part.slice(altIdx))
    } else {
      const main = parseLeg(part, role)
      if (main) legs.push(main)
    }
  }

  if (!legs.length) return { legs: [], primary: null, alternatives: [], raw }

  return { legs, primary: legs[0], alternatives: legs.slice(1), raw }
}

/**
 * 从「备选 …」这一段里切出若干备选车次。
 *
 * 切分符只认「或」与顿号，**不认逗号** —— 逗号会出现在
 * 「G311 北京西→桂林站 11:05-19:03（¥951.5）」这类片段内部，
 * 按逗号切会把车站名切碎（实测踩过：备选丢了「桂林站」）。
 *
 * 两侧允许空格：「备选 G2276 12:25-20:31 或 G3708 14:00-21:32」里
 * 「或」前后都有空格，直接 split('或') 是能切开的，
 * 但先 trim 掉首尾空格再切更稳（实测踩过只识别出 1 条备选）。
 */
function pushAlternatives(legs: TicketLeg[], altPart: string): void {
  const body = altPart.replace(/^备选\s*[:：]?/, '').trim()
  for (const piece of body.split(/\s*或\s*|、/)) {
    const l = parseLeg(piece.trim(), '备选')
    if (l) legs.push(l)
  }
}
