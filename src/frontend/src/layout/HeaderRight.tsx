import { LaGaufreV2, LanguagePicker } from '@gouvfr-lasuite/ui-kit'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useUser } from '@/features/auth'
import { Button } from '@gouvfr-lasuite/cunningham-react'

const LANGUAGES = [
  {
    label: 'Français',
    value: 'fr-fr',
  },
  {
    label: 'English',
    value: 'en-us',
  },
] as const

type TPossibleLanguages = (typeof LANGUAGES)[number]['value']

export const LanguagePickerSyncedBackend = () => {
  const { i18n } = useTranslation()
  const { user, updateUser } = useUser()
  const [selectedLanguage, setSelectedLanguage] = useState<TPossibleLanguages>(
    user?.language ?? 'en-us'
  )

  // We must set the language to lowercase because django does not use "en-US", but "en-us".

  const languages = useMemo(() => {
    return LANGUAGES.map((language) => ({
      ...language,
      isChecked: language.value === selectedLanguage,
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
  const { t } = useTranslation('layout')
  const { logout } = useUser()

  return (
    <>
      <div className="dictaphone__header-right-tools">
        <LanguagePickerSyncedBackend />
        <Button
          size="small"
          variant="tertiary"
          onClick={() => logout()}
          icon={<span className="material-icons">logout</span>}
        >
          {t('logout')}
        </Button>
      </div>

      <LaGaufreV2
        apiUrl={'https://lasuite.numerique.gouv.fr/api/services'}
        // The show more btn is buggy
        showMoreLimit={9}
      />
    </>
  )
}
