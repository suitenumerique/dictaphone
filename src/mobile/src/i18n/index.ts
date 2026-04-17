import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import {
  Duration,
  format,
  isThisYear,
  isToday,
  isYesterday,
  setDefaultOptions,
} from 'date-fns'
import { enUS, fr } from 'date-fns/locale'
import { defaultLanguage, resources } from './resources'
import { getLocales } from 'react-native-localize'

const possibleLocales = new Set(['fr', 'en'])

const userLocales = getLocales()
  .map((locale) => locale.languageCode.split(' ')[0])
  .filter((locale) => possibleLocales.has(locale))

const dateFnsLocaleBySupportedLocale = {
  en: enUS,
  fr: fr,
} as const

i18n.on('languageChanged', (lng) => {
  console.log(lng)
  setDefaultOptions({
    locale:
      dateFnsLocaleBySupportedLocale[
        lng as keyof typeof dateFnsLocaleBySupportedLocale
      ] ?? fr,
  })
})

if (!i18n.isInitialized) {
  i18n
    .use(initReactI18next)
    .init({
      lng: userLocales[0] ?? defaultLanguage,
      compatibilityJSON: 'v4',
      fallbackLng: defaultLanguage,
      interpolation: {
        escapeValue: false,
      },
      resources,
    })
    .then(() => {
      i18n.services.formatter!.add('formatDuration', (value: Duration) => {
        // Proper duration formatting like on the web is harder to do, we are fallbacking to a simplier version
        const minutes =
          (value.minutes ?? 0) +
          60 * (value.hours ?? 0) +
          (value.days ?? 0) * 24 * 60
        const seconds = value.seconds ?? 0
        if (minutes > 0) {
          if (seconds > 0) {
            return i18n.t('shared.utils.durationMinsSeconds', {
              mins: minutes,
              secs: seconds,
            })
          } else {
            return i18n.t('shared.utils.durationMins', { mins: minutes })
          }
        } else {
          return i18n.t('shared.utils.durationSeconds', { secs: seconds })
        }
      })
      i18n.services.formatter!.add(
        'formatDateTimeStatic',
        (value, _lng, options) => {
          return format(value, options?.formatStr ?? 'Pp')
        }
      )
      i18n.services.formatter!.add('formatDateTime', (value, lng, options) => {
        if (isToday(value)) {
          return `${i18n.t('shared.dates.todayAt')} ${format(value, 'p')}`
        } else if (isYesterday(value)) {
          return `${i18n.t('shared.dates.yesterdayAt')} ${format(value, 'p')}`
        } else if (isThisYear(value)) {
          // hacky way to remove the year for now, will not work for future locale
          // https://github.com/date-fns/date-fns/pull/3990
          let dateCleaned = format(value, 'PPP')
          if (lng === 'fr') {
            dateCleaned = dateCleaned.split(' ').slice(0, 2).join(' ')
          } else if (lng === 'en') {
            dateCleaned = dateCleaned.split(',')[0].trim()
          }
          return `${dateCleaned} ${i18n.t('shared.dates.at')} ${format(
            value,
            'p'
          )}`
        }
        return format(value, options?.formatStr ?? 'Pp')
      })
      i18n.services.formatter!.add('formatDate', (value, lng, options) => {
        if (isToday(value)) {
          return i18n.t('shared.dates.today')
        } else if (isYesterday(value)) {
          return i18n.t('shared.dates.yesterday')
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
}

export default i18n
