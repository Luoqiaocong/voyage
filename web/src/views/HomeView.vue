<script setup lang="ts">
/**
 * HomeView · 首页
 *
 * 结构：左文右景 Hero → 数据条 → 能力区(6 卡) → 产品演示 → 示例行程 → 三步流程 → CTA
 *
 * 视觉方向：清爽浅色系 + 沉浸式旅行科技感。
 * - 底色为极浅冷灰白（--bg #f7f9fc / --bg2 #f0f4f8）
 * - 主色为旅行蓝（--blue-600 #2563EB，配白字 5.17:1 达 WCAG AA）
 * - 暖金仅作极少量点缀（评分、徽标）
 *
 * 旅行氛围的做法：全部使用内联 SVG（地图纹理、航线、时段图标）而非位图——
 * 高分屏不糊、不增加请求体积、深浅主题自动适配，也无需维护两套图。
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import AppNavbar from '@/components/AppNavbar.vue'
import AppFooter from '@/components/AppFooter.vue'
import FeatureIcon from '@/components/FeatureIcon.vue'
import TravelIcon from '@/components/TravelIcon.vue'

const user = useUserStore()
const router = useRouter()

function startHref(): string {
  return user.isLoggedIn ? '/chat' : '/login'
}

/**
 * 点击示例胶囊：带着这句话进入对话。
 *
 * 用 query 传递而非路由 state——state 刷新即丢，query 能在登录页读取，
 * 并在登录成功后继续生效（登录页会把 example 暂存后在跳转时消费）。
 */
function useExample(text: string) {
  const target = user.isLoggedIn ? '/chat' : '/login'
  router.push({ path: target, query: { example: text } })
}

/* ---------------- 数据 ---------------- */
const features = [
  {
    icon: 'spark' as const,
    tag: '生成',
    title: 'AI 智能规划',
    desc: '说出目的地、天数与预算，一句话得到完整可执行的行程方案。',
    more: '无需填表，自然语言即可'
  },
  {
    icon: 'train' as const,
    tag: '实时',
    title: '车次票价查询',
    desc: '车次、票价与余票即时可查，交通信息真实可核验。',
    more: '接入实时车次数据源'
  },
  {
    icon: 'sun' as const,
    tag: '天气',
    title: '天气穿衣建议',
    desc: '出发前自动查询目的地天气，按天气推荐穿着与安排。',
    more: '按出行日期区间查询'
  },
  {
    icon: 'edit' as const,
    tag: '可编辑',
    title: '行程一键调整',
    desc: '按天按时段展示，景点、住宿与美食随时增删并保存。',
    more: '改完即存，下次接着看'
  },
  {
    icon: 'layers' as const,
    tag: '稳定',
    title: '多模型保障',
    desc: '接入多个大模型，调用失败自动重试与降级，对话始终稳定。',
    more: '失败自动重试不中断'
  },
  {
    icon: 'chat' as const,
    tag: '流式',
    title: '实时对话体验',
    desc: '思考过程、工具调用与正文实时呈现，等待不再漫长。',
    more: '逐字输出，所见即所得'
  }
]

/** 信任数据条 */
const stats = [
  { num: '3 步', label: '从需求到成稿' },
  { num: '2 类', label: '实时数据源' },
  { num: '多人', label: 'Agent 协作规划' },
  { num: '随时', label: '可编辑可保存' }
]

/** Hero 示例提问：可点击，点了直接带着问题进对话 */
const heroExamples = [
  { icon: 'train', text: '广州到北京 3 天，预算 3000，坐高铁' },
  { icon: 'sun', text: '成都周末两日游，帮我看看天气' },
  { icon: 'camera', text: '西安 4 天，想拍古建筑和吃小吃' }
]

interface DemoDay {
  theme: string
  summary: string
  acts: { slot: string; name: string; desc: string }[]
}
interface Demo {
  dest: string
  days: number
  tag: string
  plan: DemoDay[]
}

const demos: Demo[] = [
  {
    dest: '北京',
    days: 3,
    tag: '文化古都',
    plan: [
      {
        theme: '城市初探',
        summary: '天安门、胡同与小吃',
        acts: [
          { slot: '上午', name: '天安门广场 · 故宫', desc: '门票 60 元，需提前预约，游览约 4 小时' },
          { slot: '下午', name: '南锣鼓巷 · 胡同漫步', desc: '免费，感受老北京胡同文化' },
          { slot: '晚上', name: '王府井小吃街', desc: '人均 80 元，推荐卤煮与炸酱面' }
        ]
      },
      {
        theme: '长城壮阔',
        summary: '八达岭与奥体之夜',
        acts: [
          { slot: '上午', name: '八达岭长城', desc: '门票 40 元，建议早出发避开人流' },
          { slot: '下午', name: '鸟巢 · 水立方外观', desc: '免费外观，拍照打卡' },
          { slot: '晚上', name: '簋街夜市', desc: '人均 100 元，麻辣小龙虾' }
        ]
      },
      {
        theme: '皇家园林',
        summary: '颐和园与前门收官',
        acts: [
          { slot: '上午', name: '颐和园', desc: '门票 30 元，游昆明湖' },
          { slot: '下午', name: '圆明园遗址', desc: '门票 25 元，历史参观' },
          { slot: '晚上', name: '前门大街', desc: '免费，夜景与老字号' }
        ]
      }
    ]
  },
  {
    dest: '成都',
    days: 3,
    tag: '慢生活',
    plan: [
      {
        theme: '熊猫与锦里',
        summary: '熊猫基地与古街火锅',
        acts: [
          { slot: '上午', name: '成都大熊猫繁育研究基地', desc: '门票 55 元，建议 8 点前到' },
          { slot: '下午', name: '宽窄巷子', desc: '免费，成都城市名片' },
          { slot: '晚上', name: '锦里古街 · 火锅', desc: '人均 120 元，地道牛油火锅' }
        ]
      },
      {
        theme: '文化漫游',
        summary: '武侯祠与鹤鸣茶社',
        acts: [
          { slot: '上午', name: '武侯祠', desc: '门票 50 元，三国文化' },
          { slot: '下午', name: '人民公园 · 鹤鸣茶社', desc: '一杯盖碗茶，体验慢生活' },
          { slot: '晚上', name: '玉林路小酒馆', desc: '人均 60 元，市井夜生活' }
        ]
      },
      {
        theme: '自然与街区',
        summary: '青城山与建设路',
        acts: [
          { slot: '上午', name: '青城山（前山）', desc: '门票 80 元，道教名山' },
          { slot: '下午', name: '都江堰景区', desc: '门票 80 元，世界文化遗产' },
          { slot: '晚上', name: '建设路小吃街', desc: '人均 50 元，甜水面与兔头' }
        ]
      }
    ]
  },
  {
    dest: '上海',
    days: 2,
    tag: '都市摩登',
    plan: [
      {
        theme: '外滩与历史',
        summary: '万国建筑与陆家嘴夜景',
        acts: [
          { slot: '上午', name: '外滩万国建筑群', desc: '免费，欣赏百年建筑' },
          { slot: '下午', name: '南京东路步行街', desc: '免费，购物与老字号' },
          { slot: '晚上', name: '陆家嘴 · 三件套夜景', desc: '免费，登中心可选 180 元' }
        ]
      },
      {
        theme: '文艺漫步',
        summary: '武康路与黄浦江游船',
        acts: [
          { slot: '上午', name: '武康路 · 老洋房', desc: '免费，网红梧桐街道' },
          { slot: '下午', name: '田子坊', desc: '免费，弄堂创意街区' },
          { slot: '晚上', name: '黄浦江游船', desc: '船票 120 元，两岸夜景' }
        ]
      }
    ]
  }
]

