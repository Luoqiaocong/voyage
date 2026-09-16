<script setup lang="ts">
/**
 * 管理台外壳：左侧导航 + 右侧内容区。
 *
 * 权限说明：这里只负责「界面不展示」，真正的拦截在后端
 * （/admin 路由统一挂了 get_current_admin，非管理员返回 10105）。
 * 前端守卫只是为了少发无谓的请求、并给出友好提示，不是安全边界。
 */
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const user = useUserStore()

const nav = [
  { to: '/admin', label: '概览', exact: true },
  { to: '/admin/metrics', label: '运行指标' },
  { to: '/admin/users', label: '用户管理' },
  { to: '/admin/conversations', label: '会话洞察' },
  { to: '/admin/audit', label: '审计日志' }
]

const currentTitle = computed(
  () => nav.find((n) => (n.exact ? route.path === n.to : route.path.startsWith(n.to)))?.label ?? '管理台'
)
</script>

<template>
  <div class="admin">
    <div class="container admin__inner">
      <aside class="admin__side">
        <div class="admin__brand">
          <span class="admin__badge">ADMIN</span>
          <p class="admin__who">{{ user.userInfo?.username || user.userInfo?.email || '管理员' }}</p>
        </div>

        <nav class="admin__nav">
          <RouterLink v-for="n in nav" :key="n.to" :to="n.to" :class="{ 'is-active': route.path === n.to || (!n.exact && route.path.startsWith(n.to)) }">
            {{ n.label }}
          </RouterLink>
        </nav>

        <RouterLink to="/chat" class="admin__back">← 返回助手</RouterLink>
      </aside>

      <section class="admin__main">
        <header class="page-head">
          <h1 class="page-title">{{ currentTitle }}</h1>
        </header>
        <RouterView />
      </section>
    </div>
  </div>
</template>

<style scoped>
.admin { min-height: 100vh; display: flex; flex-direction: column; }
.admin__inner {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 32px;
  padding: 32px 0 64px;
  flex: 1;
  align-items: start;
}

.admin__side { position: sticky; top: calc(var(--nav-h) + 24px); }

.admin__brand { margin-bottom: 20px; }
.admin__badge {
  display: inline-block;
  font-family: var(--mono);
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  padding: 3px 9px;
  border-radius: 6px;
  background: var(--grad);
  color: #fff;
}
.admin__who {
  margin-top: 8px;
  font-size: 0.82rem;
  color: var(--text2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin__nav { display: flex; flex-direction: column; gap: 2px; }
.admin__nav a {
  display: block;
  padding: 9px 12px;
  border-radius: var(--r-s);
  font-size: 0.9rem;
  color: var(--text2);
  transition: background-color 0.18s, color 0.18s;
}
.admin__nav a:hover { background: var(--surface-soft); color: var(--text); }
.admin__nav a.is-active {
  background: var(--primary-soft);
  color: var(--prim);
  font-weight: 650;
}

.admin__back {
  display: inline-block;
  margin-top: 20px;
  font-size: 0.82rem;
  color: var(--text3);
}
.admin__back:hover { color: var(--prim); }

.admin__main { min-width: 0; }

@media (max-width: 860px) {
  .admin__inner { grid-template-columns: 1fr; gap: 20px; }
  .admin__side { position: static; }
  .admin__nav { flex-direction: row; flex-wrap: wrap; }
}
</style>
