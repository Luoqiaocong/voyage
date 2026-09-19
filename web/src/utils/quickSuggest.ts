/**
 * 快捷提问的上下文推荐。
 *
 * 为什么用本地启发式而不是让模型生成：
 *   建议要在用户看到对话的**同一瞬间**出现。让模型生成意味着等一次请求，
 *   界面会先显示通用建议再换成针对性建议（闪一下），体验反而更差；
 *   而且每次切会话都要多一次调用。启发式的准确率足够低风险 ——
 *   推荐错了用户只是没点，代价很小。
 *
 * 做法：从最近的对话文本里提取「目的地」，据此给出贴合场景的追问。
 * 目的是把用户从「不知道还能问什么」推到「这是我想问的下一步」。
 */

/** 常见目的地（含别名）。不追求全，够覆盖高频场景即可 */
const CITY_ALIASES: Record<string, string> = {
  北京: '北京', 上海: '上海', 广州: '广州', 深圳: '深圳', 成都: '成都',
  重庆: '重庆', 杭州: '杭州', 苏州: '苏州', 南京: '南京', 西安: '西安',
  厦门: '厦门', 青岛: '青岛', 大连: '大连', 长沙: '长沙', 武汉: '武汉',
  昆明: '昆明', 丽江: '丽江', 大理: '大理', 三亚: '三亚', 海口: '海口',
  桂林: '桂林', 贵阳: '贵阳', 哈尔滨: '哈尔滨', 天津: '天津', 珠海: '珠海',
  香港: '香港', 澳门: '澳门', 台北: '台北', 新疆: '新疆', 拉萨: '拉萨',
  敦煌: '敦煌', 西宁: '西宁', 银川: '银川', 太原: '太原', 沈阳: '沈阳',
  福州: '福州', 南宁: '南宁', 石家庄: '石家庄', 郑州: '郑州', 济南: '济南',
  兰州: '兰州', 呼和浩特: '呼和浩特'
}

/** 从文本里找出出现的目的地；返回按出现位置排序后的去重列表 */
export function detectCities(text: string): string[] {
  const found: { city: string; at: number }[] = []
  for (const [alias, city] of Object.entries(CITY_ALIASES)) {
    const at = text.indexOf(alias)
    if (at >= 0) found.push({ city, at })
  }
  found.sort((a, b) => a.at - b.at)
  return [...new Set(found.map((f) => f.city))]
}

/** 文本是否在问天气相关 */
function asksWeather(text: string): boolean {
  return /天气|气温|下雨|穿什么|带伞|冷不冷|热不热/.test(text)
}

/** 文本是否在问交通相关 */
function asksTransport(text: string): boolean {
  return /高铁|车次|机票|航班|火车|怎么去|交通|火车票/.test(text)
}

/** 文本是否已是一份行程规划 */
function asksItinerary(text: string): boolean {
  return /行程|攻略|规划|几天|安排|路线/.test(text)
}

/** 文本是否在问预算/花费 */
function asksBudget(text: string): boolean {
  return /预算|多少钱|花费|贵不贵|开销|人均/.test(text)
}

/**
 * 依据最近的对话内容生成推荐提问。
 *
 * @param recentText 最近的对话文本（用户与助手消息拼接即可，顺序无关）
 * @returns 推荐列表；无上下文可用时返回空数组，由调用方回退到默认建议
 */
export function suggestFromContext(recentText: string): string[] {
  const text = (recentText || '').slice(-2000)   // 只看最近部分，避免早期话题干扰
  if (!text.trim()) return []

  const cities = detectCities(text)
  const dest = cities[cities.length - 1]      // 最后提到的通常是当前关注的目的地
  const origin = cities.length > 1 ? cities[0] : ''

  const out: string[] = []

  if (dest) {
    if (asksWeather(text)) {
      out.push(`${dest}这几天适合穿什么？`)
    } else {
      out.push(`帮我查一下${dest}这几天的天气`)
    }

    if (asksItinerary(text)) {
      // 已在规划行程 -> 推进到更具体的落地问题
      out.push(`${dest}有哪些必吃的本地菜？`)
      out.push(`${dest}的行程再紧凑一点，去掉哪些合适？`)
    } else if (asksTransport(text)) {
      out.push(`基于这些车次，帮我排${dest}的行程`)
      out.push(`${dest}住哪个区域比较方便？`)
    } else {
      out.push(`帮我规划${dest}的 3 天行程`)
      out.push(`${dest}有哪些小众但值得去的地方？`)
    }

    if (origin && origin !== dest) {
      out.push(`${origin}到${dest}的高铁有哪些`)
    }
  } else {
    /*
     * 认不出目的地时给通用追问。
     *
     * 这一支原先只覆盖了三种话题，其余情况返回空数组、由调用方回退到
     * 固定三条示例 —— 那等于「正在问答中，却给出与当前话题无关的建议」。
     * 实测「这个大概要多少钱」就落到这里：它明明在问预算，
     * 却因为没提城市而拿不到任何贴合的建议。
     * 故补上预算分支，并把兜底从「返回空」改为「给一条仍然相关的追问」。
     */
    if (asksBudget(text)) {
      out.push('这个预算包含往返交通吗？')
      out.push('能不能给一份更省钱的方案？')
    }
    if (asksWeather(text)) {
      out.push('那需要带伞吗？')
      out.push('和上个月比，这段时间算旺季吗？')
    }
    if (asksTransport(text)) {
      out.push('帮我把这些车次按时间排一下')
      out.push('有没有更早一班的？')
    }
    if (asksItinerary(text)) {
      out.push('预算大概需要多少？')
      out.push('能不能再紧凑一点？')
    }
  }

  // 最多三条：多了会把输入框顶得太高，也削弱「建议」的分量
  return [...new Set(out)].slice(0, 3)
}
