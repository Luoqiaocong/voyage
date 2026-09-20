<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useUserStore } from '@/stores/user'
import { canAccessAdmin, roleLabel } from '@/utils/role'
import { useLogout } from '@/composables/useLogout'
import ThemeToggle from '@/components/ThemeToggle.vue'
import TravelIcon from '@/components/TravelIcon.vue'

const user = useUserStore()
const open = ref(false)
const scrolled = ref(false)

/**
 * 导航项配置。
 *
 * ## 为什么未登录时不显示「首页」
 *
 * Logo 本身就是「回首页」的通用入口（这也是用户点它的第一直觉）。
 * 未登录时整条主导航只有「首页」一项，而它指向的正是当前所在的页面 ——
 * 一个占据主导航位置、却只指向当下的链接，读起来像是导航没做完。
 * 未登录时干脆不显示主导航，让首屏的焦点落在右侧的行动按钮上。
 *
 * 已登录时才出现主导航，此时「首页」是**从别的页面回到首页**的入口，
 * 与「规划」「行程」并列有意义。
 */
const links = [
  { label: '首页', to: '/', auth: false, icon: 'compass' },
  /*
   * 「规划」而不是「助手」：这一页用户做的事是**规划行程**（描述需求、
   * 排日程、查车次），「助手」描述的是工具的身份而不是用户的目的。
   * 图标同步从 chat（对话气泡）换成 route（路线）—— 气泡强调「聊天」，
   * 容易让人以为只是个聊天框；路线强调「排出行程」这个结果。
   * 与「行程」也不撞：规划 = 生成，行程 = 已生成的收藏。
   */
  { label: '规划', to: '/chat', auth: true, icon: 'route' },
  { label: '行程', to: '/itineraries', auth: true, icon: 'map' }
]

/**
 * 桌面端要显示的主导航项。
 *
 * 未登录：一项都不显示（见上）；已登录：全部显示。
 * 移动端抽屉另有自己的判断（未登录时改为展示行动按钮），
 * 两处需求不同，故不用同一个 computed。
 */
const desktopLinks = computed(() => (user.isLoggedIn ? links : []))

/**
 * 管理台入口：**两种管理员**都展示。
 *
 * 原先写的是 role === 'admin'，引入 super_admin 后超管反而看不到入口 ——
 * 后端放行而界面不给入口，表现为「我明明是管理员却没有管理台」。
 * 判断收敛到 utils/role.ts，避免再次漏改。
 *
 * 这只是「界面不展示」，真正的拦截在后端（/admin 统一挂了 get_current_admin）。
 */
const showAdmin = computed(() => canAccessAdmin(user.userInfo?.role))

/* ---------------- 账号菜单 ---------------- */
const menuOpen = ref(false)
const menuWrap = ref<HTMLElement | null>(null)

/** 头像完整地址：后端只存文件名，需拼上 CDN 前缀 */
const AVATAR_BASE = 'https://yunimg.heiseven.top/voyage-avatar/'
const avatarUrl = computed(() => {
  const a = user.userInfo?.avatar
  return a ? `${AVATAR_BASE}${a}` : ''
})

/** 无头像时用昵称/邮箱首字母兜底，避免菜单入口是个空白圆 */
const initial = computed(() => {
  const name = user.userInfo?.username || user.userInfo?.email || '?'
  return name.slice(0, 1).toUpperCase()
})

/**
 * 角色标识：只在管理员时显示。
 *
 * 普通用户不显示 —— 给每个人都挂一个「普通用户」标签等于没有信息量，
 * 反而占位置。管理员才需要一眼确认自己的身份（避免误以为权限丢失）。
 */
const roleBadge = computed(() =>
  canAccessAdmin(user.userInfo?.role) ? roleLabel(user.userInfo?.role) : ''
)

function closeMenu() {
  menuOpen.value = false
}

