import { LaGaufreV2, LanguagePicker, UserMenu } from '@gouvfr-lasuite/ui-kit'
import { useCallback, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useUser } from '@/features/auth/api/useUser'
import {
  fromBackendLocale,
  normalizeLanguageTag,
  toBackendLocale,
} from '@/i18n/init'

// eslint-disable-next-line react-refresh/only-export-components
export const LANGUAGES = [
  {
    label: 'Français',
    shortLabel: 'FR',
    value: 'fr-fr',
  },
  {
    label: 'English',
    shortLabel: 'EN',
    value: 'en-us',
  },
] as const

type TPossibleLanguages = (typeof LANGUAGES)[number]['value']

export const LanguagePickerSyncedBackend = () => {
  const { i18n } = useTranslation()
  const { user, updateUser } = useUser()
  const selectedLanguage = (user?.language ??
    toBackendLocale(
      i18n.resolvedLanguage ?? i18n.language
    )) as TPossibleLanguages

  useEffect(() => {
    if (!user?.language) {
      return
    }

    const targetLanguage = fromBackendLocale(user.language)
    const currentLanguage = normalizeLanguageTag(
      i18n.resolvedLanguage ?? i18n.language
    )

    if (currentLanguage !== targetLanguage) {
      i18n.changeLanguage(targetLanguage).catch((err) => {
        console.error('Error changing language from user preferences', err)
      })
    }
  }, [i18n, user?.language])

  const languages = useMemo(() => {
    return LANGUAGES.map((language) => ({
      ...language,
      shortLabel: language.label,
      isChecked:
        language.value.toLowerCase() === selectedLanguage.toLowerCase(),
    }))
  }, [selectedLanguage])

  const onChange = useCallback(
    (value: string) => {
      const backendLanguage = value as TPossibleLanguages
      i18n.changeLanguage(fromBackendLocale(backendLanguage)).catch((err) => {
        console.error('Error changing language', err)
      })
      if (user) {
        updateUser({ language: backendLanguage })
      }
    },
    [i18n, updateUser, user]
  )

  return (
    <LanguagePicker size="small" languages={languages} onChange={onChange} />
  )
}

export const HeaderRight = () => {
  const { logout, user } = useUser()

  return (
    <>
      <LaGaufreV2
        apiUrl={'https://lasuite.numerique.gouv.fr/api/services'}
        // The show more btn is buggy
        showMoreLimit={9}
      />
      <UserMenu
        actions={<LanguagePickerSyncedBackend />}
        user={
          user && user.email
            ? {
                email: user.email,
                full_name: user.full_name ?? undefined,
              }
            : null
        }
        logout={logout}
      />
    </>
  )
}
