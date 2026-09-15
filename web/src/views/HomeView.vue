<script setup lang="ts">
/**
 * HomeView · 首页
 * 结构：左文右景 Hero → 数据条 → 能力区(3列) → 产品演示 → 示例行程 → 流程 → 浅色 CTA
 * 色调：冷调（清新蓝主导，暖金仅点缀）
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useUserStore } from '@/stores/user'
import AppNavbar from '@/components/AppNavbar.vue'
import AppFooter from '@/components/AppFooter.vue'
import FeatureIcon from '@/components/FeatureIcon.vue'
import TravelIcon from '@/components/TravelIcon.vue'

const user = useUserStore()

function startHref(): string {
  return user.isLoggedIn ? '/chat' : '/login'
}

/* ---------------- 数据 ---------------- */
const features = [
  {
    icon: 'spark' as const,
    tag: '生成',
    title: 'AI 智能规划',
    desc: '说出目的地、天数与预算，一句话得到完整可执行的行程方案。'
  },
  {
    icon: 'train' as const,
    tag: '实时',
    title: '车次票价查询',
    desc: '车次、票价与余票即时可查，交通信息真实可核验。'
  },
  {
    icon: 'sun' as const,
    tag: '天气',
    title: '天气穿衣建议',
    desc: '出发前自动查询目的地天气，按天气推荐穿着与安排。'
  },
  {
    icon: 'edit' as const,
    tag: '可编辑',
    title: '行程一键调整',
    desc: '按天按时段展示，景点、住宿与美食随时增删并保存。'
  },
  {
    icon: 'layers' as const,
    tag: '稳定',
    title: '多模型保障',
    desc: '接入多个大模型，调用失败自动重试与降级，对话始终稳定。'
  },
  {
    icon: 'chat' as const,
    tag: '流式',
    title: '实时对话体验',
    desc: '思考过程、工具调用与正文实时呈现，等待不再漫长。'
  }
]

/** 信任数据条 */
const stats = [
  { num: '3 步', label: '从需求到成稿' },
  { num: '2 类', label: '实时数据源' },
  { num: '多人', label: 'Agent 协作规划' },
  { num: '随时', label: '可编辑可保存' }
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

  if (!reduce) {
    flowTimer = window.setInterval(() => {
      activeStep.value = (activeStep.value + 1) % steps.length
    }, 3000)
  }
})