const demoIdx = ref(0)
const dayIdx = ref(0)
const currentDemo = ref<Demo>(demos[0])
const currentDay = ref<DemoDay>(demos[0].plan[0])

function pickDemo(i: number) {
  demoIdx.value = i
  dayIdx.value = 0
  currentDemo.value = demos[i]
  currentDay.value = demos[i].plan[0]
}

function prevDay() {
  if (dayIdx.value > 0) {
    dayIdx.value--
    currentDay.value = currentDemo.value.plan[dayIdx.value]
  }
}
function nextDay() {
  if (dayIdx.value < currentDemo.value.plan.length - 1) {
    dayIdx.value++
    currentDay.value = currentDemo.value.plan[dayIdx.value]
  }
}

/**
 * 时段 → 视觉标识。
 *
 * 行程单的可读性主要靠「一眼看出这是上午还是晚上」，
 * 所以给每个时段配图标与语义色，而不是只写两个字。
 */
const SLOT_META: Record<string, { icon: string; tone: string }> = {
  上午: { icon: 'sun', tone: 'am' },
  下午: { icon: 'camera', tone: 'pm' },
  晚上: { icon: 'moon', tone: 'night' }
}
function slotMeta(slot: string) {
  return SLOT_META[slot] ?? { icon: 'clock', tone: 'am' }
}

/**
 * 从活动名称与描述里识别类型（景点 / 美食 / 交通）。
 *
 * 示例数据是静态文案、没有结构化字段，故用关键词判断；
 * 识别不到就不显示标签——宁缺毋滥，不为了凑标签而误标。
 */
function actKind(name: string, desc: string): { label: string; tone: string } | null {
  const text = name + desc
  if (/火锅|小吃|美食|餐厅|茶社|酒馆|面|菜/.test(text)) return { label: '美食', tone: 'food' }
  if (/车|高铁|航班|机场|地铁|游船/.test(text)) return { label: '交通', tone: 'move' }
  if (/长城|故宫|园林|景区|博物馆|遗址|街区|巷子|广场|外滩|基地|山|楼/.test(text)) {
    return { label: '景点', tone: 'spot' }
  }
  return null
}

/* ---------------- 产品演示：进入视口后播放打字机 ---------------- */
const demoEl = ref<HTMLElement | null>(null)
const demoPlayed = ref(false)
const demoOutro = '生成完毕，行程已保存到账户'
const demoOutroShown = ref('')
/** 演示区定时器：卸载时统一清理，避免离开首页后仍在空转 */
const demoTimers: number[] = []

function playDemo() {
  if (demoPlayed.value) return
  demoPlayed.value = true

  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  if (reduce) {
    demoOutroShown.value = demoOutro
    return
  }

  let i = 0
  const timer = window.setInterval(() => {
    i += 1
    demoOutroShown.value = demoOutro.slice(0, i)
    if (i >= demoOutro.length) window.clearInterval(timer)
  }, 55)
  demoTimers.push(timer)
}

/* ---------------- 使用流程 ---------------- */
const steps = [
  { no: '01', title: '描述你的旅行', desc: '说出目的地、天数与预算，不必整理格式，AI 会听懂你的意思。' },
  { no: '02', title: '实时数据准备', desc: '车票、天气与住宿在后台自动查询核对，数据真实可追溯。' },
  { no: '03', title: '日程落地成稿', desc: '按天生成的行程卡片，随时增删调整，一键保存到账户。' }
]

const activeStep = ref(0)
let flowTimer: number | null = null

function pickStep(i: number) {
  activeStep.value = i
  stopFlow()
}
function stopFlow() {
  if (flowTimer !== null) {
    window.clearInterval(flowTimer)
    flowTimer = null
  }
}

/* ---------------- 滚动入场 ---------------- */
let io: IntersectionObserver | null = null
let demoIo: IntersectionObserver | null = null

onMounted(() => {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

  io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add('in')
          io?.unobserve(e.target)
        }
      }
    },
    { threshold: 0.1 }
  )
  document.querySelectorAll('.rv').forEach((el) => io?.observe(el))

  // 打字机只在演示区可见时播放——首屏外提前跑完就失去意义了
  if (demoEl.value) {
    demoIo = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            playDemo()
            demoIo?.disconnect()
          }
        }
      },
      { threshold: 0.25 }
    )
    demoIo.observe(demoEl.value)
  }

  if (!reduce) {
    flowTimer = window.setInterval(() => {
      activeStep.value = (activeStep.value + 1) % steps.length
    }, 3000)
  }
})

