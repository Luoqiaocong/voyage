<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useUserStore } from '@/stores/user'
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

/** 管理台入口仅对管理员展示。
 *  这只是「界面不展示」，真正的拦截在后端（/admin 统一挂了 get_current_admin）。 */
const showAdmin = computed(() => user.userInfo?.role === 'admin')

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
          <!-- 位图 logo：白底彩图，故用白色圆角方块作底。
               为什么不是原来的蓝色渐变方块：这张 logo 是「白底 + 极浅粉彩图形」，
               图形与背景亮度只差约 29 级。放在饱和彩色底上图形会与背景融为一体。
               用白色容器反而让它在浅色系界面里干净、不割裂。 -->
          <img src="/voyage-mark.png" alt="" />
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
        <RouterLink v-if="showAdmin" to="/admin" @click="close">
          <TravelIcon name="compass" :size="15" />
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
          <RouterLink to="/login" class="btn btn-ghost btn--sm" @click="close">登录</RouterLink>
          <RouterLink to="/login" class="btn btn-primary btn--sm" @click="close">开始规划</RouterLink>
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
          <RouterLink v-if="showAdmin" to="/admin" class="btn btn-ghost btn--sm" @click="close">管理台</RouterLink>
          <RouterLink to="/profile" class="btn btn-ghost btn--sm" @click="close">个人资料</RouterLink>
          <RouterLink to="/chat" class="btn btn-primary btn--sm" @click="close">进入助手</RouterLink>
        </template>
        <template v-else>
          <RouterLink to="/login" class="btn btn-ghost btn--sm" @click="close">登录</RouterLink>
          <RouterLink to="/login" class="btn btn-primary btn--sm" @click="close">开始规划</RouterLink>
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

.brand { display: inline-flex; align-items: center; gap: 10px; flex-shrink: 0; }

/* 品牌标记：白色圆角方块 + logo。
   底色用白而非渐变，原因见模板注释——这张 logo 的图形本身极浅，
   放在饱和彩色底上会看不清。浅色界面里白方块也更干净。 */
.brand__mark {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--border);
  display: grid;
  place-items: center;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
  overflow: hidden;
}
.brand__mark img {
  width: 100%;
  height: 100%;
  /* object-fit: cover + 放大：源图标为了给 favicon 留边距，白边较多
     （内容只占 78%）。直接放满会让图形显得偏小、视觉重量轻于原来的图标，
     故按 34px 方块的观感放大到 118%。 */
  object-fit: cover;
  transform: scale(1.18);
  display: block;
}

.brand__text {
  font-family: var(--font-display);
  font-size: 1.06rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.brand__text em { font-style: normal; color: var(--prim); }

.nav__links { display: flex; gap: 28px; font-size: 0.88rem; }

.nav__links a {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text2);
  padding: 4px 0;
  transition: color 0.18s ease;
}
.nav__links a :deep(svg) { opacity: 0.7; transition: opacity 0.18s; }
.nav__links a:hover :deep(svg), .nav__links a.router-link-active :deep(svg) { opacity: 1; }
.nav__links a::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -2px;
  height: 2px;
  border-radius: 2px;
  background: var(--grad);
  opacity: 0;
  transition: opacity 0.18s ease;
}
.nav__links a:hover { color: var(--text); }
.nav__links a.router-link-active { color: var(--text); font-weight: 600; }
.nav__links a.router-link-active::after { opacity: 1; }

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

.nav__mobile-link {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 12px 2px;
  font-size: 0.95rem;
  font-weight: 500;
  border-bottom: 1px dashed var(--hairline);
}
.nav__mobile-link :deep(svg) { color: var(--text3); }

.nav__mobile-actions { display: flex; gap: 10px; margin-top: 14px; }

@media (max-width: 860px) {
  .nav__links { display: none; }
  .nav__actions { display: none; }
  .nav__toggle { display: flex; }
  .nav__mobile { display: block; }
}
</style>
