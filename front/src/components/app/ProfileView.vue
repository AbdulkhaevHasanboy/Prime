<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '../../composables/useToast'
import { getProfile, updateProfile, getMe, setupMfa, verifyMfa } from '../../managers/apiClient'
import {
  getToken,
  updateStoredUser,
  avatarFor,
  type UserSession,
} from '../../managers/authManager'

const props = defineProps<{
  user: UserSession
}>()

const emit = defineEmits<{
  (e: 'update-user', user: UserSession): void
}>()

const { t } = useI18n()
const { showToast } = useToast()

/* ----------------------------------------------------------------
   Editable profile, backed by the FastAPI /auth/profile endpoints.
----------------------------------------------------------------- */
const form = reactive({
  first_name: '',
  last_name: '',
  bio: '',
  avatar_url: '',
  gender: '',
  education_class: '',
  favorite_subject: '',
  custom_subject: ''
})
const loading = ref(true)
const saving = ref(false)
const showEdit = ref(false)

const mfaEnabled = ref(false)
const mfaLoading = ref(false)
const showMfaSetup = ref(false)
const mfaSecret = ref('')
const mfaUri = ref('')
const mfaCodeInput = ref('')
const mfaVerifying = ref(false)

function openEdit() {
  showEdit.value = true
}

function closeEdit() {
  showEdit.value = false
}

onMounted(async () => {
  const token = getToken()
  const savedExtra = localStorage.getItem('prime_profile_extra')
  if (savedExtra) {
    try {
      const extra = JSON.parse(savedExtra)
      form.gender = extra.gender ?? ''
      form.education_class = extra.education_class ?? ''
      form.favorite_subject = extra.favorite_subject ?? ''
      form.custom_subject = extra.custom_subject ?? ''
    } catch (e) {
      console.error(e)
    }
  }

  if (!token) {
    loading.value = false
    return
  }
  try {
    const [p, me] = await Promise.all([
      getProfile(token),
      getMe(token)
    ])
    form.first_name = p.first_name ?? ''
    form.last_name = p.last_name ?? ''
    form.bio = p.bio ?? ''
    form.avatar_url = p.avatar_url ?? ''
    mfaEnabled.value = me.mfa_enabled
  } catch {
    /* no profile yet, or offline — keep the empty form */
  } finally {
    loading.value = false
  }
})

async function saveProfile() {
  const token = getToken()
  if (!token) {
    showToast(t('profile.edit.noSession'), 'error')
    return
  }
  saving.value = true
  try {
    const p = await updateProfile(token, {
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      bio: form.bio.trim(),
      avatar_url: form.avatar_url.trim(),
    })
    const extra = {
      gender: form.gender,
      education_class: form.education_class,
      favorite_subject: form.favorite_subject,
      custom_subject: form.custom_subject
    }
    localStorage.setItem('prime_profile_extra', JSON.stringify(extra))

    const display = [p.first_name, p.last_name].filter(Boolean).join(' ').trim() || props.user.name
    const avatar = (p.avatar_url ?? '').trim() || avatarFor(display)
    const patched = updateStoredUser({ name: display, avatar })
    if (patched) emit('update-user', patched)
    showToast(t('profile.edit.saved'), 'success')
    closeEdit()
  } catch (err) {
    showToast(err instanceof Error ? err.message : t('profile.edit.saveError'), 'error')
  } finally {
    saving.value = false
  }
}

async function startMfaSetup() {
  const token = getToken()
  if (!token) return
  mfaLoading.value = true
  try {
    const res = await setupMfa(token)
    mfaSecret.value = res.secret
    mfaUri.value = res.uri
    showMfaSetup.value = true
  } catch (err) {
    showToast(t('auth.toasts.generic'), 'error')
  } finally {
    mfaLoading.value = false
  }
}

async function confirmMfa() {
  const token = getToken()
  if (!token) return
  const code = mfaCodeInput.value.trim()
  if (code.length !== 6 || !/^\d+$/.test(code)) {
    showToast(t('auth.toasts.mfaInvalid'), 'error')
    return
  }
  mfaVerifying.value = true
  try {
    await verifyMfa(token, code)
    mfaEnabled.value = true
    showMfaSetup.value = false
    mfaCodeInput.value = ''
    showToast(t('profile.mfaSuccess'), 'success')
  } catch (err) {
    showToast(t('auth.toasts.mfaInvalid'), 'error')
  } finally {
    mfaVerifying.value = false
  }
}

