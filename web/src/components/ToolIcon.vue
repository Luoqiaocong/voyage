<script setup lang="ts">
/** 工具调用图标：按工具类型给出可辨识的线性图标 */
defineProps<{ kind: string }>()
</script>

<template>
  <svg
    class="tico"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- 天气 -->
    <template v-if="kind === 'weather'">
      <path d="M17.5 19H7a4 4 0 0 1-1.3-7.8A6 6 0 0 1 17 8.5a4.5 4.5 0 0 1 .5 10.5z" />
      <path d="M12 3v1.5M4.5 6l1 1M19.5 6l-1 1" />
    </template>
    <!-- 车次 -->
    <template v-else-if="kind === 'train'">
      <rect x="4" y="4" width="16" height="13" rx="2.5" />
      <path d="M4 10h16M9 21l1.5-4M15 21l-1.5-4M9 14h.01M15 14h.01" />
    </template>
    <!-- 行程 -->
    <template v-else-if="kind === 'itinerary'">
      <rect x="4" y="5" width="16" height="15" rx="2.5" />
      <path d="M4 10h16M9 3v4M15 3v4M9.5 14.5l2 2 3.5-4" />
    </template>
    <!-- 日期 -->
    <template v-else-if="kind === 'date'">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </template>
    <!-- 通用：扳手 -->
    <template v-else>
      <path d="M14.7 6.3a4 4 0 0 0 5 5l-9 9a2.1 2.1 0 0 1-3-3z" />
      <path d="M14.7 6.3 17 4a4 4 0 0 1 3 3l-2.3 2.3" />
    </template>
  </svg>
</template>

<style scoped>
.tico { width: 17px; height: 17px; flex-shrink: 0; }
</style>
