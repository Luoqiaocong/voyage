<script setup lang="ts">
// 纯装饰插图：复古航线图（广州 → 北京），无交互
</script>

<template>
  <div class="map" role="img" aria-label="从广州到北京的 AI 航线规划示意图">
    <svg class="map__svg" viewBox="0 0 560 460" fill="none" aria-hidden="true">
      <defs>
        <pattern id="dotgrid" width="22" height="22" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.4" fill="#16304a" opacity="0.16" />
        </pattern>
        <linearGradient id="routeGlow" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#1f7a8c" />
          <stop offset="1" stop-color="#3d6fb4" />
        </linearGradient>
      </defs>

      <!-- 底图：点阵 + 同心纬线 -->
      <rect x="40" y="30" width="480" height="400" rx="210" fill="url(#dotgrid)" opacity="0.75" />
      <circle cx="280" cy="230" r="150" stroke="#16304a" opacity="0.12" stroke-dasharray="2 8" />
      <circle cx="280" cy="230" r="205" stroke="#16304a" opacity="0.07" stroke-dasharray="2 10" />

      <!-- 经纬辅助线 -->
      <path d="M 130 60 Q 190 230 130 400" stroke="#16304a" opacity="0.08" />
      <path d="M 430 60 Q 370 230 430 400" stroke="#16304a" opacity="0.08" />
      <path d="M 60 170 Q 280 140 500 170" stroke="#16304a" opacity="0.08" />
      <path d="M 60 290 Q 280 320 500 290" stroke="#16304a" opacity="0.08" />

      <!-- 罗盘 (右上角) -->
      <g transform="translate(452, 92)" opacity="0.92">
        <circle r="26" stroke="#16304a" stroke-width="1.2" opacity="0.55" />
        <path d="M 0 -20 L 4 0 L 0 20 L -4 0 Z" fill="#1f7a8c" />
        <path d="M 0 -20 L 0 20 M -20 0 L 20 0" stroke="#16304a" stroke-width="1" opacity="0.35" />
        <circle r="2.4" fill="#16304a" />
      </g>

      <!-- 航线（虚线流光动画） -->
      <path
        id="route"
        d="M 128 318 Q 230 108 396 152"
        stroke="url(#routeGlow)"
        stroke-width="3"
        stroke-linecap="round"
        stroke-dasharray="1 10"
        class="route-dash"
      />

      <!-- 沿航线飞行的光点 -->
      <circle r="5" fill="#fff" stroke="#16304a" stroke-width="2">
        <animateMotion dur="5s" repeatCount="indefinite" rotate="auto">
          <mpath href="#route" />
        </animateMotion>
      </circle>
      <circle r="1.8" fill="#1f7a8c">
        <animateMotion dur="5s" repeatCount="indefinite" begin="1s" rotate="auto">
          <mpath href="#route" />
        </animateMotion>
      </circle>

      <!-- 中途站点 -->
      <circle cx="242" cy="216" r="6" fill="#ffffff" stroke="#3d6fb4" stroke-width="2" />
      <circle cx="242" cy="216" r="1.8" fill="#3d6fb4" />

      <!-- 城市图钉 -->
      <g class="pin" transform="translate(128, 318)">
        <path d="M 0 2 C -16 -10 -13 -30 0 -34 C 13 -30 16 -10 0 2 Z" fill="#1f7a8c" />
        <circle cy="-16" r="6" fill="#eef3f6" />
        <text x="14" y="10" class="pin-label">广州</text>
      </g>
      <g class="pin" transform="translate(396, 152)">
        <path d="M 0 2 C -16 -10 -13 -30 0 -34 C 13 -30 16 -10 0 2 Z" fill="#16304a" />
        <circle cy="-16" r="6" fill="#eef3f6" />
        <text x="10" y="8" class="pin-label pin-label--end">北京</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.map { position: relative; }

.map__svg { width: 100%; height: auto; }

.route-dash { animation: cruise 1.1s linear infinite; }

@keyframes cruise {
  to { stroke-dashoffset: -11; }
}

.pin-label {
  font-size: 13px;
  fill: var(--ink);
  font-family: var(--sans);
  font-weight: 600;
  letter-spacing: 0.06em;
}

.pin-label--end { fill: #eef3f6; }
</style>
