<script setup lang="ts">
/**
 * 应用外壳：路由出口 + 全局浮层。
 *
 * 这个文件是「首次进入空白」问题的兜底防线，因此有三处刻意设计：
 *
 * 1. Suspense 包住路由出口
 *    所有页面都是懒加载（() => import(...)）。没有 Suspense 时，
 *    chunk 下载期间 RouterView 渲染出的是空 —— 网速慢时就是一片白。
 *    现在下载期间显示骨架屏，用户立刻知道「在加载」而不是「坏了」。
 *
 * 2. 不用 mode="out-in"
 *    out-in 要求旧页面先离场（0.22s）再挂载新页面，而新页面的 chunk
 *    可能还没下载完，中间会出现一段真实的空窗。默认模式让新旧交替重叠，
 *    观感更连贯。
 *
 * 3. 捕获异步组件加载失败
 *    发版后旧 chunk 被清理、或网络中断时，import 会 reject。
 *    没有兜底就是永久白屏，只能靠用户手动刷新。这里给出重试按钮。
 */
import { onErrorCaptured, ref } from 'vue'
import ToastHost from '@/components/ToastHost.vue'
import ConfirmHost from '@/components/ConfirmHost.vue'
import TravelIcon from '@/components/TravelIcon.vue'
import { routeLoading } from '@/router/state'

/** 懒加载失败时的错误对象；非空则整页显示重试界面 */
const loadError = ref<Error | null>(null)

onErrorCaptured((err) => {
  // 只接管「资源加载失败」这一类，业务异常仍按原有方式冒泡到页面自行处理
  const msg = String((err as Error)?.message ?? '')
  if (/Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(msg)) {
    loadError.value = err as Error
    return false // 阻止继续冒泡，避免控制台重复报错
  }
  return true
})

function retry() {
  loadError.value = null
  // 整页重载：失败的 chunk 会被重新请求（浏览器已缓存失败结果的除外）
  window.location.reload()
}
</script>

<template>
  <a class="skip-link" href="#main">跳到主要内容</a>

  <!-- 顶部进度条：路由切换期间可见，给「正在加载」一个即时反馈 -->
  <Transition name="bar">
    <div v-if="routeLoading" class="route-bar" role="status" aria-label="页面加载中"></div>
  </Transition>

  <!-- 懒加载失败：给出可操作的出口，而不是白屏 -->
  <div v-if="loadError" class="load-fail">
    <div class="load-fail__card">
      <span class="load-fail__icon" aria-hidden="true">
        <TravelIcon name="alert" :size="26" />
      </span>
      <h1>页面没能加载出来</h1>
      <p>可能是网络波动，或应用刚更新过。重试一次通常就好了。</p>
      <div class="load-fail__ops">
        <button class="btn btn-primary" @click="retry">重新加载</button>
        <a class="btn btn-ghost" href="/">返回首页</a>
      </div>
    </div>
  </div>

  <template v-else>
    <RouterView v-slot="{ Component, route }">
      <Suspense>
        <template #default>
          <!-- key 用 path：同一组件换参数（如不同行程详情）也能重新挂载 -->
          <component :is="Component" :key="route.path" />
        </template>
        <template #fallback>
          <!-- 首屏与切页共用的骨架：保持结构感，避免大片留白 -->
          <div class="route-skel">
            <div class="container route-skel__inner">
              <span class="skel skel--title"></span>
              <span class="skel skel--text"></span>
              <div class="route-skel__cards">
                <span class="skel skel--card"></span>
                <span class="skel skel--card"></span>
                <span class="skel skel--card"></span>
              </div>
            </div>
          </div>
        </template>
      </Suspense>
    </RouterView>
  </template>

  <ToastHost />
  <ConfirmHost />
</template>

<style>
/* ==================== 顶部进度条 ==================== */
.route-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  z-index: 90;
  background: var(--grad);
  transform-origin: left;
  animation: barGrow 1.4s cubic-bezier(0.2, 0.7, 0.2, 1) forwards;
  box-shadow: 0 0 8px var(--glow);
}
@keyframes barGrow {
  0% { transform: scaleX(0); }
  45% { transform: scaleX(0.72); }
  100% { transform: scaleX(0.94); }
}
.bar-leave-active { transition: opacity 0.25s ease; }
.bar-leave-to { opacity: 0; }

/* ==================== 路由骨架屏 ==================== */
.route-skel { padding: 48px 0; min-height: 60vh; }
.route-skel__inner { display: flex; flex-direction: column; gap: 14px; }
.route-skel__cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin-top: 18px;
}

/* 全局定义骨架块：多个页面共用同一套加载观感 */
.skel {
  display: block;
  border-radius: 8px;
  background: linear-gradient(
    90deg,
    var(--surface-soft) 25%,
    var(--panel2) 37%,
    var(--surface-soft) 63%
  );
  background-size: 400% 100%;
  animation: skelShine 1.4s ease infinite;
}
.skel--title { height: 30px; width: 42%; border-radius: 10px; }
.skel--text { height: 14px; width: 66%; }
.skel--card { height: 132px; border-radius: 14px; }

@keyframes skelShine {
  0% { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}

@media (prefers-reduced-motion: reduce) {
  .skel { animation: none; }
  .route-bar { animation: none; transform: scaleX(0.9); }
}

/* ==================== 加载失败 ==================== */
.load-fail {
  min-height: 70vh;
  display: grid;
  place-items: center;
  padding: 40px 20px;
}
.load-fail__card {
  max-width: 420px;
  text-align: center;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-l);
  padding: 38px 30px;
  box-shadow: var(--shadow);
}
.load-fail__icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  border-radius: 16px;
  background: var(--gold-soft);
  color: var(--gold-600);
}
.load-fail__card h1 { font-size: 1.25rem; margin-bottom: 10px; }
.load-fail__card p { font-size: 0.88rem; color: var(--text2); line-height: 1.7; }
.load-fail__ops {
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-top: 22px;
  flex-wrap: wrap;
}
</style>
