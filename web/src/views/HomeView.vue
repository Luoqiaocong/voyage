<script setup lang="ts">
/**
 * HomeView · 官网首页
 *
 * 设计概念：**把行程单本身当作主视觉**。
 *
 * 多数旅行/AI 产品靠抽象图形（地图纹理、光晕、渐变曲线）营造氛围，
 * 再用一排平均用力的功能卡片介绍能力。但用户真正想看的是
 * 「这东西生成出来长什么样」。所以这里反过来：直接渲染一份真实的行程单，
 * 让它逐条构建出来，把「生成过程」当作英雄元素。
 *
 * 信息架构：
 *   1. Hero      可输入的规划框 + 正在生成的行程单（左「说」右「得」）
 *   2. 示例行程   3 座城市，先让用户看到完整结果
 *   3. 三个场景   对话片段 → 结果卡片，替代原来 6 张平均卡片
 *   4. 三步流程   大数字时间线 + 随步骤切换的实时预览
 *   5. 收尾 CTA   仪式感
 *
 * 动效原则：一次性编排（整页入场 → 行程逐条构建），不做无意义循环动画。
 * 全部尊重 prefers-reduced-motion。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useRotatingPlaceholder, useTypewriter } from '@/composables/useTypewriter'
import AppNavbar from '@/components/AppNavbar.vue'
import AppFooter from '@/components/AppFooter.vue'
import BackToTop from '@/components/BackToTop.vue'
import TravelIcon from '@/components/TravelIcon.vue'

const user = useUserStore()
const router = useRouter()

/* ==================== 0. Hero 打字机动效 ==================== */
/*
 * 三项动效的节奏是**依次接续**的，不是同时开始：
 *   主标题（约 1.3s）→ 副标题（约 1.2s）→ 输入框占位轮换（持续）
 * 同时开始会让人不知道看哪里；接续出现则形成一条自然的阅读动线。
 */
const HERO_TITLE_DELAY = 180
const HERO_SUB_DELAY = 1500

/**
 * 主标题分段。用「段」而不是整串字符索引，是因为标题里有换行与高亮词，
 * 逐段推进可以保留这些结构；段内再逐字。
 *
 * 分成两行（与改版前一致）：
 *   一句话，
 *   生成可执行的旅行日程
 * 换行由第 0 段的 `br: true` 表达，而不是段索引判断 —— 这样调整文案时
 * 换行位置跟着数据走，不会因为插了一段就跑到别处。
 */
const heroTitleSegments: { text: string; em?: boolean; br?: boolean }[] = [
  { text: '一句话，', br: true },
  { text: '生成' },
  { text: '可执行', em: true },
  { text: '的旅行日程' },
]
const heroTitleTotal = heroTitleSegments.reduce((n, s) => n + s.text.length, 0)
/** 读屏器用的完整标题（不逐字朗读，也不漏掉尚未「打出」的部分） */
const HERO_TITLE_PLAIN = heroTitleSegments.map((s) => s.text).join('')
/** 各段起点的全局字符偏移，用于把「已输入字数」映射到段落内的位置 */
const heroTitleOffsets = heroTitleSegments.reduce<number[]>((acc, _seg, i) => {
  acc.push(i === 0 ? 0 : acc[i - 1] + heroTitleSegments[i - 1].text.length)
  return acc
}, [])

const heroTitleTyped = useTypewriter(
  'x'.repeat(heroTitleTotal), // 只借用它的计数与节流，文本内容由分段决定
  { charMs: 62, startDelayMs: HERO_TITLE_DELAY }
)

/** 每段已显示的字符数（0..段长） */
function segTyped(index: number): number {
  const start = heroTitleOffsets[index]
  return Math.max(0, Math.min(heroTitleTyped.count.value - start, heroTitleSegments[index].text.length))
}

/**
 * 副标题：纯文本，直接用「已输入字数」切分。
 * 模板渲染完整文本 + 隐藏未输入部分，保证高度从第一帧就是最终值。
 */
const HERO_SUB_TEXT =
  '说出目的地、天数与预算。车次与天气我们实时查好，最后落成一份按天排布、随时可改的行程。'
const heroSubTyped = useTypewriter(HERO_SUB_TEXT, {
  charMs: 26,
  startDelayMs: HERO_SUB_DELAY,
})

/**
 * 输入框的轮换占位文案。
 *
 * 每条都刻意带上不同要素（天数、预算、交通、偏好），让轮换本身
 * 也在示范「可以怎么描述需求」，而不只是视觉噱头。
 */
const PLACEHOLDER_SAMPLES = [
  '广州到北京 3 天，预算 3000，坐高铁',
  '成都周末两日游，帮我看看天气',
  '西安 4 天，想拍古建筑，节奏别太赶',
  '上海出发去大理，5 天，带父母',
  '北京周边 2 天，想爬山',
]
const ph = useRotatingPlaceholder(PLACEHOLDER_SAMPLES, {
  charMs: 88,
  holdMs: 1900,
  eraseMs: 32,
})
/** 输入框是否已聚焦：聚焦后让位给真实光标，不再显示轮换占位 */
const inputFocused = ref(false)
/** 用户已输入或已聚焦时，隐藏轮换占位文案 */
const showPlaceholder = computed(() => draft.value.length === 0 && !inputFocused.value)


/* ==================== 1. Hero：一句话规划 ==================== */
const draft = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

/** 带着这句话进规划页；未登录先去登录，登录后开新会话并自动发送。 */
function submitPlan() {
  const text = draft.value.trim()
  if (user.isLoggedIn) {
    router.push(text ? { path: '/chat', query: { example: text } } : { path: '/chat' })
    return
  }
  router.push(
    text
      ? { path: '/login', query: { example: text, redirect: '/chat' } }
      : { path: '/login', query: { redirect: '/chat' } }
  )
}

/** 想不到问题就点示例，填进输入框并聚焦，用户可再改 */
function usePrompt(text: string) {
  draft.value = text
  inputEl.value?.focus()
}

/* ---------------- 语音输入 ---------------- */
/*
 * 用浏览器原生的 Web Speech API，不引第三方 SDK。
 *
 * 取舍说明：
 *   - 好处是零依赖、零成本、无需后端配合（识别在浏览器/系统侧完成）；
 *   - 代价是**只有 Chrome/Edge/Safari 支持**，Firefox 至今没有。
 *     故做能力检测：不支持时按钮不渲染，而不是给一个点了没反应的按钮。
 *   - 中文识别依赖系统语言包，桌面端偶有不准；所以识别结果**只填入输入框**，
 *     不自动提交 —— 用户可以先改错字再发送。这是有意的，避免「说错一个字
 *     就发出去了」。
 */

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

const voiceListening = ref(false)
const voiceError = ref('')

/** 浏览器是否支持语音识别 */
const voiceSupported = computed(() => {
  if (typeof window === 'undefined') return false
  const w = window as any
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition)
})

let recognition: SpeechRecognitionLike | null = null

function toggleVoice() {
  if (voiceListening.value) {
    recognition?.stop()
    return
  }
  voiceError.value = ''
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
    // 只填充不提交：允许用户改掉识别错的字
    draft.value = text.trim()
  }
  rec.onerror = (e: any) => {
    const code = e?.error ?? ''
    voiceError.value =
      code === 'not-allowed' || code === 'service-not-allowed'
        ? '浏览器拒绝了麦克风权限，请在地址栏左侧允许后重试'
        : code === 'no-speech'
          ? '没有听到声音，请再说一次'
          : '语音识别失败，请改用键盘输入'
    voiceListening.value = false
  }
  rec.onend = () => {
    voiceListening.value = false
    recognition = null
  }

  try {
    rec.start()
    recognition = rec
    voiceListening.value = true
  } catch {
    voiceError.value = '无法启动语音识别，请改用键盘输入'
  }
}

const prompts = [
  '广州 → 北京 3 天，预算 3000',
  '成都周末两日游，帮我看看天气',
  '西安 4 天，想拍古建筑'
]

/* ==================== 2. 示例行程（结果优先） ==================== */
/** 时段：示例区的行程与 Hero 的时段标签共用 */
type Slot = 'morning' | 'afternoon' | 'evening'

const SLOT_META: Record<Slot, { label: string; icon: string }> = {
  morning: { label: '上午', icon: 'sun' },
  afternoon: { label: '下午', icon: 'camera' },
  evening: { label: '晚上', icon: 'moon' }
}

interface DemoActivity {
  slot: Slot
  name: string
  desc: string
  cost: string
}
interface DemoDay {
  theme: string
  date: string
  summary: string
  acts: DemoActivity[]
}
interface Demo {
  city: string
  tag: string
  days: number
  budget: string
  plan: DemoDay[]
}

