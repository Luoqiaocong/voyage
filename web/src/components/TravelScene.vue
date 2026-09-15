<script setup lang="ts">
/**
 * TravelScene · 清爽冷调旅行场景（纯内联 SVG，零外链）
 *
 * 四套场景，按「一天的旅途时刻」叙事，但统一为明亮冷调：
 *   dawn  晨雾山谷 —— 出发
 *   coast 海岸航线 —— 在路上
 *   peak  雪线之上 —— 开阔
 *   city  城市天际 —— 抵达
 *
 * 分层绘制（天空 → 远景 → 中景 → 近景），配合 depth 做鼠标视差。
 */
withDefaults(
  defineProps<{
    scene?: 'dawn' | 'coast' | 'peak' | 'city'
    /** 视差强度 0~1 */
    depth?: number
    /** 是否显示航线与飞行光点 */
    route?: boolean
  }>(),
  { scene: 'dawn', depth: 0.6, route: true }
)
</script>

<template>
  <div class="scene" :class="`scene--${scene}`" role="img" aria-label="旅行场景插画">
    <svg class="scene__svg" viewBox="0 0 800 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <!-- 天空：明亮冷调渐变 -->
        <linearGradient id="skyCool" x1="0" y1="0" x2="0.25" y2="1">
          <stop offset="0%" stop-color="#dceafa" />
          <stop offset="45%" stop-color="#eaf3fb" />
          <stop offset="100%" stop-color="#f7f9fc" />
        </linearGradient>
        <linearGradient id="skyCoast" x1="0" y1="0" x2="0.25" y2="1">
          <stop offset="0%" stop-color="#cfe4f7" />
          <stop offset="50%" stop-color="#e4f0fa" />
          <stop offset="100%" stop-color="#f5f9fd" />
        </linearGradient>
        <linearGradient id="skyPeak" x1="0" y1="0" x2="0.25" y2="1">
          <stop offset="0%" stop-color="#d3e6f9" />
          <stop offset="55%" stop-color="#e8f2fb" />
          <stop offset="100%" stop-color="#f8fbfd" />
        </linearGradient>
        <linearGradient id="skyCity" x1="0" y1="0" x2="0.3" y2="1">
          <stop offset="0%" stop-color="#c9dff5" />
          <stop offset="50%" stop-color="#e2eefa" />
          <stop offset="100%" stop-color="#f6fafd" />
        </linearGradient>

        <!-- 山体：冷蓝灰层次（远近靠明度区分） -->
        <linearGradient id="ridgeFar" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#b9d4ee" />
          <stop offset="100%" stop-color="#cfe2f3" />
        </linearGradient>
        <linearGradient id="ridgeMid" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#8db4dc" />
          <stop offset="100%" stop-color="#aecbe8" />
        </linearGradient>
        <linearGradient id="ridgeNear" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#5b8cbd" />
          <stop offset="100%" stop-color="#7ba6cf" />
        </linearGradient>

        <!-- 海面 -->
        <linearGradient id="seaCool" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#a8c9e8" />
          <stop offset="100%" stop-color="#8fb8de" />
        </linearGradient>

        <!-- 太阳光晕（冷白偏青，不是暖黄） -->
        <radialGradient id="sunCool">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95" />
          <stop offset="40%" stop-color="#e8f4ff" stop-opacity="0.6" />
          <stop offset="100%" stop-color="#cfe6f8" stop-opacity="0" />
        </radialGradient>

        <!-- 航线 -->
        <linearGradient id="routeCool" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#2b6cb0" stop-opacity="0" />
          <stop offset="50%" stop-color="#3182ce" stop-opacity="0.8" />
          <stop offset="100%" stop-color="#0ea5e9" stop-opacity="0" />
        </linearGradient>

        <clipPath id="sceneClip2"><rect width="800" height="1000" /></clipPath>
      </defs>

      <g clip-path="url(#sceneClip2)">
        <!-- ============ 天空 ============ -->
        <rect
          width="800"
          height="1000"
          :fill="
            scene === 'coast'
              ? 'url(#skyCoast)'
              : scene === 'peak'
                ? 'url(#skyPeak)'
                : scene === 'city'
                  ? 'url(#skyCity)'
                  : 'url(#skyCool)'
          "
        />

        <!-- 柔和光晕（晨光，冷白） -->
        <circle cx="580" cy="240" r="210" fill="url(#sunCool)" />
        <circle cx="580" cy="240" r="46" fill="#ffffff" opacity="0.9" />

        <!-- ============ 云：轻盈白色 ============ -->
        <g opacity="0.75">
          <path d="M-40 220 q 48 -30 96 -8 q 42 -26 86 4 q 46 -12 70 20 H -40 Z" fill="#ffffff" opacity="0.7" />
          <path d="M460 128 q 42 -26 84 -6 q 38 -22 76 6 q 40 -10 62 18 H 460 Z" fill="#ffffff" opacity="0.55" />
          <path d="M110 392 q 56 -32 112 -6 q 48 -28 100 8 q 52 -14 82 22 H 110 Z" fill="#ffffff" opacity="0.45" />
        </g>

        <!-- ============ 远景山脊 ============ -->
        <g class="scene__layer" :style="{ transform: `translateX(${depth * 6}px)` }">
          <path
            v-if="scene !== 'coast'"
            d="M-20 640 L 96 468 L 178 566 L 268 402 L 372 588 L 462 470 L 566 610 L 668 486 L 820 640 Z"
            fill="url(#ridgeFar)"
          />
          <path
            v-else
            d="M-20 620 L 120 500 L 230 590 L 340 470 L 470 596 L 590 500 L 700 596 L 820 520 L 820 660 L -20 660 Z"
            fill="url(#ridgeFar)"
          />
        </g>

        <!-- 雪线（peak / dawn） -->
        <g v-if="scene === 'peak' || scene === 'dawn'" opacity="0.95">
          <path d="M268 402 L 300 452 L 316 430 L 340 470 L 306 462 L 288 480 Z" fill="#ffffff" opacity="0.85" />
          <path d="M462 470 L 486 512 L 500 494 L 518 528 L 488 518 Z" fill="#ffffff" opacity="0.7" />
        </g>

        <!-- ============ 中景山脊 ============ -->
        <g class="scene__layer" :style="{ transform: `translateX(${depth * 12}px)` }">
          <path
            d="M-20 760 L 110 596 L 226 700 L 330 552 L 448 706 L 560 590 L 676 716 L 820 610 L 820 820 L -20 820 Z"
            fill="url(#ridgeMid)"
          />
          <!-- 松树剪影 -->
          <g fill="#4a7aa8" opacity="0.55">
            <path d="M150 640 l 12 30 h -24 Z M150 620 l 10 26 h -20 Z" />
            <path d="M500 632 l 13 32 h -26 Z M500 610 l 11 28 h -22 Z" />
            <path d="M700 700 l 11 28 h -22 Z" />
          </g>
        </g>

        <!-- ============ 海面（coast） ============ -->
        <g v-if="scene === 'coast'" class="scene__layer" :style="{ transform: `translateX(${depth * 12}px)` }">
          <path d="M-20 742 L 820 742 L 820 1020 L -20 1020 Z" fill="url(#seaCool)" />
          <g stroke="#ffffff" stroke-width="2" fill="none" opacity="0.5" stroke-linecap="round">
            <path d="M60 800 q 40 -12 80 0 t 80 0" />
            <path d="M420 830 q 44 -14 88 0 t 88 0" />
            <path d="M140 880 q 50 -16 100 0 t 100 0" />
            <path d="M560 918 q 46 -14 92 0 t 92 0" />
          </g>
          <path d="M556 742 h 64 l -10 120 h -44 Z" fill="#ffffff" opacity="0.25" />
        </g>

        <!-- ============ 近景山脊 ============ -->
        <g class="scene__layer" :style="{ transform: `translateX(${depth * 20}px)` }">
          <path
            d="M-20 900 L 150 742 L 300 856 L 430 726 L 590 878 L 720 780 L 820 858 L 820 1020 L -20 1020 Z"
            fill="url(#ridgeNear)"
          />
          <g stroke="#8fb8de" stroke-width="1.5" opacity="0.5" fill="none">
            <path d="M100 950 q 10 -18 22 -24 M300 962 q 12 -20 26 -26 M560 946 q 10 -16 22 -22 M700 980 q 12 -18 24 -24" />
          </g>
        </g>

        <!-- ============ 城市天际（city） ============ -->
        <g v-if="scene === 'city'" class="scene__layer" :style="{ transform: `translateX(${depth * 20}px)` }">
          <g fill="#5b8cbd">
            <rect x="60" y="700" width="58" height="320" />
            <rect x="134" y="626" width="46" height="394" />
            <rect x="196" y="742" width="70" height="278" />
            <rect x="284" y="586" width="52" height="434" />
            <rect x="352" y="690" width="44" height="330" />
            <rect x="412" y="648" width="62" height="372" />
            <rect x="490" y="736" width="48" height="284" />
            <rect x="554" y="606" width="56" height="414" />
            <rect x="626" y="704" width="66" height="316" />
            <rect x="708" y="660" width="52" height="360" />
          </g>
          <g fill="#ffffff" opacity="0.5">
            <rect x="146" y="650" width="7" height="9" /><rect x="162" y="650" width="7" height="9" />
            <rect x="146" y="678" width="7" height="9" /><rect x="162" y="706" width="7" height="9" />
            <rect x="296" y="612" width="7" height="9" /><rect x="314" y="612" width="7" height="9" />
            <rect x="296" y="648" width="7" height="9" /><rect x="314" y="686" width="7" height="9" />
            <rect x="566" y="632" width="7" height="9" /><rect x="584" y="632" width="7" height="9" />
            <rect x="566" y="670" width="7" height="9" /><rect x="584" y="712" width="7" height="9" />
            <rect x="426" y="672" width="7" height="9" /><rect x="446" y="700" width="7" height="9" />
            <rect x="720" y="686" width="7" height="9" /><rect x="738" y="722" width="7" height="9" />
          </g>
        </g>

        <!-- ============ 航线 ============ -->
        <g v-if="route" class="scene__route">
          <path
            id="voyageRoute2"
            d="M40 902 C 200 700, 330 560, 470 430 S 690 240, 762 176"
            fill="none"
            stroke="#3182ce"
            stroke-width="2.4"
            stroke-linecap="round"
            stroke-dasharray="2 13"
            opacity="0.55"
            class="scene__dash"
          />
          <g fill="#2b6cb0">
            <circle cx="200" cy="700" r="4" />
            <circle cx="470" cy="430" r="4" />
          </g>
          <circle cx="200" cy="700" r="9" fill="none" stroke="#3182ce" stroke-width="1.3" opacity="0.4" />
          <circle cx="470" cy="430" r="9" fill="none" stroke="#3182ce" stroke-width="1.3" opacity="0.4" />

          <!-- 小飞机 -->
          <g class="scene__plane">
            <circle r="11" fill="#3182ce" opacity="0.14" />
            <path
              d="M-7 0 L-1 -1.6 L-1 -5.5 L1 -5.5 L1 -1.6 L7 0 L7 1.8 L1 1.2 L1 4.6 L3 6 L3 7.2 L0 6.4 L-3 7.2 L-3 6 L-1 4.6 L-1 1.2 L-7 1.8 Z"
              fill="#2b6cb0"
            />
          </g>
        </g>
      </g>
    </svg>

    <div class="scene__veil" aria-hidden="true"></div>
  </div>
