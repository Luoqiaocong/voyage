/**
 * 语音输入：把浏览器识别出的文本填进输入框。
 *
 * 用浏览器原生的 Web Speech API，不引第三方 SDK。
 *
 * 取舍说明：
 *   - 好处是零依赖、零成本、无需后端配合（识别在浏览器/系统侧完成）；
 *   - 代价是**只有 Chrome/Edge/Safari 支持**，Firefox 至今没有。
 *     故做能力检测：不支持时按钮不渲染，而不是给一个点了没反应的按钮。
 *   - 中文识别依赖系统语言包，桌面端偶有不准；所以识别结果**只回调给调用方**，
 *     由调用方决定是否填入输入框、是否提交 —— 首页选择先填空让用户改错字。
 *
 * 组件卸载时自动停止识别，避免离开页面后麦克风仍在监听。
 */
import { computed, onUnmounted, ref } from 'vue'

/** 只声明用到的部分，避免为第三方类型引入额外依赖 */
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  onresult: ((e: any) => void) | null
  onerror: ((e: any) => void) | null
  onend: (() => void) | null
}

/**
 * @param onTranscript 每收到一段识别结果时调用，参数为去空白后的文本。
 */
export function useVoiceInput(onTranscript: (text: string) => void) {
  const listening = ref(false)
  const error = ref('')

  /** 浏览器是否支持语音识别 */
  const supported = computed(() => {
    if (typeof window === 'undefined') return false
    const w = window as any
    return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition)
  })

  let recognition: SpeechRecognitionLike | null = null

  function toggle() {
    if (listening.value) {
      recognition?.stop()
      return
    }
    error.value = ''
    const w = window as any
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition
    if (!Ctor) return

    const rec: SpeechRecognitionLike = new Ctor()
    rec.lang = 'zh-CN'
    // 不设 continuous：一次说完一句就结束，比持续监听更符合「填一句话」的场景，
    // 也让用户清楚它什么时候停止（持续监听容易被误以为一直在录音）
    rec.continuous = false
    rec.interimResults = true

    rec.onresult = (e: any) => {
      let text = ''
      for (let i = 0; i < e.results.length; i++) {
        text += e.results[i][0].transcript
      }
      // 只回调不提交：允许调用方先让用户改掉识别错的字
      onTranscript(text.trim())
    }
    rec.onerror = (e: any) => {
      const code = e?.error ?? ''
      error.value =
        code === 'not-allowed' || code === 'service-not-allowed'
          ? '浏览器拒绝了麦克风权限，请在地址栏左侧允许后重试'
          : code === 'no-speech'
            ? '没有听到声音，请再说一次'
            : '语音识别失败，请改用键盘输入'
      listening.value = false
    }
    rec.onend = () => {
      listening.value = false
      recognition = null
    }

    try {
      rec.start()
      recognition = rec
      listening.value = true
    } catch {
      error.value = '无法启动语音识别，请改用键盘输入'
    }
  }

  onUnmounted(() => {
    recognition?.stop()
    recognition = null
  })

  return { listening, error, supported, toggle }
}