const demos: Demo[] = [
  {
    city: '北京',
    tag: '文化古都',
    days: 3,
    budget: '¥2800',
    plan: [
      {
        theme: '城市初探',
        date: '10-01',
        summary: '天安门、胡同与小吃',
        acts: [
          { slot: 'morning', name: '天安门广场 · 故宫', desc: '门票 60 元，需提前预约，游览约 4 小时', cost: '¥60' },
          { slot: 'afternoon', name: '南锣鼓巷 · 胡同漫步', desc: '免费，感受老北京胡同文化', cost: '免费' },
          { slot: 'evening', name: '王府井小吃街', desc: '人均 80 元，推荐卤煮与炸酱面', cost: '¥80' }
        ]
      },
      {
        theme: '长城壮阔',
        date: '10-02',
        summary: '八达岭与奥体之夜',
        acts: [
          { slot: 'morning', name: '八达岭长城', desc: '门票 40 元，建议早出发避开人流', cost: '¥40' },
          { slot: 'afternoon', name: '鸟巢 · 水立方外观', desc: '免费外观，拍照打卡', cost: '免费' },
          { slot: 'evening', name: '簋街夜市', desc: '人均 100 元，麻辣小龙虾', cost: '¥100' }
        ]
      },
      {
        theme: '皇家园林',
        date: '10-03',
        summary: '颐和园与前门收官',
        acts: [
          { slot: 'morning', name: '颐和园', desc: '门票 30 元，游昆明湖', cost: '¥30' },
          { slot: 'afternoon', name: '圆明园遗址', desc: '门票 25 元，历史参观', cost: '¥25' },
          { slot: 'evening', name: '前门大街', desc: '免费，夜景与老字号', cost: '免费' }
        ]
      }
    ]
  },
  {
    city: '成都',
    tag: '慢生活',
    days: 3,
    budget: '¥2200',
    plan: [
      {
        theme: '熊猫与锦里',
        date: '10-01',
        summary: '熊猫基地与古街火锅',
        acts: [
          { slot: 'morning', name: '大熊猫繁育研究基地', desc: '门票 55 元，建议 8 点前到', cost: '¥55' },
          { slot: 'afternoon', name: '宽窄巷子', desc: '免费，成都城市名片', cost: '免费' },
          { slot: 'evening', name: '锦里古街 · 火锅', desc: '人均 120 元，地道牛油火锅', cost: '¥120' }
        ]
      },
      {
        theme: '文化漫游',
        date: '10-02',
        summary: '武侯祠与鹤鸣茶社',
        acts: [
          { slot: 'morning', name: '武侯祠', desc: '门票 50 元，三国文化', cost: '¥50' },
          { slot: 'afternoon', name: '人民公园 · 鹤鸣茶社', desc: '一杯盖碗茶，体验慢生活', cost: '¥40' },
          { slot: 'evening', name: '玉林路小酒馆', desc: '人均 60 元，市井夜生活', cost: '¥60' }
        ]
      },
      {
        theme: '自然与街区',
        date: '10-03',
        summary: '青城山与建设路',
        acts: [
          { slot: 'morning', name: '青城山（前山）', desc: '门票 80 元，道教名山', cost: '¥80' },
          { slot: 'afternoon', name: '都江堰景区', desc: '门票 80 元，世界文化遗产', cost: '¥80' },
          { slot: 'evening', name: '建设路小吃街', desc: '人均 50 元，甜水面与兔头', cost: '¥50' }
        ]
      }
    ]
  },
  {
    city: '上海',
    tag: '都市摩登',
    days: 2,
    budget: '¥1800',
    plan: [
      {
        theme: '外滩与天际线',
        date: '10-01',
        summary: '万国建筑与陆家嘴夜景',
        acts: [
          { slot: 'morning', name: '外滩万国建筑群', desc: '免费，欣赏百年建筑', cost: '免费' },
          { slot: 'afternoon', name: '南京东路步行街', desc: '免费，购物与老字号', cost: '免费' },
          { slot: 'evening', name: '陆家嘴 · 三件套夜景', desc: '登中心可选 180 元', cost: '¥180' }
        ]
      },
      {
        theme: '文艺漫步',
        date: '10-02',
        summary: '武康路与黄浦江游船',
        acts: [
          { slot: 'morning', name: '武康路 · 老洋房', desc: '免费，梧桐街道', cost: '免费' },
          { slot: 'afternoon', name: '田子坊', desc: '免费，弄堂创意街区', cost: '免费' },
          { slot: 'evening', name: '黄浦江游船', desc: '船票 120 元，两岸夜景', cost: '¥120' }
        ]
      }
    ]
  }
]

const demoIdx = ref(0)
const activeDemo = computed(() => demos[demoIdx.value])

/* ==================== 3. 三个场景 ==================== */
interface Scenario {
  key: string
  eyebrow: string
  title: string
  value: string
  ask: string
  reply: string
  resultTitle: string
  rows: { k: string; v: string; tone?: 'ok' | 'warn' }[]
}

const scenarios: Scenario[] = [
  {
    key: 'weather',
    eyebrow: '出行前',
    title: '天气不只告知，还替你改安排',
    value: '按天气给出穿着建议，并把户外项目挪到合适的时段。',
    ask: '成都这周末穿什么？行程要改吗',
    reply: '查到周六有阵雨，已把青城山挪到周日，周六换成室内的川博。',
    resultTitle: '调整后的周末',
    rows: [
      { k: '周六', v: '阵雨 18~24°C · 四川博物院 + 太古里', tone: 'warn' },
      { k: '周日', v: '多云 17~26°C · 青城山（前山）', tone: 'ok' },
      { k: '携带', v: '折叠伞、薄外套' }
    ]
  },
  {
    key: 'ticket',
    eyebrow: '定交通',
    title: '车次、票价、余票，一次问清',
    value: '数据来自实时车次接口，不是模型推测出来的数字。',
    ask: '明天广州南到北京西的高铁',
    reply: '按早班优先列出 4 趟，二等座余票充足。',
    resultTitle: '可选车次',
    rows: [
      { k: 'G77', v: '08:00 → 13:24 · 二等座 ¥553', tone: 'ok' },
      { k: 'G79', v: '10:05 → 15:38 · 二等座 ¥553' },
      { k: 'G81', v: '13:20 → 19:02 · 二等座 ¥553' },
      { k: '历时', v: '约 5 小时 24 分' }
    ]
  },
  {
    key: 'extract',
    eyebrow: '成稿后',
    title: '聊完的攻略，一键变成可编辑行程',
    value: '按天与时段整理成结构化行程，之后随时增删改。',
    ask: '把刚才这份攻略存下来',
    reply: '已提取为 3 天行程，含 9 个活动与预算。',
    resultTitle: '已保存的行程',
    rows: [
      { k: 'Day 1', v: '故宫 · 南锣鼓巷 · 王府井' },
      { k: 'Day 2', v: '八达岭长城 · 奥体 · 簋街' },
      { k: 'Day 3', v: '颐和园 · 圆明园 · 前门' },
      { k: '状态', v: '可编辑、可分享、可导出日历', tone: 'ok' }
    ]
  }
]

/* ==================== 4. 三步流程 ==================== */
const steps = [
  {
    no: '01',
    title: '说出你的旅行',
    desc: '一句话就行。目的地、天数、预算说到哪算哪，不用整理格式。'
  },
  {
    no: '02',
    title: '数据我来核对',
    desc: '车次、天气、住宿在后台实时查询，不是模型编出来的数字。'
  },
  {
    no: '03',
    title: '行程落地成稿',
    desc: '按天按时段排好，随时增删改，也能分享给同行的人。'
  }
]

const activeStep = ref(0)
let stepTimer: number | null = null

function pickStep(i: number) {
  activeStep.value = i
  stopStepTimer()
}

function stopStepTimer() {
  if (stepTimer !== null) {
    window.clearInterval(stepTimer)
    stepTimer = null
  }
}

/* ==================== 入场与滚动揭示 ==================== */
const entered = ref(false)

/*
 * ==================== 首屏展开闸门 ====================
 *
 * 首页初始**只呈现 Hero**：一句话输入框。下方的示例行程、场景、三步流程、
 * 收尾 CTA 默认不渲染，由用户点击引导按钮或向下滚动/上滑后展开。
 *
 * 为什么默认收起：Hero 已经完整表达了「说一句话 → 得到行程」这件事，
 * 首屏直接铺开四屏内容反而稀释了唯一的行动点（输入框）。
 * 收起后首屏只有一个焦点，用户要么输入、要么展开看细节。
 *
 * 触发方式同时支持三种，覆盖桌面与移动端：
 *   · 点击/回车引导按钮（主要入口，键盘可达）
 *   · 桌面：鼠标滚轮向下
 *   · 移动端：触摸上滑
 * 后两者是「用户已经在尝试往下看」的强信号，此时立刻展开，
 * 避免出现「滚不动」的困惑。
 */
const revealed = ref(false)
/** 用于 aria-controls 指向的容器 id */
const REVEAL_ID = 'home-more'

