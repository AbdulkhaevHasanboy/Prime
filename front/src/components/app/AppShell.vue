<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '../../composables/useToast'
import { SUPPORTED_LOCALES, setLocale, type LocaleCode } from '../../i18n'
import AppSidebar from './AppSidebar.vue'
import HomeView from './HomeView.vue'
import MentorView from './MentorView.vue'
import SimulationsView from './SimulationsView.vue'
import ProfileView from './ProfileView.vue'
import ComicsView from './ComicsView.vue'
import PolyView from './PolyView.vue'
import TestsView from './TestsView.vue'
import LeaderboardView from './LeaderboardView.vue'
import ScanView from './ScanView.vue'
import ComingSoonView from './ComingSoonView.vue'
import type { UserSession } from '../../managers/authManager'

const props = defineProps<{
  user: UserSession
}>()

const emit = defineEmits<{
  (e: 'signout'): void
  (e: 'update-user', user: UserSession): void
}>()

const { t, locale } = useI18n()
const { showToast } = useToast()

const active = ref('home')
const collapsed = ref(false)
const mentorSeed = ref('')
const mentorSeedId = ref('')

const showRequiredSetup = ref(false)
const setupForm = reactive({
  gender: '',
  education_class: '',
  favorite_subject: '',
  custom_subject: ''
})

onMounted(() => {
  const savedExtra = localStorage.getItem('prime_profile_extra')
  if (!savedExtra) {
    showRequiredSetup.value = true
  } else {
    try {
      const extra = JSON.parse(savedExtra)
      if (!extra.gender || !extra.education_class || !extra.favorite_subject) {
        showRequiredSetup.value = true
      }
    } catch {
      showRequiredSetup.value = true
    }
  }
})

function saveRequiredSetup() {
  if (!setupForm.gender || !setupForm.education_class || !setupForm.favorite_subject) return
  if (setupForm.favorite_subject === 'OTHER' && !setupForm.custom_subject.trim()) return
  
  const extra = {
    gender: setupForm.gender,
    education_class: setupForm.education_class,
    favorite_subject: setupForm.favorite_subject,
    custom_subject: setupForm.custom_subject
  }
  localStorage.setItem('prime_profile_extra', JSON.stringify(extra))
  showRequiredSetup.value = false
  showToast(t('profile.edit.saved'), 'success')
  window.location.reload()
}

const REAL_PAGES = ['home', 'mentor', 'sims', 'profile', 'comics', 'poly', 'tests', 'leaderboard', 'scan']
const isComing = computed(() => !REAL_PAGES.includes(active.value))

function navigate(id: string) {
  active.value = id
}

function openSim(payload: { id: string; topic: string }) {
  mentorSeedId.value = payload.id
  mentorSeed.value = payload.topic
  active.value = 'mentor'
}

function clearMentorSeed() {
  mentorSeed.value = ''
  mentorSeedId.value = ''
}

function handleSignout() {
  showToast(t('toasts.signingOut'), 'info')
  setTimeout(() => emit('signout'), 500)
}

/* Language switcher */
const locales = SUPPORTED_LOCALES
const localeMenuOpen = ref(false)
const activeLocale = computed(() => locales.find((l) => l.code === locale.value) ?? locales[0]!)

function chooseLocale(code: LocaleCode) {
  localeMenuOpen.value = false
  if (code === locale.value) return
  setLocale(code)
}
</script>