onUnmounted(() => {
  io?.disconnect()
  demoIo?.disconnect()
  stopFlow()
  demoTimers.forEach((t) => window.clearInterval(t))
  demoTimers.length = 0
})
</script>

<template>
  <AppNavbar />

  <main id="main" tabindex="-1" class="home">
    <!-- ==================== Hero：左文右景 ==================== -->
    <section class="hero">
      <div class="hero__bg" aria-hidden="true">
        <span class="hero__glow hero__glow--a"></span>
        <span class="hero__glow hero__glow--b"></span>
      </div>

      <div class="container hero__inner">
        <div class="hero__copy">
          <p class="hero__badge" style="--d: 0ms">
            <span class="hero__badge-dot"></span>
            准备好出发了吗？AI 正在等你的目的地
          </p>

          <h1 class="hero__title" style="--d: 90ms">
            一句话，生成<br />
            <span class="grad-text">可执行的旅行日程</span>
          </h1>

          <p class="hero__lead" style="--d: 180ms">
            说出目的地、天数与预算，车票与天气实时替你查好，
            最后落成一份按天排布、随时可改的行程。
          </p>

          <div class="hero__cta" style="--d: 270ms">
            <RouterLink :to="startHref()" class="btn btn-primary btn--lg">
              开始规划旅程
              <TravelIcon name="arrow-right" :size="17" />
            </RouterLink>
            <a href="#demo" class="btn btn-ghost btn--lg">
              <TravelIcon name="compass" :size="17" />
              看看行程长什么样
            </a>
          </div>

          <!-- 可点击示例：点了直接带着这句话进入对话，省掉自己组织语言的成本 -->
          <div class="hero__example" style="--d: 360ms">
            <span class="hero__example-label">试试这样说</span>
            <div class="hero__chips">
              <button
                v-for="ex in heroExamples"
                :key="ex.text"
                type="button"
                class="chip-say"
                @click="useExample(ex.text)"
              >
                <TravelIcon :name="ex.icon" :size="14" />
                <span>{{ ex.text }}</span>
                <TravelIcon name="arrow-right" :size="13" class="chip-say__go" />
              </button>
            </div>
          </div>
        </div>

        <!-- 右侧：示例行程卡片。
             内容是静态示例（车次与票价均为写死的示范数据），
             故这里必须标「示例」而不是「实时」——标成实时会让用户
             以为这是此刻查到的真实车次，属于误导。 -->
        <div class="hero__art" style="--d: 180ms">
          <div class="hero__card">
            <div class="hero__card-head">
              <TravelIcon name="map" :size="16" />
              <span>广州 → 北京</span>
              <span class="hero__card-chip">示例</span>
            </div>
            <div class="hero__card-route">
              <span class="hero__card-city">
                <b>广州南</b>
                <i>08:00</i>
              </span>
              <span class="hero__card-line">
                <em></em>
                <TravelIcon name="plane" :size="15" />
                <em></em>
              </span>
              <span class="hero__card-city hero__card-city--end">
                <b>北京西</b>
                <i>13:24</i>
              </span>
            </div>
            <div class="hero__card-rows">
              <div class="hero__card-row">
                <span><TravelIcon name="train" :size="14" />车次</span>
                <strong>G77 · 二等座 ¥553</strong>
              </div>
              <div class="hero__card-row">
                <span><TravelIcon name="sun" :size="14" />天气</span>
                <strong>晴 · 12~22°C</strong>
              </div>
              <div class="hero__card-row">
                <span><TravelIcon name="passport" :size="14" />预算</span>
                <strong>¥2800 / ¥3000</strong>
              </div>
            </div>
            <div class="hero__card-bar"><i></i></div>
            <p class="hero__card-foot">示例行程 · 实际车次与票价以对话中查询结果为准</p>
          </div>
        </div>
      </div>

      <!-- 信任数据条 -->
      <div class="container">
        <div class="stats rv">
          <div v-for="s in stats" :key="s.label" class="stat">
            <b>{{ s.num }}</b>
            <span>{{ s.label }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 核心能力 ==================== -->
    <section id="features" class="section">
      <div class="container">
        <div class="section-head rv">
          <p class="eyebrow">核心能力</p>
          <h2>让规划这件事，变得省心</h2>
          <p>从一句需求到一份可落地的行程，每个环节都有对应的能力支撑。</p>
        </div>

        <div class="cards">
          <article v-for="f in features" :key="f.title" class="card rv">
            <span class="card__ic"><FeatureIcon :name="f.icon" /></span>
            <h3>
              {{ f.title }}
              <span class="card__tag">{{ f.tag }}</span>
            </h3>
            <p>{{ f.desc }}</p>
            <!-- 悬停时浮出的补充说明，替「了解更多」提供实际信息量 -->
            <p class="card__more">
              <TravelIcon name="arrow-right" :size="13" />
              {{ f.more }}
            </p>
          </article>
        </div>
      </div>
    </section>

    <!-- ==================== 产品演示 ==================== -->
    <section id="demo" class="section section--alt">
      <div class="container">
        <div class="section-head rv">
          <p class="eyebrow">产品演示</p>
          <h2>真实对话长这样</h2>
          <p>思考过程、工具调用与正文实时呈现，等待不再漫长。</p>
        </div>

        <div ref="demoEl" class="app-mock rv">
          <div class="mock-bar">
            <span class="d r"></span><span class="d y"></span><span class="d g"></span>
            <span class="u">voyage.ai — 对话</span>
          </div>

          <div class="mock-frame">
            <aside class="mock-side">
              <div class="s-item on">北京三日游行程规划</div>
              <div class="s-item">成都慢生活攻略</div>
              <div class="s-item">周末上海两日游</div>
              <div class="s-user"><span class="av"></span>旅行者</div>
            </aside>

            <div class="mock-chat">
              <div class="mu">
                <div class="b">帮我规划北京 3 日游，预算 3000，坐高铁出发</div>
              </div>

              <div class="ma">
                <div class="mb reason">正在分析目的地要素：天气、交通、住宿偏好…</div>

                <div class="mb tool">
                  <span class="k">工具</span>
                  已查询车次 <span class="g">G77</span> · 已查询 <span class="g">北京 3 天天气</span>
                </div>

                <div class="mb">
                  <span class="k">北京 3 日游方案</span> — 预算 ¥2800，高铁往返，市中心酒店两晚，含故宫与长城。
                </div>

                <div class="mock-itin">
                  <div class="mi">
                    <span class="mi-d">Day 1</span><b>故宫 · 胡同</b><span>天安门广场与南锣鼓巷</span>
                  </div>
                  <div class="mi">
                    <span class="mi-d">Day 2</span><b>八达岭长城</b><span>早出发避开人流</span>
                  </div>
                  <div class="mi">
                    <span class="mi-d">Day 3</span><b>颐和园 · 圆明园</b><span>皇家园林收尾</span>
                  </div>
                </div>

                <div class="mb mono">
                  {{ demoOutroShown }}<span v-if="demoPlayed" class="caret"></span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 示例行程 ==================== -->
    <section id="itinerary" class="section">
      <div class="container">
        <div class="section-head rv">
          <p class="eyebrow">示例行程</p>
          <h2>看看 AI 安排的每一天</h2>
          <p>按天与时段组织的行程，左右切换查看完整安排。</p>
        </div>

        <div class="timeline">
          <!-- 城市 Tab：选中态用实心填充，比下划线更醒目；窄屏可横向滑动 -->
          <div class="timeline__dests rv" role="tablist" aria-label="示例目的地">
            <button
              v-for="(d, i) in demos"
              :key="d.dest"
              type="button"
              role="tab"
              :aria-selected="i === demoIdx"
              :class="{ on: i === demoIdx }"
              @click="pickDemo(i)"
            >
              <b>{{ d.dest }}</b>
              <i>{{ d.days }} 天</i>
            </button>
          </div>

          <div class="timeline__nav rv">
            <div class="timeline__dest">
              {{ currentDemo.dest }}
              <span>{{ currentDemo.days }} 日游 · {{ currentDemo.tag }}</span>
            </div>
            <div class="timeline__arrows">
              <button class="tl-arrow" type="button" aria-label="前一天" :disabled="dayIdx === 0" @click="prevDay">
                <TravelIcon name="arrow-left" :size="17" />
              </button>
              <span class="tl-count">Day {{ dayIdx + 1 }} / {{ currentDemo.plan.length }}</span>
              <button
                class="tl-arrow"
                type="button"
                aria-label="后一天"
                :disabled="dayIdx === currentDemo.plan.length - 1"
                @click="nextDay"
              >
                <TravelIcon name="arrow-right" :size="17" />
              </button>
            </div>
          </div>

          <div class="timeline__card rv">
            <div class="timeline__head">
              <div>
                <div class="timeline__day">Day {{ dayIdx + 1 }}</div>
                <div class="timeline__theme">{{ currentDay.theme }} · {{ currentDay.summary }}</div>
              </div>
              <div class="timeline__ind">
                <i v-for="(_, i) in currentDemo.plan" :key="i" :class="{ on: i === dayIdx }"></i>
              </div>
            </div>

            <ul class="timeline__list">
              <li v-for="(a, i) in currentDay.acts" :key="i">
                <!-- 时段：图标 + 中文标签，让行程单更像真实的时刻表 -->
                <span class="timeline__slot" :class="`slot--${slotMeta(a.slot).tone}`">
                  <TravelIcon :name="slotMeta(a.slot).icon" :size="13" />
                  {{ a.slot }}
                </span>
                <div class="timeline__act">
                  <p class="act-name">
                    <b>{{ a.name }}</b>
                    <span v-if="actKind(a.name, a.desc)" class="act-kind" :class="`kind--${actKind(a.name, a.desc)!.tone}`">
                      {{ actKind(a.name, a.desc)!.label }}
                    </span>
                  </p>
                  <span>{{ a.desc }}</span>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 使用流程 ==================== -->
    <section id="flow" class="section section--alt">
      <div class="container">
        <div class="section-head rv">
          <p class="eyebrow">使用流程</p>
          <h2>三步，从想法到可执行</h2>
          <p>没有复杂的表单，也没有需要背诵的指令格式。</p>
        </div>

        <div class="flow">
          <!-- 左侧步骤：带连接线的纵向时间线 -->
          <div class="flow__side rv">
            <button
              v-for="(s, i) in steps"
              :key="s.no"
              type="button"
              class="fs-item"
              :class="{ on: i === activeStep }"
              @click="pickStep(i)"
            >
              <span class="fs-no">{{ s.no }}</span>
              <span class="fs-body">
                <b>{{ s.title }}</b>
                <span>{{ s.desc }}</span>
              </span>
            </button>
          </div>

          <!-- 右侧预览：静态示意，随选中步骤切换内容，避免大片留白 -->
          <div class="flow__preview rv">
            <!-- 步骤 1：用户输入 -->
            <div v-if="activeStep === 0" class="pv">
              <p class="pv-label">Step 01 · 你说</p>
              <div class="pv-inp">
                <TravelIcon name="chat" :size="15" />
                <span>帮我规划北京 3 日游，预算 3000</span>
                <span class="pv-send"><TravelIcon name="arrow-right" :size="14" /></span>
              </div>
              <div class="pv-chat">
                <div class="pv-hint">不必写得工整，地名、天数、预算说到就行</div>
              </div>
            </div>

            <!-- 步骤 2：数据核对（静态示意） -->
            <div v-else-if="activeStep === 1" class="pv">
              <p class="pv-label">Step 02 · 我查</p>
              <ul class="pv-checks">
                <li>
                  <span class="pv-dot ok"></span>
                  <b>车次</b><span>G77 二等座 ¥553 · 余票充足</span>
                </li>
                <li>
                  <span class="pv-dot ok"></span>
                  <b>天气</b><span>北京 3 天晴，12~22°C</span>
                </li>
                <li>
                  <span class="pv-dot ok"></span>
                  <b>住宿</b><span>市中心两晚，含早 ¥1160</span>
                </li>
              </ul>
              <!-- 这里说的是「产品在对话中会怎么做」，不是指上方卡片本身是实时数据。
                   卡片是静态示意，故用「对话中」限定范围，避免读成「此刻查到的结果」。 -->
              <p class="pv-foot">对话中的车次与天气均来自实时查询，不是模型编造</p>
            </div>

            <!-- 步骤 3：行程成稿 -->
            <div v-else class="pv">
              <p class="pv-label">Step 03 · 成稿</p>
              <div class="plan-mock">
                <div class="plan-head">
                  <span>北京 · 3 日游</span>
                  <span class="plan-edit"><TravelIcon name="edit" :size="13" />编辑</span>
                </div>
                <div class="plan-day open">
                  <div class="pd-head"><span class="pd-no">DAY 1</span><span class="pd-t">城市初探</span></div>
                  <div class="pd-slots"><i>上午</i>天安门广场 · 故宫<br /><i>下午</i>南锣鼓巷 · 胡同漫步</div>
                </div>
                <div class="plan-day">
                  <div class="pd-head"><span class="pd-no">DAY 2</span><span class="pd-t">长城壮阔</span></div>
                </div>
                <div class="plan-day">
                  <div class="pd-head"><span class="pd-no">DAY 3</span><span class="pd-t">皇家园林</span></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== CTA ==================== -->
    <section class="cta-wrap">
      <div class="container">
        <div class="cta rv">
          <p class="eyebrow eyebrow--plain cta__eyebrow">Get Started</p>
          <h2>下一站，交给我们规划</h2>
          <p>登录后即可与 Voyage AI 对话，生成你的第一份结构化行程。</p>
          <RouterLink :to="startHref()" class="btn btn-primary btn--lg cta__btn">
            开启旅程
            <TravelIcon name="arrow-right" :size="17" />
          </RouterLink>
        </div>
      </div>
    </section>
  </main>

  <AppFooter />
</template>

<style scoped>
.home { position: relative; z-index: 1; }

/* ==================== Hero ==================== */
.hero {
  position: relative;
  padding: 64px 0 0;
  overflow: hidden;
}

.hero__bg { position: absolute; inset: 0; pointer-events: none; }

.hero__glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
}
.hero__glow--a {
  width: 620px; height: 460px;
  top: -180px; left: -120px;
  background: radial-gradient(circle, rgba(37, 99, 235, 0.15), transparent 68%);
}
.hero__glow--b {
  width: 560px; height: 420px;
  top: -140px; right: -100px;
  background: radial-gradient(circle, rgba(14, 165, 233, 0.13), transparent 68%);
}