/*
 * 展开后把「引导件」滚到导航栏正下方。
 *
 * ## 目标位置怎么定
 *
 * 不依赖任何元素引用，而是先算出引导件在文档里的绝对纵坐标，再减去
 * 导航栏高度与一点呼吸空间。这样得到的滚动目标在滚动过程中**不会变**，
 * 不会出现「滚到一半目标跑了」的情况。
 *
 * ## 为什么不用 scrollIntoView
 *
 * 试过 `block: 'start'` 与 `'nearest'`，问题在于它对齐的是**容器顶端**，
 * 而容器（可展开区）顶部有一段内边距，紧贴其上的引导件因此被推到
 * 视口顶边之外 —— 这正是「一份可执行的行程被遮挡了，箭头也没完全显现」
 * 的成因。手动算位置能精确控制落点，让它停在导航栏下方。
 *
 * ## 关于滚动动画
 *
 * 不传 `behavior`，由全局 `html { scroll-behavior: smooth }` 决定
 * （用户在系统里开启「减弱动效」时，全局会切换为 auto，浏览器自动
 * 改为瞬时跳转，无需在此判断）。
 */
function scrollGuideIntoView() {
  if (typeof document === 'undefined') return
  const guide = document.querySelector<HTMLElement>('.join-arrow')
  if (!guide) return

  const nav = document.querySelector<HTMLElement>('.nav')
  const navH = nav?.getBoundingClientRect().height ?? 64
  const BREATH = 24 // 引导件与导航栏之间的呼吸空间

  const docTop = guide.getBoundingClientRect().top + window.scrollY
  const targetY = Math.max(docTop - navH - BREATH, 0)
  window.scrollTo(0, targetY)
}

/**
 * 展开后的滚动入口。
 *
 * **必须等布局稳定再滚**：内容刚由 display:none 变为可见时，`.rv` 元素
 * 还停在 opacity:0 并带 20px 位移，各区块高度尚未定型 —— 此时算出的
 * 目标位置是错的（实测那样滚几乎不生效）。
 * 故等两帧（一帧移除 display、一帧完成布局）再加一小段延时，
 * 让入场过渡走过大部分位移后再计算并滚动。
 */
function scrollToContent() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      window.setTimeout(scrollGuideIntoView, 120)
    })
  })
}

function reveal(andScroll = false) {
  if (revealed.value) return
  revealed.value = true
  if (andScroll) {
    // 等 v-show 把内容渲染出来再滚，否则目标元素高度还是 0
    void nextTick(() => scrollToContent())
  }
}

function collapse() {
  revealed.value = false
  /*
   * 回顶部。同样不传 behavior —— 由全局 scroll-behavior 决定。
   * 收起后页面总高骤降、浏览器会自行纠正滚动位置，回顶部最可预期：
   * 收起后的首屏就是 Hero，本来就该在顶部。
   */
  window.scrollTo(0, 0)
}

function toggleReveal() {
  if (revealed.value) collapse()
  else reveal(true)
}

/* ---------------- 滚动 / 触摸意图 ---------------- */
let wheelAcc = 0
let touchStartY: number | null = null

function onWheelIntent(e: WheelEvent) {
  if (revealed.value) return
  // 只认「向下滚」。阈值避免触控板轻微误触就展开
  if (e.deltaY <= 0) {
    wheelAcc = 0
    return
  }
  wheelAcc += e.deltaY
  if (wheelAcc >= 24) {
    // 收起状态下没有可滚动内容，阻止默认行为避免用户以为页面卡住
    e.preventDefault()
    reveal(true)
  }
}

function onTouchStartIntent(e: TouchEvent) {
  if (revealed.value) return
  touchStartY = e.touches[0]?.clientY ?? null
}

function onTouchMoveIntent(e: TouchEvent) {
  if (revealed.value || touchStartY === null) return
  const y = e.touches[0]?.clientY
  if (y === undefined) return
  // 手指上滑（y 变小）表示想看下面的内容
  if (touchStartY - y >= 28) {
    e.preventDefault()
    touchStartY = null
    reveal(true)
  }
}

let revealTimer: number | null = null
let io: IntersectionObserver | null = null

/*
 * 入场揭示：为所有 .rv 元素注册 IntersectionObserver。
 *
 * ⚠️ 必须在**展开之后重新调用一次**，不能在 onMounted 里只做一次：
 * 收起状态下内容容器是 display:none，被它包裹的元素**没有布局盒**，
 * IntersectionObserver 永远不会判定它们相交，`.in` 类加不上，
 * 展开后它们会一直停在 opacity:0 —— 表现为「下面一片空白」。
 *
 * 幂等：已加过 .in 的元素再次 observe 也无副作用（回调里会 unobserve）。
 */
let rvBound = false

function bindRevealObserver() {
  // 滚动揭示只在展开后才需要：收起时下方内容不可见，注册了也不会触发
  if (!revealed.value) return
  if (rvBound) return
  rvBound = true

  if (typeof IntersectionObserver === 'undefined') {
    // 环境不支持时直接显示，绝不因为动画而让内容不可见
    document.querySelectorAll('.rv').forEach((el) => el.classList.add('in'))
    return
  }
  io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add('in')
          io?.unobserve(e.target)
        }
      }
    },
    { threshold: 0.12 }
  )
  document.querySelectorAll('.rv').forEach((el) => io?.observe(el))
}

onMounted(() => {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

  // 展开闸门的触发器。passive:false 是必须的：收起状态下本来就没有可滚动
  // 内容，会在处理函数里 preventDefault 以免用户以为页面卡住。
  window.addEventListener('wheel', onWheelIntent, { passive: false })
  window.addEventListener('touchstart', onTouchStartIntent, { passive: true })
  window.addEventListener('touchmove', onTouchMoveIntent, { passive: false })

  if (reduce) {
    entered.value = true
    document.querySelectorAll('.rv').forEach((el) => el.classList.add('in'))
    return
  }

  // 等两帧再置位，确保过渡有起点可播
  revealTimer = window.setTimeout(() => {
    entered.value = true
  }, 60)
})

/*
 * 展开后：注册揭示观察器 + 启动步骤轮播。
 *
 * 用 watch 而不是写在点击处理函数里：滚轮/触摸也能触发展开，
 * 若只在点击里做，另外两条路径展开后内容同样会隐形。
 * 统一在这里处理，三条路径行为一致。
 */
watch(revealed, async (open) => {
  if (!open) {
    stopStepTimer()
    return
  }
  // 等两帧：一帧让 v-show 移除 display:none，再一帧让浏览器完成布局，
  // 这样 IntersectionObserver 才能基于真实位置判定
  await nextTick()
  requestAnimationFrame(() => {
    bindRevealObserver()
  })
  // 步骤轮播只在可见时才转，收起状态不再空转
  if (stepTimer === null) {
    stepTimer = window.setInterval(() => {
      activeStep.value = (activeStep.value + 1) % steps.length
    }, 3600)
  }
})

onUnmounted(() => {
  io?.disconnect()
  io = null
  stopStepTimer()
  if (revealTimer !== null) window.clearTimeout(revealTimer)
  window.removeEventListener('wheel', onWheelIntent)
  window.removeEventListener('touchstart', onTouchStartIntent)
  window.removeEventListener('touchmove', onTouchMoveIntent)
  /*
   * 离开首页时若语音识别仍在进行，必须停掉。
   * 不停的话麦克风会一直被占用（浏览器标签上持续显示录音中），
   * 用户会以为程序在偷听；重新进入首页再点也无法重新 start。
   */
  recognition?.stop()
  recognition = null
})

</script>