/** 点击菜单外部收起。只在展开时挂监听，避免每次页面点击都走判断 */
function onDocClick(e: MouseEvent) {
  if (!menuOpen.value) return
  const el = menuWrap.value
  if (el && !el.contains(e.target as Node)) menuOpen.value = false
}

/** Esc 收起：键盘用户需要退路，不能只靠点空白 */
function onDocKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && menuOpen.value) menuOpen.value = false
}

const { doLogout } = useLogout()

function close() {
  open.value = false
}

function onScroll() {
  scrolled.value = window.scrollY > 24
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()

  // 账号菜单的「点击外部收起 / Esc 收起」
  document.addEventListener('pointerdown', onDocClick)
  document.addEventListener('keydown', onDocKey)

  // userInfo 只存在内存中，整页刷新后会丢失；而「管理台」入口的显隐依赖它。
  // 这里主动补一次（store 内部有缓存，已加载过就不会重复请求）。
  if (user.isLoggedIn && !user.userInfo) {
    user.fetchUserInfo()
  }
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  document.removeEventListener('pointerdown', onDocClick)
  document.removeEventListener('keydown', onDocKey)
})
</script>

<template>
  <header class="nav" :class="{ 'nav--scrolled': scrolled, 'nav--open': open }">
    <div class="nav__inner">
      <RouterLink to="/" class="brand" @click="close">
        <span class="brand__mark" aria-hidden="true">
          <!-- 站点图标组的 voyage-mark-128.png（128x128，15.5 KB）。
               资源分工：apple-touch-icon / favicon-32 / voyage-mark 三件套
               由 voyage-mark.jpeg 扩展而来，用于站点与导航栏；
               voyage-mark-2.* 专供对话页与登录页。
               此版内边距仅 1.5%/边，内容占画布 88%/97%——
               横向做不到 100% 是因为源内容本身是 646x713 的竖形，
               塞进正方形只能横向多留一点（要铺满就得裁掉内容）。
               34px 显示、3 倍屏需 102px，128 足够且体积只有 15.5 KB。 -->
          <img src="/voyage-mark-128.png" alt="" />
        </span>
        <span class="brand__text">Voyage <em>AI</em></span>
      </RouterLink>

      <nav v-if="desktopLinks.length" class="nav__links" aria-label="主导航">
        <RouterLink
          v-for="l in desktopLinks"
          :key="l.to"
          :to="l.to"
          @click="close"
        >
          <TravelIcon :name="l.icon" :size="15" />
          {{ l.label }}
        </RouterLink>
      </nav>

      <div class="nav__actions">
        <ThemeToggle />
        <template v-if="user.isLoggedIn">
          <RouterLink to="/chat" class="btn btn-primary btn--sm" @click="close">
            进入规划
          </RouterLink>

          <!--
            账号菜单（桌面端）。
            信息区（头像/昵称/邮箱）与操作区分层：信息区带浅底与头像，
            一眼看清「当前是谁」；操作项独立成组，退出登录再单独一组。
          -->
          <div ref="menuWrap" class="usermenu">
            <button
              type="button"
              class="usermenu__btn"
              :class="{ 'is-open': menuOpen }"
              :aria-expanded="menuOpen"
              aria-haspopup="menu"
              aria-label="账号菜单"
              @click="menuOpen = !menuOpen"
            >
              <img
                v-if="avatarUrl"
                class="usermenu__avatar"
                :src="avatarUrl"
                alt=""
              />
              <span v-else class="usermenu__avatar usermenu__avatar--initial">
                {{ initial }}
              </span>
              <TravelIcon
                name="chevron-down"
                :size="14"
                class="usermenu__caret"
              />
            </button>

            <Transition name="um">
              <div v-if="menuOpen" class="usermenu__panel" role="menu">
                <!-- 信息区：浅底 + 大一圈的头像，与操作项形成明确层次 -->
                <div class="usermenu__head">
                  <img v-if="avatarUrl" class="usermenu__head-avatar" :src="avatarUrl" alt="" />
                  <span v-else class="usermenu__head-avatar usermenu__avatar--initial">
                    {{ initial }}
                  </span>
                  <div class="usermenu__head-text">
                    <p class="usermenu__name">
                      {{ user.userInfo?.username || '未设置昵称' }}
                    </p>
                    <p class="usermenu__email" :title="user.userInfo?.email">
                      {{ user.userInfo?.email }}
                    </p>
                  </div>
                  <span v-if="roleBadge" class="usermenu__role">{{ roleBadge }}</span>
                </div>

                <div class="usermenu__group">
                  <RouterLink
                    to="/profile"
                    class="usermenu__item"
                    role="menuitem"
                    @click="closeMenu"
                  >
                    <span class="usermenu__ico"><TravelIcon name="user" :size="16" /></span>
                    <span class="usermenu__label">个人资料</span>
                    <TravelIcon name="arrow-right" :size="14" class="usermenu__go" />
                  </RouterLink>

                  <RouterLink
                    v-if="showAdmin"
                    to="/admin"
                    class="usermenu__item"
                    role="menuitem"
                    @click="closeMenu"
                  >
                    <span class="usermenu__ico"><TravelIcon name="gear" :size="16" /></span>
                    <span class="usermenu__label">管理台</span>
                    <TravelIcon name="arrow-right" :size="14" class="usermenu__go" />
                  </RouterLink>
                </div>

                <!-- 退出登录单独一组，用分割线隔开；悬停才转警示色 -->
                <div class="usermenu__group usermenu__group--foot">
                  <button
                    type="button"
                    class="usermenu__item usermenu__item--danger"
                    role="menuitem"
                    @click="closeMenu(); doLogout()"
                  >
                    <span class="usermenu__ico"><TravelIcon name="sign-out" :size="16" /></span>
                    <span class="usermenu__label">退出登录</span>
                  </button>
                </div>
              </div>
            </Transition>
          </div>
        </template>
        <template v-else>
          <!--
            未登录：只保留**一个**入口「开始规划」。
            刻意**不放单独的「登录」按钮**：
            两者都指向同一个登录页（那里可自由切换登录 / 注册），
            并排放会让人以为有两条不同的路，而其实殊途同归。
            只给一个明确的行动建议，是更干净的取舍。
          -->
          <RouterLink to="/login" class="btn btn-primary btn--sm" @click="close">
            开始规划
          </RouterLink>
        </template>
      </div>

      <button
        class="nav__toggle"
        :aria-expanded="open"
        aria-label="切换导航菜单"
        @click="open = !open"
      >
        <span></span>
        <span></span>
        <span></span>
      </button>
    </div>

    <div v-if="open" class="nav__mobile">
      <!--
        抽屉里的导航项按登录态区分：
        未登录时只列「首页」—— 与桌面端不同，抽屉是个独立面板，
        空着会显得没内容，列一行「首页」比什么都不给更清楚；
        而「规划」「行程」在未登录时点进去也会被守卫弹回登录页，
        列出来只是徒增困惑，故不显示。
      -->
      <RouterLink
        v-for="l in links"
        v-show="!l.auth || user.isLoggedIn"
        :key="l.to"
        :to="l.to"
        class="nav__mobile-link"
        @click="close"
      >
        <TravelIcon :name="l.icon" :size="16" />
        {{ l.label }}
      </RouterLink>
      <div class="nav__mobile-actions">
        <template v-if="user.isLoggedIn">
          <!--
            移动端同样用账号菜单承载「个人资料 / 管理台 / 退出登录」，
            与桌面端一致（主导航里那两项已移除）。
            这里必须保留这个入口 —— 抽屉是移动端唯一的账号入口，
            去掉它用户就没地方退出登录了。
            带文字标签而不是纯图标：抽屉里图标按钮不易辨认。
          -->
          <RouterLink to="/chat" class="btn btn-primary btn--sm nav__mobile-full" @click="close">
            进入规划
          </RouterLink>

          <div class="nav__mobile-usermenu">
            <button
              type="button"
              class="btn btn-ghost btn--sm"
              :aria-expanded="menuOpen"
              aria-haspopup="menu"
              @click="menuOpen = !menuOpen"
            >
              <TravelIcon name="user" :size="15" />
              账号
              <TravelIcon
                name="chevron-down"
                :size="14"
                class="usermenu__caret"
                :class="{ 'is-open': menuOpen }"
              />
            </button>

            <!-- 结构与桌面端保持一致，只是把「图标容器」在窄屏省掉 -->
            <div v-if="menuOpen" class="nav__mobile-menu" role="menu">
              <div class="usermenu__head">
                <img v-if="avatarUrl" class="usermenu__head-avatar" :src="avatarUrl" alt="" />
                <span v-else class="usermenu__head-avatar usermenu__avatar--initial">
                  {{ initial }}
                </span>
                <div class="usermenu__head-text">
                  <p class="usermenu__name">{{ user.userInfo?.username || '未设置昵称' }}</p>
                  <p class="usermenu__email" :title="user.userInfo?.email">
                    {{ user.userInfo?.email }}
                  </p>
                </div>
                <span v-if="roleBadge" class="usermenu__role">{{ roleBadge }}</span>
              </div>

              <div class="usermenu__group">
                <RouterLink to="/profile" class="usermenu__item" role="menuitem" @click="closeMenu(); close()">
                  <TravelIcon name="user" :size="16" />
                  <span class="usermenu__label">个人资料</span>
                </RouterLink>
                <RouterLink
                  v-if="showAdmin"
                  to="/admin"
                  class="usermenu__item"
                  role="menuitem"
                  @click="closeMenu(); close()"
                >
                  <TravelIcon name="gear" :size="16" />
                  <span class="usermenu__label">管理台</span>
                </RouterLink>
              </div>

              <div class="usermenu__group usermenu__group--foot">
                <button
                  type="button"
                  class="usermenu__item usermenu__item--danger"
                  role="menuitem"
                  @click="closeMenu(); close(); doLogout()"
                >
                  <TravelIcon name="sign-out" :size="16" />
                  <span class="usermenu__label">退出登录</span>
                </button>
              </div>
            </div>
          </div>
        </template>
        <template v-else>
          <!--
            未登录：只保留**一个**入口「开始规划」。
            刻意**不放单独的「登录」按钮**：
            两者都指向同一个登录页（那里可自由切换登录 / 注册），
            并排放会让人以为有两条不同的路，而其实殊途同归。
            只给一个明确的行动建议，是更干净的取舍。
          -->
          <RouterLink to="/login" class="btn btn-primary btn--sm" @click="close">
            开始规划
          </RouterLink>
        </template>
      </div>
    </div>
  </header>
