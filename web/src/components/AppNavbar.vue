<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useUserStore } from '@/stores/user'
import { canAccessAdmin } from '@/utils/role'
import { useLogout } from '@/composables/useLogout'
import ThemeToggle from '@/components/ThemeToggle.vue'
import TravelIcon from '@/components/TravelIcon.vue'

const user = useUserStore()
const open = ref(false)
const scrolled = ref(false)

/**
 * 主导航项。
 *
 * 「我的」与「管理台」已从这里移除，改由右侧的**账号菜单**承载 ——
 * 它们都是账号级入口，放在主导航里与「首页/助手/行程」这些功能入口并列，
 * 语义层级不一致；而且现在头像菜单里已经有了，留着就是两个入口指向同一处。
 * 入口本身没有消失，只是归到了更合适的位置。
 */
const links = [
  { label: '首页', to: '/', icon: 'compass' },
  { label: '助手', to: '/chat', auth: true, icon: 'chat' },
  { label: '行程', to: '/itineraries', auth: true, icon: 'map' }
]

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

      <nav class="nav__links" aria-label="主导航">
        <RouterLink
          v-for="l in links"
          v-show="!l.auth || user.isLoggedIn"
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
            进入助手
          </RouterLink>

          <!--
            头像菜单：把「个人资料 / 管理台 / 退出登录」收进来。
            原先桌面端导航栏没有「我的」入口，退出登录只在个人页最底部 ——
            登出是账号级操作，藏在二级页面底部既不合常规也不便使用。
            这里一次点击进菜单、两步完成登出，是主流做法。
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
              <span class="usermenu__caret" aria-hidden="true"></span>
            </button>

            <Transition name="um">
              <div v-if="menuOpen" class="usermenu__panel" role="menu">
                <div class="usermenu__head">
                  <p class="usermenu__name">{{ user.userInfo?.username || '未设置昵称' }}</p>
                  <p class="usermenu__email" :title="user.userInfo?.email">
                    {{ user.userInfo?.email }}
                  </p>
                </div>

                <RouterLink
                  to="/profile"
                  class="usermenu__item"
                  role="menuitem"
                  @click="closeMenu"
                >
                  <TravelIcon name="user" :size="15" />
                  个人资料
                </RouterLink>

                <RouterLink
                  v-if="showAdmin"
                  to="/admin"
                  class="usermenu__item"
                  role="menuitem"
                  @click="closeMenu"
                >
                  <TravelIcon name="compass" :size="15" />
                  管理台
                </RouterLink>

                <button
                  type="button"
                  class="usermenu__item usermenu__item--danger"
                  role="menuitem"
                  @click="closeMenu(); doLogout()"
                >
                  <TravelIcon name="arrow-right" :size="15" />
                  退出登录
                </button>
              </div>
            </Transition>
          </div>
        </template>
        <template v-else>
          <!--
            未登录时只保留一个入口。
            原先「登录」与「开始规划」是两个按钮、指向同一个 /login，
            既重复又让人以为有两条不同的路。登录页本身就是唯一入口，
            进去既可以登录也可以注册。
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
            进入助手
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
              <span class="usermenu__caret" :class="{ 'is-open': menuOpen }" aria-hidden="true"></span>
            </button>

            <div v-if="menuOpen" class="nav__mobile-menu" role="menu">
              <p class="usermenu__name">{{ user.userInfo?.username || '未设置昵称' }}</p>
              <p class="usermenu__email">{{ user.userInfo?.email }}</p>
              <RouterLink to="/profile" class="usermenu__item" role="menuitem" @click="closeMenu(); close()">
                <TravelIcon name="user" :size="15" />
                个人资料
              </RouterLink>
              <RouterLink
                v-if="showAdmin"
                to="/admin"
                class="usermenu__item"
                role="menuitem"
                @click="closeMenu(); close()"
              >
                <TravelIcon name="compass" :size="15" />
                管理台
              </RouterLink>
              <button
                type="button"
                class="usermenu__item usermenu__item--danger"
                role="menuitem"
                @click="closeMenu(); close(); doLogout()"
              >
                <TravelIcon name="arrow-right" :size="15" />
                退出登录
              </button>
            </div>
          </div>
        </template>
        <template v-else>
          <!--
            未登录时只保留一个入口。
            原先「登录」与「开始规划」是两个按钮、指向同一个 /login，
            既重复又让人以为有两条不同的路。登录页本身就是唯一入口，
            进去既可以登录也可以注册。
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
 * 品牌区：整体作为一个可点单元。
 * 悬停只在图标上做轻微反馈（上浮 + 加深阴影），文字保持不动——
 * 让整个标识一起动会显得晃。
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
.brand:hover { background: rgba(37, 99, 235, 0.06); }
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
  font-family: var(--font-display);
  font-size: 1.06rem;
  font-weight: 800;
  /* 字距收紧一点，让「Voyage AI」读起来像一个整体标识而非两个词 */
  letter-spacing: -0.022em;
  color: var(--text);
}
.brand__text em { font-style: normal; color: var(--prim); }

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

