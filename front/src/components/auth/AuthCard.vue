<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '../../composables/useToast'
import { setApiSession, buildApiUser, type UserSession } from '../../managers/authManager'
import {
  register,
  login,
  loginMfa,
  registerOrLogin,
  getMe,
  getProfile,
  updateProfile,
  forgotPassword,
  type TokenPair,
} from '../../managers/apiClient'
import { SUPPORTED_LOCALES, setLocale, type LocaleCode } from '../../i18n'

const emit = defineEmits<{
  (e: 'login-success', user: UserSession): void
}>()

const { showToast } = useToast()
const { t, locale } = useI18n()

/** Pull a readable message out of whatever was thrown. */
function errText(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  return t('auth.toasts.generic')
}

// Language switcher (lets users pick a language before signing in)
const locales = SUPPORTED_LOCALES
const localeMenuOpen = ref(false)
function chooseLocale(code: LocaleCode) {
  localeMenuOpen.value = false
  setLocale(code)
}

const isLoginMode = ref(true)
const isLoading = ref(false)

// Second-factor step (shown when login returns token_type 'mfa_required')
const mfaStep = ref(false)
const mfaEmail = ref('')
const mfaCode = ref('')

// Form Fields
const name = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const rememberMe = ref(false)
const acceptTerms = ref(false)

// Visual validation & state toggles
const showPassword = ref(false)
const showConfirmPassword = ref(false)

// Reset form fields when toggling modes
const toggleMode = () => {
  isLoginMode.value = !isLoginMode.value
  name.value = ''
  email.value = ''
  password.value = ''
  confirmPassword.value = ''
  acceptTerms.value = false
}

// Email Validation
const isEmailValid = computed(() => {
  if (!email.value) return true // Don't show error if empty
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return emailRegex.test(email.value)
})

// Password Strength Evaluation
const passwordStrength = computed(() => {
  const pwd = password.value
  if (!pwd) return { score: 0, text: '', color: 'transparent' }
  
  let score = 0
  if (pwd.length >= 8) score++
  if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++
  if (/\d/.test(pwd)) score++
  if (/[@$!%*?&]/.test(pwd)) score++
  
  let text = t('auth.weak')
  let color = '#ef4444' // Red

  if (score === 2 || score === 3) {
    text = t('auth.medium')
    color = '#f59e0b' // Amber
  } else if (score === 4) {
    text = t('auth.strong')
    color = '#10b981' // Emerald
  }

  return { score, text, color }
})

const passwordRequirements = computed(() => {
  const pwd = password.value
  return [
    { text: t('auth.req8'), met: pwd.length >= 8 },
    { text: t('auth.reqCase'), met: /[a-z]/.test(pwd) && /[A-Z]/.test(pwd) },
    { text: t('auth.reqNum'), met: /\d/.test(pwd) },
    { text: t('auth.reqSpecial'), met: /[@$!%*?&]/.test(pwd) }
  ]
})

// Validation checks
const canSubmit = computed(() => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  const emailOk = emailRegex.test(email.value)
  const passwordOk = password.value.length >= 6
  
  if (isLoginMode.value) {
    return emailOk && passwordOk
  } else {
    return (
      name.value.trim().length >= 2 &&
      emailOk &&
      passwordStrength.value.score >= 2 &&
      password.value === confirmPassword.value &&
      acceptTerms.value
    )
  }
})

/**
 * Finish a backend login: with the JWT pair, fetch the account + profile,
 * persist the session, and hand the mapped user up to App.
 */
async function completeLogin(
  tokens: TokenPair,
  override: { name?: string; avatar?: string; provider?: UserSession['provider'] } = {},
) {
  const me = await getMe(tokens.access_token)
  // Prefer values passed in (e.g. from Google), then the saved profile.
  let displayName = override.name ?? ''
  let avatarUrl = override.avatar ?? ''
  try {
    const profile = await getProfile(tokens.access_token)
    if (!displayName) displayName = [profile.first_name, profile.last_name].filter(Boolean).join(' ').trim()
    if (!avatarUrl) avatarUrl = profile.avatar_url ?? ''
  } catch {
    /* no profile yet — fall back to the email handle */
  }
  const user = buildApiUser(me.email, me.role, {
    name: displayName || undefined,
    avatar: avatarUrl || undefined,
  })
  if (override.provider) user.provider = override.provider
  setApiSession(user, tokens.access_token, tokens.refresh_token, rememberMe.value)
  emit('login-success', user)
}

