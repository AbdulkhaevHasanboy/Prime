<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Comic {
  id: string
  img?: string
  color: string
  pages: number
  /* Publisher/author shown as attribution on the cover. */
  publisher?: string
}

/* The Pushkin strip is the worked example. The rest are locked placeholders
   so the gallery reads as intentional until more comics are added. */
const comics: Comic[] = [
  { id: 'pushkin', img: '/comics/pushkin-i-muza.jpg', color: '#a855f7', pages: 6, publisher: 'SimuLink Studio' },
  { id: 'soon1', color: '#6366f1', pages: 0 },
  { id: 'soon2', color: '#8b5cf6', pages: 0 },
]

// Track cover images that failed to load so we can show a fallback.
const broken = reactive<Record<string, boolean>>({})
function onImgError(id: string) {
  broken[id] = true
}

const openId = ref<string | null>(null)
const openComic = ref<Comic | null>(null)

function open(c: Comic) {
  if (!c.img) return
  openComic.value = c
  openId.value = c.id
}
function close() {
  openId.value = null
  openComic.value = null
}

/* Creating your own comic is a Premium-gated action. Pressing the create
   card opens the subscription prompt rather than the (not-yet-built) editor. */
const showSubscribe = ref(false)
function openCreate() {
  showSubscribe.value = true
}
function closeSubscribe() {
  showSubscribe.value = false
}
</script>