</template>

<style scoped>
.nav {
  position: sticky;
  top: 0;
  z-index: 60;
  background: var(--nav-bg);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid transparent;
  transition: box-shadow 0.3s, border-color 0.3s, background-color var(--t);
}
.nav--scrolled {
  box-shadow: 0 6px 24px rgba(15, 23, 42, 0.06);
  border-bottom-color: var(--hairline);
}
:root[data-theme='dark'] .nav--scrolled { box-shadow: 0 6px 24px rgba(2, 8, 23, 0.5); }

.nav__inner {
  max-width: 1120px;
  margin: 0 auto;
  padding: 0 24px;
  height: var(--nav-h);
  display: flex;
  align-items: center;
  gap: 32px;
}

/*
 * 品牌区：整体作为一个可点单元，**始终可点击回首页**（通用习惯）。
 *
 * 悬停反馈做了三层，都是「明显但不喧哗」的处理：
 *   1. 图标轻微上浮 + 投影加深（原有）
 *   2. 文字**转为主题色** —— 只靠图标 1px 上浮太含蓄，几乎看不出；
 *      颜色变化是最容易被注意到的反馈
 *   3. 文字下方滑出一条下划线 —— 明确「这是链接」，
 *      与主导航项的指示线用同一套语言
 * 不给整个标识加位移：文字与图标一起动会显得晃。
 */
