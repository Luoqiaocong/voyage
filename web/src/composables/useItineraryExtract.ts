import { computed, ref, type Ref } from 'vue'
import type { Router } from 'vue-router'
import { extractItinerary, getItineraryByConversation } from '@/api/itinerary'
import { useUiStore } from '@/stores/ui'
import type { RdMsg } from '@/types/message'

/**
 * 「把当前会话的历史总结成行程」这条链路的逻辑。
 *
 * 从 ChatView 抽出来，原因：它自成一段（判断条件 + 二次确认 + 调用提取 +
 * 结果引导），依赖的只有 messages / activeId / streaming / router，
 * 放在视图里会把其余逻辑挤在一起。
 */
export function useItineraryExtract(options: {
  messages: Ref<RdMsg[]>
  activeId: Ref<string | null>
  streaming: Ref<boolean>
  router: Router
}) {
  const { messages, activeId, streaming, router } = options
  const ui = useUiStore()

  /** 是否正在提取（按钮置灰与文案切换都看它） */
  const extracting = ref(false)

  /**
   * 判断当前会话里是否已有 AI 回复（提取按钮的可用条件）。
   *
   * 提取范围是整个会话：后端读取整段对话历史（含用户提出的目的地、天数、
   * 预算等约束），由 AI 总结后整理成行程；前端只负责判断「有没有内容可提取」，
   * 不需要也不能指定某条消息。
   */
  function lastAiMessage(): RdMsg | null {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i]
      if (m.role === 'assistant' && typeof m.content === 'string' && m.content.trim()) {
        return m
      }
    }
    return null
  }

  /**
   * 对话轮数（一问一答算一轮）。
   *
   * 用助手回复条数而非用户消息条数：用户可能连发几条才得到一次回答，
   * 按用户消息数会高估进度。
   */
  const rounds = computed(
    () =>
      messages.value.filter(
        (m) => m.role === 'assistant' && typeof m.content === 'string' && m.content.trim()
      ).length
  )

  /**
   * 是否具备提取条件（存在 AI 回复）。
   *
   * 只判断「有没有可提取的文本」，不判断「像不像行程」——
   * 内容预判已被证明两个方向都会出错（见 handleExtract 里的说明），
   * 真正的判定器在后端。这里仅用于把按钮置灰并给出提示，
   * 让用户在点之前就知道为什么不能点。
   */
  const canExtract = computed(() => lastAiMessage() !== null)

  async function handleExtract() {
    if (!activeId.value || streaming.value || extracting.value) return

    const target = lastAiMessage()
    if (!target) {
      ui.toast('这个会话里还没有 AI 回复，无法提取', 'error')
      return
    }

    let overwrite = false
    try {
      const existing = await getItineraryByConversation(activeId.value)
      if (existing) {
        const dest = existing.plan.destination || '未命名'
        const choice = await ui.confirmChoices(
          `该会话已有行程「${dest}」（${existing.plan.days} 天）。voyage 将总结会话历史再提取，请选择覆盖或另存。`,
          [
            { label: '覆盖原行程', value: 'overwrite', kind: 'primary' },
            { label: '另存一份', value: 'copy', kind: 'ghost' },
            { label: '取消', value: 'cancel', kind: 'ghost' }
          ]
        )
        if (!choice || choice === 'cancel') return
        overwrite = choice === 'overwrite'
      } else {
        const sure = await ui.confirm('voyage将总结会话历史以提取合适的行程，是否继续？')
        if (!sure) return
      }
    } catch {
      const sure = await ui.confirm('voyage将总结会话历史以提取合适的行程，是否继续？')
      if (!sure) return
    }

    extracting.value = true
    ui.toast('正在后台总结会话并生成行程，稍后可在「我的行程」查看', 'info', 4200)
    try {
      const it = await extractItinerary(activeId.value, overwrite)
      const go = await ui.confirmChoices(
        `行程已生成：${it.plan.destination}（${it.plan.days} 天）。可稍后在行程页查看，也可以现在前往。`,
        [
          { label: '前往行程', value: 'go', kind: 'primary' },
          { label: '留在对话', value: 'stay', kind: 'ghost' }
        ]
      )
      if (go === 'go') router.push(`/itineraries/${it.id}`)
    } catch (e: any) {
      ui.toast(e?.message ?? '行程提取失败，请确认对话中包含完整的行程安排', 'error')
    } finally {
      extracting.value = false
    }
  }

  return { extracting, rounds, canExtract, handleExtract }
}