<template>
  <div class="h-full overflow-y-auto relative">
    <div class="max-w-[1200px] mx-auto px-8 pt-8 pb-14 max-[720px]:px-4 max-[720px]:pt-6 max-[720px]:pb-12">
      <div class="mb-[26px]">
        <h1 class="font-display text-[1.9rem] font-extrabold bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">{{ t('comics.title') }}</h1>
        <p class="text-ink-soft mt-1 text-[0.95rem]">{{ t('comics.subtitle') }}</p>
      </div>

      <div class="grid grid-cols-4 gap-[18px] max-[1000px]:grid-cols-3 max-[720px]:grid-cols-2">
        <button
          v-for="c in comics"
          :key="c.id"
          class="group text-left bg-white border border-solid border-slate-200 shadow-sm rounded-[16px] overflow-hidden cursor-pointer transition-all duration-200 flex flex-col p-0 [&:not(.locked)]:hover:-translate-y-0.5 [&:not(.locked)]:hover:border-indigo-400/50 hover:shadow-[0_6px_16px_rgba(99,102,241,0.25)]"
          :class="{ 'locked !cursor-default opacity-70': !c.img }"
          @click="open(c)"
        >
          <div class="relative h-[220px] overflow-hidden flex items-center justify-center" :style="{ background: `linear-gradient(160deg, ${c.color}33, #0b1020)` }">
            <img
              v-if="c.img && !broken[c.id]"
              :src="c.img"
              :alt="t(`comics.items.${c.id}.title`)"
              class="w-full h-full object-cover object-top transition-transform duration-[0.4s] ease-[cubic-bezier(0.16,1,0.3,1)] [.group:not(.locked):hover_&]:scale-105"
              loading="lazy"
              @error="onImgError(c.id)"
            />
            <span v-else class="text-[2.6rem] opacity-50">{{ c.img ? '📖' : '🔒' }}</span>

            <span v-if="c.img" class="absolute top-[10px] right-[10px] text-[0.72rem] font-bold py-[5px] px-[11px] rounded-full backdrop-blur-[6px] text-white bg-violet-500/85">▶ {{ t('comics.read') }}</span>
            <span v-else class="absolute top-[10px] right-[10px] text-[0.72rem] font-bold py-[5px] px-[11px] rounded-full backdrop-blur-[6px] text-ink-soft bg-slate-900/40 border border-solid border-slate-200">{{ t('comics.soon') }}</span>
          </div>

          <div class="pt-[14px] px-4 pb-[18px] flex flex-col gap-[5px] flex-1">
            <template v-if="c.img">
              <span class="text-[0.72rem] font-bold tracking-[0.06em] uppercase text-violet-600">{{ t(`comics.items.${c.id}.subject`) }}</span>
              <h3 class="text-[1.02rem] font-bold text-ink">{{ t(`comics.items.${c.id}.title`) }}</h3>
              <p class="text-[0.84rem] text-ink-soft leading-[1.5] flex-1">{{ t(`comics.items.${c.id}.desc`) }}</p>
              <div class="flex items-center justify-between gap-2 mt-[2px]">
                <span v-if="c.publisher" class="inline-flex items-center gap-[5px] text-[0.78rem] text-ink-mute min-w-0">
                  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="flex-shrink-0"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                  <span class="truncate">{{ t('comics.by', { name: t(`comics.items.${c.id}.publisher`) }) }}</span>
                </span>
                <span class="text-[0.78rem] text-ink-mute flex-shrink-0">{{ t('comics.pages', { n: c.pages }) }}</span>
              </div>
            </template>
            <template v-else>
              <h3 class="text-[1.02rem] text-ink-mute font-semibold">{{ t('comics.soon') }}</h3>
            </template>
          </div>
        </button>

        <!-- Create-your-own card: shown where no comic exists. Premium-gated. -->
        <button
          class="group text-left border border-dashed border-indigo-400/50 bg-indigo-500/[0.04] rounded-[16px] overflow-hidden cursor-pointer transition-all duration-200 flex flex-col p-0 hover:-translate-y-0.5 hover:border-indigo-500 hover:bg-indigo-500/[0.08] hover:shadow-[0_6px_16px_rgba(99,102,241,0.2)]"
          @click="openCreate"
        >
          <div class="relative h-[220px] overflow-hidden flex items-center justify-center bg-gradient-to-br from-indigo-500/15 to-violet-500/15">
            <span class="flex items-center justify-center w-[64px] h-[64px] rounded-full bg-white/70 border border-solid border-indigo-400/40 text-indigo-600 transition-transform duration-300 group-hover:scale-110">
              <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
            </span>
            <span class="absolute top-[10px] right-[10px] inline-flex items-center gap-1 text-[0.72rem] font-bold py-[5px] px-[11px] rounded-full backdrop-blur-[6px] text-white bg-gradient-to-r from-indigo-500 to-violet-500">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="m15.477 12.89 1.515 8.526a.5.5 0 0 1-.81.47l-3.58-2.687a1 1 0 0 0-1.197 0l-3.586 2.686a.5.5 0 0 1-.81-.469l1.514-8.526"/><circle cx="12" cy="8" r="6"/></svg>
              Premium
            </span>
          </div>
          <div class="pt-[14px] px-4 pb-[18px] flex flex-col gap-[5px] flex-1">
            <h3 class="text-[1.02rem] font-bold text-ink">{{ t('comics.create.title') }}</h3>
            <p class="text-[0.84rem] text-ink-soft leading-[1.5] flex-1">{{ t('comics.create.desc') }}</p>
            <span class="inline-flex items-center gap-1 text-[0.82rem] font-bold text-indigo-600 mt-[2px]">
              {{ t('comics.create.cta') }}
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
            </span>
          </div>
        </button>
      </div>
    </div>

    <!-- Reader overlay -->
    <Transition name="reader-fade">
      <div v-if="openComic" class="absolute inset-0 z-50 bg-slate-900/80 backdrop-blur-[8px] flex flex-col" @click.self="close">
        <div class="flex-shrink-0 flex items-center justify-between py-[14px] px-[22px] border-b border-solid border-slate-200">
          <span class="font-bold text-[1.05rem] text-ink">{{ t(`comics.items.${openId}.title`) }}</span>
          <button class="w-[38px] h-[38px] rounded-[10px] border border-solid border-slate-200 bg-slate-100 text-ink-soft cursor-pointer flex items-center justify-center transition-all duration-200 hover:text-white hover:bg-red-500/[0.18] hover:border-red-500/40" @click="close" :title="t('comics.close')">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="flex-1 overflow-y-auto flex justify-center p-6">
          <img :src="openComic.img" :alt="t(`comics.items.${openId}.title`)" class="w-full max-w-[560px] h-fit rounded-[12px] shadow-[0_18px_50px_rgba(0,0,0,0.6)]" />
        </div>
      </div>
    </Transition>

    <!-- Subscription prompt for the create-your-own action -->
    <Transition name="reader-fade">
      <div v-if="showSubscribe" class="absolute inset-0 z-[60] flex items-center justify-center p-6 bg-slate-900/50 backdrop-blur-[6px]" @click.self="closeSubscribe">
        <div class="w-full max-w-[400px] bg-white border border-solid border-slate-200 rounded-[18px] p-6 shadow-[0_18px_50px_rgba(15,23,42,0.25)] text-center" role="dialog" aria-modal="true">
          <span class="inline-flex items-center justify-center w-[58px] h-[58px] rounded-full mx-auto mb-4 bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
            <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="m15.477 12.89 1.515 8.526a.5.5 0 0 1-.81.47l-3.58-2.687a1 1 0 0 0-1.197 0l-3.586 2.686a.5.5 0 0 1-.81-.469l1.514-8.526"/><circle cx="12" cy="8" r="6"/></svg>
          </span>
          <h3 class="text-[1.15rem] font-extrabold text-ink">{{ t('comics.subscribe.title') }}</h3>
          <p class="text-[0.9rem] text-ink-soft leading-[1.55] mt-2">{{ t('comics.subscribe.text') }}</p>
          <div class="flex flex-col gap-[10px] mt-5">
            <button class="inline-flex items-center justify-center gap-2 p-[12px] border-none rounded-[11px] bg-gradient-to-br from-indigo-500 to-violet-500 text-white text-[0.92rem] font-bold font-body cursor-pointer transition-all duration-200 hover:-translate-y-px hover:shadow-[0_6px_16px_rgba(99,102,241,0.3)]" @click="closeSubscribe">
              {{ t('comics.subscribe.cta') }}
            </button>
            <button class="p-[11px] rounded-[11px] bg-slate-100 border border-solid border-slate-200 text-ink-soft text-[0.9rem] font-semibold font-body cursor-pointer transition-all duration-200 hover:text-ink hover:bg-slate-200" @click="closeSubscribe">
              {{ t('comics.subscribe.cancel') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* Vue <Transition> enter/leave classes — cannot be expressed as Tailwind utilities. */
.reader-fade-enter-active,
.reader-fade-leave-active {
  transition: opacity 0.25s ease;
}
.reader-fade-enter-from,
.reader-fade-leave-to {
  opacity: 0;
}
</style>