onUnmounted(() => {
  io?.disconnect()
  stopFlow()
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
        <!-- 淡地图纹理 -->
        <svg class="hero__map" viewBox="0 0 1200 600" preserveAspectRatio="xMidYMid slice">
          <g fill="none" stroke="rgba(43,108,176,0.09)" stroke-width="1">
            <path d="M0 120 Q 300 60 600 140 T 1200 100" />
            <path d="M0 240 Q 340 180 660 260 T 1200 220" />
            <path d="M0 360 Q 300 300 620 380 T 1200 340" />
            <path d="M0 480 Q 360 420 680 500 T 1200 460" />
            <path d="M200 0 Q 160 300 240 600" />
            <path d="M480 0 Q 440 300 520 600" />
            <path d="M760 0 Q 720 300 800 600" />
            <path d="M1020 0 Q 980 300 1060 600" />
          </g>
          <!-- 航线 -->
          <path
            d="M120 470 C 360 300, 640 300, 940 150"
            fill="none"
            stroke="rgba(49,130,206,0.28)"
            stroke-width="2"
            stroke-dasharray="3 10"
            class="hero__route"
          />
          <circle cx="120" cy="470" r="5" fill="#2b6cb0" opacity="0.5" />
          <circle cx="940" cy="150" r="5" fill="#0ea5e9" opacity="0.6" />
        </svg>
      </div>

      <div class="container hero__inner">
        <div class="hero__copy">
          <p class="hero__badge rv">
            <span class="hero__badge-dot"></span>
            准备好出发了吗？AI 正在等你的目的地
          </p>

          <h1 class="hero__title rv">
            一句话，生成<br />
            <span class="grad-text">可执行的旅行日程</span>
          </h1>

          <p class="hero__lead rv">
            说出目的地、天数与预算，车票与天气实时替你查好，
            最后落成一份按天排布、随时可改的行程。
          </p>

          <div class="hero__cta rv">
            <RouterLink :to="startHref()" class="btn btn-primary btn--lg">
              开始规划旅程
              <TravelIcon name="arrow-right" :size="17" />
            </RouterLink>
            <a href="#demo" class="btn btn-ghost btn--lg">
              <TravelIcon name="compass" :size="17" />
              看看行程长什么样
            </a>
          </div>

          <!-- 一句话示例 -->
          <div class="hero__example rv">
            <span class="hero__example-label">试试这样说</span>
            <div class="hero__example-box">
              <TravelIcon name="chat" :size="15" />
              <span>帮我规划广州到北京的 3 天行程，预算 3000，坐高铁</span>
            </div>
          </div>
        </div>

        <!-- 右侧：轻量旅行视觉 -->
        <div class="hero__art rv" aria-hidden="true">
          <div class="hero__card">
            <div class="hero__card-head">
              <TravelIcon name="map" :size="16" />
              <span>广州 → 北京</span>
              <span class="hero__card-chip">实时</span>
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
            <p class="hero__card-foot">行程生成中 · 已核对 2 项实时数据</p>
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
          </article>
        </div>
      </div>
    </section>

    <!-- ==================== 产品演示（提升为主角） ==================== -->
    <section id="demo" class="section section--alt">
      <div class="container">
        <div class="section-head rv">
          <p class="eyebrow">产品演示</p>
          <h2>真实对话长这样</h2>
          <p>思考过程、工具调用与正文实时呈现，等待不再漫长。</p>
        </div>

        <div class="app-mock rv">
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

                <div class="mb mono">生成完毕，行程已保存到账户<span class="caret"></span></div>
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
          <p>按天与时段组织的行程，前后切换查看完整安排。</p>
        </div>

        <div class="timeline">
          <div class="timeline__dests rv">
            <button
              v-for="(d, i) in demos"
              :key="d.dest"
              type="button"
              :class="{ on: i === demoIdx }"
              @click="pickDemo(i)"
            >
              {{ d.dest }}
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
              <li v-for="a in currentDay.acts" :key="a.name">
                <span class="timeline__slot">{{ a.slot }}</span>
                <span class="timeline__act">
                  <b>{{ a.name }}</b>
                  <span>{{ a.desc }}</span>
                </span>
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
          <h2>三步，把需求变成落地计划</h2>
        </div>

        <div class="flow rv">
          <div class="flow__side">
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

          <div class="flow__preview">
            <!-- 步骤 1 -->
            <div v-if="activeStep === 0" class="pv">
              <div class="pv-label">STEP 01 — 描述需求</div>
              <div class="pv-inp">
                <span>帮我规划北京 3 日游，预算 3000，坐高铁出发</span>
                <span class="pv-send"><TravelIcon name="arrow-right" :size="16" /></span>
              </div>
              <div class="pv-chat">
                <div class="mb reason">正在解析目的地、天数与预算…</div>
              </div>
            </div>

            <!-- 步骤 2 -->
            <div v-else-if="activeStep === 1" class="pv">
              <div class="pv-label">STEP 02 — 实时数据准备</div>
              <div class="qrows">
                <div class="qrow">
                  <span class="qic"><TravelIcon name="train" :size="17" /></span>
                  <span class="qm"><b>查询车次票价</b><span class="qres">G77 二等座 ¥553 · 余票充足</span></span>
                  <span class="qst"></span>
                </div>
                <div class="qrow">
                  <span class="qic"><TravelIcon name="sun" :size="17" /></span>
                  <span class="qm"><b>查询目的地天气</b><span class="qres">北京 3 天晴到多云，12~22°C</span></span>
                  <span class="qst"></span>
                </div>
                <div class="qrow">
                  <span class="qic"><TravelIcon name="passport" :size="17" /></span>
                  <span class="qm"><b>核算预算与住宿</b><span class="qres">市中心两晚 ¥760，总预算 ¥2800</span></span>
                  <span class="qst"></span>
                </div>
              </div>
            </div>

            <!-- 步骤 3 -->
            <div v-else class="pv">
              <div class="pv-label">STEP 03 — 日程落地</div>
              <div class="plan-head">
                <div>
                  <b>北京 3 日游</b>
                  <div class="ph-sub">预算 ¥2800 · 高铁往返 · 已保存</div>
                </div>
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
    </section>

    <!-- ==================== CTA：浅色大卡片 ==================== -->
    <section class="cta-wrap">
      <div class="container">
        <div class="cta rv">
          <span class="cta__deco" aria-hidden="true">
            <svg viewBox="0 0 200 120" fill="none" stroke="rgba(43,108,176,0.18)" stroke-width="1.5">
              <path d="M6 108 C 50 74, 80 60, 120 34 S 180 12, 196 6" stroke-dasharray="4 9" />
              <circle cx="6" cy="108" r="4" fill="rgba(43,108,176,0.28)" stroke="none" />
              <circle cx="196" cy="6" r="4" fill="rgba(14,165,233,0.32)" stroke="none" />
            </svg>
          </span>
          <p class="eyebrow eyebrow--plain cta__eyebrow">Get Started</p>
          <h2>下一站，交给我们规划</h2>
          <p>登录后即可与 Voyage AI 对话，生成你的第一份结构化行程。</p>
          <RouterLink :to="startHref()" class="btn btn-primary btn--lg cta__btn">
            免费开始
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
  background: radial-gradient(circle, rgba(49, 130, 206, 0.14), transparent 68%);
}
.hero__glow--b {
  width: 560px; height: 420px;
  top: -140px; right: -100px;
  background: radial-gradient(circle, rgba(14, 165, 233, 0.13), transparent 68%);
}

.hero__map {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  mask-image: radial-gradient(ellipse 90% 80% at 50% 30%, #000 20%, transparent 78%);
  -webkit-mask-image: radial-gradient(ellipse 90% 80% at 50% 30%, #000 20%, transparent 78%);
}
.hero__route { animation: dashFlow 3s linear infinite; }
@keyframes dashFlow { to { stroke-dashoffset: -52; } }

.hero__inner {
  position: relative;
  display: grid;
  grid-template-columns: 1.06fr 0.94fr;
  gap: 56px;
  align-items: center;
  padding-bottom: 56px;
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 7px 15px;
  border-radius: 999px;
  background: var(--panel);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  font-size: 0.82rem;
  font-weight: 550;
  color: var(--text2);
  margin-bottom: 22px;
}
.hero__badge-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--blue-600);
  box-shadow: 0 0 0 3px var(--primary-soft);
  animation: pulseDot 2s ease-in-out infinite;
}
@keyframes pulseDot {
  50% { box-shadow: 0 0 0 6px rgba(49, 130, 206, 0.06); }
}

.hero__title {
  font-size: clamp(2.1rem, 4.2vw, 3.1rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.18;
}

.hero__lead {
  margin-top: 20px;
  font-size: 1.02rem;
  line-height: 1.8;
  color: var(--text2);
  max-width: 30em;
}

.hero__cta { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 30px; }

/* 一句话示例 */
.hero__example { margin-top: 30px; }

.hero__example-label {
  display: block;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text3);
  margin-bottom: 9px;
}

.hero__example-box {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  border-radius: 999px;
  background: var(--panel);
  border: 1px dashed var(--blue-300);
  color: var(--text2);
  font-size: 0.88rem;
}
.hero__example-box :deep(svg) { color: var(--blue-600); flex-shrink: 0; }

/* ---- 右侧行程卡 ---- */
.hero__art { display: flex; justify-content: center; }

.hero__card {
  width: 100%;
  max-width: 380px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  padding: 22px;
  box-shadow: var(--shadow-lift);
  animation: floaty 7s ease-in-out infinite;
}
@keyframes floaty {
  50% { transform: translateY(-10px); }
}

.hero__card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--hairline);
  font-size: 0.86rem;
  font-weight: 650;
  color: var(--text);
}
.hero__card-head :deep(svg) { color: var(--blue-600); }

