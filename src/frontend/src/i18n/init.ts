import i18n from 'i18next'
import resourcesToBackend from 'i18next-resources-to-backend'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import '@formatjs/intl-durationformat/polyfill.js'
import {
  Duration,
  format,
  isThisYear,
  isToday,
  isTomorrow,
  isYesterday,
  setDefaultOptions,
} from 'date-fns'
import { enUS, fr } from 'date-fns/locale'

const i18nDefaultNamespace = 'global'
const fallbackLocale = 'fr-FR' as const
const supportedLocales = ['en-US', 'fr-FR'] as const

type SupportedLocale = (typeof supportedLocales)[number]
type BackendLocale = 'en-us' | 'fr-fr'

const backendLocaleBySupportedLocale: Record<SupportedLocale, BackendLocale> = {
  'en-US': 'en-us',
  'fr-FR': 'fr-fr',
}

const supportedLocaleByBackendLocale: Record<BackendLocale, SupportedLocale> = {
  'en-us': 'en-US',
  'fr-fr': 'fr-FR',
}

export const normalizeLanguageTag = (
  language: string | null | undefined
): SupportedLocale => {
  if (!language) {
    return fallbackLocale
  }

  const normalizedLanguage = language.toLowerCase()

  if (normalizedLanguage.startsWith('en')) {
    return 'en-US'
  }
  if (normalizedLanguage.startsWith('fr')) {
    return 'fr-FR'
  }

  return fallbackLocale
}

export const fromBackendLocale = (
  language: string | null | undefined
): SupportedLocale => {
  if (!language) {
    return fallbackLocale
  }

  const normalizedLanguage = language.toLowerCase()
  const backendLanguage =
    normalizedLanguage in supportedLocaleByBackendLocale
      ? (normalizedLanguage as BackendLocale)
      : undefined

  if (!backendLanguage) {
    return normalizeLanguageTag(language)
  }

  return supportedLocaleByBackendLocale[backendLanguage]
}

export const toBackendLocale = (
  language: string | null | undefined
): BackendLocale => {
  return backendLocaleBySupportedLocale[normalizeLanguageTag(language)]
}

const dateFnsLocaleBySupportedLocale = {
  'en-US': enUS,
  'fr-FR': fr,
} as const

i18n.setDefaultNamespace(i18nDefaultNamespace)
i18n.on('languageChanged', (lng) => {
  setDefaultOptions({
    locale: dateFnsLocaleBySupportedLocale[normalizeLanguageTag(lng)] ?? fr,
  })
})

i18n
  .use(
    resourcesToBackend((language: string, namespace: string) => {
      return import(`../locales/${language}/${namespace}.json`)
    })
  )
  .use(initReactI18next)
  .use(LanguageDetector)
  .init({
    supportedLngs: supportedLocales,
    fallbackLng: fallbackLocale,
    ns: i18nDefaultNamespace,
    detection: {
      order: ['localStorage', 'navigator'],
      convertDetectedLanguage: normalizeLanguageTag,
    },
    interpolation: {
      escapeValue: false,
    },
  })
  .then(() => {
    i18n.services.formatter!.add('formatDuration', (value: Duration, lng) => {
      // @ts-expect-error it's ok
      return new Intl.DurationFormat((lng ?? 'en').split('-')[0], {
        style: 'narrow',
      }).format(value)
    })
    i18n.services.formatter!.add(
      'formatDateTimeStatic',
      (value, _lng, options) => {
        return format(value, options?.formatStr ?? 'Pp')
      }
    )
    i18n.services.formatter!.add('formatDateTime', (value, lng, options) => {
      if (isToday(value)) {
        return `${i18n.t('shared:dates.todayAt')} ${format(value, 'p')}`
      } else if (isYesterday(value)) {
        return `${i18n.t('shared:dates.yesterdayAt')} ${format(value, 'p')}`
      } else if (isThisYear(value)) {
        // hacky way to remove the year for now, will not work for future locale
        // https://github.com/date-fns/date-fns/pull/3990
        let dateCleaned = format(value, 'PPP')
        if (lng === 'fr-FR') {
          dateCleaned = dateCleaned.split(' ').slice(0, 2).join(' ')
        } else if (lng === 'en-US') {
          dateCleaned = dateCleaned.split(',')[0].trim()
        }
        return `${dateCleaned} ${i18n.t('shared:dates.at')} ${format(value, 'p')}`
      }
      return format(value, options?.formatStr ?? 'Pp')
    })
    i18n.services.formatter!.add('formatDate', (value, lng, options) => {
      if (isTomorrow(value)) {
        return i18n.t('shared:dates.tomorrow')
      } else if (isToday(value)) {
        return i18n.t('shared:dates.today')
      } else if (isYesterday(value)) {
        return i18n.t('shared:dates.yesterday')
      } else if (isThisYear(value)) {
        // hacky way to remove the year for now, will not work for future locale
        // https://github.com/date-fns/date-fns/pull/3990
        let dateCleaned = format(value, 'PPP')
        if (lng === 'fr-FR') {
          dateCleaned = dateCleaned.split(' ').slice(0, 2).join(' ')
        } else if (lng === 'en-US') {
          dateCleaned = dateCleaned.split(',')[0].trim()
        }
        return dateCleaned
      }
      return format(value, options?.formatStr ?? 'PPP')
    })
  })
