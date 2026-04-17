import en from './locales/en.json'
import frJson from './locales/fr.json'

export type TranslationSchema = typeof en
const fr: TranslationSchema = frJson

export const resources = {
  en: { translation: en },
  fr: { translation: fr },
} as const

export const defaultLanguage = 'fr' as const