<template>
  <div class="flex w-full h-screen overflow-hidden">
    <AppSidebar
      :active="active"
      :collapsed="collapsed"
      :user="props.user"
      @navigate="navigate"
      @toggle="collapsed = !collapsed"
    />

    <div class="flex-1 flex flex-col min-w-0 h-screen">
      <!-- Top bar: language + sign out -->
      <header class="h-[52px] flex-shrink-0 flex items-center justify-end gap-3 px-[22px]">
        <div class="relative" :class="{ open: localeMenuOpen }">
          <button class="flex items-center gap-1.5 bg-slate-100 border border-solid border-slate-200 text-ink-soft px-[11px] py-[7px] rounded-[9px] cursor-pointer text-[0.8rem] font-semibold font-display transition-all duration-200 hover:bg-slate-200 hover:text-ink" @click="localeMenuOpen = !localeMenuOpen" :title="t('language.label')">
            <span class="text-base leading-none">{{ activeLocale.flag }}</span>
            <span>{{ activeLocale.code.toUpperCase() }}</span>
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="transition-transform duration-200" :class="{ 'rotate-180': localeMenuOpen }"><path d="m6 9 6 6 6-6"/></svg>
          </button>
          <div class="fixed inset-0 z-[150]" v-if="localeMenuOpen" @click="localeMenuOpen = false"></div>
          <div class="absolute top-[calc(100%+6px)] right-0 min-w-[160px] bg-white border border-solid border-slate-200 rounded-[10px] p-1.5 shadow-sm shadow-[0_12px_30px_rgba(15,23,42,0.15)] z-[200] flex flex-col gap-0.5" v-if="localeMenuOpen">
            <button
              v-for="l in locales"
              :key="l.code"
              class="flex items-center gap-2.5 w-full bg-none border-none text-ink-soft px-2.5 py-[9px] rounded-[7px] cursor-pointer text-[0.85rem] font-medium font-display text-left transition-all duration-200 hover:bg-slate-100 hover:text-ink"
              :class="{ 'bg-indigo-500/12 text-ink': l.code === locale }"
              @click="chooseLocale(l.code)"
            >
              <span class="text-base leading-none">{{ l.flag }}</span>
              <span>{{ l.label }}</span>
            </button>
          </div>
        </div>

        <button class="flex items-center justify-center w-9 h-9 bg-slate-100 border border-solid border-slate-200 text-ink-soft rounded-[9px] cursor-pointer transition-all duration-200 hover:bg-red-500/15 hover:text-red-600 hover:border-red-500/30" @click="handleSignout" :title="t('header.signOut')">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        </button>
      </header>

      <div class="app-view flex-1 min-h-0 relative">
        <HomeView v-show="active === 'home'" @navigate="navigate" />
        <MentorView
          v-show="active === 'mentor'"
          :seed="mentorSeed"
          :seed-id="mentorSeedId"
          @seed-consumed="clearMentorSeed"
        />
        <SimulationsView v-show="active === 'sims'" @open="openSim" />
        <ScanView v-show="active === 'scan'" />
        <ProfileView v-show="active === 'profile'" :user="props.user" @update-user="emit('update-user', $event)" />
        <ComicsView v-show="active === 'comics'" />
        <PolyView v-show="active === 'poly'" @navigate="navigate" />
        <TestsView v-show="active === 'tests'" />
        <LeaderboardView v-show="active === 'leaderboard'" :user="props.user" />
        <ComingSoonView v-if="isComing" :page-id="active" @navigate="navigate" />
      </div>
    </div>
    <!-- Required profile fields setup dialog -->
    <Transition name="modal-fade">
      <div v-if="showRequiredSetup" class="fixed inset-0 z-[500] flex items-center justify-center p-6 bg-slate-900/60 backdrop-blur-[6px]">
        <div class="w-full max-w-[460px] bg-white border border-solid border-slate-200 rounded-[22px] p-[26px] shadow-2xl relative" role="dialog" aria-modal="true">
          <div class="text-center mb-6">
            <div class="w-14 h-14 rounded-full bg-indigo-500/10 text-indigo-600 flex items-center justify-center mx-auto mb-3.5">
              <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
            <h3 class="text-[1.2rem] font-extrabold text-ink leading-tight">{{ t('profile.requiredSetup.title') }}</h3>
            <p class="text-ink-soft text-[0.84rem] mt-2 leading-relaxed">{{ t('profile.requiredSetup.desc') }}</p>
          </div>

          <form class="flex flex-col gap-[14px]" @submit.prevent="saveRequiredSetup">
            <div class="grid grid-cols-2 gap-3">
              <label class="flex flex-col gap-[6px]">
                <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.requiredSetup.gender') }}</span>
                <select v-model="setupForm.gender" required class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 focus:border-indigo-500 focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)]">
                  <option value="" disabled selected>--</option>
                  <option value="MALE">{{ t('profile.gender.MALE') }}</option>
                  <option value="FEMALE">{{ t('profile.gender.FEMALE') }}</option>
                  <option value="OTHER">{{ t('profile.gender.OTHER') }}</option>
                  <option value="PRIVATE">{{ t('profile.gender.PRIVATE') }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-[6px]">
                <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.requiredSetup.class') }}</span>
                <select v-model="setupForm.education_class" required class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 focus:border-indigo-500 focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)]">
                  <option value="" disabled selected>--</option>
                  <option value="PRE_SCHOOL">{{ t('profile.class.PRE_SCHOOL') }}</option>
                  <option value="ELEMENTARY">{{ t('profile.class.ELEMENTARY') }}</option>
                  <option value="HIGH_SCHOOL">{{ t('profile.class.HIGH_SCHOOL') }}</option>
                  <option value="UNI">{{ t('profile.class.UNI') }}</option>
                  <option value="GRADUATED">{{ t('profile.class.GRADUATED') }}</option>
                </select>
              </label>
            </div>

            <label class="flex flex-col gap-[6px]">
              <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.requiredSetup.favSubject') }}</span>
              <select v-model="setupForm.favorite_subject" required class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 focus:border-indigo-500 focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)]">
                <option value="" disabled selected>--</option>
                <option value="MATH">{{ t('profile.subjects.MATH') }}</option>
                <option value="PE">{{ t('profile.subjects.PE') }}</option>
                <option value="PHYSICS">{{ t('profile.subjects.PHYSICS') }}</option>
                <option value="CHEMISTRY">{{ t('profile.subjects.CHEMISTRY') }}</option>
                <option value="BIOLOGY">{{ t('profile.subjects.BIOLOGY') }}</option>
                <option value="HISTORY">{{ t('profile.subjects.HISTORY') }}</option>
                <option value="GEOGRAPHY">{{ t('profile.subjects.GEOGRAPHY') }}</option>
                <option value="CODING">{{ t('profile.subjects.CODING') }}</option>
                <option value="OTHER">{{ t('profile.subjects.OTHER') }}</option>
              </select>
            </label>

            <label class="flex flex-col gap-[6px]" v-if="setupForm.favorite_subject === 'OTHER'">
              <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.requiredSetup.customSubject') }}</span>
              <input v-model="setupForm.custom_subject" type="text" required :placeholder="t('profile.requiredSetup.customSubject')" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 focus:border-indigo-500 focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)]" />
            </label>

            <button type="submit" class="w-full mt-2.5 p-[12px] border-none rounded-[12px] bg-gradient-to-br from-indigo-500 to-violet-500 text-white text-[0.92rem] font-bold font-body cursor-pointer transition-all duration-200 hover:-translate-y-px hover:shadow-[0_6px_16px_rgba(99,102,241,0.25)] flex items-center justify-center gap-2">
              <span>{{ t('profile.requiredSetup.btn') }}</span>
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
            </button>
          </form>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* Structural child selector targeting dynamic <component> children rendered
   via v-show/v-if; Tailwind can't express this on the component instances. */
.app-view > * {
  height: 100%;
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}

.modal-fade-enter-active .modal,
.modal-fade-leave-active .modal {
  transition: transform 0.2s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-fade-enter-from .modal,
.modal-fade-leave-to .modal {
  transform: scale(0.95);
}
</style>