.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding: 5px 9px 5px 5px;
  margin-left: -5px;
  border-radius: 12px;
  transition: background-color 0.2s ease;
}
.brand:hover { background: rgba(37, 99, 235, 0.08); }
.brand:focus-visible {
  outline: 2px solid var(--prim);
  outline-offset: 2px;
}

/* Logo 容器：白底圆角方块 + 细边框。
   图标本身是完整方形图（自带底色），容器再叠渐变会变成两层底色打架，
   故改为中性白底；浅色系界面里也更干净。 */
.brand__mark {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--panel);
  border: 1px solid var(--border);
  /* 极轻的投影：让白底图标从半透明导航栏背景上「浮」起来一点，
     否则两者亮度接近会糊在一起 */
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
  display: grid;
  place-items: center;
  overflow: hidden;
  flex-shrink: 0;
  transition: transform 0.22s cubic-bezier(0.2, 0.7, 0.2, 1), box-shadow 0.22s ease;
}
.brand:hover .brand__mark {
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(37, 99, 235, 0.16);
}
@media (prefers-reduced-motion: reduce) {
  .brand__mark { transition: none; }
  .brand:hover .brand__mark { transform: none; }
}
.brand__mark img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.brand__text {
  position: relative;
  font-family: var(--font-display);
  font-size: 1.06rem;
  font-weight: 800;
  /* 字距收紧一点，让「Voyage AI」读起来像一个整体标识而非两个词 */
  letter-spacing: -0.022em;
  color: var(--text);
  transition: color 0.2s ease;
}
/* 「AI」始终是主题色，作为标识的一部分；悬停时整串文字转主题色 */
.brand__text em { font-style: normal; color: var(--prim); }

