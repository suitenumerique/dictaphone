import { Footer, LaGaufreV2, LanguagePicker } from '@gouvfr-lasuite/ui-kit'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { authUrl } from '@/features/auth'
import { useTranslation } from 'react-i18next'
import { PropsWithChildren, useCallback, useMemo, useState } from 'react'
import { LANGUAGES } from '@/layout/HeaderRight'

export function BaseLayout({
  children,
  className,
  showShowcaseAssistant,
  title,
}: PropsWithChildren & {
  className?: string
  showShowcaseAssistant: boolean
  title?: string
}) {
  const { t, i18n } = useTranslation(['home', 'layout'])
  const [selectedLanguage, setSelectedLanguage] = useState<string>(
    i18n.language
  )

  const languages = useMemo(() => {
    return LANGUAGES.map((language) => ({
      ...language,
      isChecked:
        language.value.toLowerCase() === selectedLanguage.toLowerCase(),
    }))
  }, [selectedLanguage])
  const onChange = useCallback(
    (lang: string) => {
      i18n.changeLanguage(lang)
      setSelectedLanguage(lang)
    },
    [i18n, setSelectedLanguage]
  )

  return (
    <div className={`base-layout ${className ?? ''}`}>
      <div className="base-layout__header">
        <div className="base-layout__header__left">
          <img alt="Logo gouvernement" src="/assets/gouv-logo.svg" />
          <a href="/">
            <img
              className="base-layout__header__app-logo"
              alt="L'assistant transcript logo"
              src="/assets/logo-single-line.svg"
            />
          </a>
        </div>
        <div className="base-layout__header__right">
          <div className="base-layout__header__right__shortcuts">
            <LaGaufreV2
              apiUrl={'https://lasuite.numerique.gouv.fr/api/services'}
              // The show more btn is buggy
              showMoreLimit={9}
            />
            <LanguagePicker
              compact
              size="nano"
              languages={languages}
              onChange={onChange}
            />
          </div>
          <div className="base-layout__header__right__separator" />
          <Button
            onClick={() =>
              window.location.replace(authUrl({ returnTo: '/recordings' }))
            }
            size="small"
          >
            {t('login')}
          </Button>
        </div>
      </div>

      {title && <h1 className="base-layout__title">{title}</h1>}
      <section className="base-layout__content">{children}</section>
      {showShowcaseAssistant && (
        <div className="base-layout__showcase-assistant">
          <img
            alt="Logo LaSuite Assistant"
            src="/assets/logo-lasuite-assistant.svg"
          />
          <p>{t('introLasuiteAssistant')}</p>
          <div className="base-layout__showcase-assistant__buttons">
            <Button
              variant="bordered"
              href="https://assistant.numerique.gouv.fr/"
              target="_blank"
            >
              {t('discoverAssistant')}
            </Button>
            <Button href="https://lasuite.numerique.gouv.fr/" target="_blank">
              {t('discoverLaSuite')}
            </Button>
          </div>
        </div>
      )}

      <Footer
        externalLinks={[
          {
            href: 'https://legifrance.gouv.fr/',
            label: 'legifrance.gouv.fr',
          },
          {
            href: 'https://info.gouv.fr/',
            label: 'info.gouv.fr',
          },
          {
            href: 'https://service-public.fr/',
            label: 'service-public.fr',
          },
          {
            href: 'https://data.gouv.fr/',
            label: 'data.gouv.fr',
          },
        ]}
        legalLinks={[
          {
            href: t('layout:legal.legalTermsUrl'),
            label: t('layout:legal.legalTerms'),
          },
          {
            href: t('layout:legal.personalDataUrl'),
            label: t('layout:legal.personalData'),
          },
          {
            href: t('layout:legal.accessibilityUrl'),
            label: t('layout:legal.accessibility'),
          },
          {
            href: t('layout:legal.termsOfServiceUrl'),
            label: t('layout:legal.termsOfService'),
          },
        ]}
        license={{
          label: t('license'),
          link: {
            href: 'https://github.com/etalab/licence-ouverte/blob/master/LO.md',
            label: 'licence etalab-2.0',
          },
        }}
      />
    </div>
  )
}
