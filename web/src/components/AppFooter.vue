<script setup lang="ts">
// 页脚纯静态展示
</script>

<template>
  <footer class="footer">
    <div class="container footer__inner">
      <div class="footer__brand">
        <span class="footer__mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none">
            <circle cx="16" cy="16" r="14" stroke="currentColor" stroke-width="2.6" />
            <path
              d="M16 4.5 L18.8 13.2 L27.5 16 L18.8 18.8 L16 27.5 L13.2 18.8 L4.5 16 L13.2 13.2 Z"
              fill="currentColor"
            />
            <circle cx="16" cy="16" r="2.2" fill="var(--panel)" />
          </svg>
        </span>
        <span class="footer__name">Voyage <em>AI</em></span>
      </div>

      <p class="footer__tagline">像和资深向导聊天一样，把旅程交给 AI。</p>
    </div>
  </footer>
</template>

<style scoped>
.footer {
  margin-top: 80px;
  border-top: 1px solid var(--hairline);
  background: var(--bg2);
  position: relative;
  z-index: 1;
}

.footer__inner {
  padding: 40px 0 30px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 20px 32px;
}

.footer__brand { display: flex; align-items: center; gap: 10px; }

.footer__mark {
  width: 30px;
  height: 30px;
  color: var(--prim);
  display: grid;
  place-items: center;
}
.footer__mark svg { width: 24px; height: 24px; }

.footer__name {
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.footer__name em { font-style: normal; color: var(--prim); }

/* 原先这里有一组 .ver-chip 样式，用于页脚的「MVP v0.1.0」版本标签。
   该标签已按用户要求去掉，样式一并删除，避免留下无引用的规则。 */

.footer__tagline { color: var(--text2); font-size: 0.88rem; }

@media (max-width: 640px) {
  .footer__tagline { display: none; }
  .footer__inner { justify-content: flex-start; }
}
</style>
