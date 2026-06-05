<script setup lang="ts">
/* ================================================================
   Public marketing homepage shown to logged-out visitors.

   Previously this page was a raw Tailwind HTML document rendered
   inside a sandboxed <iframe> and machine-translated on the fly.
   It is now a native Vue component:

     • Tailwind utilities (configured in tailwind.config.js with the
       same Material-3 token palette the old document used) style it.
     • All copy lives in the i18n locale files under `landing.*`, so
       language switching is instant and accurate ($t / tm + rt).
     • CTAs call `enter()` → emits `enter`, which App.vue turns into
       the login card; nav links smooth-scroll to in-page sections.
================================================================= */
import { computed, onBeforeUnmount, onMounted, ref, type Directive } from 'vue'
import { useI18n } from 'vue-i18n'
import { SUPPORTED_LOCALES, setLocale, type LocaleCode } from '../../i18n'

const emit = defineEmits<{ (e: 'enter'): void }>()
const { t, tm, rt, locale } = useI18n()

/**
 * `v-reveal` — scroll-triggered entrance animation.
 *
 * Elements start hidden (`.reveal` baseline in tailwind.css) and fade/slide in
 * the first time they scroll into view. Pass a number to stagger the delay in
 * milliseconds, e.g. `v-reveal="120"`. The `.fade` modifier animates opacity
 * only (no slide) — use it on elements whose own transform must be preserved,
 * like the raised premium pricing card. Honors prefers-reduced-motion via CSS.
 */
const reduceMotion =
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const vReveal: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    // Modifiers pick the entrance flavor: .fade (opacity only), .left/.right
    // (slide in horizontally), .zoom (spring-scale), .blur (de-focus), or the
    // default slide-up. They map to the matching baseline class in tailwind.css.
    const m = binding.modifiers
    const variant = m.fade
      ? 'reveal-fade'
      : m.left
        ? 'reveal-left'
        : m.right
          ? 'reveal-right'
          : m.zoom
            ? 'reveal-zoom'
            : m.blur
              ? 'reveal-blur'
              : 'reveal'
    el.classList.add(variant)
    if (binding.value) el.style.setProperty('--reveal-delay', `${binding.value}ms`)
    if (reduceMotion || typeof IntersectionObserver === 'undefined') {
      el.classList.add('reveal-visible')
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            el.classList.add('reveal-visible')
            io.unobserve(el)
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -10% 0px' },
    )
    io.observe(el)
    ;(el as HTMLElement & { _revealIO?: IntersectionObserver })._revealIO = io
  },
  unmounted(el) {
    ;(el as HTMLElement & { _revealIO?: IntersectionObserver })._revealIO?.disconnect()
  },
}

/**
 * `v-tilt` — pointer-reactive 3D tilt. The card rotates toward the cursor and
 * lifts slightly, snapping back (via the `.tilt` CSS transition) on leave.
 * Skipped entirely on touch / reduced-motion. Pass a number to set max degrees
 * (default 8).
 */
const vTilt: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    if (reduceMotion || window.matchMedia?.('(pointer: coarse)').matches) return
    const max = binding.value ?? 8
    el.classList.add('tilt')
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect()
      const px = (e.clientX - r.left) / r.width - 0.5
      const py = (e.clientY - r.top) / r.height - 0.5
      el.style.transform = `perspective(900px) rotateX(${(-py * max).toFixed(2)}deg) rotateY(${(px * max).toFixed(2)}deg) translateZ(0) scale(1.03)`
    }
    const onLeave = () => {
      el.style.transform = ''
    }
    el.addEventListener('mousemove', onMove)
    el.addEventListener('mouseleave', onLeave)
    ;(el as HTMLElement & { _tilt?: () => void })._tilt = () => {
      el.removeEventListener('mousemove', onMove)
      el.removeEventListener('mouseleave', onLeave)
    }
  },
  unmounted(el) {
    ;(el as HTMLElement & { _tilt?: () => void })._tilt?.()
  },
}

// Decorative rising particles for the hero backdrop. Positions/sizes/timings are
// deterministic-ish per index so the field looks scattered without layout work.
const particles = Array.from({ length: 14 }, (_, i) => ({
  left: `${(i * 37 + 7) % 100}%`,
  bottom: `${(i * 13) % 40}%`,
  size: `${6 + ((i * 5) % 16)}px`,
  duration: `${7 + ((i * 3) % 9)}s`,
  delay: `${(i * 0.7) % 6}s`,
}))

