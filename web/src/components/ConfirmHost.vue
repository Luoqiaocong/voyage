<script setup lang="ts">
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

function ok() {
  ui.resolveConfirm(true)
}
function cancel() {
  ui.resolveConfirm(false)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.confirmState" class="confirm-mask" @click.self="cancel">
      <div class="confirm-box card" role="dialog" aria-modal="true" aria-label="确认操作">
        <h3 class="confirm-title">请确认</h3>
        <p class="confirm-msg">{{ ui.confirmState.message }}</p>
        <div class="confirm-actions">
          <button class="btn btn-ghost" @click="cancel">取消</button>
          <button class="btn btn-danger" @click="ok">确定</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.confirm-mask {
  position: fixed;
  inset: 0;
  z-index: 250;
  background: rgba(16, 28, 40, 0.42);
  display: grid;
  place-items: center;
  padding: 20px;
  animation: fade 0.18s ease;
}

.confirm-box {
  width: min(420px, 100%);
  padding: 26px 26px 22px;
  text-align: center;
}

.confirm-title { font-size: 1.25rem; }

.confirm-msg { margin-top: 10px; color: var(--ink-soft); }

.confirm-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 22px;
}

@keyframes fade {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