.hero__card-chip {
  margin-left: auto;
  font-size: 0.68rem;
  font-weight: 650;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--blue-100);
  color: var(--blue-800);
}
:root[data-theme='dark'] .hero__card-chip { background: rgba(74, 158, 224, 0.16); color: var(--blue-300); }

.hero__card-route {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 0;
}

.hero__card-city { display: flex; flex-direction: column; gap: 2px; }
.hero__card-city b { font-size: 0.95rem; font-weight: 700; }
.hero__card-city i { font-style: normal; font-size: 0.72rem; color: var(--text3); font-family: var(--mono); }
.hero__card-city--end { text-align: right; }

.hero__card-line {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--blue-600);
}
.hero__card-line em {
  flex: 1;
  height: 1px;
  background: repeating-linear-gradient(90deg, var(--blue-300) 0 4px, transparent 4px 9px);
}

.hero__card-rows { display: flex; flex-direction: column; gap: 9px; }

.hero__card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.82rem;
}
.hero__card-row span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text3);
}
.hero__card-row strong { font-weight: 650; color: var(--text); font-size: 0.84rem; }

.hero__card-bar {
  height: 4px;
  margin-top: 16px;
  border-radius: 999px;
  background: var(--slate-200);
  overflow: hidden;
}
:root[data-theme='dark'] .hero__card-bar { background: rgba(255, 255, 255, 0.1); }
.hero__card-bar i {
  display: block;
  height: 100%;
  width: 46%;
  border-radius: 999px;
  background: var(--grad);
  animation: loadbar 2.6s ease-in-out infinite;
}
@keyframes loadbar {
  0% { margin-left: -30%; }
  55%, 100% { margin-left: 88%; }
}

