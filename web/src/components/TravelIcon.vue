<script setup lang="ts">
/**
 * TravelIcon · 旅行语义图标集（线性，跟随 currentColor）
 * 覆盖：出发/抵达、交通、自然、凭证、账户等
 */
defineProps<{ name: string; size?: number }>()
</script>

<template>
  <svg
    class="ticon"
    :style="size ? { width: size + 'px', height: size + 'px' } : undefined"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.65"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- 邮件 / 信封 -->
    <template v-if="name === 'mail'">
      <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
      <path d="M3 7l9 6 9-6" />
    </template>

    <!-- 锁 -->
    <template v-else-if="name === 'lock'">
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3M12 15v2" />
    </template>

    <!-- 用户 -->
    <template v-else-if="name === 'user'">
      <circle cx="12" cy="8.5" r="3.8" />
      <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
    </template>

    <!-- 退出登录：门框 + 向外箭头 -->
    <template v-else-if="name === 'sign-out'">
      <path d="M9.5 3.5H6.2A1.7 1.7 0 0 0 4.5 5.2v13.6a1.7 1.7 0 0 0 1.7 1.7h3.3" />
      <path d="M15 8.2l3.8 3.8-3.8 3.8M18.8 12H9" />
    </template>

    <!-- 下拉箭头：账号菜单的展开指示 -->
    <template v-else-if="name === 'chevron-down'">
      <path d="M6.5 9.5l5.5 5.5 5.5-5.5" />
    </template>

    <!-- 齿轮 / 设置：管理台入口 -->
    <template v-else-if="name === 'gear'">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 13.5a7.7 7.7 0 0 0 0-3l1.8-1.4-1.9-3.2-2.1.9a7.6 7.6 0 0 0-2.6-1.5L14.3 3h-3.6l-.3 2.3a7.6 7.6 0 0 0-2.6 1.5l-2.1-.9L3.8 9.1l1.8 1.4a7.7 7.7 0 0 0 0 3l-1.8 1.4 1.9 3.2 2.1-.9a7.6 7.6 0 0 0 2.6 1.5l.3 2.3h3.6l.3-2.3a7.6 7.6 0 0 0 2.6-1.5l2.1.9 1.9-3.2z" />
    </template>

    <!-- 盾牌 / 验证码 -->
    <template v-else-if="name === 'shield'">
      <path d="M12 2.5l7.5 3.4v5.6c0 4.6-3.2 7.6-7.5 9.4-4.3-1.8-7.5-4.8-7.5-9.4V5.9z" />
      <path d="M9.2 12l2.1 2.1 3.9-4.2" />
    </template>

    <!-- 飞机 -->
    <template v-else-if="name === 'plane'">
      <path d="M10.5 3.2a1.6 1.6 0 0 1 3 0l1.1 5.3 5.5 3.1v2.2l-5.6-1.5-1 4.6 2.4 1.7v1.6L12 19.4l-3.9 1.8v-1.6l2.4-1.7-1-4.6L3.9 14.8v-2.2l5.5-3.1z" />
    </template>

    <!-- 行李箱 -->
    <template v-else-if="name === 'luggage'">
      <rect x="5" y="7.5" width="14" height="12.5" rx="2.5" />
      <path d="M9 7.5V5.2A1.7 1.7 0 0 1 10.7 3.5h2.6A1.7 1.7 0 0 1 15 5.2v2.3M9.5 11v5.5M14.5 11v5.5" />
    </template>

    <!-- 护照 -->
    <template v-else-if="name === 'passport'">
      <rect x="4.5" y="2.8" width="15" height="18.4" rx="2.4" />
      <circle cx="12" cy="10" r="3.2" />
      <path d="M8.8 10h6.4M12 6.8c1.4 1.9 1.4 4.5 0 6.4M12 6.8c-1.4 1.9-1.4 4.5 0 6.4M9 17.4h6" />
    </template>

    <!-- 地图 / 目的地 -->
    <template v-else-if="name === 'map'">
      <path d="M9 3.6 3.6 5.8v14.6L9 18.2l6 2.2 5.4-2.2V3.6L15 5.8z" />
      <path d="M9 3.6v14.6M15 5.8v14.6" />
    </template>

    <!-- 指南针 -->
    <template v-else-if="name === 'compass'">
      <circle cx="12" cy="12" r="9" />
      <path d="M15.4 8.6 13.6 13.6 8.6 15.4l1.8-5z" />
    </template>

    <!-- 山 -->
    <template v-else-if="name === 'mountain'">
      <path d="M2.5 19.5h19L14.5 7l-3.2 5.6-1.9-3z" />
      <path d="M12.4 10.6 14.5 7l3 5.3" />
    </template>

    <!-- 海浪 -->
    <template v-else-if="name === 'wave'">
      <path d="M2.5 8.5c2.4-2.6 4.8-2.6 7.2 0s4.8 2.6 7.2 0 4.6-2.4 4.6-2.4" />
      <path d="M2.5 14c2.4-2.6 4.8-2.6 7.2 0s4.8 2.6 7.2 0" />
      <path d="M2.5 19.5c2.4-2.6 4.8-2.6 7.2 0" />
    </template>

    <!-- 太阳 -->
    <template v-else-if="name === 'sun'">
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 2.4v2.2M12 19.4v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2.4 12h2.2M19.4 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6" />
    </template>

    <!-- 帐篷 -->
    <template v-else-if="name === 'tent'">
      <path d="M12 4 2.8 19.6h18.4z" />
      <path d="M12 4v15.6M9 19.6 12 12l3 7.6" />
    </template>

    <!-- 相机 / 胶片 -->
    <template v-else-if="name === 'camera'">
      <path d="M3 8.2a2 2 0 0 1 2-2h2.2l1.3-2h7l1.3 2H19a2 2 0 0 1 2 2v9.6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <circle cx="12" cy="12.8" r="3.6" />
    </template>

    <!-- 钥匙 -->
    <template v-else-if="name === 'key'">
      <circle cx="7.8" cy="15.2" r="3.8" />
      <path d="M10.6 12.5 20 3.2M17 6.4l2 2M14.4 9l2 2" />
    </template>

    <!-- 时钟 -->
    <template v-else-if="name === 'clock'">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5.2l3.4 2" />
    </template>

    <!-- 微信 -->
    <template v-else-if="name === 'wechat'">
      <path d="M9.2 3.6c-4 0-7.2 2.6-7.2 5.9 0 1.9 1.1 3.6 2.8 4.7l-.7 2.2 2.6-1.4c.8.2 1.6.3 2.5.3h.5a5.4 5.4 0 0 1-.2-1.5c0-3.2 3-5.7 6.8-5.7h.6C16 5.4 12.9 3.6 9.2 3.6z" />
      <path d="M22 13.6c0-2.7-2.7-4.9-6-4.9s-6 2.2-6 4.9 2.7 4.9 6 4.9c.7 0 1.4-.1 2-.3l2.2 1.2-.6-1.9c1.5-.9 2.4-2.4 2.4-3.9z" />
    </template>

    <!-- Apple -->
    <template v-else-if="name === 'apple'">
      <path d="M16.3 12.4c0-2.3 1.9-3.4 2-3.5-1.1-1.6-2.8-1.8-3.4-1.9-1.5-.1-2.8.9-3.6.9-.8 0-1.9-.9-3.1-.8-1.6 0-3.1.9-3.9 2.4-1.7 2.9-.4 7.1 1.2 9.4.8 1.1 1.7 2.4 3 2.4 1.2 0 1.6-.8 3.1-.8 1.4 0 1.8.8 3.1.8 1.3 0 2.1-1.2 2.9-2.3.9-1.3 1.3-2.6 1.3-2.7-.1 0-2.6-1-2.6-3.9z" />
      <path d="M14.1 5.4c.6-.8 1.1-1.9 1-3-.9 0-2 .6-2.7 1.4-.6.7-1.1 1.8-1 2.9 1 .1 2.1-.5 2.7-1.3z" />
    </template>

    <!-- Google -->
    <template v-else-if="name === 'google'">
      <path d="M21.4 12.2c0-.7-.1-1.4-.2-2H12v3.9h5.3a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.7 2.9-4.3 2.9-7.4z" />
      <path d="M12 21.6c2.7 0 4.9-.9 6.5-2.4l-3.2-2.5c-.9.6-2 .9-3.3.9-2.6 0-4.7-1.7-5.5-4H3.2v2.6A9.6 9.6 0 0 0 12 21.6z" />
      <path d="M6.5 13.6a5.7 5.7 0 0 1 0-3.6V7.4H3.2a9.6 9.6 0 0 0 0 8.7z" />
      <path d="M12 6.1c1.5 0 2.8.5 3.8 1.5l2.8-2.8A9.6 9.6 0 0 0 3.2 7.4l3.3 2.6c.8-2.3 2.9-3.9 5.5-3.9z" />
    </template>

    <!-- 眼睛 -->
    <template v-else-if="name === 'eye'">
      <path d="M2.2 12S5.6 5.8 12 5.8 21.8 12 21.8 12 18.4 18.2 12 18.2 2.2 12 2.2 12z" />
      <circle cx="12" cy="12" r="3.1" />
    </template>

    <!-- 闭眼 -->
    <template v-else-if="name === 'eye-off'">
      <path d="M9.6 5.9A9.4 9.4 0 0 1 12 5.8c6.4 0 9.8 6.2 9.8 6.2a17 17 0 0 1-3 3.8M6.5 7.4A16.6 16.6 0 0 0 2.2 12S5.6 18.2 12 18.2c1.2 0 2.3-.2 3.3-.5" />
      <path d="M10 10.2a3.1 3.1 0 0 0 4.3 4.3M3.5 3.5l17 17" />
    </template>

    <!-- 月亮（深色模式） -->
    <template v-else-if="name === 'moon'">
      <path d="M20.5 13.4A8.6 8.6 0 1 1 10.6 3.5a6.9 6.9 0 0 0 9.9 9.9z" />
    </template>

    <!-- 星 -->
    <template v-else-if="name === 'star'">
      <path d="M12 3.4l2.6 5.6 6.1.8-4.5 4.2 1.2 6-5.4-3-5.4 3 1.2-6L3.3 9.8l6.1-.8z" />
    </template>

    <!-- 箭头右 -->
    <template v-else-if="name === 'arrow-right'">
      <path d="M4.5 12h15M13 5.5l6.5 6.5-6.5 6.5" />
    </template>

    <!-- 箭头上：返回顶部按钮。与 arrow-right 同一套笔画与端点风格，
         保证两个方向放在一起时粗细、箭头开口一致 -->
    <template v-else-if="name === 'arrow-up'">
      <path d="M12 19.5v-15M5.5 11 12 4.5 18.5 11" />
    </template>

    <!-- 返回 -->
    <template v-else-if="name === 'arrow-left'">
      <path d="M19.5 12h-15M11 5.5 4.5 12 11 18.5" />
    </template>

    <!-- 勾 -->
    <template v-else-if="name === 'check'">
      <path d="M20 6.5 9.2 17.3 4 12.1" />
    </template>

    <!-- 提示 -->
    <template v-else-if="name === 'alert'">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.6v5.2M12 16.2h.01" />
    </template>

    <template v-else-if="name === 'train'">
      <!-- 车次：原有代码已在使用该名称，此前落到 fallback 渲染成日落图标，语义不符 -->
      <rect x="5" y="3" width="14" height="12" rx="3" />
      <path d="M5 9.5h14M9.5 19l1.2-3M14.5 19l-1.2-3M9 12.2h.01M15 12.2h.01M7.5 19h9" />
    </template>

    <template v-else-if="name === 'chat'">
      <!-- 对话：同上，此前也落到 fallback -->
      <path d="M21 12a8.2 8.2 0 0 1-8.2 8.2H6.4L2.5 22l1.1-4.4A8.2 8.2 0 1 1 21 12z" />
      <path d="M8.6 11.4h.01M12 11.4h.01M15.4 11.4h.01" />
    </template>

    <template v-else-if="name === 'edit'">
      <!-- 编辑铅笔：HomeView 的行程预览卡已在用该名称，此前落到 fallback -->
      <path d="M4 20h4.2L19 9.2a2.1 2.1 0 0 0-3-3L5.2 17z" />
      <path d="M14.5 6.7l2.8 2.8" />
    </template>

    <template v-else-if="name === 'route'">
      <!-- 航线：用于地图纹理上的路径点缀 -->
      <circle cx="5.5" cy="18.5" r="2.5" />
      <circle cx="18.5" cy="5.5" r="2.5" />
      <path d="M8 18.5h5.2a3 3 0 0 0 0-6H9.8a3 3 0 0 1 0-6H16" stroke-dasharray="2.4 2.6" />
    </template>

    <template v-else-if="name === 'spark'">
      <!-- 智能/生成：用于「实时数据」等科技感点缀 -->
      <path d="M12 3.5l1.7 4.4 4.4 1.7-4.4 1.7-1.7 4.4-1.7-4.4L5.9 9.6l4.4-1.7z" />
      <path d="M18.5 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
    </template>

    <!-- 日落 / 启程 -->
    <template v-else>
      <path d="M2.5 18.5h19" />
      <path d="M6.5 18.5a5.5 5.5 0 0 1 11 0" />
      <path d="M12 3.5v2.6M4.6 6.6l1.8 1.8M19.4 6.6l-1.8 1.8M1.8 13.4h2.4M19.8 13.4h2.4" />
    </template>
  </svg>
</template>

<style scoped>
.ticon { width: 18px; height: 18px; flex-shrink: 0; }
</style>
