<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '../../composables/useToast'

/* ================================================================
   Tests / Quizzes (Викторина) — DUMMY DATA, no backend.

   Everything here runs fully client-side: the questions are hard-coded
   placeholders and the per-test progress (best score + spaced-repetition
   review date) is persisted to localStorage. Swap the `QUIZZES` array and
   the load/save helpers for a real API once the backend is ready.
   ================================================================ */

const { t } = useI18n()
const { showToast } = useToast()

type Difficulty = 'easy' | 'medium' | 'hard'

interface Question {
  q: string
  options: string[]
  answer: number // index into options
}

interface Quiz {
  id: string
  color: string
  difficulty: Difficulty
  icon: string
  questions: Question[]
}

/* Dummy question banks — placeholder content until the test API lands. */
const QUIZZES: Quiz[] = [
  {
    id: 'newton',
    color: '#6366f1',
    difficulty: 'medium',
    icon: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
    questions: [
      { q: "Newton's first law is also known as the law of…", options: ['Inertia', 'Gravity', 'Acceleration', 'Energy'], answer: 0 },
      { q: 'Force equals mass times…', options: ['Velocity', 'Acceleration', 'Distance', 'Time'], answer: 1 },
      { q: 'For every action there is an equal and opposite…', options: ['Force', 'Mass', 'Reaction', 'Motion'], answer: 2 },
      { q: 'The SI unit of force is the…', options: ['Joule', 'Watt', 'Pascal', 'Newton'], answer: 3 },
    ],
  },
  {
    id: 'photosynthesis',
    color: '#8b5cf6',
    difficulty: 'easy',
    icon: '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6"/>',
    questions: [
      { q: 'Photosynthesis mainly takes place in the…', options: ['Roots', 'Chloroplasts', 'Nucleus', 'Mitochondria'], answer: 1 },
      { q: 'Which gas do plants take in for photosynthesis?', options: ['Oxygen', 'Nitrogen', 'Carbon dioxide', 'Hydrogen'], answer: 2 },
      { q: 'The green pigment that captures light is…', options: ['Carotene', 'Hemoglobin', 'Melanin', 'Chlorophyll'], answer: 3 },
    ],
  },
  {
    id: 'solar',
    color: '#a855f7',
    difficulty: 'easy',
    icon: '<circle cx="12" cy="12" r="3"/><circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><path d="M10.4 21.9a10 10 0 0 0 9.941-15.416"/><path d="M13.5 2.1a10 10 0 0 0-9.841 15.416"/>',
    questions: [
      { q: 'Which planet is closest to the Sun?', options: ['Mercury', 'Venus', 'Earth', 'Mars'], answer: 0 },
      { q: 'The largest planet in the Solar System is…', options: ['Saturn', 'Jupiter', 'Neptune', 'Uranus'], answer: 1 },
      { q: 'Which planet is known as the Red Planet?', options: ['Venus', 'Mercury', 'Mars', 'Pluto'], answer: 2 },
      { q: 'How many planets orbit the Sun?', options: ['7', '9', '10', '8'], answer: 3 },
    ],
  },
  {
    id: 'roots',
    color: '#818cf8',
    difficulty: 'hard',
    icon: '<path d="M3 12h3.28a1 1 0 0 1 .948.684l2.298 7.934a.5.5 0 0 0 .96-.044L13.82 4.771A1 1 0 0 1 14.792 4H21"/>',
    questions: [
      { q: 'What is √144?', options: ['12', '14', '16', '24'], answer: 0 },
      { q: 'What is √81?', options: ['7', '9', '11', '13'], answer: 1 },
      { q: 'What is √225?', options: ['13', '14', '15', '16'], answer: 2 },
      { q: 'What is √64?', options: ['6', '7', '9', '8'], answer: 3 },
    ],
  },
]

/* ---- Spaced repetition (client-side) ------------------------------ */
const DAY = 24 * 60 * 60 * 1000
const STORE_KEY = 'simulink:test-progress'

interface Progress {
  bestPct: number
  lastTaken: number // epoch ms
  nextReview: number // epoch ms
}

const progress = ref<Record<string, Progress>>({})