.hero__card-foot {
  margin-top: 10px;
  font-size: 0.72rem;
  color: var(--text3);
  font-family: var(--mono);
}

/* ---- 信任数据条 ---- */
.stats {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  padding: 22px 0;
  border-top: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 0 18px;
  text-align: center;
}
.stat + .stat { border-left: 1px solid var(--hairline); }
.stat b {
  font-size: 1.28rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  background: var(--grad);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.stat span { font-size: 0.79rem; color: var(--text2); }

/* ==================== 通用分区 ==================== */
.section { padding: 88px 0; position: relative; }
.section--alt {
  background: var(--bg2);
  border-top: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
}

.section-head { text-align: center; margin-bottom: 48px; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.section-head h2 { font-size: clamp(1.5rem, 3vw, 2.05rem); font-weight: 800; letter-spacing: -0.026em; }
.section-head p { font-size: 0.95rem; color: var(--text2); line-height: 1.7; max-width: 32em; }

/* ==================== 能力卡片（3 列紧凑） ==================== */
.cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.card {
  padding: 24px 22px 22px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  box-shadow: var(--shadow-sm);
  transition: transform 0.24s cubic-bezier(0.2, 0.7, 0.2, 1), box-shadow 0.24s, border-color 0.24s;
}
.card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lift);
  border-color: var(--blue-300);
}
:root[data-theme='dark'] .card:hover { border-color: var(--blue-700); }

.card__ic {
  width: 40px;
  height: 40px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--blue-50);
  border: 1px solid var(--blue-100);
  color: var(--blue-700);
  margin-bottom: 15px;
  transition: background 0.24s, color 0.24s, transform 0.24s;
}
:root[data-theme='dark'] .card__ic {
  background: rgba(74, 158, 224, 0.12);
  border-color: rgba(74, 158, 224, 0.18);
  color: var(--blue-300);
}
.card:hover .card__ic { background: var(--grad); color: #fff; border-color: transparent; transform: translateY(-2px); }

.card h3 {
  font-size: 0.98rem;
  font-weight: 700;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.card__tag {
  font-size: 0.66rem;
  font-weight: 650;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--panel2);
  border: 1px solid var(--border);
  color: var(--text3);
  letter-spacing: 0.02em;
}

.card p { font-size: 0.85rem; color: var(--text2); line-height: 1.7; }

/* ==================== 产品演示 ==================== */
.app-mock {
  max-width: 880px;
  margin: 0 auto;
  border-radius: var(--r-l);
  overflow: hidden;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-lift);
  background: var(--panel);
}

