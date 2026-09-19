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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import AppNavbar from '@/components/AppNavbar.vue'
import AppFooter from '@/components/AppFooter.vue'
import TravelIcon from '@/components/TravelIcon.vue'

const user = useUserStore()
const router = useRouter()

/* ==================== 1. Hero：一句话规划 ==================== */
const draft = ref('')
const inputEl = ref<HTMLInputElement | null>(null)

/** 带着这句话进对话；未登录先去登录（沿用既有 example 参数约定） */
function submitPlan() {
  const text = draft.value.trim()
  const target = startHref()
  router.push(text ? { path: target, query: { example: text } } : { path: target })
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

/**
 * Hero 行程单数据。
 *
 * 全部为**静态示例**：车次、票价、天气都是写死的示范值。
 * 故卡片标注「示例」而非「实时」——标成实时会让人以为这是此刻查到的
 * 真实数据，属于误导。真实查询发生在对话中，由 MCP 工具完成。
 */
/**
 * Hero 卡片展示的是**生成过程中查到的东西**（车次比选、天气、预算），
 * 而不是成品行程。
 *
 * 为什么这样分工：下方「生成结果」区展示的是最终排出的行程（按天 + 时段）。
 * 若 Hero 也放一份成品行程，两处内容必然重复（原先就是同一份北京 3 天，
 * 用户滚下去会觉得「刚才看过了」）。改为各回答一个问题：
 *   Hero    -> 它替我查到了什么、依据什么定的
 *   示例区  -> 最后排出来长什么样
 * 车次比选还顺带证明了「数据是实时查的、不是模型编的」，这正是 Hero 要传达的价值。
 */
const heroPlan = {
  from: '广州南',
  to: '北京西',
  days: 3,
  budget: '¥3000',
  season: '10-01 ~ 10-03'
}

/** 车次比选：体现「货比三家」，而不只是给一个答案 */
const heroTrains = [
  { code: 'G77', time: '08:00 → 13:24', price: 553, seat: '二等座', best: true },
  { code: 'G79', time: '10:05 → 15:38', price: 553, seat: '二等座', best: false },
  { code: 'G81', time: '13:20 → 19:02', price: 553, seat: '二等座', best: false }
]

/** 逐日天气：对应行程里每一天的安排 */
const heroWeather = [
  { day: 1, date: '10-01', text: '晴', temp: '12~22°C', icon: 'sun' },
  { day: 2, date: '10-02', text: '多云', temp: '10~19°C', icon: 'sun' },
  { day: 3, date: '10-03', text: '阴', temp: '11~18°C', icon: 'wave' }
]

/** 预算明细：让「¥3000」这个数字有出处 */
const heroBudget = [
  { label: '往返车票', value: 1106 },
  { label: '住宿 2 晚', value: 1160 },
  { label: '门票', value: 155 },
  { label: '餐饮', value: 579 }
]

/** 生成阶段文案：用于说明这张卡片是怎么来的 */
const buildStages = ['解析出行需求', '核对应季天气', '确认车次票价']

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

let revealTimer: number | null = null
let io: IntersectionObserver | null = null

onMounted(() => {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

  if (reduce) {
    entered.value = true
    document.querySelectorAll('.rv').forEach((el) => el.classList.add('in'))
    return
  }

  // 等两帧再置位，确保过渡有起点可播
  revealTimer = window.setTimeout(() => {
    entered.value = true
  }, 60)

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

  stepTimer = window.setInterval(() => {
    activeStep.value = (activeStep.value + 1) % steps.length
  }, 3600)
})

onUnmounted(() => {
  io?.disconnect()
  stopStepTimer()
  if (revealTimer !== null) window.clearTimeout(revealTimer)
  /*
   * 离开首页时若语音识别仍在进行，必须停掉。
   * 不停的话麦克风会一直被占用（浏览器标签上持续显示录音中），
   * 用户会以为程序在偷听；重新进入首页再点也无法重新 start。
   */
  recognition?.stop()
  recognition = null
})

/**
 * 未登录先去登录页，已登录直接进对话页。
 *
 * 抽成函数而不是在调用处内联三元表达式：这个判断原先写了两遍
 * （一个已删除的「或用账号登录后再规划」入口 + submitPlan），
 * 两处重复意味着将来改跳转规则必须记得同时改两个地方。
 */
function startHref(): string {
  return user.isLoggedIn ? '/chat' : '/login'
}
</script>

<template>
  <AppNavbar />

  <main id="main" tabindex="-1" class="home" :class="{ 'home--in': entered }">
    <!-- ============================================================
         1. HERO：可输入的规划框 + 正在生成的行程单
         左「说」右「得」，让输入与结果的关系一眼可见
         ============================================================ -->
    <section class="hero">
      <div class="hero__aura" aria-hidden="true"></div>

      <div class="container hero__inner">
        <!-- 左：说 -->
        <div class="hero__say">
          <p class="hero__kicker">
            <span class="dot"></span>
            多 Agent 协作 · 实时数据核对
          </p>

          <h1 class="hero__title">
            一句话，<br />
            生成<span class="hero__title-em">可执行</span>的旅行日程
          </h1>

          <p class="hero__sub">
            说出目的地、天数与预算。车次与天气我们实时查好，
            最后落成一份按天排布、随时可改的行程。
          </p>

          <!-- 可直接输入：这是 Hero 的主操作，不是装饰 -->
          <form class="ask" @submit.prevent="submitPlan">
            <span class="ask__icon" aria-hidden="true">
              <TravelIcon name="compass" :size="18" />
            </span>
            <input
              ref="inputEl"
              v-model="draft"
              class="ask__input"
              type="text"
              placeholder="例如：广州到北京 3 天，预算 3000，坐高铁"
              aria-label="描述你的旅行计划"
            />
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
        </div>

        <!--
          右：得（生成过程中查到的东西）
          刻意不放成品行程——下方「生成结果」区已有三份按天排布的行程，
          这里若再放一份就会重复。此处展示车次比选、逐日天气与预算构成，
          回答的是「它替我查了什么、依据什么定的」。
        -->
        <div class="hero__get">
          <article class="plan">
            <header class="plan__head">
              <div class="plan__route">
                <TravelIcon name="route" :size="15" />
                <span>{{ heroPlan.from }}</span>
                <span class="plan__arrow" aria-hidden="true">
                  <i></i>
                  <TravelIcon name="plane" :size="13" />
                  <i></i>
                </span>
                <span>{{ heroPlan.to }}</span>
              </div>
              <span class="plan__badge">示例</span>
            </header>

            <p class="plan__meta">
              {{ heroPlan.season }} · {{ heroPlan.days }} 天 · 预算 {{ heroPlan.budget }}
            </p>

            <div class="plan__body">
              <!-- 车次比选：给出备选而非单一答案，也证明数据是查来的 -->
              <section class="blk">
                <p class="blk__title">
                  <TravelIcon name="train" :size="14" />
                  高铁车次
                  <span class="blk__hint">3 趟可选</span>
                </p>
                <ul class="trains">
                  <li
                    v-for="t in heroTrains"
                    :key="t.code"
                    class="trains__row"
                    :class="{ 'is-best': t.best }"
                  >
                    <span class="trains__code">{{ t.code }}</span>
                    <span class="trains__time">{{ t.time }}</span>
                    <span class="trains__seat">{{ t.seat }}</span>
                    <span class="trains__price">¥{{ t.price }}</span>
                    <span v-if="t.best" class="trains__tag">推荐</span>
                  </li>
                </ul>
              </section>

              <!-- 逐日天气：对应行程里每一天 -->
              <section class="blk">
                <p class="blk__title">
                  <TravelIcon name="sun" :size="14" />
                  出行天气
                </p>
                <ul class="weather">
                  <li v-for="w in heroWeather" :key="w.day" class="weather__item">
                    <span class="weather__day">Day {{ w.day }}</span>
                    <TravelIcon :name="w.icon" :size="15" />
                    <span class="weather__text">{{ w.text }}</span>
                    <span class="weather__temp">{{ w.temp }}</span>
                  </li>
                </ul>
              </section>

              <!-- 预算构成：让「¥3000」有出处 -->
              <section class="blk">
                <p class="blk__title">
                  <TravelIcon name="luggage" :size="14" />
                  预算构成
                  <span class="blk__hint">合计 {{ heroPlan.budget }}</span>
                </p>
                <ul class="budget">
                  <li v-for="b in heroBudget" :key="b.label" class="budget__row">
                    <span class="budget__label">{{ b.label }}</span>
                    <span class="budget__bar" aria-hidden="true">
                      <i :style="{ width: `${Math.round((b.value / 3000) * 100)}%` }"></i>
                    </span>
                    <span class="budget__value">¥{{ b.value }}</span>
                  </li>
                </ul>
              </section>
            </div>

            <!--
              页脚说明这张卡片经过了哪几步，而不是播放进度。
              原先这里是一段「正在解析 → 正在核对 → 已确认」的动态进度条，
              配合区块逐块揭示。实测观感不好：卡片会从空盒子里分三层
              往外跳，刷新页面时尤其突兀。
              行程卡本身就是最好的说明，不需要再演一遍生成过程。
            -->
            <footer class="plan__foot">
              <span class="plan__stages">
                <template v-for="(s, si) in buildStages" :key="s">
                  <span class="plan__stage-i">
                    <TravelIcon name="check" :size="11" />{{ s }}
                  </span>
                  <span v-if="si < buildStages.length - 1" class="plan__stage-sep" aria-hidden="true">·</span>
                </template>
              </span>
              <span class="plan__done">可保存</span>
            </footer>
          </article>

          <p class="hero__note">示例数据 · 实际车次、天气与票价以对话中查询结果为准</p>
        </div>
      </div>
    </section>

    <!-- ============================================================
         2. 示例行程：结果优先，先看成品
         ============================================================ -->
    <section class="section">
      <div class="container">
        <header class="sec-head rv">
          <p class="eyebrow">生成结果</p>
          <h2>先看看它排出来的行程</h2>
          <p>三座城市，每天按时段拆开，费用写清楚。</p>
        </header>

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
  </main>

  <AppFooter />
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

.hero__inner {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 460px;
  gap: 64px;
  align-items: center;
}

/* ---------- 左：说 ---------- */
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

/* ---------- 右：行程单 ---------- */
.hero__get {
  position: relative;
}

.plan {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 20px 22px 16px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 20px 46px rgba(16, 24, 40, 0.09);
}

.plan__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--hairline);
}
.plan__route {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 700;
}
.plan__arrow {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--prim);
}
.plan__arrow i {
  width: 22px;
  height: 1px;
  background: repeating-linear-gradient(90deg, var(--blue-300) 0 3px, transparent 3px 6px);
}
.plan__arrow :deep(svg) {
  transform: rotate(45deg);
}
.plan__badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--gold-600);
  background: var(--gold-soft);
  padding: 3px 9px;
  border-radius: 6px;
}

