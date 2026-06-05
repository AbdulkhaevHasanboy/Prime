<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AuthCard from './components/auth/AuthCard.vue'
import AppShell from './components/app/AppShell.vue'
import LandingPage from './components/landing/LandingPage.vue'
import ToastContainer from './components/common/ToastContainer.vue'
import { useToast } from './composables/useToast'
import { loadSession, clearSession, type UserSession } from './managers/authManager'

const { showToast } = useToast()
const { t } = useI18n()

const userSession = ref<UserSession | null>(null)
// While logged out: show the public landing page first, then the login card.
const showAuth = ref(false)

function welcome(user: UserSession) {
  showToast(t('app.welcomeBack', { name: user.name, role: t(`roles.${user.role}`) }), 'success')
}

// AuthCard has already stored the tokens; it just hands us the mapped user.
const handleLoginSuccess = (user: UserSession) => {
  userSession.value = user
  welcome(user)
}

// Profile edits in ProfileView bubble up here so the sidebar/header refresh.
const handleUserUpdate = (user: UserSession) => {
  userSession.value = user
}

const handleSignout = () => {
  userSession.value = null
  showAuth.value = false // back to the public landing page
  clearSession()
  showToast(t('app.signedOut'), 'info')
}

// Add/remove body class based on dashboard state
watch(userSession, (isDashboard) => {
  if (isDashboard) {
    document.body.classList.add('is-dashboard')
  } else {
    document.body.classList.remove('is-dashboard')
  }
}, { immediate: true })

onMounted(() => {
  // Restore a remembered local session, if any.
  const saved = loadSession()
  if (saved) {
    userSession.value = saved
    document.body.classList.add('is-dashboard')
  }
})
</script>

<template>
  <!-- Background Animated Blobs -->
  <div class="bg-blobs">
    <div class="blob blob-1"></div>
    <div class="blob blob-2"></div>
    <div class="blob blob-3"></div>
  </div>

  <!-- Main View Container -->
  <main class="app-main-container" :class="{ 'is-dashboard': userSession, 'is-landing': !userSession && !showAuth }">
    <Transition name="page-fade" mode="out-in">
      <div v-if="userSession" class="view-wrapper view-wrapper--full" key="dashboard">
        <AppShell :user="userSession" @signout="handleSignout" @update-user="handleUserUpdate" />
      </div>
      <LandingPage v-else-if="!showAuth" key="landing" @enter="showAuth = true" />
      <div v-else class="view-wrapper" key="auth">
        <AuthCard @login-success="handleLoginSuccess" />
      </div>
    </Transition>
  </main>

  <!-- Active Toast Notifications -->
  <ToastContainer />
</template>

<style scoped>
.app-main-container {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  padding: 24px;
  min-height: 100vh;
}

/* Dashboard + landing take the whole screen — no centered card, no padding */
.app-main-container.is-dashboard,
.app-main-container.is-landing {
  padding: 0;
  align-items: stretch;
  justify-content: stretch;
}

/* The landing page is a normal scrolling document with full-width sections. */
.app-main-container.is-landing {
  display: block;
  min-height: auto;
}

.view-wrapper {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.view-wrapper--full {
  width: 100%;
  height: 100vh;
  align-items: stretch;
}

/* Page Transition animation between Login and Dashboard */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1), transform 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(12px) scale(0.98);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-12px) scale(0.98);
}
</style>
