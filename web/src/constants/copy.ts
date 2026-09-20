/**
 * 情感化文案库
 * 统一「旅行语气」：不说“操作成功”，说“又一条新路线等着你”。
 * 集中管理便于统一调整语气，避免各页面各写一套。
 */

/** 登录/注册页随场景轮换的诗意短句（冷调，轻快） */
export const AUTH_SCENES = [
  {
    key: 'dawn' as const,
    eyebrow: 'Day 01 · 出发',
    title: '清晨的山谷，路正等着你',
    desc: '把目的地告诉 Voyage，剩下的交给它——车次、天气、路线，一路替你查好。'
  },
  {
    key: 'coast' as const,
    eyebrow: 'On the road · 在路上',
    title: '沿着海岸线，慢慢走',
    desc: '不赶时间也没关系。AI 会记住你的节奏，把行程排成你喜欢的密度。'
  },
  {
    key: 'peak' as const,
    eyebrow: 'Above the clouds · 开阔',
    title: '站得高一点，看得远一点',
    desc: '从一句需求到一份完整行程，视野打开之后，选择也变多了。'
  },
  {
    key: 'city' as const,
    eyebrow: 'Arrival · 抵达',
    title: '下一站，是没去过的城市',
    desc: '落地即用的日程，交通与住宿都已核对，只管出发。'
  }
]

/** 表单校验与结果提示：友好、带旅行语气 */
export const AUTH_COPY = {
  emailRequired: '留个邮箱吧，行程单要寄给你',
  emailInvalid: '这个邮箱看起来不太对，再确认一下？',
  passwordRequired: '还差一步，密码还没填',
  passwordShort: '密码至少 8 位，安全一点才能走得更远',
  passwordMismatch: '两次输入的密码不一样，再核对一下',
  codeRequired: '验证码还没填哦',
  usernameRequired: '给自己起个旅行昵称吧',
  usernameLength: '昵称 2-10 个字符，短一点更好记',
  loginSuccess: '欢迎回来，旅程继续',
  /*
   * 注册成功后的提示。刻意**不说「正在带你出发」** ——
   * 注册后不会自动登录，而是切回登录表单让用户自己登一次；
   * 文案若暗示「马上进去」会与随后的界面不符。
   * 语气贴旅行（登船 / 出发），并点出下一步动作。
   */
  registerSuccess: '船舱已备好，请用刚设置的密码登船～',
  codeSent: '验证码已寄出，去邮箱看看',
  resetSuccess: '密码已更新，用新密码继续出发',
  thirdPartySoon: '第三方登录正在打通，先用邮箱出发吧',
  rememberMe: '记住我，下次直接出发'
}

/** 各页面空状态 / 加载态文案 */
export const PAGE_COPY = {
  itinerariesEmptyTitle: '还没有行程',
  itinerariesEmptyDesc: '先在助手里聊出攻略，点一下「提取行程」，这里就会长出你的第一份路线。',
  itinerariesEmptyCta: '去规划第一段旅程',
  itinerariesLoading: '正在翻找你的旅行手账…',
  chatEmptyTitle: '准备好出发了吗？',
  chatEmptyDesc: '说出目的地、天数与预算，Voyage 会替你查好车次与天气，排成可以落地的日程。',
  /*
   * 草稿态（点过「新会话」、还没开口）的问候语。
   *
   * 与 chatEmptyTitle 的分工：
   *   chatEmptyTitle 用于**无会话 / 当天首次**的欢迎屏，是介绍页的开场；
   *   这一句用于老用户点「新会话」后的空白窗 —— 不必再介绍产品，
   *   只需一句「我在听」，让用户知道这个空窗口是等他说话的，而不是坏了。
   */
  chatDraftGreeting: '想去哪儿？说给我听听',
  chatDraftHint: '目的地、天数、预算，写一句就行',
  chatLoading: '正在收拾行囊…',
  profileLoading: '正在读取你的旅行档案…'
}