<template>
  <AppNavbar />

  <main
    id="main"
    tabindex="-1"
    class="home"
    :class="{ 'home--in': entered, 'home--collapsed': !revealed }"
  >
    <!-- ============================================================
         1. HERO：一句话描述需求 → 开始规划
         单栏居中：原先右侧还有一张「它替我查了什么」示意卡（车次/天气/预算），
         与下方「生成结果」区内容重复度高，已删除（详见 .hero__inner 的样式注释）
         ============================================================ -->
    <section class="hero">
      <div class="hero__aura" aria-hidden="true"></div>

      <div class="container hero__inner">
        <div class="hero__say">
          <p class="hero__kicker">
            <span class="dot"></span>
            多 Agent 协作 · 实时数据核对
          </p>

          <!--
            主标题：逐字出现（打字机）。
            每一段都是「已输入部分 + 未输入部分」，未输入部分用 .tw-hide 隐藏
            **但仍然占位** —— 这样标题的宽高从第一帧起就是最终值，
            不会边打字边把下方内容往下推。
            aria-label 给出完整标题：读屏器不该逐字朗读，也不该漏掉隐藏部分。
          -->
          <h1 class="hero__title" :aria-label="HERO_TITLE_PLAIN">
            <span aria-hidden="true">
              <span v-for="(seg, si) in heroTitleSegments" :key="si">
                <span
                  v-if="seg.em"
                  class="hero__title-em"
                ><span>{{ seg.text.slice(0, segTyped(si)) }}</span><span class="tw-hide">{{ seg.text.slice(segTyped(si)) }}</span></span>
                <template v-else><span>{{ seg.text.slice(0, segTyped(si)) }}</span><span class="tw-hide">{{ seg.text.slice(segTyped(si)) }}</span></template>
                <!-- 段数据里标记 br 的位置之后换行，还原原来的两行标题 -->
                <br v-if="seg.br" />
              </span>
            </span>
          </h1>

          <!-- 副标题：同样逐字，在主标题之后开始 -->
          <p class="hero__sub">
            <span aria-hidden="true">{{ HERO_SUB_TEXT.slice(0, heroSubTyped.count.value) }}<span class="tw-hide">{{ HERO_SUB_TEXT.slice(heroSubTyped.count.value) }}</span></span>
            <span class="sr-only">{{ HERO_SUB_TEXT }}</span>
          </p>

          <!-- 可直接输入：这是 Hero 的主操作，不是装饰 -->
          <form class="ask" @submit.prevent="submitPlan">
            <span class="ask__icon" aria-hidden="true">
              <TravelIcon name="compass" :size="18" />
            </span>
            <!--
              输入框本体。刻意**不用原生 placeholder**：
              原生 placeholder 无法做逐字动画，而这里要的是「像有人在打字」
              的效果。改为在输入框上方叠一层等宽文本，用户一聚焦就隐藏，
              真实光标立刻接手，不会与动画光标打架。
            -->
            <span class="ask__field">
              <input
                ref="inputEl"
                v-model="draft"
                class="ask__input"
                type="text"
                aria-label="描述你的旅行计划"
                @focus="inputFocused = true"
                @blur="inputFocused = false"
              />
              <!--
                闪烁光标只在**轮换生效时**渲染。
                reduce-motion 下占位不做动画（直接显示第一条），
                此时若还留着光标闪烁，会暗示「正在打字」却始终不动，观感矛盾。
              -->
              <span v-if="showPlaceholder" class="ask__ph" aria-hidden="true">
                <span class="ask__ph-text">{{ ph.text.value }}</span>
                <span v-if="ph.caretVisible.value" class="ask__ph-caret"></span>
              </span>
            </span>
            <!--
              语音输入：只在浏览器支持时才渲染。
              移动端用户「说话」比打字自然得多，这是主要动机。
              不支持时按钮根本不出现，而不是点了没反应的死按钮。
            -->
            <button
              v-if="voiceSupported"
              type="button"
              class="ask__mic"
              :class="{ 'is-listening': voiceListening }"
              :aria-label="voiceListening ? '停止语音输入' : '用语音描述你的旅行计划'"
              :title="voiceListening ? '正在听…点击停止' : '语音输入'"
              @click="toggleVoice"
            >
              <TravelIcon name="wave" :size="17" />
            </button>
            <button class="ask__go" type="submit">
              开始规划
              <TravelIcon name="arrow-right" :size="16" />
            </button>
          </form>
          <!-- 语音识别失败/被拒时的原因，避免用户以为按钮坏了 -->
          <p v-if="voiceError" class="ask__voice-err">{{ voiceError }}</p>

          <div class="prompts">
            <span class="prompts__label">或试试</span>
            <button
              v-for="p in prompts"
              :key="p"
              type="button"
              class="prompt"
              @click="usePrompt(p)"
            >
              {{ p }}
            </button>
          </div>

          <!--
            展开闸门的触发器：一条短竖线 + 带文字的按钮。
            用 button 而非 div：原生支持 Tab 聚焦与回车/空格触发，
            无需手写 tabindex + keydown；也自带读屏器语义。
            aria-expanded / aria-controls 表明它控制着下方的可展开区域。
            向下滑动或滚轮同样能展开（见脚本里的滚动意图处理）。
          -->
          <button
            type="button"
            class="hero__handoff"
            :aria-expanded="revealed"
            :aria-controls="REVEAL_ID"
            @click="toggleReveal"
          >
            <span class="hero__handoff-line" aria-hidden="true"></span>
            <span class="hero__handoff-label">
              {{ revealed ? '收起' : '看看它生成什么' }}
            </span>
            <TravelIcon
              name="chevron-down"
              :size="16"
              class="hero__handoff-arrow"
              :class="{ 'is-up': revealed }"
            />
          </button>
        </div>
      </div>
    </section>

    <!--
      可展开区：示例行程 / 三个场景 / 三步流程 / 收尾 CTA。

      用 v-show 而不是 v-if：
        · 内容保留在 DOM 中，各区块内部的组件状态（选中的城市、
          当前步骤）在收起再展开后不丢失
        · 展开时无需重新挂载整棵子树，过渡更顺

      inert：收起时让内部元素**完全退出键盘 Tab 序列与读屏器**。
      只加 aria-hidden 是不够的 —— 那样键盘用户仍能 Tab 进看不见的内容。
      Vue 对布尔属性会把 false 移除、true 置为空串，正好符合 inert 的用法。

      id 与触发器的 aria-controls 对应。
    -->
    <div
      v-show="revealed"
      :id="REVEAL_ID"
      :inert="!revealed"
      class="reveal-host"
    >
      <!-- ============================================================
           2. 示例行程

           这一区的定位是「上一区那句话的结果」而不是新章节，
           故刻意做成**延续**而非并置：
             · 与 Hero 的间距从 136px 收到 ~40px（原来是 48+88 两段内边距叠加）
             · 引导件缩成「箭头 + 一行彩色说明」，不再是两行文字
           详见下方 .join-arrow / .section--join 的样式注释。
           ============================================================ -->
      <section class="section section--join">
        <div class="container">
        <!--
          引导件：一根向下的箭头 + 右侧居中的一行说明。
          原先这里是两行文字（引导语 + 标题），信息量偏大，把「这是一段过渡」
          做得像「这是新区块的标题」。缩成箭头 + 一行短句后，它的作用回到
          纯粹的指向：告诉读者下面的内容是从上面那句话来的。
          文字水平方向在箭头右侧、垂直方向与箭头中线对齐，读起来像一句旁注。
        -->
        <div class="join-arrow rv">
          <span class="join-arrow__shaft" aria-hidden="true"></span>
          <span class="join-arrow__tip" aria-hidden="true"></span>
          <p class="join-arrow__text">一份可执行的行程</p>
        </div>

        <div class="tabs rv">
          <button
            v-for="(d, i) in demos"
            :key="d.city"
            type="button"
            class="tab"
            :class="{ 'tab--on': i === demoIdx }"
            @click="demoIdx = i"
          >
            <b>{{ d.city }}</b>
            <i>{{ d.days }} 天 · {{ d.budget }}</i>
          </button>
        </div>

        <div class="showcase rv">
          <!--
            key 里必须带 demoIdx：各城市的日期都是 10-01/10-02/10-03，
            只用 date 作 key 时 Vue 会认为节点没变而复用 DOM，
            切换城市就成了硬切、入场动画也不会重播。
          -->
          <div
            v-for="(d, di) in activeDemo.plan"
            :key="`${demoIdx}-${d.date}`"
            class="daycard"
            :style="{ animationDelay: `${di * 70}ms` }"
          >
            <header class="daycard__head">
              <span class="daycard__no">Day {{ di + 1 }}</span>
              <span class="daycard__date">{{ d.date }}</span>
              <span class="daycard__theme">{{ d.theme }}</span>
            </header>
            <p class="daycard__sum">{{ d.summary }}</p>
            <ul class="acts">
              <li v-for="(a, i) in d.acts" :key="i" class="acts__row">
                <span class="acts__slot" :class="`acts__slot--${a.slot}`">
                  {{ SLOT_META[a.slot].label }}
                </span>
                <span class="acts__body">
                  <b>{{ a.name }}</b>
                  <i>{{ a.desc }}</i>
                </span>
                <span class="acts__cost">{{ a.cost }}</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <!-- ============================================================
         3. 三个场景：对话片段 → 结果卡片
         用具体场景替代「6 张平均卡片」
         ============================================================ -->
    <section class="section section--tint">
      <div class="container">
        <header class="sec-head rv">
          <p class="eyebrow">它到底能做什么</p>
          <h2>三个真实的场景</h2>
          <p>不列功能清单，直接看问题与结果。</p>
        </header>

        <div class="scenes">
          <article v-for="s in scenarios" :key="s.key" class="scene rv">
            <div class="scene__say">
              <p class="scene__eyebrow">{{ s.eyebrow }}</p>
              <h3 class="scene__title">{{ s.title }}</h3>
              <p class="scene__value">{{ s.value }}</p>

              <div class="chat">
                <p class="chat__me">{{ s.ask }}</p>
                <p class="chat__ai">{{ s.reply }}</p>
              </div>
            </div>

            <div class="scene__get">
              <p class="res__title">{{ s.resultTitle }}</p>
              <dl class="res">
                <div v-for="(r, i) in s.rows" :key="i" class="res__row">
                  <dt>{{ r.k }}</dt>
                  <dd :class="r.tone ? `res__v--${r.tone}` : ''">{{ r.v }}</dd>
                </div>
              </dl>
            </div>
          </article>
        </div>
      </div>
    </section>

    <!-- ============================================================
         4. 三步流程：大数字 + 随步骤切换的预览
         ============================================================ -->
    <section class="section">
      <div class="container">
        <header class="sec-head rv">
          <p class="eyebrow">怎么用</p>
          <h2>三步，从想法到可执行</h2>
        </header>

        <div class="steps">
          <ol class="steps__list rv">
            <!--
              用 button 而非可点击的 li：原生支持键盘（Tab 聚焦、回车/空格触发）
              与读屏器，无需手写 tabindex + keydown。li 本身仍由 ol 提供语义。
            -->
            <li v-for="(s, i) in steps" :key="s.no">
              <button
                type="button"
                class="step"
                :class="{ 'step--on': i === activeStep }"
                :aria-current="i === activeStep ? 'step' : undefined"
                @click="pickStep(i)"
              >
                <span class="step__no">{{ s.no }}</span>
                <span class="step__body">
                  <b>{{ s.title }}</b>
                  <i>{{ s.desc }}</i>
                </span>
              </button>
            </li>
          </ol>

          <div class="preview rv">
            <!-- 步骤 1：你说 -->
            <div v-if="activeStep === 0" class="pv">
              <p class="pv__label">你说</p>
              <div class="pv__ask">
                <TravelIcon name="chat" :size="16" />
                <span>帮我规划北京 3 日游，预算 3000，坐高铁</span>
              </div>
              <p class="pv__hint">不用写得工整，地名、天数、预算说到就行</p>
            </div>

            <!-- 步骤 2：我查 -->
            <div v-else-if="activeStep === 1" class="pv">
              <p class="pv__label">我查</p>
              <ul class="check">
                <li>
                  <span class="check__dot"></span>
                  <b>车次</b>
                  <span>G77 二等座 ¥553 · 余票充足</span>
                </li>
                <li>
                  <span class="check__dot"></span>
                  <b>天气</b>
                  <span>北京 3 天晴，12~22°C</span>
                </li>
                <li>
                  <span class="check__dot"></span>
                  <b>住宿</b>
                  <span>市中心两晚，含早 ¥1160</span>
                </li>
              </ul>
              <p class="pv__hint">这些是实时查询结果，不是模型编造的数字</p>
            </div>

            <!-- 步骤 3：成稿 -->
            <div v-else class="pv">
              <p class="pv__label">成稿</p>
              <div class="mini">
                <div class="mini__day">
                  <span>DAY 1</span>
                  <b>城市初探</b>
                  <i>上午 天安门 · 故宫 / 下午 南锣鼓巷</i>
                </div>
                <div class="mini__day">
                  <span>DAY 2</span>
                  <b>长城壮阔</b>
                  <i>上午 八达岭 / 晚上 簋街</i>
                </div>
                <div class="mini__day">
                  <span>DAY 3</span>
                  <b>皇家园林</b>
                  <i>上午 颐和园 / 下午 圆明园</i>
                </div>
              </div>
              <p class="pv__hint">可编辑、可分享，也能导出到手机日历</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ============================================================
         5. 收尾 CTA：仪式感
         ============================================================ -->
    <section class="closing">
      <div class="container">
        <div class="closing__box rv">
          <p class="closing__eyebrow">准备好出发了吗</p>
          <h2 class="closing__title">下一站，交给我们规划</h2>
          <p class="closing__sub">
            说出目的地就行。第一份行程通常在十几秒内生成。
          </p>

          <form class="ask ask--closing" @submit.prevent="submitPlan">
            <span class="ask__icon" aria-hidden="true">
              <TravelIcon name="plane" :size="18" />
            </span>
            <input
              v-model="draft"
              class="ask__input"
              type="text"
              placeholder="你想去哪里？"
              aria-label="输入目的地，开启第一次规划"
            />
            <button class="ask__go" type="submit">
              开启第一次规划
              <TravelIcon name="arrow-right" :size="16" />
            </button>
          </form>

          <!--
            此处原有一个「或用账号登录后再规划」的次要入口，已彻底删除。
            两次反馈叠加的原因：
              1. 已登录用户看到「或用账号登录后再规划」自相矛盾 —— 他已经登录了
              2. 它想表达的「另一种开始方式」已被上方输入框完全覆盖：
                 那个输入框本身就调 startHref()，未登录会去登录页、
                 已登录会带着文案进聊天页，功能重合
            即它是冗余入口而非补充说明，删掉后收尾区更干净。
          -->
        </div>
      </div>
    </section>
    </div>
  </main>

  <AppFooter />

  <!--
    返回顶部。放在 main 之外：它是 fixed 定位的浮层，
    不属于页面内容流，也不该被 .home 的入场动画影响。
    自身按滚动距离决定显隐，无需外部传参。
  -->
  <BackToTop />