// Reading-progress bar fill (0–1) + subtle mouse-parallax for the hero orbs.
const scroll = ref(0)
const heroBg = ref<HTMLElement | null>(null)

function onScroll() {
  const h = document.documentElement
  const max = h.scrollHeight - h.clientHeight
  scroll.value = max > 0 ? Math.min(1, h.scrollTop / max) : 0
}

function onMouseMove(e: MouseEvent) {
  if (!heroBg.value) return
  const x = (e.clientX / window.innerWidth - 0.5) * 28
  const y = (e.clientY / window.innerHeight - 0.5) * 28
  heroBg.value.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`
}

onMounted(() => {
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
  if (!reduceMotion) window.addEventListener('mousemove', onMouseMove, { passive: true })
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('mousemove', onMouseMove)
})

/** Open the login card. */
function enter() {
  emit('enter')
}

/** Smooth-scroll to an in-page section (the fixed nav offset lives in CSS). */
function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const navLinks = [
  { id: 'muammo', key: 'landing.nav.problem' },
  { id: 'yechim', key: 'landing.nav.solution' },
  { id: 'narxlar', key: 'landing.nav.pricing' },
  { id: 'strategiya', key: 'landing.nav.strategy' },
]

// Full Tailwind class strings are kept inline (not built dynamically) so the
// JIT compiler can see them when scanning this file.
const problemCards = [
  { icon: 'lock', color: 'text-primary', key: 'memorize' },
  { icon: 'hourglass_empty', color: 'text-secondary', key: 'forget' },
  { icon: 'groups', color: 'text-primary', key: 'oneSize' },
  { icon: 'lightbulb', color: 'text-secondary', key: 'boredom' },
]

const formats = [
  { icon: 'science', wrap: 'bg-primary/10', color: 'text-primary', key: 'sim' },
  { icon: 'menu_book', wrap: 'bg-secondary/10', color: 'text-secondary', key: 'comics' },
  { icon: 'sports_esports', wrap: 'bg-primary/10', color: 'text-primary', key: 'games' },
  { icon: 'explore', wrap: 'bg-secondary/10', color: 'text-secondary', key: 'quests' },
  { icon: 'quiz', wrap: 'bg-primary/10', color: 'text-primary', key: 'tests' },
]

const advRows = ['approach', 'personalization', 'engagement']

// tm() returns the raw array messages for the active locale; rt() renders each.
const traditionalItems = computed(() => tm('landing.solution.traditional.items') as unknown[])
const simulinkItems = computed(() => tm('landing.solution.simulink.items') as unknown[])
function planFeatures(plan: string) {
  return tm(`landing.pricing.plans.${plan}.features`) as unknown[]
}
</script>

<template>
  <div class="landing-page w-full min-h-screen bg-background text-on-background font-body-md antialiased overflow-x-hidden">
    <!-- Reading-progress bar (fills as the page scrolls) -->
    <div class="scroll-progress" :style="{ '--scroll': scroll }"></div>

    <!-- Language switcher (kept out of the i18n copy; wired straight to setLocale) -->
    <div class="fixed top-4 right-4 z-[9999] flex gap-1 rounded-full border border-white/60 bg-white/75 p-[5px] shadow-lg shadow-primary/20 backdrop-blur-md">
      <button
        v-for="l in SUPPORTED_LOCALES"
        :key="l.code"
        class="rounded-full px-[9px] py-[5px] text-[17px] leading-none transition-colors"
        :class="l.code === locale ? 'bg-primary/20 outline outline-1 outline-primary/50' : 'bg-transparent'"
        :aria-label="l.label"
        @click="setLocale(l.code as LocaleCode)"
      >{{ l.flag }}</button>
    </div>

    <!-- TopNavBar -->
    <nav class="fixed top-0 w-full z-50 bg-surface-container-lowest/80 backdrop-blur-xl border-b border-black/5 shadow-sm h-20">
      <div class="flex justify-between items-center max-w-container-max mx-auto px-margin-mobile md:px-margin-desktop h-full">
        <div class="flex items-center gap-3">
          <img src="/ico.png" alt="Logo" class="h-16 w-auto object-contain" />
          <span class="font-display-lg text-2xl md:text-3xl tracking-tighter text-primary">SimuLink</span>
        </div>
        <div class="hidden md:flex items-center gap-8">
          <a
            v-for="link in navLinks"
            :key="link.id"
            class="nav-link font-body-md text-body-md text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
            @click="scrollTo(link.id)"
          >{{ t(link.key) }}</a>
        </div>
        <div class="hidden md:flex items-center gap-4">
          <button
            class="font-label-caps text-label-caps px-6 py-2 rounded-full border border-primary text-primary hover:bg-primary/5 transition-all duration-300 active:scale-95"
            @click="enter"
          >{{ t('landing.nav.login') }}</button>
          <button
            class="sheen font-label-caps text-label-caps px-6 py-2 rounded-full bg-gradient-to-r from-primary to-secondary text-on-primary hover:opacity-90 shadow-lg shadow-primary/20 transition-all duration-300 active:scale-95"
            @click="enter"
          >{{ t('landing.nav.start') }}</button>
        </div>
        <button class="md:hidden text-primary" @click="enter">
          <span class="material-symbols-outlined text-3xl">menu</span>
        </button>
      </div>
    </nav>

    <!-- Hero Section -->
    <header id="top" class="relative pt-32 pb-20 md:pt-48 md:pb-32 overflow-hidden bg-mesh min-h-screen flex items-center">
      <div ref="heroBg" class="absolute inset-0 z-0 transition-transform duration-300 ease-out">
        <!-- Floating ambient orbs (drift with the cursor via heroBg parallax) -->
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
        <!-- Rising particle field -->
        <div
          v-for="(p, i) in particles"
          :key="i"
          class="particle"
          :style="{
            left: p.left,
            bottom: p.bottom,
            width: p.size,
            height: p.size,
            animationDuration: p.duration,
            animationDelay: p.delay,
          }"
        ></div>
        <div class="absolute inset-0 bg-gradient-to-b from-transparent to-background"></div>
      </div>
      <div class="max-w-container-max mx-auto px-margin-mobile md:px-margin-desktop relative z-10 text-center">
        <div v-reveal.zoom class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 border border-primary/20 mb-8 backdrop-blur-md">
          <span class="pulse-ring w-2 h-2 rounded-full bg-primary text-primary"></span>
          <span class="font-label-caps text-label-caps text-primary uppercase tracking-widest">{{ t('landing.hero.badge') }}</span>
        </div>
        <h1 v-reveal="120" class="font-display-lg text-display-lg-mobile md:text-display-lg text-on-background mb-6 max-w-4xl mx-auto">
          <span class="gradient-text gradient-text-animated">{{ t('landing.hero.brand') }}</span> {{ t('landing.hero.titleRest') }}
        </h1>
        <p v-reveal="240" class="font-body-lg text-body-lg text-on-surface-variant max-w-2xl mx-auto mb-10">
          {{ t('landing.hero.subtitle') }}
        </p>
        <div v-reveal="360" class="flex flex-col sm:flex-row justify-center items-center gap-4">
          <button
            class="sheen w-full sm:w-auto font-label-caps text-label-caps px-8 py-4 rounded-full bg-gradient-to-r from-primary to-secondary text-on-primary hover:shadow-xl hover:shadow-primary/30 transform hover:-translate-y-1 active:translate-y-0 transition-all duration-300"
            @click="enter"
          >{{ t('landing.hero.ctaStart') }}</button>
          <button
            class="w-full sm:w-auto font-label-caps text-label-caps px-8 py-4 rounded-full glass-panel text-primary hover:bg-white/50 transform hover:-translate-y-1 active:translate-y-0 transition-all duration-300"
            @click="scrollTo('yechim')"
          >{{ t('landing.hero.ctaMore') }}</button>
        </div>
        <!-- Bouncing scroll cue -->
        <button
          v-reveal="500"
          class="scroll-cue mx-auto mt-16 flex flex-col items-center text-on-surface-variant hover:text-primary transition-colors"
          aria-label="Scroll down"
          @click="scrollTo('muammo')"
        >
          <span class="material-symbols-outlined text-3xl">keyboard_arrow_down</span>
        </button>
      </div>
    </header>

    <!-- Problem Section -->
    <section id="muammo" class="py-20 bg-surface">
      <div class="max-w-container-max mx-auto px-margin-mobile md:px-margin-desktop">
        <div class="text-center mb-16">
          <h2 v-reveal class="font-display-lg text-3xl md:text-4xl text-on-background mb-4">
            {{ t('landing.problem.title') }} <span class="text-primary">{{ t('landing.problem.titleAccent') }}</span>
          </h2>
          <p v-reveal="100" class="text-body-lg text-on-surface-variant max-w-2xl mx-auto">{{ t('landing.problem.subtitle') }}</p>
        </div>
        <div class="flex flex-col lg:flex-row items-center gap-12">
          <div v-reveal.left class="lg:w-1/2 w-full">
            <div v-tilt="6" class="illustration aspect-[4/3] rounded-2xl flex items-center justify-center">
              <span class="material-symbols-outlined text-primary text-[120px] float-soft">menu_book</span>
            </div>
          </div>
          <div class="lg:w-1/2 grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div v-for="(c, i) in problemCards" :key="c.key" v-reveal.right="i * 120" v-tilt class="glass-panel p-6 rounded-2xl glass-card-hover">
              <span class="material-symbols-outlined text-4xl mb-4" :class="c.color">{{ c.icon }}</span>
              <h3 class="font-headline-md text-xl mb-2">{{ t(`landing.problem.cards.${c.key}.title`) }}</h3>
              <p class="text-on-surface-variant">{{ t(`landing.problem.cards.${c.key}.desc`) }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Market Gap & Solution -->
    <section id="yechim" class="py-20 bg-surface-container-lowest">
      <div class="max-w-container-max mx-auto px-margin-mobile md:px-margin-desktop">
        <div class="text-center mb-16">
          <h2 v-reveal class="font-display-lg text-3xl md:text-4xl text-on-background mb-4">
            {{ t('landing.solution.title') }} <span class="gradient-text">{{ t('landing.solution.titleAccent') }}</span>
          </h2>
          <p v-reveal="100" class="text-body-lg text-on-surface-variant max-w-2xl mx-auto">{{ t('landing.solution.subtitle') }}</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-16">
          <div v-reveal.left class="bg-surface-variant/30 p-8 rounded-3xl border border-outline-variant/50">
            <h3 class="font-headline-md text-2xl text-error mb-4 flex items-center gap-2">
              <span class="material-symbols-outlined">cancel</span> {{ t('landing.solution.traditional.title') }}
            </h3>
            <ul class="space-y-4 text-on-surface-variant text-lg">
              <li v-for="(it, i) in traditionalItems" :key="i" class="flex items-center gap-3">
                <span class="material-symbols-outlined text-outline">remove</span> {{ rt(it as never) }}
              </li>
            </ul>
          </div>
          <div v-reveal.right="120" class="bg-primary/5 p-8 rounded-3xl border border-primary/20 relative overflow-hidden">
            <div class="absolute -right-10 -top-10 w-40 h-40 bg-secondary/10 rounded-full blur-3xl"></div>
            <h3 class="font-headline-md text-2xl text-primary mb-4 flex items-center gap-2">
              <span class="material-symbols-outlined">check_circle</span> {{ t('landing.solution.simulink.title') }}
            </h3>
            <ul class="space-y-4 text-on-surface-variant text-lg relative z-10">
              <li v-for="(it, i) in simulinkItems" :key="i" class="flex items-center gap-3">
                <span class="material-symbols-outlined text-primary">check</span> {{ rt(it as never) }}
              </li>
            </ul>
          </div>
        </div>
        <h3 v-reveal class="font-headline-md text-center text-2xl mb-10">{{ t('landing.solution.formatsTitle') }}</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">
          <div v-for="(f, i) in formats" :key="f.key" v-reveal.zoom="i * 90" v-tilt="10" class="group glass-panel p-6 rounded-2xl text-center glass-card-hover">
            <div class="w-16 h-16 mx-auto rounded-full flex items-center justify-center mb-4 transition-transform duration-300 group-hover:scale-110 group-hover:-translate-y-1 float-soft" :class="f.wrap" :style="{ '--float-delay': `${i * 300}ms` }">
              <span class="material-symbols-outlined text-3xl" :class="f.color">{{ f.icon }}</span>
            </div>
            <h4 class="font-bold mb-2">{{ t(`landing.solution.formats.${f.key}`) }}</h4>
          </div>
        </div>
      </div>
    </section>

    <!-- Competitive Advantage -->
    <section class="py-20 bg-surface">
      <div class="max-w-container-max mx-auto px-margin-mobile md:px-margin-desktop">
        <div class="text-center mb-16">
          <h2 v-reveal class="font-display-lg text-3xl md:text-4xl text-on-background mb-4">
            {{ t('landing.advantage.title') }} <span class="text-secondary">{{ t('landing.advantage.titleAccent') }}</span>
          </h2>
        </div>
        <div v-reveal="120" class="overflow-x-auto">
          <table class="w-full text-left border-collapse min-w-[600px]">
            <thead>
              <tr class="border-b-2 border-outline-variant/30 text-on-surface-variant">
                <th class="py-4 px-6 font-headline-md">{{ t('landing.advantage.cols.feature') }}</th>
                <th class="py-4 px-6 font-headline-md text-primary bg-primary/5 rounded-t-xl">{{ t('landing.advantage.cols.simulink') }}</th>
                <th class="py-4 px-6 font-headline-md">{{ t('landing.advantage.cols.others') }}</th>
              </tr>
            </thead>
            <tbody class="text-on-surface">
              <tr v-for="(row, i) in advRows" :key="row" class="border-b border-outline-variant/20">
                <td class="py-4 px-6 font-medium" :class="{ 'rounded-bl-xl': i === advRows.length - 1 }">{{ t(`landing.advantage.rows.${row}.feature`) }}</td>
                <td class="py-4 px-6 bg-primary/5 font-bold text-primary" :class="{ 'rounded-b-xl': i === advRows.length - 1 }">{{ t(`landing.advantage.rows.${row}.simulink`) }}</td>
                <td class="py-4 px-6">{{ t(`landing.advantage.rows.${row}.others`) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- Pricing -->
    <section id="narxlar" class="py-20 bg-surface-container-lowest">
      <div class="max-w-container-max mx-auto px-margin-mobile md:px-margin-desktop">
        <div class="text-center mb-16">
          <h2 v-reveal class="font-display-lg text-3xl md:text-4xl text-on-background mb-4">
            {{ t('landing.pricing.title') }} <span class="text-primary">{{ t('landing.pricing.titleAccent') }}</span>
          </h2>
          <p v-reveal="100" class="text-body-lg text-on-surface-variant max-w-2xl mx-auto">{{ t('landing.pricing.subtitle') }}</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          <!-- Freemium -->
          <div v-reveal="0" v-tilt="5" class="border border-outline-variant p-8 rounded-3xl bg-surface hover:shadow-xl transition-all duration-300">
            <h3 class="font-headline-md text-2xl mb-2">{{ t('landing.pricing.plans.free.name') }}</h3>
            <p class="text-on-surface-variant mb-6">{{ t('landing.pricing.plans.free.desc') }}</p>
            <div class="text-4xl font-bold mb-6">{{ t('landing.pricing.plans.free.price') }}</div>
            <ul class="space-y-4 mb-8 text-on-surface-variant">
              <li v-for="(f, i) in planFeatures('free')" :key="i" class="flex items-center gap-2">
                <span class="material-symbols-outlined text-secondary">check</span> {{ rt(f as never) }}
              </li>
            </ul>
            <button class="w-full py-3 rounded-full border-2 border-primary text-primary font-bold hover:bg-primary/5 transition-colors" @click="enter">
              {{ t('landing.pricing.plans.free.cta') }}
            </button>
          </div>

          <!-- Premium -->
          <div v-reveal.fade="120" class="gradient-border animate-glow border-2 border-primary p-8 rounded-3xl bg-primary/5 relative transform md:-translate-y-4 shadow-2xl">
            <div class="absolute top-0 right-0 z-10 bg-primary text-white text-xs font-bold px-4 py-1 rounded-bl-xl rounded-tr-xl">
              {{ t('landing.pricing.popular') }}
            </div>
            <h3 class="font-headline-md text-2xl mb-2 text-primary">{{ t('landing.pricing.plans.premium.name') }}</h3>
            <p class="text-on-surface-variant mb-6">{{ t('landing.pricing.plans.premium.desc') }}</p>
            <div class="text-4xl font-bold mb-2 flex items-baseline gap-1.5">
              {{ t('landing.pricing.plans.premium.amount') }}
              <span class="text-lg font-normal text-on-surface-variant">{{ t('landing.pricing.plans.premium.price') }}</span>
            </div>
            <p class="text-sm text-secondary mb-6">{{ t('landing.pricing.plans.premium.note') }}</p>
            <ul class="space-y-4 mb-8 text-on-surface-variant">
              <li v-for="(f, i) in planFeatures('premium')" :key="i" class="flex items-center gap-2">
                <span class="material-symbols-outlined text-primary">check_circle</span> {{ rt(f as never) }}
              </li>
            </ul>
            <button class="sheen relative z-10 w-full py-3 rounded-full bg-primary text-white font-bold hover:bg-primary/90 transition-colors shadow-lg" @click="enter">
              {{ t('landing.pricing.plans.premium.cta') }}
            </button>
          </div>

          <!-- B2B -->
          <div v-reveal="240" v-tilt="5" class="border border-outline-variant p-8 rounded-3xl bg-surface hover:shadow-xl transition-all duration-300">
            <h3 class="font-headline-md text-2xl mb-2">{{ t('landing.pricing.plans.b2b.name') }}</h3>
            <p class="text-on-surface-variant mb-6">{{ t('landing.pricing.plans.b2b.desc') }}</p>
            <div class="text-3xl font-bold mb-6">{{ t('landing.pricing.plans.b2b.price') }}</div>
            <ul class="space-y-4 mb-8 text-on-surface-variant">
              <li v-for="(f, i) in planFeatures('b2b')" :key="i" class="flex items-center gap-2">
                <span class="material-symbols-outlined text-secondary">check</span> {{ rt(f as never) }}
              </li>
            </ul>
            <button class="w-full py-3 rounded-full border-2 border-secondary text-secondary font-bold hover:bg-secondary/5 transition-colors" @click="enter">
              {{ t('landing.pricing.plans.b2b.cta') }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Strategy -->
    <section id="strategiya" class="py-20 bg-surface">
      <div class="max-w-container-max mx-auto px-margin-mobile md:px-margin-desktop">
        <div class="text-center mb-16">
          <h2 v-reveal class="font-display-lg text-3xl md:text-4xl text-on-background mb-4">
            {{ t('landing.strategy.title') }} <span class="gradient-text">{{ t('landing.strategy.titleAccent') }}</span>
          </h2>
          <p v-reveal="100" class="text-body-lg text-on-surface-variant max-w-2xl mx-auto">{{ t('landing.strategy.subtitle') }}</p>
        </div>
        <div class="flex justify-center">
          <div v-reveal.zoom="150" v-tilt="5" class="illustration w-full max-w-5xl min-h-[280px] rounded-2xl flex items-center justify-center">
            <span class="material-symbols-outlined text-primary text-[96px] float-soft">trending_up</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="bg-surface-container-highest border-t border-outline-variant w-full py-12">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-gutter max-w-container-max mx-auto px-margin-mobile md:px-margin-desktop">
        <div class="col-span-1 flex flex-col gap-4">
          <div class="flex items-center gap-2 mb-2">
            <img src="/ico.png" alt="Logo" class="h-12 w-auto object-contain" />
            <span class="font-display-lg text-xl md:text-2xl text-primary opacity-90">SimuLink</span>
          </div>
          <p class="font-body-md text-body-md text-on-surface-variant text-sm">
            {{ t('landing.footer.copyright') }}<br />{{ t('landing.footer.rights') }}
          </p>
        </div>
        <div class="col-span-1 md:col-span-3 flex flex-wrap gap-x-8 gap-y-4 md:justify-end items-center">
          <a class="font-body-md text-body-md text-on-surface-variant hover:text-primary transition-colors cursor-pointer">{{ t('landing.footer.links.privacy') }}</a>
          <a class="font-body-md text-body-md text-on-surface-variant hover:text-primary transition-colors cursor-pointer">{{ t('landing.footer.links.terms') }}</a>
          <a class="font-body-md text-body-md text-on-surface-variant hover:text-primary transition-colors cursor-pointer">{{ t('landing.footer.links.contact') }}</a>
          <a class="font-body-md text-body-md text-on-surface-variant hover:text-primary transition-colors cursor-pointer">{{ t('landing.footer.links.blog') }}</a>
        </div>
      </div>
    </footer>
  </div>
</template>

<!--
  No <style> block by design: every visual is a Tailwind utility, and the few
  reusable bits (glass-panel, gradient-text, bg-mesh, brand-mark, the scoped
  landing baseline, …) live in src/assets/tailwind.css.
-->