function loadProgress() {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    progress.value = raw ? JSON.parse(raw) : {}
  } catch {
    progress.value = {}
  }
}

function saveProgress() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(progress.value))
  } catch {
    /* storage unavailable — keep in-memory only */
  }
}

/* Higher score → longer gap before the test is due again. */
function intervalDays(pct: number): number {
  if (pct >= 90) return 7
  if (pct >= 70) return 3
  if (pct >= 50) return 1
  return 0 // failed — review again right away
}

onMounted(loadProgress)

/* "Due in N days" / "Due now" / "Not started" for a quiz card. */
function dueDays(id: string): number | null {
  const p = progress.value[id]
  if (!p) return null
  return Math.max(0, Math.ceil((p.nextReview - Date.now()) / DAY))
}

/* ---- Overview stats ---------------------------------------------- */
const takenCount = computed(() => Object.keys(progress.value).length)
const averageBest = computed(() => {
  const scores = Object.values(progress.value).map((p) => p.bestPct)
  if (!scores.length) return 0
  return Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
})
const dueNowCount = computed(
  () => QUIZZES.filter((q) => (dueDays(q.id) ?? 1) <= 0 && progress.value[q.id]).length,
)

/* Mastery progress bar on each card uses the best score so far. */
function bestPct(id: string): number {
  return progress.value[id]?.bestPct ?? 0
}

/* ---- View state --------------------------------------------------- */
type Screen = 'list' | 'quiz' | 'result'
const screen = ref<Screen>('list')

const activeQuiz = ref<Quiz | null>(null)
const step = ref(0)
const selected = ref<number | null>(null)
const correctCount = ref(0)

/* Fade-in keyframe key per question — restart the animation on every step. */
const stepAnimKey = ref(0)

const currentQuestion = computed(() => activeQuiz.value?.questions[step.value] ?? null)
const totalQuestions = computed(() => activeQuiz.value?.questions.length ?? 0)
const scorePct = computed(() =>
  totalQuestions.value ? Math.round((correctCount.value / totalQuestions.value) * 100) : 0,
)
const wrongCount = computed(() => Math.max(0, step.value + (selected.value !== null ? 1 : 0) - correctCount.value))

function startQuiz(quiz: Quiz) {
  activeQuiz.value = quiz
  step.value = 0
  selected.value = null
  correctCount.value = 0
  stepAnimKey.value++
  screen.value = 'quiz'
}

function choose(i: number) {
  if (selected.value !== null) return // already answered this question
  selected.value = i
  if (i === currentQuestion.value?.answer) correctCount.value++
}

function nextStep() {
  if (selected.value === null) return
  if (step.value < totalQuestions.value - 1) {
    step.value++
    selected.value = null
    stepAnimKey.value++
  } else {
    finishQuiz()
  }
}

function finishQuiz() {
  const quiz = activeQuiz.value
  if (quiz) {
    const pct = scorePct.value
    const prev = progress.value[quiz.id]
    progress.value[quiz.id] = {
      bestPct: Math.max(pct, prev?.bestPct ?? 0),
      lastTaken: Date.now(),
      nextReview: Date.now() + intervalDays(pct) * DAY,
    }
    saveProgress()
  }
  screen.value = 'result'
}

function backToList() {
  screen.value = 'list'
  activeQuiz.value = null
}

const resultMessage = computed(() => {
  const pct = scorePct.value
  if (pct >= 80) return t('tests.resultGreat')
  if (pct >= 50) return t('tests.resultGood')
  return t('tests.resultTry')
})

const nextReviewDays = computed(() => (activeQuiz.value ? intervalDays(scorePct.value) : 0))

/* Per-quiz accent colour (drives the active-quiz progress bar & buttons). */
const accent = computed(() => activeQuiz.value?.color ?? '#6366f1')
/* Result ring colour follows the score: green / amber / red. */
const ringColor = computed(() =>
  scorePct.value >= 80 ? '#22c55e' : scorePct.value >= 50 ? '#f59e0b' : '#ef4444',
)
/* Show confetti only on great runs. */
const celebrate = computed(() => scorePct.value >= 80)