/* 悬停：文字转主题色 */
.brand:hover .brand__text { color: var(--prim); }

/*
 * 悬停：文字下划线由中间向两侧展开。
 * 只画在文字宽度内（不是整个品牌区），所以看起来是「这个名字被高亮」，
 * 而不是「整块按钮被框住」。
 */
.brand__text::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -3px;
  height: 2px;
  border-radius: 2px;
  background: var(--grad);
  opacity: 0;
  transform: scaleX(0.4);
  transition: opacity 0.2s ease, transform 0.24s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.brand:hover .brand__text::after {
  opacity: 1;
  transform: scaleX(1);
}
/* 键盘用户同样要看到反馈：聚焦时也显示下划线 */
.brand:focus-visible .brand__text::after {
  opacity: 1;
  transform: scaleX(1);
}
@media (prefers-reduced-motion: reduce) {
  .brand__text,
  .brand__text::after { transition: none; }
  .brand__text::after { transform: none; }
}

/*
 * 导航项：胶囊背景 + 底部指示线，双重标记当前页。
 *
 * 为什么加胶囊而不只留底线：底线很细，扫视时容易漏掉；胶囊把「当前在哪」
 * 变成一块可辨识的色块，一眼可定位。两者叠加而不取其一——胶囊给区域感，
 * 底线给精确指向，且底线在胶囊底色上仍清晰（用主题色而非灰色）。
 *
 * 内边距由 4px 0 提到 7px 14px 是让胶囊有形状；同时间距由 28px 收到 6px：
 * 视觉间隔改由内边距承担，整体占宽反而更紧凑，而每项的可点区域明显变大。
 */
.nav__links { display: flex; align-items: center; gap: 6px; font-size: 0.88rem; }

.nav__links a {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 14px;
  border-radius: 10px;
  color: var(--text2);
  transition: color 0.18s ease, background-color 0.18s ease;
}
.nav__links a :deep(svg) { opacity: 0.68; transition: opacity 0.18s ease; }
.nav__links a:hover :deep(svg),
.nav__links a.router-link-active :deep(svg) { opacity: 1; }