.mock-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--panel2);
  border-bottom: 1px solid var(--hairline);
}
.mock-bar .d { width: 11px; height: 11px; border-radius: 50%; }
.mock-bar .d.r { background: #ff5f57; }
.mock-bar .d.y { background: #febc2e; }
.mock-bar .d.g { background: #28c840; }
.mock-bar .u { margin-left: 12px; font-size: 0.75rem; color: var(--text3); font-family: var(--mono); }

.mock-frame { display: flex; min-height: 396px; }

.mock-side {
  width: 186px;
  flex-shrink: 0;
  border-right: 1px solid var(--hairline);
  background: var(--panel2);
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.mock-side .s-item {
  padding: 9px 11px;
  border-radius: 9px;
  font-size: 0.76rem;
  color: var(--text3);
}
.mock-side .s-item.on {
  background: var(--panel);
  color: var(--text);
  font-weight: 600;
  border: 1px solid var(--blue-200);
  box-shadow: var(--shadow-sm);
}
:root[data-theme='dark'] .mock-side .s-item.on { border-color: var(--blue-800); }
.mock-side .s-user {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 11px;
  font-size: 0.74rem;
  color: var(--text2);
}
.mock-side .s-user .av { width: 22px; height: 22px; border-radius: 50%; background: var(--grad); }

.mock-chat { flex: 1; padding: 22px 24px; display: flex; flex-direction: column; gap: 13px; min-width: 0; }

.mu { display: flex; justify-content: flex-end; }
.mu .b {
  max-width: 72%;
  background: var(--grad);
  color: #fff;
  border-radius: 14px 14px 4px 14px;
  padding: 10px 14px;
  font-size: 0.84rem;
  line-height: 1.6;
}

.ma { display: flex; flex-direction: column; gap: 9px; }

.mb {
  background: var(--panel2);
  border: 1px solid var(--border);
  border-radius: 4px 14px 14px 14px;
  padding: 10px 14px;
  font-size: 0.84rem;
  line-height: 1.65;
  color: var(--text);
}
.mb.mono { font-family: var(--mono); font-size: 0.77rem; color: var(--text2); }
.mb .k { font-weight: 680; }
.mb .g { color: var(--blue-700); font-weight: 600; }
:root[data-theme='dark'] .mb .g { color: var(--blue-400); }

.mb.reason {
  border-left: 3px solid var(--slate-300);
  background: var(--slate-100);
  color: var(--text2);
  font-size: 0.79rem;
  border-radius: 4px 12px 12px 4px;
}
:root[data-theme='dark'] .mb.reason { background: rgba(255, 255, 255, 0.04); border-left-color: rgba(255, 255, 255, 0.18); }

.mb.tool {
  border-left: 3px solid var(--blue-500);
  background: var(--blue-50);
  color: var(--text2);
  font-size: 0.79rem;
  border-radius: 4px 12px 12px 4px;
}
:root[data-theme='dark'] .mb.tool { background: rgba(74, 158, 224, 0.1); }

.mock-itin { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }
.mi {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-s);
  padding: 11px 12px;
}
.mi .mi-d {
  font-size: 0.64rem;
  color: #fff;
  background: var(--grad);
  display: inline-block;
  padding: 2px 8px;
  border-radius: 20px;
  font-weight: 680;
  margin-bottom: 7px;
}
.mi b { display: block; font-size: 0.81rem; margin-bottom: 3px; }
.mi span { font-size: 0.71rem; color: var(--text3); line-height: 1.5; display: block; }

.caret {
  display: inline-block;
  width: 6px;
  height: 13px;
  background: var(--blue-600);
  border-radius: 2px;
  vertical-align: -2px;
  margin-left: 2px;
  animation: caret 1.1s steps(2) infinite;
}
@keyframes caret { 50% { opacity: 0; } }

/* ==================== 示例行程 ==================== */
.timeline { max-width: 720px; margin: 0 auto; }

.timeline__dests { display: flex; justify-content: center; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }
.timeline__dests button {
  padding: 8px 18px;
  border-radius: 999px;
  font-size: 0.84rem;
  color: var(--text2);
  background: var(--panel);
  border: 1px solid var(--border);
  transition: 0.2s;
}
.timeline__dests button:hover { color: var(--blue-700); border-color: var(--blue-300); }
.timeline__dests button.on {
  background: var(--grad);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 6px 16px var(--glow);
}

.timeline__nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; gap: 16px; }
.timeline__dest { font-size: 1.3rem; font-weight: 800; letter-spacing: -0.02em; }
.timeline__dest span { font-size: 0.79rem; color: var(--text2); font-weight: 500; margin-left: 10px; }

.timeline__arrows { display: flex; gap: 8px; }
.tl-arrow {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--panel);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text2);
  transition: 0.18s;
}
.tl-arrow:hover:not(:disabled) { color: var(--blue-700); border-color: var(--blue-300); transform: translateY(-1px); }
.tl-arrow:disabled { opacity: 0.4; cursor: default; }

