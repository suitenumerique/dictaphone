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
  isYesterday,
  setDefaultOptions,
} from 'date-fns'
import { enUS, fr } from 'date-fns/locale'

const i18nDefaultNamespace = 'global'

const dateFnsLocaleBySupportedLocale = {
  'en-US': enUS,
  'fr-FR': fr,
} as const

i18n.setDefaultNamespace(i18nDefaultNamespace)
i18n.on('languageChanged', (lng) => {
  setDefaultOptions({
    locale:
      dateFnsLocaleBySupportedLocale[
        lng as keyof typeof dateFnsLocaleBySupportedLocale
      ] ?? fr,
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
    supportedLngs: ['en-US', 'fr-FR'],
    fallbackLng: 'fr-FR',
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
      if (isToday(value)) {
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
