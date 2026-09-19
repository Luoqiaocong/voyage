<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useUserStore } from '@/stores/user'
import { canAccessAdmin } from '@/utils/role'
import ThemeToggle from '@/components/ThemeToggle.vue'
import TravelIcon from '@/components/TravelIcon.vue'

const user = useUserStore()
const open = ref(false)
const scrolled = ref(false)

const links = [
  { label: '首页', to: '/', icon: 'compass' },
  { label: '助手', to: '/chat', auth: true, icon: 'chat' },
  { label: '行程', to: '/itineraries', auth: true, icon: 'map' },
  { label: '我的', to: '/profile', auth: true, icon: 'user' }
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

function close() {
  open.value = false
}

function onScroll() {
  scrolled.value = window.scrollY > 24
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()

  // userInfo 只存在内存中，整页刷新后会丢失；而「管理台」入口的显隐依赖它。
  // 这里主动补一次（store 内部有缓存，已加载过就不会重复请求）。
  if (user.isLoggedIn && !user.userInfo) {
    user.fetchUserInfo()
  }
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
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
        <!--
          管理台适度弱化：字号更小、颜色更淡、不做当前页高亮。
          它不是面向普通用户的产品功能，而是管理入口；与「首页/助手/行程/我的」
          同等呈现会让它看起来像主流程的一部分，也容易误点。
          但仍保留在导航里且可点 —— 管理员的常用入口，藏进二级菜单反而麻烦。
        -->
        <RouterLink v-if="showAdmin" to="/admin" class="nav__admin" @click="close">
          <TravelIcon name="compass" :size="14" />
          管理台
        </RouterLink>
      </nav>

      <div class="nav__actions">
        <ThemeToggle />
        <template v-if="user.isLoggedIn">
          <RouterLink to="/chat" class="btn btn-primary btn--sm" @click="close">
            进入助手
          </RouterLink>
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
          <!-- 与桌面端一致：管理台弱化一档（它不属于产品主流程） -->
          <RouterLink
            v-if="showAdmin"
            to="/admin"
            class="btn btn-ghost btn--sm nav__mobile-admin"
            @click="close"
          >
            管理台
          </RouterLink>
          <RouterLink to="/profile" class="btn btn-ghost btn--sm" @click="close">个人资料</RouterLink>
          <RouterLink to="/chat" class="btn btn-primary btn--sm" @click="close">进入助手</RouterLink>
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

/*
 * 管理台：刻意比其它导航项轻一档。
 * 字号 0.82rem（其余 0.88rem）、颜色 text3（其余 text2）、无当前页高亮。
 * 仍保留悬停反馈 —— 否则会显得「不可点」，而不是「次要」。
 *
 * 选择器写成 .nav__links a.nav__admin 而不是 .nav__admin：
 * 上面那些 .nav__links a.xxx 规则的特异性更高，若只用单类名就得靠
 * !important 硬压，那是坏味道。提高特异性即可自然覆盖。
 */
.nav__links a.nav__admin {
  margin-left: 4px;
  font-size: 0.82rem;
  gap: 5px;
  color: var(--text3);
}
.nav__links a.nav__admin :deep(svg) { opacity: 0.55; }

.nav__links a.nav__admin:hover {
  color: var(--text2);
  background: rgba(37, 99, 235, 0.05);
}
.nav__links a.nav__admin:hover :deep(svg) { opacity: 0.75; }

/* 即使身处 /admin 也不给主色胶囊与指示线 —— 它不是同级导航 */
.nav__links a.nav__admin.router-link-active {
  color: var(--text2);
  font-weight: 550;
  background: rgba(37, 99, 235, 0.05);
}
.nav__links a.nav__admin.router-link-active :deep(svg) { opacity: 0.75; }
.nav__links a.nav__admin.router-link-active::after { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .nav__links a,
  .nav__links a::after { transition: none; }
}

.nav__actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }

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

/* 移动端的「管理台」同样弱化：去掉边框，视觉上退为文字入口 */
.nav__mobile-admin {
  border-color: transparent;
  background: transparent;
  color: var(--text3);
  font-weight: 550;
  padding-left: 8px;
  padding-right: 8px;
}
.nav__mobile-admin:hover { color: var(--text2); background: rgba(37, 99, 235, 0.05); }

@media (max-width: 860px) {
  .nav__links { display: none; }
  .nav__actions { display: none; }
  .nav__toggle { display: flex; }
  .nav__mobile { display: block; }
}
</style>
