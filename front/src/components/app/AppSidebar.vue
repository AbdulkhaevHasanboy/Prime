<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

interface UserSession {
  name: string
  email: string
  avatar: string
  provider: 'google' | 'password' | 'telegram'
  role: 'student' | 'educator'
}

const props = defineProps<{
  active: string
  collapsed: boolean
  user: UserSession
}>()

const emit = defineEmits<{
  (e: 'navigate', id: string): void
  (e: 'toggle'): void
}>()

const { t } = useI18n()

/* Nav items — id matches the `nav.*` i18n key. Icons are inline Lucide paths. */
const items = [
  { id: 'home', icon: '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/>' },
  { id: 'mentor', icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' },
  { id: 'sims', icon: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>' },
  { id: 'scan', icon: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>' },
  { id: 'comics', icon: '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>' },
  { id: 'poly', icon: '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>' },
  { id: 'tests', icon: '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>' },
  { id: 'leaderboard', icon: '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>' },
  { id: 'profile', icon: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>' },
] as const

const initials = computed(() => {
  const parts = props.user.name.trim().split(/\s+/)
  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1]![0] : ''
  return (first + last).toUpperCase() || 'U'
})
</script>

<template>
  <aside
    class="flex h-screen flex-shrink-0 flex-col bg-white/80 backdrop-blur-[16px] border-r border-solid border-slate-200 transition-[width] duration-[280ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
    :class="[collapsed ? 'w-[76px]' : 'w-[250px]', 'max-[900px]:w-[76px]']"
  >
    <div class="relative flex items-center gap-3 px-[14px] py-5">
      <div class="flex h-[48px] w-[48px] flex-shrink-0 items-center justify-center">
        <img src="/ico.png" alt="Logo" class="h-[48px] w-auto object-contain" />
      </div>
      <div class="flex flex-col overflow-hidden leading-[1.15] max-[900px]:hidden" v-if="!collapsed">
        <span class="font-display text-[1.05rem] font-extrabold tracking-[0.02em] bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">SIMULINK</span>
        <span class="whitespace-nowrap text-[0.66rem] text-ink-mute">{{ t('nav.tagline') }}</span>
      </div>
      <button class="absolute -right-[11px] top-[26px] z-[5] flex h-[22px] w-[22px] cursor-pointer items-center justify-center rounded-full bg-white border border-solid border-slate-200 shadow-sm text-ink-soft transition-all duration-200 hover:text-ink hover:border-indigo-400/50" @click="emit('toggle')" :title="t('sidebar.toggle')">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path :d="collapsed ? 'm9 18 6-6-6-6' : 'm15 18-6-6 6-6'"/></svg>
      </button>
    </div>

    <!-- Nav -->
    <nav class="flex flex-1 flex-col gap-1 overflow-y-auto px-3 py-2">
      <button
        v-for="item in items"
        :key="item.id"
        class="flex w-full cursor-pointer items-center gap-3 whitespace-nowrap rounded-[10px] border-none px-3 py-[11px] text-left font-body text-[0.9rem] font-medium transition-all duration-200"
        :class="[
          active === item.id
            ? 'bg-gradient-to-r from-indigo-500/15 to-violet-500/10 text-indigo-700 shadow-[inset_2px_0_0_#6366f1]'
            : 'bg-transparent text-ink-soft hover:bg-slate-100 hover:text-ink',
          collapsed ? 'justify-center' : '',
          'max-[900px]:justify-center',
        ]"
        :title="t(`nav.${item.id}`)"
        @click="emit('navigate', item.id)"
      >
        <svg class="flex-shrink-0" :class="active === item.id ? 'text-indigo-600' : ''" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="item.icon"></svg>
        <span class="max-[900px]:hidden" v-if="!collapsed">{{ t(`nav.${item.id}`) }}</span>
      </button>
    </nav>

    <!-- User footer -->
    <div class="flex items-center gap-3 px-[18px] py-4 border-t border-solid border-slate-200">
      <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-[0.9rem] font-bold text-white">{{ initials }}</div>
      <div class="flex flex-col overflow-hidden leading-[1.2] max-[900px]:hidden" v-if="!collapsed">
        <span class="overflow-hidden text-ellipsis whitespace-nowrap text-[0.9rem] font-semibold text-ink">{{ user.name }}</span>
        <span class="text-[0.74rem] text-ink-mute">{{ t('nav.level', { n: 12 }) }}</span>
      </div>
    </div>
  </aside>
</template>
