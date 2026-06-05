<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const emit = defineEmits<{
  (e: 'navigate', id: string): void
}>()

const { t } = useI18n()

const stats = [
  { value: '10K+', key: 'users' },
  { value: '25+', key: 'subjects' },
  { value: '500+', key: 'sims' },
  { value: '98%', key: 'satisfaction' },
] as const

/* icon = inline Lucide paths, color = accent, target = page to open on click */
const features = [
  { id: 'sim3d', color: '#22d3ee', target: 'sims', icon: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>' },
  { id: 'comics', color: '#a855f7', target: 'comics', icon: '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>' },
  { id: 'mentor', color: '#38bdf8', target: 'mentor', icon: '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>' },
  { id: 'tests', color: '#34d399', target: 'tests', icon: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>' },
] as const
</script>

<template>
  <div class="home-scroll h-full overflow-y-auto relative">
    <!-- Animated ambient background -->
    <div class="pointer-events-none fixed inset-0 overflow-hidden -z-10">
      <div class="blob blob-a"></div>
      <div class="blob blob-b"></div>
      <div class="blob blob-c"></div>
    </div>

    <div class="max-w-[1100px] mx-auto px-8 pt-10 pb-16 max-[560px]:px-[18px] max-[560px]:pt-7 max-[560px]:pb-12">
      <!-- Hero -->
      <section class="text-center flex flex-col items-center">
        <span class="reveal inline-flex items-center gap-[7px] py-[7px] px-4 rounded-full text-[0.8rem] font-semibold text-cyan-600 bg-cyan-400/10 border border-solid border-cyan-400/25" style="--d:0ms">
          <svg class="spin-slow" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
          {{ t('home.badge') }}
        </span>
        <h1 class="reveal title-glow font-display text-[clamp(2.8rem,7vw,4.6rem)] font-extrabold tracking-[0.01em] mt-[22px] mb-1 bg-[length:200%_auto] bg-gradient-to-r from-sky-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent" style="--d:80ms">SIMULINK</h1>
        <p class="reveal text-[1.15rem] text-ink-soft" style="--d:180ms">{{ t('home.subtitle') }}</p>
        <p class="reveal italic text-teal-600 mt-2 text-base" style="--d:260ms">{{ t('home.quote') }}</p>

        <div class="flex gap-[14px] mt-[30px] flex-wrap justify-center">
          <button class="reveal group inline-flex items-center gap-[9px] py-[13px] px-[26px] rounded-xl font-body text-[0.95rem] font-bold cursor-pointer transition-all duration-200 border border-solid border-transparent bg-gradient-to-br from-cyan-500 to-sky-500 text-white shadow-[0_8px_24px_rgba(6,182,212,0.3)] hover:-translate-y-[2px] hover:shadow-[0_12px_34px_rgba(6,182,212,0.5)] active:translate-y-0" style="--d:340ms" @click="emit('navigate', 'sims')">
            <svg class="transition-transform duration-300 group-hover:rotate-[18deg] group-hover:scale-110" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>
            {{ t('home.ctaSims') }}
          </button>
          <button class="reveal group inline-flex items-center gap-[9px] py-[13px] px-[26px] rounded-xl font-body text-[0.95rem] font-bold cursor-pointer transition-all duration-200 border border-solid border-indigo-400/40 bg-indigo-500/[0.12] text-indigo-700 hover:bg-indigo-500/[0.22] hover:-translate-y-[2px] active:translate-y-0" style="--d:420ms" @click="emit('navigate', 'mentor')">
            <svg class="transition-transform duration-300 group-hover:scale-110" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/></svg>
            {{ t('home.ctaMentor') }}
          </button>
        </div>

        <!-- Stats -->
        <div class="grid grid-cols-4 gap-4 w-full max-w-[820px] mt-11 max-[860px]:grid-cols-2">
          <div class="reveal pop-hover bg-white border border-solid border-slate-200 shadow-sm rounded-[14px] py-5 px-[14px] flex flex-col gap-1 transition-all duration-200 hover:border-sky-400/30 hover:shadow-md" v-for="(s, i) in stats" :key="s.key" :style="{ '--d': 500 + i * 90 + 'ms' }">
            <span class="font-display text-[1.7rem] font-extrabold bg-gradient-to-r from-sky-600 to-purple-600 bg-clip-text text-transparent">{{ s.value }}</span>
            <span class="text-[0.82rem] text-ink-soft">{{ t(`home.stats.${s.key}`) }}</span>
          </div>
        </div>
      </section>

      <!-- Features -->
      <section class="mt-16">
        <h2 class="reveal text-center font-display text-[1.8rem] font-extrabold mb-7" style="--d:880ms">
          {{ t('home.featuresTitle') }} <span class="bg-gradient-to-r from-sky-600 to-purple-600 bg-clip-text text-transparent">{{ t('home.featuresTitleAccent') }}</span>
        </h2>
        <div class="grid grid-cols-3 gap-[18px] max-[860px]:grid-cols-2 max-[560px]:grid-cols-1">
          <button
            v-for="(f, i) in features"
            :key="f.id"
            class="reveal group text-left bg-white border border-solid border-slate-200 shadow-sm rounded-[16px] p-[22px] cursor-pointer transition-all duration-300 flex flex-col gap-3 hover:-translate-y-[5px] hover:border-cyan-400/35 hover:shadow-[0_18px_40px_-12px_rgba(34,211,238,0.25)]"
            :style="{ '--d': 960 + i * 100 + 'ms' }"
            @click="emit('navigate', f.target)"
          >
            <span class="w-12 h-12 rounded-[13px] flex items-center justify-center border border-solid transition-transform duration-300 group-hover:-translate-y-[2px] group-hover:scale-110" :style="{ background: f.color + '22', color: f.color, borderColor: f.color + '44' }">
              <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="f.icon"></svg>
            </span>
            <h3 class="text-[1.05rem] font-bold text-ink">{{ t(`home.features.${f.id}.title`) }}</h3>
            <p class="text-[0.87rem] text-ink-soft leading-[1.5]">{{ t(`home.features.${f.id}.desc`) }}</p>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ---- Entrance reveal (staggered via per-element --d delay) ---- */
.reveal {
  opacity: 0;
  transform: translateY(22px) scale(0.98);
  animation: reveal-in 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  animation-delay: var(--d, 0ms);
}
@keyframes reveal-in {
  to { opacity: 1; transform: translateY(0) scale(1); }
}

/* ---- Animated gradient sweep on the hero title ---- */
.title-glow {
  animation:
    reveal-in 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards,
    gradient-pan 6s ease-in-out infinite 0.7s;
  animation-delay: var(--d, 0ms), 0s;
  filter: drop-shadow(0 0 26px rgba(99, 102, 241, 0.35));
}
@keyframes gradient-pan {
  0%, 100% { background-position: 0% center; }
  50% { background-position: 100% center; }
}

/* ---- Slowly rotating sparkle in the badge ---- */
.spin-slow { animation: spin 9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* ---- Floating ambient background blobs ---- */
.blob {
  position: absolute;
  border-radius: 9999px;
  filter: blur(90px);
  opacity: 0.35;
  will-change: transform;
}
.blob-a {
  width: 460px; height: 460px;
  top: -120px; left: -100px;
  background: radial-gradient(circle, rgba(56, 189, 248, 0.55), transparent 70%);
  animation: float-a 18s ease-in-out infinite;
}
.blob-b {
  width: 520px; height: 520px;
  top: 20%; right: -160px;
  background: radial-gradient(circle, rgba(168, 85, 247, 0.5), transparent 70%);
  animation: float-b 22s ease-in-out infinite;
}
.blob-c {
  width: 400px; height: 400px;
  bottom: -140px; left: 30%;
  background: radial-gradient(circle, rgba(45, 212, 191, 0.45), transparent 70%);
  animation: float-c 26s ease-in-out infinite;
}
@keyframes float-a {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(60px, 50px) scale(1.12); }
}
@keyframes float-b {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-70px, 40px) scale(1.08); }
}
@keyframes float-c {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(40px, -60px) scale(1.15); }
}

/* Respect users who prefer reduced motion */
@media (prefers-reduced-motion: reduce) {
  .reveal, .title-glow { animation: none; opacity: 1; transform: none; }
  .spin-slow, .blob { animation: none; }
}
</style>