.hero__inner {
  position: relative;
  display: grid;
  grid-template-columns: 1.06fr 0.94fr;
  gap: 56px;
  align-items: center;
  padding-bottom: 40px;
}

/* 首屏错峰入场：一次性编排好的序列比零散的微动效更有仪式感 */
.hero__copy > *,
.hero__art {
  opacity: 0;
  transform: translateY(16px);
  animation: heroIn 0.7s cubic-bezier(0.2, 0.7, 0.2, 1) forwards;
  animation-delay: var(--d, 0ms);
}
@keyframes heroIn {
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .hero__copy > *, .hero__art { opacity: 1; transform: none; animation: none; }
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--text2);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 14px;
  box-shadow: var(--shadow-sm);
}
.hero__badge-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 3px rgba(72, 187, 120, 0.18);
}

.hero__title {
  margin-top: 22px;
  font-size: clamp(2.1rem, 4.4vw, 3.25rem);
  font-weight: 800;
  line-height: 1.14;
  letter-spacing: -0.03em;
}

.hero__lead {
  margin-top: 18px;
  font-size: 1.02rem;
  line-height: 1.75;
  color: var(--text2);
  max-width: 33em;
  font-weight: 400;
}

.hero__cta { display: flex; gap: 12px; margin-top: 30px; flex-wrap: wrap; }