/* Option button state once an answer is locked in. */
function optionClass(i: number): string {
  if (selected.value === null) return ''
  if (i === currentQuestion.value?.answer) return 'border-green-400 bg-green-400/[0.14] shadow-[0_6px_18px_-10px_rgba(34,197,94,0.5)]'
  if (i === selected.value) return 'border-red-400 bg-red-400/[0.14] shadow-[0_6px_18px_-10px_rgba(239,68,68,0.5)]'
  return 'opacity-50'
}

/* Letter-chip color swap once an answer is locked in. */
function optionLetterClass(i: number): string {
  if (selected.value === null) return 'bg-slate-100 text-ink'
  if (i === currentQuestion.value?.answer) return 'bg-green-400 text-[#06281a]'
  if (i === selected.value) return 'bg-red-400 text-[#2a0a0a]'
  return 'bg-slate-100 text-ink'
}

function diffClass(d: Difficulty) {
  if (d === 'easy') return 'text-green-600 bg-green-400/[0.16]'
  if (d === 'medium') return 'text-amber-600 bg-amber-400/[0.16]'
  return 'text-red-600 bg-red-400/[0.16]'
}

function notifyStarted() {
  showToast(t('tests.startedToast'), 'info')
}

/* Keyboard shortcuts during the quiz: 1-4 to pick, Enter to advance. */
function onQuizKey(e: KeyboardEvent) {
  if (screen.value !== 'quiz' || !currentQuestion.value) return
  if (e.key === 'Enter') {
    if (selected.value !== null) nextStep()
    return
  }
  const idx = ['1', '2', '3', '4'].indexOf(e.key)
  if (idx >= 0 && idx < currentQuestion.value.options.length) {
    choose(idx)
  }
}

watch(screen, (s) => {
  if (s === 'quiz') {
    nextTick(() => window.addEventListener('keydown', onQuizKey))
  } else {
    window.removeEventListener('keydown', onQuizKey)
  }
})