</template>

<style scoped>
/* ============================================================
   基础：整页入场 + 滚动揭示
   ============================================================ */
.home {
  position: relative;
  z-index: 1;
  background: var(--bg);
}

.home .hero,
.home .section,
.home .closing {
  opacity: 0;
  transform: translateY(14px);
  transition: opacity 0.65s ease, transform 0.65s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.home--in .hero,
.home--in .section,
.home--in .closing {
  opacity: 1;
  transform: none;
}

.rv {
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.7s cubic-bezier(0.2, 0.7, 0.2, 1),
    transform 0.7s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.rv.in {
  opacity: 1;
  transform: none;
}

@media (prefers-reduced-motion: reduce) {
  .home .hero,
  .home .section,
  .home .closing,
  .rv {
    opacity: 1;
    transform: none;
    transition: none;
  }
}

/* ============================================================
   1. HERO
   ============================================================ */
.hero {
  position: relative;
  padding: 72px 0 48px;
  overflow: hidden;
}

/* 一层极淡的蓝晕：提供纵深，不构成可辨认的图形 */
.hero__aura {
  position: absolute;
  inset: -30% 20% auto -10%;
  height: 720px;
  background: radial-gradient(
    ellipse 60% 55% at 35% 40%,
    rgba(37, 99, 235, 0.13),
    transparent 70%
  );
  pointer-events: none;
}

/*
 * Hero 内容区。
 *
 * 原先这里是两栏：左侧文案 + 右侧「它替我查了什么」示意卡（.hero__get）。
 * 右侧卡片已删除，理由：它展示的高铁车次 / 逐日天气 / 预算构成，
 * 与下方「生成结果」区的内容重复度高，而首页首屏最该做的是让人一眼
 * 看懂「这是什么、能干什么、从哪开始」—— 旁边堆一张信息密度很高的
 * 示意卡反而分散注意力，也把主操作按钮挤到了左半边。
 *
 * 改为单栏居中：文案与输入框成为唯一的视觉焦点，视线自然落在
 * 「说出你的需求」这个主操作上。
 */
.hero__inner {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  max-width: 760px;
  margin: 0 auto;
}

/* ---------- 说 ---------- */
.hero__kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.78rem;
  color: var(--text2);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 14px;
  box-shadow: var(--shadow-sm);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 3px rgba(72, 187, 120, 0.16);
}

.hero__title {
  margin-top: 22px;
  font-size: clamp(2.3rem, 4.6vw, 3.5rem);
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.035em;
}
.hero__title-em {
  position: relative;
  color: var(--prim);
}
/* 重点词下的柔和下划线：比渐变文字克制，也不影响可读性 */
.hero__title-em::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0.06em;
  height: 0.15em;
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.24), rgba(14, 165, 233, 0.08));
  border-radius: 3px;
  z-index: -1;
}

.hero__sub {
  margin-top: 20px;
  max-width: 32em;
  font-size: 1.05rem;
  line-height: 1.72;
  color: var(--text2);
}

/* ---------- 规划输入框（Hero 的主操作） ---------- */
.ask {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 30px;
  padding: 8px 8px 8px 16px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 14px 34px rgba(16, 24, 40, 0.08);
  transition: border-color 0.22s, box-shadow 0.22s;
}
.ask:focus-within {
  border-color: var(--blue-300);
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 18px 42px rgba(37, 99, 235, 0.16);
}
.ask__icon {
  display: grid;
  place-items: center;
  color: var(--prim);
  flex-shrink: 0;
}
.ask__input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  outline: none;
  font-size: 0.98rem;
  color: var(--text);
  padding: 12px 0;
}
.ask__input::placeholder {
  color: var(--text3);
}

/*
 * 语音输入按钮。
 * 放在输入框与「开始规划」之间：它属于「输入」这一组，
 * 放到主按钮右侧会让人以为它是提交的一部分。
 * 尺寸比主按钮小且无填充色，避免与「开始规划」抢视觉焦点。
 */