/* ---------- 示例胶囊 ---------- */
.hero__example { margin-top: 30px; }
.hero__example-label {
  display: block;
  font-size: 0.76rem;
  color: var(--text3);
  margin-bottom: 10px;
  letter-spacing: 0.02em;
}
.hero__chips { display: flex; flex-wrap: wrap; gap: 9px; }

.chip-say {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text2);
  font-size: 0.83rem;
  box-shadow: var(--shadow-sm);
  transition: transform 0.22s cubic-bezier(0.2, 0.7, 0.2, 1),
              border-color 0.22s, color 0.22s, box-shadow 0.22s;
}
.chip-say :deep(svg) { color: var(--prim); flex-shrink: 0; }
.chip-say__go {
  opacity: 0;
  transform: translateX(-4px);
  transition: opacity 0.22s, transform 0.22s;
}
.chip-say:hover {
  transform: translateY(-2px);
  border-color: var(--blue-300);
  color: var(--text);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.13);
}
.chip-say:hover .chip-say__go { opacity: 1; transform: none; }
.chip-say:active { transform: translateY(0); }

/* ---------- 右侧示例卡片 ---------- */
.hero__art { position: relative; }
.hero__card {
  position: relative;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  padding: 22px;
  box-shadow: 0 24px 60px rgba(37, 99, 235, 0.13);
  animation: cardFloat 6s ease-in-out infinite;
}
@keyframes cardFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}
@media (prefers-reduced-motion: reduce) {
  .hero__card { animation: none; }
}

.hero__card-head {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 0.9rem;
  font-weight: 650;
  color: var(--text);
  padding-bottom: 14px;
  border-bottom: 1px solid var(--hairline);
}
.hero__card-head :deep(svg) { color: var(--prim); }

/* 「示例」徽标：用中性的暖金点缀而非绿色——
   绿色传达「在线 / 正常」，用在「这是示例数据」上语义不对 */
.hero__card-chip {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--gold-600);
  background: var(--gold-soft);
  padding: 3px 9px;
  border-radius: 999px;
}

.hero__card-route {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 14px;
  padding: 18px 0 16px;
}
.hero__card-city { display: flex; flex-direction: column; gap: 3px; }
.hero__card-city b { font-size: 0.94rem; font-weight: 700; }
.hero__card-city i { font-style: normal; font-size: 0.74rem; color: var(--text3); font-family: var(--mono); }
.hero__card-city--end { text-align: right; }

