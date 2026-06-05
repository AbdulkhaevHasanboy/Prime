<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const emit = defineEmits<{
  (e: 'navigate', id: string): void
}>()

const { t } = useI18n()

/* Feature highlights — id matches the `poly.features.*` i18n key. */
const features = [
  { id: 'avatar', icon: '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>' },
  { id: 'lipsync', icon: '<path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/>' },
  { id: 'voice', icon: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/>' },
  { id: 'interactive', icon: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/>' },
] as const
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-[760px] mx-auto px-7 pt-14 pb-16 flex flex-col items-center text-center max-[600px]:px-[18px] max-[600px]:pt-10 max-[600px]:pb-[52px]">
      <!-- Animated avatar -->
      <div class="relative w-[168px] h-[168px] flex items-center justify-center mb-7">
        <span class="anim absolute rounded-full border border-solid border-indigo-400/40 w-[150px] h-[150px] border-dashed animate-[spin_18s_linear_infinite]"></span>
        <span class="anim absolute rounded-full border border-solid border-purple-500/[0.22] w-[168px] h-[168px] animate-[spin_26s_linear_infinite_reverse]"></span>
        <span class="anim absolute w-[130px] h-[130px] rounded-full bg-[radial-gradient(circle,rgba(139,92,246,0.5),transparent_68%)] blur-[8px] z-[1] animate-[pulse_4s_ease-in-out_infinite]"></span>
        <div class="anim relative z-[2] w-[104px] h-[104px] rounded-[28px] flex items-center justify-center text-white bg-gradient-to-br from-indigo-400 via-violet-500 to-purple-500 [background-position:55%] shadow-[0_18px_44px_rgba(99,102,241,0.45),inset_0_1px_0_rgba(255,255,255,0.3)] animate-[float_4s_ease-in-out_infinite]">
          <svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>
          </svg>
        </div>
        <span class="anim absolute w-2 h-2 rounded-full z-[3] top-2 right-[26px] bg-violet-400 shadow-[0_0_10px_#a78bfa] animate-[twinkle_2.4s_ease-in-out_infinite]"></span>
        <span class="anim absolute rounded-full z-[3] bottom-[18px] left-[18px] w-1.5 h-1.5 bg-purple-500 shadow-[0_0_10px_#a855f7] animate-[twinkle_3s_ease-in-out_infinite_0.6s]"></span>
        <span class="anim absolute rounded-full z-[3] top-10 left-1.5 w-[5px] h-[5px] bg-indigo-400 shadow-[0_0_8px_#818cf8] animate-[twinkle_2.8s_ease-in-out_infinite_1.1s]"></span>
      </div>

      <span class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[0.72rem] font-bold tracking-[0.08em] uppercase text-violet-700 bg-violet-400/10 border border-solid border-violet-400/40">
        <span class="anim w-[7px] h-[7px] rounded-full bg-violet-400 shadow-[0_0_8px_#a78bfa] animate-[pulse_1.8s_ease-in-out_infinite]"></span>
        {{ t('poly.badge') }}
      </span>

      <h1 class="mt-[18px] font-display text-[2.4rem] font-extrabold tracking-[-0.02em] bg-gradient-to-r from-indigo-600 via-violet-600 to-purple-600 bg-clip-text text-transparent max-[600px]:text-[2rem]">{{ t('poly.title') }}</h1>
      <p class="mt-3.5 max-w-[540px] text-base leading-[1.65] text-ink-soft">{{ t('poly.subtitle') }}</p>

      <!-- Feature grid -->
      <div class="mt-[38px] w-full grid grid-cols-2 gap-3.5 max-[600px]:grid-cols-1">
        <div v-for="f in features" :key="f.id" class="flex items-start gap-3.5 p-[18px] text-left rounded-[16px] bg-white shadow-sm border border-solid border-slate-200 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_6px_16px_rgba(99,102,241,0.25)] hover:border-indigo-400/50 hover:bg-indigo-50">
          <span class="flex-shrink-0 w-[42px] h-[42px] rounded-[12px] flex items-center justify-center text-violet-600 bg-gradient-to-br from-indigo-400/[0.16] to-purple-500/[0.14] border border-solid border-indigo-400/30">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="f.icon"></svg>
          </span>
          <div class="flex flex-col gap-[3px] min-w-0">
            <span class="text-[0.95rem] font-bold text-ink">{{ t(`poly.features.${f.id}.title`) }}</span>
            <span class="text-[0.83rem] leading-[1.45] text-ink-mute">{{ t(`poly.features.${f.id}.text`) }}</span>
          </div>
        </div>
      </div>

      <!-- CTAs -->
      <div class="mt-10 flex gap-3 flex-wrap justify-center">
        <button class="inline-flex items-center gap-[9px] px-[26px] py-[13px] rounded-[13px] font-body text-[0.92rem] font-bold cursor-pointer transition-all duration-200 border-none text-white bg-gradient-to-br from-indigo-500 to-violet-500 shadow-[0_8px_22px_rgba(99,102,241,0.32)] hover:-translate-y-0.5 hover:shadow-[0_6px_16px_rgba(99,102,241,0.25)]" @click="emit('navigate', 'mentor')">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          {{ t('poly.ctaMentor') }}
        </button>
        <button class="inline-flex items-center gap-[9px] px-[26px] py-[13px] rounded-[13px] font-body text-[0.92rem] font-bold cursor-pointer transition-all duration-200 bg-slate-100 border border-solid border-slate-200 text-ink hover:text-ink hover:border-slate-300" @click="emit('navigate', 'home')">{{ t('poly.back') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Component-local keyframes — Tailwind can't express these inline. */
@keyframes float {
  0%, 100% { transform: translateY(0) rotate(-1.5deg); }
  50% { transform: translateY(-12px) rotate(1.5deg); }
}

@keyframes pulse {
  0%, 100% { opacity: 0.55; transform: scale(0.95); }
  50% { opacity: 1; transform: scale(1.05); }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes twinkle {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.3); }
}

@media (prefers-reduced-motion: reduce) {
  .anim {
    animation: none;
  }
}
</style>
