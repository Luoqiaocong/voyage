import type { ChatMessage } from '@/api/conversation'
import type { ToolStep } from '@/types/tool'

/** 会话消息：assistant 消息可携带本轮的工具调用与思考过程 */
export interface RdMsg extends ChatMessage {
  tools?: ToolStep[]
  reasoning?: string
}