.hero__card-line { display: flex; align-items: center; gap: 8px; color: var(--prim); }
.hero__card-line em {
  flex: 1;
  height: 1px;
  background: repeating-linear-gradient(90deg, var(--blue-300) 0 4px, transparent 4px 8px);
}
.hero__card-line :deep(svg) { transform: rotate(45deg); }

.hero__card-rows { display: flex; flex-direction: column; gap: 10px; }
.hero__card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.84rem;
}
.hero__card-row span { display: inline-flex; align-items: center; gap: 7px; color: var(--text3); }
.hero__card-row strong { font-weight: 650; color: var(--text); }

.hero__card-bar {
  margin-top: 16px;
  height: 5px;
  border-radius: 999px;
  background: var(--surface-soft);
  overflow: hidden;
}
.hero__card-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--grad);
  /* 进度条来回推进：暗示「正在生成」，比固定长度更有生命感 */
  animation: barAdvance 2.8s ease-in-out infinite;
}
@keyframes barAdvance {
  0% { width: 24%; }
  50% { width: 82%; }
  100% { width: 24%; }
}
@media (prefers-reduced-motion: reduce) {
  .hero__card-bar i { animation: none; width: 68%; }
}

.hero__card-foot {
  margin-top: 10px;
  font-size: 0.76rem;
  color: var(--text3);
}

/* ---------- 信任数据条 ---------- */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  padding: 22px 0;
  border-top: 1px solid var(--hairline);
}
.stat { display: flex; flex-direction: column; gap: 4px; }
.stat b {
  font-family: var(--font-display);
  font-size: 1.28rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--text);
}
.stat span { font-size: 0.8rem; color: var(--text3); }

/* ==================== 通用区块 ==================== */
.section { padding: 88px 0; }
.section--alt { background: var(--bg2); }

.section-head { max-width: 44em; margin-bottom: 44px; }
.eyebrow {
  display: inline-block;
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--prim);
  margin-bottom: 12px;
}
.eyebrow--plain { color: var(--text3); }
.section-head h2 {
  font-size: clamp(1.55rem, 2.8vw, 2.15rem);
  font-weight: 800;
  letter-spacing: -0.025em;
}
.section-head > p:last-child {
  margin-top: 14px;
  font-size: 0.98rem;
  color: var(--text2);
  line-height: 1.75;
  font-weight: 400;
}

/* ---------- 滚动入场 ---------- */
.rv {
  opacity: 0;
  transform: translateY(22px);
  transition: opacity 0.7s cubic-bezier(0.2, 0.7, 0.2, 1),
              transform 0.7s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.rv.in { opacity: 1; transform: none; }
@media (prefers-reduced-motion: reduce) {
  .rv { opacity: 1; transform: none; transition: none; }
}

/* ==================== 核心能力卡片 ==================== */
.cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
}
.card {
  position: relative;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  padding: 24px 22px;
  box-shadow: var(--shadow-sm);
  transition: transform 0.24s cubic-bezier(0.2, 0.7, 0.2, 1),
              box-shadow 0.24s, border-color 0.24s;
  overflow: hidden;
}
.card::before {
  /* 顶部渐变细线：悬停时展开，给卡片一个「被点亮」的信号 */
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--grad);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.32s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 18px 40px rgba(37, 99, 235, 0.13);
  border-color: var(--blue-200);
}
.card:hover::before { transform: scaleX(1); }

.card__ic {
  display: grid;
  place-items: center;
  width: 42px; height: 42px;
  border-radius: 12px;
  background: var(--primary-soft);
  color: var(--prim);
  margin-bottom: 16px;
  transition: background-color 0.24s, color 0.24s;
}
.card:hover .card__ic { background: var(--grad); color: #fff; }

.card h3 {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 1.02rem;
  font-weight: 700;
  margin-bottom: 9px;
}
.card__tag {
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--prim);
  background: var(--primary-soft);
  padding: 2px 8px;
  border-radius: 6px;
  letter-spacing: 0.02em;
}
.card > p {
  font-size: 0.88rem;
  line-height: 1.7;
  color: var(--text2);
}

/* 补充说明默认收起，悬停时展开——不占静态版面的空间 */
.card__more {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 0;
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  font-size: 0.79rem;
  color: var(--prim);
  transition: max-height 0.3s ease, opacity 0.24s ease, margin-top 0.3s ease;
}
.card:hover .card__more { max-height: 40px; opacity: 1; margin-top: 12px; }