.ask__mic {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  margin-right: 6px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text2);
  transition: color 0.18s, background-color 0.18s, border-color 0.18s;
}
.ask__mic:hover {
  color: var(--prim);
  border-color: var(--blue-200);
  background: var(--blue-50);
}
.ask__mic:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}

/*
 * 正在收音：用呼吸光圈而不是变色 ——
 * 「正在听」是一个持续状态，脉冲更能表达「还在进行中」，
 * 单纯变色容易被理解为「已激活但已停止」。
 */
.ask__mic.is-listening {
  color: #fff;
  background: var(--prim);
  border-color: var(--prim);
  animation: micPulse 1.4s ease-in-out infinite;
}
@keyframes micPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.45); }
  50% { box-shadow: 0 0 0 7px rgba(37, 99, 235, 0); }
}
@media (prefers-reduced-motion: reduce) {
  .ask__mic.is-listening { animation: none; }
}

.ask__voice-err {
  margin-top: 8px;
  font-size: 0.8rem;
  color: var(--danger);
}
.ask__go {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
  padding: 13px 20px;
  border-radius: 11px;
  background: var(--grad);
  color: #fff;
  font-size: 0.92rem;
  font-weight: 650;
  white-space: nowrap;
  box-shadow: 0 8px 20px var(--glow);
  transition: transform 0.2s, filter 0.2s, box-shadow 0.2s;
}
.ask__go:hover {
  transform: translateY(-1px);
  filter: saturate(1.08);
  box-shadow: 0 12px 26px var(--glow);
}
.ask__go:active {
  transform: translateY(0);
}

/* ---------- 打字机动效 ----------
 *
 * .tw-hide 是「尚未打出」的部分：用 visibility 而不是 display 或 v-if。
 *   · display:none / v-if 会让文本不占位 → 元素宽高随打字变化 →
 *     下方内容被一路往下推，整页在两秒内持续抖动
 *   · visibility:hidden 仍参与布局，宽高从第一帧就是最终值，
 *     打字只是把已有位置上的字逐渐「显影」，没有任何位移
 * 这是打字机效果能否做得体面的关键一处。
 */
.tw-hide {
  visibility: hidden;
}

/* 仅供读屏器：给标题/副标题提供完整文本 */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

/* 输入框 + 打字机占位：占位需要精确定位到输入框文字起点，故用相对定位包裹 */
.ask__field {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.ask__ph {
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  pointer-events: none; /* 绝不挡住点击与聚焦 */
  color: var(--text3);
  font-size: inherit;
  white-space: nowrap;
  overflow: hidden;
}
.ask__ph-text {
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 打字光标：细竖条，缓慢闪烁，模拟真实输入光标 */
.ask__ph-caret {
  display: inline-block;
  width: 1.5px;
  height: 1.05em;
  margin-left: 2px;
  background: currentColor;
  animation: caretBlink 1.05s steps(1, end) infinite;
}
@keyframes caretBlink {
  0%, 50% { opacity: 1; }
  50.01%, 100% { opacity: 0; }
}

/* ---------- 示例提问 ---------- */
.prompts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 18px;
}
.prompts__label {
  font-size: 0.78rem;
  color: var(--text3);
}
.prompt {
  padding: 7px 13px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text2);
  font-size: 0.82rem;
  transition: border-color 0.2s, color 0.2s, background-color 0.2s;
}
.prompt:hover {
  border-color: var(--prim);
  color: var(--prim);
  background: var(--primary-soft);
}

/* ---------- Hero → 示例结果的过渡件 ----------
   一条短竖线 + 一个向下箭头，把视线从输入区引到下方结果。
   不用图片、不加装饰性渐变 —— 它承担的是**引导**职责：
   没有它时，两区之间只有一片空白，读者不知道下面和上面有关系。 */
/* ---------- 展开闸门的触发器 ----------
   结构与职责：一条短竖线 + 「看看它生成什么」+ 向下箭头。
   点击/回车展开下方内容；滚轮向下、触摸上滑同样会展开。

   做成按钮而不是纯装饰：它是首屏唯一的次要行动点，必须键盘可达、
   必须有读屏器语义（aria-expanded / aria-controls 在模板上）。 */
.hero__handoff {
  /* 复位按钮默认外观 —— 它看起来应像一条引导线，而不是一个按钮 */
  appearance: none;
  -webkit-appearance: none;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-top: 34px;
  padding: 4px 10px;
  border: none;
  background: transparent;
  color: var(--text3);
  font: inherit;
  cursor: pointer;
  transition: color 0.2s;
}
.hero__handoff:hover { color: var(--prim); }
.hero__handoff:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 4px;
  border-radius: 8px;
}

.hero__handoff-line {
  width: 1px;
  height: 30px;
  background: linear-gradient(
    180deg,
    transparent,
    var(--border) 40%,
    var(--border)
  );
}

.hero__handoff-label {
  font-size: 0.82rem;
  font-weight: 550;
  letter-spacing: 0.01em;
}

.hero__handoff-arrow {
  /* 轻微上下浮动，暗示「往下看」；幅度小到不构成干扰 */
  animation: handoffBounce 2.4s cubic-bezier(0.45, 0, 0.55, 1) infinite;
  transition: transform 0.24s cubic-bezier(0.2, 0.7, 0.2, 1);
}
/* 展开后箭头翻转，与「收起」的文案一致（否则箭头朝下却写着收起，自相矛盾） */
.hero__handoff-arrow.is-up { transform: rotate(180deg); }

@keyframes handoffBounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(3px); }
}

/* ---------- 收起态：Hero 撑满一屏 ----------
 *
 * 收起时下方内容不渲染，页面总高可能不足一屏 —— 那会带来两个问题：
 *   1. 页面底部露出一截空白，像没加载完
 *   2. 目标高度小于视口时浏览器不产生滚动，用户的滚轮/上滑毫无反馈，
 *      只能靠点击按钮（而滚动意图处理器仍会触发展开，体验上算"补救"）
 * 让 Hero 至少占满一屏，页面就成为「完整的一屏」，展开前不存在半截空白。
 *
 * 用 svh（small viewport height）而不是 vh：移动端浏览器地址栏收放时
 * vh 会把内容顶出可视区，svh 取下限更稳。带 vh 兜底供旧浏览器使用。
 * 减去导航栏高度，避免整体超出一屏反而多出滚动条。
 */
/*
 * Hero 自身有 overflow: hidden（见 .hero），内容超出会被裁掉。
 * 留出 28px 余量，让底部的引导件（箭头 + 说明）在首屏就能露出大半、
 * 明确提示「下面还有内容」；否则它正好压在下边界上被裁掉。
 */
.home--collapsed .hero {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - var(--nav-h, 64px) - 28px);
  min-height: calc(100svh - var(--nav-h, 64px) - 28px);
  padding-bottom: 32px;
}
/* Hero 内部本来就是单列居中，这里只需保证它垂直居中时不拉伸 */
.home--collapsed .hero__inner {
  margin-block: auto;
}

/* ---------- Hero → 示例结果的引导件 ----------
 *
 * 结构：一根向下的箭头（竖线 + 箭头尖）+ 右侧与箭头**中线对齐**的一行说明。
 * 用 CSS 画箭头（两条边框旋转 45°）而不是引图标：可与竖线在粗细、
 * 颜色上完全连贯，也不需要为一个三角引一个组件。
 *
 * 原先这里是两行（引导语 + 标题），信息量偏大，读起来像「新区块的大标题」；
 * 缩成箭头 + 一行短句后回到纯指向的作用。
 */
.join-arrow {
  /* 整块居中，与 Hero 的中轴一致 */
  display: flex;
  align-items: center; /* 文字垂直居中于箭头的**整根**箭头，即中线对齐 */
  justify-content: center;
  gap: 14px;
  margin: 0 auto 30px;
  /* 右移一点点：箭头本身不是视觉重心，文字才是，
     让「箭头 + 文字」这个组合看起来是整体居中的 */
  padding-left: 6px;
}

/* 竖线：用渐变让它从透明淡入，避免与上方内容硬切 */
.join-arrow__shaft {
  width: 2px;
  height: 58px;
  border-radius: 2px;
  background: linear-gradient(
    180deg,
    rgba(37, 99, 235, 0.06),
    var(--blue-300) 30%,
    var(--prim)
  );
}

/* 箭头尖：两条边框旋转成 V 形 */
.join-arrow__tip {
  width: 11px;
  height: 11px;
  margin-left: -7px; /* 与竖线首尾相接，不留缝 */
  border-right: 2px solid var(--prim);
  border-bottom: 2px solid var(--prim);
  border-radius: 1px;
  transform: rotate(45deg) translate(-2px, -2px);
}

