import { ref } from 'vue'
import { defineStore } from 'pinia'

export type ToastType = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  type: ToastType
  message: string
}

export interface ConfirmChoice {
  label: string
  value: string
  kind?: 'primary' | 'ghost' | 'danger'
}

export interface ConfirmState {
  message: string
  choices?: ConfirmChoice[]
  resolve: (v: boolean | string | null) => void
}

let toastSeq = 0

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<ToastItem[]>([])
  const confirmState = ref<ConfirmState | null>(null)

  function toast(message: string, type: ToastType = 'info', duration = 3200) {
    const id = ++toastSeq
    toasts.value.push({ id, type, message })
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, duration)
  }

  function confirm(message: string): Promise<boolean> {
    return new Promise((resolve) => {
      confirmState.value = {
        message,
        resolve: (v) => resolve(v === true)
      }
    })
  }

  function confirmChoices(message: string, choices: ConfirmChoice[]): Promise<string | null> {
    return new Promise((resolve) => {
      confirmState.value = {
        message,
        choices,
        resolve: (v) => resolve(typeof v === 'string' ? v : null)
      }
    })
  }

  function resolveConfirm(v: boolean | string | null) {
    confirmState.value?.resolve(v)
    confirmState.value = null
  }

  return { toasts, confirmState, toast, confirm, confirmChoices, resolveConfirm }
})