// Register (sign-up) or sign in against the FastAPI backend.
const handleSubmit = async () => {
  if (!canSubmit.value) {
    if (!isLoginMode.value && password.value !== confirmPassword.value) {
      showToast(t('auth.mismatch'), 'error')
    } else if (!isLoginMode.value && !acceptTerms.value) {
      showToast(t('auth.toasts.termsRequired'), 'warning')
    }
    return
  }

  const addr = email.value.trim()
  isLoading.value = true
  try {
    if (!isLoginMode.value) {
      // Create the account, then log in to get tokens.
      await register(addr, password.value)
      const tokens = await login(addr, password.value)
      // Persist the full name they typed into their profile.
      const full = name.value.trim()
      if (full) {
        const [first, ...rest] = full.split(/\s+/)
        try {
          await updateProfile(tokens.access_token, {
            first_name: first,
            last_name: rest.join(' '),
          })
        } catch {
          /* non-fatal — they can edit it later from the profile page */
        }
      }
      showToast(t('auth.toasts.signupOk'), 'success')
      await completeLogin(tokens)
      return
    }

    // Sign in.
    const tokens = await login(addr, password.value)
    if (tokens.token_type === 'mfa_required') {
      mfaEmail.value = addr
      mfaStep.value = true
      showToast(t('auth.toasts.mfaPrompt'), 'info')
      return
    }
    await completeLogin(tokens)
  } catch (err) {
    showToast(errText(err), 'error')
  } finally {
    isLoading.value = false
  }
}

// Second factor: verify the 6-digit TOTP code, then finish the login.
const handleMfaSubmit = async () => {
  if (!/^\d{6}$/.test(mfaCode.value.trim())) {
    showToast(t('auth.toasts.mfaInvalid'), 'warning')
    return
  }
  isLoading.value = true
  try {
    const tokens = await loginMfa(mfaEmail.value, mfaCode.value.trim())
    await completeLogin(tokens)
  } catch (err) {
    showToast(errText(err), 'error')
  } finally {
    isLoading.value = false
  }
}

const cancelMfa = () => {
  mfaStep.value = false
  mfaCode.value = ''
  mfaEmail.value = ''
}

/* ----------------------------------------------------------------
   Google sign-in runs CLIENT-SIDE via Google Identity Services
   (VITE_GOOGLE_CLIENT_ID). The backend's own /auth/google endpoint
   isn't configured, so instead we take the verified Google identity
   and bridge it to OUR backend: derive a stable per-account password,
   create the account if needed, then log in to get real JWT tokens.
----------------------------------------------------------------- */
function parseJwt(token: string): Record<string, any> | null {
  try {
    const part = token.split('.')[1]
    if (!part) return null
    const json = decodeURIComponent(
      atob(part.replace(/-/g, '+').replace(/_/g, '/'))
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join(''),
    )
    return JSON.parse(json)
  } catch {
    return null
  }
}

/**
 * Deterministic password for a Google account so the same user logs in
 * every time. Derived from Google's stable `sub` id and includes upper/
 * lower/digit/special to satisfy backend password rules.
 * NOTE: demo-grade — a production app would verify the Google token on the
 * server via a real OAuth endpoint rather than deriving a password here.
 */
function googlePassword(sub: string): string {
  return `Gg1$${sub}`
}

async function handleGoogleCredential(response: { credential?: string }) {
  const credential = response.credential
  const profile = credential ? parseJwt(credential) : null
  if (!credential || !profile?.email) {
    showToast(t('auth.toasts.oauthFail'), 'error')
    return
  }

  const gEmail = String(profile.email)
  const gName = String(profile.name || gEmail.split('@')[0])
  const gPicture = typeof profile.picture === 'string' ? profile.picture : ''
  const gSub = String(profile.sub || gEmail)

  isLoading.value = true
  try {
    // Create the account if it's new, then log in for real JWT tokens.
    const tokens = await registerOrLogin(gEmail, googlePassword(gSub))

    // First-time Google account → seed the profile with their Google name/photo.
    // (Don't overwrite a profile the user has already filled in themselves.)
    try {
      const existing = await getProfile(tokens.access_token)
      if (!existing.first_name && !existing.last_name) {
        const [first, ...rest] = gName.split(/\s+/)
        await updateProfile(tokens.access_token, {
          first_name: first,
          last_name: rest.join(' '),
          avatar_url: gPicture,
        })
      }
    } catch {
      /* non-fatal — profile can be edited later */
    }

    await completeLogin(tokens, { name: gName, avatar: gPicture, provider: 'google' })
    showToast(t('auth.toasts.authedAs', { name: gName }), 'success')
  } catch (err) {
    showToast(errText(err), 'error')
  } finally {
    isLoading.value = false
  }
}