/* ==================== 产品演示 ==================== */
.app-mock {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  overflow: hidden;
  box-shadow: var(--shadow);
}
.mock-bar {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 11px 15px;
  background: var(--panel2);
  border-bottom: 1px solid var(--hairline);
}
.mock-bar .d { width: 10px; height: 10px; border-radius: 50%; }
.mock-bar .r { background: #ff5f57; }
.mock-bar .y { background: #febc2e; }
.mock-bar .g { background: #28c840; }
.mock-bar .u {
  margin-left: 12px;
  font-size: 0.76rem;
  color: var(--text3);
  font-family: var(--mono);
}

.mock-frame { display: grid; grid-template-columns: 208px 1fr; }

.mock-side {
  border-right: 1px solid var(--hairline);
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--panel2);
}
.s-item {
  padding: 9px 11px;
  border-radius: 9px;
  font-size: 0.83rem;
  color: var(--text2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.s-item.on { background: var(--panel); color: var(--text); font-weight: 600; box-shadow: var(--shadow-sm); }
.s-user {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 11px;
  font-size: 0.83rem;
  color: var(--text2);
  border-top: 1px solid var(--hairline);
}
.s-user .av {
  width: 24px; height: 24px; border-radius: 50%;
  background: var(--grad);
}

.mock-chat { padding: 20px; display: flex; flex-direction: column; gap: 14px; }

.mu { display: flex; justify-content: flex-end; }
.mu .b {
  background: var(--grad);
  color: #fff;
  padding: 11px 15px;
  border-radius: 14px 14px 4px 14px;
  font-size: 0.87rem;
  max-width: 78%;
  line-height: 1.6;
  box-shadow: 0 6px 18px var(--glow);
}

.ma { display: flex; flex-direction: column; gap: 10px; }
.mb {
  background: var(--bubble-ai);
  padding: 11px 15px;
  border-radius: 14px 14px 14px 4px;
  font-size: 0.87rem;
  line-height: 1.7;
  color: var(--text2);
  max-width: 88%;
}
.mb .k {
  font-weight: 700;
  color: var(--text);
  margin-right: 4px;
}
.mb .g { color: var(--prim); font-weight: 600; }
.mb.reason { font-style: italic; color: var(--text3); font-size: 0.82rem; }
.mb.tool {
  display: flex;
  align-items: center;
  gap: 8px;
  border-left: 2px solid var(--prim);
  border-radius: 4px 12px 12px 4px;
  background: var(--primary-soft);
  font-size: 0.82rem;
}
.mb.mono { font-family: var(--mono); font-size: 0.8rem; color: var(--text3); }

.caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--prim);
  margin-left: 3px;
  vertical-align: -2px;
  animation: caretBlink 1s steps(1) infinite;
}
@keyframes caretBlink { 50% { opacity: 0; } }

.mock-itin {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 12px;
  border-radius: var(--r-s);
  background: var(--panel2);
  border: 1px solid var(--hairline);
}
.mi {
  display: grid;
  grid-template-columns: 52px auto 1fr;
  align-items: baseline;
  gap: 10px;
  font-size: 0.82rem;
}
.mi-d {
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--prim);
}
.mi b { font-weight: 650; color: var(--text); }
.mi span { color: var(--text3); }

/* ==================== 示例行程 ==================== */
.timeline { display: flex; flex-direction: column; gap: 18px; }

/* 城市 Tab：实心选中态 + 横向可滑动（窄屏不换行、不挤压） */
.timeline__dests {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
}
.timeline__dests button {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text2);
  transition: transform 0.22s, border-color 0.22s, color 0.22s, background-color 0.22s,
              box-shadow 0.22s;
}
.timeline__dests button b { font-size: 0.93rem; font-weight: 700; }
.timeline__dests button i {
  font-style: normal;
  font-size: 0.72rem;
  color: var(--text3);
}
.timeline__dests button:hover {
  transform: translateY(-2px);
  border-color: var(--blue-300);
  color: var(--text);
}
.timeline__dests button.on {
  background: var(--grad);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 10px 24px var(--glow);
}
.timeline__dests button.on i { color: rgba(255, 255, 255, 0.82); }

.timeline__nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.timeline__dest { font-size: 1.05rem; font-weight: 700; }
.timeline__dest span {
  margin-left: 10px;
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--text3);
}
.timeline__arrows { display: flex; align-items: center; gap: 10px; }
.tl-count {
  font-family: var(--mono);
  font-size: 0.78rem;
  color: var(--text3);
  min-width: 74px;
  text-align: center;
}
.tl-arrow {
  width: 34px; height: 34px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text2);
  transition: transform 0.2s, border-color 0.2s, color 0.2s;
}
.tl-arrow:hover:not(:disabled) {
  transform: translateY(-2px);
  border-color: var(--blue-300);
  color: var(--prim);
}
.tl-arrow:disabled { opacity: 0.4; cursor: not-allowed; }

.timeline__card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  padding: 26px 28px;
  box-shadow: var(--shadow-sm);
}
.timeline__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--hairline);
  margin-bottom: 6px;
}
.timeline__day {
  font-family: var(--mono);
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--prim);
}
.timeline__theme { font-size: 1.05rem; font-weight: 700; margin-top: 5px; }
.timeline__ind { display: flex; gap: 5px; padding-top: 5px; }
.timeline__ind i {
  width: 20px; height: 4px;
  border-radius: 999px;
  background: var(--surface-soft);
  transition: background-color 0.24s, width 0.24s;
}
.timeline__ind i.on { background: var(--grad); width: 30px; }

.timeline__list { list-style: none; margin: 0; padding: 0; }
.timeline__list li {
  display: grid;
  grid-template-columns: 68px 1fr;
  gap: 18px;
  padding: 15px 0;
  border-bottom: 1px dashed var(--hairline);
}
.timeline__list li:last-child { border-bottom: none; }

/* 时段标签：图标 + 语义色，行程单要能一眼看出早晚 */
.timeline__slot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: fit-content;
  padding: 6px 0;
  border-radius: 8px;
  font-size: 0.73rem;
  font-weight: 650;
  border: 1px solid transparent;
}
.slot--am { background: var(--blue-50); color: var(--blue-700); border-color: var(--blue-100); }
.slot--pm { background: var(--gold-soft); color: var(--gold-600); border-color: rgba(214, 158, 46, 0.18); }
.slot--night { background: var(--blue-900); color: #fff; border-color: transparent; }

.timeline__act { min-width: 0; }
.act-name { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; margin-bottom: 3px; }
.act-name b { font-size: 0.93rem; font-weight: 650; }
.act-kind {
  font-size: 0.68rem;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 5px;
}
.kind--spot { background: var(--primary-soft); color: var(--prim); }
.kind--food { background: var(--gold-soft); color: var(--gold-600); }
.kind--move { background: rgba(14, 165, 233, 0.12); color: var(--cyan-600); }
.timeline__act > span { font-size: 0.84rem; color: var(--text2); line-height: 1.65; }

/* ==================== 使用流程 ==================== */
.flow { display: grid; grid-template-columns: 300px 1fr; gap: 48px; align-items: start; }

.flow__side { position: relative; display: flex; flex-direction: column; }
/* 连接线：把三步串成一条时间线，而不是三个孤立的按钮 */
.flow__side::before {
  content: '';
  position: absolute;
  left: 13px;
  top: 28px;
  bottom: 28px;
  width: 1px;
  background: linear-gradient(to bottom, var(--blue-200), var(--blue-100));
}

.fs-item {
  position: relative;
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 16px;
  padding: 22px 4px;
  text-align: left;
  border-radius: var(--r-s);
  transition: background-color 0.24s;
}
.fs-item:hover { background: var(--panel); }

.fs-no {
  position: relative;
  z-index: 1;
  width: 28px; height: 28px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--panel);
  border: 1px solid var(--border);
  font-family: var(--mono);
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--text3);
  transition: background-color 0.24s, color 0.24s, border-color 0.24s, transform 0.24s;
}
.fs-item.on .fs-no {
  background: var(--grad);
  border-color: transparent;
  color: #fff;
  transform: scale(1.1);
  box-shadow: 0 6px 16px var(--glow);
}