/*
 * 说明文字：彩色标注。
 *
 * 用渐变文字（background-clip: text）而不是单色，是因为它承担的是
 * 「这一步产出了什么」的强调，需要与普通正文拉开。取蓝 → 青 → 紫的
 * 冷色过渡，与站点主色同族，不引入新色相。
 *
 * 必须同时写 `color` 作为降级：不支持 background-clip: text 的浏览器
 * 会把文字画成透明（不可见）—— 那比没有强调严重得多。
 */
.join-arrow__text {
  font-size: clamp(1.05rem, 1.6vw, 1.3rem);
  font-weight: 750;
  letter-spacing: -0.01em;
  white-space: nowrap;

  color: var(--prim); /* 降级色 */
  background-image: linear-gradient(
    100deg,
    var(--prim) 0%,
    #0ea5e9 42%,
    #7c3aed 100%
  );
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* 深色主题下提亮一档，否则蓝紫在深底上发闷 */
:root[data-theme='dark'] .join-arrow__text {
  color: var(--blue-300);
  background-image: linear-gradient(
    100deg,
    var(--blue-300) 0%,
    #38bdf8 42%,
    #a78bfa 100%
  );
}

/*
 * 减弱动效偏好下**停掉浮动**，但保留线条与箭头本身。
 * 它们是引导结构而非装饰 —— 全隐藏会让「输入 → 结果」的衔接又没了提示，
 * 静置不动即可。注意这里必须单独写：上面的 reduce 块只处理了
 * .home/.rv 的入场，覆盖不到这个无限循环动画。
 */
@media (prefers-reduced-motion: reduce) {
  .hero__handoff-arrow {
    animation: none;
    transition: none;
  }
}


/* ============================================================
   通用区块
   ============================================================ */
.section {
  padding: 88px 0;
}

/*
 * 紧接 Hero 的区块：把上间距压小，让两区读起来是**一段连续的内容**。
 *
 * 原先 Hero 下内边距 48px + 本区上内边距 88px = 136px 纯空白，
 * 加上一个左对齐的大标题，视觉上「翻页」了 —— 而这一区的内容
 * 其实只是上一区那句输入的**结果**，不该另起一章。
 */
.section--join {
  padding-top: 40px;
  /*
   * 滚动定位时在顶部留出的余量。
   *
   * ⚠️ 上一轮我把这条加在了 .section--join 上，但**滚动目标是它的父容器
   * #home-more**，属性根本没命中，所以当时那条规则毫无作用。
   * 现在加在真正的滚动目标上（.reveal-host），作为兜底：
   * 万一将来有人改用 scrollIntoView 或触发浏览器的默认锚点滚动，
   * 也会自动避开固定导航栏。
   */
  scroll-margin-top: calc(var(--nav-h, 64px) + 24px);
}

/* 可展开内容的容器（滚动目标）。解释见上 */
.reveal-host {
  scroll-margin-top: calc(var(--nav-h, 64px) + 24px);
}

.section--tint {
  background: var(--bg2);
}

/* ---------- 示例结果区：整区沿用 Hero 的居中构图 ----------
 *
 * 原先 Hero 是居中的单栏，紧接着的「生成结果」区却是左对齐的标题 + 左对齐的
 * 卡片，两区对齐方式相反 —— 读起来像两个不同设计的页面拼在一起，
 * 这正是「衔接突兀」最主要的原因（比间距问题更明显）。
 *
 * 处理原则：**整区居中，但卡片内部保持左对齐**。
 *   · 区级元素（引导件、tabs）居中，与 Hero 的构图对齐
 *   · 卡片内部不清真居中 —— 那里是「时段 + 活动 + 费用」的三列网格，
 *     文字居中会让列对不齐、扫读成本上升。卡片作为**块**在区内居中即可。
 *     （这也是常见做法：居中的版面里，内容块内部仍按左对齐阅读。）
 *
 * 注：这里原有一组 .showcase-intro 样式（两行引导语 + 标题），
 * 已按用户要求缩减为箭头 + 一行说明（见上方 .join-arrow），
 * 那组规则随之删除，避免留下无引用代码。
 */

/*
 * 卡片区收窄到 980px（居中由下方通用规则统一处理）。
 *
 * 为什么不铺满 1120px 的容器：demo 有 3 座城市，在那个宽度下
 * auto-fit 会排出 3 列、每张约 361px 宽，而卡片内部是
 * 「时段 44px + 活动内容 + 费用」的三列网格 —— 太宽会让活动名与费用
 * 之间拉出很长的空隙，扫读时反而费眼。收到 980px 后每张约 315px，
 * 行宽落在舒适区间。
 */
.section--join .showcase {
  max-width: 980px;
}

.sec-head {
  max-width: 40em;
  margin-bottom: 40px;
}

/* ============================================================
   区块居中对齐
   ------------------------------------------------------------
   Hero 是居中的单栏构图，其下方各区块原先却是左对齐 —— 两区对齐方式相反，
   页面读起来像几套不同设计拼在一起，这是「衔接突兀」最主要的原因。

   这里统一为**区块级居中**，并且用一条规则覆盖所有区块，而不是逐个加样式：
   将来新增区块会自动居中，不会再漏掉一个造成新的不一致。

   刻意**不居中卡片内部**：场景卡与步骤卡内部是「时段/编号 + 内容 + 费用」
   的多列网格，文字逐行居中会让列对不齐、扫读成本上升。
   居中的是**块本身**，块内仍按左对齐阅读 —— 这是居中式版面的常规做法。
   ============================================================ */
.section .sec-head {
  /* 块居中后文字随之居中；max-width 保证长文案不会拉成一条超长行 */
  margin-inline: auto;
  text-align: center;
}

/* 区块内容块整块居中 */
.section .scenes,
.section .steps,
.section .showcase,
.section .tabs {
  max-width: 1000px;
  margin-inline: auto;
}

/* tabs 是 flex，居中后还需让子项在行内居中排列 */
.section .tabs {
  justify-content: center;
  flex-wrap: wrap;
  overflow-x: visible;
}

.eyebrow {
  display: inline-block;
  font-size: 0.73rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--prim);
  margin-bottom: 12px;
}
.sec-head h2 {
  font-size: clamp(1.6rem, 2.9vw, 2.25rem);
  font-weight: 800;
  letter-spacing: -0.028em;
}
.sec-head > p:last-child {
  margin-top: 12px;
  font-size: 0.98rem;
  line-height: 1.72;
  color: var(--text2);
}

/* ============================================================
   2. 示例行程
   ============================================================ */
.tabs {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
  margin-bottom: 22px;
}
.tab {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 11px 20px;
  border-radius: 13px;
  border: 1px solid var(--border);
  background: var(--panel);
  transition: border-color 0.22s, box-shadow 0.22s, transform 0.22s;
}
.tab b {
  font-size: 0.95rem;
  font-weight: 700;
}
.tab i {
  font-style: normal;
  font-size: 0.73rem;
  color: var(--text3);
}
.tab:hover {
  transform: translateY(-2px);
  border-color: var(--blue-300);
}
.tab--on {
  background: var(--grad);
  border-color: transparent;
  box-shadow: 0 12px 28px var(--glow);
}
.tab--on b,
.tab--on i {
  color: #fff;
}

.showcase {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 18px;
}
.daycard {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px 22px;
  box-shadow: var(--shadow-sm);
  /* 切换城市时逐张入场（延迟由模板内的 animationDelay 错峰） */
  animation: demoIn 0.4s cubic-bezier(0.2, 0.7, 0.2, 1) both;
  transition: transform 0.26s cubic-bezier(0.2, 0.7, 0.2, 1), box-shadow 0.26s;
}
@keyframes demoIn {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .daycard {
    animation: none;
  }
}
.daycard:hover {
  transform: translateY(-4px);
  box-shadow: 0 20px 44px rgba(37, 99, 235, 0.13);
}
.daycard__head {
  display: flex;
  align-items: center;
  gap: 9px;
  padding-bottom: 11px;
  border-bottom: 2px solid var(--hairline);
}
.daycard__no {
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--prim);
}
.daycard__date {
  font-family: var(--mono);
  font-size: 0.7rem;
  color: var(--text3);
}
.daycard__theme {
  margin-left: auto;
  font-size: 0.78rem;
  font-weight: 650;
}
.daycard__sum {
  margin-top: 10px;
  font-size: 0.84rem;
  color: var(--text2);
}

