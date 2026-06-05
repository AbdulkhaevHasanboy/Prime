<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AvatarFrame from './AvatarFrame.vue'
import type { UserSession } from '../../managers/authManager'

const props = defineProps<{
  user: UserSession
}>()

const { t } = useI18n()

interface Entry {
  id: string
  name: string
  level: number
  xp: number
  achievements: number
  /* When set, this row is the signed-in user and is highlighted. */
  self?: boolean
}

/* Mock leaderboard — ranked by level and achievements. The signed-in user is
   injected so the board always shows a "You" row at their standing. */
const others: Entry[] = [
  { id: 'a', name: 'Dilnoza Karimova', level: 24, xp: 18420, achievements: 31 },
  { id: 'b', name: 'Jasur Rakhimov', level: 21, xp: 16100, achievements: 27 },
  { id: 'c', name: 'Madina Yusupova', level: 19, xp: 14250, achievements: 24 },
  { id: 'e', name: 'Sardor Aliyev', level: 14, xp: 9800, achievements: 16 },
  { id: 'f', name: 'Nigora Tosheva', level: 11, xp: 7400, achievements: 12 },
  { id: 'g', name: 'Bekzod Ismoilov', level: 9, xp: 5600, achievements: 9 },
  { id: 'h', name: 'Kamola Saidova', level: 7, xp: 4100, achievements: 6 },
]

const ranked = computed<Entry[]>(() => {
  const me: Entry = {
    id: 'me',
    name: props.user.name,
    level: 12,
    xp: 8350,
    achievements: 14,
    self: true,
  }
  return [...others, me].sort((x, y) => y.xp - x.xp)
})

const podium = computed(() => ranked.value.slice(0, 3))
const rest = computed(() => ranked.value.slice(3))

function rankOf(e: Entry) {
  return ranked.value.indexOf(e) + 1
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/)
  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1]![0] : ''
  return (first + last).toUpperCase() || 'U'
}

/* Podium ordering: 2nd, 1st, 3rd so the winner sits in the middle. */
const podiumOrder = computed(() => {
  const p = podium.value
  return [p[1], p[0], p[2]].filter(Boolean) as Entry[]
})

const medalColor: Record<number, string> = { 1: '#fbbf24', 2: '#cbd5e1', 3: '#d97706' }

/* Discord-style avatar decoration awarded by rank. Podium (1-3) gets the
   legendary toppers; 4-6 a subtle sparkle; 7-10 just a tier rim. */
type FrameVariant = 'crown' | 'wings' | 'cat' | 'sparkle' | 'ring'
const FRAME_VARIANT: Record<number, FrameVariant> = {
  1: 'crown',
  2: 'wings',
  3: 'cat',
  4: 'sparkle',
  5: 'sparkle',
  6: 'sparkle',
  7: 'ring',
  8: 'ring',
  9: 'ring',
  10: 'ring',
}
function frameFor(rank: number) {
  return FRAME_VARIANT[rank] ?? null
}

