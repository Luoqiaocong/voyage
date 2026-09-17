<script setup lang="ts">
/**
 * 轻量地图纹理（纯内联 SVG，无外部图片依赖）。
 *
 * 设计意图：给页面一层「旅行」的暗示，但不能抢内容。
 * 因此只画抽象的大陆轮廓 + 航线 + 经纬网格，全部用 currentColor 低透明度描边，
 * 由父容器通过 color 控制明暗（浅色主题下极淡，深色主题下自动反相）。
 *
 * 为什么不用真实地图图片：
 *   位图在高分屏上会糊、体积大、且深浅主题要维护两张；矢量方案零成本适配。
 */
withDefaults(
  defineProps<{
    /** 航线是否显示（Hero 用 true，背景用 false 更克制） */
    routes?: boolean
  }>(),
  { routes: false }
)
</script>

<template>
  <svg
    class="map"
    viewBox="0 0 1200 620"
    fill="none"
    preserveAspectRatio="xMidYMid slice"
    aria-hidden="true"
  >
    <!-- 经纬网格：交叉点做小圆点，像地图上的城市标记 -->
    <g class="map__grid">
      <path d="M0 90h1200M0 190h1200M0 290h1200M0 390h1200M0 490h1200" />
      <path d="M120 0v620M320 0v620M520 0v620M720 0v620M920 0v620M1120 0v620" />
    </g>

    <!-- 抽象大陆轮廓：只取形状感，不追求地理精确 -->
    <g class="map__land">
      <path
        d="M118 214c34-40 96-58 152-46 44 9 62 34 106 40 40 6 70-10 104 4 30 12 34 42 16 62
           -22 24-64 22-96 34-30 11-52 34-88 32-40-2-58-30-92-40-34-10-72 2-96-22-20-20-18-42-6-64z"
      />
      <path
        d="M610 150c46-26 118-30 166-8 32 15 40 44 74 54 30 9 62-2 86 18 20 17 14 44-10 56
           -30 15-70 6-104 14-36 9-58 34-96 30-36-4-48-32-80-42-34-11-72 0-92-26-16-22 10-46 56-96z"
      />
      <path
        d="M232 470c30-16 74-14 104 2 24 13 26 36 8 50-20 16-56 12-84 4-26-8-44-28-28-56z"
      />
      <path
        d="M906 452c36-14 84-6 108 14 18 15 10 36-12 44-30 11-72 6-100-6-24-11-26-38 4-52z"
      />
    </g>

    <!-- 航线：虚线 + 两端站点，构成「出发 → 抵达」的暗示 -->
    <g v-if="routes" class="map__routes">
      <path d="M180 250C420 120 640 120 860 210" stroke-dasharray="5 7" />
      <circle cx="180" cy="250" r="4.5" />
      <circle cx="860" cy="210" r="4.5" />
      <path d="M300 420c150-70 300-60 420 20" stroke-dasharray="5 7" />
      <circle cx="300" cy="420" r="3.5" />
      <circle cx="720" cy="440" r="3.5" />
    </g>
  </svg>
</template>

<style scoped>
.map {
  width: 100%;
  height: 100%;
  display: block;
}

/* 网格与陆地轮廓用极低透明度，避免与正文争夺注意力 */
.map__grid path {
  stroke: currentColor;
  stroke-opacity: 0.1;
  stroke-width: 1;
}
.map__land path {
  stroke: currentColor;
  stroke-opacity: 0.16;
  stroke-width: 1.3;
  fill: currentColor;
  fill-opacity: 0.028;
}
.map__routes path {
  stroke: currentColor;
  stroke-opacity: 0.34;
  stroke-width: 1.5;
  fill: none;
}
.map__routes circle {
  fill: currentColor;
  fill-opacity: 0.5;
}
</style>
