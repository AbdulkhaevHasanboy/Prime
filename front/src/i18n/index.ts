import { createI18n } from 'vue-i18n'
import en from './locales/en'
import ru from './locales/ru'
import uz from './locales/uz'

export type LocaleCode = 'en' | 'ru' | 'uz'

/**
 * The languages the UI offers. `aiName` is the human-readable name we hand to
 * Gemini so it can generate / translate the experience into that language.
 */
export const SUPPORTED_LOCALES: { code: LocaleCode; label: string; flag: string; aiName: string }[] = [
  { code: 'en', label: 'English', flag: '🇬🇧', aiName: 'English' },
  { code: 'ru', label: 'Русский', flag: '🇷🇺', aiName: 'Russian' },
  { code: 'uz', label: "O‘zbekcha", flag: '🇺🇿', aiName: 'Uzbek (Latin script)' },
]

const STORAGE_KEY = 'SimuLink-locale'

function isSupported(code: string | null): code is LocaleCode {
  return !!code && SUPPORTED_LOCALES.some((l) => l.code === code)
}

/** Remembered choice → browser language → English. */
function detectInitial(): LocaleCode {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (isSupported(saved)) return saved
  const nav = navigator.language?.slice(0, 2)
  if (isSupported(nav)) return nav
  return 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: detectInitial(),
  fallbackLocale: 'en',
  messages: { en, ru, uz },
})

/** The currently active locale code. */
export function currentLocaleCode(): LocaleCode {
  return i18n.global.locale.value as LocaleCode
}

/** Switch the UI language and persist the choice. */
export function setLocale(code: LocaleCode) {
  i18n.global.locale.value = code
  localStorage.setItem(STORAGE_KEY, code)
  document.documentElement.lang = code
}

/** The name we pass to the AI for generation / translation. */
export function aiLanguageName(code: LocaleCode = currentLocaleCode()): string {
  return SUPPORTED_LOCALES.find((l) => l.code === code)?.aiName ?? 'English'
}

document.documentElement.lang = currentLocaleCode()
