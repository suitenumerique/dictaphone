import { LaGaufreV2, LanguagePicker, UserMenu } from '@gouvfr-lasuite/ui-kit'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useUser } from '@/features/auth'

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
  const [selectedLanguage, setSelectedLanguage] = useState<TPossibleLanguages>(
    user?.language ?? 'fr-fr'
  )

  // We must set the language to lowercase because django does not use "en-US", but "en-us".

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
      setSelectedLanguage(value as TPossibleLanguages)
      i18n.changeLanguage(value).catch((err) => {
        console.error('Error changing language', err)
      })
      if (user) {
        updateUser({ language: value as TPossibleLanguages })
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
        user={{
          email: user!.email,
          full_name: user!.full_name,
        }}
        logout={logout}
      />
    </>
  )
}