/* 指示线贴在胶囊下沿内侧，比贴到导航栏底边更克制 */
.nav__links a::after {
  content: '';
  position: absolute;
  left: 14px;
  right: 14px;
  bottom: 3px;
  height: 2px;
  border-radius: 2px;
  background: var(--grad);
  opacity: 0;
  transform: scaleX(0.4);
  transition: opacity 0.22s ease, transform 0.22s ease;
}

/*
 * 悬停用主题色淡染，而不是 --panel2。
 * 原因：导航栏背景是半透明的 --nav-bg（rgba(247,249,252,0.82)），
 * 而 --panel2 是 #f5f8fc —— 两者亮度几乎相同，用后者做悬停会看不出变化。
 * 主题色淡染在深浅两个主题下都能与底色拉开差距，且暗示了「可点」。
 */
.nav__links a:hover {
  color: var(--text);
  background: rgba(37, 99, 235, 0.06);
}
.nav__links a:hover::after { opacity: 0.32; transform: scaleX(1); }

.nav__links a.router-link-active {
  color: var(--prim);
  font-weight: 650;
  background: var(--primary-soft);
}
.nav__links a.router-link-active::after { opacity: 1; transform: scaleX(1); }

/* 原先此处有一组 .nav__links a.nav__admin 规则，用于把「管理台」弱化一档
   （字号更小、颜色更淡、不给当前页高亮）。该入口已移到右侧账号菜单，
   规则一并删除，避免留下无引用的样式。 */

@media (prefers-reduced-motion: reduce) {
  .nav__links a,
  .nav__links a::after { transition: none; }
}

.nav__actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }

/* ============================================================
   账号菜单
   ------------------------------------------------------------
   设计思路：把它当成一张**小卡片**而不是一串菜单项。
   三层结构，逐层降低视觉权重：
     1. 信息区  —— 浅底 + 40px 头像 + 昵称/邮箱 + 角色标识
                    回答「我现在是谁」，也是这张卡片的「封面」
     2. 操作区  —— 个人资料 / 管理台，图标放进圆形浅底容器
     3. 危险区  —— 退出登录，分割线隔开，默认中性、悬停才转警示色
   动效克制：只做 4px 位移 + 淡入，不做缩放（缩放像「弹」出来，廉价感）。
   ============================================================ */
.usermenu { position: relative; }

.usermenu__btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px 3px 3px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  transition: border-color 0.18s, background-color 0.18s, box-shadow 0.18s;
}
.usermenu__btn:hover,
.usermenu__btn.is-open {
  border-color: var(--blue-200);
  background: var(--blue-50);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.10);
}
.usermenu__btn:focus-visible { outline: 2px solid var(--prim); outline-offset: 2px; }

.usermenu__avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
  display: block;
  background: var(--surface-soft);
  /* 头像加一圈描边：浅色底上能看出边界，不会糊进背景 */
  box-shadow: 0 0 0 1px rgba(16, 24, 40, 0.06);
}
/* 无头像时用首字母兜底，避免入口是个空白圆 */
.usermenu__avatar--initial {
  display: grid;
  place-items: center;
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--prim);
  background: linear-gradient(135deg, #dbeafe, #eff6ff);
}

