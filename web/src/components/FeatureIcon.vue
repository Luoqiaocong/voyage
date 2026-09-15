<script setup lang="ts">
/** 首页能力卡片图标：线性风格，跟随 currentColor */
defineProps<{
  name: 'spark' | 'train' | 'sun' | 'edit' | 'layers' | 'chat' | 'graph' | 'plug' | 'shield' | 'clock'
}>()
</script>

<template>
  <svg
    class="ficon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'spark'">
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
      <path d="M19 15l.9 2.4L22 18l-2.1.6L19 21l-.9-2.4L16 18l2.1-.6z" />
    </template>

    <template v-else-if="name === 'train'">
      <rect x="4" y="4" width="16" height="13" rx="2.5" />
      <path d="M4 10h16M9 21l1.5-4M15 21l-1.5-4M9 14h.01M15 14h.01" />
    </template>

    <template v-else-if="name === 'sun'">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </template>

    <template v-else-if="name === 'edit'">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
    </template>

    <template v-else-if="name === 'layers'">
      <path d="M12 2l9 5-9 5-9-5z" />
      <path d="M3 12l9 5 9-5M3 17l9 5 9-5" />
    </template>

    <template v-else-if="name === 'chat'">
      <path d="M21 12a8 8 0 0 1-8 8H5l-3 3 1-4a8 8 0 1 1 18-7z" />
    </template>

    <template v-else-if="name === 'graph'">
      <circle cx="5" cy="6" r="2" />
      <circle cx="19" cy="6" r="2" />
      <circle cx="12" cy="18" r="2" />
      <path d="M5 8v8M19 8v4M7 17l3.5-.5M17 12l-3.5.5" />
    </template>

    <template v-else-if="name === 'plug'">
      <path d="M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0z" />
      <path d="M12 17v5" />
    </template>

    <template v-else-if="name === 'clock'">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </template>

    <template v-else>
      <path d="M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z" />
      <path d="M9 12l2 2 4-4" />
    </template>
  </svg>
</template>

<style scoped>
.ficon { width: 21px; height: 21px; }
</style>
