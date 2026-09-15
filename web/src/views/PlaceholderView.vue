<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => (route.meta.title as string | undefined) ?? '页面建设中')
</script>

<template>
  <main id="main" tabindex="-1" class="ph">
    <div class="container ph__box">
      <span class="ph__mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2.4" />
          <path d="M 16 4.5 L 18.8 13.2 L 27.5 16 L 18.8 18.8 L 16 27.5 L 13.2 18.8 L 4.5 16 L 13.2 13.2 Z" fill="currentColor" />
          <circle cx="16" cy="16" r="2.2" fill="var(--bg)" />
        </svg>
      </span>
      <p class="ph__eyebrow">Next Iteration</p>
      <h1>{{ title }}</h1>
      <p class="ph__desc">该页面属于下一迭代范围，目前仅作为路由占位。先回到首页，看看本次交付的主页吧。</p>
      <RouterLink to="/" class="btn btn-primary">返回首页</RouterLink>
    </div>
  </main>
</template>

<style scoped>
.ph {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 40px 0;
}

.ph__box {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 14px;
  padding: 56px 40px;
  border: 1.5px dashed var(--line);
  border-radius: 24px;
  background: rgba(253, 250, 243, 0.7);
  max-width: 520px;
}

.ph__mark {
  width: 58px;
  height: 58px;
  color: var(--primary);
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-sm);
}

.ph__mark svg { width: 34px; height: 34px; }

.ph__eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.26em;
  text-transform: uppercase;
  color: var(--primary-deep);
  margin-top: 8px;
}

.ph__box h1 { font-size: 1.9rem; }

.ph__desc { color: var(--ink-soft); max-width: 34em; }

.ph__box .btn { margin-top: 12px; }
</style>