/* 下拉指示：改用描边图标而不是 CSS 三角形 —— 三角在圆角按钮里显得糙 */
.usermenu__caret {
  color: var(--text3);
  transition: transform 0.22s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.usermenu__btn.is-open .usermenu__caret { transform: rotate(180deg); }

.usermenu__panel {
  position: absolute;
  z-index: 70;
  top: calc(100% + 10px);
  right: 0;
  width: 268px;
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: 14px;
  /* 两级阴影：近处一层收边，远处一层抬起。
     单层大模糊会显得灰扑扑，两层才有「浮起来」的实感。 */
  box-shadow:
    0 1px 2px rgba(16, 24, 40, 0.05),
    0 12px 28px -6px rgba(16, 24, 40, 0.16),
    0 24px 52px -12px rgba(16, 24, 40, 0.12);
  background: var(--panel);
  overflow: hidden;
}

/* ---------- 1. 信息区 ---------- */
.usermenu__head {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 13px 12px 14px;
  border-radius: 10px 10px 0 0;
  /* 用主色极淡的渐变当「封面」，与下方纯白操作区自然分层 */
  background: linear-gradient(180deg, #f8fafc, #ffffff);
  border-bottom: 1px solid var(--hairline);
  margin-bottom: 6px;
}

.usermenu__head-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  font-size: 1rem;
  font-weight: 700;
  box-shadow: 0 0 0 1px rgba(16, 24, 40, 0.06);
}

.usermenu__head-text { min-width: 0; flex: 1; }

.usermenu__name {
  font-size: 0.88rem;
  font-weight: 650;
  color: var(--text);
  letter-spacing: -0.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.usermenu__email {
  margin-top: 3px;
  font-size: 0.73rem;
  color: var(--text3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 角色标识：只有管理员才渲染，普通用户挂个「普通用户」标签没有信息量 */
.usermenu__role {
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 2px;
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--prim);
  background: var(--primary-soft);
  border: 1px solid var(--blue-200);
}

/* ---------- 2/3. 操作区与危险区 ---------- */
.usermenu__group { display: flex; flex-direction: column; gap: 1px; }
/* 危险区用分割线隔开：退出与上面两项性质不同，不该混在一组里 */
.usermenu__group--foot {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--hairline);
}

.usermenu__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 9px;
  background: transparent;
  font-size: 0.845rem;
  font-weight: 550;
  color: var(--text2);
  text-align: left;
  transition: background-color 0.15s, color 0.15s;
}
.usermenu__item:hover { background: var(--surface-soft); color: var(--text); }
.usermenu__item:focus-visible { outline: 2px solid var(--prim); outline-offset: -2px; }

/*
 * 图标放在固定尺寸的方形浅底里。
 * 为什么：图标直接裸放时，不同图标的视觉重量差异很大（齿轮比用户重），
 * 一行行看会觉得参差。统一容器后左边缘对齐、重量一致，是精致感的关键。
 */
.usermenu__ico {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  flex-shrink: 0;
  color: var(--text2);
  background: var(--surface-soft);
  transition: background-color 0.15s, color 0.15s;
}
.usermenu__item:hover .usermenu__ico {
  background: var(--primary-soft);
  color: var(--prim);
}

.usermenu__label { flex: 1; }

/* 右侧进入指示：默认不可见，悬停时淡入并轻微右移 —— 暗示「会跳转」 */
.usermenu__go {
  color: var(--text3);
  opacity: 0;
  transform: translateX(-3px);
  transition: opacity 0.15s, transform 0.15s;
}
.usermenu__item:hover .usermenu__go { opacity: 0.7; transform: translateX(0); }

/*
 * 退出登录：默认与其它项完全一致，悬停才转警示色。
 * 常亮红色会让它成为菜单里最显眼的一项，而它恰恰最不该被误点。
 * 只有鼠标停在上面（说明确实是奔它去的）才给出警示语义。
 */
.usermenu__item--danger:hover {
  background: rgba(224, 82, 82, 0.07);
  color: var(--danger);
}
.usermenu__item--danger:hover .usermenu__ico {
  background: rgba(224, 82, 82, 0.11);
  color: var(--danger);
}

/* 当前所在页：只高亮图标容器，不给整行铺色，避免菜单里出现大色块 */
.usermenu__panel .router-link-active { color: var(--prim); font-weight: 650; }
.usermenu__panel .router-link-active .usermenu__ico {
  background: var(--primary-soft);
  color: var(--prim);
}

/* 菜单出入：4px 位移 + 淡入，配 cubic-bezier 让它「落」下来而不是弹出来 */
.um-enter-active { transition: opacity 0.18s ease, transform 0.18s cubic-bezier(0.2, 0.7, 0.2, 1); }
.um-leave-active { transition: opacity 0.12s ease, transform 0.12s ease; }
.um-enter-from,
.um-leave-to { opacity: 0; transform: translateY(-6px); }

@media (prefers-reduced-motion: reduce) {
  .usermenu__caret,
  .usermenu__go,
  .um-enter-active,
  .um-leave-active { transition: none; }
}

.nav__toggle {
  display: none;
  margin-left: auto;
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  color: var(--text);
}
.nav__toggle span {
  width: 18px;
  height: 2px;
  border-radius: 2px;
  background: currentColor;
  transition: transform 0.22s ease, opacity 0.22s ease;
}
.nav--open .nav__toggle span:nth-child(1) { transform: translateY(7px) rotate(45deg); }
.nav--open .nav__toggle span:nth-child(2) { opacity: 0; }
.nav--open .nav__toggle span:nth-child(3) { transform: translateY(-7px) rotate(-45deg); }

.nav__mobile {
  display: none;
  border-top: 1px solid var(--hairline);
  padding: 10px 24px 18px;
  background: var(--bg);
}

/*
 * 移动端抽屉里的导航项。
 * 当前页同样要高亮——桌面端刚做了胶囊+底线，移动端若不做，
 * 同一个站点的两套导航就会不一致（用户在不同宽度看到不同反馈）。
 * 抽屉里是竖排列表，用左侧一条竖线 + 背景染色的方式，
 * 比复用桌面的底部指示线更贴合这种版式。
 */
.nav__mobile-link {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 12px 12px;
  margin: 0 -12px;
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 500;
  color: var(--text2);
  transition: background-color 0.18s ease, color 0.18s ease;
}
.nav__mobile-link :deep(svg) { color: var(--text3); transition: color 0.18s ease; }

.nav__mobile-link:hover {
  background: rgba(37, 99, 235, 0.06);
  color: var(--text);
}

.nav__mobile-link.router-link-active {
  background: var(--primary-soft);
  color: var(--prim);
  font-weight: 650;
}
.nav__mobile-link.router-link-active :deep(svg) { color: var(--prim); }

@media (prefers-reduced-motion: reduce) {
  .nav__mobile-link,
  .nav__mobile-link :deep(svg) { transition: none; }
}

.nav__mobile-actions { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }

/* 「进入规划」占整行：它是移动端的主操作，与账号菜单并列会显得同等重要 */
.nav__mobile-full { width: 100%; justify-content: center; }

/* 移动端账号菜单：抽屉里不放浮层，改为内联展开 ——
   抽屉本身已是覆盖层，再叠一个浮层既不好点也容易误触外面 */
.nav__mobile-usermenu { width: 100%; }
.nav__mobile-usermenu > .btn { width: 100%; justify-content: center; }

/*
 * 内联面板直接复用桌面端的 .usermenu__head / __item 结构，
 * 但有两处必须覆盖：
 *   · 圆角与阴影 —— 浮层是独立卡片，内联面板是抽屉的一部分，不需要抬起
 *   · 图标容器（.usermenu__ico）—— 窄屏空间紧，省掉方形浅底，
 *     直接裸放图标但固定 16px 宽度，保证每行文字左边缘对齐
 */
.nav__mobile-menu {
  margin-top: 8px;
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
}
.nav__mobile-menu .usermenu__head {
  border-radius: 8px 8px 0 0;
  padding: 11px 10px 12px;
}
.nav__mobile-menu .usermenu__item > :deep(svg:first-child) {
  flex-shrink: 0;
  width: 16px;
  color: var(--text3);
}
.nav__mobile-menu .usermenu__item:hover > :deep(svg:first-child) { color: var(--prim); }
.nav__mobile-menu .usermenu__item--danger:hover > :deep(svg:first-child) { color: var(--danger); }

@media (max-width: 860px) {
  .nav__links { display: none; }
  .nav__actions { display: none; }
  .nav__toggle { display: flex; }
  .nav__mobile { display: block; }
}
</style>
