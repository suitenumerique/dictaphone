import i18n from 'i18next'
import resourcesToBackend from 'i18next-resources-to-backend'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import '@formatjs/intl-durationformat/polyfill.js'
import { Duration } from 'date-fns'

const i18nDefaultNamespace = 'global'

i18n.setDefaultNamespace(i18nDefaultNamespace)
i18n
  .use(
    resourcesToBackend((language: string, namespace: string) => {
      return import(`../locales/${language}/${namespace}.json`)
    })
  )
  .use(initReactI18next)
  .use(LanguageDetector)
  .init({
    supportedLngs: ['en', 'fr', 'nl', 'de'],
    fallbackLng: 'fr',
    ns: i18nDefaultNamespace,
    detection: {
      order: ['localStorage', 'navigator'],
    },
    interpolation: {
      escapeValue: false,
    },
  })
  .then(() => {
    i18n.services.formatter!.add('formatDuration', (value: Duration, lng) => {
      // @ts-expect-error it's ok
      return new Intl.DurationFormat(lng ?? 'en', {
        style: 'narrow',
      }).format(value)
    })
  })