/* 路线下方的轻量概要行 */
.plan__meta {
  margin: 12px 0 2px;
  font-size: 0.78rem;
  color: var(--text3);
  font-variant-numeric: tabular-nums;
}

/* ---------- 三个信息区块（车次 / 天气 / 预算） ---------- */
/*
 * 不再固定最小高度：原先写 min-height: 268px 是为了让区块逐块揭示时
 * 卡片不跳高，但那也意味着页面刚加载时有一段空白占位。
 * 现在三块一次性呈现，高度由内容决定即可。
 */
.plan__body {
  padding-top: 2px;
}
.blk {
  padding: 12px 0;
  border-bottom: 1px dashed var(--hairline);
}
.blk:last-child {
  border-bottom: none;
}
.blk__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--text2);
  margin-bottom: 9px;
}
.blk__title :deep(svg) {
  color: var(--prim);
}
.blk__hint {
  margin-left: auto;
  font-weight: 500;
  font-size: 0.72rem;
  color: var(--text3);
}

/* ---------- 车次比选 ---------- */
.trains {
  list-style: none;
  margin: 0;
  padding: 0;
}
.trains__row {
  display: grid;
  grid-template-columns: 46px 1fr 46px 50px auto;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 8px;
  font-size: 0.79rem;
}
.trains__row.is-best {
  background: var(--primary-soft);
}
.trains__code {
  font-family: var(--mono);
  font-weight: 700;
  font-size: 0.76rem;
}
.trains__time {
  color: var(--text2);
  font-variant-numeric: tabular-nums;
}
.trains__seat,
.trains__price {
  color: var(--text3);
  font-size: 0.74rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.trains__tag {
  font-size: 0.66rem;
  font-weight: 700;
  color: var(--prim);
  background: var(--panel);
  border-radius: 5px;
  padding: 2px 6px;
}

/* ---------- 逐日天气 ---------- */
.weather {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: 8px;
}
.weather__item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 10px 4px;
  border-radius: 10px;
  background: var(--panel2);
  border: 1px solid var(--hairline);
}
.weather__item :deep(svg) {
  color: var(--gold-600);
}
.weather__day {
  font-family: var(--mono);
  font-size: 0.66rem;
  color: var(--text3);
}
.weather__text {
  font-size: 0.76rem;
  font-weight: 650;
}
.weather__temp {
  font-size: 0.7rem;
  color: var(--text3);
  font-variant-numeric: tabular-nums;
}