// Initialise GSI and render the official Google button once the script loads.
onMounted(() => {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
  if (!clientId || clientId.includes('YOUR_GOOGLE_CLIENT_ID_HERE')) {
    console.warn('VITE_GOOGLE_CLIENT_ID is not set — Google sign-in disabled.')
    return
  }
  const timer = setInterval(() => {
    if (!window.google) return
    clearInterval(timer)
    window.google.accounts.id.initialize({ client_id: clientId, callback: handleGoogleCredential })
    const container = document.getElementById('google-signin-btn-container')
    if (container) {
      window.google.accounts.id.renderButton(container, {
        type: 'standard',
        theme: 'filled_blue',
        size: 'large',
        text: 'continue_with',
        shape: 'rectangular',
        logo_alignment: 'left',
        width: 380,
      })
    }
  }, 100)
  // Stop polling after 10s to avoid a leak if the script never loads.
  setTimeout(() => clearInterval(timer), 10000)
})

// Forgot password: the backend always returns 200 (to avoid leaking which
// emails exist), so we just acknowledge the request either way.
const handleForgotPassword = async () => {
  if (!email.value) {
    showToast(t('auth.toasts.emailFirst'), 'warning')
    return
  }
  if (!isEmailValid.value) {
    showToast(t('auth.toasts.emailValid'), 'error')
    return
  }
  try {
    await forgotPassword(email.value.trim())
  } catch {
    /* endpoint is best-effort; never surface an error here */
  }
  showToast(t('auth.toasts.resetSent'), 'success')
}
</script>

