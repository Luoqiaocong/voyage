<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const boxRef = ref<HTMLElement | null>(null)
/** 打开对话框前的焦点元素；关闭时归还焦点，键盘用户不会「掉到页面顶部」 */
let lastFocused: HTMLElement | null = null

function ok() {
  ui.resolveConfirm(true)
}
function cancel() {
  ui.resolveConfirm(null)
}
function pick(value: string) {
  ui.resolveConfirm(value)
}

/** 对话框内当前可聚焦的元素（用于初始聚焦与 Tab 循环） */
function focusables(): HTMLElement[] {
  const el = boxRef.value
  if (!el) return []
  return Array.from(
    el.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
  ).filter((n) => !n.hasAttribute('disabled'))
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    cancel()
    return
  }
  if (e.key !== 'Tab') return
  const list = focusables()
  if (!list.length) return
  const first = list[0]
  const last = list[list.length - 1]
  const active = document.activeElement as HTMLElement | null
  const inside = !!boxRef.value && !!active && boxRef.value.contains(active)
  if (e.shiftKey && (!inside || active === first)) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && (!inside || active === last)) {
    e.preventDefault()
    first.focus()
  }
}

/*
 * 对话框的键盘可达性：role="dialog" 只是给读屏器的声明，
 * 若不主动管理焦点，键盘用户仍会把 Tab 走进背后的页面（焦点陷阱缺失），
 * Esc 也无法关闭。这里补齐：打开时聚焦第一个按钮、Tab 在内部循环、
 * Esc 取消、关闭后把焦点还给触发者。
 */
watch(
  () => ui.confirmState,
  async (state) => {
    if (state) {
      lastFocused = document.activeElement as HTMLElement | null
      window.addEventListener('keydown', onKeydown, true)
      await nextTick()
      focusables()[0]?.focus()
    } else {
      window.removeEventListener('keydown', onKeydown, true)
      lastFocused?.focus?.()
      lastFocused = null
    }
  }
)

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown, true)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="ui.confirmState" class="confirm-mask" @click.self="cancel">
      <div ref="boxRef" class="confirm-box card" role="dialog" aria-modal="true" aria-label="确认操作">
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
