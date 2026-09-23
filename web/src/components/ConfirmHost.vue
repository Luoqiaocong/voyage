<script setup lang="ts">
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

function ok() {
  ui.resolveConfirm(true)
}
function cancel() {
  ui.resolveConfirm(null)
}
function pick(value: string) {
  ui.resolveConfirm(value)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.confirmState" class="confirm-mask" @click.self="cancel">
      <div class="confirm-box card" role="dialog" aria-modal="true" aria-label="确认操作">
        <h3 class="confirm-title">请确认</h3>
        <p class="confirm-msg">{{ ui.confirmState.message }}</p>
        <div class="confirm-actions">
          <template v-if="ui.confirmState.choices?.length">
            <button
              v-for="c in ui.confirmState.choices"
              :key="c.value"
              class="btn"
              :class="{
                'btn-primary': c.kind === 'primary' || !c.kind,
                'btn-ghost': c.kind === 'ghost',
                'btn-danger': c.kind === 'danger'
              }"
              @click="pick(c.value)"
            >
              {{ c.label }}
            </button>
          </template>
          <template v-else>
            <button class="btn btn-ghost" @click="cancel">取消</button>
            <button class="btn btn-danger" @click="ok">确定</button>
          </template>
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
  width: min(440px, 100%);
  padding: 26px 26px 22px;
  text-align: center;
}

.confirm-title { font-size: 1.25rem; }

.confirm-msg { margin-top: 10px; color: var(--ink-soft); line-height: 1.65; }

.confirm-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: 22px;
}

.confirm-actions .btn { min-width: 96px; }

@media (max-width: 480px) {
  .confirm-actions { flex-direction: column; }
  .confirm-actions .btn { width: 100%; }
}

@keyframes fade {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
