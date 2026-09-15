<script setup lang="ts">
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
</script>

<template>
  <div class="toast-host" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in ui.toasts" :key="t.id" class="toast" :class="`toast--${t.type}`">
        <span class="toast__icon" aria-hidden="true">
          {{ t.type === 'success' ? '✓' : t.type === 'error' ? '!' : 'i' }}
        </span>
        <span>{{ t.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 300;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  max-width: min(92vw, 480px);
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 18px;
  border-radius: 12px;
  background: var(--ink);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 500;
  box-shadow: var(--shadow-md);
  max-width: 100%;
}

.toast__icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 0.78rem;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.18);
}

.toast--success { background: var(--success); }
.toast--error { background: var(--danger); }

.toast-enter-active, .toast-leave-active { transition: all 0.25s ease; }
.toast-enter-from { opacity: 0; transform: translateY(12px) scale(0.96); }
.toast-leave-to { opacity: 0; transform: translateY(8px) scale(0.97); }
</style>