<template>
  <div class="auth-card">
    <!-- Language switcher -->
    <div class="lang-switcher" :class="{ open: localeMenuOpen }">
      <button class="lang-trigger" @click="localeMenuOpen = !localeMenuOpen" :title="t('language.label')">
        <span class="lang-flag">{{ (locales.find(l => l.code === locale) || locales[0]!).flag }}</span>
        <span class="lang-code">{{ String(locale).toUpperCase() }}</span>
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
      </button>
      <div class="lang-backdrop" v-if="localeMenuOpen" @click="localeMenuOpen = false"></div>
      <div class="lang-menu" v-if="localeMenuOpen">
        <button
          v-for="l in locales"
          :key="l.code"
          class="lang-option"
          :class="{ active: l.code === locale }"
          @click="chooseLocale(l.code)"
        >
          <span class="lang-flag">{{ l.flag }}</span>
          <span>{{ l.label }}</span>
        </button>
      </div>
    </div>

    <!-- Header -->
    <div class="auth-header">
      <div class="brand-logo">
        <img src="/ico.png" alt="Logo" class="logo-icon" />
      </div>
      <h2 class="title">{{ mfaStep ? t('auth.mfaTitle') : isLoginMode ? t('auth.titleLogin') : t('auth.titleSignup') }}</h2>
      <p class="subtitle">
        {{ mfaStep ? t('auth.mfaSubtitle') : isLoginMode ? t('auth.subtitleLogin') : t('auth.subtitleSignup') }}
      </p>
    </div>



    <!-- MFA step: enter the 6-digit code after a password login -->
    <form v-if="mfaStep" @submit.prevent="handleMfaSubmit" class="auth-form">
      <div class="input-group">
        <label for="mfaCode">{{ t('auth.mfaCode') }}</label>
        <div class="input-wrapper">
          <span class="field-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </span>
          <input
            type="text"
            id="mfaCode"
            v-model="mfaCode"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            placeholder="123456"
            required
          />
        </div>
        <span class="validation-msg" style="color: var(--text-muted)">{{ t('auth.mfaHint') }}</span>
      </div>

      <button type="submit" class="submit-btn" :disabled="isLoading">
        <span v-if="isLoading" class="spinner"></span>
        <span v-else>{{ t('auth.verify') }}</span>
      </button>

      <div class="toggle-mode-text">
        <button type="button" class="toggle-link" @click="cancelMfa">{{ t('auth.back') }}</button>
      </div>
    </form>

    <!-- Auth Form -->
    <template v-if="!mfaStep">
    <form @submit.prevent="handleSubmit" class="auth-form">
      <!-- Full Name (Sign Up only) -->
      <Transition name="slide-fade">
        <div v-if="!isLoginMode" class="input-group">
          <label for="name">{{ t('auth.fullName') }}</label>
          <div class="input-wrapper">
            <span class="field-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </span>
            <input
              type="text"
              id="name"
              v-model="name"
              :placeholder="t('auth.fullNamePlaceholder')"
              required
              autocomplete="name"
            />
          </div>
        </div>
      </Transition>

      <!-- Email Address -->
      <div class="input-group">
        <label for="email">{{ t('auth.email') }}</label>
        <div class="input-wrapper" :class="{ 'input-error': email && !isEmailValid }">
          <span class="field-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
          </span>
          <input 
            type="email"
            id="email"
            v-model="email"
            :placeholder="t('auth.emailPlaceholder')"
            required
            autocomplete="email"
          />
        </div>
        <span v-if="email && !isEmailValid" class="validation-msg text-error">{{ t('auth.emailInvalid') }}</span>
      </div>

      <!-- Password -->
      <div class="input-group">
        <div class="input-header-row">
          <label for="password">{{ t('auth.password') }}</label>
          <a v-if="isLoginMode" href="#" @click.prevent="handleForgotPassword" class="forgot-link">{{ t('auth.forgot') }}</a>
        </div>
        <div class="input-wrapper">
          <span class="field-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </span>
          <input 
            :type="showPassword ? 'text' : 'password'" 
            id="password" 
            v-model="password" 
            placeholder="••••••••" 
            required
            autocomplete="current-password"
          />
          <button type="button" class="eye-toggle" @click="showPassword = !showPassword" :title="showPassword ? t('auth.hidePassword') : t('auth.showPassword')">
            <svg v-if="showPassword" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.52 13.52 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>

        <!-- Password Strength Meter (Sign Up only) -->
        <Transition name="slide-fade">
          <div v-if="!isLoginMode && password" class="password-strength-meter">
            <div class="strength-bar-bg">
              <div 
                class="strength-bar-fg" 
                :style="{ width: `${(passwordStrength.score / 4) * 100}%`, backgroundColor: passwordStrength.color }"
              ></div>
            </div>
            <div class="strength-details">
              <span class="strength-label">{{ t('auth.strengthLabel') }} <strong :style="{ color: passwordStrength.color }">{{ passwordStrength.text }}</strong></span>
            </div>
            
            <ul class="requirements-list">
              <li v-for="(req, i) in passwordRequirements" :key="i" :class="{ met: req.met }">
                <span class="req-icon">
                  <svg v-if="req.met" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
                  <circle v-else cx="6" cy="6" r="3" fill="currentColor"/>
                </span>
                <span>{{ req.text }}</span>
              </li>
            </ul>
          </div>
        </Transition>
      </div>

      <!-- Confirm Password (Sign Up only) -->
      <Transition name="slide-fade">
        <div v-if="!isLoginMode" class="input-group">
          <label for="confirmPassword">{{ t('auth.confirm') }}</label>
          <div class="input-wrapper" :class="{ 'input-error': confirmPassword && password !== confirmPassword }">
            <span class="field-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            </span>
            <input 
              :type="showConfirmPassword ? 'text' : 'password'" 
              id="confirmPassword" 
              v-model="confirmPassword" 
              placeholder="••••••••" 
              required
              autocomplete="new-password"
            />
            <button type="button" class="eye-toggle" @click="showConfirmPassword = !showConfirmPassword" :title="showConfirmPassword ? t('auth.hidePassword') : t('auth.showPassword')">
              <svg v-if="showConfirmPassword" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.52 13.52 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" y1="2" x2="22" y2="22"/></svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
            </button>
          </div>
          <span v-if="confirmPassword && password !== confirmPassword" class="validation-msg text-error">{{ t('auth.mismatch') }}</span>
        </div>
      </Transition>

      <!-- Agreement Checkboxes -->
      <div class="checkbox-row">
        <!-- Remember me (Sign In) -->
        <label v-if="isLoginMode" class="checkbox-container">
          <input type="checkbox" v-model="rememberMe" />
          <span class="checkmark"></span>
          <span class="label-text">{{ t('auth.remember') }}</span>
        </label>

        <!-- Terms and Conditions (Sign Up) -->
        <label v-else class="checkbox-container">
          <input type="checkbox" v-model="acceptTerms" required />
          <span class="checkmark"></span>
          <span class="label-text">{{ t('auth.acceptPre') }} <a href="#" @click.prevent class="terms-link">{{ t('auth.usagePolicy') }}</a></span>
        </label>
      </div>

      <!-- Submit Button -->
      <button 
        type="submit" 
        class="submit-btn" 
        :disabled="isLoading || !canSubmit"
      >
        <span v-if="isLoading" class="spinner"></span>
        <span v-else>{{ isLoginMode ? t('auth.access') : t('auth.create') }}</span>
      </button>
    </form>

    <!-- Divider -->
    <div class="divider">
      <span class="divider-text">{{ t('auth.orContinue') }}</span>
    </div>

    <!-- Google sign-in (client-side GSI, bridged to our backend) -->
    <div class="social-wrapper">
      <div id="google-signin-btn-container" class="google-btn-wrapper"></div>
    </div>

    <!-- Toggle Mode Link -->
    <div class="toggle-mode-text">
      <span>{{ isLoginMode ? t('auth.firstTime') : t('auth.already') }}</span>
      <button class="toggle-link" @click="toggleMode">
        {{ isLoginMode ? t('auth.registerHere') : t('auth.signIn') }}
      </button>
    </div>
    </template>
  </div>
