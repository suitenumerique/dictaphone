import { useTranslation } from 'react-i18next'
import { authUrl, useUser } from '@/features/auth'
import { Footer, LaGaufreV2, LanguagePicker } from '@gouvfr-lasuite/ui-kit'
import { Button } from '@gouvfr-lasuite/cunningham-react'
import { Redirect } from 'wouter'
import { useCallback, useMemo, useState } from 'react'
import { LANGUAGES } from '@/layout/HeaderRight.tsx'

export function HomePage() {
  const { t, i18n } = useTranslation('home')
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

  const { isLoggedIn, isLoading } = useUser()

  if (isLoading) return <></>

  if (!isLoggedIn) {
    return (
      <div className="home-page">
        <div className="home-page__header">
          <div className="home-page__header__left">
            <img alt="Logo gouvernement" src="/assets/gouv-logo.svg" />
            <img
              className="home-page__header__app-logo"
              alt="L'assistant transcript logo"
              src="/assets/logo-single-line.svg"
            />
          </div>
          <div className="home-page__header__right">
            <div className="home-page__header__right__shortcuts">
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
            <div className="home-page__header__right__separator" />
            <Button
              onClick={() => window.location.replace(authUrl())}
              size="small"
            >
              {t('login')}
            </Button>
          </div>
        </div>

        <section className="home-page__content">
          <img
            className="home-page__app-logo"
            alt="L'assistant transcript logo"
            src="/assets/logo-single-line.svg"
          />
          <div className="home-page__hero">
            <div className="home-page__hero__intro">
              <h1>{t('title')}</h1>
              <p>{t('subtitle')}</p>

              <div className="home-page__hero__intro__buttons">
                <Button onClick={() => window.location.replace(authUrl())}>
                  {t('login')}
                </Button>
                <Button
                  variant="bordered"
                  href="https://assistant.numerique.gouv.fr/"
                  target="_blank"
                >
                  {t('discoverAssistant')}
                </Button>
              </div>
            </div>
            <img alt="Hero Transcripts" src="/assets/hero.svg" />
          </div>

          <div className="home-page__examples">
            <img alt="Example app 1" src="/assets/home/ex-1.svg" />
            <img alt="Example app 2" src="/assets/home/ex-2.svg" />
            <img alt="Example app 3" src="/assets/home/ex-3.svg" />
          </div>
        </section>
        <div className="home-page__showcase-assistant">
          <img
            alt="Logo LaSuite Assistant"
            src="/assets/logo-lasuite-assistant.svg"
          />
          <p>{t('introLasuiteAssistant')}</p>
          <div className="home-page__showcase-assistant__buttons">
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
          legalLinks={
            [
              // {
              //   href: '/legal-notice',
              //   label: 'Legal Mentions',
              // },
              // {
              //   href: '/personal-data-cookies',
              //   label: 'Personal Data and cookies',
              // },
              // {
              //   href: '/accessibility',
              //   label: 'Accessibility: non-compliant',
              // },
            ]
          }
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

  return <Redirect to="/recordings" />
}