.acts {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
}
.acts__row {
  display: grid;
  grid-template-columns: 44px 1fr auto;
  gap: 11px;
  align-items: start;
  padding: 11px 0;
  border-bottom: 1px dashed var(--hairline);
}
.acts__row:last-child {
  border-bottom: none;
}
.acts__slot {
  font-size: 0.7rem;
  font-weight: 650;
  text-align: center;
  padding: 3px 0;
  border-radius: 6px;
}
.acts__slot--morning {
  background: var(--blue-50);
  color: var(--blue-700);
}
.acts__slot--afternoon {
  background: var(--gold-soft);
  color: var(--gold-600);
}
.acts__slot--evening {
  background: var(--blue-900);
  color: #fff;
}
.acts__body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.acts__body b {
  font-size: 0.87rem;
  font-weight: 600;
}
.acts__body i {
  font-style: normal;
  font-size: 0.79rem;
  color: var(--text3);
  line-height: 1.5;
}
.acts__cost {
  font-size: 0.76rem;
  color: var(--text3);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* ============================================================
   3. 三个场景
   ============================================================ */
.scenes {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.scene {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 32px;
  align-items: center;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 30px 34px;
  box-shadow: var(--shadow-sm);
}
/* 偶数行左右对调，形成阅读节奏 */
.scene:nth-child(even) .scene__say {
  order: 2;
}

.scene__eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--prim);
  text-transform: uppercase;
}
.scene__title {
  margin-top: 8px;
  font-size: 1.24rem;
  font-weight: 750;
  letter-spacing: -0.02em;
}
.scene__value {
  margin-top: 8px;
  font-size: 0.9rem;
  line-height: 1.7;
  color: var(--text2);
}

.chat {
  margin-top: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 30em;
}
.chat__me {
  align-self: flex-end;
  background: var(--grad);
  color: #fff;
  padding: 9px 14px;
  border-radius: 13px 13px 4px 13px;
  font-size: 0.85rem;
  box-shadow: 0 6px 16px var(--glow);
}
.chat__ai {
  background: var(--bubble-ai);
  padding: 9px 14px;
  border-radius: 13px 13px 13px 4px;
  font-size: 0.85rem;
  line-height: 1.65;
  color: var(--text2);
}

.scene__get {
  background: var(--panel2);
  border: 1px solid var(--hairline);
  border-radius: 14px;
  padding: 18px 20px;
}
.res__title {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text3);
  letter-spacing: 0.04em;
  margin-bottom: 4px;
}
.res {
  margin: 0;
}
.res__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
  padding: 9px 0;
  border-bottom: 1px dashed var(--hairline);
}
.res__row:last-child {
  border-bottom: none;
}
.res dt {
  flex-shrink: 0;
  font-size: 0.78rem;
  color: var(--text3);
  font-family: var(--mono);
}
.res dd {
  margin: 0;
  font-size: 0.83rem;
  font-weight: 550;
  text-align: right;
  line-height: 1.5;
}
.res__v--ok {
  color: var(--success);
}
.res__v--warn {
  color: var(--gold-600);
}

/* ============================================================
   4. 三步流程
   ============================================================ */
.steps {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 44px;
  align-items: start;
}

.steps__list {
  list-style: none;
  margin: 0;
  padding: 0;
  position: relative;
}
/* 串起三步的竖线 */
.steps__list::before {
  content: '';
  position: absolute;
  left: 21px;
  top: 34px;
  bottom: 34px;
  width: 2px;
  background: linear-gradient(to bottom, var(--blue-200), var(--blue-50));
}
.step {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 16px;
  padding: 20px 4px;
  cursor: pointer;
  border-radius: 12px;
  transition: background-color 0.22s;
  /* 按钮元素的重置：抹掉浏览器默认外观，让它与原先的 li 视觉一致 */
  width: 100%;
  border: none;
  background: transparent;
  font: inherit;
  color: inherit;
  text-align: left;
}
.step:hover {
  background: var(--panel);
}
/* 键盘聚焦要有可见指示，否则 Tab 过去看不出焦点在哪 */
.step:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}
.step__no {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--panel);
  border: 2px solid var(--border);
  font-family: var(--mono);
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text3);
  transition: all 0.26s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.step--on .step__no {
  background: var(--grad);
  border-color: transparent;
  color: #fff;
  transform: scale(1.08);
  box-shadow: 0 8px 22px var(--glow);
}
.step__body b {
  display: block;
  font-size: 1.02rem;
  font-weight: 700;
  margin-bottom: 5px;
  opacity: 0.45;
  transition: opacity 0.24s;
}
.step__body i {
  font-style: normal;
  font-size: 0.85rem;
  line-height: 1.65;
  color: var(--text3);
  transition: color 0.24s;
}
.step--on .step__body b {
  opacity: 1;
}
.step--on .step__body i {
  color: var(--text2);
}

.preview {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 30px 32px;
  min-height: 300px;
  display: flex;
  align-items: center;
  box-shadow: var(--shadow);
}
.pv {
  width: 100%;
  animation: pvIn 0.34s cubic-bezier(0.2, 0.7, 0.2, 1) both;
}
@keyframes pvIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .pv {
    animation: none;
  }
}
.pv__label {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text3);
  margin-bottom: 18px;
}
.pv__ask {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--panel2);
  border: 1px solid var(--border);
  border-radius: 13px;
  padding: 15px 17px;
  font-size: 0.9rem;
}
.pv__ask :deep(svg) {
  color: var(--prim);
  flex-shrink: 0;
}
.pv__hint {
  margin-top: 16px;
  font-size: 0.79rem;
  color: var(--text3);
}

.check {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.check li {
  display: grid;
  grid-template-columns: 9px 46px 1fr;
  align-items: center;
  gap: 12px;
  padding: 13px 16px;
  border-radius: 12px;
  background: var(--panel2);
  border: 1px solid var(--hairline);
  font-size: 0.86rem;
}
.check__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 3px rgba(72, 187, 120, 0.16);
}
.check b {
  font-weight: 650;
}
.check span:last-child {
  color: var(--text2);
}

.mini {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.mini__day {
  display: grid;
  grid-template-columns: 52px 1fr;
  grid-template-rows: auto auto;
  gap: 2px 14px;
  padding: 13px 16px;
  border-radius: 12px;
  background: var(--panel2);
  border: 1px solid var(--hairline);
}
.mini__day span {
  grid-row: 1 / 3;
  font-family: var(--mono);
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--prim);
  align-self: center;
}
.mini__day b {
  font-size: 0.88rem;
  font-weight: 650;
}
.mini__day i {
  font-style: normal;
  font-size: 0.79rem;
  color: var(--text3);
}

/* ============================================================
   5. 收尾
   ============================================================ */
.closing {
  padding: 0 0 104px;
}
.closing__box {
  position: relative;
  overflow: hidden;
  text-align: center;
  /* 与个人主页顶部沉浸区共用同一份浅色水洗底，见 main.css 的 --grad-wash */
  background: var(--grad-wash);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 64px 40px 56px;
}
.closing__eyebrow {
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--prim);
}
.closing__title {
  margin-top: 12px;
  font-size: clamp(1.75rem, 3.3vw, 2.5rem);
  font-weight: 800;
  letter-spacing: -0.03em;
}
.closing__sub {
  margin: 14px auto 0;
  max-width: 32em;
  font-size: 0.98rem;
  line-height: 1.7;
  color: var(--text2);
}
.ask--closing {
  max-width: 620px;
  margin: 28px auto 0;
}
/* 原先此处有 .closing__alt（「或用账号登录后再规划」按钮的间距）。
   该入口已删除，样式一并移除，避免留下无引用的规则。 */

/* ============================================================
   响应式（移动端优先考量：Hero 堆叠、输入框换行、场景单列）
   ============================================================ */
@media (max-width: 1080px) {
  /* 原先这里调 .hero__inner 的 grid 列数与 gap（两栏变单栏）。
     Hero 已是单栏居中布局，这两条失去作用，故删除；
     断点本身保留 —— 下面 .hero 的 padding 仍需要它。 */
  .hero {
    padding-top: 52px;
  }
  .scene {
    grid-template-columns: 1fr;
    gap: 22px;
    padding: 26px 24px;
  }
  .scene:nth-child(even) .scene__say {
    order: 0;
  }
  .steps {
    grid-template-columns: 1fr;
    gap: 26px;
  }
  .steps__list::before {
    display: none;
  }
}

@media (max-width: 760px) {
  .section {
    padding: 60px 0;
  }
  .showcase {
    grid-template-columns: 1fr;
  }
  .closing__box {
    padding: 46px 22px 40px;
  }
  .closing {
    padding-bottom: 72px;
  }
}

@media (max-width: 620px) {
  .hero__title {
    font-size: 2.05rem;
  }
  /* 输入框在窄屏改为上下排列：一行放不下输入 + 按钮 */
  .ask {
    flex-wrap: wrap;
    padding: 12px;
  }
  .ask__input {
    flex: 1 1 auto;
    order: 1;
  }
  .ask__go {
    order: 2;
    width: 100%;
    justify-content: center;
  }
  .prompts {
    flex-direction: column;
    align-items: stretch;
  }
  .prompt {
    text-align: left;
  }
  /* 车次比选在窄屏改为两行：车次+时刻一行，座位+票价另起一行 */
  /* 天气三格在窄屏压缩内边距，避免文字换行 */
  .preview {
    padding: 22px 18px;
    min-height: 260px;
  }
  .scene {
    padding: 22px 18px;
  }
}
</style>