.timeline__card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  padding: 28px 30px;
  box-shadow: var(--shadow);
}

.timeline__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--hairline);
  gap: 16px;
}
.timeline__day { font-size: 1.15rem; font-weight: 800; }
.timeline__theme { font-size: 0.79rem; color: var(--text2); margin-top: 3px; }

.timeline__ind { display: flex; gap: 6px; flex-shrink: 0; }
.timeline__ind i {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--slate-200);
  transition: 0.25s;
}
:root[data-theme='dark'] .timeline__ind i { background: rgba(255, 255, 255, 0.14); }
.timeline__ind i.on { background: var(--grad); width: 22px; border-radius: 6px; }

.timeline__list { list-style: none; margin: 0; padding: 0; }
.timeline__list li { display: flex; gap: 16px; padding: 13px 0; }
.timeline__list li + li { border-top: 1px dashed var(--hairline); }

.timeline__slot {
  flex-shrink: 0;
  width: 56px;
  text-align: center;
  font-size: 0.67rem;
  color: var(--blue-700);
  background: var(--blue-50);
  border: 1px solid var(--blue-100);
  border-radius: 7px;
  padding: 6px 0;
  align-self: flex-start;
  font-weight: 680;
}
:root[data-theme='dark'] .timeline__slot {
  color: var(--blue-300);
  background: rgba(74, 158, 224, 0.12);
  border-color: rgba(74, 158, 224, 0.18);
}

.timeline__act { min-width: 0; }
.timeline__act b { font-size: 0.91rem; font-weight: 650; display: block; margin-bottom: 2px; }
.timeline__act span { font-size: 0.8rem; color: var(--text2); line-height: 1.6; }

/* ==================== 使用流程 ==================== */
.flow { display: flex; gap: 48px; align-items: flex-start; }

.flow__side { width: 296px; flex-shrink: 0; }

.fs-item {
  width: 100%;
  display: flex;
  gap: 16px;
  padding: 24px 6px;
  border-bottom: 1px solid var(--hairline);
  text-align: left;
  position: relative;
  transition: 0.3s;
}
.fs-item:first-child { border-top: 1px solid var(--hairline); }
.fs-item::before {
  content: '';
  position: absolute;
  left: -24px;
  top: 0;
  bottom: 0;
  width: 2px;
  border-radius: 2px;
  background: var(--grad);
  opacity: 0;
  transform: scaleY(0.4);
  transition: 0.3s;
}
.fs-item.on::before { opacity: 1; transform: scaleY(1); }

.fs-no {
  font-family: var(--mono);
  font-size: 0.68rem;
  letter-spacing: 0.05em;
  color: var(--text3);
  padding-top: 3px;
  transition: 0.25s;
}
.fs-item.on .fs-no { color: var(--blue-700); }

.fs-body b { font-size: 0.94rem; font-weight: 650; display: block; margin-bottom: 6px; opacity: 0.55; transition: 0.25s; }
.fs-body span { font-size: 0.8rem; color: var(--text3); line-height: 1.6; transition: 0.25s; }
.fs-item.on .fs-body b { opacity: 1; }

