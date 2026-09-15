/** 工具调用的类型定义（放在 .ts 中，便于组件与 API 层共享） */

export interface ToolStep {
  /** 稳定 key */
  id: string
  /** 工具技术名，如 get_weather */
  name: string
  /** 中文展示名，如「查询天气」 */
  label: string
  /** 图标类型：weather / train / itinerary / date / generic */
  icon: string
  status: 'running' | 'done' | 'error'
  /** 结果摘要（单行，已压缩） */
  result?: string
  /** 耗时（毫秒），可选 */
  duration?: number
}