/* Cosmetic: confetti particles for the result celebration. */
const confettiPieces = Array.from({ length: 24 }, (_, i) => ({
  i,
  left: Math.round((i * 4.17) % 100), // deterministic spread, no Math.random in setup
  delay: (i % 6) * 0.08,
  hue: ['#6366f1', '#a855f7', '#22c55e', '#f59e0b', '#ec4899', '#06b6d4'][i % 6],
}))
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-[1100px] mx-auto px-8 pt-8 pb-14 max-[560px]:px-[18px] max-[560px]:pt-6 max-[560px]:pb-12">
      <!-- ========================= LIST ========================= -->
      <template v-if="screen === 'list'">
        <!-- ---- HERO HEADER ---- -->
        <div class="mb-6 flex items-center gap-3.5">
          <span class="w-12 h-12 rounded-2xl flex-shrink-0 flex items-center justify-center text-white bg-gradient-to-br from-indigo-500 to-violet-500 shadow-[0_8px_20px_rgba(99,102,241,0.32)]">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 12H3"/><path d="M16 6H3"/><path d="M16 18H3"/><path d="m17 12 2 2 4-4"/></svg>
          </span>
          <div class="flex-1 min-w-0">
            <h1 class="font-display text-[1.9rem] leading-tight font-extrabold bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">{{ t('tests.title') }}</h1>
            <p class="text-ink-soft mt-0.5 text-[0.95rem]">{{ t('tests.subtitle') }}</p>
          </div>
        </div>

        <!-- ---- OVERVIEW STATS STRIP ---- -->
        <div class="relative overflow-hidden rounded-2xl border border-solid border-slate-200 bg-gradient-to-br from-indigo-50 via-white to-violet-50 mb-7 shadow-sm">
          <!-- decorative glow -->
          <span aria-hidden="true" class="pointer-events-none absolute -top-10 -right-10 w-44 h-44 rounded-full bg-violet-400/25 blur-3xl"></span>
          <span aria-hidden="true" class="pointer-events-none absolute -bottom-12 -left-8 w-44 h-44 rounded-full bg-indigo-400/20 blur-3xl"></span>

          <div class="relative grid grid-cols-3 max-[560px]:grid-cols-1 divide-x max-[560px]:divide-x-0 max-[560px]:divide-y divide-slate-200/80">
            <div class="px-5 py-4 flex items-center gap-3">
              <span class="w-10 h-10 rounded-xl flex items-center justify-center bg-indigo-500/15 text-indigo-600 flex-shrink-0">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3 8-8"/><path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9"/></svg>
              </span>
              <div class="leading-tight">
                <div class="font-display text-[1.35rem] font-extrabold text-ink tabular-nums">{{ takenCount }}<span class="text-ink-mute text-[0.95rem] font-bold">/{{ QUIZZES.length }}</span></div>
                <div class="text-[0.78rem] uppercase tracking-wide text-ink-soft font-bold">{{ t('tests.overview.taken') }}</div>
              </div>
            </div>

            <div class="px-5 py-4 flex items-center gap-3">
              <span class="w-10 h-10 rounded-xl flex items-center justify-center bg-violet-500/15 text-violet-600 flex-shrink-0">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
              </span>
              <div class="leading-tight">
                <div class="font-display text-[1.35rem] font-extrabold text-ink tabular-nums">{{ averageBest }}<span class="text-ink-mute text-[0.95rem] font-bold">%</span></div>
                <div class="text-[0.78rem] uppercase tracking-wide text-ink-soft font-bold">{{ t('tests.overview.average') }}</div>
              </div>
            </div>

            <div class="px-5 py-4 flex items-center gap-3">
              <span class="w-10 h-10 rounded-xl flex items-center justify-center bg-amber-400/20 text-amber-700 flex-shrink-0">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
              </span>
              <div class="leading-tight">
                <div class="font-display text-[1.35rem] font-extrabold text-ink tabular-nums">{{ dueNowCount }}</div>
                <div class="text-[0.78rem] uppercase tracking-wide text-ink-soft font-bold">{{ t('tests.overview.due') }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ---- QUIZ CARDS ---- -->
        <div class="grid grid-cols-3 gap-[18px] max-[860px]:grid-cols-2 max-[560px]:grid-cols-1">
          <button
            v-for="quiz in QUIZZES"
            :key="quiz.id"
            class="group relative flex h-full flex-col gap-3 overflow-hidden text-left bg-white border border-solid border-slate-200 rounded-2xl p-5 cursor-pointer transition-all duration-300 shadow-sm hover:-translate-y-1 hover:border-transparent hover:shadow-[0_18px_38px_-14px_rgba(15,23,42,0.32)]"
            @click="startQuiz(quiz); notifyStarted()"
          >
            <!-- Per-subject accent strip + soft tinted wash -->
            <span class="absolute inset-x-0 top-0 h-1 opacity-90 transition-opacity duration-300 group-hover:opacity-100" :style="{ background: quiz.color }"></span>
            <span aria-hidden="true" class="pointer-events-none absolute -right-10 -top-10 w-32 h-32 rounded-full blur-2xl opacity-15 transition-opacity duration-300 group-hover:opacity-30" :style="{ background: quiz.color }"></span>
            <span aria-hidden="true" class="pointer-events-none absolute -left-12 -bottom-12 w-32 h-32 rounded-full blur-2xl opacity-0 transition-opacity duration-500 group-hover:opacity-15" :style="{ background: quiz.color }"></span>

            <!-- Mastered ribbon -->
            <span v-if="bestPct(quiz.id) >= 90" class="absolute top-3 right-3 inline-flex items-center gap-1 text-[0.66rem] font-extrabold uppercase tracking-wide py-[3px] px-2 rounded-full text-white shadow-sm" :style="{ background: 'linear-gradient(135deg,' + quiz.color + ',#a855f7)' }">
              <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .587l3.668 7.431L24 9.75l-6 5.847L19.336 24 12 19.897 4.664 24 6 15.597 0 9.75l8.332-1.732z"/></svg>
              {{ t('tests.mastered') }}
            </span>

            <div class="flex justify-between items-start">
              <span class="w-12 h-12 rounded-xl flex items-center justify-center transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-6" :style="{ backgroundColor: quiz.color + '1f', color: quiz.color }">
                <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="quiz.icon"></svg>
              </span>
              <span class="text-xs font-bold py-1 px-2.5 rounded-full" :class="diffClass(quiz.difficulty)">{{ t(`tests.difficulty.${quiz.difficulty}`) }}</span>
            </div>

            <div>
              <h3 class="text-base font-bold text-ink">{{ t(`tests.items.${quiz.id}.title`) }}</h3>
              <p class="mt-0.5 text-sm text-ink-soft">{{ t(`tests.items.${quiz.id}.subject`) }}</p>
            </div>

            <div class="flex items-center gap-2 flex-wrap text-[0.8rem]">
              <span class="inline-flex items-center gap-1.5 text-ink-soft">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/></svg>
                {{ t('tests.questions', { n: quiz.questions.length }) }}
              </span>
              <span class="inline-flex items-center gap-1.5 text-ink-soft">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                {{ t('tests.timeEst', { n: quiz.questions.length }) }}
              </span>
            </div>

            <!-- Mastery progress bar (best score so far) -->
            <div class="mt-1">
              <div class="flex items-center justify-between text-[0.72rem] font-bold mb-1">
                <span class="uppercase tracking-wide text-ink-soft">{{ t('tests.mastery') }}</span>
                <span class="tabular-nums" :style="{ color: quiz.color }">{{ bestPct(quiz.id) }}%</span>
              </div>
              <div class="h-1.5 rounded-full bg-slate-200/70 overflow-hidden">
                <div class="h-full rounded-full transition-[width] duration-700 ease-out" :style="{ width: bestPct(quiz.id) + '%', background: `linear-gradient(90deg, ${quiz.color}, ${quiz.color}aa)` }"></div>
              </div>
            </div>

            <!-- Footer: schedule + CTA -->
            <div class="flex items-center justify-between mt-auto pt-3 border-t border-solid border-slate-200/80">
              <span v-if="dueDays(quiz.id) === null" class="text-[0.76rem] font-semibold py-1 px-2.5 rounded-full text-ink-soft bg-slate-100">{{ t('tests.notTaken') }}</span>
              <span v-else-if="dueDays(quiz.id)! <= 0" class="inline-flex items-center gap-1 text-[0.76rem] font-semibold py-1 px-2.5 rounded-full text-amber-700 bg-amber-400/20">
                <span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
                {{ t('tests.due') }}
              </span>
              <span v-else class="text-[0.76rem] font-semibold py-1 px-2.5 rounded-full text-indigo-700 bg-indigo-500/15">{{ t('tests.reviewIn', { n: dueDays(quiz.id) }) }}</span>
              <span class="inline-flex items-center gap-1 text-sm font-bold transition-transform duration-200 group-hover:translate-x-0.5" :style="{ color: quiz.color }">{{ progress[quiz.id] ? t('tests.review') : t('tests.start') }} →</span>
            </div>
          </button>
        </div>
      </template>

      <!-- ========================= QUIZ ========================= -->
      <template v-else-if="screen === 'quiz' && currentQuestion">
        <div class="max-w-[680px] mx-auto pt-3">
          <!-- Top bar: back, progress, step counter -->
          <div class="flex items-center gap-[14px] mb-6">
            <button class="bg-slate-100 border border-solid border-slate-200 text-ink-soft w-[36px] h-[36px] rounded-[10px] cursor-pointer text-[1.1rem] flex-shrink-0 transition-all duration-200 hover:text-ink hover:bg-slate-200" @click="backToList" :aria-label="t('tests.backToList')">←</button>
            <div class="flex-1 h-[10px] bg-slate-200/80 rounded-full overflow-hidden relative">
              <div class="h-full rounded-full transition-[width] duration-500 ease-out" :style="{ width: ((step + 1) / totalQuestions) * 100 + '%', background: `linear-gradient(90deg, ${accent}, ${accent}cc)` }"></div>
              <!-- Question milestones -->
              <div class="absolute inset-0 flex">
                <span v-for="(_, i) in totalQuestions - 1" :key="i" class="flex-1 border-r border-solid border-white/70 last:border-r-0"></span>
              </div>
            </div>
            <span class="text-[0.8rem] font-semibold text-ink-soft whitespace-nowrap tabular-nums">{{ t('tests.questionOf', { n: step + 1, total: totalQuestions }) }}</span>
          </div>

          <!-- Live score chips -->
          <div class="flex items-center gap-2 mb-4 text-[0.78rem] font-bold">
            <span class="inline-flex items-center gap-1.5 py-1 px-2.5 rounded-full text-green-700 bg-green-400/15">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              <span class="tabular-nums">{{ correctCount }}</span>
            </span>
            <span class="inline-flex items-center gap-1.5 py-1 px-2.5 rounded-full text-red-700 bg-red-400/15">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              <span class="tabular-nums">{{ wrongCount }}</span>
            </span>
            <span class="ml-auto inline-flex items-center gap-1 py-1 px-2.5 rounded-full text-ink-soft bg-slate-100">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/></svg>
              {{ t(`tests.items.${activeQuiz!.id}.subject`) }}
            </span>
          </div>

          <!-- Question card -->
          <div :key="stepAnimKey" class="quiz-anim relative bg-white border border-solid border-slate-200 rounded-2xl p-6 shadow-[0_18px_44px_-22px_rgba(15,23,42,0.22)] mb-5 overflow-hidden">
            <span class="absolute inset-x-0 top-0 h-1" :style="{ background: accent }"></span>
            <h2 class="text-[1.35rem] font-bold text-ink leading-[1.45]">{{ currentQuestion.q }}</h2>
          </div>

          <!-- Options -->
          <div :key="'opts-' + stepAnimKey" class="quiz-anim flex flex-col gap-3 mb-[26px]">
            <button
              v-for="(opt, i) in currentQuestion.options"
              :key="i"
              class="group/opt relative flex items-center gap-[14px] text-left bg-white border border-solid border-slate-200 rounded-[14px] py-[15px] px-[17px] cursor-pointer text-ink font-body text-[0.95rem] transition-all duration-200 enabled:hover:border-indigo-400/60 enabled:hover:-translate-y-px enabled:hover:shadow-[0_8px_18px_-8px_rgba(99,102,241,0.45)]"
              :class="optionClass(i)"
              :disabled="selected !== null"
              @click="choose(i)"
            >
              <span class="w-[30px] h-[30px] flex-shrink-0 rounded-[9px] flex items-center justify-center font-bold text-[0.82rem] transition-colors" :class="optionLetterClass(i)">{{ String.fromCharCode(65 + i) }}</span>
              <span class="flex-1">{{ opt }}</span>
              <!-- Selection feedback icon -->
              <svg v-if="selected !== null && i === currentQuestion.answer" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              <svg v-else-if="selected === i" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              <!-- Keyboard hint -->
              <span v-if="selected === null" class="hidden sm:inline-flex text-[0.7rem] font-bold text-ink-mute py-0.5 px-1.5 rounded-md border border-solid border-slate-200 bg-slate-50">{{ i + 1 }}</span>
            </button>
          </div>

          <button class="w-full p-[15px] rounded-[14px] border-none text-white font-body font-bold text-[0.95rem] cursor-pointer transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed enabled:hover:-translate-y-px enabled:hover:shadow-[0_10px_22px_-8px_rgba(99,102,241,0.45)]" :style="{ background: `linear-gradient(135deg, ${accent}, ${accent}cc)` }" :disabled="selected === null" @click="nextStep">
            {{ step < totalQuestions - 1 ? t('tests.next') : t('tests.finish') }} →
          </button>
        </div>
      </template>

      <!-- ======================== RESULT ======================== -->
      <template v-else-if="screen === 'result'">
        <div class="relative max-w-[520px] mx-auto text-center pt-[30px] flex flex-col items-center gap-2.5">
          <!-- Confetti burst on great scores -->
          <div v-if="celebrate" aria-hidden="true" class="pointer-events-none absolute inset-x-0 top-0 h-72 overflow-hidden">
            <span
              v-for="p in confettiPieces"
              :key="p.i"
              class="confetti-piece absolute top-0 w-2 h-3 rounded-[2px]"
              :style="{ left: p.left + '%', background: p.hue, animationDelay: p.delay + 's' }"
            ></span>
          </div>

          <div class="relative w-[164px] h-[164px] rounded-full flex items-center justify-center mb-3 shadow-[0_14px_40px_-14px_rgba(15,23,42,0.35)] bg-[conic-gradient(var(--ring)_calc(var(--pct)*1%),rgba(15,23,42,0.08)_0)]" :style="{ '--pct': scorePct, '--ring': ringColor }">
            <div class="absolute w-[130px] h-[130px] rounded-full bg-white"></div>
            <div class="relative z-10 flex flex-col items-center">
              <span class="font-display text-[2.4rem] leading-none font-extrabold" :style="{ color: ringColor }">{{ scorePct }}%</span>
              <span class="text-[0.72rem] font-bold uppercase tracking-wide text-ink-soft mt-1">{{ t('tests.correctCount', { correct: correctCount, total: totalQuestions }) }}</span>
            </div>
          </div>
          <h2 class="font-display text-[1.7rem] font-extrabold text-ink">{{ resultMessage }}</h2>

          <!-- Stats grid -->
          <div class="grid grid-cols-3 gap-2.5 w-full mt-3">
            <div class="rounded-xl bg-green-400/10 border border-solid border-green-400/25 py-3 px-2">
              <div class="font-display text-[1.25rem] font-extrabold text-green-700 leading-none tabular-nums">{{ correctCount }}</div>
              <div class="text-[0.7rem] font-bold uppercase tracking-wide text-ink-soft mt-1">{{ t('tests.correctLabel') }}</div>
            </div>
            <div class="rounded-xl bg-red-400/10 border border-solid border-red-400/25 py-3 px-2">
              <div class="font-display text-[1.25rem] font-extrabold text-red-600 leading-none tabular-nums">{{ totalQuestions - correctCount }}</div>
              <div class="text-[0.7rem] font-bold uppercase tracking-wide text-ink-soft mt-1">{{ t('tests.wrongLabel') }}</div>
            </div>
            <div class="rounded-xl bg-indigo-500/10 border border-solid border-indigo-500/25 py-3 px-2">
              <div class="font-display text-[1.25rem] font-extrabold text-indigo-600 leading-none tabular-nums">{{ activeQuiz ? progress[activeQuiz.id]?.bestPct ?? scorePct : scorePct }}%</div>
              <div class="text-[0.7rem] font-bold uppercase tracking-wide text-ink-soft mt-1">{{ t('tests.bestLabel') }}</div>
            </div>
          </div>

          <p class="inline-flex items-center gap-2 text-violet-700 text-[0.88rem] font-semibold bg-violet-400/10 border border-solid border-violet-400/25 py-2 px-4 rounded-full mt-3">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            {{ nextReviewDays > 0 ? t('tests.nextReview', { n: nextReviewDays }) : t('tests.reviewSoon') }}
          </p>

          <div class="flex gap-3 mt-[22px]">
            <button class="py-3 px-6 rounded-[12px] font-body font-bold text-[0.9rem] cursor-pointer transition-all duration-200 border border-solid border-transparent bg-gradient-to-br from-indigo-500 to-violet-500 text-white hover:-translate-y-px hover:shadow-[0_10px_22px_-8px_rgba(99,102,241,0.45)]" @click="startQuiz(activeQuiz!)">{{ t('tests.retry') }}</button>
            <button class="py-3 px-6 rounded-[12px] font-body font-bold text-[0.9rem] cursor-pointer transition-all duration-200 border border-solid bg-slate-100 border-slate-200 text-ink-soft hover:text-ink" @click="backToList">{{ t('tests.backToList') }}</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* Question + options fade-up — restarts on every step (stepAnimKey). */
.quiz-anim {
  animation: quiz-fade-up 0.35s cubic-bezier(0.16, 1, 0.3, 1) both;
}
@keyframes quiz-fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: none; }
}

/* Confetti — deterministic positions seeded from setup, falling animation here. */
.confetti-piece {
  animation: confetti-fall 1.8s cubic-bezier(0.45, 0.05, 0.55, 0.95) forwards;
  opacity: 0;
  transform-origin: center;
}
@keyframes confetti-fall {
  0%   { transform: translate3d(0, -20px, 0) rotate(0deg); opacity: 0; }
  10%  { opacity: 1; }
  100% { transform: translate3d(0, 260px, 0) rotate(540deg); opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .quiz-anim,
  .confetti-piece {
    animation: none;
    opacity: 1;
  }
}
</style>
