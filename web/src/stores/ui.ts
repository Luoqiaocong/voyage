import { ref } from 'vue'
import { defineStore } from 'pinia'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  type: ToastType
  message: string
}

let toastSeq = 0

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<ToastItem[]>([])
  const confirmState = ref<{ message: string; resolve: (v: boolean) => void } | null>(null)

  function toast(message: string, type: ToastType = 'info', duration = 3200) {
    const id = ++toastSeq
    toasts.value.push({ id, type, message })
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, duration)
  }

  function confirm(message: string): Promise<boolean> {
    return new Promise((resolve) => {
      confirmState.value = { message, resolve }
    })
  }

  function resolveConfirm(v: boolean) {
    confirmState.value?.resolve(v)
    confirmState.value = null
  }

  return { toasts, confirmState, toast, confirm, resolveConfirm }
})