.fs-body b {
  display: block;
  font-size: 0.96rem;
  font-weight: 700;
  margin-bottom: 6px;
  opacity: 0.5;
  transition: opacity 0.24s;
}
.fs-body span {
  display: block;
  font-size: 0.83rem;
  color: var(--text3);
  line-height: 1.65;
  transition: color 0.24s;
}
.fs-item.on .fs-body b { opacity: 1; }
.fs-item.on .fs-body span { color: var(--text2); }

.flow__preview {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  padding: 34px 32px;
  min-height: 400px;
  display: flex;
  align-items: center;
  box-shadow: var(--shadow);
}
.pv { width: 100%; }
.pv-label {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text3);
  margin-bottom: 22px;
}

.pv-inp {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--panel2);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  padding: 14px 16px;
  font-size: 0.87rem;
  color: var(--text);
}
.pv-inp :deep(svg) { color: var(--prim); flex-shrink: 0; }
.pv-send {
  margin-left: auto;
  width: 30px; height: 30px;
  border-radius: 9px;
  background: var(--grad);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.pv-chat { margin-top: 16px; }
.pv-hint { font-size: 0.82rem; color: var(--text3); }

.pv-checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.pv-checks li {
  display: grid;
  grid-template-columns: 10px 52px 1fr;
  align-items: baseline;
  gap: 12px;
  padding: 13px 15px;
  border-radius: var(--r-s);
  background: var(--panel2);
  border: 1px solid var(--hairline);
  font-size: 0.85rem;
}
.pv-checks b { font-weight: 650; color: var(--text); }
.pv-checks span:last-child { color: var(--text2); }
.pv-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text3); }
.pv-dot.ok { background: var(--success); box-shadow: 0 0 0 3px rgba(72, 187, 120, 0.16); }
.pv-foot { margin-top: 16px; font-size: 0.78rem; color: var(--text3); }

.plan-mock { display: flex; flex-direction: column; gap: 8px; }
.plan-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.9rem;
  font-weight: 700;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--hairline);
  margin-bottom: 4px;
}
.plan-edit {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.76rem;
  font-weight: 500;
  color: var(--prim);
}
.plan-day {
  border: 1px solid var(--hairline);
  border-radius: var(--r-s);
  padding: 12px 14px;
  background: var(--panel2);
}
.plan-day.open { background: var(--panel); border-color: var(--blue-200); }
.pd-head { display: flex; align-items: center; gap: 10px; }
.pd-no {
  font-family: var(--mono);
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--prim);
}
.pd-t { font-size: 0.86rem; font-weight: 650; }
.pd-slots { margin-top: 8px; font-size: 0.81rem; color: var(--text2); line-height: 1.9; }
.pd-slots i {
  display: inline-block;
  width: 34px;
  font-style: normal;
  font-size: 0.72rem;
  color: var(--text3);
}

/* ==================== CTA ====================
   纯文字收尾，不套卡片。
   原来是一张白底卡片（背景 + 边框 + 大圆角 + 阴影），
   与上方「使用流程」区块的卡片堆在一起显得重复，也把收尾做得过重。
   现在只留文字与按钮，靠留白分隔。 */
.cta-wrap {
  /* 上边距：原先为 0，导致与「使用流程」区块贴住（只靠该区块自身
     88px 的下边距撑着，卡片边框一顶上来就显挤）。 */
  padding: 96px 0 120px;
}
.cta {
  text-align: center;
  /* 无背景、无边框、无圆角、无阴影 —— 单纯文字 */
  max-width: 640px;
  margin: 0 auto;
}
.cta__eyebrow { margin-bottom: 14px; }
.cta h2 {
  font-size: clamp(1.7rem, 3.2vw, 2.4rem);
  font-weight: 800;
  letter-spacing: -0.028em;
}
.cta > p {
  margin: 16px auto 0;
  max-width: 34em;
  font-size: 0.98rem;
  color: var(--text2);
  line-height: 1.75;
}
.cta__btn { margin-top: 30px; }

/* ==================== 响应式 ==================== */
@media (max-width: 1024px) {
  .cards { grid-template-columns: repeat(2, 1fr); }
  .flow { grid-template-columns: 1fr; gap: 28px; }
  .flow__side::before { display: none; }
  .flow__side { flex-direction: row; overflow-x: auto; gap: 8px; }
  .fs-item { flex: 0 0 auto; max-width: 260px; padding: 14px 12px; }
}

@media (max-width: 860px) {
  /* Hero 在窄屏改为上下堆叠：文字在上，卡片在下 */
  .hero__inner { grid-template-columns: 1fr; gap: 36px; padding-bottom: 28px; }
  .hero__art { max-width: 460px; }
  .stats { grid-template-columns: repeat(2, 1fr); gap: 20px; }
  .mock-frame { grid-template-columns: 1fr; }
  .mock-side { flex-direction: row; overflow-x: auto; border-right: none; border-bottom: 1px solid var(--hairline); }
  .s-user { display: none; }
  .section { padding: 64px 0; }
}

@media (max-width: 640px) {
  .cards { grid-template-columns: 1fr; }
  .hero__title { font-size: 1.95rem; }
  .hero__cta .btn { width: 100%; }
  .hero__chips { flex-direction: column; align-items: stretch; }
  .chip-say { justify-content: flex-start; }
  .timeline__card { padding: 20px 16px; }
  .timeline__list li { grid-template-columns: 1fr; gap: 8px; }
  .timeline__slot { width: fit-content; padding: 5px 12px; }
  .timeline__nav { flex-direction: column; align-items: flex-start; }
  .flow__preview { padding: 24px 18px; min-height: 340px; }
  /* CTA 已无卡片，只需收紧上下留白（原先的 padding / border-radius 是给卡片用的） */
  .cta-wrap { padding: 64px 0 80px; }
}
</style>