.flow__preview {
  flex: 1;
  min-width: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  padding: 40px 38px;
  min-height: 420px;
  display: flex;
  align-items: center;
  box-shadow: var(--shadow);
}

.pv { width: 100%; }
.pv-label {
  font-family: var(--mono);
  font-size: 0.68rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text3);
  margin-bottom: 24px;
}

.pv-inp {
  background: var(--panel2);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  padding: 14px 16px;
  font-size: 0.87rem;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 10px;
}
.pv-send {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--grad);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
  flex-shrink: 0;
}
.pv-chat { margin-top: 18px; display: flex; flex-direction: column; gap: 12px; }

.qrows { display: flex; flex-direction: column; gap: 12px; }
.qrow {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  background: var(--panel2);
  opacity: 0.5;
}
.qrow:nth-child(1) { animation: qfill 0.5s 0.25s forwards; }
.qrow:nth-child(2) { animation: qfill 0.5s 1.05s forwards; }
.qrow:nth-child(3) { animation: qfill 0.5s 1.85s forwards; }
@keyframes qfill { to { opacity: 1; } }

.qic {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: var(--blue-50);
  border: 1px solid var(--blue-100);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--blue-700);
  flex-shrink: 0;
}
:root[data-theme='dark'] .qic {
  background: rgba(74, 158, 224, 0.12);
  border-color: rgba(74, 158, 224, 0.18);
  color: var(--blue-300);
}

.qm { flex: 1; min-width: 0; }
.qm b { font-size: 0.84rem; font-weight: 650; display: block; margin-bottom: 3px; }
.qm .qres { font-size: 0.77rem; color: var(--text2); opacity: 0; display: block; }
.qrow:nth-child(1) .qres { animation: fadein 0.4s 0.75s forwards; }
.qrow:nth-child(2) .qres { animation: fadein 0.4s 1.55s forwards; }
.qrow:nth-child(3) .qres { animation: fadein 0.4s 2.35s forwards; }
@keyframes fadein { to { opacity: 1; } }

.qst { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; background: var(--blue-500); opacity: 0.5; }
.qrow:nth-child(1) .qst { animation: qpulse 0.5s ease-in-out 0s 1, qdone 0.35s ease 0.75s forwards; }
.qrow:nth-child(2) .qst { animation: qpulse 0.5s ease-in-out 0.15s 1, qdone 0.35s ease 1.55s forwards; }
.qrow:nth-child(3) .qst { animation: qpulse 0.5s ease-in-out 0.3s 1, qdone 0.35s ease 2.35s forwards; }
@keyframes qpulse { 0%, 100% { opacity: 0.5; transform: scale(0.92); } 50% { opacity: 1; transform: scale(1.08); } }
@keyframes qdone { to { background: var(--green-500); opacity: 1; box-shadow: 0 0 0 3px rgba(56, 161, 105, 0.14); } }

.plan-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--hairline);
  margin-bottom: 13px;
  gap: 12px;
}
.plan-head b { font-size: 0.98rem; font-weight: 700; display: block; }
.plan-head .ph-sub { font-size: 0.74rem; color: var(--text3); margin-top: 4px; }
.plan-edit {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.74rem;
  color: var(--text2);
  border: 1px solid var(--border);
  padding: 6px 11px;
  border-radius: 8px;
  background: var(--panel2);
  flex-shrink: 0;
}

.plan-day {
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  margin-bottom: 10px;
  overflow: hidden;
  background: var(--panel2);
  transition: 0.25s;
}
.plan-day.open { border-color: var(--blue-300); }
:root[data-theme='dark'] .plan-day.open { border-color: var(--blue-700); }
.pd-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; font-size: 0.84rem; }
.pd-no { font-family: var(--mono); font-size: 0.67rem; color: var(--blue-700); font-weight: 680; }
:root[data-theme='dark'] .pd-no { color: var(--blue-400); }
.pd-head .pd-t { color: var(--text2); font-size: 0.78rem; margin-left: auto; }
.plan-day .pd-slots { display: none; padding: 0 16px 13px; font-size: 0.78rem; color: var(--text2); line-height: 2; }
.plan-day.open .pd-slots { display: block; }
.pd-slots i {
  font-style: normal;
  background: var(--blue-50);
  color: var(--blue-700);
  font-size: 0.65rem;
  padding: 2px 7px;
  border-radius: 6px;
  margin-right: 6px;
  font-weight: 680;
}
:root[data-theme='dark'] .pd-slots i { background: rgba(74, 158, 224, 0.12); color: var(--blue-300); }