</template>

<style scoped>
.auth-card {
  position: relative;
  background: var(--bg-card);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid var(--border-glass);
  border-radius: 24px;
  padding: 40px;
  width: 100%;
  max-width: 460px;
  box-shadow: 0 30px 60px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05);
  animation: scale-up 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

/* Language Switcher */
.lang-switcher {
  position: absolute;
  top: 18px;
  right: 18px;
  z-index: 10;
}

.lang-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-card-light);
  border: 1px solid var(--border-glass);
  color: var(--text-secondary);
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.78rem;
  font-weight: 700;
  transition: var(--transition-fast);
}

.lang-trigger:hover {
  border-color: var(--primary);
  color: var(--text-primary);
}

.lang-flag {
  font-size: 1rem;
  line-height: 1;
}

.lang-switcher.open .lang-trigger svg {
  transform: rotate(180deg);
}

.lang-trigger svg {
  transition: transform 0.2s ease;
}

.lang-backdrop {
  position: fixed;
  inset: 0;
  z-index: 5;
}

.lang-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 160px;
  background: #131a2e;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 6px;
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.lang-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  background: none;
  border: none;
  color: var(--text-secondary);
  padding: 9px 10px;
  border-radius: 7px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  text-align: left;
  transition: var(--transition-fast);
}

.lang-option:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary);
}

.lang-option.active {
  background: rgba(99, 102, 241, 0.18);
  color: var(--text-primary);
}

