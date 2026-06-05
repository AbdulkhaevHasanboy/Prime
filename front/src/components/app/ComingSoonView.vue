<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  pageId: string
}>()

const emit = defineEmits<{
  (e: 'navigate', id: string): void
}>()

const { t } = useI18n()
</script>

<template>
  <div class="flex h-full items-center justify-center p-8">
    <div class="flex max-w-[420px] flex-col items-center gap-2.5 text-center">
      <div class="text-[3.4rem]">🚧</div>
      <span class="text-[0.8rem] font-bold uppercase tracking-[0.08em] text-indigo-600">{{ t(`nav.${pageId}`) }}</span>
      <h2 class="font-display text-[1.7rem] font-extrabold text-ink">{{ t('coming.title') }}</h2>
      <p class="leading-relaxed text-ink-soft">{{ t('coming.text') }}</p>
      <button
        class="mt-3 cursor-pointer rounded-[11px] bg-gradient-to-br from-indigo-500 to-violet-500 px-6 py-[11px] font-body text-[0.9rem] font-bold text-white transition-all duration-200 hover:-translate-y-px hover:shadow-[0_6px_16px_rgba(99,102,241,0.25)]"
        @click="emit('navigate', 'home')"
      >
        {{ t('coming.backHome') }}
      </button>
    </div>
  </div>
</template>