const scope = ref<'all' | 'week'>('all')
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-[960px] mx-auto px-8 pt-8 pb-14 max-[720px]:px-4 max-[720px]:pt-6 max-[720px]:pb-12">
      <div class="flex items-end justify-between gap-4 flex-wrap mb-[26px]">
        <div>
          <h1 class="font-display text-[1.9rem] font-extrabold bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">{{ t('leaderboard.title') }}</h1>
          <p class="text-ink-soft mt-1 text-[0.95rem]">{{ t('leaderboard.subtitle') }}</p>
        </div>
        <div class="inline-flex bg-slate-100 border border-solid border-slate-200 rounded-[11px] p-1 gap-1">
          <button
            v-for="s in (['all', 'week'] as const)"
            :key="s"
            class="px-[14px] py-[7px] rounded-[8px] text-[0.82rem] font-semibold font-display cursor-pointer transition-all duration-200"
            :class="scope === s ? 'bg-white text-ink shadow-sm' : 'bg-transparent text-ink-soft hover:text-ink'"
            @click="scope = s"
          >{{ t(`leaderboard.scope.${s}`) }}</button>
        </div>
      </div>

      <!-- Podium: top 3 -->
      <div class="grid grid-cols-3 gap-3 items-end mb-7 max-[560px]:gap-2">
        <div
          v-for="p in podiumOrder"
          :key="p.id"
          class="flex flex-col items-center text-center rounded-[16px] border border-solid p-[18px] transition-all"
          :class="[
            rankOf(p) === 1 ? 'bg-gradient-to-b from-amber-50 to-white border-amber-300 -mt-4 shadow-[0_8px_24px_rgba(251,191,36,0.18)]' : 'bg-white border-slate-200 shadow-sm',
            p.self ? 'ring-2 ring-indigo-400' : '',
          ]"
        >
          <div class="relative mt-5">
            <AvatarFrame :initials="initials(p.name)" :size="80" :variant="frameFor(rankOf(p))" />
            <span class="absolute -bottom-1 -right-1 w-[22px] h-[22px] rounded-full flex items-center justify-center text-[0.72rem] font-extrabold text-white border-2 border-solid border-white z-[3]" :style="{ background: medalColor[rankOf(p)] }">{{ rankOf(p) }}</span>
          </div>
          <span class="mt-[10px] text-[0.9rem] font-bold text-ink truncate max-w-full">{{ p.self ? t('leaderboard.you') : p.name }}</span>
          <span class="text-[0.78rem] text-ink-mute">{{ t('nav.level', { n: p.level }) }}</span>
          <span class="mt-[6px] font-display text-[1.05rem] font-extrabold text-indigo-600">{{ p.xp.toLocaleString() }} <small class="text-[0.7rem] font-semibold text-ink-mute">{{ t('leaderboard.xpUnit') }}</small></span>
          <span class="inline-flex items-center gap-1 mt-[4px] text-[0.76rem] text-ink-soft">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="#fbbf24" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            {{ p.achievements }}
          </span>
        </div>
      </div>

      <!-- Ranked list (4th onward) -->
      <div class="bg-white border border-solid border-slate-200 rounded-[18px] shadow-sm overflow-hidden">
        <div class="grid grid-cols-[56px_minmax(0,1fr)_auto_auto] gap-3 items-center px-[18px] py-[11px] border-b border-solid border-slate-200 text-[0.72rem] font-bold uppercase tracking-[0.05em] text-ink-mute max-[560px]:grid-cols-[44px_minmax(0,1fr)_auto]">
          <span>{{ t('leaderboard.rank') }}</span>
          <span>{{ t('leaderboard.learner') }}</span>
          <span class="text-right max-[560px]:hidden">{{ t('leaderboard.achievements') }}</span>
          <span class="text-right">{{ t('leaderboard.xpUnit') }}</span>
        </div>
        <div
          v-for="e in rest"
          :key="e.id"
          class="grid grid-cols-[56px_minmax(0,1fr)_auto_auto] gap-3 items-center px-[18px] py-[13px] border-b border-solid border-slate-100 last:border-b-0 transition-colors duration-200 max-[560px]:grid-cols-[44px_minmax(0,1fr)_auto]"
          :class="e.self ? 'bg-indigo-500/[0.07]' : 'hover:bg-slate-50'"
        >
          <span class="font-display font-extrabold text-ink-soft text-[0.95rem]">{{ rankOf(e) }}</span>
          <div class="flex items-center gap-3 min-w-0">
            <AvatarFrame :initials="initials(e.name)" :size="46" :variant="frameFor(rankOf(e))" />
            <div class="flex flex-col min-w-0">
              <span class="text-[0.9rem] font-semibold text-ink truncate">{{ e.self ? t('leaderboard.you') : e.name }}</span>
              <span class="text-[0.74rem] text-ink-mute">{{ t('nav.level', { n: e.level }) }}</span>
            </div>
          </div>
          <span class="inline-flex items-center justify-end gap-1 text-[0.84rem] text-ink-soft max-[560px]:hidden">
            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="#fbbf24" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            {{ e.achievements }}
          </span>
          <span class="text-right font-display font-bold text-indigo-600 text-[0.9rem]">{{ e.xp.toLocaleString() }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