/* ---- 账号菜单 ---- */
.usermenu { position: relative; }

.usermenu__btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 6px 3px 3px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  transition: border-color 0.18s, background-color 0.18s;
}
.usermenu__btn:hover,
.usermenu__btn.is-open {
  border-color: var(--blue-200);
  background: var(--blue-50);
}
.usermenu__btn:focus-visible { outline: 2px solid var(--prim); outline-offset: 2px; }

.usermenu__avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
  display: block;
  background: var(--surface-soft);
}
/* 无头像时用首字母兜底，避免入口是个空白圆 */
.usermenu__avatar--initial {
  display: grid;
  place-items: center;
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--prim);
  background: var(--primary-soft);
}

.usermenu__caret {
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid var(--text3);
  transition: transform 0.2s ease;
}
.usermenu__btn.is-open .usermenu__caret { transform: rotate(180deg); }

.usermenu__panel {
  position: absolute;
  z-index: 70;
  top: calc(100% + 8px);
  right: 0;
  min-width: 216px;
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: var(--r-m);
  /* 菜单需要明显浮于页面之上，故用较强阴影（按钮上刻意不用） */
  box-shadow: 0 12px 32px rgba(16, 24, 40, 0.14), 0 2px 6px rgba(16, 24, 40, 0.06);
  background: var(--panel);
}

.usermenu__head {
  padding: 8px 10px 10px;
  border-bottom: 1px solid var(--hairline);
  margin-bottom: 4px;
}
.usermenu__name { font-size: 0.84rem; font-weight: 650; color: var(--text); }
.usermenu__email {
  margin-top: 2px;
  font-size: 0.74rem;
  color: var(--text3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.usermenu__item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: var(--r-s);
  background: transparent;
  font-size: 0.84rem;
  font-weight: 550;
  color: var(--text2);
  text-align: left;
  transition: background-color 0.16s, color 0.16s;
}
.usermenu__item:hover { background: var(--surface-soft); color: var(--text); }
.usermenu__item:focus-visible { outline: 2px solid var(--prim); outline-offset: -2px; }

/*
 * 退出登录：默认与其它项同色，悬停才转红。
 * 常亮红色会让它在菜单里最显眼，而它恰恰是最不该被误点的操作。
 * 图标转 180° 表示「离开」，比再加一个图标省事。
 */
.usermenu__item--danger :deep(svg) { transform: rotate(180deg); }
.usermenu__item--danger:hover {
  background: rgba(224, 82, 82, 0.08);
  color: var(--danger);
}

.usermenu__panel .router-link-active {
  background: var(--primary-soft);
  color: var(--prim);
  font-weight: 650;
}

/* 菜单出入：轻微下移淡入（缩放会让菜单像「弹」出来） */
.um-enter-active,
.um-leave-active { transition: opacity 0.16s ease, transform 0.16s ease; }
.um-enter-from,
.um-leave-to { opacity: 0; transform: translateY(-4px); }

@media (prefers-reduced-motion: reduce) {
  .usermenu__caret { transition: none; }
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

/* 「进入助手」占整行：它是移动端的主操作，与账号菜单并列会显得同等重要 */
.nav__mobile-full { width: 100%; justify-content: center; }

/* 移动端账号菜单：抽屉里不放浮层，改为内联展开 ——
   抽屉本身已是覆盖层，再叠一个浮层既不好点也容易误触外面 */
.nav__mobile-usermenu { width: 100%; }
.nav__mobile-usermenu > .btn { width: 100%; justify-content: center; }

.nav__mobile-menu {
  margin-top: 8px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: var(--r-m);
  background: var(--panel);
}
.nav__mobile-menu .usermenu__name { font-size: 0.84rem; font-weight: 650; color: var(--text); }
.nav__mobile-menu .usermenu__email {
  margin: 2px 0 8px;
  font-size: 0.74rem;
  color: var(--text3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 860px) {
  .nav__links { display: none; }
  .nav__actions { display: none; }
  .nav__toggle { display: flex; }
  .nav__mobile { display: block; }
}
</style>