</template>

<style scoped>
.scene {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: linear-gradient(160deg, #dceafa, #f7f9fc);
}

.scene__svg { width: 100%; height: 100%; }

.scene__layer { transition: transform 0.6s cubic-bezier(0.2, 0.7, 0.2, 1); will-change: transform; }

.scene__dash { animation: routeFlow 2.6s linear infinite; }
@keyframes routeFlow { to { stroke-dashoffset: -60; } }

/* 小飞机沿航线飞行 */
.scene__plane {
  offset-path: path('M40 902 C 200 700, 330 560, 470 430 S 690 240, 762 176');
  offset-rotate: auto;
  animation: fly 16s linear infinite;
}
@keyframes fly {
  0% { offset-distance: 0%; opacity: 0; }
  10% { opacity: 1; }
  90% { opacity: 1; }
  100% { offset-distance: 100%; opacity: 0; }
}

/* 底部轻微渐隐，让表单区自然过渡（冷白，不要重色） */
.scene__veil {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(
    to bottom,
    transparent 0%,
    transparent 62%,
    rgba(247, 249, 252, 0.35) 82%,
    rgba(247, 249, 252, 0.7) 100%
  );
}

@media (prefers-reduced-motion: reduce) {
  .scene__dash, .scene__plane { animation: none; }
  .scene__plane { opacity: 0; }
}
</style>
