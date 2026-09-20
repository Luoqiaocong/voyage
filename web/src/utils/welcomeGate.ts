/**
 * 欢迎屏的显示判定。
 *
 * 抽成纯函数而不是留在组件里，是因为这段逻辑同时被三个条件牵制，
 * 必须一起看，故固化成可单测的形式：
 *
 *   dismissed        本次进入内用户已主动关闭 → 一定不显示（优先级最高）
 *   listLoaded       会话列表还没加载完 → 不下结论（防闪一下欢迎屏）
 *   lastWelcomeAt    今天是否已经见过 → 见过就不再显示（对空列表同样生效，
 *                    否则「无会话」会绕过它变成每次都显示）
 */

/** 抑制显示的原因，供调用方区分（例如排查「为什么没显示」） */
export const WELCOME_SUPPRESS_REASONS = ['dismissed', 'notLoaded', 'seenToday'] as const

/** 判断欢迎屏是否显示的输入 */
export interface WelcomeGateState {
  /** 本次进入内用户是否已主动关闭欢迎屏 */
  dismissed: boolean
  /** 会话列表是否已加载完成 */
  listLoaded: boolean
  /**
   * 会话数量。
   *
   * 当前判定**刻意不使用**它 —— 保留参数是为了让调用方一次把相关状态都给全，
   * 也便于将来若要加「有会话就一定不显示」这类规则时不必改签名。
   */
  conversationCount: number
  /** 上次显示欢迎屏的时刻（ISO 串，可为空） */
  lastWelcomeAt: string
  /** 自定义「是否今天」的判定（便于测试注入固定时钟） */
  isToday?: (value: string) => boolean
}

/**
 * 判断当前是否应当显示欢迎屏。
 *
 * @returns 是否显示
 */
export function shouldShowWelcome({
  dismissed,
  listLoaded,
  conversationCount: _conversationCount,
  lastWelcomeAt,
  isToday = defaultIsToday,
}: WelcomeGateState): boolean {
  // 用户已明确关闭：优先于其余一切。
  // 少了这一条，「无会话」场景会因为下面「没见过就显示」而永远卸不掉欢迎屏。
  if (dismissed) return false

  // 数据还没到，先不下结论。宁可短暂空着，也不要先闪一遍欢迎屏再切走。
  if (!listLoaded) return false

  // 今天已经见过就不再显示。
  //
  // 注意这里**刻意不看 conversationCount**：
  // 「有没有会话」不该决定「要不要看介绍」——那是当天是否见过的问题。
  // 否则新用户与「清空过会话」的用户每次刷新都会重看一遍欢迎屏，
  // 而他们其实已经点过「开始新的旅程」了。
  return !isToday(lastWelcomeAt)
}

/**
 * 时间是否落在今天（本地自然日）。
 *
 * 解析失败一律按「不是今天」处理 —— 这样欢迎屏会多显示一次，
 * 而不是因为一条脏记录就永远不再显示。
 */
function defaultIsToday(value: string): boolean {
  if (!value) return false
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return false
  const now = new Date()
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  )
}
