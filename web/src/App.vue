<script setup lang="ts">
import ToastHost from '@/components/ToastHost.vue'
import ConfirmHost from '@/components/ConfirmHost.vue'
</script>

<template>
  <a class="skip-link" href="#main">跳到主要内容</a>

  <!-- 路由切换：像翻过一页旅行手账 -->
  <RouterView v-slot="{ Component, route }">
    <Transition name="route-fade" mode="out-in">
      <component :is="Component" :key="route.path" />
    </Transition>
  </RouterView>

  <ToastHost />
  <ConfirmHost />
</template>

<style>
/* 路由过渡需作用于 RouterView 的直接子组件，故为全局样式 */
.route-fade-enter-active {
  transition: opacity 0.42s ease, transform 0.42s cubic-bezier(0.2, 0.7, 0.2, 1);
}
.route-fade-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.route-fade-enter-from {
  opacity: 0;
  transform: translateY(14px);
}
.route-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@media (prefers-reduced-motion: reduce) {
  .route-fade-enter-active,
  .route-fade-leave-active {
    transition: none;
  }
}
</style>
