<script setup lang="ts">
import { useToast } from '../../composables/useToast'

const { toasts, removeToast } = useToast()

const INFO_TYPE = { border: 'border-l-4 border-l-blue-500', icon: 'text-blue-500' }

const TYPE_CLASSES: Record<string, { border: string; icon: string }> = {
  success: { border: 'border-l-4 border-l-emerald-500', icon: 'text-emerald-500' },
  error: { border: 'border-l-4 border-l-red-500', icon: 'text-red-500' },
  warning: { border: 'border-l-4 border-l-amber-500', icon: 'text-amber-500' },
  info: INFO_TYPE,
}

const typeClasses = (type: string) => TYPE_CLASSES[type] ?? INFO_TYPE
</script>

<template>
  <div class="toast-container fixed top-[24px] right-[24px] z-[100] flex flex-col gap-3 max-w-[400px] w-[calc(100%-48px)] pointer-events-none">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="[
          'toast-item pointer-events-auto relative flex items-center gap-3 p-4 rounded-xl bg-white/95 backdrop-blur-[12px] border border-solid border-slate-200 shadow-[0_10px_30px_rgba(15,23,42,0.15)] text-ink text-[0.9rem] font-medium cursor-pointer overflow-hidden transition-all duration-300 hover:-translate-y-0.5 hover:bg-white hover:border-slate-300',
          typeClasses(toast.type).border,
        ]"
        @click="removeToast(toast.id)"
      >
        <!-- Icon based on type -->
        <span :class="['toast-icon flex items-center justify-center flex-shrink-0', typeClasses(toast.type).icon]">
          <svg v-if="toast.type === 'success'" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
          <svg v-else-if="toast.type === 'error'" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          <svg v-else-if="toast.type === 'warning'" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
        </span>
        <span class="toast-message flex-grow leading-snug">{{ toast.message }}</span>
        <button class="toast-close-btn flex items-center justify-center bg-none border-none text-ink-mute cursor-pointer transition-all duration-200 hover:text-ink">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
        <div class="toast-progress absolute bottom-0 left-0 h-[3px] w-full bg-current opacity-20 origin-left" :style="{ animationDuration: `${toast.duration || 4000}ms` }"></div>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
/* Progress bar shrink animation (Tailwind cannot express custom @keyframes) */
.toast-progress {
  animation: shrink linear forwards;
}

@keyframes shrink {
  from { transform: scaleX(1); }
  to { transform: scaleX(0); }
}

/* Vue TransitionGroup enter/leave animations (cannot be expressed via Tailwind utilities) */
.toast-enter-active {
  animation: slide-in 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
.toast-leave-active {
  animation: slide-out 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes slide-in {
  from {
    opacity: 0;
    transform: translateX(100px) translateY(-10px) scale(0.9);
  }
  to {
    opacity: 1;
    transform: translateX(0) translateY(0) scale(1);
  }
}

@keyframes slide-out {
  from {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
  to {
    opacity: 0;
    transform: translateX(100px) scale(0.9);
  }
}
</style>
