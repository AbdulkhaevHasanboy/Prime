import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: number
  message: string
  type: ToastType
  duration?: number
}

const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  const showToast = (message: string, type: ToastType = 'success', duration = 4000) => {
    const id = nextId++
    const toast: Toast = { id, message, type, duration }
    toasts.value.push(toast)

    setTimeout(() => {
      removeToast(id)
    }, duration)
  }

  const removeToast = (id: number) => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  return {
    toasts,
    showToast,
    removeToast,
  }
}
