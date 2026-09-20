/**
 * 行程主题标签 → 语义色。
 *
 * ## 配色思路
 *
 * 1. **只在已有色板里取值**，不引入新色相。项目设计系统已有
 *    blue / cyan / gold / green / slate 五族（见 styles/main.css），
 *    新加色族会让整站观感散掉。
 * 2. **浅底 + 深字**，饱和度压得很低（都是 *-50/100 级别的底），
 *    符合「清爽浅色、不花哨」的要求；不用纯色实心块。
 * 3. **语义对应而非随机分配**：颜色要与标签含义有关，用户才可能记住 ——
 *    自然风光=绿、美食=金、历史文化=蓝（沉稳）、购物=紫。
 *    随机配色只是好看，学不到东西。
 * 4. 深色主题单独给一组更亮的文字色与半透明底，否则浅底深字在暗背景上发闷。
 *
 * 未识别的标签一律落到 slate 中性色 —— **不抛异常、不显示成未定义样式**，
 * 因为 preferences 是模型产出的，将来一定会出现新标签。
 */

/** 主题 → 语义色标识 */
const PREFERENCE_TONES: Record<string, PreferenceTone> = {
  // 历史文化：蓝。沉稳、有分量，与「古都/博物馆」的气质一致
  历史文化: 'history',
  历史: 'history',
  文化: 'history',
  古迹: 'history',
  人文: 'history',
  博物馆: 'history',
  // 自然风光：绿。最直观的联想
  自然风光: 'nature',
  自然: 'nature',
  风光: 'nature',
  户外: 'nature',
  徒步: 'nature',
  山水: 'nature',
  海岛: 'nature',
  海滩: 'nature',
  // 美食：金。暖色，与「吃」的联想最接近
  美食: 'food',
  小吃: 'food',
  探店: 'food',
  美食探店: 'food',
  // 购物：紫
  购物: 'shopping',
  逛街: 'shopping',
  市集: 'shopping',
  // 休闲 / 亲子 / 摄影等：青（避免与蓝色的历史撞色）
  休闲: 'leisure',
  放松: 'leisure',
  度假: 'leisure',
  亲子: 'leisure',
  摄影: 'leisure',
  夜景: 'leisure',
  夜生活: 'leisure',
  慢节奏: 'leisure'
}

export type PreferenceTone =
  | 'history'
  | 'nature'
  | 'food'
  | 'shopping'
  | 'leisure'
  | 'plain'

/** 取标签对应的语义色标识；未识别的返回 plain（中性） */
export function preferenceTone(label: string): PreferenceTone {
  const key = (label ?? '').trim()
  if (!key) return 'plain'
  if (PREFERENCE_TONES[key]) return PREFERENCE_TONES[key]
  // 兜底：标签可能带后缀（如「美食之旅」），做一次包含匹配
  for (const [word, tone] of Object.entries(PREFERENCE_TONES)) {
    if (key.includes(word)) return tone
  }
  return 'plain'
}
