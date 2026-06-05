<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const emit = defineEmits<{
  (e: 'open', payload: { id: string; topic: string }): void
}>()

const { t } = useI18n()

type Difficulty = 'easy' | 'medium' | 'hard'
type Category = 'biology' | 'physics' | 'chemistry' | 'astronomy' | 'math'

interface Sim {
  id: string
  category: Category
  color: string
  difficulty: Difficulty
  rating: number
  duration: number
  icon: string
}

const sims: Sim[] = [
  { id: 'photosynthesis', category: 'biology', color: '#6366f1', difficulty: 'easy', rating: 4.8, duration: 15, icon: '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6"/>' },
  { id: 'newton', category: 'physics', color: '#8b5cf6', difficulty: 'medium', rating: 4.9, duration: 20, icon: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>' },
  { id: 'reactions', category: 'chemistry', color: '#a855f7', difficulty: 'hard', rating: 4.7, duration: 25, icon: '<circle cx="12" cy="12" r="1"/><path d="M20.2 20.2c2.04-2.03.02-7.36-4.5-11.9-4.54-4.52-9.87-6.54-11.9-4.5-2.04 2.03-.02 7.36 4.5 11.9 4.54 4.52 9.87 6.54 11.9 4.5Z"/><path d="M15.7 15.7c4.52-4.54 6.54-9.87 4.5-11.9-2.03-2.04-7.36-.02-11.9 4.5-4.52 4.54-6.54 9.87-4.5 11.9 2.03 2.04 7.36.02 11.9-4.5Z"/>' },
  { id: 'solar', category: 'astronomy', color: '#818cf8', difficulty: 'easy', rating: 4.9, duration: 18, icon: '<circle cx="12" cy="12" r="3"/><circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><path d="M10.4 21.9a10 10 0 0 0 9.941-15.416"/><path d="M13.5 2.1a10 10 0 0 0-9.841 15.416"/>' },
  { id: 'mathRoots', category: 'math', color: '#a78bfa', difficulty: 'medium', rating: 4.8, duration: 22, icon: '<path d="M3 12h3.28a1 1 0 0 1 .948.684l2.298 7.934a.5.5 0 0 0 .96-.044L13.82 4.771A1 1 0 0 1 14.792 4H21"/>' },
  { id: 'circuit', category: 'physics', color: '#6366f1', difficulty: 'medium', rating: 4.6, duration: 20, icon: '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>' },
]

const categories: ('all' | Category)[] = ['all', 'biology', 'physics', 'chemistry', 'astronomy', 'math']
const activeCat = ref<'all' | Category>('all')
const query = ref('')

const filtered = computed(() =>
  sims.filter((s) => {
    if (activeCat.value !== 'all' && s.category !== activeCat.value) return false
    const q = query.value.trim().toLowerCase()
    if (!q) return true
    const title = t(`sims.items.${s.id}.title`).toLowerCase()
    const desc = t(`sims.items.${s.id}.desc`).toLowerCase()
    return title.includes(q) || desc.includes(q)
  }),
)

const DIFF_CLASSES: Record<Difficulty, string> = {
  easy: 'text-green-400 bg-green-400/[0.14]',
  medium: 'text-amber-400 bg-amber-400/[0.14]',
  hard: 'text-red-400 bg-red-400/[0.14]',
}

function open(s: Sim) {
  emit('open', { id: s.id, topic: t(`sims.items.${s.id}.title`) })
}
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-[1200px] mx-auto px-8 pt-8 pb-14 max-[620px]:px-[18px] max-[620px]:pt-6 max-[620px]:pb-12">
      <!-- Header -->
      <div class="flex justify-between items-start gap-[18px] flex-wrap mb-6">
        <div>
          <h1 class="font-display text-[1.9rem] font-extrabold bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">{{ t('sims.title') }}</h1>
          <p class="text-ink-soft mt-1 text-[0.95rem]">{{ t('sims.subtitle') }}</p>
        </div>
        <div class="flex gap-[10px] items-center">
          <div class="flex items-center gap-2 bg-white border border-solid border-slate-200 shadow-sm rounded-full py-[9px] px-4 text-ink-mute focus-within:border-indigo-400/50">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            <input v-model="query" type="text" :placeholder="t('sims.search')" class="bg-transparent border-none outline-none text-ink font-body text-[0.88rem] w-[200px] max-[620px]:w-[130px] placeholder:text-ink-mute" />
          </div>
          <button class="inline-flex items-center gap-[7px] bg-white border border-solid border-slate-200 shadow-sm rounded-full py-[9px] px-4 text-ink-soft font-body text-[0.88rem] font-semibold cursor-pointer transition-all duration-200 hover:text-ink hover:border-indigo-400/50">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
            {{ t('sims.filter') }}
          </button>
        </div>
      </div>

      <!-- Category tabs -->
      <div class="flex gap-[10px] flex-wrap mb-[26px]">
        <button
          v-for="c in categories"
          :key="c"
          class="py-[9px] px-5 rounded-full border border-solid font-body text-[0.88rem] font-semibold cursor-pointer transition-all duration-200"
          :class="activeCat === c ? 'bg-gradient-to-br from-indigo-500 to-violet-500 border-transparent text-white' : 'border-slate-200 bg-white shadow-sm text-ink-soft hover:text-ink hover:bg-slate-100'"
          @click="activeCat = c"
        >
          {{ t(`sims.categories.${c}`) }}
        </button>
      </div>

      <!-- Grid -->
      <div v-if="filtered.length" class="grid grid-cols-3 gap-[18px] max-[980px]:grid-cols-2 max-[620px]:grid-cols-1">
        <button v-for="s in filtered" :key="s.id" class="text-left bg-white border border-solid border-slate-200 shadow-sm rounded-2xl p-5 cursor-pointer transition-all duration-200 flex flex-col gap-[11px] hover:-translate-y-0.5 hover:border-indigo-400/50 hover:bg-slate-100 hover:shadow-md" @click="open(s)">
          <div class="flex justify-between items-start">
            <span class="w-[46px] h-[46px] rounded-[13px] flex items-center justify-center" :style="{ background: s.color + '22', color: s.color }">
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="s.icon"></svg>
            </span>
            <span class="text-[0.72rem] font-bold px-[11px] py-1 rounded-full" :class="DIFF_CLASSES[s.difficulty]">{{ t(`sims.difficulty.${s.difficulty}`) }}</span>
          </div>
          <h3 class="text-[1.08rem] font-bold text-ink">{{ t(`sims.items.${s.id}.title`) }}</h3>
          <p class="text-[0.86rem] text-ink-soft leading-[1.5] flex-1">{{ t(`sims.items.${s.id}.desc`) }}</p>
          <div class="flex gap-[18px] mt-1">
            <span class="inline-flex items-center gap-[6px] text-[0.82rem] text-ink-soft">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="#fbbf24" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              {{ s.rating }}
            </span>
            <span class="inline-flex items-center gap-[6px] text-[0.82rem] text-ink-soft">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              {{ t('sims.minutes', { n: s.duration }) }}
            </span>
          </div>
        </button>
      </div>
      <p v-else class="text-center text-ink-mute py-[60px]">{{ t('sims.empty') }}</p>
    </div>
  </div>
</template>