/* ==================== CTA（浅色大卡片） ==================== */
.cta-wrap { padding: 20px 0 88px; }

.cta {
  position: relative;
  overflow: hidden;
  max-width: 900px;
  margin: 0 auto;
  padding: 60px 40px;
  text-align: center;
  border-radius: var(--r-l);
  background: linear-gradient(160deg, var(--blue-50), var(--panel) 62%);
  border: 1px solid var(--blue-100);
  box-shadow: var(--shadow-lift);
}
:root[data-theme='dark'] .cta {
  background: linear-gradient(160deg, rgba(74, 158, 224, 0.09), var(--panel) 62%);
  border-color: var(--border);
}

.cta::before {
  content: '';
  position: absolute;
  inset: -30% -10% auto -10%;
  height: 320px;
  background: radial-gradient(ellipse at 50% 100%, rgba(49, 130, 206, 0.12), transparent 68%);
  pointer-events: none;
}

.cta__deco {
  position: absolute;
  right: 34px;
  top: 30px;
  width: 180px;
  height: 108px;
  pointer-events: none;
}
.cta__deco svg { width: 100%; height: 100%; }

.cta__eyebrow { color: var(--blue-700); justify-content: center; position: relative; }
:root[data-theme='dark'] .cta__eyebrow { color: var(--blue-400); }

.cta h2 {
  position: relative;
  font-size: clamp(1.45rem, 2.8vw, 1.9rem);
  font-weight: 800;
  letter-spacing: -0.028em;
  margin: 12px 0 13px;
}
.cta p { position: relative; font-size: 0.92rem; color: var(--text2); margin-bottom: 26px; }
.cta__btn { position: relative; }

/* ==================== 响应式 ==================== */
@media (max-width: 1024px) {
  .hero__inner { gap: 40px; }
  .cards { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 920px) {
  .hero { padding: 40px 0 0; }
  .hero__inner { grid-template-columns: 1fr; gap: 40px; padding-bottom: 40px; }
  .hero__art { order: -1; justify-content: flex-start; }
  .hero__card { max-width: 100%; animation: none; }
  .hero__lead { max-width: none; }
  .stats { grid-template-columns: repeat(2, 1fr); gap: 18px 0; }
  .stat:nth-child(3) { border-left: none; }
  .stat:nth-child(3), .stat:nth-child(4) { border-top: 1px solid var(--hairline); padding-top: 16px; }
  .mock-side { display: none; }
  .mock-itin { grid-template-columns: 1fr; }
  .flow { flex-direction: column; gap: 26px; }
  .flow__side { width: 100%; padding-left: 22px; border-left: 1px solid var(--hairline); }
  .fs-item { padding: 17px 4px; }
  .fs-item::before {
    left: -23px; top: 25px; bottom: auto;
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--slate-200); border: 2px solid var(--border);
    transform: none;
  }
  .fs-item.on::before { background: var(--grad); border-color: transparent; }
  .flow__preview { padding: 26px 20px; min-height: 380px; }
  .section { padding: 68px 0; }
  .section-head { margin-bottom: 36px; }
  .cta { padding: 48px 26px; }
  .cta__deco { display: none; }
}

@media (max-width: 640px) {
  .cards { grid-template-columns: 1fr; }
  .timeline__nav { flex-direction: column; align-items: flex-start; gap: 12px; }
  .timeline__card { padding: 20px 16px; }
  .timeline__slot { width: 46px; font-size: 0.61rem; }
  .hero__title { font-size: 1.92rem; }
  .hero__cta .btn { width: 100%; }
  .hero__example-box { font-size: 0.82rem; }
  .stats { padding: 18px 0; }
  .stat b { font-size: 1.1rem; }
}
</style>