function cancelMfaSetup() {
  showMfaSetup.value = false
  mfaSecret.value = ''
  mfaUri.value = ''
  mfaCodeInput.value = ''
}

const initials = computed(() => {
  const parts = props.user.name.trim().split(/\s+/)
  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1]![0] : ''
  return (first + last).toUpperCase() || 'U'
})

const handle = computed(() => '@' + (props.user.email.split('@')[0] || props.user.name.toLowerCase().replace(/\s+/g, '_')))

const LEVEL = 12
const xpCurrent = 2450
const xpMax = 3000
const xpPercent = Math.round((xpCurrent / xpMax) * 100)

const badges = [
  { id: 'streak30', color: '#6366f1', icon: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>' },
  { id: 'rating5', color: '#8b5cf6', icon: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>' },
  { id: 'xp1000', color: '#a855f7', icon: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>' },
  { id: 'goalMaster', color: '#818cf8', icon: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>' },
  { id: 'premium', color: '#a78bfa', icon: '<path d="m15.477 12.89 1.515 8.526a.5.5 0 0 1-.81.47l-3.58-2.687a1 1 0 0 0-1.197 0l-3.586 2.686a.5.5 0 0 1-.81-.469l1.514-8.526"/><circle cx="12" cy="8" r="6"/>' },
] as const

const stats = [
  { id: 'study', value: '127', unit: true, color: '#6366f1', icon: '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>' },
  { id: 'tests', value: '34', unit: false, color: '#8b5cf6', icon: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>' },
  { id: 'sims', value: '28', unit: false, color: '#a855f7', icon: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>' },
] as const

const knowledge = [
  { id: 'biology', pct: 85, color: '#6366f1' },
  { id: 'physics', pct: 72, color: '#8b5cf6' },
  { id: 'chemistry', pct: 60, color: '#a855f7' },
  { id: 'math', pct: 90, color: '#818cf8' },
  { id: 'english', pct: 78, color: '#a78bfa' },
] as const

const activity = [
  { id: 'photosynthesis', xp: 50 },
  { id: 'newtonTest', xp: 30 },
  { id: 'mentorChat', xp: 10 },
  { id: 'skillSwap', xp: 40 },
] as const
</script>

<template>
  <div class="h-full overflow-y-auto">
    <div class="max-w-[1320px] mx-auto px-7 pt-6 pb-14 grid grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)_minmax(0,1fr)] gap-[22px] items-start max-[1100px]:grid-cols-2 max-[720px]:grid-cols-1 max-[720px]:px-4 max-[720px]:pt-5 max-[720px]:pb-12">
      <!-- Left column -->
      <div class="flex flex-col gap-[22px] min-w-0">
        <div class="relative flex flex-col items-center text-center bg-white border border-solid border-slate-200 rounded-[18px] p-[22px] shadow-sm">
          <button class="absolute top-[14px] right-[14px] w-[34px] h-[34px] flex items-center justify-center rounded-[9px] bg-slate-100 border border-solid border-slate-200 text-ink-soft cursor-pointer transition-all duration-200 hover:text-white hover:bg-indigo-500/15 hover:border-indigo-400" :title="t('profile.edit.title')" @click="openEdit">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
          </button>
          <div class="w-[96px] h-[96px] rounded-full flex items-center justify-center font-display font-extrabold text-[2rem] text-white bg-gradient-to-br from-indigo-500 to-violet-500">{{ initials }}</div>
          <h2 class="text-[1.4rem] font-extrabold text-ink mt-[14px]">{{ user.name }}</h2>
          <span class="text-ink-mute text-[0.9rem] mt-[2px]">{{ handle }}</span>
          <div class="inline-flex items-center gap-[6px] mt-[10px] text-[0.92rem] text-ink">
            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="#fbbf24" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            <strong>4.8</strong>
            <span class="text-ink-mute text-[0.82rem]">{{ t('profile.ratingCount', { n: 127 }) }}</span>
          </div>

          <div class="w-full h-px bg-slate-200 mt-5 mb-4"></div>

          <div class="w-full flex justify-between text-[0.85rem] text-ink-soft mb-2">
            <span>{{ t('nav.level', { n: LEVEL }) }}</span>
            <span>{{ xpCurrent }} / {{ xpMax }} XP</span>
          </div>
          <div class="w-full h-2 rounded-full bg-slate-200 overflow-hidden"><i class="block h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" :style="{ width: xpPercent + '%' }"></i></div>

          <div class="inline-flex items-center gap-2 mt-5 text-[0.95rem] text-ink-soft">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="#fb923c" stroke="#fb923c" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>
            <strong class="text-orange-400 text-[1.05rem]">15</strong>
            <span>{{ t('profile.streakUnit') }}</span>
          </div>

          <div class="w-full h-px bg-slate-200 mt-5 mb-4" v-if="form.gender || form.education_class || form.favorite_subject"></div>
          <div class="w-full text-left text-[0.85rem] flex flex-col gap-2.5" v-if="form.gender || form.education_class || form.favorite_subject">
            <div class="flex justify-between" v-if="form.gender">
              <span class="text-ink-mute font-medium">{{ t('profile.details.gender') }}</span>
              <span class="text-ink font-semibold">{{ t(`profile.gender.${form.gender}`) }}</span>
            </div>
            <div class="flex justify-between" v-if="form.education_class">
              <span class="text-ink-mute font-medium">{{ t('profile.details.class') }}</span>
              <span class="text-ink font-semibold">{{ t(`profile.class.${form.education_class}`) }}</span>
            </div>
            <div class="flex justify-between" v-if="form.favorite_subject">
              <span class="text-ink-mute font-medium">{{ t('profile.details.favSubject') }}</span>
              <span class="text-ink font-semibold">
                {{ form.favorite_subject === 'OTHER' ? form.custom_subject : t(`profile.subjects.${form.favorite_subject}`) }}
              </span>
            </div>
          </div>
        </div>

        <div class="bg-white border border-solid border-slate-200 rounded-[18px] p-[22px] shadow-sm">
          <h3 class="text-[1.05rem] font-bold text-ink mb-4">{{ t('profile.badgesTitle') }}</h3>
          <div class="grid grid-cols-3 gap-3">
            <div v-for="b in badges" :key="b.id" class="flex flex-col items-center gap-2 py-[14px] px-2 rounded-[13px] bg-slate-50 border border-solid border-slate-200 text-center">
              <span class="flex" :style="{ color: b.color }">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="b.icon"></svg>
              </span>
              <span class="text-[0.72rem] font-semibold text-ink-soft">{{ t(`profile.badges.${b.id}`) }}</span>
            </div>
          </div>
        </div>

        <!-- MFA Card -->
        <div class="bg-white border border-solid border-slate-200 rounded-[18px] p-[22px] shadow-sm flex flex-col gap-3">
          <div class="flex items-center gap-2.5">
            <span class="w-8 h-8 rounded-[9px] flex items-center justify-center text-white bg-gradient-to-br from-indigo-500 to-violet-500">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            </span>
            <h3 class="text-[1.05rem] font-bold text-ink">{{ t('profile.mfaTitle') }}</h3>
          </div>
          <div v-if="mfaEnabled" class="flex items-center gap-2 text-green-600 bg-green-50 border border-green-200 rounded-xl p-3 text-[0.88rem]">
            <svg class="flex-shrink-0" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            <span>{{ t('profile.mfaEnabledDesc') }}</span>
          </div>
          <div v-else class="flex flex-col gap-3">
            <p class="text-ink-soft text-[0.85rem] leading-normal">{{ t('profile.mfaDisabledDesc') }}</p>
            <button 
              @click="startMfaSetup" 
              :disabled="mfaLoading"
              class="w-full inline-flex items-center justify-center gap-2 py-2.5 px-4 border border-solid border-indigo-400/30 bg-indigo-500/[0.08] text-indigo-700 font-semibold text-[0.88rem] rounded-xl cursor-pointer transition-all hover:bg-indigo-500/15 disabled:opacity-50"
            >
              <span v-if="mfaLoading" class="w-[14px] h-[14px] border-2 border-solid border-indigo-700/30 border-t-indigo-700 rounded-full animate-spin"></span>
              <span>{{ t('profile.mfaEnableBtn') }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Middle column -->
      <div class="flex flex-col gap-[22px] min-w-0">
        <div class="bg-white border border-solid border-slate-200 rounded-[18px] p-[22px] shadow-sm">
          <h3 class="text-[1.05rem] font-bold text-ink mb-4">{{ t('profile.statsTitle') }}</h3>
          <div class="grid grid-cols-2 gap-[14px]">
            <div v-for="s in stats" :key="s.id" class="bg-slate-50 border border-solid border-slate-200 rounded-[13px] p-4 flex flex-col gap-2">
              <span class="inline-flex items-center gap-2 text-[0.84rem] text-ink-soft">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" :stroke="s.color" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="s.icon"></svg>
                {{ t(`profile.stats.${s.id}`) }}
              </span>
              <span class="font-display text-[1.6rem] font-extrabold text-ink">{{ s.value }}<small v-if="s.unit" class="text-[0.95rem] font-semibold text-ink-soft"> {{ t('profile.stats.studyUnit') }}</small></span>
            </div>
          </div>
        </div>

        <div class="bg-white border border-solid border-slate-200 rounded-[18px] p-[22px] shadow-sm">
          <h3 class="text-[1.05rem] font-bold text-ink mb-4">{{ t('profile.knowledgeTitle') }}</h3>
          <div class="flex flex-col gap-4">
            <div v-for="k in knowledge" :key="k.id">
              <div class="flex justify-between text-[0.88rem] text-ink mb-[7px]">
                <span>{{ t(`profile.knowledge.${k.id}`) }}</span>
                <span class="text-ink-soft">{{ k.pct }}%</span>
              </div>
              <div class="h-[7px] rounded-full bg-slate-200 overflow-hidden"><i class="block h-full rounded-full" :style="{ width: k.pct + '%', background: k.color }"></i></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right column -->
      <div class="flex flex-col gap-[22px] min-w-0 max-[1100px]:col-span-2 max-[720px]:col-span-1">
        <div class="bg-white border border-solid border-slate-200 rounded-[18px] p-[22px] shadow-sm">
          <h3 class="text-[1.05rem] font-bold text-ink mb-4">{{ t('profile.activityTitle') }}</h3>
          <ul class="list-none flex flex-col gap-[6px]">
            <li v-for="a in activity" :key="a.id" class="flex items-center gap-3 p-3 rounded-[13px] transition-all duration-200 hover:bg-slate-100">
              <span class="w-[38px] h-[38px] flex-shrink-0 rounded-[11px] flex items-center justify-center text-indigo-600 bg-indigo-500/12">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/></svg>
              </span>
              <div class="flex-1 min-w-0 flex flex-col gap-[2px]">
                <span class="text-[0.9rem] font-semibold text-ink">{{ t(`profile.activity.${a.id}.title`) }}</span>
                <span class="text-[0.78rem] text-ink-mute">{{ t(`profile.activity.${a.id}.tag`) }} • {{ t(`profile.activity.${a.id}.time`) }}</span>
              </div>
              <span class="flex-shrink-0 text-[0.82rem] font-bold text-indigo-600">+{{ a.xp }} XP</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Edit profile modal -->
    <Transition name="modal-fade">
      <div v-if="showEdit" class="modal-backdrop fixed inset-0 z-[300] flex items-center justify-center p-6 bg-slate-900/40 backdrop-blur-[4px]" @click.self="closeEdit">
        <div class="modal w-full max-w-[440px] bg-white border border-solid border-slate-200 rounded-[18px] p-[22px] shadow-sm" role="dialog" aria-modal="true">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-[1.05rem] font-bold text-ink">{{ t('profile.edit.title') }}</h3>
            <button class="flex items-center justify-center w-8 h-8 rounded-[9px] bg-slate-100 border border-solid border-slate-200 text-ink-soft cursor-pointer transition-all duration-200 hover:text-white hover:bg-red-400/[0.18] hover:border-red-400/40" :title="t('profile.edit.cancel')" @click="closeEdit">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
          <form class="flex flex-col gap-[14px]" @submit.prevent="saveProfile">
            <div class="grid grid-cols-2 gap-3">
              <label class="flex flex-col gap-[6px]">
                <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.edit.firstName') }}</span>
                <input v-model="form.first_name" type="text" :disabled="loading" :placeholder="t('profile.edit.firstName')" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 resize-y focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" />
              </label>
              <label class="flex flex-col gap-[6px]">
                <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.edit.lastName') }}</span>
                <input v-model="form.last_name" type="text" :disabled="loading" :placeholder="t('profile.edit.lastName')" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 resize-y focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" />
              </label>
            </div>
            <label class="flex flex-col gap-[6px]">
              <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.edit.avatarUrl') }}</span>
              <input v-model="form.avatar_url" type="url" :disabled="loading" placeholder="https://…" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 resize-y focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" />
            </label>

            <div class="grid grid-cols-2 gap-3">
              <label class="flex flex-col gap-[6px]">
                <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.edit.gender') }}</span>
                <select v-model="form.gender" :disabled="loading" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed">
                  <option value="">--</option>
                  <option value="MALE">{{ t('profile.gender.MALE') }}</option>
                  <option value="FEMALE">{{ t('profile.gender.FEMALE') }}</option>
                  <option value="OTHER">{{ t('profile.gender.OTHER') }}</option>
                  <option value="PRIVATE">{{ t('profile.gender.PRIVATE') }}</option>
                </select>
              </label>
              <label class="flex flex-col gap-[6px]">
                <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.edit.class') }}</span>
                <select v-model="form.education_class" :disabled="loading" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed">
                  <option value="">--</option>
                  <option value="PRE_SCHOOL">{{ t('profile.class.PRE_SCHOOL') }}</option>
                  <option value="ELEMENTARY">{{ t('profile.class.ELEMENTARY') }}</option>
                  <option value="HIGH_SCHOOL">{{ t('profile.class.HIGH_SCHOOL') }}</option>
                  <option value="UNI">{{ t('profile.class.UNI') }}</option>
                  <option value="GRADUATED">{{ t('profile.class.GRADUATED') }}</option>
                </select>
              </label>
            </div>

            <label class="flex flex-col gap-[6px]">
              <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.edit.favSubject') }}</span>
              <select v-model="form.favorite_subject" :disabled="loading" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed">
                <option value="">--</option>
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

            <label class="flex flex-col gap-[6px]" v-if="form.favorite_subject === 'OTHER'">
              <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.edit.customSubject') }}</span>
              <input v-model="form.custom_subject" type="text" :disabled="loading" :placeholder="t('profile.edit.customSubject')" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 resize-y focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed" />
            </label>
            <label class="flex flex-col gap-[6px]">
              <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.edit.bio') }}</span>
              <textarea v-model="form.bio" rows="3" :disabled="loading" :placeholder="t('profile.edit.bioPlaceholder')" class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-ink text-[0.9rem] font-body outline-none transition-all duration-200 resize-y focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed"></textarea>
            </label>
            <div class="flex gap-[10px] mt-[6px]">
              <button type="button" class="py-[11px] px-[18px] rounded-[11px] bg-slate-100 border border-solid border-slate-200 text-ink-soft text-[0.9rem] font-semibold font-body cursor-pointer transition-all duration-200 hover:text-ink hover:bg-slate-100" @click="closeEdit">{{ t('profile.edit.cancel') }}</button>
              <button type="submit" class="flex-1 inline-flex items-center justify-center gap-2 mt-[2px] p-[11px] border-none rounded-[11px] bg-gradient-to-br from-indigo-500 to-violet-500 text-white text-[0.9rem] font-bold font-body cursor-pointer transition-all duration-200 enabled:hover:-translate-y-px enabled:hover:shadow-[0_6px_16px_rgba(99,102,241,0.25)] disabled:opacity-60 disabled:cursor-not-allowed" :disabled="loading || saving">
                <span v-if="saving" class="w-[15px] h-[15px] border-2 border-solid border-white/35 border-t-white rounded-full animate-spin"></span>
                <span>{{ saving ? t('profile.edit.saving') : t('profile.edit.save') }}</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </Transition>

    <!-- MFA Setup Modal -->
    <Transition name="modal-fade">
      <div v-if="showMfaSetup" class="modal-backdrop fixed inset-0 z-[300] flex items-center justify-center p-6 bg-slate-900/40 backdrop-blur-[4px]" @click.self="cancelMfaSetup">
        <div class="modal w-full max-w-[440px] bg-white border border-solid border-slate-200 rounded-[18px] p-[22px] shadow-sm text-center" role="dialog" aria-modal="true">
          <div class="flex items-center justify-between mb-4 text-left">
            <h3 class="text-[1.05rem] font-bold text-ink">{{ t('profile.mfaModalTitle') }}</h3>
            <button class="flex items-center justify-center w-8 h-8 rounded-[9px] bg-slate-100 border border-solid border-slate-200 text-ink-soft cursor-pointer transition-all duration-200 hover:text-white hover:bg-red-400/[0.18] hover:border-red-400/40" @click="cancelMfaSetup">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
          
          <p class="text-ink-soft text-[0.88rem] leading-normal text-left mb-4">{{ t('profile.mfaScanQr') }}</p>
          
          <div class="bg-slate-50 border border-solid border-slate-200 p-4 rounded-[14px] inline-block mb-4">
            <img 
              :src="'https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=' + encodeURIComponent(mfaUri)" 
              alt="QR Code" 
              class="w-[160px] h-[160px] block mx-auto bg-white border border-solid border-slate-100 p-1"
            />
          </div>
          
          <div class="text-[0.78rem] font-mono text-ink bg-slate-100 py-1.5 px-3 rounded-lg select-all mb-4 break-all">
            {{ mfaSecret }}
          </div>
          
          <form @submit.prevent="confirmMfa" class="flex flex-col gap-4 text-left">
            <label class="flex flex-col gap-[6px]">
              <span class="text-[0.74rem] font-semibold text-ink-mute uppercase tracking-[0.04em]">{{ t('profile.mfaEnterCode') }}</span>
              <input 
                v-model="mfaCodeInput" 
                type="text" 
                maxLength="6"
                placeholder="000000"
                class="w-full bg-slate-50 border border-solid border-slate-200 rounded-[10px] py-[10px] px-3 text-center tracking-[0.2em] font-mono text-[1.1rem] text-ink outline-none transition-all duration-200 focus:border-brand focus:bg-white focus:shadow-[0_0_0_3px_rgba(99,102,241,0.15)]"
              />
            </label>
            
            <div class="flex gap-[10px]">
              <button type="button" class="py-[11px] px-[18px] rounded-[11px] bg-slate-100 border border-solid border-slate-200 text-ink-soft text-[0.9rem] font-semibold font-body cursor-pointer transition-all duration-200 hover:text-ink hover:bg-slate-100" @click="cancelMfaSetup">{{ t('profile.mfaCancel') }}</button>
              <button type="submit" class="flex-1 inline-flex items-center justify-center gap-2 p-[11px] border-none rounded-[11px] bg-gradient-to-br from-indigo-500 to-violet-500 text-white text-[0.9rem] font-bold font-body cursor-pointer transition-all duration-200 enabled:hover:-translate-y-px enabled:hover:shadow-[0_6px_16px_rgba(99,102,241,0.25)] disabled:opacity-60 disabled:cursor-not-allowed" :disabled="mfaCodeInput.trim().length !== 6 || mfaVerifying">
                <span v-if="mfaVerifying" class="w-[15px] h-[15px] border-2 border-solid border-white/35 border-t-white rounded-full animate-spin"></span>
                <span>{{ mfaVerifying ? t('profile.edit.saving') : t('profile.mfaVerifyBtn') }}</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* Kept: Vue <Transition> enter/leave classes can't be expressed as utilities. */
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