/* ---------- 预算构成 ---------- */
.budget {
  list-style: none;
  margin: 0;
  padding: 0;
}
.budget__row {
  display: grid;
  grid-template-columns: 68px 1fr 56px;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
  font-size: 0.76rem;
}
.budget__label {
  color: var(--text3);
}
/* 条形图比纯数字更直观地看出钱花在哪 */
.budget__bar {
  height: 6px;
  border-radius: 3px;
  background: var(--panel2);
  overflow: hidden;
}
.budget__bar i {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--grad);
  transition: width 0.5s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.budget__value {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--text2);
  font-weight: 600;
}

/* 页脚：左侧列出这张卡片经过的三步，右侧标「可保存」 */
.plan__foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--hairline);
  font-size: 0.72rem;
  color: var(--text3);
}
.plan__stages {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  min-width: 0;
}
.plan__stage-i {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.plan__stage-i :deep(svg) {
  color: var(--success);
  flex-shrink: 0;
}
.plan__stage-sep {
  opacity: 0.45;
}
.plan__done {
  margin-left: auto;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  font-weight: 650;
  color: var(--success);
}

.hero__note {
  margin-top: 12px;
  text-align: center;
  font-size: 0.74rem;
  color: var(--text3);
}

/* ============================================================
   通用区块
   ============================================================ */
.section {
  padding: 88px 0;
}
.section--tint {
  background: var(--bg2);
}
.sec-head {
  max-width: 40em;
  margin-bottom: 40px;
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
  background: linear-gradient(160deg, #eef4ff 0%, #f8fafc 52%, #eff9ff 100%);
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
  .hero__inner {
    grid-template-columns: 1fr;
    gap: 42px;
  }
  .hero {
    padding-top: 52px;
  }
  .hero__get {
    max-width: 540px;
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
  .trains__row {
    grid-template-columns: 46px 1fr auto;
    row-gap: 2px;
  }
  .trains__seat {
    grid-column: 2 / 3;
    grid-row: 2;
    text-align: left;
  }
  .trains__price {
    grid-column: 3 / 4;
    grid-row: 2;
  }
  .trains__tag {
    grid-column: 3 / 4;
    grid-row: 1;
  }
  /* 天气三格在窄屏压缩内边距，避免文字换行 */
  .weather__item {
    padding: 9px 2px;
  }
  .budget__row {
    grid-template-columns: 58px 1fr 50px;
    gap: 8px;
  }
  .preview {
    padding: 22px 18px;
    min-height: 260px;
  }
  .scene {
    padding: 22px 18px;
  }
}
</style>