@keyframes scale-up {
  from {
    opacity: 0;
    transform: scale(0.95) translateY(10px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.auth-header {
  text-align: center;
  margin-bottom: 24px;
}

.brand-logo {
  width: 130px;
  height: 130px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.logo-icon {
  width: 130px;
  height: 130px;
  object-fit: contain;
}

.title {
  font-family: var(--font-display);
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-top: 6px;
  line-height: 1.4;
}



.auth-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

label {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  border-radius: 12px;
  background: var(--bg-card-light);
  border: 1px solid var(--border-glass);
  transition: var(--transition-fast);
}

.input-wrapper:focus-within {
  border-color: var(--primary);
  background: rgba(255, 255, 255, 0.05);
  box-shadow: 0 0 0 4px var(--primary-glow);
}

.input-wrapper.input-error {
  border-color: var(--error);
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.15);
}

.field-icon {
  position: absolute;
  left: 14px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
}

input {
  width: 100%;
  padding: 14px 14px 14px 44px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 0.95rem;
  font-family: var(--font-primary);
  outline: none;
  border-radius: 12px;
}

input::placeholder {
  color: var(--text-muted);
  opacity: 0.6;
}

.eye-toggle {
  position: absolute;
  right: 14px;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: color var(--transition-fast);
}

.eye-toggle:hover {
  color: var(--text-primary);
}

.validation-msg {
  font-size: 0.75rem;
  font-weight: 600;
  margin-top: 2px;
}

.text-error {
  color: #f87171;
}

.forgot-link {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--primary);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.forgot-link:hover {
  color: #818cf8;
}

/* Password Strength Meter styles */
.password-strength-meter {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
  background: rgba(0, 0, 0, 0.15);
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.03);
}

.strength-bar-bg {
  width: 100%;
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
  overflow: hidden;
}

.strength-bar-fg {
  height: 100%;
  width: 0;
  transition: width 0.3s ease, background-color 0.3s ease;
}

.strength-details {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
}

.strength-label {
  color: var(--text-secondary);
}

.requirements-list {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  margin-top: 4px;
}

.requirements-list li {
  font-size: 0.7rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
  transition: color var(--transition-fast);
}

.requirements-list li.met {
  color: var(--success);
}

.req-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

/* Checkbox Checkmark Custom styling */
.checkbox-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 4px 0;
}

.checkbox-container {
  display: flex;
  align-items: center;
  position: relative;
  padding-left: 28px;
  cursor: pointer;
  user-select: none;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: none;
  letter-spacing: 0;
}

.checkbox-container input {
  position: absolute;
  opacity: 0;
  cursor: pointer;
  height: 0;
  width: 0;
}

.checkmark {
  position: absolute;
  left: 0;
  height: 18px;
  width: 18px;
  background-color: var(--bg-card-light);
  border: 1px solid var(--border-glass);
  border-radius: 6px;
  transition: var(--transition-fast);
}

.checkbox-container:hover input ~ .checkmark {
  border-color: var(--primary);
}

.checkbox-container input:checked ~ .checkmark {
  background: var(--primary-gradient);
  border-color: transparent;
}

.checkmark:after {
  content: "";
  position: absolute;
  display: none;
}

.checkbox-container input:checked ~ .checkmark:after {
  display: block;
}

.checkbox-container .checkmark:after {
  left: 6px;
  top: 3px;
  width: 4px;
  height: 8px;
  border: solid white;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

.terms-link {
  color: var(--primary);
  text-decoration: none;
}

.terms-link:hover {
  text-decoration: underline;
}

/* Submit Button */
.submit-btn {
  background: var(--primary-gradient);
  color: white;
  border: none;
  border-radius: 12px;
  padding: 14px;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  transition: var(--transition-fast);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 15px rgba(99, 102, 241, 0.25);
  margin-top: 8px;
}

.submit-btn:hover:not(:disabled) {
  opacity: 0.95;
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2.5px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Divider Styles */
.divider {
  display: flex;
  align-items: center;
  text-align: center;
  margin: 24px 0;
}

.divider::before, .divider::after {
  content: '';
  flex: 1;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.divider-text {
  padding: 0 12px;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Social Wrapper */
.social-wrapper {
  margin-bottom: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}

.google-btn-wrapper {
  width: 100%;
  display: flex;
  justify-content: center;
  min-height: 40px;
}

.social-btn {
  width: 380px;
  max-width: 100%;
}

.google-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 40px;
  background: #fff;
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #1f1f1f;
  border-radius: 4px;
  font-family: var(--font-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.google-btn:hover {
  background: #f5f5f5;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.25);
}

.google-btn:active {
  transform: scale(0.99);
}

.g-icon {
  width: 18px;
  height: 18px;
}

.telegram-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 40px;
  background: rgba(36, 161, 222, 0.15);
  border: 1px solid rgba(36, 161, 222, 0.4);
  color: #54c5ff;
  border-radius: 4px;
  font-family: var(--font-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.telegram-btn:hover {
  background: rgba(36, 161, 222, 0.25);
  border-color: #24A1DE;
  box-shadow: 0 0 12px rgba(36, 161, 222, 0.2);
}

.telegram-btn:active {
  transform: scale(0.99);
}

.tg-icon {
  width: 18px;
  height: 18px;
  fill: currentColor;
}

.google-btn-wrapper :deep(iframe) {
  margin: 0 auto;
}

/* Toggle Mode Footer */
.toggle-mode-text {
  display: flex;
  justify-content: center;
  gap: 6px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.toggle-link {
  background: none;
  border: none;
  color: var(--primary);
  font-weight: 700;
  font-size: 0.85rem;
  cursor: pointer;
  padding: 0;
  transition: color var(--transition-fast);
}

.toggle-link:hover {
  color: #818cf8;
}

/* Transitions */
.slide-fade-enter-active {
  transition: all 0.3s ease-out;
}
.slide-fade-leave-active {
  transition: all 0.25s cubic-bezier(1, 0.5, 0.8, 1);
}
.slide-fade-enter-from,
.slide-fade-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}
</style>
